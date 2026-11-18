<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# MDO — `hq:*` / `aeroel:*` as constraints (opt-in)

```bash
PYTHONPATH=src python examples/mdo/hq_aeroel_constraints_demo.py
```

Activate in a mission YAML:

```yaml
assumptions:
  mdo:
    hq_aeroel_constraints: true
    # optional allow-list (suffix or full key):
    # hq_aeroel_keys: [dutch_roll, flutter, CAP]
```

Default / omitted keeps the legacy filter-after behaviour. Unassessed checks
(e.g. `hq:spiral` without `geometry.dihedral_deg`) are never satisfied constraints.

## MDO de sistema (`acdt mdo`, docs/MDO.md)

* `uav150_tailless_mdo.yaml` — MTOW × autonomia da asa voadora sem deriva (NSGA-II, AR/autonomia/perda).
* `uav150_fleet_propulsion_closure.yaml` — propulsão no ciclo exterior + fecho da frota por iteração (Ha 2010).
