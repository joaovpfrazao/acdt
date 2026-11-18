"""H1 wing mesh: frames, outward patches, SU2 hex/prism writer. No pyHyp and no SU2."""
import math
from pathlib import Path

import numpy as np
import pytest

from acdt.core.atmosphere import G0, isa
from acdt.domains.aircraft.assembly.components import Surface, naca_yt
from acdt.domains.aircraft.hifi.wing_bl import (
    DOCUMENTED_S_M2, DOCUMENTED_W0_KG, EDGE_OPEN_HALF_CHORD, H1_RATIO_BAND, MESH_FAMILY,
    build_patches, cell_count, cruise_state, factor_record, gci_3d, h1_factor_decision,
    level_counts, mac_quarter_chord, read_plot3d_surface, reference_quantities,
    root_y_offset, scaled_wing, station_frames, su2_rans_cfg, write_plot3d_surface,
    write_pyhyp_script, write_su2_volume, write_surface_case,
)


def _panel(n_sections):
    return Surface.panel("wing", 0.9, 0.36, 1.9, sweep_le_deg=28.0, dihedral_deg=2.0,
                         tc_root=0.13, tc_tip=0.10, twist_tip_deg=-10.0, n_sections=n_sections)


def test_stations_match_panel_frames():
    ref = _panel(3)._frames()
    got = station_frames(_panel(2), [0.0, 0.5, 1.0])
    assert len(got) == 3
    for a, b in zip(got, ref):
        for x, y in zip(a, b):
            assert np.allclose(x, y, atol=1e-9, rtol=0.0)


def _nose_up_deg(le, chord, chord_m):
    te = le + chord_m * chord
    return -math.degrees(math.atan2(te[2] - le[2], te[0] - le[0]))


def test_negative_twist_is_nose_down_about_the_leading_edge():
    """twist_deg is nose-up positive, the same sign AVL writes as Ainc. The hinge stays on the LE."""
    dihedral = 2.0
    down = Surface.panel("wing", 0.9, 0.36, 1.9, sweep_le_deg=28.0, dihedral_deg=dihedral,
                         twist_tip_deg=-10.0, n_sections=2)
    root, tip = down._frames()
    assert np.allclose(root[1], [1.0, 0.0, 0.0], atol=1e-12)
    assert np.allclose(tip[0], down.sections[-1]["le"], atol=1e-12)
    te = tip[0] + tip[3] * tip[1]
    assert te[2] > tip[0][2]
    g = math.radians(dihedral)
    expected = -math.degrees(math.atan2(-math.sin(math.radians(-10.0)) * math.cos(g), math.cos(math.radians(-10.0))))
    assert _nose_up_deg(tip[0], tip[1], tip[3]) == pytest.approx(expected, abs=1e-9)
    assert expected == pytest.approx(-9.994, abs=0.01)
    k = np.array([0.0, math.cos(g), math.sin(g)])
    ex = np.array([1.0, 0.0, 0.0])
    phi = math.degrees(math.atan2(float(np.dot(tip[1], np.cross(k, ex))), float(np.dot(tip[1], ex))))
    assert phi == pytest.approx(-10.0, abs=1e-9)
    assert tip[2][2] > 0.0
    up = Surface.panel("wing", 0.9, 0.36, 1.9, sweep_le_deg=28.0, dihedral_deg=dihedral,
                       twist_tip_deg=10.0, n_sections=2)
    le, chord, _t, chord_m, _tc = up._frames()[-1]
    assert (le + chord_m * chord)[2] < le[2]
    assert _nose_up_deg(le, chord, chord_m) == pytest.approx(-expected, abs=1e-9)


def test_scaled_area_is_the_documented_planform():
    surf, meta = scaled_wing()
    ref = reference_quantities(surf)
    assert ref["S_m2"] == pytest.approx(DOCUMENTED_S_M2, rel=1e-12)
    assert meta["k"] == pytest.approx(math.sqrt(DOCUMENTED_S_M2 / meta["S_draw_m2"]))
    assert ref["Bref_m"] > 4.0
    mac = mac_quarter_chord(surf)
    assert mac["lambda"] == pytest.approx(0.4)
    assert mac["eta"] == pytest.approx((1 + 2 * 0.4) / (3 * (1 + 0.4)))
    assert mac["chord_at_station_m"] == pytest.approx(mac["c_mac_m"], rel=1e-9)
    assert mac["y_ref_m"] == 0.0 and mac["z_ref_m"] == 0.0


def test_cruise_cl_uses_isa_and_weight():
    surf, _ = scaled_wing()
    ref = reference_quantities(surf)
    state = cruise_state(ref)
    at = isa(3000.0)
    q = 0.5 * at.rho * 45.0 ** 2
    assert state["CL_target"] == pytest.approx(DOCUMENTED_W0_KG * G0 / (q * DOCUMENTED_S_M2))
    assert state["Re_Cref"] == pytest.approx(at.rho * 45.0 * ref["Cref_m"] / at.mu)
    assert state["Mach"] == pytest.approx(45.0 / at.a)


def _same_curve(a, b, atol=1e-12):
    return np.allclose(a, b, atol=atol) or np.allclose(a, b[::-1], atol=atol)


def _ends(curve, a, b, atol=1e-12):
    return (np.allclose(curve[0], a, atol=atol) and np.allclose(curve[-1], b, atol=atol)) or (
        np.allclose(curve[0], b, atol=atol) and np.allclose(curve[-1], a, atol=atol))


def test_patch_normals_point_out_and_seams_meet():
    surf, _ = scaled_wing()
    p = build_patches(surf, n_chord=17, n_span=9, n_tip=5)
    upper, lower, cap = p["upper"], p["lower"], p["tip"]
    le, te = p["le"], p["te"]
    # The sharp LE is open: upper and lower no longer share that node. The strip closes it.
    root = p["frames"][0]
    half = EDGE_OPEN_HALF_CHORD * root[3]
    assert np.linalg.norm(upper[0, 0] - lower[-1, 0]) == pytest.approx(2.0 * half)
    assert _ends(le[:, 0], lower[-1, 0], upper[0, 0])
    assert _ends(te[:, 0], lower[0, 0], upper[-1, 0])
    assert _same_curve(le[:, -1], cap[0])
    assert _same_curve(te[:, -1], cap[-1])
    # Mid-chord of the root stays on the analytic NACA. The opening does not thicken it.
    mid = len(p["xcs"]) // 2
    le_pt, c, t, ch, tc = root
    yt = float(np.asarray(naca_yt([p["xcs"][mid]], tc), float)[0]) * ch
    assert np.allclose(upper[mid, 0], le_pt + p["xcs"][mid] * ch * c + yt * t)
    assert root_y_offset(upper) > 1e-4
    assert root_y_offset(upper) < 0.01
    # The loft leading edge, before the mesh opening, is still on the centreline.
    assert abs(float(root[0][1])) < 1e-9
    sp = p["span_tip"]
    i, j = 6, 2
    n = np.cross(cap[i + 1, j] - cap[i, j], cap[i, j + 1] - cap[i, j])
    assert float(np.dot(n, sp)) > 0.0
    tip_u, tip_l = upper[:, -1], lower[::-1, -1]
    assert np.allclose(cap[:, 0], tip_u, atol=1e-12) or np.allclose(cap[:, -1], tip_u, atol=1e-12)
    assert np.allclose(cap[:, 0], tip_l, atol=1e-12) or np.allclose(cap[:, -1], tip_l, atol=1e-12)
    # The crest of the tip semicircle sits outboard of the tip airfoil.
    assert float(np.dot(cap[8, 2] - upper[8, -1], sp)) > 1.0e-4
    for name in ("upper", "lower", "tip", "le", "te"):
        di = np.linalg.norm(np.diff(p[name], axis=0), axis=-1)
        dj = np.linalg.norm(np.diff(p[name], axis=1), axis=-1)
        assert min(float(di.min()), float(dj.min())) > 1.0e-6
    counts = level_counts("coarse")
    assert (counts["n_chord"], counts["n_span"], counts["n_tip"], counts["n_layers"]) == (49, 33, 9, 49)
    assert cell_count(49, 33, 9, 49) == 2 * 48 * 32 * 48 + 48 * 8 * 48 + 2 * 8 * 32 * 48


def test_plot3d_surface_roundtrip(tmp_path):
    surf, _ = scaled_wing()
    patches = build_patches(surf, 9, 5, 3)
    path = tmp_path / "wing.fmt"
    write_plot3d_surface(patches, path)
    back = read_plot3d_surface(path)
    for name, got in zip(("upper", "lower", "tip", "le", "te"), back):
        assert got.shape[:2] == patches[name].shape[:2]
        assert np.allclose(got, patches[name])


def test_pyhyp_script_is_python(tmp_path):
    write_pyhyp_script(tmp_path / "extrude.py", "wing.fmt", 9, np.float64(1.0e-5), np.float64(2.0))
    text = (tmp_path / "extrude.py").read_text(encoding="utf-8")
    compile(text, "extrude.py", "exec")
    assert "np.float64" not in text
    assert "1e-05" in text
    assert "examples/m6/runM6.py" in text
    assert '"jLow": "ySymm"' in text
    assert "4: {\"jLow\": \"ySymm\"}" in text
    assert "5: {\"jLow\": \"ySymm\"}" in text
    assert "cornerAngle" not in text
    assert '"growthRatios"' not in text
    assert '"splay"' not in text
    assert '"epsE": 1.0' in text
    assert '"cMax": 5.0' in text
    write_pyhyp_script(tmp_path / "corner.py", "wing.fmt", 9, 1.0e-5, 2.0,
                       corner_angle=120.0, growth_ratio=1.338917634890977, splay=1.0)
    corner = (tmp_path / "corner.py").read_text(encoding="utf-8")
    compile(corner, "corner.py", "exec")
    assert '"cornerAngle": 120.0' in corner
    assert '"growthRatios": [1.338917634890977] * 8' in corner
    assert '"splay": 1.0' in corner
    assert "marchDist" in text
    write_pyhyp_script(tmp_path / "schedule.py", "wing.fmt", 5, 1.0e-5, 2.0,
                       eps_e=[4.0, 4.0, 8.0, 8.0])
    schedule = (tmp_path / "schedule.py").read_text(encoding="utf-8")
    compile(schedule, "schedule.py", "exec")
    assert '"epsE": [4.0, 4.0, 8.0, 8.0]' in schedule
    with pytest.raises(ValueError, match="N-1"):
        write_pyhyp_script(tmp_path / "bad.py", "wing.fmt", 5, 1.0e-5, 2.0, eps_e=[4.0])
    write_pyhyp_script(tmp_path / "cmax.py", "wing.fmt", 5, 1.0e-5, 2.0, c_max=1.5)
    limited = (tmp_path / "cmax.py").read_text(encoding="utf-8")
    compile(limited, "cmax.py", "exec")
    assert '"cMax": 1.5' in limited


def test_surface_case_uses_measured_march(tmp_path):
    surf, _ = scaled_wing()
    patches = build_patches(surf, 9, 5, 5)
    write_surface_case(tmp_path, "coarse", patches, 1.0e-5, 72.6)
    text = (tmp_path / "extrude.py").read_text(encoding="utf-8")
    compile(text, "extrude.py", "exec")
    assert '"epsE": 4.0' in text
    assert '"cMax": 0.5' in text
    assert '"cornerAngle": 150.0' in text
    assert '"N": 49' in text
    assert '"growthRatios"' not in text


def _slab(x0, ni=2, nj=2, nk=2):
    xyz = np.zeros((ni, nj, nk, 3))
    for i in range(ni):
        for j in range(nj):
            for k in range(nk):
                xyz[i, j, k] = (x0 + i, j, k)
    return {"xyz": xyz, "symmetry_at_j0": True}


def test_hex_block_has_unit_volume_and_matching_wall_winding(tmp_path):
    report = write_su2_volume([_slab(0.0), _slab(1.0)], tmp_path / "box.su2")
    assert report["n_hex"] == 2 and report["n_prism"] == 0
    assert report["points"] == 12
    assert report["min_volume"] == pytest.approx(1.0)
    assert report["winding_ok"]
    assert report["n_wing"] == 2 and report["n_symmetry"] == 2 and report["n_farfield"] == 2
    assert report["unmarked_boundary"] == 4
    assert report["watertight"] is False
    text = Path(report["mesh"]).read_text(encoding="ascii")
    assert "\n12 " in text or text.splitlines()[2].startswith("12 ")


def test_nonpositive_hex_volume_is_rejected_unless_a_floor_is_set(tmp_path):
    slab = _slab(0.0)
    slab["xyz"] = slab["xyz"][:, :, ::-1, :].copy()
    with pytest.raises(RuntimeError, match="non-positive cell volume"):
        write_su2_volume([slab], tmp_path / "bad.su2")
    report = write_su2_volume([slab], tmp_path / "floor.su2", reject_below=-2.0)
    assert report["min_volume"] < 0.0
    assert report["min_volume"] > -2.0


def test_collapsed_tip_edges_become_positive_prisms(tmp_path):
    ni, nj, nk = 4, 3, 3
    xyz = np.zeros((ni, nj, nk, 3))
    for i in range(ni):
        for j in range(nj):
            for k in range(nk):
                if i == 0 or i == ni - 1:
                    xyz[i, j, k] = (float(i), 0.0, float(k))
                else:
                    xyz[i, j, k] = (float(i), float(j), float(k))
    report = write_su2_volume([{"xyz": xyz, "symmetry_at_j0": False}], tmp_path / "tip.su2")
    assert report["n_prism"] == 2 * (nj - 1) * (nk - 1)
    assert report["n_hex"] == (ni - 3) * (nj - 1) * (nk - 1)
    assert report["min_volume"] > 0.0
    assert report["winding_ok"]
    body = Path(report["mesh"]).read_text(encoding="ascii")
    assert "\n13 " in body
    assert "\n5 " in body


def test_gci_3d_spacing_is_the_cube_root():
    ns = (8000, 1000, 125)
    hs = [(1.0 / n) ** (1.0 / 3.0) for n in ns]
    f = [1.0 + h ** 2 for h in hs]
    g = gci_3d(*f, *ns, drifts=(0.0, 0.0, 0.0))
    assert g["h"] == pytest.approx(hs)
    assert g["p"] == pytest.approx(2.0, rel=1e-6)
    assert g["h_definition"] == "(1/N)**(1/3)"
    assert g["iterative_ok"] is True


def test_one_alpha_inside_the_band_is_eligible_and_not_applied():
    lo, hi = H1_RATIO_BAND
    assert (lo, hi) == (0.7, 1.5)
    d = h1_factor_decision(0.55, 0.50, same_quantity=True, oscillatory=False, iterative_ok=True,
                           gci_defined=True, quantity="CL")
    assert d["eligible"] is True and d["decision"] == "nao_aplicar"
    assert 0.7 <= d["ratio"] <= 1.5
    rec = factor_record(d)
    assert rec["valid"] is False
    assert "polar" in rec["invalid_reason"]


def test_rejected_ratios_are_not_eligible():
    outside = h1_factor_decision(1.2, 0.5, same_quantity=True, oscillatory=False, iterative_ok=True,
                                 gci_defined=True, quantity="CL")
    assert outside["eligible"] is False and "rever o modelo" in outside["reason"]
    missing = h1_factor_decision(0.5, None, same_quantity=True, quantity="CL")
    assert missing["decision"] == "nao_aplicar" and missing["ratio"] is None
    zero = h1_factor_decision(0.5, 0.0, same_quantity=True, quantity="CL")
    assert "zero" in zero["reason"]
    other = h1_factor_decision(0.02, 0.01, same_quantity=False, quantity="CD",
                               why="CD RANS não é o CD invíscido do AVL")
    assert other["eligible"] is False and "AVL" in other["reason"]
    osc = h1_factor_decision(0.51, 0.50, same_quantity=True, oscillatory=True, iterative_ok=True,
                             gci_defined=False, quantity="CMy")
    assert osc["eligible"] is False and "GCI" in osc["reason"]


def test_rans_cfg_uses_half_area_and_isa():
    surf, _ = scaled_wing()
    ref = reference_quantities(surf)
    state = cruise_state(ref)
    mac = mac_quarter_chord(surf)
    cfg = su2_rans_cfg("wing.su2", 2.5, state, ref["S_m2"] / 2, ref["Cref_m"], mac["x_ref_m"])
    assert "SOLVER= RANS" in cfg and "KIND_TURB_MODEL= SA" in cfg
    assert f"REF_AREA= {ref['S_m2'] / 2:.6f}" in cfg
    assert f"REF_LENGTH= {ref['Cref_m']:.6f}" in cfg
    assert "MARKER_HEATFLUX= ( wing, 0.0 )" in cfg
    assert "CONV_RESIDUAL_MINVAL= -8" in cfg
    assert MESH_FAMILY["fine"]["yplus"] == 1.0
    assert MESH_FAMILY["coarse"]["yplus"] == 2.0
