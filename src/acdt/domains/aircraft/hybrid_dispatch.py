# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""L0 hybrid-electric energy dispatch over common mission phases (opt-in, supplied components).

Fixed supplied inclusive MTOW (no hybrid mass closure). Phase shaft power:
level P = W V/(L/D eta_p) (Raymer, *Aircraft Design*, 6th ed. 2018, Sec. 17.2);
climb/descent by the excess-power relation P = W (V/(L/D) ± RC)/eta_p
(Anderson, *Aircraft Performance and Design*, McGraw-Hill 1999, Sec. 5.10), clipped at 0
in descent; taxi/take-off/landing supplied power and duration. Constant weight at MTOW
(conservative PRESSUPOSTO, fuel burn not credited).

Rule-based supervisory control (Guzzella & Sciarretta, *Vehicle Propulsion Systems*,
3rd ed., Springer 2013, Ch. 8 "Supervisory Control Algorithms", heuristic strategies):

* series ``thermostat``: generator ON at its supplied set-point when SOC <= soc_on,
  OFF when SOC >= soc_off (hysteresis); battery supplies/absorbs the difference.
* series ``load_following``: generator follows bus demand up to its rating; battery the rest.
* parallel ``power_split``: engine supplies shaft power up to its rating, motor (battery)
  the excess (electric assist); ``electric_only_phases`` run on the battery.

Architecture vocabulary (series/parallel, degree of hybridisation) after Pornet &
Isikveren, Prog. Aerosp. Sci. 79:114-135, 2015. Constant BSFC and efficiencies are
SUPPLIED component models; optional motor η(P) table (core.motor_map). No engine-cycle decks, thermal limits or transients.
"""
from copy import deepcopy
from acdt.core.energy_storage import mapping, number
from acdt.core.concept.fleet_feedback import text

G0 = 9.80665
CITATIONS = ["Raymer 2018 Aircraft Design 6th ed. Sec. 17.2 (level power)",
             "Anderson 1999 Aircraft Performance and Design Sec. 5.10 (rate of climb / excess power)",
             "Guzzella & Sciarretta 2013 Vehicle Propulsion Systems 3rd ed. Ch. 8 (rule-based supervisory control)",
             "Pornet & Isikveren 2015 Prog. Aerosp. Sci. 79:114-135 (hybrid-electric architectures)"]
PHASES = ("taxi_out", "takeoff", "climb", "transit_out", "station", "transit_back", "descent", "landing", "taxi_in")
SUPPLIED_PHASES = ("taxi_out", "takeoff", "landing", "taxi_in")


def _src(d, name):
    text(d.get("source"), name + ".source")



def _motor_eta(motor, shaft_power_W):
    """Constant η by default; optional supplied table (core.motor_map)."""
    if motor.get("map"):
        from acdt.core.motor_map import motor_efficiency
        r = motor_efficiency(shaft_power_W, motor["map"])
        if r["status"] != "assessed" or r["efficiency"] is None:
            raise ValueError("motor map unassessed at shaft power; unknown ≠ η=1")
        return r["efficiency"], r
    return motor["efficiency"], None


def validate_hybrid(h):
    mapping(h, {"architecture", "mass_kg", "aero", "engine", "generator", "motor", "battery", "fuel", "dispatch",
                "phases", "hotel_power_W", "source", "dt_s"}, "hybrid")
    _src(h, "hybrid")
    if h.get("architecture") not in ("series", "parallel"): raise ValueError("hybrid.architecture must be series|parallel")
    number("hybrid.mass_kg", h.get("mass_kg"), positive=True)
    number("hotel_power_W", h.get("hotel_power_W", 0.))
    number("dt_s", h.get("dt_s", 30.), positive=True, maximum=600)
    a = h.get("aero"); mapping(a, {"LD", "eta_prop", "altitude_m", "source"}, "hybrid.aero"); _src(a, "hybrid.aero")
    number("LD", a.get("LD"), positive=True); number("eta_prop", a.get("eta_prop"), positive=True, maximum=1)
    e = h.get("engine"); mapping(e, {"rated_power_W", "bsfc_kg_per_kWh", "source"}, "hybrid.engine"); _src(e, "hybrid.engine")
    number("engine.rated_power_W", e.get("rated_power_W"), positive=True); number("bsfc_kg_per_kWh", e.get("bsfc_kg_per_kWh"), positive=True)
    m = h.get("motor"); mapping(m, {"rated_power_W", "efficiency", "source", "map"}, "hybrid.motor"); _src(m, "hybrid.motor")
    number("motor.rated_power_W", m.get("rated_power_W"), positive=True); number("motor.efficiency", m.get("efficiency"), positive=True, maximum=1)
    if "map" in m:
        from acdt.core.motor_map import validate_motor_map
        validate_motor_map(m["map"])
    if h["architecture"] == "series":
        g = h.get("generator"); mapping(g, {"efficiency", "source"}, "hybrid.generator"); _src(g, "hybrid.generator")
        number("generator.efficiency", g.get("efficiency"), positive=True, maximum=1)
    elif "generator" in h:
        raise ValueError("parallel hybrid has no generator block (engine drives the shaft)")
    b = h.get("battery")
    mapping(b, {"capacity_Wh", "soc_initial", "soc_min", "soc_max", "c_rate_max", "charge_efficiency", "discharge_efficiency", "source"}, "hybrid.battery")
    _src(b, "hybrid.battery")
    number("capacity_Wh", b.get("capacity_Wh"), positive=True); number("c_rate_max", b.get("c_rate_max"), positive=True)
    for k in ("soc_initial", "soc_min", "soc_max", "charge_efficiency", "discharge_efficiency"):
        number(k, b.get(k), maximum=1)
    if not b["soc_min"] < b["soc_initial"] <= b["soc_max"]: raise ValueError("need soc_min < soc_initial <= soc_max")
    f = h.get("fuel"); mapping(f, {"capacity_kg", "source"}, "hybrid.fuel"); _src(f, "hybrid.fuel"); number("fuel.capacity_kg", f.get("capacity_kg"), positive=True)
    d = h.get("dispatch"); mapping(d, {"rule", "soc_on", "soc_off", "generator_setpoint_W", "electric_only_phases", "source"}, "hybrid.dispatch")
    _src(d, "hybrid.dispatch")
    rules = {"series": ("thermostat", "load_following"), "parallel": ("power_split",)}[h["architecture"]]
    if d.get("rule") not in rules: raise ValueError(f"{h['architecture']} dispatch rule must be one of {rules}")
    if d["rule"] == "thermostat":
        for k in ("soc_on", "soc_off"): number(k, d.get(k), maximum=1)
        if not b["soc_min"] <= d["soc_on"] < d["soc_off"] <= b["soc_max"]: raise ValueError("need soc_min <= soc_on < soc_off <= soc_max")
        number("generator_setpoint_W", d.get("generator_setpoint_W"), positive=True)
    elif set(d) & {"soc_on", "soc_off", "generator_setpoint_W"}:
        raise ValueError("soc_on/soc_off/generator_setpoint_W are thermostat-only")
    eo = d.get("electric_only_phases", [])
    if not isinstance(eo, list) or set(eo) - set(PHASES): raise ValueError("electric_only_phases must name common phases")
    if eo and h["architecture"] != "parallel": raise ValueError("electric_only_phases is a parallel power_split option")
    ph = h.get("phases")
    mapping(ph, set(SUPPLIED_PHASES) | {"climb", "descent", "source"}, "hybrid.phases"); _src(ph, "hybrid.phases")
    for k in SUPPLIED_PHASES:
        if k in ph:
            mapping(ph[k], {"duration_h", "shaft_power_W"}, "phase " + k)
            number(k + ".duration_h", ph[k].get("duration_h")); number(k + ".shaft_power_W", ph[k].get("shaft_power_W"))
    for k in ("climb", "descent"):
        if k in ph:
            mapping(ph[k], {"altitude_m", "rate_m_s", "speed_m_s"}, "phase " + k)
            number(k + ".altitude_m", ph[k].get("altitude_m")); number(k + ".rate_m_s", ph[k].get("rate_m_s"), positive=True)
            number(k + ".speed_m_s", ph[k].get("speed_m_s"), positive=True)


def phase_plan(h, distance_km, speed_m_s, station_h, reserve_h=0.):
    """Common phases → (name, shaft W, duration h, method). Unsupplied supplied-type phases are absent (flagged)."""
    W = h["mass_kg"] * G0; a = h["aero"]; ph = h["phases"]
    lvl = lambda V: W * V / (a["LD"] * a["eta_prop"])
    out = []
    for k in ("taxi_out", "takeoff"):
        if k in ph: out.append((k, ph[k]["shaft_power_W"], ph[k]["duration_h"], "supplied power and duration"))
    if "climb" in ph:
        c = ph["climb"]; out.append(("climb", W * (c["speed_m_s"] / a["LD"] + c["rate_m_s"]) / a["eta_prop"],
                                     c["altitude_m"] / c["rate_m_s"] / 3600, "excess-power climb, Anderson 1999 Sec. 5.10"))
    leg = distance_km * 1000 / speed_m_s / 3600
    out += [("transit_out", lvl(speed_m_s), leg, "level, Raymer 2018 Sec. 17.2"),
            ("station", lvl(speed_m_s), station_h, "level at sample speed"),
            ("transit_back", lvl(speed_m_s), leg, "level, Raymer 2018 Sec. 17.2")]
    if "descent" in ph:
        c = ph["descent"]; out.append(("descent", max(0., W * (c["speed_m_s"] / a["LD"] - c["rate_m_s"]) / a["eta_prop"]),
                                       c["altitude_m"] / c["rate_m_s"] / 3600, "excess-power descent (clipped at 0)"))
    for k in ("landing", "taxi_in"):
        if k in ph: out.append((k, ph[k]["shaft_power_W"], ph[k]["duration_h"], "supplied power and duration"))
    if reserve_h > 0: out.append(("reserve", lvl(speed_m_s), reserve_h, "operational reserve flown level at sample speed"))
    return out


def dispatch(h, plan):
    """Time-stepped rule-based dispatch; returns totals, SOC history per phase, checks (unknown never passes)."""
    b, e, m, d = h["battery"], h["engine"], h["motor"], h["dispatch"]
    series = h["architecture"] == "series"
    eta_g = h["generator"]["efficiency"] if series else None
    cap = b["capacity_Wh"]; soc = b["soc_initial"]; gen_on = series and d["rule"] == "thermostat" and soc <= d["soc_on"]
    hotel = h.get("hotel_power_W", 0.); dt_max = h.get("dt_s", 30.) / 3600
    fuel = 0.; batt_out = batt_in = 0.; peak = dict(battery_W=0., engine_W=0., motor_W=0.)
    soc_min_seen = soc; rows = []
    for name, P, T, method in plan:
        n = max(1, int(-(-T // dt_max))) if T > 0 else 0
        dt = T / n if n else 0.
        f0, s0 = fuel, soc
        for _ in range(n):
            if series:
                eta_m,_mm = _motor_eta(m, P); P_mot_in = P / eta_m; peak["motor_W"] = max(peak["motor_W"], P)
                bus = P_mot_in + hotel
                if d["rule"] == "thermostat":
                    if soc <= d["soc_on"]: gen_on = True
                    elif soc >= d["soc_off"]: gen_on = False
                    P_gen = d["generator_setpoint_W"] if gen_on else 0.
                else:
                    P_gen = min(bus, e["rated_power_W"] * eta_g)
                P_eng = P_gen / eta_g
                P_b = bus - P_gen
            else:
                eng = 0. if name in d.get("electric_only_phases", []) else min(P, e["rated_power_W"])
                mot = P - eng; peak["motor_W"] = max(peak["motor_W"], mot)
                P_eng = eng; eta_m,_mm = _motor_eta(m, mot); P_b = mot / eta_m + hotel
            peak["engine_W"] = max(peak["engine_W"], P_eng); peak["battery_W"] = max(peak["battery_W"], abs(P_b))
            fuel += e["bsfc_kg_per_kWh"] * P_eng / 1000 * dt
            if P_b >= 0:
                dE = P_b * dt / b["discharge_efficiency"]; batt_out += P_b * dt; soc -= dE / cap
            else:
                dE = -P_b * dt * b["charge_efficiency"]; batt_in += -P_b * dt
                soc = soc + dE / cap
            soc_min_seen = min(soc_min_seen, soc)
        rows.append(dict(phase=name, shaft_power_W=P, duration_h=T, fuel_kg=fuel - f0, soc_start=s0, soc_end=soc, method=method))
    checks = [dict(name="soc_above_min", passed=soc_min_seen >= b["soc_min"] - 1e-12, soc_min_seen=soc_min_seen, soc_min=b["soc_min"]),
              dict(name="soc_below_max", passed=max([b["soc_initial"]] + [r["soc_end"] for r in rows]) <= b["soc_max"] + 1e-12),
              dict(name="battery_c_rate", passed=peak["battery_W"] <= b["c_rate_max"] * cap * (1 + 1e-12), peak_W=peak["battery_W"], limit_W=b["c_rate_max"] * cap),
              dict(name="engine_rating", passed=peak["engine_W"] <= e["rated_power_W"] * (1 + 1e-12), peak_W=peak["engine_W"]),
              dict(name="motor_rating", passed=peak["motor_W"] <= m["rated_power_W"] * (1 + 1e-12), peak_W=peak["motor_W"]),
              dict(name="fuel_capacity", passed=fuel <= h["fuel"]["capacity_kg"] * (1 + 1e-12), fuel_kg=fuel, capacity_kg=h["fuel"]["capacity_kg"])]
    recharge = max(0., (b["soc_initial"] - soc) * cap)
    return dict(phases=rows, fuel_kg=fuel, battery_discharged_Wh=batt_out, battery_charged_in_flight_Wh=batt_in,
                soc_final=soc, soc_min_seen=soc_min_seen, ground_recharge_Wh=recharge, peaks=peak, checks=checks,
                feasible=all(c["passed"] for c in checks), flight_h=sum(p[2] for p in plan),
                degree_of_hybridisation_power=m["rated_power_W"] / (m["rated_power_W"] + e["rated_power_W"]) if not series else None,
                rule=d["rule"], architecture=h["architecture"], citations=CITATIONS,
                note="L0 rule-based dispatch with supplied constant efficiencies/BSFC; ground recharge restores soc_initial (terminal energy, Wh)")


def evaluate(h, distance_km, speed_m_s, station_h, reserve_h=0.):
    validate_hybrid(h)
    return dispatch(h, phase_plan(h, distance_km, speed_m_s, station_h, reserve_h))
