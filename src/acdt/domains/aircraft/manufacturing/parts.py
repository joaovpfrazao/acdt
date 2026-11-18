"""Decompose a sized design (:class:`acdt.domains.aircraft.sizing.DesignResult`) into manufactured parts.

Geometry comes from the configuration (wing/tail planforms, wing-box layout, fuselage frame layout); masses
come from the component weight build-up (``wing``, ``htail``, ``vtail``, ``fuselage`` items) and are split
among the parts of a component **in proportion to their face area** (uniform equivalent gauge — ASSUMPTION,
reported in ``notes``). The equivalent gauge is mass / (density x face area). Anything not derivable from the
design (fittings, frame depth) is either a flagged layout default in :data:`LAYOUT` or a user input.
"""
from __future__ import annotations

import math

from .processes import Part

# Layout defaults (ASSUMPTIONS, flagged in the output; override with layout={...}).
LAYOUT = {
    "frame_depth_fraction_of_D": 0.05,  # fuselage frame web depth / max diameter (no cited value: set from layout)
    "fuselage_shell_panels": 2,         # left/right half shells (moulded) or skin panels (sheet metal)
    "tail_spars_per_side": 1,
}


def _surface_parts(prefix, group, S, span, c_root, c_tip, tc, n_sides, spars_per_side, rib_pitch, box_xc,
                   Swet, mass, rho):
    """Skins, spars and box ribs of a trapezoidal lifting surface (n_sides = 2 for wing/htail, 1 for vtail)."""
    semi = span / 2 if n_sides == 2 else span
    c_mean = S / span
    h_mean = tc * c_mean
    parts = []
    # skins: upper + lower per side; one face each
    a_skin = Swet / (2 * n_sides)
    parts.append(dict(name=f"{prefix} skin", kind="skin", area=a_skin, faces=a_skin, count=2 * n_sides,
                      perimeter=2 * (semi + c_mean), max_dim=semi))
    # spars: web both faces
    a_web = h_mean * semi
    parts.append(dict(name=f"{prefix} spar", kind="spar", area=2 * a_web, faces=a_web, count=spars_per_side * n_sides,
                      perimeter=2 * semi, max_dim=semi))
    # ribs (box ribs between spars)
    n_ribs = int(math.floor(semi / rib_pitch)) + 1
    bw = (box_xc[1] - box_xc[0]) * c_mean
    a_rib = bw * h_mean
    parts.append(dict(name=f"{prefix} rib", kind="rib", area=2 * a_rib, faces=a_rib, count=n_ribs * n_sides,
                      perimeter=2 * (bw + h_mean), max_dim=max(bw, c_root * (box_xc[1] - box_xc[0]))))
    tot = sum(p["faces"] * p["count"] for p in parts)
    out = []
    for p in parts:
        m = mass * p["faces"] * p["count"] / tot / p["count"]
        t = m / (rho * p["faces"]) if rho else 0.0
        out.append(Part(name=p["name"], kind=p["kind"], mass_kg=m, area_m2=p["area"], perimeter_m=p["perimeter"],
                        max_dim_m=p["max_dim"], thickness_m=t, count=p["count"], group=group))
    return out


def decompose(res, materials: dict, layout: dict | None = None, fittings: list | None = None) -> dict:
    """Parts of the airframe structure. ``materials``: {group: material dict (needs rho)} for wing, htail, vtail,
    fuselage (missing groups fall back to ``materials['default']``). ``fittings``: user list of
    ``{name, mass_kg, area_m2, count?, max_dim_m?, group?}`` (no fitting mass is derivable from the sizing)."""
    L = {**LAYOUT, **(layout or {})}
    cfg = res.config
    w, f = cfg.wing, cfg.fuselage
    masses = {i.key: i.mass for i in res.weights.items} if res.weights else {}
    notes = ["part masses: component masses (weight build-up) split by face area — uniform equivalent gauge "
             "(ASSUMPTION)"]

    def mat(g):
        return materials.get(g) or materials["default"]

    def rho(g):
        return mat(g)["rho"]

    parts: list[Part] = []
    rp = w.box.rib_pitch or 0.6 * w.mac
    if w.box.rib_pitch is None:
        notes.append("wing rib pitch 0.6 MAC (Phase 2 box-sizing ASSUMPTION)")
    xc = (w.box.front_spar_xc, w.box.rear_spar_xc)
    fw = f.max_diameter
    if "wing" in masses:
        parts += _surface_parts("wing", "wing", w.S, w.span, w.c_root, w.c_tip, w.tc_mean, 2, 2, rp, xc,
                                w.wetted_area(fw), masses["wing"], rho("wing"))
    for key, n_sides in (("htail", 2), ("vtail", 1)):
        t = getattr(cfg, key)
        if key in masses and t is not None:
            tw = t.as_wing()
            parts += _surface_parts(key, key, tw.S, tw.span, tw.c_root, tw.c_tip, tw.tc_mean, n_sides,
                                    L["tail_spars_per_side"], tw.mac * 0.6, xc, tw.wetted_area(0.0),
                                    masses[key], rho(key))
    if "fuselage" in masses:
        n_fr = int(math.floor(f.length / f.frames.frame_pitch)) + 1
        D = f.max_diameter
        h_fr = L["frame_depth_fraction_of_D"] * D
        notes.append(f"fuselage frames: {n_fr} at {f.frames.frame_pitch} m pitch; web depth "
                     f"{L['frame_depth_fraction_of_D']} D (layout ASSUMPTION — no cited value, override)")
        npan = int(L["fuselage_shell_panels"])
        a_shell = f.wetted_area() / npan
        a_fr = math.pi * D * h_fr  # one face, at max diameter (upper bound of frame size)
        a_lg = 0.0
        geo = [dict(name="fuselage shell", kind="shell", faces=a_shell, area=a_shell, count=npan,
                    perimeter=2 * f.length + math.pi * D, max_dim=f.length, dc=True, ax=True),
               dict(name="fuselage frame", kind="frame", faces=a_fr, area=2 * a_fr, count=n_fr,
                    perimeter=math.pi * D, max_dim=D, dc=False, ax=False)]
        tot = sum(g["faces"] * g["count"] for g in geo) + a_lg
        for g in geo:
            m = masses["fuselage"] * g["faces"] / tot
            parts.append(Part(name=g["name"], kind=g["kind"], mass_kg=m, area_m2=g["area"], perimeter_m=g["perimeter"],
                              max_dim_m=g["max_dim"], thickness_m=m / (rho("fuselage") * g["faces"]), count=g["count"],
                              group="fuselage", double_curvature=g["dc"], axisymmetric=g["ax"]))
    for ft in fittings or []:
        parts.append(Part(name=ft["name"], kind="fitting", mass_kg=float(ft["mass_kg"]), area_m2=float(ft["area_m2"]),
                          max_dim_m=float(ft.get("max_dim_m", 0.0)), count=int(ft.get("count", 1)),
                          group=ft.get("group", "fittings"), perimeter_m=float(ft.get("perimeter_m", 0.0))))
    for p in parts:
        if p.material is None and p.group in ("wing", "htail", "vtail", "fuselage"):
            p.material = mat(p.group).get("key")
    m_struct = sum(p.mass_kg * p.count for p in parts)
    return {"parts": parts, "notes": notes, "structure_mass_kg": m_struct,
            "component_masses": {k: masses.get(k) for k in ("wing", "htail", "vtail", "fuselage")}}
