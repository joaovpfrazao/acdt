# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Gestão térmica L0/L1 (docs/TERMICA.md): propriedades do ar, atmosferas extremas, correlações clássicas de
convecção e radiação, rede térmica de compartimentos (regime permanente e transitório de capacidade concentrada),
arrefecimento por pele, ar dinâmico (entrada NACA submersa / conduta) e ventilador, com arrasto, massa e potência de
arrefecimento.

Fontes principais: Incropera, DeWitt, Bergman & Lavine, *Fundamentals of Heat and Mass Transfer*, 6.ª ed. (Wiley,
2007); MIL-HDBK-310 (1997); U.S. Standard Atmosphere 1976; NACA RM A8I29 (Hall & Frank, 1948).

Padrão de completude (o mesmo da disciplina ruído): cada fonte de calor é um **intervalo** [mín, máx]; uma fonte
desconhecida tem máximo ``None``. As temperaturas são intervalos; um limite máximo só passa com o máximo conhecido
e abaixo do limite, só falha com o mínimo acima do limite; o resto fica desconhecido (nunca passa por omissão).
"""
from __future__ import annotations

from .air import AIR_REF, Ambient, air_props, ambient
from .convection import INCROPERA
from .network import Bay, BaySolution, corners, solve_bay_bounds, solve_bay_steady, solve_bay_transient

__all__ = ["AIR_REF", "Ambient", "air_props", "ambient", "INCROPERA", "Bay", "BaySolution", "corners",
           "solve_bay_bounds", "solve_bay_steady", "solve_bay_transient"]
