"""Monte Carlo / Latin-hypercube uncertainty propagation (P7).

Propagate supplied input distributions through a scalar/vector evaluator and
report mean, spread and percentiles. Sampling: i.i.d. Monte Carlo or Latin
hypercube (McKay et al. 1979; Helton & Davis 2003). Saltelli Primer 2008
covers the same UQ sampling context.

Missing distributions, degenerate ranges, or all-failed evaluations →
``unassessed`` (never a silent zero uncertainty that looks like "no risk").
Partial failures → ``partial`` with ``n_failed`` recorded.

No GPL in-process; numpy only. No heavy hi-fi — callers pass the existing
handbook/size evaluators (same as OAT/Sobol P7).
"""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

REF = (
    "McKay, Beckman & Conover, Technometrics 21 (1979) 239–245 (LHS); "
    "Helton & Davis, Reliab. Eng. Syst. Saf. 81 (2003) 23–69 (LHS for UQ); "
    "Saltelli et al., Global Sensitivity Analysis. The Primer, Wiley 2008; "
    "DESIGN_WORKFLOW §5"
)

_EPS = 1e-15


def _lhs_unit(n: int, k: int, rng: np.random.Generator) -> np.ndarray:
    """Latin hypercube in (0,1)^k (McKay et al. 1979)."""
    u = np.empty((n, k), dtype=float)
    for j in range(k):
        perm = rng.permutation(n)
        u[:, j] = (perm + rng.random(n)) / n
    return u


def _norm_ppf(p: np.ndarray) -> np.ndarray:
    """Approximate standard-normal PPF (Acklam) — no scipy required."""
    # Peter J. Acklam's algorithm (public domain)
    p = np.asarray(p, dtype=float)
    a = [ -3.969683028665376e+01,  2.209460984245205e+02,
          -2.759285104469687e+02,  1.383577518672690e+02,
          -3.066479806614716e+01,  2.506628277459239e+00 ]
    b = [ -5.447609879822406e+01,  1.615858368580409e+02,
          -1.556989798598866e+02,  6.680131188771972e+01,
          -1.328068155288572e+01 ]
    c = [ -7.784894002430293e-03, -3.223964580411365e-01,
          -2.400758277161838e+00, -2.549732539343734e+00,
           4.374664141464968e+00,  2.938163982698783e+00 ]
    d = [  7.784695709041462e-03,  3.224671290700398e-01,
           2.445134137142996e+00,  3.754408661907416e+00 ]
    plow = 0.02425
    phigh = 1 - plow
    x = np.empty_like(p)
    # lower
    mask = p < plow
    if np.any(mask):
        q = np.sqrt(-2 * np.log(p[mask]))
        x[mask] = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                  ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    # central
    mask = (p >= plow) & (p <= phigh)
    if np.any(mask):
        q = p[mask] - 0.5
        r = q * q
        x[mask] = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5]) * q / \
                  (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    # upper
    mask = p > phigh
    if np.any(mask):
        q = np.sqrt(-2 * np.log(1 - p[mask]))
        x[mask] = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                   ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    return x


def _transform(u: np.ndarray, spec: dict) -> np.ndarray:
    """Map unit-cube column to physical samples per distribution spec."""
    dist = (spec.get("dist") or spec.get("distribution") or "uniform").lower()
    if dist in ("uniform", "u"):
        lo, hi = float(spec["low"]), float(spec["high"])
        if hi <= lo:
            raise ValueError(f"degenerate uniform range for '{spec.get('name')}': [{lo},{hi}]")
        return lo + u * (hi - lo)
    if dist in ("triangular", "triang", "tri"):
        lo, hi = float(spec["low"]), float(spec["high"])
        mode = float(spec.get("mode", spec.get("c", 0.5 * (lo + hi))))
        if not (lo <= mode <= hi) or hi <= lo:
            raise ValueError(f"degenerate triangular for '{spec.get('name')}'")
        fc = (mode - lo) / (hi - lo)
        out = np.empty_like(u)
        left = u < fc
        out[left] = lo + np.sqrt(u[left] * (hi - lo) * (mode - lo))
        out[~left] = hi - np.sqrt((1 - u[~left]) * (hi - lo) * (hi - mode))
        return out
    if dist in ("normal", "gauss", "gaussian"):
        mu = float(spec.get("mean", spec.get("mu", 0.0)))
        sig = float(spec.get("std", spec.get("sigma", 1.0)))
        if sig <= 0:
            raise ValueError(f"normal std must be >0 for '{spec.get('name')}'")
        # avoid 0/1 endpoints
        uu = np.clip(u, 1e-12, 1 - 1e-12)
        x = mu + sig * _norm_ppf(uu)
        if "low" in spec:
            x = np.maximum(x, float(spec["low"]))
        if "high" in spec:
            x = np.minimum(x, float(spec["high"]))
        return x
    raise ValueError(f"unsupported dist '{dist}' (use uniform|triangular|normal)")


def draw_sample(
    inputs: list[dict],
    n: int,
    *,
    method: str = "lhs",
    seed: int = 0,
) -> dict[str, Any]:
    """Draw N samples for each input. ``method``: ``lhs`` (default) or ``mc``."""
    if n < 2:
        raise ValueError("N must be >= 2 for UQ percentiles")
    if not inputs:
        raise ValueError("inputs required: [{name, dist, …}]")
    names = []
    for s in inputs:
        if "name" not in s:
            raise ValueError("each input needs 'name'")
        names.append(s["name"])
    k = len(names)
    rng = np.random.default_rng(seed)
    method = (method or "lhs").lower()
    if method in ("lhs", "latin", "latin_hypercube"):
        u = _lhs_unit(n, k, rng)
        method_label = "LHS (McKay et al. 1979; Helton & Davis 2003)"
    elif method in ("mc", "montecarlo", "monte_carlo", "iid"):
        u = rng.random((n, k))
        method_label = "i.i.d. Monte Carlo"
    else:
        raise ValueError(f"method must be lhs|mc, got {method}")
    cols = {}
    for j, spec in enumerate(inputs):
        cols[names[j]] = _transform(u[:, j], spec)
    rows = [{names[j]: float(cols[names[j]][i]) for j in range(k)} for i in range(n)]
    return {
        "names": names,
        "n": n,
        "method": method_label,
        "method_key": "lhs" if method.startswith("l") else "mc",
        "seed": seed,
        "inputs": inputs,
        "rows": rows,
        "reference": REF,
    }


def _summarize(values: list[float], percentiles: list[float]) -> dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return {
            "status": "unassessed",
            "reason": "fewer than 2 finite samples — uncertainty undefined (not zero)",
            "n": int(arr.size),
        }
    out: dict[str, Any] = {
        "status": "ok",
        "n": int(arr.size),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "spread": float(np.max(arr) - np.min(arr)),
    }
    for p in percentiles:
        out[f"p{int(p) if float(p).is_integer() else p}"] = float(np.percentile(arr, p))
    return out


def monte_carlo(
    inputs: list[dict],
    evaluate: Callable[[dict[str, float]], dict[str, float] | float | None],
    *,
    n: int = 64,
    method: str = "lhs",
    seed: int = 0,
    percentiles: list[float] | None = None,
    metrics: list[str] | None = None,
) -> dict[str, Any]:
    """Propagate input distributions; return per-metric summaries + gate_metrics flat map.

    ``evaluate(point)`` → ``{metric: float}`` or a single float (named ``Y``).
    Returning None / non-finite → failed sample (counted, not treated as zero).
    """
    percentiles = list(percentiles or [5, 50, 95])
    try:
        design = draw_sample(inputs, n, method=method, seed=seed)
    except ValueError as ex:
        return {
            "kind": "monte_carlo",
            "status": "unassessed",
            "reason": str(ex),
            "summaries": {},
            "gate_metrics": {},
            "reference": REF,
        }

    series: dict[str, list[float]] = {}
    failed = 0
    samples_out = []
    for row in design["rows"]:
        try:
            y = evaluate(row)
        except Exception:
            y = None
        if y is None:
            failed += 1
            samples_out.append({"inputs": row, "metrics": None, "ok": False})
            continue
        if isinstance(y, (int, float)):
            if not math.isfinite(float(y)):
                failed += 1
                samples_out.append({"inputs": row, "metrics": None, "ok": False})
                continue
            y = {"Y": float(y)}
        if not isinstance(y, dict) or not y:
            failed += 1
            samples_out.append({"inputs": row, "metrics": None, "ok": False})
            continue
        clean = {}
        for mk, mv in y.items():
            if metrics and mk not in metrics:
                continue
            if isinstance(mv, (int, float)) and math.isfinite(float(mv)):
                clean[mk] = float(mv)
                series.setdefault(mk, []).append(float(mv))
        if not clean:
            failed += 1
            samples_out.append({"inputs": row, "metrics": None, "ok": False})
            continue
        samples_out.append({"inputs": row, "metrics": clean, "ok": True})

    n_ok = n - failed
    if n_ok < 2:
        return {
            "kind": "monte_carlo",
            "status": "unassessed",
            "reason": f"only {n_ok} successful evaluations of {n} — cannot form percentiles",
            "n": n,
            "n_ok": n_ok,
            "n_failed": failed,
            "method": design["method"],
            "summaries": {},
            "gate_metrics": {},
            "reference": REF,
        }

    summaries = {}
    gate_metrics: dict[str, float] = {}
    any_ok = False
    any_un = False
    for mk, vals in series.items():
        sm = _summarize(vals, percentiles)
        summaries[mk] = sm
        if sm["status"] != "ok":
            any_un = True
            continue
        any_ok = True
        # flat map for decisions gate conditions
        gate_metrics[mk] = sm.get("p50", sm["mean"])
        gate_metrics[f"{mk}_mean"] = sm["mean"]
        gate_metrics[f"{mk}_std"] = sm["std"]
        for p in percentiles:
            key = f"p{int(p) if float(p).is_integer() else p}"
            if key in sm:
                gate_metrics[f"{mk}_{key}"] = sm[key]

    status = "ok" if any_ok and not any_un and failed == 0 else (
        "unassessed" if not any_ok else "partial"
    )
    return {
        "kind": "monte_carlo",
        "status": status,
        "n": n,
        "n_ok": n_ok,
        "n_failed": failed,
        "method": design["method"],
        "method_key": design["method_key"],
        "seed": seed,
        "inputs": inputs,
        "percentiles": percentiles,
        "summaries": summaries,
        "gate_metrics": gate_metrics,
        "samples": samples_out if n <= 64 else None,  # keep small runs inspectable
        "reference": REF,
        "note": (
            "gate_metrics uses p50 as the nominal point for each metric; "
            "also exposes {metric}_p5/_p95/_mean/_std for condition/interval checks. "
            "Failed evaluations are excluded — never filled with zero."
        ),
    }


def monte_carlo_pipeline(
    mission_path: str,
    inputs: list[dict],
    *,
    n: int = 32,
    method: str = "lhs",
    seed: int = 0,
    percentiles: list[float] | None = None,
    metric_keys: list[str] | None = None,
    no_systems: bool = True,
    handbook: bool = True,
) -> dict[str, Any]:
    """UQ through handbook ``run_pipeline`` (same evaluator as OAT/Sobol P7)."""
    import copy
    from pathlib import Path

    import yaml

    from .oat import _set_path, extract_metrics
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec

    raw = yaml.safe_load(Path(mission_path).read_text(encoding="utf-8"))

    def evaluate(point: dict[str, float]):
        dd = copy.deepcopy(raw)
        if handbook:
            dd.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
        for path, val in point.items():
            _set_path(dd, path, float(val))
        try:
            spec = MissionSpec.from_dict(dd)
            st = run_pipeline("aircraft", spec, no_systems=no_systems)
            res = st["result"]
            if not res.sizing.converged:
                return None
            m = extract_metrics(res)
            if metric_keys:
                m = {k: m[k] for k in metric_keys if k in m}
            return m or None
        except Exception:
            return None

    out = monte_carlo(
        inputs, evaluate, n=n, method=method, seed=seed,
        percentiles=percentiles, metrics=metric_keys,
    )
    out["mission"] = str(mission_path)
    out["options"] = {"no_systems": no_systems, "handbook": handbook}
    return out


def uq_interval_checks(
    uq: dict,
    checks: list[dict],
) -> list[dict]:
    """Turn UQ percentile bounds into gate check rows [{key, ok, message}].

    Each check: ``{metric, op, value, use: p5|p50|p95|mean, key?}``.
    Missing summary → ``ok: None`` (unassessed), never pass.
    """
    summaries = (uq or {}).get("summaries") or {}
    rows = []
    for c in checks or []:
        metric = c.get("metric")
        use = c.get("use", "p95")
        op = c.get("op", "<=")
        key = c.get("key") or f"uq:{metric}:{use}"
        sm = summaries.get(metric) if metric else None
        if not sm or sm.get("status") != "ok" or use not in sm:
            rows.append({
                "key": key, "ok": None,
                "message": f"UQ {metric}.{use} unassessed — missing summary ≠ pass",
            })
            continue
        val = float(sm[use])
        thr = float(c["value"])
        ok = {
            "<": val < thr, "<=": val <= thr,
            ">": val > thr, ">=": val >= thr,
            "==": val == thr, "!=": val != thr,
        }.get(op)
        if ok is None:
            rows.append({"key": key, "ok": None, "message": f"bad op {op}"})
            continue
        rows.append({
            "key": key, "ok": bool(ok),
            "message": f"UQ {metric}.{use}={val:g} {op} {thr:g}",
        })
    return rows
