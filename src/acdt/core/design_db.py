# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Base de dados única do estado de projeto (``acdt.design/1``), domínio-agnóstica.

Um ficheiro JSON (``design.json``) guarda, para um projeto:

* ``definition`` — a entrada (YAML tal como escrito, SHA-256 da fonte) e os requisitos já em SI, cada um com a
  unidade escrita e a unidade interna;
* ``results.<disciplina>.<nível>`` — um bloco por disciplina e nível de fidelidade (L0…L3, a escada de
  CAPABILITIES.md), com método, referências, origem, proveniência e as grandezas;
* ``verification`` — o resumo e as linhas da matriz de verificação (``acdt.verification/1``);
* ``uncertainty`` não é uma secção: cada grandeza pode trazer ``uncertainty`` (desvio-padrão, intervalo ou
  percentis, com a fonte) quando é conhecida. Sem incerteza conhecida o campo não existe (desconhecido ≠ zero).

Cada grandeza (:func:`quantity`) tem ``value`` e ``unit`` explícita na sintaxe pint (``"kg"``, ``"m/s"``,
``"1"`` = adimensional declarado) ou ``unit: null`` = **unidade não declarada** pela fonte (nunca se presume
adimensional). ``value: null`` = não calculado/desconhecido (nunca zero). A origem e o nível herdam-se do bloco;
uma grandeza pode sobrepor ``source``.

Funções: :func:`new`, :func:`set_results`, :func:`set_verification`, :func:`save`/:func:`load` (com validação
do esquema ``data/design.schema.json``), :func:`query` (por caminho, com ``*``), :func:`flatten` (tabela
caminho → grandeza com os campos herdados), :func:`diff` (com conversão de unidades) e :func:`to_csv`/
:func:`to_markdown`. A unidade dos resultados lê-se pelo sufixo das chaves (:func:`acdt.core.quantities.unit_from_key`).
"""
from __future__ import annotations

import copy
import csv
import fnmatch
import io
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA = "acdt.design/1"
LEVELS = ("L0", "L1", "L2", "L3")
SCHEMA_FILE = Path(__file__).parent / "data" / "design.schema.json"
DEFAULT_FILE = "design.json"
UNCERTAINTY_KINDS = ("desvio_padrao", "intervalo", "percentis")
HISTORY_MAX = 500


class DesignDBError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ construção
def _now() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def new(name: str, domain: str, definition: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Estado de projeto vazio (revisão 0)."""
    return {"schema": SCHEMA, "name": str(name), "domain": str(domain), "revision": 0, "created_utc": _now(),
            "updated_utc": _now(), "definition": dict(definition or {}), "results": {}, "verification": None,
            "history": []}


def quantity(value: Any, unit: str | None, *, source: str | None = None,
             uncertainty: Mapping[str, Any] | None = None, note: str | None = None) -> dict[str, Any]:
    """Uma grandeza. ``unit=None`` = não declarada; ``"1"`` = adimensional declarado."""
    if isinstance(value, float) and not math.isfinite(value):
        value, note = None, (note or f"valor não finito ({value}) guardado como desconhecido")
    q: dict[str, Any] = {"value": value, "unit": unit}
    if source:
        q["source"] = source
    if uncertainty:
        u = dict(uncertainty)
        if u.get("kind") not in UNCERTAINTY_KINDS:
            raise DesignDBError(f"incerteza: kind '{u.get('kind')}' não é um de {UNCERTAINTY_KINDS}")
        q["uncertainty"] = u
    if note:
        q["note"] = note
    return q


def _is_scalar(v: Any) -> bool:
    return v is None or isinstance(v, (bool, int, float, str))


def quantities_from_tree(tree: Any, prefix: str = "", unit_of: Any = None) -> dict[str, dict[str, Any]]:
    """Achata uma árvore de resultados (dicts aninhados) em ``{nome.pontuado: grandeza}``. Só escalares; listas
    ficam no ficheiro de resultados (referenciado pelo SHA-256 no bloco). Unidade pelo sufixo da chave."""
    from acdt.core.quantities import unit_from_key

    uf = unit_of or unit_from_key
    out: dict[str, dict[str, Any]] = {}

    def walk(o: Any, path: str, key: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{path}.{k}" if path else str(k), str(k))
        elif _is_scalar(o):
            if isinstance(o, (bool, str)):
                out[path] = quantity(o, None)  # texto/booleano: sem unidade
            else:
                out[path] = quantity(o, uf(key))
    walk(tree, prefix, prefix.rsplit(".", 1)[-1] if prefix else "")
    return out


def set_results(db: dict[str, Any], discipline: str, level: str, quantities: Mapping[str, Mapping[str, Any]], *,
                method: str = "", references: Iterable[str] = (), source: str = "", evidence: str | None = None,
                evidence_sha256: str | None = None, provenance: Mapping[str, Any] | None = None,
                notes: Iterable[str] = (), sections: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Escreve (substitui) o bloco ``results.<disciplina>.<nível>``. Devolve o bloco. ``sections``: método por
    prefixo de nome (``{"aero": "…"}``) quando o bloco junta várias secções da fonte."""
    if level not in LEVELS:
        raise DesignDBError(f"nível '{level}' não é um de {LEVELS}")
    if not discipline or "." in discipline:
        raise DesignDBError(f"disciplina '{discipline}' inválida (não vazia, sem '.')")
    blk = {"method": method, "references": list(references), "source": source, "evidence": evidence,
           "evidence_sha256": evidence_sha256, "provenance": dict(provenance or {}), "updated_utc": _now(),
           "notes": list(notes), "sections": dict(sections or {}),
           "quantities": {k: dict(v) for k, v in quantities.items()}}
    db.setdefault("results", {}).setdefault(discipline, {})[level] = blk
    _touch(db, f"results.{discipline}.{level}")
    return blk


def set_uncertainty(db: dict[str, Any], path: str, uncertainty: Mapping[str, Any]) -> None:
    """Junta incerteza conhecida a uma grandeza existente (p. ex. percentis de ``acdt uq``)."""
    hit = _find_quantity(db, path)
    if hit is None:
        raise DesignDBError(f"grandeza '{path}' não existe")
    hit.update(quantity(hit.get("value"), hit.get("unit"), uncertainty=uncertainty))
    _touch(db, path)


def set_verification(db: dict[str, Any], matrix: Mapping[str, Any] | None, evidence: str | None = None) -> None:
    """Guarda o resumo e as linhas da matriz (``acdt.verification/1``) — os campos que a rastreiam."""
    if not matrix:
        db["verification"] = None
        return
    keep = ("id", "status", "quantity", "comparison", "threshold", "unit", "value", "margin", "tolerance",
            "method", "fidelity_required", "fidelity_evaluated", "evaluator", "evidence", "message")
    rows = [{k: r.get(k) for k in keep} for r in matrix.get("rows", [])]
    counts: dict[str, int] = {}
    for r in rows:
        counts[str(r["status"])] = counts.get(str(r["status"]), 0) + 1
    db["verification"] = {"schema": matrix.get("schema"), "evidence": evidence,
                          "provenance": dict(matrix.get("provenance") or {}), "counts": counts,
                          "coverage": matrix.get("coverage"), "rows": rows}
    _touch(db, "verification")


def _touch(db: dict[str, Any], what: str) -> None:
    db["updated_utc"] = _now()
    h = db.setdefault("history", [])
    h.append({"utc": db["updated_utc"], "what": what})
    del h[:-HISTORY_MAX]


# ------------------------------------------------------------------------------------------- disco + esquema
def validate(db: Mapping[str, Any]) -> list[str]:
    """Erros de esquema (lista vazia = válido). Usa ``jsonschema`` se instalado; senão verificações essenciais."""
    errs: list[str] = []
    if db.get("schema") != SCHEMA:
        return [f"schema '{db.get('schema')}' não é '{SCHEMA}'"]
    try:
        import jsonschema
    except ImportError:
        jsonschema = None  # type: ignore[assignment]
    if jsonschema is not None:
        sch = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
        v = jsonschema.Draft202012Validator(sch)
        for e in sorted(v.iter_errors(db), key=lambda e: list(e.absolute_path)):
            errs.append(f"{'/'.join(str(p) for p in e.absolute_path) or '(raiz)'}: {e.message}")
        return errs
    for k in ("name", "domain", "revision", "definition", "results"):  # pragma: no cover — sem jsonschema
        if k not in db:
            errs.append(f"falta '{k}'")
    for d, lv in (db.get("results") or {}).items():
        for lvl, blk in lv.items():
            if lvl not in LEVELS:
                errs.append(f"results/{d}/{lvl}: nível inválido")
            for n, q in (blk.get("quantities") or {}).items():
                if "value" not in q or "unit" not in q:
                    errs.append(f"results/{d}/{lvl}/quantities/{n}: falta value/unit")
    return errs


def _json_default(o: Any) -> Any:
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:  # pragma: no cover
        pass
    if isinstance(o, Path):
        return str(o)
    return str(o)


def _clean(o: Any) -> Any:
    """NaN/inf → None (JSON estrito; desconhecido, nunca zero)."""
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def dumps(db: Mapping[str, Any]) -> str:
    return json.dumps(_clean(json.loads(json.dumps(db, default=_json_default))), indent=1, ensure_ascii=False,
                      sort_keys=True, allow_nan=False)


def save(db: dict[str, Any], path: str | Path, bump: bool = True) -> Path:
    """Valida e escreve. ``bump`` incrementa a revisão."""
    if bump:
        db["revision"] = int(db.get("revision", 0)) + 1
    txt = dumps(db)
    errs = validate(json.loads(txt))
    if errs:
        raise DesignDBError("estado de projeto inválido:\n  " + "\n  ".join(errs[:20]))
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt + "\n", encoding="utf-8")
    return p


def load(path: str | Path, check: bool = True) -> dict[str, Any]:
    """Lê ``design.json`` (ou a pasta que o contém)."""
    p = Path(path)
    if p.is_dir():
        p = p / DEFAULT_FILE
    if not p.is_file():
        raise FileNotFoundError(f"{p} não existe")
    db = json.loads(p.read_text(encoding="utf-8"))
    if check:
        errs = validate(db)
        if errs:
            raise DesignDBError(f"{p}: estado de projeto inválido:\n  " + "\n  ".join(errs[:20]))
    return db


# --------------------------------------------------------------------------------------------- consulta
_INHERIT = ("method", "source", "evidence", "evidence_sha256")


def flatten(db: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """``{caminho: grandeza}`` com os campos herdados do bloco (disciplina, nível, método, origem, proveniência).

    Caminhos: ``definition.requirements.<chave>``, ``results.<disciplina>.<nível>.<nome>``,
    ``verification.<id>``."""
    out: dict[str, dict[str, Any]] = {}
    for k, q in ((db.get("definition") or {}).get("requirements") or {}).items():
        out[f"definition.requirements.{k}"] = {**q, "discipline": "requisitos", "level": None,
                                               "source": q.get("source", "entrada")}
    for d, lv in (db.get("results") or {}).items():
        for lvl, blk in lv.items():
            fp = (blk.get("provenance") or {}).get("fingerprint")
            for n, q in (blk.get("quantities") or {}).items():
                e = {"discipline": d, "level": lvl, "provenance_fingerprint": fp}
                e.update({k: blk.get(k) for k in _INHERIT})
                sec = (blk.get("sections") or {}).get(n.split(".", 1)[0])
                if sec:
                    e["method"] = sec
                e.update(q)
                out[f"results.{d}.{lvl}.{n}"] = e
    for r in ((db.get("verification") or {}).get("rows") or []):
        out[f"verification.{r.get('id')}"] = {"value": r.get("status"), "unit": None, "discipline": "verificacao",
                                              "level": r.get("fidelity_evaluated"), "source": r.get("evaluator"),
                                              "measured": r.get("value"), "threshold": r.get("threshold"),
                                              "measured_unit": r.get("unit"), "margin": r.get("margin")}
    return out


def _find_quantity(db: Mapping[str, Any], path: str) -> dict[str, Any] | None:
    parts = path.split(".")
    if parts[:2] == ["definition", "requirements"] and len(parts) >= 3:
        return ((db.get("definition") or {}).get("requirements") or {}).get(".".join(parts[2:]))
    if parts[0] == "results" and len(parts) >= 4:
        blk = ((db.get("results") or {}).get(parts[1]) or {}).get(parts[2])
        if blk:
            return (blk.get("quantities") or {}).get(".".join(parts[3:]))
    return None


def query(db: Mapping[str, Any], pattern: str) -> dict[str, dict[str, Any]]:
    """Grandezas cujo caminho corresponde a ``pattern``: caminho exato, glob (``results.*.*.weights.W0_kg``,
    ``*W0_kg``) ou sufixo do nome (``W0_kg`` → todas as disciplinas/níveis)."""
    flat = flatten(db)
    if pattern in flat:
        return {pattern: flat[pattern]}
    if any(c in pattern for c in "*?["):
        return {k: v for k, v in flat.items() if fnmatch.fnmatchcase(k, pattern)}
    return {k: v for k, v in flat.items() if k.endswith("." + pattern)}


def get_value(db: Mapping[str, Any], path: str, unit: str | None = None) -> Any:
    """Valor de uma grandeza (caminho exato), opcionalmente convertido para ``unit``."""
    q = flatten(db).get(path)
    if q is None:
        raise KeyError(path)
    v = q.get("value")
    if unit is None or v is None or isinstance(v, (bool, str)):
        return v
    if q.get("unit") is None:
        raise DesignDBError(f"{path}: unidade não declarada; não converto para '{unit}'")
    from acdt.core.quantities import convert
    return convert(float(v), q["unit"], unit, path)


# ------------------------------------------------------------------------------------------------- diff
def diff(a: Mapping[str, Any], b: Mapping[str, Any], rtol: float = 1e-6, atol: float = 0.0,
         include: str | None = None) -> dict[str, Any]:
    """Diferenças entre dois estados (A → B), por caminho. Valores numéricos comparados na unidade de A (B é
    convertido quando as unidades diferem mas a dimensão é a mesma); unidades incompatíveis são uma mudança."""
    from acdt.core.quantities import QuantityError, convert

    fa, fb = flatten(a), flatten(b)
    if include:
        fa = {k: v for k, v in fa.items() if fnmatch.fnmatchcase(k, include)}
        fb = {k: v for k, v in fb.items() if fnmatch.fnmatchcase(k, include)}
    added = sorted(set(fb) - set(fa))
    removed = sorted(set(fa) - set(fb))
    changed: list[dict[str, Any]] = []
    for k in sorted(set(fa) & set(fb)):
        qa, qb = fa[k], fb[k]
        va, vb = qa.get("value"), qb.get("value")
        ua, ub = qa.get("unit"), qb.get("unit")
        ent: dict[str, Any] = {"path": k, "a": va, "b": vb, "unit": ua}
        num = all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (va, vb))
        if num and ua != ub:
            if ua is None or ub is None:
                ent.update(kind="unidade", unit_b=ub)
                changed.append(ent)
                continue
            try:
                vb = convert(float(vb), ub, ua, k)  # type: ignore[arg-type]
                ent["b"], ent["b_original"], ent["unit_b"] = vb, qb.get("value"), ub
            except QuantityError as ex:
                ent.update(kind="unidade_incompativel", unit_b=ub, message=str(ex))
                changed.append(ent)
                continue
        if num:
            fva, fvb = float(va), float(vb)  # type: ignore[arg-type]
            if abs(fvb - fva) > atol + rtol * max(abs(fva), abs(fvb)):
                ent.update(kind="valor", delta=fvb - fva, rel=(fvb - fva) / abs(fva) if fva else None)
                changed.append(ent)
        elif va != vb:
            ent["kind"] = "valor"
            changed.append(ent)
        elif ua != ub:
            ent.update(kind="unidade", unit_b=ub)
            changed.append(ent)
        if qa.get("level") != qb.get("level") or qa.get("method") != qb.get("method"):
            if not changed or changed[-1]["path"] != k:
                changed.append({"path": k, "kind": "fidelidade", "a": qa.get("level"), "b": qb.get("level"),
                                "method_a": qa.get("method"), "method_b": qb.get("method")})
    return {"a": {"name": a.get("name"), "revision": a.get("revision")},
            "b": {"name": b.get("name"), "revision": b.get("revision")}, "rtol": rtol, "atol": atol,
            "added": added, "removed": removed, "changed": changed,
            "identical": not (added or removed or changed)}


def explain_diff(d: Mapping[str, Any], limit: int = 200) -> str:
    lines = [f"A: {d['a']['name']} (rev {d['a']['revision']})  →  B: {d['b']['name']} (rev {d['b']['revision']})"]
    if d["identical"]:
        lines.append(f"idênticos (rtol={d['rtol']:g}, atol={d['atol']:g})")
        return "\n".join(lines)
    lines.append(f"{len(d['changed'])} alteradas, {len(d['added'])} novas, {len(d['removed'])} removidas")
    for c in d["changed"][:limit]:
        if c.get("kind") == "valor" and c.get("delta") is not None:
            rel = f" ({100 * c['rel']:+.3g} %)" if c.get("rel") is not None else ""
            lines.append(f"  ~ {c['path']}: {_fmt(c['a'])} → {_fmt(c['b'])} {c.get('unit') or ''}{rel}".rstrip())
        else:
            extra = f" [{c.get('unit')} → {c.get('unit_b')}]" if "unit_b" in c else ""
            lines.append(f"  ~ {c['path']} ({c.get('kind')}): {_fmt(c.get('a'))} → {_fmt(c.get('b'))}{extra}")
    for k in d["added"][:limit]:
        lines.append(f"  + {k}")
    for k in d["removed"][:limit]:
        lines.append(f"  - {k}")
    return "\n".join(lines)


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    return "—" if v is None else str(v)


# ------------------------------------------------------------------------------------------------ export
EXPORT_COLUMNS = ("path", "value", "unit", "discipline", "level", "method", "source", "uncertainty",
                  "provenance_fingerprint", "note")


def _unc_text(u: Mapping[str, Any] | None) -> str:
    if not u:
        return ""
    return json.dumps(u, ensure_ascii=False, sort_keys=True)


def rows(db: Mapping[str, Any], pattern: str | None = None) -> list[dict[str, Any]]:
    flat = query(db, pattern) if pattern else flatten(db)
    out = []
    for k, q in flat.items():
        r = {c: q.get(c) for c in EXPORT_COLUMNS}
        r["path"] = k
        r["uncertainty"] = _unc_text(q.get("uncertainty"))
        out.append(r)
    return out


def to_csv(db: Mapping[str, Any], pattern: str | None = None) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(EXPORT_COLUMNS), lineterminator="\n")
    w.writeheader()
    for r in rows(db, pattern):
        w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return buf.getvalue()


def to_markdown(db: Mapping[str, Any], pattern: str | None = None) -> str:
    from acdt.core.quantities import display_unit

    lines = [f"# Estado de projeto — {db.get('name')} (rev {db.get('revision')}, `{SCHEMA}`)", "",
             "| caminho | valor | unidade | nível | método | origem |", "|---|---|---|---|---|---|"]
    for r in rows(db, pattern):
        u = "não declarada" if r["unit"] is None and isinstance(r["value"], (int, float)) \
            and not isinstance(r["value"], bool) else display_unit(r["unit"])
        lines.append(f"| `{r['path']}` | {_fmt(r['value'])} | {u} | {r['level'] or ''} | {r['method'] or ''} | "
                     f"{r['source'] or ''} |")
    return "\n".join(lines) + "\n"


def summary(db: Mapping[str, Any]) -> str:
    """Resumo legível: disciplinas × níveis, contagens, verificação."""
    res = db.get("results") or {}
    lines = [f"{db.get('name')}  ({db.get('domain')}, {SCHEMA}, revisão {db.get('revision')}, "
             f"atualizado {db.get('updated_utc')})"]
    src = (db.get("definition") or {}).get("source") or {}
    if src:
        lines.append(f"entrada: {src.get('path')}  sha256 {str(src.get('sha256'))[:12]}…")
    nreq = len((db.get("definition") or {}).get("requirements") or {})
    lines.append(f"requisitos: {nreq}")
    for d in sorted(res):
        for lvl in sorted(res[d]):
            blk = res[d][lvl]
            qs = blk.get("quantities") or {}
            nu = sum(1 for q in qs.values() if q.get("unit") is None and isinstance(q.get("value"), (int, float))
                     and not isinstance(q.get("value"), bool))
            nn = sum(1 for q in qs.values() if q.get("value") is None)
            nunc = sum(1 for q in qs.values() if q.get("uncertainty"))
            lines.append(f"  {d:<18} {lvl}  {len(qs):4d} grandezas ({nu} sem unidade declarada, {nn} desconhecidas, "
                         f"{nunc} com incerteza)  método: {blk.get('method') or '—'}")
    v = db.get("verification")
    if v:
        lines.append("verificação: " + ", ".join(f"{k} {n}" for k, n in sorted(v.get("counts", {}).items())))
    return "\n".join(lines)


def copy_db(db: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(db))
