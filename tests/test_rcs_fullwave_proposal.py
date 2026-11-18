# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""The full-wave RCS proposal does not run and does not treat PO as full-wave."""
import ast
import json
import re
from pathlib import Path

from acdt.core.em.po import C0
from acdt.domains.aircraft.hifi.rcs_fullwave_proposal import proposal, task_status
from acdt.domains.aircraft.rcs.study import FREQ_DEFAULT


def test_full_wave_is_missing_and_po_is_not_a_pass():
    body = proposal()
    assert body["solver"]["started"] is False
    assert body["solver"]["imported_by_acdt"] is False
    assert body["mesh"]["fdtd_cells"] is None
    assert body["mesh"]["fdtd_cells"] != 0
    assert body["cost"]["ram_GB"] is None
    grid = body["mesh"]["grid"]
    assert grid["freq_Hz"] == FREQ_DEFAULT
    assert grid["lambda_m"] == C0 / FREQ_DEFAULT
    assert grid["dx_m"] == grid["lambda_m"] / 10.0
    assert grid["cells_per_wavelength_status"] == "PRESSUPOSTO"
    assert body["comparison"]["overall"] == "nao_aplicar"
    assert body["comparison"]["model_L1"] == "nao_avaliado"
    assert body["comparison"]["applied"] is False
    mean = next(row for row in body["comparison"]["rows"] if row["quantity"] == "frontal_mean_rcs_dbsm")
    assert mean["hifi"] is None
    assert mean["ratio"] is None
    assert mean["same_quantity"] is False
    assert mean["lower_level"] == body["lower_level"]["vv_mean_dbsm_two_bounces"]
    measured = next(row for row in body["comparison"]["rows"] if row["quantity"] == "measured_rcs")
    assert measured["hifi"] is None
    assert measured["lower_level"] is None
    tasks = task_status()
    assert [item["pr"] for item in tasks] == [23, 24, 25, 26, 27]
    assert tasks[0]["merged"] is True
    assert tasks[0]["state"] == "integrado"
    assert tasks[0]["blocked"] is None
    assert all(item["merged"] is False for item in tasks[1:])
    assert all(item["state"] == "aberto" for item in tasks[1:])
    assert tasks[2]["blocked"]
    assert tasks[4]["blocked"]


def test_proposal_does_not_import_openems():
    path = (
        Path(__file__).resolve().parents[1]
        / "src" / "acdt" / "domains" / "aircraft" / "hifi" / "rcs_fullwave_proposal.py"
    )
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        names = [alias.name for alias in node.names] if isinstance(node, (ast.Import, ast.ImportFrom)) else []
        module = getattr(node, "module", None) or ""
        assert "openEMS" not in module
        assert "subprocess" not in module
        assert all("openEMS" not in name for name in names)
    assert "Popen" not in text


def test_written_record_stays_relative_and_matches_the_proposal():
    root = Path(__file__).resolve().parents[1]
    path = root / "examples" / "output" / "rcs_onda_completa_proposta" / "proposta.json"
    text = path.read_text(encoding="utf-8")
    assert "://" not in text
    assert "acdt-tools" not in text
    assert re.search(r"[A-Za-z]:[/\\]", text) is None
    data = json.loads(text)
    body = proposal(root)
    assert data["date"] == "2026-11-18"
    assert data["branch"] == "rcs-onda-completa-proposta"
    assert data["ran"] is False
    assert data["decision"] == "nao_aplicar"
    assert data["mesh"]["fdtd_cells"] is None
    assert data["solver"]["started"] is False
    assert data["cost"]["ram_GB"] is None
    assert data["comparison"]["overall"] == body["comparison"]["overall"]
    assert data["comparison"]["model_L1"] == "nao_avaliado"
    assert data["tarefas"] == task_status()
    assert data["lower_level"]["source"].startswith("examples/")
    assert (
        data["lower_level"]["vv_mean_dbsm_two_bounces"]
        == body["lower_level"]["vv_mean_dbsm_two_bounces"]
    )
    csv_text = path.with_suffix(".csv").read_text(encoding="utf-8")
    assert "frontal_mean_rcs_dbsm" in csv_text
    assert "nao_avaliado" in csv_text
