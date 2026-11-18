"""Faceted STEP of a component assembly. Separate process: imports CadQuery (OpenCASCADE via ``cadquery-ocp``,
LGPL), never imported by acdt. Arguments: ``python step_build.py meshes.json out.step``.

``meshes.json`` = {"components": [{"name", "V": [[x, y, z], ...], "F": [[i, j, k], ...]}]}. Each component's
triangles become planar faces sewn into a shell (BRepBuilderAPI_Sewing through ``cq.Shell.makeShell``); a
closed shell becomes a solid. The result is the same faceted geometry as the STL / RCS mesh (no surface
fitting), one STEP part per component.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cadquery as cq


def _shape(V, F):
    faces = []
    for f in F:
        pts = [cq.Vector(*V[i]) for i in f]
        if (pts[1] - pts[0]).cross(pts[2] - pts[0]).Length < 1e-14:
            continue                                   # degenerate triangle (pole of a body of revolution)
        faces.append(cq.Face.makeFromWires(cq.Wire.makePolygon(pts, close=True)))
    shell = cq.Shell.makeShell(faces)
    try:
        solid = cq.Solid.makeSolid(shell)
        if solid.isValid() and solid.Volume() > 0:
            return solid, "solid"
    except Exception:
        pass
    return shell, "shell"


def main(argv: list[str]) -> int:
    spec = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    out = Path(argv[2])
    asm = cq.Assembly(name="acdt_assembly")
    kinds = {}
    for c in spec["components"]:
        try:
            shp, kind = _shape(c["V"], c["F"])
        except Exception as ex:
            print(f"FAIL {c['name']}: {ex}", file=sys.stderr)
            return 1
        asm.add(shp, name=c["name"].replace("~", "_"))
        kinds[c["name"]] = kind
    asm.save(str(out), "STEP")
    print(json.dumps(kinds))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
