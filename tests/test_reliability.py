# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina fiabilidade e manutenção de frota (docs/FIABILIDADE.md): V&V MIL-HDBK-338B, RBD, intervalos e
desconhecidos, manutibilidade, sobressalentes, frota, custo operacional, API e pipeline."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

EX = Path(__file__).resolve().parents[1] / "examples"


# ------------------------------------------------------------------------------------------ V&V (MIL-HDBK-338B)
def test_mil338b_availability_example3():
    from acdt.core.reliability import maintenance as mt

    assert mt.inherent_availability(100.0, 0.5) == pytest.approx(0.995, abs=5e-4)
    assert mt.achieved_availability(75.0, 0.75) == pytest.approx(0.99, abs=5e-3)
    assert mt.operational_availability(75.0, 0.75 + 0.3 + 0.4, 20.0) == pytest.approx(95.0 / 96.45, rel=1e-12)


def test_mil338b_interval_availability_example4():
    from acdt.core.reliability.maintenance import interval_availability

    assert interval_availability(0.01, 2.0, 1.0) == pytest.approx(0.9972, abs=5e-5)
    assert interval_availability(0.01, 2.0, 1e7) == pytest.approx(2.0 / 2.01, rel=1e-6)  # Eq. 10.25


def test_mil338b_poisson_spares():
    from acdt.core.reliability.spares import poisson_cdf, stock_for

    assert poisson_cdf(2, 0.5) == pytest.approx(0.986, abs=5e-4)
    assert stock_for(0.5, 0.98) == 2 and stock_for(0.5, 0.90) == 1
    assert poisson_cdf(800, 800.0) == pytest.approx(0.5094, abs=1e-3)  # ramo scipy (a > 500)


def test_mil338b_eq630_paths():
    from acdt.core.reliability.rbd import prob

    P = {"A": 0.3, "B1": 0.1, "B2": 0.1, "C1": 0.2, "C2": 0.2}
    node = {"type": "paths", "paths": [["A", "C1"], ["A", "C2"], ["B1", "C1"], ["B2", "C2"]]}
    assert prob(node, lambda c: P[c]) == pytest.approx(0.13572, abs=5e-6)
    # Eq. 6.30 escrita à mão
    pa, pb, pc = 0.3, 0.1, 0.2
    assert prob(node, lambda c: P[c]) == pytest.approx((2 * pc - pc ** 2) * pa + (2 * pb * pc - (pb * pc) ** 2) * (1 - pa))


def test_parallel_mttf_gain():
    from acdt.core.reliability.rbd import k_of_n_identical_mttf, mttf, parallel_identical_mttf

    lam = 2e-4
    assert mttf({"type": "parallel", "blocks": ["a", "b"]}, {"a": lam, "b": lam}, 0.0) == pytest.approx(
        parallel_identical_mttf(lam, 2), rel=1e-8)
    assert parallel_identical_mttf(lam, 2) * lam == pytest.approx(1.5)
    n = {"type": "k_of_n", "k": 2, "n": 3, "block": "a"}
    assert mttf(n, {"a": lam}, 0.0) == pytest.approx(k_of_n_identical_mttf(lam, 3, 2), rel=1e-8)
    assert mttf({"type": "series", "blocks": ["a", "b"]}, {"a": 1e-3, "b": 1e-5}, 0.0) == pytest.approx(1 / 1.01e-3)


def test_vv_cases_registered_and_pass():
    from acdt.core import vv

    r = vv.run(disciplines=["fiabilidade"])
    st = {c["id"]: c["status"] for c in r["cases"]}
    assert set(st) == {
        "FIAB-338B-AVAIL-EX3", "FIAB-338B-AAV-EX4", "FIAB-338B-POISSON-5381", "FIAB-338B-EQ630",
        "FIAB-338B-PARALLEL-MTBF", "FIAB-338B-STANDBY-N4", "FIAB-338B-WEIBULL-5361"}
    assert set(st.values()) == {"passa"}


# ------------------------------------------------------------------------------------------ RBD e taxas
def test_rbd_k_of_n_nonidentical_and_validation():
    from acdt.core.reliability.rbd import prob, validate

    node = {"type": "k_of_n", "k": 2, "blocks": ["a", "b", "c"]}
    p = {"a": 0.9, "b": 0.8, "c": 0.7}
    exact = sum(math.prod(p[x] if x in s else 1 - p[x] for x in "abc") for s in ("ab", "ac", "bc", "abc"))
    assert prob(node, p.__getitem__) == pytest.approx(exact)
    with pytest.raises(ValueError, match="repetido"):
        validate({"type": "series", "blocks": ["a", {"type": "parallel", "blocks": ["a", "b"]}]}, {"a", "b"})
    with pytest.raises(ValueError, match="não declarado"):
        validate("z", {"a"})


def test_rates_provenance_rules():
    from acdt.core.reliability.rates import resolve

    assert not resolve({"id": "x", "lambda_per_h": 1e-4}).known  # sem fonte → desconhecido
    assert resolve({"id": "x", "lambda_per_h": 1e-4, "source": "datasheet X rev. B"}).known
    r = resolve({"id": "x", "mtbf_h": {"lo": 1000, "hi": 4000}, "source": "ensaio"})
    assert (r.lo, r.hi) == (pytest.approx(2.5e-4), pytest.approx(1e-3))
    assert not resolve({"id": "x", "supplier": {"mtbf_h": 5000}}).known  # fornecedor sem fonte/data
    s = resolve({"id": "x", "supplier": {"mtbf_h": 5000, "source": "Fornecedor Y, carta", "retrieved": "2026-11-01"}})
    assert s.known and s.lo == pytest.approx(2e-4) and s.kind == "supplier"
    assert not resolve({"id": "x", "rate_key": "uav_flight_computer"}).known  # kind: assumption
    assert resolve({"id": "x", "rate_key": "uav_flight_computer"}, accept_assumptions=True).known
    pub = resolve({"id": "x", "rate_key": "alternator"})
    assert pub.known and pub.kind == "published"
    assert not resolve({"id": "x"}).known


def _spec(**kw):  # noqa: ANN003, ANN202
    s = {"mission_duration_h": 2.0, "components": [
        {"id": "motor", "lambda_per_h": 1e-4, "source": "teste", "mttr_h": 2.0, "mmh_per_action": 3.0,
         "replacement_cost": 500.0},
        {"id": "servo", "lambda_per_h": 5e-4, "source": "teste", "mttr_h": 0.5, "mmh_per_action": 1.0,
         "replacement_cost": 200.0}],
        "rbd": {"type": "series", "blocks": ["motor", {"type": "k_of_n", "k": 3, "n": 4, "block": "servo"}]},
        "preventive": [{"id": "inspecao", "interval_fh": 50.0, "duration_h": 1.0, "mmh": 2.0}],
        "logistics": {"mean_logistic_delay_h": 4.0, "mean_admin_delay_h": 1.0}}
    s.update(kw)
    return s


def test_study_closed_form_values():
    from acdt.core.reliability.study import analyse

    o = analyse(_spec())
    lam = 1e-4 + 4 * 5e-4  # MTBF básica: as quatro unidades de servo contam
    assert o["basic"]["mtbf_h"]["lo"] == pytest.approx(1 / lam)
    p = math.exp(-5e-4 * 2.0)
    R = math.exp(-1e-4 * 2.0) * (4 * p ** 3 * (1 - p) + p ** 4)
    assert o["mission"]["reliability"]["lo"] == pytest.approx(R)
    mct = (1e-4 * 2.0 + 2e-3 * 0.5) / lam  # Eq. 5.75
    assert o["maintenance"]["mttr_h"]["lo"] == pytest.approx(mct)
    f = 1 / 50.0
    assert o["maintenance"]["mtbm_h"]["lo"] == pytest.approx(1 / (lam + f))
    mbar = (lam * mct + f * 1.0) / (lam + f)
    assert o["maintenance"]["m_bar_h"]["lo"] == pytest.approx(mbar)
    assert o["maintenance"]["mmh_per_fh"]["hi"] == pytest.approx(1e-4 * 3 + 2e-3 * 1 + f * 2)
    mtbm = 1 / (lam + f)
    assert o["availability"]["operational"]["lo"] == pytest.approx(mtbm / (mtbm + mbar + 5.0))
    assert o["mtbcf_s"]["lo"] == pytest.approx(o["mission"]["mtbcf_h"]["lo"] * 3600)


def test_unknown_rate_gives_bounds_not_zero():
    from acdt.core.reliability.study import analyse

    s = _spec()
    s["components"].append({"id": "gnss", "mttr_h": 0.5, "mmh_per_action": 0.5})  # sem taxa
    s["rbd"]["blocks"].append("gnss")
    o = analyse(s)
    assert o["unknown_components"] == ["gnss"]
    assert o["mission"]["reliability"]["lo"] == 0.0 and o["mission"]["reliability"]["hi"] > 0.99
    assert o["basic"]["mtbf_h"]["lo"] is None and o["basic"]["mtbf_h"]["hi"] is not None
    assert o["maintenance"]["mmh_per_fh"]["hi"] is None and o["availability"]["operational"]["lo"] is None
    # sem atrasos logísticos: A_o só com majorante
    s2 = _spec(logistics=None)
    o2 = analyse(s2)
    assert o2["availability"]["operational"]["lo"] is None
    assert o2["availability"]["operational"]["hi"] == pytest.approx(o2["availability"]["achieved"]["hi"])


def test_fleet_sorties_spares_and_operating_cost():
    from acdt.core.reliability.study import analyse

    s = _spec(fleet={"mode": "sorties", "sorties_per_day": 6, "sortie_duration_h": 2.0, "turnaround_h": 1.0,
                     "operating_hours_per_day": 12.0},
              spares={"resupply_days": 14, "confidence": 0.9},
              operating_cost={"unit_price": 50000.0, "maintenance_rate_per_h": 60.0, "depreciation_years": 5})
    o = analyse(s)
    A = o["availability"]["operational"]["lo"]
    R = o["mission"]["reliability"]["lo"]
    assert o["fleet_size"]["hi"] == math.ceil(6 / R * 3.0 / (A * 12.0))
    ffh = 6 / R * 2.0
    a_servo = 5e-4 * 4 * ffh * 14
    from acdt.core.reliability.spares import stock_for
    assert o["spares"]["by_component"]["servo"]["stock"]["hi"] == stock_for(a_servo, 0.9)
    oc = o["operating_cost"]
    assert oc["status"] == "ok"
    assert oc["items_per_fh"]["maintenance_labour"] == pytest.approx(60.0 * o["maintenance"]["mmh_per_fh"]["hi"])
    assert oc["items_per_fh"]["maintenance_parts"] == pytest.approx(1e-4 * 500 + 2e-3 * 200)
    # peças desconhecidas → custo operacional parcial (nunca zero)
    s["components"][0].pop("replacement_cost")
    oc2 = analyse(s)["operating_cost"]
    assert oc2["status"] == "partial" and oc2["per_flight_hour"] is None


def test_fleet_coverage_reuses_fleet_feedback():
    from acdt.core.concept.fleet_feedback import fleet
    from acdt.core.reliability.study import analyse

    cov = {"mode": "coverage", "n_stations": 1, "on_station_h": 4.0, "transit_h": 1.0, "turnaround_h": 2.0,
           "handoff_overlap_h": 0.25}
    o = analyse(_spec(fleet=cov))
    A = o["availability"]["operational"]["lo"]
    ref = fleet(4.0, 1.0, 2.0, {"availability": A, "n_stations": 1, "handoff_overlap_h": 0.25})
    assert o["fleet_size"]["hi"] == ref["fleet_expected"]
    # gancho: fleet_feedback aceita a disponibilidade calculada pela fiabilidade
    r2 = fleet(4.0, 1.0, 2.0, {"availability": {"reliability": _spec()}, "n_stations": 1, "handoff_overlap_h": 0.25})
    assert r2["fleet_expected"] == ref["fleet_expected"]
    with pytest.raises(ValueError, match="desconhecida"):
        fleet(4.0, 1.0, 2.0, {"availability": {"reliability": _spec(logistics=None)}, "n_stations": 1,
                              "handoff_overlap_h": 0.25})


def test_morph_operating_cost_hook():
    from acdt.domains.aircraft.morphology.evaluate import attach_operating_cost

    row: dict = {}
    attach_operating_cost(row, {"unit_price": 20000.0, "flight_hours_per_year": 300.0,
                                "maintenance_rate_per_h": 50.0, "reliability": _spec()})
    assert row["operating_cost"]["status"] == "ok"
    assert row["operating_cost"]["items_per_fh"]["maintenance_parts"] == pytest.approx(1e-4 * 500 + 2e-3 * 200)
    row2: dict = {}
    s = _spec()
    s["components"][1].pop("mmh_per_action")
    attach_operating_cost(row2, {"unit_price": 20000.0, "flight_hours_per_year": 300.0,
                                 "maintenance_rate_per_h": 50.0, "reliability": s})
    assert row2["operating_cost"]["status"] == "unassessed"


def test_api():
    from acdt import api

    r = api.reliability(_spec())
    assert r["schema"] == "acdt.reliability/1"
    a = api.availability(mtbf_h=100, mttr_h=0.5, mtbm_h=75, m_bar_h=0.75, mdt_h=1.45, ready_time_h=20)
    assert a["inherent"] == pytest.approx(0.995, abs=5e-4) and a["operational"] == pytest.approx(0.985, abs=5e-4)
    s = api.spares_stock(0.001, 500, 0.98)
    assert s["stock"] == 2
    with pytest.raises(ValueError):
        api.reliability({"components": []})


# ------------------------------------------------------------------------------------------ pipeline
@pytest.mark.slow
def test_reliability_stage_in_pipeline_requirements_and_db():
    """UAV elétrico de exemplo (só teste; o projeto não muda): sem componentes → não avaliada; com componentes,
    frota por surtidas e requisitos na matriz de verificação e no design.json."""
    import yaml

    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec

    d = yaml.safe_load((EX / "uav_endurance_payload.yaml").read_text(encoding="utf-8"))
    d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
    d["assumptions"].setdefault("stability", {})["use_avl"] = False
    d.pop("systems", None)
    st = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_endurance_payload.yaml"))
    assert st["result"].reliability["evaluated"] is False
    rel = _spec(fleet={"mode": "sorties", "sorties_per_day": 3, "turnaround_h": 1.0, "operating_hours_per_day": 16})
    rel.pop("mission_duration_h")
    d["assumptions"]["reliability"] = rel
    d["requirements"]["mission_reliability"] = {"min": 0.99, "id": "RL-01"}
    d["requirements"]["operational_availability"] = {"min": 0.5, "id": "RL-02"}
    d["requirements"]["maintenance_man_hours_per_fh"] = {"max": 1.0, "id": "RL-03"}
    d["requirements"]["fleet_size"] = {"max": 20, "id": "RL-04"}
    d["requirements"]["mtbcf"] = {"min": 100, "unit": "h", "id": "RL-05"}
    st2 = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_endurance_payload.yaml"))
    rl = st2["result"].reliability
    assert rl["evaluated"] and rl["mission"]["duration_h"] > 0
    assert "segmentos" in rl["adapter_notes"][0] or "endurance" in rl["adapter_notes"][0]
    rows = {r["id"]: r for r in st2["verification"]["rows"]}
    for k in ("RL-01", "RL-02", "RL-03", "RL-04", "RL-05"):
        assert rows[k]["status"] == "passa", (k, rows[k])
    assert "L0" in st2["design"]["results"]["fiabilidade"]


def test_sortie_duration_defaults_to_mission_duration():
    from acdt.core.reliability.study import analyse

    s = _spec(fleet={"mode": "sorties", "sorties_per_day": 2, "turnaround_h": 1.0, "operating_hours_per_day": 12})
    r = analyse(s)
    assert r["fleet"]["cases"]["lo"]["fleet"] is not None
    s.pop("mission_duration_h")
    with pytest.raises(ValueError):
        analyse(s)


# -------------------------------------------------------------------------------- espera inativa e Weibull
def test_inactive_standby_identities():
    from acdt.core.reliability.standby import (inactive_standby_mtbf_h, inactive_standby_mtbf_two_h,
                                               inactive_standby_reliability, inactive_standby_reliability_two)

    # Fig. 7.5-17: n = 4, t/θ = 1. A soma impressa é e^{−1} (1 + 1 + 1/2 + 1/6).
    exact = math.exp(-1.0) * (1.0 + 1.0 + 0.5 + 1.0 / 6.0)
    r4 = inactive_standby_reliability(0.01, 4, 100.0)
    assert r4 == pytest.approx(exact)
    assert r4 is not None and r4 >= 0.98
    assert inactive_standby_mtbf_h(0.01, 4) == pytest.approx(400.0)
    # n = 1 é a exponencial; n = 2 com taxas iguais é e^{−λt}(1 + λt) e MTBF = 2/λ.
    assert inactive_standby_reliability(0.02, 1, 50.0) == pytest.approx(math.exp(-1.0))
    assert inactive_standby_reliability(0.01, 2, 100.0) == pytest.approx(2.0 / math.e)
    assert inactive_standby_reliability_two(0.01, 0.01, 100.0) == pytest.approx(2.0 / math.e)
    assert inactive_standby_mtbf_two_h(0.01, 0.01) == pytest.approx(200.0)
    la, lb, t = 0.01, 0.02, 100.0
    closed = (lb / (lb - la)) * math.exp(-la * t) - (la / (lb - la)) * math.exp(-lb * t)
    assert inactive_standby_reliability_two(la, lb, t) == pytest.approx(closed)
    assert inactive_standby_mtbf_two_h(la, lb) == pytest.approx(1.0 / la + 1.0 / lb)
    near = inactive_standby_reliability_two(0.01, 0.01 * (1.0 + 1e-12), 100.0)
    assert near == pytest.approx(2.0 / math.e, rel=1e-6)


def test_standby_rejects_invalid_and_does_not_invent():
    from acdt.core.reliability.standby import (inactive_standby_mtbf_h, inactive_standby_reliability,
                                               inactive_standby_reliability_two, weibull_hazard_per_h)

    assert inactive_standby_reliability(-0.01, 2, 10.0) is None
    assert inactive_standby_reliability(0.01, 0, 10.0) is None
    assert inactive_standby_reliability(0.01, 2, -1.0) is None
    assert inactive_standby_reliability(True, 2, 10.0) is None  # type: ignore[arg-type]
    assert inactive_standby_mtbf_h(0.0, 2) is None  # λ = 0 → MTBF infinita, não zero
    assert inactive_standby_reliability(0.0, 2, 10.0) == 1.0
    assert inactive_standby_reliability_two(0.0, 0.02, 10.0) == 1.0
    assert weibull_hazard_per_h(0.0, 0.5, 1000.0) is None  # singular, não zero


def test_weibull_handbook_example():
    from acdt.core.reliability.standby import weibull_hazard_per_h, weibull_reliability

    assert weibull_reliability(100.0, 2.0, 1000.0) == pytest.approx(math.exp(-0.01))
    assert weibull_reliability(100.0, 2.0, 1000.0) == pytest.approx(0.99, abs=5e-4)
    assert weibull_hazard_per_h(100.0, 2.0, 1000.0) == pytest.approx(0.0002, abs=1e-12)
    assert weibull_reliability(100.0, 1.0, 1000.0) == pytest.approx(math.exp(-0.1))  # β = 1, exponencial
    assert weibull_reliability(100.0, 2.0, 1000.0, location_h=10.0) is None
    assert weibull_hazard_per_h(100.0, 2.0, 1000.0, location_h=10.0) is None


def test_standby_fault_tree_is_not_a_gate():
    from acdt.core.reliability.standby import inactive_standby_reliability, standby_fault_tree
    from acdt.core.safety.fta import BasicEvent, FaultTree, Gate

    r = inactive_standby_reliability(0.01, 2, 100.0)
    assert r is not None
    tree = standby_fault_tree("SB", r)
    assert tree is not None
    assert tree.top_probability(100.0) == pytest.approx(1.0 - r)
    assert tree.minimal_cut_sets() == [frozenset({"SB"})]
    q = -math.expm1(-1.0)
    active = FaultTree(top="G")
    active.add_event(BasicEvent("a", rate_per_h=0.01, exposure_h=100.0))
    active.add_event(BasicEvent("b", rate_per_h=0.01, exposure_h=100.0))
    active.add_gate(Gate("G", "AND", ["a", "b"]))
    series = FaultTree(top="G")
    series.add_event(BasicEvent("a", rate_per_h=0.01, exposure_h=100.0))
    series.add_event(BasicEvent("b", rate_per_h=0.01, exposure_h=100.0))
    series.add_gate(Gate("G", "OR", ["a", "b"]))
    assert active.top_probability(100.0) == pytest.approx(q * q)
    assert series.top_probability(100.0) == pytest.approx(1.0 - math.exp(-2.0))
    assert active.top_probability(100.0) != pytest.approx(1.0 - r)
    assert series.top_probability(100.0) != pytest.approx(1.0 - r)


def test_study_standby_weibull_does_not_replace_mission():
    from acdt.core.reliability.study import analyse

    base = analyse(_spec())
    assert "standby_weibull" not in base
    side = analyse(_spec(standby={"n": 2, "lambda_per_h": 1e-3, "t_h": 100.0},
                          weibull=[{"id": "tube", "shape": 2, "scale_h": 1000, "t_h": 100}]))
    assert side["mission"]["reliability"] == base["mission"]["reliability"]
    assert side["basic"]["mtbf_h"] == base["basic"]["mtbf_h"]
    block = side["standby_weibull"]
    assert block["veredicto"] == "validado"
    assert block["standby"]["veredicto"] == "validado"
    assert block["standby"]["replaces_rbd"] is False
    assert block["standby"]["R"] == pytest.approx(math.exp(-0.1) * 1.1)
    assert block["weibull"]["items"][0]["hazard_per_h"] == pytest.approx(0.0002)
    assert block["fator_beta"] == "nao_avaliado"
    assert block["comutador_imperfeito"] == "nao_avaliado"
    assert "não substitui" in side["notes"][-1]
    switched = analyse(_spec(standby={"n": 2, "lambda_per_h": 1e-3, "t_h": 100.0, "switch_rate_per_h": 1e-4}))
    sb = switched["standby_weibull"]["standby"]
    assert sb["veredicto"] == "nao_avaliado" and sb["R"] is None
    assert sb["R_perfect_switch"] == pytest.approx(math.exp(-0.1) * 1.1)
    assert sb["switch"]["imperfect"]["applied"] is False
    mixed = analyse(_spec(weibull=[{"id": "loc", "shape": 2, "scale_h": 1000, "t_h": 100, "location_h": 5}]))
    assert mixed["standby_weibull"]["veredicto"] == "nao_avaliado"
    assert mixed["standby_weibull"]["weibull"]["items"][0]["R"] is None
    ambiguous = analyse(_spec(standby={"n": 2, "lambda_per_h": 1e-3, "lambda_a_per_h": 1e-3,
                                       "lambda_b_per_h": 2e-3, "t_h": 1.0}))
    assert ambiguous["standby_weibull"]["standby"]["R"] is None


def test_adapter_forwards_standby_block():
    from acdt.domains.aircraft.reliability import build_spec

    o = {"mission_duration_h": 1.0, "components": [{"id": "a"}],
         "standby": {"n": 4, "lambda_per_h": 0.01}}
    spec, _notes = build_spec(object(), o)  # type: ignore[arg-type]
    assert spec["standby"]["n"] == 4
    assert "weibull" not in spec
