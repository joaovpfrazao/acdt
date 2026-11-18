# Tutorial — estudo conceptual a partir de um problema (pesca ilegal)

Este tutorial segue o exemplo `examples/concept/illegal_fishing/`. Mostra como um agente de IA, só com as
ferramentas do acdt, passa de uma frase do utilizador para uma arquitetura de frota recomendada. Para o guia de
referência, ver [ai-concept-trade.md](ai-concept-trade.md).

## 0. Como pedir

No Cursor, com o servidor MCP `acdt`, basta escrever o problema:

> "Quero vigiar esta área de mar porque há barcos estrangeiros a fazer pesca ilegal."

O agente usa o prompt `concept_trade` e não te pede um formulário. Pergunta só o que mudaria a resposta e,
enquanto esperas, avança com pressupostos explícitos.

Para reproduzir o exemplo:

```
python examples/concept/illegal_fishing/run_study.py        # ~1,5 min (dimensionamento L0)
acdt concept replay examples/output/concept/illegal_fishing/study.json --with-sizing
```

## 1. Interpretação, pressupostos e perguntas

O agente interpretou a necessidade como **detetar, seguir e identificar** embarcações, com a abordagem feita
por outra entidade. A cadeia de missão é radar marítimo (área larga, dia e noite, sem depender do AIS) →
correlação AIS/VMS → EO/IR para identificação.

Como a área não foi dada, o agente assumiu (PRESSUPOSTO) um retângulo de 38,9–40,1 N × 10,9–9,7 W, com base em
BA5 Monte Real. Deixou cinco perguntas ao utilizador: a área real, se é 24/7 ou por períodos, os meios que já
existem, o orçamento e as bases.

## 2. Requisitos derivados (com as ferramentas)

* `geo_measure`: área de **13 738 km²**, base a **126 km** do centro, largura E–W de **103 km**.
* `transit_time` de uma embarcação a 10 kn sobre 103 km dá **5,56 h**: é a janela de deteção.
  * **REQ1:** POD ≥ 0,9 nessa janela, com pesquisa aleatória de Koopman (conservadora).
* **REQ2:** presença 24/7, com P(frota suficiente) ≥ 0,95 (binomial k-de-N).
* **REQ3:** identificação de um barco de 15 m. `johnson_range` mostra que, com IFOV de 0,1 mrad, o alcance de
  identificação é de cerca de 11,7 km. O datasheet da câmara ainda tem de ser verificado.
* `radar_horizon`: o horizonte é de 235 km a 3000 m e de 110 km a 600 m. A deteção é limitada pelo alcance do
  radar (20–44 km), não pelo horizonte.

## 3. Alternativas

| id | alternativa |
|---|---|
| A1 | 1 aeronave L, sem continuidade |
| A2 / A3 | L (radar NSP-7) com 1 ou 2 estações 24/7 |
| A4 / A5 | M (radar NSP-2) com 2 ou 3 estações |
| A6 | misto: 1 estação L + 1 estação M |
| A7 | S elétrico de 25 kg lançado de navio (o custo do navio não está incluído) |
| X1–X6 | não avaliáveis: aeróstato, satélite + aeronave, avião tripulado, VTOL, HALE, USV |

As variantes L, M e S são especificações YAML escritas pelo agente, com as massas de payload tiradas de
datasheets públicos (IMSAR, Trillium).

## 4. Avaliação

`size_fleet` (L0) dimensionou uma aeronave de cada tipo:

| variante | W0 | endurance | custo unitário (N=50, CER) | perda por surtida (ARP4761 low-fi) | verificações falhadas |
|---|---|---|---|---|---|
| L | 127,9 kg | 16,4 h | 184 k$ | 0,028 | trim, HQ, W&B, trem |
| M | 92,4 kg | 10,6 h | 163 k$ | 0,018 | HQ, W&B, trem |
| S | 23,6 kg | 2,7 h | 42 k$ | 0,005 | envergadura, HQ, W&B, endurance por segmentos |

Depois, `persistent_coverage` deu o número de aeronaves por estação (2 para L e M), a frota para 95 % com
A = 0,85, e as surtidas e horas de voo por dia. `sweep_coverage` deu a POD na janela.

## Busca de barreira (opt-in)

Para um evasor que tem de cruzar uma linha ou corredor (Koopman / Washburn), use `barrier_search` ou:

```bash
acdt concept barrier --input examples/concept/barrier_patrol_demo.json -o output/barrier_demo.json
```

Sem `sweep_width_km` a POD fica **unassessed** (não inventar o W do Gabbiano). `sweep_coverage` /
`persistent_coverage` sem o modo barreira ficam inalterados.


## 5. Comparação (Pareto, sem pesos)

| alt. | aeronaves | aquisição | POD janela | P(frota) | h voo/dia |
|---|---|---|---|---|---|
| A1 | 1 | 0,18 M$ | 0,55 | 0 | 16 |
| A2 | 4 | 0,74 M$ | 0,74 | 0,99 | 27 |
| **A3** | **6** | **1,10 M$** | **0,93** | **0,95** | **54** |
| A4 | 6 | 0,98 M$ | 0,73 | 0,95 | 59 |
| A5 | 9 | 1,46 M$ | 0,86 | 0,97 | 89 |
| A6 | 8 | 1,39 M$ | 0,86 | 0,98 | 57 |
| A7 | 6 (+ navio) | 0,25 M$ | 0,47 | 0,95 | 69 |

Só A3 cumpre REQ1 e REQ2. Sem restrições, a frente custo–POD é A1 → A2 → A3 (`pareto_sem_restricoes.png`):
cada passo compra mais POD, e A4–A7 são dominadas.

## 6. Sensibilidades e recomendação

* Com uma largura de varrimento do NSP-2 de 20 km (em vez de 10 km), A4 passa a POD 0,93. Isto tornaria a
  frota de aeronaves M competitiva com A3 e mais barata. É o dado a pedir ao fabricante.
* Com A = 0,70, A3 precisa de 9 aeronaves em vez de 6.
* Se a janela for de 12 h (barco a pescar, não em trânsito), uma estação L chega (A2, POD 0,94).
* Com varrimento paralelo planeado (otimista), uma estação L já dá POD 1.
* A atrição prevista com as taxas genéricas do template ARP4761 low-fi (cerca de 36 perdas/ano em A3) domina o
  custo de ciclo de vida. Tem de ser substituída por dados reais de fiabilidade.

**Recomendação (conceptual):** A3, com 6 aeronaves L em 2 estações 24/7, cerca de 1,1 M$ de aquisição (CER
de baixa confiança). Ressalvas:
* a variante L ainda tem verificações falhadas (trim, HQ, W&B, trem) a corrigir em L1;
* a opção satélite + aeronave (X2) pode reduzir muito a frota e deve ser avaliada a seguir.

## 7. Repetir com outros pressupostos

Muda um pressuposto no script (por exemplo `W["M"]`, a disponibilidade ou a área) e volta a correr.
Alternativamente, pede ao agente: *"refaz com a área X e só período noturno"*. O agente regista os novos
pressupostos e chamadas num novo estudo.


## MTOW: `size_fleet` e `acdt size`

Até 9 nov 2026, `size_fleet` usava `level=L0` por omissão e podia discordar de `acdt size` na mesma missão
YAML com `fidelity: lowfi` (ex.: +4,8 kg no UAV 150 kg, +7,5 kg na variante L de pesca ilegal). Agora:

* sem `level` → mesma fidelidade que `acdt size`;
* com `level` → diferença explícita em `mtow_alignment` / `compare_size_fleet_mtow`;
* ver `examples/concept/size_fleet_mtow_align.md`.
