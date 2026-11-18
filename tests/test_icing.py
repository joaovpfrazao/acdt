# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina gelo L0/L1 (docs/GELO.md): V&V contra Anderson NASA/CR-2004-212875 Ap. B e Jeck DOT/FAA/AR-00/30,
regras de completude (intervalos, desconhecido ≠ zero), proteção, pipeline e acoplamento."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from acdt.core.icing import envelopes as env
from acdt.core.icing import properties as pr
from acdt.core.icing.accretion import ice_thickness, stagnation
from acdt.core.icing.impingement import beta0, modified_inertia, naca4_le_radius, range_parameter
from acdt.core.icing.penalty import CLMAX_RATIO, penalty
from acdt.core.icing.protection import protection_power, running_wet_min_flux
from acdt.core.icing.study import analyse

EX = Path(__file__).resolve().parents[1] / "examples"


def _vv(case_id: str) -> dict:
    from acdt.core import vv

    r = vv.run(ids=[case_id])
    (row,) = [c for c in r["cases"] if c["id"] == case_id]
    return row


# ------------------------------------------------------------------------------------------ V&V
def test_anderson_b1_reference():
    row = _vv("ICING-AND-B1")
    assert row["status"] == "passa", row


def test_anderson_b2_reference():
    row = _vv("ICING-AND-B2")
    assert row["status"] == "passa", row


def test_appendix_c_tables():
    assert _vv("ICING-APPC-JECK")["status"] == "passa"
    # valores do corpo das Tabelas 1 e 2 de Jeck (transcritos à parte dos nós usados no módulo)
    for kind, T, m, he, ref in [("intermittent", -30, 20, 0.5, 1.279), ("continuous", -20, 30, 50, 0.073),
                                ("continuous", 0, 25, 5, 0.670), ("intermittent", -10, 35, 1.5, 0.794),
                                ("continuous", -10, 15, 200, 0.171), ("intermittent", 0, 40, 5.0, 0.645)]:
        # 1,5×10⁻³: Jeck multiplica o LWC padrão não arredondado (p. ex. 0,7125 × 1,115 = 0,794, não 0,795)
        assert env.design_lwc(kind, T, m, he).lwc_g_m3 == pytest.approx(ref, abs=1.5e-3)
    # fatores de ajuste por MVD da Tabela 3 de Jeck: razão LWC(MVD)/LWC(15 µm)
    assert env.lwc_standard("continuous", -10, 25) / env.lwc_standard("continuous", -10, 15) == pytest.approx(
        0.508, abs=1e-3)
    # achado: a Tabela 3 dá 0,398 para intermitente −30 °C/35 µm, mas a Tabela 1 dá 0,350/1,100 = 0,318; o módulo
    # usa a Tabela 1 (valores diretos) — registado em docs/GELO.md
    assert env.lwc_standard("intermittent", -30, 35) / env.lwc_standard("intermittent", -30, 15) == pytest.approx(
        0.350 / 1.100)


def test_naca_le_radius():
    assert _vv("ICING-NACA0012-RLE")["status"] == "passa"
    assert naca4_le_radius(0.12, 2.0) == pytest.approx(2 * 1.1019 * 0.0144)


# ------------------------------------------------------------------------------------------ propriedades
def test_properties_validity_and_values():
    assert pr.p_sat_water(273.15) == pytest.approx(610.78)
    assert pr.p_sat_ice(273.15) == pytest.approx(610.92)
    assert pr.p_sat_ice(263.15) < pr.p_sat_water(263.15)  # gelo abaixo de 0 °C
    with pytest.raises(ValueError):
        pr.p_sat_water(280.0)
    with pytest.raises(ValueError):
        pr.p_sat_water(220.0)
    assert pr.LAMBDA_F_GLAZE == pytest.approx(pr.lambda_fusion(273.15))
    assert pr.LAMBDA_V_GLAZE == pytest.approx(pr.lambda_vaporisation(273.15), rel=2e-3)
    assert pr.total_temperature(250.0, 100.0) == pytest.approx(250.0 + 1e4 / (2 * pr.CP_AIR))


def test_impingement_limits():
    assert modified_inertia(0.1, 0.5) == 0.125 and beta0(0.125) == 0.0
    b = [beta0(k) for k in (0.2, 0.5, 1, 3, 10, 50)]
    assert all(x < y for x, y in zip(b, b[1:])) and b[-1] < 1.0
    assert 0 < range_parameter(500) < range_parameter(20) < 1


# ------------------------------------------------------------------------------------------ Messinger
def _st(T_C: float, V: float = 80.0, lwc: float = 0.5, d: float = 0.03, mvd: float = 20.0):
    return stagnation(T_st=273.15 + T_C, V=V, d_m=d, mvd_m=mvd * 1e-6, lwc_kg_m3=lwc * 1e-3, p_st=70000.0)


def test_freezing_regimes():
    assert _st(-28.0, lwc=0.2).ice_type == "rime"
    g = _st(-4.0, lwc=1.0)
    assert g.ice_type == "glaze" and 0 < g.n0 < 1
    w = _st(-1.0, V=150.0, lwc=0.3)  # aquecimento cinético: T_tot > 0 °C
    assert w.T_tot > 273.15 and w.ice_type == "sem_gelo" and w.accretion_rate_m_s == 0.0
    assert ice_thickness(1.0, 0.5, 1e-3, 100.0, 60.0) == pytest.approx(0.5 * 1e-3 * 100 * 60 / pr.RHO_ICE)


def test_running_wet_identity_and_bounds():
    s = _st(-10.0, lwc=0.6)
    assert running_wet_min_flux(s) == pytest.approx(s.n0_raw * s.m_imp * s.lambda_f, rel=1e-9)
    p = protection_power("anti_ice_thermal", s, d_m=0.03, V=80.0, area_m2=0.5, surface_temperature_C=10.0)
    assert 0 < p.power_W["lo"] <= p.power_W["hi"]
    p2 = protection_power("anti_ice_thermal", s, d_m=0.03, V=80.0, area_m2=0.5)
    assert p2.power_W["hi"] is None  # T_s não declarada → majorante desconhecido, nunca zero
    p3 = protection_power("deice_electrothermal", s, d_m=0.03, V=80.0, area_m2=0.5)
    assert p3.power_W == {"lo": None, "hi": None}
    p4 = protection_power("deice_electrothermal", s, d_m=0.03, V=80.0, area_m2=0.5, duty_cycle=0.1,
                          parting_strip_area_m2=0.02, power_density_W_m2=30000.0)
    assert p4.power_W["lo"] == pytest.approx(running_wet_min_flux(s) * (0.05 + 0.02))
    assert p4.power_W["hi"] == pytest.approx(30000.0 * 0.07)
    assert protection_power("boots", s, d_m=0.03, V=80.0, area_m2=0.5).power_W["hi"] is None


# ------------------------------------------------------------------------------------------ envelopes
def test_envelope_geometry_and_unknowns():
    assert env.in_envelope("continuous", 3000.0, -10.0) == "dentro"
    assert env.in_envelope("continuous", 8000.0, -10.0) == "fora"
    assert env.in_envelope("continuous", 0.0, 0.0) == "fronteira"  # vértice lido da figura → desconhecido
    assert env.in_envelope("intermittent", 0.0, -10.0) == "fora"   # Fig. 5 começa a 4000 ft
    assert env.in_envelope("intermittent", 5000.0, -35.0) == "possivel"
    assert env.envelope_temperatures("continuous", 7000.0) == []
    assert env.design_lwc("continuous", 2.0, 20).lwc_g_m3 == 0.0     # acima de 0 °C: sem Ap. C
    assert env.design_lwc("continuous", -35.0, 20).lwc_g_m3 is None   # fora das tabelas: desconhecido
    assert env.design_lwc("continuous", -10.0, 50).lwc_g_m3 is None
    assert env.design_lwc("continuous", -10.0, 15, 2.0).lwc_g_m3 is None
    sb = env.design_lwc("continuous", -10.0, 15, 2.0, short_bound=True)
    assert sb.lwc_g_m3 == pytest.approx(0.590 * 1.340 * 5.0 / 2.0)
    lg = env.design_lwc("continuous", -10.0, 15, 600.0)
    assert lg.lwc_g_m3 == pytest.approx(0.590 * 0.215) and "conservador" in lg.note


# ------------------------------------------------------------------------------------------ estudo genérico
def _spec(**kw):
    s = {"conditions": [{"name": "subida", "altitude_m": 1500, "V_m_s": 50, "duration_s": 300},
                        {"name": "cruzeiro", "altitude_m": 3000, "V_m_s": 60, "duration_s": 3600},
                        {"name": "alto", "altitude_m": 9000, "V_m_s": 90, "duration_s": 3600}],
         "surfaces": [{"id": "asa", "chord_m": 1.0, "t_c": 0.12, "lifting": True},
                      {"id": "cauda", "chord_m": 0.5, "t_c": 0.10, "protection": "deice_electrothermal",
                       "protected_area_m2": 0.3, "duty_cycle": 0.1, "power_density_W_m2": 20000},
                      {"id": "sonda", "d_m": 0.02, "protection": "anti_ice_thermal", "protected_area_m2": 0.01}]}
    s.update(kw)
    return s


def test_study_intervals_and_completeness():
    r = analyse(_spec(fiki=True))
    assert r["conditions"]["alto"]["envelope_status"] == ["fora"]
    assert r["surfaces"]["asa"]["by_condition"]["alto"]["thickness_mm"] == {"lo": 0.0, "hi": 0.0}
    t = r["max_thickness_mm"]
    assert 0 < t["lo"] < t["hi"]
    assert r["max_thickness_m"]["hi"] == pytest.approx(t["hi"] * 1e-3)
    # soma das condições (acreção acumulada) ≥ maior condição isolada
    by = r["surfaces"]["asa"]["by_condition"]
    assert t["hi"] == pytest.approx(sum(e["thickness_mm"]["hi"] for e in by.values()))
    # sonda anti-gelo sem T_s → majorante da potência total desconhecido (nunca zero)
    assert r["protection"]["power_W"]["hi"] is None and r["protection"]["power_W"]["lo"] > 0
    assert r["surfaces"]["cauda"]["residual_ice"].startswith("desconhecido")
    assert r["fiki"]["verdict"] is False  # asa crítica sem proteção acumula gelo
    pen = r["surfaces"]["asa"]["penalty"]
    assert pen["applies"] is True and pen["delta_CD0"]["hi"] is None
    assert pen["clmax_ratio"]["lo"] == pytest.approx(0.52 / 1.85)
    cc = by["cruzeiro"]["critical_case"]
    assert cc["ice_type"] in ("rime", "glaze") and 0 < cc["beta0"] < 1
    assert r["exposure_s"] == {"lo": pytest.approx(r["exposure_s"]["lo"]), "hi": 3900.0}


def test_study_isa_temperature_and_fiki_unknown():
    s = _spec(fiki=True)
    for c in s["conditions"]:
        c["T_C"] = 10.0  # dia quente: fora do Ap. C
    r = analyse(s)
    assert r["max_thickness_mm"] == {"lo": 0.0, "hi": 0.0}
    assert r["fiki"]["verdict"] is None  # nunca passa a L0


def test_penalty_ranges():
    assert penalty(False)["applies"] is False
    p = penalty(None)
    assert p["applies"] is None and p["stall_speed_factor"]["hi"] == pytest.approx(1 / math.sqrt(CLMAX_RATIO[0]))


def test_api_icing():
    from acdt import api

    assert tuple(int(x) for x in api.API_VERSION.split(".")) >= (1, 4, 0)  # icing desde 1.4.0
    e = api.icing_envelope("intermittent", -20, 25, horizontal_extent_nmi=4.0, altitude_m=4000)
    assert e["lwc_g_m3"] == pytest.approx(1.041, abs=6e-4) and e["envelope_status"] == "dentro"
    assert api.icing(_spec())["schema"] == "acdt.icing/1"
    with pytest.raises(ValueError):
        api.icing({"conditions": [], "surfaces": []})


# ------------------------------------------------------------------------------------------ pipeline
@pytest.mark.slow
def test_icing_stage_in_pipeline_requirements_and_coupling():
    """UAV elétrico de exemplo (só teste; o projeto não muda): superfícies por omissão sem proteção → espessura,
    FIKI falha; com degelo eletrotérmico declarado e coupling iterar a potência entra no balanço elétrico."""
    import yaml

    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec

    d = yaml.safe_load((EX / "uav_endurance_payload.yaml").read_text(encoding="utf-8"))
    d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
    d["assumptions"].setdefault("stability", {})["use_avl"] = False
    d["requirements"]["max_ice_thickness"] = {"max": 1, "unit": "mm", "id": "IC-01"}
    d["requirements"]["flight_into_known_icing"] = {"target": "sim", "id": "IC-02"}
    st = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_endurance_payload.yaml"))
    ic = st["result"].icing
    assert ic["evaluated"] and set(ic["surfaces"]) == {"asa", "estabilizador_horizontal", "estabilizador_vertical"}
    assert ic["max_thickness_mm"]["lo"] > 1.0
    rows = {r["id"]: r for r in st["verification"]["rows"]}
    assert rows["IC-01"]["status"] == "falha" and rows["IC-02"]["status"] == "falha"
    assert "L0" in st["design"]["results"]["gelo"]
    W0 = st["result"].sizing.W0
    d["assumptions"]["icing"] = {"coupling": "iterar", "surfaces": [
        {"id": "asa", "chord_m": 0.3, "t_c": 0.12, "lifting": True, "protection": "deice_electrothermal",
         "protected_area_m2": 0.2, "duty_cycle": 0.1, "power_density_W_m2": 10000, "mass_kg": 0.3}]}
    d["requirements"]["ice_protection_power"] = {"max": 1, "unit": "kW", "id": "IC-03"}
    st2 = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_endurance_payload.yaml"))
    ic2 = st2["result"].icing
    loop = ic2["coupling_loop"]
    assert loop["converged"] and loop["history"][0]["power_W"] > 0 and loop["history"][0]["mass_kg"] == 0.3
    assert 0.0 < loop["history"][0]["duty"] <= 1.0  # ciclo = fração da missão em gelo (ou 1, conservador)
    assert st2["result"].sizing.W0 > W0
    rows2 = {r["id"]: r for r in st2["verification"]["rows"]}
    assert rows2["IC-03"]["status"] in ("passa", "falha")


def test_exposure_duty_fraction_and_conservative_fallback():
    """Ciclo da carga de proteção: fração da missão em segmentos dentro do envelope (majorante da exposição); sem
    durações, ou com power_schedule: missao, toda a missão (majorante conservador)."""
    from acdt.domains.aircraft.icing import exposure_duty

    out = {"conditions": {"subida": {"duration_s": 600.0}, "cruzeiro": {"duration_s": 3000.0},
                          "descida": {"duration_s": 400.0}},
           "exposure_s": {"lo": 300.0, "hi": 1000.0}}
    f, note = exposure_duty(out)
    assert f == pytest.approx(1000.0 / 4000.0) and "envelope" in note
    assert exposure_duty(out, "missao")[0] == 1.0
    out["conditions"]["descida"]["duration_s"] = None
    assert exposure_duty(out)[0] == 1.0
    assert exposure_duty({"conditions": {}, "exposure_s": {"hi": 0.0}})[0] == 1.0
