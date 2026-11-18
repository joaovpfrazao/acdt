"""Assembly → Physical-Optics RCS mesh with an explicit feature inventory.

Reads the component assembly (bodies — including opt-in hexagonal chines — surfaces, discs) and, when
supplied, equipment items shaped as box / sphere / cylinder. Anything that cannot be represented as a PEC
facet mesh is listed under ``unassessed`` (never silently dropped; unknown ≠ zero). Propeller discs stay
excluded by the PRESSUPOSTO of :meth:`Assembly.to_rcs_mesh`.

Cited methods: Gordon 1975 facet integral via :mod:`acdt.core.em.po`; hexagonal chine construction matches
:mod:`acdt.domains.aircraft.rcs.geometry` (Knott / Shaeffer / Tuley framing). No full-wave solver.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .assembly import Assembly
from .components import Body, Disc, Surface
from .integration import Item


def _box_mesh(cx, cy, cz, lx, ly, lz):
    """Closed axis-aligned box centred at (cx,cy,cz); outward normals."""
    hx, hy, hz = lx / 2, ly / 2, lz / 2
    V = np.array([
        [cx - hx, cy - hy, cz - hz], [cx + hx, cy - hy, cz - hz],
        [cx + hx, cy + hy, cz - hz], [cx - hx, cy + hy, cz - hz],
        [cx - hx, cy - hy, cz + hz], [cx + hx, cy - hy, cz + hz],
        [cx + hx, cy + hy, cz + hz], [cx - hx, cy + hy, cz + hz],
    ], float)
    F = np.array([
        [0, 1, 2], [0, 2, 3],  # -z
        [4, 6, 5], [4, 7, 6],  # +z
        [0, 4, 5], [0, 5, 1],  # -y
        [3, 2, 6], [3, 6, 7],  # +y
        [0, 3, 7], [0, 7, 4],  # -x
        [1, 5, 6], [1, 6, 2],  # +x
    ], int)
    return V, F


def _sphere_mesh(cx, cy, cz, r, n_u=12, n_v=8):
    """UV sphere (closed); outward normals. Coarse — L0 PO only."""
    V = []
    for j in range(n_v + 1):
        phi = math.pi * j / n_v
        for i in range(n_u):
            th = 2 * math.pi * i / n_u
            V.append((cx + r * math.sin(phi) * math.cos(th),
                      cy + r * math.sin(phi) * math.sin(th),
                      cz + r * math.cos(phi)))
    V = np.array(V, float)
    F = []
    for j in range(n_v):
        for i in range(n_u):
            a = j * n_u + i
            b = j * n_u + (i + 1) % n_u
            c = (j + 1) * n_u + (i + 1) % n_u
            d = (j + 1) * n_u + i
            if j > 0:
                F.append((a, b, c))
            if j < n_v - 1:
                F.append((a, c, d))
    return V, np.array(F, int)


def _cylinder_mesh(cx, cy, cz, size, axis="x", n_u=16):
    """Closed cylinder fitted in the item AABB ``size=(lx,ly,lz)``; generator along ``axis``."""
    ax = "xyz".index(axis)
    L = float(size[ax])
    r_dims = [size[i] for i in range(3) if i != ax]
    r = 0.5 * min(r_dims)
    # local: axis = z', then rotate
    Vloc = []
    for j, z in enumerate((-L / 2, L / 2)):
        for i in range(n_u):
            th = 2 * math.pi * i / n_u
            Vloc.append((r * math.cos(th), r * math.sin(th), z))
    # caps centres
    c0, c1 = len(Vloc), len(Vloc) + 1
    Vloc += [(0.0, 0.0, -L / 2), (0.0, 0.0, L / 2)]
    F = []
    for i in range(n_u):
        j = (i + 1) % n_u
        F += [(i, j, n_u + j), (i, n_u + j, n_u + i)]
        F += [(c0, j, i), (c1, n_u + i, n_u + j)]
    Vloc = np.array(Vloc, float)
    # map local z' → aircraft axis
    if axis == "x":
        V = np.column_stack([Vloc[:, 2], Vloc[:, 0], Vloc[:, 1]])
    elif axis == "y":
        V = np.column_stack([Vloc[:, 0], Vloc[:, 2], Vloc[:, 1]])
    else:
        V = Vloc.copy()
    V[:, 0] += cx
    V[:, 1] += cy
    V[:, 2] += cz
    return V, np.array(F, int)


def item_mesh(it: Item) -> tuple[np.ndarray, np.ndarray]:
    """PEC triangle mesh of one equipment item (box / sphere / cylinder). Needs a placed ``position``."""
    if it.position is None:
        raise ValueError(f"item {it.name!r}: position required for RCS mesh")
    cx, cy, cz = (float(v) for v in it.position)
    lx, ly, lz = (float(v) for v in it.size_m)
    sh = (it.shape or "box").lower()
    if sh == "box":
        return _box_mesh(cx, cy, cz, lx, ly, lz)
    if sh == "sphere":
        r = 0.5 * min(lx, ly, lz)
        return _sphere_mesh(cx, cy, cz, r)
    if sh == "cylinder":
        return _cylinder_mesh(cx, cy, cz, (lx, ly, lz), axis=it.cylinder_axis or "x")
    raise ValueError(f"item {it.name!r}: shape {it.shape!r} not representable in RCS mesh")


def feature_inventory(asm: Assembly, items: list[Item] | None = None,
                      exclude_roles=("propeller",)) -> dict[str, Any]:
    """Classify every assembly feature / item for the PO RCS path.

    * ``included`` — present in the merged PEC mesh
    * ``excluded_presupposto`` — deliberately left out (e.g. spinning propeller disc)
    * ``unassessed`` — cannot be represented; contribution must not be treated as zero / pass
    """
    included, excluded, unassessed = [], [], []
    for c in asm.components:
        if isinstance(c, Disc) or c.role in exclude_roles:
            excluded.append({
                "kind": "component", "name": c.name, "type": type(c).__name__.lower(),
                "role": c.role,
                "reason": "propeller/disc excluded from PEC RCS (PRESSUPOSTO of to_rcs_mesh)",
            })
            continue
        entry = {
            "kind": "component", "name": c.name, "type": type(c).__name__.lower(),
            "role": c.role,
        }
        if isinstance(c, Body) and c.chine:
            entry["chine"] = dict(c.chine)
            entry["note"] = "hexagonal chined section (sharp longitudinal edges for PO)"
        included.append(entry)
    for it in items or []:
        if it.position is None:
            unassessed.append({
                "kind": "item", "name": it.name, "shape": it.shape,
                "reason": "unplaced item — no RCS mesh (unknown ≠ zero)",
            })
            continue
        if (it.shape or "box").lower() not in ("box", "sphere", "cylinder"):
            unassessed.append({
                "kind": "item", "name": it.name, "shape": it.shape,
                "reason": f"shape {it.shape!r} has no PO mesh primitive",
            })
            continue
        # Internal equipment is still a PEC scatterer if the host is RF-transparent; otherwise the host
        # body already dominates. We still mesh every placed item so the contribution is assessed, and
        # flag host-internal ones for the analyst.
        host_note = f"host={it.host}" if it.host else "external"
        included.append({
            "kind": "item", "name": it.name, "shape": it.shape,
            "cylinder_axis": getattr(it, "cylinder_axis", None),
            "note": host_note,
        })
    return {
        "included": included,
        "excluded_presupposto": excluded,
        "unassessed": unassessed,
        "rule": "unassessed ≠ pass; unknown ≠ zero; excluded roles are PRESSUPOSTO not silent drop",
    }


def build_rcs_mesh(asm: Assembly, items: list[Item] | None = None, fine: int = 1,
                   exclude_roles=("propeller",)):
    """Merged :class:`~acdt.core.em.po.Mesh` + inventory. Items with a known shape are meshed in."""
    from acdt.core.em.po import Mesh

    inv = feature_inventory(asm, items, exclude_roles)
    Vs, Fs, off = [], [], 0
    for c in asm.components:
        if isinstance(c, Disc) or c.role in exclude_roles:
            continue
        V, F = asm.mesh(c.name, fine)
        Vs.append(V)
        Fs.append(F + off)
        off += len(V)
    for it in items or []:
        if it.position is None or (it.shape or "box").lower() not in ("box", "sphere", "cylinder"):
            continue
        V, F = item_mesh(it)
        Vs.append(V)
        Fs.append(F + off)
        off += len(V)
    if not Vs:
        raise ValueError("no representable geometry for RCS mesh")
    mesh = Mesh(np.concatenate(Vs), np.concatenate(Fs), "assembly+items")
    return mesh, inv


def apply_chine_deg(asm: Assembly, chine_deg: float, roles=("fuselage",),
                    only_already_chined: bool = True) -> list[str]:
    """Mutate ``Body.chine.angle_deg`` on matching bodies (DOE hook). Returns names touched.

    When ``only_already_chined``, bodies without a chine are left alone and the caller should list the
    skipped DOE variable as unassessed if nothing was touched. Does not invent a parallel airframe.
    """
    touched = []
    for c in asm.components:
        if not isinstance(c, Body):
            continue
        if roles and c.role not in roles and c.name not in roles:
            continue
        if only_already_chined and not c.chine:
            continue
        if c.chine is None:
            c.chine = {"angle_deg": float(chine_deg), "crown_frac": 0.35}
        else:
            c.chine = {**c.chine, "angle_deg": float(chine_deg)}
        touched.append(c.name)
    return touched
