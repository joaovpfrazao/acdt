"""Phase 5 in-house FE of the wing box (acdt.core.fem: Q4 QM6/MITC4 shells + 2-node offset beams).

* :func:`from_phase4` converts the Phase 4 CalculiX mesh (:func:`hifi.fem.build_box_mesh`, S8R/B32) to the in-house
  model — every S8R becomes 4 Q4 on the same fine grid (corner, mid-side and centre nodes), every B32 two 2-node
  beams; same loads (:func:`hifi.fem.nodal_loads`), same section masses (stiff trusses ↔ bars), same root clamp.
  This gives a like-for-like solver verification against CalculiX (Phase 4 results).
* :func:`run` static + linear buckling + modal, post-processed with the same quantities as ``hifi.fem._post``."""
from __future__ import annotations

import math
import time

import numpy as np
from scipy.spatial import cKDTree

from acdt.core.fem import FEModel, isotropic
from acdt.core.fem.laminate import sandwich


def _rect_beam(a, b, E, G, rho):
    """Rectangular a×b section (a along the local z = direction 1); J Roark Table 10.7 (b ≤ a form)."""
    s, l_ = min(a, b), max(a, b)
    J = l_ * s**3 * (1 / 3 - 0.21 * s / l_ * (1 - s**4 / (12 * l_**4)))
    return dict(E=E, G=G, A=a * b, Iy=b * a**3 / 12, Iz=a * b**3 / 12, J=J, rho=rho)


def from_phase4(res, ds: float | None = None, factor: float = 1.5):
    from ..hifi import fem as h4

    mesh = h4.build_box_mesh(res, ds)
    m = mesh.meta["material"]
    E, nu, rho = m["E"], m["nu"], m["rho"]
    G = m.get("G", E / (2 * (1 + nu)))
    nodes = [tuple(p) for p in mesh.nodes]
    tree = cKDTree(mesh.nodes)

    def centre(pts):
        p = np.mean(pts, axis=0)
        d, i = tree.query(p)
        if d < 1e-6:
            return int(i)
        nodes.append(tuple(p))
        return len(nodes) - 1

    fm = FEModel(np.zeros((0, 3)))
    sec_id, groups = {}, {}
    for es, els in mesh.shells.items():
        p = mesh.shell_props[es]
        if es not in sec_id:
            if p.get("layers"):
                tf = p["layers"][0][0]
                tc = sum(t for t, mat in p["layers"] if mat == "CORE")
                core = m["core"]
                s = sandwich(E, nu, tf, core["E"], core["G"], tc, rho, core["rho"]) if tc > 0 else \
                    isotropic(E, nu, 2 * tf, rho)
            else:
                s = isotropic(E, nu, p["t"], rho)
            sec_id[es] = fm.add_section(s)
        g = groups.setdefault(es, [])
        for e in els:
            n1, n2, n3, n4, m5, m6, m7, m8 = e
            c = centre(mesh.nodes[[n1, n2, n3, n4]])
            for q in ((n1, m5, c, m8), (m5, n2, m6, c), (c, m6, n3, m7), (m8, c, m7, n4)):
                g.append(len(fm.shells))
                fm.shells.append(q + (sec_id[es], None))
    bgroups = {}
    for es, els in mesh.beams.items():
        p = mesh.beam_props[es]
        Eb = m["E_cap"] if p["mat"] == "CAP" else E
        pid = fm.add_beam_prop(**_rect_beam(p["a"], p["b"], Eb, G, rho))
        # CalculiX OFFSET1 = 0.5: the reference line (nodes) lies on the +1 face → centroid at −OFFSET1·a along 1
        off = np.array([0.0, 0.0, -p["offset1"] * p["a"]])
        g = bgroups.setdefault(es, [])
        for e in els:
            for a, b in ((e[0], e[1]), (e[1], e[2])):
                g.append(len(fm.beams))
                fm.beams.append((a, b, pid, off, off, (0, 0, 1)))
    loads, linfo = h4.nodal_loads(res, mesh, factor)
    extra, masses, mmeta = h4.section_masses(res, mesh)
    fm.nodes = np.array(nodes, float)
    for n in mesh.root:
        fm.fixed[n] = range(6)
    fm.loads = {n: [0, 0, F, 0, 0, 0] for n, F in loads.items()}
    pm = dict(masses)
    arms, efix = [], []
    for ex in extra:
        k = len(nodes)
        nodes.append((ex["x"], ex["y"], ex["z"]))
        pm[k] = pm.get(k, 0.0) + ex["mass"]
        efix.append(k)
        for a in ex["anchors"]:
            arms.append((k, a, 2.1e14 * 1e-3, 1e-6 * 1e-3))
    return fm, mesh, {"loads": linfo, "mass": mmeta, "groups": groups, "bgroups": bgroups, "masses": pm,
                      "arms": arms, "extra_nodes": efix, "nodes_modal": np.array(nodes, float)}


def run(res, ds: float | None = None, n_buckle: int = 4, n_modes: int = 10) -> dict:
    """Static + buckling + modal of the converted Phase 4 model; returns the same metrics as Phase 4 _post.
    ``n_buckle`` / ``n_modes`` = 0 skip those steps."""
    fm, mesh, info = from_phase4(res, ds)
    out = {"nodes": int(len(fm.nodes)), "shells_q4": len(fm.shells), "beams_2n": len(fm.beams), "t": {}}
    t0 = time.time()
    st = fm.solve_static()
    out["t"]["static_s"] = time.time() - t0
    U = st["u"].reshape(-1, 6)
    jt = len(mesh.y) - 1
    fu, ru = mesh.spar_lines["f_up"][jt], mesh.spar_lines["r_up"][jt]
    out["tip_w_m"] = float(0.5 * (U[fu, 2] + U[ru, 2]))
    out["tip_twist_deg"] = float(math.degrees(math.atan2(U[fu, 2] - U[ru, 2], mesh.x_r[jt] - mesh.x_f[jt])))
    sig = {}
    tsh = np.array([fm.sections[e[4]].t for e in fm.shells])
    for es, idx in info["groups"].items():
        if es == "RIB":
            continue
        idx = np.asarray(idx)
        lay = mesh.shell_props[es].get("layers")
        # spanwise membrane stress of the skin: N_x/t (sandwich: N_x/(2 t_face), core in-plane share neglected)
        t_eff = 2 * lay[0][0] if lay else tsh[idx]
        # N (element axes) → global yy component: N_yy = Σ_ab R[a,1] N_ab R[b,1]
        R = st["R"][idx]
        N = st["N"][idx]
        a, b = R[:, 0, 1], R[:, 1, 1]
        nyy = a * a * N[:, 0] + b * b * N[:, 1] + 2 * a * b * N[:, 2]
        sig[es] = float(np.mean(nyy / t_eff)) / 1e6
    for es, idx in info["bgroups"].items():
        sig[es] = float(np.mean(st["sigma_beam"][np.asarray(idx)])) / 1e6
    out["sigma_span_mean_MPa"] = sig
    out["struct_mass_semispan_kg"] = fm.structural_mass()
    out["_mesh"], out["_fm"] = mesh, fm
    if n_buckle:
        t0 = time.time()
        bk = fm.buckling(st, n_buckle, sigma=0.5)
        out["t"]["buckling_s"] = time.time() - t0
        out["buckling_factors"] = bk["lambda"].tolist()
    if not n_modes:
        return out
    # modal: add the section masses on the stiff arms
    fm.nodes = info["nodes_modal"]
    fm.point_masses = info["masses"]
    fm.bars = info["arms"]
    for k in info["extra_nodes"]:
        fm.fixed[k] = [3, 4, 5]
    t0 = time.time()
    md = fm.modal(n_modes)
    out["t"]["modal_s"] = time.time() - t0
    out["frequencies_Hz"] = md["f_Hz"].tolist()
    out["_modes"] = md["modes"]
    return out
