# Otimização multidisciplinar (OpenMDAO) — UAV gasolina 150 kg (endurance) — montagem asa voadora

* objetivo: **W0** (registo de requisitos / `assumptions.mdo.objective` / `--objective`)
* formulação MDF; MDA NLBGS (Gauss–Seidel não linear com Aitken, ou Newton); derivadas parciais por diferenças finitas centrais de cada disciplina; totais pelo sistema linear acoplado; SLSQP (scipy)
* variáveis de projeto: ws; limites globais: ws ∈ [429.5, 1002]; pw ∈ [7.003, 18.68]; AR ∈ [5, 16]
* gestão de modelos por região de confiança (Alexandrov et al. 1998/2001; Conn, Gould & Toint 2000): modelo OpenMDAO (métodos de manual com correção β multiplicativa da polar, mais correção aditiva de ordem 1 de W0 (e E) — valor e gradiente (diferenças finitas do pipeline completo) iguais ao pipeline completo no iterado x_k —, sistemas congelados no iterado) otimizado em ±Δ·x_k; cada passo verificado no pipeline completo (XFOIL/AVL no ciclo, catálogo de motor/ESC/célula fixo, estabilidade, aeroelasticidade, missão por segmentos). Mérito: φ = f/|f0| + 10·violação.
* resultado: melhoria aceite no pipeline completo

## Iterações da região de confiança

| it | Δ | x_k (W/S, P/W, AR) | passo (modelo) | redução prevista | real | ρ | estado |
|---|---|---|---|---|---|---|---|
| 1 | 0.3 | 715.8, 11.67, 6.032 | ws 501.1, pw 9.275, AR 6.032 | 0.0738 | 0.07927 | 1.074 | aceite |
| 2 | 0.6 | 501.1, 9.204, 6.032 | ws 429.5, pw 8.346, AR 6.032 | 0.0112 | 0.006159 | 0.5495 | aceite |
| 3 | 0.6 | 429.5, 8.443, 6.032 | ws 429.5, pw 8.443, AR 6.032 | 0.0000 | n/a | n/a | convergiu (modelo não prevê melhoria) |

## Primeira otimização do modelo (calibrado no ponto base): base vs ótimo do modelo

| grandeza | base | ótimo (modelo) |
|---|---|---|
| ws | 715.8 | 501.1 |
| pw | 11.67 | 9.275 |
| AR | 6.032 | 6.032 |
| W0 | 133 | 123.2 |
| We | 79.95 | 72.4 |
| Wf | 23.08 | 20.76 |
| E_Wh | 23.08 | 20.76 |
| S | 1.822 | 2.411 |
| span | 3.316 | 3.814 |
| CD0 | 0.0388 | 0.03201 |
| K | 0.05553 | 0.05553 |
| n_lim | 4.4 | 4.4 |
| m_box | 3.72 | 4.85 |
| m_wing | 8.375 | 9.973 |
| SM_aft | 0.1 | 0.1 |
| g_trim | -0.6465 | -0.6472 |
| x_apex_frac | 0.02398 | 0.02044 |
| g_stall_speed | -5.586e-06 | -0.3 |

Ativas: —; calibração: β = CD0_lowfi/CD0_manual = 1.000, K_lowfi/K_manual = 0.914 no ponto base; CLmax limpo 1.324 (XFOIL). Restrições g ≤ 0 (g = requisito/valor − 1).

## Pipeline completo: base vs ótimo aceite

| grandeza | base | ótimo |
|---|---|---|
| W0 [kg] | 133 | 121.7 |
| We [kg] | 79.95 | 71.22 |
| Wf/bateria [kg] | 23.08 | 20.45 |
| W/S [N/m²] | 715.8 | 429.5 |
| P/W [W/N | -] | 11.67 | 8.443 |
| AR | 6.032 | 6.032 |
| S [m²] | 1.822 | 2.778 |
| b [m] | 3.316 | 4.093 |
| CD0 | 0.0388 | 0.02921 |
| (L/D)max | 10.77 | 12.38 |
| P_SL [kW] | 15.23 | 10.07 |
| caixão da asa [kg] | 3.677 | 5.514 |
| asa (pesos) [kg] | ∞ | ∞ |
| alcance (segmentos) [km] | 1775 | 1735 |
| autonomia (segmentos) [h] | 11.04 | 10.91 |
| margem divergence vs 1.2 V_D | 8.468 | 7.423 |
| margem reversal vs 1.2 V_D | ∞ | ∞ |
| margem flutter vs 1.2 V_D | ∞ | ∞ |
| viável (dimensionamento) | sim | sim |
| verificado (fase 2/3) | não | não |
| falhas | hq:CAP, hq:dutch_roll, gear:position, gear:tipback, asm:static_margin | hq:CAP, hq:dutch_roll, gear:position, gear:tipback, asm:static_margin |

Notas: o SLSQP só vê W/S, P/W e AR, com o motor, o ESC e a célula fixos (Geoffrion, J. Optim. Theory Appl. 10, 1972: o subproblema contínuo não atravessa a atribuição inteira). Um passo de catálogo à parte reescolhe o mais leve que cumpre a potência e a corrente, e só é aceite se o mérito do pipeline melhora e não há verificações novas a falhar. Não há catálogo de hélices: o diâmetro segue Raymer Sec. 10.3. Os servos continuam a ser reescolhidos no fecho. As verificações hq:/aeroel: não são restrições (ativar com `assumptions.mdo.hq_aeroel_constraints: true`) — ver as falhas na tabela.

Relatórios completos: `baseline/report.md`, `optimum/report.md`.
