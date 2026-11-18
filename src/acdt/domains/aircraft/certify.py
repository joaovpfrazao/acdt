"""Phase 10 driver: certification basis → safety assessment (FHA/FTA/FMEA + redundancy OPTIONS fed back into W0)
→ compliance matrix → SORA, with CSV/XLSX/Markdown/PNG outputs.

YAML: an optional top-level ``certification:`` block in the aircraft spec (ignored by the sizing loader)::

    certification:
      basis: stanag4671            # optional override (else automatic, see core.certification.basis)
      max_passenger_seats: 3       # CS 23.2005 level
      safety:
        t_flight_h: 1.0            # average flight duration for P/flight-hour (PRESSUPOSTO)
        options: {servo: dual}     # force options (else the trade selects)
        baseline: {backup_battery: true}   # options already carried in the design's mass budget
        unit: {battery_kg: 1.2, servo_cost: 900}   # option unit masses/costs (PRESSUPOSTO, supplier data)
        rate_overrides: {uav_servo: {lambda_per_h: 2e-4, source: "..."}}
        supplier_rates: {uav_c2_link: {lambda_per_h: 2e-4, source: "...", retrieved: "2026-11-10"}}
        latent_exposure: {batt: 50}   # hours between checks for latent failures
        severity_overrides: {FC-U2: major}
      sora: {population: "<50", aec: 10, mitigations: {M2: medium}, v_max_m_s: 45, vlos: false,
             containment: {adjacent_population_density_per_km2: 20, outdoor_assembly: "<40k"}}
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

from acdt.core.certification import build_matrix, plot_summary, select_basis, sora, to_markdown, write_csv, write_xlsx
from . import safety_assessment as SA

SCHEME_OF = {"cs23": None, "cs25": "amc25_1309", "stanag4671": "stanag4671", "stanag4703": "stanag4703"}


def _resize(spec, dm: float) -> float:
    from .sizing import run
    sp = copy.deepcopy(spec)
    sp.assumptions["weights"]["fixed_mass_kg"] = sp.assumptions["weights"].get("fixed_mass_kg", 0.0) + dm
    return float(run(sp).sizing.W0)


def certify(spec_path, outdir, cert: dict | None = None, run_full: bool = True, log=print) -> dict:
    from acdt.core.pipeline import run_pipeline
    from .report import to_dict
    spec_path = Path(spec_path)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    c = dict(raw.get("certification") or {}) | dict(cert or {})
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    log("pipeline …")
    st = run_pipeline("aircraft", spec_path, output=out / "design" if run_full else None)
    res = st["result"]
    r = to_dict(res)
    sel = select_basis(r, c)
    ctx = sel["context"]
    W0 = float(r["weights"]["W0_kg"])
    sc = dict(c.get("safety") or {})
    notes = list(sel["notes"])

    # ---------------- safety assessment
    base = sel["bases"][0]
    scheme = SCHEME_OF[base] or f"ac23_1309_class_{ctx.ac23_class}"
    template = "uas" if ctx.uav else ("ga_piston" if "piston" in str(ctx.propulsion) else None)
    safety = trade = None
    if template:
        T = float(sc.get("t_flight_h", 1.0))
        if "t_flight_h" not in sc:
            notes.append("duração média de voo T = 1 h (PRESSUPOSTO; definir certification.safety.t_flight_h)")
        unit = dict(sc.get("unit") or {})
        if template == "uas":
            from .systems_integration import select_systems
            sy = select_systems(res, res.spec.systems or {})
            sv = [s for s in sy.servos if s.servo and any(k in s.name for k in ("aileron", "elevator", "rudder"))]
            if sv and "servo_kg" not in unit:
                unit["servo_kg"] = max(s.servo["mass"] for s in sv)
                unit["n_servo_channels"] = sum(s.n_servos * (2 if "each" in s.name else 1) for s in sv)
                notes.append(f"servo redundante = mesmo servo selecionado ({unit['servo_kg']:.3f} kg, "
                             f"{unit['n_servo_channels']} canais; superfície dividida, PRESSUPOSTO conservador)")
            for x in sy.servos:
                if x.servo is None:
                    notes.append(f"{x.name}: sem servo na base de dados para {x.torque_required:.1f} N·m — massa da "
                                 "redundância deste canal não contabilizada (em aberto)")
                elif x.n_servos > 1:
                    notes.append(f"{x.name}: {x.n_servos} servos por partilha de binário (não redundância); a FTA "
                                 "considera um canal por superfície e a opção 'dual' duplica-os todos")
            if sy.autopilot and "fcc_kg" not in unit:
                unit["fcc_kg"] = sy.autopilot["mass"]
                notes.append(f"FCC redundante = {sy.autopilot['id']} ({sy.autopilot['mass']} kg; não certificado — "
                             "massa de referência)")
        log("re-sizing for dW0/dm …")
        growth = float(sc["growth"]) if "growth" in sc else _resize(res.spec, 1.0) - _resize(res.spec, 0.0)
        kw = dict(overrides=sc.get("rate_overrides"), latent_exposure=sc.get("latent_exposure"),
                  severity_overrides=sc.get("severity_overrides"),
                  supplier_rates=sc.get("supplier_rates"))
        trade = SA.redundancy_trade(template, scheme, T, W0, unit, growth, baseline=sc.get("baseline"), **kw)
        chosen = dict(sc.get("options") or trade["selected"]["options"])
        if sc.get("options"):
            trade["reason"] = "opções impostas pelo utilizador (certification.safety.options)"
            trade["selected"] = next(x for x in trade["rows"] if x["options"] == {**trade["selected"]["options"], **chosen})
        safety = SA.assess(template, trade["selected"]["options"], scheme, T, W0, keep_trees=True, **kw)
        safety["meets"] = SA.meets(safety)
        sel_row = trade["selected"]
        if abs(sel_row["dm_kg"]) > 1e-9:
            log("re-sizing with selected options …")
            sel_row["W0_resized_kg"] = _resize(res.spec, sel_row["dm_kg"])
        trees = safety.pop("_trees")
        pngs = {}
        for fid, ft in trees.items():
            pngs[fid] = ft.plot(out / f"fta_{fid}.png", title=f"{fid} — {ft.name}", t_flight=T)
        safety["fta_png"] = pngs
        SA.plot_trade(trade, out / "redundancy_trade.png", title=f"Estudo de redundância — {spec_path.stem}")
        from acdt.core.safety import fmea as F
        rows = SA.fmea_from(safety)
        F.write_csv(rows, out / "fmea.csv")
        (out / "safety.md").write_text(SA.to_markdown(safety, trade) + "\n## FMEA\n\n" + F.to_markdown(
            rows, ["componente", "λ_modo [1/h]", "efeito no sistema (condição de falha)", "severidade",
                   "ponto único de falha", "tipo de dado"]), encoding="utf-8")
    else:
        notes.append("avaliação de segurança automática só para os modelos 'ga_piston' e 'uas' — em aberto")

    # ---------------- SORA
    so = None
    if sel["sora"]:
        s_in = dict(c.get("sora") or {})
        vn = (r.get("structures") or {}).get("vn") or {}
        vmax = float(s_in.get("v_max_m_s") or vn.get("VD_EAS_m_s") or r["aero"].get("cruise_speed_m_s"))
        if "v_max_m_s" not in s_in:
            notes.append(f"SORA: velocidade máxima = V_D {vmax:.1f} m/s (PRESSUPOSTO conservador)")
        if "population" not in s_in:
            notes.append("SORA: densidade populacional '<50' (rural) PRESSUPOSTO — definir certification.sora")
        so = sora.assess(sora.SoraInput(float(r["geometry"]["wing"]["span_m"]), vmax, s_in.get("population", "<50"),
                                        int(s_in.get("aec", 10)), s_in.get("mitigations") or {}, W0,
                                        bool(s_in.get("vlos", False)), s_in.get("containment")))
        (out / "sora.md").write_text(sora.to_markdown(so), encoding="utf-8")

    # ---------------- matrix
    extra = {"safety": safety} if safety else {}
    m = build_matrix(r, c, extra=extra)
    m["notes"] = list(dict.fromkeys(m["notes"] + notes))
    write_csv(m, out / "compliance_matrix.csv")
    xl = write_xlsx(m, out / "compliance_matrix.xlsx")
    (out / "compliance_matrix.md").write_text(to_markdown(m), encoding="utf-8")
    plot_summary(m, out / "compliance_summary.png", title=f"{spec_path.stem}: " + ", ".join(m["bases"]))

    summary = {"spec": str(spec_path), "W0_kg": W0, "bases": m["bases"], "rationale": m["rationale"],
               "counts": m["counts"], "notes": m["notes"], "scheme": scheme if template else None,
               "xlsx": xl}
    if safety:
        summary["safety"] = {"options": safety["options"], "meets": safety["meets"],
                             "failure_conditions": [{k: f.get(k) for k in ("id", "name", "severity", "target_per_fh",
                                                     "P_per_fh", "status", "single_point_failures", "required")}
                                                    for f in safety["failure_conditions"]],
                             "cumulative_catastrophic": safety.get("cumulative_catastrophic"),
                             "selected": {k: trade["selected"].get(k) for k in ("options", "dm_kg", "dW0_kg", "dcost",
                                                                                 "W0_resized_kg", "missing_inputs")},
                             "reason": trade["reason"], "growth_dW0_dm": trade["growth_dW0_dm"],
                             "baseline_n_fail": trade["baseline"]["n_fail"]}
    if so:
        summary["sora"] = {k: so.get(k) for k in ("iGRC", "final_GRC", "residual_ARC", "SAIL", "category",
                                                  "design_route", "column", "containment")}
    (out / "certification.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str),
                                            encoding="utf-8")
    md = [f"# Certificação e segurança — {spec_path.stem}", "", to_markdown(m)]
    if safety:
        md.append((out / "safety.md").read_text(encoding="utf-8"))
    if so:
        md.append(sora.to_markdown(so))
    (out / "certification.md").write_text("\n".join(md), encoding="utf-8")
    return summary
