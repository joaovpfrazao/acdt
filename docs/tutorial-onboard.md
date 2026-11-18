<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Carga útil e elétrica transversais — L0 opt-in

Ferramenta de apoio ao projeto, **não** certificação. Payload e elétrica aplicam-se a
hélice térmica/elétrica, jato e VTOL: não são um ramo exclusivo de hélices.
`onboard_size` / `acdt onboard size` chama os dimensionadores existentes; não é um
novo simulador comum nem um otimizador global. Os comandos antigos mantêm os defaults.

```bash
acdt onboard size --input examples/onboard/jet.yaml -o out/onboard/jet.json
acdt onboard size --input examples/onboard/vtol.yaml -o out/onboard/vtol.json
acdt onboard size --input examples/onboard/electric.yaml -o out/onboard/electric.json
acdt onboard size --input examples/onboard/thermal.yaml -o out/onboard/thermal.json
PYTHONPATH=src python examples/onboard/check_examples.py
```

**Código CLI:** 0 = todos os checks agregados avaliados e satisfeitos; 1 = parcial,
inviável ou não convergido; 2 = entrada inválida. Os exemplos deixam CG/FOV/calor/volume
por avaliar, portanto devolvem 1 sem serem erros de execução. Ver `unassessed_checks`,
`checks`, `onboard.checks`, `issues` e `combined_checks_passed` (`true`/`false`/`null`).
O `feasible` nativo conserva o âmbito anterior, separado deste agregado. Cada chamada
regista inputs resolvidos, PRESSUPOSTOS, commit e resultado em `runs/`.

## Receita e propriedade das massas

`schema_version: '1.0'`, `model: prop|jet|vtol|hybrid`, `aircraft` (mapa nativo ou
ficheiro relativo à receita; prop exige `requirements.propulsion_type` explícito), `onboard` e, quando necessário, `duration`, `mass_ledger`,
`integration` e `mission`. Exemplos completos em `examples/onboard/`.

O bloco `onboard` também tem `schema_version: '1.0'`, `source`, listas explícitas
`items`, `loads`, `sources`. Cada linha tem `source` (datasheet ou **PRESSUPOSTO**).
Não existe uma lista fechada de payloads/arquiteturas. Identificadores são únicos.

* Item: `id`, `role: payload|equipment`, `mass_kg`, `mass_accounting: incremental|included`.
  `included` exige `included_in: payload|empty|mtow`; não é somado de novo.
  `incremental` significa **adicional** à estimativa/allowance/deck de base. Massas
  desconhecidas não são zero: fornecer uma massa explícita e a sua proveniência.
* Payload incremental aumenta o requisito de payload nos fechos prop/jato. Equipamento
  aumenta a massa fixa no prop e a massa vazia no jato; em modo de componentes do jato,
  torna-se um item fornecido com cobertura própria (não um resíduo ajustado ao OEW).
  Não repetir gerador, bateria dedicada, tanque ou acessórios já incluídos no baseline.
  Nomes duplicados nos inventários conhecidos são recusados; a declaração de inclusão
  não é uma auditoria independente das massas implícitas nas regressões.
* **VTOL:** `mass_kg` continua a ser MTOW fornecido e inclusivo. Todos os itens têm de
  ser `included_in: mtow`. O check compara itens + bateria propulsiva dimensionada +
  `mass_ledger.remaining_nonbattery_mass_kg` com esse MTOW. O resto exclui os itens
  declarados e a bateria principal. Sem esse resto, orçamento de massa por avaliar.
  Mais payload reduz a margem, **não aumenta silenciosamente MTOW** nem altera o hover
  à mesma massa total. Ainda não existe fecho estrutural/MTOW VTOL.

## Potência, consumo e reservas: uma vez só

Load: `id`, `item_id`, `source_id`, `power_W`, `peak_W`, `duty` [0,1]. Média = soma
`power_W*duty`; pico = soma conservadora dos picos ligados, sem fator de simultaneidade
inventado. `delivery_efficiency` é do terminal da fonte até à carga: dividir a média
**e** o pico uma vez. `continuous_W`/`peak_W` da fonte são limites alocados; sem limites
não se declara aprovação. Duty constante não é scheduling transitório/de falhas.

| Fonte | Acoplamento efetivo | Dados adicionais explícitos |
|---|---|---|
| `main_battery` | Prop elétrico: energia, massa da bateria e MTOW; VTOL: energia e bateria limitada por energia **ou pico/C-rate** | Sem `item_id` ou reserva própria: pack principal pertence ao dimensionador |
| `battery` dedicada | Massa do item uma vez; capacidade útil face ao tempo da missão | `item_id`, `usable_Wh` já líquido de DoD, `reserve_fraction` extra sobre consumo útil |
| `generator` no prop térmico | Consumo extra na equação de massa/Breguet; extração reduz potência disponível e margem de cruzeiro | `item_id`, `generator_efficiency`, `bsfc_kg_kWh_shaft`, `shaft_limit_W` |
| `generator` no jato | Fluxo extra integrado no cruzeiro + fases temporizadas; débito de tração e margem média/pico | `item_id`, `fuel_kg_kWh_terminal`, `thrust_penalty_N_per_W_terminal` |

No prop térmico: `P_shaft=P_terminal/eta_generator`,
`b[kg/s]=P_shaft[W]*BSFC[kg/kWh]/3.6e6`. A integração de Breguet com o termo constante
é a solução exata de `dm/dt=-a*m-b`; não é uma correlação nova de motor. No jato usa-se
`dm/dx=-(TSFC*D+b)/V`. **Não se estima nenhum coeficiente de acessórios:** os valores
são incrementais fornecidos, a validar por deck/fornecedor. Sem modelo, não se corre o
avião com eletricidade grátis: estado `unassessed`, resultado de aeronave ausente.
Loads em hélice térmica/jato (também com bateria dedicada) pedem tempos `duration.precruise_s`/`postcruise_s` e `source`; as frações de
fase legadas continuam a estimar a propulsão. Não confundir estes tempos com trajetória.

A reserva/DoD do pack principal e a reserva de combustível continuam exclusivamente
nos modelos nativos. Bateria dedicada: `required_Wh=P_terminal*t/3600*(1+reserve_fraction)`;
`usable_Wh` não volta a ser multiplicado por DoD. Não duplicar o bloco `systems` ou
hotel/extraction inputs legados na mesma receita. Pack de energia principal do prop
não verifica ainda a seleção combinada por pico propulsão + hotel: check por avaliar.

`mission` opcional chama realmente o **pointmass existente apenas para prop** a partir
do dimensionamento acoplado: hotel/consumo/extração acompanham-no. É verificação direta,
não um segundo fecho. A capacidade dedicada é também avaliada no tempo efetivamente
voado; o check de conclusão não garante todas as restrições de missão. Gerador com
hélice BEMT/passo fixo, falhas/OEI e extração térmica em 6-DOF ficam por implementar.
No jato, takeoff/OEI opcional com extração fica explicitamente por avaliar; não há
propagação automática para envelopes de falhas. Jato/VTOL não ganharam simulador dinâmico.

## Espaço, calor, CG e FOV: transversal, com limites honestos

`volume_m3` e `heat_W` opcionais por item são comparados com volumes líquidos alocados
`constraints.available_volume_m3` e capacidade declarada
`available_heat_rejection_W` + `source`. Não se usa volume bruto de fuselagem; nem se
infere calor total a partir de watts elétricos. Dados incompletos → por avaliar.

`integration` reutiliza `assembly.integration.check` com assembly, `placements` por id,
restrições abertas e proveniência. A massa vem dos itens, nunca dos placements.
CG de avião exige `base.mass_kg` reconciliada com MTOW menos inventário e CG desse resto
(incluindo bateria principal/combustível), todas as posições e restrição `cg_range`.
FOV só é avaliado com cones/obstáculos fornecidos. São screens geométricos independentes,
não realimentação automática da montagem, deslocação otimizada do CG ou projeto térmico.

## Fecho L0 térmico / CG / espacial / FOV (opt-in `closure`)

Bloco de receita `closure` (esquema 1.0) em `acdt onboard size`, exemplo
`examples/onboard/closure_electric.yaml`. Primitivas abertas — sem catálogo fechado nem
malha obrigatória:

* **thermal**: `heat_mode` `declared` | `declared_plus_conversion` | `conversion_only`.
  Calor declarado Σ `heat_W`; conversão = perda de distribuição
  `P_load·(1/η_delivery−1)` (+ gerador `shaft·(1−η_gen)` quando existir). Rejeição por
  `sinks[]` `capacity.available_W` ou `ram_air` com `Q=ṁ·cp·ΔT` (Incropera & DeWitt).
* **cg**: `base` + `placements` por id → Σm·r vs `envelope.x_m|y_m|z_m`. Sem posição ou
  envelope → CG por avaliar.
* **spatial**: baías AABB + caixas de itens (contenção, overlap, packing fraction).
* **fov**: cones az/el (ou Fibonacci) vs bloqueadores caixa/esfera (teste slab); sem
  FOV/`blockers` → por avaliar. FOV completo com malha continua em `assembly.integration`.

Números do exemplo (PRESSUPOSTO, elétrico): MTOW≈19.33 kg; calor≈41.1 W vs rejeição≈70.2 W
(margem≈29.1 W); CG x≈0.546 m dentro de [0.45,0.70]; packing nose/mid 0.30/0.13; FOV
bloqueado≈0.032 ≤ 0.15. Omitting `closure` deixa CG/FOV por avaliar como antes.

**Consumo nativo:** `jet_size` / dimensionadores nativos **não** auto-consomem a receita
`onboard` (chave rejeitada com remissão a `onboard_size`). O caminho transversal continua
explícito: `acdt onboard size` / `onboard_size`.

`hybrid`: apenas balanços de carriers explicitamente alocados com
`duration.accounting_s`; **sem dispatch propulsivo**, fecho nativo ou simulador híbrido.
No prop, aplicar `storage_check` ao resultado de missão separadamente: `sizing.run` não consome um bloco `aircraft.storage`.
A camada `storage_check` existente continua a tratar capacidade/volume de combustível e
packs: esta fatia reutiliza os mesmos validadores/convenções, não adiciona as suas massas
ou reservas de novo. Decks de motor, validação e acoplamentos dinâmicos mais completos
continuam pendentes.

Métodos: `PowerBudget` existente (MIL-E-7016F/Moir & Seabridge), Raymer/Breguet e
Hepperle dos dimensionadores nativos; identidades de potência/energia e conversões NIST
SP811. Referências em `THIRD_PARTY.md`. Nenhuma dependência nova.


## Ponte nativa + fecho automático — `acdt size` / jet / VTOL (9–10 nov 2026)

Além de `acdt onboard size` (ecrãs CG/FOV/`closure`), o mesmo bloco `onboard` na missão fecha
**automaticamente** massa + hotel de combustível/energia dentro de `acdt size` / `jet_size` /
`size_vtol` — não é preciso um segundo passo. O módulo
`acdt.domains.aircraft.onboard_bridge` traduz hotel citado → hooks nativos; o relatório fica em
`DesignResult.onboard_bridge` / `result.json` / summary (issue info «onboard auto-closed»).

| Modelo | Hook nativo |
|--------|-------------|
| prop térmico | `assumptions.propulsion.auxiliary_fuel_flow_kg_s` + `auxiliary_shaft_W` (+ pre/post) |
| prop elétrico | `assumptions.propulsion.onboard_power_W` |
| jato | `auxiliary.fuel_flow_kg_s` + `thrust_penalty_N` (+ pre/post/`empty_mass_kg`) |
| VTOL elétrico | `electric.systems_power_W` / `systems_peak_power_W` |

Sem `onboard` o comportamento antigo mantém-se. Coeficientes em falta → erro **unassessed**
(nunca combustível/energia a zero). Híbrido sem `hybrid_dispatch` → unassessed.
Não inventar potência de radar: usar `power_W` com `source`, ou deixar por avaliar.

```bash
# prop: com hotel (PRESSUPOSTO 400 W — NÃO é Gabbiano) vs baseline
PYTHONPATH=src acdt size --spec examples/onboard/prop_size_radar_hotel.yaml --level L0 --no-systems
PYTHONPATH=src acdt size --spec examples/onboard/prop_size_baseline_no_hotel.yaml --level L0 --no-systems
```

Números ilustrativos (L0 handbook, Nov 2026): com hotel Wf ≈ 20,2 kg / W0 ≈ 152,5 kg;
sem hotel Wf ≈ 14,0 kg / W0 ≈ 115,4 kg (Δ inclui massa incremental + hotel + crescimento).
Jato PRESSUPOSTO 2 kW terminal: Δ fuel ≈ +53 kg sobre o coupled_size baseline.
VTOL exemplo `onboard/vtol.yaml` via `size_vtol`: energia e pack sobem com o hotel.
