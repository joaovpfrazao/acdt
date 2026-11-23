# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""MGL e fator α de causa comum (NUREG/CR-5485 §5.3 Eq. 5.6–5.13, Ap. A Eq. A.21–A.26, Tabela A-2)."""
from __future__ import annotations

import math

import pytest

from acdt.core.reliability.common_cause import (alpha_q, alpha_to_mgl_staggered, apply_multi_ccf, common_cause_block,
                                                mgl_q, mgl_to_alpha_staggered, redundancy_tree)


def test_mgl_m3_is_eq_5_11():
    Qt, b, g = 1e-3, 0.1, 0.3
    q1, q2, q3 = mgl_q(Qt, 3, [b, g])
    assert q1 == pytest.approx((1 - b) * Qt)
    assert q2 == pytest.approx(0.5 * b * (1 - g) * Qt)
    assert q3 == pytest.approx(b * g * Qt)


def test_mgl_reduces_to_beta_factor_for_m2():
    q1, q2 = mgl_q(1e-3, 2, [0.05])
    assert (q1, q2) == pytest.approx((0.95e-3, 0.05e-3))


@pytest.mark.parametrize("m", [2, 3, 4, 5, 6])
def test_sum_identity_and_staggered_equivalence(m):
    greek = [0.1, 0.4, 0.5, 0.6, 0.7][: m - 1]
    Qt = 2e-3
    qm = mgl_q(Qt, m, greek)
    assert sum(math.comb(m - 1, k - 1) * qm[k - 1] for k in range(1, m + 1)) == pytest.approx(Qt)
    a = mgl_to_alpha_staggered(greek)                     # Tabela A-2
    assert sum(a) == pytest.approx(1.0)
    assert alpha_q(Qt, a, staggered=True) == pytest.approx(qm)
    assert alpha_to_mgl_staggered(a) == pytest.approx(greek)


def test_table_a2_m4_explicit():
    b, g, d = 0.2, 0.3, 0.4
    a = mgl_to_alpha_staggered([b, g, d])
    assert a == pytest.approx([1 - b, (1 - g) * b, (1 - d) * b * g, b * g * d])


def test_alpha_nonstaggered_eq_5_7_matches_a25_conversion_m3():
    a = [0.95, 0.03, 0.02]
    Qt = 1e-3
    at = a[0] + 2 * a[1] + 3 * a[2]
    q = alpha_q(Qt, a, staggered=False)
    assert q == pytest.approx([a[0] / at * Qt, a[1] / at * Qt, 3 * a[2] / at * Qt])
    # Eq. A.25 (não escalonado, m = 3) → MGL → Eq. 5.13 dá o mesmo
    beta = (2 * a[1] + 3 * a[2]) / at
    gamma = 3 * a[2] / (2 * a[1] + 3 * a[2])
    assert mgl_q(Qt, 3, [beta, gamma]) == pytest.approx(q)
    assert sum(math.comb(2, k - 1) * q[k - 1] for k in (1, 2, 3)) == pytest.approx(Qt)
    # Eq. A.23: m/C(m,k) α_k/α_t Q_t
    assert q == pytest.approx([3 / math.comb(3, k) * a[k - 1] / at * Qt for k in (1, 2, 3)])


def test_fta_two_of_three_matches_eq_5_12():
    Qt, b, g = 1e-3, 0.1, 0.3
    qk = mgl_q(Qt, 3, [b, g])
    tree = redundancy_tree("S", Qt, 3, 2)
    blk = apply_multi_ccf(tree, ["S.1", "S.2", "S.3"], qk, group_id="S", source="t")
    assert blk["evaluated"] and blk["n_ccf_events"] == 4
    rare = 3 * ((1 - b) * Qt) ** 2 + 1.5 * b * (1 - g) * Qt + b * g * Qt          # Eq. 5.12
    assert tree.rare_event() == pytest.approx(rare, rel=1e-12)
    assert tree.top_probability() == pytest.approx(rare, rel=1e-3)
    assert tree.top_probability() < rare


def test_block_requires_source_and_testing():
    base = {"id": "G", "m": 3, "k_fail": 2, "q_total": 1e-3}
    r = common_cause_block({"groups": [dict(base, model="mgl", mgl=[0.1, 0.3])]}, None)
    assert r["veredicto"] == "nao_avaliado" and r["groups"][0]["q_top"] is None
    r = common_cause_block({"groups": [dict(base, model="alpha", alpha=[0.95, 0.03, 0.02], params_source="x")]}, None)
    assert r["veredicto"] == "nao_avaliado" and "testing" in r["groups"][0]["notes"][0]
    r = common_cause_block({"groups": [dict(base, model="alpha", alpha=[0.9, 0.03, 0.02], params_source="x",
                                            testing="escalonado")]}, None)
    assert r["veredicto"] == "nao_avaliado"                                       # Σ α ≠ 1
    ok = common_cause_block({"groups": [dict(base, model="mgl", mgl=[0.1, 0.3], params_source="x")]}, None)
    g = ok["groups"][0]
    assert ok["veredicto"] == "validado" and g["sum_check_Q_t"] == pytest.approx(1e-3)
    assert g["q_top"] > g["q_top_independent_only"]
    assert common_cause_block({"groups": [dict(base, model="xyz")]}, None)["veredicto"] == "nao_avaliado"


def test_m_above_limit_not_assessed():
    m = 7
    tree = redundancy_tree("B", 1e-3, m, m)
    blk = apply_multi_ccf(tree, [f"B.{i + 1}" for i in range(m)], mgl_q(1e-3, m, [0.1] * (m - 1)), group_id="B",
                          source="t")
    assert not blk["evaluated"] and "B.1" in tree.events
