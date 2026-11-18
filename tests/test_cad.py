"""Structure CAD: the spec and the DXF do not need CadQuery. The STEP does, in a child process."""
import math
import sys

import pytest

from acdt.domains.aircraft.cad_export import assembly_spec, cadquery_available, export_cad, write_dxf
from acdt.domains.aircraft.geometry import Configuration, Fuselage, TrapezoidalWing, size_tails


def _ga():
    wing = TrapezoidalWing(16.2, 7.4, 0.7, 0.0, 0.12, 0.12)
    fus = Fuselage(8.0, 8.0 / 7.0)
    ht, vt = size_tails(wing, 0.60 * fus.length, 0.70, 0.04)
    return Configuration(wing, fus, ht, vt)


def test_spec_matches_the_wing_box_and_the_frame_pitch():
    cfg = _ga()
    spec = assembly_spec(cfg, x_wing_apex=2.4)
    assert spec["span_m"] == pytest.approx(cfg.wing.span)
    assert spec["root_box_chord_m"] == pytest.approx(0.45 * cfg.wing.c_root)
    assert spec["n_frames"] == pytest.approx(math.floor(8.0 / 0.5) + 1)
    names = [p["name"] for p in spec["parts"]]
    assert "wing_front_spar_right" in names and "wing_upper_skin_left" in names
    assert "fuselage_frame_000" in names and "longeron_0" in names
    assert "vtail_front_spar_right" in names and "vtail_front_spar_left" not in names
    assert "cadquery" not in sys.modules
    # Nose is 2.4 m ahead of the wing root, so the first frame sits at x = -2.4.
    assert spec["parts"][[p["name"] for p in spec["parts"]].index("fuselage_frame_000")]["x"] == pytest.approx(-2.4)


def test_dxf_is_millimetres_and_shows_the_semispan(tmp_path):
    cfg = _ga()
    spec = assembly_spec(cfg)
    path = write_dxf(spec, tmp_path / "structure.dxf")
    text = path.read_text(encoding="utf-8")
    assert "LINE" in text and "ENDSEC" in text
    tip_mm = f"{1000.0 * cfg.wing.span / 2.0:.4f}"
    assert tip_mm in text


def test_step_assembly_is_written_without_importing_cadquery_here(tmp_path):
    if not cadquery_available():
        pytest.skip("CadQuery não instalado (pip install 'acdt[cad]')")
    info = export_cad(_ga(), tmp_path, x_wing_apex=2.4)
    assert info["step"]
    step = (tmp_path / "structure.step").read_text(encoding="utf-8", errors="replace")
    assert step.startswith("ISO-10303-21")
    manifest = (tmp_path / "cad_manifest.json").read_text(encoding="utf-8")
    assert "wing_front_spar_right" in manifest
    assert "cadquery" not in sys.modules
