# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in camber-flap trim drag and gap drag (unassessed ≠ zero)."""
from types import SimpleNamespace

import numpy as np
import pytest

from acdt.domains.aircraft.aero.airfoil import AirfoilPolar
from acdt.domains.aircraft.aero.camber_flap import (
    CamberSchedule, SectionEnvelope, apply_trim_and_gap, ht_trim_induced_cd,
    resolve_gap, section_cm0_at, wing_delta_Cm,
)


def _polar(cm0, clmax=1.5):
    alpha = np.linspace(-4.0, 12.0, 21)
    cl = 0.1 + 0.1 * alpha
    cl = np.clip(cl, -0.5, clmax)
    cd = 0.01 + 0.04 * (cl - 0.2) ** 2
    cm = np.full_like(cl, cm0)
    return AirfoilPolar("SYN", 1e6, 0.0, alpha, cl, cd, cm, source="synthetic")


def _section():
    # cm0 becomes more nose-down as δ increases (typical flap)
    deltas = [-5.0, 0.0, 5.0, 10.0]
    pols = [_polar(-0.05 - 0.05 * (d / 5.0)) for d in deltas]
    return SectionEnvelope("SYN", 1e6, 0.8, deltas, pols, 0.15, "synthetic")


def _sched(sec=None):
    sec = sec or _section()
    CL = np.linspace(0.2, 1.0, 9)
    # toy envelope: negative profile ΔCD, δ rises with CL
    dCD = -0.002 * np.ones_like(CL)
    delta = np.linspace(-2.0, 8.0, CL.size)
    return CamberSchedule("camber", CL, dCD, delta, 0.5, 0.2, 0.15, 10.0, 0.01,
                          section=sec, opts={})


def _config():
    wing = SimpleNamespace(S=10.0, mac=1.0, span=10.0)
    htail = SimpleNamespace(S=2.0, arm=5.0, AR=4.0)
    return SimpleNamespace(wing=wing, htail=htail)


def test_gap_omitted_by_default():
    g = resolve_gap(None)
    assert g["status"] == "omitted" and g["dCD"] is None


def test_gap_sealed_assessed_zero_with_source():
    g = resolve_gap({"sealed": True, "source": "XFOIL GDES/FLAP sealed-gap assumption"})
    assert g["status"] == "assessed" and g["dCD"] == 0.0


def test_gap_sealed_requires_source():
    with pytest.raises(ValueError, match="source"):
        resolve_gap({"sealed": True})


def test_gap_supplied_dCD_with_source():
    g = resolve_gap({"dCD": 0.0015, "source": "PRESSUPOSTO demo increment"})
    assert g["status"] == "assessed" and g["dCD"] == pytest.approx(0.0015)


def test_gap_chord_without_dCD_is_unassessed_not_zero():
    g = resolve_gap({"chord_ratio": 0.005, "source": "measured gap"})
    assert g["status"] == "unassessed" and g["dCD"] is None


def test_ht_trim_induced_cd_classical():
    cfg = _config()
    # V_H = 2*5/(10*1) = 1.0; CL_h = -0.02/(0.9*1)= -0.02222
    # CD = (0.02222)^2 / (pi*0.8*4) * 0.2
    r = ht_trim_induced_cd(cfg, 0.02, e_ht=0.8, eta_h=0.9)
    assert r["status"] == "assessed"
    CL_h = -0.02 / (0.9 * 1.0)
    expect = (CL_h ** 2) / (np.pi * 0.8 * 4.0) * (2.0 / 10.0)
    assert r["dCD"] == pytest.approx(expect)
    assert r["V_H"] == pytest.approx(1.0)


def test_ht_trim_unassessed_without_ht():
    cfg = SimpleNamespace(wing=SimpleNamespace(S=10.0, mac=1.0), htail=None)
    r = ht_trim_induced_cd(cfg, 0.02)
    assert r["status"] == "unassessed" and r["dCD"] is None


def test_apply_trim_omitted_leaves_profile_only():
    sch = _sched()
    apply_trim_and_gap(sch, _config(), {"trim_drag": False, "gap": None, "kind": "camber",
                                        "chord_ratio": 0.2, "eta_in": 0.0, "eta_out": 0.65,
                                        "deltas_deg": [-5, 0, 5, 10], "cl_margin": 0.15,
                                        "actuators": 2, "landing_deflection": True,
                                        "trim_e_ht": 0.8, "trim_SM": 0.1})
    assert sch.trim_drag_status == "omitted" and sch.gap_drag_status == "omitted"
    assert sch.dcd(0.6) == pytest.approx(-0.002)


def test_apply_trim_and_gap_assessed_increases_cd_vs_profile():
    sch = _sched()
    o = {"trim_drag": True, "gap": {"dCD": 0.001, "source": "PRESSUPOSTO demo"},
         "kind": "camber", "chord_ratio": 0.2, "eta_in": 0.0, "eta_out": 0.65,
         "deltas_deg": [-5, 0, 5, 10], "cl_margin": 0.15, "actuators": 2,
         "landing_deflection": True, "trim_e_ht": 0.8, "trim_SM": 0.1,
         "actuator_mass_kg": None, "surface_mass_kg_m2": None, "actuator_cost_usd": 0.0}
    apply_trim_and_gap(sch, _config(), o)
    assert sch.trim_drag_status == "assessed" and sch.gap_drag_status == "assessed"
    profile = float(np.interp(0.6, sch.CL, sch.dCD))
    total = float(sch.dcd(0.6))
    assert total > profile  # trim (≥0) + gap (0.001)
    assert total - profile == pytest.approx(float(np.interp(0.6, sch.CL, sch.dCD_trim)) + 0.001)
    # two-point envelope still present
    assert sch.delta_at(0.3) < sch.delta_at(0.9)


def test_trim_unassessed_not_added_as_zero():
    sch = _sched()
    o = {"trim_drag": True, "gap": None, "kind": "camber", "chord_ratio": 0.2,
         "eta_in": 0.0, "eta_out": 0.65, "deltas_deg": [-5, 0, 5, 10], "cl_margin": 0.15,
         "actuators": 2, "landing_deflection": True, "trim_e_ht": 0.8, "trim_SM": 0.1,
         "actuator_mass_kg": None, "surface_mass_kg_m2": None, "actuator_cost_usd": 0.0}
    cfg = SimpleNamespace(wing=SimpleNamespace(S=10.0, mac=1.0), htail=None)
    apply_trim_and_gap(sch, cfg, o)
    assert sch.trim_drag_status == "unassessed"
    assert sch.dCD_trim is None
    # dcd remains profile only — but status flags that trim was NOT assessed as zero
    assert sch.dcd(0.6) == pytest.approx(-0.002)
    assert "UNASSESSED" in " ".join(sch.notes)


def test_wing_delta_Cm_scales_with_flapped_area():
    sec = _section()
    dcm_full = wing_delta_Cm(sec, 10.0, 1.0)
    dcm_half = wing_delta_Cm(sec, 10.0, 0.5)
    assert dcm_half == pytest.approx(0.5 * dcm_full)
    assert section_cm0_at(sec, 10.0) != section_cm0_at(sec, 0.0)
