"""Load formulas shared by the L1 beam. Numeric only: no aircraft objects.

* Balancing tail load from longitudinal statics (Etkin & Reid; the balancing part of
  14 CFR 23.423). Positive is upward. x increases aft.
* Checked-manoeuvre angular acceleration, 14 CFR 23.423(b) (as on the eCFR of 25 July 2017):
  nose-up at n = 1, α = +39 n_m / (V (n_m − 1.5)); nose-down at n = n_m, α = −39 n_m / (V (n_m − 1.5));
  V in knots, α in rad/s². The tail-force increment that produces α about the CG is I_yy α / l.
* Surface limit lift q S C_Lmax with Raymer Eq. 12.15, C_Lmax = 0.9 c_lmax cos Λ_c/4.
  Used as an upper bound on the manoeuvre load when the control stop and the pilot effort of
  23.423(a) are not in the model.
"""
from __future__ import annotations

import math

KT = 0.514444  # knot → m/s


def surface_limit_lift(q: float, area: float, sweep_c4: float, clmax_section: float) -> float:
    """Raymer Eq. 12.15 applied to one surface: L = q S (0.9 c_lmax cos Λ_c/4)."""
    cl = 0.9 * clmax_section * math.cos(sweep_c4)
    return q * area * cl


def equilibrium_tail_load(n: float, weight_N: float, x_cg: float, x_ac_wing: float, x_ac_tail: float) -> float:
    """Balancing horizontal-tail load [N], positive upward.

    L_w + L_t = n W and L_w (x_cg − x_ac,w) − L_t (x_ac,t − x_cg) = 0, so
    L_t = n W (x_cg − x_ac,w) / (x_ac,t − x_ac,w). A CG ahead of the wing a.c. gives a downward tail load.
    """
    arm = x_ac_tail - x_ac_wing
    if abs(arm) < 1e-9:
        return 0.0
    return n * weight_N * (x_cg - x_ac_wing) / arm


def checked_maneuver_alpha(n_m: float, V_mps: float, nose_up: bool = True) -> float:
    """14 CFR 23.423(b) angular acceleration [rad/s²]. ``V_mps`` is the true initial speed.

    The regulation writes V in knots. The formula is singular at n_m ≤ 1.5 (the table starts
    above that); the acceleration is then reported as 0.
    """
    if n_m <= 1.5 or V_mps <= 0:
        return 0.0
    V_kt = V_mps / KT
    mag = 39.0 * n_m / (V_kt * (n_m - 1.5))
    return mag if nose_up else -mag


def angular_tail_increment(Iyy: float, alpha: float, arm: float) -> float:
    """Tail-force increment [N] that produces ``alpha`` about the CG: ΔL = I_yy α / l.

    The sign follows ``alpha`` (nose-up α > 0 needs an upward increment on a tail aft of the CG
    only if the nose-up moment is a downward tail load — the caller adds it with its own sign
    convention). This function returns I α / l with the sign of α and a positive arm.
    """
    if abs(arm) < 1e-9:
        return 0.0
    return Iyy * alpha / arm
