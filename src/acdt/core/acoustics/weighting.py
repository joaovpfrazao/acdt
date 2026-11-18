# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Ponderação de frequência A — IEC 61672-1:2013, Anexo E (normativo), Eq. (E.6).

A(f) = 20·log10[ f4²·f⁴ / ((f² + f1²)·√(f² + f2²)·√(f² + f3²)·(f² + f4²)) ] − A1000

com f1 = 20,598997 Hz, f2 = 107,65265 Hz, f3 = 737,86223 Hz, f4 = 12194,217 Hz (E.4.1, valores exatos derivados
de f_r = 1 kHz, f_L = 10^1,5 Hz, f_H = 10^3,9 Hz, f_A = 10^2,45 Hz) e A1000 = −2,000 dB (E.4.2, normalização a
0 dB em 1 kHz). Os valores nominais da Tabela 3 (p. ex. −19,1 dB a 100 Hz, +1,2 dB a 2 kHz) são esta expressão
avaliada nas frequências exatas de base 10 e arredondada a 0,1 dB (verificado no caso V&V NOISE-AWEIGHT).
"""
from __future__ import annotations

import math

F1, F2, F3, F4 = 20.598997, 107.65265, 737.86223, 12194.217
A1000 = -2.000


def a_weighting(f: float) -> float:
    """A(f) [dB]; f ≤ 0 → −inf."""
    if f <= 0.0:
        return -math.inf
    f2 = f * f
    num = F4 ** 2 * f2 * f2
    den = (f2 + F1 ** 2) * math.sqrt(f2 + F2 ** 2) * math.sqrt(f2 + F3 ** 2) * (f2 + F4 ** 2)
    return 20.0 * math.log10(num / den) - A1000
