# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Asa sem deriva, itens em aberto (ronda 2, 18 nov 2026): C_m0 dos corpos de Multhopp e veredicto estrito da
rajada lateral no 6-DOF."""
import math

import pytest

from acdt.domains.aircraft.assembly.body_moment import (body_cm0, lame_area, multhopp_cm0_sum, munk_k1_k2)


@pytest.mark.parametrize("f,k1,k2", [(2.0, 0.209, 0.702), (4.0, 0.082, 0.860), (6.0, 0.045, 0.918),
                                      (10.0, 0.021, 0.960)])
def test_munk_apparent_mass_table(f, k1, k2):
    """Lamb §373 prolate spheroid reproduces Munk's (NACA TR-184) tabulated k1, k2."""
    a, b = munk_k1_k2(f)
    assert a == pytest.approx(k1, abs=0.002) and b == pytest.approx(k2, abs=0.003)


def test_multhopp_tulapurkara_example_2_4():
    """Tulapurkara NPTEL Cap. 2 Exemplo 2.4: Σ w_f²(α0L,f + i_f)Δx = −47,155, (k2−k1) 0,82, S 17,07, c̄ 1,737 →
    C_m0,f = −0,0357. k2−k1 analítico à finura 4,87 = 0,83 (lido na figura: 0,82)."""
    w = [1.097561, 1.402439, 1.402439, 1.402439, 1.25, 0.945122, 0.70122, 0.457317, 0.243902]
    s = sum(x * x * -5 * 0.914634 for x in w)
    assert s == pytest.approx(-47.155, rel=2e-3)        # the published rows are rounded (row 1: −5,4977)
    rows = [-5.497689383, -8.983337807, -8.983337807, -8.983337807, -7.141328478, -4.08075913, -2.2387498,
            -0.963512572, -0.283386051]                  # Table E 2.4.1, last column
    assert multhopp_cm0_sum([1.0] * 9, [1.0] * 9, rows, 0.82, 17.07, 1.737) == pytest.approx(-0.0357, abs=1e-4)
    assert multhopp_cm0_sum(w, [0.914634] * 9, [-5] * 9, 0.82, 17.07, 1.737) == pytest.approx(-0.0357, abs=2e-4)
    k1, k2 = munk_k1_k2(4.87)
    assert k2 - k1 == pytest.approx(0.82, abs=0.015)


def test_body_cm0_signs_and_area():
    from acdt.domains.aircraft.assembly.components import Body
    assert lame_area(2.0, 1.0, 2.0) == pytest.approx(math.pi * 0.5)
    b = Body.pod("pod", 3.0, 0.4)
    up = body_cm0(b, 2.0, 3.0, 0.8)
    assert up["status"] == "assessed" and up["Cm0"] > 0        # nose-up local flow → nose-up (destabilising) Munk moment
    assert body_cm0(b, 0.0, 3.0, 0.8)["Cm0"] == pytest.approx(0.0)
    b2 = Body.pod("pod", 3.0, 0.4, upsweep_deg=10.0)
    r2 = body_cm0(b2, 0.0, 3.0, 0.8)
    assert r2["stations"][-1]["i_f_deg"] == pytest.approx(-10.0) and r2["Cm0"] < 0   # aft upsweep: i_f < 0
    bm = Body.pod("pod", 3.0, 0.4, mirror=True) if "mirror" in Body.__dataclass_fields__ else None
    if bm is not None:
        assert body_cm0(bm, 2.0, 3.0, 0.8)["Cm0"] == pytest.approx(2 * up["Cm0"])


def test_gust_verdict_6dof_strict():
    from acdt.domains.aircraft.flightsim.tailless_sim import gust_verdict_6dof
    ok = {"peak": {"beta_deg": 10.0}, "final_beta_amp_deg": 0.5,
          "actuator": {"saturated": False, "rate_limited": False, "rate_limited_fraction": 0.0, "peak_rate_deg_s": 40.0}}
    v = gust_verdict_6dof(ok, 84.0, lambda: pytest.fail("no re-run without rate limit"))
    assert v["ok"] is True and "rate_required_deg_s" not in v
    lim = {**ok, "actuator": {**ok["actuator"], "rate_limited": True, "rate_limited_fraction": 0.0004,
                              "peak_rate_deg_s": 84.0}}
    v = gust_verdict_6dof(lim, 84.0, lambda: {"actuator": {"peak_rate_deg_s": 120.0, "saturated": False}})
    assert v["ok"] is False and v["rate_required_deg_s"] == 120.0
    assert v["rate_factor_required"] == pytest.approx(120 / 84)
    unsettled = {**ok, "final_beta_amp_deg": 2.0}
    assert gust_verdict_6dof(unsettled, 84.0, lambda: None)["ok"] is False
    assert gust_verdict_6dof({"peak": {}}, 84.0, lambda: None)["ok"] is None   # no actuator → unassessed
