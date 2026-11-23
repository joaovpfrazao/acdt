# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Referência congelada de `acdt.core.thinwalled` antes da vectorização (main 6af9b3e, 23 nov 2026).

Só para o teste de regressão `tests/test_thinwalled_regression.py`: a implementação nova tem de dar os mesmos
resultados (até ao arredondamento). Não usar no código de produção."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def _m(ri, rj):
    """Moment about the y axis (nose-up +) of a unit shear flow along the straight wall i → j."""
    return ri[1] * rj[0] - ri[0] * rj[1]


@dataclass
class ThinWalledSection:
    pts: np.ndarray                    # (n, 2) node coordinates (x, z) [m]
    boom_area: np.ndarray              # (n,) concentrated (stringer/cap) areas, already E-weighted [m²]
    walls: list                        # [(i, j, t, G_ratio, E_ratio, direct)] — 'direct': wall carries σ (skins/webs)
    cells: list = field(default_factory=list)   # [[wall indices traversed i→j (+) or j→i (−) as ±(k+1)]]
    E_ref: float = 70e9
    G_ref: float = 27e9
    rho_wall: list | None = None       # per-wall density (mass), optional
    rho_boom: np.ndarray | None = None

    # -------------------------------------------------------------- idealisation
    def idealise(self, n_iter: int = 4):
        """Boom areas B_r = concentrated area + Σ walls t b/6 (2 + z₂'/z₁') (pure vertical bending, Megson Eq.
        20.1), iterated on the centroid; ratio guarded (|z₁'| small → t b/2)."""
        P = self.pts
        B0 = np.asarray(self.boom_area, float).copy()
        zc = float(np.average(P[:, 1], weights=B0 + 1e-12)) if B0.sum() > 0 else float(P[:, 1].mean())
        xc = float(P[:, 0].mean())
        for _ in range(n_iter):
            B = B0.copy()
            hz = np.ptp(P[:, 1]) or 1.0
            for (i, j, t, _g, e, direct) in self.walls:
                if not direct:
                    continue
                b = float(np.hypot(*(P[j] - P[i])))
                for a, c in ((i, j), (j, i)):
                    z1, z2 = P[a, 1] - zc, P[c, 1] - zc
                    if abs(z1) > 0.02 * hz:
                        B[a] += e * t * b / 6 * (2 + z2 / z1)
                    else:
                        B[a] += e * t * b / 2 * 0.5
            A = B.sum()
            xc, zc = float((B * P[:, 0]).sum() / A), float((B * P[:, 1]).sum() / A)
        self.B, self.xc, self.zc = B, xc, zc
        d = P - [xc, zc]
        self.Ixx = float((B * d[:, 1] ** 2).sum())   # about the horizontal centroidal axis (flap bending)
        self.Izz = float((B * d[:, 0] ** 2).sum())   # about the vertical axis (chordwise bending)
        self.Ixz = float((B * d[:, 0] * d[:, 1]).sum())
        return self

    # -------------------------------------------------------------- shear-flow system
    def _system(self):
        P, W = self.pts, self.walls
        n, ne = len(P), len(W)
        Aeq = np.zeros((n + len(self.cells), ne))
        for k, (i, j, *_r) in enumerate(W):
            Aeq[i, k] += 1.0      # leaves i
            Aeq[j, k] -= 1.0      # enters j
        self.cell_area = []
        for c, cell in enumerate(self.cells):
            area = 0.0
            for s in cell:
                k, sg = abs(s) - 1, np.sign(s)
                i, j, t, g, *_r = W[k]
                L = float(np.hypot(*(P[j] - P[i])))
                Aeq[n + c, k] += sg * L / (t * g)
                ri, rj = (P[i], P[j]) if sg > 0 else (P[j], P[i])
                area += 0.5 * _m(ri, rj)
            if area < 0:          # orient the loop nose-up positive
                Aeq[n + c] *= -1
                self.cells[c] = [-s for s in cell]
                area = -area
            self.cell_area.append(area)
        self.cell_area = np.array(self.cell_area)
        self._Aeq = Aeq
        self._mom = np.array([_m(P[i], P[j]) for (i, j, *_r) in W])
        return Aeq

    def solve(self):
        """Idealise, then unit-load shear flows: q_Sz (S_z = 1 N through the shear centre), q_Sx, and
        q_T (unit twist rate θ' = 1 rad/m × G_ref) — returns self with x_sc, z_sc, GJ, EI."""
        if not hasattr(self, "B"):
            self.idealise()
        P = self.pts
        n = len(P)
        Aeq = self._system()
        d = P - [self.xc, self.zc]
        det = self.Ixx * self.Izz - self.Ixz**2
        rhs = np.zeros((Aeq.shape[0], 3))
        for col, (Sx, Sz) in enumerate(((0.0, 1.0), (1.0, 0.0))):
            cx = (Sx * self.Ixx - Sz * self.Ixz) / det
            cz = (Sz * self.Izz - Sx * self.Ixz) / det
            rhs[:n, col] = -self.B * (cx * d[:, 0] + cz * d[:, 1])
        rhs[n:, 2] = 2 * self.cell_area * self.G_ref            # Σ q ds/(G t) = 2 A θ'  (θ' = 1)
        sol, *_ = np.linalg.lstsq(Aeq, rhs, rcond=None)
        self.q_Sz, self.q_Sx, self.q_T = sol[:, 0], sol[:, 1], sol[:, 2]
        self.x_sc = -float(self._mom @ self.q_Sz)               # S_z = 1 at x_sc: M = −x_sc
        self.z_sc = float(self._mom @ self.q_Sx)                # S_x = 1 at z_sc: M = +z_sc
        sv = sum(g * self.G_ref * float(np.hypot(*(P[j] - P[i]))) * t**3 / 3 for (i, j, t, g, *_r) in self.walls)
        self.GJ = float(self._mom @ self.q_T) + sv
        self.EIxx, self.EIzz, self.EIxz = self.E_ref * self.Ixx, self.E_ref * self.Izz, self.E_ref * self.Ixz
        return self

    # -------------------------------------------------------------- stresses
    def boom_stress(self, M_flap: float, M_chord: float = 0.0) -> np.ndarray:
        """Direct stress in the booms [Pa, reference modulus]: M_flap > 0 bends the tip up (upper side in
        compression), M_chord > 0 bends the tip aft (front side in compression). Megson Eq. 16.18."""
        d = self.pts - [self.xc, self.zc]
        det = self.Ixx * self.Izz - self.Ixz**2
        Mx, My = -M_flap, -M_chord
        return (My * self.Ixx - Mx * self.Ixz) / det * d[:, 0] + (Mx * self.Izz - My * self.Ixz) / det * d[:, 1]

    def shear_flows(self, Sz: float, x_load: float, T_noseup: float = 0.0, Sx: float = 0.0) -> np.ndarray:
        """Wall shear flows [N/m] for a vertical shear Sz acting at x = x_load plus an applied nose-up torque
        T (about the y axis through the origin), i.e. Sz through the shear centre + torque about it."""
        T_sc = T_noseup - Sz * (x_load - self.x_sc)
        return Sz * self.q_Sz + Sx * self.q_Sx + T_sc / self.GJ * self.q_T

    def wall_lengths(self) -> np.ndarray:
        P = self.pts
        return np.array([float(np.hypot(*(P[j] - P[i]))) for (i, j, *_r) in self.walls])
