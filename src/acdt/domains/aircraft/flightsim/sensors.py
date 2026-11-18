"""Sensor footprint and coverage along a flown track.

The numbers come from the concept primitives, not from a new detection model:

* ground footprint — flat-earth trigonometry (:func:`acdt.core.concept.search.footprint`);
* radar / geometric horizon — Skolnik 2001 Sec. 8.2 (:func:`acdt.core.concept.search.horizon_km`);
* Johnson slant range — Johnson 1958 (:func:`acdt.core.concept.search.johnson_range`);
* swept area ∫ W ds and POD — Koopman 1946/1980 and Washburn 2002 (:func:`acdt.core.concept.search.pod`
  and :func:`acdt.core.concept.ops.sweep`);
* persistent presence — Ha 2010 via :func:`acdt.core.concept.ops.cycle`.

The effective swath is the geometric swath capped by the horizon and, when a Johnson block is present, by the
ground range at which the slant range equals the Johnson range. Swept area is search effort W·L. It counts
repeated passes; it is not the union of the footprints. A full loiter orbit can also report the elementary
annulus of one swath about the circle.

Validity: detection opportunity only. Clutter, sea state and the manufacturer's POD curve are not in here —
``sweep_width`` is this geometric swath, not a datasheet effective sweep width, unless the caller passes
``sweep_width_km`` to override it.
"""
from __future__ import annotations

import math

from acdt.core.concept import ops, search

from .failures import FailureEvent

_JOHNSON = {"target_dim_m", "task", "ifov_rad", "pixel_pitch_um", "focal_mm", "fov_deg", "pixels"}
SENSOR_ON_DEFAULT = ("climb", "cruise", "turn", "waypoints", "loiter", "patrol", "descent")
ON_STATION_DEFAULT = ("loiter", "patrol")


def validate_sensor(block: dict) -> None:
    if not isinstance(block, dict):
        raise ValueError("sensor tem de ser um dicionário")
    if "fov_cross_deg" not in block and "sweep_width_km" not in block:
        raise ValueError("sensor: fov_cross_deg (pegada geométrica) ou sweep_width_km (largura dada)")
    if "fov_cross_deg" in block and float(block["fov_cross_deg"]) <= 0:
        raise ValueError("fov_cross_deg tem de ser > 0")
    dep = float(block.get("depression_deg", 90.0))
    if not 0 < dep <= 90:
        raise ValueError("depression_deg tem de estar em (0, 90]")
    j = block.get("johnson")
    if j is not None:
        extra = set(j) - _JOHNSON
        if extra:
            raise ValueError(f"johnson: chaves desconhecidas {sorted(extra)}")
        if "target_dim_m" not in j:
            raise ValueError("johnson precisa de target_dim_m")
    p = block.get("persistent")
    if p is not None:
        if "turnaround_h" not in p:
            raise ValueError("sensor.persistent precisa de turnaround_h (Ha 2010)")
        if ("distance_km" in p) ^ ("airspeed_m_s" in p):
            raise ValueError("persistent: distance_km e airspeed_m_s vêm juntos (trânsito de ops.transit)")


def geometric_footprint(h_m: float, cfg: dict) -> dict:
    """Footprint at altitude ``h_m``. A fixed ``sweep_width_km`` bypasses the trigonometry."""
    if cfg.get("sweep_width_km") is not None and "fov_cross_deg" not in cfg:
        w = float(cfg["sweep_width_km"])
        return {"swath_km": w, "near_range_km": 0.0, "far_range_km": 0.0, "source": "sweep_width_km"}
    fp = search.footprint(h_m, float(cfg["fov_cross_deg"]), cfg.get("fov_along_deg"),
                          float(cfg.get("depression_deg", 90.0)))
    if "swath_km" in fp:
        sw = fp["swath_km"]
    else:
        sw = fp.get("swath_far_km", 0.0)
    return {**fp, "swath_km": sw if math.isfinite(sw) else float("inf")}


def effective_swath(h_m: float, cfg: dict) -> dict:
    """Geometric swath capped by the horizon and by the Johnson ground range, when those are finite."""
    h = max(float(h_m), 0.0)
    geo = geometric_footprint(h, cfg)
    k = float(cfg.get("horizon_k", 4.0 / 3.0))
    hor = search.horizon_km(h, float(cfg.get("h_target_m", 0.0)), k)
    limit = float(geo["swath_km"])
    reason = "footprint" if "fov_cross_deg" in cfg else "sweep_width_km"
    horizon_km = hor["horizon_km"]
    if math.isfinite(horizon_km) and limit > 2.0 * horizon_km:
        limit = 2.0 * horizon_km
        reason = "horizon"
    johnson = None
    johnson_ground = None
    if cfg.get("johnson"):
        johnson = search.johnson_range(**{k_: cfg["johnson"][k_] for k_ in cfg["johnson"] if k_ in _JOHNSON})
        slant = float(johnson["max_range_km"])
        h_km = h / 1000.0
        johnson_ground = 0.0 if slant <= h_km else math.sqrt(max(slant * slant - h_km * h_km, 0.0))
        if limit > 2.0 * johnson_ground:
            limit = 2.0 * johnson_ground
            reason = "johnson"
    if not math.isfinite(limit) or limit < 0:
        limit = 0.0
    return {"swath_km": limit, "limit": reason, "footprint": geo, "horizon_km": horizon_km,
            "horizon_k": k, "johnson": johnson, "johnson_ground_km": johnson_ground,
            "method_footprint": "flat-earth trigonometry", "method_horizon": search.REF_HORIZON,
            "method_johnson": search.REF_JOHNSON if johnson else None}


def orbit_footprint_km2(radius_m: float, swath_km: float) -> float:
    """Area of one swath wrapped around a circle: π[(R+w/2)² − max(R−w/2, 0)²]. Elementary geometry of the
    footprint already computed; a second orbit does not add area. Not a detection law."""
    r = float(radius_m) / 1000.0
    w = float(swath_km)
    outer = r + 0.5 * w
    inner = max(r - 0.5 * w, 0.0)
    return math.pi * (outer * outer - inner * inner)


def _on(name: str, cfg: dict, key: str, default: tuple) -> bool:
    names = cfg.get(key)
    if names is None:
        names = default
    return name in names


def evaluate_sensors(samples: list[dict], cfg: dict, *, total_time_s: float | None = None,
                     orbits: list | None = None, persistent_override: dict | None = None) -> dict:
    """Integrate coverage along ``samples`` (each with t, N, E, h, segment, sensor_on)."""
    if not samples:
        return {"time_on_station_h": 0.0, "swept_area_km2": 0.0, "track_length_km": 0.0, "samples": 0}
    swept = 0.0
    length = 0.0
    sensed_s = 0.0
    on_station_s = 0.0
    swaths = []
    h_on = []
    v_on = []
    for i in range(1, len(samples)):
        a, b = samples[i - 1], samples[i]
        dt = max(float(b["t"]) - float(a["t"]), 0.0)
        ds_km = math.hypot(float(b["N"]) - float(a["N"]), float(b["E"]) - float(a["E"])) / 1000.0
        seg = b.get("segment") or ""
        if _on(seg, cfg, "on_station_segments", ON_STATION_DEFAULT) or b.get("on_station"):
            on_station_s += dt
        if b.get("sensor_on", True) and _on(seg, cfg, "on_segments", SENSOR_ON_DEFAULT):
            sw = effective_swath(float(b["h"]), cfg)
            swept += sw["swath_km"] * ds_km
            length += ds_km
            sensed_s += dt
            swaths.append(sw["swath_km"])
            h_on.append(float(b["h"]))
            if b.get("Va"):
                v_on.append(float(b["Va"]))
    h_ref = sum(h_on) / len(h_on) if h_on else float(samples[-1]["h"])
    sw_ref = effective_swath(h_ref, cfg)
    out = {
        "time_on_station_h": on_station_s / 3600.0,
        "time_sensing_h": sensed_s / 3600.0,
        "swept_area_km2": swept,
        "track_length_sensing_km": length,
        "mean_swath_km": (swept / length) if length > 1e-9 else sw_ref["swath_km"],
        "swath_at_mean_altitude": sw_ref,
        "altitude_mean_m": h_ref,
        "samples": len(samples),
        "method": f"{search.REF_KOOPMAN}; footprint flat-earth; {search.REF_HORIZON}",
        "validity": "área varrida = esforço W·L (passagens repetidas contam outra vez); não é a união das pegadas. "
                    "POD é oportunidade de deteção (Koopman), não a curva do fabricante.",
    }
    if cfg.get("johnson"):
        out["method"] += f"; {search.REF_JOHNSON}"
    area = cfg.get("area_km2")
    if area is not None and length > 1e-9:
        w_mean = swept / length
        out["pod"] = {"area_km2": float(area), "sweep_width_km": w_mean, "track_length_km": length,
                      **search.pod(float(area), w_mean, length)}
        if sensed_s > 0:
            v_mean = (sum(v_on) / len(v_on)) if v_on else length * 1000.0 / sensed_s
            out["sweep"] = {**ops.sweep(float(area), w_mean, v_mean), "method": ops.REF_SWEEP,
                            "speed_m_s": v_mean}
    if orbits:
        ann = []
        for o in orbits:
            if o.get("revolutions", 0) >= 0.95 and o.get("swath_km"):
                ann.append({"radius_m": o["radius_m"], "swath_km": o["swath_km"],
                            "orbit_footprint_km2": orbit_footprint_km2(o["radius_m"], o["swath_km"]),
                            "note": "área geométrica de uma órbita; órbitas extra não somam área"})
        if ann:
            out["orbits"] = ann
    p = persistent_override if persistent_override is not None else cfg.get("persistent")
    if p:
        out["persistent"] = _persistent(p, on_station_s / 3600.0, samples, total_time_s)
    return out


def _persistent(p: dict, t_on_h: float, samples: list, total_time_s: float | None) -> dict:
    """Ha 2010 cycle. Transit times are the caller's, or the simulated time before the first on-station
    sample and after the last one."""
    if p.get("distance_km") is not None:
        tr = ops.transit(float(p["distance_km"]), float(p["airspeed_m_s"]), float(p.get("headwind_m_s", 0.0)))
        t_out, t_back = tr["t_out_h"], tr["t_back_h"]
        origin = "ops.transit"
    elif "t_out_h" in p or "t_back_h" in p:
        t_out, t_back = float(p.get("t_out_h", 0.0)), float(p.get("t_back_h", 0.0))
        origin = "dado na missão"
    else:
        t_out, t_back = _flown_transit_h(samples)
        origin = "tempos de trânsito lidos do rasto simulado (antes e depois do tempo em estação)"
    endurance = float(p["endurance_h"]) if "endurance_h" in p else (
        (total_time_s / 3600.0) if total_time_s is not None else (samples[-1]["t"] - samples[0]["t"]) / 3600.0)
    # When the caller does not override endurance, the cycle uses the flown sortie. Time on station is the
    # simulated one, so endurance must cover transit + on-station + reserve. Rebuild endurance from the pieces
    # when the user did not pass it: t_out + t_on + t_back + reserve.
    reserve = float(p.get("reserve_h", 0.0))
    if "endurance_h" not in p:
        endurance = t_out + t_on_h + t_back + reserve
    cyc = ops.cycle(endurance, t_out, t_back, float(p["turnaround_h"]), reserve, float(p.get("handoff_overlap_h", 0.0)))
    out = {"cycle": cyc, "endurance_h": endurance, "t_out_h": t_out, "t_back_h": t_back,
           "time_on_station_h": t_on_h, "transit_origin": origin, "method": ops.REF_CYCLE,
           "validity": "ciclo determinístico; o tempo em estação é o simulado, não um requisito"}
    if not cyc.get("feasible"):
        return out
    n_stat = int(p.get("n_stations", 1))
    k = n_stat * cyc["aircraft_per_station"]
    out["aircraft_needed_in_cycle"] = k
    if "availability" in p or "mtbf_h" in p:
        if "availability" in p:
            A, kind = float(p["availability"]), "given"
        else:
            av = ops.availability(p.get("mtbf_h"), p.get("mttr_h"), p.get("mtbm_h"), p.get("mdt_h"))
            kind = "operational" if "operational" in av else "inherent"
            A = av[kind]
        out["availability"] = A
        out["availability_kind"] = kind
        out["fleet_expected"] = math.ceil(k / A - 1e-9)
        out["method"] += f"; {ops.REF_AVAIL}"
    return out


def _flown_transit_h(samples: list) -> tuple[float, float]:
    cfg_types = ON_STATION_DEFAULT
    times = [float(s["t"]) for s in samples]
    on = [i for i, s in enumerate(samples) if s.get("on_station") or s.get("segment") in cfg_types]
    if not on:
        return 0.0, 0.0
    t0, t1 = times[on[0]], times[on[-1]]
    return max(t0 - times[0], 0.0) / 3600.0, max(times[-1] - t1, 0.0) / 3600.0


def sensor_loss_times(events: list[FailureEvent], segments: list[dict] | None = None) -> list[float]:
    """Absolute times of ``sensor_loss`` events that already have ``t_s``, plus segment-relative triggers
    reconstructed from flown segment durations (``t_min``)."""
    times = []
    starts = []
    if segments:
        t = 0.0
        for s in segments:
            starts.append((s.get("segment"), s.get("type"), t))
            t += float(s.get("t_min", 0.0)) * 60.0
    for e in events:
        if e.type != "sensor_loss":
            continue
        if e.t_s is not None and e.segment is None and e.altitude_m_below is None and e.altitude_m_above is None \
                and e.fuel_fraction_below is None:
            times.append(e.t_s)
        elif e.segment is not None:
            for name, typ, t0 in starts:
                if e.segment in (name, typ):
                    times.append(t0 + e.t_into_s)
                    break
        elif e.t_s is not None:
            times.append(e.t_s)
    return times


def apply_sensor_loss(samples: list[dict], off_after: list[float]) -> None:
    if not off_after:
        return
    t_off = min(off_after)
    for s in samples:
        if float(s["t"]) + 1e-9 >= t_off:
            s["sensor_on"] = False


def _metrics_block(sensor_out: dict | None, total_time_s: float, total_dist_m: float,
                   t_on_s: float | None = None) -> dict:
    """Numbers an agent can pass to ``compare_alternatives``. Cost per flight hour is not computed."""
    t_on = sensor_out["time_on_station_h"] if sensor_out else (t_on_s or 0.0) / 3600.0
    m = {"time_on_station_h": t_on, "endurance_h": total_time_s / 3600.0, "range_km": total_dist_m / 1000.0,
         "area_swept_km2": sensor_out.get("swept_area_km2") if sensor_out else None}
    pod = (sensor_out or {}).get("pod") or {}
    if "pod_random_search" in pod:
        m["pod_random_search"] = pod["pod_random_search"]
        m["pod_parallel_sweep"] = pod["pod_parallel_sweep"]
    return m


def history_samples_6dof(result: dict) -> list[dict]:
    """One sample per 6-DOF log row (``MissionRunner.COLS``). ``segment`` is the segment type."""
    H = result.get("_H")
    cols = result.get("history_columns") or []
    if H is None or not len(H) or not cols:
        return []
    C = {k: i for i, k in enumerate(cols)}
    segs = result.get("segments") or []
    out = []
    for row in H:
        i_seg = int(row[C["seg"]])
        typ = segs[i_seg]["type"] if 0 <= i_seg < len(segs) else ""
        out.append({"t": float(row[C["t"]]), "N": float(row[C["N"]]), "E": float(row[C["E"]]),
                    "h": float(row[C["h"]]), "Va": float(row[C["Va"]]), "segment": typ, "sensor_on": True,
                    "on_station": typ in ON_STATION_DEFAULT})
    return out


def products_for_6dof(mission: dict, result: dict) -> dict:
    """Sensor metrics along the 6-DOF track, and the failure log.

    The same YAML is accepted. ``sensor_loss`` cuts coverage after the trigger. Trajectory-changing responses
    (RTB, divert, glide) are not flown: closed-loop failure dynamics stay at N2+ 6-DOF and are only recorded
    here (``executed`` false)."""
    from .failures import resolve_failures
    extra = {}
    events = resolve_failures(mission) if mission.get("failures") else []
    if mission.get("failures"):
        extra["failures"] = {
            "events": [e.to_dict() for e in events],
            "log": [{"t_s": e.t_s, "type": e.type, "response": e.response, "source": e.source, "fired": False,
                     "action": "não aplicada na trajetória 6-DOF (dinâmica de malha fechada adiada)"}
                    for e in events],
            "executed": False,
            "seed": mission["failures"].get("seed"),
            "note": "ganchos determinísticos; a resposta não altera a trajetória 6-DOF neste nível",
        }
    if mission.get("sensor"):
        samples = history_samples_6dof(result)
        apply_sensor_loss(samples, sensor_loss_times(events, result.get("segments")))
        sens = evaluate_sensors(samples, mission["sensor"],
                                total_time_s=float(result.get("total_time_min", 0.0)) * 60.0)
        extra["sensor"] = sens
        extra["metrics"] = _metrics_block(sens, float(result.get("total_time_min", 0.0)) * 60.0,
                                           float(result.get("total_dist_km", 0.0)) * 1000.0)
    return extra
