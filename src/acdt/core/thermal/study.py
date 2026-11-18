# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Análise térmica genérica dirigida por especificação (``acdt.api.thermal``; docs/TERMICA.md).

A mesma função serve qualquer tipo de aeronave: o domínio (ou o utilizador) dá as fontes de calor por condição,
os compartimentos, os componentes com limites de temperatura, as condições (atmosfera, altitude, velocidade, sol)
e o arrefecimento. Devolve temperaturas como intervalos, margens, dimensionamento de ar dinâmico e ventilador, e as
grandezas de acoplamento (arrasto, massa, potência elétrica de arrefecimento).
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .air import MIL310, SOLAR_HOT_DAY_W_M2, ambient
from .convection import INCROPERA, vertical_plate_natural
from .cooling import MOMENTUM_REF, NACA_MFR_DESIGN, NACA_RM_A8I29, fan_power, size_ram_duct
from .network import Bay, Bound, Condition, Phase, solve_bay_steady, solve_bay_transient
from .sources import HeatSource, from_spec, total

SCHEMA = "acdt.thermal/1"
METHODS = [INCROPERA + ": Eqs. 1.7, 5.5–5.7, 5.10, 7.30, 7.38, 8.53/8.55/8.60, 9.26, 9.30–9.32",
           "U.S. Standard Atmosphere 1976, Eqs. (51) e (53) (μ e k do ar)", MIL310, NACA_RM_A8I29, MOMENTUM_REF]


def _num(x: Any) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _source_for(sid: str, raw: Any, cond: str) -> HeatSource:
    if isinstance(raw, HeatSource):
        return raw
    if isinstance(raw, Mapping):
        method = str(raw.get("method", "declarado pelo utilizador"))
        v = raw.get("heat_W")
        if isinstance(v, Mapping):
            if cond in v:
                v = v[cond]
            elif "default" in v:
                v = v["default"]
            else:
                return HeatSource(sid, 0.0, None, method, [f"sem valor para a condição '{cond}': desconhecido"])
        if isinstance(v, HeatSource):
            return v
        return from_spec(sid, v, method)
    return from_spec(sid, raw)


def build_condition(c: Mapping[str, Any]) -> Condition:
    prof = str(c.get("atmosphere", "isa"))
    amb = ambient(prof, float(c.get("altitude_m", 0.0)), T_sl_C=_num(c.get("T_sl_C")))
    sol = c.get("solar_W_m2")
    if sol is None:
        sol = SOLAR_HOT_DAY_W_M2 if (c.get("case") == "hot" and c.get("sun", True)) else 0.0
    return Condition(str(c["name"]), amb, float(c.get("V_m_s", 0.0)), float(sol))


def build_bay(b: Mapping[str, Any]) -> Bay:
    A = float(b["skin_area_m2"])
    sun = _num(b.get("sun_area_m2"))
    notes = []
    if sun is None:
        sun = A / math.pi
        notes.append("PRESSUPOSTO: área exposta ao sol = A_pele/π (cilindro com o sol perpendicular ao eixo)")
    cap = _num(b.get("capacity_J_K"))
    if cap is None and _num(b.get("mass_kg")) is not None and _num(b.get("cp_J_kgK")) is not None:
        cap = float(b["mass_kg"]) * float(b["cp_J_kgK"])
    return Bay(str(b["id"]), A, float(b.get("flow_length_m") or math.sqrt(A)), float(b.get("height_m") or 0.2),
               Bound.of(b.get("eps_ext"), 0.0, 1.0, "emissividade exterior"),
               Bound.of(b.get("alpha_solar"), 0.0, 1.0, "absortividade solar"), float(sun),
               Bound.of(b.get("eps_int"), 0.0, 1.0, "emissividade interna"), _num(b.get("wall_U_W_m2K")), cap, 0.0,
               notes)


def _iv(lo: float | None, hi: float | None) -> dict[str, float | None]:
    return {"lo": lo, "hi": hi}


def _C(T: float | None) -> float | None:
    return None if T is None else T - 273.15


def _comp_conductance(comp: Mapping[str, Any], T_b: float, Q: float, p: float) -> float | None:
    G = _num(comp.get("conductance_W_K"))
    if G is not None:
        return G
    A = _num(comp.get("case_area_m2"))
    if A is None or A <= 0:
        return None
    L = math.sqrt(A)
    T_c = T_b + 5.0
    for _ in range(30):  # convecção natural na caixa (Eq. 9.26, L = √A; PRESSUPOSTO), ponto fixo em T_c
        h = vertical_plate_natural(L, max(T_c, T_b + 1e-3), T_b, p).h
        T_new = T_b + Q / (h * A)
        if abs(T_new - T_c) < 1e-4:
            break
        T_c = T_new
    return h * A


def analyse(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Corre a análise térmica completa de ``spec`` (ver docs/TERMICA.md, «Especificação genérica»)."""
    conds_raw: Sequence[Mapping[str, Any]] = spec.get("conditions") or []
    if not conds_raw:
        raise ValueError("thermal: sem condições")
    conds = {str(c["name"]): (build_condition(c), str(c.get("case", "hot"))) for c in conds_raw}
    sources_raw: Mapping[str, Any] = spec.get("sources") or {}
    ref = spec.get("reference") or {}
    out_bays: dict[str, Any] = {}
    comps_out: dict[str, Any] = {}
    hot_m: list[tuple[float | None, float | None]] = []
    cold_m: list[tuple[float | None, float | None]] = []
    drag_lo = drag_hi = 0.0
    drag_known = True
    mass_total: float | None = 0.0
    fan_P: dict[str, float | None] = {}
    notes: list[str] = []
    complete = True
    for b in spec.get("bays") or []:
        bay = build_bay(b)
        bid = bay.id
        comps = list(b.get("components") or [])
        sids = list(b.get("sources") or [])
        ram = b.get("ram_air") or None
        fan = b.get("fan") or None

        def bay_heat(cn: str) -> tuple[float, float | None, list[dict[str, Any]]]:
            hs = [_source_for(sid, sources_raw.get(sid), cn) for sid in sids]
            hs += [_source_for(str(c["id"]), {"heat_W": c.get("heat_W")}, cn) for c in comps
                   if c.get("source") is None and c.get("heat_W") is not None]
            lo, hi = total(hs)
            return lo, hi, [h.to_dict() for h in hs]

        def comp_heat(c: Mapping[str, Any], cn: str) -> HeatSource:
            if c.get("source") is not None:
                return _source_for(str(c["source"]), sources_raw.get(str(c["source"])), cn)
            return _source_for(str(c["id"]), {"heat_W": c.get("heat_W", 0.0)}, cn)

        # ---- ar dinâmico: área dada ou dimensionada na condição pedida
        bres: dict[str, Any] = {"id": bid, "notes": list(bay.notes), "conditions": {}, "cooling": {}}
        A_in = _num((ram or {}).get("inlet_area_m2"))
        mfr = float((ram or {}).get("mass_flow_ratio", NACA_MFR_DESIGN))
        if ram is not None and A_in is None and ram.get("size_for"):
            cn = str(ram["size_for"])
            cond, _case = conds[cn]
            _lo, Qhi, _d = bay_heat(cn)
            lims: list[float | None] = []
            for c in comps:
                tmax = _num(c.get("T_max_C"))
                if tmax is None:
                    continue
                qc = comp_heat(c, cn)
                G = _comp_conductance(c, tmax + 273.15, qc.hi or 0.0, cond.ambient.p_Pa) if qc.hi else math.inf
                if qc.hi is None or G is None:
                    lims.append(None)
                else:
                    lims.append(tmax + 273.15 - (qc.hi / G if G and math.isfinite(G) else 0.0))
            if _num(b.get("air_T_max_C")) is not None:
                lims.append(float(b["air_T_max_C"]) + 273.15)
            if Qhi is None or not lims or any(x is None for x in lims):
                bres["cooling"]["ram_sizing"] = {"status": "desconhecido",
                                                 "reason": "calor máximo ou limite de componente desconhecido"}
                complete = False
            else:
                T_lim = min(x for x in lims if x is not None)
                from .air import ram_temperature
                d = size_ram_duct(Qhi, T_lim, ram_temperature(cond.ambient.T_K, cond.V_m_s), cond.ambient.rho,
                                  cond.V_m_s, mfr=mfr, ram_recovery=_num(ram.get("ram_recovery")),
                                  duct_loss_q=_num(ram.get("duct_loss_q")),
                                  duct_length_m=_num((ram.get("duct") or {}).get("length_m")),
                                  areal_density_kg_m2=_num((ram.get("duct") or {}).get("areal_density_kg_m2")),
                                  fixed_mass_kg=float(ram.get("hx_mass_kg", 0.0) or 0.0))
                bres["cooling"]["ram_sizing"] = {"condition": cn, "T_limit_air_C": T_lim - 273.15,
                                                 "Q_W": Qhi, **d.to_dict(),
                                                 "note": "PRESSUPOSTO: todo o calor sai pelo ar (pele ignorada; "
                                                         "conservativo)"}
                A_in = d.inlet_area_m2
        if ram is not None:
            bres["cooling"]["inlet_area_m2"] = A_in
            bres["cooling"]["mass_flow_ratio"] = mfr

        fan_conds = set((fan or {}).get("conditions") or [n for n, (c, _k) in conds.items() if c.V_m_s <= 0.5])
        for cn, (cond, case) in conds.items():
            m_ram = mfr * cond.ambient.rho * cond.V_m_s * A_in if (A_in and cond.V_m_s > 0.5) else 0.0
            m_fan = float((fan or {}).get("mass_flow_kg_s", 0.0) or 0.0) if (fan and cn in fan_conds) else 0.0
            bay.vent_m_dot_kg_s = m_ram + m_fan
            Qlo, Qhi, det = bay_heat(cn)
            hot = solve_bay_steady(bay, cond, Qhi, hot=True) if Qhi is not None else None
            cold = solve_bay_steady(bay, cond, Qlo, hot=False)
            if Qhi is None:
                complete = False
            cres: dict[str, Any] = {
                "case": case, "ambient": {"profile": cond.ambient.profile, "T_C": cond.ambient.T_C,
                                          "p_Pa": cond.ambient.p_Pa, "rho": cond.ambient.rho,
                                          "altitude_m": cond.ambient.altitude_m, "source": cond.ambient.source},
                "V_m_s": cond.V_m_s, "solar_W_m2": cond.solar_W_m2, "Q_W": _iv(Qlo, Qhi), "sources": det,
                "vent_m_dot_kg_s": bay.vent_m_dot_kg_s,
                "T_bay_C": _iv(_C(cold.T_bay_K), _C(hot.T_bay_K if hot else None)),
                "T_skin_C": _iv(_C(cold.T_skin_K), _C(hot.T_skin_K if hot else None)),
                "h_ext_W_m2K": _iv(hot.h_ext if hot else None, cold.h_ext),
                "correlations": (hot or cold).correlations, "warnings": sorted(set(cold.warnings + (hot.warnings
                                                                                                  if hot else [])))}
            if fan and cn in fan_conds:
                P = fan_power(m_fan, cond.ambient.rho, _num(fan.get("pressure_rise_Pa")), _num(fan.get("efficiency")))
                cres["fan_power_W"] = P
                prev = fan_P.get(cn, 0.0)
                fan_P[cn] = None if (P is None or prev is None) else prev + P
            ccomp = {}
            for c in comps:
                cid = str(c["id"])
                qc = comp_heat(c, cn)
                Th = None
                if hot is not None and qc.hi is not None:
                    if qc.hi <= 0:
                        Th = hot.T_bay_K
                    else:
                        G = _comp_conductance(c, hot.T_bay_K, qc.hi, cond.ambient.p_Pa)
                        Th = None if G is None else hot.T_bay_K + qc.hi / G
                if qc.lo <= 0:
                    Tl = cold.T_bay_K
                else:
                    G2 = _comp_conductance(c, cold.T_bay_K, qc.lo, cond.ambient.p_Pa)
                    Tl = cold.T_bay_K if G2 is None else cold.T_bay_K + qc.lo / G2
                tmax, tmin = _num(c.get("T_max_C")), _num(c.get("T_min_C"))
                hm = None if tmax is None else (None if Th is None else tmax - _C(Th),  # type: ignore[operator]
                                               tmax - (Tl - 273.15))
                cm = None if tmin is None else ((Tl - 273.15) - tmin, None if Th is None else _C(Th) - tmin)  # type: ignore[operator]
                ccomp[cid] = {"T_C": _iv(_C(Tl), _C(Th)), "Q_W": _iv(qc.lo, qc.hi),
                              "hot_margin_C": None if hm is None else _iv(*hm),
                              "cold_margin_C": None if cm is None else _iv(*cm),
                              "note": "" if Th is not None or hot is None else
                              "sem condutância componente→ar (conductance_W_K ou case_area_m2): T ≥ T_compartimento, "
                              "majorante desconhecido"}
                if hm is not None:
                    hot_m.append(hm)
                if cm is not None:
                    cold_m.append(cm)
                cagg = comps_out.setdefault(cid, {"bay": bid, "T_max_C": tmax, "T_min_C": tmin,
                                                 "limit_source": c.get("limit_source"), "by_condition": {}})
                cagg["by_condition"][cn] = ccomp[cid]
            if _num(b.get("air_T_max_C")) is not None:
                tm = float(b["air_T_max_C"])
                hm2 = (None if hot is None else tm - _C(hot.T_bay_K), tm - (cold.T_bay_K - 273.15))  # type: ignore[operator]
                hot_m.append(hm2)
                cres["air_hot_margin_C"] = _iv(*hm2)
            cres["components"] = ccomp
            bres["conditions"][cn] = cres
        # ---- arrasto e massa de arrefecimento na condição de referência (cruzeiro)
        rc = str(ref.get("cruise_condition", "")) or next(iter(conds))
        if ram is not None and A_in and rc in conds:
            cond, _ = conds[rc]
            m = mfr * cond.ambient.rho * cond.V_m_s * A_in
            zeta = None
            if _num(ram.get("ram_recovery")) is not None and _num(ram.get("duct_loss_q")) is not None:
                zeta = (1.0 - float(ram["ram_recovery"])) + float(ram["duct_loss_q"])
            from .cooling import internal_drag
            dlo, dhi, Ve = internal_drag(m, cond.V_m_s, zeta)
            ext = _num(ram.get("external_drag_N"))
            if ext is not None:
                dlo += ext
                dhi += ext
            q = 0.5 * cond.ambient.rho * cond.V_m_s ** 2
            bres["cooling"]["cruise"] = {"condition": rc, "m_dot_kg_s": m, "drag_N": _iv(dlo, dhi),
                                         "drag_area_m2": _iv(dlo / q, dhi / q), "zeta": zeta, "exit_V_m_s": Ve,
                                         "external_drag_included": ext is not None}
            drag_lo += dlo
            drag_hi += dhi
            if zeta is None:
                drag_known = False
            import math as _m
            dm = (ram.get("duct") or {})
            if _num(dm.get("length_m")) is not None and _num(dm.get("areal_density_kg_m2")) is not None:
                mk = 2.0 * _m.sqrt(_m.pi * A_in) * float(dm["length_m"]) * float(dm["areal_density_kg_m2"]) \
                    + float(ram.get("hx_mass_kg", 0.0) or 0.0)
            else:
                mk = None
            bres["cooling"]["mass_kg"] = mk
            mass_total = None if (mass_total is None or mk is None) else mass_total + mk
        if fan:
            fm = _num(fan.get("mass_kg"))
            mass_total = None if (mass_total is None or fm is None) else mass_total + fm
        # ---- transitório
        tr = spec.get("transient") or {}
        if tr.get("phases"):
            if bay.capacity_J_K:
                def phases(hotcase: bool) -> list[Phase] | None:
                    out: list[Phase] = []
                    for ph in tr["phases"]:
                        cn = str(ph["condition"])
                        cond, _ = conds[cn]
                        lo, hi, _d = bay_heat(cn)
                        Q = hi if hotcase else lo
                        if Q is None:
                            return None
                        m_ram = mfr * cond.ambient.rho * cond.V_m_s * A_in if (A_in and cond.V_m_s > 0.5) else 0.0
                        m_fan = float((fan or {}).get("mass_flow_kg_s", 0.0) or 0.0) if (fan and cn in fan_conds) \
                            else 0.0
                        out.append(Phase(cond, float(ph["duration_s"]), Q, m_ram + m_fan))
                    return out
                first = conds[str(tr["phases"][0]["condition"])][0]
                T0 = _num(tr.get("T0_C"))
                T0K = first.ambient.T_K if T0 is None else T0 + 273.15
                ph_hot, ph_cold = phases(True), phases(False)
                th = solve_bay_transient(bay, ph_hot, T0K, hot=True) if ph_hot else None
                tc = solve_bay_transient(bay, ph_cold, T0K, hot=False) if ph_cold else None
                bres["transient"] = {
                    "T0_C": T0K - 273.15, "capacity_J_K": bay.capacity_J_K,
                    "T_bay_max_C": _iv(None if tc is None else _C(tc["T_max_K"]),
                                       None if th is None else _C(th["T_max_K"])),
                    "T_bay_min_C": _iv(None if tc is None else _C(tc["T_min_K"]),
                                       None if th is None else _C(th["T_min_K"])),
                    "phase_at_max": None if th is None else th["phase_at_max"],
                    "history_hot": None if th is None else {"t_s": th["t_s"], "T_C": [x - 273.15 for x in th["T_K"]]},
                    "method": "capacidade concentrada (Incropera §5.3), RK45"}
            else:
                bres["transient"] = {"status": "desconhecido",
                                     "reason": "sem capacidade térmica (capacity_J_K ou mass_kg + cp_J_kgK)"}
        out_bays[bid] = bres

    def agg(ms: list[tuple[float | None, float | None]]) -> dict[str, float | None] | None:
        if not ms:
            return None
        los = [m[0] for m in ms]
        lo = None if any(x is None for x in los) else min(x for x in los if x is not None)
        his = [m[1] for m in ms if m[1] is not None]
        hi = min(his) if len(his) == len(ms) else (min(his) if his else None)
        return _iv(lo, hi)

    hot_agg = agg(hot_m)
    cold_agg = agg(cold_m)
    S = _num(ref.get("S_ref_m2"))
    rc = str(ref.get("cruise_condition", "")) or next(iter(conds))
    q_ref = None
    if rc in conds:
        cnd = conds[rc][0]
        q_ref = 0.5 * cnd.ambient.rho * cnd.V_m_s ** 2
    cooling = {"drag_N": _iv(drag_lo, drag_hi if drag_known else drag_hi), "drag_known": drag_known,
               "drag_area_m2": None if not q_ref else _iv(drag_lo / q_ref, drag_hi / q_ref),
               "delta_CD0": None if not (q_ref and S) else _iv(drag_lo / (q_ref * S), drag_hi / (q_ref * S)),
               "mass_kg": mass_total, "fan_power_W": fan_P,
               "fan_power_max_W": (None if any(v is None for v in fan_P.values())
                                   else max((float(v) for v in fan_P.values() if v is not None), default=0.0))}
    if not drag_known:
        notes.append("arrasto de arrefecimento é um intervalo [0, ṁV] (perdas de pressão não declaradas)")
    if not complete:
        notes.append("há fontes de calor sem majorante: temperaturas máximas desconhecidas onde indicado")
    return {"schema": SCHEMA, "methods": METHODS, "complete": complete, "bays": out_bays, "components": comps_out,
            "hot_margin_C": hot_agg, "cold_margin_C": cold_agg,
            "hot_margin_min_C": None if hot_agg is None else hot_agg["lo"],
            "cold_margin_min_C": None if cold_agg is None else cold_agg["lo"],
            "cooling": cooling, "notes": notes}
