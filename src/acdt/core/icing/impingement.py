# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Eficiência de captação na linha de estagnação (docs/GELO.md).

Langmuir & Blodgett (1946), «A Mathematical Investigation of Water Droplet Trajectories», AAF TR 5418, na forma
apresentada por Anderson, NASA/CR-2004-212875 (2004), §3.3:

* parâmetro de inércia K = ρ_w δ² V/(18 d μ_a) — Eq. (3.5)/(A.36); d = diâmetro do cilindro ou **2× o raio do bordo
  de ataque** do perfil (convenção do manual, §3.2);
* número de Reynolds da gota Re_δ = V δ ρ_a/μ_a — Eq. (3.10)/(A.45);
* parâmetro de alcance λ/λ_Stokes = 1/(0,8388 + 0,001483 Re_δ + 0,1847 √Re_δ) — Eq. (3.12)/(A.53), ajuste à tabela
  de Langmuir & Blodgett com ±0,2 % para 14 ≤ Re_δ ≤ 600 (0,4 % a 800);
* parâmetro de inércia modificado K₀ = 1/8 + (λ/λ_Stokes)(K − 1/8), K > 1/8 — Eq. (3.8)/(A.37); K ≤ 1/8 → sem
  impacto;
* β₀ = 1,40 (K₀ − 1/8)^0,84/(1 + 1,40 (K₀ − 1/8)^0,84) — Eq. (3.13)/(A.50), válida segundo Langmuir & Blodgett para
  K ≤ 7,5; contra o LEWICE (NACA 0012, K₀ 0,72–202) ficou entre 4,7 % abaixo (K₀ = 0,4) e 0,23 % acima (K₀ = 34).

Raio do bordo de ataque de perfis NACA de 4 dígitos: r_le = 1,1019 t² c (Abbott & von Doenhoff, *Theory of Wing
Sections*, 1959, §6.4); para o NACA 0012 dá 1,58 % da corda, o valor usado por Anderson (Apêndice B).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .properties import RHO_WATER

SOURCE = "Langmuir & Blodgett (1946) via Anderson, NASA/CR-2004-212875, Eq. (3.5), (3.8), (3.10), (3.12), (3.13)"


def naca4_le_radius(t_c: float, chord_m: float) -> float:
    """Raio do bordo de ataque [m] de um perfil NACA de 4 dígitos: 1,1019 t² c (Abbott & von Doenhoff 1959)."""
    return 1.1019 * t_c * t_c * chord_m


def inertia_parameter(delta_m: float, V: float, d_m: float, mu_a: float) -> float:
    """K = ρ_w δ² V/(18 d μ_a), Eq. (3.5)."""
    return RHO_WATER * delta_m * delta_m * V / (18.0 * d_m * mu_a)


def drop_reynolds(delta_m: float, V: float, rho_a: float, mu_a: float) -> float:
    """Re_δ = V δ ρ_a/μ_a, Eq. (3.10)."""
    return V * delta_m * rho_a / mu_a


def range_parameter(Re_delta: float) -> float:
    """λ/λ_Stokes, Eq. (3.12)."""
    return 1.0 / (0.8388 + 0.001483 * Re_delta + 0.1847 * math.sqrt(Re_delta))


def modified_inertia(K: float, lam_ratio: float) -> float:
    """K₀ = 1/8 + (λ/λ_Stokes)(K − 1/8), Eq. (3.8). Para K ≤ 1/8 devolve 1/8 (sem impacto)."""
    if K <= 0.125:
        return 0.125
    return 0.125 + lam_ratio * (K - 0.125)


def beta0(K0: float) -> float:
    """β₀ na linha de estagnação, Eq. (3.13). K₀ ≤ 1/8 → 0."""
    if K0 <= 0.125:
        return 0.0
    x = float(1.40 * (K0 - 0.125) ** 0.84)
    return x / (1.0 + x)


@dataclass(frozen=True)
class Impingement:
    K: float
    Re_delta: float
    lam_ratio: float
    K0: float
    beta0: float
    #: intervalo de β₀ com a diferença publicada contra o LEWICE (−4,7 % … +0,23 %, NACA 0012): [β₀/1,0023, β₀/0,953]
    beta0_lo: float
    beta0_hi: float
    notes: tuple[str, ...]


def stagnation_impingement(delta_m: float, V: float, d_m: float, rho_a: float, mu_a: float) -> Impingement:
    """K, Re_δ, λ/λ_Stokes, K₀ e β₀ com as propriedades à temperatura estática (como no Apêndice B do manual)."""
    if delta_m <= 0 or V <= 0 or d_m <= 0:
        raise ValueError("δ, V e d têm de ser positivos")
    K = inertia_parameter(delta_m, V, d_m, mu_a)
    Re = drop_reynolds(delta_m, V, rho_a, mu_a)
    lam = range_parameter(Re)
    K0 = modified_inertia(K, lam)
    b = beta0(K0)
    notes: list[str] = []
    if Re < 14 or Re > 800:
        notes.append(f"Re_δ = {Re:.0f} fora do ajuste da Eq. (3.12) (14–800): λ/λ_Stokes extrapolado")
    if K > 7.5:
        notes.append(f"K = {K:.2f} > 7,5 (limite de Langmuir & Blodgett para a Eq. 3.13); Anderson mostra concordância "
                     "com o LEWICE até K₀ ≈ 34 (NACA 0012)")
    if K <= 0.125:
        notes.append("K ≤ 1/8: sem impacto de gotas (Langmuir & Blodgett)")
    return Impingement(K, Re, lam, K0, b, b / 1.0023, min(1.0, b / 0.953), tuple(notes))
