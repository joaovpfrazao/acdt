# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Lightweight turbofan maps: correlation default, tables, domain honesty."""
from copy import deepcopy
from pathlib import Path
import pytest
from acdt import G0
from acdt.ai.jet import load_spec, jet_turbofan
from acdt.domains.aircraft.jet.engine_map import engine_point, validate_engine_map
from acdt.domains.aircraft.jet.turbofan import turbofan_point
from acdt.domains.aircraft.jet.sizing import size_jet
from acdt.core.motor_map import motor_efficiency

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "jet"


def test_default_matches_correlation():
    a = turbofan_point(0.5, 5000, 100000)
    b = engine_point(0.5, 5000, 100000, throttle=1.0)
    assert b["map_mode"] == "correlation"
    assert b["thrust_installed_N"] == pytest.approx(a["thrust_installed_N"])
    assert b["TSFC_kg_N_s"] == pytest.approx(a["TSFC_kg_N_s"])


def test_correlation_throttle_scales_thrust_tsfc_unassessed():
    full = engine_point(0.2, 0, 100000, installation_factor=1, throttle=1)
    half = engine_point(0.2, 0, 100000, installation_factor=1, throttle=0.5)
    assert half["thrust_installed_N"] == pytest.approx(0.5 * full["thrust_installed_N"])
    assert half["TSFC_kg_N_s"] == pytest.approx(full["TSFC_kg_N_s"])
    assert half["part_throttle_tsfc"] == "unassessed"
    assert "part_throttle_tsfc_unassessed" in half["issues"]


def test_table_cruise_matches_baseline_sizing():
    base = size_jet(load_spec(EX / "coupled_size.yaml"))
    mapped = size_jet(load_spec(EX / "engine_map_table.yaml"))
    assert mapped["converged"] and base["converged"]
    assert mapped["mtow_kg"] == pytest.approx(base["mtow_kg"], rel=1e-5)
    assert mapped["turbofan_per_engine"]["map_mode"] == "table"
    assert mapped["turbofan_per_engine"]["status"] == "assessed"


def test_table_part_power_tsfc_worse_than_max():
    spec = load_spec(EX / "engine_map_table.yaml")
    m = spec["engine"]["map"]
    full = engine_point(0.79, 11277.6, 120000, installation_factor=0.97, map=m, throttle=1.0)
    part = engine_point(0.79, 11277.6, 120000, installation_factor=0.97, map=m, throttle=0.5)
    assert part["TSFC_kg_N_s"] > full["TSFC_kg_N_s"]
    assert part["thrust_installed_N"] == pytest.approx(0.5 * full["thrust_installed_N"], rel=1e-3)
    assert part["part_throttle_tsfc"] == "from_map"


def test_out_of_domain_unassessed_not_zero():
    spec = load_spec(EX / "engine_map_table.yaml")
    m = deepcopy(spec["engine"]["map"])
    r = engine_point(0.9, 11277.6, 120000, map=m, throttle=1.0)  # M=0.9 outside [0,0.79]
    assert r["status"] == "unassessed"
    assert r["thrust_installed_N"] is None and r["TSFC_kg_N_s"] is None
    assert "engine_map_out_of_domain" in r["issues"]


def test_out_of_domain_error_raises():
    spec = load_spec(EX / "engine_map_table.yaml")
    m = deepcopy(spec["engine"]["map"])
    m["out_of_domain"] = "error"
    with pytest.raises(ValueError, match="outside supplied domain"):
        engine_point(0.9, 0, 120000, map=m, throttle=1.0)


def test_corrected_table_recovery():
    # Single-node corrected map at SLS: F/δ = F_sl, SFC/√θ = TSFC
    tsfc = 0.4 / (G0 * 3600)
    m = dict(mode="corrected_table", source="PRESSUPOSTO", out_of_domain="error",
             axes={"mach": [0.0], "altitude_m": [0.0], "throttle": [1.0]},
             F_over_delta=[[[100000.0]]], SFC_over_sqrt_theta=[[[tsfc]]], totals=False)
    validate_engine_map(m)
    r = engine_point(0.0, 0.0, 100000, installation_factor=1.0, map=m, throttle=1.0)
    assert r["thrust_installed_N"] == pytest.approx(100000)
    assert r["TSFC_kg_N_s"] == pytest.approx(tsfc)


def test_omitting_map_keeps_legacy_size():
    spec = load_spec(EX / "coupled_size.yaml")
    assert "map" not in spec.get("engine", {})
    out = size_jet(spec)
    assert out["turbofan_per_engine"]["map_mode"] == "correlation"
    assert "citations" in out["turbofan_per_engine"]


def test_jet_turbofan_ai_accepts_map():
    m = load_spec(EX / "engine_map_table.yaml")["engine"]["map"]
    r = jet_turbofan(0.79, 11277.6, 120000, map=m, throttle=1.0)
    assert r["map_mode"] == "table" and r["status"] == "assessed"


def test_motor_map_interp_and_ood():
    m = dict(mode="table", source="PRESSUPOSTO", out_of_domain="unassessed",
             points=[{"shaft_power_W": 1000, "efficiency": 0.9},
                     {"shaft_power_W": 5000, "efficiency": 0.85}])
    mid = motor_efficiency(3000, m)
    assert mid["status"] == "assessed"
    assert mid["efficiency"] == pytest.approx(0.9 * 0.5 + 0.85 * 0.5)
    bad = motor_efficiency(9000, m)
    assert bad["status"] == "unassessed" and bad["efficiency"] is None
