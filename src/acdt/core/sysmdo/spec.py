"""Especificação YAML do MDO de sistema (``mdo:``) → :class:`MDOSpec`. Ver docs/MDO.md."""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from . import expr as E

STRATEGIES = ("slsqp", "epsilon", "nsga2", "ga", "doe")
POLICIES = ("passa", "no_limite", "limiar")
SCHEMA = "acdt.mdo/1"


class MDOSpecError(ValueError):
    pass


@dataclass
class DesignVar:
    path: str
    kind: str  # continuous | integer | discrete
    lower: float = math.nan
    upper: float = math.nan
    x0: Any = None
    values: list[Any] = field(default_factory=list)  # discretas
    placement: str = "outer"  # discretas/inteiras: outer (ciclo exterior) | inner (GA/NSGA-II/DOE por índice)
    source: str = ""

    @property
    def name(self) -> str:
        return self.path

    @property
    def continuous(self) -> bool:
        return self.kind == "continuous"

    @property
    def inner(self) -> bool:
        return self.kind == "continuous" or self.placement == "inner"

    def choices(self) -> list[Any]:
        if self.kind == "discrete":
            return list(self.values)
        if self.kind == "integer":
            return list(range(int(self.lower), int(self.upper) + 1))
        raise MDOSpecError(f"{self.path}: variável contínua não tem escolhas")


@dataclass
class Objective:
    metric: str
    sense: str = "min"  # min | max
    ref: float | None = None
    label: str = ""

    @property
    def sign(self) -> float:
        return 1.0 if self.sense == "min" else -1.0


@dataclass
class MetricConstraint:
    metric: str
    lower: float | None = None
    upper: float | None = None
    source: str = ""


@dataclass
class Closure:
    """Fecho por iteração de ponto fixo de uma variável discreta (p. ex. tamanho da frota)."""

    name: str
    x0: float
    update: str  # expressão nas métricas do ótimo interior + ``name`` → novo valor
    apply: dict[str, str] = field(default_factory=dict)  # caminho → expressão em ``name`` e constantes
    max_iter: int = 6
    source: str = ""


@dataclass
class Robust:
    inputs: list[dict[str, Any]]
    k: float = 2.0
    n: int = 256
    n_train: int | None = None
    q2_min: float = 0.95
    seed: int = 0
    metrics: list[str] = field(default_factory=list)  # → métricas ``robust:<m>`` = média + k·σ
    p_pass: dict[str, float] = field(default_factory=dict)  # requisito → P(passa) mínima
    source: str = ""


@dataclass
class MDOSpec:
    design_vars: list[DesignVar]
    objectives: list[Objective]
    req_select: list[str] | str = "all"
    req_exclude: list[str] = field(default_factory=list)
    policy: str = "passa"
    metric_constraints: list[MetricConstraint] = field(default_factory=list)
    strategy: str = "slsqp"
    options: dict[str, Any] = field(default_factory=dict)
    derived: dict[str, str] = field(default_factory=dict)
    constants: dict[str, float] = field(default_factory=dict)
    outer_combos: list[dict[str, Any]] | None = None
    closure: Closure | None = None
    robust: Robust | None = None
    model: dict[str, Any] = field(default_factory=dict)
    fixed: dict[str, Any] = field(default_factory=dict)  # sobreposições fixas do estudo (p. ex. modo de reescala)
    pressupostos: list[str] = field(default_factory=list)

    @property
    def inner_vars(self) -> list[DesignVar]:
        return [d for d in self.design_vars if d.inner]

    @property
    def outer_vars(self) -> list[DesignVar]:
        return [d for d in self.design_vars if not d.inner]

    def combos(self) -> list[dict[str, Any]]:
        """Combinações do ciclo exterior: as explícitas ou o produto completo das variáveis exteriores."""
        if self.outer_combos is not None:
            return [dict(c) for c in self.outer_combos]
        ov = self.outer_vars
        if not ov:
            return [{}]
        return [dict(zip([d.path for d in ov], vals)) for vals in itertools.product(*[d.choices() for d in ov])]


def _num(x: Any, what: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(float(x)):
        raise MDOSpecError(f"{what}: valor numérico finito obrigatório (recebido {x!r})")
    return float(x)


def parse_spec(d: Mapping[str, Any], nominal: Callable[[str], float | None] | None = None) -> MDOSpec:
    """``mdo:`` → :class:`MDOSpec`. ``nominal(path)`` dá o valor de partida por omissão das variáveis contínuas."""
    d = dict(d.get("mdo", d)) if isinstance(d, Mapping) else {}
    pres: list[str] = []
    dvs: list[DesignVar] = []
    for e in d.get("design_variables") or []:
        path = str(e.get("path") or "").strip()
        if not path:
            raise MDOSpecError("variável de projeto sem 'path'")
        kind = str(e.get("type", "continuous")).lower()
        if kind not in ("continuous", "integer", "discrete"):
            raise MDOSpecError(f"{path}: type tem de ser continuous | integer | discrete")
        placement = str(e.get("placement", "outer")).lower()
        if placement not in ("outer", "inner"):
            raise MDOSpecError(f"{path}: placement tem de ser outer | inner")
        dv = DesignVar(path=path, kind=kind, placement=placement, source=str(e.get("source") or ""))
        if kind == "discrete":
            vals = list(e.get("values") or [])
            if len(vals) < 1:
                raise MDOSpecError(f"{path}: variável discreta precisa de 'values'")
            dv.values = vals
            dv.lower, dv.upper = 0.0, float(len(vals) - 1)
            dv.x0 = e.get("x0", vals[0])
        else:
            dv.lower, dv.upper = _num(e.get("lower"), f"{path}.lower"), _num(e.get("upper"), f"{path}.upper")
            if not dv.lower < dv.upper:
                raise MDOSpecError(f"{path}: lower < upper")
            x0 = e.get("x0")
            if x0 is None and nominal is not None:
                x0 = nominal(path)
                if x0 is None:
                    x0 = 0.5 * (dv.lower + dv.upper)
                    pres.append(f"{path}: sem valor nominal na missão; partida no meio do intervalo")
            elif x0 is None:
                x0 = 0.5 * (dv.lower + dv.upper)
            x0f = min(max(_num(x0, f"{path}.x0"), dv.lower), dv.upper)
            dv.x0 = int(round(x0f)) if kind == "integer" else x0f
            if kind == "integer" and placement == "outer" and dv.upper - dv.lower > 50:
                raise MDOSpecError(f"{path}: inteira exterior com mais de 51 valores — use placement: inner")
        if not dv.source:
            pres.append(f"{path}: limites sem origem declarada (PRESSUPOSTO do estudo)")
        dvs.append(dv)
    if not dvs:
        raise MDOSpecError("mdo.design_variables vazio")
    if len({d.path for d in dvs}) != len(dvs):
        raise MDOSpecError("variável de projeto repetida")
    objs: list[Objective] = []
    for o in d.get("objectives") or []:
        if isinstance(o, str):
            o = {"metric": o}
        sense = str(o.get("sense", "min")).lower()
        if sense not in ("min", "max"):
            raise MDOSpecError(f"objetivo {o.get('metric')}: sense min | max")
        ref = o.get("ref")
        objs.append(Objective(metric=str(o["metric"]), sense=sense, ref=None if ref is None else _num(ref, "ref"),
                              label=str(o.get("label") or "")))
    if not objs:
        raise MDOSpecError("mdo.objectives vazio")
    c = dict(d.get("constraints") or {})
    reqs = c.get("requirements", "all")
    if reqs not in ("all", "none") and not isinstance(reqs, list):
        raise MDOSpecError("constraints.requirements: all | none | [IDs]")
    policy = str(c.get("policy", "passa"))
    if policy not in POLICIES:
        raise MDOSpecError(f"constraints.policy: {POLICIES}")
    mcs = []
    for m in c.get("metrics") or []:
        lo, up = m.get("lower"), m.get("upper")
        if lo is None and up is None:
            raise MDOSpecError(f"restrição {m.get('metric')}: lower e/ou upper")
        mcs.append(MetricConstraint(metric=str(m["metric"]), lower=None if lo is None else _num(lo, "lower"),
                                    upper=None if up is None else _num(up, "upper"), source=str(m.get("source") or "")))
        if not m.get("source"):
            pres.append(f"restrição {m['metric']} sem origem declarada (PRESSUPOSTO)")
    strategy = str(d.get("strategy", "slsqp" if len(objs) == 1 else "nsga2")).lower()
    if strategy not in STRATEGIES:
        raise MDOSpecError(f"strategy: {STRATEGIES}")
    if strategy in ("slsqp", "ga") and len(objs) > 1:
        raise MDOSpecError(f"strategy {strategy} é mono-objetivo; para vários use nsga2, epsilon ou doe")
    if strategy == "epsilon" and len(objs) != 2:
        raise MDOSpecError("strategy epsilon: exatamente 2 objetivos")
    if strategy in ("slsqp", "epsilon") and any(dv.placement == "inner" and not dv.continuous for dv in dvs):
        raise MDOSpecError("SLSQP/ε-restrição só com variáveis interiores contínuas (discretas: placement outer)")
    derived = {str(k): str(v) for k, v in (d.get("derived") or {}).items()}
    for k, v in derived.items():
        E.compile_expr(v)
    consts = {str(k): _num(v, f"constants.{k}") for k, v in (d.get("constants") or {}).items()}
    if d.get("constants") and not d.get("constants_source"):
        pres.append("constantes do estudo sem origem declarada (constants_source; PRESSUPOSTO)")
    combos = d.get("outer", {}).get("combos") if isinstance(d.get("outer"), Mapping) else None
    clo = None
    if d.get("closure"):
        cc = dict(d["closure"])
        clo = Closure(name=str(cc["name"]), x0=_num(cc["x0"], "closure.x0"), update=str(cc["update"]),
                      apply={str(k): str(v) for k, v in (cc.get("apply") or {}).items()},
                      max_iter=int(cc.get("max_iter", 6)), source=str(cc.get("source") or ""))
        E.compile_expr(clo.update)
        for v in clo.apply.values():
            E.compile_expr(v)
        if not clo.source:
            pres.append(f"fecho '{clo.name}': regra de atualização sem origem declarada (PRESSUPOSTO)")
    rob = None
    if d.get("robust"):
        rr = dict(d["robust"])
        if not rr.get("inputs"):
            raise MDOSpecError("robust.inputs vazio")
        rob = Robust(inputs=[dict(x) for x in rr["inputs"]], k=float(rr.get("k", 2.0)), n=int(rr.get("n", 256)),
                     n_train=None if rr.get("n_train") is None else int(rr["n_train"]),
                     q2_min=float(rr.get("q2_min", 0.95)), seed=int(rr.get("seed", 0)),
                     metrics=[str(x) for x in rr.get("metrics") or []],
                     p_pass={str(k): float(v) for k, v in (rr.get("p_pass") or {}).items()},
                     source=str(rr.get("source") or ""))
        if "k" not in rr:
            pres.append("robusto: k = 2 por omissão (PRESSUPOSTO)")
    if "feas_tol" not in (d.get("options") or {}):
        pres.append("viabilidade com margem relativa ≥ −1e-6 (ruído numérico dos fechos iterativos; options.feas_tol)")
    return MDOSpec(design_vars=dvs, objectives=objs, req_select=reqs if isinstance(reqs, list) else str(reqs),
                   req_exclude=[str(x) for x in c.get("exclude") or []], policy=policy, metric_constraints=mcs,
                   strategy=strategy, options=dict(d.get("options") or {}), derived=derived, constants=consts,
                   outer_combos=[dict(x) for x in combos] if combos else None, closure=clo, robust=rob,
                   model=dict(d.get("model") or {}), fixed=dict(d.get("fixed") or {}), pressupostos=pres)


def describe_vars(dvs: Sequence[DesignVar]) -> list[dict[str, Any]]:
    out = []
    for v in dvs:
        e: dict[str, Any] = {"path": v.path, "type": v.kind, "placement": "inner" if v.inner else "outer",
                             "source": v.source or "PRESSUPOSTO"}
        if v.kind == "discrete":
            e["values"] = v.values
        else:
            e.update(lower=v.lower, upper=v.upper, x0=v.x0)
        out.append(e)
    return out
