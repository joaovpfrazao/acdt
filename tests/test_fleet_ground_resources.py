# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Schema 1.2 shared ground resources: deterministic DES queue + fleet loop."""
import copy
import pathlib

import pytest
import yaml

from acdt.core.concept import ground_queue as GQ
from acdt.core.concept.fleet_feedback import fleet
from acdt.domains.aircraft.mission_fleet import evaluate_study, validate_study

EX = pathlib.Path(__file__).resolve().parents[1] / "examples" / "fleet"
P = "PRESSUPOSTO teste"
S = dict(GQ.SETTINGS)


def acts(charge, crew=0.1, res="charger"):
    return [dict(id="crew", resource=None, duration_h=crew), dict(id="charge", resource=res, duration_h=charge)]


@pytest.mark.parametrize("on,F,ch", [(1.0, 1.5, 2.2), (0.5, 0.7, 0.3), (0.25, 0.6, 1.0), (1.0, 2.0, 0.9)])
def test_dedicated_equals_homogeneous_fleet(on, F, ch):
    o = dict(availability=0.9, n_stations=1, handoff_overlap_h=0.)
    r = GQ.fleet_with_resources(on, 0., 1, [dict(id="A", flight_h=F, acts=acts(ch), stations=[0])], {"charger": 1000}, S, 0.9)
    f = fleet(on, F - on, ch + 0.1, o)
    assert r["status"] == "converged"
    assert r["aircraft_needed_in_cycle"] == f["aircraft_needed_in_cycle"] and r["fleet_expected"] == f["fleet_expected"]


def test_ddc_zero_wait_below_saturation_and_saturation():
    # D/D/c regular arrivals, rho<1 → zero wait (Kleinrock 1975); rho≥1 → saturated, minimum counts reported
    r = GQ.fleet_with_resources(1.0, 0., 1, [dict(id="A", flight_h=1.5, acts=acts(2.2), stations=[0])], {"charger": 3}, S)
    assert r["utilisation"]["charger"] == pytest.approx(2.2 / 3) and r["ground_time"]["wait_max_h"] == 0.0
    r = GQ.fleet_with_resources(1.0, 0., 1, [dict(id="A", flight_h=1.5, acts=acts(2.2), stations=[0])], {"charger": 2}, S)
    assert r["status"] == "resource_saturated" and r["minimum_stable_counts"]["charger"] == 3 and not r["assessed"]


def test_mixed_streams_queue_and_fleet_loop():
    # two types share ONE crew: irregular arrivals create waits; fleet grows only through missed launches
    types = [dict(id="A", flight_h=0.9, acts=[dict(id="c", resource="crew", duration_h=0.3)], stations=[0]),
             dict(id="B", flight_h=0.45, acts=[dict(id="c", resource="crew", duration_h=0.35)], stations=[1])]
    r = GQ.fleet_with_resources(1.0, 0., 2, types, {"crew": 1}, S)
    assert r["status"] == "converged" and r["ground_time"]["wait_max_h"] > 0
    h = r["history"]
    assert h[-1]["missed_launches"] == 0 and len(h) >= 2 and all(x["missed_launches"] > 0 for x in h[:-1])
    assert sum(h[-1]["fleet_by_type"].values()) > sum(h[0]["fleet_by_type"].values())
    # Little: busy time = arrivals * service over the simulated launches
    assert r["utilisation"]["crew"] == pytest.approx(0.3 + 0.35)
    assert r["ground_time"]["wait_max_h"] == pytest.approx(0.25) and r["fleet_in_cycle_by_type"] == {"A": 2, "B": 2}


def test_validation():
    with pytest.raises(ValueError, match="integers"): GQ.validate_pools({"source": P, "pools": {"c": 0}})
    with pytest.raises(ValueError, match="undeclared"):
        GQ.validate_process({"source": P, "activities": [dict(id="x", resource="truck", duration_h=1)]}, {"crew": 1})
    with pytest.raises(ValueError, match="ignored"):
        GQ.validate_process({"source": P, "activities": [dict(id="x", duration_h=1, flow_kg_h=3)]}, {})
    d = yaml.safe_load(open(EX / "shared_vtol.yaml"))
    bad = copy.deepcopy(d); bad["schema_version"] = "1.1"
    with pytest.raises(ValueError): validate_study(bad)
    bad = copy.deepcopy(d); bad["candidates"][0]["turnaround"] = {"method": "supplied", "duration_h": 1, "activity": "x", "source": P}
    with pytest.raises(ValueError, match="not both"): validate_study(bad)


def test_study_shared_vtol_example():
    d = yaml.safe_load(open(EX / "shared_vtol.yaml"))
    n = evaluate_study(d)["rows"][0]["n1"]
    byd = n["operations_by_dwell"]
    assert byd["requested"]["operations"]["status"] == "resource_saturated" and byd["requested"]["fleet_required"] is None
    dm = byd["derived_max"]
    assert dm["operations"]["status"] == "converged" and dm["fleet_required"] == 7 and n["status"] == "assessed_in_scope"
    assert dm["operations"]["minimum_stable_counts"]["charger"] == 3
    d["operations"]["ground_resources"]["pools"]["charger"] = 2
    n = evaluate_study(d)["rows"][0]["n1"]
    assert n["status"] == "infeasible" and "resource_saturated:charger" in n["issues"]


def test_unknown_energy_unassessed_not_zero():
    d = yaml.safe_load(open(EX / "shared_vtol.yaml"))
    d["candidates"][0]["ground_process"]["activities"].append(dict(id="refuel", resource=None, duration="refuel", flow_kg_h=50))
    n = evaluate_study(d)["rows"][0]["n1"]
    row = n["operations_by_dwell"]["derived_max"]
    assert row["assessed"] is False and any("refuel mass unassessed" in i for i in row["issues"])
    assert n["status"] == "unassessed"


def test_jet_shared_refuel():
    d = yaml.safe_load(open(EX / "iter_jet.yaml"))
    d["schema_version"] = "1.2"
    d["operations"]["ground_resources"] = {"source": P, "pools": {"fuel_truck": 1, "crew": 1}}
    c = d["candidates"][0]; c.pop("turnaround")
    c["ground_process"] = {"source": P, "activities": [dict(id="deplane", resource="crew", duration_h=0.2),
                                                       dict(id="refuel", resource="fuel_truck", duration="refuel", flow_kg_h=20000)]}
    n = evaluate_study(d)["rows"][0]["n1"]
    row = n["operations_by_dwell"]["requested"]
    fuel = row["mission_fuel_kg"]
    assert row["ground_activities"][1]["duration_h"] == pytest.approx(fuel / 20000)
    assert row["operations"]["status"] == "converged" and row["fleet_required"] >= 1


def test_v11_examples_unchanged():
    n = evaluate_study(yaml.safe_load(open(EX / "iter_vtol.yaml")))["rows"][0]["n1"]
    assert n["operations_by_dwell"]["requested"]["fleet_required"] == 46
    assert n["operations_by_dwell"]["derived_max"]["fleet_required"] == 15
