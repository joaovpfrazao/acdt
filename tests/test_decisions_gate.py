"""P5 end-of-level gate: pass / fail / unassessed + rejected re-evaluation."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from acdt.ai import decisions as D
from acdt.core.decisions import DecisionLog, level_gate, reevaluate_rejected

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "examples" / "decisions" / "seed_n1.json"
SEED_M = ROOT / "examples" / "decisions" / "seed_n1_with_rejected_metrics.json"
PASS = ROOT / "examples" / "decisions" / "gate_n1_pass.json"
FAIL = ROOT / "examples" / "decisions" / "gate_n1_fail.json"
UNASS = ROOT / "examples" / "decisions" / "gate_n1_unassessed.json"


def _load_bundle(path: Path) -> tuple[dict, list]:
    d = json.loads(path.read_text(encoding="utf-8"))
    return d["metrics"], d.get("checks") or []


def _seed_log(folder: Path, seed_path: Path = SEED) -> None:
    D.decisions_open(str(folder), title="gate demo")
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    keys = ("what", "why", "fidelity", "rejected", "conditions", "evidence", "level_gate", "tags")
    D.decisions_add(str(folder), **{k: seed[k] for k in keys if k in seed})


def test_gate_pass(tmp_path):
    folder = tmp_path / "pass"
    _seed_log(folder)
    metrics, checks = _load_bundle(PASS)
    out = D.decisions_gate(str(folder), "N1", metrics, checks=checks)
    assert out["status"] == "pass"
    assert out["ready_to_close"] is True
    assert out["n_decisions"] == 1
    assert out["rejected_reevaluation"] == []
    assert Path(out["gate_path"]).exists()


def test_gate_fail_invalidation_and_check(tmp_path):
    folder = tmp_path / "fail"
    _seed_log(folder)
    metrics, checks = _load_bundle(FAIL)
    out = D.decisions_gate(str(folder), "N1", metrics, checks=checks)
    assert out["status"] == "fail"
    assert out["ready_to_close"] is False
    assert out["rejected_reevaluation"]
    ids = {a["id"] for a in out["rejected_reevaluation"][0]["rejected_to_reevaluate"]}
    assert "flying_wing" in ids
    assert any(c["status"] == "fail" for c in out["checks"])


def test_gate_unassessed_missing_metric_and_null_check(tmp_path):
    folder = tmp_path / "unass"
    _seed_log(folder)
    metrics, checks = _load_bundle(UNASS)
    out = D.decisions_gate(str(folder), "N1", metrics, checks=checks)
    assert out["status"] == "unassessed"
    assert out["ready_to_close"] is False
    # missing radar_mass_kg on condition
    assert out["decisions"][0]["unassessed_conditions"]
    assert any(c["status"] == "unassessed" for c in out["checks"])


def test_gate_empty_level_unassessed(tmp_path):
    folder = tmp_path / "empty"
    D.decisions_open(str(folder), title="empty")
    # decision at N0 only
    D.decisions_add(str(folder), what="concept", why="geo", fidelity="N0", level_gate="N0",
                    conditions=[])
    out = D.decisions_gate(str(folder), "N1", {"x": 1}, checks=[{"key": "ok", "ok": True}])
    assert out["status"] == "unassessed"
    assert out["n_decisions"] == 0


def test_gate_reopen_lists_rejected(tmp_path):
    folder = tmp_path / "reopen"
    _seed_log(folder, SEED_M)
    metrics, checks = _load_bundle(FAIL)
    out = D.decisions_gate(str(folder), "N1", metrics, checks=checks, reopen=True)
    assert out["status"] == "fail"
    assert len(out["reopened"]) == 1
    assert out["reopened"][0]["status"] == "open"
    plan = out["rejected_reevaluation"][0]
    assert plan["rejected_to_reevaluate"][0]["action"] == "re-evaluate"
    # stored vs current overlap for flying_wing radar_mass
    fw = next(a for a in plan["rejected_to_reevaluate"] if a["id"] == "flying_wing")
    assert "radar_mass_kg" in (fw.get("current_metrics_overlap") or {})
    listed = D.decisions_list(str(folder))
    assert listed["decisions"][0]["status"] == "open"


def test_gate_open_decision_blocks_pass(tmp_path):
    folder = tmp_path / "open"
    _seed_log(folder)
    metrics, checks = _load_bundle(PASS)
    # force open
    log = DecisionLog.load(folder)
    dec = log.get("D1")
    dec.status = "open"
    log.update(dec)
    log.save()
    out = D.decisions_gate(str(folder), "N1", metrics, checks=checks)
    assert out["status"] == "fail"


def test_reevaluate_rejected_helper():
    seed = json.loads(SEED_M.read_text(encoding="utf-8"))
    seed["id"] = "D1"
    seed["status"] = "closed"
    plan = reevaluate_rejected(seed, triggered=[{"explanation": "radar>25"}],
                               metrics={"radar_mass_kg": 30})
    assert plan["rejected_to_reevaluate"]
    assert "weighted" in plan["note"] or "vencedor" in plan["note"] or "winner" in plan["note"]


def test_legacy_check_unchanged(tmp_path):
    """Default check/list path untouched when gate not requested."""
    folder = tmp_path / "legacy"
    _seed_log(folder)
    cold = D.decisions_check(str(folder), {"radar_mass_kg": 10, "CL_alpha": 5.0,
                                           "baseline_CL_alpha": 5.0})
    assert cold["invalidations"] == []
    assert "status" not in cold or cold.get("status") != "pass"  # check API ≠ gate


def test_cli_gate(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    folder = tmp_path / "cli"
    r = subprocess.run([sys.executable, "-m", "acdt.cli", "decisions", "open", str(folder)],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, "-m", "acdt.cli", "decisions", "add", str(folder),
                        "--input", str(SEED)], cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr + r.stdout
    r = subprocess.run([sys.executable, "-m", "acdt.cli", "decisions", "gate", str(folder),
                        "--level", "N1", "--metrics", str(PASS), "-o", str(tmp_path / "g.json")],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "pass" in r.stdout
    data = json.loads((tmp_path / "g.json").read_text(encoding="utf-8"))
    assert data["status"] == "pass"
    r = subprocess.run([sys.executable, "-m", "acdt.cli", "decisions", "gate", str(folder),
                        "--level", "N1", "--metrics", str(UNASS)],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "unassessed" in r.stdout
