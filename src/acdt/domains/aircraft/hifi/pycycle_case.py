# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Run a pyCycle script in another interpreter.

The acdt process does not import pycycle. The interpreter is ``ACDT_PYCYCLE_PYTHON``,
the same boundary used for OpenVSP. The committed jet deck stays the L0 correlation.
"""
import os
import subprocess

from acdt.domains.aircraft.aero.interfaces import ToolNotAvailable


def pycycle_python():
    return os.environ.get("ACDT_PYCYCLE_PYTHON") or None


def run_pycycle(script, timeout=600):
    """Execute ``script`` with the external interpreter. Returns the process tails."""
    py = pycycle_python()
    if not py:
        raise ToolNotAvailable(
            "ACDT_PYCYCLE_PYTHON is not set; pyCycle stays out of the acdt process")
    proc = subprocess.run([py, script], capture_output=True, text=True, timeout=timeout)
    return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:]}
