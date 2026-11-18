# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Balanço térmico de Messinger na linha de estagnação, fração de congelação e taxa de acreção (docs/GELO.md).

Messinger, B. L., «Equilibrium Temperature of an Unheated Icing Surface as a Function of Air Speed», *J. Aeronaut.
Sci.* 20(1), 1953, pp. 29–42, na forma de Anderson, NASA/CR-2004-212875 (2004), §3.4–3.5 e Apêndice A:

* h_c = k_a Nu_a/d com Nu_a = 1,14 Pr_a^0,4 Re_a^0,5 (estagnação de um cilindro, Kreith) — Eq. (3.32)–(3.33);
  propriedades à temperatura de filme T_film = (T_s + T_st)/2 — Eq. (3.35);
* h_G = (h_c/c_p,a)(Pr_a/Sc_a)^0,67 — Eq. (3.47); Sc_a = μ_a/(ρ_a D_v) — Eq. (3.48);
* fator de calor relativo b = LWC V β₀ c_p,ws/h_c — Eq. (3.55);
* φ = t_f − t_st − V²/(2 c_p,ws) — Eq. (3.56);
* θ = (t_s − t_st − V²/(2 c_p,a)) + (h_G/h_c)·[(p_ww/T_st − (p_tot/T_tot)(p_w/p_st))/((1/0,622)(p_tot/T_tot) −
  p_ww/T_st)]·Λ_v — Eq. (3.57) (forma compressível de Ruff), fator de recuperação r = 1 na estagnação (§3.5.1);
* fração de congelação n₀ = (c_p,ws/Λ_f)(φ + θ/b) — Eq. (3.59); n₀ ≥ 1 → gelo opaco (rime), 0 < n₀ < 1 → gelo
  vidrado (glaze), n₀ ≤ 0 → sem congelação na estagnação;
* parâmetro de acumulação A_c = LWC V τ/(ρ_i d) — Eq. (3.26); espessura na estagnação Δ = n₀ β₀ LWC V τ/ρ_i —
  Eq. (3.23)/(3.29);
* PRESSUPOSTO (Anderson): ar húmido saturado em relação à água (p_w = p_sat(T_st)), superfície vidrada a 0 °C,
  radiação, sublimação, condução e escoamento de retorno desprezados (§3.5.3–3.5.11).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import properties as pr
from .impingement import Impingement, stagnation_impingement

SOURCE = "Messinger (1953) via Anderson, NASA/CR-2004-212875, Eq. (3.26), (3.29), (3.33), (3.47), (3.55)–(3.59)"


@dataclass(frozen=True)
class StagnationResult:
    T_st: float
    T_tot: float
    p_st: float
    p_tot: float
    rho_a: float
    mu_a: float
    imp: Impingement
    T_film: float
    k_a: float
    Pr: float
    Re_film: float
    Nu: float
    h_c: float          # W/(m²·K)
    h_G: float          # kg/(m²·s)
    Sc: float
    b: float
    phi: float          # K
    theta: float        # K
    n0_raw: float       # fração de congelação analítica (sem truncar)
    n0: float           # truncada a [0, 1]
    ice_type: str       # rime | glaze | sem_gelo
    m_imp: float        # kg/(m²·s) água captada na estagnação
    accretion_rate_m_s: float
    lambda_f: float
    lambda_v: float
    cp_ws: float


def _hc(d: float, V: float, T_st: float, p_st: float, Ts: float) -> tuple[float, float, float, float, float, float]:
    T_film = 0.5 * (Ts + T_st)
    k = pr.k_air(T_film)
    mu_f = pr.mu_air(T_film)
    rho_f = p_st / (pr.R_AIR * T_film)
    Pr = pr.CP_AIR * mu_f / k
    Re = V * d * rho_f / mu_f
    Nu = 1.14 * Pr ** 0.4 * Re ** 0.5
    return T_film, k, Pr, Re, Nu, k * Nu / d


def stagnation(*, T_st: float, V: float, d_m: float, mvd_m: float, lwc_kg_m3: float, p_st: float | None = None,
               p_tot: float | None = None, compressible: bool = True) -> StagnationResult:
    """Linha de estagnação de um cilindro/bordo de ataque (d = diâmetro ou 2 r_le). Dê ``p_st`` (voo) ou ``p_tot``
    (túnel, como nos exemplos do manual). Unidades SI; LWC em kg/m³ (1 g/m³ = 10⁻³ kg/m³)."""
    if (p_st is None) == (p_tot is None):
        raise ValueError("dê exatamente um de p_st ou p_tot")
    if p_tot is None:
        assert p_st is not None
        M2 = V * V / (pr.GAMMA_AIR * pr.R_AIR * T_st)
        p_tot = (p_st * (1.0 + 0.5 * (pr.GAMMA_AIR - 1.0) * M2) ** (pr.GAMMA_AIR / (pr.GAMMA_AIR - 1.0))
                 if compressible else pr.total_pressure_from_static(p_st, T_st, V))
    elif compressible:
        p_st = pr.static_pressure_compressible(p_tot, T_st, V)
    else:
        p_st = pr.static_pressure(p_tot, T_st, V)
    assert p_st is not None
    T_tot = pr.total_temperature(T_st, V)
    rho_a = p_st / (pr.R_AIR * T_st)
    mu_a = pr.mu_air(T_st)
    imp = stagnation_impingement(mvd_m, V, d_m, rho_a, mu_a)
    Ts = pr.T0  # superfície vidrada a 0 °C (Eq. A.14–A.15)
    T_film, k, Pr, Re_f, Nu, hc = _hc(d_m, V, T_st, p_st, Ts)
    mu_f = pr.mu_air(T_film)
    rho_f = p_st / (pr.R_AIR * T_film)
    Dv = pr.diffusivity_vapour(T_film, p_st)
    Sc = mu_f / (rho_f * Dv)
    hG = hc / pr.CP_AIR * (Pr / Sc) ** 0.67
    cp_ws = pr.cp_water_surface(Ts)
    lf, lv = pr.LAMBDA_F_GLAZE, pr.LAMBDA_V_GLAZE
    m_imp = lwc_kg_m3 * V * imp.beta0
    b = m_imp * cp_ws / hc
    phi = pr.T0 - T_st - V * V / (2.0 * cp_ws)
    p_ww = pr.p_sat_water(Ts)
    p_w = pr.p_sat_water(T_st)
    evap = (p_ww / T_st - (p_tot / T_tot) * (p_w / p_st)) / ((1.0 / 0.622) * (p_tot / T_tot) - p_ww / T_st)
    theta = (Ts - T_st - V * V / (2.0 * pr.CP_AIR)) + hG / hc * evap * lv
    if b <= 0:
        n_raw = math.inf
    else:
        n_raw = cp_ws / lf * (phi + theta / b)
    n0 = min(1.0, max(0.0, n_raw))
    kind = "rime" if n_raw >= 1.0 else ("glaze" if n_raw > 0.0 else "sem_gelo")
    if imp.beta0 <= 0:
        kind, n0 = "sem_gelo", 0.0
    rate = n0 * m_imp / pr.RHO_ICE
    return StagnationResult(T_st, T_tot, p_st, p_tot, rho_a, mu_a, imp, T_film, k, Pr, Re_f, Nu, hc, hG, Sc, b, phi,
                            theta, n_raw, n0, kind, m_imp, rate, lf, lv, cp_ws)


def accumulation_parameter(lwc_kg_m3: float, V: float, tau_s: float, d_m: float, rho_i: float = pr.RHO_ICE) -> float:
    """A_c = LWC V τ/(ρ_i d), Eq. (3.26)."""
    return lwc_kg_m3 * V * tau_s / (rho_i * d_m)


def ice_thickness(n0: float, beta0: float, lwc_kg_m3: float, V: float, tau_s: float,
                  rho_i: float = pr.RHO_ICE) -> float:
    """Δ = n₀ β₀ LWC V τ/ρ_i [m], Eq. (3.23) com a fração que congela (Eq. 3.29: Δ/d = n₀ A_c β₀)."""
    return n0 * beta0 * lwc_kg_m3 * V * tau_s / rho_i
