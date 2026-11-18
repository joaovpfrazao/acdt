# Tutorial — Fase 7: fabrico e custo

A Fase 7 junta ao projeto dimensionado um **plano de fabrico por peça** e o **custo** da aeronave:

* o custo de baixo para cima (bottom-up), peça a peça;
* o custo de cima para baixo (top-down), com o Eastlake modificado e o DAPCA IV;
* a validação contra um preço público;
* uma frente de Pareto entre W0 e o custo.

Segue a regra de sempre: só métodos clássicos e citados, nunca números inventados, primeiro baixa fidelidade e
depois calibração.

**Materiais, componentes e preços são ENTRADAS com proveniência.** O agente de IA (ou o utilizador) pesquisa-os
na web e passa-os com `source_url`, a data `retrieved` e o `source_type`. O repositório guarda só uma base pequena
e citada de parâmetros de método: `src/acdt/domains/aircraft/manufacturing/refdata.py`.

## 1. Comandos

```bash
source /workspace/acdt_env.sh
# C172S: validação contra o preço de tabela + Pareto metal vs compósito
acdt manufacture examples/manufacturing/cessna172_manufacturing.yaml --pareto
# UAV 150 kg em compósito, série de 50: infusão (VARI) vs laminação manual
acdt manufacture examples/manufacturing/uav_composite_batch.yaml --pareto
```

Cada comando escreve os seguintes ficheiros em `output/<missão>_manufacturing/`:

* `manufacturing.json` e `manufacturing.md`: o relatório;
* os gráficos `cost_breakdown.png`, `process_options.png`, `unit_cost_vs_N.png`, `cost_levels.png` e
  `pareto_w0_cost.png`;
* `pareto.json` e `cost_calibration.json`.

Os resultados de referência estão em `examples/output/cessna172_manufacturing/` e
`examples/output/uav_gasoline_150kg_manufacturing/`.

Através do MCP há quatro ferramentas:

* `manufacturing_plan`: o estudo completo, como job;
* `cost_estimate`: Eastlake e DAPCA IV paramétricos (L0), curvas de aprendizagem e custo de operação
  (`operating` → DOC Raymer 2018 Cap. 18; ver também `systems-p4 ops-cost` / morph `operating_cost`). Devolve a
  confiança e a banda AACE Classe 5, e assinala `configuration`, `unmanned` e `propulsion` fora da base;
* `process_options`: as opções de processo de uma peça;
* `compare_materials`: comparação de materiais pelos índices de Ashby.

## 2. Configuração (`assumptions.manufacturing` ou `--config`)

```yaml
manufacturing:
  year: 2025                 # USD do estudo (CPI-U, BLS; 2026 = índice de set/2026, mensal)
  N: 820                     # quantidade de produção
  materials:                 # chave → {base: <chave da biblioteca>} ou {kind, rho, E, Ftu, t_min} + price
    al2024_t3:
      base: al2024_t3
      price: {usd_per_kg: 28.8, year: 2026,
              provenance: {source_url: "https://…", retrieved: "2026-10-28", source_type: distributor}}
  groups: {default: al2024_t3}            # material por grupo (wing, htail, vtail, fuselage)
  choices:                                # opções por peça/tipo/grupo/'*': materiais × processos
    "*": {materials: [...], processes: [...]}
  process_inputs:                         # por processo, 'peça:processo' ou '*'
    cnc_machining: {prices: {al2024_t3: {usd_per_kg: 25.1, year: 2026, provenance: {...}}}}
  labour_calibration: 1.0                 # número (dados da oficina) ou 'eastlake' (ver §4)
  tooling: eastlake                       # sem cotação: pool do Eastlake | dapca | none
  purchased: {engine: {usd: …, year: …}}  # componentes comprados (senão CER do Eastlake)
  final_assembly_hours: null              # montagem final/sistemas — entrada, não modelado
  validation: {price_usd: 499000, year: 2025, source: "…"}
  operating: {...}                        # costing.OperatingInputs (custo de operação)
  configuration: conventional             # ou lista de características não convencionais → L0 "fora da base"
  labour_calibration_source: null         # fonte de um labour_calibration numérico (oficina)
  detailed: {...}                         # L2: peças do projeto detalhado, BOM, cotações (§4)
  cost_calibration: {file: …, apply: [cost_L0, cost_L1]}   # fatores nível superior → inferior (§4)
```

## 3. Métodos

| bloco | método | fonte |
|---|---|---|
| horas por peça (metal, compósito) | modelo hiperbólico FOPV, t = √((x/V0)² + 2τx/V0), x = área (in²) ou perímetro; chapa rebitada usa o FOPV de metal como proxy (assinalado) | Gutowski et al. 1994; Bao & Samareh 2000; Bao 2002 Tab. 4.1 (verificado: longarina Al de 100 in² → 1732 min) |
| laminação de tecido | ACCEM 0.000851·A^0.6295 h por camada | Hagnell & Åkermo 2016 |
| enrolamento, FDM/SLS | taxas (kg/h, cm³/h) — **entradas** de datasheet da máquina | — |
| buy-to-fly | CNC 1/0.15 (Airbus: 10–20 % voa); chapa 2.0 (DAHER: retalhos 65→50 %); compósito 1.4 (1.1–1.4) | Airbus 2018; Alma/DAHER; Gonzalo et al. 2023 |
| rebites | D ≈ 3·t, passo 4–6 D (5 D por omissão), passo mínimo 3 D, margem 2 D | FAA-H-8083-31; AC 43.13-1B |
| regras de compósitos | sem rebites cravados, ply drops 20:1, margem 3 D | Abbott 2019 (MIL-HDBK-17F) |
| viabilidade | classe de material, envelope (molde/autoclave/máquina), espessura mínima, dupla curvatura em chapa (aviso), enrolamento só axissimétrico | idem |
| aprendizagem | Crawford (unidade) e Wright (média acumulada), 85 % por omissão | Crawford 1944; Wright 1936; NASA JSC |
| material alternativo | escala de massa pelos índices de Ashby (painel E^⅓/ρ, viga E^½/ρ, tirante σ/ρ) | Ashby 2011 |
| top-down | Eastlake modificado (USD 2012, fator 2.0969 1986→2012, f_comp) e DAPCA IV (USD 2012) | Gudmundsson 2014 Cap. 2; Raymer 2018 Cap. 18 |
| escalada | CPI-U, médias anuais | BLS |

Os processos de compósito (laminação manual, infusão, prepreg OOA/autoclave) partilham o FOPV genérico de
compósito. Distinguem-se pelas entradas: o laminado (Vf, ρ, E, preço), o ferramental, a cura e, se houver dados
de oficina, `V0`/`tau` próprios. Um material pode ficar preso à sua via de processo com `processes: [...]`.

## 4. Escada de fidelidade do custo (L0 → L1 → L2)

As CERs top-down (Eastlake, DAPCA IV; Roskam VIII seria do mesmo tipo) são regressões estatísticas: Eastlake
sobre aviação geral, DAPCA IV sobre aviões militares e de transporte. **Uma aeronave não convencional** (asa
voadora, BWB, VTOL, propulsão distribuída ou elétrica, não tripulada) **está fora dessas bases de dados**, e o
erro das CERs não tem limite conhecido. Por isso o custo segue a mesma escada de fidelidade do resto do acdt:

| nível | método | entradas | classe AACE 18R-97 (80 %) |
|---|---|---|---|
| **L0** | CERs top-down (Eastlake central, DAPCA IV como segunda CER; a dispersão entre as duas é reportada) | W_e, V_H, N, f_comp | Classe 5: −20…−50 % / +30…+100 % |
| **L1** | bottom-up paramétrico por peça e processo, a partir do projeto preliminar (decomposição em peças + FOPV/ACCEM, B2F, rebites, ferramental, aprendizagem) | geometria e massas dimensionadas, materiais com preço | Classe 4: −15…−30 % / +20…+50 % |
| **L2** | bottom-up detalhado, a partir do projeto detalhado | lista real de peças, geometria, nº de camadas, nº de fixadores, BOM com preços de fornecedor pesquisados, cotações, horas de oficina | Classe 3: −10…−20 % / +10…+30 % (Classe 2 só se tudo for cotado) |

Fonte das bandas: AACE International RP 18R-97, Tabela 1. Atenção: é uma classificação para indústrias de
processo, usada aqui por analogia, e a própria AACE diz que a banda vai para o extremo largo com complexidade
tecnológica e dados de referência fracos.

### 4.1 Posição dentro da banda (regra documentada, ASSUMPTION)

* **L0**: extremo estreito dentro da base de dados. Extremo largo se `configuration` for uma lista de
  características não convencionais, se a aeronave for não tripulada, se a propulsão não for pistão/turbo ou se
  houver `cer_outside_database_reasons`. A meio caminho depois de uma calibração `cost_L0`.
* **L1**: posição consoante a calibração das horas:
  * extremo largo com os parâmetros FOPV públicos ou com a ancoragem `labour_calibration: eastlake`; neste caso
    o L1 herda a confiança do L0 e a nota diz que a ancoragem vai ao contrário da escada;
  * meio com um fator de oficina (`labour_calibration` numérico + `labour_calibration_source`);
  * extremo estreito depois da calibração `cost_L1` vinda do L2.
* **L2**: posição = 1 − fração cotada do custo recorrente. Passa a Classe 2 quando todos os itens recorrentes são
  cotações.

### 4.2 Nível recomendado

* L2, se existir.
* Senão L1, se estiver calibrado (oficina ou L2) ou se as CERs estiverem fora da base de dados (caso das
  aeronaves não convencionais).
* Senão L0. É o caso de um projeto convencional dentro da base, com o L1 por calibrar. O L1 continua a servir
  para as escolhas relativas de processo e material.

### 4.3 Calibração (nível superior → inferior)

Os fatores ficam em `cost_calibration.json`, com o mesmo formato dos fatores aero/estrutura da Fase 4
(`group`, `value`, `hifi`, `lowfi`, `what`). Só são aplicados quando o grupo é pedido:

| fator | grupo | definição | onde atua |
|---|---|---|---|
| `k_cost_L0_eastlake`, `k_cost_L0_dapca4` | `cost_L0` | custo unitário do melhor nível bottom-up (L2, senão L1) / CER | multiplica a CER (só na vizinhança do projeto) |
| `k_labour_hours_L1` | `cost_L1` | horas L2 / horas L1 das peças emparelhadas | multiplicador de horas do plano L1 |
| `k_material_L1` | `cost_L1` | custo de material L2 / L1 das peças emparelhadas | multiplicador de material do plano L1 |
| `k_unit_cost_L1`, `per_part_L1` | `cost_L1` | custo L2 / L1, total e por peça | só reportado |

Regras da calibração:

* **Emparelhamento das peças**: pelo campo `l1_part` da peça L2; sem ele, por `grupo:tipo`.
* **Independência**: se o L1 estiver ancorado ao Eastlake, os fatores `cost_L0` ficam marcados
  `independent: false` e o acdt recusa aplicá-los.

```yaml
manufacturing:
  configuration: [blended wing body, distributed propulsion]   # → L0 assinalado "fora da base", banda larga
  labour_calibration: 0.42                                     # fator de oficina...
  labour_calibration_source: "time study, shop X, 2026-09"     # ...com fonte → L1 a meio da banda
  detailed:                                                    # L2 (ver src/acdt/domains/aircraft/manufacturing/detailed.py)
    parts:
      - {name: wing upper skin LH, l1_part: wing skin, group: wing, kind: skin, count: 1, material: cf_fabric_vari,
         process: vacuum_infusion, mass_kg: …, area_m2: …, perimeter_m: …, thickness_m: …, n_plies: …,
         fasteners: {count: …, usd_each: …, year: 2026, provenance: {…}}, labour_hours: …, tooling_cost: …}
      - {name: engine mount, l1_part: fuselage:fitting, kind: fitting, count: 1,
         quote: {usd: …, year: 2026, provenance: {source_url: …, retrieved: …, source_type: other}}}
    bom: [{item: engine, qty: 1, usd: …, year: 2026, quote: true, provenance: {…}}]
    final_assembly_hours: …
    final_assembly_rate_usd_h: …
    non_recurring_usd: …        # senão NRC do Eastlake (assinalado)
  cost_calibration: {file: ../output/<run>/cost_calibration.json, apply: [cost_L1, cost_L0]}
```

Os `…` são valores do projeto detalhado ou de cotações: o acdt não os fornece.

Fluxo:

1. Correr o L0 e o L1 (`acdt manufacture …`).
2. Quando houver projeto detalhado, juntar `detailed:` e correr outra vez. Sai o L2 e um `cost_calibration.json`
   novo.
3. Nos estudos seguintes do mesmo projeto (por exemplo variantes ou Pareto), usar
   `cost_calibration.apply: [cost_L1]` para o L1 correr ao nível do L2. Juntar `cost_L0` para as CERs.

Saídas:

* secção "Escada de fidelidade" no `manufacturing.md`;
* `fidelity` no JSON;
* `cost_levels.png`: estimativa, confiança e banda por nível, com o DAPCA IV e o preço público;
* `cost_calibration.json`.

## 5. Horas do L1 sem dados de oficina

Os parâmetros FOPV vêm de peças de asa de **avião de transporte**. Nas peças pequenas o tempo é dominado por τ
(x < 2τV0: o relatório avisa) e as horas saem altas.

Na C172 o modelo bruto dá 5166 h por avião (média sobre N = 820, LF = 0.27). O Eastlake dá 942 h de fabrico por
avião. Há duas saídas:

* **`labour_calibration: <k>`**: k medido na oficina. É o caminho certo.
* **`labour_calibration: eastlake`**: k = H_fabrico(Eastlake)/H(bottom-up bruto). As horas absolutas ficam as do
  Eastlake. O ranking relativo entre peças, processos e materiais continua a ser o dos modelos de processo. A
  validação bottom-up deixa de ser independente, por isso só serve para estudos comparativos. Esta ancoragem
  vai ao contrário da escada (L0 → L1): o L1 herda a confiança do L0. Numa aeronave não convencional é só um
  recurso provisório até haver horas de oficina ou um L2 (§4).

## 6. Validação — Cessna 172S (USD 2025, N = 820 = 5 anos × 164/ano)

Fontes:

* Entregas: GAMA, *2024 Year-End Shipment Report* (164 C172S em 2024).
* Preço de tabela: 499 000 USD (fliegermagazin, 2025-05-05).
* Alumínio 2024-T3: Aircraft Spruce, consultado em 2026-10-28.
  * Chapa 0.032" 4'×12' a 289 USD → 28.8 USD/kg.
  * Chapa grossa 0.250" a 1968 USD → 25.1 USD/kg.

| modelo | custo unitário | / preço público |
|---|---|---|
| Eastlake modificado | 280 909 USD | 0.56 |
| DAPCA IV | 793 595 USD | 1.59 |
| bottom-up (FOPV bruto, k = 1) | 691 875 USD | 1.39 |

Como ler estes valores:

* Os modelos dão **custo** do fabricante. Um preço de tabela soma margem, seguro de responsabilidade civil e
  distribuição, por isso espera-se uma razão < 1.
* O Eastlake, feito para aviação geral, fica nessa banda.
* O DAPCA IV foi ajustado a aviões militares e de transporte e sobrestima a aviação geral (razão > 1).
* O bottom-up sobrestima por causa do FOPV de transporte em peças pequenas (§5).

Escada de fidelidade:

* **L0**: Eastlake 280 909 USD. Confiança média, porque é um projeto convencional de aviação geral, dentro da
  base. Banda Classe 5 no extremo estreito: 224 727 – 365 181 USD.
* **L1**: 691 875 USD. Confiança baixa a média: FOPV público, sem calibração de oficina. Banda Classe 4:
  484 313 – 1 037 813 USD.
* **Nível recomendado: L0**, por ser convencional e o L1 não estar calibrado. O L1 serve para as escolhas
  relativas.
* A dispersão Eastlake/DAPCA IV é de 2.83×.
* `k_cost_L0_eastlake` = 2.46 (L1/L0). Fica reportado, mas não deve ser aplicado enquanto o L1 não for
  calibrado.

Escolhas de processo (a mais barata viável a N = 820):

* Revestimentos, longarinas e nervuras da asa, revestimentos de cauda, casca e cavernas da fuselagem: chapa
  rebitada.
* Longarinas e nervuras finas da cauda: CNC.

Pareto (L0, W/S × AR × {metal, compósito}): duas soluções não dominadas no ponto W/S 730 N/m², AR 6.5.

| opção | W0 | custo bottom-up |
|---|---|---|
| metal | 1172 kg | 701 k USD |
| compósito (tecido CF/epóxi por infusão; pesos com fatores de compósito) | 1117 kg | 918 k USD |

## 7. Exemplo — UAV 150 kg em compósito, série de 50 (USD 2025)

Laminados de tecido de carbono/epóxi do mesmo estudo (Suranaree J. Sci. Technol., artigo 12583):

| laminado | Vf | ρ | E | Ftu | preço (Aircraft Spruce) |
|---|---|---|---|---|---|
| VARI | 45 % | 1452.5 kg/m³ | 35.63 GPa | 268.3 MPa | 93.3 USD/kg |
| laminação manual | 23 % | 1191 kg/m³ | escalado por Vf (pressuposto) | escalado por Vf (pressuposto) | 71.1 USD/kg |

Os preços combinam o tecido 282 3K (142.5 USD/kg) e a resina Aeropoxy (≈34.3 USD/kg) pela fração mássica de
fibra.

Resultados com `labour_calibration: eastlake` (k = 0.122):

| modelo | custo unitário |
|---|---|
| bottom-up | 184 815 USD (estrutura 121 049 + motor + aviónica + não recorrente/N) |
| Eastlake | 247 064 USD |
| DAPCA IV | 463 559 USD |

O Eastlake e o DAPCA são extrapolados fora da base de dados (aviação geral tripulada).

Escada de fidelidade:

* **L0**: Eastlake 247 064 USD. Confiança **baixa**: aeronave não tripulada, fora das bases das CERs. Banda
  Classe 5 no extremo largo: 123 532 – 494 129 USD.
* **L1**: 184 815 USD. Confiança baixa, porque as horas estão ancoradas ao Eastlake. Banda Classe 4:
  129 370 – 277 222 USD.
* **Nível recomendado: L1.**
* Os fatores `cost_L0` ficam marcados como não independentes.
* O passo seguinte é fazer o L2 quando existir o projeto detalhado: lista de peças, cotações dos moldes e do
  motor, horas de oficina.

Peça a peça, a escolha é a laminação manual, porque o material é mais barato e as horas FOPV são iguais. Essa
escolha **acrescenta +0.74 kg** de estrutura (Ashby).

No Pareto essa massa é realimentada no fecho de W0 (com efeito bola-de-neve). Aí a **infusão domina**:

| opção | W0 | custo |
|---|---|---|
| infusão (W/S 594, AR 12.8) | 135.8 kg | 182 787 USD |
| laminação manual (mesmo ponto) | 137.4 kg | 183 067 USD |

## 8. Limitações

* **Roskam Parte VIII** não está implementado: não foi possível verificar as equações na fonte.
* **FOPV**: os parâmetros são de peças de transporte e sobrestimam peças pequenas, por isso é preciso calibrar
  (§5). Os processos de compósito não se distinguem em horas sem dados próprios.
* **Gudmundsson**:
  * Fatores de compósito: os de engenharia, ferramental e fabrico foram verificados (RWTH); os de
    desenvolvimento e QC (1 + 0.5 f) não.
  * Hélice de passo fixo: a expressão não foi verificada (a de passo variável foi).
* **Preços**: são preços de retalho (um OEM paga menos) e de 2026, escalados para 2025 com o CPI. O CPI de 2026 é
  um índice mensal.
* **Decomposição em peças**:
  * gauge uniforme por face;
  * profundidade das cavernas 5 % do diâmetro (pressuposto sem fonte);
  * ferragens só por entrada do utilizador.
* **Fora do modelo bottom-up**: montagem final, instalação de sistemas, pintura e ensaio (são entradas).
* **Não recorrente**: engenharia, desenvolvimento e ensaio em voo vêm do Eastlake.
* **Bandas de incerteza**: as classes AACE 18R-97 são da indústria de processo (por analogia). A posição dentro
  da classe segue uma regra documentada, não um ajuste estatístico a custos aeronáuticos reais.
* **L2**: o mecanismo está testado com um caso sintético. Ainda não há um exemplo com dados reais: precisa do
  projeto detalhado e de cotações. As peças L2 sem cotação usam os mesmos modelos de processo do L1, aplicados à
  geometria real.
* **Pareto**: é um varrimento em grelha L0 (aero handbook, sem calibração low-fi), não um otimizador
  multiobjetivo. É auditável ponto a ponto.
