# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""One coarse RANS angle of a C172 wing-plus-fuselage half model.

The y+ ≈ 1 estimate in :mod:`rans_wing_fuselage` is not repeated and its JSON is
not rewritten. This module builds a solid with no tails, meshes it with Gmsh as
a separate process, and launches SU2 OpenMP (never ``mpiexec``) only when the
cell count fits both guards:

* RAM: ``cells × 1.8 kB × 3.23`` at or below 70 % of free RAM. The 1.8 kB/cell
  figure is the formula in :func:`cfd3d.rans_volume_estimate`. The 3.23 factor is
  PRESSUPOSTO, carried from the flying-wing hex mesh (8.4 GB working set
  against 2.6 GB of that formula). It is not a measurement of this tetrahedral
  mesh.
* Time: that mesh's 1.63×10⁻⁵ s/cell/iteration/thread, six threads, must fit
  in 45 min for one angle and 8000 iterations. That rate is PRESSUPOSTO here.

A missing coefficient stays missing. One angle does not calibrate the L1 polar.
"""
from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

from .cfd import _hist_cell
from .geometry import export_vsp, vsp_spec
from .rans_wing_fuselage import polar_comparison
from . import tools

# Formula already used by rans_volume_estimate. Not re-fitted.
KB_PER_CELL = 1.8
# PRESSUPOSTO from the flying-wing hex mesh: working set / formula RAM.
WORKSET_FACTOR = 3.23
# PRESSUPOSTO from the same file. Not measured on this tetrahedral mesh.
MEASURED_RATE_S = 1.63e-5
N_THREADS = 6
ITER_CAP = 8000
CHUNK_ITERS = 400
MAX_TIME_MIN = 45.0
# Cauchy window already used by the 2-D SA deck in cfd.su2_airfoil_cfg.
CAUCHY_ELEMS = 200
CAUCHY_EPS = 2e-6
CAUCHY_START = 300
PLANNED_ALPHAS = (0.0, 2.0, 4.0)
RESULT_JSON = "h5_c172_rans_um_angulo.json"
RESULT_CSV = "h5_c172_rans_um_angulo.csv"
DESIGN = "cessna172_check"


def cell_caps(available_gb: float, *, iters: int = ITER_CAP, n_alpha: int = 1,
              n_threads: int = N_THREADS, max_time_min: float = MAX_TIME_MIN,
              workset_factor: float = WORKSET_FACTOR) -> dict:
    """Largest cell count that satisfies the RAM guard and the time guard.

    The binding cap is the smallest of the three. A non-positive input does not
    become a zero-cell pass: ``run_here`` is false and ``cell_cap`` is null.
    """
    bad = []
    if not _positive(available_gb):
        bad.append("RAM livre")
    if not _positive(iters) or not _positive(n_alpha) or not _positive(n_threads):
        bad.append("contagem")
    if not _positive(max_time_min) or not _positive(workset_factor):
        bad.append("limite")
    if bad:
        return {
            "run_here": False, "cell_cap": None, "binding": None,
            "reason": "entrada inválida: " + ", ".join(bad),
            "limit_GB": None, "by_formula_ram": None, "by_workset_ram": None, "by_time": None,
        }
    limit = 0.7 * float(available_gb)
    per = KB_PER_CELL * 1e-6
    by_formula = limit / per
    by_workset = limit / (per * float(workset_factor))
    by_time = float(max_time_min) * 60.0 * float(n_threads) / (
        float(iters) * float(n_alpha) * MEASURED_RATE_S)
    named = {"formula_ram": by_formula, "workset_ram": by_workset, "measured_rate_time": by_time}
    binding = min(named, key=named.get)
    return {
        "run_here": True,
        "cell_cap": named[binding],
        "binding": binding,
        "reason": "o tecto é " + binding,
        "limit_GB": limit,
        "by_formula_ram": by_formula,
        "by_workset_ram": by_workset,
        "by_time": by_time,
        "workset_factor": float(workset_factor),
        "workset_factor_note": (
            "PRESSUPOSTO: 3,23 é o conjunto de trabalho da malha hex da asa voadora "
            "dividido pela fórmula de 1,8 kB/célula. Não foi medido nesta malha."
        ),
        "measured_rate_s": MEASURED_RATE_S,
        "measured_rate_note": (
            "PRESSUPOSTO: 1,63e-5 s/célula/iteração por thread é a taxa dessa malha hex. "
            "Não foi medida nesta malha de tetraedros."
        ),
    }


def mesh_guard(cells: float, available_gb: float, *, iters: int = ITER_CAP, n_alpha: int = 1,
               n_threads: int = N_THREADS, max_time_min: float = MAX_TIME_MIN) -> dict:
    """Refuse the launch when the counted cells miss either guard.

    ``cells`` comes from the mesh (``NELEM``). It is not replaced by the formula
    that produced the 12 million cell estimate.
    """
    caps = cell_caps(available_gb, iters=iters, n_alpha=n_alpha, n_threads=n_threads,
                     max_time_min=max_time_min)
    if not _positive(cells) or not math.isfinite(float(cells)):
        return {
            "run_here": False, "reasons": ["não há contagem finita de células"],
            "ram_formula_GB": None, "ram_workset_GB": None, "time_min_measured_rate": None,
            "caps": caps,
        }
    ram_formula = float(cells) * KB_PER_CELL * 1e-6
    ram_workset = ram_formula * WORKSET_FACTOR
    time_min = float(cells) * float(iters) * float(n_alpha) * MEASURED_RATE_S / float(n_threads) / 60.0
    reasons = []
    limit = caps.get("limit_GB")
    if limit is None or ram_workset > limit:
        reasons.append(
            f"memória com o factor 3,23: {ram_workset:.2f} GB acima de 70 % da RAM livre"
            if limit is None else
            f"memória com o factor 3,23: {ram_workset:.2f} GB > {limit:.2f} GB"
        )
    if time_min > max_time_min:
        reasons.append(
            f"tempo à taxa medida {time_min:.0f} min > limite {max_time_min:.0f} min"
        )
    return {
        "run_here": not reasons,
        "reasons": reasons,
        "ram_formula_GB": ram_formula,
        "ram_workset_GB": ram_workset,
        "time_min_measured_rate": time_min,
        "cells": int(cells),
        "limit_GB": limit,
        "caps": caps,
        "n_threads": n_threads,
        "iters": iters,
        "n_alpha": n_alpha,
        "max_time_min": max_time_min,
    }


def drop_tails(spec: dict) -> dict:
    """Copy of a VSP spec without horizontal or vertical tail."""
    out = dict(spec)
    out.pop("htail", None)
    out.pop("vtail", None)
    return out


def half_model_geo(wing_step: str, fuselage_step: str, mac: float, semispan: float,
                   h: float, farfield_c: float = 12.0) -> str:
    """Gmsh OCC script: sew each solid, keep y ≥ 0, subtract it from a box.

    Each STEP is a closed shell of surfaces, sewn into a volume. The fuselage is
    cut to y ≥ 0. The wing STEP is already the right half. ``BooleanUnion`` fails
    on this pair; ``BooleanFragments`` splits them and the farfield box subtracts
    every fragment. There is no prism layer. ``h`` is the near-body size.
    """
    g = lambda v: repr(float(v))  # noqa: E731
    R = float(farfield_c) * float(mac)
    return f"""// acdt — C172 wing + fuselage, half model, tetrahedra. No tails. No prism layer.
SetFactory("OpenCASCADE");
Geometry.OCCTargetUnit = "M";
fsurf() = ShapeFromFile("{fuselage_step}");
Surface Loop(1) = {{fsurf()}} Using Sewing;
Volume(10) = {{1}};
fb() = BoundingBox Volume{{10}};
cut = newv;
Box(cut) = {{fb(0) - 1.0, 0.0, fb(2) - 1.0, (fb(3) - fb(0)) + 2.0, fb(4) + 2.0, (fb(5) - fb(2)) + 2.0}};
half() = BooleanIntersection{{ Volume{{10}}; Delete; }}{{ Volume{{cut}}; Delete; }};
wsurf() = ShapeFromFile("{wing_step}");
Surface Loop(2) = {{wsurf()}} Using Sewing;
Volume(20) = {{2}};
aircraft() = BooleanFragments{{ Volume{{half()}}; Delete; }}{{ Volume{{20}}; Delete; }};
bw() = BoundingBox Volume{{aircraft()}};
xmin = bw(0); zmin = bw(2); xmax = bw(3); zmax = bw(5);
R = {g(R)};
semispan = {g(semispan)};
box = newv;
Box(box) = {{xmin - R, 0.0, zmin - R, (xmax - xmin) + 2 * R, semispan + R, (zmax - zmin) + 2 * R}};
fluid() = BooleanDifference{{ Volume{{box}}; Delete; }}{{ Volume{{aircraft()}}; Delete; }};
vol = fluid(0);
faces() = Boundary{{ Volume{{vol}}; }};
wall() = {{}}; sym() = {{}}; far() = {{}};
For i In {{0 : #faces() - 1}}
  t = Fabs(faces(i));
  b() = BoundingBox Surface{{t}};
  If (Fabs(b(1)) < 1e-4 && Fabs(b(4)) < 1e-4)
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
Field[1].Sampling = 40;
Field[2] = Threshold;
Field[2].InField = 1;
Field[2].SizeMin = {g(h)};
Field[2].SizeMax = R / 5;
Field[2].DistMin = {g(0.3 * mac)};
Field[2].DistMax = R;
Field[3] = Min;
Field[3].FieldsList = {{2}};
Background Field = 3;
Mesh.MeshSizeExtendFromBoundary = 0;
Mesh.MeshSizeFromPoints = 0;
Mesh.MeshSizeFromCurvature = 0;
Mesh.Algorithm = 6;
Mesh.MeshSizeMin = {g(h / 2)};
Mesh.Algorithm3D = 1;
Physical Surface("aircraft") = {{wall()}};
Physical Surface("symmetry") = {{sym()}};
Physical Surface("farfield") = {{far()}};
Physical Volume("fluid") = {{vol}};
"""


def rans_cfg(mesh: str, alpha: float, mach: float, reynolds: float, re_length: float,
             s_half: float, mac: float, x_ref: float, *, iters: int, restart: bool) -> str:
    """SU2 8.5 RANS-SA deck for one angle. Restart files are always named.

    The Cauchy window is the one in :func:`cfd.su2_airfoil_cfg`. Pitch is
    ``MOMENT_Y``, as in the half-wing Euler deck. ``ITER`` is the absolute
    iteration this launch must reach, which is how a restarted SU2 run is capped.
    """
    mach_used = max(float(mach), 0.15)
    return f"""% acdt — C172 wing + fuselage, half model, compressible RANS-SA. One angle.
SOLVER= RANS
KIND_TURB_MODEL= SA
MATH_PROBLEM= DIRECT
RESTART_SOL= {'YES' if restart else 'NO'}
MACH_NUMBER= {mach_used:.4f}
AOA= {float(alpha):.3f}
SIDESLIP_ANGLE= 0.0
FREESTREAM_TEMPERATURE= 288.15
REYNOLDS_NUMBER= {float(reynolds):.6e}
REYNOLDS_LENGTH= {float(re_length):.5f}
REF_ORIGIN_MOMENT_X= {float(x_ref):.5f}
REF_ORIGIN_MOMENT_Y= 0.0
REF_ORIGIN_MOMENT_Z= 0.0
REF_LENGTH= {float(mac):.5f}
REF_AREA= {float(s_half):.5f}
MARKER_HEATFLUX= ( aircraft, 0.0 )
MARKER_SYM= ( symmetry )
MARKER_FAR= ( farfield )
MARKER_PLOTTING= ( aircraft )
MARKER_MONITORING= ( aircraft )
NUM_METHOD_GRAD= WEIGHTED_LEAST_SQUARES
CFL_NUMBER= 5.0
CFL_ADAPT= YES
CFL_ADAPT_PARAM= ( 0.5, 1.2, 5.0, 100.0 )
CONV_NUM_METHOD_FLOW= ROE
MUSCL_FLOW= YES
SLOPE_LIMITER_FLOW= VENKATAKRISHNAN
VENKAT_LIMITER_COEFF= 0.05
CONV_NUM_METHOD_TURB= SCALAR_UPWIND
MUSCL_TURB= NO
TIME_DISCRE_FLOW= EULER_IMPLICIT
TIME_DISCRE_TURB= EULER_IMPLICIT
LINEAR_SOLVER= FGMRES
LINEAR_SOLVER_PREC= ILU
LINEAR_SOLVER_ERROR= 1E-6
LINEAR_SOLVER_ITER= 10
ITER= {int(iters)}
CONV_FIELD= ( LIFT, DRAG, MOMENT_Y )
CONV_STARTITER= {CAUCHY_START}
CONV_CAUCHY_ELEMS= {CAUCHY_ELEMS}
CONV_CAUCHY_EPS= {CAUCHY_EPS:.1e}
SCREEN_OUTPUT= ( INNER_ITER, RMS_DENSITY, LIFT, DRAG, MOMENT_Y )
HISTORY_OUTPUT= ( ITER, RMS_RES, AERO_COEFF )
CONV_FILENAME= history
MESH_FILENAME= {mesh}
MESH_FORMAT= SU2
SOLUTION_FILENAME= restart_flow.dat
RESTART_FILENAME= restart_flow.dat
OUTPUT_FILES= ( RESTART, SURFACE_CSV )
"""


def parse_history(path: Path) -> dict:
    """Last finite row of a SU2 history. A missing column is null, not zero."""
    if not path.is_file():
        return {"rows": 0, "last": {}, "columns": []}
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return {"rows": 0, "last": {}, "columns": []}
    head = [_hist_cell(cell) for cell in rows[0]]
    data = []
    for row in rows[1:]:
        if len(row) < len(head):
            continue
        parsed = []
        ok = True
        for cell in row[:len(head)]:
            try:
                parsed.append(float(_hist_cell(cell)))
            except ValueError:
                ok = False
                break
        if ok:
            data.append(parsed)
    last = dict(zip(head, data[-1])) if data else {}
    return {"rows": len(data), "last": last, "columns": head}


def cauchy_met(history: dict) -> bool:
    """True when the last Cauchy window of CL, CD and CMy is inside the deck eps.

    A missing column is not a pass. The window is the last ``CAUCHY_ELEMS``
    samples, and only after ``CAUCHY_START`` rows exist.
    """
    path_rows = history.get("series")
    if not path_rows:
        return False
    if len(path_rows) < CAUCHY_START + 2:
        return False
    window = path_rows[-CAUCHY_ELEMS:]
    if len(window) < 2:
        return False
    for key in ("CL", "CD", "CMy"):
        if any(key not in row or not _finite(row[key]) for row in window):
            return False
        for prev, cur in zip(window, window[1:]):
            scale = max(abs(cur[key]), 1e-12)
            if abs(cur[key] - prev[key]) / scale > CAUCHY_EPS:
                return False
    return True


def history_series(path: Path) -> list[dict]:
    """Every finite history row. Used for the Cauchy check. Not written to git."""
    parsed = parse_history(path)
    if not path.is_file() or parsed["rows"] == 0:
        return []
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        rows = list(csv.reader(handle))
    head = [_hist_cell(cell) for cell in rows[0]]
    out = []
    for row in rows[1:]:
        if len(row) < len(head):
            continue
        item = {}
        ok = True
        for name, cell in zip(head, row):
            try:
                item[name] = float(_hist_cell(cell))
            except ValueError:
                ok = False
                break
        if ok:
            out.append(item)
    return out


def _maybe(value):
    """Finite float, or null. A bool is not a number."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive(value) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0.0 and not isinstance(value, bool)


def _finite(value) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and not isinstance(value, bool)


def _repo_root() -> Path:
    start = Path(__file__).resolve()
    for folder in start.parents:
        if (folder / ".git").exists():
            return folder
    return start.parents[5]


def _git(repo: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _coeff(last: dict, *names: str):
    for name in names:
        if name in last and _finite(last[name]):
            return float(last[name]), name
    return None, None


def write_summary_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["quantity", "hifi", "status", "iterative_ok"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "quantity": row["quantity"],
                "hifi": "" if row["hifi"] is None else f"{row['hifi']:.8g}",
                "status": row["status"],
                "iterative_ok": row["iterative_ok"],
            })


def _base_record(today: str, repo: Path) -> dict:
    return {
        "design": DESIGN,
        "date": today,
        "branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "parent": _git(repo, "rev-parse", "origin/main"),
        "decision": "nao_aplicar",
        "valid": False,
        "applied": False,
        "model_L1": "nao_avaliado",
        "example_yaml_edited": False,
        "veredicto": "nao_avaliado",
        "solver_started": False,
        "mesh_written": False,
        "solid": "ausente",
        "imported_by_acdt": False,
        "mpiexec": False,
        "alphas_planned_deg": list(PLANNED_ALPHAS),
        "alpha_run_deg": PLANNED_ALPHAS[0],
        "alphas_not_run_deg": list(PLANNED_ALPHAS[1:]),
        "prior_record": "examples/output/cessna172_check_hifi_win/h5_c172_rans_asa_fuselagem.json",
        "prior_not_rewritten": True,
        "prism_layers": 0,
        "prism_note": (
            "Não há camada de prismas. O caso de 42 camadas e 12,07 milhões de células "
            "continua no registo anterior e não foi repetido."
        ),
    }


def _comparison_rows(last: dict, iterative_ok: bool) -> list[dict]:
    rows = []
    status = "nao_aplicar" if iterative_ok else "nao_avaliado"
    why_ok = (
        "Um α, malha grosseira de tetraedros, sem camada de prismas e sem GCI. "
        "Não se aplica factor."
    )
    why_open = (
        "O critério de Cauchy do deck não foi cumprido. "
        "O número fica registado e não valida o L1."
    )
    for quantity, names in (("CL", ("CL",)), ("CD", ("CD",)), ("Cm", ("CMy", "CMz"))):
        value, found = _coeff(last, *names)
        rows.append({
            "quantity": quantity,
            "hifi": value,
            "column": found,
            "L1": None,
            "ratio": None,
            "same_quantity": False,
            "decision": "nao_aplicar",
            "status": "nao_avaliado" if value is None else status,
            "iterative_ok": bool(iterative_ok) and value is not None,
            "why": (
                "Não há coeficiente. Em falta não é zero." if value is None
                else why_ok if iterative_ok else why_open
            ),
        })
    return rows


def run_one_angle(work: Path, dest: Path, res, *, today: str) -> dict:
    """Export the solid, mesh it, and run α = 0° only if the guard passes.

    α = 2° and 4° stay unrun. The example YAML is not opened for writing.
    """
    work = Path(work)
    dest = Path(dest)
    work.mkdir(parents=True, exist_ok=True)
    dest.mkdir(parents=True, exist_ok=True)
    repo = _repo_root()
    record = _base_record(today, repo)
    record["disk_free_GB"] = shutil.disk_usage(work).free / 1024**3
    available = tools.mem_available_gb()
    record["ram_available_at_launch_GB"] = available
    record["ram_limit_GB"] = 0.7 * available
    wing = res.config.wing
    areas = res.config.wetted_areas()
    from ....core.atmosphere import isa
    from ..aero.avl import wing_x_ac

    at = isa(res.cruise_altitude)
    mach = float(res.cruise_speed) / float(at.a)
    reynolds = float(at.rho) * float(res.cruise_speed) * float(wing.mac) / float(at.mu)
    record["reference"] = {
        "mac_m": float(wing.mac),
        "s_full_m2": float(wing.S),
        "s_half_m2": float(wing.S) / 2.0,
        "s_half_note": "A referência é a meia área da asa, como no Euler de meia asa.",
        "semispan_m": float(wing.span) / 2.0,
        "x_ref_m": float(wing_x_ac(wing)),
        "x_ref_source": "wing_x_ac, o mesmo x_ac do modelo AVL",
        "mach_freestream": mach,
        "mach_note": "Abaixo de 0,15 o deck sobe a 0,15, como o RANS 2D. O valor pedido fica aqui.",
        "re_mac": reynolds,
        "cruise_altitude_m": float(res.cruise_altitude),
        "cruise_speed_m_s": float(res.cruise_speed),
        "alpha_deg": PLANNED_ALPHAS[0],
        "alpha_note": (
            "α = 0° é o primeiro dos três ângulos já nomeados no caso RANS "
            "(0, 2, 4). Não é um α de cruzeiro equilibrado. Os outros dois não correm."
        ),
    }
    polar_obj = getattr(res, "polar", None)
    highlift = getattr(res, "highlift", None)
    polar = {
        "CD0": _maybe(getattr(polar_obj, "CD0", None)),
        "K": _maybe(getattr(polar_obj, "K", None)),
        "CLmax_clean": _maybe(getattr(highlift, "CLmax_clean", None)),
    }
    reqs = getattr(res.spec, "requirements", None)
    published = list(reqs.keys()) if hasattr(reqs, "keys") else []
    record["l1_polar_scalars"] = polar
    record["wetted_L0_m2"] = {"wing": areas.get("wing"), "fuselage": areas.get("fuselage")}
    comparison = polar_comparison(polar, published)
    record["comparison_l1"] = comparison

    print(f"acdt c172 wf: livre {available:.2f} GB, limite {0.7 * available:.2f} GB", flush=True)
    spec = drop_tails(vsp_spec(res, "c172_wf"))
    record["solid"] = "wing+fuselage"
    record["tails"] = "omitted"
    record["fuselage_note"] = (
        "O corpo é o POD do OpenVSP (comprimento e finura), não um loft do C172. "
        "É a geometria já declarada em geometry.py."
    )
    try:
        info = export_vsp(spec, work, "c172_wf", timeout=600)
    except (OSError, RuntimeError) as exc:
        record["veredicto"] = "nao_avaliado"
        record["model_note"] = f"O sólido não foi exportado ({type(exc).__name__}). Não há coeficientes."
        record["comparison_rows"] = _comparison_rows({}, False)
        _write(dest, record)
        return record
    comp = info.get("compgeom") or {}
    names = [row.get("name") for row in comp.get("components") or []]
    record["vsp_version"] = comp.get("version")
    record["len_unit"] = comp.get("len_unit")
    record["component_names"] = names
    tails_present = any(name in ("Htail", "Vtail") for name in names)
    record["tails_present_in_compgeom"] = tails_present
    if tails_present or not (work / "c172_wf_wing.step").is_file() or not (work / "c172_wf_fuselage.step").is_file():
        record["veredicto"] = "nao_avaliado"
        record["model_note"] = "O STEP de asa e fuselagem, sem caudas, não ficou completo. O SU2 não arrancou."
        record["comparison_rows"] = _comparison_rows({}, False)
        _write(dest, record)
        return record

    caps = cell_caps(available)
    record["cell_caps"] = caps
    mac = float(wing.mac)
    semispan = float(wing.span) / 2.0
    # Start coarser than the cap and refine at most once if the mesh is far below it.
    h = mac / 8.0
    mesh_path = work / "c172_wf.su2"
    mesh_info = None
    last_error = None
    for _attempt in range(3):
        print(f"acdt c172 wf: malha h={h:.4f} m", flush=True)
        try:
            mesh_info = _mesh(work, mesh_path, mac, semispan, h)
        except (OSError, RuntimeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            mesh_info = None
            h *= 1.35
            continue
        print(f"acdt c172 wf: {mesh_info['cells']} células", flush=True)
        guard = mesh_guard(mesh_info["cells"], tools.mem_available_gb())
        mesh_info["guard"] = guard
        mesh_info["h_m"] = h
        if guard["run_here"]:
            break
        h *= 1.35
    record["mesh"] = _public_mesh(mesh_info) if mesh_info else {"error": _short(last_error)}
    if mesh_info is None or not mesh_info.get("guard", {}).get("run_here"):
        record["veredicto"] = "nao_avaliado" if mesh_info is None else "nao_aplicar"
        record["model_note"] = (
            "A malha não foi escrita." if mesh_info is None else
            "A malha escrita não cabe na guarda. O SU2 não arrancou."
        )
        if mesh_info is not None:
            record["mesh_written"] = True
        record["comparison_rows"] = _comparison_rows({}, False)
        _write(dest, record)
        return record
    markers = mesh_info["markers"]
    if markers["aircraft"] < 1 or markers["symmetry"] < 1 or markers["farfield"] < 1:
        record["mesh_written"] = True
        record["veredicto"] = "nao_avaliado"
        record["model_note"] = "A malha não separou aircraft, symmetry e farfield. O SU2 não arrancou."
        record["comparison_rows"] = _comparison_rows({}, False)
        _write(dest, record)
        return record

    record["mesh_written"] = True
    launched = _solve(work, mesh_path.name, record)
    record["solver_started"] = launched["started"]
    record["chunks"] = launched["chunks"]
    record["iterative_ok"] = launched["iterative_ok"]
    record["stop_reason"] = launched["stop_reason"]
    last = launched["last"]
    record["last_iteration"] = last
    record["comparison_rows"] = _comparison_rows(last, launched["iterative_ok"])
    record["veredicto"] = "nao_aplicar"
    record["model_note"] = launched["note"]
    _write(dest, record)
    return record


def _mesh(work: Path, mesh_path: Path, mac: float, semispan: float, h: float) -> dict:
    geo = half_model_geo("c172_wf_wing.step", "c172_wf_fuselage.step", mac, semispan, h)
    tools.run_gmsh(geo, work, "c172_wf.geo", mesh_path, dim=3, timeout=900)
    cells = tools.su2_nelem(mesh_path)
    log = (work / "c172_wf_gmsh.log").read_text(encoding="utf-8", errors="replace")
    import re
    found = re.search(r"ACDT_MARKERS (\d+) (\d+) (\d+)", log)
    if found:
        markers = {
            "aircraft": int(found.group(1)),
            "symmetry": int(found.group(2)),
            "farfield": int(found.group(3)),
        }
    else:
        markers = {"aircraft": 0, "symmetry": 0, "farfield": 0}
    return {"cells": int(cells), "markers": markers, "farfield_c": 12.0}


def _public_mesh(info: dict | None) -> dict:
    if not info:
        return {}
    return {
        "cells": info.get("cells"),
        "h_m": info.get("h_m"),
        "farfield_c": info.get("farfield_c"),
        "markers": info.get("markers"),
        "guard": info.get("guard"),
        "prism_layers": 0,
    }


def _solve(work: Path, mesh_name: str, record: dict) -> dict:
    ref = record["reference"]
    exe = tools.find_exe("SU2_CFD")
    out = {
        "started": False, "chunks": [], "iterative_ok": False, "last": {},
        "stop_reason": "SU2_CFD não está no PATH nem em ACDT_HIFI_BIN",
        "note": "O solver não foi encontrado. Não há coeficientes.",
    }
    if exe is None:
        return out
    available0 = float(record["ram_available_at_launch_GB"])
    limit = 0.7 * available0
    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = str(N_THREADS)
    env["OMP_DYNAMIC"] = "FALSE"
    target = CHUNK_ITERS
    restart = False
    series: list[dict] = []
    wall0 = _now()
    peak_gb = 0.0
    while target <= ITER_CAP:
        if (_now() - wall0) / 60.0 > MAX_TIME_MIN:
            out["stop_reason"] = "o tempo de 45 min esgotou-se antes do bloco seguinte"
            break
        cfg = rans_cfg(
            mesh_name, ref["alpha_deg"], ref["mach_freestream"], ref["re_mac"], ref["mac_m"],
            ref["s_half_m2"], ref["mac_m"], ref["x_ref_m"], iters=target, restart=restart)
        (work / "c172_wf.cfg").write_text(cfg, encoding="utf-8")
        print(f"acdt c172 wf: SU2 até iter {target}, restart={restart}", flush=True)
        out["started"] = True
        t0 = _now()
        holder: dict = {}
        sampler = _peak_sampler(holder)
        try:
            code = tools.run([exe, "c172_wf.cfg"], work, f"su2_chunk_{target}.log", timeout=900, env=env)
        except subprocess.TimeoutExpired:
            code = None
            out["stop_reason"] = f"o bloco até à iteração {target} excedeu 900 s"
            out["chunks"].append({"iter_target": target, "returncode": None, "timeout": True})
            break
        finally:
            sampler["stop"] = True
            sampler["thread"].join(timeout=5)
        seen = holder.get("peak_gb")
        if _finite(seen):
            peak_gb = max(peak_gb, float(seen))
        wall = _now() - t0
        hist = _history_path(work)
        parsed = parse_history(hist) if hist else {"rows": 0, "last": {}}
        series = history_series(hist) if hist else []
        last_iter = _iteration_number(parsed["last"])
        out["chunks"].append({
            "iter_target": target,
            "returncode": code,
            "wall_s": wall,
            "history_rows": parsed["rows"],
            "last_iter": last_iter,
            "peak_working_set_GB": seen,
            "ram_available_GB": tools.mem_available_gb(),
        })
        if _finite(seen) and float(seen) > limit:
            out["stop_reason"] = (
                f"o conjunto de trabalho do SU2 chegou a {float(seen):.2f} GB, "
                f"acima de {limit:.2f} GB"
            )
            out["ram_guard_breached"] = True
            break
        if code != 0:
            out["stop_reason"] = f"SU2_CFD devolveu {code} no bloco até {target}"
            break
        if not (work / "restart_flow.dat").is_file():
            out["stop_reason"] = "o bloco acabou sem restart_flow.dat"
            break
        if cauchy_met({"series": series}):
            out["iterative_ok"] = True
            out["stop_reason"] = "Cauchy de CL, CD e CMy dentro de 2e-6 no último bloco"
            break
        if parsed["rows"] == 0:
            out["stop_reason"] = "o bloco não escreveu uma linha finita de história"
            break
        if target >= ITER_CAP:
            out["stop_reason"] = "o tecto de 8000 iterações esgotou-se sem cumprir o Cauchy"
            break
        restart = True
        # SU2 ITER is the absolute iteration to reach, including iterations already done.
        reached = int(last_iter) if _finite(last_iter) and float(last_iter) > 0 else target
        nxt = max(reached, target) + CHUNK_ITERS
        if nxt <= target:
            nxt = target + CHUNK_ITERS
        if nxt > ITER_CAP:
            target = ITER_CAP
        else:
            target = nxt
    out["peak_working_set_GB"] = peak_gb or None
    out["last"] = series[-1] if series else {}
    if out.get("ram_guard_breached"):
        out["iterative_ok"] = False
    if out["iterative_ok"]:
        out["note"] = (
            "O Cauchy do deck fechou num α. A polar L1 não é esta malha. "
            "Não se aplica factor e os outros dois ângulos não correm."
        )
    elif out["started"]:
        out["note"] = out["stop_reason"] + ". Os coeficientes, se existirem, não validam o L1."
    return out


def _iteration_number(last: dict):
    for key in ("Inner_Iter", "Iter", "ITER"):
        if key in last and _finite(last[key]):
            return last[key]
    return None


def _history_path(work: Path) -> Path | None:
    for name in ("history.csv", "history.dat", "history"):
        path = work / name
        if path.is_file():
            return path
    return None


def _peak_sampler(holder: dict) -> dict:
    """Sample SU2_CFD's working set while ``tools.run`` blocks."""
    import threading
    state = {"stop": False}

    def loop():
        while not state["stop"]:
            seen = _image_working_set_gb("SU2_CFD.exe")
            if _finite(seen):
                holder["peak_gb"] = max(float(holder.get("peak_gb") or 0.0), float(seen))
            if state["stop"]:
                break
            threading.Event().wait(2.0)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    state["thread"] = thread
    return state


def _image_working_set_gb(exe_name: str):
    """Working set of processes named ``exe_name``. Null when it cannot be read."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    count = 4096
    pids = (wintypes.DWORD * count)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(ctypes.byref(pids), ctypes.sizeof(pids), ctypes.byref(needed)):
        return None
    n = min(count, needed.value // ctypes.sizeof(wintypes.DWORD))

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    total = 0
    found = False
    access = 0x1000 | 0x0010
    for index in range(n):
        pid = int(pids[index])
        if pid <= 0:
            continue
        handle = kernel.OpenProcess(access, False, pid)
        if not handle:
            continue
        try:
            buf = ctypes.create_unicode_buffer(520)
            size = wintypes.DWORD(len(buf))
            if not kernel.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                continue
            if Path(buf.value).name.lower() != exe_name.lower():
                continue
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                continue
            total += int(counters.WorkingSetSize)
            found = True
        finally:
            kernel.CloseHandle(handle)
    if not found:
        return None
    return total / 1024**3


def _write(dest: Path, record: dict) -> None:
    rows = record.get("comparison_rows") or _comparison_rows({}, False)
    record["comparison_rows"] = rows
    scrubbed = _sanitize(_scrub_obj(record))
    record.clear()
    record.update(scrubbed)
    text = json.dumps(record, indent=1, ensure_ascii=False, allow_nan=False)
    record["path_leak"] = _forbidden_path(text)
    (dest / RESULT_JSON).write_text(
        json.dumps(record, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    write_summary_csv(dest / RESULT_CSV, rows)


def _scrub(text: str) -> str:
    import re
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']*", "[path]", text)
    return text.replace("acdt-tools", "[tools]")


def _scrub_obj(value):
    if isinstance(value, str):
        return _scrub(value)
    if isinstance(value, dict):
        return {key: _scrub_obj(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_obj(item) for item in value]
    return value


def _sanitize(value):
    """Drop non-finite floats. NaN is not a coefficient and not valid JSON."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _forbidden_path(text: str) -> bool:
    import re
    return bool(re.search(r"[A-Za-z]:[\\/]", text)) or "acdt-tools" in text


def _short(text: str | None) -> str | None:
    if text is None:
        return None
    return text[-500:]


def _now() -> float:
    import time
    return time.perf_counter()
