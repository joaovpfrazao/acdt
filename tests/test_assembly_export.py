"""P1b (f): STEP and RCS input from the component assembly (light: faceted STEP in a CadQuery subprocess,
merged PEC mesh + STL, a 3-azimuth PO check)."""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from acdt.core.em.po import read_stl
from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly.export import cadquery_available, export_step, rcs_input, rcs_quick

EX = Path(__file__).resolve().parents[1] / "examples"
TWIN = EX / "integration" / "twin_boom_pusher.json"


def _asm():
    return Assembly.from_dict(json.loads(TWIN.read_text(encoding="utf-8"))["assembly"])


def test_rcs_input_mesh_and_stl_roundtrip(tmp_path):
    asm = _asm()
    ri = rcs_input(asm, tmp_path)
    m = ri["mesh"]
    assert ri["n_facets"] == m.n_facets and Path(ri["stl"]).exists()
    assert read_stl(ri["stl"]).n_facets == m.n_facets
    n_all = sum(len(asm.mesh(c.name)[1]) for c in asm.components)
    n_prop = sum(len(asm.mesh(c.name)[1]) for c in asm.components if c.role == "propeller")
    assert m.n_facets <= n_all - n_prop                       # propeller disc excluded (PRESSUPOSTO)
    q = rcs_quick(m, az_deg=(-20.0, 0.0, 20.0))
    assert all(math.isfinite(v) for v in q["dBsm"])
    assert q["dBsm"][0] == pytest.approx(q["dBsm"][2], abs=0.5)  # symmetric drawing → symmetric cut


@pytest.mark.skipif(not cadquery_available(), reason="CadQuery not installed")
def test_export_step_faceted_parts(tmp_path):
    asm = _asm()
    st = export_step(asm, tmp_path / "a.step")
    assert st["step"] and Path(st["step"]).stat().st_size > 1000
    assert set(st["parts"]) == {c.name for c in asm.components}
    assert st["parts"]["pod"] == "solid"
    head = Path(st["step"]).read_text(errors="ignore")[:400]
    assert "ISO-10303-21" in head


def test_cli_integration_rcs(tmp_path):
    r = subprocess.run([sys.executable, "-m", "acdt.cli", "integration", str(TWIN), "-o", str(tmp_path), "--rcs"],
                       capture_output=True, text=True)
    assert (tmp_path / "assembly_rcs.stl").exists() and (tmp_path / "rcs_quick.json").exists(), r.stdout + r.stderr
    assert len(json.loads((tmp_path / "rcs_quick.json").read_text())["dBsm"]) == 3
