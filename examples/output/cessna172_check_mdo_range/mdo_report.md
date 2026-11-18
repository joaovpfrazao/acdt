# Otimização multidisciplinar (OpenMDAO) — Cessna 172S (verificação)

* objetivo: **range** (registo de requisitos / `assumptions.mdo.objective` / `--objective`); W0 ≤ 1161 kg
* formulação MDF; MDA NLBGS (Gauss–Seidel não linear com Aitken, ou Newton); derivadas parciais por diferenças finitas centrais de cada disciplina; totais pelo sistema linear acoplado; SLSQP (scipy)
* variáveis de projeto: ws, AR, req_value; limites globais: ws ∈ [486.8, 1136]; pw ∈ [6.718, 17.91]; AR ∈ [5, 16]
* gestão de modelos por região de confiança (Alexandrov et al. 1998/2001; Conn, Gould & Toint 2000): modelo OpenMDAO (métodos de manual com correção β multiplicativa da polar, mais correção aditiva de ordem 1 de W0 (e E) — valor e gradiente (diferenças finitas do pipeline completo) iguais ao pipeline completo no iterado x_k —, sistemas congelados no iterado) otimizado em ±Δ·x_k; cada passo verificado no pipeline completo (XFOIL/AVL no ciclo, re-seleção de sistemas, estabilidade, aeroelasticidade, missão por segmentos). Mérito: φ = f/|f0| + 10·violação.
* resultado: melhoria aceite no pipeline completo

## Iterações da região de confiança

| it | Δ | x_k (W/S, P/W, AR) | passo (modelo) | redução prevista | real | ρ | estado |
|---|---|---|---|---|---|---|---|
| 1 | 0.3 | 811.3, 11.2, 7.32 | ws 811.3, pw 11.82, AR 5.124, req_value 1.383e+06 | 0.1674 | 0.1197 | 0.7151 | aceite |
| 2 | 0.3 | 811.3, 11.91, 5.124 | ws 822.6, pw 12.01, AR 5, req_value 1.371e+06 | 0.0376 | 0.03764 | 1 | aceite |
| 3 | 0.6 | 822.6, 12.04, 5 | ws 823.4, pw 12.04, AR 5, req_value 1.373e+06 | 0.0015 | 0.001488 | 1 | aceite |
| 4 | 1 | 823.4, 12.04, 5 | ws 823.4, pw 12.04, AR 5, req_value 1.373e+06 | 0.0000 | 2.197e-05 | 0.9381 | aceite |
| 5 | 1 | 823.4, 12.04, 5 | ws 823.4, pw 12.04, AR 5, req_value 1.373e+06 | 0.0000 | n/a | n/a | convergiu (modelo não prevê melhoria) |

## Primeira otimização do modelo (calibrado no ponto base): base vs ótimo do modelo

| grandeza | base | ótimo (modelo) |
|---|---|---|
| ws | 811.3 | 811.3 |
| pw | 11.2 | 11.82 |
| AR | 7.32 | 5.124 |
| req_value | 1.185e+06 | 1.383e+06 |
| W0 | 1161 | 1161 |
| We | 716.4 | 696.1 |
| Wf | 178.6 | 204.2 |
| E_Wh | 178.6 | 204.2 |
| S | 14.03 | 14.03 |
| span | 10.14 | 8.48 |
| CD0 | 0.03767 | 0.03746 |
| K | 0.04697 | 0.06211 |
| n_lim | 3.8 | 3.8 |
| m_box | 102.6 | 89.88 |
| m_wing | 129.6 | 104.7 |
| SM_aft | 0.1 | 0.1 |
| g_trim | -0.6759 | -0.6786 |
| x_apex_frac | 0.1471 | 0.1411 |
| g_stall_speed | 1.557e-06 | 4.441e-16 |
| g_landing_distance | -0.1513 | -0.1513 |

Ativas: g_stall_speed; calibração: β = CD0_lowfi/CD0_manual = 1.002, K_lowfi/K_manual = 0.896 no ponto base; CLmax limpo 1.529 (XFOIL). Restrições g ≤ 0 (g = requisito/valor − 1).

## Pipeline completo: base vs ótimo aceite

| grandeza | base | ótimo |
|---|---|---|
| W0 [kg] | 1161 | 1161 |
| We [kg] | 720.5 | 693.4 |
| Wf/bateria [kg] | 178.6 | 205.7 |
| W/S [N/m²] | 811.3 | 823.4 |
| P/W [W/N | -] | 11.2 | 12.04 |
| AR | 7.32 | 5 |
| S [m²] | 14.03 | 13.83 |
| b [m] | 10.14 | 8.315 |
| CD0 | 0.03767 | 0.03739 |
| (L/D)max | 11.89 | 9.806 |
| P_SL [kW] | 127.5 | 137.1 |
| caixão da asa [kg] | 99.88 | 85.1 |
| asa (pesos) [kg] | 132.1 | 102 |
| alcance (segmentos) [km] | 1277 | 1443 |
| autonomia (segmentos) [h] | 5.802 | 6.512 |
| margem divergence vs 1.2 V_D | 0.6379 | 1.063 |
| margem reversal vs 1.2 V_D | 0.6132 | 1.032 |
| margem flutter vs 1.2 V_D | -0.03761 | 0.1898 |
| viável (dimensionamento) | sim | sim |
| verificado (fase 2/3) | não | não |
| falhas | aeroel:flutter, perf:landing_distance | hq:dutch_roll, perf:landing_distance |

Notas: o pipeline completo inclui a re-seleção DISCRETA de sistemas (motor, células, hélice do catálogo): a resposta W0(x) tem saltos (p. ex. mudança de classe de motor), que o modelo contínuo não vê — passos que atravessam um salto são rejeitados (ρ < 0) e a região contrai. As verificações hq:/aeroel: não são restrições do otimizador (Fase 4) — ver as falhas na tabela.

Relatórios completos: `baseline/report.md`, `optimum/report.md`.
