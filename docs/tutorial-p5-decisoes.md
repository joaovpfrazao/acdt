# Tutorial P5 — Registo de decisões

## O que faz

Cada decisão de design fica escrita com (DESIGN_WORKFLOW §6–7):

* o que se decidiu e **porquê** (resultados de ferramentas citados);
* o **nível de fidelidade** (N0–N3 / L0–L1…);
* as **alternativas rejeitadas** e o motivo (set-based: guardam-se para reabrir);
* as **condições de invalidação** (métrica + operador + valor, ou desvio percentual face a um baseline).

Quando um resultado posterior cumpre uma condição, `decisions check --reopen` marca a decisão
`open` e a IA reavalia as alternativas guardadas.

## CLI

```bash
export PYTHONPATH=src
acdt decisions open output/decisions_isr --title "ISR N1"
acdt decisions add output/decisions_isr --input examples/decisions/seed_n1.json
acdt decisions check output/decisions_isr --metrics /tmp/m.json          # só reporta
acdt decisions check output/decisions_isr --metrics /tmp/m.json --reopen # reabre
acdt decisions gate output/decisions_isr --level N1 --metrics examples/decisions/gate_n1_pass.json
acdt decisions gate output/decisions_isr --level N1 --metrics examples/decisions/gate_n1_fail.json --reopen
acdt decisions gate output/decisions_isr --level N1 --metrics examples/decisions/gate_n1_unassessed.json
acdt decisions list output/decisions_isr
acdt decisions report output/decisions_isr
```

### Gate de fim de nível (opt-in, DESIGN_WORKFLOW §7)

O JSON de `--metrics` pode trazer `metrics` + `checks` (`ok: true|false|null`). Resultado:

| status | significado |
|--------|-------------|
| `pass` | decisões do nível fechadas, condições avaliadas sem invalidação, checks ok |
| `fail` | invalidação, check falhado, ou decisão ainda `open` |
| `unassessed` | métrica de condição ausente, check `ok: null`, ou nenhuma decisão no nível |

Unassessed ≠ pass. O gate **não** escolhe um vencedor ponderado; com `--reopen` marca
decisões invalidadas como `open` e devolve `rejected_reevaluation` para o agente voltar a
correr `morph_evaluate` / `size` / `compare_alternatives`.

### UQ no gate (opt-in, P7)

```bash
acdt decisions gate output/decisions_isr --level N1 \
  --metrics examples/decisions/gate_n1_uq_pass.json --require-uq
```

O JSON pode trazer `uq` (resumo MC/Sobol com `summaries` / `gate_metrics` /
`interval_checks`). Com `--require-uq`, UQ em falta ou `status: unassessed` impede o pass.

Exemplo de métricas:

```json
{"radar_mass_kg": 30, "CL_alpha": 4.4, "baseline_CL_alpha": 5.0}
```

## MCP

`decisions_open`, `decisions_add`, `decisions_check`, `decisions_gate`, `decisions_list`,
`decisions_report`.

## Limites

* O registo / gate **não decide** — só grava, classifica e assinala o que reabrir.
* A reavaliação das alternativas é do agente (voltar a `morph_evaluate` / `size` /
  `compare_alternatives`); sem auto-vencedor ponderado.
* Condições só com métricas numéricas planas; checks têm de ser fornecidos.
* CLI/MCP antigos (`check` sem `gate`) inalterados.
