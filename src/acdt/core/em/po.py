"""Physical Optics (PO) radar cross-section of perfectly conducting (PEC) triangulated surfaces — LOW FIDELITY.

Formulation (Knott, Shaeffer & Tuley, *Radar Cross Section*, 2nd ed. 1993, Ch. 5; Balanis, *Advanced Engineering
Electromagnetics*, 2nd ed. 2012, §11.3; Gordon, IEEE TAP 23(4) 1975 for the facet integral; same physics as
POFACETS, Jenn/NPS):

* PO surface current on the lit side J = 2 n̂ × H_i (zero in shadow); lit test n̂·k̂_i < 0 (no self-shadowing by other
  parts unless ``occlusion=True``);
* far field, receiver polarisation ê_r, incident polarisation ê_i, propagation k̂_i, scattering direction ŝ:
  σ = (k²/π) |Σ_facets ê_r·[n̂ × (k̂_i × ê_i)] I_f|²,  I_f = ∫_f e^{j w·r} dS,  w = k(ŝ − k̂_i)
  (normal-incidence flat plate → 4πA²/λ²);
* Gordon's closed form of I_f by the 2-D divergence theorem (p = in-plane part of w, a_m edge vectors, r_m vertices,
  counter-clockwise about n̂):  I_f = e^{j w_n (n̂·r_0)} Σ_m [p·(a_m × n̂)] / (j|p|²) e^{j p·(r_m + a_m/2)} sinc(p·a_m/2),
  and I_f = A e^{j w·r_c} when |p| L ≪ 1;
* optional second bounce by shooting-and-bouncing rays with PO on the exit footprint (GO–PO, Ling, Chou & Lee,
  IEEE TAP 37(2) 1989) so dihedral / cavity-like corner returns are included approximately.

``LIMITATIONS`` (printed into every report): no edge diffraction (no PTD/MEC), no creeping/travelling waves, no
cavity/inlet modelling beyond 2 bounces, no radar-absorbing material, PEC only; accuracy degrades away from
specular directions and for edge-on incidence. High fidelity: full-wave (MoM/MLFMM, or FDTD such as openEMS).

Units: SI; σ in m², dBsm = 10 log10 σ."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

C0 = 299_792_458.0
LIMITATIONS = ("Physical Optics, PEC, low fidelity: no edge diffraction (PTD/MEC), no creeping or travelling waves, "
               "no cavities/inlets beyond the optional 2nd SBR bounce, no RAM/coatings; self-shadowing only with "
               "occlusion=True; unreliable far from specular and at edge-on aspects.")


@dataclass
class Mesh:
    V: np.ndarray            # (nv, 3)
    F: np.ndarray            # (nf, 3) int, counter-clockwise about the outward normal
    name: str = "mesh"
    info: dict = field(default_factory=dict)

    def __post_init__(self):
        self.V = np.asarray(self.V, float)
        self.F = np.asarray(self.F, int)
        a, b, c = self.V[self.F[:, 0]], self.V[self.F[:, 1]], self.V[self.F[:, 2]]
        cr = np.cross(b - a, c - a)
        nrm = np.linalg.norm(cr, axis=1)
        keep = nrm > 1e-14 * max(1.0, float(np.max(nrm)) if len(nrm) else 1.0)
        if not keep.all():
            self.F = self.F[keep]
            a, b, c, cr, nrm = a[keep], b[keep], c[keep], cr[keep], nrm[keep]
        self.n = cr / nrm[:, None]
        self.area = 0.5 * nrm
        self.c = (a + b + c) / 3.0
        self.P = np.stack([a, b, c], axis=1)                      # (nf, 3, 3)
        self.Lmax = np.max(np.linalg.norm(np.roll(self.P, -1, axis=1) - self.P, axis=2), axis=1)

    @property
    def n_facets(self):
        return len(self.F)

    def merged(self, other: "Mesh", name=None) -> "Mesh":
        return Mesh(np.r_[self.V, other.V], np.r_[self.F, other.F + len(self.V)], name or self.name)

    def flipped(self) -> "Mesh":
        return Mesh(self.V, self.F[:, ::-1], self.name)

    def transformed(self, R=None, t=None) -> "Mesh":
        V = self.V @ (np.eye(3) if R is None else np.asarray(R)).T + (0 if t is None else np.asarray(t))
        return Mesh(V, self.F, self.name)


# ------------------------------------------------------------------------------------------------ directions
def direction(az_deg, el_deg, nose=(-1.0, 0.0, 0.0), up=(0.0, 0.0, 1.0)):
    """Unit vector from the target towards the radar for azimuth (from the nose, positive towards +y side of the
    nose-left frame: rotation about ``up``) and elevation (positive = radar above). Returns (..., 3)."""
    az, el = np.radians(np.asarray(az_deg, float)), np.radians(np.asarray(el_deg, float))
    nose, up = np.asarray(nose, float), np.asarray(up, float)
    side = np.cross(up, nose)
    d = (np.cos(el)[..., None] * (np.cos(az)[..., None] * nose + np.sin(az)[..., None] * side)
         + np.sin(el)[..., None] * up)
    return d / np.linalg.norm(d, axis=-1, keepdims=True)


def pol_basis(r_hat, up=(0.0, 0.0, 1.0)):
    """Horizontal ê_H = (up × r̂)/|·| and vertical ê_V = ê_H × r̂ unit vectors (both ⊥ r̂)."""
    up = np.asarray(up, float)
    h = np.cross(up, r_hat)
    nh = np.linalg.norm(h, axis=-1, keepdims=True)
    bad = nh[..., 0] < 1e-9
    if np.any(bad):
        h[bad] = np.cross(np.array([0.0, 1.0, 0.0]), r_hat[bad])
        nh = np.linalg.norm(h, axis=-1, keepdims=True)
    h = h / nh
    v = np.cross(h, r_hat)
    return h, v


# ------------------------------------------------------------------------------------------------ facet integral
def facet_integrals(mesh: Mesh, w: np.ndarray) -> np.ndarray:
    """Gordon closed form I_f(w) = ∫_f e^{j w·r} dS for all facets and all wave vectors w (nw, 3) → (nw, nf)."""
    n = mesh.n                                           # (nf, 3)
    P = mesh.P                                           # (nf, 3, 3)
    wn = w @ n.T                                         # (nw, nf)
    p = w[:, None, :] - wn[..., None] * n[None]          # (nw, nf, 3) in-plane part
    p2 = np.einsum("wfi,wfi->wf", p, p)
    phase0 = np.exp(1j * wn * np.einsum("fi,fi->f", n, P[:, 0])[None])
    out = np.zeros(wn.shape, complex)
    for m in range(3):
        r_m = P[:, m]
        a_m = P[:, (m + 1) % 3] - r_m
        nu = np.cross(a_m, n)                            # outward edge normal × |a_m|
        pa = np.einsum("wfi,fi->wf", p, a_m)
        pn = np.einsum("wfi,fi->wf", p, nu)
        pr = np.einsum("wfi,fi->wf", p, r_m + a_m / 2)
        out += pn * np.exp(1j * pr) * np.sinc(pa / (2 * np.pi))       # np.sinc(x) = sin(πx)/(πx)
    small = p2 * mesh.Lmax[None] ** 2 < 1e-6
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(small, 0.0, out / (1j * np.where(small, 1.0, p2)))
    # in-plane part already includes the phase of p·r; add normal phase
    out = out * phase0
    if np.any(small):
        cen = np.exp(1j * (w @ mesh.c.T)) * mesh.area[None]
        out = np.where(small, cen, out)
    return out


# ------------------------------------------------------------------------------------------------ RCS
def _lit(mesh, k_i):
    return (k_i @ mesh.n.T) < 0.0                       # (nw, nf)


def occluded(mesh: Mesh, origins: np.ndarray, dirs: np.ndarray, eps: float = 1e-7, chunk: int = 4096) -> np.ndarray:
    """Möller–Trumbore: True where the ray origin + t·dir (t > eps·scale) hits any facet (vectorised, chunked)."""
    P = mesh.P
    e1, e2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
    scale = float(np.max(np.ptp(mesh.V, axis=0)))
    hit = np.zeros(len(origins), bool)
    for s in range(0, len(origins), max(1, chunk // max(1, len(P) // 256 + 1))):
        o, d = origins[s:s + chunk], dirs[s:s + chunk]
        pv = np.cross(d[:, None, :], e2[None])
        det = np.einsum("rfi,fi->rf", pv, e1)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = o[:, None, :] - P[None, :, 0]
        u = np.einsum("rfi,rfi->rf", tv, pv) * inv
        qv = np.cross(tv, e1[None])
        v = np.einsum("ri,rfi->rf", d, qv) * inv
        t = np.einsum("fi,rfi->rf", e2, qv) * inv
        h = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > eps * scale)
        hit[s:s + chunk] = h.any(axis=1)
    return hit


def first_hit(mesh: Mesh, origins, dirs, eps=1e-7):
    """Index of the first facet hit and the distance for each ray (−1 / inf if none)."""
    P = mesh.P
    e1, e2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
    scale = float(np.max(np.ptp(mesh.V, axis=0)))
    idx = np.full(len(origins), -1)
    dist = np.full(len(origins), np.inf)
    ch = max(1, int(2e6 // max(1, len(P))))
    for s in range(0, len(origins), ch):
        o, d = origins[s:s + ch], dirs[s:s + ch]
        pv = np.cross(d[:, None, :], e2[None])
        det = np.einsum("rfi,fi->rf", pv, e1)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = o[:, None, :] - P[None, :, 0]
        u = np.einsum("rfi,rfi->rf", tv, pv) * inv
        qv = np.cross(tv, e1[None])
        v = np.einsum("ri,rfi->rf", d, qv) * inv
        t = np.einsum("fi,rfi->rf", e2, qv) * inv
        h = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > eps * scale)
        t = np.where(h, t, np.inf)
        j = np.argmin(t, axis=1)
        tt = t[np.arange(len(j)), j]
        good = np.isfinite(tt)
        idx[s:s + ch][good] = j[good]
        dist[s:s + ch][good] = tt[good]
    return idx, dist


def _subsample(mesh: Mesh, f_idx, n_sub):
    """Barycentric sub-triangle centroids (n_sub² per facet) and their areas."""
    pts, ar, owner = [], [], []
    for i in range(n_sub):
        for j in range(n_sub - i):
            for up in (0, 1):
                if up and i + j >= n_sub - 1:
                    continue
                if not up:
                    b = np.array([[i, j], [i + 1, j], [i, j + 1]], float)
                else:
                    b = np.array([[i + 1, j], [i + 1, j + 1], [i, j + 1]], float)
                bc = b.mean(axis=0) / n_sub
                pts.append(bc)
    bc = np.array(pts)                                       # (ns, 2)
    P = mesh.P[f_idx]                                        # (nfl, 3, 3)
    X = (P[:, None, 0] + bc[None, :, 0, None] * (P[:, None, 1] - P[:, None, 0])
         + bc[None, :, 1, None] * (P[:, None, 2] - P[:, None, 0]))
    A = np.repeat(mesh.area[f_idx] / len(bc), len(bc))
    owner = np.repeat(f_idx, len(bc))
    return X.reshape(-1, 3), A, owner


def rcs(mesh: Mesh, freq_hz: float, k_inc: np.ndarray, s_dir: np.ndarray, e_inc: np.ndarray, e_rec: np.ndarray,
        occlusion: bool = False, bounces: int = 1, n_sub: int | None = None, n_sub_max: int = 40) -> np.ndarray:
    """σ [m²] for arrays of incidence directions k̂_i (propagation), scattering directions ŝ and polarisations
    (all (nw, 3)). ``bounces = 2`` adds the SBR second bounce (rays per facet n_sub² from ``n_sub``, default chosen
    so the ray-tube size ≤ λ/6)."""
    k_inc, s_dir = np.atleast_2d(k_inc), np.atleast_2d(s_dir)
    e_inc, e_rec = np.atleast_2d(e_inc), np.atleast_2d(e_rec)
    ch = max(1, int(1.5e6 // max(1, mesh.n_facets)))
    if len(k_inc) > ch:                               # chunk the directions to bound memory
        return np.concatenate([rcs(mesh, freq_hz, k_inc[s:s + ch], s_dir[s:s + ch], e_inc[s:s + ch], e_rec[s:s + ch],
                                   occlusion, bounces, n_sub, n_sub_max) for s in range(0, len(k_inc), ch)])
    lam = C0 / freq_hz
    k = 2 * math.pi / lam
    lit = _lit(mesh, k_inc)
    if occlusion:
        for wi in range(len(k_inc)):
            idx = np.nonzero(lit[wi])[0]
            if len(idx):
                lit[wi, idx] &= ~occluded(mesh, mesh.c[idx], np.repeat(-k_inc[wi][None], len(idx), 0))
    w = k * (s_dir - k_inc)
    I = facet_integrals(mesh, w)                                     # (nw, nf)
    kxe = np.cross(k_inc, e_inc)                                     # (nw, 3)
    # ê_r · (n̂ × (k̂ × ê)) = (ê_r × n̂)·(k̂×ê)  →  per facet
    amp = np.einsum("wi,wfi->wf", kxe, np.cross(e_rec[:, None, :], mesh.n[None]))
    S = np.sum(np.where(lit, amp * I, 0.0), axis=1)
    if bounces >= 2:
        S = S + _second_bounce(mesh, k, lam, k_inc, s_dir, e_inc, e_rec, lit, n_sub, n_sub_max)
    return (k ** 2 / math.pi) * np.abs(S) ** 2


def _second_bounce(mesh, k, lam, k_inc, s_dir, e_inc, e_rec, lit, n_sub, n_sub_max=40):
    out = np.zeros(len(k_inc), complex)
    for wi in range(len(k_inc)):
        f1 = np.nonzero(lit[wi])[0]
        if not len(f1):
            continue
        ns = n_sub or int(min(n_sub_max, max(2, math.ceil(np.max(mesh.Lmax[f1]) / (lam / 6)))))
        X, dA, own = _subsample(mesh, f1, ns)
        n1 = mesh.n[own]
        ki = k_inc[wi]
        kr = ki[None] - 2 * (n1 @ ki)[:, None] * n1                   # reflected direction
        j, d = first_hit(mesh, X + 1e-9 * n1, kr)
        ok = j >= 0
        if not ok.any():
            continue
        X, dA, n1, kr, j, d = X[ok], dA[ok], n1[ok], kr[ok], j[ok], d[ok]
        n2 = mesh.n[j]
        front = np.einsum("ri,ri->r", kr, n2) < 0
        if not front.any():
            continue
        X, dA, n1, kr, j, d, n2 = X[front], dA[front], n1[front], kr[front], j[front], d[front], n2[front]
        Q = X + d[:, None] * kr
        # PEC reflection of the incident polarisation: E_r = 2(n̂·E)n̂ − E
        Er = 2 * (n1 @ e_inc[wi])[:, None] * n1 - e_inc[wi][None]
        # footprint area on the second facet (ray-tube Jacobian, GO)
        cos1 = np.abs(n1 @ ki)
        cos2 = np.abs(np.einsum("ri,ri->r", kr, n2))
        dA2 = dA * cos1 / np.maximum(cos2, 1e-6)
        phase = np.exp(-1j * k * (X @ ki + d)) * np.exp(1j * k * (Q @ s_dir[wi]))
        kxe = np.cross(kr, Er)
        amp = np.einsum("ri,ri->r", kxe, np.cross(e_rec[wi][None], n2))
        out[wi] = np.sum(amp * phase * dA2)
    return out


def monostatic(mesh: Mesh, freq_hz: float, az_deg, el_deg, pol: str = "VV", nose=(-1, 0, 0), up=(0, 0, 1),
               **kw) -> np.ndarray:
    """Monostatic σ [m²] on the (az, el) grid (broadcast arrays). pol ∈ HH, VV, HV, VH (transmit-receive)."""
    az, el = np.broadcast_arrays(np.asarray(az_deg, float), np.asarray(el_deg, float))
    r = direction(az.ravel(), el.ravel(), nose, up)
    h, v = pol_basis(r, up)
    pick = {"H": h, "V": v}
    et, er = pick[pol[0].upper()], pick[pol[1].upper()]
    return rcs(mesh, freq_hz, -r, r, et, er, **kw).reshape(az.shape)


def bistatic(mesh: Mesh, freq_hz: float, k_inc_dir, e_inc, s_dirs, e_rec, **kw):
    s = np.atleast_2d(s_dirs)
    n = len(s)
    return rcs(mesh, freq_hz, np.repeat(np.atleast_2d(k_inc_dir), n, 0), s, np.repeat(np.atleast_2d(e_inc), n, 0),
               np.atleast_2d(e_rec) if np.ndim(e_rec) == 2 else np.repeat(np.atleast_2d(e_rec), n, 0), **kw)


def dbsm(sigma):
    return 10 * np.log10(np.maximum(np.asarray(sigma, float), 1e-30))


def sector_metrics(sigma: np.ndarray) -> dict:
    """Mean (arithmetic in m², reported also in dBsm), median and max of σ over a sector."""
    s = np.asarray(sigma, float).ravel()
    return {"mean_m2": float(s.mean()), "mean_dbsm": float(dbsm(s.mean())), "median_dbsm": float(dbsm(np.median(s))),
            "max_dbsm": float(dbsm(s.max())), "n": int(s.size)}


# ------------------------------------------------------------------------------------------------ canonical shapes
def plate(a: float, b: float, nx: int = 1, ny: int = 1) -> Mesh:
    """Rectangular PEC plate a (x) × b (y) in z = 0, normal +z."""
    xs, ys = np.linspace(-a / 2, a / 2, nx + 1), np.linspace(-b / 2, b / 2, ny + 1)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    V = np.c_[X.ravel(), Y.ravel(), np.zeros(X.size)]
    F = []
    for i in range(nx):
        for j in range(ny):
            p = i * (ny + 1) + j
            q = p + ny + 1
            F += [(p, q, q + 1), (p, q + 1, p + 1)]
    return Mesh(V, F, "plate")


def icosphere(R: float, level: int = 4) -> Mesh:
    t = (1 + 5 ** 0.5) / 2
    V = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    F = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
         (8, 6, 7), (9, 8, 1)]
    V = [np.array(v, float) / np.linalg.norm(v) for v in V]
    for _ in range(level):
        cache, F2 = {}, []

        def mid(a, b):
            key = (min(a, b), max(a, b))
            if key not in cache:
                m = V[a] + V[b]
                V.append(m / np.linalg.norm(m))
                cache[key] = len(V) - 1
            return cache[key]
        for a, b, c in F:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            F2 += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        F = F2
    return Mesh(np.array(V) * R, F, "sphere")


def cylinder(R: float, L: float, n_theta: int = 360, n_z: int = 1, caps: bool = False) -> Mesh:
    """Circular cylinder along z (faceted), outward normals."""
    th = np.linspace(0, 2 * np.pi, n_theta, endpoint=False)
    zs = np.linspace(-L / 2, L / 2, n_z + 1)
    V = np.array([(R * math.cos(a), R * math.sin(a), z) for z in zs for a in th])
    F = []
    for iz in range(n_z):
        for i in range(n_theta):
            p, q = iz * n_theta + i, iz * n_theta + (i + 1) % n_theta
            F += [(p, q, q + n_theta), (p, q + n_theta, p + n_theta)]
    m = Mesh(V, F, "cylinder")
    if caps:
        c0 = len(V)
        V2 = np.r_[V, [[0, 0, -L / 2], [0, 0, L / 2]]]
        F2 = list(map(tuple, m.F))
        top = n_z * n_theta
        for i in range(n_theta):
            F2 += [(c0, (i + 1) % n_theta, i), (c0 + 1, top + i, top + (i + 1) % n_theta)]
        m = Mesh(V2, F2, "cylinder")
    return m


def dihedral(a: float, b: float, angle_deg: float = 90.0, n: int = 1) -> Mesh:
    """Two a (along the fold, y) × b plates joined along the y axis, opening towards +x, interior angle ``angle``;
    normals point into the opening (lit faces)."""
    h = math.radians(angle_deg) / 2
    d1 = np.array([math.cos(h), 0.0, math.sin(h)])
    d2 = np.array([math.cos(h), 0.0, -math.sin(h)])
    V, F = [], []
    for d, flip in ((d1, False), (d2, True)):
        base = len(V)
        for i in range(n + 1):
            for j in range(n + 1):
                V.append(d * b * i / n + np.array([0, -a / 2 + a * j / n, 0]))
        for i in range(n):
            for j in range(n):
                p = base + i * (n + 1) + j
                q = p + n + 1
                tri = [(p, q, q + 1), (p, q + 1, p + 1)]
                F += [t[::-1] for t in tri] if flip else tri
    m = Mesh(np.array(V), F, "dihedral")
    # orient normals towards the bisector (+x)
    F = m.F.copy()
    flip = m.n[:, 0] < 0
    F[flip] = F[flip][:, ::-1]
    return Mesh(m.V, F, "dihedral")


def read_stl(path) -> Mesh:
    """ASCII or binary STL → Mesh (vertices merged)."""
    import struct
    from pathlib import Path
    data = Path(path).read_bytes()
    tris = []
    if data[:5].lower() == b"solid" and b"facet" in data[:400]:
        vs = [list(map(float, l.split()[1:4])) for l in data.decode(errors="ignore").splitlines()
              if l.strip().startswith("vertex")]
        tris = np.array(vs).reshape(-1, 3, 3)
    else:
        n = struct.unpack("<I", data[80:84])[0]
        arr = np.frombuffer(data[84:84 + 50 * n], dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)),
                                                                   ("a", "<u2")]))
        tris = arr["v"].astype(float)
    flat = tris.reshape(-1, 3)
    uq, inv = np.unique(np.round(flat, 9), axis=0, return_inverse=True)
    return Mesh(uq, inv.reshape(-1, 3), Path(path).stem)
