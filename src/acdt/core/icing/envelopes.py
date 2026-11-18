# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Envelopes de formação de gelo de projeto: 14 CFR Parte 25, Apêndice C (docs/GELO.md).

* **LWC × MVD × temperatura** (Figuras 1 e 4 do Apêndice C): valores transcritos **exatamente** das Tabelas 1 e 2 de
  Jeck, R. K., *Icing Design Envelopes (14 CFR Parts 25 and 29, Appendix C) Converted to a Distance-Based Format*,
  DOT/FAA/AR-00/30 (FAA, 2002) — colunas das distâncias padrão (2,6 nmi intermitente máximo; 17,4 nmi contínuo
  máximo), 0/−10/−20/−30 °C, MVD 15–40 µm.
* **Fator de extensão horizontal F** (Figuras 3 e 6): fatores F das mesmas tabelas (0,26–5 nmi intermitente;
  5–300 nmi contínuo). Os valores do corpo das tabelas de Jeck são LWC_padrão × F (arredondados a 3 casas).
* **Gelo na descolagem** (Parte I(c), texto do Apêndice C, eCFR): LWC 0,35 g/m³, MED 20 µm, −9 °C, do solo a 1500 ft
  acima da pista.
* **Envelope altitude–temperatura** (Figuras 2 e 5): vértices **lidos da figura** (reprodução em Jeck, Figs. 2 e 5)
  sobre as linhas da grelha — PRESSUPOSTO: leitura gráfica, incerteza ±500 ft / ±2 °F; pontos a menos disso da
  fronteira ficam ``fronteira`` (desconhecido). Na Figura 5 a zona a tracejado («possible extent of limits») fica
  ``possivel``.

PRESSUPOSTOS de interpolação: bilinear em (T, MVD) entre os nós tabelados e linear em log(HE) para F. Fora dos nós
tabelados devolve-se ``None`` (desconhecido) — nunca se extrapola. Acima de 0 °C não há envelope do Apêndice C.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

SOURCE_LWC = "14 CFR 25 Ap. C Figs. 1 e 4, transcritas em Jeck, DOT/FAA/AR-00/30 (2002), Tabelas 1 e 2"
SOURCE_F = "14 CFR 25 Ap. C Figs. 3 e 6, fatores F de Jeck, DOT/FAA/AR-00/30 (2002), Tabelas 1 e 2"
SOURCE_TO = "14 CFR 25 Ap. C, Parte I(c) (eCFR)"
SOURCE_ALT = "14 CFR 25 Ap. C Figs. 2 e 5 (reprodução em Jeck, DOT/FAA/AR-00/30) — leitura gráfica"

TEMPS_C = (-30.0, -20.0, -10.0, 0.0)
MVDS_UM = (15.0, 20.0, 25.0, 30.0, 35.0, 40.0)

#: LWC [g/m³] à distância padrão; chave T [°C] → valores para MVD 15, 20, 25, 30, 35, 40 µm
CONTINUOUS_LWC: dict[float, tuple[float, ...]] = {   # 17,4 nmi — Jeck Tabela 2
    0.0: (0.800, 0.635, 0.500, 0.375, 0.260, 0.155),
    -10.0: (0.590, 0.415, 0.300, 0.220, 0.150, 0.100),
    -20.0: (0.300, 0.210, 0.150, 0.110, 0.080, 0.060),
    -30.0: (0.200, 0.140, 0.100, 0.070, 0.050, 0.040),
}
INTERMITTENT_LWC: dict[float, tuple[float, ...]] = {  # 2,6 nmi — Jeck Tabela 1
    0.0: (2.900, 2.500, 1.750, 1.325, 1.000, 0.750),
    -10.0: (2.500, 2.200, 1.450, 1.025, 0.713, 0.513),
    -20.0: (1.925, 1.700, 1.150, 0.800, 0.575, 0.400),
    -30.0: (1.100, 0.988, 0.713, 0.500, 0.350, 0.250),
}
#: fatores F por extensão horizontal [nmi]
CONTINUOUS_F: tuple[tuple[float, float], ...] = ((5.0, 1.340), (10.0, 1.160), (17.4, 1.000), (50.0, 0.665),
                                                 (100.0, 0.460), (200.0, 0.290), (300.0, 0.215))
INTERMITTENT_F: tuple[tuple[float, float], ...] = ((0.26, 1.350), (0.5, 1.295), (1.0, 1.190), (1.5, 1.115),
                                                   (2.6, 1.000), (4.0, 0.905), (5.0, 0.860))
STANDARD_HE_NMI = {"continuous": 17.4, "intermittent": 2.6}
TAKEOFF = {"lwc_g_m3": 0.35, "mvd_um": 20.0, "T_C": -9.0, "height_agl_ft": 1500.0}
#: nota das Figs. 1 e 4: gama de altitude-pressão
ALT_RANGE_FT = {"continuous": (0.0, 22000.0), "intermittent": (4000.0, 22000.0)}

FT = 0.3048
NMI = 1852.0

# Vértices (altitude-pressão [ft], temperatura [°F]) lidos das Figs. 2 e 5
FIG2 = ((0.0, 32.0), (12000.0, 32.0), (22000.0, -4.0), (22000.0, -22.0), (0.0, -22.0))
FIG5_SOLID = ((4000.0, 26.0), (12000.0, 26.0), (22000.0, -10.0), (22000.0, -22.0), (14000.0, -22.0), (4000.0, 14.0))
FIG5_DASHED = ((14000.0, -22.0), (22000.0, -22.0), (22000.0, -10.0), (30000.0, -40.0), (19000.0, -40.0))
GRAPH_TOL_FT, GRAPH_TOL_F = 500.0, 2.0


def _interp(xs: tuple[float, ...], ys: tuple[float, ...], x: float) -> float:
    i = bisect.bisect_right(xs, x)
    if i <= 0:
        return ys[0]
    if i >= len(xs):
        return ys[-1]
    x0, x1 = xs[i - 1], xs[i]
    return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - x0) / (x1 - x0)


def lwc_standard(kind: str, T_C: float, mvd_um: float) -> float | None:
    """LWC [g/m³] à distância padrão (17,4/2,6 nmi). ``None`` fora de −30…0 °C ou 15–40 µm (sem extrapolação)."""
    tab = {"continuous": CONTINUOUS_LWC, "intermittent": INTERMITTENT_LWC}[kind]
    if not (TEMPS_C[0] - 1e-9 <= T_C <= TEMPS_C[-1] + 1e-9 and MVDS_UM[0] - 1e-9 <= mvd_um <= MVDS_UM[-1] + 1e-9):
        return None
    per_T = tuple(_interp(MVDS_UM, tab[t], mvd_um) for t in TEMPS_C)
    return _interp(TEMPS_C, per_T, T_C)


def he_factor(kind: str, he_nmi: float) -> float | None:
    """Fator F (Figs. 3/6), linear em log(HE) entre os nós de Jeck. ``None`` fora da gama tabelada."""
    nodes = {"continuous": CONTINUOUS_F, "intermittent": INTERMITTENT_F}[kind]
    lo, hi = nodes[0][0], nodes[-1][0]
    if he_nmi <= 0 or he_nmi < lo * (1 - 1e-9) or he_nmi > hi * (1 + 1e-9):
        return None
    xs = tuple(math.log(h) for h, _ in nodes)
    return _interp(xs, tuple(f for _, f in nodes), math.log(he_nmi))


@dataclass(frozen=True)
class LWCResult:
    lwc_g_m3: float | None
    lwc_standard_g_m3: float | None
    F: float | None
    he_nmi: float | None
    he_used_nmi: float | None
    note: str
    source: str


def design_lwc(kind: str, T_C: float, mvd_um: float, he_nmi: float | None = None,
               clamp_long: bool = True) -> LWCResult:
    """LWC de projeto [g/m³] para o envelope ``continuous``/``intermittent``/``takeoff``.

    ``he_nmi`` = extensão horizontal da exposição (None → distância padrão). Contínuo acima de 300 nmi com
    ``clamp_long``: usa F(300 nmi) — PRESSUPOSTO conservador (F decresce com HE, logo sobrestima o LWC)."""
    if kind == "takeoff":
        ok = abs(T_C - TAKEOFF["T_C"]) < 1e-9 and abs(mvd_um - TAKEOFF["mvd_um"]) < 1e-9
        return LWCResult(TAKEOFF["lwc_g_m3"] if ok else None, TAKEOFF["lwc_g_m3"], 1.0, he_nmi, he_nmi,
                         "" if ok else "o gelo de descolagem só está definido a −9 °C e 20 µm", SOURCE_TO)
    std = lwc_standard(kind, T_C, mvd_um)
    if T_C > 0.0:
        return LWCResult(0.0, None, None, he_nmi, None, "T > 0 °C: fora do Apêndice C (sem gelo de projeto)",
                         SOURCE_LWC)
    if std is None:
        return LWCResult(None, None, None, he_nmi, None,
                         f"T = {T_C:.1f} °C / MVD = {mvd_um:.0f} µm fora das tabelas (−30…0 °C, 15–40 µm)", SOURCE_LWC)
    if he_nmi is None:
        return LWCResult(std, std, 1.0, None, STANDARD_HE_NMI[kind], "distância padrão", SOURCE_LWC)
    nodes = {"continuous": CONTINUOUS_F, "intermittent": INTERMITTENT_F}[kind]
    he_used = he_nmi
    note = ""
    if kind == "continuous" and he_nmi > nodes[-1][0] and clamp_long:
        he_used = nodes[-1][0]
        note = f"HE = {he_nmi:.0f} nmi > 300 nmi: F(300 nmi) — PRESSUPOSTO conservador"
    F = he_factor(kind, he_used)
    if F is None:
        return LWCResult(None, std, None, he_nmi, None,
                         f"HE = {he_nmi:.3g} nmi fora da gama do fator F ({nodes[0][0]}–{nodes[-1][0]} nmi)",
                         SOURCE_F)
    return LWCResult(std * F, std, F, he_nmi, he_used, note, SOURCE_LWC + "; " + SOURCE_F)


def _seg_dist(px: float, py: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    qx, qy = ax + t * dx - px, ay + t * dy - py
    return math.hypot(qx, qy)


def _inside(poly: tuple[tuple[float, float], ...], x: float, y: float) -> bool:
    c = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _norm(poly: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    return tuple((a / GRAPH_TOL_FT, t / GRAPH_TOL_F) for a, t in poly)


def _classify(poly: tuple[tuple[float, float], ...], alt_ft: float, T_F: float) -> tuple[bool, float]:
    p = _norm(poly)
    x, y = alt_ft / GRAPH_TOL_FT, T_F / GRAPH_TOL_F
    d = min(_seg_dist(x, y, p[i], p[(i + 1) % len(p)]) for i in range(len(p)))
    return _inside(p, x, y), d


def in_envelope(kind: str, pressure_altitude_m: float, T_C: float) -> str:
    """Ponto (altitude-pressão, temperatura estática) face ao envelope das Figs. 2/5: ``dentro``, ``fora``,
    ``fronteira`` (a menos de ±500 ft/±2 °F da linha lida — desconhecido) ou ``possivel`` (zona a tracejado da
    Fig. 5 — desconhecido)."""
    alt_ft = pressure_altitude_m / FT
    T_F = T_C * 1.8 + 32.0
    if kind == "takeoff":
        return "dentro" if abs(T_C - TAKEOFF["T_C"]) < 1e-9 and alt_ft <= TAKEOFF["height_agl_ft"] else "fora"
    poly = FIG2 if kind == "continuous" else FIG5_SOLID
    inside, d = _classify(poly, alt_ft, T_F)
    if d <= 1.0:
        return "fronteira"
    if inside:
        return "dentro"
    if kind == "intermittent":
        ins2, d2 = _classify(FIG5_DASHED, alt_ft, T_F)
        if ins2 or d2 <= 1.0:
            return "possivel"
    return "fora"


def envelope_T_range(kind: str, pressure_altitude_m: float) -> tuple[float, float] | None:
    """Gama de temperatura estática [°C] do envelope (zona sólida das Figs. 2/5) a esta altitude-pressão, por
    interseção da vertical com o polígono lido. ``None`` se a altitude estiver fora do envelope."""
    if kind == "takeoff":
        return (TAKEOFF["T_C"], TAKEOFF["T_C"]) if pressure_altitude_m / FT <= TAKEOFF["height_agl_ft"] else None
    poly = FIG2 if kind == "continuous" else FIG5_SOLID
    x = pressure_altitude_m / FT
    ys: list[float] = []
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if x1 == x2:
            if abs(x - x1) < 1e-9:
                ys += [y1, y2]
            continue
        if min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9:
            ys.append(y1 + (y2 - y1) * (x - x1) / (x2 - x1))
    if not ys:
        return None
    return ((min(ys) - 32.0) / 1.8, (max(ys) - 32.0) / 1.8)


def envelope_temperatures(kind: str, pressure_altitude_m: float) -> list[float]:
    """Temperaturas a varrer a esta altitude (Apêndice C, Parte II(a): «full range of atmospheric icing
    conditions»): extremos da gama do envelope (limitados a −30…0 °C, a gama tabelada) e os nós tabelados
    0/−10/−20/−30 °C que caem dentro dela. Lista vazia → altitude fora do envelope."""
    r = envelope_T_range(kind, pressure_altitude_m)
    if r is None:
        return []
    lo, hi = max(r[0], TEMPS_C[0]), min(r[1], TEMPS_C[-1])
    if lo > hi:
        return []
    out = {round(lo, 6), round(hi, 6)} | {t for t in TEMPS_C if lo - 1e-9 <= t <= hi + 1e-9}
    return sorted(out, reverse=True)
