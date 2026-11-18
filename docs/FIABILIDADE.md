# Fiabilidade e manutenção de frota (disciplina `fiabilidade`, L0)

Estado em 18 nov 2026 (ramo `disc-fiabilidade`). Código: `acdt/core/reliability/` (núcleo, domínio-agnóstico, mypy
estrito), `acdt/domains/aircraft/reliability.py` (etapa `reliability` do pipeline) e `acdt.api.reliability` /
`acdt.api.availability` / `acdt.api.spares_stock` (desde a API 1.5.0).

Reutiliza o que já existia: a base de taxas `core/data/failure_rates.yaml` e as taxas de fornecedor com fonte e data
(`acdt.core.safety.rates`, usadas pelo ARP4761/SORA), o k-de-n binomial e a disponibilidade de
`acdt.core.concept` (`reliability.k_of_n`, `ops.availability`), a frota homogénea de
`acdt.core.concept.fleet_feedback.fleet` (ciclo de Ha 2010) e o custo operacional por hora de voo de
`manufacturing.costing.operating_cost` (estrutura DOC de Raymer 2018 Cap. 18, preço Eastlake/DAPCA).

## 1. O que faz

* **Taxas de avaria com proveniência** por componente: fornecedor (λ ou MTBF com `source` e `retrieved`), base
  pública (`rate_key`, entradas `published`/`vendor_claim`) ou valor/intervalo declarado com `source`. Sem fonte →
  **desconhecido** (nunca um número inventado). As entradas `kind: assumption` da base só entram com
  `accept_assumptions: true` e ficam marcadas como PRESSUPOSTO.
* **RBD** (diagrama de blocos de fiabilidade): série, paralelo ativo, k-de-n (unidades idênticas ou diferentes) e
  caminhos mínimos para estruturas que não são série-paralelo. **Fiabilidade de missão** R(t_missão) e **MTBCF**
  (modelo com redundâncias) e **MTBF básica** (todas as unidades em série: procura de manutenção e logística).
* **Manutibilidade**: M_ct ponderado pelas taxas, tarefas preventivas (por horas de voo ou calendário), MTBM, M̄,
  **MMH/FH** (homens-hora diretos por hora de voo).
* **Disponibilidades** intrínseca A_i, atingida A_a e operacional A_o (com tempos logístico, administrativo e de
  prontidão).
* **Sobressalentes** por Poisson: procura da frota durante o tempo de reabastecimento → stock para o nível de proteção
  declarado e o seu custo.
* **Dimensão da frota** para sustentar uma cobertura contínua (n estações) ou uma taxa de surtidas, dada a
  disponibilidade operacional, a fiabilidade de missão e o tempo de solo.
* **Custo de manutenção por FH** (mão de obra = MMH/FH × taxa; peças = Σ λ × custo de substituição) que alimenta o
  custo operacional existente.
* **Integração**: etapa `reliability` do pipeline (depois do gelo, antes do relatório), secção `reliability` no
  `result.json`, disciplina `fiabilidade`/L0 no `design.json`, requisitos `mission_reliability`, `mtbcf`, `mtbf`,
  `operational_availability`, `maintenance_man_hours_per_fh`, `fleet_size`, avaliador `fiabilidade:` na matriz de
  verificação, métricas para UQ/MDO pelos caminhos `reliability.*`, ganchos na frota
  (`fleet_feedback.fleet` aceita `availability: {reliability: …}`) e no morfológico
  (`operating_cost.reliability`), cinco casos V&V.

## 2. Métodos e fontes (cada equação conferida com a fonte)

Fonte principal: **MIL-HDBK-338B**, *Electronic Reliability Design Handbook* (DoD, 1 out. 1998), distribuição A
(pública).

| Peça | Método | Fonte |
|---|---|---|
| Lei de avarias | R(t) = e^{−λt}; taxa constante | MIL-HDBK-338B Eq. 5.57 |
| Série / paralelo ativo | P_S = Π P_i; P_S = 1 − Π(1 − P_i) | Eq. 6.20–6.27 |
| Estrutura geral | P_S = P_S(X bom) R_X + P_S(X mau) Q_X; aqui enumeração exata dos estados dos caminhos mínimos (equivalente) | Eq. 6.19, exemplo Eq. 6.30 |
| k-de-n | soma binomial P(k, n, p) (idênticas); Poisson-binomial (diferentes) | §7.5.5.1; `acdt.core.concept.reliability.k_of_n` |
| MTTF / MTBCF | ∫₀^∞ R(t) dt (integração numérica por troços, `scipy.integrate.quad`) | Eq. 5.73; definição de MTBCF na Secção 3 |
| Paralelo idêntico | MTTF = (1/λ) Σ_{i=1..n} 1/i (+50 % com o primeiro redundante) | §7.5.5, Fig. 7.5-9 |
| Básica vs missão | MTBF básica = 1/Σ λ de todas as unidades; missão = modelo com redundâncias | §6.4.2–6.4.3 |
| M_ct | Σ λ_i M_ct,i / Σ λ_i | Eq. 5.75 |
| MTBM | 1/(λ + f) (corretivas + preventivas) | §10.4.1.1 (após a Eq. 10.21) |
| M̄ | (λ M_ct + Σ f_j M_pt,j)/(λ + f) — mesma ponderação da Eq. 5.75 | §10.4.1.1 (definição de M̄) |
| A_i | MTBF/(MTBF + MTTR) | Eq. 10.18 (`ops.availability`) |
| A_a | MTBM/(MTBM + M̄) | Eq. 10.21 |
| A_o | (MTBM + RT)/(MTBM + RT + MDT), MDT = M̄ + logístico + administrativo | Eq. 10.22 |
| A_AV(T) | μ/(λ+μ) + λ/(T(λ+μ)²)(1 − e^{−(λ+μ)T}) (unidade exponencial; só na API/V&V) | Eq. 10.24 |
| MMH/FH | Σ frequência × homens-hora por ação (corretivas λ_i, preventivas f_j) | definição de DMMH/MA, Secção 3 |
| Sobressalentes | menor S com Σ_{x≤S} aˣe^{−a}/x! ≥ c, a = λ × horas de voo da frota × tempo de reabastecimento | Eq. 5.55–5.58, §5.3.8.1 |
| Frota por cobertura | ciclo de Ha (2010) e frota ⌈k/A⌉ (ou k-de-N com confiança) com A = A_o | `fleet_feedback.fleet` (Ha 2010, AFIT-OR-MS-ENS-10-03) |
| Frota por surtidas | N = ⌈lançamentos (t_s + t_solo)/(A H_op)⌉, lançamentos = surtidas/R_missão | balanço de tempo (identidade); PRESSUPOSTOS abaixo |
| Custo de manutenção | mão de obra + peças por FH no custo operacional | `manufacturing.costing.operating_cost` (Raymer 2018 Cap. 18) |

Nota: no Exemplo 3 do §10.4.1.1 o manual soma M_ct + M_pt (0,5 + 0,25 h) em vez de ponderar pelas frequências. O
código pondera (como manda a definição de M̄ e a Eq. 5.75); o caso V&V reproduz o exemplo dando M̄ diretamente.

## 3. Completude: desconhecido ≠ zero, não avaliado ≠ passa

* Todas as saídas são intervalos `{lo, hi}`. Uma taxa declarada como intervalo propaga-se de forma monótona
  (R_lo usa λ_hi; MTBF_lo usa Σ λ_hi).
* **Taxa desconhecida**: nunca vale zero. No RBD o bloco entra com R = 0 no minorante e R = 1 no majorante (limites
  válidos); a MTBF básica fica só com majorante; MMH/FH, MTBM e A_o ficam sem minorante/majorante conforme o caso.
* MTTR em falta num componente → M_ct, M̄ e as disponibilidades ficam desconhecidos (o tempo de reparação não tem
  limite natural). MMH em falta → MMH/FH só com minorante. Custo de substituição em falta → peças/FH só com
  minorante, e o custo operacional fica `partial` (sem `per_flight_hour`).
* Tempos logístico e administrativo não declarados → A_o só com majorante (atrasos ≥ 0); a frota fica só com
  minorante; requisitos `min` de A_o nunca passam por omissão.
* Sem componentes declarados → a etapa fica «não avaliada» e todos os requisitos de fiabilidade «não avaliado».
* Os limites de disponibilidade tratam MTBF e MTTR como independentes (limites exteriores, conservadores).

## 4. Pressupostos (PRESSUPOSTO) e limites

* Taxas constantes (zona plana da curva da banheira), avarias independentes (sem causa comum), redundância **ativa**
  sem comutação, sem reparação durante a missão. Redundância em espera (fria/quente) e comutadores não modelados.
* λ por hora de funcionamento × `duty` (horas de funcionamento por hora de voo, omissão 1: o componente funciona em
  todo o voo). Base temporal: horas de voo.
* `n` = unidades idênticas em série no mesmo bloco; um id não se repete na árvore fora de `paths` (independência).
* Frota por surtidas: uma surtida abortada ocupa o ciclo inteiro e é repetida (`abort_reflight`, conservador);
  `operating_hours_per_day` omissão 24 h (declarar o turno real). Na cobertura, os abortos não são contados.
* Sobressalentes: procura estacionária, stock reposto ao fim do tempo de reabastecimento, sem reparação local.
* `flight_hours_per_year` do custo operacional, quando não é dado, vale 365 × FH/aeronave/dia (operação todo o ano).
* A base `failure_rates.yaml` tem poucas entradas públicas (NASA GARS, ATSB) e várias PRESSUPOSTO; para um projeto
  real as taxas devem vir do fornecedor (com fonte e data).

## 5. Uso

### 5.1 No pipeline (`assumptions.reliability` da missão)

```yaml
assumptions:
  reliability:
    components:
      - {id: motor, supplier: {mtbf_h: 3000, source: "Fornecedor X, carta 12/2026", retrieved: "2026-12-01"},
         mttr_h: 1.0, mmh_per_action: 1.5, replacement_cost: 400}
      - {id: servo, rate_key: uav_servo, mttr_h: 0.5, mmh_per_action: 0.75, replacement_cost: 250}
      - {id: gnss, lambda_per_h: {lo: 1.0e-4, hi: 3.0e-4}, source: "datasheet Y rev. C", mttr_h: 0.5}   # sem MMH nem custo → MMH/FH e peças/FH só com minorante
    rbd: {type: series, blocks: [motor, gnss, {type: k_of_n, k: 3, n: 4, block: servo}]}
    preventive: [{id: inspecao_50h, interval_fh: 50, duration_h: 1.0, mmh: 2.0, source: "plano de manutenção"}]
    logistics: {mean_logistic_delay_h: {lo: 2, hi: 24}, mean_admin_delay_h: 1.0, ready_time_h: 0}
    fleet: {mode: sorties, sorties_per_day: 2, turnaround_h: 1.0, operating_hours_per_day: 12}
    #   ou {mode: coverage, n_stations: 1, on_station_h: 4, transit_h: 1, turnaround_h: 2, handoff_overlap_h: 0.25}
    spares: {resupply_days: 30, confidence: 0.9}
    operating_cost: {unit_price: 30000, maintenance_rate_per_h: 50, depreciation_years: 5}
requirements:
  mission_reliability: {min: 0.99, id: RL-01}
  operational_availability: {min: 0.8, id: RL-02}
  maintenance_man_hours_per_fh: {max: 0.5, id: RL-03}
  fleet_size: {max: 4, id: RL-04}
  mtbcf: {min: 500, unit: h, id: RL-05}
```

Duração da missão: `mission_duration_h`, ou a soma dos segmentos da missão exigida, ou o requisito `endurance`.
`fleet.sortie_duration_h` em falta → duração da missão (também na API genérica, com `mission_duration_h`).

Avaliadores: `fiabilidade:mission_reliability`, `fiabilidade:mtbcf_s`, `fiabilidade:mtbf_s`,
`fiabilidade:operational_availability`, `fiabilidade:maintenance.mmh_per_fh`, `fiabilidade:fleet_size` (omissões dos
requisitos acima) e qualquer grandeza da secção, p. ex. `fiabilidade:availability.inherent`. UQ e MDO:
`result_metrics: {R_missao: reliability.mission_reliability.lo, Ao: reliability.operational_availability.lo,
frota: reliability.fleet_size.hi}` ou `req:<ID>`.

### 5.2 Especificação genérica (`acdt.api`) — qualquer tipo de aeronave ou sistema

```python
from acdt import api
r = api.reliability({"mission_duration_h": 2.0, "components": [...], "rbd": {...}, "fleet": {...}})
api.availability(mtbf_h=100, mttr_h=0.5, mtbm_h=75, m_bar_h=0.75, mdt_h=1.45, ready_time_h=20)
api.spares_stock(lambda_per_h=0.001, hours=500, confidence=0.98)   # → stock 2 (MIL-HDBK-338B §5.3.8.1)
```

### 5.3 Ganchos

* **Frota** (`acdt fleet study`, `fleet_feedback.fleet`): `operations.availability: {reliability: <espec.>}` usa o
  minorante de A_o calculado aqui; A_o desconhecido → erro explícito (declare taxas, MTTR e atrasos).
* **Morfológico** (`acdt morph evaluate --systems`, bloco `operating_cost`): `operating_cost.reliability: <espec.>`
  preenche `maintenance_mmh_per_fh` e `maintenance_parts_per_fh` (majorantes); se algum for desconhecido o custo
  operacional fica `unassessed` (nunca zero).
* **Custo operacional** no pipeline: `reliability.operating_cost` (mesmo bloco de `manufacturing.costing`).

Sem acoplamento ao dimensionamento: neste nível a fiabilidade não muda o W0 (a massa de redundâncias entra pelos
blocos de sistemas/massas como hoje).

## 6. V&V (`acdt vv --discipline fiabilidade`)

| Caso | Referência | Calculado | Tolerância |
|---|---|---|---|
| FIAB-338B-AVAIL-EX3 | MIL-HDBK-338B §10.4.1.1 Ex. 3: A_i 0,995, A_a 0,99, A_o 0,985 | 0,99502; 0,99010; 0,98497 | 3 casas (A_a 2 casas) |
| FIAB-338B-AAV-EX4 | §10.4.1.2 Ex. 4: A_AV(1 h) 0,9972 | 0,99716 | 4 casas |
| FIAB-338B-POISSON-5381 | §5.3.8.1: R(500 h) com 2 reservas 0,986; stock para 98 % = 2 | 0,98561; 2 | 3 casas; exato |
| FIAB-338B-EQ630 | §6.4.4.2.1.3, Eq. 6.30: P_S = 0,13572 | 0,13572 | 5×10⁻⁶ |
| FIAB-338B-PARALLEL-MTBF | §7.5.5 e Fig. 7.5-9: +50 % com o 1.º redundante, ΔM₃ 0,33 | 1,500000; 0,3333 | 10⁻⁶ rel.; 2 casas |

Testes: `tests/test_reliability.py` (V&V, k-de-n diferente, validação do RBD, regras de proveniência das taxas,
valores em forma fechada do estudo — MTBF básica, R de missão k-de-n, M_ct, MTBM, M̄, MMH/FH, A_o —, desconhecidos
como limites, frota por surtidas e cobertura contra `fleet_feedback`, sobressalentes, custo operacional parcial,
gancho morfológico, API e pipeline com requisitos e `design.json`).

## 7. Exemplo de teste (não altera o projeto)

`examples/uav_endurance_payload.yaml` com componentes de teste (motor e ESC com intervalos declarados como «teste»,
servo `uav_servo` da base, FCC `uav_flight_computer`, alternador de referência fora do RBD), inspeção a cada 25 FH,
atrasos logísticos 2–24 h, 2 surtidas/dia em turno de 12 h:

* Com a FCC só da base (`kind: assumption`, não aceite): R_missão [0, 0,99944], MTBF básica só com majorante (429 h),
  A_o só com majorante (0,856), frota ≥ 1, custo operacional `partial` — a FCC desconhecida não passa a zero.
* Com `accept_assumptions: true` (PRESSUPOSTO assinalado): missão 2,73 h (soma dos segmentos), R_missão
  0,9975–0,9992, MTBCF 632–918 h, MTBF básica 330–411 h, M_ct 0,56–0,63 h, MTBM 23,2–23,6 FH, MMH/FH 0,042–0,043,
  A_i 0,998, A_a 0,960, A_o 0,47–0,86 (dominado pelo atraso logístico), frota 1–2, servos: 1 sobressalente para 90 %
  em 30 dias. Peças/FH só com minorante (o alternador de referência não tem custo declarado) → custo operacional
  `partial`.

## 8. Seguimentos

* Redundância em espera (fria/quente) com comutador (MIL-HDBK-338B §7.5.5.3) e reparação durante a missão (Markov).
* Missões por fases (RBD diferente por fase) e taxas por fase (`duty` por segmento).
* Distribuições não exponenciais (Weibull) para componentes com desgaste; vida limitada e intervalos ótimos de
  substituição.
* Causa comum (fator β) nas redundâncias; ligação à FTA do ARP4761 (mesmas taxas, mesma árvore).
* Sobressalentes multi-escalão (METRIC) e reparação local; custo de posse do stock.
* Frota com abortos na cobertura, filas de manutenção partilhadas (`ground_queue`) e utilização sazonal.
* Fontes de taxas públicas adicionais verificáveis (p. ex. NPRD/EPRD com edição e página) quando houver acesso.
