"""Electric propulsion first-cut: propeller diameter & rpm, motor Kv and power, ESC.

Methods
-------
* Propeller diameter statistics: Raymer 6th ed. Sec. 10.3, D = K_p P^(1/4)
  (K_p = 0.56 two-blade, 0.52 three-blade, metric m & kW), capped by a
  user geometric limit (ground/fuselage clearance, launcher).
* Tip-Mach limit on rpm: helical tip Mach (Raymer Sec. 10.3),
  M_tip = sqrt((π n D)² + V²)/a <= M_limit.
* Propeller power coefficient C_P = P/(ρ n³ D⁵) (McCormick,
  *Aerodynamics, Aeronautics and Flight Mechanics*, Ch. 6). Static C_P is a
  user input from propeller data (e.g. UIUC Propeller Data Site, APC files).
* Advance ratio J = V/(n D) at cruise (McCormick Ch. 6).
* DC motor first-order model (Drela, "First-Order DC Electric Motor Model",
  MIT 2007): rpm = Kv (V − I R); here the loaded voltage ratio V_loaded/V_nom
  is a user assumption (default 0.85) replacing I·R until motor R is known.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

KP_METRIC = {2: 0.56, 3: 0.52, 4: 0.49}


@dataclass
class PropellerSizing:
    D: float
    rpm_max: float
    rpm_cruise: float
    J_cruise: float
    tip_mach_max: float
    note: str
    method: str = "raymer"
    status: str = "ok"
    eta_cruise: float | None = None
    CT_cruise: float | None = None
    CP_cruise: float | None = None
    unassessed_terms: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    polar_source: str = ""
    pitch_m: float | None = None
    c075_D: float | None = None
    rpm_static: float | None = None
    P_shaft_cruise_W: float | None = None
    T_cruise_N: float | None = None



def size_propeller(P_max: float, V_cruise: float, rho: float, a: float, n_blades: int = 2,
                   D_max: float | None = None, cp_static: float = 0.05, J_cruise: float = 0.7,
                   tip_mach_limit: float = 0.7) -> PropellerSizing:
    D = KP_METRIC[n_blades] * (P_max / 1e3) ** 0.25
    note = "Raymer Sec. 10.3 statistics"
    if D_max and D > D_max:
        D, note = D_max, f"limited by geometric D_max ({D_max:.3f} m)"
    n = (P_max / (rho * cp_static * D**5)) ** (1 / 3)  # rev/s at static max power
    tip = math.pi * n * D / a
    if tip > tip_mach_limit:
        n = tip_mach_limit * a / (math.pi * D)
        tip = tip_mach_limit
        note += "; rpm limited by tip Mach"
    n_cr = V_cruise / (J_cruise * D)
    return PropellerSizing(D, n * 60, n_cr * 60, J_cruise, tip, note)


@dataclass
class MotorChoice:
    motor: dict | None
    esc: dict | None
    kv_target: float
    p_shaft_max: float
    i_max: float
    v_nom: float
    messages: list[str]
    feasible: bool = True       # False when the returned motor misses P / Kv / V / I
    esc_feasible: bool = True   # False when the returned ESC misses I / V
    deck: dict | None = None    # opt-in Drela first-order (or unassessed report)


def _motor_meets(m, P_shaft_max, kv, v_max, i_max, power_margin, kv_tolerance) -> bool:
    return (m["p_max"] >= power_margin * P_shaft_max and m["v_max"] >= v_max
            and abs(m["kv"] / kv - 1) <= kv_tolerance and m.get("i_max", 1e9) >= i_max)


def _esc_meets(e, i_max, v_max, esc_margin) -> bool:
    return e["i_cont"] >= esc_margin * i_max and e["v_max"] >= v_max


def select_motor_esc(db, P_shaft_max: float, rpm_max: float, v_nom: float, v_max: float,
                     power_margin: float = 1.2, kv_tolerance: float = 0.25, load_ratio: float = 0.85,
                     eta_motor: float = 0.85, esc_margin: float = 1.2, *,
                     motor_id: str | None = None, esc_id: str | None = None) -> MotorChoice:
    """Select the lightest motor/ESC pair in the component DB.

    Kv from the DC-motor relation rpm = Kv·V·(loaded/no-load ratio) (first-order DC machine model,
    e.g. Hepperle 2012, "Electric Flight – Potential and Limitations", Sec. 3). ``load_ratio``,
    ``power_margin``, ``kv_tolerance``, ``eta_motor`` and ``esc_margin`` are **user design
    assumptions** (defaults are placeholders, not handbook values) — set them from datasheets.

    ``motor_id`` / ``esc_id`` fix the integer assignment (the continuous optimiser must not switch
    component). The pinned part is returned even when it misses the rating, so the mass does not fall
    back to the rubber-engine estimate; ``feasible`` / ``esc_feasible`` is then false.
    """
    kv = rpm_max / (v_nom * load_ratio)
    i_max = P_shaft_max / (eta_motor * v_nom * load_ratio)
    msgs = []
    motor_feasible = True
    if motor_id:
        motor = next((m for m in db.motors if m["id"] == motor_id), None)
        if motor is None:
            motor_feasible = False
            msgs.append(f"Pinned motor {motor_id} is not in the database")
        elif not _motor_meets(motor, P_shaft_max, kv, v_max, i_max, power_margin, kv_tolerance):
            motor_feasible = False
            msgs.append(f"Pinned motor {motor_id} does not meet P>={power_margin * P_shaft_max:.0f} W, "
                        f"Kv≈{kv:.0f}±{kv_tolerance:.0%}, V>={v_max:.1f} V")
    else:
        cands = [m for m in db.motors if _motor_meets(m, P_shaft_max, kv, v_max, i_max, power_margin, kv_tolerance)]
        motor = min(cands, key=lambda m: m["mass"]) if cands else None
        if motor is None:
            motor_feasible = False
            msgs.append(f"No motor in DB with P>={power_margin * P_shaft_max:.0f} W, Kv≈{kv:.0f}±{kv_tolerance:.0%}, "
                        f"V>={v_max:.1f} V — add a datasheet entry or change bus voltage/prop")
    esc_feasible = True
    if esc_id:
        esc = next((e for e in db.escs if e["id"] == esc_id), None)
        if esc is None:
            esc_feasible = False
            msgs.append(f"Pinned ESC {esc_id} is not in the database")
        elif not _esc_meets(esc, i_max, v_max, esc_margin):
            esc_feasible = False
            msgs.append(f"Pinned ESC {esc_id} does not meet I>={esc_margin * i_max:.0f} A and V>={v_max:.1f} V")
    else:
        esc_c = [e for e in db.escs if _esc_meets(e, i_max, v_max, esc_margin)]
        esc = min(esc_c, key=lambda e: e["mass"]) if esc_c else None
        if esc is None:
            esc_feasible = False
            msgs.append(f"No ESC with I>={esc_margin * i_max:.0f} A and V>={v_max:.1f} V")
    return MotorChoice(motor, esc, kv, P_shaft_max, i_max, v_nom, msgs, motor_feasible, esc_feasible)
