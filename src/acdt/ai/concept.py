"""Concept-trade toolkit for AI agents: deterministic, cited calculation primitives + fleet sizing + comparison +
study record. The agent decides *what* to evaluate (mission, requirements, alternatives); these functions only
calculate. Inputs are plain dicts/numbers (units in the argument names); every result carries ``method``
(the citation) and the assumptions/validity it relies on. Pass ``study_id`` (from :func:`study_start`) to log
the call and its result in the study's audit trail.

Methods: :mod:`acdt.core.concept` (geo, ops, search, reliability, tradeoff, study)."""
from __future__ import annotations

import copy
import functools
import inspect
import json
import math
from pathlib import Path

from acdt.core.concept import geo, ops, reliability as rel, search, study as S, tradeoff

from . import registry
from .toolkit import ToolError, clean

_STUDIES: dict[str, S.Study] = {}


# --------------------------------------------------------------------------------------------- study plumbing
def _study(study_id: str) -> S.Study:
    if study_id in _STUDIES:
        return _STUDIES[study_id]
    p = registry.runs_root() / "concept" / study_id / "study.json"
    if p.exists():
        red = json.loads(p.read_text(encoding="utf-8")).get("redirect")   # study kept in output_dir
        _STUDIES[study_id] = S.Study.load(Path(red) / "study.json" if red else p)
        return _STUDIES[study_id]
    raise ToolError(f"unknown study_id {study_id!r} — call concept_study_start first")


def logged(name: str):
    """Decorator: run the primitive, clean the result and, with ``study_id``, append the call to the study."""
    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, study_id: str | None = None, **kw):
            try:
                res = clean(fn(*a, **kw))
            except (ValueError, KeyError, TypeError, ZeroDivisionError) as e:
                raise ToolError(f"{name}: {e}") from e
            if study_id:
                st = _study(study_id)
                args = dict(inspect.signature(fn).bind_partial(*a, **kw).arguments)   # positional → named
                seq = st.log_call(name, clean(args), res)
                st.save()
                res = {**res, "study_call": seq}
            return res
        wrap.tool_name = name
        return wrap
    return deco


def study_start(title: str, problem: str, output_dir: str | None = None) -> dict:
    """Open a concept study (audit trail). ``problem`` = the user's own words. Default folder
    ``$ACDT_RUNS_DIR/concept/<id>``; ``output_dir`` to write it elsewhere (e.g. examples/output/concept/...)."""
    sid = S._slug(title)
    folder = Path(output_dir) if output_dir else registry.runs_root() / "concept" / sid
    st = S.Study(title, problem, folder, sid)
    st.data["git"] = registry.git_info()
    _STUDIES[sid] = st
    st.save()
    if output_dir:   # findable by id from the default root too
        link = registry.runs_root() / "concept" / sid
        link.mkdir(parents=True, exist_ok=True)
        (link / "study.json").write_text(json.dumps({"redirect": str(folder.resolve())}), encoding="utf-8")
    return {"study_id": sid, "folder": str(folder), "kinds": list(S.KINDS),
            "next": "add interpretation, assumptions (PRESSUPOSTO + rationale), sources (url + retrieved), "
                    "requirements (metric, threshold, justification), alternatives (incl. non-evaluable ones); "
                    "pass study_id to every calculation; finish with a recommendation and concept_study_report"}


def study_add(study_id: str, kind: str, content: dict | str) -> dict:
    """Add an entry: interpretation | assumption {text, rationale, source?} | question | requirement {text,
    metric, threshold, justification} | alternative {id, text, evaluable, how|reason} | source {text, url,
    retrieved} | finding | recommendation {text, chosen, rationale, sensitivities, not_evaluated, next_steps} |
    note."""
    st = _study(study_id)
    try:
        item = st.add(kind, content)
    except ValueError as e:
        raise ToolError(str(e)) from e
    st.save()
    return {"study_id": study_id, "kind": kind, "item": item}


def study_report(study_id: str) -> dict:
    """Write report.md (+ study.json) of the study; returns the paths and a completeness check."""
    st = _study(study_id)
    d = st.data
    gaps = [k for k in ("requirements", "alternatives", "calls") if not d[k]]
    if not d["assumptions"]:
        gaps.append("assumptions (state them, even if none — 'nenhum' is a statement)")
    if not d.get("recommendation"):
        gaps.append("recommendation")
    if not any(a.get("evaluable") is False for a in d["alternatives"]):
        gaps.append("no non-evaluable alternative listed — did you consider options the tools cannot size?")
    p = st.write_report()
    return {"study_id": study_id, "report": str(p), "study_json": str(st.folder / "study.json"),
            "completeness_gaps": gaps}


# --------------------------------------------------------------------------------------------- primitives
@logged("geo_measure")
def geo_measure(points: dict | None = None, legs: list | None = None, polygon: list | None = None) -> dict:
    """Great-circle distances of ``legs`` [[from, to], ...] between named ``points`` {name: [lat, lon]} and the
    area of ``polygon`` [[lat, lon], ...] (degrees)."""
    out = {"method": f"{geo.REF_HAV}; {geo.REF_AREA}",
           "validity": "spherical Earth; simple polygon without a pole; short edges"}
    pts = {k: tuple(v) for k, v in (points or {}).items()}
    if polygon:
        out["area_km2"] = geo.polygon_area_km2(polygon)
        out["polygon_reference_point"] = list(geo.centroid_deg(polygon))
        pts.setdefault("polygon_ref", out["polygon_reference_point"])
    if legs:
        out["legs"] = []
        for a, b in legs:
            if a not in pts or b not in pts:
                raise ValueError(f"leg {a}->{b}: unknown point (known: {', '.join(pts)})")
            out["legs"].append({"from": a, "to": b, "distance_km": geo.great_circle_km(*pts[a], *pts[b])})
    return out


@logged("transit_time")
def transit_time(distance_km: float, airspeed_m_s: float, headwind_m_s: float = 0.0) -> dict:
    """Outbound/return transit times [h] with a steady along-track headwind on the outbound leg."""
    return {**ops.transit(distance_km, airspeed_m_s, headwind_m_s),
            "method": "kinematics, ground speed V ∓ w", "validity": "steady wind along track; no climb/descent"}


@logged("sweep_coverage")
def sweep_coverage(area_km2: float, sweep_width_km: float, speed_m_s: float, n_on_station: float = 1.0,
                   time_h: float | None = None, pod_target: float | None = None) -> dict:
    """Sweep rate, time to sweep the area once (≈ revisit of an exhaustive patrol), POD after ``time_h``
    (Koopman random search — conservative; parallel sweep — upper bound) and the time to reach
    ``pod_target``. ``sweep_width_km`` is the sensor's effective sweep width for the target class (from a
    researched datasheet; W = 2 × definite detection range)."""
    sw = ops.sweep(area_km2, sweep_width_km, speed_m_s, n_on_station)
    out = {**sw, "method": search.REF_KOOPMAN,
           "validity": "uniform target location; W for the target class and sea state; detection only "
                       "(classification/identification time not included)"}
    if time_h is not None:
        out["pod_at_time"] = {"time_h": time_h, **search.pod(area_km2, sweep_width_km * n_on_station,
                                                             speed_m_s * 3.6 * time_h)}
    if pod_target is not None:
        e = search.effort_for_pod(area_km2, pod_target)
        out["for_pod_target"] = {"pod_target": pod_target, **e,
                                 "time_random_h": e["effort_random_km2"] / sw["sweep_rate_km2_h"],
                                 "time_parallel_h": e["effort_parallel_km2"] / sw["sweep_rate_km2_h"]}
    return out


def _avail(a) -> tuple[float, str]:
    if a is None:
        raise ValueError("availability: give a number in (0, 1] or {mtbf_h, mttr_h} / {mtbm_h, mdt_h}")
    if isinstance(a, (int, float)):
        if not 0 < a <= 1:
            raise ValueError("availability must be in (0, 1]")
        return float(a), "given"
    r = ops.availability(**a)
    k = "operational" if "operational" in r else "inherent"
    return r[k], k


@logged("persistent_coverage")
def persistent_coverage(endurance_h: float, turnaround_h: float, distance_km: float | None = None,
                        airspeed_m_s: float | None = None, headwind_m_s: float = 0.0,
                        t_out_h: float | None = None, t_back_h: float | None = None, reserve_h: float = 0.0,
                        handoff_overlap_h: float = 0.0, n_stations: int = 1, availability=1.0,
                        confidence: float | None = None, fleet_size: int | None = None) -> dict:
    """Continuous presence on ``n_stations`` stations: time on station per sortie, aircraft per station (Ha 2010
    cyclic schedule), fleet needed with availability (expected: ⌈k/A⌉; with ``confidence``: smallest N with
    P(≥ k available) ≥ confidence, binomial) and, for a given ``fleet_size``, the mean aircraft on station and
    P(the k needed are available)."""
    if t_out_h is None or t_back_h is None:
        if distance_km is None or airspeed_m_s is None:
            raise ValueError("give distance_km + airspeed_m_s, or t_out_h + t_back_h")
        tr = ops.transit(distance_km, airspeed_m_s, headwind_m_s)
        t_out_h, t_back_h = tr["t_out_h"], tr["t_back_h"]
    cyc = ops.cycle(endurance_h, t_out_h, t_back_h, turnaround_h, reserve_h, handoff_overlap_h)
    A, kind = _avail(availability)
    out = {"cycle": cyc, "availability": A, "availability_kind": kind, "t_out_h": t_out_h, "t_back_h": t_back_h,
           "method": f"{ops.REF_CYCLE}; {ops.REF_AVAIL}; {rel.REF_KN}",
           "validity": "deterministic cycle; aircraft availability independent (no common-cause grounding, "
                       "e.g. weather); hand-off gaps only as handoff_overlap_h"}
    if not cyc["feasible"]:
        return out
    k = int(n_stations) * cyc["aircraft_per_station"]
    out["aircraft_needed_in_cycle"] = k
    sortie_h = t_out_h + cyc["time_on_station_h"] + t_back_h          # reserve carried, not flown
    out["sorties_per_day"] = 24.0 * int(n_stations) / cyc["effective_time_on_station_h"]
    out["flight_hours_per_day"] = out["sorties_per_day"] * sortie_h
    out["fleet_expected"] = math.ceil(k / A - 1e-9)
    if confidence is not None:
        out["fleet_for_confidence"] = {"confidence": confidence, "n": rel.min_n_for(k, A, confidence)}
    if fleet_size is not None:
        out["fleet"] = {"n": int(fleet_size), **ops.presence(fleet_size, A, cyc),
                        "p_enough_available": rel.k_of_n(int(fleet_size), k, A)}
    return out




@logged("barrier_search")
def barrier_search(barrier_length_km: float, speed_m_s: float | None = None,
                   sweep_width_km: float | None = None, evader_speed_m_s: float | None = None,
                   crossing_window_h: float | None = None, corridor_width_km: float | None = None,
                   n_on_station: float = 1.0, endurance_h: float | None = None,
                   turnaround_h: float | None = None, distance_km: float | None = None,
                   airspeed_m_s: float | None = None, headwind_m_s: float = 0.0,
                   t_out_h: float | None = None, t_back_h: float | None = None,
                   reserve_h: float = 0.0, handoff_overlap_h: float = 0.0,
                   availability=1.0) -> dict:
    """Barrier / barrier-patrol search on a line or corridor the evader must cross (opt-in).

    Classical Koopman / Washburn barrier patrol: coverage factor z = n·W·V/(L·u), POD random /
    definite-range; reciprocating revisit τ = 2L/(n·V); cookie-cutter closed when τ ≤ crossing window.
    Optional Ha 2010 cyclic schedule when ``endurance_h`` and ``turnaround_h`` (+ transit) are given, to
    man the barrier continuously.

    Missing ``speed_m_s``, ``sweep_width_km`` (for POD), ``evader_speed_m_s`` (for POD), or
    ``endurance_h``/transit (for continuous fleet) → those metrics are **unassessed** (never a silent
    default that passes). Do not invent a radar's real sweep width.
    """
    unassessed: list[dict] = []
    out: dict = {
        "barrier_length_km": float(barrier_length_km),
        "n_on_station": float(n_on_station),
        "method": search.REF_BARRIER,
        "validity": ("barrier line/corridor; reciprocating revisit ignores turn time; POD is detection "
                     "opportunity (Koopman), not manufacturer Pd in clutter/sea state"),
    }
    if float(barrier_length_km) <= 0:
        raise ValueError("barrier_length_km must be > 0")

    window = crossing_window_h
    if window is None and corridor_width_km is not None and evader_speed_m_s is not None:
        u_kmh = float(evader_speed_m_s) * 3.6
        if u_kmh <= 0:
            raise ValueError("evader_speed_m_s must be > 0")
        window = float(corridor_width_km) / u_kmh
        out["crossing_window_h"] = window
        out["crossing_window_source"] = "corridor_width_km / evader_speed"
    elif window is not None:
        out["crossing_window_h"] = float(window)
        out["crossing_window_source"] = "supplied"

    if speed_m_s is None:
        unassessed.append({
            "metric": "revisit_and_close",
            "reason": "speed_m_s missing — barrier revisit/close unassessed (unknown ≠ zero; no silent default)",
        })
        out["revisit"] = {"status": "unassessed"}
        out["close"] = {"status": "unassessed"}
    else:
        rev = search.barrier_revisit(barrier_length_km, speed_m_s, n_on_station)
        out["revisit"] = {**rev, "status": "assessed"}
        if window is None:
            unassessed.append({
                "metric": "closed",
                "reason": "crossing_window_h (or corridor_width_km + evader_speed_m_s) missing — "
                          "closed/cookie-cutter unassessed",
            })
            out["close"] = {"status": "unassessed"}
        else:
            cl = search.barrier_close(barrier_length_km, speed_m_s, float(window), n_on_station)
            out["close"] = {**cl, "status": "assessed"}

    if speed_m_s is None or sweep_width_km is None or evader_speed_m_s is None:
        missing = [k for k, v in (("speed_m_s", speed_m_s), ("sweep_width_km", sweep_width_km),
                                    ("evader_speed_m_s", evader_speed_m_s)) if v is None]
        unassessed.append({
            "metric": "pod",
            "reason": f"missing {', '.join(missing)} — barrier POD unassessed (do not invent sweep width)",
        })
        out["pod"] = {"status": "unassessed"}
    else:
        pod = search.barrier_coverage_factor(barrier_length_km, sweep_width_km, speed_m_s,
                                             evader_speed_m_s, n_on_station)
        out["pod"] = {**pod, "status": "assessed", "sweep_width_km": float(sweep_width_km)}

    continuous_requested = any(v is not None for v in
                               (endurance_h, turnaround_h, distance_km, t_out_h, t_back_h))
    if continuous_requested:
        if endurance_h is None or turnaround_h is None:
            unassessed.append({
                "metric": "continuous_barrier_fleet",
                "reason": "continuous manning requested but endurance_h and/or turnaround_h missing — unassessed",
            })
            out["continuous"] = {"status": "unassessed"}
        else:
            to, tb = t_out_h, t_back_h
            if to is None or tb is None:
                spd = airspeed_m_s if airspeed_m_s is not None else speed_m_s
                if distance_km is None or spd is None:
                    unassessed.append({
                        "metric": "continuous_barrier_fleet",
                        "reason": "need distance_km + airspeed_m_s (or speed_m_s) or t_out_h + t_back_h",
                    })
                    out["continuous"] = {"status": "unassessed"}
                    to = tb = None
                else:
                    tr = ops.transit(float(distance_km), float(spd), headwind_m_s)
                    to, tb = tr["t_out_h"], tr["t_back_h"]
            if to is not None and tb is not None:
                cyc = ops.cycle(float(endurance_h), float(to), float(tb), float(turnaround_h),
                                reserve_h, handoff_overlap_h)
                A, kind = _avail(availability)
                cont = {"cycle": cyc, "availability": A, "availability_kind": kind,
                        "t_out_h": to, "t_back_h": tb,
                        "method": f"{ops.REF_CYCLE}; n_on_station × aircraft_per_station"}
                if cyc.get("feasible"):
                    k = int(math.ceil(float(n_on_station) - 1e-12)) * cyc["aircraft_per_station"]
                    cont["status"] = "assessed"
                    cont["aircraft_needed_in_cycle"] = k
                    cont["fleet_expected"] = math.ceil(k / A - 1e-9)
                    cont["note"] = ("n_on_station searchers held on the barrier; Ha 2010 multiplies by "
                                    "aircraft_per_station for transit/turnaround")
                else:
                    cont["status"] = "infeasible"
                    unassessed.append({
                        "metric": "continuous_barrier_fleet",
                        "reason": cyc.get("reason", "Ha 2010 cycle infeasible"),
                    })
                out["continuous"] = cont

    out["unassessed"] = unassessed
    out["fully_assessed"] = len(unassessed) == 0
    return out

@logged("radar_horizon")
def radar_horizon(h_sensor_m: float, h_target_m: float = 0.0, k: float = 4.0 / 3.0) -> dict:
    """Line-of-sight horizon to a target of height ``h_target_m`` (4/3-earth radar; k=1 geometric)."""
    return {**search.horizon_km(h_sensor_m, h_target_m, k), "method": search.REF_HORIZON,
            "validity": "standard atmosphere refraction; ducting/sub-refraction not modelled"}


@logged("sensor_footprint")
def sensor_footprint(altitude_m: float, fov_cross_deg: float, fov_along_deg: float | None = None,
                     depression_deg: float = 90.0) -> dict:
    """Flat-earth ground footprint (nadir swath, or near/far ground range and far swath when oblique)."""
    return {**search.footprint(altitude_m, fov_cross_deg, fov_along_deg, depression_deg),
            "method": "flat-earth trigonometry", "validity": "h ≪ Earth radius; ranges ≪ horizon"}


@logged("johnson_range")
def johnson_range(target_dim_m: float, task: str = "detection", ifov_rad: float | None = None,
                  pixel_pitch_um: float | None = None, focal_mm: float | None = None,
                  fov_deg: float | None = None, pixels: int | None = None) -> dict:
    """Max slant range for detection / orientation / recognition / identification (Johnson 1958, 50 %)."""
    return {**search.johnson_range(target_dim_m, task, ifov_rad, pixel_pitch_um, focal_mm, fov_deg, pixels),
            "method": search.REF_JOHNSON,
            "validity": "50 % task probability; geometric resolution only (no atmosphere, contrast, MTF, motion)"}


@logged("fleet_reliability")
def fleet_reliability(n: int, k: int, p_success: float | None = None, p_fail: float | None = None,
                      lambda_per_fh: float | None = None, t_h: float | None = None,
                      confidence: float | None = None) -> dict:
    """P(at least k of n succeed) — binomial k-of-N. Unit success from ``p_success``, ``1 − p_fail`` or
    exp(−λ t) (e.g. λ = the catastrophic rate per FH from safety_assessment). Optional smallest n for
    ``confidence``. Compare 1-of-1 against k-of-N to show fleet redundancy."""
    if p_success is None:
        if p_fail is not None:
            p_success = 1.0 - float(p_fail)
        elif lambda_per_fh is not None and t_h is not None:
            p_success = rel.sortie_success(lambda_per_fh, t_h)
        else:
            raise ValueError("give p_success, p_fail or (lambda_per_fh, t_h)")
    out = {"n": n, "k": k, "p_unit": p_success, "p_at_least_k": rel.k_of_n(n, k, p_success),
           "p_single_unit": p_success, "method": rel.REF_KN,
           "validity": "independent identical units; constant rate; no common cause"}
    if confidence is not None:
        out["n_for_confidence"] = rel.min_n_for(k, p_success, confidence)
    return out


@logged("compare_alternatives")
def compare_alternatives(alternatives: list, objectives: dict, constraints: dict | None = None,
                         weights: dict | None = None, plot: dict | None = None, title: str | None = None,
                         _study_folder: str | None = None) -> dict:
    """Constraint screening + Pareto front over ``objectives`` {metric: min|max}; weighted score only if
    ``weights`` are given (normalised terms shown). ``plot``: {x, y, labels?, file?} → PNG."""
    res = tradeoff.compare(alternatives, objectives, constraints, weights)
    if plot:
        f = plot.get("file") or f"pareto_{plot['x']}_{plot['y']}.png"
        folder = Path(_study_folder) if _study_folder else registry.runs_root() / "concept" / "_plots"
        folder.mkdir(parents=True, exist_ok=True)
        res["plot"] = tradeoff.plot(res, plot["x"], plot["y"], str(folder / Path(f).name), title, plot.get("labels"))
    return res


def compare(alternatives: list, objectives: dict, constraints: dict | None = None, weights: dict | None = None,
            plot: dict | None = None, title: str | None = None, show: list | None = None,
            study_id: str | None = None) -> dict:
    """compare_alternatives + (with study_id) the comparison is added to the study report and the plot is
    written in the study folder."""
    folder = str(_study(study_id).folder) if study_id else None
    res = compare_alternatives(alternatives, objectives, constraints, weights, plot, title,
                               _study_folder=folder, study_id=study_id)
    if study_id:
        st = _study(study_id)
        st.data["comparisons"].append({"title": title or "", "result": {k: v for k, v in res.items()
                                                                        if k != "study_call"},
                                       "plot": res.get("plot"), "show": show or []})
        if res.get("plot"):
            st.data["files"][Path(res["plot"]).name] = Path(res["plot"]).name
        st.save()
    return res


# --------------------------------------------------------------------------------------------- fleet sizing
def _req(res: dict, key: str):
    for r in res.get("requirements") or []:
        if r.get("key") == key:
            return r.get("value_si")
    return None


def _size_variant(v: dict) -> dict:
    from acdt.ai import toolkit as T
    from acdt.core.certification.basis import select_basis
    vid = v.get("id") or "variant"
    q = int(v.get("quantity", 1))
    src = {k: v.get(k) for k in ("spec", "spec_path", "example", "run_id") if v.get(k) is not None}
    if len(src) != 1:
        raise ValueError(f"{vid}: give exactly one of spec | spec_path | example | run_id")
    # level=None → do not override mission aero.fidelity (same policy as ``acdt size``).
    # Explicit level=L0|L1 forces handbook/lowfi. Previous default L0 silently disagreed with acdt size
    # on YAML files that declare fidelity: lowfi (Nansei / illegal_fishing discrepancy).
    level = v.get("level")  # may be None
    r = T.size(**src, level=level, no_systems=v.get("no_systems", True),
               assumptions=v.get("assumptions"))
    if r.get("status") != "done":
        return {"id": vid, "quantity": q, "status": r.get("status"), "error": r.get("error"), "run_id": r.get("run_id")}
    res = json.loads(Path(r["result_json"]).read_text(encoding="utf-8"))
    w, dp, g = res.get("weights") or {}, res.get("design_point") or {}, (res.get("geometry") or {}).get("wing") or {}
    pf = res.get("performance") or {}
    end_h = pf.get("endurance_h")
    ac = {"W0_kg": w.get("W0_kg"), "We_kg": w.get("We_kg"), "payload_kg": w.get("payload_kg"),
          "fuel_or_battery_kg": w.get("Wfuel_or_battery_kg"), "P_SL_W": dp.get("P_SL_W"), "T_SL_N": dp.get("T_SL_N"),
          "wing_span_m": g.get("span_m"), "wing_area_m2": g.get("S_m2"),
          "endurance_h": end_h, "range_km": pf.get("range_km"),
          "cruise_speed_m_s": _req(res, "cruise_speed"), "cruise_altitude_m": _req(res, "cruise_altitude")}
    prop = str(_req(res, "propulsion_type") or "")
    if ac["fuel_or_battery_kg"] and end_h and not prop.startswith("electric"):
        ac["fuel_kg_per_fh_approx"] = ac["fuel_or_battery_kg"] / end_h
    if level == "L0":
        fidelity = "handbook"
    elif level == "L1":
        fidelity = "lowfi"
    elif res.get("aero_lowfi"):
        fidelity = "lowfi_from_spec"
    else:
        fidelity = "from_spec"
    out = {"id": vid, "quantity": q, "status": "done", "run_id": r["run_id"],
           "level": level if level is not None else "spec",  # "spec" = mission YAML fidelity, like acdt size
           "level_requested": level,
           "fidelity": fidelity,
           "feasible": res.get("feasible"),
           "failed_checks": [c.get("key") for c in res.get("checks", []) if c.get("ok") is False],
           "aircraft": ac, "propulsion": prop, "assumed": [],
           "mtow_alignment": {
               "same_pipeline_as_acdt_size": True,
               "policy": ("omit level → keep mission aero.fidelity (identical to acdt size); "
                          "level=L0|L1 overrides fidelity"),
               "fleet_W0_meaning": "quantity × aircraft W0 from this size run (not a second mass model)",
               "opt_in_feed": "pass run_id from a prior acdt size / toolkit.size to reuse that result",
           }}
    if ac.get("fuel_kg_per_fh_approx") is not None:
        out["assumed"].append("fuel_kg_per_fh_approx = sized fuel (incl. reserves) / endurance — upper bound")
    # certification basis (existing catalogue rules)
    cert = select_basis(res, (src.get("spec") or {}).get("certification") if src.get("spec") else None)
    out["certification"] = {"bases": cert["bases"], "sora": cert["sora"], "rationale": cert["rationale"]}
    # acquisition cost (existing L0 CERs)
    if v.get("cost"):
        c = dict(v["cost"])
        if "N" not in c:
            raise ValueError(f"{vid}.cost: N (production quantity for the CER) is required")
        if "V_H_kt" not in c:
            if not ac["cruise_speed_m_s"]:
                raise ValueError(f"{vid}.cost: give V_H_kt")
            c["V_H_kt"] = ac["cruise_speed_m_s"] / 0.514444
            out["assumed"].append("cost V_H_kt = cruise speed (lower bound of V_H; Eastlake uses V_H)")
        if prop.startswith("piston") and "engine_cost" not in c and "power_bhp" not in c and ac["P_SL_W"]:
            c["power_bhp"] = ac["P_SL_W"] / 745.6999
            out["assumed"].append("engine cost from the Eastlake piston CER on the sized P_SL (no quote)")
        c.setdefault("unmanned", (w.get("crew_kg") or 0) <= 0)
        c.setdefault("propulsion", prop or None)
        ce = T.cost_estimate(We_kg=ac["We_kg"], **c)
        unit = (ce.get("eastlake") or ce.get("dapca4") or {}).get("unit_cost")
        out["cost"] = {"unit_cost_usd": unit, "year": ce.get("year"), "confidence": ce.get("confidence"),
                       "dapca4_unit_cost_usd": (ce.get("dapca4") or {}).get("unit_cost"), "notes": ce.get("notes"),
                       "inputs": {k: c[k] for k in c if k != "operating"}}
        if ce.get("operating"):
            out["cost"]["operating"] = ce["operating"]
    # per-sortie loss from the ARP4761 FTA (existing module)
    if v.get("safety") is not None:
        s = dict(v["safety"])
        s.setdefault("t_flight_h", end_h or 1.0)
        s.setdefault("mtow_kg", ac["W0_kg"])
        s.setdefault("scheme", "stanag4671" if (ac["W0_kg"] or 0) >= 150 else "stanag4703")
        sa = T.safety_assessment(**s)
        cc = sa["assessment"]["cumulative_catastrophic"]
        lam = cc["P_per_fh"]
        out["safety"] = {"scheme": s["scheme"], "template": s.get("template", "uas"), "t_flight_h": s["t_flight_h"],
                         "catastrophic_per_fh": lam, "target_per_fh": cc.get("target"), "meets": cc.get("ok"),
                         "p_loss_per_sortie": 1.0 - math.exp(-lam * s["t_flight_h"]),
                         "rate_kinds": sorted({c.get("kind") for c in sa["assessment"]["components"].values()}),
                         "note": "rates of kind 'assumption' are PRESSUPOSTOS (see acdt.core.safety.rates)"}
    per = {k: float(x) for k, x in (v.get("per_aircraft") or {}).items()}
    if per:
        out["per_aircraft"] = per
    return out


@logged("size_fleet")
def size_fleet(variants: list, level: str | None = None) -> dict:
    """Size each variant {id, spec|spec_path|example|run_id, quantity, level?, assumptions?, cost?: cost_estimate
    kwargs (N required), safety?: safety_assessment kwargs, per_aircraft?: {metric: value}} with the existing
    ``size`` pipeline and aggregate the fleet: Σ W0, Σ We, Σ installed power, Σ unit cost, Σ per-aircraft metrics,
    the certification basis and per-sortie loss of each variant.

    MTOW alignment (9 nov 2026): the same ``run_pipeline`` as ``acdt size``. Omitting ``level`` keeps the
    mission's ``aero.fidelity`` (so a fleet of one matches ``acdt size`` on that YAML). Passing
    ``level="L0"|"L1"`` overrides fidelity — then MTOW may differ from ``acdt size`` on the same file; the
    difference is reported per variant under ``mtow_alignment``, never a silent second mass model.
    Opt-in reuse: ``run_id`` of a prior size run. Unknown/missing sizing → variant status not done (not zero).
    """
    vs = []
    for v in variants:
        v = copy.deepcopy(v)
        if level and "level" not in v:
            v["level"] = level
        vs.append(_size_variant(v))
    tot = {"n_aircraft": 0, "W0_kg": 0.0, "We_kg": 0.0, "P_SL_W": 0.0, "payload_kg": 0.0}
    missing = []
    cost_ok = all(x.get("cost", {}).get("unit_cost_usd") is not None for x in vs if x["status"] == "done")
    if cost_ok:
        tot["acquisition_usd"] = 0.0
    else:
        missing.append("acquisition_usd: give cost {N, ...} for every variant")
    for x in vs:
        if x["status"] != "done":
            missing.append(f"{x['id']}: not sized ({x.get('error')})")
            continue
        q, ac = x["quantity"], x["aircraft"]
        tot["n_aircraft"] += q
        for k in ("W0_kg", "We_kg", "P_SL_W", "payload_kg"):
            tot[k] += q * (ac.get(k) or 0.0)
        if cost_ok:
            tot["acquisition_usd"] += q * x["cost"]["unit_cost_usd"]
        for k, val in (x.get("per_aircraft") or {}).items():
            tot[k] = tot.get(k, 0.0) + q * val
    levels = sorted({str(x.get("level")) for x in vs if x.get("status") == "done"})
    return {"variants": vs, "fleet": tot, "missing": missing, "all_feasible": all(x.get("feasible") for x in vs),
            "mtow_alignment": {
                "same_pipeline_as_acdt_size": True,
                "levels_used": levels,
                "policy": ("omit level → mission aero.fidelity (= acdt size); "
                           "explicit L0/L1 overrides — MTOW may then differ from acdt size on the same YAML"),
                "fleet_W0_kg": "Σ quantity × aircraft W0 (aggregate, not a parallel estimate)",
                "before_fix_note": ("prior default level=L0 forced handbook even when the YAML said lowfi, "
                                     "producing a silent MTOW gap vs acdt size (e.g. ~4.8 kg on "
                                     "uav_gasoline_150kg, ~7.5 kg on illegal_fishing variant_L)"),
            },
            "method": "acdt size pipeline per variant (see each run_id); cost: Eastlake/DAPCA IV L0 "
                      "(low confidence for unmanned — AACE Class 5); basis: acdt.core.certification.basis; "
                      "loss per sortie: ARP4761 low-fi FTA (acdt.domains.aircraft.safety_assessment)"}




def compare_size_fleet_mtow(spec_path: str, *, level: str | None = None, rel_tol: float = 1e-9,
                            abs_tol: float = 1e-6) -> dict:
    """Regression/diagnostic: ``size_fleet`` (quantity 1) vs ``toolkit.size`` / ``acdt size`` policy on the
    same mission YAML. Reports W0 on both paths and whether they agree.

    * ``level=None`` (default): both keep YAML fidelity → must agree.
    * ``level="L0"|"L1"``: both force that level → must agree with each other; may disagree with a bare
      ``acdt size`` that left the YAML fidelity unchanged — status ``comparable_forced_level`` with the
      YAML-fidelity W0 shown for reference.
    """
    from acdt.ai import toolkit as T
    path = str(spec_path)
    fleet = size_fleet(variants=[{"id": "cmp", "spec_path": path, "quantity": 1,
                                  **({"level": level} if level is not None else {})}])
    sized = T.size(spec_path=path, level=level, no_systems=True)
    # YAML-native (acdt size) reference when a forced level is in play
    yaml_native = None
    if level is not None:
        yaml_native = T.size(spec_path=path, level=None, no_systems=True)

    def _w0(summary_or_ac):
        if isinstance(summary_or_ac, dict) and "W0_kg" in summary_or_ac:
            return float(summary_or_ac["W0_kg"])
        return float((summary_or_ac.get("weights") or {}).get("W0_kg"))

    if fleet["variants"][0].get("status") != "done" or sized.get("status") != "done":
        return {"status": "unassessed",
                "reason": "sizing failed on one path — not comparable (unknown ≠ zero)",
                "size_fleet": fleet["variants"][0], "size": sized}

    w_fleet = float(fleet["variants"][0]["aircraft"]["W0_kg"])
    w_size = _w0(sized["summary"])
    agree = math.isclose(w_fleet, w_size, rel_tol=rel_tol, abs_tol=abs_tol)
    out = {
        "status": "agree" if agree else "disagree",
        "spec_path": path,
        "level": level if level is not None else "spec",
        "W0_size_fleet_kg": w_fleet,
        "W0_toolkit_size_kg": w_size,
        "delta_kg": w_fleet - w_size,
        "rel_tol": rel_tol, "abs_tol": abs_tol,
        "size_fleet_run_id": fleet["variants"][0].get("run_id"),
        "size_run_id": sized.get("run_id"),
        "note": "same run_pipeline; fleet of one must match toolkit.size at the same level policy",
    }
    if yaml_native and yaml_native.get("status") == "done":
        w_yaml = _w0(yaml_native["summary"])
        out["W0_acdt_size_yaml_fidelity_kg"] = w_yaml
        out["delta_forced_vs_yaml_kg"] = w_size - w_yaml
        out["status"] = ("agree_forced_level" if agree else "disagree")
        out["comparable_to_bare_acdt_size"] = math.isclose(w_size, w_yaml, rel_tol=rel_tol, abs_tol=abs_tol)
        if not out["comparable_to_bare_acdt_size"]:
            out["bare_acdt_size_note"] = (
                f"forcing level={level} changes W0 by {out['delta_forced_vs_yaml_kg']:.3f} kg vs YAML "
                f"fidelity (acdt size without override); not a second mass model — declare the level"
            )
    return out

# deterministic primitives that ``acdt concept replay`` may re-run (size_fleet only with --with-sizing)
REPLAYABLE = {f.tool_name: f for f in (geo_measure, transit_time, sweep_coverage, persistent_coverage,
                                       barrier_search, radar_horizon, sensor_footprint, johnson_range,
                                       fleet_reliability, compare_alternatives)}


def replay(path: str, with_sizing: bool = False, rel_tol: float = 1e-9) -> dict:
    """Re-run the logged deterministic calls of a study and compare the numeric results."""
    st = S.Study.load(Path(path))
    fns = dict(REPLAYABLE)
    if with_sizing:
        fns["size_fleet"] = size_fleet

    def diff(a, b, pre=""):
        out = []
        if isinstance(a, dict) and isinstance(b, dict):
            for k in a:
                if k in ("study_call", "run_id", "plot") or k not in b:
                    continue
                out += diff(a[k], b[k], f"{pre}.{k}")
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b)):
                out += diff(x, y, f"{pre}[{i}]")
        elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
            if not math.isclose(a, b, rel_tol=rel_tol, abs_tol=1e-12):
                out.append(f"{pre}: {a} != {b}")
        elif a != b and not isinstance(a, (dict, list)):
            out.append(f"{pre}: {a!r} != {b!r}")
        return out
    rows = []
    for c in st.data["calls"]:
        fn = fns.get(c["tool"])
        if fn is None:
            rows.append({"seq": c["seq"], "tool": c["tool"], "status": "skipped"})
            continue
        args = dict(c["args"])
        if c["tool"] == "compare_alternatives":          # replay the numbers, do not rewrite the plot
            args.pop("plot", None), args.pop("_study_folder", None)
        new = fn(**args)
        d = diff(c["result"], new)
        rows.append({"seq": c["seq"], "tool": c["tool"], "status": "same" if not d else "different", "diff": d[:10]})
    return {"study": st.data["id"], "calls": rows, "all_same": all(r["status"] != "different" for r in rows)}
