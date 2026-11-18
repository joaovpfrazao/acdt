# Otimização multidisciplinar (OpenMDAO) — UAV ISR elétrico 25 kg

* objetivo: **W0** (registo de requisitos / `assumptions.mdo.objective` / `--objective`)
* formulação MDF; MDA NLBGS (Gauss–Seidel não linear com Aitken, ou Newton); derivadas parciais por diferenças finitas centrais de cada disciplina; totais pelo sistema linear acoplado; SLSQP (scipy)
* variáveis de projeto: ws, AR; limites globais: ws ∈ [105.4, 245.9]; pw ∈ [3.093, 8.248]; AR ∈ [5, 16]
* gestão de modelos por região de confiança (Alexandrov et al. 1998/2001; Conn, Gould & Toint 2000): modelo OpenMDAO (métodos de manual com correção β multiplicativa da polar, mais correção aditiva de ordem 1 de W0 (e E) — valor e gradiente (diferenças finitas do pipeline completo) iguais ao pipeline completo no iterado x_k —, sistemas congelados no iterado) otimizado em ±Δ·x_k; cada passo verificado no pipeline completo (XFOIL/AVL no ciclo, catálogo de motor/ESC/célula fixo, estabilidade, aeroelasticidade, missão por segmentos). Mérito: φ = f/|f0| + 10·violação.
* resultado: melhoria aceite no pipeline completo

## Iterações da região de confiança

| it | Δ | x_k (W/S, P/W, AR) | passo (modelo) | redução prevista | real | ρ | estado |
|---|---|---|---|---|---|---|---|
| 1 | 0.3 | 175.6, 5.155, 14 | ws 175.6, pw 5.282, AR 9.8 | 0.2297 | 0.2164 | 0.9418 | aceite; catálogo rejeitado |
| 2 | 0.6 | 175.6, 5.359, 9.8 | ws 176.2, pw 5.285, AR 15.68 | 0.2140 | -0.8576 | -4.007 | rejeitado (novas falhas: wing_span); catálogo rejeitado |
| 3 | 0.3 | 175.6, 5.359, 9.8 | ws 176.2, pw 5.295, AR 12.74 | 0.1088 | -0.008831 | -0.0812 | rejeitado; catálogo rejeitado |
| 4 | 0.15 | 175.6, 5.359, 9.8 | ws 176.2, pw 5.32, AR 11.27 | 0.0566 | 0.008007 | 0.1414 | aceite; catálogo aceite (outrunner_50xx_200kv_class) |
| 5 | 0.075 | 176.2, 5.261, 11.27 | ws 177.7, pw 5.302, AR 10.42 | 0.0090 | 0.003642 | 0.4055 | aceite; catálogo rejeitado |
| 6 | 0.075 | 177.7, 5.334, 10.42 | ws 176.5, pw 5.297, AR 11.21 | -0.0023 | n/a | n/a | convergiu (modelo não prevê melhoria) |

## Primeira otimização do modelo (calibrado no ponto base): base vs ótimo do modelo

| grandeza | base | ótimo (modelo) |
|---|---|---|
| ws | 175.6 | 175.6 |
| pw | 5.155 | 5.282 |
| AR | 14 | 9.8 |
| W0 | 23.42 | 22.43 |
| We | 11.51 | 10.17 |
| Wf | 7.731 | 7.895 |
| E_Wh | 1766 | 1803 |
| S | 1.308 | 1.253 |
| span | 4.279 | 3.504 |
| CD0 | 0.02316 | 0.0232 |
| K | 0.02522 | 0.03112 |
| n_lim | 5.019 | 4.711 |
| m_box | 3.67 | 3.407 |
| m_wing | 4.509 | 3.344 |
| SM_aft | 0.1 | 0.1 |
| g_trim | -0.6467 | -0.6513 |
| x_apex_frac | 0.3324 | 0.3208 |
| g_stall_speed | -2.466e-06 | 0 |
| g_span | 0.01875 | -0.1658 |
| g_mtow | -0.0632 | -0.1027 |

Ativas: g_stall_speed; calibração: β = CD0_lowfi/CD0_manual = 1.089, K_lowfi/K_manual = 0.730 no ponto base; CLmax limpo 1.292 (XFOIL). Restrições g ≤ 0 (g = requisito/valor − 1).

## Pipeline completo: base vs ótimo aceite

| grandeza | base | ótimo |
|---|---|---|
| W0 [kg] | 23.42 | 21.63 |
| We [kg] | 11.69 | 9.794 |
| Wf/bateria [kg] | 7.731 | 7.832 |
| W/S [N/m²] | 175.6 | 177.7 |
| P/W [W/N | -] | 5.155 | 5.334 |
| AR | 14 | 10.42 |
| S [m²] | 1.308 | 1.193 |
| b [m] | 4.279 | 3.527 |
| CD0 | 0.02316 | 0.02381 |
| (L/D)max | 20.69 | 17.95 |
| energia bateria [Wh] | 1766 | 1789 |
| P_SL [kW] | 1.184 | 1.131 |
| caixão da asa [kg] | 3.624 | 3.236 |
| asa (pesos) [kg] | 4.658 | 3.407 |
| alcance (segmentos) [km] | 214 | 212.4 |
| autonomia (segmentos) [h] | 2.769 | 2.733 |
| margem divergence vs 1.2 V_D | 7.657 | 10.14 |
| margem reversal vs 1.2 V_D | ∞ | ∞ |
| margem flutter vs 1.2 V_D | 2.931 | ∞ |
| viável (dimensionamento) | não | não |
| verificado (fase 2/3) | não | não |
| falhas | wing_span, hq:CAP | hq:CAP |

Notas: o SLSQP só vê W/S, P/W e AR, com o motor, o ESC e a célula fixos (Geoffrion, J. Optim. Theory Appl. 10, 1972: o subproblema contínuo não atravessa a atribuição inteira). Um passo de catálogo à parte reescolhe o mais leve que cumpre a potência e a corrente, e só é aceite se o mérito do pipeline melhora e não há verificações novas a falhar. Não há catálogo de hélices: o diâmetro segue Raymer Sec. 10.3. Os servos continuam a ser reescolhidos no fecho. As verificações hq:/aeroel: não são restrições do MDO (omissão = filtro pós-ótimo legado; ativar com `assumptions.mdo.hq_aeroel_constraints: true`) — ver as falhas na tabela.

Relatórios completos: `baseline/report.md`, `optimum/report.md`.
