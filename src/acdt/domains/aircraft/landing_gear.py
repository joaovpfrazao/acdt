"""Landing-gear layout and the limit landing load (conceptual).

Geometry, Raymer, *Aircraft Design: A Conceptual Approach*, 6th ed., 2018, Ch. 11, and Currey,
*Aircraft Landing Gear Design: Principles and Practices*, 1988:

* Tricycle tip-back: the main wheels sit aft of the most aft CG by an angle of 15° from the vertical.
* Overturn: the angle from the vertical at the CG down to the tip-over axis (nose wheel to main wheel)
  is not more than 63°. The forward CG is the critical one.
* The nose wheel carries 8–15 % of the weight over that CG range (Raymer's published band).
  A mission may replace the band when a cited weighing of that aeroplane sits outside it.
* Taildragger: the same 15° puts the main wheels ahead of the most forward CG, so the aeroplane sits
  on its tail. Overturn is measured from the tail wheel; the aft CG is critical.

Limit landing, 14 CFR 23.473 as on the eCFR of 25 July 2017 (the numbering CS 23.473 used before the
CS-23 rewrite; ASTM F3116 is the means of compliance of the rewritten paragraph, not re-derived here):

* (d) descent speed V = 4.4 (W/S)^(1/4) ft/s with W/S in lb/ft², but not below 7 and not above 10.
  Applied at the design landing weight.
* (b) that weight may be as low as 95 % of the maximum weight when the fuel clause is met. This code
  uses ``weights.components.landing_weight_fraction`` (default 0.95). It does not check the fuel clause.
* (e) wing lift up to two thirds of the weight may be assumed during the impact. Then
  n_gear = n_inertia − L/W.
* (g) the inertia load factor used for design is at least 2.67, and the ground-reaction factor at
  maximum weight is at least 2.0.

Energy, Currey 1988 §5.3 (the stroke section; Ch. 2 is the design process and does not give this
balance): η_s S N W + η_t S_t N W = W V²/(2g) + (W − L)(S + S_t), so
n = [V²/(2g) + (1 − κ)(S + S_t)] / (η_s S + η_t S_t), with κ = L/W. With no tyre stroke that is
V²/(2 g η s) + (1 − κ)/η. Oleo efficiency 0.80 and tyre efficiency 0.47 are the Raymer Ch. 11 values.
The stroke is the one that develops the gear load factor already used in the weight equations
(``gear_load_factor``, Raymer Table 11.5, default 3 for general aviation), after the regulatory floors.

Not in this step: wheel spin-up and spring-back, side load, braking, rebound, and a tyre deflection
the user did not give. Those remain open in the ground-load paragraphs.

Two defaults are not from those sources. The main-gear strut length
(``weights_detailed.DEFAULT_MAIN_GEAR_LENGTH_M``) and the tailwheel at
``DEFAULT_TAILWHEEL_FUSELAGE_FRACTION`` of the fuselage length are marked PRESSUPOSTO in the notes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from acdt import G0

from .weights_detailed import DEFAULT_MAIN_GEAR_LENGTH_M, FT, PSF

# PRESSUPOSTO: no cited tailwheel station as a fraction of fuselage length.
# Replace with landing_gear.x_tail_m.
DEFAULT_TAILWHEEL_FUSELAGE_FRACTION = 0.95

# Raymer 2018 Ch. 11 shock-absorber efficiencies.
ABSORBER_ETA = {"oleo": 0.80, "tire": 0.47}

# 14 CFR 23.473(g).
INERTIA_FLOOR = 2.67
REACTION_FLOOR = 2.0


def limit_descent_speed_ft_s(wing_loading_psf: float) -> float:
    """14 CFR 23.473(d): V = 4.4 (W/S)^(1/4) ft/s, clamped to [7, 10]. W/S in lb/ft²."""
    if wing_loading_psf <= 0:
        raise ValueError("wing loading must be positive")
    return float(min(10.0, max(7.0, 4.4 * wing_loading_psf ** 0.25)))


def wing_loading_psf(weight_kg: float, area_m2: float) -> float:
    return (weight_kg * G0 / area_m2) / PSF


def gear_load_factor(v_m_s: float, stroke_m: float, eta: float, wing_lift_fraction: float,
                     tire_stroke_m: float = 0.0, eta_tire: float = ABSORBER_ETA["tire"],
                     g: float = G0) -> float:
    """Ground-reaction factor from Currey 1988 §5.3.

    η_s S N + η_t S_t N = V²/(2g) + (1 − κ)(S + S_t), so
    N = [V²/(2g) + (1 − κ)(S + S_t)] / (η_s S + η_t S_t).
    With no tyre stroke, N = V²/(2 g η S) + (1 − κ)/η. κ = L/W (14 CFR 23.473(e) allows up to 2/3).
    """
    s_eff = eta * stroke_m + eta_tire * tire_stroke_m
    if s_eff <= 0:
        return math.inf
    s_geom = stroke_m + tire_stroke_m
    return v_m_s ** 2 / (2 * g * s_eff) + (1.0 - wing_lift_fraction) * s_geom / s_eff


def stroke_for_load_factor(v_m_s: float, n_gear: float, eta: float, wing_lift_fraction: float,
                           tire_stroke_m: float = 0.0, eta_tire: float = ABSORBER_ETA["tire"],
                           g: float = G0) -> float:
    """Oleo stroke that develops ``n_gear`` (Currey 1988 §5.3). A negative result means the tyre stroke alone is enough."""
    if eta <= 0:
        return math.inf
    lift = 1.0 - wing_lift_fraction
    denom = n_gear * eta - lift
    if denom <= 0:
        return math.inf
    rhs = v_m_s ** 2 / (2 * g) + tire_stroke_m * (lift - n_gear * eta_tire)
    return rhs / denom


def adopted_factors(n_gear_energy: float, wing_lift_fraction: float) -> tuple[float, float]:
    """Design factors after 14 CFR 23.473(g): inertia ≥ 2.67, ground reaction ≥ 2.0.

    Returns (n_inertia, n_gear). The two floors are applied to the two factors; they are not forced
    to differ by κ once a floor has raised only one of them.
    """
    n_g = max(n_gear_energy, REACTION_FLOOR)
    n_i = max(n_gear_energy + wing_lift_fraction, INERTIA_FLOOR)
    return n_i, n_g


def target_gear_factor(gear_load_factor_struct: float, wing_lift_fraction: float) -> float:
    """Structural gear factor raised, if needed, so both regulatory floors are met at κ."""
    n_g = max(gear_load_factor_struct, REACTION_FLOOR)
    if n_g + wing_lift_fraction < INERTIA_FLOOR:
        n_g = INERTIA_FLOOR - wing_lift_fraction
    return n_g


def angle_from_vertical_deg(dx_m: float, h_cg_m: float) -> float:
    """atan(dx / h_cg), degrees. Used for tip-back (dx = x_main − x_cg) and tail-down clearance."""
    if h_cg_m <= 0:
        return math.nan
    return math.degrees(math.atan(dx_m / h_cg_m))


def overturn_angle_deg(x_apex: float, x_main: float, half_track: float, x_cg: float, h_cg: float) -> float:
    """Overturn angle, degrees. The tip-over axis joins the apex wheel to one main wheel.

    d = (t/2) |x_cg − x_apex| / sqrt((t/2)² + wheelbase²), θ = atan(h_cg / d).
    Raymer Ch. 11; Currey 1988. Infinite if the track is zero or the CG is on the apex station.
    """
    wb = abs(x_main - x_apex)
    rel = abs(x_cg - x_apex)
    if half_track <= 0 or rel <= 0 or h_cg <= 0 or wb <= 0:
        return math.inf
    d = half_track * rel / math.sqrt(half_track ** 2 + wb ** 2)
    return math.degrees(math.atan(h_cg / d))


def min_half_track(x_apex: float, x_main: float, x_cg: float, h_cg: float, theta_max_deg: float) -> float:
    """Smallest half-track for which the overturn angle is ``theta_max_deg``. Infinite if no track works."""
    wb = abs(x_main - x_apex)
    rel = abs(x_cg - x_apex)
    if h_cg <= 0 or wb <= 0 or theta_max_deg <= 0 or theta_max_deg >= 90:
        return math.inf
    d_req = h_cg / math.tan(math.radians(theta_max_deg))
    if rel <= d_req:
        return math.inf
    return d_req * wb / math.sqrt(rel ** 2 - d_req ** 2)


def static_fraction_front(x_front: float, x_rear: float, x_cg: float) -> float:
    """Fraction of the weight on the front gear (nose, or the tail wheel when it is the rear contact).

    f_front = (x_rear − x_cg) / (x_rear − x_front). Statics of a two-post gear, Raymer Ch. 11.
    """
    span = x_rear - x_front
    if abs(span) < 1e-9:
        return math.nan
    return (x_rear - x_cg) / span


def place_tricycle(x_cg_fwd: float, x_cg_aft: float, h_cg: float, tipback_deg: float = 15.0,
                   nose_fraction_min: float = 0.08, nose_fraction_max: float = 0.15,
                   x_nose_min: float = 0.0, x_main_max: float | None = None,
                   x_main_fixed: float | None = None, prefer: str = "longest") -> tuple[float, float] | None:
    """Main gear on the tip-back ray, nose gear inside the nose-load band and the fuselage.

    Raymer's published band is 8–15 %. ``nose_fraction_min`` and ``nose_fraction_max`` replace it.

    With the main wheel a distance ``dx`` aft of the aft CG, the wheelbase ``B`` has to lie between
    ``(dx + Δx_cg) / nose_fraction_max`` and ``dx / nose_fraction_min`` (Raymer 2018 Ch. 11). The
    longest such ``B`` that keeps the nose at or aft of ``x_nose_min`` is used. ``None`` when the band
    is empty or every wheelbase in it puts a wheel outside the fuselage — the nose is not parked
    ahead of the datum.
    """
    if not (0.0 < nose_fraction_min < 1.0) or not (0.0 < nose_fraction_max < 1.0):
        raise ValueError("nose fraction must be between 0 and 1")
    if nose_fraction_min > nose_fraction_max + 1e-12:
        raise ValueError("nose_fraction_min cannot exceed nose_fraction_max")
    dx = h_cg * math.tan(math.radians(tipback_deg))
    if h_cg <= 0 or dx <= 0 or x_cg_aft + 1e-9 < x_cg_fwd:
        return None
    x_main = x_cg_aft + dx if x_main_fixed is None else float(x_main_fixed)
    if x_main_max is not None and x_main > x_main_max + 1e-6:
        return None
    lever_aft = x_main - x_cg_aft
    lever_fwd = x_main - x_cg_fwd
    if lever_aft <= 1e-9 or lever_fwd <= 1e-9:
        return None
    b_min = lever_fwd / nose_fraction_max
    b_max = lever_aft / nose_fraction_min
    if b_min > b_max + 1e-6:
        return None
    b = min(b_max, x_main - x_nose_min)
    if b + 1e-6 < b_min:
        return None
    if prefer == "shortest":   # opt-in: top of the nose-load band (shorter nose leg / wheelbase)
        b = b_min
    return x_main - b, x_main


def place_taildragger(x_cg_fwd: float, h_cg: float, x_tail: float, tipback_deg: float = 15.0) -> float:
    """Main gear ahead of the forward CG by the same 15° angle (the aeroplane rests on the tail wheel)."""
    return x_cg_fwd - h_cg * math.tan(math.radians(tipback_deg))


@dataclass
class LandingGearResult:
    kind: str
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    x_nose_m: float | None = None
    x_main_m: float | None = None
    x_tail_m: float | None = None
    track_m: float | None = None
    h_cg_m: float | None = None
    tipback_deg: float | None = None
    overturn_deg: float | None = None
    nose_fraction_fwd: float | None = None
    nose_fraction_aft: float | None = None
    rotation_deg: float | None = None
    descent_ft_s: float | None = None
    descent_m_s: float | None = None
    wing_loading_psf: float | None = None
    landing_weight_kg: float | None = None
    n_inertia: float | None = None
    n_gear: float | None = None
    stroke_m: float | None = None
    stroke_no_lift_m: float | None = None
    eta: float | None = None
    wing_lift_fraction: float | None = None
    geometry_ok: bool | None = None
    load_factor_ok: bool | None = None
    geometry_summary: str = ""
    load_summary: str = ""

    def summary(self) -> dict:
        return {
            "kind": self.kind,
            "geometry_ok": self.geometry_ok,
            "load_factor_ok": self.load_factor_ok,
            "geometry_summary": self.geometry_summary,
            "load_summary": self.load_summary,
            "x_nose_m": self.x_nose_m,
            "x_main_m": self.x_main_m,
            "x_tail_m": self.x_tail_m,
            "track_m": self.track_m,
            "h_cg_m": self.h_cg_m,
            "tipback_deg": self.tipback_deg,
            "overturn_deg": self.overturn_deg,
            "nose_fraction_fwd": self.nose_fraction_fwd,
            "nose_fraction_aft": self.nose_fraction_aft,
            "rotation_deg": self.rotation_deg,
            "descent_ft_s": self.descent_ft_s,
            "descent_m_s": self.descent_m_s,
            "wing_loading_psf": self.wing_loading_psf,
            "landing_weight_kg": self.landing_weight_kg,
            "n_inertia": self.n_inertia,
            "n_gear": self.n_gear,
            "stroke_m": self.stroke_m,
            "stroke_no_lift_m": self.stroke_no_lift_m,
            "eta": self.eta,
            "wing_lift_fraction": self.wing_lift_fraction,
            "notes": self.notes,
            "checks": [{"key": k, "ok": ok, "message": msg} for k, ok, msg in self.checks],
        }


def _cg_ends(res) -> tuple[float, float] | None:
    wb = getattr(res, "weight_balance", None)
    if wb is not None and wb.x_min_m is not None:
        return wb.x_min_m, wb.x_max_m
    st = getattr(res, "stability", None)
    if st is not None and st.cases:
        xs = [c.x_cg for c in st.cases]
        return min(xs), max(xs)
    return None


def _loads(res, out: LandingGearResult, comp: dict, opts: dict, area: float) -> None:
    frac = float(comp.get("landing_weight_fraction", 0.95))
    w_land = frac * res.sizing.W0
    ws = wing_loading_psf(w_land, area)
    v_ft = limit_descent_speed_ft_s(ws)
    v = v_ft * FT
    kappa = float(opts.get("wing_lift_fraction", 2.0 / 3.0))
    if kappa < 0:
        raise ValueError("wing_lift_fraction must be ≥ 0")
    if kappa > 2.0 / 3.0 + 1e-9:
        out.notes.append("κ limitado a 2/3: 14 CFR 23.473(e) não permite mais sustentação da asa no impacto.")
        kappa = 2.0 / 3.0
    absorber = opts.get("absorber", "oleo")
    eta = float(opts["eta"]) if opts.get("eta") is not None else ABSORBER_ETA.get(absorber)
    if eta is None:
        raise ValueError(f"absorber '{absorber}' has no Raymer efficiency; set landing_gear.eta")
    eta_tire = ABSORBER_ETA["tire"]
    tire = float(opts.get("tire_stroke_m") or 0.0)
    n_struct = float(comp.get("gear_load_factor", 3.0))
    n_target = target_gear_factor(n_struct, kappa)
    given = opts.get("stroke_m")
    if given is None:
        stroke = max(0.0, stroke_for_load_factor(v, n_target, eta, kappa, tire, eta_tire))
        n_energy = n_target
        max_stroke = opts.get("max_stroke_m")
        if max_stroke is not None and stroke > float(max_stroke) + 1e-9:
            out.load_factor_ok = False
            load_ok = False
            load_msg = (f"curso necessário {stroke:.3f} m excede landing_gear.max_stroke_m = {float(max_stroke):.3f} m "
                        f"para n_g = {n_target:.2f}")
        else:
            out.load_factor_ok = None
            load_ok = True
            load_msg = (f"curso {stroke:.3f} m para n_g = {n_target:.2f} (fator já usado no peso, "
                        f"com pisos de 14 CFR 23.473(g))")
    else:
        stroke = float(given)
        n_energy = gear_load_factor(v, stroke, eta, kappa, tire, eta_tire)
        if n_energy > n_struct + 1e-6:
            out.load_factor_ok = False
            load_ok = False
            load_msg = (f"com curso {stroke:.3f} m o impacto pede n_g = {n_energy:.2f}, acima do "
                        f"gear_load_factor {n_struct:.2f} usado nas equações de peso")
        else:
            out.load_factor_ok = None
            load_ok = True
            load_msg = f"curso dado {stroke:.3f} m desenvolve n_g = {n_energy:.2f} ≤ {n_struct:.2f}"
    n_i, n_g = adopted_factors(n_energy, kappa)
    no_lift = max(0.0, stroke_for_load_factor(v, target_gear_factor(n_struct, 0.0), eta, 0.0, tire, eta_tire))
    out.descent_ft_s = v_ft
    out.descent_m_s = v
    out.wing_loading_psf = ws
    out.landing_weight_kg = w_land
    out.n_inertia = n_i
    out.n_gear = n_g
    out.stroke_m = stroke
    out.stroke_no_lift_m = no_lift
    out.eta = eta
    out.wing_lift_fraction = kappa
    out.load_summary = (
        f"W_aterragem {w_land:.0f} kg ({100 * frac:.0f} % de W0; 14 CFR 23.473(b) permite 95 % sem "
        f"verificar a cláusula de combustível); W/S {ws:.2f} lb/ft²; V = {v_ft:.2f} ft/s "
        f"({v:.2f} m/s, 23.473(d)); n_inércia {n_i:.2f}; n_reação {n_g:.2f}; {load_msg}; "
        f"η = {eta:.2f} ({absorber}); κ = {kappa:.3f} (teto regulamentar 2/3). "
        f"Sem sustentação da asa o curso sobe para {no_lift:.3f} m. "
        f"Spin-up, mola de retorno, carga lateral e travões não entram neste passo.")
    out.checks.append(("gear:stroke", load_ok, load_msg))
    out.notes.append("O curso é o do amortecedor para o n_g das equações de peso (Raymer Tabela 11.5 no "
                     "valor por omissão). O pneu (η = 0.47) só conta se landing_gear.tire_stroke_m for dado.")
    out.notes.append("Balanço de energia: Currey 1988 §5.3, "
                     "N = [V²/(2g) + (1−κ)(S+S_t)] / (η_s S + η_t S_t).")


def analyse_landing_gear(res) -> LandingGearResult:
    """Layout and limit landing load for the converged aircraft. ``landing_gear: none`` is recorded and skipped."""
    comp = ((getattr(res.spec, "assumptions", None) or {}).get("weights") or {}).get("components") or {}
    opts = (res.spec.assumptions.get("landing_gear") or {}) if getattr(res, "spec", None) else {}
    kind = comp.get("landing_gear", "tricycle")
    out = LandingGearResult(kind=kind)
    if kind == "none":
        out.notes.append("Sem trem de aterragem (landing_gear: none) — lançamento e recuperação ficam por analisar.")
        out.geometry_summary = "sem trem"
        out.load_summary = "sem trem; 14 CFR 23.473 não aplicado"
        return out
    ends = _cg_ends(res)
    cfg = getattr(res, "config", None)
    if ends is None or cfg is None or not math.isfinite(getattr(res, "S", float("nan"))):
        out.notes.append("Trem não calculado: falta o envelope de CG ou a geometria.")
        return out
    x_fwd, x_aft = ends
    fus = cfg.fuselage
    if opts.get("h_cg_m") is not None:
        h = float(opts["h_cg_m"])
        out.notes.append("h_cg dado pelo utilizador (landing_gear.h_cg_m).")
    else:
        raw_length = comp.get("main_gear_length_m")
        if raw_length is None:
            length = DEFAULT_MAIN_GEAR_LENGTH_M
            length_note = (
                f" O comprimento por omissão é {length:.2f} m (PRESSUPOSTO: a Eq. 15.50 de Raymer "
                "recebe o comprimento do montante como dado e não fixa este valor). "
                "Substituir em weights.components.main_gear_length_m.")
        else:
            length = float(raw_length)
            length_note = ""
        h = length + 0.5 * fus.max_diameter
        out.notes.append("h_cg PRESSUPOSTO = comprimento do trem principal + raio da fuselagem "
                         "(CG no eixo da fuselagem; o mesmo pressuposto de flightsim/controls.py). "
                         "Substituir por landing_gear.h_cg_m." + length_note)
    out.h_cg_m = h
    tip = float(opts.get("tipback_deg", 15.0))
    theta_max = float(opts.get("overturn_max_deg", 63.0))
    f_min = float(opts.get("nose_fraction_min", 0.08))
    f_max = float(opts.get("nose_fraction_max", 0.15))
    x_nose_min = float(opts["x_nose_min_m"]) if opts.get("x_nose_min_m") is not None else 0.0
    x_main_max = float(opts["x_main_max_m"]) if opts.get("x_main_max_m") is not None else fus.length
    user_geom = opts.get("x_main_m") is not None and (opts.get("x_nose_m") is not None or opts.get("x_tail_m") is not None)

    if kind == "tricycle":
        if opts.get("x_main_m") is not None and opts.get("x_nose_m") is not None:
            x_nose, x_main = float(opts["x_nose_m"]), float(opts["x_main_m"])
            out.notes.append("Posições do trem dadas pelo utilizador.")
        else:
            fixed_main = float(opts["x_main_m"]) if opts.get("x_main_m") is not None else None
            if fixed_main is not None:
                out.notes.append("x_main_m dado sem x_nose_m: o principal fica nesse valor e a roda de nariz "
                                 f"é a mais longa da banda {100 * f_min:.1f}–{100 * f_max:.1f} % que ainda cabe "
                                 "(Raymer Cap. 11).")
            placed = place_tricycle(x_fwd, x_aft, h, tip, f_min, f_max, x_nose_min, x_main_max, fixed_main)
            if placed is None:
                out.checks.append(("gear:position", False,
                                   f"não há entre-eixos na banda {100 * f_min:.1f}–{100 * f_max:.1f} % com as duas "
                                   "rodas dentro da fuselagem "
                                   f"(0–{x_main_max:.3f} m, nariz ≥ {x_nose_min:.3f} m; Raymer Cap. 11)"))
                out.checks.append(("gear:tipback", False, "sem posição de trem"))
                _loads(res, out, comp, opts, res.S)
                out.geometry_ok = False
                out.geometry_summary = (
                    f"{kind}: sem posição na fuselagem; h_cg {h:.2f} m. "
                    f"Nenhum entre-eixos da banda {100 * f_min:.1f}–{100 * f_max:.1f} % "
                    f"mantém o nariz em x ≥ {x_nose_min:.2f} m e o principal até {x_main_max:.2f} m "
                    "(Raymer Cap. 11).")
                return out
            x_nose, x_main = placed
            out.notes.append("Trem principal no raio de tombo de "
                             f"{tip:.0f}° atrás do CG traseiro; entre-eixos na banda "
                             f"{100 * f_min:.1f}–{100 * f_max:.1f} % na roda de nariz (Raymer Cap. 11), "
                             "o mais longo que mantém o nariz dentro da fuselagem.")
        out.x_nose_m, out.x_main_m = x_nose, x_main
        fits = x_nose >= x_nose_min - 1e-6 and x_main <= x_main_max + 1e-6 and x_nose < x_main
        out.checks.append(("gear:position", fits,
                           f"nariz x = {x_nose:.3f} m, principal x = {x_main:.3f} m, fuselagem 0–{x_main_max:.3f} m"
                           + ("" if fits else " — a geometria de Raymer não cabe: o CG traseiro está perto do nariz "
                              "para este h_cg, ou o intervalo de CG é longo para a banda de "
                              f"{100 * f_min:.1f}–{100 * f_max:.1f} %")))
        out.tipback_deg = angle_from_vertical_deg(x_main - x_aft, h)
        # A placed gear meets 15° by construction. A user-given gear still has to clear it.
        tip_ok = out.tipback_deg + (1e-6 if user_geom else 0.05) >= tip
        out.checks.append(("gear:tipback", bool(tip_ok),
                           f"tombo {out.tipback_deg:.1f}° no CG traseiro (mínimo {tip:.0f}°, Raymer Cap. 11)"))
        f_fwd = static_fraction_front(x_nose, x_main, x_fwd)
        f_aft = static_fraction_front(x_nose, x_main, x_aft)
        out.nose_fraction_fwd, out.nose_fraction_aft = f_fwd, f_aft
        band_ok = (math.isfinite(f_fwd) and math.isfinite(f_aft) and f_min - 1e-6 <= f_aft
                   and f_fwd <= f_max + 1e-6 and f_aft <= f_fwd + 1e-6)
        out.checks.append(("gear:nose_load", bool(band_ok),
                           f"fração na roda de nariz {100 * f_aft:.1f} % (CG traseiro) … {100 * f_fwd:.1f} % "
                           f"(CG dianteiro); banda {100 * f_min:.1f}–{100 * f_max:.1f} % "
                           "(Raymer Cap. 11; omissão 8.0–15.0 %, substituível na missão)"))
        apex, x_crit = x_nose, x_fwd
    elif kind == "taildragger":
        if opts.get("x_tail_m") is not None:
            x_tail = float(opts["x_tail_m"])
        else:
            x_tail = DEFAULT_TAILWHEEL_FUSELAGE_FRACTION * fus.length
            out.notes.append(
                f"Roda de cauda em {DEFAULT_TAILWHEEL_FUSELAGE_FRACTION:.2f}·L ({x_tail:.2f} m). "
                "PRESSUPOSTO: não há fração citada do comprimento da fuselagem. "
                "Substituir por landing_gear.x_tail_m.")
        if opts.get("x_main_m") is not None:
            x_main = float(opts["x_main_m"])
            out.notes.append("Trem principal dado pelo utilizador.")
        else:
            x_main = place_taildragger(x_fwd, h, x_tail, tip)
            out.notes.append(f"Trem principal {tip:.0f}° à frente do CG dianteiro (Raymer Cap. 11, convencional).")
        out.x_main_m, out.x_tail_m = x_main, x_tail
        out.tipback_deg = angle_from_vertical_deg(x_fwd - x_main, h)
        tip_ok = out.tipback_deg + 0.05 >= tip
        out.checks.append(("gear:tipback", bool(tip_ok),
                           f"ângulo de nariz {out.tipback_deg:.1f}° no CG dianteiro (mínimo {tip:.0f}°)"))
        between = x_main < x_fwd + 1e-6 and x_tail > x_aft - 1e-6 and x_main < x_tail
        out.checks.append(("gear:position", between,
                           f"principal x = {x_main:.3f} m, cauda x = {x_tail:.3f} m; o CG "
                           f"({x_fwd:.3f}–{x_aft:.3f} m) tem de ficar entre as rodas"))
        f_tail_fwd = 1.0 - static_fraction_front(x_main, x_tail, x_fwd)
        f_tail_aft = 1.0 - static_fraction_front(x_main, x_tail, x_aft)
        out.nose_fraction_fwd, out.nose_fraction_aft = f_tail_fwd, f_tail_aft
        out.notes.append("A banda de fração no nariz (Raymer Cap. 11; omissão 8–15 %) é critério de triciclo. "
                         "No convencional reporta-se a fração na roda de cauda "
                         f"({100 * f_tail_fwd:.1f} % à frente, {100 * f_tail_aft:.1f} % atrás) sem a transformar em verificação.")
        apex, x_crit = x_tail, x_aft
    elif kind in ("ski", "skis"):
        ski = opts.get("ski") if isinstance(opts.get("ski"), dict) else None
        if not ski or ski.get("length_m") is None:
            out.checks.append(("gear:position", None,
                               "ski unassessed: assumptions.landing_gear.ski.length_m em falta — "
                               "recusando um comprimento inventado (Raymer Cap. 11)"))
            out.geometry_ok = None
            out.geometry_summary = "ski: unassessed (sem geometria)"
            out.notes.append("Esqui: sem length_m não há método aplicável; não se substitui por triciclo.")
            _loads(res, out, comp, opts, res.S)
            return out
        length = float(ski["length_m"])
        if opts.get("x_main_m") is not None and opts.get("x_tail_m") is not None:
            x_fore, x_ski_aft = float(opts["x_main_m"]), float(opts["x_tail_m"])
        elif ski.get("attach_x") is not None:
            mid = float(ski["attach_x"])
            x_fore, x_ski_aft = mid - 0.5 * length, mid + 0.5 * length
        else:
            mid = 0.5 * (x_fwd + x_aft)
            x_fore, x_ski_aft = mid - 0.5 * length, mid + 0.5 * length
            out.notes.append(f"PRESSUPOSTO ski.attach_x = meio do CG ({mid:.3f} m).")
        out.x_main_m, out.x_tail_m = x_fore, x_ski_aft
        tip = float(opts.get("tipback_deg", 15.0))
        dx_req = h * math.tan(math.radians(tip))
        tip_ok = x_ski_aft + 1e-6 >= (x_aft + dx_req)
        out.tipback_deg = angle_from_vertical_deg(x_ski_aft - x_aft, h)
        out.checks.append(("gear:tipback", bool(tip_ok),
                           f"contacto aft do esqui {x_ski_aft:.3f} m vs CG traseiro {x_aft:.3f} m + "
                           f"{dx_req:.3f} m (tombo {tip:.0f}°, Raymer Cap. 11)"))
        between = x_fore < x_fwd + 1e-6 and x_ski_aft > x_aft - 1e-6
        out.checks.append(("gear:position", between,
                           f"esqui [{x_fore:.3f}, {x_ski_aft:.3f}] m; CG ({x_fwd:.3f}–{x_aft:.3f} m)"))
        out.notes.append("Banda 8–15 % é critério de triciclo; esqui reporta contactos fore/aft.")
        out.notes.append("Folga da hélice 14 CFR 23.925: usar a montagem (gear_layout) com disco.")
        apex, x_crit = x_ski_aft, x_aft
    else:
        out.notes.append(f"landing_gear '{kind}' não tem método — usar tricycle, taildragger, ski ou none.")
        out.checks.append(("gear:position", None,
                           f"landing_gear '{kind}' unassessed — sem método citado (não substituído por triciclo)"))
        out.geometry_ok = None
        return out

    if opts.get("track_m") is not None:
        track = float(opts["track_m"])
        out.overturn_deg = overturn_angle_deg(apex, out.x_main_m, track / 2, x_crit, h)
        ov_ok = out.overturn_deg <= theta_max + 1e-6
        out.notes.append("Bitola dada pelo utilizador.")
    else:
        half = min_half_track(apex, out.x_main_m, x_crit, h, theta_max)
        if math.isfinite(half):
            track = 2 * half
            out.overturn_deg = overturn_angle_deg(apex, out.x_main_m, half, x_crit, h)
            ov_ok = True
        else:
            track = None
            out.overturn_deg = math.inf
            ov_ok = False
    out.track_m = track
    shown = "sem solução" if out.overturn_deg is None or not math.isfinite(out.overturn_deg) else f"{out.overturn_deg:.1f}°"
    track_txt = "n/d" if track is None else f"{track:.3f} m"
    out.checks.append(("gear:overturn", bool(ov_ok),
                       f"capotagem {shown} (máximo {theta_max:.0f}°, Raymer Cap. 11); bitola {track_txt}"))

    z_belly = h - 0.5 * fus.max_diameter
    if kind == "tricycle" and out.x_main_m is not None and fus.length > out.x_main_m and z_belly > 0:
        out.rotation_deg = angle_from_vertical_deg(z_belly, fus.length - out.x_main_m)
        rot_min = float(opts.get("rotation_min_deg", 10.0))
        rot_ok = out.rotation_deg + 1e-6 >= rot_min
        out.checks.append(("gear:rotation", rot_ok,
                           f"folga de rotação {out.rotation_deg:.1f}° com o ventre no diâmetro máximo prolongado "
                           f"até à cauda (conservador; Raymer Cap. 11 pede 10–15°). Mínimo usado: {rot_min:.0f}°"))
        out.notes.append("A folga de cauda ignora o cone real: um cone que sobe aumenta o ângulo.")
    elif kind == "tricycle":
        out.notes.append("Folga de rotação não calculada (h_cg não chega ao eixo da fuselagem, ou o trem principal "
                         "está na popa ou atrás dela). Dar landing_gear.h_cg_m.")

    _loads(res, out, comp, opts, res.S)
    geom = [ok for key, ok, _ in out.checks if key != "gear:stroke"]
    out.geometry_ok = bool(geom) and all(geom)
    track_s = "n/d" if out.track_m is None else f"{out.track_m:.2f} m"
    where = (f"nariz {out.x_nose_m:.2f} m, principal {out.x_main_m:.2f} m" if kind == "tricycle"
             else f"principal {out.x_main_m:.2f} m, cauda {out.x_tail_m:.2f} m")
    out.geometry_summary = (f"{kind}: {where}, bitola {track_s}, h_cg {h:.2f} m; "
                            f"tombo {out.tipback_deg:.1f}°; capotagem {shown}")
    return out
