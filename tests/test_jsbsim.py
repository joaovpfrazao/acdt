"""Cross-check of the in-house 6-DOF against JSBSim (LGPL-2.1, run as a separate process) using the same aero
data exported to JSBSim XML. Skipped when the jsbsim package is not installed in $ACDT_JSBSIM_PYTHON."""
import math

import pytest


pytestmark = [pytest.mark.requires_jsbsim, pytest.mark.requires_avl]  # o modelo de voo vem do AVL


@pytest.fixture(scope="module")
def fm(c172_result):
    from acdt.domains.aircraft.flightsim.aeromodel import build_flight_model
    return build_flight_model(c172_result)


def test_trim_matches(fm, tmp_path):
    from acdt.domains.aircraft.flightsim.jsbsim_runner import run_jsbsim
    from acdt.domains.aircraft.flightsim.sixdof import SixDOF, trim
    for V, h, fl in ((50.0, 1000.0, 0.0), (40.0, 300.0, 10.0)):
        ours = trim(SixDOF(fm), V, h, flap=fl)
        js = run_jsbsim(fm, [{"type": "trim", "V": V, "h": h, "flap": fl}], work_dir=tmp_path)["trim"]
        assert ours["ok"] and js["residual"] < 1e-4
        assert abs(ours["alpha_deg"] - js["alpha_deg"]) < 0.3
        assert abs(ours["delta_e_deg"] - js["delta_e_deg"]) < 0.3
        assert abs(ours["throttle"] - js["throttle"]) < 0.1 * js["throttle"]


def test_doublet_time_histories(fm, tmp_path):
    from acdt.domains.aircraft.flightsim.jsbsim_runner import compare_with_jsbsim
    r = compare_with_jsbsim(fm, 50.0, 1000.0, T=12.0, work_dir=tmp_path, plot=tmp_path / "p.png")
    for k in ("alpha", "q", "theta", "V", "h"):
        assert r["errors"][k]["nrms"] < 0.08, (k, r["errors"][k])
    lat = [{"t0": 1, "t1": 2, "da": math.radians(5)}, {"t0": 2, "t1": 3, "da": math.radians(-5)},
           {"t0": 5, "t1": 6, "dr": math.radians(5)}]
    r = compare_with_jsbsim(fm, 50.0, 1000.0, inputs=lat, T=12.0, work_dir=tmp_path)
    for k in ("phi", "p", "r", "beta"):
        assert r["errors"][k]["nrms"] < 0.08, (k, r["errors"][k])
    assert (tmp_path / "acdt" / "acdt.xml").exists() or list(tmp_path.rglob("*.xml"))


def test_export_consistency_fixes_11nov2026(fm, tmp_path):
    """11 nov 2026: (1) induced drag of the C_Lδe δe increment exported (trim throttle), (2) the side force is not
    transferred from the AERORP offset dx_fus c̄ (pitch-only correction), (3) JSBSim IC at 45° latitude (gravity
    ≈ g0). With a large C_Lδe and dx_fus the two integrators agree on trim and on a lateral doublet."""
    import copy
    from acdt.domains.aircraft.flightsim.jsbsim_runner import compare_with_jsbsim
    f2 = copy.deepcopy(fm)
    f2.aero.tables["CLde"] = [[0.8] * len(row) for row in f2.aero.tables["CLde"]]
    f2.aero.dx_fus = -0.1
    lat = [{"t0": 1, "t1": 2, "dr": math.radians(3)}, {"t0": 2, "t1": 3, "dr": math.radians(-3)}]
    r = compare_with_jsbsim(f2, 50.0, 1000.0, inputs=lat, T=6.0, work_dir=tmp_path)
    assert abs(r["trim_ours"]["throttle"] - r["trim_jsbsim"]["throttle"]) < 0.01 * r["trim_jsbsim"]["throttle"]
    assert abs(r["trim_ours"]["alpha_deg"] - r["trim_jsbsim"]["alpha_deg"]) < 0.02
    for k in ("phi", "p", "r", "beta"):
        assert r["errors"][k]["nrms"] < 0.03, (k, r["errors"][k])
    xml = next(tmp_path.rglob("acdt.xml")).read_text()
    assert "Yaw_aerorp_side_force_correction" in xml and "D_de_CL0" in xml
