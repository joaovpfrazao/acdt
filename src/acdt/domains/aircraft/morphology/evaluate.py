"""Multidisciplinary low-fidelity evaluation of morphological architectures (N1).

Reuses ``acdt size`` (L0 by default) and the point-mass mission simulator as the common judge
(DESIGN_WORKFLOW §4). Architecture choices map to a small set of assumption patches when known;
unknown choices stay in the record and do not invent geometry.

P4 (10 nov 2026): energy / hybrid / datalink / SATCOM axes are assessed when a cited model and
source are supplied (hybrid_dispatch, link power/mass hotel). Missing model or source →
``unassessed_axes`` (never a silent feasible pass or zero mass/power/energy).

P4 ops-cost (10 nov 2026): optional ``operating_cost`` / ``operating`` block (Raymer 2018 Ch. 18
DOC elements; ``unit_price`` may be Eastlake/DAPCA CER or sized unit_cost). Attaches
``cost_per_fh`` only when status=ok; incomplete terms → unassessed (never silent zero).
Examples without the block stay unchanged. Prune stays set-based / Pareto.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from acdt.domains.aircraft.mission import MissionSpec

# Energy ids that imply a hybrid architecture needing hybrid_dispatch
_HYBRID_ENERGY = frozenset({"hybrid", "hybrid_series", "hybrid_parallel"})
_FUEL_ENERGY = frozenset({"fuel", "fuel_avgas", "fuel_jetA"})
_BATT_ENERGY = frozenset({"battery", "battery_LiIon"})
_COMMS_AXIS = "avionics_link"


def _set_propulsion_type(spec: MissionSpec, value: str) -> bool:
    r = spec.requirements.get("propulsion_type")
    if r is None:
        from acdt.core.requirements import Requirement
        spec.requirements.reqs.append(Requirement(key="propulsion_type", sense="target", value=value, raw=value))
        return True
    r.value = value
    r.raw = value
    return True


def apply_choice_patches(spec: MissionSpec, choices: dict[str, str]) -> list[str]:
    """Mutate a deep-copied MissionSpec from architecture choices. Returns notes (PRESSUPOSTO / skips)."""
    notes: list[str] = []
    aa = spec.assumptions
    pk = choices.get("propulsion_kind")
    if pk == "electric":
        _set_propulsion_type(spec, "electric")
        notes.append("propulsion_kind=electric → requirements.propulsion_type=electric")
    elif pk == "piston":
        _set_propulsion_type(spec, "piston_prop")
        notes.append("propulsion_kind=piston → requirements.propulsion_type=piston_prop")
    elif pk == "hybrid":
        notes.append("propulsion_kind=hybrid — despacho só se hybrid block for fornecido (P4)")

    en = choices.get("energy")
    if en in _BATT_ENERGY and pk == "electric":
        notes.append(f"energy={en} com electric (consistente)")
    if en in _FUEL_ENERGY and pk == "piston":
        notes.append(f"energy={en} com piston (consistente)")
    if en in _HYBRID_ENERGY:
        notes.append(f"energy={en} — requer hybrid_dispatch + source (Pornet & Isikveren 2015)")

    lg = choices.get("landing_gear")
    lr = choices.get("launch_recovery")
    wcomp = aa.setdefault("weights", {}).setdefault("components", {})
    if lg == "none" or lr in ("catapult", "net", "parachute"):
        wcomp["landing_gear"] = "none"
        notes.append(f"landing_gear/launch → weights.components.landing_gear=none (lg={lg}, lr={lr})")
    elif lg in ("tricycle", "taildragger", "skids"):
        wcomp["landing_gear"] = "none" if lg == "skids" else "tricycle"
        if lg == "skids":
            notes.append("PRESSUPOSTO: skids mapeados para landing_gear=none no size atual")
        else:
            notes.append(f"landing_gear={lg} → components.landing_gear={wcomp['landing_gear']}")

    yc = choices.get("yaw_control")
    if yc == "split_aileron":
        asm_a = aa.get("assembly")
        if isinstance(asm_a, dict):
            fwb = asm_a.setdefault("options", {}).setdefault("flying_wing", {})
            fwb["yaw_control"] = "split_aileron"
            fwb.pop("size_winglets", None)
            notes.append("yaw_control=split_aileron → assembly.options.flying_wing.yaw_control (sem deriva; SAS "
                         "por omissão no UAV); geometria split_aileron/elevon tem de vir da base — senão unassessed")
        else:
            notes.append("yaw_control=split_aileron registado; sem assumptions.assembly (asa voadora desenhada) "
                         "os casos de guinada ficam unassessed")
    elif yc is not None:
        notes.append(f"PRESSUPOSTO: 'yaw_control={yc}' registado; sem mapa no size")

    for dim in ("wing", "tail", "fuselage", "propulsion_layout", "payload"):
        if dim in choices:
            notes.append(
                f"PRESSUPOSTO: '{dim}={choices[dim]}' registado; sem mapa geométrico no size "
                f"(HANDOFF P1 tipos genéricos) — a métrica de missão usa a polar do size da base")
    return notes


def _mission_metrics(sim: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    tot = sim.get("totals") or {}
    sens = sim.get("sensor") or {}
    for k_src, k_dst in (
        ("range_km", "range_km"),
        ("time_min", "endurance_min"),
        ("fuel_kg", "fuel_or_energy_kg"),
    ):
        v = tot.get(k_src, sim.get(k_src))
        if isinstance(v, (int, float)):
            out[k_dst] = float(v)
    for k_src, k_dst in (
        ("time_on_station_min", "time_on_station_min"),
        ("area_swept_km2", "area_swept_km2"),
    ):
        v = sens.get(k_src, sim.get(k_src))
        if isinstance(v, (int, float)):
            out[k_dst] = float(v)
    return out


def _has_source(meta: dict | None) -> bool:
    if not meta:
        return False
    s = meta.get("source")
    return isinstance(s, str) and bool(s.strip())


def assess_energy_and_comms(
    choices: dict[str, str],
    option_meta: dict[str, dict] | None = None,
    *,
    hybrid_templates: dict[str, dict] | None = None,
    link_catalog: dict[str, dict] | None = None,
    mission_context: dict | None = None,
) -> dict[str, Any]:
    """Assess energy/hybrid and communications axes when models+sources exist.

    Returns ``unassessed_axes``, notes, metrics extras, and optional hybrid/comms reports.
    Never invents zero mass/power/energy when data are missing.
    """
    option_meta = option_meta or {}
    hybrid_templates = hybrid_templates or {}
    link_catalog = link_catalog or {}
    mission_context = mission_context or {}
    notes: list[str] = []
    unassessed: list[str] = []
    metrics: dict[str, float] = {}
    reports: dict[str, Any] = {}

    # ---- energy / hybrid ----
    en = choices.get("energy")
    pk = choices.get("propulsion_kind")
    needs_hybrid = (en in _HYBRID_ENERGY) or (pk == "hybrid")
    meta_en = option_meta.get("energy") or {}
    if needs_hybrid:
        custom_unassessed = (
            en and en not in _HYBRID_ENERGY and en not in hybrid_templates
            and not _has_source(meta_en) and not isinstance(meta_en.get("hybrid"), dict)
        )
        if custom_unassessed:
            unassessed.append("energy")
            notes.append(
                f"energy={en!r} unassessed: opção custom sem source/template "
                f"(não herda pass de propulsion_kind=hybrid)"
            )
        else:
            tmpl = None
            for key in (en, pk, meta_en.get("hybrid_template"), "default"):
                if key and key in hybrid_templates:
                    tmpl = copy.deepcopy(hybrid_templates[key])
                    break
            if tmpl is None and isinstance(meta_en.get("hybrid"), dict):
                tmpl = copy.deepcopy(meta_en["hybrid"])
            if tmpl is None:
                unassessed.append("energy")
                notes.append(
                    f"energy/hybrid unassessed: choice energy={en!r} propulsion_kind={pk!r} "
                    f"sem bloco hybrid_dispatch + source (nunca energia/massa zero silenciosa)"
                )
            elif not (tmpl.get("source") or _has_source(meta_en)):
                unassessed.append("energy")
                notes.append("energy/hybrid unassessed: hybrid block sem 'source' (unknown≠pass)")
            else:
                if en == "hybrid_series":
                    tmpl.setdefault("architecture", "series")
                elif en == "hybrid_parallel":
                    tmpl.setdefault("architecture", "parallel")
                try:
                    from acdt.domains.aircraft import hybrid_dispatch as HD
                    ctx = {
                        "distance_km": float(mission_context.get("distance_km", 50.0)),
                        "speed_m_s": float(mission_context.get("speed_m_s", 30.0)),
                        "station_h": float(mission_context.get("station_h", 2.0)),
                        "reserve_h": float(mission_context.get("reserve_h", 0.0)),
                    }
                    hy = HD.evaluate(tmpl, ctx["distance_km"], ctx["speed_m_s"],
                                     ctx["station_h"], ctx["reserve_h"])
                    reports["hybrid"] = {"status": "assessed", "result": {
                        "architecture": hy.get("architecture"), "feasible": hy.get("feasible"),
                        "fuel_kg": hy.get("fuel_kg"), "flight_h": hy.get("flight_h"),
                        "soc_final": hy.get("soc_final"), "checks": hy.get("checks"),
                    }, "context": ctx}
                    if isinstance(hy.get("fuel_kg"), (int, float)):
                        metrics["hybrid_fuel_kg"] = float(hy["fuel_kg"])
                    if isinstance(hy.get("battery_discharged_Wh"), (int, float)):
                        metrics["hybrid_battery_Wh"] = float(hy["battery_discharged_Wh"])
                    if isinstance(hy.get("flight_h"), (int, float)):
                        metrics["hybrid_flight_h"] = float(hy["flight_h"])
                    notes.append(
                        f"hybrid_dispatch assessed ({tmpl.get('architecture')}, "
                        f"fuel={hy.get('fuel_kg')} kg, feasible={hy.get('feasible')}) — "
                        f"{str(tmpl.get('source', ''))[:60]}"
                    )
                except Exception as ex:  # noqa: BLE001
                    unassessed.append("energy")
                    notes.append(f"energy/hybrid unassessed: hybrid_dispatch failed — {ex}")
                    reports["hybrid"] = {"status": "unassessed", "error": str(ex)}
    elif en in _FUEL_ENERGY or en in _BATT_ENERGY or en is None:
        # pure fuel/battery: size path covers energy if propulsion matches; no extra model required
        if en is not None:
            notes.append(f"energy={en}: covered by native size propulsion path (no hybrid_dispatch)")
    elif en is not None:
        # custom energy id without template
        meta_en = option_meta.get("energy") or {}
        if not _has_source(meta_en) and en not in hybrid_templates:
            unassessed.append("energy")
            notes.append(
                f"energy={en!r} unassessed: opção custom sem source/modelo "
                f"(acrescentar dict com source+retrieved ou hybrid_templates)"
            )

    # ---- communications / datalink / SATCOM ----
    link = choices.get(_COMMS_AXIS)
    if link is not None:
        meta_l = dict(option_meta.get(_COMMS_AXIS) or {})
        # catalog may override/supplement
        if link in link_catalog:
            for k, v in link_catalog[link].items():
                meta_l.setdefault(k, v)
        power = meta_l.get("power_W")
        mass = meta_l.get("mass_kg")
        has_src = _has_source(meta_l)
        if power is None or not has_src:
            unassessed.append(_COMMS_AXIS)
            notes.append(
                f"avionics_link={link!r} unassessed: falta power_W e/ou source "
                f"(datalink/SATCOM nunca entra como 0 W silencioso)"
            )
            reports["comms"] = {"status": "unassessed", "link": link, "meta": meta_l}
        else:
            metrics["comms_power_W"] = float(power)
            if isinstance(mass, (int, float)):
                metrics["comms_mass_kg"] = float(mass)
            reports["comms"] = {
                "status": "assessed",
                "link": link,
                "power_W": float(power),
                "mass_kg": float(mass) if isinstance(mass, (int, float)) else None,
                "source": meta_l.get("source"),
                "retrieved": meta_l.get("retrieved"),
            }
            notes.append(
                f"comms assessed: {link} hotel {power} W"
                + (f", mass {mass} kg" if isinstance(mass, (int, float)) else "")
                + f" — {meta_l.get('source')}"
            )

    return {
        "unassessed_axes": unassessed,
        "notes": notes,
        "metrics": metrics,
        "reports": reports,
        "systems_assessed": len(unassessed) == 0 or (
            # if neither energy nor comms axes present, vacuously assessed for P4
            "energy" not in choices and _COMMS_AXIS not in choices
        ),
    }



def attach_operating_cost(row: dict, operating: dict | None, *,
                          sized_unit_cost: float | None = None) -> None:
    """Opt-in DOC attach for morph evaluate (mutates ``row``).

    ``operating`` keys = :func:`~acdt.domains.aircraft.manufacturing.costing.operational_cost_from_dict`
    inputs. Special:
      * ``unit_price_from: "size"`` — use sized Eastlake/unit_cost when available; if missing →
        unassessed (do not invent).
      * per-architecture overrides under ``by_architecture`` are merged by the caller.
    """
    if not operating:
        return
    from acdt.domains.aircraft.manufacturing.costing import operational_cost_from_dict

    d = dict(operating)
    d.pop("by_architecture", None)
    unit_from = d.get("unit_price_from")
    override = None
    notes = row.setdefault("notes", [])
    if unit_from == "size":
        d.pop("unit_price_from", None)
        if sized_unit_cost is None:
            row["operating_cost"] = {
                "status": "unassessed",
                "per_flight_hour": None,
                "unassessed_terms": ["unit_price (size unit_cost absent)"],
                "missing_inputs": ["unit_price (size unit_cost absent)"],
                "method": "DOC (Raymer 2018 Ch. 18); unit_price_from=size but size had no unit_cost",
                "note": "unassessed≠zero: no sized acquisition cost to feed DOC",
            }
            notes.append("operating_cost unassessed — size sem unit_cost (unknown≠zero)")
            return
        override = float(sized_unit_cost)
        notes.append(f"operating_cost unit_price ← size unit_cost {override:.4g}")
    try:
        out = operational_cost_from_dict(d, unit_price_override=override)
    except (TypeError, ValueError) as exc:
        row["operating_cost"] = {
            "status": "unassessed",
            "per_flight_hour": None,
            "unassessed_terms": [str(exc)],
            "missing_inputs": [str(exc)],
            "method": "DOC (Raymer 2018 Ch. 18); input error",
            "note": "unassessed≠zero",
        }
        notes.append(f"operating_cost unassessed — {exc}")
        return
    row["operating_cost"] = out
    if out.get("status") == "ok" and out.get("per_flight_hour") is not None:
        row.setdefault("metrics", {})["cost_per_fh"] = float(out["per_flight_hour"])
        notes.append(f"operating_cost ok → metrics.cost_per_fh = {out['per_flight_hour']:.4g}")
    else:
        terms = out.get("unassessed_terms") or out.get("missing_inputs") or []
        notes.append(
            f"operating_cost {out.get('status')} — termos {terms}; "
            f"não anexar cost_per_fh (unassessed≠zero / não subavaliar)"
        )


def evaluate_one(arch: dict, base_spec: MissionSpec, mission_yaml: Path | dict | None = None,
                 level: str = "L0", run_mission: bool = True,
                 hybrid_templates: dict | None = None,
                 link_catalog: dict | None = None,
                 mission_context: dict | None = None,
                 operating_cost: dict | None = None) -> dict[str, Any]:
    """Size one architecture (patched base) and optionally fly the point-mass judge."""
    from acdt.domains.aircraft import sizing
    from acdt.domains.aircraft.flightsim.pointmass import simulate_pointmass_mission

    spec = copy.deepcopy(base_spec)
    if level.upper() == "L0":
        spec.assumptions.setdefault("aero", {})["fidelity"] = "handbook"
    notes = apply_choice_patches(spec, arch["choices"])
    sys_ass = assess_energy_and_comms(
        arch["choices"], arch.get("option_meta"),
        hybrid_templates=hybrid_templates, link_catalog=link_catalog,
        mission_context=mission_context,
    )
    notes.extend(sys_ass["notes"])

    # Apply assessed comms hotel into propulsion assumptions when electric/native hooks exist
    if (sys_ass["reports"].get("comms") or {}).get("status") == "assessed":
        pw = sys_ass["metrics"].get("comms_power_W")
        if pw is not None:
            prop = spec.assumptions.setdefault("propulsion", {})
            # additive hotel — do not invent if hook already set without knowing; add on top
            if spec.propulsion_kind == "electric" or prop.get("onboard_power_W") is not None \
                    or "battery" in str(arch["choices"].get("energy", "")):
                prop["onboard_power_W"] = float(prop.get("onboard_power_W") or 0.0) + float(pw)
                notes.append(f"comms hotel → propulsion.onboard_power_W += {pw} W")
            else:
                # piston: record as systems power note; auxiliary path would need BSFC
                prop["systems_power_W"] = float(prop.get("systems_power_W") or 0.0) + float(pw)
                notes.append(
                    f"comms hotel → propulsion.systems_power_W += {pw} W "
                    f"(extracção/BSFC: se em falta o size pode ficar unassessed noutro sítio)"
                )

    row: dict[str, Any] = {
        "id": arch["id"], "choices": arch["choices"], "notes": notes,
        "evaluable": True, "metrics": {}, "checks_failed": [],
        "unassessed_axes": list(sys_ass["unassessed_axes"]),
        "systems_reports": sys_ass["reports"],
        "option_meta": arch.get("option_meta"),
    }
    row["metrics"].update(sys_ass["metrics"])

    try:
        res = sizing.run(spec, strict=False)
    except Exception as exc:  # noqa: BLE001
        row["evaluable"] = False
        row["error"] = f"size: {exc}"
        # still keep unassessed_axes — systems may be unassessed independently
        row["systems_assessed"] = len(row["unassessed_axes"]) == 0
        op = None
        if operating_cost:
            op = dict(operating_cost)
            by = (operating_cost.get("by_architecture") or {}).get(arch["id"])
            if by:
                op = {**op, **by}
                op.pop("by_architecture", None)
        attach_operating_cost(row, op, sized_unit_cost=None)
        return row
    row["converged"] = bool(res.converged)
    # Feasible size does NOT imply systems axes are assessed
    row["feasible"] = bool(res.feasible) and len(row["unassessed_axes"]) == 0
    if res.feasible and row["unassessed_axes"]:
        notes.append(
            f"size feasible mas eixos unassessed {row['unassessed_axes']} — "
            f"não passa como solução de sistemas (unknown≠pass)"
        )
        row["notes"] = notes
    row["systems_assessed"] = len(row["unassessed_axes"]) == 0
    sz = res.sizing
    row["metrics"].update({
        "W0_kg": float(sz.W0) if sz else float("nan"),
        "We_kg": float(sz.We) if sz else float("nan"),
        "LD_max": float(res.polar.LD_max) if res.polar else float("nan"),
        "S_m2": float(res.S) if res.config else float("nan"),
    })
    sized_uc = None
    if res.cost is not None and getattr(res.cost, "unit_cost", None) is not None:
        sized_uc = float(res.cost.unit_cost)
        row["metrics"]["unit_cost"] = sized_uc
    op = None
    if operating_cost:
        op = dict(operating_cost)
        by = (operating_cost.get("by_architecture") or {}).get(arch["id"])
        if by:
            op = {**op, **by}
            op.pop("by_architecture", None)
    attach_operating_cost(row, op, sized_unit_cost=sized_uc)
    row["checks_failed"] = [c.key for c in (res.checks or []) if c.ok is False][:20]
    if not run_mission or mission_yaml is None:
        row["mission"] = None
        row["notes"].append("missão ponto-massa não pedida ou sem YAML — juiz de missão ausente")
        return row
    try:
        sim = simulate_pointmass_mission(mission_yaml, res=res)
        row["mission"] = {"aborted": bool(sim.get("aborted")), "name": sim.get("name")}
        row["metrics"].update(_mission_metrics(sim))
        if sim.get("aborted"):
            row["notes"].append("missão abortada — ver falhas/limites no simulador")
    except Exception as exc:  # noqa: BLE001
        row["notes"].append(f"pointmass: {exc}")
        row["mission"] = {"error": str(exc)}
    return row


def evaluate_architectures(architectures: list[dict], mission_path: str | Path,
                           sim_path: str | Path | None = None, level: str = "L0",
                           run_mission: bool = True, limit: int | None = None,
                           hybrid_templates: dict | None = None,
                           link_catalog: dict | None = None,
                           mission_context: dict | None = None,
                           operating_cost: dict | None = None) -> dict:
    """Evaluate each kept architecture against a base mission YAML (+ optional point-mass mission).

    ``hybrid_templates``: ``{option_id: hybrid_block}`` for energy/hybrid choices.
    ``link_catalog``: ``{link_id: {power_W, mass_kg?, source, retrieved?}}`` for avionics_link.
    ``operating_cost``: optional DOC inputs (``operational_cost_from_dict``); attaches
    ``metrics.cost_per_fh`` when status=ok (Raymer 2018 Ch. 18; Eastlake/DAPCA for unit_price).
    """
    path = Path(mission_path)
    base = MissionSpec.from_yaml(path)
    sim = Path(sim_path) if sim_path else None
    rows = []
    arches = architectures[:limit] if limit is not None else architectures
    for a in arches:
        rows.append(evaluate_one(
            a, base, mission_yaml=sim if (run_mission and sim) else None,
            level=level, run_mission=run_mission and sim is not None,
            hybrid_templates=hybrid_templates, link_catalog=link_catalog,
            mission_context=mission_context,
            operating_cost=operating_cost,
        ))
    n_un = sum(1 for r in rows if r.get("unassessed_axes"))
    return {
        "rows": rows, "n": len(rows), "level": level,
        "n_systems_unassessed": n_un,
        "base_mission": str(path), "sim_mission": str(sim) if sim else None,
        "reference": (
            "size L0/L1 + point-mass judge (Anderson 1999 Cap. 5, Raymer 2018 Cap. 17); "
            "hybrid_dispatch (Pornet & Isikveren 2015; Guzzella & Sciarretta 2013); "
            "DESIGN_WORKFLOW §4; P4 energy/comms unassessed≠pass; DOC Raymer 2018 Ch. 18 / Eastlake CER unit_price opt-in"
        ),
    }
