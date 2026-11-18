## Avaliação de segurança (ARP4761 simplificada) — esquema ac23_1309_class_I

Referência dos alvos: FAA AC 23.1309-1E (2011) Fig. 2. Duração de voo considerada T = 1 h (P/h de voo = P(T)/T).

Opções de arquitetura: altímetro de reserva = True, indicador de atitude de reserva (elétrico) = False

| CF | condição de falha | severidade | alvo [/h] | P [/h] | falha única | estado |
|---|---|---|---|---|---|---|
| FC-A1 | perda total de indicação de atitude (IFR) | catastrófica | 1e-06 | 3.09e-07 | — | cumpre |
| FC-A2 | perda da atitude primária | maior | 1e-04 | 6.50e-04 | ai, vac | não cumpre |
| FC-A3 | perda total de indicação de altitude | perigosa | 1e-05 | 3.31e-08 | — | cumpre |
| FC-A4 | perda total de indicação de velocidade | maior | 1e-04 | 6.88e-05 | asi, pitot | cumpre |
| FC-A5 | perda total de indicação de rumo | maior | 1e-04 | — | — | em aberto |
| FC-A6 | perda de potência do motor (informativo — 23.2100/2405, não 1309) | informativo | — | 1.27e-04 | engine | sem alvo |

MTBF requerido do componente dominante (para cumprir o alvo, restantes inalterados):
- FC-A2: attitude_indicator → inatingível só com attitude_indicator; todas as taxas da árvore teriam de baixar ×0.15 (MTBF ×6.5)

Notas:
- FC-A1: AC 23.1309-1E Apêndice 1 (IFR); o coordenador de volta conta como fonte de atitude de reserva (PRESSUPOSTO conservador do acdt)
- FC-A4: estático alternativo/aquecimento do pitot não modelados
- FC-A5: bússola magnética sem taxa de falha publicada na base de dados (NASA GARS não a lista); giro direcional + vácuo isolados = limite superior conservador

### Estudo de redundância (opções de projeto)

| opções | Δm [kg] | ΔW0 [kg] | Δcusto | pior P/alvo | cumpre |
|---|---|---|---|---|---|
| standby_altimeter=False, standby_attitude=False | 0.00 | 0.00 | 0 | 18 | não |
| standby_altimeter=True, standby_attitude=False | 0.37 | 0.71 | n/d | 6.5 | não |
| standby_altimeter=False, standby_attitude=True | 0.73 | 1.40 | n/d | 18 | não |
| standby_altimeter=True, standby_attitude=True | 1.10 | 2.11 | n/d | 6.5 | não |

**Selecionado:** standby_altimeter=True, standby_attitude=False — NENHUM conjunto de opções cumpre — escolhido o com menos condições em incumprimento; requer componentes mais fiáveis (ver MTBF requerido).
Entradas em falta (não contabilizadas): altimeter_cost.

## FMEA

| componente | λ_modo [1/h] | efeito no sistema (condição de falha) | severidade | ponto único de falha | tipo de dado |
|---|---|---|---|---|---|
| indicador de atitude (vácuo) | 0.0004 | FC-A1, FC-A2 | catastrófica | não | published |
| bomba de vácuo | 0.00025 | FC-A1, FC-A2 | catastrófica | não | published |
| coordenador de volta (elétrico) | 0.000476 | FC-A1 | catastrófica | não | published |
| altímetro | 0.000182 | FC-A3 | perigosa | não | published |
| indicador de velocidade | 5.52e-05 | FC-A4 | maior | não | published |
| tubo de pitot | 1.36e-05 | FC-A4 | maior | não | published |
| giro direcional (vácuo) | 0.000294 | — | sem efeito | não | published |
| alternador | 0.000132 | — | sem efeito | não | published |
| motor (Lycoming, ATSB) | 0.000127 | FC-A6 | sem efeito | não | published |
| altímetro de reserva | 0.000182 | FC-A3 | perigosa | não | published |
