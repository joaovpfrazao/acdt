# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Pegada ambiental L0 (CO₂/CO₂e) da energia usada em voo e, opcionalmente, do fabrico das baterias.

* **Combustível, combustão (TTW)**: CO₂ = massa × FCF, FCF = 3,16 kg CO₂/kg (Jet-A/Jet-A1) e 3,10 kg CO₂/kg
  (AvGas/Jet-B) — ICAO Anexo 16 Vol. IV (CORSIA), Parte II Cap. 2, 2.2.3. Só CO₂ (CH₄ e N₂O não incluídos).
* **Combustível, ciclo de vida (WTW)**: valor de base do ciclo de vida do CORSIA (Anexo 16 Vol. IV, fórmula das
  reduções com combustíveis elegíveis), LC = 89 gCO₂e/MJ (combustíveis de jato) e 95 gCO₂e/MJ (AvGas), × energia = massa × PCI (PCI por omissão = mínimos ASTM D1655/D910, como na térmica;
  PRESSUPOSTO).
* **Eletricidade da rede**: energia tirada da bateria / rendimento de carga × intensidade da rede **declarada** pelo
  utilizador (intervalo com fonte). Sem intensidade → **desconhecido**; sem rendimento de carga → minorante com
  η = 1 e majorante desconhecido.
* **Fabrico de baterias** (opcional): capacidade × fator. ``ivl_c444_2019`` = 61–106 kg CO₂e/kWh (Emilsson &
  Dahllöf, IVL C 444, 2019: baterias NMC de veículos ligeiros, materiais virgens, sem reciclagem) — aplicar a outra
  química ou aplicação é PRESSUPOSTO; ou um intervalo declarado com fonte. Sem nada → desconhecido.
* **Fora do âmbito (não avaliado)**: fabrico da estrutura e dos motores, fim de vida, efeitos não-CO₂ em altitude.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from .lcc import rng

FCF = {"jet_a": 3.16, "jet_a1": 3.16, "avgas": 3.10, "jet_b": 3.10}
FCF_SOURCE = ("ICAO Anexo 16 Vol. IV (CORSIA), Parte II Cap. 2, 2.2.3: 3,16 kg CO₂/kg (Jet-A/Jet-A1), 3,10 kg CO₂/kg "
              "(AvGas/Jet-B)")
LC_G_PER_MJ = {"jet_a": 89.0, "jet_a1": 89.0, "jet_b": 89.0, "avgas": 95.0}
LC_SOURCE = ("CORSIA (ICAO Anexo 16 Vol. IV): valor de base do ciclo de vida LC = 89 gCO₂e/MJ (combustíveis de jato) e "
             "95 gCO₂e/MJ (AvGas) da fórmula das reduções com combustíveis elegíveis (conferido no material de "
             "formação da ICAO sobre os regulamentos-modelo do CORSIA, 2023, §5.12, e no CAR 1000.23 do Canadá)")
BATTERY_FACTORS = {"ivl_c444_2019": (61.0, 106.0, "Emilsson & Dahllöf (2019), IVL C 444, Lithium-Ion Vehicle Battery "
                                                  "Production: 61–106 kg CO₂e/kWh (NMC, veículos ligeiros, materiais "
                                                  "virgens, sem reciclagem)")}


def _mul(a: tuple[float | None, float | None], b: tuple[float | None, float | None]) -> tuple[float | None, float | None]:
    lo = None if a[0] is None or b[0] is None else a[0] * b[0]
    hi = None if a[1] is None or b[1] is None else a[1] * b[1]
    return lo, hi


def _add(*xs: tuple[float | None, float | None]) -> tuple[float | None, float | None]:
    lo = sum((x[0] or 0.0) for x in xs)  # parcelas ≥ 0: desconhecido entra com 0 no minorante
    hi_parts = [x[1] for x in xs]
    return lo, (None if any(h is None for h in hi_parts) else float(sum(h for h in hi_parts if h is not None)))


def _d(x: tuple[float | None, float | None]) -> dict[str, float | None]:
    return {"lo": x[0], "hi": x[1]}


def analyse(spec: Mapping[str, Any]) -> dict[str, Any]:
    """``spec``: ``{fuel_kg_per_fh, fuel: jet_a|avgas|…, fcf_kg_per_kg?, lhv_MJ_kg?, battery_kWh_per_fh,
    charge_efficiency, grid_intensity_kgCO2e_per_kWh: {lo, hi, source}, battery_capacity_kWh, battery_cycle_life,
    flights_per_fh, battery_footprint: ivl_c444_2019 | {lo, hi, source}, fleet_flight_hours, aircraft_flight_hours,
    mission_duration_h}``."""
    notes: list[str] = []
    sources: dict[str, str] = {}
    unknown: list[str] = []
    per_fh: dict[str, tuple[float | None, float | None]] = {}
    fuel = rng(spec.get("fuel_kg_per_fh"))
    if fuel[0]:
        ft = str(spec.get("fuel") or "")
        fcf = spec.get("fcf_kg_per_kg")
        if fcf is not None:
            f = rng(fcf)
            sources["fcf"] = str(spec.get("fcf_source") or "declarado (sem fonte: PRESSUPOSTO)")
        elif ft in FCF:
            f = (FCF[ft], FCF[ft])
            sources["fcf"] = FCF_SOURCE
        else:
            f = (None, None)
            unknown.append(f"fator de emissão do combustível '{ft}' (declare fuel: jet_a|avgas ou fcf_kg_per_kg)")
        per_fh["fuel_combustion_CO2"] = _mul(fuel, f)
        lhv = spec.get("lhv_MJ_kg")
        if ft in LC_G_PER_MJ and lhv is not None:
            lc = LC_G_PER_MJ[ft] / 1000.0
            per_fh["fuel_well_to_wake_CO2e"] = _mul(fuel, (float(lhv) * lc, float(lhv) * lc))
            sources["fuel_wtw"] = LC_SOURCE + f"; PCI {lhv} MJ/kg ({spec.get('lhv_source', 'declarado')})"
    e = rng(spec.get("battery_kWh_per_fh"))
    if e[0]:
        gi = rng(spec.get("grid_intensity_kgCO2e_per_kWh"))
        if gi[0] is None:
            unknown.append("grid_intensity_kgCO2e_per_kWh (intensidade da rede: declare um intervalo com fonte)")
        else:
            src = (spec.get("grid_intensity_kgCO2e_per_kWh") or {})
            sources["grid"] = str(src.get("source") if isinstance(src, Mapping) else "") or \
                "declarado sem fonte (PRESSUPOSTO)"
        eta = rng(spec.get("charge_efficiency"))
        if eta[0] is None:
            grid_e: tuple[float | None, float | None] = (e[0], None)
            notes.append("rendimento de carga não declarado: minorante com η = 1, majorante desconhecido")
        else:
            grid_e = (e[0] / (eta[1] or eta[0]), None if e[1] is None else e[1] / eta[0])
        per_fh["electricity_grid_CO2e"] = _mul(grid_e, gi)
    ops = _add(*per_fh.values()) if per_fh else (0.0, 0.0)
    # na soma de operação usa-se WTW se existir (inclui a combustão); senão TTW
    if "fuel_well_to_wake_CO2e" in per_fh:
        ops = _add(*[v for k, v in per_fh.items() if k != "fuel_combustion_CO2"])
        notes.append("operação: combustível em ciclo de vida (WTW, inclui a combustão); TTW reportado à parte")
    out: dict[str, Any] = {"evaluated": True, "schema": "acdt.lca/1",
                           "per_flight_hour_kgCO2e": {k: _d(v) for k, v in per_fh.items()},
                           "operation_per_fh_kgCO2e": _d(ops)}
    fh_ac = rng(spec.get("aircraft_flight_hours"))
    fh_fleet = rng(spec.get("fleet_flight_hours"))
    cap = spec.get("battery_capacity_kWh")
    bat_fp: tuple[float | None, float | None] | None = None
    if cap:
        bf = spec.get("battery_footprint")
        if isinstance(bf, str) and bf in BATTERY_FACTORS:
            lo, hi, s = BATTERY_FACTORS[bf]
            fac: tuple[float | None, float | None] = (lo, hi)
            sources["battery"] = s
            notes.append("PRESSUPOSTO: fator de fabrico de baterias de veículos ligeiros NMC aplicado a esta bateria")
        elif isinstance(bf, Mapping):
            fac = rng(bf)
            sources["battery"] = str(bf.get("source") or "declarado sem fonte (PRESSUPOSTO)")
        else:
            fac = (None, None)
            unknown.append("battery_footprint (fabrico de baterias: ivl_c444_2019 ou intervalo com fonte)")
        life = spec.get("battery_cycle_life")
        fpf = spec.get("flights_per_fh")
        if life and fpf and fh_ac[0] is not None:
            cyc = (fh_ac[0] * float(fpf), None if fh_ac[1] is None else fh_ac[1] * float(fpf))
            packs = (float(max(1, math.ceil(cyc[0] / float(life)))),
                     None if cyc[1] is None else float(max(1, math.ceil(cyc[1] / float(life)))))
        else:
            packs = (1.0, None)
            notes.append("vida em ciclos ou ciclos por FH não declarados: 1 bateria no minorante, majorante "
                         "desconhecido")
        bat_fp = _mul(_mul(packs, (float(cap), float(cap))), fac)
        out["battery_manufacturing_per_aircraft_kgCO2e"] = _d(bat_fp)
        out["battery_packs_per_aircraft"] = _d(packs)
    if fh_ac[0] is not None:
        op_ac = _mul(ops, fh_ac)
        out["operation_per_aircraft_kgCO2e"] = _d(op_ac)
        tot_ac = _add(op_ac, bat_fp) if bat_fp is not None else op_ac
        out["life_per_aircraft_kgCO2e"] = _d(tot_ac)
        if fh_ac[0]:
            out["per_flight_hour_total_kgCO2e"] = _d((None if tot_ac[0] is None else tot_ac[0] / (fh_ac[1] or fh_ac[0]),
                                                      None if tot_ac[1] is None else tot_ac[1] / fh_ac[0]))
    n = spec.get("fleet_size")
    if fh_fleet[0] is not None:
        op_fl = _mul(ops, fh_fleet)
        tot_fl = op_fl
        if bat_fp is not None and n:
            tot_fl = _add(op_fl, _mul(bat_fp, (float(n), float(n))))
        out["life_cycle_fleet_kgCO2e"] = _d(tot_fl)
    t_m = spec.get("mission_duration_h")
    if t_m:
        out["per_mission_kgCO2e"] = _d(_mul(ops, (float(t_m), float(t_m))))
    out.update({"unknown": unknown, "notes": notes, "sources": sources,
                "not_assessed": ["fabrico da estrutura e dos motores", "fim de vida", "efeitos não-CO₂ em altitude",
                                 "CH₄/N₂O da combustão"],
                "status": "completo" if not unknown else "parcial"})
    return out
