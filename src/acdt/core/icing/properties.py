# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Propriedades do ar, da água e do gelo para cálculos de formação de gelo (docs/GELO.md).

Todas as expressões e constantes são as do Apêndice A de Anderson, D. N., *Manual of Scaling Methods*,
NASA/CR-2004-212875 (2004), na forma SI do manual (cal, g, cm convertidos aqui para SI). Validade declarada pela
fonte: −40 °F a 40 °F (≈ −40 °C a 4 °C) para c_p,a, k_a e μ_a; −50 °C a 0 °C para as pressões de vapor.
"""
from __future__ import annotations

import math

#: caloria internacional [J] — Anderson usa Btu/(lbm·R) = cal/(g·K), a igualdade só é exata com cal_IT
CAL_IT = 4.1868
SOURCE = "Anderson, NASA/CR-2004-212875 (2004), Apêndice A"

CP_AIR = 0.240 * CAL_IT * 1e3          # J/(kg·K), Eq. (A.1)
R_AIR = 287.0                          # J/(kg·K), Eq. (A.11) (0,287 N·m/(g·K))
GAMMA_AIR = 1.40                       # Eq. (A.18)
RHO_ICE = 917.0                        # kg/m³, Eq. (A.27) (incerteza «talvez até 10 %»)
RHO_WATER = 1000.0                     # kg/m³, Eq. (A.28)
MU_WATER = 0.01786 * 0.1               # Pa·s, Eq. (A.25) (no ponto de congelação)
T0 = 273.15                            # K
LAMBDA_F_GLAZE = 79.7 * CAL_IT * 1e3   # J/kg, Eq. (A.20) (superfície a 0 °C)
LAMBDA_V_GLAZE = 597.3 * CAL_IT * 1e3  # J/kg, Eq. (A.23) (superfície a 0 °C)

_A = (610.78, 44.365, 1.4289, 2.6506e-2, 3.0312e-4, 2.0341e-6, 6.1368e-9)   # Pa/K^n, Eq. (A.8)
_B = (610.92, 50.347, 1.8860, 4.1762e-2, 5.8247e-4, 4.8388e-6, 1.8388e-8)   # Pa/K^n, Eq. (A.10)


def _poly(c: tuple[float, ...], dT: float) -> float:
    # forma encaixada da fonte: a0 + ΔT(a1 + ΔT(a2 + ΔT(a3 + ΔT(a4 + ΔT(a5 + ΔT a6)))))
    acc = c[6]
    for k in range(5, -1, -1):
        acc = c[k] + dT * acc
    return acc


def p_sat_water(T: float) -> float:
    """Pressão de saturação do vapor sobre água líquida [Pa], Pruppacher & Klett via Eq. (A.8)–(A.9).
    Válida de −50 °C a 0 °C (fora disso levanta ``ValueError``: não se extrapola)."""
    dT = T - T0
    if not -50.0 - 1e-9 <= dT <= 1e-9:
        raise ValueError(f"p_sat_water: T = {T:.2f} K fora da validade da Eq. (A.8) (−50 °C a 0 °C)")
    return _poly(_A, dT)


def p_sat_ice(T: float) -> float:
    """Pressão de saturação do vapor sobre gelo [Pa], Eq. (A.10). Válida de −50 °C a 0 °C."""
    dT = T - T0
    if not -50.0 - 1e-9 <= dT <= 1e-9:
        raise ValueError(f"p_sat_ice: T = {T:.2f} K fora da validade da Eq. (A.10) (−50 °C a 0 °C)")
    return _poly(_B, dT)


def cp_water_surface(Ts: float) -> float:
    """Calor específico da água na superfície [J/(kg·K)], Eq. (A.2): 1,0074 + 8,29×10⁻⁵ (T_s − 273,15)² cal/(g·K)."""
    return (1.0074 + 8.29e-5 * (Ts - T0) ** 2) * CAL_IT * 1e3


def k_air(T_film: float) -> float:
    """Condutividade do ar [W/(m·K)], Eq. (A.3): −12,69 + 2,029 √T cal/(h·m·K) (T em K, temperatura de filme)."""
    return (-12.69 + 2.029 * math.sqrt(T_film)) * CAL_IT / 3600.0


def mu_air(T: float) -> float:
    """Viscosidade do ar [Pa·s], Eq. (A.24): 10⁻⁴/(0,12764 + 124,38/T) g/(cm·s)."""
    return 1e-4 / (0.12764 + 124.38 / T) * 0.1


def diffusivity_vapour(T_film: float, p_st: float) -> float:
    """Difusividade do vapor de água no ar [m²/s], Eq. (A.4): 0,211 (T/273,15)^1,94 (1,0132×10⁵/p) cm²/s."""
    return float(0.211e-4 * (T_film / T0) ** 1.94 * (1.0132e5 / p_st))


def lambda_fusion(Ts: float) -> float:
    """Calor latente de fusão [J/kg], Eq. (A.19): 79,7 + 0,485 ΔT − 2,5×10⁻³ ΔT² cal/g (ΔT = T_s − 273,15)."""
    dT = Ts - T0
    return (79.7 + 0.485 * dT - 2.5e-3 * dT ** 2) * CAL_IT * 1e3


def lambda_vaporisation(Ts: float) -> float:
    """Calor latente de vaporização [J/kg], Eq. (A.21)–(A.22): 597,3 (273,15/T)^E cal/g, E = 0,167 + 3,67×10⁻⁴ T."""
    E = 0.167 + 3.670e-4 * Ts
    return float(597.3 * (T0 / Ts) ** E * CAL_IT * 1e3)


def total_temperature(T_st: float, V: float) -> float:
    """Temperatura total (de estagnação) [K], Eq. (A.16): T_tot = T_st + V²/(2 c_p,a)."""
    return T_st + V * V / (2.0 * CP_AIR)


def static_pressure(p_tot: float, T_st: float, V: float) -> float:
    """Pressão estática a partir da total, forma incompressível Eq. (A.6): p_st = p_tot/(1 + V²/(2 R T_st))."""
    return p_tot / (1.0 + V * V / (2.0 * R_AIR * T_st))


def total_pressure_from_static(p_st: float, T_st: float, V: float) -> float:
    """Inverso da Eq. (A.6) (túnel com a secção de ensaio à pressão ambiente, Anderson §A.1)."""
    return p_st * (1.0 + V * V / (2.0 * R_AIR * T_st))


def static_pressure_compressible(p_tot: float, T_st: float, V: float) -> float:
    """Eq. (A.7): p_st = p_tot/(1 + (γ−1)/2 M²)^(γ/(γ−1)), M = V/√(γ R T_st) (Eq. A.38)."""
    M2 = V * V / (GAMMA_AIR * R_AIR * T_st)
    return float(p_tot / (1.0 + 0.5 * (GAMMA_AIR - 1.0) * M2) ** (GAMMA_AIR / (GAMMA_AIR - 1.0)))
