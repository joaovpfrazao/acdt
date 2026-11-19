# Relatórios automáticos de revisão de projeto (`acdt report`)

`acdt report` gera o relatório de uma revisão de projeto (**SRR**, **PDR** ou **CDR**) a partir do estado de
projeto (`design.json`, `acdt.design/1`) e dos registos à volta:

* matriz de verificação (`acdt.verification/1`);
* proveniência (`acdt.provenance/1`);
* incerteza (`acdt.uq/1`);
* MDO (`acdt.mdo/1`);
* V&V (`acdt.vv/1`);
* calibração contra ensaio (`acdt.calib/1`).

O resultado sai em Markdown, HTML autónomo (figuras embutidas) e JSON (`acdt.review/1`), e opcionalmente em PDF.
O relatório termina num **veredito calculado** a partir de critérios de entrada e de sucesso declarados.

O módulo é genérico (`acdt/core/review/`). Cada domínio só declara o seu perfil: disciplinas primárias, grandezas
de resumo e grandeza de viabilidade. O perfil do domínio aircraft está em
`acdt/domains/aircraft/review_profile.py`.

## Comando

```
acdt report out/uav --level PDR                 # pasta do design.json → out/uav/revisao_pdr/
acdt report out/uav/design.json --level CDR -o revisoes/cdr \
    --uq out/uq_estudo --mdo out/mdo --vv output/vv --calib out/calib_tunel \
    --criteria criterios.yaml [--no-discover] [--pdf] [--json]
```

* Os registos de UQ, MDO, V&V e calibração são procurados automaticamente na pasta do `design.json` e nas
  subpastas, até 3 níveis (`uq.json`, `mdo.json`, `vv_report.json`, `calibration_record.json`). As opções
  `--uq/--mdo/--vv/--calib` acrescentam outros (ficheiro ou pasta, repetíveis). Um ficheiro dado explicitamente
  com o esquema errado é um erro. Um ficheiro descoberto com o esquema errado é ignorado, com aviso.
* As figuras PNG já produzidas na pasta do projeto e nas pastas dos estudos são embutidas. O relatório não gera
  figuras novas.
* A pasta de saída não pode ser a do `design.json`, porque o relatório tem proveniência própria e sobreporia a
  da corrida.
* **Códigos de saída**: 0 `pronto`, 1 `nao_pronto`, 3 `insuficiente`, 2 entrada inválida (docs/API.md §4).
  `--json` devolve o envelope `acdt.cli/1` com o veredito e o estado de cada critério.
* `--pdf` usa o [WeasyPrint](https://weasyprint.org/) (BSD-3-Clause) se estiver instalado. O WeasyPrint não é
  dependência do acdt. Sem ele o comando sai com código 2. A alternativa é imprimir o HTML para PDF no navegador.

API Python (desde a API 1.1.0):

```python
from acdt import api
r = api.report("out/uav", "PDR", "out/uav/revisao_pdr", criteria={"required_level": {"PDR": "L1"}})
print(r["verdict"]["status"], [c["id"] for c in r["criteria"] if c["status"] == "nao_cumpre"])
```

## Norma usada

**NASA NPR 7123.1D, *NASA Systems Engineering Processes and Requirements*** (em vigor desde 5 jul 2023, versão
com a Alteração 2), **Apêndice G, "Life-Cycle and Technical Review Entrance and Success Criteria"**:
<https://nodis3.gsfc.nasa.gov/displayDir.cfm?Internal_ID=N_PR_7123_001D_&page_name=AppendixG>

| revisão | secção | tabela |
|---|---|---|
| SRR (projetos e programas de projeto único) | G.5 | Tabela G-4 — SRR Entrance and Success Criteria |
| PDR | G.7 | Tabela G-6 — PDR Entrance and Success Criteria |
| CDR | G.8 | Tabela G-7 — CDR Entrance and Success Criteria |

O NASA Systems Engineering Handbook (SP-2016-6105 Rev2) remete para estas tabelas da NPR 7123.1. Usou-se
diretamente a NPR, que é o texto normativo e está em vigor. Os excertos citados em `acdt/core/review/criteria.py`
são literais e foram conferidos com o texto publicado no NODIS em 18 nov 2026. A ECSS-M-ST-10C e a MIL-STD-1521B
não são usadas.

O próprio apêndice diz que os critérios são "recommended best practices" e que *"Tailoring and customizing are
expected for projects and programs"* (G.1.2). O acdt usa essa adaptação de duas maneiras: escolhe um subconjunto
dos critérios e associa a cada um um teste sobre os registos.

## Como os critérios estão definidos

Cada critério (`Criterion` em `criteria.py`) tem:

* `id`, como `PDR-S05` (revisão, `E` de entrada ou `S` de sucesso, número);
* o excerto literal da tabela;
* `check`: o avaliador automático, ou `None` quando o critério fica para revisão humana;
* `interpretacao`: como o acdt lê o critério.

**PRESSUPOSTO:** a ligação entre o texto da NPR e o teste automático é uma interpretação do acdt, não da NASA. Por
isso aparece em todas as linhas do relatório.

| avaliador | cumpre quando | insuficiente quando | usado em |
|---|---|---|---|
| `requisitos_definidos` | há requisitos na matriz | não há matriz | SRR-E01 |
| `metodo_por_requisito` | todas as linhas têm método (análise, ensaio, …) | não há matriz | SRR-E02, SRR-S05 |
| `arvore_requisitos` | `tree_issues` vazio e todos os requisitos com fonte | não há `verification_matrix.json` | SRR-S03, PDR-S03 |
| `conceito_viavel` | a grandeza de viabilidade (`feasible`) é verdadeira | não existe ou é nula | SRR-S04 |
| `requisitos_cumpridos` | nenhum requisito em `falha` (salvo dispensa) e nenhum `nao_avaliado`/`desconhecido` | há requisitos não avaliados ou não há matriz | PDR-E01, CDR-E01 |
| `avaliador_por_requisito` | todos os requisitos com avaliador declarado e registado | não há matriz | PDR-E02 |
| `incerteza_requisitos` | estudo UQ sem `prob_falha` e a cobrir todos os requisitos numéricos | não há UQ, há `inconclusivo` ou há requisitos sem P(passa) | PDR-S04, CDR-S04 |
| `margens` | nenhum requisito `no_limite` (no CDR, também nenhum `prob_no_limite`) | nenhuma margem avaliada (no CDR, também sem UQ) | PDR-S05, CDR-S02 |
| `fidelidade_disciplinas` | todas as disciplinas primárias no nível exigido | uma disciplina primária sem resultados | PDR-S06, CDR-E07 |
| `vv_modelos` | relatório V&V sem `falha`, `nao_avaliado` nem `desconhecido` | não há relatório ou há casos por avaliar | PDR-S07, CDR-S05 |
| `estudos_compromisso` | estudo MDO com projeto viável escolhido | não há estudo MDO | PDR-S08 |
| `ensaios_calibracao` | calibração com dados reais e decisão `aplicar`/`parcial` | não há calibração ou só há dados sintéticos | CDR-S06 |
| `linha_de_base` | a evidência confere com os SHA-256 registados e o registo de proveniência tem commit sem `dirty` | não há `provenance.json` ou o commit é desconhecido | PDR-E09, CDR-S08 |
| `cobertura_completa` | todos os requisitos com avaliador e avaliados de forma conclusiva | há requisitos com avaliador mas sem avaliação conclusiva | CDR-S03 |

Em cada avaliador, uma falha conhecida dá `nao_cumpre`. Por exemplo: um requisito em falha, `no_limite`, um
caso V&V em falha, um SHA-256 diferente, `git dirty`, uma disciplina abaixo do nível exigido ou um requisito sem
avaliador.

Os critérios que os registos do acdt não cobrem ficam como **`revisao_humana`** e aparecem sempre como
pendentes. São eles: agenda e instruções ao painel, RFA/RID, custo e calendário, segurança e garantia de missão,
fabricabilidade, ICD e o plano de fecho dos TBD/TBR.

### Nível de fidelidade exigido

**PRESSUPOSTO do acdt:** a NPR não fala em níveis de fidelidade. Por omissão, as disciplinas primárias têm de
estar em **L0 na SRR, L1 na PDR e L2 na CDR**, na escada L0–L3 de CAPABILITIES.md. Conta o nível mais alto com
pelo menos uma grandeza conhecida.

No domínio aircraft, as disciplinas primárias são massas, aerodinâmica, estabilidade, estruturas e desempenho. O
dimensionamento fica de fora porque é L0 por natureza; a viabilidade entra pelo SRR-S04. Ambos os valores se
ajustam por projeto.

### Veredito

O veredito conta só os critérios automáticos que não foram dispensados:

* **`nao_pronto`**: algum critério dá `nao_cumpre`. Uma falha conhecida decide, mesmo que falte evidência
  noutros critérios;
* **`insuficiente`**: nenhum critério dá `nao_cumpre`, mas algum dá `insuficiente`, ou não há nenhum critério
  automático;
* **`pronto`**: todos os critérios automáticos dão `cumpre`.

Faltar evidência nunca conta como cumprir: `insuficiente ≠ cumpre`, `nao_avaliado ≠ passa`. Os critérios
`revisao_humana` não entram no veredito, mas ficam listados. Um `pronto` diz só que a evidência registada suporta
os critérios automáticos. Não substitui a decisão do painel de revisão.

### Ficheiro de critérios (`--criteria`)

```yaml
required_level: {PDR: L1, CDR: L3}           # nível exigido às disciplinas primárias
primary_disciplines: [aerodinamica, estruturas, massas]
headline: [weights.W0_kg, geometry.wing.S_m2]   # grandezas do resumo
waivers:                                      # "or has waivers" (Tabelas G-6/G-7)
  - {id: REQ-stall_speed, justificacao: "dispensa aprovada na revisão X (ref. …)"}
tailoring:                                    # G.1.2: adaptação justificada
  - {criterio: PDR-S08, justificacao: "trade de configuração feito no estudo conceptual (acdt concept)"}
```

Cada dispensa e cada adaptação exige uma `justificacao` não vazia, que fica impressa no relatório. Um requisito
dispensado em falha deixa de decidir o veredito, mas continua nos itens em aberto, com severidade baixa. Um
critério adaptado fica `dispensado`. Campos desconhecidos são um erro.

## Conteúdo do relatório

1. **Veredito**: estado, critérios que o decidem, contagens e regra.
2. **Critérios**: excerto da NPR, interpretação, estado, detalhe e evidência de cada critério.
3. **Conformidade com os requisitos**: a matriz completa, com os cinco estados, margem relativa, método,
   fidelidade exigida e avaliada e ponteiro para a evidência. Indica também a fração avaliada, os requisitos sem
   avaliador e as verificações calculadas sem requisito.
4. **Resumo do projeto**: as grandezas de resumo do perfil, com unidade, nível, disciplina, caminho e P5/P50/P95
   quando há incerteza guardada. Um valor desconhecido aparece como "—" e nunca como zero; uma unidade não
   declarada aparece como "(não declarada)". Inclui os requisitos de entrada em SI e como foram escritos.
5. **Fidelidade por disciplina**: níveis presentes, máximo, exigido, estado (`cumpre`/`abaixo`/`ausente`),
   origem (modelo ou ensaio), método e número de grandezas sem unidade declarada. Lista o que ainda está em
   L0/L1.
6. **Itens em aberto e riscos**, por severidade:
   * requisitos em `falha`, `no_limite`, `nao_avaliado` ou `desconhecido`;
   * verificações calculadas sem requisito, em falha ou desconhecidas;
   * avisos do pipeline;
   * PRESSUPOSTOs (texto "PRESSUPOSTO" na definição, nas notas dos resultados, nos estudos UQ/MDO e na
     calibração, e entradas UQ sem fonte);
   * calibração com dados sintéticos, `nao_aplicar` ou fora da gama de validade;
   * casos V&V que não passam;
   * requisitos com P(passa) abaixo do alvo ou inconclusivo;
   * avisos do MDO;
   * disciplinas abaixo do nível;
   * grandezas sem unidade;
   * evidência alterada.
7. **Incerteza**: por estudo, método, n, semente, P5/P50/P95 de cada métrica e P(passa) por requisito, com o
   intervalo de confiança, o alvo e o estado probabilístico. Inclui também as incertezas guardadas no estado de
   projeto.
8. **MDO e frente de Pareto**: estratégia, objetivos, variáveis, avaliações (viáveis e falhadas), projeto
   escolhido com o método do joelho e os primeiros 20 pontos da frente.
9. **V&V dos modelos**: versão do registo e estado de cada caso.
10. **Calibração**: método e referência, decisão, dados sintéticos ou reais, e parâmetros com σ.
11. **Rastreabilidade**: o SHA-256 atual de cada ficheiro de evidência e o estado face ao SHA-256 que outro
    registo guardou: `confere`, `difere`, `sem_registo` ou `em_falta`. Os SHA-256 registados vêm de três sítios:
    o `evidence_sha256` dos blocos do `design.json`, a matriz de verificação e o manifesto `outputs` do
    `provenance.json`. O próprio `design.json` não decide a linha de base, porque é atualizado por `acdt verify`
    e `acdt db add-uq` e tem o seu próprio histórico de revisões.
12. **Figuras**.

## Exemplo e testes

O exemplo pequeno, analítico, está em `tests/data/review_small/` e é gerado por `gerar.py` com as próprias
ferramentas do acdt. Os registos são normalizados para serem reprodutíveis: instantes fixos, caminhos relativos,
proveniência reduzida e Monte Carlo sem amostras. O relatório de referência `relatorio_pdr.golden.md` é comparado
byte a byte (`tests/test_review.py::test_golden_markdown_of_small_example`). Os outros testes cobrem:

* a estrutura e o JSON;
* o veredito, incluindo os dados em falta;
* um requisito não avaliado que bloqueia;
* a calibração real contra a sintética;
* as dispensas e adaptações com justificação;
* a evidência alterada e o `git dirty`;
* as figuras embutidas;
* o PDF opcional;
* a CLI (`--json`, códigos de saída) e a API.

Com um projeto real, por exemplo `acdt size examples/uav_gasoline_150kg.yaml -o out/uav` seguido de
`acdt report out/uav --level PDR`, o veredito é `nao_pronto`, pelos motivos seguintes:

* um requisito sem avaliador (`REQ-propulsion_type`);
* o requisito de velocidade de perda está `no_limite`, porque é dimensionante por construção;
* massas e desempenho ainda estão em L0.

Na SRR, o mesmo projeto dá `pronto`.

## Por fazer

* Gerar as figuras do relatório (Pareto, histogramas UQ) quando os estudos não as tenham produzido.
* Acrescentar critérios para revisões que ainda não estão cobertas (MDR/SDR, TRR, PRR).
* Ler o registo de decisões (`acdt decisions`) como evidência dos estudos de compromisso.
* Ligar o resultado de `acdt certify` (matriz de conformidade) aos critérios de segurança.
* Permitir o modelo de ficha RID/RFA para o painel.

## Figuras geradas e revisões MDR, TRR e PRR (19 nov 2026)

Os dois primeiros pontos de «Por fazer» estão feitos neste ramo. O registo de decisões, a matriz de `acdt certify`
e a ficha RID/RFA continuam por fazer.

`acdt report` passa a aceitar também `--level MDR`, `--level TRR` e `--level PRR`. A assinatura de
`acdt.api.report` não mudou (o nível já era uma cadeia). A versão da API mantém-se.

### Figuras

A secção 12 continua a listar os PNG que já estejam nas pastas do projeto. Se não houver nenhum, o relatório
mantém a frase «Nenhuma figura já produzida nas pastas do projeto.»

Por cima disso, o relatório prepara figuras só com números já guardados:

* Frente de Pareto de um `acdt.mdo/1`, quando há dois objetivos e todas as avaliações trazem os dois valores
  finitos, e quando cada identificador da frente existe no registo. Veredicto `validado` e calibração
  `nao_aplicar`: é uma transcrição, não uma medida nova. O PNG (`figuras/pareto_….png`) só é desenhado quando o
  relatório é escrito numa pasta. O Markdown de referência não guarda a soma do PNG.
* Histograma de uma métrica das amostras de um `acdt.uq/1`. Se `samples` falta ou é nulo, se alguma amostra não
  tem `ok` verdadeiro, se a métrica não é finita em todas, ou se `n_ok` inteiro não coincide com a lista, o
  veredicto é `nao_avaliado`. Não se desenha um histograma vazio e não se trata a amostra em falta como zero.
  O Monte Carlo do acdt deixa `samples` nulo quando n > 64.

No exemplo analítico `tests/data/review_small` (não é um projeto): a frente tem 9 avaliações e as 9 estão na
frente, objetivos `f1` (min) e `f2` (min), ficheiro `mdo/mdo.json`. O `uq/uq.json` não guarda amostras, por isso
o histograma fica `nao_avaliado`. Os YAML de `examples/` não foram editados.

### Critérios novos

Fonte: NASA NPR 7123.1D (em vigor desde 5 jul 2023, Alteração 2), Apêndice G, conferido no NODIS em 19 nov 2026.
Os excertos são literais. A ligação ao avaliador automático continua a ser um PRESSUPOSTO do acdt (G.1.2).

| Revisão | Secção | Tabela | O que o acdt avalia sozinho |
|---|---|---|---|
| MDR | G.6 | G-5, projetos e programas de projeto único | arquitetura credível (`conceito_viavel`), requisitos atribuídos (`arvore_requisitos`), compromissos (`estudos_compromisso`) |
| TRR | G.11 | G-10 | configuração dos ficheiros registados (`linha_de_base`), discrepâncias conhecidas (`requisitos_cumpridos`) |
| PRR | G.9 | G-8 | requisitos na configuração registada (`requisitos_cumpridos`) |

A SDR de projeto usa a mesma Tabela G-5. O comando é `--level MDR`. A SDR de programas que não são de projeto
único é a Tabela G-2 e não está implementada.

A PRR, no texto da norma, destina-se a projetos que desenvolvem ou adquirem vários sistemas (tipicamente mais de
três, ou o que o projeto determinar). Um único avião não fica `nao_pronto` só por esse âmbito.

PRESSUPOSTO: o nível de fidelidade exigido passa a ser L0 na MDR, na TRR e na PRR, além de L0/L1/L2 na
SRR/PDR/CDR. A NPR não define esta escada. Estes três níveis não usam `fidelidade_disciplinas`: documentação de
produção, planos de ensaio e «o produto é fabricável» não passam por haver um resultado L0.

Ficam para o painel, e não passam por um estudo que já exista: espetro, instalações, formação, segurança, custo,
calendário, fornecedores, lista de materiais e registo de riscos. Um estudo de incerteza não é um registo de
riscos. O V&V dos modelos não é o objetivo do ensaio.

No mesmo exemplo analítico, a MDR fica `pronto` porque os três avaliadores automáticos cumprem; a TRR fica
`nao_pronto` (TRR-E04, requisito em falha); a PRR fica `nao_pronto` (PRR-S04). Os critérios humanos não tornam a
revisão pronta nem a bloqueiam. Isto não é a decisão de um painel.

O registo medido está em `examples/output/relatorios_figuras/resultado.json`. Veredicto da tarefa: `validado`
para a transcrição da frente e dos excertos; calibração `nao_aplicar`; histograma `nao_avaliado`.
