"""Pipeline orchestrator and design-state model (domain-agnostic).

A *domain* (``acdt.domains.<name>``) registers a :class:`Domain` with an ordered
list of :class:`Stage` objects. Each stage reads and writes a shared
:class:`DesignState` and may stop the pipeline (e.g. infeasible requirements).
Iterative couplings (MDA) live *inside* stages or in :mod:`acdt.core.mdo`; the
orchestrator itself is deliberately a plain sequence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from acdt.core.requirements import Issue


class InfeasibleError(RuntimeError):
    """Requirements are inconsistent or cannot be met (raised by domain stages)."""


@dataclass
class DesignState:
    """Everything that flows between stages/phases. ``data`` holds the stage outputs
    under stable keys (``spec``, ``result``, ``systems``, ``report_path`` ...)."""

    domain: str
    data: dict[str, Any] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    stopped: bool = False

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v

    def get(self, k, default=None):
        return self.data.get(k, default)


@dataclass
class Stage:
    name: str
    run: Callable[[DesignState], None]
    enabled: Callable[[DesignState], bool] = lambda s: True
    description: str = ""


@dataclass
class Domain:
    name: str
    description: str
    load_spec: Callable[[str], Any]
    stages: list[Stage]
    references: list[str] = field(default_factory=list)


DOMAINS: dict[str, Domain] = {}


def register_domain(d: Domain) -> Domain:
    DOMAINS[d.name] = d
    return d


def get_domain(name: str) -> Domain:
    if name not in DOMAINS:
        import importlib

        importlib.import_module(f"acdt.domains.{name}")  # plugins register themselves on import
    return DOMAINS[name]


def run_pipeline(domain: str, spec_path, **options) -> DesignState:
    """Run the domain stages. ``spec_path``: a spec file, or an already-loaded spec object (e.g. the
    modified copy used by the optimiser's verification re-run)."""
    d = get_domain(domain)
    spec = d.load_spec(spec_path) if isinstance(spec_path, (str, bytes)) or hasattr(spec_path, "__fspath__") \
        else spec_path
    import time

    t0 = time.time()
    st = DesignState(domain, {"spec": spec, "options": options})
    for stage in d.stages:
        if st.stopped:
            break
        if stage.enabled(st):
            stage.run(st)
            st.log.append(stage.name)
    out = options.get("output")
    if out is not None:  # proveniência ao lado das saídas (acdt.core.provenance); não muda nenhum resultado
        from acdt.core import provenance

        src = [spec_path] if isinstance(spec_path, str) or hasattr(spec_path, "__fspath__") else []
        provenance.note_output(out, inputs=src, entry_point=f"run_pipeline({domain})", since=t0)
    return st
