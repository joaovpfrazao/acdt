"""Biblioteca de V&V como produto (``acdt vv``; docs/VV.md): casos de referência publicados por disciplina.

Cada caso (:class:`Case`) tem o enunciado do problema, os valores de referência **publicados** com a citação
completa, a tolerância **declarada a priori** por grandeza e o avaliador do acdt que produz o valor comparado.
Tipos (Oberkampf & Roy, Verification and Validation in Scientific Computing, CUP 2010, Cap. 1–2):

* ``verificacao`` — o código contra uma solução exata/analítica ou uma norma que define a grandeza (resolve bem as
  equações?);
* ``validacao`` — o modelo contra dados físicos publicados (são as equações certas?).

Estados por grandeza e por caso: ``passa`` (|Δ| dentro da tolerância), ``falha``, ``nao_avaliado`` (ferramenta ou
dependência em falta, ou caso filtrado pelo custo — nunca conta como passa) e ``desconhecido`` (o avaliador correu e
não deu valor, ou levantou exceção). O caso passa só se todas as grandezas passarem.

O relatório (``acdt.vv/1``, JSON + Markdown) é versionado: versão do registo, impressão digital SHA-256 das
definições dos casos (ids, referências, tolerâncias) e o registo de proveniência ``acdt.provenance/1`` da corrida.
Os casos vivem em módulos registados (``acdt.core.vv_cases`` e ``acdt.domains.<d>.vv_cases``); um domínio novo
acrescenta os seus com :func:`register`.
"""
from __future__ import annotations

import importlib
import json
import math
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SCHEMA = "acdt.vv/1"
REGISTRY_VERSION = "2026.11.18"
STATUSES = ("passa", "falha", "nao_avaliado", "desconhecido")
KINDS = ("verificacao", "validacao")
COSTS = ("barato", "medio", "pesado")  # barato: < ~10 s, corre na CI; medio: pipeline/otimização; pesado: no PC
CASE_MODULES = ["acdt.core.vv_cases", "acdt.domains.aircraft.vv_cases"]
VV_FILES = ("vv_report.json", "vv_report.md")


class NotAssessed(Exception):
    """Levantada pelo avaliador quando falta uma ferramenta/dependência: o caso fica ``nao_avaliado``."""


@dataclass(frozen=True)
class Reference:
    """Um valor publicado. ``tol_abs``/``tol_rel``: tolerância declarada (passa se |Δ| ≤ tol_abs + tol_rel·|ref|).
    ``kind = "min"``/``"max"``: limite em vez de valor (passa se valor ≥/≤ ref − /+ tolerância)."""

    quantity: str
    value: float
    unit: str
    citation: str
    tol_abs: float = 0.0
    tol_rel: float = 0.0
    tol_source: str = ""
    kind: str = "valor"  # valor | min | max

    def allowed(self) -> float:
        return self.tol_abs + self.tol_rel * abs(self.value)

    def to_dict(self) -> dict[str, Any]:
        return {"quantity": self.quantity, "value": self.value, "unit": self.unit, "citation": self.citation,
                "tol_abs": self.tol_abs, "tol_rel": self.tol_rel, "tol_source": self.tol_source, "kind": self.kind}


Evaluator = Callable[[], Mapping[str, float | None]]


@dataclass(frozen=True)
class Case:
    id: str
    discipline: str
    title: str
    problem: str
    kind: str
    references: tuple[Reference, ...]
    evaluator: Evaluator
    evaluator_name: str
    cost: str = "barato"
    requires: tuple[str, ...] = ()  # executáveis externos (avl, xfoil) ou módulos Python (py:openmdao)
    notes: str = ""
    tests: tuple[str, ...] = ()  # testes pytest que já cobriam o caso (inventário)

    def definition(self) -> dict[str, Any]:
        return {"id": self.id, "discipline": self.discipline, "title": self.title, "problem": self.problem,
                "kind": self.kind, "cost": self.cost, "requires": list(self.requires),
                "evaluator": self.evaluator_name, "references": [r.to_dict() for r in self.references],
                "notes": self.notes, "tests": list(self.tests)}


_REGISTRY: dict[str, Case] = {}
_LOADED = False


def register(case: Case) -> Case:
    if case.kind not in KINDS:
        raise ValueError(f"{case.id}: tipo '{case.kind}' ∉ {KINDS}")
    if case.cost not in COSTS:
        raise ValueError(f"{case.id}: custo '{case.cost}' ∉ {COSTS}")
    if not case.references:
        raise ValueError(f"{case.id}: sem valores de referência")
    for r in case.references:
        if not r.citation.strip():
            raise ValueError(f"{case.id}/{r.quantity}: referência sem citação")
        if r.tol_abs < 0 or r.tol_rel < 0 or (r.tol_abs == 0 and r.tol_rel == 0 and r.kind == "valor"):
            raise ValueError(f"{case.id}/{r.quantity}: tolerância declarada em falta ou negativa")
    if case.id in _REGISTRY and _REGISTRY[case.id] is not case:
        raise ValueError(f"caso V&V repetido: {case.id}")
    _REGISTRY[case.id] = case
    return case


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    for m in CASE_MODULES:
        importlib.import_module(m)


def cases() -> list[Case]:
    _load()
    return list(_REGISTRY.values())


def registry_fingerprint(cs: Sequence[Case] | None = None) -> str:
    from acdt.core.provenance import canonical_hash

    return canonical_hash([c.definition() for c in sorted(cs if cs is not None else cases(), key=lambda c: c.id)])


def _missing(requires: Sequence[str]) -> list[str]:
    import importlib.util
    import shutil

    out = []
    for r in requires:
        if r.startswith("py:"):
            if importlib.util.find_spec(r[3:]) is None:
                out.append(r)
        elif shutil.which(r) is None:
            out.append(r)
    return out


def compare(ref: Reference, value: float | None) -> dict[str, Any]:
    d: dict[str, Any] = {**ref.to_dict(), "computed": value, "delta": None, "delta_rel": None,
                         "allowed": ref.allowed()}
    if value is None or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        d["status"] = "desconhecido"
        return d
    v = float(value)
    d["computed"] = v
    d["delta"] = v - ref.value
    d["delta_rel"] = (v - ref.value) / abs(ref.value) if ref.value != 0 else None
    if ref.kind == "min":
        ok = v >= ref.value - ref.allowed()
    elif ref.kind == "max":
        ok = v <= ref.value + ref.allowed()
    else:
        ok = abs(v - ref.value) <= ref.allowed()
    d["status"] = "passa" if ok else "falha"
    return d


def run_case(case: Case) -> dict[str, Any]:
    out: dict[str, Any] = {**case.definition(), "status": "nao_avaliado", "message": "", "seconds": 0.0,
                           "results": []}
    miss = _missing(case.requires)
    if miss:
        out["message"] = "em falta: " + ", ".join(miss)
        out["results"] = [{**r.to_dict(), "computed": None, "status": "nao_avaliado"} for r in case.references]
        return out
    t0 = time.perf_counter()
    try:
        vals = dict(case.evaluator())
    except NotAssessed as e:
        out["message"] = str(e)
        out["results"] = [{**r.to_dict(), "computed": None, "status": "nao_avaliado"} for r in case.references]
        out["seconds"] = time.perf_counter() - t0
        return out
    except Exception as e:  # noqa: BLE001 — erro do avaliador: desconhecido, nunca passa
        out["status"] = "desconhecido"
        out["message"] = f"{type(e).__name__}: {e}"
        out["traceback"] = traceback.format_exc(limit=6)
        out["results"] = [{**r.to_dict(), "computed": None, "status": "desconhecido"} for r in case.references]
        out["seconds"] = time.perf_counter() - t0
        return out
    out["seconds"] = time.perf_counter() - t0
    res = [compare(r, vals.get(r.quantity)) for r in case.references]
    out["results"] = res
    sts = {r["status"] for r in res}
    out["status"] = ("falha" if "falha" in sts else "desconhecido" if "desconhecido" in sts
                     else "nao_avaliado" if "nao_avaliado" in sts else "passa")
    return out


def select(ids: Sequence[str] | None = None, disciplines: Sequence[str] | None = None,
           max_cost: str = "barato") -> tuple[list[Case], list[Case]]:
    """(escolhidos, filtrados pelo custo). ``ids`` explícitos ignoram o filtro de custo."""
    allc = cases()
    if ids:
        unknown = [i for i in ids if i not in _REGISTRY]
        if unknown:
            raise KeyError("casos V&V desconhecidos: " + ", ".join(unknown))
        allc = [c for c in allc if c.id in ids]
        return allc, []
    if disciplines:
        allc = [c for c in allc if c.discipline in disciplines]
    lim = COSTS.index(max_cost) if max_cost in COSTS else len(COSTS) - 1
    keep = [c for c in allc if COSTS.index(c.cost) <= lim]
    return keep, [c for c in allc if COSTS.index(c.cost) > lim]


def run(ids: Sequence[str] | None = None, disciplines: Sequence[str] | None = None, max_cost: str = "barato",
        log: Callable[[str], None] | None = None) -> dict[str, Any]:
    from acdt.core import provenance as P

    chosen, skipped = select(ids, disciplines, max_cost)
    rows = []
    for c in chosen:
        r = run_case(c)
        rows.append(r)
        if log:
            log(f"  [{r['status']}] {c.id} ({r['seconds']:.1f} s) {r['message']}".rstrip())
    for c in skipped:
        rows.append({**c.definition(), "status": "nao_avaliado", "seconds": 0.0,
                     "message": f"custo '{c.cost}' acima do pedido ('{max_cost}'); corra com --cost {c.cost}",
                     "results": [{**x.to_dict(), "computed": None, "status": "nao_avaliado"}
                                 for x in c.references]})
    rows.sort(key=lambda r: (r["discipline"], r["id"]))
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    return {"schema": SCHEMA, "registry_version": REGISTRY_VERSION,
            "registry_fingerprint": registry_fingerprint(), "max_cost": max_cost,
            "filters": {"ids": list(ids or []), "disciplines": list(disciplines or [])},
            "counts": counts, "cases": rows, "provenance": P.collect(entry_point="acdt vv"),
            "nota": "nao_avaliado ≠ passa; desconhecido = o avaliador correu sem valor (ou com erro)"}


def _fmt(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.6g}"
    return str(x)


def _fmt_q(r: Mapping[str, Any]) -> str:
    u = "" if r.get("unit") in (None, "", "—") else f" {r['unit']}"
    allowed = float(r["tol_abs"]) + float(r["tol_rel"]) * abs(float(r["value"]))
    kind = r.get("kind", "valor")
    if kind == "min":
        ref = f"≥ {_fmt(float(r['value']) - allowed)}"
    elif kind == "max":
        ref = f"≤ {_fmt(float(r['value']) + allowed)}"
    else:
        ref = f"{_fmt(r['value'])} ± {_fmt(allowed)}"
    return f"{r['quantity']}: {_fmt(r.get('computed'))} / {ref}{u}"


def to_markdown(rep: Mapping[str, Any]) -> str:
    pv = rep.get("provenance") or {}
    git = ((pv.get("acdt") or {}).get("git") or {})
    L = ["# Relatório de V&V", "",
         f"Formato `{rep['schema']}`; registo de casos versão **{rep['registry_version']}** (impressão digital "
         f"`{rep['registry_fingerprint'][:16]}`); custo máximo pedido: `{rep['max_cost']}`; commit "
         f"`{str(git.get('commit') or '—')[:12]}`" + (" (árvore suja)" if git.get("dirty") else "") + ".", "",
         "Estados: **passa**, **falha**, **nao_avaliado** (ferramenta/dependência em falta ou custo filtrado — nunca "
         "conta como passa), **desconhecido** (o avaliador correu sem valor ou com erro).", "",
         "| Estado | N.º |", "|---|---|"]
    L += [f"| {s} | {rep['counts'][s]} |" for s in STATUSES]
    L += ["", "| Caso | Disciplina | Tipo | Custo | Estado | Grandezas (calculado / referência ± tolerância) | Nota |",
          "|---|---|---|---|---|---|---|"]
    for c in rep["cases"]:
        q = "; ".join(_fmt_q(r) for r in c["results"])
        L.append(f"| {c['id']} | {c['discipline']} | {c['kind']} | {c['cost']} | {c['status']} | {q} | "
                 f"{str(c.get('message') or '').replace('|', '/')[:120]} |")
    L += ["", "## Casos", ""]
    for c in rep["cases"]:
        L += [f"### {c['id']} — {c['title']}", "", c["problem"], "",
              f"Avaliador: `{c['evaluator']}`. Estado: **{c['status']}**."
              + (f" Testes que já o cobriam: {', '.join(c['tests'])}." if c.get("tests") else ""), ""]
        refs = sorted({r["citation"] for r in c["results"]})
        L += [f"* Referência: {x}" for x in refs]
        tols = sorted({r["tol_source"] for r in c["results"] if r.get("tol_source")})
        L += [f"* Tolerância: {x}" for x in tols]
        if c.get("notes"):
            L.append(f"* Nota: {c['notes']}")
        L.append("")
    return "\n".join(L) + "\n"


def write(rep: dict[str, Any], outdir: str | Path) -> list[Path]:
    d = Path(outdir)
    d.mkdir(parents=True, exist_ok=True)
    js, md = d / VV_FILES[0], d / VV_FILES[1]
    js.write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    md.write_text(to_markdown(rep), encoding="utf-8")
    return [js, md]


@dataclass
class _Builder:
    """Açúcar para os módulos de casos: ``case(...)(fn)`` regista ``fn`` como avaliador."""

    discipline: str
    defaults: dict[str, Any] = field(default_factory=dict)

    def __call__(self, id: str, title: str, problem: str, kind: str, references: Sequence[Reference], *,
                 cost: str = "barato", requires: Sequence[str] = (), notes: str = "",
                 tests: Sequence[str] = ()) -> Callable[[Evaluator], Evaluator]:
        def deco(fn: Evaluator) -> Evaluator:
            register(Case(id=id, discipline=self.discipline, title=title, problem=problem, kind=kind,
                          references=tuple(references), evaluator=fn,
                          evaluator_name=f"{fn.__module__}.{getattr(fn, '__qualname__', repr(fn))}",
                          cost=cost, requires=tuple(requires), notes=notes, tests=tuple(tests)))
            return fn
        return deco


def builder(discipline: str) -> _Builder:
    return _Builder(discipline)
