# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""pyCycle stays out of the acdt process."""
import os
from pathlib import Path

import pytest

from acdt.domains.aircraft.aero.interfaces import ToolNotAvailable
from acdt.domains.aircraft.hifi.pycycle_case import run_pycycle


def test_pycycle_needs_its_own_interpreter(monkeypatch):
    monkeypatch.delenv("ACDT_PYCYCLE_PYTHON", raising=False)
    assert os.environ.get("ACDT_PYCYCLE_PYTHON") is None
    with pytest.raises(ToolNotAvailable):
        run_pycycle("cycle.py")


def test_pycycle_module_does_not_import_the_library():
    text = Path("src/acdt/domains/aircraft/hifi/pycycle_case.py").read_text(encoding="utf-8")
    assert "import pycycle" not in text.split('"""', 2)[-1]
