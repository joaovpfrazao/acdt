<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Referência de transporte a jato L0

`a320_ref.json` guarda números públicos e proveniência por campo (consulta: 6 nov 2026).
`transport_l0.yaml` permite repetir o orçamento de massa e o ponto de cruzeiro.
Não é um conjunto de dados certificado nem uma variante única: OEW, massa máxima,
empuxo e alcance dependem da configuração. Mach e alongamento são derivados;
perfil equivalente, polar, VC e reservas são **PRESSUPOSTOS**.

```sh
acdt jet check --input examples/jet/a320_ref.json -o output/jet_check.json
acdt jet analyse --input examples/jet/transport_l0.yaml -o output/jet_analyse.json
```

O check compara apenas We estatístico com OEW, com tolerância **PRESSUPOSTO** de 25%.
Mostra também margens de empuxo e de massa; não valida independentemente o alcance
nem o deck do motor. We e OEW têm definições diferentes. Não constitui prova CS-25.

## Fecho acoplado (semente de estudo, não referência publicada)

```sh
acdt jet size --input examples/jet/coupled_size.yaml -o output/jet_size.json
```

A carga útil, alcance de projeto e limite de MTOW desta semente são PRESSUPOSTOS,
não dados validados de um A320. Avalia uma alternativa de asa/motores dados;
a massa muda, o CL/CDonda/L/D muda e a queima é integrada por Breguet diferencial.
O resultado separa convergência, empuxo disponível e restrição MTOW, sem
escolher arquitetura nem redimensionar componentes. Ver tutorial para limites.

## Triagem L0 de corrida, subida e OEI

```sh
acdt jet performance --input examples/jet/performance_l0.yaml -o out/jet_performance.json
```

Mesma massa fechada; cenários e coeficientes de configuração explicitamente
PRESSUPOSTO. Não são dados de voo nem uma configuração A320 validada. O exemplo
só compara corrida AEO, sustentação e gradientes estacionários com objetivos de
engenharia; referências numéricas 25.121 não recebem aprovação regulamentar.
Distância total de descolagem, V1/VMC/V2 e balanced field ficam não avaliados.

## Engine maps (opt-in)

`engine_map_table.yaml` — same transport candidate as `coupled_size.yaml` with a
PRESSUPOSTO Mach/altitude/throttle table. Cruise Π=1 reproduces the default
Mattingly/Ihme closure (MTOW ≈ 67856 kg). Part power uses a worse TSFC from the
table. Out-of-domain queries return `unassessed` (no silent extrapolation).
Does **not** run pyCycle/NPSS/GasTurb/T-MATS.
