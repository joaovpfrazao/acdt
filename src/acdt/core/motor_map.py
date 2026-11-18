# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Lightweight electric motor efficiency maps from supplied tables.

No FEA, no thermal transient solver, no OEM decoder. User supplies η versus
shaft power (and optional RPM). Linear interpolation; out-of-domain →
unassessed (unknown ≠ η=1). Constant-efficiency hybrid/prop paths remain the
default when no map is given.

Citations: energy conservation P_elec = P_shaft/η; table interpolation as in
Press et al. (Numerical Recipes). Efficiencies are INPUTS (PRESSUPOSTO unless
datasheet).
"""
from __future__ import annotations
from copy import deepcopy
from .energy_storage import mapping, number


def validate_motor_map(spec):
    if spec is None:
        return
    mapping(spec, {"mode", "source", "points", "out_of_domain"}, "motor.map")
    if spec.get("mode", "table") != "table":
        raise ValueError("motor.map.mode must be table (only lightweight table supported)")
    if not isinstance(spec.get("source"), str) or not spec["source"].strip():
        raise ValueError("motor.map.source required")
    ood = spec.get("out_of_domain", "unassessed")
    if ood not in ("unassessed", "error"):
        raise ValueError("motor.map.out_of_domain must be unassessed|error")
    pts = spec.get("points")
    if not isinstance(pts, list) or len(pts) < 2:
        raise ValueError("motor.map.points needs ≥2 entries")
    for p in pts:
        mapping(p, {"shaft_power_W", "efficiency", "rpm", "source"}, "motor map point")
        number("shaft_power_W", p.get("shaft_power_W"), maximum=1e9)
        number("efficiency", p.get("efficiency"), positive=True, maximum=1)
        if "rpm" in p:
            number("rpm", p["rpm"], maximum=1e6)


def motor_efficiency(shaft_power_W, map=None, rpm=None):
    """Return {efficiency, status, ...}; default constant None map → caller keeps η."""
    if map is None:
        return {"efficiency": None, "status": "default_constant", "issues": [],
                "limitations": "No motor map; use the supplied constant efficiency."}
    validate_motor_map(map)
    number("shaft_power_W", shaft_power_W, maximum=1e9)
    pts = sorted(map["points"], key=lambda p: (p["shaft_power_W"], p.get("rpm", 0.0)))
    # 1-D in power when rpm omitted; if rpm given on all points, require match band
    if all("rpm" in p for p in pts) and rpm is not None:
        number("rpm", rpm, maximum=1e6)
        # nearest rpm group then interp in power
        rpms = sorted({float(p["rpm"]) for p in pts})
        # pick closest rpm column
        rstar = min(rpms, key=lambda r: abs(r - rpm))
        col = [p for p in pts if float(p["rpm"]) == rstar]
    else:
        col = pts
        rstar = None
    powers = [float(p["shaft_power_W"]) for p in col]
    etas = [float(p["efficiency"]) for p in col]
    if shaft_power_W < powers[0] or shaft_power_W > powers[-1]:
        if map.get("out_of_domain", "unassessed") == "error":
            raise ValueError("motor map query outside domain")
        return {"efficiency": None, "status": "unassessed", "in_domain": False,
                "issues": ["motor_map_out_of_domain"], "map_source": map["source"],
                "limitations": "Outside supplied η(P) table; unknown ≠ η=1."}
    # linear
    for i in range(len(powers) - 1):
        if powers[i] <= shaft_power_W <= powers[i + 1]:
            if powers[i + 1] == powers[i]:
                eta = etas[i]
            else:
                t = (shaft_power_W - powers[i]) / (powers[i + 1] - powers[i])
                eta = etas[i] * (1 - t) + etas[i + 1] * t
            return {"efficiency": eta, "status": "assessed", "in_domain": True,
                    "rpm_column": rstar, "map_source": map["source"], "issues": [],
                    "inputs": deepcopy({"shaft_power_W": shaft_power_W, "rpm": rpm}),
                    "limitations": "Supplied η table only; no motor thermal/FEA model."}
    return {"efficiency": etas[-1], "status": "assessed", "in_domain": True,
            "map_source": map["source"], "issues": []}
