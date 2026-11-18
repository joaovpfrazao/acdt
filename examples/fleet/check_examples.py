# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Recorded PRESSUPOSTO cases; model phase classes are NOT universally comparable."""
from copy import deepcopy
import json
from pathlib import Path
from acdt.ai.jet import load_spec
from acdt.ai.mission_fleet import mission_fleet_study


def compact(result):
    return dict(run_id=result.get("run_id"),rows=[dict(candidate=r["candidate_id"],
                status=r["n1"]["status"],n0_bounds=r["n0"]["fleet_required_bounds"],n0_fixed_dwell_bounds=r["n0"]["fixed_mission_fleet_required_bounds"],
                coverage=r["n1"].get("coverage_class"),metrics=r["n1"]["metrics"])
                for r in result["rows"]])


def main():
    root=Path(__file__).resolve().parent
    out={name:compact(mission_fleet_study(root/(name+".yaml"))) for name in ("prop_electric","jet","vtol")}
    source=load_spec(root/"prop_electric.yaml");source["candidates"]=source["candidates"][:1]
    base=mission_fleet_study(source)
    hotel=deepcopy(source)
    hotel["candidates"][0]["recipe"]["onboard"]["loads"][0].update(power_W=300,peak_W=400)
    fast=deepcopy(source);fast["candidates"][0]["turnaround"]["average_input_W"]=1000
    out["electric_sensitivity"]={"base":compact(base),"hotel_300W_duty_half":compact(mission_fleet_study(hotel)),"charger_1000W":compact(mission_fleet_study(fast))}
    print(json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":main()
