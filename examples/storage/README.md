<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Energia comum L0

Executar da raiz: `PYTHONPATH=src python examples/storage/check_examples.py`.
Usa consumos reais dos modelos existentes, grava produtores e balanços em
`out/storage/examples/` e proveniência em `runs/` (ou `ACDT_RUNS_DIR`).

`prop_mission.yaml`/`electric_mission.yaml`: perfis curtos pointmass hipotéticos;
`fuel_prop.yaml`/`electric.yaml`: armazenamento correspondente. `jet.yaml` reutiliza
`examples/jet/coupled_size.yaml`; a carga é o resultado desse fecho em 8105d18,
não uma capacidade de A320 publicada. `vtol.yaml` verifica o candidato de 25 kg
com a missão PRESSUPOSTO existente do `size_vtol`. Densidade, rating e volumes
instalados/alocados são PRESSUPOSTOS explícitos, não dados de fornecedor.

Não há novo simulador de jato/VTOL ou política híbrida. Passar capacidade não
valida o produtor, potência desconhecida, ajuste 3-D, CG ou fecho de massa.
Ver [tutorial](../../docs/tutorial-energy-storage.md).
