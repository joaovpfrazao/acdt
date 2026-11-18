# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Schema 1.2 mixed fleets: bounded enumeration of station assignments over supplied types.

Each station is served by ONE supplied, already-assessed candidate type (its chosen
dwell row from the homogeneous N1 evaluation). All type subsets up to
``max_types`` and all positive station splits are enumerated (bounded, no
search heuristic). Optional shared ground pools put all types in ONE
deterministic DES queue (core.concept.ground_queue); otherwise each type keeps
its own homogeneous schedule (fleet_feedback.fleet or its own pools). Mixes are
compared by Pareto dominance (Deb 2001) per objective; no weighted winner.
"""
import itertools
from copy import deepcopy
from acdt.core.energy_storage import mapping, aggregate
from acdt.core.concept import tradeoff, ground_queue as GQ
from acdt.core.concept.fleet_feedback import text, fleet

MIX_METRICS = {"fleet_required", "fleet_mtow_kg", "energy_rate_Wh_per_h", "fuel_rate_kg_per_h", "n_types"}
MAX_MIXES = 512


def validate_mixed(m, candidate_ids, operations):
    mapping(m, {"members", "max_types", "shared_ground", "objectives", "min_stations_by_type", "source"}, "mixed_fleet")
    text(m.get("source"), "mixed_fleet.source")
    mem = m.get("members")
    if not isinstance(mem, list) or not 2 <= len(mem) <= 6 or len(set(mem)) != len(mem) or set(mem) - set(candidate_ids):
        raise ValueError("mixed_fleet.members: 2..6 distinct declared candidate ids")
    k = m.get("max_types", 2)
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= min(4, len(mem)):
        raise ValueError("mixed_fleet.max_types: integer 1..min(4, members)")
    if not isinstance(m.get("shared_ground", False), bool): raise ValueError("shared_ground must be boolean")
    if m.get("shared_ground") and "ground_resources" not in operations:
        raise ValueError("shared_ground needs operations.ground_resources pools")
    ms = m.get("min_stations_by_type", {})
    if not isinstance(ms, dict) or set(ms) - set(mem) or any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= operations["n_stations"] for v in ms.values()) \
            or sum(ms.values()) > operations["n_stations"]:
        raise ValueError("min_stations_by_type: member id -> integer stations, total <= n_stations (explicit mission requirement)")
    obj = m.get("objectives")
    if not isinstance(obj, dict) or not obj or set(obj) - MIX_METRICS or any(v not in ("min", "max") for v in obj.values()):
        raise ValueError("mixed_fleet.objectives: explicit min|max over " + str(sorted(MIX_METRICS)))
    n = operations["n_stations"]
    total = sum(_compositions_count(n, j) * _choose(len(mem), j) for j in range(1, k + 1))
    if total > MAX_MIXES: raise ValueError(f"{total} mixes exceed bound {MAX_MIXES}; reduce members/max_types/stations")


def _choose(n, k):
    from math import comb
    return comb(n, k)


def _compositions_count(n, j):
    from math import comb
    return comb(n - 1, j - 1) if n >= j else 0


def _compositions(n, j):
    for cuts in itertools.combinations(range(1, n), j - 1):
        b = (0,) + cuts + (n,)
        yield [b[i + 1] - b[i] for i in range(j)]


def _rates(row, model):
    sp = row["on_station_h"]
    E, F = row.get("mission_energy_Wh"), row.get("mission_fuel_kg")
    # a quantity a type does not carry is a KNOWN zero (electric → no fuel, pure fuel → no battery energy);
    # both unknown stays unknown
    if E is None and F is None: return None, None
    return E, F


def evaluate_mixed(spec, rows):
    m = spec["mixed_fleet"]; o = spec["operations"]
    pools = (o.get("ground_resources") or {}).get("pools", {})
    A = fleet(1., 0., 0., o)["availability"]; conf = o.get("confidence")
    shared = m.get("shared_ground", False)
    out = []
    for s in spec["mission"]["samples"]:
        by = {r["candidate_id"]: r for r in rows if r["sample"]["id"] == s["id"]}
        info, excluded = {}, []
        for cid in m["members"]:
            n1 = by[cid]["n1"]; pol = n1.get("dwell_policy", "requested")
            row = (n1.get("operations_by_dwell") or {}).get(pol)
            model = next(c for c in spec["candidates"] if c["id"] == cid).get("recipe", {}).get("model")
            if n1.get("eligible") is not True or not row or row.get("flight_duration_h") is None:
                excluded.append(dict(id=cid, status=n1.get("status"), reason="homogeneous evaluation not eligible/assessed"))
                continue
            if shared and not row.get("ground_activities"):
                excluded.append(dict(id=cid, reason="shared_ground requires a ground_process for every member")); continue
            info[cid] = dict(row=row, mtow=n1.get("mtow_kg"), model=model,
                             cand=next(c for c in spec["candidates"] if c["id"] == cid))
        mixes = []
        ids = list(info)
        for j in range(1, min(m.get("max_types", 2), len(ids)) + 1):
            for subset in itertools.combinations(ids, j):
                for split in _compositions(o["n_stations"], j):
                    need = {c: v for c, v in (m.get("min_stations_by_type") or {}).items() if v > dict(zip(subset, split)).get(c, 0)}
                    if need:
                        mid = "+".join(f"{c}×{k}" for c, k in zip(subset, split))
                        mixes.append(dict(id=mid, types=[dict(id=c, stations=k) for c, k in zip(subset, split)], assessed=False,
                                          status="violates_min_stations_by_type", issues=["min_stations:" + ",".join(sorted(need))], metrics={}))
                        continue
                    mixes.append(_one(subset, split, info, o, pools, A, conf, shared))
        alts = [dict(id=x["id"], metrics=x["metrics"]) for x in mixes if x["assessed"]]
        comp = tradeoff.compare(alts, m["objectives"]) if alts else dict(pareto=[], rows=[])
        out.append(dict(sample_id=s["id"], members_assessed=ids, excluded_members=excluded, mixes=mixes,
                        n_mixes=len(mixes), comparison=comp, pareto=comp["pareto"],
                        interpretation="nondominated station-assignment mixes of supplied assessed types for the SAME sample; "
                                       "no weighted winner, no cross-sample claim; unassessed mixes retained"))
    return dict(method="bounded enumeration of type subsets × positive station splits; Pareto (Deb 2001)",
                shared_ground=shared, samples=out,
                limitations=["Each station served by one type at its own chosen dwell; no alternating types on one station, "
                             "no handoff between types, no mission-specific capability weighting.",
                             "Shared ground = one deterministic FIFO DES for all types (no priorities); otherwise types are independent.",
                             "Different coverage classes (pointmass/jet/VTOL) are combined only by their scoped native results."])


def _one(subset, split, info, o, pools, A, conf, shared):
    mid = "+".join(f"{c}×{k}" for c, k in zip(subset, split))
    res = dict(id=mid, types=[dict(id=c, stations=k) for c, k in zip(subset, split)], assessed=False, issues=[], metrics={})
    stations, start = {}, 0
    for c, k in zip(subset, split):
        stations[c] = list(range(start, start + k)); start += k
    fleet_by, ops_by = {}, {}
    if shared:
        types = []
        for c in subset:
            r = info[c]["row"]
            types.append(dict(id=c, flight_h=r["flight_duration_h"], on_station_h=r["on_station_h"],
                              acts=deepcopy(r["ground_activities"]), stations=stations[c]))
        st = GQ.validate_process(info[subset[0]]["cand"]["ground_process"], pools)
        q = GQ.fleet_with_resources(types[0]["on_station_h"], o["handoff_overlap_h"], o["n_stations"], types, pools, st, A, conf)
        res["shared_ground"] = q
        if not q["assessed"]:
            res["issues"] += q["issues"]; res["status"] = q["status"]; return res
        fleet_by = q["fleet_for_confidence_by_type"] if conf is not None else q["fleet_expected_by_type"]
        if any(v is None for v in fleet_by.values()):
            res["issues"].append("confidence_fleet_search_limit"); return res
    else:
        for c in subset:
            r = info[c]["row"]
            if r.get("ground_activities"):
                st = GQ.validate_process(info[c]["cand"]["ground_process"], pools)
                q = GQ.fleet_with_resources(r["on_station_h"], o["handoff_overlap_h"], len(stations[c]),
                                            [dict(id=c, flight_h=r["flight_duration_h"], acts=deepcopy(r["ground_activities"]),
                                                  stations=list(range(len(stations[c]))))], pools, st, A, conf)
                ops_by[c] = q
                n = (q.get("fleet_for_confidence") if conf is not None else q.get("fleet_expected")) if q["assessed"] else None
            else:
                g = (r.get("turnaround") or {}).get("duration_h")
                if g is None:
                    res["issues"].append(c + ": ground time unassessed"); return res
                f = fleet(r["on_station_h"], r["off_station_flight_h"], g, dict(o, n_stations=len(stations[c])))
                ops_by[c] = f
                n = f["fleet_for_confidence"] if conf is not None else f["fleet_expected"]
                if not f["cycle"]["feasible"]: n = None
            if n is None:
                res["issues"].append(c + ": schedule infeasible or unassessed"); return res
            fleet_by[c] = n
        res["per_type_operations"] = ops_by
    E = F = 0.
    for c in subset:
        r = info[c]["row"]; k = len(stations[c]); sp = r["on_station_h"] - o["handoff_overlap_h"]
        e, f = _rates(r, info[c]["model"])
        if e is None and f is None:
            res["issues"].append(c + ": consumption unassessed"); return res
        E += k * (e or 0.) / sp; F += k * (f or 0.) / sp
    mt = [info[c]["mtow"] for c in subset]
    res.update(assessed=True, status="assessed", fleet_by_type=fleet_by,
               metrics=dict(fleet_required=sum(fleet_by.values()),
                            fleet_mtow_kg=sum(fleet_by[c] * info[c]["mtow"] for c in subset) if all(x is not None for x in mt) else None,
                            energy_rate_Wh_per_h=E, fuel_rate_kg_per_h=F, n_types=len(subset)),
               rate_note="consumption per hour of continuous coverage: Σ stations·(sortie energy or fuel)/launch spacing; "
                         "a carrier a type does not use counts as known zero")
    return res
