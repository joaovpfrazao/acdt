"""Modelo aerodinâmico, propulsivo e de massa para a simulação 6-DOF (baixa fidelidade, tabelado).

Fontes
------
* Derivadas estáticas, de taxa e de comando: **AVL 3.40** (processo externo, VLM) num varrimento α × flap,
  eixos de estabilidade, taxas adimensionais p̂ = pb/2V, q̂ = qc̄/2V, r̂ = rb/2V (Drela & Youngren, AVL doc.).
* Fuselagem (AVL não a modela): C_nβ,f = −1.3 Vol_f/(S b)(D_f/W_f) (Raymer 6th ed. Eq. 16.47) e desvio do ponto
  neutro dx_fus (manual, já calculado no estágio de estabilidade).
* C_Lα̇, C_mα̇ (atraso do downwash): C_Lα̇ = 2 η V̄_h C_Lα,h dε/dα, C_mα̇ = −2 η V̄_h C_Lα,h (l_t/c̄) dε/dα
  (Etkin & Reid 1996 Sec. 5.8; Nelson 1998 Sec. 3.7).
* Arrasto: C_D = C_D0 + ΔC_D0,flap + K C_L² (polar do projeto) com ΔC_D0,flap = F (c_f/c)(S_flap/S)(δ_f − 10°)
  para δ_f > 10°, F = 0.0144 (simples), 0.0074 (fendido/ranhurado) (Raymer 6th ed. Eq. 12.61).
* Perda: mistura sigmoide entre o modelo linear e placa plana C_L = 2 sinα|sinα| cosα, C_D = 2|sinα|³ + C_D0
  (Beard & McLain 2012, *Small Unmanned Aircraft*, Eqs. 4.9–4.10), com α_perda onde C_L,lin = C_L,max(δ_f)
  (C_L,max limpo/descolagem/aterragem do estágio de hipersustentação, interpolado em δ_f).
* Propulsão: hélice T = η(V) P_disp(h) δ_t / V limitada a baixa velocidade pela tração média de descolagem de
  Raymer Sec. 17.8 (T = η_TO P/(0.7 V_TO)) — o mesmo modelo do módulo de desempenho; reacção T = δ_t T_SL σ
  (lapse). Consumo: pistão ṁ = c_p P_veio, jacto ṁ = c_t T; eléctrico P_bat = P_veio/η_cadeia + P_sistemas
  com η_cadeia = η_tot/η_cruzeiro.
* Massa e inércias: soma de componentes (Roskam Part V) do estágio de estabilidade; I_xz = 0 (PRESSUPOSTO).

Convenções de sinal (padrão): δe > 0 bordo de fuga em baixo (C_mδe < 0); δa > 0 rola para a direita
(C_lδa > 0); δr > 0 bordo de fuga à esquerda (C_nδr < 0); δ_f > 0 flap em baixo.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from acdt import G0
from acdt.core.atmosphere import isa
from acdt.domains.aircraft.weights_detailed import DEFAULT_MAIN_GEAR_LENGTH_M

TABLE_KEYS = ("CL", "Cm", "CLa", "Cma", "CYb", "Clb", "Cnb", "CLq", "Cmq", "CYp", "Clp", "Cnp", "CYr", "Clr",
              "Cnr", "CLde", "Cmde", "CYda", "Clda", "Cnda", "CYdr", "Cldr", "Cndr")
FLAP_DRAG_F = {"plain": 0.0144, "split": 0.0074, "slotted": 0.0074, "fowler": 0.0074, "double_slotted": 0.0074,
               "triple_slotted": 0.0074, "none": 0.0}


@dataclass
class AeroModel:
    S: float
    b: float
    c: float
    x_ref: float                      # moment reference [m, absolute fuselage station]
    alpha_deg: list                   # table grid
    flap_deg: list
    tables: dict                      # key -> [n_flap][n_alpha]
    CLmax: list                       # per flap
    CD0: float
    K: float
    flap_dCD0: list                   # per flap
    CLad: float
    Cmad: float
    dx_fus: float                     # NP shift by the fuselage [fraction of c]
    limits: dict                      # max deflections [deg]
    stall_M: float = 50.0             # sigmoid sharpness [1/rad] (Beard & McLain 2012, Aerosonde value)
    notes: list = field(default_factory=list)
    stall_alpha: dict = field(default_factory=dict)  # cache: str(flap) -> (α+, α−) [rad]
    # drag rudder (tailless split ailerons): the rudder channel carries ΔC_n directly (C_nδr = 1) and adds the
    # profile drag ΔC_D = yaw_drag_per_Cn·|ΔC_n| (= b/ȳ_f, McCormick 1995 Eq. 3.45 via assembly.tailless). 0 = off.
    yaw_drag_per_Cn: float = 0.0
    # tailless yaw augmentation through the drag rudder (mission autopilot): k_beta, k_r (SAS gains, MIL-F-8785C
    # sized in assembly.tailless), washout_s, the split actuator (C1, delta_max_deg, rate_max_deg_s, lag_s,
    # delay_s, bias_deg) and the heading loop for the decrab. Empty = conventional rudder sideslip loop.
    yaw_sas: dict = field(default_factory=dict)

    # -------------------------------------------------------------- interpolation
    def _interp(self, key: str, alpha: float, flap: float) -> float:
        a = np.asarray(self.alpha_deg)
        f = np.asarray(self.flap_deg)
        T = np.asarray(self.tables[key])
        ad = math.degrees(alpha)
        # linear in α with linear extrapolation outside the AVL grid; linear in flap (clipped)
        rows = []
        for i in range(len(f)):
            rows.append(_lin_extrap(a, T[i], ad))
        if len(f) == 1:
            return rows[0]
        return float(np.interp(min(max(flap, f[0]), f[-1]), f, rows))

    def clmax(self, flap: float) -> float:
        return float(np.interp(flap, self.flap_deg, self.CLmax))

    def alpha_stall(self, flap: float) -> tuple[float, float]:
        """Sigmoid centres (α+, α−) [rad] chosen so that the peak of the blended C_L equals +C_L,max(δ_f) and
        −0.8 C_L,max,clean (negative stall: PRESSUPOSTO)."""
        key = f"{float(flap):.3f}"
        if key in self.stall_alpha:
            return tuple(self.stall_alpha[key])
        a = np.radians(np.linspace(-40, 50, 901))
        cl = np.array([self._interp("CL", x, flap) for x in a])
        sa = np.sin(a)
        fp = 2 * sa * np.abs(sa) * np.cos(a)
        M = self.stall_M

        def peak(a0, sign):
            sg = 1 / (1 + np.exp(np.clip(-sign * M * (a - a0), -50, 50)))
            c = (1 - sg) * cl + sg * fp
            return c.max() if sign > 0 else -c.min()

        out = []
        for sign, target in ((1, self.clmax(flap)), (-1, 0.8 * self.CLmax[0])):
            lo, hi = (0.0, math.radians(45)) if sign > 0 else (math.radians(-45), 0.0)
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                too_high = peak(mid, sign) > target
                if sign > 0:
                    lo, hi = (lo, mid) if too_high else (mid, hi)
                else:
                    lo, hi = (mid, hi) if too_high else (lo, mid)
            out.append(0.5 * (lo + hi))
        self.stall_alpha[key] = out
        return out[0], out[1]

    def sigma(self, alpha: float, flap: float) -> float:
        ap, an = self.alpha_stall(flap)
        M = self.stall_M
        s = 1 / (1 + math.exp(max(-50.0, min(50.0, -M * (alpha - ap))))) + \
            1 / (1 + math.exp(max(-50.0, min(50.0, M * (alpha - an)))))
        return min(s, 1.0)

    def flap_drag(self, flap: float) -> float:
        return float(np.interp(flap, self.flap_deg, self.flap_dCD0))

    # -------------------------------------------------------------- coefficients
    def coefficients(self, alpha: float, beta: float, p_hat: float, q_hat: float, r_hat: float, ad_hat: float,
                     de: float, da: float, dr: float, flap: float, x_cg: float, sigma: float | None = None) -> dict:
        """Wind-axis C_L, C_D, C_Y and stability-axis C_l, C_m, C_n about ``x_cg`` (angles/deflections in rad,
        rates dimensionless in stability axes, flap in deg)."""
        g = lambda k: self._interp(k, alpha, flap)  # noqa: E731
        CL_lin = g("CL") + g("CLq") * q_hat + self.CLad * ad_hat + g("CLde") * de
        s = self.sigma(alpha, flap) if sigma is None else sigma
        sa = math.sin(alpha)
        CL_fp = 2 * sa * abs(sa) * math.cos(alpha)
        CL = (1 - s) * CL_lin + s * CL_fp
        CD_pre = self.CD0 + self.flap_drag(flap) + self.K * CL_lin**2
        CD = (1 - s) * CD_pre + s * (self.CD0 + 2 * abs(sa) ** 3)
        if self.yaw_drag_per_Cn:
            CD += self.yaw_drag_per_Cn * abs(g("Cndr") * dr)
        CY = g("CYb") * beta + g("CYp") * p_hat + g("CYr") * r_hat + g("CYda") * da + g("CYdr") * dr
        k = (x_cg - self.x_ref) / self.c - self.dx_fus
        CN = CL * math.cos(alpha) + CD * math.sin(alpha)
        Cm = g("Cm") + g("Cmq") * q_hat + self.Cmad * ad_hat + g("Cmde") * de + CN * k
        Cl = g("Clb") * beta + g("Clp") * p_hat + g("Clr") * r_hat + g("Clda") * da + g("Cldr") * dr
        Cn = g("Cnb") * beta + g("Cnp") * p_hat + g("Cnr") * r_hat + g("Cnda") * da + g("Cndr") * dr \
            + CY * (x_cg - self.x_ref) / self.b
        return {"CL": CL, "CD": CD, "CY": CY, "Cl": Cl, "Cm": Cm, "Cn": Cn, "sigma": s, "CL_lin": CL_lin}

    # -------------------------------------------------------------- io
    def to_json(self, path) -> Path:
        p = Path(path)
        p.write_text(json.dumps(asdict(self), indent=1))
        return p

    @classmethod
    def from_json(cls, path) -> "AeroModel":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


def _lin_extrap(x, y, xi):
    if xi <= x[0]:
        return float(y[0] + (y[1] - y[0]) / (x[1] - x[0]) * (xi - x[0]))
    if xi >= x[-1]:
        return float(y[-1] + (y[-1] - y[-2]) / (x[-1] - x[-2]) * (xi - x[-1]))
    return float(np.interp(xi, x, y))


@dataclass
class Propulsion:
    kind: str                 # piston_prop | electric | turboprop | jet
    P_sl: float | None        # shaft power SL [W]
    T_sl: float | None        # jet thrust SL [N]
    eta_cruise: float
    eta_takeoff: float
    V_low: float              # below this speed thrust is held at T_low (Raymer 17.8 average take-off thrust)
    c_p: float | None
    c_t: float | None
    eta_chain: float          # electric battery→shaft
    P_sys: float
    n_engines: int = 1
    z_thrust: float = 0.0     # thrust line below (+) the CG [m]
    prop: dict | None = None  # propeller.FixedPitchPropeller.to_dict() (BEMT map, rpm-matched) or None

    def propeller(self):
        if self.prop is None:
            return None
        if getattr(self, "_prop_obj", None) is None:
            from ..propeller import FixedPitchPropeller
            object.__setattr__(self, "_prop_obj", FixedPitchPropeller.from_dict(self.prop))
        return self._prop_obj

    def thrust(self, V: float, h: float, throttle: float) -> tuple[float, float]:
        """(T [N], fuel mass flow [kg/s] or battery power [W] for electric). With a propeller map: rpm-matched
        fixed-pitch operating point (propeller.py) per engine; otherwise constant efficiencies."""
        from ..propulsion import is_propeller, lapse
        th = min(max(throttle, 0.0), 1.0)
        sig = isa(max(h, 0.0)).sigma
        pr = self.propeller()
        if pr is not None and is_propeller(self.kind):
            op = pr.operating_point(max(V, 0.0), h, th)  # totals over the n identical units
            if self.kind == "electric":
                return op["T"], op["P"] / self.eta_chain + self.P_sys
            return op["T"], (self.c_p or 0.0) * op["P"]
        if is_propeller(self.kind):
            P = th * self.P_sl * lapse(self.kind, sig)
            Tlow = self.eta_takeoff * P / self.V_low
            T = min(Tlow, self.eta_cruise * P / max(V, 1e-3))
            if self.kind == "electric":
                return T, P / self.eta_chain + self.P_sys
            return T, (self.c_p or 0.0) * P
        T = th * self.T_sl * lapse(self.kind, sig)
        return T, (self.c_t or 0.0) * T

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MassModel:
    m: float
    x_cg: float
    Ixx: float
    Iyy: float
    Izz: float
    Ixz: float = 0.0
    fuel_kg: float = 0.0
    battery_J: float = 0.0
    gear: dict = field(default_factory=dict)  # kind, x_nose, x_main, track, h_cg [m]


@dataclass
class FlightModel:
    aero: AeroModel
    prop: Propulsion
    mass: MassModel
    notes: list = field(default_factory=list)

    def summary(self) -> dict:
        a = self.aero
        i0 = int(np.argmin(np.abs(np.asarray(a.alpha_deg) - 4.0)))
        return {"S": a.S, "b": a.b, "c": a.c, "x_ref": a.x_ref, "alpha_grid_deg": a.alpha_deg, "flap_grid_deg": a.flap_deg,
                "CLmax": a.CLmax, "CD0": a.CD0, "K": a.K, "flap_dCD0": a.flap_dCD0, "CLad": a.CLad, "Cmad": a.Cmad,
                "derivatives_clean_alpha4": {k: a.tables[k][0][i0] for k in TABLE_KEYS},
                "propulsion": self.prop.to_dict(), "mass": asdict(self.mass), "notes": self.notes + a.notes}

    def save(self, out_dir) -> Path:
        od = Path(out_dir)
        od.mkdir(parents=True, exist_ok=True)
        p = od / "flight_model.json"
        p.write_text(json.dumps({"aero": asdict(self.aero), "prop": self.prop.to_dict(), "mass": asdict(self.mass),
                                 "notes": self.notes}, indent=1, default=float))
        return p

    @classmethod
    def load(cls, path) -> "FlightModel":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(AeroModel(**d["aero"]), Propulsion(**d["prop"]), MassModel(**d["mass"]), d.get("notes", []))


# ------------------------------------------------------------------ builder
def _prop_per_engine(pm, n_eng):
    """Propeller map dict (totals over the n identical engine+propeller units) or None."""
    return None if pm.prop is None else pm.prop.to_dict()


def build_flight_model(res, opts: dict | None = None, layout=None, loading: str = "MTOW") -> FlightModel:
    """Build the tabulated flight model of a converged design (needs AVL; see module docstring for sources).

    ``loading``: name of a stability loading case for mass/CG (default MTOW); inertias are the MTOW component
    sum scaled by the mass ratio (PRESSUPOSTO para outros casos)."""
    from ..aero.avl import ControlLayout, avl_available, run_avl_case, wing_x_ac  # noqa: F401
    from ..performance import PerfModel
    from ..stability import ETA_H, inertias, neutral_point
    from .controls import DEFAULTS, ToolNotAvailable, _layout
    if not avl_available():
        raise ToolNotAvailable("build_flight_model requer o AVL no PATH")
    o = {**DEFAULTS, **(res.spec.assumptions.get("stability", {}).get("controls") or {}), **(opts or {})}
    st, cfg, w = res.stability, res.config, res.config.wing
    L = layout or _layout(o)
    from ..stability import inertia_estimate
    I, I_src, I_xc = inertia_estimate(res, st, {**res.spec.assumptions["stability"], **o})
    I = dict(I)
    if o.get("inertia_kgm2"):  # progressive calibration: measured / published inertias
        I.update({k: float(v) for k, v in o["inertia_kgm2"].items() if k in ("Ixx", "Iyy", "Izz", "Ixz")})
        I_src = "dadas pelo utilizador (inertia_kgm2)"
    case = next((c for c in st.cases if c.name == loading), None)
    m = case.mass if case else I["m"]
    x_cg = case.x_cg if case else I["x_cg"]
    sc = m / I["m"]
    alphas = list(o.get("alpha_grid_deg", [-4.0, 0.0, 4.0, 8.0, 12.0]))
    flaps = sorted({0.0, float(o["flap_takeoff_deg"]), float(o["flap_landing_deg"])})
    x_apex = st.x_wing_apex
    x_ref = I["x_cg"]
    fus = cfg.fuselage
    Cnb_f = -1.3 * (fus.wetted_area() * fus.max_diameter / 4) / (w.S * w.span)  # Raymer Eq. 16.47
    tabs = {k: [[0.0] * len(alphas) for _ in flaps] for k in TABLE_KEYS}
    runs = 0
    sgn = {}
    for i, fl in enumerate(flaps):
        for j, al in enumerate(alphas):
            a = run_avl_case(cfg, alpha_deg=al, x_ref=x_ref - x_apex, deflections={"flap": fl}, controls=L)
            runs += 1
            d, cc = a.derivatives, a.controls
            if not sgn:  # orient controls to the standard convention once (clean, first α)
                sgn = {"elevator": -1.0 if cc["elevator"]["Cm"] > 0 else 1.0,
                       "aileron": -1.0 if cc["aileron"]["Cl"] < 0 else 1.0,
                       "rudder": -1.0 if cc["rudder"]["Cn"] > 0 else 1.0}
            vals = {"CL": a.CL, "Cm": a.Cm, "CLa": d["CLa"], "Cma": d["Cma"], "CYb": d["CYb"], "Clb": d["Clb"],
                    "Cnb": d["Cnb"] + Cnb_f, "CLq": d.get("CLq", 0.0), "Cmq": d["Cmq"], "CYp": d.get("CYp", 0.0),
                    "Clp": d["Clp"], "Cnp": d["Cnp"], "CYr": d.get("CYr", 0.0), "Clr": d["Clr"], "Cnr": d["Cnr"],
                    "CLde": sgn["elevator"] * cc["elevator"].get("CL", 0.0),
                    "Cmde": sgn["elevator"] * cc["elevator"].get("Cm", 0.0),
                    "CYda": sgn["aileron"] * cc["aileron"].get("CY", 0.0),
                    "Clda": sgn["aileron"] * cc["aileron"].get("Cl", 0.0),
                    "Cnda": sgn["aileron"] * cc["aileron"].get("Cn", 0.0),
                    "CYdr": sgn["rudder"] * cc["rudder"].get("CY", 0.0),
                    "Cldr": sgn["rudder"] * cc["rudder"].get("Cl", 0.0),
                    "Cndr": sgn["rudder"] * cc["rudder"].get("Cn", 0.0)}
            for k in TABLE_KEYS:
                tabs[k][i][j] = float(vals[k])
    hl = res.highlift
    clm = [float(np.interp(f, [0.0, o["flap_takeoff_deg"], o["flap_landing_deg"]],
                           [hl.CLmax_clean, hl.CLmax_takeoff, hl.CLmax_landing])) for f in flaps]
    flap_cfg = res.spec.assumptions["aero"].get("flap") or {}
    kind = flap_cfg.get("kind", "plain")
    Sf = flap_cfg.get("flapped_area_ratio", 0.6)
    cf = 1 - L.flap_hinge_xc
    dcd0 = [FLAP_DRAG_F.get(kind, 0.0144) * cf * Sf * max(f - 10.0, 0.0) for f in flaps]
    npd = neutral_point(cfg, {"CLa_w": res.CLalpha}, st.x_mac_le, st.x_wing_apex)
    lt, c = cfg.htail.arm, w.mac
    Vh = cfg.htail.S * lt / (w.S * c)
    CLad = 2 * ETA_H * Vh * npd["CLa_h"] * npd["deps_dalpha"]
    Cmad = -CLad * lt / c
    aero = AeroModel(S=w.S, b=w.span, c=c, x_ref=x_ref, alpha_deg=alphas, flap_deg=flaps, tables=tabs, CLmax=clm,
                     CD0=res.polar.CD0, K=res.polar.K, flap_dCD0=dcd0, CLad=CLad, Cmad=Cmad, dx_fus=st.dx_fus,
                     limits={"elevator": o["elevator_max_deg"], "aileron": o["aileron_max_deg"],
                             "rudder": o["rudder_max_deg"], "flap": max(flaps)},
                     notes=[f"AVL: {runs} casos (α {alphas} × flap {flaps}); C_nβ fuselagem {Cnb_f:+.4f} (Raymer 16.47)",
                            f"ΔC_D0 flap Raymer Eq. 12.61 ({kind}, c_f/c {cf:.2f}, S_flap/S {Sf:.2f})",
                            "perda: mistura sigmoide com placa plana (Beard & McLain Eqs. 4.9–4.10); C_m pós-perda "
                            "linear (sem dados) — PRESSUPOSTO",
                            "sem efeito de solo, sopro da hélice nem compressibilidade"])
    pm = PerfModel.from_result(res)
    if pm.auxiliary_shaft_W:
        raise ValueError("onboard thermal generator extraction: use pointmass; 6-DOF coupling is not implemented")
    rho0 = isa(0.0).rho
    W = m * G0
    Vto = 1.1 * math.sqrt(2 * W / (rho0 * w.S * pm.CLmax_to))
    pd = res.spec.assumptions["propulsion"]
    prop = Propulsion(kind=pm.kind, P_sl=pm.P_sl, T_sl=pm.T_sl, eta_cruise=pm.eta_cruise, eta_takeoff=pm.eta_takeoff,
                      V_low=0.7 * Vto, c_p=pm.c_p, c_t=pm.c_t,
                      eta_chain=(pm.eta_tot / pm.eta_cruise) if pm.eta_tot else 1.0, P_sys=pm.P_sys or 0.0,
                      n_engines=int(pd.get("n_engines", 1)), z_thrust=float(o.get("thrust_line_z_m", 0.0)),
                      prop=_prop_per_engine(pm, int(pd.get("n_engines", 1))))
    comp = res.spec.assumptions["weights"].get("components", {})
    stations = {s["item"]: s["x_m"] for s in st.stations}
    h_mg = comp.get("main_gear_length_m", DEFAULT_MAIN_GEAR_LENGTH_M)
    kind = comp.get("landing_gear", "tricycle")
    if o.get("cg_height_m") is not None:
        h_cg = o["cg_height_m"]
    elif kind == "none":  # belly skids on the fuselage bottom (PRESSUPOSTO: CG on the fuselage axis)
        h_cg = 0.5 * fus.max_diameter
    else:
        h_cg = h_mg + 0.5 * fus.max_diameter
    gear = {"kind": kind, "x_main": stations.get("main_gear"),
            "x_nose": stations.get("nose_gear"), "h_cg": h_cg,
            "track": float(o.get("gear_track_m") or 0.23 * w.span), "fuselage_length": fus.length,
            "fuselage_diameter": fus.max_diameter}
    energy = res.sizing.energy_J if pm.kind == "electric" else 0.0
    mass = MassModel(m=m, x_cg=x_cg, Ixx=I["Ixx"] * sc, Iyy=I["Iyy"] * sc, Izz=I["Izz"] * sc, Ixz=I.get("Ixz", 0.0) * sc,
                     fuel_kg=(res.sizing.Wf if pm.kind != "electric" else 0.0) if loading == "MTOW" else 0.0,
                     battery_J=energy or 0.0, gear=gear)
    notes = [f"massa/CG: caso '{loading}' ({m:.1f} kg, x_cg {x_cg:.3f} m); inércias {I_src}"
             f"{' escaladas pela massa' if abs(sc - 1) > 1e-6 else ''}; I_xz = 0 (PRESSUPOSTO)",
             f"trem: via {gear['track']:.2f} m ({'dado' if o.get('gear_track_m') else 'PRESSUPOSTO 0.23 b'}), "
             f"altura do CG {h_cg:.2f} m",
             ("propulsão: hélice de passo fixo, mapa BEMT C_T(J), C_P(J) com rpm de equilíbrio motor/hélice "
              "(propeller.py) — o mesmo do dimensionamento/desempenho" if prop.prop else
              "propulsão: T = η P/V limitada por T_TO médio (Raymer 17.8) — mesma base do módulo de desempenho"),
             "inércias, verificação cruzada: componentes/Roskam ("
             + I_xc["roskam_source"] + ") = " + ", ".join(f"{k} {v:.2f}" for k, v in
                                                         I_xc["ratio_components_over_roskam"].items())]
    return FlightModel(aero, prop, mass, notes)
