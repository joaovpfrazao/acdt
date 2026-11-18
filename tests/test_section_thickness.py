"""Declared section thickness and the camber the loft and the assembly AVL do not build.

No SU2 and no pyHyp. The AVL process runs only when ``avl`` is on PATH, and only to compare
symmetric NACA cards at one angle. A missing binary skips that comparison; it is not a pass of
the camber line.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import yaml

from acdt.domains.aircraft.aero.avl import _grab, avl_available
from acdt.domains.aircraft.assembly.assembly import Assembly
from acdt.domains.aircraft.assembly.components import (
    Surface, naca4_designation, naca_yt, section_thickness_record, symmetric_naca_code,
)
from acdt.domains.aircraft.hifi.wing_bl import (
    DOCUMENTED_S_M2, DRAWING, avl_text, cruise_state, mac_quarter_chord, scaled_wing,
)

EX = Path(__file__).resolve().parents[1] / "examples"
# Same header for both AVL files. Mesh Bref can move with thickness (dihedral gives t a y component);
# that shift must not be read as an aerodynamic delta.
FROZEN_REF = {"S_m2": 3.186, "Cref_m": 0.727118, "Bref_m": 4.38168}
FROZEN_ALPHA_DEG = 9.520570


def _naca_cards(text: str) -> list[str]:
    """Lines that follow a NACA keyword. Comment lines are not cards."""
    cards = []
    expect = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if expect:
            cards.append(line)
            expect = False
        elif line == "NACA":
            expect = True
    return cards


def test_naca4_reads_digits_and_does_not_build_a_mean_line():
    parsed = naca4_designation("NACA 4415")
    assert parsed == {
        "designation": "NACA 4415",
        "camber_percent_chord": 4,
        "camber_position_tenths": 4,
        "thickness_percent_chord": 15,
    }
    assert naca4_designation("naca4415")["designation"] == "NACA 4415"
    assert naca4_designation("NACA 0012")["camber_percent_chord"] == 0
    assert naca4_designation("NACA 23012") is None
    assert naca4_designation("Clark Y") is None
    assert naca4_designation("GOE 398") is None
    assert naca4_designation("naca4") is None
    assert naca4_designation(None) is None
    rec = section_thickness_record("NACA 4415", 0.15, 0.12)
    assert set(rec["parsed"]) == {
        "designation", "camber_percent_chord", "camber_position_tenths", "thickness_percent_chord",
    }
    assert "yc" not in rec and "camber_line" not in rec


def test_camber_status_is_not_zero_when_unknown():
    gap = section_thickness_record("NACA 4415", 0.13, 0.10)
    assert gap["camber"] == "lacuna"
    assert gap["naca_root"] == "0013" and gap["naca_tip"] == "0010"
    assert gap["parsed"]["thickness_percent_chord"] == 15
    assert "não é construída" in gap["motivo"]
    assert any(p.startswith("PRESSUPOSTO:") for p in gap["pressupostos"])

    flat = section_thickness_record("NACA 0012", 0.15, 0.12)
    assert flat["camber"] == "ausente_na_designacao"
    assert flat["naca_root"] == "0015" and flat["naca_tip"] == "0012"

    for name in ("Clark Y", "GOE 398", "NACA 23012", "naca4", None, ""):
        rec = section_thickness_record(name, 0.12, 0.10)
        assert rec["camber"] == "desconhecida"
        assert rec["parsed"] is None
        assert rec["naca_root"] == "0012"


def test_symmetric_code_rejects_non_positive_and_rounds_half_to_even():
    assert symmetric_naca_code(0.15) == "0015"
    assert symmetric_naca_code(0.12) == "0012"
    assert symmetric_naca_code(0.135) == "0014"   # round(13.5) is 14
    assert symmetric_naca_code(0.01) == "0001"
    with pytest.raises(ValueError):
        symmetric_naca_code(0.0)
    with pytest.raises(ValueError):
        symmetric_naca_code(-0.12)
    with pytest.raises(ValueError):
        symmetric_naca_code(float("nan"))


def test_declared_thickness_on_a_cranked_surface_keeps_planform():
    """Not the flying wing. Intermediate t/c follows leading-edge arc length."""
    crank = Surface(
        name="crank", role="wing", airfoil="Clark Y",
        sections=[
            {"le": [0.0, 0.0, 0.0], "chord": 1.2, "twist_deg": 1.0, "tc": 0.09},
            {"le": [0.4, 1.0, 0.0], "chord": 0.9, "twist_deg": -2.0, "tc": 0.09},
            {"le": [0.6, 1.0, 0.5], "chord": 0.5, "twist_deg": -4.0, "tc": 0.08},
        ],
    )
    new, rec = crank.with_declared_thickness(0.20, 0.08, airfoil="NACA 2412")
    assert rec["camber"] == "lacuna" and rec["naca_root"] == "0020" and rec["naca_tip"] == "0008"
    assert new.airfoil == "NACA 2412"
    assert new.planform_area() == pytest.approx(crank.planform_area(), rel=0, abs=1e-12)
    les = np.array([s["le"] for s in new.sections], float)
    seg = np.linalg.norm(np.diff(les, axis=0), axis=1)
    frac = np.concatenate([[0.0], np.cumsum(seg) / seg.sum()])
    assert frac[1] == pytest.approx(seg[0] / seg.sum())
    assert frac[1] != pytest.approx(0.5)
    for old, sec, f in zip(crank.sections, new.sections, frac):
        assert sec["le"] == old["le"]
        assert sec["chord"] == old["chord"]
        assert sec["twist_deg"] == old["twist_deg"]
        assert sec["tc"] == pytest.approx(0.20 + (0.08 - 0.20) * float(f))
        assert "yc" not in sec
    text = Assembly([new], expand_mirror=False).avl_text(ref={"Sref": 1.0, "Cref": 1.0, "Bref": 2.0})
    cards = _naca_cards(text)
    assert cards[0] == "0020" and cards[-1] == "0008"
    assert "CLAF" not in text
    assert "2412" not in cards
    assert "linha média não é construída" in text


def test_loft_thickness_follows_declared_tc():
    thin = Surface.panel("rect", 1.0, 1.0, 2.0, tc_root=0.10, tc_tip=0.10, n_sections=2)
    thick, _rec = thin.with_declared_thickness(0.20, 0.20)
    yt = float(naca_yt(0.3, 0.10))
    point = [[0.3, 1.0, 1.5 * yt]]
    assert thin.contains(point)[0] < 0.0
    assert thick.contains(point)[0] > 0.0
    z_thin = float(np.max(np.abs(thin.mesh()[0][:, 2])))
    z_thick = float(np.max(np.abs(thick.mesh()[0][:, 2])))
    assert z_thick == pytest.approx(2.0 * z_thin, rel=1e-9, abs=0.0)


def test_bad_thickness_and_coincident_sections_raise():
    panel = Surface.panel("fin", 0.4, 0.3, 0.8, dihedral_deg=90.0, tc_root=0.09, tc_tip=0.09)
    with pytest.raises(ValueError):
        panel.with_declared_thickness(0.0, 0.12)
    with pytest.raises(ValueError):
        panel.with_declared_thickness(float("inf"), 0.12)
    flat = Surface(name="flat", sections=[
        {"le": [0.0, 0.0, 0.0], "chord": 1.0, "tc": 0.12},
        {"le": [0.0, 0.0, 0.0], "chord": 0.8, "tc": 0.10},
    ])
    with pytest.raises(ValueError, match="coincid"):
        flat.with_declared_thickness(0.15, 0.12)


def test_flying_wing_yaml_json_and_loft_share_declared_tc():
    spec = yaml.safe_load((EX / "heavy" / "uav150_flying_wing_tailless.yaml").read_text(encoding="utf-8"))
    aero = spec["assumptions"]["aero"]
    assert aero["tc_root"] == 0.15
    assert aero["tc_tip"] == 0.12
    assert aero["airfoil"] == "NACA 4415"
    drawing = json.loads((EX / "integration" / "flying_wing_pusher_tailless.json").read_text(encoding="utf-8"))
    wing = next(c for c in drawing["assembly"]["components"] if c["name"] == "wing")
    assert wing["airfoil"] == "NACA 4415"
    assert wing["panel"]["tc_root"] == 0.15 and wing["panel"]["tc_tip"] == 0.12
    assert wing["panel"]["n_sections"] == 3
    loaded = Assembly.from_dict(drawing["assembly"])
    surf = next(c for c in loaded.components if c.name == "wing" and not c.mirrored_image)
    assert [s["tc"] for s in surf.sections] == pytest.approx([0.15, 0.135, 0.12])
    cards = _naca_cards(loaded.avl_text())
    assert cards == ["0015", "0014", "0012"]
    assert "CLAF" not in loaded.avl_text()
    h1, _meta = scaled_wing()
    assert h1.sections[0]["tc"] == pytest.approx(0.15)
    assert h1.sections[-1]["tc"] == pytest.approx(0.12)
    assert h1.airfoil == "NACA 4415"
    assert 2.0 * h1.planform_area() == pytest.approx(DOCUMENTED_S_M2, rel=1e-9, abs=0.0)
    ref = {"S_m2": DOCUMENTED_S_M2, "Cref_m": 0.7, "Bref_m": 4.0}
    text = avl_text(h1, ref, 0.0, 0.98)
    assert _naca_cards(text) == ["0015", "0012"]
    assert "CLAF" not in text
    assert "4415" not in _naca_cards(text)
    assert "PRESSUPOSTO" in text and "curvatura" in text
    closed = json.loads((EX / "integration" / "flying_wing_pusher_closed.json").read_text(encoding="utf-8"))
    closed_wing = next(c for c in closed["assembly"]["components"] if c["name"] == "wing")
    assert closed_wing["panel"]["tc_root"] == 0.13
    assert closed_wing["panel"]["tc_tip"] == 0.10


def _run_avl(work: Path, surface, ref: dict, mach: float, x_ref: float, alpha_deg=None, cl=None) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    (work / "wing.avl").write_text(avl_text(surface, ref, mach, x_ref), encoding="utf-8")
    if alpha_deg is not None:
        a_cmd = f"a a {alpha_deg:.6f}"
    else:
        a_cmd = f"a c {cl:.6f}"
    cmds = ["oper", a_cmd, f"m\nmn {mach:.4f}\n", "x", "st", "st.txt", "", "quit"]
    exe = shutil.which("avl")
    r = subprocess.run([exe, "wing.avl"], input="\n".join(cmds) + "\n", capture_output=True, text=True,
                       timeout=120, cwd=work)
    st = work / "st.txt"
    if not st.exists():
        raise RuntimeError(f"AVL failed in {work}:\n{r.stdout[-1500:]}\n{r.stderr[-400:]}")
    text = st.read_text(encoding="utf-8")
    return {k: _grab(text, k) for k in ("Alpha", "CLtot", "Cmtot", "CDtot", "Sref", "Cref", "Bref", "Xref")}


@pytest.mark.requires_avl
def test_avl_cl_cm_at_frozen_references(tmp_path):
    """Old 0.13/0.10 cards against the declared 0.15/0.12 cards. Same planform, twist and header."""
    new, meta = scaled_wing()
    k = meta["k"]
    d = DRAWING
    old = Surface.panel(
        "wing", d["root_chord"] * k, d["tip_chord"] * k, d["span"] * k,
        sweep_le_deg=d["sweep_le_deg"], dihedral_deg=d["dihedral_deg"],
        tc_root=0.13, tc_tip=0.10, twist_tip_deg=d["twist_tip_deg"],
        n_sections=2, origin=meta["origin_m"], mirror=True, role="wing", airfoil=d["airfoil"],
    )
    assert _naca_cards(avl_text(old, FROZEN_REF, 0.0, 0.98)) == ["0013", "0010"]
    x_ref = mac_quarter_chord(new)["x_ref_m"]
    state = cruise_state(FROZEN_REF)
    old_a = _run_avl(tmp_path / "old_a", old, FROZEN_REF, state["Mach"], x_ref, alpha_deg=FROZEN_ALPHA_DEG)
    new_a = _run_avl(tmp_path / "new_a", new, FROZEN_REF, state["Mach"], x_ref, alpha_deg=FROZEN_ALPHA_DEG)
    old_c = _run_avl(tmp_path / "old_c", old, FROZEN_REF, state["Mach"], x_ref, cl=state["CL_target"])
    new_c = _run_avl(tmp_path / "new_c", new, FROZEN_REF, state["Mach"], x_ref, cl=state["CL_target"])
    for row in (old_a, new_a, old_c, new_c):
        assert math.isfinite(row["CLtot"]) and math.isfinite(row["Cmtot"])
        assert row["Sref"] == pytest.approx(FROZEN_REF["S_m2"], abs=5e-5)
        assert row["Cref"] == pytest.approx(FROZEN_REF["Cref_m"], abs=5e-5)
        assert row["Bref"] == pytest.approx(FROZEN_REF["Bref_m"], abs=5e-5)
        assert row["Xref"] == pytest.approx(x_ref, abs=5e-5)
    # Symmetric 00xx without CLAF: thickness is not in the vortex-lattice solution.
    # A move larger than the printed 1e-5 would be a real change and must be re-recorded.
    assert new_a["CLtot"] == pytest.approx(old_a["CLtot"], abs=1e-5)
    assert new_a["Cmtot"] == pytest.approx(old_a["Cmtot"], abs=1e-5)
    assert new_a["Alpha"] == pytest.approx(FROZEN_ALPHA_DEG, abs=1e-4)
    assert new_c["CLtot"] == pytest.approx(old_c["CLtot"], abs=1e-5)
    assert new_c["Cmtot"] == pytest.approx(old_c["Cmtot"], abs=1e-5)
    assert new_c["Alpha"] == pytest.approx(old_c["Alpha"], abs=1e-4)
    # Reference digits measured 14 nov 2026 with the Windows AVL build (frozen header, printed ST digits).
    # Other AVL builds differ in the last digits (Linux build, same input: CLtot 0.50204, Cmtot 0.02893, CDtot 0.01665). The absolute check
    # is a sanity band only (PRESSUPOSTO: 1 % relative on CL, 5 % on the inviscid CDtot, 0.001 absolute on Cm); the old/new
    # comparison above, run on one build, is what must hold to 1e-5.
    for row in (old_a, new_a, old_c, new_c):
        assert row["CLtot"] == pytest.approx(0.50293, rel=1e-2)
        assert row["Cmtot"] == pytest.approx(0.02886, abs=1e-3)
        assert row["CDtot"] == pytest.approx(0.01611, rel=5e-2)
