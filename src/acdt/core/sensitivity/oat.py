"""One-at-a-time (OAT) local sensitivity and fidelity-by-need hints.

Finite-difference elasticities ε = (Δy/y) / (Δx/x) of mission metrics w.r.t. design
variables and model parameters. High |ε| → raise fidelity / spend effort there
(DESIGN_WORKFLOW §5).

References: Saltelli et al., *Global Sensitivity Analysis. The Primer*, Wiley 2008
(OAT / elementary effects as a screening step); DESIGN_WORKFLOW §5 (fidelity by need).
"""
from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Callable

import yaml

REF = ("Saltelli et al., Global Sensitivity Analysis. The Primer, Wiley 2008 (OAT screening); "
       "DESIGN_WORKFLOW §5 (subir fidelidade onde a sensibilidade da decisão é alta)")

# Map dotted variable paths → discipline hint for fidelity upgrade
DISCIPLINE_HINTS = {
    "assumptions.aero.AR": ("aerodynamics", "L1 lowfi XFOIL/AVL ou N2 OAS"),
    "assumptions.aero.taper": ("aerodynamics", "L1 AVL load / N2 shape"),
    "assumptions.aero.tc_root": ("aerodynamics/structures", "XFOIL polar + wingbox"),
    "assumptions.aero.cfe": ("aerodynamics", "build-up / RANS profile drag"),
    "assumptions.aero.swet_sref": ("aerodynamics/geometry", "CAD molhada / OpenVSP"),
    "assumptions.aero.clmax_airfoil": ("aerodynamics", "XFOIL/CFD high-lift"),
    "assumptions.propulsion.battery_Wh_kg": ("energy", "datasheet célula + overhead medido"),
    "assumptions.propulsion.eta_total": ("propulsion", "BEMT / banco de motor"),
    "assumptions.propulsion.systems_power_W": ("systems", "electrical_analyse + payload catalog"),
    "assumptions.weights.components.growth_allowance": ("weights", "BOM L1 / massas medidas"),
    "requirements.payload_mass": ("mission/payload", "payload_trade + packaging"),
    "requirements.endurance": ("mission", "simulate pointmass judge"),
    "requirements.cruise_speed": ("mission/aero", "polar L1 + mission sim"),
    "CD0": ("aerodynamics", "lowfi polar / RANS"),
    "e_oswald": ("aerodynamics", "AVL / OAS induced"),
    "battery_Wh_kg": ("energy", "datasheet"),
}


def _get_path(d: dict, path: str):
    cur: Any = d
    for p in path.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def _set_path(d: dict, path: str, value) -> None:
    parts = path.split(".")
    cur = d
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    leaf = parts[-1]
    # requirement style {min|max|target: v, unit: …}
    if isinstance(cur.get(leaf), dict) and any(k in cur[leaf] for k in ("min", "max", "target", "value")):
        node = cur[leaf]
        for k in ("target", "min", "max", "value"):
            if k in node:
                node[k] = value
                return
    cur[leaf] = value


def _num(x) -> float | None:
    if isinstance(x, bool) or x is None:
        return None
    if isinstance(x, (int, float)) and math.isfinite(float(x)):
        return float(x)
    return None


def extract_metrics(result) -> dict[str, float]:
    """Pull a flat mission-metric dict from a DesignResult."""
    m: dict[str, float] = {}
    sz = result.sizing
    if sz and sz.W0 and math.isfinite(sz.W0):
        m["W0_kg"] = float(sz.W0)
    if sz and sz.We and math.isfinite(sz.We):
        m["We_kg"] = float(sz.We)
    if sz and getattr(sz, "energy_J", None) and sz.energy_J and math.isfinite(sz.energy_J):
        m["E_Wh"] = float(sz.energy_J) / 3600.0
    if sz and sz.Wf is not None and math.isfinite(sz.Wf):
        m["Wf_kg"] = float(sz.Wf)
    if result.polar is not None:
        if result.polar.CD0 is not None:
            m["CD0"] = float(result.polar.CD0)
        k = getattr(result.polar, "K", None) or getattr(result.polar, "k", None)
        if k is not None and math.isfinite(k):
            m["K"] = float(k)
    if result.cruise_speed is not None and math.isfinite(result.cruise_speed):
        m["V_cruise_mps"] = float(result.cruise_speed)
    if result.S is not None and math.isfinite(result.S):
        m["S_m2"] = float(result.S)
    if result.design_point is not None and result.design_point.ws is not None:
        m["ws_Pa"] = float(result.design_point.ws)
    # legs: endurance / range if present
    legs = getattr(sz, "legs", None) or {}
    if isinstance(legs, dict):
        for key in ("endurance_h", "range_m", "range_km"):
            if key in legs and _num(legs[key]) is not None:
                m[key] = float(legs[key])
    return m


def elasticities(baseline: dict[str, float], samples: list[dict]) -> dict[str, Any]:
    """Compute elasticities from OAT samples.

    Each sample: ``{variable, x0, x1, metrics: {…}}`` (one variable perturbed).
    Returns per-variable, per-metric ε and |ε| ranking.
    """
    rows = []
    for s in samples:
        var = s["variable"]
        x0, x1 = float(s["x0"]), float(s["x1"])
        if x0 == 0 or x1 == x0:
            continue
        dx_rel = (x1 - x0) / x0
        met = s.get("metrics") or {}
        for mk, y1 in met.items():
            y0 = baseline.get(mk)
            y0n, y1n = _num(y0), _num(y1)
            if y0n is None or y1n is None or y0n == 0:
                continue
            eps = ((y1n - y0n) / y0n) / dx_rel
            rows.append({
                "variable": var, "metric": mk, "x0": x0, "x1": x1,
                "y0": y0n, "y1": y1n, "elasticity": eps, "abs_elasticity": abs(eps),
            })
    ranking = sorted(rows, key=lambda r: -r["abs_elasticity"])
    by_var: dict[str, list] = {}
    for r in ranking:
        by_var.setdefault(r["variable"], []).append(r)
    return {
        "baseline": baseline,
        "rows": ranking,
        "by_variable": by_var,
        "top": ranking[:12],
        "reference": REF,
        "note": "elasticidade local OAT ε=(Δy/y)/(Δx/x); válida na vizinhança do ponto",
    }


def fidelity_hints(elasticity_result: dict, threshold: float = 0.5) -> list[dict]:
    """Suggest where to raise fidelity when |ε| ≥ threshold."""
    tips = []
    seen = set()
    for r in elasticity_result.get("rows") or []:
        if r["abs_elasticity"] < threshold:
            continue
        var = r["variable"]
        if var in seen:
            continue
        seen.add(var)
        disc, action = DISCIPLINE_HINTS.get(var, ("unknown", "rever modelo / subir um nível"))
        tips.append({
            "variable": var,
            "metric": r["metric"],
            "abs_elasticity": r["abs_elasticity"],
            "discipline": disc,
            "suggest": action,
            "reason": f"|ε|={r['abs_elasticity']:.2f} de {r['metric']} vs {var} ≥ {threshold}",
        })
    return tips


def oat_from_samples(baseline: dict[str, float], samples: list[dict],
                     threshold: float = 0.5) -> dict[str, Any]:
    el = elasticities(baseline, samples)
    el["fidelity_hints"] = fidelity_hints(el, threshold=threshold)
    el["threshold"] = threshold
    return el


def uncertainty_band(baseline: dict[str, float],
                     bands: list[dict],
                     evaluate: Callable[[dict[str, float]], dict[str, float]]) -> dict[str, Any]:
    """Propagate ±pct model-parameter bands one-at-a-time through ``evaluate``.

    ``bands``: ``[{name, nominal, pct}]`` e.g. ``{name: CD0, nominal: 0.025, pct: 15}``.
    """
    out_rows = []
    for b in bands:
        name, nom, pct = b["name"], float(b["nominal"]), float(b["pct"])
        lo, hi = nom * (1 - pct / 100), nom * (1 + pct / 100)
        m_lo = evaluate({name: lo})
        m_hi = evaluate({name: hi})
        for mk in set(baseline) | set(m_lo) | set(m_hi):
            y0, a, c = _num(baseline.get(mk)), _num(m_lo.get(mk)), _num(m_hi.get(mk))
            if y0 is None or a is None or c is None:
                continue
            out_rows.append({
                "parameter": name, "metric": mk, "nominal": y0,
                "low": min(a, c), "high": max(a, c),
                "span": abs(c - a), "span_pct": abs(c - a) / abs(y0) * 100 if y0 else None,
                "pct_input": pct,
            })
    ranking = sorted(out_rows, key=lambda r: -(r["span_pct"] or 0))
    return {
        "baseline": baseline,
        "rows": ranking,
        "top": ranking[:12],
        "fidelity_hints": fidelity_hints(
            {"rows": [{"variable": r["parameter"], "metric": r["metric"],
                       "abs_elasticity": (r["span_pct"] or 0) / max(r["pct_input"], 1e-9),
                       "elasticity": 0.0} for r in ranking]},
            threshold=0.5,
        ),
        "reference": REF,
        "note": "banda OAT ±pct; span_pct alto → incerteza do parâmetro mexe na decisão",
    }


def oat_pipeline(mission_path: str | Path,
                 variables: list[dict],
                 *,
                 rel_step: float = 0.05,
                 no_systems: bool = True,
                 handbook: bool = True,
                 metrics_keys: list[str] | None = None,
                 threshold: float = 0.5,
                 output_dir: str | Path | None = None) -> dict[str, Any]:
    """OAT on a mission YAML via ``run_pipeline`` (handbook + no_systems by default).

    ``variables``: ``[{path: "assumptions.aero.AR", rel_step?: 0.05}]`` or absolute
    ``{path, values: [..]}``.
    """
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec

    raw = yaml.safe_load(Path(mission_path).read_text(encoding="utf-8"))

    def run_dict(d: dict) -> dict[str, float]:
        dd = copy.deepcopy(d)
        if handbook:
            dd.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
        spec = MissionSpec.from_dict(dd)
        st = run_pipeline("aircraft", spec, no_systems=no_systems)
        res = st["result"]
        if not res.sizing.converged:
            return {"_converged": 0.0}
        m = extract_metrics(res)
        m["_converged"] = 1.0
        if metrics_keys:
            m = {k: m[k] for k in metrics_keys if k in m}
        return m

    baseline = run_dict(raw)
    samples = []
    for v in variables:
        path = v["path"]
        cur = _get_path(raw, path)
        # unwrap requirement dict
        if isinstance(cur, dict):
            for k in ("target", "min", "max", "value"):
                if k in cur and _num(cur[k]) is not None:
                    cur = cur[k]
                    break
        x0 = _num(cur)
        if x0 is None:
            samples.append({"variable": path, "error": f"caminho sem número: {path}",
                            "x0": None, "x1": None, "metrics": {}})
            continue
        step = float(v.get("rel_step", rel_step))
        values = v.get("values") or [x0 * (1 + step)]
        for x1 in values:
            d2 = copy.deepcopy(raw)
            _set_path(d2, path, float(x1))
            met = run_dict(d2)
            samples.append({"variable": path, "x0": x0, "x1": float(x1), "metrics": met})

    result = oat_from_samples(
        {k: v for k, v in baseline.items() if k != "_converged"},
        [{**s, "metrics": {k: v for k, v in (s.get("metrics") or {}).items() if k != "_converged"}}
         for s in samples if s.get("x0") is not None],
        threshold=threshold,
    )
    result["mission"] = str(mission_path)
    result["variables"] = variables
    result["rel_step"] = rel_step
    result["options"] = {"no_systems": no_systems, "handbook": handbook}
    result["samples"] = samples
    result["baseline_raw"] = baseline
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "sensitivity.json").write_text(
            __import__("json").dumps(result, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8")
        result["files"] = {"sensitivity.json": str(out / "sensitivity.json")}
    return result
