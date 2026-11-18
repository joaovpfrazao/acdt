# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Recorded mission–propulsion–fleet feedback, evaluating explicit candidates only."""
import json
from pathlib import Path
from copy import deepcopy
from .jet import load_spec
from .toolkit import clean
from . import registry


def mission_fleet_study(spec,record=True):
    inputs=deepcopy(load_spec(spec))
    base=Path(spec).resolve().parent if isinstance(spec,(str,Path)) else Path.cwd()
    if not isinstance(inputs,dict) or not isinstance(inputs.get("candidates"),list):
        raise ValueError("study requires a candidates list")
    for c in inputs["candidates"]:
        if not isinstance(c,dict): raise ValueError("candidate mapping required")
        if isinstance(c.get("recipe"),str):
            path=base/c["recipe"];c["recipe"]=deepcopy(load_spec(path));rb=path.parent
        else:rb=base
        r=c.get("recipe",{})
        if not isinstance(r,dict): raise ValueError("candidate recipe must be a mapping or filename")
        if isinstance(r.get("aircraft"),str):r["aircraft"]=deepcopy(load_spec(rb/r["aircraft"]))
    run=registry.new_run("mission_fleet_study","mission-fleet",{"spec":inputs}) if record else None
    try:
        from acdt.domains.aircraft.mission_fleet import evaluate_study
        out=clean(evaluate_study(inputs))
        if run:
            out["run_id"]=run.id
            out["files"]={"result":str(run.path/"result.json"),"run":str(run.path/"run.json")}
            Path(out["files"]["result"]).write_text(json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
            run.record["assumptions"]=out["assumptions"]
            counts={s:sum(r["n1"]["status"]==s for r in out["rows"]) for s in ("assessed_in_scope","infeasible","unassessed")}
            run.finish(outputs={"case_status_counts":counts,"pareto_by_sample":{c["sample_id"]+"/"+c["coverage_class"]:c["pareto"] for c in out["comparisons"]}},files=out["files"],status="done" if not counts["unassessed"] else "partial")
        return out
    except Exception as exc:
        if run:run.finish(status="error",error=str(exc))
        raise
