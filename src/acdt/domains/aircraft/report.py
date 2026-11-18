"""Markdown report, plots and machine-readable JSON (the inter-phase data model)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import yaml

from acdt import G0, __version__
from .constraints import plot_constraint_diagram
from acdt.core.requirements import types_for

REFERENCES = """\
- Raymer, D. P., *Aircraft Design: A Conceptual Approach*, 6th ed., AIAA, 2018 (equation numbers as in the 6th ed.).
- Roskam, J., *Airplane Design*, Parts I–VIII, DARcorporation.
- Gudmundsson, S., *General Aviation Aircraft Design: Applied Methods and Procedures*, Elsevier, 2014.
- Anderson, J. D., *Aircraft Performance and Design*, McGraw-Hill, 1999.
- Torenbeek, E., *Synthesis of Subsonic Airplane Design*, Delft Univ. Press, 1982.
- USAF Stability and Control DATCOM, 1978.
- Hepperle, M., "Electric Flight – Potential and Limitations", NATO STO-MP-AVT-209, 2012.
- Niu, M. C. Y., *Airframe Structural Design*, Conmilit, 1988.
- Drela, M., "First-Order DC Electric Motor Model", MIT, 2007.
- ISO 2533:1975 Standard Atmosphere.
- Nicolai, L. M., Carichner, G. E., *Fundamentals of Aircraft and Airship Design*, Vol. I, AIAA, 2010 (Table 5.1, We = A·W0^B incl. UAV classes).
- EASA CS-23 (Amdt. 4 and earlier) / 14 CFR 23.337 (pre-Amdt. 23-64): limit manoeuvring load factors.
- IEC 60028:1925, International standard of resistance for copper (ρCu = 8890 kg/m³).
- FAA Type Certificate Data Sheet 1E10 (Lycoming O-360/IO-360 series) — engine dry mass in the C172 check.
- Drela, M., "XFOIL: An Analysis and Design System for Low Reynolds Number Airfoils", 1989; XFOIL 6.99 (GPL).
- Drela, M., Youngren, H., AVL 3.40 (Athena Vortex Lattice), MIT, 2022 (GPL).
- Sharpe, P., NeuralFoil, MIT, 2024 (fallback section polars).
- Schrenk, O., "A Simple Approximation Method for Obtaining the Spanwise Lift Distribution", NACA TM 948, 1940.
- Megson, T. H. G., *Aircraft Structures for Engineering Students*, 5th ed., 2013 (Ch. 16, 19–23).
- Bruhn, E. F., *Analysis and Design of Flight Vehicle Structures*, 1973 (Ch. A3, C5, C11).
- Etkin, B., Reid, L. D., *Dynamics of Flight: Stability and Control*, 3rd ed., Wiley, 1996.
- Nelson, R. C., *Flight Stability and Automatic Control*, 2nd ed., McGraw-Hill, 1998.
- Kroo, I., *Aircraft Design: Synthesis and Analysis*, Stanford (lift-dependent drag, fuselage span-efficiency factor).
- EASA CS-23 Amdt. 4 / 14 CFR 23.333–23.341 (flight envelope, design speeds, gust loads); 14 CFR/CS 23.65 (climb speed).
- NATO STANAG 4671 Ed. 1 (USAR), 2009: USAR.303, .333, .335, .337, .341.
- Abbott, I. H., von Doenhoff, A. E., *Theory of Wing Sections*, Dover, 1959.
"""


def _f(x, nd=3):
    if x is None:
        return "-"
    if isinstance(x, (int, float)) and not math.isfinite(x):
        return "n/a"
    return f"{x:.{nd}g}" if isinstance(x, float) else str(x)


def to_dict(res) -> dict:
    """Serializable summary of a DesignResult — the data handed to the next phase."""
    sz, dp = res.sizing, res.design_point
    d = {
        "acdt_version": __version__, "name": res.spec.name, "feasible": res.feasible,
        "requirements": [{"key": r.key, "sense": r.sense, "value_si": r.value, "raw": r.raw, "unit": r.unit,
                          "params": r.params} for r in res.spec.requirements],
        "weights": {"W0_kg": sz.W0, "We_kg": sz.We, "Wfuel_or_battery_kg": sz.Wf, "payload_kg": sz.payload,
                    "crew_kg": sz.crew, "We_W0": sz.empty_fraction, "Wf_W0": sz.fuel_fraction,
                    "battery_energy_Wh": (sz.energy_J / 3600 if sz.energy_J else None)},
        "design_point": {"W_S_N_m2": dp.ws, "W_S_kg_m2": dp.ws / G0, "metric": dp.metric, "value": dp.value,
                         "active_constraints": dp.active, "P_SL_W": res.power_sl, "T_SL_N": res.thrust_sl},
        "issues": [{"severity": i.severity, "message": i.message} for i in res.issues],
        "checks": [{"key": c.key, "ok": c.ok, "message": c.message} for c in res.checks],
        "onboard_bridge": getattr(res, "onboard_bridge", None),
        "mda_history": res.history,
        "weight_initial_source": res.weight_initial_source,
        "weight_cross_check": res.weight_cross_check,
        "weight_breakdown": (None if res.weights is None else {
            "W0_kg": res.weights.W0, "We_kg": res.weights.empty, "Nz_ultimate": res.weights.Nz,
            "groups_kg": res.weights.groups, "notes": res.weights.notes,
            "items": [vars(i) for i in res.weights.items]}),
    }
    if res.config is not None:
        d["geometry"] = {"wing": res.config.wing.summary(),
                         "fuselage": {"length_m": res.config.fuselage.length,
                                      "diameter_m": res.config.fuselage.max_diameter},
                         "htail": {"S_m2": res.config.htail.S, "arm_m": res.config.htail.arm},
                         "vtail": {"S_m2": res.config.vtail.S, "arm_m": res.config.vtail.arm},
                         "wing_box": vars(res.config.wing.box)}
        d["aero"] = {"CD0": res.polar.CD0, "K": res.polar.K, "LD_max": res.polar.LD_max,
                     "CL_alpha_per_rad": res.CLalpha, "CLmax_clean": res.highlift.CLmax_clean,
                     "CLmax_takeoff": res.highlift.CLmax_takeoff, "CLmax_landing": res.highlift.CLmax_landing,
                     "cruise_speed_m_s": res.cruise_speed, "cruise_altitude_m": res.cruise_altitude}
        el = getattr(getattr(res, "structures_l1", None), "elastic", None)
        if el is not None:
            d["aero"]["elastic_correction"] = el.to_dict()
    if res.cost is not None:
        d["cost"] = vars(res.cost)
    s = res.systems
    if s is not None:
        d["systems"] = {
            "propeller": vars(s.propeller) if s.propeller else None,
            "motor": s.motor.motor if s.motor else None, "esc": s.motor.esc if s.motor else None,
            "battery": ({k: v for k, v in vars(s.battery).items()} if s.battery else None),
            "servos": [{"surface": x.name, "hinge_moment_Nm": x.hinge_moment, "torque_req_Nm": x.torque_required,
                        "servo": x.servo["id"] if x.servo else None, "n": x.n_servos} for x in s.servos],
            "autopilot": s.autopilot, "power_avg_W": s.power_budget.average_w if s.power_budget else None,
            "masses": [{"name": m.name, "mass_kg": m.mass} for m in s.masses],
            "messages": s.messages, "closure_history": s.closure_history,
            "pinned_ok": getattr(s, "pinned_ok", True),
        }
    from .report_phase2 import phase2_dict, phase3_dict
    d.update(phase2_dict(res))
    d.update(phase3_dict(res))
    return d


def plot_polar(res, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    CL = np.linspace(0, res.highlift.CLmax_clean, 60)
    CD = res.polar.CD(CL)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 4))
    a1.plot(CD, CL)
    a1.set_xlabel("CD")
    a1.set_ylabel("CL")
    a1.set_title("Polar parabólica")
    a1.grid(alpha=.3)
    a2.plot(CL, CL / CD)
    a2.axvline(res.polar.CL_LDmax, ls="--", c="k")
    a2.set_xlabel("CL")
    a2.set_ylabel("L/D")
    a2.set_title(f"(L/D)max = {res.polar.LD_max:.1f}")
    a2.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def _table(rows: list[dict], cols: list[str] | None = None, nd=4) -> str:
    if not rows:
        return "_(vazio)_\n"
    cols = cols or list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(_f(r.get(c), nd) if not isinstance(r.get(c), str) else r.get(c)
                                      for c in cols) + " |")
    return "\n".join(out) + "\n"


def _weights_section(res) -> list[str]:
    """Weight breakdown (component build-up), its convergence and the statistical cross-check."""
    bd, sz = res.weights, res.sizing
    L = ["## 2a. Estimativa de pesos por componentes (Raymer 6th ed. Cap. 15 + sistemas)", ""]
    L += [f"Valor inicial do peso vazio: {res.weight_initial_source or '-'}.", ""]
    if bd is None:
        L += ["Método estatístico (sem build-up por componentes) — "
              "`assumptions.weights.method: statistical`.", ""]
    else:
        L += [f"Fator de carga último Nz = {bd.Nz:.2f} (1.5 × limite). Iteração: estatística → geometria → "
              "componentes → novo We → re-dimensionar, até convergir (histórico na secção 8).", "",
              _table(bd.table(), ["grupo", "item", "kg", "% W0", "método"]), ""]
        rows = [{"grupo": g, "kg": m, "% W0": 100 * m / bd.W0} for g, m in bd.groups.items()]
        rows.append({"grupo": "**peso vazio We**", "kg": bd.empty, "% W0": 100 * bd.empty / bd.W0})
        L += ["Resumo por grupo e composição de W0:", "", _table(rows + [
            {"grupo": "combustível / bateria", "kg": sz.Wf, "% W0": 100 * sz.Wf / sz.W0},
            {"grupo": "payload", "kg": sz.payload, "% W0": 100 * sz.payload / sz.W0},
            {"grupo": "tripulação", "kg": sz.crew, "% W0": 100 * sz.crew / sz.W0},
            {"grupo": "**W0**", "kg": sz.W0, "% W0": 100.0}]), ""]
        if bd.notes:
            L += ["Notas do build-up:", ""] + [f"- {n}" for n in bd.notes] + [""]
    if res.weight_cross_check:
        L += ["Cross-check estatístico (We/W0 das classes publicadas no W0 obtido; "
              "'fora' = W0 fora do intervalo da base de dados):", "",
              _table([{"classe": r["class"], "We/W0": r["We/W0"], "We [kg]": r["We_kg"],
                       "na gama": {True: "sim", False: "fora", None: "-"}[r["in_range"]],
                       "fonte": r["source"]} for r in res.weight_cross_check]), ""]
    return L


def write_report(res, outdir: str | Path) -> Path:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    spec, sz, dp = res.spec, res.sizing, res.design_point
    L = [f"# Relatório de dimensionamento — {spec.name}", "",
         f"_acdt {__version__} · Fase 1 (conceptual) + 1E (sistemas) + Fase 2 (baixa fidelidade)_", "",
         spec.description or "", ""]
    verdict = "✅ VIÁVEL" if res.feasible else "❌ INVIÁVEL / requisitos não cumpridos"
    L += [f"**Resultado:** {verdict}", ""]
    if res.verified is not None:
        L += ["**Verificação por segmentos (Fase 2):** " + ("✅ todos os requisitos de desempenho cumpridos" if
              res.verified else "⚠️ pelo menos um requisito não cumprido na missão por segmentos (ver §13)"), ""]

    L += ["## 1. Requisitos desta corrida", "",
          _table([{"requisito": r.key, "sentido": r.sense, "valor": f"{r.raw} {r.unit}".strip(),
                   "qualificadores": ", ".join(f"{k}={v:g}" for k, v in r.params.items()) or "-",
                   "estágios": ", ".join(r.type.stages),
                   "avaliado": "sim" if r.type.implemented else "não (fase futura)"} for r in spec.requirements])]
    free = [k for k in types_for("aircraft") if spec.requirements.get(k) is None]
    L += [f"Requisitos não definidos (livres / por omissão): {', '.join(free)}", ""]
    if res.issues:
        L += ["### Validação", ""] + [f"- **{i.severity}**: {i.message}" for i in res.issues] + [""]

    L += ["## 2. Peso à descolagem (Raymer Cap. 3; Hepperle 2012 para elétrico)", "",
          _table([{"grandeza": "W0 [kg]", "valor": sz.W0}, {"grandeza": "We [kg]", "valor": sz.We},
                  {"grandeza": "Combustível/bateria [kg]", "valor": sz.Wf},
                  {"grandeza": "Payload + tripulação [kg]", "valor": sz.payload + sz.crew},
                  {"grandeza": "We/W0", "valor": sz.empty_fraction},
                  {"grandeza": "Wf/W0", "valor": sz.fuel_fraction},
                  {"grandeza": "Energia bateria nominal [Wh]", "valor": sz.energy_J / 3600 if sz.energy_J else None}]),
          "Pernas da missão: " + "; ".join(f"{l.kind} {l.value:.0f} (SI) @ V={l.V:.1f} m/s, L/D={l.LD:.1f}, "
                                            f"h={l.altitude:.0f} m" for l in res.legs), ""]
    L += _weights_section(res)
    if not sz.converged:
        L += [f"**Sem convergência do peso:** {sz.message}", ""]
        (out / "report.md").write_text("\n".join(L), encoding="utf-8")
        (out / "result.json").write_text(json.dumps(to_dict(res), indent=2, default=str), encoding="utf-8")
        return out / "report.md"

    png = plot_constraint_diagram(dp, res.constraints, out / "constraint_diagram.png", f"{spec.name}")
    plot_polar(res, out / "drag_polar.png")
    unit = "W/kg" if dp.metric == "P/W" else "-"
    val = dp.value * G0 if dp.metric == "P/W" else dp.value
    L += ["## 3. Design point (diagrama de restrições)", "", "![constraint diagram](constraint_diagram.png)", "",
          f"- **W0/S = {dp.ws:.1f} N/m² ({dp.ws / G0:.2f} kg/m²)**",
          f"- **{dp.metric}_SL = {val:.4g} {unit}**" + (f" → P_SL = {res.power_sl / 1e3:.3g} kW" if res.power_sl
                                                       else f" → T_SL = {res.thrust_sl:.0f} N"),
          f"- Restrições ativas: {', '.join(dp.active)}",
          f"- Área alar S = {res.S:.3f} m²", ""]

    w = res.config.wing
    L += ["## 4. Geometria de primeira iteração", "",
          _table([{"parâmetro": k, "valor": v} for k, v in w.summary().items()]),
          f"Fuselagem: L = {res.config.fuselage.length:.2f} m, D = {res.config.fuselage.max_diameter:.3f} m. "
          f"Empenagem horizontal S = {res.config.htail.S:.3f} m², vertical S = {res.config.vtail.S:.3f} m², "
          f"braço = {res.config.htail.arm:.2f} m (coef. de volume, Raymer Eq. 6.28–6.29).", "",
          f"Caixão da asa (parametrizado na geometria, análise na Fase 2): longarinas a "
          f"{w.box.front_spar_xc:.0%}/{w.box.rear_spar_xc:.0%} c, largura na raiz {w.box.box_width(w.c_root):.3f} m.", ""]

    L += ["## 5. Aerodinâmica (Raymer Cap. 12 / DATCOM)", "", "![polar](drag_polar.png)", "",
          f"- CLα = {res.CLalpha:.3f} /rad ({res.CLalpha * math.pi / 180:.4f} /deg)",
          f"- CLmax limpo / descolagem / aterragem = {res.highlift.CLmax_clean:.2f} / "
          f"{res.highlift.CLmax_takeoff:.2f} / {res.highlift.CLmax_landing:.2f}",
          f"- CD0 = {res.polar.CD0:.5f}, K = {res.polar.K:.4f} (e = {1 / (math.pi * w.AR * res.polar.K):.3f}), "
          f"(L/D)max = {res.polar.LD_max:.2f} a CL = {res.polar.CL_LDmax:.2f}", "",
          "Decomposição do CD0 (component build-up):", "",
          _table(res.buildup.table(w.S)),
          f"D/q adicional (trem, antenas, ...): {res.buildup.misc_dq:.4f} m²; L&P: {res.buildup.lp_fraction:.0%}", ""]

    L += ["## 6. Verificações", ""]
    for c in res.checks:
        mark = "✅" if c.ok else ("❌" if c.ok is False else "➖")
        L.append(f"- {mark} `{c.key}` — {c.message}")
    L.append("")
    if res.cost is not None:
        L += ["## 7. Custo unitário (Eastlake modificado, Gudmundsson 2014 Cap. 2)", "",
              _table([{"item": k, "USD": v} for k, v in vars(res.cost).items()], nd=6)]

    L += ["## 8. Histórico do ciclo MDA (peso ↔ design point ↔ geometria ↔ arrasto)", "", _table(res.history)]

    s = res.systems
    if s is not None:
        L += ["## 9. Sistemas e eletrónica (Fase 1E)", ""]
        if s.propeller:
            p = s.propeller
            L += [f"- **Hélice**: D = {p.D:.3f} m ({p.D / 0.0254:.1f} in), rpm máx ≈ {p.rpm_max:.0f}, rpm cruzeiro ≈ "
                  f"{p.rpm_cruise:.0f} (J = {p.J_cruise}), Mach de ponta {p.tip_mach_max:.2f} — {p.note}. "
                  "Passo a escolher com dados de hélice (UIUC Propeller Data Site / APC) para o J de cruzeiro."]
        if s.motor:
            m = s.motor
            L += [f"- **Motor**: Kv alvo {m.kv_target:.0f} rpm/V, P_eixo máx {m.p_shaft_max:.0f} W, I máx {m.i_max:.1f} A "
                  f"@ {m.v_nom:.1f} V → {m.motor['id'] if m.motor else 'NENHUM'}; "
                  f"**ESC** → {m.esc['id'] if m.esc else 'NENHUM'}"]
        if s.battery:
            b = s.battery
            L += [f"- **Bateria**: {b.S}S{b.P}P de `{b.cell['id']}` ({b.cell['chemistry']}), {b.capacity_ah:.1f} Ah, "
                  f"{b.v_nom:.1f} V nom., {b.energy_nom_J / 3600:.0f} Wh, massa {b.mass:.2f} kg "
                  f"({b.specific_energy_Wh_kg:.0f} Wh/kg pack), C pico {b.c_rate_peak:.2f} "
                  f"({'OK' if b.current_ok else 'EXCEDIDO'}), dimensionada por {b.limiting}. "
                  f"Massa atribuída no sizing: {sz.Wf:.2f} kg."]
        L += ["", "Servos (momentos de charneira a V_D):", "",
              _table([{"superfície": x.name, "S_c m²": x.area, "c_c m": x.chord, "H N·m": x.hinge_moment,
                       "binário req. N·m": x.torque_required, "servo": x.servo["id"] if x.servo else "NENHUM",
                       "n": x.n_servos} for x in s.servos])]
        if s.autopilot:
            a = s.autopilot
            L += [f"- **Autopiloto**: `{a['id']}` (IMU×{a['imu']}, baro×{a['baro']}, CAN×{a['can']}, "
                  f"massa≈{a['mass']} kg) — {a.get('url', '')}",
                  f"  - rejeitados: {'; '.join(s.autopilot_rejected) or '-'}"]
        if s.power_budget:
            pb = s.power_budget
            L += ["", "Power budget:", "", _table(pb.table()),
                  f"Média {pb.average_w:.1f} W, pico {pb.peak_w:.1f} W; regulador aviónica ≥ "
                  f"{pb.regulator_rating_w('avionics'):.1f} W, servos ≥ {pb.regulator_rating_w('servo'):.1f} W.", ""]
        if s.gauges:
            L += ["Cablagem de potência (secção por corrente e queda de tensão):", "",
                  _table([{"fio": k, "AWG": g.awg, "mm²": g.area_mm2, "ΔV V": g.voltage_drop_V,
                           "ΔV %": 100 * g.drop_fraction, "governado por": g.governed_by}
                          for k, g in s.gauges.items()]),
                  "Exportado: `harness.wireviz.yml` (WireViz), `harness.dot` (Graphviz), `netlist.csv`, "
                  "`harness.net` (netlist KiCad, formato \"E\" — importar no Pcbnew).", ""]
            (out / "harness.wireviz.yml").write_text(s.harness.to_wireviz_yaml(), encoding="utf-8")
            (out / "harness.dot").write_text(s.harness.to_dot(), encoding="utf-8")
            (out / "netlist.csv").write_text(s.harness.to_csv(), encoding="utf-8")
            from acdt.core.systems.harness import kicad_netlist
            (out / "harness.net").write_text(kicad_netlist(s.harness, str(getattr(getattr(res, "spec", None), "name", "acdt"))),
                                             encoding="utf-8")
        L += ["Massas de sistemas selecionados:", "", _table([{"item": m.name, "kg": m.mass} for m in s.masses])]
        if s.closure_history:
            L += ["Fecho massa/energia sistemas → sizing:", "", _table(s.closure_history)]
        if s.messages:
            L += ["Avisos de seleção:", ""] + [f"- {m}" for m in s.messages] + [""]
        L += [s.checklist_md, ""]
        (out / "compliance_checklist.md").write_text(s.checklist_md, encoding="utf-8")

    from .report_phase2 import phase2_sections, phase3_sections
    L += phase2_sections(res, out, _table, _f)
    L += phase3_sections(res, out, _table, _f)
    L += _calibration_section(spec)

    L += ["## Pressupostos usados", "", "```yaml", yaml.safe_dump(_yaml_ready(spec.assumptions), sort_keys=False,
                                                                   allow_unicode=True).strip(), "```", "",
          "## Referências", "", REFERENCES]
    (out / "report.md").write_text("\n".join(L), encoding="utf-8")
    (out / "result.json").write_text(json.dumps(to_dict(res), indent=2, default=str), encoding="utf-8")
    return out / "report.md"


def _yaml_ready(obj):
    """PyYAML cannot represent numpy scalars. The assembly planform (taper = c_tip/c_root) is one source."""
    if isinstance(obj, dict):
        return {k: _yaml_ready(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_yaml_ready(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def _calibration_section(spec) -> list[str]:
    """Phase 4 calibration factors (L3 → L1/L2) traced in the L1/L2 report: which are applied, their values and
    their high/low-fidelity sources (hifi/calibration.py)."""
    c = (spec.assumptions or {}).get("calibration") or {}
    if not c.get("file") and not c.get("factors"):
        return []
    from .hifi import calibration as cal_mod

    L = ["## Calibração Fase 4 (L3 → L1/L2)", ""]
    applied = cal_mod.load(spec.assumptions)
    cal = {"factors": {}}
    if c.get("file"):
        try:
            cal = json.loads(Path(c["file"]).read_text(encoding="utf-8"))
            L.append(f"Ficheiro: `{c['file']}` (desenho de origem: {cal.get('design')}).")
        except OSError as ex:
            L.append(f"Ficheiro de calibração ilegível: {ex}")
    for k, v in (c.get("factors") or {}).items():
        cal["factors"][k] = (v if isinstance(v, dict) else
                             {"group": cal_mod._group_of(k), "value": v, "hifi": float("nan"), "lowfi": float("nan"),
                              "what": "valor inline (assumptions.calibration.factors)"})
    L += ["", f"Grupos aplicados: {', '.join(c.get('apply') or []) or 'nenhum (só reportados)'}.", ""]
    L += cal_mod.table_md(cal, applied) + [""]
    if applied:
        L += ["Os fatores aplicados multiplicam a saída dos métodos L1/L2 (os métodos não mudam); fora da vizinhança "
              "do desenho de origem a validade é responsabilidade do utilizador.", ""]
    return L
