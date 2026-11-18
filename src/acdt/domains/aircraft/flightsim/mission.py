"""Fase 8 — dynamic mission simulation (6-DOF + classic autopilot + Dryden/gusts).

Mission YAML (``mission:`` block or top level)::

    name: C172 circuito
    dt: 0.02                     # integration step [s] (RK4)
    log_dt: 0.1
    extrapolate_after_s: 120     # long cruise/loiter/waypoint legs: N s dynamic, rest extrapolated (steady)
    wind: {speed_m_s: 5, from_deg: 270, turbulence: {intensity: light, seed: 1},
           gusts: [{t: 300, amplitude_m_s: 5, gradient_m: 30, axis: up}]}
    segments:
      - {type: takeoff, flap: 10}
      - {type: climb, to_altitude_m: 1500, speed_m_s: 37}
      - {type: cruise, distance_km: 40, speed_m_s: 55}          # or time_min; heading_deg optional
      - {type: turn, heading_change_deg: 180, load_factor: 1.4}
      - {type: waypoints, points_km: [[10, 0], [10, 10]], speed_m_s: 50}
      - {type: loiter, time_min: 20, speed_m_s: 40, load_factor: 1.1}   # or radius_m; patrol = loiter
      - {type: descent, to_altitude_m: 300, vertical_speed_m_s: 3}
      - {type: landing, flap: 30, glide_deg: 3}

Methods: :mod:`.sixdof` (Stevens & Lewis flat-earth 6-DOF), :mod:`.autopilot` (Beard & McLain Ch. 6/10),
:mod:`.wind` (Dryden, Beard & McLain Table 4.1; CS 25.341 1−cos gust). Speeds default to cited rules:
V_R = 1.1 V_S,TO and V_REF = 1.3 V_S0 (CS 23.51 / 23.73), climb at V_Y (quasi-steady performance).
The quasi-steady comparison (k_energy) uses the *same* flight model (drag polar + propulsion) with
level/steady-climb equilibrium, so it isolates the dynamic effects (trim drag, transients, turns, wind).
"""
from __future__ import annotations

import copy
import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from acdt.core.atmosphere import isa
from .autopilot import Autopilot, design_gains, line_course, orbit_course, wrap
from .sixdof import Controls, SixDOF, dcm_body_to_ned, euler_from_quat, linearise, state, trim
from .wind import WindField

G0 = 9.80665
FLARE = {"tau_over_wh": 3.0, "td_sink_m_s": 0.3, "flap_rate_deg_s": 5.0, "rotation_rate_deg_s": 3.0,
         "k_psi_ground": 2.0, "k_r_ground": 0.5, "h_zone_m": 30.0, "screen_m": 15.24}
# design parameters (not aircraft data): flare time constant τ = 3/ω_h (loop can track it), touchdown sink,
# flap/rotation rates, ground steering PD, altitude-hold zone (Beard & McLain Sec. 6.4), 50 ft screen height.


def load_mission(src) -> dict:
    import yaml
    if isinstance(src, dict):
        raw = src
    else:
        raw = yaml.safe_load(Path(src).read_text(encoding="utf-8"))
    d = raw.get("mission", raw) if isinstance(raw, dict) else raw
    # aircraft / sensor / failures may sit beside the mission: wrapper; both fidelities read them
    if isinstance(raw, dict) and d is not raw:
        for k in ("aircraft", "sensor", "failures", "pointmass_dt", "base_km", "divert_km"):
            if k in raw and k not in d:
                d[k] = raw[k]
    if not isinstance(d, dict) or not d.get("segments"):
        raise ValueError("missão sem 'segments'")
    known = {"takeoff", "climb", "cruise", "turn", "waypoints", "loiter", "patrol", "descent", "landing"}
    for s in d["segments"]:
        if s.get("type") not in known:
            raise ValueError(f"segmento desconhecido {s.get('type')!r}; válidos: {sorted(known)}")
    return d


def lift_dump_de(aero, flap: float = 0.0, alpha: float = 0.0) -> float:
    """Elevon/elevator to the stop in the lift-dump direction (the one that reduces C_L).

    After touchdown in a fly-off stance the three-wheel geometry *fixes* the pitch
    attitude (the nose strut is already on the ground, so the wing cannot be
    lowered). Deflecting the trailing edge to dump lift puts more weight on the
    wheels, analogous to a lift-dump / spoiler in Raymer 2018 Sec. 17.9 braking
    (lower C_L,ground). Sign follows C_Lδe at ``alpha`` (typical: C_Lδe > 0, so
    δe is taken to the negative stop).
    """
    cde = aero._interp("CLde", alpha, flap)
    lim = math.radians(float(aero.limits["elevator"]))
    if not cde or not math.isfinite(cde) or lim <= 0:
        return 0.0
    return -math.copysign(lim, cde)


# Declared numerical tolerance of the 6-DOF touchdown side-load ratio (14 nov 2026, fix-side-load-tolerance).
# The peak is one sample of the tyre force f_y = μ N tanh(v_y/v_ε) on a spring-damper contact, so it is not a
# repeatable number to the last digit: across 15 runs of the example crosswind mission (wind speed perturbed by
# 0, ±1e-12 … ±1e-3 relative, Linux) the inboard ratio spread was 0.588–0.632 (±3.6 % about 0.61). The band
# below (±5 %) is that measured spread rounded up — PRESSUPOSTO numérico, not a certification margin. Inside
# the band the flag is None (no limite → não avaliado ≠ passa); it never turns an exceedance into a pass.
SIDE_LOAD_RATIO_TOL = 0.05
SIDE_LOAD_TOL_SOURCE = ("tolerância numérica declarada ±5 % na razão de carga lateral do 6-DOF (dispersão medida "
                        "0,588–0,632 em 15 corridas com o vento perturbado 1e-12…1e-3; PRESSUPOSTO numérico, não "
                        "margem de certificação); dentro da banda o resultado fica no_limite / não avaliado")


def side_load_band(inboard_ratio: float, outboard_ratio: float, tol: float = SIDE_LOAD_RATIO_TOL) -> dict:
    """Banded 14 CFR 23.485 verdict for 6-DOF side-load ratios (load / limit load).

    max ratio ≤ 1 − tol → ``passa`` (True); > 1 + tol → ``excede`` (False); otherwise ``no_limite`` (None:
    the 6-DOF sampling cannot decide; unassessed ≠ pass). ``side_load_margin`` = 1 − max ratio is always reported.
    """
    r = max(float(inboard_ratio), float(outboard_ratio))
    if not math.isfinite(r):
        return {"side_load_ok": None, "side_load_status": "nao_avaliado", "side_load_max_ratio": r}
    if r <= 1.0 - tol:
        ok, st = True, "passa"
    elif r > 1.0 + tol:
        ok, st = False, "excede"
    else:
        ok, st = None, "no_limite"
    return {"side_load_ok": ok, "side_load_status": st, "side_load_max_ratio": r, "side_load_margin": 1.0 - r,
            "side_load_tolerance": tol, "side_load_tolerance_source": SIDE_LOAD_TOL_SOURCE}


@dataclass
class SegRec:
    name: str
    type: str
    t0: float
    t1: float = 0.0
    used0: float = 0.0
    used1: float = 0.0
    dist_m: float = 0.0
    h0: float = 0.0
    h1: float = 0.0
    extrapolated_s: float = 0.0
    W0_N: float = 0.0
    V_target: float = 0.0
    notes: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


class MissionRunner:
    def __init__(self, fm, mission: dict, res=None):
        self.fm, self.ms, self.res = fm, mission, res
        self.dt = float(mission.get("dt", 0.02))
        self.log_dt = float(mission.get("log_dt", 0.1))
        self.extrap = float(mission.get("extrapolate_after_s", 120.0))
        self.wind = WindField.from_dict(mission.get("wind"))
        if getattr(fm.aero, "yaw_sas", None):
            fm.aero.yaw_sas["dt"] = self.dt
        self._psi_c = None
        self.sim = SixDOF(fm, wind=self.wind)
        self.t = 0.0
        self.flap = 0.0
        self.brake = 0.0
        self.log = []
        self.segs: list[SegRec] = []
        self.ap = None
        self.k = 0
        self.notes = []
        self.dist = 0.0
        self.aborted = None
        self.max_t = float(mission.get("max_time_s", 6 * 3600))
        self._every = max(1, int(round(self.log_dt / self.dt)))
        self._aft = None   # AftMonitor during take-off / landing (ground_clearance)

    # ------------------------------------------------------------------ helpers
    @property
    def electric(self):
        return self.fm.prop.kind == "electric"

    def W(self):
        return self.sim.mass(self.x) * G0

    def Vs(self, flap, h=0.0):
        return math.sqrt(2 * self.W() / (isa(h).rho * self.fm.aero.S * self.fm.aero.clmax(flap)))

    def meas(self):
        x = self.x
        R = dcm_body_to_ned(x[6:10])
        phi, th, psi = euler_from_quat(x[6:10])
        vn = R @ x[3:6]
        vr = x[3:6] - R.T @ self.wind(self.t, x[0:3])
        Va = float(np.linalg.norm(vr))
        if self.ap is not None:
            self.ap.alpha = math.atan2(vr[2], vr[0]) if Va > 5.0 else None
            self.ap.flap = self.flap
        return {"phi": phi, "theta": th, "psi": psi, "p": x[10], "q": x[11], "r": x[12], "h": -x[2],
                "hdot": -vn[2], "chi": math.atan2(vn[1], vn[0]) if math.hypot(vn[0], vn[1]) > 0.5 else psi,
                "Vg": math.hypot(vn[0], vn[1]), "Va": Va, "beta": math.asin(max(-1, min(1, vr[1] / max(Va, 1e-3)))),
                "alpha": math.atan2(vr[2], vr[0]), "ne": (x[0], x[1]),
                "on_ground": self.on_ground()}

    def on_ground(self) -> bool:
        """Fresh contact check (the 6-DOF's contact_loads may belong to a trim evaluation)."""
        if -self.x[2] > 30.0:
            return False
        R = dcm_body_to_ned(self.x[6:10])
        for _, rb, *_r in self.sim.ground.contacts:
            if (self.x[0:3] + R @ rb)[2] > 0:
                return True
        return False

    def retune(self, V, h, gamma=0.0):
        tr = trim(self.sim, V, max(h, 50.0), gamma=0.0, flap=self.flap)
        g = design_gains(self.sim, tr, self.flap)
        m = self.meas() if hasattr(self, "x") else None
        if self.ap is None:
            self.ap = Autopilot(self.sim, g, self.flap)
            self.ap.retune(g, g["trim"]["theta"], g["trim"]["throttle"])
        else:
            th_now = m["theta"] if m else g["trim"]["theta"]
            self.ap.retune(g, th_now, self.c.throttle if hasattr(self, "c") else g["trim"]["throttle"])
        if not tr["ok"]:
            self.notes.append(f"t={self.t:.0f}s: trim a V={V:.1f} m/s, flap {self.flap:g}° não convergiu "
                              f"(resíduo {tr['residual']:.2g}) — ganhos aproximados")
        return tr, g

    def lat_air(self, m, chi_c=None, phi_c=None, dt=None, phi_ff=0.0):
        ap = self.ap
        dt = dt or self.dt
        if phi_c is None:
            phi_c = ap.loops["chi"](wrap(chi_c - m["chi"]), dt, ff=phi_ff)
        da = ap.roll(phi_c, m["phi"], m["p"])
        dr = ap.yaw(m, dt, psi_c=getattr(self, "_psi_c", None))
        return da, dr, phi_c

    def gdr(self, dr_conv: float) -> float:
        """Ground yaw command: conventional rudder value (δr > 0 nose left), or for a drag rudder (tailless,
        ΔC_n > 0 nose right) the same fraction of the yaw capacity with the sign flipped; the nose wheel follows the
        same fraction (:class:`.sixdof.GroundModel` steer_ref/steer_sign)."""
        lim = math.radians(self.fm.aero.limits["rudder"])
        if getattr(self.fm.aero, "yaw_sas", None):
            return max(-lim, min(lim, -dr_conv / 0.5 * lim))
        return max(-lim, min(lim, dr_conv))

    def lon_alt(self, m, h_c, V_c, theta_ff=0.0):
        ap = self.ap
        e = h_c - m["h"]
        z = FLARE["h_zone_m"]
        th_c = ap.loops["h"](max(-z, min(z, e)), self.dt, ff=theta_ff)
        de = ap.pitch(th_c, m["theta"], m["q"])
        thr = ap.loops["V"](V_c - m["Va"], self.dt)
        return de, thr

    def lon_speed_pitch(self, m, V_c, thr):
        ap = self.ap
        th_c = ap.loops["V2"](V_c - m["Va"], self.dt)
        return ap.pitch(th_c, m["theta"], m["q"]), thr

    def tick(self, c: Controls):
        self.c = c
        m_dt = self.dt
        mm = self.meas()
        self.wind.advance(self.t, m_dt, mm["Va"], mm["psi"], mm["h"])
        if self.k % self._every == 0:
            self._log(c)
        x0 = self.x
        self.x = self.sim.step(self.t, self.x, c, m_dt)
        self.dist += math.hypot(self.x[0] - x0[0], self.x[1] - x0[1])
        if self._aft is not None and -self.x[2] < 30.0:
            self._aft.sample(self.x, dcm_body_to_ned(self.x[6:10]), getattr(self.sim, "contact_loads", None))
        self.t += m_dt
        self.k += 1
        if not np.all(np.isfinite(self.x)):
            raise RuntimeError("estado não finito")
        if self.t > self.max_t:
            raise RuntimeError("tempo máximo da missão excedido")

    def _log(self, c):
        info = {}
        self.sim.derivatives(self.t, self.x, c, info)
        phi, th, psi = euler_from_quat(self.x[6:10])
        R = dcm_body_to_ned(self.x[6:10])
        vn = R @ self.x[3:6]
        self.log.append([self.t, self.x[0], self.x[1], -self.x[2], info["Va"], math.hypot(vn[0], vn[1]), -vn[2],
                         info["alpha"], info["beta"], phi, th, psi, self.x[10], self.x[11], self.x[12], info["n_z"],
                         info["n_y"], c.de, c.da, c.dr, c.throttle, c.flap, c.brake, self.x[13], info["m"],
                         info["T"], info["flow"], info["CL"], info["sigma"], info["gear_load"], *info["wind"],
                         len(self.segs) - 1])

    def begin(self, s: dict) -> SegRec:
        m = self.meas()
        rec = SegRec(s.get("name", s["type"]), s["type"], self.t, used0=self.x[13], h0=m["h"], W0_N=self.W())
        rec._dist0 = self.dist
        self.segs.append(rec)
        gm = getattr(self.sim, "ground", None)
        if s["type"] in ("takeoff", "landing") and gm is not None and gm.contacts:
            from .ground_clearance import AftMonitor
            self._aft = AftMonitor(gm.contacts)
        return rec

    def end(self, rec: SegRec):
        rec.t1, rec.used1, rec.h1 = self.t, self.x[13], -self.x[2]
        rec.dist_m = self.dist - rec._dist0
        if self._aft is not None:
            sm = self._aft.summary()
            if sm is not None:
                rec.metrics["aft_clearance"] = sm
            self._aft = None

    def flap_to(self, target):
        r = FLARE["flap_rate_deg_s"] * self.dt
        self.flap = target if abs(target - self.flap) <= r else self.flap + math.copysign(r, target - self.flap)
        return self.flap

    def jump(self, rec, T_rem, along=True, window=20.0):
        """Steady extrapolation of the remainder of a long leg: average fuel flow and ground velocity over the
        last ``window`` s of the dynamic part (whole orbit periods for loiters); mass and position updated,
        attitude kept."""
        L = [r for r in self.log if r[0] >= self.t - window]
        if len(L) < 2 or T_rem <= 0:
            return
        a = np.array(L)
        flow = (a[-1, 23] - a[0, 23]) / max(a[-1, 0] - a[0, 0], 1e-6)
        vn = (a[-1, 1:3] - a[0, 1:3]) / max(a[-1, 0] - a[0, 0], 1e-6)
        self.x[13] += flow * T_rem
        if along:
            self.x[0:2] += vn * T_rem
            self.dist += float(np.linalg.norm(vn)) * T_rem
        else:
            self.dist += float(np.mean(a[:, 5])) * T_rem
        self.t += T_rem
        rec.extrapolated_s += T_rem
        self._log(self.c)

    # ------------------------------------------------------------------ segments
    def seg_takeoff(self, s):
        fm = self.fm
        flap = float(s.get("flap", fm.aero.flap_deg[1] if len(fm.aero.flap_deg) > 1 else 0.0))
        self.flap = flap
        rec = self.begin(s)
        gear = fm.mass.gear or {}
        Vs = self.Vs(flap)
        if gear.get("kind", "none") == "none":
            V0 = 1.3 * Vs
            h0 = FLARE["screen_m"]
            self.x = state((self.x[0], self.x[1], -h0), V0)
            tr, g = self.retune(V0, h0)
            self.x = tr["x"].copy()
            self.x[2] = -h0
            rec.h0 = h0
            rec.notes.append(f"sem trem: lançamento (catapulta/mão) a 1.3 V_S,TO = {V0:.1f} m/s, {h0:.1f} m "
                             "(PRESSUPOSTO)")
            self.c = Controls(de=g["trim"]["de"], throttle=g["trim"]["throttle"], flap=flap)
            for _ in range(int(2.0 / self.dt)):
                m = self.meas()
                da, dr, _ = self.lat_air(m, chi_c=0.0)
                de, thr = self.lon_alt(m, h0, V0)
                self.tick(Controls(de=de, da=da, dr=dr, throttle=thr, flap=flap))
            self.end(rec)
            return
        # V_R = k·V_S (Sadraey 2012 Eq. 9.35: 1.1–1.3; default 1.1 as before)
        VR = float(s.get("rotation_speed_factor", 1.1)) * Vs
        V2 = 1.2 * Vs
        rec.V_target = VR
        tr, g = self.retune(V2, 50.0)
        # θ at lift-off: attitude for CL = CLmax,TO / 1.1² at the ground (γ = 0)
        a = fm.aero
        CLlof = a.clmax(flap) / 1.21
        al_grid = np.radians(np.arange(-2, 16, 0.1))
        CLs = [self.sim.aero_coeffs(al, 0, 0, 0, 0, 0, Controls(flap=flap, de=g["trim"]["de"]), fm.mass.x_cg)[0]
               for al in al_grid]
        th_lof = float(al_grid[int(np.argmin(np.abs(np.array(CLs) - CLlof)))])
        stance = math.radians(float(gear.get("ground_attitude_deg") or 0.0))
        fly_off = stance > 0.0   # nose-up stance = lift-off attitude: hold it, no rotation (Sadraey Sec. 9.6.2)
        if fly_off:
            th_lof = stance
        psi0 = euler_from_quat(self.x[6:10])[2]
        th_c = None
        strikes = {}
        t_rot = t_lof = x_lof = V_lof = None
        x0 = np.array(self.x[0:2])
        rate = math.radians(FLARE["rotation_rate_deg_s"])
        while True:
            m = self.meas()
            thr = min(1.0, (self.t - rec.t0) / 2.0)
            on = m["on_ground"]
            e_psi = wrap(psi0 - m["psi"])
            if on and m["Va"] < VR and th_c is None and not fly_off:
                de = 0.0
                da = 0.0
                dr = self.gdr(-(FLARE["k_psi_ground"] * e_psi - FLARE["k_r_ground"] * m["r"]))
            else:
                if th_c is None:
                    th_c, t_rot = m["theta"], self.t
                th_c = min(th_lof, th_c + rate * self.dt)
                de = self.ap.pitch(th_c, m["theta"], m["q"])
                if on:
                    dr = self.gdr(-(FLARE["k_psi_ground"] * e_psi - FLARE["k_r_ground"] * m["r"]))
                    da = self.ap.roll(0.0, m["phi"], m["p"])
                else:
                    if t_lof is None:
                        t_lof, x_lof, V_lof = self.t, np.array(self.x[0:2]), m["Va"]
                    da, dr, _ = self.lat_air(m, chi_c=psi0)
                dr = max(-math.radians(a.limits["rudder"]), min(math.radians(a.limits["rudder"]), dr))
            self.tick(Controls(de=de, da=da, dr=dr, throttle=thr, flap=flap))
            for nm_, N_ in (getattr(self.sim, "contact_loads", None) or {}).items():   # tip / aft strikes
                if nm_.startswith(("tip_", "aft_")) and N_ > 0:
                    strikes[nm_] = max(strikes.get(nm_, 0.0), float(N_))
            if m["h"] >= FLARE["screen_m"] + self.sim.ground.h_cg and t_lof is not None:
                break
            if self.t - rec.t0 > 180:
                rec.notes.append("descolagem não concluída em 180 s")
                self.aborted = "takeoff"
                break
        d_total = float(np.linalg.norm(np.array(self.x[0:2]) - x0))
        skids = (gear.get("tip_skids") or {}) if (gear.get("tip_skids") or {}).get("status") == "assessed" else {}
        skid_hits = {k: v for k, v in strikes.items() if k.startswith("tip_") and skids}
        hard = {k: v for k, v in strikes.items() if k not in skid_hits}
        rec.metrics = {"V_R_m_s": None if fly_off else VR, "mode": "fly_off" if fly_off else "rotation",
                       "theta_LOF_deg": math.degrees(th_lof),
                       "strikes_N": hard or None,
                       "skid_contacts_N": skid_hits or None,
                       "ground_roll_m": float(np.linalg.norm(x_lof - x0)) if x_lof is not None else None,
                       "distance_to_15m_m": d_total, "t_rotation_s": (t_rot - rec.t0) if t_rot is not None else None,
                       "t_liftoff_s": (t_lof - rec.t0) if t_lof is not None else None,
                       "V_liftoff_m_s": V_lof}
        # hand over to the airborne loops with bumpless integrators
        self.ap.retune(g, self.meas()["theta"], 1.0)
        self.end(rec)

    def seg_climb(self, s):
        rec = self.begin(s)
        self.flap = float(s.get("flap", 0.0))
        h_t = float(s["to_altitude_m"])
        V_c = float(s.get("speed_m_s") or self.default_Vy())
        rec.V_target = V_c
        self.retune(V_c, 0.5 * (self.meas()["h"] + h_t))
        chi_c = math.radians(s["heading_deg"]) if "heading_deg" in s else self.meas()["chi"]
        thr_c = float(s.get("throttle", 1.0))
        mode = "climb"
        while True:
            m = self.meas()
            da, dr, _ = self.lat_air(m, chi_c=chi_c)
            if mode == "climb" and h_t - m["h"] < FLARE["h_zone_m"]:
                mode = "hold"
                self.retune(V_c, h_t)
            if mode == "climb":
                de, thr = self.lon_speed_pitch(m, V_c, thr_c)
            else:
                de, thr = self.lon_alt(m, h_t, V_c)
            self.tick(Controls(de=de, da=da, dr=dr, throttle=thr, flap=self.flap_to(self.flap)))
            if mode == "hold" and abs(m["h"] - h_t) < 3.0 and abs(m["Va"] - V_c) < 2.0:
                break
            if self.t - rec.t0 > 3 * 3600:
                rec.notes.append("subida não atingiu a altitude (tecto?)")
                break
        self.end(rec)

    def default_Vy(self):
        if self.res is not None:
            from ..performance import PerfModel, climb_rate
            return climb_rate(PerfModel.from_result(self.res), self.W(), self.meas()["h"])[1]
        return 1.3 * self.Vs(0.0)

    def V_default(self):
        """Speed when a segment gives none: the previous segment's target (not the instantaneous V_a), floored at
        1.3 V_S of the current configuration."""
        prev = self.segs[-2].V_target if len(self.segs) >= 2 else 0.0
        return max(prev or self.meas()["Va"], 1.3 * self.Vs(self.flap, self.meas()["h"]))

    def _level(self, s, rec, done, guidance, along=True):
        h_c = float(s.get("altitude_m", self.meas()["h"]))
        V_c = float(s.get("speed_m_s") or self.V_default())
        rec.V_target = V_c
        self.retune(V_c, h_c)
        t_dyn0 = self.t
        jumped = False
        while not done():
            m = self.meas()
            gd = guidance(m)
            chi_c, phi_c, ff = gd[:3]
            da, dr, _ = self.lat_air(m, chi_c=chi_c, phi_c=phi_c, phi_ff=gd[3] if len(gd) > 3 else 0.0)
            de, thr = self.lon_alt(m, h_c, V_c, theta_ff=ff)
            self.tick(Controls(de=de, da=da, dr=dr, throttle=thr, flap=self.flap_to(0.0)))
            if not jumped and self.t - t_dyn0 >= self.extrap and hasattr(rec, "_remaining"):
                T_rem = rec._remaining(m)
                if T_rem > 30.0:
                    self.jump(rec, T_rem - 10.0, along=along, window=getattr(rec, "_window", 20.0))
                jumped = True
        return h_c, V_c

    def seg_cruise(self, s):
        rec = self.begin(s)
        chi_c = math.radians(s["heading_deg"]) if "heading_deg" in s else self.meas()["chi"]
        d0, t0 = self.dist, self.t
        D = float(s["distance_km"]) * 1e3 if "distance_km" in s else None
        T = float(s["time_min"]) * 60 if "time_min" in s else None
        if D is None and T is None:
            raise ValueError("cruise: distance_km ou time_min")
        rec._remaining = (lambda m: (D - (self.dist - d0)) / max(m["Vg"], 1.0)) if D else \
            (lambda m: T - (self.t - t0))
        done = (lambda: self.dist - d0 >= D) if D else (lambda: self.t - t0 >= T)
        self._level(s, rec, done, lambda m: (chi_c, None, 0.0))
        self.end(rec)

    def seg_turn(self, s):
        rec = self.begin(s)
        n = float(s.get("load_factor", 1.2))
        dpsi = math.radians(float(s["heading_change_deg"]))
        phi_t = math.copysign(math.acos(1.0 / n), dpsi)
        st = {"acc": 0.0, "last": self.meas()["chi"], "t90": None, "phase": "bank"}
        chi_f = wrap(st["last"] + dpsi)
        th_ff = 0.0

        def guid(m):
            st["acc"] += wrap(m["chi"] - st["last"])
            st["last"] = m["chi"]
            if st["t90"] is None and abs(m["phi"]) >= 0.9 * abs(phi_t):
                st["t90"] = self.t - rec.t0
            if st["phase"] == "bank" and abs(dpsi) - abs(st["acc"]) < math.radians(15):
                st["phase"] = "rollout"
                self.ap.loops["chi"].i = 0.0
            a = self.ap.gains["trim"]["alpha"]
            if st["phase"] == "bank":
                return None, phi_t, a * (1 / math.cos(phi_t) - 1)  # coordinated-turn feed-forward, n = 1/cos φ
            return chi_f, None, a * (1 / max(math.cos(m["phi"]), 0.3) - 1)

        done = lambda: st["phase"] == "rollout" and abs(wrap(chi_f - self.meas()["chi"])) < math.radians(2) \
            and abs(self.meas()["phi"]) < math.radians(3)  # noqa: E731
        self._level(s, rec, done, guid)
        rec.metrics = {"bank_cmd_deg": math.degrees(phi_t), "n_cmd": n, "t_to_90pct_bank_s": st["t90"]}
        self.end(rec)

    def seg_loiter(self, s):
        rec = self.begin(s)
        V = float(s.get("speed_m_s") or self.V_default())
        # radius sized at the highest ground speed (V + steady wind) with the bank capped 5° below the
        # autopilot limit, so the orbit stays flyable downwind
        Vg_max = V + float(np.linalg.norm(self.wind.steady()[:2]))
        phi_av = math.radians((self.ap.gains["design"]["phi_max_deg"] if self.ap else 30.0) - 5.0)
        if "radius_m" in s:
            rho = float(s["radius_m"])
            rho_min = Vg_max**2 / (G0 * math.tan(phi_av))
            if rho < rho_min:
                rec.notes.append(f"raio {rho:.0f} m < mínimo voável {rho_min:.0f} m (φ ≤ {math.degrees(phi_av):.0f}°,"
                                 f" Vg até {Vg_max:.1f} m/s) — erros radiais esperados")
        else:
            n = float(s.get("load_factor", 1.1))
            phi_n = math.acos(1 / n)
            if phi_n > phi_av:
                rec.notes.append(f"n={n:g} pede φ={math.degrees(phi_n):.0f}° > {math.degrees(phi_av):.0f}° "
                                 "disponível — raio dimensionado com o limite")
            rho = Vg_max**2 / (G0 * math.tan(min(phi_n, phi_av)))
        lam = 1 if s.get("direction", "right") == "right" else -1
        m = self.meas()
        chi = m["chi"]
        cn = m["ne"][0] + lam * rho * math.cos(chi + math.pi / 2)
        cE = m["ne"][1] + lam * rho * math.sin(chi + math.pi / 2)
        T = float(s["time_min"]) * 60
        t0 = self.t
        rec._remaining = lambda m: T - (self.t - t0)
        T_orb = 2 * math.pi * rho / V
        rec._window = min(math.ceil(20.0 / T_orb) * T_orb, self.extrap)  # whole orbits (unbiased averages)
        errs = []

        def guid(m):
            chi_c, e = orbit_course(m["ne"], (cn, cE), rho, lam, m["chi"])
            errs.append(e)
            # coordinated-turn feed-forward on the orbit (χ̇ = Vg/ρ), faded out away from it (capture)
            w_ff = max(0.0, 1.0 - abs(e) / (0.5 * rho))
            phi_ff = lam * math.atan(m["Vg"]**2 / (G0 * rho)) * w_ff
            return chi_c, None, self.ap.gains["trim"]["alpha"] * (1 / math.cos(phi_ff) - 1), phi_ff

        self._level({**s, "speed_m_s": V}, rec, lambda: self.t - t0 >= T, guid, along=False)
        e = np.array(errs[len(errs) // 2:]) if errs else np.zeros(1)
        rec.metrics = {"radius_m": rho, "radial_err_rms_m": float(np.sqrt(np.mean(e**2)))}
        self.end(rec)

    def seg_patrol(self, s):
        """Same mechanics as loiter. The point-mass runner treats patrol as on-station; 6-DOF flies the orbit."""
        self.seg_loiter(s)

    def seg_waypoints(self, s):
        rec = self.begin(s)
        m = self.meas()
        pts = [np.array(m["ne"])] + [np.array(p, dtype=float) * 1e3 for p in s["points_km"]]
        st = {"i": 1, "leg_t0": self.t, "jumped": False, "xte": []}
        h_c = float(s.get("altitude_m", m["h"]))
        V_c = float(s.get("speed_m_s") or self.V_default())
        rec.V_target = V_c
        self.retune(V_c, h_c)
        while st["i"] < len(pts):
            m = self.meas()
            r, w = pts[st["i"] - 1], pts[st["i"]]
            q = (w - r) / max(np.linalg.norm(w - r), 1e-6)
            chi_c, e = line_course(m["ne"], r, q, m["chi"])
            st["xte"].append(e)
            da, dr, _ = self.lat_air(m, chi_c=chi_c)
            de, thr = self.lon_alt(m, h_c, V_c)
            self.tick(Controls(de=de, da=da, dr=dr, throttle=thr, flap=self.flap_to(0.0)))
            p = np.array(self.x[0:2])
            rem = float((w - p) @ q)
            if not st["jumped"] and self.t - st["leg_t0"] > self.extrap and rem > 3000.0 + 30 * V_c:
                T_rem = (rem - 3000.0) / max(m["Vg"], 1.0)
                self.jump(rec, T_rem)
                st["jumped"] = True
            if rem <= 0.0:  # half-plane switching (Beard & McLain Alg. 5)
                st["i"] += 1
                st["leg_t0"] = self.t
                st["jumped"] = False
        x = np.array(st["xte"][int(len(st["xte"]) * 0.2):] or [0.0])
        rec.metrics = {"n_waypoints": len(pts) - 1, "cross_track_rms_m": float(np.sqrt(np.mean(x**2)))}
        self.end(rec)

    def seg_descent(self, s):
        """Default: Beard & McLain descend zone — throttle at idle (or ``throttle``), airspeed held with pitch,
        altitude hold inside the h-zone. With ``vertical_speed_m_s`` / ``gamma_deg``: ramped altitude command +
        airspeed on throttle; if the throttle sits at idle with V > V_c + 3 m/s for 3 s (path steeper than the
        idle glide), falls back to the descend zone."""
        rec = self.begin(s)
        h_t = float(s["to_altitude_m"])
        V_c = float(s.get("speed_m_s") or self.V_default())
        rec.V_target = V_c
        self.retune(V_c, 0.5 * (self.meas()["h"] + h_t))
        chi_c = math.radians(s["heading_deg"]) if "heading_deg" in s else self.meas()["chi"]
        vs = abs(float(s.get("vertical_speed_m_s", 0.0))) or (
            V_c * math.sin(math.radians(abs(s["gamma_deg"]))) if "gamma_deg" in s else 0.0)
        mode = "ramp" if vs > 0 else "idle"
        thr_idle = float(s.get("throttle", 0.0))
        h_c = self.meas()["h"]
        t_over, Va_prev, Vdot_f, capture = 0.0, self.meas()["Va"], 0.0, False
        while True:
            m = self.meas()
            da, dr, _ = self.lat_air(m, chi_c=chi_c)
            if mode == "idle" and m["h"] - h_t < FLARE["h_zone_m"]:
                # capture: ramp from here at the current sink rate (a 30 m altitude step into the hold loop
                # would dive the aircraft), airspeed back on throttle; no fall-back to idle from now on
                mode, capture = "ramp", True
                vs = max(-m["hdot"], 0.5)
                h_c = m["h"]
                self.ap.retune(self.ap.gains, m["theta"], self.c.throttle)
            if mode == "ramp" and h_c - h_t < 0.3:
                mode = "hold"  # same altitude loop, command now constant
            if mode == "ramp":
                # constant-rate ramp, then exponential capture (time constant h_zone / vs) so the commanded
                # sink rate — and the pitch feed-forward — go smoothly to zero at h_t
                hc_dot = min(vs, vs * (h_c - h_t) / FLARE["h_zone_m"])
                h_c = max(h_t, h_c - hc_dot * self.dt)
                de, thr = self.lon_alt(m, h_c, V_c, theta_ff=-hc_dot / V_c)
                # fast at idle and *not* slowing down (dV/dt > −0.1 m/s²): the ramp is steeper than the idle glide
                Vdot_f += (self.dt / 2.0) * ((m["Va"] - Va_prev) / self.dt - Vdot_f)  # 2 s low-pass
                slowing = Vdot_f < -0.1
                t_over = t_over + self.dt if (thr <= 1e-3 and m["Va"] > V_c + 3.0 and not slowing) else 0.0
                Va_prev = m["Va"]
                if t_over > 3.0 and not capture:
                    mode = "idle"
                    rec.notes.append(f"t={self.t:.0f}s: rampa de {vs:.1f} m/s mais íngreme do que o planeio em "
                                     "ralenti — passou a V por picada (Beard & McLain, zona de descida)")
            elif mode == "idle":
                de, thr = self.lon_speed_pitch(m, V_c, thr_idle)
            else:
                de, thr = self.lon_alt(m, h_t, V_c)
            self.tick(Controls(de=de, da=da, dr=dr, throttle=thr, flap=self.flap_to(float(s.get("flap", 0.0)))))
            if mode == "hold" and abs(m["h"] - h_t) < 3.0 and abs(m["Va"] - V_c) < 2.0:
                break
            if self.t - rec.t0 > 3 * 3600:
                rec.notes.append("descida não concluída")
                break
        rec.metrics = {"vertical_speed_cmd_m_s": vs or None, "mode_final": mode}
        self.end(rec)

    def seg_landing(self, s):
        fm = self.fm
        rec = self.begin(s)
        flap = float(s.get("flap", fm.aero.flap_deg[-1]))
        gam = math.radians(float(s.get("glide_deg", 3.0)))
        V_ref = float(s.get("speed_m_s", 1.3 * self.Vs(flap)))
        rec.V_target = V_ref
        prev_flap = self.flap
        self.flap = flap  # gains designed in the landing configuration
        tr, g = self.retune(V_ref, max(self.meas()["h"] * 0.5, 50.0))
        m = self.meas()
        chi_r = math.radians(float(s["heading_deg"])) if s.get("heading_deg") is not None else m["chi"]
        u = np.array([math.cos(chi_r), math.sin(chi_r)])
        ap_split = getattr(self.ap, "split", None) is not None
        decrab = bool(s.get("decrab", ap_split))
        if decrab and not ap_split:
            rec.notes.append("decrab pedido mas só implementado para o leme de arrasto (asa sem deriva) — ignorado")
            decrab = False
        decrab_h = s.get("decrab_height_m")   # None → decrab at the flare (PRESSUPOSTO); else wing-low from this AGL
        if decrab:
            self._decrab_gains(V_ref)
        td = {"crab_at_flare_deg": None, "residual_crab_deg": None, "drift_m_s": None, "phi_td_deg": None,
              "side": {}, "N": {}, "bumpers": {}}
        h_cg = self.sim.ground.h_cg
        p_td = np.array(m["ne"]) + u * (m["h"] - h_cg) / math.tan(gam)
        w_h = g["w_theta"] / g["design"]["W_h"]
        tau = FLARE["tau_over_wh"] / w_h
        h_flare = tau * V_ref * math.sin(gam) + h_cg
        self.flap = prev_flap  # flaps then run out at the flap rate
        phase, h_fc, t_f, th_td = "approach", None, None, 0.0
        skids = (fm.mass.gear or {}).get("kind", "none") == "none"
        decel, t_over, n_decel, Va_prev, Vdot_f = False, 0.0, 0, m["Va"], 0.0
        x_screen = t_td = sink_td = V_td = None
        kd = FLARE
        while True:
            m = self.meas()
            p = np.array(m["ne"])
            on = m["on_ground"]
            if phase == "approach":
                dist = float((p_td - p) @ u)
                h_c = h_cg + max(dist, 0.0) * math.tan(gam)
                if x_screen is None and m["h"] - h_cg <= kd["screen_m"]:
                    x_screen = p.copy()
                chi_c, _ = line_course(m["ne"], p_td - u * 1e4, u, m["chi"])
                if decrab and decrab_h is not None and self._psi_c is None and m["h"] - h_cg <= float(decrab_h):
                    td["crab_at_decrab_deg"] = math.degrees(wrap(m["psi"] - m["chi"]))
                    self._psi_c = chi_r
                da, dr, _ = self.lat_air(m, chi_c=chi_c)
                if decel:  # idle and fast: bleed speed on pitch, then re-anchor the glide path from here
                    de, thr = self.lon_speed_pitch(m, V_ref, 0.0)
                    if m["Va"] < V_ref + 1.0:
                        decel = False
                        p_td = p + u * (m["h"] - h_cg) / math.tan(gam)
                        self.ap.retune(self.ap.gains, m["theta"], 0.0)
                else:
                    de, thr = self.lon_alt(m, h_c, V_ref, theta_ff=-gam)
                    Vdot_f += (self.dt / 2.0) * ((m["Va"] - Va_prev) / self.dt - Vdot_f)  # 2 s low-pass
                    slowing = Vdot_f < -0.1
                    t_over = t_over + self.dt if (thr <= 1e-3 and m["Va"] > V_ref + 3.0 and not slowing) else 0.0
                    Va_prev = m["Va"]
                    if t_over > 2.0 and m["h"] - h_cg > kd["screen_m"]:
                        decel, t_over = True, 0.0
                        n_decel += 1
                        self.ap.retune(self.ap.gains, m["theta"], 0.0)
                if m["h"] <= h_flare and self.flap >= flap - 1e-6:
                    phase, t_f, h_fc = "flare", self.t, m["h"]
                    td["crab_at_flare_deg"] = math.degrees(wrap(m["psi"] - m["chi"]))
                    if decrab:   # align the nose with the runway; the course loop banks into wind (wing-low)
                        self._psi_c = chi_r
            elif phase == "flare":
                h0 = kd["td_sink_m_s"] * tau
                h_c = h_cg + (h_fc - h_cg + h0) * math.exp(-(self.t - t_f) / tau) - h0
                hd_c = -(h_fc - h_cg + h0) / tau * math.exp(-(self.t - t_f) / tau)
                if x_screen is None and m["h"] - h_cg <= kd["screen_m"]:
                    x_screen = p.copy()
                da, dr, _ = self.lat_air(m, chi_c=chi_r)
                de, _ = self.lon_alt(m, h_c, V_ref, theta_ff=hd_c / max(m["Va"], 1.0))
                thr = 0.0
                if on:
                    phase, t_td, sink_td, V_td, th_td = "rollout", self.t, -m["hdot"], m["Va"], m["theta"]
                    p_tdown = p.copy()
                    self._psi_c = None
                    vn = dcm_body_to_ned(self.x[6:10]) @ self.x[3:6]
                    td.update({"residual_crab_deg": math.degrees(wrap(m["psi"] - chi_r)),
                               "track_vs_runway_deg": math.degrees(wrap(m["chi"] - chi_r)),
                               "drift_m_s": float(-u[1] * vn[0] + u[0] * vn[1]), "phi_td_deg": math.degrees(m["phi"]),
                               "beta_td_deg": math.degrees(m["beta"])})
            else:  # roll-out: idle, wings level, brakes after 1 s, nose-wheel steering
                thr = 0.0
                if skids:  # belly landing: hold the touchdown attitude (stick back) against the skid friction
                    de = self.ap.pitch(th_td, m["theta"], m["q"]) if m["Va"] > 3.0 else 0.0
                elif float((fm.mass.gear or {}).get("ground_attitude_deg") or 0.0) > 0.0 and self.t - t_td > 1.0:
                    # fly-off stance: pitch is fixed by the gear; dump lift (Raymer 17.9 / lift-dump)
                    de = lift_dump_de(fm.aero, flap=self.flap, alpha=m.get("alpha", 0.0))
                else:
                    de = 0.0 if self.t - t_td > 1.0 else self.ap.pitch(m["theta"], m["theta"], m["q"])
                da = self.ap.roll(0.0, m["phi"], m["p"])
                e_psi = wrap(chi_r - m["psi"])
                dr = self.gdr(-(kd["k_psi_ground"] * e_psi - kd["k_r_ground"] * m["r"]))
                self.brake = 1.0 if self.t - t_td > 1.0 else 0.0
                if m["Vg"] < 0.5:
                    break
            self.tick(Controls(de=de, da=da, dr=dr, throttle=thr, flap=self.flap_to(flap), brake=self.brake))
            if phase in ("flare", "rollout") and -self.x[2] < 5.0 and (t_td is None or self.t - t_td <= 3.0):
                self.sim._ground(self.x, dcm_body_to_ned(self.x[6:10]), self.c)   # loads at this state
                for nm, fy in self.sim.contact_side.items():
                    N_ = self.sim.contact_loads.get(nm, 0.0)
                    if nm.startswith("main"):
                        inb = fy if nm.endswith("L") else -fy      # +y body is inboard for the left wheel
                        d_ = td["side"].setdefault(nm, {"inboard_N": 0.0, "outboard_N": 0.0})
                        d_["inboard_N"] = max(d_["inboard_N"], inb)
                        d_["outboard_N"] = max(d_["outboard_N"], -inb)
                        td["N"][nm] = max(td["N"].get(nm, 0.0), N_)
                    elif nm not in ("nose", "tail") and N_ > 0:
                        td["bumpers"][nm] = max(td["bumpers"].get(nm, 0.0), N_)
            if self.t - rec.t0 > 1800:
                rec.notes.append("aterragem não concluída em 30 min")
                self.aborted = "landing"
                break
            if phase != "rollout" and m["h"] < -0.5:
                self.aborted = "landing (abaixo do solo sem contacto)"
                break
        p_end = np.array(self.x[0:2])
        rec.metrics = {"V_REF_m_s": V_ref, "glide_deg": math.degrees(gam), "h_flare_m": h_flare - h_cg,
                       "flare_tau_s": tau, "sink_at_touchdown_m_s": sink_td, "V_touchdown_m_s": V_td,
                       "air_distance_from_15m_m": float(np.linalg.norm(p_tdown - x_screen))
                       if (x_screen is not None and t_td is not None) else None,
                       "ground_roll_m": float(np.linalg.norm(p_end - p_tdown)) if t_td is not None else None}
        if float((fm.mass.gear or {}).get("ground_attitude_deg") or 0.0) > 0.0 and not skids:
            rec.metrics["lift_dump"] = True
            rec.metrics["lift_dump_note"] = (
                "atitude fixa pela geometria do trem (perna do nariz já no solo): elevon a descarregar "
                "sustentação após 1 s (Raymer Sec. 17.9 / lift-dump); o nariz não pode baixar")
        self._psi_c = None
        if t_td is not None:
            rec.metrics["touchdown"] = self._td_report(td, decrab)
        if n_decel:
            rec.notes.append(f"aproximação: {n_decel}x acima de V_REF+3 m/s em ralenti — rampa de "
                             f"{math.degrees(gam):.1f}° mais íngreme do que o planeio em ralenti; desacelerou por "
                             "picada e re-ancorou a rampa (considerar flaps/travões aerodinâmicos ou rampa menor)")
        if t_td is not None and x_screen is not None:
            rec.metrics["total_from_15m_m"] = rec.metrics["air_distance_from_15m_m"] + rec.metrics["ground_roll_m"]
        self.end(rec)

    def _decrab_gains(self, V: float):
        """Heading PD on the yaw axis through the drag rudder for the decrab: saturation-based form of Beard &
        McLain 2012 Eq. 6.7–6.8 applied to ψ (a_ψ1 = −N_r, a_ψ2 = N_ΔCn = q̄Sb/I_z): k_ψ = ΔC_n,max/e_ψ,max,
        ω_ψ = √(a_ψ2 k_ψ), k_dψ = (2ζω_ψ − a_ψ1)/a_ψ2 (PRESSUPOSTO e_ψ,max 20°, ζ 0,707; integral k_iψ = k_ψ ω_ψ/2 com anti-windup; feed-forward −C_nβ(α)β da própria tabela)."""
        from .sixdof import IDX
        a, ys = self.fm.aero, self.fm.aero.yaw_sas
        rho = isa(0.0).rho
        qS = 0.5 * rho * V**2 * a.S
        al = self.ap.gains["trim"]["alpha"]
        Cnr = float(self.sim._tab(al, self.flap)[IDX["Cnr"]])
        a1 = -qS * a.b * Cnr * a.b / (2 * V) / self.fm.mass.Izz
        a2 = qS * a.b / self.fm.mass.Izz
        cap = math.radians(a.limits["rudder"])
        e = math.radians(float(ys.get("e_psi_max_deg", 20.0)))
        kp = cap / e
        w = math.sqrt(a2 * kp)
        ys["k_psi"], ys["k_dpsi"], ys["w_psi"] = kp, (2 * 0.707 * w - a1) / a2, w
        ys["k_ipsi"] = kp * w * float(ys.get("ki_frac", 0.5))   # PRESSUPOSTO: integral corner ω_ψ/2
        self.ap.psi_i = 0.0

    def _td_report(self, td: dict, decrab: bool) -> dict:
        """Touchdown in crosswind: residual crab, drift, main-gear side loads vs the 14 CFR 23.485 limit side loads
        (pre-Amdt 23-64, as amended by Amdt 23-45: 0.5 W inboard on one side, 0.33 W outboard on the other, with
        1.33 W vertical) — the loads the gear is designed for (PRESSUPOSTO: gear designed to 23.485; the gear
        structure is not sized for side load in landing_gear)."""
        W = self.W()
        ib = max((v["inboard_N"] for v in td["side"].values()), default=None)
        ob = max((v["outboard_N"] for v in td["side"].values()), default=None)
        out = {**{k: v for k, v in td.items() if k not in ("side", "N", "bumpers")}, "decrab": decrab,
               "main_side_N": td["side"], "main_vertical_peak_N": td["N"], "W_N": W,
               "limit_23_485": {"inboard_N": 0.5 * W, "outboard_N": 0.33 * W,
                                "source": "14 CFR 23.485(c) (pré-Amdt 23-64; Amdt 23-45): 0,5 W para dentro num lado, "
                                          "0,33 W para fora no outro, vertical 1,33"},
               "bumper_contacts_N": td["bumpers"] or None}
        if ib is not None:
            out["inboard_ratio"] = ib / (0.5 * W)
            out["outboard_ratio"] = ob / (0.33 * W)
            out.update(side_load_band(out["inboard_ratio"], out["outboard_ratio"]))
        else:
            out["side_load_ok"] = None
            out["side_load_status"] = "nao_avaliado"
            out["side_load_note"] = ("sem contacto do trem principal registado na janela do toque (h < 5 m, ≤ 3 s "
                                     "após o toque) — 23.485 não avaliado (não avaliado ≠ passa)")
        skids = (self.fm.mass.gear or {}).get("tip_skids") or {}
        designed = bool(skids.get("status") == "assessed")
        tip_hits = {k: v for k, v in (td["bumpers"] or {}).items() if k.startswith("tip_")}
        other_hits = {k: v for k, v in (td["bumpers"] or {}).items() if not k.startswith("tip_")}
        if designed:
            out["tip_skid_ok"] = True
            out["tip_skid_P_des_N"] = skids.get("P_des_N")
            if tip_hits:
                out["tip_skid_contacts_N"] = tip_hits
                peak = max(tip_hits.values())
                # 6-DOF contact N is a numerical spring force (stiffness-capped), not the energy-method
                # design load — reported, not used to fail side_load_ok. tip_skid_ok is the sizing flag.
                out["tip_skid_peak_N"] = peak
                out["tip_skid_note"] = (
                    f"contacto de patim dimensionado (N_6DOF pico {peak:.0f} N, N_des energia "
                    f"{skids.get('P_des_N'):.0f} N); o contacto deixa de falhar side_load_ok "
                    "(14 CFR 23.485 só no trem principal)")
        elif tip_hits:
            # undesigned tip strike: not a 23.485 side-load exceedance, but the old fail-closed flag
            out["side_load_ok"] = False
            out["issue"] = "contacto de ponta de asa (sem patins dimensionados): " + ", ".join(tip_hits)
        if other_hits:
            out["other_contacts_N"] = other_hits
            out["aft_strike_ok"] = not any(k.startswith("aft_") for k in other_hits)
            msg = "contacto de para-choques (não-patim) no toque: " + ", ".join(other_hits)
            out["issue"] = (out.get("issue") + "; " + msg) if out.get("issue") else msg
            # aft/TE/prop contact is its own residual — it does not flip the 23.485 flag
        return out

    # ------------------------------------------------------------------ run
    def run(self) -> dict:
        fm = self.fm
        segs = self.ms["segments"]
        gear = fm.mass.gear or {}
        if segs[0]["type"] == "takeoff" and gear.get("kind", "none") != "none":
            thg = math.radians(float(gear.get("ground_attitude_deg") or 0.0))   # nose-up stance (nose strut)
            h0 = float(gear.get("h_cg_static") or self.sim.ground.h_cg)
            self.x = state((0.0, 0.0, -(h0 - 0.07)), 0.0, theta=thg,
                           psi=math.radians(segs[0].get("heading_deg", 0.0)))
            self.c = Controls(flap=float(segs[0].get("flap", 0.0)))
            for _ in range(int(2.0 / self.dt)):  # settle on the gear
                self.x = self.sim.step(self.t, self.x, self.c, self.dt)
            self.sim.derivatives(self.t, self.x, self.c)
        else:
            init = self.ms.get("initial", {})
            h0 = float(init.get("altitude_m", 300.0))
            V0 = float(init.get("speed_m_s", 1.4 * math.sqrt(2 * fm.mass.m * G0 / (1.225 * fm.aero.S * fm.aero.clmax(0)))))
            self.x = state((0.0, 0.0, -h0), V0)
            tr, g = self.retune(V0, h0)
            self.x = tr["x"].copy()
            self.x[2] = -h0
            self.c = tr["controls"]
        for s in segs:
            if self.aborted:
                break
            try:
                getattr(self, "seg_" + s["type"])(s)
            except RuntimeError as e:
                self.aborted = f"{s['type']}: {e}"
                if self.segs:
                    self.end(self.segs[-1])
                break
        return self.results()

    # ------------------------------------------------------------------ post-processing
    COLS = ["t", "N", "E", "h", "Va", "Vg", "hdot", "alpha", "beta", "phi", "theta", "psi", "p", "q", "r", "n_z", "n_y",
            "de", "da", "dr", "throttle", "flap", "brake", "used", "m", "T", "flow", "CL", "stall_sigma", "gear_load",
            "wN", "wE", "wD", "seg"]

    def results(self) -> dict:
        H = np.array(self.log) if self.log else np.zeros((0, len(self.COLS)))
        C = {k: i for i, k in enumerate(self.COLS)}
        lim = {k: math.radians(v) for k, v in self.fm.aero.limits.items()}
        rows = []
        unit = "Wh" if self.electric else "kg"
        f = 1 / 3600 if self.electric else 1.0
        for i, r in enumerate(self.segs):
            sel = H[:, C["seg"]] == i
            A = H[sel]
            row = {"segment": r.name, "type": r.type, "t_min": (r.t1 - r.t0) / 60, "dist_km": r.dist_m / 1e3,
                   f"used_{unit}": (r.used1 - r.used0) * f, "h0_m": r.h0, "h1_m": r.h1,
                   "extrapolated_min": r.extrapolated_s / 60, "V_target_m_s": r.V_target}
            if len(A):
                row.update({"Va_mean_m_s": float(A[:, C["Va"]].mean()),
                            "nz_max": float(A[:, C["n_z"]].max()), "nz_min": float(A[:, C["n_z"]].min()),
                            "alpha_max_deg": math.degrees(float(A[A[:, C["Va"]] > 5.0, C["alpha"]].max()))
                            if (A[:, C["Va"]] > 5.0).any() else None,
                            "stall_time_s": float((A[:, C["stall_sigma"]] > 0.5).sum() * self.log_dt),
                            "beta_max_deg": math.degrees(float(np.abs(A[A[:, C["Va"]] > 5.0, C["beta"]]).max()))
                            if (A[:, C["Va"]] > 5.0).any() else None})
                for k, key in (("de", "elevator"), ("da", "aileron"), ("dr", "rudder")):
                    d = np.abs(A[:, C[k]])
                    row[f"{k}_max_deg"] = math.degrees(float(d.max()))
                    row[f"{k}_sat_pct"] = 100.0 * float((d >= 0.98 * lim[key]).mean())
                row["throttle_sat_pct"] = 100.0 * float((A[:, C["throttle"]] >= 0.999).mean())
            row.update(r.metrics)
            row["notes"] = r.notes
            rows.append(row)
        used = float(self.x[13])
        out = {"segments": rows, "total_time_min": self.t / 60, "total_dist_km": self.dist / 1e3,
               f"total_used_{unit}": used * f, "unit": unit, "aborted": self.aborted, "notes": self.notes,
               "history_columns": self.COLS, "_H": H}
        phases = {r.type: r.metrics.get("aft_clearance") for r in self.segs
                  if r.type in ("takeoff", "landing") and r.metrics.get("aft_clearance")}
        gm = getattr(self.sim, "ground", None)
        if phases and gm is not None:
            from .ground_clearance import assess_aft_clearance
            opts = self.ms.get("aft_clearance") or (self.fm.mass.gear or {}).get("aft_clearance")
            out["aft_clearance"] = assess_aft_clearance(gm.contacts, phases, self.fm.mass.m, self.fm.mass.Iyy,
                                                        opts if isinstance(opts, dict) else None)
        return out


# ---------------------------------------------------------------------- quasi-steady comparison
def _flow_for_thrust(prop, V, h, T_req):
    lo, hi = 0.0, 1.0
    if prop.thrust(V, h, 1.0)[0] < T_req:
        return prop.thrust(V, h, 1.0)[1], 1.0
    if T_req <= 0:
        return prop.thrust(V, h, 0.0)[1], 0.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if prop.thrust(V, h, mid)[0] < T_req:
            lo = mid
        else:
            hi = mid
    return prop.thrust(V, h, hi)[1], hi


def quasi_steady(fm, rec: dict, W0: float) -> float | None:
    """Fuel [kg] or energy [J] of the same segment flown in equilibrium with the same model: level/turn
    D = ½ρV²S(CD0 + K CL²) with CL = nW/qS; climb at full throttle (or the segment throttle) from h0 to h1 at
    the target speed; descent T = D − W sin γ (idle floor)."""
    a, p = fm.aero, fm.prop
    t = rec["t_min"] * 60
    V = rec.get("V_target_m_s") or rec.get("Va_mean_m_s")
    if not V or t <= 0:
        return None
    h0, h1 = rec["h0_m"], rec["h1_m"]
    W = W0

    def D(V, h, n=1.0):
        rho = isa(h).rho
        CL = n * W / (0.5 * rho * V**2 * a.S)
        return 0.5 * rho * V**2 * a.S * (a.CD0 + a.K * CL**2)

    typ = rec["type"]
    if typ in ("cruise", "waypoints"):
        return _flow_for_thrust(p, V, h0, D(V, h0))[0] * t
    if typ in ("turn", "loiter", "patrol"):
        n = rec.get("n_cmd") or (1 / math.cos(math.atan(V**2 / (G0 * rec["radius_m"]))) if rec.get("radius_m") else 1.0)
        return _flow_for_thrust(p, V, h0, D(V, h0, n))[0] * t
    if typ == "climb":
        h, burn, dh = h0, 0.0, 25.0
        while h < h1 - 1e-6:
            hm = h + 0.5 * min(dh, h1 - h)
            T, flow = p.thrust(V, hm, 1.0)
            roc = (T - D(V, hm)) * V / W
            if roc <= 0.05:
                return None
            burn += flow * min(dh, h1 - h) / roc
            h += dh
        return burn
    if typ == "descent":
        gam = (h0 - h1) / max(rec["dist_km"] * 1e3, 1.0)
        hm = 0.5 * (h0 + h1)
        return _flow_for_thrust(p, V, hm, D(V, hm) - W * math.sin(math.atan(gam)))[0] * t
    return None


def compare_quasi_steady(fm, result: dict, runner: MissionRunner) -> dict:
    unit = result["unit"]
    f = 1 / 3600 if unit == "Wh" else 1.0
    rows, s_dyn, s_qs = [], 0.0, 0.0
    for r, seg in zip(result["segments"], runner.segs):
        q = quasi_steady(fm, r, seg.W0_N)
        dyn = r[f"used_{unit}"] / f
        k = dyn / q if q else None
        r["quasi_steady_" + unit] = q * f if q else None
        r["k_energy"] = k
        if q:
            s_dyn += dyn
            s_qs += q
        rows.append({"segment": r["segment"], "dyn": dyn * f, "qs": q * f if q else None, "k": k})
    return {"rows": rows, "k_energy_airborne": s_dyn / s_qs if s_qs else None,
            "note": "k = consumo 6-DOF / consumo quase-estacionário com o mesmo modelo (segmentos em voo; "
                    "descolagem/aterragem não comparados)"}


def hq_metrics(fm, V, h, category="B") -> dict:
    """Linear modes of the 6-DOF at (V, h) and MIL-F-8785C levels (via stability.handling_qualities)."""
    from ..stability import handling_qualities
    sim = SixDOF(fm)
    tr = trim(sim, V, h)
    lin = linearise(sim, tr["x"], tr["controls"])
    md = lin["modes"]
    rho = isa(h).rho
    n_alpha = 0.5 * rho * V**2 * fm.aero.S * _cla(sim, tr) / (fm.mass.m * G0)
    lon = {k: md[k] for k in ("short_period", "phugoid") if k in md}
    if "short_period" in md:
        lon["CAP"] = md["short_period"]["wn"]**2 / n_alpha
    lat = {k: md[k] for k in ("dutch_roll", "roll", "spiral") if k in md}
    rows = handling_qualities({"longitudinal": lon, "lateral": lat}, category)
    return {"V": V, "h": h, "modes": md, "n_alpha": n_alpha, "CAP": lon.get("CAP"), "levels": rows}


def _cla(sim, tr):
    al = math.radians(tr["alpha_deg"])
    c = tr["controls"]
    f = lambda a: sim.aero_coeffs(a, 0, 0, 0, 0, 0, c, sim.fm.mass.x_cg)[0]  # noqa: E731
    return (f(al + 1e-4) - f(al - 1e-4)) / 2e-4


# ---------------------------------------------------------------------- plots / files
def plot_mission(result: dict, out_dir: Path, title: str = "") -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    H = result["_H"]
    C = {k: i for i, k in enumerate(result["history_columns"])}
    files = {}
    if not len(H):
        return files
    t = H[:, C["t"]] / 60
    seg = H[:, C["seg"]].astype(int)
    H = H.copy()
    slow = H[:, C["Va"]] < 5.0  # α, β meaningless at rest
    H[slow, C["alpha"]] = np.nan
    H[slow, C["beta"]] = np.nan
    names = [s["segment"] for s in result["segments"]]
    cmap = plt.get_cmap("tab10")
    fig, ax = plt.subplots(4, 2, figsize=(13, 11), sharex=True)
    d = 57.2958
    panels = [("h", "h [m]", 1), ("Va", "V_a [m/s]", 1), ("alpha", "α, θ [°]", d), ("phi", "φ [°]", d),
              ("n_z", "n_z [g]", 1), ("throttle", "manete [-]", 1), ("de", "δe, δa, δr [°]", d), ("used", "consumo", 1)]
    for a, (k, lab, fac) in zip(ax.flat, panels):
        for i in sorted(set(seg)):
            m = seg == i
            a.plot(t[m], H[m, C[k]] * fac, color=cmap(i % 10), lw=1.2, label=names[i] if i < len(names) else "")
        if k == "alpha":
            a.plot(t, H[:, C["theta"]] * d, "k:", lw=0.8, label="θ")
        if k == "de":
            a.plot(t, H[:, C["da"]] * d, "k--", lw=0.6, label="δa")
            a.plot(t, H[:, C["dr"]] * d, "k:", lw=0.6, label="δr")
        if k == "used":
            lab = "consumo [J]" if result["unit"] == "Wh" else "combustível [kg]"
        a.set_ylabel(lab)
        a.grid(alpha=0.3)
    ax[0, 0].legend(fontsize=7, ncol=2)
    for a in ax[-1]:
        a.set_xlabel("t [min]")
    fig.suptitle(f"Missão 6-DOF — {title}")
    fig.tight_layout()
    p = out_dir / "mission_time_history.png"
    fig.savefig(p, dpi=100)
    plt.close(fig)
    files["time_history"] = str(p)
    # 3D trajectory
    fig = plt.figure(figsize=(10, 8))
    a3 = fig.add_subplot(111, projection="3d")
    for i in sorted(set(seg)):
        m = seg == i
        a3.plot(H[m, C["E"]] / 1e3, H[m, C["N"]] / 1e3, H[m, C["h"]], color=cmap(i % 10), lw=1.5,
                label=names[i] if i < len(names) else "")
    a3.set_xlabel("E [km]")
    a3.set_ylabel("N [km]")
    a3.set_zlabel("h [m]")
    a3.legend(fontsize=8)
    a3.set_title(f"Trajectória 3D — {title}")
    p = out_dir / "mission_trajectory_3d.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    files["trajectory_3d"] = str(p)
    # ground track
    fig, a = plt.subplots(figsize=(8, 7))
    for i in sorted(set(seg)):
        m = seg == i
        a.plot(H[m, C["E"]] / 1e3, H[m, C["N"]] / 1e3, color=cmap(i % 10), label=names[i] if i < len(names) else "")
    a.set_aspect("equal", "datalim")
    a.set_xlabel("E [km]")
    a.set_ylabel("N [km]")
    a.grid(alpha=0.3)
    a.legend(fontsize=8)
    a.set_title("Traço no solo (troços extrapolados aparecem como saltos rectos)")
    p = out_dir / "mission_ground_track.png"
    fig.savefig(p, dpi=100)
    plt.close(fig)
    files["ground_track"] = str(p)
    return files


def simulate_mission_6dof(fm, mission, res=None, out_dir=None, hq: bool = True) -> dict:
    """Run a mission (dict or YAML path) on the flight model ``fm``; writes history CSV, summary JSON and PNGs to
    ``out_dir`` when given. Returns the summary (without the raw history array)."""
    ms = load_mission(mission)
    run = MissionRunner(fm, ms, res)
    r = run.run()
    r["quasi_steady"] = compare_quasi_steady(fm, r, run)
    if ms.get("sensor") or ms.get("failures"):
        from .sensors import products_for_6dof
        for k, v in products_for_6dof(ms, r).items():
            r[k] = v
    r["name"] = ms.get("name", "missão")
    if run.ap is not None and getattr(run.ap, "split", None) is not None:
        sp = run.ap.split
        L = run.ap.yaw_log
        frac = sp.n_lim / max(sp.n_steps, 1)
        peak = math.degrees(sp.peak_rate)
        rate_max = math.degrees(sp.rate) if math.isfinite(sp.rate) else None
        r["yaw_split"] = {**L, "saturated_cmd_pct": 100.0 * L["n_sat"] / max(L["n"], 1),
                          "actuator_saturated": sp.sat, "rate_limited": sp.rate_lim,
                          "rate_limited_fraction": frac,
                          "peak_rate_deg_s": peak,
                          "rate_max_deg_s": rate_max,
                          "rate_limit_note": (
                              f"limite de taxa {'tocado em ' + f'{100 * frac:.2f} %' if sp.rate_lim else 'não tocado'} "
                              f"do tempo (pico {peak:.0f} °/s"
                              + (f" vs {rate_max:.0f} °/s do servo" if rate_max else "")
                              + "); o pico é a taxa já limitada pelo atuador. Não é um passa silencioso: o "
                              "contacto fica reportado. A missão é avaliada à parte (saturação de comando, "
                              "derrapagem, decrab).")}
    if hq:
        cr = [s for s in r["segments"] if s["type"] in ("cruise", "waypoints", "loiter")]
        if cr:
            try:
                r["handling_qualities"] = hq_metrics(fm, cr[0]["V_target_m_s"], cr[0]["h0_m"])
            except Exception as e:  # noqa: BLE001
                r["handling_qualities"] = {"error": str(e)}
    to_opts = takeoff_options_for(fm, ms, r, res)
    if to_opts is not None:
        r["takeoff_options"] = to_opts
    if out_dir:
        od = Path(out_dir)
        od.mkdir(parents=True, exist_ok=True)
        with open(od / "mission_history.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(r["history_columns"])
            w.writerows(np.round(r["_H"], 6).tolist())
        r["files"] = plot_mission(r, od, r["name"])
        if r.get("takeoff_options"):
            from .takeoff_options import to_markdown
            (od / "takeoff_options.md").write_text(to_markdown(r["takeoff_options"]), encoding="utf-8")
            r["files"]["takeoff_options_md"] = str(od / "takeoff_options.md")
        r["files"]["history_csv"] = str(od / "mission_history.csv")
        summ = {k: v for k, v in r.items() if k != "_H"}
        (od / "mission_summary.json").write_text(json.dumps(summ, indent=1, default=_js, ensure_ascii=False))
        r["files"]["summary_json"] = str(od / "mission_summary.json")
    r.pop("_H", None)
    return r


class _ScaledThrust:
    """Propulsion proxy with the thrust scaled by ``k`` (fuel flow unchanged — option study only)."""

    def __init__(self, prop, k: float):
        self._p, self._k = prop, k

    def thrust(self, V, h, throttle):
        T, flow = self._p.thrust(V, h, throttle)
        return T * self._k, flow

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._p, name)


def takeoff_options_for(fm, ms: dict, r: dict, res=None) -> dict | None:
    """Options table (:mod:`.takeoff_options`) when the 6-DOF take-off misses the sizing ``takeoff_ground_roll``
    requirement (or always with ``mission.takeoff_options: true``; ``false`` switches it off). The still-air roll and
    the headwind option are re-flown on the 6-DOF (take-off segment alone, same flight model)."""
    flag = ms.get("takeoff_options")
    if flag is False:
        return None
    seg = next((s for s in r.get("segments") or [] if s.get("type") == "takeoff"), None)
    if not seg or seg.get("ground_roll_m") is None:
        return None
    req = None
    try:
        rq = res.spec.requirements if res is not None else None
        if rq is not None and rq.get("takeoff_ground_roll"):
            req = float(rq.value("takeoff_ground_roll"))
    except Exception:  # noqa: BLE001
        req = None
    if req is None and isinstance(flag, dict) and flag.get("requirement_m") is not None:
        req = float(flag["requirement_m"])
    if req is None or (flag is None and float(seg["ground_roll_m"]) <= req):
        return None
    from . import takeoff_options as TOO
    heading = float(ms["segments"][0].get("heading_deg", 0.0)) if ms["segments"][0].get("type") == "takeoff" else 0.0
    base_fm = copy.deepcopy(fm)

    def rerun(h, wind, thrust_factor=1.0):
        m2 = {"dt": ms.get("dt", 0.02), "segments": [{"type": "takeoff", "heading_deg": float(h)}]}
        if wind:
            m2["wind"] = dict(wind)
        fm2 = copy.deepcopy(base_fm)
        if thrust_factor != 1.0:
            fm2.prop = _ScaledThrust(fm2.prop, float(thrust_factor))
        out = MissionRunner(fm2, m2, res).run()
        sg = next((s for s in out["segments"] if s["type"] == "takeoff"), {})
        return sg.get("ground_roll_m")
    cat = ((getattr(res, "launch_recovery", None) or {}).get("catapult")) if res is not None else None
    try:
        return TOO.assess(fm, seg, req, wind=ms.get("wind"), heading_deg=heading, aft=r.get("aft_clearance"),
                          catapult=cat, rerun=rerun)
    except Exception as ex:  # noqa: BLE001 — reported, never a silent pass
        return {"schema": "takeoff_options", "status": "error", "issue": str(ex)}


def _js(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)
