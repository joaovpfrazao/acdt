# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Análise genérica de fiabilidade e manutenção ``acdt.reliability/1`` (docs/FIABILIDADE.md §5).

Entrada (todas as grandezas por hora de voo, FH):

* ``components``: ``[{id, supplier | rate_key | lambda_per_h | mtbf_h (+ source), n, duty, mttr_h, mmh_per_action,
  replacement_cost, spares: {resupply_days, confidence}}]``;
* ``rbd``: árvore (``series`` | ``parallel`` | ``k_of_n`` | ``paths``); omissão: série dos componentes
  ``critical`` (omissão ``true``);
* ``mission_duration_h``; ``accept_assumptions`` (aceitar entradas ``kind: assumption`` da base, omissão ``false``);
* ``preventive``: ``[{id, interval_fh | interval_days, duration_h, mmh, parts_cost, source}]``;
* ``logistics``: ``{mean_logistic_delay_h, mean_admin_delay_h, ready_time_h, source}`` (número ou ``{lo, hi}``);
* ``utilization``: ``{fh_per_aircraft_per_day}``; ``fleet``: ver :mod:`.fleet`; ``spares``: ``{resupply_days,
  confidence, fleet_size}`` (omissões por componente); ``operating_cost``: bloco de
  :func:`acdt.domains.aircraft.manufacturing.costing.operational_cost_from_dict` (a manutenção é preenchida aqui).

Saída: intervalos ``{lo, hi}``; ``None`` = desconhecido (nunca zero). Ver o docstring de cada módulo para as fontes.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Mapping

from . import REF_338B, SCHEMA
from . import fleet as fleet_mod
from . import maintenance as mt
from . import rbd as rbd_mod
from .rates import Rate, _num, resolve
from .spares import stock_for

_BIG = 1e12
Iv = dict[str, Any]


def _iv(lo: float | None, hi: float | None) -> Iv:
    return {"lo": lo, "hi": hi}


def _pair(raw: Any) -> tuple[float | None, float | None]:
    if isinstance(raw, Mapping):
        return _num(raw.get("lo")), _num(raw.get("hi"))
    v = _num(raw)
    return v, v


def _inv(x: float | None) -> float | None:
    return None if x is None or x <= 0 else 1.0 / x


def analyse(spec: Mapping[str, Any]) -> dict[str, Any]:
    comps_in = list(spec.get("components") or [])
    if not comps_in:
        raise ValueError("a especificação de fiabilidade precisa de components")
    ids = [str(c.get("id")) for c in comps_in]
    if len(set(ids)) != len(ids) or any(i in ("", "None") for i in ids):
        raise ValueError("ids de componentes únicos e não vazios")
    comps = {str(c["id"]): dict(c) for c in comps_in}
    acc = bool(spec.get("accept_assumptions", False))
    notes: list[str] = []
    rates: dict[str, Rate] = {cid: resolve(c, accept_assumptions=acc) for cid, c in comps.items()}

    # ---- RBD (modelo de missão) e multiplicidades (modelo básico)
    tree = spec.get("rbd")
    if tree is None:
        crit = [cid for cid, c in comps.items() if c.get("critical", True)]
        if not crit:
            raise ValueError("sem componentes críticos e sem rbd")
        tree = rbd_mod.series_of(crit)
        notes.append("rbd por omissão: série dos componentes críticos (sem redundância declarada)")
    used = rbd_mod.validate(tree, set(comps))
    n_of = {cid: int(c.get("n", 1) or 1) for cid, c in comps.items()}
    mult = rbd_mod.multiplicity(tree, n_of)
    for cid in comps:
        mult.setdefault(cid, n_of[cid])  # fora do RBD (não críticos): contam para a manutenção

    unit: dict[str, tuple[float | None, float | None]] = {}
    comp_out: dict[str, Any] = {}
    for cid, cd0 in comps.items():
        r = rates[cid]
        duty = _num(cd0.get("duty"))
        duty = 1.0 if duty is None else duty
        if cd0.get("duty") is None:
            r.notes.append("duty 1 (PRESSUPOSTO: funciona durante todo o voo)")
        u: tuple[float | None, float | None] = (None, None) if not r.known else (
            float(r.lo or 0.0) * duty, float(r.hi or 0.0) * duty)
        unit[cid] = u
        u0, u1 = u
        comp_out[cid] = {"lambda_per_h": _iv(r.lo, r.hi), "kind": r.kind, "source": r.source, "notes": r.notes,
                         "duty": duty, "n": n_of[cid], "units_total": mult[cid], "in_mission_model": cid in used,
                         "lambda_per_fh_total": _iv(None if u0 is None else u0 * mult[cid],
                                                    None if u1 is None else u1 * mult[cid])}
    unknown = sorted(cid for cid in comps if unit[cid][0] is None)

    # ---- missão: R(t) e MTBCF (blocos folha com n em série: λ_bloco = λ_u n)
    blk_lo: dict[str, float | None] = {}  # → R_lo (λ_hi)
    blk_hi: dict[str, float | None] = {}  # → R_hi (λ_lo)
    for cid in comps:
        a0, a1 = unit[cid]
        blk_lo[cid] = None if a1 is None else a1 * n_of[cid]
        blk_hi[cid] = None if a0 is None else a0 * n_of[cid]
    t_m = _num(spec.get("mission_duration_h"))
    mission: dict[str, Any] = {"duration_h": t_m, "rbd": copy.deepcopy(tree)}
    if t_m is not None and t_m > 0:
        mission["reliability"] = _iv(rbd_mod.reliability(tree, blk_lo, t_m, 0.0),
                                     rbd_mod.reliability(tree, blk_hi, t_m, 1.0))
    else:
        mission["reliability"] = _iv(None, None)
        notes.append("duração da missão desconhecida: fiabilidade de missão desconhecida")
    mission["mtbcf_h"] = _iv(rbd_mod.mttf(tree, blk_lo, 0.0), rbd_mod.mttf(tree, blk_hi, 1.0))
    if unknown:
        notes.append(f"λ desconhecido em {unknown}: minorantes com R = 0 e majorantes com R = 1 nesses blocos")

    # ---- básico (todas as unidades em série: procura de manutenção)
    lam_lo_known = sum((unit[c][0] or 0.0) * mult[c] for c in comps if unit[c][0] is not None)
    lam_hi = None if unknown else sum((unit[c][1] or 0.0) * mult[c] for c in comps)
    basic = {"lambda_per_fh": _iv(lam_lo_known, lam_hi), "mtbf_h": _iv(_inv(lam_hi), _inv(lam_lo_known))}

    # ---- utilização e manutenção preventiva
    util = spec.get("utilization") or {}
    fh_day = _num(util.get("fh_per_aircraft_per_day"))
    prev_out: list[dict[str, Any]] = []
    f_tot: float | None = 0.0
    for pt in spec.get("preventive") or []:
        f = None
        if _num(pt.get("interval_fh")):
            f = 1.0 / float(pt["interval_fh"])
        elif _num(pt.get("interval_days")):
            f = None if not fh_day else 1.0 / (float(pt["interval_days"]) * fh_day)
            if f is None:
                notes.append(f"tarefa preventiva {pt.get('id')!r} por calendário sem utilização (FH/dia): "
                             "frequência desconhecida")
        prev_out.append({"id": pt.get("id"), "frequency_per_fh": f, "duration_h": _num(pt.get("duration_h")),
                         "mmh": _num(pt.get("mmh")), "parts_cost": _num(pt.get("parts_cost")),
                         "source": pt.get("source")})
        f_tot = None if (f is None or f_tot is None) else f_tot + f

    # ---- manutibilidade: M_ct (Eq. 5.75), MTBM, M̄, MMH/FH
    lam_rng = {c: ((unit[c][0] or 0.0) * mult[c], (unit[c][1] or 0.0) * mult[c]) if unit[c][0] is not None
               else (0.0, _BIG) for c in comps}
    mttr_v = {c: _num(comps[c].get("mttr_h")) for c in comps}
    miss_mttr = sorted(c for c in comps if mttr_v[c] is None)
    if miss_mttr:
        mct: Iv = _iv(None, None)
        notes.append(f"MTTR não declarado em {miss_mttr}: M_ct, M̄ e disponibilidades desconhecidos")
    else:
        lo_, hi_ = mt.weighted_mean_bounds([float(mttr_v[c] or 0.0) for c in comps],
                                           [lam_rng[c][0] for c in comps], [lam_rng[c][1] for c in comps])
        mct = _iv(lo_, hi_)
    m_bar: Iv = _iv(None, None)
    if not miss_mttr and f_tot is not None and all(p["duration_h"] is not None for p in prev_out):
        vals = [float(mttr_v[c] or 0.0) for c in comps] + [float(p["duration_h"]) for p in prev_out]
        wl = [lam_rng[c][0] for c in comps] + [float(p["frequency_per_fh"]) for p in prev_out]
        wh = [lam_rng[c][1] for c in comps] + [float(p["frequency_per_fh"]) for p in prev_out]
        m_bar = _iv(*mt.weighted_mean_bounds(vals, wl, wh))
    elif prev_out:
        notes.append("tarefa preventiva sem frequência ou duração: M̄ desconhecido")
    else:
        m_bar = dict(mct)
    if f_tot is None:
        mtbm_iv = _iv(None, None if lam_lo_known + 0.0 <= 0 else None)
    else:
        mtbm_iv = _iv(None if lam_hi is None else mt.mtbm(lam_hi, f_tot),
                      None if lam_lo_known + f_tot <= 0 else mt.mtbm(lam_lo_known, f_tot))
    mmh_lo = 0.0
    mmh_hi: float | None = 0.0
    for c in comps:
        m = _num(comps[c].get("mmh_per_action"))
        ul = unit[c][0]
        if m is None or ul is None:
            mmh_hi = None
        if m is not None and ul is not None:
            mmh_lo += ul * mult[c] * m
            if mmh_hi is not None:
                mmh_hi += float(unit[c][1] or 0.0) * mult[c] * m
    for p in prev_out:
        if p["mmh"] is None or p["frequency_per_fh"] is None:
            mmh_hi = None
            continue
        mmh_lo += p["frequency_per_fh"] * p["mmh"]
        if mmh_hi is not None:
            mmh_hi += p["frequency_per_fh"] * p["mmh"]
    maint = {"mttr_h": mct, "m_bar_h": m_bar, "mtbm_h": mtbm_iv, "preventive_frequency_per_fh": f_tot,
             "preventive": prev_out, "mmh_per_fh": _iv(mmh_lo, mmh_hi)}

    # ---- disponibilidades (Eq. 10.18, 10.21, 10.22)
    def ratio(up: Iv, down: Iv, fn: Any) -> Iv:
        lo = None if up["lo"] is None or down["hi"] is None else fn(up["lo"], down["hi"])
        hi = None if up["hi"] is None or down["lo"] is None else fn(up["hi"], down["lo"])
        return _iv(lo, hi)

    A_i = ratio(basic["mtbf_h"], mct, mt.inherent_availability)
    A_a = ratio(mtbm_iv, m_bar, mt.achieved_availability)
    lg = spec.get("logistics") or {}
    ld_lo, ld_hi = _pair(lg.get("mean_logistic_delay_h"))
    ad_lo, ad_hi = _pair(lg.get("mean_admin_delay_h"))
    rt_lo, rt_hi = _pair(lg.get("ready_time_h", 0.0))
    rt_lo, rt_hi = (rt_lo or 0.0), (rt_hi or 0.0)
    mdt = _iv(None if m_bar["lo"] is None else m_bar["lo"] + (ld_lo or 0.0) + (ad_lo or 0.0),
              None if (m_bar["hi"] is None or ld_hi is None or ad_hi is None) else m_bar["hi"] + ld_hi + ad_hi)
    if ld_hi is None or ad_hi is None:
        notes.append("tempos logístico/administrativo não declarados: A_o só com majorante (atrasos ≥ 0)")
    A_o = _iv(None if mtbm_iv["lo"] is None or mdt["hi"] is None else
              mt.operational_availability(mtbm_iv["lo"], mdt["hi"], rt_lo),
              None if mtbm_iv["hi"] is None or mdt["lo"] is None else
              mt.operational_availability(mtbm_iv["hi"], mdt["lo"], rt_hi))
    avail = {"inherent": A_i, "achieved": A_a, "operational": A_o, "mdt_h": mdt,
             "basis": "horas de voo (λ por FH); limites exteriores"}

    out: dict[str, Any] = {"schema": SCHEMA, "evaluated": True, "components": comp_out, "unknown_components": unknown,
                           "basic": basic, "mission": mission, "maintenance": maint, "availability": avail,
                           "notes": notes}

    # ---- frota
    fl = spec.get("fleet")
    # horas de voo da frota por dia {lo, hi} (procura de sobressalentes): surtidas/R × duração
    fleet_fh: tuple[float | None, float | None] | None = None
    if fl:
        out["fleet"] = fleet_mod.size(fl, A_o, mission["reliability"])
        if out["fleet"]["mode"] == "sorties":
            base = float(fl["sorties_per_day"]) * float(fl["sortie_duration_h"])
            if fl.get("abort_reflight", True) is False:
                fleet_fh = (base, base)
            else:
                r_lo, r_hi = mission["reliability"]["lo"], mission["reliability"]["hi"]
                fleet_fh = (None if not r_hi else base / r_hi, None if not r_lo else base / r_lo)
            if fh_day is None:
                for b in ("hi", "lo"):
                    cs = out["fleet"]["cases"].get(b) or {}
                    if cs.get("fh_per_aircraft_per_day"):
                        fh_day = float(cs["fh_per_aircraft_per_day"])
                        notes.append(f"utilização derivada da frota (caso {b}): {fh_day:.3g} FH/aeronave/dia")
                        break
    out["utilization_fh_per_aircraft_per_day"] = fh_day

    # ---- sobressalentes (Poisson, Eq. 5.58)
    sp = spec.get("spares") or {}
    fleet_n = _num(sp.get("fleet_size"))
    if fleet_n is None and out.get("fleet"):
        fleet_n = out["fleet"]["fleet"].get("hi")
    sp_out: dict[str, Any] = {}
    cost_lo = 0.0
    cost_hi: float | None = 0.0
    for c, cd in comps.items():
        s = {**sp, **(cd.get("spares") or {})}
        days, conf = _num(s.get("resupply_days")), _num(s.get("confidence"))
        if days is None or conf is None:
            continue
        if fleet_fh is not None:
            f_lo, f_hi = fleet_fh
        elif fleet_n is not None and fh_day is not None:
            f_lo = f_hi = float(fleet_n) * fh_day
        else:
            f_lo = f_hi = None
        if f_lo is None and f_hi is None:
            sp_out[c] = {"stock": _iv(None, None), "note": "horas de voo da frota por dia desconhecidas (frota ou "
                         "utilização)"}
            cost_hi = None
            continue
        ul, uh = unit[c]
        a_lo = None if (ul is None or f_lo is None) else ul * f_lo * days * mult[c]
        a_hi = None if (uh is None or f_hi is None) else uh * f_hi * days * mult[c]
        st = _iv(None if a_lo is None else stock_for(a_lo, conf), None if a_hi is None else stock_for(a_hi, conf))
        uc = _num(cd.get("replacement_cost"))
        cst = _iv(None if (uc is None or st["lo"] is None) else uc * st["lo"],
                  None if (uc is None or st["hi"] is None) else uc * st["hi"])
        cost_lo += cst["lo"] or 0.0
        cost_hi = None if (cost_hi is None or cst["hi"] is None) else cost_hi + cst["hi"]
        sp_out[c] = {"demand_mean": _iv(a_lo, a_hi), "stock": st, "cost": cst, "confidence": conf,
                     "resupply_days": days, "fleet_fh_per_day": _iv(f_lo, f_hi)}
    if sp_out:
        out["spares"] = {"by_component": sp_out, "total_cost": _iv(cost_lo, cost_hi),
                         "method": "Poisson P(X ≤ S) ≥ c (MIL-HDBK-338B Eq. 5.58, §5.3.8.1)"}

    # ---- custo de manutenção por FH e acoplamento ao custo operacional (Raymer 2018 Cap. 18; costing.py)
    parts_lo = 0.0
    parts_hi: float | None = 0.0
    for c, cd in comps.items():
        uc = _num(cd.get("replacement_cost"))
        ul = unit[c][0]
        if uc is None or ul is None:
            parts_hi = None
        if uc is not None and ul is not None:
            parts_lo += ul * mult[c] * uc
            if parts_hi is not None:
                parts_hi += float(unit[c][1] or 0.0) * mult[c] * uc
    for p in prev_out:
        if p["parts_cost"] is not None:
            if p["frequency_per_fh"] is None:
                parts_hi = None
            else:
                parts_lo += p["frequency_per_fh"] * p["parts_cost"]
                if parts_hi is not None:
                    parts_hi += p["frequency_per_fh"] * p["parts_cost"]
    oc = spec.get("operating_cost")
    rate = _num((oc or {}).get("maintenance_rate_per_h")) if oc else _num(spec.get("labour_rate_per_h"))
    if rate is None:
        rate = _num(spec.get("labour_rate_per_h"))
    mc: dict[str, Any] = {"parts_per_fh": _iv(parts_lo, parts_hi), "labour_rate_per_h": rate,
          "labour_per_fh": _iv(None if rate is None else rate * mmh_lo,
                               None if (rate is None or mmh_hi is None) else rate * mmh_hi)}
    mc["total_per_fh"] = _iv(None if mc["labour_per_fh"]["lo"] is None else mc["labour_per_fh"]["lo"] + parts_lo,
                             None if (mc["labour_per_fh"]["hi"] is None or parts_hi is None)
                             else mc["labour_per_fh"]["hi"] + parts_hi)
    out["maintenance_cost"] = mc
    if oc:
        out["operating_cost"] = operating_cost(oc, out)

    # ---- atalhos para requisitos / UQ / MDO (s para o registo de unidades)
    out["mission_reliability"] = mission["reliability"]
    out["mtbcf_s"] = {k: (None if v is None else v * 3600.0) for k, v in mission["mtbcf_h"].items()}
    out["mtbf_s"] = {k: (None if v is None else v * 3600.0) for k, v in basic["mtbf_h"].items()}
    out["operational_availability"] = A_o
    out["fleet_size"] = (out.get("fleet") or {}).get("fleet") or _iv(None, None)
    out["methods"] = {
        "rbd": f"{REF_338B}, Eq. 6.19–6.27, §7.5.5.1 (k-de-n), Eq. 5.57/5.73",
        "basic_vs_mission": f"{REF_338B}, §6.4.2–6.4.3 (fiabilidade básica vs de missão), Secção 3 (MTBCF)",
        "maintainability": f"{REF_338B}, Eq. 5.75 (M_ct), §10.4.1.1 (MTBM = 1/(λ+f)), Secção 3 (DMMH/MA)",
        "availability": f"{REF_338B}, Eq. 10.18, 10.21, 10.22",
        "spares": f"{REF_338B}, Eq. 5.58",
        "fleet": "acdt.core.concept.fleet_feedback (Ha 2010) ou balanço de surtidas",
        "operating_cost": "Raymer 2018 Cap. 18 (estrutura DOC) via manufacturing.costing.operating_cost",
    }
    return out


def operating_cost(block: Mapping[str, Any], rel: Mapping[str, Any]) -> dict[str, Any]:
    """Preenche a manutenção do custo operacional existente (majorantes de MMH/FH e peças/FH)."""
    from acdt.domains.aircraft.manufacturing.costing import operational_cost_from_dict

    d = dict(block)
    notes: list[str] = []
    mmh = rel["maintenance"]["mmh_per_fh"]["hi"]
    parts = rel["maintenance_cost"]["parts_per_fh"]["hi"]
    extra_unassessed: list[str] = []
    if mmh is not None:
        d["maintenance_mmh_per_fh"] = float(mmh)
        notes.append(f"maintenance_mmh_per_fh ← fiabilidade (majorante) {mmh:.4g}")
    else:
        d.pop("maintenance_mmh_per_fh", None)
        extra_unassessed.append("maintenance_mmh_per_fh (MMH/FH desconhecido na fiabilidade)")
    if parts is not None:
        d["maintenance_parts_per_fh"] = float(parts)
        notes.append(f"maintenance_parts_per_fh ← fiabilidade (majorante) {parts:.4g}")
    else:
        d.pop("maintenance_parts_per_fh", None)
        extra_unassessed.append("maintenance_parts_per_fh (custo de peças desconhecido na fiabilidade)")
    if d.get("flight_hours_per_year") is None and rel.get("utilization_fh_per_aircraft_per_day"):
        d["flight_hours_per_year"] = 365.0 * float(rel["utilization_fh_per_aircraft_per_day"])
        notes.append("flight_hours_per_year = 365 × FH/aeronave/dia (PRESSUPOSTO: operação todo o ano)")
    try:
        out = operational_cost_from_dict(d)
    except (TypeError, ValueError) as ex:
        return {"status": "unassessed", "per_flight_hour": None, "unassessed_terms": [str(ex)], "notes": notes}
    out["notes"] = list(out.get("notes") or []) + notes
    if extra_unassessed:
        out["unassessed_terms"] = list(out.get("unassessed_terms") or []) + extra_unassessed
        out["status"] = "partial" if out.get("items_per_fh") else "unassessed"
        out["per_flight_hour"] = None
        out["per_year"] = None
    return out


_ = math
