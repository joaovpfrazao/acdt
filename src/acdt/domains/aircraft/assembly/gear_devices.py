# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in assembly landing-gear devices beyond the tricycle already in :func:`.sizing.gear_layout`.

Named ``gear.type`` values are *shortcuts* that place generic components / run the same classical
layout checks — never a closed list as the only path. A hand-placed tricycle, taildragger, ski or
leg drawing remains valid when this helper is unused.

Methods
-------
* **Taildragger / conventional** — Raymer 2018 Ch. 11 / Currey 1988: main wheels on the 15° ray
  *ahead* of the most-forward CG; overturn about the tail-wheel–main axis (aft CG critical);
  static load share on the tail wheel reported (the 8–15 % nose band is tricycle-only);
  propeller ground clearance **9 in** (14 CFR 23.925(a)(1) tail-wheel aeroplanes, as amended
  before Amdt. 23-64). Missing stations → unassessed / fail with residuals — never a silent
  tricycle substitute.
* **Ski** — contact geometry from a *supplied* ski length / attach / thickness (Raymer Ch. 11
  treats skis as an alternate landing device; no invented ski length). Fore/aft ski contacts
  replace the wheel pair for tip-back / overturn / prop clearance. Missing ski block →
  ``status='unassessed'``.
* **Drawn legs** — optional Body pods (role ``gear_leg``) from ground contact to the attach
  height so CAD / STEP / DXF see strut geometry, not just contact points (Currey strut
  envelope at L0: cylinder of given diameter; PRESSUPOSTO diameter when not supplied).
* **Kinematics** — open geometric retract check: wheel-centre arc about a supplied hinge/axis
  sampled for interference with structure / propulsor discs. Missing path → unassessed. No
  mechanism dynamics or FEM.
* **Tip skids** (opt-in ``gear.tip_skids``) — wing-tip shoes for a narrow-track aeroplane that
  may brush a tip in a crosswind roll (Raymer 2018 Ch. 11: outrigger / tip gear on bicycle and
  narrow-track layouts). Sized by landing-gear energy absorption E = η N δ (Currey 1988; Raymer
  Sec. 18.2; Sadraey 2012 Sec. 9.7) for a drop of the tip effective mass through the static tip
  clearance. Not a substitute for 14 CFR 23.233(a) (0.2 V_S0) and not a reason to widen the
  track past the 23.485 side-load check.
* **Fixed-gear drag scaling** — a lumped ``extra_drag_areas_m2.fixed_gear`` is scaled with
  current strut lengths over the PRESSUPOSTO defaults used in Raymer Eq. 15.50/15.51 (0.60 m
  main, 0.50 m nose). Without a wheel/strut split the whole area is scaled (reported; applied
  only when ``gear.scale_drag`` is set).
* **Side-load structure** — vertical legs checked as beams/columns under 14 CFR 23.485
  (0.5 W inboard / 0.33 W outboard, combined with 1.33 × the static wheel load). Al 2024-T3
  MMPDS typical, FS 1.5. Diameter PRESSUPOSTO 0.06 m unless ``leg_diameter_m`` is given.
* **Sadraey 9.5.3.2 max track** — front-view simply-supported beam between the main wheels,
  mid-span deflection δ = W T³ / (48 EI) (central load; standard beam theory). Implied extra
  dihedral ΔΓ = atan(2δ / T). The book's numerical δ allowable is not cited here, so the
  deflection is reported and the pass/fail stays unassessed unless ``delta_allow_m`` is given.
"""
from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np

from .assembly import Assembly
from .components import Body, Disc

IN = 0.0254

# Aliases that mean the same classical layout (shortcuts, not a closed enum).
TAILDRAGGER_TYPES = frozenset({"taildragger", "conventional", "tailwheel"})
SKI_TYPES = frozenset({"ski", "skis"})


def _rotation_vertices(asm: Assembly):
    from .sizing import _rotation_vertices
    return _rotation_vertices(asm)


def _prop_clearance_default(kind: str) -> float:
    """14 CFR 23.925(a)(1): 7 in nose-wheel, 9 in tail-wheel."""
    return 9 * IN if kind in TAILDRAGGER_TYPES else 7 * IN


def layout_taildragger(asm: Assembly, cg_fwd: list, cg_aft: list, opts: dict) -> dict:
    """Place main + tail wheel on the assembly mesh (Raymer Ch. 11; 14 CFR 23.925)."""
    from ..landing_gear import (DEFAULT_TAILWHEEL_FUSELAGE_FRACTION, angle_from_vertical_deg,
                                min_half_track, overturn_angle_deg, place_taildragger,
                                static_fraction_front)
    o = {
        "tipback_deg": 15.0, "overturn_max_deg": 63.0, "prop_clearance_m": None,
        "ground_z": None, "x_main": None, "x_tail": None, "half_track": None,
        "tailwheel_fuselage_fraction": DEFAULT_TAILWHEEL_FUSELAGE_FRACTION,
        **opts,
    }
    prop_c = o["prop_clearance_m"] if o["prop_clearance_m"] is not None else _prop_clearance_default("taildragger")
    P = _rotation_vertices(asm)
    discs = [c for c in asm.components if isinstance(c, Disc)]
    bodies = [c for c in asm.components if isinstance(c, Body) and c.role not in ("item", "gear_leg")]
    zf, zr = float(cg_fwd[2]), float(cg_aft[2])
    xf, xr = float(cg_fwd[0]), float(cg_aft[0])
    tip = float(o["tipback_deg"])
    z_min = float(P[:, 2].min())
    disc_low = [float(d.bbox()[0][2]) for d in discs]

    # Tail station: user, else PRESSUPOSTO fraction of the longest fuselage-like body.
    if o["x_tail"] is not None:
        x_tail = float(o["x_tail"])
        tail_note = "x_tail dado"
    else:
        if not bodies:
            return {
                "type": "taildragger", "status": "unassessed",
                "checks": [("asm:gear_position", None,
                            "taildragger unassessed: sem corpo de fuselagem para a estação da roda de cauda "
                            "e landing_gear/gear.x_tail em falta (PRESSUPOSTO DEFAULT_TAILWHEEL_FUSELAGE_FRACTION "
                            "só com fuselagem; Raymer Cap. 11)")],
                "issues": ["x_tail missing and no fuselage body"],
            }
        fus = max(bodies, key=lambda b: b.length)
        L = float(fus.length)
        x0 = float(fus.origin[0])
        frac = float(o["tailwheel_fuselage_fraction"])
        x_tail = x0 + frac * L
        tail_note = (f"PRESSUPOSTO x_tail = {frac:.2f}·L_fus ({x_tail:.3f} m); "
                     "substituir por gear.x_tail")

    def layout(zg):
        h = max(zf, zr) - zg
        if o["x_main"] is not None:
            xm = float(o["x_main"])
        else:
            xm = place_taildragger(xf, h, x_tail, tip)
        return h, xm

    def zg_required(xm):
        # Prop / belly clearances at the three-point (tail-down) attitude.
        req = [z_min] + [z - prop_c for z in disc_low]
        return min(req) if req else z_min

    given = o["ground_z"] is not None
    if given:
        zg, it = float(o["ground_z"]), 0
    else:
        zg = z_min
        for it in range(1, 41):
            _, xm = layout(zg)
            zn = zg_required(xm)
            if abs(zn - zg) < 1e-4:
                zg = zn
                break
            zg = zn
    h, xm = layout(zg)
    clear_prop = min([z - zg for z in disc_low], default=math.inf)
    belly = z_min - zg
    tipback = angle_from_vertical_deg(xf - xm, h)
    checks = []
    checks.append(("asm:gear_tipback", tipback + 1e-6 >= tip,
                   f"ângulo de nariz {tipback:.1f}° no CG dianteiro (mín. {tip:.0f}°, Raymer Cap. 11 "
                   f"taildragger), x_main {xm:.3f} m, h_cg {h:.3f} m"))
    between = xm < xf + 1e-6 and x_tail > xr - 1e-6 and xm < x_tail
    checks.append(("asm:gear_position", between,
                   f"principal x = {xm:.3f} m, cauda x = {x_tail:.3f} m; CG "
                   f"({xf:.3f}–{xr:.3f} m) entre as rodas (Raymer Cap. 11)"))
    # Tail load share reported — not the tricycle 8–15 % band.
    f_tail_fwd = 1.0 - static_fraction_front(xm, x_tail, xf)
    f_tail_aft = 1.0 - static_fraction_front(xm, x_tail, xr)
    # Tail load share is reported on the result (not a Raymer pass/fail band — that is tricycle-only).
    if discs:
        checks.append(("asm:gear_prop_clearance", clear_prop + 1e-6 >= prop_c,
                       f"folga da hélice ao solo {clear_prop:.3f} m (mín. {prop_c:.3f} m = 9 in, "
                       f"14 CFR 23.925(a)(1) tail-wheel)"))
    checks.append(("asm:gear_belly", belly >= -1e-6, f"folga do ventre ao solo {belly:.3f} m"))
    t_req = min_half_track(x_tail, xm, xr, h, float(o["overturn_max_deg"]))
    res = {
        "type": "taildragger", "status": "assessed", "ground_z": zg, "ground_z_given": given,
        "iterations": it, "h_cg": h, "x_main": xm, "x_tail": x_tail, "x_nose": None,
        "prop_clearance_m": clear_prop, "belly_clearance_m": belly, "tipback_deg": tipback,
        "tail_fraction": [f_tail_fwd, f_tail_aft], "half_track_min": t_req,
        "wheelbase": x_tail - xm, "main_leg_from_lowest_point_m": z_min - zg,
        "notes": [tail_note, "Método: Raymer Cap. 11 taildragger + 14 CFR 23.925(a)(1) 9 in"],
    }
    if o["half_track"] is not None:
        ov = overturn_angle_deg(x_tail, xm, float(o["half_track"]), xr, h)
        res["overturn_deg"] = ov
        checks.append(("asm:gear_overturn", ov <= float(o["overturn_max_deg"]) + 1e-6,
                       f"capotagem {ov:.1f}° no CG traseiro (máx. {o['overturn_max_deg']:.0f}°, "
                       f"Raymer Cap. 11), meia-via {o['half_track']} m"))
    elif math.isfinite(t_req):
        checks.append(("asm:gear_overturn", True,
                       f"bitola mínima {2 * t_req:.3f} m para {o['overturn_max_deg']:.0f}° "
                       f"(Raymer Cap. 11; apex = roda de cauda)"))
    else:
        checks.append(("asm:gear_overturn", False, "capotagem sem solução (Raymer Cap. 11)"))
    res["checks"] = checks
    return res


def layout_ski(asm: Assembly, cg_fwd: list, cg_aft: list, opts: dict) -> dict:
    """Ski contact layout from *supplied* ski geometry (Raymer Ch. 11 alternate landing device).

    Required ``gear.ski`` keys: ``length_m``. Optional: ``attach_x`` (ski mid / attach station),
    ``thickness_m``, ``half_track``, ``prop_clearance_m``. No length → unassessed (never invent a ski).
    """
    from ..landing_gear import angle_from_vertical_deg, min_half_track, overturn_angle_deg
    ski = opts.get("ski")
    if not isinstance(ski, dict) or ski.get("length_m") is None:
        return {
            "type": "ski", "status": "unassessed",
            "checks": [("asm:gear_position", None,
                        "ski unassessed: gear.ski.length_m em falta — recusando um comprimento inventado "
                        "(Raymer Cap. 11 trata esquis como dispositivo alternativo; Currey 1988)")],
            "issues": ["ski.length_m missing"],
        }
    length = float(ski["length_m"])
    if length <= 0 or not math.isfinite(length):
        return {
            "type": "ski", "status": "unassessed",
            "checks": [("asm:gear_position", None, "ski.length_m não positivo — unassessed")],
            "issues": ["ski.length_m non-positive"],
        }
    thick = float(ski.get("thickness_m") or 0.05)  # PRESSUPOSTO contact pad thickness when omitted
    tip = float(opts.get("tipback_deg", 15.0))
    prop_c = (opts["prop_clearance_m"] if opts.get("prop_clearance_m") is not None
              else _prop_clearance_default(opts.get("ski_prop_as", "taildragger")))
    P = _rotation_vertices(asm)
    discs = [c for c in asm.components if isinstance(c, Disc)]
    zf, zr = float(cg_fwd[2]), float(cg_aft[2])
    xf, xr = float(cg_fwd[0]), float(cg_aft[0])
    z_min = float(P[:, 2].min())
    disc_low = [float(d.bbox()[0][2]) for d in discs]
    # Mid attach: user or mid-CG (PRESSUPOSTO).
    if ski.get("attach_x") is not None:
        x_mid = float(ski["attach_x"])
        mid_note = "ski.attach_x dado"
    else:
        x_mid = 0.5 * (xf + xr)
        mid_note = (f"PRESSUPOSTO ski.attach_x = meio do intervalo de CG ({x_mid:.3f} m); "
                    "substituir por gear.ski.attach_x")
    x_fore = x_mid - 0.5 * length
    x_aft = x_mid + 0.5 * length
    # Ground under ski bottom.
    if opts.get("ground_z") is not None:
        zg = float(opts["ground_z"])
        given = True
        it = 0
    else:
        # Ski bottom clears prop by prop_c and sits below belly by thickness.
        zg = min([z_min - thick] + [z - prop_c - thick for z in disc_low])
        given, it = False, 1
    h = max(zf, zr) - zg
    # Tip-back about aft ski contact (like main wheel aft of CG for tricycle / like resting on ski).
    tipback = angle_from_vertical_deg(x_aft - xr, h) if x_aft >= xr else angle_from_vertical_deg(xr - x_aft, h)
    # For ski: require aft contact behind aft CG by tip angle (Raymer tip-back analogy on the contact patch).
    dx_req = h * math.tan(math.radians(tip))
    tip_ok = (x_aft + 1e-6 >= xr + dx_req) if h > 0 else False
    clear_prop = min([z - (zg + thick) for z in disc_low], default=math.inf)
    belly = z_min - (zg + thick)
    checks = []
    checks.append(("asm:gear_tipback", tip_ok,
                   f"contacto aft do esqui x = {x_aft:.3f} m vs CG traseiro {xr:.3f} m + "
                   f"{dx_req:.3f} m (tombo {tip:.0f}°, Raymer Cap. 11); tipback medido {tipback:.1f}°"))
    between = x_fore < xf + 1e-6 and x_aft > xr - 1e-6
    checks.append(("asm:gear_position", between,
                   f"esqui [{x_fore:.3f}, {x_aft:.3f}] m (L={length:.3f} m); CG "
                   f"({xf:.3f}–{xr:.3f} m) sobre o contacto"))
    if discs:
        checks.append(("asm:gear_prop_clearance", clear_prop + 1e-6 >= prop_c,
                       f"folga hélice ao topo do esqui {clear_prop:.3f} m (mín. {prop_c:.3f} m, "
                       f"14 CFR 23.925(a)(1) via solo do esqui)"))
    checks.append(("asm:gear_belly", belly >= -1e-6,
                   f"folga ventre ao topo do esqui {belly:.3f} m (espessura {thick:.3f} m)"))
    half = ski.get("half_track", opts.get("half_track"))
    t_req = min_half_track(x_aft, x_fore, xr, h, float(opts.get("overturn_max_deg", 63.0)))
    res = {
        "type": "ski", "status": "assessed", "ground_z": zg, "ground_z_given": given, "iterations": it,
        "h_cg": h, "x_main": x_fore, "x_tail": x_aft, "x_nose": None, "ski": {
            "length_m": length, "thickness_m": thick, "attach_x": x_mid,
            "x_fore": x_fore, "x_aft": x_aft,
        },
        "prop_clearance_m": clear_prop, "belly_clearance_m": belly, "tipback_deg": tipback,
        "half_track_min": t_req, "wheelbase": length,
        "notes": [mid_note,
                  f"Espessura do contacto {thick:.3f} m"
                  + (" (PRESSUPOSTO 0.05 m)" if ski.get("thickness_m") is None else ""),
                  "Método: contacto fore/aft do esqui como par de estações (Raymer Cap. 11); "
                  "sem dinâmica de neve"],
    }
    if half is not None:
        ov = overturn_angle_deg(x_aft, x_fore, float(half), xr, h)
        res["overturn_deg"] = ov
        checks.append(("asm:gear_overturn", ov <= float(opts.get("overturn_max_deg", 63.0)) + 1e-6,
                       f"capotagem {ov:.1f}° (máx. {opts.get('overturn_max_deg', 63):.0f}°)"))
    elif math.isfinite(t_req):
        checks.append(("asm:gear_overturn", True,
                       f"bitola mínima {2 * t_req:.3f} m para {opts.get('overturn_max_deg', 63):.0f}°"))
    else:
        checks.append(("asm:gear_overturn", False, "capotagem sem solução"))
    res["checks"] = checks
    return res


def draw_legs(layout: dict, opts: dict | None = None) -> list[dict]:
    """Body dicts for strut/oleo cylinders from ground to attach height (role ``gear_leg``).

    PRESSUPOSTO diameter ``gear.leg_diameter_m`` default 0.06 m (Currey envelopes the strut; no cited
    GA default diameter — replace when known). Returns [] when layout has no stations.
    """
    o = opts or {}
    if not o.get("draw_legs"):
        return []
    diam = float(o.get("leg_diameter_m") or 0.06)
    zg = layout.get("ground_z")
    h_cg = layout.get("h_cg")
    if zg is None or h_cg is None:
        return []
    # Attach roughly at CG height (PRESSUPOSTO: strut to wing/fuselage near h_cg above ground).
    z_attach = zg + float(h_cg)
    length = max(z_attach - zg, 1e-3)
    half = float(o["half_track"]) if o.get("half_track") is not None else (
        float(layout["half_track_min"]) if layout.get("half_track_min") and math.isfinite(layout["half_track_min"])
        else 0.4)
    legs = []
    kind = layout.get("type")
    stations = []
    if kind == "tricycle" and layout.get("x_nose") is not None:
        stations.append(("gear_nose_leg", float(layout["x_nose"]), 0.0, False))
        stations.append(("gear_main_leg", float(layout["x_main"]), half, True))
    elif kind in ("taildragger", "ski"):
        xm = layout.get("x_main")
        xt = layout.get("x_tail")
        if xm is not None:
            stations.append(("gear_main_leg", float(xm), half, True))
        if xt is not None:
            stations.append(("gear_tail_leg", float(xt), 0.0, False))
    for name, x, y, mirror in stations:
        # Local +x → aircraft +z via pitch = -90° (strut stands on the ground).
        legs.append({
            "type": "body", "name": name, "role": "gear_leg",
            "origin": [x, y, zg],
            "orientation": {"pitch": -90.0},
            "mirror": bool(mirror),
            "pod": {
                "length": length, "width": diam, "height": diam,
                "nose_frac": 0.05, "tail_frac": 0.05, "tail_scale": 1.0, "nose_scale": 1.0,
            },
            "mass_kg": float(o.get("leg_mass_kg") or 0.0) or None,
        })
    return legs


def check_retract(asm: Assembly, layout: dict, retract: dict | None) -> dict:
    """Sample wheel-centre arcs for interference with structure / discs.

    ``retract`` schema (per leg name or ``main`` / ``nose`` / ``tail``)::

        {main: {hinge: [x,y,z], axis: [0,1,0], angle_deg: 90, radius_m?: ...}, ...}

    Missing retract → unassessed. No dynamics / FEM — open geometric envelope only.
    """
    report: dict[str, Any] = {
        "method": "geometric retract envelope (wheel-centre arc vs assembly contains); "
                  "Currey 1988 kinematics at L0 as clearance only — no mechanism dynamics",
        "status": "unassessed",
        "legs": [],
    }
    if not retract:
        report["issues"] = ["gear.retract ausente — cinemática unassessed (sem inventar trajectória)"]
        return report
    if not isinstance(retract, dict):
        report["issues"] = ["gear.retract must be a mapping"]
        return report
    obstacles = [c for c in asm.components
                 if not (isinstance(c, Body) and (c.role or "") == "gear_leg")]
    any_assessed = False
    for leg_name, spec in retract.items():
        if not isinstance(spec, dict):
            report["legs"].append({"leg": leg_name, "status": "unassessed",
                                   "issues": ["retract entry must be a mapping"]})
            continue
        if spec.get("hinge") is None or spec.get("axis") is None or spec.get("angle_deg") is None:
            report["legs"].append({
                "leg": leg_name, "status": "unassessed",
                "issues": ["hinge, axis e angle_deg obrigatórios — sem trajectória inventada"],
            })
            continue
        hinge = np.asarray(spec["hinge"], float)
        axis = np.asarray(spec["axis"], float)
        nrm = np.linalg.norm(axis)
        if nrm < 1e-12:
            report["legs"].append({"leg": leg_name, "status": "unassessed",
                                   "issues": ["axis nulo"]})
            continue
        axis = axis / nrm
        ang = math.radians(float(spec["angle_deg"]))
        # Wheel centre at down position: from layout ground contact under the leg station.
        if spec.get("wheel_center") is not None:
            w0 = np.asarray(spec["wheel_center"], float)
        else:
            x_key = {"nose": "x_nose", "main": "x_main", "tail": "x_tail"}.get(leg_name, "x_main")
            xw = layout.get(x_key)
            if xw is None:
                report["legs"].append({"leg": leg_name, "status": "unassessed",
                                       "issues": [f"sem {x_key} no layout para o centro da roda"]})
                continue
            y = float(spec.get("y", layout.get("half_track_min") or 0.4 if leg_name == "main" else 0.0))
            w0 = np.array([float(xw), y, float(layout.get("ground_z") or 0.0)], float)
        # Rodrigues rotation of (w0 − hinge) about axis.
        hits = []
        samples = []
        n_samp = int(spec.get("samples") or 24)
        for i in range(n_samp + 1):
            th = ang * i / n_samp
            v = w0 - hinge
            k = axis
            v_rot = (v * math.cos(th) + np.cross(k, v) * math.sin(th)
                     + k * np.dot(k, v) * (1 - math.cos(th)))
            p = hinge + v_rot
            samples.append(p.tolist())
            for obs in obstacles:
                try:
                    clr = float(np.max(obs.contains(p.reshape(1, 3))))
                except Exception:
                    continue
                if clr > 0.0:
                    hits.append({"obstacle": obs.name, "point": p.tolist(), "penetration_m": clr})
                    break
        any_assessed = True
        report["legs"].append({
            "leg": leg_name, "status": "interference" if hits else "clear",
            "angle_deg": float(spec["angle_deg"]), "samples": len(samples),
            "hits": hits[:5], "wheel_center_down": w0.tolist(),
        })
    report["status"] = ("assessed" if any_assessed and report["legs"]
                        else "unassessed")
    if any_assessed:
        report["ok"] = all(L.get("status") == "clear" for L in report["legs"] if L.get("status") != "unassessed")
        if report.get("ok"):
            msg = "recolha sem interferência estrutural/disco"
        else:
            bits = []
            for L in report["legs"]:
                if L.get("status") == "interference":
                    obs = [h["obstacle"] for h in (L.get("hits") or [])]
                    bits.append(f"{L['leg']}→{obs}")
            msg = ("recolha com interferência: " + ", ".join(bits)) if bits else "recolha unassessed"
        report["checks"] = [(
            "asm:gear_retract",
            None if report["status"] == "unassessed" else bool(report.get("ok")),
            msg,
        )]
    return report



# ------------------------------------------------------------------------------------------------ tip skids
# Currey 1988 / Raymer Sec. 18.2 / Sadraey 2012 Sec. 9.7: E = η N δ.
# Solid rubber/composite shoe (not an oleo): η ≈ 0.5 (Currey, steel/rubber spring; oleo ≈ 0.8).
# Stroke, shoe length and the installation-mass floor are PRESSUPOSTO (replace with a drawing).
SKID_STROKE_M = 0.025
SKID_ETA = 0.50
SKID_SHOE_LENGTH_M = 0.08
SKID_MASS_MIN_KG = 0.08          # per side, fittings + shoe (PRESSUPOSTO installation floor)
SKID_NONOPT = 1.25
SKID_SOURCE = ("Raymer 2018 Ch. 11 (outrigger / tip gear on narrow-track layouts); energy E = η N δ, "
               "Currey 1988 / Raymer Sec. 18.2 / Sadraey 2012 Sec. 9.7")


def wing_tip_point(asm: Assembly) -> dict | None:
    """Lowest point near the tip of the main wing (same convention as the 6-DOF tip bumper)."""
    from .sizing import main_wing
    try:
        w, gw = main_wing(asm)
    except ValueError:
        return None
    V, _ = w.mesh()
    ymax = float(np.max(np.abs(V[:, 1])))
    tip = V[np.abs(V[:, 1]) >= 0.98 * ymax]
    if tip.size == 0:
        return None
    k = int(np.argmin(tip[:, 2]))
    return {"x": float(tip[k, 0]), "y": ymax, "z": float(tip[k, 2]), "b": float(gw["b"])}


def size_tip_skids(asm: Assembly, layout: dict, W_N: float, *, Ixx_kgm2: float | None = None,
                   mass_kg: float | None = None, opts: dict | None = None) -> dict:
    """Size a pair of wing-tip skids (energy method). ``opts`` is ``gear.tip_skids`` (True or a dict).

    Design energy: the tip effective mass dropped through the static tip-clearance height
    (PRESSUPOSTO conservative: the tip 'falls' from its parked height). m_eff = 1/(1/m + y²/I_xx)
    when I_xx is given, otherwise m_eff = m (upper bound). N_des = n_ult E / (η δ).
    """
    o = opts if isinstance(opts, dict) else {}
    tip = wing_tip_point(asm)
    if not tip or layout.get("ground_z") is None or layout.get("x_main") is None:
        return {"status": "unassessed", "issue": "sem ponta de asa ou trem colocado — patins unassessed"}
    if not (W_N and W_N > 0):
        return {"status": "unassessed", "issue": "W ausente — patins não dimensionados (geometria só)"}
    zg, xm = float(layout["ground_z"]), float(layout["x_main"])
    thg = math.radians(float(layout.get("ground_attitude_deg") or 0.0))
    h_tip = (tip["z"] - zg) * math.cos(thg) - (tip["x"] - xm) * math.sin(thg)
    half = layout.get("half_track") if layout.get("half_track") is not None else layout.get("half_track_min")
    if half is None:
        return {"status": "unassessed", "issue": "meia-bitola ausente"}
    half = float(half)
    y = tip["y"]
    phi = math.degrees(math.atan2(max(h_tip, 0.0), max(y - half, 1e-9)))
    stroke = float(o.get("stroke_m", SKID_STROKE_M))
    eta = float(o.get("eta", SKID_ETA))
    n_ult = float(o.get("n_ult", 1.5))
    L = float(o.get("shoe_length_m", SKID_SHOE_LENGTH_M))
    m_min = float(o.get("mass_min_kg", SKID_MASS_MIN_KG))
    m = float(mass_kg) if mass_kg else W_N / 9.80665
    if Ixx_kgm2 and Ixx_kgm2 > 0:
        m_eff = 1.0 / (1.0 / m + y * y / Ixx_kgm2)
        m_eff_note = "m_eff = 1/(1/m + y²/I_xx)"
    else:
        m_eff = m
        m_eff_note = "I_xx ausente: m_eff = m (limite superior, conservador)"
    E = m_eff * 9.80665 * max(h_tip, 0.0)
    if eta * stroke <= 0:
        return {"status": "unassessed", "issue": "η δ ≤ 0"}
    N_des = n_ult * E / (eta * stroke)
    from ..structures import MATERIALS
    mat = MATERIALS["al2024_t3"]
    A = N_des / mat["sigma_cap"] if mat["sigma_cap"] else 0.0
    m_section = A * L * mat["rho"] * SKID_NONOPT
    m_each = max(m_section, m_min)
    ok = h_tip > 0 and N_des > 0
    return {
        "status": "assessed", "ok": ok, "source": SKID_SOURCE,
        "n_skids": 2, "tip_x_m": tip["x"], "tip_y_m": y, "tip_z_m": tip["z"],
        "h_tip_static_m": float(h_tip),
        "phi_contact_about_wheel_deg": phi,
        "stroke_m": stroke, "eta": eta, "n_ult": n_ult,
        "eta_note": "PRESSUPOSTO: sapata de borracha/compósito (Currey, mola sólida ≈ 0,5; oleo ≈ 0,8)",
        "stroke_note": "PRESSUPOSTO: curso 25 mm (substituir por um desenho)",
        "m_eff_kg": float(m_eff), "m_eff_note": m_eff_note,
        "energy_J": float(E), "P_des_N": float(N_des),
        "shoe_area_m2": float(A), "shoe_length_m": L,
        "mass_section_kg": float(m_section), "mass_min_kg": m_min,
        "mass_each_kg": float(m_each), "mass_kg": float(2 * m_each),
        "material": mat["name"],
        "mass_note": ("secção teórica A = N_des/Fcy (Al 2024-T3 MMPDS) × comprimento × ρ × 1,25; "
                      "piso de instalação PRESSUPOSTO por sapata"),
    }



# -------------------------------------------------------------------------------- gear drag / side load / max track
# Reference strut lengths: the PRESSUPOSTO defaults of Raymer Eq. 15.50/15.51 (weights_detailed).
try:
    from ..weights_detailed import DEFAULT_MAIN_GEAR_LENGTH_M
except ImportError:  # pragma: no cover
    DEFAULT_MAIN_GEAR_LENGTH_M = 0.60
DEFAULT_NOSE_GEAR_LENGTH_M = 0.50


def _leg_lengths(layout: dict, opts: dict | None = None) -> dict | None:
    """Main and nose strut lengths (vertical legs, PRESSUPOSTO).

    Prefer explicit lengths (layout or ``weights.components`` / ``opts``:
    ``main_gear_length_m``, ``nose_gear_length_m`` — the same inputs as Raymer
    Eq. 15.50/15.51). Else main ≈ h_cg (attach near the CG height) and nose =
    main + ``nose_strut_extension_m``. The lowest-airframe-to-ground clearance
    is *not* the strut length.
    """
    o = opts or {}
    L_main = (layout.get("main_leg_length_m") if layout.get("main_leg_length_m") is not None
              else o.get("main_gear_length_m"))
    L_nose = (layout.get("nose_leg_length_m") if layout.get("nose_leg_length_m") is not None
              else o.get("nose_gear_length_m"))
    if L_main is None and layout.get("h_cg") is not None:
        L_main = float(layout["h_cg"])
    if L_main is None:
        return None
    if L_nose is None:
        ext = float(layout.get("nose_strut_extension_m") or 0.0)
        L_nose = float(L_main) + ext
    return {"main_m": float(L_main), "nose_m": float(L_nose)}


def scale_fixed_gear_drag_area(area_m2: float, layout: dict, *,
                               ref_main_m: float = DEFAULT_MAIN_GEAR_LENGTH_M,
                               ref_nose_m: float = DEFAULT_NOSE_GEAR_LENGTH_M,
                               length_opts: dict | None = None) -> dict:
    """Scale a lumped fixed-gear equivalent parasite area with strut length.

    ``area_m2`` is the YAML ``extra_drag_areas_m2.fixed_gear`` (wheels + struts, no
    split). ΣL / ΣL_ref uses two mains + one nose. Missing lengths → unassessed
    (unknown ≠ a silent factor of 1).
    """
    if area_m2 is None or area_m2 < 0 or not math.isfinite(area_m2):
        return {"status": "unassessed", "issue": "área de arrasto do trem ausente ou inválida"}
    legs = _leg_lengths(layout, length_opts)
    if not legs:
        return {"status": "unassessed", "issue": "comprimentos das pernas ausentes — área do trem não escalada"}
    L = 2.0 * legs["main_m"] + legs["nose_m"]
    Lref = 2.0 * ref_main_m + ref_nose_m
    if Lref <= 0:
        return {"status": "unassessed", "issue": "comprimento de referência ≤ 0"}
    factor = L / Lref
    return {
        "status": "assessed",
        "source": ("área equivalente do trem escalada com ΣL das pernas / omissão "
                   f"{ref_main_m:.2f}/{ref_nose_m:.2f} m das Eqs. 15.50/15.51 de Raymer"),
        "area_given_m2": float(area_m2),
        "area_scaled_m2": float(area_m2 * factor),
        "factor": float(factor),
        "L_main_m": legs["main_m"], "L_nose_m": legs["nose_m"],
        "L_sum_m": float(L), "L_ref_m": float(Lref),
        "note": "sem divisão roda/perna, escala-se a área completa (PRESSUPOSTO)",
    }


def size_gear_side_load_structure(layout: dict, W_N: float, *,
                                  nose_fraction: float | None = None,
                                  diameter_m: float | None = None,
                                  n_ult: float = 1.5,
                                  length_opts: dict | None = None,
                                  side_factor: float = 1.0) -> dict:
    """Vertical-leg beam/column check under 14 CFR 23.485 side load + 1.33 × static vertical.

    ``side_factor`` (default 1, i.e. 23.485 as written) multiplies both side loads: a gear designed above the
    regulatory minimum (design choice, e.g. to the measured 6-DOF touchdown side load).

    23.485(c) (pré-Amdt 23-64; Amdt 23-45): 0,5 W inboard on one main wheel, 0,33 W
    outboard on the other, combined with a vertical load of 1.33 times the static
    load at that wheel. Material Al 2024-T3 (MMPDS typical Fcy / Fsu). Legs are
    treated as vertical cantilevers (PRESSUPOSTO; no drag brace is modelled).
    Missing W or lengths → unassessed.
    """
    if not (W_N and W_N > 0):
        return {"status": "unassessed", "issue": "W ausente — estrutura às cargas laterais unassessed"}
    legs = _leg_lengths(layout, length_opts)
    if not legs:
        return {"status": "unassessed", "issue": "comprimentos das pernas ausentes"}
    from ..structures import MATERIALS
    mat = MATERIALS["al2024_t3"]
    d = float(diameter_m) if diameter_m else 0.06
    d_note = None if diameter_m else "PRESSUPOSTO leg_diameter_m = 0.06 m (Currey strut envelope; substituir)"
    # wall: start at MMPDS t_min_web; grow if needed (not below t_min)
    t_min = float(mat.get("t_min_web") or 0.51e-3)
    nf = nose_fraction
    if nf is None:
        band = layout.get("nose_fraction")
        if isinstance(band, (list, tuple)) and band:
            nf = 0.5 * (float(band[0]) + float(band[-1]))
        elif isinstance(band, (int, float)):
            nf = float(band)
        else:
            nf = 0.12  # mid of Raymer's 8–15 % band, only if the layout has no fraction
    nf = min(max(float(nf), 0.0), 0.5)
    # static load on *one* main wheel; 1.33 × that is the 23.485 vertical at the wheel
    P_stat = W_N * (1.0 - nf) / 2.0
    P_vert = 1.33 * P_stat
    F_in, F_out = 0.5 * W_N * float(side_factor), 0.33 * W_N * float(side_factor)
    F_side = max(F_in, F_out)  # inboard 0.5 W is critical
    L = legs["main_m"]
    # size a circular tube: σ = P/A + M (d/2)/I ≤ Fcy / n_ult; τ = V/A ≤ Fsu / n_ult
    t = t_min
    allow_c, allow_s = mat["sigma_cap"] / n_ult, mat["tau"] / n_ult
    rho = mat["rho"]

    def props(th):
        di = max(d - 2.0 * th, 0.0)
        A = math.pi / 4.0 * (d * d - di * di)
        I = math.pi / 64.0 * (d ** 4 - di ** 4)
        M = F_side * L
        sig = (P_vert / A if A else math.inf) + (M * (d / 2.0) / I if I else math.inf)
        tau = F_side / A if A else math.inf
        mass = A * L * rho * 2.0  # two main legs; nose checked only for vertical (no 23.485 side on the nose here)
        return A, I, sig, tau, mass

    A, I, sig, tau, mass = props(t)
    while (sig > allow_c or tau > allow_s) and t < 0.49 * d:
        t = min(t * 1.25, 0.49 * d)
        A, I, sig, tau, mass = props(t)
    rf_c = allow_c / sig if sig else math.inf
    rf_s = allow_s / tau if tau else math.inf
    ok = bool(sig <= allow_c + 1e-9 and tau <= allow_s + 1e-9)
    # Euler (cantilever, K=2, PRESSUPOSTO: fixed at the attach, free at the wheel)
    P_cr = (math.pi ** 2) * mat["E"] * I / (2.0 * L) ** 2 if L and I else 0.0
    rf_buck = P_cr / P_vert if P_vert else math.inf
    return {
        "status": "assessed", "ok": ok and rf_buck >= 1.0,
        "source": ("14 CFR 23.485(c) (pré-Amdt 23-64; Amdt 23-45): 0,5 W para dentro / 0,33 W para "
                   "fora, vertical 1,33 × carga estática na roda; perna vertical em consola "
                   "(PRESSUPOSTO, sem braço de arrasto); Al 2024-T3 MMPDS typical, FS "
                   f"{n_ult:g}"),
        "diameter_m": d, "wall_m": float(t), "diameter_note": d_note,
        "L_main_m": L, "nose_fraction": nf,
        "F_side_N": float(F_side), "P_vert_N": float(P_vert),
        "sigma_MPa": float(sig / 1e6), "tau_MPa": float(tau / 1e6),
        "allow_sigma_MPa": float(allow_c / 1e6), "allow_tau_MPa": float(allow_s / 1e6),
        "RF_bending": float(rf_c), "RF_shear": float(rf_s), "RF_buckling": float(rf_buck),
        "P_cr_N": float(P_cr), "mass_two_mains_kg": float(mass), "side_factor": float(side_factor),
        "K_euler": 2.0, "K_note": "PRESSUPOSTO: consola (K = 2) sem braço de arrasto",
    }


def max_track_sadraey_9532(layout: dict, W_N: float, EI_Nm2: float | None,
                           delta_allow_m: float | None = None) -> dict:
    """Sadraey 2012 Sec. 9.5.3.2: maximum track from mid-span deflection of the wing.

    Front view: the wing is a simply-supported beam, the two main wheels are the
    supports, the aircraft weight is the central load. Mid-span deflection
    δ = W T³ / (48 EI) (standard beam theory). Extra dihedral ΔΓ = atan(2δ / T)
    is the mechanism Sadraey names (deflection appears as dihedral and degrades
    lateral stability). The book's numerical δ allowable is not used unless the
    caller supplies ``delta_allow_m`` — otherwise the deflection is reported and
    the check stays unassessed (unknown ≠ pass). Missing W, track or EI →
    unassessed.
    """
    half = layout.get("half_track")
    if half is None:
        half = layout.get("half_track_min")
    if half is None or not (W_N and W_N > 0):
        return {"status": "unassessed", "issue": "bitola ou W ausente — Sadraey 9.5.3.2 unassessed"}
    T = 2.0 * float(half)
    if T <= 0:
        return {"status": "unassessed", "issue": "bitola ≤ 0"}
    src = ("Sadraey 2012 Sec. 9.5.3.2 (integridade estrutural: viga simplesmente apoiada nas "
           "rodas principais, deflexão a meio-vão); δ = W T³/(48 EI), teoria clássica de vigas")
    if not (EI_Nm2 and EI_Nm2 > 0):
        return {"status": "unassessed", "issue": "EI da asa no vão do trem ausente",
                "source": src, "track_m": T, "W_N": float(W_N)}
    delta = W_N * T ** 3 / (48.0 * EI_Nm2)
    dgamma = math.degrees(math.atan2(2.0 * delta, T))
    out = {
        "status": "assessed", "source": src,
        "track_m": T, "W_N": float(W_N), "EI_Nm2": float(EI_Nm2),
        "delta_m": float(delta), "delta_dihedral_deg": float(dgamma),
        "formula": "delta = W T^3 / (48 EI); Delta_Gamma = atan(2 delta / T)",
    }
    if delta_allow_m is not None:
        T_max = (48.0 * EI_Nm2 * float(delta_allow_m) / W_N) ** (1.0 / 3.0)
        out["delta_allow_m"] = float(delta_allow_m)
        out["T_max_m"] = float(T_max)
        out["ok"] = bool(T <= T_max + 1e-9)
    else:
        out["ok"] = None
        out["note"] = ("δ admissível de Sadraey não citado aqui; a deflexão e o ΔΓ são reportados, "
                       "o passa/falha fica unassessed (desconhecido ≠ passa)")
    return out


def conservative_wing_EI_at_root(asm: Assembly) -> dict | None:
    """Lower-bound root EI of a min-gauge rectangular box (Al 2024-T3 t_min_skin).

    Used only to give Sadraey 9.5.3.2 a conservative number when a sized wingbox
    EI is not on the layout. PRESSUPOSTO section: spars at 0.25c and 0.70c, height
    = t/c × c at the root, skins at MMPDS t_min_skin. A thinner box deflects more,
    so T_max is conservative (lower). Missing wing → None.
    """
    from .sizing import main_wing
    from ..structures import MATERIALS
    try:
        w, gw = main_wing(asm)
    except ValueError:
        return None
    c = float(getattr(w, "c_root", None) or gw.get("c_root") or 0.0)
    tc = float(getattr(w, "tc_root", None) or gw.get("tc_root") or gw.get("tc") or 0.0)
    if c <= 0 or tc <= 0:
        return None
    mat = MATERIALS["al2024_t3"]
    t = float(mat["t_min_skin"])
    h = tc * c
    width = (0.70 - 0.25) * c  # PRESSUPOSTO spar stations when the box is not sized here
    # two skins (bending about x, vertical load): 2 * (width * t) * (h/2)^2
    # two webs: 2 * (t * h^3 / 12)
    I = 2.0 * (width * t) * (h / 2.0) ** 2 + 2.0 * (t * h ** 3 / 12.0)
    return {"EI_Nm2": float(mat["E"] * I), "I_m4": float(I), "c_root_m": c, "tc_root": tc,
            "t_skin_m": t, "box_width_m": width, "box_height_m": h,
            "note": "PRESSUPOSTO: caixão 0,25–0,70 c, peles à espessura mínima MMPDS (limite inferior de EI)"}


def apply_gear_devices(spec: dict, layout: dict) -> tuple[dict, dict]:
    """Opt-in post-pass: draw legs, tip skids, retract check.

    Returns ``(new_spec_or_same, devices_report)``. Does nothing when no flag is set.
    """
    gear = spec.get("gear") or {}
    report: dict[str, Any] = {"schema": "gear_devices", "level": "L0"}
    out = spec
    legs = draw_legs(layout, gear)
    if legs:
        out = copy.deepcopy(spec)
        comps = out.setdefault("assembly", {}).setdefault("components", [])
        # Drop previous auto legs so re-entry is idempotent.
        comps[:] = [c for c in comps if not (c.get("role") == "gear_leg" and str(c.get("name", "")).startswith("gear_"))]
        comps.extend(legs)
        report["drawn_legs"] = [{"name": c["name"], "origin": c["origin"],
                                 "length_m": c["pod"]["length"], "diameter_m": c["pod"]["width"]}
                                for c in legs]
        report["leg_diameter_note"] = (
            None if gear.get("leg_diameter_m") is not None else
            "PRESSUPOSTO leg_diameter_m = 0.06 m (Currey strut envelope; substituir)")
    ts = gear.get("tip_skids")
    if ts:
        W = float((gear.get("_W_N") or layout.get("W_N") or 0.0) or 0.0)
        if not W:
            # allow the caller to put W on the layout; otherwise geometry-only unassessed
            W = float(layout.get("W_N") or 0.0)
        asm = Assembly.from_dict((out if legs else spec)["assembly"])
        report["tip_skids"] = size_tip_skids(
            asm, layout, W, Ixx_kgm2=layout.get("Ixx_kgm2"), mass_kg=layout.get("mass_kg"),
            opts=ts)
        sk = report["tip_skids"]
        layout["tip_skids"] = sk
        if sk.get("status") == "assessed":
            layout.setdefault("checks", []).append(
                ("asm:gear_tip_skids", bool(sk.get("ok")),
                 f"patins de ponta: N_des {sk['P_des_N']:.0f} N, curso {sk['stroke_m']*1e3:.0f} mm, "
                 f"massa {sk['mass_kg']:.2f} kg (2×), folga estática {sk['h_tip_static_m']*1e3:.0f} mm, "
                 f"φ contacto {sk['phi_contact_about_wheel_deg']:.1f}° ({sk['source']})"))
        else:
            layout.setdefault("checks", []).append(
                ("asm:gear_tip_skids", None, f"patins de ponta unassessed: {sk.get('issue')}"))
    if gear.get("retract") is not None or gear.get("check_retract"):
        asm = Assembly.from_dict((out if legs else spec)["assembly"])
        report["retract"] = check_retract(asm, layout, gear.get("retract"))
        if report["retract"].get("checks"):
            layout.setdefault("checks", []).extend(report["retract"]["checks"])
    elif gear.get("draw_legs") and "retract" not in gear:
        report["retract"] = {
            "status": "unassessed",
            "issues": ["gear.retract ausente — cinemática unassessed"],
        }
    return out, report


def leg_drawing_lines(layout: dict, opts: dict | None = None) -> list[dict]:
    """Plan (x–y) and side (x–z) line segments for drawn contacts — feeds DXF / plan views.

    Each item: ``{view: "plan"|"side", a: [u,v], b: [u,v], name}``. Units metres.
    """
    o = opts or {}
    zg = float(layout.get("ground_z") or 0.0)
    h = float(layout.get("h_cg") or 0.3)
    half = float(o["half_track"]) if o.get("half_track") is not None else float(layout.get("half_track_min") or 0.4)
    if not math.isfinite(half):
        half = 0.4
    lines = []
    kind = layout.get("type")
    pts = []
    if kind == "tricycle" and layout.get("x_nose") is not None:
        pts.append(("nose", float(layout["x_nose"]), 0.0))
        pts.append(("main", float(layout["x_main"]), half))
        pts.append(("main_L", float(layout["x_main"]), -half))
    elif kind in ("taildragger", "ski") or kind in TAILDRAGGER_TYPES or kind in SKI_TYPES:
        if layout.get("x_main") is not None:
            pts.append(("main", float(layout["x_main"]), half))
            pts.append(("main_L", float(layout["x_main"]), -half))
        if layout.get("x_tail") is not None:
            pts.append(("tail", float(layout["x_tail"]), 0.0))
    for name, x, y in pts:
        lines.append({"view": "plan", "name": name, "a": [x, -0.02], "b": [x, 0.02]} if abs(y) < 1e-9 else
                      {"view": "plan", "name": name, "a": [x, y - 0.02], "b": [x, y + 0.02]})
        lines.append({"view": "side", "name": name + "_strut",
                      "a": [x, zg], "b": [x, zg + h]})
    return lines
