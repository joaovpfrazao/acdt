# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Relatórios automáticos de revisão de projeto (SRR, PDR, CDR; ``acdt report``; docs/RELATORIOS.md).

Critérios de entrada e de sucesso de NASA NPR 7123.1D, Apêndice G (Tabelas G-4, G-6, G-7), avaliados sobre o
estado de projeto (``acdt.design/1``) e os registos à volta (verificação, proveniência, UQ, MDO, V&V,
calibração). Veredito ``pronto`` / ``nao_pronto`` / ``insuficiente``; dados em falta nunca contam como cumpridos.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from .build import SCHEMA, build, load_overrides
from .bundle import Bundle, ReviewInputError, collect
from .criteria import CRITERIA, GATES, STANDARD, VERDICTS
from .profile import ReviewProfile, register_profile
from .render import to_html, to_markdown, write

#: Código de saída do CLI por veredito (docs/API.md §4).
EXIT_CODE = {"pronto": 0, "nao_pronto": 1, "insuficiente": 3}


def report(design: str | Path, gate: str, output: str | Path | None = None, *, uq: Iterable[str | Path] = (),
           mdo: Iterable[str | Path] = (), vv: Iterable[str | Path] = (), calib: Iterable[str | Path] = (),
           criteria: str | Path | Mapping[str, Any] | None = None, discover: bool = True, pdf: bool = False,
           now: str | None = None) -> dict[str, Any]:
    """Relatório completo; escreve os ficheiros em ``output`` se dado (``files`` no resultado)."""
    b = collect(design, uq=uq, mdo=mdo, vv=vv, calib=calib, discover=discover)
    over = dict(criteria) if isinstance(criteria, Mapping) else load_overrides(criteria)
    r = build(b, gate, over, now=now)
    if output is not None:
        r["files"] = [str(p) for p in write(r, output, b.base, pdf=pdf)]
    return r


__all__ = ["SCHEMA", "CRITERIA", "GATES", "STANDARD", "VERDICTS", "EXIT_CODE", "Bundle", "ReviewInputError",
           "ReviewProfile", "build", "collect", "load_overrides", "register_profile", "report", "to_html",
           "to_markdown", "write"]
