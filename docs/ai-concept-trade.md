# Estudo conceptual conduzido pela IA (concept trade)

O utilizador descreve um **problema**, não um avião. Por exemplo: *"quero vigiar esta área de mar porque há
barcos estrangeiros a fazer pesca ilegal"*. A partir daí, o agente de IA trata de tudo:

* define a missão;
* deriva requisitos mensuráveis;
* gera arquiteturas alternativas (1 grande, várias pequenas, 2 médias, mistas, criativas);
* avalia-as;
* recomenda uma ao nível conceptual.

**O raciocínio é da IA; os números são das ferramentas.** O acdt não tem um esquema fixo de entradas
("tempo no local, carga, …") nem heurísticas que escolham a arquitetura. Cada problema é diferente e é a IA que
decide o que importa. Em troca, cada decisão fica escrita, justificada e auditável.

O prompt MCP `concept_trade` (`src/acdt/ai/prompts/concept_trade.md`) contém o fluxo completo que o agente
segue. Este documento resume-o para quem o revê.

## Princípios

1. **Primitivas determinísticas e citadas, compostas pela IA.** As ferramentas recebem dicionários e devolvem
   dicionários. Cada uma devolve `method` (a referência) e `validity` (os limites de validade). Não há uma
   ferramenta genérica de "avaliar expressão".
2. **Não inventar números.** Cada valor é um resultado de ferramenta, um dado pesquisado com URL e data, ou um
   **PRESSUPOSTO** com justificação. A IA pesquisa na web os dados atuais: datasheets de sensores, o
   comportamento do alvo, a geografia e os preços. O repositório não guarda esses dados.
3. **Sem pesos por omissão.** A comparação é uma frente de Pareto com os requisitos como restrições. Só há
   pontuação ponderada se a IA (ou o utilizador) der os pesos, e nesse caso cada termo normalizado é mostrado.
4. **Alternativas não avaliáveis também contam.** Aeróstato, satélite, VTOL, mothership, HALE… ficam
   registados com `evaluable=false` e o motivo.
5. **Rasto de auditoria.** Com `study_id`, cada chamada fica registada (argumentos e resultado) em
   `study.json`. O comando `acdt concept replay` volta a correr as chamadas e confirma que dão o mesmo
   resultado.

## Ferramentas (MCP)

| ferramenta | o que calcula | método |
|---|---|---|
| `concept_study_start` / `concept_study_add` / `concept_study_report` | registo do estudo, que gera report.md e study.json | INCOSE SE Handbook 4.ª ed. (rastreabilidade) |
| `geo_measure` | distâncias de grande círculo e área de polígono | Sinnott 1984; Chamberlain & Duquette 2007 (JPL 07-03) |
| `transit_time` | ida, volta e trânsito com vento | cinemática |
| `sweep_coverage` | taxa de varrimento W·V, tempo para varrer a área e POD no tempo t (pesquisa aleatória e varrimento paralelo) | Koopman 1946/1980; Washburn 2002 |
| `barrier_search` | patrulha de barreira: z=n·W·V/(L·u), POD, revisitação τ=2L/(n·V), fecho cookie-cutter, frota Ha 2010 opcional; inputs em falta → unassessed | Koopman 1946/1980; Washburn 2002; Ha 2010 |
| `persistent_coverage` | tempo na estação, aeronaves por estação, frota com disponibilidade (esperada e para uma confiança), surtidas e horas de voo por dia | Ha 2010 (AFIT-OR-MS-ENS-10-03); Blanchard & Fabrycky 2011; MIL-HDBK-338B |
| `fleet_reliability` | P(≥ k de N) binomial, com sucesso unitário a partir de p, de 1−p_falha ou de exp(−λt) | O'Connor & Kleyner 2012; MIL-HDBK-338B |
| `radar_horizon` | horizonte radar (terra 4/3) ou geométrico | Skolnik 2001, Sec. 8.2 |
| `sensor_footprint` | faixa no solo de um sensor de imagem (terra plana) | trigonometria |
| `johnson_range` | alcance de deteção, orientação, reconhecimento e identificação | Johnson 1958 |
| `size_fleet` | dimensiona cada variante com o **mesmo** `run_pipeline` que `acdt size`; omitir `level` = fidelidade do YAML (frota de 1 ≡ `acdt size`); `level=L0\|L1` força handbook/lowfi e reporta `mtow_alignment`; agrega W0×q, custo, cert, perda/surtida | pipeline `size`, `cost_estimate`, `safety_assessment` |
| `compare_alternatives` | filtragem por restrições, frente de Pareto, pontuação ponderada opcional e gráfico | Deb 2001; Marler & Arora 2004 |

O código está em `src/acdt/core/concept/` (geo, ops, search, reliability, tradeoff, study) e em
`src/acdt/ai/concept.py` (funções da IA e registo). O registo MCP está em `src/acdt/ai/concept_mcp.py`.

## Fluxo

1. `concept_study_start(title, problem)`. Daí em diante, passa-se `study_id` a cada cálculo.
2. **Perceber** o problema (`interpretation`): quem decide o quê, qual é o alvo ou a necessidade, onde e
   quando.
3. **Pressupostos e perguntas**, explícitos (`assumption` com `rationale`, `question`).
4. **Requisitos mensuráveis** (`requirement`: métrica, limiar e justificação), derivados com as primitivas. Por
   exemplo, a janela de deteção é o tempo de travessia do alvo (`transit_time`).
5. **Alternativas diversas** antes de avaliar (`alternative`, incluindo as não avaliáveis).
6. **Avaliar** com `size_fleet` e as primitivas de operações. As verificações falhadas também são resultados.
7. **Iterar**: sensibilidade dos pressupostos que mandam no resultado; variantes novas quando se aprende algo.
8. **Comparar** com `compare_alternatives`: objetivos, restrições = requisitos, e gráfico.
9. **Recomendar** (`recommendation`: escolha, porquê, sensibilidades, o que não foi avaliado, próximos
   passos). Depois, `concept_study_report`.

## CLI

```
acdt concept replay <study.json> [--with-sizing]   # repete as chamadas registadas e compara os resultados
acdt concept report <study.json>                   # reescreve o report.md
```

## Exemplo

Pesca ilegal ao largo de Peniche/Nazaré: `examples/concept/illegal_fishing/` (as especificações das variantes
e o script com as decisões do agente) e `examples/output/concept/illegal_fishing/` (report.md, study.json e os
gráficos de Pareto). Há um tutorial passo a passo em
[tutorial-concept-trade.md](tutorial-concept-trade.md).

## Limites (hoje)

* Asa fixa apenas (pistão, elétrico e híbrido). VTOL, jatos, aeróstatos, navios e satélites ficam como
  alternativas não avaliáveis.
* A cobertura usa uma largura de varrimento "cookie-cutter" para a classe de alvo (dada pelo datasheet). Não
  modela desordem do mar, estado do mar nem a probabilidade de falso alarme.
* As interrupções por meteorologia e o espaço aéreo não são modelados. A disponibilidade é independente entre
  aeronaves.
* O custo de aquisição vem do CER L0 (baixa confiança para UAV). O custo de operação exige taxas de manutenção
  e preços pesquisados; sem eles é reportado como em falta.
* A perda por surtida vem do template ARP4761 de baixa fidelidade, com taxas genéricas.
