"""Orquestração do MDO de sistema: ciclo exterior discreto (+ fecho por iteração) → estratégia interior →
arquivo de todas as avaliações → frente de Pareto, joelho, melhor por objetivo. docs/MDO.md."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from . import expr as E
from .evaluate import Archive, Evaluator, Record, SystemModel, build_constraints
from .om_problem import build_problem, nsga2_driver_class, set_start
from .pareto import knee_point, pareto_mask
from .spec import SCHEMA, MDOSpec, describe_vars

Log = Callable[[str], None]


def _quiet(fn: Callable[[], Any]) -> Any:
    """Corre o driver sem o texto que o OpenMDAO/scipy imprimem (a mensagem fica no resultado)."""
    import contextlib
    import io
    import warnings

    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore")
        return fn()


def _ov(r: Record, m: str) -> float:
    v = r.objectives.get(m)
    return math.nan if v is None else float(v)


def _best(recs: list[Record], spec: MDOSpec, j: int = 0) -> Record | None:
    o = spec.objectives[j]
    feas = [r for r in recs if r.feasible and r.objectives.get(o.metric) is not None]
    if not feas:
        return None
    return min(feas, key=lambda r: o.sign * _ov(r, o.metric))


def _least_violation(recs: list[Record]) -> Record | None:
    ok = [r for r in recs if r.ok]
    return min(ok, key=lambda r: r.violation) if ok else None


def _slsqp(ev: Evaluator, opts: Mapping[str, Any], x0: dict[str, Any] | None = None, j: int = 0,
           eps: dict[int, float] | None = None) -> dict[str, Any]:
    import openmdao.api as om

    drv = om.ScipyOptimizeDriver(optimizer="SLSQP", maxiter=int(opts.get("maxiter", 40)),
                                 tol=float(opts.get("tol", 1e-6)), disp=False)
    prob = build_problem(ev, drv, fd_step=float(opts.get("fd_step", 1e-3)), eps=eps, objective_index=j)
    set_start(prob, ev, x0)
    n0 = len(ev.archive.records)
    fail = _quiet(prob.run_driver)
    recs = ev.archive.records[n0:]
    sr = getattr(drv, "_scipy_optimize_result", None)
    smsg = str(getattr(sr, "message", "") or "")
    xs = {dv.path: float(prob.get_val(f"x{i}")[0]) for i, dv in enumerate(ev.spec.inner_vars)}
    final = ev.evaluate([xs])[0]
    success = not (fail.success is False if hasattr(fail, "success") else bool(fail))
    best = final if final.feasible else _best(recs + [final], ev.spec, j)
    return {"driver": "SLSQP (ScipyOptimizeDriver)", "success": bool(success) and final.feasible,
            "final": final.id, "best": best.id if best else None, "n_eval": len(ev.archive.records) - n0,
            "nit": int(getattr(sr, "nit", 0) or 0), "scipy_message": smsg,
            "message": "" if final.feasible else "ponto final do SLSQP não é viável; reportado o melhor viável avaliado"}


def _ga(ev: Evaluator, opts: Mapping[str, Any]) -> dict[str, Any]:
    import openmdao.api as om

    drv = om.SimpleGADriver(max_gen=int(opts.get("max_gen", 20)), pop_size=int(opts.get("pop_size", 0)),
                            penalty_parameter=float(opts.get("penalty", 10.0)), penalty_exponent=1.0)
    bits = int(opts.get("bits", 8))
    drv.options["bits"] = {f"x{i}": bits for i, dv in enumerate(ev.spec.inner_vars) if dv.kind == "continuous"}
    drv.options["run_parallel"] = False
    drv._randomstate = int(opts.get("seed", 0))
    prob = build_problem(ev, drv, scale=False)
    set_start(prob, ev, None)
    n0 = len(ev.archive.records)
    _quiet(prob.run_driver)
    b = _best(ev.archive.records[n0:], ev.spec)
    return {"driver": "SimpleGADriver (OpenMDAO; penalidade)", "best": b.id if b else None,
            "n_eval": len(ev.archive.records) - n0}


def _nsga2(ev: Evaluator, opts: Mapping[str, Any], log: Log) -> dict[str, Any]:
    Drv = nsga2_driver_class()
    drv = Drv()
    drv.options["pop_size"] = int(opts.get("pop_size", 40))
    drv.options["max_gen"] = int(opts.get("max_gen", 30))
    drv.options["seed"] = int(opts.get("seed", 0))
    drv.options["integer"] = [f"x{i}" for i, dv in enumerate(ev.spec.inner_vars) if dv.kind != "continuous"]
    x0 = [float(dv.x0) if dv.kind != "discrete" else float(dv.values.index(dv.x0)) for dv in ev.spec.inner_vars]
    drv.options["initial"] = [x0]  # o ponto de partida declarado entra na população inicial
    drv.options["prefetch"] = lambda pts: ev.evaluate([{dv.path: p[f"x{i}"] for i, dv in enumerate(ev.spec.inner_vars)}
                                                       for p in pts])
    drv.options["on_generation"] = lambda g, X, F, CV: log(f"    NSGA-II geração {g + 1}: "
                                                           f"{int(np.sum(CV <= 0))}/{len(CV)} viáveis")
    prob = build_problem(ev, drv, objective_index=None, scale=False)
    set_start(prob, ev, None)
    n0 = len(ev.archive.records)
    _quiet(prob.run_driver)
    return {"driver": "NSGA-II (Deb et al. 2002; driver OpenMDAO do acdt)", "n_eval": len(ev.archive.records) - n0,
            "pop_size": drv.options["pop_size"], "max_gen": drv.options["max_gen"], "seed": drv.options["seed"]}


def _doe(ev: Evaluator, opts: Mapping[str, Any]) -> dict[str, Any]:
    import openmdao.api as om

    from acdt.core.sensitivity import distributions as D

    dvs = ev.spec.inner_vars
    method = str(opts.get("method", "lhs"))
    if method == "full_factorial":
        levels = int(opts.get("levels", 3))
        grids = [np.linspace(dv.lower, dv.upper, levels) if dv.kind == "continuous"
                 else np.arange(dv.lower, dv.upper + 1) for dv in dvs]
        mesh = np.array(np.meshgrid(*grids, indexing="ij")).reshape(len(dvs), -1).T
    else:
        n = int(opts.get("n", 20))
        u = D.unit_sample(n, len(dvs), "lhs", np.random.default_rng(int(opts.get("seed", 0))))
        mesh = np.array([[dv.lower + u[i, j] * (dv.upper - dv.lower) for j, dv in enumerate(dvs)] for i in range(n)])
    pts = [{dv.path: float(row[j]) for j, dv in enumerate(dvs)} for row in mesh]
    n0 = len(ev.archive.records)
    ev.evaluate(pts)  # lote paralelo; o DOEDriver abaixo encontra-as em cache
    cases = [[(f"x{j}", np.array([row[j]])) for j in range(len(dvs))] for row in mesh]
    prob = build_problem(ev, om.DOEDriver(om.ListGenerator(cases)), objective_index=None, scale=False)
    _quiet(prob.run_driver)
    return {"driver": f"DOEDriver (OpenMDAO; {method}, {len(pts)} pontos)", "n_eval": len(ev.archive.records) - n0,
            "seed": int(opts.get("seed", 0))}


def _epsilon(ev: Evaluator, opts: Mapping[str, Any], log: Log) -> dict[str, Any]:
    """ε-restrição (Haimes, Lasdon & Wismer, IEEE Trans. SMC 1(3):296–297, 1971): âncoras mono-objetivo e depois
    min f₁ s.a. f₂ ≤ ε em ``n_points`` níveis entre as âncoras, arranque a quente no ponto anterior."""
    o1, o2 = ev.spec.objectives
    n0 = len(ev.archive.records)
    a1 = _slsqp(ev, opts, j=0)
    a2 = _slsqp(ev, opts, j=1)
    r1 = ev.archive.records[a1["best"]] if a1["best"] is not None else None
    r2 = ev.archive.records[a2["best"]] if a2["best"] is not None else None
    runs: list[dict[str, Any]] = [{"anchor": o1.metric, **a1}, {"anchor": o2.metric, **a2}]
    if r1 is None or r2 is None:
        return {"driver": "ε-restrição + SLSQP", "runs": runs, "n_eval": len(ev.archive.records) - n0,
                "message": "âncora sem ponto viável: frente não construída"}
    e_a, e_b = _ov(r1, o2.metric), _ov(r2, o2.metric)
    n = int(opts.get("n_points", 5))
    x = dict(r1.x)
    for e in np.linspace(e_a, e_b, n + 2)[1:-1]:
        log(f"    ε-restrição: {o2.metric} {'≤' if o2.sense == 'min' else '≥'} {e:.5g}")
        rr = _slsqp(ev, opts, x0=x, j=0, eps={1: float(e)})
        runs.append({"eps": float(e), **rr})
        if rr["best"] is not None:
            x = dict(ev.archive.records[rr["best"]].x)
    return {"driver": "ε-restrição (Haimes et al. 1971) + SLSQP", "runs": runs, "n_eval": len(ev.archive.records) - n0}


def _inner(spec: MDOSpec, ev: Evaluator, log: Log) -> dict[str, Any]:
    o = spec.options
    s = spec.strategy
    if s == "slsqp":
        return _slsqp(ev, o)
    if s == "ga":
        return _ga(ev, o)
    if s == "nsga2":
        return _nsga2(ev, o, log)
    if s == "doe":
        return _doe(ev, o)
    return _epsilon(ev, o, log)


def front(recs: list[Record], spec: MDOSpec) -> tuple[list[Record], dict[str, Any] | None]:
    feas = [r for r in recs if r.feasible and all(r.objectives.get(o.metric) is not None for o in spec.objectives)]
    if not feas:
        return [], None
    F = np.array([[o.sign * _ov(r, o.metric) for o in spec.objectives] for r in feas])
    m = pareto_mask(F)
    fr = [r for r, k in zip(feas, m) if k]
    # remove duplicados (mesmos objetivos)
    seen: set[tuple[float, ...]] = set()
    uniq = []
    for r in sorted(fr, key=lambda r: spec.objectives[0].sign * _ov(r, spec.objectives[0].metric)):
        k2 = tuple(round(_ov(r, o.metric), 9) for o in spec.objectives)
        if k2 not in seen:
            seen.add(k2)
            uniq.append(r)
    if len(spec.objectives) < 2:
        return uniq, None
    Fu = np.array([[o.sign * _ov(r, o.metric) for o in spec.objectives] for r in uniq])
    ki, how = knee_point(Fu)
    return uniq, {"id": uniq[ki].id, "method": how}


def run_mdo(spec: MDOSpec, model: SystemModel, *, outdir: str | Path | None = None, plots: bool = True,
            log: Log = print, final_matrix: Callable[[Record], Mapping[str, Any] | None] | None = None
            ) -> dict[str, Any]:
    from acdt.core import provenance as P

    from .robust import RobustSurrogate

    for k in ("seed",):
        if k in spec.options:
            P.register_seed(f"mdo.{spec.strategy}.seed", spec.options[k])
    if spec.robust is not None:
        P.register_seed("mdo.robust.seed", spec.robust.seed)
    archive = Archive()
    if spec.fixed:
        model = model.with_overrides(spec.fixed)
    cons, filters = build_constraints(spec, list(model.requirement_defs()))
    loops: list[dict[str, Any]] = []
    combos = spec.combos()
    for combo in combos:
        log(f"[mdo] combinação exterior {combo or '(nenhuma)'}")
        clo = spec.closure
        cval = clo.x0 if clo else None
        hist: list[dict[str, Any]] = []
        for it in range(clo.max_iter if clo else 1):
            env: dict[str, float] = dict(spec.constants)
            over: dict[str, Any] = dict(combo)
            if clo is not None and cval is not None:
                env[clo.name] = cval
                for path, src in clo.apply.items():
                    v = E.evaluate(src, env)
                    if v is None:
                        raise ValueError(f"fecho: '{src}' sem valor")
                    over[path] = v
            m = model.with_overrides(over) if over else model
            reqdefs = list(m.requirement_defs())  # limiares podem depender do fecho (p. ex. requisito por avião)
            cons, filters = build_constraints(spec, reqdefs)
            rob = RobustSurrogate(spec, m, reqdefs) if spec.robust is not None else None
            ev = Evaluator(spec, m, {**combo, **({clo.name: cval} if clo else {})}, archive, cons, rob, env, over)
            ev.phase = f"c{combos.index(combo)}" + (f".it{it}" if clo else "")
            n0 = len(archive.records)
            res = _inner(spec, ev, log)
            recs = archive.records[n0:]
            fr, knee = front(recs, spec)
            pick = archive.records[knee["id"]] if knee else (fr[0] if fr else None)
            feasible_pick = pick is not None
            if pick is None and clo is not None:
                pick = _least_violation(recs)  # sem viável: o fecho segue o projeto de menor violação (marcado)
            entry: dict[str, Any] = {"combo": combo, "phase": ev.phase, "inner": res,
                                     "front": [r.id for r in fr], "knee": knee,
                                     "chosen": pick.id if (pick and feasible_pick) else None,
                                     "closure_pick": None if pick is None else
                                     {"id": pick.id, "feasible": feasible_pick},
                                     "robust": rob.info if rob is not None else None}
            if clo is not None:
                newv = None
                if pick is not None:
                    newv = E.evaluate(clo.update, {**env, **{k.replace(":", "_").replace("-", "_"): v
                                                             for k, v in pick.metrics.items()}, **pick.metrics})
                entry.update(closure_value=cval, closure_update=newv)
                hist.append(entry)
                log(f"  fecho {clo.name}: {cval:g} → {newv if newv is None else f'{newv:g}'}")
                if newv is None:
                    why = "ótimo interior sem valor para a regra"
                    if not any(r.ok for r in recs):
                        msgs = sorted({r.message for r in recs if r.message})
                        why = "todas as avaliações falharam: " + "; ".join(msgs)[:200]
                    entry["closure_status"] = f"desconhecido ({why})"
                    break
                if abs(newv - cval) < 1e-9:  # type: ignore[operator]
                    entry["closure_status"] = "convergiu"
                    break
                if any(abs(h["closure_value"] - newv) < 1e-9 for h in hist[:-1]):
                    entry["closure_status"] = "ciclo (oscila entre valores): não convergiu"
                    break
                cval = newv
            else:
                hist.append(entry)
        if clo is not None and hist and "closure_status" not in hist[-1]:
            hist[-1]["closure_status"] = f"não convergiu em {clo.max_iter} iterações"
        loops.append({"combo": combo, "iterations": hist,
                      "closure_status": hist[-1].get("closure_status") if clo else None})
    # resultado global: só a última iteração de cada fecho conta para a decisão
    final_ids: set[int] = set()
    for lp in loops:
        last = lp["iterations"][-1]
        ph = last["phase"]
        final_ids |= {r.id for r in archive.records if r.phase.split("+")[0] == ph}
    decision = [r for r in archive.records if r.id in final_ids]
    gf, gknee = front(decision, spec)
    best = {o.metric: (b.id if (b := _best(decision, spec, j)) else None) for j, o in enumerate(spec.objectives)}
    b0 = best[spec.objectives[0].metric]
    chosen = archive.records[gknee["id"]] if gknee else (archive.records[b0] if b0 is not None else None)
    warn: list[str] = []
    okr = [r for r in archive.records if r.ok]
    if len(okr) >= 2 and len({tuple(sorted((k, repr(v)) for k, v in r.x.items())) for r in okr}) > 1:
        for o in spec.objectives:
            vals = [r.objectives.get(o.metric) for r in okr]
            fv = [float(v) for v in vals if v is not None]
            if fv and max(fv) - min(fv) <= 1e-12 * max(1.0, abs(fv[0])):
                warn.append(f"o objetivo {o.metric} não muda entre projetos diferentes: confirme que os caminhos "
                            "das variáveis são usados pelo modelo")
    na = sorted({i for r in archive.records for i in (r.extra.get("nao_avaliado_pelo_modelo") or [])})
    if na:
        warn.append("requisitos numéricos não avaliados pelo modelo deste estudo (ficam nao_avaliado em cada projeto, "
                    "não são restrição e nunca contam como passa): " + ", ".join(na))
    out: dict[str, Any] = {
        "schema": SCHEMA, "warnings": warn, "fixed": spec.fixed, "model": model.describe(), "strategy": spec.strategy, "options": spec.options,
        "design_variables": describe_vars(spec.design_vars),
        "objectives": [{"metric": o.metric, "sense": o.sense, "ref": o.ref} for o in spec.objectives],
        "constraints": [{"name": c.name, "kind": c.kind, "note": c.note, "offset": c.offset} for c in cons],
        "filters": filters, "policy": spec.policy, "derived": spec.derived, "constants": spec.constants,
        "closure": None if spec.closure is None else {"name": spec.closure.name, "x0": spec.closure.x0,
                                                      "update": spec.closure.update, "apply": spec.closure.apply,
                                                      "source": spec.closure.source or "PRESSUPOSTO"},
        "loops": loops, "n_evaluations": len(archive.records), "n_model_calls": archive.n_model_calls,
        "n_failed": sum(1 for r in archive.records if not r.ok),
        "n_feasible": sum(1 for r in archive.records if r.feasible),
        "pareto": [r.id for r in gf], "knee": gknee, "best": best, "chosen": chosen.id if chosen else None,
        "least_violation": (lv.id if (lv := _least_violation(archive.records)) else None),
        "pressupostos": spec.pressupostos, "evaluations": [r.to_dict() for r in archive.records],
    }
    if chosen is not None and final_matrix is not None:
        out["verification_matrix"] = final_matrix(chosen)
    if outdir is not None:
        from .report import write

        out["files"] = [str(p) for p in write(out, outdir, plots=plots)]
    return out
