"""Phase 5: airfoil-contour sections, lifting line, structural–aerodynamic wing problem, 3-D preview."""
import math
from pathlib import Path

import numpy as np
import pytest

from acdt.domains.aircraft.wingbox.aero import LiftingLine
from acdt.domains.aircraft.wingbox.section import Contour, wing_section

EX = Path(__file__).resolve().parents[1] / "examples"


def test_lifting_line_elliptic():
    """Elliptic planform, no twist: e = 1, C_Di = C_L²/(π AR), C_L = a AR/(AR+2)… (Anderson §5.3.1)."""
    b, c0 = 10.0, 1.0
    ll = LiftingLine(b, lambda y: c0 * np.sqrt(np.clip(1 - (2 * np.asarray(y) / b) ** 2, 1e-12, None)), 20)
    a0 = 2 * math.pi * np.ones(ll.n)
    al, A, CL, CDi, ccl = ll.trim(0.5, np.zeros(ll.n), a0, np.zeros(ll.n))
    assert CDi == pytest.approx(CL**2 / (math.pi * ll.AR), rel=1e-3)
    assert CL / al == pytest.approx(2 * math.pi / (1 + 2 / ll.AR), rel=2e-3)
    # ∫ c·cl dy over the span = C_L S
    y = ll.y
    assert 2 * np.trapezoid(ccl[::-1], y[::-1]) == pytest.approx(CL * ll.S, rel=0.02)


def test_dnose_moves_shear_centre_forward():
    kw = dict(t_up=1.2e-3, t_lo=1.0e-3, t_wf=1.5e-3, t_wr=1.0e-3, E=72e9, G=27e9)
    ct = Contour(0.02, 0.4, 0.12)
    s0 = wing_section(1.5, ct, 0.2, 0.65, **kw)
    s1 = wing_section(1.5, ct, 0.2, 0.65, t_le=0.6e-3, **kw)
    assert 0.2 < s1.x_sc / 1.5 < s0.x_sc / 1.5 < 0.65
    assert s1.GJ > s0.GJ


@pytest.fixture(scope="module")
def c172():
    from acdt.core.pipeline import run_pipeline
    return run_pipeline("aircraft", str(EX / "cessna172_check.yaml"))["result"]


@pytest.mark.slow
def test_section_axis_in_phase3(c172):
    d = c172.structures.box.details
    assert "x_sc_c" in d and 0.2 < d["x_sc_c"][0] < 0.425           # ahead of mid-box (D-nose)
    # section GJ vs Phase 3 Bredt single cell: same order, D-nose adds stiffness
    assert 0.8 < c172.structures.box.GJ[0] / d["GJ_phase3"][0] < 2.0


def test_wingbox_problem_tradeoffs(c172, tmp_path):
    from acdt.domains.aircraft.wingbox.optimize import WingBoxProblem
    from acdt.domains.aircraft.wingbox.render import render_wing_structure
    P = WingBoxProblem(c172, "range")
    b = P.base
    # Level A box mass within 10 % of the Phase 3 box (same sizing, LLT vs Schrenk loads)
    assert b.mass_box == pytest.approx(c172.structures.box.masses["total"], rel=0.10)
    assert b.perf["range_m"] == pytest.approx(P.R0, rel=1e-9)        # calibrated baseline
    thick = P.evaluate({"tc_root": 0.15, "tc_tip": 0.15})
    assert thick.mass_box < b.mass_box                                 # deeper box → lighter
    assert thick.cruise["CDp_wing"] > b.cruise["CDp_wing"]             # thicker → more profile drag
    # elastic twist changes the span loading and induced drag
    rigid = P._llt_elastic(b.cruise["CL"], 0.5 * P.rho_c * P.V_c**2, b.x, P._polars(b.x),
                           1e12 * np.ones_like(P.y), b.section["x_sc_c"])
    assert abs(b.cruise["theta_e_tip_deg"]) > 1e-3
    assert rigid["CDi"] != pytest.approx(b.cruise["CDi"], rel=1e-5)
    # washout lowers the tip cl
    wo = P.evaluate({"twist_tip": -3.0})
    assert wo.cruise["cl_y"][-5] < b.cruise["cl_y"][-5]
    p = render_wing_structure(P.wing, b.x, b.box, tmp_path / "w.png", "t", P.p, b.section["x_sc_c"])
    assert Path(p).stat().st_size > 10000


def test_run_study_outputs(c172, tmp_path):
    from acdt.domains.aircraft.wingbox.study import run_study
    s = run_study(c172, tmp_path, "range", "c172", tc_sweep=[0.14], maxiter=2, sweep_maxiter=2, fem=False)
    assert s["optimum"]["feasible"]
    assert s["optimum"]["perf"]["range_m"] >= s["baseline"]["perf"]["range_m"] * 0.999
    for p in s["paths"].values():
        assert Path(p).stat().st_size > 10000


def test_rear_spar_bound_uses_most_forward_te_hinge():
    """Split aileron at 0.40c is ahead of the elevon at 0.25c → xr_max = 0.57c (0.03c clearance)."""
    from acdt.domains.aircraft.wingbox.optimize import rear_spar_xr_max
    xr, surfs = rear_spar_xr_max({
        "assembly": {"options": {"flying_wing": {
            "split_aileron": {"cf_c": 0.40, "eta_inner": 0.45, "eta_outer": 0.98},
            "elevon": {"cf_c": 0.25, "eta_inner": 0.20, "eta_outer": 0.45},
        }}}
    })
    assert xr == pytest.approx(1.0 - 0.40 - 0.03)
    assert {s["name"] for s in surfs} == {"split_aileron", "elevon"}
    # conventional default is not mixed in once flying-wing surfaces are listed
    assert all(s["source"].startswith("assembly.options.flying_wing") for s in surfs)


def test_rear_spar_bound_default_conventional():
    from acdt.domains.aircraft.wingbox.optimize import rear_spar_xr_max
    xr, surfs = rear_spar_xr_max({})
    assert xr == pytest.approx(0.72)
    assert surfs[0]["name"] == "aileron" and surfs[0]["cf_c"] == pytest.approx(0.25)


def test_rear_spar_bound_stability_override():
    from acdt.domains.aircraft.wingbox.optimize import rear_spar_xr_max
    xr, _ = rear_spar_xr_max({"stability": {"aileron_cf_c": 0.30}})
    assert xr == pytest.approx(1.0 - 0.30 - 0.03)


def test_clamp_rear_spar_moves_baseline_ahead_of_hinge():
    from acdt.domains.aircraft.wingbox.optimize import clamp_rear_spar
    x0 = {"xr": 0.65}
    bounds = {"xr": (0.50, 0.72)}
    notes = clamp_rear_spar(x0, bounds, 0.57)
    assert x0["xr"] == pytest.approx(0.57)
    assert bounds["xr"] == (0.50, 0.57)
    assert notes and "0.650" in notes[0] and "0.570" in notes[0]


def test_wingbox_problem_clamps_default_rear_spar_for_flying_wing(c172):
    """Phase-3 default rear spar (0.65c) sits behind a 0.40c split-aileron hinge; the problem must clamp."""
    import copy
    from acdt.domains.aircraft.wingbox.optimize import WingBoxProblem
    res = copy.copy(c172)
    res.spec = copy.copy(c172.spec)
    res.spec.assumptions = copy.deepcopy(dict(c172.spec.assumptions))
    res.spec.assumptions.setdefault("assembly", {}).setdefault("options", {})["flying_wing"] = {
        "split_aileron": {"cf_c": 0.40, "eta_inner": 0.45, "eta_outer": 0.98},
        "elevon": {"cf_c": 0.25, "eta_inner": 0.20, "eta_outer": 0.45},
    }
    P = WingBoxProblem(res, "weight")
    assert P.xr_max == pytest.approx(0.57)
    assert P.x0["xr"] <= P.xr_max + 1e-12
    assert P.bounds["xr"][1] == pytest.approx(0.57)
    assert P.hinge_notes
    ev = P.evaluate(P.x0)
    assert ev.x["xr"] <= 0.57 + 1e-12



def _mini_assembly_spec(twist_tip_deg=-10.0):
    return {"assembly": {"components": [
        {"type": "surface", "name": "wing", "mirror": True,
         "panel": {"root_chord": 1.0, "tip_chord": 0.6, "span": 4.0, "sweep_le_deg": 20.0,
                   "twist_tip_deg": twist_tip_deg}}
    ]}}


def test_geometric_twist_tip_from_assembly():
    from types import SimpleNamespace
    from acdt.domains.aircraft.wingbox.optimize import geometric_twist_tip_deg
    assert geometric_twist_tip_deg(SimpleNamespace())["status"] == "no_assembly"
    res = SimpleNamespace(assembly_loop={"spec": _mini_assembly_spec(-10.0)})
    r = geometric_twist_tip_deg(res)
    assert r["status"] == "assessed"
    assert r["twist_tip_deg"] == pytest.approx(-10.0)


def test_hold_section_freezes_tc_camber_and_twist(c172):
    """Opt-in hold_section keeps the baseline t/c, camber and twist; SLSQP may only move spars / ribs / k_skin."""
    from acdt.domains.aircraft.wingbox.optimize import HOLD_SECTION_VARS, WingBoxProblem
    P = WingBoxProblem(c172, "weight", hold_section=True)
    assert P.hold_section
    for k in HOLD_SECTION_VARS:
        assert P.bounds[k][0] == pytest.approx(P.x0[k])
        assert P.bounds[k][1] == pytest.approx(P.x0[k])
    r = P.optimise(maxiter=3)
    for k in HOLD_SECTION_VARS:
        assert r["x"][k] == pytest.approx(P.x0[k], abs=1e-12)


def test_hold_section_reads_drawn_washout(c172):
    """Without an assembly the baseline twist is 0; with a drawn washout it becomes the tip twist."""
    import copy
    from acdt.domains.aircraft.wingbox.optimize import WingBoxProblem
    P0 = WingBoxProblem(c172, "weight")
    assert P0.x0["twist_tip"] == pytest.approx(0.0)
    res2 = copy.copy(c172)
    res2.assembly_loop = {"spec_scaled": _mini_assembly_spec(-10.0)}
    P = WingBoxProblem(res2, "weight", hold_section=True)
    assert P.x0["twist_tip"] == pytest.approx(-10.0)
    assert P.bounds["twist_tip"] == (-10.0, -10.0)
    ev = P.evaluate(P.x0)
    assert ev.x["twist_tip"] == pytest.approx(-10.0)


def test_flying_wing_reversal_uses_elevon_span(c172):
    """Reversal constraint is the inboard elevon, not a fictitious outboard aileron; split yaw is unassessed."""
    import copy
    from acdt.domains.aircraft.wingbox.optimize import WingBoxProblem
    res = copy.copy(c172)
    res.spec = copy.copy(c172.spec)
    res.spec.assumptions = copy.deepcopy(dict(c172.spec.assumptions))
    res.spec.assumptions.setdefault("assembly", {}).setdefault("options", {})["flying_wing"] = {
        "split_aileron": {"cf_c": 0.40, "eta_inner": 0.45, "eta_outer": 0.98},
        "elevon": {"cf_c": 0.25, "eta_inner": 0.20, "eta_outer": 0.45},
    }
    P = WingBoxProblem(res, "weight")
    ev = P.evaluate(P.x0)
    names = {c["name"]: c for c in ev.aeroelastic["controls"]}
    assert set(names) == {"elevon", "split_aileron"}
    assert ev.aeroelastic["reversal_surface"] == "elevon"
    assert names["split_aileron"]["yaw_effectiveness"] == "unassessed"
    assert names["elevon"]["role"] == "roll_pitch"
    assert "effectiveness_at_1_2_VD" in names["elevon"]
