# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Planador em compósito (docs/PLANADOR_COMPOSITO.md): CS-22, casca em sanduíche, propulsão none, perfil da
fuselagem, polar planada e o modo de construção composito_monocasca (exemplo examples/benchmarks/ls4)."""
from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest
import yaml

from acdt.core import materials as matlib
from acdt.core.structures import sandwich as sw
from acdt.domains.aircraft import structures as S
from acdt.domains.aircraft.glide import glide_polar

EX = Path(__file__).resolve().parents[1] / "examples" / "benchmarks" / "ls4"
G0 = 9.80665


# ------------------------------------------------------------------ casca em sanduíche
GL = matlib.get("gfrp_qi")
FACE = sw.Face(GL.E, GL.nu, GL.rho, GL.Fcy, GL.Ftu, GL.Fsu)
CORE = sw.Core(95e6, 27e6, 80.0)


def test_monolithic_wall_reduces_to_isotropic_cylinder():
    """t_c = 0: N_cr clássico = E t²/(R √(3(1−ν²))) (Timoshenko & Gere) e φ ≈ √(R/t)/16 (SP-8007)."""
    t, R = 2e-3, 0.4
    D, Eh = sw.stiffness(t / 2, 0.0, FACE)
    assert 2 * math.sqrt(D * Eh) / R == pytest.approx(FACE.E * t**2 / (R * math.sqrt(3 * (1 - FACE.nu**2))))
    phi_iso = math.sqrt(R / t) / 16
    g_iso = 1 - 0.731 * (1 - math.exp(-phi_iso))
    assert sw.bending_knockdown(R, D, Eh) == pytest.approx(g_iso, rel=0.03)


def test_sandwich_stiffness_and_wrinkling():
    """Allen 1969: D = E t_f d²/(2(1−ν²)); Hoff & Mautner σ_wr = 0,5 (E_f E_c G_c)^⅓."""
    tf, tc = 0.5e-3, 5e-3
    D, Eh = sw.stiffness(tf, tc, FACE)
    assert D == pytest.approx(FACE.E * tf * (tc + tf) ** 2 / (2 * (1 - FACE.nu**2)))
    assert Eh == pytest.approx(2 * FACE.E * tf)
    c = sw.check_wall(1e4, 0.0, 0.3, 1.0, tf, tc, FACE, CORE)
    assert c["sigma_wrinkling_Pa"] == pytest.approx(0.5 * (FACE.E * CORE.E * CORE.G) ** (1 / 3))
    assert c["RF_face_compression"] == pytest.approx(FACE.Fcy / (1e4 / (2 * tf)))


def test_size_wall_lightest_feasible_and_monotonic():
    tfs = [k * 0.25e-3 for k in range(2, 13)]
    tcs = [0.0, 3e-3, 5e-3, 10e-3]
    lo = sw.size_wall(2e4, 5e3, 0.35, 1.5, FACE, CORE, tfs, tcs)
    hi = sw.size_wall(2e5, 5e4, 0.35, 1.5, FACE, CORE, tfs, tcs)
    assert lo["ok"] and hi["ok"] and lo["RF_min"] >= 1.0 and hi["RF_min"] >= 1.0
    assert hi["areal_mass_kg_m2"] > lo["areal_mass_kg_m2"]
    # nenhuma parede mais leve da grelha passa
    for tc in tcs:
        for tf in tfs:
            c = sw.check_wall(2e4, 5e3, 0.35, 1.5, tf, tc, FACE, CORE)
            if c["areal_mass_kg_m2"] < lo["areal_mass_kg_m2"] - 1e-12:
                assert c["RF_min"] < 1.0
    bad = sw.size_wall(1e9, 0.0, 0.35, 1.5, FACE, CORE, tfs, tcs)
    assert not bad["ok"]


# ------------------------------------------------------------------ CS-22
def test_cs22_load_factors_and_speeds():
    """CS 22.337 (U: +5,3/+4,0/−1,5/−2,65), 22.335(a) VA = VS1 √n1, 22.335(f) VD mínimo, 22.341 k."""
    assert S.CS22_N["U"] == (5.3, 4.0, -1.5, -2.65) and S.CS22_N["A"] == (7.0, 7.0, -5.0, -5.0)
    assert S.regulation_min_n(472, "utility", "cs_22") == 5.3
    ws = 472 * G0 / 10.5
    assert S.cs22_vd_min(ws, 0.01) == pytest.approx(18 * (ws / 10) ** (1 / 3) * 10 / 3.6)
    assert S.cs22_vd_min(ws, None) is None
    assert S.cs22_vd_min(ws, None, "A") == pytest.approx((3.5 * ws / 10 + 200) / 3.6)
    k, mu = S.cs22_gust_k(ws, 0.7, 5.5, 1.225)
    assert mu == pytest.approx(2 * (ws / G0) / (1.225 * 0.7 * 5.5))
    r = mu / (12.17 + 0.191 * mu)
    assert k == pytest.approx(0.96 * r / (0.475 + r))
    vn = S.v_n_diagram(472, 10.5, 1.3, 5.5, 0.75, 30.0, "utility", "cs_22", VD_eas=83.33, lm=0.7)
    assert vn.regulation == "cs_22" and vn.VA == pytest.approx(vn.VS1 * math.sqrt(5.3))
    assert vn.VD == pytest.approx(83.33) and vn.gust["Ude_VC"] == 15.0 and vn.gust["Ude_VD"] == 7.5
    # CS 22.341(b): positivo limitado por 1,25 (V/VS1)²
    assert vn.gust["n_VC_pos"] <= 1.25 * (vn.VA / vn.VS1) ** 2 + 1e-9
    assert vn.n_pos >= 5.3 and vn.n_neg <= -2.65


def test_resolve_material_dict_and_glider_cap():
    m = S.resolve_material({"skin": "gfrp_pm45", "cap": "gfrp_ud_cap", "core": "pvc_foam_h80"})
    assert isinstance(m, dict) and m["E_cap"] == pytest.approx(41e9) and m["sigma_cap"] == pytest.approx(300e6)
    assert m["core"]["rho"] == pytest.approx(80.0)
    assert S.resolve_material("al2024_t3") == "al2024_t3"
    cap = matlib.get("gfrp_ud_cap")
    assert cap.Fcy == cap.Ftu == pytest.approx(matlib.GLIDER_GFRP_CAP_ULT_PA)


# ------------------------------------------------------------------ polar planada
def test_glide_polar_closed_form():
    """(L/D)max = 1/(2√(CD0 K)); afundamento mínimo a CL = √(3 CD0/K) (Anderson 1999 §5.4)."""
    CD0, K, Sw, m = 0.010, 0.016, 10.5, 320.0
    g = glide_polar(Sw, CD0, K, 1.4, m)
    assert g.LD_max == pytest.approx(1 / (2 * math.sqrt(CD0 * K)))
    CL = math.sqrt(3 * CD0 / K)
    V = math.sqrt(2 * m * G0 / (g.rho * Sw * CL))
    assert g.V_min_sink == pytest.approx(V)
    assert g.sink_min == pytest.approx(V * (CD0 + K * CL**2) / CL)
    assert all(g.sink(v) >= g.sink_min - 1e-12 for v, _ in g.points)
    # polar de velocidades escala com √(m) (Thomas 1999 §4.3)
    g2 = glide_polar(Sw, CD0, K, 1.4, 4 * m)
    assert g2.V_best_LD == pytest.approx(2 * g.V_best_LD) and g2.LD_max == pytest.approx(g.LD_max)
    with pytest.raises(ValueError):
        glide_polar(Sw, 0.0, K, 1.4, m)


# ------------------------------------------------------------------ perfil da fuselagem
def test_fuselage_profile_validation_and_area():
    from acdt.core.pipeline import InfeasibleError
    from acdt.domains.aircraft.geometry import Fuselage
    from acdt.domains.aircraft.sizing import fuselage_profile
    p = fuselage_profile([[0, 0.5], [0.5, 1.0], [1, 0.5]])
    assert p == ((0.0, 0.5), (0.5, 1.0), (1.0, 0.5))
    for bad in ([[0, 0.0], [1, 1.0]], [[0, 1.0], [0.9, 0.5]], [[0, 0.5], [1, 0.9]], [[0.5, 1], [0, 1], [1, 1]]):
        with pytest.raises(InfeasibleError):
            fuselage_profile(bad)
    f = Fuselage(length=4.0, max_diameter=1.0)
    f.profile = ((0.0, 1.0), (1.0, 1.0))           # cilindro: 2π R L
    assert f.radius(1.3) == pytest.approx(0.5)
    assert f.wetted_area() == pytest.approx(2 * math.pi * 0.5 * 4.0, rel=1e-3)


# ------------------------------------------------------------------ exemplo LS4 (rápido: aero de manual)
@pytest.fixture(scope="module")
def ls4():
    from acdt.domains.aircraft import structure_layout as sl
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.sizing import run
    d = yaml.safe_load((EX / "ls4.yaml").read_text(encoding="utf-8"))
    d = copy.deepcopy(d)
    d["assumptions"]["aero"]["fidelity"] = "handbook"
    d["assumptions"]["aero"]["clmax_airfoil"] = 1.38
    d["assumptions"]["structure_layout"]["coupling"] = "relatorio"
    d["assumptions"]["structure_layout"]["flutter"] = {"enabled": False}
    res = run(MissionSpec.from_dict(d, EX / "ls4.yaml"))
    return res, sl.analyse_layout(res)


def test_ls4_unpowered_closure_and_cs22(ls4):
    res, _ = ls4
    sz = res.sizing
    assert sz.Wf == pytest.approx(0.0)
    assert sz.W0 == pytest.approx(sz.We + 110.0 + 124.0, rel=1e-6)
    assert res.structures.vn.regulation == "cs_22"
    assert res.structures.vn.VD == pytest.approx(83.333)
    assert res.sizing.W0 * G0 / res.S == pytest.approx(440.85, rel=1e-3)     # carga alar fixa
    assert not any("No range/endurance" in str(i.message) for i in res.issues)


def test_ls4_composite_layout_few_stiffeners(ls4):
    _, lay = ls4
    fus = lay["fuselage"]
    assert fus["layout"]["construction"] == "composito_monocasca" and fus["layout"]["n_stringers"] == 0
    kinds = {m["kind"] for m in lay["members"] if m["component"] == "fuselagem"}
    assert "reforcador" not in kinds and {"revestimento", "antepara"} <= kinds
    # só estações de carga + 3 anteparas declaradas (nada de passo regular)
    assert len(fus["frames"]) <= 10
    surf = {s["comp"]: s for s in lay["geometry"]["surfaces"]}
    assert surf["asa"]["rib_eta"] == [0.0, 0.25, 0.45, 0.55, 0.78, 1.0]
    # cauda em T: raiz do estabilizador na ponta da deriva; asa de ombro acima do eixo
    fin, ht = surf["deriva"], surf["estabilizador"]
    assert ht["root_c4_m"][2] == pytest.approx(fin["root_c4_m"][2] + fin["span_vec_m"][2])
    assert surf["asa"]["root_c4_m"][2] > 0.2
    assert all(r["ok"] for r in fus["shell_table"])


def test_construction_option_rejects_unknown():
    from acdt.domains.aircraft import structure_layout as sl
    with pytest.raises(ValueError):
        sl.is_composite({"construction": "madeira"})
    assert not sl.is_composite({}) and sl.is_composite({"construction": "composito_monocasca"})
