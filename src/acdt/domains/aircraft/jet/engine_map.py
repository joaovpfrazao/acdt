# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Lightweight turbofan thrust/SFC maps — tables or Mattingly/Ihme correlation.

NO cycle deck: this module never installs, vendors, wraps or runs pyCycle, NPSS,
GasTurb, T-MATS or CFD. Generating a deck with a cycle code is out of scope
(João's PC / deferred L2). Interpolation of a *user-supplied* table is allowed.

Modes
-----
* ``correlation`` (default): existing Mattingly 2002 Ch.2 thrust lapse + Ihme
  2025 Eq. 2.77 TSFC at maximum dry rating. Optional ``throttle`` in (0,1]
  scales thrust as a power-lever proxy (conceptual design practice; Raymer
  Ch. 13 / Mattingly sizing context). Part-throttle TSFC stays at the max-rated
  Ihme value and is flagged ``part_throttle_tsfc_unassessed`` when throttle<1
  unless a table/corrected map supplies SFC.
* ``table``: user grid or point list of thrust_lapse (or thrust_installed_N) and
  TSFC_kg_N_s vs Mach, altitude, throttle. Multilinear interpolation on the
  supplied axes (Press et al., Numerical Recipes — multilinear interp).
* ``corrected_table``: Walsh & Fletcher (*Gas Turbine Performance*) style
  corrected parameters: store F/δ and SFC/√θ vs Mach and throttle (or N_c);
  recover F = (F/δ)·δ and SFC = (SFC/√θ)·√θ with ISA freestream static δ, θ
  (standard day; no inlet recovery map beyond isentropic ram already in δ0/θ0
  if the table is defined that way — here δ,θ are static ISA p/p_SL, T/T_SL
  unless the table declares ``totals: true`` and uses ram totals).

Out of the supplied domain: never silent extrapolation. ``out_of_domain`` is
``unassessed`` (return status) or ``error`` (raise). ``extrapolate_flagged``
only when the user explicitly opts in; result carries ``extrapolated: true``.

PRESSUPOSTO: ISA; steady rating; no bleed/offtake schedule, hot-day, transient
or installed-inlet CFD. Unknown coverage ≠ zero thrust/SFC.
"""
from __future__ import annotations
import math
from copy import deepcopy
from acdt.core.atmosphere import isa, P0, T0
from acdt.core.energy_storage import mapping, number
from ._validation import bounded
from .turbofan import turbofan_point


def _text(x, name):
    if not isinstance(x, str) or not x.strip():
        raise ValueError(name + " must be nonempty text / source")


def _sorted_unique(name, values):
    if not isinstance(values, (list, tuple)) or len(values) < 1:
        raise ValueError(name + " needs at least one axis node")
    out = [number(name, v, maximum=1e7) for v in values]
    if any(out[i] >= out[i + 1] for i in range(len(out) - 1)):
        raise ValueError(name + " must be strictly increasing")
    return out


def _bracket(axis, x, *, allow_extrapolate):
    if len(axis) == 1:
        if x == axis[0] or allow_extrapolate:
            return 0, 0, 0.0
        return None
    if x < axis[0] or x > axis[-1]:
        if not allow_extrapolate:
            return None
        if x < axis[0]:
            return 0, 0, 0.0
        return len(axis) - 2, len(axis) - 1, 1.0
    for i in range(len(axis) - 1):
        if axis[i] <= x <= axis[i + 1]:
            if axis[i + 1] == axis[i]:
                return i, i + 1, 0.0
            t = (x - axis[i]) / (axis[i + 1] - axis[i])
            return i, i + 1, t
    return len(axis) - 2, len(axis) - 1, 1.0


def _get3(arr, i, j, k):
    return float(arr[i][j][k])


def _multilinear(values, t_m, t_h, t_p, im, ih, ip):
    """Trilinear on unit cube corners (i,i+1)×(j,j+1)×(k,k+1)."""
    c000 = _get3(values, im[0], ih[0], ip[0])
    c100 = _get3(values, im[1], ih[0], ip[0])
    c010 = _get3(values, im[0], ih[1], ip[0])
    c110 = _get3(values, im[1], ih[1], ip[0])
    c001 = _get3(values, im[0], ih[0], ip[1])
    c101 = _get3(values, im[1], ih[0], ip[1])
    c011 = _get3(values, im[0], ih[1], ip[1])
    c111 = _get3(values, im[1], ih[1], ip[1])
    c00 = c000 * (1 - t_m) + c100 * t_m
    c10 = c010 * (1 - t_m) + c110 * t_m
    c01 = c001 * (1 - t_m) + c101 * t_m
    c11 = c011 * (1 - t_m) + c111 * t_m
    c0 = c00 * (1 - t_h) + c10 * t_h
    c1 = c01 * (1 - t_h) + c11 * t_h
    return c0 * (1 - t_p) + c1 * t_p


def validate_engine_map(spec):
    """Validate opt-in map block; correlation needs no block."""
    if spec is None:
        return
    mapping(spec, {"mode", "source", "points", "axes", "thrust_lapse", "thrust_installed_N",
                   "TSFC_kg_N_s", "F_over_delta", "SFC_over_sqrt_theta", "totals",
                   "out_of_domain", "interpolation"}, "engine.map")
    _text(spec.get("source"), "engine.map.source")
    mode = spec.get("mode", "table")
    if mode not in ("table", "corrected_table", "correlation"):
        raise ValueError("engine.map.mode must be table|corrected_table|correlation")
    ood = spec.get("out_of_domain", "unassessed")
    if ood not in ("unassessed", "error", "extrapolate_flagged"):
        raise ValueError("out_of_domain must be unassessed|error|extrapolate_flagged")
    if mode == "correlation":
        return
    if "points" in spec:
        pts = spec["points"]
        if not isinstance(pts, list) or not (2 <= len(pts) <= 5000):
            raise ValueError("map.points must be a list with 2..5000 entries")
        for p in pts:
            mapping(p, {"mach", "altitude_m", "throttle", "thrust_lapse", "thrust_installed_N",
                        "TSFC_kg_N_s", "F_over_delta", "SFC_over_sqrt_theta"}, "map point")
            number("mach", p.get("mach"), maximum=0.95)
            number("altitude_m", p.get("altitude_m"), maximum=20000)
            number("throttle", p.get("throttle"), positive=True, maximum=1)
            if mode == "table":
                if ("thrust_lapse" in p) == ("thrust_installed_N" in p):
                    raise ValueError("each table point needs exactly one of thrust_lapse|thrust_installed_N")
                number("TSFC_kg_N_s", p.get("TSFC_kg_N_s"), positive=True, maximum=1e-3)
                if "thrust_lapse" in p:
                    number("thrust_lapse", p["thrust_lapse"], positive=True, maximum=2)
                else:
                    number("thrust_installed_N", p["thrust_installed_N"], positive=True)
            else:
                number("F_over_delta", p.get("F_over_delta"), positive=True)
                number("SFC_over_sqrt_theta", p.get("SFC_over_sqrt_theta"), positive=True, maximum=1e-3)
        return
    # structured axes
    axes = spec.get("axes")
    if not isinstance(axes, dict):
        raise ValueError("map needs points[] or axes{}")
    mapping(axes, {"mach", "altitude_m", "throttle"}, "map.axes")
    ms = _sorted_unique("axes.mach", axes["mach"])
    hs = _sorted_unique("axes.altitude_m", axes["altitude_m"])
    # throttle may start at small positive
    ps = axes["throttle"]
    if not isinstance(ps, (list, tuple)) or len(ps) < 1:
        raise ValueError("axes.throttle needs ≥1 node")
    ps = [number("throttle", v, positive=True, maximum=1) for v in ps]
    if any(ps[i] >= ps[i + 1] for i in range(len(ps) - 1)):
        raise ValueError("axes.throttle must be strictly increasing")
    shape = (len(ms), len(hs), len(ps))

    def _check_grid(name, grid, *, positive=True, maximum=1e7):
        if not isinstance(grid, list) or len(grid) != shape[0]:
            raise ValueError(f"{name} must be nested list shaped {shape}")
        for i, plane in enumerate(grid):
            if not isinstance(plane, list) or len(plane) != shape[1]:
                raise ValueError(f"{name} row {i} length")
            for j, row in enumerate(plane):
                if not isinstance(row, list) or len(row) != shape[2]:
                    raise ValueError(f"{name}[{i}][{j}] length")
                for k, v in enumerate(row):
                    number(f"{name}[{i},{j},{k}]", v, positive=positive, maximum=maximum)

    if mode == "table":
        has_lapse = "thrust_lapse" in spec
        has_thr = "thrust_installed_N" in spec
        if has_lapse == has_thr:
            raise ValueError("table axes mode needs exactly one of thrust_lapse|thrust_installed_N")
        if has_lapse:
            _check_grid("thrust_lapse", spec["thrust_lapse"], positive=True, maximum=2)
        else:
            _check_grid("thrust_installed_N", spec["thrust_installed_N"], positive=True)
        _check_grid("TSFC_kg_N_s", spec["TSFC_kg_N_s"], positive=True, maximum=1e-3)
    else:
        _check_grid("F_over_delta", spec["F_over_delta"], positive=True)
        _check_grid("SFC_over_sqrt_theta", spec["SFC_over_sqrt_theta"], positive=True, maximum=1e-3)
        if "totals" in spec and not isinstance(spec["totals"], bool):
            raise ValueError("map.totals must be bool")


def _points_to_grid(points, mode, thrust_sl_N):
    """Build a regular grid from scattered points when they form a full product set."""
    ms = sorted({float(p["mach"]) for p in points})
    hs = sorted({float(p["altitude_m"]) for p in points})
    ps = sorted({float(p["throttle"]) for p in points})
    index = {(float(p["mach"]), float(p["altitude_m"]), float(p["throttle"])): p for p in points}
    if len(index) != len(ms) * len(hs) * len(ps):
        raise ValueError("map.points must fill a complete Cartesian product of unique mach×altitude×throttle")
    if mode == "table":
        use_lapse = "thrust_lapse" in next(iter(points))
        thrust = []
        tsfc = []
        for m in ms:
            pm, pt = [], []
            for h in hs:
                row_m, row_t = [], []
                for p in ps:
                    cell = index[(m, h, p)]
                    if use_lapse:
                        row_m.append(float(cell["thrust_lapse"]))
                    else:
                        row_m.append(float(cell["thrust_installed_N"]) / thrust_sl_N)
                    row_t.append(float(cell["TSFC_kg_N_s"]))
                pm.append(row_m)
                pt.append(row_t)
            thrust.append(pm)
            tsfc.append(pt)
        return ms, hs, ps, thrust, tsfc, "lapse"
    F, S = [], []
    for m in ms:
        pF, pS = [], []
        for h in hs:
            rF, rS = [], []
            for p in ps:
                cell = index[(m, h, p)]
                rF.append(float(cell["F_over_delta"]))
                rS.append(float(cell["SFC_over_sqrt_theta"]))
            pF.append(rF)
            pS.append(rS)
        F.append(pF)
        S.append(pS)
    return ms, hs, ps, F, S, "corrected"


def _lookup(spec, mach, altitude_m, throttle, thrust_sl_N):
    ood = spec.get("out_of_domain", "unassessed")
    allow = ood == "extrapolate_flagged"
    mode = spec.get("mode", "table")
    if "points" in spec:
        ms, hs, ps, A, B, kind = _points_to_grid(spec["points"], mode, thrust_sl_N)
    else:
        ms = _sorted_unique("axes.mach", spec["axes"]["mach"])
        hs = _sorted_unique("axes.altitude_m", spec["axes"]["altitude_m"])
        ps = [number("throttle", v, positive=True, maximum=1) for v in spec["axes"]["throttle"]]
        if mode == "table":
            if "thrust_lapse" in spec:
                A, kind = spec["thrust_lapse"], "lapse"
            else:
                A = [[[float(v) / thrust_sl_N for v in row] for row in plane] for plane in spec["thrust_installed_N"]]
                kind = "lapse"
            B = spec["TSFC_kg_N_s"]
        else:
            A, B, kind = spec["F_over_delta"], spec["SFC_over_sqrt_theta"], "corrected"
    bm = _bracket(ms, mach, allow_extrapolate=allow)
    bh = _bracket(hs, altitude_m, allow_extrapolate=allow)
    bp = _bracket(ps, throttle, allow_extrapolate=allow)
    if bm is None or bh is None or bp is None:
        if ood == "error":
            raise ValueError(f"engine map query (M={mach}, h={altitude_m}, Π={throttle}) outside supplied domain")
        return None, True, False
    extrapolated = (mach < ms[0] or mach > ms[-1] or altitude_m < hs[0] or altitude_m > hs[-1]
                    or throttle < ps[0] or throttle > ps[-1])
    if extrapolated and ood != "extrapolate_flagged":
        # should not happen if bracket returned None above
        return None, True, False
    im = (bm[0], bm[1])
    ih = (bh[0], bh[1])
    ip = (bp[0], bp[1])
    a = _multilinear(A, bm[2], bh[2], bp[2], im, ih, ip)
    b = _multilinear(B, bm[2], bh[2], bp[2], im, ih, ip)
    return (a, b, kind), False, extrapolated


def engine_point(mach: float, altitude_m: float, thrust_sl_N: float = 120000.0,
                 installation_factor: float = 0.97, throttle_ratio: float = 1.05,
                 tsfc_multiplier: float = 1.0, throttle: float = 1.0, map=None) -> dict:
    """Installed thrust and TSFC at Mach/altitude/throttle.

    Default (``map is None`` or ``map.mode==correlation``): Mattingly/Ihme via
    :func:`turbofan_point`, thrust scaled by ``throttle``. Table modes replace
    the correlation when opted in.
    """
    bounded("throttle", throttle, 0, 1, open_lower=True)
    if map is not None:
        validate_engine_map(map)
    use_corr = map is None or map.get("mode", "table") == "correlation"
    if use_corr:
        base = turbofan_point(mach, altitude_m, thrust_sl_N, installation_factor=installation_factor,
                              throttle_ratio=throttle_ratio, tsfc_multiplier=tsfc_multiplier)
        thrust = base["thrust_installed_N"] * throttle
        out = dict(base)
        out.update(thrust_installed_N=thrust, fuel_flow_kg_s=thrust * base["TSFC_kg_N_s"],
                   throttle=throttle, map_mode="correlation",
                   status="assessed", extrapolated=False, in_domain=True,
                   citations=list(base["citations"]) + [
                       "Part-throttle thrust scaled by power-lever proxy Π (conceptual; not a cycle deck)"])
        if throttle < 1.0 - 1e-12:
            out["part_throttle_tsfc"] = "unassessed"
            out["limitations"] = (base["limitations"] +
                                  " Part-throttle TSFC left at max-rated Ihme value (unassessed); supply a table for SFC(Π).")
            out["issues"] = ["part_throttle_tsfc_unassessed"]
        else:
            out["part_throttle_tsfc"] = "max_rated_ihme"
            out["issues"] = []
        out["map_source"] = None if map is None else map.get("source")
        return out

    # table / corrected_table
    bounded("mach", mach, 0, 0.95)
    bounded("altitude_m", altitude_m, 0, 20000)
    bounded("thrust_sl_N", thrust_sl_N, 0, 1e7, open_lower=True)
    bounded("installation_factor", installation_factor, 0, 1, open_lower=True)
    looked, ood, extrapolated = _lookup(map, mach, altitude_m, throttle, thrust_sl_N)
    if looked is None:
        return {"mach": mach, "altitude_m": altitude_m, "throttle": throttle,
                "thrust_installed_N": None, "TSFC_kg_N_s": None, "fuel_flow_kg_s": None,
                "status": "unassessed", "in_domain": False, "extrapolated": False,
                "map_mode": map["mode"], "map_source": map["source"],
                "issues": ["engine_map_out_of_domain"],
                "limitations": "Query outside supplied map domain; unknown ≠ zero (no silent extrapolation).",
                "citations": ["User-supplied map; no cycle code"],
                "pressupostos": {"thrust_sl_N": thrust_sl_N, "installation_factor": installation_factor,
                                 "throttle": throttle, "ISA": True}}
    a, b, kind = looked
    atm = isa(altitude_m)
    if kind == "lapse":
        # table thrust_lapse is UNINSTALLED α; apply installation like correlation
        thrust = thrust_sl_N * a * installation_factor
        tsfc = b
        citations = ["User-supplied thrust_lapse/TSFC table (multilinear interp); installation_factor applied to lapse"]
    else:
        if map.get("totals"):
            ram = 1 + 0.2 * mach ** 2
            theta = atm.T / T0 * ram
            delta = atm.p / P0 * ram ** 3.5
            basis = "isentropic freestream totals (δ0,θ0)"
        else:
            theta = atm.T / T0
            delta = atm.p / P0
            basis = "ISA static δ,θ (Walsh & Fletcher corrected-parameter recovery)"
        # a = F/δ uninstalled or installed? Require installed F/δ in table to avoid double install.
        thrust = a * delta  # table stores installed F/δ
        tsfc = b * math.sqrt(theta)
        citations = [f"Walsh & Fletcher corrected parameters: F=(F/δ)·δ, SFC=(SFC/√θ)·√θ using {basis}",
                     "User-supplied corrected table (multilinear interp); no cycle code"]
        # installation_factor already baked into table for corrected mode
    if thrust <= 0 or tsfc <= 0:
        raise ValueError("map interpolation produced non-positive thrust or TSFC")
    return {"mach": mach, "altitude_m": altitude_m, "throttle": throttle,
            "thrust_installed_N": thrust, "thrust_lapse_installed": thrust / thrust_sl_N,
            "TSFC_kg_N_s": tsfc, "fuel_flow_kg_s": thrust * tsfc,
            "status": "assessed", "in_domain": True, "extrapolated": bool(extrapolated),
            "map_mode": map["mode"], "map_source": map["source"],
            "part_throttle_tsfc": "from_map", "issues": (["engine_map_extrapolated"] if extrapolated else []),
            "citations": citations,
            "limitations": "Supplied-table / corrected-parameter map only; not pyCycle/NPSS/GasTurb/T-MATS; "
                           "no bleed schedule, hot-day or transient.",
            "pressupostos": {"thrust_sl_N": thrust_sl_N, "installation_factor": installation_factor,
                             "throttle": throttle, "ISA": True, "map": deepcopy(map)}}
