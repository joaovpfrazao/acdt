# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Homogeneous fleet feedback and explicit ground service bookkeeping.

Ha (2010), AFIT-OR-MS-ENS-10-03: existing ops.cycle; Blanchard & Fabrycky
(2011)/MIL-HDBK-338B availability; existing reliability k-of-N, O'Connor &
Kleyner (2012). Ground charge time = terminal energy / (efficiency * allocated
average input power), energy conservation, NIST SP811 (2008) Wh/W = h.
No charge curves, shared-resource queues, empirical turnaround defaults or
mixed-fleet scheduler. Dedicated resource per aircraft is an explicit input.
"""
import math
from fractions import Fraction
from . import ops, reliability
from acdt.core.energy_storage import number, mapping


def text(value,name):
    if not isinstance(value,str) or not value.strip(): raise ValueError(name+" requires nonempty text/source")


def interval(value,name,positive=False):
    if not isinstance(value,list) or len(value)!=2: raise ValueError(name+" needs [lower, upper]")
    a,b=[number(name,x,positive=positive) for x in value]
    if a>b: raise ValueError(name+" lower exceeds upper")
    return a,b


def fleet(on_station_h,off_station_flight_h,turnaround_h,settings):
    """Actual homogeneous schedule; NOT inferred max endurance or fleet optimum.

    ops.cycle depends on SUM of off-station time only. Aggregate flight and
    ground time in its off-time bucket to avoid subtractive cancellation; do not
    expose internal buckets as actual leg times.
    Native departure/arrival overhead can therefore be counted without guessing
    its split. Native reserve energy is retained, not flown/subtracted twice.
    """
    for name,v in (("on_station_h",on_station_h),("off_station_flight_h",off_station_flight_h),("turnaround_h",turnaround_h)):
        number(name,v)
    A=settings["availability"]
    if isinstance(A,dict):
        mapping(A,{"mtbf_h","mttr_h","mtbm_h","mdt_h"},"availability")
        for a,b in (("mtbf_h","mttr_h"),("mtbm_h","mdt_h")):
            if (a in A)!=(b in A): raise ValueError("availability needs complete time pairs")
            if a in A:number(a,A[a],positive=True);number(b,A[b])
        r=ops.availability(**A);A=r.get("operational",r.get("inherent"))
    number("availability",A,positive=True,maximum=1)
    n=settings["n_stations"]
    if isinstance(n,bool) or not isinstance(n,int) or n<1 or n>10000: raise ValueError("n_stations must be integer 1..10000")
    overlap=number("handoff_overlap_h",settings["handoff_overlap_h"])
    if "confidence" in settings:
        number("confidence",settings["confidence"],positive=True,maximum=1)
        if settings["confidence"]==1 and A<1: raise ValueError("finite fleet cannot guarantee confidence 1 with availability <1")
    c=ops.cycle(on_station_h,0.,0.,off_station_flight_h+turnaround_h,0.,overlap)
    if c["feasible"]:
        # PRESSUPOSTO: overlap is flown inside station time, not free removed
        # flight time. Repeat sortie every station-overlap hours; N intervals
        # must cover the full flight+ground cycle. Direct cyclic timeline identity.
        cycle_h=on_station_h+off_station_flight_h+turnaround_h
        effective=on_station_h-overlap
        # Exact decimal representations of declared times prevent .1+.2 noise
        # crossing an integer fleet boundary, without subtracting a tolerance.
        full=sum(Fraction(str(x)) for x in (on_station_h,off_station_flight_h,turnaround_h))
        spacing=Fraction(str(on_station_h))-Fraction(str(overlap))
        c.update(cycle_time_h=cycle_h,aircraft_per_station=math.ceil(full/spacing),
                 duty_cycle=effective/cycle_h,overlap_policy="flown once inside station time; repeat interval station-overlap")
    out=dict(cycle=c,scope="identical aircraft, supplied fixed-duration schedule; not maximum endurance",availability=A,
             on_station_h=on_station_h,off_station_flight_h=off_station_flight_h,ground_turnaround_h=turnaround_h,
             flight_duration_h=on_station_h+off_station_flight_h,fleet_expected=None,fleet_for_confidence=None,
             aircraft_needed_in_cycle=None,method=ops.REF_CYCLE+"; "+ops.REF_AVAIL+"; "+reliability.REF_KN)
    if c["feasible"]:
        k=n*c["aircraft_per_station"]
        out.update(aircraft_needed_in_cycle=k,fleet_expected=math.ceil(Fraction(k)/Fraction(str(A))))
        if "confidence" in settings:
            out["fleet_for_confidence"]=reliability.min_n_for(k,A,settings["confidence"])
            out["confidence_search_limit"]=200
    return out


def turnaround(spec,battery_terminal_Wh=None,has_fuel=False,multiple_packs=False):
    """Explicit aggregate ground time OR dedicated constant-average-power charging.

    supplied duration includes ALL ground activities. Charging fixed_h covers
    user-supplied remaining activities, serial or independent parallel. No default
    charger count: per-aircraft dedicated allocation means required fleet count
    chargers, not one charger shared by the whole fleet.
    """
    mapping(spec,{"method","duration_h","activity","average_input_W","efficiency","allocation","fixed_h","combine","source"},"turnaround")
    text(spec.get("source"),"turnaround.source")
    method=spec.get("method")
    if method=="supplied":
        if set(spec)-{"method","duration_h","activity","source"}: raise ValueError("supplied turnaround has ignored charging fields")
        text(spec.get("activity"),"turnaround.activity")
        dt=number("duration_h",spec.get("duration_h"))
        return dict(assessed=True,duration_h=dt,inputs=dict(spec),method="explicit supplied total ground duration",issues=[])
    if method!="charge": raise ValueError("turnaround method must be supplied or charge")
    if "duration_h" in spec or "activity" in spec: raise ValueError("charging uses derived service time plus fixed_h, not duration_h/activity")
    p=number("average_input_W",spec.get("average_input_W"),positive=True)
    eta=number("charge efficiency",spec.get("efficiency"),positive=True,maximum=1)
    fixed=number("fixed_h",spec.get("fixed_h"))
    if spec.get("combine") not in ("serial","parallel"): raise ValueError("declare serial or independent parallel ground activities")
    if spec.get("allocation")!="dedicated_per_aircraft":
        return dict(assessed=False,duration_h=None,inputs=dict(spec),issues=["shared_charger_queues_unimplemented"])
    if has_fuel or multiple_packs or battery_terminal_Wh is None:
        return dict(assessed=False,duration_h=None,inputs=dict(spec),issues=["charging_carrier_or_complete_energy_unassessed"])
    E=number("battery_terminal_Wh",battery_terminal_Wh)
    charge_h=E/(eta*p)
    return dict(assessed=True,duration_h=fixed+charge_h if spec["combine"]=="serial" else max(fixed,charge_h),
                charge_h=charge_h,battery_terminal_Wh=E,grid_Wh=E/eta,inputs=dict(spec),issues=[],
                resource_policy="one dedicated allocated charger per aircraft; no queue",method="E_terminal/(eta * allocated average input W); NIST SP811")
