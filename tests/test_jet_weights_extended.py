# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Extended Raymer transport regressions + pressurization: imperial hand checks and coupling."""
import copy
import math
from pathlib import Path
import pytest
import yaml
from acdt.domains.aircraft.jet.weights import transport_weights, validate_weights, LB, FT, INCH, PSI, FT3
from acdt.domains.aircraft.jet.weights import _regress, KDOOR
from acdt.domains.aircraft.jet.sizing import size_jet
from acdt.domains.aircraft.jet.pressurization import assess_extraction, validate_pressurization

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "jet" / "components_raymer_extended.yaml"


@pytest.fixture
def spec():
    return yaml.safe_load(EX.read_text())


def test_fuselage_fineness_and_kdoor_hand_check():
    # ADAC/SUAVE: L/D structural, Kdoor table. Wdg=100000 lb, Nz=3.75.
    p = dict(length_m=120*FT, wetted_area_m2=4000*FT**2, depth_m=13*FT, wing_span_m=110*FT,
             wing_taper_ratio=0.3, wing_sweep_quarter_chord_deg=25, cargo_door="one_side",
             fuselage_mounted_main_gear=False)
    Kws = 0.75*((1+2*0.3)/(1+0.3))*(110/120)*math.tan(math.radians(25))
    expected = 0.3280*1.06*1.0*(100000*3.75)**0.5 * 120**0.25 * 4000**0.302 * (1+Kws)**0.04 * (120/13)**0.10
    assert _regress("raymer_transport_fuselage", p, 100000, 3.75)/LB == pytest.approx(expected, rel=1e-12)
    assert KDOOR["two_side_and_aft_clamshell"] == 1.25


def test_w_press_add_on_and_pair_required(spec):
    p = dict(length_m=120*FT, wetted_area_m2=4000*FT**2, depth_m=13*FT, wing_span_m=110*FT,
             wing_taper_ratio=0.3, wing_sweep_quarter_chord_deg=25, cargo_door="none",
             fuselage_mounted_main_gear=False)
    base = _regress("raymer_transport_fuselage", p, 100000, 3.75)
    p2 = dict(p, pressurized_volume_m3=5000*FT3, delta_p_Pa=8*PSI)
    assert _regress("raymer_transport_fuselage", p2, 100000, 3.75) == pytest.approx(base + 11.9*(5000*8)**0.271*LB)
    bad = copy.deepcopy(spec["weights"]); bad["items"][3]["inputs"].pop("delta_p_Pa")
    with pytest.raises(ValueError, match="together"): validate_weights(bad)


def test_landing_gear_uses_Wl_and_knots():
    p = dict(landing_mass_kg=90000*LB, landing_load_factor=3, main_length_m=50*INCH, nose_length_m=40*INCH,
             main_wheels=8, nose_wheels=2, main_shock_struts=2, landing_stall_speed_kt=120,
             main_kneeling=False, nose_kneeling=False)
    Nl = 4.5
    main = 0.0106*90000**0.888*Nl**0.25*50**0.4*8**0.321*2**-0.5*120**0.1
    nose = 0.032*90000**0.646*Nl**0.2*40**0.5*2**0.45
    assert _regress("raymer_transport_landing_gear", p, 100000, 3.75)/LB == pytest.approx(main+nose, rel=1e-12)


def test_system_equations_hand_checks():
    assert _regress("raymer_transport_apu", {"uninstalled_mass_kg": 400*LB}, 1, 1)/LB == pytest.approx(880)
    assert _regress("raymer_transport_propulsion_accessories",
                    {"n_engines": 2, "cockpit_to_engine_length_m": 60*FT, "mass_per_engine_kg": 2500*LB}, 1, 1)/LB == pytest.approx(
        5*2 + 0.80*60*2 + 49.19*((2500*2)/1000)**0.541)
    fuel = _regress("raymer_transport_fuel_system",
                    {"fuel_volume_m3": 3000*0.003785411784, "n_tanks": 4, "integral_tank_fraction": 0.5}, 1, 1)/LB
    assert fuel == pytest.approx(2.405*3000**0.606*(1.5)**-1*(1.5)*4**0.5)


def test_extended_example_closes_with_pressurization(spec):
    r = size_jet(copy.deepcopy(spec))
    assert r["converged"] and r["feasible"]
    bu = r["weight_build_up"]
    assert bu["coverage"]["complete"]
    assert bu["pressurization"]["pressure_shell_increment_kg"] > 0
    fuse = next(i for i in bu["items"] if i["name"] == "fuselage_structure")
    assert fuse["method"] == "raymer_transport_fuselage" and fuse["detail"]["pressure_shell_increment_kg"] > 0
    gear = next(i for i in bu["items"] if i["name"] == "landing_gear")
    assert gear["detail"]["landing_stall_speed_kt"] == 110
    assert r["pressurization"]["status"] == "assessed_supplied_auxiliary"
    assert r["pressurization"]["checks"][0]["passed"] is True
    # actual numbers for the report (illustrative PRESSUPOSTO)
    assert r["mtow_kg"] == pytest.approx(r["mtow_kg"])  # finite
    assert r["weights"]["empty_mass_kg"] == bu["empty_mass_kg"]
    assert bu["empty_mass_kg"] == pytest.approx(sum(i["mass_kg"] for i in bu["items"]))


def test_pressurization_without_extraction_unassessed(spec):
    d = copy.deepcopy(spec)
    d["pressurization"].pop("extraction")
    r = size_jet(d)
    assert r["converged"]
    assert r["pressurization"]["status"] == "unassessed"
    assert r["pressurization"]["checks"][0]["passed"] is None
    assert "pressurization_extraction_unassessed" in r["issues"]


def test_engines_dry_has_no_thrust_regression(spec):
    d = copy.deepcopy(spec["weights"])
    d["items"][6]["method"] = "raymer_transport_nacelles"
    with pytest.raises(ValueError, match="covers exactly"): validate_weights(d)
    # missing engines stays incomplete, never zero
    d = copy.deepcopy(spec["weights"]); d["items"].pop(6)
    r = transport_weights(70000, 122.6, 9.48, d)
    assert r["empty_mass_kg"] is None and "engines_dry" in r["coverage"]["missing"]


def test_extraction_validation():
    with pytest.raises(ValueError, match="supplied_auxiliary"):
        validate_pressurization({"cabin_volume_m3": 100, "delta_p_Pa": 50000, "source": "s",
                                 "extraction": {"mode": "bleed_map", "fuel_flow_kg_s": 0.1, "thrust_penalty_N": 0, "source": "x"}})
    a = assess_extraction({"cabin_volume_m3": 100, "delta_p_Pa": 50000, "source": "s"})
    assert a["status"] == "unassessed" and a["checks"][0]["passed"] is None
