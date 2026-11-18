# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Tailless flying wing without vertical surfaces: split ailerons (McCormick 1995 Eq. 3.45) + yaw SAS."""
from __future__ import annotations

import copy
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly import tailless as tl
from acdt.domains.aircraft.assembly.flying_wing import apply_flying_wing_options, measure_c_vt
from acdt.domains.aircraft.stability import _modes_lat, lateral_matrix

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
TL = json.loads((EX / "integration" / "flying_wing_pusher_tailless.json").read_text(encoding="utf-8"))
needs_avl = pytest.mark.requires_avl

# synthetic, physically shaped lateral derivatives of a finless swept wing [1/rad]
D = {"CYb": -0.02, "CYp": 0.01, "CYr": 0.005, "Clb": -0.12, "Clp": -0.40, "Clr": 0.15,
     "Cnb": 0.004, "Cnp": -0.02, "Cnr": -0.006, "CYda": -0.01, "Clda": -0.12, "Cnda": -0.01}


def test_split_drag_is_mccormick_eq_3_45_per_leaf():
    one = 1.7 * 0.3 ** 1.38 * 0.05 * math.sin(math.radians(40)) ** 2
    assert tl.split_drag_increment(0.3, 0.05, 40, 0) == pytest.approx(one)
    assert tl.split_drag_increment(0.3, 0.05, 40) == pytest.approx(2 * one)       # symmetric leaves
    assert tl.split_drag_increment(0.3, 0.05, 40, K_f=0.9) == pytest.approx(2 * one * 0.9 / 1.7)
    assert tl.split_drag_increment(0.3, 0.05, 0) == 0.0


def test_geometry_capacity_and_inverse():
    a = Assembly.from_dict(TL["assembly"])
    g = tl.split_geometry(a, 0.5, 0.98, 0.3)
    assert g["S_f"] == pytest.approx(0.3 * g["S_strip"])
    assert 0.5 * g["semispan"] < g["y_bar"] < 0.98 * g["semispan"]
    C1 = tl.yaw_power(g)
    assert C1 == pytest.approx(1.7 * 0.3 ** 1.38 * g["S_f"] / g["S"] * g["y_bar"] / g["b"])
    cap = tl.capacity(C1, 60)
    assert cap == pytest.approx(2 * C1 * 0.75)
    assert tl.deflection_for(cap, C1) == pytest.approx(60.0)
    assert tl.deflection_for(3 * C1, C1) is None                        # beyond 90°
    se = tl.side_effects(g, C1, 60, z_cg=g["z_f"] - 0.1)
    assert se["dCn"] == pytest.approx(cap) and se["dCl"] == 0.0
    assert se["dCm"] < 0                                                  # drag above the CG → nose down
    with pytest.raises(ValueError):
        tl.split_geometry(a, 0.9, 0.5, 0.3)


def test_span_required_monotone():
    a = Assembly.from_dict(TL["assembly"])
    g = tl.split_geometry(a, 0.6, 0.98, 0.3)
    cap = tl.capacity(tl.yaw_power(g), 60)
    f = tl.span_required(a, cap, 0.98, 0.3, 60)
    assert f == pytest.approx(0.38, abs=0.01)
    assert tl.span_required(a, 10.0, 0.98, 0.3, 60) is None
    assert tl.span_required(a, 0.0, 0.98, 0.3, 60) == 0.0


def test_crosswind_balance_and_unassessed():
    r = tl.crosswind_case(D, 1.0, 30.0, 6.0, None, None, 25.0)
    assert r["status"] == "unassessed" and r["ok"] is None
    beta, da = math.radians(r["beta_deg"]), math.radians(r["delta_a_deg"])
    assert D["Clb"] * beta + D["Clda"] * da == pytest.approx(0.0, abs=1e-12)
    assert D["Cnb"] * beta + D["Cnda"] * da + r["dCn_required"] == pytest.approx(0.0, abs=1e-12)
    r2 = tl.crosswind_case(D, 1.0, 30.0, 6.0, 0.01, 60.0, 25.0)
    assert r2["status"] == "assessed"
    assert tl.capacity(0.01, r2["delta_split_deg"]) == pytest.approx(abs(r2["dCn_required"]))


def test_coordination_case():
    r = tl.coordination_case(D, 40.0, 1.0, 2.0, 4.0, 10.0, "B", 1, 25.0, None, None)
    assert r["status"] == "unassessed" and r["ok"] is None
    assert r["roll_ok"] and abs(r["delta_a_deg"]) <= 25
    r2 = tl.coordination_case(D, 40.0, 1.0, 2.0, 4.0, 10.0, "B", 1, 25.0, 0.01, 60.0)
    assert r2["dCn_required"] == pytest.approx(max(abs(r2["dCn_entry"]), abs(r2["dCn_steady_roll"]),
                                                   abs(r2["dCn_turn"])))


def _A(d=D, V=40.0):
    return lateral_matrix(d, 0.5 * 1.0 * V**2 * 2.0, 4.0, 140.0, 10.0, 40.0, V)


def test_close_loop_equals_augmented_derivatives():
    V, qS, b, Izz = 40.0, 0.5 * 1.0 * 40.0**2 * 2.0, 4.0, 40.0
    Acl = tl.close_loop(_A(), 0.05, 0.2, qS * b / Izz, b, V)
    aug = {**D, "Cnb": D["Cnb"] + 0.05, "Cnr": D["Cnr"] - 0.2}
    assert np.allclose(Acl, _A(aug))


def test_design_sas_fixes_an_unstable_dutch_roll():
    bare = _modes_lat(_A())
    cr = {"qSb_Izz": 0.5 * 40.0**2 * 2.0 * 4.0 / 40.0, "b": 4.0, "u0": 40.0}
    A_ap = _A(V=25.0)
    ap = {"qSb_Izz": 0.5 * 25.0**2 * 2.0 * 4.0 / 40.0, "b": 4.0, "u0": 25.0}
    turb = tl.dryden_lateral(15.24, 30.0)
    s = tl.design_sas(_A(), cr, A_ap, ap, turb)
    assert s["status"] == "ok" and s["sigma_u"] > 0
    dr = s["lat_cruise"]["dutch_roll"]
    assert dr["zeta"] >= 0.08 and dr["zeta"] * dr["wn"] >= 0.15
    if bare.get("dutch_roll"):
        assert dr["zeta"] > bare["dutch_roll"]["zeta"]
    none = tl.design_sas(_A(), cr, None, None, None, kb_max=0.0, kr_max=0.0, n=2)
    assert none["status"] in ("ok", "infeasible")


def test_dryden_low_altitude_mil_f_8785c():
    t = tl.dryden_lateral(50 * 0.3048, 30.0)
    den = 0.177 + 0.000823 * 50
    assert t["sigma_w"] == pytest.approx(0.1 * 30 * 0.514444)
    assert t["sigma_v"] == pytest.approx(t["sigma_w"] / den ** 0.4)
    assert t["L_v_m"] == pytest.approx(50 / den ** 1.2 * 0.3048)


def test_turbulence_sigma_linear_and_zero_without_feedback():
    A, V = _A(V=25.0), 25.0
    q = 0.5 * 25.0**2 * 2.0 * 4.0 / 40.0
    aug = tl.close_loop(A, 0.05, 0.3, q, 4.0, V)
    assert np.max(np.linalg.eigvals(aug[:3, :3]).real) < 0
    s1 = tl.turbulence_sigma_u(A, 0.05, 0.3, q, 4.0, V, 1.0, 90.0)
    s2 = tl.turbulence_sigma_u(A, 0.05, 0.3, q, 4.0, V, 2.0, 90.0)
    assert s1 > 0 and s2 == pytest.approx(2 * s1)
    assert tl.turbulence_sigma_u(A, 0.0, 0.3, q, 4.0, V, 1.0, 90.0) >= 0.0


def test_sas_authority_unknown_is_not_pass():
    sas = {"status": "ok", "sigma_u": 0.002, "lat_approach": {"dutch_roll": {"wn": 3.0}}}
    cw = {"dCn_required": 0.004}
    a = tl.sas_authority(sas, cw, 0.01, 60.0, None)
    assert a["ok"] is None and a["authority_ok"] is True
    a = tl.sas_authority(sas, cw, None, None, 200)
    assert a["ok"] is None and a["status"] == "unassessed"
    a = tl.sas_authority(sas, cw, 0.001, 30.0, 200)
    assert a["ok"] is False
    a = tl.sas_authority(sas, cw, 0.01, 60.0, 200)
    assert a["ok"] is True and a["rate_required_deg_s"] > 0
    assert a["combined_with_crosswind_ok"] is True


def test_hq_row_logic():
    r = {"key": "dutch_roll", "nível": 4}
    hq_sas = {"dutch_roll": {"key": "dutch_roll", "nível": 1, "valor": "0.2 / 0.5 / 2", "modo": "DR",
                             "ref": "MIL-F-8785C Table VI"}}
    base = {"sas_enabled": True, "sas": {"status": "ok", "k_beta": 0.01, "k_r": 0.3}, "authority": {"issues": []}}
    assert tl.hq_row(r, False, "m", hq_sas, True, 1, base)[0] is True
    assert tl.hq_row(r, False, "m", hq_sas, False, 1, base)[0] is False
    assert tl.hq_row(r, False, "m", hq_sas, None, 1, base)[0] is None
    ok, msg = tl.hq_row(r, False, "m", None, None, 1, {"sas_enabled": False})
    assert ok is False and "SAS desligado" in msg and "célula nua" in msg


def test_flying_wing_option_yaw_control_step():
    s = copy.deepcopy(TL)
    s.setdefault("options", {})["flying_wing"] = {"yaw_control": "split_aileron", "size_winglets": True, "c_vt": 0.2}
    out, rep = apply_flying_wing_options(s)
    steps = {x["step"]: x for x in rep["steps"]}
    assert steps["yaw_control"]["status"] == "requested" and steps["yaw_control"]["c_vt_drawn"] == 0.0
    assert steps["size_winglets"]["status"] == "unassessed"
    assert measure_c_vt(Assembly.from_dict(out["assembly"])) == 0.0
    s2 = copy.deepcopy(TL)
    s2.setdefault("options", {})["flying_wing"] = {"yaw_control": "thrust_vectoring"}
    _, rep2 = apply_flying_wing_options(s2)
    assert rep2["steps"][0]["status"] == "unassessed"
    assert tl.options(TL) is None and tl.options(s) is not None


def test_morph_tailless_yaw_rules():
    from acdt.domains.aircraft.morphology.evaluate import apply_choice_patches
    from acdt.domains.aircraft.morphology.generate import cut_incompatible
    arches = [{"id": "a", "choices": {"tail": "tailless", "yaw_control": "rudder"}},
              {"id": "b", "choices": {"tail": "tailless", "yaw_control": "split_aileron"}}]
    r = cut_incompatible(arches)
    assert [k["id"] for k in r["kept"]] == ["b"] and r["cut"][0]["id"] == "a"
    from acdt.domains.aircraft.mission import MissionSpec
    spec = MissionSpec.from_yaml(EX / "heavy" / "uav150_flying_wing_closed.yaml")
    notes = apply_choice_patches(spec, {"yaw_control": "split_aileron"})
    fwb = spec.assumptions["assembly"]["options"]["flying_wing"]
    assert fwb["yaw_control"] == "split_aileron" and "size_winglets" not in fwb
    assert any("split_aileron" in n for n in notes)


@pytest.mark.slow
@needs_avl
def test_tailless_example_closes_bare_fails_sas_passes():
    """Example: W0 loop closes; bare Dutch roll fails (information), SAS within split-aileron capability passes.
    Since the pitch-trim fix (10 nov 2026: useful load at the empty CG, SM target 0.05 inside NACA TR-796's
    0.02–0.08, washout −10°, no flap, sizing CLmax = trimmed CLmax) every loading case trims and the crosswind passes."""
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.phase2 import stability_stage
    from acdt.domains.aircraft.sizing import run as size_run
    res = size_run(MissionSpec.from_yaml(EX / "heavy" / "uav150_flying_wing_tailless.yaml"))
    assert res.sizing.converged
    stability_stage(res)
    t = res.dynamics["tailless"]
    assert t["c_vt_measured"] == 0.0 and t["sas_enabled"] is True
    assert t["bare"]["cruise"]["dutch_roll"]["zeta"] < 0.08            # bare airframe fails — reported
    assert t["sas"]["status"] == "ok"
    ck = {c.key: c for c in res.checks}
    assert ck["hq:dutch_roll"].ok is True and "célula nua" in ck["hq:dutch_roll"].message
    assert ck["hq:sas_authority"].ok is True
    assert ck["hq:yaw_coordination"].ok is True
    assert ck["hq:yaw_crosswind"].ok is True and "crosswind_options" not in t
    assert t["crosswind"]["crosswind_max_kt"] >= t["crosswind"]["crosswind_kt"]
    assert t["authority"]["rate_required_deg_s"] <= t["actuators"]["rate_max_effective_deg_s"]
    assert res.feasible
    # trimmed-CLmax closure (no flap): converged, CLmax used == trimmed CLmax of the drawing
    tt = res.tailless_trim
    assert tt["converged"] and 1.0 < tt["CLmax_trimmed"] < 1.3
    assert res.highlift.CLmax_landing == pytest.approx(tt["CLmax_trimmed"], abs=1e-9)
    assert res.sizing.W0 == pytest.approx(150.4, abs=5.0)   # 12 nov 2026: 19° stance legs (Raymer 15.50/15.51)
    ap = t["approach_consistency"]
    assert ap["ok"] is True and ck["hq:pitch_trim_tailless"].ok is True
    assert set(ap["cases"]) == {"vazio", "carga", "combustível", "cheio"}
    assert all(c["cruise"]["ok"] and c["approach"]["ok"] for c in ap["cases"].values())
    assert not ap["static_margin_band"]["outside"]
    assert all(0.02 <= v <= 0.08 for v in ap["static_margin_band"]["cases"].values())
    assert ap["washout_check"]["panknin"]["status"] == "assessed"
    # useful_load_at: empty_cg — the unpositioned fuel sits on the fixed-mass CG, so fuel alone does not move it
    lc = res.assembly["result"].loading["cases"]
    assert lc["combustível"]["cg"][0] == pytest.approx(lc["vazio"]["cg"][0], abs=1e-9)
    # follow-up: actuator dynamics, hinge moments/servos, lateral gust
    assert ck["hq:sas_time_delay"].ok is True and t["actuator_dynamics"]["delay_s"] == 0.10
    assert t["actuator_dynamics"]["delay_margin_level1_s"] >= 0.10
    sp = t["actuators"]["split_aileron"]["servo"]["servo"]
    assert sp["name"] == "Volz DA 30" and sp["n_per_surface"] == 2
    ev = t["actuators"]["elevon"]["servo"]["servo"]
    # elevon rate required = bank-hold peak in the SAS gust (≈97 °/s); since the 19° stance trims δe ≈ −18° on the
    # ground roll the DA 26 no longer fits → 1× Volz DA 30 (117 °/s at the surface); its travel is not in the
    # datasheet → unassessed (None), not a pass
    es = t["actuators"]["elevon"]["servo"]
    assert ev["name"] == "Volz DA 30" and ev["travel_ok"] is None and es["ok"] is True and es["rate_ok"] is True and 90 < es["rate_required_deg_s"] < 110
    assert ck["hq:actuators"].ok is True
    assert ck["asm:actuator_mass"].ok is True
    # gear with the nose-up stance (opt-in gear.ground_attitude_deg): Raymer band 8–15 % met, take-off closes by
    # fly-off at the stance (still air, point mass ≤ 300 m); elevon alone could not lift the nose wheel at θ_g = 0
    g_ = res.assembly["result"].gear
    assert g_["ground_attitude_deg"] == 19.0 and g_["nose_strut_extension_m"] > 0.2
    assert all(ck[k].ok is True for k in ("asm:gear_tipback", "asm:gear_rotation", "asm:gear_prop_clearance",
                                          "asm:gear_position", "asm:gear_overturn", "gear:nose_load"))
    to_ = t["takeoff_rotation"]
    assert ck["gear:takeoff_rotation"].ok is True and to_["mode"] == "fly_off" and to_["ground_roll_worst_m"] <= 300.0
    assert all(c["fly_off"]["VLOF_over_VS"] >= 1.1 for c in to_["cases"].values())
    # 11 nov 2026: split pre-deflection δ0 = 2° chosen as design (linear ΔC_n near zero) — strict criterion passes,
    # its cruise drag is in the sizing polar (McCormick Eq. 3.45, both sides)
    gl = t["lateral_gust"]
    assert ck["hq:lateral_gust"].ok is True and gl["bias_deg"] == 2.0 and "options" not in gl
    assert gl["sas"]["actuator"]["rate_limited"] is False
    assert gl["bias_drag"]["dCD0"] == pytest.approx(0.000202, rel=0.02)
    assert res.assembly_loop["drag"]["split_bias"]["dCD0"] == pytest.approx(gl["bias_drag"]["dCD0"], rel=1e-6)
    # phugoid: bare at/near the Level 1 boundary (ζ 0.04, MIL-F-8785C; 0.041 since the 12 nov gear, W0 150 kg),
    # pitch-attitude hold (UAV autopilot hypothesis) → Level 1
    assert ck["hq:phugoid_autopilot"].ok is True and t["pitch_hold"]["bare_phugoid_zeta"] < 0.05
    # useful load lumped at the empty CG: fuel volume fits (gross) near it; fine packaging unassessed → None
    pk = t["cg_packaging"]
    assert pk["fuel_fits"] is True and ck["asm:useful_load_packaging"].ok is None
    # bodies' Cm (Torenbeek) is in the main trim; AVL-wing-only remains as a sensitivity
    assert ap.get("bodies_in_main_trim") is True
    assert all("with_bodies" in c and "avl_wing" in c for c in ap["cases"].values())
    # 18 nov 2026: body C_m0 by Multhopp (Nelson 1998 Sec. 2.3; Tulapurkara Eq. 2.56) always reported; the main
    # trim keeps C_m0 = 0 (PRESSUPOSTO) unless flying_wing.body_cm0: multhopp. Linux: +0,0101 (α0L,f +3,9°).
    bc = ap["bodies_cm0"]
    assert bc["status"] == "assessed" and bc["in_main_trim"] is False and 0.0 < bc["Cm0"] < 0.03
    assert all(c["body_cm0_alternative"]["cruise_ok"] and c["body_cm0_alternative"]["approach_ok"]
               for c in ap["cases"].values())
    fp = t["fine_packaging"]
    assert fp["status"] == "assessed" and fp.get("fuel", {}).get("fits") is True
    assert "cheio" in (fp.get("cases") or {})
    assert fp.get("sm_in_band") is True and fp.get("ok") is None  # payload volume still unassessed
    # 6-DOF: flight model from the assembly, lateral gust bare vs SAS in every loading case, and the mission with the
    # yaw channel through the split aileron (crosswind circuit, decrab, touchdown side loads)
    import tempfile
    from acdt.domains.aircraft.flightsim.study import simulation_study
    with tempfile.TemporaryDirectory() as td:
        r = simulation_study(res, EX / "simulation" / "uav150_tailless_crosswind.yaml", td, log=lambda m: None)
    ms = r["mission"]
    assert ms["status"] == "assessed" and not ms["aborted"] and ms["case"] == "cheio"
    seg = {s_["type"]: s_ for s_ in ms["segments"]}
    assert set(seg) == {"takeoff", "climb", "waypoints", "descent", "landing"}
    assert seg["waypoints"]["beta_max_deg"] < 10.0                   # turns with the split yaw damper + washout
    td_ = seg["landing"]["touchdown"]
    assert td_["decrab"] is True and abs(td_["crab_at_decrab_deg"]) > 8.0 and abs(td_["residual_crab_deg"]) < 1.0
    assert td_["limit_23_485"]["inboard_N"] == pytest.approx(0.5 * td_["W_N"])
    assert ms["yaw_split"]["actuator_saturated"] is False
    assert "rate_limited_fraction" in ms["yaw_split"] and "rate_max_deg_s" in ms["yaw_split"]
    assert ms.get("friction_sensitivity", {}).get("status") == "assessed"
    # 12 nov 2026: nose-up stance 19° = lift-off attitude (fly-off, Sadraey 2012 Sec. 9.6.2). Track stays
    # 0.48 m (wider track removed the tip contact but ~1.5× 23.485 outboard). 14 CFR 23.233(a) 0.2 V_S0
    # is not relaxed. Tip skids (Raymer Ch. 11 / Currey energy): designed contact does not fail side_load_ok.
    to = seg["takeoff"]
    assert to["mode"] == "fly_off" and to["theta_LOF_deg"] == pytest.approx(19.0) and to["V_liftoff_m_s"] > 28.0
    assert ms["gear"]["ground_attitude_deg"] == 19.0 and ms["gear"]["tip_clearance_angle_about_wheel_static_deg"] > 5.0
    assert "tip_skids" in ms["gear"] and ms["gear"]["tip_skids"]["status"] == "assessed"
    assert td_["tip_skid_ok"] is True
    # 23.485 only; designed tip-skid contact no longer flips this flag. Banded verdict with the declared 6-DOF
    # sampling tolerance (SIDE_LOAD_RATIO_TOL): Linux spread 0.59–0.63 inboard over 15 perturbed runs. The
    # message dumps the numbers so a platform-dependent trajectory (Windows) can be diagnosed from the log.
    diag = {k: td_.get(k) for k in ("inboard_ratio", "outboard_ratio", "side_load_status", "side_load_margin",
                                    "main_side_N", "main_vertical_peak_N", "phi_td_deg", "drift_m_s",
                                    "residual_crab_deg", "bumper_contacts_N", "issue")}
    diag["sink_at_touchdown_m_s"] = seg["landing"].get("sink_at_touchdown_m_s")
    assert td_["side_load_status"] == "passa" and td_["side_load_ok"] is True, diag
    assert td_["inboard_ratio"] < 1.0 and td_["outboard_ratio"] < 1.0, diag   # 14 CFR 23.485 within limits
    assert seg["landing"].get("lift_dump") is True
    if to.get("strikes_N"):
        assert all(not k.startswith("tip_") for k in to["strikes_N"])
    # aft_strike (prop/TE on the centreline, ~0.18 m static clearance in the 19° stance) may still
    # register in the same 6-DOF run; it is reported, not treated as a pass, and is not a tip-skid event.
    # 14 nov 2026 (gear-aft-strike): dynamic aft clearance through take-off and flare (Sadraey 2012 Sec. 9.5.1.3)
    # with options (attitude limit, strut extension, tail bumper by energy). Linux: min ≈ 0.06 m in the take-off
    # (θ 22.6°, mains compressed ~0.09 m) — a small margin, so only the structure of the verdict is asserted.
    ac = ms["aft_clearance"]
    assert ac["status"] == "assessed" and set(ac["phases"]) == {"takeoff", "landing"}
    assert ac["critical_point"] == "aft_strike" and 40.0 < ac["alpha_C_deg"] < 50.0
    assert ac["alpha_C_compressed_deg"] < ac["alpha_C_deg"] and ac["ok"] is not None
    assert {"attitude_limit", "strut_extension", "tail_bumper"} <= set(ac["options"])
    assert ac["min_clearance_m"] < 0.25   # 0.18 m static in the 19° stance; compression only lowers it
    # 16 nov 2026 (l1-trem-ventocruzado): crosswind take-off roll above the 300 m requirement → options table
    # (flightsim/takeoff_options.py); verdicts are platform-dependent near 300 m, so only the structure is asserted
    if to["ground_roll_m"] > 300.0:
        too = ms["takeoff_options"]
        assert too["status"] == "assessed" and too["requirement_m"] == 300.0
        assert too["ground_roll_6dof_still_air_m"] < too["ground_roll_6dof_m"]          # crosswind costs roll
        O = too["options"]
        assert set(O) == {"a_vento_de_frente", "b_tracao", "c_carga_alar", "d_massa", "e_atitude", "f_catapulta",
                          "g_vento_cruzado_menor"}
        assert O["g_vento_cruzado_menor"]["closes"] is False and O["f_catapulta"]["closes"] is None
        assert O["b_tracao"]["thrust_factor_required"] > 1.0 and "check_6dof" in O["b_tracao"]
        assert "sweep" in O["e_atitude"]
    # 18 nov 2026: strict 6-DOF gust verdict per case (same criterion as hq:lateral_gust). Linux: 'cheio' touches
    # the split rate limit (0,5 % of the time) → False, ~100 °/s required vs 84 °/s; only the structure is asserted
    g6 = r["lateral_gust_6dof"]
    assert set(g6["cases"]) == set(r["lateral_tests"]) and g6["ok"] is not None
    for v in g6["cases"].values():
        assert v["status"] == "assessed" and v["ok"] is not None
        if v["rate_limited"]:
            assert v["ok"] is False and v["rate_required_deg_s"] >= v["rate_available_deg_s"] * 0.999
    assert r["name"] == "tailless_lateral_test" and r["case"] == "cheio"
    assert set(r["lateral_tests"]) == {"vazio", "carga", "combustível", "cheio"}
    for lt in r["lateral_tests"].values():
        assert lt["status"] == "assessed" and lt["trim"]["ok"] and lt["elevator_within_limit"]
        assert lt["sas"]["final_beta_amp_deg"] < lt["bare"]["final_beta_amp_deg"]
    assert r["lateral_test"] is r["lateral_tests"]["cheio"]


def test_side_load_band_declared_tolerance():
    """Banded 23.485 verdict: pass only below 1 − tol, fail above 1 + tol, None (no limite) in between."""
    from acdt.domains.aircraft.flightsim.mission import SIDE_LOAD_RATIO_TOL, side_load_band
    tol = SIDE_LOAD_RATIO_TOL
    assert tol == pytest.approx(0.05)
    b = side_load_band(0.63, 0.57)
    assert b["side_load_ok"] is True and b["side_load_status"] == "passa" and b["side_load_margin"] == pytest.approx(0.37)
    for r in (1.0 - tol + 1e-9, 0.99, 1.0, 1.0 + tol):
        b = side_load_band(0.2, r)
        assert b["side_load_ok"] is None and b["side_load_status"] == "no_limite", r
    b = side_load_band(1.0 + tol + 1e-9, 0.1)
    assert b["side_load_ok"] is False and b["side_load_status"] == "excede"
    assert side_load_band(float("nan"), 0.1)["side_load_ok"] is None
