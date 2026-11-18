# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Thick-panel wake map, history parser and the AVL comparison. OpenVSP is not called."""
import csv

import pytest

from acdt.domains.aircraft.hifi.vspaero_panel import (
    COEFFICIENTS,
    DOCUMENTED_WAKE,
    compare_with_avl,
    nonfinite_columns,
    parse_history,
    thick_vspaero_block,
    wake_residual_note,
    write_iteration_csv,
)
from acdt.domains.aircraft.hifi.wing_bl import scaled_wing


_HISTORY = """
# Name                   Value      Units
Sref_                   3.1860000 Lunit^2
Rho_                    0.0023770 Munit/Lunit^3
Vinf_                 100.0000000 Lunit/Tunit

      Iter             Mach            CLtot              CDi             CDtot           CMytot            CLiw             CDiw         L2 Residual      Max Residual
               1   0.136953812568   0.100000000000   0.010000000000   0.020000000000   0.030000000000   0.110000000000   0.012000000000   1.355659477106   1.944474307329
               this row is short
               5   0.136953812568   0.528617793438   0.024896685554   0.039918904949   0.035398852751   0.541907177500   0.019933177212  -0.695285133166   0.870626383931
"""


def test_documented_wake_is_the_live_default_not_a_retune():
    assert DOCUMENTED_WAKE == {
        "WakeNumIter": 5,
        "NumWakeNodes": 8,
        "WakeRelax": 1.0,
        "FixedWakeFlag": 0,
        "ImplicitWake": 0,
    }


def test_thick_block_selects_the_panel_set_and_keeps_the_wake_map():
    surf, scale = scaled_wing()
    block = thick_vspaero_block(
        {"S_m2": scale["S_m2"], "Bref_m": 4.381874564811488, "Cref_m": 0.7270860799131671},
        {"Mach": 0.1369538125677505, "Re_Cref": 1756220.95},
        0.9801559793360929, 9.52057)
    assert block["surface"] == "thick"
    assert block["wake"] == DOCUMENTED_WAKE
    assert block["sref"] == pytest.approx(3.186)
    assert "fuselage" not in block
    assert surf.naca4_mean_line is False


def test_parser_keeps_tokens_and_drops_a_short_row():
    parsed = parse_history(_HISTORY)
    assert parsed["reference"]["Sref_"] == "3.1860000"
    assert parsed["reference"]["Rho_"] == "0.0023770"
    assert parsed["reference"]["Vinf_"] == "100.0000000"
    assert len(parsed["rows"]) == 2
    last = parsed["rows"][-1]
    assert last["CLtot"] == "0.528617793438"
    assert last["CDi"] == "0.024896685554"
    assert last["CDtot"] == "0.039918904949"
    assert last["CMytot"] == "0.035398852751"
    assert last["CLiw"] == "0.541907177500"
    assert last["CDiw"] == "0.019933177212"
    assert last["L2_Residual"] == "-0.695285133166"
    assert "0" not in last.values()
    note = wake_residual_note(parsed["rows"])
    assert note["converged"] is False
    assert note["iterative_ok"] is False
    assert note["L2_last"] == pytest.approx(-0.695285133166)


def test_comparison_is_nao_aplicar_and_a_missing_value_is_not_zero():
    parsed = parse_history(_HISTORY)
    avl = {"CL": 0.50293, "CDff": 0.0145358, "Cmtot": 0.02886, "CDtot": 0.01611}
    rec = compare_with_avl(parsed["rows"][-1], avl, iterative_ok=False)
    assert rec["overall"] == "nao_aplicar"
    assert rec["valid"] is False
    assert rec["applied"] is False
    assert rec["model_L1"] == "nao_aplicar"
    assert rec["CL"]["decision"] == "nao_aplicar"
    assert rec["CL"]["valid"] is False
    assert rec["CL"]["ratio"] == pytest.approx(0.528617793438 / 0.50293)
    assert rec["Cm"]["ratio"] == pytest.approx(0.035398852751 / 0.02886)
    assert rec["moment_sign"] == "same"
    assert rec["CDi_vs_CDff"]["ratio"] is None
    assert rec["CDi_vs_CDff"]["reported_ratio"] == pytest.approx(0.024896685554 / 0.0145358)
    assert rec["CDi_vs_CDff"]["reported_ratio_inside_band"] is False
    assert rec["CDtot_vs_AVL_CDtot"]["ratio"] is None
    assert all(item["valid"] is False and item["decision"] == "nao_aplicar" for item in rec["factors"])
    empty = compare_with_avl(
        {"CLtot": "0.5", "CMytot": "0.01", "CDi": "0.02", "CDiw": "0.02", "CDtot": "0.03"},
        {"CL": None, "CDff": 0.01, "Cmtot": 0.01, "CDtot": 0.01})
    assert empty["CL"]["ratio"] is None
    assert empty["CL"]["hifi"] == pytest.approx(0.5)
    assert empty["overall"] == "nao_aplicar"
    assert empty["moment_sign"] is None


def test_nonfinite_history_is_not_a_coefficient():
    row = {"CLtot": "nan", "CDi": "-nan(ind)", "CDtot": "0.01", "CMytot": ""}
    assert nonfinite_columns(row) == ["CLtot", "CDi"]
    rec = compare_with_avl(row, {"CL": 0.5, "CDff": 0.01, "Cmtot": 0.02, "CDtot": 0.01})
    assert rec["CL"]["hifi"] is None
    assert rec["CL"]["ratio"] is None
    assert rec["CL"]["reason"] == "quantidade em falta ou não é a mesma grandeza"
    assert rec["overall"] == "nao_aplicar"


def test_csv_leaves_a_missing_coefficient_blank(tmp_path):
    path = tmp_path / "iters.csv"
    write_iteration_csv(path, [{"Iter": "1", "CLtot": "0.5"}])
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["CLtot"] == "0.5"
    assert rows[0]["CDi"] == ""
    assert set(rows[0]) == set(COEFFICIENTS)
