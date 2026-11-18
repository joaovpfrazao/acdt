"""Phase 2: low-fidelity aero (AVL/XFOIL), V-n & wing box, stability, segment mission performance.

Hand checks reference the cited clauses/equations; tests needing the AVL/XFOIL binaries are skipped
when they are absent (the pipeline then falls back to NeuralFoil / Schrenk and says so)."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from acdt import G0
from acdt.core.pipeline import run_pipeline
from acdt.domains.aircraft.aero.airfoil import xfoil_available, xfoil_polar
from acdt.domains.aircraft.aero.avl import avl_available, run_avl_case
from acdt.domains.aircraft.performance import (PerfModel, climb_rate, flight_envelope, landing_distance,
                                               takeoff_distance_integrated)
from acdt.domains.aircraft.stability import neutral_point
from acdt.domains.aircraft.structures import (MATERIALS, box_beam_sizing, regulation_min_n, shear_moment_diagram,
                                              span_load, spanwise_lift_schrenk, v_n_diagram)

EX = Path(__file__).parents[1] / "examples"
needs_avl = pytest.mark.requires_avl
needs_xfoil = pytest.mark.requires_xfoil


@pytest.fixture(scope="module")
def c172(tmp_path_factory):
    st = run_pipeline("aircraft", EX / "cessna172_check.yaml", output=tmp_path_factory.mktemp("c172"))
    return st["result"], Path(st["report_path"])


@pytest.fixture(scope="module")
def uav(tmp_path_factory):
    st = run_pipeline("aircraft", EX / "uav_endurance_payload.yaml", output=tmp_path_factory.mktemp("uav"))
    return st["result"], Path(st["report_path"])


# ------------------------------------------------------------------ tool wrappers
@needs_xfoil
def test_xfoil_naca2412_polar():
    p = xfoil_polar("naca2412", 3e6)
    cl0 = float(np.interp(0.0, p.alpha, p.cl))
    assert 0.20 < cl0 < 0.30                      # Abbott & von Doenhoff App. IV: cl(0) ≈ 0.25
    assert 1.5 < p.clmax < 1.9 and 14 < p.alpha_clmax < 20
    assert 0.004 < float(np.min(p.cd)) < 0.009
    assert "XFOIL" in p.source


@pytest.mark.slow
@needs_avl
def test_avl_wrapper_lift_slope_and_efficiency(c172):
    res, _ = c172
    a = run_avl_case(res.config, alpha_deg=4.0)
    AR = res.config.wing.AR
    cla_helmbold = 2 * math.pi * AR / (2 + math.sqrt(4 + AR**2))  # Helmbold/DATCOM, M = 0, straight wing
    assert a.derivatives["CLa"] == pytest.approx(cla_helmbold * 1.1, rel=0.15)  # + tail lift
    assert 0.9 < a.e <= 1.02
    assert a.Cmalpha < 0                           # stable
    ys = [s["y"] for s in a.strips]
    assert len(a.strips) > 10 and min(ys) < 0 < max(ys)


# ------------------------------------------------------------------ V-n (CS-23 / STANAG 4671)
def test_manoeuvre_load_factors_clauses():
    assert regulation_min_n(1157, "normal", "cs_23") == pytest.approx(3.8)       # 2.1+24000/(2551+10000)=4.01→3.8
    assert regulation_min_n(5000, "normal", "cs_23") == pytest.approx(2.1 + 24000 / (5000 / 0.45359237 + 10000))
    assert regulation_min_n(1000, "utility", "cs_23") == 4.4
    assert regulation_min_n(1000, "aerobatic", "cs_23") == 6.0
    assert regulation_min_n(25, "normal", "stanag_4671") == pytest.approx(3.8)   # USAR.337(a)
    assert regulation_min_n(20000, "normal", "stanag_4671") == pytest.approx(2.1 + 10900 / 24536)


def test_vn_c172_like():
    # C172S: 1157 kg, 16.2 m², CLmax 1.6 clean, CLα 4.6, MAC 1.49 m, cruise 122 kt TAS @ 8000 ft
    vn = v_n_diagram(1157, 16.2, 1.6, 4.6, 1.49, 56.0)
    ws_psf = 1157 * G0 / 16.2 / 47.880259
    assert vn.n_pos == pytest.approx(3.8) and vn.n_neg == pytest.approx(-1.52)
    assert vn.VC == pytest.approx(33 * math.sqrt(ws_psf) * 0.514444, rel=1e-6)    # 23.335(a)(1)
    assert vn.VD == pytest.approx(1.4 * vn.VC, rel=1e-6)                          # 23.335(b)(1)
    assert vn.VA == pytest.approx(min(vn.VS1 * math.sqrt(3.8), vn.VC))            # 23.335(c)
    mu = 2 * vn.W_S / (1.225 * 1.49 * 4.6 * G0)
    Kg = 0.88 * mu / (5.3 + mu)
    assert vn.Kg == pytest.approx(Kg)
    ng = 1 + Kg * 1.225 * 15.24 * vn.VC * 4.6 / (2 * vn.W_S)                     # 23.341 Pratt formula
    assert vn.n_gust(vn.VC) == pytest.approx(ng, rel=1e-6)
    assert 3.4 < ng < 4.1


# ------------------------------------------------------------------ loads & wing box
class _W:
    span, S, c_root, c_tip, mac, tc_root, tc_tip = 10.0, 15.0, 1.5, 1.5, 1.5, 0.12, 0.12

    class box:
        front_spar_xc, rear_spar_xc, rib_pitch = 0.15, 0.60, None


def test_schrenk_integrates_to_lift_and_root_moment():
    y, c, l = spanwise_lift_schrenk(_W, 1000.0)
    assert 2 * np.trapezoid(l, y) == pytest.approx(1000.0, rel=2e-3)
    load = span_load(_W, 1000.0, 1.0, 0.0)
    b = shear_moment_diagram(load)
    assert b.shear[0] == pytest.approx(500.0, rel=2e-3) and b.shear[-1] == 0.0
    # rectangular+elliptic average: semispan centroid = ½(b/4 + 4/(3π)·b/2)
    yc = 0.5 * (_W.span / 4 + 4 / (3 * math.pi) * _W.span / 2)
    assert b.moment[0] == pytest.approx(500.0 * yc, rel=0.01)


def test_box_caps_from_bending():
    load = span_load(_W, 10000.0, 3.8, 0.0)
    b = shear_moment_diagram(load)
    m = MATERIALS["al2024_t3"]
    box = box_beam_sizing(_W, b, "al2024_t3", 1.5)
    assert box.cap_area[0] == pytest.approx(1.5 * b.moment[0] / (box.h_box[0] * m["sigma_cap"]), rel=1e-9)
    assert box.masses["total"] == pytest.approx(1.25 * box.masses["ideal"])
    assert box.cap_area[-1] <= box.cap_area[0]


# ------------------------------------------------------------------ stability
def test_neutral_point_handbook_vs_avl(c172):
    res, _ = c172
    st = res.stability
    assert st is not None
    assert st.SM_aft == pytest.approx(res.spec.assumptions["stability"]["target_static_margin"], abs=2e-3)
    assert st.SM_fwd >= st.SM_aft > 0
    np_no_fus = neutral_point(res.config, x_mac_le=st.x_mac_le, x_wing_apex=st.x_wing_apex,
                              include_fuselage=False)["xbar_np"]
    assert np_no_fus > st.xbar_np                   # fuselage is destabilising (Raymer Eq. 16.25)
    if st.xbar_np_avl is not None:                 # AVL (no fuselage) vs handbook (no fuselage) within 6 % MAC
        assert abs(st.xbar_np_avl - np_no_fus) < 0.06
    assert st.Vh == pytest.approx(0.70, abs=0.01)


# ------------------------------------------------------------------ performance
@pytest.mark.requires_avl
def test_performance_c172(c172):
    res, _ = c172
    pf = res.performance
    assert pf is not None
    m = PerfModel.from_result(res)
    W = res.sizing.W0 * G0
    roc, vy = climb_rate(m, W, 0.0)
    assert roc == pytest.approx(pf.envelope["roc_sl"]) and 3.0 < roc < 7.0   # C172S POH: 3.7 m/s
    env = flight_envelope(m, W)
    assert 3500 < env["service_ceiling"] < 6000 < env["absolute_ceiling"] + 1000
    to = takeoff_distance_integrated(m, W)
    assert 120 < to["ground_roll"] < 350 and to["total_50ft"] > to["ground_roll"]
    ld = landing_distance(m, W)
    assert ld["total_50ft"] > ld["ground_roll"] > 0
    keys = {c["requisito"]: c for c in pf.requirement_compare}
    assert keys["range"]["ok"] and keys["service_ceiling"]["ok"]
    # fixed-pitch BEMT propeller (Phase 9): 715 ft/min vs POH 730 (climb is not an active constraint)
    assert keys["climb_rate"]["obtido"] == pytest.approx(keys["climb_rate"]["requerido"], rel=0.05)
    assert 1000 < pf.mission.range_m / 1e3 < 1600   # POH: 1185 km at 75 % power with 45 min reserve
    assert res.feasible                              # perf:* checks do not affect sizing feasibility
    assert res.verified in (True, False)


def test_vn_feeds_weights_and_box_cross_check(c172):
    res, _ = c172
    sr = res.structures
    assert res.weights.Nz == pytest.approx(1.5 * sr.vn.n_limit_pos, rel=0.01)
    assert 0.4 < sr.box.mass / sr.wing_mass_raymer < 1.0  # strength-sized box is a lower bound
    assert res.structures_avl is None or res.structures_avl.load.source.startswith("AVL")


def test_c172_passes_poh_envelope_gear_and_scissor(c172):
    """The real 172S has to clear the conceptual CG, gear and scissor checks.

    POH 172S Sec. 6 normal-category limit polygon, not the loading cloud: 35.0 in at or
    below 1950 lb, then 41.0 in at 2550 lb, aft 47.3 in. On the weighing form,
    % MAC = (arm − 25.90) / 58.80, so that polygon is 15.5–36.4 %. The model empty
    arm stays near 39 in, so the cloud does not start at 15.5 %. Tolerance on the
    reported cloud: 1 percentage point outside that polygon (0.1 in on the form is
    0.17 point; 1 point covers the empty aeroplane not sitting on the 35.0 in corner).

    Nose fraction from the equipment list: nose wheel −6.8 in, main wheel 58.2 in,
    wheelbase 65 in (Sec. 1). f = (58.2 − X) / 65 is 16.8 % at 47.3 in and 35.7 % at
    35.0 in, outside Raymer's 8–15 %. The mission uses that band. Calling
    ``place_tricycle`` with 8–15 % still returns None. The scissor's own tolerance is
    0.5 % of S_h/S (``tail_sizing_scissor``).

    Rear-seat mass is capped so full baggage and full fuel stay inside the conceptual
    aft limit (neutral point minus 10 % of the sized MAC), which is ahead of 47.3 in.
    Station arms are the POH inches, in order.
    """
    res, _ = c172
    wb = res.weight_balance
    checks = {c.key: c for c in res.checks}
    assert checks["wb:envelope"].ok is True, checks["wb:envelope"].message
    assert checks["gear:position"].ok is True, checks["gear:position"].message
    assert checks["hq:scissor"].ok is True, checks["hq:scissor"].message
    # documented: current tail within the scissor's own 0.5 % of the required ratio
    sc = res.dynamics["scissor"]
    assert sc["Sh_S_current"] + 1e-9 >= sc["Sh_S_required"] * (1 - 5e-3)

    xs = {i["name"]: i["x_m"] for i in wb.items}
    assert xs["bancos dianteiros"] < xs["combustível"] < xs["bancos traseiros"] < xs["bagagem 1"] < xs["bagagem 2"]
    fw = xs["bancos dianteiros"] - 37.0 * 0.0254
    assert fw == pytest.approx(xs["combustível"] - 48.0 * 0.0254)
    fwd_in = (wb.x_min_m - fw) / 0.0254
    aft_in = (wb.x_max_m - fw) / 0.0254
    assert 34 < fwd_in < 46
    assert fwd_in + 4 < aft_in <= 47.3 + 0.3
    fwd_pct = (fwd_in - 25.90) / 58.80 * 100
    aft_pct = (aft_in - 25.90) / 58.80 * 100
    assert wb.mac_percent(wb.x_min_m) == pytest.approx(fwd_pct, abs=0.05)
    assert wb.mac_percent(wb.x_max_m) == pytest.approx(aft_pct, abs=0.05)
    # 15.48 % at 35.0 in and 36.39 % at 47.3 in, plus the 1-point tolerance
    assert fwd_pct >= (35.0 - 25.90) / 58.80 * 100 - 1.0
    assert aft_pct <= (47.3 - 25.90) / 58.80 * 100 + 1.0

    gear = res.landing_gear
    assert gear.x_nose_m is not None and gear.x_main_m is not None
    # The constant-diameter belly still clears less than 10°. That check is not one of
    # wb:envelope, gear:position or hq:scissor. A rising tail cone is not invented here.
    gchecks = {k: (ok, msg) for k, ok, msg in gear.checks}
    assert gchecks["gear:rotation"][0] is False
    h = 0.65 + 0.5 * res.config.fuselage.max_diameter
    from acdt.domains.aircraft.landing_gear import angle_from_vertical_deg, place_tricycle
    assert place_tricycle(wb.x_min_m, wb.x_max_m, h, 15.0, 0.08, 0.15, 0.0,
                          res.config.fuselage.length) is None
    assert angle_from_vertical_deg(0.65, res.config.fuselage.length - gear.x_main_m) < 10.0
    f_min = (58.2 - 47.3) / 65.0
    f_max = (58.2 - 35.0) / 65.0
    assert gear.nose_fraction_aft >= f_min - 1e-3
    assert gear.nose_fraction_fwd <= f_max + 1e-3


@pytest.mark.requires_avl
def test_c172_rotation_climb_and_landing_stay_short_of_the_poh(c172):
    """POH 172S misses that stay misses until a cited method changes the model.

    Climb is Anderson Ch. 5 with the fixed-pitch BEMT map, against the POH 730 ft/min.
    Landing is Raymer Sec. 17.9 at γ = 3°, the 5.2 % maximum gradient of 14 CFR / CS
    23.75(a)(1), against the POH short-field 1335 ft (407 m). Ground effect on induced
    drag (Hoerner & Borst 1975; McCormick 1979) lowers drag and lengthens the braking
    roll, so it is not added to close this gap. Take-off ground roll is the POH 960 ft
    (293 m) and already passes. Rotation uses the constant-diameter belly; Raymer Ch. 11
    asks for 10–15°. The check tolerance in ``performance_analysis`` stays 0.1 %.
    """
    res, _ = c172
    checks = {c.key: c for c in res.checks}
    by_req = {c["requisito"]: c for c in res.performance.requirement_compare}
    climb, land, takeoff = by_req["climb_rate"], by_req["landing_distance"], by_req["takeoff_ground_roll"]
    assert checks["perf:climb_rate"].ok is False
    assert checks["perf:landing_distance"].ok is False
    assert checks["gear:rotation"].ok is False
    assert climb["ok"] is False and land["ok"] is False and takeoff["ok"] is True
    assert climb["obtido"] < climb["requerido"] * (1 - 1e-3)
    assert land["obtido"] > land["requerido"] * (1 + 1e-3)
    # 30 Oct 2026 pipeline: −2.0 % climb, +23.8 % landing, −6.3 % take-off ground roll.
    assert (climb["obtido"] - climb["requerido"]) / climb["requerido"] == pytest.approx(-0.020, abs=0.005)
    assert (land["obtido"] - land["requerido"]) / land["requerido"] == pytest.approx(0.238, abs=0.02)
    assert (takeoff["obtido"] - takeoff["requerido"]) / takeoff["requerido"] == pytest.approx(-0.063, abs=0.02)
    assert res.landing_gear.rotation_deg == pytest.approx(6.7, abs=0.2)
    assert res.landing_gear.rotation_deg < 10.0
    ld = res.performance.landing
    assert ld["gamma_deg"] == pytest.approx(3.0)
    assert ld["total_50ft"] == pytest.approx(land["obtido"], rel=1e-6)


@pytest.mark.requires_avl
def test_lowfi_aero_c172(c172):
    res, _ = c172
    lf = res.lowfi
    assert lf is not None
    assert lf.CD0 == pytest.approx(res.buildup.CD0, rel=0.15)
    assert 0.80 < lf.e_eff < 1.0 and lf.fit_rms < 2e-3


@pytest.mark.slow
def test_uav_pipeline_reports(uav):
    res, rep = uav
    # Phase 3: takeoff+climb energy now from the segment model -> baseline (AR 14 by hand) breaks the 4.2 m span
    # limit only; reported honestly, `acdt optimize` resolves it (test_phase3)
    failed = {c.key for c in res.checks if c.ok is False and not c.key.startswith(("perf:", "hq:", "aeroel:", "wb:", "gear:"))}
    # NeuralFoil (extra wingbox) can lift W0 over the 25 kg limit. Both outcomes are accepted,
    # as in tests/test_examples_cli.py::test_cli_uav.
    assert "wing_span" in failed and failed <= {"wing_span", "mtow"}
    assert res.structures.vn.regulation == "stanag_4671"
    assert res.stability.SM_aft > 0.05
    txt = rep.read_text(encoding="utf-8")
    for sec in ("## 10.", "## 11.", "## 12.", "## 13."):
        assert sec in txt
    for f in ("vn_diagram.png", "wing_loads.png", "wing_box.png", "cg_envelope.png", "payload_range.png",
              "climb_ceiling.png"):
        assert (rep.parent / f).exists(), f
    d = json.loads((rep.parent / "result.json").read_text())
    assert "stability" in d and "performance" in d and "verified_segment_mission" in d
    # segment-mission endurance close to the requirement (energy sizing uses a simplified climb budget)
    e = {c["requisito"]: c for c in res.performance.requirement_compare}["endurance"]
    assert e["obtido"] == pytest.approx(e["requerido"], rel=0.06)


@pytest.mark.slow
def test_lowfi_falls_back_without_binaries(monkeypatch, tmp_path):
    import shutil as _sh
    real = _sh.which
    from acdt.domains.aircraft.aero import airfoil as _af
    pytest.importorskip("neuralfoil")
    monkeypatch.setattr(_sh, "which", lambda n, *a, **k: None if n in ("avl", "xfoil") else real(n, *a, **k))
    monkeypatch.setenv("ACDT_POLAR_CACHE", "off")  # o cache em disco guardaria polares XFOIL
    _af._cached.cache_clear()
    st = run_pipeline("aircraft", EX / "cessna172_check.yaml", output=tmp_path)
    res = st["result"]
    assert res.feasible and res.lowfi is not None
    _af._cached.cache_clear()
    assert "NeuralFoil" in res.lowfi.airfoil_source and res.lowfi.span_source.startswith("Schrenk")
    assert res.stability.xbar_np_avl is None and res.avl is None
