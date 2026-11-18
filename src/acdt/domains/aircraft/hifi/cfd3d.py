"""Phase 4: 3-D CFD of the wing (coarse Euler, run here) and the full-aircraft RANS case (set up only — needs
a stronger machine).

* Wing, half model: OpenVSP wing STEP (metres) → Gmsh OCC: right half-wing volume subtracted from a box
  farfield with a symmetry plane at y = 0; tetrahedral mesh sized on the chord; SU2 compressible Euler (JST),
  two angles of attack → CLα and the CL offset vs the L1 AVL vortex lattice (both inviscid: like-for-like;
  AVL wing-alone CL from its wing strips Σ c_l ΔS / S).
* Full aircraft RANS-SA: the same pipeline on the whole-aircraft STEP needs a prism boundary layer at
  y+ ≈ 1 → O(5–15 M) cells. A case directory (Gmsh .geo + SU2 .cfg + README with the estimate and the
  commands) is written; it is not meshed or run on this box (tools.Budget).

Euler/RANS: SU2 (Economon et al., AIAA J 54(3) 2016). Mesh: Gmsh (Geuzaine & Remacle 2009)."""
from __future__ import annotations

import json
import math
import os
import subprocess
import time
from pathlib import Path

import numpy as np

from ..aero.interfaces import ToolNotAvailable
from . import tools
from .cfd import SU2_REF, _last_history


def wing_half_mesh(step: str | Path, path: str | Path, mac: float, semispan: float, h_wing: float | None = None,
                   farfield_c: float = 20.0) -> dict:
    """Half-wing Euler mesh. The .geo is written by acdt and meshed by the separate gmsh executable (OCC kernel):
    keep the y ≥ 0 surfaces of the wing STEP, sew them into a volume, subtract it from a box farfield
    (symmetry at y = 0), classify the fluid boundary into wing / symmetry / farfield, distance+box size fields."""
    g = lambda v: repr(float(v))  # noqa: E731
    R = farfield_c * mac
    h = h_wing or mac / 40
    step_abs = Path(step).resolve()
    geo_dir = Path(path).resolve().parent
    try:
        step_geo = Path(os.path.relpath(step_abs, geo_dir)).as_posix()
    except ValueError:
        step_geo = step_abs.as_posix()
    geo = f"""// acdt Phase 4 — half-wing Euler mesh (written by acdt, meshed by the gmsh executable)
SetFactory("OpenCASCADE");
Geometry.OCCTargetUnit = "M";
imp() = ShapeFromFile("{step_geo}");
all() = Surface{{:}};
// y >= 0 faces; a face whose bounding box repeats an accepted one (the root cap is exported once per
// half-wing by OpenVSP) is dropped, otherwise the sewn shell self-intersects and the boolean fails
right() = {{}}; left() = {{}}; rb() = {{}};
For i In {{0 : #all() - 1}}
  bs() = BoundingBox Surface{{all(i)}};
  dup = 0;
  For j In {{0 : #right() - 1}}
    d = 0;
    For k In {{0 : 5}}
      d = d + Fabs(bs(k) - rb(6 * j + k));
    EndFor
    If (d < 1e-6)
      dup = 1;
    EndIf
  EndFor
  If (bs(1) > -1e-5 && dup == 0)
    right() += all(i);
    rb() += bs();
  Else
    left() += all(i);
  EndIf
EndFor
If (#left() > 0)
  Recursive Delete{{ Surface{{left()}}; }}
EndIf
sl = newsl;
Surface Loop(sl) = {{right()}} Using Sewing;
wing = newv;
Volume(wing) = {{sl}};
R = {g(R)};
semispan = {g(semispan)};
bw() = BoundingBox Volume{{wing}};
xmin = bw(0); zmin = bw(2); xmax = bw(3); zmax = bw(5);
box = newv;
Box(box) = {{xmin - R, 0.0, zmin - R, (xmax - xmin) + 2 * R, semispan + R, (zmax - zmin) + 2 * R}};
fluid() = BooleanDifference{{ Volume{{box}}; Delete; }}{{ Volume{{wing}}; Delete; }};
vol = fluid(0);
faces() = Boundary{{ Volume{{vol}}; }};
wall() = {{}}; sym() = {{}}; far() = {{}};
For i In {{0 : #faces() - 1}}
  t = Fabs(faces(i));
  b() = BoundingBox Surface{{t}};
  If (Fabs(b(1)) < 1e-6 && Fabs(b(4)) < 1e-6)
    sym() += t;
  Else
    If (b(0) < xmin - 0.5 * R || b(3) > xmax + 0.5 * R || b(2) < zmin - 0.5 * R || b(5) > zmax + 0.5 * R || b(4) > semispan + 0.5 * R)
      far() += t;
    Else
      wall() += t;
    EndIf
  EndIf
EndFor
Printf("ACDT_MARKERS %g %g %g", #wall(), #sym(), #far());
Field[1] = Distance;
Field[1].SurfacesList = {{wall()}};
Field[1].Sampling = 60;
Field[2] = Threshold;
Field[2].InField = 1;
Field[2].SizeMin = {g(h)};
Field[2].SizeMax = R / 4;
Field[2].DistMin = {g(0.02 * mac)};
Field[2].DistMax = R;
Field[3] = Box;
Field[3].VIn = {g(2 * h)};
Field[3].VOut = R;
Field[3].XMin = xmin - {g(0.3 * mac)};
Field[3].XMax = xmax + {g(2 * mac)};
Field[3].YMin = 0;
Field[3].YMax = {g(semispan * 1.2)};
Field[3].ZMin = zmin - {g(0.5 * mac)};
Field[3].ZMax = zmax + {g(0.5 * mac)};
Field[3].Thickness = {g(2 * mac)};
Field[4] = Min;
Field[4].FieldsList = {{2, 3}};
Background Field = 4;
Mesh.MeshSizeExtendFromBoundary = 0;
Mesh.MeshSizeFromPoints = 0;
Mesh.MeshSizeFromCurvature = 0;
Mesh.Algorithm = 6;
Mesh.MeshSizeMin = {g(h / 4)};
Mesh.Algorithm3D = 1; // Delaunay
Physical Surface("wing") = {{wall()}};
Physical Surface("symmetry") = {{sym()}};
Physical Surface("farfield") = {{far()}};
Physical Volume("fluid") = {{vol}};
"""
    path = Path(path)
    tools.run_gmsh(geo, path.parent, path.stem + ".geo", path, dim=3)
    n_tet = tools.su2_nelem(path)
    import re
    log = (path.parent / (path.stem + "_gmsh.log")).read_text(errors="replace")
    mk = re.search(r"ACDT_MARKERS (\d+) (\d+) (\d+)", log)
    wall, sym, far = (range(int(mk.group(i))) for i in (1, 2, 3)) if mk else ([], [], [])
    # The .su2 sits in a step folder; the case folder is its parent. A direct call whose ``path`` is not
    # under a case still stores a relative path (the temp directory name), never an absolute one.
    return {"mesh": tools.case_relative(path, Path(path).resolve().parent.parent),
            "cells": int(n_tet), "h_wing": h, "farfield_c": farfield_c,
            "markers": {"wing": len(wall), "symmetry": len(sym), "farfield": len(far)}}


# PRESSUPOSTO, not a physical model: how close a subsonic Euler CD must lie to the induced drag
# before it is accepted. d'Alembert (profile drag ~ 0) plus Raymer Eq. 12.5 with CD0 = 0.
EULER_DRAG_TOL = 0.50


def wind_axis_coefficients(cfx: float, cfz: float, alpha_deg: float) -> tuple[float, float]:
    """Lift and drag from the body-axis force coefficients.

    SU2 (x aft, z up) reports the wind axes as CD = CFx cos α + CFz sin α and
    CL = −CFx sin α + CFz cos α. Checked on the C172 wing history: the CD column
    matches this to 1e-6, including the negative values. ``REF_ORIGIN`` does not
    enter the force. A negative CD is the pressure integral, not a swapped axis.
    """
    a = math.radians(alpha_deg)
    cd = cfx * math.cos(a) + cfz * math.sin(a)
    cl = -cfx * math.sin(a) + cfz * math.cos(a)
    return cl, cd


def induced_drag_coefficient(cl: float, aspect_ratio: float, e: float) -> float:
    """CL² / (π e AR). Raymer Eq. 12.5 with CD0 = 0 (inviscid profile drag, d'Alembert)."""
    return cl * cl / (math.pi * e * aspect_ratio)


def euler_drag_check(cl: float, cd: float, aspect_ratio: float, e: float,
                     tol: float = EULER_DRAG_TOL) -> dict:
    """Subsonic Euler drag must be ≥ 0 and within ``tol`` of the induced drag. Otherwise it is not usable."""
    cdi = induced_drag_coefficient(cl, aspect_ratio, e)
    if not (math.isfinite(cl) and math.isfinite(cd) and math.isfinite(cdi)):
        ok, reason = False, "non-finite coefficient"
    elif cd < 0.0:
        ok, reason = False, "subsonic Euler drag is negative"
    elif cdi <= 0.0:
        ok, reason = False, "no positive induced-drag target"
    else:
        err = abs(cd - cdi) / cdi
        ok = err <= tol
        reason = "" if ok else f"|CD-CDi|/CDi = {err:.2f} > {tol:g}"
    return {"CL": cl, "CD": cd, "CDi": cdi, "e": e, "AR": aspect_ratio, "ok": ok, "reason": reason}


def su2_euler_cfg(mesh: str, alpha: float, mach: float, S_half: float, mac: float, x_ref: float,
                  iters: int = 1500, restart: bool = False) -> str:
    return f"""% acdt Phase 4 — wing half model, compressible Euler
SOLVER= EULER
MATH_PROBLEM= DIRECT
RESTART_SOL= {'YES' if restart else 'NO'}
MACH_NUMBER= {mach:.4f}
AOA= {alpha:.3f}
SIDESLIP_ANGLE= 0.0
FREESTREAM_PRESSURE= 101325.0
FREESTREAM_TEMPERATURE= 288.15
REF_ORIGIN_MOMENT_X= {x_ref:.5f}
REF_ORIGIN_MOMENT_Y= 0.0
REF_ORIGIN_MOMENT_Z= 0.0
REF_LENGTH= {mac:.5f}
REF_AREA= {S_half:.5f}
MARKER_EULER= ( wing )
MARKER_SYM= ( symmetry )
MARKER_FAR= ( farfield )
MARKER_PLOTTING= ( wing )
MARKER_MONITORING= ( wing )
NUM_METHOD_GRAD= GREEN_GAUSS
CFL_NUMBER= 5.0
CFL_ADAPT= YES
CFL_ADAPT_PARAM= ( 0.5, 1.2, 5.0, 100.0 )
CONV_NUM_METHOD_FLOW= JST
JST_SENSOR_COEFF= ( 0.5, 0.02 )
TIME_DISCRE_FLOW= EULER_IMPLICIT
LINEAR_SOLVER= FGMRES
LINEAR_SOLVER_PREC= ILU
LINEAR_SOLVER_ERROR= 1E-6
LINEAR_SOLVER_ITER= 10
ITER= {iters}
CONV_FIELD= RMS_DENSITY
CONV_RESIDUAL_MINVAL= -9
SCREEN_OUTPUT= (INNER_ITER, RMS_DENSITY, LIFT, DRAG, MOMENT_Y)
HISTORY_OUTPUT= (ITER, RMS_RES, AERO_COEFF)
MESH_FILENAME= {mesh}
MESH_FORMAT= SU2
SOLUTION_FILENAME= restart_flow.dat
RESTART_FILENAME= restart_flow.dat
OUTPUT_FILES= (RESTART, SURFACE_CSV)
"""


def estimate_euler(cells: int, n_alpha: int, iters: int, max_time_min: float = 45.0) -> tools.Budget:
    # measured on this box class: ~1.0 kB/cell (Euler, 3-D tets, implicit), ~ 2.5 µs/cell/iter on 8 cores.
    # max_time_min is the authorized wall-clock cap (default 45). It does not relax the RAM check.
    return tools.budget(cells * 1.0e-6 + 0.6, cells * iters * n_alpha * 2.5e-6 / 60, max_time_min=max_time_min)


def avl_wing_alone(res, alphas=(0.0, 4.0)) -> dict:
    """AVL CL of the wing alone (Σ c_l ΔS of the wing strips / S) at two α; same α datum as the VSP model."""
    from ..aero.avl import run_avl_case
    out = []
    w = res.config.wing
    mach = res.cruise_speed / 340.29
    for a in alphas:
        r = run_avl_case(res.config, alpha_deg=a, mach=mach)
        out.append(sum(s["cl"] * s["area"] for s in r.strips) / w.S)
    return {"alpha": list(alphas), "CL_wing": out,
            "CLa": (out[1] - out[0]) / math.radians(alphas[1] - alphas[0]), "mach": mach}


def run_wing_euler(res, step, work, alphas=(0.0, 4.0), iters: int = 1500, nproc: int | None = None,
                   h_factor: float = 1.0, force: bool = False, max_time_min: float = 45.0) -> dict:
    su2 = tools.find_exe("SU2_CFD")
    if su2 is None:
        raise ToolNotAvailable("SU2_CFD not found")
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    w = res.config.wing
    m = wing_half_mesh(step, work / "wing_half.su2", w.mac, w.span / 2, h_wing=w.mac / 40 / h_factor)
    b = estimate_euler(m["cells"], len(alphas), iters, max_time_min=max_time_min)
    out = {"mesh": m, "budget": b.__dict__, "ref": SU2_REF + "; Euler JST", "alpha": [], "CL": [], "CD": [],
           "CMy": [], "res": [], "notes": []}
    if not b.run_here and not force:
        out["notes"].append(f"não corrido: {b.reason}")
        return out
    mach = max(res.cruise_speed / 340.29, 0.15)
    lam = w.c_tip / w.c_root
    y_mac = w.span / 6 * (1 + 2 * lam) / (1 + lam)
    x_ref = y_mac * math.tan(w.sweep_at(0.0)) + 0.25 * w.mac      # c/4 of the MAC (wing apex at x = 0)
    nproc = nproc or min(8, tools.cores())
    t0 = time.time()
    # The old 780 s cap killed an angle the budget had already accepted. Stop at the authorized wall clock.
    for k, a in enumerate(alphas):
        remaining = max_time_min * 60.0 - (time.time() - t0)
        if remaining < 30.0:
            out["notes"].append(f"α={a}: sem tempo restante no limite de {max_time_min:.0f} min")
            break
        cfg = work / f"e{a:+05.1f}.cfg"
        cfg.write_text(su2_euler_cfg("wing_half.su2", a, mach, w.S / 2, w.mac, x_ref, iters, restart=k > 0))
        try:
            rc = tools.run(tools.mpi_prefix(nproc) + [su2, cfg.name], work, f"e{a:+05.1f}.log", timeout=remaining)
        except subprocess.TimeoutExpired:
            out["notes"].append(f"α={a}: SU2 interrompido ao fim do limite de {max_time_min:.0f} min")
            break
        h = work / "history.csv"
        if rc != 0 or not h.exists():
            out["notes"].append(f"α={a}: SU2 falhou (rc {rc})")
            continue
        d = _last_history(h)
        h.rename(work / f"history_e{a:+05.1f}.csv")
        cl, cd = d.get("CL"), d.get("CD")
        if cl is not None and cd is not None and "CFx" in d and "CFz" in d:
            cl_w, cd_w = wind_axis_coefficients(float(d["CFx"]), float(d["CFz"]), a)
            if abs(cl_w - float(cl)) > 1e-4 or abs(cd_w - float(cd)) > 1e-4:
                out["notes"].append(f"α={a}: CL/CD do histórico não coincidem com o eixo de vento")
        out["alpha"].append(a)
        out["CL"].append(cl)
        out["CD"].append(cd)
        out["CMy"].append(d.get("CMy"))
        out["res"].append(d.get("rms[Rho]"))
    out["wall_s"] = time.time() - t0
    out["mach"] = mach
    from ..aero.drag import oswald_raymer
    aa = res.spec.assumptions.get("aero") or {}
    e = aa.get("oswald") or oswald_raymer(w.AR, w.sweep_at(0.0))
    out["AR"] = w.AR
    out["e_oswald"] = e
    out["drag_check"] = []
    for a_i, cl_i, cd_i in zip(out["alpha"], out["CL"], out["CD"]):
        if cl_i is None or cd_i is None:
            continue
        chk = euler_drag_check(float(cl_i), float(cd_i), w.AR, e)
        chk["alpha"] = a_i
        out["drag_check"].append(chk)
    if out["drag_check"] and not all(c["ok"] for c in out["drag_check"]):
        out["notes"].append(
            "CD de Euler rejeitado: num escoamento subsónico devia ser ≥ 0 e próximo de CL²/(π e AR) "
            "(Raymer Eq. 12.5 com CD0 = 0). O número gravado é o CD de eixo de vento do SU2; não se troca o sinal.")
    if len(out["CL"]) >= 2:
        out["CLa_euler"] = (out["CL"][-1] - out["CL"][0]) / math.radians(out["alpha"][-1] - out["alpha"][0])
        try:
            av = avl_wing_alone(res, tuple(out["alpha"][:2]))
            out["avl"] = av
            out["k_CLa"] = out["CLa_euler"] / av["CLa"]
            out["dCL_at_alpha0"] = out["CL"][0] - av["CL_wing"][0]
        except Exception as ex:  # pragma: no cover
            out["notes"].append(f"AVL: {ex}")
    (work / "wing_euler.json").write_text(json.dumps(out, indent=1, default=float))
    return out


def rans_volume_estimate(swet_full_m2: float, mac_m: float, first_cell_m: float, *,
                         n_alpha: int = 3, iters: int = 8000, n_cores: int = 8) -> dict:
    """Cell, RAM and time estimate used by :func:`full_aircraft_rans_case`.

    ``swet_full_m2`` is the sum of both sides. The half model uses half of that area.
    Surface spacing is mac/100. The prism count grows at 1.2 until about 0.01 chords.
    RAM is 1.8 kB/cell. Time is 4 µs/cell/iteration/core, 8000 iterations and three
    angles on 8 cores, unless the caller overrides those three counts. This is the
    formula already in this module. It is not a measured mesh.
    """
    swet_half = float(swet_full_m2) / 2.0
    h_s = float(mac_m) / 100.0
    n_surf = swet_half / h_s**2 * 2.0
    n_layers = int(math.ceil(math.log(1 + 0.05 * float(mac_m) * 0.2 / float(first_cell_m)) / math.log(1.2)))
    cells = n_surf * n_layers + 6.0 * n_surf
    return {
        "swet_full_m2": float(swet_full_m2),
        "swet_half_m2": swet_half,
        "surface_spacing_m": h_s,
        "n_surface_tri": int(n_surf),
        "prism_layers": n_layers,
        "cells_estimate": int(cells),
        "ram_GB": cells * 1.8e-6,
        "wall_h": cells * iters * n_alpha * 4e-6 / 3600.0 / n_cores,
        "iters": iters,
        "n_alpha": n_alpha,
        "n_cores": n_cores,
        "rate_s_per_cell_iter_per_core": 4e-6,
        "kB_per_cell": 1.8,
    }


def full_aircraft_rans_case(res, step, work, yplus: float = 1.0, nproc_target: int = 64) -> dict:
    """Write the full-aircraft RANS-SA case (half model) for a stronger machine; estimates cells/RAM/time."""
    from .cfd import first_cell
    from ....core.atmosphere import isa

    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    w = res.config.wing
    at = isa(res.cruise_altitude)
    Re = at.rho * res.cruise_speed * w.mac / at.mu
    h1 = first_cell(Re, w.mac, yplus)
    est_n = rans_volume_estimate(sum(res.config.wetted_areas().values()), w.mac, h1)
    h_s = est_n["surface_spacing_m"]
    n_layers = est_n["prism_layers"]
    mem = est_n["ram_GB"]
    hours = est_n["wall_h"]
    geo = f"""// acdt Phase 4 — full aircraft half model, RANS-SA (Gmsh {''}4.x). First cell {h1:.2e} m (y+ {yplus:g}).
SetFactory("OpenCASCADE");
Geometry.OCCTargetUnit = "M";
v() = ShapeFromFile("{Path(step).name}");
// keep y >= 0, build fluid = box − aircraft, symmetry at y = 0 (see wing_half_mesh in cfd3d.py)
Mesh.MeshSizeMin = {h_s / 4:.4g};
Mesh.MeshSizeMax = {20 * w.mac:.4g};
Mesh.Algorithm3D = 10;
// prism layer: Field[1] = BoundaryLayer (Gmsh ≥ 4.11 supports 3-D BL via Extrude Boundary Layer) —
// {n_layers} layers, first {h1:.2e} m, ratio 1.2
"""
    (work / "aircraft_rans.geo").write_text(geo)
    cfg = su2_euler_cfg("aircraft_half.su2", 2.0, res.cruise_speed / at.a, w.S / 2, w.mac, 0.25 * w.mac, 8000)
    cfg = cfg.replace("SOLVER= EULER", "SOLVER= RANS\nKIND_TURB_MODEL= SA") \
             .replace("MARKER_EULER= ( wing )", "MARKER_HEATFLUX= ( aircraft, 0.0 )") \
             .replace("MARKER_PLOTTING= ( wing )", "MARKER_PLOTTING= ( aircraft )") \
             .replace("MARKER_MONITORING= ( wing )", "MARKER_MONITORING= ( aircraft )") \
             .replace("CONV_NUM_METHOD_FLOW= JST", "CONV_NUM_METHOD_FLOW= ROE\nMUSCL_FLOW= YES\nSLOPE_LIMITER_FLOW= VENKATAKRISHNAN"
                      "\nCONV_NUM_METHOD_TURB= SCALAR_UPWIND\nMUSCL_TURB= NO") \
             .replace("NUM_METHOD_GRAD= GREEN_GAUSS", "NUM_METHOD_GRAD= WEIGHTED_LEAST_SQUARES") \
             .replace("FREESTREAM_PRESSURE= 101325.0\nFREESTREAM_TEMPERATURE= 288.15",
                      f"REYNOLDS_NUMBER= {Re:.4e}\nREYNOLDS_LENGTH= {w.mac:.5f}\nFREESTREAM_TEMPERATURE= {at.T:.2f}")
    (work / "aircraft_rans.cfg").write_text(cfg)
    est = {"Re_mac": Re, "first_cell_m": h1, "surface_spacing_m": h_s,
           "n_surface_tri": est_n["n_surface_tri"],
           "prism_layers": n_layers, "cells_estimate": est_n["cells_estimate"], "ram_GB": mem,
           "wall_h_8cores_3alpha": hours, "wall_h_64cores_3alpha": hours * est_n["n_cores"] / nproc_target,
           "commands": [f"cd {tools.case_relative(work, work.resolve().parent)}",
                        "gmsh aircraft_rans.geo -3 -format su2 -o aircraft_half.su2",
                        f"mpirun -n <N> SU2_CFD aircraft_rans.cfg   # AOA in the cfg; repeat for α = 0, 2, 4 (+ stall sweep)"]}
    (work / "README.md").write_text(
        "# Caso RANS-SA da aeronave completa (meia aeronave) — máquina mais forte\n\n"
        + "\n".join(f"* {k}: {v}" for k, v in est.items() if k != "commands")
        + "\n\n```\n" + "\n".join(est["commands"]) + "\n```\n\nO .geo indica a construção (como `cfd3d.wing_half_mesh`);"
        " a camada de prismas 3-D tem de ser verificada (qualidade, y+) antes de correr.\n")
    (work / "estimate.json").write_text(json.dumps(est, indent=1, default=float))
    return est
