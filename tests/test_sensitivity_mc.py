
"""P7 Monte Carlo / LHS UQ + gate coupling."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from acdt.ai import decisions as D
from acdt.ai import sensitivity as S
from acdt.core.sensitivity import monte_carlo, draw_sample, uq_interval_checks

ROOT = Path(__file__).resolve().parents[1]
MC_DEMO = ROOT / "examples" / "sensitivity" / "mc_linear_demo.json"
GATE_UQ_PASS = ROOT / "examples" / "decisions" / "gate_n1_uq_pass.json"
GATE_UQ_FAIL = ROOT / "examples" / "decisions" / "gate_n1_uq_fail.json"
GATE_UQ_UN = ROOT / "examples" / "decisions" / "gate_n1_uq_unassessed.json"
SEED = ROOT / "examples" / "decisions" / "seed_n1.json"
OAT_DEMO = ROOT / "examples" / "sensitivity" / "samples_demo.json"


def test_lhs_linear_mean():
    out = monte_carlo(
        [{"name": "x1", "dist": "uniform", "low": 0, "high": 1},
         {"name": "x2", "dist": "uniform", "low": 0, "high": 1}],
        lambda p: {"Y": 2 * p["x1"] + p["x2"]},
        n=400, method="lhs", seed=0,
    )
    assert out["status"] == "ok"
    assert out["summaries"]["Y"]["mean"] == pytest.approx(1.5, abs=0.05)
    assert out["summaries"]["Y"]["std"] == pytest.approx(math.sqrt(5 / 12), abs=0.08)
    assert "Y_p95" in out["gate_metrics"]


def test_degenerate_unassessed():
    out = monte_carlo(
        [{"name": "x", "dist": "uniform", "low": 1, "high": 1}],
        lambda p: {"Y": p["x"]},
        n=10,
    )
    assert out["status"] == "unassessed"
    assert out["summaries"] == {}


def test_all_failed_unassessed():
    out = monte_carlo(
        [{"name": "x", "dist": "uniform", "low": 0, "high": 1}],
        lambda p: None,
        n=10, method="mc", seed=1,
    )
    assert out["status"] == "unassessed"
    assert out["n_failed"] == 10


def test_precomputed_samples_cli_path():
    data = json.loads(MC_DEMO.read_text(encoding="utf-8"))
    out = S.sensitivity_mc(evaluate_table=data)
    assert out["status"] == "ok"
    assert out["summaries"]["Y"]["mean"] == pytest.approx(1.5, abs=0.1)


def test_interval_checks():
    uq = S.sensitivity_mc(evaluate_table=json.loads(MC_DEMO.read_text(encoding="utf-8")))
    rows = uq_interval_checks(uq, [
        {"metric": "W0_kg", "use": "p95", "op": "<=", "value": 100},
        {"metric": "missing", "use": "p50", "op": "<=", "value": 1},
    ])
    assert rows[0]["ok"] is True
    assert rows[1]["ok"] is None  # unassessed


def test_oat_unchanged():
    data = json.loads(OAT_DEMO.read_text(encoding="utf-8"))
    out = S.sensitivity_from_samples(data["baseline"], data["samples"])
    assert out["rows"]


def _seed(folder: Path):
    D.decisions_open(str(folder), title="uq gate")
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    keys = ("what", "why", "fidelity", "rejected", "conditions", "evidence", "level_gate", "tags")
    D.decisions_add(str(folder), **{k: seed[k] for k in keys})


def test_gate_with_uq_pass(tmp_path):
    folder = tmp_path / "gpass"
    _seed(folder)
    bundle = json.loads(GATE_UQ_PASS.read_text(encoding="utf-8"))
    out = D.decisions_gate(
        str(folder), "N1", bundle["metrics"], checks=bundle.get("checks"),
        uq=bundle["uq"], require_uq=True, uq_metric_use="p50",
    )
    assert out["uq"]["applied"] is True
    assert out["status"] == "pass"
    assert out["ready_to_close"] is True
    # radar_mass from UQ p50 should be in metrics (~20 < 25)
    assert "radar_mass_kg" in out["metrics"]


def test_gate_with_uq_interval_fail(tmp_path):
    folder = tmp_path / "gfail"
    _seed(folder)
    bundle = json.loads(GATE_UQ_FAIL.read_text(encoding="utf-8"))
    out = D.decisions_gate(
        str(folder), "N1", bundle["metrics"], checks=bundle.get("checks"),
        uq=bundle["uq"], require_uq=True,
    )
    assert out["status"] == "fail"
    assert any(c["key"].startswith("uq:") and c["ok"] is False for c in out["checks"])


def test_gate_require_uq_unassessed(tmp_path):
    folder = tmp_path / "gun"
    _seed(folder)
    bundle = json.loads(GATE_UQ_UN.read_text(encoding="utf-8"))
    out = D.decisions_gate(
        str(folder), "N1", bundle["metrics"], checks=bundle.get("checks"),
        uq=bundle["uq"], require_uq=True,
    )
    assert out["status"] == "unassessed"
    assert out["ready_to_close"] is False


def test_gate_without_uq_unchanged(tmp_path):
    folder = tmp_path / "legacy"
    _seed(folder)
    # cold metrics — no invalidation
    out = D.decisions_gate(
        str(folder), "N1",
        {"radar_mass_kg": 10, "CL_alpha": 5.0, "baseline_CL_alpha": 5.0},
        checks=[{"key": "mtow", "ok": True, "message": "ok"}],
    )
    assert out["status"] == "pass"
    assert out["uq"]["applied"] is False


def test_cli_mc_and_gate(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    out = tmp_path / "mc.json"
    r = subprocess.run(
        [sys.executable, "-m", "acdt.cli", "sensitivity", "mc",
         "--input", str(MC_DEMO), "-o", str(out)],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "mean=" in r.stdout
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summaries"]["Y"]["status"] == "ok"

    folder = tmp_path / "cli_gate"
    r = subprocess.run([sys.executable, "-m", "acdt.cli", "decisions", "open", str(folder)],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0
    r = subprocess.run([sys.executable, "-m", "acdt.cli", "decisions", "add", str(folder),
                        "--input", str(SEED)], cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    r = subprocess.run(
        [sys.executable, "-m", "acdt.cli", "decisions", "gate", str(folder),
         "--level", "N1", "--metrics", str(GATE_UQ_PASS), "--require-uq",
         "-o", str(tmp_path / "g.json")],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "pass" in r.stdout
