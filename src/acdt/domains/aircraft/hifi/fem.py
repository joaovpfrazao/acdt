"""Phase 4 FEM: CalculiX shell model of the Phase 3 wing box — static stresses at ultimate load, linear
buckling (*BUCKLE) and normal modes (*FREQUENCY) — compared with the Phase 3 box (Farrar/Needham/Kuhn sizing,
Bredt–Batho GJ, two-cover EI).

Model (one semispan, clamped at the fuselage side y0 = D/2 as the Phase 3 aeroelastic model):
* two-spar box, flat covers at ±h/2 about the chord plane (h, w, spar x/c of Phase 3), LE sweep of the wing;
* S8R shells: covers (skin t_s per rib bay), spar webs (t_w), ribs at the Phase 3 rib pitch (t = t_min_web);
* metal: discrete stringers, B32 beams, equal-area rectangular section (A_st = (t̄ − t_s)·pitch, depth ≤ 0.2 h —
  ASSUMPTION replacing the Z section), offset inside the cover; count from the root stringer pitch, constant
  along the span (the bay thicknesses carry the taper);
* CFRP: sandwich covers/webs (*SHELL SECTION, COMPOSITE: face / core / face), UD spar caps as B32 beams;
* loads: Phase 3 net running load (lift − inertia) × 1.5, lift at c/4 and q c² cm0 at V_D resolved onto the
  two spars, inertia at mid-box. That is the shear centre of this rectangle (equal webs, no D-nose).
  ``beam.torque`` / ``box.GJ`` after ``elastic_axis='section'`` are the Phase 5 multi-cell pair (shear
  centre ``x_sc/c``, GJ with the D-nose). The tip-twist comparison uses the mid-box torque and the
  Phase 3 Bredt–Batho GJ kept in ``details['GJ_phase3']`` (Megson Eq. 18.4);
* modes: structure + the rest of the wing mass (wing item − FEM box mass) as nodal masses so that each section
  has the Phase 3 strip-model mass, c.g. and inertia (m ∝ c, x_cg, I_cg = m c²/12), the aft mass on stiff truss
  arms — like-for-like with the Phase 3 flutter estimate.

CalculiX: G. Dhondt, *The Finite Element Method for Three-Dimensional Thermomechanical Applications* (Wiley 2004),
GPL-2, called as an external executable. Buckling of stiffened panels: Bruhn C5/C7, Niu Ch. 14.

The Windows ``ccx_dynamic`` 2.23 binary defaults to PaStiX 6.4. On this wing box that static factorisation
is about 10³ too small (tip ~10⁻⁶ m). The same deck with ``SOLVER=SPOOLES`` (CalculiX User's Manual,
keywords ``*STATIC`` and ``*BUCKLE``, parameter SOLVER) gives a tip of 0.155 m, matching a Linux CalculiX
2.23 SPOOLES run of the same loads. ``*FREQUENCY`` is left on the default solver: those eigenvalues already
agreed with the beam.

``*BUCKLE`` scales only the load written inside that step. A previous ``*STATIC`` step is removed
(User's Manual, keyword ``*BUCKLE``); it is not the preload unless ``*STEP, PERTURBATION`` is set, and
that is a different problem. The 2.23 solver prints ``sigma=1`` and does not apply the manual's check
``5σ < λ < 50000σ`` (the shift stays 1; Dhondtguido/CalculiX issue 74). Four factors sitting on that
shift are not the lowest eigenvalue. :func:`reliable_buckling_factors` divides the reference load by
``s`` until the lowest factor is off the shift, then reports ``λ/s`` on the ultimate load. Asking for
1 mode, or tightening the accuracy from ``1e-3``, did not move a factor that the shift had already
replaced. The same UAV deck with ``OMP_NUM_THREADS=12`` returned a cluster about 1 (0.85–2.2, or
0.98–1.02); with one thread it returned 1.871, 2.179, 2.233, 2.588. Buckling therefore runs on one
thread. The static step stays on several threads: that factorisation matched the beam."""
from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..aero.interfaces import ToolNotAvailable
from . import tools

CCX_REF = "CalculiX 2.x (Dhondt 2004), S8R shells / B32 beams"


@dataclass
class BoxMesh:
    nodes: np.ndarray                 # (N, 3)
    shells: dict                      # elset -> list of 8-node connectivities (0-based)
    beams: dict                       # elset -> list of 3-node connectivities
    shell_props: dict                 # elset -> dict(kind, t or layers)
    beam_props: dict                  # elset -> dict(a, b, offset, material)
    root: list                        # node ids at y0
    spar_lines: dict                  # 'f_up','f_lo','r_up','r_lo' -> list of node ids along span (fine grid)
    y: np.ndarray                     # fine spanwise grid
    x_f: np.ndarray                   # front-spar x at each fine station
    x_r: np.ndarray
    h: np.ndarray
    rib_iy: list                      # fine-grid index of the ribs
    meta: dict = field(default_factory=dict)


def _interp(box_y, arr, y):
    a = np.asarray(arr, float)
    a = np.where(np.isfinite(a), a, np.nan)
    m = np.isfinite(a)
    return np.interp(y, np.asarray(box_y)[m], a[m])


def build_box_mesh(res, ds: float | None = None, n_cb: int = 2, n_h: int = 4) -> BoxMesh:
    """Structured S8R/B32 mesh of the Phase 3 box. ``ds`` spanwise element size (default ≈ root stringer pitch for
    metal, c_root/12 for CFRP), ``n_cb`` elements per stringer bay chordwise, ``n_h`` across the web height."""
    from ..structures import MATERIALS, chord_at

    w = res.config.wing
    box = res.structures.box
    det = box.details
    m = next((v for v in MATERIALS.values() if v["name"] == box.material), None)
    ext = (res.spec.assumptions.get("structures") or {}).get("material")
    if m is None and isinstance(ext, dict) and ext.get("name") == box.material:
        m = ext                       # external material in structures form (acdt.ai.external)
    if m is None:
        raise ValueError(f"material {box.material!r} not in MATERIALS")
    composite = "E_cap" in m
    s = w.span / 2
    y0 = 0.5 * res.config.fuselage.max_diameter if res.config.fuselage else 0.0
    L = w.box.rib_pitch or 0.6 * w.mac
    n_bays = max(1, math.ceil((s - y0) / L - 1e-6))
    y_rib = np.linspace(y0, s, n_bays + 1)
    pitch0 = float(det["stringer_pitch"][0]) if not composite else math.nan
    if ds is None:
        ds = pitch0 if not composite else chord_at(w, np.array([y0]))[0] / 12
    n_per_bay = max(2, math.ceil(L / ds))
    yf = [y0]
    for k in range(n_bays):
        yf += list(np.linspace(y_rib[k], y_rib[k + 1], 2 * n_per_bay + 1)[1:])
    yf = np.array(yf)
    rib_iy = [k * 2 * n_per_bay for k in range(n_bays + 1)]
    c = chord_at(w, yf)
    xle = (yf - 0.0) * math.tan(w.sweep_at(0.0))
    x_f, x_r = xle + w.box.front_spar_xc * c, xle + w.box.rear_spar_xc * c
    h = _interp(box.y, box.h_box, yf)
    w_root = float(_interp(box.y, box.w_box, np.array([y0]))[0])
    if composite:
        n_st, n_c = 0, 4 * n_cb
    else:
        n_st = max(1, int(round(w_root / pitch0)) - 1)
        n_c = (n_st + 1) * n_cb
    nx, nz, ny = 2 * n_c + 1, 2 * n_h + 1, len(yf)
    key, coords = {}, []

    def node(p):
        k = (round(p[0], 7), round(p[1], 7), round(p[2], 7))
        if k not in key:
            key[k] = len(coords)
            coords.append(p)
        return key[k]

    # fine grids (parametric) -> node ids
    up = np.zeros((ny, nx), int)
    lo = np.zeros((ny, nx), int)
    wf = np.zeros((ny, nz), int)
    wr = np.zeros((ny, nz), int)
    for j in range(ny):
        for i in range(nx):
            x = x_f[j] + (x_r[j] - x_f[j]) * i / (nx - 1)
            up[j, i] = node((x, yf[j], h[j] / 2))
            lo[j, i] = node((x, yf[j], -h[j] / 2))
        for i in range(nz):
            z = -h[j] / 2 + h[j] * i / (nz - 1)
            wf[j, i] = node((x_f[j], yf[j], z))
            wr[j, i] = node((x_r[j], yf[j], z))
    ribs = {}
    for k, j in enumerate(rib_iy):
        g = np.zeros((nx, nz), int)
        for a in range(nx):
            for b in range(nz):
                g[a, b] = node((x_f[j] + (x_r[j] - x_f[j]) * a / (nx - 1), yf[j], -h[j] / 2 + h[j] * b / (nz - 1)))
        ribs[k] = g

    def quads(G, flip=False):
        out = []
        for a in range(0, G.shape[0] - 1, 2):
            for b in range(0, G.shape[1] - 1, 2):
                n1, n2, n3, n4 = G[a, b], G[a, b + 2], G[a + 2, b + 2], G[a + 2, b]
                m5, m6, m7, m8 = G[a, b + 1], G[a + 1, b + 2], G[a + 2, b + 1], G[a + 1, b]
                e = [n1, n2, n3, n4, m5, m6, m7, m8]
                if flip:
                    e = [n1, n4, n3, n2, m8, m7, m6, m5]
                out.append((a // 2, e))
        return out

    shells, sprops = {}, {}
    bay_of = lambda a: min(n_bays - 1, (a * 2) // (2 * n_per_bay))  # noqa: E731  (element row -> rib bay)
    y_mid = 0.5 * (y_rib[:-1] + y_rib[1:])
    t_up = _interp(box.y, det["skin_upper"], y_mid)
    t_lo = _interp(box.y, det["skin_lower"], y_mid)
    t_w = _interp(box.y, box.web_t, y_mid)
    core = _interp(box.y, det["core_t"], y_mid) if composite else np.zeros(n_bays)
    wcore = _interp(box.y, det["web_core_t"], y_mid) if composite else np.zeros(n_bays)
    for name, G, flip in (("UP", up, False), ("LO", lo, True), ("WF", wf, True), ("WR", wr, False)):
        for a, e in quads(G, flip):
            k = bay_of(a)
            shells.setdefault(f"{name}{k}", []).append(e)
    for k, G in ribs.items():
        shells.setdefault("RIB", []).extend(e for _, e in quads(G))
    for k in range(n_bays):
        if composite:
            for nm, tf, tc in (("UP", t_up[k] / 2, core[k]), ("LO", t_lo[k] / 2, core[k]),
                               ("WF", t_w[k] / 2, wcore[k]), ("WR", t_w[k] / 2, wcore[k])):
                sprops[f"{nm}{k}"] = {"layers": [(tf, "FACE")] + ([(tc, "CORE")] if tc > 0 else []) + [(tf, "FACE")]}
        else:
            sprops[f"UP{k}"] = {"t": t_up[k]}
            sprops[f"LO{k}"] = {"t": t_lo[k]}
            sprops[f"WF{k}"] = sprops[f"WR{k}"] = {"t": t_w[k]}
    sprops["RIB"] = {"t": m["t_min_web"], "layers": None} if not composite else {"t": m["t_min_web"]}
    # beams
    beams, bprops = {}, {}
    tb_u = _interp(box.y, det["cover_tbar_upper"], y_mid)
    tb_l = _interp(box.y, det["cover_tbar_lower"], y_mid)
    h_mid = np.interp(y_mid, yf, h)
    if not composite:
        cols = [kk * 2 * n_cb for kk in range(1, n_st + 1)]
        w_mid = np.interp(y_mid, yf, x_r - x_f)
        for k in range(n_bays):
            # CalculiX: the section centroid lies at −OFFSET1·a along beam axis 1 (= +z here), so +1 puts the
            # upper stringer below (inside) the upper skin and −1 the lower one above it (Phase 5 fix: the signs
            # were reversed, placing the stringers outside the box)
            for nm, tb, ts, sgn in (("SU", tb_u[k], t_up[k], +1), ("SL", tb_l[k], t_lo[k], -1)):
                A = max((tb - ts) * w_mid[k] / (n_st + 1), 1e-7)
                a = min(A / (1.05 * ts), 0.2 * h_mid[k])
                b = A / a
                bprops[f"{nm}{k}"] = {"a": a, "b": b, "offset1": sgn * (0.5 + ts / (2 * a)), "mat": "MAT"}
        for j in range(0, ny - 2, 2):
            k = bay_of(j // 2)
            for col in cols:
                beams.setdefault(f"SU{k}", []).append([up[j, col], up[j + 1, col], up[j + 2, col]])
                beams.setdefault(f"SL{k}", []).append([lo[j, col], lo[j + 1, col], lo[j + 2, col]])
    else:
        Acap = _interp(box.y, box.cap_area, y_mid)
        for k in range(n_bays):
            a = math.sqrt(max(Acap[k] / 2, 1e-8))   # Phase 3 A is the total per cover, two caps (spars) each
            for nm, sgn in (("CU", +1), ("CL", -1)):   # inside the box (see the stringer note above)
                bprops[f"{nm}{k}"] = {"a": a, "b": a, "offset1": sgn * 0.5, "mat": "CAP"}
        for j in range(0, ny - 2, 2):
            k = bay_of(j // 2)
            for col in (0, nx - 1):
                beams.setdefault(f"CU{k}", []).append([up[j, col], up[j + 1, col], up[j + 2, col]])
                beams.setdefault(f"CL{k}", []).append([lo[j, col], lo[j + 1, col], lo[j + 2, col]])
    root = sorted(set(up[0].tolist() + lo[0].tolist() + wf[0].tolist() + wr[0].tolist() + ribs[0].ravel().tolist()))
    spar = {"f_up": up[:, 0].tolist(), "f_lo": lo[:, 0].tolist(), "r_up": up[:, -1].tolist(), "r_lo": lo[:, -1].tolist(),
            "f_mid": wf[:, n_h].tolist(), "r_mid": wr[:, n_h].tolist()}
    meta = {"material": m, "composite": composite, "n_stringers_per_cover": n_st, "n_bays": n_bays, "rib_pitch": L,
            "y0": y0, "ds": float(ds), "y_rib": y_rib.tolist(), "n_c": n_c, "n_h": n_h}
    return BoxMesh(np.array(coords), shells, beams, sprops, bprops, root, spar, yf, x_f, x_r, h, rib_iy, meta)


def fem_mass(mesh: BoxMesh) -> float:
    """Structural mass of the FEM semispan (shells + beams) [kg]."""
    m = mesh.meta["material"]
    X = mesh.nodes
    tot = 0.0
    for es, els in mesh.shells.items():
        p = mesh.shell_props[es]
        if p.get("layers"):
            rho_t = sum(t * (m["rho"] if mat == "FACE" else m["core"]["rho"]) for t, mat in p["layers"])
        else:
            rho_t = p["t"] * m["rho"]
        for e in els:
            P = X[e[:4]]
            A = 0.5 * np.linalg.norm(np.cross(P[2] - P[0], P[3] - P[1]))
            tot += rho_t * A
    for es, els in mesh.beams.items():
        p = mesh.beam_props[es]
        for e in els:
            tot += m["rho"] * p["a"] * p["b"] * np.linalg.norm(X[e[2]] - X[e[0]])
    return float(tot)


# -------------------------------------------------------------------------------- loads and masses
def meshed_box_gj(box) -> np.ndarray:
    """Bredt–Batho GJ of the rectangle that is actually meshed (Megson Eq. 18.4).

    After ``elastic_axis='section'``, ``box.GJ`` is the Phase 5 multi-cell stiffness and the rectangular-cell
    value is kept as ``details['GJ_phase3']``. Without that substitution ``box.GJ`` is already Bredt."""
    gj = (box.details or {}).get("GJ_phase3", box.GJ)
    return np.asarray(gj, float)


def torque_about_meshed_box(res, y) -> np.ndarray:
    """Limit torque [N·m] about the mid-box, the shear centre of the meshed rectangle.

    Equal spar webs put that centre at mid-width (Megson 2017 §17). ``beam.torque`` is about the section
    shear centre once ``details['x_sc_c']`` exists. The pitching-moment couple is the same about any parallel
    axis; only the lift changes arm: T_mid = T_section + ∫_y^tip ℓ (x_mid − x_sc) c dη. Inertia is applied
    at the mid-box, so it adds none."""
    from ..structures import _cum_from_tip

    sr = res.structures
    ld = sr.load
    box = sr.box
    xb = res.config.wing.box
    x_mid = 0.5 * (xb.front_spar_xc + xb.rear_spar_xc)
    T = np.asarray(sr.beam.torque, float).copy()
    xsc = (box.details or {}).get("x_sc_c")
    if xsc is not None:
        dx = x_mid - np.interp(ld.y, box.y, np.asarray(xsc, float))
        T = T + _cum_from_tip(ld.y, ld.lift * dx * ld.chord)
    return np.interp(np.asarray(y, float), ld.y, T)


def nodal_loads(res, mesh: BoxMesh, factor: float = 1.5) -> dict:
    """Ultimate nodal z-forces on the spar cap lines (fine stations, tributary length), reproducing the Phase 3
    V, M and the torque about the mid-box (lift at c/4 + q c² cm0 at V_D, inertia at mid-box)."""
    from ..structures import RHO0

    sr = res.structures
    ld = sr.load
    w = res.config.wing
    yf = mesh.y
    lift = np.interp(yf, ld.y, ld.lift)
    iner = np.interp(yf, ld.y, ld.inertia)
    c = np.interp(yf, ld.y, ld.chord)
    q = 0.5 * RHO0 * sr.vn.VD**2
    # cm0 used by Phase 3 recovered from its root torque: T0 = ∫ l (x_ea − ¼) c dy + q cm0 ∫ c² dy
    xsc = res.structures.box.details.get("x_sc_c")       # Phase 5 shear-centre axis (else mid-box)
    x_ea = np.interp(ld.y, res.structures.box.y, xsc) if xsc is not None else \
        0.5 * (w.box.front_spar_xc + w.box.rear_spar_xc)
    T_lift = np.trapezoid(ld.lift * (x_ea - 0.25) * ld.chord, ld.y)
    cm0 = (float(sr.beam.torque[0]) - T_lift) / (q * np.trapezoid(ld.chord**2, ld.y))
    trib = np.zeros_like(yf)
    dy = np.diff(yf)
    trib[:-1] += dy / 2
    trib[1:] += dy / 2
    xle = yf * math.tan(w.sweep_at(0.0))
    x_qc = xle + 0.25 * c
    d = mesh.x_r - mesh.x_f
    F_l, F_i, Mp = lift * trib, iner * trib, q * c**2 * cm0 * trib
    Fr = F_l * (x_qc - mesh.x_f) / d - Mp / d - 0.5 * F_i
    Ff = F_l - F_l * (x_qc - mesh.x_f) / d + Mp / d - 0.5 * F_i
    loads = {}
    for j in range(len(yf)):
        for key, F in (("f_up", Ff[j]), ("f_lo", Ff[j]), ("r_up", Fr[j]), ("r_lo", Fr[j])):
            n = mesh.spar_lines[key][j]
            loads[n] = loads.get(n, 0.0) + factor * F / 2
    Ftot = factor * (Ff + Fr)
    y0 = yf[0]
    # Torque of these forces about the mid-box (not the Phase 5 section shear centre). The two axes differ
    # by the lift arm (x_sc − x_mid)·c, which is what made T0_fem disagree with beam.torque.
    x_box = 0.5 * (mesh.x_f + mesh.x_r)
    info = {"cm0_phase3": float(cm0), "V0_fem_N": float(Ftot.sum()),
            "V0_phase3_N": float(factor * np.interp(y0, sr.beam.y, sr.beam.shear)),
            "M0_fem_Nm": float(np.sum(Ftot * (yf - y0))),
            "M0_phase3_Nm": float(factor * np.interp(y0, sr.beam.y, sr.beam.moment)),
            "T0_fem_Nm": float(np.sum(factor * (Ff * (x_box - mesh.x_f) - Fr * (mesh.x_r - x_box)))),
            "T0_phase3_Nm": float(factor * float(np.asarray(torque_about_meshed_box(res, y0))))}
    return loads, info


def section_masses(res, mesh: BoxMesh, x_cg_c: float = 0.5) -> tuple[list, dict]:
    """Non-structural nodal masses that give each rib-bay section the Phase 3 strip-model mass m(y) ∝ c,
    c.g. at ``x_cg_c`` c and I_cg = m c²/12 (Wright & Cooper uniform section). Two masses per rib: m_a on the
    front-spar web, m_b on an aft point x_b (truss arm). Returns (extra nodes, {node: mass})."""
    from ..structures import chord_at

    w = res.config.wing
    wm = res.structures.wing_mass_raymer or res.structures.box.mass
    if res.weights is not None:
        wm = next((it.mass for it in res.weights.items if it.key == "wing"), wm)
    y0, s = mesh.meta["y0"], w.span / 2
    yy = np.linspace(y0, s, 400)
    cc = chord_at(w, yy)
    mpl = 0.5 * wm * cc / np.trapezoid(cc, yy)          # as aeroelasticity.strip_model: half-wing mass ∝ c on y0..s
    m_fem_total = fem_mass(mesh)
    ribs = mesh.rib_iy
    yr = mesh.y[ribs]
    extra, masses = [], {}
    # strip mass assigned to the rib stations (tributary between mid-bays), outboard of y0
    edges = np.r_[yr[0], 0.5 * (yr[1:] + yr[:-1]), yr[-1]]
    struct_share = m_fem_total * np.diff(edges) / (yr[-1] - yr[0])
    deficit = 0.0
    for k, j in enumerate(ribs):
        sel = (yy >= edges[k]) & (yy <= edges[k + 1])
        m_sec = float(np.trapezoid(mpl[sel], yy[sel])) if sel.sum() > 1 else 0.0
        c = chord_at(w, np.array([mesh.y[j]]))[0]
        xle = mesh.y[j] * math.tan(w.sweep_at(0.0))
        x_cg = xle + x_cg_c * c
        I_target = m_sec * c**2 / 12
        mb_ = struct_share[k]
        xb_ = 0.5 * (mesh.x_f[j] + mesh.x_r[j])
        Ib_ = mb_ * (mesh.x_r[j] - mesh.x_f[j]) ** 2 / 12
        mn = m_sec - mb_
        if mn <= 0:
            deficit += -mn
            continue
        xa = mesh.x_f[j]
        # unknowns m_a, m_b, x_b: mass, first and second moments about x_cg
        S1 = m_sec * x_cg - mb_ * xb_
        S2 = I_target - Ib_ - mb_ * (xb_ - x_cg) ** 2
        # m_a (xa - x_cg)^2 + m_b (x_b - x_cg)^2 = S2, m_a xa + m_b x_b = S1, m_a + m_b = mn
        best = None
        for frac in np.linspace(0.02, 0.98, 97):
            ma, mbn = frac * mn, (1 - frac) * mn
            xb = (S1 - ma * xa) / mbn
            r = ma * (xa - x_cg) ** 2 + mbn * (xb - x_cg) ** 2 - S2
            if best is None or abs(r) < abs(best[0]):
                best = (r, ma, mbn, xb)
        _, ma, mbn, xb = best
        # front mass on the spar/cover/rib corners (stiff in all directions — a point mass on the thin web
        # mid-height would give spurious local web modes)
        for key in ("f_up", "f_lo"):
            nf = mesh.spar_lines[key][j]
            masses[nf] = masses.get(nf, 0.0) + ma / 2
        jn = j - 1 if j > 0 else j + 1
        extra.append({"x": float(xb), "y": float(mesh.y[j]), "z": 0.0, "mass": float(mbn), "rib": k,
                      "anchors": [mesh.spar_lines["r_up"][j], mesh.spar_lines["r_lo"][j],
                                  mesh.spar_lines["r_up"][jn], mesh.spar_lines["r_lo"][jn]]})
    meta = {"wing_mass_item_kg": float(wm), "fem_struct_semispan_kg": m_fem_total, "deficit_kg": deficit}
    return extra, masses, meta


# -------------------------------------------------------------------------------- CalculiX deck
def _materials(m: dict) -> str:
    out = [f"*MATERIAL, NAME=MAT\n*ELASTIC\n{m['E']:.6e}, {m['nu']}\n*DENSITY\n{m['rho']}\n"]
    if "E_cap" in m:
        out.append(f"*MATERIAL, NAME=FACE\n*ELASTIC\n{m['E']:.6e}, {m['nu']}\n*DENSITY\n{m['rho']}\n")
        cr = m["core"]
        nu_c = min(max(cr["E"] / (2 * cr["G"]) - 1, 0.0), 0.45)
        out.append(f"*MATERIAL, NAME=CORE\n*ELASTIC\n{cr['E']:.6e}, {nu_c:.3f}\n*DENSITY\n{cr['rho']}\n")
        out.append(f"*MATERIAL, NAME=CAP\n*ELASTIC\n{m['E_cap']:.6e}, 0.3\n*DENSITY\n{m['rho']}\n")
    out.append("*MATERIAL, NAME=STIFF\n*ELASTIC\n2.1e14, 0.3\n*DENSITY\n1e-6\n")
    return "".join(out)


def write_deck(mesh: BoxMesh, path: Path, step: str, loads: dict | None = None, masses: dict | None = None,
               extra: list | None = None, n_modes: int = 10) -> Path:
    """``step``: 'static' | 'buckle' | 'frequency'."""
    X = mesh.nodes
    L = ["*HEADING\nacdt Phase 4 wing box\n*NODE, NSET=NALL\n"]
    L += [f"{i + 1}, {p[0]:.7f}, {p[1]:.7f}, {p[2]:.7f}\n" for i, p in enumerate(X)]
    nid = len(X)
    eid = 0
    extra_ids = []
    if extra:
        for ex in extra:
            nid += 1
            ex["id"] = nid
            L.append(f"{nid}, {ex['x']:.7f}, {ex['y']:.7f}, {ex['z']:.7f}\n")
            extra_ids.append(nid)
    for es, els in mesh.shells.items():
        L.append(f"*ELEMENT, TYPE=S8R, ELSET={es}\n")
        for e in els:
            eid += 1
            L.append(f"{eid}, " + ", ".join(str(n + 1) for n in e) + "\n")
    for es, els in mesh.beams.items():
        L.append(f"*ELEMENT, TYPE=B32, ELSET={es}\n")
        for e in els:
            eid += 1
            L.append(f"{eid}, " + ", ".join(str(n + 1) for n in e) + "\n")
    if extra:
        L.append("*ELEMENT, TYPE=T3D2, ELSET=ARMS\n")
        for ex in extra:
            for a in ex["anchors"]:
                eid += 1
                L.append(f"{eid}, {a + 1}, {ex['id']}\n")
    mass_nodes = dict(masses or {})
    if step == "frequency" and (mass_nodes or extra):
        L.append("*ELEMENT, TYPE=MASS, ELSET=PMASS\n")
        mlist = []
        for n, mv in mass_nodes.items():
            eid += 1
            L.append(f"{eid}, {n + 1}\n")
            mlist.append((eid, mv))
        for ex in extra or []:
            eid += 1
            L.append(f"{eid}, {ex['id']}\n")
            mlist.append((eid, ex["mass"]))
        for e, mv in mlist:
            L.append(f"*ELSET, ELSET=PM{e}\n{e}\n*MASS, ELSET=PM{e}\n{mv:.6e}\n")
    L.append(_materials(mesh.meta["material"]))
    for es, p in mesh.shell_props.items():
        if es not in mesh.shells:
            continue
        if p.get("layers"):
            L.append(f"*SHELL SECTION, ELSET={es}, COMPOSITE\n")
            L += [f"{t:.6e},, {mat}\n" for t, mat in p["layers"]]
        else:
            mat = "FACE" if mesh.meta["composite"] else "MAT"
            L.append(f"*SHELL SECTION, ELSET={es}, MATERIAL={mat}\n{p['t']:.6e}\n")
    for es, p in mesh.beam_props.items():
        if es not in mesh.beams:
            continue
        L.append(f"*BEAM SECTION, ELSET={es}, MATERIAL={p['mat']}, SECTION=RECT, OFFSET1={p['offset1']:.4f}\n"
                 f"{p['a']:.6e}, {p['b']:.6e}\n0., 0., 1.\n")
    if extra:
        L.append("*SOLID SECTION, ELSET=ARMS, MATERIAL=STIFF\n1e-3\n")
    L.append("*NSET, NSET=ROOT\n" + "".join(f"{n + 1},\n" for n in mesh.root))
    L.append("*BOUNDARY\nROOT, 1, 6\n")
    sets = {k: v for k, v in mesh.spar_lines.items()}
    for k, v in sets.items():
        L.append(f"*NSET, NSET=L_{k.upper()}\n" + "".join(f"{n + 1},\n" for n in v))
    if step == "static":
        # SPOOLES, not the PaStiX default of the Windows ccx_dynamic build (see module docstring).
        L.append("*STEP\n*STATIC, SOLVER=SPOOLES\n*CLOAD\n" + "".join(f"{n + 1}, 3, {F:.6e}\n" for n, F in loads.items()))
        L.append("*NODE PRINT, NSET=L_F_UP\nU\n*NODE PRINT, NSET=L_R_UP\nU\n")
        L.append("*EL PRINT, ELSET=" + ",".join([]) if False else "")
        for es in list(mesh.shells) + list(mesh.beams):
            if es.startswith(("UP", "LO", "SU", "SL", "CU", "CL")):
                L.append(f"*EL PRINT, ELSET={es}\nS\n")
        L.append("*END STEP\n")
    elif step == "buckle":
        # 4 modes and accuracy 1e-3. On ccx 2.23 neither one moves a factor that has fallen on the
        # shift σ=1; reliable_buckling_factors scales ``loads`` and divides the factor back.
        L.append("*STEP\n*BUCKLE, SOLVER=SPOOLES\n4, 1e-3\n*CLOAD\n" + "".join(f"{n + 1}, 3, {F:.6e}\n" for n, F in loads.items()))
        L.append("*NODE FILE\nU\n*END STEP\n")
    elif step == "frequency":
        L.append(f"*STEP\n*FREQUENCY\n{n_modes}\n")
        L.append("*NODE PRINT, NSET=L_F_MID\nU\n*NODE PRINT, NSET=L_R_MID\nU\n*NODE FILE\nU\n*END STEP\n")
    path.write_text("".join(L))
    return path


# -------------------------------------------------------------------------------- .dat parsing
_FLOAT = r"[-+]?\d*\.?\d+(?:[EeDd][-+]?\d+)?"


def parse_dat_blocks(path: Path) -> list[tuple[str, list[list[float]]]]:
    blocks, cur, head = [], None, None
    for line in Path(path).read_text(errors="replace").splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r"^[a-z]", s) and ("for set" in s or "time" in s):
            if cur is not None:
                blocks.append((head, cur))
            head, cur = s, []
            continue
        if cur is not None:
            vals = re.findall(_FLOAT, s)
            if vals and re.match(r"^\d", s):
                cur.append([float(v.replace("D", "E").replace("d", "e")) for v in vals])
    if cur is not None:
        blocks.append((head, cur))
    return blocks


def _is_shift_echo(factors: list[float]) -> bool:
    """True when several reported factors sit on the ARPACK shift σ = 1.

    A real cluster of panel modes near the design load has the same signature, so a caller that
    sees this must repeat the solve with a smaller reference load and divide the factors back.
    """
    if len(factors) < 3:
        return False
    lo, hi = min(factors), max(factors)
    return lo > 0.8 and hi < 1.25 and hi / lo < 1.20


def reliable_buckling_factors(solve, max_tries: int = 4) -> dict:
    """Lowest ``*BUCKLE`` factors on the ultimate load, not on the shift σ = 1.

    ``solve(scale)`` writes the ultimate loads divided by ``scale`` and returns ``(rc, factors)``.
    CalculiX 2.23 keeps σ = 1 (the log line ``sigma=1``). Factors well below that shift are skipped
    and a 4-mode request then prints a cluster about 1 (verified here on a square plate whose
    Timoshenko k = 4 factor is 0.05). Dividing the reference load by ``s`` multiplies every factor
    by ``s``. Repeat until the lowest factor is at least 0.5 and is not that cluster, then divide
    by ``s``. The same plate at a true factor of 1.83 is returned on the first solve: the number of
    modes and the accuracy are not what hides the eigenvalue.
    """
    scale = 1.0
    raw: list[float] = []
    rc = 0
    for _ in range(max_tries):
        rc, raw = solve(scale)
        raw = list(raw or [])
        if rc != 0 or not raw:
            break
        lo = min(raw)
        if lo >= 0.5 and not _is_shift_echo(raw):
            break
        nxt = scale * 20.0 / max(lo, 0.5)
        if nxt > 1e9 or nxt <= scale * 1.05:
            break
        scale = nxt
    return {"factors": [f / scale for f in raw], "scale": scale, "raw": raw, "rc": rc}


def parse_buckling_factors(path: Path) -> list[float]:
    txt = Path(path).read_text(errors="replace")
    i = txt.find("B U C K L I N G   F A C T O R")
    if i < 0:
        return []
    out = []
    for line in txt[i:].splitlines()[1:]:
        v = line.split()
        if len(v) == 2 and v[0].isdigit():
            out.append(float(v[1]))
        elif out and not v:
            break
    return out


def parse_frequencies(path: Path) -> list[float]:
    txt = Path(path).read_text(errors="replace")
    i = txt.find("E I G E N V A L U E   O U T P U T")
    out = []
    if i < 0:
        return out
    for line in txt[i:].splitlines():
        v = line.split()
        if len(v) == 5 and v[0].isdigit():
            out.append(float(v[3]))  # cycles/time
        elif out and len(v) and not v[0].isdigit():
            break
    return out


def parse_modes(path: Path, mesh: BoxMesh, n_modes: int) -> dict:
    """Mass-normalised mode shapes (CalculiX normalises φᵀMφ = 1) on the front/rear spar mid-height lines:
    returns y, x_f, x_r and for each mode the (vx, vz) of both lines + a heave/twist/in-plane classification."""
    blocks = [(h, r) for h, r in parse_dat_blocks(path) if h.startswith("displacements")]
    idx_f = {n: i for i, n in enumerate(mesh.spar_lines["f_mid"])}
    idx_r = {n: i for i, n in enumerate(mesh.spar_lines["r_mid"])}
    ny = len(mesh.y)
    shapes, cls = [], []
    for k in range(min(n_modes, len(blocks) // 2)):
        F = np.zeros((ny, 3))
        R = np.zeros((ny, 3))
        for row in blocks[2 * k][1]:
            F[idx_f[int(row[0]) - 1]] = row[1:4]
        for row in blocks[2 * k + 1][1]:
            R[idx_r[int(row[0]) - 1]] = row[1:4]
        d = mesh.x_r - mesh.x_f
        heave = 0.5 * (F[:, 2] + R[:, 2])
        twist = (F[:, 2] - R[:, 2]) / d
        inpl = 0.5 * (F[:, 0] + R[:, 0])
        cbar = d / 0.45
        meas = {"bending": np.abs(heave).max(), "torsion": (np.abs(twist) * cbar / 2).max(),
                "in-plane": np.abs(inpl).max()}
        t = max(meas, key=meas.get)
        # local (panel/rib) modes: small motion of the spar lines relative to the strongest global mode
        shapes.append({"wf": F[:, 2].tolist(), "wr": R[:, 2].tolist(), "uf": F[:, 0].tolist(), "ur": R[:, 0].tolist()})
        cls.append({"type": t, **{k_: float(v) for k_, v in meas.items()}})
    mx = max((max(c["bending"], c["torsion"], c["in-plane"]) for c in cls), default=1.0)
    for c in cls:
        if max(c["bending"], c["torsion"], c["in-plane"]) < 0.05 * mx:
            c["type"] = "local"
    return {"y": mesh.y.tolist(), "x_f": mesh.x_f.tolist(), "x_r": mesh.x_r.tolist(), "shapes": shapes,
            "classification": cls}


# -------------------------------------------------------------------------------- driver
def estimate(mesh: BoxMesh) -> tools.Budget:
    """S8R/B32 are expanded to C3D20R by CalculiX (×3 nodes): SPOOLES ≈ 1.5 kB per expanded DOF (measured
    order of magnitude); ARPACK buckling/modes ≈ 10× a static solve."""
    nodes = len(mesh.nodes) * 3
    dof = nodes * 3
    mem = 0.3 + dof * 1.5e-5
    t = dof / 2.0e5 * 2.0
    return tools.budget(mem, t)


def run_box_fem(res, work: str | Path, ds: float | None = None, force: bool = False,
                steps=("static", "buckle", "frequency")) -> dict:
    ccx = tools.find_exe("ccx")
    if ccx is None:
        raise ToolNotAvailable("CalculiX 'ccx' not found ($ACDT_HIFI_BIN or PATH)")
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    mesh = build_box_mesh(res, ds)
    b = estimate(mesh)
    out = {"nodes": len(mesh.nodes), "shells": sum(len(v) for v in mesh.shells.values()),
           "beams": sum(len(v) for v in mesh.beams.values()), "meta": {k: v for k, v in mesh.meta.items()
                                                                        if k != "material"},
           "budget": vars(b), "ref": CCX_REF, "notes": []}
    loads, linfo = nodal_loads(res, mesh)
    extra, masses, mmeta = section_masses(res, mesh)
    out["mass"], out["loads"] = mmeta, linfo
    for st in ("static", "buckle", "frequency"):
        write_deck(mesh, work / f"box_{st}.inp", st, loads, masses, [dict(e) for e in extra] if st == "frequency" else None)
    # The recorded command is relative to the case folder (parent of ``work``). The run below still
    # uses the absolute executable from find_exe; only the name is stored.
    case = Path(work).resolve().parent
    cd = tools.case_relative(work, case)
    exe = Path(ccx).name
    n_omp = min(8, tools.cores())
    cmds = {st: f"cd {cd} && OMP_NUM_THREADS={1 if st == 'buckle' else n_omp} {exe} box_{st}"
            for st in ("static", "buckle", "frequency")}
    out["commands"] = cmds
    if not b.run_here and not force:
        out["notes"].append(f"não corrido: {b.reason}")
        return out
    env = {"OMP_NUM_THREADS": str(min(8, tools.cores()))}
    t0 = time.time()
    buckle_meta = None
    for st in steps:
        if st == "buckle":
            buckle_env = dict(env, OMP_NUM_THREADS="1")

            def solve(scale, _loads=loads, _mesh=mesh, _work=work, _ccx=ccx, _env=buckle_env):
                scaled = {n: F / scale for n, F in _loads.items()}
                write_deck(_mesh, _work / "box_buckle.inp", "buckle", scaled)
                rc = tools.run([_ccx, "box_buckle"], _work, "box_buckle.log", env=_env, timeout=3600)
                dat = _work / "box_buckle.dat"
                fac = parse_buckling_factors(dat) if dat.exists() else []
                return rc, fac

            buckle_meta = reliable_buckling_factors(solve)
            if buckle_meta["rc"] != 0:
                out["notes"].append(f"buckle: ccx rc {buckle_meta['rc']} (ver box_buckle.log)")
            elif buckle_meta["scale"] != 1.0:
                out["notes"].append(
                    "encurvadura: a carga de referência foi dividida por "
                    f"{buckle_meta['scale']:.6g} para o fator sair do shift σ=1 do *BUCKLE; "
                    "λ à carga última é o fator do solver a dividir por essa escala")
        else:
            rc = tools.run([ccx, f"box_{st}"], work, f"box_{st}.log", env=env, timeout=3600)
            if rc != 0:
                out["notes"].append(f"{st}: ccx rc {rc} (ver box_{st}.log)")
    out["wall_s"] = time.time() - t0
    out.update(_post(res, mesh, work, loads))
    if buckle_meta is not None and buckle_meta["factors"]:
        # _post stored the solver's raw factors. Those belong to the scaled load.
        out["buckling_factors_ultimate"] = buckle_meta["factors"]
        out["buckling_load_scale"] = buckle_meta["scale"]
        out["buckling_factors_solver"] = buckle_meta["raw"]
        out["commands"]["buckle"] += (
            f"  # repeated until the factor leaves sigma=1; load scale {buckle_meta['scale']:.6g}; "
            "lambda_ult = lambda_solver/scale")
    (work / "fem_results.json").write_text(json.dumps(out, indent=1, default=float))
    return out


def _post(res, mesh: BoxMesh, work: Path, loads: dict) -> dict:
    """Compare FEM with Phase 3: tip deflection/twist (beam theory with the Phase 3 EI/GJ), cover stresses,
    buckling factor at ultimate, first bending/torsion frequencies (strip model)."""
    box = res.structures.box
    sr = res.structures
    r = {}
    dat = work / "box_static.dat"
    if dat.exists():
        blocks = parse_dat_blocks(dat)
        U = {}
        for head, rows in blocks:
            if head.startswith("displacements"):
                for row in rows:
                    U[int(row[0]) - 1] = row[1:4]
        jt = len(mesh.y) - 1
        fu, ru = mesh.spar_lines["f_up"][jt], mesh.spar_lines["r_up"][jt]
        if fu in U and ru in U:
            wt = 0.5 * (U[fu][2] + U[ru][2])
            th = math.degrees(math.atan2(U[fu][2] - U[ru][2], mesh.x_r[jt] - mesh.x_f[jt]))
            r["tip_w_fem_m"], r["tip_twist_fem_deg"] = wt, th
        # beam theory, clamped at y0, ultimate (factor 1.5). Bending stays on box.EI (the comparison the
        # bending test already uses). Torsion is the mid-box torque over the Phase 3 Bredt GJ of this
        # rectangle — not beam.torque / box.GJ, which after elastic_axis='section' are the multi-cell pair.
        y = mesh.y
        M = 1.5 * np.interp(y, sr.beam.y, sr.beam.moment)
        T = 1.5 * torque_about_meshed_box(res, y)
        EI = np.interp(y, box.y, box.EI)
        GJ = np.interp(y, box.y, meshed_box_gj(box))
        slope = np.r_[0, np.cumsum(0.5 * (M[1:] / EI[1:] + M[:-1] / EI[:-1]) * np.diff(y))]
        defl = np.r_[0, np.cumsum(0.5 * (slope[1:] + slope[:-1]) * np.diff(y))]
        twist = np.r_[0, np.cumsum(0.5 * (T[1:] / GJ[1:] + T[:-1] / GJ[:-1]) * np.diff(y))]
        r["tip_w_beam_m"], r["tip_twist_beam_deg"] = float(defl[-1]), float(math.degrees(twist[-1]))
        # cover stresses (mean σ_yy of the integration points per element set = membrane)
        sig = {}
        for head, rows in blocks:
            if head.startswith("stresses"):
                mset = re.search(r"for set (\S+)", head)
                if mset and rows:
                    a = np.array(rows)
                    sig[mset.group(1)] = float(np.mean(a[:, 3])) if a.shape[1] >= 8 else float("nan")
        r["sigma_yy_mean_MPa"] = {k: v / 1e6 for k, v in sig.items()}
        k0 = 0 if mesh.meta["n_bays"] == 1 else 1
        yb = 0.5 * (mesh.meta["y_rib"][k0] + mesh.meta["y_rib"][k0 + 1])
        if not mesh.meta["composite"]:
            s3 = float(np.interp(yb, box.y, box.details["sigma_cover"]))
            r["cover_bay"] = {"bay": k0, "y": yb, "sigma_phase3_MPa": s3 / 1e6,
                              "skin_fem_MPa": sig.get(f"UP{k0}".upper(), float("nan")) / 1e6,
                              "stringer_fem_MPa": sig.get(f"SU{k0}", float("nan")) / 1e6}
        else:
            r["cover_bay"] = {"bay": k0, "y": yb, "cap_fem_MPa": sig.get(f"CU{k0}", float("nan")) / 1e6,
                              "skin_fem_MPa": sig.get(f"UP{k0}", float("nan")) / 1e6,
                              "cap_allow_MPa": mesh.meta["material"]["sigma_cap"] / 1e6}
    bf = parse_buckling_factors(work / "box_buckle.dat") if (work / "box_buckle.dat").exists() else []
    r["buckling_factors_ultimate"] = bf
    fr = parse_frequencies(work / "box_frequency.dat") if (work / "box_frequency.dat").exists() else []
    r["frequencies_Hz"] = fr
    if fr:
        modes = parse_modes(work / "box_frequency.dat", mesh, len(fr))
        r["modes"] = modes
        r["mode_types"] = [m["type"] for m in modes["classification"]]
    if res.aeroelastic is not None:
        fl = res.aeroelastic.flutter
        r["strip_f_bending_Hz"], r["strip_f_torsion_Hz"] = fl["f_bending_Hz"], fl["f_torsion_Hz"]
    return r
