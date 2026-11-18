# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""The thermal and icing proposal does not run and does not invent a mesh."""
import ast
from pathlib import Path

from acdt.domains.aircraft.hifi.thermal_ice_proposal import proposal


def test_proposal_leaves_hifi_missing_and_does_not_pass():
    body = proposal()
    assert body["comparison"]["overall"] == "nao_aplicar"
    assert body["comparison"]["applied"] is False
    assert body["comparison"]["valid"] is False
    assert body["comparison"]["model_L0"] == "nao_avaliado"
    assert body["comparison"]["model_L1"] == "nao_avaliado"
    assert body["comparison"]["recomputed"] is False
    for row in body["comparison"]["rows"]:
        assert row["hifi"] is None
        assert row["ratio"] is None
        assert row["status"] == "nao_avaliado"
        assert row["hifi"] != 0
    assert body["thermal"]["mesh"]["cells"] is None
    assert body["icing"]["mesh"]["cells"] is None
    assert body["thermal"]["cost"]["ram_GB"] is None
    assert body["icing"]["cost"]["cpu_h"] is None
    assert body["thermal"]["solver"]["started"] is False
    assert body["thermal"]["solver"]["openfoam"]["started"] is False
    assert body["icing"]["solver"]["started"] is False
    assert body["icing"]["solver"]["imported_by_acdt"] is False
    assert body["icing"]["irt_shapes"]["present"] is False
    appendix = next(row for row in body["comparison"]["rows"] if row["quantity"] == "ice_appendix_O")
    assert appendix["lower_level"] is None


def test_written_proposal_has_no_machine_path():
    import json
    import re

    path = (
        Path(__file__).resolve().parents[1]
        / "examples" / "output" / "termico_gelo_proposta" / "proposta.json"
    )
    text = path.read_text(encoding="utf-8")
    record = json.loads(text)
    assert record["ran"] is False
    assert record["decision"] == "nao_aplicar"
    assert record["model_L0"] == "nao_avaliado"
    assert record["model_L1"] == "nao_avaliado"
    assert re.search(r"[A-Za-z]:[\\/]", text) is None
    assert "://" not in text
    assert "acdt-tools" not in text


def test_proposal_module_does_not_launch_a_solver():
    path = (
        Path(__file__).resolve().parents[1]
        / "src" / "acdt" / "domains" / "aircraft" / "hifi" / "thermal_ice_proposal.py"
    )
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        names = [alias.name for alias in node.names] if isinstance(node, (ast.Import, ast.ImportFrom)) else []
        module = getattr(node, "module", None) or ""
        assert "subprocess" not in module
        assert all(name != "subprocess" for name in names)
    assert "Popen" not in text
