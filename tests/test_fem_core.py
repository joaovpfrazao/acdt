"""Phase 5 FE core verification against closed-form solutions (Timoshenko & Gere; Roark; Bredt)."""
import math

import numpy as np
import pytest

from acdt.core.fem import FEModel, isotropic

E, NU, RHO = 70e9, 0.3, 2700.0
G = E / 2 / (1 + NU)


def _plate(L, b, nx, ny, t):
    idx, nodes = {}, []
    for i, x in enumerate(np.linspace(0, L, nx + 1)):
        for j, y in enumerate(np.linspace(0, b, ny + 1)):
            idx[i, j] = len(nodes)
            nodes.append((x, y, 0.0))
    m = FEModel(np.array(nodes))
    s = m.add_section(isotropic(E, NU, t, RHO))
    m.shells = [(idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1], s, None)
                for i in range(nx) for j in range(ny)]
    return m, idx


def test_cantilever_plate_bending_and_membrane():
    L, b, t, P = 1.0, 0.1, 0.01, 100.0
    m, idx = _plate(L, b, 20, 2, t)
    for j in range(3):
        m.fixed[idx[0, j]] = range(6)
        m.loads[idx[20, j]] = [0, 0, P / 3, 0, 0, 0]
    w = m.solve_static()["u"][6 * idx[20, 1] + 2]
    assert w == pytest.approx(P * L**3 / (3 * E * b * t**3 / 12), rel=0.02)
    m, idx = _plate(L, b, 10, 2, t)
    for j in range(3):
        m.fixed[idx[0, j]] = range(6)
        m.loads[idx[10, j]] = [0, P / 3, 0, 0, 0, 0]
    v = m.solve_static()["u"][6 * idx[10, 1] + 1]
    ref = P * L**3 / (3 * E * t * b**3 / 12) + P * L / (5 / 6 * G * b * t)
    assert v == pytest.approx(ref, rel=0.02)


def test_ss_plate_buckling_k4():
    a, t, n, Nx = 0.5, 0.01, 12, 1000.0
    m, idx = _plate(a, a, n, n, t)
    for (i, j), k in idx.items():
        m.fixed[k] = ([2] if i in (0, n) or j in (0, n) else []) + [5]
    m.fixed[idx[0, 0]] = [0, 1, 2, 5]
    m.fixed[idx[0, n]] = [0, 2, 5]
    for j in range(n + 1):
        wgt = (0.5 if j in (0, n) else 1) * a / n
        m.loads[idx[n, j]] = [-Nx * wgt, 0, 0, 0, 0, 0]
        m.loads[idx[0, j]] = [Nx * wgt, 0, 0, 0, 0, 0]
    bk = m.buckling(m.solve_static(), 3)
    D = E * t**3 / 12 / (1 - NU**2)
    assert bk["lambda"][0] * Nx == pytest.approx(4 * math.pi**2 * D / a**2, rel=0.02)


def test_cantilever_plate_frequency():
    L, b, t = 1.0, 0.1, 0.01
    m, idx = _plate(L, b, 20, 2, t)
    for j in range(3):
        m.fixed[idx[0, j]] = range(6)
    f = m.modal(2)["f_Hz"][0]
    ref = 1.8751**2 / (2 * math.pi) * math.sqrt(E * b * t**3 / 12 / (RHO * b * t * L**4))
    assert f == pytest.approx(ref, rel=0.02)


def _box(L=2.0, w=0.4, h=0.1, t=0.002, ny=40, nw=8, nh=4):
    per = ([(-w / 2 + w * i / nw, h / 2) for i in range(nw)] + [(w / 2, h / 2 - h * i / nh) for i in range(nh)]
           + [(w / 2 - w * i / nw, -h / 2) for i in range(nw)] + [(-w / 2, -h / 2 + h * i / nh) for i in range(nh)])
    ys = np.linspace(0, L, ny + 1)
    nodes = [(x, y, z) for y in ys for (x, z) in per]
    npr = len(per)
    m = FEModel(np.array(nodes, float))
    s = m.add_section(isotropic(E, NU, t, RHO))
    m.shells = [(j * npr + i, j * npr + (i + 1) % npr, (j + 1) * npr + (i + 1) % npr, (j + 1) * npr + i, s, None)
                for j in range(ny) for i in range(npr)]
    for i in range(npr):
        m.fixed[i] = range(6)
    return m, per, ys, npr


def test_box_torsion_rate_matches_bredt_and_bending_beam():
    w, h, t, T = 0.4, 0.1, 0.002, 1000.0
    m, per, ys, npr = _box()
    tip = [len(ys) * npr - npr + i for i in range(npr)]
    q = T / (2 * w * h)
    for i in range(npr):
        a, b = np.array(per[i]), np.array(per[(i + 1) % npr])
        f = q * (b - a)
        for n in (tip[i], tip[(i + 1) % npr]):
            m.loads.setdefault(n, np.zeros(6))[[0, 2]] += f / 2
    U = m.solve_static()["u"].reshape(-1, 6)
    iR = next(i for i, (x, z) in enumerate(per) if abs(x - w / 2) < 1e-9 and abs(z) < 1e-9)
    iL = next(i for i, (x, z) in enumerate(per) if abs(x + w / 2) < 1e-9 and abs(z) < 1e-9)
    tw = lambda j: (U[j * npr + iR, 2] - U[j * npr + iL, 2]) / w   # noqa: E731
    J = 4 * (w * h) ** 2 / (2 * w / t + 2 * h / t)
    assert abs((tw(30) - tw(20)) / (ys[30] - ys[20])) == pytest.approx(T / (G * J), rel=0.03)
    m.loads = {tip[iR]: [0, 0, 500.0, 0, 0, 0], tip[iL]: [0, 0, 500.0, 0, 0, 0]}
    U = m.solve_static()["u"].reshape(-1, 6)
    I = 2 * w * t * (h / 2) ** 2 + 2 * t * h**3 / 12
    ref = 1000 * 2.0**3 / (3 * E * I) + 1000 * 2.0 / (G * 2 * h * t)
    assert U[tip[iR], 2] == pytest.approx(ref, rel=0.03)


def test_beam_element_cantilever_and_offset():
    """Euler–Bernoulli cantilever (local z = zref ↔ Iy) and a rigid-offset beam under an eccentric axial load:
    w_tip = P e L² / (2 E I) (Przemieniecki offset transformation)."""
    e = 0.05
    for off in (None, (0, 0, e)):
        m = FEModel(np.array([(0, i * 0.1, 0) for i in range(11)], float))
        pid = m.add_beam_prop(E=E, G=G, A=1e-4, Iy=2e-9, Iz=3e-9, J=1e-9, rho=RHO)
        m.beams = [(i, i + 1, pid, off, off, (0, 0, 1)) for i in range(10)]
        m.fixed[0] = range(6)
        m.loads[10] = [0, 0, 10.0, 0, 0, 0] if off is None else [0, 100.0, 0, 0, 0, 0]
        u = m.solve_static()["u"].reshape(-1, 6)
        ref = 10 / (3 * E * 2e-9) if off is None else 100.0 * e / (2 * E * 2e-9)
        assert abs(u[10, 2]) == pytest.approx(ref, rel=0.01)


def test_sandwich_plate_buckling_with_core_shear():
    """Hard simply-supported square sandwich plate: N_cr = N_E / (1 + N_E/(2S)), S = G_c d²/t_c
    (Mindlin plate, m = n = 1; Allen, *Analysis and Design of Structural Sandwich Panels*, 1969)."""
    from acdt.core.fem.laminate import sandwich
    tf, tc, Ef, Gc, a, n, Nx = 0.25e-3, 2e-3, 60e9, 30e6, 0.168, 16, 1000.0
    m, idx = _plate(a, a, n, n, tf)
    sec = sandwich(Ef, 0.3, tf, 70e6, Gc, tc, 1550.0, 75.0)
    m.sections[0] = sec
    for (i, j), k in idx.items():
        m.fixed[k] = ([2] if i in (0, n) or j in (0, n) else []) + ([3] if i in (0, n) else []) + \
            ([4] if j in (0, n) else []) + [5]
    m.fixed[idx[0, 0]] = range(6)
    m.fixed[idx[0, n]] = [0, 2, 3, 4, 5]
    for j in range(n + 1):
        wgt = (0.5 if j in (0, n) else 1) * a / n
        m.loads[idx[n, j]] = [-Nx * wgt, 0, 0, 0, 0, 0]
        m.loads[idx[0, j]] = [Nx * wgt, 0, 0, 0, 0, 0]
    lam = m.buckling(m.solve_static(), 2)["lambda"][0]
    NE = 4 * math.pi**2 * sec.D[0, 0] / a**2
    S = Gc * (tc + tf) ** 2 / tc
    assert sec.As[0, 0] == pytest.approx(S)
    assert lam * Nx == pytest.approx(NE / (1 + NE / (2 * S)), rel=0.02)
