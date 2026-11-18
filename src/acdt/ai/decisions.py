"""Toolkit wrappers for P5 decision log."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from acdt.core.decisions import DecisionLog, check_conditions, level_gate


def decisions_open(folder: str, title: str = "decision log", log_id: str | None = None) -> dict:
    log = DecisionLog(Path(folder), log_id=log_id, title=title)
    path = log.save()
    return {"path": str(path), "id": log.data["id"], "schema": log.data["schema"]}


def decisions_add(folder: str, what: str, why: str, fidelity: str,
                  rejected: list[dict] | None = None,
                  conditions: list[dict] | None = None,
                  evidence: list[dict] | None = None,
                  level_gate: str | None = None,
                  tags: list[str] | None = None,
                  decision_id: str | None = None) -> dict:
    p = Path(folder)
    log = DecisionLog.load(p) if (p / "decisions.json").exists() or p.name.endswith(".json") else DecisionLog(p)
    if p.suffix == ".json":
        log = DecisionLog.load(p)
    dec = log.add(what, why, fidelity, rejected=rejected, conditions=conditions,
                  evidence=evidence, level_gate=level_gate, tags=tags, decision_id=decision_id)
    path = log.save()
    log.write_report()
    return {"path": str(path), "decision": dec.to_dict()}


def decisions_check(folder: str, metrics: dict, decision_id: str | None = None,
                    reopen: bool = False) -> dict[str, Any]:
    log = DecisionLog.load(Path(folder))
    if reopen:
        out = log.reopen_invalidated(metrics)
        log.save()
        log.write_report()
        return out
    return log.check(metrics, decision_id=decision_id)


def decisions_list(folder: str) -> dict:
    log = DecisionLog.load(Path(folder))
    return {"id": log.data["id"], "title": log.data["title"],
            "decisions": log.data["decisions"], "reference": log.data["reference"]}


def decisions_report(folder: str) -> dict:
    log = DecisionLog.load(Path(folder))
    md = log.write_report()
    return {"path": str(md), "markdown": log.report_md()}


def decisions_gate(folder: str, level: str, metrics: dict,
                   checks: list[dict] | None = None,
                   reopen: bool = False,
                   require_decisions: bool = True,
                   uq: dict | None = None,
                   require_uq: bool = False,
                   uq_metric_use: str = "p50") -> dict[str, Any]:
    """Opt-in end-of-level gate (N0/N1/…). Status pass|fail|unassessed; never pass on missing evidence.

    With ``reopen=True``, invalidated closed decisions are marked open and rejected
    alternatives are listed for re-evaluation (no auto-winner).

    ``uq`` / ``require_uq``: opt-in P7 Monte Carlo or Sobol summary coupling — missing or
    unassessed UQ never counts as pass.
    """
    log = DecisionLog.load(Path(folder))
    out = level_gate(log, level, metrics, checks=checks,
                     reopen_invalidated=reopen,
                     require_decisions=require_decisions,
                     uq=uq, require_uq=require_uq, uq_metric_use=uq_metric_use)
    if reopen and out.get("reopened"):
        log.save()
        log.write_report()
        out["path"] = str(log.folder / "decisions.json")
    # always write gate snapshot next to the log when folder writable
    try:
        gate_path = Path(folder) / f"gate_{level}.json"
        if Path(folder).suffix == ".json":
            gate_path = Path(folder).parent / f"gate_{level}.json"
        gate_path.parent.mkdir(parents=True, exist_ok=True)
        import json
        gate_path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str),
                             encoding="utf-8")
        out["gate_path"] = str(gate_path)
    except OSError:
        pass
    return out
