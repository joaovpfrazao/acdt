"""Phase 4: MSC/NX Nastran SOL 145 (p-k flutter) deck of the same wing-box FEM + DLM model, written with
pyNastran (BSD-3) and checked by reading it back. It is *not run here* (no Nastran on the box); it is the
input for an independent check with a Nastran licence, or with the open DLR Loads Kernel / pyNastran-based
toolchains.

Mapping from the CalculiX model (fem.py): S8R → CQUAD8 (same corner/mid-side node order), isotropic → PSHELL,
sandwich → PCOMP (face/core/face), each B32 beam → two CBAR with PBARL BAR (dims a × b, plane-1 vector +z,
offset along +z = OFFSET1·a), truss arms → CROD (stiff MAT1), nodal masses → CONM2, root clamp → SPC1 123456,
normal modes → EIGRL. Aero: one CAERO1 (right half-wing, same planform and panel counts as flutter.aero_grid),
AERO SYMXZ = +1 (symmetric) — the antisymmetric deck is the same with SYMXZ = −1; SPLINE1 (surface spline,
Harder & Desmarais 1972) to the four spar lines; MKAERO1 at the DLM Mach; FLUTTER PK with FLFACT density ratio
1 (velocities are then EAS, ρ_ref = 1.225). Units N, m, kg, s (PARAM WTMASS 1).

References: MSC Nastran Aeroelastic Analysis User's Guide (Rodden & Johnson 1994); Quick Reference Guide."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ..aero.interfaces import ToolNotAvailable
from . import tools


def write_sol145(res, mesh, masses: dict, extra: list, work, mach: float, velocities, sym: bool = True,
                 n_modes: int = 10, kr=None, nx: int = 8, ny: int = 20) -> dict:
    try:
        from pyNastran.bdf.bdf import BDF, CaseControlDeck
    except ImportError as ex:  # pragma: no cover
        raise ToolNotAvailable("pyNastran not installed") from ex
    from .flutter import KR

    kr = kr or KR
    m = mesh.meta["material"]
    b = BDF(debug=False)
    b.sol = 145
    G = lambda E, nu: E / (2 * (1 + nu))  # noqa: E731
    b.add_mat1(1, m["E"], G(m["E"], m["nu"]), m["nu"], rho=m["rho"])
    b.add_mat1(9, 2.1e14, G(2.1e14, 0.3), 0.3, rho=1e-6)
    if "E_cap" in m:
        cr = m["core"]
        nu_c = min(max(cr["E"] / (2 * cr["G"]) - 1, 0.0), 0.45)
        b.add_mat1(2, cr["E"], cr["G"], nu_c, rho=cr["rho"])
        b.add_mat1(3, m["E_cap"], G(m["E_cap"], 0.3), 0.3, rho=m["rho"])
    matid = {"MAT": 1, "FACE": 1, "CORE": 2, "CAP": 3, "STIFF": 9}
    X = mesh.nodes
    for i, p in enumerate(X):
        b.add_grid(i + 1, [float(v) for v in p])
    nid = len(X)
    for ex in extra:
        nid += 1
        ex["nid_nas"] = nid
        b.add_grid(nid, [ex["x"], ex["y"], ex["z"]])
    eid, pid = 0, 0
    for es, els in mesh.shells.items():
        p = mesh.shell_props[es]
        pid += 1
        if p.get("layers"):
            b.add_pcomp(pid, [matid[mt] for _, mt in p["layers"]], [t for t, _ in p["layers"]],
                        [0.0] * len(p["layers"]), comment=es)
        else:
            b.add_pshell(pid, mid1=1, t=p["t"], mid2=1, mid3=None, comment=es)
        for e in els:
            eid += 1
            b.add_cquad8(eid, pid, [n + 1 for n in e])
    for es, els in mesh.beams.items():
        p = mesh.beam_props[es]
        pid += 1
        b.add_pbarl(pid, matid[p["mat"]], "BAR", [p["a"], p["b"]], comment=es)
        off = [0.0, 0.0, float(p["offset1"] * p["a"])]
        for e in els:
            for ga, gb in ((e[0], e[2]), (e[2], e[1])):   # B32 order: end, end, middle
                eid += 1
                b.add_cbar(eid, pid, [ga + 1, gb + 1], [0.0, 0.0, 1.0], None, offt="GGG", wa=off, wb=off)
    if extra:
        pid += 1
        b.add_prod(pid, 9, 1e-3, comment="ARMS")
        for ex in extra:
            for a in ex["anchors"]:
                eid += 1
                b.add_crod(eid, pid, [a + 1, ex["nid_nas"]])
    for n, mv in masses.items():
        eid += 1
        b.add_conm2(eid, n + 1, float(mv))
    for ex in extra:
        eid += 1
        b.add_conm2(eid, ex["nid_nas"], float(ex["mass"]))
    b.add_spc1(1, "123456", [n + 1 for n in mesh.root])
    b.add_eigrl(10, nd=n_modes, norm="MASS")
    # aero
    w = res.config.wing
    s = w.span / 2
    y0 = mesh.meta["y0"]
    cref = w.mac
    b.add_aero(velocity=1.0, cref=cref, rho_ref=1.225, acsid=0, sym_xz=1 if sym else -1)
    b.add_paero1(1000)
    tanL = math.tan(w.sweep_at(0.0))
    b.add_caero1(10001, 1000, 1, [0.0, 0.0, 0.0], w.c_root, [s * tanL, s, 0.0], w.c_tip,
                 nspan=ny, nchord=nx, comment="right half-wing (DLM)")
    sg = sorted({n + 1 for k in ("f_up", "f_lo", "r_up", "r_lo") for n in mesh.spar_lines[k]})
    b.add_set1(100, sg)
    # boxes inboard of the FEM root stay attached (surface spline extrapolates; Phase 3 treats it rigid)
    b.add_spline1(200, 10001, 10001, 10001 + nx * ny - 1, 100)
    b.add_mkaero1([float(mach)], [float(k) for k in kr])
    b.add_flfact(1, [1.0])
    b.add_flfact(2, [float(mach)])
    b.add_flfact(3, [float(v) for v in velocities])
    b.add_flutter(30, "PK", 1, 2, 3, imethod="L", nvalue=n_modes)
    b.add_param("WTMASS", 1.0)
    b.add_param("LMODES", n_modes)
    b.add_param("OPPHIPA", 1)
    b.case_control_deck = CaseControlDeck([
        "TITLE = acdt Phase 4 wing box SOL 145 " + ("symmetric" if sym else "antisymmetric"),
        "ECHO = NONE", "SPC = 1", "METHOD = 10", "FMETHOD = 30", "DISP = ALL"])
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    path = work / f"wing_sol145_{'sym' if sym else 'anti'}.bdf"
    b.write_bdf(str(path), size=16, is_double=False)
    # validation: read back
    chk = BDF(debug=False)
    chk.read_bdf(str(path), xref=True)
    return {"bdf": tools.case_relative(path, Path(work).resolve().parent),
            "grids": len(chk.nodes), "elements": len(chk.elements), "masses": len(chk.masses),
            "caero_boxes": nx * ny, "sym_xz": 1 if sym else -1, "xref_ok": True,
            "run": f"nastran {path.name}   # MSC or Simcenter (NX) Nastran with the aeroelastic option"}
