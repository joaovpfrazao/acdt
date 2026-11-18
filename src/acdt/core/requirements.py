"""Open requirements registry.

A run is described by an *arbitrary subset* of user requirements. Each
requirement *type* is registered once and declares:

* its physical dimension (for unit conversion),
* which pipeline **stages** consume it (``sizing``, ``constraint``,
  ``trade``, ``check``, ``systems``, ``context``),
* the senses it accepts (``min``, ``max``, ``target``, ``objective``),
* whether it is implemented yet (unimplemented types are accepted, stored
  and reported as *not evaluated* with the reference method foreseen).

Stage consumers (constraint builders, checks, objectives) register
themselves against requirement keys in their own modules, so new
requirement types are plugged in without touching the core::

    from acdt.core.requirements import RequirementType, register_requirement
    register_requirement(RequirementType("hover_time", "time", "...", stages=("sizing",),
                                         domains=("aircraft",)))

Domain plugins (``acdt.domains.<name>``) register their built-in types and
validators (``register_validator``) on import; the core holds none.

The registry itself contains no engineering method; it is bookkeeping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from acdt.core import units

SENSES = ("min", "max", "target", "objective")
# chaves de rastreabilidade aceites em cada entrada de requisito (iguais a acdt.core.verification.TRACE_KEYS)
TRACE_KEYS = ("id", "text", "source", "source_kind", "parent", "parents", "method", "fidelity", "tolerance",
              "tolerance_source", "evaluator", "goal", "notes")


@dataclass(frozen=True)
class RequirementType:
    key: str
    dimension: str
    description: str
    stages: tuple[str, ...]
    senses: tuple[str, ...] = ("min", "max", "target")
    implemented: bool = True
    reference: str = ""
    params: tuple[str, ...] = ()  # optional qualifiers, e.g. altitude, speed
    choices: tuple[str, ...] = ()  # for category-type requirements
    domains: tuple[str, ...] = ("core",)  # domain plugins that use this type (shared types allowed)


@dataclass
class Requirement:
    key: str
    sense: str
    value: Any  # SI float, or str for categories; for objective: "minimize"/"maximize"
    unit: str = ""
    raw: Any = None
    params: dict[str, float] = field(default_factory=dict)  # SI qualifiers
    weight: float = 1.0
    # rastreabilidade (acdt.core.verification): id, text, source, source_kind, parent(s), method, fidelity,
    # tolerance, tolerance_source, evaluator, goal, notes — não mudam o dimensionamento
    trace: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> RequirementType:
        return REGISTRY[self.key]

    def describe(self) -> str:
        if self.sense == "objective":
            return f"{self.key}: {self.value}"
        q = "" if not self.params else " @ " + ", ".join(f"{k}={v:g}" for k, v in self.params.items())
        return f"{self.key} {self.sense} {self.raw} {self.unit}{q}".strip()


REGISTRY: dict[str, RequirementType] = {}
_HANDLERS: dict[str, dict[str, Callable[..., Any]]] = {"constraint": {}, "check": {}, "objective": {}}


def register_requirement(rt: RequirementType, overwrite: bool = False) -> RequirementType:
    if rt.key in REGISTRY and not overwrite:
        raise KeyError(f"requirement type '{rt.key}' already registered")
    REGISTRY[rt.key] = rt
    return rt


def register_handler(stage: str, key: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: register a stage consumer (constraint builder, check, objective)."""

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _HANDLERS.setdefault(stage, {})[key] = fn
        return fn

    return deco


def handlers(stage: str) -> dict[str, Callable[..., Any]]:
    return _HANDLERS.get(stage, {})


_VALIDATORS: dict[str, list[Callable[..., Any]]] = {}


def register_validator(domain: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: register a domain-specific static validator ``fn(reqset) -> list[Issue]``."""

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _VALIDATORS.setdefault(domain, []).append(fn)
        return fn

    return deco


def types_for(domain: str) -> dict[str, RequirementType]:
    return {k: v for k, v in REGISTRY.items() if domain in v.domains or "core" in v.domains}


class RequirementError(ValueError):
    pass


def parse_requirement(key: str, spec: Any) -> Requirement:
    """Parse one YAML entry.

    Accepted forms::

        endurance: {min: 2, unit: h}
        cruise_speed: {target: 22, unit: m/s, altitude: {value: 1000, unit: m}}
        unit_cost: {objective: minimize}
        unit_cost: {max: 150, unit: kUSD}
        propulsion_type: electric
        payload_mass: 3          # bare number -> target in default SI unit
        takeoff_ground_roll: {max: 300, unit: m, id: MIS-TO-01, source: missao, method: analise,
                              fidelity: N1, tolerance: 0.02, evaluator: perf:takeoff_ground_roll}

    The traceability keys (``TRACE_KEYS``: id, text, source, …) go to ``Requirement.trace`` and are read by
    :mod:`acdt.core.verification`; they never change the analysis.
    """
    if key not in REGISTRY:
        import difflib

        sugg = difflib.get_close_matches(key, REGISTRY, n=3)
        raise RequirementError(f"Unknown requirement '{key}'. Did you mean {sugg}? "
                               f"Register new types with acdt.core.requirements.register_requirement().")
    rt = REGISTRY[key]
    trace: dict[str, Any] = {}
    if isinstance(spec, dict):
        spec = dict(spec)
        trace = {k: spec.pop(k) for k in TRACE_KEYS if k in spec}
    if rt.dimension == "category":
        val = spec if isinstance(spec, str) else (spec or {}).get("target", (spec or {}).get("value"))
        if rt.choices and val not in rt.choices:
            raise RequirementError(f"{key}: '{val}' not in {rt.choices}")
        return Requirement(key, "target", val, raw=val, trace=trace)
    if not isinstance(spec, dict):
        spec = {"target": spec}
    spec = dict(spec)
    explicit_unit = spec.get("unit")
    unit = spec.pop("unit", units.default_unit(rt.dimension))
    weight = float(spec.pop("weight", 1.0))
    params: dict[str, float] = {}
    for p in rt.params:
        if p in spec:
            pv = spec.pop(p)
            dim = {"altitude": "length", "quantity": "dimensionless"}.get(p, "speed")
            if isinstance(pv, (dict, str)):  # {value, unit} ou "3000 m" (acdt.core.quantities)
                params[p] = _qty_si(pv, dim, f"{key}.{p}")[0]
            else:
                params[p] = float(pv)
    if "value" in spec:
        spec["target"] = spec.pop("value")
    senses = [s for s in SENSES if s in spec]
    if len(senses) != 1 or spec.keys() - set(senses):
        raise RequirementError(f"{key}: give exactly one of {SENSES} (+unit, qualifiers {rt.params}); got {list(spec)}")
    sense = senses[0]
    if sense not in rt.senses:
        raise RequirementError(f"{key}: sense '{sense}' not allowed (allowed: {rt.senses})")
    raw = spec[sense]
    if sense == "objective":
        if raw not in ("minimize", "maximize"):
            raise RequirementError(f"{key}: objective must be 'minimize' or 'maximize'")
        return Requirement(key, sense, raw, unit, raw, params, weight, trace)
    if isinstance(raw, str):  # "150 kg", "10 h": unidade escrita no valor (acdt.core.quantities; docs/DADOS.md)
        val, raw, unit = _qty_si(raw if explicit_unit is None else {"value": raw, "unit": explicit_unit},
                                 rt.dimension, f"{key}.{sense}")
        return Requirement(key, sense, val, unit, raw, params, weight, trace)
    try:
        val = units.to_si(raw, unit, rt.dimension)
    except units.UnitError as e:
        raise RequirementError(f"{key}: {e}") from e
    return Requirement(key, sense, val, unit, raw, params, weight, trace)


def _qty_si(v: Any, dimension: str, where: str) -> tuple[float, float, str]:
    from acdt.core.quantities import to_dimension_si
    try:
        return to_dimension_si(v, dimension, where)
    except units.UnitError as e:
        raise RequirementError(str(e)) from e


@dataclass
class Issue:
    severity: str  # "error" | "warning" | "info"
    message: str
    keys: tuple[str, ...] = ()


class RequirementSet:
    """A collection of parsed requirements with lookup helpers and validation."""

    def __init__(self, reqs: list[Requirement], domain: str | None = None):
        self.reqs = reqs
        self.domain = domain

    @classmethod
    def from_dict(cls, d: dict[str, Any], domain: str | None = None) -> "RequirementSet":
        out = []
        for k, v in (d or {}).items():
            if isinstance(v, list):  # several bounds on the same quantity
                out += [parse_requirement(k, x) for x in v]
            else:
                out.append(parse_requirement(k, v))
        return cls(out, domain)

    def __iter__(self) -> Iterator[Requirement]:
        return iter(self.reqs)

    def get(self, key: str, sense: str | None = None) -> Requirement | None:
        for r in self.reqs:
            if r.key == key and (sense is None or r.sense == sense):
                return r
        return None

    def value(self, key: str, default: Any = None, sense: str | None = None) -> Any:
        r = self.get(key, sense)
        return default if r is None else r.value

    def by_stage(self, stage: str) -> list[Requirement]:
        return [r for r in self.reqs if stage in r.type.stages]

    def objectives(self) -> list[Requirement]:
        return [r for r in self.reqs if r.sense == "objective"]

    def validate(self) -> list[Issue]:
        """Static consistency checks before any analysis (cheap, no physics beyond
        trivial orderings). Physics-based infeasibility is detected downstream."""
        issues: list[Issue] = []
        by_key: dict[str, list[Requirement]] = {}
        for r in self.reqs:
            by_key.setdefault(r.key, []).append(r)
            if not r.type.implemented:
                issues.append(Issue("warning", f"'{r.key}' accepted but not evaluated yet "
                                    f"(foreseen method: {r.type.reference})", (r.key,)))
        for k, rs in by_key.items():
            mins = [r.value for r in rs if r.sense == "min"]
            maxs = [r.value for r in rs if r.sense == "max"]
            tgts = [r.value for r in rs if r.sense == "target" and isinstance(r.value, (int, float))]
            if mins and maxs and max(mins) > min(maxs):
                issues.append(Issue("error", f"{k}: min {max(mins):g} > max {min(maxs):g} (SI)", (k,)))
            for t in tgts:
                if (mins and t < max(mins)) or (maxs and t > min(maxs)):
                    issues.append(Issue("error", f"{k}: target {t:g} outside its own min/max bounds (SI)", (k,)))
        for fn in (_VALIDATORS.get(self.domain, []) if self.domain else
                   [f for fs in _VALIDATORS.values() for f in fs]):
            issues += fn(self)
        return issues
