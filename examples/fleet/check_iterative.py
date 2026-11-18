# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Run the schema 1.1 examples (PRESSUPOSTO data) and print compact capability/closure/fleet rows."""
import json
from pathlib import Path
from acdt.ai.mission_fleet import mission_fleet_study


def compact(r):
    rows=[]
    for x in r["rows"]:
        n=x["n1"];e=n.get("endurance") or {};cl=n.get("closure") or {}
        byd=n.get("operations_by_dwell") or {}
        rows.append(dict(candidate=x["candidate_id"],status=n["status"],issues=n["issues"][:2],
                         requested_on_station_h=x["sample"]["on_station_h"],derived_max_on_station_h=e.get("derived_max_on_station_h"),
                         endurance_status=e.get("status"),closure=cl.get("status"),
                         closure_history=[(h.get("design_station_h"),h.get("residual_h"),h.get("requested_verified")) for h in cl.get("history",[])],
                         reserve=(n.get("reserve") or {}).get("policy"),dwell_policy=n.get("dwell_policy"),
                         fleet_by_dwell={k:v.get("fleet_required") for k,v in byd.items()},
                         energy_by_dwell_Wh={k:v.get("mission_energy_Wh") for k,v in byd.items()},
                         fuel_by_dwell_kg={k:v.get("mission_fuel_kg") for k,v in byd.items()},
                         n0_bounds=x["n0"]["fleet_required_bounds"],vtol_mass_closure=n.get("vtol_mass_closure"),
                         hybrid={k:(n.get("hybrid_dispatch") or {}).get(k) for k in ("fuel_kg","soc_final","soc_min_seen","ground_recharge_Wh")} if n.get("hybrid_dispatch") else None,
                         unrepresented_phases=[c.get("unrepresented") for c in n.get("checks",[]) if c["name"]=="required_phases_represented"],
                         shared_ground={k:{kk:(v.get("operations") or {}).get(kk) for kk in ("status","utilisation","minimum_stable_counts","fleet_in_cycle_by_type")} for k,v in byd.items() if v.get("ground_activities")}))
    mixed=[dict(sample=s["sample_id"],pareto=s["pareto"],mixes={x["id"]:(x.get("status"),x["metrics"]) for x in s["mixes"]}) for s in (r.get("mixed_fleet") or {}).get("samples",[])]
    return dict(run_id=r.get("run_id"),rows=rows,mixed_fleet=mixed,pareto={c["sample_id"]+"/"+c["coverage_class"]:c["pareto"] for c in r["comparisons"]})


def main():
    root=Path(__file__).resolve().parent
    names=("iter_prop_native_reserve","iter_prop_operational_reserve","iter_vtol","iter_vtol_closure","iter_jet","shared_vtol","mixed_vtol_fixed_wing","hybrid_dispatch")
    print(json.dumps({n:compact(mission_fleet_study(root/(n+".yaml"))) for n in names},indent=2,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":main()
