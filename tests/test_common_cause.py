# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Fator β de causa comum (NUREG/CR-5485 Ap. A, Eq. A.10–A.13) e ligação à FTA ARP4761."""
from __future__ import annotations

import math

import pytest

from acdt.core.reliability.common_cause import (apply_beta_factor, beta_split, common_cause_block,
                                                redundancy_tree)
from acdt.core.safety.fta import BasicEvent, FaultTree, Gate


def test_beta_split_is_eq_a13():
    sp = beta_split(1e-3, 0.05)
    assert sp["Q_1"] == pytest.approx(0.95e-3) and sp["Q_m"] == pytest.approx(5e-5)
    assert sp["Q_1"] + sp["Q_m"] == pytest.approx(sp["Q_t"])          # Eq. A.12
    assert beta_split(1e-3, 1.2) is None and beta_split(-1.0, 0.1) is None and beta_split(1e-3, True) is None


def test_two_train_active_redundancy_exact_and_rare_event():
    r = common_cause_block({"groups": [{"id": "FCC", "m": 2, "q_total": 1e-3, "beta": 0.05,
                                        "beta_source": "valor de teste"}]}, None)
    g = r["groups"][0]
    assert r["veredicto"] == "validado" and g["veredicto"] == "validado"
    q1, qm = 0.95e-3, 5e-5
    assert g["q_top_rare_event"] == pytest.approx(q1 * q1 + qm)                    # [(1−β)Q]² + βQ
    assert g["q_top"] == pytest.approx(q1 * q1 + qm - q1 * q1 * qm)               # exata (Shannon)
    assert g["q_top_independent_only"] == pytest.approx(1e-6)
    assert ["FCC.CCF"] in g["minimal_cut_sets"] and ["FCC.1.I", "FCC.2.I"] in g["minimal_cut_sets"]
    assert g["ccf_share_of_top"] > 0.9                                            # a causa comum domina


def test_k_of_n_and_beta_zero_reduces_to_independent():
    r = common_cause_block({"groups": [{"id": "S", "m": 3, "k_fail": 2, "q_total": 1e-2, "beta": 0.0,
                                        "beta_source": "β = 0 (identidade)"}]}, None)
    g = r["groups"][0]
    q = 1e-2
    assert g["q_top"] == pytest.approx(3 * q * q * (1 - q) + q ** 3)
    assert g["q_top"] == pytest.approx(g["q_top_independent_only"])


def test_unknown_beta_or_source_is_not_zero():
    r = common_cause_block({"groups": [{"id": "A", "m": 2, "q_total": 1e-3},
                                       {"id": "B", "m": 2, "q_total": 1e-3, "beta": 0.1}]}, None)
    assert r["veredicto"] == "nao_avaliado"
    for g in r["groups"]:
        assert g["q_top"] is None and g["q_top_bounds"] == {"lo": pytest.approx(1e-6), "hi": None}
    assert "fonte" in " ".join(r["groups"][1]["notes"])
    assert common_cause_block({"groups": [{"id": "C", "m": 2, "beta": 0.1, "beta_source": "x"}]},
                              None)["groups"][0]["q_top"] is None
    assert common_cause_block(None, None)["veredicto"] == "nao_pedido"


def test_lambda_and_mission_time():
    r = common_cause_block({"groups": [{"id": "M", "m": 2, "lambda_per_h": 1e-4, "beta": 0.1,
                                        "beta_source": "teste"}]}, 2.0)
    g = r["groups"][0]
    assert g["Q_t"] == pytest.approx(-math.expm1(-2e-4)) and g["q_from"]["t_h"] == 2.0


def test_apply_to_existing_arp4761_tree_with_shared_event():
    t = FaultTree(top="TOP")
    for e in ("a", "b"):
        t.add_event(BasicEvent(e, prob=1e-3))
    t.add_event(BasicEvent("c", prob=1e-2))
    t.add_gate(Gate("AB", "AND", ["a", "b"]))
    t.add_gate(Gate("TOP", "OR", ["AB", "c"]))
    before = t.top_probability()
    blk = apply_beta_factor(t, ["a", "b"], 0.1, group_id="G", source="teste")
    assert blk["veredicto"] == "validado" and "G.CCF" in t.events and t.gates["a"].kind == "OR"
    after = t.top_probability()
    q_ab = (0.9e-3) ** 2 + 1e-4 - (0.9e-3) ** 2 * 1e-4
    assert after == pytest.approx(1 - (1 - q_ab) * (1 - 1e-2))
    assert after > before
    # Q_t diferentes no grupo: a árvore não muda
    u = FaultTree(top="T")
    u.add_event(BasicEvent("x", prob=1e-3))
    u.add_event(BasicEvent("y", prob=2e-3))
    u.add_gate(Gate("T", "AND", ["x", "y"]))
    blk2 = apply_beta_factor(u, ["x", "y"], 0.1, group_id="H")
    assert blk2["veredicto"] == "nao_avaliado" and set(u.events) == {"x", "y"}


def test_redundancy_tree_gate_kinds():
    assert redundancy_tree("g", 0.1, 3, 3).gates["g.TOP"].kind == "AND"
    assert redundancy_tree("g", 0.1, 3, 1).gates["g.TOP"].kind == "OR"
    assert redundancy_tree("g", 0.1, 3, 2).gates["g.TOP"].kind == "KOFN"


def test_study_side_block():
    from acdt.core.reliability.standby import evaluate_extensions

    blk = evaluate_extensions({"common_cause": {"groups": [{"id": "FCC", "m": 2, "q_total": 1e-3, "beta": 0.05,
                                                            "beta_source": "teste"}]}}, 1.0)
    assert blk["fator_beta"] == "validado" and blk["common_cause"]["groups"][0]["veredicto"] == "validado"
    assert blk["replaces_rbd"] is False
    none = evaluate_extensions({"standby": {"n": 2, "lambda_per_h": 1e-3, "t_h": 1.0}}, 1.0)
    assert none["fator_beta"] == "nao_avaliado" and none["common_cause"]["beta"] is None
