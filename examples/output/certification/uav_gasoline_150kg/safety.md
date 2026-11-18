## Avaliação de segurança (ARP4761 simplificada) — esquema stanag4703

Referência dos alvos: STANAG 4703 (AEP-83) UL.30 + Annex G (cumulative catastrophic). Duração de voo considerada T = 10 h (P/h de voo = P(T)/T).

Opções de arquitetura: servos por eixo (superfície dividida) = dual, computador de voo = dual, bateria de reserva = True

| CF | condição de falha | severidade | alvo [/h] | P [/h] | falha única | estado |
|---|---|---|---|---|---|---|
| FC-U1 | perda de controlo da aeronave | catastrófica | 1e-05 | 3.81e-06 | — | cumpre |
| FC-U2 | perda de propulsão (aterragem forçada) | perigosa | — | 9.95e-04 | engine | sem alvo |
| FC-U3 | perda de controlo direcional (leme) | maior | — | 2.59e-06 | — | sem alvo |
| FC-U4 | perda da ligação C2 (comando e controlo) | maior | — | — | — | em aberto |

Soma das condições catastróficas: 3.81e-06 /h vs 1.10e-05 (STANAG 4703 Annex G) → cumpre

Notas:
- FC-U4: sem taxa de falha pública da ligação C2 — depende do rádio, do espetro e do procedimento de perda de ligação (OSO#06); estado em aberto

### Estudo de redundância (opções de projeto)

| opções | Δm [kg] | ΔW0 [kg] | Δcusto | pior P/alvo | cumpre |
|---|---|---|---|---|---|
| servo=single, fcc=simplex, backup_battery=False | -1.50 | -3.18 | n/d | 1.6e+02 | não |
| servo=single, fcc=dual, backup_battery=False | -1.49 | -3.16 | n/d | 1.5e+02 | não |
| servo=single, fcc=triplex, backup_battery=False | -1.48 | -3.14 | n/d | 1.5e+02 | não |
| servo=dual, fcc=simplex, backup_battery=False | -0.60 | -1.27 | n/d | 1.1e+02 | não |
| servo=dual, fcc=dual, backup_battery=False | -0.59 | -1.25 | n/d | 1e+02 | não |
| servo=dual, fcc=triplex, backup_battery=False | -0.58 | -1.23 | n/d | 1e+02 | não |
| servo=single, fcc=simplex, backup_battery=True | 0.00 | 0.00 | 0 | 56 | não |
| servo=single, fcc=dual, backup_battery=True | 0.01 | 0.02 | n/d | 47 | não |
| servo=single, fcc=triplex, backup_battery=True | 0.02 | 0.04 | n/d | 47 | não |
| servo=dual, fcc=simplex, backup_battery=True | 0.90 | 1.91 | n/d | 9.4 | não |
| servo=dual, fcc=dual, backup_battery=True | 0.91 | 1.93 | n/d | 0.35 | sim |
| servo=dual, fcc=triplex, backup_battery=True | 0.92 | 1.95 | n/d | 0.36 | sim |

**Selecionado:** servo=dual, fcc=dual, backup_battery=True — conjunto mais leve que cumpre todos os alvos quantitativos e a regra de falha única.
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
