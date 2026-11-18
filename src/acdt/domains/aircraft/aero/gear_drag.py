# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Landing-gear drag area in the polar (opt-in pieces, 16 nov 2026).

The gear enters the zero-lift drag as a miscellaneous (D/q) term of the component build-up,
CD0 = Σ(Cf FF Q S_wet)/S_ref + Σ(D/q)_misc/S_ref + CD_L&P (Raymer 2018 Eq. 12.24). The (D/q) itself is an input
(``assumptions.aero.extra_drag_areas_m2``, e.g. ``fixed_gear``) — no table value is invented here.

Two generic pieces:

* **Fixed gear scaled with the strut length** — :func:`.assembly.gear_devices.scale_fixed_gear_drag_area` already
  scales the lumped area with ΣL of the legs (two mains + one nose) against the reference lengths of the family the
  area came from (report-only until now, ``gear.scale_drag``). With ``gear.apply_scaled_drag: true`` (in
  ``assumptions.assembly.options.gear``, or ``aero.gear_drag: {scale_with_legs: true, ref_main_m, ref_nose_m}``
  without an assembly) the difference (scaled − given) is added to the polar as an extra
  ``(D/q)`` entry ``<key>_length_increment`` (the given key stays as it was, so the follow-up report scales the same
  number). Strut lengths come from ``weights.components`` / the gear block (the Raymer Eq. 15.50/15.51 inputs); when
  they are missing nothing is added and the row is *unassessed* (unknown ≠ a silent factor of 1).
* **Retractable gear** — ``aero.gear_drag.retractable: true`` takes the gear keys out of the cruise polar and keeps
  them as ``gear_down_drag_areas_m2``; they are added as ΔC_D0 = Σ(D/q)/S only in the gear-down configurations
  (take-off and landing ground roll / transition), on top of ``dCD0_takeoff`` (Raymer 2018 Sec. 17.8: the take-off
  C_D0 includes the drag of the extended gear and flaps). With a retractable gear ``dCD0_takeoff`` should then hold the
  flap increment only (PRESSUPOSTO declared in the report).

Fixed gear is always in the polar (cruise, climb, take-off, landing), as before.
"""
from __future__ import annotations

import copy
import math
from typing import Any

SOURCE = ("Raymer 2018 Eq. 12.24 (Σ(D/q)_misc/S_ref no C_D0); escala com ΣL das pernas contra as pernas de referência "
          "da família de onde veio a área (gear_devices.scale_fixed_gear_drag_area, comprimentos das Eqs. 15.50/15.51 "
          "de Raymer); trem retráctil só em baixo na descolagem/aterragem (Raymer 2018 Sec. 17.8)")
GEAR_KEYS_DEFAULT = ("fixed_gear", "landing_gear", "gear", "retractable_gear")
INCREMENT_SUFFIX = "_length_increment"
MARK = "_gear_drag"


def _gear_opts(A: dict[str, Any]) -> dict[str, Any]:
    """Gear block of the assembly: inline ``assembly.gear``, ``assembly.options.gear`` or the flying-wing shortcut
    ``assembly.options.flying_wing.gear`` (later ones win)."""
    asm_raw = A.get("assembly")
    asm: dict[str, Any] = asm_raw if isinstance(asm_raw, dict) else {}
    o = asm.get("options") or {}
    out = {}
    for blk in (asm.get("gear"), o.get("gear"), (o.get("flying_wing") or {}).get("gear")):
        if isinstance(blk, dict):
            out.update(blk)
    return out


def _length_opts(A: dict[str, Any], gopts: dict[str, Any]) -> dict[str, Any]:
    out = {}
    comps = ((A.get("weights") or {}).get("components") or {})
    for src in (comps, gopts):
        for k in ("main_gear_length_m", "nose_gear_length_m"):
            if src.get(k) is not None:
                out[k] = float(src[k])
    return out


def requested(A: dict[str, Any]) -> bool:
    aero = A.get("aero") or {}
    return bool(isinstance(aero.get(MARK), dict) or (aero.get("gear_drag") or {}).get("retractable")
                or (aero.get("gear_drag") or {}).get("scale_with_legs") or _gear_opts(A).get("apply_scaled_drag"))


def prepare(A: dict[str, Any]) -> dict[str, Any] | None:
    """Apply the opt-in gear-drag pieces to ``A`` (``spec.assumptions``) in place; returns the report, or None when
    nothing was requested. Idempotent: a second call returns the stored report."""
    aero = A.get("aero") or {}
    if isinstance(aero.get(MARK), dict):
        rep0: dict[str, Any] = aero[MARK]
        return rep0
    gd = aero.get("gear_drag") or {}
    gopts = _gear_opts(A)
    want_scale = bool(gopts.get("apply_scaled_drag") or gd.get("scale_with_legs"))
    retract = bool(gd.get("retractable"))
    if not (want_scale or retract):
        return None
    extra = dict(aero.get("extra_drag_areas_m2") or {})
    keys = [k for k in (gd.get("keys") or GEAR_KEYS_DEFAULT) if k in extra]
    rep: dict[str, Any] = {"schema": "gear_drag", "source": SOURCE, "gear_keys": keys,
                 "given_m2": {k: float(extra[k]) for k in keys}, "retractable": retract}
    if not keys:
        rep.update({"status": "unassessed",
                    "issue": "nenhuma área de trem em aero.extra_drag_areas_m2 (chaves "
                             + ", ".join(gd.get("keys") or GEAR_KEYS_DEFAULT) + ") — nada aplicado"})
        aero[MARK] = rep
        return rep
    if want_scale:
        from ..assembly.gear_devices import (DEFAULT_MAIN_GEAR_LENGTH_M,  # type: ignore[attr-defined]
                                             DEFAULT_NOSE_GEAR_LENGTH_M, scale_fixed_gear_drag_area)
        lo = _length_opts(A, gopts)
        layout = {}
        if "main_gear_length_m" in lo:
            layout["main_leg_length_m"] = lo["main_gear_length_m"]
        if "nose_gear_length_m" in lo:
            layout["nose_leg_length_m"] = lo["nose_gear_length_m"]
        if "main_gear_length_m" not in lo:
            layout = {}          # no strut length before the layout → unassessed here, never a factor of 1
        k0 = keys[0]
        sc = scale_fixed_gear_drag_area(
            float(extra[k0]), layout,
            ref_main_m=float(gd.get("ref_main_m", gopts.get("drag_ref_main_m", DEFAULT_MAIN_GEAR_LENGTH_M))),
            ref_nose_m=float(gd.get("ref_nose_m", gopts.get("drag_ref_nose_m", DEFAULT_NOSE_GEAR_LENGTH_M))))
        rep["scaled"] = sc
        if sc.get("status") == "assessed":
            inc = float(sc["area_scaled_m2"] - sc["area_given_m2"])
            extra[k0 + INCREMENT_SUFFIX] = inc
            keys.append(k0 + INCREMENT_SUFFIX)
            rep["increment_m2"] = inc
            rep["applied_key"] = k0
        else:
            rep["scale_issue"] = sc.get("issue")
    down = {}
    if retract:
        for k in keys:
            down[k] = float(extra.pop(k))
        rep["note_dCD0_takeoff"] = ("PRESSUPOSTO: com trem retráctil, dCD0_takeoff fica só com o incremento dos "
                                    "flaps; o trem em baixo soma-se aqui")
    total = float(sum(v for k, v in extra.items() if k in keys)) + float(sum(down.values()))
    rep.update({"status": "assessed" if (not want_scale or "increment_m2" in rep) else "unassessed",
                "polar_gear_m2": float(sum(v for k, v in extra.items() if k in keys)),
                "gear_down_m2": float(sum(down.values())), "gear_total_m2": total})
    aero["extra_drag_areas_m2"] = extra
    aero["gear_down_drag_areas_m2"] = down
    aero[MARK] = rep
    A["aero"] = aero
    return rep


def gear_down_dq(aero: dict[str, Any]) -> float:
    """Σ(D/q) [m²] of a retracted gear that is added only gear-down (0 for a fixed gear: already in the polar)."""
    return float(sum((aero.get("gear_down_drag_areas_m2") or {}).values()))


def dcd0_takeoff(aero: dict[str, Any], S: float | None) -> float:
    """ΔC_D0 of the take-off / landing ground configuration: ``dCD0_takeoff`` (flaps, + gear when the user lumped it)
    plus the retracted-gear area extended (Raymer 2018 Sec. 17.8)."""
    d = float(aero.get("dCD0_takeoff", 0.0) or 0.0)
    dq = gear_down_dq(aero)
    if dq > 0 and S and S > 0 and math.isfinite(S):
        d += dq / float(S)
    return d


def summary(rep: dict[str, Any] | None, S: float, CD0: float) -> dict[str, Any] | None:
    """Report with ΔC_D0 at the sized S (for the result / check row)."""
    if not rep:
        return None
    out = copy.deepcopy(rep)
    if S and S > 0:
        out["S_m2"] = float(S)
        out["dCD0_increment"] = float(rep.get("increment_m2", 0.0)) / S
        out["CD0_gear_polar"] = float(rep.get("polar_gear_m2", 0.0)) / S
        out["dCD0_gear_down"] = float(rep.get("gear_down_m2", 0.0)) / S
        out["CD0"] = float(CD0)
    return out


def row(rep: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if not rep:
        return None
    if rep.get("status") != "assessed":
        return ("aero:gear_drag", None,
                f"arrasto do trem unassessed: {rep.get('issue') or rep.get('scale_issue') or '?'} ({rep['source']})")
    parts = []
    if "increment_m2" in rep:
        sc = rep["scaled"]
        parts.append(f"{rep['applied_key']} {sc['area_given_m2']:.4f} m² × {sc['factor']:.3f} (ΣL {sc['L_sum_m']:.2f} m / "
                     f"ref {sc['L_ref_m']:.2f} m) = {sc['area_scaled_m2']:.4f} m², +{rep['increment_m2']:.4f} m² no polar")
    if rep.get("retractable"):
        parts.append(f"trem retráctil: {rep['gear_down_m2']:.4f} m² só em baixo (descolagem/aterragem)")
    if rep.get("dCD0_increment") is not None:
        parts.append(f"ΔC_D0 de cruzeiro {rep['dCD0_increment']:+.5f} (S {rep['S_m2']:.3f} m², C_D0 {rep['CD0']:.5f})")
    if rep.get("dCD0_gear_down"):
        parts.append(f"ΔC_D0 trem em baixo {rep['dCD0_gear_down']:+.5f}")
    return ("aero:gear_drag", True, "; ".join(parts) + f" ({rep['source']})")
