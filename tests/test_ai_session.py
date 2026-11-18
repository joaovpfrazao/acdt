"""End-to-end demo: scripted MCP client session (examples/ai_session/session.py), requirement dict → validated →
sized L0/L1 → MDO → dossier, with the compute plan for hifi (heavy step left for the user's approval)."""
import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")
pytest.importorskip("openmdao")


@pytest.mark.slow
def test_ai_session_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("ACDT_RUNS_DIR", str(tmp_path / "runs"))
    p = Path(__file__).resolve().parents[1] / "examples" / "ai_session" / "session.py"
    spec = importlib.util.spec_from_file_location("ai_session", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.main(["--out", str(tmp_path / "out")]) == 0
    log = json.loads((tmp_path / "out" / "transcript.json").read_text(encoding="utf-8"))
    tools = [e["tool"] for e in log]
    assert tools == ["requirements_schema", "validate_requirements", "size", "size", "optimize", "compare_runs",
                     "hifi_estimate", "generate_report"]
    assert not any(e["is_error"] for e in log)
    s0, s1, opt = log[2]["result"], log[3]["result"], log[4]["result"]
    assert s0["level"] == "L0" and s1["level"] == "L1" and s0["summary"]["feasible"]
    assert opt["status"] == "done" and opt["summary"]["trust_region_iterations"] >= 1
    assert log[6]["result"]["verdict"] == "needs_user_approval"
    from acdt.ai import registry
    rec = registry.load(s1["run_id"]).record
    assert rec["parent_run"] == s0["run_id"]
    src = {a["path"]: a["source"] for a in rec["assumptions"]}
    assert "uav_endurance_payload.yaml" in src["aero.AR"] and "level=L1" in src["aero.fidelity"]
    md = (tmp_path / "out" / "dossier.md").read_text(encoding="utf-8")
    assert s0["run_id"] in md and opt["run_id"] in md
