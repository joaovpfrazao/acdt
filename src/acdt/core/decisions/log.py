"""Decision record + invalidation / reopen (DESIGN_WORKFLOW §6–7).

Each decision stores what was chosen, why (cited tool results), fidelity level,
rejected alternatives with reasons, and invalidation conditions. When a later
metric meets a condition, :func:`check_conditions` flags it and :func:`reopen`
marks the decision open again so saved alternatives can be re-evaluated.

Condition grammar (all numeric comparisons on a flat ``metrics`` dict):
  ``{"metric": "radar_mass_kg", "op": ">", "value": 25}``
  ``{"metric": "CL_alpha", "op": "<", "value": 4.0, "relative_to": "baseline_CL_alpha", "pct": -10}``
  — if ``relative_to`` + ``pct`` are set, compare metric to baseline*(1+pct/100) with ``op``.

References: INCOSE SE Handbook 4th ed. (decision record / traceability);
Sobek, Ward & Liker, *Sloan Management Review* 40(4), 1999 (set-based concurrent engineering).
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "acdt.decision_log/1"
OPS = ("<", "<=", ">", ">=", "==", "!=")
REF = ("INCOSE Systems Engineering Handbook, 4th ed. (decision record); "
       "Sobek/Ward/Liker 1999 (set-based — keep rejected alternatives for reopen); "
       "DESIGN_WORKFLOW §6–7")


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40].strip("_") or "dec"


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Decision:
    id: str
    what: str
    why: str
    fidelity: str                          # N0|N1|N2|N3|L0|L1|…
    status: str = "closed"                 # closed | open | superseded
    rejected: list[dict] = field(default_factory=list)  # [{id, reason, metrics?}]
    conditions: list[dict] = field(default_factory=list)  # invalidation conditions
    evidence: list[dict] = field(default_factory=list)    # [{tool, run_id?, summary}]
    level_gate: str | None = None          # e.g. "N1"
    tags: list[str] = field(default_factory=list)
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)
    reopen_history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Decision":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


def _eval_one(cond: dict, metrics: dict) -> tuple[bool, str]:
    """Return (triggered, explanation). Missing metric → not triggered."""
    m = cond.get("metric")
    if m is None or m not in metrics:
        return False, f"métrica '{m}' ausente — condição não avaliada"
    val = float(metrics[m])
    op = cond.get("op", ">")
    if op not in OPS:
        raise ValueError(f"op inválido: {op} (use {OPS})")
    if cond.get("relative_to") is not None and cond.get("pct") is not None:
        base_key = cond["relative_to"]
        if base_key not in metrics:
            return False, f"baseline '{base_key}' ausente — condição não avaliada"
        threshold = float(metrics[base_key]) * (1.0 + float(cond["pct"]) / 100.0)
        label = f"{m}={val:g} {op} {base_key}×(1{float(cond['pct']):+g}%)={threshold:g}"
    else:
        threshold = float(cond["value"])
        label = f"{m}={val:g} {op} {threshold:g}"
    ok = {
        "<": val < threshold, "<=": val <= threshold,
        ">": val > threshold, ">=": val >= threshold,
        "==": val == threshold, "!=": val != threshold,
    }[op]
    return ok, label


def check_conditions(decision: Decision | dict, metrics: dict) -> dict[str, Any]:
    """Evaluate invalidation conditions against ``metrics``. Does not mutate."""
    d = decision if isinstance(decision, Decision) else Decision.from_dict(decision)
    hits, misses = [], []
    for i, c in enumerate(d.conditions):
        trig, expl = _eval_one(c, metrics)
        row = {"index": i, "condition": c, "triggered": trig, "explanation": expl}
        (hits if trig else misses).append(row)
    return {
        "decision_id": d.id,
        "status": d.status,
        "invalidated": bool(hits) and d.status == "closed",
        "triggered": hits,
        "not_triggered": misses,
        "reference": REF,
    }


def reopen(decision: Decision, metrics: dict | None = None, reason: str | None = None) -> Decision:
    """Mark decision open; append reopen history. Caller should re-evaluate ``rejected``."""
    check = check_conditions(decision, metrics or {}) if metrics is not None else None
    decision.status = "open"
    decision.updated = _now()
    decision.reopen_history.append({
        "at": decision.updated,
        "reason": reason or "condição de invalidação cumprida",
        "triggered": (check or {}).get("triggered"),
    })
    return decision


class DecisionLog:
    """Persisted log of design decisions (``decisions.json``)."""

    def __init__(self, folder: Path, log_id: str | None = None, title: str = "decision log"):
        self.folder = Path(folder)
        self.data: dict[str, Any] = {
            "schema": SCHEMA,
            "id": log_id or _slug(title),
            "title": title,
            "created": _now(),
            "decisions": [],
            "reference": REF,
        }

    @classmethod
    def load(cls, path: Path) -> "DecisionLog":
        p = Path(path)
        if p.is_dir():
            p = p / "decisions.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        log = cls(p.parent, d.get("id"), d.get("title", "decision log"))
        log.data = d
        return log

    def save(self) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        p = self.folder / "decisions.json"
        p.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        return p

    def _next_id(self, prefix: str = "D") -> str:
        n = len(self.data["decisions"]) + 1
        return f"{prefix}{n}"

    def add(self, what: str, why: str, fidelity: str, *,
            rejected: list[dict] | None = None,
            conditions: list[dict] | None = None,
            evidence: list[dict] | None = None,
            level_gate: str | None = None,
            tags: list[str] | None = None,
            decision_id: str | None = None,
            status: str = "closed") -> Decision:
        dec = Decision(
            id=decision_id or self._next_id(),
            what=what, why=why, fidelity=fidelity, status=status,
            rejected=list(rejected or []),
            conditions=list(conditions or []),
            evidence=list(evidence or []),
            level_gate=level_gate,
            tags=list(tags or []),
        )
        self.data["decisions"].append(dec.to_dict())
        return dec

    def get(self, decision_id: str) -> Decision | None:
        for d in self.data["decisions"]:
            if d["id"] == decision_id:
                return Decision.from_dict(d)
        return None

    def update(self, decision: Decision) -> None:
        for i, d in enumerate(self.data["decisions"]):
            if d["id"] == decision.id:
                decision.updated = _now()
                self.data["decisions"][i] = decision.to_dict()
                return
        raise KeyError(decision.id)

    def check(self, metrics: dict, decision_id: str | None = None) -> dict[str, Any]:
        """Check one or all closed decisions; return invalidations."""
        rows = []
        for raw in self.data["decisions"]:
            if decision_id and raw["id"] != decision_id:
                continue
            r = check_conditions(raw, metrics)
            rows.append(r)
        return {
            "metrics": metrics,
            "invalidations": [r for r in rows if r["invalidated"]],
            "results": rows,
            "reference": REF,
        }

    def reopen_invalidated(self, metrics: dict) -> dict[str, Any]:
        """Reopen every closed decision whose conditions fire; persist not automatic."""
        report = self.check(metrics)
        reopened = []
        for inv in report["invalidations"]:
            dec = self.get(inv["decision_id"])
            assert dec is not None
            reopen(dec, metrics=metrics)
            self.update(dec)
            reopened.append(dec.to_dict())
        return {"reopened": reopened, "check": report}

    def report_md(self) -> str:
        d = self.data
        L = [f"# Registo de decisões: {d['title']}", "",
             f"*`{d['id']}` ({d['schema']}), criado {d['created']}. "
             "Cada decisão traz porquê, fidelidade, alternativas rejeitadas e condições de invalidação "
             "(DESIGN_WORKFLOW §6–7).*", ""]
        for raw in d["decisions"]:
            L += [f"## {raw['id']} — {raw['what']}", "",
                  f"* Estado: **{raw['status']}**; fidelidade: `{raw['fidelity']}`"
                  + (f"; gate `{raw['level_gate']}`" if raw.get("level_gate") else ""),
                  f"* Porquê: {raw['why']}", ""]
            if raw.get("evidence"):
                L.append("Evidência:")
                for e in raw["evidence"]:
                    L.append(f"* `{e.get('tool', '?')}`"
                             + (f" (run `{e['run_id']}`)" if e.get("run_id") else "")
                             + (f" — {e['summary']}" if e.get("summary") else ""))
                L.append("")
            if raw.get("rejected"):
                L += ["Alternativas rejeitadas:", ""]
                for r in raw["rejected"]:
                    L.append(f"* **{r.get('id', '?')}** — {r.get('reason', '')}")
                L.append("")
            if raw.get("conditions"):
                L += ["Condições de invalidação:", ""]
                for c in raw["conditions"]:
                    if c.get("relative_to") is not None:
                        L.append(f"* `{c['metric']}` {c.get('op', '>')} "
                                 f"{c['relative_to']} × (1{float(c['pct']):+g}%)")
                    else:
                        L.append(f"* `{c['metric']}` {c.get('op', '>')} {c.get('value')}")
                L.append("")
            if raw.get("reopen_history"):
                L.append("Reaberturas:")
                for h in raw["reopen_history"]:
                    L.append(f"* {h.get('at')}: {h.get('reason')}")
                L.append("")
        return "\n".join(L)

    def write_report(self) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        p = self.folder / "decisions.md"
        p.write_text(self.report_md(), encoding="utf-8")
        return p

    def level_gate(self, level: str, metrics: dict, *,
                   checks: list[dict] | None = None,
                   reopen_invalidated: bool = False,
                   require_decisions: bool = True,
                   uq: dict | None = None,
                   require_uq: bool = False,
                   uq_metric_use: str = "p50") -> dict[str, Any]:
        """End-of-level gate (DESIGN_WORKFLOW §7). See :func:`gate.level_gate`."""
        from .gate import level_gate as _gate
        return _gate(self, level, metrics, checks=checks,
                     reopen_invalidated=reopen_invalidated,
                     require_decisions=require_decisions,
                     uq=uq, require_uq=require_uq, uq_metric_use=uq_metric_use)
