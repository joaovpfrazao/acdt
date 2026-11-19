# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0

# Proposta: RCS de onda completa

Estado em 18 nov 2026, ramo `rcs-onda-completa-proposta`. Nada foi corrido. Não se escreveu malha
FDTD. O PO não fica validado nem calibrado. A comparação fica `nao_avaliado`. Decisão `nao_aplicar`.
O yaml dos exemplos não muda.

Registo: `examples/output/rcs_onda_completa_proposta/proposta.json` e `proposta.csv`.

## Malha

O registo de duas reflexões (`h6_rcs_bounces2.json`) é Óptica Física a 10 GHz, 192 facetas no loft
da asa sem deriva. Isso não é uma grelha de onda completa. λ = c/f com c = 299 792 458 m/s, o valor
já em `core/em/po.py`, e f = 10 GHz, a frequência de `rcs.study.FREQ_DEFAULT`. λ = 0,029979 m.

PRESSUPOSTO: dez células por comprimento de onda, Δx = λ/10 = 2,998 mm, é uma grelha de trabalho
para FDTD. Não é uma demonstração de convergência. A caixa de cálculo e os sólidos que o PO deixa
por avaliar (fuselagem, derivas de ponta, trem, hélice) não estão fechados, por isso o número de
células fica em falta e não é zero.

## Solver

O candidato já listado em `THIRD_PARTY.md` é o openEMS, GPL-3.0, só como executável externo.
Não foi instalado e o processo acdt não o importa. `core/em/po.py` também nomeia MoM/MLFMM.
Não há binário escolhido para essa classe.

## Custo

Sem a malha, não há GB nem horas. A estimativa de 0,05 GB do PO não é o custo da onda completa.
`tools.budget` continua a recusar uma corrida acima de 70 % da RAM livre ou de 45 min.

## Comparação

A média frontal VV com duas reflexões é a do ficheiro já guardado, −7,491 dBsm. Não é a mesma
grandeza que uma RCS de onda completa, por isso não há razão. Não há RCS medido no repositório.

## Estado das cinco tarefas

O PR #23 está no `main` (`5c58b68`). Os outros quatro continuam abertos. Este ramo não os integra.

1. PR #23, `win-openvsp-esteira`, integrado. OpenVSP 3.56 no Windows. O painel grosso acabou com a
   esteira nos defaults lidos de volta. O L1 AVL fica `nao_aplicar`: não validado e sem calibração.
2. PR #24, `pycycle-sem-ajuste`, aberto. A etiqueta 4.4.0 com OpenMDAO 3.41.0 e NumPy 1.26.4
   imprime o turbojato sem editar `ThermoAdd`. O L0 fica `nao_aplicar`. O L1 fica `nao_avaliado`
   porque o deck não existe. O gráfico final não correu.
3. PR #25, `c172-rans-asa-fuselagem`, aberto e bloqueado. A fórmula já registada dá 21,731 GB e
   40,24 h, com 2415 min contra 45 min. A primeira medição tinha 16,32 GB livres e limite 11,42 GB.
   Nova leitura: 16,34 GB livres de 31,86 GB, limite 11,44 GB. O solver não arrancou e a malha
   não foi engrossada. O L1 fica `nao_avaliado`.
4. PR #26, `termico-gelo-proposta`, aberto. Só proposta, sem sólido e sem corrida. O L0 e o L1
   ficam `nao_avaliado`.
5. PR #27, este ramo, aberto. Só proposta. O openEMS não arrancou. O PO fica `nao_avaliado` face à onda completa.
