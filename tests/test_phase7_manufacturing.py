import math

import pytest

from acdt.core import materials as LIB
from acdt.domains.aircraft.manufacturing import Part, accem_layup_hours, evaluate, fopv_minutes, plan
from acdt.domains.aircraft.manufacturing import refdata as R
from acdt.domains.aircraft.manufacturing.selection import compare, mass_ratio

PROV = {"source_url": "https://example.org/test-price", "retrieved": "2026-10-01", "source_type": "other"}


def _mat(key, price):
    m = LIB.get(key).to_dict()
    m["key"] = key
    m["price"] = {"usd_per_kg": price, "year": 2025, "provenance": PROV}
    return m


def test_fopv_published_point():
    # Bao (2002) / Bao & Samareh (2000): Al spar, 100 in^2 -> 1732 min
    V0, tau = R.FOPV[("metal", "spar")]
    assert fopv_minutes(100, V0, tau) == pytest.approx(1732, abs=1)
    # relative composite / Al parameters (Table 1): composite skin V0 0.871 x spar
    assert R.FOPV[("composite", "skin")][0] / V0 == pytest.approx(0.871, abs=2e-3)


def test_accem_layup():
    assert accem_layup_hours(1000 * 0.0254**2, 2) == pytest.approx(2 * 0.000851 * 1000**0.6295)


def test_feasibility_rules():
    al, cf = _mat("al2024_t3", 10), _mat("cfrp_qi", 40)
    skin = Part("skin", "skin", 2.0, 1.0, perimeter_m=4.0, max_dim_m=2.0, thickness_m=1.0e-3)
    assert not evaluate(skin, "sheet_metal_riveted", {**cf, "usd_per_kg": 40})["feasible"]   # no bucked rivets in CFRP
    assert not evaluate(skin, "filament_winding", {**cf, "usd_per_kg": 40})["feasible"]      # not axisymmetric
    assert not evaluate(skin, "prepreg_autoclave", {**cf, "usd_per_kg": 40}, {"envelope_m": 1.5})["feasible"]
    thin = Part("skin", "skin", 0.5, 1.0, thickness_m=0.2e-3)
    assert not evaluate(thin, "sheet_metal_riveted", {**al, "usd_per_kg": 10})["feasible"]   # below t_min
    ev = evaluate(skin, "sheet_metal_riveted", {**al, "usd_per_kg": 10}, {"rivet_D_m": 3.2e-3, "rivet_pitch_D": 5})
    assert ev["fasteners"] == math.ceil(4.0 / (5 * 3.2e-3))
    assert not evaluate(skin, "sheet_metal_riveted", {**al, "usd_per_kg": 10}, {"rivet_D_m": 3.2e-3,
                                                                               "rivet_pitch_D": 2.5})["feasible"]


def test_quantity_drives_process_choice():
    """Tool-less AM wins at low N, a tooled moulding wins at high N (tooling amortisation)."""
    poly = {"kind": "polymer", "rho": 1000.0, "price": {"usd_per_kg": 100, "year": 2025, "provenance": PROV}}
    cf = _mat("cfrp_qi", 40)
    part = Part("fairing", "fairing", 0.3, 0.2, max_dim_m=0.4, thickness_m=2e-3, material="cfrp_qi")
    pin = {"fdm": {"build_cm3_h": 20, "machine_rate_usd_h": 10, "b2f": 1.1},
           "wet_layup": {"tooling_cost": 20000, "labour_rate_usd_h": 50, "V0": 10.0, "tau": 60.0}}
    ch = {"*": {"materials": ["poly", "cfrp_qi"], "processes": ["fdm", "wet_layup"]}}
    lo = plan([part], {"poly": poly, "cfrp_qi": cf}, 2, choices=ch, process_inputs=pin, scaling=None)
    hi = plan([part], {"poly": poly, "cfrp_qi": cf}, 100000, choices=ch, process_inputs=pin, scaling=None)
    assert lo["selection"]["fairing"][0] == "fdm"
    assert hi["selection"]["fairing"][0] == "wet_layup"


def test_ashby_scaling():
    al, cf = _mat("al2024_t3", 10), _mat("cfrp_qi", 40)
    r = mass_ratio(al, cf, "panel_stiffness")
    assert r == pytest.approx(cf["rho"] / al["rho"] * (al["E"] / cf["E"]) ** (1 / 3))
    c = compare({"al": {**al, "usd_per_kg": 10}, "cf": {**cf, "usd_per_kg": 40}}, "panel_stiffness", "al")
    assert c["ranking"][0]["material"] == "cf"


def test_learning_in_plan():
    al = _mat("al2024_t3", 10)
    p = Part("rib", "rib", 0.5, 0.2, thickness_m=1.5e-3, material="al2024_t3")
    a = plan([p], {"al2024_t3": al}, 1, process_inputs={"*": {"tooling_cost": 0}})
    b = plan([p], {"al2024_t3": al}, 8, process_inputs={"*": {"tooling_cost": 0}})
    assert b["learning_factor"] == pytest.approx((1 + 0.85 + 0.85**math.log2(3) + 0.85**2 + 0.85**math.log2(5)
                                                 + 0.85**math.log2(6) + 0.85**math.log2(7) + 0.85**3) / 8)
    assert b["totals"]["labour_cost"] < a["totals"]["labour_cost"]


def test_compare_normalised_cost():
    al, cf = _mat("al2024_t3", 10), _mat("cfrp_qi", 40)
    c = compare({"al": {**al, "usd_per_kg": 10}, "cf": {**cf, "usd_per_kg": 40}}, "panel_stiffness", "al")
    row = {r["material"]: r for r in c["ranking"]}
    assert row["al"]["relative_material_cost"] == 1.0
    assert row["cf"]["relative_material_cost"] == pytest.approx(row["cf"]["relative_mass"] * 4.0)
