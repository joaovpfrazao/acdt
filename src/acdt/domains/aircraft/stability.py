"""Fase 2 — estabilidade estática e controlo (baixa fidelidade).

Methods (all classical, cited):

* **Neutral point** (stick-fixed), Raymer 6th ed. Ch. 16 (Eq. 16.9 form) / Nelson,
  *Flight Stability and Automatic Control*, 2nd ed., Ch. 2:
  x̄_np = [CLα_w x̄_ac,wb + η_h (S_h/S) CLα_h (1 − dε/dα) x̄_ac,h] / [CLα_w + η_h (S_h/S) CLα_h (1 − dε/dα)]
  with downwash dε/dα = 2 CLα_w/(π A) (elliptic-wing estimate, Nelson Ch. 2; Raymer Sec. 16.3),
  η_h = 0.9 (Raymer Sec. 16.3 typical) and the fuselage a.c. shift
  Δx̄_ac,f = −(1.8/CLα_w) · b_f h_f l_fn/(S c̄) (Torenbeek 1982, App. E).
  Cross-checked against the AVL neutral point (vortex lattice, no fuselage).
* **Static margin** SM = x̄_np − x̄_cg for every loading case of the **CG envelope**, built
  from the component weight breakdown. Structure stations are Roskam, *Airplane Design*
  Part V, Ch. 8 / Table 8.1 typical locations (ASSUMPTIONS). Useful load is not in that
  table. Until the mission sets stations, crew, payload and battery use the ``balance``
  reference: the CG of the fixed mass (Raymer 2018 Sec. 15.1, x_cg = Σ m x / Σ m). An item
  placed there does not move that CG, which is the layout station that does not widen the
  loading diagram. A UAV with zero crew mass has no crew item. Wing fuel stays at 30 % MAC.
  Override in ``assumptions.stability.stations``. A ``firewall`` reference is inches aft of
  the POH firewall datum.
* **Wing placement**: the wing is moved along the fuselage until the most-aft CG has the
  target static margin (Raymer Ch. 16 "wing is positioned to give the desired static margin";
  target is a designer ASSUMPTION, default 0.10).
* **Tail volume** check against Raymer Table 6.4 (the class value used to size the tails).
* **Control derivatives**: flap effectiveness τ from thin-airfoil theory,
  τ = 1 − (θ_f − sin θ_f)/π, cos θ_f = 2 c_f/c − 1 (Glauert); elevator
  CLδe = η_h (S_h/S) CLα_h τ_e, Cmδe = −η_h V̄_h CLα_h τ_e (Nelson Ch. 2); aileron
  Clδa = (2 CLα_w τ_a /(S b)) ∫ c y dy (Nelson Ch. 5 strip integration); rudder
  Cnδr = −η_v V̄_v CLα_v τ_r (Nelson Ch. 2). Cross-checked against AVL control derivatives.
* **Trim** at the forward end of the same CG range the scissor plot uses (the smallest x̄ of the
  loading cases): δe = −(Cm0 + (x̄_cg − x̄_np) CL)/Cmδe, wing Cm0 =
  cm0 A cos²Λ/(A + 2 cos Λ) (Raymer Eq. 16.13, DATCOM), at clean CLmax and in cruise; |δe| ≤ 25°
  (ASSUMPTION). The operational forward limit and the scissor control line use the same equation at
  the more-aft of that clean case and the full-flap flare (landing CLmax, fuselage Cm0, flap moment),
  and they test that same (x̄_fwd, x̄_aft). A plain or split flap uses Glauert's b_C. A slotted flap
  uses the USAF DATCOM Sec. 6.1.2.1 center of pressure (44 % of the extended chord) on Raymer's
  ΔCLmax. In the flare only, the tail lift slope is multiplied by Torenbeek's induced-angle ground
  effect (Phillips & Hunsaker 2013, Eq. 4). CLmax is not raised, and dε/dα inside the neutral point
  is not reduced: that downwash change is the rotation penalty, not a flare relief.

Phase 3 (below): stability/control "scissor" plot (Torenbeek 1982 Ch. 9), dynamic modes from AVL derivatives
(Nelson 1998 Ch. 4–5; Etkin & Reid 1996) with component-summation inertias, and handling-quality levels per
MIL-F-8785C (Class I; piloted-aircraft standard — indicative for UAVs).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


from .aero.avl import wing_x_ac
from .aero.lift import HighLiftDevice, delta_clmax_flap, lift_curve_slope

ETA_H = 0.9

# Component CG stations. Structure follows Roskam Part V Table 8.1 typical locations.
# 'L' = fraction of fuselage length from the nose; 'MAC' = fraction of the wing MAC aft of the MAC LE;
# 'tail' = 40 % of the tail MAC; 'firewall' = inches aft of the firewall (POH datum), which needs
# stability.firewall_x_m, firewall_fraction, or firewall_from_engine.
# Useful load is not in Table 8.1. ``balance`` means the CG of the fixed mass (Raymer 2018
# Sec. 15.1: the layout sum x = Σ m x / Σ m). A variable item placed there does not move that
# CG, so it does not widen the diagram. Wing fuel stays at 30 % MAC (the tank is in the wing).
# A mission station replaces any of these.
DEFAULT_STATIONS = {
    "wing": ("MAC", 0.40), "htail": ("htail", 0.40), "vtail": ("vtail", 0.40), "fuselage": ("L", 0.42),
    "main_gear": ("MAC", 0.55), "nose_gear": ("L", 0.10), "engine_installed": ("L", 0.08),
    "motor_esc": ("L", 0.04), "propeller": ("L", 0.0), "fuel_system": ("MAC", 0.30),
    "flight_controls": ("L", 0.50), "servos": ("MAC", 0.60), "hydraulics": ("L", 0.30),
    "avionics": ("L", 0.25), "electrical": ("L", 0.25), "harness": ("L", 0.35), "air_conditioning": ("L", 0.25),
    "furnishings": ("MAC", 0.10), "growth": ("L", 0.42), "user_items": ("L", 0.40),
    "crew": ("balance", 0.0), "payload": ("balance", 0.0), "fuel": ("MAC", 0.30), "battery": ("balance", 0.0),
}

INCH = 0.0254


@dataclass
class LoadingCase:
    name: str
    mass: float
    x_cg: float       # from fuselage nose [m]
    xbar_cg: float    # fraction of MAC (from MAC LE)
    SM: float


@dataclass
class StabilityResult:
    x_wing_apex: float            # wing root LE from the nose [m]
    x_mac_le: float
    mac: float
    xbar_np: float                # handbook (with fuselage), fraction of MAC
    xbar_np_no_fus: float
    xbar_np_avl: float | None
    dx_fus: float
    deps_dalpha: float
    CLa_w: float
    CLa_h: float
    Vh: float
    Vv: float
    Vh_class: float | None
    Vv_class: float | None
    cases: list[LoadingCase]
    controls: dict                # handbook & AVL control derivatives
    trim: dict
    target_SM: float
    placement: str
    stations: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def SM_fwd(self) -> float:
        return max(c.SM for c in self.cases)

    @property
    def SM_aft(self) -> float:
        return min(c.SM for c in self.cases)

    @property
    def cg_range_mac(self):
        return min(c.xbar_cg for c in self.cases), max(c.xbar_cg for c in self.cases)

    def summary(self) -> dict:
        return {"x_wing_apex_m": self.x_wing_apex, "placement": self.placement, "xbar_np": self.xbar_np,
                "xbar_np_no_fuselage": self.xbar_np_no_fus, "xbar_np_avl": self.xbar_np_avl,
                "fuselage_ac_shift": self.dx_fus, "deps_dalpha": self.deps_dalpha, "SM_fwd": self.SM_fwd,
                "SM_aft": self.SM_aft, "cg_range_mac": self.cg_range_mac, "Vh": self.Vh, "Vv": self.Vv,
                "Vh_class": self.Vh_class, "Vv_class": self.Vv_class, "controls": self.controls, "trim": self.trim,
                "cases": [vars(c) for c in self.cases], "notes": self.notes}


def flap_effectiveness(cf_c: float) -> float:
    """Thin-airfoil flap effectiveness τ = dα0/dδ (Glauert): τ = 1 − (θf − sin θf)/π."""
    th = math.acos(2 * cf_c - 1)
    return 1 - (th - math.sin(th)) / math.pi


def wing_cm0(cm0_airfoil: float, aspect_ratio: float, sweep_c4: float) -> float:
    """Raymer Eq. 16.13 (DATCOM): Cm0 = cm0 · A cos²Λ / (A + 2 cos Λ)."""
    c = math.cos(sweep_c4)
    return cm0_airfoil * (aspect_ratio * c * c / (aspect_ratio + 2 * c))


# Lamb's apparent-mass factor k2−k1 for a prolate spheroid, as tabulated by Tuckerman,
# NACA Report 139 (1923), "Notes on Aerodynamic Forces on Airship Hulls", supplementary table.
# Pairs are (L/D, k2−k1). The sphere is 0; the table ends at 9.97 (0.939). The slender limit
# is 1, which is not a finite row, so a finer body keeps the last published value.
_LAMB_K2_MINUS_K1 = (
    (1.00, 0.000), (1.50, 0.316), (2.00, 0.493), (2.51, 0.607), (2.99, 0.681),
    (3.99, 0.778), (4.99, 0.836), (6.01, 0.873), (6.97, 0.897), (8.01, 0.916),
    (9.02, 0.930), (9.97, 0.939),
)


def lamb_k2_minus_k1(fineness: float) -> float:
    """k2−k1 interpolated on Tuckerman's reprint of Lamb's ellipsoid table (NACA Report 139)."""
    rows = _LAMB_K2_MINUS_K1
    if fineness <= rows[0][0]:
        return rows[0][1]
    if fineness >= rows[-1][0]:
        return rows[-1][1]
    for (x0, y0), (x1, y1) in zip(rows, rows[1:]):
        if fineness <= x1:
            return y0 + (fineness - x0) / (x1 - x0) * (y1 - y0)
    return rows[-1][1]


def fuselage_cm0(fineness: float, length: float, diameter: float, wing_area: float, mac: float,
                 alpha0_deg: float, incidence_deg: float = 0.0) -> float:
    """Multhopp fuselage moment at wing zero lift (Nelson, *Flight Stability*, 1998, Ch. 2).

    Cm0,f = (k2−k1) / (36.5 S c̄) · ∫ w_f² (α0w + i_f) dx, with the angles in degrees.
    The 36.5 is the textbook factor that lets α be written in degrees. k2−k1 is Lamb's factor.
    The integral is taken at constant width equal to the maximum diameter (PRESSUPOSTO: the
    parametric fuselage is a body of revolution, Torenbeek App. F, and the nose and tail are
    not segmented, so this overstates |Cm0,f|).
    """
    if wing_area <= 0 or mac <= 0 or length <= 0 or diameter <= 0:
        return 0.0
    k = lamb_k2_minus_k1(fineness)
    return k * diameter ** 2 * length * (alpha0_deg + incidence_deg) / (36.5 * wing_area * mac)


def flap_cm_increment(cf_c: float, delta_deg: float, area_ratio: float) -> float:
    """Wing Cm from a plain flap: (S_flapped/S) · b_C · δ.

    b_C = ∂cm_c/4/∂δ per radian (Glauert 1926). Taking the flapped chord as the MAC makes
    ∫ c² dy = c̄ S_f, which is exact only for a rectangular flapped wing (PRESSUPOSTO on a taper).
    """
    from .aeroelasticity import glauert_flap
    _, b_c = glauert_flap(cf_c)
    return area_ratio * b_c * math.radians(delta_deg)


# USAF Stability and Control DATCOM (1978), Sec. 6.1.2.1, Fig. 6.1.2.1-35a: slotted-flap
# incremental center of pressure lies between 41 and 47 % of the extended chord. The average
# used by the DATCOM is 44 %, with no dependence on cf/c.
DATCOM_SLOTTED_CP = 0.44
SLOTTED_FLAP_KINDS = frozenset({"slotted", "fowler", "double_slotted", "triple_slotted"})
# Section slope in lift.lift_curve_slope when the caller does not override it (η ≈ 0.95).
_SECTION_CLA = 0.95 * 2.0 * math.pi


def slotted_flap_cm(delta_cl: float, chord_extension: float) -> float:
    """ΔCm about the original quarter-chord for a slotted flap.

    USAF DATCOM 1978, Sec. 6.1.2.1: the incremental center of pressure is
    ``DATCOM_SLOTTED_CP`` of the extended chord. With the extension aft of a fixed
    leading edge, x_cp/c = 0.44 · (c'/c) on the original chord, so
    ΔCm = (0.25 − 0.44 c'/c) ΔCL. ``delta_cl`` is the three-dimensional increment
    (Raymer Eq. 12.21), which already carries S_flapped/S. It is not multiplied again.
    """
    return (0.25 - DATCOM_SLOTTED_CP * chord_extension) * delta_cl


def torenbeek_induced_ratio(height_over_span: float) -> float:
    """φ = (C_Di/C_L²)_h / (C_Di/C_L²)_∞ = 1 − exp[−2.48 (2h/b)^0.768].

    Torenbeek, *Synthesis of Subsonic Airplane Design*, 1982, as quoted by Phillips
    and Hunsaker, Journal of Aircraft, Vol. 50, No. 4, 2013, Eq. (4). At one lift
    coefficient this is also α_i in ground effect over α_i in free air. φ is 0 on
    the ground and 1 in free air.
    """
    if height_over_span <= 0.0:
        return 0.0
    return 1.0 - math.exp(-2.48 * (2.0 * height_over_span) ** 0.768)


def cla_ground_factor(aspect_ratio: float, height_over_span: float, a0: float = _SECTION_CLA) -> float:
    """Elliptic CLα in ground effect divided by the same CLα in free air.

    1/CLα = 1/a0 + φ/(π AR), with Oswald e = 1 (PRESSUPOSTO) and a0 the section
    slope of ``lift_curve_slope``. The ratio multiplies a free-air CLα. It does
    not replace the Helmbold slope used for the neutral point.
    """
    if aspect_ratio <= 0.0 or a0 <= 0.0:
        return 1.0
    phi = torenbeek_induced_ratio(height_over_span)

    def cla(p: float) -> float:
        return 1.0 / (1.0 / a0 + p / (math.pi * aspect_ratio))

    free = cla(1.0)
    return 1.0 if free <= 0.0 else cla(phi) / free


def _tail_height_m(res) -> tuple[float | None, str]:
    """Height of the tail aerodynamic centre: gear length plus half the fuselage diameter.

    PRESSUPOSTO, the same fuselage-axis height as ``landing_gear`` h_cg. A T-tail is
    not raised above that axis.
    """
    cfg = getattr(res, "config", None)
    fus = getattr(cfg, "fuselage", None) if cfg is not None else None
    if fus is None or float(getattr(fus, "max_diameter", 0.0) or 0.0) <= 0.0:
        return None, ""
    assumptions = getattr(getattr(res, "spec", None), "assumptions", None) or {}
    raw = ((assumptions.get("weights") or {}).get("components") or {}).get("main_gear_length_m")
    if raw is None:
        from .weights_detailed import DEFAULT_MAIN_GEAR_LENGTH_M
        length = DEFAULT_MAIN_GEAR_LENGTH_M
        src = f"omissão {length:.2f} m (PRESSUPOSTO, weights_detailed.DEFAULT_MAIN_GEAR_LENGTH_M)"
    else:
        length = float(raw)
        src = "weights.components.main_gear_length_m"
    return length + 0.5 * float(fus.max_diameter), src


def flare_tail_cla_scale(res, htail=None) -> tuple[float, str]:
    """Factor on the flare tail lift slope from Torenbeek's φ. 1 when there is no tail.

    ``htail`` defaults to the configuration tail. The scissor passes each trial tail
    because span, and therefore h/b, changes with S_h at constant aspect ratio.
    """
    cfg = getattr(res, "config", None)
    ht = htail if htail is not None else (getattr(cfg, "htail", None) if cfg is not None else None)
    if ht is None or float(getattr(ht, "S", 0.0) or 0.0) <= 0.0 or float(getattr(ht, "AR", 0.0) or 0.0) <= 0.0:
        return 1.0, (
            "Efeito de solo no CLα da cauda não aplicado neste passo: não há cauda horizontal. "
            "O fator de Hoerner e Borst do arrasto induzido não é um CLα.")
    h, length_src = _tail_height_m(res)
    span = math.sqrt(float(ht.AR) * float(ht.S))
    if h is None or h <= 0.0 or span <= 1e-9:
        return 1.0, "Efeito de solo no CLα da cauda não aplicado (altura ou envergadura nulas)."
    phi = torenbeek_induced_ratio(h / span)
    factor = cla_ground_factor(float(ht.AR), h / span)
    return factor, (
        f"Efeito de solo no flare: CLα da cauda × {factor:.3f} "
        f"(φ = {phi:.3f} = 1 − exp[−2.48 (2h/b)^0.768], Torenbeek 1982, citado por Phillips e Hunsaker, "
        f"Journal of Aircraft, Vol. 50, No. 4, 2013, Eq. (4); h/b = {h / span:.3f}, h = {h:.3f} m, "
        f"trem + 0.5 D, {length_src}; PRESSUPOSTO: o centro aerodinâmico da cauda está à altura do eixo "
        f"da fuselagem). 1/CLα = 1/a0 + φ/(π AR), a0 = 0.95·2π, e = 1 (PRESSUPOSTO). O quociente multiplica "
        f"o CLα livre e não substitui o declive de Helmbold. O CLmax não aumenta e o dε/dα do ponto neutro "
        f"não é reduzido: essa redução é a penalização de rotação, não um alívio do flare. "
        f"Na tesoura, φ repete-se em cada S_h/S porque a envergadura muda com a área. "
        f"O flare fica em efeito de solo só neste declive. "
        f"O fator de Hoerner e Borst não é usado como CLα.")


def control_forward_xbar(xbar_np: float, cm0: float, cm_de: float, elevator_max_deg: float,
                         cl: float) -> float | None:
    """Most-forward CG that trims at ``cl`` with the elevator at the nose-up stop.

    x̄ = x̄_np − (Cm0 + |Cmδe| δe_max) / CL (Nelson 1998, Ch. 2). ``cm_de`` is per radian.
    """
    if cl <= 1e-6 or abs(cm_de) < 1e-6:
        return None
    return xbar_np - (cm0 + abs(cm_de) * math.radians(elevator_max_deg)) / cl


def _section_alpha0_deg(res) -> float | None:
    lowfi = getattr(res, "lowfi", None)
    polar = getattr(lowfi, "polar_cruise", None) if lowfi is not None else None
    if polar is None or not hasattr(polar, "alpha0_deg"):
        return None
    try:
        alpha = float(polar.alpha0_deg)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return alpha if math.isfinite(alpha) else None


def forward_cg_terms(res) -> dict:
    """Cm0 pieces of the forward-limit trim. Landing CL is None when the result has no CLmax_landing.

    Flap deflection and chord ratio, if the mission does not set them, are the phase-9 defaults
    (30° and c_f/c = 0.25). Both are PRESSUPOSTO and are named as such in ``clauses``.
    """
    w = res.config.wing
    lowfi = getattr(res, "lowfi", None)
    if lowfi is not None:
        cm0_af, wing_src = float(lowfi.cm0), "cm0 do perfil"
    else:
        cm0_af, wing_src = -0.05, "cm0 = −0.05 (PRESSUPOSTO, o mesmo da estabilidade)"
    cm0_wing = wing_cm0(cm0_af, w.AR, w.sweep_c4)
    clauses = [f"Cm0 da asa = {cm0_wing:.4f} (Raymer Eq. 16.13, {wing_src})"]

    alpha0 = _section_alpha0_deg(res)
    if alpha0 is None:
        cm0_fus = 0.0
        clauses.append("Cm0 da fuselagem não entra (sem α0 do perfil)")
    else:
        fus = res.config.fuselage
        cm0_fus = fuselage_cm0(fus.fineness, fus.length, fus.max_diameter, w.S, w.mac, alpha0, 0.0)
        clauses.append(
            f"Cm0,f = {cm0_fus:.4f} entra no flare (Multhopp, Nelson 1998 Cap. 2; k2−k1 da tabela de Lamb em "
            f"Tuckerman, NACA Report 139; α0 = {alpha0:.2f}°. Largura constante igual a D e i_f = 0, "
            "PRESSUPOSTO — fuselagem de revolução, Torenbeek App. F, sem segmentar nariz e cauda)")

    assumptions = getattr(getattr(res, "spec", None), "assumptions", None) or {}
    aero = assumptions.get("aero") or {}
    stab = assumptions.get("stability") or {}
    flap = aero.get("flap") or {}
    if flap.get("landing_deg") is not None:
        delta, delta_src = float(flap["landing_deg"]), "aero.flap.landing_deg"
    elif stab.get("flap_landing_deg") is not None:
        delta, delta_src = float(stab["flap_landing_deg"]), "stability.flap_landing_deg"
    else:
        delta, delta_src = 30.0, ("PRESSUPOSTO, omissão de flightsim/controls.py — substituir em "
                                   "assumptions.aero.flap.landing_deg")
    if flap.get("cf_c") is not None:
        cf_c, cf_src = float(flap["cf_c"]), "aero.flap.cf_c"
    elif stab.get("flap_cf_c") is not None:
        cf_c, cf_src = float(stab["flap_cf_c"]), "stability.flap_cf_c"
    else:
        cf_c, cf_src = 0.25, ("PRESSUPOSTO, omissão de flightsim/controls.py — substituir em "
                              "assumptions.aero.flap.cf_c")
    cl_clean = float(res.highlift.CLmax_clean)
    cl_land = getattr(res.highlift, "CLmax_landing", None)
    if cl_land is not None:
        cl_land = float(cl_land)
        if not math.isfinite(cl_land) or cl_land <= 1e-6:
            cl_land = None

    area = flap.get("flapped_area_ratio")
    kind = str(flap.get("kind", "plain"))
    if area is None or float(area) <= 0 or (kind not in SLOTTED_FLAP_KINDS and not 0.0 < cf_c < 1.0):
        cm0_flap = 0.0
        clauses.append("ΔCm do flap não entra (sem área de flap ou sem c_f/c entre 0 e 1)")
    elif kind in SLOTTED_FLAP_KINDS:
        if "chord_extension" in flap and flap["chord_extension"] is not None:
            ext, ext_src = float(flap["chord_extension"]), "aero.flap.chord_extension"
        else:
            ext, ext_src = 1.0, "PRESSUPOSTO c'/c = 1 (sem extensão de corda; o bordo de ataque fica fixo)"
        if ext <= 0.0:
            cm0_flap = 0.0
            clauses.append("ΔCm do flap slotted não entra (c'/c ≤ 0).")
        else:
            dev = HighLiftDevice(kind, float(area), ext, float(flap.get("hinge_sweep", 0.0) or 0.0))
            dcl = delta_clmax_flap(dev)
            cm0_flap = slotted_flap_cm(dcl, ext)
            clauses.append(
                f"ΔCm do flap = {cm0_flap:.4f} entra no flare (USAF DATCOM 1978, Sec. 6.1.2.1, "
                f"Fig. 6.1.2.1-35a: centro de pressão incremental a 44 % da corda estendida, média de "
                f"41–47 %, independente de c_f/c). Tipo {kind}. c'/c = {ext:g} ({ext_src}). "
                f"ΔCm = (0.25 − 0.44 c'/c) ΔCL sobre a corda de origem, extensão para trás. "
                f"ΔCL = {dcl:.4f} é o de Raymer Eq. 12.21 (já com S_f/S = {float(area):.3f}); "
                f"não se multiplica outra vez por S_f/S. δ = {delta:g}° ({delta_src}) e "
                f"c_f/c = {cf_c:g} ({cf_src}) não entram neste centro de pressão.")
    else:
        cm0_flap = flap_cm_increment(cf_c, delta, float(area))
        plain = "" if kind == "plain" else (
            f" O tipo é {kind}; o módulo é o do flap simples de Glauert (PRESSUPOSTO).")
        clauses.append(
            f"ΔCm do flap = {cm0_flap:.4f} entra no flare (Glauert 1926, b_C·δ·S_f/S; δ = {delta:g}° ({delta_src}); "
            f"c_f/c = {cf_c:g} ({cf_src}); S_f/S = {float(area):.3f}; "
            "corda da parte com flap igual à CMA, PRESSUPOSTO)."
            f"{plain}")

    factor = 1.0
    if cl_land is None:
        clauses.append("Flare com flaps não calculado: o resultado não traz CLmax de aterragem.")
    else:
        factor, ge_clause = flare_tail_cla_scale(res)
        clauses.append(ge_clause)
    return {"cm0_wing": cm0_wing, "cm0_fuselage": cm0_fus, "cm0_flap": cm0_flap,
            "cm0_flare": cm0_wing + cm0_fus + cm0_flap, "cl_clean": cl_clean, "cl_landing": cl_land,
            "tail_cla_ground_factor": factor, "clauses": clauses}


def binding_forward_station(res, xbar_np: float, cm_de: float, elevator_max_deg: float,
                            x_mac_le: float, mac: float) -> tuple[float | None, str]:
    """More-aft forward CG of the clean CLmax trim and the full-flap flare, in metres from the nose.

    Raymer Ch. 16 names the landing flare, flaps down, as the critical forward-CG case. The station
    is the Nelson trim equation. The flare row uses ``tail_cla_ground_factor`` on Cmδe
    (Torenbeek φ on the tail lift slope only).
    """
    if abs(cm_de) < 1e-6:
        return None, "Limite dianteiro de controlo não calculado (Cmδe ≈ 0)."
    terms = forward_cg_terms(res)

    def station(cm0, cl, cm_de_row):
        if cl is None:
            return None
        xbar = control_forward_xbar(xbar_np, cm0, cm_de_row, elevator_max_deg, cl)
        if xbar is None:
            return None
        return xbar, x_mac_le + xbar * mac

    rows = []
    clean = station(terms["cm0_wing"], terms["cl_clean"], cm_de)
    if clean is not None:
        rows.append(("limpo", terms["cl_clean"], terms["cm0_wing"], clean[1]))
    land = station(terms["cm0_flare"], terms["cl_landing"],
                   cm_de * terms.get("tail_cla_ground_factor", 1.0))
    if land is not None:
        rows.append(("flare com flaps", terms["cl_landing"], terms["cm0_flare"], land[1]))
    if not rows:
        return None, "Limite dianteiro não calculado (CLmax ≤ 0)."
    name, cl, cm0, x = max(rows, key=lambda row: row[3])
    others = ", ".join(f"{n} a {xi:.3f} m (CL {c:.2f}, Cm0 {m:.4f})" for n, c, m, xi in rows)
    note = (f"Limite dianteiro conceptual: dimensiona «{name}» a {x:.3f} m. "
            f"Casos: {others}. Nelson 1998 Cap. 2, |δe| = {elevator_max_deg:g}°. "
            + " ".join(terms["clauses"]))
    return x, note


def fuselage_ac_shift(b_f: float, h_f: float, l_fn: float, S: float, mac: float, CLa_w: float) -> float:
    """Torenbeek (1982) App. E: Δx̄_ac = −(1.8/CLα_w) b_f h_f l_fn/(S c̄) (destabilising, forward shift)."""
    return -1.8 / CLa_w * b_f * h_f * l_fn / (S * mac)


def _np_aero(res, CLa: float) -> dict:
    """Wing inputs of :func:`neutral_point`. Elastic CLα and x_ac only when the size loop applied the correction."""
    el = getattr(getattr(res, "structures_l1", None), "elastic", None)
    if el is not None and el.applied and math.isfinite(el.CLa_flex):
        return {"CLa_w": float(el.CLa_flex), "xac_w": float(el.xac_w)}
    return {"CLa_w": CLa}


def neutral_point(config, aero=None, x_mac_le: float = 0.0, x_wing_apex: float = 0.0, mach: float = 0.0,
                  include_fuselage: bool = True):
    """Handbook stick-fixed neutral point (fraction of MAC, from the MAC LE). ``aero`` may give 'CLa_w'
    and 'xac_w' (fraction of MAC; default 0.25, Raymer Sec. 16.3).
    Returns dict with xbar_np, dε/dα, tail terms and the fuselage shift."""
    w, ht = config.wing, config.htail
    fus = config.fuselage
    CLa_w = (aero or {}).get("CLa_w") or lift_curve_slope(w.AR, mach, w.sweep_at(w.xc_max_t))
    CLa_h = lift_curve_slope(ht.AR, mach, ht.as_wing().sweep_at(0.3))
    deps = 2 * CLa_w / (math.pi * w.AR)
    xac_w = float((aero or {}).get("xac_w", 0.25))
    dx = fuselage_ac_shift(fus.max_diameter, fus.max_diameter, x_wing_apex, w.S, w.mac, CLa_w) if include_fuselage else 0.0
    xac_wb = xac_w + dx
    xac_h = 0.25 + ht.arm / w.mac
    th = ETA_H * ht.S / w.S * CLa_h * (1 - deps)
    xnp = (CLa_w * xac_wb + th * xac_h) / (CLa_w + th)
    return {"xbar_np": xnp, "deps_dalpha": deps, "CLa_w": CLa_w, "CLa_h": CLa_h, "dx_fus": dx, "tail_term": th}


def _firewall_x(res, length: float) -> float | None:
    """POH firewall station in metres from the nose, or None when the mission has no firewall datum.

    ``firewall_x_m`` is used as given. ``firewall_fraction`` is a fraction of the fuselage length.
    ``firewall_from_engine`` puts the firewall half an engine length aft of the engine mass station.
    That half-length step is a PRESSUPOSTO: the engine station is treated as mid-length. The length
    itself has to be cited on the mission (``engine_length_m``).
    """
    o = ((getattr(getattr(res, "spec", None), "assumptions", None) or {}).get("stability") or {})
    if o.get("firewall_x_m") is not None:
        return float(o["firewall_x_m"])
    if o.get("firewall_fraction") is not None:
        return float(o["firewall_fraction"]) * length
    if not o.get("firewall_from_engine"):
        return None
    eng = o.get("engine_length_m")
    if eng is None:
        raise ValueError("stability.firewall_from_engine needs stability.engine_length_m")
    stations = {**DEFAULT_STATIONS, **{k: tuple(v) for k, v in (o.get("stations") or {}).items()}}
    x_eng = _station_x("engine_installed", stations, length, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, None)
    return x_eng + 0.5 * float(eng)


def _station_x(key, stations, L, x_mac_le, mac, x_ht_mac_le, ht_mac, x_vt_mac_le, vt_mac,
               x_firewall=None):
    ref, f = stations.get(key, stations["user_items"])
    if ref == "L":
        return f * L
    if ref == "MAC":
        return x_mac_le + f * mac
    if ref == "htail":
        return x_ht_mac_le + f * ht_mac
    if ref == "vtail":
        return x_vt_mac_le + f * vt_mac
    if ref == "m":
        return f
    if ref == "firewall":
        if x_firewall is None:
            raise ValueError(f"{key}: station reference 'firewall' needs stability.firewall_x_m, "
                             "firewall_fraction or firewall_from_engine")
        return x_firewall + f * INCH
    if ref == "balance":
        raise ValueError(f"{key}: station reference 'balance' is resolved from the fixed-mass CG, "
                         "not as a geometric fraction")
    raise ValueError(f"unknown station reference '{ref}'")


def _items_and_cases(res, x_apex, stations):
    """Mass items with stations for a wing apex position; returns (item list, loading cases list)."""
    cfg = res.config
    w, ht, vt, fus = cfg.wing, cfg.htail.as_wing(), cfg.vtail.as_wing(), cfg.fuselage
    L = fus.length
    x_mac_le = x_apex + w.y_mac * math.tan(w.sweep_at(0.0))
    x_ac = x_apex + wing_x_ac(w)
    x_ht_mac_le = x_ac + cfg.htail.arm - 0.25 * ht.mac
    x_vt_mac_le = x_ac + cfg.vtail.arm - 0.25 * vt.mac
    args = (L, x_mac_le, w.mac, x_ht_mac_le, ht.mac, x_vt_mac_le, vt.mac, _firewall_x(res, L))
    items = []
    for it in res.weights.items:
        key = it.key
        if key.startswith("item:"):
            st = stations.get(key[5:]) or stations.get("user_items")
            items.append({"key": key, "group": it.group, "mass": it.mass,
                          "x": _station_x("x", {"x": st, "user_items": st}, *args)})
        else:
            items.append({"key": key, "group": it.group, "mass": it.mass, "x": _station_x(key, stations, *args)})
    sz = res.sizing
    electric = res.spec.propulsion_kind == "electric"
    useful = {"crew": sz.crew, "payload": sz.payload}
    ef = {"battery" if electric else "fuel": sz.Wf}
    m_e = sum(i["mass"] for i in items)
    mx_e = sum(i["mass"] * i["x"] for i in items)
    # Fixed mass excludes crew, payload, fuel and battery. ``balance`` sits on that CG
    # (Raymer 2018 Sec. 15.1): adding the item then leaves x_cg unchanged.
    x_fixed = mx_e / m_e if m_e > 0 else 0.5 * L

    def useful_x(key):
        ref, _frac = stations.get(key, stations["user_items"])
        if ref == "balance":
            return x_fixed
        return _station_x(key, stations, *args)

    ux = {k: useful_x(k) for k in ("crew", "payload", "fuel", "battery")}
    # loading sequence (plotted as a closed loop): empty → + fuel → + payload (MTOW) → fuel burnt (ZFW)
    combos = [("vazio + tripulação" if sz.crew else "vazio", {"crew"}), ("sem payload", {"crew", "energy"}),
              ("MTOW", {"crew", "payload", "energy"}), ("sem combustível (ZFW)", {"crew", "payload"})]
    if electric:  # battery is never removed in flight; the empty case still carries it
        combos = [("vazio + bateria", {"crew", "energy"}), ("MTOW", {"crew", "payload", "energy"})]
    cases = []
    for name, sel in combos:
        m, mx = m_e, mx_e
        for k in ("crew", "payload"):
            if k in sel and useful[k] > 0:
                m += useful[k]
                mx += useful[k] * ux[k]
        if "energy" in sel:
            k = "battery" if electric else "fuel"
            m += ef[k]
            mx += ef[k] * ux[k]
        cases.append((name, m, mx / m))
    items += [{"key": k, "group": "useful load", "mass": v, "x": ux[k]} for k, v in {**useful, **ef}.items() if v > 0]
    return items, cases, x_mac_le


def stability_analysis(res, avl_result=None, opts: dict | None = None) -> StabilityResult:
    """Neutral point, CG envelope with wing placement, tail volumes, control derivatives and trim."""
    from .geometry import RAYMER_TAIL_VOLUME

    o = {"target_static_margin": 0.10, "wing_apex_x_fraction": None, "stations": {}, "elevator_max_deg": 25.0,
         "elevator_cf_c": 0.30, "aileron_cf_c": 0.25, "rudder_cf_c": 0.35, "aileron_span_fraction": 0.35,
         **(opts or {})}
    stations = {**DEFAULT_STATIONS, **{k: tuple(v) for k, v in o["stations"].items()}}
    cfg = res.config
    w, ht, vt, fus = cfg.wing, cfg.htail, cfg.vtail, cfg.fuselage
    notes = []
    CLa_w = res.CLalpha

    def np_at(xa):
        x_mac_le = xa + w.y_mac * math.tan(w.sweep_at(0.0))
        return neutral_point(cfg, _np_aero(res, CLa_w), x_mac_le, xa), x_mac_le

    def sm_aft(xa):
        _, cases, x_mac_le = _items_and_cases(res, xa, stations)
        npd, _ = np_at(xa)
        return min(npd["xbar_np"] - (xc - x_mac_le) / w.mac for _, _, xc in cases)

    if o["wing_apex_x_fraction"] is not None:
        xa = o["wing_apex_x_fraction"] * fus.length
        placement = f"utilizador: ápice da asa a {o['wing_apex_x_fraction']:.0%} L"
    else:
        lo, hi = 0.0, 0.8 * fus.length
        f_lo, f_hi = sm_aft(lo) - o["target_static_margin"], sm_aft(hi) - o["target_static_margin"]
        if f_lo * f_hi > 0:
            xa = lo if abs(f_lo) < abs(f_hi) else hi
            notes.append("Não foi possível colocar a asa para a margem alvo dentro de 0–80 % L — rever massas/estações.")
        else:
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                fm = sm_aft(mid) - o["target_static_margin"]
                if fm * f_lo > 0:
                    lo, f_lo = mid, fm
                else:
                    hi = mid
            xa = 0.5 * (lo + hi)
        placement = (f"asa posicionada para SM = {o['target_static_margin']:.0%} no CG mais recuado "
                     f"(ápice a {xa / fus.length:.1%} L)")
    items, cases_raw, x_mac_le = _items_and_cases(res, xa, stations)
    npd, _ = np_at(xa)
    npd0 = neutral_point(cfg, _np_aero(res, CLa_w), x_mac_le, xa, include_fuselage=False)
    cases = [LoadingCase(n, m, xc, (xc - x_mac_le) / w.mac, npd["xbar_np"] - (xc - x_mac_le) / w.mac)
             for n, m, xc in cases_raw]
    x_tail_end = xa + wing_x_ac(w) + ht.arm + 0.75 * ht.as_wing().mac
    if x_tail_end > 1.05 * fus.length:
        notes.append(f"Bordo de fuga da empenagem a {x_tail_end:.2f} m > comprimento da fuselagem {fus.length:.2f} m "
                     "(braço de cauda fixo) — reduzir tail_arm_fraction ou usar boom de cauda.")
    Vh = ht.S * ht.arm / (w.S * w.mac)
    Vv = vt.S * vt.arm / (w.S * w.span)
    cls = res.spec.assumptions["geometry"].get("tail_class") or res.spec.aircraft_class
    Vh_c, Vv_c = RAYMER_TAIL_VOLUME.get(cls, (None, None))
    # ---- control derivatives (handbook) ----
    te, ta, tr = (flap_effectiveness(o["elevator_cf_c"]), flap_effectiveness(o["aileron_cf_c"]),
                  flap_effectiveness(o["rudder_cf_c"]))
    CLa_h = npd["CLa_h"]
    CLa_v = lift_curve_slope(2 * vt.AR, 0.0, vt.as_wing().sweep_at(0.3))  # end-plate effect: effective AR ≈ 2× (fin on body)
    b2 = w.span / 2
    y1 = (1 - o["aileron_span_fraction"]) * b2
    yy = np.linspace(y1, b2, 50)
    cy = w.c_root + (w.c_tip - w.c_root) * yy / b2
    hb = {"CLde": ETA_H * ht.S / w.S * CLa_h * te, "Cmde": -ETA_H * Vh * CLa_h * te,
          "Clda_magnitude": 2 * CLa_w * ta / (w.S * w.span) * float(np.trapezoid(cy * yy, yy)),
          "Cndr": -ETA_H * Vv * CLa_v * tr, "tau_e": te, "tau_a": ta, "tau_r": tr}
    ctrl = {"handbook_per_rad": hb}
    xnp_avl = None
    if avl_result is not None:
        # AVL Xnp is in the AVL frame (origin at the wing root LE)
        xnp_avl = (avl_result.Xnp - w.y_mac * math.tan(w.sweep_at(0.0))) / w.mac
        c = avl_result.controls
        ctrl["avl_per_rad"] = {"CLde": c["elevator"].get("CL"), "Cmde_about_ref": c["elevator"].get("Cm"),
                               "Clda_magnitude": abs(c["aileron"].get("Cl", float("nan"))),
                               "Cndr": c["rudder"].get("Cn"), "Cnb": avl_result.derivatives.get("Cnb"),
                               "Clb": avl_result.derivatives.get("Clb"), "Cmq": avl_result.derivatives.get("Cmq")}
        # convert AVL Cmδe (about its reference = wing quarter-MAC) to Cmδe about any cg: same derivative
        # shifted by CLδe (x_ref − x_cg)/c̄ — reported about the aft CG
        notes.append("Clδa comparado em módulo (convenções de sinal do aileron diferem entre AVL e Nelson).")
    # ---- trim at the forward end of the same range the scissor uses (min x̄) ----
    cm0_af = getattr(res, "lowfi", None).cm0 if getattr(res, "lowfi", None) is not None else -0.05
    Cm0 = wing_cm0(cm0_af, w.AR, w.sweep_c4)
    fwd = min(cases, key=lambda c: c.xbar_cg)
    from acdt import G0
    from acdt.core.atmosphere import isa
    rho = isa(res.cruise_altitude).rho
    CL_cr = res.sizing.W0 * G0 / (0.5 * rho * res.cruise_speed**2 * res.S)
    trim = {}
    for nm, CL in (("CLmax limpo (CG dianteiro)", res.highlift.CLmax_clean), ("cruzeiro (CG dianteiro)", CL_cr)):
        de = -(Cm0 - fwd.SM * CL) / hb["Cmde"]
        trim[nm] = {"CL": CL, "delta_e_deg": math.degrees(de), "xbar_cg": fwd.xbar_cg,
                    "x_cg_m": fwd.x_cg, "ok": abs(math.degrees(de)) <= o["elevator_max_deg"]}
    if not all(t["ok"] for t in trim.values()):
        notes.append(f"Trim no CG dianteiro excede |δe| ≤ {o['elevator_max_deg']:g}° — aumentar S_h, braço ou corda "
                     "do profundor, ou restringir o CG dianteiro.")
    if avl_result is not None and avl_result.derivatives.get("Cnb", 1) <= 0:
        notes.append("Cnβ ≤ 0 (AVL): instabilidade direcional — aumentar a empenagem vertical.")
    notes.append("Estações de estrutura: PRESSUPOSTOS (Roskam Part V Table 8.1, valores típicos). "
                 "Tripulação, carga e bateria, se a missão não as der, ficam no CG da massa fixa "
                 "(Raymer 2018 Sec. 15.1: a estação que não desloca o balanço). Um UAV sem massa de "
                 "tripulação não leva tripulação. O combustível de asa fica a 30 % da CMA. "
                 "Substituir em assumptions.stability.stations.")
    st_list = [{"item": i["key"], "mass_kg": i["mass"], "x_m": i["x"]} for i in items]
    return StabilityResult(xa, x_mac_le, w.mac, npd["xbar_np"], npd0["xbar_np"], xnp_avl, npd["dx_fus"],
                           npd["deps_dalpha"], CLa_w, CLa_h, Vh, Vv, Vh_c, Vv_c, cases, ctrl, trim,
                           o["target_static_margin"], placement, st_list, notes)


def plot_cg_envelope(st: StabilityResult, path, title: str = ""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    xs = [100 * c.xbar_cg for c in st.cases]
    ms = [c.mass for c in st.cases]
    order = list(range(len(xs)))  # loading sequence order (see _items_and_cases)
    ax.plot([xs[i] for i in order] + [xs[order[0]]], [ms[i] for i in order] + [ms[order[0]]], "b-o")
    for c in st.cases:
        ax.annotate(c.name, (100 * c.xbar_cg, c.mass), fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.axvline(100 * st.xbar_np, color="r", lw=1.5, label=f"ponto neutro (manual) {100 * st.xbar_np:.1f} %")
    if st.xbar_np_avl is not None:
        ax.axvline(100 * st.xbar_np_avl, color="m", ls="--", label=f"ponto neutro AVL (s/ fuselagem) "
                   f"{100 * st.xbar_np_avl:.1f} %")
    ax.set_xlabel("x_cg [% CMA]")
    ax.set_ylabel("massa [kg]")
    ax.set_title(title or "Envelope de CG")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


# =============================================================== Phase 3: scissor plot, dynamic modes, HQ
def _control_line_sentence(terms: dict, elevator_max_deg: float, tau_e: float) -> str:
    clean = (f"CLmax limpo {terms['cl_clean']:.2f} (Cm0 asa {terms['cm0_wing']:.4f})")
    if terms["cl_landing"] is None:
        flare = "flare com flaps não entra neste resultado"
    else:
        flare = (f"flare com flaps (CLmax aterragem {terms['cl_landing']:.2f}, "
                 f"Cm0 {terms['cm0_flare']:.4f})")
    return (f"o x̄ mais à ré entre o {clean} e o {flare}, δe = −{elevator_max_deg:g}°, τ_e = {tau_e:.3f}. "
            + " ".join(terms["clauses"]))


def tail_sizing_scissor(res, st: StabilityResult, opts: dict | None = None, n: int = 41) -> dict:
    """Stability / control "scissor" plot (Torenbeek 1982 Ch. 9; Raymer Ch. 16) vs S_h/S, wing position and tail
    arm fixed. Stability line: x̄_cg,aft = x̄_np(S_h) − SM_min (Raymer Eq. 16.9 + Torenbeek fuselage shift).
    Control line: the more-aft forward CG of the clean CLmax trim and the full-flap flare
    (landing CLmax, wing + fuselage + flap Cm0), x̄ = x̄_np − (Cm0 + |Cmδe| δe_max)/CL,
    Cmδe = −η_h V̄_h CLα_h τ_e (Nelson Ch. 2). Same build-up as ``binding_forward_station``.
    The flare row multiplies CLα_h by Torenbeek's φ at that trial tail's span. The tail
    mass change with S_h is not fed back (first cut). The CG range is ``st.cg_range_mac``,
    the same loading cases the trim evaluates at its forward end."""
    from dataclasses import replace
    o = {"target_static_margin": 0.10, "elevator_max_deg": 25.0, "elevator_cf_c": 0.30, **(opts or {})}
    cfg, w = res.config, res.config.wing
    S_now = cfg.htail.S
    ratios = np.linspace(0.02, max(3.0 * S_now / w.S, 0.4), n)
    te = flap_effectiveness(o["elevator_cf_c"])
    terms = forward_cg_terms(res)
    de = o["elevator_max_deg"]
    stab, ctrl = [], []
    for r in ratios:
        c2 = replace(cfg, htail=replace(cfg.htail, S=r * w.S))
        npd = neutral_point(c2, _np_aero(res, res.CLalpha), st.x_mac_le, st.x_wing_apex)
        Vh = r * w.S * c2.htail.arm / (w.S * w.mac)
        Cmde = -ETA_H * Vh * npd["CLa_h"] * te
        scale, _ = flare_tail_cla_scale(res, c2.htail)
        xs = []
        x_clean = control_forward_xbar(npd["xbar_np"], terms["cm0_wing"], Cmde, de, terms["cl_clean"])
        if x_clean is not None:
            xs.append(x_clean)
        if terms["cl_landing"] is not None:
            x_land = control_forward_xbar(npd["xbar_np"], terms["cm0_flare"], Cmde * scale, de,
                                          terms["cl_landing"])
            if x_land is not None:
                xs.append(x_land)
        stab.append(npd["xbar_np"] - o["target_static_margin"])
        ctrl.append(max(xs) if xs else math.nan)
    stab, ctrl = np.array(stab), np.array(ctrl)
    lo, hi = st.cg_range_mac
    # minimum S_h/S on each line (linear interpolation): stability (x̄_aft ≤ line), control (x̄_fwd ≥ line)
    def first_cross(vals, target, above):
        good = vals >= target if above else vals <= target
        if not good.any():
            return math.nan
        i = int(np.argmax(good))
        if i == 0:
            return float(ratios[0])
        f = (target - vals[i - 1]) / (vals[i] - vals[i - 1])
        return float(ratios[i - 1] + f * (ratios[i] - ratios[i - 1]))

    r_stab, r_ctrl = first_cross(stab, hi, True), first_cross(ctrl, lo, False)
    r_req = max(r_stab, r_ctrl) if math.isfinite(r_stab) and math.isfinite(r_ctrl) else math.nan
    return {"Sh_S": ratios, "stability_line": stab, "control_line": ctrl, "cg_range": (lo, hi),
            "Sh_S_current": S_now / w.S, "Sh_S_required": r_req, "Sh_S_stability": r_stab, "Sh_S_control": r_ctrl,
            "binding": "estabilidade" if r_stab >= r_ctrl else "controlo",
            # 0.5 % tolerance: the wing is placed by bisection so that the stability line passes through x̄_aft
            "ok": bool(math.isfinite(r_req) and S_now / w.S >= r_req * (1 - 5e-3)),
            "notes": ["linha de controlo: " + _control_line_sentence(terms, de, te),
                      "massa da cauda não realimentada (posição da asa e braço fixos)",
                      "gama de CG: a mesma do trim (extremos dos casos de carregamento)"]}


def plot_scissor(sc: dict, path, title: str = ""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.plot(100 * sc["stability_line"], sc["Sh_S"], "b-", label="estabilidade (x̄_NP − SM)")
    ax.plot(100 * sc["control_line"], sc["Sh_S"], "r-", label="controlo (trim CLmax, δe máx.)")
    lo, hi = sc["cg_range"]
    ax.plot([100 * lo, 100 * hi], [sc["Sh_S_current"]] * 2, "k-", lw=4, alpha=0.6, label="gama de CG atual")
    if math.isfinite(sc["Sh_S_required"]):
        ax.axhline(sc["Sh_S_required"], color="g", ls="--", lw=0.8, label=f"S_h/S mín. {sc['Sh_S_required']:.3f}")
    ax.set_xlabel("x̄_cg [% MAC]")
    ax.set_ylabel("S_h / S")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    ax.set_title(title or "Diagrama 'scissor' (Torenbeek Cap. 9)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def inertias(res, st: StabilityResult, stations: dict | None = None, include=None) -> dict:
    """Moments of inertia by component summation about the MTOW CG (Roskam, Airplane Design Part V, Ch. 10
    approach): items as point masses at their stations (x), wing/htail mass and wing fuel distributed ∝ chord along
    the span, vtail mass along its height, fuselage as a slender rod about its own CG (m L²/12). z offsets of
    other items neglected (ASSUMPTION). ``include(item) -> bool`` restricts the sum to some items (still about the
    all-items CG). Non-dimensional radii as Roskam Part V Eqs. 3.7–3.9: R̄x = 2√(I_xx/m)/b, etc."""
    stations = {**DEFAULT_STATIONS, **(stations or {})}
    items, cases, _ = _items_and_cases(res, st.x_wing_apex, stations)
    mt = sum(i["mass"] for i in items)
    xcg = sum(i["mass"] * i["x"] for i in items) / mt
    if include is not None:
        items = [i for i in items if include(i)]
    cfg = res.config
    w, ht, vt = cfg.wing, cfg.htail.as_wing(), cfg.vtail.as_wing()

    def span_int(wing, b_half):
        y = np.linspace(0, b_half, 50)
        c = wing.c_root + (wing.c_tip - wing.c_root) * y / b_half
        return float(np.trapezoid(c * y**2, y) / np.trapezoid(c, y))  # ⟨y²⟩

    y2w, y2h = span_int(w, w.span / 2), span_int(ht, ht.span / 2)
    z2v = span_int(vt, vt.span)  # vtail "span" = height for the single fin (as_wing uses full AR)
    Ixx = Iyy = Izz = 0.0
    for it in items:
        m, dx = it["mass"], it["x"] - xcg
        k = it["key"]
        ky2 = y2w if k in ("wing", "fuel") else (y2h if k == "htail" else 0.0)
        kz2 = z2v if k == "vtail" else 0.0
        own_y = cfg.fuselage.length**2 / 12 if k == "fuselage" else 0.0
        Ixx += m * (ky2 + kz2)
        Iyy += m * (dx**2 + kz2 + own_y)
        Izz += m * (dx**2 + ky2 + own_y)
    b, L = w.span, cfg.fuselage.length
    e = (b + L) / 2
    ms = sum(i["mass"] for i in items) if include is not None else mt
    xs = sum(i["mass"] * i["x"] for i in items) / ms if ms > 0 else xcg
    return {"m": mt, "x_cg": xcg, "m_sel": ms, "x_sel": xs, "Ixx": Ixx, "Iyy": Iyy, "Izz": Izz,
            "Rx": 2 * math.sqrt(Ixx / mt) / b, "Ry": 2 * math.sqrt(Iyy / mt) / L, "Rz": 2 * math.sqrt(Izz / mt) / e}


# Roskam, Airplane Design Part V (1985/2018), Appendix B, Table B2 "Non-dimensional radii of gyration for single
# engine propeller driven airplanes" (one pilot included; ** = at W_OE, * = at W_TO). Read from the table.
ROSKAM_RADII = {
    "beech_n35": (0.248, 0.338, 0.393),      # Bonanza, at W_TO
    "cessna_150m": (0.254, 0.405, 0.418),    # at W_OE
    "cessna_172m": (0.242, 0.386, 0.403),    # at W_OE
    "cessna_177a": (0.212, 0.362, 0.394),    # at W_OE
    "cessna_r182": (0.342, 0.397, 0.393),    # at W_OE
    "cessna_210k": (0.222, 0.356, 0.379),    # at W_OE + 25 % fuel
}


def inertias_radii_of_gyration(m: float, b: float, L: float, R) -> dict:
    """Class I inertias (Roskam Part V Eqs. 3.7–3.9): I_xx = m (b R̄x)²/4, I_yy = m (L R̄y)²/4,
    I_zz = m (e R̄z)²/4, e = (b + L)/2; R̄ from a comparable airplane (Appendix B)."""
    Rx, Ry, Rz = R
    e = (b + L) / 2
    return {"Ixx": m * (b * Rx) ** 2 / 4, "Iyy": m * (L * Ry) ** 2 / 4, "Izz": m * (e * Rz) ** 2 / 4,
            "Rx": Rx, "Ry": Ry, "Rz": Rz}


def inertia_estimate(res, st: StabilityResult, opts: dict | None = None) -> tuple[dict, str, dict]:
    """Inertias used by the dynamics/simulator: ``inertia_method`` components (default) | roskam.
    Roskam: ``radii_of_gyration`` {Rx, Ry, Rz} or ``roskam_reference`` (key of ROSKAM_RADII). Returns
    (inertias at the MTOW CG, source label, cross-check {components, roskam, ratios})."""
    o = opts or {}
    comp = inertias(res, st, o.get("stations"))
    b, L = res.config.wing.span, res.config.fuselage.length
    R = o.get("radii_of_gyration")
    ref = o.get("roskam_reference")
    if R:
        R = (R["Rx"], R["Ry"], R["Rz"])
        lab = "R̄ dados"
    elif ref:
        if ref not in ROSKAM_RADII:
            raise ValueError(f"roskam_reference '{ref}' unknown ({', '.join(ROSKAM_RADII)})")
        R, lab = ROSKAM_RADII[ref], f"R̄ de {ref} (Roskam Part V Tab. B2)"
    else:  # cross-check against the mean of Table B2
        R = tuple(float(np.mean([v[i] for v in ROSKAM_RADII.values()])) for i in range(3))
        lab = "R̄ média da Tab. B2 (Roskam Part V)"
    # Roskam R̄ are for the empty airplane with one pilot (Tab. B2, W_OE basis): apply them to the operating empty
    # mass (empty + crew) and add payload and fuel/battery by the component sum (parallel axis about the MTOW CG)
    load = inertias(res, st, o.get("stations"), include=lambda i: i["key"] in ("payload", "fuel", "battery"))
    m_oe = comp["m"] - load["m_sel"]
    x_oe = (comp["m"] * comp["x_cg"] - load["m_sel"] * load["x_sel"]) / m_oe
    oe = inertias_radii_of_gyration(m_oe, b, L, R)
    sh = m_oe * (x_oe - comp["x_cg"]) ** 2
    rk = {"Ixx": oe["Ixx"] + load["Ixx"], "Iyy": oe["Iyy"] + sh + load["Iyy"], "Izz": oe["Izz"] + sh + load["Izz"],
          "Rx": R[0], "Ry": R[1], "Rz": R[2], "m_oe": m_oe,
          "oe": {k: oe[k] for k in ("Ixx", "Iyy", "Izz")}}
    ratios = {k: comp[k] / rk[k] for k in ("Ixx", "Iyy", "Izz")}
    xc = {"components": {k: comp[k] for k in ("Ixx", "Iyy", "Izz", "Rx", "Ry", "Rz")}, "roskam": rk,
          "roskam_source": lab + " no peso operacional vazio + carga útil por componentes",
          "ratio_components_over_roskam": ratios}
    if o.get("inertia_method", "components") == "roskam":
        out = {**comp, **{k: rk[k] for k in ("Ixx", "Iyy", "Izz")}}
        return out, f"Roskam Part V Eqs. 3.7–3.9, {lab}", xc
    return comp, "soma de componentes (Roskam Part V)", xc


def longitudinal_matrix(CL, CD, K, CLa, Cma, Cmad, Cmq, kprop, qS, c, m, Iyy, u0) -> np.ndarray:
    """State matrix [u, w, q, θ] of :func:`dynamic_modes` (Nelson 1998 Ch. 4; Etkin & Reid 1996 Ch. 6)."""
    from acdt import G0
    Xu = -kprop * CD * qS / (m * u0)
    Zu = -2 * CL * qS / (m * u0)
    Xw = (CL - 2 * K * CL * CLa) * qS / (m * u0)
    Zw = -(CLa + CD) * qS / (m * u0)
    Mw = Cma * qS * c / (Iyy * u0)
    Mwd = Cmad * (c / (2 * u0)) * qS * c / (Iyy * u0)
    Mq = Cmq * (c / (2 * u0)) * qS * c / Iyy
    return np.array([[Xu, Xw, 0.0, -G0], [Zu, Zw, u0, 0.0],
                     [Mwd * Zu, Mw + Mwd * Zw, Mq + Mwd * u0, 0.0], [0.0, 0.0, 1.0, 0.0]])


def lateral_matrix(d: dict, qS, b, m, Ixx, Izz, u0) -> np.ndarray:
    """State matrix [β, p, r, φ] of :func:`dynamic_modes` from the stability-axis derivatives ``d`` (CYβ, CYp,
    CYr, Clβ, Clp, Clr, Cnβ, Cnp, Cnr); Ixz neglected (Nelson 1998 Ch. 5)."""
    from acdt import G0
    Yb, Yp, Yr = d["CYb"] * qS / m, d["CYp"] * qS * b / (2 * m * u0), d["CYr"] * qS * b / (2 * m * u0)
    Lb, Lp, Lr = (d["Clb"] * qS * b / Ixx, d["Clp"] * qS * b**2 / (2 * Ixx * u0),
                  d["Clr"] * qS * b**2 / (2 * Ixx * u0))
    Nb, Np, Nr = (d["Cnb"] * qS * b / Izz, d["Cnp"] * qS * b**2 / (2 * Izz * u0),
                  d["Cnr"] * qS * b**2 / (2 * Izz * u0))
    return np.array([[Yb / u0, Yp / u0, -(1 - Yr / u0), G0 / u0], [Lb, Lp, Lr, 0.0], [Nb, Np, Nr, 0.0],
                     [0.0, 1.0, 0.0, 0.0]])


def dynamic_modes(res, st: StabilityResult, avl=None, opts: dict | None = None) -> dict:
    """Linearised small-perturbation modes about trimmed level cruise at MTOW (Nelson 1998 Ch. 4–5; Etkin &
    Reid 1996 Ch. 6). Stability-axis, Ixz neglected.

    Longitudinal [u, w, q, θ]: X_u = −3 CD q̄S/(m u0) (constant-power propeller; −2 CD for constant thrust),
    Z_u = −2 CL q̄S/(m u0), X_w = (CL − 2K CL CLα) q̄S/(m u0), Z_w = −(CLα + CD) q̄S/(m u0),
    M_w = Cmα q̄Sc̄/(I_y u0), Cmα = −CLα SM (handbook NP incl. fuselage), M_ẇ from
    Cmα̇ = −2 η V̄_h CLα_h (l_t/c̄) dε/dα, M_q from Cmq (AVL; else −2 η V̄_h CLα_h l_t/c̄).
    Lateral [β, p, r, φ]: AVL CYβ, Clβ, Cnβ, CYp, Clp, Cnp, CYr, Clr, Cnr (no fuselage in AVL) + fuselage
    Cnβ = −1.3 Vol_f/(S b) (D_f/W_f) (Raymer Eq. 16.47; Vol_f ≈ S_wet,f D_f/4, ASSUMPTION)."""
    from acdt import G0
    from acdt.core.atmosphere import isa
    o = {**(opts or {})}
    cfg, w = res.config, res.config.wing
    I = inertia_estimate(res, st, o)[0]
    m = I["m"]
    at = isa(res.cruise_altitude)
    u0 = res.cruise_speed
    qS = 0.5 * at.rho * u0**2 * w.S
    CL = m * G0 / qS
    CD = res.polar.CD0 + res.polar.K * CL**2
    npd = neutral_point(cfg, _np_aero(res, res.CLalpha), st.x_mac_le, st.x_wing_apex)
    CLa = npd["CLa_w"] + npd["tail_term"]
    SM = min(c.SM for c in st.cases if c.name == "MTOW") if any(c.name == "MTOW" for c in st.cases) else st.SM_aft
    Cma = -CLa * SM
    c = w.mac
    lt = cfg.htail.arm
    Vh = cfg.htail.S * lt / (w.S * c)
    Cmad = -2 * ETA_H * Vh * npd["CLa_h"] * (lt / c) * npd["deps_dalpha"]
    d = avl.derivatives if avl is not None else {}
    src = "AVL" if avl is not None else "manual"
    Cmq = d.get("Cmq", -2 * ETA_H * Vh * npd["CLa_h"] * lt / c)
    kprop = 3.0 if res.spec.propulsion_kind in ("electric", "piston", "turboprop") else 2.0
    Alon = longitudinal_matrix(CL, CD, res.polar.K, CLa, Cma, Cmad, Cmq, kprop, qS, c, m, I["Iyy"], u0)
    # lateral
    fus = cfg.fuselage
    vol_f = fus.wetted_area() * fus.max_diameter / 4
    Cnb_f = -1.3 * vol_f / (w.S * w.span)
    b = w.span
    if avl is not None:
        CYb, Clb, Cnb = d.get("CYb"), d.get("Clb"), d.get("Cnb") + Cnb_f
        CYp, Clp, Cnp = d.get("CYp", 0.0), d.get("Clp"), d.get("Cnp")
        CYr, Clr, Cnr = d.get("CYr", 0.0), d.get("Clr"), d.get("Cnr")
    else:
        return {"longitudinal": _modes_long(Alon, u0, qS, CLa, m, I), "lateral": None, "inertia": I,
                "source": src, "notes": ["AVL não disponível: modos laterais não avaliados (derivadas laterais "
                                         "de manual não implementadas — usar AVL)"]}
    Alat = lateral_matrix({"CYb": CYb, "CYp": CYp, "CYr": CYr, "Clb": Clb, "Clp": Clp, "Clr": Clr, "Cnb": Cnb,
                           "Cnp": Cnp, "Cnr": Cnr}, qS, b, m, I["Ixx"], I["Izz"], u0)
    lon = _modes_long(Alon, u0, qS, CLa, m, I)
    lat = _modes_lat(Alat)
    return {"longitudinal": lon, "lateral": lat, "inertia": I, "source": src,
            "derivatives": {"CLa": CLa, "Cma": Cma, "Cmad": Cmad, "Cmq": Cmq, "CL": CL, "CD": CD, "Cnb_fus": Cnb_f,
                            "Cnb_total": Cnb, "Clb": Clb, "Clp": Clp, "Cnr": Cnr, "CYb": CYb},
            "A_lon": Alon, "A_lat": Alat, "u0": u0,
            "notes": [f"derivadas de taxa e laterais: {src} (sem fuselagem) + Cnβ da fuselagem (Raymer 16.47) "
                      f"{Cnb_f:+.4f}", "Cmα = −CLα·SM no CG de MTOW (ponto neutro de manual com fuselagem)",
                      "inércias por soma de componentes (Roskam Parte V) — PRESSUPOSTOS de estações"]}


def _pair(lam):
    wn = abs(lam)
    return {"wn": float(wn), "zeta": float(-lam.real / wn) if wn > 0 else math.nan,
            "period_s": float(2 * math.pi / abs(lam.imag)) if abs(lam.imag) > 1e-12 else math.inf,
            "eig": complex(lam)}


def _modes_long(A, u0, qS, CLa, m, I):
    lam = np.linalg.eigvals(A)
    cplx = sorted([l for l in lam if l.imag > 1e-9], key=lambda l: abs(l))
    out = {"eig": [complex(x) for x in lam]}
    if len(cplx) == 2:
        out["phugoid"], out["short_period"] = _pair(cplx[0]), _pair(cplx[1])
    else:  # short period split into two real roots (heavily damped) or phugoid real
        reals = sorted([l.real for l in lam if abs(l.imag) <= 1e-9])
        if cplx:
            p = _pair(cplx[0])
            if abs(cplx[0]) > 0.5:
                out["short_period"] = p
                out["phugoid"] = {"wn": math.nan, "zeta": math.nan, "real_roots": reals}
            else:
                out["phugoid"] = p
                out["short_period"] = {"wn": math.sqrt(abs(reals[0] * reals[-1])) if len(reals) >= 2 else math.nan,
                                       "zeta": 1.0, "real_roots": reals}
    n_alpha = qS * CLa / (m * 9.80665)
    sp = out.get("short_period", {})
    out["n_alpha"] = n_alpha
    out["CAP"] = sp.get("wn", math.nan) ** 2 / n_alpha if n_alpha > 0 else math.nan
    return out


def _modes_lat(A):
    lam = np.linalg.eigvals(A)
    cplx = [l for l in lam if l.imag > 1e-9]
    reals = sorted([l.real for l in lam if abs(l.imag) <= 1e-9], key=abs)
    out = {"eig": [complex(x) for x in lam]}
    if cplx:
        out["dutch_roll"] = _pair(cplx[0])
    if len(reals) >= 2:
        sp, rl = reals[0], reals[-1]
        out["spiral"] = {"lambda": sp, "T2_s": math.log(2) / sp if sp > 0 else math.inf,
                         "T_half_s": math.log(2) / -sp if sp < 0 else math.inf, "stable": sp < 0}
        out["roll"] = {"lambda": rl, "tau_s": -1 / rl if rl < 0 else math.inf}
    return out


# MIL-F-8785C (1980) limits, Class I. Category B (cruise) default; C (terminal) available.
MIL_F_8785C = {
    "short_period_zeta": {"A": [(0.35, 1.30), (0.25, 2.00), (0.15, math.inf)],
                          "B": [(0.30, 2.00), (0.20, 2.00), (0.15, math.inf)],
                          "C": [(0.35, 1.30), (0.25, 2.00), (0.15, math.inf)]},          # Table IV
    "CAP": {"A": [(0.28, 3.6), (0.16, 10.0), (0.16, math.inf)], "B": [(0.085, 3.6), (0.038, 10.0), (0.038, math.inf)],
            "C": [(0.16, 3.6), (0.096, 10.0), (0.096, math.inf)]},                       # Figs 1–3 (approx. bounds)
    "phugoid_zeta_min": [0.04, 0.0],                                                    # 3.2.1.2 (L3: T2 ≥ 55 s)
    "dutch_roll": {"A": [(0.19, 0.35, 1.0), (0.02, 0.05, 0.4), (0.0, -math.inf, 0.4)],
                   "B": [(0.08, 0.15, 0.4), (0.02, 0.05, 0.4), (0.0, -math.inf, 0.4)],
                   "C": [(0.08, 0.15, 1.0), (0.02, 0.05, 0.4), (0.0, -math.inf, 0.4)]},  # Table VI (ζ, ζω, ω)
    "roll_tau_max": {"A": [1.0, 1.4, 10.0], "B": [1.4, 3.0, 10.0], "C": [1.0, 1.4, 10.0]},  # Table VII, Class I
    "spiral_T2_min": {"A": [12.0, 8.0, 4.0], "B": [20.0, 8.0, 4.0], "C": [12.0, 8.0, 4.0]},  # Table VIII
}


def handling_qualities(modes: dict, category: str = "B") -> list[dict]:
    """Levels per MIL-F-8785C (Class I aircraft, flight-phase category A/B/C). Level 4 = worse than Level 3.
    Piloted-aircraft standard: for a UAV the levels are indicative only (no Froude/dynamic scaling applied)."""
    L = MIL_F_8785C
    rows = []

    def level_range(v, bands):
        for i, (lo, hi) in enumerate(bands):
            if lo <= v <= hi:
                return i + 1
        return 4

    lon, lat = modes.get("longitudinal") or {}, modes.get("lateral") or {}
    sp = lon.get("short_period", {})
    if sp:
        rows.append({"key": "short_period", "modo": "período curto ζ", "valor": sp.get("zeta"), "nível": level_range(sp.get("zeta", -1),
                     L["short_period_zeta"][category]), "limite N1": "%.2f–%.2f" % L["short_period_zeta"][category][0],
                     "ref": "MIL-F-8785C Table IV"})
        rows.append({"key": "CAP", "modo": "CAP = ω²/(n/α) [1/(g s²)]", "valor": lon.get("CAP"),
                     "nível": level_range(lon.get("CAP", -1), L["CAP"][category]),
                     "limite N1": "%.3g–%.3g" % L["CAP"][category][0], "ref": "MIL-F-8785C Figs. 1–3"})
    ph = lon.get("phugoid", {})
    if ph:
        z = ph.get("zeta", math.nan)
        lv = 1 if z >= L["phugoid_zeta_min"][0] else (2 if z >= 0 else 3 if z == z else 4)
        if z != z and "real_roots" in ph:
            lv = 1 if max(ph["real_roots"]) < 0 else 3
        rows.append({"key": "phugoid", "modo": "fugóide ζ", "valor": z, "nível": lv, "limite N1": "≥ 0.04", "ref": "MIL-F-8785C 3.2.1.2"})
    dr = lat.get("dutch_roll")
    if dr:
        z, wn = dr["zeta"], dr["wn"]
        lv = 4
        for i, (zm, zwm, wm) in enumerate(L["dutch_roll"][category]):
            if z >= zm and z * wn >= zwm and wn >= wm:
                lv = i + 1
                break
        rows.append({"key": "dutch_roll", "modo": "rolamento holandês ζ / ζω / ω", "valor": f"{z:.3f} / {z * wn:.3f} / {wn:.2f}", "nível": lv,
                     "limite N1": "%.2f / %.2f / %.1f" % L["dutch_roll"][category][0], "ref": "MIL-F-8785C Table VI"})
    rl = lat.get("roll")
    if rl:
        t = rl["tau_s"]
        lim = L["roll_tau_max"][category]
        lv = next((i + 1 for i, x in enumerate(lim) if t <= x), 4)
        rows.append({"key": "roll", "modo": "rolamento τ_R [s]", "valor": t, "nível": lv, "limite N1": f"≤ {lim[0]:g}",
                     "ref": "MIL-F-8785C Table VII"})
    spi = lat.get("spiral")
    if spi:
        T2 = spi["T2_s"]
        lim = L["spiral_T2_min"][category]
        lv = next((i + 1 for i, x in enumerate(lim) if T2 >= x), 4)
        rows.append({"key": "spiral", "modo": "espiral T2 [s] (∞ = estável)", "valor": T2, "nível": lv, "limite N1": f"≥ {lim[0]:g}",
                     "ref": "MIL-F-8785C Table VIII"})
    return rows


def plot_root_locus(modes: dict, path, title: str = ""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for key, mk, lab in (("longitudinal", "bo", "longitudinal"), ("lateral", "rs", "lateral")):
        md = modes.get(key)
        if md:
            e = np.array(md["eig"])
            ax.plot(e.real, e.imag, mk, label=lab)
    ax.axvline(0, color="k", lw=0.6)
    ax.set_xlabel("Re λ [1/s]")
    ax.set_ylabel("Im λ [rad/s]")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    ax.set_title(title or "Valores próprios (Nelson / Etkin)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
