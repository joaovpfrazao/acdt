# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in bridge: common ``onboard`` recipe → native size / jet / VTOL burn hooks.

When a mission (or jet/VTOL spec) carries an explicit ``onboard`` block with loads, this module
maps the cited generator/battery hotel into the native consumption fields:

* prop thermal — ``auxiliary_fuel_flow_kg_s`` + ``auxiliary_shaft_W`` (+ pre/post durations)
* prop/VTOL electric — ``onboard_power_W`` / ``electric.systems_power_W`` (+ peak when known)
* jet — ``auxiliary.fuel_flow_kg_s`` + ``auxiliary.thrust_penalty_N`` (+ pre/post)

Methods: :func:`acdt.core.onboard.analyse_onboard` (MIL-E-7016F / Moir & Seabridge load identities;
BSFC/fuel_kg_kWh and efficiencies are **inputs**, never estimated). Missing extraction coefficients
with nonzero load → **unassessed** (raises; never free electricity / silent zero burn).

No ``onboard`` block → no-op (existing missions unchanged). Hybrid stays unassessed (no dispatch).
"""
from __future__ import annotations

from copy import deepcopy


def _onboard_block(d: dict) -> tuple[dict | None, dict]:
    """Return (onboard_schema, duration_dict). Accepts top-level or assumptions.onboard."""
    if not isinstance(d, dict):
        return None, {}
    s = d.get("onboard")
    if s is None and isinstance(d.get("assumptions"), dict):
        s = d["assumptions"].get("onboard")
    if s is None:
        return None, {}
    dur = d.get("duration") if isinstance(d.get("duration"), dict) else {}
    if not dur and isinstance(d.get("assumptions"), dict):
        dur = d["assumptions"].get("onboard_duration") or {}
    return s, dur if isinstance(dur, dict) else {}


def _model_from_propulsion(kind: str) -> str:
    k = (kind or "").lower()
    if k in ("electric", "electric_prop"):
        return "electric"
    if k in ("piston_prop", "turboprop"):
        return "prop"
    if k.startswith("jet") or k in ("turbofan", "turbojet"):
        return "jet"
    if "vtol" in k:
        return "vtol"
    if "hybrid" in k:
        return "hybrid"
    return "prop"


def apply_onboard_to_size_dict(d: dict) -> tuple[dict, dict]:
    """Mutate a deep copy of a prop/electric **mission** dict for :class:`MissionSpec` / ``acdt size``.

    Returns ``(new_dict, report)``. ``report["applied"]`` is False when no onboard block is present.
    """
    from acdt.core.onboard import analyse_onboard

    out = deepcopy(d)
    s, dur = _onboard_block(out)
    if s is None:
        return out, {"applied": False, "reason": "no onboard block"}
    req = out.get("requirements") or {}
    prop = (req.get("propulsion_type") or "piston_prop")
    if isinstance(prop, dict):
        prop = prop.get("value") or prop.get("target") or "piston_prop"
    model = _model_from_propulsion(str(prop))
    if model == "hybrid":
        raise ValueError(
            "onboard hotel on hybrid propulsion is unassessed in acdt size "
            "(no hybrid_dispatch model — unknown ≠ free electricity / silent zero burn); "
            "supply hotel_power_W via an explicit hybrid path or use onboard_size with a cited model"
        )
    a = analyse_onboard(s, model, duration_s=None)
    if a.get("missing_models"):
        raise ValueError(
            "onboard hotel load supplied but extraction/generator model incomplete: "
            + ", ".join(a["missing_models"])
            + " — unassessed (never free energy / silent zero burn); provide BSFC+η "
            "(thermal), fuel_kg_kWh_terminal+thrust penalty (jet), or use main_battery (electric)"
        )
    aa = out.setdefault("assumptions", {})
    pa = aa.setdefault("propulsion", {})
    # refuse overlap with legacy hooks already set nonzero
    legacy = ("systems_power_W", "onboard_power_W", "auxiliary_fuel_flow_kg_s", "auxiliary_shaft_W",
              "auxiliary_pre_s", "auxiliary_post_s")
    if any(float(pa.get(k, 0) or 0) for k in legacy):
        raise ValueError("onboard bridge: propulsion already has hotel/extraction hooks; "
                         "use either onboard or legacy fields, not both")
    pre = float(dur.get("precruise_s", 0) or 0)
    post = float(dur.get("postcruise_s", 0) or 0)
    if model == "prop":
        if a["fuel_flow_kg_s"] is None or a["shaft_extraction_W"] is None:
            raise ValueError("onboard thermal extraction unresolved — unassessed")
        pa["auxiliary_fuel_flow_kg_s"] = float(a["fuel_flow_kg_s"])
        pa["auxiliary_shaft_W"] = float(a["shaft_extraction_W"])
        pa["auxiliary_pre_s"] = pre
        pa["auxiliary_post_s"] = post
    elif model == "electric":
        pa["onboard_power_W"] = float(a["main_battery_average_W"])
        # peak not a native prop field; recorded in report only
    else:
        raise ValueError(f"onboard bridge for mission size supports prop/electric, not {model!r}; "
                         f"use acdt jet / acdt vtol / onboard_size")

    # incremental mass → fixed empty equipment + payload requirement bump
    wa = aa.setdefault("weights", {})
    wa["fixed_mass_kg"] = float(wa.get("fixed_mass_kg") or 0) + float(a["incremental_equipment_kg"])
    if a["incremental_payload_kg"]:
        pm = req.setdefault("payload_mass", {"target": 0, "unit": "kg"})
        if isinstance(pm, dict):
            key = "target" if "target" in pm else ("min" if "min" in pm else "target")
            pm[key] = float(pm.get(key) or 0) + float(a["incremental_payload_kg"])
            pm.setdefault("unit", "kg")
        else:
            req["payload_mass"] = {"target": float(pm) + float(a["incremental_payload_kg"]), "unit": "kg"}

    # keep audit trail; drop live onboard so MissionSpec stays clean (report carries the recipe)
    out.pop("onboard", None)
    if isinstance(out.get("assumptions"), dict):
        out["assumptions"].pop("onboard", None)
    out.setdefault("assumptions", {}).setdefault("onboard_bridge", {})
    # gerador(es) da extração de veio (prop térmico): perdas P_veio − P_terminal = P_veio·(1 − η) e coeficientes
    # efetivos para acoplar cargas extra (ventilador) — identidades do próprio modelo onboard (η e BSFC são entradas)
    gens = [r for r in a.get("sources") or [] if r.get("kind") not in ("main_battery", "battery")]
    gen_term = gen_loss = gen_shaft = gen_fuel = None
    if model == "prop" and gens and all(r.get("shaft_extraction_W") is not None for r in gens):
        gen_term = float(sum(r["terminal_average_W"] for r in gens))
        gen_shaft = float(sum(r["shaft_extraction_W"] for r in gens))
        gen_fuel = float(sum(r["fuel_flow_kg_s"] for r in gens))
        gen_loss = gen_shaft - gen_term
    report = {
        "applied": True,
        "generator_terminal_W": gen_term,
        "generator_shaft_W": gen_shaft,
        "generator_loss_W": gen_loss,
        "generator_eta_effective": (gen_term / gen_shaft) if gen_term and gen_shaft else None,
        "generator_fuel_per_shaft_kg_J": (gen_fuel / gen_shaft) if gen_fuel and gen_shaft else None,
        "status": "assessed",
        "model": model,
        "load_average_W": a["load_average_W"],
        "load_peak_W": a["load_peak_W"],
        "fuel_flow_kg_s": a.get("fuel_flow_kg_s"),
        "shaft_extraction_W": a.get("shaft_extraction_W"),
        "main_battery_average_W": a.get("main_battery_average_W"),
        "incremental_payload_kg": a["incremental_payload_kg"],
        "incremental_equipment_kg": a["incremental_equipment_kg"],
        "precruise_s": pre,
        "postcruise_s": post,
        "method": "acdt.core.onboard.analyse_onboard → native auxiliary/hotel hooks",
        "source": s.get("source"),
        "note": "opt-in; missions without onboard unchanged; coefficients are inputs (PRESSUPOSTO unless sourced)",
    }
    out["assumptions"]["onboard_bridge"] = report
    return out, report


def apply_onboard_to_jet_spec(spec: dict) -> tuple[dict, dict]:
    """Inject onboard hotel into jet ``auxiliary`` before :func:`size_jet` validation."""
    from acdt.core.onboard import analyse_onboard

    out = deepcopy(spec)
    s, dur = _onboard_block(out)
    if s is None:
        return out, {"applied": False, "reason": "no onboard block"}
    a = analyse_onboard(s, "jet", duration_s=None)
    if a.get("missing_models"):
        raise ValueError(
            "jet onboard hotel missing fuel_kg_kWh_terminal and/or thrust_penalty_N_per_W_terminal: "
            + ", ".join(a["missing_models"])
            + " — unassessed (never free energy)"
        )
    if out.get("auxiliary") and any(float((out["auxiliary"] or {}).get(k, 0) or 0)
                                    for k in ("fuel_flow_kg_s", "thrust_penalty_N", "pre_duration_s", "post_duration_s", "empty_mass_kg")):
        raise ValueError("onboard bridge: jet auxiliary already set; do not combine with onboard")
    pre = float(dur.get("precruise_s", 0) or 0)
    post = float(dur.get("postcruise_s", 0) or 0)
    out["auxiliary"] = {
        "fuel_flow_kg_s": float(a["fuel_flow_kg_s"] or 0),
        "thrust_penalty_N": float(a["thrust_penalty_N"] or 0),
        "pre_duration_s": pre,
        "post_duration_s": post,
        # equipment incremental mass rides as empty_mass_kg (same as onboard_size jet path)
        "empty_mass_kg": float(a["incremental_equipment_kg"]),
    }
    out["payload_kg"] = float(out.get("payload_kg") or 0) + float(a["incremental_payload_kg"])
    out.pop("onboard", None)
    out.pop("duration", None)
    report = {
        "applied": True, "status": "assessed", "model": "jet",
        "fuel_flow_kg_s": out["auxiliary"]["fuel_flow_kg_s"],
        "thrust_penalty_N": out["auxiliary"]["thrust_penalty_N"],
        "load_average_W": a["load_average_W"],
        "incremental_payload_kg": a["incremental_payload_kg"],
        "incremental_equipment_kg": a["incremental_equipment_kg"],
        "method": "analyse_onboard → jet auxiliary",
        "note": "equipment incremental → auxiliary.empty_mass_kg; payload incremental → payload_kg",
    }
    out["onboard_bridge"] = report
    return out, report


def apply_onboard_to_vtol_spec(spec: dict) -> tuple[dict, dict]:
    """Inject onboard hotel into VTOL ``electric.systems_power_W`` / peak."""
    from acdt.core.onboard import analyse_onboard

    out = deepcopy(spec)
    s, dur = _onboard_block(out)
    if s is None:
        return out, {"applied": False, "reason": "no onboard block"}
    a = analyse_onboard(s, "vtol", duration_s=None)
    e = out.setdefault("electric", {})
    if float(e.get("systems_power_W", 0) or 0) or "systems_peak_power_W" in e:
        raise ValueError("onboard bridge: VTOL electric.systems_power_W already set; do not combine with onboard")
    e["systems_power_W"] = float(a["main_battery_average_W"])
    e["systems_peak_power_W"] = float(a["main_battery_peak_W"])
    out.pop("onboard", None)
    out.pop("duration", None)
    report = {
        "applied": True, "status": "assessed", "model": "vtol",
        "systems_power_W": e["systems_power_W"],
        "systems_peak_power_W": e["systems_peak_power_W"],
        "load_average_W": a["load_average_W"],
        "method": "analyse_onboard → VTOL electric.systems_power_W",
    }
    out["onboard_bridge"] = report
    return out, report
