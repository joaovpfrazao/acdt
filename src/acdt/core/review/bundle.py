# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Recolha da evidência de uma revisão: estado de projeto (``acdt.design/1``) e os registos à volta.

A partir de um ``design.json`` (ou da pasta que o contém) lê, se existirem na pasta ou em subpastas (até 3
níveis), ou se forem dados explicitamente: matriz de verificação (``acdt.verification/1``), proveniência
(``acdt.provenance/1``), resultados (``result.json`` referenciado pelos blocos), estudos de incerteza
(``acdt.uq/1``), MDO (``acdt.mdo/1``), V&V (``acdt.vv/1``) e calibração (``acdt.calib/1``), e as figuras PNG.
Cada ficheiro fica com o SHA-256 atual e, quando outro registo o tinha guardado, o SHA-256 registado.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from acdt.core.provenance import sha256_file

FILE_NAMES = {"uq": "uq.json", "mdo": "mdo.json", "vv": "vv_report.json", "calib": "calibration_record.json"}
SCHEMAS = {"uq": "acdt.uq/1", "mdo": "acdt.mdo/1", "vv": "acdt.vv/1", "calib": "acdt.calib/1",
           "verification": "acdt.verification/1", "provenance": "acdt.provenance/1", "design": "acdt.design/1"}
MAX_DEPTH = 3


class ReviewInputError(ValueError):
    """Entrada inválida para o relatório de revisão (ficheiro em falta, esquema errado)."""


@dataclass
class Record:
    kind: str
    path: Path
    data: Any
    sha256: str


@dataclass
class Bundle:
    base: Path
    design_path: Path
    design: dict[str, Any]
    design_sha256: str
    matrix: dict[str, Any] | None = None
    matrix_path: Path | None = None
    provenance: dict[str, Any] | None = None
    provenance_path: Path | None = None
    result: dict[str, Any] | None = None
    result_path: Path | None = None
    uq: list[Record] = field(default_factory=list)
    mdo: list[Record] = field(default_factory=list)
    vv: list[Record] = field(default_factory=list)
    calib: list[Record] = field(default_factory=list)
    figures: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def rel(self, p: Path | str) -> str:
        """Caminho relativo à pasta do estado de projeto (barras ``/``); absoluto se não houver relativo."""
        p = Path(p)
        try:
            return Path(os.path.relpath(p.resolve(), self.base.resolve())).as_posix()
        except ValueError:  # outra unidade (Windows)
            return p.resolve().as_posix()


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        raise ReviewInputError(f"{p}: não é JSON legível ({type(ex).__name__}: {ex})") from ex


def _walk(base: Path, name: str) -> list[Path]:
    out: list[Path] = []
    base_depth = len(base.resolve().parts)
    for root, dirs, files in os.walk(base):
        depth = len(Path(root).resolve().parts) - base_depth
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "__")))
        if depth >= MAX_DEPTH:
            dirs[:] = []
        if name in files:
            out.append(Path(root) / name)
    return sorted(out)


def _expand(paths: Iterable[str | Path], name: str) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        q = Path(p)
        if q.is_dir():
            found = _walk(q, name)
            if not found:
                raise ReviewInputError(f"{q}: não tem {name}")
            out.extend(found)
        elif q.is_file():
            out.append(q)
        else:
            raise ReviewInputError(f"{q}: não existe")
    return out


def _load_record(kind: str, p: Path) -> Record:
    d = _read_json(p)
    if not isinstance(d, dict) or d.get("schema") != SCHEMAS[kind]:
        raise ReviewInputError(f"{p}: esquema {d.get('schema') if isinstance(d, dict) else '?'} ≠ {SCHEMAS[kind]}")
    return Record(kind, p, d, sha256_file(p))


def collect(design: str | Path, *, uq: Iterable[str | Path] = (), mdo: Iterable[str | Path] = (),
            vv: Iterable[str | Path] = (), calib: Iterable[str | Path] = (), discover: bool = True) -> Bundle:
    """Junta a evidência. ``design``: ``design.json`` ou pasta. Os registos dados explicitamente juntam-se aos
    descobertos na pasta (``discover``); o mesmo ficheiro não entra duas vezes."""
    from acdt.core import design_db as D

    dp = Path(design)
    if dp.is_dir():
        dp = dp / D.DEFAULT_FILE
    if not dp.is_file():
        raise ReviewInputError(f"{dp}: estado de projeto (design.json) não existe — corra primeiro o comando que o "
                               "produz (p. ex. acdt size) ou acdt db build")
    db = _read_json(dp)
    if not isinstance(db, dict) or db.get("schema") != D.SCHEMA:
        raise ReviewInputError(f"{dp}: esquema {db.get('schema') if isinstance(db, dict) else '?'} ≠ {D.SCHEMA}")
    b = Bundle(base=dp.parent, design_path=dp, design=db, design_sha256=sha256_file(dp))
    probs = D.validate(db)
    if probs:
        b.warnings.append(f"design.json não valida contra o esquema ({len(probs)} problemas; o 1.º: {probs[0]})")

    mp = dp.parent / "verification_matrix.json"
    if mp.is_file():
        m = _read_json(mp)
        if isinstance(m, dict) and m.get("schema") == SCHEMAS["verification"]:
            b.matrix, b.matrix_path = m, mp
    pp = dp.parent / "provenance.json"
    if pp.is_file():
        p = _read_json(pp)
        if isinstance(p, dict) and p.get("schema") == SCHEMAS["provenance"]:
            b.provenance, b.provenance_path = p, pp
    ev = {str(blk.get("evidence")) for lv in (db.get("results") or {}).values() for blk in lv.values()
          if blk.get("evidence")}
    if "result.json" in ev and (dp.parent / "result.json").is_file():
        b.result_path = dp.parent / "result.json"
        r = _read_json(b.result_path)
        b.result = r if isinstance(r, dict) else None

    seen: set[Path] = set()
    for kind, given in (("uq", uq), ("mdo", mdo), ("vv", vv), ("calib", calib)):
        explicit = _expand(given, FILE_NAMES[kind])
        found = _walk(dp.parent, FILE_NAMES[kind]) if discover else []
        lst: list[Record] = getattr(b, kind)
        for p in explicit + found:
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            try:
                lst.append(_load_record(kind, p))
            except ReviewInputError as ex:
                if p in explicit:  # dado explicitamente: erro de entrada
                    raise
                b.warnings.append(f"ignorado: {ex}")
    # figuras: as da pasta do projeto e as das pastas dos estudos (já produzidas; não se geram aqui)
    dirs = [dp.parent] + [r.path.parent for r in b.uq + b.mdo + b.vv + b.calib]
    figs: list[Path] = []
    for d in dirs:
        for f in sorted(d.glob("*.png")):
            if f.resolve() not in {x.resolve() for x in figs}:
                figs.append(f)
    b.figures = figs
    return b


def recorded_hashes(b: Bundle) -> dict[str, str]:
    """SHA-256 que os registos guardaram para outros ficheiros: ``{caminho absoluto resolvido: sha256}``."""
    out: dict[str, str] = {}

    def put(p: Path, h: Any) -> None:
        if isinstance(h, str) and h:
            out.setdefault(str(p.resolve()), h)

    for lv in (b.design.get("results") or {}).values():
        for blk in lv.values():
            if blk.get("evidence") and blk.get("evidence_sha256"):
                put(b.base / str(blk["evidence"]), blk["evidence_sha256"])
    if b.matrix and b.matrix.get("evidence_file"):
        put(b.base / str(b.matrix["evidence_file"]), b.matrix.get("evidence_sha256"))
    if b.provenance:
        for o in b.provenance.get("outputs") or []:
            if isinstance(o, Mapping) and o.get("path"):
                put(b.base / str(o["path"]), o.get("sha256"))
    for r in b.calib:
        f = ((r.data.get("data") or {}).get("file") or {})
        if f.get("path"):
            q = Path(str(f["path"]))
            put(q if q.is_absolute() else r.path.parent / q, f.get("sha256_bytes") or f.get("sha256"))
    return out
