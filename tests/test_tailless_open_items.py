# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Tailless open items (11 nov 2026): biased split actuator, pitch-attitude hold, useful-load packaging at the CG."""
from __future__ import annotations

import json
import math
import types
from pathlib import Path

import numpy as np
import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly import tailless_actuation as TX
from acdt.domains.aircraft.assembly import tailless_trim as TT

EX = Path(__file__).resolve().parents[1] / "examples"
TL = json.loads((EX / "integration" / "flying_wing_pusher_tailless.json").read_text(encoding="utf-8"))


def test_split_actuator_bias_zero_is_the_sin2_law():
    a = TX.SplitActuator(0.01, 60, None, 0.0, 0.0, 0.01)
    b = TX.SplitActuator(0.01, 60, None, 0.0, 0.0, 0.01, bias_deg=0.0)
    for cmd in (0.004, -0.007, 0.0):
        assert a.step(cmd) == pytest.approx(b.step(cmd))
        assert a.s == pytest.approx(math.copysign(math.asin(math.sqrt(abs(cmd) / 0.02)), cmd) if cmd else 0.0)


def test_split_actuator_bias_is_linear_near_zero_and_inverts():
    C1, d0 = 0.01, math.radians(4.0)
    act = TX.SplitActuator(C1, 60, None, 0.0, 0.0, 0.01, bias_deg=4.0)
    d = math.radians(0.1)
    # Rajput et al. 2014 / Wang et al. 2011: ΔC_n = 2C₁ sin2δ0 sin2d
    assert act._dcn_biased(d) == pytest.approx(2 * C1 * math.sin(2 * d0) * math.sin(2 * d), rel=1e-9)
    for cmd in (1e-5, -3e-3, 0.012):
        assert act._dcn_biased(act._d_for_biased(cmd)) == pytest.approx(cmd, rel=1e-6)
    assert act.d_lim == pytest.approx(math.radians(56.0))
    # a sign reversal of ΔC_n needs a finite deflection change (rate stays finite through zero)
    r = TX.SplitActuator(C1, 60, 50.0, 0.0, 0.0, 0.001, bias_deg=4.0)
    for k in range(200):
        r.step(1e-4 * math.sin(2 * math.pi * k / 200))
    assert not r.rate_lim


def test_pitch_hold_gains_beard_mclain_6_4_1():
    Mq, Ma, Mde = -3.0, -20.0, -40.0
    kp, kd, wn = TX.pitch_hold_gains(Mq, Ma, Mde, math.radians(20), math.radians(10))
    assert kp == pytest.approx(-2.0)                      # δe_max/e_θmax · sign(a_θ3)
    assert wn == pytest.approx(math.sqrt(20 + 2 * 40))
    assert kd == pytest.approx((2 * 0.707 * wn - 3.0) / -40.0)


def test_pitch_hold_damps_a_light_phugoid():
    # [u, w, q, θ] shaped like a small UAV at 45 m/s: lightly damped phugoid
    g, u0 = 9.80665, 45.0
    A = np.array([[-0.02, 0.05, 0.0, -g], [-0.4, -4.0, u0, 0.0], [0.0, -0.6, -4.0, 0.0], [0.0, 0.0, 1.0, 0.0]])
    ev0 = np.linalg.eigvals(A)
    ph0 = min(ev0, key=abs)
    cl = TX.pitch_hold_closed_loop(A, 0.3, 0.05, 0.5, -0.5, 0.0, 0.5 * 1.0 * u0**2 * 3.0, 0.8, 140.0, 40.0, u0,
                                   math.radians(17))
    ev = np.linalg.eigvals(cl["A_cl"])
    assert np.all(ev.real < 0)
    slow = min(ev, key=abs)
    z0 = -ph0.real / abs(ph0)
    z1 = -slow.real / abs(slow) if abs(slow.imag) > 1e-9 else 1.0
    assert z1 > z0
    assert "Beard & McLain" in cl["source"]


def test_cg_packaging_fuel_fits_in_the_example():
    asm = Assembly.from_dict(TL["assembly"])
    out = types.SimpleNamespace(loading={
        "rows": {"cheio": [("combustível não posicionado", 22.3), ("carga não posicionada", 27.0)]},
        "cases": {"vazio": {"cg": [0.873, 0.0, 0.0]}}})
    r = TT.cg_packaging(asm, out)
    assert r["status"] == "assessed" and r["fuel_fits"] is True
    assert r["fuel_volume_m3"] == pytest.approx(22.3 / 0.72e3 * 1.02)       # 14 CFR 23.969: 2 % expansion
    assert r["slab_volume_m3"] >= r["fuel_volume_m3"]
    assert 0.02 < r["slab_half_width_m"] < 0.3
    # the gross volume is bounded by the geometry (a bool cast of a signed clearance would fill the bbox)
    tot = sum(r["slab_by_component_m3"].values())
    assert tot == pytest.approx(r["slab_volume_m3"])
    assert "centerbody" in r["slab_by_component_m3"]
    assert "bodies_only" in r and r["payload_volume"].startswith("unassessed")
    assert all(v["payload_density_needed_kg_L"] > 0 for v in r["payload_density_needed"].values())
    # nothing to package → unassessed when no body/surface
    empty = types.SimpleNamespace(components=[])
    assert TT.cg_packaging(empty, out)["status"] == "unassessed"
