"""Megson thin-walled idealised sections: Bredt torsion, multi-cell torsion, channel shear centre, box inertia."""
import numpy as np
import pytest

from acdt.core.thinwalled import ThinWalledSection


def _rect(w, h, ts, n=8, B=0.0):
    corners = [(0, h / 2), (w, h / 2), (w, -h / 2), (0, -h / 2)]
    loop, tl = [], []
    for k in range(4):
        p0, p1 = np.array(corners[k]), np.array(corners[(k + 1) % 4])
        for i in range(n):
            loop.append(p0 + (p1 - p0) * i / n)
            tl.append(ts[k])
    N = len(loop)
    ba = np.zeros(N)
    ba[::n] = B
    walls = [(i, (i + 1) % N, tl[i], 1.0, 1.0, True) for i in range(N)]
    return ThinWalledSection(np.array(loop), ba, walls, [[k + 1 for k in range(N)]], 70e9, 27e9).solve()


def test_single_cell_bredt_and_inertia():
    w, h, t = 0.4, 0.1, 0.002
    s = _rect(w, h, [t] * 4)
    assert s.GJ == pytest.approx(4 * (w * h) ** 2 * 27e9 / (2 * (w + h) / t), rel=1e-3)
    assert s.Ixx == pytest.approx(2 * w * t * (h / 2) ** 2 + 2 * t * h**3 / 12, rel=1e-6)
    assert s.x_sc == pytest.approx(w / 2, abs=1e-9)
    s2 = _rect(w, h, [t, t, t, 2 * t], n=20, B=1e-4)       # thicker front web → SC moves forward
    assert s2.x_sc < w / 2 and abs(s2.z_sc) < 1e-9


def test_open_channel_shear_centre():
    h, b, tf, tw, n = 0.2, 0.08, 0.003, 0.002, 40
    pts = ([(b - b * i / n, h / 2) for i in range(n)] + [(0, h / 2 - h * i / n) for i in range(n)]
           + [(b * i / n, -h / 2) for i in range(n + 1)])
    ts = [tf] * n + [tw] * n + [tf] * n
    walls = [(i, i + 1, ts[i], 1.0, 1.0, True) for i in range(len(pts) - 1)]
    s = ThinWalledSection(np.array(pts), np.zeros(len(pts)), walls, [], 70e9, 27e9).solve()
    assert s.x_sc == pytest.approx(-3 * b**2 * tf / (6 * b * tf + h * tw), rel=1e-3)


def test_two_cell_torsion():
    # two cells side by side sharing the middle web; closed form (Megson Ch. 18): solve 3x3 directly
    w1, w2, h, t, tm, G = 0.3, 0.2, 0.1, 0.002, 0.003, 27e9
    P = np.array([(0, h / 2), (w1, h / 2), (w1 + w2, h / 2), (w1 + w2, -h / 2), (w1, -h / 2), (0, -h / 2)])
    walls = [(0, 1, t, 1, 1, True), (1, 2, t, 1, 1, True), (2, 3, t, 1, 1, True), (3, 4, t, 1, 1, True),
             (4, 5, t, 1, 1, True), (5, 0, t, 1, 1, True), (1, 4, tm, 1, 1, True)]
    cells = [[1, 7, 5, 6], [2, 3, 4, -7]]
    s = ThinWalledSection(P, np.zeros(6), walls, cells, 70e9, G).solve()
    A1, A2 = w1 * h, w2 * h
    d1, d2, d12 = (2 * w1 + h) / t, (2 * w2 + h) / t, h / tm
    # q1 (d1+d12) - q2 d12 = 2 A1 G θ', q2 (d2+d12) - q1 d12 = 2 A2 G θ'
    M = np.array([[d1 + d12, -d12], [-d12, d2 + d12]])
    q = np.linalg.solve(M, [2 * A1 * G, 2 * A2 * G])
    sv = sum(G * np.hypot(*(P[j] - P[i])) * tt**3 / 3 for (i, j, tt, *_r) in walls)
    assert s.GJ == pytest.approx(2 * A1 * q[0] + 2 * A2 * q[1] + sv, rel=1e-9)
