# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Estudo (applied: false): planador em compósito (Rolladen-Schneider LS4) dimensionado pelo acdt vs avião real.

Uso: python examples/studies/planador_ls4/estudo_planador_ls4.py [pasta_de_saída]

Escreve ``comparacao.md`` e ``comparacao.json`` (tabela acdt vs real com Δ %, fontes de reference_data.json) e as
imagens 3-D da estrutura (por tipo e por RF) do caso com a geometria do LS4. Nada é aplicado ao exemplo."""
from __future__ import annotations

import copy
import json
import math
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
STUDY = Path(__file__).with_name("planador_ls4.yaml")
G0 = 9.80665


def _run(d: dict, ex: Path):
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec
    return run_pipeline("aircraft", MissionSpec.from_dict(d, ex))["result"]


def run_case(case: dict, base: dict, ex: Path) -> tuple[object, list[dict]]:
    d = copy.deepcopy(base)
    hist: list[dict] = []
    S_t = case.get("wing_area_m2")
    if S_t is None:
        return _run(d, ex), hist
    ws = float(d["assumptions"]["constraints"]["ws_fixed"])
    res = None
    for _ in range(8):
        d["assumptions"]["constraints"]["ws_fixed"] = ws
        res = _run(d, ex)
        new = res.sizing.W0 * G0 / float(S_t)
        hist.append({"ws_N_m2": ws, "W0_kg": res.sizing.W0, "S_m2": res.S})
        if abs(new - ws) < 0.2:
            break
        ws = new
    return res, hist


def wing_alone_e(res) -> dict:
    """Sensibilidade: e de Trefftz do AVL só com a asa (sem a empenagem não equilibrada) vs configuração completa."""
    import re
    import subprocess
    import tempfile

    from acdt.domains.aircraft.aero.avl import write_avl_file
    out: dict = {}
    with tempfile.TemporaryDirectory() as tmp:
        write_avl_file(res.config, Path(tmp) / "a.avl", mach=0.08)
        s = (Path(tmp) / "a.avl").read_text()
        (Path(tmp) / "w.avl").write_text(s[: s.index("SURFACE\nHtail")])
        for f, k in (("a.avl", "e_config"), ("w.avl", "e_asa")):
            r = subprocess.run(["avl", f], input="OPER\nA A 6\nX\n\n\nQUIT\n", capture_output=True, text=True,
                               cwd=tmp, timeout=60).stdout
            out[k] = float(re.findall(r"e =\s*(\S+)", r)[-1])
    return out


def metrics(res, ref: dict, m_ref: float) -> dict:
    from acdt.domains.aircraft.glide import glide_from_result
    v = ref["values"]
    sl = res.structure_layout or {}
    byc = (sl.get("budget") or {}).get("by_component_kg", {})
    items = {it.key: it.mass for it in res.weights.items}
    st = res.stability
    xle = st.x_wing_apex
    cg = [1000 * (c.x_cg - xle) for c in st.cases]
    vn = res.structures.vn
    gM = glide_from_result(res)                      # W0
    gR = glide_from_result(res, m_ref)               # massa da polar publicada
    gMT = glide_from_result(res, v["mtom_kg"]["value"])
    fl = sl.get("flutter") or {}
    ae = getattr(res, "aeroelastic", None)
    out = {
        "W0_kg": res.sizing.W0, "We_kg": res.sizing.We, "S_m2": res.S, "b_m": res.config.wing.span,
        "WS_kg_m2": res.sizing.W0 / res.S,
        "wing_layout_kg": float(byc.get("asa", float("nan"))),
        "wing_box_structures_kg": float(res.structures.box.masses["total"]),
        "fuselage_layout_kg": float(byc.get("fuselagem", float("nan"))),
        "htail_layout_kg": float(byc.get("estabilizador", float("nan"))),
        "vtail_layout_kg": float(byc.get("deriva", float("nan"))),
        "fittings_layout_kg": float(byc.get("ligacoes", float("nan"))),
        "main_gear_kg": items.get("main_gear"), "tail_wheel_kg": items.get("nose_gear"),
        "flight_controls_kg": items.get("flight_controls"), "avionics_kg": items.get("avionics"),
        "cg_mm_aft_LE": [min(cg), max(cg)],
        "VS1_W0_km_h": 3.6 * gM.V_stall, "VS1_mtom_km_h": 3.6 * gMT.V_stall, "VS1_ref_mass_km_h": 3.6 * gR.V_stall,
        "VA_km_h": 3.6 * vn.VA, "VD_km_h": 3.6 * vn.VD, "n1": vn.n_pos if hasattr(vn, "n_pos") else None,
        "vn": res.structures.vn.summary() if hasattr(res.structures.vn, "summary") else None,
        "LDmax": gR.LD_max, "V_LDmax_km_h": 3.6 * gR.V_best_LD,
        "sink_min_m_s": gR.sink_min, "V_sink_min_km_h": 3.6 * gR.V_min_sink,
        "sink_at_km_h": {str(int(V)): gR.sink(V / 3.6) for V in (75, 95, 100, 148, 200)},
        "CD0": res.polar.CD0, "K": res.polar.K, "CLmax": res.highlift.CLmax_clean,
        "flutter_layout": {k: fl.get(k) for k in ("evaluated", "V_F_eas", "V_div_eas", "V_required_eas", "verdict")},
        "aeroelastic_margins": ({k: {"V_eas": m.get("V_eas"), "ok": m.get("ok")} for k, m in ae.margins.items()}
                                if ae is not None and hasattr(ae, "margins") else None),
        "structure_verdicts": sl.get("verdict_counts"),
        "n_frames_fuselage": len((sl.get("fuselage") or {}).get("frames") or []),
        "n_stringers_fuselage": ((sl.get("fuselage") or {}).get("layout") or {}).get("n_stringers"),
    }
    return out


def _d(a, b):
    if a is None or b is None or (isinstance(a, float) and math.isnan(a)):
        return "desconhecido"
    return f"{100 * (a - b) / b:+.0f} %"


def table(c: dict, ref: dict) -> list[list[str]]:
    v = ref["values"]
    src = lambda k: v[k]["source"]  # noqa: E731
    rows = [
        ["W0 / MTOM [kg]", f"{c['W0_kg']:.0f}", f"{v['mtom_kg']['value']:.0f}", _d(c["W0_kg"], v["mtom_kg"]["value"]),
         src("mtom_kg")],
        ["massa vazia [kg]", f"{c['We_kg']:.0f}", f"{v['empty_mass_kg']['value']:.0f}",
         _d(c["We_kg"], v["empty_mass_kg"]["value"]), src("empty_mass_kg")],
        ["asa (estrutura paramétrica) [kg]", f"{c['wing_layout_kg']:.1f}", f"{v['wing_mass_kg']['value']:.0f}",
         _d(c["wing_layout_kg"], v["wing_mass_kg"]["value"]), src("wing_mass_kg")],
        ["fuselagem (casca + cavernas + anteparas) [kg]", f"{c['fuselage_layout_kg']:.1f}", "desconhecido",
         "desconhecido", "—"],
        ["empenagens H + V [kg]", f"{c['htail_layout_kg'] + c['vtail_layout_kg']:.1f}", "desconhecido",
         "desconhecido", "—"],
        ["trem (Raymer 15.50/15.51, extrapolado) [kg]", f"{(c['main_gear_kg'] or 0) + (c['tail_wheel_kg'] or 0):.1f}",
         "desconhecido", "desconhecido", "—"],
        ["S [m²]", f"{c['S_m2']:.2f}", f"{v['wing_area_m2']['value']:.2f}", _d(c["S_m2"], v["wing_area_m2"]["value"]),
         src("wing_area_m2")],
        ["envergadura [m]", f"{c['b_m']:.2f}", f"{v['span_m']['value']:.2f}", _d(c["b_m"], v["span_m"]["value"]),
         src("span_m")],
        ["carga alar W0/S [kg/m²]", f"{c['WS_kg_m2']:.1f}", f"{v['wing_loading_mtom_kg_m2']['value']:.2f}",
         _d(c["WS_kg_m2"], v["wing_loading_mtom_kg_m2"]["value"]), src("wing_loading_mtom_kg_m2")],
        ["CG [mm atrás do BA na raiz]", f"{c['cg_mm_aft_LE'][0]:.0f}–{c['cg_mm_aft_LE'][1]:.0f}", "225–375",
         "dentro" if 225 <= c["cg_mm_aft_LE"][0] and c["cg_mm_aft_LE"][1] <= 375 else "fora", src("cg_range_mm_aft_datum")],
        ["(L/D)max à massa da polar", f"{c['LDmax']:.1f}", f"{v['polar_best_LD_ref_mass']['value']:.0f}",
         _d(c["LDmax"], v["polar_best_LD_ref_mass"]["value"]), "cumulus"],
        ["V de (L/D)max [km/h]", f"{c['V_LDmax_km_h']:.0f}", f"{v['polar_best_LD_ref_mass']['V_km_h']:.0f}",
         _d(c["V_LDmax_km_h"], v["polar_best_LD_ref_mass"]["V_km_h"]), "cumulus"],
    ]
    for (V, w) in v["polar_points_km_h_m_s"]["value"]:
        a = c["sink_at_km_h"][str(int(V))]
        rows.append([f"afundamento a {V:.0f} km/h [m/s]", f"{a:.3f}", f"{w:.3f}", _d(a, w), "cumulus"])
    rows += [
        ["(L/D)max (Jane's, massa desconhecida)", f"{c['LDmax']:.1f}", f"{v['best_LD']['value']}",
         _d(c["LDmax"], v["best_LD"]["value"]), src("best_LD")],
        ["afundamento mínimo [m/s] (Jane's, massa desc.)", f"{c['sink_min_m_s']:.2f} a {c['V_sink_min_km_h']:.0f} km/h",
         f"{v['min_sink_m_s']['value']} a 75 km/h", _d(c["sink_min_m_s"], v["min_sink_m_s"]["value"]),
         src("min_sink_m_s")],
        ["V perda [km/h] (Jane's, massa desc.; acdt a 320 kg | MTOM)",
         f"{c['VS1_ref_mass_km_h']:.0f} | {c['VS1_mtom_km_h']:.0f}", f"{v['stall_speed_km_h']['value']:.0f}",
         _d(c["VS1_ref_mass_km_h"], v["stall_speed_km_h"]["value"]), src("stall_speed_km_h")],
        ["VA [km/h] (VS1 √n1 a W0)", f"{c['VA_km_h']:.0f}", f"{v['VA_km_h']['value']:.0f}",
         _d(c["VA_km_h"], v["VA_km_h"]["value"]), src("VA_km_h")],
        ["VD [km/h] (entrada: VNE/0,9)", f"{c['VD_km_h']:.0f}", f"{v['VD_min_km_h']['value']:.0f}",
         _d(c["VD_km_h"], v["VD_min_km_h"]["value"]), src("VD_min_km_h")],
    ]
    fl = c["flutter_layout"]
    if fl.get("evaluated"):
        rows.append(["flutter (vigas + faixas) V_F [km/h EAS]", f"{3.6 * fl['V_F_eas']:.0f} ({fl['verdict']} vs "
                     f"1,2 VD = {3.6 * fl['V_required_eas']:.0f})", "> VD = 300 (sem flutter)",
                     _d(3.6 * fl["V_F_eas"], 300.0), src("flutter")])
    return rows


def main(out: Path | None = None) -> dict:
    cfg = yaml.safe_load(STUDY.read_text(encoding="utf-8"))
    ex = ROOT / cfg["example"]
    ref = json.loads((ROOT / cfg["reference"]).read_text(encoding="utf-8"))
    out = out or (ROOT / cfg["output"])
    out.mkdir(parents=True, exist_ok=True)
    base = yaml.safe_load(ex.read_text(encoding="utf-8"))
    m_ref = float(cfg["polar_reference_mass_kg"])
    allc: dict = {"applied": False, "example": cfg["example"], "reference": cfg["reference"], "cases": {}}
    md = ["# Planador em compósito — Rolladen-Schneider LS4: acdt vs avião real", "",
          "Estudo `applied: false` (examples/studies/planador_ls4). Fontes e qualidade em "
          "`examples/benchmarks/ls4/reference_data.json`. Δ = (acdt − real)/real.", ""]
    for case in cfg["cases"]:
        t0 = time.time()
        res, hist = run_case(case, base, ex)
        c = metrics(res, ref, m_ref)
        try:
            c["avl_e"] = wing_alone_e(res)
            from acdt.domains.aircraft.glide import glide_polar
            AR = res.config.wing.AR
            dK = 1 / (math.pi * AR * c["avl_e"]["e_asa"]) - 1 / (math.pi * AR * c["avl_e"]["e_config"])
            g2 = glide_polar(res.S, res.polar.CD0, res.polar.K + dK, res.highlift.CLmax_clean, m_ref)
            c["sens_wing_alone_e"] = {"K": res.polar.K + dK, "LDmax": g2.LD_max, "sink_min_m_s": g2.sink_min,
                                      "sink_at_km_h": {str(int(V)): g2.sink(V / 3.6) for V in (95, 148, 200)}}
        except Exception as ex_:  # noqa: BLE001 — sensibilidade opcional (AVL)
            c["avl_e"] = {"erro": f"{type(ex_).__name__}: {ex_}"}
        c["ws_history"] = hist
        c["t_s"] = time.time() - t0
        allc["cases"][case["id"]] = c
        md += [f"## Caso `{case['id']}` — {case.get('note', '')}", "",
               "| grandeza | acdt | real | Δ | fonte |", "|---|---|---|---|---|"]
        md += ["| " + " | ".join(r) + " |" for r in table(c, ref)]
        if "sens_wing_alone_e" in c:
            s = c["sens_wing_alone_e"]
            md += ["", f"Sensibilidade (AVL só com a asa, e = {c['avl_e']['e_asa']:.3f} vs configuração "
                   f"{c['avl_e']['e_config']:.3f} com a empenagem não equilibrada): (L/D)max {s['LDmax']:.1f}, "
                   f"afundamento mín. {s['sink_min_m_s']:.3f} m/s; a 95/148/200 km/h "
                   + "/".join(f"{w:.3f}" for w in s["sink_at_km_h"].values()) + " m/s."]
        md += ["", f"Veredictos da estrutura paramétrica: {c['structure_verdicts']}; fuselagem com "
               f"{c['n_frames_fuselage']} cavernas/anteparas e {c['n_stringers_fuselage']} reforçadores.", ""]
        if case.get("wing_area_m2"):
            from acdt.domains.aircraft.structure_render import render_layout
            for mode, suf in (("kind", ""), ("RF", "_rf")):
                p = out / f"estrutura_ls4_{case['id']}{suf}.png"
                render_layout(res.structure_layout, p, color_by=mode,
                              title=f"LS4 (acdt, compósito monocasca) — {case['id']}")
                md.append(f"![estrutura {mode}]({p.name})")
            md.append("")
    def _clean(o):
        import numpy as np
        if isinstance(o, dict):
            return {str(k): _clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_clean(v) for v in o]
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, float) and not math.isfinite(o):
            return str(o)
        return o
    (out / "comparacao.json").write_text(json.dumps(_clean(allc), indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "comparacao.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return allc


if __name__ == "__main__":
    r = main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(json.dumps({k: {kk: r["cases"][k][kk] for kk in ("W0_kg", "We_kg", "wing_layout_kg", "LDmax", "t_s")}
                      for k in r["cases"]}, indent=1))
