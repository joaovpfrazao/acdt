"""Mission / operations geometry: transit, sweep rate, revisit, persistent presence and availability.

* Transit time with a steady along-track wind: t = d/(V − w) outbound, d/(V + w) back (kinematics, ground speed = V ± w).
* Sweep rate (search effort per unit time) Q = W·V and the time to sweep an area once, A/(W·V)
  (Koopman, B. O. (1946/1980), "Search and Screening", OEG Report 56 / Pergamon 1980; Washburn, A. R.
  (2002), "Search and Detection", 4th ed., INFORMS).
* Continuous coverage of one station by identical aircraft in a cyclic schedule: an aircraft spends T_L on
  station and T_rt = transit out + transit back + ground turnaround off station; the minimum number for
  no-gap coverage is N = ⌈(T_L + T_rt)/T_L⌉ = ⌈1 + T_rt/T_L⌉ and the on-station duty cycle of one aircraft is
  T_L/(T_L + T_rt) — Ha, T. (2010), "The UAV Continuous Coverage Problem", MSc thesis AFIT-OR-MS-ENS-10-03,
  Air Force Institute of Technology (DTIC ADA517241), deterministic identical-UAV model.
* Inherent availability A_i = MTBF/(MTBF + MTTR); operational availability A_o = MTBM/(MTBM + MDT) —
  Blanchard, B. S. & Fabrycky, W. J. (2011), "Systems Engineering and Analysis", 5th ed., Prentice Hall
  (availability measures); MIL-HDBK-338B (1998), §5 (availability).

Validity: steady flight at the given true airspeed, steady wind along track (cross-wind ignored), no
weather/airspace interruptions, deterministic cyclic schedule (the stochastic effect is handled through
availability and the k-of-N fleet reliability in :mod:`acdt.core.concept.reliability`).
"""
from __future__ import annotations

import math

REF_SWEEP = "Koopman 1946 'Search and Screening'; Washburn 2002 'Search and Detection'"
REF_CYCLE = "Ha 2010, 'The UAV Continuous Coverage Problem', AFIT-OR-MS-ENS-10-03 (DTIC ADA517241)"
REF_AVAIL = "Blanchard & Fabrycky 2011 'Systems Engineering and Analysis' 5th ed.; MIL-HDBK-338B §5"


def transit(distance_km: float, airspeed_m_s: float, headwind_m_s: float = 0.0) -> dict:
    """Outbound (into ``headwind``) and return transit times [h] and the round trip."""
    V, w = float(airspeed_m_s), float(headwind_m_s)
    if V <= abs(w):
        raise ValueError("airspeed must exceed the wind speed")
    d = float(distance_km) * 1000.0
    t_out, t_back = d / (V - w) / 3600.0, d / (V + w) / 3600.0
    return {"t_out_h": t_out, "t_back_h": t_back, "t_round_trip_h": t_out + t_back}


def sweep(area_km2: float, sweep_width_km: float, speed_m_s: float, n_on_station: float = 1.0) -> dict:
    """Sweep rate Q = n·W·V [km²/h] and the time to sweep the area once [h] (≈ revisit interval of an
    exhaustive parallel-track patrol)."""
    Q = float(n_on_station) * float(sweep_width_km) * float(speed_m_s) * 3.6
    if Q <= 0:
        raise ValueError("sweep width, speed and n_on_station must be > 0")
    return {"sweep_rate_km2_h": Q, "time_to_sweep_area_h": float(area_km2) / Q}


def cycle(endurance_h: float, t_out_h: float, t_back_h: float, turnaround_h: float, reserve_h: float = 0.0,
          handoff_overlap_h: float = 0.0) -> dict:
    """Cyclic schedule of one station (Ha 2010): time on station per sortie, round trip off station, aircraft
    needed for no-gap coverage and the on-station duty cycle of one aircraft."""
    T_L = float(endurance_h) - float(t_out_h) - float(t_back_h) - float(reserve_h)
    T_rt = float(t_out_h) + float(t_back_h) + float(turnaround_h)
    if T_L <= 0:
        return {"time_on_station_h": T_L, "round_trip_h": T_rt, "feasible": False,
                "reason": "endurance does not cover the transit + reserve: no time on station"}
    T_eff = T_L - float(handoff_overlap_h)
    if T_eff <= 0:
        return {"time_on_station_h": T_L, "round_trip_h": T_rt, "feasible": False,
                "reason": "hand-off overlap exceeds the time on station"}
    n = math.ceil((T_eff + T_rt) / T_eff - 1e-12)
    return {"time_on_station_h": T_L, "effective_time_on_station_h": T_eff, "round_trip_h": T_rt,
            "aircraft_per_station": n, "duty_cycle": T_eff / (T_eff + T_rt), "feasible": True}


def availability(mtbf_h: float | None = None, mttr_h: float | None = None, mtbm_h: float | None = None,
                 mdt_h: float | None = None) -> dict:
    """Inherent (MTBF, MTTR) and/or operational (MTBM, MDT) availability (Blanchard & Fabrycky 2011)."""
    out = {}
    if mtbf_h is not None and mttr_h is not None:
        out["inherent"] = float(mtbf_h) / (float(mtbf_h) + float(mttr_h))
    if mtbm_h is not None and mdt_h is not None:
        out["operational"] = float(mtbm_h) / (float(mtbm_h) + float(mdt_h))
    if not out:
        raise ValueError("give (mtbf_h, mttr_h) and/or (mtbm_h, mdt_h)")
    return out


def presence(n_aircraft: int, availability: float, cycle_result: dict) -> dict:
    """Average aircraft on station of a fleet = N·A·duty cycle (expected value), and the number of stations
    that N·A available aircraft can hold without gaps (⌊N·A / aircraft_per_station⌋, deterministic)."""
    if not cycle_result.get("feasible"):
        return {"mean_on_station": 0.0, "continuous_stations_expected": 0, "feasible": False}
    nA = int(n_aircraft) * float(availability)
    return {"mean_on_station": nA * cycle_result["duty_cycle"],
            "continuous_stations_expected": int(math.floor(nA / cycle_result["aircraft_per_station"] + 1e-9)),
            "available_aircraft_expected": nA, "feasible": True}
