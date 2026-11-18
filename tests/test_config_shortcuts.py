# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Configuration shortcuts (V / inverted_V / twin_boom) and explicit dihedral → spiral."""
from pathlib import Path
import math
import pytest

from acdt.domains.aircraft.assembly.shortcuts import build_shortcut, resolve_assembly_shortcut, SHORTCUTS
from acdt.domains.aircraft.assembly.sizing import classify_surface, surface_geometry
from acdt.domains.aircraft.mission import MissionSpec
from acdt.domains.aircraft.sizing import build_configuration, run as size_run

ROOT = Path(__file__).resolve().parents[1]
UAV = ROOT / "examples" / "uav_gasoline_150kg.yaml"


def _geo_aero():
    return (
        dict(fuselage_length_m=3.2, fuselage_diameter_m=0.40, c_ht=0.55, c_vt=0.03,
             tail_arm_fraction=0.55, dihedral_deg=2.0, ar_v=1.5),
        dict(AR=16, taper=0.6, sweep_c4_deg=0.0, tc_root=0.15, tc_tip=0.12),
    )


def test_shortcut_names_and_refuse_missing_volumes():
    assert "inverted_V" in SHORTCUTS and "twin_boom" in SHORTCUTS
    geo, aero = _geo_aero()
    bad = {k: v for k, v in geo.items() if k not in ("c_ht", "c_vt")}
    with pytest.raises(ValueError, match="c_ht"):
        build_shortcut("inverted_V", geo=bad, aero=aero)


def test_inverted_v_is_vee_not_hv_substitute():
    from acdt.domains.aircraft.assembly import Assembly
    from acdt.domains.aircraft.assembly.components import Surface
    geo, aero = _geo_aero()
    geo["configuration"] = "inverted_V"
    geo["tail_dihedral_deg"] = -35.0
    d = build_shortcut("inverted_V", geo=geo, aero=aero)
    names = [c["name"] for c in d["assembly"]["components"]]
    assert "tail" in names and "htail" not in names and "vtail" not in names
    asm = Assembly.from_dict(d["assembly"])
    surfs = [c for c in asm.components if isinstance(c, Surface) and not c.mirrored_image]
    areas = {s.name: surface_geometry(s)["S"] for s in surfs}
    largest = max(areas, key=areas.get)
    kinds = {s.name: classify_surface(s, surface_geometry(s), s.name == largest) for s in surfs}
    geos = {s.name: surface_geometry(s) for s in surfs}
    assert kinds["tail"] == "vee"
    assert abs(geos["tail"]["dihedral_deg"]) == pytest.approx(35.0)
    # Signed cant kept on the panel (inverted = negative); geometry summary uses |Γ|.
    raw = next(c for c in d["assembly"]["components"] if c["name"] == "tail")
    assert raw["panel"]["dihedral_deg"] == pytest.approx(-35.0)
    assert d["options"]["vee"]["S_panel_m2"] > 0


def test_twin_boom_has_booms_and_vee():
    geo, aero = _geo_aero()
    d = build_shortcut("twin_boom", geo=geo, aero=aero)
    roles = {c["name"]: c.get("role") for c in d["assembly"]["components"]}
    assert roles.get("boom") == "boom" and "inverted" in (roles.get("tail") or "").lower()
    assert d["options"]["shortcut"] == "twin_boom"


def test_resolve_does_not_overwrite_supplied_assembly():
    spec = MissionSpec.from_yaml(UAV)
    spec.assumptions["geometry"]["configuration"] = "inverted_V"
    spec.assumptions["geometry"]["c_ht"] = 0.55
    spec.assumptions["geometry"]["c_vt"] = 0.03
    spec.assumptions["assembly"] = {"file": str(ROOT / "examples/integration/twin_boom_pusher.json")}
    d, note = resolve_assembly_shortcut(spec)
    assert d is None and note is None


def test_dihedral_explicit_reaches_wing():
    spec = MissionSpec.from_yaml(UAV)
    spec.assumptions["geometry"]["dihedral_deg"] = 5.0
    cfg = build_configuration(spec, W0=150.0, ws=150.0 * 9.80665 / 2.5)
    assert math.degrees(cfg.wing.dihedral) == pytest.approx(5.0)


@pytest.mark.requires_avl
def test_spiral_unassessed_without_explicit_dihedral(tmp_path):
    from acdt.core.pipeline import run_pipeline
    spec = MissionSpec.from_yaml(UAV)
    spec.assumptions["geometry"]["dihedral_deg"] = None  # explicit null → unassessed
    st = run_pipeline("aircraft", spec, output=tmp_path / "spiral0")
    res = st["result"]
    spiral = [c for c in res.checks if c.key == "hq:spiral"]
    assert spiral, "hq:spiral row expected"
    assert spiral[0].ok is None
    assert "unassessed" in spiral[0].message.lower()
    assert "dihedral" in spiral[0].message.lower()


@pytest.mark.requires_avl
def test_spiral_assessed_with_explicit_dihedral(tmp_path):
    from acdt.core.pipeline import run_pipeline
    import math
    spec = MissionSpec.from_yaml(UAV)
    spec.assumptions["geometry"]["dihedral_deg"] = 2.0
    st = run_pipeline("aircraft", spec, output=tmp_path / "spiral1")
    res = st["result"]
    assert math.degrees(res.config.wing.dihedral) == pytest.approx(2.0)
    spiral = [c for c in res.checks if c.key == "hq:spiral"]
    assert spiral and spiral[0].ok is not None
    assert "Γ=2" in spiral[0].message


@pytest.mark.slow
def test_inverted_v_shortcut_size_runs():
    """Runnable example path: configuration shortcut injects assembly; size converges."""
    from acdt.domains.aircraft.assembly.shortcuts import resolve_assembly_shortcut
    spec = MissionSpec.from_yaml(UAV)
    g = spec.assumptions["geometry"]
    g["configuration"] = "inverted_V"
    g["dihedral_deg"] = 2.0
    g["tail_dihedral_deg"] = -35.0
    g["c_ht"] = 0.55
    g["c_vt"] = 0.04
    drawing, note = resolve_assembly_shortcut(spec)
    assert drawing is not None and "inverted_V" in (note or "")
    spec.assumptions["assembly"] = drawing
    res = size_run(spec)
    assert res.sizing.converged
    assert res.assembly_loop is not None
    opt = res.assembly_loop.get("options") or res.assembly_loop.get("spec", {}).get("options") or {}
    assert opt.get("shortcut") == "inverted_V"
    assert res.sizing.W0 > 50
