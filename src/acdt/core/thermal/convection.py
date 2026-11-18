# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Correlações clássicas de convecção e radiação (Incropera, DeWitt, Bergman & Lavine, 6.ª ed., 2007).

Cada função devolve o número de Nusselt médio (ou h) e avisa quando sai da gama de validade declarada no livro;
fora da gama o valor é calculado na mesma, mas a função :func:`validity` regista-o (o chamador decide).

* Placa plana, escoamento paralelo, média em L (propriedades à temperatura de filme):
  laminar Nu = 0,664 Re^½ Pr^⅓ (Eq. 7.30, Pr ≥ 0,6); mista com transição a Re_x,c = 5×10⁵
  Nu = (0,037 Re^0,8 − 871) Pr^⅓ (Eq. 7.38, 0,6 ≤ Pr ≤ 60, Re ≤ 10⁸); turbulenta desde o bordo de ataque
  (camada tripada) Nu = 0,037 Re^0,8 Pr^⅓ (Eq. 7.38 com Re_x,c → 0).
* Convecção natural, placa vertical: Churchill & Chu, Nu = {0,825 + 0,387 Ra^⅙/[1 + (0,492/Pr)^(9/16)]^(8/27)}²
  (Eq. 9.26, toda a gama de Ra). Placas horizontais com L = A/P: superfície superior quente
  Nu = 0,54 Ra^¼ (10⁴–10⁷, Eq. 9.30), 0,15 Ra^⅓ (10⁷–10¹¹, Eq. 9.31); inferior quente 0,27 Ra^¼ (10⁵–10¹⁰,
  Eq. 9.32). β = 1/T_f (gás perfeito).
* Escoamento interno em conduta: Dittus–Boelter Nu = 0,023 Re^0,8 Pr^n, n = 0,4 a aquecer o fluido, 0,3 a
  arrefecer (Eq. 8.60; Re ≥ 10 000, 0,6 ≤ Pr ≤ 160, L/D ≥ 10); laminar completamente desenvolvido Nu = 3,66
  (T_s uniforme, Eq. 8.55) ou 4,36 (fluxo uniforme, Eq. 8.53), Re < 2300.
* Radiação de uma superfície pequena num envolvente grande: q = εσA(T_s⁴ − T_viz⁴) (Eq. 1.7).
* Capacidade concentrada: Bi = h·L_c/k < 0,1 (Eq. 5.10), τ = ρVc/(hA_s) (Eq. 5.7), θ/θ_i = exp(−t/τ) (Eq. 5.6).
* Temperatura de parede adiabática T_aw = T + r·V²/(2c_p), r = Pr^½ (laminar) ou Pr^⅓ (turbulento):
  White, *Viscous Fluid Flow*, 3.ª ed. (2006), relações de recuperação da camada limite compressível.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .air import CP_AIR, SIGMA_SB, AirProps, air_props

INCROPERA = ("Incropera, DeWitt, Bergman & Lavine, Fundamentals of Heat and Mass Transfer, 6.ª ed. (Wiley, 2007)")
WHITE = "White, Viscous Fluid Flow, 3.ª ed. (McGraw-Hill, 2006) — fator de recuperação"
G = 9.80665
RE_XC = 5.0e5


@dataclass
class Convection:
    """Coeficiente de convecção médio com a correlação usada e avisos de validade."""

    h: float
    Nu: float
    correlation: str
    Re: float | None = None
    Ra: float | None = None
    Pr: float | None = None
    warnings: list[str] = field(default_factory=list)


def film_props(T_s: float, T_inf: float, p: float) -> AirProps:
    return air_props(0.5 * (T_s + T_inf), p)


def flat_plate_forced(V: float, L: float, T_s: float, T_inf: float, p: float, *, tripped: bool = False,
                      props: AirProps | None = None) -> Convection:
    """h médio numa placa plana de comprimento L em escoamento paralelo (Eqs. 7.30 / 7.38)."""
    if L <= 0 or V <= 0:
        raise ValueError("placa plana forçada precisa de V > 0 e L > 0")
    pr = props or film_props(T_s, T_inf, p)
    Re = V * L / pr.nu
    Pr = pr.Pr
    w: list[str] = []
    if Pr < 0.6:
        w.append(f"Pr = {Pr:.3f} < 0,6 (fora das Eqs. 7.30/7.38)")
    if tripped:
        Nu, corr = 0.037 * Re ** 0.8 * Pr ** (1 / 3), "Incropera Eq. 7.38 (Re_x,c → 0, turbulenta desde o bordo)"
    elif Re <= RE_XC:
        Nu, corr = 0.664 * Re ** 0.5 * Pr ** (1 / 3), "Incropera Eq. 7.30 (laminar)"
    else:
        Nu, corr = (0.037 * Re ** 0.8 - 871.0) * Pr ** (1 / 3), "Incropera Eq. 7.38 (mista, Re_x,c = 5×10⁵)"
        if Re > 1e8:
            w.append(f"Re_L = {Re:.3g} > 10⁸ (fora da Eq. 7.38)")
    return Convection(Nu * pr.k / L, Nu, corr, Re=Re, Pr=Pr, warnings=w)


def rayleigh(T_s: float, T_inf: float, L: float, pr: AirProps) -> float:
    beta = 1.0 / pr.T_K
    return G * beta * abs(T_s - T_inf) * L ** 3 / (pr.nu * pr.alpha)


def vertical_plate_natural(L: float, T_s: float, T_inf: float, p: float, *, props: AirProps | None = None
                           ) -> Convection:
    """Churchill & Chu, placa vertical de altura L, toda a gama de Ra (Incropera Eq. 9.26)."""
    if L <= 0:
        raise ValueError("altura L > 0")
    pr = props or film_props(T_s, T_inf, p)
    Ra = rayleigh(T_s, T_inf, L, pr)
    Pr = pr.Pr
    Nu = (0.825 + 0.387 * Ra ** (1 / 6) / (1 + (0.492 / Pr) ** (9 / 16)) ** (8 / 27)) ** 2
    w = [] if Ra <= 1e13 else [f"Ra = {Ra:.3g} > 10¹³"]
    return Convection(Nu * pr.k / L, Nu, "Incropera Eq. 9.26 (Churchill & Chu, placa vertical)", Ra=Ra, Pr=Pr,
                      warnings=w)


def horizontal_plate_natural(area: float, perimeter: float, T_s: float, T_inf: float, p: float, *,
                             hot_side_up: bool, props: AirProps | None = None) -> Convection:
    """Placa horizontal, L = A/P (Incropera Eqs. 9.30–9.32). ``hot_side_up``: superfície superior quente (ou
    inferior fria)."""
    L = area / perimeter
    pr = props or film_props(T_s, T_inf, p)
    Ra = rayleigh(T_s, T_inf, L, pr)
    w: list[str] = []
    if hot_side_up:
        if Ra <= 1e7:
            Nu, corr = 0.54 * Ra ** 0.25, "Incropera Eq. 9.30"
            if Ra < 1e4:
                w.append(f"Ra = {Ra:.3g} < 10⁴ (fora da Eq. 9.30)")
        else:
            Nu, corr = 0.15 * Ra ** (1 / 3), "Incropera Eq. 9.31"
            if Ra > 1e11:
                w.append(f"Ra = {Ra:.3g} > 10¹¹ (fora da Eq. 9.31)")
    else:
        Nu, corr = 0.27 * Ra ** 0.25, "Incropera Eq. 9.32"
        if not 1e5 <= Ra <= 1e10:
            w.append(f"Ra = {Ra:.3g} fora de 10⁵–10¹⁰ (Eq. 9.32)")
    return Convection(Nu * pr.k / L, Nu, corr, Ra=Ra, Pr=pr.Pr, warnings=w)


def duct_internal(m_dot: float, D_h: float, area: float, T_m: float, p: float, *, heating: bool,
                  uniform_flux: bool = False, props: AirProps | None = None) -> Convection:
    """Conduta: Dittus–Boelter (Eq. 8.60) em turbulento, 3,66/4,36 em laminar completamente desenvolvido."""
    pr = props or air_props(T_m, p)
    Re = m_dot * D_h / (area * pr.mu)
    Pr = pr.Pr
    w: list[str] = []
    if Re >= 1e4:
        n = 0.4 if heating else 0.3
        Nu, corr = 0.023 * Re ** 0.8 * Pr ** n, f"Incropera Eq. 8.60 (Dittus–Boelter, n = {n})"
    elif Re < 2300:
        Nu = 4.36 if uniform_flux else 3.66
        corr = "Incropera Eq. 8.53 (fluxo uniforme)" if uniform_flux else "Incropera Eq. 8.55 (T_s uniforme)"
    else:
        Nu, corr = 0.023 * Re ** 0.8 * Pr ** (0.4 if heating else 0.3), "Dittus–Boelter em transição"
        w.append(f"Re = {Re:.0f} em transição (2300–10⁴): Dittus–Boelter fora da gama (Eq. 8.60 pede Re ≥ 10⁴)")
    return Convection(Nu * pr.k / D_h, Nu, corr, Re=Re, Pr=Pr, warnings=w)


def radiation(eps: float, area: float, T_s: float, T_sur: float) -> float:
    """q = εσA(T_s⁴ − T_viz⁴) [W] (Incropera Eq. 1.7)."""
    return float(eps * SIGMA_SB * area * (T_s ** 4 - T_sur ** 4))


def biot(h: float, Lc: float, k: float) -> float:
    return h * Lc / k


def adiabatic_wall_T(T_inf: float, V: float, Pr: float, turbulent: bool) -> float:
    r = Pr ** (1 / 3) if turbulent else Pr ** 0.5
    return float(T_inf + r * V * V / (2.0 * CP_AIR))


def lumped_time_to(T_target: float, T_i: float, T_inf: float, tau: float) -> float:
    """Tempo até T_target em resposta de capacidade concentrada (Incropera Eq. 5.5): t = τ·ln(θ_i/θ)."""
    th, thi = T_target - T_inf, T_i - T_inf
    if th == 0 or th / thi <= 0:
        return math.inf
    return float(tau * math.log(thi / th))
