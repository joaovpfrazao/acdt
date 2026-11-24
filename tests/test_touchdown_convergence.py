# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Veredicto de carga lateral no toque (14 CFR 23.485) convergido no passo do 6-DOF (24 nov 2026).

Modelos de voo gravados (``FlightModel.save``) da asa voadora sem deriva, caso 'cheio': exemplo tal como está e
opção (a) da rajada (examples/studies/rajada_cheio). Aterragem curta com vento cruzado de 5,2 m/s a 90°, a partir
de 120 m. Com sub-passos no contacto e a mudança de lei no instante do toque, a razão máxima de carga lateral e o
veredicto não dependem do passo da missão (10 / 20 / 25 ms) nem do sub-passo (5 / 2,5 / 1,25 ms)."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"
MISSION = {"name": "toque", "wind": {"speed_m_s": 5.2, "from_deg": 270},
           "initial": {"altitude_m": 120.0, "speed_m_s": 28.0},
           "segments": [{"type": "descent", "to_altitude_m": 60},
                        {"type": "landing", "flap": 0, "glide_deg": 2, "heading_deg": 0, "decrab_height_m": 30}]}


def _touchdown(fm_name: str, **kw) -> dict:
    from acdt.domains.aircraft.flightsim.aeromodel import FlightModel
    from acdt.domains.aircraft.flightsim.mission import MissionRunner
    fm = FlightModel.load(DATA / f"{fm_name}_flight_model.json")
    ms = copy.deepcopy(MISSION)
    ms.update(kw)
    r = MissionRunner(fm, ms, None).run()
    assert not r.get("aborted")
    td = r["segments"][-1]["touchdown"]
    return td


@pytest.mark.parametrize("fm_name", ["toque_tailless_base", "toque_tailless_opcao_a"])
def test_side_load_verdict_converged_in_mission_step(fm_name):
    tds = [_touchdown(fm_name, dt=dt) for dt in (0.01, 0.02, 0.025)]
    r = [td["side_load_max_ratio"] for td in tds]
    assert len({td["side_load_status"] for td in tds}) == 1, r
    mean = sum(r) / len(r)
    assert max(abs(x - mean) for x in r) <= 0.10 * mean, r     # medido: base ±6 %, opção (a) ±2 %


def test_side_load_converged_in_substep():
    r = [_touchdown("toque_tailless_opcao_a", dt=0.02, touchdown_substep_s=h)["side_load_max_ratio"]
         for h in (0.005, 0.0025, 0.00125)]
    assert max(r) - min(r) <= 0.05 * max(r), r


def test_default_substep_declared():
    from acdt.domains.aircraft.flightsim import mission as M
    assert M.TOUCHDOWN_SUBSTEP_S == 0.0025


def test_design_side_load_factor_scales_the_limit():
    """gear.side_load_factor k (opt-in): o toque compara com k × 23.485; a razão a 23.485 continua reportada."""
    from acdt.domains.aircraft.flightsim.aeromodel import FlightModel
    from acdt.domains.aircraft.flightsim.mission import MissionRunner
    fm = FlightModel.load(DATA / "toque_tailless_opcao_a_flight_model.json")
    fm.mass.gear["side_load_factor"] = 1.3
    ms = copy.deepcopy(MISSION)
    ms["dt"] = 0.02
    td = MissionRunner(fm, ms, None).run()["segments"][-1]["touchdown"]
    assert td["design_side_load_factor"] == 1.3
    assert td["inboard_ratio"] == pytest.approx(td["inboard_ratio_23_485"] / 1.3)
    assert td["limit_design_N"]["inboard_N"] == pytest.approx(1.3 * td["limit_23_485"]["inboard_N"])


def test_leg_structure_side_factor_monotone():
    from acdt.domains.aircraft.assembly.gear_devices import size_gear_side_load_structure
    lay = {"nose_fraction": [0.08, 0.15]}
    lo = {"main_gear_length_m": 0.47, "nose_gear_length_m": 0.78}
    m = [size_gear_side_load_structure(lay, 1550.0, length_opts=lo, side_factor=k) for k in (1.0, 1.3, 2.0)]
    assert all(x["status"] == "assessed" for x in m)
    assert m[0]["side_factor"] == 1.0 and m[0]["F_side_N"] == pytest.approx(0.5 * 1550.0)
    assert m[1]["F_side_N"] == pytest.approx(1.3 * 0.5 * 1550.0)
    assert m[0]["mass_two_mains_kg"] <= m[1]["mass_two_mains_kg"] <= m[2]["mass_two_mains_kg"]
