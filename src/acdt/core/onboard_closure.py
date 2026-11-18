# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in L0 onboard thermal / CG / spatial / FOV screens with open primitives.

Cited methods (no new dependencies, no heavy mesh solver required):
* Thermal load: energy conservation on electrical conversion — heat =
  declared item heat_W and/or P*(1/η−1) distribution loss and generator
  shaft*(1−η_gen) (same η already used for PowerBudget / Moir & Seabridge).
* Rejection: supplied capacity, or steady cooling-air energy balance
  Q = ṁ·cp·ΔT (Incropera & DeWitt, Fundamentals of Heat and Mass Transfer;
  open-system screening identity, not an ECS pack map).
* CG: Σ m·r / Σ m vs explicit envelope (Meriam & Kraige / Raymer mass props).
* Spatial: axis-aligned box containment, packing fraction, AABB overlap
  (same AABB primitive as assembly.integration).
* FOV: discrete az/el rays (González 2010 Fibonacci option unused here —
  same az/el grid as assembly.integration) vs AABB/sphere blockers via the
  classic slab ray–box test; missing FOV/blocker data stays unassessed.

PRESSUPOSTO: steady loads, constant rejection, boxes not detailed CAD,
ray step may miss thin blockers. Never treats missing data as pass.
"""
from __future__ import annotations
import math
from copy import deepcopy
from .energy_storage import mapping, number, aggregate


METHOD = (
    "Thermal: conversion-loss energy balance + Q=mdot*cp*dT cooling air (Incropera & DeWitt); "
    "CG: Σm·r; Spatial: AABB fit/overlap; FOV: az/el ray grid vs AABB/sphere (slab test). "
    "Electrical duty bookkeeping remains MIL-E-7016F / Moir & Seabridge as in core.onboard."
)


def _text(x, name):
    if not isinstance(x, str) or not x.strip():
        raise ValueError(name + " must be nonempty text / source")


def _signed(name, value, *, maximum=1e6):
    """Finite signed SI scalar for coordinates (energy_storage.number is non-negative)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if abs(value) > maximum:
        raise ValueError(f"{name} outside numerical domain")
    return float(value)


def _vec3(name, v):
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise ValueError(name + " must be length-3 [x,y,z]")
    return [_signed(name + f"[{i}]", v[i]) for i in range(3)]


def _box(spec, name):
    mapping(spec, {"lo", "hi", "center", "size_m"}, name)
    if "lo" in spec and "hi" in spec:
        lo, hi = _vec3(name + ".lo", spec["lo"]), _vec3(name + ".hi", spec["hi"])
        if any(hi[i] <= lo[i] for i in range(3)):
            raise ValueError(name + " needs hi > lo on every axis")
        return lo, hi
    if "center" in spec and "size_m" in spec:
        c, s = _vec3(name + ".center", spec["center"]), _vec3(name + ".size_m", spec["size_m"])
        if any(x <= 0 for x in s):
            raise ValueError(name + " size_m must be positive")
        return [c[i] - s[i] / 2 for i in range(3)], [c[i] + s[i] / 2 for i in range(3)]
    raise ValueError(name + " needs lo/hi or center/size_m")


def _item_box(pos, size):
    return [pos[i] - size[i] / 2 for i in range(3)], [pos[i] + size[i] / 2 for i in range(3)]


def _inside(inner_lo, inner_hi, outer_lo, outer_hi, tol=1e-9):
    return all(inner_lo[i] >= outer_lo[i] - tol and inner_hi[i] <= outer_hi[i] + tol for i in range(3))


def _aabb_gap(a_lo, a_hi, b_lo, b_hi):
    gap = [max(b_lo[i] - a_hi[i], a_lo[i] - b_hi[i]) for i in range(3)]
    if all(g < 0 for g in gap):
        return max(gap)
    return math.sqrt(sum(max(g, 0.0) ** 2 for g in gap))


def _ray_aabb(origin, direction, lo, hi, eps=1e-12):
    """Slab method: first positive hit distance, or inf if miss (Williams et al. style)."""
    t0, t1 = 0.0, math.inf
    for i in range(3):
        d = direction[i]
        if abs(d) < eps:
            if origin[i] < lo[i] or origin[i] > hi[i]:
                return math.inf
            continue
        inv = 1.0 / d
        ta, tb = (lo[i] - origin[i]) * inv, (hi[i] - origin[i]) * inv
        if ta > tb:
            ta, tb = tb, ta
        t0, t1 = max(t0, ta), min(t1, tb)
        if t1 < t0:
            return math.inf
    return t0 if t0 > eps else (t1 if t1 > eps else math.inf)


def _ray_sphere(origin, direction, center, radius, eps=1e-12):
    oc = [origin[i] - center[i] for i in range(3)]
    b = sum(oc[i] * direction[i] for i in range(3))
    c = sum(oc[i] * oc[i] for i in range(3)) - radius * radius
    disc = b * b - c
    if disc < 0:
        return math.inf
    s = math.sqrt(disc)
    for t in (-b - s, -b + s):
        if t > eps:
            return t
    return math.inf


def _direction(az_deg, el_deg):
    az, el = math.radians(az_deg), math.radians(el_deg)
    return (-math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))


def validate_closure(c):
    mapping(c, {"schema_version", "source", "thermal", "cg", "spatial", "fov"}, "closure")
    if c.get("schema_version") != "1.0":
        raise ValueError("closure.schema_version must be 1.0")
    _text(c.get("source"), "closure.source")
    for key in ("thermal", "cg", "spatial", "fov"):
        if key in c and not isinstance(c[key], dict):
            raise ValueError(f"closure.{key} must be a mapping")


def analyse_closure(onboard, closure, *, analyse=None):
    """Screen thermal/CG/spatial/FOV from open primitives; missing → unassessed.

    ``onboard`` is the validated onboard inventory mapping. ``analyse`` may be the
    existing analyse_onboard result (for conversion losses); if omitted, conversion
    heat is unassessed unless heat_mode is declared-only.
    """
    validate_closure(closure)
    items = {i["id"]: i for i in onboard["items"]}
    checks = []
    sections = {}
    assumptions = [dict(path="closure", value=deepcopy(closure),
                        source="explicit inputs / PRESSUPOSTO unless substantiated")]
    limitations = [
        "L0 screening only: steady heat, AABB packing, discrete FOV rays vs primitives — not ECS design, certified CG envelope, CAD clash or antenna pattern.",
        "Missing thermal/CG/spatial/FOV inputs stay unassessed; never treated as pass.",
    ]

    def check(name, passed, **kw):
        checks.append(dict(name=name, passed=passed, **kw))

    if "thermal" in closure:
        sections["thermal"] = _thermal(onboard, closure["thermal"], analyse, check)
    else:
        check("thermal_balance", None, note="closure.thermal omitted")

    if "cg" in closure:
        sections["cg"] = _cg(items, closure["cg"], check)
    else:
        check("CG", None, note="closure.cg omitted")

    if "spatial" in closure:
        sections["spatial"] = _spatial(items, closure["spatial"], check)
    else:
        check("spatial_fit", None, note="closure.spatial omitted")

    if "fov" in closure:
        sections["fov"] = _fov(items, closure["fov"], check)
    else:
        check("FOV_3D", None, note="closure.fov omitted")

    return dict(
        schema_version="1.0",
        level="L0",
        inputs=deepcopy(closure),
        sections=sections,
        checks=checks,
        requested_checks_passed=aggregate(c["passed"] for c in checks),
        assumptions=assumptions,
        limitations=limitations,
        method=METHOD,
    )


def _thermal(onboard, spec, analyse, check):
    mapping(spec, {"heat_mode", "sinks", "source"}, "closure.thermal")
    _text(spec.get("source"), "closure.thermal.source")
    mode = spec.get("heat_mode", "declared")
    if mode not in ("declared", "declared_plus_conversion", "conversion_only"):
        raise ValueError("heat_mode must be declared|declared_plus_conversion|conversion_only")
    items = onboard["items"]
    declared = None
    if mode in ("declared", "declared_plus_conversion"):
        if all(i.get("heat_W") is not None for i in items):
            declared = sum(i["heat_W"] for i in items)
        else:
            check("thermal_declared_heat", None, note="every item needs heat_W for declared mode")
    conversion = None
    if mode in ("declared_plus_conversion", "conversion_only"):
        conversion = _conversion_heat(onboard, analyse, check)
    heat = None
    if mode == "declared":
        heat = declared
    elif mode == "conversion_only":
        heat = conversion
    else:
        if declared is not None and conversion is not None:
            heat = declared + conversion
        else:
            heat = None
    sinks = spec.get("sinks", [])
    if not isinstance(sinks, list) or len(sinks) > 50:
        raise ValueError("closure.thermal.sinks must be a list <=50")
    available = 0.0
    sink_rows = []
    any_sink = False
    for s in sinks:
        mapping(s, {"id", "kind", "available_W", "mass_flow_kg_s", "cp_J_kgK", "delta_T_K",
                    "area_m2", "speed_m_s", "density_kg_m3", "source"}, "thermal sink")
        _text(s.get("id"), "sink.id")
        _text(s.get("source"), "sink.source")
        kind = s.get("kind")
        if kind not in ("capacity", "ram_air"):
            raise ValueError("sink.kind must be capacity|ram_air")
        row = dict(id=s["id"], kind=kind, available_W=None, source=s["source"])
        if kind == "capacity":
            number("available_W", s.get("available_W"))
            row["available_W"] = float(s["available_W"])
        else:
            md = s.get("mass_flow_kg_s")
            if md is None and all(k in s for k in ("area_m2", "speed_m_s", "density_kg_m3")):
                md = number("area_m2", s["area_m2"], positive=True) * number("speed_m_s", s["speed_m_s"], positive=True) * number("density_kg_m3", s["density_kg_m3"], positive=True)
                row["mass_flow_kg_s"] = md
                row["mass_flow_basis"] = "area*speed*density"
            elif md is not None:
                md = number("mass_flow_kg_s", md, positive=True)
                row["mass_flow_kg_s"] = md
            else:
                check("thermal_sink:" + s["id"], None, note="ram_air needs mass_flow_kg_s or area/speed/density")
                sink_rows.append(row)
                continue
            cp = number("cp_J_kgK", s.get("cp_J_kgK", 1004.0), positive=True)
            dT = number("delta_T_K", s.get("delta_T_K"), positive=True)
            row["cp_J_kgK"] = cp
            row["delta_T_K"] = dT
            row["available_W"] = md * cp * dT
            row["method"] = "Q=mdot*cp*delta_T (Incropera & DeWitt open-system screening)"
        available += row["available_W"]
        any_sink = True
        sink_rows.append(row)
    margin = available - heat if heat is not None and any_sink else None
    passed = margin >= 0 if margin is not None else None
    check("thermal_balance", passed, required_W=heat, available_W=available if any_sink else None, margin_W=margin)
    return dict(heat_mode=mode, heat_load_W=heat, declared_heat_W=declared, conversion_heat_W=conversion,
                available_rejection_W=available if any_sink else None, margin_W=margin, sinks=sink_rows,
                status="assessed" if passed is not None else "unassessed")


def _conversion_heat(onboard, analyse, check):
    """Distribution loss P_load*(1/η_del−1) + generator shaft*(1−η_gen) when coefficients exist."""
    if analyse is None:
        check("thermal_conversion_heat", None, note="analyse_onboard result required for conversion heat")
        return None
    by_id = {x["id"]: x for x in onboard["sources"]}
    total = 0.0
    known = True
    for src in analyse["sources"]:
        raw = by_id[src["id"]]
        eta_d = raw["delivery_efficiency"]
        avg_load = src["load_average_W"]
        if eta_d <= 0 or eta_d > 1:
            known = False
            break
        total += avg_load * (1.0 / eta_d - 1.0)
        if raw["kind"] == "generator":
            if "generator_efficiency" in raw and src.get("shaft_extraction_W") is not None:
                eta_g = raw["generator_efficiency"]
                total += src["shaft_extraction_W"] * (1.0 - eta_g)
            elif raw.get("fuel_kg_kWh_terminal") is not None:
                # Jet path: terminal electrical already after generator; no separate shaft η —
                # conversion heat beyond delivery must be declared on items.
                pass
            elif avg_load > 0:
                known = False
                check("thermal_conversion_heat", None, note=f"generator {src['id']} lacks efficiency for conversion heat")
                return None
    if not known:
        check("thermal_conversion_heat", None)
        return None
    return total


def _cg(items, spec, check):
    mapping(spec, {"base", "placements", "envelope", "source"}, "closure.cg")
    _text(spec.get("source"), "closure.cg.source")
    base = spec.get("base")
    places = spec.get("placements", {})
    env = spec.get("envelope")
    if base is None or env is None:
        check("CG", None, note="closure.cg needs base and envelope")
        return dict(status="unassessed")
    mapping(base, {"mass_kg", "cg_m", "source"}, "closure.cg.base")
    _text(base.get("source"), "cg.base.source")
    number("base.mass_kg", base.get("mass_kg"), positive=True)
    bcg = _vec3("base.cg_m", base.get("cg_m"))
    if not isinstance(places, dict):
        raise ValueError("closure.cg.placements must map item id → position")
    missing = [i for i in items if i not in places]
    if missing:
        check("CG", None, missing_placements=missing, note="every onboard item needs a CG placement")
        return dict(status="unassessed", missing_placements=missing)
    rows = [("base", float(base["mass_kg"]), bcg)]
    for iid, it in items.items():
        p = places[iid]
        mapping(p, {"position_m", "cg_offset_m", "source"}, "cg placement")
        pos = _vec3(iid + ".position_m", p.get("position_m"))
        off = _vec3(iid + ".cg_offset_m", p.get("cg_offset_m", [0, 0, 0]))
        if "source" in p:
            _text(p["source"], iid + ".source")
        rows.append((iid, float(it["mass_kg"]), [pos[i] + off[i] for i in range(3)]))
    M = sum(m for _, m, _ in rows)
    if M <= 0:
        raise ValueError("CG total mass must be positive")
    cg = [sum(m * r[i] for _, m, r in rows) / M for i in range(3)]
    mapping(env, {"x_m", "y_m", "z_m", "source"}, "closure.cg.envelope")
    if "source" in env:
        _text(env["source"], "envelope.source")
    margins = {}
    ok = True
    assessed = False
    for axis, key in enumerate(("x_m", "y_m", "z_m")):
        if key not in env:
            continue
        lim = env[key]
        mapping(lim, {"min", "max"}, f"envelope.{key}")
        lo, hi = number(f"{key}.min", lim["min"], maximum=1e6), number(f"{key}.max", lim["max"], maximum=1e6)
        if hi < lo:
            raise ValueError(f"envelope.{key} max < min")
        m = min(cg[axis] - lo, hi - cg[axis])
        margins[key] = dict(value_m=cg[axis], min_m=lo, max_m=hi, margin_m=m, ok=m >= 0)
        ok = ok and m >= 0
        assessed = True
    passed = ok if assessed else None
    check("CG", passed, cg_m=cg, margins=margins, total_mass_kg=M)
    return dict(status="assessed" if assessed else "unassessed", cg_m=cg, total_mass_kg=M,
                margins=margins, breakdown={n: {"mass_kg": m, "r_m": r} for n, m, r in rows})


def _spatial(items, spec, check):
    mapping(spec, {"bays", "placements", "source"}, "closure.spatial")
    _text(spec.get("source"), "closure.spatial.source")
    bays_in = spec.get("bays", [])
    places = spec.get("placements", {})
    if not isinstance(bays_in, list) or not isinstance(places, dict):
        raise ValueError("spatial.bays list and placements mapping required")
    bays = {}
    for b in bays_in:
        mapping(b, {"id", "box", "max_packing_fraction", "source"}, "spatial bay")
        _text(b.get("id"), "bay.id")
        _text(b.get("source"), "bay.source")
        lo, hi = _box(b["box"], "bay." + b["id"])
        frac = b.get("max_packing_fraction")
        if frac is not None:
            number("max_packing_fraction", frac, maximum=1)
        vol = (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])
        bays[b["id"]] = dict(lo=lo, hi=hi, volume_m3=vol, max_packing_fraction=frac, source=b["source"])
    if not bays:
        check("spatial_fit", None, note="no bays supplied")
        return dict(status="unassessed")
    missing = [i for i in items if i not in places]
    if missing:
        check("spatial_fit", None, missing_placements=missing)
        return dict(status="unassessed", missing_placements=missing)
    placed = {}
    bay_items = {b: [] for b in bays}
    ok = True
    for iid, it in items.items():
        p = places[iid]
        mapping(p, {"size_m", "position_m", "bay", "source"}, "spatial placement")
        size = _vec3(iid + ".size_m", p.get("size_m"))
        if any(x <= 0 for x in size):
            raise ValueError(iid + " size_m must be positive")
        pos = _vec3(iid + ".position_m", p.get("position_m"))
        bay_id = p.get("bay")
        if bay_id not in bays:
            raise ValueError(f"placement {iid}: unknown bay {bay_id!r}")
        if "source" in p:
            _text(p["source"], iid + ".source")
        lo, hi = _item_box(pos, size)
        inside = _inside(lo, hi, bays[bay_id]["lo"], bays[bay_id]["hi"])
        check(f"spatial_within:{iid}", inside, bay=bay_id)
        ok = ok and inside
        vol = size[0] * size[1] * size[2]
        placed[iid] = dict(lo=lo, hi=hi, volume_m3=vol, bay=bay_id, position_m=pos, size_m=size)
        bay_items[bay_id].append(iid)
    # overlap
    ids = list(placed)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            g = _aabb_gap(placed[a]["lo"], placed[a]["hi"], placed[b]["lo"], placed[b]["hi"])
            passed = g >= 0
            check(f"spatial_no_overlap:{a}:{b}", passed, gap_m=g)
            ok = ok and passed
    packing = {}
    for bid, bay in bays.items():
        iv = sum(placed[i]["volume_m3"] for i in bay_items[bid])
        frac = iv / bay["volume_m3"] if bay["volume_m3"] > 0 else None
        lim = bay["max_packing_fraction"]
        passed = frac <= lim if lim is not None and frac is not None else None
        check(f"spatial_packing:{bid}", passed, fraction=frac, max_fraction=lim, items_volume_m3=iv,
              bay_volume_m3=bay["volume_m3"])
        if passed is False:
            ok = False
        packing[bid] = dict(fraction=frac, items=bay_items[bid], items_volume_m3=iv, bay_volume_m3=bay["volume_m3"],
                            max_packing_fraction=lim)
    check("spatial_fit", ok)
    return dict(status="assessed", placements=placed, packing=packing, ok=ok)


def _fov(items, spec, check):
    mapping(spec, {"sensors", "blockers", "source"}, "closure.fov")
    _text(spec.get("source"), "closure.fov.source")
    sensors = spec.get("sensors", [])
    blockers = spec.get("blockers", [])
    if not isinstance(sensors, list) or not isinstance(blockers, list):
        raise ValueError("fov.sensors and fov.blockers must be lists")
    if not sensors:
        check("FOV_3D", None, note="no sensors supplied")
        return dict(status="unassessed")
    block_geom = []
    for b in blockers:
        mapping(b, {"id", "kind", "box", "center", "radius_m", "opacity", "source"}, "fov blocker")
        _text(b.get("id"), "blocker.id")
        _text(b.get("source"), "blocker.source")
        kind = b.get("kind")
        op = number("opacity", b.get("opacity", 1.0), maximum=1)
        if kind == "box":
            lo, hi = _box(b["box"], "blocker." + b["id"])
            block_geom.append(dict(id=b["id"], kind="box", lo=lo, hi=hi, opacity=op))
        elif kind == "sphere":
            c = _vec3("blocker.center", b.get("center"))
            r = number("radius_m", b.get("radius_m"), positive=True)
            block_geom.append(dict(id=b["id"], kind="sphere", center=c, radius_m=r, opacity=op))
        else:
            raise ValueError("blocker.kind must be box|sphere")
    results = []
    overall = True
    assessed_any = False
    for s in sensors:
        mapping(s, {"item_id", "position_m", "aperture_offset_m", "az_deg", "el_deg", "axis", "half_angle_deg",
                    "step_deg", "max_blocked_frac", "range_m", "ignore", "source", "name"}, "fov sensor")
        _text(s.get("source"), "sensor.source")
        iid = s.get("item_id")
        if iid not in items:
            raise ValueError(f"fov sensor item_id {iid!r} not in onboard items")
        if "position_m" not in s:
            check("FOV_3D:" + iid, None, note="sensor position_m required")
            overall = None if overall is not False else False
            continue
        pos = _vec3(iid + ".position_m", s["position_m"])
        off = _vec3(iid + ".aperture_offset_m", s.get("aperture_offset_m", [0, 0, 0]))
        origin = [pos[i] + off[i] for i in range(3)]
        step = number("step_deg", s.get("step_deg", 10.0), positive=True, maximum=45)
        allow = number("max_blocked_frac", s.get("max_blocked_frac", 0.0), maximum=1)
        rng = number("range_m", s.get("range_m", 1e6), positive=True)
        ignore = set(s.get("ignore", ()))
        dirs = _fov_dirs(s, step)
        if not dirs:
            check("FOV_3D:" + (s.get("name") or iid), None, note="empty FOV sample")
            continue
        blocked = []
        by = {}
        for d in dirs:
            tmin, who = math.inf, None
            for b in block_geom:
                if b["id"] in ignore:
                    continue
                if b["kind"] == "box":
                    t = _ray_aabb(origin, d, b["lo"], b["hi"])
                else:
                    t = _ray_sphere(origin, d, b["center"], b["radius_m"])
                if t < tmin and t < rng:
                    tmin, who = t, b
            if who is not None:
                blocked.append(who["opacity"])
                by[who["id"]] = by.get(who["id"], 0.0) + who["opacity"] / len(dirs)
            else:
                blocked.append(0.0)
        frac = sum(blocked) / len(blocked)
        margin = allow - frac
        passed = frac <= allow + 1e-12
        name = s.get("name") or iid
        check("FOV_3D:" + name, passed, blocked_frac=frac, max_blocked_frac=allow, margin=margin,
              n_rays=len(dirs), blocked_by=by)
        results.append(dict(name=name, item_id=iid, blocked_frac=frac, max_blocked_frac=allow, margin=margin,
                            ok=passed, n_rays=len(dirs), blocked_by=by, origin_m=origin))
        overall = overall and passed
        assessed_any = True
    check("FOV_3D", overall if assessed_any else None)
    return dict(status="assessed" if assessed_any else "unassessed", sensors=results, blockers=block_geom, ok=overall if assessed_any else None)


def _fov_dirs(spec, step):
    if "axis" in spec or "half_angle_deg" in spec:
        # Fibonacci cone about axis (González 2010), same construction as assembly.integration
        ax = list(_vec3("axis", spec.get("axis", [0, 0, 1])))
        nrm = math.sqrt(sum(x * x for x in ax))
        if nrm <= 0:
            raise ValueError("fov axis must be nonzero")
        ax = [x / nrm for x in ax]
        ha = math.radians(number("half_angle_deg", spec["half_angle_deg"], positive=True, maximum=180))
        n = max(16, int(math.ceil(2 * math.pi * (1 - math.cos(ha)) / math.radians(step) ** 2)))
        a = [1.0, 0, 0] if abs(ax[0]) < 0.9 else [0, 1.0, 0]
        u = [ax[1] * a[2] - ax[2] * a[1], ax[2] * a[0] - ax[0] * a[2], ax[0] * a[1] - ax[1] * a[0]]
        un = math.sqrt(sum(x * x for x in u))
        u = [x / un for x in u]
        w = [ax[1] * u[2] - ax[2] * u[1], ax[2] * u[0] - ax[0] * u[2], ax[0] * u[1] - ax[1] * u[0]]
        out = []
        for i in range(n):
            ii = i + 0.5
            cz = 1 - ii / n * (1 - math.cos(ha))
            ph = ii * math.pi * (3 - math.sqrt(5))
            sz = math.sqrt(max(0.0, 1 - cz * cz))
            loc = [sz * math.cos(ph), sz * math.sin(ph), cz]
            out.append([loc[0] * u[j] + loc[1] * w[j] + loc[2] * ax[j] for j in range(3)])
        return out
    az0, az1 = spec.get("az_deg", (-180.0, 180.0))
    el0, el1 = spec.get("el_deg", (-90.0, 90.0))
    if not (isinstance(az0, (int, float)) and isinstance(az1, (int, float)) and isinstance(el0, (int, float)) and isinstance(el1, (int, float))):
        raise ValueError("az_deg/el_deg bounds must be numbers")
    full = (az1 - az0) >= 360 - 1e-9
    naz = max(1, int(math.ceil((az1 - az0) / step)))
    nel = max(1, int(math.ceil((el1 - el0) / step)))
    azs = [az0 + (az1 - az0) * k / naz for k in range(naz)] if full else [az0 + (az1 - az0) * k / naz for k in range(naz + 1)]
    els = [el0 + (el1 - el0) * k / nel for k in range(nel + 1)]
    return [_direction(az, el) for az in azs for el in els]
