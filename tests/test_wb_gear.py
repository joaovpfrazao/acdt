"""Operational weight and balance (Raymer 2018 Sec. 15.1, Roskam Part II 1985 Ch. 10) and landing-gear
layout / limit landing load (Raymer Ch. 11, Currey 1988, 14 CFR 23.473 as of 25 July 2017)."""
import math

import pytest

from acdt import G0
from acdt.core.systems.mass import (LoadItem, cg_limit_at, operational_loadings, outside_limits)
from acdt.domains.aircraft.landing_gear import (ABSORBER_ETA, adopted_factors, angle_from_vertical_deg,
                                                gear_load_factor, limit_descent_speed_ft_s, min_half_track,
                                                overturn_angle_deg, place_tricycle, static_fraction_front,
                                                stroke_for_load_factor, target_gear_factor)


def _box():
    # Empty 1000 kg at 2.0 m, fuel 0–200 kg at 2.5 m, payload 0–150 kg at 1.5 m.
    return [
        LoadItem("vazio", 2.0, 1000, 1000, "fixed"),
        LoadItem("combustível", 2.5, 0, 200, "fuel"),
        LoadItem("payload", 1.5, 0, 150, "variable"),
    ]


def test_loading_vertices_match_hand_moments():
    env = operational_loadings(_box(), m_max=1350)
    # payload only: (1000*2 + 150*1.5) / 1150
    assert env.most_forward.x == pytest.approx(2225 / 1150)
    assert env.most_forward.mass == pytest.approx(1150)
    assert "payload" in env.most_forward.name and "combustível" not in env.most_forward.name
    # fuel only: (1000*2 + 200*2.5) / 1200
    assert env.most_aft.x == pytest.approx(2500 / 1200)
    assert env.most_aft.mass == pytest.approx(1200)
    full = next(p for p in env.points if p.mass == pytest.approx(1350))
    assert full.x == pytest.approx((2000 + 500 + 225) / 1350)
    assert env.paths  # fuel burn from the feasible full-fuel corners


def test_mtow_cap_drops_the_heavy_corner_and_adds_the_face():
    env = operational_loadings(_box(), m_max=1200)
    assert all(p.mass <= 1200 + 1e-6 for p in env.points)
    assert any(p.mass == pytest.approx(1200) for p in env.points)
    assert not any(p.mass == pytest.approx(1350) for p in env.points)


def test_cg_limit_is_piecewise_and_catches_the_forward_point():
    assert cg_limit_at([(1000, 1.8), (1200, 2.0)], 1100) == pytest.approx(1.9)
    assert cg_limit_at([(0.0, 1.5)], 999) == pytest.approx(1.5)
    env = operational_loadings(_box(), 1350)
    assert outside_limits(env.points, [(0.0, 1.90)], [(0.0, 2.10)]) == []
    bad = outside_limits(env.points, [(0.0, 1.95)], [(0.0, 2.10)])
    assert bad and min(p.x for p in bad) == pytest.approx(2225 / 1150)


def test_descent_speed_is_the_far_formula_with_the_published_caps():
    # 4.4 * 16^(1/4) = 4.4 * 2 = 8.8 ft/s. Below 7 and above 10 the clause clamps.
    assert limit_descent_speed_ft_s(16) == pytest.approx(8.8)
    assert limit_descent_speed_ft_s(1) == 7
    assert limit_descent_speed_ft_s(100) == 10


def test_energy_stroke_round_trips_and_floors_match_23473g():
    v = 10 * 0.3048  # the 10 ft/s cap, in m/s
    # Currey 1988 §5.3. With no tyre stroke, N = V²/(2 g η S) + (1−κ)/η.
    stroke = stroke_for_load_factor(v, 3.0, 0.80, 0.0)
    assert gear_load_factor(v, stroke, 0.80, 0.0) == pytest.approx(3.0)
    # the same stroke with the permitted wing lift: the second term is (1−κ)/η, not (1−κ)
    assert gear_load_factor(v, stroke, 0.80, 2.0 / 3.0) == pytest.approx(3.0 - (2.0 / 3.0) / 0.80)
    # κ = 1 cancels the aircraft weight, so N = V²/(2 g η S)
    assert stroke_for_load_factor(v, 3.0, 0.80, 1.0) == pytest.approx(v ** 2 / (2 * G0 * 3.0 * 0.80))
    both = stroke_for_load_factor(v, 3.0, 0.80, 2.0 / 3.0, 0.05, 0.47)
    assert both > 0
    assert gear_load_factor(v, both, 0.80, 2.0 / 3.0, 0.05, 0.47) == pytest.approx(3.0)
    n_i, n_g = adopted_factors(1.5, 2.0 / 3.0)
    assert n_i == pytest.approx(2.67) and n_g == pytest.approx(2.0)
    assert target_gear_factor(3.0, 2.0 / 3.0) == pytest.approx(3.0)
    assert target_gear_factor(1.5, 0.0) == pytest.approx(2.67)
    assert ABSORBER_ETA["oleo"] == 0.80 and ABSORBER_ETA["tire"] == 0.47


def test_tipback_nose_fraction_and_overturn_geometry():
    x_nose, x_main = place_tricycle(4.9, 5.0, 1.0, 15.0, 0.08)
    dx = math.tan(math.radians(15))
    assert x_main == pytest.approx(5.0 + dx)
    # longest wheelbase in the 8–15 % band: 8 % at the aft CG, and the nose is still aft of the datum
    assert x_nose == pytest.approx(x_main - dx / 0.08)
    assert x_nose > 0
    assert static_fraction_front(x_nose, x_main, 5.0) == pytest.approx(0.08)
    # the 8 % wheelbase would put the nose ahead of the datum, and no shorter one stays inside 8–15 %
    assert place_tricycle(1.9, 2.0, 1.0, 15.0, 0.08) is None
    # the longest legal wheelbase sticks out; a shorter one in the same band keeps the nose at x = 0
    shortened = place_tricycle(2.9, 3.0, 1.0, 15.0, 0.08)
    assert shortened is not None and shortened[0] == pytest.approx(0.0, abs=1e-6)
    assert static_fraction_front(shortened[0], shortened[1], 3.0) >= 0.08 - 1e-6
    assert static_fraction_front(shortened[0], shortened[1], 2.9) <= 0.15 + 1e-6
    # CG travel too long for 8–15 % at this height: no wheelbase, rather than a nose ahead of the aeroplane
    assert place_tricycle(2.6, 3.0, 1.0, 15.0, 0.08) is None
    assert angle_from_vertical_deg(x_main - 5.0, 1.0) == pytest.approx(15.0)
    # d = (t/2) * x_cg / hypot(t/2, wheelbase); CG at mid-wheelbase is less critical than a forward CG
    # only when the apex is the nose. Here x=2 is forward of x=3, so the angle is larger.
    assert overturn_angle_deg(0, 4, 1, 2, 1) > overturn_angle_deg(0, 4, 1, 3, 1)
    half = min_half_track(0, 4, 2, 1, 63)
    assert overturn_angle_deg(0, 4, half, 2, 1) == pytest.approx(63.0)
    assert min_half_track(0, 4, 0.2, 1, 63) == math.inf
    assert static_fraction_front(1.0, 4.0, 2.5) == pytest.approx(0.5)


def _aircraft(limits=None, gear="tricycle"):
    from acdt.domains.aircraft.phase2 import _layout
    from acdt.domains.aircraft.stability import StabilityResult

    class NS:
        def __init__(self, **k):
            self.__dict__.update(k)

    wb = {"crew_optional": False, "extra_items": []}
    if limits:
        wb.update(limits)
    res = NS(
        spec=NS(propulsion_kind="piston_prop", assumptions={
            "stability": {"elevator_max_deg": 25.0, "elevator_cf_c": 0.30},
            "weight_balance": wb,
            "landing_gear": {"h_cg_m": 1.2},
            "weights": {"components": {"landing_gear": gear, "gear_load_factor": 3.0,
                                       "main_gear_length_m": 0.6, "landing_weight_fraction": 0.95}},
        }),
        sizing=NS(W0=330.0),
        S=16.0,
        checks=[],
        lowfi=None,
        highlift=NS(CLmax_clean=1.6),
        config=NS(wing=NS(AR=7.0, sweep_c4=0.0), fuselage=NS(length=8.0, max_diameter=1.2)),
        stability=StabilityResult(
            2.0, 2.0, 1.5, 0.40, 0.35, None, -0.02, 0.4, 4.5, 4.0, 0.7, 0.04, 0.7, 0.04,
            [], {}, {}, 0.10, "test",
            stations=[
                {"item": "wing", "mass_kg": 100, "x_m": 2.4},
                {"item": "fuselage", "mass_kg": 80, "x_m": 2.0},
                {"item": "fuel", "mass_kg": 40, "x_m": 2.5},
                {"item": "payload", "mass_kg": 30, "x_m": 1.6},
                {"item": "crew", "mass_kg": 80, "x_m": 1.5},
            ]),
    )
    _layout(res)
    return res


def test_main_station_alone_is_kept_and_a_miss_is_a_failed_check():
    from acdt.domains.aircraft.landing_gear import analyse_landing_gear

    class Ends:
        def __init__(self, fwd, aft):
            self.x_min_m, self.x_max_m = fwd, aft

    res = _aircraft()
    res.weight_balance = Ends(4.9, 5.0)
    res.spec.assumptions["landing_gear"]["x_main_m"] = 5.30
    gear = analyse_landing_gear(res)
    assert gear.x_main_m == pytest.approx(5.30)
    assert gear.x_nose_m is not None and gear.x_nose_m >= -1e-6
    assert any("x_main_m dado sem x_nose_m" in n for n in gear.notes)
    # CG near the nose: the 8–15 % band does not fit inside the fuselage
    res.weight_balance = Ends(1.9, 2.0)
    del res.spec.assumptions["landing_gear"]["x_main_m"]
    bad = analyse_landing_gear(res)
    assert bad.x_nose_m is None and bad.x_main_m is None and bad.geometry_ok is False
    assert any(key == "gear:position" and ok is False for key, ok, _ in bad.checks)
    assert any(key == "gear:stroke" for key, _, _ in bad.checks)


def test_layout_on_a_sized_aircraft_reports_checks_without_sizing_failure():
    res = _aircraft({"x_forward_m": 0.0, "x_aft_m": 10.0})
    assert res.weight_balance.within_limits is True
    assert res.landing_gear.kind == "tricycle"
    assert 7 <= res.landing_gear.descent_ft_s <= 10
    assert res.landing_gear.stroke_m > 0
    assert res.landing_gear.n_gear >= 2.0
    keys = {c.key for c in res.checks}
    assert "wb:envelope" in keys and "gear:stroke" in keys and "gear:tipback" in keys
    tight = _aircraft({"x_forward_m": 2.0, "x_aft_m": 2.04})
    assert tight.weight_balance.within_limits is False
    from acdt.domains.aircraft.sizing import LAYOUT_PREFIXES
    assert all(c.key.startswith(LAYOUT_PREFIXES) or c.ok is not False for c in tight.checks)
    failed_sizing = [c for c in tight.checks if c.ok is False and not c.key.startswith(LAYOUT_PREFIXES)]
    assert failed_sizing == []


def test_no_gear_is_recorded_and_leaves_the_regulation_open(tmp_path):
    res = _aircraft(gear="none")
    assert res.landing_gear.kind == "none" and res.landing_gear.checks == []
    from acdt.domains.aircraft.weight_balance import plot_loading_diagram
    assert plot_loading_diagram(res.weight_balance, tmp_path / "wb.png")
    from acdt.core.certification import build_matrix
    r = {"weights": {"W0_kg": 330, "We_kg": 200, "crew_kg": 80},
         "requirements": [{"key": "regulatory_category", "value_si": "cs_23"},
                          {"key": "propulsion_type", "value_si": "piston_prop"}],
         "checks": [{"key": "static_margin", "ok": True, "message": "SM 10 %"}],
         "weight_balance": res.weight_balance.summary(),
         "landing_gear": res.landing_gear.summary()}
    # no gear → ground-load paragraphs stay open
    m = build_matrix(r, {"max_passenger_seats": 3})
    st = {row["parágrafo"]: row["estado"] for row in m["rows"]}
    assert st["23.2220"] == "open" and st["23.2305"] == "open"
    r["landing_gear"] = {"kind": "tricycle", "geometry_ok": False, "geometry_summary": "tombo curto",
                         "load_factor_ok": None, "load_summary": "V = 8.8 ft/s; curso 0.20 m"}
    r["weight_balance"] = {"evaluated": True, "within_limits": False, "summary": "CG fora do limite dianteiro"}
    m = build_matrix(r, {"max_passenger_seats": 3})
    st = {row["parágrafo"]: row["estado"] for row in m["rows"]}
    assert st["23.2305"] == "non-compliant"
    assert st["23.2220"] == "needs-test"   # value determined; the means of compliance still include a test
    assert st["23.2100"] == "non-compliant"


def test_cli_gear_summary_names_geometry_and_failed_checks(capsys):
    from acdt.cli import _phase2_summary
    from acdt.domains.aircraft.landing_gear import LandingGearResult

    class R:
        lowfi = structures = stability = dynamics = aeroelastic = weight_balance = performance = None

    R.landing_gear = LandingGearResult(
        kind="tricycle", geometry_ok=False, tipback_deg=None, overturn_deg=None,
        descent_ft_s=8.8, stroke_m=0.20, n_gear=2.67,
        checks=[("gear:position", False, "fora"), ("gear:rotation", False, "curto"),
                ("gear:stroke", True, "ok")])
    _phase2_summary(R())
    failed = capsys.readouterr().out
    assert "geometria falha" in failed
    assert "gear:position" in failed and "gear:rotation" in failed
    assert "gear:stroke" not in failed
    R.landing_gear = LandingGearResult(
        kind="tricycle", geometry_ok=True, tipback_deg=15.2, overturn_deg=50.0,
        descent_ft_s=8.0, stroke_m=0.15, n_gear=3.0,
        checks=[("gear:position", True, "ok"), ("gear:stroke", True, "ok")])
    _phase2_summary(R())
    ok = capsys.readouterr().out
    assert "geometria ok" in ok and "tombo 15.2°" in ok and "falhas:" not in ok


def test_firewall_arm_and_loading_replace_the_lumped_useful_load():
    from acdt.domains.aircraft.stability import _firewall_x, _station_x
    from acdt.domains.aircraft.weight_balance import _items_from_stations

    x = _station_x("fuel", {"fuel": ("firewall", 48.0), "user_items": ("L", 0.4)},
                   8.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 1.0)
    assert x == pytest.approx(1.0 + 48.0 * 0.0254)
    with pytest.raises(ValueError, match="firewall"):
        _station_x("crew", {"crew": ("firewall", 37), "user_items": ("L", 0.4)},
                   8.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, None)

    class NS:
        def __init__(self, **k):
            self.__dict__.update(k)

    length = 0.757174
    res = NS(
        spec=NS(propulsion_kind="piston_prop", assumptions={
            "stability": {"firewall_from_engine": True, "engine_length_m": length, "stations": {}},
            "weight_balance": {"loading": [
                {"name": "bancos dianteiros", "arm_in": 37, "mass_min_kg": 77, "mass_max_kg": 77, "kind": "fixed"},
                {"name": "combustível", "arm_in": 48, "kind": "fuel"},
            ], "extra_items": []},
        }),
        config=NS(fuselage=NS(length=8.0)),
        stability=NS(stations=[
            {"item": "wing", "mass_kg": 100, "x_m": 2.0},
            {"item": "crew", "mass_kg": 77, "x_m": 1.5},
            {"item": "payload", "mass_kg": 30, "x_m": 1.6},
            {"item": "fuel", "mass_kg": 40, "x_m": 2.5},
        ]),
    )
    items = _items_from_stations(res, res.spec.assumptions["weight_balance"])
    names = [i.name for i in items]
    assert names.count("combustível") == 1
    assert "tripulação" not in names and "payload" not in names and "wing" in names
    fw = _firewall_x(res, 8.0)
    assert fw == pytest.approx(0.08 * 8.0 + 0.5 * length)
    fuel = next(i for i in items if i.kind == "fuel")
    assert fuel.mass_min == 0 and fuel.mass_max == pytest.approx(40)
    assert fuel.x == pytest.approx(fw + 48 * 0.0254)
    pilot = next(i for i in items if i.name == "bancos dianteiros")
    assert pilot.kind == "fixed" and pilot.mass_min == pytest.approx(77)
    assert pilot.x == pytest.approx(fw + 37 * 0.0254)


def test_forward_limit_binds_on_the_more_aft_trim():
    """Nelson Ch. 2 trim, once clean and once in the full-flap flare. The station is the more aft of the two.

    Fuselage Cm0 is Multhopp with Lamb's k2−k1. A plain flap stays on Glauert. A slotted flap uses
    the DATCOM 44 % extended-chord center of pressure on Raymer's ΔCLmax. With no horizontal tail
    the Torenbeek factor is not applied. With a tail, the flare row scales Cmδe and the clean row
    does not.
    """
    from acdt.domains.aircraft.aero.lift import HighLiftDevice, delta_clmax_flap
    from acdt.domains.aircraft.geometry import Configuration, Fuselage, TrapezoidalWing, size_tails
    from acdt.domains.aircraft.stability import (DATCOM_SLOTTED_CP, ETA_H, LoadingCase, StabilityResult,
                                                 binding_forward_station, cla_ground_factor,
                                                 control_forward_xbar, flap_cm_increment, flap_effectiveness,
                                                 flare_tail_cla_scale, forward_cg_terms, fuselage_cm0,
                                                 lamb_k2_minus_k1, neutral_point, slotted_flap_cm,
                                                 tail_sizing_scissor, torenbeek_induced_ratio, wing_cm0)

    assert lamb_k2_minus_k1(1.0) == 0.0
    assert lamb_k2_minus_k1(2.0) == pytest.approx(0.493)
    assert lamb_k2_minus_k1(6.97) == pytest.approx(0.897)
    assert lamb_k2_minus_k1(9.97) == pytest.approx(0.939)
    assert lamb_k2_minus_k1(100.0) == pytest.approx(0.939)  # table ends; the limit 1 is not a published row
    k7 = lamb_k2_minus_k1(7.0)
    assert 0.897 < k7 < 0.916

    class NS:
        def __init__(self, **k):
            self.__dict__.update(k)

    class Polar:
        alpha0_deg = -2.0

    w = TrapezoidalWing(S=16.0, AR=8.0, taper=1.0)
    fus = Fuselage(length=7.0, max_diameter=1.0)
    de, xnp, x_le = 25.0, 0.40, 2.0
    cm_de = -1.5
    cm0_wing = wing_cm0(-0.05, w.AR, 0.0)
    assert cm0_wing == pytest.approx(-0.05 * 8 / 10)
    cm0_f = fuselage_cm0(fus.fineness, fus.length, fus.max_diameter, w.S, w.mac, -2.0, 0.0)
    assert cm0_f == pytest.approx(k7 * 1.0 * 7.0 * -2.0 / (36.5 * 16.0 * w.mac))
    assert cm0_f < 0
    cm0_flap = flap_cm_increment(0.30, 30.0, 0.55)
    assert cm0_flap < 0
    dcl_slot = delta_clmax_flap(HighLiftDevice("slotted", 0.55, 1.0))
    cm0_slot = slotted_flap_cm(dcl_slot, 1.0)
    assert cm0_slot == pytest.approx((0.25 - DATCOM_SLOTTED_CP) * dcl_slot)
    assert torenbeek_induced_ratio(0.0) == 0.0
    assert torenbeek_induced_ratio(1.0e6) == pytest.approx(1.0, abs=1e-9)
    # h/b = 0.5 → 2h/b = 1 → φ = 1 − exp(−2.48)
    assert torenbeek_induced_ratio(0.5) == pytest.approx(1.0 - math.exp(-2.48))
    assert cla_ground_factor(4.0, 1.0e6) == pytest.approx(1.0, abs=1e-6)

    def aircraft(landing, flap):
        assumptions = {"stability": {"elevator_max_deg": de, "elevator_cf_c": 0.30}}
        if flap:
            assumptions["aero"] = {"flap": flap}
        return NS(spec=NS(assumptions=assumptions), config=NS(wing=w, fuselage=fus),
                  lowfi=NS(cm0=-0.05, polar_cruise=Polar()),
                  highlift=NS(CLmax_clean=1.6, **({"CLmax_landing": landing} if landing else {})))

    # no landing CL: the clean station, and the flare is reported as not evaluated
    x_clean_only, note_clean = binding_forward_station(aircraft(None, None), xnp, cm_de, de, x_le, w.mac)
    xbar_clean = control_forward_xbar(xnp, cm0_wing, cm_de, de, 1.6)
    assert x_clean_only == pytest.approx(x_le + xbar_clean * w.mac)
    assert "não traz CLmax de aterragem" in note_clean
    assert "efeito de solo" not in note_clean

    # landing CL below the clean CL, no flap area: the clean trim is the more aft one
    low_cl = aircraft(1.2, {"kind": "plain", "flapped_area_ratio": 0.0, "landing_deg": 30, "cf_c": 0.30})
    # area 0 skips the flap moment; fuselage Cm0 still enters the flare numerator
    x_low, note_low = binding_forward_station(low_cl, xnp, cm_de, de, x_le, w.mac)
    x_flare_low = x_le + control_forward_xbar(xnp, cm0_wing + cm0_f, cm_de, de, 1.2) * w.mac
    assert x_flare_low < x_clean_only
    assert x_low == pytest.approx(x_clean_only)
    assert "dimensiona «limpo»" in note_low
    assert "não aplicado" in note_low and "Hoerner" in note_low

    # slotted flap, no tail yet: DATCOM moment, and the tail factor is not applied
    flared = aircraft(2.2, {"kind": "slotted", "flapped_area_ratio": 0.55, "landing_deg": 30, "cf_c": 0.30})
    x_flare, note_flare = binding_forward_station(flared, xnp, cm_de, de, x_le, w.mac)
    xbar_flare = control_forward_xbar(xnp, cm0_wing + cm0_f + cm0_slot, cm_de, de, 2.2)
    assert x_flare == pytest.approx(x_le + xbar_flare * w.mac)
    assert x_flare > x_clean_only
    assert "dimensiona «flare com flaps»" in note_flare
    assert "DATCOM" in note_flare and "44" in note_flare and "PRESSUPOSTO" in note_flare
    assert "Glauert" not in note_flare and "slotted" in note_flare
    assert "não aplicado" in note_flare and "Hoerner" in note_flare

    # the scissor control line is that same more-aft x̄, not the clean-only line
    ht, vt = size_tails(w, 4.0, 0.70, 0.04)
    cfg = Configuration(w, fus, ht, vt)
    res = flared
    res.config = cfg
    res.CLalpha = 4.5
    mac = w.mac
    st = StabilityResult(
        1.5, x_le, mac, xnp, xnp, None, 0.0, 0.4, 4.5, 4.0, 0.5, 0.04, 0.5, 0.04,
        [LoadingCase("vazio", 800, x_le + 0.15 * mac, 0.15, 0.25),
         LoadingCase("cheio", 1000, x_le + 0.35 * mac, 0.35, 0.05)],
        {}, {}, 0.10, "test")
    sc = tail_sizing_scissor(res, st, {"elevator_max_deg": de, "elevator_cf_c": 0.30}, n=5)
    assert "flare com flaps" in sc["notes"][0] and "NÃO incluídos" not in sc["notes"][0]
    r = float(sc["Sh_S"][2])
    from dataclasses import replace
    c2 = replace(cfg, htail=replace(cfg.htail, S=r * w.S))
    npd = neutral_point(c2, {"CLa_w": 4.5}, st.x_mac_le, st.x_wing_apex)
    vh = r * c2.htail.arm / mac
    cmde = -ETA_H * vh * npd["CLa_h"] * flap_effectiveness(0.30)
    terms = forward_cg_terms(res)
    scale, scale_note = flare_tail_cla_scale(res, c2.htail)
    assert scale > 1.0 and "Torenbeek" in scale_note
    bound = max(control_forward_xbar(npd["xbar_np"], terms["cm0_wing"], cmde, de, terms["cl_clean"]),
                control_forward_xbar(npd["xbar_np"], terms["cm0_flare"], cmde * scale, de, terms["cl_landing"]))
    assert sc["control_line"][2] == pytest.approx(bound)
    clean_only = control_forward_xbar(npd["xbar_np"], terms["cm0_wing"], cmde, de, terms["cl_clean"])
    assert bound > clean_only
    assert "Torenbeek" in sc["notes"][0] and "não aplicado" not in sc["notes"][0]
    assert "flare com flaps" in sc["notes"][0] and "efeito de solo" in sc["notes"][0]


def test_balance_station_keeps_payload_on_the_fixed_mass_cg():
    """Raymer 2018 Sec. 15.1: an item at the fixed-mass CG does not move that CG.

    The old default (payload at 50 % L) widens the same loading. Crew mass 0 adds no crew item.
    """
    from acdt.domains.aircraft.geometry import Configuration, Fuselage, TrapezoidalWing, size_tails
    from acdt.domains.aircraft.stability import DEFAULT_STATIONS, _items_and_cases

    class Item:
        def __init__(self, key, mass):
            self.key, self.group, self.mass = key, "structure", mass

    class Bits:
        def __init__(self, **k):
            self.__dict__.update(k)

    wing = TrapezoidalWing(S=2.0, AR=10.0, taper=0.6)
    fus = Fuselage(3.2, 0.4)
    ht, vt = size_tails(wing, 1.5, 0.5, 0.04)
    res = Bits(config=Configuration(wing, fus, ht, vt),
               sizing=Bits(crew=0.0, payload=30.0, Wf=20.0),
               spec=Bits(propulsion_kind="piston_prop", assumptions={"stability": {}}),
               weights=Bits(items=[Item("fuselage", 10.0), Item("engine_installed", 28.0),
                                   Item("wing", 14.0)]))
    items, cases, _ = _items_and_cases(res, 0.9, DEFAULT_STATIONS)
    by = {i["key"]: i for i in items}
    fixed = [i for i in items if i["key"] not in ("crew", "payload", "fuel", "battery")]
    x_fixed = sum(i["mass"] * i["x"] for i in fixed) / sum(i["mass"] for i in fixed)
    assert "crew" not in by
    assert by["payload"]["x"] == pytest.approx(x_fixed)
    named = {n: x for n, _m, x in cases}
    assert named["vazio"] == pytest.approx(x_fixed)
    assert named["sem combustível (ZFW)"] == pytest.approx(x_fixed)
    wide = {**DEFAULT_STATIONS, "payload": ("L", 0.50)}
    _, cases_wide, _ = _items_and_cases(res, 0.9, wide)

    def span(rows):
        xs = [x for _n, _m, x in rows]
        return max(xs) - min(xs)

    assert span(cases) < span(cases_wide)


def test_wing_loading_uses_si_gravity():
    from acdt.domains.aircraft.landing_gear import wing_loading_psf
    from acdt.domains.aircraft.weights_detailed import PSF
    # 1 N on 1 m² is 1 Pa. The mass that weighs 1 N is 1/G0 kg.
    assert wing_loading_psf(1.0 / G0, 1.0) == pytest.approx(1.0 / PSF)
    # 1 lb over 1 ft²: mass = 0.45359237 kg, area = 0.3048**2 m²
    assert wing_loading_psf(0.45359237, 0.3048 ** 2) == pytest.approx(1.0, rel=1e-3)


def test_uncited_defaults_are_named_pressupostos():
    from acdt.core.systems.mass import MTOW_CLOSURE_TOL_KG
    from acdt.domains.aircraft.landing_gear import (
        DEFAULT_TAILWHEEL_FUSELAGE_FRACTION, analyse_landing_gear)
    from acdt.domains.aircraft.weights_detailed import DEFAULT_MAIN_GEAR_LENGTH_M

    assert DEFAULT_MAIN_GEAR_LENGTH_M == 0.60
    assert DEFAULT_TAILWHEEL_FUSELAGE_FRACTION == 0.95
    assert MTOW_CLOSURE_TOL_KG == 0.05
    near = [LoadItem("vazio", 2.0, 1000, 1000, "fixed"), LoadItem("extra", 2.0, 0, 0.04, "variable")]
    assert any(p.mass == pytest.approx(1000.04) for p in operational_loadings(near, 1000).points)
    far = [LoadItem("vazio", 2.0, 1000, 1000, "fixed"), LoadItem("extra", 2.0, 0, 0.06, "variable")]
    assert all(p.mass <= 1000 + MTOW_CLOSURE_TOL_KG for p in operational_loadings(far, 1000).points)

    class Ends:
        def __init__(self, fwd, aft):
            self.x_min_m, self.x_max_m = fwd, aft

    res = _aircraft()
    res.weight_balance = Ends(2.0, 2.2)
    res.spec.assumptions["landing_gear"].pop("h_cg_m")
    res.spec.assumptions["weights"]["components"].pop("main_gear_length_m")
    gear = analyse_landing_gear(res)
    assert gear.h_cg_m == pytest.approx(DEFAULT_MAIN_GEAR_LENGTH_M + 0.5 * 1.2)
    length_note = next(n for n in gear.notes if "comprimento por omissão" in n)
    assert "0.60" in length_note and "PRESSUPOSTO" in length_note and "15.50" in length_note

    tail = _aircraft(gear="taildragger")
    tail.weight_balance = Ends(2.0, 2.2)
    placed = analyse_landing_gear(tail)
    assert placed.x_tail_m == pytest.approx(DEFAULT_TAILWHEEL_FUSELAGE_FRACTION * 8.0)
    tail_note = next(n for n in placed.notes if "0.95·L" in n)
    assert "PRESSUPOSTO" in tail_note
    tail.spec.assumptions["landing_gear"]["x_tail_m"] = 7.0
    given = analyse_landing_gear(tail)
    assert given.x_tail_m == pytest.approx(7.0)
    assert not any("0.95·L" in n for n in given.notes)
