# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in cross-aircraft onboard adapter: real native sizing, not metadata only.

Common accounting/electrical identities: core.onboard (MIL-E-7016F/Moir &
Seabridge; NIST 2008). Native mass/Breguet/energy models and their citations
remain in weights, jet.sizing, vtol.size. No inferred accessory engine model.
"""
from copy import deepcopy
from acdt.core.onboard import analyse_onboard, validate_onboard
from acdt.core.energy_storage import mapping, number, aggregate


def size_onboard(recipe, native_out=None):
    """Versioned orchestrator using prop sizing.run / size_jet / size_vtol.

    Common `onboard` inputs are incremental to the explicitly supplied baseline,
    or declared already included. No mass allowance is subtracted from a statistical
    regression, no storage inventory is summed twice, no VTOL MTOW increment.
    Hybrid is explicitly accounting-only: fixed allocations do not create dispatch.
    ``native_out`` (internal, optional dict) receives the live prop sizing result
    for forward capability searches; it never changes the returned JSON.
    """
    mapping(recipe,{"schema_version","model","aircraft","onboard","duration","mass_ledger","integration","mission","closure"},"onboard recipe")
    if recipe.get("schema_version")!="1.0": raise ValueError("recipe.schema_version must be 1.0")
    model=recipe.get("model"); d=deepcopy(recipe.get("aircraft")); s=recipe.get("onboard")
    if not isinstance(d,dict): raise ValueError("aircraft must be resolved native input mapping")
    validate_onboard(s)
    if model not in ("prop","jet","vtol","hybrid"): raise ValueError("model must be prop/jet/vtol/hybrid")
    duration=recipe.get("duration",{})
    mapping(duration,{"precruise_s","postcruise_s","accounting_s","source"},"onboard duration")
    if duration:
        if not isinstance(duration.get("source"),str) or not duration["source"].strip(): raise ValueError("duration source required")
        for k in ("precruise_s","postcruise_s","accounting_s"):
            if k in duration: number(k,duration[k])
    ledger=recipe.get("mass_ledger",{})
    mapping(ledger,{"remaining_nonbattery_mass_kg","source"},"mass_ledger")
    if ledger:
        if not isinstance(ledger.get("source"),str) or not ledger["source"].strip(): raise ValueError("mass_ledger source required")
        number("remaining_nonbattery_mass_kg",ledger.get("remaining_nonbattery_mass_kg"))
    if model!="hybrid" and "accounting_s" in duration: raise ValueError("accounting_s is for hybrid accounting only; native aircraft determine mission duration")
    if model!="vtol" and ledger: raise ValueError("mass_ledger is only for supplied inclusive VTOL MTOW")
    if model!="prop" and recipe.get("mission"): raise ValueError("common dynamic pointmass coupling is currently prop only, not jet/VTOL/hybrid")
    prop_spec=None
    if model=="prop":
        from .mission import MissionSpec
        if "propulsion_type" not in d.get("requirements",{}): raise ValueError("prop adapter requires explicit native propulsion_type")
        if "storage" in d: raise ValueError("prop storage must use existing storage_check with mission demand; not ignored by sizing.run")
        prop_spec=MissionSpec.from_dict(d)
        if prop_spec.propulsion_kind not in ("electric","piston_prop","turboprop"): raise ValueError("prop adapter does not substitute GA equations for jets/hybrids")
        target="electric" if prop_spec.propulsion_kind=="electric" else "prop"
    else: target=model
    if target in ("electric","vtol") and duration: raise ValueError("electric prop native model determines its own takeoff/climb/leg duration")
    a=analyse_onboard(s,target,duration.get("accounting_s"))
    out=dict(schema_version="1.0",level="L0",model=model,inputs=deepcopy(recipe),resolved_aircraft=None,
             status="unassessed",aircraft_result=None,onboard=a,mass_coupled=False,energy_coupled=False,
             assumptions=list(a["assumptions"]),checks=[],issues=[],
             limitations=["Opt-in native sizing adapter, not a global multidisciplinary optimizer or new dynamic jet/VTOL simulator.",
                          "Included mass is a sourced user ownership declaration plus bounds checks, not independent verification of external inventories.",
                          "Incremental loads must be additional to the baseline/deck; no automatic subtraction of implicit avionics/accessory allowances."])
    checks=out["checks"]
    def check(name,passed,**kw): checks.append(dict(name=name,passed=passed,**kw))
    if model=="hybrid":
        out["issues"].append("hybrid_propulsion_dispatch_unimplemented")
        _finish(out); return out
    if a["missing_models"]:
        out["issues"]+=a["missing_models"]
        _finish(out); return out  # NEVER run with unmodelled generator electricity for free
    rate=a["fuel_flow_kg_s"]
    active_thermal=target in ("prop","jet") and any(x["terminal_peak_W"]>0 for x in a["sources"])
    if active_thermal and not all(k in duration for k in ("precruise_s","postcruise_s")):
        out["issues"].append("onboard_noncruise_durations_unassessed")
        _finish(out); return out
    inc_payload=a["incremental_payload_kg"]; inc_eq=a["incremental_equipment_kg"]
    items=s["items"]
    if model=="vtol":
        if any(i["mass_accounting"]!="included" or i.get("included_in")!="mtow" for i in items):
            raise ValueError("VTOL mass_kg is supplied inclusive MTOW: every onboard item must be included_in mtow; never silently add mass")
        closing="closure" in d
        if closing:
            if ledger: raise ValueError("VTOL closure solves MTOW from components: do not also give mass_ledger")
            if "mass_kg" in d: raise ValueError("VTOL closure solves MTOW: do not also supply mass_kg")
            if d["closure"].get("fixed_items"): raise ValueError("onboard owns the VTOL fixed items; do not also give closure.fixed_items")
            d["closure"]["fixed_items"]=[dict(id=i["id"],role=i["role"],mass_kg=i["mass_kg"],source=i["source"]) for i in items]
        else: number("VTOL MTOW",d.get("mass_kg"),positive=True)
        e=d.setdefault("electric",{})
        if e.get("systems_power_W",0) or "systems_peak_power_W" in e: raise ValueError("legacy VTOL hotel loads overlap common onboard loads")
        e["systems_power_W"]=a["main_battery_average_W"]
        e["systems_peak_power_W"]=a["main_battery_peak_W"]
        from .vtol.size import size_vtol
        r=size_vtol(d)
        if closing:
            dt=r["t_total_s"] if r["converged"] else None
            check("VTOL_mass_closure",r["converged"],status=r["closure"]["status"],mtow_kg=r["mtow_kg"],
                  residual_kg=r["closure"]["solver"]["residual_kg"],
                  note="MTOW solved from onboard items + component build-up + native battery")
            out["limitations"].append("VTOL opt-in component mass closure: payload/onboard items change MTOW; NDARC regressions extrapolated to small electric VTOL (flagged); airframe/booms/mechanisms are sourced fractions or masses.")
            out["mass_coupled"]=bool(r["converged"])
        else:
            dt=r["t_total_s"]
            check("VTOL_included_item_mass",d["mass_kg"]>=a["item_mass_kg"],margin_kg=d["mass_kg"]-a["item_mass_kg"])
            remaining=ledger.get("remaining_nonbattery_mass_kg")
            margin=d["mass_kg"]-a["item_mass_kg"]-r["battery_mass_kg"]-remaining if remaining is not None else None
            check("VTOL_inclusive_mass_budget",margin>=0 if margin is not None else None,margin_kg=margin,
                  note="MTOW unchanged; onboard items + sized propulsion battery + explicit remaining nonbattery mass")
            out["limitations"].append("VTOL fixed supplied MTOW, no automatic structural/payload/battery mass closure; changing payload changes allocation margin, not MTOW.")
            out["mass_coupled"]=True
    elif model=="jet":
        if "auxiliary" in d: raise ValueError("do not combine native auxiliary hook with common onboard accounting")
        for i in items:
            if i["mass_accounting"]=="included" and i.get("included_in")=="mtow": raise ValueError("jet mass is solved; declare payload or empty owner, not MTOW")
        baseline_payload=d["payload_kg"]
        d["payload_kg"]+=inc_payload
        w=d.get("weights",{"mode":"statistical"})
        extra=inc_eq
        if w.get("mode")=="components":
            names={i["name"] for i in w.get("items",[])}
            for i in items:
                if i["mass_accounting"]=="incremental" and i["id"] in names: raise ValueError("onboard incremental item already named in jet component inventory")
                if i["role"]=="equipment" and i["mass_accounting"]=="incremental":
                    key="onboard:"+i["id"]
                    if key in w.get("additional_required_groups",[]): raise ValueError("duplicate onboard weight coverage")
                    w.setdefault("additional_required_groups",[]).append(key)
                    w.setdefault("items",[]).append(dict(name=i["id"],covers=[key],method="supplied",mass_kg=i["mass_kg"],source=i["source"]))
            extra=0.
            d["weights"]=w
        d["auxiliary"]=dict(fuel_flow_kg_s=rate,thrust_penalty_N=a["thrust_penalty_N"],
                            pre_duration_s=duration.get("precruise_s",0),post_duration_s=duration.get("postcruise_s",0),empty_mass_kg=extra)
        from .jet.sizing import size_jet
        r=size_jet(d)
        from acdt.core.atmosphere import isa
        dt=d["range_m"]/(d["mach"]*isa(d["altitude_m"]).a)+duration.get("precruise_s",0)+duration.get("postcruise_s",0)
        check("included_payload_mass",sum(i["mass_kg"] for i in items if i.get("included_in")=="payload")<=baseline_payload)
        if r["converged"]:
            check("included_empty_mass",sum(i["mass_kg"] for i in items if i.get("included_in")=="empty")<=r["weights"]["empty_mass_kg"]-inc_eq)
        else: check("included_empty_mass",None)
        if r["converged"]:
            peak=sum(x.get("peak_thrust_penalty_N",0.) for x in a["sources"])
            margin=r["turbofan_per_engine"]["thrust_installed_N"]*d["n_engines"]-peak-r["cruise"]["max_drag_N"]
            check("jet_peak_extraction_cruise_thrust",margin>=0,margin_N=margin)
        if "performance" in r:
            if any(x["kind"]=="generator" and x["terminal_peak_W"]>0 for x in a["sources"]):
                r["performance"].update(status="unassessed_onboard_extraction",requested_checks_passed=None,ground=None,climb_points=[])
                if "onboard_takeoff_OEI_extraction_unassessed" not in r["performance"]["issues"]:
                    r["performance"]["issues"].append("onboard_takeoff_OEI_extraction_unassessed")
                r["performance"]["checks"]=[]
                r["combined_requested_checks_passed"]=False
            check("native_requested_performance",r["performance"]["requested_checks_passed"])
        out["mass_coupled"]=r["converged"]
        out["limitations"].append("Jet accessory fuel integrated in cruise and explicit pre/post phase time; thrust debit is a user incremental cruise coefficient. No takeoff/OEI extraction/dispatch model.")
    else:
        if prop_spec.systems: raise ValueError("common onboard opt-in cannot also select legacy systems masses/loads; provide one owned inventory")
        p=prop_spec.assumptions["propulsion"]
        keys=("systems_power_W","onboard_power_W","auxiliary_fuel_flow_kg_s","auxiliary_shaft_W","auxiliary_pre_s","auxiliary_post_s")
        if any(p.get(k,0) for k in keys): raise ValueError("legacy/native hotel/extraction inputs overlap common onboard inputs")
        if any(x.get("peak_shaft_extraction_W",0) for x in a["sources"]) and p.get("propeller"):
            out["issues"].append("fixed_pitch_generator_extraction_unimplemented"); _finish(out); return out
        if prop_spec.assumptions.get("assembly"):
            out["issues"].append("onboard_assembly_mass_feedback_unassessed_use_independent_integration_check"); _finish(out); return out
        for i in items:
            if i["mass_accounting"]=="included" and i.get("included_in")=="mtow": raise ValueError("prop mass is solved, not supplied inclusive MTOW")
        existing={i.get("name") for i in prop_spec.assumptions["weights"].get("components",{}).get("items",[])}
        if any(i["mass_accounting"]=="incremental" and i["id"] in existing for i in items):
            raise ValueError("incremental onboard item already named in native component inventory")
        baseline_payload=prop_spec.requirements.value("payload_mass",0.)
        if inc_payload:
            d.setdefault("requirements",{})["payload_mass"]={"min":baseline_payload+inc_payload,"unit":"kg"}
        aa=d.setdefault("assumptions",{}); pa=aa.setdefault("propulsion",{})
        pa.update(onboard_power_W=a["main_battery_average_W"],auxiliary_fuel_flow_kg_s=rate,
                  auxiliary_shaft_W=a["shaft_extraction_W"],auxiliary_pre_s=duration.get("precruise_s",0),auxiliary_post_s=duration.get("postcruise_s",0))
        aa.setdefault("weights",{})["fixed_mass_kg"]=prop_spec.assumptions["weights"]["fixed_mass_kg"]+inc_eq
        from .mission import MissionSpec
        from .sizing import run
        from acdt.core.pipeline import InfeasibleError
        try:
            res=run(MissionSpec.from_dict(d),strict=False)
        except InfeasibleError as exc:
            out["status"]="infeasible"
            out["issues"].append(str(exc)); check("native_sizing_feasible",False)
            _finish(out); return out
        if native_out is not None: native_out["res"]=res
        sz=res.sizing
        r=dict(converged=bool(sz and sz.converged),feasible=bool(res.feasible),mtow_kg=sz.W0 if sz and sz.converged else None,
               empty_mass_kg=sz.We+res.spec.assumptions["weights"]["fixed_mass_kg"] if sz and sz.converged else None,
               fuel_or_battery_mass_kg=sz.Wf if sz and sz.converged else None,
               energy_nominal_Wh=sz.energy_J/3600 if sz and sz.energy_J is not None else None,
               scope="existing sizing.run L0/L1 result, not a rerun of all phase-2/HQ/report stages")
        check("included_payload_mass",sum(i["mass_kg"] for i in items if i.get("included_in")=="payload")<=baseline_payload)
        check("included_empty_mass",sum(i["mass_kg"] for i in items if i.get("included_in")=="empty")<=r["empty_mass_kg"]-inc_eq if r["empty_mass_kg"] is not None else None)
        dt=sum(l.value/l.V if l.kind=="cruise" else l.value for l in (res.legs or []))
        if target=="electric" and r["converged"]:
            from .flightsim.pointmass import Plant
            plant=Plant.from_sizing(res)
            r["full_rating_battery_power_W"]=plant.propulsion(res.legs[0].V,res.legs[0].altitude,1.)[1]
            r["power_scope"]="existing native propulsion model at full rating and mission speed/altitude, with average main hotel; not transient hardware verification"
            from .performance import PerfModel, takeoff_climb_energy
            pm=PerfModel.from_result(res)
            alt=max([l.altitude for l in res.legs]+[0.])
            tc=takeoff_climb_energy(pm,sz.W0,alt)
            dt+=60+tc["t_climb"]
            check("main_pack_combined_peak_rating",None,note="prop main-pack energy coupled, combined propulsion + hotel peak selection not implemented")
        else: dt+=duration.get("precruise_s",0)+duration.get("postcruise_s",0)
        if any(x.get("peak_shaft_extraction_W",0) for x in a["sources"]) and r["converged"]:
            from .performance import PerfModel
            from acdt import G0
            pm=PerfModel.from_result(res); l=res.legs[0]
            from acdt.core.atmosphere import isa
            margin=pm.power_avail(l.altitude,pm.eta_cruise)-pm.drag(sz.W0*G0,l.V,isa(l.altitude).rho)*l.V
            check("generator_cruise_shaft_headroom",margin>=0,margin_propulsive_W=margin)
            peak=sum(x.get("peak_shaft_extraction_W",0.) for x in a["sources"])
            peak_margin=margin+(a["shaft_extraction_W"]-peak)*pm.eta_cruise
            check("generator_peak_cruise_shaft_headroom",peak_margin>=0,margin_propulsive_W=peak_margin)
        if recipe.get("mission") and r["converged"]:
            from .flightsim.pointmass import simulate_pointmass_mission
            r["mission_pointmass"]=simulate_pointmass_mission(recipe["mission"],res=res)
            check("requested_pointmass_completed",not r["mission_pointmass"]["aborted"],note="completion only; no 6-DOF or all-constraints validation")
            out["onboard_pointmass"]=analyse_onboard(s,target,r["mission_pointmass"]["total_time_min"]*60)
            check("pointmass_onboard_capacity",out["onboard_pointmass"]["requested_checks_passed"])
            out["limitations"].append("Optional pointmass is a forward check, not a second sizing closure; dedicated-battery capacity also screened over its flown time.")
        d=dict(d,assumptions=deepcopy(res.spec.assumptions))
        out["mass_coupled"]=r["converged"]
        out["limitations"].append("Prop thermal: constant-efficiency propeller only, explicit shaft BSFC/extraction; no generator failure/OEI or 6-DOF extraction coupling. Native reserves applied once. Noncruise fuel phases use supplied durations, not a full trajectory mass closure.")
    out["resolved_aircraft"]=d; out["aircraft_result"]=r
    if r.get("converged") is False: dt=None
    if "storage" in r: check("native_requested_storage",r["storage"]["storage_feasible"])
    out["onboard"]=analyse_onboard(s,target,dt)
    out["energy_coupled"]=bool(r.get("converged",True))
    if r.get("converged") is False: out["status"]="not_converged"
    if out["energy_coupled"]: out["status"]="evaluated"
    check("native_sizing_feasible",r["feasible"])
    if recipe.get("integration"):
        _integration(out,recipe["integration"],items)
    if recipe.get("closure"):
        _closure(out, recipe["closure"], items, s)
    _finish(out)
    return out


def _integration(out, spec, items):
    """Reuse existing geometry/FOV checker without inventing positions/usable volume/CG."""
    mapping(spec,{"assembly","placements","constraints","base","source"},"onboard integration")
    if not isinstance(spec.get("source"),str) or not spec["source"].strip(): raise ValueError("integration source required")
    places=spec.get("placements",{})
    if not isinstance(places,dict) or set(places)-{i["id"] for i in items}: raise ValueError("placement keys must identify onboard items")
    if set(places)!={i["id"] for i in items}:
        out["issues"].append("incomplete_onboard_placements"); return
    if spec.get("base"):
        number("integration base mass",spec["base"].get("mass_kg"),positive=True)
        result=out["aircraft_result"]
        mtow=result.get("mtow_kg",result.get("mass_kg"))
        if mtow is None or abs(spec["base"]["mass_kg"]+sum(i["mass_kg"] for i in items)-mtow)>max(.01,1e-6*mtow):
            raise ValueError("integration remainder base mass must reconcile with sized/supplied MTOW and owned items")
    rows=[]
    for i in items:
        p=deepcopy(places[i["id"]])
        if any(k in p for k in ("name","mass_kg","power_w","heat_w")): raise ValueError("placement cannot add/redefine owned mass or electrical load")
        rows.append(dict(p,name=i["id"],mass_kg=i["mass_kg"]))
    from .assembly.integration import check
    spatial=check(spec["assembly"],rows,spec.get("constraints"),spec.get("base"),place_unpositioned=True)
    out["integration"]=spatial
    # Independent geometry check is NOT assembly feedback or aircraft-wide CG
    # when the explicit remainder mass/CG is absent.
    for c in out["onboard"]["checks"]:
        if c["name"]=="CG":
            c["passed"]=spatial["ok"] if spec.get("base") and any(x.get("type")=="cg_range" for x in spec.get("constraints",[])) else None
        if c["name"]=="FOV_3D":
            c["passed"]=spatial["ok"] if any(p.get("fov") for p in places.values()) else None
    out["checks"].append(dict(name="independent_integration",passed=spatial["ok"]))


def _closure(out, spec, items, onboard_block):
    """Opt-in L0 thermal/CG/spatial/FOV screens with open primitives (core.onboard_closure)."""
    from acdt.core.onboard_closure import analyse_closure
    report = analyse_closure(onboard_block, spec, analyse=out.get("onboard"))
    out["closure"] = report
    # Prefer closure assessment for shared check names when actually assessed.
    by = {c["name"]: c for c in report["checks"]}
    for c in out["onboard"]["checks"]:
        if c["name"] == "CG" and "CG" in by and by["CG"]["passed"] is not None:
            c["passed"] = by["CG"]["passed"]
            c.update({k: by["CG"][k] for k in by["CG"] if k not in ("name", "passed")})
        if c["name"] == "FOV_3D" and "FOV_3D" in by and by["FOV_3D"]["passed"] is not None:
            c["passed"] = by["FOV_3D"]["passed"]
            c.update({k: by["FOV_3D"][k] for k in by["FOV_3D"] if k not in ("name", "passed")})
        if c["name"] == "declared_heat" and "thermal_balance" in by and by["thermal_balance"]["passed"] is not None:
            # Keep scalar declared_heat; thermal_balance is the richer screen.
            pass
    out["checks"].append(dict(name="onboard_closure", passed=report["requested_checks_passed"]))
    out["assumptions"] += report["assumptions"]
    out["limitations"] += report["limitations"]
    for c in report["checks"]:
        if c["name"] not in {x["name"] for x in out["onboard"]["checks"]}:
            out["onboard"]["checks"].append(c)



def _finish(out):
    out["onboard"]["requested_checks_passed"]=aggregate(c["passed"] for c in out["onboard"]["checks"])
    values=[c["passed"] for c in out["checks"]]+[out["onboard"]["requested_checks_passed"]]
    if out["aircraft_result"] is None: values.append(None)
    out["combined_checks_passed"]=aggregate(values)
    out["unassessed_checks"]=[c["name"] for c in out["checks"]+out["onboard"]["checks"] if c["passed"] is None]
    out["issues"] += [c["name"] for c in out["checks"] if c["passed"] is False]
    out["issues"] += [c["name"] for c in out["onboard"]["checks"] if c["passed"] is False]
