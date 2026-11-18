"""Concept-trade primitives (AI-driven architecture studies): hand calculations, determinism, Pareto, fleet."""
import math

import pytest

from acdt.ai import concept as C
from acdt.ai import toolkit as T
from acdt.core.concept import geo, ops, reliability as rel, search, tradeoff


def test_transit_and_sweep_hand_calc():
    t = ops.transit(90.0, 25.0, 5.0)                     # 90 km at 20 / 30 m/s ground speed
    assert t["t_out_h"] == pytest.approx(90e3 / 20 / 3600)
    assert t["t_back_h"] == pytest.approx(90e3 / 30 / 3600)
    s = ops.sweep(10000.0, 20.0, 50.0, 2)                # Q = 2·20 km·180 km/h = 7200 km²/h
    assert s["sweep_rate_km2_h"] == pytest.approx(7200.0)
    assert s["time_to_sweep_area_h"] == pytest.approx(10000 / 7200)


def test_koopman_pod_and_effort():
    p = search.pod(1000.0, 10.0, 100.0)                  # coverage 1 → 1 − e⁻¹ ; sweep 1
    assert p["pod_random_search"] == pytest.approx(1 - math.exp(-1))
    assert p["pod_parallel_sweep"] == pytest.approx(1.0)
    e = search.effort_for_pod(1000.0, 0.9)
    assert e["effort_random_km2"] == pytest.approx(-1000 * math.log(0.1))
    r = C.sweep_coverage(area_km2=1000, sweep_width_km=10, speed_m_s=100 / 3.6, time_h=1.0, pod_target=0.9)
    assert r["pod_at_time"]["pod_random_search"] == pytest.approx(1 - math.exp(-1))
    assert r["for_pod_target"]["time_random_h"] == pytest.approx(math.log(10))


def test_continuous_coverage_hand_calc():
    # endurance 10 h, 1 h out + 1 h back, 4 h on ground, 0.5 h reserve → T_L = 7.5 h, T_rt = 6 h
    c = ops.cycle(10, 1, 1, 4, 0.5)
    assert c["time_on_station_h"] == pytest.approx(7.5) and c["round_trip_h"] == pytest.approx(6)
    assert c["aircraft_per_station"] == math.ceil(1 + 6 / 7.5) == 2
    assert c["duty_cycle"] == pytest.approx(7.5 / 13.5)
    pc = C.persistent_coverage(endurance_h=10, turnaround_h=4, t_out_h=1, t_back_h=1, reserve_h=0.5)
    assert pc["sorties_per_day"] == pytest.approx(24 / 7.5) and pc["flight_hours_per_day"] == pytest.approx(3.2 * 9.5)
    assert ops.cycle(2, 1, 1, 1)["feasible"] is False
    r = C.persistent_coverage(endurance_h=10, turnaround_h=4, t_out_h=1, t_back_h=1, reserve_h=0.5, n_stations=2,
                              availability={"mtbf_h": 90, "mttr_h": 10}, confidence=0.9, fleet_size=6)
    assert r["availability"] == pytest.approx(0.9) and r["aircraft_needed_in_cycle"] == 4
    assert r["fleet_expected"] == math.ceil(4 / 0.9) == 5
    assert r["fleet"]["p_enough_available"] == pytest.approx(rel.k_of_n(6, 4, 0.9))
    n = r["fleet_for_confidence"]["n"]
    assert rel.k_of_n(n, 4, 0.9) >= 0.9 > rel.k_of_n(n - 1, 4, 0.9)


def test_binomial_k_of_n():
    assert rel.k_of_n(3, 2, 0.9) == pytest.approx(3 * 0.9 ** 2 * 0.1 + 0.9 ** 3)   # 0.972
    assert rel.k_of_n(1, 1, 0.95) == pytest.approx(0.95)
    assert rel.k_of_n(4, 0, 0.1) == 1.0 and rel.k_of_n(2, 3, 0.99) == 0.0
    f = C.fleet_reliability(n=2, k=1, lambda_per_fh=1e-3, t_h=10)
    p = math.exp(-1e-2)
    assert f["p_at_least_k"] == pytest.approx(1 - (1 - p) ** 2)


def test_horizon_footprint_johnson_geo():
    h = search.horizon_km(1000.0)["horizon_km"]
    assert h == pytest.approx(4.12 * math.sqrt(1000), rel=2e-3)                # Skolnik 4/3-earth rule
    assert search.footprint(1000, 90)["swath_km"] == pytest.approx(2.0)
    j = search.johnson_range(10.0, "identification", ifov_rad=1e-4)
    assert j["max_range_km"] == pytest.approx(10 / (2 * 6.4 * 1e-4) / 1000)
    # 1° of latitude ≈ 111.19 km on the 6371 km sphere; 1°×1° cell at the equator ≈ 12364 km²
    assert geo.great_circle_km(0, 0, 1, 0) == pytest.approx(111.195, rel=1e-4)
    assert geo.polygon_area_km2([[0, 0], [0, 1], [1, 1], [1, 0]]) == pytest.approx(12364, rel=2e-3)


def test_pareto_and_weights():
    alts = [{"id": "a", "metrics": {"cost": 1, "pod": 0.5}}, {"id": "b", "metrics": {"cost": 2, "pod": 0.9}},
            {"id": "c", "metrics": {"cost": 3, "pod": 0.8}}, {"id": "d", "metrics": {"cost": 1.5}}]
    r = tradeoff.compare(alts, {"cost": "min", "pod": "max"})
    assert r["pareto"] == ["a", "b"]
    rows = {x["id"]: x for x in r["rows"]}
    assert rows["c"]["dominated_by"] == ["b"] and rows["d"]["missing"] == ["pod"] and "ranking" not in r
    r2 = tradeoff.compare(alts, {"cost": "min", "pod": "max"}, constraints={"pod": {"min": 0.6}},
                          weights={"cost": 1, "pod": 1})
    assert r2["pareto"] == ["b"] and not {x["id"]: x for x in r2["rows"]}["a"]["feasible"]
    assert r2["ranking"][0] == "b"
    with pytest.raises(ValueError):
        tradeoff.compare(alts, {"cost": "lowest"})


def test_determinism_and_study_replay(tmp_path):
    st = C.study_start("teste determinismo", "problema de teste", output_dir=str(tmp_path / "s"))
    sid = st["study_id"]
    a = C.persistent_coverage(endurance_h=12, turnaround_h=3, distance_km=150, airspeed_m_s=40, study_id=sid)
    b = C.persistent_coverage(endurance_h=12, turnaround_h=3, distance_km=150, airspeed_m_s=40)
    assert {k: v for k, v in a.items() if k != "study_call"} == b
    C.sweep_coverage(area_km2=5000, sweep_width_km=20, speed_m_s=40, time_h=3, study_id=sid)
    C.study_add(sid, "assumption", {"text": "x", "rationale": "y"})
    C.study_add(sid, "alternative", {"id": "A1", "text": "z", "evaluable": False, "reason": "not sizable"})
    C.compare([{"id": "A1", "metrics": {"c": 1, "p": 1}}], {"c": "min", "p": "max"}, plot={"x": "c", "y": "p"},
              study_id=sid)
    rep = C.study_report(sid)
    assert (tmp_path / "s" / "report.md").exists() and "recommendation" in " ".join(rep["completeness_gaps"])
    rr = C.replay(str(tmp_path / "s" / "study.json"))
    assert rr["all_same"] and [c["status"] for c in rr["calls"]] == ["same"] * 3


@pytest.mark.slow
def test_fleet_of_one_equals_size():
    # Same level policy on both sides (YAML fidelity when level omitted; was a silent L0 default before).
    s = T.size(example="uav_gasoline_150kg", level=None, no_systems=True)
    f = C.size_fleet(variants=[{"id": "x", "example": "uav_gasoline_150kg", "quantity": 1,
                                "cost": {"N": 50, "year": 2025}, "safety": {}}])
    v = f["variants"][0]
    assert v["aircraft"]["W0_kg"] == pytest.approx(s["summary"]["weights"]["W0_kg"], rel=1e-12)
    assert f["fleet"]["W0_kg"] == pytest.approx(v["aircraft"]["W0_kg"])
    assert v["certification"]["bases"] == ["stanag4703"] and 0 < v["safety"]["p_loss_per_sortie"] < 1
    f3 = C.size_fleet(variants=[{"id": "x", "example": "uav_gasoline_150kg", "quantity": 3,
                                 "cost": {"N": 50, "year": 2025}}])
    assert f3["fleet"]["W0_kg"] == pytest.approx(3 * v["aircraft"]["W0_kg"])
    assert f3["fleet"]["acquisition_usd"] == pytest.approx(3 * v["cost"]["unit_cost_usd"])


def test_mcp_concept_tools_registered():
    pytest.importorskip("mcp")
    import anyio
    from mcp import Client
    from acdt.ai.mcp_server import build_server

    async def go():
        async with Client(build_server()) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert {"concept_study_start", "persistent_coverage", "size_fleet", "compare_alternatives",
                    "sweep_coverage", "barrier_search", "fleet_reliability", "geo_measure"} <= names
            prompts = {p.name for p in (await c.list_prompts()).prompts}
            assert "concept_trade" in prompts
            r = await c.call_tool("transit_time", {"distance_km": 36, "airspeed_m_s": 10})
            sc = getattr(r, "structured_content", None) or getattr(r, "structuredContent", None)
            assert sc["t_out_h"] == pytest.approx(1.0)
    anyio.run(go)
