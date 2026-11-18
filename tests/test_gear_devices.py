# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Taildragger / ski assembly gear, drawn legs, retract kinematics (opt-in, Raymer Ch. 11 / 14 CFR 23.925)."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly.gear_devices import (
    apply_gear_devices,
    check_retract,
    draw_legs,
    layout_ski,
    layout_taildragger,
    leg_drawing_lines,
)
from acdt.domains.aircraft.assembly.sizing import analyse, gear_layout
from acdt.domains.aircraft.landing_gear import analyse_landing_gear
from acdt.domains.aircraft.mission import MissionSpec
from acdt.domains.aircraft.sizing import run as size_run

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "integration"
TAIL = json.loads((EX / "conventional_taildragger.json").read_text(encoding="utf-8"))
SKI = json.loads((EX / "ski_gear_demo.json").read_text(encoding="utf-8"))


def test_unknown_gear_type_is_unassessed_not_tricycle():
    asm = Assembly.from_dict(TAIL["assembly"])
    g = gear_layout(asm, [1.2, 0, 0.1], [1.4, 0, 0.1], {"type": "quadcycle"})
    assert g["status"] == "unassessed"
    assert g["checks"][0][1] is None
    assert "triciclo" in g["checks"][0][2].lower() or "tricycle" in g["checks"][0][2].lower()


def test_ski_without_length_is_unassessed():
    asm = Assembly.from_dict(TAIL["assembly"])
    g = layout_ski(asm, [1.2, 0, 0.1], [1.4, 0, 0.1], {"type": "ski", "ski": {}})
    assert g["status"] == "unassessed"
    assert g["checks"][0][1] is None
    assert "length_m" in g["checks"][0][2]


def test_taildragger_layout_and_prop_clearance_9in():
    out = analyse(copy.deepcopy(TAIL), TAIL["flight"], {"run_avl": False})
    g = out.gear
    assert g["type"] == "taildragger"
    assert g["status"] == "assessed"
    assert g["x_main"] < g["x_tail"]
    by = {c[0]: c for c in g["checks"]}
    assert "asm:gear_tipback" in by and "asm:gear_position" in by
    assert "asm:gear_prop_clearance" in by
    assert "9 in" in by["asm:gear_prop_clearance"][2] or "0.228" in by["asm:gear_prop_clearance"][2]
    assert by["asm:gear_prop_clearance"][1] is True
    assert by["asm:gear_tipback"][1] is True
    assert by["asm:gear_position"][1] is True
    # Drawn legs + retract
    assert g.get("devices", {}).get("drawn_legs")
    assert any(c["name"] == "gear_main_leg" for c in g["devices"]["drawn_legs"])
    assert g["devices"]["retract"]["status"] == "assessed"
    print("TAILDRAGGER", {k: round(g[k], 4) if isinstance(g.get(k), float) else g.get(k)
                          for k in ("x_main", "x_tail", "h_cg", "tipback_deg", "prop_clearance_m", "wheelbase")})


def test_ski_layout_with_supplied_length():
    out = analyse(copy.deepcopy(SKI), SKI["flight"], {"run_avl": False})
    g = out.gear
    assert g["type"] == "ski" and g["status"] == "assessed"
    assert g["ski"]["length_m"] == pytest.approx(1.40)
    by = {c[0]: c for c in g["checks"]}
    assert by["asm:gear_position"][1] is True
    print("SKI", g["ski"], "tipback", g.get("tipback_deg"), "prop", g.get("prop_clearance_m"))


def test_draw_legs_and_retract_missing_unassessed():
    layout = {"type": "taildragger", "ground_z": -0.4, "h_cg": 0.5, "x_main": 1.0, "x_tail": 3.0,
              "half_track_min": 0.4}
    legs = draw_legs(layout, {"draw_legs": True, "leg_diameter_m": 0.05, "half_track": 0.5})
    assert len(legs) >= 2 and all(L["role"] == "gear_leg" for L in legs)
    lines = leg_drawing_lines(layout, {"half_track": 0.5})
    assert any(L["view"] == "side" for L in lines) and any(L["view"] == "plan" for L in lines)
    r = check_retract(Assembly.from_dict(TAIL["assembly"]), layout, None)
    assert r["status"] == "unassessed"
    spec = copy.deepcopy(TAIL)
    spec["gear"] = {"type": "taildragger", "draw_legs": True, "half_track": 0.5}
    # fake layout stations
    _, rep = apply_gear_devices(spec, {**layout, "type": "taildragger"})
    assert rep.get("drawn_legs")
    assert rep["retract"]["status"] == "unassessed"


def test_fixed_type_ski_unassessed_without_geometry():
    # Minimal stub DesignResult-like object via _aircraft helper from test_wb_gear
    import importlib.util
    spec = importlib.util.spec_from_file_location("twb", ROOT / "tests" / "test_wb_gear.py")
    twb = importlib.util.module_from_spec(spec); spec.loader.exec_module(twb)
    _aircraft = twb._aircraft
    res = _aircraft(gear="ski")
    class Ends:
        def __init__(self):
            self.x_min_m, self.x_max_m = 2.0, 2.2
    res.weight_balance = Ends()
    out = analyse_landing_gear(res)
    assert out.kind == "ski"
    pos = [c for c in out.checks if c[0] == "gear:position"]
    assert pos and pos[0][1] is None
    assert "unassessed" in pos[0][2]


def test_fixed_type_ski_with_length_places_contacts():
    import importlib.util
    spec = importlib.util.spec_from_file_location("twb", ROOT / "tests" / "test_wb_gear.py")
    twb = importlib.util.module_from_spec(spec); spec.loader.exec_module(twb)
    _aircraft = twb._aircraft
    res = _aircraft(gear="ski")
    class Ends:
        def __init__(self):
            self.x_min_m, self.x_max_m = 2.0, 2.2
    res.weight_balance = Ends()
    res.spec.assumptions["landing_gear"]["ski"] = {"length_m": 1.5, "attach_x": 2.1}
    out = analyse_landing_gear(res)
    assert out.x_main_m is not None and out.x_tail_m is not None
    assert out.x_tail_m - out.x_main_m == pytest.approx(1.5)
    tip = [c for c in out.checks if c[0] == "gear:tipback"]
    assert tip and tip[0][1] is not None


def test_tricycle_path_unchanged_smoke():
    """Backward compatible: tricycle still works; omit new options → no devices report required."""
    from acdt.domains.aircraft.assembly.sizing import gear_layout as gl
    twin = json.loads((EX / "twin_boom_pusher.json").read_text(encoding="utf-8"))
    # twin has no gear; place tricycle explicitly
    asm = Assembly.from_dict(twin["assembly"])
    # Use synthetic CGs near the pod
    g = gl(asm, [1.5, 0, 0.05], [1.8, 0, 0.05], {"type": "tricycle", "nose_fraction": [0.08, 0.15]})
    assert g["type"] == "tricycle"
    assert "devices" not in g
