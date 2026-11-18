"""Fase 9 — camber (cruise) flaps as a design OPTION.

A camber flap is a plain trailing-edge flap (typically 15–25 % chord) deflected by small angles in flight,
negative for high speed / low CL and positive for loiter / high CL, so that each CL is flown with the
section whose low-drag range ("bucket") contains it. The airplane then follows the *envelope* of the
flapped polars (Thomas, *Fundamentals of Sailplane Design*, 1999, Ch. 3 "Airfoils" and Ch. 5 "Flaps";
Althaus & Wortmann, *Stuttgarter Profilkatalog I*, 1981 — FX flapped laminar sections; Boermans & Waibel,
"Aerodynamic and structural design of the Standard Class sailplane ASW-24", ICAS 1988 / Boermans 2006
"Research on sailplane aerodynamics at Delft" — HQ/DU flapped sections and the flap schedule δ(CL)).

Method (low fidelity, each step classical and cited; the flap is only an *option* — the design-options
study in :mod:`acdt.domains.aircraft.design_options` decides whether it pays):

1. **Section polars vs δf** — XFOIL GDES/FLAP (plain sealed-gap flap hinged on the camber line at
   x/c = 1 − c_f/c) or NeuralFoil on the AeroSandbox-deflected geometry, δf ∈ [−10°, +15°] by default.
2. **Section envelope** — cd_env(cl) = min_δ cd_δ(cl) over the deflections whose attached range contains cl
   (cl_min,δ + 0.05 < cl < cl_max,δ − ``cl_margin``), and the schedule δ*(cl).
3. **Wing envelope** — the spanwise cl(y) of the clean wing (AVL, else Schrenk) is kept (PRESSUPOSTO: the
   flap-induced change of span loading and of the induced drag is neglected — small for full-span flaps,
   see Thomas Ch. 5); for every wing CL one deflection is chosen for the whole flapped span, minimising
   the wing profile drag; ΔCD(CL) = Q (1 + leakage) Σ (cd_δ* − cd_0) S_i / S ≤ 0.
4. **High lift** — ΔCLmax = 0.9 (clmax,δmax − clmax,0) (S_flapped / S) cos Λ at the stall Reynolds number
   (Raymer Eq. 12.21 with the XFOIL/NeuralFoil section increment instead of Table 12.2).

Opt-in (``camber_flap.trim_drag`` / ``camber_flap.gap``): residual elevator/HT induced trim drag from
Δcm0(δ) (Nelson / Etkin tail-volume balance) and a supplied gap ΔCD with source, or an explicit sealed-gap
claim. Missing effectiveness / moment / HT geometry / gap increment → **unassessed**, never a silent zero.
Still not modelled: hinge-moment actuator sizing, partial-span induced-drag penalty, DATCOM gap correlations
without a supplied coefficient.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .airfoil import AirfoilPolar, airfoil_polar

DEFAULT_DELTAS = (-10.0, -7.5, -5.0, -2.5, 0.0, 2.5, 5.0, 7.5, 10.0, 12.5, 15.0)

# defaults of assumptions.aero.camber_flap (the geometric values are PRESSUPOSTOS of the option, not data)
CAMBER_DEFAULTS = {
    "kind": "camber",          # camber (inboard, ailerons outboard) | flaperon (full span, ailerons merged)
    "chord_ratio": 0.20,       # c_f/c — PRESSUPOSTO (sailplane camber flaps 0.15–0.20 c, Thomas Ch. 5)
    "eta_in": 0.0,             # flapped span (fraction of the semispan; fuselage strips excluded anyway)
    "eta_out": None,           # None → 0.65 camber / 0.95 flaperon — PRESSUPOSTO
    "deltas_deg": list(DEFAULT_DELTAS),
    "cl_margin": 0.15,         # stay this far below the flapped section clmax when scheduling
    "actuators": None,         # extra actuators vs the clean wing; None → 2 camber / 0 flaperon (PRESSUPOSTO)
    "actuator_mass_kg": None,  # user/datasheet value per actuator (no default: not invented)
    "surface_mass_kg_m2": None,  # hinge/fitting increment per flap area (user value; no default)
    "actuator_cost_usd": 0.0,  # per actuator (user value, dated)
    "landing_deflection": True,  # also used as a landing flap (Raymer plain-flap ΔCLmax) — PRESSUPOSTO
    # Opt-in trim / gap (default omit → legacy envelope-only polar; unknown ≠ zero when requested)
    "trim_drag": False,          # True → add HT induced trim CD from Δcm0(δ); needs HT geometry
    "trim_SM": 0.10,             # static margin used for residual trim (PRESSUPOSTO if not from stability)
    "trim_e_ht": 0.80,           # Oswald-like e of the HT for induced trim drag (PRESSUPOSTO)
    "gap": None,                 # None → gap drag omitted (legacy); see resolve_gap()
}


def resolve(opts: dict | None) -> dict | None:
    if not opts:
        return None
    o = {**CAMBER_DEFAULTS, **opts}
    if o["eta_out"] is None:
        o["eta_out"] = 0.95 if o["kind"] == "flaperon" else 0.65
    if o["actuators"] is None:
        o["actuators"] = 0 if o["kind"] == "flaperon" else 2
    return o


@dataclass
class SectionEnvelope:
    airfoil: str
    Re: float
    hinge_x: float
    deltas: list
    polars: list
    cl_margin: float = 0.15
    source: str = ""

    def _valid(self, p: AirfoilPolar, cl):
        i0, i1 = int(np.argmin(p.cl)), int(np.argmax(p.cl))
        return (cl > p.cl[i0] + 0.05) & (cl < p.cl[i1] - self.cl_margin)

    def cd_table(self, cl) -> np.ndarray:
        """cd[δ, cl] with NaN where the flapped section is outside its attached range."""
        cl = np.atleast_1d(np.asarray(cl, float))
        out = np.full((len(self.deltas), cl.size), np.nan)
        for k, p in enumerate(self.polars):
            v = self._valid(p, cl)
            out[k, v] = p.cd_at_cl(cl[v])
        return out

    def envelope(self, cl):
        """(cd_env, δ*) at section cl; the clean polar (δ = 0) where no deflection is valid."""
        cl = np.atleast_1d(np.asarray(cl, float))
        t = self.cd_table(cl)
        i0 = self.deltas.index(0.0)
        clean = self.polars[i0].cd_at_cl(cl)
        t[i0] = np.where(np.isnan(t[i0]), clean, t[i0])
        k = np.nanargmin(t, axis=0)
        return t[k, np.arange(cl.size)], np.asarray(self.deltas)[k]

    def clmax(self, delta: float) -> float:
        return self.polars[self.deltas.index(delta)].clmax

    def cm0(self, delta: float) -> float:
        return self.polars[self.deltas.index(delta)].cm0


def section_envelope(airfoil: str, Re: float, mach: float = 0.0, xtr: float = 1.0, chord_ratio: float = 0.2,
                     deltas=DEFAULT_DELTAS, prefer: str = "xfoil", cl_margin: float = 0.15) -> SectionEnvelope:
    deltas = sorted({float(d) for d in deltas} | {0.0})
    xh = 1.0 - chord_ratio
    # each deflection is an independent XFOIL process → run them concurrently (threads only wait on subprocesses)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(len(deltas), 6)) as ex:
        pols = list(ex.map(lambda d: airfoil_polar(airfoil, Re, mach, xtr=xtr, prefer=prefer, flap=(xh, d)), deltas))
    src = sorted({p.source.split(",")[0].split(" (")[0] for p in pols})
    return SectionEnvelope(airfoil, Re, xh, deltas, pols, cl_margin, " + ".join(src))


@dataclass
class CamberSchedule:
    """Wing-level camber-flap envelope: ΔCD(CL) ≤ 0 and the flap schedule δ(CL).

    Optional ``dCD_trim`` / ``dCD_gap`` are added only when the corresponding status is ``assessed``.
    Unassessed terms are never silently treated as zero in :meth:`dcd`.
    """
    kind: str
    CL: np.ndarray
    dCD: np.ndarray
    delta: np.ndarray
    flapped_area_ratio: float
    flap_area_m2: float
    dCLmax: float
    delta_max: float
    dcm0_per_deg: float
    section: SectionEnvelope | None = None
    section_stall: SectionEnvelope | None = None
    notes: list = field(default_factory=list)
    opts: dict = field(default_factory=dict)
    dCD_trim: np.ndarray | None = None
    dCD_gap: float | None = None
    trim_drag_status: str = "omitted"   # omitted | assessed | unassessed
    gap_drag_status: str = "omitted"    # omitted | assessed | unassessed
    trim_meta: dict = field(default_factory=dict)
    gap_meta: dict = field(default_factory=dict)

    def dcd(self, CL):
        CL = np.asarray(CL, float)
        out = np.interp(CL, self.CL, self.dCD)
        if self.trim_drag_status == "assessed" and self.dCD_trim is not None:
            out = out + np.interp(CL, self.CL, self.dCD_trim)
        if self.gap_drag_status == "assessed" and self.dCD_gap is not None:
            out = out + float(self.dCD_gap)
        return out

    def delta_at(self, CL):
        return np.interp(np.asarray(CL, float), self.CL, self.delta)

    def summary(self) -> dict:
        i = int(np.argmin(self.dCD))
        # profile-only min; total with assessed trim/gap at that CL
        c_star = float(self.CL[i])
        return {"kind": self.kind, "flapped_area_ratio": self.flapped_area_ratio, "flap_area_m2": self.flap_area_m2,
                "dCLmax": self.dCLmax, "delta_max_deg": self.delta_max, "dCD_min": float(self.dCD[i]),
                "CL_at_dCD_min": c_star, "dcm0_per_deg": self.dcm0_per_deg,
                "dCD_total_at_dCD_min": float(self.dcd(c_star)),
                "trim_drag_status": self.trim_drag_status, "gap_drag_status": self.gap_drag_status,
                "trim_meta": dict(self.trim_meta), "gap_meta": dict(self.gap_meta),
                "schedule": [{"CL": float(c), "delta_deg": float(d), "dCD_profile": float(x),
                              "dCD_trim": (float(np.interp(c, self.CL, self.dCD_trim))
                                           if self.dCD_trim is not None else None)}
                             for c, d, x in zip(self.CL[::4], self.delta[::4], self.dCD[::4])],
                "section_source": self.section.source if self.section else "", "notes": self.notes}


def _re_bin(Re: float) -> float:
    """Reynolds number snapped to a log grid (Δlog10 = 0.05, ±6 %) so that the sizing iterations reuse the
    cached flapped polars (cd ∝ Re^-0.2..-0.5 → < 3 % in cd; PRESSUPOSTO of the low-fidelity method)."""
    return float(f"{10 ** (round(math.log10(max(Re, 1e4)) / 0.05) * 0.05):.2g}")


def _mach_bin(M: float) -> float:
    return round(round(M / 0.05) * 0.05, 2)



def section_cm0_at(sec: SectionEnvelope, delta_deg: float) -> float:
    """Interpolate section cm0 vs flap deflection (from the flapped polars)."""
    d = np.asarray(sec.deltas, float)
    cm = np.asarray([sec.cm0(float(x)) for x in d], float)
    return float(np.interp(delta_deg, d, cm))


def wing_delta_Cm(sec: SectionEnvelope, delta_deg: float, flapped_area_ratio: float) -> float:
    """L0 wing ΔCm from section Δcm0 at constant δ (strip mean-chord ≈ mac — PRESSUPOSTO).

    ΔCm ≈ (cm0(δ) − cm0(0)) · (S_flapped/S). Cited as the usual strip average of section moment
    about the aerodynamic centre (Etkin & Reid / Nelson moment build-up; not a DATCOM hinge moment).
    """
    dcm = section_cm0_at(sec, delta_deg) - section_cm0_at(sec, 0.0)
    return dcm * float(flapped_area_ratio)


def resolve_gap(gap) -> dict:
    """Classify gap drag. Never invents a gap/c → ΔCD correlation.

    * ``None`` / omitted → ``omitted`` (legacy; envelope polar unchanged).
    * ``{sealed: true, source: ...}`` → assessed ΔCD = 0 (XFOIL GDES/FLAP sealed-gap geometry).
    * ``{dCD: <float>, source: ...}`` → assessed supplied increment (mandatory nonempty source).
    * ``{chord_ratio: ..., source: ...}`` without ``dCD`` → **unassessed** (gap known, drag not).
    """
    if gap is None:
        return {"status": "omitted", "dCD": None, "note": "gap drag omitted (opt-in camber_flap.gap)"}
    if not isinstance(gap, dict):
        raise ValueError("camber_flap.gap must be a mapping or null")
    src = gap.get("source")
    if gap.get("sealed") is True:
        if not (isinstance(src, str) and src.strip()):
            raise ValueError("camber_flap.gap.sealed: true requires a nonempty source "
                             "(e.g. 'XFOIL GDES/FLAP sealed-gap assumption')")
        return {"status": "assessed", "dCD": 0.0, "sealed": True, "source": src.strip(),
                "note": "sealed gap → no extra gap ΔCD (XFOIL sealed-flap geometry); " + src.strip()}
    if gap.get("dCD") is not None:
        if not (isinstance(src, str) and src.strip()):
            raise ValueError("camber_flap.gap.dCD requires a nonempty source (datasheet/DATCOM/PRESSUPOSTO)")
        dcd = float(gap["dCD"])
        if not math.isfinite(dcd) or dcd < 0:
            raise ValueError("camber_flap.gap.dCD must be a finite ≥ 0 increment")
        return {"status": "assessed", "dCD": dcd, "source": src.strip(),
                "note": f"supplied gap ΔCD = {dcd:g} ({src.strip()})"}
    if gap.get("chord_ratio") is not None:
        return {"status": "unassessed", "dCD": None,
                "chord_ratio": float(gap["chord_ratio"]), "source": src,
                "note": "gap/c supplied but no cited ΔCD or sealed claim — unassessed "
                        "(never invent a gap-drag correlation; provide gap.dCD with source or gap.sealed)"}
    return {"status": "unassessed", "dCD": None,
            "note": "camber_flap.gap present but neither sealed nor dCD — unassessed"}


def ht_trim_induced_cd(config, delta_Cm: float, *, e_ht: float = 0.80, eta_h: float = 0.9) -> dict:
    """HT induced trim-drag increment from a wing ΔCm that the elevator must cancel.

    Classical tail-volume balance (Nelson *Flight Stability* Ch. 2; Etkin & Reid): 
    CL_h ≈ −ΔCm / (η_h V_H), then CD_i,h = CL_h² / (π e_ht AR_h) · (S_h/S).
    Missing HT geometry or non-finite V_H / AR_h → unassessed (not zero).
    """
    ht = getattr(config, "htail", None)
    w = getattr(config, "wing", None)
    if ht is None or w is None:
        return {"status": "unassessed", "dCD": None, "reason": "no htail/wing on configuration"}
    S, mac = float(w.S), float(w.mac)
    Sh, arm, ARh = float(ht.S), float(ht.arm), float(getattr(ht, "AR", 0.0) or 0.0)
    if S <= 0 or mac <= 0 or Sh <= 0 or arm <= 0 or ARh <= 0:
        return {"status": "unassessed", "dCD": None, "reason": "HT/wing geometry incomplete for V_H / AR_h"}
    V_H = Sh * arm / (S * mac)
    if V_H <= 0 or not math.isfinite(V_H):
        return {"status": "unassessed", "dCD": None, "reason": "tail volume V_H not positive"}
    if e_ht <= 0 or eta_h <= 0:
        return {"status": "unassessed", "dCD": None, "reason": "e_ht / eta_h must be > 0"}
    CL_h = -float(delta_Cm) / (eta_h * V_H)
    dCD = (CL_h ** 2) / (math.pi * e_ht * ARh) * (Sh / S)
    return {"status": "assessed", "dCD": dCD, "CL_h": CL_h, "V_H": V_H, "AR_h": ARh,
            "method": "Nelson/Etkin: CL_h = −ΔCm/(η V_H); CD_i,h = CL_h²/(π e AR_h)·(S_h/S)",
            "eta_h": eta_h, "e_ht": e_ht}


def apply_trim_and_gap(sched: CamberSchedule, config, opts: dict | None = None) -> CamberSchedule:
    """Attach opt-in trim-drag and gap terms to an existing :class:`CamberSchedule` (mutates and returns it)."""
    o = resolve(opts or sched.opts) or {}
    # --- gap ---
    g = resolve_gap(o.get("gap"))
    sched.gap_drag_status = g["status"]
    sched.gap_meta = {k: v for k, v in g.items() if k != "status"}
    if g["status"] == "assessed":
        sched.dCD_gap = float(g["dCD"])
        sched.notes.append("gap drag: " + g["note"])
    elif g["status"] == "unassessed":
        sched.dCD_gap = None
        sched.notes.append("gap drag UNASSESSED: " + g["note"])
    else:
        sched.notes.append("gap drag omitted (set camber_flap.gap to assess)")

    # --- trim ---
    if not o.get("trim_drag"):
        sched.trim_drag_status = "omitted"
        sched.dCD_trim = None
        sched.trim_meta = {"note": "trim drag omitted (set camber_flap.trim_drag: true)"}
        sched.notes.append("arrasto de compensação omitido (opt-in trim_drag: true); Δcm0 reportado em dcm0_per_deg")
        return sched
    if sched.section is None:
        sched.trim_drag_status = "unassessed"
        sched.dCD_trim = None
        sched.trim_meta = {"reason": "no section envelope for cm0(δ)"}
        sched.notes.append("trim drag UNASSESSED: sem polar de secção para Δcm0")
        return sched
    e_ht = float(o.get("trim_e_ht", 0.80))
    eta = 0.9  # ETA_H classical (stability.ETA_H)
    dCD_t = np.zeros_like(sched.CL)
    meta_rows = []
    any_bad = False
    reason = None
    for j, (c, d) in enumerate(zip(sched.CL, sched.delta)):
        dCm = wing_delta_Cm(sched.section, float(d), sched.flapped_area_ratio)
        r = ht_trim_induced_cd(config, dCm, e_ht=e_ht, eta_h=eta)
        if r["status"] != "assessed":
            any_bad = True
            reason = r.get("reason")
            break
        dCD_t[j] = r["dCD"]
        if j % 8 == 0:
            meta_rows.append({"CL": float(c), "delta_deg": float(d), "dCm": dCm,
                              "CL_h": r["CL_h"], "dCD_trim": r["dCD"]})
    if any_bad:
        sched.trim_drag_status = "unassessed"
        sched.dCD_trim = None
        sched.trim_meta = {"reason": reason}
        sched.notes.append(f"trim drag UNASSESSED: {reason} (never zero)")
    else:
        sched.trim_drag_status = "assessed"
        sched.dCD_trim = dCD_t
        sched.trim_meta = {"method": "Nelson/Etkin HT induced from ΔCm(δ*)", "e_ht": e_ht, "eta_h": eta,
                          "samples": meta_rows,
                          "dCD_trim_max": float(np.max(dCD_t)), "dCD_trim_at_mid": float(dCD_t[len(dCD_t)//2])}
        sched.notes.append(
            f"trim drag assessed: max ΔCD_trim={float(np.max(dCD_t)):.5f} "
            f"(CL_h=−ΔCm/(η V_H), CD_i,h; Nelson/Etkin; e_ht={e_ht:g})")
    return sched


def wing_camber_schedule(config, opts: dict, V: float, rho: float, mu: float, a: float, laminar_wing: float,
                         Q_wing: float, lp_fraction: float, V_stall: float, CLmax_wing: float,
                         prefer: str = "xfoil", sweep: float = 0.0) -> CamberSchedule:
    """Wing envelope polar correction for the camber-flap option ``opts`` (see :data:`CAMBER_DEFAULTS`)."""
    from .lowfi import _strip_cl_model
    o = resolve(opts)
    w, fus = config.wing, config.fuselage
    airfoil = getattr(w, "airfoil", None) or "NACA 0012"
    Re = _re_bin(rho * V * w.mac / mu)
    Re_s = _re_bin(rho * V_stall * w.mac / mu)
    xtr = max(laminar_wing, 0.01)
    deltas = o["deltas_deg"]
    sec = section_envelope(airfoil, Re, _mach_bin(V / a), xtr, o["chord_ratio"], deltas, prefer, o["cl_margin"])
    y, area, cl_fun, *_ , span_src = _strip_cl_model(config, V / a, fus.max_diameter)
    eta = np.abs(y) / (w.span / 2)
    m = (eta >= o["eta_in"]) & (eta <= o["eta_out"])
    S = w.S
    S_fl = float(np.sum(area[m]))
    CL = np.linspace(0.0, 0.95 * CLmax_wing, 48)
    dCD, dl = np.zeros_like(CL), np.zeros_like(CL)
    k = 1.0 * Q_wing * (1 + lp_fraction) / S
    for j, c in enumerate(CL):
        cl = cl_fun(c)[m]
        t = sec.cd_table(cl)                       # [δ, strip]
        i0 = sec.deltas.index(0.0)
        clean = sec.polars[i0].cd_at_cl(cl)
        base = float(np.sum(clean * area[m]))
        tot = np.array([np.sum(r * area[m]) if np.all(np.isfinite(r)) else np.inf for r in t])
        tot[i0] = base
        b = int(np.argmin(tot))
        dCD[j], dl[j] = k * (tot[b] - base), sec.deltas[b]
    # high lift at the stall Reynolds number with the largest deflection
    dmax = max(sec.deltas)
    sec_s = section_envelope(airfoil, Re_s, _mach_bin(V_stall / a), 1.0, o["chord_ratio"], [0.0, dmax], prefer)
    dcl = sec_s.clmax(dmax) - sec_s.clmax(0.0)
    dCLmax = 0.9 * max(dcl, 0.0) * (S_fl / S) * math.cos(sweep)
    dcm = (sec.cm0(dmax) - sec.cm0(0.0)) / dmax if dmax else 0.0
    notes = [f"camber flap {o['kind']}: c_f/c {o['chord_ratio']:.2f}, η {o['eta_in']:.2f}–{o['eta_out']:.2f}, "
             f"S_flapped/S {S_fl / S:.2f}; polars {sec.source} at Re {Re:.2g} (cruise) and {Re_s:.2g} (stall); "
             f"span loading {span_src}",
             f"Δcm0 {dcm:+.4f}/° de flap (secção)"]
    sched = CamberSchedule(o["kind"], CL, dCD, dl, S_fl / S, S_fl * o["chord_ratio"], dCLmax, dmax, dcm,
                           sec, sec_s, notes, o)
    return apply_trim_and_gap(sched, config, o)


def plot_camber(sched: CamberSchedule, polar, path, title: str = ""):
    """Section polars vs δ with the envelope, the flap schedule δ(CL) and the airplane polar with/without."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.2))
    sec = sched.section
    cmap = plt.get_cmap("coolwarm")
    for d, p in zip(sec.deltas, sec.polars):
        i0, i1 = int(np.argmin(p.cl)), int(np.argmax(p.cl))
        ax[0].plot(p.cd[i0:i1 + 1], p.cl[i0:i1 + 1], color=cmap((d + 10) / 25), lw=0.9, label=f"δ {d:+g}°")
    clg = np.linspace(min(p.clmin for p in sec.polars), max(p.clmax for p in sec.polars), 300)
    cde, _ = sec.envelope(clg)
    ax[0].plot(cde, clg, "k-", lw=2, label="envolvente")
    ax[0].set_xlim(0, 0.03)
    ax[0].set_xlabel("cd")
    ax[0].set_ylabel("cl")
    ax[0].set_title(f"{sec.airfoil}, Re {sec.Re:.2g}, c_f/c {1 - sec.hinge_x:.2f}")
    ax[0].legend(fontsize=6, ncol=2)
    ax[1].step(sched.CL, sched.delta, where="mid")
    ax[1].set_xlabel("CL avião")
    ax[1].set_ylabel("δf ótimo [°]")
    ax[1].set_title("Escalonamento δ(CL)")
    CL = sched.CL
    from .drag import DragPolar
    clean = DragPolar(polar.CD0, polar.K)
    ax[2].plot(clean.CD(CL), CL, "k--", label=f"sem flap (L/D max {clean.LD_max:.1f})")
    env = DragPolar(polar.CD0, polar.K, sched)
    ax[2].plot(env.CD(CL), CL, "b-", label=f"envolvente (L/D max {env.LD_max:.1f})")
    ax[2].set_xlabel("CD")
    ax[2].set_ylabel("CL")
    ax[2].set_title(title or "Polar do avião")
    ax[2].legend(fontsize=8)
    for a_ in ax:
        a_.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
