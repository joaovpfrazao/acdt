"""P1b (g): AVL body-model validation harness (one light case; reference comparison logic mocked)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly import validation as V

EX = Path(__file__).resolve().parents[1] / "examples"
TWIN = EX / "integration" / "twin_boom_pusher.json"


def test_munk_bound_positive_per_body():
    asm = Assembly.from_dict(json.loads(TWIN.read_text())["assembly"])
    m = V.munk_shift(asm, 5.0)
    assert m["total"] > 0 and all(v > 0 for v in m["per_body"].values())


def test_reference_comparison_requires_source_and_picks_best(monkeypatch):
    fake = {"mac": 0.5, "x_mac_le": 1.0, "x_np": 1.15, "x_np_avl_bodies": 1.10, "x_np_no_bodies": 1.20,
            "x_np_torenbeek": 1.16, "avl_no_bodies": {"CLa": 5.0}}
    monkeypatch.setattr(V, "neutral_point", lambda asm, mach=0.0: fake)
    sp = json.loads(TWIN.read_text())
    sp["validation"] = {"reference": {"xbar_np": 0.32}}
    with pytest.raises(ValueError):
        V.run_case(sp)
    sp["validation"]["reference"]["source"] = "test only (mock)"
    r = V.run_case(sp)
    assert r["xbar_np"]["avl_torenbeek"] == pytest.approx(0.32) and r["best"] == "avl_torenbeek"
    assert r["error_mac"]["avl_bodies"] == pytest.approx(-0.12)


@pytest.mark.requires_avl
def test_harness_runs_one_case(tmp_path):
    rows = V.run_cases([TWIN])
    r = rows[0]
    assert set(r["xbar_np"]) == {"avl_bodies", "avl_no_bodies", "avl_torenbeek", "munk_bound"}
    assert r["shift_mac"]["torenbeek"] <= 0 and r["shift_mac"]["munk_bound"] < 0
    p = V.write_report(rows, tmp_path / "v.md")
    assert "twin_boom_pusher" in p.read_text()
