# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina térmica (acdt.core.thermal, domains/aircraft/thermal.py; docs/TERMICA.md)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from acdt.core.thermal.air import CP_AIR, ambient, air_props
from acdt.core.thermal.convection import flat_plate_forced, vertical_plate_natural
from acdt.core.thermal.cooling import fan_power, internal_drag, required_mass_flow, size_ram_duct
from acdt.core.thermal.network import (Bay, Bound, Condition, Phase, corners, losses, solve_bay_bounds, solve_bay_steady,
                                       solve_bay_transient)
from acdt.core.thermal.sources import electric_chain, ice_cooling, total
from acdt.core.thermal.study import analyse

EX = Path(__file__).resolve().parents[1] / "examples"


def _vv(case_id):
    from acdt.core import vv

    rep = vv.run(ids=[case_id])
    (c,) = rep["cases"]
    return c


# ------------------------------------------------------------------------------------------ V&V (Incropera)
def test_incropera_ex51_lumped():
    assert _vv("THERMAL-INC-EX5.1")["status"] == "passa"


def test_incropera_ex71_flat_plate():
    assert _vv("THERMAL-INC-EX7.1")["status"] == "passa"


def test_incropera_ex92_natural():
    assert _vv("THERMAL-INC-EX9.2")["status"] == "passa"


def test_incropera_ex86_duct():
    assert _vv("THERMAL-INC-EX8.6")["status"] == "passa"


def test_mil310_tables():
    assert _vv("THERMAL-MIL310")["status"] == "passa"
    a = ambient("mil310_hot_1pct", 1000.0)
    assert a.T_C == pytest.approx(40.0) and a.rho == pytest.approx(1.007)
    assert a.p_Pa == pytest.approx(1.007 * 287.05287 * 313.15)
    mid = ambient("mil310_hot_1pct", 500.0)
    assert 40.0 < mid.T_C < 49.0 and 1.007 < mid.rho < 1.081
    assert ambient("mil310_cold_20pct", 0.0).T_C == pytest.approx(-51.0)
    with pytest.raises(ValueError):
        ambient("mil310_cold_20pct", 12000.0)
    with pytest.raises(ValueError):
        ambient("nao_existe", 0.0)


def test_air_props_vs_table_a4():
    assert _vv("THERMAL-AIR-PROPS")["status"] == "passa"
    a = air_props(300.0, 101325.0)
    # Tabela A.4: ν = 15,89×10⁻⁶ m²/s a 300 K; a tabela usa ρ = 1,1614 kg/m³ (o gás ideal dá 1,1766), daí ~1,3 %
    assert a.nu == pytest.approx(15.89e-6, rel=0.02)
    assert CP_AIR == pytest.approx(1004.7, abs=0.1)


# ------------------------------------------------------------------------------------------ correlações
def test_flat_plate_regimes_and_natural_convection():
    lam = flat_plate_forced(5.0, 0.5, 310.0, 300.0, 101325.0)
    assert "7.30" in lam.correlation and lam.Re < 5e5
    mix = flat_plate_forced(40.0, 2.0, 310.0, 300.0, 101325.0)
    assert "7.38" in mix.correlation and mix.Re > 5e5
    trip = flat_plate_forced(40.0, 2.0, 310.0, 300.0, 101325.0, tripped=True)
    assert trip.h > mix.h  # turbulenta desde o bordo > mista
    nat = vertical_plate_natural(0.3, 330.0, 300.0, 101325.0)
    assert 2.0 < nat.h < 10.0  # ordem de grandeza da convecção natural em ar


# ------------------------------------------------------------------------------------------ rede térmica
def _bay(**kw):
    d = dict(id="b", skin_area_m2=1.0, flow_length_m=1.0, height_m=0.2, eps_ext=Bound(0.9, 0.9, "t"),
             alpha_solar=Bound(0.3, 0.3, "t"), sun_area_m2=0.3, eps_int=Bound(0.5, 0.5, "t"))
    d.update(kw)
    return Bay(**d)


def test_steady_energy_balance_closes_and_bounds_are_ordered():
    cond = Condition("c", ambient("mil310_hot_1pct", 0.0), 25.0, 1120.0)
    s = solve_bay_steady(_bay(vent_m_dot_kg_s=0.01), cond, 100.0, hot=True)
    assert s.q_skin_W + s.q_vent_W == pytest.approx(100.0, rel=1e-4)
    assert s.T_bay_K > cond.ambient.T_K
    wide = _bay(vent_m_dot_kg_s=0.01, eps_ext=Bound(0.0, 1.0, "t"), alpha_solar=Bound(0.0, 1.0, "t"), eps_int=Bound(0.0, 1.0, "t"))
    lo, hi = solve_bay_bounds(wide, cond, 100.0, 100.0)
    assert hi is not None and lo.T_bay_K < s.T_bay_K < hi.T_bay_K
    assert len(corners(wide)) == 16 and len(corners(_bay(), forced=False)) == 1
    # qualquer ponto interior da caixa fica entre os limites (monotonia por parâmetro)
    for c in [(0.5, 0.5, 0.5, False), (0.2, 0.9, 0.7, True), (0.95, 0.05, 0.3, False)]:
        T = solve_bay_steady(wide, cond, 100.0, hot=c).T_bay_K
        assert lo.T_bay_K - 1e-6 <= T <= hi.T_bay_K + 1e-6
    # parado ao sol com pouca potência: a pele aquece o compartimento, logo ε_int alto é o vértice quente
    sun = Condition("s", ambient("mil310_hot_1pct", 0.0), 0.0, 1120.0)
    b2 = _bay(alpha_solar=Bound(0.9, 0.9, "t"), eps_int=Bound(0.1, 0.9, "t"))
    lo2, hi2 = solve_bay_bounds(b2, sun, 5.0, 5.0)
    assert hi2 is not None and hi2.T_bay_K >= solve_bay_steady(b2, sun, 5.0, hot=True).T_bay_K
    # sem calor, sem sol, parado: equilíbrio com o ambiente
    z = solve_bay_steady(_bay(), Condition("z", ambient("isa", 0.0), 0.0, 0.0), 0.0, hot=True)
    assert z.T_bay_K == pytest.approx(288.15, abs=0.05)


def test_transient_ventilated_bay_matches_analytic_lumped_solution():
    """Só ventilação (parede isolada): C dT/dt = Q − ṁc_p(T − T_in) → solução exponencial (Incropera Eq. 5.25)."""
    amb = ambient("isa", 0.0)
    cond = Condition("v", amb, 0.0, 0.0)
    m, C, Q = 0.01, 5000.0, 200.0
    b = _bay(wall_U_W_m2K=1e-12, vent_m_dot_kg_s=m, capacity_J_K=C)
    tr = solve_bay_transient(b, [Phase(cond, 600.0, Q)], amb.T_K, hot=True)
    a = m * CP_AIR / C
    T_end = amb.T_K + Q / (m * CP_AIR) * (1.0 - math.exp(-a * 600.0))
    assert tr["T_end_K"] == pytest.approx(T_end, abs=0.02)
    ss = solve_bay_steady(b, cond, Q, hot=True)
    tr2 = solve_bay_transient(b, [Phase(cond, 20 * C / (m * CP_AIR), Q)], amb.T_K, hot=True)
    assert tr2["T_end_K"] == pytest.approx(ss.T_bay_K, abs=0.05)
    with pytest.raises(ValueError):
        solve_bay_transient(_bay(), [Phase(cond, 10.0, Q)], amb.T_K, hot=True)
    assert losses(b, cond, amb.T_K, True) == pytest.approx(0.0, abs=1e-6)


# ------------------------------------------------------------------------------------------ fontes
def test_electric_chain_split_and_shared_bound():
    d = electric_chain(1000.0, 0.8)
    assert d["cadeia_total"].lo == pytest.approx(200.0)
    assert d["bateria"].hi == pytest.approx(200.0) and d["bateria"].lo == 0.0
    lo, hi = total([d["bateria"], d["esc"], d["motor"]])
    assert (lo, hi) == (0.0, pytest.approx(200.0))  # majorante partilhado: nunca 3 × 200
    k = electric_chain(1000.0, 0.8, eta_motor=0.9, eta_esc=0.95)
    P_shaft = 800.0
    assert k["motor"].lo == pytest.approx(P_shaft * (1 / 0.9 - 1))
    assert k["esc"].lo == pytest.approx(P_shaft / 0.9 * (1 / 0.95 - 1))
    assert k["bateria"].known and k["bateria"].lo == pytest.approx(200.0 - k["motor"].lo - k["esc"].lo)
    r = electric_chain(1000.0, 0.8, R_pack_ohm=0.05, V_nom=50.0)
    assert r["bateria"].lo == pytest.approx((1000.0 / 50.0) ** 2 * 0.05)


def test_ice_cooling_bounds():
    s = ice_cooling("m", 10000.0, 0.001, 43.5e6)
    assert s.lo == 0.0 and s.hi == pytest.approx(43500.0 - 10000.0)
    f = ice_cooling("m", 10000.0, 0.001, 43.5e6, cooling_fraction=0.3)
    assert f.lo == f.hi == pytest.approx(0.3 * 43500.0)


# ------------------------------------------------------------------------------------------ arrefecimento
def test_ram_duct_drag_mass_and_fan():
    m = required_mass_flow(500.0, 330.0, 310.0)
    assert m == pytest.approx(500.0 / (CP_AIR * 20.0))
    assert required_mass_flow(500.0, 300.0, 310.0) is None
    d = size_ram_duct(500.0, 330.0, 310.0, 1.1, 30.0, ram_recovery=0.8, duct_loss_q=0.4,
                      duct_length_m=0.5, areal_density_kg_m2=1.2)
    assert d.inlet_area_m2 == pytest.approx(m / (0.6 * 1.1 * 30.0))
    Ve = 30.0 * math.sqrt(1.0 - 0.6)
    assert d.drag_N_lo == d.drag_N_hi == pytest.approx(m * (30.0 - Ve))
    assert d.duct_mass_kg == pytest.approx(2 * math.sqrt(math.pi * d.inlet_area_m2) * 0.5 * 1.2)
    u = size_ram_duct(500.0, 330.0, 310.0, 1.1, 30.0)
    assert u.drag_N_lo == 0.0 and u.drag_N_hi == pytest.approx(m * 30.0) and u.duct_mass_kg is None
    assert internal_drag(0.1, 30.0, 1.5)[1] == pytest.approx(3.0)  # ζ ≥ 1: perda total
    assert fan_power(0.02, 1.2, 300.0, 0.5) == pytest.approx(0.02 * 300.0 / (1.2 * 0.5))
    assert fan_power(0.02, 1.2, None, 0.5) is None


def _spec(**bay_kw):
    bay = {"id": "baia", "skin_area_m2": 1.2, "flow_length_m": 1.8, "height_m": 0.22, "eps_ext": 0.85,
           "alpha_solar": 0.3, "eps_int": [0.1, 0.9], "sources": ["aviónica", "bateria"],
           "components": [{"id": "bat", "source": "bateria", "conductance_W_K": 4.0, "T_max_C": 60, "T_min_C": -20,
                           "limit_source": "teste"}]}
    bay.update(bay_kw)
    return {"conditions": [{"name": "solo", "case": "hot", "atmosphere": "mil310_hot_1pct", "V_m_s": 0.0},
                           {"name": "cruz", "case": "hot", "atmosphere": "mil310_hot_1pct", "altitude_m": 1000.0,
                            "V_m_s": 30.0},
                           {"name": "frio", "case": "cold", "atmosphere": "mil310_cold_1pct", "altitude_m": 1000.0,
                            "V_m_s": 30.0}],
            "sources": {"aviónica": {"heat_W": 40.0}, "bateria": {"heat_W": {"solo": 0.0, "default": [5.0, 20.0]}}},
            "bays": [bay], "reference": {"S_ref_m2": 2.0, "cruise_condition": "cruz"}}


def test_generic_study_intervals_unknown_and_ram_air_coupling_outputs():
    r = analyse(_spec())
    assert r["complete"] and r["hot_margin_C"]["lo"] is not None
    assert r["hot_margin_C"]["lo"] <= r["hot_margin_C"]["hi"]
    c = r["bays"]["baia"]["conditions"]["cruz"]
    assert c["Q_W"] == {"lo": 45.0, "hi": 60.0}
    assert c["T_bay_C"]["lo"] <= c["T_bay_C"]["hi"]
    # fonte desconhecida → majorante desconhecido → margem a quente sem minorante (nunca passa)
    s = _spec()
    s["sources"]["bateria"] = {"heat_W": None}
    u = analyse(s)
    assert not u["complete"] and u["hot_margin_C"]["lo"] is None
    # componente sem condutância: T ≥ T_b, majorante desconhecido
    s2 = _spec(components=[{"id": "bat", "source": "bateria", "T_max_C": 60}])
    u2 = analyse(s2)
    assert u2["components"]["bat"]["by_condition"]["cruz"]["T_C"]["hi"] is None
    # ar dinâmico dimensionado → área, arrasto (perdas declaradas), massa, ΔC_D0
    s3 = _spec(ram_air={"size_for": "cruz", "ram_recovery": 0.8, "duct_loss_q": 0.5,
                        "duct": {"length_m": 0.4, "areal_density_kg_m2": 1.0}})
    r3 = analyse(s3)
    rs = r3["bays"]["baia"]["cooling"]["ram_sizing"]
    assert rs["inlet_area_m2"] > 0 and r3["cooling"]["drag_known"]
    cool = r3["cooling"]
    assert cool["drag_N"]["lo"] == pytest.approx(cool["drag_N"]["hi"]) and cool["drag_N"]["hi"] > 0
    assert cool["delta_CD0"]["hi"] == pytest.approx(cool["drag_area_m2"]["hi"] / 2.0)
    assert cool["mass_kg"] > 0
    cr = r3["bays"]["baia"]["conditions"]["cruz"]
    assert cr["vent_m_dot_kg_s"] > 0
    assert cr["T_bay_C"]["hi"] < c["T_bay_C"]["hi"]  # ventilado arrefece
    # obturador: conduto fechado no dia frio → sem ventilação nessa condição
    s5 = _spec(ram_air={"size_for": "cruz", "ram_recovery": 0.8, "duct_loss_q": 0.5, "open_conditions": ["cruz", "solo"]})
    r5 = analyse(s5)
    assert r5["bays"]["baia"]["conditions"]["frio"]["vent_m_dot_kg_s"] == 0.0
    assert r5["bays"]["baia"]["conditions"]["cruz"]["vent_m_dot_kg_s"] > 0.0
    # conduto impossível (limite abaixo da temperatura de recuperação): arrasto desconhecido, nunca zero
    s4 = _spec(ram_air={"size_for": "cruz"}, air_T_max_C=30.0)
    r4 = analyse(s4)
    assert r4["bays"]["baia"]["cooling"]["status"] == "nao_dimensionado"
    assert r4["cooling"]["drag_N"]["hi"] is None and r4["cooling"]["mass_kg"] is None


def test_ram_inlet_sized_for_the_worst_flying_segment_not_the_max_of_a_partial_set():
    """A entrada fica com a maior área pedida pelos segmentos em voo. Um segmento que não fecha deixa a área
    desconhecida: não se toma o máximo dos outros."""
    hot = {"case": "hot", "atmosphere": "mil310_hot_1pct"}
    conds = [{"name": "subida_quente", **hot, "altitude_m": 0.0, "V_m_s": 18.0},
             {"name": "cruzeiro_quente", **hot, "altitude_m": 1000.0, "V_m_s": 32.0}]
    s = _spec(ram_air={"size_for": "pior_segmento", "ram_recovery": 0.8, "duct_loss_q": 0.5,
                       "duct": {"length_m": 0.4, "areal_density_kg_m2": 1.0}})
    s["conditions"] = conds
    s["sources"]["aviónica"] = {"heat_W": {"subida_quente": 120.0, "cruzeiro_quente": 40.0, "default": 40.0}}
    s["sources"]["bateria"] = {"heat_W": {"subida_quente": 30.0, "cruzeiro_quente": 10.0, "default": 10.0}}
    r = analyse(s)
    rs = r["bays"]["baia"]["cooling"]["ram_sizing"]
    areas = {c["condition"]: c["inlet_area_m2"] for c in rs["candidates"]}
    assert rs["policy"] == "pior_segmento" and rs["status"] != "desconhecido"
    assert rs["condition"] == max(areas, key=areas.get)
    assert rs["inlet_area_m2"] == pytest.approx(max(areas.values()))
    assert rs["condition"] == "subida_quente"
    named = _spec(ram_air={"size_for": "cruzeiro_quente", "ram_recovery": 0.8, "duct_loss_q": 0.5,
                           "duct": {"length_m": 0.4, "areal_density_kg_m2": 1.0}})
    named["conditions"] = conds
    named["sources"] = s["sources"]
    cruise_only = analyse(named)["bays"]["baia"]["cooling"]["inlet_area_m2"]
    assert r["bays"]["baia"]["cooling"]["inlet_area_m2"] > cruise_only
    bad = _spec(ram_air={"size_for": "pior_segmento", "ram_recovery": 0.8, "duct_loss_q": 0.5})
    bad["conditions"] = conds
    bad["sources"]["aviónica"] = {"heat_W": {"subida_quente": None, "cruzeiro_quente": 40.0, "default": 40.0}}
    bad["sources"]["bateria"] = {"heat_W": 0.0}
    u = analyse(bad)
    assert u["bays"]["baia"]["cooling"]["ram_sizing"]["status"] == "desconhecido"
    assert u["cooling"]["drag_N"]["hi"] is None


def test_thermal_evaluator_interval_semantics():
    from acdt.core.verification import TracedRequirement, VerificationContext, classify, resolve_evaluator
    import acdt.domains.aircraft.verification_evaluators  # noqa: F401

    ev, arg = resolve_evaluator("termica:hot_margin_C")
    req = TracedRequirement(id="T1", text="margem", quantity="thermal_margin", comparison="min", threshold=0.0,
                            unit="K")

    def st(lo, hi):
        return classify(req, ev.fn(req, VerificationContext({"thermal": {"evaluated": True,
                                                                         "hot_margin_C": {"lo": lo, "hi": hi}}}),
                                   arg))[0]
    assert st(2.0, 10.0) == "passa"
    assert st(-5.0, -1.0) == "falha"
    assert st(-5.0, 3.0) == "desconhecido"
    assert st(None, 3.0) == "desconhecido"
    assert st(None, -3.0) == "falha"
    ne = {"thermal": {"evaluated": False, "reason": "x"}}
    assert classify(req, ev.fn(req, VerificationContext(ne), arg))[0] == "nao_avaliado"
    evd, argd = resolve_evaluator("termica:cooling.drag_area_m2")
    rq = TracedRequirement(id="T2", text="arrasto", quantity="cooling_drag_area", comparison="max", threshold=0.01,
                           unit="m2")
    ok = {"thermal": {"evaluated": True, "cooling": {"drag_area_m2": {"lo": 0.0, "hi": 0.005}}}}
    assert classify(rq, evd.fn(rq, VerificationContext(ok), argd))[0] == "passa"
    unk = {"thermal": {"evaluated": True, "cooling": {"drag_area_m2": {"lo": 0.0, "hi": 0.05}}}}
    assert classify(rq, evd.fn(rq, VerificationContext(unk), argd))[0] == "desconhecido"


def test_api_thermal_and_atmosphere():
    from acdt import api

    a = api.thermal_atmosphere("mil310_cold_1pct", 0.0)
    assert a["T_C"] == pytest.approx(-61.0) and "MIL-HDBK-310" in a["source"]
    r = api.thermal(_spec())
    assert r["schema"] == "acdt.thermal/1"


# ------------------------------------------------------------------------------------------ pipeline
@pytest.mark.slow
def test_thermal_stage_electric_uav_in_pipeline_and_coupling():
    """UAV elétrico: fontes da cadeia, compartimento declarado com ar dinâmico, requisitos, design.json e o modo
    iterar (ponto fixo com o dimensionamento: área de arrasto e massa injetadas)."""
    import yaml

    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec

    d = yaml.safe_load((EX / "uav_endurance_payload.yaml").read_text(encoding="utf-8"))
    d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
    d["assumptions"].setdefault("stability", {})["use_avl"] = False
    bay = {"id": "fuselagem", "skin_area_m2": 1.0, "flow_length_m": 1.6, "height_m": 0.2, "eps_ext": 0.85,
           "alpha_solar": 0.3, "eps_int": [0.1, 0.9], "sources": ["avionica", "bateria", "esc"],
           "capacity_J_K": 9000.0,
           "components": [{"id": "bateria_pack", "source": "bateria", "conductance_W_K": 10.0, "T_max_C": 60,
                           "T_min_C": -20, "limit_source": "teste (limite declarado)"}],
           "ram_air": {"size_for": "pior_segmento", "ram_recovery": 0.8, "duct_loss_q": 0.5,
                       "duct": {"length_m": 0.4, "areal_density_kg_m2": 1.0}}}
    d["assumptions"]["thermal"] = {"bays": [bay], "electric": {"eta_esc": 0.97, "eta_motor": 0.9},
                                   "ground_time_s": 300}
    d["requirements"]["thermal_margin"] = {"min": 0, "unit": "K", "id": "TH-01"}
    d["requirements"]["cooling_drag_area"] = {"max": 1.0, "unit": "m2", "id": "TH-02"}
    st = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_endurance_payload.yaml"))
    th = st["result"].thermal
    assert th["evaluated"] and th["level"] == "L0"
    src = {s["id"]: s for s in th["bays"]["fuselagem"]["conditions"]["cruzeiro_quente"]["sources"]}
    assert src["esc"]["lo_W"] == src["esc"]["hi_W"] > 0  # η declarados → bateria pela diferença, ESC exato
    rs = th["bays"]["fuselagem"]["cooling"]["ram_sizing"]
    climb = next(c for c in rs["candidates"] if str(c["condition"]).startswith("subida"))
    # A subida quente não fecha: o ar de entrada fica acima do limite. A área não é a do cruzeiro.
    assert rs["status"] == "desconhecido" and rs["policy"] == "pior_segmento"
    assert climb["inlet_area_m2"] is None and climb["needs_fan"] is True
    assert th["cooling"]["drag_N"]["hi"] is None and th["cooling"]["mass_kg"] is None
    assert "segmento" in th["operating_points"]["cruzeiro"]["source"]
    tmax = th["bays"]["fuselagem"]["transient"]["T_bay_max_C"]
    assert tmax["hi"] is not None and tmax["lo"] <= tmax["hi"]
    rows = {r["id"]: r for r in st["verification"]["rows"]}
    assert rows["TH-01"]["status"] in ("passa", "falha", "desconhecido")
    assert rows["TH-02"]["status"] == "desconhecido"  # arrasto desconhecido não passa
    assert "L0" in st["design"]["results"]["termica"]
    W0_rel = st["result"].sizing.W0
    d["assumptions"]["thermal"]["bays"][0]["ram_air"]["size_for"] = "cruzeiro_quente"
    d["assumptions"]["thermal"]["coupling"] = "iterar"
    st2 = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_endurance_payload.yaml"))
    loop = st2["result"].thermal["coupling_loop"]
    assert loop["converged"] and len(loop["history"]) >= 2
    assert loop["mission"]["used"] is True and "ponto de projeto" not in loop["mission"]["source"]
    assert "segmento" in st2["result"].thermal["operating_points"]["cruzeiro"]["source"]
    da_iter = loop["history"][-1]["drag_area_m2"]
    da_final = st2["result"].thermal["cooling"]["drag_area_m2"]["hi"]
    assert da_final is not None and da_iter == pytest.approx(da_final, rel=0.02)
    a2 = st2["result"].spec.assumptions
    assert st2["result"].sizing.W0 > W0_rel  # arrasto e massa de arrefecimento aumentam o W0
    assert a2 is not None
    saved_perf = st2["result"].performance
    saved_req = getattr(st2["result"], "required_mission", None)
    st2["result"].performance = None
    st2["result"].required_mission = None
    from acdt.domains.aircraft.thermal import analyse_thermal
    da_dp = analyse_thermal(st2["result"])["cooling"]["drag_area_m2"]["hi"]
    st2["result"].performance = saved_perf
    st2["result"].required_mission = saved_req
    assert da_dp is not None and da_final is not None and da_dp > 0
    assert math.isfinite((da_final - da_dp) / da_dp)


@pytest.mark.slow
def test_thermal_stage_piston_engine_cooling_and_defaults():
    """UAV a gasolina, compartimento por omissão: calor do motor por balanço de energia; sem ΔT do ar o arrasto
    de arrefecimento do motor é desconhecido; com ΔT declarado é um intervalo."""
    import yaml

    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec

    d = yaml.safe_load((EX / "uav_gasoline_150kg.yaml").read_text(encoding="utf-8"))
    d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
    d["assumptions"].setdefault("stability", {})["use_avl"] = False
    st = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_gasoline_150kg.yaml"))
    th = st["result"].thermal
    assert th["evaluated"] and "fuselagem" in th["bays"]
    ec = th["engine_cooling"]["by_condition"]["cruzeiro_quente"]
    assert ec["status"] == "desconhecido" and th["cooling"]["drag_known"] is False
    assert th["engine_cooling"]["design_inlet"]["status"] == "desconhecido"
    d["assumptions"]["thermal"] = {"engine": {"air_temperature_rise_K": 30.0}}
    st2 = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_gasoline_150kg.yaml"))
    ec2 = st2["result"].thermal["engine_cooling"]["by_condition"]["cruzeiro_quente"]
    assert ec2["Q_W"]["lo"] == 0.0 and ec2["Q_W"]["hi"] > 0
    assert ec2["drag_N"]["lo"] == 0.0 and ec2["drag_N"]["hi"] > 0  # perdas não declaradas: [0, ṁV]
    di = st2["result"].thermal["engine_cooling"]["design_inlet"]
    assert di["status"] == "dimensionado"
    assert di["inlet_area_m2"] == pytest.approx(max(di["candidates_m2"].values()))
    assert di["condition"] == max(di["candidates_m2"], key=di["candidates_m2"].get)
    assert ec2["inlet_area_m2"] == pytest.approx(di["inlet_area_m2"])
    assert ec2["required_inlet_area_m2"] <= di["inlet_area_m2"] + 1e-12


@pytest.mark.slow
def test_thermal_iterar_fan_power_survives_closed_loop_power_budget():
    """Regressão: com power budget em malha fechada (systems_integration.run_with_systems) ``systems_power_W`` é
    substituído pela média do balanço; a potência do ventilador do modo iterar entra como carga de ``systems.loads``
    e o W0 sobe com ela (antes perdia-se em silêncio). Só a pressão do ventilador muda entre os dois casos."""
    import yaml

    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.thermal import FAN_LOAD_NAME

    d = yaml.safe_load((EX / "uav_endurance_payload.yaml").read_text(encoding="utf-8"))
    assert d.get("systems")  # caso com power budget em malha fechada
    d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
    d["assumptions"].setdefault("stability", {})["use_avl"] = False

    def run(dp_Pa: float):  # noqa: ANN202
        bay = {"id": "fuselagem", "skin_area_m2": 1.0, "flow_length_m": 1.6, "height_m": 0.2, "eps_ext": 0.85,
               "alpha_solar": 0.3, "eps_int": [0.1, 0.9], "sources": ["avionica", "bateria", "esc"],
               "fan": {"mass_flow_kg_s": 0.05, "pressure_rise_Pa": dp_Pa, "efficiency": 0.3, "mass_kg": 0.1,
                       "conditions": ["cruzeiro_quente"]}}
        d["assumptions"]["thermal"] = {"bays": [bay], "coupling": "iterar",
                                       "electric": {"eta_esc": 0.97, "eta_motor": 0.9}}
        return run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "uav_endurance_payload.yaml"))

    lo, hi = run(10.0), run(2000.0)
    p_lo = lo["result"].thermal["coupling_loop"]["history"][-1]["power_W"]
    p_hi = hi["result"].thermal["coupling_loop"]["history"][-1]["power_W"]
    assert p_hi > p_lo > 0
    assert hi["result"].thermal["coupling_loop"]["converged"]
    loads = {L["name"]: L for L in hi["result"].spec.systems.get("loads", [])}
    assert loads[FAN_LOAD_NAME]["power_w"] > 0
    assert hi["result"].sizing.W0 > lo["result"].sizing.W0
