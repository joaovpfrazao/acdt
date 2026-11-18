# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Tailless gear (12 nov 2026): nose-up stance option of gear_layout (opt-in), Sadraey 2012 Sec. 9.6.2 take-off
rotation moment balance / fly-off stance, nose-strut extension in the 6-DOF ground model."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly.sizing import gear_layout

EX = Path(__file__).resolve().parents[1] / "examples"
TL = json.loads((EX / "integration" / "flying_wing_pusher_tailless.json").read_text(encoding="utf-8"))
CGF, CGA = [0.86, 0.0, -0.035], [0.875, 0.0, -0.035]


def _strip(g):
    return {k: v for k, v in g.items() if k != "checks"}, [(c[0], c[1]) for c in g["checks"]]


def test_level_stance_is_unchanged():
    asm = Assembly.from_dict(TL["assembly"])
    a = gear_layout(asm, CGF, CGA, dict(TL["gear"]))
    b = gear_layout(asm, CGF, CGA, {**TL["gear"], "ground_attitude_deg": 0.0})
    assert _strip(a) == _strip(b)                       # opt-in: θ_g = 0 reproduces the level layout exactly
    assert "nose_strut_extension_m" not in a and "ground_attitude_deg" not in a


def test_nose_up_stance_geometry():
    asm = Assembly.from_dict(TL["assembly"])
    lv = gear_layout(asm, CGF, CGA, dict(TL["gear"]))
    th = 19.0
    g = gear_layout(asm, CGF, CGA, {**TL["gear"], "ground_attitude_deg": th, "half_track": 0.48})
    t = math.radians(th)
    ck = {c[0]: c[1] for c in g["checks"]}
    d, h = g["x_main"] - CGA[0], g["h_cg"]
    # tip-back off the vertical in the static attitude = atan(d/h) − θ_g (Raymer Ch. 11, 15°)
    assert math.degrees(math.atan2(d, h)) - th == pytest.approx(15.0, abs=1e-6) and ck["asm:gear_tipback"]
    assert g["tipback_deg"] == pytest.approx(15.0, abs=1e-6)
    assert g["nose_strut_extension_m"] == pytest.approx((g["x_main"] - g["x_nose"]) * math.tan(t))
    assert g["rotation_from_stance_deg"] >= 10.0 - 1e-6 and ck["asm:gear_rotation"]
    assert g["prop_clearance_m"] >= 7 * 0.0254 - 1e-6 and ck["asm:gear_prop_clearance"]   # both attitudes
    assert g["h_cg_static"] == pytest.approx(h * math.cos(t) + d * math.sin(t))
    assert g["x_main"] > lv["x_main"] and g["ground_z"] < lv["ground_z"]
    assert g["half_track"] == 0.48 and ck["asm:gear_overturn"]


@pytest.mark.requires_avl
def test_rotation_moment_balance_is_sadraey(c172_result):
    from acdt.domains.aircraft.flightsim import tailless_takeoff as TO
    from acdt.domains.aircraft.flightsim.aeromodel import build_flight_model
    fm = build_flight_model(c172_result)
    a, m = fm.aero, fm.mass.m
    W = m * 9.80665
    d, h, k, rho = 0.3, 0.9, 1.2, 1.225
    r = TO._rotation(fm, d, h, 0.0, k, rho, 8.0)
    Vs = math.sqrt(2 * W / (rho * a.S * a.CLmax[0]))
    q = 0.5 * rho * (k * Vs) ** 2
    de = math.radians(a.limits["elevator"]) * (-1 if a._interp("Cmde", 0.0, 0.0) < 0 else 1)
    c = a.coefficients(0.0, 0, 0, 0, 0, 0, de, 0, 0, 0.0, fm.mass.x_cg)
    N = W - q * a.S * c["CL"]                                 # Eq. 9.39 (θ_g = 0: no thrust lift)
    M = q * a.S * a.c * c["Cm"] - N * d - TO.MU_ROLL * N * h  # Eq. 9.52, horizontal forces → −μN h
    assert r["theta_dd_deg_s2"] == pytest.approx(math.degrees(M / (fm.mass.Iyy + m * (d * d + h * h))))
    if r["d_max_m"] is not None:                               # the largest d gives exactly θ̈_req
        assert TO._rotation(fm, r["d_max_m"], h, 0.0, k, rho, 8.0)["theta_dd_deg_s2"] == pytest.approx(8.0, abs=1e-6)
    # net elevon power about the main wheels per radian: c̄ C_mδe + C_Lδe (d + μh)
    assert r["elevon_net_power_per_rad"] == pytest.approx(
        a.c * a._interp("Cmde", 0.0, 0.0) + a._interp("CLde", 0.0, 0.0) * (d + TO.MU_ROLL * h))


@pytest.mark.requires_avl
def test_fly_off_and_unassessed(c172_result):
    from acdt.domains.aircraft.flightsim import tailless_takeoff as TO
    from acdt.domains.aircraft.flightsim.aeromodel import build_flight_model
    fm = build_flight_model(c172_result)
    f = TO._flyoff(fm, math.radians(8.0), 1.225, 300.0)
    W = fm.mass.m * 9.80665
    assert f["V_LOF_m_s"] == pytest.approx(math.sqrt(2 * W / (1.225 * fm.aero.S * f["CL_trim"])))
    assert f["ok"] == (f["de_within_limit"] and f["VLOF_over_VS"] >= 1.1 and f["ground_roll_m"] <= 300.3)
    assert TO.assess(None, {}, {}, {"type": "none"}, {}, {})["status"] == "unassessed"
    assert TO.row({"status": "unassessed", "issue": "x"})[1] is None


@pytest.mark.requires_avl
def test_nose_extension_in_ground_model(c172_result):
    from acdt.domains.aircraft.flightsim.aeromodel import build_flight_model
    from acdt.domains.aircraft.flightsim.sixdof import GroundModel
    fm = copy.deepcopy(build_flight_model(c172_result))
    g0 = GroundModel.from_model(fm)
    fm.mass.gear = {**fm.mass.gear, "nose_extension_m": 0.3}
    g1 = GroundModel.from_model(fm)
    n0 = [c for c in g0.contacts if c[0] == "nose"][0][1]
    n1 = [c for c in g1.contacts if c[0] == "nose"][0][1]
    m0 = [c for c in g0.contacts if c[0] == "main_L"][0][1]
    m1 = [c for c in g1.contacts if c[0] == "main_L"][0][1]
    assert n1[2] == pytest.approx(n0[2] + 0.3) and list(m1) == list(m0)


def test_shortest_wheelbase_option():
    from acdt.domains.aircraft.landing_gear import place_tricycle
    lo = place_tricycle(1.0, 1.1, 0.5, 15.0, 0.08, 0.15, -2.0)
    sh = place_tricycle(1.0, 1.1, 0.5, 15.0, 0.08, 0.15, -2.0, prefer="shortest")
    xm = lo[1]
    assert sh[1] == xm and (xm - sh[0]) == pytest.approx((xm - 1.0) / 0.15)    # front-CG nose load at the band top
    assert (xm - lo[0]) == pytest.approx((xm - 1.1) / 0.08)                     # default unchanged: longest
    asm = Assembly.from_dict(TL["assembly"])
    g = gear_layout(asm, CGF, CGA, {**TL["gear"], "ground_attitude_deg": 19.0, "wheelbase": "shortest"})
    gl = gear_layout(asm, CGF, CGA, {**TL["gear"], "ground_attitude_deg": 19.0})
    assert g["nose_strut_extension_m"] < gl["nose_strut_extension_m"]
    assert max(g["nose_fraction"]) == pytest.approx(0.15, abs=1e-6)


def test_tip_skids_energy_sizing():
    """Opt-in tip skids: Currey / Raymer / Sadraey energy E = η N δ; missing W stays unassessed."""
    from acdt.domains.aircraft.assembly.gear_devices import apply_gear_devices, size_tip_skids
    asm = Assembly.from_dict(TL["assembly"])
    opts = {**TL["gear"], "ground_attitude_deg": 19.0, "half_track": 0.48, "tip_skids": True}
    g = gear_layout(asm, CGF, CGA, opts)
    W = 150.4 * 9.80665
    sk = size_tip_skids(asm, g, W)
    assert sk["status"] == "assessed" and sk["ok"] and sk["n_skids"] == 2
    assert sk["h_tip_static_m"] > 0.0 and sk["phi_contact_about_wheel_deg"] > 5.0
    assert sk["energy_J"] == pytest.approx(sk["m_eff_kg"] * 9.80665 * sk["h_tip_static_m"])
    assert sk["P_des_N"] == pytest.approx(sk["n_ult"] * sk["energy_J"] / (sk["eta"] * sk["stroke_m"]))
    assert sk["mass_kg"] >= 2 * 0.08                         # PRESSUPOSTO installation floor (never silent zero)
    assert sk["mass_each_kg"] == pytest.approx(max(sk["mass_section_kg"], sk["mass_min_kg"]))
    # I_xx reduces m_eff below m
    Ixx = 40.0
    y = sk["tip_y_m"]
    m = W / 9.80665
    sk_i = size_tip_skids(asm, g, W, Ixx_kgm2=Ixx, mass_kg=m)
    assert sk_i["m_eff_kg"] == pytest.approx(1.0 / (1.0 / m + y * y / Ixx))
    assert sk_i["m_eff_kg"] < sk["m_eff_kg"]
    # apply_gear_devices wires the check when W is on the layout
    g["W_N"] = W
    _, rep = apply_gear_devices({"assembly": TL["assembly"], "gear": opts}, g)
    assert rep["tip_skids"]["status"] == "assessed"
    assert any(c[0] == "asm:gear_tip_skids" and c[1] for c in g["checks"])
    # missing W stays unassessed (unknown ≠ zero)
    assert size_tip_skids(asm, g, 0.0)["status"] == "unassessed"


def test_lift_dump_de_reduces_cl():
    """Lift-dump goes to the elevator stop against the sign of C_Lδe."""
    from acdt.domains.aircraft.flightsim.mission import lift_dump_de

    class _A:
        limits = {"elevator": 25.0}
        def _interp(self, key, alpha, flap):
            assert key == "CLde"
            return 0.4
    de = lift_dump_de(_A(), 0.0, 0.0)
    assert de == pytest.approx(-math.radians(25.0))

    class _B(_A):
        def _interp(self, key, alpha, flap):
            return -0.4
    assert lift_dump_de(_B()) == pytest.approx(math.radians(25.0))


def test_gear_drag_scale_side_load_and_sadraey_track():
    from acdt.domains.aircraft.assembly.gear_devices import (
        conservative_wing_EI_at_root, max_track_sadraey_9532, scale_fixed_gear_drag_area,
        size_gear_side_load_structure)
    asm = Assembly.from_dict(TL["assembly"])
    g = gear_layout(asm, CGF, CGA, {**TL["gear"], "ground_attitude_deg": 19.0, "half_track": 0.48})
    lengths = {"main_gear_length_m": 0.47, "nose_gear_length_m": 0.78}
    sc = scale_fixed_gear_drag_area(0.03, g, ref_main_m=0.35, ref_nose_m=0.30, length_opts=lengths)
    assert sc["status"] == "assessed"
    assert sc["factor"] == pytest.approx((2 * 0.47 + 0.78) / (2 * 0.35 + 0.30))
    assert sc["area_scaled_m2"] == pytest.approx(0.03 * sc["factor"])
    # missing lengths stay unassessed (unknown ≠ factor 1)
    g_bare = {k: v for k, v in g.items() if k not in ("h_cg", "main_leg_from_lowest_point_m",
                                                      "nose_strut_extension_m", "ground_z")}
    assert scale_fixed_gear_drag_area(0.03, g_bare)["status"] == "unassessed"

    W = 150.4 * 9.80665
    side = size_gear_side_load_structure(g, W, length_opts=lengths)
    assert side["status"] == "assessed" and side["ok"] is True
    assert side["F_side_N"] == pytest.approx(0.5 * W)
    assert side["RF_bending"] >= 1.0 and side["RF_buckling"] >= 1.0
    assert size_gear_side_load_structure(g, 0.0)["status"] == "unassessed"

    ei = conservative_wing_EI_at_root(asm)
    assert ei and ei["EI_Nm2"] > 0
    tr = max_track_sadraey_9532(g, W, ei["EI_Nm2"])
    assert tr["status"] == "assessed" and tr["ok"] is None   # allowable not cited → not a pass
    assert tr["delta_m"] == pytest.approx(W * tr["track_m"] ** 3 / (48.0 * ei["EI_Nm2"]))
    assert max_track_sadraey_9532(g, W, None)["status"] == "unassessed"
    # with a supplied allowable the check is boolean
    tr_ok = max_track_sadraey_9532(g, W, ei["EI_Nm2"], delta_allow_m=0.01)
    assert tr_ok["ok"] is True and tr_ok["T_max_m"] > tr["track_m"]


def test_friction_sensitivity_scales_with_mu():
    from acdt.domains.aircraft.flightsim.sixdof import friction_sensitivity
    td = {"W_N": 1500.0, "drift_m_s": 0.42, "inboard_ratio": 0.50, "outboard_ratio": 0.58}
    r = friction_sensitivity(td)
    assert r["status"] == "assessed" and len(r["cases"]) == 3
    mid = next(c for c in r["cases"] if c["mu_side"] == 0.8)
    assert mid["inboard_ratio"] == pytest.approx(0.50) and mid["side_load_ok"] is True
    hi = next(c for c in r["cases"] if c["mu_side"] == 1.0)
    assert hi["outboard_ratio"] == pytest.approx(0.58 * 1.0 / 0.8)
    assert friction_sensitivity({"W_N": 1.0})["status"] == "unassessed"

