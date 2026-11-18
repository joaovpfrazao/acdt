"""MCP registration for P5 decision log."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import Field

from . import decisions as D


def register(srv, ann, call) -> None:
    tool = srv.tool

    @tool(name="decisions_open", annotations=ann(False, "Create a decision log folder"))
    async def decisions_open(
            folder: Annotated[str, Field(description="directory for decisions.json")],
            title: str = "decision log",
            log_id: Annotated[Optional[str], Field(description="optional id")] = None,
    ) -> dict[str, Any]:
        """Create an empty decision log (DESIGN_WORKFLOW §6)."""
        return await call(D.decisions_open, folder, title, log_id)

    @tool(name="decisions_add", annotations=ann(False, "Record a design decision"))
    async def decisions_add(
            folder: Annotated[str, Field(description="decision log folder")],
            what: Annotated[str, Field(description="what was decided")],
            why: Annotated[str, Field(description="why — cite tool results")],
            fidelity: Annotated[str, Field(description="N0|N1|N2|N3|L0|L1|…")],
            rejected: Annotated[Optional[list], Field(description="[{id, reason, metrics?}]")] = None,
            conditions: Annotated[Optional[list], Field(
                description="invalidation: [{metric, op, value}] or "
                            "[{metric, op, relative_to, pct}]")] = None,
            evidence: Annotated[Optional[list], Field(description="[{tool, run_id?, summary}]")] = None,
            level_gate: Annotated[Optional[str], Field(description="gate level e.g. N1")] = None,
            tags: Annotated[Optional[list[str]], Field(description="free tags")] = None,
            decision_id: Annotated[Optional[str], Field(description="override id")] = None,
    ) -> dict[str, Any]:
        """Append a closed decision with rejected alternatives and invalidation conditions."""
        return await call(D.decisions_add, folder, what, why, fidelity, rejected, conditions,
                          evidence, level_gate, tags, decision_id)

    @tool(name="decisions_check", annotations=ann(False, "Evaluate invalidation conditions"))
    async def decisions_check(
            folder: Annotated[str, Field(description="decision log folder")],
            metrics: Annotated[dict, Field(description="flat {metric: number} from latest tools")],
            decision_id: Annotated[Optional[str], Field(description="check one id only")] = None,
            reopen: Annotated[bool, Field(description="if true, reopen invalidated decisions")] = False,
    ) -> dict[str, Any]:
        """Check conditions; with reopen=true mark affected decisions open (set-based revisit)."""
        return await call(D.decisions_check, folder, metrics, decision_id, reopen)

    @tool(name="decisions_list", annotations=ann(True, "List decisions in a log"))
    async def decisions_list(folder: Annotated[str, Field(description="decision log folder")]) -> dict:
        return await call(D.decisions_list, folder)

    @tool(name="decisions_report", annotations=ann(False, "Write decisions.md"))
    async def decisions_report(folder: Annotated[str, Field(description="decision log folder")]) -> dict:
        return await call(D.decisions_report, folder)

    @tool(name="decisions_gate", annotations=ann(False, "End-of-level gate pass|fail|unassessed"))
    async def decisions_gate(
            folder: Annotated[str, Field(description="decision log folder")],
            level: Annotated[str, Field(description="N0|N1|N2|N3|…")],
            metrics: Annotated[dict, Field(description="flat {metric: number}")],
            checks: Annotated[Optional[list], Field(
                description="optional [{key, ok: bool|null, message?}] — ok=null → unassessed"
            )] = None,
            reopen: Annotated[bool, Field(
                description="reopen invalidated decisions and list rejected alts to re-evaluate"
            )] = False,
            require_decisions: Annotated[bool, Field(
                description="if true, no decisions at level → unassessed"
            )] = True,
            uq: Annotated[Optional[dict], Field(
                description="opt-in P7 MC/Sobol summary (gate_metrics, summaries, interval_checks)"
            )] = None,
            require_uq: Annotated[bool, Field(
                description="if true, missing/unassessed UQ → gate unassessed"
            )] = False,
            uq_metric_use: Annotated[str, Field(
                description="which MC summary fills condition metrics: p50|p95|mean|…"
            )] = "p50",
    ) -> dict[str, Any]:
        """DESIGN_WORKFLOW §7 gate. Never treats unassessed/missing as pass; does not pick a winner."""
        return await call(D.decisions_gate, folder, level, metrics, checks, reopen,
                          require_decisions, uq, require_uq, uq_metric_use)
