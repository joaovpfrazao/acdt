# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Adaptadores nativos das disciplinas para VTOL, jato e asa fixa.

A térmica, o gelo, o ruído, a fiabilidade, o custo de série e o ciclo de vida já aceitam uma
especificação genérica na API. Este módulo constrói essa especificação a partir do resultado
nativo (``size_vtol`` / ``size_jet``) e faz a carga útil e a arquitetura elétrica entrarem nos
três tipos. O que não está no resultado fica por avaliar: não é zero e não é um passa.

A massa do equipamento não é somada a ``mass_kg`` / ``payload_kg`` / W0. Esses campos já são a
massa fechada pelo dimensionamento; somar outra vez seria contá-la duas vezes. A potência
elétrica é que entra no hotel, no calor e na energia.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

DISC_KEYS = ("payload_equipment", "electrical", "thermal", "icing", "noise", "reliability",
             "series_cost", "life_cycle")


def _num(x: Any) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def container_of(obj: Any) -> Mapping[str, Any]:
    """Bloco onde estão ``payload_equipment`` e ``electrical``: o spec (VTOL/jato) ou ``assumptions``."""
    if isinstance(obj, Mapping):
        return obj
    assumptions = getattr(obj, "assumptions", None)
    if isinstance(assumptions, Mapping):
        return assumptions
    return {}


def _items(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, Mapping):
        rows = list(raw.get("items") or [])
    else:
        return []
    out = []
    for i, row in enumerate(rows):
        if isinstance(row, Mapping):
            item = dict(row)
            item.setdefault("id", f"payload_{i + 1}")
            out.append(item)
    return out


def _blank(present: bool = False) -> dict[str, Any]:
    return {"present": present, "mode": None, "P_avg_W": None, "P_peak_W": None, "source": "",
            "reason": "", "pressupostos": [], "distribution_heat_W": None, "distribution_method": "",
            "items": [], "generators": [], "example_catalog": False, "mass_kg": None,
            "mass_complete": True, "unit_cost_USD": None, "cost_complete": True,
            "coupled_to_mass": False,
            "mass_note": "a massa do equipamento não entra no fecho: mass_kg / payload_kg / W0 já são a massa "
                         "dimensionada"}


def equipment_effect(obj: Any) -> dict[str, Any]:
    """Potência, calor de distribuição, massa e custo da carga útil e da arquitetura elétrica.

    Sem bloco → ``present`` falso e o hotel existente não muda. Com bloco, uma potência em falta
    torna a média desconhecida (não a soma dos outros). ``distribution_eta`` em falta torna o calor
    das perdas desconhecido. Fonte ``EXAMPLE`` continua a entrar no número e fica marcada: não é
    uma ficha de fornecedor.
    """
    box = container_of(obj)
    payload = box.get("payload_equipment")
    electrical = box.get("electrical")
    items = _items(payload)
    if not items and not isinstance(electrical, Mapping):
        return _blank(False)
    out = _blank(True)
    out["items"] = items
    notes: list[str] = []
    names_in_arch: set[str] = set()
    p_arch: float | None = None
    peak_arch: float | None = None
    if isinstance(electrical, Mapping):
        out["mode"] = "architecture"
        try:
            from acdt.ai.systems_p4 import electrical_analyse
            arch = electrical_analyse(dict(electrical))
        except Exception as ex:  # noqa: BLE001 — a arquitetura não fecha: a potência fica desconhecida
            out["P_avg_W"] = None
            out["reason"] = f"arquitetura elétrica não avaliada: {type(ex).__name__}: {ex}"
            out["source"] = out["reason"]
            return out
        p_arch = float(arch["P_avg_W"])
        peak_arch = float(arch["P_peak_W"])
        names_in_arch = {str(row.get("load") or row.get("name")) for row in (arch.get("loads") or [])}
        out["electrical"] = {"id": arch.get("id"), "P_avg_W": p_arch, "P_peak_W": peak_arch,
                             "reference": arch.get("reference"), "ok": arch.get("ok"),
                             "reasons": arch.get("reasons")}
        gens = list(electrical.get("generation") or [])
        bats = list(electrical.get("batteries") or [])
        for gid in electrical.get("generation_ids") or []:
            gens.append({"id": str(gid), "catalog_id": True})
        for bid in electrical.get("battery_ids") or []:
            bats.append({"id": str(bid), "catalog_id": True})
        out["generators"] = gens + bats
        notes.append("MIL-E-7016F / Moir & Seabridge Cap. 5, via electrical_analyse")
    else:
        out["mode"] = "payload"

    extra = 0.0
    extra_peak: float | None = 0.0
    unknown = False
    for it in items:
        if str(it["id"]) in names_in_arch:
            notes.append(f"{it['id']}: já está nas cargas da arquitetura; não é somado outra vez")
            continue
        p = _num(it.get("power_w_avg"))
        if p is None:
            unknown = True
            notes.append(f"{it['id']}: power_w_avg em falta (não é 0 W)")
            extra_peak = None
            continue
        duty = _num(it.get("duty"))
        if duty is None:
            duty = 1.0
            notes.append(f"{it['id']}: duty 1 (PRESSUPOSTO: funciona durante todo o voo)")
            out["pressupostos"].append(f"{it['id']}.duty = 1")
        extra += p * duty
        pk = _num(it.get("power_w_peak"))
        if pk is None or extra_peak is None:
            extra_peak = None
        else:
            extra_peak += pk
    if unknown:
        out["P_avg_W"] = None
        out["P_peak_W"] = None
        out["reason"] = "potência da carga útil incompleta: a média não é a soma dos itens conhecidos"
    elif out["mode"] == "architecture":
        out["P_avg_W"] = float(p_arch or 0.0) + extra
        out["P_peak_W"] = None if peak_arch is None or extra_peak is None else float(peak_arch) + extra_peak
    else:
        out["P_avg_W"] = extra
        out["P_peak_W"] = extra_peak
    out["example_catalog"] = any(str(it.get("source") or "").strip().upper() == "EXAMPLE" for it in items) or any(
        str(g.get("source") or "").strip().upper() == "EXAMPLE" or g.get("catalog_id") for g in out["generators"]) or (
            isinstance(electrical, Mapping) and bool(electrical.get("payload_ids")))
    if out["example_catalog"]:
        notes.append("há fonte EXAMPLE: o número entra no cálculo e não é ficha de fornecedor (nao_avaliado)")

    # perdas de distribuição: só com η declarado; sem η o calor extra fica desconhecido
    if isinstance(electrical, Mapping):
        eta = _num(electrical.get("distribution_eta"))
        p = out["P_avg_W"]
        if eta is None:
            out["distribution_heat_W"] = None if p is None else [p * 0.0, None]
            # lo 0 só como minorante físico de uma perda (não pode ser negativa); hi desconhecido
            if p is not None:
                out["distribution_heat_W"] = [0.0, None]
            out["distribution_method"] = ("perda de distribuição desconhecida: electrical.distribution_eta não "
                                          "declarado (não é η = 1)")
        elif not 0.0 < eta <= 1.0:
            out["distribution_heat_W"] = [0.0, None]
            out["distribution_method"] = f"distribution_eta = {eta} fora de ]0, 1]: calor desconhecido"
        elif p is None:
            out["distribution_heat_W"] = [0.0, None]
            out["distribution_method"] = "η de distribuição declarado, potência da carga desconhecida"
        else:
            q = p * (1.0 / eta - 1.0)
            out["distribution_heat_W"] = [q, q]
            out["distribution_method"] = (f"perda = P·(1/η − 1), η = {eta} (conservação de energia na "
                                          "distribuição; η declarado)")
        notes.append(out["distribution_method"])

    masses = []
    costs = []
    mass_ok, cost_ok = True, True
    for it in items + out["generators"]:
        m = _num(it.get("mass_kg"))
        if m is None:
            mass_ok = False
        else:
            masses.append(m)
        c = _num(it.get("unit_cost_USD"))
        if c is None:
            cost_ok = False
        else:
            costs.append(c)
        if str(it.get("source") or "").strip() == "" and (_num(it.get("power_w_avg")) is not None
                                                           or _num(it.get("power_w_cont")) is not None):
            notes.append(f"{it.get('id') or it.get('name')}: potência sem source (valor declarado no spec)")
    out["mass_kg"] = sum(masses) if masses else None
    out["mass_complete"] = mass_ok
    out["unit_cost_USD"] = sum(costs) if costs else None
    out["cost_complete"] = cost_ok
    if not mass_ok:
        notes.append("massa incompleta: não é a soma dos itens com massa")
    if not cost_ok:
        notes.append("custo unitário incompleto: o custo de série fica só com minorante")
    out["source"] = "; ".join(notes)
    if out["P_avg_W"] is None and not out["reason"]:
        out["reason"] = out["source"]
    return out


def distribution_source(obj: Any) -> dict[str, Any]:
    """Fonte térmica ``perdas_distribuicao``, ou vazio se não há arquitetura elétrica."""
    eq = equipment_effect(obj)
    if not eq["present"] or eq["mode"] != "architecture":
        return {}
    heat = eq["distribution_heat_W"]
    if heat is None:
        heat_w: Any = None
    elif heat[0] == heat[1]:
        heat_w = heat[0]
    else:
        heat_w = heat
    return {"perdas_distribuicao": {"heat_W": heat_w, "method": eq["distribution_method"]}}


def equipment_components(obj: Any) -> list[dict[str, Any]]:
    """Componentes para o RBD. Sem λ e sem fonte a taxa fica desconhecida (o estudo abre o intervalo)."""
    eq = equipment_effect(obj)
    if not eq["present"]:
        return []
    rows = []
    seen: set[str] = set()
    box = container_of(obj)
    declared = box.get("reliability") if isinstance(box.get("reliability"), Mapping) else {}
    for c in (declared or {}).get("components") or []:
        if isinstance(c, Mapping) and c.get("id"):
            seen.add(str(c["id"]))
    for it in eq["items"]:
        cid = "payload:" + str(it["id"])
        if cid in seen:
            continue
        rows.append(_rate_row(cid, it))
    for g in eq["generators"]:
        cid = "eletrica:" + str(g.get("id") or g.get("name") or "fonte")
        if cid in seen:
            continue
        rows.append(_rate_row(cid, g))
        seen.add(cid)
    return rows


def _rate_row(cid: str, it: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"id": cid, "critical": True}
    src = str(it.get("source") or "").strip()
    if it.get("lambda_per_h") is not None and src and src.upper() != "EXAMPLE":
        row["lambda_per_h"] = it["lambda_per_h"]
        row["source"] = src
    elif it.get("mtbf_h") is not None and src and src.upper() != "EXAMPLE":
        row["mtbf_h"] = it["mtbf_h"]
        row["source"] = src
    else:
        row["note"] = "sem λ com fonte (EXAMPLE não é fonte): a taxa fica desconhecida"
    return row


def fold_series_cost(out: dict[str, Any], obj: Any) -> None:
    """Soma o custo declarado do equipamento. Custo em falta → o total fica só com minorante."""
    eq = equipment_effect(obj)
    if not eq["present"]:
        return
    out.setdefault("adapter_notes", [])
    if not eq["cost_complete"] or eq["unit_cost_USD"] is None:
        out["adapter_notes"].append("custo do equipamento desconhecido: o custo de série é minorante")
        out["payload_equipment_USD"] = {"lo": None, "hi": None}
        for k in ("average_unit_cost_USD", "flyaway_cost_USD", "unit_cost_at_quantity_USD"):
            v = out.get(k)
            if isinstance(v, (int, float)):
                out[k] = {"lo": v, "hi": None}
        return
    add = float(eq["unit_cost_USD"])
    out["payload_equipment_USD"] = add
    out["adapter_notes"].append(f"custo do equipamento {add} USD/aeronave somado ao unitário (declarado)")
    for k in ("average_unit_cost_USD", "flyaway_cost_USD", "unit_cost_at_quantity_USD"):
        v = out.get(k)
        if isinstance(v, (int, float)):
            out[k] = v + add


def fold_life_cycle_energy(espec: dict[str, Any], notes: list[str], obj: Any, kind: str) -> None:
    """Energia elétrica do equipamento na hora de voo. Em motor térmico não há extração: fica por avaliar."""
    eq = equipment_effect(obj)
    if not eq["present"]:
        return
    if eq["P_avg_W"] is None:
        notes.append("potência do equipamento desconhecida: a energia por FH não a inclui (não é zero)")
        espec["equipment_unaccounted"] = True
        return
    if kind != "electric":
        notes.append("potência elétrica do equipamento não entra no combustível: sem modelo de extração "
                     "(desconhecido, não é zero)")
        espec["equipment_unaccounted"] = True
        return
    extra = float(eq["P_avg_W"]) / 1000.0
    base = espec.get("battery_kWh_per_fh")
    if base is None:
        espec["battery_kWh_per_fh"] = extra
        notes.append(f"energia/FH = equipamento {extra} kWh (PRESSUPOSTO: ciclo 1 durante a hora de voo)")
    else:
        espec["battery_kWh_per_fh"] = float(base) + extra
        notes.append(f"energia/FH += equipamento {extra} kWh (PRESSUPOSTO: ciclo 1)")
    espec["equipment_kWh_per_fh"] = extra


def open_unaccounted(out: dict[str, Any], espec: Mapping[str, Any]) -> None:
    if not espec.get("equipment_unaccounted"):
        return
    for k in ("co2e_per_flight_hour_kg", "life_cycle_co2e_kg"):
        v = out.get(k)
        if isinstance(v, Mapping):
            out[k] = {"lo": v.get("lo"), "hi": None}


def _status(evaluated: bool, reason: str, *, verdict: str | None = None, **rest: Any) -> dict[str, Any]:
    ver = verdict or ("validado" if evaluated else "nao_avaliado")
    body = {"evaluated": evaluated, "veredicto": ver, "calibracao_L1_L2": "nao_aplicar", "reason": reason}
    body.update(rest)
    return body


def _thermal_native(kind: str, result: Mapping[str, Any], spec: Mapping[str, Any], eq: Mapping[str, Any]) -> dict[str, Any]:
    from acdt.core.thermal.sources import electric_chain, electrical_load

    block = dict(spec.get("thermal") or {})
    bays = block.get("bays")
    if not bays:
        return _status(False, "sem thermal.bays: o resultado nativo não traz a fuselagem; a área não é inventada")
    conds: list[dict[str, Any]] = []
    powers: dict[str, float] = {}
    skipped: list[str] = []
    if kind == "vtol":
        v_of = {"hover": 0.0, "vertical_climb": None, "cruise": None, "loiter": None}
        mission = (result.get("inputs_resolved") or {}).get("mission") or {}
        v_of["vertical_climb"] = _num(mission.get("climb_rate_m_s")) or 0.0
        v_cruise = _num((result.get("cruise") or {}).get("V_m_s"))
        v_of["cruise"] = v_cruise
        v_of["loiter"] = v_cruise
        for seg in result.get("segments") or []:
            name = str(seg.get("segment"))
            if name == "transition":
                skipped.append("transition: velocidade única desconhecida (o envelope não é um ponto)")
                continue
            v = v_of.get(name)
            if v is None:
                skipped.append(f"{name}: velocidade desconhecida")
                continue
            conds.append({"name": name, "case": "hot", "atmosphere": str(block.get("hot_atmosphere") or "isa"),
                          "altitude_m": float(block.get("altitude_m") or 0.0), "V_m_s": float(v),
                          "solar_W_m2": block.get("solar_W_m2")})
            powers[name] = float(seg.get("P_elec_W") or 0.0)
    else:
        cruise = result.get("cruise") or {}
        v = _num(cruise.get("speed_tas_m_s"))
        if not result.get("converged") or v is None:
            return _status(False, "jato sem cruzeiro convergido: a condição térmica não é inventada")
        conds.append({"name": "cruzeiro", "case": "hot", "atmosphere": str(block.get("hot_atmosphere") or "isa"),
                      "altitude_m": float(spec.get("altitude_m") or 0.0), "V_m_s": v,
                      "solar_W_m2": block.get("solar_W_m2")})
        skipped.append("subida: o fecho L0 do jato não tem segmento de subida")
        powers["cruzeiro"] = 0.0
    if not conds:
        return _status(False, "sem condição com velocidade conhecida")
    declared = 0.0
    declared_src = "sem hotel elétrico declarado"
    if kind == "vtol":
        declared = float(((result.get("inputs_resolved") or {}).get("electric") or {}).get("systems_power_W") or 0.0)
        declared_src = "electric.systems_power_W"
    if not eq["present"]:
        p_hot, p_src = declared, declared_src
    elif eq["P_avg_W"] is None:
        p_hot, p_src = None, str(eq["reason"] or eq["source"])
    elif eq["mode"] == "architecture":
        p_hot, p_src = max(declared, float(eq["P_avg_W"])), str(eq["source"])
    else:
        p_hot, p_src = declared + float(eq["P_avg_W"]), declared_src + " + " + str(eq["source"])
    srcs: dict[str, Any] = {}
    if p_hot is None:
        srcs["avionica"] = {"heat_W": None, "method": p_src}
    else:
        srcs["avionica"] = {"heat_W": electrical_load(
            "avionica", float(p_hot), float(block.get("radiated_fraction") or 0.0), p_src).to_dict()["lo_W"],
            "method": p_src}
    if eq["mode"] == "architecture":
        srcs.update(distribution_source(spec))
    if kind == "vtol" and powers:
        eta = float(result.get("eta_chain") or 0.0)
        e = (result.get("inputs_resolved") or {}).get("electric") or {}
        per: dict[str, dict[str, Any]] = {}
        if 0.0 < eta <= 1.0:
            for cn, pb in powers.items():
                chain = electric_chain(pb, eta, eta_esc=_num(e.get("eta_esc")), eta_motor=_num(e.get("eta_motor")))
                per[cn] = chain
            for comp in ("bateria", "esc", "motor"):
                srcs[comp] = {"heat_W": {cn: [per[cn][comp].lo, per[cn][comp].hi] for cn in per},
                              "method": per[next(iter(per))][comp].method}
        else:
            skipped.append("cadeia elétrica: η fora de ]0, 1]")
    if kind == "jet":
        eng = block.get("engine") or {}
        q = _num(eng.get("heat_rejection_W"))
        srcs["motor_termico"] = {"heat_W": None if q is None else q,
                                 "method": "calor do turbofan só se thermal.engine.heat_rejection_W estiver declarado; "
                                           "Heywood Cap. 12 não é aplicado ao jato"}
        if q is None:
            skipped.append("calor do motor do jato desconhecido (heat_rejection_W não declarado)")
    bays_out = []
    for b in bays:
        if not isinstance(b, Mapping):
            continue
        bay = dict(b)
        have = [str(s) for s in (bay.get("sources") or [])]
        for sid in srcs:
            if sid not in have:
                have.append(sid)
        bay["sources"] = have
        bays_out.append(bay)
    flying = [c["name"] for c in conds if float(c["V_m_s"]) > 0.5]
    spec_th = {"conditions": conds, "sources": srcs, "bays": bays_out,
               "reference": {"cruise_condition": flying[0] if flying else conds[0]["name"]}}
    if block.get("transient"):
        spec_th["transient"] = block["transient"]
    try:
        from acdt.core.thermal.study import analyse
        th = analyse(spec_th)
    except Exception as ex:  # noqa: BLE001
        return _status(False, f"térmica falhou: {type(ex).__name__}: {ex}", skipped=skipped)
    # o calor da aviónica no dict pode ter ficado número; o estudo devolve intervalos.
    # η de distribuição em falta deixa o calor em [0, desconhecido]: o estudo corre, mas não fecha.
    partial = bool(skipped) or p_hot is None
    dist = (srcs.get("perdas_distribuicao") or {}).get("heat_W")
    if isinstance(dist, (list, tuple)) and (len(dist) < 2 or dist[1] is None):
        partial = True
        note = "perdas de distribuição com limite superior desconhecido"
        if note not in skipped:
            skipped.append(note)
    return _status(True, "" if not partial else "; ".join(skipped) or str(p_src),
                   verdict="nao_avaliado" if partial else "validado", mission_complete=not partial,
                   skipped=skipped, result=th, operating_conditions=[c["name"] for c in conds])


def _icing_native(kind: str, result: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    block = dict(spec.get("icing") or {})
    surfaces = list(block.get("surfaces") or [])
    notes = []
    if not surfaces and kind == "jet":
        tc = _num((spec.get("wave") or {}).get("thickness_ratio"))
        s = _num(spec.get("wing_area_m2"))
        ar = _num(spec.get("aspect_ratio"))
        if tc and s and ar and ar > 0:
            chord = math.sqrt(s / ar)
            surfaces = [{"id": "asa", "chord_m": chord, "t_c": tc, "lifting": True, "protection": "none"}]
            notes.append("asa: corda média √(S/AR) e t/c de wave.thickness_ratio; d = 2 r_le com o "
                         "PRESSUPOSTO NACA de 4 dígitos já usado no tipo fixo; sem proteção")
    if not surfaces:
        return _status(False, "sem superfícies: o VTOL L0 não traz corda nem t/c, e não são inventados",
                       notes=notes)
    conds = list(block.get("conditions") or [])
    skipped: list[str] = []
    if not conds:
        if kind == "vtol":
            mission = (result.get("inputs_resolved") or {}).get("mission") or {}
            v_cruise = _num((result.get("cruise") or {}).get("V_m_s"))
            for seg in result.get("segments") or []:
                name = str(seg.get("segment"))
                t = _num(seg.get("t_s"))
                if name in ("hover",):
                    skipped.append("hover: V = 0, fora da captação")
                    continue
                if name == "transition":
                    skipped.append("transition: V desconhecida")
                    continue
                if name == "vertical_climb":
                    v = _num(mission.get("climb_rate_m_s"))
                else:
                    v = v_cruise
                if not t or not v or v <= 0:
                    skipped.append(f"{name}: sem V ou duração")
                    continue
                conds.append({"name": name, "altitude_m": float(block.get("altitude_m") or 0.0),
                              "V_m_s": v, "duration_s": t})
        else:
            cruise = result.get("cruise") or {}
            v = _num(cruise.get("speed_tas_m_s"))
            rng = _num(spec.get("range_m"))
            if result.get("converged") and v and rng and v > 0:
                conds.append({"name": "cruzeiro", "altitude_m": float(spec.get("altitude_m") or 0.0),
                              "V_m_s": v, "duration_s": rng / v})
                skipped.append("subida: o fecho L0 do jato não tem segmento de subida; a espessura é só o cruzeiro")
            else:
                return _status(False, "jato sem cruzeiro convergido para o gelo", notes=notes)
    if not conds:
        return _status(False, "sem condição de gelo com V > 0; " + "; ".join(skipped), notes=notes)
    spec_i = {"envelopes": block.get("envelopes") or ["continuous", "intermittent"],
              "mvd_um": block.get("mvd_um"), "conditions": conds, "surfaces": surfaces,
              "fiki": block.get("fiki")}
    try:
        from acdt.core.icing.study import analyse
        ice = analyse(spec_i)
    except Exception as ex:  # noqa: BLE001
        return _status(False, f"gelo falhou: {type(ex).__name__}: {ex}", notes=notes, skipped=skipped)
    partial = bool(skipped)
    return _status(True, "; ".join(skipped), verdict="nao_avaliado" if partial else "validado",
                   mission_complete=not partial, notes=notes, skipped=skipped, result=ice)


def _noise_native(kind: str, result: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    if kind == "jet":
        return _status(False, "jato sem método de ruído citado (SAE ARP876 não está verificado neste repositório); "
                       "não se usa o modelo de hélice")
    block = dict(spec.get("noise") or {})
    rotors = (result.get("inputs_resolved") or {}).get("rotors") or spec.get("rotors") or {}
    blades = rotors.get("n_blades", block.get("blades"))
    rpm = _num(rotors.get("rpm"))
    if rpm is None:
        rpm = _num((result.get("hover") or {}).get("rpm_bemt"))
    alt = _num(block.get("flyover_altitude_m"))
    missing = []
    if blades is None:
        missing.append("n_blades")
    if rpm is None:
        missing.append("rpm de funcionamento (rpm_max é o limite de ponta, não o ponto)")
    if alt is None:
        missing.append("noise.flyover_altitude_m")
    if missing:
        return _status(False, "ruído não avaliado: " + ", ".join(missing))
    hover = result.get("hover") or {}
    n = int(hover.get("n_rotors") or rotors.get("n") or 1)
    thrust = _num(hover.get("thrust_per_rotor_N"))
    power = _num(hover.get("P_per_rotor_W"))
    diameter = _num(hover.get("diameter_m"))
    if thrust is None or power is None or diameter is None:
        return _status(False, "pairar sem empuxo, potência ou diâmetro")
    from acdt.api import rotor_noise
    try:
        rn = rotor_noise(blades=int(blades), diameter_m=diameter, rpm=float(rpm), thrust_N=thrust,
                         power_W=power, n_rotors=n, altitude_m=float(alt), speed_m_s=0.0,
                         rho=float(hover.get("rho_kg_m3") or 1.225), c_m_s=float(hover.get("a_m_s") or 340.294))
    except Exception as ex:  # noqa: BLE001
        return _status(False, f"ruído falhou: {type(ex).__name__}: {ex}")
    return _status(True, "Gutin + Schlegel-King-Mull no pairar; nível é limite inferior (sem espessura, sem motor)",
                   lower_bound=True, result=rn)


def _reliability_native(result: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    block = dict(spec.get("reliability") or {})
    comps = list(block.get("components") or []) + equipment_components(spec)
    if not comps:
        return _status(False, "sem componentes com ou sem taxa: fiabilidade não inventada")
    t = _num(block.get("mission_duration_h"))
    src = "reliability.mission_duration_h"
    if t is None:
        segs = result.get("segments") or []
        if segs:
            t = sum(float(s.get("t_s") or 0.0) for s in segs) / 3600.0
            src = "soma dos segmentos nativos"
        elif result.get("cruise") and spec.get("range_m") and (result["cruise"] or {}).get("speed_tas_m_s"):
            t = float(spec["range_m"]) / float(result["cruise"]["speed_tas_m_s"]) / 3600.0
            src = "alcance/velocidade do cruzeiro (só o cruzeiro)"
    spec_r: dict[str, Any] = {"schema": "acdt.reliability/1", "components": comps,
                              "mission_duration_h": t, "accept_assumptions": bool(block.get("accept_assumptions", False))}
    for k in ("rbd", "preventive", "logistics", "utilization", "fleet", "spares", "operating_cost",
              "labour_rate_per_h"):
        if block.get(k) is not None:
            spec_r[k] = block[k]
    try:
        from acdt.core.reliability.study import analyse
        rel = analyse(spec_r)
    except Exception as ex:  # noqa: BLE001
        return _status(False, f"fiabilidade falhou: {type(ex).__name__}: {ex}")
    unknown = bool(rel.get("unknown_components"))
    return _status(True, f"duração: {src}" + ("; λ desconhecido em " + ", ".join(rel.get("unknown_components") or [])
                                              if unknown else ""),
                   verdict="nao_avaliado" if unknown else "validado", duration_source=src, result=rel)


def _series_native(spec: Mapping[str, Any]) -> dict[str, Any]:
    block = spec.get("series_cost")
    if not isinstance(block, Mapping):
        return _status(False, "sem series_cost: o Eastlake/DAPCA do tipo fixo não é aplicado ao VTOL ou ao jato "
                       "sem as entradas")
    try:
        from acdt.domains.aircraft.manufacturing.series import analyse
        out = analyse(dict(block))
    except Exception as ex:  # noqa: BLE001
        return _status(False, f"custo de série falhou: {type(ex).__name__}: {ex}")
    fold_series_cost(out, spec)
    incomplete = isinstance(out.get("average_unit_cost_USD"), Mapping) and out["average_unit_cost_USD"].get("hi") is None
    return _status(True, "; ".join(out.get("adapter_notes") or []) or str(out.get("method") or ""),
                   verdict="nao_avaliado" if incomplete else "validado", result=out)


def _life_native(kind: str, result: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    block = spec.get("life_cycle")
    if not isinstance(block, Mapping):
        return _status(False, "sem life_cycle declarado: frota, vida e custo não são inventados")
    from acdt.core.lcc import environment as env
    from acdt.core.lcc import lcc
    notes: list[str] = []
    # chave ausente fica de fora: lcc.analyse trata omissão com omissão (o default de dict.get não
    # dispara se o valor for None). None explícito seria um inteiro inválido, não um desconhecido.
    lspec = {k: block[k] for k in ("fleet_size", "service_life_years", "production_rate_per_year", "rdte_years",
                                   "rdte_USD", "unit_production_cost_USD", "cost_per_fh_USD",
                                   "fh_per_aircraft_per_year", "disposal_per_aircraft_USD",
                                   "residual_per_aircraft_USD", "discount_rate", "escalation_os")
             if k in block and block[k] is not None}
    espec = dict(block.get("environment") or {})
    prop = "electric" if kind == "vtol" else "turbofan"
    included_in_native_energy = False
    if kind == "vtol":
        t = sum(float(s.get("t_s") or 0.0) for s in (result.get("segments") or [])) / 3600.0
        if t > 0 and result.get("energy_Wh") is not None and "battery_kWh_per_fh" not in espec:
            espec["battery_kWh_per_fh"] = float(result["energy_Wh"]) / 1000.0 / t
            included_in_native_energy = True
            notes.append("energia/FH = energy_Wh do size_vtol / duração (PRESSUPOSTO: ciclo 1; o hotel da carga "
                         "já está em energy_Wh quando energy_complete; é minorante se for falso)")
        if result.get("energy_nominal_Wh") is not None and "battery_capacity_kWh" not in espec:
            espec["battery_capacity_kWh"] = float(result["energy_nominal_Wh"]) / 1000.0
    else:
        cruise = result.get("cruise") or {}
        v = _num(cruise.get("speed_tas_m_s"))
        burn = _num((result.get("weights") or {}).get("fuel_mass_kg"))
        rng = _num(spec.get("range_m"))
        if v and rng and burn is not None and v > 0 and "fuel_kg_per_fh" not in espec:
            espec["fuel_kg_per_fh"] = burn / (rng / v / 3600.0)
            espec.setdefault("fuel", "jet_a")
            notes.append("combustível/FH = combustível do fecho / tempo de cruzeiro (PRESSUPOSTO: inclui a reserva)")
    if included_in_native_energy:
        # size_vtol já somou o hotel a energy_Wh. Somar outra vez contaria a carga duas vezes.
        eq_now = equipment_effect(spec)
        if eq_now["present"] and not result.get("energy_complete", True):
            notes.append("potência do equipamento desconhecida: a energia/FH não a inclui (não é zero)")
            espec["equipment_unaccounted"] = True
        elif eq_now["present"]:
            notes.append("o hotel da carga ou da arquitetura já está em energy_Wh; não é somado outra vez")
    else:
        fold_life_cycle_energy(espec, notes, spec, "electric" if prop == "electric" else "jet")
    try:
        out = lcc.analyse(lspec)
        life_h = out["fleet_flight_hours"]
        n = int(lspec["fleet_size"])
        espec.setdefault("fleet_flight_hours", life_h)
        espec.setdefault("aircraft_flight_hours", {"lo": life_h["lo"] / n, "hi": life_h["hi"] / n})
        espec.setdefault("mission_duration_h", None)
        out["environment"] = env.analyse(espec)
        e = out["environment"]
        out["co2e_per_flight_hour_kg"] = e.get("per_flight_hour_total_kgCO2e", e["operation_per_fh_kgCO2e"])
        out["life_cycle_co2e_kg"] = e.get("life_cycle_fleet_kgCO2e", {"lo": None, "hi": None})
        open_unaccounted(out, espec)
    except Exception as ex:  # noqa: BLE001
        return _status(False, f"ciclo de vida falhou: {type(ex).__name__}: {ex}", notes=notes)
    incomplete = bool(espec.get("equipment_unaccounted")) or any(
        isinstance(out.get(k), Mapping) and out[k].get("hi") is None
        for k in ("co2e_per_flight_hour_kg", "life_cycle_cost_NPV_USD"))
    cost = out.get("life_cycle_cost_USD")
    cost_open = isinstance(cost, Mapping) and cost.get("hi") is None

    def _open(v: Any) -> bool:
        return not isinstance(v, Mapping) or v.get("lo") is None or v.get("hi") is None

    co2_open = bool(espec.get("equipment_unaccounted")) or _open(out.get("co2e_per_flight_hour_kg")) or _open(
        out.get("life_cycle_co2e_kg"))
    # o custo pode fechar com o CO₂ ainda em aberto (fator de bateria não declarado). O veredicto da
    # disciplina só é validado quando os dois fecham; co2_complete distingue as duas partes.
    return _status(True, "; ".join(notes), verdict="nao_avaliado" if cost_open or co2_open else "validado",
                   notes=notes, co2_complete=not co2_open, result=out,
                   incomplete_flag=incomplete or co2_open or cost_open)


def evaluate(kind: str, result: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    """As seis disciplinas a partir do resultado nativo. Não altera a massa fechada."""
    eq = equipment_effect(spec)
    thermal = _thermal_native(kind, result, spec, eq)
    icing = _icing_native(kind, result, spec)
    noise = _noise_native(kind, result, spec)
    reliability = _reliability_native(result, spec)
    series = _series_native(spec)
    life = _life_native(kind, result, spec)
    ran = [name for name, blk in (("termica", thermal), ("gelo", icing), ("ruido", noise),
                                  ("fiabilidade", reliability), ("custo_serie", series), ("ciclo_vida", life))
           if blk.get("evaluated")]
    return {"schema": "acdt.native_disciplines/1", "kind": kind, "veredicto": "validado" if ran else "nao_avaliado",
            "calibracao_L1_L2": "nao_aplicar",
            "reason": "adaptador correu: " + ", ".join(ran) if ran else "nenhuma disciplina fechou com os dados nativos",
            "equipment": {k: eq[k] for k in ("present", "mode", "P_avg_W", "P_peak_W", "source", "reason",
                                            "example_catalog", "mass_kg", "mass_complete", "coupled_to_mass",
                                            "mass_note", "unit_cost_USD", "cost_complete", "distribution_heat_W",
                                            "distribution_method")},
            "thermal": thermal, "icing": icing, "noise": noise, "reliability": reliability,
            "series_cost": series, "life_cycle": life}


def attach(kind: str, result: dict[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    block = evaluate(kind, result, spec)
    result["disciplines"] = block
    return block


def hotel_adjustment(base_w: float, base_source: str, obj: Any) -> tuple[float | None, str]:
    """Hotel do tipo fixo: a arquitetura substitui pelo máximo; a carga útil soma. Incompleto → None."""
    eq = equipment_effect(obj)
    if not eq["present"]:
        return base_w, base_source
    if eq["P_avg_W"] is None:
        return None, eq["reason"] or eq["source"]
    if eq["mode"] == "architecture":
        p = max(base_w, float(eq["P_avg_W"]))
        how = "a arquitetura é maior que o hotel declarado" if p > base_w else "o hotel declarado já cobre a arquitetura"
        return p, eq["source"] + "; " + how
    return base_w + float(eq["P_avg_W"]), base_source + " + " + eq["source"]
