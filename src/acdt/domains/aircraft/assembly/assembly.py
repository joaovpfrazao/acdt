"""Assembly of generic components + adapters to existing acdt inputs (RCS PO mesh, STL, AVL surfaces).

``Assembly.from_dict({"components": [{"type": "body"|"surface"|"disc", "name", ...}]})`` — see
:mod:`.components` for the fields. Bodies accept ``stations`` or the ``pod`` shorthand, surfaces ``sections`` or
the ``panel`` shorthand."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .components import (
    TYPES, Body, Component, Disc, Surface, naca4_mean_line_record, naca4_section_code,
    section_thickness_record, symmetric_naca_code,
)

_COMMON = ("name", "role", "origin", "orientation", "mirror", "mass_kg", "cg", "transparent_to", "opacity")


def component_from_dict(d: dict) -> Component:
    d = dict(d)
    typ = d.pop("type", None)
    if typ not in TYPES:
        raise ValueError(f"component {d.get('name')!r}: type must be one of {sorted(TYPES)} (got {typ!r})")
    if "name" not in d:
        raise ValueError("every component needs a name")
    common = {k: d.pop(k) for k in _COMMON if k in d}
    for k in ("origin", "cg"):
        if k in common and common[k] is not None:
            common[k] = tuple(float(v) for v in common[k])
    if "transparent_to" in common:
        common["transparent_to"] = tuple(common["transparent_to"])
    if typ == "body" and "pod" in d:
        p = d.pop("pod")
        return Body.pod(common.pop("name"), **p, **common)
    if typ == "surface" and "panel" in d:
        p = d.pop("panel")
        return Surface.panel(common.pop("name"), **p, **common, **d)
    return TYPES[typ](**common, **d)


class Assembly:
    def __init__(self, components: list[Component], expand_mirror: bool = True):
        self.components: list[Component] = []
        for c in components:
            self.components.append(c)
            if c.mirror and expand_mirror:
                self.components.append(c.mirrored())
        names = [c.name for c in self.components]
        dup = {n for n in names if names.count(n) > 1}
        if dup:
            raise ValueError(f"duplicate component names {sorted(dup)}")
        self._mesh_cache: dict = {}

    @classmethod
    def from_dict(cls, spec: dict) -> "Assembly":
        comps = spec.get("components") if isinstance(spec, dict) else spec
        if not comps:
            raise ValueError("assembly needs a non-empty 'components' list")
        return cls([component_from_dict(c) for c in comps])

    def get(self, name: str) -> Component:
        for c in self.components:
            if c.name == name:
                return c
        raise KeyError(f"unknown component {name!r}; have {[c.name for c in self.components]}")

    def mesh(self, name: str, fine: int = 1):
        key = (name, fine)
        if key not in self._mesh_cache:
            self._mesh_cache[key] = self.get(name).mesh(fine)
        return self._mesh_cache[key]

    def triangles(self, fine: int = 1):
        """All triangles (nf, 3, 3) and the owning component index per triangle."""
        P, owner = [], []
        for i, c in enumerate(self.components):
            V, F = self.mesh(c.name, fine)
            P.append(V[F])
            owner.append(np.full(len(F), i))
        return np.concatenate(P), np.concatenate(owner)

    def summary(self) -> dict:
        out = {}
        lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
        for c in self.components:
            b0, b1 = c.bbox()
            lo, hi = np.minimum(lo, b0), np.maximum(hi, b1)
            row = {"type": type(c).__name__.lower(), "role": c.role, "volume_m3": c.volume(),
                   "wetted_area_m2": c.wetted_area(), "centroid": c.centroid().tolist(),
                   "bbox": [b0.tolist(), b1.tolist()]}
            if isinstance(c, Surface):
                row["planform_area_m2"] = c.planform_area()
            if c.mass_kg is not None:
                row["mass_kg"] = c.mass_kg
            out[c.name] = row
        return {"components": out, "bbox": [lo.tolist(), hi.tolist()],
                "wetted_area_total_m2": sum(r["wetted_area_m2"] for r in out.values() if r["type"] != "disc"),
                "method": "triangulated closed meshes; volume by divergence theorem (bodies: ∫A(x)dx with Lamé "
                          "section area); NACA 4-digit thickness (Abbott & von Doenhoff 1959)"}

    # ------------------------------------------------------------------------------------ adapters
    def to_rcs_mesh(self, fine: int = 1, exclude_roles=("propeller",)):
        """Merged :class:`acdt.core.em.po.Mesh` (outward normals) for the PO RCS solver. Discs are excluded by
        default (a rotating prop is not a PEC plate — PRESSUPOSTO)."""
        from acdt.core.em.po import Mesh
        Vs, Fs, off = [], [], 0
        for c in self.components:
            if isinstance(c, Disc) or c.role in exclude_roles:
                continue
            V, F = self.mesh(c.name, fine)
            Vs.append(V)
            Fs.append(F + off)
            off += len(V)
        return Mesh(np.concatenate(Vs), np.concatenate(Fs), "assembly")

    def write_stl(self, path, fine: int = 1) -> Path:
        """ASCII STL of every component (readable by `acdt rcs` STL mode and any CAD viewer)."""
        path = Path(path)
        lines = ["solid acdt_assembly"]
        for c in self.components:
            V, F = self.mesh(c.name, fine)
            for f in F:
                a, b, cc = V[f]
                n = np.cross(b - a, cc - a)
                n = n / (np.linalg.norm(n) or 1.0)
                lines += [f"facet normal {n[0]:.6e} {n[1]:.6e} {n[2]:.6e}", " outer loop"]
                lines += [f"  vertex {p[0]:.6e} {p[1]:.6e} {p[2]:.6e}" for p in (a, b, cc)]
                lines += [" endloop", "endfacet"]
        lines.append("endsolid acdt_assembly")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def avl_text(self, name: str = "acdt_assembly", mach: float = 0.0, ref: dict | None = None,
                 cg: tuple | None = None, nchord: int = 8, nspan: int = 12) -> str:
        """AVL geometry file (Drela & Youngren, AVL 3.x user guide) with every lifting surface as SURFACE /
        SECTION (LE point, chord, Ainc = section twist; NACA 4-digit symmetric of the section t/c, unless that
        surface opted in to the 4-digit mean line). A y-mirrored
        surface is written once with YDUPLICATE 0. Bodies and discs are NOT written (AVL BODY needs a profile
        file — TODO), so body lift / Munk moment is missing. Reference values: ``ref`` {Sref, Cref, Bref} or
        the largest surface (both sides) — PRESSUPOSTO."""
        surfs = [c for c in self.components if isinstance(c, Surface) and not c.mirrored_image]
        if not surfs:
            raise ValueError("no lifting surfaces in the assembly")
        if ref is None:
            big = max(surfs, key=lambda s: s.planform_area() * (2 if s.mirror else 1))
            S = big.planform_area() * (2 if big.mirror else 1)
            V, _ = big.mesh()
            b = 2 * float(np.abs(V[:, 1]).max()) if big.mirror else float(np.ptp(V[:, 1]) or np.ptp(V[:, 2]))
            ref = {"Sref": S, "Cref": S / max(b, 1e-9), "Bref": b}
        x0 = cg if cg is not None else (0.0, 0.0, 0.0)
        out = [name, "#Mach", f"{mach:g}", "#IYsym IZsym Zsym", "0 0 0.0", "#Sref Cref Bref",
               f"{ref['Sref']:.5f} {ref['Cref']:.5f} {ref['Bref']:.5f}", "#Xref Yref Zref",
               f"{x0[0]:.5f} {x0[1]:.5f} {x0[2]:.5f}", "#CDp", "0.0"]
        for s in surfs:
            out += ["#" + "=" * 60, "SURFACE", s.name, "#Nchord Cspace Nspan Sspace", f"{nchord} 1.0 {nspan} 1.0"]
            if s.mirror:
                out += ["YDUPLICATE", "0.0"]
            built = None
            if s.naca4_mean_line:
                built = naca4_mean_line_record(s.airfoil, s.sections[0]["tc"], s.sections[-1]["tc"])
                out.append("# " + built["motivo"])
            else:
                rec = section_thickness_record(s.airfoil, s.sections[0]["tc"], s.sections[-1]["tc"])
                if rec["camber"] == "lacuna":
                    out.append("# " + rec["motivo"])
            for sec in s.sections:
                if built is not None:
                    code = naca4_section_code(
                        built["parsed"]["camber_percent_chord"],
                        built["parsed"]["camber_position_tenths"], sec["tc"])
                else:
                    code = symmetric_naca_code(sec["tc"])
                le = s.to_global([sec["le"]])[0]
                out += ["SECTION", "#Xle Yle Zle Chord Ainc",
                        f"{le[0]:.5f} {le[1]:.5f} {le[2]:.5f} {sec['chord']:.5f} {sec['twist_deg']:.3f}",
                        "NACA", code]
        return "\n".join(out) + "\n"
