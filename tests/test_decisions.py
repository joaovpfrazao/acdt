"""P5 decision log: record, invalidate, reopen."""
from __future__ import annotations

import json
from pathlib import Path

from acdt.ai import decisions as D
from acdt.core.decisions import Decision, DecisionLog, check_conditions, reopen

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "examples" / "decisions" / "seed_n1.json"


def test_add_and_check_triggers(tmp_path):
    folder = tmp_path / "log"
    D.decisions_open(str(folder), title="teste")
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    added = D.decisions_add(str(folder), **{k: seed[k] for k in
                            ("what", "why", "fidelity", "rejected", "conditions", "evidence",
                             "level_gate", "tags")})
    assert added["decision"]["status"] == "closed"
    cold = D.decisions_check(str(folder), {"radar_mass_kg": 10, "CL_alpha": 5.0,
                                           "baseline_CL_alpha": 5.0})
    assert cold["invalidations"] == []
    hot = D.decisions_check(str(folder), {"radar_mass_kg": 30, "CL_alpha": 5.0,
                                          "baseline_CL_alpha": 5.0})
    assert len(hot["invalidations"]) == 1
    assert hot["invalidations"][0]["triggered"][0]["condition"]["metric"] == "radar_mass_kg"


def test_relative_pct_condition():
    dec = Decision(
        id="D1", what="x", why="y", fidelity="N2",
        conditions=[{"metric": "CL_alpha", "op": "<", "relative_to": "baseline_CL_alpha", "pct": -10}],
    )
    r = check_conditions(dec, {"CL_alpha": 4.4, "baseline_CL_alpha": 5.0})  # 4.4 < 4.5
    assert r["invalidated"]
    r2 = check_conditions(dec, {"CL_alpha": 4.6, "baseline_CL_alpha": 5.0})
    assert not r2["invalidated"]


def test_reopen_persists(tmp_path):
    folder = tmp_path / "log2"
    D.decisions_open(str(folder))
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    D.decisions_add(str(folder), what=seed["what"], why=seed["why"], fidelity=seed["fidelity"],
                    conditions=seed["conditions"], rejected=seed["rejected"])
    out = D.decisions_check(str(folder), {"radar_mass_kg": 40}, reopen=True)
    assert len(out["reopened"]) == 1
    assert out["reopened"][0]["status"] == "open"
    listed = D.decisions_list(str(folder))
    assert listed["decisions"][0]["status"] == "open"
    assert listed["decisions"][0]["reopen_history"]


def test_report_md(tmp_path):
    folder = tmp_path / "log3"
    D.decisions_open(str(folder), title="ISR N1")
    D.decisions_add(str(folder), what="escolher EO/IR mid", why="Pareto payload_trade",
                    fidelity="N1",
                    rejected=[{"id": "eo_ir_light", "reason": "FOV insuficiente"}],
                    conditions=[{"metric": "power_w_avg", "op": ">", "value": 60}])
    rep = D.decisions_report(str(folder))
    assert "Registo de decisões" in rep["markdown"]
    assert Path(rep["path"]).exists()


def test_cli_roundtrip(tmp_path):
    import os, subprocess, sys
    folder = tmp_path / "cli"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run([sys.executable, "-m", "acdt.cli", "decisions", "open", str(folder),
                        "--title", "cli"], cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, "-m", "acdt.cli", "decisions", "add", str(folder),
                        "--input", str(SEED)], cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr + r.stdout
    metrics = tmp_path / "m.json"
    metrics.write_text(json.dumps({"radar_mass_kg": 30, "CL_alpha": 5, "baseline_CL_alpha": 5}),
                       encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "acdt.cli", "decisions", "check", str(folder),
                        "--metrics", str(metrics), "--reopen"],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "reabertas" in r.stdout
