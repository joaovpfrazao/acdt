# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Rastreio por correlação de postos de Spearman (Spearman 1904; uso em amostras LHS: Helton & Davis, Reliab. Eng.
Syst. Saf. 81 (2003) 23–69, §6) sobre as corridas de treino do modelo verdadeiro de `uq.json`, para as saídas cujo
substituto quadrático foi rejeitado (Q² < 0,95), onde o Sobol' e o Morris ficam `nao_avaliado`.

Só ordena influências monótonas; não é decomposição de variância. p-valor do teste t de Spearman (scipy).
Uso: python examples/studies/uq_disciplinas/rastreio_postos.py examples/output/uq_disciplinas"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from scipy.stats import spearmanr

OUTS = ("W0_kg", "lcc_pv_USD", "co2e_fh_kg", "co2e_ciclo_kg", "unit_cost_USD", "hot_margin_min_C",
        "ice_power_W", "cooling_drag_area_m2", "mission_reliability")


def main(folder: str) -> dict:
    d = json.loads((Path(folder) / "uq.json").read_text(encoding="utf-8"))
    ok = [s for s in d["training_samples"] if s.get("ok")]
    names = list(ok[0]["inputs"])
    res: dict = {"metodo": "Spearman ρ (Spearman 1904; Helton & Davis 2003 §6)", "n": len(ok),
                 "n_falhadas": len(d["training_samples"]) - len(ok), "applied": False, "saidas": {}}
    for o in OUTS:
        ys = [s["metrics"].get(o) for s in ok]
        if any(y is None for y in ys) or len(set(ys)) < 3:
            res["saidas"][o] = {"veredicto": "nao_avaliado", "nota": "sem variância ou valores em falta"}
            continue
        rows = []
        for n in names:
            r, p = spearmanr([s["inputs"][n] for s in ok], ys)
            rows.append({"entrada": n, "rho": float(r), "p": float(p)})
        rows.sort(key=lambda x: -abs(x["rho"]))
        res["saidas"][o] = {"min": min(ys), "max": max(ys), "ranking": rows}
    (Path(folder) / "rastreio_postos.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = main(sys.argv[1] if len(sys.argv) > 1 else "examples/output/uq_disciplinas")
    for o, v in r["saidas"].items():
        top = v.get("ranking", [])[:3]
        print(o, v.get("min"), v.get("max"), [(t["entrada"].split(".")[-1], round(t["rho"], 2), round(t["p"], 3))
                                             for t in top])
