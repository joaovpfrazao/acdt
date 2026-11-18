# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Notebooks de examples/notebooks: guardados sem saídas, válidos e documentados (execução: job notebooks no CI,
``pytest --nbmake examples/notebooks``; docs/API.md §6)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NBS = sorted((ROOT / "examples" / "notebooks").glob("*.ipynb"))


def test_there_are_notebooks():
    assert len(NBS) >= 3


@pytest.mark.parametrize("nb", NBS, ids=lambda p: p.name)
def test_notebook_stripped_and_valid(nb):
    d = json.loads(nb.read_text(encoding="utf-8"))
    assert d["nbformat"] == 4
    for c in d["cells"]:
        if c["cell_type"] == "code":
            assert c.get("outputs") == [], f"{nb.name}: saídas guardadas (limpar antes de commit)"
            assert c.get("execution_count") is None, f"{nb.name}: execution_count guardado"
    first = "".join(d["cells"][0]["source"])
    assert "SPDX-License-Identifier: Apache-2.0" in first
    assert "from acdt import api" in "".join("".join(c["source"]) for c in d["cells"])
    assert nb.name in (ROOT / "docs" / "API.md").read_text(encoding="utf-8")
