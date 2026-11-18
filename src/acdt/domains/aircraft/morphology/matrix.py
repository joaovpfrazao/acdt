"""Open morphological matrix (Zwicky 1969). Seeds are starting options, never a closed list.

The agent (or YAML) may add dimensions and options. Options may be plain ids (strings) or
dicts ``{id, source, retrieved?, …}`` so provenance travels with a custom link/energy choice.
The generator never refuses an unknown option: it only combines and, separately, cuts physical
incompatibilities with a written reason.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

# Seeds from docs/DESIGN_WORKFLOW.md § N1 — shortcuts that assemble generic concepts, NOT a catalogue.
# Energy / hybrid / datalink / SATCOM expanded 10 nov 2026 (P4); string ids stay backward compatible.
SEED_DIMENSIONS: dict[str, list] = {
    "wing": ["low", "mid", "high", "flying_wing", "box_wing", "joined_wing", "tandem"],
    "fuselage": ["pod", "blended", "lifting_body", "twin_boom", "radome_ventral", "radome_dorsal"],
    "tail": ["conventional", "T", "V", "inverted_V", "H", "canard", "tailless"],
    "propulsion_layout": ["tractor", "pusher", "distributed", "on_booms"],
    "propulsion_kind": ["piston", "electric", "hybrid"],
    "launch_recovery": ["runway", "catapult", "net", "parachute", "VTOL"],
    "landing_gear": ["tricycle", "taildragger", "none", "skids"],
    # energy source / hybrid architecture (Pornet & Isikveren 2015 vocabulary as shortcuts)
    "energy": [
        "fuel", "battery", "hybrid",  # legacy seeds
        "fuel_avgas", "fuel_jetA", "battery_LiIon",
        "hybrid_series", "hybrid_parallel",
    ],
    # communications / C2 (LOS datalink, relay, SATCOM bands) — supply power/mass+source to assess
    "avionics_link": [
        "LOS", "relay", "SATCOM",  # legacy
        "datalink_LOS", "datalink_relay", "SATCOM_L", "SATCOM_Ku",
    ],
    "payload": ["EO_IR", "radar", "AIS", "ESM", "multi"],
}


def option_id(opt: Any) -> str:
    """Normalize a matrix option (str or dict) to its id."""
    if isinstance(opt, dict):
        oid = opt.get("id") or opt.get("name")
        if not oid:
            raise ValueError("option dict needs 'id' (or 'name')")
        return str(oid)
    return str(opt)


def option_meta(opt: Any) -> dict:
    """Metadata for an option (empty for plain strings)."""
    if isinstance(opt, dict):
        return {k: v for k, v in opt.items() if k not in ()}
    return {"id": str(opt)}


def normalize_dimensions(dimensions: dict[str, list]) -> dict[str, list[str]]:
    """Map option objects → id lists for Cartesian product; meta kept separately by caller."""
    return {k: [option_id(o) for o in opts] for k, opts in dimensions.items()}


def index_option_meta(dimensions: dict[str, list]) -> dict[str, dict[str, dict]]:
    """``meta[dim][id] = option dict`` for dict-valued options (and thin {id} for strings)."""
    out: dict[str, dict[str, dict]] = {}
    for dim, opts in dimensions.items():
        out[dim] = {}
        for o in opts:
            oid = option_id(o)
            out[dim][oid] = option_meta(o)
    return out


@dataclass
class MorphMatrix:
    """One row per dimension; each value is an open list of option ids or option dicts."""
    dimensions: dict[str, list] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def add_option(self, dimension: str, option: str | dict) -> None:
        self.dimensions.setdefault(dimension, [])
        oid = option_id(option)
        existing_ids = {option_id(o) for o in self.dimensions[dimension]}
        if oid not in existing_ids:
            self.dimensions[dimension].append(option)

    def add_dimension(self, name: str, options: list | None = None) -> None:
        if name not in self.dimensions:
            self.dimensions[name] = list(options or [])

    def to_dict(self) -> dict:
        return {
            "dimensions": {k: list(v) for k, v in self.dimensions.items()},
            "notes": list(self.notes),
            "reference": (
                "Zwicky 1969 — open morphological matrix; seeds are not a closed catalogue; "
                "option dicts may carry source/retrieved (P4 energy/comms 10 nov 2026)"
            ),
        }


def default_matrix(extra: dict[str, list] | None = None) -> MorphMatrix:
    """Seed matrix; ``extra`` merges additional options (and new dimensions) without removing seeds."""
    dims = deepcopy(SEED_DIMENSIONS)
    for k, opts in (extra or {}).items():
        dims.setdefault(k, [])
        have = {option_id(o) for o in dims[k]}
        for o in opts:
            if option_id(o) not in have:
                dims[k].append(o)
                have.add(option_id(o))
    m = MorphMatrix(dimensions=dims)
    m.notes.append(
        "PRESSUPOSTO: sementes DESIGN_WORKFLOW § N1 + atalhos energia/híbrido/datalink/SATCOM (P4); "
        "a IA acrescenta opções com source/retrieved; seeds ≠ catálogo fechado"
    )
    return m
