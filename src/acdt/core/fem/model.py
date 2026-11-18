"""Sparse FE model: flat shells (QM6 + MITC4), offset beams, bars; static, linear buckling and modal analysis."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from .solvers import Factor

from .laminate import ShellSection

_G = 1 / math.sqrt(3)
_GP = np.array([[-_G, -_G], [_G, -_G], [_G, _G], [-_G, _G]])
_XI = np.array([-1.0, 1.0, 1.0, -1.0])
_ETA = np.array([-1.0, -1.0, 1.0, 1.0])


def _shape(xi, eta):
    N = 0.25 * (1 + xi * _XI) * (1 + eta * _ETA)
    dN = np.array([0.25 * _XI * (1 + eta * _ETA), 0.25 * _ETA * (1 + xi * _XI)])  # (2,4): d/dxi, d/deta
    return N, dN


@dataclass
class FEModel:
    """Container: nodes (N×3), shells (quads, CCW about their outward normal is not required), beams, bars,
    point masses, boundary conditions and nodal loads. Units SI."""
    nodes: np.ndarray
    shells: list = field(default_factory=list)       # (n1,n2,n3,n4, section_id, ref_dir or None)
    sections: list = field(default_factory=list)     # ShellSection
    beams: list = field(default_factory=list)        # (n1, n2, beam_prop_id, offset1(3), offset2(3), zref(3))
    beam_props: list = field(default_factory=list)   # dict(E, G, A, Iy, Iz, J, rho)
    bars: list = field(default_factory=list)         # (n1, n2, EA, rho_A)
    point_masses: dict = field(default_factory=dict)  # node -> mass [kg]
    fixed: dict = field(default_factory=dict)        # node -> iterable of dof indices (0..5)
    loads: dict = field(default_factory=dict)        # node -> 6-vector
    drill: float = 1e-3

    # ------------------------------------------------------------------ bookkeeping
    @property
    def ndof(self) -> int:
        return 6 * len(self.nodes)

    def add_section(self, s: ShellSection) -> int:
        self.sections.append(s)
        return len(self.sections) - 1

    def add_beam_prop(self, **p) -> int:
        self.beam_props.append(p)
        return len(self.beam_props) - 1

    def free_dofs(self) -> np.ndarray:
        mask = np.ones(self.ndof, bool)
        for n, ds in self.fixed.items():
            for d in ds:
                mask[6 * n + d] = False
        # nodes with no element: fix
        used = np.zeros(len(self.nodes), bool)
        for e in self.shells:
            used[list(e[:4])] = True
        for b in self.beams:
            used[[b[0], b[1]]] = True
        for b in self.bars:
            used[[b[0], b[1]]] = True
        for n in np.where(~used)[0]:
            mask[6 * n:6 * n + 6] = False
        return np.where(mask)[0]

    def load_vector(self) -> np.ndarray:
        F = np.zeros(self.ndof)
        for n, f in self.loads.items():
            F[6 * n:6 * n + 6] += np.asarray(f, float)
        return F

    # ------------------------------------------------------------------ shell kinematics (vectorised)
    def _shell_geometry(self):
        E = np.array([e[:4] for e in self.shells], int)
        X = self.nodes[E]                                      # (ne,4,3)
        c = X.mean(axis=1)
        n = np.cross(X[:, 2] - X[:, 0], X[:, 3] - X[:, 1])
        n /= np.linalg.norm(n, axis=1)[:, None]
        e1 = 0.5 * (X[:, 1] + X[:, 2]) - 0.5 * (X[:, 0] + X[:, 3])
        e1 -= (e1 * n).sum(1)[:, None] * n
        e1 /= np.linalg.norm(e1, axis=1)[:, None]
        e2 = np.cross(n, e1)
        R = np.stack([e1, e2, n], axis=1)                       # rows = local axes
        xy = np.einsum("eij,ekj->eki", R[:, :2, :], X - c[:, None, :])
        return E, R, xy

    def _section_mats(self, R):
        ne = len(self.shells)
        A = np.zeros((ne, 3, 3))
        D = np.zeros((ne, 3, 3))
        As = np.zeros((ne, 2, 2))
        rhoA = np.zeros(ne)
        cache = {}
        for k, e in enumerate(self.shells):
            sid, ref = e[4], e[5] if len(e) > 5 else None
            th = 0.0
            if ref is not None:
                r = np.asarray(ref, float)
                r = r - (r @ R[k, 2]) * R[k, 2]
                th = math.atan2(r @ R[k, 1], r @ R[k, 0])     # material 1-axis angle in element axes
            key = (sid, round(th, 9))
            if key not in cache:
                cache[key] = self.sections[sid].rotated(th)
            s = cache[key]
            A[k], D[k], As[k], rhoA[k] = s.A, s.D, s.As, s.rho_A
        return A, D, As, rhoA

    def _shell_local(self, want_K=True):
        """Local 24×24 stiffness of every shell + data for stress recovery."""
        E, R, xy = self._shell_geometry()
        ne = len(E)
        Am, Db, As, rhoA = self._section_mats(R)
        N0, dN0 = _shape(0.0, 0.0)
        J0 = np.einsum("ij,ejk->eik", dN0, xy)                 # (ne,2,2)
        detJ0 = np.linalg.det(J0)
        iJ0 = np.linalg.inv(J0)
        Kcc = np.zeros((ne, 8, 8))
        Kci = np.zeros((ne, 8, 4))
        Kii = np.zeros((ne, 4, 4))
        Kb = np.zeros((ne, 12, 12))
        area = np.zeros(ne)
        # MITC4 tying points: gamma_xi at B(0,-1), D(0,1); gamma_eta at A(-1,0), C(1,0)
        tie = {}
        for nm, (a, b) in {"B": (0, -1), "D": (0, 1), "A": (-1, 0), "C": (1, 0)}.items():
            Nt, dNt = _shape(a, b)
            Jt = np.einsum("ij,ejk->eik", dNt, xy)            # rows: d/dxi (x,y), d/deta (x,y)
            row = 0 if nm in "BD" else 1
            g = np.zeros((ne, 12))
            g[:, 0::3] = dNt[row][None, :]
            g[:, 1::3] = -Nt[None, :] * Jt[:, row, 1][:, None]
            g[:, 2::3] = Nt[None, :] * Jt[:, row, 0][:, None]
            tie[nm] = g
        for (xi, eta) in _GP:
            N, dN = _shape(xi, eta)
            J = np.einsum("ij,ejk->eik", dN, xy)
            detJ = np.linalg.det(J)
            iJ = np.linalg.inv(J)
            dNx = np.einsum("eij,jk->eik", iJ, dN)            # (ne,2,4)
            area += detJ
            Bm = np.zeros((ne, 3, 8))
            Bm[:, 0, 0::2] = dNx[:, 0]
            Bm[:, 1, 1::2] = dNx[:, 1]
            Bm[:, 2, 0::2] = dNx[:, 1]
            Bm[:, 2, 1::2] = dNx[:, 0]
            dP = np.zeros((ne, 2, 2))                         # natural derivatives of P1 = 1-xi², P2 = 1-eta²
            nat = np.array([[-2 * xi, 0.0], [0.0, -2 * eta]])  # rows d/dxi, d/deta ; cols P1, P2
            dP = np.einsum("eij,jk->eik", iJ0, nat) * (detJ0 / detJ)[:, None, None]   # (ne, x/y, P1/P2)
            Bi = np.zeros((ne, 3, 4))
            Bi[:, 0, 0:2] = dP[:, 0]
            Bi[:, 1, 2:4] = dP[:, 1]
            Bi[:, 2, 0:2] = dP[:, 1]
            Bi[:, 2, 2:4] = dP[:, 0]
            w = detJ[:, None, None]
            Kcc += np.einsum("eki,ekl,elj->eij", Bm, Am, Bm) * w
            Kci += np.einsum("eki,ekl,elj->eij", Bm, Am, Bi) * w
            Kii += np.einsum("eki,ekl,elj->eij", Bi, Am, Bi) * w
            Bb = np.zeros((ne, 3, 12))
            Bb[:, 0, 2::3] = dNx[:, 0]
            Bb[:, 1, 1::3] = -dNx[:, 1]
            Bb[:, 2, 1::3] = -dNx[:, 0]
            Bb[:, 2, 2::3] = dNx[:, 1]
            Kb += np.einsum("eki,ekl,elj->eij", Bb, Db, Bb) * w
            gxi = 0.5 * (1 - eta) * tie["B"] + 0.5 * (1 + eta) * tie["D"]
            geta = 0.5 * (1 - xi) * tie["A"] + 0.5 * (1 + xi) * tie["C"]
            Bs = np.einsum("eij,ejk->eik", iJ, np.stack([gxi, geta], axis=1))
            Kb += np.einsum("eki,ekl,elj->eij", Bs, As, Bs) * w
        cond = np.linalg.solve(Kii, np.transpose(Kci, (0, 2, 1)))   # Kii^-1 Kic  (ne,4,8)
        Km = Kcc - np.einsum("eij,ejk->eik", Kci, cond)
        K = np.zeros((ne, 24, 24))
        im = np.array([6 * i + k for i in range(4) for k in (0, 1)])
        ib = np.array([6 * i + k for i in range(4) for k in (2, 3, 4)])
        idr = np.array([6 * i + 5 for i in range(4)])
        K[:, im[:, None], im[None, :]] = Km
        K[:, ib[:, None], ib[None, :]] = Kb
        kd = self.drill * Am[:, 2, 2] * area
        Pd = np.eye(4) - 0.25 + 1e-4 * np.eye(4)
        K[:, idr[:, None], idr[None, :]] = kd[:, None, None] * Pd[None]
        # centre B matrices for stress recovery
        dNx0 = np.einsum("eij,jk->eik", iJ0, dN0)
        Bm0 = np.zeros((ne, 3, 8))
        Bm0[:, 0, 0::2] = dNx0[:, 0]
        Bm0[:, 1, 1::2] = dNx0[:, 1]
        Bm0[:, 2, 0::2] = dNx0[:, 1]
        Bm0[:, 2, 1::2] = dNx0[:, 0]
        Bb0 = np.zeros((ne, 3, 12))
        Bb0[:, 0, 2::3] = dNx0[:, 0]
        Bb0[:, 1, 1::3] = -dNx0[:, 1]
        Bb0[:, 2, 1::3] = -dNx0[:, 0]
        Bb0[:, 2, 2::3] = dNx0[:, 1]
        return {"E": E, "R": R, "xy": xy, "K": K, "cond": cond, "Am": Am, "Db": Db, "rhoA": rhoA, "area": area,
                "Bm0": Bm0, "Bb0": Bb0, "im": im, "ib": ib}

    # ------------------------------------------------------------------ beams / bars
    def _beam_data(self):
        out = []
        for (n1, n2, pid, o1, o2, zref) in self.beams:
            p = self.beam_props[pid]
            o1 = np.zeros(3) if o1 is None else np.asarray(o1, float)
            o2 = np.zeros(3) if o2 is None else np.asarray(o2, float)
            x1, x2 = self.nodes[n1] + o1, self.nodes[n2] + o2
            L = np.linalg.norm(x2 - x1)
            ex = (x2 - x1) / L
            z = np.asarray(zref, float)
            z = z - (z @ ex) * ex
            z /= np.linalg.norm(z)
            ey = np.cross(z, ex)
            R = np.array([ex, ey, z])
            T = np.zeros((12, 12))
            for k in range(4):
                T[3 * k:3 * k + 3, 3 * k:3 * k + 3] = R
            Toff = np.eye(12)
            for a, o in ((0, o1), (6, o2)):
                S = np.array([[0, -o[2], o[1]], [o[2], 0, -o[0]], [-o[1], o[0], 0]])
                Toff[a:a + 3, a + 3:a + 6] = -S
            out.append((n1, n2, p, L, T @ Toff))
        return out

    @staticmethod
    def _beam_k(p, L):
        E, G, A, Iy, Iz, J = p["E"], p["G"], p["A"], p["Iy"], p["Iz"], p["J"]
        k = np.zeros((12, 12))
        k[np.ix_([0, 6], [0, 6])] = E * A / L * np.array([[1, -1], [-1, 1]])
        k[np.ix_([3, 9], [3, 9])] = G * J / L * np.array([[1, -1], [-1, 1]])
        a = E * Iz / L**3 * np.array([[12, 6 * L, -12, 6 * L], [6 * L, 4 * L * L, -6 * L, 2 * L * L],
                                      [-12, -6 * L, 12, -6 * L], [6 * L, 2 * L * L, -6 * L, 4 * L * L]])
        k[np.ix_([1, 5, 7, 11], [1, 5, 7, 11])] = a
        b = E * Iy / L**3 * np.array([[12, -6 * L, -12, -6 * L], [-6 * L, 4 * L * L, 6 * L, 2 * L * L],
                                      [-12, 6 * L, 12, 6 * L], [-6 * L, 2 * L * L, 6 * L, 4 * L * L]])
        k[np.ix_([2, 4, 8, 10], [2, 4, 8, 10])] = b
        return k

    @staticmethod
    def _beam_kg(P, L):
        """Geometric stiffness of an axially loaded beam (Przemieniecki 1968, Eq. 15.? ; Cook et al. Ch. 18)."""
        g = P / (30 * L) * np.array([[36, 3 * L, -36, 3 * L], [3 * L, 4 * L * L, -3 * L, -L * L],
                                     [-36, -3 * L, 36, -3 * L], [3 * L, -L * L, -3 * L, 4 * L * L]])
        k = np.zeros((12, 12))
        k[np.ix_([1, 5, 7, 11], [1, 5, 7, 11])] = g
        s = np.diag([1, -1, 1, -1])
        k[np.ix_([2, 4, 8, 10], [2, 4, 8, 10])] = s @ g @ s
        return k

    # ------------------------------------------------------------------ assembly
    def _scatter(self, rows, cols, vals):
        n = self.ndof
        return sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                             shape=(n, n)).tocsr()

    def _shell_dofs(self, E):
        return (6 * E[:, :, None] + np.arange(6)[None, None, :]).reshape(len(E), 24)

    def _to_global(self, Kl, R):
        ne = len(Kl)
        K5 = Kl.reshape(ne, 8, 3, 8, 3)
        Kg = np.einsum("eki,eakbl,elj->eaibj", R, K5, R)
        return Kg.reshape(ne, 24, 24)

    def stiffness(self):
        rows, cols, vals = [], [], []
        sh = None
        if self.shells:
            sh = self._shell_local()
            Kg = self._to_global(sh["K"], sh["R"])
            dofs = self._shell_dofs(sh["E"])
            rows.append(np.repeat(dofs, 24, axis=1).ravel())
            cols.append(np.tile(dofs, (1, 24)).ravel())
            vals.append(Kg.ravel())
        bd = self._beam_data()
        for n1, n2, p, L, T in bd:
            k = T.T @ self._beam_k(p, L) @ T
            d = np.r_[np.arange(6 * n1, 6 * n1 + 6), np.arange(6 * n2, 6 * n2 + 6)]
            rows.append(np.repeat(d, 12))
            cols.append(np.tile(d, 12))
            vals.append(k.ravel())
        for n1, n2, EA, _ in self.bars:
            e = self.nodes[n2] - self.nodes[n1]
            L = np.linalg.norm(e)
            e /= L
            k3 = EA / L * np.outer(e, e)
            k = np.block([[k3, -k3], [-k3, k3]])
            d = np.r_[np.arange(6 * n1, 6 * n1 + 3), np.arange(6 * n2, 6 * n2 + 3)]
            rows.append(np.repeat(d, 6))
            cols.append(np.tile(d, 6))
            vals.append(k.ravel())
        return self._scatter(rows, cols, vals), sh, bd

    def mass(self, sh=None, bd=None):
        m = np.zeros(self.ndof)
        if self.shells:
            sh = sh or self._shell_local()
            mn = sh["rhoA"] * sh["area"] / 4
            t = np.array([self.sections[e[4]].t for e in self.shells])
            for k in range(4):
                n = sh["E"][:, k]
                for d in range(3):
                    np.add.at(m, 6 * n + d, mn)
                for d in range(3, 6):
                    np.add.at(m, 6 * n + d, mn * (t**2 / 12 + sh["area"] / 48))
        for n1, n2, p, L, _ in (bd if bd is not None else self._beam_data()):
            mm = p.get("rho", 0.0) * p["A"] * L / 2
            for n in (n1, n2):
                m[6 * n:6 * n + 3] += mm
                m[6 * n + 3:6 * n + 6] += mm * L**2 / 24 * 1e-2
        for n1, n2, _, rA in self.bars:
            L = np.linalg.norm(self.nodes[n2] - self.nodes[n1])
            for n in (n1, n2):
                m[6 * n:6 * n + 3] += rA * L / 2
        for n, mv in self.point_masses.items():
            m[6 * n:6 * n + 3] += mv
        return sp.diags(m).tocsr()

    def structural_mass(self) -> float:
        sh = self._shell_local() if self.shells else None
        tot = float(np.sum(sh["rhoA"] * sh["area"])) if sh else 0.0
        for n1, n2, p, L, _ in self._beam_data():
            tot += p.get("rho", 0.0) * p["A"] * L
        return tot

    # ------------------------------------------------------------------ analyses
    def solve_static(self, F: np.ndarray | None = None) -> dict:
        K, sh, bd = self.stiffness()
        F = self.load_vector() if F is None else F
        free = self.free_dofs()
        Kff = K[free][:, free]
        lu = Factor(Kff)
        u = np.zeros(self.ndof)
        u[free] = lu.solve(F[free])
        res = {"u": u, "K": K, "free": free, "lu": lu, "_sh": sh, "_bd": bd}
        res.update(self.recover(u, sh, bd))
        return res

    def recover(self, u, sh=None, bd=None) -> dict:
        """Element resultants: shells N (Nx, Ny, Nxy) [N/m] and M [N m/m] at the centre (element axes);
        beams axial force P [N] and axial stress at the centroid."""
        out = {}
        if self.shells:
            sh = sh or self._shell_local()
            dofs = self._shell_dofs(sh["E"])
            ug = u[dofs].reshape(-1, 8, 3)
            ul = np.einsum("eij,eaj->eai", sh["R"], ug).reshape(-1, 24)
            dm = ul[:, sh["im"]]
            db = ul[:, sh["ib"]]
            a = -np.einsum("eij,ej->ei", sh["cond"], dm)
            Bm0, Bb0 = sh["Bm0"], sh["Bb0"]
            # incompatible modes vanish in the centre-derivative sense (P' = 0 at xi = eta = 0)
            eps = np.einsum("eij,ej->ei", Bm0, dm)
            N = np.einsum("eij,ej->ei", sh["Am"], eps)
            kap = np.einsum("eij,ej->ei", Bb0, db)
            M = np.einsum("eij,ej->ei", sh["Db"], kap)
            out.update({"N": N, "M": M, "eps": eps, "R": sh["R"], "inc": a})
        P, sig = [], []
        for n1, n2, p, L, T in (bd if bd is not None else self._beam_data()):
            d = np.r_[u[6 * n1:6 * n1 + 6], u[6 * n2:6 * n2 + 6]]
            dl = T @ d
            f = p["E"] * p["A"] * (dl[6] - dl[0]) / L
            P.append(f)
            sig.append(f / p["A"])
        out["P"], out["sigma_beam"] = np.array(P), np.array(sig)
        return out

    def geometric_stiffness(self, stat: dict):
        rows, cols, vals = [], [], []
        if self.shells:
            sh = stat["_sh"]
            E, R, xy = sh["E"], sh["R"], sh["xy"]
            ne = len(E)
            N = stat["N"]
            S = np.zeros((ne, 2, 2))
            S[:, 0, 0], S[:, 1, 1], S[:, 0, 1], S[:, 1, 0] = N[:, 0], N[:, 1], N[:, 2], N[:, 2]
            kg4 = np.zeros((ne, 4, 4))
            for (xi, eta) in _GP:
                _, dN = _shape(xi, eta)
                J = np.einsum("ij,ejk->eik", dN, xy)
                detJ = np.linalg.det(J)
                dNx = np.einsum("eij,jk->eik", np.linalg.inv(J), dN)
                kg4 += np.einsum("eki,ekl,elj->eij", dNx, S, dNx) * detJ[:, None, None]
            Kl = np.zeros((ne, 24, 24))
            for d in (0, 1, 2):
                idx = np.array([6 * i + d for i in range(4)])
                Kl[:, idx[:, None], idx[None, :]] = kg4
            Kg = self._to_global(Kl, R)
            dofs = self._shell_dofs(E)
            rows.append(np.repeat(dofs, 24, axis=1).ravel())
            cols.append(np.tile(dofs, (1, 24)).ravel())
            vals.append(Kg.ravel())
        for (n1, n2, p, L, T), P in zip(stat["_bd"], stat["P"]):
            k = T.T @ self._beam_kg(P, L) @ T
            d = np.r_[np.arange(6 * n1, 6 * n1 + 6), np.arange(6 * n2, 6 * n2 + 6)]
            rows.append(np.repeat(d, 12))
            cols.append(np.tile(d, 12))
            vals.append(k.ravel())
        if not rows:
            return sp.csr_matrix((self.ndof, self.ndof))
        return self._scatter(rows, cols, vals)

    def buckling(self, stat: dict | None = None, n_modes: int = 4, sigma: float | None = None) -> dict:
        """Smallest positive load factors λ of (K + λ K_G(σ0)) φ = 0 (σ0 from the static load case)."""
        stat = stat or self.solve_static()
        Kg = self.geometric_stiffness(stat)
        free = stat["free"]
        K = stat["K"][free][:, free].tocsr()
        G = (-Kg[free][:, free]).tocsr()
        lam_all, vec_all = [], []
        sig = sigma or 0.05
        for _ in range(6):
            try:
                fac = Factor(K - sig * G)       # buckling mode: OPinv = (K − σ K_G)⁻¹ with K_G = −G
                w, v = spla.eigsh(K, k=min(n_modes + 6, K.shape[0] - 2), M=G, sigma=sig, mode="buckling",
                                  which="LM", OPinv=fac.op())
                fac.free()
            except Exception:  # pragma: no cover
                w, v = np.array([]), None
            pos = w > 0
            if pos.sum() >= n_modes or (pos.any() and sig > 10):
                order = np.argsort(w[pos])
                lam_all = w[pos][order][:n_modes]
                vec_all = v[:, pos][:, order][:, :n_modes]
                break
            sig *= 4
        modes = np.zeros((self.ndof, len(lam_all)))
        if len(lam_all):
            modes[free] = vec_all
        return {"lambda": np.asarray(lam_all), "modes": modes}

    def modal(self, n_modes: int = 6, stat_K=None) -> dict:
        K, sh, bd = self.stiffness()
        M = self.mass(sh, bd)
        free = self.free_dofs()
        Kf, Mf = K[free][:, free].tocsr(), M[free][:, free].tocsr()
        fac = Factor(Kf + Mf)
        w2, v = spla.eigsh(Kf, k=n_modes, M=Mf, sigma=-1.0, which="LM", OPinv=fac.op())
        fac.free()
        o = np.argsort(w2)
        modes = np.zeros((self.ndof, n_modes))
        modes[free] = v[:, o]
        return {"f_Hz": np.sqrt(np.maximum(w2[o], 0)) / (2 * math.pi), "modes": modes}
