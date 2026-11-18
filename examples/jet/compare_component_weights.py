# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Run illustrative alternatives, no architecture selection or OEW validation.

PRESSUPOSTO component inputs/masses in coupled_components.yaml. The +10% ultimate
load sensitivity is a study perturbation, not a regulatory sizing instruction.
"""
from copy import deepcopy
import json
from pathlib import Path
from acdt.ai.jet import jet_size, load_spec

if __name__ == "__main__":
    spec = load_spec(Path(__file__).with_name("coupled_components.yaml"))
    statistical = deepcopy(spec); statistical["weights"] = {"mode": "statistical"}
    heavier = deepcopy(spec); heavier["weights"]["ultimate_n"] *= 1.10
    missing = deepcopy(spec); missing["weights"]["items"].pop(3)
    results = {}
    for name,candidate in [("statistical",statistical),("components",spec),("load_plus_10_percent",heavier),("missing_fuselage",missing)]:
        r=jet_size(candidate)
        results[name]={"run_id":r["run_id"],"converged":r["converged"],"mtow_kg":r["mtow_kg"],
                       "empty_mass_kg":r["weights"]["empty_mass_kg"] if r["weights"] else None,
                       "solver_status":r["solver"]["status"],
                       "coverage":r.get("weight_build_up",{}).get("coverage")}
    print(json.dumps(results,indent=2,ensure_ascii=False))
