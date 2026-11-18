"""Phase 6: material library (isotropic + CLT equivalents) and parametric thin-walled sections vs textbook values."""
import math

import pytest

from acdt.core import materials as M
from acdt.core import sections as S


def test_metals_match_mil_hdbk_5j():
    m = M.get("al7075_t6")
    assert m.Ftu == pytest.approx(78 * M.KSI) and m.E == pytest.approx(10.3e6 * 6894.757, rel=1e-6)
    s = M.get("steel_4130")
    assert s.Fty == pytest.approx(75 * M.KSI) and s.rho == pytest.approx(7834, rel=2e-3)
    assert M.get("al2024_t3").E == 72.4e9


def test_quasi_isotropic_clt_is_isotropic():
    lam = M.LAMINA["AS4/3501-6"]
    c = M.clt_engineering_constants(lam, M.QUASI_ISO)
    assert c["Ex"] == pytest.approx(c["Ey"], rel=1e-9)
    # quasi-isotropic laminate: G = E / 2(1+ν) exactly (Jones 1999 §4.6)
    assert c["Gxy"] == pytest.approx(c["Ex"] / (2 * (1 + c["nu_xy"])), rel=1e-9)
    # invariant form: E_QI between the Voigt-like bounds
    assert lam["E2"] < c["Ex"] < lam["E1"] / 2


def test_composite_equivalent_allowables_from_strain_cutoff():
    m = M.get("cfrp_qi")
    cut = M.STRAIN_CUTOFF
    assert m.Fcy == pytest.approx(cut["k_env"] * cut["eps_c"] * m.E)
    assert m.kind == "composite_equivalent" and m.laminate["angles_half_stack"] == [0, 45, -45, 90]
    cap = M.get("cfrp_cap")
    assert cap.E > 1.8 * m.E        # UD-rich cap laminate is much stiffer spanwise
    d = M.composite_box_material()
    assert d["E_cap"] == cap.E and d["core"]["G"] == 27e6


H, B, T = 0.1, 0.05, 0.002          # mid-line web height, flange width, thickness


def test_channel_shear_centre_and_warping():
    p = S.channel(H + T, B + T / 2, T, T).properties()
    assert -p["y_sc"] == pytest.approx(3 * B ** 2 / (H + 6 * B), rel=1e-9)        # Megson Ex. 17.x / Roark
    assert p["Gamma"] == pytest.approx(T * B ** 3 * H ** 2 / 12 * (3 * B + 2 * H) / (6 * B + H), rel=1e-9)
    assert p["J"] == pytest.approx((H + 2 * B) * T ** 3 / 3, rel=1e-9)


def test_i_and_z_sections():
    p = S.i_section(H + T, B, T, T).properties()
    assert p["Gamma"] == pytest.approx(T * B ** 3 * H ** 2 / 24, rel=1e-9)
    assert p["Iyy"] == pytest.approx(T * H ** 3 / 12 + 2 * B * T * (H / 2) ** 2, rel=1e-9)
    assert abs(p["y_sc"]) < 1e-12 and abs(p["z_sc"]) < 1e-12
    z = S.z_section(H + T, B + T / 2, T, T).properties()
    assert abs(z["y_sc"]) < 1e-12 and abs(z["z_sc"]) < 1e-12                       # antisymmetric → centroid
    assert z["Gamma"] == pytest.approx(T * B ** 3 * H ** 2 * (B + 2 * H) / (12 * (2 * B + H)), rel=1e-9)
    assert z["Iyz"] != 0


def test_closed_tubes_bredt():
    r = S.rect_tube(0.1 + T, 0.05 + T, T).properties()
    assert r["J"] == pytest.approx(2 * T * (0.05 * 0.1) ** 2 / 0.15, rel=1e-9)
    c = S.circular_tube(0.1 + T, T, n=720).properties()
    assert c["J"] == pytest.approx(2 * math.pi * 0.05 ** 3 * T, rel=1e-4)
    assert c["Iyy"] == pytest.approx(math.pi * 0.05 ** 3 * T, rel=1e-4)


def test_local_buckling_and_crippling():
    E, Fcy = 72.4e9, 269e6
    ang = S.angle(0.03, 0.03, 0.002)
    lb = ang.local_buckling(E, 0.33)["sigma_cr"]
    b = 0.03 - 0.001
    assert lb == pytest.approx(0.43 * math.pi ** 2 * E / (12 * (1 - 0.33 ** 2)) * (0.002 / b) ** 2, rel=1e-9)
    # Gerard multi-corner, angle g = 2
    A = 2 * b * 0.002
    r = 0.56 * ((2 * 0.002 ** 2 / A) * math.sqrt(E / Fcy)) ** 0.85
    assert ang.crippling(E, Fcy)["ratio"] == pytest.approx(r, rel=1e-9)
    # thicker sections cripple at higher stress; capped at Fcy
    assert S.angle(0.03, 0.03, 0.004).crippling(E, Fcy)["Fcs"] > ang.crippling(E, Fcy)["Fcs"]
    assert S.angle(0.02, 0.02, 0.006).crippling(E, Fcy)["Fcs"] == pytest.approx(Fcy)
    # Needham cross-check within the usual scatter (± 25 %) of Gerard for a mid-slenderness angle
    n = ang.crippling(E, Fcy, method="needham")["Fcs"]
    assert 0.75 < n / ang.crippling(E, Fcy)["Fcs"] < 1.33
    # NASA SP-8007 knock-down for a thin tube
    tb = S.circular_tube(0.1, 0.001).local_buckling(E, 0.33)
    phi = math.sqrt(0.0495 / 0.001) / 16
    assert tb["gamma_SP8007"] == pytest.approx(1 - 0.901 * (1 - math.exp(-phi)), rel=1e-9)


@pytest.mark.parametrize("kind", ["I", "C", "Z", "builtup"])
def test_spar_cap_allowables(kind):
    E, Fcy = 72.4e9, 269e6
    a = S.spar_cap_allowable(kind, 0.15, 0.05, 0.004, 0.0016, E, Fcy)
    assert 0.2 * Fcy < a["F"] <= Fcy
    thick = S.spar_cap_allowable(kind, 0.15, 0.05, 0.008, 0.0016, E, Fcy)
    assert thick["F"] >= a["F"]
    comp = S.spar_cap_allowable(kind, 0.15, 0.05, 0.004, 0.0016, 111e9, 312e6, composite=True)
    assert comp["F"] <= 312e6 and comp["Fcs"] is None
    assert S.cap_area(kind, 0.05, 0.004) > 0
