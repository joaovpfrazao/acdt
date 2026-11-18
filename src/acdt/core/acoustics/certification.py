# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""14 CFR Parte 36, Apêndice G — ruído de descolagem de aviões pequenos a hélice (texto eCFR consultado a
18 nov 2026).

* G36.301(b): monomotores com pedido de certificado de tipo antes de 3 fev 2006 e multimotores — 76 dB(A) até
  600 kg (1320 lb), a subir com o logaritmo do peso a 9,83 dB(A) por duplicação até 88 dB(A), constante até
  8618 kg (19 000 lb).
* G36.301(c): monomotores com pedido em/após 3 fev 2006 — 70 dB(A) até 570 kg (1257 lb), 10,75 dB(A) por
  duplicação até 85 dB(A), constante até 8618 kg.
* G36.111(a)–(c): ponto de medição a 2500 m do início da corrida, na linha central; trajetória de referência em
  dois segmentos — potência de descolagem até 15 m (50 ft) com a distância de descolagem aprovada, depois subida a
  V_y com potência de descolagem; atmosfera de referência 1013,25 hPa, 15 °C, 70 % HR, vento nulo.
* G36.107(a): microfone invertido 7 mm acima de uma placa metálica de 40 cm nivelada com o solo.

O limite de ICAO Anexo 16 Vol. I Cap. 10 não está implementado (texto não verificado).
"""
from __future__ import annotations

import math

REF = "14 CFR Parte 36, Apêndice G (G36.111, G36.301), eCFR"
X_MEAS_M = 2500.0
H_SEG1_M = 15.24  # 50 ft
MTOW_MAX_KG = 8618.0


def part36_g_limit(mtow_kg: float, single_engine_after_2006: bool) -> float | None:
    """Limite dB(A) de G36.301 (b) ou (c); None acima de 8618 kg (fora do âmbito)."""
    if mtow_kg > MTOW_MAX_KG or mtow_kg <= 0.0:
        return None
    if single_engine_after_2006:
        L0, W0, slope, cap = 70.0, 570.0, 10.75, 85.0
    else:
        L0, W0, slope, cap = 76.0, 600.0, 9.83, 88.0
    if mtow_kg <= W0:
        return L0
    return min(cap, L0 + slope * math.log2(mtow_kg / W0))


def part36_g_reference_height(d_takeoff_50ft_m: float, roc_m_s: float, vy_m_s: float) -> float | None:
    """Altura de referência sobre o ponto de medição (G36.111(c)), subida a V_y com gradiente constante.
    None se a descolagem a 15 m não acaba antes dos 2500 m ou sem subida."""
    if not (d_takeoff_50ft_m < X_MEAS_M) or roc_m_s <= 0.0 or vy_m_s <= roc_m_s:
        return None
    tan_g = roc_m_s / math.sqrt(vy_m_s ** 2 - roc_m_s ** 2)
    return H_SEG1_M + (X_MEAS_M - d_takeoff_50ft_m) * tan_g
