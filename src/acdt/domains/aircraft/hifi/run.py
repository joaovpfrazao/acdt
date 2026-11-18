"""Phase 4 orchestrator: ``acdt hifi <mission.yaml> [-o out] [--steps ...]``.

Runs the L3 chain on the L1/L2 design and writes ``report_fase4.md`` with the HiFi vs low-fi comparison and the
calibration table. Each step writes a JSON in its folder; an existing JSON is reused (``--force`` reruns), so a
long step can be run once (or on a stronger machine) and the report regenerated. Every step is guarded by the
box-capacity estimate (:func:`tools.budget`): too-heavy cases are *written* with their command and estimate,
not run. Missing tools → the step is skipped with the reason (never a fake number)."""
from __future__ import annotations

import json
import math
import time
import traceback
from pathlib import Path

STEPS = ("geometry", "cfd2d", "gci", "wing_euler", "rans_case", "fem", "flutter", "nastran", "detailed",
         "calibration")


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _save(p: Path, d) -> dict:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1, default=float))
    return d


def run_hifi(mission, out, steps=STEPS, force: bool = False, log=print, max_time_min: float = 45.0) -> dict:
    from acdt.core.pipeline import run_pipeline
    from acdt.core.atmosphere import isa
    from . import calibration, cfd, cfd3d, fem, flutter, geometry, nastran, tools
    from ..detailed_sizing import detailed_sizing
    from ..weights_detailed import roskam_class_ii

    out = Path(out).resolve()                       # external tools run with cwd inside ``out``
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    res = run_pipeline("aircraft", str(mission))["result"]
    name = Path(mission).stem                       # file-safe stem for artefact names
    title = str(getattr(getattr(res, "spec", None), "name", name))
    R = {"name": name, "title": title, "mission": str(mission), "steps": {}}

    def step(key, path, fn):
        if key not in steps:
            R["steps"][key] = _load(path) or {"skipped": "passo não pedido nesta corrida (--steps)"}
            return R["steps"][key]
        d = None if force else _load(path)
        if d is None:
            t0 = time.time()
            log(f"[acdt hifi] {key} …")
            try:
                d = _save(path, fn())
            except Exception as ex:  # tool missing or failed: record, do not invent
                d = {"skipped": f"{type(ex).__name__}: {ex}", "trace": traceback.format_exc(limit=3)}
            d.setdefault("wall_s_step", time.time() - t0)
        R["steps"][key] = d
        return d

    g = step("geometry", out / "geometry" / "geometry.json", lambda: _geom(res, out / "geometry", name, geometry))
    step("cfd2d", out / "cfd2d" / "section_verification.json", lambda: cfd.verify_section(res, out / "cfd2d"))

    def _gci():
        # One angle, three meshes. A fourth mesh and three angles are a separate study
        # (cfd.grid_convergence); do not start that study from this default.
        lf = res.lowfi
        M = res.cruise_speed / isa(res.cruise_altitude).a
        return cfd.grid_convergence(res.config.wing.airfoil, lf.cruise_Re, 2.0, out / "gci", mach=M)
    gc = step("gci", out / "gci" / "gci.json", _gci)
    wstep = (g or {}).get("step_wing")
    wstep_abs = tools.resolve_case_path(wstep, out) if wstep else None
    step("wing_euler", out / "wing_euler" / "wing_euler.json",
         lambda: cfd3d.run_wing_euler(res, wstep_abs, out / "wing_euler", max_time_min=max_time_min)
         if wstep_abs else {"skipped": "sem STEP da asa"})
    step_abs = tools.resolve_case_path(g["step"], out) if g and g.get("step") else None
    step("rans_case", out / "rans_case" / "estimate.json",
         lambda: cfd3d.full_aircraft_rans_case(res, step_abs, out / "rans_case") if step_abs
         else {"skipped": "sem STEP"})
    fo = step("fem", out / "fem" / "fem_results.json", lambda: fem.run_box_fem(res, out / "fem"))

    def _flut():
        fl = flutter.run_flutter(res, fo, out / "flutter")
        if not math.isfinite(fl["margin"]["V_F_g003"]):     # no crossing up to 2.5 V_D: extend the sweep once
            fl = flutter.run_flutter(res, fo, out / "flutter", V_max_factor=6.0, nV=100)
            fl["note"] = "varrimento estendido até 6 V_D (sem cruzamento até 2.5 V_D)"
        flutter.plot_vgf(fl, out / "flutter" / f"{name}_vgf.png", name)
        return fl
    fl = step("flutter", out / "flutter" / "flutter_results.json",
              _flut if fo and "modes" in fo else lambda: {"skipped": "sem modos FEM"})

    def _nas():
        import numpy as np
        mesh = fem.build_box_mesh(res, (fo or {}).get("meta", {}).get("ds"))
        extra, masses, _ = fem.section_masses(res, mesh)
        VD = res.structures.vn.VD
        return {"decks": [nastran.write_sol145(res, mesh, masses, extra, out / "nastran", VD / 340.29,
                                               np.linspace(0.1 * VD, 2.5 * VD, 25), sym=s) for s in (True, False)]}
    step("nastran", out / "nastran" / "nastran.json", _nas)
    step("detailed", out / "detailed" / "detailed.json",
         lambda: {**detailed_sizing(res), "roskam_class_ii": roskam_class_ii(res)})
    sec = R["steps"].get("cfd2d") or {}
    cal = calibration.build(name, sec if "k_clmax" in sec else None, fo if fo and "tip_w_fem_m" in fo else None,
                            fl if fl and "margin" in fl else None, gc if gc and "cd" in gc else None,
                            sources={"cfd2d": tools.case_relative(out / "cfd2d", out),
                                     "fem": tools.case_relative(out / "fem", out),
                                     "flutter": tools.case_relative(out / "flutter", out),
                                     "lowfi": f"{tools.case_relative(mission, out)} (acdt size)"})
    if "calibration" in steps:
        calibration.write(cal, out / "calibration.json")
    R["calibration"] = cal
    R["report"] = str(write_report_fase4(res, R, out))
    from acdt.core import provenance  # registo ao lado dos JSON de cada passo (out/provenance.json)

    provenance.note_output(out, inputs=[mission], entry_point="run_hifi", since=t_start)
    return R


def _geom(res, out, name, geometry):
    from . import tools
    r = geometry.build_vsp(res, out, name)
    case = out.parent
    stl = tools.resolve_case_path(r["stl"], case)
    png = geometry.render_png(stl, out / f"{name}_3d.png", name)
    r["render_png"] = tools.case_relative(png, case)
    r.pop("spec", None)
    return r


def _rel(p, out) -> str:
    from . import tools
    return tools.case_relative(p, out) if p else "—"


def _f(x, fmt=".3g"):
    try:
        return format(float(x), fmt) if x is not None and math.isfinite(float(x)) else "—"
    except (TypeError, ValueError):
        return str(x)


def _tbl(rows):
    if not rows:
        return []
    keys = list(rows[0])
    return ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)] + [
        "| " + " | ".join(_f(r[k]) if isinstance(r[k], (int, float)) else str(r[k]) for k in keys) + " |"
        for r in rows]


def write_report_fase4(res, R, out) -> Path:
    from . import calibration

    S, n = R["steps"], R["name"]
    L = [f"# Fase 4 — verificação de alta fidelidade: {R.get('title', n)} (`{n}`)", "",
         "L3 verifica o desenho L1/L2 (não redimensiona). Cada número abaixo vem de um ficheiro nesta pasta; "
         "casos pesados demais para esta máquina estão escritos com estimativa e comando (secção 9).", ""]
    g = S.get("geometry") or {}
    L += ["## 1. Geometria (OpenVSP → STEP/STL)", ""]
    if "wetted" in g:
        L += _tbl([{"componente": c["component"], "Swet VSP m²": c["Swet_vsp_m2"], "Swet L0 m²": c["Swet_L0_m2"],
                    "razão": c["ratio"]} for c in g["wetted"]])
        L += ["", f"Total VSP/L0 = {_f(g['Swet_ratio'])}. {g.get('note', '')}", "",
              f"Render 3-D: `{_rel(g.get('render_png'), out)}`; STEP: `{_rel(g.get('step'), out)}` (metros).", ""]
    else:
        L += [f"não corrido: {g.get('skipped', '—')}", ""]
    s = S.get("cfd2d") or {}
    L += ["## 2. Secção: SU2 RANS-SA 2-D vs XFOIL (L1)", ""]
    if "k_clmax" in s:
        L += _tbl([{"grandeza": "cl_max (Re de perda)", "RANS": s["clmax_rans"], "XFOIL": s["clmax_xfoil"],
                    "razão/dif.": s["k_clmax"]},
                   {"grandeza": "cd @ cl 0.5 (Re cruzeiro)", "RANS": s["cd05_rans"], "XFOIL": s["cd05_xfoil"],
                    "razão/dif.": s["k_cd_profile"]},
                   {"grandeza": "cm0", "RANS": s["cm0_rans"], "XFOIL": s["cm0_xfoil"], "razão/dif.": s["d_cm0"]}])
        L += ["", f"Malha {s['mesh_cells']} células; RANS totalmente turbulento (SA) vs XFOIL com transição "
              "(cruzeiro xtr ≤ 0.10): parte da diferença em cd é física (transição), não erro de nenhum modelo. "
              "Por isso `k_cd_profile` é reportado e não é aplicado. "
              "RANS estacionário perto da perda: ±10 % em cl_max (NASA TMR).", ""]
    else:
        L += [f"não corrido: {s.get('skipped', '—')}", ""]
    gc = S.get("gci") or {}
    L += ["## 3. Convergência de malha (GCI, Celik et al. 2008)", ""]
    if "cd" in gc:
        L += _tbl([{"grandeza": k, "fina": v["f"][0], "média": v["f"][1], "grossa": v["f"][2],
                    "extrapolada": v.get("f_ext"), "ordem p": v.get("p"),
                    "GCI fina %": 100 * v["gci_fine"] if v.get("gci_fine") is not None else None,
                    "oscilatória (U %)": (f"sim ({100 * v['u_osc']:.2f})" if v.get("oscillatory") else "não"),
                    "deriva iterativa máx %": 100 * max((x or 0.0) for x in v.get("iter_drift", [0.0])),
                    "erro iterativo desprezável": "sim" if v.get("iterative_ok") else "NÃO"}
                   for k, v in gc.items() if isinstance(v, dict) and "f" in v])
        L += ["", f"Células {gc.get('cells')}; iterações por malha {gc.get('iterations', '—')}. A GCI só é válida "
              "se o erro iterativo for ≪ erro de discretização (Roache 1998; Celik et al. 2008): critério aqui "
              "deriva nos últimos 10 % das iterações < 0,1 × |f_fina − f_média|/f_fina. Convergência oscilatória: "
              "sem extrapolação de Richardson, incerteza U = ½(f_max − f_min) (Stern et al. 2001).", ""]
    else:
        L += [f"não corrido: {gc.get('skipped', '—')}", ""]
    we = S.get("wing_euler") or {}
    L += ["## 4. Asa 3-D: SU2 Euler vs AVL", ""]
    if "k_CLa" in we:
        L += [f"CLα Euler = {_f(we['CLa_euler'])} /rad vs AVL {_f(we['avl']['CLa'])} /rad → k_CLα = "
              f"{_f(we['k_CLa'])} (malha {we['mesh'].get('cells')} células, M = {_f(we['mach'])}).", ""]
        if we.get("dCL_at_alpha0") is not None and we.get("CLa_euler"):
            shift = math.degrees(we["dCL_at_alpha0"] / we["CLa_euler"])
            L += [f"CL a α = 0 está {_f(we['dCL_at_alpha0'])} acima do AVL da asa, com a mesma inclinação "
                  f"(k_CLα = {_f(we['k_CLa'])}): equivale a {shift:.2f}° de incidência (ΔCL / CLα). "
                  "AVL e o STEP usam a mesma incidência (`geometry.wing_incidence_deg`, omissão 0). "
                  "Não é a área de referência: S_ref = S/2 e um fator 2 mudaria o CL e o CLα juntos.", ""]
        if we.get("CL") and we.get("CD"):
            from ..aero.drag import oswald_raymer
            from .cfd3d import euler_drag_check
            wng = res.config.wing
            aa = res.spec.assumptions.get("aero") or {}
            e = aa.get("oswald") or oswald_raymer(wng.AR, wng.sweep_at(0.0))
            alphas = we.get("alpha") or [None] * len(we["CL"])
            rows = []
            for a, cl, cd in zip(alphas, we["CL"], we["CD"]):
                chk = euler_drag_check(cl, cd, wng.AR, e)
                rows.append({"α °": a, "CL": cl, "CD": cd, "CDi": chk["CDi"],
                             "aceite": "sim" if chk["ok"] else "não"})
            L += _tbl(rows)
            if any(r["aceite"] == "não" for r in rows):
                L += ["", "CD de Euler subsónico devia ser ≥ 0 e próximo de CL²/(π e AR) (Raymer Eq. 12.5 com "
                      "CD0 = 0; paradoxo de d'Alembert). O CD gravado é o eixo de vento do SU2 "
                      "(CFx cos α + CFz sin α), com S_ref = S/2 e `MARKER_MONITORING` só na asa. "
                      "O sinal não se troca: a integral de pressão é mesmo para a frente. Não se aplica como calibração.", ""]
            else:
                L += [""]
    else:
        L += ["não corrido: " + "; ".join(we.get("notes", []) or [we.get("skipped", "—")]), ""]
    fo = S.get("fem") or {}
    L += ["## 5. Caixão da asa: CalculiX (cascas S8R + vigas B32) vs viga Fase 3", ""]
    if "tip_w_fem_m" in fo:
        rows = [{"grandeza": "flecha de ponta (último) m", "FEM": fo["tip_w_fem_m"], "Fase 3": fo["tip_w_beam_m"]},
                {"grandeza": "torção de ponta °", "FEM": fo["tip_twist_fem_deg"], "Fase 3": fo["tip_twist_beam_deg"]},
                {"grandeza": "λ encurvadura mín. (último)", "FEM": min(fo.get("buckling_factors_ultimate") or [math.nan]),
                 "Fase 3": 1.0},
                {"grandeza": "1.ª flexão Hz", "FEM": next((f for f, t in zip(fo["frequencies_Hz"], fo["mode_types"])
                                                          if t == "bending"), None), "Fase 3": fo["strip_f_bending_Hz"]},
                {"grandeza": "1.ª torção Hz", "FEM": next((f for f, t in zip(fo["frequencies_Hz"], fo["mode_types"])
                                                          if t == "torsion"), None), "Fase 3": fo["strip_f_torsion_Hz"]}]
        L += _tbl(rows) + ["", f"{fo['nodes']} nós, {fo['shells']} cascas, {fo['beams']} vigas; {_f(fo.get('wall_s'))} s.", ""]
    else:
        L += ["não corrido: " + "; ".join(fo.get("notes", []) or [fo.get("skipped", "—")]), ""]
    fl = S.get("flutter") or {}
    L += ["## 6. Flutter: modos FEM + DLM (p-k) vs estimativa de faixas da Fase 3", ""]
    if "margin" in fl:
        m = fl["margin"]
        L += _tbl([{"caso": k, "V_F g=0 m/s EAS": fl[k]["V_F_g0"], "V_F g=0.03 m/s EAS": fl[k]["V_F_g003"],
                    "f_F Hz": fl[k].get("f_F_Hz") or math.nan} for k in ("symmetric", "antisymmetric")])
        L += ["", f"Requisito 1.2 V_D = {_f(m['V_required'])} m/s EAS ({m['basis']}); margem "
              f"{'∞ (sem flutter no varrimento)' if not math.isfinite(m['margin_g003']) else _f(100 * m['margin_g003'], '+.0f') + ' %'}"
              f" → {'OK' if m['ok'] else 'FALHA'}. Fase 3 (faixas): V_F = {_f(fl.get('strip_V_F'))} m/s. "
              f"{fl.get('note', '')}", "", f"Diagrama V-g-f: `flutter/{n}_vgf.png`.", ""]
    else:
        L += [f"não corrido: {fl.get('skipped', '—')}", ""]
    L += ["Deck Nastran SOL 145 (mesma malha/massas/DLM) em `nastran/` — lido de volta com pyNastran; "
          "não corrido (sem MSC/NX Nastran aqui).", ""]
    d = S.get("detailed") or {}
    L += ["## 7. Dimensionamento detalhado", ""]
    if "ribs" in d:
        rb, j = d["ribs"], d["root_joint"]
        L += [f"**Nervuras** (esmagamento Brazier, Niu Cap. 5): passo {_f(rb['pitch_m'])} m, {rb['n_ribs_per_side']} por "
              f"semi-asa, massa {_f(rb['mass_both_sides_kg'])} kg (Fase 3: {_f(rb['phase3_rib_mass_kg'])} kg).", ""]
        L += _tbl([{k: r[k] for k in ("y_m", "M_ult_Nm", "w_crush_N_per_m", "t_web_mm", "governed_by")}
                   for r in rb["rows"][:: max(1, len(rb["rows"]) // 6)]]) + [""]
        jj = j.get("joint") or {}
        L += [f"**Ligação à raiz** (Bruhn D1, fator de ferragem {j['fitting_factor']}): P_banzo = "
              f"{_f(j['P_cap_with_fitting_factor_N'])} N → " + (
                  f"{jj['n_bolts_per_cap']} × {jj['bolt']} (Ø {_f(jj['d_mm'])} mm) em corte duplo, MS = "
                  f"{_f(jj['MS_shear'], '.2f')}; chapa de ferragem ≥ {_f(jj['t_fitting_mm'])} mm; e ≥ "
                  f"{_f(jj['e_min_mm'])} mm, passo ≥ {_f(jj['pitch_min_mm'])} mm." if jj else "rever ferragem."), ""]
        L += ["**Superfícies de comando** (momento de charneira a V_D, Roskam VI Cap. 10; C_h PRESSUPOSTOS):", ""]
        L += _tbl(d["control_surfaces"]) + [""]
        rk = d.get("roskam_class_ii") or {}
        if rk:
            L += [f"**Pesos Classe II (Roskam Parte V)** vs Raymer (W_TO = {_f(rk['W_to_lb'], '.0f')} lb, n_ult = "
                  f"{_f(rk['n_ult'])}):", ""]
            L += _tbl([{"item": r["item"], "Roskam kg": r["roskam_kg"], "Raymer kg": r["raymer_kg"] or math.nan,
                        "razão": r["ratio"] or math.nan, "usado": "sim" if r["used"] else "não"} for r in rk["rows"]])
            L += [""] + [f"- {x}" for x in rk["notes"]] + [""]
    cal = R["calibration"]
    from .calibration import load
    applied = load(res.spec.assumptions) if hasattr(res, "spec") else {}
    L += ["## 8. Fatores de calibração L3 → L1/L2", "",
          "Rastreáveis: cada fator = razão (ou diferença) alta/baixa fidelidade do mesmo desenho. Aplicados só "
          "com `assumptions.calibration.apply: [aero, flutter]` e `file: <esta pasta>/calibration.json`; os de "
          "estruturas são só reportados.", ""]
    L += calibration.table_md(cal, applied) + [""]
    rc = S.get("rans_case") or {}
    L += ["## 9. Para uma máquina mais potente", ""]
    if rc and "skipped" not in rc:
        L += [f"- RANS-SA avião completo (meio modelo, `rans_case/`): ≈ {_f(rc.get('cells_estimate'), '.3g')} células, "
              f"RAM ≈ {_f(rc.get('ram_GB'), '.0f')} GB, ≈ {_f(rc.get('wall_h_8cores_3alpha'), '.0f')} h em 8 núcleos / "
              f"{_f(rc.get('wall_h_64cores_3alpha'), '.1f')} h em 64 (3 α). Comandos: "
              + "; ".join(f"`{c}`" for c in rc.get("commands", [])[1:])]
    if "k_CLa" not in we:
        L += ["- Asa 3-D Euler (`wing_euler/`): malha tetraédrica Gmsh + SU2 Euler; ver secção 4."]
    L += ["- Nastran SOL 145: `nastran/*.bdf` (MSC/NX Nastran ou equivalente).",
          "- FEM fino: `fem/` com ds menor (`fem.run_box_fem(res, work, ds=…)`).", ""]
    p = Path(out) / "report_fase4.md"
    p.write_text("\n".join(L), encoding="utf-8")
    return p
