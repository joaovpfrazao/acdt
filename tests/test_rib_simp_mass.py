"""Opt-in SIMP-informed rib-web mass in the Phase 6 structural budget.

Illustrative / PRESSUPOSTO inputs only — not a real FEM or vendor result.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import numpy as np

from acdt.domains.aircraft import structures as S
from acdt.domains.aircraft.geometry import TrapezoidalWing
from acdt.domains.aircraft.wingbox.rib_simp_mass import (
    apply_simp_rib_mass,
    apply_to_box,
    rib_web_mass_from_simp,
)
from acdt.domains.aircraft.wingbox import sizing6 as Z


def _wing_case(kind="metal"):
    w = TrapezoidalWing(S=10.0, AR=8.0, taper=0.6, tc_root=0.15, tc_tip=0.12, airfoil="NACA 2412")
    w.box.front_spar_xc, w.box.rear_spar_xc, w.box.rib_pitch = 0.2, 0.65, 0.6
    y = np.linspace(0, w.span / 2, 41)
    c = S.chord_at(w, y)
    lift = 3.8 * 1000 * 9.81 / 2 * c / np.trapezoid(c, y)
    V = S._cum_from_tip(y, lift)
    M = S._cum_from_tip(y, V)
    T = S._cum_from_tip(y, -0.02 * c * lift)
    beam = S.BeamLoads(y, V, M, T)
    mat = Z.phase6_material(kind)
    x = {"xf": 0.2, "xr": 0.65, "rib_pitch": 0.6, "k_skin": 1.0, "phi_cap": 0.15, "n_str": 6}
    box = Z.size_box6(w, beam, mat, x, y0=0.6)
    return w, beam, mat, x, box

RHO = 2780.0
RHO_SRC = "MIL-HDBK-5J Table 3.2.3.0(b) — typical/S-basis (as Phase 3 MATERIALS)"
T_SRC = "EXAMPLE/PRESSUPOSTO: thickness taken as if from sizing6.size_ribs (Niu 1988 §5.4)"
ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "wingbox"


def _two_rib_case():
    masses = {
        "caps": 8.0, "box_skins": 0.0, "core": 0.0, "webs": 0.0, "web_uprights": 0.0,
        "LE_TE_skins": 0.0, "ribs": 0.60528384, "ideal": 10.60528384,
        "nonoptimum": 2.65132096, "total": 13.2566048,
    }
    ribs = {
        "y": [0.0, 1.0], "w_m": [0.40, 0.32], "h_m": [0.15, 0.12],
        "t_m": [0.001, 0.0008], "t_mm": [1.0, 0.8],
        "dV_N": [500.0, 350.0], "p_crush_N_m": [3000.0, 2200.0],
        "D_h": [0.0, 0.0], "mass_factor": [1.0, 1.0],
        "box_part_kg": [0.1668, 0.0854016], "rest_kg": [0.03336, 0.01708032],
    }
    return masses, ribs


def test_web_mass_is_achieved_volume_times_solid():
    one = rib_web_mass_from_simp(
        w_m=0.40, h_m=0.15, p_crush_N_m=3000.0, dV_N=500.0,
        t_m=0.001, rho_kg_m3=RHO, vol=0.40, penal=3.0,
        nelx=32, iters=30, rho_source=RHO_SRC, t_source=T_SRC,
    )
    assert one["status"] == "ok"
    solid = 0.40 * 0.15 * 0.001 * RHO
    assert one["solid_web_kg"] == pytest.approx(solid)
    assert one["vol_achieved"] == pytest.approx(0.40, abs=0.01)
    assert one["mass_web_kg"] == pytest.approx(one["vol_achieved"] * solid, rel=1e-12)
    # illustrative number (EXAMPLE/PRESSUPOSTO, ~0.0667 kg)
    assert one["mass_web_kg"] == pytest.approx(0.0667, abs=5e-4)


def test_web_unassessed_if_vol_or_source_missing():
    missing_vol = rib_web_mass_from_simp(
        w_m=0.40, h_m=0.15, p_crush_N_m=3000.0, dV_N=500.0,
        t_m=0.001, rho_kg_m3=RHO, vol=None, penal=3.0,
        rho_source=RHO_SRC, t_source=T_SRC,
    )
    assert missing_vol["status"] == "unassessed"
    assert missing_vol["mass_web_kg"] is None
    assert any("vol" in t for t in missing_vol["unassessed_terms"])

    missing_src = rib_web_mass_from_simp(
        w_m=0.40, h_m=0.15, p_crush_N_m=3000.0, dV_N=500.0,
        t_m=0.001, rho_kg_m3=RHO, vol=0.4, penal=3.0,
        rho_source="", t_source=T_SRC,
    )
    assert missing_src["status"] == "unassessed"
    assert missing_src["mass_web_kg"] is None
    assert any("rho_source" in t for t in missing_src["unassessed_terms"])


def test_budget_assessed_replaces_web_keeps_le_te_rest():
    masses, ribs = _two_rib_case()
    sized = masses["ribs"]
    out = apply_simp_rib_mass(
        masses, ribs, rho_kg_m3=RHO, rho_source=RHO_SRC, t_source=T_SRC,
        vol=0.40, penal=3.0, nelx=32, iters=30, stations="all",
        nonoptimum_factor=1.25,
    )
    assert out["status"] == "ok"
    assert out["ribs_sized_kg"] == pytest.approx(sized)
    # LE/TE remainder is unchanged (PRESSUPOSTO, outside SIMP domain)
    assert out["rest_kg_semispan"] == pytest.approx(sum(ribs["rest_kg"]))
    # two semispans; web lighter than the solid/lightening-hole size_ribs box_part
    assert out["ribs_simp_kg"] < sized
    assert out["ribs_simp_kg"] == pytest.approx(0.3026, abs=5e-3)
    assert out["delta_kg"] == pytest.approx(out["ribs_simp_kg"] - sized)
    # original masses dict is not mutated
    assert masses["ribs"] == sized
    assert out["masses_simp"]["ribs"] == pytest.approx(out["ribs_simp_kg"])
    assert out["masses_simp"]["total"] == pytest.approx(1.25 * out["masses_simp"]["ideal"])


def test_root_only_is_unassessed_no_extrapolation():
    masses, ribs = _two_rib_case()
    out = apply_simp_rib_mass(
        masses, ribs, rho_kg_m3=RHO, rho_source=RHO_SRC, t_source=T_SRC,
        vol=0.40, penal=3.0, nelx=24, iters=10, stations="root",
    )
    assert out["status"] == "unassessed"
    assert out["ribs_simp_kg"] is None
    assert out["masses_simp"] is None
    assert any("extrapolation" in t for t in out["unassessed_terms"])
    assert masses["ribs"] == pytest.approx(0.60528384)


def test_budget_unassessed_if_vol_or_penal_missing():
    masses, ribs = _two_rib_case()
    no_vol = apply_simp_rib_mass(
        masses, ribs, rho_kg_m3=RHO, rho_source=RHO_SRC, t_source=T_SRC, penal=3.0,
    )
    assert no_vol["status"] == "unassessed"
    assert any("vol" in t for t in no_vol["unassessed_terms"])
    no_penal = apply_simp_rib_mass(
        masses, ribs, rho_kg_m3=RHO, rho_source=RHO_SRC, t_source=T_SRC, vol=0.4,
    )
    assert no_penal["status"] == "unassessed"
    assert any("penal" in t for t in no_penal["unassessed_terms"])


def test_size_box6_details_additive_and_default_mass_unchanged():
    _, _, _, _, box = _wing_case("metal")
    ribs = box.details["ribs"]
    assert "box_part_kg" in ribs and "rest_kg" in ribs and "mass_factor" in ribs and "t_m" in ribs
    assert len(ribs["box_part_kg"]) == len(ribs["y"])
    # sized mass is still 2 × Σ(box_part + rest)
    rebuilt = 2.0 * (sum(ribs["box_part_kg"]) + sum(ribs["rest_kg"]))
    assert box.masses["ribs"] == pytest.approx(rebuilt, rel=1e-12)
    # opt-in apply is the only path that may change the budget
    before = dict(box.masses)
    report = apply_to_box(box, {"enabled": True}, material=Z.phase6_material("metal"))
    assert report["status"] == "unassessed"  # vol/penal missing
    assert box.masses == before
    assert box.details["rib_simp_mass"]["status"] == "unassessed"


def test_apply_to_box_updates_masses_when_ok():
    _, _, mat, _, box = _wing_case("metal")
    before = box.masses["ribs"]
    report = apply_to_box(
        box,
        {"vol": 0.40, "penal": 3.0, "nelx": 16, "iters": 12, "stations": "all"},
        material=mat,
    )
    assert report["status"] == "ok"
    assert box.masses["ribs"] == pytest.approx(report["ribs_simp_kg"])
    assert box.masses["ribs"] != pytest.approx(before)
    assert "rib_simp_mass" in box.details
    assert box.details["rib_simp_mass"]["status"] == "ok"


def test_cli_and_examples(tmp_path):
    from acdt.cli import main
    out = tmp_path / "ok.json"
    assert main(["rib-simp", "--input", str(EX / "rib_simp_mass_illustrative.json"), "-o", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] == "ok"
    assert data["ribs_simp_kg"] == pytest.approx(0.3026, abs=5e-3)

    bad = tmp_path / "un.json"
    rc = main(["rib-simp", "--input", str(EX / "rib_simp_mass_unassessed.json"), "-o", str(bad)])
    assert rc == 2
    u = json.loads(bad.read_text(encoding="utf-8"))
    assert u["status"] == "unassessed"
    assert u["ribs_simp_kg"] is None
    assert u["masses_simp"] is None

    root = tmp_path / "root.json"
    rc = main(["rib-simp", "--input", str(EX / "rib_simp_mass_root_only.json"), "-o", str(root)])
    assert rc == 2
    r = json.loads(root.read_text(encoding="utf-8"))
    assert r["status"] == "unassessed"
    assert any("extrapolation" in t for t in r["unassessed_terms"])


def test_toolkit_wrapper_matches_cli():
    from acdt.ai.rib_simp import rib_simp_mass
    raw = json.loads((EX / "rib_simp_mass_illustrative.json").read_text(encoding="utf-8"))
    out = rib_simp_mass(raw)
    assert out["status"] == "ok"
    assert out["ribs_simp_kg"] == pytest.approx(0.3026, abs=5e-3)
    missing = rib_simp_mass(json.loads((EX / "rib_simp_mass_unassessed.json").read_text(encoding="utf-8")))
    assert missing["status"] == "unassessed"
    assert missing["ribs_simp_kg"] is None
