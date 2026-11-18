# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Momentum (actuator-disk) theory for hovering and axially climbing rotors (VTOL / eVTOL L0).

* Ideal hover power P_ideal = T^(3/2) / sqrt(2 rho A), induced velocity v_h = sqrt(T / (2 rho A))
  (Johnson, *Helicopter Theory*, Princeton 1980, Ch. 2; Leishman, *Principles of Helicopter
  Aerodynamics*, 2nd ed., Cambridge 2006, Ch. 2).
* Figure of merit FM = P_ideal / P_actual (Leishman 2006 Sec. 2.8; Johnson 1980 Sec. 2.4). PRESSUPOSTO:
  0.70 by default for small eVTOL / UAV rotors; Leishman 2006 quotes 0.7–0.8 for well-designed full-scale
  rotors, small low-Reynolds rotors are lower (≈0.5–0.7).
* Disk loading DL = T / A; power loading PL = T / P.
* Axial climb (momentum): P = T (V_c/2 + sqrt((V_c/2)^2 + v_h^2)) (Leishman 2006 Sec. 2.6; Johnson 1980 Sec. 2.3).
* Forward flight induced velocity, Glauert's level-disk approximation v_i = v_h^2 / sqrt(V^2 + v_i^2)
  (Glauert 1926; Leishman 2006 Sec. 2.14), used only for the L0 transition envelope.
* Tip Mach and blade loading C_T / sigma = T / (rho A sigma (Omega R)^2) (Leishman 2006 Sec. 2.4 / Ch. 6:
  C_T/sigma ≈ 0.12–0.14 is the practical stall limit). PRESSUPOSTO: tip-Mach limit 0.6 (noise), solidity 0.10.

Limits: uniform inflow, no swirl/tip losses beyond FM, no rotor–rotor interference. Opt-in axial BEMT is in bemt.py; yawed flight and NDARC-level interference remain deferred.
"""
from __future__ import annotations

import math

G0 = 9.80665


def induced_velocity_hover(T: float, rho: float, A: float) -> float:
    """v_h = sqrt(T / (2 rho A)) [m/s] (Johnson 1980 Ch. 2)."""
    return math.sqrt(T / (2.0 * rho * A))


def ideal_hover_power(T: float, rho: float, A: float) -> float:
    """P_ideal = T^(3/2) / sqrt(2 rho A) [W] (Johnson 1980 Ch. 2; Leishman 2006 Eq. 2.16)."""
    if T <= 0 or rho <= 0 or A <= 0:
        raise ValueError("T, rho and A must be positive")
    return T ** 1.5 / math.sqrt(2.0 * rho * A)


def hover_power(T: float, rho: float, A: float, FM: float = 0.70) -> float:
    """Shaft hover power P = P_ideal / FM [W]."""
    if not 0 < FM <= 1:
        raise ValueError("figure of merit must be in (0, 1]")
    return ideal_hover_power(T, rho, A) / FM


def climb_power(T: float, rho: float, A: float, Vc: float, FM: float = 0.70) -> float:
    """Axial climb shaft power (momentum) P = T (Vc/2 + sqrt((Vc/2)^2 + v_h^2)) / FM [W].

    Dividing by FM applies the hover profile/non-ideal factor to the climb case (L0 PRESSUPOSTO)."""
    vh = induced_velocity_hover(T, rho, A)
    return T * (0.5 * Vc + math.sqrt((0.5 * Vc) ** 2 + vh ** 2)) / FM


def induced_velocity_forward(T: float, rho: float, A: float, V: float) -> float:
    """Glauert level-disk induced velocity v_i solving v_i^4 + V^2 v_i^2 - v_h^4 = 0 [m/s]."""
    vh = induced_velocity_hover(T, rho, A)
    return math.sqrt(-0.5 * V ** 2 + math.sqrt(0.25 * V ** 4 + vh ** 4))


def disk_area_from_loading(T: float, DL: float) -> float:
    return T / DL


def tip_speed_limit(a_sound: float, mach_tip: float = 0.6) -> float:
    return a_sound * mach_tip


def blade_loading(T: float, rho: float, A: float, tip_speed: float, solidity: float = 0.10) -> float:
    """C_T / sigma with C_T = T / (rho A (Omega R)^2) (Leishman 2006 Sec. 2.4)."""
    return T / (rho * A * tip_speed ** 2) / solidity
