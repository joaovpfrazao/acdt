# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""N0 envelope → supplied N1 candidate → mission/ground service → fleet feedback.

Uses existing onboard sizing, pointmass (Anderson 1999 Ch.5 / Raymer 2018
Ch.17), jet differential Breguet, VTOL momentum/segments, Ha 2010 operations,
Deb 2001 Pareto comparison. Not architecture search, maximum-endurance solve,
mixed-fleet scheduling or a converged multidisciplinary/fleet fixed point.
"""
from copy import deepcopy
from acdt.core.energy_storage import mapping, number, aggregate
from acdt.core.concept import ops, tradeoff
from acdt.core.concept.fleet_feedback import text, interval, fleet, turnaround
from .onboard import size_onboard
from . import mission_endurance as EN
from acdt.core.concept import ground_queue as GQ

METRICS={"fleet_required","fleet_mtow_kg","ground_turnaround_h","mission_energy_Wh","mission_fuel_kg","derived_max_on_station_h"}
VERSIONS=("1.0","1.1","1.2")
SPATIAL={"CG","FOV_3D","allocated_volume","declared_heat","thermal_balance","spatial_fit"}


def validate_study(spec):
    mapping(spec,{"schema_version","source","mission","operations","candidates","objectives","mixed_fleet"},"mission fleet study")
    if spec.get("schema_version") not in VERSIONS: raise ValueError("study.schema_version must be 1.0, 1.1 or 1.2")
    v11=spec["schema_version"] in ("1.1","1.2");v12=spec["schema_version"]=="1.2"
    text(spec.get("source"),"study.source")
    m=spec.get("mission")
    mapping(m,{"envelope","samples","source"}|({"required_phases"} if v12 else set()),"mission")
    if "required_phases" in m:
        from .mission_phases import CANONICAL
        rp=m["required_phases"]
        if not isinstance(rp,list) or not rp or set(rp)-set(CANONICAL) or len(set(rp))!=len(rp): raise ValueError("mission.required_phases: distinct names from "+str(CANONICAL))
    text(m.get("source"),"mission.source")
    e=m.get("envelope")
    mapping(e,{"distance_km","speed_m_s","on_station_h","payload_kg"},"mission envelope")
    for k in ("distance_km","speed_m_s","on_station_h","payload_kg"): interval(e.get(k),k,k=="speed_m_s")
    samples=m.get("samples")
    if not isinstance(samples,list) or not 1<=len(samples)<=32: raise ValueError("provide 1..32 explicit mission samples, no hidden grid")
    ids=set()
    for s in samples:
        mapping(s,{"id","distance_km","speed_m_s","on_station_h","payload_kg","source"},"mission sample")
        text(s.get("id"),"sample.id");text(s.get("source"),"sample.source")
        if s["id"] in ids: raise ValueError("duplicate sample id")
        ids.add(s["id"])
        for k,b in e.items():
            x=number(k,s.get(k),positive=k=="speed_m_s")
            if not b[0]<=x<=b[1]: raise ValueError("sample outside supplied "+k+" envelope")
    o=spec.get("operations")
    mapping(o,{"availability","n_stations","handoff_overlap_h","reserve_h","confidence","source","common_sim"}|({"operational_reserve","dwell_policy"} if v11 else set())|({"ground_resources"} if v12 else set()),"operations")
    text(o.get("source"),"operations.source")
    number("reserve_h",o.get("reserve_h"))
    if "operational_reserve" in o:
        r=o["operational_reserve"]
        mapping(r,{"time_h","divert_km","native_reserve","source"},"operational_reserve")
        text(r.get("source"),"operational_reserve.source")
        number("operational_reserve.time_h",r.get("time_h")); number("operational_reserve.divert_km",r.get("divert_km"))
        if r.get("native_reserve")!="replace": raise ValueError("operational_reserve.native_reserve must be 'replace' (native fraction zeroed so reserve counts once)")
        if o["reserve_h"]: raise ValueError("give operational_reserve OR legacy reserve_h, not both")
    if o.get("dwell_policy","requested") not in ("requested","derived_max"): raise ValueError("dwell_policy must be requested or derived_max")
    pools=GQ.validate_pools(o["ground_resources"]) if "ground_resources" in o else None
    fleet(1.,0.,0.,o) # validate availability/count/confidence, even for empty/infeasible scenarios
    cs=spec.get("candidates")
    if not isinstance(cs,list) or not 1<=len(cs)<=32 or len(cs)*len(samples)>128: raise ValueError("provide <=128 explicit candidate/sample evaluations")
    ids=set()
    for c in cs:
        mapping(c,{"id","architecture","source","n0","recipe","turnaround","pack_power","common_sim"}|({"endurance"} if v11 else set())|({"ground_process"} if v12 else set()),"candidate")
        if "ground_process" in c:
            if "turnaround" in c: raise ValueError("give turnaround (dedicated/supplied) OR ground_process (shared resources), not both")
            GQ.validate_process(c["ground_process"],pools or {})
        if "endurance" in c: EN.settings(c["endurance"])
        for k in ("id","architecture","source"): text(c.get(k),"candidate."+k)
        if c["id"] in ids: raise ValueError("duplicate candidate id")
        ids.add(c["id"])
        mapping(c.get("n0"),{"endurance_h","turnaround_h","source"},"candidate.n0")
        text(c["n0"].get("source"),"n0.source")
        interval(c["n0"].get("endurance_h"),"n0.endurance_h")
        interval(c["n0"].get("turnaround_h"),"n0.turnaround_h")
        if "recipe" in c and not isinstance(c["recipe"],dict): raise ValueError("resolved recipe mapping required")
        if "pack_power" in c:
            p=c["pack_power"]
            mapping(p,{"continuous_C","peak_C","source"},"pack_power")
            text(p.get("source"),"pack_power.source")
            number("continuous_C",p.get("continuous_C"),positive=True)
            number("peak_C",p.get("peak_C"),positive=True)
            if p["peak_C"]<p["continuous_C"]: raise ValueError("peak_C below continuous_C")
    if "mixed_fleet" in spec:
        if not v12: raise ValueError("mixed_fleet requires schema_version 1.2")
        from .mission_fleet_mixed import validate_mixed
        validate_mixed(spec["mixed_fleet"],[c["id"] for c in cs],o)
    obj=spec.get("objectives")
    if not isinstance(obj,dict) or not obj or set(obj)-METRICS or any(v not in ("min","max") for v in obj.values()): raise ValueError("explicit supported objectives min|max required; no default weighted winner")


def _reserve_time_h(o,s):
    """Operational reserve as time at sample speed; divert distance flown at the same speed (PRESSUPOSTO)."""
    r=o.get("operational_reserve")
    if not r: return o["reserve_h"]
    return r["time_h"]+r["divert_km"]/(s["speed_m_s"]*3.6)


def _n0(c,s,o):
    tr=ops.transit(s["distance_km"],s["speed_m_s"])
    off=tr["t_round_trip_h"]
    corners=[]
    for E in sorted(set(c["n0"]["endurance_h"])):
        for g in sorted(set(c["n0"]["turnaround_h"])):
            station=E-off-_reserve_time_h(o,s)
            r=fleet(max(0.,station),off,g,o)
            ok=r["cycle"]["feasible"] and station+1e-10>=s["on_station_h"]
            fixed=fleet(s["on_station_h"],off,g,o)
            corners.append(dict(endurance_h=E,turnaround_h=g,available_on_station_h=station,
                                meets_station_duration=ok,operations=r,requested_mission_operations=fixed))
    counts=[x["operations"]["fleet_for_confidence"] if "confidence" in o else x["operations"]["fleet_expected"] for x in corners if x["meets_station_duration"]]
    counts=[n for n in counts if n is not None]
    fixed_counts=[x["requested_mission_operations"]["fleet_for_confidence"] if "confidence" in o else x["requested_mission_operations"]["fleet_expected"] for x in corners if x["meets_station_duration"]]
    fixed_counts=[n for n in fixed_counts if n is not None]
    return dict(status="provisional_supplied_envelope",source=c["n0"]["source"],corners=corners,
                fixed_mission_fleet_required_bounds=[min(fixed_counts),max(fixed_counts)] if fixed_counts else None,
                fleet_required_bounds=[min(counts),max(counts)] if counts else None,
                bounds_are_conditional_on_assessed_feasible_corners=True,
                all_corners_assessed_and_meet_station=all(x["meets_station_duration"] and (x["operations"]["fleet_for_confidence"] if "confidence" in o else x["operations"]["fleet_expected"]) is not None for x in corners),
                note="bounds of assessed feasible corners only; not probability distribution, architecture selection or validated endurance; infeasible/unassessed corners retained")


def _bind(recipe,s,station_h=None,reserve=None,ledger=None):
    """Bind sample to native inputs. station_h = DESIGN station time (default requested);
    reserve = explicit operational reserve, added once to the SIZING mission while the
    native reserve fraction is zeroed (recorded in ledger)."""
    r=deepcopy(recipe)
    ledger=[] if ledger is None else ledger
    station=s["on_station_h"] if station_h is None else station_h
    extra_m=(reserve["time_h"]*3600*s["speed_m_s"]+reserve["divert_km"]*1000) if reserve else 0.
    if not isinstance(r,dict): raise ValueError("resolved onboard recipe mapping required")
    d=r.get("aircraft")
    if not isinstance(d,dict): raise ValueError("resolved native aircraft mapping required")
    if "mission" in r: raise ValueError("study owns generated fixed-duration mission; do not also supply recipe.mission")
    model=r.get("model")
    if model not in ("prop","jet","vtol"): return r
    items=r["onboard"]["items"]
    inc=sum(i["mass_kg"] for i in items if i["role"]=="payload" and i["mass_accounting"]=="incremental")
    named=sum(i["mass_kg"] for i in items if i["role"]=="payload")
    if s["payload_kg"]<named: raise ValueError("sample payload smaller than owned payload inventory; do not scale hardware masses silently")
    t=ops.transit(s["distance_km"],s["speed_m_s"])["t_round_trip_h"]+s["on_station_h"]
    distance=(t if station_h is None else t-s["on_station_h"]+station)*3600*s["speed_m_s"]+extra_m
    if model=="prop":
        from .mission import MissionSpec
        ms=MissionSpec.from_dict(d)
        h=ms.requirements.value("cruise_altitude",0.)
        req=d.setdefault("requirements",{})
        req["payload_mass"]={"target":s["payload_kg"]-inc,"unit":"kg"}
        req.pop("endurance",None) # one range-equivalent fixed-speed mission, no extra endurance leg
        req["range"]={"min":distance,"unit":"m"}
        req["cruise_speed"]={"target":s["speed_m_s"],"unit":"m/s"}
        if reserve:
            if ms.propulsion_kind!="electric":
                raise ValueError("operational reserve with thermal prop unassessed: native Raymer Eq. 3.11 6 % reserve+trapped allowance is not separable, adding a reserve would double it")
            pa=d.setdefault("assumptions",{}).setdefault("propulsion",{})
            ledger.append(dict(path="aircraft.assumptions.propulsion.energy_reserve",original=ms.assumptions["propulsion"]["energy_reserve"],replaced_by=0.))
            pa["energy_reserve"]=0.
        r["mission"]={"name":"fixed-duration fleet scenario", "pointmass_dt":5.,
                      "initial":{"altitude_m":h,"speed_m_s":s["speed_m_s"]},"segments":[]}
        for label,dt,on_station in (("outbound",t/2-s["on_station_h"]/2,False),("station",s["on_station_h"],True),("return",t/2-s["on_station_h"]/2,False)):
            if dt>0:r["mission"]["segments"].append(dict(type="cruise",name=label,time_min=dt*60,speed_m_s=s["speed_m_s"],altitude_m=h,on_station=on_station))
    elif model=="jet":
        from acdt.core.atmosphere import isa
        d["payload_kg"]=s["payload_kg"]-inc
        d["mach"]=s["speed_m_s"]/isa(d["altitude_m"]).a
        d["range_m"]=distance
        if reserve:
            from .jet.sizing import PHYSICAL_DEFAULTS
            ledger.append(dict(path="aircraft.reserve_fraction",original=d.get("reserve_fraction",PHYSICAL_DEFAULTS["reserve_fraction"]),replaced_by=0.))
            d["reserve_fraction"]=0.
        if not all(k in r.get("duration",{}) for k in ("precruise_s","postcruise_s")): raise ValueError("jet fleet schedule needs explicit departure/arrival durations, even without generator")
    else:
        if inc: raise ValueError("VTOL payload must be declared included in supplied MTOW")
        extra=s["payload_kg"]-named
        if extra:
            if any(i["id"]=="fleet_payload_remainder" for i in items): raise ValueError("reserved fleet payload id collision")
            items.append(dict(id="fleet_payload_remainder",role="payload",mass_kg=extra,mass_accounting="included",included_in="mtow",source=s["source"]))
        mi=d.setdefault("mission",{})
        mi.update(cruise_distance_m=2*s["distance_km"]*1000+(reserve["divert_km"]*1000 if reserve else 0.),cruise_speed_m_s=s["speed_m_s"],
                  t_loiter_s=(station+(reserve["time_h"] if reserve else 0.))*3600)
        if reserve:
            from .vtol.size import _COMMON as VD
            el=d.setdefault("electric",{})
            ledger.append(dict(path="aircraft.electric.reserve",original=el.get("reserve",VD["electric"]["reserve"]),replaced_by=0.))
            el["reserve"]=0.
    return r


def _gate(onboard,candidate):
    """Mass/energy/declared constraints gate, NOT global multidisciplinary feasibility.

    Unrequested missing spatial screens remain explicit outside this decision
    scope. Known failures ALWAYS block; requested missing spatial data blocks too.
    Only the existing prop pack-peak unknown can be resolved by an explicit pack
    C-rating and full-rating native demand (P=C*nominal Wh, existing VTOL convention).
    """
    required=[];excluded=[];extra=[]
    constraints=onboard["inputs"]["onboard"].get("constraints",{})
    integration=onboard["inputs"].get("integration",{})
    rows=[x for x in onboard["checks"] if x["name"]!="pointmass_onboard_capacity"]+onboard["onboard"]["checks"]
    rows+=onboard.get("onboard_pointmass",{}).get("checks",[])
    for row in rows:
        name=row["name"];v=row["passed"]
        if v is None and (name in SPATIAL or name.startswith(("thermal_","spatial_","FOV_3D:"))):
            closure=onboard["inputs"].get("closure",{})
            requested=(name=="allocated_volume" and "available_volume_m3" in constraints) or (name=="declared_heat" and ("available_heat_rejection_W" in constraints or "thermal" in closure)) or (name=="CG" and (bool(integration) or "cg" in closure)) or (name=="FOV_3D" and (bool(integration) or "fov" in closure)) or (name.startswith("thermal_") and "thermal" in closure) or (name.startswith("spatial_") and "spatial" in closure) or (name.startswith("FOV_3D:") and "fov" in closure)
            if not requested: excluded.append(name);continue
        if name=="main_pack_combined_peak_rating" and v is None and candidate.get("pack_power"):
            a=onboard["aircraft_result"] or {};E=a.get("energy_nominal_Wh");p=a.get("full_rating_battery_power_W")
            if E is not None and p is not None:
                avg=onboard["onboard"]["main_battery_average_W"];peak=onboard["onboard"]["main_battery_peak_W"]
                cp=candidate["pack_power"]
                v=p<=E*cp["continuous_C"] and p-avg+peak<=E*cp["peak_C"]
                extra.append(dict(name="explicit_pack_C_rating",passed=bool(v),required_continuous_W=p,required_peak_W=p-avg+peak,
                                  available_continuous_W=E*cp["continuous_C"],available_peak_W=E*cp["peak_C"],source=cp["source"],
                                  scope="conservative simultaneous full propulsion rating and connected hotel peak; no transient hardware/thermal validation"))
        required.append(dict(name=name,passed=None if v is None else bool(v)))
    return required,excluded,extra


def _n1(c,s,o):
    out=dict(status="unassessed",eligible=None,issues=[],metrics={},history=[],native=None,operations=None,turnaround=None,checks=[])
    if s["on_station_h"]<=o["handoff_overlap_h"]:
        out.update(status="infeasible",eligible=False);out["issues"].append("no_effective_on_station_time");return out
    if "recipe" not in c:
        out["issues"].append("missing_N1_recipe");return out
    model=c["recipe"].get("model")
    if model not in ("prop","jet","vtol"):
        out["issues"].append("unsupported_N1_adapter_or_hybrid_dispatch");return out
    try:
        bound=_bind(c["recipe"],s)
        b=size_onboard(bound);out["native"]=b
        if c.get("pack_power"):
            from .mission import MissionSpec
            if model!="prop" or MissionSpec.from_dict(bound["aircraft"]).propulsion_kind!="electric":
                raise ValueError("pack_power is only for the current electric prop native pack; VTOL already has its own C-rate check")
        out["history"].append(dict(stage="bind_and_size",model=model,mass_coupled=b["mass_coupled"],energy_coupled=b["energy_coupled"]))
        out["checks"],out["excluded_unrequested_checks"],out["pack_power_checks"]=_gate(b,c)
        if o["reserve_h"]:
            out["checks"].append(dict(name="N0_time_reserve_vs_native_energy_reserve",passed=None))
            out["issues"].append("nonzero_time_reserve_requires_explicit_reserve_mission_not_fraction_equivalence")
        a=b["aircraft_result"]
        if not a:
            out["issues"]+=b["issues"]
            out["eligible"]=False if aggregate(x["passed"] for x in out["checks"]) is False else None
            out["status"]="infeasible" if out["eligible"] is False else "unassessed"
            return out
        out["coverage_class"]={"prop":"airborne_level_pointmass","jet":"range_equivalent_jet_with_supplied_phases","vtol":"native_VTOL_segments"}[model]
        tbase=ops.transit(s["distance_km"],s["speed_m_s"])["t_round_trip_h"]
        E=fuel=None
        if model=="prop":
            pm=a.get("mission_pointmass")
            if not pm or pm["aborted"] is not None:
                out["checks"].append(dict(name="requested_mission_completed",passed=False if pm else None))
                out["issues"].append("pointmass_missing_or_aborted");out["eligible"]=aggregate(x["passed"] for x in out["checks"]);out["status"]="infeasible" if out["eligible"] is False else "unassessed";return out
            flight_h=pm["total_time_min"]/60
            if pm["unit"]=="Wh":E=pm["total_used_Wh"]
            else:fuel=pm["total_used_kg"]
            mtow=a["mtow_kg"]
            method="actual existing pointmass, range-equivalent fixed-speed level segments; starts airborne, zero wind, no field phases, turns or geographic return closure"
        elif model=="jet":
            if not a["converged"]:
                out["eligible"]=False;out["status"]="infeasible";out["issues"]+=a["issues"];return out
            cs=_common_sim_opt(c,o)
            if cs:
                from .flightsim.common_mission import simulate_common_mission
                sim=simulate_common_mission(model="jet",size_out=a,spec=c["recipe"]["aircraft"],sample=s,common=cs)
                out["common_sim"]=sim
                out["checks"]+=sim["checks"]
                if sim.get("unassessed_phases"):
                    out["issues"].append("common_sim_unassessed_phases:"+ ",".join(sim["unassessed_phases"]))
                if sim["status"]=="aborted" or sim["mission_result"].get("aborted"):
                    out["eligible"]=False;out["status"]="infeasible";out["issues"].append("common_sim_aborted");return out
                flight_h=sim["flight_duration_h"];fuel=sim["fuel_used_kg"];mtow=a["mtow_kg"]
                method="opt-in common pointmass with engine_point (Mattingly/Ihme or map); taxi phases may be unassessed"
                out["coverage_class"]="common_pointmass_jet"
            else:
                flight_h=tbase+s["on_station_h"]+sum(bound["duration"][k] for k in ("precruise_s","postcruise_s"))/3600
                fuel=a["weights"]["trip_burn_kg"];mtow=a["mtow_kg"]
                method="native jet differential Breguet: range-equivalent straight level station flight + explicit departure/arrival time; not dynamic simulator/turn loiter"
        else:
            if a.get("converged") is False:
                out["checks"].append(dict(name="VTOL_mass_closure",passed=None));out["issues"]+=b["issues"]
                out["eligible"]=aggregate(x["passed"] for x in out["checks"]);out["status"]="infeasible" if out["eligible"] is False else "unassessed";return out
            cs=_common_sim_opt(c,o)
            if cs:
                from .flightsim.common_mission import simulate_common_mission
                sim=simulate_common_mission(model="vtol",size_out=a,sample=s,common=cs)
                out["common_sim"]=sim
                out["checks"]+=sim["checks"]
                if sim.get("unassessed_phases"):
                    out["issues"].append("common_sim_unassessed_phases:"+ ",".join(sim["unassessed_phases"]))
                flight_h=sim["flight_duration_h"];E=sim["energy_Wh"];mtow=a.get("mtow_kg",a["mass_kg"])
                method="opt-in common VTOL phase energy timeline from native size_vtol powers; descent/taxi may be unassessed"
                out["coverage_class"]="common_energy_timeline_vtol"
            else:
                flight_h=a["t_total_s"]/3600;E=a["energy_Wh"];mtow=a["mass_kg"]
                method="native VTOL power/segment integration, including modelled hover/climb/transition; no dynamic flight simulator"
        off=flight_h-s["on_station_h"]
        if off < -1e-8: raise ValueError("native flight duration shorter than requested station time")
        multi=any(x["kind"]=="battery" and x["terminal_peak_W"]>0 for x in b["onboard"]["sources"])
        if "turnaround" not in c:
            ground=dict(assessed=False,duration_h=None,issues=["missing_turnaround_model"])
        else:ground=turnaround(c["turnaround"],E,has_fuel=fuel is not None,multiple_packs=multi)
        out["turnaround"]=ground
        out["checks"].append(dict(name="ground_service_assessed",passed=True if ground["assessed"] else None))
        out["issues"]+=ground["issues"]
        out["history"].append(dict(stage="mission_and_ground",flight_duration_h=flight_h,on_station_h=s["on_station_h"],off_station_flight_h=max(0.,off),mission_energy_Wh=E,mission_fuel_kg=fuel,ground_turnaround_h=ground["duration_h"],method=method))
        out["metrics"].update(mission_energy_Wh=E,mission_fuel_kg=fuel,ground_turnaround_h=ground["duration_h"])
        if ground["assessed"]:
            f=fleet(s["on_station_h"],max(0.,off),ground["duration_h"],o)
            out["operations"]=f;out["checks"].append(dict(name="homogeneous_station_schedule",passed=f["cycle"]["feasible"]))
            n=f["fleet_for_confidence"] if "confidence" in o else f["fleet_expected"]
            if "confidence" in o:
                out["checks"].append(dict(name="confidence_fleet_within_search_limit",passed=True if n is not None else None))
            out["metrics"].update(fleet_required=n,fleet_mtow_kg=n*mtow if n is not None else None)
            if ground.get("resource_policy"):ground["required_dedicated_chargers"]=n
            out["history"].append(dict(stage="fleet_recalculated",fleet_required=n,provisional=True))
        out["eligible"]=aggregate(x["passed"] for x in out["checks"])
        out["status"]="assessed_in_scope" if out["eligible"] is True else ("infeasible" if out["eligible"] is False else "unassessed")
        out["issues"] += [x["name"] for x in out["checks"] if x["passed"] is not True]
    except (ValueError,KeyError,TypeError) as exc:
        out["eligible"]=False if aggregate(x["passed"] for x in out["checks"]) is False else None
        out["status"]="infeasible" if out["eligible"] is False else "unassessed"
        out["issues"].append("candidate_evaluation: "+str(exc))
    return out



def _common_sim_opt(c, o):
    """Opt-in common_sim from candidate or operations; default off (legacy paths)."""
    cs = None
    if isinstance(c.get("common_sim"), dict):
        cs = c["common_sim"]
    elif isinstance(o.get("common_sim"), dict):
        cs = o["common_sim"]
    if not cs or not cs.get("enabled"):
        return None
    from .flightsim.common_mission import validate_common_sim
    validate_common_sim(cs)
    return cs


COVERAGE={"prop":"airborne_level_pointmass","jet":"range_equivalent_jet_with_supplied_phases","vtol":"native_VTOL_segments","hybrid":"hybrid_rule_based_dispatch_level_phases"}


def _prop_mission(h,V,d_km,T,t_res_h,dt=5.):
    leg=d_km*1000/V/3600
    segs=[dict(type="cruise",name=n,time_min=x*60,speed_m_s=V,altitude_m=h,on_station=on)
          for n,x,on in (("outbound",leg,False),("station",T,True),("return",leg,False),("operational_reserve",t_res_h,False)) if x>0]
    total=2*leg+T+t_res_h
    return dict(name="fixed-design capability search",pointmass_dt=dt,max_time_s=total*3600+3600,
                initial=dict(altitude_m=h,speed_m_s=V),segments=segs),total


def _prop_noncruise_hold(res):
    """Native non-cruise allowance the airborne pointmass does NOT fly; held, never turned into station time.

    Electric: take-off + climb energy of the same segment model the sizing uses
    (performance.takeoff_climb_energy). Thermal: Raymer 2018 Table 3.2 warm-up/
    take-off, climb and landing fractions booked by weights.fuel_fraction, held as
    W0(1 - f_to f_cl f_land) (slightly conservative landing share) + explicit
    auxiliary pre/post fuel. Same allowances as sizing, counted once.
    """
    from .weights import SEGMENT_FRACTIONS as SF
    W0=res.sizing.W0;p=res.spec.assumptions["propulsion"]
    if res.spec.propulsion_kind=="electric":
        from .performance import PerfModel, takeoff_climb_energy
        alt=max([l.altitude for l in res.legs]+[0.])
        E=takeoff_climb_energy(PerfModel.from_result(res),W0,alt)["total"]
        return dict(value=E,unit="J",value_Wh=E/3600,method="native take-off + climb segment energy (performance.takeoff_climb_energy), held from usable pack energy")
    m=W0*(1-SF["warmup_takeoff"]*SF["climb"]*SF["landing"])+p.get("auxiliary_fuel_flow_kg_s",0.)*(p.get("auxiliary_pre_s",0.)+p.get("auxiliary_post_s",0.))
    return dict(value=m,unit="kg",method="Raymer 2018 Table 3.2 warm-up/take-off, climb, landing fractions (as booked by sizing) + explicit auxiliary pre/post fuel, held from usable fuel")


def _model_terms(c,s,o,st):
    """Per-model sized(T_design) + nominal(T) closures over the REAL native models."""
    from acdt.core.atmosphere import isa
    model=c["recipe"]["model"];reserve=o.get("operational_reserve")
    t_res=_reserve_time_h(o,s) if reserve else 0.
    V=s["speed_m_s"];d=s["distance_km"]
    search=lambda ok:EN.max_feasible(ok,st["tolerance_h"],st["search_limit_h"],st["max_iterations"])
    if model=="hybrid":
        from . import hybrid_dispatch as HD
        h=c["recipe"]["aircraft"]["hybrid"];HD.validate_hybrid(h)
        run=lambda T,res:HD.evaluate(h,d,V,T,t_res if res else 0.)
        def sized(Td):
            r=run(Td,True)
            b=dict(inputs={"onboard":{}},checks=[dict(name="hybrid_dispatch:"+x["name"],passed=x["passed"]) for x in r["checks"]],
                   onboard={"checks":[],"sources":[]},aircraft_result=r,issues=[],status="evaluated")
            ok=lambda T:run(T,True)["feasible"]
            def nominal(T):
                q=run(T,False)
                return None if not q["feasible"] else dict(flight_h=q["flight_h"],E=q["ground_recharge_Wh"],fuel=q["fuel_kg"],
                    method="L0 hybrid rule-based dispatch over common phases at fixed supplied MTOW; E = ground recharge to initial SOC")
            return dict(bound=deepcopy(c["recipe"]),b=b,ledger=[],derived=search(ok),ok=ok,nominal=nominal,mtow=h["mass_kg"],failed=False)
        return sized,False
    if model=="prop":
        from .mission import MissionSpec
        from .flightsim.pointmass import simulate_pointmass_mission
        h=MissionSpec.from_dict(c["recipe"]["aircraft"]).requirements.value("cruise_altitude",0.)
        def sized(Td):
            lg=[];bound=_bind(c["recipe"],s,station_h=Td,reserve=reserve,ledger=lg)
            nat={};b=size_onboard(bound,nat);a=b["aircraft_result"]
            if not a or not a.get("converged") or "res" not in nat: return dict(bound=bound,b=b,ledger=lg,failed=True)
            res=nat["res"]
            hold=_prop_noncruise_hold(res)
            def sim(T,with_reserve):
                from .flightsim.pointmass import Plant, PointMassMission, load_mission
                m,total=_prop_mission(h,V,d,T,t_res if with_reserve else 0.)
                if total<=0: return None
                plant=Plant.from_sizing(res)
                plant.budget-=hold["value"]
                if plant.budget<=0: return dict(aborted="native non-cruise allowance exceeds usable budget",unit=hold["unit"])
                r=PointMassMission(plant,load_mission(m)).run();r.pop("_samples",None)
                return r
            def ok(T):
                pm=sim(T,True)
                if pm is None: return True
                if pm["aborted"] and "tempo máximo" in pm["aborted"]: return None
                return pm["aborted"] is None
            def nominal(T):
                pm=sim(T,False)
                if pm is None or pm["aborted"] is not None: return None
                E,fuel=(pm["total_used_Wh"],None) if pm["unit"]=="Wh" else (None,pm["total_used_kg"])
                return dict(flight_h=pm["total_time_min"]/60,E=E,fuel=fuel,method="existing pointmass at fixed sized design, level fixed speed, starts airborne, zero wind")
            return dict(bound=bound,b=b,ledger=lg,derived=search(ok),ok=ok,nominal=nominal,mtow=a["mtow_kg"],failed=False,held_allowance=hold)
        return sized,True
    if model=="jet":
        from .jet.sizing import fixed_design_burn, IntegrationError
        def sized(Td):
            lg=[];bound=_bind(c["recipe"],s,station_h=Td,reserve=reserve,ledger=lg)
            b=size_onboard(bound);a=b["aircraft_result"]
            if not a or not a.get("converged"): return dict(bound=bound,b=b,ledger=lg,failed=True)
            spec=b["resolved_aircraft"];m0=a["mtow_kg"];usable=a["weights"]["trip_burn_kg"]
            pre=sum(bound["duration"][k] for k in ("precruise_s","postcruise_s"))
            Vj=spec["mach"]*isa(spec["altitude_m"]).a
            def burn(T,with_reserve):
                R=2*d*1000+Vj*T*3600+((Vj*reserve["time_h"]*3600+reserve["divert_km"]*1000) if (with_reserve and reserve) else 0.)
                return fixed_design_burn(spec,m0,R)["trip_burn_kg"]
            def ok(T):
                try: return burn(T,True)<=usable*(1+1e-9)
                except IntegrationError: return None
                except ValueError: return False
            def nominal(T):
                cs=_common_sim_opt(c,o)
                if cs:
                    from .flightsim.common_mission import simulate_common_mission
                    sample=dict(distance_km=d,speed_m_s=V,on_station_h=T,payload_kg=s["payload_kg"])
                    sim=simulate_common_mission(model="jet",size_out=a,spec=spec,sample=sample,common=cs)
                    if sim["status"]=="aborted" or (sim.get("mission_result") or {}).get("aborted"): return None
                    return dict(flight_h=sim["flight_duration_h"],E=None,fuel=sim["fuel_used_kg"],
                                method="opt-in common pointmass (engine_point); Breguet still used for capability bracket ok()",
                                common_sim=sim)
                return dict(flight_h=(2*d*1000/Vj+T*3600+pre)/3600,E=None,fuel=burn(T,False),
                            method="fixed-MTOW differential Breguet (same terms as size_jet), straight level station, explicit pre/post time")
            return dict(bound=bound,b=b,ledger=lg,derived=search(ok),ok=ok,nominal=nominal,mtow=m0,failed=False,usable_fuel_kg=usable)
        return sized,True
    if "closure" in c["recipe"]["aircraft"]:
        def sized(Td):
            lg=[];bound=_bind(c["recipe"],s,station_h=Td,reserve=reserve,ledger=lg)
            b=size_onboard(bound);a=b["aircraft_result"]
            if not a or not a.get("converged"): return dict(bound=bound,b=b,ledger=lg,failed=True)
            m0=a["mtow_kg"];B=a["battery_mass_kg"]
            fixed=deepcopy(c["recipe"]);fixed["aircraft"].pop("closure");fixed["aircraft"]["mass_kg"]=m0
            def native(T,with_reserve):
                bb=size_onboard(_bind(fixed,s,station_h=T,reserve=reserve if with_reserve else None))
                return bb["aircraft_result"]
            def ok(T):
                a2=native(T,True)
                if a2 is None: return None
                return a2["battery_mass_kg"]<=B*(1+1e-9) and bool(a2["feasible"])
            def nominal(T):
                a2=native(T,False)
                return None if not a2 else dict(flight_h=a2["t_total_s"]/3600,E=a2["energy_Wh"],fuel=None,
                    method="native VTOL segment energy at the closed MTOW with the closed (installed) battery mass")
            return dict(bound=bound,b=b,ledger=lg,derived=search(ok),ok=ok,nominal=nominal,mtow=m0,failed=False,
                        installed_battery_kg=B,vtol_closure=dict(status=a["closure"]["status"],mtow_kg=m0,
                        residual_kg=a["closure"]["solver"]["residual_kg"],iterations=a["closure"]["solver"]["iterations"]))
        return sized,True
    def sized(Td):
        lg=[];bound=_bind(c["recipe"],s,station_h=Td,reserve=reserve,ledger=lg)
        b=size_onboard(bound);a=b["aircraft_result"]
        if not a: return dict(bound=bound,b=b,ledger=lg,failed=True)
        def ok(T):
            bb=size_onboard(_bind(c["recipe"],s,station_h=T,reserve=reserve))
            m={x["name"]:x["passed"] for x in bb["checks"]}.get("VTOL_inclusive_mass_budget")
            if m is None or bb["aircraft_result"] is None: return None
            return bool(m) and bool(bb["aircraft_result"]["feasible"])
        def nominal(T):
            bb=size_onboard(_bind(c["recipe"],s,station_h=T))
            a2=bb["aircraft_result"]
            return None if not a2 else dict(flight_h=a2["t_total_s"]/3600,E=a2["energy_Wh"],fuel=None,
                method="native VTOL segment energy at fixed supplied MTOW; battery up to inclusive mass budget")
        return dict(bound=bound,b=b,ledger=lg,derived=search(ok),ok=ok,nominal=nominal,mtow=a["mass_kg"],failed=False)
    return sized,False


def _shared_dwell(c,o,T,n,label,mtow,multi):
    """Schema 1.2: closed sortie → service durations → shared-resource DES fleet loop."""
    proc=c["ground_process"];st=GQ.validate_process(proc,(o.get("ground_resources") or {}).get("pools",{}))
    acts,issues=GQ.durations(proc,n["E"],n["fuel"],multi)
    off=max(0.,n["flight_h"]-T)
    row=dict(label=label,on_station_h=T,flight_duration_h=n["flight_h"],off_station_flight_h=off,mission_energy_Wh=n["E"],
             mission_fuel_kg=n["fuel"],method=n["method"],ground_activities=acts,assessed=False,issues=list(issues))
    if issues:
        row["turnaround"]=dict(assessed=False,duration_h=None,issues=issues);return row
    pools=(o.get("ground_resources") or {}).get("pools",{})
    A=fleet(1.,0.,0.,o)["availability"]
    res=GQ.fleet_with_resources(T,o["handoff_overlap_h"],o["n_stations"],[dict(id=c["id"],flight_h=n["flight_h"],acts=acts,stations=list(range(o["n_stations"])))],
                                pools,st,A,o.get("confidence"))
    gt=res.get("ground_time") or {}
    row["turnaround"]=dict(assessed=res["assessed"],duration_h=gt.get("ground_max_h"),mean_h=gt.get("ground_mean_h"),wait_max_h=gt.get("wait_max_h"),
                           issues=res["issues"],method="shared-resource DES ground time (service + FIFO wait), max over steady window",
                           resource_policy="shared pools "+str(pools))
    row.update(operations=res,assessed=res["assessed"],issues=list(res["issues"]),schedule_feasible=res["status"]=="converged")
    if res["assessed"]:
        k=res["fleet_for_confidence"] if "confidence" in o else res["fleet_expected"]
        row.update(fleet_required=k,fleet_mtow_kg=k*mtow if k is not None else None)
    elif res["status"] in ("resource_saturated","infeasible"):
        row.update(assessed=True,schedule_feasible=False,fleet_required=None,fleet_mtow_kg=None)
    return row


def _n1_v11(c,s,o,x12=None):
    """Schema 1.1: derived maximum station time, sizing↔capability closure, explicit reserve once."""
    from acdt.core.onboard import analyse_onboard
    out=dict(status="unassessed",eligible=None,issues=[],metrics={},history=[],native=None,operations=None,turnaround=None,checks=[],
             endurance=None,closure=None,reserve=None,operations_by_dwell=None,dwell_policy=o.get("dwell_policy","requested"))
    if s["on_station_h"]<=o["handoff_overlap_h"]:
        out.update(status="infeasible",eligible=False);out["issues"].append("no_effective_on_station_time");return out
    if "recipe" not in c:
        out["issues"].append("missing_N1_recipe");return out
    model=c["recipe"].get("model")
    hyb=x12 is not None and model=="hybrid" and isinstance(c["recipe"].get("aircraft"),dict) and "hybrid" in c["recipe"]["aircraft"]
    if hyb and c["recipe"].get("onboard"):
        out["issues"].append("hybrid_dispatch_with_common_onboard_unimplemented_use_hotel_power_W");return out
    if model not in ("prop","jet","vtol") and not hyb:
        out["issues"].append("unsupported_N1_adapter_or_hybrid_dispatch");return out
    st=EN.settings(c.get("endurance"));reserve=o.get("operational_reserve");Treq=s["on_station_h"]
    def conclude():
        out["eligible"]=aggregate(x["passed"] for x in out["checks"])
        out["status"]="assessed_in_scope" if out["eligible"] is True else ("infeasible" if out["eligible"] is False else "unassessed")
        out["issues"]+=[x["name"] for x in out["checks"] if x["passed"] is not True and x["name"] not in out["issues"]]
        return out
    try:
        sized,rubber=_model_terms(c,s,o,st)
        failed=[]
        def evaluate(Td):
            ev=sized(Td)
            if ev["failed"]: failed.append(ev); return None
            return ev
        if rubber:
            cl=EN.capability_closure(evaluate,Treq,st["closure_tolerance_h"],st["closure_max_iterations"])
            final=cl.pop("last")
        else:
            final=evaluate(Treq)
            cl=dict(status="not_applicable_fixed_supplied_mtow",converged=None,history=[],
                    note=("hybrid MTOW, battery and fuel capacity are supplied; derived maximum only, no resize loop exists" if model=="hybrid"
                          else "VTOL MTOW is supplied and inclusive; derived maximum only, no resize loop exists"))
        out["closure"]=cl
        out["history"]+= [dict(stage="capability_closure",**h) for h in cl["history"]]
        ev=final or (failed[-1] if failed else None)
        if ev is None: raise ValueError("no native evaluation")
        b=ev["b"];out["native"]=b
        if c.get("pack_power"):
            from .mission import MissionSpec
            if model!="prop" or MissionSpec.from_dict(ev["bound"]["aircraft"]).propulsion_kind!="electric":
                raise ValueError("pack_power is only for the current electric prop native pack; VTOL already has its own C-rate check")
        out["checks"],out["excluded_unrequested_checks"],out["pack_power_checks"]=_gate(b,c)
        out["reserve"]=(dict(policy="explicit_operational_reserve_replaces_native_fraction",time_h=reserve["time_h"],divert_km=reserve["divert_km"],
                             reserve_time_at_sample_speed_h=_reserve_time_h(o,s),source=reserve["source"],native_replaced=ev["ledger"],
                             applied_in=["sizing mission","derived-endurance capability search"],
                             excluded_from=["nominal consumption","charging energy","flight schedule"],
                             note="flown at sample speed/altitude; divert distance at the same speed; held, not flown, in nominal sorties")
                        if reserve else (dict(policy="no_native_reserve_fraction",note="hybrid: only SOC minimum and fuel capacity limits; no reserve fraction exists")
                                         if model=="hybrid" else dict(policy="native_fraction_only",note="native reserve fraction/DoD retained once; no operational reserve mission")))
        if o["reserve_h"]:
            out["checks"].append(dict(name="N0_time_reserve_vs_native_energy_reserve",passed=None))
            out["issues"].append("nonzero_time_reserve_requires_explicit_operational_reserve_schema_1_1")
        if ev["failed"]:
            out["checks"].append(dict(name="native_sizing_converged",passed=False if b.get("status")=="infeasible" else None))
            out["issues"]+=b["issues"]; return conclude()
        if ev.get("vtol_closure"):
            out["vtol_mass_closure"]=dict(ev["vtol_closure"],installed_battery_kg=ev["installed_battery_kg"],
                note="MTOW solved from components at the final design station time; capability searched at that fixed MTOW/battery")
        der=ev["derived"];out["endurance"]=dict(der,model=model,held_noncruise_allowance=ev.get("held_allowance"),requested_on_station_h=Treq,
            derived_max_on_station_h=der["value_h"],excess_on_station_h=(der["value_h"]-Treq) if der["value_h"] is not None else None,
            scope="fixed sized design at the sampled distance/speed, with operational reserve held; NOT a different design or loiter-speed optimisation")
        ok=ev["ok"](Treq)
        if der["status"]=="infeasible_at_zero_station": ok=False
        out["checks"].append(dict(name="derived_max_covers_requested_station",passed=ok,
                                  derived_max_on_station_h=der["value_h"],requested_on_station_h=Treq))
        if rubber: out["checks"].append(dict(name="capability_closure_converged",passed=True if cl["converged"] else (False if cl["status"]=="capability_infeasible" else None),status=cl["status"]))
        out["coverage_class"]=COVERAGE[model]
        if x12 is not None:
            from .mission_phases import coverage, required_check
            kind=None
            if model=="prop":
                from .mission import MissionSpec
                kind="electric" if MissionSpec.from_dict(c["recipe"]["aircraft"]).propulsion_kind=="electric" else "prop"
            out["mission_phases"]=coverage(model,kind,out["reserve"]["policy"],c["recipe"]["aircraft"].get("hybrid"),
                                           jet_durations=bool((c["recipe"].get("duration") or {})))
            if x12.get("required_phases"):
                out["checks"].append(required_check(out["mission_phases"],x12["required_phases"]))
            if model=="hybrid":
                out["hybrid_dispatch"]=ev["b"]["aircraft_result"]
        multi=any(x["kind"]=="battery" and x["terminal_peak_W"]>0 for x in b["onboard"]["sources"])
        def dwell(T,label):
            n=ev["nominal"](T)
            if n is None: return dict(label=label,on_station_h=T,assessed=False,issues=["nominal_sortie_not_completed"])
            off=max(0.,n["flight_h"]-T)
            if "ground_process" in c: return _shared_dwell(c,o,T,n,label,ev["mtow"],multi)
            ground=dict(assessed=False,duration_h=None,issues=["missing_turnaround_model"]) if "turnaround" not in c else turnaround(c["turnaround"],n["E"],has_fuel=n["fuel"] is not None,multiple_packs=multi)
            row=dict(label=label,on_station_h=T,flight_duration_h=n["flight_h"],off_station_flight_h=off,mission_energy_Wh=n["E"],
                     mission_fuel_kg=n["fuel"],turnaround=ground,method=n["method"],assessed=ground["assessed"],issues=list(ground["issues"]))
            if ground["assessed"]:
                f=fleet(T,off,ground["duration_h"],o);k=f["fleet_for_confidence"] if "confidence" in o else f["fleet_expected"]
                if ground.get("resource_policy"): ground["required_dedicated_chargers"]=k
                row.update(operations=f,fleet_required=k,fleet_mtow_kg=k*ev["mtow"] if k is not None else None,schedule_feasible=f["cycle"]["feasible"])
            return row
        rows={"requested":dwell(Treq,"requested")}
        if der["status"]=="converged" and ok: rows["derived_max"]=dwell(max(der["value_h"],Treq),"derived_max")
        out["operations_by_dwell"]=rows
        if "derived_max" in rows: out["endurance"]["derived_max_sortie_flight_h"]=rows["derived_max"].get("flight_duration_h")
        chosen=rows.get(out["dwell_policy"])
        if chosen is None:
            out["checks"].append(dict(name="dwell_policy_operable",passed=None));return conclude()
        out["turnaround"]=chosen.get("turnaround");out["operations"]=chosen.get("operations")
        out["checks"].append(dict(name="ground_service_assessed",passed=True if chosen["assessed"] else None))
        out["issues"]+=chosen["issues"]
        if chosen["assessed"]:
            out["checks"].append(dict(name="homogeneous_station_schedule",passed=chosen["schedule_feasible"]))
            if "confidence" in o: out["checks"].append(dict(name="confidence_fleet_within_search_limit",passed=True if chosen["fleet_required"] is not None else None))
        if out["dwell_policy"]=="derived_max":
            target="vtol" if model=="vtol" else ("jet" if model=="jet" else ("electric" if chosen.get("mission_energy_Wh") is not None else "prop"))
            od=analyse_onboard(ev["bound"]["onboard"],target,chosen["flight_duration_h"]*3600) if chosen["assessed"] else {"checks":[]}
            for row in od["checks"]:
                if row["passed"] is None and row["name"] in SPATIAL: continue
                out["checks"].append(dict(name="derived_dwell:"+row["name"],passed=row["passed"]))
        out["mtow_kg"]=ev["mtow"]
        out["metrics"].update(mission_energy_Wh=chosen.get("mission_energy_Wh"),mission_fuel_kg=chosen.get("mission_fuel_kg"),
                              ground_turnaround_h=(chosen.get("turnaround") or {}).get("duration_h"),fleet_required=chosen.get("fleet_required"),
                              fleet_mtow_kg=chosen.get("fleet_mtow_kg"),derived_max_on_station_h=der["value_h"])
        out["history"].append(dict(stage="fleet_recalculated",dwell_policy=out["dwell_policy"],fleet_required=chosen.get("fleet_required"),
                                   dependency="direct: closed sortie → ground time → fleet; no fleet→design dependency with dedicated resources"))
        return conclude()
    except (ValueError,KeyError,TypeError) as exc:
        out["eligible"]=False if aggregate(x["passed"] for x in out["checks"]) is False else None
        out["status"]="infeasible" if out["eligible"] is False else "unassessed"
        out["issues"].append("candidate_evaluation: "+str(exc))
        return out


def evaluate_study(spec):
    """Evaluate supplied samples/candidates, retain unknowns, compare only like missions.

    One-pass feedback, not fictitious convergence: fleet only changes dedicated
    resource count, not charging allocation. No fleet→queue→endurance fixed point.
    N0 never requires aircraft geometry. Native N1 models can require geometry.
    """
    validate_study(spec)
    rows=[];comparisons=[]
    for s in spec["mission"]["samples"]:
        groups={};excluded=[]
        for c in spec["candidates"]:
            n0=_n0(c,s,spec["operations"])
            if spec["schema_version"]=="1.2": n1=_n1_v11(c,s,spec["operations"],dict(required_phases=spec["mission"].get("required_phases")))
            else: n1=(_n1_v11 if spec["schema_version"]=="1.1" else _n1)(c,s,spec["operations"])
            bounds=n0["fleet_required_bounds"];n=n1["metrics"].get("fleet_required")
            fixed_bounds=n0["fixed_mission_fleet_required_bounds"]
            change=dict(n0_bounds=bounds,n0_fixed_mission_bounds=fixed_bounds,
                        delta_from_fixed_mission_bounds=[n-fixed_bounds[0],n-fixed_bounds[1]] if n is not None and fixed_bounds else None,
                        N1_fixed_mission_fleet=n,count_is_conditional=n1["eligible"] is not True,
                        delta_from_bounds=[n-bounds[0],n-bounds[1]] if n is not None and bounds else None,
                        reason="N0 supplied maximum/endurance interval replaced by actual supported fixed-duration mission and grounded service; NOT a new maximum-endurance estimate")
            if spec["schema_version"] in ("1.1","1.2"):
                byd=n1.get("operations_by_dwell") or {}
                change.update(N1_fleet_at_requested_dwell=(byd.get("requested") or {}).get("fleet_required"),
                              N1_fleet_at_derived_max_dwell=(byd.get("derived_max") or {}).get("fleet_required"))
            rows.append(dict(candidate_id=c["id"],architecture=c["architecture"],sample=deepcopy(s),source=c["source"],n0=n0,n1=n1,feedback=change))
            if n1["eligible"] is True:groups.setdefault(n1["coverage_class"],[]).append(dict(id=c["id"],metrics=n1["metrics"]))
            else:excluded.append(dict(id=c["id"],status=n1["status"],issues=n1["issues"]))
        # Do not assert dominance across incompatible model/mission phase coverage.
        if not groups:groups={"no_assessed_candidates":[]}
        for coverage,alternatives in groups.items():
            comparison=tradeoff.compare(alternatives,spec["objectives"])
            comparison.update(sample_id=s["id"],coverage_class=coverage,excluded_from_assessed_frontier=deepcopy(excluded),
                              interpretation="conditional nondominated supplied candidates for SAME sampled mission AND model phase coverage; unsupported alternatives retained; no cross-coverage dominance, global optimum or automatic winner")
            comparisons.append(comparison)
    if spec["schema_version"] in ("1.1","1.2"):
        convergence=dict(kind="per_candidate_capability_closure",
                         candidates={r["candidate_id"]+"/"+r["sample"]["id"]:(r["n1"].get("closure") or {}).get("status") for r in rows},
                         fleet_feedback="direct arithmetic: closed sortie → ground → fleet; no fleet→design dependency exists with dedicated resources, so no outer loop is run",
                         converged=None,reason="see per-candidate closure status/residual history; study-level fixed point not defined")
    else:
        convergence=dict(kind="one_pass_feedback",converged=None,reason="no solved fixed point; dedicated per-aircraft resources or supplied turnaround; revise scenarios externally")
    limitations=["Explicit sample evaluations, not continuous envelope optimization, autonomous architecture search, certified availability or global fleet optimum.",
                 "Homogeneous fleet per candidate; no mixed-fleet allocation, common-cause availability, charger queues or shared infrastructure dispatch.",
                 "N1 results are fixed-duration mission scenarios, NOT derived maximum endurance. Native reserve energy counted once; nonzero operational time reserve remains unassessed.",
                 "Eligible means scoped mass/energy/mission/operations checks assessed, not full thermal/spatial/CG/FOV closure or regulatory compliance.",
                 "Prop pointmass starts airborne in level flight; jet default Breguet / VTOL native segments; opt-in common_sim.enabled uses common pointmass (jet) or phase energy timeline (VTOL)."]
    if spec["schema_version"]=="1.2":
        limitations.append("Schema 1.2 shared ground resources: deterministic next-event DES (Law 2015) of a periodic launch schedule with FIFO pooled resources; "
                           "stability rho<1 (Kleinrock 1975); no stochastic queues, failures, priorities or travel between pads. Pools are per candidate unless mixed_fleet shares them.")
    if spec["schema_version"] in ("1.1","1.2"):
        limitations[2]=("Schema 1.1: derived maximum station time of the FIXED sized design at sampled distance/speed (bisection, conservative lower value). "
                        "Explicit operational reserve replaces native fractions and is applied once; thermal-prop Raymer 6 % allowance is not separable (unassessed with reserve). "
                        "No loiter-speed optimisation, wind, tank-capacity limit or regulatory reserve compliance.")
        limitations.append("Rubber prop/jet (and VTOL with opt-in aircraft.closure): upward-only sizing↔capability correction with residual history; VTOL fixed supplied MTOW has no resize loop. Jet derived range equals its design mission by construction (same integrator); VTOL closed design likewise unless its battery is power-limited.")
    extra={}
    if "mixed_fleet" in spec:
        from .mission_fleet_mixed import evaluate_mixed
        extra["mixed_fleet"]=evaluate_mixed(spec,rows)
    return dict(schema_version=spec["schema_version"],level="N0→N1/L0",inputs=deepcopy(spec),rows=rows,comparisons=comparisons,**extra,
                convergence=convergence,
                assumptions=[dict(source=spec["source"],value=deepcopy(spec))],limitations=limitations)
