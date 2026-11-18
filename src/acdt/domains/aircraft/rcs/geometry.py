"""Parametric *faceted* aircraft surface mesh for PO radar cross-section studies (Phase 6).

Frame: x aft from the nose, y right (starboard), z up; the nose points to −x. Components (closed, outward normals):

* fuselage: hexagonal "chined" cross-section — chines at z = 0 (half-width W/2), flat crown/keel of width w_t,
  side facets inclined at the *chine (facet) angle* φ from the horizontal; the section area is kept equal to the
  baseline round fuselage (πD²/4) so internal volume is preserved. Pointed nose over ``nose_frac``·L, constant
  section, boat-tail to ``tail_scale`` at the base (flat base).
* wing: straight-tapered, diamond (double-wedge) section of thickness t/c with the maximum thickness at 50 % c,
  leading-edge sweep Λ_LE, trailing-edge sweep Λ_TE (planform edge alignment), root at the chine line.
* V-tail: two diamond surfaces with dihedral (cant) Γ from the horizontal, LE sweep = wing LE sweep (aligned edges).

Geometry assumptions are flagged ``ASSUMPTION`` in :data:`DEFAULTS` and in the study report."""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np

from ....core.em.po import Mesh

DEFAULTS = {
    "crown_frac": 0.35,        # ASSUMPTION: flat crown/keel width w_t = 0.35 D
    "nose_frac": 0.22,         # ASSUMPTION: pointed nose length / L
    "tail_start": 0.62,        # ASSUMPTION: boat-tail starts at 0.62 L
    "tail_scale": 0.30,        # ASSUMPTION: base section scale
    "x_wing_le_frac": 0.33,    # ASSUMPTION: wing root LE at 0.33 L
    "tail_AR": 4.0,            # ASSUMPTION: V-tail panel aspect ratio (both panels, projected on own plane)
    "tail_taper": 0.5,         # ASSUMPTION
    "tail_tc": 0.08,           # ASSUMPTION
}


@dataclass
class Shape:
    """Design variables of the aero/RCS demo (P6 adds wing/fuselage/sensor stations)."""
    sweep_le_deg: float = 0.0
    align: float = 0.0          # 0 → baseline taper, 1 → TE parallel to LE (λ = 1)
    chine_deg: float = 45.0     # fuselage side-facet angle from horizontal
    tail_cant_deg: float = 42.0  # V-tail dihedral from horizontal
    # --- P6 N2 (defaults preserve Phase-6 aero/RCS behaviour) ---
    wing_z_frac: float = 0.0    # wing root z / (fuselage H/2); 0 = chine line (current)
    x_wing_le_frac: float | None = None  # None → DEFAULTS["x_wing_le_frac"]
    L_scale: float = 1.0        # fuselage length scale (volume ∝ L)
    D_scale: float = 1.0        # fuselage diameter scale (area preserved by hexagon vs πD²/4)
    sensor_x_frac: float = 0.18 # payload aperture x / L (nose = 0)

    def to_dict(self):
        return asdict(self)


def hexagon_section(D: float, chine_deg: float, crown_frac: float):
    """Chine half-width W/2 and height H of the hexagonal section with area πD²/4, crown w_t = crown_frac·D."""
    wt = crown_frac * D
    A = math.pi * D * D / 4
    tphi = math.tan(math.radians(chine_deg))
    # A = (2 w_t + H/tanφ) H / 2  →  H²/(2 tanφ) + w_t H − A = 0
    a, b, c = 1 / (2 * tphi), wt, -A
    H = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
    W = wt + H / tphi
    return W, H, wt


def _section_pts(W, H, wt, s):
    return np.array([(W / 2, 0), (wt / 2, H / 2), (-wt / 2, H / 2), (-W / 2, 0), (-wt / 2, -H / 2),
                     (wt / 2, -H / 2)]) * s


def fuselage_mesh(L, D, chine_deg, p=DEFAULTS) -> tuple[Mesh, dict]:
    W, H, wt = hexagon_section(D, chine_deg, p["crown_frac"])
    xs = [0.0, p["nose_frac"] * L, p["tail_start"] * L, L]
    sc = [0.0, 1.0, 1.0, p["tail_scale"]]
    V, F = [(0.0, 0.0, 0.0)], []
    rings = []
    for x, s in zip(xs[1:], sc[1:]):
        pts = _section_pts(W, H, wt, s)
        rings.append(len(V))
        V += [(x, y, z) for y, z in pts]
    n = 6
    r0 = rings[0]
    for i in range(n):
        F.append((0, r0 + (i + 1) % n, r0 + i))
    for ra, rb in zip(rings[:-1], rings[1:]):
        for i in range(n):
            a, b = ra + i, ra + (i + 1) % n
            c, d = rb + (i + 1) % n, rb + i
            F += [(a, b, c), (a, c, d)]
    rl = rings[-1]
    cb = len(V)
    V.append((L, 0.0, 0.0))
    for i in range(n):
        F.append((cb, rl + i, rl + (i + 1) % n))
    m = _orient(Mesh(np.array(V), F, "fuselage"), np.array([L / 2, 0, 0]))
    return m, {"W": W, "H": H, "w_t": wt, "perimeter": float(2 * wt + 4 * math.hypot((W - wt) / 2, H / 2)),
               "area": math.pi * D * D / 4}


def _orient(m: Mesh, centre) -> Mesh:
    """Flip facets whose normal points towards the component reference (convex parts: outward normals)."""
    F = m.F.copy()
    inward = np.einsum("fi,fi->f", m.n, m.c - centre) < 0
    F[inward] = F[inward][:, ::-1]
    return Mesh(m.V, F, m.name)


def lifting_surface(root_le, c_root, c_tip, semispan, sweep_le_deg, tc, dihedral_deg=0.0, side=+1, name="surface",
                    n_span=1):
    """Diamond-section straight-tapered panel; returns a closed Mesh (root face omitted — buried in the body)."""
    tl = math.tan(math.radians(sweep_le_deg))
    G = math.radians(dihedral_deg)
    ys = np.linspace(0, semispan, n_span + 1)
    V, F = [], []
    secs = []
    for y in ys:
        c = c_root + (c_tip - c_root) * y / semispan
        xle = root_le[0] + y * tl
        # section in local (x, eta=span coordinate in the surface plane, zeta=normal)
        pts = [(xle, 0.0), (xle + c / 2, tc * c / 2), (xle + c, 0.0), (xle + c / 2, -tc * c / 2)]
        idx = []
        for x, zeta in pts:
            yy = side * (y * math.cos(G) - zeta * math.sin(G))
            zz = root_le[2] + y * math.sin(G) + zeta * math.cos(G)
            V.append((x, root_le[1] + yy if side > 0 else root_le[1] + yy, zz))
            idx.append(len(V) - 1)
        secs.append(idx)
    for a, b in zip(secs[:-1], secs[1:]):
        for k in range(4):
            p, q = a[k], a[(k + 1) % 4]
            r, s = b[(k + 1) % 4], b[k]
            F += [(p, q, r), (p, r, s)]
    tip = secs[-1]
    F += [(tip[0], tip[1], tip[2]), (tip[0], tip[2], tip[3])]
    m = Mesh(np.array(V), F, name)
    # orient each facet outward relative to the local chord line through the panel mid-thickness
    F2 = m.F.copy()
    for fi in range(len(F2)):
        c = m.c[fi]
        # reference: point on the mid-plane below/above the facet centroid → use the panel mid-surface normal
        y_loc = abs(c[1] - root_le[1])
        nrm_plane = np.array([0.0, -side * math.sin(G), math.cos(G)])
        mid_z_offset = np.dot(c - np.array([c[0], root_le[1] + side * (y_loc / max(math.cos(G), 1e-9)) * 0, root_le[2]]),
                              nrm_plane)
        sgn = np.sign(np.dot(m.n[fi], nrm_plane))
        if fi >= len(F2) - 2:          # tip facets: outward = spanwise
            span_dir = np.array([0.0, side * math.cos(G), math.sin(G)])
            if np.dot(m.n[fi], span_dir) < 0:
                F2[fi] = F2[fi][::-1]
            continue
        # upper facets (positive offset along the plane normal) must have n·nrm_plane > 0
        upper = _is_upper(m.P[fi], root_le, side, G)
        if (upper and sgn < 0) or (not upper and sgn > 0):
            F2[fi] = F2[fi][::-1]
    return Mesh(m.V, F2, name)


def _is_upper(P, root_le, side, G):
    nrm_plane = np.array([0.0, -side * math.sin(G), math.cos(G)])
    off = (P - np.asarray(root_le)) @ nrm_plane
    return float(np.max(off)) > 1e-12 and float(np.min(off)) > -1e-12


def planform(S, b, sweep_le_deg, taper0, align):
    """Root/tip chords and TE sweep for fixed S and span: Λ_TE interpolates between the baseline-taper TE sweep and
    Λ_LE (align = 1 → parallel edges)."""
    s = b / 2
    cr0 = 2 * S / (b * (1 + taper0))
    ct0 = taper0 * cr0
    tl = math.tan(math.radians(sweep_le_deg))
    tte0 = tl - (cr0 - ct0) / s                 # TE sweep (tan) of the baseline taper with this LE sweep
    tte = tte0 + align * (tl - tte0)
    dc = s * (tl - tte)                         # c_root − c_tip
    cmean = S / b                               # (cr + ct)/2
    cr, ct = cmean + dc / 2, cmean - dc / 2
    return {"c_root": cr, "c_tip": ct, "taper": ct / cr, "sweep_te_deg": math.degrees(math.atan(tte)),
            "sweep_c4_deg": math.degrees(math.atan(tl - 0.25 * dc / s)),
            "sweep_c2_deg": math.degrees(math.atan(tl - 0.5 * dc / s)), "semispan": s}


def vtail_size(S_h, S_v, cant_deg):
    """Purser & Campbell (NACA Rep. 823, 1945): projected-area rule S_h = S cos²Γ, S_v = S sin²Γ → the V-tail
    area that satisfies both: S = max(S_h/cos²Γ, S_v/sin²Γ)."""
    g = math.radians(cant_deg)
    return max(S_h / math.cos(g) ** 2, S_v / math.sin(g) ** 2)


def aircraft_mesh(base: dict, shape: Shape, p=DEFAULTS) -> tuple[Mesh, dict]:
    """Whole faceted aircraft (fuselage + wing + V-tail) from the baseline description ``base`` (keys: S, b, taper,
    tc, L, D, S_h, S_v, tail_arm).

    P6: ``shape.L_scale`` / ``D_scale`` stretch the fuselage; ``wing_z_frac`` raises/lowers the wing root;
    ``x_wing_le_frac`` overrides the default LE station; ``sensor_x_frac`` is recorded in ``info`` for packaging.
    """
    L = base["L"] * float(shape.L_scale)
    D = base["D"] * float(shape.D_scale)
    fus, fi = fuselage_mesh(L, D, shape.chine_deg, p)
    pl = planform(base["S"], base["b"], shape.sweep_le_deg, base["taper"], shape.align)
    W = fi["W"]
    x_frac = p["x_wing_le_frac"] if shape.x_wing_le_frac is None else float(shape.x_wing_le_frac)
    x_le = x_frac * L
    y0 = W / 2
    z_wing = float(shape.wing_z_frac) * (fi["H"] / 2)
    # chord at the body side (planform defined on the centreline)
    tl = math.tan(math.radians(shape.sweep_le_deg))
    c_side = pl["c_root"] + (pl["c_tip"] - pl["c_root"]) * y0 / pl["semispan"]
    semi = pl["semispan"] - y0
    parts = [fus]
    for side in (+1, -1):
        parts.append(lifting_surface((x_le + y0 * tl, side * y0, z_wing), c_side, pl["c_tip"], semi,
                                     shape.sweep_le_deg, base["tc"], 0.0, side, "wing"))
    S_vt = vtail_size(base["S_h"], base["S_v"], shape.tail_cant_deg)
    Sp = S_vt / 2                                    # per panel
    bp = math.sqrt(p["tail_AR"] * Sp)                # panel span (along its own plane), AR per panel = b_p²/S_p
    crt = 2 * Sp / (bp * (1 + p["tail_taper"]))
    x_t = max(L - 1.05 * crt, x_le + pl["c_root"])       # ASSUMPTION: V-tail root TE ≈ at the fuselage base
    xs0, xs1 = p["tail_start"] * L, L
    sc_t = 1.0 if x_t <= xs0 else 1.0 + (p["tail_scale"] - 1.0) * (x_t - xs0) / (xs1 - xs0)
    z_t = 0.5 * fi["H"] * sc_t
    for side in (+1, -1):
        parts.append(lifting_surface((x_t, side * fi["w_t"] / 2 * sc_t * 0.5, z_t), crt, p["tail_taper"] * crt, bp,
                                     max(shape.sweep_le_deg, 15.0), p["tail_tc"], shape.tail_cant_deg, side, "vtail"))
    m = parts[0]
    for q in parts[1:]:
        m = m.merged(q, "aircraft")
    info = {"planform": pl, "fuselage": fi, "S_vtail": S_vt, "tail_panel_span": bp, "tail_c_root": crt,
            "L": L, "D": D, "x_wing_le": x_le, "z_wing": z_wing,
            "sensor_x": float(shape.sensor_x_frac) * L,
            "wet": {"fuselage": float(fus.area.sum()), "wing": float(sum(q.area.sum() for q in parts[1:3])),
                    "vtail": float(sum(q.area.sum() for q in parts[3:]))}}
    m.info = info
    return m, info
