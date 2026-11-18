"""L1 beam: closed-form checks, fuselage vs Raymer, wash-in, and the size-cycle hook."""
import math
import subprocess
import sys

import numpy as np
import pytest

from acdt import G0
from acdt.core.structures.beam import (cantilever_response, cylinder_axial_knockdown, thin_circular_tube,
                                      tube_thickness)
from acdt.core.structures.loads import (checked_maneuver_alpha, equilibrium_tail_load, surface_limit_lift)
from acdt.domains.aircraft.aero.drag import DragPolar
from acdt.domains.aircraft.aero.lift import clmax_clean
from acdt.domains.aircraft.geometry import Configuration, Fuselage, TrapezoidalWing, size_tails
from acdt.domains.aircraft.performance import PerfModel, climb_rate
from acdt.domains.aircraft.structures import MATERIALS, naca4_half_thickness
from acdt.domains.aircraft.structures_l1 import _uniform_tail, analyse, wing_beam_response, wing_elastic


def _ga():
    wing = TrapezoidalWing(16.2, 7.4, 0.7, 0.0, 0.12, 0.12)
    fus = Fuselage(8.0, 8.0 / 7.0)
    ht, vt = size_tails(wing, 0.60 * fus.length, 0.70, 0.04)
    return Configuration(wing, fus, ht, vt)


def test_core_package_does_not_import_domains():
    code = ("import acdt.core.structures, sys; "
            "assert not any(n.startswith('acdt.domains') for n in sys.modules)")
    subprocess.check_call([sys.executable, "-c", code])


def test_boxfem_is_the_shell_model():
    from acdt.core.fem import FEModel
    from acdt.core.structures import BoxFEM
    assert BoxFEM is FEModel


def test_sp8007_knockdown_and_clamp():
    # R/t = 100: φ = √(R/t)/16 = 0.625, γ = 1 − 0.901 (1 − e^{−φ}) ≈ 0.581 (NASA SP-8007, 1968).
    phi = math.sqrt(100.0) / 16.0
    gamma = 1.0 - 0.901 * (1.0 - math.exp(-phi))
    assert cylinder_axial_knockdown(100.0) == pytest.approx(gamma, rel=1e-12)
    assert cylinder_axial_knockdown(100.0) == pytest.approx(0.581, abs=0.002)
    assert cylinder_axial_knockdown(1.0e6) == 0.25


def test_thin_tube_and_cantilever_closed_form():
    R, t = 0.5, 0.002
    s = thin_circular_tube(R, t, n_booms=4, A_boom=1e-4)
    assert s["A_skin"] == pytest.approx(2 * math.pi * R * t)
    assert s["I_skin"] == pytest.approx(math.pi * R ** 3 * t)
    assert s["J"] == pytest.approx(2 * math.pi * R ** 3 * t)
    assert s["I_boom"] == pytest.approx(4 * 1e-4 * R ** 2 / 2)

    L, P, EI, GJ, T = 2.0, 1000.0, 1.0e6, 5.0e5, 200.0
    y = np.linspace(0.0, L, 401)
    M = P * (L - y)
    resp = cantilever_response(y, M, np.full_like(y, T), EI, GJ)
    assert resp["deflection_m"][-1] == pytest.approx(P * L ** 3 / (3 * EI), rel=0.005)
    assert resp["twist_rad"][-1] == pytest.approx(T * L / GJ, rel=0.005)
    y0 = 0.4
    resp2 = cantilever_response(y, M, np.full_like(y, T), EI, GJ, y0)
    assert resp2["deflection_m"][0] == 0.0
    assert resp2["deflection_m"][-1] == pytest.approx(P * (L - y0) ** 3 / (3 * EI), rel=0.005)
    assert resp2["twist_rad"][-1] == pytest.approx(T * (L - y0) / GJ, rel=0.005)


def test_tube_thickness_meets_yield_and_buckling():
    R, E, sig, tau = 0.4, 72.4e9, 269e6, 262e6
    M, T, V = 2.0e4, 500.0, 3000.0
    out = tube_thickness(M, T, V, R, E, sig, tau, 0.4e-3)
    assert out["sigma"] <= sig * 1.001
    assert out["sigma"] <= out["sigma_cr"] * 1.01
    assert out["t"] >= 0.4e-3


def test_tail_load_formulas():
    q, S, sweep, cl = 1500.0, 3.5, math.radians(20), 1.1
    assert surface_limit_lift(q, S, sweep, cl) / (q * S) == pytest.approx(clmax_clean(cl, sweep))
    # CG ahead of the wing a.c. → downward tail load.
    assert equilibrium_tail_load(3.8, 10000.0, 2.0, 2.5, 7.0) == pytest.approx(38000 * (2.0 - 2.5) / (7.0 - 2.5))
    # 23.423(b): n_m = 3.8, V = 100 kt → 39*3.8 / (100*(3.8−1.5)).
    V = 100 * 0.514444
    assert checked_maneuver_alpha(3.8, V, nose_up=True) == pytest.approx(39 * 3.8 / (100 * (3.8 - 1.5)))
    assert checked_maneuver_alpha(3.8, V, nose_up=False) < 0
    assert checked_maneuver_alpha(1.5, V) == 0.0


def test_uniform_tail_root_moment():
    cfg = _ga()
    L = 8000.0
    box = _uniform_tail(cfg.htail, L, "al2024_t3", 1.25)
    w = cfg.htail.as_wing()
    M = L * w.span / 8.0
    c0, tc = w.c_root, w.tc_root
    fs, rs = w.box.front_spar_xc, w.box.rear_spar_xc
    h = 0.95 * c0 * (float(naca4_half_thickness(fs, tc)) + float(naca4_half_thickness(rs, tc)))
    m = MATERIALS["al2024_t3"]
    A = max(1.5 * M / (h * m["sigma_cap"]), m["cap_min_area"])
    assert box.cap_area[0] == pytest.approx(A, rel=1e-6)


def test_fuselage_mass_within_25_percent_of_raymer():
    cfg = _ga()
    l1 = analyse(cfg, 1150.0, q_cruise=0.5 * 1.225 * 62.0 ** 2, V_cruise=62.0, CLmax=1.6, CLalpha=4.5,
                 engine_mass_kg=150.0, elastic=False, material="al2024_t3")
    ratio = l1.masses["fuselage_over_raymer"]
    assert l1.fuselage["governing"] == "tail_VA"
    assert 0.75 <= ratio <= 1.25
    rx = l1.fuselage["landing_reactions_N"]
    W_land = 0.95 * 1150.0 * G0
    assert rx["forward"] + rx["aft"] == pytest.approx(rx["n_gear"] * W_land, rel=1e-9)
    assert l1.masses["structural_cg_m"] > 0


def test_wash_in_is_monotonic_in_torsional_stiffness():
    from acdt.domains.aircraft.structures import wing_structure

    cfg = _ga()
    sr = wing_structure({"wing": cfg.wing, "W0": 1150.0, "CLmax": 1.6, "CLalpha": 4.5, "V_cruise_eas": 62.0,
                         "category": "normal", "regulation": "cs_23", "wing_mass_raymer": 120.0,
                         "material": "al2024_t3", "cm0": 0.0, "fuselage_width": cfg.fuselage.max_diameter,
                         "elastic_axis": "midbox"})
    q = 0.5 * 1.225 * 62.0 ** 2
    CL = 1150.0 * G0 / (q * cfg.wing.S)
    soft = wing_elastic(cfg.wing, sr.box, q, CL, k_GJ=0.5, cm0=0.0, y_clamp=cfg.fuselage.max_diameter / 2)
    mid = wing_elastic(cfg.wing, sr.box, q, CL, k_GJ=1.0, cm0=0.0, y_clamp=cfg.fuselage.max_diameter / 2)
    stiff = wing_elastic(cfg.wing, sr.box, q, CL, k_GJ=4.0, cm0=0.0, y_clamp=cfg.fuselage.max_diameter / 2)
    assert soft.tip_twist_deg > mid.tip_twist_deg > stiff.tip_twist_deg > 0
    assert soft.K_ratio > mid.K_ratio > stiff.K_ratio > 1.0
    assert soft.CLa_flex > soft.CLa_rigid
    assert mid.xac_w == pytest.approx(0.25, abs=1e-6)
    # Stiffer torsion → less induced drag → higher L/D and climb, toward the rigid wing.
    CD0 = 0.028
    def ld(k):
        return DragPolar(CD0, 0.045 * k).LD_max
    assert ld(soft.K_ratio) < ld(mid.K_ratio) < ld(stiff.K_ratio) < ld(1.0)
    def roc(k):
        m = PerfModel("piston_prop", cfg.wing.S, CD0, 0.045 * k, 1.5, 120e3, None, 0.8, 0.75, 0.55,
                      None, None, 0.7, 0.0, 1.6, 2.0)
        return climb_rate(m, 1150.0 * G0, 0.0)[0]
    assert roc(soft.K_ratio) < roc(mid.K_ratio) < roc(stiff.K_ratio)


def test_k_EI_scales_tip_deflection():
    from acdt.domains.aircraft.structures import wing_structure

    cfg = _ga()
    sr = wing_structure({"wing": cfg.wing, "W0": 1150.0, "CLmax": 1.6, "CLalpha": 4.5, "V_cruise_eas": 62.0,
                         "material": "al2024_t3", "elastic_axis": "midbox", "fuselage_width": 0.0})
    a = wing_beam_response(cfg.wing, sr.box, sr.beam, k_EI=1.0, k_GJ=1.0, y_clamp=0.0)
    b = wing_beam_response(cfg.wing, sr.box, sr.beam, k_EI=2.0, k_GJ=2.0, y_clamp=0.0)
    assert b["tip_m"] == pytest.approx(a["tip_m"] / 2.0, rel=0.01)
    assert b["tip_twist_deg"] == pytest.approx(a["tip_twist_deg"] / 2.0, rel=0.01)


def test_beam_tip_matches_boxfem_within_30_percent():
    """Slender rectangular box: Euler–Bernoulli / Bredt beam vs BoxFEM (QM6+MITC4). Shear is negligible."""
    from acdt.core.fem import isotropic
    from acdt.core.structures import BoxFEM
    from acdt.domains.aircraft.structures import bredt_gj

    L, w, h, t, P, Tq = 6.0, 0.50, 0.12, 0.003, 400.0, 500.0
    E, NU, RHO = 70e9, 0.3, 2700.0
    G = E / 2 / (1 + NU)
    ny, nw, nh = 24, 6, 4
    per = ([(-w / 2 + w * i / nw, h / 2) for i in range(nw)] + [(w / 2, h / 2 - h * i / nh) for i in range(nh)]
           + [(w / 2 - w * i / nw, -h / 2) for i in range(nw)] + [(-w / 2, -h / 2 + h * i / nh) for i in range(nh)])
    ys = np.linspace(0, L, ny + 1)
    nodes = [(x, y, z) for y in ys for (x, z) in per]
    npr = len(per)
    m = BoxFEM(np.array(nodes, float))
    sec = m.add_section(isotropic(E, NU, t, RHO))
    m.shells = [(j * npr + i, j * npr + (i + 1) % npr, (j + 1) * npr + (i + 1) % npr, (j + 1) * npr + i, sec, None)
                for j in range(ny) for i in range(npr)]
    for i in range(npr):
        m.fixed[i] = range(6)
    tip = [len(ys) * npr - npr + i for i in range(npr)]
    iR = next(i for i, (x, z) in enumerate(per) if abs(x - w / 2) < 1e-9 and abs(z) < 1e-9)
    iL = next(i for i, (x, z) in enumerate(per) if abs(x + w / 2) < 1e-9 and abs(z) < 1e-9)
    m.loads = {tip[iR]: [0, 0, P / 2, 0, 0, 0], tip[iL]: [0, 0, P / 2, 0, 0, 0]}
    U = m.solve_static()["u"].reshape(-1, 6)
    I = 2 * w * t * (h / 2) ** 2 + 2 * t * h ** 3 / 12
    y = np.linspace(0.0, L, 41)
    beam = cantilever_response(y, P * (L - y), np.zeros_like(y), E * I, 1.0)
    assert beam["deflection_m"][-1] == pytest.approx(float(U[tip[iR], 2]), rel=0.30)

    m.loads = {}
    q = Tq / (2 * w * h)
    for i in range(npr):
        a = np.array(per[i])
        b = np.array(per[(i + 1) % npr])
        f = q * (b - a)
        for n in (tip[i], tip[(i + 1) % npr]):
            m.loads.setdefault(n, np.zeros(6))
            m.loads[n][[0, 2]] += f / 2
    U = m.solve_static()["u"].reshape(-1, 6)
    # Right-hand rotation about the span axis (+y): u_z = −θ x, so θ = (u_z,left − u_z,right) / width.
    twist_fem = (U[tip[iL], 2] - U[tip[iR], 2]) / w
    GJ = float(bredt_gj(w, h, t, t, t, G))
    beam_t = cantilever_response(y, np.zeros_like(y), np.full_like(y, Tq), 1.0, GJ)
    assert beam_t["twist_rad"][-1] == pytest.approx(float(twist_fem), rel=0.30)


def test_avl_section_incidence_follows_wing_twist(tmp_path):
    from acdt.domains.aircraft.aero.avl import write_avl_file

    cfg = _ga()
    p = write_avl_file(cfg, tmp_path / "rigid.avl")
    rigid = p.read_text(encoding="utf-8")
    assert "SURFACE\nWing\n" in rigid

    def twist(y):
        return 0.25 * y          # deg, nose up

    p2 = write_avl_file(cfg, tmp_path / "flex.avl", wing_twist_deg=twist)
    text = p2.read_text(encoding="utf-8")
    wing = text.split("SURFACE\nHtail")[0]
    aincs = []
    lines = wing.splitlines()
    for i, ln in enumerate(lines):
        if ln == "SECTION" and i + 1 < len(lines):
            aincs.append(float(lines[i + 1].split()[-1]))
    b2 = cfg.wing.span / 2
    ya = 0.65 * b2                 # default aileron break: outer 35 %
    assert aincs[0] == pytest.approx(twist(0.0), abs=1e-4)
    assert aincs[1] == pytest.approx(twist(ya), abs=1e-3)
    assert aincs[2] == pytest.approx(twist(b2), abs=1e-3)
    # The rigid file keeps a zero incidence on every wing section.
    rigid_wing = rigid.split("SURFACE\nHtail")[0]
    for i, ln in enumerate(rigid_wing.splitlines()):
        if ln == "SECTION":
            assert float(rigid_wing.splitlines()[i + 1].split()[-1]) == 0.0


def test_neutral_point_accepts_elastic_wing_ac():
    from acdt.domains.aircraft.stability import neutral_point

    cfg = _ga()
    a = neutral_point(cfg, {"CLa_w": 4.5})
    b = neutral_point(cfg, {"CLa_w": 5.0, "xac_w": 0.32})
    assert b["xbar_np"] > a["xbar_np"]
    assert b["CLa_w"] == pytest.approx(5.0)


@pytest.mark.slow
def test_size_cycle_flex_converges_and_json_fields():
    from pathlib import Path
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.report import to_dict
    from acdt.domains.aircraft.sizing import run

    spec = MissionSpec.from_yaml(Path(__file__).parents[1] / "examples" / "cessna172_check.yaml")
    spec.assumptions["aero"]["fidelity"] = "handbook"
    spec.assumptions["structures"]["flex"] = True
    spec.assumptions["structures"]["mass_in_loop"] = True
    res = run(spec)
    assert res.converged
    h = res.history
    assert abs(h[-1]["W0"] / h[-2]["W0"] - 1) < 0.001
    assert abs(h[-1]["torção ponta [deg]"] - h[-2]["torção ponta [deg]"]) < 0.02
    el = res.structures_l1.elastic
    assert el.applied and el.K_ratio > 1.0
    d = to_dict(res)
    assert "masses" in d["structures"] and "deflections" in d["structures"]
    assert d["aero"]["elastic_correction"]["applied"] is True
    assert 0.75 <= d["structures"]["masses"]["fuselage_over_raymer"] <= 1.25
