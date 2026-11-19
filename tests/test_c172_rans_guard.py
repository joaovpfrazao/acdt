# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""The C172 wing-plus-fuselage RANS case stays inside the compute guard."""
import ast
from pathlib import Path

import pytest

from acdt.domains.aircraft.hifi.cfd3d import rans_volume_estimate
from acdt.domains.aircraft.hifi.rans_wing_fuselage import (
    computation_guard,
    checkpoint_plan,
    polar_comparison,
)

_SWET_WF = 47.91709302438845
_SWET_FULL = 55.74815331780326
_MAC = 0.013802602464351698 * 100.0
_H1 = 7.463288479681644e-06


def test_volume_formula_matches_the_stored_wing_fuselage_count():
    est = rans_volume_estimate(_SWET_WF, _MAC, _H1)
    assert est["cells_estimate"] == 12072848
    assert est["ram_GB"] == pytest.approx(21.731126792695072, rel=1e-12)
    assert est["wall_h"] == pytest.approx(40.242827393879764, rel=1e-12)
    assert est["prism_layers"] == 42
    full = rans_volume_estimate(_SWET_FULL, _MAC, _H1)
    assert full["cells_estimate"] == 14045906
    assert full["ram_GB"] == pytest.approx(25.282631139397022, rel=1e-12)


def test_nominal_case_is_refused_on_ram_and_on_time():
    est = rans_volume_estimate(_SWET_WF, _MAC, _H1)
    guard = computation_guard(est["ram_GB"], est["wall_h"], available_gb=19.642)
    assert guard["run_here"] is False
    assert guard["limit_GB"] == pytest.approx(0.7 * 19.642)
    assert any("memória" in reason for reason in guard["reasons"])
    assert any("tempo" in reason for reason in guard["reasons"])
    huge = computation_guard(est["ram_GB"], est["wall_h"], available_gb=1000.0)
    assert huge["run_here"] is False
    assert not any("memória" in reason for reason in huge["reasons"])
    assert any("tempo" in reason for reason in huge["reasons"])


def test_a_missing_coefficient_is_not_zero_and_not_a_pass():
    comparison = polar_comparison(
        {"CD0": 0.02, "K": 0.05, "CLmax_clean": 1.4},
        ["cruise_speed", "stall_speed"],
    )
    assert comparison["overall"] == "nao_aplicar"
    assert comparison["valid"] is False
    assert comparison["applied"] is False
    assert comparison["model_L1"] == "nao_avaliado"
    assert comparison["published_polar"]["present"] is False
    assert comparison["published_polar"]["status"] == "nao_avaliado"
    for row in comparison["rows"]:
        assert row["hifi"] is None
        assert row["ratio"] is None
        assert row["status"] == "nao_avaliado"
        assert row["hifi"] != 0
    assert comparison["l1_polar"]["same_as_rans_polar"] is False
    plan = checkpoint_plan()
    assert plan["launched"] is False
    assert plan["chunk_iters"] is None
    assert plan["imported_by_acdt"] is False


def test_recorded_refusal_has_no_coefficients_and_no_machine_path():
    import json
    import re

    path = (
        Path(__file__).resolve().parents[1]
        / "examples" / "output" / "cessna172_check_hifi_win" / "h5_c172_rans_asa_fuselagem.json"
    )
    text = path.read_text(encoding="utf-8")
    record = json.loads(text)
    assert record["status"] == "nao_corrido"
    assert record["solver_started"] is False
    assert record["mesh_written"] is False
    assert record["decision"] == "nao_aplicar"
    assert record["applied"] is False
    assert record["model_L1"] == "nao_avaliado"
    assert record["estimate"]["cells_estimate"] == 12072848
    assert record["estimate"]["ram_GB"] == pytest.approx(21.731126792695072)
    assert record["guard"]["run_here"] is False
    assert record["checkpoints"]["launched"] is False
    assert record["checkpoints"]["chunk_iters"] is None
    assert record["comparison"]["published_polar"]["present"] is False
    for row in record["comparison"]["rows"]:
        assert row["hifi"] is None
        assert row["ratio"] is None
    assert re.search(r"[A-Za-z]:[\\/]", text) is None
    assert "acdt-tools" not in text
    assert "://" not in text


def test_guard_module_does_not_launch_su2():
    path = (
        Path(__file__).resolve().parents[1]
        / "src" / "acdt" / "domains" / "aircraft" / "hifi" / "rans_wing_fuselage.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = [alias.name for alias in node.names] if isinstance(node, (ast.Import, ast.ImportFrom)) else []
        module = getattr(node, "module", None) or ""
        assert "su2" not in module.lower()
        assert all("su2" not in name.lower() for name in names)
    text = path.read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "Popen" not in text
