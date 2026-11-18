# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Propriedades do ar seco e atmosferas de projeto (normal, quente e fria).

* Viscosidade dinâmica: lei de Sutherland com as constantes da U.S. Standard Atmosphere 1976 (NOAA-S/T 76-1562),
  Eq. (51): μ = β·T^1,5/(T + S), β = 1,458×10⁻⁶ kg/(m·s·K^½), S = 110,4 K.
* Condutividade térmica: U.S. Standard Atmosphere 1976, Eq. (53): k = 2,64638×10⁻³·T^1,5/(T + 245,4·10^(−12/T)).
* c_p de gás caloricamente perfeito: c_p = γR/(γ−1), γ = 1,4, R = 287,05287 J/(kg·K) (ISO 2533 / ICAO Doc 7488).
  PRESSUPOSTO: c_p constante (a Tabela A.4 de Incropera et al. dá 1006–1009 J/(kg·K) entre 250 e 350 K; −0,2 a
  −0,4 %).
* Atmosferas:
  - ``isa`` — ISO 2533 (:mod:`acdt.core.atmosphere`);
  - ``mil310_hot_1pct`` / ``mil310_cold_1pct`` — MIL-HDBK-310 (23 jun 1997), §5.3.1.1.2 e §5.3.1.2.2: temperaturas
    de 1 % de frequência no mês mais extremo, com a massa volúmica associada, por altitude geométrica 0–30 km;
    pressão p = ρ·R·T;
  - ``mil310_cold_20pct`` — Tabela XX (20 %, 0–10 km; o §4.3.3 recomenda 20 % para o frio). A tabela não dá massa
    volúmica: PRESSUPOSTO pressão ISA à mesma altitude, ρ = p/(R·T);
  - ``custom`` — temperatura ao nível do solo e gradiente dados pelo utilizador, pressão ISA.
  Radiação solar de projeto do dia quente: Tabela I da MIL-HDBK-310 (ciclo diário do 1 % quente), máximo
  1120 W/m² às 12–13 h (hora solar local) ao nível do solo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from acdt.core.atmosphere import GAMMA, R_AIR, isa

AIR_REF = ("U.S. Standard Atmosphere 1976 (NOAA-S/T 76-1562), Eqs. (51) e (53); c_p = γR/(γ−1) com ISO 2533")
MIL310 = ("MIL-HDBK-310, Global Climatic Data for Developing Military Products (DoD, 23 jun 1997), §5.3.1.1.2 "
          "(1 % quente), §5.3.1.2.2 (1 % frio), Tabela XX (20 % frio), Tabela I (ciclo diário do 1 % quente)")
CP_AIR = GAMMA * R_AIR / (GAMMA - 1.0)
SIGMA_SB = 5.670374419e-8  # W/(m²·K⁴), CODATA 2018 (valor exato derivado das constantes do SI de 2019)
SOLAR_HOT_DAY_W_M2 = 1120.0  # MIL-HDBK-310 Tabela I, 12–13 h

# MIL-HDBK-310 §5.3.1.1.2: (altitude geométrica km, T °C, ρ kg/m³) — 1 % quente
_HOT_1 = [(0, 49, 1.081), (1, 40, 1.007), (2, 30, 0.919), (4, 17, 0.757), (6, 6, 0.613), (8, -5, 0.497),
          (10, -13, 0.397), (12, -22, 0.317), (14, -30, 0.210), (16, -37, 0.159), (18, -37, 0.119),
          (20, -32, 0.087), (22, -30, 0.067), (24, -33, 0.049), (26, -28, 0.036), (28, -23, 0.027),
          (30, -18, 0.020)]
# §5.3.1.2.2: 1 % frio
_COLD_1 = [(0, -61, 1.610), (1, -53, 1.408), (2, -41, 1.132), (4, -48, 0.868), (6, -57, 0.675), (8, -66, 0.523),
           (10, -74, 0.415), (12, -73, 0.297), (14, -75, 0.214), (16, -86, 0.206), (18, -86, 0.143),
           (20, -86, 0.078), (22, -84, 0.054), (24, -85, 0.038), (26, -84, 0.029), (28, -83, 0.020),
           (30, -83, 0.016)]
# Tabela XX, coluna 20 % (altitude geométrica), 0–10 km
_COLD_20 = [(0, -51), (1, -49), (2, -31), (4, -40), (6, -51), (8, -61), (10, -65)]

PROFILES = ("isa", "mil310_hot_1pct", "mil310_cold_1pct", "mil310_cold_20pct", "custom")


@dataclass(frozen=True)
class Ambient:
    """Estado do ar ambiente para a análise térmica."""

    profile: str
    altitude_m: float
    T_K: float
    p_Pa: float
    rho: float
    source: str

    @property
    def T_C(self) -> float:
        return self.T_K - 273.15


@dataclass(frozen=True)
class AirProps:
    T_K: float
    rho: float
    mu: float
    k: float
    cp: float

    @property
    def nu(self) -> float:
        return self.mu / self.rho

    @property
    def Pr(self) -> float:
        return self.mu * self.cp / self.k

    @property
    def alpha(self) -> float:
        return self.k / (self.rho * self.cp)


def mu_air(T: float) -> float:
    """Viscosidade dinâmica [Pa·s], USSA 1976 Eq. (51)."""
    return float(1.458e-6 * T ** 1.5 / (T + 110.4))


def k_air(T: float) -> float:
    """Condutividade térmica [W/(m·K)], USSA 1976 Eq. (53)."""
    return float(2.64638e-3 * T ** 1.5 / (T + 245.4 * 10.0 ** (-12.0 / T)))


def air_props(T_K: float, p_Pa: float) -> AirProps:
    """Propriedades do ar seco a (T, p): gás perfeito, μ e k da USSA 1976, c_p constante."""
    if not (T_K > 0 and p_Pa > 0):
        raise ValueError("T e p têm de ser positivos")
    return AirProps(T_K, p_Pa / (R_AIR * T_K), mu_air(T_K), k_air(T_K), CP_AIR)


def _interp_table(rows: Sequence[tuple[float, float, float]], h_m: float) -> tuple[float, float]:
    z = np.array([r[0] for r in rows], float) * 1000.0
    if h_m < z[0] - 1e-9 or h_m > z[-1] + 1e-9:
        raise ValueError(f"altitude {h_m:.0f} m fora da tabela MIL-HDBK-310 ({z[0]:.0f}–{z[-1]:.0f} m)")
    T = float(np.interp(h_m, z, [r[1] + 273.15 for r in rows]))
    rho = float(math.exp(np.interp(h_m, z, [math.log(r[2]) for r in rows])))
    return T, rho


def ambient(profile: str, altitude_m: float, *, T_sl_C: float | None = None, lapse_K_m: float = -0.0065) -> Ambient:
    """Ar ambiente à altitude geométrica ``altitude_m`` (interpolação linear de T e de ln ρ entre linhas da tabela;
    PRESSUPOSTO). ``custom``: T = T_sl + gradiente·h, pressão ISA."""
    h = max(float(altitude_m), 0.0)
    if profile == "isa":
        s = isa(h)
        return Ambient(profile, h, s.T, s.p, s.rho, "ISO 2533 (ISA)")
    if profile == "mil310_hot_1pct":
        T, rho = _interp_table(_HOT_1, h)
        return Ambient(profile, h, T, rho * R_AIR * T, rho, MIL310 + " — 1 % quente")
    if profile == "mil310_cold_1pct":
        T, rho = _interp_table(_COLD_1, h)
        return Ambient(profile, h, T, rho * R_AIR * T, rho, MIL310 + " — 1 % frio")
    if profile == "mil310_cold_20pct":
        z = [r[0] * 1000.0 for r in _COLD_20]
        if h > z[-1] + 1e-9:
            raise ValueError("MIL-HDBK-310 Tabela XX (20 % frio) transcrita só até 10 km")
        T = float(np.interp(h, z, [r[1] + 273.15 for r in _COLD_20]))
        p = isa(h).p
        return Ambient(profile, h, T, p, p / (R_AIR * T), MIL310 + " — 20 % frio (PRESSUPOSTO: pressão ISA)")
    if profile == "custom":
        if T_sl_C is None:
            raise ValueError("atmosfera custom precisa de T_sl_C")
        T = float(T_sl_C) + 273.15 + lapse_K_m * h
        p = isa(h).p
        return Ambient(profile, h, T, p, p / (R_AIR * T), f"utilizador: T_sl = {T_sl_C} °C, gradiente {lapse_K_m} K/m, "
                       "pressão ISA (PRESSUPOSTO)")
    raise ValueError(f"perfil de atmosfera desconhecido '{profile}' (use {', '.join(PROFILES)})")


def ram_temperature(T_K: float, V: float) -> float:
    """Temperatura total (de estagnação) T0 = T + V²/(2 c_p) (escoamento adiabático, gás caloricamente perfeito)."""
    return T_K + V * V / (2.0 * CP_AIR)
