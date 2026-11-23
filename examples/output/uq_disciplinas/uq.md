# Incerteza e sensibilidade

Formato `acdt.uq/1`. Modelo: pipeline aircraft L0/L1 (`uav_endurance_payload.yaml`), fidelidade handbook, sem aeroelasticity; um pipeline por amostra

Propagação **LHS**, N = 400, semente 20261123; IC 95 %; probabilidade-alvo 0.95 (PRESSUPOSTO).

## Pressupostos

* probabilidade-alvo 0.95 por omissão (PRESSUPOSTO: declare uncertainty.target_probability e a origem)
* tolerância de convergência SE/média ≤ 0.01 por omissão (PRESSUPOSTO)
* assumptions.propulsion.battery_Wh_kg: PRESSUPOSTO: ±10 % em torno do nível de pack do exemplo (200 Wh/kg)
* assumptions.propulsion.eta_total: PRESSUPOSTO: banda em torno do produto de rendimentos do exemplo (0,62)
* assumptions.thermal.electric.eta_esc: PRESSUPOSTO: banda em torno do valor de teste 0,97
* assumptions.life_cycle.discount_rate: PRESSUPOSTO: banda em torno do valor de teste 0,05

## Entradas incertas

| Caminho | Distribuição | Nominal | Origem |
|---|---|---|---|
| `assumptions.propulsion.battery_Wh_kg` | U(180, 220) | 200 | PRESSUPOSTO: ±10 % em torno do nível de pack do exemplo (200 Wh/kg) |
| `assumptions.propulsion.eta_total` | U(0.58, 0.66) | 0.62 | PRESSUPOSTO: banda em torno do produto de rendimentos do exemplo (0,62) |
| `assumptions.thermal.electric.eta_esc` | U(0.95, 0.98) | 0.97 | PRESSUPOSTO: banda em torno do valor de teste 0,97 |
| `assumptions.life_cycle.cost_per_fh_USD` | U(40, 90) | 65 | intervalo de teste de tests/test_life_cycle.py (40–90 USD/h) |
| `assumptions.life_cycle.fh_per_aircraft_per_year` | U(300, 500) | 400 | intervalo de teste de tests/test_life_cycle.py (300–500 h/ano) |
| `assumptions.life_cycle.environment.grid_intensity_kgCO2e_per_kWh` | U(0.1, 0.4) | 0.25 | intervalo de teste de tests/test_life_cycle.py (0,1–0,4 kg CO2e/kWh) |
| `assumptions.life_cycle.discount_rate` | U(0.03, 0.07) | 0.05 | PRESSUPOSTO: banda em torno do valor de teste 0,05 |

## Substituto (superfície de resposta quadrática; 28 corridas do modelo verdadeiro, 2 falhadas; aceite se Q² ≥ 0.95)

| Saída | Termos | Q² (PRESS) | R² | RMSE LOO |
|---|---|---|---|---|
| cooling_drag_area_m2 | 15 | 0.9683 | 0.9976 | 0.0003761 |
| CD0 | rejeitado | Q² = -1.721 < 0.95 (validação cruzada PRESS) |  |  |
| E_Wh | rejeitado | Q² = -0.895 < 0.95 (validação cruzada PRESS) |  |  |
| K | rejeitado | constante no desenho de treino (sem variância a modelar) |  |  |
| S_m2 | rejeitado | Q² = -0.695 < 0.95 (validação cruzada PRESS) |  |  |
| V_cruise_mps | rejeitado | constante no desenho de treino (sem variância a modelar) |  |  |
| W0_kg | rejeitado | Q² = -0.695 < 0.95 (validação cruzada PRESS) |  |  |
| We_kg | rejeitado | Q² = -0.802 < 0.95 (validação cruzada PRESS) |  |  |
| Wf_kg | rejeitado | Q² = -0.608 < 0.95 (validação cruzada PRESS) |  |  |
| co2e_ciclo_kg | rejeitado | Q² = -0.116 < 0.95 (validação cruzada PRESS) |  |  |
| co2e_fh_kg | rejeitado | Q² = -0.076 < 0.95 (validação cruzada PRESS) |  |  |
| hot_margin_min_C | rejeitado | Q² = 0.576 < 0.95 (validação cruzada PRESS) |  |  |
| ice_power_W | rejeitado | Q² = -0.307 < 0.95 (validação cruzada PRESS) |  |  |
| lcc_pv_USD | rejeitado | Q² = 0.922 < 0.95 (validação cruzada PRESS) |  |  |
| mission_reliability | rejeitado | Q² = -1.737 < 0.95 (validação cruzada PRESS) |  |  |
| req:REQ-climb_rate | rejeitado | Q² = -1.481 < 0.95 (validação cruzada PRESS) |  |  |
| req:REQ-cruise_altitude | rejeitado | constante no desenho de treino (sem variância a modelar) |  |  |
| req:REQ-cruise_speed | rejeitado | constante no desenho de treino (sem variância a modelar) |  |  |
| req:REQ-endurance | rejeitado | Q² = -1.923 < 0.95 (validação cruzada PRESS) |  |  |
| req:REQ-mtow | rejeitado | Q² = -0.695 < 0.95 (validação cruzada PRESS) |  |  |
| req:REQ-payload_mass | rejeitado | constante no desenho de treino (sem variância a modelar) |  |  |
| req:REQ-service_ceiling | rejeitado | constante no desenho de treino (sem variância a modelar) |  |  |
| req:REQ-stall_speed | rejeitado | constante no desenho de treino (sem variância a modelar) |  |  |
| req:REQ-wing_span | rejeitado | Q² = -0.470 < 0.95 (validação cruzada PRESS) |  |  |
| unit_cost_USD | rejeitado | Q² = -0.693 < 0.95 (validação cruzada PRESS) |  |  |
| ws_Pa | rejeitado | constante no desenho de treino (sem variância a modelar) |  |  |

Fração das amostras de propagação fora da caixa de treino (em pelo menos uma entrada): 22.8 %. requisitos não numéricos ou sem substituto aceite: P(passa) das amostras de treino do modelo verdadeiro.

| Entrada | Caixa de treino | Fora (fração) | Excursão máx. (× largura da caixa) |
|---|---|---|---|
| `assumptions.propulsion.battery_Wh_kg` | [181.4, 219.5] | 4.2 % | 0.036 |
| `assumptions.propulsion.eta_total` | [0.5826, 0.6577] | 6.0 % | 0.033 |
| `assumptions.thermal.electric.eta_esc` | [0.9501, 0.9795] | 2.0 % | 0.016 |
| `assumptions.life_cycle.cost_per_fh_USD` | [40.07, 89.12] | 2.0 % | 0.016 |
| `assumptions.life_cycle.fh_per_aircraft_per_year` | [301.9, 494.6] | 3.8 % | 0.027 |
| `assumptions.life_cycle.environment.grid_intensity_kgCO2e_per_kWh` | [0.1004, 0.3898] | 3.5 % | 0.033 |
| `assumptions.life_cycle.discount_rate` | [0.03059, 0.06883] | 4.5 % | 0.029 |

Fora da caixa = extrapolação do polinómio; caudas ilimitadas (normal/lognormal) e o LHS de treino (N_treino pontos) deixam sempre uma fração ≈ 2/(N_treino+1) por entrada limitada.

## Resultados (percentis)

Avaliações falhadas: 0 (contam como não-passa nos requisitos; nunca como zero).

| Saída | Nominal | Média | σ | P5 | P50 | P95 | IC P95 | SE/média | Convergiu | Fonte |
|---|---|---|---|---|---|---|---|---|---|---|
| W0_kg | 37.96 | 40.4 | 11.3 | 34.11 | 37 | 56.78 | — | 0.055 | não | modelo (treino LHS; intervalos varridos uniformemente) |
| lcc_pv_USD | 1.008e+07 | 1.008e+07 | 2.18e+06 | 7.232e+06 | 1.006e+07 | 1.332e+07 | — | 0.043 | não | modelo (treino LHS; intervalos varridos uniformemente) |
| co2e_fh_kg | 0.6634 | 0.721 | 0.247 | 0.4528 | 0.7008 | 1.079 | — | 0.067 | não | modelo (treino LHS; intervalos varridos uniformemente) |
| co2e_ciclo_kg | 1.327e+05 | 1.433e+05 | 4.45e+04 | 7.774e+04 | 1.501e+05 | 1.783e+05 | — | 0.061 | não | modelo (treino LHS; intervalos varridos uniformemente) |
| unit_cost_USD | 4.144e+04 | 4.259e+04 | 5.32e+03 | 3.962e+04 | 4.1e+04 | 5.032e+04 | — | 0.024 | não | modelo (treino LHS; intervalos varridos uniformemente) |
| hot_margin_min_C | -63.95 | -89.15 | 56.6 | -181.6 | -63.95 | -63.95 | — | 0.12 | não | modelo (treino LHS; intervalos varridos uniformemente) |
| ice_power_W | 247.8 | 247.9 | 0.271 | 247.8 | 247.8 | 248.5 | — | 0.00021 | sim | modelo (treino LHS; intervalos varridos uniformemente) |
| cooling_drag_area_m2 | 0.003072 | 0.005451 | 0.00505 | -0.0001475 | 0.003325 | 0.016 | [0.01512, 0.01656] | 0.046 | não | substituto |
| mission_reliability | 0.9997 | 0.9997 | 4.18e-07 | 0.9997 | 0.9997 | 0.9997 | — | 8.2e-08 | sim | modelo (treino LHS; intervalos varridos uniformemente) |

## Requisitos: probabilidade de cumprir

O estado determinístico (corrida nominal) não muda; a coluna «estado prob.» é nova: **prob_passa** (limite inferior de Wilson ≥ alvo), **prob_no_limite** (P(passa) abaixo do alvo, mas P(passa ∪ no_limite) ≥ alvo: cumpre só dentro da tolerância declarada), **prob_falha** (limite superior < alvo e não prob_no_limite), **inconclusivo** (mais amostras), **nao_avaliado**, **desconhecido**. Amostras sem veredicto contam como não-passa.

| Requisito | Estado nominal | P(passa) | IC | P(no_limite) | P(falha) | Estado prob. | Fonte |
|---|---|---|---|---|---|---|---|
| REQ-propulsion_type | nao_avaliado | — | — | — | — | nao_avaliado | modelo (treino LHS) |
| REQ-regulatory_category | desconhecido | — | — | — | — | desconhecido | modelo (treino LHS) |
| REQ-payload_mass | passa | 0.929 | [0.774, 0.980] | 0.000 | 0.000 | inconclusivo | modelo (treino LHS) |
| REQ-endurance | no_limite | 0.000 | [0.000, 0.121] | 0.893 | 0.036 | prob_falha | modelo (treino LHS) |
| REQ-cruise_speed | passa | 0.929 | [0.774, 0.980] | 0.000 | 0.000 | inconclusivo | modelo (treino LHS) |
| REQ-cruise_altitude | passa | 0.929 | [0.774, 0.980] | 0.000 | 0.000 | inconclusivo | modelo (treino LHS) |
| REQ-stall_speed | no_limite | 0.000 | [0.000, 0.121] | 0.929 | 0.000 | prob_falha | modelo (treino LHS) |
| REQ-climb_rate | no_limite | 0.000 | [0.000, 0.121] | 0.929 | 0.000 | prob_falha | modelo (treino LHS) |
| REQ-service_ceiling | passa | 0.929 | [0.774, 0.980] | 0.000 | 0.000 | inconclusivo | modelo (treino LHS) |
| REQ-wing_span | falha | 0.000 | [0.000, 0.121] | 0.000 | 0.929 | prob_falha | modelo (treino LHS) |
| REQ-mtow | falha | 0.000 | [0.000, 0.121] | 0.000 | 0.929 | prob_falha | modelo (treino LHS) |

## Sobol' (Sobol' (S1 de Saltelli 2010, ST de Jansen 1999); N = 2048, 18432 avaliações, 0 falhadas)

* W0_kg: nao_avaliado — sem substituto aceite (Q² = -0.695 < 0.95 (validação cruzada PRESS)); Sobol' não avaliado
* lcc_pv_USD: nao_avaliado — sem substituto aceite (Q² = 0.922 < 0.95 (validação cruzada PRESS)); Sobol' não avaliado
* co2e_fh_kg: nao_avaliado — sem substituto aceite (Q² = -0.076 < 0.95 (validação cruzada PRESS)); Sobol' não avaliado
* co2e_ciclo_kg: nao_avaliado — sem substituto aceite (Q² = -0.116 < 0.95 (validação cruzada PRESS)); Sobol' não avaliado
* unit_cost_USD: nao_avaliado — sem substituto aceite (Q² = -0.693 < 0.95 (validação cruzada PRESS)); Sobol' não avaliado
* hot_margin_min_C: nao_avaliado — sem substituto aceite (Q² = 0.576 < 0.95 (validação cruzada PRESS)); Sobol' não avaliado
* ice_power_W: nao_avaliado — sem substituto aceite (Q² = -0.307 < 0.95 (validação cruzada PRESS)); Sobol' não avaliado
### cooling_drag_area_m2

ΣS1 = 0.974 (IC [0.923, 1.022])

| Entrada | S1 | IC S1 | ST | IC ST |
|---|---|---|---|---|
| `assumptions.propulsion.eta_total` | 0.936 | [0.881, 0.980] | 0.937 | [0.895, 0.972] |
| `assumptions.propulsion.battery_Wh_kg` | 0.015 | [0.007, 0.024] | 0.021 | [0.019, 0.023] |
| `assumptions.life_cycle.discount_rate` | 0.007 | [0.000, 0.014] | 0.012 | [0.011, 0.013] |
| `assumptions.life_cycle.cost_per_fh_USD` | 0.007 | [0.002, 0.013] | 0.007 | [0.007, 0.008] |
| `assumptions.life_cycle.fh_per_aircraft_per_year` | 0.005 | [0.002, 0.008] | 0.004 | [0.004, 0.005] |
| `assumptions.thermal.electric.eta_esc` | 0.002 | [-0.001, 0.006] | 0.003 | [0.003, 0.003] |
| `assumptions.life_cycle.environment.grid_intensity_kgCO2e_per_kWh` | 0.003 | [-0.001, 0.006] | 0.003 | [0.003, 0.003] |

* mission_reliability: nao_avaliado — sem substituto aceite (Q² = -1.737 < 0.95 (validação cruzada PRESS)); Sobol' não avaliado

## Morris (r = 20, p = 4, 160 avaliações)

EE no cubo unitário (por unidade de quantil); grelha em quantis 1–99 % nas marginais ilimitadas (PRESSUPOSTO)

### W0_kg

| Entrada | μ* | μ*/máx | μ | σ |
|---|---|---|---|---|

### lcc_pv_USD

| Entrada | μ* | μ*/máx | μ | σ |
|---|---|---|---|---|

### co2e_fh_kg

| Entrada | μ* | μ*/máx | μ | σ |
|---|---|---|---|---|

### co2e_ciclo_kg

| Entrada | μ* | μ*/máx | μ | σ |
|---|---|---|---|---|

### unit_cost_USD

| Entrada | μ* | μ*/máx | μ | σ |
|---|---|---|---|---|

### hot_margin_min_C

| Entrada | μ* | μ*/máx | μ | σ |
|---|---|---|---|---|

### ice_power_W

| Entrada | μ* | μ*/máx | μ | σ |
|---|---|---|---|---|

### cooling_drag_area_m2

| Entrada | μ* | μ*/máx | μ | σ |
|---|---|---|---|---|
| `assumptions.propulsion.eta_total` | 0.01641 | 1.000 | -0.01641 | 0.009273 |
| `assumptions.life_cycle.discount_rate` | 0.002339 | 0.143 | 0.0002286 | 0.002435 |
| `assumptions.propulsion.battery_Wh_kg` | 0.002014 | 0.123 | -0.002014 | 0.001976 |
| `assumptions.life_cycle.cost_per_fh_USD` | 0.001379 | 0.084 | -0.001379 | 0.0009991 |
| `assumptions.life_cycle.fh_per_aircraft_per_year` | 0.001045 | 0.064 | 0.000931 | 0.0009814 |
| `assumptions.thermal.electric.eta_esc` | 0.0008984 | 0.055 | 0.0008984 | 0.0001153 |
| `assumptions.life_cycle.environment.grid_intensity_kgCO2e_per_kWh` | 0.000852 | 0.052 | -0.000328 | 0.0009608 |

### mission_reliability

| Entrada | μ* | μ*/máx | μ | σ |
|---|---|---|---|---|


## Referências

* McKay, Beckman & Conover, Technometrics 21 (1979) 239–245 (LHS); Iman & Conover, Commun. Statist. Simul. Comput. 11 (1982) 311–334 (correlação de postos); Ang & Tang, Probability Concepts in Engineering, 2.ª ed., Wiley 2007 (lognormal); Ferson et al., SAND2002-4015 (2003) e Oberkampf & Roy, Verification and Validation in Scientific Computing, CUP 2010, Cap. 13 (intervalos / caixas de probabilidade)
* Conover 1999 Sec. 3.2 (IC de quantis por estatísticas de ordem); Stein 1987 (variância do LHS); Wilson 1927 e Agresti & Coull 1998 (IC de proporção)
* Saltelli, Comput. Phys. Commun. 145 (2002) 280–297 (desenho A, B, A_B); Saltelli et al., Comput. Phys. Commun. 181 (2010) 259–270, Tab. 2; Jansen, Comput. Phys. Commun. 117 (1999) 35–43
* Morris, Technometrics 33 (1991) 161–174; Campolongo, Cariboni & Saltelli, Environ. Model. Softw. 22 (2007) 1509–1518 (μ*)
