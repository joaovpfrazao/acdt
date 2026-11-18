## Avaliação de segurança (ARP4761 simplificada) — esquema stanag4671

Referência dos alvos: STANAG 4671 Ed. 1 USAR.1309 / AMC.1309 (Annex A definitions). Duração de voo considerada T = 10 h (P/h de voo = P(T)/T).

Opções de arquitetura: servos por eixo (superfície dividida) = dual, computador de voo = dual, bateria de reserva = True

| CF | condição de falha | severidade | alvo [/h] | P [/h] | falha única | estado |
|---|---|---|---|---|---|---|
| FC-U1 | perda de controlo da aeronave | catastrófica | 1e-06 | 3.81e-06 | — | não cumpre |
| FC-U2 | perda de propulsão (aterragem forçada) | perigosa | 1e-05 | 9.95e-04 | engine | não cumpre |
| FC-U3 | perda de controlo direcional (leme) | maior | 1e-04 | 2.59e-06 | — | cumpre |
| FC-U4 | perda da ligação C2 (comando e controlo) | maior | 1e-04 | — | — | em aberto |

Soma das condições catastróficas: 3.81e-06 /h vs 1.00e-05 (STANAG 4671 AMC.1309 (alternativa: soma ≤ 1e-5)) → cumpre

MTBF requerido do componente dominante (para cumprir o alvo, restantes inalterados):
- FC-U1: uav_servo → inatingível só com uav_servo; todas as taxas da árvore teriam de baixar ×0.51 (MTBF ×1.96)
- FC-U2: uav_two_stroke_engine → 1e+05 h (atual 1e+03 h)

Notas:
- FC-U4: sem taxa de falha pública da ligação C2 — depende do rádio, do espetro e do procedimento de perda de ligação (OSO#06); estado em aberto

### Estudo de redundância (opções de projeto)

| opções | Δm [kg] | ΔW0 [kg] | Δcusto | pior P/alvo | cumpre |
|---|---|---|---|---|---|
| servo=single, fcc=simplex, backup_battery=False | -1.50 | -3.16 | n/d | 1.7e+03 | não |
| servo=single, fcc=dual, backup_battery=False | -1.49 | -3.14 | n/d | 1.6e+03 | não |
| servo=single, fcc=triplex, backup_battery=False | -1.48 | -3.12 | n/d | 1.6e+03 | não |
| servo=dual, fcc=simplex, backup_battery=False | -0.60 | -1.27 | n/d | 1.2e+03 | não |
| servo=dual, fcc=dual, backup_battery=False | -0.59 | -1.24 | n/d | 1.1e+03 | não |
| servo=dual, fcc=triplex, backup_battery=False | -0.58 | -1.22 | n/d | 1.1e+03 | não |
| servo=single, fcc=simplex, backup_battery=True | 0.00 | 0.00 | 0 | 6.1e+02 | não |
| servo=single, fcc=dual, backup_battery=True | 0.01 | 0.02 | n/d | 5.1e+02 | não |
| servo=single, fcc=triplex, backup_battery=True | 0.02 | 0.04 | n/d | 5.1e+02 | não |
| servo=dual, fcc=simplex, backup_battery=True | 0.90 | 1.90 | n/d | 1e+02 | não |
| servo=dual, fcc=dual, backup_battery=True | 0.91 | 1.92 | n/d | 1e+02 | não |
| servo=dual, fcc=triplex, backup_battery=True | 0.92 | 1.94 | n/d | 1e+02 | não |

**Selecionado:** servo=dual, fcc=dual, backup_battery=True — NENHUM conjunto de opções cumpre — escolhido o com menos condições em incumprimento; requer componentes mais fiáveis (ver MTBF requerido).
Entradas em falta (não contabilizadas): fcc_cost, servo_cost.

## FMEA

| componente | λ_modo [1/h] | efeito no sistema (condição de falha) | severidade | ponto único de falha | tipo de dado |
|---|---|---|---|---|---|
| motor de combustão | 0.001 | FC-U1, FC-U2 | catastrófica | não | assumption |
| gerador acionado pelo motor | 0.000132 | FC-U1 | catastrófica | não | published |
| computador de voo 1 | 0.0001 | FC-U1 | catastrófica | não | assumption |
| computador de voo 2 | 0.0001 | FC-U1 | catastrófica | não | assumption |
| servo profundor 1 | 0.0005 | FC-U1 | catastrófica | não | vendor_claim |
| cablagem profundor 1 | 1e-05 | FC-U1 | catastrófica | não | assumption |
| servo profundor 2 | 0.0005 | FC-U1 | catastrófica | não | vendor_claim |
| cablagem profundor 2 | 1e-05 | FC-U1 | catastrófica | não | assumption |
| servo aileron esq. 1 | 0.0005 | FC-U1 | catastrófica | não | vendor_claim |
| cablagem aileron esq. 1 | 1e-05 | — | sem efeito | não | assumption |
| servo aileron esq. 2 | 0.0005 | FC-U1 | catastrófica | não | vendor_claim |
| cablagem aileron esq. 2 | 1e-05 | — | sem efeito | não | assumption |
| servo aileron dir. 1 | 0.0005 | FC-U1 | catastrófica | não | vendor_claim |
| cablagem aileron dir. 1 | 1e-05 | — | sem efeito | não | assumption |
| servo aileron dir. 2 | 0.0005 | FC-U1 | catastrófica | não | vendor_claim |
| cablagem aileron dir. 2 | 1e-05 | — | sem efeito | não | assumption |
| servo leme 1 | 0.0005 | FC-U3 | maior | não | vendor_claim |
| cablagem leme 1 | 1e-05 | FC-U3 | maior | não | assumption |
| servo leme 2 | 0.0005 | FC-U3 | maior | não | vendor_claim |
| cablagem leme 2 | 1e-05 | FC-U3 | maior | não | assumption |
| bateria de reserva | 0.0001 | FC-U1 | catastrófica | não | assumption |
