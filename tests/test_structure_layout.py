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
    ids = {m["id"] for m in r["members"] if m["kind"] == "ferragem"}
    assert {"ferragem.boom.1", "ferragem.boom~m.1"} <= ids          # ferragens das duas ligações dos booms
    assert not any(i.startswith("ferragem.estabilizador") for i in ids)   # a cauda está nos booms


# ------------------------------------------------------------------ incremento B: ferragens
PSI, INCH, LBF = 6894.757, 0.0254, 4.44822


def test_lug_reproduces_affdl_example():
    """AFFDL-TR-69-42 §9.6: olhal macho 7075-T651, garfo 2024-T351, cavilha 4130 (sem casquilhos aqui)."""
    from acdt.core.structures import fittings as ft
    assert ft.k_bearing(1.24) == pytest.approx(1.46, abs=0.02)          # K = 1,46 a e/D = 1,24 (exemplo)
    assert ft.k_bearing(1.50) == pytest.approx(1.33, abs=0.01)          # K = 1,33 a e/D = 1,5 (exemplo)
    kn, _ = ft.k_net(0.40, 0.625, 0.051)
    assert kn is not None and 0.70 <= kn <= 0.74                      # exemplo 0,74 (lemos a curva 0,1)
    male = {"Ftu": 77000 * PSI, "Fty": 66000 * PSI, "E": 10.3e6 * PSI}
    fem = {"Ftu": 64000 * PSI, "Fty": 40000 * PSI, "E": 10.5e6 * PSI}
    pin = {"Ftu": 125000 * PSI, "Fsu": 82000 * PSI}
    r = ft.lug_joint(1.0, 1.0 * INCH, 0.75 * INCH, 3.0 * INCH, 1.5 * INCH, male, pin, t_clevis=0.5 * INCH,
                     g=0.1 * INCH, eps_u=0.12, clevis=fem, w_clevis=2.5 * INCH, e_clevis=1.25 * INCH,
                     eps_u_clevis=0.12, D_pin=0.75 * INCH)
    assert r.P_bru_N / LBF == pytest.approx(77000, rel=0.01)
    assert r.P_pin_shear_N / LBF == pytest.approx(72400, rel=0.005)
    assert r.P_pin_bending_N / LBF == pytest.approx(30100, rel=0.01)
    assert r.mode == "flexão da cavilha" and r.verdict == "passa"


def test_k_net_unknown_ductility_is_conservative_and_thin_lug_unknown():
    from acdt.core.structures import fittings as ft
    assert ft.k_net(0.4, 0.62, None)[0] < ft.k_net(0.4, 0.62, 0.05)[0]
    assert ft.k_net(0.4, 0.5, 0.05)[0] is None
    al = sl.material_dict("al7075_t6")
    st = sl.material_dict("steel_4130")
    r = ft.lug_joint(1000.0, 0.02, 0.003, 0.06, 0.03, al, st)       # D/t = 6,7 > 5
    assert r.P_bru_N is None and r.verdict == "desconhecido"
    s = ft.size_lug(30e3, al, st)
    assert s["mass_kg"] > 0 and s["res"].RF >= 1.0 and s["D_m"] / s["t_m"] <= 5.0 + 1e-9


def test_engine_mount_truss_equilibrium():
    from acdt.core.structures import fittings as ft
    st = sl.material_dict("steel_4130")
    W = 1000.0
    r = ft.engine_mount(np.zeros(3), np.zeros(3), 0.0, 0.2, 0.15, 0.4, st,
                        cases=[("v", np.array([0.0, 0.0, -W]), np.zeros(3))])
    assert r["verdict"] == "passa" and r["mass_kg"] > 0
    fw = np.array(r["nodes_firewall"])
    en = np.array(r["nodes_engine"])
    Fz = 0.0
    for t in r["tubes"]:      # um só caso: N = extremo de tração + extremo de compressão (um deles é 0)
        i, j = int(t["nodes"][0][-1]) - 1, int(t["nodes"][1][-1]) - 1
        u = fw[j] - en[i]
        Fz += (t["N_tension_limit_N"] + t["N_compression_limit_N"]) * u[2] / np.linalg.norm(u)
    assert Fz == pytest.approx(W, rel=1e-6)                     # tubos sustentam o peso do motor


def test_c172_fittings_and_engine_mount(c172):
    r = c172.structure_layout
    fit = [m for m in r["members"] if m["component"] == "ligacoes"]
    kinds = {m["kind"] for m in fit}
    assert {"ferragem", "berco_motor"} <= kinds
    ids = {m["id"].rsplit(".", 1)[0] for m in fit if m["kind"] == "ferragem"}
    assert {"ferragem.asa_fuselagem", "ferragem.trem_principal", "ferragem.estabilizador", "ferragem.deriva"} <= ids
    assert all(m["verdict"] in ("passa", "desconhecido") for m in fit)
    em = r["fittings"]["engine_mount"]
    assert em["verdict"] == "desconhecido"          # n.º de cilindros não declarado no exemplo
    assert any("23.361" in c for c in em["cases"]) and any("23.363" in c for c in em["cases"])
    assert r["budget"]["by_component_kg"]["ligacoes"] > 0


# ------------------------------------------------------------------ incremento C: acoplamento iterar
def _fake(items):
    from types import SimpleNamespace as NS
    return NS(weights=NS(items=[NS(key=k, mass=m) for k, m in items]))


def _lay(rows):
    return {"members": [sl.member(f"m{i}", c, "x", m, x) for i, (c, m, x) in enumerate(rows)],
            "budget": {"unknown_mass": []}}


def test_coupling_items_preserve_mass_and_moment():
    res = _fake([("wing", 120.0), ("fuselage", 90.0), ("main_gear", 70.0)])
    lay = _lay([("asa", 60.0, 2.0), ("asa", 40.0, 2.5), ("fuselagem", 100.0, 3.0), ("ligacoes", 5.0, 1.0),
                ("boom", 3.0, 4.0)])
    items, st, notes = sl.coupling_items(res, lay)
    d = {i["name"]: i["mass_kg"] for i in items}
    assert d["estrutura_parametrica:wing"] == pytest.approx(100.0 - 120.0)
    assert d["estrutura_parametrica:fuselage"] == pytest.approx(10.0)
    assert d["estrutura_parametrica:ligacoes"] == pytest.approx(5.0) and d["estrutura_parametrica:boom"] == 3.0
    x_w = (60 * 2.0 + 40 * 2.5) / 100
    assert st["wing"] == ["m", pytest.approx(x_w)] and st["estrutura_parametrica:wing"] == ["m", pytest.approx(x_w)]
    # item original + correção = massa paramétrica, no CG paramétrico → momento igual ao da estrutura paramétrica
    assert (120.0 + d["estrutura_parametrica:wing"]) * st["wing"][1] == pytest.approx(60 * 2.0 + 40 * 2.5)
    assert "main_gear" not in st


def test_coupling_items_assembly_single_correction():
    res = _fake([("asm:wing", 17.0), ("asm:pod", 4.0), ("main_gear", 10.0)])
    items, st, notes = sl.coupling_items(res, _lay([("asa", 6.0, 1.0), ("fuselagem", 12.0, 0.8), ("boom", 3.0, 2.0)]))
    assert len(items) == 1 and items[0]["mass_kg"] == pytest.approx(21.0 - 21.0)
    assert any("montagem" in n for n in notes)


def test_c172_iterar_converges_and_sets_balance_stations():
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec
    d = yaml.safe_load((EX / "cessna172_check.yaml").read_text(encoding="utf-8"))
    d.setdefault("assumptions", {})["structure_layout"] = {"enabled": True, "coupling": "iterar",
                                                          "fittings": {"engine_mount": {"n_cylinders": 4}}}
    res = run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "cessna172_check.yaml"))["result"]
    loop = res.structure_coupling
    assert loop["converged"] and 2 <= len(loop["history"]) <= 8
    W = [h["W0_kg"] for h in loop["history"]]
    assert abs(W[-1] - W[-2]) / W[-1] < 1e-3 and abs(W[-1] - W[0]) > 1.0       # o acoplamento mexe no W0
    st = res.spec.assumptions["stability"]["stations"]
    assert st["wing"][0] == "m" and st["fuselage"][0] == "m"
    keys = [i.key for i in res.weights.items]
    assert "item:estrutura_parametrica:wing" in keys and "item:estrutura_parametrica:ligacoes" in keys
    assert res.structure_layout["coupling"]["converged"]
    # nada aplicado ao exemplo: o yaml em disco não tem o bloco
    assert "structure_layout" not in (yaml.safe_load((EX / "cessna172_check.yaml").read_text(encoding="utf-8"))
                                      .get("assumptions") or {})


# ------------------------------------------------------------------ incremento D: detalhe da fuselagem
def test_superellipse_section_limits():
    c = fr.section_points(0.5, 8)
    assert c["P"] == pytest.approx(math.pi) and c["circular"]
    e = fr.section_points(0.5, 64, 1.0, 1.0, 2.0)
    assert e["P"] == pytest.approx(math.pi, rel=1e-3) and e["A"] == pytest.approx(math.pi / 4, rel=1e-3)
    sq = fr.section_points(0.5, 64, 1.0, 0.6, 40.0)
    el = fr.section_points(0.5, 64, 1.0, 0.6, 2.0)
    assert el["A"] == pytest.approx(math.pi * 0.5 * 0.3, rel=1e-3)
    assert el["P"] < sq["P"] < 3.2 and el["A"] < sq["A"] < 0.6        # entre a elipse e o retângulo
    assert not sq["circular"]


def test_roark_plate_beta_and_floor_beam():
    assert fr.plate_ss_uniform_beta(1.0, 1.0) == pytest.approx(0.2874)
    assert fr.plate_ss_uniform_beta(0.5, 1.0) == pytest.approx(0.6102)
    mat = sl.material_dict("al2024_t3")
    p = fr.size_floor_panel(0.5, 1.0, 10e3, mat, 0.5e-3)
    assert p["sigma_Pa"] == pytest.approx(0.6102 * 10e3 * 0.25 / p["t_m"] ** 2) and p["RF"] >= 1.0
    b = fr.size_floor_beam(1.0, 5e3, mat, 0.5e-3)
    assert b["M_u_Nm"] == pytest.approx(5e3 / 8) and b["RF"] >= 1.0


def test_pressure_hoop_and_cutout_in_shell():
    mat = sl.material_dict("al2024_t3")
    lay = fr.ShellLayout(n_stringers=24, stringer_kind="z", stringer_h=0.02, stringer_b=0.012, stringer_t=1e-3,
                         skin_t=1e-3, frame_pitch=0.5)
    st0 = fr.ShellStation(0.0, 1.0, 2e4, 5e3, 1e3)
    r0 = fr.shell_station_check(st0, lay, mat)
    stp = fr.ShellStation(0.0, 1.0, 2e4, 5e3, 1e3, p_lim=40e3)
    rp = fr.shell_station_check(stp, lay, mat)
    assert rp["sigma_hoop_Pa"] == pytest.approx(40e3 * 1.0 / 1e-3)
    assert rp["RF_skin_hoop_pressure"] == pytest.approx(mat["Ftu"] / (1.5 * 1.33 * 40e6))
    stc = fr.ShellStation(0.0, 1.0, 2e4, 5e3, 1e3, cutouts=[(60.0, 120.0)])
    rc = fr.shell_station_check(stc, lay, mat)
    assert rc["n_cut"] > 0 and rc["q_skin_N_m"] > r0["q_skin_N_m"] and rc["I_m4"] < r0["I_m4"]
    nc = fr.shell_station_check(fr.ShellStation(0.0, 1.0, 2e4, 5e3, 1e3, w=2.0, h=1.4, n_exp=3.0, p_lim=40e3),
                                lay, mat)
    assert nc["verdict"] != "passa" and nc["pressure_note"]


def _c172_d(extra):
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec
    d = yaml.safe_load((EX / "cessna172_check.yaml").read_text(encoding="utf-8"))
    d.setdefault("assumptions", {})["structure_layout"] = {"enabled": True, "fuselage": extra}
    return run_pipeline("aircraft", MissionSpec.from_dict(d, EX / "cessna172_check.yaml"))["result"].structure_layout


def test_c172_floor_door_pressure():
    r = _c172_d({"cutouts": [{"id": "porta_esq", "x0_m": 1.6, "x1_m": 2.5, "theta_deg": -90.0, "width_deg": 50.0}],
                 "pressure_Pa": 25e3})
    f = r["fuselage"]
    assert f["floor"]["evaluated"] and f["floor"]["q_lim_Pa"] > 0
    kinds = {m["kind"] for m in r["members"]}
    assert {"viga_piso", "piso", "soleira"} <= kinds
    edge = [m for m in r["members"] if m["kind"] == "caverna_pesada" and "abertura:porta_esq" in m["loads"]]
    assert len(edge) == 2
    assert any("pressurizacao" in (m.get("ring") or {}) for m in r["members"] if m["kind"].startswith("caverna"))
    assert all(m["verdict"] in ("passa", "falha", "desconhecido") for m in r["members"])


def test_twin_boom_pod_noncircular_floor_declared():
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec
    p = EX / "uav_twin_boom_shortcut.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d.setdefault("assumptions", {})["structure_layout"] = {
        "enabled": True, "fuselage": {"section": {"w_m": 0.40, "h_m": 0.30, "n_exp": 3.0},
                                      "floor": {"enabled": True, "x0_frac": None, "q_Pa": 3000.0},
                                      "cutouts": [{"id": "alcapao", "x0_frac": 0.35, "x1_frac": 0.55,
                                                   "theta_deg": 180.0, "width_deg": 60.0}]}}
    r = run_pipeline("aircraft", MissionSpec.from_dict(d, p))["result"].structure_layout
    f = r["fuselage"]
    assert f["section"]["noncircular"] and f["floor"]["evaluated"]
    assert any(m["kind"] == "soleira" for m in r["members"])
    assert f["shell_table"][0]["perimeter_m"] < 2 * math.pi * f["shell_table"][0]["R_m"] * 1.5


# ------------------------------------------------------------------ incremento E: flutter do avião inteiro
def _uniform_cantilever(n=30, s=7.5, c=2.0, EI=2e7, GJ=2e6, E=70e9, G=27e9, axis="y"):
    ys = np.linspace(0, s, n + 1)
    nodes = [{"id": i + 1, "xyz": [0.0, float(y), 0.0] if axis == "y" else [0.0, 0.0, float(y)]}
             for i, y in enumerate(ys)]
    comp = "asa" if axis == "y" else "deriva"
    els = [{"id": i + 1, "component": comp, "nodes": [i + 1, i + 2], "A": 1e-4, "I1": EI / E, "I2": 10 * EI / E,
            "J": GJ / G} for i in range(n)]
    return {"material": {"E": E, "G": G}, "nodes": nodes, "elements": els}, ys


@pytest.mark.parametrize("axis", ["y", "z"])
def test_frame_element_cantilever_tip_deflection(axis):
    from acdt.domains.aircraft import structure_flutter as sf
    model, _ = _uniform_cantilever(n=1, s=2.0, axis=axis)
    K, M, keep = sf.assemble(model, {}, fixed=[1])
    P = 1000.0
    f = np.zeros(K.shape[0])
    normal = 2 if axis == "y" else 1                  # carga normal à superfície (I1)
    f[6 + normal] = P
    u = np.zeros_like(f)
    u[keep] = np.linalg.solve(K[np.ix_(keep, keep)], f[keep])
    assert u[6 + normal] == pytest.approx(P * 2.0**3 / (3 * 2e7), rel=1e-9)


def test_beam_flutter_matches_closed_forms_and_binary_model():
    from acdt.domains.aircraft import aeroelasticity as ae
    from acdt.domains.aircraft import structure_flutter as sf
    s, c, EI, GJ, mpl, xf, xcg = 7.5, 2.0, 2e7, 2e6, 200.0, 0.48, 0.5
    model, ys = _uniform_cantilever(s=s, c=c, EI=EI, GJ=GJ)
    surf = {"asa": {"span": s, "c_root": c, "c_tip": c, "e": xf - 0.25, "x_cg_off": xcg - xf, "a_w": 2 * math.pi,
                    "m_per_c": mpl / c}}
    r = sf.flutter_from_beam_model(model, surf, {}, {}, VD_eas=50.0, fixed=[1], n_modes=8)
    fb = 1.8751**2 / (2 * math.pi) * math.sqrt(EI / (mpl * s**4))             # 1.º modo de flexão encastrado
    ft = 1 / (4 * s) * math.sqrt(GJ / (mpl * c**2 * (1 / 12 + (xcg - xf) ** 2)))   # 1.º de torção
    f = [m["f_Hz"] for m in r["modes"]]
    assert f[0] == pytest.approx(fb, rel=0.02) and f[1] == pytest.approx(ft, rel=0.02)
    ws = ae.WingStrip(ys, np.full_like(ys, c), np.full_like(ys, EI), np.full_like(ys, GJ), np.full_like(ys, mpl),
                      xf - 0.25, xf, xcg, 2 * math.pi)
    VF_wc = ae.flutter_estimate_typical_section(ws, V_max=400)["V_F"]
    Vdiv = ae.torsional_divergence_speed(ws)["V_div"]          # forma fechada das faixas
    assert r["V_F_eas"] == pytest.approx(VF_wc, rel=0.10)
    assert r["V_div_eas"] == pytest.approx(Vdiv, rel=0.03)
    assert r["verdict"] == "passa"                 # 1,2 × 50 < V_F


def test_c172_whole_aircraft_flutter(c172):
    fl = c172.structure_layout["flutter"]
    assert fl["evaluated"] and fl["verdict"] in ("passa", "falha")
    assert fl["n_modes"] >= 8 and all(m["f_Hz"] > 0.5 for m in fl["modes"])
    assert {"asa", "estabilizador", "deriva"} <= set(fl["surfaces"])
    assert fl["mass_kg"] == pytest.approx(c172.sizing.W0, rel=0.02)
    assert fl["V_F_eas"] > fl["V_D_eas"]


def test_twin_boom_whole_aircraft_flutter():
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec
    p = EX / "uav_twin_boom_shortcut.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d.setdefault("assumptions", {})["structure_layout"] = {"enabled": True}
    r = run_pipeline("aircraft", MissionSpec.from_dict(d, p))["result"].structure_layout
    fl = r["flutter"]
    assert fl["evaluated"] and math.isfinite(fl["V_F_eas"]) or math.isinf(fl["V_F_eas"])
    assert any(m["component"].startswith("boom") for m in fl["modes"])
    # empenagem ao centro presa a um só boom: número relatado, veredicto desconhecido
    assert fl["verdict"] == "desconhecido" and fl["verdict_computed"] in ("passa", "falha")
# ------------------------------------------------------------------ render 3-D da estrutura
def test_layout_geometry_and_render(c172, tmp_path):
    from acdt.domains.aircraft.structure_render import render_layout
    r = c172.structure_layout
    g = r["geometry"]
    assert [b["comp"] for b in g["bodies"]] == ["fuselagem"]
    assert {s["comp"] for s in g["surfaces"]} == {"asa", "estabilizador", "deriva"}
    fus = g["bodies"][0]
    assert len(fus["frames"]) == sum(1 for m in r["members"] if m["kind"].startswith("caverna"))
    assert fus["bulkheads"] and fus["floor"] and fus["n_stringers"] > 0
    for mode in ("kind", "RF"):
        p = render_layout(r, tmp_path / f"c172_{mode}.png", color_by=mode, dpi=60)
        assert p.exists() and p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and p.stat().st_size > 10_000
