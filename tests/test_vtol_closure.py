# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in VTOL component mass closure (vtol.closure) + onboard + fleet 1.1 coupling."""
import copy
import math
import pathlib

import pytest
import yaml

from acdt.domains.aircraft.vtol import size_vtol
from acdt.domains.aircraft.vtol.closure import close_vtol, FT, LB, FTLB
from acdt.domains.aircraft.onboard import size_onboard
from acdt.domains.aircraft.mission_fleet import evaluate_study

P = "PRESSUPOSTO teste"
EX = pathlib.Path(__file__).resolve().parents[1] / "examples" / "fleet"


def spec(arch="multirotor", **over):
    comps = {"rotors": {"method": "AFDD00", "n_blades": 2, "flap_frequency_per_rev": 1.1, "source": P},
             "motors": {"method": "NASA15", "torque_class": "other", "source": P},
             "controllers": {"method": "fraction_of_motor", "fraction": 0.3, "source": P},
             "rotor_support": {"method": "fraction_of_mtow", "fraction": 0.05, "source": P},
             "airframe": {"method": "fraction_of_mtow", "fraction": 0.25, "source": P},
             "other": [{"id": "avionics", "mass_kg": 0.5, "source": P}]}
    comps.update(over.pop("components", {}))
    s = {"architecture": arch, "mission": {"t_hover_s": 120, "cruise_distance_m": 5000, "cruise_speed_m_s": 15},
         "closure": {"mass_bounds_kg": [3, 200], "fixed_items": [{"id": "payload", "mass_kg": 2, "source": P}],
                     "components": comps}}
    s["closure"].update(over)
    return s


def test_converges_and_mass_sums():
    r = size_vtol(spec())
    c = r["closure"]
    assert c["status"] == "converged" and r["converged"] and r["feasible"]
    b = c["breakdown"]
    total = b["fixed_items_kg"] + b["other_kg"] + sum(v["mass_kg"] for k, v in b.items() if isinstance(v, dict))
    assert abs(total - r["mtow_kg"]) <= c["solver"]["history"][-1]["tolerance_kg"]
    assert r["mass_kg"] == r["mtow_kg"] and abs(c["solver"]["residual_kg"]) <= 1e-4
    assert b["battery"]["mass_kg"] == r["battery_mass_kg"]
    assert len(c["solver"]["history"]) == c["solver"]["evaluations"] >= 3
    assert b["rotors"]["extrapolation"] is True and b["motors"]["extrapolation"] is True


def test_afdd00_and_nasa15_hand_check():
    r = size_vtol(spec())
    b = r["closure"]["breakdown"]; hp = r["hover"]
    R = hp["diameter_m"] / 2 / FT; c = 0.10 * math.pi * R / 2; V = hp["tip_speed_max_m_s"] / FT; n = 4
    wb = 0.0024419 * n * 2 ** 0.53479 * R ** 1.74231 * c ** 0.77291 * V ** 0.87562 * 1.1 ** 2.51048
    wh = 0.0061182 * n * 2 ** 0.20373 * R ** 0.60406 * V ** 0.52803 * 1.1 ** 1.00218 * (wb / n) ** 0.87127
    assert b["rotors"]["mass_kg"] == pytest.approx((wb + wh) * LB, rel=1e-12)
    Q = r["peak"]["P_per_rotor_W"] / (hp["tip_speed_max_m_s"] / (hp["diameter_m"] / 2)) / FTLB
    assert b["motors"]["mass_kg"] == pytest.approx(n * 0.5382 * 2.5606 * Q ** 0.8129 * LB, rel=1e-12)
    assert b["controllers"]["mass_kg"] == pytest.approx(0.3 * b["motors"]["mass_kg"])
    assert b["rotor_support"]["mass_kg"] == pytest.approx(0.05 * r["mtow_kg"])
    assert FTLB == pytest.approx(1.3558179483, rel=1e-9)


def test_tilt_factor_and_required_mechanism():
    s = spec("tilt_rotor")
    r = size_vtol(s)
    assert r["closure"]["status"] == "incomplete_component_coverage" and "tilt_mechanism" in r["closure"]["missing_components"]
    assert r["mtow_kg"] is None and r["feasible"] is False
    s["closure"]["components"]["tilt_mechanism"] = {"method": "fraction_of_mtow", "fraction": 0.03, "source": P}
    r = size_vtol(s)  # default tilt-rotor disk loading 350 N/m²: power-limited pack, honestly no root in bounds
    assert r["closure"]["status"] == "not_bracketed" and r["mtow_kg"] is None
    s["rotors"] = {"disk_loading_N_m2": 150.0}; s["closure"]["components"]["airframe"]["fraction"] = 0.15
    r = size_vtol(s)
    assert r["converged"] and r["closure"]["breakdown"]["rotors"]["f_tilt"] == 1.17940


def test_lift_cruise_requires_cruise_propulsor():
    r = size_vtol(spec("lift_cruise"))
    assert r["closure"]["missing_components"] == ["cruise_propulsor"]
    r = size_vtol(spec("lift_cruise", components={"cruise_propulsor": {"method": "supplied", "mass_kg": 0.4, "source": P}}))
    assert r["converged"] and r["closure"]["breakdown"]["rotors"]["f_tilt"] == 1.0


def test_missing_component_is_not_zero():
    s = spec(); del s["closure"]["components"]["airframe"]
    r = size_vtol(s)
    assert r["closure"]["status"] == "incomplete_component_coverage" and r["closure"]["breakdown"] is None
    assert r["converged"] is False and r["issues"] == ["incomplete_component_coverage"]


def test_not_bracketed_and_max_iterations():
    r = size_vtol(spec(mass_bounds_kg=[3, 4]))
    assert r["closure"]["status"] == "not_bracketed" and r["mtow_kg"] is None
    r = size_vtol(spec(solver={"max_iterations": 2}))
    assert r["closure"]["status"] == "max_iterations" and r["closure"]["solver"]["iterations"] == 2


def test_validation_errors():
    s = spec(); s["mass_kg"] = 10
    with pytest.raises(ValueError, match="do not also supply mass_kg"): close_vtol(s)
    s = spec(); s["closure"]["components"]["airframe"].pop("source")
    with pytest.raises(ValueError, match="source required"): size_vtol(s)
    s = spec(); s["closure"]["components"]["motors"].pop("torque_class")
    with pytest.raises(ValueError, match="torque_class"): size_vtol(s)
    s = spec(); s["closure"]["components"]["rotors"]["method"] = "AFDD82"
    with pytest.raises(ValueError, match="method"): size_vtol(s)
    with pytest.raises(ValueError, match="strictly increasing"): size_vtol(spec(mass_bounds_kg=[10, 5]))


def test_motor_class_inconsistency_flagged():
    r = size_vtol(spec(components={"motors": {"method": "NASA15", "torque_class": "high_torque", "source": P}}))
    chk = {c["name"]: c["passed"] for c in r["closure"]["checks"]}
    assert r["converged"] and chk["motor_torque_class_consistent"] is False and r["feasible"] is False
    assert "motor_torque_class_consistent" in r["issues"]


def test_payload_increases_mtow_and_backward_compat():
    a = size_vtol(spec())["mtow_kg"]
    s = spec(); s["closure"]["fixed_items"][0]["mass_kg"] = 3
    assert size_vtol(s)["mtow_kg"] > a + 1.0
    fixed = size_vtol({"architecture": "multirotor", "mass_kg": 10.0})
    assert "closure" not in fixed and "converged" not in fixed and fixed["mass_kg"] == 10.0


def _onboard(closure=True):
    d = yaml.safe_load(open(EX / "iter_vtol_closure.yaml"))
    rec = copy.deepcopy(d["candidates"][0]["recipe"])
    return rec


def test_onboard_closure_and_guards():
    rec = _onboard()
    o = size_onboard(rec)
    chk = {c["name"]: c["passed"] for c in o["checks"]}
    assert chk["VTOL_mass_closure"] is True and o["mass_coupled"] and o["status"] == "evaluated"
    fi = o["resolved_aircraft"]["closure"]["fixed_items"]
    assert [i["id"] for i in fi] == ["instrument"]
    assert o["aircraft_result"]["mtow_kg"] > 1
    bad = copy.deepcopy(rec); bad["mass_ledger"] = {"remaining_nonbattery_mass_kg": 1, "source": P}
    with pytest.raises(ValueError, match="mass_ledger"): size_onboard(bad)
    bad = copy.deepcopy(rec); bad["aircraft"]["mass_kg"] = 10
    with pytest.raises(ValueError, match="mass_kg"): size_onboard(bad)
    bad = copy.deepcopy(rec); bad["aircraft"]["closure"]["fixed_items"] = [{"id": "x", "mass_kg": 1, "source": P}]
    with pytest.raises(ValueError, match="fixed items"): size_onboard(bad)


def test_onboard_nonconverged_is_unassessed():
    rec = _onboard(); rec["aircraft"]["closure"]["mass_bounds_kg"] = [3, 3.5]
    o = size_onboard(rec)
    assert o["status"] == "not_converged" and {c["name"]: c["passed"] for c in o["checks"]}["VTOL_mass_closure"] is False


def test_fleet_v11_closure_iterates():
    d = yaml.safe_load(open(EX / "iter_vtol_closure.yaml"))
    n = evaluate_study(d)["rows"][0]["n1"]
    assert n["closure"]["status"] == "converged" and n["closure"]["status"] != "not_applicable_fixed_supplied_mtow"
    assert n["vtol_mass_closure"]["status"] == "converged" and n["status"] == "assessed_in_scope"
    assert n["endurance"]["derived_max_on_station_h"] >= d["mission"]["samples"][0]["on_station_h"]
    byd = n["operations_by_dwell"]
    m0 = n["vtol_mass_closure"]["mtow_kg"]
    assert byd["requested"]["fleet_mtow_kg"] == pytest.approx(byd["requested"]["fleet_required"] * m0)


def test_fleet_v11_energy_limited_derived_equals_design():
    d = yaml.safe_load(open(EX / "iter_vtol_closure.yaml"))
    d["candidates"][0]["recipe"]["aircraft"]["electric"]["c_rate_max"] = 60.0
    n = evaluate_study(d)["rows"][0]["n1"]
    assert n["closure"]["status"] == "converged"
    T = d["mission"]["samples"][0]["on_station_h"]
    tol = n["endurance"].get("tolerance_h", 0.01)
    assert T - tol <= n["endurance"]["derived_max_on_station_h"] <= T + tol  # design = capability, conservative bisection
    assert {c["name"]: c["passed"] for c in n["checks"]}["derived_max_covers_requested_station"] is True


def test_fleet_v10_closure_runs_and_fixed_vtol_unchanged():
    d = yaml.safe_load(open(EX / "iter_vtol_closure.yaml"))
    d["schema_version"] = "1.0"; d["operations"].pop("operational_reserve"); d["operations"].pop("dwell_policy")
    d["objectives"].pop("derived_max_on_station_h")
    n = evaluate_study(d)["rows"][0]["n1"]
    assert n["status"] == "assessed_in_scope" and n["metrics"]["fleet_required"] >= 1
    old = evaluate_study(yaml.safe_load(open(EX / "iter_vtol.yaml")))["rows"][0]["n1"]
    assert old["closure"]["status"] == "not_applicable_fixed_supplied_mtow"
    assert old["operations_by_dwell"]["requested"]["fleet_required"] == 46
    assert old["operations_by_dwell"]["derived_max"]["fleet_required"] == 15
