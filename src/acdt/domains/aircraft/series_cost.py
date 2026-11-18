# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina «custo_serie» (L0) do domínio aircraft (docs/CUSTO_SERIE.md).

Etapa do pipeline depois da fiabilidade. Só corre quando a missão a pede (``assumptions.series_cost`` declarado ou
um requisito ``unit_cost_at_quantity`` / ``flyaway_cost`` / ``break_even_quantity``); senão fica «não avaliada».

* ``method: eastlake`` (por omissão): as entradas do Eastlake modificado são as do custo unitário do
  dimensionamento (:func:`acdt.domains.aircraft.sizing.eastlake_inputs`: massa da estrutura = fração × We,
  V_H = ``max_speed`` ou cruzeiro, motor, compósito, atuadores) — só N varia;
* ``method: dapca4``: We e V do dimensionamento; ``series_cost.dapca`` dá o resto (cpi, taxas, FTA, motor…);
* ``method: learning``: rota de baixo para cima com ``series_cost.learning: {T1, slope, theory, nre, lots}``.

Requisitos com qualificador ``quantity`` são avaliados nessa quantidade. Não muda W0 (sem acoplamento ao
dimensionamento); alimenta o ciclo de vida (custo de aquisição, RDT&E).
"""
from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any

from .manufacturing.series import analyse, cer_point

LEVEL = "L0"
REQ_KEYS = ("unit_cost_at_quantity", "flyaway_cost", "break_even_quantity")
DEFAULTS: dict[str, Any] = {
    "enabled": True, "method": "eastlake", "quantity": None, "quantities": [1, 5, 10, 25, 50, 100, 250, 500, 1000],
    "price": None, "prices": None, "n_max": 10000, "dapca": None, "learning": None,
}


def _opts(spec: Any) -> tuple[dict[str, Any], bool]:
    o = copy.deepcopy(DEFAULTS)
    user = spec.assumptions.get("series_cost") if isinstance(spec.assumptions, dict) else None
    if isinstance(user, dict):
        o.update(user)
    return o, isinstance(user, dict)


def _not_evaluated(reason: str) -> dict[str, Any]:
    return {"evaluated": False, "level": LEVEL, "reason": reason, "average_unit_cost_USD": None,
            "flyaway_cost_USD": None, "break_even_quantity": None}


def _requested(spec: Any) -> list[Any]:
    try:
        return [r for r in spec.requirements if r.key in REQ_KEYS]
    except TypeError:
        return []


def build_spec(res: Any, o: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    from .sizing import eastlake_inputs

    notes: list[str] = []
    sz = res.sizing
    method = str(o.get("method") or "eastlake")
    N = o.get("quantity")
    if N is None:
        N = int((res.spec.assumptions.get("cost") or {}).get("N", 500))
        notes.append(f"quantidade N = {N} (assumptions.cost.N ou 500, omissão de Gudmundsson para 5 anos)")
    spec: dict[str, Any] = {"method": method, "quantity": int(N), "quantities": list(o.get("quantities") or []),
                            "price": o.get("price"), "prices": o.get("prices"), "n_max": o.get("n_max", 10000)}
    for r in _requested(res.spec):
        q = r.params.get("quantity")
        if q:
            spec["quantities"].append(int(q))
    if method == "eastlake":
        ei = eastlake_inputs(res.spec, sz.We, res.power_sl, res.cruise_speed)
        spec["inputs"] = {k: v for k, v in asdict(ei).items() if k != "N"}
        notes.append(f"Eastlake: W_estrutura {ei.W_airframe_kg:.1f} kg, V_H {ei.V_H_kt:.1f} kt (as do custo unitário)")
        if str(getattr(res.spec, "aircraft_class", "")).startswith("uav"):
            notes.append("validade: a base do Eastlake é aviação geral (Part 23/CS-23; Gudmundsson 2014 Cap. 2) — num "
                         "UAS é extrapolação; prefira method: learning com T1 do plano de fabrico")
    elif method == "dapca4":
        vmax = res.spec.requirements.value("max_speed") or res.cruise_speed
        d = dict(o.get("dapca") or {})
        d.setdefault("We_kg", float(sz.We))
        d.setdefault("V_kt", float(vmax) / 0.514444)
        spec["inputs"] = d
        notes.append(f"DAPCA IV: We {d['We_kg']:.1f} kg, V {d['V_kt']:.1f} kt")
    elif method == "learning":
        spec["learning"] = dict(o.get("learning") or {})
    else:
        raise ValueError(f"series_cost.method {method!r} desconhecido (eastlake, dapca4, learning)")
    return spec, notes


def _at(spec: dict[str, Any], q: int) -> dict[str, Any]:
    from .manufacturing.series import learning_program

    if spec["method"] in ("eastlake", "dapca4"):
        return cer_point(spec["method"], spec["inputs"], q)
    lc = spec["learning"]
    return learning_program(float(lc["T1"]), float(lc.get("slope", 0.85)), str(lc.get("theory", "crawford")), q,
                            nre=float(lc.get("nre", 0.0)), per_aircraft_items=float(lc.get("per_aircraft_items", 0.0)))


def analyse_series_cost(res: Any) -> dict[str, Any]:
    o, _ = _opts(res.spec)
    spec, notes = build_spec(res, o)
    out = analyse(spec)
    nre_unknown = out.get("nre_declared") is False
    # valores nos qualificadores de quantidade dos requisitos
    for r in _requested(res.spec):
        q = r.params.get("quantity")
        if r.key == "break_even_quantity" or not q:
            continue
        p = _at(spec, int(q))
        key = "average_unit_cost_USD" if r.key == "unit_cost_at_quantity" else "flyaway_unit_cost_USD"
        out.setdefault("at_requirement", {})[r.key] = {"quantity": int(q), "value_USD": p[key]}
    ar = out.get("at_requirement") or {}
    out["unit_cost_at_quantity_USD"] = (ar.get("unit_cost_at_quantity") or {}).get("value_USD",
                                                                                   out.get("average_unit_cost_USD"))
    out["flyaway_cost_USD"] = (ar.get("flyaway_cost") or {}).get("value_USD", out.get("flyaway_cost_USD"))
    if nre_unknown:  # custo médio só é limite inferior: num requisito max nunca passa
        out["unit_cost_at_quantity_USD"] = {"lo": out["unit_cost_at_quantity_USD"], "hi": None}
        out["average_unit_cost_USD"] = {"lo": out.get("average_unit_cost_USD"), "hi": None}
    out.update({"level": LEVEL, "adapter_notes": notes,
                "currency": "USD (CER: 2012 × cpi; learning: T1 e NRE declarados em USD)"})
    return out


def series_cost_stage(res: Any) -> None:
    from acdt.core.requirements import Issue

    o, declared = _opts(res.spec)
    if not o.get("enabled", True):
        res.series_cost = _not_evaluated("series_cost.enabled: false")
        return
    if not declared and not _requested(res.spec):
        res.series_cost = _not_evaluated("sem assumptions.series_cost nem requisitos de custo de série")
        return
    if res.sizing is None or not res.sizing.converged:
        res.series_cost = _not_evaluated("dimensionamento não convergiu")
        return
    try:
        res.series_cost = analyse_series_cost(res)
    except Exception as ex:  # noqa: BLE001 — a etapa nunca parte o pipeline; fica desconhecido
        res.series_cost = _not_evaluated(f"falhou: {type(ex).__name__}: {ex}")
        res.issues.append(Issue("warning", f"custo de série não avaliado: {type(ex).__name__}: {ex}"))
