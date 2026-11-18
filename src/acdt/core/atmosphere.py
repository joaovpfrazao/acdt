"""International Standard Atmosphere (ISA) 0–20 km.

Source: ISO 2533:1975 / ICAO Doc 7488 (Manual of the ICAO Standard Atmosphere);
also Anderson, *Introduction to Flight*, Ch. 3 (hydrostatic + gradient layers).
Viscosity: Sutherland's law with ICAO constants (beta_s = 1.458e-6, S = 110.4 K).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

R_AIR = 287.05287  # J/(kg K)  ICAO
GAMMA = 1.4
T0 = 288.15  # K
P0 = 101325.0  # Pa
RHO0 = 1.225  # kg/m^3
G0 = 9.80665
LAPSE = -0.0065  # K/m troposphere
H_TROPO = 11000.0


@dataclass(frozen=True)
class AtmState:
    altitude: float  # geopotential altitude [m]
    T: float  # K
    p: float  # Pa
    rho: float  # kg/m^3
    a: float  # speed of sound m/s
    mu: float  # dynamic viscosity Pa s

    @property
    def sigma(self) -> float:
        """Density ratio rho/rho0."""
        return self.rho / RHO0

    @property
    def nu(self) -> float:
        return self.mu / self.rho


def isa(h: float, dT: float = 0.0) -> AtmState:
    """ISA state at geopotential altitude ``h`` [m] (valid 0–20 km).

    ``dT`` is an ISA temperature offset [K] (pressure profile kept standard,
    density from the ideal-gas law, the usual ISA+dT convention).
    """
    if h < -1000 or h > 20000:
        raise ValueError("isa(): altitude outside -1 km .. 20 km")
    if h <= H_TROPO:
        T = T0 + LAPSE * h
        p = P0 * (T / T0) ** (-G0 / (LAPSE * R_AIR))
    else:
        T11 = T0 + LAPSE * H_TROPO
        p11 = P0 * (T11 / T0) ** (-G0 / (LAPSE * R_AIR))
        T = T11
        p = p11 * math.exp(-G0 * (h - H_TROPO) / (R_AIR * T11))
    T += dT
    rho = p / (R_AIR * T)
    a = math.sqrt(GAMMA * R_AIR * T)
    mu = 1.458e-6 * T ** 1.5 / (T + 110.4)
    return AtmState(h, T, p, rho, a, mu)


def altitude_from_density(rho: float) -> float:
    """Inverse ISA (troposphere/lower stratosphere) by bisection."""
    lo, hi = -1000.0, 20000.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if isa(mid).rho > rho:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
