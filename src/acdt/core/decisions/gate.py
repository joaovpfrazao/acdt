"""End-of-level gate for decision logs (DESIGN_WORKFLOW §7).

Opt-in: evaluates recorded decisions and outstanding checks for a named level
(N0, N1, N2, …) and returns status ``pass`` | ``fail`` | ``unassessed``.

Rules (unknown ≠ zero / unassessed ≠ pass):
* missing metric on an invalidation condition → that item is **unassessed**
* check with ``ok is None`` → **unassessed**
* check with ``ok is False`` or a triggered invalidation → **fail**
* open decisions at the level → **fail** (set-based revisit not finished)
* no decisions recorded for the level when ``require_decisions`` → **unassessed**
* overall is pass only if nothing failed and nothing is unassessed

Does **not** auto-pick a weighted winner among alternatives (Sobek/Ward/Liker
set-based). When conditions fire, rejected alternatives are listed for the
agent to re-evaluate; ``reopen=True`` marks those decisions ``open``.

References: INCOSE SE Handbook 4th ed.; Sobek/Ward/Liker 1999; DESIGN_WORKFLOW §6–7.
"""
from __future__ import annotations

from typing import Any

from .log import REF, Decision, DecisionLog, check_conditions, reopen

GATE_REF = REF + "; DESIGN_WORKFLOW §7 (gates e reavaliação)"
VALID_STATUS = ("pass", "fail", "unassessed")


def _level_match(raw: dict, level: str) -> bool:
    """Decision belongs to the gate level via ``level_gate`` or ``fidelity``."""
    lg = (raw.get("level_gate") or "").strip()
    fid = (raw.get("fidelity") or "").strip()
    lvl = level.strip()
    if lg:
        return lg.upper() == lvl.upper()
    return fid.upper() == lvl.upper()


def _classify_conditions(decision: Decision | dict, metrics: dict) -> dict[str, Any]:
    """Like check_conditions but splits not-triggered into evaluated vs unassessed."""
    base = check_conditions(decision, metrics)
    unassessed, clear = [], []
    for row in base["not_triggered"]:
        expl = row.get("explanation") or ""
        if "ausente" in expl or "não avaliada" in expl:
            unassessed.append({**row, "status": "unassessed"})
        else:
            clear.append(row)
    d = decision if isinstance(decision, Decision) else Decision.from_dict(decision)
    return {
        "decision_id": base["decision_id"],
        "status": base["status"],
        "invalidated": base["invalidated"],
        "triggered": base["triggered"],
        "not_triggered": clear,
        "unassessed_conditions": unassessed,
        "rejected": list(d.rejected or []),
        "what": d.what,
        "level_gate": d.level_gate,
        "fidelity": d.fidelity,
    }


def _check_status(ok: bool | None) -> str:
    if ok is False:
        return "fail"
    if ok is None:
        return "unassessed"
    return "pass"


def reevaluate_rejected(decision: Decision | dict, *, triggered: list | None = None,
                        metrics: dict | None = None) -> dict[str, Any]:
    """Surface rejected alternatives that must be re-run after invalidation.

    Does not score, rank, or pick a winner — set-based keep-alive only.
    If a rejected row carries stored ``metrics``, they are echoed next to the
    current metrics for the agent; comparison is informational, never decisive.
    """
    d = decision if isinstance(decision, Decision) else Decision.from_dict(decision)
    rows = []
    for alt in d.rejected or []:
        row = {
            "id": alt.get("id"),
            "reason": alt.get("reason"),
            "action": "re-evaluate",
            "stored_metrics": alt.get("metrics"),
        }
        if metrics is not None and isinstance(alt.get("metrics"), dict):
            row["current_metrics_overlap"] = {
                k: {"stored": alt["metrics"].get(k), "current": metrics.get(k)}
                for k in alt["metrics"] if k in (metrics or {})
            }
        rows.append(row)
    return {
        "decision_id": d.id,
        "what": d.what,
        "rejected_to_reevaluate": rows,
        "triggered_conditions": triggered or [],
        "note": ("set-based: keep alternatives alive; do not auto-pick a weighted "
                 "winner — re-run morph_evaluate / size / compare_alternatives"),
        "reference": GATE_REF,
    }


def _apply_uq(metrics: dict, checks: list, uq: dict | None, *,
              require_uq: bool, uq_metric_use: str) -> tuple[dict, list, dict]:
    """Merge UQ summaries into metrics/checks for the gate (opt-in)."""
    report: dict[str, Any] = {
        "applied": False,
        "require_uq": require_uq,
        "uq_metric_use": uq_metric_use,
    }
    metrics = dict(metrics)
    checks = list(checks)

    if uq is None:
        if require_uq:
            checks.append({
                "key": "uq:required",
                "ok": None,
                "message": "UQ required for this gate but no uq payload supplied — unassessed ≠ pass",
            })
            report["status"] = "unassessed"
            report["reason"] = "uq payload missing"
        return metrics, checks, report

    report["applied"] = True
    report["kind"] = uq.get("kind") or ("sobol" if "indices" in uq else "monte_carlo")
    ustatus = uq.get("status")
    report["status"] = ustatus

    if require_uq and ustatus in (None, "unassessed"):
        checks.append({
            "key": "uq:required",
            "ok": None,
            "message": f"UQ status={ustatus!r} — required UQ unassessed ≠ pass",
        })
    elif require_uq and ustatus == "partial":
        # still usable but flag
        checks.append({
            "key": "uq:partial",
            "ok": True,
            "message": "UQ partial (some failures); summaries that exist are used",
        })

    # Merge MC gate_metrics / percentile aliases into metrics for condition eval
    gm = dict(uq.get("gate_metrics") or {})
    summaries = uq.get("summaries") or {}
    use = uq_metric_use or "p50"
    for mk, sm in summaries.items():
        if isinstance(sm, dict) and sm.get("status") == "ok":
            if use in sm and mk not in metrics:
                gm.setdefault(mk, sm[use])
            elif "mean" in sm and mk not in metrics:
                gm.setdefault(mk, sm["mean"])
    # Sobol: do not invent metric values; only interval/required checks
    for k, v in gm.items():
        if k not in metrics and isinstance(v, (int, float)):
            metrics[k] = float(v)
    report["merged_metrics"] = sorted(gm.keys())

    # Optional interval checks carried on the UQ payload
    interval = uq.get("interval_checks") or []
    if interval:
        from acdt.core.sensitivity.monte_carlo import uq_interval_checks
        checks.extend(uq_interval_checks(uq, interval))

    # Sobol unassessed indices when required
    if require_uq and report["kind"] == "sobol":
        idxs = uq.get("indices") or []
        if not idxs and ustatus != "ok":
            checks.append({
                "key": "uq:sobol",
                "ok": None,
                "message": "Sobol indices unassessed — required UQ ≠ pass",
            })
        for r in idxs:
            if r.get("status") == "unassessed":
                checks.append({
                    "key": f"uq:sobol:{r.get('variable', '?')}",
                    "ok": None,
                    "message": r.get("reason") or "Sobol index unassessed",
                })

    return metrics, checks, report



def level_gate(log: DecisionLog, level: str, metrics: dict,
               *, checks: list[dict] | None = None,
               reopen_invalidated: bool = False,
               require_decisions: bool = True,
               uq: dict | None = None,
               require_uq: bool = False,
               uq_metric_use: str = "p50") -> dict[str, Any]:
    """Evaluate end-of-level gate. Opt-in; does not mutate unless ``reopen_invalidated``.

    ``checks``: optional outstanding verification rows
    ``[{key, ok: bool|None, message?}]`` from size/HQ/perf/… — ``ok=None`` is unassessed.

    ``uq`` (opt-in P7): Monte Carlo / Sobol summary. When ``require_uq`` is True, a missing
    or ``unassessed`` UQ run makes the gate ``unassessed`` (never pass). MC
    ``gate_metrics`` / chosen percentiles are merged into ``metrics`` for condition
    evaluation; optional ``uq["interval_checks"]`` become extra checks. No weighted winner.
    """
    if not level or not str(level).strip():
        raise ValueError("level is required (e.g. N0, N1, N2)")
    level = str(level).strip()
    metrics = dict(metrics or {})
    checks = list(checks or [])
    uq_report: dict[str, Any] = {"applied": False}
    if uq is not None or require_uq:
        metrics, checks, uq_report = _apply_uq(metrics, checks, uq, require_uq=require_uq,
                                               uq_metric_use=uq_metric_use)

    selected = [raw for raw in log.data.get("decisions", []) if _level_match(raw, level)]
    reasons: list[str] = []
    decision_rows: list[dict] = []
    rejected_plan: list[dict] = []
    reopened: list[dict] = []

    any_fail = False
    any_unassessed = False

    if require_decisions and not selected:
        any_unassessed = True
        reasons.append(
            f"nenhuma decisão registada para o nível {level} "
            f"(level_gate/fidelity) — evidência em falta ≠ pass"
        )

    for raw in selected:
        row = _classify_conditions(raw, metrics)
        decision_rows.append(row)
        st = raw.get("status", "closed")

        if st == "open":
            any_fail = True
            reasons.append(
                f"decisão {row['decision_id']} está open — "
                f"reavaliar alternativas rejeitadas antes de fechar {level}"
            )
            # still surface rejected for the agent
            if row["rejected"]:
                rejected_plan.append(reevaluate_rejected(
                    raw, triggered=row["triggered"], metrics=metrics))

        if row["unassessed_conditions"]:
            any_unassessed = True
            miss = ", ".join(
                (u["condition"].get("metric") or "?") for u in row["unassessed_conditions"]
            )
            reasons.append(
                f"decisão {row['decision_id']}: condições com métricas ausentes "
                f"({miss}) → unassessed"
            )

        if row["triggered"]:
            # invalidation fired
            any_fail = True
            trig = "; ".join(t.get("explanation", "") for t in row["triggered"])
            reasons.append(
                f"decisão {row['decision_id']} invalidada: {trig}"
            )
            rejected_plan.append(reevaluate_rejected(
                raw, triggered=row["triggered"], metrics=metrics))
            if reopen_invalidated and st == "closed":
                dec = log.get(row["decision_id"])
                assert dec is not None
                reopen(dec, metrics=metrics,
                       reason=f"gate {level}: condição de invalidação cumprida")
                log.update(dec)
                reopened.append(dec.to_dict())

        if st == "superseded":
            reasons.append(f"decisão {row['decision_id']} superseded (informativo)")

    check_rows = []
    for c in checks:
        key = c.get("key", "?")
        ok = c.get("ok")
        status = _check_status(ok if ok is None or isinstance(ok, bool) else bool(ok))
        check_rows.append({
            "key": key,
            "ok": ok,
            "status": status,
            "message": c.get("message", ""),
        })
        if status == "fail":
            any_fail = True
            reasons.append(f"check '{key}' falhou: {c.get('message', '')}")
        elif status == "unassessed":
            any_unassessed = True
            reasons.append(
                f"check '{key}' unassessed (ok=null) — unknown≠pass: {c.get('message', '')}"
            )

    if any_fail:
        status = "fail"
    elif any_unassessed:
        status = "unassessed"
    else:
        status = "pass"
        reasons.append(
            f"nível {level}: decisões fechadas sem invalidação avaliada; "
            f"checks ok; pronto a fechar (set-based: alternativas rejeitadas preservadas)"
        )

    ready = status == "pass"
    out = {
        "level": level,
        "status": status,
        "ready_to_close": ready,
        "metrics": metrics,
        "decisions": decision_rows,
        "checks": check_rows,
        "rejected_reevaluation": rejected_plan,
        "reopened": reopened,
        "reasons": reasons,
        "n_decisions": len(selected),
        "n_checks": len(check_rows),
        "uq": uq_report,
        "reference": GATE_REF,
        "note": (
            "Gate opt-in (DESIGN_WORKFLOW §7). Não escolhe vencedor ponderado; "
            "não trata unassessed/métrica ausente como pass. "
            "UQ opt-in: require_uq ou uq=…; missing UQ ≠ pass."
        ),
    }
    return out
