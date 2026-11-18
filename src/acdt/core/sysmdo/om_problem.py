"""Ligação ao OpenMDAO (Gray et al., Struct. Multidisc. Optim. 59, 2019): componente do sistema, problema e um
driver NSGA-II (Deb et al. 2002) para frentes de Pareto.

O componente expõe as variáveis interiores como entradas ``x<i>``, os objetivos (em minimização) como ``f<j>`` e
as margens das restrições como ``g<k>`` (g ≥ 0). As derivadas parciais são diferenças finitas avançadas do próprio
sistema, calculadas **em lote** (as perturbações correm em paralelo no modelo) — o modelo é caixa-preta (o pipeline
já fecha o seu MDA, formulação MDF; Martins & Lambe, AIAA J. 51(9), 2013).
"""
from __future__ import annotations

import math
from typing import Any, Callable, Sequence

import numpy as np

from .evaluate import FAIL_MARGIN, Evaluator, Record


def _penalty(ev: Evaluator) -> dict[str, float]:
    """Objetivos para uma avaliação falhada: 10× a maior magnitude finita já vista (só orienta o otimizador;
    a avaliação fica marcada ``falhou`` no arquivo e nunca é reportada como projeto)."""
    out: dict[str, float] = {}
    for o in ev.spec.objectives:
        vals = [abs(float(v)) for r in ev.archive.records for k, v in r.objectives.items()
                if k == o.metric and v is not None and math.isfinite(float(v))]
        big = 10.0 * max(vals + [abs(o.ref or 0.0), 1.0])
        out[o.metric] = big if o.sense == "min" else -big
    return out


def record_outputs(ev: Evaluator, r: Record) -> tuple[list[float], list[float]]:
    pen = _penalty(ev) if not r.ok else {}
    f = []
    for o in ev.spec.objectives:
        v = r.objectives.get(o.metric)
        val = float(v) if (r.ok and v is not None) else pen.get(o.metric, 0.0)
        f.append(o.sign * val)
    skip = set(r.extra.get("nao_avaliado_pelo_modelo") or [])
    g = [float(v) if v is not None else (0.0 if k.startswith("req:") and k[4:] in skip else FAIL_MARGIN)
         for k, v in r.constraints.items()]
    return f, g


def make_component(ev: Evaluator, fd_step: float) -> Any:
    import openmdao.api as om

    names = [dv.path for dv in ev.spec.inner_vars]
    lows = [dv.lower for dv in ev.spec.inner_vars]
    ups = [dv.upper for dv in ev.spec.inner_vars]
    x0 = [float(dv.x0) if dv.kind != "discrete" else float(dv.values.index(dv.x0)) for dv in ev.spec.inner_vars]
    ncon = len(ev.constraints) + (len(ev.spec.robust.p_pass) if ev.spec.robust else 0)
    nobj = len(ev.spec.objectives)

    class SystemComp(om.ExplicitComponent):  # type: ignore[misc]
        def setup(self) -> None:
            for i, v in enumerate(x0):
                self.add_input(f"x{i}", val=v)
            for j in range(nobj):
                self.add_output(f"f{j}", val=0.0)
            for k in range(ncon):
                self.add_output(f"g{k}", val=0.0)

        def setup_partials(self) -> None:
            self.declare_partials("*", "*", method="exact")

        def _pt(self, inputs: Any) -> dict[str, float]:
            return {n: float(inputs[f"x{i}"][0]) for i, n in enumerate(names)}

        def compute(self, inputs: Any, outputs: Any) -> None:
            r = ev.evaluate([self._pt(inputs)])[0]
            f, g = record_outputs(ev, r)
            for j, v in enumerate(f):
                outputs[f"f{j}"] = v
            for k, v in enumerate(g):
                outputs[f"g{k}"] = v

        def compute_partials(self, inputs: Any, partials: Any) -> None:
            base = self._pt(inputs)
            pts = [base]
            hs = []
            for i, n in enumerate(names):
                h = fd_step * (ups[i] - lows[i])
                if base[n] + h > ups[i]:
                    h = -h  # passo para dentro dos limites (o modelo pode não estar definido fora)
                hs.append(h)
                p = dict(base)
                p[n] = base[n] + h
                pts.append(p)
            ev.phase, old = ev.phase + "+fd", ev.phase
            recs = ev.evaluate(pts)
            ev.phase = old
            f0, g0 = record_outputs(ev, recs[0])
            for i in range(len(names)):
                f1, g1 = record_outputs(ev, recs[i + 1])
                for j in range(nobj):
                    partials[f"f{j}", f"x{i}"] = (f1[j] - f0[j]) / hs[i]
                for k in range(ncon):
                    partials[f"g{k}", f"x{i}"] = (g1[k] - g0[k]) / hs[i]

    return SystemComp


def build_problem(ev: Evaluator, driver: Any, *, fd_step: float = 1e-3, eps: dict[int, float] | None = None,
                  objective_index: int | None = 0, scale: bool = True) -> Any:
    """Problema OpenMDAO: um componente de sistema + ``driver``. ``eps``: ε-restrições f_j ≤ ε (ε-restrição)."""
    import openmdao.api as om

    prob = om.Problem(reports=False)
    prob.model.add_subsystem("sys", make_component(ev, fd_step)(), promotes=["*"])
    for i, dv in enumerate(ev.spec.inner_vars):
        kw: dict[str, Any] = {"lower": dv.lower, "upper": dv.upper}
        if scale and dv.kind == "continuous":
            kw.update(ref0=dv.lower, ref=dv.upper)
        prob.model.add_design_var(f"x{i}", **kw)
    objs = ev.spec.objectives
    idx = range(len(objs)) if objective_index is None else [objective_index]
    for j in idx:
        o = objs[j]
        ref = abs(o.ref) if o.ref else None
        prob.model.add_objective(f"f{j}", **({"ref": ref} if ref else {}))
    ncon = len(ev.constraints) + (len(ev.spec.robust.p_pass) if ev.spec.robust else 0)
    for k in range(ncon):
        prob.model.add_constraint(f"g{k}", lower=0.0)
    for j, e in (eps or {}).items():
        o = objs[j]
        ref = abs(o.ref) if o.ref else max(abs(e), 1.0)
        prob.model.add_constraint(f"f{j}", upper=o.sign * e if o.sense == "min" else -e, ref=ref)
    prob.driver = driver
    prob.setup(check=False)
    return prob


def set_start(prob: Any, ev: Evaluator, x: dict[str, Any] | None) -> None:
    for i, dv in enumerate(ev.spec.inner_vars):
        v = (x or {}).get(dv.path, dv.x0)
        if dv.kind == "discrete":
            v = dv.values.index(v) if v in dv.values else 0
        prob.set_val(f"x{i}", float(v))


def nsga2_driver_class() -> Any:
    import openmdao.api as om
    from openmdao.core.driver import Driver, RecordingDebugging

    from .pareto import crowding_distance, nondominated_sort

    class NSGA2Driver(Driver):  # type: ignore[misc]
        """NSGA-II (Deb, Pratap, Agarwal & Meyarivan, IEEE TEC 6(2), 2002): ordenação não dominada com
        dominância com restrições (§VI), distância de aglomeração, torneio binário, cruzamento SBX (η_c) e mutação
        polinomial (η_m) (Deb & Agrawal, Complex Systems 9, 1995). Variáveis inteiras/discretas: arredondadas."""

        def _declare_options(self) -> None:
            self.options.declare("pop_size", default=40, types=int)
            self.options.declare("max_gen", default=30, types=int)
            self.options.declare("seed", default=0, types=int)
            self.options.declare("eta_c", default=15.0)
            self.options.declare("eta_m", default=20.0)
            self.options.declare("p_c", default=0.9)
            self.options.declare("integer", default=[], types=list)
            self.options.declare("prefetch", default=None, allow_none=True)
            self.options.declare("on_generation", default=None, allow_none=True)
            self.options.declare("initial", default=None, allow_none=True)

        def _setup_driver(self, problem: Any) -> None:
            super()._setup_driver(problem)
            self.supports._read_only = False
            self.supports["multiple_objectives"] = True
            self.supports["inequality_constraints"] = True
            self.supports["gradients"] = False
            self.supports._read_only = True

        def _eval(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            names = list(self._designvars)
            pre: Callable[[Sequence[dict[str, float]]], None] | None = self.options["prefetch"]
            if pre is not None:
                pre([{n: float(X[i, j]) for j, n in enumerate(names)} for i in range(X.shape[0])])
            F, CV = [], []
            for i in range(X.shape[0]):
                for j, n in enumerate(names):
                    self._set_design_var(n, X[i, j])
                with RecordingDebugging(self._get_name(), self.iter_count, self) as rec:
                    self._run_solve_nonlinear()
                    rec.abs = 0.0
                    rec.rel = 0.0
                self.iter_count += 1
                F.append([float(np.asarray(v).ravel()[0]) for v in self.get_objective_values().values()])
                cv = 0.0
                for n, v in self.get_constraint_values().items():
                    meta = self._cons[n]
                    val = float(np.asarray(v).ravel()[0])
                    lo, up = meta.get("lower"), meta.get("upper")
                    if lo is not None and lo > -1e29 and val < lo:
                        cv += lo - val
                    if up is not None and up < 1e29 and val > up:
                        cv += val - up
                CV.append(cv)
            return np.asarray(F), np.asarray(CV)

        def run(self) -> bool:
            rng = np.random.default_rng(self.options["seed"])
            names = list(self._designvars)
            lo = np.array([float(np.asarray(self._designvars[n]["lower"]).ravel()[0]) for n in names])
            hi = np.array([float(np.asarray(self._designvars[n]["upper"]).ravel()[0]) for n in names])
            integer = np.array([n in self.options["integer"] for n in names])
            N = self.options["pop_size"] + (self.options["pop_size"] % 2)
            X = lo + rng.random((N, len(names))) * (hi - lo)
            init = self.options["initial"]
            if init is not None:
                for i, row in enumerate(np.atleast_2d(np.asarray(init, dtype=float))[:N]):
                    X[i] = row
            X[:, integer] = np.round(X[:, integer])
            F, CV = self._eval(X)
            for gen in range(self.options["max_gen"]):
                rank = np.empty(N, dtype=int)
                crowd = np.empty(N)
                for r, fr in enumerate(nondominated_sort(F, CV)):
                    rank[fr] = r
                    crowd[fr] = crowding_distance(F[fr])
                Q = self._offspring(X, rank, crowd, lo, hi, integer, rng)
                FQ, CVQ = self._eval(Q)
                XR, FR, CVR = np.vstack([X, Q]), np.vstack([F, FQ]), np.concatenate([CV, CVQ])
                sel: list[int] = []
                for fr in nondominated_sort(FR, CVR):
                    if len(sel) + len(fr) <= N:
                        sel += fr
                    else:
                        cd = crowding_distance(FR[fr])
                        sel += [fr[i] for i in np.argsort(-cd, kind="stable")[: N - len(sel)]]
                        break
                X, F, CV = XR[sel], FR[sel], CVR[sel]
                cb = self.options["on_generation"]
                if cb is not None:
                    cb(gen, X, F, CV)
            self._final = (X, F, CV)
            return False

        def _offspring(self, X: np.ndarray, rank: np.ndarray, crowd: np.ndarray, lo: np.ndarray, hi: np.ndarray,
                       integer: np.ndarray, rng: np.random.Generator) -> np.ndarray:
            N, k = X.shape
            ec, em, pc = float(self.options["eta_c"]), float(self.options["eta_m"]), float(self.options["p_c"])

            def tour() -> int:
                a, b = rng.integers(0, N, 2)
                if rank[a] != rank[b]:
                    return int(a if rank[a] < rank[b] else b)
                return int(a if crowd[a] >= crowd[b] else b)

            out: list[np.ndarray] = []
            span = np.where(hi > lo, hi - lo, 1.0)
            while len(out) < N:
                p1, p2 = X[tour()].copy(), X[tour()].copy()
                if rng.random() < pc:
                    for j in range(k):
                        if rng.random() < 0.5 and abs(p1[j] - p2[j]) > 1e-14:
                            u = rng.random()
                            beta = (2 * u) ** (1 / (ec + 1)) if u <= 0.5 else (1 / (2 * (1 - u))) ** (1 / (ec + 1))
                            c1 = 0.5 * ((1 + beta) * p1[j] + (1 - beta) * p2[j])
                            c2 = 0.5 * ((1 - beta) * p1[j] + (1 + beta) * p2[j])
                            p1[j], p2[j] = c1, c2
                for c in (p1, p2):
                    for j in range(k):
                        if rng.random() < 1.0 / k:
                            u = rng.random()
                            d = (2 * u) ** (1 / (em + 1)) - 1 if u < 0.5 else 1 - (2 * (1 - u)) ** (1 / (em + 1))
                            c[j] += d * span[j]
                    np.clip(c, lo, hi, out=c)
                    c[integer] = np.round(c[integer])
                    out.append(c)
            return np.asarray(out[:N])

    return NSGA2Driver
