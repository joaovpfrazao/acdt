"""Build the structure assembly from a JSON spec. Separate process: imports CadQuery.

CadQuery pulls in OpenCASCADE through ``cadquery-ocp`` (LGPL). This script is the only place that
import happens. It does not import acdt. Arguments: ``python cad_build.py spec.json out_dir``.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import cadquery as cq


def _gap(a, b) -> float:
    pa, pb = a.toTuple(), b.toTuple()
    return math.dist(pa, pb)


def _wire(pts):
    vs = [cq.Vector(*p) for p in pts]
    if _gap(vs[0], vs[-1]) > 1e-9:
        vs.append(vs[0])
    edges = []
    for a, b in zip(vs, vs[1:]):
        if _gap(a, b) < 1e-8:
            continue
        edges.append(cq.Edge.makeLine(a, b))
    return cq.Wire.assembleEdges(edges)


def _solid(part):
    kind = part["kind"]
    if kind == "loft":
        return cq.Solid.makeLoft([_wire(s) for s in part["sections"]], ruled=True)
    if kind == "ring":
        radius, depth, width, x = part["R"], part["t_radial"], part["width"], part["x"]
        inner = max(radius - depth, 1e-4)
        return (cq.Workplane("YZ").circle(radius).circle(inner).extrude(width)
                .translate((x - width / 2.0, 0, 0)).val())
    if kind == "rod":
        side = part["side"]
        return (cq.Workplane("YZ").center(part["y"], part["z"]).rect(side, side)
                .extrude(part["x1"] - part["x0"]).translate((part["x0"], 0, 0)).val())
    raise ValueError(f"unknown part kind {kind!r}")


def main(argv: list[str]) -> int:
    spec = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    out = Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    assembly = cq.Assembly(name="acdt_structure")
    for part in spec["parts"]:
        try:
            assembly.add(_solid(part), name=part["name"])
        except Exception as ex:
            print(f"FAIL {part['name']}: {ex}", file=sys.stderr)
            return 1
    oml = spec.get("oml_step")
    if oml:
        assembly.add(cq.importers.importStep(oml), name="oml_openvsp")
    step = out / "structure.step"
    assembly.save(str(step))
    manifest = {"step": step.name, "parts": [p["name"] for p in spec["parts"]],
                "oml_openvsp": bool(oml)}
    (out / "cad_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
