"""W0-vs-cost trade over the low-fidelity MDO model (Phase 7.3).

Grid sweep of (W/S, AR) × discrete structural options (material family for the weight model + material/
process choices per part group). Each point is a converged L0 MDA (the OpenMDAO model of ``mdo``) followed
by the manufacturing study (bottom-up process plan + Eastlake/DAPCA top-down). Points violating a sizing
constraint or with a part that has no feasible, fully specified process are flagged infeasible
(manufacturability as a constraint); the non-dominated feasible set in (W0, unit cost) is returned.
A grid sweep (not a multi-objective optimiser) keeps every point auditable.
"""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from .study import study


def nondominated(pts: list[tuple[float, float]]) -> list[int]:
    """Indices of the points not dominated in (minimise f1, minimise f2)."""
    idx = []
    for i, (a, b) in enumerate(pts):
        if not any((c <= a and d <= b) and (c < a or d < b) for j, (c, d) in enumerate(pts) if j != i):
            idx.append(i)
    return sorted(idx, key=lambda i: pts[i][0])


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def sweep(res, mcfg: dict, options: dict, ws_factors=(0.8, 0.9, 1.0, 1.1, 1.2), AR_values=None,
          cost_metric: str = "bottom_up", out: str | Path | None = None, plot: bool = True,
          feed_mass_change: bool = True) -> dict:
    """``res``: converged baseline DesignResult; ``mcfg``: ``assumptions.manufacturing`` block;
    ``options``: {label: {"weights_material": "metal"|"composite", "manufacturing": {overrides of mcfg}}};
    ``cost_metric``: "bottom_up" | "eastlake" | "dapca4" (unit cost used for the Pareto front);
    ``feed_mass_change``: the structural mass change of the selected materials (Ashby scaling vs the material the
    part was sized in) is added to the weight closure and the MDA re-converged."""
    from ..mdo import AircraftMDO, build_problem, evaluate

    ws0, pw0, AR0 = res.design_point.ws, res.design_point.value, res.config.wing.AR
    AR_values = list(AR_values or [round(AR0 * f, 2) for f in (0.8, 1.0, 1.2)])
    init = {"W0": res.sizing.W0, "We": res.sizing.We, "Wf": res.sizing.Wf, "CD0": res.polar.CD0, "K": res.polar.K,
            "n_lim": res.structures.vn.n_limit_pos if res.structures else 3.8,
            "m_box": res.structures.box.mass if res.structures else 0.1, "S": res.S, "span": res.config.wing.span,
            "E_Wh": (res.sizing.energy_J or 0) / 3600 or res.sizing.Wf, "m_wing": res.sizing.We * 0.15}
    points, notes = [], []
    for label, opt in options.items():
        spec = copy.deepcopy(res.spec)
        comp = spec.assumptions["weights"].setdefault("components", {})
        if opt.get("weights_material"):
            comp["material"] = opt["weights_material"]
        model = AircraftMDO(spec, None, None)  # handbook aero (no low-fi calibration) — consistent across options
        prob, gkeys = build_problem(model, {"ws": ws0, "pw": pw0, "AR": AR0}, "W0", "nlbgs", ("ws", "AR"),
                                    {"ws": (0.3 * ws0, 3 * ws0), "AR": (2.0, 40.0)}, None, 60, 1e-6, init)
        mc = _merge(mcfg, opt.get("manufacturing") or {})
        for f in ws_factors:
            for AR in AR_values:
                ws = ws0 * f
                try:
                    s = evaluate(prob, {"ws": ws, "AR": AR})
                except Exception as e:  # pragma: no cover - solver failure is reported, not hidden
                    notes.append(f"{label} W/S={ws:.0f} AR={AR}: MDA failed ({e})")
                    continue
                # material choice → structural mass change (Ashby scaling of the selected parts) fed back into the
                # weight closure as a fixed mass, re-converged (snowball included); ≤ 4 passes
                fixed0, dm, it = model.fixed, 0.0, 0
                while True:
                    ns = model.namespace(s["W0"], s["Wf"], ws, AR, s["pw"], s["n_lim"], s["CD0"], s["K"],
                                         s["m_box"])
                    ns.power_sl = model.P_sl(s["pw"], s["W0"])
                    st = study(ns, mc, out=None, plots=False)
                    d_new = st["plan"]["mass_change"]["delta_kg"] if feed_mass_change else 0.0
                    if abs(d_new - dm) < 0.05 or it >= 4:
                        break
                    dm, it = d_new, it + 1
                    model.fixed = fixed0 + dm
                    s = evaluate(prob, {"ws": ws, "AR": AR})
                model.fixed = fixed0
                g = {k: s[k] for k in gkeys + ["g_trim"] if k in s}
                viol = [k for k, v in g.items() if v > 1e-3]
                unres = st["plan"]["unresolved_parts"]
                cost = {"bottom_up": st["bottom_up"]["unit_cost"], "eastlake": st["topdown"]["eastlake"]["unit_cost"],
                        "dapca4": st["topdown"]["dapca4"]["unit_cost"]}
                points.append({"option": label, "ws": ws, "AR": AR, "pw": s["pw"], "W0": s["W0"], "We": s["We"],
                               "structure_mass_change_kg": dm,
                               "unit_cost": cost[cost_metric], "costs": cost, "violated": viol,
                               "unresolved_parts": sorted(unres), "feasible": not viol and not unres,
                               "selection": st["plan"]["selection"]})
    feas = [p for p in points if p["feasible"]]
    front = [feas[i] for i in nondominated([(p["W0"], p["unit_cost"]) for p in feas])]
    r = {"cost_metric": cost_metric, "N": mcfg.get("N"), "year": mcfg.get("year"), "points": points,
         "pareto": front, "notes": notes + [
             "L0 handbook-aero MDA per point (no low-fi calibration); cost from the manufacturing study at N",
             "material choice → structural mass change (Ashby) fed back into the W0 closure"
             + ("" if feed_mass_change else " — DISABLED"),
             "infeasible = a sizing constraint violated (g > 0) or a part without a feasible, fully specified "
             "process"]}
    if out is not None and plot:
        r["plot"] = str(plot_pareto(r, Path(out)))
    return r


def plot_pareto(r: dict, out: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = sorted({p["option"] for p in r["points"]})
    cols = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    for i, lab in enumerate(labels):
        P = [p for p in r["points"] if p["option"] == lab]
        f = [p for p in P if p["feasible"]]
        x = [p for p in P if not p["feasible"]]
        ax.scatter([p["W0"] for p in f], [p["unit_cost"] / 1e3 for p in f], color=cols[i % 10], label=lab, s=28)
        if x:
            ax.scatter([p["W0"] for p in x], [p["unit_cost"] / 1e3 for p in x], color=cols[i % 10], marker="x",
                       s=28, alpha=0.6, label=f"{lab} (inviável)")
    fr = r["pareto"]
    if fr:
        ax.plot([p["W0"] for p in fr], [p["unit_cost"] / 1e3 for p in fr], "k--", lw=1.2, label="frente de Pareto")
    ax.set_xlabel("W0 [kg]")
    ax.set_ylabel(f"custo unitário ({r['cost_metric']}) [k USD {r.get('year')}]")
    ax.set_title(f"W0 vs custo unitário, N = {r.get('N')}")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = out / "pareto_w0_cost.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p
