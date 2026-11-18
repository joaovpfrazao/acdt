# Tutorial P6 (leve) — Forma OML N2 com aero/RCS/packaging

## O que faz

Latin hypercube sobre variáveis de forma facetada (já usadas no estudo aero/RCS) **mais**
escalas de fuselagem, estação vertical/longitudinal da asa e estação do sensor. Objectivos
Pareto: `perf_ratio` ↑, RCS frontal ↓, `pack_score` ↑.

**Não inclui** RANS / ADflow / TACS — isso fica para o Grok Build no PC do João.

## CLI

```bash
export PYTHONPATH=src
acdt shape bounds
acdt shape packaging --L 1.8 --D 0.22 --x-wing-le 0.6 --sensor-x 0.3 \
  --payload '{"volume_l": 2.5}'
acdt shape study --result examples/output/uav_endurance_payload_mdo/baseline/result.json \
  -o /tmp/shape_n2 --samples 40 --payload '{"volume_l": 2.5}'
```

## MCP

`shape_bounds`, `shape_n2_study`, `shape_packaging_score`.

## Limites

* Packaging volume/FOV é heurística N2; FOV completo = `assembly.integration`.
* RCS = Óptica Física; aero = diferencial sobre o `result.json` dimensionado.
