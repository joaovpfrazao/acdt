# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Manutibilidade e disponibilidade (MIL-HDBK-338B, 1 out. 1998).

* M_ct = Σ λ_i M_ct,i / Σ λ_i — tempo médio de reparação (Eq. 5.75);
* MTBM = 1 / (λ + f) — intervalo médio entre ações corretivas (taxa λ) e preventivas (frequência f) (§10.4.1.1, a
  seguir à Eq. 10.21); M̄ = (λ M_ct + Σ f_j M_pt,j) / (λ + f) — tempo médio de manutenção ativa ponderado pelas
  frequências (mesma ponderação da Eq. 5.75). Nota: o Exemplo 3 do §10.4.1.1 soma M_ct + M_pt (0,5 + 0,25 h) em vez
  de ponderar; o caso V&V reproduz o exemplo dando M̄ diretamente;
* A_i = MTBF / (MTBF + MTTR) (Eq. 10.18); A_a = MTBM / (MTBM + M̄) (Eq. 10.21);
  A_o = (MTBM + RT) / (MTBM + RT + MDT), MDT = M̄ + tempo logístico médio + tempo administrativo médio (Eq. 10.22;
  RT = tempo de prontidão, omissão 0);
* disponibilidade média num intervalo (unidade única exponencial) A_AV(T) = μ/(λ+μ) + λ/(T(λ+μ)²)(1 − e^{−(λ+μ)T})
  (Eq. 10.24);
* MMH/FH = Σ (frequência da ação por hora de voo × homens-hora por ação) — definição de DMMH/MA (Secção 3) somada
  sobre as ações corretivas (λ_i) e preventivas (f_j).

Base temporal: horas de voo (λ por FH). Intervalos: limites exteriores (MTBF e MTTR tratados como independentes),
logo conservadores.
"""
from __future__ import annotations

import math
from typing import Sequence


def weighted_mean_bounds(values: Sequence[float], wlo: Sequence[float], whi: Sequence[float]) -> tuple[float, float]:
    """Limites exatos de Σ w_i v_i / Σ w_i com w_i ∈ [wlo_i, whi_i] (extremos em vértices ordenados por v)."""
    if not values:
        raise ValueError("lista vazia")
    idx = sorted(range(len(values)), key=lambda i: values[i])

    def val(hi_set: set[int]) -> float:
        num = den = 0.0
        for i in range(len(values)):
            w = whi[i] if i in hi_set else wlo[i]
            num += w * values[i]
            den += w
        return num / den if den > 0 else math.nan

    cands_max = [val(set(idx[k:])) for k in range(len(idx) + 1)]
    cands_min = [val(set(idx[:k])) for k in range(len(idx) + 1)]
    mx = max(c for c in cands_max if not math.isnan(c))
    mn = min(c for c in cands_min if not math.isnan(c))
    return mn, mx


def inherent_availability(mtbf: float, mttr: float) -> float:
    """A_i = MTBF / (MTBF + MTTR) (MIL-HDBK-338B Eq. 10.18; :func:`acdt.core.concept.ops.availability`)."""
    from acdt.core.concept.ops import availability
    return float(availability(mtbf_h=mtbf, mttr_h=mttr)["inherent"])


def achieved_availability(mtbm: float, m_bar: float) -> float:
    """A_a = MTBM / (MTBM + M̄) (Eq. 10.21)."""
    return float(mtbm) / (float(mtbm) + float(m_bar))


def operational_availability(mtbm: float, mdt: float, ready_time: float = 0.0) -> float:
    """A_o = (MTBM + RT) / (MTBM + RT + MDT) (Eq. 10.22)."""
    return (float(mtbm) + float(ready_time)) / (float(mtbm) + float(ready_time) + float(mdt))


def interval_availability(lam: float, mu: float, T: float) -> float:
    """A_AV(T) de uma unidade exponencial com reparação (Eq. 10.24)."""
    s = float(lam) + float(mu)
    return float(mu) / s + float(lam) / (float(T) * s * s) * (1.0 - math.exp(-s * float(T)))


def mtbm(lam: float, f: float) -> float:
    """MTBM = 1/(λ + f) (§10.4.1.1)."""
    return 1.0 / (float(lam) + float(f))
