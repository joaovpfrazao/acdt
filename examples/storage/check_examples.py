# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Run existing producers then common storage adapters; no new simulator or reference data."""
from pathlib import Path
import json
from acdt.ai.jet import load_spec, jet_size
from acdt.ai.storage import storage_check
from acdt.domains.aircraft.flightsim.pointmass import simulate_pointmass_mission
from acdt.domains.aircraft.vtol.size import size_vtol

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/"out/storage/examples"
OUT.mkdir(parents=True, exist_ok=True)
for label in ("prop", "electric", "jet", "vtol"):
    if label in ("prop", "electric"):
        producer = simulate_pointmass_mission(ROOT/f"examples/storage/{label}_mission.yaml")
        kind, reserve = "mission", .15  # PRESSUPOSTO extra usable reserve, not a rule
        config = "fuel_prop" if label == "prop" else "electric"
    elif label == "jet":
        producer = jet_size(ROOT/"examples/jet/coupled_size.yaml")
        kind, reserve, config = "jet_size", None, "jet"
    else:
        producer = size_vtol({"mass_kg": 25})  # existing illustrative default mission, PRESSUPOSTO
        kind, reserve, config = "vtol_size", None, "vtol"
    (OUT/f"{label}_producer.json").write_text(json.dumps(producer, indent=2, allow_nan=False)+"\n")
    r = storage_check(ROOT/f"examples/storage/{config}.yaml", kind, producer, reserve)
    (OUT/f"{label}_storage.json").write_text(json.dumps(r, indent=2, allow_nan=False)+"\n")
    print(label, "storage_feasible=", r["storage_feasible"], "demand=", r["demand"], "run=", r["run_id"])
