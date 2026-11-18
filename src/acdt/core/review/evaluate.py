# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Avaliação automática dos critérios de revisão e veredito.

Estados de um critério: ``cumpre``, ``nao_cumpre``, ``insuficiente`` (faltam dados para decidir — nunca conta
como cumpre), ``revisao_humana`` (fora dos registos do acdt) e ``dispensado`` (adaptação declarada com
justificação, NPR 7123.1D G.1.2).

Veredito, só sobre os critérios automáticos não dispensados:

* ``nao_pronto`` — algum critério ``nao_cumpre`` (uma falha conhecida decide, mesmo com dados em falta);
* ``insuficiente`` — nenhum ``nao_cumpre`` mas algum ``insuficiente`` (ou nenhum critério automático);
* ``pronto`` — todos ``cumpre``. Os critérios de revisão humana ficam sempre listados como pendentes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .bundle import Bundle
from .criteria import Criterion
from .profile import NON_PRIMARY, ReviewProfile

LEVEL_ORDER = ("L0", "L1", "L2", "L3")
UNEVALUATED = ("nao_avaliado", "desconhecido")


@dataclass
class Ctx:
    bundle: Bundle
    profile: ReviewProfile
    gate: str
    waivers: dict[str, str] = field(default_factory=dict)   # id do requisito → justificação
    trace: list[dict[str, Any]] = field(default_factory=list)  # linhas de rastreabilidade (preenchidas antes)

    # ------------------------------------------------------------------ verificação
    @property
    def verification(self) -> Mapping[str, Any] | None:
        if self.bundle.matrix is not None:
            return self.bundle.matrix
        v = self.bundle.design.get("verification")
        return v if isinstance(v, Mapping) else None

    @property
    def rows(self) -> list[Mapping[str, Any]] | None:
        v = self.verification
        return None if v is None else list(v.get("rows") or [])

    @property
    def coverage(self) -> Mapping[str, Any]:
        v = self.verification or {}
        return v.get("coverage") or {}


Result = tuple[str, str, list[str]]  # (estado, detalhe, evidência)


def _ev_matrix(c: Ctx) -> list[str]:
    b = c.bundle
    return [b.rel(b.matrix_path)] if b.matrix_path else [b.rel(b.design_path) + "#verification"]


def _list(xs: Sequence[str], n: int = 8) -> str:
    xs = list(xs)
    return ", ".join(xs[:n]) + (f" … (+{len(xs) - n})" if len(xs) > n else "")


# ---------------------------------------------------------------------------------------------- avaliadores
def chk_requisitos_definidos(c: Ctx, cr: Criterion) -> Result:
    rows = c.rows
    if rows is None:
        return "insuficiente", "sem matriz de verificação (acdt verify / acdt size)", []
    if not rows:
        return "nao_cumpre", "a matriz de verificação não tem requisitos", _ev_matrix(c)
    return "cumpre", f"{len(rows)} requisitos rastreáveis", _ev_matrix(c)


def chk_metodo_por_requisito(c: Ctx, cr: Criterion) -> Result:
    from acdt.core.verification import METHODS
    rows = c.rows
    if rows is None:
        return "insuficiente", "sem matriz de verificação", []
    if not rows:
        return "insuficiente", "sem requisitos", _ev_matrix(c)
    bad = [str(r.get("id")) for r in rows if r.get("method") not in METHODS]
    if bad:
        return "nao_cumpre", f"sem método de verificação: {_list(bad)}", _ev_matrix(c)
    return "cumpre", f"método declarado nos {len(rows)} requisitos", _ev_matrix(c)


def chk_avaliador_por_requisito(c: Ctx, cr: Criterion) -> Result:
    rows = c.rows
    if rows is None:
        return "insuficiente", "sem matriz de verificação", []
    if not rows:
        return "insuficiente", "sem requisitos", _ev_matrix(c)
    bad = sorted({str(r.get("id")) for r in rows if not r.get("evaluator")
                  or "não registado" in str(r.get("message") or "")}
                 | set(map(str, c.coverage.get("requisitos_sem_avaliador") or [])))
    if bad:
        return "nao_cumpre", f"{len(bad)} requisito(s) sem avaliador: {_list(bad)}", _ev_matrix(c)
    return "cumpre", f"avaliador declarado nos {len(rows)} requisitos", _ev_matrix(c)


def chk_arvore_requisitos(c: Ctx, cr: Criterion) -> Result:
    m = c.bundle.matrix
    if m is None:
        return ("insuficiente", "sem verification_matrix.json ao lado do design.json (a árvore e as fontes só lá "
                "estão)", [])
    issues = list(m.get("tree_issues") or [])
    nosrc = [str(r.get("id")) for r in m.get("rows") or [] if not r.get("source")]
    if issues or nosrc:
        d = []
        if issues:
            d.append(f"{len(issues)} problema(s) na árvore: {_list(issues, 3)}")
        if nosrc:
            d.append(f"sem fonte: {_list(nosrc)}")
        return "nao_cumpre", "; ".join(d), _ev_matrix(c)
    return "cumpre", f"árvore sem problemas; {len(m.get('rows') or [])} requisitos com fonte", _ev_matrix(c)


def _quantities_named(c: Ctx, names: Sequence[str]) -> list[tuple[str, Mapping[str, Any]]]:
    out = []
    for disc, lv in sorted((c.bundle.design.get("results") or {}).items()):
        for lvl, blk in sorted(lv.items()):
            for k, q in sorted((blk.get("quantities") or {}).items()):
                if any(k == n or k.endswith("." + n) for n in names):
                    out.append((f"results.{disc}.{lvl}.{k}", q))
    return out


def chk_conceito_viavel(c: Ctx, cr: Criterion) -> Result:
    qs = _quantities_named(c, c.profile.feasibility)
    ev = [c.bundle.rel(c.bundle.design_path) + "#" + p for p, _ in qs]
    if not qs:
        return "insuficiente", f"sem grandeza de viabilidade ({', '.join(c.profile.feasibility)}) no estado de projeto", []
    vals = [q.get("value") for _, q in qs]
    if any(v is False for v in vals):
        return "nao_cumpre", "dimensionamento inviável: " + _list([p for p, q in qs if q.get("value") is False]), ev
    if all(v is True for v in vals):
        return "cumpre", "dimensionamento viável", ev
    return "insuficiente", "viabilidade desconhecida (valor não booleano ou nulo)", ev


def chk_requisitos_cumpridos(c: Ctx, cr: Criterion) -> Result:
    rows = c.rows
    if rows is None:
        return "insuficiente", "sem matriz de verificação", []
    if not rows:
        return "insuficiente", "sem requisitos", _ev_matrix(c)
    fail = [str(r["id"]) for r in rows if r.get("status") == "falha" and str(r["id"]) not in c.waivers]
    waived = [str(r["id"]) for r in rows if r.get("status") == "falha" and str(r["id"]) in c.waivers]
    unev = [str(r["id"]) for r in rows if r.get("status") in UNEVALUATED]
    extra = f"; com dispensa: {_list(waived)}" if waived else ""
    if fail:
        return "nao_cumpre", f"{len(fail)} requisito(s) em falha: {_list(fail)}{extra}", _ev_matrix(c)
    if unev:
        return ("insuficiente", f"{len(unev)} requisito(s) não avaliados/desconhecidos (≠ passa): {_list(unev)}"
                + extra, _ev_matrix(c))
    return "cumpre", f"{len(rows)} requisitos cumpridos (passa ou no_limite){extra}", _ev_matrix(c)


def _uq_requirements(c: Ctx) -> dict[str, list[tuple[str, Mapping[str, Any]]]]:
    out: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for r in c.bundle.uq:
        for rid, p in sorted(((r.data.get("propagation") or {}).get("requirements") or {}).items()):
            out.setdefault(str(rid), []).append((c.bundle.rel(r.path), p))
    return out


def chk_incerteza_requisitos(c: Ctx, cr: Criterion) -> Result:
    if not c.bundle.uq:
        return "insuficiente", "sem estudo de incerteza (acdt uq / acdt.uq/1)", []
    ureq = _uq_requirements(c)
    ev = [c.bundle.rel(r.path) for r in c.bundle.uq]
    if not ureq:
        return "insuficiente", "o estudo de incerteza não avalia requisitos (P(passa))", ev
    st = {rid: [str(p.get("estado_probabilistico")) for _, p in lst] for rid, lst in ureq.items()}
    fail = sorted(rid for rid, s in st.items() if "prob_falha" in s)
    inc = sorted(rid for rid, s in st.items() if set(s) - {"prob_passa", "prob_no_limite", "prob_falha"})
    numeric = [str(r["id"]) for r in c.rows or [] if r.get("comparison") in ("min", "max", "target")]
    uncovered = sorted(set(numeric) - set(ureq))
    if fail:
        return "nao_cumpre", f"P(passa) abaixo do alvo declarado no estudo: {_list(fail)}", ev
    if inc:
        return "insuficiente", f"estado probabilístico inconclusivo/não avaliado: {_list(inc)}", ev
    if uncovered:
        return ("insuficiente", f"{len(uncovered)} requisito(s) numérico(s) da matriz sem avaliação probabilística: "
                f"{_list(uncovered)}", ev)
    nl = sorted(rid for rid, s in st.items() if "prob_no_limite" in s)
    return "cumpre", (f"{len(ureq)} requisito(s) com P(passa) ≥ alvo" if not nl else
                      f"{len(ureq) - len(nl)} com P(passa) ≥ alvo; no limite: {_list(nl)}"), ev


def chk_margens(c: Ctx, cr: Criterion) -> Result:
    rows = c.rows
    if rows is None:
        return "insuficiente", "sem matriz de verificação", []
    num = [r for r in rows if r.get("status") in ("passa", "no_limite", "falha") and r.get("margin") is not None]
    if not num:
        return "insuficiente", "nenhum requisito numérico avaliado com margem", _ev_matrix(c)
    nl = [str(r["id"]) for r in num if r.get("status") == "no_limite"]
    ev = _ev_matrix(c)
    det = [f"{len(num)} requisitos com margem avaliada"]
    if cr.params.get("require_uq") and c.bundle.uq:
        ev += [c.bundle.rel(r.path) for r in c.bundle.uq]
        nl += sorted(rid for rid, lst in _uq_requirements(c).items()
                     if any(p.get("estado_probabilistico") == "prob_no_limite" for _, p in lst))
    if nl:
        return "nao_cumpre", f"margem dentro da tolerância (no_limite): {_list(sorted(set(nl)))}", ev
    if cr.params.get("require_uq") and not c.bundle.uq:
        return "insuficiente", "; ".join(det + ["sem estudo de incerteza das margens (acdt uq)"]), ev
    return "cumpre", "; ".join(det), ev


def discipline_levels(c: Ctx) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for disc, lv in (c.bundle.design.get("results") or {}).items():
        lv_ok = [lvl for lvl, blk in lv.items()
                 if any(q.get("value") is not None for q in (blk.get("quantities") or {}).values())]
        out[str(disc)] = sorted(lv_ok, key=LEVEL_ORDER.index)
    return out


def primary_disciplines(c: Ctx) -> list[str]:
    if c.profile.primary_disciplines:
        return list(c.profile.primary_disciplines)
    return sorted(d for d in (c.bundle.design.get("results") or {}) if d not in NON_PRIMARY)


def chk_fidelidade_disciplinas(c: Ctx, cr: Criterion) -> Result:
    need = c.profile.required_level.get(c.gate, "L0")
    have = discipline_levels(c)
    prim = primary_disciplines(c)
    if not prim:
        return "insuficiente", "sem disciplinas registadas no estado de projeto", []
    missing = [d for d in prim if not have.get(d)]
    below = [f"{d} ({have[d][-1]})" for d in prim if have.get(d) and
             LEVEL_ORDER.index(have[d][-1]) < LEVEL_ORDER.index(need)]
    ev = [c.bundle.rel(c.bundle.design_path) + "#results"]
    det = f"nível exigido {need} (PRESSUPOSTO do acdt); primárias: {', '.join(prim)}"
    if below:
        return "nao_cumpre", f"{det}; abaixo do nível: {_list(below)}" + (
            f"; sem resultados: {_list(missing)}" if missing else ""), ev
    if missing:
        return "insuficiente", f"{det}; sem resultados: {_list(missing)}", ev
    return "cumpre", det, ev


def chk_vv_modelos(c: Ctx, cr: Criterion) -> Result:
    if not c.bundle.vv:
        return "insuficiente", "sem relatório de V&V (acdt vv / acdt.vv/1)", []
    tot = {"passa": 0, "falha": 0, "nao_avaliado": 0, "desconhecido": 0}
    fail: list[str] = []
    unev: list[str] = []
    for r in c.bundle.vv:
        for case in r.data.get("cases") or []:
            s = str(case.get("status"))
            tot[s] = tot.get(s, 0) + 1
            if s == "falha":
                fail.append(str(case.get("id")))
            elif s in UNEVALUATED:
                unev.append(str(case.get("id")))
    ev = [c.bundle.rel(r.path) for r in c.bundle.vv]
    cnt = ", ".join(f"{k} {v}" for k, v in tot.items())
    if fail:
        return "nao_cumpre", f"casos de V&V em falha: {_list(fail)} ({cnt})", ev
    if unev:
        return "insuficiente", f"casos de V&V por avaliar: {_list(unev)} ({cnt})", ev
    if not tot["passa"]:
        return "insuficiente", "relatório de V&V sem casos", ev
    return "cumpre", cnt, ev


def chk_estudos_compromisso(c: Ctx, cr: Criterion) -> Result:
    if not c.bundle.mdo:
        return "insuficiente", "sem estudo MDO/compromisso (acdt mdo / acdt.mdo/1)", []
    ev = [c.bundle.rel(r.path) for r in c.bundle.mdo]
    ok = [r for r in c.bundle.mdo if r.data.get("chosen") is not None and (r.data.get("n_feasible") or 0) > 0]
    if ok:
        return "cumpre", f"{len(ok)} estudo(s) com projeto viável escolhido", ev
    return "nao_cumpre", "nenhum estudo MDO com projeto viável escolhido", ev


def chk_ensaios_calibracao(c: Ctx, cr: Criterion) -> Result:
    if not c.bundle.calib:
        return "insuficiente", "sem calibração contra ensaio (acdt calib / acdt.calib/1)", []
    ev = [c.bundle.rel(r.path) for r in c.bundle.calib]
    real = [r for r in c.bundle.calib if not r.data.get("synthetic")]
    if not real:
        return "insuficiente", "só há calibrações com dados SINTÉTICOS (não são evidência de ensaio)", ev
    ok = [r for r in real if r.data.get("decision") in ("aplicar", "parcial")]
    if ok:
        return "cumpre", f"{len(ok)} calibração(ões) contra ensaio com decisão aplicar/parcial", ev
    return "nao_cumpre", "as calibrações contra ensaio real ficaram todas nao_aplicar", ev


def chk_linha_de_base(c: Ctx, cr: Criterion) -> Result:
    b = c.bundle
    ev = [b.rel(b.provenance_path)] if b.provenance_path else []
    bad = [t["path"] for t in c.trace if t["status"] in ("difere", "em_falta") and t["role"] != "estado de projeto"]
    if bad:
        return "nao_cumpre", f"evidência alterada ou em falta face ao SHA-256 registado: {_list(bad)}", ev
    if not b.provenance:
        return "insuficiente", "sem registo de proveniência (provenance.json) na pasta do projeto", ev
    git = (b.provenance.get("acdt") or {}).get("git") or {}
    if git.get("dirty"):
        return "nao_cumpre", (f"corrida com alterações por registar no git (commit {str(git.get('commit'))[:12]}, "
                              "dirty)"), ev
    if not git.get("commit"):
        return "insuficiente", "versão do código desconhecida (sem commit git no registo)", ev
    return "cumpre", f"evidência confere; código no commit {str(git.get('commit'))[:12]}", ev


def chk_cobertura_completa(c: Ctx, cr: Criterion) -> Result:
    st, det, ev = chk_avaliador_por_requisito(c, cr)
    if st != "cumpre":
        return st, det, ev
    unev = [str(r["id"]) for r in c.rows or [] if r.get("status") in UNEVALUATED]
    if unev:
        return "insuficiente", f"{len(unev)} requisito(s) com avaliador mas sem avaliação conclusiva: {_list(unev)}", ev
    return "cumpre", f"{len(c.rows or [])} requisitos com avaliador e avaliados", ev


CHECKS: dict[str, Callable[[Ctx, Criterion], Result]] = {
    "requisitos_definidos": chk_requisitos_definidos,
    "metodo_por_requisito": chk_metodo_por_requisito,
    "avaliador_por_requisito": chk_avaliador_por_requisito,
    "arvore_requisitos": chk_arvore_requisitos,
    "conceito_viavel": chk_conceito_viavel,
    "requisitos_cumpridos": chk_requisitos_cumpridos,
    "incerteza_requisitos": chk_incerteza_requisitos,
    "margens": chk_margens,
    "fidelidade_disciplinas": chk_fidelidade_disciplinas,
    "vv_modelos": chk_vv_modelos,
    "estudos_compromisso": chk_estudos_compromisso,
    "ensaios_calibracao": chk_ensaios_calibracao,
    "linha_de_base": chk_linha_de_base,
    "cobertura_completa": chk_cobertura_completa,
}


def evaluate_criteria(c: Ctx, criteria: Sequence[Criterion], tailoring: Mapping[str, str]) -> list[dict[str, Any]]:
    out = []
    for cr in criteria:
        row: dict[str, Any] = {"id": cr.id, "phase": cr.phase, "ref": cr.ref, "quote": cr.quote,
                               "automatico": cr.check is not None, "check": cr.check, "interpretacao": cr.interpretacao}
        if cr.id in tailoring:
            row.update(status="dispensado", detail=f"adaptação declarada: {tailoring[cr.id]}", evidence=[])
        elif cr.check is None:
            row.update(status="revisao_humana", detail="pendente do painel de revisão", evidence=[])
        else:
            st, det, ev = CHECKS[cr.check](c, cr)
            row.update(status=st, detail=det, evidence=ev)
        out.append(row)
    return out


def verdict(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    auto = [r for r in rows if r["automatico"] and r["status"] != "dispensado"]
    counts = {s: sum(1 for r in rows if r["status"] == s)
              for s in ("cumpre", "nao_cumpre", "insuficiente", "revisao_humana", "dispensado")}
    if any(r["status"] == "nao_cumpre" for r in auto):
        v = "nao_pronto"
        why = [r["id"] for r in auto if r["status"] == "nao_cumpre"]
    elif any(r["status"] == "insuficiente" for r in auto) or not auto:
        v = "insuficiente"
        why = [r["id"] for r in auto if r["status"] == "insuficiente"] or ["nenhum critério automático"]
    else:
        v, why = "pronto", []
    return {"status": v, "motivos": why, "counts": counts, "n_automaticos": len(auto),
            "ambito": "critérios automáticos declarados (os de revisão humana ficam pendentes e não entram)"}
