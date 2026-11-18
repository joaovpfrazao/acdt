# Tutorial P2 — matriz morfológica N1 e poda por conjuntos

O nível N1 (DESIGN_WORKFLOW) parte de uma **matriz morfológica aberta** (Zwicky 1969): uma linha por
dimensão, opções como sementes — não uma lista fechada. A IA acrescenta opções e propõe pelo menos uma
alternativa fora do habitual. O gerador só **combina** e **corta incompatibilidades físicas** com um
motivo escrito. A avaliação multidisciplinar em baixa fidelidade reutiliza `acdt size` e o **simulador de
missão em massa pontual** como juiz comum. A poda é *set-based* (Sobek, Ward & Liker 1999): ficam 2–3
vivas; só se corta o claramente dominado dentro da banda de incerteza N1 (PRESSUPOSTO ±15 %).

## 1. Matriz

```bash
acdt morph matrix -o output/morph_matrix.json
# ou partir do exemplo
cp examples/morphology/n1_uav_isr_matrix.json output/morph_matrix.json
```

## 2. Gerar e cortar

```bash
acdt morph generate --matrix output/morph_matrix.json \
  --dimensions wing,fuselage,tail,propulsion_layout,propulsion_kind,launch_recovery,landing_gear,energy \
  --max-combinations 500 -o output/morph_gen.json
```

O JSON traz `kept` e `cut` (cada corte com `reason`).

## 3. Avaliar

```bash
acdt morph evaluate --architectures output/morph_gen.json \
  --mission examples/uav_endurance_payload.yaml \
  --sim examples/simulation/n0_patrol.yaml \
  --level L0 --limit 8 -o output/morph_eval.json
```

Sem `--sim`, corre só o dimensionamento (métricas W0, L/D, …). Com `--sim`, o juiz de massa pontual
acrescenta alcance, autonomia e tempo em estação. Opções de asa/cauda/fuselagem ainda **não** mudam a
geometria do `size` (PRESSUPOSTO / HANDOFF P1); ficam no registo.

## 4. Podar

```bash
acdt morph prune --rows output/morph_eval.json --band 0.15 --keep 3 -o output/morph_alive.json
```

## MCP

Ferramentas: `morph_matrix`, `morph_generate`, `morph_evaluate`, `morph_prune`.

## Referências

* Zwicky, F. (1969), *Discovery, Invention, Research through the Morphological Approach*.
* Sobek, D. K., Ward, A. C. & Liker, J. K. (1999), *Sloan Management Review* 40(2).
* Deb, K. (2001), Pareto dominance (via `compare_alternatives` / `tradeoff.compare`).
* Anderson (1999) Cap. 5; Raymer (2018) Cap. 17 — juiz de massa pontual.


## 5. Energia / híbrido / datalink / SATCOM (P4, opt-in)

Os eixos `energy` e `avionics_link` são **abertos**: as sementes (`hybrid_series`, `SATCOM_Ku`, …)
são atalhos, não um catálogo fechado. A IA acrescenta opções como

```json
{"id": "datalink_mesh", "power_W": 40, "mass_kg": 0.6,
 "source": "PRESSUPOSTO ou datasheet", "retrieved": "2026-11-10"}
```

```bash
acdt morph generate --matrix examples/morphology/n1_energy_comms_matrix.json \
  --max-combinations 50 -o /tmp/morph_ec_gen.json
acdt morph evaluate --architectures /tmp/morph_ec_gen.json \
  --mission examples/uav_endurance_payload.yaml \
  --systems examples/morphology/n1_energy_comms_systems.json \
  --limit 6 -o /tmp/morph_ec_eval.json
```

* Com `hybrid_templates` + `source` → `hybrid_dispatch` (Pornet & Isikveren 2015; Guzzella & Sciarretta 2013).
* Com `power_W` + `source` no link → hotel `comms_power_W`.
* Sem modelo/source → `unassessed_axes` (nunca passa como sistemas fechados; poda set-based mantém vivos).
* Cortes físicos: hybrid_series≠piston; hybrid_parallel≠electric puro; battery≠piston; etc.
* **Eastlake/CER operacional** no mesmo passo: ainda aberto.
