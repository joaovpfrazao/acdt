"""L2 cost: detailed bottom-up from the DETAILED design (Phase 7, fidelity ladder L0 → L1 → L2).

Input (``manufacturing.detailed``; every number from the detailed design, a shop time study or a dated quote)::

    parts:                      # actual part list (drawings / CAD / FEM model / ply book)
      - name: wing upper skin LH
        l1_part: wing skin      # L1 part it refines (default: match by group + kind) — for the calibration
        group: wing
        kind: skin
        count: 1
        material: cf_fabric_vari  # key of manufacturing.materials
        process: vacuum_infusion
        mass_kg: 1.92            # flown mass of one part (CAD / weighing)
        area_m2: 1.31            # actual moulded/machined area
        perimeter_m: 6.1         # joined edge length
        thickness_m: 0.0012
        n_plies: 4               # ply book (composites)
        max_dim_m: 2.9
        fasteners: {count: 64, usd_each: 0.9, year: 2026, provenance: {...}}   # actual fastener schedule
        labour_hours: 5.5        # optional: shop time study / router (same basis as hours_basis)
        tooling_cost: 4800       # optional: mould quote (USD, study year)
        quote: {usd: 950, year: 2026, provenance: {...}}   # optional: supplier quote per part (replaces the model)
    bom:                        # purchased items with researched supplier prices or quotes
      - {item: engine, qty: 1, usd: 9800, year: 2026, quote: true, provenance: {...}}
    final_assembly_hours: 120   # per aircraft (router / time study)
    final_assembly_rate_usd_h: 85
    non_recurring_usd: null     # programme NRC (engineering, certification, test); default: Eastlake (flagged)

Parts without a quote are costed with the same process models as L1 (:mod:`.processes` through :func:`.plan.plan`),
but on the ACTUAL geometry, ply count, fastener count and the user's hours/tooling where given.
"""
from __future__ import annotations

from acdt.ai.external import check_provenance

from . import refdata as R
from .plan import plan
from .processes import Part

PART_FIELDS = ("name", "kind", "mass_kg", "area_m2", "perimeter_m", "max_dim_m", "thickness_m", "count", "group",
               "double_curvature", "axisymmetric", "n_plies", "material")


def _esc(usd: float, y, year: int, cpi_table=None) -> float:
    y = int(y if y is not None else year)
    return float(usd) * (R.cpi_factor(year, y, cpi_table) if y != year else 1.0)


def key_of(p: dict) -> str:
    return p.get("l1_part") or f"{p.get('group', '')}:{p.get('kind', '')}"


def estimate(dcfg: dict, materials: dict, N: int, year: int, *, process_inputs=None, learning=None,
             hours_basis="first_unit", tooling_pool=None, cpi_table=None, nonrec_per_unit_fallback=0.0) -> dict:
    parts_in = list(dcfg.get("parts") or [])
    if not parts_in:
        raise ValueError("detailed.parts is empty: L2 needs the part list of the detailed design")
    warn, rows = [], []
    modelled = [p for p in parts_in if not p.get("quote")]
    quoted = [p for p in parts_in if p.get("quote")]
    P = []
    for p in modelled:
        for f in ("name", "kind", "mass_kg", "area_m2", "material", "process"):
            if p.get(f) is None:
                raise ValueError(f"detailed part {p.get('name')!r}: '{f}' missing (L2 uses the detailed geometry)")
        P.append(Part(**{k: p[k] for k in PART_FIELDS if k in p and p[k] is not None}))
    choices = {p["name"]: {"materials": [p["material"]], "processes": [p["process"]]} for p in modelled}
    pl = plan(P, materials, N, choices=choices, process_inputs=process_inputs, year=year, learning=learning,
              hours_basis=hours_basis, tooling_pool=tooling_pool, cpi_table=cpi_table, scaling=None) if P else None
    LF = pl["learning_factor"] if pl else 1.0
    byname = {r["part"]["name"]: r for r in (pl["parts"] if pl else [])}
    tot = {"structure": 0.0, "structure_quoted": 0.0, "labour_hours": 0.0, "material_cost": 0.0, "labour_cost": 0.0,
           "fastener_cost": 0.0, "tooling_per_unit": 0.0}
    unresolved = []
    for p in modelled:
        r = byname[p["name"]]
        s = r["selected"]
        if s is None:
            unresolved.append(p["name"])
            rows.append({"name": p["name"], "key": key_of(p), "basis": "infeasible", "reasons":
                         [o["reasons"] for o in r["options"]]})
            continue
        s = dict(s)
        basis = ["process model on detailed geometry"]
        if p.get("labour_hours") is not None:
            s["labour_hours"] = float(p["labour_hours"])
            basis.append("labour hours: shop time study (input)")
        if p.get("tooling_cost") is not None:
            s["tooling_cost"] = float(p["tooling_cost"])
            s["tooling_per_unit"] = s["tooling_cost"] / N
            basis.append("tooling: quote (input)")
        fa = p.get("fasteners")
        if fa:
            s["fasteners"] = int(fa["count"])
            s["fastener_cost"] = s["fasteners"] * _esc(fa.get("usd_each", 0.0), fa.get("year"), year, cpi_table)
            basis.append("fasteners: detailed schedule (input)")
            if fa.get("usd_each") is None:
                warn.append(f"{p['name']}: fastener price missing (usd_each)")
        lab = (s["labour_hours"] or 0.0) * s["labour_rate_usd_h"] * LF
        if s["material_cost"] is None:
            unresolved.append(p["name"])
            continue
        unit = s["material_cost"] + lab + s["fastener_cost"] + s["machine_cost"] + s["tooling_per_unit"]
        c = s["count"]
        tot["structure"] += unit * c
        tot["labour_hours"] += (s["labour_hours"] or 0.0) * LF * c
        tot["material_cost"] += s["material_cost"] * c
        tot["labour_cost"] += lab * c
        tot["fastener_cost"] += s["fastener_cost"] * c
        tot["tooling_per_unit"] += s["tooling_per_unit"] * c
        rows.append({"name": p["name"], "key": key_of(p), "count": c, "process": s["process"],
                     "material": s["material"], "labour_hours": (s["labour_hours"] or 0.0) * LF * c,
                     "material_cost": s["material_cost"] * c, "unit_cost": unit * c,  # per aircraft "basis": "; ".join(basis),
                     "warnings": s["warnings"]})
    for p in quoted:
        q = p["quote"]
        pv, iss = check_provenance(q.get("provenance"))
        u = _esc(q["usd"], q.get("year"), year, cpi_table) * int(p.get("count", 1))
        tot["structure"] += u
        tot["structure_quoted"] += u
        rows.append({"name": p["name"], "key": key_of(p), "count": int(p.get("count", 1)), "process": "quote",
                     "material": p.get("material"), "labour_hours": None, "material_cost": None, "unit_cost": u,
                     "basis": "supplier quote", "provenance": pv, "issues": iss})
    bom, bom_tot, bom_q = [], 0.0, 0.0
    for b in dcfg.get("bom") or []:
        pv, iss = check_provenance(b.get("provenance"))
        u = _esc(b["usd"], b.get("year"), year, cpi_table) * float(b.get("qty", 1))
        bom_tot += u
        if b.get("quote"):
            bom_q += u
        if iss:
            warn.append(f"BOM {b.get('item')}: {'; '.join(map(str, iss))}")
        bom.append({"item": b.get("item"), "qty": b.get("qty", 1), "usd": u, "quote": bool(b.get("quote")),
                    "provenance": pv})
    fah = dcfg.get("final_assembly_hours")
    fa = None
    if fah is None:
        warn.append("final assembly / systems installation hours not given (final_assembly_hours): not costed")
    else:
        rate = dcfg.get("final_assembly_rate_usd_h")
        if rate is None:
            raise ValueError("detailed.final_assembly_rate_usd_h is required with final_assembly_hours")
        fa = float(fah) * float(rate)
    if dcfg.get("non_recurring_usd") is not None:
        nrc, nrc_src = float(dcfg["non_recurring_usd"]) / N, "input"
    else:
        nrc, nrc_src = nonrec_per_unit_fallback, "Eastlake eng+dev+flight test / N (no L2 NRC given)"
        warn.append("non-recurring cost taken from Eastlake (L0) — give detailed.non_recurring_usd")
    recurring = tot["structure"] + bom_tot + (fa or 0.0)
    unit = recurring + nrc
    quoted_share = (tot["structure_quoted"] + bom_q) / recurring if recurring else 0.0
    return {"level": "L2", "N": N, "year": year, "learning_factor": LF, "parts": rows, "bom": bom,
            "totals": {**tot, "bom": bom_tot, "bom_quoted": bom_q, "final_assembly": fa, "recurring": recurring,
                       "non_recurring_per_unit": nrc, "unit_cost": unit},
            "non_recurring_source": nrc_src, "quoted_share_of_recurring": quoted_share,
            "unresolved_parts": unresolved, "warnings": warn}
