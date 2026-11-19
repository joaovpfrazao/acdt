# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina «fiabilidade» (L0) do domínio aircraft (docs/FIABILIDADE.md).

Etapa do pipeline depois do gelo. Constrói a especificação genérica (:mod:`acdt.core.reliability.study`) a partir de
``assumptions.reliability`` e do que o dimensionamento já calculou:

* **duração da missão**: ``reliability.mission_duration_h``; senão a soma dos segmentos da missão exigida
  (``performance.mission_required``); senão o requisito ``endurance``; senão desconhecida;
* **componentes, RBD, tarefas, logística, frota, sobressalentes, custo operacional**: declarados pelo utilizador
  (sem componentes declarados a disciplina fica «não avaliada» — nunca uma fiabilidade inventada);
* **frota por surtidas**: sem ``sortie_duration_h`` usa a duração da missão.

Não há acoplamento ao dimensionamento (a fiabilidade não muda W0 neste nível); o acoplamento é com a frota
(:func:`acdt.core.concept.fleet_feedback.fleet`) e com o custo operacional (manufacturing.costing).
"""
from __future__ import annotations

import copy
from typing import Any

from acdt.core.reliability.study import analyse

LEVEL = "L0"
DEFAULTS: dict[str, Any] = {
    "enabled": True, "components": None, "rbd": None, "mission_duration_h": None, "accept_assumptions": False,
    "preventive": None, "logistics": None, "utilization": None, "fleet": None, "spares": None,
    "operating_cost": None, "labour_rate_per_h": None,
}


def _opts(spec: Any) -> dict[str, Any]:
    o = copy.deepcopy(DEFAULTS)
    user = (spec.assumptions.get("reliability") or {}) if isinstance(spec.assumptions, dict) else {}
    o.update(user)
    return o


def _not_evaluated(reason: str) -> dict[str, Any]:
    return {"evaluated": False, "level": LEVEL, "reason": reason, "mission_reliability": {"lo": None, "hi": None},
            "operational_availability": {"lo": None, "hi": None}}


def mission_duration_h(res: Any, o: dict[str, Any]) -> tuple[float | None, str]:
    if o.get("mission_duration_h") is not None:
        return float(o["mission_duration_h"]), "reliability.mission_duration_h"
    from .thermal import _f, _segments
    segs = list(_segments(res))
    if segs:
        t = [(_f(s.get("t [min]")) or 0.0) for s in segs]
        if sum(t) > 0:
            return sum(t) / 60.0, "performance.mission_required (soma dos segmentos)"
    try:
        e = res.spec.requirements.value("endurance")
    except Exception:  # noqa: BLE001
        e = None
    if e:
        return float(e) / 3600.0, "requisito endurance (PRESSUPOSTO: missão = autonomia)"
    return None, "desconhecida"


def build_spec(res: Any, o: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    t, src = mission_duration_h(res, o)
    notes.append(f"duração da missão: {'?' if t is None else f'{t:.3g} h'} ({src})")
    spec: dict[str, Any] = {k: copy.deepcopy(o.get(k)) for k in ("components", "rbd", "accept_assumptions",
                                                                 "preventive", "logistics", "utilization", "fleet",
                                                                 "spares", "operating_cost", "labour_rate_per_h",
                                                                 "standby", "weibull")
                            if o.get(k) is not None}
    spec["schema"] = "acdt.reliability/1"
    spec["mission_duration_h"] = t
    fl = spec.get("fleet")
    if isinstance(fl, dict) and fl.get("mode", "sorties") == "sorties" and "sorties_per_day" in fl \
            and fl.get("sortie_duration_h") is None:
        if t is None:
            raise ValueError("fleet.sortie_duration_h em falta e duração da missão desconhecida")
        fl["sortie_duration_h"] = t
        notes.append("fleet.sortie_duration_h = duração da missão")
    return spec, notes


def analyse_reliability(res: Any) -> dict[str, Any]:
    o = _opts(res.spec)
    spec, notes = build_spec(res, o)
    out = analyse(spec)
    out.update({"level": LEVEL, "adapter_notes": notes})
    return out


def reliability_stage(res: Any) -> None:
    from acdt.core.requirements import Issue

    o = _opts(res.spec)
    if not o.get("enabled", True):
        res.reliability = _not_evaluated("reliability.enabled: false")
        return
    if not o.get("components"):
        res.reliability = _not_evaluated("sem componentes declarados (assumptions.reliability.components): "
                                         "fiabilidade desconhecida")
        return
    try:
        res.reliability = analyse_reliability(res)
    except Exception as ex:  # noqa: BLE001 — a etapa nunca parte o pipeline; fica desconhecido
        res.reliability = _not_evaluated(f"falhou: {type(ex).__name__}: {ex}")
        res.issues.append(Issue("warning", f"fiabilidade não avaliada: {type(ex).__name__}: {ex}"))
