"""Multi-criteria comparison of alternatives: constraint screening, Pareto front, optional transparent weights.

* Pareto dominance / non-dominated set: a dominates b when a is no worse in every objective and strictly better
  in at least one — Pareto, V. (1906), "Manuale di economia politica"; Deb, K. (2001), "Multi-Objective
  Optimization using Evolutionary Algorithms", Wiley, Def. of dominance and non-dominated set.
* Weighted sum of min–max normalised objectives (only when the caller supplies weights; no default weights) —
  Marler, R. T. & Arora, J. S. (2004), "Survey of multi-objective optimization methods for engineering",
  Structural and Multidisciplinary Optimization 26, 369–395 (weighted sum, normalisation).

The module never picks an alternative: it reports dominance, constraint violations and, if weights are given,
the weighted score with each normalised term so the choice stays with the agent/user and is auditable.
A weighted sum cannot reach non-convex parts of the Pareto front (Marler & Arora 2004): report the front too.
"""
from __future__ import annotations

REF = "Deb 2001 (Pareto dominance); Marler & Arora 2004, SMO 26:369–395 (normalised weighted sum)"


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def _violations(m: dict, constraints: dict) -> list[str]:
    out = []
    for k, c in (constraints or {}).items():
        v = m.get(k)
        if not _num(v):
            out.append(f"{k}: missing")
            continue
        if "min" in c and v < c["min"]:
            out.append(f"{k} = {v:.4g} < min {c['min']:.4g}")
        if "max" in c and v > c["max"]:
            out.append(f"{k} = {v:.4g} > max {c['max']:.4g}")
    return out


def dominates(a: dict, b: dict, objectives: dict) -> bool:
    better = False
    for k, sense in objectives.items():
        x, y = a[k], b[k]
        if sense == "max":
            x, y = -x, -y
        if x > y:
            return False
        if x < y:
            better = True
    return better


def compare(alternatives: list[dict], objectives: dict, constraints: dict | None = None,
            weights: dict | None = None) -> dict:
    """alternatives: [{id, metrics: {...}}]; objectives: {metric: 'min'|'max'}; constraints:
    {metric: {min?, max?}}; weights: {metric: w ≥ 0} (optional) → table, pareto ids, dominated_by, scores."""
    for k, s in objectives.items():
        if s not in ("min", "max"):
            raise ValueError(f"objective {k}: sense must be 'min' or 'max'")
    if not objectives:
        raise ValueError("give at least one objective {metric: 'min'|'max'}")
    rows = []
    for a in alternatives:
        m = a.get("metrics") or {}
        missing = [k for k in objectives if not _num(m.get(k))]
        viol = _violations(m, constraints or {})
        rows.append({"id": a["id"], "metrics": m, "missing": missing, "violations": viol,
                     "feasible": not viol, "comparable": not missing})
    cand = [r for r in rows if r["feasible"] and r["comparable"]]
    for r in rows:
        r["dominated_by"] = [o["id"] for o in cand if o is not r and r in cand and
                             dominates(o["metrics"], r["metrics"], objectives)] if r in cand else []
    pareto = [r["id"] for r in cand if not r["dominated_by"]]
    for r in rows:
        r["pareto"] = r["id"] in pareto
    out = {"objectives": objectives, "constraints": constraints or {}, "pareto": pareto, "rows": rows,
           "reference": REF,
           "note": "no default weights: the Pareto set is the result; a weighted ranking exists only if weights "
                   "were given (then each normalised term is shown)"}
    if weights:
        ws = {k: float(w) for k, w in weights.items() if k in objectives}
        if not ws or sum(ws.values()) <= 0 or any(w < 0 for w in ws.values()):
            raise ValueError("weights: non-negative numbers on objective metrics, not all zero")
        tot = sum(ws.values())
        rng = {}
        for k in ws:
            vals = [r["metrics"][k] for r in cand]
            rng[k] = (min(vals), max(vals)) if vals else (0.0, 0.0)
        for r in cand:
            terms = {}
            for k, w in ws.items():
                lo, hi = rng[k]
                v = r["metrics"][k]
                n = 1.0 if hi == lo else ((hi - v) / (hi - lo) if objectives[k] == "min" else (v - lo) / (hi - lo))
                terms[k] = {"normalised": n, "weight": w / tot, "contribution": n * w / tot}
            r["score_terms"] = terms
            r["score"] = sum(t["contribution"] for t in terms.values())
        out["weights"] = {k: w / tot for k, w in ws.items()}
        out["normalisation_ranges"] = {k: list(v) for k, v in rng.items()}
        out["ranking"] = [r["id"] for r in sorted(cand, key=lambda r: (-r["score"], r["id"]))]
    return out


def plot(result: dict, x: str, y: str, path: str, title: str | None = None, labels: dict | None = None) -> str:
    """Scatter of two metrics with the Pareto set highlighted (others grey, infeasible as crosses)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    par = []
    for r in result["rows"]:
        m = r["metrics"]
        if not (_num(m.get(x)) and _num(m.get(y))):
            continue
        if not r["feasible"]:
            ax.scatter(m[x], m[y], marker="x", color="tab:red", zorder=3)
        elif r["pareto"]:
            ax.scatter(m[x], m[y], s=60, color="tab:blue", zorder=4)
            par.append((m[x], m[y]))
        else:
            ax.scatter(m[x], m[y], s=40, color="0.6", zorder=3)
        ax.annotate(r["id"], (m[x], m[y]), textcoords="offset points", xytext=(6, 4), fontsize=8)
    if len(par) > 1:
        par.sort()
        ax.plot(*zip(*par), color="tab:blue", lw=1, ls="--", zorder=2, label="frente de Pareto")
    lab = labels or {}
    ax.set_xlabel(lab.get(x, x))
    ax.set_ylabel(lab.get(y, y))
    ax.grid(alpha=0.3)
    ax.set_title(title or f"{y} vs {x}")
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], marker="o", ls="", color="tab:blue", label="Pareto (viável)"),
                       Line2D([], [], marker="o", ls="", color="0.6", label="dominada"),
                       Line2D([], [], marker="x", ls="", color="tab:red", label="falha restrições")],
              fontsize=8, loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
