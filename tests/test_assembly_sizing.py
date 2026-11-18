"""P1b: the generic assembly evaluated as an aircraft (per-part masses, CD0 buildup, AVL with bodies, gear,
loading) and its hook into ``acdt size`` (``assumptions.assembly``)."""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly.sizing import (analyse, assembly_from_design, assembly_stage, classify_surface,
                                                   surface_geometry,
                                                   structure_weights)

EX = Path(__file__).resolve().parents[1] / "examples"
TWIN = json.loads((EX / "integration" / "twin_boom_pusher.json").read_text(encoding="utf-8"))
FLYING_WING = json.loads((EX / "integration" / "flying_wing_pusher.json").read_text(encoding="utf-8"))
needs_avl = pytest.mark.requires_avl


def _twin():
    spec = copy.deepcopy(TWIN)
    spec["masses"] = [{"name": "engine", "mass_kg": 12.0, "position": [2.45, 0.0, 0.0], "group": "propulsion"}]
    return spec


@needs_avl
def test_twin_boom_pusher_parts_drag_np_and_gear():
    r = analyse(_twin(), {"W0_kg": 140.0, "V_m_s": 40.0, "altitude_m": 1000.0, "Wf_kg": 25.0, "payload_kg": 20.0})
    kinds = {p.name: p.kind for p in r.structure}
    assert kinds["wing"] == "wing" and kinds["tail"] == "vee"
    assert {kinds[b] for b in ("pod", "boom", "radome")} == {"body"}
    tail = next(p for p in r.structure if p.name == "tail")
    assert "15.47" in tail.method and "15.48" in tail.method and "Purser" in tail.method
    assert all(p.mass_kg > 0 for p in r.structure)
    # wetted-area buildup: every part contributes, total in the usual small-UAV band (Raymer Table 12.3 order)
    assert {c["component"] for c in r.drag["components"]} >= {"wing", "tail", "pod", "boom"}
    assert 0.015 < r.drag["CD0"] < 0.050          # Table 12.3 order; the pusher's inverted-V is large
    # bodies move the neutral point forward with both methods
    assert r.np["x_np_avl_bodies"] < r.np["x_np_no_bodies"]
    assert r.np["x_np_torenbeek"] < r.np["x_np_no_bodies"]
    assert set(r.static_margin) == {"vazio", "carga", "combustível", "cheio"}
    # gear from the geometry: the pusher disc is what touches first in rotation
    keys = {c[0]: c for c in r.checks}
    for k in ("asm:gear_tipback", "asm:gear_rotation", "asm:gear_prop_clearance", "asm:gear_position",
              "asm:static_margin", "asm:integration"):
        assert k in keys
    assert r.gear["rotation_first_contact"][0] > 2.6
    assert r.gear["prop_clearance_m"] >= 0.1778 - 1e-6           # 7 in, 14 CFR 23.925(a)(1)
    assert keys["asm:integration"][1]
    # the illustrative layout is not balanced (pusher engine aft of the wing): the check must say so
    assert not keys["asm:static_margin"][1]


@needs_avl
def test_flying_wing_without_tail():
    r = analyse(FLYING_WING, FLYING_WING["flight"])
    kinds = {p.name: p.kind for p in r.structure}
    assert kinds == {"wing": "wing", "winglet": "vtail", "centerbody": "body"}
    assert all("composite" in p.method for p in r.structure)
    assert r.np["np_source"] == "avl_torenbeek"
    sm = min(r.static_margin.values())
    assert 0.05 <= sm < 0.15
    assert dict((c[0], c[1]) for c in r.checks)["asm:static_margin"]
    assert not any("massa montada" in n for n in r.notes)       # W0 of the example closes with the parts


def test_remaining_fuel_sits_at_the_drawn_tanks():
    """Mission fuel beyond the drawn tank mass stays in those tanks (Raymer: fuel is tanked fuel)."""
    spec = copy.deepcopy(TWIN)
    spec["options"] = {"run_avl": False}
    r = analyse(spec, {"W0_kg": 140.0, "V_m_s": 40.0, "altitude_m": 0.0, "Nz": 4.0,
                       "Wf_kg": 50.0, "payload_kg": 30.0})
    note = next(n for n in r.notes if "tanques desenhados" in n)
    assert note.startswith("16.00 kg")
    tank_x = next(i for i in spec["items"] if i["name"] == "fuel_tank")["position"][0]
    x_empty = r.loading["cases"]["vazio"]["cg"][0]
    x_fuel = r.loading["cases"]["combustível"]["cg"][0]
    m_empty = r.loading["cases"]["vazio"]["mass_kg"]
    # 50 kg of fuel, all of it at the drawn tank (34 kg drawn + 16 kg remainder)
    assert x_fuel == pytest.approx((m_empty * x_empty + 50.0 * tank_x) / (m_empty + 50.0), rel=1e-6)


def test_canard_and_fin_classification_without_avl():
    asm = Assembly.from_dict({"components": [
        {"type": "body", "name": "f", "role": "fuselage", "pod": {"length": 3.0, "width": 0.4}},
        {"type": "surface", "name": "w", "role": "wing", "origin": [1.8, 0, 0], "mirror": True,
         "panel": {"root_chord": 0.6, "tip_chord": 0.4, "span": 2.0, "sweep_le_deg": 20}},
        {"type": "surface", "name": "c", "role": "canard", "origin": [0.4, 0, 0], "mirror": True,
         "panel": {"root_chord": 0.3, "tip_chord": 0.2, "span": 0.7}},
        {"type": "surface", "name": "v", "role": "fin", "origin": [2.4, 0, 0],
         "panel": {"root_chord": 0.5, "tip_chord": 0.3, "span": 0.5, "dihedral_deg": 90}}]})
    assert classify_surface(asm.get("c"), surface_geometry(asm.get("c")), False) == "canard"
    assert classify_surface(asm.get("v"), surface_geometry(asm.get("v")), False) == "vtail"
    parts = {p.name: p for p in structure_weights(asm, 60.0, 5.7, 1200.0, "metal")}
    assert "15.47" in parts["c"].method and "15.48" in parts["v"].method and "15.46" in parts["w"].method


@pytest.mark.slow
@needs_avl
def test_fixed_type_adapter_reproduces_the_c172_layout():
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.phase2 import stability_stage
    from acdt.domains.aircraft.sizing import run
    res = run(MissionSpec.from_yaml(EX / "cessna172_check.yaml"))
    stability_stage(res)
    out, cmp = assembly_stage(res, assembly_from_design(res))
    assert cmp["S_assembly_m2"] == pytest.approx(cmp["S_sized_m2"], rel=1e-6)
    assert cmp["structure_assembly_kg"] == pytest.approx(cmp["structure_sized_kg"], rel=0.15)
    mac, le = out.np["mac"], out.np["x_mac_le"]
    xs = [(c["cg"][0] - le) / mac for c in out.loading["cases"].values()]
    lo, hi = res.stability.cg_range_mac
    assert min(xs) == pytest.approx(lo, abs=0.04) and max(xs) == pytest.approx(hi, abs=0.04)
    assert (out.np["x_np_no_bodies"] - le) / mac == pytest.approx(res.stability.xbar_np_avl, abs=0.03)
    # stable with the handbook body shift; AVL BODY alone is far more pessimistic and is flagged
    assert dict((c[0], c[1]) for c in out.checks)["asm:static_margin"]
    assert any("validação limitada" in n for n in out.notes)


@needs_avl
def test_size_hook_reports_assembly_checks_without_changing_feasibility():
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.phase2 import stability_stage
    from acdt.domains.aircraft.sizing import run
    spec = MissionSpec.from_yaml(EX / "uav_gasoline_150kg.yaml")
    spec.assumptions["assembly"] = {"file": str(EX / "integration" / "twin_boom_pusher.json"),
                                    "options": {"in_loop": False}}
    res = run(spec)
    stability_stage(res)
    assert res.assembly is not None, [i.message for i in res.issues]
    assert res.assembly_loop is None                 # in_loop: false → old post-sizing evaluation only
    checks = {c.key: c.ok for c in res.checks if c.key.startswith("asm:")}
    assert not checks["asm:wing_area"]               # drawn 2.34 m² vs sized wing: flagged, not rescaled
    assert "asm:static_margin" in checks and "asm:gear_rotation" in checks
    assert res.feasible                              # asm: checks are layout checks (LAYOUT_PREFIXES)
    assert res.assembly["comparison"]["structure_sized_kg"] > 0


@needs_avl
def test_cli_and_toolkit_entry_points(tmp_path, monkeypatch):
    from acdt.ai import assembly as A
    from acdt.cli import main
    monkeypatch.setenv("ACDT_RUNS_DIR", str(tmp_path / "runs"))
    rc = main(["integration", str(EX / "integration" / "flying_wing_pusher.json"), "--size", "-o", str(tmp_path)])
    assert rc == 0 and (tmp_path / "assembly_sizing.json").exists()
    r = A.assembly_sizing(FLYING_WING, FLYING_WING["flight"], name="fw")
    assert r["checks"] and Path(r["files"]["result"]).exists()
