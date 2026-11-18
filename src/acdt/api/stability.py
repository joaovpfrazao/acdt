# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Estabilidade da API pública: assinatura de cada nome de ``acdt.api.__all__`` comparada com ``api_surface.json``.

Regras (versionamento semântico, docs/API.md §2):

* nome removido ou assinatura alterada → exige subir a versão MAIOR;
* nome acrescentado (sem mexer nos existentes) → exige subir pelo menos a MENOR;
* superfície igual → qualquer versão serve (CORREÇÃO à vontade).

Regenerar o ficheiro depois de subir ``API_VERSION``::

    python -m acdt.api.stability --write
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any, Mapping

SNAPSHOT = Path(__file__).with_name("api_surface.json")


def describe(obj: Any) -> str:
    """Descrição estável de um objeto público: assinatura de funções, base de classes, tipo de constantes."""
    if inspect.isclass(obj):
        return "class(" + ", ".join(b.__name__ for b in obj.__bases__) + ")"
    if callable(obj):
        try:
            return "def" + str(inspect.signature(obj))
        except (TypeError, ValueError):  # pragma: no cover - builtins sem assinatura
            return "callable"
    if isinstance(obj, (str, int, float, bool)):
        return f"const:{type(obj).__name__}"
    return f"value:{type(obj).__name__}"


def surface() -> dict[str, str]:
    """``{nome: descrição}`` da superfície pública atual (``acdt.api.__all__``)."""
    import acdt.api as api

    return {n: describe(getattr(api, n)) for n in sorted(api.__all__)}


def _ver(v: str) -> tuple[int, int, int]:
    a, b, c = (int(x) for x in v.split("."))
    return a, b, c


def check(snapshot: Mapping[str, Any], current: Mapping[str, str], version: str) -> list[str]:
    """Problemas de versionamento entre o ficheiro fixado e a superfície atual (lista vazia = conforme)."""
    old: Mapping[str, str] = snapshot.get("surface") or {}
    v0, v1 = _ver(str(snapshot.get("api_version", "0.0.0"))), _ver(version)
    removed = sorted(set(old) - set(current))
    changed = sorted(n for n in set(old) & set(current) if old[n] != current[n])
    added = sorted(set(current) - set(old))
    probs: list[str] = []
    if v1 < v0:
        probs.append(f"API_VERSION {version} é menor que a fixada {snapshot.get('api_version')}")
    if (removed or changed) and v1[0] <= v0[0]:
        probs.append("mudança incompatível sem subir a versão MAIOR — removidos: "
                     f"{removed or '-'}; alterados: " + ("; ".join(f"{n}: {old[n]} → {current[n]}" for n in changed)
                                                         or "-"))
    if added and not (removed or changed) and v1[:2] <= v0[:2]:
        probs.append(f"nomes acrescentados {added} sem subir a versão MENOR (API {version})")
    return probs


def load_snapshot() -> dict[str, Any]:
    """Conteúdo de ``api_surface.json``."""
    data: dict[str, Any] = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return data


def write_snapshot() -> Path:
    """Fixa a superfície atual com a ``API_VERSION`` atual (recusa se as regras falharem)."""
    import acdt.api as api

    if SNAPSHOT.is_file():
        probs = check(load_snapshot(), surface(), api.API_VERSION)
        if probs:
            raise SystemExit("api_surface.json não atualizado:\n  " + "\n  ".join(probs))
    SNAPSHOT.write_text(json.dumps({"schema": "acdt.api_surface/1", "api_version": api.API_VERSION,
                                    "surface": surface()}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return SNAPSHOT


def main(argv: list[str] | None = None) -> int:
    import acdt.api as api

    args = sys.argv[1:] if argv is None else argv
    if "--write" in args:
        print(f"escrito {write_snapshot()}")
        return 0
    probs = check(load_snapshot(), surface(), api.API_VERSION)
    for p in probs:
        print(p)
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
