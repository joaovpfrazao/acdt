# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Provisão de sobressalentes por Poisson (MIL-HDBK-338B Eq. 5.55–5.58, §5.3.8.1).

Com procura de taxa constante, o número de avarias num período tem distribuição de Poisson de média a = λ t; a
probabilidade de não faltar sobressalente com S unidades em stock é P(X ≤ S) = Σ_{x=0..S} aˣ e^{−a}/x! (Eq. 5.58;
exemplo do projetor: λ = 0,001/h, t = 500 h, S = 2 → 0,986). O stock para um nível de proteção c é o menor S com
P(X ≤ S) ≥ c. Aqui t é o tempo de reabastecimento/reparação do circuito (pipeline) e a procura é a de toda a frota.
PRESSUPOSTO: procura estacionária (sem crescimento de fiabilidade nem envelhecimento), stock reposto ao fim de t.
"""
from __future__ import annotations

import math


def poisson_cdf(s: int, a: float) -> float:
    """P(X ≤ s) para X ~ Poisson(a) (Eq. 5.58)."""
    if a < 0:
        raise ValueError("média de Poisson negativa")
    if a == 0:
        return 1.0
    if a > 500.0:  # e^{−a} sai da gama do float: mesma soma por scipy (função gama incompleta regularizada)
        from scipy.stats import poisson
        return float(poisson.cdf(int(s), a))
    term = math.exp(-a)
    tot = term
    for x in range(1, int(s) + 1):
        term *= a / x
        tot += term
    return min(1.0, tot)


def stock_for(a: float, confidence: float, s_max: int = 100000) -> int:
    """Menor S com P(X ≤ S) ≥ ``confidence``."""
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence em (0, 1)")
    s = 0
    while poisson_cdf(s, a) < confidence:
        s += 1
        if s > s_max:
            raise ValueError("stock acima do limite de pesquisa")
    return s
