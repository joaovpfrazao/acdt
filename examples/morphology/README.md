<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Exemplos morfológicos N1

* `n1_uav_isr_matrix.json` — matriz ISR legado (sem mudança de contrato).
* `n1_energy_comms_matrix.json` — eixos energy/comms com opções-dict e casos unassessed.
* `n1_energy_comms_systems.json` — `hybrid_templates` + `mission_context` para evaluate.

```bash
PYTHONPATH=src acdt morph generate --matrix examples/morphology/n1_energy_comms_matrix.json -o /tmp/g.json
PYTHONPATH=src acdt morph evaluate --architectures /tmp/g.json \
  --mission examples/uav_endurance_payload.yaml \
  --systems examples/morphology/n1_energy_comms_systems.json --limit 6 -o /tmp/e.json
```
