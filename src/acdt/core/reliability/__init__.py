# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Fiabilidade e manutenção de frota (L0; docs/FIABILIDADE.md).

* :mod:`.rates` — taxas de avaria por componente com proveniência (fornecedor com fonte e data, base pública
  ``core/data/failure_rates.yaml`` ou valor declarado com fonte); sem fonte → desconhecido;
* :mod:`.rbd` — diagramas de blocos de fiabilidade (série, paralelo ativo, k-de-n, caminhos mínimos), R(t),
  MTBF básica e MTBCF (MIL-HDBK-338B §6.4, §7.5);
* :mod:`.maintenance` — M_ct, MTBM, M̄, MMH/FH, disponibilidades intrínseca, atingida e operacional
  (MIL-HDBK-338B Eq. 5.75, 10.18–10.24);
* :mod:`.spares` — provisão de sobressalentes por Poisson (MIL-HDBK-338B Eq. 5.58);
* :mod:`.fleet` — dimensão da frota por cobertura (reutiliza :func:`acdt.core.concept.fleet_feedback.fleet`) ou por
  taxa de surtidas;
* :mod:`.study` — análise genérica ``acdt.reliability/1`` com intervalos ``{lo, hi}``.
"""
from __future__ import annotations

SCHEMA = "acdt.reliability/1"
REF_338B = "MIL-HDBK-338B (1 out. 1998), Electronic Reliability Design Handbook"
