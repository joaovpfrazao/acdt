# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Figuras do relatório de revisão, só com números já guardados nos registos.

Não se inventa um ponto, não se trata uma amostra em falta como zero e não se desenha um histograma
quando o estudo não trouxe as amostras (o Monte Carlo de ``acdt.uq/1`` deixa ``samples`` nulo quando
n > 64). A figura é uma transcrição do registo: veredicto ``validado`` para esse desenho, calibração
``nao_aplicar`` (não é uma medida nova).
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Mapping


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def _map(v: Any) -> Mapping[Any, Any]:
    if isinstance(v, Mapping):
        return v
    return {}


def _stem(rel: str) -> str:
    p = Path(str(rel).replace("\\", "/"))
    raw = p.stem if str(p.parent) in ("", ".") else f"{p.parent.as_posix()}_{p.stem}"
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._")
    return s or "estudo"


def pareto_plan(data: Mapping[str, Any], rel: str, sha256: str | None) -> dict[str, Any]:
    """Frente de Pareto de um ``acdt.mdo/1``. Sem dois objetivos finitos em todas as avaliações → não avaliado."""
    base: dict[str, Any] = {"kind": "pareto", "file": rel, "sha256": sha256, "veredicto": "nao_avaliado",
                            "calibracao": "nao_aplicar", "out_name": f"pareto_{_stem(rel)}.png", "points": [],
                            "front": []}
    objs = [o for o in (data.get("objectives") or []) if isinstance(o, Mapping)]
    if len(objs) < 2 or not objs[0].get("metric") or not objs[1].get("metric"):
        base["reason"] = "o registo MDO não declara dois objetivos"
        return base
    mx, my = str(objs[0]["metric"]), str(objs[1]["metric"])
    evs = data.get("evaluations")
    if not isinstance(evs, list) or not evs:
        base["reason"] = "o registo MDO não traz avaliações"
        return base
    pts: list[dict[str, Any]] = []
    for e in evs:
        if not isinstance(e, Mapping):
            base["reason"] = "avaliação inválida no registo MDO"
            return base
        o = _map(e.get("objectives"))
        if not _finite(o.get(mx)) or not _finite(o.get(my)):
            base["reason"] = f"avaliação {e.get('id')!r} sem {mx} e {my} finitos"
            return base
        pts.append({"id": e.get("id"), "x": float(o[mx]), "y": float(o[my]), "feasible": e.get("feasible")})
    front = list(data.get("pareto") or [])
    ids = {p["id"] for p in pts}
    missing = [i for i in front if i not in ids]
    if missing:
        base["reason"] = f"a frente cita avaliações que não estão no registo: {missing}"
        return base
    base.update({"veredicto": "validado", "reason": "", "x": mx, "y": my,
                 "x_sense": objs[0].get("sense"), "y_sense": objs[1].get("sense"),
                 "points": pts, "front": front, "n": len(pts), "n_front": len(front)})
    return base


def histogram_plan(data: Mapping[str, Any], rel: str, sha256: str | None) -> dict[str, Any]:
    """Histograma de uma métrica das amostras guardadas. Sem amostras completas → não avaliado."""
    base: dict[str, Any] = {"kind": "histograma_uq", "file": rel, "sha256": sha256,
                            "veredicto": "nao_avaliado", "calibracao": "nao_aplicar",
                            "out_name": f"histograma_{_stem(rel)}.png", "values": []}
    if "samples" not in data or data.get("samples") is None:
        base["reason"] = ("o registo UQ não guarda amostras (samples nulo ou ausente); "
                          "não se desenha uma distribuição")
        return base
    samples = data.get("samples")
    if not isinstance(samples, list) or not samples:
        base["reason"] = "a lista de amostras está vazia"
        return base
    ok = [s for s in samples if isinstance(s, Mapping) and s.get("ok") is True]
    if len(ok) != len(samples):
        base["reason"] = "há amostras sem ok verdadeiro; não se omite nenhuma como se fosse zero"
        return base
    metric = None
    for s in ok:
        metrics = _map(s.get("metrics"))
        for k, v in metrics.items():
            if _finite(v):
                metric = str(k)
                break
        if metric:
            break
    if metric is None:
        base["reason"] = "as amostras não trazem nenhuma métrica finita"
        return base
    vals: list[float] = []
    for s in ok:
        metrics = _map(s.get("metrics"))
        if not _finite(metrics.get(metric)):
            base["reason"] = f"a amostra não tem {metric} finito; o histograma não fica parcial"
            return base
        vals.append(float(metrics[metric]))
    n_ok = data.get("n_ok")
    if isinstance(n_ok, int) and not isinstance(n_ok, bool) and n_ok != len(vals):
        base["reason"] = f"n_ok = {n_ok} e há {len(vals)} amostras; a lista não está completa"
        return base
    base.update({"veredicto": "validado", "reason": "", "metric": metric, "values": vals, "n": len(vals)})
    return base


def draw_plan(plan: Mapping[str, Any], path: Path) -> None:
    """Desenha um plano já validado. Não cria o ficheiro se o veredicto não for ``validado``."""
    if plan.get("veredicto") != "validado":
        return
    import matplotlib
    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    if plan["kind"] == "pareto":
        front = set(plan["front"])
        off = [p for p in plan["points"] if p["id"] not in front]
        on = [p for p in plan["points"] if p["id"] in front]
        if off:
            ax.scatter([p["x"] for p in off], [p["y"] for p in off], c="#666666", label="avaliação")
        if on:
            ax.scatter([p["x"] for p in on], [p["y"] for p in on], c="#a33b3b", label="frente")
        ax.set_xlabel(f"{plan['x']} ({plan.get('x_sense') or '?'})")
        ax.set_ylabel(f"{plan['y']} ({plan.get('y_sense') or '?'})")
        ax.set_title("Frente de Pareto (valores do registo)")
        ax.legend()
    else:
        ax.hist(list(plan["values"]), bins="auto", color="#3d5a80")
        ax.set_xlabel(str(plan["metric"]))
        ax.set_ylabel("contagem")
        ax.set_title("Histograma das amostras guardadas")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
