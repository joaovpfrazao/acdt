# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Dimensão da frota a partir da disponibilidade e da fiabilidade de missão.

* **cobertura** (estações contínuas): reutiliza :func:`acdt.core.concept.fleet_feedback.fleet` (ciclo de Ha 2010,
  AFIT-OR-MS-ENS-10-03; frota esperada ⌈k/A⌉ e, com ``confidence``, k-de-N binomial, MIL-HDBK-338B §7.5.5.1) com a
  disponibilidade operacional calculada aqui;
* **surtidas** (taxa diária): balanço de tempo — horas de aeronave exigidas por dia = lançamentos × (duração da
  surtida + tempo de solo); cada aeronave dá A × H_op horas por dia; N = ⌈lançamentos (t_s + t_solo) / (A H_op)⌉.
  Lançamentos = surtidas / R_missão (PRESSUPOSTO conservador: uma surtida abortada ocupa o ciclo inteiro e é
  repetida); H_op = horas de operação por dia (omissão 24 — PRESSUPOSTO, declarar o turno real).

Intervalos: a frota mínima usa A_hi e R_hi; a máxima A_lo e R_lo; extremo desconhecido → ``None``.
"""
from __future__ import annotations

import math
from typing import Any, Mapping


def coverage(cfg: Mapping[str, Any], A: float) -> dict[str, Any]:
    from acdt.core.concept.fleet_feedback import fleet

    settings: dict[str, Any] = {"availability": float(A), "n_stations": int(cfg.get("n_stations", 1)),
                                "handoff_overlap_h": float(cfg.get("handoff_overlap_h", 0.0) or 0.0)}
    if cfg.get("confidence") is not None:
        settings["confidence"] = float(cfg["confidence"])
    r: dict[str, Any] = fleet(float(cfg["on_station_h"]), float(cfg["transit_h"]),  # type: ignore[no-untyped-call]
                              float(cfg["turnaround_h"]), settings)
    n = r.get("fleet_for_confidence") if "confidence" in settings else r.get("fleet_expected")
    return {"fleet": n, "aircraft_needed_in_cycle": r.get("aircraft_needed_in_cycle"),
            "feasible": bool(r["cycle"]["feasible"]), "detail": r}


def sorties(cfg: Mapping[str, Any], A: float, R_mission: float) -> dict[str, Any]:
    spd = float(cfg["sorties_per_day"])
    ts = float(cfg["sortie_duration_h"])
    tg = float(cfg["turnaround_h"])
    H = float(cfg.get("operating_hours_per_day", 24.0) or 24.0)
    if spd <= 0 or ts <= 0 or tg < 0 or not 0 < H <= 24:
        raise ValueError("surtidas: sorties_per_day > 0, sortie_duration_h > 0, turnaround_h ≥ 0, 0 < H_op ≤ 24")
    if R_mission <= 0 or A <= 0:
        return {"fleet": None, "feasible": False, "note": "R_missão ou A nulos: frota infinita"}
    launches = spd / R_mission if cfg.get("abort_reflight", True) else spd
    hours = launches * (ts + tg)
    n = math.ceil(hours / (A * H) - 1e-12)
    fh_day = launches * ts / n if n else None
    return {"fleet": n, "feasible": True, "launches_per_day": launches, "aircraft_hours_per_day": hours,
            "fh_per_aircraft_per_day": fh_day, "operating_hours_per_day": H}


def size(cfg: Mapping[str, Any], A: Mapping[str, float | None], R: Mapping[str, float | None]) -> dict[str, Any]:
    """Frota {lo, hi} para o modo declarado (``coverage`` | ``sorties``)."""
    mode = str(cfg.get("mode", "coverage" if "n_stations" in cfg or "on_station_h" in cfg else "sorties"))
    out: dict[str, Any] = {"mode": mode, "fleet": {"lo": None, "hi": None}, "cases": {}}
    for bound, a_key, r_key in (("lo", "hi", "hi"), ("hi", "lo", "lo")):
        a = A.get(a_key)
        r = R.get(r_key)
        if a is None or (mode == "sorties" and r is None):
            out["cases"][bound] = {"fleet": None, "note": "disponibilidade ou fiabilidade de missão desconhecida"}
            continue
        c = coverage(cfg, a) if mode == "coverage" else sorties(cfg, a, float(r or 0.0))
        c.update({"A": a, "R_mission": r})
        out["cases"][bound] = c
        out["fleet"][bound] = c.get("fleet")
    if mode == "coverage":
        out["method"] = ("Ha 2010 (AFIT-OR-MS-ENS-10-03) via acdt.core.concept.fleet_feedback.fleet; A operacional "
                         "MIL-HDBK-338B Eq. 10.22")
    elif mode == "sorties":
        out["method"] = ("balanço de tempo: N = ⌈lançamentos (t_s + t_solo)/(A H_op)⌉, lançamentos = surtidas/R_missão "
                         "(PRESSUPOSTO: surtida abortada repetida); A MIL-HDBK-338B Eq. 10.22")
    else:
        raise ValueError("fleet.mode: coverage | sorties")
    return out
