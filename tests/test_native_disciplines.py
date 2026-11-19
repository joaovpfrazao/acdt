# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Adaptadores nativos: a carga útil e a arquitetura elétrica entram nas disciplinas.

Os números são de ensaio (potências e custos declarados aqui). Não são dados de uma aeronave.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from acdt.ai import jet as J
from acdt.domains.aircraft.native_disciplines import (
    equipment_components, equipment_effect, evaluate, hotel_adjustment,
)
from acdt.domains.aircraft.reliability import _opts
from acdt.domains.aircraft.thermal import hotel_power
from acdt.domains.aircraft.vtol import size_vtol
from acdt.domains.aircraft.jet.sizing import size_jet

ROOT = Path(__file__).resolve().parents[1]
JET = ROOT / "examples" / "jet" / "coupled_size.yaml"

BAY = {"id": "fuselagem", "skin_area_m2": 0.8, "sources": ["avionica"]}


def _mr(**extra):
    spec = {"architecture": "multirotor", "mass_kg": 5.0,
            "rotors": {"n": 4, "diameter_m": 0.38, "FM": 0.7},
            "mission": {"t_hover_s": 600},
            "electric": {"eta_motor": 0.85, "eta_esc": 0.95, "pack_Wh_kg": 200,
                         "reserve": 0.2, "dod": 0.8, "c_rate_max": 50, "systems_power_W": 0.0}}
    spec.update(extra)
    return spec


def _q(result, name="hover"):
    bay = result["bays"]["fuselagem"]
    return bay["conditions"][name]["Q_W"]["lo"]


class _Spec:
    def __init__(self, assumptions):
        self.assumptions = assumptions
        self.propulsion_kind = "electric"


class _Res:
    def __init__(self, assumptions):
        self.spec = _Spec(assumptions)
        self.systems = None


def test_equipment_missing_power_is_unknown_not_the_sum():
    eq = equipment_effect({"payload_equipment": {"items": [
        {"id": "cam", "power_w_avg": 25, "source": "ensaio"},
        {"id": "radio"},
    ]}})
    assert eq["present"] is True
    assert eq["P_avg_W"] is None
    assert eq["mode"] == "payload"
    assert "radio" in eq["source"]
    assert "não é a soma" in eq["reason"]
    assert eq["coupled_to_mass"] is False


def test_duty_default_and_distribution_loss():
    bare = equipment_effect({"payload_equipment": {"items": [{"id": "cam", "power_w_avg": 25}]}})
    assert bare["P_avg_W"] == pytest.approx(25.0)
    assert bare["pressupostos"] == ["cam.duty = 1"]
    assert "PRESSUPOSTO" in bare["source"]

    eq = equipment_effect({"electrical": {
        "loads": [{"name": "hotel", "power_w": 40, "duty": 1.0}],
        "distribution_eta": 0.9,
    }})
    assert eq["mode"] == "architecture"
    assert eq["P_avg_W"] == pytest.approx(40.0)
    q = 40.0 * (1.0 / 0.9 - 1.0)
    assert eq["distribution_heat_W"] == pytest.approx([q, q])

    # a mesma carga já na arquitetura não é somada outra vez
    both = equipment_effect({"electrical": {
        "loads": [{"name": "cam", "power_w": 40, "duty": 1.0}],
        "distribution_eta": 0.9,
    }, "payload_equipment": {"items": [{"id": "cam", "power_w_avg": 25}]}})
    assert both["P_avg_W"] == pytest.approx(40.0)


def test_missing_distribution_eta_is_not_one():
    eq = equipment_effect({"electrical": {"loads": [{"name": "hotel", "power_w": 40, "duty": 1.0}]}})
    assert eq["distribution_heat_W"] == [0.0, None]
    assert "não é η = 1" in eq["distribution_method"]
    bad = equipment_effect({"electrical": {
        "loads": [{"name": "hotel", "power_w": 40, "duty": 1.0}],
        "distribution_eta": 1.5,
    }})
    assert bad["distribution_heat_W"] == [0.0, None]


def test_example_source_is_flagged_and_does_not_enter_the_rbd():
    spec = {"payload_equipment": {"items": [{
        "id": "cam", "power_w_avg": 5, "source": "EXAMPLE", "lambda_per_h": 1e-4,
    }]}}
    eq = equipment_effect(spec)
    assert eq["example_catalog"] is True
    assert eq["P_avg_W"] == pytest.approx(5.0)
    row = equipment_components(spec)[0]
    assert row["id"] == "payload:cam"
    assert "lambda_per_h" not in row
    assert row["critical"] is True


def test_hotel_architecture_takes_the_max_and_payload_adds():
    arch = {"electrical": {"loads": [{"name": "hotel", "power_w": 40, "duty": 1.0}], "distribution_eta": 0.9}}
    p, _ = hotel_adjustment(12.0, "declarado", arch)
    assert p == pytest.approx(40.0)
    p2, _ = hotel_adjustment(50.0, "declarado", arch)
    assert p2 == pytest.approx(50.0)
    pay = {"payload_equipment": {"items": [{"id": "cam", "power_w_avg": 8, "duty": 1}]}}
    p3, _ = hotel_adjustment(12.0, "declarado", pay)
    assert p3 == pytest.approx(20.0)
    missing = {"payload_equipment": {"items": [{"id": "cam"}]}}
    assert hotel_adjustment(12.0, "declarado", missing)[0] is None
    assert hotel_adjustment(12.0, "declarado", {}) == (12.0, "declarado")


def test_fixed_wing_hotel_power_reads_assumptions():
    base = {"propulsion": {"systems_power_W": 12.0, "onboard_power_W": 0.0}}
    assert hotel_power(_Res(base))[0] == pytest.approx(12.0)
    with_pay = {**base, "payload_equipment": {"items": [
        {"id": "radio", "power_w_avg": 8, "duty": 1, "source": "ensaio"}]}}
    assert hotel_power(_Res(with_pay))[0] == pytest.approx(20.0)
    opts = _opts(_Spec({**with_pay, "reliability": {"components": [
        {"id": "fcc", "lambda_per_h": 1e-6, "source": "ensaio"}]}}))
    ids = [c["id"] for c in opts["components"]]
    assert ids == ["fcc", "payload:radio"]
    assert "lambda_per_h" not in opts["components"][1]


def test_vtol_payload_energy_changes_and_mass_does_not():
    base = size_vtol(_mr())
    with_pay = size_vtol(_mr(payload_equipment={"items": [
        {"id": "cam", "power_w_avg": 25, "source": "ensaio"}]}))
    assert with_pay["mass_kg"] == pytest.approx(base["mass_kg"])
    assert with_pay["energy_complete"] is True
    assert with_pay["energy_Wh"] == pytest.approx(base["energy_Wh"] + 25.0 * 600.0 / 3600.0)
    assert with_pay["battery_mass_kg"] > base["battery_mass_kg"]
    assert with_pay["disciplines"]["schema"] == "acdt.native_disciplines/1"
    assert with_pay["disciplines"]["calibracao_L1_L2"] == "nao_aplicar"
    json.loads(json.dumps(with_pay, allow_nan=False))


def test_vtol_unknown_payload_power_does_not_close_the_energy():
    base = size_vtol(_mr())
    unknown = size_vtol(_mr(payload_equipment={"items": [{"id": "cam"}]}))
    # o número fica só com o hotel declarado (0 W); não é a energia fechada
    assert unknown["energy_complete"] is False
    assert unknown["energy_Wh"] == pytest.approx(base["energy_Wh"])
    assert unknown["mass_kg"] == pytest.approx(5.0)
    assert unknown["disciplines"]["equipment"]["P_avg_W"] is None


def test_vtol_thermal_uses_payload_and_transition_stays_open():
    bare = size_vtol(_mr(thermal={"bays": [BAY]}))
    loaded = size_vtol(_mr(thermal={"bays": [dict(BAY)]}, payload_equipment={"items": [
        {"id": "cam", "power_w_avg": 25, "duty": 1, "source": "ensaio"}]}))
    th_b, th_l = bare["disciplines"]["thermal"], loaded["disciplines"]["thermal"]
    assert th_b["evaluated"] is True and th_l["evaluated"] is True
    assert th_l["veredicto"] == "validado"
    assert _q(th_l["result"]) == pytest.approx(_q(th_b["result"]) + 25.0)

    lc = size_vtol({
        "architecture": "lift_cruise", "mass_kg": 20.0,
        "rotors": {"n": 4, "diameter_m": 0.8},
        "mission": {"t_hover_s": 30, "cruise_distance_m": 5000, "cruise_speed_m_s": 25},
        "thermal": {"bays": [dict(BAY)]},
    })
    ice = lc["disciplines"]
    assert ice["thermal"]["evaluated"] is True
    assert ice["thermal"]["veredicto"] == "nao_avaliado"
    assert any("transition" in s for s in ice["thermal"]["skipped"])


def test_unknown_distribution_heat_does_not_validate_thermal():
    r = size_vtol(_mr(thermal={"bays": [dict(BAY)]}, electrical={
        "loads": [{"name": "hotel", "power_w": 30, "duty": 1.0}],
    }))
    th = r["disciplines"]["thermal"]
    assert th["evaluated"] is True
    assert th["veredicto"] == "nao_avaliado"
    assert any("distribuição" in s for s in th["skipped"])
    assert r["energy_Wh"] > size_vtol(_mr())["energy_Wh"]


def test_vtol_noise_needs_operating_rpm_not_tip_limit():
    quiet = size_vtol(_mr(rotors={"n": 4, "diameter_m": 0.38, "FM": 0.7, "n_blades": 2},
                          noise={"flyover_altitude_m": 100}))
    noise = quiet["disciplines"]["noise"]
    assert noise["evaluated"] is False
    assert noise["veredicto"] == "nao_avaliado"
    assert "rpm_max" in noise["reason"]
    assert quiet["hover"]["rpm_max"] > 0

    heard = size_vtol(_mr(rotors={"n": 4, "diameter_m": 0.38, "FM": 0.7, "n_blades": 2, "rpm": 3000},
                          noise={"flyover_altitude_m": 100}))
    hn = heard["disciplines"]["noise"]
    assert hn["evaluated"] is True and hn["lower_bound"] is True
    assert hn["veredicto"] == "validado"
    assert hn["result"]["overhead_LA_dBA"] > 0
    json.loads(json.dumps(heard["disciplines"], allow_nan=False))


def test_reliability_unknown_rate_is_not_a_pass():
    r = size_vtol(_mr(reliability={
        "mission_duration_h": 1.0,
        "components": [{"id": "motor", "lambda_per_h": 1e-5, "source": "ensaio"}],
    }, payload_equipment={"items": [{"id": "cam", "power_w_avg": 10, "source": "ensaio"}]}))
    rel = r["disciplines"]["reliability"]
    assert rel["evaluated"] is True
    assert rel["veredicto"] == "nao_avaliado"
    assert "payload:cam" in rel["result"]["unknown_components"]
    assert rel["result"]["mission_reliability"]["lo"] == pytest.approx(0.0)
    assert rel["result"]["mission_reliability"]["hi"] < 1.0


def test_series_cost_opens_when_a_price_is_missing():
    block = {"method": "learning", "quantity": 10,
             "learning": {"T1": 1000.0, "slope": 0.85, "nre": 0.0, "slope_source": "ensaio"}}
    closed = size_vtol(_mr(series_cost=block, payload_equipment={"items": [
        {"id": "cam", "power_w_avg": 10, "unit_cost_USD": 50, "source": "ensaio"}]}))
    bare = size_vtol(_mr(series_cost=dict(block)))
    got = closed["disciplines"]["series_cost"]
    assert got["veredicto"] == "validado"
    assert got["result"]["average_unit_cost_USD"] == pytest.approx(
        bare["disciplines"]["series_cost"]["result"]["average_unit_cost_USD"] + 50.0)

    opened = size_vtol(_mr(series_cost=dict(block), payload_equipment={"items": [
        {"id": "cam", "power_w_avg": 10, "source": "ensaio"}]}))
    cost = opened["disciplines"]["series_cost"]
    assert cost["evaluated"] is True and cost["veredicto"] == "nao_avaliado"
    assert cost["result"]["average_unit_cost_USD"]["hi"] is None
    assert cost["result"]["average_unit_cost_USD"]["lo"] == pytest.approx(
        bare["disciplines"]["series_cost"]["result"]["average_unit_cost_USD"])


def test_life_cycle_electric_payload_and_unknown_fuel_penalty():
    life = {"fleet_size": 2, "service_life_years": 5, "fh_per_aircraft_per_year": 100,
            "rdte_USD": 0, "unit_production_cost_USD": 10000, "cost_per_fh_USD": 10,
            "disposal_per_aircraft_USD": 0, "discount_rate": 0.03,
            "environment": {"grid_intensity_kgCO2e_per_kWh": {"lo": 0.2, "hi": 0.4, "source": "ensaio"},
                            "charge_efficiency": 0.9,
                            "battery_footprint": {"lo": 60.0, "hi": 100.0, "source": "ensaio"},
                            "battery_cycle_life": 500, "flights_per_fh": 1}}
    bare = size_vtol(_mr(life_cycle=life))
    loaded = size_vtol(_mr(life_cycle=copy.deepcopy(life), payload_equipment={"items": [
        {"id": "cam", "power_w_avg": 25, "duty": 1, "source": "ensaio"}]}))
    a = bare["disciplines"]["life_cycle"]
    b = loaded["disciplines"]["life_cycle"]
    assert a["veredicto"] == "validado" and a["co2_complete"] is True
    assert b["veredicto"] == "validado" and b["co2_complete"] is True
    # 25 W já estão em energy_Wh; a hora de voo ganha 0,025 kWh uma só vez (η_carga 0,9, rede 0,2 kg/kWh)
    a_lo = a["result"]["environment"]["per_flight_hour_kgCO2e"]["electricity_grid_CO2e"]["lo"]
    b_lo = b["result"]["environment"]["per_flight_hour_kgCO2e"]["electricity_grid_CO2e"]["lo"]
    assert b_lo - a_lo == pytest.approx(0.025 / 0.9 * 0.2)
    assert "não é somado outra vez" in b["reason"]

    jet = evaluate("jet", {"converged": True, "cruise": {"speed_tas_m_s": 200.0},
                           "weights": {"fuel_mass_kg": 1000.0}},
                   {"range_m": 200000.0, "altitude_m": 0.0, "wing_area_m2": 20.0, "aspect_ratio": 8.0,
                    "wave": {"thickness_ratio": 0.12}, "life_cycle": copy.deepcopy(life),
                    "payload_equipment": {"items": [{"id": "cam", "power_w_avg": 200, "source": "ensaio"}]}})
    assert jet["life_cycle"]["evaluated"] is True
    assert jet["life_cycle"]["veredicto"] == "nao_avaliado"
    assert jet["life_cycle"]["co2_complete"] is False
    assert jet["noise"]["evaluated"] is False
    assert jet["icing"]["evaluated"] is True and jet["icing"]["veredicto"] == "nao_avaliado"
    json.loads(json.dumps(jet, allow_nan=False))


def test_size_jet_keeps_mtow_and_attaches_disciplines():
    base_spec = J.load_spec(JET)
    plain = size_jet(copy.deepcopy(base_spec))
    spec = copy.deepcopy(base_spec)
    spec["payload_equipment"] = {"items": [{"id": "cam", "power_w_avg": 200, "mass_kg": 4.0, "source": "ensaio"}]}
    spec["thermal"] = {"bays": [{"id": "baia", "skin_area_m2": 40.0, "sources": ["avionica"]}],
                       "engine": {"heat_rejection_W": 5000.0}}
    rich = size_jet(spec)
    assert rich["converged"] is True and plain["converged"] is True
    assert rich["mtow_kg"] == pytest.approx(plain["mtow_kg"])
    assert "payload_equipment" not in rich["inputs"]
    disc = rich["disciplines"]
    assert disc["kind"] == "jet"
    assert disc["noise"]["evaluated"] is False and disc["noise"]["veredicto"] == "nao_avaliado"
    assert disc["icing"]["evaluated"] is True and disc["icing"]["veredicto"] == "nao_avaliado"
    assert any("subida" in s for s in disc["icing"]["skipped"])
    assert disc["thermal"]["evaluated"] is True and disc["thermal"]["veredicto"] == "nao_avaliado"
    assert disc["equipment"]["coupled_to_mass"] is False
    assert disc["equipment"]["mass_kg"] == pytest.approx(4.0)
    json.loads(json.dumps(rich, allow_nan=False))
