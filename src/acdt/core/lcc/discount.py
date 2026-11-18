# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Fatores de atualização para LCC — NIST Handbook 135 (Fuller & Petersen, 1995 ed., fev. 1996), Tabela 3-1.

* SPV(t, d) = 1/(1+d)^t (montante único no fim do ano t; Eq. 3.6);
* UPV(n, d) = Σ_{t=1..n} 1/(1+d)^t = [(1+d)^n − 1]/[d (1+d)^n] (série anual uniforme; Eq. 3.8);
* UPV*(n, d, e) = Σ_{t=1..n} ((1+e)/(1+d))^t = (1+e)/(d−e) [1 − ((1+e)/(1+d))^n] (série com escalada constante e,
  A_t = A_0 (1+e)^t; Eq. 3.9);
* taxa real d = (1+D)/(1+I) − 1 (Eq. 3.11); nominal D = (1+I)(1+d) − 1 (Eq. 3.13).
"""
from __future__ import annotations


def spv(t: float, d: float) -> float:
    return float((1.0 + d) ** (-t))


def upv(n: int, d: float) -> float:
    if d == 0.0:
        return float(n)
    return float(((1.0 + d) ** n - 1.0) / (d * (1.0 + d) ** n))


def upv_star(n: int, d: float, e: float) -> float:
    if abs(d - e) < 1e-15:
        return float(n)  # (1+e)/(1+d) = 1: n parcelas iguais a 1
    r = (1.0 + e) / (1.0 + d)
    return float((1.0 + e) / (d - e) * (1.0 - r ** n))


def real_rate(nominal: float, inflation: float) -> float:
    return float((1.0 + nominal) / (1.0 + inflation) - 1.0)


def nominal_rate(real: float, inflation: float) -> float:
    return float((1.0 + inflation) * (1.0 + real) - 1.0)
