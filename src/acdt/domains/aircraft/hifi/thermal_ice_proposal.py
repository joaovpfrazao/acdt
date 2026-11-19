# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""High-fidelity thermal and icing proposal. Nothing is solved or meshed.

The lower-level numbers are the ones already written in the handoff. They are
not recomputed here. A missing mesh count stays missing.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

RESULT_JSON = "proposta.json"
RESULT_CSV = "proposta.csv"

_ROWS = (
    {
        "quantity": "thermal_bay_temperature",
        "lower_level": "compartimento do exemplo, cruzeiro 50–52 °C; subida e solo 64–70 °C",
        "lower_source": "docs/HANDOFF.md, Gestão térmica L0/L1",
        "why": "O L0/L1 é uma rede de dois nós. Não há campo de temperatura.",
    },
    {
        "quantity": "thermal_wall_heat_flux",
        "lower_level": "MARKER_HEATFLUX = 0 nos .cfg de RANS já escritos",
        "lower_source": "hifi/cfd.py, hifi/cfd3d.py, hifi/wing_bl.py",
        "why": "Parede adiabática não é o balanço de energia do compartimento.",
    },
    {
        "quantity": "ice_thickness_stagnation",
        "lower_level": "exemplo: estabilizador 14,1–57,2 mm; asa 11,3–45,4 mm",
        "lower_source": "docs/HANDOFF.md, Gelo L0/L1; Messinger via Anderson",
        "why": "Espessura de estagnação em geometria limpa. Não há forma acrescida.",
    },
    {
        "quantity": "ice_beta0",
        "lower_level": "β₀ de Langmuir e Blodgett, Eq. (3.13) de Anderson",
        "lower_source": "docs/GELO.md",
        "why": "β₀ é o valor na estagnação. β local não está implementado.",
    },
    {
        "quantity": "ice_appendix_O",
        "lower_level": None,
        "lower_source": "docs/GELO.md: tabelas do Apêndice O não verificadas",
        "why": "SLD não entra como zero. Não há proposta numérica enquanto as tabelas não forem verificadas.",
    },
)


def proposal() -> dict:
    """Meshes, solvers and cost. Every numeric hi-fi field is missing."""
    thermal = {
        "mesh": {
            "solid": "ausente",
            "solid_note": (
                "O compartimento L0/L1 é um nó. Não há sólido da baía, por isso "
                "não se escreve malha."
            ),
            "if_a_solid_exists": (
                "Na pele exterior, a primeira célula viscosa usaria first_cell com "
                "y+ = 1, já em hifi/cfd.py. O interior do compartimento e a condução "
                "na parede não têm receita neste repositório."
            ),
            "cells": None,
            "cells_status": "nao_avaliado",
        },
        "solver": {
            "name": "SU2_CFD",
            "process": "separado",
            "imported_by_acdt": False,
            "started": False,
            "current_case": "MARKER_HEATFLUX = 0",
            "conjugate_case_in_repo": False,
            "openfoam": {
                "role": "stub",
                "license": "GPL-3.0",
                "process": "separado",
                "started": False,
            },
        },
        "cost": _cost(),
    }
    icing = {
        "mesh": {
            "solid": "ausente",
            "clean_section": (
                "Os casos ICING-AND-B1 e ICING-AND-B2 e o raio do NACA 0012 já "
                "estão no V&V L1. Não se escreveu malha de bordo de ataque."
            ),
            "accreted_surface": "nao_construida",
            "cells": None,
            "cells_status": "nao_avaliado",
            "appendix_O": "fora_desta_proposta",
        },
        "solver": {
            "name": "LEWICE",
            "process": "separado",
            "imported_by_acdt": False,
            "started": False,
            "in_third_party": False,
            "license_in_repo": None,
            "license_note": (
                "A licença não está em THIRD_PARTY.md. Não se instala nem se "
                "importa neste ramo."
            ),
            "role": (
                "Referência já citada para o desvio de β₀ em docs/GELO.md. "
                "Não é um cálculo novo."
            ),
        },
        "cost": _cost(),
        "irt_shapes": {
            "present": False,
            "status": "nao_avaliado",
            "why": "Não há formas medidas da NASA IRT neste repositório.",
        },
    }
    rows = []
    for item in _ROWS:
        rows.append({
            "quantity": item["quantity"],
            "hifi": None,
            "lower_level": item["lower_level"],
            "lower_source": item["lower_source"],
            "ratio": None,
            "same_quantity": False,
            "decision": "nao_aplicar",
            "status": "nao_avaliado",
            "why": item["why"],
        })
    return {
        "thermal": thermal,
        "icing": icing,
        "comparison": {
            "overall": "nao_aplicar",
            "valid": False,
            "applied": False,
            "model_L0": "nao_avaliado",
            "model_L1": "nao_avaliado",
            "recomputed": False,
            "rows": rows,
            "model_note": (
                "A proposta não avalia o L0 nem o L1. nao_avaliado não é aprovação. "
                "O yaml dos exemplos não muda."
            ),
        },
    }


def _cost() -> dict:
    return {
        "ram_GB": None,
        "cpu_h": None,
        "status": "nao_avaliado",
        "gate": (
            "tools.budget recusa memória acima de 70 % da RAM livre ou tempo "
            "acima de 45 min. Sem malha, essa conta não se faz."
        ),
        "why": "Não há sólido nem malha. Uma contagem de células não é inventada.",
        "pressuposto": None,
    }


def build_record(*, today: str, branch: str | None) -> dict:
    body = proposal()
    return {
        "date": today,
        "branch": branch,
        "kind": "proposta",
        "ran": False,
        "decision": "nao_aplicar",
        "valid": False,
        "applied": False,
        "model_L0": "nao_avaliado",
        "model_L1": "nao_avaliado",
        "example_yaml_edited": False,
        **body,
        "csv": RESULT_CSV,
    }


def write_record(dest: Path, *, today: str, branch: str | None) -> dict:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    record = build_record(today=today, branch=branch)
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
