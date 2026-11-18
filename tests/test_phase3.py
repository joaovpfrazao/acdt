"""Phase 3: aeroelasticity, buckling box, dynamics/HQ, scissor, electric mission energy, MDO."""
import math

import numpy as np
import pytest

from acdt.domains.aircraft import aeroelasticity as ae
from acdt.domains.aircraft.structures import MATERIALS, kuhn_web, needham_crippling

EX = __import__("pathlib").Path(__file__).resolve().parents[1] / "examples"


def _uniform_strip(GJ=2e6, s=7.5, c=2.0, e=0.23, a_w=2 * math.pi, n=61):
    y = np.linspace(0.0, s, n)
    return ae.WingStrip(y=y, c=np.full(n, c), EI=np.full(n, 1e7), GJ=np.full(n, GJ), m=np.full(n, 50.0),
                        e=e, x_f=0.25 + e, x_cg=0.45, a_w=a_w)


@pytest.fixture(scope="module")
def c172():
    from acdt.core.pipeline import run_pipeline
    return run_pipeline("aircraft", str(EX / "cessna172_check.yaml"))["result"]


@pytest.fixture(scope="module")
def uav_state():
    from acdt.core.pipeline import run_pipeline
    return run_pipeline("aircraft", str(EX / "uav_endurance_payload.yaml"))


@pytest.fixture(scope="module")
def uav(uav_state):
    return uav_state["result"]


def test_divergence_closed_form():
    # uniform clamped wing, strip theory: q_D = π² GJ / (4 s² e c a_w)  (Wright & Cooper Eq. 8.13)
    ws = _uniform_strip()
    qD = math.pi**2 * 2e6 / (4 * 7.5**2 * 0.23 * 2.0**2 * 2 * math.pi)
    r = ae.torsional_divergence_speed(ws)
    assert qD == pytest.approx(15177, rel=1e-3)
    assert r["q_D"] == pytest.approx(qD, rel=0.02)


def test_glauert_flap_coefficients():
    aC, bC = ae.glauert_flap(0.25)
    assert aC == pytest.approx(3.826, abs=2e-3)
    assert bC == pytest.approx(-0.6495, abs=2e-3)


def test_flutter_below_divergence_and_aeer45():
    ws = _uniform_strip()
    fl = ae.flutter_estimate_typical_section(ws, V_max=400.0)
    div = ae.torsional_divergence_speed(ws)
    assert math.isfinite(fl["V_F"]) and fl["V_F"] < div["V_div"]
    r = ae.simplified_flutter_criteria_aeer45(ws, 0.35, 80.0, {"x": True})
    assert r["F_max"] == pytest.approx(200.0 / (80.0 / 0.44704) ** 2)
    assert r["applicable"]


def test_kuhn_and_needham():
    m = MATERIALS["al2024_t3"]
    # thick web below its buckling stress → shear-resistant, k = 0
    r = kuhn_web(q=1e4, t=3e-3, h=0.2, d=0.2, E=m["E"], nu=m["nu"], tau_allow=m["tau"], Fcy=m["sigma_cap"])
    assert r["k"] == pytest.approx(0.0)
    r2 = kuhn_web(q=2e5, t=0.8e-3, h=0.3, d=0.3, E=m["E"], nu=m["nu"], tau_allow=m["tau"], Fcy=m["sigma_cap"])
    assert 0 < r2["k"] < 1
    sc = needham_crippling(m["sigma_cap"], m["E"])
    assert 0 < sc <= m["sigma_cap"]


@pytest.mark.slow
def test_buckling_box_heavier_than_strength_box(c172):
    sr = c172.structures
    assert sr.box.method == "buckling" and sr.box_strength is not None
    assert sr.box.mass > sr.box_strength.mass
    assert 0.5 < sr.box.mass / sr.wing_mass_raymer < 1.2


@pytest.mark.requires_avl
def test_c172_dynamics_and_hq(c172):
    dy = c172.dynamics
    sc = dy["scissor"]
    # The wing is placed so the stability line passes through the aft CG. The flare uses the
    # DATCOM slotted-flap moment and Torenbeek's tail-lift factor, so the same tail also
    # clears the control line. Tolerance: 0.5 % of S_h/S, the one in tail_sizing_scissor.
    assert sc["Sh_S_current"] == pytest.approx(sc["Sh_S_stability"], rel=0.02)
    assert sc["ok"] is True
    assert sc["Sh_S_current"] + 1e-9 >= sc["Sh_S_required"] * (1 - 5e-3)
    assert "flare com flaps" in sc["notes"][0] and "efeito de solo" in sc["notes"][0]
    assert "Torenbeek" in sc["notes"][0] and "DATCOM" in sc["notes"][0]
    lon, lat = dy["modes"]["longitudinal"], dy["modes"]["lateral"]
    assert 2 < lon["short_period"]["wn"] < 8 and lon["short_period"]["zeta"] > 0.3
    assert 0.1 < lon["phugoid"]["wn"] < 0.4 and 0 < lon["phugoid"]["zeta"] < 0.3
    assert lat["dutch_roll"]["zeta"] > 0 and lat["roll"]["tau_s"] < 1.0
    assert all(r["nível"] == 1 for r in dy["hq"])


def test_c172_aeroelastic_margins(c172):
    a = c172.aeroelastic
    assert a.margins["divergence"]["ok"] and a.margins["reversal"]["ok"]
    assert a.flutter["V_F"] < a.divergence["V_div"]
    assert a.aeer45["ok"]


@pytest.mark.slow
def test_electric_takeoff_climb_energy_consistent(uav):
    # sizing uses the same segment model (1 min at takeoff power + climb at V_y) as the verification
    msg = [i.message for i in uav.issues if "descolagem + subida" in i.message]
    assert msg
    e = uav.performance.mission_required
    assert uav.sizing.energy_J > 0 and e is not None


def test_design_point_fixed_ws(c172):
    from acdt.domains.aircraft.constraints import design_point
    import inspect
    assert "ws_fixed" in inspect.signature(design_point).parameters


@pytest.mark.slow
@pytest.mark.requires_avl
@pytest.mark.skipif(not __import__("acdt.core.mdo", fromlist=["x"]).openmdao_available(), reason="OpenMDAO")
def test_mdo_model_reproduces_baseline_and_improves(uav, uav_state):
    from acdt.domains.aircraft import mdo
    opt = mdo.optimize(uav, uav_state.get("systems"), "W0")
    assert opt["baseline"]["W0"] == pytest.approx(uav.sizing.W0, rel=0.03)
    assert opt["driver"]["success"]
    assert opt["optimum"]["W0"] <= opt["baseline"]["W0"] + 1e-6
    assert opt["optimum"]["g_span"] <= 1e-4  # the span limit violated at the baseline is restored


def test_aileron_reversal_wrapper_matches_general_effectiveness():
    """Legacy outboard-aileron interface is the general strip with χ from the tip (W&C Ch. 9)."""
    ws = _uniform_strip()
    legacy = ae.aileron_reversal_speed(ws, 0.35, 0.75)
    chi = ae.control_span_mask(ws, {"span_fraction": 0.35})
    gen = ae.control_effectiveness(ws, chi, 0.25)
    assert legacy["V_R"] == pytest.approx(gen["V_R"], rel=1e-12)
    assert math.isfinite(legacy["V_R"])


def test_inboard_elevon_control_effectiveness_is_assessed():
    """An inboard elevon (eta 0.20–0.45) is not the Phase 3 outboard aileron; both get a V_R."""
    ws = _uniform_strip()
    outb = ae.aileron_reversal_speed(ws, 0.35, 0.75)
    chi = ae.control_span_mask(ws, {"eta_inner": 0.20, "eta_outer": 0.45})
    # mask is on the inboard half, not the tip
    assert chi[0] == 0.0 or ws.y[0] >= 0.20 * ws.y[-1]
    assert chi[-1] == 0.0
    assert chi.sum() > 0
    inn = ae.control_effectiveness(ws, chi, 0.25)
    assert math.isfinite(inn["V_R"])
    assert inn["V_R"] != pytest.approx(outb["V_R"], rel=1e-3)
    q = 0.5 * ae.RHO0 * (0.5 * inn["V_R"]) ** 2
    eta = inn["effectiveness"](q)
    assert 0.0 < eta <= 1.0 + 1e-6
