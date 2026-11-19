# Custo do ciclo de vida e pegada de CO₂e — disciplina `ciclo_vida` (L0)

Etapa `life_cycle` do pipeline de aeronaves (depois de `series_cost`; só corre se houver
`assumptions.life_cycle` ou um requisito de ciclo de vida) e funções `acdt.api.life_cycle_cost`,
`life_cycle_emissions` e `present_value` (API 1.7.0). Núcleo genérico em `acdt.core.lcc` (`discount`, `lcc`,
`environment`), sem dependência de aeronaves.

## 1. Métodos e fontes

| grandeza | equação | fonte |
|---|---|---|
| categorias | LCC = RDT&E + investimento (produção) + O&S + abate − valor residual | OSD CAPE, *Operating and Support Cost-Estimating Guide* (2020) §2.1 |
| atualização | LCC = Σ_t C_t / (1+d)^t (montantes no fim do ano; ano 0 = data base) | NIST Handbook 135 (Fuller & Petersen, ed. 1995) Eq. 5.1 |
| fator único | SPV = 1/(1+d)^t | idem Tabela 3-1, Eq. 3.6 |
| fator uniforme | UPV = [(1+d)^n − 1] / [d (1+d)^n] | idem Eq. 3.8 |
| uniforme com escalada | UPV* = (1+e)/(d−e) · [1 − ((1+e)/(1+d))^n] (A_t = A_0 (1+e)^t) | idem Eq. 3.9 |
| taxa real ↔ nominal | d = (1+D)/(1+I) − 1; D = (1+I)(1+d) − 1 | idem Eq. 3.11/3.13 |
| CO₂ de combustão | massa de combustível × FCF; FCF 3,16 kg CO₂/kg (Jet-A/Jet-A1), 3,10 (AvGas/Jet-B) | ICAO Anexo 16 Vol. IV (CORSIA), Parte II Cap. 2, 2.2.3 |
| CO₂e do poço à esteira | massa × PCI × LC; LC 89 gCO₂e/MJ (jet), 95 (AvGas) | valor de referência CORSIA do ciclo de vida do combustível fóssil |
| PCI | Jet A 42,8 MJ/kg (ASTM D1655), avgas 43,5 MJ/kg (ASTM D910) — mínimos da norma (PRESSUPOSTO) | `core/thermal/sources.py` |
| eletricidade | E_rede = E_bateria / η_carga; CO₂e = E_rede × intensidade **declarada** pelo utilizador (intervalo) | — (sem valor por omissão) |
| fabrico de baterias | 61–106 kg CO₂e/kWh (NMC, veículos ligeiros, materiais virgens, reciclagem excluída) | Emilsson & Dahllöf (2019), IVL Report C 444 |

O fator IVL é para baterias de veículos; aplicá-lo a uma bateria de aeronave é **PRESSUPOSTO** (fica na saída).
Pode declarar-se outro intervalo com `battery_footprint: {lo, hi, source}`.

## 2. Calendário (PRESSUPOSTOS declarados na saída)

* RDT&E repartido por igual pelos anos 1..`rdte_years` (0 → na data base).
* Produção a `production_rate_per_year` aeronaves/ano a partir do ano seguinte (por omissão, toda a frota num ano).
* Cada aeronave entregue no ano y voa nos anos y+1..y+L (L = `service_life_years`) e é abatida no fim do ano y+L.
* O&S anual = aeronaves ativas × FH/ano × custo/FH × (1+e)^t.

## 3. Entradas (`assumptions.life_cycle`)

Cada valor pode ser um número, `{lo, hi}` ou `None` (desconhecido).

| chave | significado | origem por omissão |
|---|---|---|
| `fleet_size` | n.º de aeronaves | quantidade de `series_cost` (PRESSUPOSTO) |
| `service_life_years` | vida útil (anos) | obrigatório |
| `production_rate_per_year`, `rdte_years` | calendário | frota num ano; 0 |
| `rdte_USD`, `unit_production_cost_USD` | RDT&E e produção por aeronave | `series_cost` (ferramentas + recorrente, sem margem) |
| `cost_per_fh_USD` | O&S por hora de voo | declarado → `reliability.operating_cost` → `life_cycle.operating_cost` (Raymer DOC); a depreciação é sempre retirada (a aquisição já está na produção) |
| `fh_per_aircraft_per_year` | utilização | `flight_hours_per_year` do custo operacional |
| `disposal_per_aircraft_USD`, `residual_per_aircraft_USD` | fim de vida | abate desconhecido; residual 0 (conservador) |
| `discount_rate`, `escalation_os` | taxa real e escalada real do O&S | sem taxa → só dólares constantes, VP desconhecido |
| `environment` | `fuel`, `fuel_kg_per_fh`, `lhv_MJ_kg`, `battery_kWh_per_fh`, `charge_efficiency`, `grid_intensity_kgCO2e_per_kWh`, `battery_capacity_kWh`, `battery_cycle_life`, `flights_per_fh`, `battery_footprint` | combustível/FH = Wf / duração da missão; energia/FH = energia de missão / duração (majorantes) |

## 4. Saídas

`constant_dollar_USD` e `present_value_USD` por categoria (`{lo, hi}`), `life_cycle_cost_USD` (VP se houver taxa,
senão dólares constantes, com `life_cycle_cost_basis`), `cost_per_flight_hour_USD`, `cost_per_mission_USD`,
`fleet_flight_hours`, fluxos anuais `cash_flows_lo/hi`, `environment` (CO₂e por FH, por missão, por aeronave e da
frota; `not_assessed`), `co2e_per_flight_hour_kg`, `life_cycle_co2e_kg`, `status` `completo`/`parcial` e
`adapter_notes` com a origem de cada entrada.

Intervalos: mínimo e máximo sobre os cantos das entradas em intervalo e uma grelha de 11 pontos da taxa. Uma
categoria de custo desconhecida dá minorante 0 e majorante **desconhecido**; um requisito `max` com majorante
desconhecido fica `desconhecido`, nunca `passa`.

## 5. Requisitos e integração

| requisito | dimensão | sentido | avaliador por omissão |
|---|---|---|---|
| `life_cycle_cost` | moeda | max | `ciclo_vida:life_cycle_cost_USD` |
| `life_cycle_cost_per_fh` | moeda | max | `ciclo_vida:cost_per_flight_hour_USD` |
| `co2e_per_flight_hour` | massa | max | `ciclo_vida:co2e_per_flight_hour_kg` |
| `life_cycle_co2e` | massa | max | `ciclo_vida:life_cycle_co2e_kg` |

Disciplina `ciclo_vida`/L0 no `design.json` (chaves `*_USD` em `USD_acdt`); métricas de UQ/MDO pelos caminhos
`life_cycle.*` (p. ex. `life_cycle.life_cycle_cost_USD.hi`).

```yaml
assumptions:
  series_cost: {quantity: 50, price: 60000}
  life_cycle:
    service_life_years: 10
    production_rate_per_year: 20
    rdte_years: 2
    fh_per_aircraft_per_year: {lo: 300, hi: 500}
    cost_per_fh_USD: {lo: 40, hi: 90}
    discount_rate: 0.05          # real
    environment:
      grid_intensity_kgCO2e_per_kWh: {lo: 0.1, hi: 0.4, source: "declarar a fonte"}
      charge_efficiency: 0.9
      battery_footprint: ivl_c444_2019
      battery_cycle_life: 400
requirements:
  life_cycle_cost: {max: 2.0e7, id: LC-01}
  co2e_per_flight_hour: {max: 5, id: LC-02}
```

## 6. V&V

| caso | referência | resultado |
|---|---|---|
| `LCC-NIST135-FACTORS` | NIST HB 135 Tabela 3-1 e Eq. 3.6–3.9: SPV(3 %, 15) 0,642; UPV 11,94; UPV*(2 %, 3 %, 15) 13,89; 862,61 $; 457,97 $; 485,62 $ | passa |
| `LCC-NIST135-RATES` | idem Eq. 3.12/3.14: 0,02885; 0,0712 | passa |
| `LCC-NIST135-EX51A` | idem Exemplo 5-1a: LCC 516 233 $ (fator FEMP UPV* 15,13 declarado) | passa (10⁻⁴ rel.) |
| `LCA-CORSIA-FCF` | ICAO Anexo 16 Vol. IV: 1 t Jet-A → 3160 kg CO₂; 1 t AvGas → 3100 kg | passa |

Testes: `tests/test_life_cycle.py` (cálculo à mão do VP com calendário, intervalos, desconhecidos, escalada,
residual, CO₂e elétrico e de baterias, API, pipeline com o UAV elétrico e o UAV a gasolina de exemplo — só como
casos de teste).

## 7. Limites e trabalho futuro

* Não avaliados (listados em `not_assessed`): fabrico da estrutura e dos motores, fim de vida, efeitos não-CO₂ em
  altitude. Não é uma ACV ISO 14040/44 completa.
* Fatores PV por item declarados só em `present_value` (não no calendário do programa).
* Custo de produção constante por aeronave (sem curva sobre o calendário); sem inflação diferencial por categoria
  além de `escalation_os`.

## 8. Adaptador nativo (19 nov 2026)

No VTOL, a energia por hora de voo é `energy_Wh` / duração quando o utilizador não declara `battery_kWh_per_fh`. Esse `energy_Wh` já inclui o hotel da carga ou da arquitetura, por isso não é somado outra vez. Se a potência da carga for desconhecida, `energy_complete` é falso e o majorante do CO₂e abre. Num jato ou num motor térmico não há modelo de extração: a potência elétrica do equipamento não entra no combustível e o CO₂e fica em aberto. Frota, vida e horas de voo não são inventadas. O veredicto só é `validado` quando o custo e o CO₂e fecham. Na asa fixa elétrica a energia do equipamento soma-se uma vez a `battery_kWh_per_fh` (PRESSUPOSTO: ciclo 1 durante a hora de voo), porque o dimensionamento ainda não a leu de `payload_equipment`. Medida de ensaio: `examples/output/adaptadores_vtol_jato/adaptadores.json`.
