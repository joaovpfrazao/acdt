"""Saídas do MDO de sistema: ``mdo.json`` (``acdt.mdo/1``), ``mdo.md``, ``evaluations.csv``, ``pareto.png`` e,
quando o domínio a fornece, a matriz de verificação do projeto escolhido."""
from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
from typing import Any, Mapping

FILES = ("mdo.json", "mdo.md", "evaluations.csv")


def _g(x: Any, fmt: str = ".5g") -> str:
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "sim" if x else "não"
    if isinstance(x, float):
        return "—" if not math.isfinite(x) else format(x, fmt)
    return str(x)


def to_csv(r: Mapping[str, Any]) -> str:
    ev = r["evaluations"]
    xs = sorted({k for e in ev for k in e["x"]})
    cb = sorted({k for e in ev for k in e["combo"]})
    obs = [o["metric"] for o in r["objectives"]]
    cons = [c["name"] for c in r["constraints"]]
    mets = sorted({k for e in ev for k in e["metrics"]} - set(obs))
    reqs = sorted({k for e in ev for k in e["requirements"]})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "phase", "ok", "feasible", "violation", "pareto", *[f"combo:{c}" for c in cb], *xs,
                *[f"obj:{o}" for o in obs], *[f"con:{c}" for c in cons], *mets, *[f"status:{q}" for q in reqs],
                "message"])
    par = set(r.get("pareto") or [])
    for e in ev:
        w.writerow([e["id"], e["phase"], e["ok"], e["feasible"], e["violation"], e["id"] in par,
                    *[e["combo"].get(c) for c in cb], *[e["x"].get(k) for k in xs],
                    *[e["objectives"].get(o) for o in obs], *[e["constraints"].get(c) for c in cons],
                    *[e["metrics"].get(m) for m in mets],
                    *[(e["requirements"].get(q) or {}).get("status") for q in reqs], e["message"]])
    return buf.getvalue()


def _row(r: Mapping[str, Any], e: Mapping[str, Any]) -> str:
    x = ", ".join(f"{k} = {_g(v)}" for k, v in {**e["combo"], **e["x"]}.items())
    o = ", ".join(f"{k} = {_g(v)}" for k, v in e["objectives"].items())
    sc = ", ".join(f"{k} {v}" for k, v in sorted(e["status_counts"].items()))
    return f"| {e['id']} | {x} | {o} | {'sim' if e['feasible'] else 'não'} | {sc} |"


def to_markdown(r: Mapping[str, Any]) -> str:
    ev = {e["id"]: e for e in r["evaluations"]}
    L = ["# MDO de sistema (`acdt mdo`)", "", f"Modelo: {r['model'].get('text', r['model'])}.", "",
         f"Estratégia: **{r['strategy']}**; {r['n_evaluations']} avaliações ({r['n_model_calls']} corridas do "
         f"modelo, {r['n_failed']} falhadas, {r['n_feasible']} viáveis). Política das restrições de requisitos: "
         f"`{r['policy']}`.", "", "## Variáveis de projeto", "", "| caminho | tipo | onde | limites/valores | origem |",
         "|---|---|---|---|---|"]
    for v in r["design_variables"]:
        lim = v.get("values") if v["type"] == "discrete" else f"[{_g(v['lower'])}, {_g(v['upper'])}], x0 {_g(v['x0'])}"
        L.append(f"| `{v['path']}` | {v['type']} | {v['placement']} | {lim} | {v['source']} |")
    if r.get("fixed"):
        L += ["", f"Sobreposições fixas do estudo: {r['fixed']}."]
    if r.get("warnings"):
        L += ["", "## Avisos", ""] + [f"* {w}" for w in r["warnings"]]
    L += ["", "## Objetivos", ""] + [f"* {o['sense']} `{o['metric']}`" for o in r["objectives"]]
    L += ["", "## Restrições", "", "| nome | tipo | nota |", "|---|---|---|"]
    L += [f"| `{c['name']}` | {c['kind']} | {c['note']} |" for c in r["constraints"]]
    if r["filters"]:
        L += ["", "Filtros (estado reportado por projeto, não restrição):", ""]
        L += [f"* `{f['id']}`: {f['nota']}" for f in r["filters"]]
    if r.get("closure"):
        c = r["closure"]
        L += ["", "## Fecho por iteração", "", f"`{c['name']}` de partida {c['x0']:g}; atualização `{c['update']}`; "
              f"aplicado a {c['apply']}; origem: {c['source']}.", ""]
        for lp in r["loops"]:
            vals = " → ".join(_g(it.get("closure_value")) for it in lp["iterations"])
            last = lp["iterations"][-1]
            L.append(f"* {lp['combo'] or '(sem combinação)'}: {vals} → {_g(last.get('closure_update'))} "
                     f"({lp['closure_status']})")
    L += ["", "## Resultado", ""]
    if r.get("chosen") is None:
        lv = r.get("least_violation")
        L.append("**Nenhum projeto viável.** " + (f"Menor violação: avaliação {lv} "
                                                  f"(violação {_g(ev[lv]['violation'])})." if lv is not None else ""))
    else:
        if r.get("knee"):
            L.append(f"Joelho da frente: avaliação **{r['knee']['id']}** ({r['knee']['method']}).")
        for m, i in r["best"].items():
            L.append(f"* melhor viável em `{m}`: avaliação {i}")
    L += ["", "| id | x | objetivos | viável | estado dos requisitos |", "|---|---|---|---|---|"]
    ids = list(r.get("pareto") or [])
    if r.get("chosen") is not None and r["chosen"] not in ids:
        ids.insert(0, r["chosen"])
    L += [_row(r, ev[i]) for i in ids[:60]]
    if len(r.get("pareto") or []) > 1:
        L += ["", f"Frente de Pareto: {len(r['pareto'])} projetos não dominados (todas as avaliações viáveis da "
              "decisão final; Deb et al. 2002)."]
    vm = r.get("verification_matrix")
    if vm:
        cov = vm.get("coverage") or {}
        L += ["", f"Matriz de verificação do projeto escolhido: `verification_matrix.md` "
              f"({cov.get('por_estado', '')})."]
    if r["pressupostos"]:
        L += ["", "## PRESSUPOSTOS", ""] + [f"* {p}" for p in r["pressupostos"]]
    L += ["", "Todas as avaliações (com o estado de cada requisito) em `evaluations.csv`.", ""]
    return "\n".join(L)


def plot(r: Mapping[str, Any], path: Path) -> Path | None:
    obs = r["objectives"]
    if len(obs) < 2:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    a, b = obs[0]["metric"], obs[1]["metric"]
    ev = r["evaluations"]
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    inf = [e for e in ev if e["ok"] and not e["feasible"] and e["objectives"].get(a) is not None
           and e["objectives"].get(b) is not None]
    fe = [e for e in ev if e["feasible"]]
    if inf:
        ax.scatter([e["objectives"][a] for e in inf], [e["objectives"][b] for e in inf], s=10, c="0.75",
                   label="inviável")
    if fe:
        ax.scatter([e["objectives"][a] for e in fe], [e["objectives"][b] for e in fe], s=14, c="tab:blue",
                   label="viável")
    byid = {e["id"]: e for e in ev}
    pf = sorted([byid[i] for i in r.get("pareto") or []], key=lambda e: e["objectives"][a])
    if pf:
        ax.plot([e["objectives"][a] for e in pf], [e["objectives"][b] for e in pf], "o-", c="tab:red", ms=5,
                label="frente de Pareto")
    if r.get("knee"):
        k = byid[r["knee"]["id"]]
        ax.scatter([k["objectives"][a]], [k["objectives"][b]], s=120, marker="*", c="k", zorder=5, label="joelho")
    ax.set_xlabel(f"{a} ({obs[0]['sense']})")
    ax.set_ylabel(f"{b} ({obs[1]['sense']})")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def _default(o: Any) -> Any:
    import numpy as np

    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _clean(o: Any) -> Any:
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def write(r: dict[str, Any], outdir: str | Path, plots: bool = True) -> list[Path]:
    d = Path(outdir)
    d.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    if plots:
        p = plot(r, d / "pareto.png")
        if p is not None:
            out.append(p)
    js, md, cs = d / FILES[0], d / FILES[1], d / FILES[2]
    js.write_text(json.dumps(_clean(r), indent=1, ensure_ascii=False, default=_default), encoding="utf-8")
    md.write_text(to_markdown(r), encoding="utf-8")
    cs.write_text(to_csv(r), encoding="utf-8")
    out += [js, md, cs]
    vm = r.get("verification_matrix")
    if vm:
        from acdt.core.verification import write_matrix

        out += write_matrix(vm, d)
    return out
