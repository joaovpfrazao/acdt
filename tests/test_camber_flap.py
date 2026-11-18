"""Fase 9 — camber flaps as a design option (fast: NeuralFoil surrogate, disk cache off)."""
import numpy as np
import pytest

from acdt.domains.aircraft.aero.camber_flap import (CamberSchedule, resolve, section_envelope)
from acdt.domains.aircraft.aero.drag import DragPolar

nf = pytest.importorskip("neuralfoil")


@pytest.fixture(autouse=True)
def _no_disk_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("ACDT_POLAR_CACHE", str(tmp_path))


def test_resolve_defaults():
    assert resolve(None) is None
    c, f = resolve({"kind": "camber"}), resolve({"kind": "flaperon"})
    assert c["eta_out"] == 0.65 and c["actuators"] == 2
    assert f["eta_out"] == 0.95 and f["actuators"] == 0
    assert c["actuator_mass_kg"] is None  # no invented masses


def test_section_envelope_neuralfoil():
    sec = section_envelope("NACA 4415", 1e6, 0.0, 1.0, 0.2, (-10, -5, 0, 5, 10, 15), prefer="neuralfoil")
    cl = np.array([0.1, 0.3, 0.6, 1.0, 1.3])
    cd_env, dl = sec.envelope(cl)
    clean = sec.polars[sec.deltas.index(0.0)].cd_at_cl(cl)
    assert np.all(cd_env <= clean + 1e-12)            # envelope never worse than the clean section
    assert dl[0] <= 0 and dl[-1] >= 0                 # negative δ at low cl, positive at high cl
    assert sec.clmax(15.0) > sec.clmax(0.0) + 0.1     # flap raises clmax
    assert "NeuralFoil" in sec.source


def _sched(dcd_min=-0.002):
    CL = np.linspace(0, 1.4, 15)
    dCD = dcd_min * np.exp(-((CL - 1.0) / 0.3) ** 2)
    return CamberSchedule("camber", CL, dCD, np.sign(CL - 0.5) * 5, 0.6, 0.15, 0.1, 15.0, -0.01)


def test_dragpolar_with_camber_numeric_optimum():
    base = DragPolar(0.025, 0.045)
    env = DragPolar(0.025, 0.045, _sched())
    assert env.CD(1.0) < base.CD(1.0)
    assert env.LD_max > base.LD_max
    # zero schedule → same optimum as the analytic polar (within the grid step)
    z = DragPolar(0.025, 0.045, _sched(0.0))
    assert z.LD_max == pytest.approx(base.LD_max, rel=2e-3)
    assert z.CL_LDmax == pytest.approx(base.CL_LDmax, rel=0.03)
    assert z.CL_min_power == pytest.approx(base.CL_min_power, rel=0.03)


def test_xfoil_flap_cmd():
    from acdt.domains.aircraft.aero.airfoil import _xfoil_flap_cmd
    assert _xfoil_flap_cmd(None) == "" and _xfoil_flap_cmd((0.8, 0.0)) == ""
    c = _xfoil_flap_cmd((0.8, -5.0))
    assert c.startswith("GDES\nFLAP\n0.8000") and "-5.000" in c


def test_polar_disk_cache_roundtrip(tmp_path, monkeypatch):
    from acdt.domains.aircraft.aero import airfoil as af
    monkeypatch.setenv("ACDT_POLAR_CACHE", str(tmp_path / "pc"))
    af._cached.cache_clear()
    p1 = af.airfoil_polar("NACA 2412", 5e5, prefer="neuralfoil", flap=(0.8, 5.0))
    assert len(list((tmp_path / "pc").glob("*.json"))) == 1
    af._cached.cache_clear()
    p2 = af.airfoil_polar("NACA 2412", 5e5, prefer="neuralfoil", flap=(0.8, 5.0))
    assert np.allclose(p1.cd, p2.cd) and p1.source == p2.source


def _fast_uav():
    from acdt.domains.aircraft.mission import MissionSpec
    s = MissionSpec.from_yaml("examples/uav_endurance_payload.yaml")
    s.assumptions["aero"]["fidelity"] = "handbook"
    s.assumptions["aero"]["airfoil_solver"] = "neuralfoil"
    s.assumptions["aero"]["airfoil"] = "NACA 4412"
    return s


def test_variant_spec_options():
    from acdt.domains.aircraft.design_options import variant_spec
    s = _fast_uav()
    assert variant_spec(s, "none").assumptions["aero"]["flap"]["kind"] == "none"
    p = variant_spec(s, "plain")
    assert p.assumptions["aero"]["flap"]["kind"] == "plain" and p.assumptions["aero"]["camber_flap"] is None
    c = variant_spec(s, "camber", {"camber": {"chord_ratio": 0.18}})
    assert c.assumptions["aero"]["flap"]["kind"] == "none"
    assert c.assumptions["aero"]["camber_flap"] == {"kind": "camber", "chord_ratio": 0.18}
    assert c.assumptions["cost"]["F_CF"] == 1.03
    with pytest.raises(ValueError):
        variant_spec(s, "fowler_magic")


@pytest.mark.slow
def test_flap_options_study_fast():
    from acdt.domains.aircraft.design_options import flap_options_study
    s = _fast_uav()
    st = flap_options_study(s, options=("plain", "camber"), objective="W0", min_gain=0.5, performance=False,
                            per_option={"camber": {"actuator_mass_kg": 0.05, "surface_mass_kg_m2": 0.2}})
    rows = {r["option"]: r for r in st["rows"]}
    assert {"plain", "camber", "plain_same_area"} <= set(rows)
    cam = rows["camber"]
    assert cam["camber"]["dCD_min"] < 0 and cam["flap_system_kg"] > 0.1
    # a 50 % margin can never be met → camber is never selected without justification
    assert st["selected"] in ("plain", "plain_same_area") or not rows["plain"]["feasible"]
    assert all(d.get("vs") for d in st["deltas"].values())
