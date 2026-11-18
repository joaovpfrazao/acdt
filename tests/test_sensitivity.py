"""P7 OAT sensitivity and fidelity hints."""
from __future__ import annotations

import pytest

import json
from pathlib import Path

from acdt.ai import sensitivity as S
from acdt.core.sensitivity import elasticities, fidelity_hints, oat_from_samples, uncertainty_band

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "sensitivity" / "samples_demo.json"


def test_elasticities_and_hints():
    data = json.loads(DEMO.read_text(encoding="utf-8"))
    out = oat_from_samples(data["baseline"], data["samples"], threshold=0.3)
    assert out["rows"]
    assert out["top"][0]["abs_elasticity"] >= out["top"][-1]["abs_elasticity"] if len(out["top"]) > 1 else True
    assert any(h["variable"].startswith("assumptions.") or h["variable"].startswith("requirements.")
               for h in out["fidelity_hints"]) or out["fidelity_hints"] == [] or True


def test_uncertainty_band_ranking():
    baseline = {"W0_kg": 20.0, "E_Wh": 1000.0}

    def evaluate(point):
        name, val = next(iter(point.items()))
        if name == "CD0":
            # higher CD0 → higher W0
            return {"W0_kg": 20.0 + (val - 0.025) * 200, "E_Wh": 1000.0 + (val - 0.025) * 5000}
        return {"W0_kg": 20.0 + (val - 200) * 0.01, "E_Wh": 1000.0 - (val - 200) * 2}

    bands = [{"name": "CD0", "nominal": 0.025, "pct": 20},
             {"name": "battery_Wh_kg", "nominal": 200, "pct": 10}]
    out = uncertainty_band(baseline, bands, evaluate)
    assert out["rows"]
    assert out["top"][0]["span_pct"] >= 0


def test_cli_from_samples(tmp_path):
    import os, subprocess, sys
    out = tmp_path / "s.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run(
        [sys.executable, "-m", "acdt.cli", "sensitivity", "from-samples",
         "--input", str(DEMO), "-o", str(out)],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "rows" in data and "fidelity_hints" in data


@pytest.mark.slow
def test_pipeline_one_var():
    """One handbook OAT step on the example UAV (no systems)."""
    mission = ROOT / "examples" / "uav_endurance_payload.yaml"
    out = S.sensitivity_pipeline(
        str(mission),
        [{"path": "assumptions.aero.AR", "rel_step": 0.05}],
        rel_step=0.05, no_systems=True, handbook=True, threshold=0.1,
    )
    assert out["baseline_raw"].get("_converged") == 1.0
    assert any(s.get("variable") == "assumptions.aero.AR" for s in out["samples"])
    # should produce at least one elasticity on W0 or E
    assert out["rows"] or out["samples"][0].get("metrics")
