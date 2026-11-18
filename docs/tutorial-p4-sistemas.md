# Tutorial P4 — Arquitetura elétrica e trade de carga útil

## O que faz

1. **Arquitetura elétrica** — orçamento de potência (MIL-E-7016F; Moir & Seabridge) com geração,
   baterias de aviónica e cargas por barramento; margens N1 (`generation` 1,25, `battery_wh` 1,20) como
   PRESSUPOSTO.
2. **Trade de carga útil** — catálogo (massa, potência média/pico, volume, FOV) comparado em Pareto
   (`compare`); o catálogo embutido é **EXAMPLE DATA** — a IA deve pesquisar datasheets com `source` +
   `retrieved`.
3. **Custo por hora de voo (agregação)** — soma directa de energia × preço + manutenção + outros
   (preços do utilizador) — `cost-fh` / `cost_per_flight_hour`.
4. **DOC operacional Eastlake/CER** (opt-in) — elementos Raymer 2018 Cap. 18; `unit_price` pode
   vir do Eastlake (Gudmundsson 2014 Cap. 2) ou DAPCA IV; no morph, `operating_cost` no JSON
   `--systems` anexa `cost_per_fh` só com `status=ok` (termo em falta → unassessed, nunca zero
   silencioso).

## CLI

```bash
source /workspace/acdt_env.sh   # ou o vosso venv
export PYTHONPATH=src

acdt systems-p4 catalog -o /tmp/cat.json
acdt systems-p4 electrical --architecture examples/systems/electrical_uav_isr.json -o /tmp/elec.json
acdt systems-p4 payload-trade --kinds radar,eo_ir -o /tmp/pay.json
acdt systems-p4 cost-fh --rate 1.2 --price 2.0 --maintenance 15 -o /tmp/cost.json

# DOC completo (Eastlake → aquisição + elementos Raymer) — EXAMPLE rates
acdt systems-p4 ops-cost --operating examples/systems/ops_cost_eastlake_complete.json -o /tmp/ops_ok.json
# termo em falta (preço combustível) → status=unassessed, per_flight_hour=null
acdt systems-p4 ops-cost --operating examples/systems/ops_cost_unassessed_fuel.json -o /tmp/ops_un.json

# morph: anexar DOC quando inputs existem (opt-in)
acdt morph evaluate --architectures examples/morphology/n1_ops_cost_arches.json \
  --mission examples/uav_endurance_payload.yaml \
  --systems examples/morphology/n1_ops_cost_systems.json --limit 2 -o /tmp/morph_ops.json
# unit_price_from=size sem unit_cost no size → unassessed
acdt morph evaluate --architectures examples/morphology/n1_ops_cost_arches.json \
  --mission examples/uav_endurance_payload.yaml \
  --systems examples/morphology/n1_ops_cost_unassessed_systems.json --limit 1 -o /tmp/morph_ops_un.json
```

## MCP

`electrical_catalog`, `electrical_analyse`, `payload_catalog`, `payload_trade`,
`cost_per_flight_hour`, `operational_cost`.

## Limites

* Fecho automático de hotel/massa no `acdt size`: usar o bloco transversal `onboard` na missão
  (ver [tutorial-onboard.md](tutorial-onboard.md) — ponte nativa). `systems-p4` sozinho continua a
  ser análise/trade; o acoplamento de combustível/energia no size é via `onboard`.
* DOC usa CERs de aquisição + taxas datadas do utilizador/agente — **não** inventa cotações L2
  nem BOM completo (HANDOFF MÉDIA §5).
* Catálogo de exemplo: não é recomendação de produto.
