# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina gelo L0/L1, núcleo domínio-agnóstico (docs/GELO.md).

* :mod:`.envelopes` — 14 CFR 25 Ap. C (Jeck, DOT/FAA/AR-00/30);
* :mod:`.properties` — propriedades do ar/água/gelo (Anderson, NASA/CR-2004-212875, Ap. A);
* :mod:`.impingement` — captação na estagnação (Langmuir & Blodgett 1946);
* :mod:`.accretion` — balanço de Messinger (1953), fração de congelação, espessura;
* :mod:`.protection` — potência de anti-gelo/degelo térmico;
* :mod:`.penalty` — penalização aerodinâmica publicada (NASA/TP-2011-216929);
* :mod:`.study` — análise genérica ``acdt.icing/1``.
"""
