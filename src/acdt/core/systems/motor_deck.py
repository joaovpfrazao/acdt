# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""First-order DC / BLDC motor deck (Drela 2007) — opt-in, no invented maps.

Source
------
Drela, M., "First-Order DC Electric Motor Model", MIT, 2007. Already cited in
``electric_propulsion.py``. SI identities: Kt = 1/Kv_SI, E = omega/Kv_SI, I = (V-E)/R, Q = Kt (I - I0),
P_shaft = Q*omega, eta = P_shaft/(V I).

``Kv`` is taken in the UAV-usual rpm/V (converted to rad/s/V). ``R`` and
``I0`` plus a source are required; a numeric-only record is not applied
(unassessed ≠ η=0.85, never a silent zero). Optional ``I_max`` / ``V_max``
flag out-of-domain use — values are not clipped to look feasible.

An optional sourced η(P) table is forwarded to :mod:`acdt.core.motor_map`
(already the hybrid path). This module does not invent efficiency islands
or vendor maps. Constant-efficiency ``eta_motor`` / ``load_ratio`` in the
systems cycle stay the default when no deck is given.
"""
from __future__ import annotations

import math
from typing import Any

SOURCE = ("Drela, M., 'First-Order DC Electric Motor Model', MIT, 2007 — "
          "https://web.mit.edu/drela/Public/web/qprop/motor1_theory.pdf")

_REQUIRED = ("kv_rpm_per_V", "R_ohm", "I0_A", "source")


def _num(name: str, v, lo=None, hi=None):
    if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
        return None, f"{name} missing or not numeric"
    x = float(v)
    if not math.isfinite(x):
        return None, f"{name} not finite"
    if lo is not None and x < lo:
        return None, f"{name}={x} below {lo}"
    if hi is not None and x > hi:
        return None, f"{name}={x} above {hi}"
    return x, None


def parse_deck(raw: dict | None) -> dict[str, Any]:
    """Validate a deck record. Missing Kv/R/I0/source → status unassessed, no coefficients applied."""
    out: dict[str, Any] = {"source_model": SOURCE, "status": "unassessed", "unassessed_terms": [],
                           "notes": [], "params": None}
    if not raw or not isinstance(raw, dict):
        out["unassessed_terms"].append("motor deck not supplied")
        out["notes"].append("sem deck — o ciclo de sistemas mantém η/load_ratio constantes (omissão ≠ deck)")
        return out
    missing = []
    src = raw.get("source")
    if not (isinstance(src, str) and src.strip()):
        missing.append("source")
    kv, e = _num("kv_rpm_per_V", raw.get("kv_rpm_per_V"), lo=1e-6, hi=1e6)
    if e:
        missing.append(e)
    R, e = _num("R_ohm", raw.get("R_ohm"), lo=1e-9, hi=100.0)
    if e:
        missing.append(e)
    I0, e = _num("I0_A", raw.get("I0_A"), lo=0.0, hi=1e4)
    if e:
        missing.append(e)
    if missing:
        out["unassessed_terms"] = missing
        out["notes"].append("Kv, R, I0 e source são obrigatórios (Drela 2007); número sem fonte não é aplicado")
        return out
    params: dict[str, Any] = {"kv_rpm_per_V": kv, "R_ohm": R, "I0_A": I0, "source": src.strip()}
    if raw.get("retrieved"):
        params["retrieved"] = str(raw["retrieved"])
    for key, lo, hi in (("I_max_A", 0.0, 1e5), ("V_max_V", 0.0, 1e4)):
        if key in raw and raw[key] is not None:
            val, err = _num(key, raw[key], lo=lo, hi=hi)
            if err:
                out["unassessed_terms"].append(err)
            else:
                params[key] = val
    if out["unassessed_terms"]:
        out["notes"].append("limites I_max/V_max inválidos — não aplicados")
        return out
    if "map" in raw and raw["map"] is not None:
        params["map"] = raw["map"]
    out["status"] = "ok"
    out["params"] = params
    return out


def _point(V: float, omega: float, I: float, params: dict) -> dict[str, Any]:
    Kv_si = params["kv_rpm_per_V"] * 2 * math.pi / 60.0
    Kt = 1.0 / Kv_si
    R, I0 = params["R_ohm"], params["I0_A"]
    Q = Kt * (I - I0)
    P_shaft = Q * omega
    P_elec = V * I
    eta = (P_shaft / P_elec) if P_elec > 0 else None
    rpm = omega * 60.0 / (2 * math.pi)
    notes, issues, status = [], [], "ok"
    if I < 0:
        status = "unassessed"
        issues.append("current_negative")
        notes.append("I < 0 (regeneração / back-EMF > V) — fora do domínio motopropulsor; não é η=0 silenciosa")
        eta = None
    elif I < I0:
        notes.append("I < I0 → binário de veio negativo (não é ponto de propulsão)")
    if params.get("I_max_A") is not None and I > params["I_max_A"] + 1e-12:
        status = "unassessed"
        issues.append("motor_deck_out_of_domain_current")
        notes.append(f"I={I:.3g} A > I_max={params['I_max_A']:.3g} A — fora de domínio, valor não é recortado")
        eta = None
    if params.get("V_max_V") is not None and V > params["V_max_V"] + 1e-12:
        status = "unassessed"
        issues.append("motor_deck_out_of_domain_voltage")
        notes.append(f"V={V:.3g} V > V_max={params['V_max_V']:.3g} V — fora de domínio, valor não é recortado")
        eta = None
    return {
        "status": status, "V_V": V, "I_A": I, "rpm": rpm, "omega_rad_s": omega,
        "torque_N_m": Q, "P_shaft_W": P_shaft, "P_elec_W": P_elec, "efficiency": eta,
        "Kt_N_m_per_A": Kt, "Kv_SI_rad_s_per_V": Kv_si, "issues": issues, "notes": notes,
        "in_domain": status == "ok", "source": params["source"], "model": SOURCE,
        "params": {k: params[k] for k in ("kv_rpm_per_V", "R_ohm", "I0_A", "retrieved") if k in params},
    }


def assess_motor(deck: dict | None, *, V_V: float | None = None, rpm: float | None = None,
                 I_A: float | None = None, torque_N_m: float | None = None) -> dict[str, Any]:
    """Evaluate one operating point. Unassessed if the deck or the operating inputs are incomplete."""
    parsed = parse_deck(deck)
    base = {"source_model": SOURCE, "deck_status": parsed["status"],
            "unassessed_terms": list(parsed["unassessed_terms"]), "notes": list(parsed["notes"])}
    if parsed["status"] != "ok":
        return {**base, "status": "unassessed", "efficiency": None, "P_shaft_W": None, "I_A": None}
    params = parsed["params"]
    V, eV = _num("V_V", V_V, lo=0.0, hi=1e4)
    if eV:
        base["unassessed_terms"].append(eV)
        return {**base, "status": "unassessed", "efficiency": None, "P_shaft_W": None, "I_A": None}
    Kv_si = params["kv_rpm_per_V"] * 2 * math.pi / 60.0
    Kt = 1.0 / Kv_si
    R, I0 = params["R_ohm"], params["I0_A"]
    n_ops = sum(x is not None for x in (rpm, I_A, torque_N_m))
    if n_ops != 1:
        base["unassessed_terms"].append("operating point: give exactly one of rpm, I_A, torque_N_m (with V_V)")
        return {**base, "status": "unassessed", "efficiency": None, "P_shaft_W": None, "I_A": None}
    if rpm is not None:
        n, e = _num("rpm", rpm, lo=0.0, hi=1e6)
        if e:
            base["unassessed_terms"].append(e)
            return {**base, "status": "unassessed", "efficiency": None}
        omega = n * 2 * math.pi / 60.0
        I = (V - omega / Kv_si) / R
    elif I_A is not None:
        I, e = _num("I_A", I_A, lo=-1e5, hi=1e5)
        if e:
            base["unassessed_terms"].append(e)
            return {**base, "status": "unassessed", "efficiency": None}
        omega = Kv_si * (V - I * R)
    else:
        Q, e = _num("torque_N_m", torque_N_m, lo=-1e6, hi=1e6)
        if e:
            base["unassessed_terms"].append(e)
            return {**base, "status": "unassessed", "efficiency": None}
        I = Q / Kt + I0
        omega = Kv_si * (V - I * R)
    pt = _point(V, omega, I, params)
    # optional sourced η table — never invent one; cross-check only when in domain
    if params.get("map") is not None and pt["P_shaft_W"] is not None and pt["status"] == "ok":
        from acdt.core.motor_map import motor_efficiency
        tab = motor_efficiency(pt["P_shaft_W"], params["map"], rpm=pt["rpm"])
        pt["map_table"] = tab
        if tab.get("status") == "unassessed":
            pt["notes"].append("tabela η(P) fora de domínio — não se substitui o modelo Drela por η=1")
        elif tab.get("efficiency") is not None:
            pt["notes"].append(
                f"tabela η(P) fornecida = {tab['efficiency']:.3f} (fonte {tab.get('map_source')}); "
                f"modelo Drela = {pt['efficiency']:.3f} — não se misturam")
    pt["unassessed_terms"] = [] if pt["status"] == "ok" else list(pt.get("issues") or [])
    return pt
