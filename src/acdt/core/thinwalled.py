"""Thin-walled (idealised) multi-cell beam sections — Megson, *Aircraft Structures for Engineering Students*,
4th–6th ed.: structural idealisation (Ch. 20/"Structural idealization": booms carry direct stress, walls carry
constant shear flow; wall direct-stress capacity lumped into the adjacent booms with B = t_D b/6 (2 + σ₂/σ₁),
Megson Eq. 20.1), unsymmetric bending (Eq. 16.18), shear of open and closed multi-cell sections (Eq. 20.6 with the
cell closure q_s,0 from zero twist — shear centre), torsion of multi-cell sections (Ch. 18, equal twist rate in
every cell, Bredt–Batho). St Venant contribution Σ G b t³/3 of every wall added to GJ (open parts).

Conventions: section plane (x, z), x aft, z up, beam axis y. Moments about y are positive nose-up:
M = z f_x − x f_z. Modulus-weighted areas (booms carry E_b/E_ref), shear-modulus-weighted walls (G_w/G_ref).

The solver is generic (any planar graph of walls; cells listed explicitly) so it also serves other domains
(hull girders, chassis rails)."""
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

    # -------------------------------------------------------------- wall arrays (vectorised)
    def _wall_arrays(self):
        """Wall table as arrays (i, j, t, G_ratio, E_ratio, direct, length) — built once per section."""
        Wa = np.asarray([w[:6] for w in self.walls], float).reshape(-1, 6)
        I, J = Wa[:, 0].astype(int), Wa[:, 1].astype(int)
        T, Gr, Er, D = Wa[:, 2], Wa[:, 3], Wa[:, 4], Wa[:, 5] != 0
        dP = self.pts[J] - self.pts[I]
        L = np.hypot(dP[:, 0], dP[:, 1])
        return I, J, T, Gr, Er, D, L

    # -------------------------------------------------------------- idealisation
    def idealise(self, n_iter: int = 4):
        """Boom areas B_r = concentrated area + Σ walls t b/6 (2 + z₂'/z₁') (pure vertical bending, Megson Eq.
        20.1), iterated on the centroid; ratio guarded (|z₁'| small → t b/2)."""
        P = np.asarray(self.pts, float)
        B0 = np.asarray(self.boom_area, float).copy()
        zc = float(np.average(P[:, 1], weights=B0 + 1e-12)) if B0.sum() > 0 else float(P[:, 1].mean())
        xc = float(P[:, 0].mean())
        I, J, T, _g, Er, D, L = self._wall_arrays()
        # both ends of every direct-stress wall: (a = boom receiving area, c = the other end)
        a = np.concatenate((I[D], J[D]))
        c = np.concatenate((J[D], I[D]))
        etb = np.tile(Er[D] * T[D] * L[D], 2)
        hz = np.ptp(P[:, 1]) or 1.0
        B = B0
        for _ in range(n_iter):
            z1, z2 = P[a, 1] - zc, P[c, 1] - zc
            big = np.abs(z1) > 0.02 * hz
            ratio = np.divide(z2, z1, out=np.zeros_like(z1), where=big)
            add = np.where(big, etb / 6 * (2 + ratio), etb / 2 * 0.5)
            B = B0 + np.bincount(a, weights=add, minlength=len(B0))
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
        P = np.asarray(self.pts, float)
        n, ne = len(P), len(self.walls)
        I, J, T, Gr, _e, _d, L = self._wall_arrays()
        k = np.arange(ne)
        Aeq = np.zeros((n + len(self.cells), ne))
        np.add.at(Aeq, (I, k), 1.0)       # leaves i
        np.add.at(Aeq, (J, k), -1.0)      # enters j
        mom = P[I, 1] * P[J, 0] - P[I, 0] * P[J, 1]      # _m(P[i], P[j]) per wall; _m(rj, ri) = −_m(ri, rj)
        self.cell_area = []
        for c, cell in enumerate(self.cells):
            s = np.asarray(cell, int)
            kk, sg = np.abs(s) - 1, np.sign(s).astype(float)
            np.add.at(Aeq[n + c], kk, sg * L[kk] / (T[kk] * Gr[kk]))
            area = float(0.5 * (sg * mom[kk]).sum())
            if area < 0:          # orient the loop nose-up positive
                Aeq[n + c] *= -1
                self.cells[c] = [-s_ for s_ in cell]
                area = -area
            self.cell_area.append(area)
        self.cell_area = np.array(self.cell_area)
        self._Aeq = Aeq
        self._mom = mom
        self._L = L
        return Aeq

    def solve(self):
        """Idealise, then unit-load shear flows: q_Sz (S_z = 1 N through the shear centre), q_Sx, and
        q_T (unit twist rate θ' = 1 rad/m × G_ref) — returns self with x_sc, z_sc, GJ, EI.

        Linear system: node equilibrium (one row per node, one redundant) + one compatibility row per cell. When the
        cells close every independent loop (n_cells = n_walls − n_nodes + 1) dropping one node row leaves a square
        system solved directly (LU); otherwise least squares, as before. Same solution to round-off."""
        if not hasattr(self, "B"):
            self.idealise()
        P = np.asarray(self.pts, float)
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
        sol = None
        if Aeq.shape[0] == Aeq.shape[1] + 1 and n > 0:
            try:
                sol = np.linalg.solve(Aeq[1:], rhs[1:])
            except np.linalg.LinAlgError:
                sol = None
            # the dropped node row must hold (consistent loads); else fall back to least squares
            if sol is not None and np.abs(Aeq[0] @ sol - rhs[0]).max() > 1e-9 * (np.abs(rhs).max() or 1.0):
                sol = None
        if sol is None:
            sol, *_ = np.linalg.lstsq(Aeq, rhs, rcond=None)
        self.q_Sz, self.q_Sx, self.q_T = sol[:, 0], sol[:, 1], sol[:, 2]
        self.x_sc = -float(self._mom @ self.q_Sz)               # S_z = 1 at x_sc: M = −x_sc
        self.z_sc = float(self._mom @ self.q_Sx)                # S_x = 1 at z_sc: M = +z_sc
        _i, _j, T, Gr, *_r = self._wall_arrays()
        sv = float((Gr * self.G_ref * self._L * T**3 / 3).sum())
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
