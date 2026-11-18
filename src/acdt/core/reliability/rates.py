# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Taxa de avaria de um componente com proveniência (reutiliza :mod:`acdt.core.safety.rates`).

Ordem de resolução (a primeira presente decide):

1. ``supplier``: ``{lambda_per_h | mtbf_h, source, retrieved}`` — :func:`acdt.core.safety.rates.supplier_rate`; sem
   fonte ou data → desconhecido (nunca um número sem origem);
2. ``rate_key``: entrada de ``core/data/failure_rates.yaml`` (``published`` ou ``vendor_claim``). Entradas
   ``kind: assumption`` (PRESSUPOSTO da base) só entram com ``accept_assumptions: true``; senão desconhecido;
3. ``lambda_per_h`` ou ``mtbf_h`` (número ou ``{lo, hi}``) com ``source`` (texto não vazio); sem fonte → desconhecido;
4. nada → desconhecido.

A taxa efetiva por hora de voo é λ × ``duty`` (horas de funcionamento por hora de voo; omissão 1 — PRESSUPOSTO: o
componente funciona durante todo o voo) × ``n`` (unidades idênticas em série).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class Rate:
    """λ por hora de funcionamento como intervalo; ``lo``/``hi`` ``None`` = desconhecido."""

    lo: float | None
    hi: float | None
    kind: str                     # supplier | published | vendor_claim | user | assumption | desconhecido
    source: str | None
    notes: list[str] = field(default_factory=list)

    @property
    def known(self) -> bool:
        return self.lo is not None and self.hi is not None


def _num(x: Any) -> float | None:
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v


def _interval(raw: Any, invert: bool = False) -> tuple[float | None, float | None]:
    """Número ou ``{lo, hi}`` → (lo, hi) de λ; ``invert`` para MTBF (λ = 1/MTBF, troca os extremos)."""
    if isinstance(raw, Mapping):
        a, b = _num(raw.get("lo")), _num(raw.get("hi"))
    else:
        a = b = _num(raw)
    if a is None or b is None:
        return None, None
    if a > b:
        raise ValueError(f"intervalo invertido: lo {a} > hi {b}")
    if a < 0:
        raise ValueError("taxa/MTBF negativos")
    if invert:
        if a <= 0:
            raise ValueError("MTBF tem de ser > 0")
        return 1.0 / b, 1.0 / a
    return a, b


def resolve(comp: Mapping[str, Any], *, accept_assumptions: bool = False) -> Rate:
    """λ (por hora de funcionamento) de um componente declarado; ver o docstring do módulo."""
    from acdt.core.safety.rates import rate as db_rate
    from acdt.core.safety.rates import supplier_rate

    cid = str(comp.get("id", "?"))
    if comp.get("supplier") is not None:
        e = supplier_rate(cid, comp.get("supplier"))
        if e.get("status") == "ok" and e.get("lambda_per_h") is not None:
            lam = float(e["lambda_per_h"])
            return Rate(lam, lam, "supplier", f"{e['source']} (consultado {e['retrieved']})")
        return Rate(None, None, "desconhecido", None,
                    [f"taxa de fornecedor incompleta ({', '.join(e.get('unassessed_terms') or [])}): não aplicada"])
    if comp.get("rate_key"):
        key = str(comp["rate_key"])
        try:
            e = db_rate(key)
        except KeyError as ex:
            return Rate(None, None, "desconhecido", None, [str(ex)])
        kind = str(e.get("kind", "?"))
        src = f"{e.get('source', '')} {e.get('url', '')}".strip()
        lam_db = _num(e.get("lambda_per_h"))
        if lam_db is None:
            return Rate(None, None, "desconhecido", src, [f"failure_rates.yaml[{key}] sem lambda_per_h"])
        if kind == "assumption" and not accept_assumptions:
            return Rate(None, None, "desconhecido", src,
                        [f"failure_rates.yaml[{key}] é PRESSUPOSTO (kind: assumption): não aplicado sem "
                         "accept_assumptions: true — declare dados do fornecedor"])
        notes = [f"failure_rates.yaml[{key}] kind={kind}"]
        if kind == "vendor_claim":
            notes.append("declaração do fabricante, não verificada independentemente")
        if kind == "assumption":
            notes.append("PRESSUPOSTO aceite por accept_assumptions: true")
        return Rate(lam_db, lam_db, kind, src, notes)
    if comp.get("lambda_per_h") is not None or comp.get("mtbf_h") is not None:
        src = str(comp.get("source") or "").strip()
        if not src:
            return Rate(None, None, "desconhecido", None,
                        ["λ/MTBF declarado sem 'source': não aplicado (taxas só de fornecedor ou fonte pública)"])
        if comp.get("lambda_per_h") is not None:
            lo, hi = _interval(comp["lambda_per_h"])
        else:
            lo, hi = _interval(comp["mtbf_h"], invert=True)
        if lo is None:
            return Rate(None, None, "desconhecido", src, ["λ/MTBF ilegível"])
        return Rate(lo, hi, str(comp.get("kind") or "user"), src)
    return Rate(None, None, "desconhecido", None, ["sem taxa de avaria declarada"])


def effective(comp: Mapping[str, Any], r: Rate) -> tuple[float | None, float | None]:
    """λ efetivo por hora de voo de um bloco (λ × duty × n); ``None`` se desconhecido."""
    duty = _num(comp.get("duty"))
    duty = 1.0 if duty is None else duty
    n = int(comp.get("n", 1) or 1)
    if duty < 0 or n < 1:
        raise ValueError(f"componente {comp.get('id')!r}: duty ≥ 0 e n ≥ 1")
    if not r.known:
        return None, None
    return float(r.lo or 0.0) * duty * n, float(r.hi or 0.0) * duty * n
