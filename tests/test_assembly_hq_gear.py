"""hq:* and gear:* read from the generic assembly (P1b follow-up, :mod:`acdt.domains.aircraft.assembly.handling`).

The flying wing's winglets (vertical volume ≈ 0.028, Raymer Eq. 6.29) and the twin boom's placed tricycle now
reach the MIL-F-8785C and Raymer Ch. 11 checks; the limits are the same. Without an assembly nothing changes.
Most cases are one AVL call on an as-drawn example; the two sized examples are in test_assembly_p1b_leftovers.
"""
from __future__ import annotations

import copy
import json
import math
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly import handling as hd
from acdt.domains.aircraft.assembly.sizing import analyse, main_wing
from acdt.domains.aircraft.landing_gear import LandingGearResult
from acdt.domains.aircraft.sizing import CheckResult

EX = Path(__file__).resolve().parents[1] / "examples"
TWIN = json.loads((EX / "integration" / "twin_boom_pusher.json").read_text(encoding="utf-8"))
FW = json.loads((EX / "integration" / "flying_wing_pusher.json").read_text(encoding="utf-8"))
needs_avl = pytest.mark.requires_avl
TWIN_FLIGHT = {"W0_kg": 140.0, "V_m_s": 40.0, "altitude_m": 1000.0, "Wf_kg": 25.0, "payload_kg": 20.0}


def _res(W0, V, h, CD0=0.03, K=0.03, kind="electric"):
    """The fields of a sized DesignResult that :func:`hd.dynamics` reads."""
    return SimpleNamespace(cruise_altitude=h, cruise_speed=V, sizing=SimpleNamespace(W0=W0),
                           polar=SimpleNamespace(CD0=CD0, K=K), spec=SimpleNamespace(propulsion_kind=kind, aircraft_class="uav"))


def test_vertical_volume_of_the_drawings():
    """Projected side area × arm to the wing a.c. (Raymer Eq. 6.29): the winglets ≈ 0.028 (as in HANDOFF §4b)."""
    for spec, ref in ((FW, 0.028), (TWIN, 0.0997)):
        a = Assembly.from_dict(spec["assembly"])
        assert hd.vertical_volume(a, main_wing(a)[1]["x_ac"]) == pytest.approx(ref, abs=1e-3)


def test_body_cnb_is_raymer_16_47_with_the_mesh_volume():
    a = Assembly.from_dict(FW["assembly"])
    g = main_wing(a)[1]
    tot, per = hd.body_cnb(a, g["S"], g["b"])
    body = a.get("centerbody")
    D, W = max(s["h"] for s in body.stations), max(s["w"] for s in body.stations)
    assert per["centerbody"] == pytest.approx(-1.3 * abs(body.volume()) / (g["S"] * g["b"]) * D / W)
    assert tot < 0
    t2, p2 = hd.body_cnb(Assembly.from_dict(TWIN["assembly"]), 1.0, 1.0)
    assert set(p2) >= {"pod", "boom"} and p2["boom"] < 0


def test_inertias_parallel_axis_and_point_masses():
    """Point masses add m·d² about the case CG; mirrored parts give roll inertia (Roskam Part V Ch. 10)."""
    spec = copy.deepcopy(FW)
    out = analyse(spec, FW["flight"], {"run_avl": False})
    a = Assembly.from_dict(spec["assembly"])
    I = hd.inertias(a, out, "cheio")
    assert I["m"] == pytest.approx(out.loading["cases"]["cheio"]["mass_kg"])
    assert I["m_structure_spread"] + I["m_point"] == pytest.approx(I["m"], rel=1e-9)
    assert 0 < I["Ixx"] < I["Izz"] and I["Iyy"] > 0              # flying wing: span dominates roll/yaw
    # one more kilogram 1 m aft of the CG along x adds 1 kg·m² to Iyy and Izz and nothing to Ixx
    cg = out.loading["cases"]["cheio"]["cg"]
    out.loading["rows"]["cheio"] = list(out.loading["rows"]["cheio"]) + [("probe", 1.0, [cg[0] + 1.0, cg[1], cg[2]])]
    out.loading["cases"]["cheio"] = {**out.loading["cases"]["cheio"]}   # CG kept: measure about the same point
    J = hd.inertias(a, out, "cheio")
    assert J["Iyy"] - I["Iyy"] == pytest.approx(1.0) and J["Izz"] - I["Izz"] == pytest.approx(1.0)
    assert J["Ixx"] == pytest.approx(I["Ixx"])


@needs_avl
def test_flying_wing_modes_see_the_winglets():
    """As drawn (18 kg): AVL of the assembly at cruise CL; Cnβ > 0 from the winglets, no tail → Cmα̇ = 0."""
    out = analyse(FW, FW["flight"])
    md = hd.dynamics(_res(18.0, 24.0, 500.0), FW, out)
    d = md["derivatives"]
    assert d["c_vt_measured"] == pytest.approx(0.028, abs=1e-3)
    assert d["Cnb_avl"] > 0 and d["Cnb_bodies"] < 0
    assert d["Cmad"] == 0.0 and d["tails_cmad"] == []
    assert d["Clb"] < 0 and d["Clp"] < 0 and d["Cnr"] < 0
    assert d["SM"] == pytest.approx(out.static_margin["cheio"], rel=1e-9)
    assert md["lateral"].get("dutch_roll") and md["longitudinal"].get("short_period")
    assert md["inertia"]["scale_W0_over_assembly"] == pytest.approx(1.0, abs=0.05)
    # the fixed-type rows are replaced, the scissor stays, nothing else is touched
    hq_keys = ["hq:scissor", "hq:short_period", "hq:CAP", "hq:phugoid", "hq:dutch_roll", "hq:roll", "hq:spiral"]
    res = _res(18.0, 24.0, 500.0)
    res.checks = [CheckResult(k, True, "tipo fixo") for k in hq_keys] + [CheckResult("trim", True, "x")]
    res.dynamics = {"modes": {"x": 1}, "hq": [{"key": k[3:]} for k in hq_keys[1:]], "hq_category": "B",
                    "hq_required_level": 1}
    res.issues, res.landing_gear = [], None
    rec = hd.apply(res, {**FW, "options": {}}, out)
    assert not res.issues, [i.message for i in res.issues]
    msgs = {c.key: c.message for c in res.checks}
    assert msgs["hq:scissor"] == "tipo fixo" and msgs["trim"] == "x"
    for k in hq_keys[1:]:
        assert msgs[k].startswith("montagem:") and msgs[k].endswith("UAV: indicativo"), msgs[k]
    assert res.dynamics["source"] == "assembly" and res.dynamics["fixed_type"]["modes"] == {"x": 1}
    assert len(rec["fixed_type"]["hq"]) == 6
    assert rec["gear"] is None                                    # no gear: fixed type stays


def test_gear_rows_from_the_placed_tricycle():
    g = {"type": "tricycle", "x_nose": 0.7, "x_main": 2.7, "h_cg": 0.6, "tipback_deg": 15.0,
         "nose_fraction": [0.08, 0.139], "half_track_min": 0.365, "rotation_deg": 13.9,
         "rotation_first_contact": [5.5, 1.0, 0.08]}
    rows = {k: (ok, m) for k, ok, m in hd.gear_rows(g)}
    assert set(rows) == set(hd.GEAR_KEYS)
    assert all(ok for ok, _ in rows.values())
    assert "0.730 m" in rows["gear:overturn"][1]
    bad = {k: ok for k, ok, _ in hd.gear_rows({**g, "nose_fraction": [0.05, 0.12], "rotation_deg": 8.0})}
    assert not bad["gear:nose_load"] and not bad["gear:rotation"] and bad["gear:tipback"]
    none = {k: ok for k, ok, _ in hd.gear_rows({**g, "x_nose": None})}
    assert not none["gear:position"] and not none["gear:nose_load"] and none["gear:tipback"]


@needs_avl
def test_twin_boom_gear_rows_replace_the_fixed_type():
    spec = copy.deepcopy(TWIN)
    spec["masses"] = [{"name": "engine", "mass_kg": 12.0, "position": [2.45, 0.0, 0.0], "group": "propulsion"}]
    out = analyse(spec, TWIN_FLIGHT)
    res = _res(140.0, 40.0, 1000.0, kind="piston")
    lg = LandingGearResult("tricycle", checks=[("gear:position", False, "fuselagem 0–3.2 m"),
                                               ("gear:tipback", False, "sem posição"),
                                               ("gear:stroke", True, "curso")])
    res.landing_gear, res.issues, res.dynamics = lg, [], None
    res.checks = [CheckResult(k, ok, m) for k, ok, m in lg.checks]
    rec = hd.apply(res, spec, out)
    keys = {c.key: c for c in res.checks}
    assert set(hd.GEAR_KEYS) <= set(keys) and keys["gear:stroke"].message == "curso"
    for k in hd.GEAR_KEYS:
        assert keys[k].message.startswith("montagem:")
    asm = {c[0]: c[1] for c in out.checks}
    assert keys["gear:tipback"].ok == asm["asm:gear_tipback"]
    assert keys["gear:rotation"].ok == asm["asm:gear_rotation"]
    assert {k for k, _, _ in lg.checks} == set(hd.GEAR_KEYS) | {"gear:stroke"}
    assert [k for k, _, _ in rec["fixed_type"]["gear"]] == ["gear:position", "gear:tipback"]
    # options.checks_from: fixed_type keeps the old rows
    res.checks = [CheckResult("gear:position", False, "fuselagem")]
    rec = hd.apply(res, {**spec, "options": {"checks_from": "fixed_type"}}, out)
    assert res.checks[0].message == "fuselagem" and "fixed_type" in rec["note"]


def test_no_assembly_leaves_the_checks_alone():
    from acdt.domains.aircraft.phase2 import _assembly
    res = SimpleNamespace(spec=SimpleNamespace(assumptions={}), checks=[CheckResult("hq:dutch_roll", True, "x")],
                          issues=[], assembly=None)
    _assembly(res)
    assert res.assembly is None and res.checks[0].message == "x" and not res.issues
