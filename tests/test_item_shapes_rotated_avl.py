# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Item sphere/cylinder shapes (Meriam & Kraige) and rotated-body AVL → unassessed."""
from __future__ import annotations

import copy
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly.integration import Item, check, mass_properties, _item_body
from acdt.domains.aircraft.assembly.sizing import _body_is_rotated, analyse, avl_geometry, neutral_point

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "integration"
DEMO = json.loads((EX / "shapes_and_rotated_body.json").read_text(encoding="utf-8"))
needs_avl = pytest.mark.requires_avl


def test_item_sphere_volume_and_inertia():
    it = Item.from_dict({"name": "ball", "mass_kg": 5.0, "size_m": [0.2, 0.2, 0.2], "shape": "sphere",
                         "position": [0, 0, 0]})
    r = 0.1
    assert it.volume_m3() == pytest.approx(4 / 3 * math.pi * r ** 3)
    I = it.inertia_about_centroid()
    assert I[0, 0] == pytest.approx(2 / 5 * 5.0 * r * r)
    assert I[1, 1] == pytest.approx(I[0, 0]) and I[2, 2] == pytest.approx(I[0, 0])
    assert len(it.samples()) >= 7


def test_item_cylinder_volume_and_inertia_about_z():
    it = Item.from_dict({"name": "mast", "mass_kg": 2.0, "size_m": [0.1, 0.1, 0.4],
                         "shape": "cylinder", "cylinder_axis": "z", "position": [0, 0, 0]})
    r, L = 0.05, 0.4
    assert it.volume_m3() == pytest.approx(math.pi * r * r * L)
    I = it.inertia_about_centroid()
    assert I[2, 2] == pytest.approx(0.5 * 2.0 * r * r)          # about axis
    assert I[0, 0] == pytest.approx(0.25 * 2.0 * r * r + 2.0 * L * L / 12.0)


def test_box_default_unchanged_inertia():
    it = Item.from_dict({"name": "box", "mass_kg": 3.0, "size_m": [0.3, 0.2, 0.1], "position": [1, 0, 0]})
    assert it.shape == "box"
    a, b, c = 0.3, 0.2, 0.1
    I = it.inertia_about_centroid()
    assert I[0, 0] == pytest.approx(3.0 / 12 * (b * b + c * c))


def test_item_body_meshes_sphere_and_cylinder():
    sph = Item.from_dict({"name": "s", "mass_kg": 1.0, "size_m": [0.2, 0.2, 0.2], "shape": "sphere",
                          "position": [1.0, 0.0, 0.0], "obstructs": True})
    b = _item_body(sph)
    assert b.volume() == pytest.approx(sph.volume_m3(), rel=0.08)
    cyl = Item.from_dict({"name": "c", "mass_kg": 1.0, "size_m": [0.4, 0.1, 0.1], "shape": "cylinder",
                          "cylinder_axis": "x", "position": [0.0, 0.0, 0.0]})
    bc = _item_body(cyl)
    assert abs(bc.orientation.get("yaw", 0)) < 1e-9
    cy = Item.from_dict({"name": "cy", "mass_kg": 1.0, "size_m": [0.1, 0.4, 0.1], "shape": "cylinder",
                         "cylinder_axis": "y", "position": [0, 0, 0]})
    assert _item_body(cy).orientation.get("yaw") == pytest.approx(90.0)


def test_demo_packaging_shapes_and_mass():
    r = check(DEMO["assembly"], DEMO["items"], DEMO["constraints"], DEMO.get("base"))
    mp = r["mass_properties"]
    assert mp["item_shapes"]["eo_ball"] == "sphere"
    assert mp["item_shapes"]["antenna_mast"] == "cylinder"
    assert mp["item_shapes"]["avionics_box"] == "box"
    assert mp["breakdown"]["eo_ball"]["volume_m3"] == pytest.approx(
        Item.from_dict(DEMO["items"][0]).volume_m3())
    # sphere inertia smaller than same-AABB box
    ball = Item.from_dict({**DEMO["items"][0]})
    boxish = Item.from_dict({**DEMO["items"][0], "shape": "box"})
    assert ball.inertia_about_centroid()[0, 0] < boxish.inertia_about_centroid()[0, 0]
    print("SHAPES mass", round(mp["mass_kg"], 3), "cg", [round(x, 4) for x in mp["cg"]],
          "Ixx", round(mp["inertia_kg_m2"]["Ixx"], 5))


def test_body_is_rotated_helper():
    asm = Assembly.from_dict(DEMO["assembly"])
    assert _body_is_rotated(asm.get("side_boom"))
    assert not _body_is_rotated(asm.get("fuselage"))


@needs_avl
def test_rotated_body_avl_unassessed_not_axis_aligned_standin(tmp_path):
    asm = Assembly.from_dict(DEMO["assembly"])
    _, notes, rotated = avl_geometry(asm, tmp_path, with_bodies=True)
    assert "side_boom" in rotated
    assert any("unassessed" in n for n in notes)
    # Fuselage still written; boom must not appear as BODY
    txt = (tmp_path / "assembly.avl").read_text()
    assert "BODY\nfuselage" in txt
    assert "BODY\nside_boom" not in txt
    npd = neutral_point(asm, source="avl_bodies")
    assert npd["bodies_avl_status"] == "unassessed"
    assert npd["x_np_status"] == "unassessed"
    assert "side_boom" in npd["rotated_bodies_omitted"]
    # Torenbeek path: SM assessed from axis-aligned parts only, but bodies status still unassessed
    np2 = neutral_point(asm, source="avl_torenbeek")
    assert np2["bodies_avl_status"] == "unassessed"
    assert "side_boom" not in np2["torenbeek_shifts_m"]
    print("AVL x_np_bodies", round(npd["x_np_avl_bodies"], 4), "torenbeek", round(np2["x_np_torenbeek"], 4),
          "omitted", npd["rotated_bodies_omitted"])


@needs_avl
def test_analyse_flags_unassessed_when_np_source_avl_bodies():
    spec = copy.deepcopy(DEMO)
    out = analyse(spec, spec["flight"])
    by = {c[0]: c for c in out.checks}
    assert "asm:avl_bodies" in by and by["asm:avl_bodies"][1] is None
    assert by["asm:static_margin"][1] is None
    assert "unassessed" in by["asm:static_margin"][2]
