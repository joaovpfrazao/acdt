# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Tailless pitch trim fix (10 nov 2026): Panknin washout cross-check, trimmed-CLmax opt-in, NACA TR-796 SM band."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly import tailless_trim as TT
from acdt.domains.aircraft.assembly.tailless_approach import SM_TAILLESS, SM_TAILLESS_SOURCE

EX = Path(__file__).resolve().parents[1] / "examples"
TL = json.loads((EX / "integration" / "flying_wing_pusher_tailless.json").read_text(encoding="utf-8"))


def test_panknin_reproduces_b2streamlines_worked_example():
    # b2streamlines.com/Panknin/Panknin.html: b 120 in, chords 13/11 in, Λc/4 17°, E 222 (α0 −3.65°, Cm −0.097),
    # E 230 (α0 +1.73°, Cm +0.053), C_L 0.6, σ 0.05 → K1 0.52, K2 0.48, −8.6° total, ≈ 3.2° geometric washout
    r = TT.panknin_twist_deg(120 / 12, 17.0, 11 / 13, 0.6, 0.05, -0.097, 0.053, -3.65, 1.73)
    assert r["status"] == "assessed"
    assert r["K1"] == pytest.approx(0.52, abs=0.01) and r["K2"] == pytest.approx(0.48, abs=0.01)
    assert r["total_deg"] == pytest.approx(-8.6, abs=0.25)          # site rounds K1 to 0.52
    assert r["geometric_deg"] == pytest.approx(-3.2, abs=0.25)
    # with the site's rounded K1/K2 the published −8.6° is exact
    tot = (0.52 * -0.097 + 0.48 * 0.053 - 0.6 * 0.05) / (1.4e-5 * 10**1.43 * 17.0)
    assert tot == pytest.approx(-8.6, abs=0.05)


def test_panknin_trends_and_unswept_unassessed():
    base = TT.panknin_twist_deg(6.0, 25.0, 0.4, 0.5, 0.07)
    assert base["total_deg"] < 0
    assert TT.panknin_twist_deg(6.0, 25.0, 0.4, 0.5, 0.10)["total_deg"] < base["total_deg"]   # more SM → more washout
    assert TT.panknin_twist_deg(6.0, 35.0, 0.4, 0.5, 0.07)["total_deg"] > base["total_deg"]   # more sweep → less
    assert TT.panknin_twist_deg(6.0, 0.0, 0.4, 0.5, 0.07)["status"] == "unassessed"


def test_wing_planform_and_washout_check_on_tailless_drawing():
    a = Assembly.from_dict(TL["assembly"])
    pl = TT.wing_planform(a)
    assert pl["twist_tip_minus_root_deg"] == pytest.approx(-10.0)
    assert 0 < pl["taper"] < 1 and pl["sweep_c4_deg"] > 10 and pl["AR_mean_chord"] > 3
    w = TT.washout_check(a, 0.5, 0.07)
    assert w["panknin"]["status"] == "assessed" and w["panknin"]["total_deg"] < 0
    assert "PRESSUPOSTO" in w["note"]


def test_clmax_trimmed_opt_in_flag():
    assert TT.clmax_trimmed_requested(None) is False
    assert TT.clmax_trimmed_requested({"spec": {}}) is False
    assert TT.clmax_trimmed_requested({"spec": {"options": {"flying_wing": {"clmax": "trimmed"}}}}) is True
    assert TT.clmax_trimmed_requested({"spec": {"options": {"flying_wing": {"clmax": "fixed"}}}}) is False


def test_static_margin_band_is_tr796():
    assert SM_TAILLESS == (0.02, 0.08)
    assert "TR-796" in SM_TAILLESS_SOURCE
