# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Wing-plus-fuselage RANS estimate and the compute guard. SU2 is not started.

The cell count is :func:`acdt.domains.aircraft.hifi.cfd3d.rans_volume_estimate`,
the same arithmetic as ``full_aircraft_rans_case``. There is no wing-plus-fuselage
solid, so this module does not write a mesh. A missing coefficient stays missing.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .cfd3d import rans_volume_estimate
from .tools import mem_available_gb

RESULT_JSON = "h5_c172_rans_asa_fuselagem.json"
RESULT_CSV = "h5_c172_rans_asa_fuselagem.csv"
# Prior hex-mesh rate, flying wing, recorded in h5_c172_gci.json. Not measured here.
PRIOR_MEASURED_RATE_S = 1.63e-5
QUANTITIES = ("CL", "CD", "Cm")


def estimate_wing_fuselage(res) -> dict:
    """Wing and fuselage wetted area only, through the existing volume formula."""
    from ....core.atmosphere import isa
    from .cfd import first_cell

    wing = res.config.wing
    areas = res.config.wetted_areas()
    at = isa(res.cruise_altitude)
    reynolds = at.rho * res.cruise_speed * wing.mac / at.mu
    first = first_cell(reynolds, wing.mac, 1.0)
    estimate = rans_volume_estimate(areas["wing"] + areas["fuselage"], wing.mac, first)
    estimate["Re_mac"] = reynolds
    estimate["first_cell_m"] = first
    estimate["wetted_m2"] = {"wing": areas["wing"], "fuselage": areas["fuselage"]}
    estimate["components"] = "wing+fuselage"
    estimate["solid"] = "ausente"
    estimate["solid_note"] = (
        "Não há sólido só de asa e fuselagem. A conta não escreve malha nem .geo."
    )
    estimate["prism_layer_checked"] = False
    estimate["prior_measured_rate_s_per_cell_iter_per_thread"] = PRIOR_MEASURED_RATE_S
    estimate["prior_measured_rate_note"] = (
        "PRESSUPOSTO: 1,63e-5 s/célula/iteração por thread é a taxa da malha hex da "
        "asa voadora. Não foi medida nesta malha."
    )
    estimate["wall_h_6threads_prior_rate"] = (
        estimate["wall_h"] * (PRIOR_MEASURED_RATE_S / 4e-6) * (8.0 / 6.0)
    )
    return estimate


def computation_guard(ram_gb: float, wall_h: float, *, available_gb: float | None = None,
                      max_time_min: float = 45.0) -> dict:
    """Same two checks as ``tools.budget``. A refusal does not start the solver."""
    available = mem_available_gb() if available_gb is None else float(available_gb)
    limit = 0.7 * available
    time_min = float(wall_h) * 60.0
    reasons = []
    if float(ram_gb) > limit:
        reasons.append(
            f"memória estimada {ram_gb:.1f} GB > 70 % de {available:.1f} GB disponíveis"
        )
    if time_min > max_time_min:
        reasons.append(
            f"tempo estimado {time_min:.0f} min > limite {max_time_min:.0f} min"
        )
    return {
        "run_here": not reasons,
        "ram_GB": float(ram_gb),
        "ram_available_GB": available,
        "limit_GB": limit,
        "time_min": time_min,
        "max_time_min": max_time_min,
        "reasons": reasons,
    }


def checkpoint_plan() -> dict:
    """SU2 restart names already written by ``su2_euler_cfg``. Nothing is launched."""
    return {
        "launched": False,
        "imported_by_acdt": False,
        "solver_basename": "SU2_CFD",
        "restart_sol_on_continuation": "YES",
        "solution_filename": "restart_flow.dat",
        "restart_filename": "restart_flow.dat",
        "output_files": ["RESTART", "SURFACE_CSV"],
        "source": "su2_euler_cfg",
        "citation": "Economon et al., AIAA Journal 54(3), 2016",
        "chunk_iters": None,
        "chunk_note": (
            "O comprimento de cada bloco não foi escolhido. A corrida não arrancou "
            "e não há restart_flow.dat."
        ),
    }


def polar_comparison(l1: dict, published_requirements: list[str]) -> dict:
    """No RANS coefficients. L1 scalars and POH requirements are not this polar."""
    rows = []
    for name in QUANTITIES:
        rows.append({
            "quantity": name,
            "hifi": None,
            "L1": None,
            "published": None,
            "ratio": None,
            "same_quantity": False,
            "decision": "nao_aplicar",
            "status": "nao_avaliado",
            "why": "Não há coeficiente RANS. Em falta não é zero.",
        })
    return {
        "overall": "nao_aplicar",
        "valid": False,
        "applied": False,
        "model_L1": "nao_avaliado",
        "model_note": (
            "A polar L1 fica registada à parte e não é calibrada. "
            "nao_avaliado não é aprovação. O yaml não muda."
        ),
        "rows": rows,
        "l1_polar": {
            "CD0": l1.get("CD0"),
            "K": l1.get("K"),
            "CLmax_clean": l1.get("CLmax_clean"),
            "method": "Raymer Eq. 12.5 (CD = CD0 + K CL²) e Eq. 12.15 (CLmax limpo)",
            "same_as_rans_polar": False,
            "why": (
                "CD0, K e CLmax limpo não são CL, CD e Cm de um ângulo da malha "
                "de asa e fuselagem. Não se forma razão."
            ),
        },
        "published_polar": {
            "present": False,
            "status": "nao_avaliado",
            "requirements_in_the_example": list(published_requirements),
            "absent": ["CL(alpha)", "CD(alpha)", "Cm(alpha)"],
            "why": (
                "O exemplo cita o POH 172S para velocidade, perda, subida e distâncias. "
                "Não há, no repositório, uma tabela publicada de CL, CD e Cm deste avião "
                "em função do ângulo."
            ),
        },
    }


def build_record(estimate: dict, guard: dict, comparison: dict, *, today: str, branch: str | None,
                 disk_free_GB: float) -> dict:
    launched = bool(guard["run_here"])
    return {
        "date": today,
        "branch": branch,
        "decision": "nao_aplicar",
        "valid": False,
        "applied": False,
        "model_L1": "nao_avaliado",
        "example_yaml_edited": False,
        "solver_started": False,
        "mesh_written": False,
        "imported_by_acdt": False,
        "status": "nao_corrido" if not launched else "cabe_e_nao_foi_lancado",
        "estimate": estimate,
        "guard": guard,
        "checkpoints": checkpoint_plan(),
        "comparison": comparison,
        "disk_free_GB": disk_free_GB,
        "prior_record": "examples/output/cessna172_check_hifi_win/h5_c172_gci.json",
        "full_aircraft_case_not_rewritten": "examples/output/cessna172_check_hifi_win/rans_case/estimate.json",
        "coarser_mesh": "nao_repetida",
        "coarser_note": (
            "A malha engrossada já recusada em h5_c172_gci.json não é este caso "
            "e não foi repetida."
        ),
        "csv": RESULT_CSV,
        "citations": [
            "Economon et al., AIAA Journal 54(3), 2016",
            "Spalart and Allmaras, AIAA 92-0439",
            "Raymer, Aircraft Design: A Conceptual Approach, Eq. 12.5 and Eq. 12.15",
            "Geuzaine and Remacle, International Journal for Numerical Methods in Engineering 79(11), 2009",
        ],
    }


def write_csv(path: Path, comparison: dict) -> None:
    fields = ["quantity", "hifi", "L1", "published", "ratio", "decision", "status"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", restval="")
        writer.writeheader()
        for row in comparison["rows"]:
            writer.writerow({
                "quantity": row["quantity"],
                "hifi": "" if row["hifi"] is None else row["hifi"],
                "L1": "" if row["L1"] is None else row["L1"],
                "published": "" if row["published"] is None else row["published"],
                "ratio": "" if row["ratio"] is None else row["ratio"],
                "decision": row["decision"],
                "status": row["status"],
            })
        polar = comparison["l1_polar"]
        for name in ("CD0", "K", "CLmax_clean"):
            value = polar[name]
            writer.writerow({
                "quantity": f"L1_{name}",
                "hifi": "",
                "L1": "" if value is None else f"{value:.8g}",
                "published": "",
                "ratio": "",
                "decision": "nao_aplicar",
                "status": "nao_avaliado",
            })


def write_record(dest: Path, record: dict, comparison: dict) -> Path:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / RESULT_JSON
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(dest / RESULT_CSV, comparison)
    return path
