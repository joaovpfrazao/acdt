"""Manufacturing plan and bottom-up part cost (Phase 7).

Per part: enumerate the allowed (material, process) options, evaluate each with :func:`processes.evaluate`,
and cost it at production quantity N:

    unit part cost = material x B2F x price + labour_h x rate x LF(N) + fasteners + machine_h x machine rate
                     + tooling / N

LF(N) is the average learning factor over N units (Crawford unit curve by default, slope 0.85 — NASA JSC
aerospace default) applied to the process hours taken as the **first-unit** time (``hours_basis='first_unit'``,
ASSUMPTION flagged in the output); set ``hours_basis='standard'`` to use the FOPV hours as mature standard
times (LF = 1). The option with the lowest unit cost among the feasible, fully-specified ones is selected.

Materials enter with a dated price ``{usd_per_kg, year, provenance}`` and are escalated to the study year with
CPI-U (:func:`refdata.cpi_factor`). Tooling: a quote per part design (``tooling_cost`` in the process inputs)
or, if none, an allocation of a top-down tooling pool (e.g. the Eastlake/DAPCA tooling cost) by part area —
flagged, since a pool does not discriminate between processes.
"""
from __future__ import annotations

from . import refdata as R
from .costing import learning_factor
from .selection import scale_part
from .processes import PROCESSES, Part, evaluate, material_class


def price_material(mat: dict, year: int, cpi_table: dict | None = None) -> dict:
    """Escalate ``mat['price']`` = {usd_per_kg, year, provenance} to ``year``; validate provenance."""
    from acdt.ai.external import check_provenance
    m = dict(mat)
    pr = m.get("price")
    if pr is None:
        m.setdefault("usd_per_kg", None)
        return m
    p, iss = check_provenance(pr.get("provenance"))
    f = R.cpi_factor(year, int(pr.get("year", year)), cpi_table) if int(pr.get("year", year)) != year else 1.0
    m["usd_per_kg"] = float(pr["usd_per_kg"]) * f
    m["price_provenance"] = p
    m["price_issues"] = iss
    m["price_escalation"] = f
    return m


def default_options(part: Part, mclass: str) -> list[str]:
    return [k for k, v in PROCESSES.items() if mclass in [material_class({"kind": x}) for x in v["materials"]]]


def plan(parts: list[Part], materials: dict, N: int, *, choices: dict | None = None, process_inputs: dict | None = None,
         year: int = 2025, learning: dict | None = None, hours_basis: str = "first_unit",
         tooling_pool: float | None = None, cpi_table: dict | None = None, scaling: str | None = "auto",
         labour_calibration: float = 1.0, material_calibration: float = 1.0) -> dict:
    """Manufacturing plan for an aircraft at production quantity N.

    ``materials``: {key: material dict with rho, kind, price{usd_per_kg, year, provenance}}.
    ``choices``: {part name | part kind | group | '*': {"materials": [keys], "processes": [names]}} (most specific
    wins); default: every material in ``materials`` x every process able to process it.
    ``process_inputs``: {process | 'part name:process' | '*': inputs for :func:`processes.evaluate`}; a
    ``prices: {material: {usd_per_kg, year, provenance}}`` entry overrides the material price for that process
    (stock form: plate for machining vs sheet for forming).
    ``scaling``: when a part is offered in a material other than the one it was sized in, its mass is scaled
    with the Ashby index of its governing load (:func:`selection.scale_part`; ``'auto'`` = by part kind)."""
    choices = choices or {}
    pin = process_inputs or {}
    lc = {"slope": R.LEARNING_DEFAULT["slope"], "theory": "crawford", **(learning or {})}
    LF = learning_factor(N, lc["slope"], lc["theory"]) if hours_basis == "first_unit" else 1.0
    mats = {k: price_material({"key": k, **v}, year, cpi_table) for k, v in materials.items()}
    area_tot = sum(p.area_m2 * p.count for p in parts) or 1.0
    rows, chosen, notes = [], [], []
    if hours_basis == "first_unit":
        notes.append(f"labour: FOPV/process hours taken as first-unit time, averaged over N={N} with a "
                     f"{lc['slope']:.0%} {lc['theory']} curve -> LF={LF:.3f} (ASSUMPTION; hours_basis='standard' "
                     f"for LF=1)")
    for part in parts:
        ch = choices.get(part.name) or choices.get(part.kind) or choices.get(part.group) or choices.get("*") or {}
        mkeys = ch.get("materials") or ([part.material] if part.material else list(mats))
        opts = []
        for mk in mkeys:
            if mk not in mats:
                raise KeyError(f"material {mk!r} not provided")
            m = mats[mk]
            if mk != part.material and part.material in mats and scaling:
                part_m = scale_part(part, mats[part.material], m, scaling)
            else:
                part_m = part
            procs = ch.get("processes") or default_options(part, material_class(m))
            if m.get("processes"):  # material tied to its process route (e.g. a VARI laminate ↔ vacuum_infusion)
                procs = [p for p in procs if p in m["processes"]]
            for pr in procs:
                inp = {"year": year, **pin.get("*", {}), **pin.get(pr, {}), **pin.get(f"{part.name}:{pr}", {})}
                sp = (inp.get("prices") or {}).get(mk)  # stock-form price for this process (e.g. plate vs sheet)
                if sp is not None:
                    inp["usd_per_kg"] = price_material({"price": sp}, year, cpi_table)["usd_per_kg"]
                ev = evaluate(part_m, pr, m, inp)
                if sp is not None:
                    ev["price_source"] = sp.get("provenance")
                ev["mass_kg"] = part_m.mass_kg
                if ev["tooling_cost"] is None and ev["needs_tooling"]:
                    if tooling_pool is not None:
                        ev["tooling_cost"] = tooling_pool * part.area_m2 / area_tot
                        ev["warnings"].append("tooling allocated from the top-down tooling pool by area")
                    else:
                        ev["missing"].append("tooling_cost (quote) or a tooling_pool")
                tool = ev["tooling_cost"] or 0.0
                kl = labour_calibration * float(inp.get("labour_calibration", 1.0))  # global x per process
                if ev["labour_hours"] is not None and kl != 1.0:
                    ev["labour_hours"] *= kl
                    ev["warnings"].append(f"labour hours x {kl:g} (labour_calibration)")
                if ev["material_cost"] is not None and material_calibration != 1.0:
                    ev["material_cost"] *= material_calibration
                    ev["warnings"].append(f"material cost x {material_calibration:g} (cost_L1 calibration)")
                lab = None if ev["labour_hours"] is None else ev["labour_hours"] * ev["labour_rate_usd_h"] * LF
                parts_cost = None
                if lab is not None and ev["material_cost"] is not None:
                    parts_cost = (ev["material_cost"] + lab + ev["fastener_cost"] + ev["machine_cost"] + tool / N)
                ev.update({"labour_cost": lab, "tooling_per_unit": tool / N, "unit_cost_per_part": parts_cost,
                           "unit_cost": None if parts_cost is None else parts_cost * part.count,
                           "count": part.count, "learning_factor": LF})
                opts.append(ev)
        ok = [o for o in opts if o["feasible"] and o["unit_cost"] is not None and not o["missing"]]
        partial = [o for o in opts if o["feasible"] and o["unit_cost"] is not None]
        best = min(ok or partial, key=lambda o: o["unit_cost"]) if (ok or partial) else None
        if best is not None and not ok:
            best = {**best, "warnings": best["warnings"] + ["selected with missing inputs: " + "; ".join(best["missing"])]}
        rows.append({"part": part.to_dict(), "options": opts, "selected": best})
        if best is not None:
            chosen.append(best)
    tot = {k: sum((c.get(k) or 0.0) * (c["count"] if k != "unit_cost" else 1) for c in chosen)
           for k in ("material_cost", "labour_cost", "fastener_cost", "machine_cost", "tooling_per_unit", "unit_cost")}
    tot["labour_hours"] = sum((c["labour_hours"] or 0) * c["count"] for c in chosen) * LF
    tot["bought_mass_kg"] = sum(c["bought_mass_kg"] * c["count"] for c in chosen)
    tot["flown_mass_kg"] = sum(c["mass_kg"] * c["count"] for c in chosen)
    unresolved = [r["part"]["name"] for r in rows if r["selected"] is None]
    return {"N": N, "year": year, "learning_factor": LF, "parts": rows, "totals": tot, "unresolved_parts": unresolved,
            "selection": {r["part"]["name"]: (r["selected"]["process"], r["selected"]["material"])
                          for r in rows if r["selected"]}, "notes": notes,
            "materials": {k: {kk: v for kk, v in m.items() if kk in ("usd_per_kg", "price_provenance", "price_issues",
                                                                    "price_escalation", "kind", "rho")}
                          for k, m in mats.items()}}
