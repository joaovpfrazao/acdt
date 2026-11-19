# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Published turbojet viewer versus the L0 correlation, and the missing L1 deck.

The acdt process does not import pycycle. The numbers come from the stdout of
the unmodified ``example_cycles/simple_turbojet.py`` at tag 4.4.0
(Hendricks and Gray, Aerospace 2019, 6, 87, doi 10.3390/aerospace6080087).

``engine_map`` stores a user table. It is not a cycle deck. No table of this
turbojet is in the repository, so the L1 comparison stays ``nao_avaliado``.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from acdt.core.units import to_si
from acdt.domains.aircraft.hifi.wing_bl import H1_RATIO_BAND, factor_record, h1_factor_decision
from acdt.domains.aircraft.jet.turbofan import turbofan_point

# Inputs of the published script. The viewer prints Mach with five decimals, so
# 1e-6 becomes 0.00000. The L0 query uses these inputs, not the rounded print.
PUBLISHED_POINTS = {
    "DESIGN": {"mach": 1e-6, "alt_ft": 0.0, "Fn_target_lbf": 11800.0,
               "T4_target_degR": 2370.0, "comp_PR": 13.5, "comp_eff": 0.83, "turb_eff": 0.86},
    "OD0": {"mach": 1e-6, "alt_ft": 0.0, "Fn_target_lbf": 11000.0},
    "OD1": {"mach": 0.2, "alt_ft": 5000.0, "Fn_target_lbf": 8000.0},
}
PUBLISHED_URL = "https://raw.githubusercontent.com/OpenMDAO/pyCycle/4.4.0/example_cycles/simple_turbojet.py"

# Fields validate_engine_map accepts. None of them are stored for this turbojet.
TABLE_FIELDS = (
    "source", "mach", "altitude_m", "throttle",
    "thrust_lapse", "thrust_installed_N", "TSFC_kg_N_s",
)
CORRECTED_FIELDS = (
    "source", "mach", "altitude_m", "throttle",
    "F_over_delta", "SFC_over_sqrt_theta", "totals",
)
# Printed by the published viewer and absent from engine_map.
CYCLE_FIELDS_NOT_IN_THE_MAP = (
    "OPR", "W", "Fg", "Fram", "FAR", "Wfuel", "T4", "comp_eff", "turb_eff",
    "Nmech", "station tot:P", "station tot:T",
)

_POINT = re.compile(r"POINT:\s+(\S+)")
_ROW = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+"
    r"([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+"
    r"([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+"
    r"([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s*$"
)
_COLS = ("Mach_printed", "Alt_ft", "W_lbm_s", "Fn_lbf", "Fg_lbf", "Fram_lbf", "OPR", "TSFC_lbm_lbf_h")
RESULT_JSON = "h8_pycycle_sem_ajuste.json"
RESULT_CSV = "h8_pycycle_sem_ajuste.csv"


def missing_l1_deck() -> dict:
    """Exact gap. An empty map is not filled with zeros, and L0 is not renamed L1."""
    return {
        "l1_thermodynamic_deck_present": False,
        "status": "nao_avaliado",
        "source": "src/acdt/domains/aircraft/jet/engine_map.py and jet/turbofan.py",
        "why": (
            "engine_map declara que não há deck de ciclo e não corre pyCycle, NPSS, "
            "GasTurb, T-MATS nem CFD. Sem mapa, engine_point chama turbofan_point, "
            "que é a correlação L0. Não existe no repositório uma grelha table nem "
            "corrected_table deste turbojato."
        ),
        "table_fields_accepted_and_absent": list(TABLE_FIELDS),
        "corrected_table_fields_accepted_and_absent": list(CORRECTED_FIELDS),
        "cycle_fields_the_map_cannot_store": list(CYCLE_FIELDS_NOT_IN_THE_MAP),
        "illustrative_map_not_this_engine": (
            "examples/jet/engine_map_table.yaml é uma tabela PRESSUPOSTO de transporte, "
            "amostrada da correlação L0. Não é o turbojato de PR 13,5 e T4 2370 R, "
            "e não foi editada."
        ),
        "l0_not_relabelled": True,
    }


def parse_viewer(text: str) -> dict[str, dict[str, str]]:
    """Performance rows of the published viewer. Tokens stay strings."""
    current = None
    found: dict[str, dict[str, str]] = {}
    for raw in text.splitlines():
        point = _POINT.search(raw)
        if point:
            current = point.group(1)
            continue
        match = _ROW.match(raw)
        if current and match and current not in found:
            found[current] = dict(zip(_COLS, match.groups()))
    return found


def _num(token):
    if token in (None, ""):
        return None
    try:
        value = float(token)
    except (TypeError, ValueError):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _reported(hifi, lowfi):
    if hifi is None or lowfi in (None, 0) or lowfi == 0.0:
        return None, None
    try:
        ratio = float(hifi) / float(lowfi)
    except (TypeError, ValueError, ZeroDivisionError):
        return None, None
    lo, hi = H1_RATIO_BAND
    return ratio, bool(lo <= ratio <= hi)


def compare_points(printed: dict[str, dict[str, str]]) -> dict:
    """TSFC ratio versus turbofan_point. Different engine class: not the same quantity.

    Commanded turbojet thrust and the L0 maximum-rating thrust are not ratioed.
    A missing print stays missing.
    """
    rows = []
    decisions = []
    for name, spec in PUBLISHED_POINTS.items():
        row = printed.get(name) or {}
        alt_m = to_si(float(spec["alt_ft"]), "ft", "length")
        low = turbofan_point(float(spec["mach"]), alt_m)
        tsfc_h = _num(row.get("TSFC_lbm_lbf_h"))
        tsfc_l = low["TSFC_lb_lbf_h"]
        decision = h1_factor_decision(
            tsfc_h, tsfc_l, same_quantity=False, quantity=f"TSFC_{name}",
            why=("O TSFC do turbojato publicado e o TSFC da correlação L0 de "
                 "turbofan de alta razão de bypass são classes de motor diferentes."))
        ratio, inside = _reported(tsfc_h, tsfc_l)
        decision["reported_ratio"] = ratio
        decision["reported_ratio_inside_band"] = inside
        decision["band_is_not_an_apply_gate"] = True
        stored = factor_record(decision)
        stored["reported_ratio"] = ratio
        stored["reported_ratio_inside_band"] = inside
        decisions.append(stored)
        rows.append({
            "point": name,
            "mach_input": spec["mach"],
            "alt_ft_input": spec["alt_ft"],
            "alt_m": alt_m,
            "Fn_target_lbf": spec["Fn_target_lbf"],
            "printed": {key: row.get(key) for key in _COLS} if row else None,
            "Fn_printed_lbf": _num(row.get("Fn_lbf")),
            "TSFC_printed": tsfc_h,
            "L0_TSFC_lb_lbf_h": tsfc_l,
            "L0_thrust_installed_N": low["thrust_installed_N"],
            "L0_thrust_note": (
                "Empuxo L0 à classificação máxima, com thrust_sl_N por omissão. "
                "O Fn do pyCycle é o alvo comandado. Não se forma razão de empuxo."
            ),
            "decision": decision,
        })
    present = [row for row in rows if row["TSFC_printed"] is not None]
    return {
        "overall": "nao_aplicar",
        "valid": False,
        "applied": False,
        "same_engine": False,
        "model_L0": "nao_aplicar",
        "model_L1": "nao_avaliado",
        "model_note": (
            "A correlação L0 não fica validada nem calibrada: a razão de TSFC é "
            "uma diferença de classe de motor. O deck termodinâmico L1 não existe, "
            "por isso essa comparação fica nao_avaliado. O yaml não muda."
        ),
        "points_printed": len(present),
        "points_expected": len(PUBLISHED_POINTS),
        "rows": rows,
        "factors": decisions,
    }


def write_csv(path: Path, comparison: dict) -> None:
    fields = ["point", "Mach_printed", "Alt_ft", "W_lbm_s", "Fn_lbf", "Fg_lbf", "Fram_lbf",
              "OPR", "TSFC_lbm_lbf_h", "L0_TSFC_lb_lbf_h", "TSFC_reported_ratio"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore", restval="")
        writer.writeheader()
        for row in comparison["rows"]:
            printed = row["printed"] or {}
            writer.writerow({
                "point": row["point"],
                "Mach_printed": printed.get("Mach_printed", ""),
                "Alt_ft": printed.get("Alt_ft", ""),
                "W_lbm_s": printed.get("W_lbm_s", ""),
                "Fn_lbf": printed.get("Fn_lbf", ""),
                "Fg_lbf": printed.get("Fg_lbf", ""),
                "Fram_lbf": printed.get("Fram_lbf", ""),
                "OPR": printed.get("OPR", ""),
                "TSFC_lbm_lbf_h": printed.get("TSFC_lbm_lbf_h", ""),
                "L0_TSFC_lb_lbf_h": "" if row["L0_TSFC_lb_lbf_h"] is None else f"{row['L0_TSFC_lb_lbf_h']:.8g}",
                "TSFC_reported_ratio": "" if row["decision"]["reported_ratio"] is None else f"{row['decision']['reported_ratio']:.8g}",
            })


def build_record(stdout: str, *, today: str, branch: str | None, versions: dict,
                 returncode: int, wall_s: float, estimate: dict, script_sha256: str) -> dict:
    printed = parse_viewer(stdout)
    comparison = compare_points(printed)
    plot_failed = "plot_compressor_maps" in stdout and returncode != 0
    return {
        "date": today,
        "branch": branch,
        "decision": "nao_aplicar",
        "valid": False,
        "applied": False,
        "model_L0": "nao_aplicar",
        "model_L1": "nao_avaliado",
        "example_yaml_edited": False,
        "imported_by_acdt": False,
        "local_source_patch": False,
        "published_example": "OpenMDAO/pyCycle tag 4.4.0, example_cycles/simple_turbojet.py",
        "published_example_host": "raw.githubusercontent.com",
        "published_example_path": "OpenMDAO/pyCycle/4.4.0/example_cycles/simple_turbojet.py",
        "published_example_sha256": script_sha256,
        "versions": versions,
        "returncode": returncode,
        "plot_failed_after_solution": plot_failed,
        "plot_note": (
            "O script publicado chama map_plots depois de imprimir os três pontos. "
            "Neste venv o matplotlib não está instalado e plot_compressor_maps "
            "termina com AttributeError. A solução impressa fica; o gráfico não foi produzido."
        ),
        "numpy_deprecation": (
            "NumPy 1.26 avisa, na linha de impressão, que converter um vector de "
            "ndim > 0 em escalar está descontinuado. Não é um TypeError. O código "
            "do pyCycle não foi editado."
        ),
        "wall_s": wall_s,
        "estimate": estimate,
        "design_inputs": PUBLISHED_POINTS["DESIGN"],
        "points": comparison["rows"],
        "comparison": {
            "overall": comparison["overall"],
            "same_engine": False,
            "model_note": comparison["model_note"],
            "factors": comparison["factors"],
        },
        "l1_deck": missing_l1_deck(),
        "prior_patched_run": "examples/output/jet_pycycle/h8_pycycle.json",
        "csv": RESULT_CSV,
        "citations": [
            "Hendricks and Gray, Aerospace 2019, 6, 87, doi 10.3390/aerospace6080087",
            "Mattingly, Heiser and Pratt 2002, Ch. 2",
            "Ihme 2025, Eq. 2.77",
            "NIST SP 811, 2008, Appendix B, via acdt.core.units: 1 ft = 0.3048 m",
        ],
    }


def write_record(stdout: str, dest: Path, **kwargs) -> dict:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    record = build_record(stdout, **kwargs)
    (dest / RESULT_JSON).write_text(
        json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(dest / RESULT_CSV, compare_points(parse_viewer(stdout)))
    return record
