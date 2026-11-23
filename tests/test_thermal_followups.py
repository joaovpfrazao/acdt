# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Seguimentos da térmica L0: sol em altitude (Laue 1970), majorante de Meredith, perdas do gerador onboard e
ventilador acoplado em motor térmico (extração de veio P/η, caudal P/η·BSFC)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from acdt.core.thermal.air import SOLAR_CONSTANT_W_M2, laue_direct_W_m2, solar_hot_day
from acdt.core.thermal.cooling import meredith_thrust_bound
from acdt.core.thermal.study import build_condition

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def test_laue_and_meinel_against_source_values():
    # PVEducation 'Air Mass': AM 1,5 ao nível do mar → 0,846 kW/m² (Meinel & Meinel)
    assert laue_direct_W_m2(0.0, 1.5) == pytest.approx(846.0, abs=0.5)
    # Laue (SAND2012-2389 Eq. 24), AM 1, h = 1 km: 1353·[(1 − 0,14)·0,7 + 0,14]
    assert laue_direct_W_m2(1000.0) == pytest.approx(1353.0 * (0.86 * 0.7 + 0.14))
    with pytest.raises(ValueError):
        laue_direct_W_m2(0.0, 0.9)


def test_solar_hot_day_scales_mil310_with_altitude_and_caps_outside_validity():
    assert solar_hot_day(0.0)[0] == 1120.0
    s3, src = solar_hot_day(3000.0)
    assert s3 == pytest.approx(1120.0 * (1.0 + 0.06 * 3.0)) and "Laue" in src
    s5, src5 = solar_hot_day(5000.0)
    assert s5 == SOLAR_CONSTANT_W_M2 and "majorante" in src5  # fora da validade: majorante, não zero
    c = build_condition({"name": "cruzeiro_quente", "case": "hot", "atmosphere": "mil310_hot_1pct",
                         "altitude_m": 600.0, "V_m_s": 25.0})
    assert c.solar_W_m2 == pytest.approx(1120.0 * 1.036) and "Laue" in c.solar_source
    cold = build_condition({"name": "f", "case": "cold", "atmosphere": "mil310_cold_1pct", "altitude_m": 600.0})
    assert cold.solar_W_m2 == 0.0
    decl = build_condition({"name": "d", "case": "hot", "atmosphere": "mil310_hot_1pct", "solar_W_m2": 900.0})
    assert decl.solar_W_m2 == 900.0 and decl.solar_source == "declarado"


def test_meredith_bound_is_ideal_brayton_and_not_credited():
    T = 288.15
    V = 0.5 * math.sqrt(1.4 * 287.05287 * T)          # M = 0,5
    m = meredith_thrust_bound(1000.0, V, T)
    eta = 1.0 - 1.0 / (1.0 + 0.2 * 0.25)
    assert m["eta_cycle_ideal"] == pytest.approx(eta) and m["thrust_upper_N"] == pytest.approx(eta * 1000.0 / V)
    assert m["credited"] is False
    low = meredith_thrust_bound(200.0, 25.0, 322.15)   # UAV lento: ~1e-3 do calor
    assert low["eta_cycle_ideal"] < 1.5e-3
    assert meredith_thrust_bound(200.0, 0.0, 300.0)["status"] == "nao_avaliado"


def _onboard(power_W: float = 400.0) -> dict:
    return {"schema_version": "1.0", "source": "PRESSUPOSTO teste — não é datasheet",
            "items": [{"id": "radar", "role": "payload", "mass_kg": 2.0, "mass_accounting": "incremental",
                       "source": "PRESSUPOSTO"},
                      {"id": "alternador", "role": "equipment", "mass_kg": 1.0, "mass_accounting": "incremental",
                       "source": "PRESSUPOSTO"}],
            "loads": [{"id": "radar_load", "item_id": "radar", "source_id": "bus", "power_W": power_W,
                       "peak_W": power_W * 1.5, "duty": 1.0, "source": "PRESSUPOSTO"}],
            "sources": [{"id": "bus", "kind": "generator", "item_id": "alternador", "delivery_efficiency": 0.9,
                         "continuous_W": 1000, "peak_W": 1000, "generator_efficiency": 0.75, "shaft_limit_W": 1500,
                         "bsfc_kg_kWh_shaft": 0.35, "source": "PRESSUPOSTO teste"}]}


def test_bridge_reports_generator_loss_by_energy_balance():
    from acdt.domains.aircraft.onboard_bridge import apply_onboard_to_size_dict

    _d, rep = apply_onboard_to_size_dict({"requirements": {"propulsion_type": "piston_prop"},
                                          "assumptions": {"propulsion": {}, "weights": {}},
                                          "onboard": _onboard(400.0)})
    term = 400.0 / 0.9
    assert rep["generator_terminal_W"] == pytest.approx(term)
    assert rep["generator_loss_W"] == pytest.approx(term / 0.75 - term)        # P_veio·(1 − η)
    assert rep["generator_eta_effective"] == pytest.approx(0.75)
    assert rep["generator_fuel_per_shaft_kg_J"] == pytest.approx(0.35 / 3.6e6)


@pytest.mark.slow
def test_piston_onboard_generator_heat_and_fan_coupled_as_shaft_extraction():
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec

    d = yaml.safe_load((EX / "uav_gasoline_150kg.yaml").read_text(encoding="utf-8"))
    d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
    d["assumptions"].setdefault("stability", {})["use_avl"] = False
    d["onboard"] = _onboard(400.0)
    for k in ("systems_power_W", "onboard_power_W"):
        d["assumptions"].setdefault("propulsion", {}).pop(k, None)

    def run(fan_dp: float | None):  # noqa: ANN202
        th: dict = {}
        if fan_dp is not None:
            th = {"coupling": "iterar",
                  "bays": [{"id": "fuselagem", "skin_area_m2": 2.0, "flow_length_m": 2.0, "height_m": 0.4,
                            "eps_ext": 0.85, "alpha_solar": 0.3, "eps_int": [0.1, 0.9],
                            "sources": ["avionica", "gerador"],
                            "fan": {"mass_flow_kg_s": 0.05, "pressure_rise_Pa": fan_dp, "efficiency": 0.3,
                                    "mass_kg": 0.1, "conditions": ["cruzeiro_quente"]}}]}
        d["assumptions"]["thermal"] = th
        return run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_gasoline_150kg.yaml"))

    base = run(None)["result"]
    t = base.thermal
    assert t["evaluated"] and t["generator"]["loss_W"] == pytest.approx(400.0 / 0.9 * (1 / 0.75 - 1))
    srcs = {s["id"]: s for s in t["bays"]["fuselagem"]["conditions"]["cruzeiro_quente"]["sources"]}
    assert srcs["gerador"]["hi_W"] == pytest.approx(t["generator"]["loss_W"])
    assert srcs["avionica"]["hi_W"] > 0                   # carga onboard dissipa-se a bordo (antes 0 W)
    assert t["bays"]["fuselagem"]["conditions"]["cruzeiro_quente"]["solar_W_m2"] > 1120.0
    lo, hi = run(10.0)["result"], run(3000.0)["result"]
    shaft0 = base.spec.assumptions["propulsion"]["auxiliary_shaft_W"]
    hist = hi.thermal["coupling_loop"]["history"]
    assert hist[-1]["power_W"] > 0 and not any("ventilador" in x for x in hist[-1]["not_coupled"])
    assert hi.spec.assumptions["propulsion"]["auxiliary_shaft_W"] > shaft0
    assert hi.spec.assumptions["propulsion"]["auxiliary_fuel_flow_kg_s"] > \
        lo.spec.assumptions["propulsion"]["auxiliary_fuel_flow_kg_s"]
    assert hi.sizing.W0 > lo.sizing.W0
