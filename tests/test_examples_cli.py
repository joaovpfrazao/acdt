import json
from pathlib import Path

import pytest

from acdt.cli import main
from acdt.domains.aircraft.mission import MissionSpec
from acdt.domains.aircraft.sizing import run

EX = Path(__file__).parents[1] / "examples"


@pytest.mark.parametrize("name,expect_active", [
    ("ga_range_speed", "Vmax"),                 # range + speed driven
    ("trainer_maneuver_cost", "Volta"),         # manoeuvre + cost driven
])
def test_requirement_mixes(name, expect_active):
    r = run(MissionSpec.from_yaml(EX / f"{name}.yaml"))
    assert r.feasible
    assert any(expect_active in a for a in r.design_point.active)


def test_cost_objective_selects_min_weight():
    r = run(MissionSpec.from_yaml(EX / "trainer_maneuver_cost.yaml"))
    assert r.cost is not None and 5e4 < r.cost.unit_cost < 1e6


@pytest.mark.slow
def test_cli_uav(tmp_path):
    rc = main(["size", str(EX / "uav_endurance_payload.yaml"), "-o", str(tmp_path)])
    # Phase 3: with the takeoff+climb energy taken from the same segment model as the verification, the
    # baseline (AR 14 by hand) needs a slightly bigger wing and breaks the 4.2 m span limit — reported, not
    # hidden; `acdt optimize` resolves it (see test_phase3)
    assert rc == 1
    for f in ("report.md", "constraint_diagram.png", "drag_polar.png", "result.json", "harness.wireviz.yml",
              "netlist.csv", "compliance_checklist.md"):
        assert (tmp_path / f).exists(), f
    d = json.loads((tmp_path / "result.json").read_text())
    failed = {c["key"] for c in d["checks"] if c["ok"] is False and not c["key"].startswith(
        ("perf:", "hq:", "aeroel:", "wb:", "gear:"))}
    # with the optional NeuralFoil/AeroSandbox installed (Phase 5 [wingbox] extra) the section polars come from
    # NeuralFoil instead of the thin-airfoil/XFOIL path and the baseline W0 grows to ≈ 27 kg (> 25 kg MTOW limit)
    # — environment dependent, checked at ba83c41 back to Phase 4 commits; both outcomes are accepted
    assert "wing_span" in failed and failed <= {"wing_span", "mtow"} and 15 < d["weights"]["W0_kg"] <= 30
    assert d["systems"]["battery"]["current_ok"]
    assert d["systems"]["autopilot"]["imu"] >= 3
    # matriz de verificação gerada pelo pipeline (docs/REQUISITOS.md): a envergadura falha também lá
    m = json.loads((tmp_path / "verification_matrix.json").read_text(encoding="utf-8"))
    assert m["schema"] == "acdt.verification/1" and (tmp_path / "verification_matrix.md").exists()
    rows = {r["quantity"]: r for r in m["rows"]}
    assert rows["wing_span"]["status"] == "falha" and rows["wing_span"]["evidence"].startswith("result.json#")
    assert sum(m["coverage"]["por_estado"].values()) == len(m["rows"])
    assert m["provenance"]["fingerprint"]


@pytest.mark.slow
def test_cli_overconstrained_returns_nonzero(tmp_path):
    rc = main(["size", str(EX / "uav_overconstrained.yaml"), "-o", str(tmp_path)])
    assert rc == 1
    d = json.loads((tmp_path / "result.json").read_text())
    assert not d["feasible"]
    assert any(c["key"] == "mtow" and c["ok"] is False for c in d["checks"])


def test_no_closure_reported(tmp_path):
    import yaml
    d = yaml.safe_load((EX / "uav_endurance_payload.yaml").read_text())
    d["requirements"]["endurance"] = {"min": 10, "unit": "h"}
    spec2 = MissionSpec.from_dict(d)
    r = run(spec2)
    assert not r.feasible and any("No closure" in i.message for i in r.issues)


def test_requirements_listing(capsys):
    assert main(["requirements"]) == 0
    assert "endurance" in capsys.readouterr().out


def test_jet_path():
    spec = MissionSpec.from_dict({"name": "jet", "aircraft_class": "jet_trainer", "requirements": {
        "propulsion_type": "jet", "crew_mass": 180, "payload_mass": 50, "range": {"min": 1200, "unit": "km"},
        "cruise_speed": {"target": 180, "altitude": {"value": 8000, "unit": "m"}},
        "stall_speed": {"max": 50}, "takeoff_ground_roll": {"max": 600}}})
    r = run(spec)
    assert r.feasible and r.thrust_sl > 0 and r.design_point.metric == "T/W"
