"""P6 light N2 shape + packaging score."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from acdt.domains.aircraft.rcs import geometry as G
from acdt.domains.aircraft.shape_opt import packaging_score, run_n2_study
from acdt.domains.aircraft.shape_opt.n2 import evaluate_n2
from acdt.domains.aircraft.rcs import study as St

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "examples" / "output" / "uav_endurance_payload_mdo" / "baseline" / "result.json"


def test_shape_defaults_preserve_phase6_mesh():
    base = {"S": 1.2, "b": 4.0, "taper": 0.6, "tc": 0.12, "L": 1.8, "D": 0.22,
            "S_h": 0.15, "S_v": 0.08, "tail_arm": 1.0, "AR": 14.0}
    m0, i0 = G.aircraft_mesh(base, G.Shape(0, 0, 45, 42))
    m1, i1 = G.aircraft_mesh(base, G.Shape())  # all defaults
    assert i0["fuselage"]["W"] == pytest.approx(i1["fuselage"]["W"])
    assert abs(i1["z_wing"]) < 1e-12


def test_wing_z_and_scales_change_info():
    base = {"S": 1.2, "b": 4.0, "taper": 0.6, "tc": 0.12, "L": 1.8, "D": 0.22,
            "S_h": 0.15, "S_v": 0.08, "tail_arm": 1.0, "AR": 14.0}
    _, mid = G.aircraft_mesh(base, G.Shape())
    _, hi = G.aircraft_mesh(base, G.Shape(wing_z_frac=0.8, L_scale=1.1, D_scale=1.05,
                                          x_wing_le_frac=0.4, sensor_x_frac=0.1))
    assert hi["z_wing"] > mid["z_wing"]
    assert hi["L"] == pytest.approx(1.8 * 1.1)
    assert hi["sensor_x"] < mid["sensor_x"]


def test_packaging_score_volume_and_fov():
    info = {"L": 2.0, "D": 0.3, "x_wing_le": 0.8, "sensor_x": 0.3}
    ok = packaging_score(info, payload={"volume_l": 2.0})
    assert ok["pack_ok"]
    bad = packaging_score(info, payload={"volume_l": 500.0})  # huge
    assert not bad["volume_ok"]
    blocked = packaging_score({"L": 2.0, "D": 0.3, "x_wing_le": 0.35, "sensor_x": 0.3},
                              payload={"volume_l": 0.1})
    assert not blocked["fov_ok"]


@pytest.mark.skipif(not RESULT.exists(), reason="example result.json missing")
def test_n2_study_small(tmp_path):
    out = run_n2_study(RESULT, tmp_path / "n2", n_samples=4, seed=1,
                       payload={"volume_l": 2.5})
    assert out["rows"]
    assert (tmp_path / "n2" / "shape_n2.json").exists()
    assert "pareto" in out
