import math

import pytest

from acdt.core.systems import load_default_db
from acdt.core.systems.avionics import AutopilotRequirements, Load, PowerBudget, select_autopilot
from acdt.core.systems.battery import best_pack, size_battery
from acdt.core.systems.compliance import applicable_standards, checklist_markdown
from acdt.core.systems.electric_propulsion import KP_METRIC, select_motor_esc, size_propeller
from acdt.core.systems.harness import Connector, Harness, Wire, awg_area_m2, resistance, select_gauge
from acdt.core.systems.mass import MassItem, cg, percent_mac
from acdt.core.systems.servos import hinge_moment, select_servo

DB = load_default_db()
CELL = {"id": "c", "chemistry": "li_ion", "v_nom": 3.6, "v_max": 4.2, "capacity_ah": 5.0, "i_cont": 10, "mass": 0.07}


def test_propeller_raymer_statistics():
    p = size_propeller(1000.0, 22.0, 1.225, 340.0, n_blades=2)
    assert p.D == pytest.approx(KP_METRIC[2] * 1.0 ** 0.25)
    assert p.rpm_cruise == pytest.approx(22.0 / (0.7 * p.D) * 60)
    lim = size_propeller(1000.0, 22.0, 1.225, 340.0, D_max=0.4, tip_mach_limit=0.3)
    assert lim.D == 0.4 and lim.tip_mach_max <= 0.3 + 1e-9


def test_motor_kv_and_current():
    m = select_motor_esc(DB, 1000.0, 4000.0, 28.8, 33.6)
    assert m.kv_target == pytest.approx(4000 / (28.8 * 0.85))
    assert m.motor is not None and m.motor["p_max"] >= 1200 and m.motor["v_max"] >= 33.6
    assert m.esc is not None and m.esc["i_cont"] >= 1.2 * m.i_max
    assert m.feasible and m.esc_feasible


def _two_motors():
    from types import SimpleNamespace
    return SimpleNamespace(motors=[
        {"id": "light", "p_max": 2000, "v_max": 40, "i_max": 200, "kv": 160, "mass": 0.2},
        {"id": "heavy", "p_max": 3000, "v_max": 40, "i_max": 200, "kv": 160, "mass": 0.5},
    ], escs=[
        {"id": "esc_s", "i_cont": 200, "v_max": 40, "mass": 0.05},
        {"id": "esc_b", "i_cont": 200, "v_max": 40, "mass": 0.2},
    ])


def test_free_selection_is_the_lightest_and_a_pin_is_not_replaced():
    # rpm so that Kv = rpm / (V · load_ratio) equals 160, inside both motors' band.
    rpm = 160.0 * 28.8 * 0.85
    db = _two_motors()
    free = select_motor_esc(db, 1000.0, rpm, 28.8, 33.6)
    assert free.motor["id"] == "light" and free.esc["id"] == "esc_s" and free.feasible
    pinned = select_motor_esc(db, 1000.0, rpm, 28.8, 33.6, motor_id="heavy", esc_id="esc_b")
    assert pinned.motor["id"] == "heavy" and pinned.feasible
    assert pinned.esc["id"] == "esc_b" and pinned.esc_feasible
    assert pinned.motor["mass"] > free.motor["mass"]


def test_pinned_motor_below_the_power_margin_keeps_its_mass():
    rpm = 160.0 * 28.8 * 0.85
    db = _two_motors()
    # 1.2 · 2000 W = 2400 W: light (2000 W) fails, heavy (3000 W) is the free choice.
    free = select_motor_esc(db, 2000.0, rpm, 28.8, 33.6)
    assert free.motor["id"] == "heavy" and free.feasible
    held = select_motor_esc(db, 2000.0, rpm, 28.8, 33.6, motor_id="light")
    assert held.motor["id"] == "light" and held.motor["mass"] == 0.2 and held.feasible is False


def test_battery_energy_and_current_limited():
    E = 1000 * 3600  # 1 kWh
    p = size_battery(CELL, E, i_peak=20, S=8)
    assert p.P == math.ceil(E / (8 * 3.6 * 5 * 3600)) and p.limiting == "energy"
    assert p.mass == pytest.approx(8 * p.P * 0.07 * 1.2)
    q = size_battery(CELL, 100 * 3600, i_peak=95, S=8)
    assert q.limiting == "current" and q.P == 10 and q.current_ok
    best = best_pack(DB.cells, E, 30, lambda c: 8)
    assert best.mass == min(size_battery(c, E, 30, 8).mass for c in DB.cells)


def test_servo_hinge_moment():
    H = hinge_moment(q=500, S_c=0.05, c_c=0.08, Ch_alpha=-0.25, Ch_delta=-0.6, alpha=0.1, delta=0.4)
    assert H == pytest.approx((-0.025 - 0.24) * 500 * 0.05 * 0.08)
    s = select_servo(DB.servos, 1.0, 8.4)
    assert s["torque"] >= 1.0
    assert select_servo(DB.servos, 1e3, 8.4) is None


def test_autopilot_selection_and_rejections():
    ap, rej = select_autopilot(DB.autopilots, AutopilotRequirements(min_imu=3, min_baro=2, min_can=1))
    assert ap["imu"] >= 3 and ap["baro"] >= 2
    assert any("IMU" in r for r in rej)
    none, _ = select_autopilot(DB.autopilots, AutopilotRequirements(min_imu=9))
    assert none is None


def test_power_budget():
    pb = PowerBudget([Load("a", 10), Load("b", 20, duty=0.5, peak_w=40), Load("s", 2, peak_w=20, bus="servo")])
    assert pb.average_w == pytest.approx(10 + 10 + 2)
    assert pb.peak_w == pytest.approx(10 + 40 + 20)
    assert pb.regulator_rating_w("avionics") == pytest.approx(1.5 * 50)


def test_wire_gauge_sizing():
    R = resistance(1.0, awg_area_m2(12), 20.0)
    assert R == pytest.approx(1.724e-8 / awg_area_m2(12), rel=0.02)  # IEC 60028 copper
    g = select_gauge(40, 0.5, 44.4)
    assert g.awg is not None and g.drop_fraction <= 0.03
    long = select_gauge(5, 3.0, 5.0)
    assert long.governed_by == "voltage drop" and long.drop_fraction <= 0.03


def test_harness_netlist_exports():
    h = Harness("t")
    h.add_connector(Connector("BAT", ["+", "-"]))
    h.add_connector(Connector("ESC", ["+", "-"]))
    h.connect(Wire("W1", ("BAT", "+"), ("ESC", "+"), "VBAT", 40, 0.4, 44.4))
    h.connect(Wire("W2", ("BAT", "-"), ("ESC", "-"), "GND", 40, 0.4, 44.4))
    with pytest.raises(KeyError):
        h.connect(Wire("W3", ("BAT", "x"), ("ESC", "+"), "bad"))
    h.size_wires()
    assert set(h.netlist()) == {"VBAT", "GND"}
    assert "W1" in h.to_csv() and "connectors:" in h.to_wireviz_yaml() and h.to_dot().startswith("graph")


def test_compliance_checklist():
    ids = {s["id"] for s in applicable_standards("easa_specific", 21.0, True, {"li_battery"})}
    assert {"EASA-SORA-2.5", "ASTM-F3298-24", "UN-38.3"} <= ids
    assert "STANAG-4671" not in ids
    ga = {s["id"] for s in applicable_standards("cs_23", 1100, False, set())}
    assert "CS-23" in " ".join(ga) and "EASA-SORA-2.5" not in ga
    assert "Checklist" in checklist_markdown("easa_specific", 21.0, True, set())


def test_cg():
    items = [MassItem("a", 1.0, 0.0), MassItem("b", 3.0, 1.0)]
    assert cg(items) == pytest.approx(0.75)
    assert percent_mac(0.75, 0.5, 1.0) == pytest.approx(25.0)
