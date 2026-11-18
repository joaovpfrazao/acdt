"""Quasi-steady point-mass mission (3-DOF kinematics) for N0 and N1.

Anderson, J. D. (1999), *Aircraft Performance and Design*, Ch. 3 (flat-earth point mass and velocity
addition) and Ch. 5 (excess power, climb, glide tan γ = 1/(L/D), coordinated turn
Ω = g √(n²−1)/V, level turn n = 1/cos φ).
Raymer, D. P. (2018), *Aircraft Design: A Conceptual Approach*, 6th ed., Ch. 17 (mission segments,
take-off Sec. 17.8, landing Sec. 17.9).

The integrator does not integrate V̇ or γ̇. Speed and flight-path angle are the equilibrium of those
equations, and the position (north, east, altitude) is explicit Euler on that equilibrium. Along-track
acceleration is neglected (PRESSUPOSTO: the segment speed is reached immediately). Steady wind only:
the wind triangle is Anderson 1999 Ch. 3; turbulence and 1−cos gusts stay on the 6-DOF runner.
The drag polar, propulsion and mass come from a sizing result or from the N0 ``aircraft`` block when
there is no shape yet. A flight-model plant (no camber) is the one compared with the 6-DOF run.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from acdt import G0
from acdt.core.atmosphere import isa

from ..performance import PerfModel, landing_distance, takeoff_distance_integrated
from ..propulsion import is_propeller, lapse
from .failures import resolve_failures
from .mission import load_mission
from .sensors import (ON_STATION_DEFAULT, SENSOR_ON_DEFAULT, _metrics_block, effective_swath, evaluate_sensors,
                      validate_sensor)
from .wind import WindField

METHOD = ("Anderson, J. D. (1999), Aircraft Performance and Design, Ch. 3 (flat-earth point mass, "
          "velocity addition) and Ch. 5 (excess power, climb, glide tan γ = 1/(L/D), coordinated turn "
          "Ω = g√(n²−1)/V, level turn n = 1/cos φ); Raymer, D. P. (2018), Aircraft Design: A Conceptual "
          "Approach, 6th ed., Ch. 17 (mission segments, take-off Sec. 17.8, landing Sec. 17.9)")
VALIDITY = ("equilíbrio quase-estacionário (sem dinâmica de velocidade nem de ângulo de trajetória); "
            "terra plana, norte/este locais, sem terreno; só vento constante; polar parabólica; "
            "deteção é oportunidade, não POD com clutter")
# Raymer 17.8 ground-roll ODE is integrated here for TIME only. Distance comes from takeoff_distance_integrated.
_BSFC_TO_CP = 0.45359237 / (745.69987 * 3600.0)  # lb/hp/h → kg/(W·s), same factors as sizing._prop_data
_SCREEN = 15.24  # 50 ft, Raymer 17.8 / 17.9


def wind_triangle(Va: float, gamma: float, course: float, wind_ned) -> dict | None:
    """Ground velocity for a commanded course (0 = north, clockwise toward east).

    Va_h = V cos γ, w_along = w_N cos χ + w_E sin χ, w_cross = −w_N sin χ + w_E cos χ,
    sin(crab) = −w_cross/Va_h, Vg = w_along + √(Va_h² − w_cross²). None when the wind triangle has no
    solution (Anderson 1999 Ch. 3). The ground track stays on the commanded course; crab is the heading
    offset into the wind."""
    Va_h = float(Va) * math.cos(float(gamma))
    wN, wE = float(wind_ned[0]), float(wind_ned[1])
    w_along = wN * math.cos(course) + wE * math.sin(course)
    w_cross = -wN * math.sin(course) + wE * math.cos(course)
    if Va_h <= 1e-6 or abs(w_cross) > abs(Va_h) - 1e-9:
        return None
    Vg = w_along + math.sqrt(max(Va_h * Va_h - w_cross * w_cross, 0.0))
    if Vg <= 1e-6:
        return None
    crab = math.asin(max(-1.0, min(1.0, -w_cross / Va_h)))
    return {"Vg": Vg, "crab": crab, "psi": course + crab, "vN": Vg * math.cos(course), "vE": Vg * math.sin(course),
            "w_along": w_along, "w_cross": w_cross, "Va_h": Va_h}


def _air_plus_wind(Va: float, gamma: float, psi: float, wind_ned) -> tuple[float, float, float]:
    """Ground velocity when the air heading is known (turn): air vector plus wind."""
    Va_h = float(Va) * math.cos(float(gamma))
    vN = Va_h * math.cos(psi) + float(wind_ned[0])
    vE = Va_h * math.sin(psi) + float(wind_ned[1])
    return vN, vE, math.hypot(vN, vE)


@dataclass
class Plant:
    """Parabolic polar plus a propulsion map. Thrust and flow follow the flight-model model
    (η P/V, or a propeller map when the sizing result has one)."""
    kind: str
    S: float
    CD0: float
    K: float
    CLmax: float
    CLmax_to: float
    CLmax_land: float
    P_sl: float | None
    T_sl: float | None
    eta_cruise: float
    eta_climb: float
    eta_takeoff: float
    c_p: float | None
    c_t: float | None
    eta_tot: float
    eta_chain: float
    P_sys: float
    payload_power_W: float
    generator_efficiency: float | None
    n_engines: int
    mu_roll: float
    CL_ground: float
    dCD0_to: float
    mu_brake: float
    mass_kg: float
    budget: float | None          # usable kg or J; None flies the profile
    electric: bool
    camber: object | None = None
    V_low: float = 1.0
    source: str = "n0"
    notes: list = field(default_factory=list)
    _thrust_fn: object | None = None
    _prop: object | None = None

    auxiliary_fuel_flow_kg_s: float = 0.0
    auxiliary_shaft_W: float = 0.0

    def polar(self):
        from ..aero.drag import DragPolar
        return DragPolar(self.CD0, self.K, self.camber)

    def stall(self, W: float, rho: float, CLmax: float | None = None) -> float:
        return math.sqrt(2.0 * W / (rho * self.S * (CLmax or self.CLmax)))

    def drag_cl(self, W: float, V: float, h: float, n: float = 1.0) -> tuple[float, float]:
        rho = isa(max(h, 0.0)).rho
        qS = 0.5 * rho * V * V * self.S
        if qS <= 0:
            return float("inf"), float("inf")
        CL = n * W / qS
        cd = self.CD0 + self.K * CL * CL
        if self.camber is not None:
            cd = cd + float(self.camber.dcd(CL))
        return qS * cd, CL

    def roc(self, W: float, V: float, h: float, throttle: float = 1.0, engine_frac: float = 1.0,
            n: float = 1.0) -> float:
        """Climb rate (T − D) V / W at one speed (Anderson 1999 Ch. 5). Public for the identity test."""
        D, _ = self.drag_cl(W, V, h, n)
        T, _ = self.propulsion(V, h, throttle, engine_frac)
        return (T - D) * V / max(W, 1e-9)

    def propulsion(self, V: float, h: float, throttle: float, engine_frac: float = 1.0) -> tuple[float, float]:
        """(T [N], fuel flow [kg/s] or battery power [W]). ``engine_frac`` ≤ 0 is all engines out:
        thrust 0; electric keeps the idle bus (systems + payload); fuel flow is 0 (generator dead).
        Identical engines (PRESSUPOSTO)."""
        if self.auxiliary_shaft_W and engine_frac<1:
            raise ValueError("onboard generator failure/OEI scheduling is unassessed")
        T, flow = self._raw_thrust(V, h, throttle)
        Tid, fid = self._raw_thrust(V, h, 0.0) if engine_frac < 1.0 - 1e-12 else (T, flow)
        if engine_frac <= 1e-12:
            T, flow = 0.0, (fid if self.electric else 0.0)
        elif engine_frac < 1.0 - 1e-12:
            T = Tid + (T - Tid) * engine_frac
            flow = fid + (flow - fid) * engine_frac
        if self.payload_power_W:
            if self.electric:
                flow += self.payload_power_W
            elif self.generator_efficiency:
                flow += (self.c_p or 0.0) * self.payload_power_W / self.generator_efficiency
        if engine_frac>0: flow += self.auxiliary_fuel_flow_kg_s
        return T, flow

    def _raw_thrust(self, V: float, h: float, throttle: float) -> tuple[float, float]:
        if self._thrust_fn is not None:
            return self._thrust_fn(max(V, 0.0), h, throttle)
        th = min(max(float(throttle), 0.0), 1.0)
        sig = isa(max(h, 0.0)).sigma
        if self._prop is not None and is_propeller(self.kind):
            op = self._prop.operating_point(max(V, 0.0), h, th)
            if self.electric:
                return op["T"], op["P"] / self.eta_chain + self.P_sys
            return op["T"], (self.c_p or 0.0) * op["P"]
        if is_propeller(self.kind):
            P = th * max(0.0,(self.P_sl or 0.0)*lapse(self.kind,sig)-self.auxiliary_shaft_W)
            Tlow = self.eta_takeoff * P / max(self.V_low, 1e-3)
            T = min(Tlow, self.eta_cruise * P / max(V, 1e-3))
            if self.electric:
                return T, P / self.eta_chain + self.P_sys
            return T, (self.c_p or 0.0) * P
        T = th * (self.T_sl or 0.0) * lapse(self.kind, sig)
        return T, (self.c_t or 0.0) * T

    def throttle_for(self, V: float, h: float, T_req: float, engine_frac: float = 1.0):
        """Bisection on throttle. Returns (throttle, flow, T) or None when even full throttle is short by > 1 N."""
        Tmax, _ = self.propulsion(V, h, 1.0, engine_frac)
        Tidle, flow_idle = self.propulsion(V, h, 0.0, engine_frac)
        if T_req <= Tidle + 1e-6:
            return 0.0, flow_idle, Tidle, True  # idle floor: path may still be imposed
        if Tmax < T_req - 1.0:
            return None
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if self.propulsion(V, h, mid, engine_frac)[0] < T_req:
                lo = mid
            else:
                hi = mid
        T, flow = self.propulsion(V, h, hi, engine_frac)
        return hi, flow, T, False

    def as_perf(self) -> PerfModel:
        """PerfModel for Raymer 17.8 / 17.9 distances. η_climb is the cruise value when the flight model
        does not store it (PRESSUPOSTO, noted by the caller)."""
        return PerfModel(self.kind, self.S, self.CD0, self.K, self.CLmax, self.P_sl, self.T_sl, self.eta_cruise,
                         self.eta_climb, self.eta_takeoff, self.c_p, self.c_t, self.eta_tot, self.P_sys,
                         self.CLmax_to, self.CLmax_land, self.mu_roll, self.CL_ground, self.dCD0_to,
                         None, self.camber, auxiliary_fuel_flow_kg_s=self.auxiliary_fuel_flow_kg_s,
                         auxiliary_shaft_W=self.auxiliary_shaft_W)

    @classmethod
    def from_n0(cls, aircraft: dict) -> "Plant":
        if not isinstance(aircraft, dict):
            raise ValueError("aircraft tem de ser um dicionário")
        notes = []
        src = aircraft.get("source")
        if not src:
            notes.append("bloco aircraft sem source: origem dos números não citada")
            src = "não citada"
        for key in ("mass_kg", "S_m2", "CD0", "CLmax"):
            if key not in aircraft:
                raise ValueError(f"aircraft.{key} é obrigatório (N0 não herda o dimensionamento)")
        if "K" in aircraft:
            K = float(aircraft["K"])
        elif "AR" in aircraft and "e" in aircraft:
            K = 1.0 / (math.pi * float(aircraft["AR"]) * float(aircraft["e"]))
        else:
            raise ValueError("aircraft: falta K ou o par (AR, e)")
        p = aircraft.get("propulsion") or {}
        kind = p.get("kind")
        if kind not in ("electric", "piston_prop", "turboprop", "jet"):
            raise ValueError("propulsion.kind: electric, piston_prop, turboprop ou jet")
        electric = kind == "electric"
        eta_cruise = p.get("eta_cruise")
        if is_propeller(kind):
            if "P_sl_W" not in p:
                raise ValueError("propulsão a hélice: falta P_sl_W")
            if eta_cruise is None:
                raise ValueError("propulsão: falta eta_cruise (não se aplica 0,80 por omissão)")
            eta_cruise = float(eta_cruise)
        else:
            if "T_sl_N" not in p:
                raise ValueError("jato: falta T_sl_N")
            eta_cruise = float(eta_cruise) if eta_cruise is not None else 1.0
        eta_climb = float(p["eta_climb"]) if "eta_climb" in p else eta_cruise
        if "eta_climb" not in p and is_propeller(kind):
            notes.append("eta_climb = eta_cruise (PRESSUPOSTO; a subida em voo usa η de cruzeiro do modelo de tração)")
        eta_takeoff = float(p["eta_takeoff"]) if "eta_takeoff" in p else None
        c_p = c_t = None
        eta_tot = float(p.get("eta_tot", 1.0))
        eta_chain = 1.0
        if electric:
            if "eta_tot" not in p:
                raise ValueError("elétrico: falta eta_tot (bateria → tração)")
            eta_tot = float(p["eta_tot"])
            if eta_cruise <= 0:
                raise ValueError("eta_cruise tem de ser > 0")
            eta_chain = eta_tot / eta_cruise
            if eta_chain > 1.0 + 1e-9:
                notes.append(f"η_tot/η_cruise = {eta_chain:.3f} > 1 (PRESSUPOSTO inconsistente); "
                             "o consumo usa essa razão na mesma")
        elif kind == "jet":
            if "c_t" not in p:
                raise ValueError("jato: falta c_t [kg/(N·s)]")
            c_t = float(p["c_t"])
        else:
            if "c_p" in p:
                c_p = float(p["c_p"])
            elif "bsfc_lb_hp_h" in p:
                c_p = float(p["bsfc_lb_hp_h"]) * _BSFC_TO_CP
            else:
                raise ValueError("propulsor: falta c_p [kg/(W·s)] ou bsfc_lb_hp_h")
        payload = float(p.get("payload_power_W", 0.0))
        gen = float(p["generator_efficiency"]) if "generator_efficiency" in p else None
        if payload and not electric and not gen:
            raise ValueError("payload_power_W num motor a combustível precisa de generator_efficiency "
                             "(não se inventa η do gerador)")
        if "P_systems_W" in p:
            P_sys = float(p["P_systems_W"])
        elif "systems_power_W" in p:
            P_sys = float(p["systems_power_W"])
        else:
            P_sys = 0.0
            notes.append("P_systems_W = 0 (não declarado)")
        n_eng = int(p["n_engines"]) if "n_engines" in p else 1
        if "n_engines" not in p:
            notes.append("n_engines = 1 (não declarado)")
        if n_eng < 1:
            raise ValueError("n_engines tem de ser ≥ 1")
        CLmax = float(aircraft["CLmax"])
        if "CLmax_takeoff" in aircraft:
            CLto = float(aircraft["CLmax_takeoff"])
        else:
            CLto = CLmax
            notes.append("CLmax_takeoff = CLmax (sem alta sustentação declarada)")
        if "CLmax_landing" in aircraft:
            CLl = float(aircraft["CLmax_landing"])
        else:
            CLl = CLmax
            notes.append("CLmax_landing = CLmax (sem alta sustentação declarada)")

        def _fb(key, default, text):
            if key in aircraft:
                return float(aircraft[key])
            notes.append(text)
            return default

        mu_roll = _fb("mu_roll", 0.04, "mu_roll = 0.04 (PRESSUPOSTO)")
        CL_g = _fb("CL_ground", 0.5, "CL_ground = 0.5 (PRESSUPOSTO)")
        dCD0 = _fb("dCD0_takeoff", 0.01, "dCD0_takeoff = 0.01 (PRESSUPOSTO)")
        mu_b = _fb("mu_brake", 0.4, "mu_brake = 0.4 (PRESSUPOSTO, dentro da gama da Raymer Table 17.1)")
        budget = None
        if electric and "battery_Wh" in p:
            budget = float(p["battery_Wh"]) * 3600.0  # usable Wh already net of reserve; do not apply DoD again
        elif (not electric) and "fuel_kg" in p:
            budget = float(p["fuel_kg"])
        else:
            notes.append("sem orçamento de combustível/energia: o perfil voa sem limite de consumo")
        plant = cls(kind, float(aircraft["S_m2"]), float(aircraft["CD0"]), K, CLmax, CLto, CLl,
                    float(p["P_sl_W"]) if "P_sl_W" in p else None,
                    float(p["T_sl_N"]) if "T_sl_N" in p else None,
                    eta_cruise, eta_climb, eta_takeoff if eta_takeoff is not None else eta_cruise,
                    c_p, c_t, eta_tot, eta_chain, P_sys, payload, gen, n_eng, mu_roll, CL_g, dCD0, mu_b,
                    float(aircraft["mass_kg"]), budget, electric, None, float(p.get("V_low_m_s", 1.0)),
                    "n0", notes)
        if eta_takeoff is None:
            plant.eta_takeoff = eta_cruise
            plant._eta_takeoff_missing = True
        else:
            plant._eta_takeoff_missing = False
        plant.source_text = src
        return plant

    @classmethod
    def from_sizing(cls, res) -> "Plant":
        pm = PerfModel.from_result(res)
        from ..performance import mission_budget
        budget, bnote = mission_budget(res)
        n_eng = int(res.spec.assumptions["propulsion"].get("n_engines", 1))
        electric = pm.kind == "electric"
        eta_chain = (pm.eta_tot / pm.eta_cruise) if (electric and pm.eta_cruise) else 1.0
        notes = [bnote, "avião do dimensionamento (a massa pontual não constrói o modelo de voo AVL)"]
        if getattr(res, "assembly_loop", None):
            notes.append("CD0 veio do ciclo de montagem")
        plant = cls(pm.kind, pm.S, pm.CD0, pm.K, pm.CLmax, pm.CLmax_to, pm.CLmax_land, pm.P_sl, pm.T_sl,
                    pm.eta_cruise, pm.eta_climb, pm.eta_takeoff, pm.c_p, pm.c_t, pm.eta_tot, eta_chain, pm.P_sys,
                    0.0, None, n_eng, pm.mu_roll, pm.CL_ground, pm.dCD0_to, 0.4, float(res.sizing.W0), budget,
                    electric, pm.camber, 1.0, "sizing", notes, None, pm.prop)
        plant.auxiliary_shaft_W=pm.auxiliary_shaft_W
        plant.auxiliary_fuel_flow_kg_s=pm.auxiliary_fuel_flow_kg_s
        plant._eta_takeoff_missing = False
        plant.source_text = "sizing"
        plant.notes.append("P_systems já está no PerfModel; a potência de carga do bloco aircraft não se soma")
        return plant

    @classmethod
    def from_flight_model(cls, fm) -> "Plant":
        """Same CD0, K, S and ``Propulsion.thrust`` as the 6-DOF model. No camber (the quasi-steady
        comparison does not have it either)."""
        a, p, m = fm.aero, fm.prop, fm.mass
        electric = p.kind == "electric"
        CLmax = float(a.clmax(0.0))
        flaps = list(a.flap_deg)
        CLto = float(a.clmax(flaps[1] if len(flaps) > 1 else 0.0))
        CLl = float(a.clmax(flaps[-1] if flaps else 0.0))
        budget = (m.battery_J if electric else m.fuel_kg) or None
        notes = ["polar e propulsão do modelo de voo, sem camber (o mesmo modelo do quase-estacionário)",
                 "η_climb não está no modelo de voo: a descolagem Raymer usa η_climb = η_cruise (PRESSUPOSTO)"]
        if budget is None:
            notes.append("sem orçamento de combustível/energia: o perfil voa sem limite de consumo")
        plant = cls(p.kind, a.S, a.CD0, a.K, CLmax, CLto, CLl, p.P_sl, p.T_sl, p.eta_cruise, p.eta_cruise,
                    p.eta_takeoff, p.c_p, p.c_t, p.eta_chain * p.eta_cruise, p.eta_chain, p.P_sys, 0.0, None,
                    int(p.n_engines), 0.04, 0.5, 0.01, 0.4, float(m.m), budget, electric, None, float(p.V_low),
                    "flight_model", notes, p.thrust, None)
        plant._eta_takeoff_missing = False
        plant.source_text = "flight_model"
        return plant


def _km_pair(v, what: str) -> tuple[float, float]:
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        raise ValueError(f"{what} deve ser [norte_km, este_km]")
    return float(v[0]) * 1000.0, float(v[1]) * 1000.0


class PointMassMission:
    def __init__(self, plant: Plant, mission: dict):
        self.plant = plant
        self.ms = mission
        dt = float(mission.get("pointmass_dt", 1.0))
        if dt < 1e-3:
            raise ValueError("pointmass_dt tem de ser ≥ 0.001 s (o dt do YAML é o passo 6-DOF)")
        self.dt = dt
        self.max_t = float(mission.get("max_time_s", 6 * 3600))
        self.wind_field = WindField.from_dict(mission.get("wind"))
        self.wind = self.wind_field.steady()
        self.notes = list(plant.notes)
        wspec = mission.get("wind") or {}
        if wspec.get("turbulence") or wspec.get("gusts"):
            self.notes.append("turbulência Dryden e rajadas 1−cos são do 6-DOF; a massa pontual usa só o "
                              "vento médio (Anderson 1999, soma de velocidades)")
        segs = mission["segments"]
        init = mission.get("initial") or {}
        if segs[0]["type"] == "takeoff":
            h0 = 0.0
        else:
            h0 = float(init.get("altitude_m", 300.0))
        hdg = math.radians(float(init.get("heading_deg", 0.0)))
        self.t = 0.0
        self.N = 0.0
        self.E = 0.0
        self.h = h0
        self.course = hdg
        self.psi = hdg
        self.Va = float(init["speed_m_s"]) if "speed_m_s" in init else 0.0
        self.Vg = self.Va
        self.gamma = 0.0
        self.n = 1.0
        self.throttle = 0.0
        self.W = plant.mass_kg * G0
        self.used = 0.0
        self.unusable = 0.0
        self.dist = 0.0
        self.engine_frac = 1.0
        self.engines_out = 0
        self.rate_factor = 1.0
        self.sensor_ok = True
        self.mode = "mission"          # mission | rtb | divert | glide
        self.target = (0.0, 0.0)
        self.then = "land"
        self.loiter_min = None
        self.aborted = None
        self.samples = []
        self.segs = []
        self.orbits = []
        self.failure_log = []
        self.events = resolve_failures(mission) if mission.get("failures") else []
        self.pending = list(self.events)
        self.sensor = mission.get("sensor")
        if self.sensor:
            validate_sensor(self.sensor)
        self.base = _km_pair(mission.get("base_km", [0.0, 0.0]), "base_km")
        self._seg = None
        self._idle_note = False
        self._speed_warn = False
        self._response_done = False

    # ---------------------------------------------------------------- bookkeeping
    def _abort(self, msg: str) -> None:
        if self.aborted is None:
            self.aborted = msg

    def _fuel_fraction(self):
        if self.plant.budget is None or self.plant.budget <= 0:
            return None
        return max(self.plant.budget - self.used, 0.0) / self.plant.budget

    def _check_events(self) -> None:
        if not self.pending:
            return
        name = self._seg["name"] if self._seg else ""
        typ = self._seg["type"] if self._seg else ""
        t_into = self.t - (self._seg["t0"] if self._seg else 0.0)
        fired = [e for e in self.pending if e.matches(self.t, name, typ, t_into, self.h, self._fuel_fraction())]
        for e in fired:
            self.pending.remove(e)
            self._apply_event(e)

    def _next_trigger(self):
        name = self._seg["name"] if self._seg else None
        typ = self._seg["type"] if self._seg else None
        t0 = self._seg["t0"] if self._seg else None
        times = [tt for e in self.pending if (tt := e.next_time(self.t, name, typ, t0)) is not None]
        return min(times) if times else None

    def _apply_event(self, e) -> None:
        action = "continua o perfil"
        if e.type == "engine_out":
            k = self.plant.n_engines if e.engines_out is None else int(e.engines_out)
            if k > self.plant.n_engines:
                raise ValueError(f"engines_out {k} > n_engines {self.plant.n_engines}")
            self.engines_out = k
            self.engine_frac = max(self.plant.n_engines - k, 0) / self.plant.n_engines
            action = f"{k} motor(es) em falha; fração viva {self.engine_frac:.2f}"
        elif e.type == "sensor_loss":
            self.sensor_ok = False
            action = "sensor desligado; a cobertura pára"
        elif e.type == "link_loss":
            action = "ligação perdida; forças e energia iguais"
        elif e.type in ("fuel_degradation", "battery_degradation"):
            self.rate_factor *= float(e.factor)
            action = f"consumo ×{e.factor:g} sobre a taxa de Anderson/Raymer (PRESSUPOSTO, não é envelhecimento)"
            if e.remaining_fraction is not None:
                self._shed(e.remaining_fraction)
                action += f"; fração utilizável restante {e.remaining_fraction:g} (massa inalterada)"
        if e.response == "rtb":
            self.mode = "rtb"
            self.target = self.base
            self.then = e.then
            self.loiter_min = e.loiter_min
            self._response_done = False
            action += "; regresso à base"
        elif e.response == "divert":
            self.mode = "divert"
            self.target = e.divert_km
            self.then = e.then
            self.loiter_min = e.loiter_min
            self._response_done = False
            action += "; desvio"
        elif e.response == "continue" and e.type == "engine_out" and self.engine_frac <= 1e-12:
            self.mode = "glide"
            self._response_done = False
            action += "; planado no rumo atual, perfil restante cancelado"
        elif self.mode != "mission" and e.response == "continue":
            action += "; o perfil já estava cancelado e não é retomado"
        self.failure_log.append({"t_s": self.t, "type": e.type, "response": e.response, "source": e.source,
                                 "fired": True, "action": action})

    def _shed(self, fraction: float) -> None:
        if self.plant.budget is None:
            self.notes.append("remaining_fraction sem orçamento: não aplicado")
            return
        remaining = max(self.plant.budget - self.used, 0.0)
        lost = remaining * (1.0 - fraction)
        self.plant.budget -= lost
        self.unusable += lost

    def _begin(self, seg: dict, typ: str | None = None, name: str | None = None) -> None:
        typ = typ or seg["type"]
        self._seg = {"name": name or seg.get("name", typ), "type": typ, "t0": self.t, "used0": self.used,
                     "h0": self.h, "dist0": self.dist, "V": 0.0, "notes": [], "on_station": bool(seg.get("on_station"))}
        self.segs.append(self._seg)

    def _end(self) -> None:
        s = self._seg
        if s is None:
            return
        s["t1"] = self.t
        s["used1"] = self.used
        s["h1"] = self.h
        s["dist"] = self.dist - s["dist0"]

    def _sample(self) -> None:
        s = self._seg
        typ = s["type"] if s else "initial"
        on_types = (self.sensor or {}).get("on_segments", SENSOR_ON_DEFAULT)
        stat_types = (self.sensor or {}).get("on_station_segments", ON_STATION_DEFAULT)
        sens = bool(self.sensor) and self.sensor_ok and typ in on_types
        on_stat = typ in stat_types or bool(s and s.get("on_station"))
        self.samples.append({
            "t": self.t, "N": self.N, "E": self.E, "h": self.h, "Va": self.Va, "Vg": self.Vg,
            "gamma_deg": math.degrees(self.gamma), "course_deg": math.degrees(self.course) % 360.0,
            "psi_deg": math.degrees(self.psi) % 360.0, "n": self.n, "throttle": self.throttle,
            "used": self.used, "m_kg": self.W / G0, "sensor_on": sens, "on_station": on_stat,
            "mode": self.mode, "segment": typ, "seg": len(self.segs) - 1,
        })

    def _burn(self, flow: float, dt: float) -> None:
        flow_eff = flow * self.rate_factor
        self.used += flow_eff * dt
        if not self.plant.electric:
            self.W = max(self.W - flow_eff * dt * G0, 1.0)
        if self.plant.budget is not None and self.used >= self.plant.budget - 1e-6:
            self.used = min(self.used, self.plant.budget)
            self._abort("combustível/energia esgotado")

    def _limit_dt(self, flow: float, *, responding: bool = False) -> float:
        self._check_events()
        if self.aborted:
            return 0.0
        if not responding and self.mode != "mission":
            return 0.0
        dt = self.dt
        nt = self._next_trigger()
        if nt is not None:
            dt = min(dt, max(nt - self.t, 0.0))
        flow_eff = max(flow, 0.0) * self.rate_factor
        if self.plant.budget is not None and flow_eff > 0:
            room = self.plant.budget - self.used
            if room <= 1e-9:
                self._abort("combustível/energia esgotado")
                return 0.0
            dt = min(dt, room / flow_eff)
        if self.t + dt > self.max_t:
            dt = self.max_t - self.t
            if dt <= 1e-12:
                self._abort("tempo máximo da missão excedido")
                return 0.0
        return max(dt, 0.0)

    def _commit(self, dt: float, Va: float, gamma: float, n: float, throttle: float, vN: float, vE: float,
                Vg: float, psi: float, course: float, flow: float) -> None:
        self._burn(flow, dt)
        self.t += dt
        self.N += vN * dt
        self.E += vE * dt
        self.dist += Vg * dt
        self.h = max(self.h, 0.0)
        self.Va, self.Vg, self.gamma, self.n = Va, Vg, gamma, n
        self.throttle, self.psi, self.course = throttle, psi, course
        if self._seg is not None:
            self._seg["V"] = Va
        self._sample()

    # ---------------------------------------------------------------- speeds
    def _default_speed(self, role: str) -> float:
        """Anderson Ch. 5, the same rules as sizing._legs. Floor 1.2 Vs only on a default (CS 23.65(a)).
        The 6-DOF runner instead reuses the previous target floored at 1.3 Vs."""
        pol = self.plant.polar()
        prop = is_propeller(self.plant.kind)
        if role in ("loiter", "patrol"):
            cl = pol.CL_min_power if prop else pol.CL_LDmax
        elif role == "glide":
            cl = pol.CL_LDmax
        else:
            cl = pol.CL_LDmax if prop else pol.CL_LDmax / math.sqrt(3.0)
        if cl > self.plant.CLmax:
            cl = 0.95 * self.plant.CLmax
            self.notes.append(f"CL de projeto {role} acima de CLmax; usa-se 0,95 CLmax")
        rho = isa(max(self.h, 0.0)).rho
        V = math.sqrt(2.0 * self.W / (rho * self.plant.S * cl))
        Vs = self.plant.stall(self.W, rho)
        if V < 1.2 * Vs:
            V = 1.2 * Vs
            self.notes.append(f"velocidade por omissão de {role} elevada a 1,2 V_S (CS 23.65(a))")
        return V

    def _speed(self, seg: dict, role: str):
        if "speed_m_s" not in seg:
            return self._default_speed(role)
        V = float(seg["speed_m_s"])
        rho = isa(max(self.h, 0.0)).rho
        Vs = self.plant.stall(self.W, rho)
        if V < Vs * 0.999:
            self._abort(f"velocidade {V:.2f} m/s abaixo de V_S {Vs:.2f} m/s")
            return None
        if V < 1.2 * Vs and not self._speed_warn:
            self.notes.append(f"V = {V:.1f} m/s < 1,2 V_S ({1.2 * Vs:.1f} m/s)")
            self._speed_warn = True
        return V

    def _vy(self) -> tuple[float, float]:
        rho = isa(max(self.h, 0.0)).rho
        Vs = self.plant.stall(self.W, rho)
        grid = np.linspace(1.2 * Vs, 4.0 * Vs, 40)
        rocs = [self.plant.roc(self.W, float(V), self.h, 1.0, self.engine_frac) for V in grid]
        i = int(np.argmax(rocs))
        return float(grid[i]), float(rocs[i])

    def _level(self, V: float, n: float):
        """Throttle that matches drag at load factor n. None if the thrust cannot hold level flight."""
        D, CL = self.plant.drag_cl(self.W, V, self.h, n)
        if CL > self.plant.CLmax * 1.001:
            self._abort(f"CL {CL:.2f} > CLmax {self.plant.CLmax:.2f}")
            return None
        got = self.plant.throttle_for(V, self.h, D, self.engine_frac)
        if got is None:
            self._abort("tração insuficiente para voo nivelado")
            return None
        thr, flow, _T, _idle = got
        return thr, flow, D, CL

    # ---------------------------------------------------------------- segments
    def _course_of(self, seg: dict) -> float:
        if "heading_deg" in seg:
            return math.radians(float(seg["heading_deg"]))
        return self.course

    def _fly_cruise(self, seg: dict, role: str = "cruise") -> None:
        self._begin(seg, role if role != "cruise" else seg["type"])
        if "distance_km" not in seg and "time_min" not in seg:
            raise ValueError(f"{role}: distance_km ou time_min")
        D = float(seg["distance_km"]) * 1000.0 if "distance_km" in seg else None
        T = float(seg["time_min"]) * 60.0 if "time_min" in seg else None
        course = self._course_of(seg)
        V = self._speed(seg, "loiter" if role in ("loiter", "patrol") else "cruise")
        n = 1.0
        if V is None:
            self._end()
            return
        d0, t0 = self.dist, self.t
        while self.aborted is None and self.mode == "mission":
            if D is not None and self.dist - d0 >= D - 1e-4:
                break
            if T is not None and self.t - t0 >= T - 1e-6:
                break
            hold = self._level(V, n)
            if hold is None:
                break
            thr, flow, _D, _CL = hold
            dt = self._limit_dt(flow)
            if dt <= 0:
                break
            tri = wind_triangle(V, 0.0, course, self.wind)
            if tri is None:
                self._abort("triângulo do vento sem solução (vento cruzado ou de cauda acima da velocidade)")
                break
            if D is not None:
                dt = min(dt, max(D - (self.dist - d0), 0.0) / tri["Vg"])
            if T is not None:
                dt = min(dt, max(T - (self.t - t0), 0.0))
            if dt <= 1e-12:
                break
            self._commit(dt, V, 0.0, n, thr, tri["vN"], tri["vE"], tri["Vg"], tri["psi"], course, flow)
            self._check_events()
        self._end()

    def _fly_climb(self, seg: dict) -> None:
        self._begin(seg)
        h_t = float(seg["to_altitude_m"])
        if self.h >= h_t - 1e-3:
            self._seg["notes"].append("já na altitude pedida")
            self._end()
            return
        fixed = "speed_m_s" in seg
        V = self._speed(seg, "cruise") if fixed else None
        if fixed and V is None:
            self._end()
            return
        course = self._course_of(seg)
        h_mark = self.h - 25.0
        while self.aborted is None and self.mode == "mission" and self.h < h_t - 1e-3:
            if not fixed and self.h - h_mark >= 25.0:
                V, _roc = self._vy()
                h_mark = self.h
            D, CL = self.plant.drag_cl(self.W, V, self.h, 1.0)
            if CL > self.plant.CLmax * 1.001:
                self._abort(f"CL {CL:.2f} > CLmax {self.plant.CLmax:.2f}")
                break
            _T, flow = self.plant.propulsion(V, self.h, 1.0, self.engine_frac)
            roc = self.plant.roc(self.W, V, self.h, 1.0, self.engine_frac)
            if roc <= 0.05:
                self._abort("subida sem excesso de potência")
                break
            gamma = math.asin(min(roc / V, 0.999))
            tri = wind_triangle(V, gamma, course, self.wind)
            if tri is None:
                self._abort("triângulo do vento sem solução (vento cruzado ou de cauda acima da velocidade)")
                break
            dt = self._limit_dt(flow)
            if dt <= 0:
                break
            dt = min(dt, (h_t - self.h) / roc)
            if not fixed:
                dt = min(dt, max(25.0 - (self.h - h_mark), 1e-6) / roc)
            self.h += roc * dt  # committed with the step; clamp just below overshoot
            if self.h > h_t:
                self.h = h_t
            self._commit(dt, V, gamma, 1.0, 1.0, tri["vN"], tri["vE"], tri["Vg"], tri["psi"], course, flow)
            self._check_events()
        self._end()

    def _fly_descent(self, seg: dict) -> None:
        self._begin(seg)
        h_t = float(seg["to_altitude_m"])
        if self.h <= h_t + 1e-3:
            self._seg["notes"].append("já na altitude pedida")
            self._end()
            return
        course = self._course_of(seg)
        commanded = "vertical_speed_m_s" in seg or "gamma_deg" in seg
        if not commanded:
            self._glide_down(h_t, course, None)
            self._end()
            return
        V = self._speed(seg, "cruise")
        if V is None:
            self._end()
            return
        if "gamma_deg" in seg:
            gamma = -abs(math.radians(float(seg["gamma_deg"])))
        else:
            vs = abs(float(seg["vertical_speed_m_s"]))
            if vs >= V:
                self._abort("velocidade vertical maior do que a velocidade")
                self._end()
                return
            gamma = -math.asin(vs / V)
        self._descend_gamma(h_t, course, V, gamma, seg)
        self._end()

    def _descend_gamma(self, h_t: float, course: float, V: float, gamma: float, seg: dict | None) -> None:
        """Kinematic descent. T = D + W sin γ (Anderson). Idle thrust above that demand keeps the path."""
        while self.aborted is None and self.mode == "mission" and self.h > h_t + 1e-3:
            D, CL = self.plant.drag_cl(self.W, V, self.h, 1.0)
            if CL > self.plant.CLmax * 1.001:
                self._abort(f"CL {CL:.2f} > CLmax {self.plant.CLmax:.2f}")
                break
            T_req = D + self.W * math.sin(gamma)
            got = self.plant.throttle_for(V, self.h, T_req, self.engine_frac)
            if got is None:
                self._abort("tração insuficiente para a rampa pedida")
                break
            thr, flow, _T, idle_floor = got
            if idle_floor and not self._idle_note:
                self.notes.append("ralenti produz mais tração do que a rampa pede; a trajetória mantém-se e "
                                  "queima-se o ralenti")
                self._idle_note = True
            vsink = -V * math.sin(gamma)  # positive down
            tri = wind_triangle(V, gamma, course, self.wind)
            if tri is None:
                self._abort("triângulo do vento sem solução (vento cruzado ou de cauda acima da velocidade)")
                break
            dt = self._limit_dt(flow)
            if dt <= 0:
                break
            dt = min(dt, (self.h - h_t) / max(vsink, 1e-6))
            self.h -= vsink * dt
            if self.h < h_t:
                self.h = h_t
            self._commit(dt, V, gamma, 1.0, thr, tri["vN"], tri["vE"], tri["Vg"], tri["psi"], course, flow)
            self._check_events()

    def _glide_state(self) -> tuple[float, float, float]:
        """(CL, L/D, γ) of the unpowered glide. γ = −arctan(1/(L/D)) so the still-air range is h·(L/D)
        even as V(ρ) changes, because each slice uses ds = dh · cot|γ| (Anderson 1999 Ch. 5)."""
        pol = self.plant.polar()
        cl = pol.CL_LDmax
        if cl > self.plant.CLmax:
            cl = 0.95 * self.plant.CLmax
            self.notes.append("CLmax < CL de (L/D)max; planeio a 0,95 CLmax")
        cd = self.plant.CD0 + self.plant.K * cl * cl
        if self.plant.camber is not None:
            cd = cd + float(self.plant.camber.dcd(cl))
        LD = cl / cd
        return cl, LD, -math.atan(1.0 / LD)

    def _glide_down(self, h_t: float, course: float, target) -> None:
        """Glide toward ``target`` (or on ``course`` when target is None) down to ``h_t``."""
        cl, LD, gamma = self._glide_state()
        while self.aborted is None and self.h > h_t + 1e-3:
            if target is not None and self.mode in ("rtb", "divert", "glide"):
                # a later event may retarget; engine-out glide does not resume the profile
                self._check_events()
                if self.aborted:
                    break
            rho = isa(max(self.h, 0.0)).rho
            V = math.sqrt(max(2.0 * self.W / (rho * self.plant.S * cl), 1e-6))
            if target is not None:
                dN, dE = target[0] - self.N, target[1] - self.E
                dist = math.hypot(dN, dE)
                if dist <= 1.0:
                    return
                course = math.atan2(dE, dN)
            Va_h = V * math.cos(gamma)
            # one slice, shortened to the integrator step and to the altitude left
            dh_max = self.h - h_t
            dt_full = (dh_max * LD) / max(Va_h, 1e-6)
            _T, flow = self.plant.propulsion(V, self.h, 0.0, self.engine_frac)
            responding = self.mode != "mission"
            dt = self._limit_dt(flow, responding=responding)
            if dt <= 0:
                break
            if dt_full > dt:
                dh = dh_max * dt / dt_full
            else:
                dh = dh_max
                dt = dt_full
            tri = wind_triangle(V, gamma, course, self.wind)
            if tri is None:
                self._abort("triângulo do vento sem solução (vento cruzado ou de cauda acima da velocidade)")
                break
            if target is not None:
                dist = math.hypot(target[0] - self.N, target[1] - self.E)
                if tri["Vg"] > 0 and dist / tri["Vg"] < dt:
                    scale = dist / (tri["Vg"] * dt)
                    dt *= scale
                    dh *= scale
                    if dt <= 1e-9:
                        return
            self.h -= dh
            if self.h < h_t:
                self.h = h_t
            self._commit(dt, V, gamma, 1.0, 0.0, tri["vN"], tri["vE"], tri["Vg"], tri["psi"], course, flow)
            if target is not None and math.hypot(target[0] - self.N, target[1] - self.E) <= 1.0:
                return
        if target is not None and self.h <= h_t + 1e-2:
            miss = math.hypot(target[0] - self.N, target[1] - self.E)
            if miss > 1.0:
                self.notes.append(f"planeio chegou ao solo a {miss:.0f} m do ponto")
                if self._seg is not None:
                    self._seg["notes"].append(f"falhou o ponto por {miss:.0f} m")

    def _fly_turn(self, seg: dict) -> None:
        """Air-heading change at Ω = g √(n²−1)/V (Anderson coordinated level turn). Ground track is the air
        vector plus the wind, so with zero wind the time is |Δψ|/Ω exactly."""
        self._begin(seg)
        if "heading_change_deg" not in seg:
            raise ValueError("turn: falta heading_change_deg")
        V = self._speed(seg, "cruise")
        if V is None:
            self._end()
            return
        dpsi = math.radians(float(seg["heading_change_deg"]))
        if "radius_m" in seg:
            R = float(seg["radius_m"])
            n = math.sqrt(1.0 + (V * V / (G0 * R)) ** 2)
        else:
            n = float(seg.get("load_factor", 1.2))
        if n < 1.0:
            raise ValueError("turn: load_factor tem de ser ≥ 1")
        hold = self._level(V, n)
        if hold is None:
            self._end()
            return
        thr, flow, _D, _CL = hold
        Omega = G0 * math.sqrt(n * n - 1.0) / V
        sign = 1.0 if dpsi >= 0 else -1.0
        remaining = abs(dpsi)
        while self.aborted is None and self.mode == "mission" and remaining > 1e-8:
            dt = self._limit_dt(flow)
            if dt <= 0:
                break
            dt = min(dt, remaining / Omega)
            step = sign * Omega * dt
            psi_mid = self.psi + 0.5 * step
            vN, vE, Vg = _air_plus_wind(V, 0.0, psi_mid, self.wind)
            self.psi = self.psi + step
            remaining -= abs(step)
            self._commit(dt, V, 0.0, n, thr, vN, vE, Vg, self.psi, math.atan2(vE, vN) if Vg > 1e-6 else self.psi,
                         flow)
            # refresh thrust in case weight or an event changed it; events at the end of _commit's caller
            self._check_events()
            if self.mode != "mission" or self.aborted:
                break
            hold = self._level(V, n)
            if hold is None:
                break
            thr, flow, _D, _CL = hold
        self.course = self.psi
        self._end()

    def _fly_loiter(self, seg: dict, role: str = "loiter") -> None:
        """Ground circle. Centre matches the 6-DOF orbit (right = +1). Radius from airspeed, so zero wind
        matches; the 6-DOF radius grows with wind. Stop on time, not on completed orbits."""
        self._begin(seg, role)
        if "time_min" not in seg:
            raise ValueError(f"{role}: falta time_min")
        V = self._speed(seg, "loiter")
        if V is None:
            self._end()
            return
        lam = 1.0 if seg.get("direction", "right") == "right" else -1.0
        if "radius_m" in seg:
            R = float(seg["radius_m"])
            n = math.sqrt(1.0 + (V * V / (G0 * R)) ** 2)
        else:
            n = float(seg.get("load_factor", 1.1))
            R = V * V / (G0 * math.sqrt(max(n * n - 1.0, 1e-9)))
        if n < 1.0 + 1e-6:
            raise ValueError(f"{role}: o fator de carga tem de ser > 1")
        chi = self.course
        cn = self.N + lam * R * math.cos(chi + math.pi / 2.0)
        cE = self.E + lam * R * math.sin(chi + math.pi / 2.0)
        alpha = chi - lam * math.pi / 2.0
        T = float(seg["time_min"]) * 60.0
        t0 = self.t
        turned = 0.0
        while self.aborted is None and self.mode == "mission" and self.t - t0 < T - 1e-6:
            motion_N = lam * (-math.sin(alpha))
            motion_E = lam * math.cos(alpha)
            course = math.atan2(motion_E, motion_N)
            hold = self._level(V, n)
            if hold is None:
                break
            thr, flow, _D, _CL = hold
            tri = wind_triangle(V, 0.0, course, self.wind)
            if tri is None:
                self._abort("triângulo do vento sem solução na órbita")
                break
            dt = self._limit_dt(flow)
            if dt <= 0:
                break
            dt = min(dt, T - (self.t - t0))
            dalpha = lam * (tri["Vg"] / R) * dt
            alpha += dalpha
            turned += abs(dalpha)
            self.N = cn + R * math.cos(alpha)
            self.E = cE + R * math.sin(alpha)
            # position set explicitly; commit would add v*dt on top, so advance time/fuel only
            self._burn(flow, dt)
            self.t += dt
            self.dist += tri["Vg"] * dt
            self.Va, self.Vg, self.gamma, self.n = V, tri["Vg"], 0.0, n
            self.throttle, self.psi, self.course = thr, tri["psi"], course
            self._seg["V"] = V
            self._sample()
            self._check_events()
        if self.sensor and turned > 0:
            sw = effective_swath(self.h, self.sensor)["swath_km"]
            self.orbits.append({"radius_m": R, "revolutions": turned / (2.0 * math.pi), "swath_km": sw})
        self._seg["notes"].append(f"raio de solo {R:.0f} m, {turned / (2 * math.pi):.2f} voltas")
        self._end()

    def _fly_waypoints(self, seg: dict) -> None:
        self._begin(seg)
        if "points_km" not in seg:
            raise ValueError("waypoints: falta points_km")
        V = self._speed(seg, "cruise")
        if V is None:
            self._end()
            return
        pts = [(float(p[0]) * 1000.0, float(p[1]) * 1000.0) for p in seg["points_km"]]
        for pN, pE in pts:
            while self.aborted is None and self.mode == "mission":
                dN, dE = pN - self.N, pE - self.E
                dist = math.hypot(dN, dE)
                if dist <= 1e-3:
                    break
                course = math.atan2(dE, dN)
                hold = self._level(V, 1.0)
                if hold is None:
                    break
                thr, flow, _D, _CL = hold
                tri = wind_triangle(V, 0.0, course, self.wind)
                if tri is None:
                    self._abort("triângulo do vento sem solução (vento cruzado ou de cauda acima da velocidade)")
                    break
                dt = self._limit_dt(flow)
                if dt <= 0:
                    break
                dt = min(dt, dist / tri["Vg"])
                self._commit(dt, V, 0.0, 1.0, thr, tri["vN"], tri["vE"], tri["Vg"], tri["psi"], course, flow)
                self._check_events()
            if self.aborted or self.mode != "mission":
                break
        self._end()

    def _ground_roll_time(self, KT: float, KA: float, V1: float, V2: float, n: int = 200) -> float:
        """Time of V̇ = g (K_T − K_A V²), the derivative of the Raymer 17.8 ground-roll integral."""
        if KT <= 0 and V2 > V1:
            return float("inf")
        t = 0.0
        V = V1
        step = (V2 - V1) / n
        for i in range(n):
            Vn = V1 + step * (i + 1)
            vd0 = G0 * (KT - KA * V * V)
            vd1 = G0 * (KT - KA * Vn * Vn)
            vd = 0.5 * (vd0 + vd1)
            if abs(vd) < 1e-8:
                return float("inf")
            t += (Vn - V) / vd
            V = Vn
        return t

    def _fly_takeoff(self, seg: dict) -> None:
        self._begin(seg)
        if self.plant._eta_takeoff_missing and is_propeller(self.plant.kind):
            raise ValueError("descolagem: falta eta_takeoff (não se aplica 0,80 por omissão)")
        self._seg["notes"].append("o flap do segmento não altera CLmax; usa-se CLmax_takeoff")
        self._seg["notes"].append("tempo da corrida por integração de V̇ = g(K_T − K_A V²); a distância é "
                                  "Raymer 17.8. Sem a fração de aquecimento da Tabela 3.2")
        m = self.plant.as_perf()
        if m.eta_takeoff is None:
            raise ValueError("descolagem: falta eta_takeoff")
        dist = takeoff_distance_integrated(m, self.W, max(self.h, 0.0))
        if not math.isfinite(dist["total_50ft"]):
            self._abort("descolagem sem excesso de tração")
            self._end()
            return
        rho = isa(max(self.h, 0.0)).rho
        Vs = m.stall(self.W, rho, m.CLmax_to)
        Vto = 1.1 * Vs
        if is_propeller(m.kind):
            T = m.power_avail(max(self.h, 0.0), m.eta_takeoff, None) / (0.7 * Vto)
        else:
            T = (m.T_sl or 0.0) * lapse(m.kind, isa(max(self.h, 0.0)).sigma)
        KT = T / self.W - m.mu_roll
        CD0 = m.CD0 + m.dCD0_to
        KA = rho / (2.0 * self.W / m.S) * (m.mu_roll * m.CL_ground - CD0 - m.K * m.CL_ground ** 2)
        t_roll = self._ground_roll_time(KT, KA, 0.0, Vto)
        Vtr = 1.15 * Vs
        g = math.radians(dist["gamma_climb_deg"])
        R = Vtr ** 2 / (0.2 * G0)
        h_tr = R * (1.0 - math.cos(g))
        if h_tr >= _SCREEN:
            g_p = math.acos(max(-1.0, min(1.0, 1.0 - _SCREEN / R)))
            t_tr, t_climb = R * g_p / Vtr, 0.0
        else:
            t_tr = R * g / Vtr
            t_climb = (_SCREEN - h_tr) / max(Vtr * math.sin(g), 1e-6)
        t_tot = t_roll + t_tr + t_climb
        _Troll, flow_roll = self.plant.propulsion(0.7 * Vto, self.h, 1.0, self.engine_frac)
        _Tc, flow_c = self.plant.propulsion(Vtr, self.h, 1.0, self.engine_frac)
        # one kinematic step: the distance is the Raymer total, not a wind triangle (17.8 has no wind)
        self._burn(flow_roll, t_roll)
        self._burn(flow_c, t_tr + t_climb)
        self.t += t_tot
        course = self.course
        self.N += dist["total_50ft"] * math.cos(course)
        self.E += dist["total_50ft"] * math.sin(course)
        self.dist += dist["total_50ft"]
        self.h = _SCREEN
        self.Va = Vtr
        self.Vg = Vtr
        self.n = 1.0
        self.throttle = 1.0
        self._seg["V"] = Vto
        self._sample()
        self._seg["notes"].append(f"total sobre 50 ft {dist['total_50ft']:.0f} m (Raymer 17.8)")
        self._end()

    def _fly_landing(self, seg: dict) -> None:
        self._begin(seg)
        self._seg["notes"].append("o flap do segmento não altera CLmax; usa-se CLmax_landing")
        self._seg["notes"].append("μ_brake = {:.2f} (PRESSUPOSTO)".format(self.plant.mu_brake)
                                  if "mu_brake" not in seg else "μ_brake do segmento")
        if self.h > _SCREEN + 0.5:
            self._seg["notes"].append("descida até ao ecrã de 50 ft incluída na aterragem")
            # reuse the descent kinematics down to the screen, still inside this segment
            saved_mode_check = self.mode
            course = self._course_of(seg)
            if "vertical_speed_m_s" in seg or "gamma_deg" in seg:
                V = self._speed(seg, "cruise") or self._default_speed("cruise")
                if "gamma_deg" in seg:
                    gamma = -abs(math.radians(float(seg["gamma_deg"])))
                else:
                    vs = abs(float(seg["vertical_speed_m_s"]))
                    gamma = -math.asin(min(vs / V, 0.999))
                self._descend_gamma(_SCREEN, course, V, gamma, seg)
            else:
                gamma = -math.radians(float(seg.get("glide_deg", 3.0)))
                V = self._speed(seg, "cruise") or self._default_speed("cruise")
                self._descend_gamma(_SCREEN, course, V, gamma, seg)
            if self.aborted or self.mode != saved_mode_check:
                self._end()
                return
        m = self.plant.as_perf()
        mu = float(seg.get("mu_brake", self.plant.mu_brake))
        gdeg = float(seg.get("glide_deg", 3.0))
        ld = landing_distance(m, self.W, 0.0, _SCREEN, mu, gdeg)
        rho = isa(0.0).rho
        Vs = m.stall(self.W, rho, m.CLmax_land)
        Vf, Vtd = 1.23 * Vs, 1.15 * Vs
        ga = math.radians(gdeg)
        t_app = ld["approach"] / max(Vf * math.cos(ga), 1e-3)
        t_flare = ld["flare"] / max(Vf, 1e-3)
        t_free = 3.0
        KT = -mu
        KA = rho / (2.0 * self.W / m.S) * (mu * m.CL_ground - (m.CD0 + m.dCD0_to) - m.K * m.CL_ground ** 2)
        t_brake = self._ground_roll_time(KT, KA, Vtd, 0.0)
        if not math.isfinite(t_brake):
            t_brake = ld["braking"] / max(0.5 * Vtd, 1e-3)
        t_tot = t_app + t_flare + t_free + t_brake
        _T, flow = self.plant.propulsion(max(Vf, 1.0), self.h, 0.0, self.engine_frac)
        self._burn(flow, t_tot)
        self.t += t_tot
        course = self.course
        self.N += ld["total_50ft"] * math.cos(course)
        self.E += ld["total_50ft"] * math.sin(course)
        self.dist += ld["total_50ft"]
        self.h = 0.0
        self.Va = 0.0
        self.Vg = 0.0
        self.throttle = 0.0
        self._seg["V"] = Vf
        self._sample()
        self._seg["notes"].append(f"total desde 50 ft {ld['total_50ft']:.0f} m (Raymer 17.9)")
        self._end()

    # ---------------------------------------------------------------- failure response
    def _spiral(self, target) -> None:
        """Descending spiral over the point until the ground. n ≈ 1.1, CL = n·CL_(L/D)max capped at
        0.95 CLmax, R = V²/(g √(n²−1)) (Anderson coordinated turn)."""
        n = 1.1
        pol = self.plant.polar()
        cl = min(n * pol.CL_LDmax, 0.95 * self.plant.CLmax)
        cd = self.plant.CD0 + self.plant.K * cl * cl
        LD = cl / max(cd, 1e-9)
        gamma = -math.atan(n / LD)  # sinγ ≈ −D/W with D = n W / (L/D) gives tan|γ| = n/(L/D)
        # Keep the textbook coordinated-turn radius at the 1 g best-glide speed (decision).
        rho = isa(max(self.h, 0.0)).rho
        cl1 = min(pol.CL_LDmax, 0.95 * self.plant.CLmax)
        V = math.sqrt(max(2.0 * self.W / (rho * self.plant.S * cl1), 1e-6))
        R = V * V / (G0 * math.sqrt(n * n - 1.0))
        # put the aircraft on the circle, along the current bearing from the target
        bear = math.atan2(self.E - target[1], self.N - target[0])
        self.N = target[0] + R * math.cos(bear)
        self.E = target[1] + R * math.sin(bear)
        if self._seg is not None:
            self._seg["notes"].append(f"espiral de descida, raio {R:.0f} m, n = 1,1")
        while self.aborted is None and self.h > 0.05:
            self._check_events()
            if self.aborted:
                break
            if self.mode in ("rtb", "divert") and self.target != target:
                return
            rho = isa(max(self.h, 0.0)).rho
            V = math.sqrt(max(2.0 * self.W / (rho * self.plant.S * cl1), 1e-6))
            R = V * V / (G0 * math.sqrt(n * n - 1.0))
            Omega = G0 * math.sqrt(n * n - 1.0) / V
            _T, flow = self.plant.propulsion(V, self.h, 0.0, self.engine_frac)
            vsink = V * math.sin(abs(gamma))
            dt = self._limit_dt(flow, responding=True)
            if dt <= 0:
                break
            dt = min(dt, self.h / max(vsink, 1e-6))
            bear += Omega * dt
            self.N = target[0] + R * math.cos(bear)
            self.E = target[1] + R * math.sin(bear)
            self.h -= vsink * dt
            if self.h < 0:
                self.h = 0.0
            self.psi = bear + math.pi / 2.0
            self.course = self.psi
            vN, vE, Vg = _air_plus_wind(V, gamma, self.psi, self.wind)
            self._burn(flow, dt)
            self.t += dt
            self.dist += Vg * dt
            self.Va, self.Vg, self.gamma, self.n = V, Vg, gamma, n
            self.throttle = 0.0
            if self._seg is not None:
                self._seg["V"] = V
            self._sample()
        self.h = 0.0

    def _powered_to(self, target) -> None:
        """Level cruise, then a descent that starts at Δh/tan|γ| (still air, PRESSUPOSTO mesmo com vento).
        Default γ = −3° when the thrust can hold it, otherwise the best glide."""
        V = self.Va if self.Va > 1.0 else self._default_speed("cruise")
        gamma = math.radians(-3.0)
        D, _CL = self.plant.drag_cl(self.W, V, max(self.h, 0.0), 1.0)
        T_req = D + self.W * math.sin(gamma)
        if self.plant.throttle_for(V, max(self.h, 1.0), T_req, self.engine_frac) is None:
            _cl, _LD, gamma = self._glide_state()
            self.notes.append("a rampa de −3° não cabe na tração; o regresso desce em (L/D)max")
        # cruise until the still-air switch
        while self.aborted is None and self.h > 1.0:
            self._check_events()
            if self.aborted:
                return
            if self.engine_frac <= 1e-12:
                self._glide_down(0.0, self.course, self.target)
                if self.h > 1.0 and math.hypot(self.target[0] - self.N, self.target[1] - self.E) <= 1.0:
                    self._spiral(self.target)
                return
            if self.mode in ("rtb", "divert"):
                target = self.target
            dist = math.hypot(target[0] - self.N, target[1] - self.E)
            switch = self.h / max(math.tan(abs(gamma)), 1e-6)
            if dist <= switch + 1.0:
                break
            course = math.atan2(target[1] - self.E, target[0] - self.N)
            hold = self._level(V, 1.0)
            if hold is None:
                self._glide_down(0.0, course, target)
                return
            thr, flow, _D, _CL = hold
            tri = wind_triangle(V, 0.0, course, self.wind)
            if tri is None:
                self._abort("triângulo do vento sem solução no regresso")
                return
            dt = self._limit_dt(flow, responding=True)
            if dt <= 0:
                return
            # stop on the switch radius (half-plane / one step), not a fixed capture radius
            gap = dist - switch
            dt = min(dt, max(gap, 0.0) / tri["Vg"])
            if dt <= 1e-9:
                break
            self._commit(dt, V, 0.0, 1.0, thr, tri["vN"], tri["vE"], tri["Vg"], tri["psi"], course, flow)
        self._descend_toward(target, V, gamma)

    def _descend_toward(self, target, V: float, gamma: float) -> None:
        while self.aborted is None and self.h > 0.05:
            self._check_events()
            if self.aborted:
                return
            if self.engine_frac <= 1e-12:
                self._glide_down(0.0, self.course, self.target)
                break
            target = self.target if self.mode in ("rtb", "divert") else target
            dist = math.hypot(target[0] - self.N, target[1] - self.E)
            if dist <= 1.0:
                break
            course = math.atan2(target[1] - self.E, target[0] - self.N)
            D, CL = self.plant.drag_cl(self.W, V, self.h, 1.0)
            if CL > self.plant.CLmax * 1.001:
                self._abort(f"CL {CL:.2f} > CLmax {self.plant.CLmax:.2f}")
                return
            got = self.plant.throttle_for(V, self.h, D + self.W * math.sin(gamma), self.engine_frac)
            if got is None:
                _c, _L, gamma = self._glide_state()
                got = self.plant.throttle_for(V, self.h, D + self.W * math.sin(gamma), self.engine_frac)
                if got is None:
                    thr, flow = 0.0, self.plant.propulsion(V, self.h, 0.0, self.engine_frac)[1]
                else:
                    thr, flow, _T, _idle = got
            else:
                thr, flow, _T, _idle = got
            tri = wind_triangle(V, gamma, course, self.wind)
            if tri is None:
                self._abort("triângulo do vento sem solução na descida de regresso")
                return
            vsink = -V * math.sin(gamma)
            dt = self._limit_dt(flow, responding=True)
            if dt <= 0:
                return
            dt = min(dt, self.h / max(vsink, 1e-6), dist / tri["Vg"])
            self.h -= vsink * dt
            if self.h < 0:
                self.h = 0.0
            self._commit(dt, V, gamma, 1.0, thr, tri["vN"], tri["vE"], tri["Vg"], tri["psi"], course, flow)
        if self.h > 1.0 and math.hypot(self.target[0] - self.N, self.target[1] - self.E) <= max(self.Vg, 1.0):
            self._spiral(self.target)
        elif self.h <= 0.05:
            self.h = 0.0
            miss = math.hypot(self.target[0] - self.N, self.target[1] - self.E)
            if miss > 1.0 and self._seg is not None:
                self._seg["notes"].append(f"falhou o ponto por {miss:.0f} m")
                self.notes.append(f"regresso chegou ao solo a {miss:.0f} m do ponto")

    def _fly_response(self) -> None:
        if self._response_done or self.aborted:
            return
        if self.mode == "glide":
            self._begin({}, "glide", "planeio")
            self._glide_down(0.0, self.course, None)
            self._end()
        elif self.mode in ("rtb", "divert"):
            label = "regresso" if self.mode == "rtb" else "desvio"
            self._begin({}, self.mode, label)
            if self.engine_frac <= 1e-12:
                self._glide_down(0.0, self.course, self.target)
                if self.h > 1.0:
                    self._spiral(self.target)
            else:
                self._powered_to(self.target)
            self._end()
            if (self.then == "loiter" and self.loiter_min and self.h > 1.0 and self.aborted is None
                    and math.hypot(self.target[0] - self.N, self.target[1] - self.E) < 5000.0):
                self.mode = "mission"  # the loiter is the instructed hold, not a return of the old profile
                self._fly_loiter({"type": "loiter", "time_min": self.loiter_min, "load_factor": 1.1}, "loiter")
                self.mode = "divert" if label == "desvio" else "rtb"
        self._response_done = True

    def _dispatch(self, seg: dict) -> None:
        typ = seg["type"]
        if typ == "takeoff":
            self._fly_takeoff(seg)
        elif typ == "climb":
            self._fly_climb(seg)
        elif typ == "cruise":
            self._fly_cruise(seg, "cruise")
        elif typ == "turn":
            self._fly_turn(seg)
        elif typ == "waypoints":
            self._fly_waypoints(seg)
        elif typ in ("loiter", "patrol"):
            self._fly_loiter(seg, typ)
        elif typ == "descent":
            self._fly_descent(seg)
        elif typ == "landing":
            self._fly_landing(seg)
        else:
            raise ValueError(f"segmento desconhecido {typ!r}")

    def run(self) -> dict:
        self._sample()  # t = 0, so the track starts at the origin
        for seg in self.ms["segments"]:
            if self.aborted or self.mode != "mission":
                break
            self._dispatch(seg)
            if self.mode != "mission":
                break
        if self.mode != "mission" and self.aborted is None:
            self._fly_response()
        return self.results()

    def results(self) -> dict:
        unit = "Wh" if self.plant.electric else "kg"
        fac = 1.0 / 3600.0 if self.plant.electric else 1.0
        rows = []
        for s in self.segs:
            row = {"segment": s["name"], "type": s["type"], "t_min": (s.get("t1", self.t) - s["t0"]) / 60.0,
                   "dist_km": s.get("dist", 0.0) / 1000.0, f"used_{unit}": (s.get("used1", self.used) - s["used0"]) * fac,
                   "h0_m": s["h0"], "h1_m": s.get("h1", self.h), "V_target_m_s": s["V"], "notes": s["notes"]}
            rows.append(row)
        t_on = 0.0
        for a, b in zip(self.samples, self.samples[1:]):
            if b.get("on_station"):
                t_on += max(b["t"] - a["t"], 0.0)
        sensor_out = None
        if self.sensor:
            sensor_out = evaluate_sensors(self.samples, self.sensor, total_time_s=self.t, orbits=self.orbits or None)
        failures = None
        if self.ms.get("failures"):
            failures = {"events": [e.to_dict() for e in self.events], "log": self.failure_log, "executed": True,
                        "seed": self.ms["failures"].get("seed"),
                        "note": "resposta voada na massa pontual; no 6-DOF a mesma falha só é registada"}
        out = {"name": self.ms.get("name", "missão"), "fidelity": "pointmass", "method": METHOD,
               "validity": VALIDITY, "segments": rows, "total_time_min": self.t / 60.0,
               "total_dist_km": self.dist / 1000.0, f"total_used_{unit}": self.used * fac, "unit": unit,
               "unusable": self.unusable * fac, "aborted": self.aborted, "notes": self.notes,
               "aircraft_source": self.plant.source, "history_columns": list(_COLS),
               "metrics": _metrics_block(sensor_out, self.t, self.dist, t_on)}
        if sensor_out is not None:
            out["sensor"] = sensor_out
        if failures is not None:
            out["failures"] = failures
        out["_samples"] = self.samples
        return out


_COLS = ["t", "N", "E", "h", "Va", "Vg", "gamma_deg", "course_deg", "psi_deg", "n", "throttle", "used", "m_kg",
         "sensor_on", "mode", "seg"]


def plot_pointmass(result: dict, out_dir: Path, title: str = "") -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    S = result.get("_samples") or []
    files = {}
    if len(S) < 2:
        return files
    t = [s["t"] / 60.0 for s in S]
    seg = [s["seg"] for s in S]
    names = [r["segment"] for r in result["segments"]]
    cmap = plt.get_cmap("tab10")
    fig, ax = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    panels = [(ax[0, 0], "h", "h [m]"), (ax[0, 1], "Va", "V_a [m/s]"),
              (ax[1, 0], "throttle", "manete [-]"), (ax[1, 1], "used", "consumo")]
    for a, key, lab in panels:
        for i in sorted(set(seg)):
            xs = [tt for tt, ss in zip(t, seg) if ss == i]
            ys = [s[key] for s, ss in zip(S, seg) if ss == i]
            a.plot(xs, ys, color=cmap((i if i >= 0 else 0) % 10), lw=1.2,
                   label=names[i] if 0 <= i < len(names) else "")
        a.set_ylabel(lab)
        a.grid(alpha=0.3)
    ax[0, 0].legend(fontsize=7, ncol=2)
    ax[1, 0].set_xlabel("t [min]")
    ax[1, 1].set_xlabel("t [min]")
    fig.suptitle(f"Missão massa pontual — {title}")
    fig.tight_layout()
    p = out_dir / "mission_time_history.png"
    fig.savefig(p, dpi=100)
    plt.close(fig)
    files["time_history"] = str(p)
    fig, a = plt.subplots(figsize=(8, 7))
    for i in sorted(set(seg)):
        xs = [s["E"] / 1e3 for s, ss in zip(S, seg) if ss == i]
        ys = [s["N"] / 1e3 for s, ss in zip(S, seg) if ss == i]
        a.plot(xs, ys, color=cmap((i if i >= 0 else 0) % 10), label=names[i] if 0 <= i < len(names) else "")
    a.set_aspect("equal", "datalim")
    a.set_xlabel("E [km]")
    a.set_ylabel("N [km]")
    a.grid(alpha=0.3)
    a.legend(fontsize=8)
    a.set_title("Traço no solo — massa pontual")
    p = out_dir / "mission_ground_track.png"
    fig.savefig(p, dpi=100)
    plt.close(fig)
    files["ground_track"] = str(p)
    return files


def _write_outputs(result: dict, out_dir) -> dict:
    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    samples = result.get("_samples") or []
    with open(od / "mission_history.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(_COLS)
        for s in samples:
            w.writerow([s["t"], s["N"], s["E"], s["h"], s["Va"], s["Vg"], s["gamma_deg"], s["course_deg"],
                        s["psi_deg"], s["n"], s["throttle"], s["used"], s["m_kg"], int(s["sensor_on"]),
                        s["mode"], s["seg"]])
    files = plot_pointmass(result, od, result.get("name", ""))
    files["history_csv"] = str(od / "mission_history.csv")
    summ = {k: v for k, v in result.items() if k != "_samples"}
    (od / "mission_summary.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False, default=_js),
                                             encoding="utf-8")
    files["summary_json"] = str(od / "mission_summary.json")
    return files


def _js(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def simulate_pointmass_mission(src, out_dir=None, res=None, fm=None) -> dict:
    """Run one YAML mission in point-mass fidelity.

    ``fm`` (flight model) wins over ``res`` (sizing), which wins over the ``aircraft`` block. Schema errors
    raise ``ValueError``. An in-flight limit sets ``aborted`` and returns the partial mission.
    """
    import copy
    raw = copy.deepcopy(src) if isinstance(src, dict) else src
    ms = load_mission(raw)
    if fm is not None:
        plant = Plant.from_flight_model(fm)
        if ms.get("aircraft"):
            plant.notes.append("bloco aircraft ignorado: usa-se o modelo de voo")
    elif res is not None:
        plant = Plant.from_sizing(res)
        if ms.get("aircraft"):
            plant.notes.append("bloco aircraft ignorado: o dimensionamento ganha")
    elif ms.get("aircraft"):
        plant = Plant.from_n0(ms["aircraft"])
    else:
        raise ValueError("massa pontual: falta o bloco aircraft, o resultado de dimensionamento ou o modelo de voo")
    sim = PointMassMission(plant, ms)
    result = sim.run()
    if out_dir is not None:
        result["files"] = _write_outputs(result, out_dir)
    result.pop("_samples", None)
    return result
