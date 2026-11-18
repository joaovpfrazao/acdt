# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Custo do ciclo de vida e pegada ambiental L0 (docs/CICLO_VIDA.md), domínio-agnóstico.

* :mod:`.discount` — fatores de atualização SPV/UPV/UPV* e taxas real/nominal (NIST Handbook 135, 1995);
* :mod:`.lcc` — LCC = RDT&E + investimento (produção) + O&S + abate, em dólares constantes e valor presente
  (categorias: OSD CAPE O&S Cost-Estimating Guide 2020 §2.1; atualização: NIST HB 135 Eq. 5.1);
* :mod:`.environment` — CO₂/CO₂e da energia (combustível: ICAO Anexo 16 Vol. IV; rede: intensidade declarada) e
  fabrico de baterias (IVL C444, opcional).
"""
