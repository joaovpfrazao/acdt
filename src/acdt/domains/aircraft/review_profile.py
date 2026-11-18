# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Perfil de revisão de projeto (``acdt report``) do domínio aircraft.

Disciplinas primárias: as que o pipeline aircraft escreve no estado de projeto e que dimensionam o avião
(docs/DADOS.md, ``SECTION_MAP``); o dimensionamento fica de fora porque é L0 por natureza (a viabilidade
entra pelo critério do conceito). PRESSUPOSTO: a escolha das primárias é do acdt (a NPR 7123.1D fala em
"primary subsystems" sem os enumerar); ajuste por projeto com ``primary_disciplines`` no ficheiro de critérios.
"""
from __future__ import annotations

from acdt.core.review.profile import ReviewProfile, register_profile

PROFILE = register_profile(ReviewProfile(
    domain="aircraft",
    primary_disciplines=("massas", "aerodinamica", "estabilidade", "estruturas", "desempenho"),
    headline=("weights.W0_kg", "weights.We_kg", "weights.Wfuel_or_battery_kg", "weights.battery_energy_Wh",
              "design_point.W_S_N_m2", "geometry.wing.S_m2", "geometry.wing.span_m", "geometry.wing.AR",
              "aero.CD0", "aero.LD_max", "aero.cruise_speed_m_s", "performance.endurance_h", "performance.range_km"),
    feasibility=("feasible",),
    notes=("disciplinas primárias: PRESSUPOSTO do acdt (domains/aircraft/review_profile.py)",),
))
