"""Phase 6: Physical Optics RCS — canonical closed forms, facet integral, aircraft mesh, aero/RCS study."""
import math

import numpy as np
import pytest

from acdt.core.em import po, validate
from acdt.domains.aircraft.rcs import geometry as G
from acdt.domains.aircraft.rcs import study as St


def test_canonical_cases_within_tolerance():
    for c in validate.cases():
        assert c["ok"], c


def test_facet_integral_matches_quadrature():
    m = po.Mesh(np.array([[0, 0, 0], [0.7, 0.1, 0.05], [0.2, 0.6, -0.1]]), [(0, 1, 2)])
    rng = np.random.default_rng(1)
    w = rng.normal(size=(5, 3)) * 12
    I = po.facet_integrals(m, w)
    # brute-force: centroid rule on 200² congruent sub-triangles (O(h²) error)
    X, dA, _ = po._subsample(m, np.array([0]), 200)
    ref = (np.exp(1j * X @ w.T) * dA[:, None]).sum(0)
    assert np.allclose(I[:, 0], ref, rtol=1e-4, atol=1e-5 * m.area[0])
    # |p| → 0 branch
    I0 = po.facet_integrals(m, (m.n[0] * 3.0)[None])
    assert abs(I0[0, 0]) == pytest.approx(m.area[0], rel=1e-9)


def test_backface_and_occlusion():
    pl = po.plate(0.2, 0.2)
    s_back = po.monostatic(pl, 10e9, 0.0, 0.0, "VV", nose=(0, 0, -1), up=(1, 0, 0))
    assert s_back < 1e-20                                     # unlit side: no PO current
    two = pl.merged(pl.transformed(t=(0, 0, -0.5)))          # second plate hidden behind the first
    s1 = po.monostatic(two, 10e9, 0.0, 0.0, "VV", nose=(0, 0, 1), up=(1, 0, 0), occlusion=True)
    s0 = po.monostatic(pl, 10e9, 0.0, 0.0, "VV", nose=(0, 0, 1), up=(1, 0, 0))
    assert s1 == pytest.approx(s0, rel=1e-9)


def test_monostatic_po_is_polarisation_independent_single_bounce():
    m = po.icosphere(0.3, 3)
    a = po.monostatic(m, 5e9, np.linspace(-30, 30, 7), 5.0, "VV", nose=(1, 0, 0))
    b = po.monostatic(m, 5e9, np.linspace(-30, 30, 7), 5.0, "HH", nose=(1, 0, 0))
    assert np.allclose(a, b, rtol=1e-9)


BASE = dict(S=1.3077, b=4.2788, taper=0.6, tc=0.12, L=1.8, D=0.22, S_h=0.206, S_v=0.1696, tail_arm=0.99)


def test_faceted_aircraft_mesh_closed_outward_and_volume_preserving():
    for chine in (25.0, 45.0, 65.0):
        W, H, wt = G.hexagon_section(0.22, chine, 0.35)
        assert (2 * wt + H / math.tan(math.radians(chine))) * H / 2 == pytest.approx(math.pi * 0.22 ** 2 / 4)
    m, info = G.aircraft_mesh(BASE, G.Shape(35, 0.5, 40, 45))
    vol = np.sum(np.einsum("fi,fi->f", m.c, m.n) * m.area) / 3
    assert vol > 0
    pl = info["planform"]
    assert (pl["c_root"] + pl["c_tip"]) * pl["semispan"] == pytest.approx(BASE["S"])
    # Purser & Campbell projected-area rule
    assert info["S_vtail"] * math.cos(math.radians(45)) ** 2 >= BASE["S_h"] - 1e-12
    assert info["S_vtail"] * math.sin(math.radians(45)) ** 2 >= BASE["S_v"] - 1e-12
    full = G.planform(1.0, 4.0, 30, 0.5, 1.0)
    assert full["taper"] == pytest.approx(1.0) and full["sweep_te_deg"] == pytest.approx(30.0)


def test_oswald_nita_scholz_trends():
    e0 = St.oswald_nita_scholz(10, 0.45, 0.0)
    assert St.oswald_nita_scholz(10, 1.0, 0.0) < e0          # unswept: optimum taper near 0.35–0.45 (Hoerner)
    assert St.oswald_nita_scholz(10, 0.2, 35.0) > St.oswald_nita_scholz(10, 0.8, 35.0)


def test_aero_rcs_evaluator_and_pareto(tmp_path):
    res = {"name": "t", "geometry": {"wing": {"S_m2": 1.3077, "AR": 14, "span_m": 4.2788, "taper": 0.6, "t/c": 0.12,
                                               "sweep_LE_deg": 1.0},
                                      "fuselage": {"length_m": 1.8, "diameter_m": 0.22},
                                      "htail": {"S_m2": 0.206, "arm_m": 0.99}, "vtail": {"S_m2": 0.1696, "arm_m": 0.99}},
           "aero": {"CD0": 0.0232, "K": 0.0252, "cruise_speed_m_s": 22.0, "cruise_altitude_m": 600.0},
           "weights": {"W0_kg": 23.4}, "weight_breakdown": {"items": [{"key": "wing", "mass": 4.66},
                                                                      {"key": "fuselage", "mass": 1.09}]}}
    import json
    p = tmp_path / "result.json"
    p.write_text(json.dumps(res))
    base = St.baseline_from_result(p)
    ev = St.Evaluator(base, daz=2.0)
    b0 = ev(ev.s0)
    assert b0["aero"]["perf_ratio"] == pytest.approx(1.0) and b0["aero"]["CD0"] == pytest.approx(0.0232)
    swept = ev(G.Shape(40.0, 0.0, 45.0, ev.s0.tail_cant_deg))
    # frontal sector: sweeping the leading-edge flash out of |az| ≤ 30° lowers the PO frontal RCS
    assert swept["rcs"]["all"]["mean_dbsm"] < b0["rcs"]["all"]["mean_dbsm"]
    assert swept["aero"]["dW_struct_kg"] > 0                  # Raymer wing-weight sweep penalty
    mask = St.pareto_mask([1, 2, 1.5, 0.5], [0, 1, 2, -1])
    assert mask.tolist() == [True, True, False, True]
