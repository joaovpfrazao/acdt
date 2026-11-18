# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Recorded JSON/YAML entry for shared onboard coupling across native aircraft paths."""
import json
from pathlib import Path
from copy import deepcopy
from .jet import load_spec
from . import registry
from .toolkit import clean


def onboard_size(spec, record=True):
    """Run opt-in payload/electrical coupling; partial/unassessed is never full pass."""
    inputs=deepcopy(load_spec(spec))
    base=Path(spec).resolve().parent if isinstance(spec,(str,Path)) else Path.cwd()
    for key in ("aircraft","mission"):
        if isinstance(inputs.get(key),str): inputs[key]=load_spec(base/inputs[key])
    run=registry.new_run("onboard_size",str(inputs.get("model","onboard")),{"spec":inputs}) if record else None
    try:
        from acdt.domains.aircraft.onboard import size_onboard
        out=clean(size_onboard(inputs))
        if run:
            out["run_id"]=run.id
            path=run.path/"result.json"
            out["files"]={"result":str(path),"run":str(run.path/"run.json")}
            path.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
            run.record["assumptions"]=out["assumptions"]
            state="done" if out["combined_checks_passed"] is True else ("infeasible" if out["combined_checks_passed"] is False else "partial")
            run.finish(outputs={"status":out["status"],"mass_coupled":out["mass_coupled"],"energy_coupled":out["energy_coupled"],
                                "combined_checks_passed":out["combined_checks_passed"],"issues":out["issues"]},files=out["files"],status=state)
        return out
    except Exception as exc:
        if run: run.finish(status="error",error=str(exc))
        raise
