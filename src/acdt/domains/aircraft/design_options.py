"""Fase 9 — discrete design OPTIONS evaluated by the sizing/optimisation chain (here: wing trailing-edge devices).

Design principle: a device such as a camber flap is never imposed. Every option is sized through the same
MDA (constraint diagram + mission + component weights + cost, :func:`.sizing.run`), optionally re-optimised
(OpenMDAO, :func:`.mdo.optimize`), and the option is *selected only if it beats the best alternative by more
than* ``min_gain`` on the objective (default 1 %, PRESSUPOSTO: below the resolution of conceptual methods a
more complex system is not justified — Raymer Sec. 19.1 "trade studies"). The report always gives the delta
of every option against the best alternative.

Options (``assumptions.design_options.flaps.options``):

* ``none``      — clean wing, ailerons only (CLmax clean, Raymer Eq. 12.15);
* ``plain``     — high-lift flap for take-off/landing only (the user's ``aero.flap`` or plain 0.6 S, Raymer
  Table 12.2 / Eq. 12.21), not used in cruise;
* ``camber``    — inboard camber flap scheduled in flight (−10…+15°), ailerons outboard
  (:mod:`.aero.camber_flap`; Thomas 1999; Althaus & Wortmann 1981; Boermans 2006);
* ``flaperon``  — full-span camber flap mixed with the ailerons (one surface per side).

Weights: flap-system items only from user/datasheet values (``actuator_mass_kg``, ``surface_mass_kg_m2``);
cost: modified Eastlake factor F_CF = 1.03 for a complex flap system, 1.0 for simple/none (Gudmundsson 2014
Sec. 2.2.2) — scheduled camber flaps/flaperons are classed as complex (PRESSUPOSTO) — plus actuator unit costs.
"""
from __future__ import annotations

import copy
import math

import numpy as np

from acdt import G0
from acdt.core.atmosphere import isa

FLAP_OPTIONS = ("none", "plain", "camber", "flaperon")
# fixed-geometry (no in-flight camber scheduling) alternatives a camber option must beat
SIMPLE_OPTIONS = ("none", "plain", "plain_same_area", "droop_flaperon")
F_CF = {"none": 1.0, "plain": 1.0, "camber": 1.03, "flaperon": 1.03}


def variant_spec(spec, option: str, cfg: dict | None = None):
    """Copy of ``spec`` with the trailing-edge device ``option``; ``cfg`` = per-option overrides
    (e.g. ``{camber: {chord_ratio: 0.18, actuator_mass_kg: 0.06}}``)."""
    if option not in FLAP_OPTIONS:
        raise ValueError(f"flap option '{option}' unknown ({', '.join(FLAP_OPTIONS)})")
    sp = copy.deepcopy(spec)
    aa = sp.assumptions["aero"]
    over = dict((cfg or {}).get(option) or {})
    user_flap = aa.get("flap") if (aa.get("flap") or {}).get("kind", "none") != "none" else None
    aa["camber_flap"] = None
    if option == "none":
        aa["flap"] = {"kind": "none"}
    elif option == "plain":
        aa["flap"] = {**(user_flap or {"kind": "plain", "flapped_area_ratio": 0.6}), **over}
    else:
        aa["flap"] = {"kind": "none"}
        aa["camber_flap"] = {"kind": option, **over}
    ca = sp.assumptions.setdefault("cost", {})
    if "F_CF" not in (over or {}):
        ca["F_CF"] = F_CF[option]
    return sp


def max_level_speed(m, W: float, h: float) -> float:
    """Highest speed with power (thrust) available ≥ drag at full throttle (Anderson APD Ch. 5)."""
    from .performance import is_propeller
    rho = isa(h).rho
    V = np.linspace(m.stall(W, rho) * 1.1, 150.0, 300)
    D = m.drag(W, V, rho)
    if is_propeller(m.kind):
        excess = m.power_avail(h, m.eta_cruise, V if m.prop is not None else None) - D * V
    else:
        from .performance import lapse
        excess = m.T_sl * lapse(m.kind, isa(h).sigma) - D
    ok = np.where(excess >= 0)[0]
    return float(V[ok[-1]]) if ok.size else math.nan


def _row(option, res, perf=None) -> dict:
    from .performance import PerfModel
    sz = res.sizing
    r = {"option": option, "converged": bool(res.converged), "feasible": bool(res.feasible), "W0": sz.W0,
         "We": sz.We, "Wf_or_battery": sz.Wf, "S": res.S if res.config else math.nan,
         "P_sl_kW": (res.power_sl or math.nan) / 1e3, "W/S": res.design_point.ws,
         "LD_max": res.polar.LD_max, "CL_LDmax": res.polar.CL_LDmax, "CLmax_landing": res.highlift.CLmax_landing,
         "unit_cost": res.cost.unit_cost if getattr(res, "cost", None) else math.nan,
         "active": list(res.design_point.active)}
    from .sizing import LAYOUT_PREFIXES, VERIFICATION_PREFIXES, unit_cost_estimate
    if not math.isfinite(r["unit_cost"]) and res.converged:
        # Eastlake (Gudmundsson 2014) also when the mission has no cost requirement, for the option deltas;
        # flagged as out of calibration range for UAVs
        try:
            r["unit_cost"] = float(unit_cost_estimate(res.spec, sz.We, res.power_sl, res.cruise_speed).unit_cost)
            if res.spec.aircraft_class.startswith("uav"):
                r["unit_cost_note"] = "Eastlake (GA) fora da gama de calibração para UAV — usar só como delta relativo"
        except Exception:  # noqa: BLE001
            pass
    skip = VERIFICATION_PREFIXES + LAYOUT_PREFIXES
    r["failed"] = ([c.key for c in res.checks if c.ok is False and not c.key.startswith(skip)]
                   + [i.message[:90] for i in res.issues if i.severity == "error"]
                   + ([] if res.design_point.feasible else ["design point"]))
    if res.weights is not None:
        r["flap_system_kg"] = sum(i.mass for i in res.weights.items if "flap" in i.name.lower())
    if res.converged and res.config is not None:
        m = PerfModel.from_result(res)
        r["V_max"] = max_level_speed(m, sz.W0 * G0, res.cruise_altitude)
        loit = [L for L in res.legs if L.kind != "cruise"]
        if loit:
            V = loit[0].V
            r["V_loiter"] = V
            r["P_loiter_W"] = float(m.drag(sz.W0 * G0, V, isa(res.cruise_altitude).rho)) * V
    if perf is not None:
        r["endurance_h"] = perf.mission.endurance_s / 3600
        r["range_km"] = perf.mission.range_m / 1e3
    cam = res.polar.camber
    if cam is not None:
        r["camber"] = cam.summary()
    return r


OBJ_SENSE = {"W0": ("W0", 1), "cost": ("unit_cost", 1), "energy": ("Wf_or_battery", 1),
             "endurance": ("endurance_h", -1), "range": ("range_km", -1), "V_max": ("V_max", -1),
             "power": ("P_sl_kW", 1)}


def flap_options_study(spec, options=None, objective: str | None = None, min_gain: float | None = None,
                       per_option: dict | None = None, performance: bool = True) -> dict:
    """Size every option and select one. Returns ``{rows, selected, objective, justified, deltas, notes,
    results}`` (``results`` keeps the DesignResult per option for plots)."""
    from .mdo import objective_from_registry
    from .performance import performance_analysis
    from .sizing import run
    do = (spec.assumptions.get("design_options") or {}).get("flaps") or {}
    options = tuple(options or do.get("options") or FLAP_OPTIONS)   # explicit argument > spec > all
    per_option = per_option or do.get("per_option") or {k: do[k] for k in FLAP_OPTIONS if isinstance(do.get(k), dict)}
    objective = objective or do.get("objective") or objective_from_registry(spec)
    min_gain = do.get("min_gain", 0.01) if min_gain is None else min_gain
    key, sense = OBJ_SENSE[objective]
    rows, results, notes = [], {}, []
    for op in options:
        sp = variant_spec(spec, op, per_option)
        try:
            res = run(sp)
        except Exception as ex:  # noqa: BLE001 — an infeasible option is a result, not a crash
            rows.append({"option": op, "converged": False, "feasible": False, "error": str(ex)})
            continue
        perf = None
        if performance and res.converged:
            try:
                perf = performance_analysis(res)
            except Exception as ex:  # noqa: BLE001
                notes.append(f"{op}: desempenho falhou ({ex})")
        rows.append(_row(op, res, perf))
        results[op] = res
    # fairness: a camber flap must beat a plain flap of the SAME flapped area (otherwise the gain could be
    # just a larger landing flap) → extra alternative "plain_same_area" (Raymer plain flap, same S_flapped/S)
    for cop in ("camber", "flaperon"):
        cam_res = results.get(cop)
        if cam_res is None or cam_res.polar.camber is None or "plain" not in options:
            continue
        ratio = round(cam_res.polar.camber.flapped_area_ratio, 3)
        name = "plain_same_area" if cop == "camber" else "droop_flaperon"
        user_plain = (per_option.get("plain") or {}).get("flapped_area_ratio") or \
            (spec.assumptions["aero"].get("flap") or {}).get("flapped_area_ratio")
        if user_plain is not None and abs(user_plain - ratio) <= 0.02:
            continue
        sp = variant_spec(spec, "plain", {"plain": {**(per_option.get("plain") or {}), "kind": "plain",
                                                     "flapped_area_ratio": ratio}})
        try:
            res = run(sp)
            perf = performance_analysis(res) if (performance and res.converged) else None
            rows.append(_row(name, res, perf))
            results[name] = res
            notes.append(f"{name}: flap simples (Raymer plain) com a mesma área que {cop} (S_flapped/S {ratio:.2f}) — "
                         f"isola o ganho do escalonamento de camber do ganho de área de flap"
                         + ("; flaperon descaído só na aterragem, sem camber em cruzeiro" if cop == "flaperon" else ""))
        except Exception as ex:  # noqa: BLE001
            notes.append(f"{name}: {ex}")
    ok = [r for r in rows if r.get("converged") and r.get("feasible") and math.isfinite(r.get(key, math.nan))]
    if not ok:
        return {"rows": rows, "selected": None, "objective": objective, "justified": False, "deltas": {},
                "notes": notes + ["nenhuma opção viável"], "results": results}

    def score(r):
        return sense * r[key]

    best = min(ok, key=score)
    simple = [r for r in ok if r["option"] in SIMPLE_OPTIONS]
    best_simple = min(simple, key=score) if simple else None
    selected, justified = best["option"], True
    if best["option"] in ("camber", "flaperon") and best_simple is not None:
        gain = (score(best_simple) - score(best)) / abs(best_simple[key])
        if gain < min_gain:
            selected, justified = best_simple["option"], False
            notes.append(f"{best['option']} melhora {objective} só {100 * gain:.2f} % (< {100 * min_gain:.1f} %): "
                         f"não justificado; escolhido {best_simple['option']}")
    sel = next(r for r in ok if r["option"] == selected)
    others = [r for r in ok if r["option"] != selected]
    ref = min(others, key=score) if others else None
    deltas = {}
    for r in ok:
        base = ref if r["option"] == selected else sel
        if base is None:
            continue
        deltas[r["option"]] = {k: (r[k] - base[k]) for k in ("W0", "We", "Wf_or_battery", "S", "P_sl_kW",
                                                             "LD_max", "unit_cost", "V_max", "endurance_h",
                                                             "range_km", "flap_system_kg", "P_loiter_W")
                               if isinstance(r.get(k), float) and isinstance(base.get(k), float)}
        deltas[r["option"]]["vs"] = base["option"]
    return {"rows": rows, "selected": selected, "objective": objective, "objective_key": key,
            "justified": justified, "min_gain": min_gain, "deltas": deltas, "notes": notes, "results": results}


def plot_design_point_shift(study: dict, path, title: str = ""):
    """Constraint-diagram envelopes and design points of each option (design-point shift)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ymax = 0.0
    for k, (op, res) in enumerate(study["results"].items()):
        dp = res.design_point
        if dp.envelope is None or not math.isfinite(dp.ws):
            continue
        y = G0 if dp.metric == "P/W" else 1.0
        c = f"C{k}"
        ax.plot(dp.ws_grid / G0, dp.envelope * y, color=c, lw=1.8, label=f"{op}: envolvente")
        ax.axvline(dp.ws_max / G0, color=c, ls=":", lw=1.2)
        ax.plot(dp.ws / G0, dp.value * y, "*", color=c, ms=15, mec="k", label=f"{op}: W/S {dp.ws / G0:.1f}, "
                f"{'P/W' if dp.metric == 'P/W' else 'T/W'} {dp.value * y:.1f}, W0 {res.sizing.W0:.1f} kg")
        ymax = max(ymax, dp.value * y * 1.5)
    ax.set_ylim(0, ymax or 1)
    ax.set_xlabel("W/S [kg/m²]")
    ax.set_ylabel("P/W [W/kg]" if ymax else "T/W")
    ax.set_title(title or "Deslocamento do ponto de projeto por opção de flap")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def plot_pareto(points: list[dict], xkey: str, ykey: str, path, title: str = "", xlabel: str = "",
                ylabel: str = ""):
    """Scatter of option results (e.g. from a requirement sweep) with the non-dominated front (both minimised
    unless the key is in ``endurance_h``/``range_km``/``V_max``/``dash``, which are maximised)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    mx = {"endurance_h", "range_km", "V_max", "dash", "endurance_req_h", "dash_req"}
    sx, sy = (-1 if xkey in mx else 1), (-1 if ykey in mx else 1)
    pts = [p for p in points if math.isfinite(p.get(xkey, math.nan)) and math.isfinite(p.get(ykey, math.nan))]
    front = [p for p in pts if not any((sx * q[xkey] <= sx * p[xkey] and sy * q[ykey] <= sy * p[ykey])
                                       and (q[xkey] != p[xkey] or q[ykey] != p[ykey]) for q in pts)]
    fig, ax = plt.subplots(figsize=(7.5, 5))
    ops = sorted({p["option"] for p in pts}, key=lambda o: FLAP_OPTIONS.index(o) if o in FLAP_OPTIONS else 9)
    for k, op in enumerate(ops):
        q = sorted([p for p in pts if p["option"] == op], key=lambda p: p[xkey])
        ax.plot([p[xkey] for p in q], [p[ykey] for p in q], "o-", color=f"C{k}", label=op)
    xs = sorted({p[xkey] for p in pts})
    if len(xs) < len(pts):
        # requirement sweep (several options per requirement value): the useful "front" is the best feasible
        # option at each requirement level (lower envelope of the objective), annotated with its name
        f = [min((p for p in pts if p[xkey] == x), key=lambda p: sy * p[ykey]) for x in xs]
        lab = "melhor opção viável por requisito"
    else:
        f, lab = sorted(front, key=lambda p: p[xkey]), "frente não dominada"
    ax.plot([p[xkey] for p in f], [p[ykey] for p in f], "k--", lw=1.6, zorder=5, label=lab)
    ax.scatter([p[xkey] for p in f], [p[ykey] for p in f], s=110, facecolors="none", edgecolors="k", zorder=6)
    if len(xs) < len(pts):
        for p in f:
            ax.annotate(p["option"], (p[xkey], p[ykey]), textcoords="offset points", xytext=(6, -12), fontsize=8)
    ax.set_xlabel(xlabel or xkey)
    ax.set_ylabel(ylabel or ykey)
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def study_summary(study: dict) -> dict:
    """JSON-safe summary (drops DesignResult objects)."""
    return {k: v for k, v in study.items() if k != "results"}


def flap_options_report(spec, out_dir, study: dict | None = None, title: str = "") -> dict:
    """Run (or reuse) the flap-options study and write ``flap_options.json`` + plots: envelope polar and flap
    schedule per camber option (``camber_<option>.png``) and the design-point shift (``design_point_shift.png``)."""
    import json
    from pathlib import Path
    from .aero.camber_flap import plot_camber
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    st = study or flap_options_study(spec)
    files = {}
    for op, res in st["results"].items():
        if res.polar.camber is not None and res.polar.camber.section is not None:
            files[f"camber_{op}"] = str(plot_camber(res.polar.camber, res.polar, out / f"camber_{op}.png",
                                                    f"{title or spec.name} — {op}"))
    if st["results"]:
        files["design_point_shift"] = str(plot_design_point_shift(st, out / "design_point_shift.png",
                                                                  f"{title or spec.name}: ponto de projeto por opção"))
    summ = study_summary(st)
    summ["files"] = files
    (out / "flap_options.json").write_text(json.dumps(summ, indent=1, default=_json_default))
    files["json"] = str(out / "flap_options.json")
    summ["files"] = files
    return summ


def _json_default(o):
    import numpy as np
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _set_requirement(spec, key: str, value_si: float):
    """Copy of ``spec`` with requirement ``key`` set to ``value_si`` (SI units, same sense)."""
    import copy
    sp = copy.deepcopy(spec)
    hit = [r for r in sp.requirements if r.key == key and r.sense != "objective"]
    if not hit:
        raise ValueError(f"requirement '{key}' not in the mission (add it to sweep it)")
    for r in hit:
        r.value = float(value_si)
    return sp


def flap_options_sweep(spec, key: str, values, out_path, ykey: str = "W0", options=None) -> list[dict]:
    """Requirement sweep (e.g. ``max_speed`` or ``endurance``) of every flap option → points for
    :func:`plot_pareto` (requirement vs ``ykey``)."""
    pts = []
    for v in values:
        sp = _set_requirement(spec, key, v)
        st = flap_options_study(sp, options=options, performance=False)
        for r in st["rows"]:
            if r.get("converged") and r.get("feasible"):
                pts.append({"option": r["option"], key: float(v), "selected": r["option"] == st["selected"],
                            **{k: r.get(k, math.nan) for k in {ykey, "W0", "P_sl_kW", "S", "LD_max"}}})
    plot_pareto(pts, key, ykey, out_path, f"Varrimento de {key}: {ykey} por opção de flap", key, ykey)
    return pts
