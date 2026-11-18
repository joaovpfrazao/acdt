"""Exports of a component assembly (P1b): faceted STEP (CadQuery in a separate process, same pattern as
:mod:`..cad_export`) and the RCS input (merged PEC mesh for the Physical-Optics solver :mod:`acdt.core.em.po`,
plus its STL for ``acdt rcs``).

Nothing heavy here: the STEP is the drawing's own triangulation (no surface fit), and :func:`rcs_quick` is a
coarse single-cut monostatic sweep. Full polars / bistatic / two-bounce studies of the assembly are for the
Grok Build run on João's PC (docs/HANDOFF.md §4b).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from .assembly import Assembly

_STEP = Path(__file__).with_name("step_build.py")


def cadquery_available() -> bool:
    probe = subprocess.run([sys.executable, "-c", "import cadquery"], capture_output=True, text=True)
    return probe.returncode == 0


def export_step(asm: Assembly, path, fine: int = 1, include_discs: bool = True) -> dict:
    """Faceted STEP of every component (one part each). Returns {step, parts: {name: solid|shell}, notes}."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    comps = []
    for c in asm.components:
        if not include_discs and type(c).__name__ == "Disc":
            continue
        V, F = asm.mesh(c.name, fine)
        comps.append({"name": c.name, "V": np.asarray(V, float).tolist(), "F": np.asarray(F, int).tolist()})
    src = path.with_suffix(".meshes.json")
    src.write_text(json.dumps({"components": comps}), encoding="utf-8")
    out = {"step": None, "parts": {}, "meshes": str(src),
           "notes": ["STEP facetado (as mesmas facetas do STL/RCS, sem ajuste de superfícies)"]}
    if not cadquery_available():
        out["notes"].append("CadQuery não está instalado (pip install 'acdt[cad]'): o STEP não foi escrito.")
        return out
    from acdt.core.provenance import tool_used
    tool_used("python (cadquery)", sys.executable)
    run = subprocess.run([sys.executable, str(_STEP), str(src), str(path)], capture_output=True, text=True)
    if run.returncode != 0:
        raise RuntimeError(f"step_build falhou:\n{run.stderr[-2000:]}")
    out["step"] = str(path)
    out["parts"] = json.loads(run.stdout.strip().splitlines()[-1])
    return out


def _write_stl(m, path) -> None:
    lines = ["solid acdt_assembly_rcs"]
    for f in m.F:
        a, b, c = m.V[f]
        n = np.cross(b - a, c - a)
        n = n / (np.linalg.norm(n) or 1.0)
        lines += [f"facet normal {n[0]:.6e} {n[1]:.6e} {n[2]:.6e}", " outer loop"]
        lines += [f"  vertex {q[0]:.9e} {q[1]:.9e} {q[2]:.9e}" for q in (a, b, c)]
        lines += [" endloop", "endfacet"]
    lines.append("endsolid acdt_assembly_rcs")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def rcs_input(asm: Assembly, out_dir, fine: int = 1, exclude_roles=("propeller",),
             items=None) -> dict:
    """RCS mesh of the assembly (discs / propellers excluded, PRESSUPOSTO of :meth:`Assembly.to_rcs_mesh`) and
    its binary-free ASCII STL (readable by ``acdt rcs`` STL mode).

    When ``items`` is supplied, box/sphere/cylinder equipment is meshed in via
    :func:`acdt.domains.aircraft.assembly.rcs_bridge.build_rcs_mesh`; unplaced or unknown shapes are listed
    under ``inventory.unassessed`` (never silently dropped). Returns
    {mesh, stl, n_facets, inventory}.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    from .rcs_bridge import build_rcs_mesh, feature_inventory
    if items is not None:
        m, inv = build_rcs_mesh(asm, items=items, fine=fine, exclude_roles=exclude_roles)
    else:
        m = asm.to_rcs_mesh(fine, exclude_roles)
        inv = feature_inventory(asm, items=None, exclude_roles=exclude_roles)
    stl = out_dir / "assembly_rcs.stl"
    _write_stl(m, stl)
    return {"mesh": m, "stl": str(stl), "n_facets": int(m.n_facets), "inventory": inv,
            "frame": "x para trás, z para cima: nariz em −x (po.monostatic nose=(-1, 0, 0))"}


def rcs_quick(mesh, freq_hz: float = 10e9, az_deg=(-30.0, 0.0, 30.0), el_deg: float = 0.0, pol: str = "VV") -> dict:
    """Coarse monostatic PO check (single bounce, no occlusion) at a few azimuths: {az_deg, dBsm}."""
    from acdt.core.em import po
    az = np.asarray(az_deg, float)
    s = po.monostatic(mesh, freq_hz, az, el_deg, pol, nose=(-1, 0, 0), occlusion=False, bounces=1)
    return {"az_deg": az.tolist(), "dBsm": [float(v) for v in po.dbsm(np.asarray(s))], "freq_Hz": freq_hz,
            "pol": pol, "el_deg": el_deg, "method": "PO (Knott et al. 1993 Ch. 5), 1 reflexão, sem oclusão"}
