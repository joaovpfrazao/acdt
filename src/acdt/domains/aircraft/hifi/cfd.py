"""Phase 4 CFD: Gmsh meshes and SU2 cases that verify the L1/L2 aerodynamics.

1. **2-D RANS of the wing section** (SU2 incompressible RANS, Spalart–Allmaras, fully turbulent) on a Gmsh hybrid
   mesh (quad boundary layer, first cell for y+ ≈ 1, far field at 100 c) at the cruise and stall Reynolds
   numbers used by L1 → section clmax, cd at the cruise cl, cm0, checked against the XFOIL polars of L1.
2. **Coarse 3-D Euler of the wing** (SU2 compressible Euler, half span with a symmetry plane) on a Gmsh tetra mesh
   built from the OpenVSP wing STEP → CLα, Cm_α, induced-drag factor, checked against AVL (VLM).
3. **Full-aircraft 3-D RANS**: case files written (mesh script + cfg), run only if the compute guard allows.

Airfoil coordinates: NACA 4- and 5-digit (standard, non-reflexed) analytic definitions, Abbott & von Doenhoff,
*Theory of Wing Sections* (1959) §6.4–6.6, closed trailing edge (a4 = −0.1036). SU2: Economon et al., AIAA J 54(3)
2016; SA model: Spalart & Allmaras, AIAA 92-0439; Gmsh: Geuzaine & Remacle, IJNME 79(11) 2009."""
from __future__ import annotations

import csv
import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ..aero.interfaces import ToolNotAvailable, _naca_digits
from . import tools

SU2_REF = "SU2 v8 (Economon et al., AIAA J 54(3), 2016), SA (Spalart & Allmaras, AIAA 92-0439)"

# 5-digit mean lines (non-reflexed, design cl 0.3): P → (m, k1), Abbott & von Doenhoff Table / §6.6
_FIVE = {1: (0.0580, 361.400), 2: (0.1260, 51.640), 3: (0.2025, 15.957), 4: (0.2900, 6.643), 5: (0.3910, 3.230)}


def naca_coords(airfoil: str, n: int = 121) -> np.ndarray:
    """Closed-TE NACA 4/5-digit coordinates, from TE over the upper surface to LE and back (Selig order)."""
    d = _naca_digits(airfoil)
    if d is None:
        raise ValueError(f"only NACA 4/5-digit airfoils supported, got {airfoil!r}")
    beta = np.linspace(0, math.pi, n)
    x = 0.5 * (1 - np.cos(beta))
    t = int(d[-2:]) / 100
    yt = 5 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4)
    if len(d) == 4:
        m, p = int(d[0]) / 100, int(d[1]) / 10
        yc = np.zeros_like(x)
        dy = np.zeros_like(x)
        if m > 0:
            f = x < p
            yc[f] = m / p**2 * (2 * p * x[f] - x[f] ** 2)
            dy[f] = 2 * m / p**2 * (p - x[f])
            yc[~f] = m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x[~f] - x[~f] ** 2)
            dy[~f] = 2 * m / (1 - p) ** 2 * (p - x[~f])
    else:
        L, P, Q = int(d[0]), int(d[1]), int(d[2])
        if Q != 0 or P not in _FIVE:
            raise ValueError(f"reflexed / unknown 5-digit mean line in {airfoil!r}")
        m, k1 = _FIVE[P]
        k1 *= (0.15 * L) / 0.3  # design cl = 0.15 L, the tabulated k1 is for cl = 0.3
        f = x < m
        yc = np.where(f, k1 / 6 * (x**3 - 3 * m * x**2 + m**2 * (3 - m) * x), k1 * m**3 / 6 * (1 - x))
        dy = np.where(f, k1 / 6 * (3 * x**2 - 6 * m * x + m**2 * (3 - m)), -k1 * m**3 / 6)
    th = np.arctan(dy)
    xu, yu = x - yt * np.sin(th), yc + yt * np.cos(th)
    xl, yl = x + yt * np.sin(th), yc - yt * np.cos(th)
    up = np.c_[xu[::-1], yu[::-1]]
    lo = np.c_[xl[1:], yl[1:]]
    return np.vstack([up, lo])


def first_cell(Re: float, chord: float = 1.0, yplus: float = 1.0) -> float:
    """Wall spacing for a target y+ from the flat-plate Cf (Schlichting: Cf = 0.026 Re^-1/7)."""
    cf = 0.026 * Re ** (-1 / 7)
    return yplus * chord * math.sqrt(2 / cf) / Re


# --------------------------------------------------------------------------------------------- 2-D mesh
def airfoil_mesh(airfoil: str, path: str | Path, Re: float, n_surf: int = 161, farfield: float = 100.0,
                 growth: float = 1.15, bl_thick: float = 0.04, refine: float = 1.0) -> dict:
    """Gmsh 2-D hybrid mesh: quad boundary layer (first cell y+≈1, growth ``growth``) + triangles, written in SU2
    format with markers ``airfoil`` and ``farfield``.

    ``refine`` = r scales the mesh systematically for a grid-convergence study (Celik et al. 2008): surface
    points ×r, first cell /r, BL growth ratio g^(1/r), near-field and wake sizes /r."""
    n_surf = int(round((n_surf - 1) * refine)) + 1
    growth = growth ** (1.0 / refine)
    xy = naca_coords(airfoil, n_surf)
    h1 = first_cell(Re) / refine
    g = lambda v: repr(float(v))  # noqa: E731  (full precision in the .geo)
    L = ["// acdt Phase 4 — 2-D hybrid airfoil mesh (written by acdt, meshed by the gmsh executable)",
         ]
    P = xy[:-1]
    for k, (x, y) in enumerate(P, start=1):
        L.append(f"Point({k}) = {{{g(x)}, {g(y)}, 0, 0.01}};")
    n = len(P)
    i_le = int(np.argmin(P[:, 0]))
    up_pts = list(range(1, i_le + 2))
    lo_pts = list(range(i_le + 1, n + 1)) + [1]
    R = farfield
    c0, f1, f2 = n + 1, n + 2, n + 3
    L += [f"Spline(1) = {{{', '.join(map(str, up_pts))}}};",
          f"Spline(2) = {{{', '.join(map(str, lo_pts))}}};",
          f"Point({c0}) = {{0.5, 0, 0, {g(R / 8)}}};",
          f"Point({f1}) = {{{g(0.5 + R)}, 0, 0, {g(R / 8)}}};",
          f"Point({f2}) = {{{g(0.5 - R)}, 0, 0, {g(R / 8)}}};",
          f"Circle(3) = {{{f1}, {c0}, {f2}}};",
          f"Circle(4) = {{{f2}, {c0}, {f1}}};",
          "Curve Loop(1) = {3, 4};", "Curve Loop(2) = {1, 2};", "Plane Surface(1) = {1, 2};",
          f"Transfinite Curve{{1}} = {n_surf} Using Bump 0.15;",
          f"Transfinite Curve{{2}} = {n_surf} Using Bump 0.15;",
          "Field[1] = BoundaryLayer;", "Field[1].CurvesList = {1, 2};",
          f"Field[1].Size = {g(h1)};", f"Field[1].Ratio = {g(growth)};", f"Field[1].Thickness = {g(bl_thick)};",
          "Field[1].Quads = 1;", "BoundaryLayer Field = 1;",
          # wake / near-field refinement
          "Field[2] = Distance;", "Field[2].CurvesList = {1, 2};",
          "Field[3] = Threshold;", "Field[3].InField = 2;", f"Field[3].SizeMin = {g(0.008 / refine)};",
          f"Field[3].SizeMax = {g(R / 8)};", "Field[3].DistMin = 0.05;", f"Field[3].DistMax = {g(R)};",
          "Field[3].StopAtDistMax = 1;",
          "Field[4] = Box;"]
    for k, v in dict(VIn=0.03 / refine, VOut=R, XMin=-0.2, XMax=3.0, YMin=-0.4, YMax=0.4, Thickness=1.5).items():
        L.append(f"Field[4].{k} = {g(v)};")
    L += ["Field[5] = Min;", "Field[5].FieldsList = {3, 4};", "Background Field = 5;",
          "Mesh.MeshSizeExtendFromBoundary = 0;", "Mesh.MeshSizeFromPoints = 0;", "Mesh.Algorithm = 5;",
          'Physical Curve("airfoil") = {1, 2};', 'Physical Curve("farfield") = {3, 4};',
          'Physical Surface("fluid") = {1};', ""]
    path = Path(path)
    tools.run_gmsh("\n".join(L), path.parent, path.stem + ".geo", path, dim=2)
    n_el = tools.su2_nelem(path)
    return {"mesh": tools.case_relative(path, Path(path).resolve().parent),
            "cells": int(n_el), "first_cell": h1, "farfield_c": farfield, "airfoil": airfoil}


# --------------------------------------------------------------------------------------------- SU2 2-D
def su2_airfoil_cfg(mesh: str, alpha: float, Re: float, mach: float = 0.15, iters: int = 4000,
                    restart: bool = False) -> str:
    """Compressible RANS-SA, Roe 2nd order (the SU2 'Turbulent NACA 0012' validation set-up, Rumer/NASA TMR).
    Mach below 0.15 is raised to 0.15 (density-based solver stiffness; Prandtl–Glauert effect < 1 %)."""
    return f"""% acdt Phase 4 — 2-D compressible RANS (SA, fully turbulent), chord 1 m
SOLVER= RANS
KIND_TURB_MODEL= SA
MATH_PROBLEM= DIRECT
RESTART_SOL= {'YES' if restart else 'NO'}
MACH_NUMBER= {max(mach, 0.15):.4f}
AOA= {alpha:.3f}
FREESTREAM_TEMPERATURE= 288.15
REYNOLDS_NUMBER= {Re:.6e}
REYNOLDS_LENGTH= 1.0
REF_ORIGIN_MOMENT_X= 0.25
REF_ORIGIN_MOMENT_Y= 0.00
REF_ORIGIN_MOMENT_Z= 0.00
REF_LENGTH= 1.0
REF_AREA= 1.0
MARKER_HEATFLUX= ( airfoil, 0.0 )
MARKER_FAR= ( farfield )
MARKER_PLOTTING= ( airfoil )
MARKER_MONITORING= ( airfoil )
NUM_METHOD_GRAD= WEIGHTED_LEAST_SQUARES
CFL_NUMBER= 5.0
CFL_ADAPT= YES
CFL_ADAPT_PARAM= ( 0.5, 1.2, 5.0, 200.0 )
LINEAR_SOLVER= FGMRES
LINEAR_SOLVER_PREC= ILU
LINEAR_SOLVER_ERROR= 1E-6
LINEAR_SOLVER_ITER= 15
MGLEVEL= 0
CONV_NUM_METHOD_FLOW= ROE
MUSCL_FLOW= YES
SLOPE_LIMITER_FLOW= VENKATAKRISHNAN
VENKAT_LIMITER_COEFF= 0.05
CONV_NUM_METHOD_TURB= SCALAR_UPWIND
MUSCL_TURB= NO
TIME_DISCRE_FLOW= EULER_IMPLICIT
TIME_DISCRE_TURB= EULER_IMPLICIT
ITER= {iters}
CONV_FIELD= ( LIFT, DRAG, MOMENT_Z )
CONV_STARTITER= 300
CONV_CAUCHY_ELEMS= 200
CONV_CAUCHY_EPS= 2E-6
MESH_FILENAME= {mesh}
MESH_FORMAT= SU2
SOLUTION_FILENAME= restart_flow.dat
RESTART_FILENAME= restart_flow.dat
OUTPUT_FILES= ( RESTART, SURFACE_CSV )
SCREEN_OUTPUT= ( INNER_ITER, RMS_DENSITY, RMS_NU_TILDE, LIFT, DRAG, MOMENT_Z )
HISTORY_OUTPUT= ( ITER, RMS_RES, AERO_COEFF )
CONV_FILENAME= history
SCREEN_WRT_FREQ_INNER= 100
"""


def _hist_cell(value: str) -> str:
    # SU2 8.5 writes ``    "CL"    `` (spaces inside the quotes). csv.reader keeps those spaces, so a
    # later strip of only the surrounding quote leaves the name unmatched and a short file (under 200
    # rows) feeds the header line itself to float().
    return value.strip().strip('"').strip()


def _last_history(path: Path) -> dict:
    with open(path) as f:
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError(f"empty history {path}")
    head = [_hist_cell(h) for h in rows[0]]
    data = []
    for row in rows[1:]:
        if len(row) < len(head):
            continue
        try:
            data.append([float(_hist_cell(v)) for v in row[:len(head)]])
        except ValueError:
            continue
    if not data:
        raise ValueError(f"no numeric rows in {path}")
    last = data[-1]
    d = dict(zip(head, last))
    lift = [r[head.index("CL")] for r in data[-200:]] if "CL" in head else []
    d["CL_unsteady"] = float(np.std(lift)) if lift else 0.0
    # iterative-convergence indicator: relative change of each force coefficient over the last 10 % of the
    # iterations of this run (the residual alone does not show the slow drift of CD in cold-started SA runs)
    k0 = max(0, int(0.9 * (len(data) - 1)))
    for key in ("CL", "CD", "CMz", "CMy"):
        if key in head and len(data) > 10:
            i = head.index(key)
            a, b = data[k0][i], last[i]
            d[f"{key}_drift"] = abs(b - a) / max(abs(b), 1e-12)
    return d


@dataclass
class Polar2D:
    airfoil: str
    Re: float
    mach: float = 0.15
    alpha: list = field(default_factory=list)
    cl: list = field(default_factory=list)
    cd: list = field(default_factory=list)
    cm: list = field(default_factory=list)
    res: list = field(default_factory=list)
    unsteady: list = field(default_factory=list)
    drift: list = field(default_factory=list)  # {cl, cd, cm} relative change over the last 10 % of iterations
    iters_total: list = field(default_factory=list)
    cells: int = 0
    wall_s: float = 0.0
    notes: list = field(default_factory=list)

    @property
    def clmax(self) -> float:
        return float(max(self.cl)) if self.cl else float("nan")

    def summary(self) -> dict:
        d = asdict(self)
        d["clmax"] = self.clmax
        return d


def estimate_2d(cells: int, n_alpha: int, iters: int = 4000) -> tools.Budget:
    """SU2 INC_RANS 2-D: ~1.5 kB/cell... measured ≈ 0.25 GB per 50 k cells; ≈ 2.5 µs per cell-iteration per core."""
    mem = 0.4 + cells * 5e-6
    t = cells * iters * n_alpha * 2.5e-6 / max(1, min(8, tools.cores())) / 60
    return tools.budget(mem, t)


def run_airfoil_polar(airfoil: str, Re: float, alphas, work: str | Path, nproc: int | None = None,
                      iters: int = 4000, force: bool = False, mach: float = 0.15, refine: float = 1.0) -> Polar2D:
    """Mesh + SU2 sweep in α (each point restarts from the previous one). Raises ToolNotAvailable without SU2."""
    su2 = tools.find_exe("SU2_CFD")
    if su2 is None:
        raise ToolNotAvailable("SU2_CFD not found ($ACDT_HIFI_BIN or PATH)")
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    m = airfoil_mesh(airfoil, work / "airfoil.su2", Re, refine=refine)
    pol = Polar2D(airfoil, Re, cells=m["cells"], mach=max(mach, 0.15))
    b = estimate_2d(m["cells"], len(alphas), iters)
    if not b.run_here and not force:
        pol.notes.append(f"não corrido: {b.reason}")
        return pol
    nproc = nproc or min(8, tools.cores())
    t0 = time.time()
    for k, a in enumerate(alphas):
        cfg = work / f"a{a:+05.1f}.cfg"
        cfg.write_text(su2_airfoil_cfg("airfoil.su2", a, Re, mach=mach, iters=iters, restart=k > 0))
        rc = tools.run(tools.mpi_prefix(nproc) + [su2, cfg.name], work, f"a{a:+05.1f}.log")
        h = work / "history.csv"
        if rc != 0 or not h.exists():
            pol.notes.append(f"α={a}: SU2 falhou (rc {rc}), ver {cfg.with_suffix('.log').name}")
            continue
        d = _last_history(h)
        h.rename(work / f"history_a{a:+05.1f}.csv")
        pol.alpha.append(float(a))
        pol.cl.append(d.get("CL", float("nan")))
        pol.cd.append(d.get("CD", float("nan")))
        pol.cm.append(-d.get("CMz", float("nan")))  # SU2 CMz>0 is nose-down (x aft, y up)
        pol.res.append(d.get("rms[Rho]", float("nan")))
        pol.unsteady.append(d["CL_unsteady"])
        pol.drift.append({"cl": d.get("CL_drift"), "cd": d.get("CD_drift"), "cm": d.get("CMz_drift")})
        pol.iters_total.append(iters)
    pol.wall_s = time.time() - t0
    (work / "polar.json").write_text(json.dumps(pol.summary(), indent=1))
    return pol


def _interp_at_cl(cl, y, target):
    cl, y = np.asarray(cl), np.asarray(y)
    i1 = int(np.argmax(cl))
    c, v = cl[: i1 + 1], y[: i1 + 1]
    o = np.argsort(c)
    return float(np.interp(target, c[o], v[o]))


CRUISE_ALPHAS = (-2.0, 0.0, 2.0, 4.0, 6.0)
STALL_ALPHAS = (0.0, 4.0, 8.0, 10.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 20.0)


def verify_section(res, work: str | Path, iters: int = 4000, nproc: int | None = None,
                   cruise_alphas=CRUISE_ALPHAS, stall_alphas=STALL_ALPHAS) -> dict:
    """SU2 RANS section polars at the L1 cruise and stall Reynolds numbers, compared with the L1 XFOIL polars.

    Returns the comparison and the *section* ratios RANS / XFOIL: clmax (stall Re), cd at cl = 0.5 (the L1
    ``CDp_wing_cruise`` point), cm0 difference. Fully-turbulent SA vs XFOIL (cruise xtr ≤ 0.10, stall free
    transition, Ncrit 9): the cruise comparison is like-for-like within the forced-transition approximation; near
    stall steady RANS-SA is itself uncertain (typically ±10 % on clmax, NASA TMR) — stated in the report."""
    from ....core.atmosphere import isa

    lf = res.lowfi
    if lf is None:
        raise ToolNotAvailable("needs aero.fidelity: lowfi (the XFOIL polars to compare with)")
    work = Path(work)
    af = res.config.wing.airfoil
    M_c = res.cruise_speed / isa(res.cruise_altitude).a
    pc = run_airfoil_polar(af, lf.cruise_Re, cruise_alphas, work / "cruise", nproc, iters, mach=M_c)
    ps = run_airfoil_polar(af, lf.clmax_Re, stall_alphas, work / "stall", nproc, iters, mach=0.15)
    xc, xs = lf.polar_cruise, lf.polar_stall
    out = {"airfoil": af, "cruise": pc.summary(), "stall": ps.summary(), "ref": SU2_REF,
           "mesh_cells": pc.cells, "notes": pc.notes + ps.notes}
    if pc.cl and ps.cl:
        cd_r = _interp_at_cl(pc.cl, pc.cd, 0.5)
        cd_x = float(xc.cd_at_cl(0.5))
        cm_r = _interp_at_cl(pc.cl, pc.cm, 0.0) if min(pc.cl) < 0 < max(pc.cl) else float(pc.cm[0])
        cla_r = float(np.polyfit(np.radians(pc.alpha), pc.cl, 1)[0])
        out.update({
            "clmax_rans": ps.clmax, "clmax_xfoil": float(xs.clmax), "k_clmax": ps.clmax / float(xs.clmax),
            "alpha_clmax_rans": float(ps.alpha[int(np.argmax(ps.cl))]),
            "clmax_at_sweep_end": bool(int(np.argmax(ps.cl)) == len(ps.cl) - 1),
            "cd05_rans": cd_r, "cd05_xfoil": cd_x, "k_cd_profile": cd_r / cd_x,
            "cm0_rans": cm_r, "cm0_xfoil": float(xc.cm0), "d_cm0": cm_r - float(xc.cm0),
            "cla_rans": cla_r,
            "unsteady_max": float(max(ps.unsteady)) if ps.unsteady else 0.0,
        })
    (work / "section_verification.json").write_text(json.dumps(out, indent=1, default=float))
    return out


def gci(f1: float, f2: float, f3: float, h1: float, h2: float, h3: float, Fs: float = 1.25) -> dict:
    """Grid Convergence Index, Celik et al., ASME J. Fluids Eng. 130 (2008) 078001 (Roache's GCI with the
    fixed-point iteration for non-constant refinement ratio). 1 = fine, 3 = coarse; h = (1/N)^(1/2) in 2-D."""
    r21, r32 = h2 / h1, h3 / h2
    e21, e32 = f2 - f1, f3 - f2
    out = {"f": [f1, f2, f3], "h": [h1, h2, h3], "r21": r21, "r32": r32}
    if e21 == 0 or e32 == 0:
        return {**out, "p": float("nan"), "oscillatory": False, "f_ext": f1, "gci_fine": 0.0}
    s = np.sign(e32 / e21)
    p = 2.0
    for _ in range(100):
        q = np.log((r21 ** p - s) / (r32 ** p - s))
        p_new = abs(np.log(abs(e32 / e21)) + q) / np.log(r21)
        if abs(p_new - p) < 1e-8:
            break
        p = p_new
    f_ext = (r21 ** p * f1 - f2) / (r21 ** p - 1)
    ea21 = abs((f1 - f2) / f1)
    o = {**out, "p": float(p), "oscillatory": bool(s < 0), "f_ext": float(f_ext),
         "e_ext_fine": float(abs((f_ext - f1) / f_ext)), "gci_fine": float(Fs * ea21 / (r21 ** p - 1))}
    if s < 0:
        # oscillatory convergence: Richardson extrapolation is not valid; report instead the oscillation-range
        # uncertainty U = ½ (f_max − f_min) (Stern et al., ASME JFE 123 (2001) 793, §"oscillatory convergence")
        o["u_osc"] = float(0.5 * (max(f1, f2, f3) - min(f1, f2, f3)) / abs(f1))
        o["gci_fine"] = None
        o["f_ext"] = None
    return o


def continue_point(work: str | Path, alpha: float, Re: float, mach: float = 0.15, iters: int = 4000,
                   nproc: int | None = None) -> dict:
    """Continue one converged-so-far SU2 point from its restart_flow.dat for ``iters`` more iterations (same mesh,
    same settings). Returns the last-history dict (with the drift indicators)."""
    su2 = tools.find_exe("SU2_CFD")
    if su2 is None:
        raise ToolNotAvailable("SU2_CFD not found ($ACDT_HIFI_BIN or PATH)")
    work = Path(work)
    tag = f"a{alpha:+05.1f}"
    cfg = work / f"{tag}_cont.cfg"
    cfg.write_text(su2_airfoil_cfg("airfoil.su2", alpha, Re, mach=mach, iters=iters, restart=True))
    rc = tools.run(tools.mpi_prefix(nproc or min(8, tools.cores())) + [su2, cfg.name], work, f"{tag}_cont.log")
    h = work / "history.csv"
    if rc != 0 or not h.exists():
        raise RuntimeError(f"SU2 continuation failed (rc {rc}) in {work}")
    d = _last_history(h)
    n = len(list(work.glob(f"history_{tag}_cont*.csv")))
    h.rename(work / f"history_{tag}_cont{n + 1}.csv")
    return d


def grid_convergence(airfoil: str, Re: float, alpha: float, work: str | Path, mach: float = 0.15,
                     refine=(1 / np.sqrt(2), 1.0, np.sqrt(2)), iters: int = 4000, nproc: int | None = None,
                     drift_tol: float = 1e-3, max_rounds: int = 3) -> dict:
    """Three systematically refined meshes at one α; GCI on cl, cd, cm (Celik et al. 2008).

    The GCI assumes the iterative error is negligible against the discretisation error (Roache 1998, ch. 5;
    Celik et al. 2008, §1). Each mesh is therefore continued from its restart, ``iters`` iterations per round
    (each round a separate bounded run), until every force coefficient changes by less than ``drift_tol``
    (relative) over the last 10 % of the round, or ``max_rounds`` is reached. Each coefficient's GCI is then
    flagged ``iterative_ok`` only if the worst drift is < 0.1 × the fine–medium relative difference.
    Existing results in ``work`` (polar.json + restart) are resumed, not recomputed.

    The pipeline default is this three-mesh, one-angle study (``run.py`` calls it at α = 2°).
    Celik et al. 2008 recommend a refinement ratio above 1.3. On the stored C172 meshes the
    coarser step is r32 = 1.273, the observed order of cd is above the formal order, and only
    one angle was run. A follow-up would add one finer mesh at refine = 2 — one more factor
    √2 in h past the current finest (refine = √2), about twice the cells (~1.2×10^5 on that
    airfoil) — and the angles 0°, 2° and 4°. Those three angles are PRESSUPOSTO neighbours of
    the cl = 0.5 comparison, not a cited GCI prescription. ``gci`` stays a three-grid formula;
    the extra mesh would be a new triplet with the two current finer meshes. That study is not
    this default and is not started here."""
    work = Path(work)
    pts = []
    for r in sorted(refine, reverse=True):  # refine > 1 is the finer mesh → fine first
        wd = work / f"r{r:.3f}"
        pj = wd / "polar.json"
        if pj.exists() and (wd / "restart_flow.dat").exists():
            pol = json.loads(pj.read_text(encoding="utf-8"))
        else:
            pol = run_airfoil_polar(airfoil, Re, [alpha], wd, nproc, iters, mach=mach, refine=r).summary()
        if not pol["cl"]:
            return {"notes": pol["notes"]}
        drift = (pol.get("drift") or [{}])[0] or {}
        if not drift:  # result written before the drift indicator existed: recompute it from the history file
            tag = f"a{alpha:+05.1f}"
            hs = sorted(wd.glob(f"history_{tag}_cont*.csv"), key=lambda q: int(q.stem.rsplit("cont", 1)[1]))
            hist = hs[-1] if hs else wd / f"history_{tag}.csv"
            if hist.exists():
                d = _last_history(hist)
                drift = {"cl": d.get("CL_drift"), "cd": d.get("CD_drift"), "cm": d.get("CMz_drift")}
        n_it = (pol.get("iters_total") or [iters])[0]
        rounds = 0
        while drift and max((v or 0.0) for v in drift.values()) > drift_tol and rounds < max_rounds:
            d = continue_point(wd, alpha, Re, mach, iters, nproc)
            rounds += 1
            n_it += iters
            drift = {"cl": d.get("CL_drift"), "cd": d.get("CD_drift"), "cm": d.get("CMz_drift")}
            pol["cl"], pol["cd"], pol["cm"] = [d["CL"]], [d["CD"]], [-d["CMz"]]
            pol["res"] = [d.get("rms[Rho]")]
            pol["drift"], pol["iters_total"] = [drift], [n_it]
            pj.write_text(json.dumps(pol, indent=1))
        pts.append((pol, drift, n_it))
    N = [p["cells"] for p, _, _ in pts]
    h = [(1.0 / n) ** 0.5 for n in N]
    out = {"airfoil": airfoil, "Re": Re, "alpha": alpha, "cells": N, "iterations": [n for _, _, n in pts],
           "ref": "Celik et al. (2008) ASME JFE 130:078001", "drift_tol": drift_tol}
    for key in ("cl", "cd", "cm"):
        f = [p[key][0] for p, _, _ in pts]
        g = gci(*f, *h)
        g["iter_drift"] = [dr.get(key) for _, dr, _ in pts]
        worst = max((v or 0.0) for v in g["iter_drift"])
        ea21 = abs((f[0] - f[1]) / f[0]) if f[0] else float("inf")
        g["iterative_ok"] = bool(worst < 0.1 * ea21)
        out[key] = g
    (work / "gci.json").write_text(json.dumps(out, indent=1, default=float))
    return out


def plot_section(v: dict, res, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lf = res.lowfi
    fig, ax = plt.subplots(1, 3, figsize=(14, 4))
    for key, pol, lab in (("cruise", lf.polar_cruise, "cruzeiro"), ("stall", lf.polar_stall, "perda")):
        r = v[key]
        p = pol.lo
        ax[0].plot(p.alpha, p.cl, "-", lw=1, label=f"XFOIL {lab} Re {r['Re']:.2g}")
        ax[0].plot(r["alpha"], r["cl"], "o--", label=f"SU2 RANS-SA {lab}")
        ax[1].plot(p.cd, p.cl, "-", lw=1, label=f"XFOIL {lab}")
        ax[1].plot(r["cd"], r["cl"], "o--", label=f"SU2 {lab}")
        ax[2].plot(p.alpha, p.cm, "-", lw=1, label=f"XFOIL {lab}")
        ax[2].plot(r["alpha"], r["cm"], "o--", label=f"SU2 {lab}")
    for a, (xl, yl) in zip(ax, (("α [°]", "cl"), ("cd", "cl"), ("α [°]", "cm c/4"))):
        a.set_xlabel(xl)
        a.set_ylabel(yl)
        a.grid(alpha=0.3)
    ax[1].set_xlim(0, 0.04)
    ax[0].legend(fontsize=7)
    fig.suptitle(f"{v['airfoil']}: SU2 RANS-SA 2-D vs XFOIL (L1)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return str(path)


def launch_wing_rans(patches, avl_text, cfg_text, run, **kwargs):
    """Run a wing RANS callable only after the mesh matches the AVL file and the SU2 case.

    ``run`` is not called when :func:`verify_wing_rans_geometry` fails. The import stays inside
    the function because ``wing_bl`` imports this module at load time. This function does not
    import SU2 or pyHyp.
    """
    from .wing_bl import verify_wing_rans_geometry

    report = verify_wing_rans_geometry(patches, avl_text, cfg_text, **kwargs)
    return {"geometry": report, "result": run()}
