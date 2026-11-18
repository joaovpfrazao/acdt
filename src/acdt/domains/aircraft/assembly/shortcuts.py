# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Named configuration shortcuts that assemble generic components for ``acdt size``.

Named types are *shortcuts* (DESIGN_WORKFLOW / HANDOFF P1): they build the same Body / Surface /
Disc primitives as a hand-written ``assumptions.assembly`` drawing. They are never a closed list
of the only layouts the tools can analyse — any drawing of components remains valid.

Supported shortcuts
-------------------
* ``conventional`` — not emitted here; the fixed-type Configuration path stays the default.
* ``V`` / ``inverted_V`` — single fuselage + wing + one mirrored V (or inverted-V) panel pair.
  Panel area from horizontal/vertical volume coefficients with the Purser & Campbell
  (NACA Rep. 823) projections used elsewhere in ``assembly.sizing``: S_h = S·cos²Γ,
  S_v = S·sin²Γ, with S sized so both Raymer Eqs. 6.28–6.29 targets are met (take the
  larger requirement). Missing Γ, arm or volume coeffs → refuse (no silent H+V substitute).
* ``twin_boom`` — short pod + mirrored booms + wing + inverted-V (default) or V at the boom
  tips. Same Purser & Campbell V sizing. Boom length / spacing from geometry fractions.

Weights, CD0, AVL, W&B and ``hq:*`` then follow the existing assembly path (Raymer 15.46–15.49,
junction Q, Nelson / Etkin modes). No new heavy solvers.
"""
from __future__ import annotations

import math

SHORTCUTS = ("V", "inverted_V", "twin_boom")


def _req(geo: dict, key: str, label: str):
    v = geo.get(key)
    if v is None:
        raise ValueError(f"geometry.{key} required for configuration shortcut ({label}); "
                         "refusing a silent conventional-tail substitute")
    return float(v)


def _vee_panel_area(*, c_ht: float, c_vt: float, mac: float, span: float, S_w: float,
                    arm: float, gamma_deg: float) -> tuple[float, float, dict]:
    """Planform area of one V panel (full mirrored pair counted once as surface.mirror).

    Purser & Campbell / Raymer: projected S_h = S_panel·cos²Γ, S_v = S_panel·sin²Γ.
    Need S_h >= c_ht·mac·S_w/L and S_v >= c_vt·b·S_w/L → S_panel = max(S_h/cos²Γ, S_v/sin²Γ).
    """
    G = math.radians(abs(gamma_deg))
    cg, sg = math.cos(G), math.sin(G)
    if abs(cg) < 1e-6 or abs(sg) < 1e-6:
        raise ValueError(f"V-tail dihedral Γ={gamma_deg}° too close to 0° or 90° for Purser & Campbell "
                         "split (need both horizontal and vertical projections)")
    if arm <= 0:
        raise ValueError("tail arm must be > 0 for V-tail volume sizing (Raymer Eqs. 6.28–6.29)")
    Sh_req = c_ht * mac * S_w / arm
    Sv_req = c_vt * span * S_w / arm
    S_from_h = Sh_req / (cg * cg)
    S_from_v = Sv_req / (sg * sg)
    S_panel = max(S_from_h, S_from_v)
    return S_panel, G, {
        "method": "Purser & Campbell NACA Rep. 823 projections; Raymer 2018 Eqs. 6.28–6.29 volumes",
        "S_h_required_m2": Sh_req, "S_v_required_m2": Sv_req,
        "S_panel_m2": S_panel, "binding": "horizontal" if S_from_h >= S_from_v else "vertical",
        "gamma_deg": gamma_deg,
    }


def build_shortcut(kind: str, *, geo: dict, aero: dict, S_ref_m2: float = 2.0) -> dict:
    """Return an ``assumptions.assembly``-shaped dict for ``kind`` ∈ SHORTCUTS.

    ``S_ref_m2`` is the *drawn* wing area; :class:`~.loop.AssemblyLoop` rescales it to the sized
    wing each MDA pass. Fuselage length / diameter come from ``geo`` (required).
    """
    kind = str(kind)
    if kind not in SHORTCUTS:
        raise ValueError(f"geometry.configuration '{kind}' unknown; shortcuts: {SHORTCUTS} "
                         "(or omit for the conventional fixed-type path / supply assumptions.assembly)")
    L = _req(geo, "fuselage_length_m", kind)
    D = geo.get("fuselage_diameter_m")
    if D is None:
        fin = float(geo.get("fuselage_fineness") or 7.0)
        D = L / fin
    else:
        D = float(D)
    AR = float(aero.get("AR") or 10.0)
    taper = float(aero.get("taper") or 0.5)
    sweep = float(aero.get("sweep_c4_deg") or 0.0)
    tc_r = float(aero.get("tc_root") or 0.12)
    tc_t = float(aero.get("tc_tip") or tc_r)
    wing_dih = geo.get("dihedral_deg")
    wing_dih = 3.0 if wing_dih is None else float(wing_dih)
    c_ht = geo.get("c_ht")
    c_vt = geo.get("c_vt")
    if c_ht is None or c_vt is None:
        raise ValueError(f"geometry.c_ht and geometry.c_vt required for '{kind}' shortcut "
                         "(Raymer volume coeffs); refusing a silent substitute")
    c_ht, c_vt = float(c_ht), float(c_vt)
    arm_frac = float(geo.get("tail_arm_fraction") or 0.60)
    arm = arm_frac * L
    S_w = float(S_ref_m2)
    b = math.sqrt(AR * S_w)
    # MAC of trapezoidal wing (Raymer Eq. 7.5)
    c_root = 2 * S_w / (b * (1 + taper))
    c_tip = taper * c_root
    mac = 2 / 3 * c_root * (1 + taper + taper ** 2) / (1 + taper)
    y_mac = b / 6 * (1 + 2 * taper) / (1 + taper)
    # LE sweep from c/4 (Raymer Sec. 7.3)
    sweep_c4 = math.radians(sweep)
    sweep_le = math.atan(math.tan(sweep_c4) + 4 / AR * 0.25 * (1 - taper) / (1 + taper))

    if kind in ("V", "inverted_V"):
        gamma = geo.get("tail_dihedral_deg")
        if gamma is None:
            gamma = 35.0 if kind == "V" else -35.0
        else:
            gamma = float(gamma)
            if kind == "inverted_V" and gamma > 0:
                gamma = -abs(gamma)
            if kind == "V" and gamma < 0:
                gamma = abs(gamma)
        S_panel, _, vee_meta = _vee_panel_area(c_ht=c_ht, c_vt=c_vt, mac=mac, span=b, S_w=S_w,
                                              arm=arm, gamma_deg=gamma)
        # Panel span along the panel: choose AR_v ~ 1.5 on the projected vertical or from geo.ar_v
        ar_v = float(geo.get("ar_v") or 1.5)
        # Treat S_panel as the full V (both sides via mirror): each side has S_panel/2
        S_side = S_panel / 2
        # span along panel from S = span * (c_r+c_t)/2 with taper_v
        taper_v = float(geo.get("taper_v") or 0.5)
        # Use AR of the panel in its plane: AR_panel = span_panel² / S_side
        span_panel = math.sqrt(ar_v * S_side)
        c_r_t = 2 * S_side / (span_panel * (1 + taper_v))
        c_t_t = taper_v * c_r_t
        x_wing = 0.35 * L
        x_ac_w = x_wing + y_mac * math.tan(sweep_le) + 0.25 * mac
        x_tail = x_ac_w + arm
        z_wing = 0.0
        comps = [
            {"type": "body", "name": "fuselage", "role": "fuselage",
             "pod": {"length": L, "width": D, "nose_frac": 0.2, "tail_frac": 0.45, "tail_scale": 0.1}},
            {"type": "surface", "name": "wing", "role": "wing", "origin": [x_wing, 0.0, z_wing], "mirror": True,
             "panel": {"root_chord": c_root, "tip_chord": c_tip, "span": b / 2,
                       "sweep_le_deg": math.degrees(sweep_le), "dihedral_deg": wing_dih,
                       "tc_root": tc_r, "tc_tip": tc_t}},
            {"type": "surface", "name": "tail", "role": ("V tail" if kind == "V" else "inverted V tail"),
             "origin": [x_tail, 0.0, z_wing], "mirror": True,
             "panel": {"root_chord": c_r_t, "tip_chord": c_t_t, "span": span_panel,
                       "sweep_le_deg": 15.0, "dihedral_deg": gamma, "tc_root": 0.10, "tc_tip": 0.10}},
        ]
        note = (f"shortcut '{kind}': V panels by Purser & Campbell / Raymer 6.28–6.29; "
                f"Γ={gamma}°, binding={vee_meta['binding']}; PRESSUPOSTO drawing scaled by assembly loop")
        return {
            "_note": note,
            "assembly": {"components": comps},
            "options": {"scaling": "uniform", "shortcut": kind, "vee": vee_meta},
            "gear": {"type": "tricycle"},
            "masses": [],
        }

    # twin_boom
    gamma = geo.get("tail_dihedral_deg")
    gamma = -35.0 if gamma is None else float(gamma)
    if gamma > 0:
        gamma = -abs(gamma)  # default inverted V on twin boom (Nansei-class)
    S_panel, _, vee_meta = _vee_panel_area(c_ht=c_ht, c_vt=c_vt, mac=mac, span=b, S_w=S_w,
                                          arm=arm, gamma_deg=gamma)
    boom_y_frac = float(geo.get("boom_span_fraction") or 0.35)  # y / (b/2)
    boom_y = boom_y_frac * (b / 2)
    pod_frac = float(geo.get("pod_length_fraction") or 0.55)
    pod_L = pod_frac * L
    boom_width = float(geo.get("boom_width_m") or max(0.08, 0.25 * D))
    # Boom runs from near wing LE to tail AC
    x_wing = 0.40 * pod_L
    x_ac_w = x_wing + y_mac * math.tan(sweep_le) + 0.25 * mac
    x_tail = x_ac_w + arm
    boom_x0 = 0.15 * pod_L
    boom_L = max(x_tail - boom_x0 + 0.3, 0.6 * L)
    ar_v = float(geo.get("ar_v") or 1.5)
    S_side = S_panel / 2
    taper_v = float(geo.get("taper_v") or 0.5)
    span_panel = math.sqrt(ar_v * S_side)
    c_r_t = 2 * S_side / (span_panel * (1 + taper_v))
    c_t_t = taper_v * c_r_t
    z_wing = 0.05 * D
    comps = [
        {"type": "body", "name": "pod", "role": "fuselage",
         "pod": {"length": pod_L, "width": D, "nose_frac": 0.28, "tail_frac": 0.08, "tail_scale": 0.7}},
        {"type": "surface", "name": "wing", "role": "wing", "origin": [x_wing, 0.0, z_wing], "mirror": True,
         "panel": {"root_chord": c_root, "tip_chord": c_tip, "span": b / 2,
                   "sweep_le_deg": math.degrees(sweep_le), "dihedral_deg": wing_dih,
                   "tc_root": tc_r, "tc_tip": tc_t}},
        {"type": "body", "name": "boom", "role": "boom", "origin": [boom_x0, boom_y, z_wing], "mirror": True,
         "pod": {"length": boom_L, "width": boom_width, "nose_frac": 0.1, "tail_frac": 0.1, "tail_scale": 0.6}},
        {"type": "surface", "name": "tail", "role": "inverted V tail",
         "origin": [x_tail, boom_y, z_wing], "mirror": True,
         "panel": {"root_chord": c_r_t, "tip_chord": c_t_t, "span": span_panel,
                   "sweep_le_deg": 12.0, "dihedral_deg": gamma, "tc_root": 0.10, "tc_tip": 0.10}},
    ]
    note = (f"shortcut 'twin_boom': pod + mirrored booms + inverted-V (Purser & Campbell / Raymer 6.28–6.29); "
            f"Γ={gamma}°, boom_y_frac={boom_y_frac}; PRESSUPOSTO drawing scaled by assembly loop")
    return {
        "_note": note,
        "assembly": {"components": comps},
        "options": {"scaling": "uniform", "shortcut": "twin_boom", "vee": vee_meta,
                    "boom_span_fraction": boom_y_frac},
        "gear": {"type": "tricycle"},
        "masses": [],
    }


def resolve_assembly_shortcut(spec) -> tuple[dict | None, str | None]:
    """If ``geometry.configuration`` names a shortcut and no ``assumptions.assembly`` drawing is
    already set, build one. Returns ``(assembly_dict_or_None, info_or_None)``.

    An existing ``assumptions.assembly`` (file or inline components) always wins — shortcuts never
    overwrite a supplied drawing. ``conventional`` / missing → no injection.
    """
    A = getattr(spec, "assumptions", None) or {}
    if not isinstance(A, dict):
        return None, None
    if A.get("assembly"):
        # Already has a drawing (file or inline). Do not substitute.
        return None, None
    geo = A.get("geometry") or {}
    kind = geo.get("configuration")
    if not kind or kind in ("conventional", "conventional_tail", "H_V"):
        return None, None
    aero = A.get("aero") or {}
    drawing = build_shortcut(kind, geo=geo, aero=aero)
    return drawing, drawing.get("_note")
