# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Absorção atmosférica de tons puros — ISO 9613-1:1993.

Coeficiente de atenuação α [dB/m] (Eq. 5):

α = 8,686 f² { 1,84×10⁻¹¹ (p_a/p_r)⁻¹ (T/T0)^½ + (T/T0)^(−5/2) [ 0,01275 e^(−2239,1/T) / (f_rO + f²/f_rO)
    + 0,1068 e^(−3352,0/T) / (f_rN + f²/f_rN) ] }

frequências de relaxação do oxigénio e do azoto (Eq. 3 e 4):

f_rO = (p_a/p_r) [ 24 + 4,04×10⁴ h (0,02 + h)/(0,391 + h) ]
f_rN = (p_a/p_r) (T/T0)^(−½) { 9 + 280 h exp[ −4,170 ((T/T0)^(−⅓) − 1) ] }

concentração molar de vapor de água h [%] a partir da humidade relativa h_r [%] (Anexo B, B.1–B.3):
h = h_r (p_sat/p_r)/(p_a/p_r), p_sat/p_r = 10^C, C = −6,8346 (T01/T)^1,261 + 4,6151.

T0 = 293,15 K, T01 = 273,16 K, p_r = 101,325 kPa. Gama de validade declarada pela norma: 50 Hz – 10 kHz,
−20 °C a +50 °C, 10 % – 100 % de humidade relativa, pressão até 200 kPa (fora da gama: :func:`in_validity`).
O SAE ARP 866A citado pela Parte 36 é o procedimento antigo equivalente; usa-se aqui a ISO 9613-1.
"""
from __future__ import annotations

import math

T0 = 293.15
T01 = 273.16
P_R = 101.325  # kPa


def molar_h2o(T_K: float, rh_pct: float, p_kpa: float = P_R) -> float:
    """h [%] — ISO 9613-1 Anexo B."""
    C = -6.8346 * (T01 / T_K) ** 1.261 + 4.6151
    return float(rh_pct * (10.0 ** C) / (p_kpa / P_R))


def alpha_iso9613(f: float, T_C: float = 20.0, rh_pct: float = 70.0, p_kpa: float = P_R) -> float:
    """α [dB/m] de um tom puro de frequência f [Hz]."""
    if f <= 0.0:
        return 0.0
    T = T_C + 273.15
    pr = p_kpa / P_R
    h = molar_h2o(T, rh_pct, p_kpa)
    tr = T / T0
    frO = pr * (24.0 + 4.04e4 * h * (0.02 + h) / (0.391 + h))
    frN = pr * tr ** -0.5 * (9.0 + 280.0 * h * math.exp(-4.170 * (tr ** (-1.0 / 3.0) - 1.0)))
    f2 = f * f
    return float(8.686 * f2 * (1.84e-11 / pr * tr ** 0.5
                         + tr ** -2.5 * (0.01275 * math.exp(-2239.1 / T) / (frO + f2 / frO)
                                         + 0.1068 * math.exp(-3352.0 / T) / (frN + f2 / frN))))


def in_validity(f: float, T_C: float, rh_pct: float, p_kpa: float = P_R) -> bool:
    return 50.0 <= f <= 10_000.0 and -20.0 <= T_C <= 50.0 and 10.0 <= rh_pct <= 100.0 and 0.0 < p_kpa <= 200.0
