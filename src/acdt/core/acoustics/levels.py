# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Níveis de pressão sonora (dB re 20 µPa) e soma energética.

* Nível de pressão sonora L_p = 20·log10(p_rms / p_ref), p_ref = 20 µPa (IEC 61672-1:2013, 3.2, Nota 2).
* Fontes incoerentes somam-se em energia: L = 10·log10 Σ 10^(L_i/10) (Kinsler, Frey, Coppens & Sanders,
  *Fundamentals of Acoustics*, 4.ª ed., Wiley 2000, Cap. 5 — níveis em decibel e combinação de fontes incoerentes).
* Divergência esférica em campo livre: p_rms ∝ 1/r, ΔL = −20·log10(r2/r1) (Kinsler et al. 2000, Cap. 5, onda
  esférica).
"""
from __future__ import annotations

import math
from typing import Iterable

P_REF = 20e-6  # Pa


def lp_from_prms(p_rms: float) -> float:
    """L_p [dB re 20 µPa]; p_rms ≤ 0 → −inf (sem som, não «zero dB»)."""
    return 20.0 * math.log10(p_rms / P_REF) if p_rms > 0.0 else -math.inf


def prms_from_lp(lp: float) -> float:
    return float(P_REF * 10.0 ** (lp / 20.0))


def level_sum(levels: Iterable[float]) -> float:
    """Soma energética (fontes incoerentes); níveis −inf não contribuem; lista vazia → −inf."""
    s = sum(10.0 ** (v / 10.0) for v in levels if math.isfinite(v))
    return 10.0 * math.log10(s) if s > 0.0 else -math.inf


def spherical_spreading_db(r: float, r_ref: float) -> float:
    """ΔL de r_ref para r em campo livre (negativo quando r > r_ref)."""
    return -20.0 * math.log10(r / r_ref)
