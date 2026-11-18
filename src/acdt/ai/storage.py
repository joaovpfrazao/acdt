# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Provenance wrapper for common storage checks and explicit aircraft demand adapters."""
import json
from .jet import load_spec
from acdt.domains.aircraft.storage import aircraft_storage
from acdt.core.energy_storage import mapping


def storage_check(spec, source_kind="direct", result=None, reserve_fraction=None, record=True):
    """Check capacity/mass/volume, not full mission simulation or hybrid scheduling.

    spec: {storage: {fuel?, battery?, assumption_sources?}, demand?: {...}}.
    direct needs explicit trip and reserve in kg / terminal Wh. Other source_kind:
    jet_size, vtol_size, mission; result is an existing producer result (no rerun).
    mission requires explicit reserve_fraction. Do not add a second producer reserve.
    """
    from . import registry
    inputs = load_spec(spec)
    mapping(inputs, {"storage", "demand"}, "storage check spec")
    if "storage" not in inputs: raise ValueError("storage mapping required (may be incomplete)")
    args = {"spec": inputs, "source_kind": source_kind, "result": result, "reserve_fraction": reserve_fraction}
    run = registry.new_run("storage_check", "energy-storage", args) if record else None
    try:
        out = aircraft_storage(inputs["storage"], source_kind, result, reserve_fraction, inputs.get("demand"))
        if run:
            out["run_id"] = run.id
            path = run.path/"result.json"
            out["files"] = {"result": str(path), "run": str(run.path/"run.json")}
            path.write_text(json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
            run.record["assumptions"] = out["assumptions"]
            state = out["storage_feasible"]
            run.finish(outputs={k: out[k] for k in ("storage_feasible", "status", "issues", "unassessed")},
                       files=out["files"], status="done" if state is True else ("infeasible" if state is False else "unassessed"))
        return out
    except Exception as exc:
        if run: run.finish(status="error", error=str(exc))
        raise
