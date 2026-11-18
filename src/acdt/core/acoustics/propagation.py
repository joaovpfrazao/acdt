# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Do espectro da fonte ao observador: nível, sobrevoo e alcance de deteção auditiva.

Cadeia por componente (tom ou banda de oitava), campo livre, atmosfera homogénea:

1. nível da fonte à distância r e ângulo θ (a fonte já inclui a divergência esférica: Gutin ∝ 1/r; a banda larga
   escala por −20 log10(r/r_ref));
2. absorção atmosférica −α(f)·r com α da ISO 9613-1 (:mod:`.absorption`), à frequência recebida;
3. frequência recebida com o efeito Doppler da fonte em movimento, f_obs = f/(1 − M cos θ) (Marte & Kurtz, JPL TR
   32-1462, 1970, Apêndice C, passo 11: «fundamental frequency nB/[2π(1 − M_F cos θ)]»);
4. reflexão no solo: ΔL declarado pelo utilizador (0 dB = campo livre; +6,02 dB = duplicação de pressão num
   microfone sobre placa rígida, como em 14 CFR 36 Ap. G, G36.107(a) — Kinsler et al., *Fundamentals of
   Acoustics*, 4.ª ed., 2000, reflexão numa fronteira rígida);
5. ponderação A à frequência recebida (:mod:`.weighting`); bandas de oitava ponderadas no centro da banda
   (PRESSUPOSTO, prática de soma por bandas);
6. soma energética de todos os componentes (fontes incoerentes; :mod:`.levels`).

Sobrevoo: trajetória retilínea nivelada à altura H, observador no solo com afastamento lateral y; L_A,max é o
máximo de L_A(t) e L_AE (nível de exposição sonora) = 10 log10 ∫ 10^(L_A(t)/10) dt / 1 s (ISO 1996-1:2016,
definição de nível de exposição sonora). O eixo da hélice é o da trajetória (PRESSUPOSTO: atitude e ângulo de
subida desprezados).

Deteção auditiva: um componente é audível quando o seu nível recebido iguala ou excede o limiar
max(T_f(f), L_ambiente(f) + margem), com T_f da ISO 226:2003 (:mod:`.hearing`; definição de limiar = 50 % de
deteção) e o ruído ambiente em bandas de 1/3 de oitava dado pelo utilizador. As bandas de oitava da banda larga
repartem-se igualmente pelas três bandas de 1/3 de oitava (−10 log10 3 dB cada; PRESSUPOSTO de espectro plano na
oitava). O alcance de deteção usa a pior direção da fonte (máximo em θ) a cada distância — limite superior
(conservador para quem quer não ser ouvido). Sem ruído ambiente o resultado é o limite em silêncio. Com ruído
ambiente a regra «nível ≥ banda ambiente + margem» não é o modelo de deteção de sinais de Fidell et al. (1974) e
pode subestimar o alcance (um tom pode ser detetável abaixo do nível da banda de 1/3 de oitava): por isso o
alcance em silêncio é sempre reportado também.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from .absorption import alpha_iso9613, in_validity
from .hearing import threshold_iso226
from .levels import level_sum
from .weighting import a_weighting

LevelFn = Callable[[float, float], float]  # (r [m], θ [rad]) → L_p campo livre sem absorção [dB]
THIRD = 2.0 ** (1.0 / 3.0)


@dataclass
class Component:
    """Um tom (``band='tom'``) ou uma banda de oitava (``band='oitava'``) de uma fonte."""

    name: str
    f_Hz: float
    level: LevelFn
    kind: str = "tonal"        # tonal | banda_larga | motor | outro
    band: str = "tom"          # tom | oitava


@dataclass
class Atmosphere:
    T_C: float = 15.0
    rh_pct: float = 70.0
    p_kpa: float = 101.325
    c_m_s: float = 340.294     # velocidade do som na fonte (ISA 0 m por omissão; o chamador passa a da altitude)


@dataclass
class Received:
    LA: float
    Lp: float
    components: list[dict[str, float | str]] = field(default_factory=list)
    out_of_validity: list[str] = field(default_factory=list)


def doppler(f: float, mach: float, theta: float) -> float:
    return f / max(1.0 - mach * math.cos(theta), 1e-6)


def received(comps: Sequence[Component], r: float, theta: float, atm: Atmosphere, mach: float = 0.0,
             ground_dB: float = 0.0, detail: bool = False) -> Received:
    lps: list[float] = []
    las: list[float] = []
    rows: list[dict[str, float | str]] = []
    oov: list[str] = []
    for c in comps:
        f = doppler(c.f_Hz, mach, theta)
        L0 = c.level(r, theta)
        if not math.isfinite(L0):
            continue
        L = L0 - alpha_iso9613(f, atm.T_C, atm.rh_pct, atm.p_kpa) * r + ground_dB
        if not in_validity(f, atm.T_C, atm.rh_pct, atm.p_kpa):
            oov.append(c.name)
        la = L + a_weighting(f)
        lps.append(L)
        las.append(la)
        if detail:
            rows.append({"name": c.name, "kind": c.kind, "band": c.band, "f_source_Hz": c.f_Hz, "f_received_Hz": f,
                         "Lp_dB": L, "LA_dBA": la})
    return Received(level_sum(las), level_sum(lps), rows, oov)


def flyover(comps: Sequence[Component], H: float, V: float, atm: Atmosphere, y: float = 0.0,
            ground_dB: float = 0.0, n: int = 241, span: float = 15.0) -> dict[str, float]:
    """L_A,max e L_AE de uma passagem retilínea à altura H [m] e velocidade V [m/s]."""
    mach = V / atm.c_m_s
    d0 = math.hypot(H, y)
    xs = [d0 * span * (2.0 * i / (n - 1) - 1.0) for i in range(n)]
    las: list[float] = []
    for s in xs:
        r = math.sqrt(s * s + d0 * d0)
        th = math.acos(max(-1.0, min(1.0, -s / r)))
        las.append(received(comps, r, th, atm, mach, ground_dB).LA)
    i = max(range(n), key=lambda k: las[k])
    dt = (xs[1] - xs[0]) / V if V > 0 else 0.0
    sel = 10.0 * math.log10(sum(10.0 ** (v / 10.0) for v in las if math.isfinite(v)) * dt) if dt > 0 else math.nan
    r_max = math.sqrt(xs[i] ** 2 + d0 ** 2)
    return {"LAmax_dBA": las[i], "SEL_dBA": sel, "theta_at_max_deg": math.degrees(math.acos(-xs[i] / r_max)),
            "r_at_max_m": r_max}


def _thirds(c: Component, f: float, L: float) -> list[tuple[float, float]]:
    if c.band == "oitava":
        d = 10.0 * math.log10(3.0)
        return [(f / THIRD, L - d), (f, L - d), (f * THIRD, L - d)]
    return [(f, L)]


def _ambient(amb: Mapping[float, float] | None, f: float) -> float | None:
    """Banda ambiente de 1/3 de oitava que contém f (a de centro mais próximo em log f, até meia banda)."""
    if not amb:
        return None
    fc = min(amb, key=lambda k: abs(math.log10(k) - math.log10(f)))
    return float(amb[fc]) if abs(math.log10(fc) - math.log10(f)) <= math.log10(THIRD) / 2.0 + 1e-9 else None


def audibility_margin(comps: Sequence[Component], r: float, theta: float, atm: Atmosphere, mach: float = 0.0,
                      ambient: Mapping[float, float] | None = None, margin_dB: float = 0.0,
                      ground_dB: float = 0.0) -> tuple[float, str]:
    """max_componentes (L_recebido − limiar) [dB] e o componente que manda; −inf se nenhum tem limiar definido."""
    best, who = -math.inf, ""
    for c in comps:
        f = doppler(c.f_Hz, mach, theta)
        L0 = c.level(r, theta)
        if not math.isfinite(L0):
            continue
        L = L0 - alpha_iso9613(f, atm.T_C, atm.rh_pct, atm.p_kpa) * r + ground_dB
        for ff, LL in _thirds(c, f, L):
            tf = threshold_iso226(ff)
            if tf is None:
                continue
            amb = _ambient(ambient, ff)
            thr = tf if amb is None else max(tf, amb + margin_dB)
            if LL - thr > best:
                best, who = LL - thr, c.name
    return best, who


def detection_range(comps: Sequence[Component], atm: Atmosphere, mach: float = 0.0,
                    ambient: Mapping[float, float] | None = None, margin_dB: float = 0.0, ground_dB: float = 0.0,
                    r_min: float = 1.0, r_max: float = 100_000.0, n_theta: int = 37) -> dict[str, float | str | None]:
    """Distância oblíqua máxima a que a fonte é audível (pior direção). None se nem a r_min é audível."""
    thetas = [math.pi * i / (n_theta - 1) for i in range(n_theta)]

    def m(r: float) -> tuple[float, str, float]:
        best = (-math.inf, "", 0.0)
        for th in thetas:
            v, who = audibility_margin(comps, r, th, atm, mach, ambient, margin_dB, ground_dB)
            if v > best[0]:
                best = (v, who, th)
        return best

    lo_m = m(r_min)
    if lo_m[0] < 0.0:
        return {"range_m": None, "governing": None, "theta_deg": None}
    if m(r_max)[0] >= 0.0:
        return {"range_m": r_max, "governing": m(r_max)[1], "theta_deg": None}
    lo, hi = r_min, r_max
    for _ in range(60):
        mid = math.sqrt(lo * hi)
        if m(mid)[0] >= 0.0:
            lo = mid
        else:
            hi = mid
        if hi / lo < 1.0005:
            break
    g = m(lo)
    return {"range_m": lo, "governing": g[1], "theta_deg": math.degrees(g[2])}
