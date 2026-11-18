"""Search and detection primitives: Koopman search laws, radar/optical horizon, sensor footprint, Johnson criteria.

* Random search: P = 1 − exp(−W·L/A), L = V·t — Koopman, B. O. (1946/1980), "Search and Screening", OEG
  Report 56 (Pergamon 1980); Washburn, A. R. (2002), "Search and Detection", 4th ed., INFORMS.
  Conservative for systematic search; covers target motion that is random relative to the searcher.
* Definite-range ("cookie-cutter") exhaustive parallel sweep with track spacing S = W: P = min(1, W·L/A)
  (Koopman 1980; Washburn 2002) — the upper bound of a systematic search.
* Effort for a target probability with random search: W·L = −A·ln(1 − P).
* Horizon to a target at height h_t from a sensor at h_s: d = √(2kR)(√h_s + √h_t); k = 4/3 for the standard
  radar atmosphere (Skolnik, M. I. (2001), "Introduction to Radar Systems", 3rd ed., McGraw-Hill, Sec. 8.2
  "propagation — refraction, 4/3 earth"); k = 1 gives the geometric horizon. 4/3-earth: d[km] ≈ 4.12 √h[m].
* Flat-earth sensor footprint: nadir swath 2h·tan(FOV/2); oblique view with depression angle θ and vertical
  FOV β: ground ranges h/tan(θ ± β/2) (elementary trigonometry; valid for h ≪ R_E and ranges ≪ horizon).
* Johnson criteria (cycles across the target critical dimension for 50 % probability): detection 1.0,
  orientation 1.4, recognition 4.0, identification 6.4 — Johnson, J. (1958), "Analysis of image forming
  systems", Image Intensifier Symposium, Fort Belvoir; pixels = 2 × cycles (Nyquist). Max slant range
  R = d_c / (2·N_cycles·IFOV).

* Barrier / barrier-patrol search: an evader must cross a line or corridor of length L. With searcher speed V,
  sweep width W and n searchers on station, the Koopman barrier coverage factor is
  z = n·W·V / (L·u) (V, u in consistent length/time). Random-search POD = 1 − exp(−z); definite-range
  (cookie-cutter) POD = min(1, z) — Koopman 1946/1980; Washburn 2002. A reciprocating patrol revisits a point
  on the barrier every τ = 2L/(n·V); the barrier is closed against a crossing window T when τ ≤ T
  (cookie-cutter revisit). Missing W, V or endurance when a metric needs them → that metric is
  **unassessed** (never a silent pass); unknown ≠ zero.

Validity: these give detection opportunity, not the sensor's probability of detection in clutter/sea state —
use the manufacturer's published detection range / swath for the target class (researched, with source).
"""
from __future__ import annotations

import math

R_EARTH_M = 6371008.8
REF_KOOPMAN = "Koopman 1946/1980 'Search and Screening'; Washburn 2002 'Search and Detection'"
REF_HORIZON = "Skolnik 2001 'Introduction to Radar Systems' 3rd ed. Sec. 8.2 (4/3-earth refraction)"
REF_JOHNSON = "Johnson 1958 'Analysis of image forming systems' (Image Intensifier Symposium)"
JOHNSON_CYCLES = {"detection": 1.0, "orientation": 1.4, "recognition": 4.0, "identification": 6.4}


def pod(area_km2: float, sweep_width_km: float, track_length_km: float) -> dict:
    """Probability of detection after a track length L in area A (random-search and definite-range laws)."""
    c = float(sweep_width_km) * float(track_length_km) / float(area_km2)
    return {"coverage_factor": c, "pod_random_search": 1.0 - math.exp(-c), "pod_parallel_sweep": min(1.0, c)}


def effort_for_pod(area_km2: float, pod_target: float) -> dict:
    """Search effort W·L [km²] for a target POD: random search −A ln(1−P); exhaustive sweep A·P."""
    p = float(pod_target)
    if not 0.0 < p < 1.0:
        raise ValueError("pod_target must be in (0, 1)")
    return {"effort_random_km2": -float(area_km2) * math.log(1.0 - p), "effort_parallel_km2": float(area_km2) * p}


def horizon_km(h_sensor_m: float, h_target_m: float = 0.0, k: float = 4.0 / 3.0) -> dict:
    """Line-of-sight horizon [km] (k = 4/3 radar, 1 geometric) — Skolnik 2001."""
    a = math.sqrt(2.0 * k * R_EARTH_M)
    d = a * (math.sqrt(max(h_sensor_m, 0.0)) + math.sqrt(max(h_target_m, 0.0))) / 1000.0
    return {"horizon_km": d, "k": k}


def footprint(altitude_m: float, fov_cross_deg: float, fov_along_deg: float | None = None,
              depression_deg: float = 90.0) -> dict:
    """Flat-earth ground footprint of a sensor at ``altitude_m``: nadir (depression 90°) or oblique."""
    h = float(altitude_m)
    if depression_deg >= 89.999:
        w = 2.0 * h * math.tan(math.radians(fov_cross_deg) / 2.0)
        out = {"swath_km": w / 1000.0, "near_range_km": 0.0, "far_range_km": 0.0}
        if fov_along_deg is not None:
            out["along_km"] = 2.0 * h * math.tan(math.radians(fov_along_deg) / 2.0) / 1000.0
        return out
    th, b = math.radians(depression_deg), math.radians(fov_along_deg if fov_along_deg is not None else fov_cross_deg)
    lo = th - b / 2.0
    near = h / math.tan(th + b / 2.0)
    far = float("inf") if lo <= 0 else h / math.tan(lo)
    slant_far = math.hypot(far, h) if math.isfinite(far) else float("inf")
    w_far = 2.0 * slant_far * math.tan(math.radians(fov_cross_deg) / 2.0) if math.isfinite(slant_far) else float("inf")
    return {"near_range_km": near / 1000.0, "far_range_km": far / 1000.0,
            "swath_far_km": w_far / 1000.0, "slant_range_far_km": slant_far / 1000.0}


def johnson_range(target_dim_m: float, task: str = "detection", ifov_rad: float | None = None,
                  pixel_pitch_um: float | None = None, focal_mm: float | None = None,
                  fov_deg: float | None = None, pixels: int | None = None) -> dict:
    """Max slant range [km] for a Johnson task (detection/orientation/recognition/identification) given the
    IFOV (or pixel pitch + focal length, or FOV + pixel count)."""
    if task not in JOHNSON_CYCLES:
        raise ValueError(f"task: {', '.join(JOHNSON_CYCLES)}")
    if ifov_rad is None:
        if pixel_pitch_um and focal_mm:
            ifov_rad = pixel_pitch_um * 1e-6 / (focal_mm * 1e-3)
        elif fov_deg and pixels:
            ifov_rad = math.radians(fov_deg) / int(pixels)
        else:
            raise ValueError("give ifov_rad, (pixel_pitch_um, focal_mm) or (fov_deg, pixels)")
    n = JOHNSON_CYCLES[task]
    R = float(target_dim_m) / (2.0 * n * ifov_rad)
    return {"task": task, "cycles": n, "pixels_on_target": 2 * n, "ifov_rad": ifov_rad, "max_range_km": R / 1000.0}


REF_BARRIER = ("Koopman 1946/1980 'Search and Screening' (barrier patrol); "
               "Washburn 2002 'Search and Detection' 4th ed. (barrier patrols)")


def barrier_coverage_factor(barrier_length_km: float, sweep_width_km: float, searcher_speed_m_s: float,
                            evader_speed_m_s: float, n_on_station: float = 1.0) -> dict:
    """Koopman barrier coverage factor z = n·W·V/(L·u) and POD (random / definite-range).

    Speeds are converted to km/h. ``sweep_width_km`` is the *effective* sweep width for the target class
    (datasheet / sourced); do not invent a radar's W.
    """
    L = float(barrier_length_km)
    W = float(sweep_width_km)
    V = float(searcher_speed_m_s) * 3.6
    u = float(evader_speed_m_s) * 3.6
    n = float(n_on_station)
    if L <= 0 or W <= 0 or V <= 0 or u <= 0 or n <= 0:
        raise ValueError("barrier_length, sweep_width, speeds and n_on_station must be > 0")
    z = n * W * V / (L * u)
    return {
        "coverage_factor": z,
        "pod_random_search": 1.0 - math.exp(-z),
        "pod_parallel_sweep": min(1.0, z),
        "searcher_speed_km_h": V,
        "evader_speed_km_h": u,
        "method": REF_BARRIER,
    }


def barrier_revisit(barrier_length_km: float, searcher_speed_m_s: float, n_on_station: float = 1.0) -> dict:
    """Reciprocating barrier patrol revisit: τ = 2L/(n·V) [h] (round-trip along the line).

    Cookie-cutter 'closed' checks compare τ to a crossing window (corridor width / evader speed, or a
    supplied detection window). Speed must be supplied — no silent default.
    """
    L = float(barrier_length_km)
    V = float(searcher_speed_m_s) * 3.6
    n = float(n_on_station)
    if L <= 0 or V <= 0 or n <= 0:
        raise ValueError("barrier_length, searcher speed and n_on_station must be > 0")
    tau = 2.0 * L / (n * V)
    return {
        "revisit_h": tau,
        "patrol_leg_h": L / (n * V),
        "searcher_speed_km_h": V,
        "n_on_station": n,
        "method": REF_BARRIER,
        "validity": "reciprocating back-and-forth along a straight barrier; no turn time, no weather",
    }


def barrier_close(barrier_length_km: float, searcher_speed_m_s: float, crossing_window_h: float,
                  n_on_station: float = 1.0) -> dict:
    """Whether a reciprocating patrol closes the barrier (τ ≤ T) and the fleet/length extremes.

    * ``closed`` — cookie-cutter: revisit ≤ crossing window
    * ``n_to_close`` — min n on station with τ ≤ T
    * ``L_max_km`` — longest barrier one set of n searchers closes at this speed and T
    """
    T = float(crossing_window_h)
    if T <= 0:
        raise ValueError("crossing_window_h must be > 0")
    rev = barrier_revisit(barrier_length_km, searcher_speed_m_s, n_on_station)
    V = rev["searcher_speed_km_h"]
    L = float(barrier_length_km)
    n = float(n_on_station)
    n_need = math.ceil(2.0 * L / (V * T) - 1e-12)
    L_max = n * V * T / 2.0
    return {
        **rev,
        "crossing_window_h": T,
        "closed": rev["revisit_h"] <= T + 1e-12,
        "n_to_close": int(max(1, n_need)),
        "L_max_closed_km": L_max,
        "method": REF_BARRIER,
    }
