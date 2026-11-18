# Otimização multidisciplinar (OpenMDAO) — Cessna 172S (verificação)

* objetivo: **W0** (registo de requisitos / `assumptions.mdo.objective` / `--objective`)
* formulação MDF; MDA NLBGS (Gauss–Seidel não linear com Aitken, ou Newton); derivadas parciais por diferenças finitas centrais de cada disciplina; totais pelo sistema linear acoplado; SLSQP (scipy)
* variáveis de projeto: ws, AR; limites globais: ws ∈ [486.8, 1136]; pw ∈ [6.718, 17.91]; AR ∈ [5, 16]
* gestão de modelos por região de confiança (Alexandrov et al. 1998/2001; Conn, Gould & Toint 2000): modelo OpenMDAO (métodos de manual com correção β multiplicativa da polar, mais correção aditiva de ordem 1 de W0 (e E) — valor e gradiente (diferenças finitas do pipeline completo) iguais ao pipeline completo no iterado x_k —, sistemas congelados no iterado) otimizado em ±Δ·x_k; cada passo verificado no pipeline completo (XFOIL/AVL no ciclo, re-seleção de sistemas, estabilidade, aeroelasticidade, missão por segmentos). Mérito: φ = f/|f0| + 10·violação.
* resultado: melhoria aceite no pipeline completo

## Iterações da região de confiança

| it | Δ | x_k (W/S, P/W, AR) | passo (modelo) | redução prevista | real | ρ | estado |
|---|---|---|---|---|---|---|---|
| 1 | 0.3 | 811.3, 11.2, 7.32 | ws 811.3, pw 12.04, AR 5.124 | 0.0355 | 0.0322 | 0.9079 | aceite |
| 2 | 0.6 | 811.3, 12.15, 5.124 | ws 821.2, pw 12.23, AR 5 | 0.0024 | 0.002462 | 1.039 | aceite |
| 3 | 1 | 821.2, 12.26, 5 | ws 822.1, pw 12.27, AR 5 | 0.0001 | 0.0001494 | 1.048 | aceite |
| 4 | 1 | 822.1, 12.26, 5 | ws 822, pw 12.27, AR 5 | -0.0000 | n/a | n/a | convergiu (modelo não prevê melhoria) |

## Primeira otimização do modelo (calibrado no ponto base): base vs ótimo do modelo

| grandeza | base | ótimo (modelo) |
|---|---|---|
| ws | 811.3 | 811.3 |
| pw | 11.2 | 12.04 |
| AR | 7.32 | 5.124 |
| W0 | 1161 | 1120 |
| We | 716.4 | 678.2 |
| Wf | 178.6 | 180.3 |
| E_Wh | 178.6 | 180.3 |
| S | 14.03 | 13.54 |
| span | 10.14 | 8.328 |
| CD0 | 0.03767 | 0.03839 |
| K | 0.04697 | 0.06211 |
| n_lim | 3.8 | 3.8 |
| m_box | 102.6 | 85.66 |
| m_wing | 129.6 | 100 |
| SM_aft | 0.1 | 0.1 |
| g_trim | -0.6759 | -0.6812 |
| x_apex_frac | 0.1471 | 0.1394 |
| g_stall_speed | 1.557e-06 | 2.22e-16 |
| g_landing_distance | -0.1513 | -0.1513 |

Ativas: g_stall_speed; calibração: β = CD0_lowfi/CD0_manual = 1.002, K_lowfi/K_manual = 0.896 no ponto base; CLmax limpo 1.529 (XFOIL). Restrições g ≤ 0 (g = requisito/valor − 1).

## Pipeline completo: base vs ótimo aceite

| grandeza | base | ótimo |
|---|---|---|
| W0 [kg] | 1161 | 1121 |
| We [kg] | 720.5 | 676.1 |
| Wf/bateria [kg] | 178.6 | 182.6 |
| W/S [N/m²] | 811.3 | 822.1 |
| P/W [W/N | -] | 11.2 | 12.26 |
| AR | 7.32 | 5 |
| S [m²] | 14.03 | 13.37 |
| b [m] | 10.14 | 8.176 |
| CD0 | 0.03767 | 0.03828 |
| (L/D)max | 11.89 | 9.691 |
| P_SL [kW] | 127.5 | 134.8 |
| caixão da asa [kg] | 99.88 | 81.41 |
| asa (pesos) [kg] | 132.1 | 97.67 |
| alcance (segmentos) [km] | 1277 | 1268 |
| autonomia (segmentos) [h] | 5.802 | 5.733 |
| margem divergence vs 1.2 V_D | 0.6379 | 1.075 |
| margem reversal vs 1.2 V_D | 0.6132 | 1.044 |
| margem flutter vs 1.2 V_D | -0.03761 | 0.1964 |
| viável (dimensionamento) | sim | não |
| verificado (fase 2/3) | não | não |
| falhas | aeroel:flutter, perf:landing_distance | hq:dutch_roll, perf:landing_distance |

Notas: o pipeline completo inclui a re-seleção DISCRETA de sistemas (motor, células, hélice do catálogo): a resposta W0(x) tem saltos (p. ex. mudança de classe de motor), que o modelo contínuo não vê — passos que atravessam um salto são rejeitados (ρ < 0) e a região contrai. As verificações hq:/aeroel: não são restrições do otimizador (Fase 4) — ver as falhas na tabela.

Relatórios completos: `baseline/report.md`, `optimum/report.md`.
