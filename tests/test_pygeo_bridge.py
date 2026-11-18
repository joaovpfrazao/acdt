# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""The loft FFD is written here. pyGeo itself is not imported."""
import ast
from pathlib import Path

import numpy as np
import pytest

from acdt.domains.aircraft.hifi import pygeo_bridge as pb
from acdt.domains.aircraft.hifi.wing_bl import build_patches, scaled_wing


def _patches():
    surf, _ref = scaled_wing()
    return build_patches(surf, n_chord=9, n_span=5, n_tip=5)


def test_ffd_box_contains_the_loft():
    pts = pb.surface_points(_patches())
    grid = pb.ffd_lattice(pts)
    inside = pb.points_inside(pts, grid)
    assert inside["all_inside"] and inside["n_inside"] == inside["n_points"]
    assert grid.shape == (*pb.FFD_SHAPE, 3)
    lo = np.array([grid[..., d].min() for d in range(3)])
    hi = np.array([grid[..., d].max() for d in range(3)])
    assert np.all(pts.min(axis=0) > lo) and np.all(pts.max(axis=0) < hi)


def test_case_script_imports_pygeo_and_not_acdt(tmp_path):
    record = pb.write_case(tmp_path, _patches())
    assert record["n_points"] > 10
    assert record["adflow"] == "nao_avaliado" and record["tacs"] == "nao_avaliado"
    script = (tmp_path / "pygeo_ffd.py").read_text(encoding="utf-8")
    tree = ast.parse(script)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
    assert set(imports) == {"json", "numpy", "pygeo"}
    assert "import acdt" not in script and "import adflow" not in script and "import tacs" not in script
    assert (tmp_path / "surface.xyz").exists() and (tmp_path / "ffd.xyz").exists()
    shell = pb.container_shell()
    assert "pygeo_ffd.py" in shell and "mpirun" in shell and "-np 1" in shell


def test_acdt_does_not_import_pygeo_adflow_or_tacs():
    src = Path(__file__).resolve().parents[1] / "src"
    banned = ("pygeo", "adflow", "tacs", "pyhyp", "idwarp")
    for f in src.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, (ast.Import, ast.ImportFrom)) else []
            mod = getattr(node, "module", None) or ""
            for name in banned:
                assert name not in names and not mod.startswith(name), f"{f} imports {name}"


def test_volume_roundtrip_is_fortran_order(tmp_path):
    grid = pb.ffd_lattice(np.array([[0.0, 0.0, 0.0], [1.0, 2.0, 0.2]]))
    path = tmp_path / "ffd.xyz"
    pb.write_plot3d_volume(grid, path)
    lines = path.read_text(encoding="ascii").splitlines()
    assert lines[0] == "1"
    assert lines[1] == "6 8 4"
    # First x value is the low corner. i is fastest, so the second x is the next i, same j and k.
    xs = [float(v) for v in lines[2:2 + 6 * 8 * 4]]
    assert xs[0] == pytest.approx(grid[0, 0, 0, 0])
    assert xs[1] == pytest.approx(grid[1, 0, 0, 0])
