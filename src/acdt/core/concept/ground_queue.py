# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Shared ground resources: deterministic discrete-event fleet/queue simulation (opt-in).

Next-event time-advance discrete-event simulation (Law, *Simulation Modeling and
Analysis*, 5th ed., McGraw-Hill, 2015, Ch. 1-2) of a periodic launch schedule
served by a pooled fleet and FIFO multi-server ground resources (chargers,
refuel points, crews). Deterministic arrivals and service give a D/D/c-type
system; stability requires utilisation rho_r = lambda * d_r / c_r < 1 per
resource (Kleinrock, *Queueing Systems Vol. 1*, Wiley, 1975, Sec. 2.1/3.1;
Little's law L = lambda W, Little, Oper. Res. 9(3), 1961). No stochastic
(Erlang/M/M/c) delays, priorities, failures or preemption are modelled.

Loop (fleet size <-> turnaround): for each trial fleet N the simulation gives the
actual ground time (queue wait + service) and missed launches; N increases from
a lower bound until no launch is missed and ground times are steady. With a
FIXED launch schedule queue waits depend on resource counts and the schedule,
not on N; N acts through aircraft availability (missed launches). History reported.
"""
import heapq
import math
from collections import deque
from fractions import Fraction
from acdt.core.energy_storage import mapping, number

REF = ("Law 2015 'Simulation Modeling and Analysis' 5th ed. Ch.1-2 (next-event DES); Kleinrock 1975 "
       "'Queueing Systems Vol.1' (utilisation, stability); Little 1961 Oper. Res. 9(3):383-387 (L = lambda W)")
SETTINGS = {"horizon_cycles": 40, "max_extra_aircraft": 200, "steady_tolerance_h": 1e-6}


def validate_pools(pools):
    mapping(pools, {"pools", "source"}, "operations.ground_resources")
    if not isinstance(pools.get("source"), str) or not pools["source"].strip():
        raise ValueError("ground_resources.source required")
    p = pools.get("pools")
    if not isinstance(p, dict) or not p:
        raise ValueError("ground_resources.pools must map resource id -> integer count")
    for k, v in p.items():
        if not isinstance(k, str) or not k or isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 1000:
            raise ValueError("resource pool counts must be integers 1..1000 (no default count)")
    return p


def validate_process(proc, pools=None):
    mapping(proc, {"activities", "source", "settings"}, "ground_process")
    if not isinstance(proc.get("source"), str) or not proc["source"].strip():
        raise ValueError("ground_process.source required")
    acts = proc.get("activities")
    if not isinstance(acts, list) or not 1 <= len(acts) <= 12:
        raise ValueError("ground_process.activities: 1..12 serial activities")
    ids = set()
    for a in acts:
        mapping(a, {"id", "resource", "duration_h", "duration", "average_input_W", "efficiency", "flow_kg_h"}, "ground activity")
        if not isinstance(a.get("id"), str) or not a["id"] or a["id"] in ids:
            raise ValueError("ground activity ids must be unique nonempty text")
        ids.add(a["id"])
        r = a.get("resource")
        if r is not None and (pools is not None and r not in pools):
            raise ValueError(f"activity {a['id']} uses undeclared resource {r!r}")
        kind = a.get("duration", "fixed")
        if kind == "fixed":
            if set(a) - {"id", "resource", "duration_h", "duration"}: raise ValueError("fixed activity has ignored fields")
            number("duration_h", a.get("duration_h"))
        elif kind == "charge":
            if set(a) - {"id", "resource", "duration", "average_input_W", "efficiency"}: raise ValueError("charge activity has ignored fields")
            number("average_input_W", a.get("average_input_W"), positive=True)
            number("charge efficiency", a.get("efficiency"), positive=True, maximum=1)
        elif kind == "refuel":
            if set(a) - {"id", "resource", "duration", "flow_kg_h"}: raise ValueError("refuel activity has ignored fields")
            number("flow_kg_h", a.get("flow_kg_h"), positive=True)
        else:
            raise ValueError("activity duration must be fixed (duration_h), charge or refuel")
    st = dict(SETTINGS, **(proc.get("settings") or {}))
    mapping(proc.get("settings") or {}, set(SETTINGS), "ground_process.settings")
    for k in ("horizon_cycles", "max_extra_aircraft"):
        if isinstance(st[k], bool) or not isinstance(st[k], int) or not 4 <= st[k] <= 2000:
            raise ValueError(k + " must be integer 4..2000")
    number("steady_tolerance_h", st["steady_tolerance_h"], positive=True)
    return st


def durations(proc, energy_Wh=None, fuel_kg=None, multiple_packs=False):
    """Service durations from the closed sortie; unknown energy/fuel -> None (unassessed, never zero)."""
    out, issues = [], []
    for a in proc["activities"]:
        k = a.get("duration", "fixed")
        if k == "fixed":
            d = a["duration_h"]
        elif k == "charge":
            if energy_Wh is None or multiple_packs:
                issues.append(f"{a['id']}: charging energy unassessed"); d = None
            else:
                d = energy_Wh / (a["efficiency"] * a["average_input_W"])
        else:
            if fuel_kg is None:
                issues.append(f"{a['id']}: refuel mass unassessed"); d = None
            else:
                d = fuel_kg / a["flow_kg_h"]
        out.append(dict(id=a["id"], resource=a.get("resource"), duration_h=d, kind=k))
    return out, issues


def simulate(spacing_h, n_stations, streams, pools, n_aircraft, horizon_h):
    """One deterministic run. streams: [{type, flight_h, acts:[{resource,duration_h}], stations:[...] , n_aircraft}]
    — one homogeneous stream per aircraft type; pools shared by all streams."""
    ev, seq = [], 0

    def push(t, pri, kind, data):
        nonlocal seq
        heapq.heappush(ev, (t, pri, seq, kind, data)); seq += 1

    busy = {r: 0 for r in pools}; busy_time = {r: 0.0 for r in pools}
    queues = {r: deque() for r in pools}
    ready = []
    sorties = []
    for si, s in enumerate(streams):
        ready.append(deque((si, i) for i in range(s["n_aircraft"])))
        for st in s["stations"]:
            sp = s.get("spacing_h", spacing_h)
            offset = sp * st / n_stations
            k = 0
            while offset + k * sp < horizon_h:
                push(offset + k * sp, 2, "launch", (si, st)); k += 1
    missed = []

    def start(t, a, si, i, rec):
        act = streams[si]["acts"][i]
        r = act["resource"]
        if r is not None:
            busy[r] += 1; busy_time[r] += act["duration_h"]
        rec["waits"].append(t - rec["_enq"])
        push(t + act["duration_h"], 0, "finish", (a, si, i, rec))

    def enter(t, a, si, i, rec):
        acts = streams[si]["acts"]
        if i == len(acts):
            rec["ready_h"] = t; ready[si].append(a); return
        r = acts[i]["resource"]
        rec["_enq"] = t
        if r is None or busy[r] < pools[r]:
            start(t, a, si, i, rec)
        else:
            queues[r].append((a, si, i, rec))

    while ev:
        t, pri, _, kind, data = heapq.heappop(ev)
        if kind == "launch":
            si, st = data
            if ready[si]:
                a = ready[si].popleft()
                rec = dict(stream=si, station=st, launch_h=t, land_h=t + streams[si]["flight_h"], waits=[])
                sorties.append(rec)
                push(rec["land_h"], 1, "land", (a, si, rec))
            else:
                missed.append(dict(stream=si, station=st, time_h=t))
        elif kind == "land":
            a, si, rec = data
            enter(t, a, si, 0, rec)
        else:
            a, si, i, rec = data
            r = streams[si]["acts"][i]["resource"]
            if r is not None:
                busy[r] -= 1
                if queues[r]:
                    b = queues[r].popleft(); start(t, *b)
            enter(t, a, si, i + 1, rec)
    return sorties, missed, busy_time


def _stats(sorties, horizon_h):
    done = [s for s in sorties if "ready_h" in s]
    def window(lo, hi):
        g = [s["ready_h"] - s["land_h"] for s in done if lo <= s["land_h"] < hi]
        w = [sum(s["waits"]) for s in done if lo <= s["land_h"] < hi]
        return g, w
    half = horizon_h / 2
    g3, _ = window(half, 0.75 * horizon_h)
    g4, w4 = window(0.75 * horizon_h, horizon_h)
    gs, ws = window(half, horizon_h)
    return dict(ground_max_h=max(gs) if gs else None, ground_mean_h=sum(gs) / len(gs) if gs else None,
                wait_max_h=max(ws) if ws else None, wait_mean_h=sum(ws) / len(ws) if ws else None,
                third_quarter_ground_max_h=max(g3) if g3 else None, last_quarter_ground_max_h=max(g4) if g4 else None,
                sorties_in_window=len(gs))


def fleet_with_resources(on_station_h, overlap_h, n_stations, types, pools, settings, availability=1.0, confidence=None):
    """Minimal pooled fleet per type with shared FIFO resources. types: [{id, flight_h, acts, stations}].

    Increments the fleet of the type with missed launches (one aircraft per step, the type with most
    misses first) — a bounded deterministic search, not an optimiser. Returns history + states."""
    from . import reliability
    spacing = on_station_h - overlap_h
    sp = {t["id"]: (t["on_station_h"] - overlap_h if "on_station_h" in t else spacing) for t in types}
    out = dict(method=REF, assessed=False, status="unassessed", history=[], issues=[], pools=dict(pools),
               launch_spacing_h=spacing, stagger="stations offset uniformly by spacing/n_stations (PRESSUPOSTO)",
               dependency_note="queue waits depend on resources and the fixed launch schedule; fleet size acts through missed launches")
    if spacing <= 0 or min(sp.values()) <= 0:
        out.update(status="infeasible", issues=["no_effective_on_station_time"]); return out
    out["launch_spacing_by_type_h"] = dict(sp)
    lam = {t["id"]: len(t["stations"]) / sp[t["id"]] for t in types}
    util = {}
    for r, c in pools.items():
        work = sum(lam[t["id"]] * sum(a["duration_h"] for a in t["acts"] if a["resource"] == r) for t in types)
        util[r] = work / c
    out["utilisation"] = util
    out["minimum_stable_counts"] = {r: math.floor(u * pools[r] + 1e-12) + 1 for r, u in util.items()}
    sat = [r for r, u in util.items() if u >= 1 - 1e-12]
    if sat:
        out.update(status="resource_saturated", issues=["resource_saturated:" + ",".join(sat)]); return out
    # lower bound: concurrent aircraft in flight+service, pooled per type
    n = {}
    for t in types:
        svc = sum(a["duration_h"] for a in t["acts"])
        n[t["id"]] = max(1, math.ceil(Fraction(len(t["stations"])) * (Fraction(str(t["flight_h"])) + Fraction(str(round(svc, 12)))) / Fraction(str(sp[t["id"]]))))
    longest = max(t["flight_h"] + sum(a["duration_h"] for a in t["acts"]) for t in types)
    horizon = settings["horizon_cycles"] * max(max(sp.values()), longest) + longest
    limit = {k: v + settings["max_extra_aircraft"] for k, v in n.items()}
    while True:
        streams = [dict(type=t["id"], flight_h=t["flight_h"], acts=t["acts"], stations=t["stations"], n_aircraft=n[t["id"]],
                        spacing_h=sp[t["id"]]) for t in types]
        sorties, missed, busy = simulate(spacing, n_stations, streams, pools, None, horizon)
        st = _stats(sorties, horizon)
        steady = (st["third_quarter_ground_max_h"] is not None and st["last_quarter_ground_max_h"] is not None and
                  st["last_quarter_ground_max_h"] <= st["third_quarter_ground_max_h"] + settings["steady_tolerance_h"])
        miss_by = {t["id"]: sum(1 for m in missed if streams[m["stream"]]["type"] == t["id"]) for t in types}
        out["history"].append(dict(fleet_by_type=dict(n), missed_launches=len(missed), missed_by_type=miss_by,
                                   ground_max_h=st["ground_max_h"], wait_max_h=st["wait_max_h"], steady=steady))
        if not missed:
            if not steady:
                out.update(status="not_steady", issues=["ground_time_not_steady_within_horizon"]); return out
            break
        worst = max(miss_by, key=lambda k: (miss_by[k], k))
        n[worst] += 1
        if n[worst] > limit[worst]:
            out.update(status="fleet_search_limit", issues=["fleet_search_limit"]); return out
    k = sum(n.values())
    out.update(assessed=True, status="converged", fleet_in_cycle_by_type=dict(n), aircraft_needed_in_cycle=k,
               horizon_h=horizon, steady_window="second half of horizon", resource_busy_h=busy,
               ground_time=st, simulated_sorties=len(sorties))
    out["fleet_expected_by_type"] = {kk: math.ceil(Fraction(v) / Fraction(str(availability))) for kk, v in n.items()}
    out["fleet_expected"] = sum(out["fleet_expected_by_type"].values())
    if confidence is not None:
        by = {kk: reliability.min_n_for(v, availability, confidence) for kk, v in n.items()}
        out["fleet_for_confidence_by_type"] = by
        out["fleet_for_confidence"] = None if any(v is None for v in by.values()) else sum(by.values())
    out["availability_policy"] = "spares per type: ceil(k/A) or k-of-N confidence, as homogeneous fleet() convention"
    return out
