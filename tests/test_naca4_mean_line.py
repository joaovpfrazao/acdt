"""Opt-in NACA 4-digit mean line. The default loft stays symmetric.

Abbott & von Doenhoff 1959, Eq. 6.4 (ordinate), Eq. 6.5 (slope) and Eq. 6.6 (surface).
No SU2 and no pyHyp. The example yaml is not edited.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from acdt.domains.aircraft.assembly.assembly import Assembly
from acdt.domains.aircraft.assembly.components import (
    Surface, camber_clearance, naca4_mean_line, naca4_section_code, naca4_surface, naca_yt,
)
from acdt.domains.aircraft.hifi.cfd import naca_coords
from acdt.domains.aircraft.hifi.wing_bl import (
    avl_text, build_patches, cruise_state, level_counts, mac_quarter_chord,
    reference_quantities, scaled_wing, su2_rans_cfg, verify_wing_rans_geometry,
)

EX = Path(__file__).resolve().parents[1] / "examples"


def _naca_cards(text: str) -> list[str]:
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


def test_zero_camber_is_the_symmetric_thickness_exactly():
    x = np.linspace(0.0, 1.0, 33)
    yc, dy = naca4_mean_line(x, 0.0, 0.0)
    assert np.array_equal(yc, np.zeros_like(x))
    assert np.array_equal(dy, np.zeros_like(x))
    xu, zu, xl, zl = naca4_surface(x, 0.15, 0.0, 0.4)
    yt = naca_yt(x, 0.15)
    assert np.array_equal(xu, x)
    assert np.array_equal(zu, yt)
    assert np.array_equal(xl, x)
    assert np.array_equal(zl, -yt)


def test_mean_line_matches_eq_6_4_through_6_6():
    """Digits of 4415: m = 0.04, p = 0.4. The ordinate at p is m, and the slope changes sign there."""
    m, p = 4 / 100, 4 / 10
    yc_p, dy_p = naca4_mean_line(p, m, p)
    assert yc_p == pytest.approx(m, abs=1e-15)
    assert dy_p == pytest.approx(0.0, abs=1e-15)
    x_fwd = 2 / 10
    yc_f, dy_f = naca4_mean_line(x_fwd, m, p)
    assert yc_f == pytest.approx((m / p**2) * (2 * p * x_fwd - x_fwd**2), abs=1e-15)
    assert dy_f == pytest.approx((2 * m / p**2) * (p - x_fwd), abs=1e-15)
    assert dy_f > 0.0
    x_aft = 7 / 10
    yc_a, dy_a = naca4_mean_line(x_aft, m, p)
    assert yc_a == pytest.approx(
        (m / (1 - p) ** 2) * (1 - 2 * p + 2 * p * x_aft - x_aft**2), abs=1e-15)
    assert dy_a == pytest.approx((2 * m / (1 - p) ** 2) * (p - x_aft), abs=1e-15)
    assert dy_a < 0.0
    assert naca4_mean_line(0.0, m, p)[0] == pytest.approx(0.0, abs=1e-15)
    assert naca4_mean_line(1.0, m, p)[0] == pytest.approx(0.0, abs=1e-15)
    xu, zu, xl, zl = naca4_surface(p, 0.15, m, p)
    yt = float(naca_yt(p, 0.15))
    assert float(xu) == pytest.approx(p, abs=1e-15)
    assert float(zu) == pytest.approx(m + yt, abs=1e-15)
    assert float(zl) == pytest.approx(m - yt, abs=1e-15)


def test_surface_matches_the_existing_four_digit_coordinates():
    """Same closed-TE thickness as cfd.naca_coords. Declared t/c wins over the name's thickness digit."""
    n = 81
    x = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n)))
    xu, zu, xl, zl = naca4_surface(x, 0.15, 0.04, 0.4)
    loop = np.vstack([
        np.column_stack([xu[::-1], zu[::-1]]),
        np.column_stack([xl[1:], zl[1:]]),
    ])
    assert np.allclose(loop, naca_coords("4415", n), atol=1e-12)
    xu, zu, xl, zl = naca4_surface(x, 0.12, 0.04, 0.4)
    loop = np.vstack([
        np.column_stack([xu[::-1], zu[::-1]]),
        np.column_stack([xl[1:], zl[1:]]),
    ])
    assert np.allclose(loop, naca_coords("4412", n), atol=1e-12)
    assert not np.allclose(loop, naca_coords("4415", n), atol=1e-6)


def test_p0_and_unknown_names_are_refused_and_do_not_mutate():
    with pytest.raises(ValueError, match="p = 0"):
        naca4_mean_line(0.2, 0.04, 0.0)
    panel = Surface.panel(
        "rect", 1.0, 1.0, 2.0, tc_root=0.15, tc_tip=0.12, airfoil="NACA 4415")
    for name in ("NACA 0015", "NACA 4015", "NACA 23012", "Clark Y", "naca4"):
        panel.airfoil = name
        with pytest.raises(ValueError):
            panel.with_naca4_mean_line()
        assert panel.naca4_mean_line is False
    with pytest.raises(ValueError):
        naca4_section_code(4, 0, 0.15)
    with pytest.raises(ValueError):
        naca4_section_code(0, 4, 0.15)


def test_opt_in_writes_camber_digits_and_declared_thickness():
    base, _meta = scaled_wing()
    assert base.naca4_mean_line is False
    cam, rec = base.with_naca4_mean_line()
    assert base.naca4_mean_line is False
    assert cam.naca4_mean_line is True
    assert cam.airfoil == "NACA 4415"
    assert cam.sections[0]["tc"] == pytest.approx(0.15)
    assert cam.sections[-1]["tc"] == pytest.approx(0.12)
    assert cam.planform_area() == pytest.approx(base.planform_area(), abs=0.0)
    assert rec["camber"] == "construida"
    assert rec["m"] == pytest.approx(0.04)
    assert rec["p"] == pytest.approx(0.4)
    assert rec["naca_root"] == "4415" and rec["naca_tip"] == "4412"
    assert any(p.startswith("PRESSUPOSTO:") for p in rec["pressupostos"])
    ref = {"S_m2": 3.186, "Cref_m": 0.72709, "Bref_m": 4.3819}
    text = avl_text(cam, ref, 0.0, 0.98)
    assert _naca_cards(text) == ["4415", "4412"]
    assert "CLAF" not in text
    assert "linha média construída" in text
    assert "não é construída" not in text
    plain = avl_text(base, ref, 0.0, 0.98)
    assert _naca_cards(plain) == ["0015", "0012"]
    assert "não é construída" in plain


def test_intermediate_station_rounds_thickness_and_keeps_camber():
    drawing = json.loads(
        (EX / "integration" / "flying_wing_pusher_tailless.json").read_text(encoding="utf-8"))
    loaded = Assembly.from_dict(drawing["assembly"])
    surf = next(c for c in loaded.components if c.name == "wing" and not c.mirrored_image)
    cam, rec = surf.with_naca4_mean_line()
    text = Assembly([cam], expand_mirror=False).avl_text(
        ref={"Sref": 1.0, "Cref": 1.0, "Bref": 2.0})
    assert _naca_cards(text) == ["4415", "4414", "4412"]
    assert rec["naca_tip"] == "4412"
    assert surf.naca4_mean_line is False
    still_plain = Assembly.from_dict(drawing["assembly"]).avl_text()
    assert _naca_cards(still_plain) == ["0015", "0014", "0012"]


def test_declared_thickness_does_not_switch_the_opt_in():
    panel = Surface.panel(
        "rect", 1.0, 1.0, 2.0, tc_root=0.15, tc_tip=0.12, airfoil="NACA 4415")
    plain, rec = panel.with_declared_thickness(0.16, 0.10, airfoil="NACA 2412")
    assert plain.naca4_mean_line is False and rec["camber"] == "lacuna"
    cam, _ = panel.with_naca4_mean_line()
    still, rec2 = cam.with_declared_thickness(0.16, 0.10)
    assert still.naca4_mean_line is True
    assert rec2["camber"] == "construida"
    assert rec2["naca_root"] == "4416" and rec2["naca_tip"] == "4410"
    with pytest.raises(ValueError):
        cam.with_declared_thickness(0.16, 0.10, airfoil="Clark Y")
    assert cam.airfoil == "NACA 4415" and cam.naca4_mean_line is True


def test_clearance_on_the_mean_line_and_flat_when_m_is_zero():
    xi = np.array([0.3, -0.1, 1.2])
    ze = np.array([0.01, 0.0, -0.02])
    got = camber_clearance(xi, ze, 0.12, 1.0, 0.0, 0.4)
    yt = naca_yt(xi, 0.12)
    sym = yt - np.abs(ze)
    sym = np.where((xi < 0.0) | (xi > 1.0), -np.maximum(-xi, xi - 1.0) - np.abs(ze), sym)
    assert np.allclose(got, sym, atol=1e-9)

    m, p, tc = 0.04, 0.4, 0.15
    x = 0.25
    xu, zu, _xl, _zl = naca4_surface(x, tc, m, p)
    on = camber_clearance(float(xu), float(zu), tc, 1.0, m, p)
    assert float(on) == pytest.approx(0.0, abs=1e-8)
    above = camber_clearance(float(xu), float(zu) + 0.01, tc, 1.0, m, p)
    assert float(above) < -1e-3
    panel = Surface.panel(
        "rect", 1.0, 1.0, 2.0, tc_root=tc, tc_tip=tc, airfoil="NACA 4415")
    cam, _ = panel.with_naca4_mean_line()
    point = [[float(xu), 1.0, float(zu)]]
    assert cam.contains(point)[0] == pytest.approx(0.0, abs=1e-6)
    assert panel.contains(point)[0] < 0.0
    z_plain = float(np.max(panel.mesh()[0][:, 2]))
    z_cam = float(np.max(cam.mesh()[0][:, 2]))
    assert z_cam > z_plain + 0.02


def test_cambered_patches_keep_the_chord_and_the_section():
    base, _ = scaled_wing()
    cam, rec = base.with_naca4_mean_line()
    p = build_patches(cam, n_chord=17, n_span=9, n_tip=9)
    upper, lower = p["upper"], p["lower"]
    le, c, t, ch, tc = p["frames"][0]
    assert np.allclose(0.5 * (upper[0, 0] + lower[-1, 0]), le, atol=1e-12)
    assert np.allclose(0.5 * (upper[-1, 0] + lower[0, 0]), le + ch * c, atol=1e-12)
    i = len(p["xcs"]) // 2
    x = float(p["xcs"][i])
    xu, zu, _xl, _zl = naca4_surface(x, tc, rec["m"], rec["p"])
    expect = le + float(xu) * ch * c + float(zu) * ch * t
    assert np.allclose(upper[i, 0], expect, atol=1e-12)
    plain = build_patches(base, n_chord=17, n_span=9, n_tip=9)
    assert np.linalg.norm(upper[i, 0] - plain["upper"][i, 0]) > 1e-3
    # The symmetric family is the same code path as before this opt-in.
    mid = len(plain["xcs"]) // 2
    ple, pc, pt, pch, ptc = plain["frames"][0]
    yt = float(np.asarray(naca_yt([plain["xcs"][mid]], ptc), float)[0]) * pch
    assert np.array_equal(
        plain["upper"][mid, 0], ple + plain["xcs"][mid] * pch * pc + yt * pt)


def test_example_yaml_stays_symmetric():
    spec = yaml.safe_load(
        (EX / "heavy" / "uav150_flying_wing_tailless.yaml").read_text(encoding="utf-8"))
    assert spec["assumptions"]["aero"]["airfoil"] == "NACA 4415"
    assert spec["assumptions"]["aero"]["tc_root"] == 0.15
    assert spec["assumptions"]["aero"]["tc_tip"] == 0.12
    wing, _ = scaled_wing()
    assert wing.naca4_mean_line is False


def test_cambered_coarse_surface_passes_the_geometry_gate():
    base, _ = scaled_wing()
    cam, _rec = base.with_naca4_mean_line()
    counts = level_counts("coarse")
    patches = build_patches(cam, counts["n_chord"], counts["n_span"], counts["n_tip"])
    ref = reference_quantities(cam)
    state = cruise_state(ref)
    x_ref = mac_quarter_chord(cam)["x_ref_m"]
    text = avl_text(cam, ref, state["Mach"], x_ref)
    assert _naca_cards(text) == ["4415", "4412"]
    cfg = su2_rans_cfg("wing.su2", 9.52057, state, ref["S_m2"] / 2.0, ref["Cref_m"], x_ref)
    report = verify_wing_rans_geometry(patches, text, cfg, cmy=None, cm_avl=None)
    assert report["pode_correr"] is True
    failed = [c["id"] for c in report["checks"] if c["status"] == "falha"]
    assert failed == []
