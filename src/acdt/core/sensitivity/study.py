"""Estudo de incerteza + sensibilidade (domínio-agnóstico): ``acdt uq``; docs/INCERTEZA.md.

Fluxo: (1) corrida nominal determinística (a matriz de verificação de sempre); (2) propagação Monte Carlo/LHS das
entradas incertas declaradas, com semente, percentis P5/P50/P95 + IC, média corrida e critério de convergência;
intervalos (incerteza epistémica) num ciclo exterior sobre os extremos → resultados em [mín, máx];
(3) P(passa) por requisito e **estado probabilístico** (coluna nova; o estado determinístico não muda);
(4) sensibilidade global Sobol' e/ou Morris (opcionais); (5) JSON + Markdown (+ PNG) na pasta de saída.

O domínio fornece um :class:`Model`: ``nominal(path)`` (valor nominal de um caminho), ``run(points)`` (lista de
:class:`Sample`) e ``describe()``. As semente(s) vão para o registo de proveniência (``acdt.provenance/1``).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import numpy as np

from . import distributions as D
from . import gsa, stats
from . import surrogate as SGx

SCHEMA = "acdt.uq/1"
DEFAULT_TARGET = 0.95  # PRESSUPOSTO quando o utilizador não declara a probabilidade-alvo (marcado no relatório)
DEFAULT_CONF = 0.95
DEFAULT_REL_TOL = 0.01  # PRESSUPOSTO: SE/média ≤ 1 % para dizer que a média convergiu
UQ_FILES = ("uq.json", "uq.md")


@dataclass
class Sample:
    """Uma avaliação do modelo. ``ok=False`` = falhou (não convergiu / exceção): conta, nunca vale zero."""

    ok: bool
    metrics: dict[str, float] = field(default_factory=dict)
    requirements: dict[str, dict[str, Any]] = field(default_factory=dict)  # id → {status, value}
    message: str = ""


class Model(Protocol):
    def nominal(self, path: str) -> float | None: ...

    def run(self, points: Sequence[Mapping[str, float]]) -> list[Sample]: ...

    def describe(self) -> dict[str, Any]: ...

    def requirement_defs(self) -> list[Any]: ...  # TracedRequirement (para classificar valores do substituto)


@dataclass
class UQSpec:
    inputs: list[D.UncertainInput]
    n: int = 64
    method: str = "lhs"
    seed: int = 0
    confidence: float = DEFAULT_CONF
    target: float = DEFAULT_TARGET
    target_source: str = ""
    rel_tol: float = DEFAULT_REL_TOL
    percentiles: tuple[float, ...] = stats.PERCENTILES
    metrics: list[str] | None = None
    correlation: D.Correlation | None = None
    sobol: dict[str, Any] | None = None
    morris: dict[str, Any] | None = None
    targets: dict[str, float] = field(default_factory=dict)  # alvo por requisito
    excluded: list[dict[str, Any]] = field(default_factory=list)  # entradas pedidas mas não propagadas (porquê)
    surrogate: dict[str, Any] | None = None  # {n_train, q2_min, seed} → superfície de resposta (surrogate.py)
    pressupostos: list[str] = field(default_factory=list)


def parse_spec(d: Mapping[str, Any], nominal: Any, extra_inputs: Sequence[D.UncertainInput] = (),
               excluded: Sequence[Mapping[str, Any]] = ()) -> UQSpec:
    """``uncertainty:`` da missão (ou ficheiro próprio) → :class:`UQSpec`. ``nominal(path)`` dá valores nominais."""
    raw_inputs = list(d.get("inputs") or [])
    ins: list[D.UncertainInput] = []
    for e in raw_inputs:
        path = str(e.get("path") or e.get("param") or "")
        ins.append(D.parse_input(e, nominal(path) if path else None))
    ins += list(extra_inputs)
    seen: set[str] = set()
    for i in ins:
        if i.path in seen:
            raise D.UncertaintySpecError(f"entrada incerta repetida: {i.path}")
        seen.add(i.path)
    if not ins:
        raise D.UncertaintySpecError("nenhuma entrada incerta declarada (uncertainty.inputs)")
    pres: list[str] = []
    target = d.get("target_probability")
    tsrc = str(d.get("target_source") or "")
    if target is None:
        target = DEFAULT_TARGET
        pres.append(f"probabilidade-alvo {DEFAULT_TARGET:g} por omissão (PRESSUPOSTO: declare "
                    f"uncertainty.target_probability e a origem)")
    elif not tsrc:
        pres.append(f"probabilidade-alvo {float(target):g} sem origem declarada (PRESSUPOSTO)")
    if "rel_tol" not in d:
        pres.append(f"tolerância de convergência SE/média ≤ {DEFAULT_REL_TOL:g} por omissão (PRESSUPOSTO)")
    for i in ins:
        if i.pressuposto:
            pres.append(f"{i.label}: {i.source}")
    targets = {str(k): float(v) for k, v in (d.get("requirement_targets") or {}).items()}
    sob = d.get("sobol")
    mor = d.get("morris")
    sens = d.get("sensitivity") or {}
    sob = sob if sob is not None else sens.get("sobol")
    mor = mor if mor is not None else sens.get("morris")
    met = d.get("metrics")
    sur = d.get("surrogate")
    spec = UQSpec(inputs=ins, n=int(d.get("n", 64)), method=str(d.get("method", "lhs")), seed=int(d.get("seed", 0)),
                  confidence=float(d.get("confidence", DEFAULT_CONF)), target=float(target), target_source=tsrc,
                  rel_tol=float(d.get("rel_tol", DEFAULT_REL_TOL)),
                  percentiles=tuple(float(p) for p in (d.get("percentiles") or stats.PERCENTILES)),
                  metrics=[str(m) for m in met] if met else None,
                  sobol=dict(sob) if isinstance(sob, Mapping) else ({} if sob else None),
                  morris=dict(mor) if isinstance(mor, Mapping) else ({} if mor else None),
                  targets=targets, excluded=[dict(x) for x in excluded], pressupostos=pres,
                  surrogate=dict(sur) if isinstance(sur, Mapping) else ({} if sur else None))
    if spec.surrogate is not None and "q2_min" not in spec.surrogate:
        from .surrogate import DEFAULT_Q2_MIN
        pres.append(f"substituto aceite com Q² ≥ {DEFAULT_Q2_MIN:g} por omissão (PRESSUPOSTO)")
    spec.correlation = D.parse_correlations(d.get("correlations") or [], ins)
    if not 0.0 < spec.confidence < 1.0 or not 0.0 < spec.target <= 1.0:
        raise D.UncertaintySpecError("confidence ∈ (0,1) e target_probability ∈ (0,1]")
    return spec


def _batch_eval(model: Model, base: Mapping[str, float]) -> gsa.Evaluate:
    def ev(points: list[dict[str, float]]) -> list[Mapping[str, float] | None]:
        res = model.run([{**base, **p} for p in points])
        return [s.metrics if s.ok else None for s in res]
    return ev


def _propagate(spec: UQSpec, model: Model, design: D.Design, epi: Mapping[str, float]) -> dict[str, Any]:
    rows = [{**r, **epi} for r in design.rows()]
    samples = model.run(rows)
    metrics = spec.metrics or sorted({m for s in samples if s.ok for m in s.metrics})
    summ = {}
    for m in metrics:
        vals = [s.metrics[m] for s in samples if s.ok and m in s.metrics]
        sm = stats.summarize(vals, percentiles=spec.percentiles, conf=spec.confidence, rel_tol=spec.rel_tol)
        sm["n_sem_valor"] = len(samples) - len(vals)
        summ[m] = sm
    req_ids: list[str] = []
    for s in samples:
        for rid in s.requirements:
            if rid not in req_ids:
                req_ids.append(rid)
    reqs = {}
    for rid in req_ids:
        counts: dict[str, int] = {}
        for s in samples:
            st = (s.requirements.get(rid) or {}).get("status") if s.ok else "falhou"
            key = st if st else "nao_avaliado"
            counts[key] = counts.get(key, 0) + 1
        reqs[rid] = stats.probabilistic_status(counts, len(samples), target=spec.targets.get(rid, spec.target),
                                               conf=spec.confidence)
    n_failed = sum(1 for s in samples if not s.ok)
    return {"epistemic": dict(epi), "n": len(samples), "n_failed": n_failed,
            "failures": sorted({s.message for s in samples if not s.ok and s.message})[:10],
            "summaries": summ, "requirements": reqs,
            "samples": [{"inputs": r, "ok": s.ok, "metrics": s.metrics,
                         "requirements": {k: v.get("status") for k, v in s.requirements.items()}}
                        for r, s in zip(rows, samples)]}


def _envelope(runs: Sequence[Mapping[str, Any]], spec: UQSpec) -> dict[str, Any]:
    """Com intervalos: [mín, máx] de cada estatística sobre os pontos exteriores (caixa de probabilidade)."""
    if len(runs) == 1:
        r = runs[0]
        return {"summaries": r["summaries"], "requirements": r["requirements"]}
    summ: dict[str, Any] = {}
    keys = ["mean", "std"] + [stats.pkey(p) for p in spec.percentiles]
    for m in runs[0]["summaries"]:
        items = [r["summaries"].get(m) or {} for r in runs]
        if any(i.get("status") != "ok" for i in items):
            summ[m] = {"status": "nao_avaliado", "reason": "algum ponto do intervalo sem estatística"}
            continue
        e: dict[str, Any] = {"status": "ok", "intervalo": True,
                             "converged": all(bool(i.get("converged")) for i in items)}
        for k in keys:
            vals = [float(i[k]) for i in items]
            e[k] = [min(vals), max(vals)]
        summ[m] = e
    reqs: dict[str, Any] = {}
    for rid in runs[0]["requirements"]:
        items = [r["requirements"].get(rid) or {} for r in runs]
        sts = [i.get("estado_probabilistico") for i in items]

        def rng_(key: str) -> list[float] | None:
            v = [float(i[key]) for i in items if i.get(key) is not None]
            return [min(v), max(v)] if v else None

        def ic_(key: str) -> list[float] | None:
            v = [i[key] for i in items if i.get(key) is not None]
            return [min(float(x[0]) for x in v), max(float(x[1]) for x in v)] if v else None

        if len(set(sts)) == 1 and sts[0] is not None:
            st = str(sts[0])
        elif all(s in ("desconhecido", "nao_avaliado") for s in sts):
            st = "desconhecido"
        else:
            st = "inconclusivo"
        reqs[rid] = {"estado_probabilistico": st, "intervalo": True,
                     "p_passa": rng_("p_passa"), "p_passa_ic": ic_("p_passa_ic"),
                     "p_no_limite": rng_("p_no_limite"), "p_no_limite_ic": ic_("p_no_limite_ic"),
                     "p_falha": rng_("p_falha"), "p_falha_ic": ic_("p_falha_ic"),
                     "por_ponto": sts, "alvo": items[0].get("alvo"), "confianca": items[0].get("confianca"),
                     "fonte": items[0].get("fonte", "modelo"),
                     "nota": "P em [mín, máx] sobre os extremos dos intervalos; IC = [menor limite inferior, "
                             "maior limite superior] (Ferson et al. 2003)"}
    return {"summaries": summ, "requirements": reqs}


class SurrogateModel:
    """Modelo = superfícies de resposta aceites; requisitos numéricos classificados pela regra de sempre
    (:func:`acdt.core.verification.classify`) sobre o valor previsto; o resto fica ``None`` (vem do treino)."""

    def __init__(self, sur: Any, reqs: Sequence[Any], classify_ids: set[str], base: Model):
        self.sur, self.reqs, self.ids, self.base = sur, {r.id: r for r in reqs}, classify_ids, base

    def nominal(self, path: str) -> float | None:
        return self.base.nominal(path)

    def describe(self) -> dict[str, Any]:
        d = dict(self.base.describe())
        d["text"] = "substituto quadrático (PRESS) de: " + str(d.get("text", ""))
        return d

    def requirement_defs(self) -> list[Any]:
        return list(self.reqs.values())

    def run(self, points: Sequence[Mapping[str, float]]) -> list[Sample]:
        from acdt.core.verification import Evidence, classify

        pred = self.sur.predict(points)
        out = []
        for i in range(len(points)):
            met = {m: float(v[i]) for m, v in pred.items() if math.isfinite(float(v[i]))}
            rq: dict[str, dict[str, Any]] = {}
            for rid in self.ids:
                v = met.get(f"req:{rid}")
                if v is not None:
                    st, _m, _ = classify(self.reqs[rid], Evidence(value=v))
                    rq[rid] = {"status": st, "value": v}
            out.append(Sample(True, met, rq))
        return out


def _training(spec: UQSpec, model: Model) -> dict[str, Any]:
    """Desenho LHS de treino sobre TODAS as entradas (intervalos uniformes), avaliado no modelo verdadeiro."""
    from . import surrogate as SG

    so = spec.surrogate or {}
    n = int(so.get("n_train", max(2 * SG.n_terms(len(spec.inputs), False), 20)))
    seed = int(so.get("seed", spec.seed + 3))
    rng = np.random.default_rng(seed)
    u = D.unit_sample(n, len(spec.inputs), "lhs", rng)
    # Intervalos: a propagação só os avalia nos extremos (ciclo exterior), por isso o treino tem de os conter. O LHS
    # deixa o mínimo/máximo a até 1/n do extremo → todas as amostras de propagação ficavam «fora da caixa» (100 %).
    # Coluna estratificada que inclui os extremos: permutação de {0, 1/(n−1), …, 1} (n − 1 estratos fechados).
    for j, inp in enumerate(spec.inputs):
        if inp.epistemic and n > 1:
            u[:, j] = rng.permutation(np.linspace(0.0, 1.0, n))
    x = np.column_stack([inp.ppf(u[:, j]) for j, inp in enumerate(spec.inputs)])
    names = [i.path for i in spec.inputs]
    pts = [{names[j]: float(x[i, j]) for j in range(len(names))} for i in range(n)]
    samples = model.run(pts)
    q2 = float(so.get("q2_min", SG.DEFAULT_Q2_MIN))
    sur = SG.build(x, [smp.metrics if smp.ok else None for smp in samples], names, q2, so.get("metrics"))
    return {"n": n, "seed": seed, "x": x, "points": pts, "samples": samples, "sur": sur}


def _from_training(spec: UQSpec, tr: Mapping[str, Any], prop: dict[str, Any]) -> None:
    """Saídas/requisitos sem substituto aceite: estatística das amostras de treino do modelo verdadeiro."""
    samples: list[Sample] = tr["samples"]
    acc = tr["sur"].models
    metrics = spec.metrics or sorted({m for smp in samples if smp.ok for m in smp.metrics})
    for m in metrics:
        if m in acc:
            prop["summaries"].setdefault(m, {})["fonte"] = "substituto"
            continue
        vals = [smp.metrics[m] for smp in samples if smp.ok and m in smp.metrics]
        sm = stats.summarize(vals, percentiles=spec.percentiles, conf=spec.confidence, rel_tol=spec.rel_tol)
        sm["fonte"] = "modelo (treino LHS; intervalos varridos uniformemente)"
        sm["substituto"] = tr["sur"].rejected.get(m, "não pedido")
        prop["summaries"][m] = sm
    ids: list[str] = []
    for smp in samples:
        for rid in smp.requirements:
            if rid not in ids:
                ids.append(rid)
    for rid in ids:
        cur = prop["requirements"].get(rid)
        if cur is not None and cur.get("fonte") == "substituto":
            continue
        counts: dict[str, int] = {}
        for smp in samples:
            st = (smp.requirements.get(rid) or {}).get("status") if smp.ok else "falhou"
            counts[st or "nao_avaliado"] = counts.get(st or "nao_avaliado", 0) + 1
        q = stats.probabilistic_status(counts, len(samples), target=spec.targets.get(rid, spec.target),
                                       conf=spec.confidence)
        q["fonte"] = "modelo (treino LHS)"
        prop["requirements"][rid] = q


def run_study(spec: UQSpec, model: Model, *, outdir: str | Path | None = None,
              nominal_matrix: Mapping[str, Any] | None = None, nominal_sample: Sample | None = None,
              plots: bool = True) -> dict[str, Any]:
    from acdt.core import provenance as P

    P.register_seed("uq.seed", spec.seed)
    design = D.sample(spec.inputs, spec.n, method=spec.method, seed=spec.seed, correlation=spec.correlation)
    epi_pts = design.epistemic_points or [{}]
    # intervalos fixados no centro para Sobol/Morris? Não: varridos uniformemente (rastreio) — ver gsa
    tr: dict[str, Any] | None = None
    prop_model: Model = model
    if spec.surrogate is not None:
        tr = _training(spec, model)
        P.register_seed("uq.surrogate.seed", tr["seed"])
        reqdefs = [r for r in model.requirement_defs() if r.comparison in ("min", "max", "target")]
        thr_uncertain = any(i.path.startswith("requirements.") for i in spec.inputs)
        ok_ids = set()
        for r in reqdefs:
            sts = [(smp.requirements.get(r.id) or {}).get("status") for smp in tr["samples"] if smp.ok]
            if (not thr_uncertain and sts and all(x in ("passa", "falha", "no_limite") for x in sts)
                    and f"req:{r.id}" in tr["sur"].models):
                ok_ids.add(r.id)
        prop_model = SurrogateModel(tr["sur"], reqdefs, ok_ids, model)
    runs = [_propagate(spec, prop_model, design, e) for e in epi_pts]
    if tr is not None:
        for rr in runs:
            for rid, q in rr["requirements"].items():
                if isinstance(prop_model, SurrogateModel) and rid in prop_model.ids:
                    q["fonte"] = "substituto"
            _from_training(spec, tr, rr)
            rr["samples"] = rr["samples"][:200]
    env = _envelope(runs, spec)
    out: dict[str, Any] = {
        "schema": SCHEMA, "model": model.describe(),
        "settings": {"n": spec.n, "method": design.method, "seed": spec.seed, "confidence": spec.confidence,
                     "target_probability": spec.target, "target_source": spec.target_source,
                     "requirement_targets": spec.targets, "rel_tol": spec.rel_tol,
                     "percentiles": list(spec.percentiles),
                     "correlations": ({"names": spec.correlation.names,
                                       "matrix": spec.correlation.matrix.tolist(),
                                       "source": spec.correlation.source,
                                       "method": "Iman & Conover 1982 (correlação de postos)"}
                                      if spec.correlation else None)},
        "inputs": [i.to_dict() for i in spec.inputs], "excluded_inputs": spec.excluded,
        "pressupostos": spec.pressupostos,
        "epistemic_points": epi_pts if design.epistemic_points else [],
        "nominal": ({"ok": nominal_sample.ok, "metrics": nominal_sample.metrics,
                     "requirements": nominal_sample.requirements} if nominal_sample else None),
        "propagation": {"runs": runs, **env},
        "references": [D.REF, stats.REF],
    }
    if tr is not None:
        sur = tr["sur"]
        xs = np.asarray([[float(r[n]) for n in sur.names] for r in
                         [{**row, **e} for e in epi_pts for row in design.rows()]], dtype=float) \
            if design.names else np.zeros((0, len(sur.names)))
        out["surrogate"] = {**sur.report(), "n_train": tr["n"], "seed": tr["seed"],
                            "n_train_failed": sum(1 for smp in tr["samples"] if not smp.ok),
                            "fracao_extrapolada": SGx.outside_box(xs, sur.lo, sur.hi) if xs.size else 0.0,
                            "extrapolacao_por_entrada": SGx.outside_box_per_input(xs, sur.lo, sur.hi, sur.names)
                            if xs.size else {},
                            "requisitos_pelo_substituto": sorted(prop_model.ids)
                            if isinstance(prop_model, SurrogateModel) else [],
                            "nota": "requisitos não numéricos ou sem substituto aceite: P(passa) das amostras de "
                                    "treino do modelo verdadeiro"}
        out["training_samples"] = [{"inputs": p, "ok": smp.ok, "metrics": smp.metrics, "message": smp.message,
                                    "requirements": {k: v.get("status") for k, v in smp.requirements.items()}}
                                   for p, smp in zip(tr["points"], tr["samples"])]
        gsa_model: Model = prop_model
    else:
        gsa_model = model
    if spec.sobol is not None:
        if spec.correlation is not None:
            out.setdefault("avisos", []).append("Sobol' assume entradas independentes: correlações ignoradas")
        so = spec.sobol
        out["sobol"] = gsa.sobol(spec.inputs, _batch_eval(gsa_model, {}), so.get("metrics") or spec.metrics,
                                 n=int(so.get("n", 32)), seed=int(so.get("seed", spec.seed + 1)),
                                 bootstrap=int(so.get("bootstrap", 0)), conf=spec.confidence)
        P.register_seed("uq.sobol.seed", out["sobol"]["seed"])
        for m, res in out["sobol"]["metrics"].items():
            for av in res.get("avisos") or []:
                out.setdefault("avisos", []).append(f"Sobol' {m}: {av}")
        if tr is not None:
            for m, res in out["sobol"]["metrics"].items():
                if m in tr["sur"].rejected:
                    res.update(status="nao_avaliado", indices=[],
                               reason=f"sem substituto aceite ({tr['sur'].rejected[m]}); Sobol' não avaliado")
    if spec.morris is not None:
        mo = spec.morris
        out["morris"] = gsa.morris(spec.inputs, _batch_eval(gsa_model, {}), mo.get("metrics") or spec.metrics,
                                   r=int(mo.get("r", 10)), levels=int(mo.get("levels", 4)),
                                   seed=int(mo.get("seed", spec.seed + 2)))
        P.register_seed("uq.morris.seed", out["morris"]["seed"])
        if tr is not None:
            for m, res in out["morris"]["metrics"].items():
                if m in tr["sur"].rejected:
                    res.update(status="nao_avaliado", effects=[],
                               reason=f"sem substituto aceite ({tr['sur'].rejected[m]})")
    if nominal_matrix is not None:
        from acdt.core.verification import attach_probabilistic

        out["verification_matrix"] = attach_probabilistic(nominal_matrix, env["requirements"])
    if outdir is not None:
        write(out, outdir, plots=plots)
    return out


# ------------------------------------------------------------------------------------------------ escrita
def _g(x: Any, fmt: str = ".4g") -> str:
    if x is None:
        return "—"
    if isinstance(x, list):
        return "[" + ", ".join(_g(v, fmt) for v in x) + "]"
    if isinstance(x, float):
        return format(x, fmt)
    return str(x)


def to_markdown(r: Mapping[str, Any]) -> str:
    s = r["settings"]
    L = ["# Incerteza e sensibilidade", "",
         f"Formato `{r['schema']}`. Modelo: {r['model'].get('text', '')}", "",
         f"Propagação **{s['method'].upper()}**, N = {s['n']}, semente {s['seed']}; IC {int(100 * s['confidence'])} %; "
         f"probabilidade-alvo {s['target_probability']:g}"
         + (f" ({s['target_source']})" if s.get("target_source") else " (PRESSUPOSTO)") + ".", ""]
    if r.get("pressupostos"):
        L += ["## Pressupostos", ""] + [f"* {p}" for p in r["pressupostos"]] + [""]
    L += ["## Entradas incertas", "", "| Caminho | Distribuição | Nominal | Origem |", "|---|---|---|---|"]
    for i in r["inputs"]:
        L.append(f"| `{i['path']}` | {i['describe']} | {_g(i['nominal'])} | {i['source'][:150]} |")
    if r.get("excluded_inputs"):
        L += ["", "Não propagadas:", ""] + [f"* `{x.get('path') or x.get('name')}`: {x.get('reason')}"
                                           for x in r["excluded_inputs"]]
    if s.get("correlations"):
        L += ["", f"Correlações de postos (Iman & Conover 1982): {s['correlations']['source']}"]
    if r.get("epistemic_points"):
        L += ["", f"Intervalos (sem distribuição): ciclo exterior em {len(r['epistemic_points'])} extremos; "
                  "estatísticas em [mín, máx]."]
    if r.get("surrogate"):
        sg = r["surrogate"]
        L += ["", f"## Substituto (superfície de resposta quadrática; {sg['n_train']} corridas do modelo verdadeiro, "
                  f"{sg['n_train_failed']} falhadas; aceite se Q² ≥ {sg['q2_min']:g})", "",
              "| Saída | Termos | Q² (PRESS) | R² | RMSE LOO |", "|---|---|---|---|---|"]
        L += [f"| {m} | {a['n_terms']} | {a['Q2']:.4f} | {a['R2']:.4f} | {a['rmse_loo']:.4g} |"
              for m, a in sg["accepted"].items()]
        L += [f"| {m} | rejeitado | {why} |  |  |" for m, why in sg["rejected"].items()]
        L += ["", f"Fração das amostras de propagação fora da caixa de treino (em pelo menos uma entrada): "
                  f"{100 * sg['fracao_extrapolada']:.1f} %. " + sg["nota"] + "."]
        per = sg.get("extrapolacao_por_entrada") or {}
        if per:
            L += ["", "| Entrada | Caixa de treino | Fora (fração) | Excursão máx. (× largura da caixa) |",
                  "|---|---|---|---|"]
            L += [f"| `{nm}` | [{_g(e['lo'])}, {_g(e['hi'])}] | {100 * e['fracao']:.1f} % | "
                  f"{_g(e['excursao_max'], '.3f')} |" for nm, e in per.items()]
            L += ["", "Fora da caixa = extrapolação do polinómio; caudas ilimitadas (normal/lognormal) e o LHS de "
                      "treino (N_treino pontos) deixam sempre uma fração ≈ 2/(N_treino+1) por entrada limitada."]
    pr = r["propagation"]
    nf = sum(int(x["n_failed"]) for x in pr["runs"])
    L += ["", "## Resultados (percentis)", "",
          f"Avaliações falhadas: {nf} (contam como não-passa nos requisitos; nunca como zero).", "",
          "| Saída | Nominal | Média | σ | P5 | P50 | P95 | IC P95 | SE/média | Convergiu | Fonte |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    nom = (r.get("nominal") or {}).get("metrics") or {}
    for m, sm in pr["summaries"].items():
        if sm.get("status") != "ok":
            L.append(f"| {m} | {_g(nom.get(m))} | {sm.get('status')} |  |  |  |  |  |  |  | {sm.get('fonte', '')} |")
            continue
        L.append(f"| {m} | {_g(nom.get(m))} | {_g(sm['mean'])} | {_g(sm['std'], '.3g')} | {_g(sm.get('p5'))} | "
                 f"{_g(sm.get('p50'))} | {_g(sm.get('p95'))} | {_g(sm.get('p95_ic'))} | "
                 f"{_g(sm.get('se_rel'), '.2g')} | {'sim' if sm.get('converged') else 'não'} | "
                 f"{sm.get('fonte', 'modelo')} |")
    L += ["", "## Requisitos: probabilidade de cumprir", "",
          "O estado determinístico (corrida nominal) não muda; a coluna «estado prob.» é nova: **prob_passa** "
          "(limite inferior de Wilson ≥ alvo), **prob_no_limite** (P(passa) abaixo do alvo, mas P(passa ∪ no_limite) ≥ "
          "alvo: cumpre só dentro da tolerância declarada), **prob_falha** (limite superior < alvo e não "
          "prob_no_limite), **inconclusivo** (mais "
          "amostras), **nao_avaliado**, **desconhecido**. Amostras sem veredicto contam como não-passa.", "",
          "| Requisito | Estado nominal | P(passa) | IC | P(no_limite) | P(falha) | Estado prob. | Fonte |",
          "|---|---|---|---|---|---|---|---|"]
    nreq = (r.get("nominal") or {}).get("requirements") or {}
    for rid, q in pr["requirements"].items():
        L.append(f"| {rid} | {(nreq.get(rid) or {}).get('status', '—')} | {_g(q.get('p_passa'), '.3f')} | "
                 f"{_g(q.get('p_passa_ic'), '.3f')} | {_g(q.get('p_no_limite'), '.3f')} | "
                 f"{_g(q.get('p_falha'), '.3f')} | {q['estado_probabilistico']} | {q.get('fonte', 'modelo')} |")
    if r.get("sobol"):
        so = r["sobol"]
        L += ["", f"## Sobol' ({so['method']}; N = {so['n']}, {so['n_evaluations']} avaliações, "
                  f"{so['n_failed']} falhadas)", ""]
        for m, res in so["metrics"].items():
            if res.get("status") != "ok":
                L += [f"* {m}: {res.get('status')} — {res.get('reason')}"]
                continue
            L += [f"### {m}", "", f"ΣS1 = {res['sum_S1']:.3f}"
                  + (f" (IC {_g(res.get('sum_S1_ic'), '.3f')})" if res.get("sum_S1_ic") else "")
                  + ("" if res.get("consistente", True) else " — **inconsistente** (ver avisos)"), "",
                  "| Entrada | S1 | IC S1 | ST | IC ST |", "|---|---|---|---|---|"]
            L += [f"| `{x['variable']}` | {x['S1']:.3f} | {_g(x.get('S1_ic'), '.3f')} | {x['ST']:.3f} | "
                  f"{_g(x.get('ST_ic'), '.3f')} |" for x in res["indices"]]
            L += [f"* aviso: {a}" for a in res.get("avisos") or []]
            L.append("")
    if r.get("morris"):
        mo = r["morris"]
        L += ["", f"## Morris (r = {mo['r']}, p = {mo['levels']}, {mo['n_evaluations']} avaliações)", "",
              mo["nota"], ""]
        for m, res in mo["metrics"].items():
            L += [f"### {m}", "", "| Entrada | μ* | μ*/máx | μ | σ |", "|---|---|---|---|---|"]
            L += [f"| `{x['variable']}` | {_g(x['mu_star'])} | {_g(x['mu_star_norm'], '.3f')} | {_g(x['mu'])} | "
                  f"{_g(x['sigma'])} |" for x in res["effects"]]
            L.append("")
    if r.get("avisos"):
        L += ["## Avisos", ""] + [f"* {a}" for a in r["avisos"]]
    L += ["", "## Referências", ""] + [f"* {x}" for x in r["references"]]
    if r.get("sobol"):
        L.append(f"* {r['sobol']['reference']}")
    if r.get("morris"):
        L.append(f"* {r['morris']['reference']}")
    return "\n".join(L) + "\n"


def _plots(r: Mapping[str, Any], d: Path) -> list[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    files = []
    so = r.get("sobol") or {}
    for m, res in (so.get("metrics") or {}).items():
        if res.get("status") != "ok":
            continue
        idx = res["indices"][:10][::-1]
        fig, ax = plt.subplots(figsize=(7, 0.45 * len(idx) + 1.5))
        y = np.arange(len(idx))
        ax.barh(y + 0.2, [x["ST"] for x in idx], 0.4, label="ST")
        ax.barh(y - 0.2, [x["S1"] for x in idx], 0.4, label="S1")
        ax.set_yticks(y, [x["variable"].split(".")[-1] for x in idx])
        ax.set_xlabel("índice de Sobol'")
        ax.set_title(f"Sobol' — {m}")
        ax.legend()
        fig.tight_layout()
        fn = d / f"uq_sobol_{''.join(c if c.isalnum() else '_' for c in m)}.png"
        fig.savefig(fn, dpi=110)
        plt.close(fig)
        files.append(fn.name)
    runs = r["propagation"]["runs"]
    if len(runs) == 1:
        for m, sm in list(r["propagation"]["summaries"].items())[:12]:
            if sm.get("status") != "ok":
                continue
            vals = [s["metrics"][m] for s in runs[0]["samples"] if s["ok"] and m in s["metrics"]]
            fig, ax = plt.subplots(figsize=(6, 3.5))
            ax.hist(vals, bins=max(5, int(math.sqrt(len(vals)))))
            for k in ("p5", "p50", "p95"):
                if k in sm:
                    ax.axvline(sm[k], ls="--", color="k", lw=0.8)
            ax.set_title(f"{m}: P5/P50/P95")
            fig.tight_layout()
            fn = d / f"uq_hist_{''.join(c if c.isalnum() else '_' for c in m)}.png"
            fig.savefig(fn, dpi=100)
            plt.close(fig)
            files.append(fn.name)
    return files


def write(r: dict[str, Any], outdir: str | Path, plots: bool = True) -> list[Path]:
    d = Path(outdir)
    d.mkdir(parents=True, exist_ok=True)
    if plots:
        r["plots"] = _plots(r, d)
    js, md = d / UQ_FILES[0], d / UQ_FILES[1]
    js.write_text(json.dumps(r, indent=1, ensure_ascii=False, default=_json_default), encoding="utf-8")
    md.write_text(to_markdown(r), encoding="utf-8")
    out = [js, md]
    vm = r.get("verification_matrix")
    if vm is not None:
        from acdt.core.verification import write_matrix

        out += write_matrix(vm, d)
    return out


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return str(o)
