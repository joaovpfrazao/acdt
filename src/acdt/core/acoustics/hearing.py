# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Limiar de audição em campo livre — ISO 226:2003, Tabela 1, coluna T_f.

Definição (ISO 226:2003, 3.7): nível de um som para o qual, em condições especificadas, uma pessoa dá 50 % de
respostas corretas de deteção em ensaios repetidos. Condições (cláusula 1): onda plana progressiva em campo livre,
fonte de frente para o ouvinte, tons puros, audição binaural, ouvintes otologicamente normais de 18 a 25 anos.
A norma indica (Nota 1) que pode aplicar-se a bandas de ruído de 1/3 de oitava.

Fora de 20 Hz – 12,5 kHz a tabela não define limiar: :func:`threshold_iso226` devolve ``None`` (desconhecido, nunca
«audível» nem «inaudível» por omissão). Entre frequências tabeladas interpola-se linearmente em log10(f)
(PRESSUPOSTO de interpolação; a norma só tabela as frequências preferidas da ISO 266).
"""
from __future__ import annotations

import math

FREQ = (20.0, 25.0, 31.5, 40.0, 50.0, 63.0, 80.0, 100.0, 125.0, 160.0, 200.0, 250.0, 315.0, 400.0, 500.0, 630.0,
        800.0, 1000.0, 1250.0, 1600.0, 2000.0, 2500.0, 3150.0, 4000.0, 5000.0, 6300.0, 8000.0, 10000.0, 12500.0)
TF = (78.5, 68.7, 59.5, 51.1, 44.0, 37.5, 31.5, 26.5, 22.1, 17.9, 14.4, 11.4, 8.6, 6.2, 4.4, 3.0, 2.2, 2.4, 3.5,
      1.7, -1.3, -4.2, -6.0, -5.4, -1.5, 6.0, 12.6, 13.9, 12.3)
REFERENCE = "ISO 226:2003, Tabela 1 (T_f, limiar de audição binaural em campo livre, 50 % de deteção)"


def threshold_iso226(f: float) -> float | None:
    """T_f [dB re 20 µPa] à frequência f; None fora de 20 Hz – 12,5 kHz."""
    if not (FREQ[0] <= f <= FREQ[-1]):
        return None
    lf = math.log10(f)
    for i in range(len(FREQ) - 1):
        a, b = FREQ[i], FREQ[i + 1]
        if a <= f <= b:
            la, lb = math.log10(a), math.log10(b)
            w = 0.0 if lb == la else (lf - la) / (lb - la)
            return TF[i] + w * (TF[i + 1] - TF[i])
    return TF[-1]  # pragma: no cover
