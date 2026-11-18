"""Rib topology demo (Phase 6, optional) — 2-D SIMP compliance minimisation of a wing-box rib web.

Formulation (written from the papers, no code copied): density-based topology optimisation with the SIMP
penalisation E(ρ) = E_min + ρ^p (E − E_min) (Bendsøe 1989; Bendsøe & Sigmund, *Topology Optimization*, 2003),
bilinear Q4 plane-stress elements, density filter (Bruns & Tortorelli 2001) and the Optimality-Criteria update with
bisection on the volume Lagrange multiplier (Sigmund 2001 "A 99 line topology optimization code"; Andreassen et al.
2011 "Efficient topology optimization in MATLAB using 88 lines of code", Struct. Multidisc. Optim. 43).

Rib model (``ASSUMPTION``, demonstration only): the rib web between the spars is a rectangle w × h, attached to
both spar webs (left/right edges clamped), loaded by the Brazier crushing pressure p (Niu §5.4, from
``sizing6.size_ribs``) pushing the upper and lower covers towards each other, plus the bay shear increment ΔV
applied as a uniform vertical line load on the upper edge (reacted by the spar webs). The result is a layout suggestion (where lightening
holes may go); the rib is still SIZED by ``sizing6.size_ribs``. Linear, small displacements, single load case."""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve


def _ke(nu: float) -> np.ndarray:
    """Q4 plane-stress element stiffness for unit E, unit thickness, unit square element (closed form)."""
    k = np.array([1 / 2 - nu / 6, 1 / 8 + nu / 8, -1 / 4 - nu / 12, -1 / 8 + 3 * nu / 8,
                  -1 / 4 + nu / 12, -1 / 8 - nu / 8, nu / 6, 1 / 8 - 3 * nu / 8])
    i = [[0, 1, 2, 3, 4, 5, 6, 7], [1, 0, 7, 6, 5, 4, 3, 2], [2, 7, 0, 5, 6, 3, 4, 1], [3, 6, 5, 0, 7, 2, 1, 4],
         [4, 5, 6, 7, 0, 1, 2, 3], [5, 4, 3, 2, 1, 0, 7, 6], [6, 3, 4, 1, 2, 7, 0, 5], [7, 2, 1, 4, 3, 6, 5, 0]]
    return 1 / (1 - nu**2) * k[np.array(i)]


def rib_simp(w: float, h: float, p_crush: float, dV: float, nelx: int = 90, vol: float = 0.4, penal: float = 3.0,
             rmin: float = 1.8, nu: float = 0.33, iters: int = 80, tol: float = 0.01) -> dict:
    """Return the density field (nely × nelx), compliance history and the mesh size. Units cancel (unit E, t)."""
    nely = max(int(round(nelx * h / w)), 8)
    a = w / nelx                                          # element size (square elements)
    KE = _ke(nu)
    nn = (nelx + 1) * (nely + 1)
    ndof = 2 * nn
    nid = np.arange(nn).reshape(nelx + 1, nely + 1).T     # node id [row j (top→bottom), col i]
    n1 = nid[1:, :-1].ravel(order="F")                    # element lower-left (row below)
    n2 = nid[1:, 1:].ravel(order="F")
    n3 = nid[:-1, 1:].ravel(order="F")
    n4 = nid[:-1, :-1].ravel(order="F")
    edof = np.stack([2 * n1, 2 * n1 + 1, 2 * n2, 2 * n2 + 1, 2 * n3, 2 * n3 + 1, 2 * n4, 2 * n4 + 1], 1)
    iK = np.kron(edof, np.ones((8, 1), int)).ravel()
    jK = np.kron(edof, np.ones((1, 8), int)).ravel()
    # loads: crushing pressure on top (down, −y) and bottom (up, +y) edges; shear flow ΔV/(2h)·… on the side edges
    F = np.zeros(ndof)
    top, bot = nid[0, :], nid[-1, :]
    fl = p_crush * a * np.ones(nelx + 1)
    fl[[0, -1]] *= 0.5
    F[2 * top + 1] -= fl
    F[2 * bot + 1] += fl
    # bay shear: the rib transfers ΔV from the covers to the spar webs → vertical load along the top edge
    F[2 * top + 1] -= dV / (nelx + 1)
    fixed = np.r_[2 * nid[:, 0], 2 * nid[:, 0] + 1, 2 * nid[:, -1], 2 * nid[:, -1] + 1]
    free = np.setdiff1d(np.arange(ndof), fixed)
    # density filter
    cx, cy = np.meshgrid(np.arange(nelx), np.arange(nely))
    cx, cy = cx.ravel(order="F"), cy.ravel(order="F")
    r = int(np.ceil(rmin))
    rows, cols, vals = [], [], []
    for e in range(nelx * nely):
        dx = np.arange(max(cx[e] - r, 0), min(cx[e] + r + 1, nelx))
        dy = np.arange(max(cy[e] - r, 0), min(cy[e] + r + 1, nely))
        X, Y = np.meshgrid(dx, dy)
        wgt = np.maximum(0.0, rmin - np.hypot(X - cx[e], Y - cy[e])).ravel()
        rows += [e] * wgt.size
        cols += (X.ravel() * nely + Y.ravel()).tolist()
        vals += wgt.tolist()
    H = coo_matrix((vals, (rows, cols)), shape=(nelx * nely,) * 2).tocsr()
    Hs = np.asarray(H.sum(1)).ravel()
    x = np.full(nelx * nely, vol)
    xp = x.copy()
    Emin, hist = 1e-9, []
    for it in range(iters):
        sK = (KE.ravel()[None, :] * (Emin + xp[:, None] ** penal * (1 - Emin))).ravel()
        K = coo_matrix((sK, (iK, jK)), shape=(ndof, ndof)).tocsc()
        K = (K + K.T) / 2
        U = np.zeros(ndof)
        U[free] = spsolve(K[free][:, free], F[free])
        ue = U[edof]
        ce = np.einsum("ij,jk,ik->i", ue, KE, ue)
        c = float(np.sum((Emin + xp**penal * (1 - Emin)) * ce))
        hist.append(c)
        dc = H @ ((-penal * xp ** (penal - 1) * (1 - Emin) * ce) / Hs)
        dv = H @ (np.ones_like(x) / Hs)
        l1, l2, move = 0.0, 1e9, 0.2
        while (l2 - l1) / (l1 + l2 + 1e-30) > 1e-3:
            lm = 0.5 * (l1 + l2)
            xn = np.clip(x * np.sqrt(np.maximum(-dc, 0) / (dv * lm)), np.maximum(0, x - move), np.minimum(1, x + move))
            xpn = (H @ xn) / Hs
            l1, l2 = (lm, l2) if xpn.mean() > vol else (l1, lm)
        change = float(np.max(np.abs(xn - x)))
        x, xp = xn, xpn
        if change < tol:
            break
    return {"rho": xp.reshape(nelx, nely).T, "compliance": hist, "nelx": nelx, "nely": nely, "iters": it + 1,
            "vol": float(xp.mean()), "w": w, "h": h}


def plot_rib(res: dict, path, title: str = ""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.6), gridspec_kw={"width_ratios": [3, 1]})
    ax[0].imshow(1 - res["rho"], cmap="gray", extent=(0, res["w"] * 1e3, 0, res["h"] * 1e3), vmin=0, vmax=1)
    ax[0].set_xlabel("x entre longarinas [mm]")
    ax[0].set_ylabel("z [mm]")
    ax[0].set_title(title or "Nervura — SIMP (demo)")
    ax[1].plot(res["compliance"])
    ax[1].set_xlabel("iteração")
    ax[1].set_ylabel("flexibilidade (E = t = 1)")
    ax[1].set_yscale("log")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
