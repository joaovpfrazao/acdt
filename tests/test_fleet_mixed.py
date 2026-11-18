# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Schema 1.2 mixed fleets: bounded station-assignment enumeration, shared pools, Pareto only."""
import copy
import pathlib

import pytest
import yaml

from acdt.domains.aircraft.mission_fleet import evaluate_study, validate_study
from acdt.domains.aircraft.mission_fleet_mixed import _compositions

EX = pathlib.Path(__file__).resolve().parents[1] / "examples" / "fleet"


@pytest.fixture(scope="module")
def spec():
    return yaml.safe_load(open(EX / "mixed_vtol_fixed_wing.yaml"))


@pytest.fixture(scope="module")
def result(spec):
    return evaluate_study(copy.deepcopy(spec))


def test_compositions_bounded():
    assert sorted(_compositions(3, 2)) == [[1, 2], [2, 1]]
    assert list(_compositions(4, 1)) == [[4]] and len(list(_compositions(5, 3))) == 6


def test_enumeration_and_constraint(result):
    s = result["mixed_fleet"]["samples"][0]
    ids = {x["id"]: x for x in s["mixes"]}
    assert s["n_mixes"] == 4 and ids["elétrico×3"]["status"] == "violates_min_stations_by_type"
    assert ids["elétrico×3"]["assessed"] is False and "elétrico×3" not in s["pareto"]
    mixed = ids["elétrico×2+VTOL-fecho-massa×1"]
    assert mixed["assessed"] and mixed["metrics"]["n_types"] == 2
    # Raymer Table 3.1 'uav_small' empty fraction for the electric type: a three-way trade (fleet size, MTOW,
    # energy rate), no automatic winner; the mixed fleet stays on the front.
    assert set(s["pareto"]) == {"VTOL-fecho-massa×3", "elétrico×1+VTOL-fecho-massa×2", "elétrico×2+VTOL-fecho-massa×1"}
    assert "weights" not in s["comparison"] or not s["comparison"].get("weights")


def test_metrics_consistent_with_types(result):
    s = result["mixed_fleet"]["samples"][0]
    rows = {r["candidate_id"]: r["n1"] for r in result["rows"]}
    m = {x["id"]: x for x in s["mixes"]}["elétrico×2+VTOL-fecho-massa×1"]
    fb = m["fleet_by_type"]
    assert m["metrics"]["fleet_required"] == sum(fb.values())
    assert m["metrics"]["fleet_mtow_kg"] == pytest.approx(sum(fb[c] * rows[c]["mtow_kg"] for c in fb))
    e = 0.
    for c, k in (("elétrico", 2), ("VTOL-fecho-massa", 1)):
        row = rows[c]["operations_by_dwell"]["requested"]
        e += k * row["mission_energy_Wh"] / row["on_station_h"]
    assert m["metrics"]["energy_rate_Wh_per_h"] == pytest.approx(e)
    assert m["metrics"]["fuel_rate_kg_per_h"] == 0.0
    q = m["shared_ground"]
    assert q["status"] == "converged" and set(q["fleet_in_cycle_by_type"]) == {"elétrico", "VTOL-fecho-massa"}


def test_shared_pool_saturates_mix(spec):
    d = copy.deepcopy(spec); d["operations"]["ground_resources"]["pools"]["charger"] = 1
    s = evaluate_study(d)["mixed_fleet"]["samples"][0]
    # each homogeneous member already saturates the single charger → excluded, never assessed as a mix
    assert {x["id"] for x in s["excluded_members"]} == {"elétrico", "VTOL-fecho-massa"}
    assert s["mixes"] == [] and s["pareto"] == []


def test_independent_ground_matches_homogeneous(spec):
    d = copy.deepcopy(spec); d["mixed_fleet"]["shared_ground"] = False; d["mixed_fleet"]["min_stations_by_type"] = {}
    r = evaluate_study(d)
    s = r["mixed_fleet"]["samples"][0]
    ids = {x["id"]: x for x in s["mixes"]}
    homo = {x["candidate_id"]: x["n1"]["metrics"]["fleet_required"] for x in r["rows"]}
    assert ids["elétrico×3"]["metrics"]["fleet_required"] == homo["elétrico"]
    assert ids["VTOL-fecho-massa×3"]["metrics"]["fleet_required"] == homo["VTOL-fecho-massa"]


def test_unassessed_member_excluded_not_zero(spec):
    d = copy.deepcopy(spec)
    d["candidates"][1]["recipe"]["aircraft"]["closure"]["mass_bounds_kg"] = [3, 4]
    s = evaluate_study(d)["mixed_fleet"]["samples"][0]
    assert [x["id"] for x in s["excluded_members"]] == ["VTOL-fecho-massa"]
    assert s["pareto"] == []  # the required VTOL station cannot be covered


def test_validation(spec):
    for mut, msg in ((lambda d: d.update(schema_version="1.1"), "."),
                     (lambda d: d["mixed_fleet"].update(members=["elétrico"]), "members"),
                     (lambda d: d["mixed_fleet"].update(objectives={"winner": "max"}), "objectives"),
                     (lambda d: d["mixed_fleet"].update(min_stations_by_type={"VTOL-fecho-massa": 9}), "min_stations"),
                     (lambda d: d["mixed_fleet"].update(max_types=3), "max_types")):
        d = copy.deepcopy(spec); mut(d)
        with pytest.raises(ValueError, match=msg): validate_study(d)
