"""MTOW alignment: size_fleet and acdt size / toolkit.size share the same pipeline and level policy."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from acdt.ai import concept as C
from acdt.ai import toolkit as T

EX = Path(__file__).resolve().parents[1] / "examples"
UAV = "uav_gasoline_150kg"
VARIANT_L = EX / "concept" / "illegal_fishing" / "variant_L.yaml"


@pytest.mark.slow
def test_fleet_of_one_matches_size_when_level_omitted():
    """Default size_fleet (no level) must match toolkit.size(level=None) = acdt size YAML policy."""
    s = T.size(example=UAV, level=None, no_systems=True)
    f = C.size_fleet(variants=[{"id": "x", "example": UAV, "quantity": 1}])
    w_s = s["summary"]["weights"]["W0_kg"]
    w_f = f["variants"][0]["aircraft"]["W0_kg"]
    assert w_f == pytest.approx(w_s, rel=1e-12, abs=1e-9)
    assert f["variants"][0]["level"] == "spec"
    assert f["mtow_alignment"]["same_pipeline_as_acdt_size"] is True


@pytest.mark.slow
def test_forced_L0_differs_from_yaml_lowfi_but_fleet_matches_forced_size():
    """Historical discrepancy: L0 handbook vs YAML lowfi — now explicit, not silent."""
    s_yaml = T.size(example=UAV, level=None, no_systems=True)
    s_L0 = T.size(example=UAV, level="L0", no_systems=True)
    f_L0 = C.size_fleet(variants=[{"id": "x", "example": UAV, "quantity": 1, "level": "L0"}])
    w_yaml = s_yaml["summary"]["weights"]["W0_kg"]
    w_L0 = s_L0["summary"]["weights"]["W0_kg"]
    assert abs(w_L0 - w_yaml) > 1.0  # real gap that used to look like a bug
    assert f_L0["variants"][0]["aircraft"]["W0_kg"] == pytest.approx(w_L0, rel=1e-12)
    assert f_L0["variants"][0]["level"] == "L0"


@pytest.mark.slow
@pytest.mark.requires_avl
def test_compare_helper_agree_spec_and_report_forced_gap():
    cmp0 = C.compare_size_fleet_mtow(str(VARIANT_L), level=None)
    assert cmp0["status"] == "agree"
    assert abs(cmp0["delta_kg"]) <= 1e-6
    cmp1 = C.compare_size_fleet_mtow(str(VARIANT_L), level="L0")
    assert cmp1["status"] == "agree_forced_level"
    assert cmp1["comparable_to_bare_acdt_size"] is False
    assert abs(cmp1["delta_forced_vs_yaml_kg"]) > 1.0
    # lock the measured Nansei-class gap order of magnitude (~7.5 kg on variant_L at this revision)
    assert 5.0 < abs(cmp1["delta_forced_vs_yaml_kg"]) < 15.0


@pytest.mark.slow
def test_run_id_feed_reuses_size_result():
    s = T.size(example=UAV, level=None, no_systems=True)
    f = C.size_fleet(variants=[{"id": "fed", "run_id": s["run_id"], "quantity": 2}])
    assert f["variants"][0]["status"] == "done"
    assert f["fleet"]["W0_kg"] == pytest.approx(2 * s["summary"]["weights"]["W0_kg"], rel=1e-12)


@pytest.mark.slow
def test_existing_fleet_of_one_L0_contract():
    """Explicit L0 on both sides still agrees (legacy test contract)."""
    s = T.size(example=UAV, level="L0", no_systems=True)
    f = C.size_fleet(variants=[{"id": "x", "example": UAV, "quantity": 1, "level": "L0",
                                "cost": {"N": 50, "year": 2025}, "safety": {}}])
    assert f["variants"][0]["aircraft"]["W0_kg"] == pytest.approx(s["summary"]["weights"]["W0_kg"], rel=1e-12)
