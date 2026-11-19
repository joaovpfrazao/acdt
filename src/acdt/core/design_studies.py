# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Liga estudos já gravados ao estado de projeto ``acdt.design/1``.

Não calcula um avião. Copia números finitos que o ficheiro já traz. Um valor em falta não entra
(desconhecido não é zero). ``nao_avaliado`` não vira ``passa``.

* ``acdt.mdo/1`` → ``results.mdo.L2`` e ``definition.derived.mdo``. O nível L2 é o que docs/DADOS.md
  pede para este bloco. PRESSUPOSTO: não é uma análise aerodinâmica L2.
* ``acdt.vv/1`` → ``results.vv.L0``. PRESSUPOSTO: o esquema só tem L0…L3; este bloco é o relatório da
  framework, não a fidelidade do avião. O erro relativo é o ``delta_rel`` já gravado.
* Passos de ``acdt hifi`` → ``results.<disciplina>.L3``, só escalares finitos. Uma estimativa de malha
  RANS (sem CL) não entra como aerodinâmica. Um passo ``skipped`` não escreve números.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from acdt.core import design_db as D
from acdt.core.provenance import sha256_file
from acdt.core.quantities import unit_from_key

# PRESSUPOSTO: a pasta do passo diz a disciplina. Não substitui o L0/L1 dessa disciplina.
HIFI_DISCIPLINE: dict[str, str] = {
    "geometry": "geometria",
    "cfd2d": "aerodinamica",
    "gci": "aerodinamica",
    "wing_euler": "aerodinamica",
    "rans_case": "aerodinamica",
    "fem": "estruturas",
    "flutter": "aeroelasticidade",
    "nastran": "estruturas",
    "detailed": "dimensionamento",
    "nlgeom": "estruturas",
}
HIFI_FILES: dict[str, str] = {
    "geometry": "geometry/geometry.json",
    "cfd2d": "cfd2d/section_verification.json",
    "gci": "gci/gci.json",
    "wing_euler": "wing_euler/wing_euler.json",
    "rans_case": "rans_case/estimate.json",
    "fem": "fem/fem_results.json",
    "flutter": "flutter/flutter_results.json",
    "nastran": "nastran/nastran.json",
    "detailed": "detailed/detailed.json",
    "nlgeom": "fem/nlgeom.json",
}
_SKIP_DESCENT = {"meta", "mesh", "modes", "shapes", "commands", "trace", "loads", "markers", "avl",
                 "notes", "files", "alpha", "increment", "riks", "material", "spar"}


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def _map(v: Any) -> Mapping[Any, Any]:
    return v if isinstance(v, Mapping) else {}


def _id_key(v: Any) -> str | int | None:
    if isinstance(v, bool) or not isinstance(v, (str, int)):
        return None
    return v


def _num(x: Any) -> int | float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise TypeError(x)
    return int(x) if isinstance(x, int) else float(x)


def _load(path: str | Path, names: tuple[str, ...]) -> tuple[Path, dict[str, Any]]:
    p = Path(path)
    if p.is_dir():
        hit = next((p / n for n in names if (p / n).is_file()), None)
        if hit is None:
            raise D.DesignDBError(f"{p}: nenhum de {names}")
        p = hit
    if not p.is_file():
        raise D.DesignDBError(f"{p} não existe")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise D.DesignDBError(f"{p}: o JSON não é um objeto")
    return p, data


def _put(qs: dict[str, dict[str, Any]], name: str, value: Any, unit: str | None, note: str = "") -> None:
    if isinstance(value, str):
        qs[name] = D.quantity(value, None, note=note or None)
        return
    if not _finite(value):
        return
    qs[name] = D.quantity(_num(value), unit, note=note or None)


def attach_mdo(db: dict[str, Any], study: Mapping[str, Any], *, evidence: str | None,
               evidence_sha256: str | None) -> dict[str, Any]:
    """Copia o estudo ``acdt.mdo/1`` para ``results.mdo.L2``. Não altera outras disciplinas."""
    if study.get("schema") != "acdt.mdo/1":
        raise D.DesignDBError(f"estudo MDO com schema '{study.get('schema')}' (esperado acdt.mdo/1)")
    qs: dict[str, dict[str, Any]] = {}
    omitidas: list[str] = []
    for key in ("n_evaluations", "n_failed", "n_feasible"):
        if _finite(study.get(key)):
            _put(qs, key, study[key], None)
        else:
            omitidas.append(key)
    frente = study.get("pareto")
    if isinstance(frente, list):
        _put(qs, "n_pareto", len(frente), None)
    else:
        omitidas.append("pareto")
    raw_evs = study.get("evaluations")
    evs = raw_evs if isinstance(raw_evs, list) else []
    by_id: dict[str | int, Mapping[Any, Any]] = {}
    for e in evs:
        if isinstance(e, Mapping):
            eid = _id_key(e.get("id"))
            if eid is not None:
                by_id[eid] = e
    chosen_id = study.get("chosen")
    chosen_key = _id_key(chosen_id)
    chosen = by_id.get(chosen_key) if chosen_key is not None else None
    notas = ["PRESSUPOSTO: L2 é o nível de armazenamento pedido em docs/DADOS.md, não uma análise L2.",
             "A lista de identificadores da frente fica no mdo.json (não é uma grandeza)."]
    variaveis: dict[str, Any] = {}
    if chosen is None:
        notas.append("nenhum projeto escolhido no registo: objetivos e variáveis não foram escritos")
        omitidas.append("chosen")
    else:
        objs = _map(chosen.get("objectives"))
        for met, val in objs.items():
            if _finite(val):
                _put(qs, f"objetivo.{met}", val, unit_from_key(str(met)))
            else:
                omitidas.append(f"objetivo.{met}")
        xs = _map(chosen.get("x"))
        for path, val in xs.items():
            if _finite(val):
                _put(qs, f"x.{path}", val, unit_from_key(str(path).rsplit(".", 1)[-1]))
                variaveis[str(path)] = _num(val)
            else:
                omitidas.append(f"x.{path}")
        if isinstance(chosen.get("feasible"), bool):
            qs["escolhido.feasible"] = D.quantity(chosen["feasible"], None)
    definition = db.setdefault("definition", {})
    if not isinstance(definition, dict):
        notas.append("definition não é um objeto: as variáveis derivadas não foram escritas")
    else:
        derived = definition.get("derived")
        if derived is None:
            derived = {}
            definition["derived"] = derived
        if isinstance(derived, dict):
            derived["mdo"] = {"source": "acdt mdo", "evidence": evidence, "evidence_sha256": evidence_sha256,
                              "chosen": chosen_id, "variables": variaveis}
        else:
            notas.append("definition.derived já existe e não é um objeto: não foi substituído")
    D.set_results(db, "mdo", "L2", qs, method=f"acdt mdo ({study.get('strategy') or 'estratégia não declarada'})",
                  source="acdt mdo", evidence=evidence, evidence_sha256=evidence_sha256, notes=notas)
    return {"veredicto": "validado" if qs else "nao_avaliado", "calibracao": "nao_aplicar",
            "escritas": sorted(qs), "omitidas": omitidas}


def attach_vv(db: dict[str, Any], report: Mapping[str, Any], *, evidence: str | None,
              evidence_sha256: str | None) -> dict[str, Any]:
    """Copia o relatório ``acdt.vv/1``. O ``delta_rel`` nulo não é escrito como zero."""
    if report.get("schema") != "acdt.vv/1":
        raise D.DesignDBError(f"relatório V&V com schema '{report.get('schema')}' (esperado acdt.vv/1)")
    qs: dict[str, dict[str, Any]] = {}
    omitidas: list[str] = []
    raw_counts = report.get("counts")
    counts = raw_counts if isinstance(raw_counts, Mapping) else {}
    for st, n in counts.items():
        if _finite(n):
            _put(qs, f"counts.{st}", n, None)
    for case in report.get("cases") or []:
        if not isinstance(case, Mapping) or not case.get("id"):
            continue
        cid = str(case["id"]).replace(".", "_")
        if isinstance(case.get("status"), str):
            qs[f"caso.{cid}.status"] = D.quantity(str(case["status"]), None)
        for row in case.get("results") or []:
            if not isinstance(row, Mapping) or not row.get("quantity"):
                continue
            qn = str(row["quantity"]).replace(".", "_")
            estado = str(row.get("status") or "")
            base = f"caso.{cid}.{qn}"
            if estado in ("nao_avaliado", "desconhecido"):
                omitidas.append(base)
                continue
            unit = row.get("unit") if isinstance(row.get("unit"), str) and row.get("unit") else None
            if _finite(row.get("delta")):
                _put(qs, f"{base}.delta", row["delta"], unit)
            else:
                omitidas.append(f"{base}.delta")
            if _finite(row.get("delta_rel")):
                _put(qs, f"{base}.delta_rel", row["delta_rel"], "1",
                     note="(computado − referência) / |referência|, já gravado no relatório")
            else:
                omitidas.append(f"{base}.delta_rel")
    notas = ["PRESSUPOSTO: L0 é a casa que o esquema acdt.design/1 obriga. Este bloco é o relatório "
             "acdt.vv/1 da framework, não a fidelidade do avião.",
             "nao_avaliado e desconhecido não trazem erro (não é zero e não é passa)."]
    versao = report.get("registry_version")
    refs = [versao] if isinstance(versao, str) and versao else []
    D.set_results(db, "vv", "L0", qs, method="acdt vv (casos publicados; erro já calculado no relatório)",
                  source="acdt vv", evidence=evidence, evidence_sha256=evidence_sha256, notes=notas,
                  references=refs)
    return {"veredicto": "validado" if qs else "nao_avaliado", "calibracao": "nao_aplicar",
            "escritas": sorted(qs), "omitidas": omitidas}


def _hifi_quantities(step: str, payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    qs: dict[str, dict[str, Any]] = {}

    def take(name: str, value: Any, unit_key: str) -> None:
        if _finite(value):
            _put(qs, f"{step}.{name}", value, unit_from_key(unit_key))

    for key, val in payload.items():
        if key in _SKIP_DESCENT or key == "skipped":
            continue
        if _finite(val):
            take(str(key), val, str(key))
        elif isinstance(val, Mapping):
            for key2, val2 in val.items():
                if key2 in _SKIP_DESCENT or not _finite(val2):
                    continue
                leaf = str(key2)
                take(f"{key}.{leaf}", val2, leaf)
    return qs


def attach_hifi_step(db: dict[str, Any], step: str, payload: Mapping[str, Any], *, evidence: str | None,
                     evidence_sha256: str | None) -> dict[str, Any]:
    """Um passo de ``acdt hifi``. Sem escalares finitos, não cria o nível L3."""
    if step == "rans_case" and not _finite(payload.get("CL")):
        return {"veredicto": "nao_avaliado", "calibracao": "nao_aplicar", "escritas": [],
                "motivo": "o caso RANS de avião completo neste ficheiro não traz CL; uma estimativa de malha "
                          "não entra como aerodinâmica L3"}
    if step not in HIFI_DISCIPLINE:
        return {"veredicto": "nao_avaliado", "calibracao": "nao_aplicar", "escritas": [],
                "motivo": f"passo '{step}' sem disciplina declarada"}
    if "skipped" in payload:
        return {"veredicto": "nao_avaliado", "calibracao": "nao_aplicar", "escritas": [],
                "motivo": f"passo não corrido: {payload.get('skipped')}"}
    qs = _hifi_quantities(step, payload)
    if not qs:
        return {"veredicto": "nao_avaliado", "calibracao": "nao_aplicar", "escritas": [],
                "motivo": "o ficheiro não traz escalares finitos para copiar"}
    disc = HIFI_DISCIPLINE[step]
    prev = ((db.get("results") or {}).get(disc) or {}).get("L3") or {}
    if not isinstance(prev, Mapping):
        prev = {}
    merged = dict(_map(prev.get("quantities")))
    merged.update(qs)
    sections = {str(k): str(v) for k, v in _map(prev.get("sections")).items()}
    sections[step] = f"acdt hifi passo {step}"
    notes = [n for n in (prev.get("notes") or []) if isinstance(n, str)]
    anterior = prev.get("evidence")
    if isinstance(anterior, str) and anterior and anterior != evidence:
        notes.append(f"evidência anterior do bloco: {anterior} (sha256 {prev.get('evidence_sha256')})")
    notes.append(f"{step}: escalares finitos do ficheiro; unidade pelo sufixo do nome, senão não declarada. "
                 "PRESSUPOSTO: a disciplina é a da pasta do passo. O campo evidence fica com o último ficheiro.")
    refs = [r for r in (prev.get("references") or []) if isinstance(r, str)]
    D.set_results(db, disc, "L3", merged, method="acdt hifi", source="acdt hifi", evidence=evidence,
                  evidence_sha256=evidence_sha256, notes=notes, sections=sections, references=refs)
    return {"veredicto": "validado", "calibracao": "nao_aplicar", "disciplina": disc,
            "escritas": sorted(qs)}


def attach_mdo_file(db: dict[str, Any], path: str | Path) -> dict[str, Any]:
    p, data = _load(path, ("mdo.json",))
    return attach_mdo(db, data, evidence=p.as_posix(), evidence_sha256=sha256_file(p))


def attach_vv_file(db: dict[str, Any], path: str | Path) -> dict[str, Any]:
    p, data = _load(path, ("vv_report.json",))
    return attach_vv(db, data, evidence=p.as_posix(), evidence_sha256=sha256_file(p))


def attach_hifi_path(db: dict[str, Any], path: str | Path, step: str | None = None) -> list[dict[str, Any]]:
    """Uma pasta de ``acdt hifi`` (vários passos) ou um JSON (``step`` obrigatório)."""
    p = Path(path)
    out: list[dict[str, Any]] = []
    if p.is_dir():
        found = False
        for name, rel in HIFI_FILES.items():
            fp = p / rel
            if not fp.is_file():
                continue
            found = True
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                rep = attach_hifi_step(db, name, data, evidence=fp.as_posix(), evidence_sha256=sha256_file(fp))
            else:
                rep = {"veredicto": "nao_avaliado", "motivo": f"{fp} não é um objeto"}
            rep["passo"] = name
            out.append(rep)
        if not found:
            raise D.DesignDBError(f"{p}: nenhum JSON de passo hifi conhecido")
        return out
    if not step:
        raise D.DesignDBError("add-hifi de um ficheiro precisa de --step")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise D.DesignDBError(f"{p}: o JSON não é um objeto")
    rep = attach_hifi_step(db, step, data, evidence=p.as_posix(), evidence_sha256=sha256_file(p))
    rep["passo"] = step
    return [rep]
