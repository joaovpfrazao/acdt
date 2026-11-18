"""Toolkit wrappers for P7 sensitivity / fidelity-by-need."""
from __future__ import annotations

from typing import Any

from acdt.core.sensitivity import (
    oat_from_samples, oat_pipeline, uncertainty_band,
    sobol_analyze, sobol_from_evaluations, sobol_pipeline,
    monte_carlo, monte_carlo_pipeline,
)


def sensitivity_from_samples(baseline: dict, samples: list[dict], threshold: float = 0.5) -> dict:
    return oat_from_samples(baseline, samples, threshold=threshold)


def sensitivity_pipeline(mission: str, variables: list[dict], rel_step: float = 0.05,
                         no_systems: bool = True, handbook: bool = True,
                         threshold: float = 0.5, output: str | None = None) -> dict:
    return oat_pipeline(mission, variables, rel_step=rel_step, no_systems=no_systems,
                        handbook=handbook, threshold=threshold, output_dir=output)


def sensitivity_uncertainty(baseline: dict, bands: list[dict],
                            table: dict[str, dict[str, float]]) -> dict:
    """``table`` maps parameter name → {low_metrics…} and we rebuild evaluate from hi/lo pairs.

    Prefer passing precomputed ``samples`` via ``sensitivity_from_samples``. This helper expects
    ``table[name] = {"low": metrics, "high": metrics}`` for each band.
    """
    def evaluate(point: dict[str, float]) -> dict[str, float]:
        # point has one key; pick low or high by comparing to nominal
        name, val = next(iter(point.items()))
        band = next(b for b in bands if b["name"] == name)
        nom = float(band["nominal"])
        side = "low" if val < nom else "high"
        return table[name][side]

    return uncertainty_band(baseline, bands, evaluate)


def sensitivity_sobol(bounds: list[dict] | None = None,
                      evaluate_table: dict | None = None,
                      *,
                      n: int = 64,
                      seed: int = 0,
                      bootstrap: int = 0,
                      conf: float = 0.95,
                      mission: str | None = None,
                      variables: list[dict] | None = None,
                      metric: str = "W0_kg",
                      no_systems: bool = True,
                      handbook: bool = True,
                      rel_span: float = 0.10) -> dict[str, Any]:
    """Opt-in Sobol' global SA (Saltelli/Jansen). OAT paths unchanged when this is not called.

    Modes:
    * ``evaluate_table`` with Y_A/Y_B/Y_AB (or evaluations+metric) → indices only
    * ``mission`` + ``variables`` → handbook Saltelli pipeline (same evaluator as OAT)
    * ``bounds`` + callable not exposed here — use core ``sobol_analyze`` for custom models
    """
    if evaluate_table is not None:
        return sobol_from_evaluations(evaluate_table, bootstrap=bootstrap, seed=seed, conf=conf)
    if mission and variables is not None:
        return sobol_pipeline(
            mission, variables, n=n, seed=seed, metric=metric,
            no_systems=no_systems, handbook=handbook,
            bootstrap=bootstrap, conf=conf, rel_span=rel_span,
        )
    if bounds is not None and evaluate_table is None and not mission:
        return {
            "status": "unassessed",
            "reason": "bounds without evaluate_table or mission — provide Y_A/Y_B/Y_AB or mission+variables",
            "indices": [],
        }
    return {
        "status": "unassessed",
        "reason": "need evaluate_table (Y_A/Y_B/Y_AB) or mission+variables",
        "indices": [],
    }



def sensitivity_mc(inputs: list[dict] | None = None,
                   *,
                   evaluate_table: dict | None = None,
                   mission: str | None = None,
                   n: int = 64,
                   method: str = "lhs",
                   seed: int = 0,
                   percentiles: list[float] | None = None,
                   metric_keys: list[str] | None = None,
                   no_systems: bool = True,
                   handbook: bool = True) -> dict:
    """Opt-in Monte Carlo / LHS UQ. OAT/Sobol unchanged when this is not called.

    * ``mission`` + ``inputs`` → handbook pipeline propagation
    * ``evaluate_table`` with precomputed ``samples``: [{inputs, metrics}] → summarize only
    """
    if evaluate_table is not None and "samples" in evaluate_table:
        # summarize precomputed successful samples
        import math
        percentiles = list(percentiles or evaluate_table.get("percentiles") or [5, 50, 95])
        series: dict[str, list[float]] = {}
        failed = 0
        n_tot = 0
        for s in evaluate_table["samples"]:
            n_tot += 1
            mets = s.get("metrics") if s.get("ok", True) else None
            if not mets:
                failed += 1
                continue
            for mk, mv in mets.items():
                if isinstance(mv, (int, float)) and math.isfinite(float(mv)):
                    if metric_keys and mk not in metric_keys:
                        continue
                    series.setdefault(mk, []).append(float(mv))
        from acdt.core.sensitivity.monte_carlo import _summarize, REF
        summaries, gate_metrics = {}, {}
        for mk, vals in series.items():
            sm = _summarize(vals, percentiles)
            summaries[mk] = sm
            if sm.get("status") == "ok":
                gate_metrics[mk] = sm.get("p50", sm["mean"])
                gate_metrics[f"{mk}_mean"] = sm["mean"]
                gate_metrics[f"{mk}_std"] = sm["std"]
                for p in percentiles:
                    key = f"p{int(p) if float(p).is_integer() else p}"
                    if key in sm:
                        gate_metrics[f"{mk}_{key}"] = sm[key]
        n_ok = n_tot - failed
        status = "ok" if summaries and failed == 0 else (
            "unassessed" if not summaries else "partial"
        )
        if n_ok < 2:
            status = "unassessed"
        out = {
            "kind": "monte_carlo",
            "status": status,
            "n": n_tot,
            "n_ok": n_ok,
            "n_failed": failed,
            "method": evaluate_table.get("method", "precomputed samples"),
            "percentiles": percentiles,
            "summaries": summaries,
            "gate_metrics": gate_metrics,
            "reference": REF,
            "interval_checks": evaluate_table.get("interval_checks"),
        }
        return out
    if mission and inputs is not None:
        return monte_carlo_pipeline(
            mission, inputs, n=n, method=method, seed=seed,
            percentiles=percentiles, metric_keys=metric_keys,
            no_systems=no_systems, handbook=handbook,
        )
    return {
        "kind": "monte_carlo",
        "status": "unassessed",
        "reason": "need mission+inputs or evaluate_table.samples",
        "summaries": {},
        "gate_metrics": {},
    }
