# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina ruído L0 (acdt.core.acoustics, domains/aircraft/noise.py; docs/RUIDO.md)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from acdt.core import vv
from acdt.core.acoustics import a_weighting, alpha_iso9613, level_sum, lp_from_prms, threshold_iso226
from acdt.core.acoustics.certification import part36_g_limit, part36_g_reference_height
from acdt.core.acoustics.propagation import Atmosphere, Component, detection_range, flyover, received
from acdt.core.acoustics.rotor import FT, gutin_english_dyn_cm2, gutin_prms, rotor_components

LBF = 4.4482216152605
EX = Path(__file__).resolve().parents[1] / "examples"


def _case(cid: str) -> dict:
    rep = vv.run(ids=[cid])
    return rep["cases"][0]


def test_gutin_si_matches_english_engineering_form():
    """Termo de empuxo: o prefator 169,3 = 478,8/(2√2) coincide a 1e-3. Termo de binário: a forma de engenharia
    usa 0,76 P_h/M_t², que é 550/(0,64 c) com c ≈ 1131 ft/s; a c = 1116,4 ft/s o exato é 0,770 (1,3 %)."""
    c = 1116.4 * FT
    for B, rpm, R, T, P, th in [(2, 2400, 1.0, 1500.0, 80e3, 100), (3, 6000, 0.3, 60.0, 3e3, 80),
                                (4, 1200, 2.0, 5000.0, 300e3, 120)]:
        om = rpm / 60 * 2 * math.pi
        Mt = om * R / c
        for m in (1, 2, 3):
            si_t = gutin_prms(m, B, om, T, 0.0, 150.0, math.radians(th), c, R)
            en_t = 0.1 * gutin_english_dyn_cm2(m, B, R / FT, Mt, 150.0 / FT, 0.0, T / LBF, math.radians(th))
            assert si_t == pytest.approx(en_t, rel=1e-3)
            si_q = gutin_prms(m, B, om, 0.0, P / om, 150.0, math.radians(th), c, R)
            en_q = 0.1 * gutin_english_dyn_cm2(m, B, R / FT, Mt, 150.0 / FT, P / 745.69987, 0.0, math.radians(th))
            assert si_q == pytest.approx(en_q * (550.0 / (0.64 * 1116.4)) / 0.76, rel=1e-3)


def test_gutin_on_axis_is_silent_and_scales_with_distance():
    om = 2400 / 60 * 2 * math.pi
    assert gutin_prms(1, 2, om, 1000.0, 300.0, 50.0, 0.0, 340.0, 1.0) == 0.0  # J_mB(0) = 0
    p1 = gutin_prms(1, 2, om, 1000.0, 300.0, 50.0, 1.7, 340.0, 1.0)
    p2 = gutin_prms(1, 2, om, 1000.0, 300.0, 100.0, 1.7, 340.0, 1.0)
    assert p1 / p2 == pytest.approx(2.0)


def test_skm_marte_kurtz_example():
    assert _case("NOISE-SKM-EXAMPLE")["status"] == "passa"


def test_a_weighting_table():
    assert _case("NOISE-AWEIGHT")["status"] == "passa"
    assert a_weighting(1000.0) == pytest.approx(0.0, abs=2e-3)
    assert a_weighting(0.0) == -math.inf


def test_iso9613_table():
    assert _case("NOISE-ISO9613-ALPHA")["status"] == "passa"
    assert alpha_iso9613(4000, 20, 70) > alpha_iso9613(1000, 20, 70) > alpha_iso9613(250, 20, 70) > 0


def test_part36_limits():
    assert _case("NOISE-P36G-LIMITS")["status"] == "passa"
    # patamares atingidos onde o texto diz (≈ 1400 kg e ≈ 1500 kg)
    assert part36_g_limit(600 * 2 ** (12 / 9.83), False) == pytest.approx(88.0)
    assert part36_g_limit(570 * 2 ** (15 / 10.75), True) == pytest.approx(85.0)
    assert part36_g_limit(9000, True) is None
    H = part36_g_reference_height(500.0, 3.0, 40.0)
    assert H == pytest.approx(15.24 + 2000.0 * 3.0 / math.sqrt(40.0 ** 2 - 9.0))
    assert part36_g_reference_height(2600.0, 3.0, 40.0) is None


def test_iso226_threshold():
    assert threshold_iso226(1000.0) == pytest.approx(2.4)
    assert threshold_iso226(4000.0) == pytest.approx(-5.4)
    assert threshold_iso226(10.0) is None and threshold_iso226(16000.0) is None  # desconhecido, nunca 0
    t = threshold_iso226(math.sqrt(1000.0 * 1250.0))
    assert t == pytest.approx(0.5 * (2.4 + 3.5))


def test_levels():
    assert level_sum([60.0, 60.0]) == pytest.approx(63.0103, abs=1e-3)
    assert level_sum([]) == -math.inf and lp_from_prms(0.0) == -math.inf
    assert lp_from_prms(1.0) == pytest.approx(93.9794, abs=1e-3)


def _rotor():
    return rotor_components(B=2, R=0.3, rpm=6000, T=60.0, P=3000.0, c=340.0, rho=1.225, blade_area_m2=0.02,
                            h_proj_m=0.004)


def test_propagation_flyover_and_detection():
    comps, info = _rotor()
    assert info["broadband_in_sum"] and len(comps) == 16
    atm = Atmosphere(15.0, 70.0, 101.325, 340.0)
    a = received(comps, 100.0, math.pi / 2, atm)
    b = received(comps, 400.0, math.pi / 2, atm)
    assert a.LA > b.LA + 12.0  # divergência (12 dB) + absorção
    fly = flyover(comps, 100.0, 25.0, atm)
    assert fly["LAmax_dBA"] >= a.LA - 1e-9 and math.isfinite(fly["SEL_dBA"])
    q = detection_range(comps, atm, 25.0 / 340.0)
    amb = {f: 40.0 for f in (50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000,
                              2500, 3150, 4000, 5000, 6300, 8000, 10000)}
    m = detection_range(comps, atm, 25.0 / 340.0, amb, 0.0)
    assert q["range_m"] is not None and m["range_m"] is not None and q["range_m"] > m["range_m"] > 100.0


def test_detection_none_when_inaudible():
    silent = [Component("x", 1000.0, lambda r, th: -50.0)]
    assert detection_range(silent, Atmosphere())["range_m"] is None


def test_noise_evaluator_lower_bound_semantics():
    from acdt.core.verification import TracedRequirement, VerificationContext, classify, resolve_evaluator
    import acdt.domains.aircraft.verification_evaluators  # noqa: F401  (regista os avaliadores)

    ev, arg = resolve_evaluator("ruido:overhead_LAmax_dBA")
    req = TracedRequirement(id="N1", text="ruído", quantity="noise", comparison="max", threshold=60.0,
                            unit="dB")
    inc = {"noise": {"evaluated": True, "sources_complete": False, "overhead_LAmax_dBA": 55.0}}
    assert classify(req, ev.fn(req, VerificationContext(inc), arg))[0] == "desconhecido"
    inc["noise"]["overhead_LAmax_dBA"] = 65.0
    assert classify(req, ev.fn(req, VerificationContext(inc), arg))[0] == "falha"
    ok = {"noise": {"evaluated": True, "sources_complete": True, "overhead_LAmax_dBA": 55.0}}
    assert classify(req, ev.fn(req, VerificationContext(ok), arg))[0] == "passa"
    ne = {"noise": {"evaluated": False, "reason": "jato"}}
    assert classify(req, ev.fn(req, VerificationContext(ne), arg))[0] == "nao_avaliado"
    assert classify(req, ev.fn(req, VerificationContext({}), arg))[0] == "nao_avaliado"


@pytest.mark.slow
def test_noise_stage_in_pipeline_c172():
    """C172 com o mapa BEMT: secção noise, design.json (ruido/L0), requisitos e Parte 36 Ap. G."""
    import yaml

    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec

    d = yaml.safe_load((EX / "cessna172_check.yaml").read_text(encoding="utf-8"))
    d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
    d["assumptions"]["noise"] = {"certification": {"part36_G": {}}}
    d["requirements"]["noise"] = {"max": 40, "unit": "dBA", "id": "NZ-01"}
    d["requirements"]["aural_detection_range"] = {"max": 1, "unit": "km", "id": "NZ-02"}
    spec = MissionSpec.from_dict(d, EX / "cessna172_check.yaml")
    st = run_pipeline("aircraft", spec)
    nz = st["result"].noise
    assert nz["evaluated"] and nz["level"] == "L0" and nz["sources_complete"] is False
    assert 20.0 < nz["overhead_LAmax_dBA"] < 90.0
    assert nz["detection_ground_range_m"] > 1000.0
    p = nz["part36_G"]
    assert p["rule"] == "G36.301(c)"
    assert p["limit_dBA"] == pytest.approx(part36_g_limit(st["result"].sizing.W0, True))
    assert p["reference_height_m"] and p["reference_height_m"] > 100.0
    assert p["ok"] in (False, None)  # fontes incompletas: nunca passa
    rows = {r["id"]: r for r in st["verification"]["rows"]}
    assert rows["NZ-01"]["status"] in ("falha", "desconhecido")
    assert rows["NZ-02"]["status"] == "falha"  # limite inferior já excede 1 km
    db = st["design"]
    assert "L0" in db["results"]["ruido"]


def test_noise_not_evaluated_for_jet_and_without_propeller_map():
    from types import SimpleNamespace

    from acdt.domains.aircraft.noise import analyse_noise
    r = analyse_noise(SimpleNamespace(spec=SimpleNamespace(propulsion_kind="jet", assumptions={})))
    assert r["evaluated"] is False and r["overhead_LAmax_dBA"] is None


def test_api_rotor_noise_hover_and_flyover():
    from acdt import api

    h = api.rotor_noise(blades=2, diameter_m=0.6, rpm=6000, thrust_N=60, power_W=3000, n_rotors=4, altitude_m=100,
                        blade_area_m2=0.02, projected_thickness_m=0.004)
    f = api.rotor_noise(blades=2, diameter_m=0.6, rpm=6000, thrust_N=60, power_W=3000, n_rotors=4, altitude_m=100,
                        speed_m_s=20, blade_area_m2=0.02, projected_thickness_m=0.004)
    one = api.rotor_noise(blades=2, diameter_m=0.6, rpm=6000, thrust_N=60, power_W=3000, n_rotors=1, altitude_m=100,
                          blade_area_m2=0.02, projected_thickness_m=0.004)
    assert h["overhead_LA_dBA"] - one["overhead_LA_dBA"] == pytest.approx(10 * math.log10(4), abs=1e-6)
    assert f["flyover"]["LAmax_dBA"] >= f["overhead_LA_dBA"] - 1e-9 and f["flyover"]["SEL_dBA"] is not None
    assert h["detection_ground_range_quiet_m"] > 100.0
