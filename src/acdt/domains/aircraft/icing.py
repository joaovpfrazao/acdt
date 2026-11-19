# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina «gelo» (L0/L1) do domínio aircraft (docs/GELO.md).

Etapa do pipeline depois da térmica. Constrói uma especificação genérica (:mod:`acdt.core.icing.study`) a partir do
que o dimensionamento já calculou:

* **condições**: os segmentos da missão exigida (altitude, velocidade, duração) quando o desempenho correu ou, no
  ciclo ``iterar``, quando a missão exigida acaba de ser calculada; senão subida e cruzeiro do ponto de projeto
  (como na térmica). Só entram no varrimento os pontos dentro do envelope
  altitude–temperatura do Apêndice C;
* **superfícies**: ``icing.surfaces`` do utilizador; sem isso asa (corda média aerodinâmica, t/c médio), estabilizador
  horizontal e vertical da configuração, **sem proteção** (d = 2 r_le, r_le = 1,1019 t² c — PRESSUPOSTO perfil NACA
  de 4 dígitos);
* proteção por superfície (``protection``: none | anti_ice_thermal | deice_electrothermal | boots) com área
  (``protected_area_m2`` ou ``protected_chord_fraction`` → A = 2·fração·S, extradorso + intradorso, PRESSUPOSTO),
  ``surface_temperature_C``, ``duty_cycle``, ``power_density_W_m2``, ``mass_kg``.

**Acoplamento** (``icing.coupling``): ``relatorio`` (omissão) — só relata; ``iterar`` — ponto fixo com o
dimensionamento: potência elétrica de proteção (majorante) × ciclo (fração da missão em segmentos dentro do envelope,
``power_schedule: exposicao``; 1 com ``missao`` ou sem durações) em ``propulsion.systems_power_W`` e como carga de
``systems.loads`` (só aeronaves elétricas) e massa declarada dos sistemas em ``weights.fixed_mass_kg``. Desconhecidos não são acoplados (listados).
"""
from __future__ import annotations

import copy
import math
from typing import Any

from acdt.core.icing.study import analyse

from .thermal import _f, _h_range, _segments, ensure_required_mission, operating_points, with_load

LEVEL = "L0"
DEFAULTS: dict[str, Any] = {
    "enabled": True, "coupling": "relatorio", "max_iter": 6, "tol": 0.01,
    "envelopes": ["continuous", "intermittent"], "mvd_um": None, "conditions": None, "surfaces": None,
    "temperature": "envelope",   # envelope (varre o Ap. C) | isa (só a temperatura ISA+dT de cada segmento)
    "isa_dT_K": 0.0, "fiki": None, "max_altitude_m": None,
    # exposicao: potência de proteção só na fração da missão em segmentos dentro do envelope (majorante da exposição);
    # missao: toda a missão (majorante conservador). Sem durações conhecidas → missao.
    "power_schedule": "exposicao",
}


def _opts(spec: Any) -> dict[str, Any]:
    o = copy.deepcopy(DEFAULTS)
    user = (spec.assumptions.get("icing") or {}) if isinstance(spec.assumptions, dict) else {}
    o.update(user)
    return o


def _not_evaluated(reason: str) -> dict[str, Any]:
    return {"evaluated": False, "level": LEVEL, "reason": reason, "max_thickness_mm": None, "exposure_s": None,
            "protection": None}


def build_conditions(res: Any, o: dict[str, Any]) -> list[dict[str, Any]]:
    conds: list[dict[str, Any]] = []
    for s in _segments(res):
        name = str(s.get("segmento", ""))
        t = (_f(s.get("t [min]")) or 0.0) * 60.0
        V = _f(s.get("V [m/s]")) or 0.0
        if t <= 0 or V <= 0:
            continue
        h0, h1 = _h_range(s.get("h [m]", "0"))
        c: dict[str, Any] = {"name": name, "altitude_m": max(h0, h1) if name.startswith("subida") else h1,
                             "V_m_s": V, "duration_s": t, "source": "performance.mission_required (segmento)"}
        conds.append(c)
    if not conds:
        for key, op in operating_points(res).items():
            V = float(op.get("V_m_s") or 0.0)
            if V <= 0:
                continue
            conds.append({"name": key, "altitude_m": float(op.get("altitude_m") or 0.0), "V_m_s": V,
                          "duration_s": op.get("duration_s"), "source": op.get("source")})
    if o.get("temperature") == "isa":
        from acdt.core.atmosphere import isa
        for c in conds:
            c["T_C"] = isa(float(c["altitude_m"]), float(o.get("isa_dT_K") or 0.0)).T - 273.15
    names: dict[str, int] = {}
    for c in conds:  # nomes únicos
        n = names.get(c["name"], 0)
        names[c["name"]] = n + 1
        if n:
            c["name"] = f"{c['name']}_{n + 1}"
    return conds


def default_surfaces(res: Any) -> list[dict[str, Any]]:
    cfg = getattr(res, "config", None)
    if cfg is None:
        raise ValueError("sem configuração geométrica: declare icing.surfaces")
    w = cfg.wing
    out = [{"id": "asa", "chord_m": w.mac, "t_c": w.tc_mean, "lifting": True, "critical": True,
            "protection": "none", "S_m2": w.S}]
    for sid, t in (("estabilizador_horizontal", cfg.htail), ("estabilizador_vertical", cfg.vtail)):
        tw = t.as_wing()
        out.append({"id": sid, "chord_m": tw.mac, "t_c": t.tc, "lifting": sid.endswith("horizontal"),
                    "critical": True, "protection": "none", "S_m2": t.S})
    return out


def build_spec(res: Any, o: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    conds = o.get("conditions") or build_conditions(res, o)
    surfs = copy.deepcopy(o.get("surfaces")) or default_surfaces(res)
    if not o.get("surfaces"):
        notes.append("superfícies por omissão (asa, estabilizadores) sem proteção; d = 2 r_le com r_le = 1,1019 t² c "
                     "(PRESSUPOSTO perfil NACA de 4 dígitos)")
    S_ref = float(getattr(res, "S", 0.0) or 0.0)
    for s in surfs:
        if s.get("protected_area_m2") is None and s.get("protected_chord_fraction") is not None:
            S = float(s.get("S_m2") or S_ref)
            s["protected_area_m2"] = 2.0 * float(s["protected_chord_fraction"]) * S
            notes.append(f"{s['id']}: área protegida = 2 × {s['protected_chord_fraction']} × S = "
                         f"{s['protected_area_m2']:.3f} m² (PRESSUPOSTO extradorso + intradorso, corda constante)")
        if s.get("chord_m") is None and s.get("d_m") is None and s.get("le_radius_m") is None:
            raise ValueError(f"superfície {s.get('id')!r} sem geometria (chord_m + t_c, le_radius_m ou d_m)")
    spec = {"schema": "acdt.icing/1", "envelopes": o.get("envelopes"), "mvd_um": o.get("mvd_um"),
            "conditions": conds, "surfaces": surfs, "fiki": o.get("fiki")}
    return spec, notes


def analyse_icing(res: Any) -> dict[str, Any]:
    o = _opts(res.spec)
    spec, notes = build_spec(res, o)
    out = analyse(spec)
    out.update({"level": LEVEL, "adapter_notes": notes, "coupling_mode": o["coupling"],
                "inputs": {k: o[k] for k in ("envelopes", "temperature", "isa_dT_K", "fiki")}})
    out["coupling_effect"] = coupling_effect(res, out, spec)
    return out


def _mass(spec: dict[str, Any]) -> tuple[float | None, list[str]]:
    miss: list[str] = []
    tot = 0.0
    for s in spec["surfaces"]:
        if s.get("protection", "none") in ("none",):
            continue
        m = _f(s.get("mass_kg"))
        if m is None:
            miss.append(str(s["id"]))
        else:
            tot += m
    return (None if miss else tot), miss


def coupling_effect(res: Any, out: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    p = (out.get("protection") or {}).get("electrical_power_W") or {}
    m, miss = _mass(spec)
    eff: dict[str, Any] = {"applied": out.get("coupling_mode") == "iterar", "electrical_power_W": p,
                           "mass_kg": m, "mass_unknown_for": miss}
    hp = float(res.spec.assumptions["propulsion"].get("systems_power_W", 0.0) or 0.0)
    eff["power_fraction_of_systems"] = None if not hp or p.get("hi") is None else p["hi"] / hp
    eff["mass_fraction_of_W0"] = None if m is None else m / res.sizing.W0
    return eff


def exposure_duty(out: dict[str, Any], schedule: str = "exposicao") -> tuple[float, str]:
    """Fração da missão em que a proteção corre (ciclo da carga no balanço elétrico).

    ``exposicao``: Σ duração dos segmentos com algum caso dentro do envelope do Ap. C (``exposure_s.hi``, majorante da
    exposição) / Σ duração de todos os segmentos analisados. Se alguma duração for desconhecida, ou com
    ``missao``, devolve 1 (toda a missão, majorante conservador)."""
    if schedule == "missao":
        return 1.0, "toda a missão (icing.power_schedule: missao)"
    conds = out.get("conditions") or {}
    durs = [_f(c.get("duration_s")) for c in conds.values()]
    exp = _f((out.get("exposure_s") or {}).get("hi"))
    if not durs or any(d is None for d in durs) or exp is None:
        return 1.0, "toda a missão (durações dos segmentos desconhecidas — majorante conservador)"
    tot = sum(float(d or 0.0) for d in durs)
    if tot <= 0:
        return 1.0, "toda a missão (duração total nula — majorante conservador)"
    frac = min(1.0, max(0.0, exp / tot))
    return frac, (f"fração da missão em segmentos dentro do envelope = {exp:.0f} s / {tot:.0f} s = {frac:.3f} "
                  "(majorante da exposição; potência de pico inalterada)")


def coupling_increments(out: dict[str, Any], spec: dict[str, Any], kind: str,
                        schedule: str = "exposicao") -> dict[str, Any]:
    inc: dict[str, Any] = {"power_W": None, "mass_kg": None, "not_coupled": []}
    inc["duty"], inc["duty_note"] = exposure_duty(out, schedule)
    p = ((out.get("protection") or {}).get("electrical_power_W") or {}).get("hi")
    if p is None:
        inc["not_coupled"].append("potência elétrica de proteção desconhecida (majorante)")
    elif kind == "electric":
        inc["power_W"] = float(p)
    elif p:
        inc["not_coupled"].append("potência elétrica de proteção em motor térmico: declare-a como carga onboard")
    m, miss = _mass(spec)
    if m is None:
        inc["not_coupled"].append(f"massa de proteção não declarada: {miss}")
    else:
        inc["mass_kg"] = m
    return inc


def size_with_icing(spec: Any, run_fn: Any) -> tuple[Any, Any, dict[str, Any]]:
    """Modo ``iterar``: ponto fixo dimensionamento ↔ gelo. ``run_fn(spec) -> (res, systems)``."""
    o = _opts(spec)
    base_mass = float(spec.assumptions["weights"].get("fixed_mass_kg", 0.0) or 0.0)
    base_P = float(spec.assumptions["propulsion"].get("systems_power_W", 0.0) or 0.0)
    hist: list[dict[str, Any]] = []
    cur = {"power_W": 0.0, "mass_kg": 0.0}
    sp = spec
    res = sysr = None
    converged = False
    mission: dict[str, Any] = {"used": False, "source": "ciclo não arrancou"}
    for it in range(int(o["max_iter"])):
        res, sysr = run_fn(sp)
        mission = ensure_required_mission(res)
        ic_spec, _n = build_spec(res, o)
        out = analyse(ic_spec)
        inc = coupling_increments(out, ic_spec, spec.propulsion_kind, str(o.get("power_schedule") or "exposicao"))
        new = {k: float(inc[k] or 0.0) for k in ("power_W", "mass_kg")}
        duty = float(inc["duty"])
        hist.append({"iter": it, "W0_kg": res.sizing.W0, **new, "duty": duty, "duty_note": inc["duty_note"],
                     "not_coupled": inc["not_coupled"], "mission": mission})
        dif = max(abs(new[k] - cur[k]) / max(abs(new[k]), abs(cur[k]), 1e-9) for k in new) if any(
            new[k] or cur[k] for k in new) else 0.0
        if it > 0 and dif < float(o["tol"]):
            converged = True
            break
        if it == 0 and not any(new.values()):
            converged = True
            break
        cur = new
        sp = copy.copy(spec)
        sp.assumptions = copy.deepcopy(spec.assumptions)
        sp.assumptions["weights"]["fixed_mass_kg"] = base_mass + new["mass_kg"]
        if spec.propulsion_kind == "electric":
            # energia: potência × ciclo (fração da missão em gelo); com power budget em malha fechada
            # (systems_integration.run_with_systems) systems_power_W é substituído pela média do balanço, por isso a
            # proteção entra também como carga do balanço (potência média × ciclo; pico = potência total)
            sp.assumptions["propulsion"]["systems_power_W"] = base_P + new["power_W"] * duty
            if new["power_W"] and getattr(spec, "systems", None):
                sp.systems = with_load(spec.systems, ICE_LOAD_NAME, new["power_W"], duty, peak_w=new["power_W"])
    return res, sysr, {"converged": converged, "history": hist, "method": "ponto fixo dimensionamento ↔ gelo",
                       "mission": mission,
                       "operating_point": "tabela de segmentos da missão exigida, quando a missão fecha; senão o "
                                          "ponto de projeto (a falta fica em mission.source)",
                       "electrical_load": "propulsion.systems_power_W (+ P × ciclo) e systems.loads (ciclo = fração da "
                                          "missão em gelo, ou 1 sem durações; pico = P)"}


ICE_LOAD_NAME = "proteção contra o gelo (acdt.icing)"


def icing_stage(res: Any) -> None:
    from acdt.core.requirements import Issue

    o = _opts(res.spec)
    if not o.get("enabled", True):
        res.icing = _not_evaluated("icing.enabled: false")
        return
    try:
        out = analyse_icing(res)
    except Exception as ex:  # noqa: BLE001 — a etapa de gelo nunca parte o pipeline; fica desconhecido
        res.icing = _not_evaluated(f"falhou: {type(ex).__name__}: {ex}")
        res.issues.append(Issue("warning", f"gelo não avaliado: {type(ex).__name__}: {ex}"))
        return
    loop = getattr(res, "icing_coupling", None)
    if loop is not None:
        out["coupling_loop"] = loop
    res.icing = out


_ = math
