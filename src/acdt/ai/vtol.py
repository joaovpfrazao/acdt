# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Toolkit wrappers for VTOL / eVTOL L0 (momentum-theory hover, transition, architecture compare)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acdt.domains.aircraft.vtol import ARCHITECTURES, compare_architectures, hover_point, size_vtol


def load_spec(path_or_dict: str | dict) -> dict:
    """Spec from a dict, a JSON or a YAML file."""
    if isinstance(path_or_dict, dict):
        return path_or_dict
    p = Path(path_or_dict)
    txt = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(txt)
    return json.loads(txt)


def vtol_hover(mass_kg: float, n_rotors: int = 4, diameter_m: float | None = None,
               disk_loading_N_m2: float | None = None, FM: float = 0.70, altitude_m: float = 0.0,
               download_factor: float = 1.0, bemt: dict | None = None) -> dict[str, Any]:
    out = hover_point(mass_kg, n_rotors, diameter_m, disk_loading_N_m2, FM, altitude_m,
                      download_factor=download_factor)
    out["pressupostos"] = [k for k, v in (("FM", FM == 0.70), ("download_factor", download_factor == 1.0)) if v]
    if bemt:
        from acdt.domains.aircraft.vtol.bemt import attach_to_hover
        out = attach_to_hover(out, bemt)
        if out.get("power_source") == "bemt":
            out["pressupostos"] = [x for x in out["pressupostos"] if x != "FM"]
    return out


def vtol_size(spec: str | dict) -> dict[str, Any]:
    return size_vtol(load_spec(spec))


def vtol_compare(spec: str | dict, architectures: list[str] | None = None,
                 overrides: dict | None = None) -> dict[str, Any]:
    s = load_spec(spec)
    return compare_architectures(s, architectures or s.get("compare"), overrides or s.get("overrides"))


def vtol_architectures() -> dict[str, Any]:
    return {"architectures": ARCHITECTURES, "note": "all defaults are PRESSUPOSTO; override in the spec"}
