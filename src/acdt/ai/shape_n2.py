"""Toolkit wrappers for P6 light N2 shape study."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from acdt.domains.aircraft.shape_opt import packaging_score, run_n2_study
from acdt.domains.aircraft.rcs import geometry as G


def shape_n2_study(result_json: str, output: str, n_samples: int = 40, seed: int = 0,
                   payload: dict | None = None) -> dict[str, Any]:
    return run_n2_study(result_json, output, n_samples=n_samples, seed=seed, payload=payload)


def shape_packaging_score(L: float, D: float, x_wing_le: float, sensor_x: float,
                          payload: dict | None = None) -> dict:
    info = {"L": L, "D": D, "x_wing_le": x_wing_le, "sensor_x": sensor_x}
    return packaging_score(info, payload=payload)


def shape_bounds() -> dict:
    from acdt.domains.aircraft.shape_opt.n2 import BOUNDS_N2
    return {"bounds": BOUNDS_N2, "shape_fields": list(G.Shape.__dataclass_fields__)}
