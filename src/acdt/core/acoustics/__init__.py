# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Acústica de baixa fidelidade, domínio-agnóstica (disciplina «ruído»; docs/RUIDO.md).

Módulos (cada um só com métodos publicados e citados):

* :mod:`.levels` — níveis em dB re 20 µPa, soma energética, divergência esférica;
* :mod:`.weighting` — ponderação A (IEC 61672-1:2013, Anexo E, Eq. E.6);
* :mod:`.absorption` — absorção atmosférica de tons puros (ISO 9613-1:1993, Eq. 3–5 e Anexo B);
* :mod:`.hearing` — limiar de audição em campo livre (ISO 226:2003, Tabela 1, T_f);
* :mod:`.rotor` — ruído tonal de carga de hélices/rotores (Gutin 1936, forma de campo afastado) e ruído de
  banda larga (vórtices) de Schlegel, King & Mull (1966), como apresentados por Marte & Kurtz (1970);
* :mod:`.propagation` — nível no observador (espectro de fonte → divergência + absorção + Doppler + ponderação A),
  sobrevoo (L_A,max) e alcance de deteção auditiva;
* :mod:`.certification` — limites de 14 CFR Parte 36, Apêndice G (G36.301) e altura de referência (G36.111).
"""
from __future__ import annotations

from .absorption import alpha_iso9613
from .hearing import threshold_iso226
from .levels import P_REF, level_sum, lp_from_prms, prms_from_lp
from .weighting import a_weighting

__all__ = ["P_REF", "a_weighting", "alpha_iso9613", "level_sum", "lp_from_prms", "prms_from_lp", "threshold_iso226"]
