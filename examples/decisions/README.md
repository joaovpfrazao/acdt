<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Exemplos P5 — registo de decisões


## Gate de fim de nível (opt-in, 10 nov 2026)

```bash
export PYTHONPATH=src
acdt decisions open /tmp/dec_n1 --title "ISR N1"
acdt decisions add /tmp/dec_n1 --input examples/decisions/seed_n1.json
acdt decisions gate /tmp/dec_n1 --level N1 --metrics examples/decisions/gate_n1_pass.json
acdt decisions gate /tmp/dec_n1 --level N1 --metrics examples/decisions/gate_n1_fail.json --reopen
acdt decisions gate /tmp/dec_n1 --level N1 --metrics examples/decisions/gate_n1_unassessed.json
```

Status: `pass` | `fail` | `unassessed`. Métrica ausente ou `ok: null` ≠ pass.
Com `--reopen`, decisões invalidadas abrem e as rejeitadas são listadas para reavaliar
(sem escolher vencedor ponderado).

## Gate + UQ (P7, 10 nov 2026)

```bash
acdt decisions gate /tmp/dec_n1 --level N1 --metrics examples/decisions/gate_n1_uq_pass.json --require-uq
acdt decisions gate /tmp/dec_n1 --level N1 --metrics examples/decisions/gate_n1_uq_fail.json --require-uq
acdt decisions gate /tmp/dec_n1 --level N1 --metrics examples/decisions/gate_n1_uq_unassessed.json --require-uq
```
