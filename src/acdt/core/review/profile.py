# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Perfis de revisão por domínio: disciplinas primárias, grandezas de resumo e a grandeza de viabilidade.

Um domínio regista o seu perfil (:func:`register_profile`); sem perfil usa-se o genérico: todas as disciplinas
registadas no estado de projeto são primárias (exceto ``outros``, ``calibracao``, ``mdo`` e ``vv``), sem
grandezas de resumo escolhidas, e a viabilidade lê-se de qualquer grandeza chamada ``feasible``.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Mapping

from .criteria import DEFAULT_REQUIRED_LEVEL

NON_PRIMARY = ("outros", "calibracao", "mdo", "vv")


@dataclass(frozen=True)
class ReviewProfile:
    domain: str
    primary_disciplines: tuple[str, ...] = ()       # vazio = as que existirem no estado de projeto
    headline: tuple[str, ...] = ()                  # nomes (fim do caminho) das grandezas do resumo
    feasibility: tuple[str, ...] = ("feasible",)    # nomes de grandezas booleanas de viabilidade
    required_level: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_REQUIRED_LEVEL))
    notes: tuple[str, ...] = ()


_PROFILES: dict[str, ReviewProfile] = {}


def register_profile(p: ReviewProfile) -> ReviewProfile:
    _PROFILES[p.domain] = p
    return p


def profile_for(domain: str | None) -> ReviewProfile:
    d = str(domain or "")
    if d and d not in _PROFILES:
        try:  # o domínio regista o perfil ao ser importado
            importlib.import_module(f"acdt.domains.{d}")
        except ImportError:
            pass
    return _PROFILES.get(d) or ReviewProfile(domain=d or "generico")


def apply_overrides(p: ReviewProfile, over: Mapping[str, Any] | None) -> ReviewProfile:
    """Perfil com as substituições do ficheiro de critérios (``primary_disciplines``, ``headline``,
    ``required_level``)."""
    if not over:
        return p
    lvl = dict(p.required_level)
    lvl.update({str(k).upper(): str(v) for k, v in (over.get("required_level") or {}).items()})
    return ReviewProfile(
        domain=p.domain,
        primary_disciplines=tuple(over.get("primary_disciplines") or p.primary_disciplines),
        headline=tuple(over.get("headline") or p.headline),
        feasibility=tuple(over.get("feasibility") or p.feasibility),
        required_level=lvl, notes=p.notes)
