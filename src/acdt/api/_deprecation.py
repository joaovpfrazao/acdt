# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Ajudante de descontinuação da API pública (política em docs/API.md §3).

Um nome público descontinuado continua a funcionar e emite :class:`ACDTDeprecationWarning` com a versão em que foi
descontinuado, a versão em que sai e a alternativa. Só pode ser removido numa versão MAIOR da API, e nunca antes de
ter passado por pelo menos uma versão MENOR já descontinuado."""
from __future__ import annotations

import functools
import warnings
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

#: nome → {"since", "removed_in", "alternative"} dos nomes descontinuados (lido pelo teste de estabilidade)
DEPRECATED: dict[str, dict[str, str | None]] = {}


class ACDTDeprecationWarning(DeprecationWarning):
    """Aviso de descontinuação da API pública do acdt (subclasse de :class:`DeprecationWarning`)."""


def _parse(v: str) -> tuple[int, int, int]:
    parts = [int(x) for x in v.split(".")]
    if len(parts) != 3:
        raise ValueError(f"versão {v!r} não é MAIOR.MENOR.CORREÇÃO")
    return parts[0], parts[1], parts[2]


def deprecated(since: str, *, removed_in: str, alternative: str | None = None,
               name: str | None = None) -> Callable[[F], F]:
    """Decorador: marca uma função pública como descontinuada.

    Args:
        since: versão da API em que passou a descontinuada (``"1.2.0"``).
        removed_in: versão MAIOR em que pode ser removida (``"2.0.0"``); tem de ser maior que ``since``.
        alternative: o que usar em vez dela (texto curto, p.ex. ``"acdt.api.size"``).
        name: nome a registar (por omissão ``__qualname__`` da função).

    Returns:
        O decorador; a função decorada emite :class:`ACDTDeprecationWarning` a cada chamada.
    """
    s, r = _parse(since), _parse(removed_in)
    if r[0] <= s[0] or r[1:] != (0, 0):
        raise ValueError(f"removed_in {removed_in!r} tem de ser uma versão MAIOR X.0.0 acima de since {since!r}")

    def deco(fn: F) -> F:
        key = name or fn.__qualname__
        DEPRECATED[key] = {"since": since, "removed_in": removed_in, "alternative": alternative}
        msg = (f"acdt.api.{key} está descontinuada desde a API {since} e sai na {removed_in}"
               + (f"; use {alternative}" if alternative else ""))

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            warnings.warn(msg, ACDTDeprecationWarning, stacklevel=2)
            return fn(*args, **kwargs)

        wrapper.__deprecated__ = msg  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return deco
