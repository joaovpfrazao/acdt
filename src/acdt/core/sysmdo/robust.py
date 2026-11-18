"""Objetivo/restrição robustos em modo barato (só sobre substituto): média + k·σ e P(passa).

O modelo verdadeiro corre ``n_train`` vezes num LHS conjunto (variáveis de projeto contínuas interiores × entradas
incertas); cada métrica pedida ganha a superfície de resposta quadrática de ``acdt uq`` (aceite só com Q² por PRESS
≥ ``q2_min``; Allen 1974). Em cada projeto avaliado, as entradas incertas são amostradas (LHS, números aleatórios
comuns, semente fixa) e a média e σ saem do substituto; ``robust:<m>`` = média + k·σ (formulação média-desvio do
projeto robusto, Taguchi; Du & Chen, J. Mech. Des. 122(4), 2000). P(passa) de um requisito numérico = fração das
amostras classificadas ``passa`` pela regra de sempre (``verification.classify``) sobre o valor previsto.
Substituto rejeitado → a métrica robusta fica sem valor (desconhecida, nunca zero) e o relatório diz porquê.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from acdt.core.sensitivity import distributions as D
from acdt.core.sensitivity import surrogate as SG

from .spec import MDOSpec


class RobustSurrogate:
    def __init__(self, spec: MDOSpec, model: Any, reqdefs: Sequence[Any]):
        assert spec.robust is not None
        self.spec, self.rb = spec, spec.robust
        self.inputs = [D.parse_input(e, model.nominal(str(e.get("path")))) for e in self.rb.inputs]
        self.dvs = [d for d in spec.inner_vars if d.kind == "continuous"]
        self.reqs = {r.id: r for r in reqdefs}
        self.model = model
        self.trained: dict[tuple[Any, ...], Any] = {}
        self.info: dict[str, Any] = {}
        rng = np.random.default_rng(self.rb.seed + 7)
        u = D.unit_sample(self.rb.n, len(self.inputs), "lhs", rng)
        self.U = np.column_stack([inp.ppf(u[:, j]) for j, inp in enumerate(self.inputs)]) if self.inputs else \
            np.zeros((self.rb.n, 0))

    def _metrics(self) -> list[str]:
        return list(self.rb.metrics) + [f"req:{r}" for r in self.rb.p_pass]

    def _train(self, disc: Mapping[str, Any]) -> Any:
        k = tuple(sorted((a, repr(b)) for a, b in disc.items()))
        if k in self.trained:
            return self.trained[k]
        names = [d.path for d in self.dvs] + [i.path for i in self.inputs]
        nt = self.rb.n_train or max(2 * SG.n_terms(len(names), False), 20)
        rng = np.random.default_rng(self.rb.seed + 3)
        u = D.unit_sample(nt, len(names), "lhs", rng)
        cols = [d.lower + u[:, j] * (d.upper - d.lower) for j, d in enumerate(self.dvs)]
        cols += [inp.ppf(u[:, len(self.dvs) + j]) for j, inp in enumerate(self.inputs)]
        x = np.column_stack(cols)
        pts = [{names[j]: float(x[i, j]) for j in range(len(names))} for i in range(nt)]
        m = self.model.with_overrides(disc) if disc else self.model
        samples = m.run(pts)
        sur = SG.build(x, [s.metrics if s.ok else None for s in samples], names, self.rb.q2_min, self._metrics())
        self.trained[k] = sur
        self.info[repr(dict(disc)) or "{}"] = {"n_train": nt, "seed": self.rb.seed + 3,
                                              "n_failed": sum(1 for s in samples if not s.ok), **sur.report()}
        return sur

    def evaluate(self, pts: Sequence[Mapping[str, float]], disc: Mapping[str, Any]) -> list[dict[str, Any]]:
        from acdt.core.verification import Evidence, classify

        sur = self._train(disc)
        out: list[dict[str, Any]] = []
        for p in pts:
            q = [{**{d.path: float(p[d.path]) for d in self.dvs},
                  **{inp.path: float(self.U[i, j]) for j, inp in enumerate(self.inputs)}} for i in range(self.U.shape[0])]
            pred = sur.predict(q)
            met: dict[str, float | None] = {}
            for mname in self.rb.metrics:
                y = pred.get(mname)
                met[f"robust:{mname}"] = None if y is None else float(np.mean(y) + self.rb.k * np.std(y, ddof=1))
                met[f"mean:{mname}"] = None if y is None else float(np.mean(y))
                met[f"std:{mname}"] = None if y is None else float(np.std(y, ddof=1))
            pp: dict[str, float | None] = {}
            for rid in self.rb.p_pass:
                y = pred.get(f"req:{rid}")
                r = self.reqs.get(rid)
                if y is None or r is None:
                    pp[rid] = None
                    continue
                n_ok = sum(1 for v in y if classify(r, Evidence(value=float(v)))[0] == "passa")
                pp[rid] = n_ok / len(y)
            out.append({"metrics": met, "p_pass": pp})
        return out
