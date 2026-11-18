# Tutorial P7 — Sensibilidade e fidelidade por necessidade

## Ideia

Medir elasticidades locais ε = (Δy/y)/(Δx/x) das métricas de missão às variáveis e às
incertezas dos modelos. Onde |ε| é alto, **sobe a fidelidade** (DESIGN_WORKFLOW §5).

## CLI

```bash
export PYTHONPATH=src

# a partir de amostras já calculadas (rápido)
acdt sensitivity from-samples --input examples/sensitivity/samples_demo.json -o /tmp/s.json

# OAT no pipeline (handbook, sem systems — mais lento)
acdt sensitivity pipeline --mission examples/uav_endurance_payload.yaml \
  --variables examples/sensitivity/variables_uav.json -o /tmp/s_pipe.json

# Sobol' global opt-in (Saltelli/Jansen) — Ishigami demo ou missão handbook
acdt sensitivity sobol --input examples/sensitivity/sobol_ishigami.json -o /tmp/sobol.json
acdt sensitivity sobol --mission examples/uav_endurance_payload.yaml \
  --variables examples/sensitivity/sobol_uav_vars.json --n 8 --metric W0_kg -o /tmp/sobol_uav.json
# CIs percentis (Efron): acrescente --bootstrap 200

# Monte Carlo / LHS UQ (opt-in)
acdt sensitivity mc --input examples/sensitivity/mc_linear_demo.json -o /tmp/mc.json
acdt sensitivity mc --mission examples/uav_endurance_payload.yaml \
  --input examples/sensitivity/mc_uav_inputs.json --n 8 -o /tmp/mc_uav.json
```

### Sobol' (global)

Índices **S1** (primeira ordem) e **ST** (efeito total, inclui interações) a partir de matrizes
Saltelli A, B, A_B^(i). Estimadores Jansen (Saltelli et al. 2010). Sem `--bootstrap` → point
estimates; com bootstrap → intervalos percentis. Variância nula ou Y em falta → `unassessed`,
nunca um 0.0 que pareça “sem influência”.

Números ilustrativos (`sobol_ishigami.json`, N=256, seed=42 — PRESSUPOSTO demo):

| factor | S1 (est.) | ST (est.) | S1 analítico | ST analítico |
|--------|----------:|----------:|-------------:|-------------:|
| x1 | 0.314 | 0.657 | 0.314 | 0.558 |
| x2 | 0.454 | 0.412 | 0.442 | 0.442 |
| x3 | 0.031 | 0.266 | 0.000 | 0.244 |

Com N=1024 os ST aproximam melhor o analítico; N=256 basta para o exemplo CLI.
Sem `--bootstrap` os índices são point estimates; com `--bootstrap 100` vêm CIs percentis.

### Monte Carlo / LHS UQ

Propaga `inputs` com `dist: uniform|triangular|normal` por **LHS** (omissão) ou `--method mc`.
Saída: mean, std, p5/p50/p95, `gate_metrics` (`{metric}_p95`, …). Demo linear
`mc_linear_demo.json` (Y=2x1+x2, E[Y]=1.5).

Acoplar ao gate N1/N2:

```bash
acdt decisions gate output/decisions_isr --level N1 \
  --metrics examples/decisions/gate_n1_uq_pass.json --require-uq
```

## MCP

`sensitivity_from_samples`, `sensitivity_pipeline`, `sensitivity_sobol`, `sensitivity_mc`.

## Limites

* OAT / Sobol / gate-sem-UQ inalterados se MC/`--uq` não forem pedidos.
* UQ ou Sobol em falta com `--require-uq` → gate `unassessed` (nunca pass).
* `pipeline` / `sobol` / `mc` usam handbook + `no_systems` por omissão; N pequeno = smoke.
* As dicas de fidelidade são heurísticas por caminho de variável.
