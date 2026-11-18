# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Shared incremental onboard inventory and electrical allocation, schema 1.0.

Reuses PowerBudget/Load: MIL-E-7016F; Moir & Seabridge (3rd ed.), Ch.5,
as implemented in systems.avionics/electrical. Average=sum(P*duty), peak=sum
connected peaks (conservative simultaneous peak, NOT a transient dispatch).
E[Wh]=P[W]*t[s]/3600, fuel[kg/s]=P[W]*BSFC[kg/kWh]/3.6e6.
SI conversions: NIST SP811 (2008), Appendix B.8 (existing THIRD_PARTY reference).
No generator/engine coefficients are estimated: efficiencies, BSFC, incremental
jet fuel/traction penalties, capacities, masses and spatial data are INPUTS.
PRESSUPOSTO: time-invariant duty/load allocation; no hybrid propulsion scheduling.
"""
from copy import deepcopy
from .energy_storage import mapping, number, aggregate
from .systems.avionics import Load, PowerBudget


def _text(x, name):
    if not isinstance(x,str) or not x.strip(): raise ValueError(name+" must be nonempty text / source")


def validate_onboard(s):
    mapping(s,{"schema_version","source","items","loads","sources","constraints"},"onboard")
    if s.get("schema_version") != "1.0": raise ValueError("onboard.schema_version must be 1.0")
    _text(s.get("source"),"onboard.source")
    for key in ("items","loads","sources"):
        if not isinstance(s.get(key),list) or len(s[key])>200: raise ValueError(key+" must be explicit list <=200")
    ids=set()
    for i in s["items"]:
        mapping(i,{"id","role","mass_kg","mass_accounting","included_in","source","volume_m3","heat_W"},"onboard item")
        _text(i.get("id"),"item.id"); _text(i.get("source"),"item.source")
        if i["id"] in ids: raise ValueError("duplicate onboard item id")
        ids.add(i["id"])
        if i.get("role") not in ("payload","equipment"): raise ValueError("role must be payload or equipment")
        number("item.mass_kg",i.get("mass_kg"))
        if i.get("mass_accounting") not in ("incremental","included"): raise ValueError("declare incremental vs included mass")
        if i["mass_accounting"] == "included":
            if i.get("included_in") not in ("payload","empty","mtow"): raise ValueError("included mass needs explicit owner payload/empty/mtow")
            if i["included_in"] == "payload" and i["role"] != "payload": raise ValueError("equipment is not payload")
            if i["included_in"] == "empty" and i["role"] != "equipment": raise ValueError("payload is not empty equipment")
        elif "included_in" in i: raise ValueError("incremental mass cannot also be included")
        for k in ("volume_m3","heat_W"):
            if i.get(k) is not None: number(k,i[k])
    sources=set(); owned=set()
    for x in s["sources"]:
        mapping(x,{"id","kind","item_id","delivery_efficiency","continuous_W","peak_W","usable_Wh",
                   "reserve_fraction","generator_efficiency","bsfc_kg_kWh_shaft","fuel_kg_kWh_terminal",
                   "thrust_penalty_N_per_W_terminal","shaft_limit_W","source"},"onboard source")
        _text(x.get("id"),"source.id"); _text(x.get("source"),"source provenance")
        if x["id"] in sources: raise ValueError("duplicate source id")
        sources.add(x["id"])
        if x.get("kind") not in ("main_battery","battery","generator"): raise ValueError("unsupported source kind")
        if x["kind"] == "main_battery":
            if "item_id" in x: raise ValueError("main propulsion pack mass is sized by aircraft, never added as another item")
            if any(k in x for k in ("usable_Wh","reserve_fraction")): raise ValueError("main pack reserve/DoD belongs to native sizing, once only")
        else:
            if x.get("item_id") not in ids or x["item_id"] in owned: raise ValueError("source must own one unique declared equipment item")
            item=next(i for i in s["items"] if i["id"]==x["item_id"])
            if item["role"] != "equipment": raise ValueError("source mass is equipment, not payload")
            owned.add(x["item_id"])
        number("delivery_efficiency",x.get("delivery_efficiency"),positive=True,maximum=1)
        for k in ("continuous_W","peak_W","usable_Wh","reserve_fraction","generator_efficiency",
                  "bsfc_kg_kWh_shaft","fuel_kg_kWh_terminal","thrust_penalty_N_per_W_terminal","shaft_limit_W"):
            if x.get(k) is not None:
                number(k,x[k],positive=k in {"generator_efficiency","bsfc_kg_kWh_shaft","fuel_kg_kWh_terminal"},maximum=1 if k=="generator_efficiency" else 1e15)
        if x["kind"] != "generator" and any(k in x for k in ("generator_efficiency","bsfc_kg_kWh_shaft","fuel_kg_kWh_terminal","thrust_penalty_N_per_W_terminal","shaft_limit_W")):
            raise ValueError("battery cannot carry a generator fuel/extraction model")
        if x["kind"] == "generator" and any(k in x for k in ("usable_Wh","reserve_fraction")):
            raise ValueError("generator fuel reserve belongs to native fuel sizing, once only")
    load_ids=set()
    for l in s["loads"]:
        mapping(l,{"id","item_id","source_id","power_W","peak_W","duty","bus","source"},"onboard load")
        _text(l.get("id"),"load.id"); _text(l.get("source"),"load.source")
        if l["id"] in load_ids: raise ValueError("duplicate load id")
        load_ids.add(l["id"])
        if l.get("item_id") not in ids or l.get("source_id") not in sources: raise ValueError("load needs declared item and source")
        for k in ("power_W","peak_W","duty"): number(k,l.get(k),maximum=1 if k=="duty" else 1e15)
        if l["peak_W"] < l["power_W"]: raise ValueError("peak_W must cover connected power, not duty-averaged power")
        if "bus" in l: _text(l["bus"],"bus")
    constraints=s.get("constraints",{})
    mapping(constraints,{"available_volume_m3","available_heat_rejection_W","source"},"onboard constraints")
    if constraints:
        _text(constraints.get("source"),"constraints.source")
        for k in ("available_volume_m3","available_heat_rejection_W"):
            if constraints.get(k) is not None: number(k,constraints[k])


def analyse_onboard(s, model, duration_s=None):
    """Common allocation/capacity screening; missing limits are unassessed, not zero.

    `model` is prop/electric/jet/vtol/hybrid; hybrid is accounting only. Duration
    already covers the modelled phases; dedicated batteries use explicitly USABLE
    energy and their explicit extra reserve. Native main-pack reserve/DoD is not repeated.
    """
    validate_onboard(s)
    if model not in ("prop","electric","jet","vtol","hybrid"): raise ValueError("unknown onboard model")
    if duration_s is not None: number("duration_s",duration_s)
    checks=[]
    def check(name,passed,**kw): checks.append(dict(name=name,passed=passed,**kw))
    rows=[]; main=main_peak=fuel=shaft=penalty=0.; missing=[]
    for x in s["sources"]:
        loads=[l for l in s["loads"] if l["source_id"]==x["id"]]
        pb=PowerBudget([Load(l["id"],l["power_W"],l["duty"],l["peak_W"],l.get("bus","onboard")) for l in loads])
        avg,peak=pb.average_w/x["delivery_efficiency"],pb.peak_w/x["delivery_efficiency"]
        r=dict(id=x["id"],kind=x["kind"],load_average_W=pb.average_w,load_peak_W=pb.peak_w,
               terminal_average_W=avg,terminal_peak_W=peak,energy_Wh=avg*duration_s/3600 if duration_s is not None else None,
               fuel_flow_kg_s=0.,shaft_extraction_W=0.,thrust_penalty_N=0.,source=x["source"])
        for key,need in (("continuous_W",avg),("peak_W",peak)):
            limit=x.get(key)
            check(x["id"]+":"+key,limit>=need if limit is not None else None,required_W=need,available_W=limit)
        if x["kind"]=="main_battery":
            if model not in ("electric","vtol","hybrid"): raise ValueError("main battery allocation needs an electric/VTOL model")
            main+=avg; main_peak+=peak
        elif x["kind"]=="battery":
            reserve=x.get("reserve_fraction"); cap=x.get("usable_Wh")
            need=r["energy_Wh"]*(1+reserve) if r["energy_Wh"] is not None and reserve is not None else None
            check(x["id"]+":energy",cap>=need if cap is not None and need is not None else None,required_Wh=need,usable_Wh=cap)
        else:
            if model=="jet" and any(k in x for k in ("generator_efficiency","bsfc_kg_kWh_shaft","shaft_limit_W")):
                raise ValueError("jet needs explicit incremental deck fuel/thrust penalties, not shaft BSFC")
            if model=="prop" and any(k in x for k in ("fuel_kg_kWh_terminal","thrust_penalty_N_per_W_terminal")):
                raise ValueError("thermal prop uses explicit shaft BSFC and generator efficiency, not jet deck penalties")
            if model in ("electric","vtol"): raise ValueError("electric/VTOL native propulsion has no fuel generator dispatch; use separate accounting/hybrid screening")
            known=True
            if model=="prop" and all(x.get(k) is not None for k in ("generator_efficiency","bsfc_kg_kWh_shaft")):
                r["shaft_extraction_W"]=avg/x["generator_efficiency"]
                r["peak_shaft_extraction_W"]=peak/x["generator_efficiency"]
                r["fuel_flow_kg_s"]=r["shaft_extraction_W"]*x["bsfc_kg_kWh_shaft"]/3.6e6
                lim=x.get("shaft_limit_W")
                check(x["id"]+":shaft_peak",lim>=peak/x["generator_efficiency"] if lim is not None else None)
            elif model=="jet" and all(x.get(k) is not None for k in ("fuel_kg_kWh_terminal","thrust_penalty_N_per_W_terminal")):
                r["fuel_flow_kg_s"]=avg*x["fuel_kg_kWh_terminal"]/3.6e6
                r["thrust_penalty_N"]=avg*x["thrust_penalty_N_per_W_terminal"]
                r["peak_thrust_penalty_N"]=peak*x["thrust_penalty_N_per_W_terminal"]
            elif peak>0:
                known=False; missing.append(x["id"]+":extraction_model")
                r.update(fuel_flow_kg_s=None,shaft_extraction_W=None,thrust_penalty_N=None)
            check(x["id"]+":extraction_model",True if known else None)
            if known:
                fuel+=r["fuel_flow_kg_s"]; shaft+=r["shaft_extraction_W"]; penalty+=r["thrust_penalty_N"]
        rows.append(r)
    cs=s.get("constraints",{})
    volume=sum(i["volume_m3"] for i in s["items"]) if all(i.get("volume_m3") is not None for i in s["items"]) else None
    heat=sum(i["heat_W"] for i in s["items"]) if all(i.get("heat_W") is not None for i in s["items"]) else None
    for name,need,key in (("allocated_volume",volume,"available_volume_m3"),("declared_heat",heat,"available_heat_rejection_W")):
        cap=cs.get(key); check(name,cap>=need if cap is not None and need is not None else None,required=need,available=cap)
    check("CG",None); check("FOV_3D",None)
    pb=PowerBudget([Load(l["id"],l["power_W"],l["duty"],l["peak_W"],l.get("bus","onboard")) for l in s["loads"]])
    return dict(schema_version="1.0",model=model,inputs=deepcopy(s),duration_s=duration_s,
                load_average_W=pb.average_w,load_peak_W=pb.peak_w,loads=pb.table(),sources=rows,
                main_battery_average_W=main,main_battery_peak_W=main_peak,
                fuel_flow_kg_s=None if missing else fuel,shaft_extraction_W=None if missing else shaft,
                thrust_penalty_N=None if missing else penalty,missing_models=missing,
                incremental_payload_kg=sum(i["mass_kg"] for i in s["items"] if i["role"]=="payload" and i["mass_accounting"]=="incremental"),
                incremental_equipment_kg=sum(i["mass_kg"] for i in s["items"] if i["role"]=="equipment" and i["mass_accounting"]=="incremental"),
                item_mass_kg=sum(i["mass_kg"] for i in s["items"]),checks=checks,
                requested_checks_passed=aggregate(c["passed"] for c in checks),
                assumptions=[dict(path="onboard",value=deepcopy(s),source="explicit inputs / PRESSUPOSTO unless substantiated")],
                limitations=["Fixed allocation/duty, conservative simultaneous peaks; no hybrid propulsion dispatch or failure/redundancy scheduling.",
                             "Independent capacity/declared-heat/volume screens are not thermal design, CG closure or 3-D fit. Missing data stays unassessed.",
                             "Source/item masses owned once; main propulsion battery belongs to native sizing. Incremental means additional to existing engine-deck/airframe baseline."])
