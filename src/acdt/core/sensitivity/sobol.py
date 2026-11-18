"""Sobol' global sensitivity indices (first-order and total-effect).

Saltelli sample matrices A, B, A_B^(i) with Jansen (1999) estimators as recommended
in Saltelli et al. (2010) / Saltelli et al., *Global Sensitivity Analysis. The Primer*,
Wiley 2008. Optional percentile bootstrap CIs (Efron & Tibshirani resampling of the N
rows) — when bootstrap is off, indices are reported as point estimates.

Rules: missing samples, zero/near-zero output variance, or failed evaluations →
``unassessed`` for that index (never a silent 0.0 that reads as "no influence").
True near-zero indices from a valid estimator remain numeric with status ``ok``.

No GPL in-process; numpy only (core dep). No CFD/ADflow/TACS.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

REF = (
    "Saltelli et al., Global Sensitivity Analysis. The Primer, Wiley 2008; "
    "Saltelli et al., Comput. Phys. Commun. 181 (2010) 259–270 (Jansen estimators); "
    "Jansen, Comput. Phys. Commun. 117 (1999) 35–43; "
    "Efron & Tibshirani, An Introduction to the Bootstrap, 1993 (optional CIs)"
)

_EPS_VAR = 1e-14


def saltelli_matrices(
    bounds: list[dict],
    n: int,
    *,
    seed: int = 0,
) -> dict[str, Any]:
    """Draw Saltelli A, B (N×k) by independent Monte Carlo in [low, high].

    ``bounds``: ``[{name, low, high}]``. Returns matrices and the list of evaluation
    points in Saltelli order: all rows of A, all of B, then for each factor i the
    rows of A_B^(i) (A with column i from B). Total points = N*(k+2).

    Sampling is i.i.d. uniform (Saltelli 2008 MC design). Quasi-Monte Carlo Sobol'
    sequences are not required for correctness of the estimators.
    """
    if n < 2:
        raise ValueError("Sobol/Saltelli sample size N must be >= 2")
    if not bounds:
        raise ValueError("bounds required [{name, low, high}, …]")
    names, lows, highs = [], [], []
    for b in bounds:
        name = b["name"]
        lo, hi = float(b["low"]), float(b["high"])
        if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
            raise ValueError(f"degenerate range for '{name}': low={lo}, high={hi}")
        names.append(name)
        lows.append(lo)
        highs.append(hi)
    k = len(names)
    rng = np.random.default_rng(seed)
    lo = np.asarray(lows, dtype=float)
    hi = np.asarray(highs, dtype=float)
    A = lo + (hi - lo) * rng.random((n, k))
    B = lo + (hi - lo) * rng.random((n, k))
    AB = []
    for i in range(k):
        Abi = A.copy()
        Abi[:, i] = B[:, i]
        AB.append(Abi)
    points = []
    for row in A:
        points.append({"tag": "A", "values": {names[j]: float(row[j]) for j in range(k)}})
    for row in B:
        points.append({"tag": "B", "values": {names[j]: float(row[j]) for j in range(k)}})
    for i, Abi in enumerate(AB):
        for row in Abi:
            points.append({
                "tag": f"AB_{names[i]}",
                "factor": names[i],
                "values": {names[j]: float(row[j]) for j in range(k)},
            })
    return {
        "names": names,
        "n": n,
        "k": k,
        "A": A,
        "B": B,
        "AB": AB,
        "points": points,
        "n_evaluations": n * (k + 2),
        "seed": seed,
        "bounds": [{"name": names[i], "low": lows[i], "high": highs[i]} for i in range(k)],
        "method": "Saltelli MC matrices A, B, A_B^(i) (Primer 2008)",
        "reference": REF,
    }


def _jansen_indices(y_a: np.ndarray, y_b: np.ndarray, y_ab: np.ndarray) -> tuple[float, float, float]:
    """Return (S_i, ST_i, V) using Jansen estimators; V is sample variance of Y_A."""
    y_a = np.asarray(y_a, dtype=float).ravel()
    y_b = np.asarray(y_b, dtype=float).ravel()
    y_ab = np.asarray(y_ab, dtype=float).ravel()
    n = y_a.size
    # variance of model output (use Y_A; Saltelli 2010)
    v = float(np.var(y_a, ddof=1)) if n > 1 else 0.0
    if v < _EPS_VAR:
        return float("nan"), float("nan"), v
    # Jansen first-order: S_i = (V - 1/(2N) Σ (Y_B - Y_ABi)²) / V
    s_i = (v - (0.5 / n) * float(np.sum((y_b - y_ab) ** 2))) / v
    # Jansen total-effect: ST_i = 1/(2N) Σ (Y_A - Y_ABi)² / V
    st_i = ((0.5 / n) * float(np.sum((y_a - y_ab) ** 2))) / v
    return float(s_i), float(st_i), v


def _finite(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(float(x))


def sobol_indices(
    y_a: list[float] | np.ndarray,
    y_b: list[float] | np.ndarray,
    y_ab: dict[str, list[float] | np.ndarray],
    *,
    names: list[str] | None = None,
    bootstrap: int = 0,
    seed: int = 0,
    conf: float = 0.95,
) -> dict[str, Any]:
    """Sobol' S_i and S_Ti from Saltelli evaluations of one scalar output.

    ``y_ab[name]`` must align row-wise with ``y_a`` / ``y_b`` (length N).
    ``bootstrap>0`` → percentile CIs (Efron); else point estimates only.
    """
    ya = np.asarray(y_a, dtype=float).ravel()
    yb = np.asarray(y_b, dtype=float).ravel()
    if ya.size != yb.size or ya.size < 2:
        return {
            "status": "unassessed",
            "reason": "Y_A/Y_B missing or N<2 — cannot estimate Sobol indices",
            "indices": [],
            "reference": REF,
        }
    if not np.all(np.isfinite(ya)) or not np.all(np.isfinite(yb)):
        return {
            "status": "unassessed",
            "reason": "non-finite model outputs in Y_A/Y_B",
            "indices": [],
            "reference": REF,
        }
    names = list(names or y_ab.keys())
    if not names:
        return {
            "status": "unassessed",
            "reason": "no factors in Y_AB",
            "indices": [],
            "reference": REF,
        }
    v = float(np.var(ya, ddof=1))
    if v < _EPS_VAR:
        return {
            "status": "unassessed",
            "reason": "output variance ~0 — indices undefined (not 'no influence')",
            "variance": v,
            "n": int(ya.size),
            "indices": [],
            "reference": REF,
        }

    rows = []
    any_ok = False
    any_un = False
    for name in names:
        if name not in y_ab:
            rows.append({
                "variable": name, "S1": None, "ST": None, "status": "unassessed",
                "reason": f"Y_AB for '{name}' missing",
            })
            any_un = True
            continue
        yabi = np.asarray(y_ab[name], dtype=float).ravel()
        if yabi.size != ya.size or not np.all(np.isfinite(yabi)):
            rows.append({
                "variable": name, "S1": None, "ST": None, "status": "unassessed",
                "reason": f"Y_AB['{name}'] length/NaN mismatch",
            })
            any_un = True
            continue
        s1, st, _ = _jansen_indices(ya, yb, yabi)
        if not math.isfinite(s1) or not math.isfinite(st):
            rows.append({
                "variable": name, "S1": None, "ST": None, "status": "unassessed",
                "reason": "estimator returned non-finite",
            })
            any_un = True
            continue
        row = {
            "variable": name, "S1": s1, "ST": st, "status": "ok",
            "estimator": "Jansen 1999 / Saltelli et al. 2010",
        }
        if bootstrap and bootstrap > 0:
            ci = _bootstrap_ci(ya, yb, yabi, n_boot=bootstrap, seed=seed, conf=conf)
            row["S1_ci"] = ci["S1_ci"]
            row["ST_ci"] = ci["ST_ci"]
            row["bootstrap"] = bootstrap
            row["confidence"] = conf
        else:
            row["note"] = "point estimate (no bootstrap)"
        rows.append(row)
        any_ok = True

    # rank by total-effect when ok
    ranked = sorted(
        [r for r in rows if r["status"] == "ok"],
        key=lambda r: -abs(r["ST"]),
    )
    status = "ok" if any_ok and not any_un else ("unassessed" if not any_ok else "partial")
    return {
        "status": status,
        "n": int(ya.size),
        "k": len(names),
        "variance": v,
        "mean_Y_A": float(np.mean(ya)),
        "indices": rows,
        "ranking_ST": ranked,
        "bootstrap": bootstrap if bootstrap else None,
        "confidence": conf if bootstrap else None,
        "estimator": "Jansen (first-order + total-effect)",
        "reference": REF,
        "note": (
            "S1=first-order, ST=total-effect incl. interactions. "
            "Sum of S1 may be <1; ST_i >= S1_i expected. "
            + ("CIs: percentile bootstrap on N rows." if bootstrap else
               "Point estimates only — enable bootstrap for CIs.")
        ),
    }


def _bootstrap_ci(y_a, y_b, y_ab, *, n_boot: int, seed: int, conf: float) -> dict:
    rng = np.random.default_rng(seed)
    n = y_a.size
    s1s, sts = [], []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        s1, st, v = _jansen_indices(y_a[idx], y_b[idx], y_ab[idx])
        if v >= _EPS_VAR and math.isfinite(s1) and math.isfinite(st):
            s1s.append(s1)
            sts.append(st)
    alpha = (1.0 - conf) / 2.0
    def pct(arr):
        if len(arr) < 2:
            return None
        a = np.asarray(arr, dtype=float)
        return [float(np.quantile(a, alpha)), float(np.quantile(a, 1 - alpha))]
    return {"S1_ci": pct(s1s), "ST_ci": pct(sts), "n_valid": len(s1s)}


def evaluate_saltelli(
    design: dict[str, Any],
    evaluate: Callable[[dict[str, float]], float | None],
) -> dict[str, Any]:
    """Run ``evaluate(values)->scalar`` on every Saltelli point; pack Y_A, Y_B, Y_AB.

    ``evaluate`` returning None / non-finite → that row marked failed; if any failures,
    indices for affected factors become unassessed.
    """
    names = design["names"]
    n, k = design["n"], design["k"]
    y_a, y_b = [], []
    failed = 0
    for row in design["A"]:
        val = evaluate({names[j]: float(row[j]) for j in range(k)})
        if not _finite(val):
            failed += 1
            y_a.append(float("nan"))
        else:
            y_a.append(float(val))
    for row in design["B"]:
        val = evaluate({names[j]: float(row[j]) for j in range(k)})
        if not _finite(val):
            failed += 1
            y_b.append(float("nan"))
        else:
            y_b.append(float(val))
    y_ab: dict[str, list[float]] = {name: [] for name in names}
    for i, name in enumerate(names):
        for row in design["AB"][i]:
            val = evaluate({names[j]: float(row[j]) for j in range(k)})
            if not _finite(val):
                failed += 1
                y_ab[name].append(float("nan"))
            else:
                y_ab[name].append(float(val))
    return {
        "Y_A": y_a,
        "Y_B": y_b,
        "Y_AB": y_ab,
        "failed_evaluations": failed,
        "n_evaluations": design["n_evaluations"],
        "names": names,
    }


def sobol_analyze(
    bounds: list[dict],
    evaluate: Callable[[dict[str, float]], float | None],
    *,
    n: int = 64,
    seed: int = 0,
    bootstrap: int = 0,
    conf: float = 0.95,
) -> dict[str, Any]:
    """Generate Saltelli sample, evaluate, return Sobol indices for a scalar output."""
    try:
        design = saltelli_matrices(bounds, n, seed=seed)
    except ValueError as ex:
        return {"status": "unassessed", "reason": str(ex), "indices": [], "reference": REF}
    packed = evaluate_saltelli(design, evaluate)
    if packed["failed_evaluations"]:
        # if any NaN, sobol_indices will mark unassessed via non-finite check
        pass
    out = sobol_indices(
        packed["Y_A"], packed["Y_B"], packed["Y_AB"],
        names=packed["names"], bootstrap=bootstrap, seed=seed, conf=conf,
    )
    out["design"] = {
        "n": design["n"], "k": design["k"], "seed": seed,
        "bounds": design["bounds"],
        "n_evaluations": design["n_evaluations"],
        "failed_evaluations": packed["failed_evaluations"],
        "method": design["method"],
    }
    return out


def sobol_from_evaluations(
    payload: dict,
    *,
    bootstrap: int = 0,
    seed: int = 0,
    conf: float = 0.95,
) -> dict[str, Any]:
    """Sobol indices from a supplied Saltelli evaluation dict.

    Expected keys: ``Y_A``, ``Y_B``, ``Y_AB`` (dict name→list), optional ``names``.
    Or ``metric`` + ``evaluations``: list of ``{tag, values, metrics}`` from a prior run.
    """
    if "Y_A" in payload and "Y_B" in payload and "Y_AB" in payload:
        return sobol_indices(
            payload["Y_A"], payload["Y_B"], payload["Y_AB"],
            names=payload.get("names"), bootstrap=bootstrap, seed=seed, conf=conf,
        )
    metric = payload.get("metric")
    evs = payload.get("evaluations") or payload.get("points")
    names = payload.get("names") or [b["name"] for b in payload.get("bounds") or []]
    if not metric or not evs or not names:
        return {
            "status": "unassessed",
            "reason": "need Y_A/Y_B/Y_AB or evaluations+metric+names",
            "indices": [],
            "reference": REF,
        }
    y_a, y_b = [], []
    y_ab: dict[str, list] = {n: [] for n in names}
    for e in evs:
        tag = e.get("tag") or e.get("matrix")
        mets = e.get("metrics") or {}
        val = mets.get(metric)
        if tag == "A":
            y_a.append(val if _finite(val) else float("nan"))
        elif tag == "B":
            y_b.append(val if _finite(val) else float("nan"))
        elif isinstance(tag, str) and tag.startswith("AB_"):
            fac = e.get("factor") or tag[3:]
            if fac in y_ab:
                y_ab[fac].append(val if _finite(val) else float("nan"))
        elif e.get("factor") in y_ab:
            y_ab[e["factor"]].append(val if _finite(val) else float("nan"))
    return sobol_indices(y_a, y_b, y_ab, names=names, bootstrap=bootstrap, seed=seed, conf=conf)


def ishigami(x1, x2, x3, a: float = 7.0, b: float = 0.1) -> float:
    """Ishigami–Homma test function (Saltelli Primer); Xi ~ U(-π, π)."""
    return math.sin(x1) + a * math.sin(x2) ** 2 + b * x3 ** 4 * math.sin(x1)


# Analytical Sobol indices for Ishigami a=7, b=0.1 (Saltelli Primer / Homma & Saltelli 1996)
ISHIGAMI_ANALYTIC = {
    "S1": {"x1": 0.3139, "x2": 0.4424, "x3": 0.0},
    "ST": {"x1": 0.5576, "x2": 0.4424, "x3": 0.2437},
}


def sobol_pipeline(
    mission_path: str,
    variables: list[dict],
    *,
    n: int = 32,
    seed: int = 0,
    metric: str = "W0_kg",
    no_systems: bool = True,
    handbook: bool = True,
    bootstrap: int = 0,
    conf: float = 0.95,
    rel_span: float = 0.10,
) -> dict[str, Any]:
    """Saltelli–Sobol on handbook ``run_pipeline`` (same evaluator as OAT P7).

    ``variables``: ``[{path, low?, high?, rel_span?}]``. Missing low/high →
    nominal±rel_span from the mission YAML. Degenerate / non-converged → unassessed.
    """
    import copy
    from pathlib import Path

    import yaml

    from .oat import _get_path, _num, _set_path, extract_metrics

    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec

    raw = yaml.safe_load(Path(mission_path).read_text(encoding="utf-8"))
    bounds = []
    for v in variables:
        path = v["path"]
        cur = _get_path(raw, path)
        if isinstance(cur, dict):
            for k in ("target", "min", "max", "value"):
                if k in cur and _num(cur[k]) is not None:
                    cur = cur[k]
                    break
        x0 = _num(cur)
        if "low" in v and "high" in v:
            lo, hi = float(v["low"]), float(v["high"])
        elif x0 is None or x0 == 0:
            return {
                "status": "unassessed",
                "reason": f"cannot form range for '{path}' (missing/zero nominal)",
                "indices": [],
                "reference": REF,
            }
        else:
            span = float(v.get("rel_span", rel_span))
            lo, hi = x0 * (1 - span), x0 * (1 + span)
            if hi <= lo:
                return {
                    "status": "unassessed",
                    "reason": f"degenerate range for '{path}'",
                    "indices": [],
                    "reference": REF,
                }
        bounds.append({"name": path, "low": lo, "high": hi})

    def run_point(values: dict[str, float]) -> float | None:
        dd = copy.deepcopy(raw)
        if handbook:
            dd.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
        for pth, val in values.items():
            _set_path(dd, pth, float(val))
        try:
            spec = MissionSpec.from_dict(dd)
            st = run_pipeline("aircraft", spec, no_systems=no_systems)
            res = st["result"]
            if not res.sizing.converged:
                return None
            m = extract_metrics(res)
            return m.get(metric)
        except Exception:
            return None

    out = sobol_analyze(bounds, run_point, n=n, seed=seed, bootstrap=bootstrap, conf=conf)
    out["mission"] = str(mission_path)
    out["metric"] = metric
    out["options"] = {"no_systems": no_systems, "handbook": handbook, "rel_span": rel_span}
    # fidelity hints from ST ranking (reuse OAT discipline map)
    from .oat import DISCIPLINE_HINTS
    hints = []
    for r in out.get("ranking_ST") or []:
        if r.get("status") != "ok":
            continue
        if abs(r["ST"]) < 0.05:
            continue
        var = r["variable"]
        disc, action = DISCIPLINE_HINTS.get(var, ("unknown", "rever modelo / subir um nível"))
        hints.append({
            "variable": var, "metric": metric, "ST": r["ST"], "S1": r["S1"],
            "discipline": disc, "suggest": action,
            "reason": f"ST={r['ST']:.3f} on {metric} (Sobol total-effect)",
        })
    out["fidelity_hints"] = hints
    return out
