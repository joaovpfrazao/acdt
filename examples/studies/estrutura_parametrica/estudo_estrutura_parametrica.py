# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Estudo (applied: false): estrutura paramétrica L1 em exemplos convencionais (docs/ESTRUTURA_PARAMETRICA.md).

Uso: python examples/studies/estrutura_parametrica/estudo_estrutura_parametrica.py [pasta_de_saída]

Para cada caso: corre o pipeline com ``structure_layout`` ligado EM MEMÓRIA e escreve a tabela de membros (CSV),
o resumo (JSON: orçamento de massa/CG/inércia, comparação com a viga L1 e Raymer, cavernas pesadas), o modelo de
vigas neutro (``acdt.beam/1``, JSON) e o mesmo em texto tipo Nastran (.bdf). Nada é aplicado aos exemplos."""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
STUDY = Path(__file__).with_name("estrutura_parametrica.yaml")


def _clean(o):
    import numpy as np
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, float) and o == float("inf"):
        return "inf"
    return o


def run_case(case: dict, out: Path) -> dict:
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.structure_layout import to_nastran
    ex = ROOT / case["example"]
    d = yaml.safe_load(ex.read_text(encoding="utf-8"))
    d.setdefault("assumptions", {})["structure_layout"] = case["structure_layout"]
    t0 = time.time()
    res = run_pipeline("aircraft", MissionSpec.from_dict(d, ex))["result"]
    r = res.structure_layout
    cid = case["id"]
    with open(out / f"{cid}_membros.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "componente", "tipo", "massa_kg", "x_m", "y_m", "z_m", "RF_min", "veredicto", "metodo",
                    "fonte", "seccao", "cargas"])
        for m in r["members"]:
            w.writerow([m["id"], m["component"], m["kind"],
                        "" if m["mass_kg"] is None else f"{m['mass_kg']:.4f}", f"{m['x_m']:.3f}", f"{m['y_m']:.3f}",
                        f"{m['z_m']:.3f}", "" if m["RF_min"] is None else f"{m['RF_min']:.3f}", m["verdict"],
                        m["method"], m["source"], json.dumps(_clean(m["section"]), ensure_ascii=False),
                        ";".join(m.get("loads") or [])])
    heavy = [{"id": m["id"], "loads": m["loads"], "caso": m["governing_case"], "seccao": m["section"],
              "RF": m["RF_min"], "veredicto": m["verdict"], "anel": m["ring"], "nota": m.get("note")}
             for m in r["members"] if m["kind"] == "caverna_pesada"]
    summ = {"caso": cid, "exemplo": case["example"], "applied": False, "W0_kg": res.sizing.W0,
            "tempo_s": time.time() - t0, "veredicto": r["verdict"], "contagem": r["verdict_counts"],
            "orcamento": r["budget"], "comparacao": r["comparison"], "cavernas_pesadas": heavy,
            "pior_estacao_casca": r["fuselage"].get("worst_shell_station"),
            "layout": r["fuselage"].get("layout"), "notas": r["fuselage"].get("notes"),
            "material": r["material"]["name"], "superficies": r.get("surfaces"),
            "booms": [{k: b.get(k) for k in ("evaluated", "reason", "geometry", "root_moment_limit_Nm", "notes")}
                      for b in r.get("booms", [])],
            "notas_layout": r.get("notes"), "vigas_em_falta": r["beam_model"].get("missing")}
    (out / f"{cid}_resumo.json").write_text(json.dumps(_clean(summ), indent=1, ensure_ascii=False), encoding="utf-8")
    (out / f"{cid}_vigas.json").write_text(json.dumps(_clean(r["beam_model"]), indent=1, ensure_ascii=False),
                                           encoding="utf-8")
    (out / f"{cid}_vigas.bdf").write_text(to_nastran(r["beam_model"]), encoding="utf-8")
    return summ


def main(out_dir: str | None = None) -> list[dict]:
    st = yaml.safe_load(STUDY.read_text(encoding="utf-8"))
    assert st.get("applied") is False, "estudo: applied tem de ser false"
    out = Path(out_dir) if out_dir else ROOT / "examples" / "output" / "estrutura_parametrica"
    out.mkdir(parents=True, exist_ok=True)
    rows = [run_case(c, out) for c in st["cases"]]
    for s in rows:
        c = s["comparacao"]
        print(f"{s['caso']}: W0 {s['W0_kg']:.1f} kg; fuselagem paramétrica {c['fuselage_layout_kg']:.1f} kg vs L1 "
              f"{c['fuselage_L1_kg']:.1f} kg vs Raymer {c['fuselage_raymer_kg']:.1f} kg; estabilizador "
              f"{c['htail_layout_kg']:.2f} vs L1 {c['htail_L1_kg']:.2f} kg; deriva {c['vtail_layout_kg']:.2f} vs L1 "
              f"{c['vtail_L1_kg']:.2f} kg; booms {[round(b['root_moment_limit_Nm'] or 0, 1) for b in s['booms']]} N·m; "
              f"{s['contagem']}")
    return rows


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
