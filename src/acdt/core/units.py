"""Minimal unit handling (SI internally).

Conversion factors are exact definitions (NIST SP 811, 2008 edition, Appendix B).
Every quantity in acdt is SI internally: m, s, kg, N, W, J, Pa, K, rad.
"""
from __future__ import annotations

import math

# dimension -> {unit: factor to SI}
_UNITS: dict[str, dict[str, float]] = {
    "length": {"m": 1.0, "km": 1e3, "ft": 0.3048, "in": 0.0254, "mm": 1e-3, "cm": 1e-2,
               "nmi": 1852.0, "NM": 1852.0, "mi": 1609.344},
    "time": {"s": 1.0, "min": 60.0, "h": 3600.0, "hr": 3600.0, "day": 86400.0},
    "mass": {"kg": 1.0, "g": 1e-3, "lb": 0.45359237, "t": 1000.0},
    "speed": {"m/s": 1.0, "km/h": 1 / 3.6, "kt": 1852.0 / 3600.0, "kts": 1852.0 / 3600.0,
              "KTAS": 1852.0 / 3600.0, "mph": 0.44704, "ft/s": 0.3048, "ft/min": 0.3048 / 60, "fpm": 0.3048 / 60},
    "power": {"W": 1.0, "kW": 1e3, "hp": 745.69987158227022, "shp": 745.69987158227022},
    "energy": {"J": 1.0, "kJ": 1e3, "Wh": 3600.0, "kWh": 3.6e6},
    "force": {"N": 1.0, "kN": 1e3, "lbf": 4.4482216152605},
    "angle": {"rad": 1.0, "deg": math.pi / 180.0},
    "angular_rate": {"rad/s": 1.0, "deg/s": math.pi / 180.0},
    "area": {"m2": 1.0, "m^2": 1.0, "ft2": 0.09290304, "ft^2": 0.09290304},
    "wing_loading": {"N/m2": 1.0, "Pa": 1.0, "kg/m2": 9.80665, "lb/ft2": 47.88025898, "psf": 47.88025898},
    "dimensionless": {"-": 1.0, "": 1.0, "g": 1.0, "%": 0.01},
    "currency": {"USD": 1.0, "kUSD": 1e3, "MUSD": 1e6},  # cost model output is USD; no FX conversion
    "sound": {"dB": 1.0, "dBA": 1.0},
    # diferença de temperatura (margens): 1 K = 1 °C; 1 °F de diferença = 5/9 K (NIST SP 811 B.8)
    "temperature_difference": {"K": 1.0, "°C": 1.0, "degC": 1.0, "C": 1.0, "°F": 5.0 / 9.0, "degF": 5.0 / 9.0},
    "voltage": {"V": 1.0},
    "current": {"A": 1.0},
    "specific_energy": {"J/kg": 1.0, "Wh/kg": 3600.0},
    "torque": {"N*m": 1.0, "Nm": 1.0, "kg*cm": 0.0980665, "kgf*cm": 0.0980665},
    "category": {"": 1.0, "-": 1.0},
    # material data (acdt.ai.external): psi = lbf/in², lb/in³, lb/ft³ from the exact lb, lbf, in, ft definitions
    "stress": {"Pa": 1.0, "kPa": 1e3, "MPa": 1e6, "GPa": 1e9, "N/mm2": 1e6, "psi": 4.4482216152605 / 0.0254**2,
               "ksi": 1e3 * 4.4482216152605 / 0.0254**2, "Msi": 1e6 * 4.4482216152605 / 0.0254**2},
    "density": {"kg/m3": 1.0, "kg/m^3": 1.0, "g/cm3": 1000.0, "g/cm^3": 1000.0, "lb/in3": 0.45359237 / 0.0254**3,
                "lb/ft3": 0.45359237 / 0.3048**3},
    "strain": {"-": 1.0, "": 1.0, "%": 0.01, "microstrain": 1e-6, "ue": 1e-6},
    "electric_charge": {"Ah": 3600.0, "mAh": 3.6, "C": 1.0},
    "rotational_constant": {"rpm/V": 1.0, "kv": 1.0},
}


class UnitError(ValueError):
    pass


def units_for(dimension: str) -> list[str]:
    return list(_UNITS[dimension])


def to_si(value: float, unit: str, dimension: str) -> float:
    """Convert ``value`` in ``unit`` to SI for the given ``dimension``.

    Temperature is not handled here (affine); use :mod:`acdt.core.atmosphere`.
    """
    table = _UNITS.get(dimension)
    if table is None:
        raise UnitError(f"Unknown dimension '{dimension}'")
    if unit not in table:
        raise UnitError(f"Unit '{unit}' not valid for {dimension}; use one of {sorted(table)}")
    return float(value) * table[unit]


def from_si(value: float, unit: str, dimension: str) -> float:
    return float(value) / _UNITS[dimension][unit]


def default_unit(dimension: str) -> str:
    return next(iter(_UNITS[dimension]))
