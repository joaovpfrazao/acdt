# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Estrutura paramétrica (docs/ESTRUTURA_PARAMETRICA.md): verificações analíticas e integração no C172."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import yaml

from acdt.core.structures import frames as fr
from acdt.domains.aircraft import structure_layout as sl

EX = Path(__file__).resolve().parents[1] / "examples"
AL = sl.material_dict("al2024_t3")


def test_pinched_ring_timoshenko():
    """Anel comprimido por duas forças opostas P: |M| = P R/π nas cargas, P R (1/2 − 1/π) a 90°, N = P/2 a 90°
    (Timoshenko, Strength of Materials Pt. I; Roark cap. 9)."""
    P, R = 1000.0, 0.8
    r = fr.ring_internal_forces(R, [fr.RingLoad(0, Fz=-P), fr.RingLoad(180, Fz=P)], shell_reaction=False)
    th, M = r["theta_deg"], r["M"]
    assert r["M_max_abs"] == pytest.approx(P * R / math.pi, rel=1e-4)
    assert abs(M[np.argmin(abs(th - 90))]) == pytest.approx(P * R * (0.5 - 1 / math.pi), rel=1e-4)
    assert abs(r["N"][np.argmin(abs(th - 90))]) == pytest.approx(P / 2, rel=1e-3)
    assert r["closure_residual"] < 1e-9


def test_ring_shell_reaction_equilibrium_and_coefficient():
    """Força radial P reagida pelo fluxo q = P sin θ/(π R) da casca (Megson): a resultante do fluxo é −P e o
    momento máximo, no ponto de carga, é 3/(4π) P R (forma fechada do mesmo modelo — regressão)."""
    P, R = 500.0, 0.5
    r = fr.ring_internal_forces(R, [fr.RingLoad(180, Fz=P)])
    th = np.radians(r["theta_deg"])
    fz = np.trapezoid(r["q_shell"] * (-np.sin(th)) * R, th)
    assert fz == pytest.approx(-P, rel=1e-4)
    assert r["M_max_abs"] == pytest.approx(3 / (4 * math.pi) * P * R, rel=1e-3)
    assert r["theta_M_max_deg"] == pytest.approx(180.0, abs=1.0)


def test_ring_rejects_unbalanced_without_shell():
    with pytest.raises(ValueError):
        fr.ring_internal_forces(1.0, [fr.RingLoad(0, Fz=1.0)], shell_reaction=False)


def test_pressure_bulkhead_plate_formulas():
    """Timoshenko & Woinowsky-Krieger: apoiada 3(3+ν) p a²/(8 t²); encastrada 3 p a²/(4 t²)."""
    a, t, p, nu = 0.5, 2e-3, 20e3, AL["nu"]
    ss = fr.pressure_bulkhead(a, t, p, AL)
    cl = fr.pressure_bulkhead(a, t, p, AL, "clamped")
    assert ss["sigma_Pa"] == pytest.approx(3 * (3 + nu) * p * a**2 / (8 * t**2))
    assert cl["sigma_Pa"] == pytest.approx(3 * p * a**2 / (4 * t**2))
    sz = fr.size_pressure_bulkhead(a, p, AL, 0.4e-3)
    assert sz["RF"] == pytest.approx(1.0, rel=1e-6)


def test_euler_johnson_tangent_at_transition():
    """Johnson e Euler coincidem (e são tangentes) em σ = Fcc/2 (Bruhn C2)."""
    E, Fcc = 72e9, 250e6
    Lr = math.pi * math.sqrt(2 * E / Fcc)
    assert fr.euler_johnson(E, Fcc, Lr * 0.999) == pytest.approx(Fcc / 2, rel=1e-2)
    assert fr.euler_johnson(E, Fcc, Lr * 1.001) == pytest.approx(Fcc / 2, rel=1e-2)
    assert fr.euler_johnson(E, Fcc, 1e-6) == pytest.approx(Fcc, rel=1e-6)


def test_shell_idealisation_inertia():
    """n booms iguais B num anel de raio R: I = n B R²/2 (n ≥ 3); sem flexão a largura efetiva é a do painel."""
    lay = fr.ShellLayout(n_stringers=16, skin_t=1e-3, frame_pitch=0.4)
    st = fr.ShellStation(0.0, 0.6, 1e-6, 0.0)
    c = fr.shell_station_check(st, lay, AL)
    B = c["stringer_area_m2"] + c["panel_width_m"] * 1e-3
    assert c["I_m4"] == pytest.approx(16 * B * 0.6**2 / 2, rel=1e-9)


def test_skin_shear_flow_thin_tube():
    """q = V/(π R) + T/(2 π R²) (Megson, tubo circular fino), ao último (×1,5)."""
    lay = fr.ShellLayout(n_stringers=20, skin_t=1e-3)
    c = fr.shell_station_check(fr.ShellStation(0.0, 0.5, 0.0, 1000.0, 200.0), lay, AL)
    assert c["q_skin_N_m"] == pytest.approx(1.5 * (1000 / (math.pi * 0.5) + 200 / (2 * math.pi * 0.25)))


def test_frame_sizing_and_unknown_without_body_moment():
    r = fr.ring_internal_forces(0.5, [fr.RingLoad(180, Fz=5000.0)])
    sz = fr.size_frame("z", 0.03, 0.02, 0.5e-3, AL, 1.5 * r["M"], 1.5 * r["N"], 2000.0, 1.0, 0.5)
    assert sz["RF_min"] >= 1.0 and sz["verdict"] == "passa"
    c = fr.frame_check(fr.frame_profile("z", 0.03, 0.02, 1e-3), AL, 0.0, 0.0, None, 1.0, 0.5)
    assert c["RF_shanley"] is None and c["verdict"] == "desconhecido"


def test_shanley_requirement():
    """EI_req = C_f M_ult D²/L com C_f = 1/16 000 (Shanley 1949)."""
    c = fr.frame_check(fr.frame_profile("z", 0.03, 0.02, 1e-3), AL, 0.0, 0.0, 1e4, 1.2, 0.5)
    assert c["EI_req_Nm2"] == pytest.approx(1.5e4 * 1.2**2 / (16000 * 0.5))


def test_budget_cg_inertia():
    ms = [sl.member("a", "c", "k", 2.0, 0.0, I_own=(1.0, 1.0, 1.0), RF=2.0),
          sl.member("b", "c", "k", 2.0, 2.0, RF=2.0),
          sl.member("u", "c", "k", None, 5.0, verdict="desconhecido")]
    b = sl.budget(ms)
    assert b["mass_kg"] == 4.0 and b["cg_m"][0] == pytest.approx(1.0)
    assert b["inertia_kg_m2"]["Iyy"] == pytest.approx(1.0 + 2 * 2.0 * 1.0)
    assert b["unknown_mass"] == ["u"]


def test_boom_cantilever_root_moment():
    o = sl.options(type("S", (), {"assumptions": {}})())
    bd = {"id": "boom_e", "x0_m": 1.0, "length_m": 2.0, "diameter_m": 0.06, "y_m": -1.0,
          "loads": [{"id": "cauda", "x_m": 3.0, "Fz_N": -300.0}]}
    out = sl.boom_layout(bd, o, AL, 1.25)
    assert out["evaluated"]
    root = out["shell_table"][0]
    assert root["sigma_stringer_max_Pa"] > 0
    kinds = {m["kind"] for m in out["members"]}
    assert {"caverna_pesada", "antepara", "revestimento", "reforcador"} <= kinds
    assert all(m["y_m"] == -1.0 for m in out["members"])
    assert not sl.boom_layout({"id": "x", "x0_m": 0, "length_m": 1, "diameter_m": 0.05}, o, AL, 1.25)["evaluated"]


def test_nastran_text_fields():
    model = {"material": {"E": 7e10, "G": 2.7e10, "nu": 0.33},
             "nodes": [{"id": 1, "xyz": [0.0, 0.0, 0.0]}, {"id": 2, "xyz": [1.0, 0.0, 0.0]}],
             "elements": [{"id": 1, "nodes": [1, 2], "A": 1e-4, "I1": 1e-8, "I2": 1e-8, "J": 2e-8}],
             "point_masses": [{"node": 2, "mass_kg": 1.5}]}
    txt = sl.to_nastran(model)
    lines = txt.splitlines()
    assert sum(ln.startswith("GRID") for ln in lines) == 2
    assert sum(ln.startswith("CBAR") for ln in lines) == 1 and "ENDDATA" in lines
    assert all(len(ln) <= 80 for ln in lines if not ln.startswith("$"))


def test_default_is_opt_in():
    o = sl.options(type("S", (), {"assumptions": {}})())
    assert o["enabled"] is False and o["coupling"] == "relatorio"


@pytest.fixture(scope="module")
def c172():
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec
    d = yaml.safe_load((EX / "cessna172_check.yaml").read_text(encoding="utf-8"))
    d.setdefault("assumptions", {})["structure_layout"] = {"enabled": True}
    return run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "cessna172_check.yaml"))["result"]


def test_c172_layout_end_to_end(c172):
    r = c172.structure_layout
    assert r["evaluated"] and r["level"] == "L1"
    kinds = {m["kind"] for m in r["members"]}
    assert {"caverna", "caverna_pesada", "antepara", "revestimento", "reforcador", "painel_reforcado",
            "alma_longarina", "nervura"} <= kinds
    heavy = {i for m in r["members"] if m["kind"] == "caverna_pesada" for i in m["loads"]}
    assert {"asa_longarina_frente", "asa_longarina_tras", "trem_tras", "cauda", "berco_motor"} <= heavy
    assert all(m["verdict"] in ("passa", "falha", "desconhecido") for m in r["members"])
    cmp_ = r["comparison"]
    assert 0.5 < cmp_["fuselage_layout_kg"] / cmp_["fuselage_raymer_kg"] < 2.0
    b = r["budget"]
    assert b["mass_kg"] > 0 and b["inertia_kg_m2"]["Iyy"] > 0
    bm = r["beam_model"]
    assert bm["format"] == "acdt.beam/1" and len(bm["elements"]) == len(bm["nodes"]) - 1 and not bm["missing"]
    assert sum(pm["mass_kg"] for pm in bm["point_masses"]) == pytest.approx(b["mass_kg"], rel=1e-9)
    assert sl.to_nastran(bm).count("CONM2") == len(bm["point_masses"])


def test_c172_tails_through_wingbox(c172):
    r = c172.structure_layout
    comps = {m["component"] for m in r["members"]}
    assert {"asa", "estabilizador", "deriva"} <= comps
    for c in ("estabilizador", "deriva"):
        sf = r["surfaces"][c]
        assert sf["method"] == "buckling" and sf["mass_kg"] > 0
        assert 0.5 < r["comparison"][f"{'htail' if c[0] == 'e' else 'vtail'}_layout_kg"] / \
            r["comparison"][f"{'htail' if c[0] == 'e' else 'vtail'}_L1_kg"] < 2.0
    bm = r["beam_model"]
    comp_el = {e["component"] for e in bm["elements"]}
    assert {"fuselagem", "asa", "estabilizador", "deriva"} <= comp_el
    vt_nodes = {n for e in bm["elements"] if e["component"] == "deriva" for n in e["nodes"]}
    z = [bm["nodes"][n - 1]["xyz"][2] for n in vt_nodes]
    assert max(z) - min(z) > 1.0          # deriva ao longo de +z
    l1 = c172.structures_l1.tails
    assert l1["htail_box"]["EI"][0] > 0 and l1["vtail_box"]["GJ"][0] > 0


def _quadplane() -> dict:
    return {"components": [
        {"type": "body", "name": "fus", "role": "fuselage",
         "stations": [{"x": 0, "w": 0.2, "h": 0.2}, {"x": 1.2, "w": 0.2, "h": 0.2}]},
        {"type": "body", "name": "boom", "role": "boom", "origin": [0.0, 0.8, 0.0], "mirror": True,
         "stations": [{"x": 0, "w": 0.05, "h": 0.05}, {"x": 2.0, "w": 0.05, "h": 0.05}]},
        {"type": "disc", "name": "rf", "role": "lift_rotor", "origin": [0.05, 0.8, 0.05], "mirror": True,
         "diameter": 0.6},
        {"type": "disc", "name": "ra", "role": "lift_rotor", "origin": [1.95, 0.8, 0.05], "mirror": True,
         "diameter": 0.6},
        {"type": "disc", "name": "prop", "role": "propeller", "origin": [1.25, 0, 0], "diameter": 0.4},
        {"type": "surface", "name": "ht", "role": "htail", "origin": [1.8, 0.8, 0.0], "mirror": True,
         "sections": [{"le": [0, 0, 0], "chord": 0.25}, {"le": [0, 0.3, 0], "chord": 0.2}]}]}


def test_vtol_quadplane_booms_rotor_and_tail_loads():
    o = sl.options(type("S", (), {"assumptions": {}})())
    tails = {"htail_limit_lift_N": 200.0, "vtail_limit_lift_N": 100.0, "vtail_box": {"semispan_m": 0.3}}
    booms, notes = sl.booms_from_assembly({"assembly": _quadplane()}, 25.0, tails, o, 0.6)
    assert [b["id"] for b in booms] == ["boom", "boom~m"] and booms[1]["y_m"] == -0.8
    T = 1.5 * 25.0 * 9.80665 / 4
    rot = [ld for ld in booms[0]["loads"] if ld["kind"] == "rotor"]
    assert len(rot) == 2 and rot[0]["Fz_N"] == pytest.approx(T)      # a hélice de propulsão não conta
    tail = [ld for ld in booms[0]["loads"] if ld["kind"] == "tail"][0]
    assert tail["Fz_N"] == pytest.approx(-100.0) and tail["T_Nm"] == pytest.approx(50.0 * 0.12)
    assert any("binário de reação" in n for n in notes)
    out = sl.boom_layout(booms[0], o, AL, 1.25)
    assert out["evaluated"]
    # pairar: rotor de trás a 1,95 m, ligação a 0,6 m -> M = T (1,95 - 0,6); cauda (voo) dá 100 x 1,2 (+y)
    M_hover = T * (1.95 - 0.6)
    M_tail = math.hypot(100.0, 50.0) * (1.8 - 0.6)
    assert out["root_moment_limit_Nm"] == pytest.approx(max(M_hover, M_tail), rel=1e-6)
    heavy = {i for m in out["members"] if m["kind"] == "caverna_pesada" for i in m["loads"]}
    assert {"rotor:rf", "rotor:ra", "cauda"} <= heavy


def test_boom_two_sided_cantilever():
    s = np.linspace(0.0, 2.0, 21)
    V, M, T = sl._boom_loads_integrate(s, 1.0, [(0.0, 10.0, 0.0, 0.0), (2.0, 10.0, 0.0, 3.0)])
    assert M[10] == pytest.approx(10.0) and M[0] == pytest.approx(0.0) and M[-1] == pytest.approx(0.0)
    assert T[15] == pytest.approx(3.0) and T[5] == pytest.approx(0.0)


def test_twin_boom_pipeline_booms_from_assembly():
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec
    p = EX / "uav_twin_boom_shortcut.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d.setdefault("assumptions", {})["structure_layout"] = {"enabled": True}
    r = run_pipeline("aircraft", MissionSpec.from_dict(d, p))["result"].structure_layout
    assert r["evaluated"]
    ev = [b for b in r["booms"] if b.get("evaluated")]
    assert len(ev) == 2 and ev[0]["geometry"]["y_m"] == pytest.approx(-ev[1]["geometry"]["y_m"])
    assert all(b["root_moment_limit_Nm"] > 0 for b in ev)
    bm = r["beam_model"]
    assert len(bm["elements"]) == len(bm["nodes"]) - 1 and not bm["missing"]     # árvore ligada
    assert any(e["component"].startswith("ligacao:") for e in bm["elements"])
    assert r["budget"]["by_component_kg"]["boom"] > 0
