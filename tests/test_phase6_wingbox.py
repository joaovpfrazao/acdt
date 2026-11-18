"""Phase 6 wing box: buckling sizing formulas against textbook values, rib sizing, and the shell-FEM calibration
consistency (FEM vs Megson section on a simple tapered wing)."""
import math

import numpy as np
import pytest

from acdt.domains.aircraft import structures as S
from acdt.domains.aircraft.geometry import TrapezoidalWing
from acdt.domains.aircraft.wingbox import shell6
from acdt.domains.aircraft.wingbox import sizing6 as Z
from acdt.core import sections as SEC

MET = Z.phase6_material("metal")
COMP = Z.phase6_material("composite")


def test_plate_k_textbook():
    # Timoshenko & Gere §9.2: k = 4 at a/b = 1, 2; k = 4.5 at a/b = √2 (m = 1/2 transition); 6.25 at a/b = 0.5
    assert Z._kplate(np.array(1.0), 1.0) == pytest.approx(4.0)
    assert Z._kplate(np.array(2.0), 1.0) == pytest.approx(4.0)
    assert Z._kplate(np.array(math.sqrt(2)), 1.0) == pytest.approx(4.5)
    assert Z._kplate(np.array(0.5), 1.0) == pytest.approx(6.25)


def test_z_crippling_matches_gerard():
    t_h, EF = 1 / 15, MET["E"] / MET["sigma_cap"]
    p = SEC.z_section(1.0, Z.Z_FLANGE, t_h, t_h)
    A = p.properties()["A"]
    ref = min(3.2 * ((t_h**2 / A) * EF ** (1 / 3)) ** 0.75, 1.0)       # Gerard 2-corner (Bruhn C7.7)
    assert Z._z_crippling_ratio(round(t_h, 5), round(EF, 1)) == pytest.approx(ref, rel=1e-3)


def test_metal_cover_meets_its_criteria():
    P = np.array([3e5, 1e5, 2e4])
    qT = np.array([2e4, 1e4, 3e3])
    w, h, L, n = np.array([0.7, 0.6, 0.45]), np.array([0.15, 0.12, 0.09]), 0.7, 10
    r = Z.metal_cover(P, qT, w, h, L, n, 0.15, MET["sigma_cap"], MET)
    b = w / (n + 1)
    E, nu = MET["E"], MET["nu"]
    s_cr = 4 * math.pi**2 * E / (12 * (1 - nu**2)) * (r["t_s"] / b) ** 2
    A_tot = r["A_cover"] + 2 * r["A_cap"]
    # no skin buckling at limit load (shear interaction only lowers s_cr → check the pure-compression bound)
    assert np.all(s_cr * A_tot >= P / 1.5 * 0.999)
    assert np.all(r["sigma"] <= MET["sigma_cap"] * 1.0001)
    # thicker for higher load; the ultimate variant is never lighter
    assert r["t_s"][0] > r["t_s"][1] > r["t_s"][2]
    ru = Z.metal_cover(P, qT, w, h, L, n, 0.15, MET["sigma_cap"], MET, skin_buckling="ultimate")
    assert np.all(ru["mass"] >= r["mass"] * 0.999)


def test_sandwich_allen_core_shear_limit():
    # N_cr = N_E/(1 + N_E/S) → crimping S when N_E ≫ S (Allen 1969; Zenkert 1995)
    P = np.array([3e4])
    r = Z.sandwich_cover(P, np.array([1e3]), np.array([0.1]), 0.4, COMP["sigma_cap"] / COMP["E"], COMP)
    tf, tc = float(r["t_f"][0]), float(r["t_core"][0])
    E, nu, Gc = COMP["E"], COMP["nu"], COMP["core"]["G"]
    d = tc + tf
    S_ = Gc * d**2 / tc
    D = E * tf * d**2 / (2 * (1 - nu**2))
    NE = Z._kplate(np.array(4.0), 1.0) * math.pi**2 * D / 0.1**2
    Ncr = NE / (1 + NE / S_)
    Nx = E * float(r["eps"][0]) * 2 * tf
    assert Nx <= Ncr * 1.01
    assert Ncr < min(NE, S_)


def test_rib_crushing_and_holes():
    # Niu §5.4: p = 2σ² t̄ L/(E h); wide column π²E t²/(12(1−ν²)h²) · t ≥ p
    sig, tb, h, L = 150e6, 3e-3, 0.15, 0.7
    r = Z.size_ribs([0.0], [sig], [tb * L], [h], [0.7], [10.0], MET)
    p = 2 * sig**2 * tb * L / (MET["E"] * h)
    assert r["p_crush"][0] == pytest.approx(p)
    t = r["t"][0]
    f = 1.0 if r["D_h"][0] == 0 else 0.5
    scr = math.pi**2 * MET["E"] * t**2 / (12 * (1 - MET["nu"] ** 2) * h**2)
    assert scr * t * f >= p * 0.999
    assert r["governs"][0] == "crushing"
    # lightly loaded rib → min gauge with the largest holes
    r2 = Z.size_ribs([0.0], [1e6], [1e-3], [0.15], [0.7], [1.0], MET)
    assert r2["t"][0] == MET["t_min_web"] and r2["D_h"][0] == 0.5


def test_cap_types_differ_at_slender_flanges():
    old = Z.CAP_BT
    try:
        Z.CAP_BT = 25.0
        a = {k: Z.cap_allowable(k, 0.15, 2e-4, 1e-3, MET) for k in Z.SPAR_TYPES}
        assert a["I"] > a["C"]           # T cap (two half-flanges) beats an angle with one wide free flange
        assert all(v <= MET["sigma_cap"] for v in a.values())
    finally:
        Z.CAP_BT = old


def _wing_case(kind):
    w = TrapezoidalWing(S=10.0, AR=8.0, taper=0.6, tc_root=0.15, tc_tip=0.12, airfoil="NACA 2412")
    w.box.front_spar_xc, w.box.rear_spar_xc, w.box.rib_pitch = 0.2, 0.65, 0.6
    y = np.linspace(0, w.span / 2, 41)
    c = S.chord_at(w, y)
    lift = 3.8 * 1000 * 9.81 / 2 * c / np.trapezoid(c, y)
    V = S._cum_from_tip(y, lift)
    M = S._cum_from_tip(y, V)
    T = S._cum_from_tip(y, -0.02 * c * lift)
    beam = S.BeamLoads(y, V, M, T)
    mat = Z.phase6_material(kind)
    x = {"xf": 0.2, "xr": 0.65, "rib_pitch": 0.6, "k_skin": 1.0, "phi_cap": 0.15, "n_str": 6}
    box = Z.size_box6(w, beam, mat, x, y0=0.6)
    return w, beam, mat, x, box


@pytest.mark.parametrize("kind", ["metal", "composite"])
def test_calibration_consistency(kind):
    w, beam, mat, x, box = _wing_case(kind)
    sec = Z.section6(w, box, mat, camber=(0.02, 0.4), y0=0.6, raw=True)
    cal, diag, sb = shell6.calibrate(w, box, mat, x, 0.6, (0.02, 0.4), sec, beam)
    inboard = cal.eta < 0.7
    # contour FEM and Megson section describe the same structure → factors near 1 away from the tip
    assert np.all((cal.k_EI[inboard] > 0.75) & (cal.k_EI[inboard] < 1.35))
    assert np.all((cal.k_GJ[inboard] > 0.7) & (cal.k_GJ[inboard] < 1.6))      # root bay: clamp (warping) restraint
    assert np.all(np.abs(cal.dx_sc[inboard]) < 0.06)
    assert np.all((cal.k_sigma[inboard] > 0.7) & (cal.k_sigma[inboard] < 1.3))
    # the calibrated beam reproduces the FEM: check with the design-like load case
    box.details["k_sigma"] = np.ones_like(box.y)
    secc = Z.section6(w, box, mat, camber=(0.02, 0.4), y0=0.6, calib=cal)
    lift = -np.gradient(beam.shear, beam.y)
    c = S.chord_at(w, beam.y)
    T = S._cum_from_tip(beam.y, lift * (secc["x_sc_c"] - 0.25) * c)       # lift at c/4 about the shear centre
    beam2 = S.BeamLoads(beam.y, beam.shear, beam.moment, T)
    chk = shell6.fem_check6(w, box, mat, x, 0.6, (0.02, 0.4), lift, np.zeros_like(beam.y), 0.0, beam2, secc)
    assert chk["tip_w_fem_m"] == pytest.approx(chk["tip_w_beam_m"], rel=0.05)
    assert chk["V0_N"] == pytest.approx(chk["V0_beam_N"], rel=0.03)
    assert chk["T0_fem_Nm"] == pytest.approx(chk["T0_beam_Nm"], rel=0.05)
    assert chk["tip_twist_fem_deg"] == pytest.approx(chk["tip_twist_beam_deg"], rel=0.25, abs=0.05)
    assert chk["root_bay_cover_force_fem_N"] == pytest.approx(chk["root_bay_cover_force_beam_N"], rel=0.15)


def test_rib_simp_demo():
    from acdt.domains.aircraft.wingbox.rib_simp import rib_simp
    r = rib_simp(0.4, 0.15, 3000.0, 500.0, nelx=40, iters=30)
    assert abs(r["vol"] - 0.4) < 0.01
    assert r["compliance"][-1] < 0.6 * r["compliance"][0]
    assert r["rho"].shape == (r["nely"], r["nelx"])


def test_buckling_reserve_factor_is_numeric_and_at_least_one():
    """Phase 6 reports a load-factor reserve for skins and ribs (sized to the criterion or min gauge)."""
    for kind in ("metal", "composite"):
        w, beam, mat, x, box = _wing_case(kind)
        br = box.details["buckling_reserve"]
        assert br["skin_RF_min"] >= 0.99
        assert br["rib_RF_min"] >= 0.99
        assert len(br["skin_RF"]) == len(box.y)
        assert len(br["rib_RF"]) == box.details["n_ribs_semispan"]
        # at least one rib RF is stored on the rib record too
        assert box.details["ribs"]["RF"][0] == pytest.approx(br["rib_RF"][0])
