# Relatório de revisão PDR — exemplo analítico de teste

- **Revisão:** PDR (Preliminary Design Review)
- **Norma:** NPR 7123.1D (2023-07-05), Tabela G-6 (PDR), §G.7
- **Fonte:** https://nodis3.gsfc.nasa.gov/displayDir.cfm?Internal_ID=N_PR_7123_001D_&page_name=AppendixG
- **Projeto:** exemplo analítico de teste — domínio analitico, acdt.design/1, revisão 0, atualizado 2026-11-18T00:00:00+00:00
- **Entrada:** exemplo_analitico.yaml (SHA-256 —)
- **Gerado:** 2026-11-18T00:00:00+00:00 (acdt report, acdt.review/1)

Objetivo da revisão (NPR, G.7): "The PDR demonstrates that the preliminary design meets all system of interest requirements with acceptable risk and within the cost and schedule constraints and establishes the basis for proceeding with detailed design."

## 1. Veredito

**Veredito: NÃO PRONTO**

Critérios: 4 cumpre, 4 não cumpre, 1 insuficiente, 0 dispensado (automáticos: 9); 5 para revisão humana.

Decidem o veredito: PDR-E01, PDR-E02, PDR-S05, PDR-S06.

Âmbito: critérios automáticos declarados (os de revisão humana ficam pendentes e não entram). nao_avaliado/desconhecido ≠ passa; insuficiente ≠ cumpre; o veredito cobre só os critérios automáticos e não substitui a decisão do painel de revisão.

Regra: NÃO PRONTO se algum critério automático não cumpre; INSUFICIENTE se nenhum falha mas falta evidência para algum; PRONTO só com todos os automáticos a cumprir.

## 2. Critérios de entrada e de sucesso

Critérios de NPR 7123.1D Tabela G-6 (PDR) (excertos literais). Adaptação: G.1.2: "Tailoring and customizing are expected for projects and programs." A ligação entre o texto da NPR e o teste automático é uma interpretação do acdt (PRESSUPOSTO), indicada em cada linha.

| ID | Fase | Critério (NPR) | Avaliação | Estado | Detalhe | Evidência |
|---|---|---|---|---|---|---|
| PDR-E01 | entrada | A preliminary design that can be shown to meet all technical requirements and performance measures or has waivers. | nenhum requisito em falha (salvo dispensa declarada); nao_avaliado/desconhecido → insuficiente | NÃO CUMPRE | 1 requisito(s) em falha: R3 | verification_matrix.json |
| PDR-E02 | entrada | Baselined Verification and Validation Plan | cada requisito tem avaliador declarado e registado (requisitos_sem_avaliador vazio) | NÃO CUMPRE | 1 requisito(s) sem avaliador: R4 | verification_matrix.json |
| PDR-S03 | sucesso | The flow down of verifiable requirements is complete and proper, or, if not, an adequate plan exists for timely resolution of open items. Requirements are traceable to parent technical requirements and to mission goals and objectives. | a árvore de requisitos não tem problemas (tree_issues vazio) e cada requisito tem fonte | cumpre | árvore sem problemas; 4 requisitos com fonte | verification_matrix.json |
| PDR-S04 | sucesso | The preliminary design is expected to meet the requirements at an acceptable level of risk. | existe estudo de incerteza (acdt.uq/1) e nenhum requisito fica em prob_falha; inconclusivo → insuficiente | insuficiente | 2 requisito(s) numérico(s) da matriz sem avaliação probabilística: R2, R3 | uq/uq.json |
| PDR-S05 | sucesso | Adequate technical and programmatic margins (e.g., mass, power, memory) and resources exist to complete the development within budget, schedule, and known risks. | nenhum requisito avaliado fica no_limite (margem dentro da tolerância) | NÃO CUMPRE | margem dentro da tolerância (no_limite): R2 | verification_matrix.json |
| PDR-S06 | sucesso | Preliminary analysis of the primary subsystems has been completed and summarized, highlighting performance and design margin challenges. | as disciplinas primárias têm resultados registados no nível exigido para a revisão | NÃO CUMPRE | nível exigido L1 (PRESSUPOSTO do acdt); primárias: dimensionamento, estruturas; abaixo do nível: dimensionamento (L0) | design.json#results |
| PDR-S07 | sucesso | Appropriate modeling and analytical results are available and have been considered in the design. | existe relatório de V&V (acdt.vv/1) sem casos em falha; casos não avaliados → insuficiente | cumpre | passa 1, falha 0, nao_avaliado 0, desconhecido 0 | vv/vv_report.json |
| PDR-S08 | sucesso | Technical trade studies are mostly complete to sufficient detail and remaining trade studies are identified, plans exist for their closure, and potential impacts are understood. | existe estudo MDO (acdt.mdo/1) com projeto viável escolhido | cumpre | 1 estudo(s) com projeto viável escolhido | mdo/mdo.json |
| PDR-E09 | entrada | Subsystem design specifications (hardware and software), with supporting trade-off analyses and data, as required, that are ready to be baselined after review comments are incorporated. | a evidência confere com os SHA-256 registados e a proveniência não tem alterações por registar (git) | cumpre | evidência confere; código no commit 6104522e85fc | provenance.json |
| PDR-S10 | sucesso | TBD and TBR items are clearly identified with acceptable plans and schedule for their disposition. | revisão humana | revisão humana | pendente do painel de revisão | — |
| PDR-S11 | sucesso | The program/project cost, schedule, and JCL analysis (when required) are credible and within program/project constraints | revisão humana | revisão humana | pendente do painel de revisão | — |
| PDR-S12 | sucesso | Safety and mission assurance (e.g., safety, reliability, maintainability, quality controls, ...) have been adequately addressed in preliminary designs | revisão humana | revisão humana | pendente do painel de revisão | — |
| PDR-S13 | sucesso | Manufacturability has been adequately included in design. | revisão humana | revisão humana | pendente do painel de revisão | — |
| PDR-E14 | entrada | A preliminary PDR agenda, success criteria, and instructions to the review board have been agreed to | revisão humana | revisão humana | pendente do painel de revisão | — |

## 3. Conformidade com os requisitos

Fonte: verification_matrix.json. Estados: passa 1, falha 1, no_limite 1, nao_avaliado 1, desconhecido 0. Fração avaliada: 0.75. nao_avaliado e desconhecido nunca contam como passa.

| ID | Grandeza | Limiar | Valor | Unidade | Margem (rel.) | Estado | Método | Fid. exig./aval. | Evidência |
|---|---|---|---|---|---|---|---|---|---|
| R1 | y | ≤ 1.5 | 1 | — | 0.3333 | passa | analise | N0/N0 | result.json#sizing.y |
| R2 | m | ≤ 10 kg | 10 | kg | 0 | no_limite | analise | N0/N0 | result.json#sizing.m_kg |
| R3 | sigma | ≤ 100 MPa | 1.2e+08 | Pa | -0.2 | falha | analise | N0/N0 | result.json#struct.sigma_max_Pa |
| R4 | z | verdadeiro | — | — | — | nao_avaliado | analise | N0/— | — |

Requisitos sem avaliador: R4.

## 4. Resumo do projeto

O domínio não declara grandezas de resumo (perfil genérico); ver as disciplinas abaixo.

## 5. Fidelidade por disciplina

Nível exigido às disciplinas primárias nesta revisão: L1 (nível exigido por revisão = PRESSUPOSTO do acdt (SRR L0, PDR L1, CDR L2, MDR L0, TRR L0, PRR L0); a NPR 7123.1D não define níveis de fidelidade).

| Disciplina | Níveis | Máximo | Primária | Exigido | Estado | Origem | Método | Sem unidade |
|---|---|---|---|---|---|---|---|---|
| dimensionamento | L0 | L0 | sim | L1 | abaixo | modelo | função analítica de teste | 1 |
| estruturas | L1 | L1 | sim | L1 | cumpre | modelo | valor fixo de teste | 0 |

Ainda em L0/L1: dimensionamento, estruturas.

## 6. Itens em aberto e riscos

| Severidade | Categoria | ID | Descrição | Fonte |
|---|---|---|---|---|
| alta | requisito | R3 | falha | matriz de verificação |
| media | aviso | warning | aviso de teste (modelo analítico) | result.json#issues |
| media | calibracao | polar_tunel_sintetico | dados SINTÉTICOS: não são evidência de ensaio | calib/calibration_record.json |
| media | fidelidade | dimensionamento | abaixo: nível máximo L0, exigido L1 | design.json#results |
| media | requisito | R2 | no_limite: dentro da banda ±0.5 (tolerância declarada) | matriz de verificação |
| media | requisito | R4 | nao_avaliado: sem avaliador declarado | matriz de verificação |
| baixa | pressuposto | item[0] | probabilidade-alvo 0.95 por omissão (PRESSUPOSTO: declare uncertainty.target_probability e a origem) | uq/uq.json#pressupostos |
| baixa | pressuposto | item[1] | tolerância de convergência SE/média ≤ 0.01 por omissão (PRESSUPOSTO) | uq/uq.json#pressupostos |
| baixa | pressuposto | notas | PRESSUPOSTO: modelo analítico só para testar o relatório | design.json#definition |
| baixa | unidade | dimensionamento | 1 grandeza(s) numéricas sem unidade declarada no nível L0 | design.json#results |

## 7. Incerteza

uq/uq.json (SHA-256 f91e283dcc27): lhs, n = 200, semente 1; modelo: função analítica.

| Métrica | n | Média | P5 | P50 | P95 |
|---|---|---|---|---|---|
| m_kg | 200 | 9.999 | 8.381 | 9.997 | 11.61 |
| y | 200 | 0.9999 | 0.8009 | 0.997 | 1.191 |

| Requisito | P(passa) | IC | P(no_limite) | P(falha) | Alvo | Estado |
|---|---|---|---|---|---|---|
| R1 | 1 | [0.9812, 1] | 0 | 0 | 0.95 | prob_passa |

## 8. MDO e frente de Pareto

mdo/mdo.json (SHA-256 5f04f2824b7e): estratégia doe; objetivos min f1, min f2; variáveis x; 9 avaliações, 0 falhadas, 9 viáveis, 9 na frente.

Escolhido: #4 x = x=0.848; objetivos f1=0.719, f2=1.327 (joelho: Das 1999: maior distância à reta entre extremos (frente normalizada)).

| # | x | Objetivos |
|---|---|---|
| 7 | x=0.007463 | f1=5.57e-05, f2=3.97 |
| 8 | x=0.3844 | f1=0.1477, f2=2.61 |
| 2 | x=0.5652 | f1=0.3195, f2=2.059 |
| 4 | x=0.848 | f1=0.719, f2=1.327 |
| 0 | x=1.024 | f1=1.048, f2=0.9532 |
| 1 | x=1.273 | f1=1.621, f2=0.5282 |
| 3 | x=1.541 | f1=2.375, f2=0.2106 |
| 6 | x=1.746 | f1=3.049, f2=0.06447 |
| 5 | x=1.778 | f1=3.163, f2=0.04911 |

## 9. V&V dos modelos

vv/vv_report.json (SHA-256 2eb629bc2598): registo 2026.11.17, custo máximo barato; desconhecido=0, falha=0, nao_avaliado=0, passa=1.

| Caso | Disciplina | Tipo | Estado | Mensagem |
|---|---|---|---|---|
| ATM-ISA-SL | atmosfera | verificacao | passa | — |

## 10. Calibração contra ensaio

calib/calibration_record.json (SHA-256 a0cdb7f52889): polar_tunel_sintetico — aero L1, método wls (Bard, Nonlinear Parameter Estimation, Academic Press 1974, Cap. 7; Seber & Wild, Nonlinear Regression, Wiley 1989; Orear, Am. J. Phys. 50 (1982) 912 (variância efetiva); Birge, Phys. Rev. 40 (1932) 207); decisão aplicar; dados SINTÉTICOS.

| Parâmetro | Valor | σ | Unidade | Decisão | Motivos |
|---|---|---|---|---|---|
| CD0 | 0.02504 | 0.000159 | — | aplicar | — |
| e | 0.7789 | 0.005338 | — | aplicar | — |

## 11. Rastreabilidade da evidência

SHA-256 atual de cada ficheiro e, quando outro registo o guardou, a comparação: confere, difere, sem_registo ou em_falta.

| Papel | Ficheiro | SHA-256 | Estado |
|---|---|---|---|
| estado de projeto | design.json | 0fac9b9cbd01b73bbca23435ffa1ad5d7bff12f13823a19728d7e7861448a39f | sem_registo |
| matriz de verificação | verification_matrix.json | cfaaa5b291780a8c5aa97d5924bee755eb4c10557c7f5c9fce731a95d27b2bc3 | sem_registo |
| proveniência | provenance.json | 1cfb7f2e4e536c1a9f65eaafdff2def01d11c8bd9c1ae796bc6306efe09d20e6 | sem_registo |
| resultados (evidência dos blocos) | result.json | 4dbd371f54d78039380a214b3d1621e50c422d2ff514121e41c9472fa7d09255 | confere |
| incerteza | uq/uq.json | f91e283dcc27d6f9edaafa15d2886bc308d1e1103c305ae7a752441bf5a1be05 | sem_registo |
| MDO | mdo/mdo.json | 5f04f2824b7e6e62ce65e5d185c286c9bee9c53f2904668f4f867c5843c9251f | sem_registo |
| V&V | vv/vv_report.json | 2eb629bc2598d305dc6c71c7c05815164eb65dbddb60c60a579c14834774df60 | sem_registo |
| calibração | calib/calibration_record.json | a0cdb7f528890642c36230fab50991fb43793c8e5c611cb22771f0f800364f02 | sem_registo |
| dados de ensaio | calib/polar_tunel_sintetico.csv | c3c7803765d584686f7a430c62d310fbaed6b7918d9268f945aa36f4eda4ab6a | confere |

## 12. Figuras

Nenhuma figura já produzida nas pastas do projeto.

As figuras seguintes saem só dos números já guardados nos registos. Um plano não avaliado não produz ficheiro.

Frente de Pareto de mdo/mdo.json (SHA-256 5f04f2824b7e): 9 avaliações, 9 na frente, objetivos f1 (min) e f2 (min). Transcrição dos valores do registo; veredicto validado; calibração nao_aplicar.

![pareto_mdo_mdo.png](figuras/pareto_mdo_mdo.png)

*pareto_mdo_mdo.png*

Histograma de uq/uq.json (SHA-256 f91e283dcc27): não avaliado — o registo UQ não guarda amostras (samples nulo ou ausente); não se desenha uma distribuição. Calibração nao_aplicar.
