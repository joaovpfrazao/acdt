"""Evidence extraction: map acdt results (the ``result.json`` dictionary of ``acdt size``) to compliance evidence.

Each evidence function returns ``{"ok": True | False | None, "value": str, "tool": str}``; ``ok=None`` means the
quantity is reported but no numeric criterion exists in the catalogued paragraph (determination-type rules).
"""
from __future__ import annotations

import json
import math

KT = 0.514444


def extract_evidence(res) -> dict:
    """Live ``DesignResult`` → the same JSON-able dictionary that ``acdt size`` writes to ``result.json``."""
    from ...domains.aircraft.report import to_dict
    return json.loads(json.dumps(to_dict(res), default=str))


def _checks(r: dict) -> dict:
    return {c["key"]: c for c in r.get("checks", []) or []}


def _ev(ok, value, tool):
    return {"ok": ok, "value": value, "tool": tool}


def _info(c):
    """Design-requirement check (customer requirement, not a regulatory criterion) → informative evidence."""
    if c is None:
        return None
    return _ev(None, c["value"] + (" [requisito do projeto: OK]" if c["ok"] else " [requisito do projeto: NÃO cumprido]"),
               c["tool"])


def _from_checks(r, keys, tool):
    ch = _checks(r)
    got = [ch[k] for k in keys if k in ch]
    if not got:
        return None
    return _ev(all(c["ok"] for c in got), "; ".join(c["message"] for c in got), tool)


def ev_cert_level(r, ctx, p):
    if ctx.uav:
        return _ev(None, f"UAV, MTOW {ctx.mtow_kg:.1f} kg", "acdt size (pesos)")
    return _ev(None, f"Nível {ctx.level} ({ctx.passengers} passageiros), {ctx.perf_level} speed; AC 23.1309 Classe "
               f"{ctx.ac23_class}", "acdt certify (base)")


def ev_wb_cg(r, ctx, p):
    w = r.get("weights", {})
    sm = _from_checks(r, ["static_margin"], "acdt size (CG/estabilidade)")
    wb = r.get("weight_balance") or {}
    parts = [f"W0 {w.get('W0_kg', 0):.1f} kg, We {w.get('We_kg', 0):.1f} kg"]
    oks = []
    if sm:
        parts.append(sm["value"])
        if sm["ok"] is not None:
            oks.append(sm["ok"])
    if wb.get("evaluated"):
        parts.append(wb.get("summary") or "")
        if wb.get("within_limits") is not None:
            oks.append(bool(wb["within_limits"]))
    ok = None if not oks else all(oks)
    return _ev(ok, "; ".join(p for p in parts if p), "acdt size (pesos, envelope de CG)")


def _gear_block(r):
    g = r.get("landing_gear") or {}
    if not g or g.get("kind") in (None, "none"):
        return None
    return g


def ev_ground_loads(r, ctx, p):
    g = _gear_block(r)
    if g is None or not g.get("load_summary"):
        return None
    return _ev(g.get("load_factor_ok"), g.get("load_summary"), "acdt size (14 CFR 23.473, Raymer Cap. 11)")


def ev_landing_gear(r, ctx, p):
    g = _gear_block(r)
    if g is None or g.get("geometry_ok") is None:
        return None
    return _ev(g.get("geometry_ok"), g.get("geometry_summary") or "", "acdt size (trem, Raymer Cap. 11)")


def ev_perf_data(r, ctx, p):
    pf = r.get("performance") or {}
    if not pf:
        return None
    return _ev(None, f"alcance {pf.get('range_km', 0):.0f} km, autonomia {pf.get('endurance_h', 0):.2f} h, "
               f"envelope e T/O/aterragem calculados", "acdt size (desempenho)")


def ev_stall_speed(r, ctx, p):
    vn = (r.get("structures") or {}).get("vn") or {}
    v = vn.get("VS1_EAS_m_s")
    if v is None:
        return None
    return _ev(None, f"VS1 = {v:.1f} m/s EAS ({v / KT:.0f} kt), CLmax limpo {r.get('aero', {}).get('CLmax_clean', 0):.2f}",
               "acdt size (aero/CLmax, V-n)")


def ev_takeoff(r, ctx, p):
    c = _from_checks(r, ["perf:takeoff_ground_roll"], "acdt size (Raymer 17.8)")
    to = (r.get("performance") or {}).get("takeoff") or {}
    if not to and not c:
        return None
    txt = f"corrida {to.get('ground_roll', 0):.0f} m, até 15 m {to.get('total_50ft', 0):.0f} m"
    if c:
        txt += " [requisito do projeto: " + ("OK]" if c["ok"] else "NÃO cumprido]")
    return _ev(None, txt, "acdt size (descolagem, Raymer 17.8)")


def ev_climb_gradient(r, ctx, p):
    to = (r.get("performance") or {}).get("takeoff") or {}
    g = to.get("gamma_climb_deg")
    if g is None:
        return None
    grad = math.tan(math.radians(g))
    if "min_gradient" in p:
        req = p["min_gradient"]
    else:
        req = p["min_gradient_low"] if (ctx.level in (1, 2) and ctx.perf_level == "low") else p["min_gradient_high"]
    return _ev(grad >= req, f"gradiente de subida após descolagem {100 * grad:.1f} % vs ≥ {100 * req:.1f} % "
               "(potência de descolagem, configuração de descolagem do modelo — verificar flaps/velocidade da regra)",
               "acdt size (segmento de subida, Raymer 17.8)")


def ev_climb_rate(r, ctx, p):
    c = _from_checks(r, ["perf:climb_rate", "perf:service_ceiling"], "acdt size (envelope)")
    if c:
        return _info(c)
    e = (r.get("performance") or {}).get("envelope") or {}
    return _ev(None, f"ROC NM {e.get('roc_sl', 0):.2f} m/s, teto {e.get('service_ceiling', 0):.0f} m", "acdt size") if e else None


def ev_landing(r, ctx, p):
    c = _from_checks(r, ["perf:landing_distance"], "acdt size (aterragem)")
    la = (r.get("performance") or {}).get("landing") or {}
    if not la and not c:
        return None
    txt = f"desde 15 m {la.get('total_50ft', 0):.0f} m, corrida {la.get('ground_roll', 0):.0f} m"
    if c:
        txt += " [requisito do projeto: " + ("OK]" if c["ok"] else "NÃO cumprido]")
    return _ev(None, txt, "acdt size (aterragem)")


def ev_controllability(r, ctx, p):
    return _from_checks(r, ["trim", "hq:scissor", "hq:roll"], "acdt size (trim, diagrama tesoura, rolamento)")


def ev_trim(r, ctx, p):
    return _from_checks(r, ["trim"], "acdt size (trim)")


def ev_static_stability(r, ctx, p):
    c = _from_checks(r, ["static_margin"], "acdt size (ponto neutro/margem estática)")
    st = r.get("stability") or {}
    if c and st.get("Vv"):
        c["value"] += f"; Vv = {st['Vv']:.3f}"
    return c


def ev_dynamic_stability(r, ctx, p):
    hq = (r.get("dynamics") or {}).get("handling_qualities") or []
    rows = {h["key"]: h for h in hq}
    keys = [k for k in ("short_period", "dutch_roll", "phugoid") if k in rows]
    if not keys:
        return None
    lv = {k: rows[k].get("nível") for k in keys}
    ok = all(v is not None and v <= 2 for v in lv.values())
    return _ev(ok, ", ".join(f"{k} nível {v}" for k, v in lv.items())
               + " (amortecido se nível ≤ 2, MIL-F-8785C; nível 2 indica qualidade degradada)",
               "acdt size (modos AVL/derivadas, MIL-F-8785C)")


def ev_vn_envelope(r, ctx, p):
    vn = (r.get("structures") or {}).get("vn") or {}
    if not vn:
        return None
    return _ev(None, f"VA {vn['VA_EAS_m_s']:.1f}, VC {vn['VC_EAS_m_s']:.1f}, VD {vn['VD_EAS_m_s']:.1f} m/s EAS; "
               f"n {vn['n_limit_pos']:.2f}/{vn['n_limit_neg']:.2f} ({vn.get('governing', '')})", "acdt size (V-n)")


def ev_span_load(r, ctx, p):
    s = r.get("structures") or {}
    if "root_moment_Nm" not in s:
        return None
    return _ev(None, f"{s.get('condition', '')}; M raiz {s['root_moment_Nm']:.0f} N·m ({s.get('load_source', '')})",
               "acdt size (cargas na envergadura)")


def _n_required(formula, mtow_kg):
    if formula == "usar337":
        return min(2.1 + 10900.0 / (mtow_kg + 4536.0), 3.8)
    if formula in ("astm_f3116", "cs25_337"):
        W = mtow_kg / 0.45359237
        n = 2.1 + 24000.0 / (W + 10000.0)
        return max(2.5, min(n, 3.8))
    return None


def ev_manoeuvre_load_factor(r, ctx, p):
    vn = (r.get("structures") or {}).get("vn") or {}
    if not vn:
        return None
    n = float(vn.get("n_manoeuvre_pos", 0))
    req = _n_required(p.get("formula"), ctx.mtow_kg)
    if req is None:
        return _ev(None, f"n manobra +{n:.2f}/{vn.get('n_manoeuvre_neg', 0):.2f} (critério definido pelo requerente)",
                   "acdt size (V-n)")
    src = {"usar337": "USAR.337", "astm_f3116": "2,1+24000/(W+10000) ≤ 3,8 (ASTM F3116 — verificar revisão)",
           "cs25_337": "CS 25.337"}[p["formula"]]
    neg_ok = True
    if p["formula"] == "usar337":
        neg_ok = abs(float(vn.get("n_manoeuvre_neg", 0))) >= 0.4 * req - 1e-9
    return _ev(n >= req - 1e-9 and neg_ok, f"n manobra +{n:.2f} vs mínimo {req:.2f} ({src})", "acdt size (V-n)")


def ev_gust_load_factor(r, ctx, p):
    vn = (r.get("structures") or {}).get("vn") or {}
    g = vn.get("n_gust_VC")
    if not g:
        return None
    return _ev(None, f"n rajada a VC {g[0]:.2f}/{g[1]:.2f} (μg {vn.get('mu_g', 0):.1f}, Kg {vn.get('Kg', 0):.3f})",
               "acdt size (V-n, rajada Pratt)")


def ev_ultimate_factor(r, ctx, p):
    vn = (r.get("structures") or {}).get("vn") or {}
    if not vn.get("n_ultimate"):
        return None
    f = vn["n_ultimate"] / vn["n_limit_pos"]
    return _ev(f >= 1.5 - 1e-6, f"n último / n limite = {f:.2f} (≥ 1,5)", "acdt size (V-n)")


def ev_structural_strength(r, ctx, p):
    s = r.get("structures") or {}
    sb = s.get("skin_buckling") or {}
    if not sb:
        return None
    return _ev(bool(sb.get("ok")), f"caixão da asa dimensionado ({s.get('box_method', '')}), massa "
               f"{(s.get('wing_box_mass_kg') or {}).get('total', float('nan')):.1f} kg; encurvadura de revestimento "
               f"{'OK' if sb.get('ok') else 'NÃO OK'} (só asa — fuselagem/empenagens por fazer)", "acdt size (caixão da asa)")


def ev_aeroelasticity(r, ctx, p):
    return _from_checks(r, ["aeroel:divergence", "aeroel:reversal", "aeroel:flutter", "aeroel:aeer45"],
                        "acdt size (aeroelasticidade: flutter binário, divergência, inversão, AEER-45)")


def ev_materials(r, ctx, p):
    s = r.get("structures") or {}
    notes = " ".join(s.get("notes") or [])
    if not notes:
        return None
    return _ev(None, "admissíveis declarados como PRESSUPOSTO/MMPDS típico nas notas estruturais — valores de projeto "
               "estatísticos (A/B-basis) por obter", "acdt size (materiais)")


def ev_glide(r, ctx, p):
    a = r.get("aero") or {}
    if not a.get("LD_max"):
        return None
    return _ev(None, f"L/D máx {a['LD_max']:.1f} → razão de planeio ≈ {a['LD_max']:.0f}:1", "acdt size (polar)")


def ev_propulsion(r, ctx, p):
    dp = r.get("design_point") or {}
    if not dp.get("P_SL_W") and not dp.get("T_SL_N"):
        return None
    txt = f"P_NM {dp['P_SL_W'] / 1000:.1f} kW" if dp.get("P_SL_W") else f"T_NM {dp['T_SL_N'] / 1000:.1f} kN"
    return _ev(None, txt + " (motor certificado/qualificado em separado)", "acdt size (ponto de projeto)")


def ev_control_surfaces(r, ctx, p):
    return _from_checks(r, ["trim", "hq:roll"], "acdt size / acdt controls (superfícies de comando)")


def ev_electrical(r, ctx, p):
    ex = r.get("_extra", {}).get("electrical")
    if ex:
        return ex
    return None


def ev_safety_assessment(r, ctx, p):
    sa = r.get("_extra", {}).get("safety")
    if not sa:
        return None
    fcs = sa.get("failure_conditions", [])
    if p.get("fcs"):                      # paragraph covers only some failure conditions
        fcs = [f for f in fcs if f["id"] in p["fcs"]]
        if not any(f.get("ok") is not None for f in fcs):
            return None                   # nothing quantified for this paragraph → stays open
    quant = [f for f in fcs if f.get("ok") is not None]
    if not quant:
        return _ev(None, "avaliação de segurança só qualitativa", "acdt safety")
    bad = [f["id"] for f in quant if not f["ok"]]
    spf = [f["id"] for f in fcs if f.get("single_point_catastrophic")]
    ok = not bad and not spf
    cc = sa.get("cumulative_catastrophic")
    if "meets" in sa and not p.get("fcs"):              # scheme-aware verdict (STANAG 4703 cumulative / 4671 AMC.1309 alternative)
        ok = bool(sa["meets"])
    txt = f"{len(quant) - len(bad)}/{len(quant)} condições de falha quantificadas cumprem o alvo ({sa.get('scheme')})"
    if bad:
        txt += f"; falham: {', '.join(bad)}"
    if spf:
        txt += f"; falha única catastrófica em: {', '.join(spf)}"
    if cc and not p.get("fcs"):
        txt += (f"; soma catastrófica {cc['P_per_fh']:.1e}/h vs {cc['target']:.1e} ({cc['ref']}): "
                + ("cumpre" if cc["ok"] else "não cumpre"))
    open_ = [f["id"] for f in fcs if f.get("ok") is None]
    if open_:
        txt += f"; sem alvo ou em aberto: {', '.join(open_)}"
    return _ev(ok, txt, "acdt safety (FHA/FTA/FMEA)")


EVIDENCE = {k[3:]: v for k, v in globals().items() if k.startswith("ev_") and callable(v)}
