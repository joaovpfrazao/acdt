"""Adapters to external open-source tools (skipped when the optional tool is absent)."""
from pathlib import Path

import numpy as np
import pytest

from acdt.domains.aircraft.aero.interfaces import write_avl
from acdt.domains.aircraft.mission import MissionSpec
from acdt.domains.aircraft.sizing import run

EX = Path(__file__).parents[1] / "examples"


@pytest.fixture(scope="module")
def uav():
    return run(MissionSpec.from_yaml(EX / "uav_endurance_payload.yaml"))


def test_write_avl(uav, tmp_path):
    p = write_avl(uav.config, tmp_path / "uav.avl", cd0=uav.polar.CD0)
    txt = p.read_text()
    assert txt.count("SURFACE") == 3 and "NACA\n4412" in txt


def test_neuralfoil_polar():
    pytest.importorskip("neuralfoil")
    from acdt.domains.aircraft.aero.interfaces import neuralfoil_polar
    r = neuralfoil_polar("naca4412", np.array([0.0, 5.0]), 6e5)
    assert 0.3 < float(r["CL"][0]) < 0.7 and float(r["CL"][1]) > float(r["CL"][0])


def test_aerosandbox_crosscheck_lift_slope(uav):
    pytest.importorskip("aerosandbox")
    from acdt.domains.aircraft.aero.interfaces import aerosandbox_crosscheck
    r = aerosandbox_crosscheck(uav.config, uav.cruise_speed, uav.cruise_altitude, 2.0, "vlm")
    # VLM includes the tail contribution; handbook (wing+body, Raymer Eq. 12.6) within ~25 %
    assert r["CL_alpha_per_rad"] == pytest.approx(uav.CLalpha, rel=0.25)
    b = aerosandbox_crosscheck(uav.config, uav.cruise_speed, uav.cruise_altitude, 2.0, "buildup")
    assert b["CD"] == pytest.approx(uav.polar.CD(b["CL"]), rel=0.35)
