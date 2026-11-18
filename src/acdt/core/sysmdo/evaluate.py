"""Avaliador de sistema: ponto de projeto → modelo caixa-preta → métricas, estado dos requisitos, restrições.

Cada avaliação fica no arquivo (:class:`Archive`) com o estado de cada requisito da matriz de verificação, para
que **todo** o projeto avaliado tenha o seu estado (``passa``/``no_limite``/``falha``/``nao_avaliado``/
``desconhecido``) e não só o ótimo. Avaliações falhadas contam e nunca valem zero.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from acdt.core.sensitivity.study import Sample

from . import expr as E
from .spec import MDOSpec

FAIL_MARGIN = -1.0  # margem normalizada atribuída a restrições de avaliações falhadas/desconhecidas (só para o otimizador)
_EPS = 1e-9
FEAS_TOL = 1e-6  # margem relativa: ruído numérico dos fechos iterativos do modelo (o pipeline converge a ~1e-7)


class SystemModel(Protocol):
    def run(self, points: Sequence[Mapping[str, float]]) -> list[Sample]: ...

    def requirement_defs(self) -> list[Any]: ...

    def describe(self) -> dict[str, Any]: ...

    def nominal(self, path: str) -> float | None: ...

    def with_overrides(self, overrides: Mapping[str, Any]) -> "SystemModel": ...


@dataclass
class Constraint:
    """Uma restrição g ≥ 0 (margem normalizada pelo |limiar|, como em ``verification.classify``)."""

    name: str
    kind: str  # requisito | metrica
    req: Any = None
    metric: str = ""
    lower: float | None = None
    upper: float | None = None
    offset: float = 0.0  # política: passa → +tol; limiar → 0; no_limite → −tol
    policy: str = "limiar"
    note: str = ""

    def margin(self, metrics: Mapping[str, float], reqs: Mapping[str, Mapping[str, Any]]) -> float | None:
        if self.kind == "requisito":
            r = self.req
            q = reqs.get(r.id) or {}
            v = q.get("value")
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
                return None
            # limiar e tolerância DESTA avaliação quando o modelo os dá (um requisito pode ser variável de projeto)
            t_s = q.get("threshold")
            thr = float(t_s) if isinstance(t_s, (int, float)) and not isinstance(t_s, bool) else float(r.threshold)
            tol_s = q.get("tolerance")
            tol = float(tol_s) if isinstance(tol_s, (int, float)) and not isinstance(tol_s, bool) else r.tolerance
            scale = abs(thr) if thr != 0.0 else 1.0
            if r.comparison == "min":
                m = (float(v) - thr) / scale
            elif r.comparison == "max":
                m = (thr - float(v)) / scale
            else:
                m = tol - abs(float(v) - thr) / scale
            off = self.offset
            if self.policy == "passa" and r.comparison != "target":
                off = tol + _EPS
            elif self.policy == "no_limite" and r.comparison != "target":
                off = -tol
            return m - off
        v2 = metrics.get(self.metric)
        if v2 is None or not math.isfinite(v2):
            return None
        ms = []
        if self.lower is not None:
            ms.append((v2 - self.lower) / (abs(self.lower) or 1.0))
        if self.upper is not None:
            ms.append((self.upper - v2) / (abs(self.upper) or 1.0))
        return min(ms)


def build_constraints(spec: MDOSpec, reqdefs: Sequence[Any]) -> tuple[list[Constraint], list[dict[str, Any]]]:
    """Requisitos do registo → restrições automáticas (numéricas) e filtros (bool/categoria, só reportados)."""
    cons: list[Constraint] = []
    filters: list[dict[str, Any]] = []
    sel = spec.req_select
    for r in reqdefs:
        if sel == "none" or (isinstance(sel, list) and r.id not in sel) or r.id in spec.req_exclude:
            continue
        if r.comparison in ("min", "max", "target"):
            tol = float(r.tolerance)
            off = {"passa": tol + _EPS, "limiar": 0.0, "no_limite": -tol}[spec.policy] if r.comparison != "target" \
                else (0.0 if spec.policy != "passa" else _EPS)
            cons.append(Constraint(name=f"req:{r.id}", kind="requisito", req=r, offset=off, policy=spec.policy,
                                   note=f"{r.comparison} {r.display or r.threshold} (tol ±{tol:g}"
                                        f"{', ' + r.tolerance_source if r.tolerance_source else ''}); política "
                                        f"{spec.policy}"))
        else:
            filters.append({"id": r.id, "comparison": r.comparison, "text": r.text,
                            "nota": "requisito não numérico: filtro (estado reportado por projeto), não restrição"})
    if isinstance(sel, list):
        known = {r.id for r in reqdefs}
        for rid in sel:
            if rid not in known:
                filters.append({"id": rid, "nota": "requisito pedido mas não existe no registo"})
    for mc in spec.metric_constraints:
        cons.append(Constraint(name=f"met:{mc.metric}", kind="metrica", metric=mc.metric, lower=mc.lower,
                               upper=mc.upper, note=mc.source or "PRESSUPOSTO"))
    return cons, filters


@dataclass
class Record:
    id: int
    combo: dict[str, Any]
    x: dict[str, Any]
    ok: bool
    metrics: dict[str, float]
    requirements: dict[str, dict[str, Any]]
    objectives: dict[str, float | None]
    constraints: dict[str, float | None]
    violation: float
    feasible: bool
    phase: str = ""
    message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def status_counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for q in self.requirements.values():
            s = str(q.get("status") or "nao_avaliado")
            c[s] = c.get(s, 0) + 1
        return c

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "phase": self.phase, "combo": self.combo, "x": self.x, "ok": self.ok,
                "feasible": self.feasible, "violation": self.violation, "objectives": self.objectives,
                "constraints": self.constraints, "metrics": self.metrics,
                "requirements": {k: {"status": v.get("status"), "value": v.get("value")}
                                 for k, v in self.requirements.items()},
                "status_counts": self.status_counts, "message": self.message, **self.extra}


class Archive:
    def __init__(self) -> None:
        self.records: list[Record] = []
        self.n_model_calls = 0

    def add(self, r: Record) -> Record:
        self.records.append(r)
        return r


class Evaluator:
    """Ponto (caminho → valor; discretas interiores por índice) → :class:`Record`, com cache e lotes paralelos."""

    def __init__(self, spec: MDOSpec, model: SystemModel, combo: Mapping[str, Any], archive: Archive,
                 constraints: Sequence[Constraint], robust: Any = None, extra_env: Mapping[str, float] | None = None,
                 overrides: Mapping[str, Any] | None = None):
        self.spec, self.model, self.combo, self.archive = spec, model, dict(combo), archive
        self.overrides = dict(overrides or {})  # o que o modelo deste ciclo já tem aplicado (combinação + fecho)
        self.constraints = list(constraints)
        self.robust = robust
        self.env = dict(spec.constants)
        self.env.update(extra_env or {})
        self.cache: dict[tuple[Any, ...], Record] = {}
        self.phase = ""
        self._models: dict[tuple[Any, ...], SystemModel] = {}

    # ------------------------------------------------------------------ pontos
    def _split(self, x: Mapping[str, float]) -> tuple[dict[str, float], dict[str, Any]]:
        cont: dict[str, float] = {}
        disc: dict[str, Any] = {}
        for dv in self.spec.inner_vars:
            v = float(x[dv.path])
            if dv.kind == "continuous":
                cont[dv.path] = v
            elif dv.kind == "integer":
                cont[dv.path] = float(int(round(min(max(v, dv.lower), dv.upper))))
            else:
                i = int(round(min(max(v, 0.0), len(dv.values) - 1)))
                disc[dv.path] = dv.values[i]
        return cont, disc

    def key(self, x: Mapping[str, float]) -> tuple[Any, ...]:
        cont, disc = self._split(x)
        return tuple(round(cont[k], 12) for k in sorted(cont)) + tuple(repr(disc[k]) for k in sorted(disc))

    def _model_for(self, disc: Mapping[str, Any]) -> SystemModel:
        k = tuple(sorted((a, repr(b)) for a, b in disc.items()))
        if not disc:
            return self.model
        if k not in self._models:
            self._models[k] = self.model.with_overrides(disc)
        return self._models[k]

    def evaluate(self, xs: Sequence[Mapping[str, float]]) -> list[Record]:
        todo: dict[tuple[Any, ...], tuple[dict[str, float], dict[str, Any]]] = {}
        for x in xs:
            k = self.key(x)
            if k not in self.cache and k not in todo:
                todo[k] = self._split(x)
        groups: dict[tuple[Any, ...], list[tuple[Any, ...]]] = {}
        for k, (_c, disc) in todo.items():
            groups.setdefault(tuple(sorted((a, repr(b)) for a, b in disc.items())), []).append(k)
        for keys in groups.values():
            disc = todo[keys[0]][1]
            pts = [todo[k][0] for k in keys]
            samples = self._model_for(disc).run(pts)
            self.archive.n_model_calls += len(pts)
            rob = self.robust.evaluate(pts, disc) if self.robust is not None else [{} for _ in pts]
            for k, smp, rb in zip(keys, samples, rob):
                cont, d2 = todo[k]
                self.cache[k] = self._record({**cont, **d2}, smp, rb)
        return [self.cache[self.key(x)] for x in xs]

    def _matrix_ok(self, c: Constraint | None, reqs: Mapping[str, Mapping[str, Any]]) -> bool:
        """Margem ligeiramente negativa mas a matriz diz ``no_limite`` só pela resolução numérica do avaliador
        (tolerância declarada 0) → cumpre o limiar à resolução do modelo (mesma regra da matriz). Com a política
        ``no_limite``, ``passa``/``no_limite`` da matriz cumprem sempre."""
        if c is None or c.kind != "requisito" or self.spec.policy == "passa":
            return False
        q = reqs.get(c.req.id) or {}
        st = q.get("status")
        if self.spec.policy == "no_limite":
            return st in ("passa", "no_limite")
        tol = q.get("tolerance", c.req.tolerance)
        return st == "no_limite" and not tol

    def _record(self, x: dict[str, Any], smp: Sample, rob: Mapping[str, Any]) -> Record:
        met = dict(smp.metrics) if smp.ok else {}
        if smp.ok:
            env = {**self.env, **{k.replace(":", "_").replace("-", "_"): v for k, v in met.items()}, **met}
            for name, src in self.spec.derived.items():
                v = E.evaluate(src, env)
                if v is not None:
                    met[name] = v
                    env[name] = v
            for k2, v2 in (rob.get("metrics") or {}).items():
                if v2 is not None and math.isfinite(float(v2)):
                    met[k2] = float(v2)
        objs: dict[str, float | None] = {o.metric: met.get(o.metric) for o in self.spec.objectives}
        cons: dict[str, float | None] = {}
        for c in self.constraints:
            cons[c.name] = c.margin(met, smp.requirements) if smp.ok else None
        for rid, pmin in (self.spec.robust.p_pass.items() if self.spec.robust else []):
            p = (rob.get("p_pass") or {}).get(rid)
            cons[f"ppass:{rid}"] = None if p is None else float(p) - pmin
        ftol = float(self.spec.options.get("feas_tol", FEAS_TOL))
        viol = 0.0
        unknown = False
        kinds = {cc.name: cc for cc in self.constraints}
        outside: list[str] = []
        for name, v in cons.items():
            ck = kinds.get(name)
            if v is None and smp.ok and ck is not None and ck.kind == "requisito" and \
                    (smp.requirements.get(ck.req.id) or {}).get("status") == "nao_avaliado":
                # fora do âmbito do modelo deste estudo (a etapa que o avalia não corre): não pode ser restrição;
                # fica `nao_avaliado` na matriz deste projeto (nunca conta como passa) e listado no relatório
                outside.append(ck.req.id)
                continue
            if v is None:
                unknown = True
                viol += -FAIL_MARGIN
            elif v < -ftol and not self._matrix_ok(ck, smp.requirements):
                viol += -v
        ok = smp.ok and all(v is not None for v in objs.values())
        msg = smp.message
        if smp.ok and not ok:
            msg = "objetivo sem valor: " + ", ".join(k for k, v in objs.items() if v is None)
        if unknown and ok:
            msg = (msg + "; " if msg else "") + "restrição com valor desconhecido (conta como violada)"
        r = Record(id=len(self.archive.records), combo=dict(self.combo), x=x, ok=ok, metrics=met,
                   requirements=dict(smp.requirements), objectives=objs, constraints=cons,
                   violation=viol if ok else math.inf, feasible=ok and viol <= 0.0, phase=self.phase, message=msg,
                   extra={"overrides": dict(self.overrides), "nao_avaliado_pelo_modelo": outside})
        return self.archive.add(r)
