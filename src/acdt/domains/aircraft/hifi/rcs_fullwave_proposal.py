# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Full-wave RCS proposal. openEMS is not started and is not imported.

The lower level is the Physical Optics record already on disk. A missing
full-wave value stays missing.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from acdt.core.em.po import C0
from acdt.domains.aircraft.rcs.study import FREQ_DEFAULT

RESULT_JSON = "proposta.json"
RESULT_CSV = "proposta.csv"
_PO_REL = "examples/output/uav150_flying_wing_tailless_hifi_win/h6_rcs_bounces2.json"


def _root() -> Path:
    return Path(__file__).resolve().parents[5]


def wavelength() -> dict:
    """λ = c/f at the PO study frequency. λ/10 is a working grid, not a convergence proof."""
    freq = float(FREQ_DEFAULT)
    lam = C0 / freq
    return {
        "freq_Hz": freq,
        "c_m_s": C0,
        "lambda_m": lam,
        "cells_per_wavelength": 10,
        "cells_per_wavelength_status": "PRESSUPOSTO",
        "cells_per_wavelength_note": (
            "PRESSUPOSTO: dez células por comprimento de onda é uma grelha de trabalho "
            "para FDTD. Não é uma citação de convergência e não foi corrida."
        ),
        "dx_m": lam / 10.0,
    }


def po_lower_level(root: Path | None = None) -> dict:
    path = (root or _root()) / _PO_REL
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "source": _PO_REL,
        "method": "Physical Optics",
        "vv_mean_dbsm_one_bounce": data["bounces_1"]["VV"]["mean_dbsm"],
        "vv_mean_dbsm_two_bounces": data["bounces_2"]["VV"]["mean_dbsm"],
        "full_wave_in_that_file": data["full_wave"],
        "same_as_full_wave": False,
    }


def proposal(root: Path | None = None) -> dict:
    lower = po_lower_level(root)
    grid = wavelength()
    rows = [
        {
            "quantity": "frontal_mean_rcs_dbsm",
            "hifi": None,
            "lower_level": lower["vv_mean_dbsm_two_bounces"],
            "lower_method": "PO, duas reflexões, VV",
            "ratio": None,
            "same_quantity": False,
            "decision": "nao_aplicar",
            "status": "nao_avaliado",
            "why": "A média do PO não é uma RCS de onda completa. Não se forma razão.",
        },
        {
            "quantity": "measured_rcs",
            "hifi": None,
            "lower_level": None,
            "lower_method": None,
            "ratio": None,
            "same_quantity": False,
            "decision": "nao_aplicar",
            "status": "nao_avaliado",
            "why": "Não há RCS medido no repositório. Em falta não é zero.",
        },
    ]
    return {
        "mesh": {
            "po_facets_are_not_the_grid": True,
            "fdtd_cells": None,
            "fdtd_cells_status": "nao_avaliado",
            "domain_m": None,
            "grid": grid,
            "why": (
                "Sem caixa de cálculo e sem o sólido que o PO deixa por avaliar "
                "(fuselagem, derivas, trem, hélice), a contagem de células fica em falta."
            ),
        },
        "solver": {
            "name": "openEMS",
            "license": "GPL-3.0",
            "process": "executável externo",
            "imported_by_acdt": False,
            "started": False,
            "source": "THIRD_PARTY.md",
            "mom_mlfmm_binary": None,
            "mom_note": (
                "core/em/po.py nomeia MoM/MLFMM como classe de onda completa. "
                "Não há binário escolhido nem instalado."
            ),
        },
        "cost": {
            "ram_GB": None,
            "cpu_h": None,
            "status": "nao_avaliado",
            "gate": (
                "tools.budget recusa memória acima de 70 % da RAM livre ou tempo "
                "acima de 45 min. A estimativa de 0,05 GB do PO não é o custo FDTD."
            ),
            "why": "Sem malha de onda completa não se inventa GB nem horas.",
            "pressuposto": None,
        },
        "lower_level": lower,
        "comparison": {
            "overall": "nao_aplicar",
            "valid": False,
            "applied": False,
            "model_L1": "nao_avaliado",
            "recomputed": False,
            "rows": rows,
            "model_note": (
                "O PO não fica validado nem calibrado por uma proposta que não correu. "
                "nao_avaliado não é aprovação. O yaml não muda."
            ),
        },
    }


def task_status() -> list[dict]:
    """Open pull requests of this effort. None of them is merged."""
    return [
        {
            "task": 1,
            "pr": 23,
            "branch": "win-openvsp-esteira",
            "state": "aberto",
            "merged": False,
            "verdict": "nao_aplicar",
            "model": "L1 AVL nao_avaliado como validação: nao_aplicar, sem calibração",
            "blocked": None,
        },
        {
            "task": 2,
            "pr": 24,
            "branch": "pycycle-sem-ajuste",
            "state": "aberto",
            "merged": False,
            "verdict": "nao_aplicar",
            "model": "L0 nao_aplicar; L1 nao_avaliado, deck ausente",
            "blocked": "O deck termodinâmico L1 não existe. O gráfico final não correu.",
        },
        {
            "task": 3,
            "pr": 25,
            "branch": "c172-rans-asa-fuselagem",
            "state": "aberto",
            "merged": False,
            "verdict": "nao_aplicar",
            "model": "L1 nao_avaliado",
            "blocked": (
                "21,731 GB e 40,24 h. Na medição havia 16,32 GB livres, limite 11,42 GB, "
                "e 2415 min contra 45 min. Não se engrossou a malha."
            ),
        },
        {
            "task": 4,
            "pr": 26,
            "branch": "termico-gelo-proposta",
            "state": "aberto",
            "merged": False,
            "verdict": "nao_aplicar",
            "model": "L0 e L1 nao_avaliado",
            "blocked": "Pedido só como proposta. Não há sólido da baía nem malha de acreção.",
        },
        {
            "task": 5,
            "pr": 27,
            "branch": "rcs-onda-completa-proposta",
            "state": "aberto",
            "merged": False,
            "verdict": "nao_aplicar",
            "model": "L1 PO nao_avaliado face à onda completa",
            "blocked": "Pedido só como proposta. O openEMS não arrancou e não há contagem de células.",
        },
    ]


def build_record(*, today: str, branch: str | None, root: Path | None = None) -> dict:
    body = proposal(root)
    return {
        "date": today,
        "branch": branch,
        "kind": "proposta",
        "ran": False,
        "decision": "nao_aplicar",
        "valid": False,
        "applied": False,
        "model_L1": "nao_avaliado",
        "example_yaml_edited": False,
        **body,
        "tarefas": task_status(),
        "csv": RESULT_CSV,
    }


def write_record(dest: Path, *, today: str, branch: str | None, root: Path | None = None) -> dict:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    record = build_record(today=today, branch=branch, root=root)
    (dest / RESULT_JSON).write_text(
        json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    fields = ["quantity", "hifi", "lower_level", "ratio", "decision", "status"]
    with (dest / RESULT_CSV).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", restval="")
        writer.writeheader()
        for row in record["comparison"]["rows"]:
            writer.writerow({
                "quantity": row["quantity"],
                "hifi": "",
                "lower_level": "" if row["lower_level"] is None else row["lower_level"],
                "ratio": "",
                "decision": row["decision"],
                "status": row["status"],
            })
    return record
