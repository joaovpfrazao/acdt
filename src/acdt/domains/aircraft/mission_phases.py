# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Common operational mission phases: how each native fleet adapter represents them.

Canonical phases taxi_out, takeoff, climb, transit_out, station, transit_back, descent,
landing, taxi_in, reserve. Representation states:

* ``flown`` — integrated by the native model (pointmass, Breguet, VTOL segment, hybrid dispatch);
* ``allowance`` — native fraction/energy allowance booked by sizing, not flown as a trajectory
  (Raymer 2018 Table 3.2 fractions, electric take-off+climb energy);
* ``lumped:<phase>`` — inside another phase's allowance/segment (not separable);
* ``supplied_duration`` — explicit supplied time without a power model;
* ``not_applicable`` — phase does not exist for the vehicle (VTOL taxi);
* ``not_modeled`` — absent; a REQUIRED not_modeled phase is unassessed, never a pass.

This is a consistent coverage contract over the EXISTING adapters, not a new trajectory model.
"""
CANONICAL = ("taxi_out", "takeoff", "climb", "transit_out", "station", "transit_back", "descent", "landing", "taxi_in", "reserve")
REPRESENTED = ("flown", "allowance", "supplied_duration", "not_applicable")


def coverage(model, kind=None, reserve_policy=None, hybrid=None, jet_durations=False):
    """kind: electric|prop for model prop. hybrid: the hybrid spec (phases supplied)."""
    t = {}
    if model == "prop" and kind == "electric":
        t = dict(taxi_out=("not_modeled", ""), takeoff=("allowance", "native take-off energy (performance.takeoff_climb_energy), held"),
                 climb=("allowance", "native climb energy (performance.takeoff_climb_energy), held"),
                 descent=("not_modeled", "pointmass level legs only"), landing=("not_modeled", ""), taxi_in=("not_modeled", ""))
    elif model == "prop":
        t = dict(taxi_out=("lumped:takeoff", "Raymer 2018 Table 3.2 warm-up+take-off fraction"),
                 takeoff=("allowance", "Raymer 2018 Table 3.2 warm-up+take-off fraction, held"),
                 climb=("allowance", "Raymer 2018 Table 3.2 climb fraction, held"),
                 descent=("lumped:landing", "Raymer 2018 Table 3.2 landing fraction (descent not separate)"),
                 landing=("allowance", "Raymer 2018 Table 3.2 landing fraction, held"), taxi_in=("lumped:landing", "Raymer landing fraction"))
    elif model == "jet":
        t = dict(taxi_out=("lumped:takeoff", "Raymer 2018 Table 3.2 warm-up+take-off fraction" + ("; supplied precruise time" if jet_durations else "")),
                 takeoff=("allowance", "Raymer 2018 Table 3.2 warm-up+take-off fraction"),
                 climb=("allowance", "Raymer 2018 Table 3.2 climb fraction (fuel); time from supplied precruise duration"),
                 descent=("lumped:landing", "Raymer 2018 Table 3.2 landing fraction; time from supplied postcruise duration"),
                 landing=("allowance", "Raymer 2018 Table 3.2 landing fraction"), taxi_in=("lumped:landing", "Raymer landing fraction"))
    elif model == "vtol":
        t = dict(taxi_out=("not_applicable", "vertical take-off"), takeoff=("flown", "hover segment (t_hover_s covers take-off and landing hover)"),
                 climb=("flown", "vertical climb segment + transition"), descent=("not_modeled", "no descent segment"),
                 landing=("lumped:takeoff", "hover segment total"), taxi_in=("not_applicable", "vertical landing"))
    elif model == "hybrid" and hybrid is not None:
        ph = hybrid.get("phases", {})
        for k in ("taxi_out", "takeoff", "climb", "descent", "landing", "taxi_in"):
            t[k] = ("flown", "hybrid dispatch, supplied phase input") if k in ph else ("not_modeled", "phase not supplied")
    else:
        return dict(model=model, phases={k: dict(state="not_modeled", method="no native adapter") for k in CANONICAL})
    flown = {"prop": "existing pointmass level leg", "jet": "differential Breguet cruise", "vtol": "native cruise/loiter segment",
             "hybrid": "hybrid rule-based dispatch, level power"}[model]
    for k in ("transit_out", "station", "transit_back"):
        t[k] = ("flown", flown)
    t["reserve"] = ("flown", "explicit operational reserve in sizing/capability mission") if reserve_policy == "explicit_operational_reserve_replaces_native_fraction" \
        else (("allowance", "native reserve fraction / DoD") if model in ("prop", "jet", "vtol") else ("not_modeled", "only SOC/fuel capacity limits"))
    return dict(model=model, phases={k: dict(state=t[k][0], method=t[k][1]) for k in CANONICAL},
                contract="coverage of existing adapters; lumped/allowance phases are not trajectories")


def required_check(cov, required):
    miss = [p for p in required if not (cov["phases"][p]["state"] in REPRESENTED or cov["phases"][p]["state"].startswith("lumped:"))]
    return dict(name="required_phases_represented", passed=None if miss else True, unrepresented=miss, required=list(required))
