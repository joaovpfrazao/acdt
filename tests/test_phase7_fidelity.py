"""Phase 7 cost fidelity ladder L0 → L1 → L2: confidence flags, AACE bands, calibration higher → lower.

The L2 part list here is a SYNTHETIC test fixture (built from the L1 decomposition with chosen hours and a quote);
it exercises the mechanics, it is not data of a real aircraft."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROV = {"source_url": "https://example.org/quote-test", "retrieved": "2026-10-28", "source_type": "other"}


@pytest.fixture(scope="module")
def c172():
    from acdt.domains.aircraft import sizing
    from acdt.domains.aircraft.manufacturing.study import load_config, study
    from acdt.domains.aircraft.mission import MissionSpec
    cfg = load_config(ROOT / "examples/manufacturing/cessna172_manufacturing.yaml")
    res = sizing.run(MissionSpec.from_yaml(cfg["mission"]))
    return cfg, res, study(res, cfg["manufacturing"], out=None, plots=False)


@pytest.mark.slow
def test_bands_and_l0_flags(c172):
    from acdt.domains.aircraft.manufacturing import fidelity as F
    b = F.band(100.0, 5, 1.0)
    assert (b["low"], b["high"]) == pytest.approx((50.0, 200.0))
    b = F.band(100.0, 4, 0.0)
    assert (b["low"], b["high"]) == pytest.approx((85.0, 120.0))
    cfg, res, r = c172
    fid = r["fidelity"]
    l0 = fid["levels"]["L0"]
    assert not l0["outside_database"] and l0["band"]["aace_class"] == 5 and l0["band"]["position"] == 0.0
    assert fid["levels"]["L1"]["band"]["aace_class"] == 4
    assert fid["recommended"] == "L0"           # conventional GA, L1 not shop/L2-calibrated
    # unconventional configuration → outside the CER database, wide Class 5 band, L1 recommended
    from acdt.domains.aircraft.manufacturing.study import study
    r2 = study(res, {**cfg["manufacturing"], "configuration": ["blended wing body", "distributed propulsion"]},
               out=None, plots=False)
    l0 = r2["fidelity"]["levels"]["L0"]
    assert l0["outside_database"] and l0["confidence"] == "low" and l0["band"]["low_pct"] == pytest.approx(-50)
    assert r2["fidelity"]["recommended"] == "L1"


def _detailed(r):
    rows = {x["part"]["name"]: x for x in r["plan"]["parts"]}
    ws = rows["wing skin"]
    p = ws["part"]
    LF = r["plan"]["learning_factor"]
    h1 = ws["selected"]["labour_hours"]
    return {"parts": [
        {**{k: p[k] for k in ("kind", "group", "mass_kg", "area_m2", "perimeter_m", "max_dim_m", "thickness_m")},
         "name": "wing skin (detailed)", "l1_part": "wing skin", "count": p["count"], "material": "al2024_t3",
         "process": "sheet_metal_riveted", "labour_hours": 0.5 * h1,
         "fasteners": {"count": 400, "usd_each": 0.5, "year": 2025, "provenance": PROV}},
        {"name": "wing spar (quoted)", "l1_part": "wing spar", "kind": "spar", "group": "wing", "count": 4,
         "quote": {"usd": 1000.0, "year": 2025, "provenance": PROV}}],
        "bom": [{"item": "engine", "qty": 1, "usd": 40000, "year": 2025, "quote": True, "provenance": PROV}],
        "final_assembly_hours": 300, "final_assembly_rate_usd_h": 60}, 0.5 * h1 * LF * p["count"], h1 * LF * p["count"]


def test_l2_and_calibration(c172, tmp_path):
    from acdt.domains.aircraft.manufacturing.study import study
    cfg, res, r = c172
    det, h2, h1 = _detailed(r)
    m = {**cfg["manufacturing"], "detailed": det}
    r2 = study(res, m, out=tmp_path, plots=True)
    l2 = r2["detailed"]
    assert not l2["unresolved_parts"] and l2["totals"]["bom"] == pytest.approx(40000)
    assert l2["totals"]["final_assembly"] == pytest.approx(18000)
    assert 0 < l2["quoted_share_of_recurring"] < 1
    fid = r2["fidelity"]
    assert fid["recommended"] == "L2" and fid["levels"]["L2"]["band"]["aace_class"] == 3
    Fo = fid["calibration_out"]["factors"]
    assert Fo["k_labour_hours_L1"]["value"] == pytest.approx(h2 / h1, rel=1e-9)   # = 0.5 by construction
    assert Fo["k_cost_L0_eastlake"]["hifi_level"] == "L2"
    assert "wing:spar" not in Fo["per_part_L1"]["unmatched_L2_keys"]
    cal = tmp_path / "cost_calibration.json"
    assert cal.exists() and Path(r2["plots"]["cost_levels"]).exists()
    # apply L2 → L1: the matched L1 part hours become the L2 hours (single matched part → exact)
    r3 = study(res, {**cfg["manufacturing"], "cost_calibration": {"file": str(cal), "apply": ["cost_L1", "cost_L0"]}},
               out=None, plots=False)
    ws = [x for x in r3["plan"]["parts"] if x["part"]["name"] == "wing skin"][0]["selected"]
    assert ws["labour_hours"] * r3["plan"]["learning_factor"] * ws["count"] == pytest.approx(h2, rel=1e-6)
    f3 = r3["fidelity"]
    assert f3["levels"]["L1"]["labour_anchor"] == "L2" and f3["levels"]["L1"]["band"]["position"] == 0.0
    assert f3["levels"]["L0"]["calibrated"]
    assert f3["levels"]["L0"]["unit_cost"] == pytest.approx(
        r3["topdown"]["eastlake"]["unit_cost"] * json.loads(cal.read_text())["factors"]["k_cost_L0_eastlake"]["value"])


def test_anchored_l1_not_applied_to_l0(c172, tmp_path):
    from acdt.domains.aircraft.manufacturing.study import study
    cfg, res, _ = c172
    r = study(res, {**cfg["manufacturing"], "labour_calibration": "eastlake"}, out=tmp_path, plots=False)
    f = r["fidelity"]["calibration_out"]["factors"]["k_cost_L0_eastlake"]
    assert f["independent"] is False
    with pytest.raises(ValueError, match="not independent"):
        study(res, {**cfg["manufacturing"], "cost_calibration": {"file": str(tmp_path / "cost_calibration.json"),
                                                                 "apply": ["cost_L0"]}}, out=None, plots=False)
