<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Missão–propulsão–frota: primeiro feedback N0→N1 (L0)

Ferramenta de apoio ao projeto, não certificação nem um otimizador universal.
`acdt fleet study --input examples/fleet/prop_electric.yaml -o /tmp/fleet.json`
expõe a ferramenta MCP `mission_fleet_study(spec, record=True)`.
O exemplo contém uma alternativa híbrida deliberadamente **por avaliar**: o comando
escreve todos os resultados e termina com código 1. Código 0 significa todos os casos
avaliados dentro do âmbito; 2 indica entrada global inválida. `record=True` guarda
entradas resolvidas, resultados e proveniência no registo de corridas existente.

## O que já está ligado por código

1. **N0 sem forma:** intervalos de autonomia e tempo em terra, distância de ida à estação,
   velocidade, permanência e payload. Avaliam-se os cantos declarados; não há distribuição
   de probabilidade, grelha escondida ou decisão automática da propulsão.
2. **N1 com receitas fornecidas:** chama-se `onboard_size`, não um novo dimensionador.
   Carga útil, equipamentos, gerador/extração e hotel continuam a ser contabilizados uma
   vez nos modelos existentes. A receita pode ser inline ou um ficheiro relativo ao estudo;
   o ficheiro de aeronave é relativo à receita. A lista de arquiteturas é aberta.
3. **Missão realizada → energia → serviço em terra → frota homogénea:** preservam-se os
   resultados nativos, checks, etapas e motivos de mudança. A frota inicial é provisória.
   Há duas bases N0: toda a permanência disponível no intervalo de autonomia e
   `fixed_mission_fleet_required_bounds`, com a mesma permanência pedida do N1.
   `feedback.delta_from_fixed_mission_bounds` isola esta comparação de duração coerente.
   A nova contagem depende da missão de duração fixa avaliada, **não** de autonomia máxima
   deduzida. N0 pode usar toda a permanência disponível no seu intervalo; N1 usa a
   permanência amostrada. Por isso, a diferença não mede só um efeito da propulsão.
4. Mantêm-se alternativas dominadas, inviáveis e por avaliar. Pareto só inclui casos
   integralmente avaliados **na mesma amostra e classe de cobertura das fases**; não existe
   vencedor ponderado por omissão nem comparação entre fidelidades incompatíveis.

| Adaptador | Consumo e tempo usados | Limite principal |
|---|---|---|
| Hélice térmica/elétrica | dimensionamento + pointmass real de ida/permanência/regresso em voo nivelado | começa já em altitude; sem saída/chegada, curvas ou operação no solo; equivalente energético, não fecho geográfico do regresso |
| Jato | fecho `jet_size` e integração diferencial Breguet; permanência convertida em distância à velocidade amostrada | não é loiter em curva; tempos pré/pós-cruzeiro fornecidos e frações de combustível nativas, não simulador dinâmico |
| VTOL | potência/energia por segmentos nativos, incluindo pairar/subida/transição modelados | MTOW fornecido inclusivo; payload ocupa orçamento, não incrementa o MTOW; sem dinâmica comum |
| Híbrido/outros | N0 e alternativa mantidos | sem dispatch ou adaptador N1 inventado |

PRESSUPOSTO desta primeira ponte: velocidade fixa e vento nulo, sem permanência geográfica
ou curvas no prop/jet. A velocidade de cada amostra substitui o cruzeiro da receita. No prop usa-se uma única
missão equivalente em alcance, eliminando a antiga perna de endurance para não somar duas
missões. Payload amostrado é o total: o inventário nomeado nunca é reduzido silenciosamente.
No VTOL, o resto é incluído no MTOW e testado contra o orçamento não-bateria declarado.

## Entradas abertas e serviço em terra

Ver os YAML em `examples/fleet/`. Esquema versionado `1.0`:

- `mission.envelope`: `[mínimo,máximo]` de `distance_km` (**ida**), `speed_m_s`,
  `on_station_h`, `payload_kg`; `mission.samples` dá os pontos explicitamente escolhidos.
- `candidates`: `id`, `architecture`, `source`, `n0.endurance_h`, `n0.turnaround_h`,
  `n0.source`, `recipe`, `turnaround`; fontes obrigatórias para os pressupostos.
- `operations`: `availability` (escalar ou MTBF/MTTR / MTBM/MDT), `n_stations`,
  `handoff_overlap_h`, `reserve_h`, `source`; `confidence` é opcional.
- `objectives`: sentidos `min|max` explícitos para `fleet_required`, `fleet_mtow_kg`,
  `ground_turnaround_h`, `mission_energy_Wh` ou `mission_fuel_kg`. Grandezas ausentes
  não são energia grátis nem critérios comparáveis.
- Até 32 amostras e 32 candidatos, no máximo 128 avaliações explícitas por estudo.

`turnaround.method: supplied` exige `duration_h`, `activity` e `source`: tempo **total**
fornecido de reabastecimento/troca/recarga/manutenção. É um PRESSUPOSTO operacional, não
verificação da infraestrutura. Sem fórmula empírica de reabastecimento inventada.

`method: charge` exige `average_input_W`, `efficiency`, `allocation:
dedicated_per_aircraft`, `fixed_h`, `combine: serial|parallel` e `source`.
A potência é a **média efetiva alocada no ciclo**, não a potência de placa nem uma curva
CC/CV. `charge_h = Wh_terminais_consumidos / (eficiência * W_entrada)`;
`grid_Wh = Wh_terminais / eficiência`. Reserva/DoD já pertencem ao dimensionamento e não
são multiplicadas de novo. Atividades independentes em paralelo usam o máximo dos tempos;
em série somam-se. Cada aeronave tem o seu recurso dedicado: reporta-se a quantidade de
carregadores exigida pela frota. Partilha/filas, várias baterias ativas e recarga combinada
com combustível ficam por avaliar. Infraestrutura instalada não é inferida.

A permanência efetiva substituível é `on_station_h - handoff_overlap_h`.
**PRESSUPOSTO:** a sobreposição já é voada dentro da permanência e ocupa o ciclo completo;
N intervalos de substituição têm de cobrir voo+terra. Assim o novo adaptador conserva
esse tempo no numerador da contagem; não altera o comportamento histórico de `ops.cycle`.
Disponibilidade média usa arredondamento conservador; confiança usa a rotina binomial
existente, com limite de procura 200. Falhar essa procura não cai silenciosamente na média.

## Elegibilidade e incerteza

`n1.eligible` é verdadeiro/falso/`null`, separadamente da viabilidade nativa. Energia,
missão, capacidades e serviço em terra precisam de prova no âmbito escolhido. Sem modelo
de extração/limite do gerador ou capacidade do pack não há candidato vencedor por omissão.
No prop elétrico, `pack_power.continuous_C`, `peak_C`, `source` opcionais fornecem ratings
**do pack**: `P_limite = C * Wh_nominais`. Verifica-se o rating propulsivo completo à
velocidade/altitude da missão e o pico de hotel simultâneo. Isto não seleciona hardware,
não substitui limites térmicos/transitórios e não resolve os antigos checks por magia.

Volume/calor/CG/FOV em falta e **não pedidos** ficam explicitamente fora desta decisão
operacional. Limites pedidos mas por avaliar bloqueiam; falhas conhecidas bloqueiam sempre.
Nenhuma elegibilidade aqui prova integração multidisciplinar/certificação. Contagens de
casos não elegíveis são apenas aritmética condicional (`feedback.count_is_conditional`).

`reserve_h` do N0 não é automaticamente equivalente à fração de reserva combustível/pack
nativa: se não for zero, o N1 permanece por avaliar até existir missão operacional de reserva.
As amostras e fontes preservam a incerteza declarada; não se propaga uma distribuição de
incerteza nem se otimiza continuamente o envelope.

## Executar e interpretar

```sh
PYTHONPATH=src python -m acdt.cli fleet study --input examples/fleet/jet.yaml -o /tmp/jet-fleet.json
PYTHONPATH=src python examples/fleet/check_examples.py
```

O script regista três estudos e demonstra deltas reais de consumo/frota ao mudar hotel e
potência média de recarga. Todos os números são **PRESSUPOSTOS ilustrativos**, não dados de
referência de aeronaves, carregadores ou infraestruturas. Os estudos jet/VTOL não partilham
necessariamente a mesma missão e não devem ser tratados como ranking inter-aeronaves.

**Pendente:** solver iterativo N0↔N1 com autonomia máxima/intervalos realizados, filas e
alocação dependente da frota, frota mista, despacho híbrido, fases comuns completas,
reservas operacionais e calibração. `convergence.kind: one_pass_feedback`,
`converged: null`: este primeiro encadeamento é real, mas não finge convergência.
Fontes: Ha (2010), disponibilidade/reliabilidade e Deb (2001) já em `THIRD_PARTY.md`;
modelos nativos mantêm as suas referências; identidade energética NIST SP811.

## Esquema 1.1 — autonomia máxima derivada, fecho e reserva operacional (9 nov 2026)

`schema_version: "1.1"` ativa o caminho iterativo; `1.0` mantém exatamente o resultado anterior.
Campos novos (só aceites em 1.1):

- `operations.operational_reserve: {time_h, divert_km, native_reserve: replace, source}` —
  reserva **explícita**, voada à velocidade/altitude da amostra (desvio à mesma velocidade,
  PRESSUPOSTO). Entra **uma vez**: na missão de dimensionamento e na procura de capacidade;
  fica fora do consumo nominal, da energia de recarga e do horário. A fração nativa é posta a
  zero e registada em `n1.reserve.native_replaced` (prop elétrico `energy_reserve`, jato
  `reserve_fraction`, VTOL `electric.reserve`). No prop térmico, os 6 % de Raymer (Eq. 3.11)
  juntam reserva e combustível não utilizável e não são separáveis: fica **por avaliar**,
  nunca reserva duplicada. Não usar `reserve_h` e `operational_reserve` em simultâneo.
- `operations.dwell_policy: requested | derived_max` — a frota usa a permanência pedida ou a
  máxima derivada do projeto fixo. As duas linhas aparecem sempre em `n1.operations_by_dwell`.
- `candidates[].endurance` (opcional): `tolerance_h`, `search_limit_h`, `max_iterations`,
  `closure_tolerance_h`, `closure_max_iterations` (tolerâncias numéricas, não físicas).
- Objetivo opcional `derived_max_on_station_h: max`.

**Autonomia máxima derivada** (`n1.endurance`): maior permanência na estação, à distância e
velocidade da amostra, que o projeto **já dimensionado** completa com ida, regresso e reserva
dentro da energia/combustível/massa utilizável. Duplicação do intervalo e bisseção (Burden &
Faires 2011, §2.1); devolve-se o maior valor **verificado** (conservador) e o histórico.
Monotonia em tempo é PRESSUPOSTO (massa fixa, potência positiva). Estados explícitos:
`converged`, `infeasible_at_zero_station`, `not_bounded_within_search_limit`,
`max_iterations`, `unassessed`.

| Modelo | Como se deriva | O que fica retido |
|---|---|---|
| Prop elétrico/térmico | pointmass nivelado do projeto fixo | energia nativa de descolagem+subida (elétrico) ou frações Raymer descolagem/subida/aterragem + auxiliar pré/pós (térmico): não se convertem em permanência, porque o pointmass começa já em voo |
| Jato | Breguet diferencial a MTOW fixo (`fixed_design_burn`, mesmos termos do `size_jet`) | combustível de reserva; tempos pré/pós fornecidos. Coincide com a missão de projeto por construção |
| VTOL | segmentos nativos; bateria até ao orçamento de massa inclusivo | MTOW fornecido; sem curvas/dinâmica |
| VTOL com `aircraft.closure` | segmentos nativos ao MTOW fechado; bateria necessária ≤ bateria instalada do fecho | MTOW e bateria fixos do projeto fechado; sem curvas/dinâmica |

**Iteração real, só onde existe dependência:** no prop e no jato o dimensionamento é
"rubber" (massa calculada para uma permanência de projeto) e a capacidade é verificada por
outro modelo/integrador. `n1.closure` corrige para cima,
`T_projeto(k+1) = T_projeto(k) + max(0, T_pedido − T_max(k)) + tol`, até a permanência
pedida ser verificada diretamente; nunca reduz o projeto nem elimina alocações nativas.
Histórico com resíduo, `requested_verified`, e estados `converged`, `not_contracting`,
`max_iterations`, `sizing_failed`, `capability_infeasible`, `capability_unassessed`.
No VTOL de MTOW fornecido: `not_applicable_fixed_supplied_mtow`, sem laço inventado. Com o
fecho de massa opt-in (`aircraft.closure`, sem `mass_kg` nem `mass_ledger`; ver
[tutorial-vtol.md](tutorial-vtol.md)) o VTOL passa a "rubber": o MTOW é resolvido por componentes para
a permanência de projeto, a capacidade é procurada a MTOW/bateria fixos e `n1.vtol_mass_closure` regista
estado, MTOW, resíduo, iterações e bateria instalada. A carga útil da amostra entra no MTOW (já não é
só margem de alocação). Exemplo `examples/fleet/iter_vtol_closure.yaml`: MTOW 9,766 kg, bateria
2,403 kg (limitada por potência), T_max 0,211 h, frota 24 → 8 (pedida → máxima derivada), energia
69,7 → 266,6 Wh — números PRESSUPOSTO.
A frota é aritmética direta da surtida fechada: com recursos dedicados não existe
dependência frota→projeto, por isso não há laço exterior (`convergence.fleet_feedback`).

Exemplos executáveis (dados PRESSUPOSTO): `examples/fleet/iter_*.yaml` e
`PYTHONPATH=src python examples/fleet/check_iterative.py`.

**Ainda pendente:** otimização da velocidade de loiter, vento, limite de volume de tanque
(o jato usa o combustível do fecho), reservas regulamentares e simulador dinâmico jato/VTOL.
Recursos partilhados: ver esquema 1.2 abaixo.

## Esquema 1.2 — recursos de solo partilhados e filas (9 nov 2026)

`schema_version: "1.2"` = 1.1 + blocos opcionais. Com recursos partilhados:

```yaml
operations:
  ground_resources: {source: "...", pools: {charger: 3, crew: 1}}   # contagens explícitas, sem omissão
candidates:
  - ground_process:            # substitui turnaround (não ambos)
      source: "..."
      activities:              # em série, pela ordem dada
        - {id: post_flight_check, resource: crew, duration_h: 0.05}
        - {id: charge, resource: charger, duration: charge, average_input_W: 1000, efficiency: 0.9}
        - {id: refuel, resource: fuel_truck, duration: refuel, flow_kg_h: 600}   # combustível da surtida
```

Método: simulação de eventos discretos com avanço ao próximo evento (Law 2015, Cap. 1–2) de um
calendário periódico de lançamentos (um a cada `on_station − overlap` por estação; estações
desfasadas uniformemente — PRESSUPOSTO), frota partilhada entre estações e filas FIFO por recurso.
Estabilidade exige ρ_r = λ·d_r/c_r < 1 (Kleinrock 1975); se não, `resource_saturated` com
`minimum_stable_counts`. Cota inferior da frota pela lei de Little (L = λW, Little 1961); a frota
sobe um avião de cada vez enquanto houver lançamentos falhados (`operations.history`), até zero
falhas e tempos de solo estáveis na segunda metade do horizonte. Disponibilidade/confiança
aplicadas como no modelo homogéneo (ceil(k/A) ou k-de-N).

Interpretação honesta: com calendário fixo, a espera depende dos recursos e do calendário, não de N;
N atua através de lançamentos falhados. Num único tipo com chegadas regulares e ρ<1 a espera é zero
(D/D/c); esperas surgem com chegadas irregulares (tipos mistos, serviços diferentes).

Exemplo `examples/fleet/shared_vtol.yaml` (2 estações, 3 carregadores de 1 kW, 1 equipa; PRESSUPOSTO):
permanência pedida 0,02 h → carregadores saturados (ρ = 2,58, mínimo 8); permanência máxima derivada
0,211 h → ρ_carregador 0,936, ρ_equipa 0,474, espera 0, 6 aviões no ciclo, frota 7 (A = 0,9).
Com 2 carregadores: `infeasible` (`resource_saturated:charger`).

Limites: sem filas estocásticas (Erlang/M/M/c), avarias, prioridades, deslocação entre placas,
curvas de carga ou dispatch dinâmico; recursos por candidato (homogéneo), exceto em `mixed_fleet`.

### Frotas mistas (`mixed_fleet`, 1.2)

```yaml
mixed_fleet:
  source: "..."
  members: [elétrico, VTOL-fecho-massa]     # ids de candidatos declarados (2..6)
  max_types: 2                              # tipos por combinação (≤4)
  shared_ground: true                       # uma DES para todos (exige ground_process em todos)
  min_stations_by_type: {VTOL-fecho-massa: 1}   # requisito explícito (p. ex. estação sem pista)
  objectives: {fleet_required: min, fleet_mtow_kg: min, energy_rate_Wh_per_h: min}
```

Cada estação é servida por um só tipo, com a linha de permanência escolhida na avaliação homogénea
desse tipo (mesma amostra). Enumeram-se todos os subconjuntos até `max_types` e todas as
repartições positivas das `n_stations` (limite 512). Métricas: frota total (sobressalentes por tipo,
ceil(k/A) ou k-de-N), MTOW da frota, energia e combustível por hora de cobertura
(Σ estações·consumo da surtida/intervalo de lançamento; portador não usado = zero conhecido;
ambos desconhecidos → por avaliar). Resultado: conjunto de Pareto, sem vencedor.
Membros não elegíveis ficam em `excluded_members`, nunca entram como zero.

Exemplo `examples/fleet/mixed_vtol_fixed_wing.yaml` (3 estações, 4 carregadores de 2 kW, 2 equipas,
uma estação exige VTOL; PRESSUPOSTO): elétrico×3 viola o requisito; elétrico×2+VTOL×1 → frota 12
(7 + 5), MTOW da frota 251,8 kg, 4249 Wh/h; elétrico×1+VTOL×2 → 13, 298,3 kg, 5689 Wh/h;
VTOL×3 → 13, 326,8 kg, 7130 Wh/h. Pareto: elétrico×2+VTOL×1.

### Despacho híbrido L0 e fases comuns (1.2)

Candidato `recipe: {model: hybrid, aircraft: {hybrid: {...}}}` (sem `onboard`; carga hotel por
`hotel_power_W`). Blocos obrigatórios com fonte: `aero {LD, eta_prop}`, `engine {rated_power_W,
bsfc_kg_per_kWh}`, `generator {efficiency}` (série), `motor {rated_power_W, efficiency}`,
`battery {capacity_Wh, soc_initial, soc_min, soc_max, c_rate_max, charge_efficiency,
discharge_efficiency}`, `fuel {capacity_kg}`, `dispatch {rule, ...}`, `phases {taxi_out, takeoff,
climb {altitude_m, rate_m_s, speed_m_s}, descent, landing, taxi_in}`.

Regras (Guzzella & Sciarretta 2013, Cap. 8, estratégias heurísticas): série `thermostat` (gerador ao
set-point com SOC ≤ soc_on até SOC ≥ soc_off), série `load_following` (gerador segue a procura até à
potência nominal), paralelo `power_split` (motor térmico até à potência nominal, motor elétrico o resto;
`electric_only_phases`). Integração no tempo (`dt_s`, 30 s por omissão PRESSUPOSTO), peso constante no
MTOW (conservador). Verificações: SOC mín./máx., taxa C, potências nominais, capacidade de combustível —
falha é falha, nunca omissão. Energia de recarga em terra = (SOC inicial − SOC final)·capacidade.

`n1.mission_phases` regista, para as fases canónicas (táxi, descolagem, subida, trânsito, estação,
regresso, descida, aterragem, táxi, reserva), como cada adaptador as representa (`flown`, `allowance`
Raymer/energia nativa, `lumped:<fase>`, `not_applicable`, `not_modeled`). Com
`mission.required_phases`, uma fase exigida `not_modeled` torna o candidato `unassessed`.

Exemplo `examples/fleet/hybrid_dispatch.yaml` (PRESSUPOSTO): série termóstato → combustível 0,317 kg,
SOC 0,90 → 0,696 (mín. 0,498), recarga 61,1 Wh, frota 5, T_max 4,33 h; paralelo → 0,247 kg,
recarga 71,0 Wh, frota 5, T_max 2,89 h (Pareto com objetivos frota/combustível); elétrico de asa fixa →
`unassessed` (táxi, descida, aterragem não modelados no pointmass).
