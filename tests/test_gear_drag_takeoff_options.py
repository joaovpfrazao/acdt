# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Gear drag area in the polar (aero/gear_drag.py) and take-off ground-roll options (flightsim/takeoff_options.py),
16 nov 2026 (ramo l1-trem-ventocruzado)."""
from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest
import yaml

from acdt.domains.aircraft.aero import gear_drag as GD

EX = Path(__file__).resolve().parents[1] / "examples"


def _A(**gd):
    return {"aero": {"extra_drag_areas_m2": {"fixed_gear": 0.03, "antennas": 0.004}, "dCD0_takeoff": 0.01,
                     **({"gear_drag": gd} if gd else {})},
            "weights": {"components": {"main_gear_length_m": 0.47, "nose_gear_length_m": 0.78}}}


def test_absent_option_changes_nothing():
    A = _A()
    assert not GD.requested(A) and GD.prepare(A) is None
    assert A["aero"]["extra_drag_areas_m2"] == {"fixed_gear": 0.03, "antennas": 0.004}
    assert GD.dcd0_takeoff(A["aero"], 3.0) == pytest.approx(0.01)       # fixed gear: already in the polar


def test_scaled_fixed_gear_goes_into_the_polar_once():
    A = _A(scale_with_legs=True, ref_main_m=0.35, ref_nose_m=0.30)
    rep = GD.prepare(A)
    f = (2 * 0.47 + 0.78) / (2 * 0.35 + 0.30)                        # ΣL / ΣL_ref (two mains + nose)
    assert rep["status"] == "assessed" and rep["scaled"]["factor"] == pytest.approx(f)
    ex = A["aero"]["extra_drag_areas_m2"]
    assert ex["fixed_gear"] == 0.03                                   # given key untouched (follow-up scales it)
    assert ex["fixed_gear_length_increment"] == pytest.approx(0.03 * (f - 1))
    assert sum(ex.values()) == pytest.approx(0.03 * f + 0.004)
    assert GD.prepare(A) is rep and sum(A["aero"]["extra_drag_areas_m2"].values()) == pytest.approx(0.03 * f + 0.004)
    s = GD.summary(rep, 3.0, 0.03)
    assert s["dCD0_increment"] == pytest.approx(0.03 * (f - 1) / 3.0)
    assert GD.row(s)[1] is True and "Raymer 2018 Eq. 12.24" in GD.row(s)[2]


def test_missing_strut_length_is_unassessed_not_factor_one():
    A = _A(scale_with_legs=True)
    A["weights"] = {}
    rep = GD.prepare(A)
    assert rep["status"] == "unassessed" and "fixed_gear_length_increment" not in A["aero"]["extra_drag_areas_m2"]
    assert GD.row(rep)[1] is None


def test_retractable_gear_only_gear_down():
    A = _A(retractable=True)
    rep = GD.prepare(A)
    assert "fixed_gear" not in A["aero"]["extra_drag_areas_m2"] and rep["gear_down_m2"] == pytest.approx(0.03)
    assert GD.dcd0_takeoff(A["aero"], 2.0) == pytest.approx(0.01 + 0.03 / 2.0)
    assert GD.dcd0_takeoff(A["aero"], None) == pytest.approx(0.01)


def test_gear_opts_found_in_flying_wing_block():
    A = _A()
    A["assembly"] = {"options": {"flying_wing": {"gear": {"apply_scaled_drag": True, "drag_ref_main_m": 0.35,
                                                          "drag_ref_nose_m": 0.30}}}}
    assert GD.requested(A) and GD.prepare(A)["increment_m2"] == pytest.approx(0.03 * 0.72)


@pytest.mark.slow
def test_sizing_applies_gear_drag_and_perf_sees_it():
    """Fast fixed-type example: scaled area raises CD0 by Σ(D/q)/S; retractable gear leaves cruise and enters the
    take-off ΔC_D0 of PerfModel (Raymer 2018 Sec. 17.8)."""
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.performance import PerfModel
    from acdt.domains.aircraft.sizing import run
    f = EX / "uav_gasoline_150kg.yaml"
    d = yaml.safe_load(f.read_text(encoding="utf-8"))
    d2 = copy.deepcopy(d)
    d2["assumptions"]["aero"]["gear_drag"] = {"scale_with_legs": True, "ref_main_m": 0.30, "ref_nose_m": 0.25}
    r2 = run(MissionSpec.from_dict(d2, f))
    g = r2.gear_drag
    assert g["status"] == "assessed" and g["increment_m2"] > 0
    ck = {c.key: c for c in r2.checks}
    assert ck["aero:gear_drag"].ok is True
    assert g["dCD0_increment"] == pytest.approx(g["increment_m2"] / r2.S)
    d3 = copy.deepcopy(d)
    d3["assumptions"]["aero"]["gear_drag"] = {"retractable": True}
    r3 = run(MissionSpec.from_dict(d3, f))
    m3 = PerfModel.from_result(r3)
    assert m3.dCD0_to == pytest.approx(d["assumptions"]["aero"].get("dCD0_takeoff", 0.01) + 0.03 / r3.S)
    r1 = run(MissionSpec.from_dict(copy.deepcopy(d), f))
    assert r1.gear_drag is None and r3.polar.CD0 < r1.polar.CD0 < r2.polar.CD0


# ------------------------------------------------------------------------------------------- take-off options

def test_wind_components():
    from acdt.domains.aircraft.flightsim.takeoff_options import wind_components
    hw, cw = wind_components({"speed_m_s": 5.2, "from_deg": 270}, 0.0)
    assert hw == pytest.approx(0.0, abs=1e-9) and cw == pytest.approx(5.2)
    hw, cw = wind_components({"speed_m_s": 5.0, "from_deg": 30}, 0.0)
    assert hw == pytest.approx(5 * math.cos(math.radians(30))) and cw == pytest.approx(2.5)


@pytest.fixture(scope="module")
def fm172(c172_result):
    from acdt.domains.aircraft.flightsim.aeromodel import build_flight_model
    return build_flight_model(c172_result)


@pytest.mark.requires_avl
def test_ground_roll_trends(fm172):
    from acdt.domains.aircraft.flightsim.takeoff_options import ground_roll
    b = ground_roll(fm172, fly_off=False)
    assert 0 < b["ground_roll_m"] < 1e4 and b["VLOF_over_VS"] == pytest.approx(1.1)
    assert ground_roll(fm172, fly_off=False, headwind=4.0)["ground_roll_m"] < b["ground_roll_m"]
    assert ground_roll(fm172, fly_off=False, thrust_factor=1.2)["ground_roll_m"] < b["ground_roll_m"]
    assert ground_roll(fm172, fly_off=False, S_factor=1.2)["ground_roll_m"] < b["ground_roll_m"]
    assert ground_roll(fm172, fly_off=False, mass_factor=0.9)["ground_roll_m"] < b["ground_roll_m"]


@pytest.mark.slow
@pytest.mark.requires_avl
def test_options_table_closes_with_the_numbers_it_reports(fm172):
    from acdt.domains.aircraft.flightsim import takeoff_options as T
    base = T.ground_roll(fm172, fly_off=False)["ground_roll_m"]
    seg = {"ground_roll_m": 1.1 * base}                    # a 6-DOF roll 10 % above the point mass
    req = base                                              # requirement = point-mass still-air roll
    rep = T.assess(fm172, seg, req, wind={"speed_m_s": 6.0, "from_deg": 90.0}, heading_deg=0.0)
    assert rep["status"] == "assessed" and rep["k_6dof_over_point_mass"] == pytest.approx(1.1)
    O = rep["options"]
    for key in ("b_tracao", "c_carga_alar", "d_massa"):
        assert O[key]["closes"] is True and O[key]["ground_roll_est_m"] <= req * (1 + 1e-3)
    a = O["a_vento_de_frente"]
    assert a["closes"] is True and a["headwind_required_m_s"] < 6.0
    assert math.cos(math.radians(a["wind_to_runway_angle_max_deg"])) * 6.0 == pytest.approx(a["headwind_required_m_s"])
    assert O["f_catapulta"]["closes"] is None                       # not configured → unassessed, never a pass
    assert O["g_vento_cruzado_menor"]["closes"] is False and O["g_vento_cruzado_menor"]["admissible"] is False
    assert O["e_atitude"]["closes"] is None                         # rotation mode
    assert set(rep["closing"]) == {"a_vento_de_frente", "b_tracao", "c_carga_alar", "d_massa"}
    assert T.row(rep)[1] is True
    md = T.to_markdown(rep)
    assert "| b. tração |" in md and "14 CFR 23.233(a)" in md
    cat = T.assess(fm172, seg, req, catapult={"speed_ok": True, "stroke_m": 5.2, "n_x_g": 8.0})
    assert cat["options"]["f_catapulta"]["closes"] is True
