# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Unpatched pyCycle viewer parse and the missing L1 deck. pyCycle is not imported."""
from pathlib import Path

import pytest

from acdt.domains.aircraft.hifi.pycycle_compare import (
    CORRECTED_FIELDS,
    TABLE_FIELDS,
    compare_points,
    missing_l1_deck,
    parse_viewer,
)

_STDOUT = """
                              POINT: DESIGN
    Mach      Alt       W      Fn      Fg    Fram     OPR     TSFC
 0.00000      0.0 147.333 11800.0 11800.0     0.0  13.500  0.79852
                              POINT: OD0
 0.00000      0.0 142.787 11000.0 11000.0     0.0  12.859  0.78364
                              POINT: OD1
 0.20000   5000.0 119.121  8000.0  8812.5   812.5  12.203  0.82951
"""


def test_parser_keeps_the_printed_tokens():
    parsed = parse_viewer(_STDOUT)
    assert parsed["DESIGN"]["TSFC_lbm_lbf_h"] == "0.79852"
    assert parsed["DESIGN"]["Fn_lbf"] == "11800.0"
    assert parsed["OD1"]["Alt_ft"] == "5000.0"
    assert parsed["OD1"]["Fram_lbf"] == "812.5"


def test_missing_l1_lists_the_map_fields_and_does_not_invent_a_deck():
    gap = missing_l1_deck()
    assert gap["l1_thermodynamic_deck_present"] is False
    assert gap["status"] == "nao_avaliado"
    assert gap["l0_not_relabelled"] is True
    assert "TSFC_kg_N_s" in gap["table_fields_accepted_and_absent"]
    assert "F_over_delta" in gap["corrected_table_fields_accepted_and_absent"]
    assert set(TABLE_FIELDS) == set(gap["table_fields_accepted_and_absent"])
    assert set(CORRECTED_FIELDS) == set(gap["corrected_table_fields_accepted_and_absent"])
    assert "OPR" in gap["cycle_fields_the_map_cannot_store"]


def test_tsfc_ratio_is_not_a_calibration_and_a_missing_point_is_not_zero():
    rec = compare_points(parse_viewer(_STDOUT))
    assert rec["overall"] == "nao_aplicar"
    assert rec["valid"] is False
    assert rec["applied"] is False
    assert rec["same_engine"] is False
    assert rec["model_L0"] == "nao_aplicar"
    assert rec["model_L1"] == "nao_avaliado"
    design = rec["rows"][0]
    assert design["point"] == "DESIGN"
    assert design["TSFC_printed"] == pytest.approx(0.79852)
    assert design["L0_TSFC_lb_lbf_h"] == pytest.approx(0.4, abs=1e-4)
    assert design["decision"]["ratio"] is None
    assert design["decision"]["reported_ratio"] == pytest.approx(0.79852 / design["L0_TSFC_lb_lbf_h"])
    assert design["decision"]["reported_ratio_inside_band"] is False
    assert design["L0_thrust_installed_N"] != pytest.approx(0.0)
    empty = compare_points({})
    assert empty["rows"][0]["TSFC_printed"] is None
    assert empty["rows"][0]["decision"]["reported_ratio"] is None
    assert empty["overall"] == "nao_aplicar"


def test_recorded_run_is_not_an_applied_factor():
    import json

    path = (
        Path(__file__).resolve().parents[1]
        / "examples" / "output" / "jet_pycycle" / "h8_pycycle_sem_ajuste.json"
    )
    text = path.read_text(encoding="utf-8")
    record = json.loads(text)
    assert record["decision"] == "nao_aplicar"
    assert record["applied"] is False
    assert record["valid"] is False
    assert record["model_L0"] == "nao_aplicar"
    assert record["model_L1"] == "nao_avaliado"
    assert record["local_source_patch"] is False
    assert record["example_yaml_edited"] is False
    assert record["plot_failed_after_solution"] is True
    assert record["returncode"] == 1
    assert record["versions"]["om-pycycle"] == "4.4.0"
    assert record["versions"]["openmdao"] == "3.41.0"
    assert record["versions"]["numpy"] == "1.26.4"
    assert record["points"][0]["printed"]["TSFC_lbm_lbf_h"] == "0.79852"
    assert record["points"][0]["decision"]["ratio"] is None
    assert record["l1_deck"]["status"] == "nao_avaliado"
    assert record["l1_deck"]["l1_thermodynamic_deck_present"] is False
    assert "TSFC_kg_N_s" in record["l1_deck"]["table_fields_accepted_and_absent"]
    assert "://" not in text
    assert "acdt-tools" not in text


def test_compare_module_does_not_import_pycycle():
    import ast

    path = Path(__file__).resolve().parents[1] / "src" / "acdt" / "domains" / "aircraft" / "hifi" / "pycycle_compare.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = [a.name for a in node.names] if isinstance(node, (ast.Import, ast.ImportFrom)) else []
        mod = getattr(node, "module", None) or ""
        assert "pycycle" not in names and "pycycle" not in mod.split(".")
