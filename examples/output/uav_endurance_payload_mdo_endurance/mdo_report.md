# Otimização multidisciplinar (OpenMDAO) — UAV ISR elétrico 25 kg

* objetivo: **endurance** (registo de requisitos / `assumptions.mdo.objective` / `--objective`); W0 ≤ 25 kg
* formulação MDF; MDA NLBGS (Gauss–Seidel não linear com Aitken, ou Newton); derivadas parciais por diferenças finitas centrais de cada disciplina; totais pelo sistema linear acoplado; SLSQP (scipy)
* variáveis de projeto: ws, AR, req_value; limites globais: ws ∈ [105.4, 245.9]; pw ∈ [3.093, 8.248]; AR ∈ [5, 16]
* gestão de modelos por região de confiança (Alexandrov et al. 1998/2001; Conn, Gould & Toint 2000): modelo OpenMDAO (métodos de manual com correção β multiplicativa da polar, mais correção aditiva de ordem 1 de W0 (e E) — valor e gradiente (diferenças finitas do pipeline completo) iguais ao pipeline completo no iterado x_k —, sistemas congelados no iterado) otimizado em ±Δ·x_k; cada passo verificado no pipeline completo (XFOIL/AVL no ciclo, catálogo de motor/ESC/célula fixo, estabilidade, aeroelasticidade, missão por segmentos). Mérito: φ = f/|f0| + 10·violação.
* resultado: melhoria aceite no pipeline completo

## Iterações da região de confiança

| it | Δ | x_k (W/S, P/W, AR) | passo (modelo) | redução prevista | real | ρ | estado |
|---|---|---|---|---|---|---|---|
| 1 | 0.3 | 175.6, 5.155, 14 | ws 175.6, pw 5.253, AR 9.8, req_value 1.046e+04 | 0.3496 | -0.3046 | -0.8714 | rejeitado (novas falhas: mtow); catálogo rejeitado |
| 2 | 0.15 | 175.6, 5.155, 14 | ws 175.6, pw 5.182, AR 11.9, req_value 1.022e+04 | 0.3234 | 0.1106 | 0.3421 | rejeitado (novas falhas: mtow); catálogo rejeitado |
| 3 | 0.075 | 175.6, 5.155, 14 | ws 175.6, pw 5.164, AR 12.98, req_value 9675 | 0.2625 | 0.2625 | 1 | aceite; catálogo rejeitado |
| 4 | 0.075 | 175.6, 5.168, 12.98 | ws 177.5, pw 5.192, AR 12, req_value 1.034e+04 | 0.0738 | -0.2094 | -2.837 | rejeitado (novas falhas: mtow); catálogo rejeitado |
| 5 | 0.0375 | 175.6, 5.168, 12.98 | ws 177.3, pw 5.172, AR 12.88, req_value 1.004e+04 | 0.0403 | 0.008234 | 0.2043 | rejeitado (novas falhas: wing_span); catálogo rejeitado; convergiu (Δ < Δ_min) |

## Primeira otimização do modelo (calibrado no ponto base): base vs ótimo do modelo

| grandeza | base | ótimo (modelo) |
|---|---|---|
| ws | 175.6 | 175.6 |
| pw | 5.155 | 5.253 |
| AR | 14 | 9.8 |
| req_value | 9000 | 1.046e+04 |
| W0 | 23.42 | 25 |
| We | 11.51 | 10.84 |
| Wf | 7.731 | 9.772 |
| E_Wh | 1766 | 2232 |
| S | 1.308 | 1.396 |
| span | 4.279 | 3.699 |
| CD0 | 0.02316 | 0.0221 |
| K | 0.02522 | 0.03112 |
| n_lim | 5.019 | 4.664 |
| m_box | 3.67 | 3.808 |
| m_wing | 4.509 | 3.81 |
| SM_aft | 0.1 | 0.1 |
| g_trim | -0.6467 | -0.6513 |
| x_apex_frac | 0.3324 | 0.3277 |
| g_stall_speed | -2.466e-06 | 4.441e-16 |
| g_span | 0.01875 | -0.1194 |
| g_mtow | -0.0632 | -2.683e-12 |

Ativas: g_stall_speed, g_mtow; calibração: β = CD0_lowfi/CD0_manual = 1.089, K_lowfi/K_manual = 0.730 no ponto base; CLmax limpo 1.292 (XFOIL). Restrições g ≤ 0 (g = requisito/valor − 1).

## Pipeline completo: base vs ótimo aceite

| grandeza | base | ótimo |
|---|---|---|
| W0 [kg] | 23.42 | 24.25 |
| We [kg] | 11.69 | 11.69 |
| Wf/bateria [kg] | 7.731 | 8.561 |
| W/S [N/m²] | 175.6 | 175.6 |
| P/W [W/N | -] | 5.155 | 5.168 |
| AR | 14 | 12.98 |
| S [m²] | 1.308 | 1.354 |
| b [m] | 4.279 | 4.192 |
| CD0 | 0.02316 | 0.02258 |
| (L/D)max | 20.69 | 20.28 |
| energia bateria [Wh] | 1766 | 1955 |
| P_SL [kW] | 1.184 | 1.229 |
| caixão da asa [kg] | 3.624 | 3.735 |
| asa (pesos) [kg] | 4.658 | 4.612 |
| alcance (segmentos) [km] | 214 | 228.5 |
| autonomia (segmentos) [h] | 2.769 | 2.947 |
| margem divergence vs 1.2 V_D | 7.657 | 8.094 |
| margem reversal vs 1.2 V_D | ∞ | ∞ |
| margem flutter vs 1.2 V_D | 2.931 | 3.136 |
| viável (dimensionamento) | não | sim |
| verificado (fase 2/3) | não | não |
| falhas | wing_span, hq:CAP | hq:CAP |

Notas: o SLSQP só vê W/S, P/W e AR, com o motor, o ESC e a célula fixos (Geoffrion, J. Optim. Theory Appl. 10, 1972: o subproblema contínuo não atravessa a atribuição inteira). Um passo de catálogo à parte reescolhe o mais leve que cumpre a potência e a corrente, e só é aceite se o mérito do pipeline melhora e não há verificações novas a falhar. Não há catálogo de hélices: o diâmetro segue Raymer Sec. 10.3. Os servos continuam a ser reescolhidos no fecho. As verificações hq:/aeroel: não são restrições do MDO (omissão = filtro pós-ótimo legado; ativar com `assumptions.mdo.hq_aeroel_constraints: true`) — ver as falhas na tabela.

Relatórios completos: `baseline/report.md`, `optimum/report.md`.
