"""Manufacturing & cost study of a sized design (Phase 7): parts -> process plan -> bottom-up cost, compared with
the top-down CERs (modified Eastlake, DAPCA IV), optional operating cost and validation against a public price.

Configuration: ``assumptions.manufacturing`` of the mission spec (all values inputs with provenance)::

    year: 2025                 # study year (USD of that year); CPI-U escalation from refdata (or cpi_table)
    N: 820                     # production quantity (Eastlake: 5-year production)
    materials:                 # key -> {base: library key | full dict, overrides..., price: {usd_per_kg, year,
                               #          provenance: {source_url, retrieved, source_type}}}
    groups: {default: al2024_t3, wing: ..., fuselage: ...}   # material each component was sized in
    choices: {...}             # per part/kind/group: {materials: [...], processes: [...]}
    process_inputs: {...}      # per process: labour_rate_usd_h, tooling_cost, cure_h, envelope_m, ...
    learning: {slope: 0.85, theory: crawford}
    hours_basis: first_unit    # | standard
    labour_calibration: 1.0    # multiplier on process hours (calibrate against shop data / top-down CER)
    tooling: eastlake          # tooling pool for parts without a quote: eastlake | dapca | none
    purchased: {engine: {usd, year, provenance}, ...}   # bought-in items (escalated to the study year)
    final_assembly_hours: null # per aircraft (systems installation, paint, test) — input, not modelled
    validation: {price_usd, year, source}               # public price to compare with
    operating: {...}           # costing.OperatingInputs fields
    configuration: conventional  # or a list of unconventional features (flags the L0 CERs as outside database)
    labour_calibration_source: null  # provenance of a numeric labour_calibration (shop data) — sets the L1 band
    detailed: {...}            # L2 detailed bottom-up (see detailed.py): parts, bom, final assembly, NRC
    cost_calibration: {file: cost_calibration.json, apply: [cost_L0, cost_L1]}   # higher level → lower

Fidelity ladder (fidelity.py): L0 top-down CERs → L1 parametric bottom-up (this decomposition) → L2 detailed
bottom-up; each level reports its confidence and AACE 18R-97 band; ``cost_calibration.json`` carries the factors
higher → lower (applied only on opt-in).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from acdt.core import materials as LIB

from ..cost import EastlakeInputs, eastlake_unit_cost, piston_engine_cost
from . import refdata as R
from .costing import DapcaInputs, dapca4, operational_cost_from_dict
from .parts import decompose
from . import detailed as DET
from . import fidelity as FID
from .plan import plan
from .processes import material_class


def resolve_materials(cfg_mats: dict) -> dict:
    out = {}
    for k, v in (cfg_mats or {}).items():
        v = dict(v or {})
        base = v.pop("base", None)
        m = LIB.get(base).to_dict() if base else {}
        m.update(v)
        for f in ("E", "G", "nu", "rho", "Ftu", "Fty", "Fcy", "Fsu", "t_min"):
            if isinstance(m.get(f), str):  # YAML 1.1 reads '35.63e9' (no exponent sign) as a string
                m[f] = float(m[f])
        m["key"] = k
        for f in ("rho", "kind"):
            if f not in m:
                raise ValueError(f"material {k}: '{f}' missing (give base: <library key> or the value)")
        out[k] = m
    return out


def _escalate(item: dict, year: int, cpi_table=None) -> float:
    y = int(item.get("year", year))
    return float(item["usd"]) * (R.cpi_factor(year, y, cpi_table) if y != year else 1.0)


def topdown(res, mcfg: dict, f_comp: float) -> dict:
    """Modified Eastlake and DAPCA IV unit cost of the sized design at N, CPI of the study year."""
    spec = res.spec
    A = spec.assumptions
    ca = dict(A.get("cost") or {})
    year = int(mcfg.get("year", 2025))
    cpi = float(mcfg.get("cpi") or R.cpi_factor(year, 2012, mcfg.get("cpi_table")))
    N = int(mcfg.get("N", ca.get("N", 500)))
    We = res.sizing.We
    vmax = (spec.requirements.value("max_speed") or res.cruise_speed) / 0.514444
    P_bhp = (res.power_sl or 0.0) / 745.69987 if getattr(res, "power_sl", None) else 0.0
    n_eng = A["propulsion"]["n_engines"]
    pur = {k: _escalate(v, year, mcfg.get("cpi_table")) for k, v in (mcfg.get("purchased") or {}).items()}
    if "engine" in pur:
        eng = pur["engine"]
    elif spec.propulsion_kind == "piston_prop":
        eng = piston_engine_cost(P_bhp, n_eng, cpi)
    else:
        eng = float(ca.get("engine_cost", 0.0))
    avi = pur.get("avionics", float(ca.get("avionics_cost", 15000.0 * cpi)))
    prop = pur.get("propeller", float(ca.get("propeller_cost", 0.0)))
    keep = {k: v for k, v in ca.items() if k in EastlakeInputs.__dataclass_fields__
            and k not in ("W_airframe_kg", "V_H_kt", "engine_cost", "N", "cpi", "avionics_cost", "f_comp",
                          "propeller_cost")}
    keep.setdefault("Q_m", N / 60.0)
    ei = EastlakeInputs(W_airframe_kg=ca.get("airframe_fraction_of_empty", 0.65) * We, V_H_kt=vmax, N=N, cpi=cpi,
                        engine_cost=eng, avionics_cost=avi, propeller_cost=prop, f_comp=f_comp, **keep)
    el = eastlake_unit_cost(ei)
    mf = 1.0 + f_comp * float(mcfg.get("dapca_composite_factor", 0.0))
    dp = dapca4(DapcaInputs(We_kg=We, V_kt=vmax, Q=N, FTA=int(ca.get("N_P", 2)), cpi=cpi, n_engines=1,
                            engine_cost=eng, avionics_cost=avi + prop, material_factor=mf))
    return {"year": year, "cpi_2012": cpi, "N": N, "V_H_kt": vmax, "We_kg": We, "f_comp": f_comp,
            "eastlake": {**el.as_dict(), "inputs": {k: getattr(ei, k) for k in ei.__dataclass_fields__}},
            "dapca4": dapca4_summary(dp), "engine_cost": eng, "avionics_cost": avi, "propeller_cost": prop,
            "airframe_fraction_of_empty": ca.get("airframe_fraction_of_empty", 0.65)}


def dapca4_summary(d: dict) -> dict:
    return {k: d[k] for k in ("unit_cost", "flyaway_per_unit", "non_recurring", "recurring", "hours", "costs", "notes")}


def study(res, mcfg: dict | None = None, out: str | Path | None = None, plots: bool = True) -> dict:
    mcfg = dict(mcfg if mcfg is not None else (res.spec.assumptions.get("manufacturing") or {}))
    year = int(mcfg.get("year", 2025))
    N = int(mcfg.get("N", (res.spec.assumptions.get("cost") or {}).get("N", 500)))
    mats = resolve_materials(mcfg.get("materials") or {})
    groups = dict(mcfg.get("groups") or {})
    if not mats or "default" not in groups:
        raise ValueError("manufacturing.materials and manufacturing.groups.default are required (materials are "
                         "inputs with a dated price and provenance)")
    gm = {g: mats[k] for g, k in groups.items()}
    dec = decompose(res, gm, mcfg.get("layout"), mcfg.get("fittings"))
    # top-down first (tooling pool, composite fraction of the structure by mass)
    m_tot = sum(p.mass_kg * p.count for p in dec["parts"]) or 1.0
    f_comp = sum(p.mass_kg * p.count for p in dec["parts"] if material_class(mats[p.material]) == "composite") / m_tot
    td = topdown(res, {**mcfg, "N": N}, f_comp)
    pool = {"eastlake": td["eastlake"]["tooling"], "dapca": td["dapca4"]["costs"]["tooling"],
            "none": None}[mcfg.get("tooling", "eastlake")]
    pi = dict(mcfg.get("process_inputs") or {})
    kc = mcfg.get("labour_calibration", 1.0)
    cal_in, applied = FID.load(mcfg, Path(mcfg["_base"]) if mcfg.get("_base") else None)
    k_mat = 1.0

    def _plan(k):
        return plan(dec["parts"], mats, N, choices=mcfg.get("choices"), process_inputs=pi, year=year,
                    learning=mcfg.get("learning"), hours_basis=mcfg.get("hours_basis", "first_unit"),
                    tooling_pool=pool, cpi_table=mcfg.get("cpi_table"), labour_calibration=k,
                    material_calibration=k_mat)
    cal_mode = None
    fl = cal_in["factors"].get("k_labour_hours_L1")
    if "cost_L1" in applied and fl is not None:
        # L2 → L1: the factor is relative to the L1 labour/material level it was computed with
        k_cal = float(fl.get("l1_labour_calibration", 1.0)) * float(fl["value"])
        fm = cal_in["factors"].get("k_material_L1")
        if fm is not None:
            k_mat = float(fm.get("l1_material_calibration", 1.0)) * float(fm["value"])
        cal_mode = (f"cost_L1 calibration from L2 (detailed design): labour k = {k_cal:.3f}, material k = "
                    f"{k_mat:.3f}" + (" — replaces the Eastlake anchoring" if kc == "eastlake" else ""))
        l1_anchor = "L2"
    elif kc == "eastlake":
        l1_anchor = 'eastlake'
        # low-fi first, then calibrate: scale the FOPV/process hours so the bottom-up structure hours per unit equal
        # the modified-Eastlake manufacturing hours per unit (whole airframe → conservative for the structure).
        # Keeps the RELATIVE part/process/material ranking of the process models; the absolute level is Eastlake's.
        raw = _plan(1.0)
        h_bu = raw["totals"]["labour_hours"]
        h_el = td["eastlake"]["hours"]["manufacturing_per_unit"]
        k_cal = h_el / h_bu if h_bu > 0 else 1.0
        cal_mode = (f"labour_calibration = eastlake: k = {h_el:.0f} h (Eastlake mfg h/unit) / {h_bu:.0f} h "
                    f"(raw bottom-up h/unit) = {k_cal:.3f} — absolute hours tied to Eastlake (GA CER; extrapolated "
                    f"outside its database, e.g. small UAVs)")
    else:
        k_cal = float(kc)
    if "cost_L1" in applied and fl is None:
        raise ValueError("cost_calibration.apply has cost_L1 but no k_labour_hours_L1 factor (run L2 first)")
    if not (("cost_L1" in applied and fl is not None) or kc == "eastlake"):
        l1_anchor = "shop" if (k_cal != 1.0 and mcfg.get("labour_calibration_source")) else "input"
    pl = _plan(k_cal)
    pur = {k: _escalate(v, year, mcfg.get("cpi_table")) for k, v in (mcfg.get("purchased") or {}).items()}
    if "engine" not in pur:
        pur["engine (Eastlake CER)" if res.spec.propulsion_kind == "piston_prop" else "engine (cost.engine_cost)"] = \
            td["engine_cost"]
    if "avionics" not in pur:
        pur["avionics (cost.avionics_cost / Gudmundsson default)"] = td["avionics_cost"]
    fa_h = mcfg.get("final_assembly_hours")
    fa_rate = float(mcfg.get("final_assembly_rate_usd_h") or (pl["parts"][0]["selected"] or {}).get(
        "labour_rate_usd_h") or 0.0) if pl["parts"] else 0.0
    fa = None if fa_h is None else float(fa_h) * fa_rate
    nonrec_per_unit = (td["eastlake"]["engineering"] + td["eastlake"]["dev_support"]
                       + td["eastlake"]["flight_test"]) / N
    bu_unit = pl["totals"]["unit_cost"] + sum(pur.values()) + (fa or 0.0) + nonrec_per_unit
    el = td["eastlake"]
    el_rec_struct = (el["manufacturing"] + el["quality"] + el["materials"]) / N
    bu_rec = pl["totals"]["labour_cost"] + pl["totals"]["material_cost"] + pl["totals"]["fastener_cost"]
    bottom_up = {"structure_parts": pl["totals"]["unit_cost"], "purchased": pur, "final_assembly": fa,
                 "non_recurring_per_unit (Eastlake eng+dev+flight test)/N": nonrec_per_unit, "unit_cost": bu_unit,
                 "notes": ["structure parts: bottom-up process model; final assembly/systems installation "
                           + ("from final_assembly_hours" if fa is not None else "NOT included (give "
                                                                                  "final_assembly_hours)"),
                           "non-recurring engineering/development/flight test taken from Eastlake (no bottom-up "
                           "model)"]}
    cal = {"eastlake_recurring_mfg_qc_mat_per_unit": el_rec_struct, "bottom_up_structure_recurring_per_unit": bu_rec,
           "ratio_eastlake_over_bottom_up": el_rec_struct / bu_rec if bu_rec else math.nan,
           "eastlake_mfg_hours_per_unit": el["hours"]["manufacturing_per_unit"],
           "bottom_up_hours_per_unit": pl["totals"]["labour_hours"],
           "note": "Eastlake manufacturing covers the whole airframe (parts, assembly, systems installation) "
                   "while the bottom-up covers the structural parts — a ratio > 1 is expected; a ratio << 1 "
                   "means the FOPV parameters (transport-wing parts) overestimate these parts: set "
                   "labour_calibration from shop data (or 'eastlake')",
           "labour_calibration": k_cal, "labour_calibration_mode": cal_mode or "input",
           "material_calibration": k_mat}
    l2 = None
    if mcfg.get("detailed"):
        l2 = DET.estimate(mcfg["detailed"], mats, N, year, process_inputs=pi, learning=mcfg.get("learning"),
                          hours_basis=mcfg.get("hours_basis", "first_unit"), tooling_pool=pool,
                          cpi_table=mcfg.get("cpi_table"), nonrec_per_unit_fallback=nonrec_per_unit)
    appl = FID.cer_applicability(res, mcfg)
    new_cal = FID.build(res.spec.name, td, {"unit_cost": bu_unit, "learning_factor": pl["learning_factor"]},
                        pl["parts"], l2, l1_independent=(l1_anchor != "eastlake"),
                        sources={"year": year, "N": N, "l1_labour_calibration": k_cal})
    if "k_labour_hours_L1" in new_cal["factors"]:
        new_cal["factors"]["k_labour_hours_L1"]["l1_labour_calibration"] = k_cal
    if "k_material_L1" in new_cal["factors"]:
        new_cal["factors"]["k_material_L1"]["l1_material_calibration"] = k_mat
    fid = FID.levels(td, {"unit_cost": bu_unit}, l2, appl, l1_anchor, applied, cal_in)
    fid.update({"applied_calibration": applied, "calibration_in": cal_in, "calibration_out": new_cal})
    m_sized = sum(p.mass_kg * p.count for p in dec["parts"])
    pl["mass_change"] = {"sized_structure_kg": m_sized, "selected_structure_kg": pl["totals"]["flown_mass_kg"],
                         "delta_kg": pl["totals"]["flown_mass_kg"] - m_sized,
                         "note": "mass change of the selected materials (Ashby scaling) is NOT fed back into the "
                                 "sizing loop — use the Pareto sweep / re-size with the chosen material"}
    result = {"year": year, "N": N, "parts": [p.to_dict() for p in dec["parts"]], "decomposition_notes": dec["notes"],
              "f_comp": f_comp, "plan": pl, "topdown": td, "bottom_up": bottom_up, "calibration": cal,
              "detailed": l2, "fidelity": fid,
              "references": {k: R.ref(k) for k in sorted({s for r in pl["parts"] for o in r["options"]
                                                         for s in o["sources"]} | {"gudmundsson2014", "raymer_dapca",
                                                                                   "bls_cpi", "nasa_learning",
                                                                                   "aace_18r97"})}}
    if mcfg.get("operating"):
        oi = dict(mcfg["operating"])
        oi.setdefault("unit_price", (mcfg.get("validation") or {}).get("price_usd") or el["unit_cost"])
        result["operating"] = operational_cost_from_dict(oi)
    if mcfg.get("validation"):
        v = mcfg["validation"]
        p = float(v["price_usd"]) * (R.cpi_factor(year, int(v["year"]), mcfg.get("cpi_table"))
                                     if int(v.get("year", year)) != year else 1.0)
        result["validation"] = {"public_price_usd": p, "source": v.get("source"),
                                "eastlake_unit_cost": el["unit_cost"], "dapca4_unit_cost": td["dapca4"]["unit_cost"],
                                "bottom_up_unit_cost": bu_unit,
                                "ratio_eastlake": el["unit_cost"] / p, "ratio_dapca4": td["dapca4"]["unit_cost"] / p,
                                "ratio_bottom_up": bu_unit / p,
                                "note": "models give manufacturer COST; a list PRICE adds profit, liability, "
                                        "distribution — ratio < 1 expected"}
    if out is not None:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "manufacturing.json").write_text(json.dumps(_clean(result), indent=1, default=str))
        (out / "manufacturing.md").write_text(markdown(result))
        FID.write(_clean(new_cal), out / "cost_calibration.json")
        if plots:
            result["plots"] = make_plots(result, out, res=res, mcfg=mcfg)
    return result


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def markdown(r: dict) -> str:
    td, bu, pl = r["topdown"], r["bottom_up"], r["plan"]
    L = [f"# Fabrico e custo — N = {r['N']}, USD {r['year']}", "",
         f"CPI-U {r['year']}/2012 = {td['cpi_2012']:.4f}; fração compósita da estrutura f_comp = {r['f_comp']:.2f}", "",
         "## Custo unitário (top-down vs bottom-up)", "", "| modelo | custo unitário (USD) |", "|---|---:|",
         f"| Eastlake (Gudmundsson 2014) | {td['eastlake']['unit_cost']:,.0f} |",
         f"| DAPCA IV (Raymer 2018) | {td['dapca4']['unit_cost']:,.0f} |",
         f"| bottom-up (peças + comprados + NRC Eastlake) | {bu['unit_cost']:,.0f} |", ""]
    fid = r.get("fidelity")
    if fid:
        L += ["## Escada de fidelidade (L0 → L1 → L2)", "",
              "| nível | método | custo unitário (USD) | confiança | banda AACE 18R-97 (80 %) |", "|---|---|---:|---|---|"]
        for k, lv in fid["levels"].items():
            b = lv["band"]
            L.append(f"| {k} | {lv['method']} | {lv['unit_cost']:,.0f} | {lv['confidence']} | Classe {b['aace_class']}: "
                     f"{b['low']:,.0f} – {b['high']:,.0f} ({b['low_pct']:+.0f} % / {b['high_pct']:+.0f} %) |")
        l0 = fid["levels"]["L0"]
        L += ["", f"Nível recomendado: **{fid['recommended']}** ({fid['recommended_why']}). CERs fora da base de dados: "
                  f"{'sim — ' + '; '.join(l0['reasons']) if l0['outside_database'] else 'não'}. "
                  f"Dispersão Eastlake/DAPCA IV: {l0['model_spread']['ratio_max_min']:.2f}x.", ""]
        if fid["levels"]["L1"].get("note"):
            L += [f"L1: {fid['levels']['L1']['note']}", ""]
        F = fid["calibration_out"]["factors"]
        L += ["Fatores de calibração (nível superior → inferior; `cost_calibration.json`; aplicados: "
              f"{', '.join(fid['applied_calibration']) or 'nenhum'}):", ""]
        L += [f"- `{k}` = {f['value']:.3f} ({f['what']})" + ("" if f.get("independent", True) else " — NÃO independente")
              for k, f in F.items() if f.get("value") is not None]
        L.append("")
    if "validation" in r:
        v = r["validation"]
        L += [f"Preço público: {v['public_price_usd']:,.0f} USD — {v['source']}", "",
              f"Razões modelo/preço: Eastlake {v['ratio_eastlake']:.2f}, DAPCA IV {v['ratio_dapca4']:.2f}, "
              f"bottom-up {v['ratio_bottom_up']:.2f} ({v['note']})", ""]
    L += ["## Plano de fabrico (processo escolhido por peça)", "",
          "| peça | n | material | processo | massa (kg) | h/peça | B2F | custo/aeronave (USD) |",
          "|---|---:|---|---|---:|---:|---:|---:|"]
    for row in pl["parts"]:
        s = row["selected"]
        if s is None:
            L.append(f"| {row['part']['name']} | {row['part']['count']} | — | sem opção viável | | | | |")
            continue
        L.append(f"| {row['part']['name']} | {s['count']} | {s['material']} | {s['process']} | {s['mass_kg']:.2f} | "
                 f"{(s['labour_hours'] or 0) * pl['learning_factor']:.1f} | {s['b2f']:.2f} | {s['unit_cost']:,.0f} |")
    t = pl["totals"]
    L += ["", f"Totais/aeronave: material {t['material_cost']:,.0f}, mão-de-obra {t['labour_cost']:,.0f} "
              f"({t['labour_hours']:.0f} h), fixadores {t['fastener_cost']:,.0f}, máquina {t['machine_cost']:,.0f}, "
              f"ferramental/N {t['tooling_per_unit']:,.0f} — total {t['unit_cost']:,.0f} USD; comprado "
              f"{t['bought_mass_kg']:.0f} kg para {t['flown_mass_kg']:.0f} kg voados", "",
          "## Calibração", "", f"Eastlake (fabrico+QC+material)/N = {r['calibration']['eastlake_recurring_mfg_qc_mat_per_unit']:,.0f}"
          f" USD vs bottom-up estrutura {r['calibration']['bottom_up_structure_recurring_per_unit']:,.0f} USD "
          f"(razão {r['calibration']['ratio_eastlake_over_bottom_up']:.2f}). {r['calibration']['note']}", "",
          "## Notas", ""] + [f"- {n}" for n in r["decomposition_notes"] + pl["notes"] + bu["notes"]]
    if "operating" in r:
        o = r["operating"]
        pfh = o.get("per_flight_hour")
        assessed = o.get("assessed_sum_per_fh")
        st = o.get("status") or ("ok" if not o.get("missing_inputs") else "partial")
        if st == "ok" and pfh is not None:
            head = f"{pfh:,.0f} USD/h de voo: "
        else:
            suma = assessed if assessed is not None else 0
            head = (f"status={st}, soma avaliada {suma:,.0f} USD/h "
                    f"(não é DOC completo; unassessed≠zero): ")
        missing = o.get("unassessed_terms") or o.get("missing_inputs") or []
        L += ["", "## Custo de operação", "", head +
              ", ".join(f"{k} {v:,.0f}" for k, v in (o.get("items_per_fh") or {}).items()) +
              (f" — inputs em falta: {', '.join(missing)}" if missing else "")]
    L += ["", "## Referências", ""] + [f"- {v}" for v in r["references"].values()]
    return "\n".join(L) + "\n"


def make_plots(r: dict, out: Path, res=None, mcfg=None) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker  # noqa: F401
    files = {}
    td, pl = r["topdown"], r["plan"]
    el = td["eastlake"]
    N = r["N"]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    cats = [("engenharia+dev+ensaios /N", (el["engineering"] + el["dev_support"] + el["flight_test"]) / N),
            ("ferramental /N", el["tooling"] / N), ("fabrico+QC /N", (el["manufacturing"] + el["quality"]) / N),
            ("materiais /N", el["materials"] / N), ("motor+hélice+aviónica", el["per_unit_variable"])]
    bottom = 0
    for name, v in cats:
        ax.bar("Eastlake", v, bottom=bottom, label=name)
        bottom += v
    dc = td["dapca4"]["costs"]
    dcat = [(dc["engineering"] + dc["dev_support"] + dc["flight_test"]) / N, dc["tooling"] / N,
            (dc["manufacturing"] + dc["quality"]) / N, dc["materials"] / N,
            dc["engines_per_aircraft"] + dc["avionics_per_aircraft"]]
    bottom = 0
    for (name, _), v in zip(cats, dcat):
        ax.bar("DAPCA IV", v, bottom=bottom, color=None)
        bottom += v
    t = pl["totals"]
    bu = r["bottom_up"]
    bcat = [bu["non_recurring_per_unit (Eastlake eng+dev+flight test)/N"], t["tooling_per_unit"],
            t["labour_cost"] + t["fastener_cost"] + t["machine_cost"] + (bu["final_assembly"] or 0), t["material_cost"],
            sum(bu["purchased"].values())]
    bottom = 0
    for v in bcat:
        ax.bar("bottom-up", v, bottom=bottom)
        bottom += v
    if "validation" in r:
        ax.axhline(r["validation"]["public_price_usd"], color="k", ls="--", label="preço público")
    ax.set_ylabel(f"USD {r['year']} por aeronave")
    ax.set_title(f"Custo unitário a N = {N}")
    ax.legend(fontsize=7)
    fig.tight_layout()
    p = out / "cost_breakdown.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    files["cost_breakdown"] = str(p)
    # per-part options
    fig, ax = plt.subplots(figsize=(9, 5))
    names = [row["part"]["name"] for row in pl["parts"]]
    procs = sorted({o["process"] + " / " + o["material"] for row in pl["parts"] for o in row["options"]
                    if o["unit_cost"] is not None and o["feasible"]})
    w = 0.8 / max(len(procs), 1)
    for j, pr in enumerate(procs):
        ys = []
        for row in pl["parts"]:
            v = [o["unit_cost"] for o in row["options"] if o["process"] + " / " + o["material"] == pr
                 and o["unit_cost"] is not None and o["feasible"]]
            ys.append(v[0] if v else 0)
        ax.bar([i + j * w for i in range(len(names))], ys, w, label=pr)
    for i, row in enumerate(pl["parts"]):
        if row["selected"]:
            ax.text(i + 0.4 - w / 2, 0, "★", ha="center", va="bottom", fontsize=8)
    ax.set_xticks([i + 0.4 - w / 2 for i in range(len(names))])
    ax.set_xticklabels(names, rotation=40, ha="right", fontsize=8)
    ax.set_ylabel("USD por aeronave (todas as unidades da peça)")
    ax.set_title(f"Opções material/processo por peça (N = {N})")
    ax.legend(fontsize=6, ncol=2)
    fig.tight_layout()
    p = out / "process_options.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    files["process_options"] = str(p)
    # unit cost vs N (top-down)
    if res is not None:
        Ns = [10, 25, 50, 100, 200, 500, 1000, 2000]
        e, d = [], []
        for n in Ns:
            x = topdown(res, {**(mcfg or {}), "N": n}, r["f_comp"])
            e.append(x["eastlake"]["unit_cost"])
            d.append(x["dapca4"]["unit_cost"])
        fig, ax = plt.subplots(figsize=(6.5, 4.2))
        ax.loglog(Ns, e, "o-", label="Eastlake")
        ax.loglog(Ns, d, "s-", label="DAPCA IV")
        ax.axvline(N, color="grey", ls=":")
        if "validation" in r:
            ax.axhline(r["validation"]["public_price_usd"], color="k", ls="--", label="preço público")
        ax.set_xlabel("quantidade produzida N")
        ax.set_ylabel(f"custo unitário (USD {r['year']})")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()
        fig.tight_layout()
        p = out / "unit_cost_vs_N.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        files["unit_cost_vs_N"] = str(p)
    fid = r.get("fidelity")
    if fid:
        lv = fid["levels"]
        names = list(lv)
        v = [lv[k]["unit_cost"] for k in names]
        lo = [lv[k]["unit_cost"] - lv[k]["band"]["low"] for k in names]
        hi = [lv[k]["band"]["high"] - lv[k]["unit_cost"] for k in names]
        fig, ax = plt.subplots(figsize=(7, 4.2))
        col = {"low": "#d9534f", "low-medium": "#f0ad4e", "medium": "#f7d26a", "medium-high": "#9bc53d",
               "high": "#5cb85c"}
        ax.bar(names, v, yerr=[lo, hi], capsize=8, color=[col.get(lv[k]["confidence"], "#999") for k in names],
               edgecolor="k")
        for i, k in enumerate(names):
            ax.text(i, v[i], f"  {v[i]/1e3:,.0f} k\n  {lv[k]['confidence']}\n  AACE {lv[k]['band']['aace_class']}",
                    va="bottom", ha="left", fontsize=8)
        if "L0" in lv:
            ax.scatter([0, 0], [lv["L0"]["eastlake"], lv["L0"]["dapca4"]], marker="_", s=400, c="k", zorder=5)
            ax.text(-0.45, lv["L0"]["dapca4"], "DAPCA IV", fontsize=7)
        if "validation" in r:
            ax.axhline(r["validation"]["public_price_usd"], ls="--", c="gray")
            ax.text(len(names) - 0.5, r["validation"]["public_price_usd"], "preço público", fontsize=7, ha="right",
                    va="bottom")
        ax.set_ylabel(f"custo unitário (USD {r['year']})")
        ax.set_title("Escada de fidelidade do custo: estimativa, confiança e banda AACE 18R-97 (80 %)", fontsize=9)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x/1e3:,.0f} k"))
        fig.tight_layout()
        p = out / "cost_levels.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        files["cost_levels"] = str(p)
    return files


# ---------------------------------------------------------------------------------------------- file driver
def load_config(mission: str | Path, config: str | Path | None = None) -> dict:
    """{mission, manufacturing, pareto?}. ``mission`` may itself be a manufacturing config with ``mission:``
    (path relative to the config); otherwise ``config`` (or the mission's ``assumptions.manufacturing``)."""
    import yaml
    mission = Path(mission)
    d = yaml.safe_load(mission.read_text(encoding="utf-8")) or {}
    if config is None and "manufacturing" in d and "mission" in d:
        config, d = mission, None
    if config is not None:
        c = yaml.safe_load(Path(config).read_text(encoding="utf-8")) or {}
        mp = c.get("mission")
        mpath = (Path(config).parent / mp).resolve() if (mp and d is None) else mission
        return {"mission": str(mpath), "manufacturing": {**(c.get("manufacturing") or {}),
                                                          "_base": str(Path(config).parent.resolve())},
                "pareto": c.get("pareto")}
    m = (d.get("assumptions") or {}).get("manufacturing")
    if not m:
        raise ValueError("no manufacturing config: give --config or assumptions.manufacturing in the mission")
    return {"mission": str(mission), "manufacturing": {**m, "_base": str(mission.parent.resolve())},
            "pareto": d["assumptions"].get("manufacturing_pareto")}


def run_files(cfg: dict, out: str | Path, pareto: bool = False, log=print) -> dict:
    """Size the mission (L0/L1 pipeline), run the study and, optionally, the W0–cost Pareto sweep."""
    import json

    from ..mission import MissionSpec
    from .. import sizing
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    log(f"dimensionamento: {cfg['mission']}")
    res = sizing.run(MissionSpec.from_yaml(cfg["mission"]))
    st = study(res, cfg["manufacturing"], out=out, plots=True)
    files = {"json": str(out / "manufacturing.json"), "md": str(out / "manufacturing.md"),
             "cost_calibration": str(out / "cost_calibration.json"), **st.get("plots", {})}
    r = {"study": st, "files": files}
    if pareto:
        from .pareto import sweep
        p = cfg.get("pareto") or {}
        if not p.get("options"):
            raise ValueError("pareto: 'options' missing in the config")
        log(f"Pareto: {len(p['options'])} opções × W/S × AR")
        pr = sweep(res, cfg["manufacturing"], p["options"], p.get("ws_factors", (0.8, 0.9, 1.0)),
                   p.get("AR_values"), p.get("cost_metric", "bottom_up"), out=out,
                   feed_mass_change=p.get("feed_mass_change", True))
        (out / "pareto.json").write_text(json.dumps(_clean(pr), indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        files["pareto_json"] = str(out / "pareto.json")
        files["pareto_png"] = pr.get("plot")
        r["pareto"] = pr
    return r
