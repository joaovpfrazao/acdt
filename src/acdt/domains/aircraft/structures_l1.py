"""BeamAero — L1 aircraft structure on top of the wing box already sized in :mod:`structures`.

The wing beam is the Phase 2/5 box (Megson / Bruhn). This module adds:

* a fuselage equivalent beam:  circular shell with the NASA SP-8007 (1968) knockdown, minimum
  longerons and frames (Niu 1988 Ch. 11 layout), a floor and two bulkheads (Torenbeek 1982 App. D
  lists those items; the gauges below are the material minima, stated as PRESSUPOSTO);
* empennage beams: the same :func:`structures.box_beam_sizing` on :meth:`TailSurface.as_wing`,
  with a uniform span load (PRESSUPOSTO, heavier in bending than an ellipse: M_root = L b / 8);
* cruise elastic twist fed back to a Glauert lifting line (Anderson §5.3), the same fixed point
  as Phase 5 (:meth:`wingbox.optimize` ``_llt_elastic``) without NeuralFoil. Section slope
  a₀ = 0.95 × 2π (Raymer §12.4.1). α_L0 = 0 unless the caller passes a pitching moment ``cm0``.

``k_EI`` and ``k_GJ`` scale the wing beam only (they are the wing FEM / beam ratios). The fuselage
has no L3 calibration.

The in-cycle mass uses a wing aerodynamic centre at 0.35 L until the stability stage places the
wing. :func:`analyse_design` called again after that stage (see :mod:`phase2`) refreshes the
reported beam. The two stations are not the same; the note on the result says which one was used.

The shell is an unstiffened monocoque (SP-8007) plus minimum longerons. A longeron-stiffened shell
is lighter for the same buckling load, so this mass is a conservative lower-fidelity estimate, not
a factor fitted to Raymer Eq. 15.49. Raymer's fuselage group also includes floors, doors and
windows; the floor and the two bulkheads below are the cited pieces this beam can carry. Doors and
windows are not modelled.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from acdt import G0
from acdt.core.atmosphere import isa
from acdt.core.structures.beam import cantilever_response, thin_circular_tube, tube_thickness
from acdt.core.structures.loads import (angular_tail_increment, checked_maneuver_alpha, equilibrium_tail_load,
                                       surface_limit_lift)

from .geometry import LB, FT
from .landing_gear import adopted_factors
from .structures import MATERIALS, PSF, RHO0, BeamLoads, _cum_from_tip, box_beam_sizing, chord_at, v_n_diagram
from .weights_detailed import raymer_ga_fuselage

# Layout PRESSUPOSTO, stated. Floor length and width: light single-aisle, not a transport deck.
# Frame flange width: Niu Ch. 11 light-aircraft frame, order 25 mm.
_FLOOR_LENGTH_FRAC = 0.45
_FLOOR_WIDTH_FRAC = 0.75
_FRAME_FLANGE_M = 0.025
_N_BULKHEADS = 2
_X_WING_FRAC = 0.35          # until stability places the wing
_X_ENGINE_FRAC = 0.12
_X_CG_LAND_FRAC = 0.30       # landing CG when the loading diagram has not run
_X_NOSE_GEAR_FRAC = 0.10
_X_MAIN_GEAR_FRAC = 0.45
_CLMAX_HT = 1.0              # section, symmetric + elevator. PRESSUPOSTO — not the wing clmax
_CLMAX_VT = 0.8              # section, fin. PRESSUPOSTO
_Z_CP_FRAC = 0.40            # fin centre of pressure / height. PRESSUPOSTO
_K_Y = 0.25                  # pitch radius of gyration / L for the 23.423 increment. PRESSUPOSTO
_A0_OVER_2PI = 0.95          # Raymer §12.4.1
_FS = 1.5                    # 14 CFR / CS 23.303


def flex_requested(assumptions: dict | None) -> bool:
    """``assumptions.structures.flex`` or ``assumptions.aero.elastic``."""
    a = assumptions or {}
    return bool((a.get("structures") or {}).get("flex") or (a.get("aero") or {}).get("elastic"))


@dataclass
class ElasticCorrection:
    """Cruise lifting-line correction. ``applied`` is true only when the size loop scaled K by ``K_ratio``."""

    applied: bool
    CLa_rigid: float
    CLa_flex: float
    CDi_rigid: float
    CDi_flex: float
    K_ratio: float
    xac_w: float
    tip_twist_deg: float
    tip_deflection_m: float
    stations: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    _y: np.ndarray | None = field(default=None, repr=False)
    _twist_deg: np.ndarray | None = field(default=None, repr=False)

    def twist_deg(self, y: float) -> float:
        """Nose-up twist [deg] at semispan station ``y`` [m]. Zero inboard of the clamp."""
        if self._y is None or self._twist_deg is None or len(self._y) == 0:
            return 0.0
        return float(np.interp(y, self._y, self._twist_deg))

    def to_dict(self) -> dict:
        return {"applied": self.applied, "CLa_rigid_per_rad": self.CLa_rigid, "CLa_flex_per_rad": self.CLa_flex,
                "CDi_rigid": self.CDi_rigid, "CDi_flex": self.CDi_flex, "K_ratio": self.K_ratio,
                "xac_w_mac": self.xac_w, "tip_twist_deg": self.tip_twist_deg,
                "tip_deflection_m": self.tip_deflection_m, "stations": self.stations, "notes": self.notes}


@dataclass
class StructuresL1:
    masses: dict
    deflections: dict
    elastic: ElasticCorrection | None
    notes: list[str] = field(default_factory=list)
    fuselage: dict = field(default_factory=dict)
    tails: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"masses": self.masses, "deflections": self.deflections,
                "elastic_correction": None if self.elastic is None else self.elastic.to_dict(),
                "fuselage": {k: v for k, v in self.fuselage.items() if k != "x"},
                "tails": self.tails, "notes": self.notes}


def _material(material: str | dict) -> dict:
    return MATERIALS[material] if isinstance(material, str) else material


def _radius(x, L: float, R: float) -> np.ndarray:
    """Equivalent body of revolution, not a loft. Breaks (x/L, R/Rmax): nose 0.45, cabin 1, tail 0.35."""
    xp = np.array([0.0, 0.12, 0.25, 0.62, 0.82, 1.0]) * L
    rp = np.array([0.45, 0.75, 1.0, 1.0, 0.62, 0.35]) * R
    return np.interp(np.asarray(x, float), xp, rp)


def _stations(L: float, extra) -> np.ndarray:
    x = np.linspace(0.0, L, 41)
    add = [float(v) for v in extra if v is not None and 0.0 <= float(v) <= L]
    if add:
        x = np.unique(np.concatenate([x, add]))
    return x


def _trap(y, f) -> float:
    return float(np.trapezoid(np.asarray(f, float), np.asarray(y, float)))


def _xac_fraction(wing, y, lift) -> float:
    """Lift-weighted quarter-chord as a fraction of MAC. Unswept c/4 line → 0.25."""
    y = np.asarray(y, float)
    lift = np.maximum(np.asarray(lift, float), 0.0)
    L = _trap(y, lift)
    if L <= 1e-9:
        return 0.25
    dx = (y - wing.y_mac) * math.tan(wing.sweep_c4)
    return 0.25 + _trap(y, lift * dx) / L / wing.mac


def raymer_fuselage_kg(config, W0_kg: float, Nz: float, q_cruise_Pa: float) -> float:
    """Raymer Eq. 15.49 [kg], unpressurised, same arguments as the component build-up."""
    fus, ht = config.fuselage, config.htail
    lb = raymer_ga_fuselage(fus.wetted_area() / FT ** 2, Nz, W0_kg / LB, ht.arm / FT, fus.length / FT,
                            fus.max_diameter / FT, q_cruise_Pa / PSF)
    return float(lb * LB)


def _uniform_tail(surface, lift_limit: float, material, nonopt: float):
    """One tail as a two-spar box. ``lift_limit`` is the limit load [N], whole surface.
    Uniform semispan load: M_root = L b / 8 (heavier than elliptic). Ultimate ×1.5 is inside the box sizer."""
    wing = surface.as_wing()
    b2 = wing.span / 2.0
    y = np.linspace(0.0, b2, 21)
    c = chord_at(wing, y)
    lift = np.full(y.shape, lift_limit / wing.span)          # per unit span, one side; 2 ∫ = L
    V = _cum_from_tip(y, lift)
    M = _cum_from_tip(y, V)
    xea = 0.5 * (wing.box.front_spar_xc + wing.box.rear_spar_xc)
    T = _cum_from_tip(y, lift * (xea - 0.25) * c)
    box = box_beam_sizing(wing, BeamLoads(y, V, M, T), material, _FS, nonopt)
    return box


def _integrate_beam(x, w_up, points) -> tuple[np.ndarray, np.ndarray]:
    """V, M from the nose. ``w_up`` [N/m] upward; point loads (x, F_up) added on the station they fall in."""
    x = np.asarray(x, float)
    w = np.asarray(w_up, float)
    V = np.zeros_like(x)
    M = np.zeros_like(x)
    pts = sorted((float(px), float(pf)) for px, pf in points)
    ip = 0
    for i in range(1, len(x)):
        V[i] = V[i - 1] + 0.5 * (w[i] + w[i - 1]) * (x[i] - x[i - 1])
        while ip < len(pts) and pts[ip][0] <= x[i] + 1e-9:
            if pts[ip][0] >= x[i - 1] - 1e-9:
                V[i] += pts[ip][1]
            ip += 1
        M[i] = M[i - 1] + 0.5 * (V[i] + V[i - 1]) * (x[i] - x[i - 1])
    return V, M


def _piece(x, lo, hi, value) -> np.ndarray:
    x = np.asarray(x, float)
    return np.where((x >= lo) & (x <= hi), value, 0.0)


def fuselage_beam(config, W0_kg: float, n_limit: float, q_VA: float, q_VC: float, material, nonopt: float,
                  *, x_wing: float | None = None, x_cg_flight: float | None = None, engine_mass_kg: float = 0.0,
                  gear=None, q_cruise: float = 0.0, landing_weight_fraction: float = 0.95,
                  gear_load_factor: float = 3.0, wing_lift_fraction: float = 2.0 / 3.0,
                  clmax_ht: float = _CLMAX_HT, clmax_vt: float = _CLMAX_VT) -> dict:
    """Size the fuselage shell. Returns masses, a station table and the limit-load cases.

    Design envelope (limit, then ×1.5 ultimate), per station, the max of:

    * horizontal-tail lift the surface can develop at VA (Raymer Eq. 12.15), reacted as a
      cantilever aft of the wing (Bruhn empennage load path);
    * equilibrium tail load at n_limit (Etkin) plus the 14 CFR 23.423(b) angular-acceleration
      increment — kept, and usually smaller than the attainable lift;
    * nose engine inertia n_limit W_engine between the engine and the wing;
    * landing: inertia and the two gear reactions (14 CFR 23.473 floors via :func:`adopted_factors`
      when a solved gear is not passed).

    14 CFR 23.427 gust and 23.441 rudder are not in this envelope (no gust-alleviation or
    hinge-moment model). The note says so. Vertical-tail torsion L z_cp is carried by the
    fuselage ahead of the fin. Unsymmetrical horizontal-tail torsion is omitted.
    """
    fus = config.fuselage
    L, R = fus.length, fus.max_diameter / 2.0
    m = _material(material)
    W = W0_kg * G0
    x_w = _X_WING_FRAC * L if x_wing is None else float(x_wing)
    x_w = min(max(x_w, 0.05 * L), 0.9 * L)
    x_ht = min(L, x_w + config.htail.arm)
    x_vt = min(L, x_w + config.vtail.arm)
    x_eng = _X_ENGINE_FRAC * L
    mac = config.wing.mac
    x_cg = (x_w - 0.10 * mac) if x_cg_flight is None else float(x_cg_flight)

    L_tail = surface_limit_lift(q_VA, config.htail.S, config.htail.as_wing().sweep_c4, clmax_ht)
    L_eq = equilibrium_tail_load(n_limit, W, x_cg, x_w, x_ht)
    Iyy = W0_kg * (_K_Y * L) ** 2
    # VA [m/s] from q = ½ ρ0 VA² (EAS). The regulation writes knots; the helper converts.
    V_VA = math.sqrt(2.0 * q_VA / RHO0) if q_VA > 0 else 0.0
    dL = angular_tail_increment(Iyy, checked_maneuver_alpha(n_limit, V_VA, nose_up=True), x_ht - x_cg)
    L_bal = abs(L_eq) + abs(dL)
    L_aft = max(L_tail, L_bal)

    ht = config.vtail.as_wing()
    L_fin = surface_limit_lift(q_VC, config.vtail.S, ht.sweep_c4, clmax_vt)
    z_cp = _Z_CP_FRAC * ht.span
    T_fin = L_fin * z_cp

    x = _stations(L, [x_w, x_ht, x_vt, x_eng])
    M_tail = np.abs(_piece(x, x_w, x_ht, 1.0) * L_aft * np.maximum(x_ht - x, 0.0))
    V_tail = np.abs(_piece(x, x_w, x_ht, L_aft))
    F_eng = n_limit * engine_mass_kg * G0
    M_eng = np.abs(_piece(x, x_eng, x_w, 1.0) * F_eng * np.maximum(x_w - x, 0.0))
    V_eng = np.abs(_piece(x, x_eng, x_w, F_eng))
    T_line = np.abs(_piece(x, 0.0, x_vt, T_fin))

    # Landing. Inertia centroid at the landing CG: uniform over [0, 2 x_cg] so the load does not
    # change sign (a straight line through a forward CG would). PRESSUPOSTO.
    if gear is not None and getattr(gear, "n_gear", None) and getattr(gear, "n_inertia", None):
        n_i, n_g = float(gear.n_inertia), float(gear.n_gear)
        kappa = float(gear.wing_lift_fraction or wing_lift_fraction)
        W_land = float(gear.landing_weight_kg or landing_weight_fraction * W0_kg) * G0
        xs = [v for v in (getattr(gear, "x_nose_m", None), getattr(gear, "x_main_m", None),
                          getattr(gear, "x_tail_m", None)) if v is not None]
        x_fwd, x_aft = (min(xs), max(xs)) if len(xs) >= 2 else (_X_NOSE_GEAR_FRAC * L, _X_MAIN_GEAR_FRAC * L)
    else:
        n_i, n_g = adopted_factors(gear_load_factor, wing_lift_fraction)
        kappa = wing_lift_fraction
        W_land = landing_weight_fraction * W
        x_fwd, x_aft = _X_NOSE_GEAR_FRAC * L, _X_MAIN_GEAR_FRAC * L
    x_cg_l = min(max(_X_CG_LAND_FRAC * L, 0.05 * L), 0.95 * L)
    span_i = min(L, 2.0 * x_cg_l)
    w_i = np.where(x <= span_i, -n_i * W_land / span_i, 0.0)
    L_w = kappa * W_land
    den = x_aft - x_fwd
    if abs(den) < 1e-6:
        R_aft, R_fwd = n_g * W_land, 0.0
    else:
        R_aft = (n_i * W_land * x_cg_l - L_w * x_w - n_g * W_land * x_fwd) / den
        R_fwd = n_g * W_land - R_aft
    V_l, M_l = _integrate_beam(x, w_i, [(x_fwd, R_fwd), (x_aft, R_aft), (x_w, L_w)])

    M_lim = np.maximum(np.maximum(M_tail, M_eng), np.abs(M_l))
    V_lim = np.maximum(np.maximum(V_tail, V_eng), np.abs(V_l))
    T_lim = T_line
    labels = np.array(["tail_VA"] * len(x), dtype=object)
    labels = np.where(M_eng >= M_tail, "engine", labels)
    labels = np.where(np.abs(M_l) >= np.maximum(M_tail, M_eng), "landing", labels)

    t_min = max(m["t_min_skin"], fus.frames.skin_thickness)
    E, G = m["E"], m.get("G", m["E"] / (2 * (1 + m["nu"])))
    R_x = _radius(x, L, R)
    t = np.empty_like(x)
    gamma = np.empty_like(x)
    for i in range(len(x)):
        sized = tube_thickness(_FS * M_lim[i], _FS * T_lim[i], _FS * V_lim[i], float(R_x[i]), E,
                               m["sigma_cap"], m["tau"], t_min)
        t[i], gamma[i] = sized["t"], sized["gamma"]

    rho = m["rho"]
    skin = _trap(x, rho * 2 * math.pi * R_x * t)
    n_long = int(fus.frames.n_longerons)
    longerons = n_long * m["cap_min_area"] * L * rho
    x_fr = np.arange(0.0, L + 1e-9, fus.frames.frame_pitch)
    if len(x_fr) == 0 or x_fr[-1] < L - 1e-6:
        x_fr = np.append(x_fr, L)
    R_fr = _radius(x_fr, L, R)
    frames = float(np.sum(rho * _FRAME_FLANGE_M * m["t_min_web"] * 2 * math.pi * R_fr))
    shell = skin + longerons + frames
    nonopt_mass = (nonopt - 1.0) * shell
    # Floor over the cabin (0.15 L → 0.15 L + 0.45 L). Bulkheads: firewall and tail closure,
    # area π Rmax², thickness = minimum web (Torenbeek App. D lists bulkheads; gauge is the minimum).
    x_floor0 = 0.15 * L
    floor = rho * (_FLOOR_LENGTH_FRAC * L) * (_FLOOR_WIDTH_FRAC * fus.max_diameter) * m["t_min_skin"]
    bulk = _N_BULKHEADS * rho * math.pi * R ** 2 * m["t_min_web"]
    total = nonopt * shell + floor + bulk

    dm = rho * 2 * math.pi * R_x * t
    skin_m = _trap(x, dm)
    x_skin = _trap(x, x * dm) / skin_m if skin_m > 0 else 0.5 * L
    x_frames = float(np.sum(x_fr * R_fr) / np.sum(R_fr)) if np.sum(R_fr) else 0.5 * L
    x_floor = x_floor0 + 0.5 * _FLOOR_LENGTH_FRAC * L
    x_bulk = 0.5 * (x_eng + L)
    m_fr = frames
    cg = (skin * x_skin + longerons * 0.5 * L + m_fr * x_frames + floor * x_floor + bulk * x_bulk) / total

    # Tail bending relative to the wing, limit attainable load, on the as-built EI.
    aft = x >= x_w
    s = x[aft] - x_w
    if len(s) >= 2:
        I_aft = np.array([thin_circular_tube(float(ri), float(ti))["I"] for ri, ti in zip(R_x[aft], t[aft])])
        J_aft = np.array([thin_circular_tube(float(ri), float(ti))["J"] for ri, ti in zip(R_x[aft], t[aft])])
        M_aft = L_tail * np.maximum(x_ht - x[aft], 0.0)
        resp = cantilever_response(s, M_aft, np.full_like(s, T_fin), E * I_aft, G * J_aft, 0.0)
        tail_defl = float(resp["deflection_m"][-1])
        fin_twist = float(np.degrees(resp["twist_rad"][-1]))
    else:
        tail_defl, fin_twist = 0.0, 0.0

    i_max = int(np.argmax(M_lim))
    notes = [
        "Fuselagem: casca circular não reforçada, γ de NASA SP-8007 (1968) na encurvadura clássica "
        "0,605 E t/R (Timoshenko & Gere, ν = 0,3). Longarinas só com área mínima (o momento já está no revestimento).",
        f"Piso { _FLOOR_LENGTH_FRAC:.2f} L × { _FLOOR_WIDTH_FRAC:.2f} D, duas anteparas π R² à espessura mínima "
        "(Torenbeek 1982 App. D lista estes itens; a espessura é a mínima do material — PRESSUPOSTO). "
        f"Fator não-ótimo {nonopt:g} só em revestimento + longarinas + cavernas.",
        "Envelope de manobra: sustentação atingível do estabilizador a VA (Raymer 12.15), equilíbrio + 23.423(b), "
        "inércia do motor e aterragem (23.473). 23.427 (rajada) e 23.441 (leme) não estão modelados. "
        "Torção assimétrica do estabilizador omitida.",
        (f"Estação da asa neste fecho: x = {x_w:.2f} m "
         f"(pressuposto {_X_WING_FRAC:.2f} L; o estágio de estabilidade ainda não colocou a asa)."
         if x_wing is None else
         f"Estação da asa neste fecho: x = {x_w:.2f} m "
         "(centro aerodinâmico: ápice colocado pela estabilidade + quarto da corda média)."),
    ]
    if "E_cap" in m:
        notes.append("γ de SP-8007 é uma correlação de cilindros de alumínio. Em CFRP entra como PRESSUPOSTO "
                     "conservativo, não como ensaio do laminado.")
    return {
        "mass_kg": float(total), "skin_kg": float(skin), "longerons_kg": float(longerons),
        "frames_kg": float(frames), "floor_kg": float(floor), "bulkheads_kg": float(bulk),
        "nonoptimum_kg": float(nonopt_mass), "cg_m": float(cg), "x": x, "t_m": t, "R_m": R_x,
        "M_limit_Nm": M_lim, "V_limit_N": V_lim, "T_limit_Nm": T_lim, "governing": str(labels[i_max]),
        "M_limit_max_Nm": float(M_lim[i_max]),
        "t_max_m": float(t.max()), "gamma_at_t_max": float(gamma[int(np.argmax(t))]),
        "L_tail_VA_N": float(L_tail), "L_equilibrium_N": float(L_eq), "dL_23_423_N": float(dL),
        "L_fin_N": float(L_fin), "T_fin_Nm": float(T_fin), "L_tail_design_N": float(L_aft),
        "x_engine_m": float(x_eng), "F_engine_limit_N": float(F_eng), "x_gear_fwd_m": float(x_fwd),
        "x_gear_aft_m": float(x_aft), "W_landing_N": float(W_land), "wing_lift_landing_N": float(L_w),
        "x_wing_m": float(x_w), "x_ht_m": float(x_ht), "x_vt_m": float(x_vt),
        "tail_deflection_m": tail_defl, "fin_twist_deg": fin_twist,
        "landing_reactions_N": {"forward": float(R_fwd), "aft": float(R_aft), "n_inertia": float(n_i),
                                "n_gear": float(n_g)},
        "notes": notes,
    }


def wing_beam_response(wing, box, beam, k_EI: float = 1.0, k_GJ: float = 1.0, y_clamp: float = 0.0) -> dict | None:
    """Cantilever on the sized wing EI/GJ. Positive deflection is tip up; positive twist is nose up."""
    if box is None or box.EI is None or box.GJ is None or beam is None:
        return None
    y = np.asarray(box.y, float)
    EI = np.maximum(k_EI * np.asarray(box.EI, float), 1.0)
    GJ = np.maximum(k_GJ * np.asarray(box.GJ, float), 1.0)
    # Beam stations follow the load grid. Interpolate stiffness onto them when the two grids differ.
    yb = np.asarray(beam.y, float)
    if len(yb) != len(y) or np.max(np.abs(yb - y)) > 1e-9:
        EI = np.interp(yb, y, EI)
        GJ = np.interp(yb, y, GJ)
        y = yb
    resp = cantilever_response(y, beam.moment, beam.torque, EI, GJ, y_clamp)
    n = len(y)
    step = max(1, n // 8)
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return {"y": y, "deflection_m": resp["deflection_m"], "twist_rad": resp["twist_rad"],
            "tip_m": float(resp["deflection_m"][-1]), "tip_twist_deg": float(np.degrees(resp["twist_rad"][-1])),
            "stations": [{"y_m": float(y[i]), "deflection_m": float(resp["deflection_m"][i]),
                          "twist_deg": float(np.degrees(resp["twist_rad"][i]))} for i in idx]}


def wing_elastic(wing, box, q: float, CL: float, *, k_EI: float = 1.0, k_GJ: float = 1.0, cm0: float = 0.0,
                 y_clamp: float = 0.0, n: int = 16) -> ElasticCorrection:
    """Glauert lifting line with elastic twist at dynamic pressure ``q``, trimmed to ``CL``.

    θ(y) = ∫ T/GJ from the clamp, T' = ℓ (x_sc − 0.25) c + q c² cm0 (Megson; same split as
    :func:`structures.shear_moment_diagram`). Fixed point, 8 iterations, stop at |Δθ| < 1e-6.
    CLα_flex is dCL/dα with the twist free to follow the load (a frozen twist would hide the wash-in).
    """
    from .wingbox.aero import LiftingLine

    notes = ["Linha sustentadora de Glauert (Anderson §5.3) com a₀ = 0,95·2π (Raymer §12.4.1) e α_L0 = 0. "
             "A torção elástica entra no ângulo local. Sem NeuralFoil neste caminho."]
    if box is None or box.GJ is None or q <= 0 or CL <= 0:
        notes.append("Sem caixão ou sem q/CL: correção elástica não calculada.")
        return ElasticCorrection(False, math.nan, math.nan, math.nan, math.nan, math.nan, 0.25, 0.0, 0.0,
                                 notes=notes)
    ll = LiftingLine(wing.span, lambda yy: chord_at(wing, yy), n=n)
    a0 = np.full(ll.n, _A0_OVER_2PI * 2 * math.pi)
    aL0 = np.zeros(ll.n)
    y = np.asarray(box.y, float)
    GJ = np.maximum(k_GJ * np.asarray(box.GJ, float), 1.0)
    EI = np.maximum(k_EI * np.asarray(box.EI, float), 1.0)
    xsc = box.details.get("x_sc_c")
    if xsc is None:
        xsc = 0.5 * (wing.box.front_spar_xc + wing.box.rear_spar_xc)
    xsc = np.asarray(xsc, float)
    c = chord_at(wing, y)
    order = np.argsort(ll.y)

    def solve(CL_target, update_twist, th_e):
        CDi = math.nan
        lift = np.zeros_like(y)
        theta = np.zeros_like(y)
        for _ in range(8):
            _al, _A, _CL, CDi, ccl = ll.trim(CL_target, th_e, a0, aL0)
            ccl_y = np.interp(y, ll.y[order], ccl[order])
            lift = q * ccl_y
            if not update_twist:
                break
            T = _cum_from_tip(y, lift * (xsc - 0.25) * c + q * c ** 2 * cm0)
            theta = cantilever_response(y, np.zeros_like(y), T, EI, GJ, y_clamp)["twist_rad"]
            new = np.interp(ll.y, y, theta)
            if np.max(np.abs(new - th_e)) < 1e-6:
                th_e = new
                break
            th_e = new
        al, A, CLr, CDi, ccl = ll.trim(CL_target, th_e, a0, aL0)
        return al, CDi, th_e, theta, lift

    al_r, CDi_r, _, _, lift_r = solve(CL, False, np.zeros(ll.n))
    A_unit = ll.solve(np.ones(ll.n), a0)
    CLa_r = math.pi * ll.AR * float(A_unit[0])
    al, CDi, th_e, theta, lift = solve(CL, True, np.zeros(ll.n))
    dCL = max(0.05, 0.05 * CL)
    al2, _, _, _, _ = solve(CL + dCL, True, th_e.copy())
    CLa_f = dCL / (al2 - al) if abs(al2 - al) > 1e-8 else CLa_r
    tip = float(np.degrees(theta[-1]))
    if not math.isfinite(CDi) or CDi_r <= 0 or abs(tip) > 25.0:
        notes.append("Ponto fixo da torção fora do intervalo físico (|θ_ponta| > 25° ou CDi inválido): "
                     "K não é aplicado.")
        ratio = math.nan
    else:
        ratio = float(CDi / CDi_r)
    xac = _xac_fraction(wing, y, lift)
    # Cruise bending of this lift, for the reported cruise deflection (the sizing beam is separate).
    M = _cum_from_tip(y, _cum_from_tip(y, lift))
    bend = cantilever_response(y, M, np.zeros_like(y), EI, GJ, y_clamp)
    nsta = len(y)
    step = max(1, nsta // 8)
    idx = list(range(0, nsta, step))
    if idx[-1] != nsta - 1:
        idx.append(nsta - 1)
    stations = [{"y_m": float(y[i]), "twist_deg": float(np.degrees(theta[i])),
                 "deflection_m": float(bend["deflection_m"][i])} for i in idx]
    corr = ElasticCorrection(False, float(CLa_r), float(CLa_f), float(CDi_r), float(CDi), ratio, float(xac),
                             tip, float(bend["deflection_m"][-1]), stations, notes, y, np.degrees(theta))
    return corr


def _structural_cg(fus_cg, fus_m, x_wing, wing_m, x_ht, ht_m, x_vt, vt_m) -> float | None:
    parts = [(fus_m, fus_cg), (wing_m or 0.0, x_wing), (ht_m, x_ht), (vt_m, x_vt)]
    m = sum(p[0] for p in parts)
    if m <= 0:
        return None
    return float(sum(p[0] * p[1] for p in parts) / m)


def analyse(config, W0_kg: float, *, structures=None, q_cruise: float | None = None, V_cruise: float | None = None,
            altitude: float = 0.0, material: str | dict = "al2024_t3", nonoptimum: float = 1.25,
            k_EI: float = 1.0, k_GJ: float = 1.0, cm0: float = 0.0, CL_cruise: float | None = None,
            engine_mass_kg: float = 0.0, gear=None, CLmax: float = 1.6, CLalpha: float = 5.0,
            regulation: str = "cs_23", category: str = "normal", n_limit: float | None = None,
            x_wing: float | None = None, elastic: bool = True, landing_weight_fraction: float = 0.95,
            gear_load_factor: float = 3.0, wing_lift_fraction: float = 2.0 / 3.0) -> StructuresL1:
    """Fuselage, tails, wing deflection and (if ``elastic``) the cruise lifting-line correction.

    ``structures`` is a :class:`structures.StructuresResult` when the wing box already exists.
    The wing mass reported here is that box; this function does not replace the Raymer wing weight.
    """
    at = isa(altitude)
    V_eas = None
    if V_cruise is not None:
        V_eas = V_cruise * math.sqrt(at.sigma)
    if structures is not None:
        vn = structures.vn
        q_VA = 0.5 * RHO0 * vn.VA ** 2
        q_VC = 0.5 * RHO0 * vn.VC ** 2
        n_lim = vn.n_limit_pos
        box, beam = structures.box, structures.beam
        wing_mass = structures.box.mass
    else:
        V_eas = V_eas if V_eas is not None else 50.0
        vn = v_n_diagram(W0_kg, config.wing.S, CLmax, CLalpha, config.wing.mac, V_eas, category, regulation,
                         altitude, n_pos=n_limit)
        q_VA = 0.5 * RHO0 * vn.VA ** 2
        q_VC = 0.5 * RHO0 * vn.VC ** 2
        n_lim = vn.n_limit_pos
        box = beam = None
        wing_mass = None
    if q_cruise is None:
        q_cruise = 0.5 * at.rho * (V_cruise or V_eas or 50.0) ** 2
    if CL_cruise is None and q_cruise > 0:
        CL_cruise = W0_kg * G0 / (q_cruise * config.wing.S)

    fus = fuselage_beam(config, W0_kg, n_lim, q_VA, q_VC, material, nonoptimum, x_wing=x_wing,
                        engine_mass_kg=engine_mass_kg, gear=gear, q_cruise=q_cruise,
                        landing_weight_fraction=landing_weight_fraction, gear_load_factor=gear_load_factor,
                        wing_lift_fraction=wing_lift_fraction)
    ht = _uniform_tail(config.htail, surface_limit_lift(q_VA, config.htail.S, config.htail.as_wing().sweep_c4,
                                                        _CLMAX_HT), material, nonoptimum)
    vt = _uniform_tail(config.vtail, surface_limit_lift(q_VC, config.vtail.S, config.vtail.as_wing().sweep_c4,
                                                        _CLMAX_VT), material, nonoptimum)
    Nz = _FS * n_lim
    ray = raymer_fuselage_kg(config, W0_kg, Nz, q_cruise)
    ratio = fus["mass_kg"] / ray if ray else None
    y_clamp = config.fuselage.max_diameter / 2.0
    wing_resp = wing_beam_response(config.wing, box, beam, k_EI, k_GJ, y_clamp) if box is not None else None
    corr = None
    if elastic and box is not None and CL_cruise and CL_cruise > 0:
        corr = wing_elastic(config.wing, box, q_cruise, CL_cruise, k_EI=k_EI, k_GJ=k_GJ, cm0=cm0, y_clamp=y_clamp)
    cg = _structural_cg(fus["cg_m"], fus["mass_kg"], fus["x_wing_m"], wing_mass, fus["x_ht_m"], ht.mass,
                        fus["x_vt_m"], vt.mass)
    masses = {"wing_box_kg": None if wing_mass is None else float(wing_mass), "fuselage_kg": fus["mass_kg"],
              "htail_kg": float(ht.mass), "vtail_kg": float(vt.mass), "fuselage_raymer_kg": float(ray),
              "fuselage_over_raymer": None if ratio is None else float(ratio), "structural_cg_m": cg,
              "fuselage_breakdown_kg": {k: fus[k] for k in ("skin_kg", "longerons_kg", "frames_kg", "floor_kg",
                                                           "bulkheads_kg", "nonoptimum_kg")}}
    deflections = {"k_EI": float(k_EI), "k_GJ": float(k_GJ), "wing_y_clamp_m": float(y_clamp),
                   "fuselage_tail_m": fus["tail_deflection_m"], "fuselage_fin_twist_deg": fus["fin_twist_deg"]}
    if wing_resp is not None:
        deflections.update({"wing_tip_m": wing_resp["tip_m"], "wing_tip_twist_deg": wing_resp["tip_twist_deg"],
                            "wing_stations": wing_resp["stations"]})
    if corr is not None and math.isfinite(corr.tip_twist_deg):
        deflections["cruise_tip_twist_deg"] = corr.tip_twist_deg
        deflections["cruise_tip_m"] = corr.tip_deflection_m
    notes = list(fus["notes"])
    notes.append("Empenagens: caixão de duas longarinas (Megson), carga em envergadura uniforme — PRESSUPOSTO, "
                 "M_raiz = L b/8 por semienvergadura, mais pesado em flexão do que uma elipse. "
                 f"c_lmax de secção {_CLMAX_HT:g} (estabilizador) e {_CLMAX_VT:g} (deriva), não o da asa; "
                 "CLmax pela Eq. 12.15 de Raymer.")
    notes.append("k_EI e k_GJ multiplicam EI e GJ da asa (razão viga/BoxFEM). A fuselagem não os usa.")
    if ratio is not None:
        notes.append(f"Massa da fuselagem L1 / Raymer Eq. 15.49 = {ratio:.2f}. "
                     "A regressão de Raymer inclui portas, janelas e suportes que esta casca não tem.")
    tails = {"htail_kg": float(ht.mass), "vtail_kg": float(vt.mass),
             "htail_limit_lift_N": float(surface_limit_lift(q_VA, config.htail.S, config.htail.as_wing().sweep_c4,
                                                           _CLMAX_HT)),
             "vtail_limit_lift_N": float(surface_limit_lift(q_VC, config.vtail.S, config.vtail.as_wing().sweep_c4,
                                                           _CLMAX_VT))}
    fus_out = {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in fus.items() if k != "notes"}
    return StructuresL1(masses, deflections, corr, notes, fus_out, tails)


def apply_beam_masses(breakdown, masses: dict) -> None:
    """Replace fuselage and tail WeightItem masses. The wing stays on ``wing_method``."""
    ray = masses.get("fuselage_raymer_kg") or 0.0
    methods = {
        "fuselage": f"viga-tubo L1 (NASA SP-8007 / Megson) {masses['fuselage_kg']:.2f} kg; "
                    f"Raymer Eq. 15.49 teria {ray:.2f} kg",
        "htail": f"caixão L1 da empenagem horizontal (carga uniforme, Megson) {masses['htail_kg']:.2f} kg",
        "vtail": f"caixão L1 da empenagem vertical (carga uniforme, Megson) {masses['vtail_kg']:.2f} kg",
    }
    keys = {"fuselage": "fuselage_kg", "htail": "htail_kg", "vtail": "vtail_kg"}
    for it in breakdown.items:
        key = keys.get(it.key)
        if key and key in masses and math.isfinite(masses[key]):
            it.mass = float(masses[key])
            it.method = methods[it.key]


def component_masses(config, W0_kg: float, V_cruise: float, CLmax: float, CLalpha: float, q_cruise: float,
                     **kwargs) -> dict:
    """Fuselage and tail masses for the weight loop. No lifting line."""
    return analyse(config, W0_kg, q_cruise=q_cruise, V_cruise=V_cruise, CLmax=CLmax, CLalpha=CLalpha,
                   elastic=False, **kwargs).masses


def mass_kwargs_from_spec(spec, uas: bool) -> dict:
    """Material, regulation and gear factors shared by the weight loop and :func:`analyse_design`."""
    from .weights_detailed import _merge_opts

    A = spec.assumptions
    sa = A["structures"]
    wo = _merge_opts(A["weights"].get("components"))
    mat = sa.get("material", "auto")
    if mat == "auto":
        mat = "cfrp" if wo.get("material") == "composite" else "al2024_t3"
    reg = sa.get("regulation", "auto")
    if reg == "auto":
        reg = "stanag_4671" if uas else "cs_23"
    return {"material": mat, "nonoptimum": sa.get("nonoptimum_factor", 1.25), "regulation": reg,
            "category": wo.get("structural_category", "normal"), "n_limit": wo.get("limit_load_factor"),
            "landing_weight_fraction": wo.get("landing_weight_fraction", 0.95),
            "gear_load_factor": wo.get("gear_load_factor", 3.0),
            "wing_lift_fraction": (A.get("landing_gear") or {}).get("wing_lift_fraction", 2.0 / 3.0)}


def analyse_design(res, k_EI: float = 1.0, k_GJ: float = 1.0, elastic: bool = True, x_wing: float | None = None,
                   gear=None) -> StructuresL1:
    """:func:`analyse` from a sized :class:`~acdt.domains.aircraft.sizing.DesignResult`."""
    from .systems_integration import is_uas

    spec = res.spec
    kw = mass_kwargs_from_spec(spec, is_uas(spec))
    eng = 0.0
    if res.weights is not None:
        for it in res.weights.items:
            if it.key in ("engine_installed", "motor_esc"):
                eng = it.mass
                break
    cm0 = res.lowfi.cm0 if getattr(res, "lowfi", None) is not None else 0.0
    return analyse(res.config, res.sizing.W0, structures=res.structures, q_cruise=None, V_cruise=res.cruise_speed,
                   altitude=res.cruise_altitude, k_EI=k_EI, k_GJ=k_GJ, cm0=cm0, engine_mass_kg=eng,
                   gear=gear, CLmax=res.highlift.CLmax_clean, CLalpha=res.CLalpha, x_wing=x_wing,
                   elastic=elastic, **kw)
