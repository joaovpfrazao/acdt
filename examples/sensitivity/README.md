<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Exemplos P7 — sensibilidade

* `samples_demo.json` — OAT local (elasticidades).
* `variables_uav.json` — caminhos para `sensitivity pipeline`.
* `sobol_ishigami.json` — avaliações Saltelli da função Ishigami (Homma & Saltelli / Primer).
* `sobol_uav_vars.json` — 2 variáveis ±10 % para smoke Sobol handbook.

```bash
PYTHONPATH=src acdt sensitivity sobol --input examples/sensitivity/sobol_ishigami.json -o /tmp/sobol.json
```

* `mc_linear_demo.json` — LHS pré-computado Y=2x1+x2 (E[Y]=1.5) + W0_kg.
* `mc_uav_inputs.json` — inputs uniformes para `sensitivity mc --mission …`.

```bash
PYTHONPATH=src acdt sensitivity mc --input examples/sensitivity/mc_linear_demo.json -o /tmp/mc.json
```
