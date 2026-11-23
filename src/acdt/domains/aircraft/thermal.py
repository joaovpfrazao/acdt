# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina «térmica» (L0/L1) do domínio aircraft (docs/TERMICA.md).

Etapa do pipeline depois do desempenho. Constrói uma especificação genérica (:mod:`acdt.core.thermal.study`) a
partir do que o dimensionamento já calculou — nada de novo é estimado:

* **fontes de calor** por condição: carga elétrica de bordo (``propulsion.systems_power_W`` + ``onboard_power_W``
  ou o orçamento de potência dos sistemas, o maior), perdas da cadeia elétrica de propulsão (η_total/η_hélice;
  repartição bateria/ESC/motor com ``thermal.electric``), calor de arrefecimento do motor térmico (balanço de
  energia com ṁ_combustível dos segmentos da missão e PCI; fração declarada em ``thermal.engine``), fontes extra
  do utilizador (``thermal.sources``: carga útil, gerador, travões, …);
* **condições**: solo e subida no dia quente (MIL-HDBK-310 1 %), cruzeiro/espera quente, cruzeiro/espera fria
  (1 % frio, sem sol), com as velocidades, altitudes e potências dos segmentos da missão (ou, sem desempenho, do
  ponto de projeto: P = D·V/η);
* **compartimentos**: ``thermal.bays`` do utilizador; sem isso um compartimento «fuselagem» com a área molhada do
  cilindro π·D·L (PRESSUPOSTO), altura D e as fontes internas (aviónica; bateria e ESC nos elétricos).

**Acoplamento** (``thermal.coupling``):

* ``relatorio`` (omissão): uma passagem; o arrasto de arrefecimento (área de arrasto, ΔC_D0), a massa de condutas/
  permutadores/ventiladores e a potência elétrica dos ventiladores são calculados e o seu efeito relatado, sem
  alterar o projeto;
* ``iterar``: dentro da etapa de dimensionamento, ciclo de ponto fixo — dimensiona, calcula a missão exigida
  (a mesma tabela de segmentos do desempenho) e avalia a térmica nesses segmentos, injeta
  ``aero.extra_drag_areas_m2.arrefecimento_termico`` (majorante do intervalo de arrasto),
  ``weights.fixed_mass_kg`` (+ massa de arrefecimento conhecida) e, nos elétricos,
  ``propulsion.systems_power_W`` (+ potência do ventilador em cruzeiro; com power budget em malha fechada também
  como carga ``systems.loads``, porque o fecho substitui ``systems_power_W``), e redimensiona até variação < ``tol``.
  Grandezas desconhecidas não são acopladas (ficam registadas como não acopladas, nunca como zero).
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any

from acdt.core.thermal.sources import (LHV_MJ_KG, LHV_REF, HeatSource, electric_chain, electrical_load,
                                       ice_cooling)
from acdt.core.thermal.study import analyse

LEVEL = "L0"
DEFAULTS: dict[str, Any] = {
    "enabled": True, "coupling": "relatorio", "max_iter": 6, "tol": 0.01,
    "hot_atmosphere": "mil310_hot_1pct", "cold_atmosphere": "mil310_cold_1pct",
    "solar_W_m2": None, "ground": True, "ground_time_s": None, "conditions": None, "bays": None, "sources": {},
    "radiated_fraction": 0.0,
    "electric": {"eta_esc": None, "eta_motor": None, "eta_battery": None, "cell_R_internal_ohm": None,
                 "source": None},
    "engine": {"fuel": None, "lhv_MJ_kg": None, "cooling_fraction": None, "heat_rejection_W": None,
               "air_temperature_rise_K": None, "ram_recovery": None, "duct_loss_q": None,
               "mass_flow_ratio": None, "source": None},
    "components": [], "transient": None,
}


def _opts(spec: Any) -> dict[str, Any]:
    o = copy.deepcopy(DEFAULTS)
    user = (spec.assumptions.get("thermal") or {}) if isinstance(spec.assumptions, dict) else {}
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(o.get(k), dict) and k not in ("sources",):
            o[k] = {**o[k], **v}
        else:
            o[k] = v
    return o


def _not_evaluated(reason: str) -> dict[str, Any]:
    return {"evaluated": False, "level": LEVEL, "reason": reason, "hot_margin_C": None, "cold_margin_C": None,
            "hot_margin_min_C": None, "cold_margin_min_C": None}


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _h_range(s: str) -> tuple[float, float]:
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(s))]
    return (nums[0], nums[-1]) if nums else (0.0, 0.0)


def _segments(res: Any) -> list[dict[str, Any]]:
    """Tabela da missão exigida. O desempenho, quando já correu, ganha; no ciclo ``iterar`` (ainda sem essa etapa)
    usa-se ``required_mission``, calculada com o mesmo ``simulate_mission(..., stop='legs')``."""
    for holder in (getattr(res, "performance", None),):
        if holder is None:
            continue
        try:
            table = list(holder.mission_required.table())
        except Exception:  # noqa: BLE001 — sem tabela de segmentos: tenta a missão do ciclo, senão o ponto de projeto
            table = []
        if table:
            return table
    sim = getattr(res, "required_mission", None)
    if sim is None:
        return []
    try:
        return list(sim.table())
    except Exception:  # noqa: BLE001
        return []


def ensure_required_mission(res: Any) -> dict[str, Any]:
    """Garante a tabela de segmentos no ciclo ``iterar``. Se a missão não puder ser calculada, o ponto de projeto
    continua a ser a alternativa e fica dito — não se trata essa falta como segmento de duração zero."""
    if _segments(res):
        src = "performance.mission_required (segmento)" if getattr(res, "performance", None) is not None else (
            "missão exigida (simulate_mission, stop=legs) calculada no ciclo iterar")
        return {"used": True, "source": src}
    try:
        from .performance import required_mission
        sim = required_mission(res)
    except Exception as ex:  # noqa: BLE001 — a missão em falta não parte o ciclo; o ponto de projeto fica explícito
        return {"used": False, "source": f"tabela de missão indisponível ({type(ex).__name__}: {ex}); ponto de projeto"}
    if not getattr(sim, "segments", None):
        return {"used": False, "source": "missão exigida sem segmentos; ponto de projeto"}
    res.required_mission = sim
    if not _segments(res):
        return {"used": False, "source": "tabela de segmentos vazia; ponto de projeto"}
    return {"used": True, "source": "missão exigida (simulate_mission, stop=legs) calculada no ciclo iterar"}


def _bsfc_kg_J(res: Any) -> tuple[float, str]:
    p = res.spec.assumptions["propulsion"]
    if p.get("bsfc_lb_hp_h") is not None:
        return float(p["bsfc_lb_hp_h"]) * 0.45359237 / (745.69987 * 3600), "assumptions.propulsion.bsfc_lb_hp_h"
    b = 0.5 if res.spec.propulsion_kind == "turboprop" else 0.4
    return b * 0.45359237 / (745.69987 * 3600), f"Raymer Tabela 3.4 (cruzeiro, {b} lb/(hp·h)), como weights.py"


def operating_points(res: Any) -> dict[str, dict[str, Any]]:
    """Pontos de funcionamento da propulsão (potência elétrica da bateria ou caudal de combustível) para as
    condições térmicas: dos segmentos da missão exigida quando o desempenho correu, senão do ponto de projeto."""
    kind = res.spec.propulsion_kind
    segs = _segments(res)
    out: dict[str, dict[str, Any]] = {}
    for s in segs:
        name = str(s.get("segmento", ""))
        t = (_f(s.get("t [min]")) or 0.0) * 60.0
        h0, h1 = _h_range(s.get("h [m]", "0"))
        V = _f(s.get("V [m/s]")) or 0.0
        e_Wh, f_kg = _f(s.get("consumo [Wh]")), _f(s.get("consumo [kg]"))
        if t <= 0:
            continue
        key = "subida" if name.startswith("subida") else ("cruzeiro" if ("espera" in name or "cruzeiro" in name)
                                                           else None)
        if key is None or key in out:
            continue
        pt: dict[str, Any] = {"segment": name, "V_m_s": V, "altitude_m": h1 if key == "cruzeiro" else h0,
                              "duration_s": t, "source": "performance.mission_required (segmento)"}
        if e_Wh is not None:
            pt["P_batt_W"] = e_Wh * 3600.0 / t
        if f_kg is not None:
            pt["fuel_flow_kg_s"] = f_kg / t
        out[key] = pt
    if "cruzeiro" not in out:
        P = res.cruise_power_required()
        p = res.spec.assumptions["propulsion"]
        pt = {"segment": "ponto de projeto (cruzeiro)", "V_m_s": res.cruise_speed, "altitude_m": res.cruise_altitude,
              "duration_s": None, "P_shaft_W": P, "source": "DesignResult.cruise_power_required (D·V/η_p)"}
        if kind == "electric":
            pt["P_batt_W"] = P * p["eta_cruise"] / p["eta_total"]
        elif kind in ("piston_prop", "turboprop"):
            pt["fuel_flow_kg_s"] = P * _bsfc_kg_J(res)[0]
        out["cruzeiro"] = pt
    if "subida" not in out and res.power_sl:
        p = res.spec.assumptions["propulsion"]
        pt = {"segment": "ponto de projeto (potência ao nível do mar)", "V_m_s": 0.8 * res.cruise_speed,
              "altitude_m": 0.0, "duration_s": None, "P_shaft_W": res.power_sl,
              "source": "DesignResult.power_sl; PRESSUPOSTO V = 0,8·V_cruzeiro"}
        if kind == "electric":
            pt["P_batt_W"] = res.power_sl / (p["eta_total"] / p["eta_cruise"])
        elif kind in ("piston_prop", "turboprop"):
            pt["fuel_flow_kg_s"] = res.power_sl * _bsfc_kg_J(res)[0]
        out["subida"] = pt
    return out


def hotel_power(res: Any) -> tuple[float | None, str]:
    p = res.spec.assumptions["propulsion"]
    a = float(p.get("systems_power_W", 0.0) or 0.0) + float(p.get("onboard_power_W", 0.0) or 0.0)
    b = None
    s = getattr(res, "systems", None)
    pb = getattr(s, "power_budget", None) if s is not None else None
    if pb is not None:
        try:
            b = float(pb.average_w)
        except Exception:  # noqa: BLE001
            b = None
    if b is not None and b > a:
        base, src = b, "orçamento de potência dos sistemas (MIL-E-7016F / Moir & Seabridge), média"
    else:
        base, src = a, "assumptions.propulsion.systems_power_W + onboard_power_W"
    from .native_disciplines import hotel_adjustment
    return hotel_adjustment(base, src, res.spec)


def build_spec(res: Any, o: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Especificação genérica (core.thermal.study) a partir do DesignResult e de ``assumptions.thermal``."""
    kind = res.spec.propulsion_kind
    p = res.spec.assumptions["propulsion"]
    notes: list[str] = []
    ops = operating_points(res)
    cr, cl = ops.get("cruzeiro") or {}, ops.get("subida") or {}
    hot, cold = str(o["hot_atmosphere"]), str(o["cold_atmosphere"])
    conds: list[dict[str, Any]] = o.get("conditions") or []
    if not conds:
        h_c = float(cr.get("altitude_m", res.cruise_altitude) or 0.0)
        if cold == "mil310_cold_20pct" and h_c > 10000:
            cold = "mil310_cold_1pct"
            notes.append("acima de 10 km: frio 1 % (a Tabela XX de 20 % só foi transcrita até 10 km)")
        sol = o.get("solar_W_m2")
        if o.get("ground", True):
            conds.append({"name": "solo_quente", "case": "hot", "atmosphere": hot, "altitude_m": 0.0, "V_m_s": 0.0,
                          "solar_W_m2": sol})
        if cl:
            conds.append({"name": "subida_quente", "case": "hot", "atmosphere": hot, "altitude_m": 0.0,
                          "V_m_s": float(cl.get("V_m_s") or 0.0), "solar_W_m2": sol})
        conds.append({"name": "cruzeiro_quente", "case": "hot", "atmosphere": hot, "altitude_m": h_c,
                      "V_m_s": float(cr.get("V_m_s") or res.cruise_speed), "solar_W_m2": sol})
        conds.append({"name": "cruzeiro_frio", "case": "cold", "atmosphere": cold, "altitude_m": h_c,
                      "V_m_s": float(cr.get("V_m_s") or res.cruise_speed), "solar_W_m2": 0.0})
    phase_of = {"solo_quente": None, "subida_quente": cl, "cruzeiro_quente": cr, "cruzeiro_frio": cr}
    for c in conds:  # condições do utilizador: fase de propulsão pela chave 'propulsion' (subida|cruzeiro|parado)
        if c.get("propulsion"):
            phase_of[str(c["name"])] = ops.get(str(c["propulsion"]))
        phase_of.setdefault(str(c["name"]), cr if float(c.get("V_m_s", 0) or 0) > 0.5 else None)
    # ---- fontes
    P_hot, hot_src = hotel_power(res)
    if P_hot is None:
        srcs: dict[str, Any] = {"avionica": {"heat_W": None, "method": hot_src}}
    else:
        srcs = {"avionica": {"heat_W": electrical_load("avionica", P_hot, float(o["radiated_fraction"]),
                                                       f"carga elétrica de bordo: {hot_src}"),
                             "method": hot_src}}
    if P_hot is not None and P_hot <= 0.0:
        notes.append("carga elétrica de bordo declarada = 0 W (systems_power_W/onboard_power_W e power_budget): "
                     "aviónica sem calor — confirme que não é uma omissão do modelo")
    el = o.get("electric") or {}
    eng = o.get("engine") or {}
    chain_ids: list[str] = []
    engine_q: dict[str, HeatSource] = {}
    if kind == "electric":
        eta_chain = float(p["eta_total"]) / float(p["eta_cruise"])
        R_pack, V_nom = None, None
        sysr = getattr(res, "systems", None)
        bat = getattr(sysr, "battery", None) if sysr is not None else None
        Rc = _f(el.get("cell_R_internal_ohm"))
        if bat is not None:
            V_nom = _f(getattr(bat, "v_nom", None))
            if Rc is not None:
                R_pack = Rc * int(getattr(bat, "S", 1)) / max(int(getattr(bat, "P", 1)), 1)
        elif Rc is not None:
            notes.append("cell_R_internal_ohm declarado mas sem pacote de baterias selecionado (systems): I²R não "
                         "avaliado")
        per: dict[str, dict[str, HeatSource]] = {}
        for cn, op in phase_of.items():
            Pb = (op or {}).get("P_batt_W") if op else 0.0
            if Pb is None:
                continue
            per[cn] = electric_chain(float(Pb or 0.0), eta_chain, eta_esc=_f(el.get("eta_esc")),
                                     eta_motor=_f(el.get("eta_motor")), eta_battery=_f(el.get("eta_battery")),
                                     R_pack_ohm=R_pack, V_nom=V_nom)
        for comp in ("bateria", "esc", "motor"):
            srcs[comp] = {"heat_W": {cn: d[comp] for cn, d in per.items()} | {"default": 0.0},
                          "method": "cadeia elétrica de propulsão (η_total/η_hélice)"}
        chain_ids = ["bateria", "esc"]
    elif kind in ("piston_prop", "turboprop"):
        fuel = str(eng.get("fuel") or ("jet_a" if kind == "turboprop" else "avgas"))
        if fuel not in LHV_MJ_KG and _f(eng.get("lhv_MJ_kg")) is None:
            raise ValueError(f"combustível '{fuel}' sem PCI por omissão: declare thermal.engine.lhv_MJ_kg")
        lhv = _f(eng.get("lhv_MJ_kg"))
        lhv_src = "thermal.engine.lhv_MJ_kg"
        if lhv is None:
            lhv = LHV_MJ_KG[fuel]
            lhv_src = LHV_REF[fuel] + " (PRESSUPOSTO: mínimo da norma)"
        bs, bs_src = _bsfc_kg_J(res)
        for cn, op in phase_of.items():
            ff = (op or {}).get("fuel_flow_kg_s") if op else 0.0
            if ff is None:
                continue
            Ps = (op or {}).get("P_shaft_W")
            if Ps is None:
                Ps = float(ff or 0.0) / bs
            engine_q[cn] = ice_cooling("motor_termico", float(Ps), float(ff or 0.0), lhv * 1e6,
                                       _f(eng.get("cooling_fraction")), _f(eng.get("heat_rejection_W")))
        srcs["motor_termico"] = {"heat_W": dict(engine_q) | {"default": 0.0},
                                 "method": f"balanço de energia do motor; PCI {lhv} MJ/kg ({lhv_src}); BSFC {bs_src}"}
    else:
        notes.append(f"propulsão '{kind}': calor do motor para compartimentos adjacentes não modelado — declare-o em "
                     "thermal.sources (fica desconhecido, nunca zero, se o compartimento o listar)")
    for sid, v in (o.get("sources") or {}).items():
        srcs[str(sid)] = v if isinstance(v, dict) else {"heat_W": v}
    from .native_disciplines import distribution_source
    srcs.update(distribution_source(res.spec))
    # ---- compartimentos
    bays = o.get("bays")
    if not bays:
        fus = getattr(getattr(res, "config", None), "fuselage", None)
        L = float(getattr(fus, "length", 0.0) or 0.0)
        D = float(getattr(fus, "max_diameter", 0.0) or 0.0)
        if L <= 0 or D <= 0:
            raise ValueError("sem geometria da fuselagem: declare thermal.bays")
        bays = [{"id": "fuselagem", "skin_area_m2": math.pi * D * L, "flow_length_m": L, "height_m": D,
                 "sources": ["avionica"] + chain_ids + [str(k) for k in (o.get("sources") or {})],
                 "components": list(o.get("components") or []),
                 "note": "PRESSUPOSTO: compartimento único = fuselagem cilíndrica π·D·L, altura D; emissividades e "
                         "absortividade desconhecidas (intervalo físico [0, 1])"}]
        notes.append(bays[0]["note"])
    for bay in bays:
        if not isinstance(bay, dict):
            continue
        have = [str(s) for s in (bay.get("sources") or [])]
        if "perdas_distribuicao" in srcs and "perdas_distribuicao" not in have and (
                "avionica" in have or bay is bays[0]):
            have.append("perdas_distribuicao")
            bay["sources"] = have
            notes.append(f"{bay.get('id')}: perdas de distribuição acrescentadas às fontes do compartimento")
    S = res.S
    spec = {"conditions": conds, "sources": srcs, "bays": bays,
            "reference": {"S_ref_m2": S, "cruise_condition": "cruzeiro_quente"}}
    tr = o.get("transient")
    if tr is None and any(b.get("capacity_J_K") or (b.get("mass_kg") and b.get("cp_J_kgK")) for b in bays):
        ph = []
        if o.get("ground", True):
            ph.append({"condition": "solo_quente", "duration_s": float((o.get("ground_time_s") or 0) or 0)})
        if cl and cl.get("duration_s"):
            ph.append({"condition": "subida_quente", "duration_s": float(cl["duration_s"])})
        if cr and cr.get("duration_s"):
            ph.append({"condition": "cruzeiro_quente", "duration_s": float(cr["duration_s"])})
        ph = [x for x in ph if x["duration_s"] > 0]
        if ph:
            tr = {"phases": ph}
            if not o.get("ground_time_s"):
                notes.append("transitório sem tempo no solo (thermal.ground_time_s não declarado)")
    if tr:
        spec["transient"] = tr
    return spec, notes


def _engine_cooling(res: Any, o: dict[str, Any], spec: dict[str, Any], th: dict[str, Any]) -> dict[str, Any] | None:
    """Ar de arrefecimento do motor térmico: ṁ = Q/(c_p·ΔT_ar) com ΔT_ar declarado; arrasto interno (cooling.py)."""
    if res.spec.propulsion_kind not in ("piston_prop", "turboprop"):
        return None
    from acdt.core.thermal.cooling import NACA_MFR_DESIGN, internal_drag
    from acdt.core.thermal.air import CP_AIR
    from acdt.core.thermal.study import _source_for, build_condition
    eng = o.get("engine") or {}
    dT = _f(eng.get("air_temperature_rise_K"))
    mfr = _f(eng.get("mass_flow_ratio")) or NACA_MFR_DESIGN
    out: dict[str, Any] = {"by_condition": {}}
    for c in spec["conditions"]:
        cn = str(c["name"])
        if float(c.get("V_m_s", 0) or 0) <= 0.5:
            continue
        q = _source_for("motor_termico", spec["sources"]["motor_termico"], cn)
        cond = build_condition(c)
        if dT is None or dT <= 0:
            out["by_condition"][cn] = {"Q_W": {"lo": q.lo, "hi": q.hi}, "m_dot_kg_s": None, "drag_N": None,
                                       "inlet_area_m2": None, "status": "desconhecido",
                                       "reason": "thermal.engine.air_temperature_rise_K não declarado"}
            continue
        m_lo = q.lo / (CP_AIR * dT)
        m_hi = None if q.hi is None else q.hi / (CP_AIR * dT)
        rr, dl = _f(eng.get("ram_recovery")), _f(eng.get("duct_loss_q"))
        zeta = None if rr is None or dl is None else (1 - rr) + dl
        d_lo = internal_drag(m_lo, cond.V_m_s, zeta)[0]
        d_hi = None if m_hi is None else internal_drag(m_hi, cond.V_m_s, zeta)[1]
        qd = 0.5 * cond.ambient.rho * cond.V_m_s ** 2
        area = None if m_hi is None else m_hi / (mfr * cond.ambient.rho * cond.V_m_s)
        out["by_condition"][cn] = {"Q_W": {"lo": q.lo, "hi": q.hi}, "m_dot_kg_s": {"lo": m_lo, "hi": m_hi},
                                   "drag_N": {"lo": d_lo, "hi": d_hi}, "zeta": zeta,
                                   "drag_area_m2": {"lo": d_lo / qd, "hi": None if d_hi is None else d_hi / qd},
                                   "inlet_area_m2": area}
    candidates = {cn: row.get("inlet_area_m2") for cn, row in out["by_condition"].items()}
    if not candidates or any(a is None for a in candidates.values()):
        out["design_inlet"] = {
            "status": "desconhecido",
            "candidates_m2": candidates,
            "reason": ("thermal.engine.air_temperature_rise_K não declarado" if dT is None or dT <= 0 else
                       "há segmento em voo sem área; o pior não é o máximo dos restantes")}
        return out
    winner = max(candidates, key=lambda cn: float(candidates[cn] or 0.0))
    installed = float(candidates[winner] or 0.0)
    out["design_inlet"] = {
        "status": "dimensionado", "condition": winner, "inlet_area_m2": installed, "candidates_m2": candidates,
        "method": "A = max ṁ/(MFR·ρ·V) nos segmentos em voo; MFR de projeto 0,60 (Hall & Frank, NACA RM A8I29)",
        "off_design_note": ("PRESSUPOSTO: em cada segmento o caudal admitido é MFR·ρ·V·A com o mesmo MFR de "
                            "projeto; a variação de recuperação com o MFR, descrita no NACA RM A8I29, não é aplicada")}
    for c in spec["conditions"]:
        cn = str(c["name"])
        row = out["by_condition"].get(cn)
        if row is None or row.get("inlet_area_m2") is None:
            continue
        cond = build_condition(c)
        m_adm = mfr * cond.ambient.rho * cond.V_m_s * installed
        zeta = row.get("zeta")
        d_lo, d_hi, _ve = internal_drag(m_adm, cond.V_m_s, zeta if isinstance(zeta, float) else None)
        qd = 0.5 * cond.ambient.rho * cond.V_m_s ** 2
        row["required_m_dot_kg_s"] = row["m_dot_kg_s"]
        row["required_inlet_area_m2"] = row["inlet_area_m2"]
        row["m_dot_kg_s"] = {"lo": m_adm, "hi": m_adm}
        row["drag_N"] = {"lo": d_lo, "hi": d_hi}
        row["drag_area_m2"] = {"lo": d_lo / qd, "hi": d_hi / qd}
        row["inlet_area_m2"] = installed
    return out


def sizing_unusable(res: Any) -> str | None:
    """Motivo pelo qual o dimensionamento não serve de entrada às análises acopladas (``None`` = serve).

    Sem convergência (p.ex. espiral de massa a baixa densidade da bateria) o ``DesignResult`` traz NaN na
    velocidade/potência; a térmica não tem solução de regime para entradas não finitas — fica ``nao_avaliado``."""
    sz = getattr(res, "sizing", None)
    if sz is None or not getattr(sz, "converged", False):
        return "dimensionamento não convergiu (sem solução: p.ex. espiral de massa)"
    for nm in ("cruise_speed", "power_sl"):
        v = getattr(res, nm, None)
        if v is not None and not math.isfinite(float(v)):
            return f"dimensionamento com {nm} não finito"
    W0 = getattr(sz, "W0", None)
    if W0 is None or not math.isfinite(float(W0)):
        return "dimensionamento com W0 não finito"
    return None


def analyse_thermal(res: Any) -> dict[str, Any]:
    why = sizing_unusable(res)
    if why is not None:
        raise ValueError(f"{why}; térmica sem solução de regime — nao_avaliado")
    o = _opts(res.spec)
    spec, notes = build_spec(res, o)
    th = analyse(spec)
    ec = _engine_cooling(res, o, spec, th)
    cool = th["cooling"]
    if ec is not None:
        cr = ec["by_condition"].get("cruzeiro_quente") or {}
        d = cr.get("drag_N")
        if isinstance(d, dict):
            cool["engine_drag_N"] = d
            lo = cool["drag_N"]["lo"] + (d["lo"] or 0.0)
            hi = None if d["hi"] is None or cool["drag_N"]["hi"] is None else cool["drag_N"]["hi"] + d["hi"]
            cool["drag_N"] = {"lo": lo, "hi": hi}
            if cr.get("zeta") is None:
                cool["drag_known"] = False
        else:
            cool["engine_drag_N"] = None
            cool["drag_known"] = False
            notes.append("arrasto de arrefecimento do motor desconhecido (thermal.engine.air_temperature_rise_K)")
        c = next((x for x in spec["conditions"] if x["name"] == "cruzeiro_quente"), None)
        if c is not None and cool["drag_N"]["hi"] is not None:
            from acdt.core.thermal.study import build_condition
            cd = build_condition(c)
            qd = 0.5 * cd.ambient.rho * cd.V_m_s ** 2
            cool["drag_area_m2"] = {"lo": cool["drag_N"]["lo"] / qd, "hi": cool["drag_N"]["hi"] / qd}
            cool["delta_CD0"] = {"lo": cool["drag_N"]["lo"] / (qd * res.S), "hi": cool["drag_N"]["hi"] / (qd * res.S)}
        elif cool["drag_N"]["hi"] is None:
            cool["drag_area_m2"] = {"lo": cool["drag_area_m2"]["lo"] if cool.get("drag_area_m2") else None,
                                    "hi": None}
            cool["delta_CD0"] = {"lo": cool["delta_CD0"]["lo"] if cool.get("delta_CD0") else None, "hi": None}
    ops = operating_points(res)
    th.update({"evaluated": True, "level": LEVEL, "operating_points": ops, "engine_cooling": ec,
               "adapter_notes": notes, "coupling_mode": o["coupling"], "inputs": {
                   k: o[k] for k in ("hot_atmosphere", "cold_atmosphere", "radiated_fraction", "electric", "engine")}})
    th["coupling_effect"] = coupling_effect(res, th)
    return th


def coupling_effect(res: Any, th: dict[str, Any]) -> dict[str, Any]:
    """Efeito das grandezas de acoplamento no projeto atual (relatório de uma passagem)."""
    cool = th.get("cooling") or {}
    eff: dict[str, Any] = {"applied": th.get("coupling_mode") == "iterar"}
    da = cool.get("drag_area_m2")
    try:
        CD0 = float(res.polar.CD0)
    except Exception:  # noqa: BLE001
        CD0 = None
    if isinstance(da, dict) and CD0:
        f0 = CD0 * res.S
        eff["drag_area_fraction_of_CD0"] = {"lo": None if da.get("lo") is None else da["lo"] / f0,
                                            "hi": None if da.get("hi") is None else da["hi"] / f0}
    m = cool.get("mass_kg")
    eff["mass_fraction_of_W0"] = None if m is None else m / res.sizing.W0
    P = cool.get("fan_power_max_W")
    hp, _s = hotel_power(res)
    eff["fan_power_W"] = P
    eff["fan_power_fraction_of_hotel"] = None if (P is None or not hp) else P / hp
    return eff


def coupling_increments(th: dict[str, Any], kind: str) -> dict[str, Any]:
    """Incrementos a injetar no dimensionamento (modo iterar). Desconhecidos → não acoplados (listados)."""
    cool = th.get("cooling") or {}
    inc: dict[str, Any] = {"drag_area_m2": None, "mass_kg": None, "power_W": None, "not_coupled": []}
    da = cool.get("drag_area_m2") or {}
    if da.get("hi") is not None:
        inc["drag_area_m2"] = float(da["hi"])
        if not cool.get("drag_known", True):
            inc["not_coupled"].append("arrasto: perdas não declaradas — acoplado o majorante ṁV")
    else:
        inc["not_coupled"].append("arrasto de arrefecimento desconhecido")
    if cool.get("mass_kg") is not None:
        inc["mass_kg"] = float(cool["mass_kg"])
    else:
        inc["not_coupled"].append("massa de arrefecimento desconhecida")
    fp = (cool.get("fan_power_W") or {}).get("cruzeiro_quente", 0.0)
    if fp is None:
        inc["not_coupled"].append("potência do ventilador desconhecida")
    elif kind == "electric":
        inc["power_W"] = float(fp)
    elif fp:
        inc["not_coupled"].append("potência do ventilador em motor térmico: declare-a como carga onboard (BSFC/η do "
                                  "gerador)")
    return inc


def size_with_thermal(spec: Any, run_fn: Any) -> tuple[Any, Any, dict[str, Any]]:
    """Modo ``iterar``: ponto fixo dimensionamento ↔ térmica. ``run_fn(spec) -> (res, systems)``."""
    o = _opts(spec)
    base_mass = float(spec.assumptions["weights"].get("fixed_mass_kg", 0.0) or 0.0)
    base_P = float(spec.assumptions["propulsion"].get("systems_power_W", 0.0) or 0.0)
    base_areas = dict(spec.assumptions["aero"].get("extra_drag_areas_m2") or {})
    hist: list[dict[str, Any]] = []
    cur = {"drag_area_m2": 0.0, "mass_kg": 0.0, "power_W": 0.0}
    sp = spec
    res = sysr = None
    converged = False
    mission: dict[str, Any] = {"used": False, "source": "ciclo não arrancou"}
    for it in range(int(o["max_iter"])):
        res, sysr = run_fn(sp)
        why = sizing_unusable(res)
        if why is not None:  # sem solução: o ciclo para; a etapa térmica regista nao_avaliado com o motivo
            hist.append({"iter": it, "W0_kg": None, "status": "nao_avaliado", "reason": why})
            break
        mission = ensure_required_mission(res)
        th = analyse_thermal(res)
        inc = coupling_increments(th, spec.propulsion_kind)
        new = {k: float(inc[k] or 0.0) for k in ("drag_area_m2", "mass_kg", "power_W")}
        hist.append({"iter": it, "W0_kg": res.sizing.W0, **new, "not_coupled": inc["not_coupled"],
                     "mission": mission})
        dif = max(abs(new[k] - cur[k]) / max(abs(new[k]), abs(cur[k]), 1e-9) for k in new) if any(
            new[k] or cur[k] for k in new) else 0.0
        if it > 0 and dif < float(o["tol"]):
            converged = True
            break
        cur = new
        sp = copy.copy(spec)
        sp.assumptions = copy.deepcopy(spec.assumptions)
        sp.assumptions["aero"]["extra_drag_areas_m2"] = {**base_areas, "arrefecimento_termico": new["drag_area_m2"]}
        sp.assumptions["weights"]["fixed_mass_kg"] = base_mass + new["mass_kg"]
        if spec.propulsion_kind == "electric":
            sp.assumptions["propulsion"]["systems_power_W"] = base_P + new["power_W"]
            # com power budget em malha fechada (systems_integration.run_with_systems) systems_power_W é substituído
            # pela média do balanço: sem isto a potência do ventilador perdia-se em silêncio. Entra também como
            # carga do balanço (ciclo 1 — PRESSUPOSTO conservador: o ventilador corre em todo o cruzeiro quente)
            if new["power_W"] and getattr(spec, "systems", None):
                sp.systems = with_load(spec.systems, FAN_LOAD_NAME, new["power_W"], 1.0)
    return res, sysr, {"converged": converged, "history": hist, "method": "ponto fixo dimensionamento ↔ térmica",
                       "mission": mission,
                       "operating_point": "tabela de segmentos da missão exigida, quando a missão fecha; senão o "
                                          "ponto de projeto (a falta fica em mission.source)",
                       "electrical_load": "propulsion.systems_power_W + systems.loads (ciclo 1, conservador)"}


FAN_LOAD_NAME = "ventilador de arrefecimento (acdt.thermal)"


def with_load(systems: Any, name: str, power_w: float, duty: float, peak_w: float | None = None) -> dict[str, Any]:
    """Cópia de ``spec.systems`` com a carga ``name`` (substitui uma anterior com o mesmo nome) no balanço elétrico.

    Usado pelos acoplamentos ``iterar`` (térmica, gelo): ``run_with_systems`` substitui ``systems_power_W`` pela média
    do balanço, por isso a potência acoplada tem de entrar como carga do balanço."""
    ss = copy.deepcopy(dict(systems or {}))
    loads = [L for L in list(ss.get("loads") or []) if L.get("name") != name]
    load: dict[str, Any] = {"name": name, "power_w": float(power_w), "duty": float(duty)}
    if peak_w is not None:
        load["peak_w"] = float(peak_w)
    ss["loads"] = loads + [load]
    return ss


def thermal_stage(res: Any) -> None:
    from acdt.core.requirements import Issue

    o = _opts(res.spec)
    if not o.get("enabled", True):
        res.thermal = _not_evaluated("thermal.enabled: false")
        return
    try:
        th = analyse_thermal(res)
    except Exception as ex:  # noqa: BLE001 — a etapa térmica nunca parte o pipeline; fica desconhecido
        res.thermal = _not_evaluated(f"falhou: {type(ex).__name__}: {ex}")
        res.issues.append(Issue("warning", f"térmica não avaliada: {type(ex).__name__}: {ex}"))
        return
    loop = getattr(res, "thermal_coupling", None)
    if loop is not None:
        th["coupling_loop"] = loop
    res.thermal = th
