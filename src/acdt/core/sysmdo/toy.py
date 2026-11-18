"""Modelos de sistema analíticos (``SystemModel``) para verificar o construtor de MDO e para modelos Python do
utilizador: uma função ``f(params) -> métricas`` + requisitos rastreáveis cujo valor é uma métrica."""
from __future__ import annotations

import math
from typing import Any, Callable, Mapping, Sequence

from acdt.core.sensitivity.study import Sample
from acdt.core.verification import TracedRequirement


class FunctionModel:
    """``fn(params)`` com ``params`` = valores fixos ⊕ sobreposições ⊕ ponto. ``reqs``: requisitos com
    ``quantity`` = nome da métrica que dá o valor; o limiar pode vir de um parâmetro (``threshold_param``)."""

    def __init__(self, fn: Callable[[Mapping[str, Any]], Mapping[str, float]], params: Mapping[str, Any],
                 reqs: Sequence[Mapping[str, Any]] = (), name: str = "função analítica"):
        self.fn, self.params, self.reqs, self.name = fn, dict(params), [dict(r) for r in reqs], name
        self.n_calls = 0

    def nominal(self, path: str) -> float | None:
        v = self.params.get(path)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    def with_overrides(self, overrides: Mapping[str, Any]) -> "FunctionModel":
        m = FunctionModel(self.fn, {**self.params, **overrides}, self.reqs, self.name)
        return m

    def requirement_defs(self) -> list[Any]:
        out = []
        for r in self.reqs:
            thr = r.get("threshold")
            if r.get("threshold_param"):
                thr = float(self.params[str(r["threshold_param"])])
            out.append(TracedRequirement(id=str(r["id"]), text=str(r.get("text", r["id"])),
                                         quantity=str(r["metric"]), comparison=str(r["comparison"]), threshold=thr,
                                         tolerance=float(r.get("tolerance", 0.0))))
        return out

    def run(self, points: Sequence[Mapping[str, float]]) -> list[Sample]:
        out = []
        for p in points:
            self.n_calls += 1
            try:
                met = {k: float(v) for k, v in self.fn({**self.params, **p}).items()}
            except (ValueError, ZeroDivisionError, OverflowError) as e:
                out.append(Sample(False, message=str(e)))
                continue
            rq: dict[str, dict[str, Any]] = {}
            from acdt.core.verification import Evidence, classify

            for r in self.requirement_defs():
                v = met.get(r.quantity)
                if v is None or not math.isfinite(v):
                    rq[r.id] = {"status": "desconhecido", "value": None}
                else:
                    rq[r.id] = {"status": classify(r, Evidence(value=v))[0], "value": v, "threshold": r.threshold,
                                "tolerance": r.tolerance}
            out.append(Sample(True, met, rq))
        return out

    def describe(self) -> dict[str, Any]:
        return {"domain": "analitico", "text": self.name}


def sellar(p: Mapping[str, Any]) -> dict[str, float]:
    """Sellar, Batill & Renaud (AIAA 96-0714, 1996), MDA resolvido por Gauss–Seidel (formulação MDF)."""
    x, z1, z2 = float(p["x"]), float(p["z1"]), float(p["z2"])
    y1, y2 = 1.0, 1.0
    for _ in range(200):
        y1n = z1 ** 2 + z2 + x - 0.2 * y2
        y2n = math.sqrt(max(y1n, 0.0)) + z1 + z2
        if abs(y1n - y1) + abs(y2n - y2) < 1e-13:
            y1, y2 = y1n, y2n
            break
        y1, y2 = y1n, y2n
    return {"obj": x ** 2 + z2 + y1 + math.exp(-y2), "y1": y1, "y2": y2}


def zdt1(p: Mapping[str, Any]) -> dict[str, float]:
    """ZDT1 (Zitzler, Deb & Thiele, Evol. Comput. 8(2):173–195, 2000); frente verdadeira f₂ = 1 − √f₁."""
    n = int(p.get("n", 5))
    xs = [float(p[f"x{i}"]) for i in range(1, n + 1)]
    f1 = xs[0]
    g = 1.0 + 9.0 * sum(xs[1:]) / (n - 1)
    return {"f1": f1, "f2": g * (1.0 - math.sqrt(f1 / g))}
