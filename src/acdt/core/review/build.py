# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Relatório de revisão de projeto (``acdt.review/1``): estrutura em dados, independente do formato de saída."""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from acdt.core.provenance import sha256_file

from .bundle import Bundle, ReviewInputError, recorded_hashes
from .criteria import DEFAULT_REQUIRED_LEVEL, GATES, STANDARD, criteria_for, gate_key
from .figures import histogram_plan, pareto_plan
from .evaluate import (LEVEL_ORDER, UNEVALUATED, Ctx, discipline_levels, evaluate_criteria, primary_disciplines,
                       verdict)
from .profile import apply_overrides, profile_for

SCHEMA = "acdt.review/1"
_NIVEL_ORDEM = ("SRR", "PDR", "CDR", "MDR", "TRR", "PRR")
_PRESSUPOSTO_NIVEL = ("nível exigido por revisão = PRESSUPOSTO do acdt ("
                      + ", ".join(f"{g} {DEFAULT_REQUIRED_LEVEL[g]}" for g in _NIVEL_ORDEM)
                      + "); a NPR 7123.1D não define níveis de fidelidade")
_PRESS = re.compile(r"PRESSUPOSTO", re.IGNORECASE)
_OUTVAL = re.compile(r"fora da gama de validade", re.IGNORECASE)
PARETO_MAX_ROWS = 20


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


# -------------------------------------------------------------------------------------------- substituições
def load_overrides(path: str | Path | None) -> dict[str, Any]:
    """Ficheiro de critérios (YAML/JSON): ``waivers``, ``tailoring``, ``required_level``,
    ``primary_disciplines``, ``headline``, ``feasibility``. Dispensas e adaptações exigem justificação."""
    if path is None:
        return {}
    import yaml

    p = Path(path)
    if not p.is_file():
        raise ReviewInputError(f"{p}: ficheiro de critérios não existe")
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(d, dict):
        raise ReviewInputError(f"{p}: o ficheiro de critérios tem de ser um mapa")
    known = {"waivers", "tailoring", "required_level", "primary_disciplines", "headline", "feasibility"}
    extra = set(d) - known
    if extra:
        raise ReviewInputError(f"{p}: campos desconhecidos {sorted(extra)} (aceites: {sorted(known)})")
    return d


def _justified(items: Any, key: str, what: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for it in items or []:
        if not isinstance(it, Mapping) or not it.get(key) or not str(it.get("justificacao") or "").strip():
            raise ReviewInputError(f"{what}: cada entrada precisa de '{key}' e de 'justificacao' não vazia ({it!r})")
        out[str(it[key])] = str(it["justificacao"]).strip()
    return out


# ------------------------------------------------------------------------------------------ rastreabilidade
def traceability(b: Bundle) -> list[dict[str, Any]]:
    rec = recorded_hashes(b)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(p: Path, role: str) -> None:
        key = str(p.resolve())
        if key in seen:
            return
        seen.add(key)
        cur = sha256_file(p) if p.is_file() else None
        r = rec.get(key)
        st = ("em_falta" if cur is None else "sem_registo" if r is None else "confere" if r == cur else "difere")
        rows.append({"role": role, "path": b.rel(p), "sha256": cur, "sha256_registado": r, "status": st})

    add(b.design_path, "estado de projeto")
    if b.matrix_path:
        add(b.matrix_path, "matriz de verificação")
    if b.provenance_path:
        add(b.provenance_path, "proveniência")
    for lv in (b.design.get("results") or {}).values():
        for blk in lv.values():
            if blk.get("evidence"):
                add(b.base / str(blk["evidence"]), "resultados (evidência dos blocos)")
    for kind, role in (("uq", "incerteza"), ("mdo", "MDO"), ("vv", "V&V"), ("calib", "calibração")):
        for r in getattr(b, kind):
            add(r.path, role)
            if kind == "calib":
                f = (r.data.get("data") or {}).get("file") or {}
                if f.get("path"):
                    q = Path(str(f["path"]))
                    add(q if q.is_absolute() else r.path.parent / q, "dados de ensaio")
    for f in b.figures:
        add(f, "figura")
    return rows


# ---------------------------------------------------------------------------------------------- secções
def _requirements(c: Ctx) -> dict[str, Any]:
    rows = c.rows
    if rows is None:
        return {"present": False, "counts": {}, "rows": []}
    from acdt.core.verification import STATUSES
    keep = ("id", "text", "source", "quantity", "comparison", "threshold", "display", "unit", "value", "margin",
            "status", "method", "fidelity_required", "fidelity_evaluated", "evaluator", "evidence", "message")
    out = []
    for r in rows:
        d = {k: r.get(k) for k in keep}
        d["dispensa"] = c.waivers.get(str(r.get("id")))
        out.append(d)
    counts = {s: sum(1 for r in rows if r.get("status") == s) for s in STATUSES}
    cov = dict(c.coverage)
    return {"present": True, "counts": counts, "fracao_avaliada": cov.get("fracao_avaliada"),
            "requisitos_sem_avaliador": list(cov.get("requisitos_sem_avaliador") or []),
            "avaliadores_sem_requisito": list(cov.get("avaliadores_sem_requisito") or []), "rows": out,
            "fonte": "verification_matrix.json" if c.bundle.matrix is not None else "design.json#verification"}


def _flat(db: Mapping[str, Any]) -> list[tuple[str, str, str, Mapping[str, Any], Mapping[str, Any]]]:
    out = []
    for disc, lv in sorted((db.get("results") or {}).items()):
        for lvl, blk in sorted(lv.items(), key=lambda kv: LEVEL_ORDER.index(kv[0]) if kv[0] in LEVEL_ORDER else 9):
            for k, q in sorted((blk.get("quantities") or {}).items()):
                out.append((str(disc), str(lvl), str(k), q, blk))
    return out


def _design_summary(c: Ctx) -> dict[str, Any]:
    db = c.bundle.design
    flat = _flat(db)
    head = []
    for name in c.profile.headline:
        hits = [t for t in flat if t[2] == name or t[2].endswith("." + name)]
        if not hits:
            head.append({"name": name, "value": None, "unit": None, "level": None, "discipline": None,
                         "path": None, "nota": "não registado no estado de projeto (desconhecido)"})
            continue
        disc, lvl, k, q, blk = max(hits, key=lambda t: (LEVEL_ORDER.index(t[1]) if t[1] in LEVEL_ORDER else -1,
                                                        t[2] == name))
        u = q.get("uncertainty") or {}
        head.append({"name": name, "value": q.get("value"), "unit": q.get("unit"), "level": lvl,
                     "discipline": disc, "path": f"results.{disc}.{lvl}.{k}", "method": blk.get("method"),
                     "p5": u.get("p5"), "p50": u.get("p50"), "p95": u.get("p95")})
    src = (db.get("definition") or {}).get("source") or {}
    reqs = []
    for key, r in sorted(((db.get("definition") or {}).get("requirements") or {}).items()):
        reqs.append({"key": key, "value": r.get("value"), "unit": r.get("unit"), "raw": r.get("raw"),
                     "raw_unit": r.get("raw_unit"), "source": r.get("source")})
    return {"name": db.get("name"), "domain": db.get("domain"), "schema": db.get("schema"),
            "revision": db.get("revision"), "updated_utc": db.get("updated_utc"), "input": src.get("path"),
            "input_sha256": src.get("sha256"), "headline": head, "definition_requirements": reqs}


def _fidelity(c: Ctx) -> dict[str, Any]:
    need = c.profile.required_level.get(c.gate, "L0")
    have = discipline_levels(c)
    prim = set(primary_disciplines(c))
    db = c.bundle.design
    rows = []
    for d in sorted(set(have) | prim):
        lv = have.get(d) or []
        top = lv[-1] if lv else None
        blk = ((db.get("results") or {}).get(d) or {}).get(top or "", {}) if top else {}
        qs = (blk.get("quantities") or {}).values() if blk else []
        n_nounit = sum(1 for q in qs if q.get("unit") is None and isinstance(q.get("value"), (int, float))
                       and not isinstance(q.get("value"), bool))
        if d not in prim:
            st = "—"
        elif not lv:
            st = "ausente"
        elif LEVEL_ORDER.index(top or "L0") < LEVEL_ORDER.index(need):
            st = "abaixo"
        else:
            st = "cumpre"
        rows.append({"discipline": d, "levels": lv, "max_level": top, "primary": d in prim,
                     "required": need if d in prim else None, "status": st, "method": blk.get("method") if blk else None,
                     "fidelity": (blk.get("fidelity") or "modelo") if blk else None, "n_sem_unidade": n_nounit})
    low = [r["discipline"] for r in rows if r["max_level"] in ("L0", "L1")]
    return {"required_level": need, "rows": rows, "ainda_L0_L1": low, "pressuposto": _PRESSUPOSTO_NIVEL}


def _uq(c: Ctx) -> dict[str, Any]:
    studies = []
    for r in c.bundle.uq:
        d = r.data
        prop = d.get("propagation") or {}
        metrics = []
        for m, s in sorted((prop.get("summaries") or {}).items()):
            metrics.append({"metric": m, "status": s.get("status"), "n": s.get("n"), "mean": s.get("mean"),
                            "p5": s.get("p5"), "p50": s.get("p50"), "p95": s.get("p95"),
                            "epistemico": bool(s.get("epistemico") or s.get("intervalo"))})
        reqs = []
        for rid, p in sorted((prop.get("requirements") or {}).items()):
            reqs.append({"id": rid, "p_passa": p.get("p_passa"), "p_passa_ic": p.get("p_passa_ic"),
                         "p_falha": p.get("p_falha"), "p_no_limite": p.get("p_no_limite"), "alvo": p.get("alvo"),
                         "estado": p.get("estado_probabilistico"), "nota": p.get("nota")})
        st = d.get("settings") or {}
        studies.append({"file": c.bundle.rel(r.path), "sha256": r.sha256, "n": st.get("n"), "method": st.get("method"),
                        "seed": st.get("seed"), "model": (d.get("model") or {}).get("text"),
                        "inputs": [{"path": i.get("path"), "describe": i.get("describe"), "source": i.get("source"),
                                    "pressuposto": bool(i.get("pressuposto"))} for i in d.get("inputs") or []],
                        "metrics": metrics, "requirements": reqs, "references": list(d.get("references") or [])})
    dbu = []
    for disc, lvl, k, q, _ in _flat(c.bundle.design):
        u = q.get("uncertainty")
        if u:
            dbu.append({"path": f"results.{disc}.{lvl}.{k}", "unit": q.get("unit"), "kind": u.get("kind"),
                        "p5": u.get("p5"), "p50": u.get("p50"), "p95": u.get("p95"), "sd": u.get("sd"),
                        "source": u.get("source")})
    return {"present": bool(studies or dbu), "studies": studies, "design_db": dbu}


def _mdo(c: Ctx) -> dict[str, Any]:
    studies = []
    for r in c.bundle.mdo:
        d = r.data
        ev = {e.get("id"): e for e in d.get("evaluations") or []}
        par = []
        for i in list(d.get("pareto") or [])[:PARETO_MAX_ROWS]:
            e = ev.get(i) or {}
            par.append({"id": i, "x": e.get("x"), "objectives": e.get("objectives"), "feasible": e.get("feasible")})
        ch = ev.get(d.get("chosen")) if d.get("chosen") is not None else None
        studies.append({"file": c.bundle.rel(r.path), "sha256": r.sha256, "strategy": d.get("strategy"),
                        "objectives": [{"metric": o.get("metric"), "sense": o.get("sense")}
                                       for o in d.get("objectives") or []],
                        "design_variables": [v.get("path") for v in d.get("design_variables") or []],
                        "n_evaluations": d.get("n_evaluations"), "n_failed": d.get("n_failed"),
                        "n_feasible": d.get("n_feasible"), "n_pareto": len(d.get("pareto") or []),
                        "pareto": par, "pareto_truncado": len(d.get("pareto") or []) > PARETO_MAX_ROWS,
                        "knee": d.get("knee"),
                        "chosen": ({"id": ch.get("id"), "x": ch.get("x"), "objectives": ch.get("objectives")}
                                   if ch else None),
                        "warnings": list(d.get("warnings") or [])})
    return {"present": bool(studies), "studies": studies}


def _figure_plans(b: Bundle) -> dict[str, Any]:
    """Planos de figura a partir dos registos já guardados. Não desenha o ficheiro."""
    plans = [pareto_plan(r.data, b.rel(r.path), r.sha256) for r in b.mdo]
    plans += [histogram_plan(r.data, b.rel(r.path), r.sha256) for r in b.uq]
    return {"plans": plans}


def _vv(c: Ctx) -> dict[str, Any]:
    reps = []
    for r in c.bundle.vv:
        d = r.data
        reps.append({"file": c.bundle.rel(r.path), "sha256": r.sha256, "registry_version": d.get("registry_version"),
                     "counts": d.get("counts"), "max_cost": d.get("max_cost"),
                     "cases": [{"id": k.get("id"), "discipline": k.get("discipline"), "kind": k.get("kind"),
                                "status": k.get("status"), "message": k.get("message")} for k in d.get("cases") or []]})
    return {"present": bool(reps), "reports": reps}


def _calib(c: Ctx) -> dict[str, Any]:
    recs = []
    for r in c.bundle.calib:
        d = r.data
        m = d.get("method") or {}
        recs.append({"file": c.bundle.rel(r.path), "sha256": r.sha256, "name": d.get("name"),
                     "discipline": d.get("discipline"), "level": d.get("level"), "method": m.get("name"),
                     "reference": m.get("reference"), "synthetic": bool(d.get("synthetic")),
                     "decision": d.get("decision"),
                     "parameters": [{"name": n, "value": p.get("value"), "sd": p.get("sd"), "unit": p.get("unit"),
                                     "decision": p.get("decision"), "reasons": list(p.get("reasons") or [])}
                                    for n, p in sorted((d.get("parameters") or {}).items())],
                     "validity": (d.get("validity") or {}).get("ranges")})
    return {"present": bool(recs), "records": recs}


def _sm(status: Any, msg: Any) -> str:
    return f"{status}: {msg}" if msg else str(status)


def _strings(o: Any, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(o, Mapping):
        for k, v in o.items():
            yield from _strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(o, str):
        yield path, o


def _open_items(c: Ctx, crit: list[dict[str, Any]], fid: dict[str, Any], trace: list[dict[str, Any]]
                ) -> list[dict[str, Any]]:
    b = c.bundle
    items: list[dict[str, Any]] = []

    def add(cat: str, ident: str, desc: str, src: str, sev: str) -> None:
        items.append({"categoria": cat, "id": ident, "descricao": desc, "fonte": src, "severidade": sev})

    sev_of = {"falha": "alta", "desconhecido": "media", "nao_avaliado": "media", "no_limite": "media"}
    for row_ in c.rows or []:
        s = str(row_.get("status"))
        if s in sev_of:
            w = c.waivers.get(str(row_.get("id")))
            add("requisito", str(row_.get("id")), (f"{s}: {row_['message']}" if row_.get("message") else s) +
                (f" (com dispensa: {w})" if w else ""), "matriz de verificação", "baixa" if w else sev_of[s])
    res = b.result or {}
    unreq = set(map(str, c.coverage.get("avaliadores_sem_requisito") or []))
    for ch in res.get("checks") or []:
        if not isinstance(ch, Mapping):
            continue
        key = str(ch.get("key"))
        if f"check:{key}" in unreq and ch.get("ok") is not True:
            st = "falha" if ch.get("ok") is False else "desconhecido"
            add("verificacao_sem_requisito", key, _sm(st, ch.get("message")), "result.json#checks",
                "alta" if st == "falha" else "media")
    for iss in res.get("issues") or []:
        if isinstance(iss, Mapping) and iss.get("severity") in ("warning", "error"):
            add("aviso", str(iss.get("severity")), str(iss.get("message")), "result.json#issues",
                "alta" if iss.get("severity") == "error" else "media")
    seen_p: set[str] = set()
    srcs: list[tuple[str, Any]] = [("design.json#definition", (b.design.get("definition") or {}).get("input")),
                                   ("design.json#results",
                                    {d: {lv: blk.get("notes") for lv, blk in lvs.items()}
                                     for d, lvs in (b.design.get("results") or {}).items()})]
    srcs += [(f"{b.rel(rec.path)}#pressupostos", rec.data.get("pressupostos")) for rec in b.uq + b.mdo]
    srcs += [(f"{b.rel(rec.path)}#method.notes", (rec.data.get("method") or {}).get("notes")) for rec in b.calib]
    for src, tree in srcs:
        for p, s in _strings(tree):
            if _PRESS.search(s) and s not in seen_p:
                seen_p.add(s)
                add("pressuposto", ("item" + p) if p.startswith("[") else (p or "—"), s, src, "baixa")
    for rec in b.uq:
        for i in rec.data.get("inputs") or []:
            if i.get("pressuposto"):
                add("pressuposto", str(i.get("path")), f"entrada incerta sem fonte: {i.get('describe')}",
                    b.rel(rec.path), "baixa")
    for src, tree in (("design.json", b.design), ("result.json", res)):
        for p, s in _strings(tree):
            if _OUTVAL.search(s):
                add("calibracao", p, s, src, "alta")
    for rec in b.calib:
        d = rec.data
        if d.get("synthetic"):
            add("calibracao", str(d.get("name")), "dados SINTÉTICOS: não são evidência de ensaio", b.rel(rec.path),
                "media")
        for n, p in sorted((d.get("parameters") or {}).items()):
            if p.get("decision") != "aplicar":
                add("calibracao", f"{d.get('name')}:{n}", "nao_aplicar: " + ("; ".join(p.get("reasons") or [])
                                                                             or "sem critérios cumpridos"),
                    b.rel(rec.path), "media")
    for rec in b.vv:
        for k in rec.data.get("cases") or []:
            if k.get("status") != "passa":
                add("vv", str(k.get("id")), _sm(k.get("status"), k.get("message")), b.rel(rec.path),
                    "alta" if k.get("status") == "falha" else "media")
    for rec in b.uq:
        for rid, p in sorted(((rec.data.get("propagation") or {}).get("requirements") or {}).items()):
            st = p.get("estado_probabilistico")
            if st != "prob_passa":
                add("incerteza", str(rid), _sm(st, p.get("nota")), b.rel(rec.path),
                    "alta" if st == "prob_falha" else "media")
    for rec in b.mdo:
        for w in rec.data.get("warnings") or []:
            add("mdo", "aviso", str(w), b.rel(rec.path), "baixa")
        if rec.data.get("chosen") is None:
            add("mdo", "sem_escolha", "nenhum projeto viável escolhido", b.rel(rec.path), "alta")
    for row in fid["rows"]:
        if row["status"] in ("abaixo", "ausente"):
            add("fidelidade", row["discipline"], f"{row['status']}: nível máximo {row['max_level'] or '—'}, "
                f"exigido {row['required']}", "design.json#results", "media")
        if row["n_sem_unidade"]:
            add("unidade", row["discipline"], f"{row['n_sem_unidade']} grandeza(s) numéricas sem unidade declarada "
                f"no nível {row['max_level']}", "design.json#results", "baixa")
    for t in trace:
        if t["status"] in ("difere", "em_falta"):
            add("rastreabilidade", t["path"], f"{t['status']} face ao SHA-256 registado", t["role"],
                "baixa" if t["role"] == "estado de projeto" else "alta")
    for w in b.warnings:
        add("entrada", "aviso", w, "acdt report", "media")
    order = {"alta": 0, "media": 1, "baixa": 2}
    items.sort(key=lambda i: (order[i["severidade"]], i["categoria"], i["id"], i["descricao"]))
    return items


def build(b: Bundle, gate: str, overrides: Mapping[str, Any] | None = None, now: str | None = None
          ) -> dict[str, Any]:
    """Relatório ``acdt.review/1`` de uma revisão (SRR, PDR, CDR, MDR, TRR ou PRR) a partir da evidência recolhida."""
    g = gate_key(gate)
    over = dict(overrides or {})
    prof = apply_overrides(profile_for(b.design.get("domain")), over)
    waivers = _justified(over.get("waivers"), "id", "waivers")
    tailoring = _justified(over.get("tailoring"), "criterio", "tailoring")
    unknown = set(tailoring) - {cr.id for cr in criteria_for(g)}
    if unknown:
        raise ReviewInputError(f"tailoring: critérios desconhecidos para {g}: {sorted(unknown)}")
    trace = traceability(b)
    c = Ctx(bundle=b, profile=prof, gate=g, waivers=waivers, trace=trace)
    crit = evaluate_criteria(c, criteria_for(g), tailoring)
    fid = _fidelity(c)
    figures = [{"path": b.rel(f), "sha256": next((t["sha256"] for t in trace if t["path"] == b.rel(f)), None)}
               for f in b.figures]
    return {
        "schema": SCHEMA, "gate": g, "gate_title": GATES[g]["title"], "gate_purpose": GATES[g]["purpose"],
        "standard": dict(STANDARD, table=GATES[g]["table"], section=GATES[g]["section"]),
        "generated_utc": now or _now(),
        "verdict": verdict(crit), "criteria": crit,
        "design": _design_summary(c), "requirements": _requirements(c), "fidelity": fid,
        "uq": _uq(c), "mdo": _mdo(c), "vv": _vv(c), "calibration": _calib(c),
        "open_items": _open_items(c, crit, fid, trace), "traceability": trace, "figures": figures,
        "figure_plans": _figure_plans(b),
        "overrides": {"waivers": waivers, "tailoring": tailoring,
                      "required_level": dict(prof.required_level), "primary_disciplines": primary_disciplines(c)},
        "profile_notes": list(prof.notes), "warnings": list(b.warnings),
        "nota": "nao_avaliado/desconhecido ≠ passa; insuficiente ≠ cumpre; o veredito cobre só os critérios "
                "automáticos e não substitui a decisão do painel de revisão",
    }


__all__ = ["SCHEMA", "build", "load_overrides", "traceability", "UNEVALUATED"]
