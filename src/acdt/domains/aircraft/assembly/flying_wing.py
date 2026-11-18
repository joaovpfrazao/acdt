# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in flying-wing helpers: size tip fins/winglets from directional volume, place tricycle gear.

Named layout options under ``assumptions.assembly.options.flying_wing`` are *shortcuts* that mutate
the generic component drawing before the W0 loop. They never invent a closed list of allowed
layouts — any hand-drawn assembly remains valid when the block is omitted.

Methods
-------
* Winglet / fin area from the Raymer (2018) Eq. 6.29 vertical volume coefficient
  ``c_VT = Σ S·|sin Γ|·l_v / (S_w·b)`` (same projection already used by
  :func:`.handling.vertical_volume`). Target ``c_vt`` must be supplied; missing target → refuse
  (unassessed / no silent invented volume). Surfaces with role/kind winglet|fin|vtail are scaled
  by their chords only (span and tip station fixed) so c_VT matches the target. Dutch-roll / spiral remain the existing MIL-F-8785C ``hq:*`` checks after AVL.
* Landing gear: switch ``gear.type`` from ``none`` to ``tricycle`` and let
  :func:`.sizing.gear_layout` place tip-back / nose-load / rotation / 14 CFR 23.925 prop clearance
  on the flying-wing mesh. Failures stay failures (residuals in ``asm:gear_*``), never a fake pass.
"""
from __future__ import annotations

import copy
import math
from typing import Any

from .assembly import Assembly
from .components import Surface
from .handling import vertical_volume
from .sizing import classify_surface, main_wing, surface_geometry


def _winglet_surfaces(asm: Assembly) -> list[Surface]:
    surfs = [c for c in asm.components if isinstance(c, Surface) and not c.mirrored_image]
    if not surfs:
        return []
    areas = {s.name: surface_geometry(s)["S"] for s in surfs}
    largest = max(areas, key=areas.get)
    out = []
    for s in surfs:
        g = surface_geometry(s)
        kind = classify_surface(s, g, s.name == largest)
        role = (s.role or "").lower()
        if kind in ("vtail", "vee") or any(k in role for k in ("winglet", "fin", "deriva", "rudder")):
            if s.name == largest:
                continue  # never resize the main wing
            out.append(s)
    return out


def measure_c_vt(asm: Assembly) -> float:
    """Raymer Eq. 6.29 vertical volume coefficient measured on the drawing."""
    _, gw = main_wing(asm)
    return float(vertical_volume(asm, gw["x_ac"]))


def size_winglets_to_c_vt(spec: dict, c_vt_target: float, *, tol: float = 1e-3) -> dict[str, Any]:
    """Scale winglet/fin planforms so measured c_VT equals ``c_vt_target`` (Raymer Eq. 6.29).

    Returns a report. Mutates ``spec['assembly']`` in place. If no directional surface exists or
    the target is non-positive, returns ``status='unassessed'`` without inventing geometry.
    """
    report: dict[str, Any] = {
        "method": "Raymer 2018 Eq. 6.29 vertical volume (S·|sin Γ|·l_v)/(S_w·b); "
                  "chord-only scale of winglet/fin panels (span/arm fixed)",
        "c_vt_target": float(c_vt_target),
        "status": "unassessed",
    }
    if c_vt_target is None or not math.isfinite(float(c_vt_target)) or float(c_vt_target) <= 0:
        report["issues"] = ["c_vt_target missing or non-positive — refusing a silent invented volume"]
        return report
    asm = Assembly.from_dict(spec["assembly"])
    fins = _winglet_surfaces(asm)
    c0 = measure_c_vt(asm)
    report["c_vt_before"] = c0
    report["surfaces"] = [s.name for s in fins]
    if not fins:
        report["issues"] = ["no winglet/fin/vtail surface to size — unassessed"]
        return report
    if c0 <= 1e-9:
        report["issues"] = ["measured c_VT ≈ 0 (arm or |sin Γ| null) — cannot scale; unassessed"]
        return report
    # Chord-only scales (span / tip station fixed). On a swept winglet, larger chords also move
    # x_ac slightly, so iterate: k ← k · c_target / c_meas (Raymer Eq. 6.29).
    names = {s.name for s in fins}
    history = []
    k_tot = 1.0
    c_now = c0
    for _ in range(8):
        if abs(c_now - float(c_vt_target)) <= max(tol, 0.02 * float(c_vt_target)):
            break
        if c_now <= 1e-12:
            break
        k = float(c_vt_target) / c_now
        k_tot *= k
        for c in spec["assembly"]["components"]:
            if c.get("name") not in names:
                continue
            if "panel" in c:
                p = c["panel"]
                for key in ("root_chord", "tip_chord"):
                    if key in p and p[key] is not None:
                        p[key] = float(p[key]) * k
            elif "sections" in c:
                for sec in c["sections"]:
                    sec["chord"] = float(sec["chord"]) * k
        c_now = measure_c_vt(Assembly.from_dict(spec["assembly"]))
        history.append({"k_step": k, "c_vt": c_now})
    report["scale_chord_total"] = k_tot
    report["history"] = history
    report["c_vt_after"] = c_now
    report["residual"] = c_now - float(c_vt_target)
    report["status"] = ("assessed" if abs(c_now - float(c_vt_target)) <= max(tol, 0.05 * float(c_vt_target))
                        else "residual")
    return report


def enable_tricycle_gear(spec: dict, gear_opts: dict | None = None) -> dict[str, Any]:
    """Replace ``gear: none`` with a tricycle request for :func:`.sizing.gear_layout`.

    Does not invent a pass: placement and ``asm:gear_*`` checks run later on the mesh.
    """
    report: dict[str, Any] = {
        "method": "Raymer Ch. 11 tricycle placement + 14 CFR 23.925 prop clearance via gear_layout",
        "status": "requested",
    }
    prev = spec.get("gear") or {"type": "none"}
    report["previous"] = copy.deepcopy(prev)
    if (prev.get("type") or "none") not in ("none", None) and not (gear_opts or {}).get("replace", True):
        report["status"] = "skipped"
        report["issues"] = [f"gear already '{prev.get('type')}' — not replaced"]
        return report
    g = {"type": "tricycle", "tipback_deg": 15.0, "nose_fraction": [0.08, 0.15],
         "overturn_max_deg": 63.0, "rotation_min_deg": 10.0}
    if isinstance(prev, dict):
        for k, v in prev.items():
            if k != "type" and v is not None:
                g[k] = v
    if gear_opts:
        g.update({k: v for k, v in gear_opts.items() if k != "replace" and v is not None})
    g["type"] = "tricycle"
    spec["gear"] = g
    report["gear"] = {k: g[k] for k in g}
    nf = g.get("nose_fraction") or [0.08, 0.15]
    if list(nf) != [0.08, 0.15]:
        report["nose_fraction_note"] = (
            f"PRESSUPOSTO nose_fraction {list(nf)} (Raymer Ch. 11 publishes 8–15 %); "
            "use only when the 8–15 % tip-back band is empty for the CG travel")
    return report



def extend_fuselage_for_gear(spec: dict, fw: dict) -> dict:
    """Lengthen the primary fuselage body forward until Raymer Ch. 11 placement succeeds.

    PRESSUPOSTO layout change. Uses :func:`.sizing.analyse` loading CGs (not a synthetic probe) so
    the stretch matches the masses that gear_layout will see later. Still reports infeasible when
    ``max_fuselage_length_factor`` is exhausted — never a fake pass.
    """
    from .sizing import analyse
    report = {
        "method": "PRESSUPOSTO: lengthen fuselage pod forward until gear_layout finds a nose station "
                  "for the assembly loading CGs (Raymer Ch. 11 8–15 % band)",
        "status": "unassessed",
    }
    bodies = [c for c in spec["assembly"]["components"]
              if c.get("type") == "body" and (c.get("role") or "") in ("fuselage", "")]
    if not bodies:
        bodies = [c for c in spec["assembly"]["components"] if c.get("type") == "body" and "pod" in c]
    if not bodies:
        report["issues"] = ["no fuselage body to extend"]
        return report
    body = bodies[0]
    pod = body.setdefault("pod", {})
    L0 = float(pod.get("length") or 0)
    if L0 <= 0:
        report["issues"] = ["fuselage pod.length missing"]
        return report
    origin = list(body.get("origin") or [0.0, 0.0, 0.0])
    max_fac = float(fw.get("max_fuselage_length_factor") or 3.0)
    report["length_before_m"] = L0
    report["origin_before"] = list(origin)
    # Use the drawing's flight block as-is when present. Do NOT invent Wf_kg on a light
    # demo flight (that shifts the CG and falsely blocks the nose station).
    if spec.get("flight"):
        flight = dict(spec["flight"])
    else:
        flight = {"W0_kg": 140.0, "V_m_s": 40.0, "altitude_m": 1000.0, "Wf_kg": 20.0, "payload_kg": 20.0}
    fac = 1.0
    last_gear = {}
    for _ in range(28):
        pod["length"] = L0 * fac
        body["origin"] = [origin[0] - (pod["length"] - L0), origin[1], origin[2]]
        try:
            out = analyse(spec, flight)
            g = out.gear or {}
        except Exception as ex:  # pragma: no cover
            report["issues"] = [f"analyse failed while stretching: {ex}"]
            return report
        last_gear = {k: g.get(k) for k in ("x_nose", "x_main", "h_cg", "tipback_deg")}
        if g.get("x_nose") is not None:
            pos = next((c for c in g.get("checks") or [] if c[0] == "asm:gear_position"), None)
            ok_pos = bool(pos and pos[1])
            report.update({
                "status": "assessed" if ok_pos else "partial",
                "length_after_m": float(pod["length"]),
                "length_factor": fac,
                "origin_after": list(body["origin"]),
                "gear_probe": last_gear,
                "asm_gear_position": ok_pos,
            })
            if not ok_pos and pos:
                report["issues"] = [pos[2]]
            return report
        next_fac = fac * 1.08
        if next_fac > max_fac + 1e-9:
            if fac < max_fac - 1e-9:
                fac = max_fac
                continue  # one last try at the exact cap
            break
        fac = next_fac
    # Revert geometry — never leave a failed stretch on the drawing (would blow empty weight).
    pod["length"] = L0
    body["origin"] = list(origin)
    report.update({
        "status": "infeasible",
        "length_after_m": L0,
        "length_factor": 1.0,
        "origin_after": list(origin),
        "gear_probe": last_gear,
        "issues": ["no Raymer Ch. 11 nose station within max_fuselage_length_factor "
                   f"({max_fac:g}) for the assembly loading CGs; fuselage restored"],
        "reverted": True,
    })
    return report


def apply_flying_wing_options(spec: dict, mission_flight: dict | None = None) -> tuple[dict, dict | None]:
    """Apply ``options.flying_wing`` shortcuts to a loaded assembly spec. No-op if absent/disabled.

    Schema (all opt-in)::

        options:
          flying_wing:
            size_winglets: true
            c_vt: 0.10                 # required when size_winglets (Raymer Eq. 6.29)
            place_gear: true
            extend_fuselage_for_gear: true  # PRESSUPOSTO lengthen pod for Raymer band
            gear: {tipback_deg: 15, ...}   # optional overrides for gear_layout
            yaw_control: split_aileron     # NO vertical surface; yaw by split ailerons (:mod:`.tailless`)
            sas: true                      # active yaw SAS (default true for a UAV)
            split_aileron: {eta_inner, eta_outer, cf_c, delta_max_deg, rate_max_deg_s}
            elevon: {eta_inner, eta_outer, cf_c, max_deg}

    ``yaw_control: split_aileron`` and ``size_winglets`` are mutually exclusive (there is no fin to size):
    the winglet step is skipped and reported ``unassessed``. The split-aileron cases and the bare/SAS modes run
    later, in :func:`.handling.apply` (they need the sized W0 and the AVL derivatives).
    """
    o = spec.get("options") or {}
    fw = o.get("flying_wing")
    if not fw or fw is False:
        return spec, None
    if not isinstance(fw, dict):
        raise ValueError("assembly.options.flying_wing must be a mapping or false/absent")
    out = copy.deepcopy(spec)
    report: dict[str, Any] = {"schema": "flying_wing", "level": "L0", "steps": []}
    yaw = str(fw.get("yaw_control") or "").lower()
    if yaw:
        st: dict[str, Any] = {"step": "yaw_control", "yaw_control": yaw}
        if yaw == "split_aileron":
            st["c_vt_drawn"] = measure_c_vt(Assembly.from_dict(out["assembly"]))
            st["status"] = "requested"
            st["note"] = ("sem superfície vertical: guinada por split ailerons (arrasto assimétrico, McCormick 1995 "
                          "Eq. 3.45) e SAS ativo; casos e modos avaliados em handling.apply")
            if st["c_vt_drawn"] > 1e-6:
                st["issues"] = [f"desenho ainda tem superfície vertical (c_VT {st['c_vt_drawn']:.3f})"]
        else:
            st["status"] = "unassessed"
            st["issues"] = [f"yaw_control '{yaw}' sem método no acdt (só split_aileron)"]
        report["steps"].append(st)
    if fw.get("size_winglets") and yaw == "split_aileron":
        report["steps"].append({"step": "size_winglets", "status": "unassessed",
                                "issues": ["size_winglets ignorado: yaw_control=split_aileron não tem deriva"]})
    elif fw.get("size_winglets"):
        if fw.get("c_vt") is None:
            report["steps"].append({
                "step": "size_winglets", "status": "unassessed",
                "issues": ["flying_wing.size_winglets set but c_vt missing — "
                           "refusing a silent invented volume (Raymer Eq. 6.29)"]})
        else:
            report["steps"].append({"step": "size_winglets",
                                    **size_winglets_to_c_vt(out, float(fw["c_vt"]))})
    if fw.get("place_gear"):
        report["steps"].append({"step": "place_gear",
                                **enable_tricycle_gear(out, fw.get("gear") if isinstance(fw.get("gear"), dict) else None)})
        if fw.get("extend_fuselage_for_gear"):
            if mission_flight and not out.get("flight"):
                out["flight"] = dict(mission_flight)
            elif mission_flight:
                out["flight"] = {**out["flight"], **{k: v for k, v in mission_flight.items()
                                                    if v is not None}}
            report["steps"].append({"step": "extend_fuselage_for_gear",
                                    **extend_fuselage_for_gear(out, fw)})
    if not report["steps"]:
        report["note"] = "flying_wing block present but no size_winglets/place_gear/yaw_control flag"
    out.setdefault("options", {})["_flying_wing_report"] = report
    return out, report
