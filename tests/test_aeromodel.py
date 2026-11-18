"""Fase 8b: modelo de voo tabelado (AVL α×flap, arrasto, perda, propulsão, massa)."""
import math

import numpy as np
import pytest

from acdt.domains.aircraft.aero.avl import avl_available
from acdt.domains.aircraft.flightsim.aeromodel import (TABLE_KEYS, AeroModel, FlightModel, Propulsion,
                                                       build_flight_model)

needs_avl = pytest.mark.requires_avl


def _toy(**kw):
    al = [-4.0, 0.0, 4.0, 8.0, 12.0]
    CLa, CL0, Cm0, Cma = 5.0, 0.2, 0.0, -1.0
    t = {k: [[0.0] * 5] for k in TABLE_KEYS}
    t["CL"] = [[CL0 + CLa * math.radians(a) for a in al]]
    t["Cm"] = [[Cm0 + Cma * math.radians(a) for a in al]]
    t["Cmde"] = [[-1.5] * 5]
    t["CLde"] = [[0.4] * 5]
    t["Cnb"] = [[0.08] * 5]
    t["CYb"] = [[-0.4] * 5]
    args = dict(S=16.0, b=11.0, c=1.5, x_ref=2.0, alpha_deg=al, flap_deg=[0.0], tables=t, CLmax=[1.5], CD0=0.03,
                K=0.05, flap_dCD0=[0.0], CLad=1.5, Cmad=-5.0, dx_fus=0.0, limits={})
    args.update(kw)
    return AeroModel(**args)


def test_linear_region_and_extrapolation():
    a = _toy()
    c = a.coefficients(math.radians(2), 0, 0, 0, 0, 0, math.radians(-5), 0, 0, 0.0, 2.0)
    CL = 0.2 + 5 * math.radians(2) + 0.4 * math.radians(-5)
    assert c["CL_lin"] == pytest.approx(CL)
    assert c["CD"] == pytest.approx(0.03 + 0.05 * CL**2, rel=1e-3)  # σ ≈ 0 well below stall
    # linear extrapolation beyond the AVL grid (−4..12°)
    assert a._interp("CL", math.radians(14), 0.0) == pytest.approx(0.2 + 5 * math.radians(14))


def test_cg_transfer_and_yaw_transfer():
    a = _toy()
    c0 = a.coefficients(math.radians(4), math.radians(5), 0, 0, 0, 0, 0, 0, 0, 0.0, 2.0)
    c1 = a.coefficients(math.radians(4), math.radians(5), 0, 0, 0, 0, 0, 0, 0, 0.0, 2.15)
    CN = c0["CL"] * math.cos(math.radians(4)) + c0["CD"] * math.sin(math.radians(4))
    assert c1["Cm"] - c0["Cm"] == pytest.approx(CN * 0.1, rel=1e-9)            # Δx = 0.1 c̄ aft
    assert c1["Cn"] - c0["Cn"] == pytest.approx(c0["CY"] * 0.15 / 11.0, rel=1e-9)  # side force ahead of CG


def test_stall_peak_matches_clmax_and_post_stall_flat_plate():
    a = _toy()
    cl = [a.coefficients(math.radians(x), 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 2.0)["CL"] for x in np.arange(-30, 45, 0.25)]
    assert max(cl) == pytest.approx(1.5, abs=0.01)
    assert min(cl) == pytest.approx(-0.8 * 1.5, abs=0.01)
    c90 = a.coefficients(math.radians(89), 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 2.0)
    assert c90["CD"] == pytest.approx(0.03 + 2 * math.sin(math.radians(89)) ** 3, rel=1e-3)


def test_propeller_thrust_low_speed_cap():
    p = Propulsion(kind="piston_prop", P_sl=100e3, T_sl=None, eta_cruise=0.8, eta_takeoff=0.55, V_low=20.0,
                   c_p=7e-8, c_t=None, eta_chain=1.0, P_sys=0.0)
    T0, mdot = p.thrust(0.0, 0.0, 1.0)
    assert T0 == pytest.approx(0.55 * 100e3 / 20.0)        # Raymer 17.8 mean take-off thrust
    assert p.thrust(60.0, 0.0, 1.0)[0] == pytest.approx(0.8 * 100e3 / 60.0)
    assert mdot == pytest.approx(7e-8 * 100e3)
    e = Propulsion(kind="electric", P_sl=1000.0, T_sl=None, eta_cruise=0.8, eta_takeoff=0.55, V_low=10.0, c_p=None,
                   c_t=None, eta_chain=0.8, P_sys=30.0)
    assert e.thrust(20.0, 1000.0, 0.5)[1] == pytest.approx(500 / 0.8 + 30)


@pytest.mark.slow
@needs_avl
def test_build_flight_model_c172(c172_result, tmp_path):
    fm = build_flight_model(c172_result)
    a = fm.aero
    d = {k: a.tables[k][0][2] for k in TABLE_KEYS}  # clean, α = 4°
    # standard signs (Etkin & Reid; Roskam): static stability and control power
    assert d["Cma"] < 0 and d["Cnb"] > 0 and d["Clb"] < 0 and d["CYb"] < 0
    assert d["Clp"] < 0 and d["Cmq"] < 0 and d["Cnr"] < 0
    assert d["Cmde"] < 0 and d["Clda"] > 0 and d["Cndr"] < 0 and d["CYdr"] > 0
    # flaps raise C_L at fixed α and add Raymer 12.61 drag only above 10°
    assert a.tables["CL"][-1][2] > a.tables["CL"][0][2]
    assert a.flap_dCD0[0] == 0.0 and a.flap_dCD0[-1] > 0
    assert a.CLmax == sorted(a.CLmax)
    assert fm.mass.m == pytest.approx(c172_result.sizing.W0, rel=0.02)
    fm2 = FlightModel.load(fm.save(tmp_path))
    c = dict(alpha=0.1, beta=0.05, p_hat=0.01, q_hat=0.02, r_hat=-0.01, ad_hat=0.0, de=-0.05, da=0.1, dr=0.05,
             flap=10.0, x_cg=fm.mass.x_cg)
    assert fm2.aero.coefficients(**c) == pytest.approx(a.coefficients(**c))
    fm3 = build_flight_model(c172_result, opts={"inertia_kgm2": {"Ixx": 1285.0}})
    assert fm3.mass.Ixx == pytest.approx(1285.0, rel=0.02)


def test_inertia_estimate_roskam_vs_components(c172_result):
    """Roskam Part V Eqs. 3.7-3.9 with Table B2 radii (Cessna 172M) vs the component sum.

    The reference is the JSBSim c172p empty tensor (948/1346/1967 slug·ft², 1500 lb, CG at 41 in;
    educational model, as its file header says) plus the point masses that make 2550 lb: front seats
    180 lb at 36 in, rear seats 160 lb at 70 in, 185 lb of fuel in each wing at 56 in and ±112 in.
    About the loaded CG that is 2770/1999/4150 kg·m². The band below uses 2770/2002/4153.

    Stations are the mission POH arms, the dict the flight model and the dynamic modes already pass.
    Roskam Iyy is then 2011 kg·m². The 2502.7 kg·m² figure is the same formula with the payload at
    50 % of L (the old default): on this geometry that arm gives 2500 kg·m², 24.9 % above 2002, and
    a slightly heavier layout crossed the band. That arm is not the C172 station. The reference stays.
    """
    from acdt.domains.aircraft.stability import ROSKAM_RADII, inertia_estimate
    assert ROSKAM_RADII["cessna_172m"] == pytest.approx((0.242, 0.386, 0.403))
    st = c172_result.stability
    mission = {"inertia_method": "roskam", "roskam_reference": "cessna_172m",
               "stations": c172_result.spec.assumptions["stability"]["stations"]}
    Ir, src, xc = inertia_estimate(c172_result, st, mission)
    Ic, src_c, _ = inertia_estimate(c172_result, st, {**mission, "inertia_method": "components"})
    bare, _, _ = inertia_estimate(c172_result, st, {"inertia_method": "roskam", "roskam_reference": "cessna_172m"})
    # The rear seat is aft of the fixed-mass CG, so the mission pitch inertia exceeds the balance default.
    assert Ir["Iyy"] > bare["Iyy"]
    assert "Roskam" in src and src != src_c
    for k, ref in (("Ixx", 2770.0), ("Iyy", 2002.0), ("Izz", 4153.0)):
        assert Ir[k] == pytest.approx(ref, rel=0.25)
        assert Ic[k] == pytest.approx(ref, rel=0.30)
        assert 0.6 < xc["ratio_components_over_roskam"][k] < 1.4
    # user-specified radii of gyration override the reference table
    Iu, _, _ = inertia_estimate(c172_result, st, {**mission, "radii_of_gyration": {"Rx": 0.30, "Ry": 0.386, "Rz": 0.403}})
    assert Iu["Ixx"] > Ir["Ixx"]


def test_propeller_calibration_in_sizing(c172_result):
    """Progressive calibration: propeller efficiencies replace the flat assumptions (fixed-pitch BEMT map)."""
    pc = c172_result.propeller_calibration["final"]
    assert len(c172_result.propeller_calibration["history"]) <= 5 and 0.3 < pc["eta_takeoff"] < pc["eta_climb"] < pc["eta_cruise"] < 0.92
    assert pc["_static_rpm"] == pytest.approx(2350, rel=0.02)    # calibrated to the POH static rpm
