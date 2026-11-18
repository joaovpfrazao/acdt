"""Report sections, plots and JSON for the Phase-2 stages (low-fi aero, structures, stability, performance)."""
from __future__ import annotations

import math

import numpy as np

from acdt import G0


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def phase2_dict(res) -> dict:
    d = {}
    if res.lowfi is not None:
        d["aero_lowfi"] = res.lowfi.summary()
    if res.structures is not None:
        d["structures"] = res.structures.summary()
    l1 = getattr(res, "structures_l1", None)
    if l1 is not None:
        packed = l1.to_dict()
        d.setdefault("structures", {})
        d["structures"]["masses"] = packed["masses"]
        d["structures"]["deflections"] = packed["deflections"]
    if res.structures_avl is not None:
        d["structures_avl_loading"] = res.structures_avl.summary()
    if res.avl is not None:
        a = res.avl
        d["avl_cruise_trim"] = {"alpha_deg": a.alpha_deg, "CL": a.CL, "CDi": a.CDi, "e": a.e, "Cm": a.Cm,
                                "x_ref": a.x_ref, "Xnp": a.Xnp, "derivatives": a.derivatives,
                                "controls_per_rad": a.controls, "deflections_deg": a.deflections_deg}
    if res.stability is not None:
        d["stability"] = res.stability.summary()
    if getattr(res, "weight_balance", None) is not None:
        d["weight_balance"] = res.weight_balance.summary()
    if getattr(res, "landing_gear", None) is not None:
        d["landing_gear"] = res.landing_gear.summary()
    if res.performance is not None:
        d["performance"] = res.performance.summary()
    if getattr(res, "noise", None) is not None:
        d["noise"] = res.noise
    if getattr(res, "thermal", None) is not None:
        d["thermal"] = res.thermal
    if getattr(res, "icing", None) is not None:
        d["icing"] = res.icing
    if getattr(res, "reliability", None) is not None:
        d["reliability"] = res.reliability
    if getattr(res, "series_cost", None) is not None:
        d["series_cost"] = res.series_cost
    d["verified_segment_mission"] = res.verified
    return _jsonable(d)


def avl_vs_handbook(res) -> list[dict]:
    """Side-by-side handbook vs AVL/low-fi values (Phase-2 cross-check table)."""
    from .aero.drag import oswald_raymer

    w = res.config.wing
    rows = []
    e_hb = res.spec.assumptions["aero"]["oswald"] or oswald_raymer(w.AR, w.sweep_at(0.0))
    st, a, lf = res.stability, res.avl, res.lowfi
    from .aero.lift import lift_curve_slope
    from acdt.core.atmosphere import isa
    CLa_hb = lift_curve_slope(w.AR, res.cruise_speed / isa(res.cruise_altitude).a, w.sweep_at(w.xc_max_t),
                              S_exp_over_S_ref=w.exposed_area(res.config.fuselage.max_diameter) / w.S,
                              fuselage_diameter=res.config.fuselage.max_diameter, span=w.span)
    rows.append({"grandeza": "CLα asa [/rad]", "manual": CLa_hb, "AVL / baixa fid.": (a.CLalpha if a else None),
                 "método manual": "DATCOM / Raymer Eq. 12.6", "nota": "AVL: avião completo (asa + cauda), sem fuselagem"})
    if a is not None:
        CL = a.CL
        rows.append({"grandeza": f"CDi a CL = {CL:.3f}", "manual": CL**2 / (math.pi * w.AR * e_hb),
                     "AVL / baixa fid.": a.CDi, "método manual": f"Oswald Raymer e = {e_hb:.3f}",
                     "nota": f"AVL e (Trefftz) = {a.e:.3f}; Oswald inclui arrasto viscoso dependente de CL"})
    if st is not None:
        rows.append({"grandeza": "x̄_NP [MAC]", "manual": st.xbar_np, "AVL / baixa fid.": st.xbar_np_avl,
                     "método manual": "Raymer Eq. 16.9 + Torenbeek (fuselagem)",
                     "nota": f"sem fuselagem: {st.xbar_np_no_fus:.3f} (AVL não modela a fuselagem)"})
        hb, av = st.controls.get("handbook_per_rad", {}), st.controls.get("avl_per_rad", {})
        for k, lab, ka in (("CLde", "CLδe [/rad]", "CLde"), ("Cmde", "Cmδe [/rad]", "Cmde_about_ref"),
                           ("Clda_magnitude", "|Clδa| [/rad]", "Clda_magnitude"), ("Cndr", "Cnδr [/rad]", "Cndr")):
            rows.append({"grandeza": lab, "manual": hb.get(k), "AVL / baixa fid.": av.get(ka),
                         "método manual": "Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM)", "nota":
                         "AVL: Cmδe no CG traseiro; Cnδr com convenção de sinal AVL" if k in ("Cmde", "Cndr") else ""})
    if lf is not None:
        rows += [{"grandeza": "CD0 (polar ajustada)", "manual": res.buildup.CD0, "AVL / baixa fid.": lf.CD0,
                  "método manual": "Raymer Eq. 12.24", "nota": f"perfil {lf.airfoil_source}; ajuste rms {lf.fit_rms:.1e}"},
                 {"grandeza": "e efetivo", "manual": e_hb, "AVL / baixa fid.": lf.e_eff,
                  "método manual": "Raymer Eq. 12.49", "nota": "baixa fid.: AVL e_inv × Kroo (fuselagem) + cd(cl) do perfil"},
                 {"grandeza": "cl_max do perfil", "manual": res.spec.assumptions["aero"]["clmax_airfoil"],
                  "AVL / baixa fid.": lf.clmax_airfoil, "método manual": "pressuposto do utilizador",
                  "nota": f"XFOIL/NeuralFoil a Re = {lf.clmax_Re:.2e}"}]
    return rows


def _wb_gear_section(res, out, table) -> list[str]:
    wb = getattr(res, "weight_balance", None)
    gear = getattr(res, "landing_gear", None)
    if wb is None and gear is None:
        return []
    L = ["## 12a. Peso e centragem operacional e trem de aterragem", ""]
    if wb is not None and wb.evaluated and wb.envelope is not None:
        from .weight_balance import plot_loading_diagram
        plot_loading_diagram(wb, out / "wb_loading.png", f"{res.spec.name}: carregamento")
        L += ["Peso e centragem (Raymer 2018 Sec. 15.1; Roskam Parte II Cap. 10). "
              "Os limites, quando não são dados no ficheiro, são os conceptuais: margem estática alvo atrás "
              "e, à frente, o mais à ré entre o trim no CLmax limpo e o flare com flaps.", "",
              "![carregamento](wb_loading.png)", "",
              wb.message, ""]
        rows = []
        for p in wb.envelope.points:
            mac = wb.mac_percent(p.x)
            rows.append({"carregamento": p.name, "massa [kg]": p.mass, "x_cg [m]": p.x, "x̄ [% CMA]": mac})
        L += [table(rows)]
        if wb.x_forward_m is not None or wb.x_aft_m is not None:
            L += [f"Limites a W0: dianteiro {wb.x_forward_m if wb.x_forward_m is not None else '—'} m, "
                  f"traseiro {wb.x_aft_m if wb.x_aft_m is not None else '—'} m.", ""]
        L += [f"- {n}" for n in wb.notes] + [""]
    if gear is not None:
        L += [f"**Trem ({gear.kind}).** {gear.geometry_summary}", "", gear.load_summary, ""]
        if gear.checks:
            L += [table([{"verificação": k, "ok": "sim" if ok else "não", "resultado": msg}
                         for k, ok, msg in gear.checks]), ""]
        L += [f"- {n}" for n in gear.notes] + [""]
    return L


def phase2_sections(res, out, table, f) -> list[str]:
    """Markdown for sections 10–13 (plots written to ``out``)."""
    L = []
    if res.config is None:
        return L
    from .structures import plot_vn, plot_wing_box, plot_wing_loads

    if res.lowfi is not None:
        from .aero.lowfi import plot_lowfi
        lf = res.lowfi
        plot_lowfi(lf, out / "lowfi_polar.png", f"{res.spec.name}: polar")
        L += ["## 10. Aerodinâmica de baixa fidelidade (Fase 2: XFOIL + AVL)", "", "![lowfi](lowfi_polar.png)", "",
              f"- Perfil: {lf.airfoil_source}; Re de cruzeiro {lf.cruise_Re:.3g}, cm0 = {lf.cm0:.4f}",
              f"- clmax do perfil (Re de perda {lf.clmax_Re:.3g}) = {lf.clmax_airfoil:.3f} → CLmax limpo "
              f"{res.highlift.CLmax_clean:.3f} (Raymer Eq. 12.15)",
              f"- Carga em envergadura: {lf.span_source}; e_inv = {f(lf.e_inv)}, fator de fuselagem (Kroo) "
              f"{lf.e_fuselage:.4f}",
              f"- CDp da asa (integração em faixas, CL = 0.5) = {lf.CDp_wing_at_cruise:.5f} vs termo do manual "
              f"{lf.wing_handbook_CD0:.5f}",
              f"- **Polar usada no ciclo: CD0 = {lf.CD0:.5f}, K = {lf.K:.5f} (e = {lf.e_eff:.3f})**", ""]
        L += [f"- {n}" for n in lf.notes] + [""]
    if res.avl is not None or res.stability is not None:
        L += ["### Comparação AVL / baixa fidelidade vs métodos de manual", "",
              table(avl_vs_handbook(res), ["grandeza", "manual", "AVL / baixa fid.", "método manual", "nota"])]

    sr = res.structures
    if sr is not None:
        vn = sr.vn
        plot_vn(vn, out / "vn_diagram.png", f"{res.spec.name}: V-n ({vn.regulation})")
        plot_wing_loads(sr, out / "wing_loads.png")
        plot_wing_box(sr, out / "wing_box.png")
        s = vn.summary()
        L += ["## 11. Estruturas: V-n, cargas na asa e caixão (Fase 2)", "", "![V-n](vn_diagram.png)", "",
              table([{"grandeza": k, "valor": v if not isinstance(v, list) else f"{v[0]:.3f} / {v[1]:.3f}"}
                     for k, v in s.items()]),
              "Cláusulas aplicadas: " + "; ".join(vn.clauses), ""]
        L += [f"- ⚠️ {n}" for n in vn.notes]
        L += ["", f"Condição crítica de dimensionamento: {sr.condition}.", "", "![loads](wing_loads.png)", "",
              f"Raiz (limite): V = {sr.beam.shear[0]:.1f} N, M = {sr.beam.moment[0]:.1f} N·m, "
              f"T = {sr.beam.torque[0]:.1f} N·m.", "", "![box](wing_box.png)", "",
              table([{"parcela": k, "massa [kg]": v} for k, v in sr.box.masses.items()])]
        rows = [{"método": "Raymer Eq. 15.46 (estatístico)", "massa da asa [kg]": sr.wing_mass_raymer},
                {"método": f"caixão Megson/Bruhn, carga Schrenk ({sr.box.material})", "massa da asa [kg]": sr.box.mass}]
        if res.structures_avl is not None:
            rows.append({"método": "caixão Megson/Bruhn, carga AVL", "massa da asa [kg]": res.structures_avl.box.mass})
        L += ["Cross-check da massa da asa:", "", table(rows)]
        L += [f"- {n}" for n in sr.box.notes] + [""]

    l1 = getattr(res, "structures_l1", None)
    if l1 is not None:
        m, df = l1.masses, l1.deflections
        ratio = m.get("fuselage_over_raymer")
        ratio_s = f"{ratio:.2f}" if isinstance(ratio, float) else "—"
        L += ["### Viga L1: fuselagem, empenagens e torção elástica", "",
              f"Fuselagem {m.get('fuselage_kg', float('nan')):.1f} kg, Raymer Eq. 15.49 "
              f"{m.get('fuselage_raymer_kg', float('nan')):.1f} kg (razão {ratio_s}). "
              f"Estabilizador {m.get('htail_kg', float('nan')):.1f} kg, deriva {m.get('vtail_kg', float('nan')):.1f} kg. "
              f"CG estrutural {m.get('structural_cg_m') if m.get('structural_cg_m') is not None else '—'} m "
              "(não move as estações Roskam do peso e centragem).",
              f"Deflexão da cauda no caso limite {df.get('fuselage_tail_m', float('nan')) * 1000:.1f} mm; "
              f"torção da deriva {df.get('fuselage_fin_twist_deg', float('nan')):.3f}°."]
        if l1.elastic is not None:
            el = l1.elastic
            kr = f"{el.K_ratio:.4f}" if isinstance(el.K_ratio, float) and math.isfinite(el.K_ratio) else "—"
            L += [f"Correção elástica de cruzeiro: aplicada = {'sim' if el.applied else 'não'}; "
                  f"K_flex/K_rígido = {kr}; torção de ponta {el.tip_twist_deg:.3f}°; "
                  f"CLα flexível {el.CLa_flex:.3f} /rad. O CLα de manual do resultado mantém-se."]
        L += [f"- {n}" for n in l1.notes] + [""]

    st = res.stability
    if st is not None:
        from .stability import plot_cg_envelope
        plot_cg_envelope(st, out / "cg_envelope.png", f"{res.spec.name}: envelope de CG")
        L += ["## 12. Estabilidade e controlo (Fase 2: Raymer Cap. 16, Etkin & Reid, Nelson)", "",
              "![cg](cg_envelope.png)", "",
              f"- {st.placement}; ápice da asa a x = {st.x_wing_apex:.3f} m",
              f"- Ponto neutro x̄_NP = {st.xbar_np:.3f} MAC (manual), {f(st.xbar_np_avl)} (AVL); dε/dα = "
              f"{st.deps_dalpha:.3f}",
              f"- **Margem estática: {100 * st.SM_fwd:.1f} % (CG dianteiro) … {100 * st.SM_aft:.1f} % (CG traseiro)**",
              (f"- AVL, cruzeiro compensado no CG traseiro: α = {res.avl.alpha_deg:.2f}°, δe = "
               f"{res.avl.deflections_deg.get('elevator', float('nan')):.2f}°, Cnβ = {res.avl.derivatives.get('Cnb', float('nan')):.4f}, "
               f"Clβ = {res.avl.derivatives.get('Clb', float('nan')):.4f}, Cmq = {res.avl.derivatives.get('Cmq', float('nan')):.2f}"
               if res.avl is not None else "- AVL não executado"),
              f"- Coef. de volume: V_h = {st.Vh:.3f}, V_v = {st.Vv:.4f} (Raymer Table 6.4: "
              f"{f(st.Vh_class)} / {f(st.Vv_class)})", "",
              table([{"caso": c.name, "massa [kg]": c.mass, "x_cg [m]": c.x_cg, "x̄_cg [MAC]": c.xbar_cg,
                      "SM": c.SM} for c in st.cases]),
              "Compensação (trim) no CG dianteiro:", "",
              table([{"condição": k, "CL": t["CL"], "δe [°]": t["delta_e_deg"], "ok (|δe| ≤ máx.)": str(t["ok"])}
                     for k, t in st.trim.items()])]
        L += [f"- {n}" for n in st.notes] + [""]
    L += _wb_gear_section(res, out, table)

    pf = res.performance
    if pf is not None:
        from .performance import plot_climb, plot_payload_range
        plot_payload_range(pf.payload_range, out / "payload_range.png", f"{res.spec.name}: payload–alcance")
        plot_climb(pf.envelope, out / "climb_ceiling.png")
        e = pf.envelope
        L += ["## 13. Desempenho por segmentos (Fase 2: Raymer Cap. 17, Anderson)", "",
              f"Orçamento utilizável: {pf.budget_note}.", "",
              "Missão requerida (segmentos):", "", table(pf.mission_required.table()),
              f"Missão até esgotar o orçamento: **alcance {pf.mission.range_m / 1e3:.1f} km, endurance "
              f"{pf.mission.endurance_s / 3600:.2f} h**.", "", table(pf.mission.table()),
              "Requisitos vs desempenho por segmentos:", "",
              table([{**c, "ok": "✅" if c["ok"] else "❌"} for c in pf.requirement_compare]),
              "![payload-range](payload_range.png)", "", table(pf.payload_range["points"]),
              f"Nota: {pf.payload_range['note']}.", "", "![climb](climb_ceiling.png)", "",
              f"- ROC máx. ao nível do mar {e['roc_sl']:.2f} m/s; teto de serviço "
              f"{'> %.0f m' % e['h'][-1] if not math.isfinite(e['service_ceiling']) else '%.0f m' % e['service_ceiling']}; "
              f"teto absoluto {'> %.0f m' % e['h'][-1] if not math.isfinite(e['absolute_ceiling']) else '%.0f m' % e['absolute_ceiling']}",
              f"- Descolagem (Raymer 17.8): corrida {pf.takeoff['ground_roll']:.0f} m, total sobre 15 m "
              f"{pf.takeoff['total_50ft']:.0f} m (V_TO {pf.takeoff['V_TO']:.1f} m/s)",
              f"- Aterragem (Raymer 17.9): corrida {pf.landing['ground_roll']:.0f} m, total sobre 15 m "
              f"{pf.landing['total_50ft']:.0f} m (μ_travagem {pf.landing['mu_brake']:g}; aproximação γ = "
              f"{pf.landing.get('gamma_deg', 3.0):g}° — `performance.approach_angle_deg`, por omissão o máximo de "
              "5.2 % / 3° de CS/14 CFR 23.75(a)(1))", ""]
        L += [f"- {n}" for n in pf.notes] + [""]
    return L


def phase3_dict(res) -> dict:
    d = {}
    if getattr(res, "aeroelastic", None) is not None:
        d["aeroelasticity"] = res.aeroelastic.summary()
    dy = getattr(res, "dynamics", None)
    if dy:
        sc, mo = dy.get("scissor"), dy.get("modes")
        d["dynamics"] = {
            "scissor": ({k: v for k, v in sc.items() if k not in ("Sh_S", "stability_line", "control_line")}
                        if sc else None),
            "modes": ({k: v for k, v in mo.items() if k not in ("A_lon", "A_lat")} if mo else None),
            "handling_qualities": dy.get("hq"), "hq_category": dy.get("hq_category")}
    sr = res.structures
    if sr is not None and sr.box_strength is not None:
        d["wing_box_comparison_kg"] = {"strength_box": sr.box_strength.mass, "buckling_box": sr.box.mass,
                                       "raymer_15_46": sr.wing_mass_raymer}
    return _jsonable(d)


def _mode_row(name, m):
    if not m:
        return None
    return {"modo": name, "ωn [rad/s]": m.get("wn"), "ζ": m.get("zeta"),
            "período [s]": (2 * math.pi / (m["wn"] * math.sqrt(1 - m["zeta"] ** 2))
                            if m.get("wn") and m.get("zeta") is not None and 0 <= m["zeta"] < 1 else None)}


def phase3_sections(res, out, table, f) -> list[str]:
    """Markdown for the Phase-3 sections 14–16 (aeroelasticity, buckling box, scissor + dynamics + HQ)."""
    L = []
    if res.config is None:
        return L
    sr = res.structures
    if sr is not None and sr.box_strength is not None:
        b = sr.box
        L += ["## 14. Caixão da asa dimensionado à estabilidade (Fase 3: Bruhn C5/C7/C11, Farrar, Kuhn)", "",
              table([{"caixão": "resistência (Fase 2, limite inferior)", "massa [kg]": sr.box_strength.mass,
                      "/ Raymer 15.46": (sr.box_strength.mass / sr.wing_mass_raymer if sr.wing_mass_raymer else None)},
                     {"caixão": f"encurvadura (Fase 3, {b.material})", "massa [kg]": b.mass,
                      "/ Raymer 15.46": (b.mass / sr.wing_mass_raymer if sr.wing_mass_raymer else None)},
                     {"caixão": "Raymer Eq. 15.46 (asa completa, estatístico)", "massa [kg]": sr.wing_mass_raymer,
                      "/ Raymer 15.46": 1.0}]),
              "Parcelas (caixão de encurvadura):", "",
              table([{"parcela": k, "massa [kg]": v} for k, v in b.masses.items()])]
        det = b.details or {}
        if "kuhn_k" in det and det["kuhn_k"] is not None:
            k = np.asarray(det["kuhn_k"], float)
            L.append(f"- Almas Kuhn: fator de tração diagonal k máx. {np.nanmax(k):.3f} (k = 0: alma resistente ao "
                     "corte, sem tração diagonal)")
        if "stringer_pitch" in det and det["stringer_pitch"] is not None:
            p = np.asarray(det["stringer_pitch"], float)
            if np.isfinite(p).any():
                L.append(f"- Passo dos reforçadores: {np.nanmin(p) * 1e3:.0f}–{np.nanmax(p) * 1e3:.0f} mm "
                         "(encurvadura local do revestimento, k = 4)")
        L += [f"- {n}" for n in b.notes] + [""]
    ae = getattr(res, "aeroelastic", None)
    if ae is not None:
        from .aeroelasticity import plot_flutter
        try:
            plot_flutter(ae, out / "flutter_vg.png", f"{res.spec.name}: flutter binário (V-g)")
            fig = ["![flutter](flutter_vg.png)", ""]
        except Exception:  # pragma: no cover
            fig = []
        rows = []
        for k, lab, ref in (("divergence", "divergência torsional", "W&C 8.3 / Bisplinghoff 8-2 (faixas + FE)"),
                            ("reversal", "inversão do aileron", "W&C 8.4, Glauert (flap 2D)"),
                            ("flutter", "flutter binário (flexão–torção)", "W&C 11 (modos assumidos, quase-estacionário)")):
            m = ae.margins[k]
            rows.append({"fenómeno": lab, "V [m/s EAS]": m["V_eas"], "requerido 1.2 V_D": m["V_required"],
                         "margem": (f"{100 * m['margin']:+.0f} %" if math.isfinite(m["margin"]) else "sem ocorrência"),
                         "ok": "✅" if m["ok"] else "❌", "método": ref})
        a45 = ae.aeer45
        L += ["## 15. Aeroelasticidade clássica (Fase 3)", "", f"V_D = {ae.VD_eas:.1f} m/s EAS.", "", table(rows),
              f"- Frequências desacopladas: flexão {f(ae.flutter.get('f_bending_Hz'))} Hz, torção "
              f"{f(ae.flutter.get('f_torsion_Hz'))} Hz; flutter a {f(ae.flutter.get('f_F'))} Hz",
              f"- AEER-45 (fator de flexibilidade torsional da asa): F = {a45['F']:.3e} vs F_max = 200/V_D² = "
              f"{a45['F_max']:.3e} → {'OK' if a45['ok'] else 'FALHA'}"
              + ("" if a45["applicable"] else " (não aplicável — informativo)"), ""] + fig
        if ae.static:
            s = ae.static
            prow = []
            for name, pt in s["points"].items():
                for tag in ("rigid", "flex"):
                    r = pt[tag]
                    prow.append({"ponto": name, "modelo": "rígido" if tag == "rigid" else "flexível", "α [°]": r["alpha_deg"],
                                 "CL": r["CL"], "CDi": r["CDi"], "CLα [/rad]": r["CLalpha_per_rad"],
                                 "flecha ponta [m]": r["tip_deflection_m"], "torção ponta [°]": r["tip_twist_deg"]})
            L += ["### Acoplamento aero-estrutural estático (OpenAeroStruct, VLM + caixão)", "", table(prow),
                  f"- Efeito da forma deformada no arrasto induzido de cruzeiro: K_flex/K = {s['K_ratio']:.4f}"]
            if ae.flex_perf:
                fp = ae.flex_perf
                L.append(f"- Missão por segmentos: rígido {fp['rígido']['range_km']:.1f} km / "
                         f"{fp['rígido']['endurance_h']:.3f} h → flexível {fp['flexível']['range_km']:.1f} km / "
                         f"{fp['flexível']['endurance_h']:.3f} h (comparação com o resultado desacoplado da Fase 2)")
            L += [f"- {n}" for n in s.get("notes", [])]
        L += [f"- {n}" for n in ae.notes] + [""]
    dy = getattr(res, "dynamics", None)
    if dy:
        from .stability import plot_root_locus, plot_scissor
        L += ["## 16. Diagrama de tesoura, modos dinâmicos e qualidades de voo (Fase 3)", ""]
        sc = dy.get("scissor")
        if sc:
            plot_scissor(sc, out / "scissor.png", f"{res.spec.name}: diagrama de tesoura")
            L += ["![scissor](scissor.png)", "",
                  f"- S_h/S atual {sc['Sh_S_current']:.3f}; requerido {f(sc['Sh_S_required'])} (estabilidade "
                  f"{f(sc['Sh_S_stability'])}, controlo {f(sc['Sh_S_control'])}; dimensionante: {sc['binding']}) → "
                  + ("✅" if sc["ok"] else "❌") + " (Torenbeek Cap. 9)"]
            L += [f"- {n}" for n in sc.get("notes", [])] + [""]
        mo = dy.get("modes")
        if mo:
            plot_root_locus(mo, out / "root_locus.png", f"{res.spec.name}: valores próprios")
            lon, lat = mo["longitudinal"], mo.get("lateral") or {}
            rows = [r for r in (_mode_row("período curto", lon.get("short_period")), _mode_row("fugóide", lon.get("phugoid")),
                                _mode_row("rolamento holandês", lat.get("dutch_roll"))) if r]
            if lat.get("roll"):
                rows.append({"modo": "rolamento (constante de tempo)", "ωn [rad/s]": None, "ζ": None,
                             "período [s]": None, "τ / T [s]": lat["roll"]["tau_s"]})
            if lat.get("spiral"):
                sp = lat["spiral"]
                rows.append({"modo": "espiral " + ("estável" if sp.get("stable") else "instável"), "ωn [rad/s]": None,
                             "ζ": None, "período [s]": None,
                             "τ / T [s]": sp.get("T_half_s") if sp.get("stable") else sp.get("T2_s")})
            I = mo.get("inertia", {})
            L += ["![modes](root_locus.png)", "", table(rows, ["modo", "ωn [rad/s]", "ζ", "período [s]", "τ / T [s]"]),
                  f"- n/α = {f(lon.get('n_alpha'))} g/rad, CAP = {f(lon.get('CAP'))} 1/(g s²)",
                  f"- Inércias (Roskam V, soma por componentes): Ixx {f(I.get('Ixx'))}, Iyy {f(I.get('Iyy'))}, "
                  f"Izz {f(I.get('Izz'))} kg·m²"]
            L += [f"- {n}" for n in mo.get("notes", [])] + [""]
        hq = dy.get("hq")
        if hq:
            L += [f"Qualidades de voo — MIL-F-8785C, Classe I, categoria {dy.get('hq_category')} (nível exigido "
                  f"{dy.get('hq_required_level')}):", "",
                  table([{k: v for k, v in r.items() if k != "key"} for r in hq]), ""]
    return L
