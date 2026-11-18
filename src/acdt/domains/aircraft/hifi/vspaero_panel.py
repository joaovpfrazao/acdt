# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Thick-panel VSPAERO of the tailless wing, compared with the two-section AVL card.

The acdt process does not import ``openvsp``. Geometry and the solver run through
:func:`acdt.domains.aircraft.hifi.geometry.export_vsp` in ``ACDT_VSP_PYTHON``.
The wake map is the live default of OpenVSP 3.56 (WakeNumIter 5, NumWakeNodes 8,
WakeRelax 1, FixedWakeFlag 0, ImplicitWake 0), written explicitly and read back.
OpenVSP 3.45.0 (changelog, 2025-07-18) describes the implicit wake as an adjoint
coupling of vortex strength and wake position, and records that explicit-wake
convergence was also improved. ImplicitWake stays 0: this case is the explicit wake.

The 3.46.0 changelog line "Fix TE wake detection for VSPAERO" is not used as the
cause. That release note does not describe this wing, and the wing has no body.
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

from .geometry import export_vsp, flying_wing_vsp_spec
from .wing_bl import (
    DOCUMENTED_S_M2,
    H1_RATIO_BAND,
    cruise_state,
    factor_record,
    h1_factor_decision,
    mac_quarter_chord,
    reference_quantities,
    run_avl_cruise,
    scaled_wing,
)
from . import tools

# Live defaults read from VSPAEROSweep on OpenVSP 3.56.0. Not a retune.
DOCUMENTED_WAKE = {
    "WakeNumIter": 5,
    "NumWakeNodes": 8,
    "WakeRelax": 1.0,
    "FixedWakeFlag": 0,
    "ImplicitWake": 0,
}

# Ceiling carried from the thin-lattice record. Not a measurement of the panel mesh.
RAM_ESTIMATE_GB = 0.8
TIME_ESTIMATE_MIN = 20.0

_MULTIWORD = (("L2 Residual", "L2_Residual"), ("Max Residual", "Max_Residual"))
COEFFICIENTS = (
    "Iter", "Mach", "AoA", "CLtot", "CDo", "CDi", "CDtot", "CMytot",
    "CLiw", "CDiw", "L2_Residual", "Max_Residual",
)
DESIGN = "uav150_flying_wing_tailless"
RESULT_JSON = "h7_vspaero_painel.json"
RESULT_CSV = "h7_vspaero_painel.csv"


def parse_history(text: str) -> dict:
    """Split a VSPAERO ``.history`` file. Coefficients stay tokens until :func:`_num`.

    Header names ``L2 Residual`` and ``Max Residual`` are joined before the split.
    A data row whose width differs from the header is skipped, not padded with zeros.
    """
    reference: dict[str, str] = {}
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    if not text:
        return {"reference": reference, "columns": [], "rows": rows}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("*") or line.startswith("Solver"):
            continue
        if header is None and line.startswith("Iter"):
            folded = line
            for src, dst in _MULTIWORD:
                folded = folded.replace(src, dst)
            header = folded.split()
            continue
        if header is None:
            parts = line.split()
            if len(parts) >= 2 and parts[0].endswith("_"):
                reference[parts[0]] = parts[1]
            continue
        parts = line.split()
        if len(parts) != len(header):
            continue
        rows.append(dict(zip(header, parts)))
    return {"reference": reference, "columns": header or [], "rows": rows}


def _num(row: dict | None, key: str):
    if not row or key not in row or row[key] in (None, ""):
        return None
    try:
        value = float(row[key])
    except (TypeError, ValueError):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _reported_ratio(hifi, lowfi):
    if hifi is None or lowfi is None:
        return None, None
    try:
        hf, lf = float(hifi), float(lowfi)
    except (TypeError, ValueError):
        return None, None
    if lf == 0.0 or hf != hf or lf != lf:
        return None, None
    ratio = hf / lf
    lo, hi = H1_RATIO_BAND
    return ratio, bool(lo <= ratio <= hi)


def wake_residual_note(rows: list[dict]) -> dict:
    """Five default wake iterations are not a converged solution.

    No cited stop criterion is applied as a pass. ``converged`` stays false.
    """
    last = rows[-1] if rows else None
    prev = rows[-2] if len(rows) >= 2 else None
    l2_last = _num(last, "L2_Residual")
    l2_prev = _num(prev, "L2_Residual")
    cl_last = _num(last, "CLtot")
    cl_prev = _num(prev, "CLtot")
    return {
        "converged": False,
        "iterative_ok": False,
        "n_rows": len(rows),
        "L2_last": l2_last,
        "L2_previous": l2_prev,
        "dCL_last_step": None if cl_last is None or cl_prev is None else cl_last - cl_prev,
        "reason": (
            "WakeNumIter fica no default 5. O residual L2 da última iteração ainda muda. "
            "Não há critério de paragem citado que declare esta corrida convergida."
        ),
    }


def compare_with_avl(last: dict | None, avl: dict, *, iterative_ok: bool = False) -> dict:
    """CL and Cm use :func:`h1_factor_decision`. Drag ratios are reported and are not the same quantity.

    One angle, a residual that is still moving, and a different lattice stay ``nao_aplicar``.
    A missing coefficient stays missing: it is not stored as zero and it is not a pass.
    """
    last = last or {}
    why_point = (
        "um α; a polar não foi avaliada; o residual da esteira não está parado; "
        "não há GCI"
    )
    cl_h, cm_h = _num(last, "CLtot"), _num(last, "CMytot")
    cl = h1_factor_decision(
        cl_h, avl.get("CL"), same_quantity=True,
        iterative_ok=iterative_ok, gci_defined=False, quantity="CL",
        why=why_point if cl_h is not None and avl.get("CL") is not None else None)
    cm = h1_factor_decision(
        cm_h, avl.get("Cmtot"), same_quantity=True,
        iterative_ok=iterative_ok, gci_defined=False, quantity="Cm",
        why=why_point if cm_h is not None and avl.get("Cmtot") is not None else None)
    cdi = h1_factor_decision(
        _num(last, "CDi"), avl.get("CDff"), same_quantity=False, quantity="CDi",
        why="O CDi de integração de superfície do VSPAERO é outra grandeza que o CDff do AVL.")
    cdiw = h1_factor_decision(
        _num(last, "CDiw"), avl.get("CDff"), same_quantity=False, quantity="CDiw",
        why="O CDiw da esteira é outra grandeza que o CDff do AVL.")
    cdtot = h1_factor_decision(
        _num(last, "CDtot"), avl.get("CDtot"), same_quantity=False, quantity="CDtot",
        why="O CDtot do VSPAERO inclui o CDo. O CDtot do AVL é outra grandeza.")
    for dec, hifi_key, low_key in (
        (cdi, "CDi", "CDff"), (cdiw, "CDiw", "CDff"), (cdtot, "CDtot", "CDtot"),
    ):
        ratio, inside = _reported_ratio(_num(last, hifi_key), avl.get(low_key))
        dec["reported_ratio"] = ratio
        dec["reported_ratio_inside_band"] = inside
        dec["band_is_not_an_apply_gate"] = True
    cl_s, cm_s = _num(last, "CLtot"), _num(last, "CMytot")
    avl_cl, avl_cm = avl.get("CL"), avl.get("Cmtot")
    if None in (cl_s, cm_s, avl_cl, avl_cm):
        moment_sign = None
    elif cl_s == 0.0 or cm_s == 0.0 or avl_cl == 0.0 or avl_cm == 0.0:
        moment_sign = None
    else:
        moment_sign = "same" if (cm_s > 0) == (float(avl_cm) > 0) else "opposite"
    parts = [
        "O modelo L1, o AVL de duas secções, não fica validado e não é calibrado.",
        "Um α e malhas diferentes (painel 41×16, AVL nchord 12 e nspan 40) não aplicam factor.",
    ]
    if cdi.get("reported_ratio_inside_band") is False:
        parts.append("A razão informativa CDi/CDff fica fora de [0.7, 1.5].")
    if cdiw.get("reported_ratio_inside_band") is False:
        parts.append("A razão informativa CDiw/CDff fica fora de [0.7, 1.5].")
    factors = []
    for dec in (cl, cm, cdi, cdiw, cdtot):
        stored = factor_record(dec)
        if "reported_ratio" in dec:
            stored["reported_ratio"] = dec["reported_ratio"]
            stored["reported_ratio_inside_band"] = dec["reported_ratio_inside_band"]
        factors.append(stored)
    return {
        "overall": "nao_aplicar",
        "valid": False,
        "applied": False,
        "model_L1": "nao_aplicar",
        "model_note": " ".join(parts),
        "same_lattice": False,
        "same_geometry_family": True,
        "moment_sign": moment_sign,
        "h1_band_not_an_apply_gate": True,
        "CL": cl,
        "Cm": cm,
        "CDi_vs_CDff": cdi,
        "CDiw_vs_CDff": cdiw,
        "CDtot_vs_AVL_CDtot": cdtot,
        "factors": factors,
    }


def thick_vspaero_block(ref: dict, state: dict, x_ref: float, alpha_deg: float, ncpu: int = 4) -> dict:
    """Case block for ``vsp_build``. StallModel stays 0 inside the build script."""
    return {
        "surface": "thick",
        "alpha_deg": float(alpha_deg),
        "mach": float(state["Mach"]),
        "sref": float(ref["S_m2"]),
        "bref": float(ref["Bref_m"]),
        "cref": float(ref["Cref_m"]),
        "xcg": float(x_ref),
        "ycg": 0.0,
        "zcg": 0.0,
        "re_cref": float(state["Re_Cref"]),
        "ncpu": int(ncpu),
        "wake": dict(DOCUMENTED_WAKE),
    }


def write_iteration_csv(path: Path, rows: list[dict]) -> None:
    """Iteration table. A missing column is an empty field, not a zero."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(COEFFICIENTS), extrasaction="ignore", restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in COEFFICIENTS})


def _git_branch(start: Path):
    start = Path(start)
    if start.is_file():
        start = start.parent
    try:
        proc = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _wing_readback(compgeom: dict) -> dict | None:
    for row in compgeom.get("readback") or []:
        if row.get("name") == "Wing":
            return row
    return None


def nonfinite_columns(row: dict | None) -> list[str]:
    """Column names whose token is not a finite float. An empty token is missing, not non-finite."""
    bad = []
    for key in COEFFICIENTS:
        if not row or key not in row or row[key] in (None, ""):
            continue
        try:
            value = float(row[key])
        except (TypeError, ValueError):
            bad.append(key)
            continue
        if value != value or value in (float("inf"), float("-inf")):
            bad.append(key)
    return bad


def _last_numbers(row: dict | None) -> dict:
    out = {}
    for key in COEFFICIENTS:
        out[key] = _num(row, key)
    return out


def run_thick_panel(work: Path, dest: Path, *, today: str) -> dict:
    """Run the coarse thick panel and the AVL card. Write JSON and CSV under ``dest``.

    Mesh files stay in ``work``. The example YAML is not edited. A budget refusal
    or a missing AVL angle writes the record and does not launch VSPAERO.
    """
    work = Path(work)
    dest = Path(dest)
    work.mkdir(parents=True, exist_ok=True)
    dest.mkdir(parents=True, exist_ok=True)
    avail = tools.mem_available_gb()
    guard = tools.budget(RAM_ESTIMATE_GB, TIME_ESTIMATE_MIN, max_time_min=TIME_ESTIMATE_MIN)
    disk = shutil.disk_usage(work).free / 1024**3
    surf, scale = scaled_wing()
    ref = reference_quantities(surf)
    # The documented area is the AVL Sref. reference_quantities uses the loft planform.
    ref = dict(ref)
    ref["S_m2"] = float(scale["S_m2"])
    if abs(ref["S_m2"] - DOCUMENTED_S_M2) > 1e-9:
        raise RuntimeError("a área documentada não chegou ao cartão")
    state = cruise_state(ref)
    x_ref = float(mac_quarter_chord(surf)["x_ref_m"])
    avl = run_avl_cruise(work / "avl", surf, ref, state, x_ref)
    branch = _git_branch(Path(__file__))
    base = {
        "design": DESIGN,
        "date": today,
        "branch": branch,
        "decision": "nao_aplicar",
        "valid": False,
        "applied": False,
        "model_L1": "nao_aplicar",
        "example_yaml_edited": False,
        "windows_openvsp": True,
        "surface": "thick",
        "stall_model": 0,
        "documented_wake_requested": dict(DOCUMENTED_WAKE),
        "prior_panel_failure": {
            "source": "examples/output/uav150_flying_wing_tailless_hifi_win/h7_openvsp.json",
            "openvsp": "OpenVSP 3.48.2",
            "error": "Could not find global edge for trailing wake. Nodes 1363 and 1364.",
            "history": False,
            "used_for_these_coefficients": False,
        },
        "resolution_note": (
            "OpenVSP 3.56.0 no Windows, conjunto grosso, com WakeNumIter, NumWakeNodes, "
            "WakeRelax, FixedWakeFlag e ImplicitWake escritos e lidos de volta. "
            "A linha do CHANGELOG 3.46.0, «Fix TE wake detection for VSPAERO», não é tomada "
            "como causa: a nota não descreve esta asa, e a asa não tem corpo. "
            "A diferença de versão fica registada."
        ),
        "citations": [
            "McDonald and Gloudemans, Open Vehicle Sketch Pad, AIAA 2022-0004",
            "OpenVSP 3.45.0 changelog, 2025-07-18: implicit wake couples vortex strength and wake position through the adjoint; explicit-wake convergence was also improved. ImplicitWake is left at 0.",
            "OpenVSP 3.46.0 changelog lists «Fix TE wake detection for VSPAERO» and does not describe this wing.",
            "Drela and Youngren, AVL 3.40, avl_doc.txt",
        ],
        "estimate": {
            "ram_available_GB": avail,
            "limit_GB": 0.7 * avail,
            "ram_estimate_GB": RAM_ESTIMATE_GB,
            "ram_estimate_is_a_ceiling": True,
            "ram_estimate_source": "teto do registo VSPAERO fino; não é uma medição desta malha de painéis",
            "disk_free_GB": disk,
            "time_estimate_min": TIME_ESTIMATE_MIN,
            "budget_run_here": guard.run_here,
            "budget_reason": guard.reason,
        },
        "reference": {
            "sref_m2": ref["S_m2"],
            "bref_m": ref["Bref_m"],
            "cref_m": ref["Cref_m"],
            "xcg_m": x_ref,
            "mach": state["Mach"],
            "re_cref": state["Re_Cref"],
            "re_cref_note": "Escrito no caso. StallModel 0, por isso a solução não é viscosa.",
            "alpha_deg": avl.get("alpha_deg"),
            "alpha_source": "AVL externo, cartão de duas secções, nesta corrida",
        },
        "avl_two_section": {
            "available": avl.get("available"),
            "source": avl.get("source"),
            "alpha_deg": avl.get("alpha_deg"),
            "CLtot": avl.get("CL"),
            "CDff": avl.get("CDff"),
            "Cmtot": avl.get("Cmtot"),
            "CDtot": avl.get("CDtot"),
            "Xref": avl.get("Xref"),
            "Sref": avl.get("Sref"),
            "Cref": avl.get("Cref"),
            "Bref": avl.get("Bref"),
            "Mach": avl.get("Mach"),
            "nchord": avl.get("nchord"),
            "nspan": avl.get("nspan"),
            "note": "O cartão de quatro secções do estudo de controlos é outra discretização e não entra nesta comparação.",
        },
    }
    json_path = dest / RESULT_JSON
    csv_path = dest / RESULT_CSV
    if not guard.run_here:
        base["vspaero_run"] = False
        base["model_note"] = "A guarda de 70 % da RAM livre recusou a corrida. Não há coeficientes."
        base["comparison"] = compare_with_avl(None, avl, iterative_ok=False)
        json_path.write_text(json.dumps(base, indent=1, ensure_ascii=False), encoding="utf-8")
        write_iteration_csv(csv_path, [])
        return base
    if not avl.get("available") or avl.get("alpha_deg") is None:
        base["vspaero_run"] = False
        base["model_note"] = "O AVL não devolveu α. O VSPAERO não foi lançado: o ângulo não é inventado."
        base["comparison"] = compare_with_avl(None, avl, iterative_ok=False)
        json_path.write_text(json.dumps(base, indent=1, ensure_ascii=False), encoding="utf-8")
        write_iteration_csv(csv_path, [])
        return base
    spec = flying_wing_vsp_spec(surf, "wing")
    spec["vspaero"] = thick_vspaero_block(ref, state, x_ref, avl["alpha_deg"])
    info = export_vsp(spec, work, "wing")
    comp = info["compgeom"]
    solved = comp.get("vspaero") or {}
    history_path = work / "wing.history"
    if history_path.is_file():
        history_text = history_path.read_text(encoding="utf-8", errors="replace")
    else:
        history_text = solved.get("history") or ""
    parsed = parse_history(history_text)
    rows = parsed["rows"]
    missing = [key for key in COEFFICIENTS if rows and key not in rows[0]]
    residual = wake_residual_note(rows)
    tokens = rows[-1] if rows and not missing else None
    bad = nonfinite_columns(tokens)
    last = None if bad else tokens
    comparison = compare_with_avl(last, {
        "CL": avl.get("CL"), "CDff": avl.get("CDff"),
        "Cmtot": avl.get("Cmtot"), "CDtot": avl.get("CDtot"),
    }, iterative_ok=False)
    inputs = solved.get("inputs") or {}
    base.update({
        "vspaero_run": True,
        "openvsp": comp.get("version"),
        "vspaero_solver": solved.get("solver"),
        "vsp_python": Path(tools.vsp_python()).name if tools.vsp_python() else None,
        "returncode": solved.get("returncode"),
        "vspaero_error": comp.get("vspaero_error"),
        "geometry_wall_s": solved.get("geometry_wall_s"),
        "solver_wall_s": solved.get("sweep_wall_s"),
        "wake_applied": solved.get("wake_applied"),
        "wake_skipped": solved.get("wake_skipped"),
        "inputs_read_back": inputs,
        "history_reference": parsed["reference"],
        "mesh_geoms_removed": solved.get("mesh_geoms_removed"),
        "mesh_note": (
            "ComputeCompGeom deixa geoms do tipo Mesh no veículo. No conjunto grosso, "
            "SET_ALL incluía esses geoms e a história saía não finita. São apagados "
            "antes do VSPAERO. O conjunto grosso continua GeomSet SET_ALL e "
            "ThinGeomSet SET_NONE sobre a geometria de projecto. O caminho fino não mexe neles."
        ),
        "history_columns_missing": missing,
        "nonfinite_columns": bad,
        "n_history_rows": len(rows),
        "residual": residual,
        "last_iteration_tokens": {key: tokens.get(key) for key in COEFFICIENTS} if tokens else None,
        "last_iteration": _last_numbers(last) if last else None,
        "wing_readback": _wing_readback(comp),
        "len_unit": comp.get("len_unit"),
        "len_unit_metre": comp.get("len_unit_metre"),
        "comparison": comparison,
        "model_note": comparison["model_note"],
        "csv": RESULT_CSV,
        "rho_vinf_note": (
            "Rho_ e Vinf_ são os valores do cabeçalho do .history. "
            "StallModel 0, por isso não escalam o CL invíscido. "
            "A densidade por omissão não é tratada como kg/m3."
        ),
    })
    if bad or solved.get("returncode") not in (0, None) or not rows or missing or solved.get("returncode") is None:
        base["decision"] = "nao_aplicar"
        base["model_L1"] = "nao_aplicar"
        if solved.get("stderr_tail"):
            base["stderr_tail"] = solved.get("stderr_tail")
        if bad:
            base["model_note"] = (
                "A história tem valores não finitos em "
                + ", ".join(bad)
                + ". Não há coeficientes e o resultado não é um passa."
            )
        elif not rows:
            base["model_note"] = (
                "O VSPAERO não escreveu uma história utilizável. "
                "Não há coeficientes e o resultado não é um passa."
            )
    elif solved.get("returncode") == 0:
        base["decision"] = "nao_aplicar"
        base["model_L1"] = "nao_aplicar"
    base["estimate"]["geometry_wall_s"] = solved.get("geometry_wall_s")
    base["estimate"]["solver_wall_s"] = solved.get("sweep_wall_s")
    json_path.write_text(json.dumps(base, indent=1, ensure_ascii=False), encoding="utf-8")
    write_iteration_csv(csv_path, rows if not missing else [])
    return base
