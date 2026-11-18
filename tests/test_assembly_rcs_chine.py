"""Body.chine hexagonal edges in the PO mesh + aero/RCS study reading the assembly (not parallel geometry)."""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly.components import Body
from acdt.domains.aircraft.assembly.integration import Item
from acdt.domains.aircraft.assembly.rcs_bridge import build_rcs_mesh, feature_inventory, apply_chine_deg
from acdt.domains.aircraft.rcs.study import eval_assembly, run_assembly_study

EX = Path(__file__).resolve().parents[1] / "examples" / "integration"
CHINE = EX / "chine_fuselage_rcs.json"


def test_body_chine_mesh_has_six_side_edges():
    b = Body.pod("f", length=2.0, width=0.4, height=0.36, chine_deg=45.0)
    assert b.chine["angle_deg"] == 45.0
    V, F = b.mesh()
    # mid-station ring: exactly 6 vertices (not the smooth 24)
    xs = sorted(set(np.round(V[:, 0], 6)))
    mid_x = xs[len(xs) // 2]
    ring = V[np.isclose(V[:, 0], mid_x)]
    # cap stations may share x with tip; filter by |y| or |z| span
    assert len(ring) in (6, 7)  # 6 ring + optional cap centre coinciding — usually 6
    # sharp chine vertices at z ≈ 0 with |y| ≈ W/2
    chine_pts = ring[np.abs(ring[:, 2]) < 1e-8]
    assert len(chine_pts) >= 2
    assert abs(chine_pts[:, 1]).max() > 0.15


def test_chine_angle_changes_section_width():
    b45 = Body.pod("a", length=2.0, width=0.4, height=0.36, chine_deg=45.0)
    b25 = Body.pod("b", length=2.0, width=0.4, height=0.36, chine_deg=25.0)
    # same D → different W from hexagon_section
    r45 = b45.chine_ring(0.4, 0.36)
    r25 = b25.chine_ring(0.4, 0.36)
    W45 = 2 * abs(r45[0, 0])
    W25 = 2 * abs(r25[0, 0])
    assert W25 > W45  # shallower chine → wider section for same area


def test_smooth_body_unchanged_default():
    b = Body.pod("s", length=2.0, width=0.4, height=0.3)
    assert b.chine is None
    V, _ = b.mesh()
    assert len(V) > 200  # 24-pt rings


def test_inventory_marks_prop_excluded_and_items_included():
    spec = json.loads(CHINE.read_text(encoding="utf-8"))
    asm = Assembly.from_dict(spec["assembly"])
    items = [Item.from_dict(d) for d in spec["items"]]
    inv = feature_inventory(asm, items)
    names_in = {e["name"] for e in inv["included"]}
    names_ex = {e["name"] for e in inv["excluded_presupposto"]}
    assert "fuselage" in names_in and "eo_ball" in names_in and "antenna_mast" in names_in
    assert "prop" in names_ex
    fuse = next(e for e in inv["included"] if e["name"] == "fuselage")
    assert fuse.get("chine", {}).get("angle_deg") == 45.0
    assert inv["unassessed"] == [] or all("reason" in u for u in inv["unassessed"])


def test_build_rcs_mesh_includes_items():
    spec = json.loads(CHINE.read_text(encoding="utf-8"))
    asm = Assembly.from_dict(spec["assembly"])
    items = [Item.from_dict(d) for d in spec["items"]]
    m0, _ = build_rcs_mesh(asm, items=None)
    m1, inv = build_rcs_mesh(asm, items=items)
    assert m1.n_facets > m0.n_facets
    assert {e["name"] for e in inv["included"]} >= {"eo_ball", "avionics_box", "antenna_mast"}


def test_eval_assembly_reads_chine_not_parallel_geometry():
    spec = json.loads(CHINE.read_text(encoding="utf-8"))
    r45 = eval_assembly(spec, daz=5.0, chine_deg=45.0)
    r25 = eval_assembly(spec, daz=5.0, chine_deg=25.0)
    assert r45["source"] == "assembly"
    assert r45["n_facets"] == r25["n_facets"]
    assert r45["rcs"]["all"]["mean_dbsm"] != pytest.approx(r25["rcs"]["all"]["mean_dbsm"], abs=1e-4)
    assert any(m["var"] == "chine_deg" for m in r45["mapped_shape_vars"])
    un = {u["var"] for u in r45["unassessed_shape_vars"]}
    assert {"sweep_le_deg", "align", "tail_cant_deg"} <= un
    assert r45["aero"]["status"] == "assessed"
    assert r45["aero"]["CD0"] > 0
    # L/D may be unassessed when K missing — must not be silently zero
    if "LD" not in r45["aero"]:
        assert "unassessed" in (r45["aero"].get("ld_note") or "").lower() or "not" in (r45["aero"].get("ld_note") or "").lower()


def test_unplaced_item_is_unassessed_not_dropped():
    spec = json.loads(CHINE.read_text(encoding="utf-8"))
    spec = json.loads(json.dumps(spec))
    spec["items"].append({"name": "loose", "mass_kg": 0.5, "size_m": [0.1, 0.1, 0.1], "shape": "box"})
    r = eval_assembly(spec, daz=10.0)
    names = {u["name"] for u in r["inventory"]["unassessed"]}
    assert "loose" in names


def test_apply_chine_deg_only_already_chined():
    asm = Assembly.from_dict(json.loads(CHINE.read_text(encoding="utf-8"))["assembly"])
    touched = apply_chine_deg(asm, 30.0)
    assert touched == ["fuselage"]
    fuse = next(c for c in asm.components if c.name == "fuselage")
    assert fuse.chine["angle_deg"] == 30.0


def test_run_assembly_study_writes_report(tmp_path):
    rep = run_assembly_study(CHINE, tmp_path, n_samples=3, seed=0, daz=5.0, log=lambda *_: None)
    assert (tmp_path / "assembly_rcs_study.json").exists()
    assert (tmp_path / "assembly_rcs_study.md").exists()
    assert rep["baseline_rcs_mean_dbsm"] == pytest.approx(rep["rows"][0]["rcs_mean_dbsm"])
    assert len(rep["rows"]) == 4  # baseline + 3
    assert math.isfinite(rep["baseline_rcs_mean_dbsm"])


def test_cli_rcs_study_assembly(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "acdt.cli", "rcs", "study", str(CHINE),
         "-o", str(tmp_path), "--samples", "3", "--freq", "10"],
        capture_output=True, text=True, env={**dict(**{k: v for k, v in __import__("os").environ.items()}),
                                             "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "assembly_rcs_study.json").exists()
    assert "unassessed" in r.stdout.lower() or "inventário" in r.stdout.lower()


def test_cli_shape_study_assembly(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "acdt.cli", "shape", "study",
         "--assembly", str(CHINE), "-o", str(tmp_path), "--samples", "2"],
        capture_output=True, text=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "assembly_rcs_study.json").exists()


def test_cli_integration_rcs_inventory(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "acdt.cli", "integration", str(CHINE), "-o", str(tmp_path), "--rcs"],
        capture_output=True, text=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    inv = json.loads((tmp_path / "rcs_inventory.json").read_text(encoding="utf-8"))
    assert any(e.get("chine") for e in inv["included"] if e["name"] == "fuselage")
    assert any(e["name"] == "prop" for e in inv["excluded_presupposto"])
