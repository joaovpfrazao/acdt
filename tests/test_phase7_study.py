"""Phase 7 manufacturing study on the C172 (validation vs public price) and the W0–cost Pareto sweep."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def c172():
    from acdt.domains.aircraft import sizing
    from acdt.domains.aircraft.manufacturing.study import load_config
    from acdt.domains.aircraft.mission import MissionSpec
    cfg = load_config(ROOT / "examples/manufacturing/cessna172_manufacturing.yaml")
    return cfg, sizing.run(MissionSpec.from_yaml(cfg["mission"]))


@pytest.mark.slow
def test_c172_study(c172, tmp_path):
    from acdt.domains.aircraft.manufacturing.study import study
    cfg, res = c172
    r = study(res, cfg["manufacturing"], out=tmp_path, plots=True)
    v = r["validation"]
    # Eastlake (GA CER) is a manufacturer cost: below the list price but the same order of magnitude
    assert 0.3 < v["ratio_eastlake"] < 1.0
    assert 0.5 < v["ratio_dapca4"] < 3.0
    sel = r["plan"]["selection"]
    assert not r["plan"]["unresolved_parts"]
    assert {p for p, _ in sel.values()} <= {"sheet_metal_riveted", "cnc_machining"}
    assert sel["wing skin"][0] == "sheet_metal_riveted"
    for k in ("cost_breakdown", "process_options", "unit_cost_vs_N"):
        assert Path(r["plots"][k]).exists()
    # material price provenance validated and CPI-escalated (2026 → 2025 < 1)
    m = r["plan"]["materials"]["al2024_t3"]
    assert m["price_escalation"] < 1 and not [i for i in m["price_issues"] if i["severity"] == "error"]
    cal = r["calibration"]
    assert cal["bottom_up_hours_per_unit"] > cal["eastlake_mfg_hours_per_unit"]  # FOPV small-part overestimate flag


def test_c172_eastlake_calibration(c172):
    from acdt.domains.aircraft.manufacturing.study import study
    cfg, res = c172
    r = study(res, {**cfg["manufacturing"], "labour_calibration": "eastlake"}, out=None, plots=False)
    cal = r["calibration"]
    assert cal["bottom_up_hours_per_unit"] == pytest.approx(cal["eastlake_mfg_hours_per_unit"], rel=1e-6)


def test_pareto_sweep(c172, tmp_path):
    from acdt.domains.aircraft.manufacturing.pareto import nondominated, sweep
    assert nondominated([(1, 5), (2, 3), (3, 4), (4, 1)]) == [0, 1, 3]
    cfg, res = c172
    p = cfg["pareto"]
    r = sweep(res, cfg["manufacturing"], p["options"], ws_factors=(0.8,), AR_values=[7.32], out=tmp_path)
    assert len(r["points"]) == 2
    met = [q for q in r["points"] if q["option"].startswith("metal")][0]
    com = [q for q in r["points"] if not q["option"].startswith("metal")][0]
    assert com["W0"] < met["W0"]                     # composite structure lighter (Raymer composite factors)
    assert com["selection"]["wing skin"][1] == "cf_fabric_vari"
    assert r["pareto"] and Path(r["plot"]).exists()
