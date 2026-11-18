"""Command-line interface: ``acdt size <mission.yaml> [-o outdir]``, ``acdt optimize <mission.yaml>``,
``acdt requirements``, ``acdt mcp`` (MCP server for AI agents)."""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

from acdt import G0
from acdt.core.pipeline import InfeasibleError, run_pipeline
from acdt.core.provenance import note_output
from acdt.core.requirements import RequirementError, types_for


def _cmd_size(a) -> int:
    import yaml

    domain = (yaml.safe_load(Path(a.mission).read_text(encoding="utf-8")) or {}).get("domain", "aircraft")
    out = Path(a.output or Path("out") / Path(a.mission).stem)
    try:
        st = run_pipeline(domain, a.mission, output=out, no_systems=a.no_systems)
    except (InfeasibleError, RequirementError) as e:
        print(f"[acdt] requisitos inconsistentes: {e}", file=sys.stderr)
        return 2
    res, rep, spec = st["result"], st.get("report_path"), st["spec"]
    dp = res.design_point
    print(f"[acdt] {spec.name}: {'VIÁVEL' if res.feasible else 'INVIÁVEL'}")
    print(f"  W0 = {res.sizing.W0:.2f} kg, We/W0 = {res.sizing.empty_fraction:.3f}, iterações = {res.iterations}")
    if dp.ws == dp.ws:
        v = dp.value * G0 if dp.metric == "P/W" else dp.value
        print(f"  W/S = {dp.ws / G0:.2f} kg/m², {dp.metric} = {v:.4g} {'W/kg' if dp.metric == 'P/W' else ''}")
        print(f"  S = {res.S:.3f} m², b = {res.config.wing.span:.2f} m, ativas: {', '.join(dp.active)}")
    _phase2_summary(res)
    lp = getattr(res, "assembly_loop", None)
    if lp:
        import json
        from acdt.ai.toolkit import clean
        out.mkdir(parents=True, exist_ok=True)
        (out / "assembly_scaled.json").write_text(json.dumps(clean(lp["spec_scaled"]), indent=1, ensure_ascii=False),
                                                  encoding="utf-8")
        print(f"  montagem dimensionada: {out / 'assembly_scaled.json'} (acdt integration … --step --rcs)")
    for i in res.issues:
        print(f"  [{i.severity}] {i.message}")
    for c in res.checks:
        if c.ok is False:
            print(f"  [falha] {c.key}: {c.message}")
    v = getattr(res, "verified", None)
    print(f"  verificação da missão (Fase 2): {'OK' if v else ('FALHA' if v is False else 'n/a')}")
    print(f"  relatório: {rep}")
    return 0 if res.feasible else 1


def _cmd_integration(a) -> int:
    """P1: packaging / FOV / mass-CG check of a JSON spec {assembly, items, constraints, base}."""
    import json
    from acdt.domains.aircraft.assembly import Assembly, check

    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    asm = Assembly.from_dict(spec["assembly"])
    res = check(asm, spec.get("items", []), spec.get("constraints"), spec.get("base"))
    out = Path(a.output or Path("out") / (Path(a.spec).stem + "_integration"))
    out.mkdir(parents=True, exist_ok=True)
    note_output(out)
    from acdt.ai.toolkit import clean
    (out / "integration.json").write_text(json.dumps(clean(res), indent=1, ensure_ascii=False), encoding="utf-8")
    asm.write_stl(out / "assembly.stl")
    try:
        (out / "assembly.avl").write_text(asm.avl_text(), encoding="utf-8")
    except ValueError:
        pass
    for c in res["constraints"]:
        tag = "OK " if c["ok"] else "FALHA"
        who = c.get("item") or "/".join(str(c[k]) for k in ("a", "b") if k in c) or c.get("body", "")
        m = c.get("margin")
        extra = f" bloqueado por {c['blocked_by']}" if c.get("blocked_by") and not c["ok"] else ""
        print(f"  [{tag}] {c['type']:<20} {who:<16} margem {m if m is None else round(m, 4)} {c.get('unit', '')}{extra}")
    mp = res["mass_properties"]
    print(f"  massa {mp.get('mass_kg', 0):.2f} kg, CG {[round(v, 3) for v in mp.get('cg', [])]} m; potência média "
          f"{res['power_w']['avg']:.0f} W (pico {res['power_w']['peak']:.0f} W)")
    print(f"  {'OK' if res['ok'] else str(res['n_violations']) + ' violações'} — resultados em {out}")
    ok = res["ok"]
    if getattr(a, "step", False) or getattr(a, "rcs", False):
        from acdt.domains.aircraft.assembly.export import export_step, rcs_input, rcs_quick
        if a.step:
            st = export_step(asm, out / "assembly.step")
            print(f"  STEP: {st['step'] or 'não escrito'}" + "".join(f"; {n}" for n in st["notes"]))
        if a.rcs:
            from acdt.domains.aircraft.assembly.integration import Item as _Item
            items = [_Item.from_dict(d) for d in spec.get("items") or []]
            ri = rcs_input(asm, out, items=items)
            q = rcs_quick(ri["mesh"])
            (out / "rcs_quick.json").write_text(json.dumps(q, indent=1), encoding="utf-8")
            (out / "rcs_inventory.json").write_text(json.dumps(ri.get("inventory"), indent=1, ensure_ascii=False),
                                                    encoding="utf-8")
            inv = ri.get("inventory") or {}
            print(f"  RCS: {ri['stl']} ({ri['n_facets']} facetas; {ri['frame']}); verificação PO 10 GHz VV "
                  + ", ".join(f"az {z:+.0f}° {d:.1f} dBsm" for z, d in zip(q["az_deg"], q["dBsm"]))
                  + f"; inventário {len(inv.get('included', []))} incluídos / "
                    f"{len(inv.get('excluded_presupposto', []))} excluídos / "
                    f"{len(inv.get('unassessed', []))} unassessed"
                  + " — polar completo: acdt rcs stl <stl> (Grok Build, HANDOFF §4b)")
    if getattr(a, "np_validation", False):
        from acdt.domains.aircraft.assembly.validation import run_case, write_report
        row = run_case(spec, Path(a.spec).stem, float((spec.get("validation") or {}).get("mach", 0.0)))
        (out / "np_validation.json").write_text(json.dumps(clean(row), indent=1, ensure_ascii=False), encoding="utf-8")
        write_report([row], out / "np_validation.md")
        if "xbar_np" in row:
            x = row["xbar_np"]
            print(f"  x̄_np (CMA): AVL c/ corpos {x['avl_bodies']:.3f}, s/ corpos {x['avl_no_bodies']:.3f}, "
                  f"+Torenbeek {x['avl_torenbeek']:.3f}, limite Munk {x['munk_bound']:.3f}"
                  + ("" if row["avl_within_munk"] else " — AVL com corpos além do limite de Munk"))
        else:
            print(f"  validação do ponto neutro: {row.get('note')}")
    if getattr(a, "size", False):
        from acdt.domains.aircraft.assembly.sizing import analyse
        if "flight" not in spec:
            print("  --size precisa de 'flight' {W0_kg, V_m_s, altitude_m, n_limit, ...} no JSON")
            return 2
        sz = analyse(spec, spec["flight"])
        (out / "assembly_sizing.json").write_text(json.dumps(clean(sz.summary()), indent=1, ensure_ascii=False),
                                                  encoding="utf-8")
        for p_ in sz.structure:
            print(f"  massa {p_.name:<14} {p_.mass_kg:7.2f} kg  {p_.method}")
        print(f"  CD0 (áreas molhadas) {sz.drag['CD0']:.4f}")
        for key, c_ok, msg in sz.checks:
            print(f"  [{'OK ' if c_ok else 'FALHA'}] {key}: {msg}")
        for n in sz.notes:
            print(f"  nota: {n}")
        ok = ok and all(c[1] for c in sz.checks)
    return 0 if ok else 1


def _cmd_cad(a) -> int:
    import yaml
    from acdt.domains.aircraft.cad_export import export_cad

    domain = (yaml.safe_load(Path(a.mission).read_text(encoding="utf-8")) or {}).get("domain", "aircraft")
    out = Path(a.output or Path("out") / (Path(a.mission).stem + "_cad"))
    try:
        st = run_pipeline(domain, a.mission, output=out)
    except (InfeasibleError, RequirementError) as e:
        print(f"[acdt] requisitos inconsistentes: {e}", file=sys.stderr)
        return 2
    res = st["result"]
    x_apex = res.stability.x_wing_apex if getattr(res, "stability", None) is not None else None
    try:
        info = export_cad(res.config, out / "cad", x_wing_apex=x_apex, oml_step=a.oml)
    except (RuntimeError, OSError) as e:
        print(f"[acdt] CAD: {e}", file=sys.stderr)
        return 1
    print(f"[acdt] CAD: {info['n_parts']} peças")
    print(f"  DXF: {info['dxf']}")
    print(f"  STEP: {info['step'] or 'não escrito'}")
    for note in info["notes"]:
        print(f"  {note}")
    return 0


def _cmd_optimize(a) -> int:
    from acdt.core.mdo import openmdao_available
    if not openmdao_available():
        print("[acdt] OpenMDAO não instalado: pip install 'acdt[mdo]'", file=sys.stderr)
        return 2
    from acdt.domains.aircraft.mdo import optimize_pipeline
    out = Path(a.output or Path("out") / (Path(a.mission).stem + "_mdo"))
    note_output(out)
    try:
        r = optimize_pipeline(a.mission, out, a.objective, a.solver)
    except (InfeasibleError, RequirementError, RuntimeError, ValueError) as e:
        print(f"[acdt] otimização impossível: {e}", file=sys.stderr)
        return 2
    o = r["opt"]
    print(f"[acdt] otimização ({o['objective']}, {o['solver']}, região de confiança {len(o['trust_region'])} it): "
          + ("melhoria aceite" if o["improved"] else "nenhum passo aceite (base ótima)"))
    pb, po = o["pipeline"]["baseline"], o["pipeline"]["optimum"]
    for k in ("W0 [kg]", "AR", "W/S [N/m²]", "b [m]", "energia bateria [Wh]", "Wf/bateria [kg]",
              "autonomia (segmentos) [h]", "alcance (segmentos) [km]", "falhas"):
        if k in pb:
            f = (lambda v: f"{v:.4g}") if isinstance(pb[k], float) else str
            print(f"  {k}: {f(pb[k])} → {f(po[k])}")
    print(f"  relatório: {r['report']}")
    return 0


def _phase2_summary(res):
    """One-line-per-discipline Phase 2 key results (if the stages ran)."""
    sr, st, pf = getattr(res, "structures", None), getattr(res, "stability", None), getattr(res, "performance", None)
    if getattr(res, "lowfi", None) is not None:
        print(f"  aero low-fi ({res.lowfi.airfoil_source}/{res.lowfi.span_source}): CD0 = {res.lowfi.CD0:.4f}, "
              f"e = {res.lowfi.e_eff:.3f}, clmax = {res.lowfi.clmax_airfoil:.2f}")
    if sr is not None:
        r = sr.box.mass / sr.wing_mass_raymer if sr.wing_mass_raymer else float("nan")
        print(f"  V-n ({sr.vn.regulation}): n_lim = {sr.vn.n_limit_pos:.2f} ({sr.vn.governing}); caixão da asa "
              f"{sr.box.mass:.2f} kg vs Raymer {sr.wing_mass_raymer or float('nan'):.2f} kg (razão {r:.2f})")
    l1 = getattr(res, "structures_l1", None)
    if l1 is not None and l1.masses.get("fuselage_kg") is not None:
        ratio = l1.masses.get("fuselage_over_raymer")
        ratio_s = f"{ratio:.2f}" if isinstance(ratio, float) else "—"
        extra = ""
        if l1.elastic is not None and l1.elastic.applied and isinstance(l1.elastic.K_ratio, float):
            extra = f"; torção de ponta {l1.elastic.tip_twist_deg:.2f}° (K×{l1.elastic.K_ratio:.3f})"
        print(f"  estruturas L1: fuselagem {l1.masses['fuselage_kg']:.1f} kg "
              f"(Raymer {ratio_s}), HT {l1.masses.get('htail_kg', float('nan')):.1f} kg, "
              f"VT {l1.masses.get('vtail_kg', float('nan')):.1f} kg{extra}")
    if st is not None:
        print(f"  estabilidade: SM = {100 * st.SM_fwd:.1f} … {100 * st.SM_aft:.1f} % MAC, NP = {st.xbar_np:.3f} MAC"
              + (f" (AVL {st.xbar_np_avl:.3f})" if st.xbar_np_avl is not None else ""))
    dy = getattr(res, "dynamics", None)
    if dy and dy.get("modes"):
        lon, lat = dy["modes"]["longitudinal"], dy["modes"].get("lateral") or {}
        sp, ph = lon.get("short_period", {}), lon.get("phugoid", {})
        dr = lat.get("dutch_roll", {})
        print(f"  modos: período curto ζ = {sp.get('zeta', float('nan')):.2f} ωn = {sp.get('wn', float('nan')):.2f} "
              f"rad/s; fugóide ζ = {ph.get('zeta', float('nan')):.3f}; rolamento holandês ζ = "
              f"{dr.get('zeta', float('nan')):.3f}; MIL-F-8785C níveis "
              + ", ".join(f"{r['key']} N{r['nível']}" for r in dy.get("hq", [])))
    ae = getattr(res, "aeroelastic", None)
    if ae is not None:
        parts = []
        for k, m in ae.margins.items():
            parts.append(f"{k} " + ("sem ocorrência" if not math.isfinite(m["margin"]) else f"{100 * m['margin']:+.0f} %"))
        print("  aeroelasticidade (margem vs 1.2 V_D): " + ", ".join(parts))
    wb = getattr(res, "weight_balance", None)
    if wb is not None and wb.evaluated:
        print(f"  peso e centragem: {'dentro dos limites' if wb.within_limits else 'fora dos limites'} — {wb.message}")
    gear = getattr(res, "landing_gear", None)
    if gear is not None and gear.kind != "none":
        failed = [key for key, ok, _ in gear.checks if ok is False]
        geom = {True: "ok", False: "falha"}.get(gear.geometry_ok, "n/d")
        parts = [f"geometria {geom}"]
        if gear.tipback_deg is not None and math.isfinite(gear.tipback_deg):
            parts.append(f"tombo {gear.tipback_deg:.1f}°")
        if gear.overturn_deg is not None and math.isfinite(gear.overturn_deg):
            parts.append(f"capotagem {gear.overturn_deg:.1f}°")
        if gear.descent_ft_s is not None:
            parts.append(f"V = {gear.descent_ft_s:.2f} ft/s")
        if gear.stroke_m is not None:
            parts.append(f"curso {gear.stroke_m:.3f} m")
        if gear.n_gear is not None:
            parts.append(f"n_g = {gear.n_gear:.2f}")
        if failed:
            parts.append("falhas: " + ", ".join(failed))
        print(f"  trem ({gear.kind}): " + ", ".join(parts))
    if pf is not None:
        print(f"  desempenho: alcance = {pf.mission.range_m / 1e3:.0f} km, autonomia = "
              f"{pf.mission.endurance_s / 3600:.2f} h")
        for c in pf.requirement_compare:
            print(f"    {c['grandeza']}: {c['obtido']:.4g} vs requerido {c['requerido']:.4g} {c['unidade']} → "
                  f"{'OK' if c['ok'] else 'FALHA'}")


def _cmd_hifi(a) -> int:
    from acdt.domains.aircraft.hifi.run import STEPS, run_hifi

    out = a.output or str(Path("output") / (Path(a.mission).stem + "_hifi"))
    steps = tuple(a.steps.split(",")) if a.steps else STEPS
    R = run_hifi(a.mission, out, steps, a.force, max_time_min=a.max_time_min)
    for k, v in R["steps"].items():
        st = "—" if v is None else ("ignorado: " + v["skipped"].splitlines()[0] if "skipped" in v else "ok")
        print(f"  {k:12s} {st}")
    print(f"  relatório: {R['report']}")
    return 0


def _cmd_wingbox(a) -> int:
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.wingbox.study import run_study

    res = run_pipeline("aircraft", a.mission)["result"]
    obj = a.objective or ("endurance" if res.sizing.energy_J else "range")
    out = a.output or str(Path("output") / (Path(a.mission).stem + "_wingbox"))
    tcs = [float(v) for v in a.tc.split(",")] if a.tc else None
    s = run_study(res, out, obj, Path(a.mission).stem, tc_sweep=tcs, maxiter=a.maxiter, fem=not a.no_fem,
                  hold_section=True if a.hold_section else None)
    b, o = s["baseline"], s["optimum"]
    print(f"  caixão {b['box_mass_kg']:.2f} → {o['box_mass_kg']:.2f} kg; L/D {b['cruise']['L_D']:.2f} → "
          f"{o['cruise']['L_D']:.2f}; longarinas {o['x']['xf']:.3f}/{o['x']['xr']:.3f} c; t/c {o['x']['tc_root']:.3f}")
    for k, v in s["paths"].items():
        print(f"  {k}: {v}")
    return 0



def _cmd_rib_simp(a) -> int:
    import json
    from acdt.ai.toolkit import clean
    from acdt.domains.aircraft.wingbox.rib_simp_mass import apply_simp_rib_mass, rib_web_mass_from_simp
    pth = Path(a.input)
    txt = pth.read_text(encoding="utf-8")
    raw = json.loads(txt) if pth.suffix.lower() == ".json" else __import__("yaml").safe_load(txt)
    dest = Path(a.output or "output/rib_simp_mass.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if raw.get("masses") and raw.get("ribs"):
        cfg = raw.get("rib_simp_mass") or raw
        out = apply_simp_rib_mass(
            raw["masses"], raw["ribs"],
            rho_kg_m3=cfg.get("rho_kg_m3") or raw.get("rho_kg_m3"),
            rho_source=cfg.get("rho_source") or raw.get("rho_source") or "",
            t_source=cfg.get("t_source", raw.get("t_source",
                             "sizing6.size_ribs (Niu 1988 §5.4 crushing/shear/buckling/min gauge)")),
            vol=cfg.get("vol", raw.get("vol")), penal=cfg.get("penal", raw.get("penal")),
            nelx=int(cfg.get("nelx", raw.get("nelx", 40))),
            iters=int(cfg.get("iters", raw.get("iters", 40))),
            rmin=float(cfg.get("rmin", raw.get("rmin", 1.8))),
            nu=float(cfg.get("nu", raw.get("nu", 0.33))),
            stations=cfg.get("stations", raw.get("stations", "all")),
            nonoptimum_factor=raw.get("nonoptimum_factor"),
        )
    else:
        rib = raw.get("rib") or raw
        out = rib_web_mass_from_simp(
            w_m=rib.get("w_m"), h_m=rib.get("h_m"), p_crush_N_m=rib.get("p_crush_N_m"),
            dV_N=rib.get("dV_N"), t_m=rib.get("t_m"), rho_kg_m3=rib.get("rho_kg_m3"),
            vol=rib.get("vol"), penal=rib.get("penal", 3.0),
            rmin=float(rib.get("rmin", 1.8)), nu=float(rib.get("nu", 0.33)),
            nelx=int(rib.get("nelx", 40)), iters=int(rib.get("iters", 40)),
            rho_source=rib.get("rho_source"), t_source=rib.get("t_source"),
        )
    dest.write_text(json.dumps(clean(out), indent=2, ensure_ascii=False), encoding="utf-8")
    st = out.get("status")
    if "ribs_simp_kg" in out:
        print(f"[acdt] rib-simp: status={st} nervuras {out.get('ribs_sized_kg')} → {out.get('ribs_simp_kg')} kg "
              f"(Δ {out.get('delta_kg')} kg)")
    else:
        print(f"[acdt] rib-simp: status={st} m_web={out.get('mass_web_kg')} kg vol={out.get('vol_achieved')}")
    if out.get("unassessed_terms"):
        print("  unassessed:", "; ".join(map(str, out["unassessed_terms"])))
    print(f"  → {dest}")
    return 0 if st == "ok" else 2


def _cmd_wingbox6(a) -> int:
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.wingbox.study6 import run_study6

    res = run_pipeline("aircraft", a.mission)["result"]
    obj = a.objective or ("endurance" if res.sizing.energy_J else "range")
    stem = Path(a.mission).stem
    out = a.output or str(Path("output") / (stem + "_wingbox6"))
    p5 = a.phase5 or str(Path(a.mission).parent / "output" / f"{stem}_wingbox" / f"{stem}_wingbox.json")
    cfg = None
    if getattr(a, "rib_simp_mass", None):
        import json as _json
        pth = Path(a.rib_simp_mass)
        cfg = _json.loads(pth.read_text(encoding="utf-8")) if pth.suffix.lower() == ".json" else __import__("yaml").safe_load(pth.read_text(encoding="utf-8"))
    s = run_study6(res, out, obj, stem, material=a.material, maxiter=a.maxiter, fem=not a.no_fem, phase5_json=p5,
                   rib_simp_mass=cfg, hold_section=True if a.hold_section else None)
    b, o = s["baseline"], s["optimum"]
    print(f"  caixão {b['box_mass_kg']:.2f} → {o['box_mass_kg']:.2f} kg; L/D {b['cruise']['L_D']:.2f} → "
          f"{o['cruise']['L_D']:.2f}; n_str {s['n_str']}; nervuras {o['phase6']['n_ribs_semispan']}/semiasa")
    for k, v in s["paths"].items():
        print(f"  {k}: {v}")
    return 0


def _cmd_rcs(a) -> int:
    import json as _json

    from acdt.core.em import validate
    from acdt.core.em.po import LIMITATIONS
    from acdt.domains.aircraft.rcs import study

    print(f"  AVISO: {LIMITATIONS}")
    if a.mode == "validate":
        ok = True
        for c in validate.cases(a.freq * 1e9):
            d = f"Δ = {c['delta_db']:+.3f} dB" if c.get("po_dbsm") is not None else f"max|Δ| = {c['max_abs_delta_db']:.2e} dB"
            print(f"  {'OK ' if c['ok'] else 'FALHA'} {c['case']}: {d} (tol ±{c['tol_db']} dB)")
            ok &= c["ok"]
        return 0 if ok else 1
    src = Path(a.input)
    out = Path(a.output or (Path("output") / (src.stem.replace("result", src.parent.name) + "_rcs")))
    out.mkdir(parents=True, exist_ok=True)
    if a.mode == "stl":
        r = study.stl_polar(src, out / f"{src.stem}_rcs_polar.png", a.freq * 1e9, a.el, a.daz)
        (out / f"{src.stem}_rcs.json").write_text(_json.dumps(r, indent=1))
        for p_, m in r["frontal"].items():
            print(f"  {p_}: frontal (|az| ≤ 30°) mean {m['mean_dbsm']:.2f} dBsm, mediana {m['median_dbsm']:.2f}, "
                  f"máx {m['max_dbsm']:.2f}")
        print(f"  polar: {r['png']}")
        return 0
    if src.suffix in (".yaml", ".yml"):
        rc = main(["size", str(src), "-o", str(out / "size")])
        src = out / "size" / "result.json"
        if not src.exists():
            print(f"  dimensionamento falhou (rc={rc})")
            return 2
    # Opt-in assembly path: JSON with top-level "assembly" → RCS/aero from the montage (chine, items),
    # not the parallel parametric faceted aircraft. Backward compatible with result.json studies.
    if src.suffix == ".json":
        peek = _json.loads(src.read_text(encoding="utf-8"))
        if isinstance(peek, dict) and "assembly" in peek and "geometry" not in peek:
            r = study.run_assembly_study(src, out, a.freq * 1e9, n_samples=a.samples,
                                         log=lambda m: print("  " + m))
            print(f"  baseline RCS frontal {r['baseline_rcs_mean_dbsm']:.2f} dBsm; Pareto {r['pareto_ids']}")
            for u in r.get("unassessed_shape_vars") or []:
                print(f"  [unassessed] Shape var {u['var']}: {u['reason']}")
            inv = r.get("inventory") or {}
            print(f"  inventário: {len(inv.get('included', []))} incluídos, "
                  f"{len(inv.get('excluded_presupposto', []))} excluídos (PRESSUPOSTO), "
                  f"{len(inv.get('unassessed', []))} unassessed")
            for k, v in r.get("files", {}).items():
                print(f"  {k}: {v}")
            return 0
    refine = [float(v) for v in a.refine.split(",")] if a.refine else ()
    r = study.run_study(src, out, a.freq * 1e9, a.samples, refine, log=lambda m: print("  " + m))
    for k, v in r["picks"].items():
        print(f"  {k}: {v['shape']} → desempenho ×{v['aero']['perf_ratio']:.3f}, L/D {v['aero']['LD']:.2f}, "
              f"RCS frontal {v['rcs']['all']['mean_dbsm']:.2f} dBsm")
    for k, v in r["files"].items():
        print(f"  {k}: {v}")
    return 0


def _cmd_manufacture(a) -> int:
    from acdt.domains.aircraft.manufacturing.study import load_config, run_files

    cfg = load_config(a.mission, a.config)
    out = Path(a.output or (Path("output") / (Path(cfg["mission"]).stem + "_manufacturing")))
    r = run_files(cfg, out, pareto=a.pareto, log=lambda m: print("  " + m))
    st = r["study"]
    bu, td = st["bottom_up"], st["topdown"]
    print(f"[acdt] fabrico/custo N={st['N']}, USD {st['year']}: bottom-up {bu['unit_cost']:,.0f}, "
          f"Eastlake {td['eastlake']['unit_cost']:,.0f}, DAPCA IV {td['dapca4']['unit_cost']:,.0f} por unidade")
    for k, (pr, m) in st["plan"]["selection"].items():
        print(f"  {k}: {pr} / {m}")
    if st["plan"]["unresolved_parts"]:
        print(f"  [aviso] peças sem processo viável/completo: {', '.join(st['plan']['unresolved_parts'])}")
    if "validation" in st:
        v = st["validation"]
        print(f"  validação vs preço público {v['public_price_usd']:,.0f} ({v['source']}): Eastlake "
              f"×{v['ratio_eastlake']:.2f}, DAPCA ×{v['ratio_dapca4']:.2f}, bottom-up ×{v['ratio_bottom_up']:.2f}")
    if "pareto" in r:
        for q in r["pareto"]["pareto"]:
            print(f"  Pareto: {q['option']} W/S={q['ws']:.0f} AR={q['AR']:.2f} W0={q['W0']:.1f} kg "
                  f"custo={q['unit_cost']:,.0f}")
    for k, v in r["files"].items():
        print(f"  {k}: {v}")
    return 0


def _size_for(mission: str, out: Path):
    import yaml
    domain = (yaml.safe_load(Path(mission).read_text(encoding="utf-8")) or {}).get("domain", "aircraft")
    st = run_pipeline(domain, mission, output=out / "size")
    return st["result"]


def _cmd_controls(a) -> int:
    from acdt.domains.aircraft.flightsim.study import controls_study

    out = Path(a.output or (Path("output") / (Path(a.mission).stem + "_controls")))
    res = _size_for(a.mission, out)
    s = controls_study(res, out)
    ai, el, ru = s["aileron"], s["elevator"], s["rudder"]
    print(f"[acdt] superfícies de controlo ({Path(a.mission).stem})")
    print(f"  ailerão: fração de envergadura atual {ai.get('current_span_fraction')} → dimensionada "
          f"{ai.get('sized_span_fraction')} (cumpre atual: {ai.get('ok_current')})")
    print(f"  profundor: cf/c dimensionado {el.get('sized_cf_c')}   leme: cf/c dimensionado {ru.get('sized_cf_c')}")
    for x in (ai, el, ru):
        if x.get("note"):
            print(f"  aviso: {x['note']}")
    print(f"  layout dimensionado: {s['layout_sized']}")
    for n in s["notes"]:
        print(f"  nota: {n}")
    for k, v in s["files"].items():
        print(f"  {k}: {v}")
    return 0


def _kv(text: str | None) -> dict:
    """'a=1,b=x,c=true' → {a: 1.0, b: 'x', c: True}."""
    out = {}
    for it in filter(None, (text or "").split(",")):
        k, v = it.split("=", 1)
        lv = v.strip().lower()
        if lv in ("true", "false"):
            out[k.strip()] = lv == "true"
        else:
            try:
                out[k.strip()] = float(v)
            except ValueError:
                out[k.strip()] = v.strip()
    return out


def _cmd_certify(a) -> int:
    from acdt.domains.aircraft.certify import certify
    out = Path(a.output or (Path("output") / (Path(a.mission).stem + "_certification")))
    cert = {}
    if a.basis:
        cert["basis"] = a.basis
    if a.passengers is not None:
        cert["max_passenger_seats"] = a.passengers
    saf = {}
    if a.t_flight:
        saf["t_flight_h"] = a.t_flight
    if a.options:
        saf["options"] = _kv(a.options)
    if saf:
        import yaml
        raw = yaml.safe_load(Path(a.mission).read_text(encoding="utf-8")) or {}
        cert["safety"] = dict((raw.get("certification") or {}).get("safety") or {}) | saf
    s = certify(a.mission, out, cert, log=lambda m: print(f"[acdt] {m}"))
    print(f"[acdt] base(s): {', '.join(s['bases'])} — " + "; ".join(s["rationale"]))
    print("  matriz: " + ", ".join(f"{k} {v}" for k, v in s["counts"].items()))
    sa = s.get("safety")
    if sa:
        for f in sa["failure_conditions"]:
            p = f"{f['P_per_fh']:.2e}" if f.get("P_per_fh") is not None else "—"
            t = f"{f['target_per_fh']:.0e}" if f.get("target_per_fh") else "—"
            print(f"  {f['id']:<6} {f['name'][:46]:<46} P {p:>9} /h  alvo {t:>6}  {f['status']}")
        cc = sa.get("cumulative_catastrophic")
        if cc:
            print(f"  soma catastrófica {cc['P_per_fh']:.2e} vs {cc['target']:.2e} ({cc['ref']})")
        se = sa["selected"]
        print(f"  redundância selecionada: {se['options']} Δm {se['dm_kg']:.2f} kg, ΔW0 "
              f"{(se['dW0_kg'] or 0):.2f} kg — {sa['reason']}")
    if s.get("sora"):
        so = s["sora"]
        print(f"  SORA: iGRC {so['iGRC']} → GRC {so['final_GRC']}, ARC-{so['residual_ARC']} → SAIL {so['SAIL']} "
              f"({so['category']})")
    print(f"  saída: {out}")
    return 0


def _cmd_safety(a) -> int:
    import json
    from acdt.domains.aircraft import safety_assessment as SA
    if a.template == "sora":
        from acdt.core.certification import sora as S
        if not a.input:
            print("[acdt] safety sora: passe --input JSON (SoraInput + containment opt-in)", file=sys.stderr)
            return 2
        raw = json.loads(Path(a.input).read_text(encoding="utf-8"))
        inp = S.SoraInput(
            span_m=float(raw["span_m"]), v_max_m_s=float(raw["v_max_m_s"]),
            population=raw.get("population", "<50"), aec=int(raw.get("aec", 10)),
            mitigations=raw.get("mitigations") or {}, mtow_kg=raw.get("mtow_kg"),
            vlos=bool(raw.get("vlos", False)), containment=raw.get("containment"),
        )
        out = S.assess(inp)
        dest = Path(a.output or "output/sora.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(S.to_markdown(out))
        print(f"  → {dest}")
        return 0
    opt = _kv(a.options)
    supplier = None
    if getattr(a, "supplier_rates", None):
        supplier = json.loads(Path(a.supplier_rates).read_text(encoding="utf-8"))
        if isinstance(supplier, dict) and "supplier_rates" in supplier:
            supplier = supplier["supplier_rates"]
    if a.trade:
        t = SA.redundancy_trade(a.template, a.scheme, a.t_flight, a.mtow, _kv(a.unit), None,
                                baseline=_kv(a.baseline), supplier_rates=supplier)
        print(SA.to_markdown(t["selected"]["assessment"], t))
    else:
        print(SA.to_markdown(SA.assess(a.template, opt, a.scheme, a.t_flight, a.mtow, supplier_rates=supplier)))
    return 0


def _cmd_flap_options(a) -> int:
    from acdt.domains.aircraft.design_options import flap_options_report, flap_options_sweep
    from acdt.domains.aircraft.mission import MissionSpec

    spec = MissionSpec.from_yaml(a.mission)
    out = Path(a.output or (Path("output") / (Path(a.mission).stem + "_flap_options")))
    kw = {}
    if a.options:
        spec.assumptions.setdefault("design_options", {}).setdefault("flaps", {})["options"] = a.options.split(",")
    if a.objective:
        spec.assumptions.setdefault("design_options", {}).setdefault("flaps", {})["objective"] = a.objective
    s = flap_options_report(spec, out, **kw)
    print(f"[acdt] opções de flap ({Path(a.mission).stem}), objetivo {s['objective']}")
    for r in s["rows"]:
        if not r.get("converged"):
            print(f"  {r['option']:<16} não convergiu {r.get('error', '')} {', '.join(r.get('failed') or [])}")
            continue
        print(f"  {r['option']:<16} W0 {r['W0']:7.2f} kg  S {r['S']:.3f} m²  L/D max {r['LD_max']:5.2f}  "
              f"CLmax,L {r['CLmax_landing']:.2f}  V_max {r.get('V_max', float('nan')):5.1f} m/s  "
              f"endurance {r.get('endurance_h', float('nan')):.2f} h  flap sys {r.get('flap_system_kg', 0):.2f} kg"
              + ("" if r.get("feasible") else f"  INVIÁVEL: {', '.join(r.get('failed') or [])}"))
    print(f"  selecionado: {s['selected']} (justificado: {s['justified']}, margem mínima {100 * s['min_gain']:.1f} %)")
    d = s["deltas"].get(s["selected"]) if s["selected"] else None
    if d:
        print("  delta vs " + d["vs"] + ": " + ", ".join(f"{k} {v:+.3g}" for k, v in d.items() if k != "vs"))
    for n in s["notes"]:
        print(f"  nota: {n}")
    if a.sweep:
        key, vals = a.sweep.split("=")
        pts = flap_options_sweep(spec, key, [float(v) for v in vals.split(",")], out / f"pareto_{key}.png")
        print(f"  varrimento {key}: {len(pts)} pontos → {out / f'pareto_{key}.png'}")
    for k, v in s["files"].items():
        print(f"  {k}: {v}")
    return 0


def _print_pointmass(r) -> int:
    unit = r.get("unit", "")
    used = r.get("total_used_" + unit, float("nan"))
    print(f"[acdt] simulação massa pontual '{r.get('name')}' ({r.get('aircraft_source')}): "
          f"{r['total_time_min']:.2f} min, {r['total_dist_km']:.3f} km, consumo {used:.4g} {unit}"
          + (f" — ABORTADA: {r['aborted']}" if r.get("aborted") else ""))
    met = r.get("metrics") or {}
    if met.get("time_on_station_h"):
        print(f"  tempo em estação {met['time_on_station_h'] * 60:.2f} min"
              + (f", área varrida {met['area_swept_km2']:.3g} km²" if met.get("area_swept_km2") else ""))
    if met.get("pod_random_search") is not None:
        print(f"  POD (procura aleatória) {met['pod_random_search']:.3f}")
    for n in r.get("notes", []):
        print(f"  nota: {n}")
    for k, v in (r.get("files") or {}).items():
        print(f"  {k}: {v}")
    return 0 if not r.get("aborted") else 1



def _cmd_morph(a) -> int:
    """P2 morphological N1: matrix | generate | evaluate | prune."""
    import json
    from acdt.ai import morph as M
    if a.action == "matrix":
        extra = json.loads(Path(a.extra).read_text(encoding="utf-8")) if a.extra else None
        out = M.morph_matrix(extra)
    elif a.action == "generate":
        dims = json.loads(Path(a.matrix).read_text(encoding="utf-8")) if a.matrix else None
        if isinstance(dims, dict) and "dimensions" in dims:
            dims = dims["dimensions"]
        use = a.dimensions.split(",") if a.dimensions else None
        out = M.morph_generate(dimensions=dims, use_dimensions=use,
                               max_combinations=a.max_combinations,
                               seeds=a.matrix is None)
        print(f"[acdt] morph generate: {out['generated']} combinações, "
              f"{out['n_kept']} mantidas, {out['n_cut']} cortadas")
    elif a.action == "evaluate":
        arches = json.loads(Path(a.architectures).read_text(encoding="utf-8"))
        if isinstance(arches, dict):
            arches = arches.get("kept") or arches.get("architectures") or arches.get("rows")
        hybrid_templates = link_catalog = mission_context = operating_cost = None
        if getattr(a, "systems", None):
            sysd = json.loads(Path(a.systems).read_text(encoding="utf-8"))
            hybrid_templates = sysd.get("hybrid_templates")
            link_catalog = sysd.get("link_catalog")
            mission_context = sysd.get("mission_context")
            operating_cost = sysd.get("operating_cost") or sysd.get("operating")
        out = M.morph_evaluate(arches, a.mission, sim=a.sim, level=a.level, limit=a.limit,
                               hybrid_templates=hybrid_templates, link_catalog=link_catalog,
                               mission_context=mission_context,
                               operating_cost=operating_cost)
        n_un = out.get("n_systems_unassessed", 0)
        print(f"[acdt] morph evaluate: {out['n']} arquiteturas @ {out['level']}"
              + (f"; {n_un} com eixos energy/comms unassessed" if n_un else ""))
    elif a.action == "prune":
        rows = json.loads(Path(a.rows).read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("rows") or rows
        out = M.morph_prune(rows, band=a.band, keep=a.keep)
        print(f"[acdt] morph prune: {len(out['alive'])} vivas, {len(out['rejected'])} rejeitadas "
              f"(banda ±{out['band']:.0%})")
    else:
        print(f"[acdt] ação desconhecida: {a.action}", file=sys.stderr)
        return 2
    dest = Path(a.output or "output/morph.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  → {dest}")
    return 0






def _cmd_shape(a) -> int:
    """P6 light N2: study | bounds | packaging."""
    import json
    from acdt.ai import shape_n2 as S
    if a.action == "bounds":
        out = S.shape_bounds()
        print("[acdt] shape bounds:", ", ".join(out["bounds"]))
    elif a.action == "packaging":
        payload = json.loads(a.payload) if a.payload else None
        if a.payload and a.payload.endswith(".json") and Path(a.payload).exists():
            payload = json.loads(Path(a.payload).read_text(encoding="utf-8"))
        out = S.shape_packaging_score(a.L, a.D, a.x_wing_le, a.sensor_x, payload=payload)
        print(f"[acdt] packaging pack_ok={out['pack_ok']} score={out['pack_score']:.2f} "
              f"vol_margin={out['volume_margin_m3']:.4f} m³")
    elif a.action == "study":
        payload = None
        if a.payload:
            payload = json.loads(Path(a.payload).read_text(encoding="utf-8")) if a.payload.endswith(".json")                 else json.loads(a.payload)
        if getattr(a, "assembly", None):
            from acdt.domains.aircraft.rcs import study as R
            out = R.run_assembly_study(a.assembly, a.output or "output/assembly_rcs_study",
                                       n_samples=a.samples, seed=a.seed,
                                       log=lambda m: print("  " + m))
            print(f"[acdt] shape/assembly RCS Pareto: {out.get('pareto_ids')}  "
                  f"baseline {out['baseline_rcs_mean_dbsm']:.2f} dBsm")
        else:
            out = S.shape_n2_study(a.result, a.output or "output/shape_n2", n_samples=a.samples,
                                   seed=a.seed, payload=payload)
            print(f"[acdt] shape N2 Pareto: {out.get('pareto')}")
    else:
        print(f"[acdt] ação desconhecida: {a.action}", file=sys.stderr)
        return 2
    dest = Path(a.output_json or (Path(a.output) / "shape_n2_cli.json" if a.output else "output/shape_cli.json"))
    if a.action == "study" and out.get("files"):
        print(f"  → {out['files'].get('shape_n2.json')}")
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  → {dest}")
    return 0


def _cmd_storage(a) -> int:
    """Common storage capacity screen, separate from legacy design feasibility."""
    import json
    from acdt.ai.storage import storage_check, load_spec
    try:
        result = load_spec(a.result) if a.result else None
        out = storage_check(a.input, a.source_kind, result, a.reserve_fraction)
        text = json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False)
        dest = Path(a.output or "out/storage_check.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text+"\n", encoding="utf-8")
        print(text)
        return 0 if out["storage_feasible"] is True else (1 if out["storage_feasible"] is False else 3)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"[acdt] storage: {exc}", file=sys.stderr)
        return 2


def _cmd_fleet_study(a) -> int:
    import json
    from pathlib import Path
    from acdt.ai.mission_fleet import mission_fleet_study
    try:
        out=mission_fleet_study(a.input)
        text=json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False)
        path=Path(a.output or "output/mission_fleet_study.json");path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text+"\n",encoding="utf-8");print(text)
        return 0 if all(r["n1"]["eligible"] is True for r in out["rows"]) else 1
    except (ValueError,TypeError,KeyError,OSError) as exc:
        print(f"[acdt] fleet study: {exc}",file=sys.stderr);return 2


def _cmd_onboard(a) -> int:
    """Opt-in shared payload/electrical native sizing; unknown is not pass."""
    import json
    from pathlib import Path
    from acdt.ai.onboard import onboard_size
    try:
        out=onboard_size(a.input)
        text=json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False)
        p=Path(a.output or "output/onboard_size.json"); p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(text+"\n",encoding="utf-8"); print(text)
        return 0 if out["combined_checks_passed"] is True else 1
    except (ValueError,TypeError,KeyError,OSError) as exc:
        print(f"[acdt] onboard: {exc}",file=sys.stderr); return 2


def _cmd_jet(a) -> int:
    """Jet L0: all scalar outputs include assumptions and validity limits."""
    import json
    from pathlib import Path
    from acdt.ai import jet as J
    try:
        if a.action == "wave-drag":
            if a.mach is None:
                raise ValueError("--mach obrigatório")
            out = J.jet_wave_drag(a.mach, a.cl, a.thickness_ratio, a.sweep, a.technology_factor)
        elif a.action == "turbofan":
            if a.mach is None:
                raise ValueError("--mach obrigatório")
            out = J.jet_turbofan(a.mach, a.altitude, a.thrust, a.installation_factor,
                                 a.throttle_ratio, a.tsfc_multiplier)
        elif a.action == "loads":
            if any(v is None for v in (a.mass, a.area, a.vc)):
                raise ValueError("--mass, --area e --vc (EAS m/s) obrigatórios")
            out = J.jet_loads(a.mass, a.area, a.vc, a.cl_max, a.cl_min, a.vd_ratio)
        else:
            if not a.input:
                raise ValueError("--input obrigatório (JSON/YAML)")
            if a.action == "weights":
                out = J.jet_weights(a.input)
            elif a.action == "performance":
                out = J.jet_performance(a.input)
            elif a.action == "size":
                out = J.jet_size(a.input)
            else:
                out = J.jet_check(a.input) if a.action == "check" else J.jet_analyse(a.input)
        text = json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False)
        dest = Path(a.output or f"output/jet_{a.action}.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 1 if out.get("issues") or out.get("combined_requested_checks_passed") is False else 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"[acdt] jet: {exc}", file=sys.stderr)
        return 2


def _cmd_vtol(a) -> int:
    """VTOL / eVTOL L0: hover | size | compare."""
    import json
    from acdt.ai import vtol as V
    if a.action == "hover":
        if a.mass is None:
            print("[acdt] vtol hover: --mass obrigatório", file=sys.stderr)
            return 2
        out = V.vtol_hover(a.mass, a.n_rotors, a.diameter, a.disk_loading, a.fm, a.altitude)
        print(f"[acdt] vtol hover: T={out['thrust_total_N']:.1f} N, D={out['diameter_m']:.3f} m x{out['n_rotors']}, "
              f"DL={out['disk_loading_N_m2']:.0f} N/m², P_ideal={out['P_ideal_W']:.0f} W, "
              f"P_hover={out['P_hover_shaft_W']:.0f} W (FM {out['FM']:.2f})")
    elif a.action in ("size", "compare"):
        if not a.input:
            print(f"[acdt] vtol {a.action}: --input obrigatório", file=sys.stderr)
            return 2
        spec = V.load_spec(a.input)
        if a.architecture:
            spec["architecture"] = a.architecture
        if a.action == "size":
            out = V.vtol_size(spec)
            if "closure" in out:
                c = out["closure"]
                print(f"[acdt] vtol size ({out['architecture']}) fecho de massa: estado={c['status']}, "
                      f"MTOW={out['mtow_kg'] if out['mtow_kg'] is None else round(out['mtow_kg'], 3)} kg, "
                      f"iterações={c['solver']['iterations']}, resíduo={c['solver']['residual_kg']} kg, viável={out['feasible']}")
                if not out["converged"]:
                    dest = Path(a.output or "output/vtol_size.json")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
                    print(f"  → {dest}")
                    return 1
            print(f"[acdt] vtol size ({out['architecture']}): P_hover={out['hover']['P_hover_shaft_W']:.0f} W, "
                  f"E={out['energy_Wh']:.0f} Wh, bateria={out['battery_mass_kg']:.2f} kg "
                  f"({out['battery_mass_fraction']:.0%}, limitada por {out['battery_limiting']}), "
                  f"viável={out['feasible']}")
            print(f"  PRESSUPOSTOS: {len(out['pressupostos'])} valores por omissão (ver JSON)")
        else:
            archs = a.architectures.split(",") if a.architectures else None
            out = V.vtol_compare(spec, archs)
            for r in out["rows"]:
                print(f"  {r['architecture']:<12} n={r['n_rotors']} D={r['diameter_m']:.2f} m "
                      f"P_hover={r['P_hover_kW']:.2f} kW E={r['energy_Wh']:.0f} Wh "
                      f"bat={r['battery_mass_kg']:.2f} kg ({r['battery_mass_fraction']:.0%}) "
                      f"viável={r['feasible']}")
            print(f"[acdt] vtol compare: bateria mais leve → {out['lightest_battery']}")
    else:
        print(f"[acdt] ação desconhecida: {a.action}", file=sys.stderr)
        return 2
    dest = Path(a.output or f"output/vtol_{a.action}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  → {dest}")
    return 0


def _cmd_sensitivity(a) -> int:
    """P7: from-samples | pipeline | sobol."""
    import json
    from acdt.ai import sensitivity as S
    if a.action == "from-samples":
        data = json.loads(Path(a.input).read_text(encoding="utf-8"))
        out = S.sensitivity_from_samples(data["baseline"], data["samples"],
                                         threshold=a.threshold)
        top = (out.get("top") or [])[:5]
        print(f"[acdt] sensitivity: {len(out.get('rows') or [])} elasticidades; top:")
        for r in top:
            print(f"  |ε|={r['abs_elasticity']:.2f}  {r['metric']} ← {r['variable']}")
        hints = out.get("fidelity_hints") or []
        if hints:
            print("  fidelidade sugerida:")
            for h in hints[:5]:
                print(f"    {h['variable']}: {h['suggest']} ({h['reason']})")
    elif a.action == "pipeline":
        variables = json.loads(Path(a.variables).read_text(encoding="utf-8"))
        if isinstance(variables, dict):
            variables = variables.get("variables") or variables.get("paths") or []
            if variables and isinstance(variables[0], str):
                variables = [{"path": p} for p in variables]
        out = S.sensitivity_pipeline(a.mission, variables, rel_step=a.rel_step,
                                     no_systems=not a.with_systems, handbook=not a.lowfi,
                                     threshold=a.threshold, output=a.output and str(Path(a.output).parent)
                                     if a.output and a.output.endswith(".json") else a.output)
        top = (out.get("top") or [])[:5]
        print(f"[acdt] sensitivity: {len(out.get('rows') or [])} elasticidades; top:")
        for r in top:
            print(f"  |ε|={r['abs_elasticity']:.2f}  {r['metric']} ← {r['variable']}")
        hints = out.get("fidelity_hints") or []
        if hints:
            print("  fidelidade sugerida:")
            for h in hints[:5]:
                print(f"    {h['variable']}: {h['suggest']} ({h['reason']})")
    elif a.action == "sobol":
        if a.input:
            data = json.loads(Path(a.input).read_text(encoding="utf-8"))
            # raw Y_A/Y_B/Y_AB or {bounds+...} for analyze — prefer evaluations table
            if "Y_A" in data or "evaluations" in data:
                out = S.sensitivity_sobol(evaluate_table=data, bootstrap=a.bootstrap,
                                          conf=a.conf, seed=a.seed)
            elif a.mission and ("variables" in data or "bounds" in data):
                variables = data.get("variables") or [
                    {"path": b["name"], "low": b["low"], "high": b["high"]} for b in data["bounds"]
                ]
                out = S.sensitivity_sobol(mission=a.mission, variables=variables, n=a.n,
                                          metric=a.metric or data.get("metric", "W0_kg"),
                                          seed=a.seed, bootstrap=a.bootstrap, conf=a.conf,
                                          no_systems=not a.with_systems, handbook=not a.lowfi,
                                          rel_span=a.rel_span)
            else:
                print("[acdt] sobol: --input precisa Y_A/Y_B/Y_AB ou variables/bounds", file=sys.stderr)
                return 2
        elif a.mission and a.variables:
            variables = json.loads(Path(a.variables).read_text(encoding="utf-8"))
            if isinstance(variables, dict):
                variables = variables.get("variables") or variables.get("bounds") or []
            out = S.sensitivity_sobol(mission=a.mission, variables=variables, n=a.n,
                                      metric=a.metric, seed=a.seed, bootstrap=a.bootstrap,
                                      conf=a.conf, no_systems=not a.with_systems,
                                      handbook=not a.lowfi, rel_span=a.rel_span)
        else:
            print("[acdt] sobol: use --input (Y_A/…) ou --mission + --variables", file=sys.stderr)
            return 2
        print(f"[acdt] sensitivity sobol: status={out.get('status')} N={out.get('n')} metric={out.get('metric', '?')}")
        for r in out.get("indices") or []:
            if r.get("status") == "ok":
                ci = ""
                if r.get("S1_ci"):
                    ci = f"  S1_CI={r['S1_ci']} ST_CI={r['ST_ci']}"
                print(f"  {r['variable']}: S1={r['S1']:.4f}  ST={r['ST']:.4f}{ci}")
            else:
                print(f"  {r['variable']}: unassessed — {r.get('reason')}")
        if out.get("status") == "unassessed" and not out.get("indices"):
            print(f"  reason: {out.get('reason')}")
    elif a.action == "mc":
        percentiles = None
        if getattr(a, "percentiles", None):
            percentiles = [float(x) for x in a.percentiles.split(",")]
        if a.input and not a.mission:
            data = json.loads(Path(a.input).read_text(encoding="utf-8"))
            if "samples" in data:
                out = S.sensitivity_mc(evaluate_table=data, percentiles=percentiles)
            elif "inputs" in data:
                # need evaluate via mission
                print("[acdt] mc: --input com inputs requer --mission, ou samples pré-computadas",
                      file=sys.stderr)
                return 2
            else:
                print("[acdt] mc: --input precisa samples[] ou use --mission + --variables/--input inputs",
                      file=sys.stderr)
                return 2
        elif a.mission:
            if a.input:
                data = json.loads(Path(a.input).read_text(encoding="utf-8"))
                inputs = data.get("inputs") or data.get("variables") or data
                if isinstance(inputs, dict) and "inputs" in data:
                    inputs = data["inputs"]
                percentiles = percentiles or data.get("percentiles")
                n = data.get("n", a.n)
                method = data.get("method", a.method)
                seed = data.get("seed", a.seed)
            elif a.variables:
                data = json.loads(Path(a.variables).read_text(encoding="utf-8"))
                inputs = data.get("inputs") or data.get("variables") or data
                n, method, seed = a.n, a.method, a.seed
            else:
                print("[acdt] mc: --mission precisa --input/--variables com inputs[]", file=sys.stderr)
                return 2
            # normalize path-style variables to inputs with uniform ±rel_span if needed
            norm = []
            for it in inputs:
                if "name" not in it and "path" in it:
                    it = {**it, "name": it["path"]}
                if "dist" not in it and "low" in it and "high" in it:
                    it = {**it, "dist": "uniform"}
                norm.append(it)
            out = S.sensitivity_mc(norm, mission=a.mission, n=n, method=method, seed=seed,
                                   percentiles=percentiles, no_systems=not a.with_systems,
                                   handbook=not a.lowfi)
        else:
            print("[acdt] mc: use --mission + inputs ou --input com samples[]", file=sys.stderr)
            return 2
        print(f"[acdt] sensitivity mc: status={out.get('status')} N={out.get('n')} "
              f"ok={out.get('n_ok')} failed={out.get('n_failed')} ({out.get('method')})")
        for mk, sm in (out.get("summaries") or {}).items():
            if sm.get("status") == "ok":
                print(f"  {mk}: mean={sm['mean']:.4g}  p5={sm.get('p5')}  p50={sm.get('p50')}  "
                      f"p95={sm.get('p95')}  std={sm['std']:.4g}")
            else:
                print(f"  {mk}: unassessed — {sm.get('reason')}")
        if out.get("status") == "unassessed" and not out.get("summaries"):
            print(f"  reason: {out.get('reason')}")
    else:
        print(f"[acdt] ação desconhecida: {a.action}", file=sys.stderr)
        return 2
    dest = Path(a.output or "output/sensitivity.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  → {dest}")
    return 0


def _cmd_decisions(a) -> int:
    """P5 decision log: open | add | check | gate | list | report."""
    import json
    from acdt.ai import decisions as D
    folder = a.folder
    if a.action == "open":
        out = D.decisions_open(folder, title=a.title or "decision log", log_id=a.id)
        print(f"[acdt] decisions open → {out['path']}")
    elif a.action == "add":
        payload = json.loads(Path(a.input).read_text(encoding="utf-8")) if a.input else {}
        out = D.decisions_add(
            folder,
            what=a.what or payload["what"],
            why=a.why or payload["why"],
            fidelity=a.fidelity or payload["fidelity"],
            rejected=payload.get("rejected"),
            conditions=payload.get("conditions"),
            evidence=payload.get("evidence"),
            level_gate=payload.get("level_gate") or a.level_gate,
            tags=payload.get("tags"),
            decision_id=payload.get("id") or a.id,
        )
        print(f"[acdt] decisions add {out['decision']['id']} ({out['decision']['status']})")
    elif a.action == "check":
        metrics = json.loads(Path(a.metrics).read_text(encoding="utf-8")) if a.metrics else {}
        if isinstance(metrics, dict) and "metrics" in metrics and len(metrics) == 1:
            metrics = metrics["metrics"]
        out = D.decisions_check(folder, metrics, decision_id=a.id, reopen=a.reopen)
        inv = out.get("invalidations") or out.get("check", {}).get("invalidations") or []
        if a.reopen:
            print(f"[acdt] decisions reopen: {len(out.get('reopened', []))} reabertas")
        else:
            print(f"[acdt] decisions check: {len(inv)} invalidações")
    elif a.action == "gate":
        payload = json.loads(Path(a.metrics).read_text(encoding="utf-8")) if a.metrics else {}
        if isinstance(payload, dict) and "metrics" in payload:
            metrics = payload["metrics"]
            checks = payload.get("checks") or []
        else:
            metrics, checks = payload if isinstance(payload, dict) else {}, []
        if a.checks:
            extra = json.loads(Path(a.checks).read_text(encoding="utf-8"))
            checks = list(checks) + (extra if isinstance(extra, list) else extra.get("checks", []))
        level = a.level or a.level_gate or payload.get("level") or payload.get("level_gate")
        if not level:
            print("[acdt] decisions gate: --level N0|N1|… obrigatório", file=sys.stderr)
            return 2
        uq = None
        if getattr(a, "uq", None):
            uq = json.loads(Path(a.uq).read_text(encoding="utf-8"))
        elif isinstance(payload, dict) and payload.get("uq"):
            uq = payload["uq"]
        # metrics file may embed uq + interval_checks
        if isinstance(payload, dict) and "uq" not in (uq or {}) and payload.get("summaries"):
            uq = payload
        require_uq = bool(getattr(a, "require_uq", False) or
                          (isinstance(payload, dict) and payload.get("require_uq")))
        uq_use = getattr(a, "uq_metric_use", None) or (
            payload.get("uq_metric_use") if isinstance(payload, dict) else None) or "p50"
        out = D.decisions_gate(folder, level, metrics, checks=checks, reopen=a.reopen,
                               require_decisions=not a.allow_empty,
                               uq=uq, require_uq=require_uq, uq_metric_use=uq_use)
        print(f"[acdt] decisions gate {level}: {out['status']}"
              + (f" (ready_to_close={out['ready_to_close']})" if out.get("ready_to_close") is not None else ""))
        if out.get("uq", {}).get("applied") or out.get("uq", {}).get("require_uq"):
            print(f"  uq: applied={out['uq'].get('applied')} status={out['uq'].get('status')} "
                  f"kind={out['uq'].get('kind')}")
        for r in out.get("reasons", [])[:8]:
            print(f"  - {r}")
        if out.get("rejected_reevaluation"):
            n = sum(len(x.get("rejected_to_reevaluate") or []) for x in out["rejected_reevaluation"])
            print(f"  → {n} alternativa(s) rejeitada(s) a reavaliar (sem auto-vencedor)")
    elif a.action == "list":
        out = D.decisions_list(folder)
        for d in out["decisions"]:
            print(f"  {d['id']}: [{d['status']}] {d['what'][:60]}")
    elif a.action == "report":
        out = D.decisions_report(folder)
        print(f"[acdt] decisions report → {out['path']}")
    else:
        print(f"[acdt] ação desconhecida: {a.action}", file=sys.stderr)
        return 2
    if a.output:
        dest = Path(a.output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"  → {dest}")
    return 0



def _cmd_bemt(a) -> int:
    import json
    from acdt.ai.toolkit import clean
    raw = {}
    if a.input:
        pth = Path(a.input)
        txt = pth.read_text(encoding="utf-8")
        raw = json.loads(txt) if pth.suffix.lower() == ".json" else __import__("yaml").safe_load(txt)
    dest = Path(a.output or f"output/bemt_{a.action}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if a.action == "propeller":
        from acdt.domains.aircraft.systems_bemt import size_propeller_bemt
        P = float(raw.get("P_shaft_W") or getattr(a, "power", None) or 0)
        V = float(raw.get("V_cruise_m_s") or getattr(a, "speed", None) or 0)
        h = float(raw.get("altitude_m") or 0.0)
        cfg = raw.get("propeller") or raw
        out = size_propeller_bemt(cfg, P, V, h, raw.get("kind", "electric"))
        payload = dict(out.__dict__)
    else:
        from acdt.domains.aircraft.vtol.bemt import assess_rotor_bemt
        T = raw.get("thrust_per_rotor_N")
        out = assess_rotor_bemt(raw.get("rotor") or raw, thrust_per_rotor_N=T,
                                V_axial_m_s=float(raw.get("V_axial_m_s") or 0.0),
                                altitude_m=float(raw.get("altitude_m") or 0.0))
        payload = out
    dest.write_text(json.dumps(clean(payload), indent=2, ensure_ascii=False), encoding="utf-8")
    st = payload.get("status")
    print(f"[acdt] bemt {a.action}: status={st}")
    if a.action == "propeller":
        print(f"  D={payload.get('D')} m, rpm_cruise={payload.get('rpm_cruise')}, "
              f"J={payload.get('J_cruise')}, eta={payload.get('eta_cruise')}")
    else:
        print(f"  T={payload.get('thrust_N')} N, P={payload.get('P_shaft_W')} W, FM={payload.get('FM')}")
    if payload.get("unassessed_terms"):
        print("  unassessed:", "; ".join(payload["unassessed_terms"]))
    print(f"  → {dest}")
    return 0 if st == "ok" else 2


def _cmd_motor_deck(a) -> int:
    import json
    from acdt.ai.toolkit import clean
    from acdt.core.systems.motor_deck import assess_motor
    pth = Path(a.input)
    txt = pth.read_text(encoding="utf-8")
    raw = json.loads(txt) if pth.suffix.lower() == ".json" else __import__("yaml").safe_load(txt)
    deck = raw.get("deck") or raw.get("motor") or raw
    op = raw.get("operating") or raw
    out = assess_motor(deck, V_V=op.get("V_V"), rpm=op.get("rpm"), I_A=op.get("I_A"),
                       torque_N_m=op.get("torque_N_m"))
    dest = Path(a.output or "output/motor_deck.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(clean(out), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[acdt] motor-deck: status={out.get('status')} η={out.get('efficiency')} "
          f"P_shaft={out.get('P_shaft_W')} W I={out.get('I_A')} A")
    if out.get("unassessed_terms"):
        print("  unassessed:", "; ".join(map(str, out["unassessed_terms"])))
    print(f"  → {dest}")
    return 0 if out.get("status") == "ok" else 2


def _cmd_systems_p4(a) -> int:
    """P4: electrical | payload-trade | catalog | cost-fh | ops-cost."""
    import json
    from acdt.ai import systems_p4 as S
    if a.action == "catalog":
        out = S.electrical_catalog(a.catalog)
    elif a.action == "electrical":
        arch = json.loads(Path(a.architecture).read_text(encoding="utf-8"))
        out = S.electrical_analyse(arch, a.catalog)
        print(f"[acdt] electrical {out['id']}: ok={out['ok']} "
              f"P_avg={out['P_avg_W']:.1f} W P_peak={out['P_peak_W']:.1f} W "
              f"gen={out['generation_cont_W']:.0f} W bat={out['battery_Wh']:.0f} Wh")
        for r in out.get("reasons") or []:
            print(f"  ! {r}")
    elif a.action == "payload-trade":
        payloads = None
        if a.payloads:
            payloads = json.loads(Path(a.payloads).read_text(encoding="utf-8"))
            if isinstance(payloads, dict):
                payloads = payloads.get("payloads") or payloads.get("rows") or payloads
        kinds = a.kinds.split(",") if a.kinds else None
        obj = json.loads(a.objectives) if a.objectives else None
        cons = json.loads(a.constraints) if a.constraints else None
        out = S.payload_trade(payloads=payloads, catalog_path=a.catalog, objectives=obj,
                              constraints=cons, kinds=kinds)
        print(f"[acdt] payload-trade: {len(out['pareto'])} Pareto de {len(out['rows'])} "
              f"({', '.join(out['pareto'])})")
    elif a.action == "cost-fh":
        out = S.cost_per_flight_hour(a.rate, a.price, a.maintenance, a.other)
        print(f"[acdt] cost/fh: {out['total_per_h']:.2f} (energia {out['energy_cost_per_h']:.2f})")
    elif a.action == "ops-cost":
        if not a.operating:
            print("[acdt] ops-cost: passe --operating JSON (DOC Raymer 2018 / Eastlake CER)", file=sys.stderr)
            return 2
        op = json.loads(Path(a.operating).read_text(encoding="utf-8"))
        out = S.operational_cost(op)
        st = out.get("status")
        pfh = out.get("per_flight_hour")
        print(f"[acdt] ops-cost: status={st}"
              + (f"  {pfh:.2f} /FH" if pfh is not None else
                 f"  assessed_sum={out.get('assessed_sum_per_fh')} unassessed={out.get('unassessed_terms')}"))
    else:
        print(f"[acdt] ação desconhecida: {a.action}", file=sys.stderr)
        return 2
    dest = Path(a.output or f"output/systems_p4_{a.action.replace('-', '_')}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  → {dest}")
    return 0


def _cmd_simulate(a) -> int:
    from acdt.domains.aircraft.flightsim.study import simulation_study

    if a.fidelity == "pointmass":
        if a.jsbsim or a.layout:
            print("  nota: --jsbsim e --layout são do 6-DOF; não são corridos na massa pontual")
        try:
            from acdt.domains.aircraft.flightsim.pointmass import simulate_pointmass_mission
            out = Path(a.output or (Path("output") / (Path(a.sim or a.mission).stem + "_pm")))
            if a.sim:
                res = _size_for(a.mission, out)
                r = simulate_pointmass_mission(a.sim, out, res=res)
            else:
                r = simulate_pointmass_mission(a.mission, out)
        except ValueError as e:
            print(f"[acdt] {e}", file=sys.stderr)
            return 2
        return _print_pointmass(r)
    if not a.sim:
        print("[acdt] o 6-DOF precisa do projeto e da missão: "
              "acdt simulate <projeto.yaml> <missão.yaml> --fidelity 6dof", file=sys.stderr)
        return 2
    out = Path(a.output or (Path("output") / (Path(a.mission).stem + "_sim")))
    res = _size_for(a.mission, out)
    r = simulation_study(res, a.sim, out, layout=a.layout or "sized", jsbsim_check=a.jsbsim,
                         log=lambda m: print("  " + m))
    if r.get("name") == "tailless_lateral_test":
        return _print_tailless_sim(r)
    unit = r.get("unit", "")
    print(f"[acdt] simulação 6-DOF '{r.get('name')}': {r['total_time_min']:.1f} min, {r['total_dist_km']:.1f} km, "
          f"consumo {r['total_used_' + unit]:.3g} {unit}"
          + (f" — ABORTADA: {r['aborted']}" if r.get("aborted") else ""))
    for s_ in r["segments"]:
        k = s_.get("k_energy")
        print(f"  {s_['segment']:>10s}: {s_['t_min']:6.2f} min {s_['dist_km']:7.2f} km  n_z {s_['nz_min']:.2f}…"
              f"{s_['nz_max']:.2f}  α_max {s_['alpha_max_deg']:.1f}°" + (f"  k_energia {k:.3f}" if k else ""))
    qs = r.get("quasi_steady", {})
    if qs.get("k_energy_airborne"):
        print(f"  k_energia (em voo, 6-DOF / quase-estacionário) = {qs['k_energy_airborne']:.3f}")
    for n in r.get("notes", []):
        print(f"  nota: {n}")
    if "jsbsim" in r:
        print(f"  JSBSim: {r['jsbsim']}")
    for k, v in r["files"].items():
        print(f"  {k}: {v}")
    return 0 if not r.get("aborted") else 1


def _print_tailless_sim(r) -> int:
    lt0 = r.get("lateral_test") or {}
    print(f"[acdt] 6-DOF asa voadora sem deriva: {r.get('status', lt0.get('status'))} (caso de referência '{r.get('case')}')")
    for cn, lt in (r.get("lateral_tests") or {r.get("case"): lt0}).items():
        if lt.get("trim"):
            t = lt["trim"]
            print(f"  [{cn}] equilíbrio: α {t['alpha_deg']:.1f}°, δe {t['delta_e_deg']:.1f}°, manete {t['throttle']:.2f}")
        for k in ("bare", "sas"):
            if k in lt:
                p = lt[k]["peak"]
                print(f"  [{cn}] rajada lateral, {'célula nua' if k == 'bare' else 'com SAS'}: β pico {p['beta_deg']:.1f}°, "
                      f"φ pico {p['phi_deg']:.1f}°, split {p['split_deg']:.1f}°, elevon {p['elevon_deg']:.1f}°, "
                      f"|β| final {lt[k]['final_beta_amp_deg']:.3g}°")
    for cn, jc in (r.get("jsbsim_cases") or {}).items():
        nr = jc.get("nrms") or {}
        print(f"  [{cn}] JSBSim vs 6-DOF: NRMS β {nr.get('beta', float('nan')):.3f}, p {nr.get('p', float('nan')):.3f}, "
              f"r {nr.get('r', float('nan')):.3f}, φ {nr.get('phi', float('nan')):.3f}; sensibilidade própria β "
              f"{jc.get('self_sensitivity_nrms_beta', float('nan')):.3f}")
    if "jsbsim" in r and "jsbsim_cases" not in r:
        print(f"  JSBSim: {r['jsbsim']}")
    ms = r.get("mission")
    if ms:
        print(f"  missão 6-DOF (caso '{ms.get('case')}', guinada pelo split aileron): {ms.get('status')}"
              + (f" — {ms.get('aborted')}" if ms.get("aborted") else "") + (f" — {ms.get('error')}" if ms.get("error") else ""))
        for sg in ms.get("segments") or []:
            print(f"    {sg['segment']:<10s} {sg['t_min']:6.1f} min  |β|max {sg.get('beta_max_deg', float('nan')):.1f}°  "
                  f"split ΔC_n sat {sg.get('dr_sat_pct', float('nan')):.1f} %")
            if sg.get("type") == "takeoff" and sg.get("ground_roll_m") is not None:
                print(f"    descolagem ({sg.get('mode', 'rotation')}): corrida {sg['ground_roll_m']:.0f} m, V_LOF "
                      f"{sg.get('V_liftoff_m_s') or float('nan'):.1f} m/s, θ_LOF {sg.get('theta_LOF_deg', float('nan')):.1f}°"
                      + (f"; contactos {sg['strikes_N']}" if sg.get("strikes_N") else ""))
            td = sg.get("touchdown")
            if td:
                print(f"    toque: crab {td.get('crab_at_decrab_deg', td.get('crab_at_flare_deg')) or 0:+.1f}° → residual "
                      f"{td.get('residual_crab_deg') or 0:+.1f}°, deriva {td.get('drift_m_s') or 0:+.2f} m/s, φ {td.get('phi_td_deg') or 0:+.1f}°; "
                      f"carga lateral trem principal: para dentro {td.get('inboard_ratio', float('nan')):.2f}, para fora "
                      f"{td.get('outboard_ratio', float('nan')):.2f} do limite 14 CFR 23.485 → "
                      f"{td.get('side_load_ok')} ({td.get('side_load_status', '?')}, margem "
                      f"{td.get('side_load_margin', float('nan')):+.2f}, tol. ±{td.get('side_load_tolerance', float('nan')):.2f})"
                      + (f"; {td['issue']}" if td.get("issue") else ""))
        ac = ms.get("aft_clearance") or {}
        if ac.get("status") == "assessed":
            bp = (ac.get("options") or {}).get("tail_bumper") or {}
            print(f"    folga traseira ({ac.get('critical_point')}): mínima {ac['min_clearance_m']:.3f} m "
                  f"({ac.get('worst_phase')}), θ perto do solo {ac['theta_max_near_ground_deg']:.1f}° contra α_C "
                  f"{ac['alpha_C_compressed_deg']:.1f}° (comprimido) → {ac.get('ok')}; para-choques N_des "
                  f"{bp.get('P_des_N', float('nan')):.0f} N")
        too = ms.get("takeoff_options") or {}
        if too.get("status") == "assessed":
            print(f"    opções da corrida de descolagem: 6-DOF {too['ground_roll_6dof_m']:.0f} m contra "
                  f"{too['requirement_m']:.0f} m (ar calmo 6-DOF "
                  f"{too.get('ground_roll_6dof_still_air_m') or float('nan'):.0f} m); fecham: "
                  f"{', '.join(too.get('closing') or []) or 'nenhuma'}")
        ys = ms.get("yaw_split") or {}
        if ys:
            print(f"    split: pico ΔC_n {ys.get('peak_dCn', 0):.4f}, pico {ys.get('peak_split_deg', 0):.1f}°, taxa pico "
                  f"{ys.get('peak_rate_deg_s', 0):.0f} °/s, limite de taxa {100 * ys.get('rate_limited_fraction', 0):.2f} % do tempo")
    for n in r.get("notes", []):
        print(f"  nota: {n}")
    for k, v in r.get("files", {}).items():
        print(f"  {k}: {v}")
    return 0 if r.get("lateral_test", {}).get("status") == "assessed" else 1


def _cmd_mcp(a) -> int:
    try:
        from acdt.ai.mcp_server import main as mcp_main
    except ImportError as e:
        print(f"[acdt] pacote 'mcp' em falta ({e}): pip install 'acdt[ai]'", file=sys.stderr)
        return 2
    return mcp_main((["--http"] if a.http else []) + ["--host", a.host, "--port", str(a.port), "--path", a.path])


def _cmd_requirements(a) -> int:
    from acdt.core.pipeline import get_domain

    get_domain(a.domain)
    for k, rt in types_for(a.domain).items():
        flag = "" if rt.implemented else "  (aceite, não avaliado ainda)"
        print(f"{k:22s} [{rt.dimension}] senses={','.join(rt.senses)} stages={','.join(rt.stages)}{flag}")
        print(f"{'':22s} {rt.description}" + (f" — {rt.reference}" if rt.reference else ""))
    return 0


def _cmd_concept(a) -> int:
    """Estudo conceptual (IA): replay / report / barrier (opt-in Koopman–Washburn barrier patrol)."""
    import json
    from acdt.ai import concept as C
    from acdt.core.concept.study import Study
    if a.action == "barrier":
        kw = dict(
            barrier_length_km=a.barrier_length_km, speed_m_s=a.speed_m_s, sweep_width_km=a.sweep_width_km,
            evader_speed_m_s=a.evader_speed_m_s, crossing_window_h=a.crossing_window_h,
            corridor_width_km=a.corridor_width_km, n_on_station=a.n_on_station, endurance_h=a.endurance_h,
            turnaround_h=a.turnaround_h, distance_km=a.distance_km, airspeed_m_s=a.airspeed_m_s,
            headwind_m_s=a.headwind_m_s, reserve_h=a.reserve_h,
        )
        # drop Nones so missing → unassessed inside the primitive
        kw = {k: v for k, v in kw.items() if v is not None}
        if a.input:
            spec = json.loads(Path(a.input).read_text(encoding="utf-8"))
            # file values as base; CLI flags override when set
            for k, v in spec.items():
                if k.startswith("_"):
                    continue
                kw.setdefault(k, v)
        if "barrier_length_km" not in kw:
            print("[acdt] concept barrier: precisa de --barrier-length-km ou JSON com barrier_length_km",
                  file=sys.stderr)
            return 2
        if "n_on_station" not in kw:
            kw["n_on_station"] = 1.0
        out = C.barrier_search(**kw)
        text = json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False)
        dest = Path(a.output or "output/barrier_search.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text + "\n", encoding="utf-8")
        print(text)
        print(f"  → {dest}")
        if out.get("unassessed"):
            for u in out["unassessed"]:
                print(f"  [unassessed] {u['metric']}: {u['reason']}")
            return 3
        return 0
    if a.action == "report":
        st = Study.load(Path(a.study))
        print(f"[acdt] relatório: {st.write_report()}")
        return 0
    r = C.replay(a.study, with_sizing=a.with_sizing)
    for c in r["calls"]:
        print(f"  #{c['seq']:>3} {c['tool']:22s} {c['status']}" + (f"  {c['diff'][:3]}" if c.get("diff") else ""))
    print(f"[acdt] {r['study']}: " + ("todas as chamadas repetidas dão o mesmo resultado" if r["all_same"]
                                      else "HÁ DIFERENÇAS"))
    return 0 if r["all_same"] else 1


def _cmd_provenance(a) -> int:
    """Registo de proveniência: ``show`` (ler), ``capture`` (desta máquina, sem correr nada) e ``diff A B``."""
    import json
    from acdt.core import provenance as P

    if a.action == "show":
        print(json.dumps(P.load(a.paths[0]), indent=1, ensure_ascii=False))
        return 0
    if a.action == "capture":
        rec = P.collect(tools=_known_tools())
        txt = json.dumps(rec, indent=1, ensure_ascii=False)
        if a.output:
            Path(a.output).write_text(txt, encoding="utf-8")
            print(f"[acdt] proveniência: {a.output}")
        else:
            print(txt)
        return 0
    if len(a.paths) != 2:
        print("[acdt] provenance diff precisa de dois caminhos", file=sys.stderr)
        return 2
    r = P.compare(P.load(a.paths[0]), P.load(a.paths[1]))
    print(json.dumps(r, indent=1, ensure_ascii=False) if a.json else P.explain(r))
    return 0 if r["identicos"] else 1


def _known_tools() -> dict:
    """Executáveis visíveis nesta máquina (para ``provenance capture``; não os corre, excepto sondas de versão)."""
    import shutil
    from acdt.domains.aircraft.hifi.tools import find_exe, vsp_python
    from acdt.domains.aircraft.flightsim.jsbsim_runner import jsbsim_python

    t = {e: find_exe(e) or shutil.which(e) for e in ("avl", "xfoil", "gmsh", "SU2_CFD", "ccx", "mpirun")}
    t["openvsp_python"] = vsp_python()
    t["python (jsbsim)"] = jsbsim_python()
    return {k: v for k, v in t.items() if v}


def _cmd_verify(a) -> int:
    """Matriz de verificação de uma pasta já corrida (``acdt size … -o PASTA``) contra a missão."""
    from acdt.core.verification import STATUSES
    from acdt.domains.aircraft.verification_run import verify_output

    try:
        m = verify_output(a.mission, a.output_dir)
    except FileNotFoundError as e:
        print(f"[acdt] {e} — corra primeiro `acdt size {a.mission} -o {a.output_dir}`", file=sys.stderr)
        return 2
    cov = m["coverage"]
    print(f"[acdt] matriz de verificação: {cov['requisitos']} requisitos — "
          + ", ".join(f"{s} {cov['por_estado'][s]}" for s in STATUSES))
    for r in m["rows"]:
        if r["status"] in ("falha", "no_limite") or (a.all and r["status"] != "passa"):
            print(f"  [{r['status']}] {r['id']}: {r['text']} — {r['message'][:140]}")
    if cov["requisitos_sem_avaliador"]:
        print(f"  sem avaliador: {', '.join(cov['requisitos_sem_avaliador'])}")
    if m["tree_issues"]:
        print(f"  árvore: {'; '.join(m['tree_issues'])}")
    print(f"  ficheiros: {Path(a.output_dir) / 'verification_matrix.md'} (+ .json, .csv)")
    if a.strict:
        return 1 if any(cov["por_estado"][s] for s in ("falha", "nao_avaliado", "desconhecido")) else 0
    return 1 if cov["por_estado"]["falha"] else 0


def _cmd_uq(a) -> int:
    """Incerteza + sensibilidade (docs/INCERTEZA.md): missão com ``uncertainty:`` (ou --spec) → uq.json/uq.md."""
    from acdt.core.sensitivity.distributions import UncertaintySpecError
    from acdt.domains.aircraft.uq_run import run_uq

    ov: dict = {"n": a.n, "seed": a.seed, "method": a.method,
                "model": {"workers": a.workers, "fidelity": a.fidelity,
                          "skip_stages": a.skip_stage or None}}
    if a.sobol is not None:
        ov["sobol"] = {"n": a.sobol}
    if a.morris is not None:
        ov["morris"] = {"r": a.morris}
    if a.no_gsa:
        ov["sobol"], ov["morris"] = None, None
    out = a.output or "output/uq"
    try:
        r = run_uq(a.mission, out, uq_file=a.spec, overrides=ov, plots=not a.no_plots)
    except UncertaintySpecError as e:
        print(f"[acdt] uq: {e}", file=sys.stderr)
        return 2
    s = r["settings"]
    pr = r["propagation"]
    nf = sum(int(x["n_failed"]) for x in pr["runs"])
    print(f"[acdt] uq: {len(r['inputs'])} entradas incertas, {s['method'].upper()} N={s['n']} semente {s['seed']}"
          f", {len(pr['runs'])} ponto(s) de intervalo, {nf} amostras falhadas")
    for m, sm in pr["summaries"].items():
        if sm.get("status") == "ok" and "p5" in sm:
            f = (lambda v: f"[{v[0]:.4g}, {v[1]:.4g}]" if isinstance(v, list) else f"{v:.4g}")
            print(f"  {m}: P5 {f(sm['p5'])}  P50 {f(sm['p50'])}  P95 {f(sm['p95'])}"
                  f"{'' if sm.get('converged') else '  (não convergiu)'}")
    for rid, q in pr["requirements"].items():
        if q.get("p_passa") is not None:
            print(f"  [{q['estado_probabilistico']}] {rid}: P(passa) = {q['p_passa'] if isinstance(q['p_passa'], list) else round(q['p_passa'], 3)}")
    for kind in ("sobol", "morris"):
        if r.get(kind):
            print(f"  {kind}: {r[kind]['n_evaluations']} avaliações")
    print(f"  ficheiros: {Path(out) / 'uq.md'} (+ uq.json, verification_matrix.* com P(passa))")
    return 0


def _cmd_mdo(a) -> int:
    """MDO global de sistema (docs/MDO.md): missão com ``mdo:`` (ou --spec) → mdo.json/md, evaluations.csv, pareto.png."""
    from acdt.core.sysmdo import MDOSpecError
    from acdt.core.sysmdo.expr import ExprError
    from acdt.domains.aircraft.mdo_system import run_mdo_mission

    opts: dict = {}
    if a.seed is not None:
        opts["seed"] = a.seed
    if a.max_gen is not None:
        opts["max_gen"] = a.max_gen
    if a.pop_size is not None:
        opts["pop_size"] = a.pop_size
    ov: dict = {"strategy": a.strategy, "options": opts,
                "model": {"workers": a.workers, "fidelity": a.fidelity, "skip_stages": a.skip_stage or None}}
    out = a.output or "output/mdo"
    try:
        r = run_mdo_mission(a.mission, out, mdo_file=a.spec, overrides=ov, plots=not a.no_plots)
    except (MDOSpecError, ExprError, ValueError) as e:
        print(f"[acdt] mdo: {e}", file=sys.stderr)
        return 2
    print(f"[acdt] mdo: {r['strategy']}, {r['n_evaluations']} avaliações ({r['n_failed']} falhadas, "
          f"{r['n_feasible']} viáveis), frente com {len(r['pareto'])} projeto(s)")
    if r.get("chosen") is not None:
        e = r["evaluations"][r["chosen"]]
        print("  escolhido (" + ("joelho" if r.get("knee") else "ótimo") + f"): {e['combo'] or ''} {e['x']} → "
              + ", ".join(f"{k} = {v:.5g}" for k, v in e["objectives"].items() if v is not None))
    else:
        print("  nenhum projeto viável (ver menor violação em mdo.md)")
    print("  ficheiros: " + ", ".join(Path(f).name for f in r.get("files", [])) + f" em {out}")
    return 0 if r.get("chosen") is not None else 1


def _cmd_vv(a) -> int:
    """Biblioteca de V&V (docs/VV.md): casos de referência publicados → relatório versionado JSON + MD."""
    from acdt.core import vv

    if a.list:
        for c in sorted(vv.cases(), key=lambda c: (c.discipline, c.id)):
            print(f"  {c.id:28s} {c.discipline:15s} {c.kind:12s} {c.cost:7s} {c.title}")
        print(f"  registo {vv.REGISTRY_VERSION}, impressão digital {vv.registry_fingerprint()[:16]}")
        return 0
    try:
        rep = vv.run(ids=a.case or None, disciplines=a.discipline or None, max_cost=a.cost,
                     log=lambda s: print(s, flush=True))
    except KeyError as e:
        print(f"[acdt] {e.args[0]}", file=sys.stderr)
        return 2
    out = Path(a.output or "output/vv")
    files = vv.write(rep, out)
    c = rep["counts"]
    print(f"acdt vv: passa {c['passa']}, falha {c['falha']}, nao_avaliado {c['nao_avaliado']}, "
          f"desconhecido {c['desconhecido']} (registo {rep['registry_version']}); "
          + ", ".join(f.name for f in files) + f" em {out}")
    if c["falha"] or (a.strict and (c["desconhecido"] or c["nao_avaliado"])):
        return 1
    return 0


def _run_with_provenance(a, argv) -> int:
    """Cada subcomando corre num âmbito de proveniência: entradas = argumentos que são ficheiros existentes,
    sementes = opções ``*seed*``, saída = ``-o/--output`` (pasta → provenance.json; ficheiro → x.provenance.json),
    mais as pastas que o pipeline/hifi anotam. Os resultados não mudam."""
    from acdt.core import provenance as P

    if a.cmd in ("provenance", "mcp", "requirements", "verify"):
        return a.fn(a)
    opts = {k: v for k, v in vars(a).items() if k != "fn"}
    inputs = [v for k, v in opts.items() if isinstance(v, str) and k not in ("output", "output_json")
              and Path(v).is_file()]
    seeds = {k: v for k, v in opts.items() if "seed" in k and isinstance(v, (int, float, str, type(None)))
             and not isinstance(v, bool)}
    with P.run_scope(f"acdt {a.cmd}", argv=list(argv if argv is not None else sys.argv[1:]), inputs=inputs,
                     seeds=seeds):
        try:
            return a.fn(a)
        finally:
            for k in ("output", "output_json"):
                v = opts.get(k)
                if isinstance(v, str) and v and Path(v).exists():
                    P.note_output(v)


def main(argv=None) -> int:
    if os.name == "nt" and not sys.flags.utf8_mode:  # ficheiros md/csv com →, ≤, Δ: cp1252 falharia
        print("[acdt] aviso: defina PYTHONUTF8=1 no Windows (ver docs/DEV-SETUP-WINDOWS.md)", file=sys.stderr)
    p = argparse.ArgumentParser(prog="acdt", description="acdt — engineering design framework (domínio: aircraft)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("size", help="dimensionar a partir de um ficheiro de missão YAML")
    s.add_argument("mission")
    s.add_argument("-o", "--output")
    s.add_argument("--no-systems", action="store_true", help="não correr a seleção de sistemas")
    s.set_defaults(fn=_cmd_size)
    o = sub.add_parser("optimize", help="otimização MDO (OpenMDAO) + verificação no pipeline completo")
    o.add_argument("mission")
    o.add_argument("-o", "--output")
    o.add_argument("--objective", choices=["W0", "energy", "cost", "endurance", "range"],
                   help="por omissão: do registo de requisitos (mtow_objective/unit_cost) ou W0")
    o.add_argument("--solver", choices=["nlbgs", "newton"])
    o.set_defaults(fn=_cmd_optimize)
    h = sub.add_parser("hifi", help="Fase 4: verificação de alta fidelidade (OpenVSP, SU2, CalculiX, DLM) + calibração")
    h.add_argument("mission")
    h.add_argument("-o", "--output")
    h.add_argument("--steps", help="lista separada por vírgulas (por omissão: todos)")
    h.add_argument("--force", action="store_true", help="recorrer mesmo com resultados JSON existentes")
    h.add_argument("--max-time-min", type=float, default=45.0,
                   help="limite de tempo da guarda, em minutos (omissão 45). A RAM continua a 70 por cento da memória livre")
    h.set_defaults(fn=_cmd_hifi)
    wb = sub.add_parser("wingbox", help="Fase 5: otimização estrutural-aerodinâmica da asa (longarinas, t/c, torção)")
    wb.add_argument("mission")
    wb.add_argument("-o", "--output")
    wb.add_argument("--objective", choices=["weight", "range", "endurance", "mtow"],
                    help="por omissão: range (combustível) ou endurance (elétrico)")
    wb.add_argument("--tc", help="t/c de raiz do varrimento, separados por vírgulas (por omissão 0.10…0.18)")
    wb.add_argument("--maxiter", type=int, default=40)
    wb.add_argument("--no-fem", action="store_true", help="sem verificação FEM (casca) do ótimo")
    wb.add_argument("--hold-section", action="store_true",
                    help="fixa t/c, curvatura e torção geométrica na geometria de partida "
                         "(assumptions.structures.wingbox.hold_section)")
    wb.set_defaults(fn=_cmd_wingbox)
    w6 = sub.add_parser("wingbox6", help="Fase 6: caixão com encurvadura (reforçadores/sanduíche), nervuras e banzos "
                                         "dimensionados, viga calibrada por FEM de cascas, otimização")
    w6.add_argument("mission")
    w6.add_argument("-o", "--output")
    w6.add_argument("--objective", choices=["weight", "range", "endurance", "mtow"],
                    help="por omissão: range (combustível) ou endurance (elétrico)")
    w6.add_argument("--material", choices=["metal", "composite"], help="por omissão: o da missão")
    w6.add_argument("--maxiter", type=int, default=30)
    w6.add_argument("--phase5", help="JSON da Fase 5 para comparação (por omissão examples/output/<missão>_wingbox)")
    w6.add_argument("--no-fem", action="store_true", help="sem verificação FEM final")
    w6.add_argument("--rib-simp-mass", help="JSON/YAML opt-in: {vol, penal, nelx?} — massa SIMP no orçamento")
    w6.add_argument("--hold-section", action="store_true",
                    help="fixa t/c, curvatura e torção geométrica na geometria de partida "
                         "(assumptions.structures.wingbox.hold_section)")
    w6.set_defaults(fn=_cmd_wingbox6)

    rs = sub.add_parser("rib-simp", help="Massa SIMP da alma da nervura no orçamento (opt-in, 2-D leve)")
    rs.add_argument("--input", required=True, help="JSON/YAML: uma nervura ou {masses, ribs, vol, penal, rho_kg_m3, rho_source}")
    rs.add_argument("-o", "--output", help="JSON de saída")
    rs.set_defaults(fn=_cmd_rib_simp)
    mf = sub.add_parser("manufacture", help="Fase 7: plano de fabrico por peça, custo (bottom-up, Eastlake, DAPCA IV), "
                                            "validação e Pareto W0–custo")
    mf.add_argument("mission", help="missão YAML (ou ficheiro de configuração de fabrico com 'mission:')")
    mf.add_argument("--config", help="YAML com 'manufacturing:' (e opcional 'pareto:'); por omissão "
                                     "assumptions.manufacturing da missão")
    mf.add_argument("-o", "--output")
    mf.add_argument("--pareto", action="store_true", help="varrimento W/S × AR × opções → frente de Pareto W0–custo")
    mf.set_defaults(fn=_cmd_manufacture)
    cd = sub.add_parser("cad", help="montagem STEP da estrutura interna e desenho DXF (CadQuery num processo à parte)")
    cd.add_argument("mission")
    cd.add_argument("-o", "--output")
    cd.add_argument("--oml", help="STEP da superfície exterior (OpenVSP), incluído na montagem se existir")
    cd.set_defaults(fn=_cmd_cad)
    ig = sub.add_parser("integration", help="P1: geometria por componentes + verificação de packaging, campos de "
                                            "visão e massa/CG (JSON {assembly, items, constraints, base})")
    ig.add_argument("spec")
    ig.add_argument("-o", "--output")
    ig.add_argument("--size", action="store_true", help="P1b: avaliar também a montagem como aeronave (massas por "
                    "peça, CD0, AVL com corpos, CG, trem) com o 'flight' do JSON")
    ig.add_argument("--step", action="store_true", help="P1b: STEP facetado da montagem (CadQuery num processo à "
                    "parte)")
    ig.add_argument("--np-validation", action="store_true", help="P1b: ponto neutro AVL com/sem corpos vs "
                    "Torenbeek e limite de Munk (+ referência publicada em 'validation', se houver)")
    ig.add_argument("--rcs", action="store_true", help="P1b: malha RCS (STL, sem hélices) + verificação PO rápida")
    ig.set_defaults(fn=_cmd_integration)
    ct = sub.add_parser("controls", help="Fase 8: dimensionar ailerões/profundor/leme/flaps por requisitos (AVL)")
    ct.add_argument("mission")
    ct.add_argument("-o", "--output")
    ct.set_defaults(fn=_cmd_controls)
    sm = sub.add_parser("simulate", help="missão: massa pontual (N0/N1) ou 6-DOF (piloto automático, Dryden, rajadas)")
    sm.add_argument("mission", help="projeto YAML, ou (com --fidelity pointmass) a missão com bloco aircraft")
    sm.add_argument("sim", nargs="?", help="missão de simulação YAML (obrigatória no 6-DOF; "
                    "ver docs/tutorial-fase8-simulador.md e docs/tutorial-p3-massa-pontual.md)")
    sm.add_argument("--fidelity", choices=["pointmass", "6dof"], default="6dof",
                    help="pointmass (Anderson/Raymer, sem AVL) ou 6dof (omissão)")
    sm.add_argument("-o", "--output")
    sm.add_argument("--layout", choices=["sized", "current"], default=None,
                    help="6-DOF: superfícies dimensionadas (omissão) ou as da especificação")
    sm.add_argument("--jsbsim", action="store_true", help="6-DOF: verificação cruzada com JSBSim (processo separado)")
    sm.set_defaults(fn=_cmd_simulate)
    fo = sub.add_parser("flap-options", help="Fase 9: comparar none/plain/camber/flaperon (camber flaps como opção "
                                             "de projeto; escolhe só se justificado)")
    fo.add_argument("mission")
    fo.add_argument("-o", "--output")
    fo.add_argument("--options", help="lista separada por vírgulas (por omissão none,plain,camber,flaperon)")
    fo.add_argument("--objective", choices=["W0", "cost", "energy", "endurance", "range", "V_max", "power"])
    fo.add_argument("--sweep", help="varrimento de requisito em SI, ex. max_speed=30,34,38,42 → Pareto")
    fo.set_defaults(fn=_cmd_flap_options)
    ce = sub.add_parser("certify", help="Fase 10: base de certificação, matriz de conformidade (CSV/XLSX/MD), "
                                        "avaliação de segurança (FHA/FTA/FMEA + redundância) e SORA")
    ce.add_argument("mission")
    ce.add_argument("-o", "--output")
    ce.add_argument("--basis", choices=["cs23", "cs25", "stanag4671", "stanag4703"], help="impor a base")
    ce.add_argument("--passengers", type=int, help="nº máximo de lugares de passageiros (CS 23.2005)")
    ce.add_argument("--t-flight", type=float, help="duração média de voo [h] para P por hora de voo")
    ce.add_argument("--options", help="impor opções de redundância, ex. servo=dual,fcc=dual,backup_battery=true")
    ce.set_defaults(fn=_cmd_certify)
    sf = sub.add_parser("safety", help="Fase 10: FHA/FTA rápida de uma arquitetura-modelo (sem dimensionamento)")
    sf.add_argument("template", choices=["uas", "ga_piston", "sora"])
    sf.add_argument("--scheme", default="stanag4671", help="ac23_1309_class_I..IV | amc25_1309 | stanag4671 | "
                                                           "stanag4703")
    sf.add_argument("--t-flight", type=float, default=1.0)
    sf.add_argument("--mtow", type=float, default=150.0)
    sf.add_argument("--options", help="ex. servo=dual,fcc=triplex")
    sf.add_argument("--trade", action="store_true", help="estudo de redundância (todas as combinações)")
    sf.add_argument("--unit", help="massas/custos unitários das opções, ex. servo_kg=0.18,battery_kg=1.5")
    sf.add_argument("--baseline", help="opções já no orçamento de massas, ex. backup_battery=true")
    sf.add_argument("--input", help="sora: JSON com span_m, v_max_m_s, containment? (passo #8 opt-in)")
    sf.add_argument("-o", "--output", help="sora: JSON de saída")
    sf.add_argument("--supplier-rates", help="JSON {key: {lambda_per_h|mtbf_h, source, retrieved}}")
    sf.set_defaults(fn=_cmd_safety)
    m = sub.add_parser("mcp", help="servidor MCP para agentes de IA (Cursor, Claude, Grok Build); requer acdt[ai]")
    m.add_argument("--http", action="store_true", help="HTTP streamable em vez de stdio")
    m.add_argument("--host", default="127.0.0.1")
    m.add_argument("--port", type=int, default=8765)
    m.add_argument("--path", default="/mcp")
    m.set_defaults(fn=_cmd_mcp)
    rc = sub.add_parser("rcs", help="Fase 6: RCS de baixa fidelidade (Óptica Física) e otimização aero/RCS")
    rc.add_argument("mode", choices=["study", "stl", "validate"],
                    help="study: Pareto aero/RCS a partir de result.json ou missão YAML; stl: polar de um STL; "
                         "validate: casos canónicos")
    rc.add_argument("input", nargs="?", default="")
    rc.add_argument("-o", "--output")
    rc.add_argument("--freq", type=float, default=10.0, help="frequência [GHz] (por omissão 10)")
    rc.add_argument("--samples", type=int, default=100, help="amostras do DOE (hipercubo latino)")
    rc.add_argument("--refine", help="limites ε de RCS [dBsm] para refinamento COBYLA, separados por vírgulas")
    rc.add_argument("--el", type=float, default=0.0, help="elevação do polar STL [deg]")
    rc.add_argument("--daz", type=float, default=0.5, help="passo de azimute do polar STL [deg]")
    rc.set_defaults(fn=_cmd_rcs)




    sh = sub.add_parser("shape", help="P6 N2 leve: DOE forma OML aero/RCS/packaging (sem RANS)")
    sh.add_argument("action", choices=["study", "bounds", "packaging"])
    sh.add_argument("--result", help="study: result.json do size")
    sh.add_argument("-o", "--output", help="study: pasta de saída")
    sh.add_argument("--output-json", help="JSON CLI auxiliar")
    sh.add_argument("--samples", type=int, default=40)
    sh.add_argument("--seed", type=int, default=0)
    sh.add_argument("--payload", help="JSON {volume_l,…} ou caminho .json")
    sh.add_argument("--L", type=float, default=1.8)
    sh.add_argument("--D", type=float, default=0.22)
    sh.add_argument("--x-wing-le", dest="x_wing_le", type=float, default=0.6)
    sh.add_argument("--sensor-x", dest="sensor_x", type=float, default=0.3)
    sh.add_argument("--assembly", help="opt-in: JSON da montagem (chine/itens) em vez do result.json paramétrico")
    sh.set_defaults(fn=_cmd_shape)

    es = sub.add_parser("storage", help="Energia comum L0: capacidade combustível/bateria e volume alocado")
    es.add_argument("action", choices=["check"])
    es.add_argument("--input", required=True, help="JSON/YAML com storage e, para direct, demand")
    es.add_argument("--source-kind", choices=["direct", "jet_size", "vtol_size", "mission"], default="direct")
    es.add_argument("--result", help="JSON/YAML de resultado existente, sem voltar a simular")
    es.add_argument("--reserve-fraction", type=float, help="mission: reserva explícita relativa ao consumo, incluindo zero")
    es.add_argument("-o", "--output", help="JSON de saída")
    es.set_defaults(fn=_cmd_storage)

    fs = sub.add_parser("fleet",help="N0→N1 missão/propulsão/frota: cenários explícitos e feedback, sem ótimo global")
    fs.add_argument("action",choices=["study"])
    fs.add_argument("--input",required=True)
    fs.add_argument("-o","--output")
    fs.set_defaults(fn=_cmd_fleet_study)

    ob = sub.add_parser("onboard",help="Payload/elétrica transversal opt-in: massa, energia, extração e checks comuns")
    ob.add_argument("action",choices=["size"])
    ob.add_argument("--input",required=True,help="receita versionada JSON/YAML")
    ob.add_argument("-o","--output")
    ob.set_defaults(fn=_cmd_onboard)

    jt = sub.add_parser("jet", help="Jatos subsónicos L0: Korn, turbofan, V-n e orçamento de massa")
    jt.add_argument("action", choices=["wave-drag", "turbofan", "loads", "analyse", "check", "size", "performance", "weights"])
    jt.add_argument("--input", help="analyse/check/size/performance/weights: spec ou referência JSON/YAML")
    jt.add_argument("-o", "--output", help="JSON de saída")
    jt.add_argument("--mach", type=float)
    jt.add_argument("--cl", type=float, default=0.5)
    jt.add_argument("--thickness-ratio", type=float, default=0.12)
    jt.add_argument("--sweep", type=float, default=25.0, help="flecha a meia corda [graus]")
    jt.add_argument("--technology-factor", type=float, default=0.95)
    jt.add_argument("--altitude", type=float, default=0.0, help="ISA [m]")
    jt.add_argument("--thrust", type=float, default=120000.0, help="SLS não instalado por motor [N]")
    jt.add_argument("--installation-factor", type=float, default=0.97)
    jt.add_argument("--throttle-ratio", type=float, default=1.05)
    jt.add_argument("--tsfc-multiplier", type=float, default=1.0)
    jt.add_argument("--mass", type=float, help="massa de cálculo [kg]")
    jt.add_argument("--area", type=float, help="área alar [m²]")
    jt.add_argument("--vc", type=float, help="VC EAS [m/s], NÃO TAS")
    jt.add_argument("--cl-max", type=float, default=1.5)
    jt.add_argument("--cl-min", type=float, default=-1.0)
    jt.add_argument("--vd-ratio", type=float, default=1.25)
    jt.set_defaults(fn=_cmd_jet)

    vt = sub.add_parser("vtol", help="VTOL/eVTOL L0: pairar (quantidade de movimento), transição, arquiteturas")
    vt.add_argument("action", choices=["hover", "size", "compare"])
    vt.add_argument("-o", "--output", help="JSON de saída")
    vt.add_argument("--input", help="size/compare: spec JSON ou YAML")
    vt.add_argument("--architecture", choices=["multirotor", "lift_cruise", "tilt_rotor"])
    vt.add_argument("--architectures", help="compare: lista separada por vírgulas")
    vt.add_argument("--mass", type=float, help="hover: massa [kg]")
    vt.add_argument("--n-rotors", dest="n_rotors", type=int, default=4)
    vt.add_argument("--diameter", type=float, help="hover: diâmetro do rotor [m]")
    vt.add_argument("--disk-loading", dest="disk_loading", type=float, help="hover: carga de disco [N/m²]")
    vt.add_argument("--fm", type=float, default=0.70, help="figura de mérito (PRESSUPOSTO 0,70)")
    vt.add_argument("--altitude", type=float, default=0.0)
    vt.set_defaults(fn=_cmd_vtol)

    bm = sub.add_parser("bemt", help="BEMT leve opt-in: hélice (ciclo de sistemas) ou rotor axial (VTOL)")
    bm.add_argument("action", choices=["propeller", "rotor"])
    bm.add_argument("--input", required=True, help="JSON/YAML com geometria e polar (fonte obrigatória na tabela)")
    bm.add_argument("-o", "--output", help="JSON de saída")
    bm.set_defaults(fn=_cmd_bemt)

    md = sub.add_parser("motor-deck", help="Deck de motor Drela 2007 (opt-in; Kv, R, I0 + source)")
    md.add_argument("--input", required=True, help="JSON/YAML {deck, operating}")
    md.add_argument("-o", "--output", help="JSON de saída")
    md.set_defaults(fn=_cmd_motor_deck)

    se = sub.add_parser("sensitivity", help="P7: sensibilidade OAT / Sobol global e dicas de fidelidade")
    se.add_argument("action", choices=["from-samples", "pipeline", "sobol", "mc"])
    se.add_argument("-o", "--output", help="JSON de saída")
    se.add_argument("--input", help="from-samples: {baseline,samples}; sobol: Y_A/Y_B/Y_AB")
    se.add_argument("--mission", help="pipeline/sobol: YAML missão")
    se.add_argument("--variables", help="pipeline/sobol: JSON [{path}] ou {variables:[…]}")
    se.add_argument("--rel-step", type=float, default=0.05)
    se.add_argument("--threshold", type=float, default=0.5)
    se.add_argument("--with-systems", action="store_true")
    se.add_argument("--lowfi", action="store_true", help="usar aero.fidelity lowfi em vez de handbook")
    se.add_argument("--n", type=int, default=32, help="sobol: Saltelli N (evals=N*(k+2))")
    se.add_argument("--metric", default="W0_kg", help="sobol pipeline: métrica escalar")
    se.add_argument("--seed", type=int, default=0, help="sobol: semente MC")
    se.add_argument("--bootstrap", type=int, default=0, help="sobol: 0=point est.; >0 CIs percentis")
    se.add_argument("--conf", type=float, default=0.95, help="sobol: nível CI bootstrap")
    se.add_argument("--rel-span", type=float, default=0.10, help="sobol: ±fração se low/high omitidos")
    se.add_argument("--method", default="lhs", help="mc: lhs|mc")
    se.add_argument("--percentiles", default="5,50,95", help="mc: lista csv")
    se.set_defaults(fn=_cmd_sensitivity)

    de = sub.add_parser("decisions", help="P5: registo de decisões (porquê, fidelidade, rejeitadas, invalidação)")
    de.add_argument("action", choices=["open", "add", "check", "gate", "list", "report"])
    de.add_argument("folder", help="pasta do decisions.json")
    de.add_argument("-o", "--output", help="JSON de saída")
    de.add_argument("--title", help="open: título")
    de.add_argument("--id", help="open/add/check: id")
    de.add_argument("--input", help="add: JSON com what/why/fidelity/rejected/conditions/…")
    de.add_argument("--what", help="add: o que se decidiu")
    de.add_argument("--why", help="add: porquê")
    de.add_argument("--fidelity", help="add: N0|N1|…")
    de.add_argument("--level-gate", dest="level_gate")
    de.add_argument("--metrics", help="check: JSON {metric: number}")
    de.add_argument("--reopen", action="store_true", help="check/gate: reabrir invalidadas")
    de.add_argument("--level", help="gate: N0|N1|N2|…")
    de.add_argument("--checks", help="gate: JSON [{key, ok, message?}] ou {checks:[…]}")
    de.add_argument("--allow-empty", action="store_true",
                    help="gate: sem decisões no nível não força unassessed")
    de.add_argument("--uq", help="gate: JSON UQ MC/Sobol (summaries/gate_metrics)")
    de.add_argument("--require-uq", action="store_true",
                    help="gate: UQ em falta/unassessed → gate unassessed")
    de.add_argument("--uq-metric-use", default="p50",
                    help="gate: p50|p95|mean para preencher métricas de condição")
    de.set_defaults(fn=_cmd_decisions)

    sp = sub.add_parser("systems-p4", help="P4: arquitetura elétrica / orçamento de potência e trade de carga útil")
    sp.add_argument("action", choices=["catalog", "electrical", "payload-trade", "cost-fh", "ops-cost"])
    sp.add_argument("-o", "--output", help="JSON de saída")
    sp.add_argument("--catalog", help="YAML catálogo (payloads.yaml)")
    sp.add_argument("--architecture", help="electrical: JSON da arquitetura")
    sp.add_argument("--payloads", help="payload-trade: JSON de linhas (senão catálogo)")
    sp.add_argument("--kinds", help="payload-trade: filtro csv eo_ir,radar,...")
    sp.add_argument("--objectives", help="payload-trade: JSON {metric: min|max}")
    sp.add_argument("--constraints", help="payload-trade: JSON {metric: {min?,max?}}")
    sp.add_argument("--rate", type=float, default=0.0, help="cost-fh: kg/h ou kWh/h")
    sp.add_argument("--price", type=float, default=0.0, help="cost-fh: €/kg ou €/kWh")
    sp.add_argument("--maintenance", type=float, default=0.0)
    sp.add_argument("--other", type=float, default=0.0)
    sp.add_argument("--operating", help="ops-cost: JSON DOC (Raymer 2018 Ch. 18; eastlake/dapca opcional)")
    sp.set_defaults(fn=_cmd_systems_p4)

    mo = sub.add_parser("morph", help="P2 N1: matriz morfológica, gerar/cortar, avaliar, podar (set-based)")
    mo.add_argument("action", choices=["matrix", "generate", "evaluate", "prune"])
    mo.add_argument("-o", "--output", help="JSON de saída")
    mo.add_argument("--extra", help="matrix: JSON {dim: [opts]} a acrescentar")
    mo.add_argument("--matrix", help="generate: JSON da matriz (dimensions)")
    mo.add_argument("--dimensions", help="generate: subset csv de dimensões")
    mo.add_argument("--max-combinations", type=int, default=200)
    mo.add_argument("--architectures", help="evaluate: JSON com kept/architectures")
    mo.add_argument("--mission", help="evaluate: YAML base para size")
    mo.add_argument("--sim", help="evaluate: YAML missão ponto-massa (juiz)")
    mo.add_argument("--systems", help="evaluate: JSON {hybrid_templates, link_catalog, mission_context, operating_cost?}")
    mo.add_argument("--level", default="L0", help="evaluate: L0|L1")
    mo.add_argument("--limit", type=int, default=12)
    mo.add_argument("--rows", help="prune: JSON com rows de evaluate")
    mo.add_argument("--band", type=float, default=0.15)
    mo.add_argument("--keep", type=int, default=3)
    mo.set_defaults(fn=_cmd_morph)
    cc = sub.add_parser("concept", help="estudo conceptual: replay / report / barrier (Koopman–Washburn opt-in)")
    cc.add_argument("action", choices=["replay", "report", "barrier"])
    cc.add_argument("study", nargs="?", help="replay/report: study.json ou pasta do estudo")
    cc.add_argument("--with-sizing", action="store_true", help="repetir também size_fleet (dimensionamento)")
    cc.add_argument("--input", help="barrier: JSON com os argumentos (CLI sobrescreve)")
    cc.add_argument("-o", "--output", help="barrier: JSON de saída")
    cc.add_argument("--barrier-length-km", type=float)
    cc.add_argument("--speed-m-s", type=float)
    cc.add_argument("--sweep-width-km", type=float)
    cc.add_argument("--evader-speed-m-s", type=float)
    cc.add_argument("--crossing-window-h", type=float)
    cc.add_argument("--corridor-width-km", type=float)
    cc.add_argument("--n-on-station", type=float, default=None)
    cc.add_argument("--endurance-h", type=float)
    cc.add_argument("--turnaround-h", type=float)
    cc.add_argument("--distance-km", type=float)
    cc.add_argument("--airspeed-m-s", type=float)
    cc.add_argument("--headwind-m-s", type=float, default=None)
    cc.add_argument("--reserve-h", type=float, default=None)
    cc.set_defaults(fn=_cmd_concept)
    vf = sub.add_parser("verify", help="matriz de verificação dos requisitos (passa/falha/no_limite/nao_avaliado/"
                                       "desconhecido) a partir de uma pasta de `acdt size`; docs/REQUISITOS.md")
    vf.add_argument("mission")
    vf.add_argument("output_dir")
    vf.add_argument("--all", action="store_true", help="listar também os não avaliados e desconhecidos")
    vf.add_argument("--strict", action="store_true", help="código 1 também com nao_avaliado/desconhecido")
    vf.set_defaults(fn=_cmd_verify)
    uq = sub.add_parser("uq", help="incerteza + sensibilidade: Monte Carlo/LHS, P5/P50/P95, P(passa) por requisito, "
                                   "Sobol'/Morris; docs/INCERTEZA.md")
    uq.add_argument("mission")
    uq.add_argument("-o", "--output", help="pasta de saída (omissão output/uq)")
    uq.add_argument("--spec", help="YAML com a secção uncertainty (senão a da missão)")
    uq.add_argument("-n", type=int, help="tamanho da amostra (sobrepõe uncertainty.n)")
    uq.add_argument("--seed", type=int)
    uq.add_argument("--method", choices=["lhs", "mc"])
    uq.add_argument("--workers", type=int, help="processos em paralelo (omissão: n.º de CPUs − 1)")
    uq.add_argument("--fidelity", choices=["handbook"], help="forçar aerodinâmica handbook (mais barata)")
    uq.add_argument("--skip-stage", action="append", help="etapa a não correr (p. ex. aeroelasticity)")
    uq.add_argument("--sobol", type=int, metavar="N", help="Sobol' com N (custo N(k+2))")
    uq.add_argument("--morris", type=int, metavar="R", help="Morris com R trajetórias (custo R(k+1))")
    uq.add_argument("--no-gsa", action="store_true", help="só propagação (sem Sobol/Morris)")
    uq.add_argument("--no-plots", action="store_true")
    uq.set_defaults(fn=_cmd_uq)
    md = sub.add_parser("mdo", help="MDO global de sistema em OpenMDAO: variáveis por caminho (contínuas/discretas), "
                                    "vários objetivos, restrições do registo de requisitos, SLSQP/GA/NSGA-II/DOE/"
                                    "ε-restrição, frente de Pareto e joelho; docs/MDO.md")
    md.add_argument("mission")
    md.add_argument("-o", "--output", help="pasta de saída (omissão output/mdo)")
    md.add_argument("--spec", help="YAML com a secção mdo (senão a da missão)")
    md.add_argument("--strategy", choices=["slsqp", "epsilon", "nsga2", "ga", "doe"])
    md.add_argument("--seed", type=int)
    md.add_argument("--pop-size", type=int)
    md.add_argument("--max-gen", type=int)
    md.add_argument("--workers", type=int, help="processos em paralelo (omissão: n.º de CPUs − 1)")
    md.add_argument("--fidelity", choices=["handbook"], help="forçar aerodinâmica handbook (mais barata)")
    md.add_argument("--skip-stage", action="append", help="etapa a não correr (p. ex. aeroelasticity)")
    md.add_argument("--no-plots", action="store_true")
    md.set_defaults(fn=_cmd_mdo)
    vvp = sub.add_parser("vv", help="biblioteca de V&V: casos de referência publicados (citação, tolerância "
                                    "declarada) → relatório versionado passa/falha/nao_avaliado; docs/VV.md")
    vvp.add_argument("-o", "--output", help="pasta de saída (omissão output/vv)")
    vvp.add_argument("--cost", choices=["barato", "medio", "pesado"], default="barato",
                     help="custo máximo dos casos a correr (omissão barato = o que corre na CI)")
    vvp.add_argument("--case", action="append", help="só este caso (repetível; ignora --cost)")
    vvp.add_argument("--discipline", action="append", help="só esta disciplina (repetível)")
    vvp.add_argument("--list", action="store_true", help="listar os casos registados")
    vvp.add_argument("--strict", action="store_true", help="código 1 também com nao_avaliado/desconhecido")
    vvp.set_defaults(fn=_cmd_vv)
    r = sub.add_parser("requirements", help="listar os tipos de requisito registados")
    r.add_argument("--domain", default="aircraft")
    r.set_defaults(fn=_cmd_requirements)
    pv = sub.add_parser("provenance", help="proveniência dos resultados: show / capture / diff (porque dois "
                                           "resultados diferem: binário, SO, árvore suja, entradas, sementes)")
    pv.add_argument("action", choices=["show", "capture", "diff"])
    pv.add_argument("paths", nargs="*", help="registo, pasta de saída, ficheiro de resultado ou run.json")
    pv.add_argument("-o", "--output", help="capture: ficheiro JSON")
    pv.add_argument("--json", action="store_true", help="diff: saída JSON")
    pv.set_defaults(fn=_cmd_provenance)
    a = p.parse_args(argv)
    return _run_with_provenance(a, argv)


if __name__ == "__main__":
    sys.exit(main())
