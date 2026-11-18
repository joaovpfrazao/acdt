"""Wing RANS geometry gate. No SU2 and no AVL process: the mesh is the loft, the AVL file is text."""
import math

import numpy as np
import pytest

from acdt.domains.aircraft.assembly.components import Surface, naca_yt
from acdt.domains.aircraft.hifi.cfd import launch_wing_rans
from acdt.domains.aircraft.hifi.wing_bl import (
    INCIDENCE_TOL_DEG, WingGeometryError, _global_frame, avl_text, build_patches,
    cruise_state, mac_quarter_chord, parse_avl_geometry, reference_quantities,
    su2_rans_cfg, verify_wing_rans_geometry,
)


def _case(surf, n_chord=11, n_span=7, n_tip=5, flip_i=False, patches=None):
    ref = reference_quantities(surf)
    mac = mac_quarter_chord(surf)
    state = cruise_state(ref)
    text = avl_text(surf, ref, state["Mach"], mac["x_ref_m"])
    if patches is None:
        patches = build_patches(surf, n_chord, n_span, n_tip, flip_i=flip_i)
    area = ref["S_m2"] / 2.0 if surf.mirror else ref["S_m2"]
    cfg = su2_rans_cfg("wing.su2", 3.0, state, area, ref["Cref_m"], mac["x_ref_m"])
    return patches, text, cfg, ref


def _frames_patches(surf):
    """Upper/lower on the real sections, including a crank the straight loft does not build."""
    frames = [_global_frame(surf, fr) for fr in surf._frames()]
    xcs = np.linspace(0.0, 1.0, 7)
    upper = np.zeros((len(xcs), len(frames), 3))
    lower = np.zeros_like(upper)
    for j, (le, c, t, ch, tc) in enumerate(frames):
        yt = np.asarray(naca_yt(xcs, tc), float) * ch
        upper[:, j] = le + xcs[:, None] * ch * c + yt[:, None] * t
        xr = xcs[::-1]
        lower[:, j] = le + xr[:, None] * ch * c - yt[::-1][:, None] * t
    return {"upper": upper, "lower": lower}


def _check(report, cid):
    return next(c for c in report["checks"] if c["id"] == cid)


def test_flying_wing_matches_avl_and_the_run_is_called():
    from acdt.domains.aircraft.hifi.wing_bl import scaled_wing
    surf, _ = scaled_wing()
    patches, text, cfg, ref = _case(surf)
    called = []
    out = launch_wing_rans(patches, text, cfg, lambda: called.append("su2") or "correu")
    assert called == ["su2"] and out["result"] == "correu"
    report = out["geometry"]
    assert report["pode_correr"] is True
    assert report["aprovacao_completa"] is False
    sign = _check(report, "sinal_cmy")
    assert sign["status"] == "nao_avaliado" and sign["passou"] is False and sign["bloqueia"] is False
    by_role = {}
    for s in report["sections"]:
        by_role.setdefault(s["papel"], []).append(s)
    assert set(by_role) == {"raiz", "intermedia", "ponta"}
    tip = by_role["ponta"][0]
    assert tip["ainc_avl_deg"] == pytest.approx(-10.0, abs=1e-6)
    assert tip["incidencia_deg"] == pytest.approx(-10.0, abs=1e-6)
    assert abs(tip["erro_deg"]) < INCIDENCE_TOL_DEG
    # Dihedral moves the x-z projection off Ainc. That number is not the decision.
    assert abs(tip["incidencia_xz_deg"] - tip["ainc_avl_deg"]) > 1e-4
    assert _check(report, "area_sref")["area_malha_m2"] == pytest.approx(ref["S_m2"], rel=1e-9)
    assert _check(report, "envergadura_bref")["envergadura_m"] == pytest.approx(ref["Bref_m"], rel=1e-5)
    assert _check(report, "ref_origin")["status"] == "passa"
    assert report["tolerances"]["incidence_deg"] == 0.05


def test_another_wing_with_nose_up_twist_passes():
    surf = Surface.panel(
        "wing", 1.4, 0.7, 5.0, sweep_le_deg=18.0, dihedral_deg=4.0,
        tc_root=0.16, tc_tip=0.11, twist_tip_deg=4.0, n_sections=2, origin=(0.3, 0.0, 0.0),
        mirror=True)
    patches, text, cfg, ref = _case(surf, n_span=5)
    report = verify_wing_rans_geometry(patches, text, cfg, cmy=0.02, cm_avl=0.01)
    assert report["aprovacao_completa"] is True
    tip = [s for s in report["sections"] if s["papel"] == "ponta"][0]
    assert tip["incidencia_deg"] == pytest.approx(4.0, abs=1e-6)
    assert tip["incidencia_deg"] > 0.0


def test_unmirrored_wing_uses_sref_not_half():
    surf = Surface.panel(
        "wing", 0.8, 0.5, 2.5, sweep_le_deg=0.0, dihedral_deg=-2.0,
        tc_root=0.12, tc_tip=0.12, twist_tip_deg=-3.0, n_sections=2, mirror=False)
    patches, text, cfg, ref = _case(surf)
    assert "YDUPLICATE" not in text
    report = verify_wing_rans_geometry(patches, text, cfg)
    assert report["yduplicate"] is False
    assert _check(report, "ref_area")["esperado_m2"] == pytest.approx(ref["S_m2"], rel=1e-6)
    assert _check(report, "area_sref")["passou"] is True


def test_cranked_sections_match_when_the_mesh_follows_them():
    surf = Surface(name="crank", sections=[
        {"le": [0.2, 0.0, 0.0], "chord": 1.0, "twist_deg": 1.0, "tc": 0.15},
        {"le": [0.5, 1.2, 0.08], "chord": 0.7, "twist_deg": -2.0, "tc": 0.13},
        {"le": [1.1, 2.4, 0.05], "chord": 0.45, "twist_deg": -6.5, "tc": 0.10},
    ], mirror=True)
    patches, text, cfg, ref = _case(surf, patches=_frames_patches(surf))
    parsed = parse_avl_geometry(text)
    assert len(parsed["surfaces"][0]["sections"]) == 3
    report = verify_wing_rans_geometry(patches, text, cfg)
    assert report["pode_correr"] is True
    tips = [s["incidencia_deg"] for s in report["sections"]]
    assert tips[0] == pytest.approx(1.0, abs=1e-5)
    assert tips[1] == pytest.approx(-2.0, abs=1e-5)
    assert tips[2] == pytest.approx(-6.5, abs=1e-5)
    assert _check(report, "area_sref")["area_malha_m2"] == pytest.approx(ref["S_m2"], rel=1e-9)


def test_index_flip_does_not_change_the_decision():
    surf = Surface.panel(
        "wing", 1.0, 0.5, 3.0, sweep_le_deg=10.0, dihedral_deg=1.0,
        twist_tip_deg=-5.0, n_sections=2, mirror=True)
    a, text, cfg, _ = _case(surf, flip_i=False)
    b, _, _, _ = _case(surf, flip_i=True)
    ra = verify_wing_rans_geometry(a, text, cfg)
    rb = verify_wing_rans_geometry(b, text, cfg)
    assert [s["incidencia_deg"] for s in ra["sections"]] == pytest.approx(
        [s["incidencia_deg"] for s in rb["sections"]])


def test_opposite_twist_blocks_and_does_not_launch():
    good = Surface.panel(
        "wing", 1.1, 0.55, 3.2, sweep_le_deg=12.0, dihedral_deg=2.0,
        twist_tip_deg=-8.0, n_sections=2, mirror=True)
    bad = Surface.panel(
        "wing", 1.1, 0.55, 3.2, sweep_le_deg=12.0, dihedral_deg=2.0,
        twist_tip_deg=8.0, n_sections=2, mirror=True)
    _patches, text, cfg, _ref = _case(good)
    wrong, _, _, _ = _case(bad)
    called = []
    with pytest.raises(WingGeometryError) as exc:
        launch_wing_rans(wrong, text, cfg, lambda: called.append("su2"))
    assert called == []
    report = exc.value.report
    assert report["pode_correr"] is False
    assert _check(report, "incidencia")["status"] == "falha"
    tip = [s for s in report["sections"] if s["papel"] == "ponta"][0]
    assert tip["incidencia_deg"] == pytest.approx(8.0, abs=0.05)
    assert tip["ainc_avl_deg"] == pytest.approx(-8.0, abs=1e-3)


def test_reversed_span_fails():
    surf = Surface.panel("wing", 1.0, 0.6, 2.0, twist_tip_deg=-2.0, n_sections=2, mirror=True)
    patches, text, cfg, _ = _case(surf)
    flipped = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in patches.items()}
    flipped["upper"] = patches["upper"].copy()
    flipped["lower"] = patches["lower"].copy()
    flipped["upper"][..., 1] *= -1.0
    flipped["lower"][..., 1] *= -1.0
    with pytest.raises(WingGeometryError) as exc:
        verify_wing_rans_geometry(flipped, text, cfg)
    assert _check(exc.value.report, "eixo_envergadura_y")["status"] == "falha"


def test_reference_mismatches_block():
    surf = Surface.panel("wing", 1.2, 0.6, 4.0, sweep_le_deg=5.0, dihedral_deg=1.0,
                         twist_tip_deg=-4.0, n_sections=2, mirror=True)
    patches, text, cfg, ref = _case(surf)
    mac = mac_quarter_chord(surf)
    sref_line = f"{ref['S_m2']:.5f} {ref['Cref_m']:.5f} {ref['Bref_m']:.5f}"
    bad_area = text.replace(sref_line, f"{ref['S_m2'] * 1.25:.5f} {ref['Cref_m']:.5f} {ref['Bref_m']:.5f}", 1)
    with pytest.raises(WingGeometryError) as exc:
        verify_wing_rans_geometry(patches, bad_area, cfg)
    assert _check(exc.value.report, "area_sref")["status"] == "falha"

    bad_slip = cfg.replace("SIDESLIP_ANGLE= 0.0", "SIDESLIP_ANGLE= 2.0", 1)
    with pytest.raises(WingGeometryError) as exc:
        verify_wing_rans_geometry(patches, text, bad_slip)
    assert _check(exc.value.report, "eixo_aoa_xz")["status"] == "falha"

    bad_origin = cfg.replace(f"REF_ORIGIN_MOMENT_X= {mac['x_ref_m']:.6f}",
                             f"REF_ORIGIN_MOMENT_X= {mac['x_ref_m'] + 0.25:.6f}", 1)
    with pytest.raises(WingGeometryError) as exc:
        verify_wing_rans_geometry(patches, text, bad_origin)
    assert _check(exc.value.report, "ref_origin")["status"] == "falha"
    assert "em falta" not in _check(exc.value.report, "ref_origin")["motivo"]

    missing = cfg.replace(f"REF_ORIGIN_MOMENT_X= {mac['x_ref_m']:.6f}\n", "", 1)
    with pytest.raises(WingGeometryError) as exc:
        verify_wing_rans_geometry(patches, text, missing)
    motivo = _check(exc.value.report, "ref_origin")["motivo"]
    assert "em falta" in motivo and "zero" in motivo

    no_sym = cfg.replace("MARKER_SYM= ( symmetry )\n", "", 1)
    with pytest.raises(WingGeometryError) as exc:
        verify_wing_rans_geometry(patches, text, no_sym)
    assert _check(exc.value.report, "simetria_y0")["status"] == "falha"


def test_moment_sign_disagreement_blocks_and_zero_does_not_pass():
    surf = Surface.panel("wing", 1.0, 0.5, 3.0, twist_tip_deg=0.0, n_sections=2, mirror=True)
    patches, text, cfg, _ = _case(surf)
    same = verify_wing_rans_geometry(patches, text, cfg, cmy=-0.012, cm_avl=-0.005)
    assert _check(same, "sinal_cmy")["status"] == "passa"
    assert same["aprovacao_completa"] is True
    called = []
    with pytest.raises(WingGeometryError) as exc:
        launch_wing_rans(patches, text, cfg, lambda: called.append(1), cmy=0.01, cm_avl=-0.02)
    assert called == []
    assert _check(exc.value.report, "sinal_cmy")["status"] == "falha"
    zero = verify_wing_rans_geometry(patches, text, cfg, cmy=0.0, cm_avl=-0.01)
    sign = _check(zero, "sinal_cmy")
    assert sign["status"] == "nao_avaliado" and sign["passou"] is False and sign["bloqueia"] is False
    assert zero["pode_correr"] is True and zero["aprovacao_completa"] is False


def test_incomplete_avl_section_is_not_zero_incidence():
    surf = Surface.panel("wing", 1.0, 0.5, 3.0, twist_tip_deg=-10.0, n_sections=2, mirror=True)
    _patches, text, _cfg, _ref = _case(surf)
    broken = text.replace("-10.000", "", 1)
    with pytest.raises(ValueError, match="não é zero"):
        parse_avl_geometry(broken)


def test_two_stations_do_not_count_as_an_intermediate():
    surf = Surface.panel("wing", 1.0, 0.5, 3.0, twist_tip_deg=-2.0, n_sections=2, mirror=True)
    patches, text, cfg, _ = _case(surf, n_span=2, n_tip=3)
    with pytest.raises(WingGeometryError) as exc:
        verify_wing_rans_geometry(patches, text, cfg)
    assert "intermédia" in _check(exc.value.report, "incidencia")["motivo"]


def test_several_surfaces_need_a_name():
    surf = Surface.panel("wing", 1.0, 0.5, 3.0, twist_tip_deg=0.0, n_sections=2, mirror=True)
    patches, text, cfg, _ = _case(surf)
    tail = (
        "SURFACE\n"
        "tail\n"
        "SECTION\n"
        "3.00000 0.00000 0.00000 0.40000 0.000\n"
        "NACA\n"
        "0012\n"
        "SECTION\n"
        "3.20000 0.80000 0.00000 0.25000 0.000\n"
        "NACA\n"
        "0010\n"
    )
    two = text + tail
    with pytest.raises(ValueError, match="várias superfícies"):
        verify_wing_rans_geometry(patches, two, cfg)
    report = verify_wing_rans_geometry(patches, two, cfg, surface="wing")
    assert report["surface"] == "wing"
    assert report["pode_correr"] is True
