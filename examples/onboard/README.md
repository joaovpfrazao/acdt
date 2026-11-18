<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Exemplos transversais de carga útil/elétrica

Todos os novos números são **PRESSUPOSTOS ilustrativos**, não dados de fornecedor nem
validação de um avião real. `jet.yaml` reutiliza a alternativa de transporte já existente;
os restantes usam requisitos explícitos/hipóteses nativas em baixa fidelidade.

`PYTHONPATH=src python examples/onboard/check_examples.py` corre três casos por caminho:
baseline, potência/pico elétricos duplicados, mais 1 kg de payload. Regista resultados e
run ids em `out/onboard/examples/comparisons.json`. Não seleciona uma arquitetura.

* Jato/hélice: mais massa altera o fecho. Gerador exige modelo incremental fornecido;
  não foi inferido BSFC de acessórios nem um mapa de motor.
* Elétrico: hotel afeta energia e pack/MTOW. Pico combinado do pack prop ainda por avaliar.
* VTOL: MTOW mantém-se 25 kg inclusivos; mais payload consome margem do orçamento.
  Mais carga elétrica aumenta energia/pico e pode aumentar o pack por C-rate.
* O caso jato com pico duplicado ultrapassa intencionalmente os 10 kW alocados ao bus
  (a eficiência 0,9 exige 11,11 kW): deve falhar esse check, mesmo convergindo a massa.
* Sem geometria/CG/FOV/calor/volumes, o agregado fica `null`, nunca aprovação global.

CLI: `PYTHONPATH=src acdt onboard size --input examples/onboard/jet.yaml`.
Retorno 1 em resultados parciais/inviáveis é intencional. Ver
[contrato de contabilização e limites](../../docs/tutorial-onboard.md).


## `acdt size` com hotel (fecho automático)

Bloco `onboard` na missão → massa + hotel fecham **dentro** de `acdt size` / `jet_size` /
`size_vtol` (sem passo `onboard_size` separado). Relatório em `onboard_bridge` no summary/JSON.

* `prop_size_radar_hotel.yaml` — missão piston com radar/alternador PRESSUPOSTO; o hotel
  altera combustível via `onboard_bridge` (não inventa W Gabbiano).
* `prop_size_baseline_no_hotel.yaml` — gémeo sem `onboard` (Wf/W0 mais baixos; legado).
* Specs `jet` / `vtol` podem carregar o mesmo bloco `onboard` directamente em
  `jet_size` / `size_vtol` (ver `tests/test_onboard_bridge.py`).
