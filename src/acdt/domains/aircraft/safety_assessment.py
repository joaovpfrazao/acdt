"""Aircraft-level low-fidelity safety assessment (SAE ARP4761 / ARP4754A process, simplified):
architecture from the design → FHA (failure conditions, severity, target per scheme) → FTA per failure condition
(minimal cut sets, probability per flight hour, single-failure rule) → FMEA → redundancy trade whose mass/cost
deltas feed back into W0 as design OPTIONS (selected only when they are needed to meet the targets).

Two templates (the architecture is generated from the design, overridable in the ``certification.safety`` block):

* ``ga_piston`` — classic single-engine piston GA panel (vacuum attitude/heading gyros, electric turn coordinator,
  pitot-static instruments). Failure conditions and severities for IFR Class I from FAA AC 23.1309-1E Appendix 1
  (attitude total loss catastrophic, primary attitude loss major, altitude total loss hazardous, airspeed total loss
  major, heading total loss major).
* ``uas`` — fixed-wing UAS: flight-control computer, pitch/roll/yaw servos (from the systems sizing), engine-driven
  generator + backup battery, engine. Severities per STANAG 4671 Annex A definitions (loss of control →
  catastrophic; loss of propulsion → forced landing → hazardous; loss of yaw control → major).

Failure rates: :mod:`acdt.core.safety.rates` (each with source and kind). Anything without a public rate (C2 link,
magnetic compass) makes the failure condition *open* — never a guessed number.
"""
from __future__ import annotations

import itertools
import math

from acdt.core.safety import BasicEvent, FaultTree, Gate, target
from acdt.core.safety import fmea as _fmea
from acdt.core.safety.fha import SCHEMES, SEVERITY_PT, dal
from acdt.core.safety.rates import merge_supplier_rates, rate

UAS_OPTIONS = {"servo": ("single", "dual"), "fcc": ("simplex", "dual", "triplex"), "backup_battery": (False, True)}
GA_OPTIONS = {"standby_altimeter": (False, True), "standby_attitude": (False, True)}
OPTION_PT = {"servo": "servos por eixo (superfície dividida)", "fcc": "computador de voo",
             "backup_battery": "bateria de reserva", "standby_altimeter": "altímetro de reserva",
             "standby_attitude": "indicador de atitude de reserva (elétrico)"}


# ---------------------------------------------------------------- architecture templates
def _uas(opt: dict) -> tuple[dict, list[dict]]:
    comps = {"engine": ("motor de combustão", "uav_two_stroke_engine"),
             "gen": ("gerador acionado pelo motor", "uav_generator")}
    nf = {"simplex": 1, "dual": 2, "triplex": 3}[opt["fcc"]]
    fccs = [f"fcc{i + 1}" for i in range(nf)]
    for f in fccs:
        comps[f] = (f"computador de voo {f[-1]}", "uav_flight_computer")
    if nf == 1:
        fcc = fccs[0]
    elif nf == 2:
        fcc = ("AND", fccs, "perda dos 2 FCC")
    else:
        fcc = ("KOFN", fccs, "≥2 de 3 FCC falham", 2)
    ns = 2 if opt["servo"] == "dual" else 1

    def chain(surf, label):
        out = []
        for i in range(ns):
            s, h = f"srv_{surf}{i + 1}", f"har_{surf}{i + 1}"
            comps[s] = (f"servo {label} {i + 1}", "uav_servo")
            comps[h] = (f"cablagem {label} {i + 1}", "wiring_harness")
            out.append(("OR", [s, h], f"perda canal {label} {i + 1}"))
        return out[0] if ns == 1 else ("AND", out, f"perda de {label}")

    pitch = chain("elev", "profundor")
    roll = ("AND", [chain("ailL", "aileron esq."), chain("ailR", "aileron dir.")], "perda de rolamento")
    yaw = chain("rud", "leme")
    gen = ("OR", ["gen", "engine"], "perda de geração")
    if opt["backup_battery"]:
        comps["batt"] = ("bateria de reserva", "backup_battery")
        power = ("AND", [gen, "batt"], "perda de energia elétrica")
    else:
        power = gen
    fcs = [{"id": "FC-U1", "name": "perda de controlo da aeronave", "severity": "catastrophic",
            "tree": ("OR", [fcc, pitch, roll, power], "perda de controlo")},
           {"id": "FC-U2", "name": "perda de propulsão (aterragem forçada)", "severity": "hazardous", "tree": "engine"},
           {"id": "FC-U3", "name": "perda de controlo direcional (leme)", "severity": "major", "tree": yaw},
           {"id": "FC-U4", "name": "perda da ligação C2 (comando e controlo)", "severity": "major", "tree": None,
            "open": "sem taxa de falha pública da ligação C2 — depende do rádio, do espetro e do procedimento de "
                    "perda de ligação (OSO#06); estado em aberto"}]
    return comps, fcs


def _attach_c2(comps: dict, fcs: list[dict], overrides: dict | None, supplier_report: list[dict] | None) -> None:
    """Close FC-U4 only when a sourced C2 rate is present; unsourced supplier data stays unassessed."""
    c2_ok = bool(overrides and "uav_c2_link" in overrides)
    c2_un = next((r for r in (supplier_report or []) if r.get("key") == "uav_c2_link" and r["status"] != "ok"), None)
    fc = next(f for f in fcs if f["id"] == "FC-U4")
    if c2_ok and not c2_un:
        comps["c2"] = ("ligação C2 (comando e controlo)", "uav_c2_link")
        fc["tree"] = "c2"
        fc.pop("open", None)
        fc["note"] = "taxa C2 de fornecedor com fonte e data — não é um valor inventado pelo acdt"
    elif c2_un:
        fc["open"] = ("taxa C2 de fornecedor incompleta ("
                      + ", ".join(c2_un.get("unassessed_terms") or [])
                      + ") — FC em aberto, unassessed≠pass / nunca zero silencioso")
        fc["tree"] = None


def _ga(opt: dict) -> tuple[dict, list[dict]]:
    comps = {"ai": ("indicador de atitude (vácuo)", "attitude_indicator"), "vac": ("bomba de vácuo", "vacuum_pump"),
             "tc": ("coordenador de volta (elétrico)", "turn_coordinator"),
             "alt": ("altímetro", "altimeter"), "asi": ("indicador de velocidade", "airspeed_indicator"),
             "pitot": ("tubo de pitot", "pitot_tube"), "dg": ("giro direcional (vácuo)", "directional_gyro"),
             "alt_gen": ("alternador", "alternator"), "engine": ("motor (Lycoming, ATSB)", "piston_engine_lycoming")}
    primary_att = ("OR", ["ai", "vac"], "perda da atitude primária")
    att_total = [primary_att, "tc"]
    if opt["standby_attitude"]:
        comps["sai"] = ("indicador de atitude de reserva (elétrico)", "attitude_indicator")
        att_total.append("sai")
    alt = "alt"
    if opt["standby_altimeter"]:
        comps["alt2"] = ("altímetro de reserva", "altimeter")
        alt = ("AND", ["alt", "alt2"], "perda dos 2 altímetros")
    fcs = [{"id": "FC-A1", "name": "perda total de indicação de atitude (IFR)", "severity": "catastrophic",
            "tree": ("AND", att_total, "perda total de atitude"),
            "note": "AC 23.1309-1E Apêndice 1 (IFR); o coordenador de volta conta como fonte de atitude de reserva "
                    "(PRESSUPOSTO conservador do acdt)"},
           {"id": "FC-A2", "name": "perda da atitude primária", "severity": "major", "tree": primary_att},
           {"id": "FC-A3", "name": "perda total de indicação de altitude", "severity": "hazardous", "tree": alt},
           {"id": "FC-A4", "name": "perda total de indicação de velocidade", "severity": "major",
            "tree": ("OR", ["asi", "pitot"], "perda de velocidade"),
            "note": "estático alternativo/aquecimento do pitot não modelados"},
           {"id": "FC-A5", "name": "perda total de indicação de rumo", "severity": "major", "tree": None,
            "open": "bússola magnética sem taxa de falha publicada na base de dados (NASA GARS não a lista); "
                    "giro direcional + vácuo isolados = limite superior conservador"},
           {"id": "FC-A6", "name": "perda de potência do motor (informativo — 23.2100/2405, não 1309)",
            "severity": None, "tree": "engine"}]
    return comps, fcs


TEMPLATES = {"uas": (_uas, UAS_OPTIONS), "ga_piston": (_ga, GA_OPTIONS)}


def _tree(fc: dict, comps: dict, overrides: dict | None, latent: dict | None) -> FaultTree:
    ft = FaultTree(top="TOP", name=fc["name"])
    cnt = itertools.count()

    def node(n):
        if isinstance(n, str):
            if n not in ft.events:
                name, key = comps[n]
                r = rate(key, overrides)
                ex = (latent or {}).get(n)
                ft.add_event(BasicEvent(n, name, r["lambda_per_h"], exposure_h=ex, latent=ex is not None,
                                        source=f"{key}: {r['kind']}"))
            return n
        kind, ins, label = n[0], n[1], n[2]
        gid = f"G{next(cnt)}"
        kids = [node(x) for x in ins]
        ft.add_gate(Gate(gid, kind, kids, label, k=n[3] if kind == "KOFN" else 1))
        return gid

    t = fc["tree"]
    if isinstance(t, str):
        t = ("OR", [t], fc["name"])
    root = node(t)
    ft.top = root
    return ft


def _required_mtbf(ft: FaultTree, T: float, tgt: float, comps_rate: dict) -> dict | None:
    """MTBF that the dominant (Fussell–Vesely) component type would need for P/fh ≤ target (others unchanged)."""
    imp = ft.importance(T)
    top_ev = max(imp, key=imp.get)
    key = comps_rate[top_ev]
    same = [e for e in ft.events if comps_rate[e] == key]
    base = {e: ft.events[e].rate_per_h for e in same}

    def p(f):
        for e in same:
            ft.events[e].rate_per_h = base[e] * f
        return ft.per_flight_hour(T)

    lo, hi = 1e-8, 1.0
    if p(lo) > tgt:
        p(1.0)
        allb = {e: ev.rate_per_h for e, ev in ft.events.items()}

        def pa(f):
            for e, ev in ft.events.items():
                ev.rate_per_h = allb[e] * f
            return ft.per_flight_hour(T)
        lo2, hi2 = 1e-8, 1.0
        for _ in range(80):
            mid = math.sqrt(lo2 * hi2)
            lo2, hi2 = (mid, hi2) if pa(mid) <= tgt else (lo2, mid)
        pa(1.0)
        return {"component": key, "mtbf_required_h": None,
                "note": f"inatingível só com {key}; todas as taxas da árvore teriam de baixar ×{lo2:.2g} "
                        f"(MTBF ×{1 / lo2:.3g})", "uniform_factor": lo2}
    for _ in range(80):
        mid = math.sqrt(lo * hi)
        lo, hi = (mid, hi) if p(mid) <= tgt else (lo, mid)
    p(1.0)
    lam = base[top_ev] * lo
    return {"component": key, "mtbf_required_h": 1.0 / lam, "mtbf_current_h": 1.0 / base[top_ev]}


def assess(template: str, options: dict, scheme: str, t_flight_h: float, mtow_kg: float | None = None,
           overrides: dict | None = None, latent_exposure: dict | None = None, keep_trees: bool = False,
           severity_overrides: dict | None = None, supplier_rates: dict | None = None) -> dict:
    build, space = TEMPLATES[template]
    opt = {k: v[0] for k, v in space.items()} | dict(options or {})
    comps, fcs = build(opt)
    overrides, supplier_report = merge_supplier_rates(overrides, supplier_rates)
    if template == "uas":
        _attach_c2(comps, fcs, overrides, supplier_report)
    for fc in fcs:
        if fc["id"] in (severity_overrides or {}):
            fc["note"] = (fc.get("note", "") + f" | severidade alterada pelo utilizador: {fc['severity']} → "
                          f"{severity_overrides[fc['id']]} (PRESSUPOSTO, justificar)").strip(" |")
            fc["severity"] = severity_overrides[fc["id"]]
    comps_rate = {k: v[1] for k, v in comps.items()}
    out = []
    trees = {}
    for fc in fcs:
        sev = fc["severity"]
        tgt = target(scheme, sev, mtow_kg) if sev else None
        row = {"id": fc["id"], "name": fc["name"], "severity": sev, "severity_pt": SEVERITY_PT.get(sev, "informativo"),
               "target_per_fh": tgt, "dal": dal(scheme, sev) if sev else "", "note": fc.get("note", "")}
        if fc["tree"] is None:
            row.update(P_per_fh=None, ok=None, status="em aberto", note=fc.get("open", ""), single_point_catastrophic=False)
            out.append(row)
            continue
        ft = _tree(fc, comps, overrides, latent_exposure)
        s = ft.summary(t_flight_h)
        spc = sev == "catastrophic" and bool(s["single_point_failures"])
        ok = None if tgt is None else (s["P_per_fh"] <= tgt and not spc)
        row.update(P_per_fh=s["P_per_fh"], P_flight=s["P_top"], n_cut_sets=s["n_cut_sets"], min_order=s["min_order"],
                   single_point_failures=s["single_point_failures"], single_point_catastrophic=spc,
                   cut_sets=s["cut_sets"][:8], ok=ok,
                   status={None: "sem alvo", True: "cumpre", False: "não cumpre"}[ok])
        if ok is False and s["P_per_fh"] > tgt:
            row["required"] = _required_mtbf(ft, t_flight_h, tgt, comps_rate)
        trees[fc["id"]] = ft
        out.append(row)
    res = {"template": template, "options": opt, "scheme": scheme, "scheme_ref": SCHEMES[scheme]["ref"],
           "t_flight_h": t_flight_h, "failure_conditions": out,
           "supplier_rates": supplier_report,
           "components": {k: {"name": v[0], **{x: rate(v[1], overrides)[x] for x in ("lambda_per_h", "kind", "source")},
                              "rate_key": v[1]} for k, v in comps.items()}}
    cat = [r for r in out if r["severity"] == "catastrophic" and r.get("P_per_fh") is not None]
    p_cat = sum(r["P_per_fh"] for r in cat)
    if scheme == "stanag4703" and mtow_kg:
        tc = target("stanag4703", "catastrophic", mtow_kg)
        res["cumulative_catastrophic"] = {"P_per_fh": p_cat, "target": tc, "ok": p_cat <= tc,
                                          "ref": "STANAG 4703 Annex G"}
    elif scheme == "stanag4671":
        res["cumulative_catastrophic"] = {"P_per_fh": p_cat, "target": SCHEMES[scheme]["combined_catastrophic_fallback"],
                                          "ok": p_cat <= 1e-5, "ref": "STANAG 4671 AMC.1309 (alternativa: soma ≤ 1e-5)"}
    if keep_trees:
        res["_trees"] = trees
    return res


def n_failing(a: dict) -> int:
    """Failure conditions not meeting the scheme. STANAG 4703: cumulative catastrophic target + single-failure
    rule only. STANAG 4671: catastrophic conditions may use the AMC.1309 alternative (sum ≤ 1e-5)."""
    fcs = a["failure_conditions"]
    cc = a.get("cumulative_catastrophic")
    spc = sum(1 for r in fcs if r["single_point_catastrophic"])
    if a["scheme"] == "stanag4703" and cc:
        return int(not cc["ok"]) + spc
    n = sum(1 for r in fcs if r["ok"] is False and r["severity"] != "catastrophic")
    cat_fail = [r for r in fcs if r["ok"] is False and r["severity"] == "catastrophic"]
    if a["scheme"] == "stanag4671" and cc and cc["ok"] and spc == 0:
        return n
    return n + len(cat_fail)


def meets(a: dict) -> bool:
    return n_failing(a) == 0


def option_mass(template: str, opt: dict, unit: dict, baseline: dict | None = None) -> tuple[float, float | None, list[str]]:
    """Mass and cost deltas of an option set vs the baseline (``baseline`` = options already in the design's mass
    budget, default the first value of each option). ``unit``:
    {"servo_kg", "fcc_kg", "battery_kg", "altimeter_kg", "attitude_kg", and *_cost}. Missing → not counted, listed."""
    dm, dc, missing = 0.0, 0.0, []

    def add(k, n):
        nonlocal dm, dc
        if n == 0:
            return
        if unit.get(f"{k}_kg") is None:
            missing.append(f"{k}_kg")
        else:
            dm += n * unit[f"{k}_kg"]
        if unit.get(f"{k}_cost") is None:
            missing.append(f"{k}_cost")
        else:
            dc += n * unit[f"{k}_cost"]

    _, space = TEMPLATES[template]
    b = {k: v[0] for k, v in space.items()} | dict(baseline or {})
    if template == "uas":
        n_surf = unit.get("n_servo_channels", 4)       # elevator + 2 ailerons + rudder
        ns = {"single": 0, "dual": n_surf}
        nf = {"simplex": 0, "dual": 1, "triplex": 2}
        add("servo", ns[opt["servo"]] - ns[b["servo"]])
        add("fcc", nf[opt["fcc"]] - nf[b["fcc"]])
        add("battery", int(opt["backup_battery"]) - int(b["backup_battery"]))
    else:
        add("altimeter", int(opt["standby_altimeter"]) - int(b["standby_altimeter"]))
        add("attitude", int(opt["standby_attitude"]) - int(b["standby_attitude"]))
    return dm, (dc if not any(m.endswith("_cost") for m in missing) else None), missing


def redundancy_trade(template: str, scheme: str, t_flight_h: float, mtow_kg: float, unit: dict,
                     growth: float | None = None, overrides: dict | None = None,
                     latent_exposure: dict | None = None, baseline: dict | None = None,
                     severity_overrides: dict | None = None, supplier_rates: dict | None = None) -> dict:
    """Enumerate the redundancy OPTIONS; ΔW0 ≈ growth · Δm (growth = dW0/dm_fixed from a re-sizing). The chosen
    set is the lightest one that meets every quantitative target and the single-failure rule; if none does, the
    one with the fewest failing conditions (then lightest) is reported and flagged."""
    _, space = TEMPLATES[template]
    rows = []
    for combo in itertools.product(*space.values()):
        opt = dict(zip(space.keys(), combo))
        a = assess(template, opt, scheme, t_flight_h, mtow_kg, overrides, latent_exposure,
                   severity_overrides=severity_overrides, supplier_rates=supplier_rates)
        dm, dc, missing = option_mass(template, opt, unit, baseline)
        nfail = n_failing(a)
        cc = a.get("cumulative_catastrophic")
        worst = max((r["P_per_fh"] / r["target_per_fh"] for r in a["failure_conditions"]
                     if r.get("P_per_fh") is not None and r["target_per_fh"]), default=None)
        if scheme == "stanag4703" and cc:
            worst = cc["P_per_fh"] / cc["target"]
        rows.append({"options": opt, "meets": meets(a), "n_fail": nfail, "worst_ratio": worst, "dm_kg": dm,
                     "dW0_kg": growth * dm if growth is not None else None, "dcost": dc, "missing_inputs": missing,
                     "assessment": a})
    feas = [r for r in rows if r["meets"]]
    if feas:
        best = min(feas, key=lambda r: (r["dm_kg"], _n_added(r["options"], space), r["dcost"] or 0.0))
        why = "conjunto mais leve que cumpre todos os alvos quantitativos e a regra de falha única"
    else:
        best = min(rows, key=lambda r: (r["n_fail"], _cat_ratio(r) if _cat_ratio(r) > 1 else 0.0, r["dm_kg"],
                                         _n_added(r["options"], space)))
        why = ("NENHUM conjunto de opções cumpre — escolhido o com menos condições em incumprimento; requer "
               "componentes mais fiáveis (ver MTBF requerido)")
    base = next(r for r in rows if r["options"] == {k: v[0] for k, v in space.items()} | (baseline or {}))
    return {"rows": rows, "selected": best, "baseline": base, "reason": why, "growth_dW0_dm": growth}


def _n_added(opt: dict, space: dict) -> int:
    """Number of options away from the baseline (tie-break when unit masses are missing)."""
    return sum(list(space[k]).index(v) for k, v in opt.items())


def _cat_ratio(r: dict) -> float:
    """Worst catastrophic P/target (the part redundancy options act on), rounded to 2 significant digits so that
    options with negligible benefit do not win over lighter ones."""
    v = [x["P_per_fh"] / x["target_per_fh"] for x in r["assessment"]["failure_conditions"]
         if x["severity"] == "catastrophic" and x.get("P_per_fh") is not None and x["target_per_fh"]]
    return float(f"{max(v):.2g}") if v else 0.0


def fmea_from(a: dict) -> list[dict]:
    comps = a["components"]
    contrib: dict[str, list] = {k: [] for k in comps}
    spf = set()
    for r in a["failure_conditions"]:
        for cs in r.get("cut_sets") or []:
            for e in cs["cut_set"]:
                contrib[e].append(r)
        if r.get("single_point_catastrophic"):
            spf |= set(r["single_point_failures"])
    order = ["no_effect", "minor", "major", "hazardous", "catastrophic"]
    cl = []
    for k, c in comps.items():
        fcs = list({r["id"]: r for r in contrib[k]}.values())
        sev = max((r["severity"] or "no_effect" for r in fcs), key=order.index, default="no_effect")
        cl.append(_fmea.Component(k, c["name"], c["rate_key"], c["lambda_per_h"], c["source"], c["kind"],
                                  modes=[_fmea.FailureMode("perda de função", 1.0, "perda da função do componente",
                                                           ", ".join(r["id"] for r in fcs) or "—", sev)]))
    return _fmea.fmea_rows(cl, spf)


def to_markdown(a: dict, trade: dict | None = None) -> str:
    L = [f"## Avaliação de segurança (ARP4761 simplificada) — esquema {a['scheme']}", "",
         f"Referência dos alvos: {a['scheme_ref']}. Duração de voo considerada T = {a['t_flight_h']:g} h "
         "(P/h de voo = P(T)/T).", "",
         "Opções de arquitetura: " + ", ".join(f"{OPTION_PT.get(k, k)} = {v}" for k, v in a["options"].items()), "",
         "| CF | condição de falha | severidade | alvo [/h] | P [/h] | falha única | estado |", "|---|---|---|---|---|---|---|"]
    for r in a["failure_conditions"]:
        p = f"{r['P_per_fh']:.2e}" if r.get("P_per_fh") is not None else "—"
        t = f"{r['target_per_fh']:.0e}" if r.get("target_per_fh") else "—"
        sp = ", ".join(r.get("single_point_failures") or []) or "—"
        L.append(f"| {r['id']} | {r['name']} | {r['severity_pt']} | {t} | {p} | {sp} | {r['status']} |")
    cc = a.get("cumulative_catastrophic")
    if cc:
        L += ["", f"Soma das condições catastróficas: {cc['P_per_fh']:.2e} /h vs {cc['target']:.2e} ({cc['ref']}) → "
              + ("cumpre" if cc["ok"] else "não cumpre")]
    req = [r for r in a["failure_conditions"] if r.get("required")]
    if req:
        L += ["", "MTBF requerido do componente dominante (para cumprir o alvo, restantes inalterados):"]
        for r in req:
            q = r["required"]
            v = f"{q['mtbf_required_h']:.3g} h (atual {q['mtbf_current_h']:.3g} h)" if q.get("mtbf_required_h") else q["note"]
            L.append(f"- {r['id']}: {q['component']} → {v}")
    notes = [f"- {r['id']}: {r['note']}" for r in a["failure_conditions"] if r.get("note")]
    if notes:
        L += ["", "Notas:"] + notes
    if trade:
        L += ["", "### Estudo de redundância (opções de projeto)", "",
              "| opções | Δm [kg] | ΔW0 [kg] | Δcusto | pior P/alvo | cumpre |", "|---|---|---|---|---|---|"]
        for r in sorted(trade["rows"], key=lambda r: r["dm_kg"]):
            o = ", ".join(f"{k}={v}" for k, v in r["options"].items())
            w = f"{r['dW0_kg']:.2f}" if r["dW0_kg"] is not None else "—"
            c = f"{r['dcost']:.0f}" if r["dcost"] is not None else "n/d"
            wr = f"{r['worst_ratio']:.2g}" if r["worst_ratio"] is not None else "—"
            L.append(f"| {o} | {r['dm_kg']:.2f} | {w} | {c} | {wr} | {'sim' if r['meets'] else 'não'} |")
        s = trade["selected"]
        L += ["", f"**Selecionado:** {', '.join(f'{k}={v}' for k, v in s['options'].items())} — {trade['reason']}."]
        if s["missing_inputs"]:
            L.append(f"Entradas em falta (não contabilizadas): {', '.join(sorted(set(s['missing_inputs'])))}.")
    return "\n".join(L) + "\n"


def plot_trade(trade: dict, path, title: str = "") -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for r in trade["rows"]:
        x = r["dW0_kg"] if r["dW0_kg"] is not None else r["dm_kg"]
        y = r["worst_ratio"] or 1e-3
        ax.scatter(x, y, c="#2e7d32" if r["meets"] else "#c62828", s=40, zorder=3)
        lab = "/".join({True: "+", False: "−"}.get(v, str(v)[:3]) if isinstance(v, bool) else str(v)[:3]
                       for v in r["options"].values())
        ax.annotate(lab, (x, y), fontsize=6.5,
                    xytext=(3, 3), textcoords="offset points")
    s = trade["selected"]
    ax.scatter(s["dW0_kg"] if s["dW0_kg"] is not None else s["dm_kg"], s["worst_ratio"] or 1e-3, s=180,
               facecolors="none", edgecolors="k", lw=1.5, label="selecionado", zorder=4)
    ax.axhline(1.0, color="k", ls="--", lw=0.8, label="alvo (P = alvo)")
    ax.set_yscale("log")
    ax.set_xlabel("ΔW0 [kg]" if s["dW0_kg"] is not None else "Δm [kg]")
    ax.set_ylabel("pior razão P/alvo (log)")
    ax.set_title((title or "Estudo de redundância") + "\n(" + " / ".join(OPTION_PT.get(k, k) for k in s["options"])
                 + ")", fontsize=9)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return str(path)
