# Guia para agentes de IA — acdt

O utilizador descreve o avião que quer; o agente usa as ferramentas do acdt (servidor MCP `acdt mcp`) para chegar
a um projeto dimensionado, verificado e documentado. Este guia é a referência do agente (também servido como
recurso `acdt://agents-guide`). Regras curtas em inglês: [AGENTS.md](../AGENTS.md).
Capacidades por área (o que existe, limites, roadmap): [CAPABILITIES.md](../CAPABILITIES.md) / `acdt://capabilities`.

## 1. Regras de metodologia

* **Nunca inventar números.** Cada valor vem de (a) uma ferramenta acdt, (b) um pressuposto citado em
  `assumption_sources` (p. ex. `aero.e: "Raymer 6th ed. Eq. 12.49"`), ou (c) um dado externo com proveniência
  (`source_url`, `retrieved`, `source_type`) validado por `validate_material` / `validate_component`. Sem fonte →
  dizer "não sei" ou pesquisar.
* **Só métodos clássicos citados.** O catálogo (`acdt://methods`) lista cada módulo com as referências extraídas das
  docstrings. Se o método não existe no acdt, dizê-lo; não substituir por fórmulas próprias.
* **Baixa fidelidade primeiro, calibração progressiva.**

  | nível | o quê | ferramenta |
  |---|---|---|
  | L0 | métodos de manual (Raymer/Roskam/Gudmundsson), segundos | `size(level="L0")` |
  | L1 | XFOIL + AVL no ciclo de dimensionamento, ≈30 s por exemplo nesta box | `size(level="L1")` |
  | L2 | MDO (OpenMDAO, região de confiança), caixão de asa (fases 5/6), RCS | `optimize`, `wingbox`, `rcs` |
  | L3 | OpenVSP, SU2, CalculiX, DLM p-k | `hifi_estimate`, `hifi` |
  | cal. | fatores L3/L1 aplicados ao L1 | `apply_calibration` → `size` |

* **Limites de validade.** Reportar sempre as verificações falhadas (`checks`, com margens), os `issues`, os
  pressupostos por omissão que pesam no resultado e o domínio do método (classe estatística, Re, Mach, …).

## 2. Ordem do fluxo

1. **Requisitos** — `requirements_schema` (chaves, unidades, sentidos), depois `validate_requirements` com o dict
   do utilizador (aceita "2.5 h", "25 kt", "150 min"). Corrigir erros; perguntar o que falta (classe, propulsão,
   carga útil, alcance/autonomia). O `run_id` devolvido serve de entrada aos passos seguintes.
2. **Conceptual** — `size(run_id=…, level="L0")`: W0, ponto de projeto (W/S, P/W), geometria, verificações.
3. **Ponto de projeto** — incluído em `size` (diagrama de restrições); se infeasible ler a mensagem e relaxar um
   requisito com o utilizador ou fornecer o pressuposto em falta (citado).
4. **Componentes / sistemas** — `systems` (UAV elétrico: hélice, motor, ESC, bateria, servos, autopiloto, cablagem).
   Componentes reais pesquisados na web entram por `components={"motors": […], "cells": […]}` com proveniência.
5. **Preliminar / MDO** — `size(level="L1")`, depois `optimize` (começar com `level="L0"` para explorar;
   L1 custa minutos: medido 6 min 55 s para 2 iterações no `uav_endurance_payload`).
6. **Caixão de asa** — `wingbox(phase=5)` e depois `wingbox(phase=6, run_id=<run da fase 5>)`. Materiais
   externos: `materials={"structure": {…}}`.
7. **RCS** — só se a assinatura interessar: `rcs(mode="validate")` (casos canónicos) e `rcs(mode="study")`.
8. **Detalhado** — `hifi(steps=["detailed"])` (leve).
9. **Alta fidelidade** — `hifi_estimate` → mostrar o plano ao utilizador → `hifi` (ver §4).
10. **Calibração** — `get_calibration` / `apply_calibration`, depois `size` de novo e `compare_runs`.
11. **Fabrico e custo (Fase 7)**, seguindo a escada de fidelidade (§3A):
    * `cost_estimate` dá o L0;
    * `manufacturing_plan` dá o L1, a partir do projeto preliminar;
    * `manufacturing_plan` com `detailed` dá o L2, a partir do projeto detalhado;
    * `process_options` e `compare_materials` servem para peças isoladas.

    Ver `docs/tutorial-fase7-fabrico-custo.md`.
12. **Relatório** — `generate_report(run_ids=[…])` → `dossier.md` + `dossier.json`.

Corridas longas devolvem `job_id` ao fim de `wait_s`; seguir com `job_status(job_id, wait_s=…)`.

## 3. Pesquisa na web (materiais, componentes, custos)

* **Fontes credíveis**, por ordem: MMPDS / CMH-17 / ESDU / normas; datasheet do fabricante; artigos revistos por
  pares e livros de texto; páginas de retalhistas só para preço e massa. Fóruns, wikis sem fonte e páginas geradas
  por IA não são fontes.
* **Dar os valores tal como impressos, com unidade** ("42 ksi", "10.0 Msi", "0.098 lb/in3", "5000 mAh"): o acdt
  converte para SI e verifica a plausibilidade (gamas por tipo de material; energia específica das células;
  potência específica dos motores; G vs E/2(1+ν)).
* **Proveniência obrigatória:** `source_url` (http/https), `retrieved` (data ISO, não futura; aviso se > 5 anos),
  `source_type` (`manufacturer_datasheet`, `handbook`, `standard`, `peer_reviewed` — credíveis; `distributor`, `other` → aviso), `datasheet`
  (nome/número do documento) e, para metais, `basis` (A/B/S/típico). Valores em falta que o acdt deriva
  (p. ex. Fcy = Fty, Fsu = 0,6 Ftu) aparecem como avisos — reportá-los.
* **Preços mudam:** datar sempre; o custo de produção do acdt é o modelo de Eastlake modificado
  (Gudmundsson 2014, Sec. 2.3) e os componentes comprados entram com o preço datado da fonte.
* Validar primeiro (`validate_material`, `validate_component`), depois passar ao `size`/`wingbox`/`systems`. O dado
  fica registado no run (`external_data`) e marcado como "external" nos pressupostos.

### 3A. Preços e escada de fidelidade do custo

* **Preços são entradas.** Cada preço vem de uma página datada de distribuidor ou fabricante, ou de uma
  cotação. Formatos: `price: {usd_per_kg, year, provenance}` para materiais; `{usd, year, provenance}` para BOM
  e cotações.
  * Assinalar os preços de retalho: um OEM paga menos.
  * O acdt escala o ano com o CPI-U. Nunca inventar um preço: o que falta é reportado como em falta.
  * Material preso a uma via de processo (laminado VARI, prepreg): `processes: [...]`.
  * `labour_calibration` numérico só com `labour_calibration_source` (dados de oficina). `'eastlake'` é um
    recurso provisório, porque ancora o L1 ao L0.
* **CERs (Eastlake, DAPCA IV) só valem dentro da sua base estatística.** Para uma aeronave não convencional
  (asa voadora, BWB, VTOL, propulsão distribuída/elétrica, não tripulada), passar `configuration`, `unmanned` e
  `propulsion`. O L0 sai então com **confiança baixa**, banda AACE Classe 5 no extremo largo (−50 %/+100 %) e a
  dispersão Eastlake/DAPCA. Nunca o apresentar como "o custo".
* **Escada**:
  * **L0**: CERs.
  * **L1**: bottom-up paramétrico por peça e processo (projeto preliminar). É o nível recomendado para não
    convencionais.
  * **L2**: bottom-up detalhado (`detailed`). Entradas: lista real de peças, geometria, nº de camadas e de
    fixadores, `l1_part`, BOM com preços pesquisados, cotações, horas de oficina, montagem final, NRC.
* **Calibração nível superior → inferior** (`cost_calibration.json`):
  * `k_cost_L0_*` corrige as CERs;
  * `k_labour_hours_L1` e `k_material_L1` corrigem o L1.

  Aplicar só na vizinhança do projeto, com `cost_calibration: {file, apply: [cost_L1, cost_L0]}`. Nunca
  aplicar fatores com `independent: false`.
* **Reportar** por nível: o custo, a confiança, a banda AACE 18R-97 e o nível recomendado com o motivo. Juntar
  os fatores aplicados.

## 4. Guarda de computação (obrigatório)

* Passos **pesados**: `cfd2d` (medido 276 s + 1067 s no UAV, 346 s + 1578 s no C172), `gci` (não terminou em
  9 min), `wing_euler`. Só correm com `user_approved=true` **depois** de o utilizador autorizar explicitamente essa
  corrida nessa máquina; registar `approval_note` (quem, quando, onde).
* O PC do utilizador só é usado com a sua permissão. `ACDT_MCP_HEAVY=never` no servidor recusa sempre os pesados.
* `rans_case` nunca corre o RANS do avião completo: escreve o caso e a estimativa de malha/memória para um cluster.
* Resultados existentes são reutilizados (`cached`) salvo `force=true`; `continue_run` continua um run hifi.

## 5. Proveniência dos runs

Cada chamada cria `runs/<id>/run.json` (`$ACDT_RUNS_DIR`, por omissão `./runs`, ignorado pelo git) com: entradas,
pressupostos com origem (`user` + citação, `external`, `assumed (acdt default …)`), dados externos, calibração,
versões (acdt, Python, bibliotecas, executáveis), commit git (e se a árvore está suja), saídas e ficheiros.
`get_run`, `list_runs`, `compare_runs` leem este registo. Citar sempre os `run_id` nas respostas.

## 6. Como reportar

1. Resumo: viável ou não, números-chave com unidades (W0, S, b, P, energia/combustível, autonomia/alcance) e
   o `run_id` de onde vêm.
2. Verificações falhadas e margens; o que as causa.
3. Pressupostos que dominam o resultado, distinguindo os do utilizador, os externos (com fonte) e os por omissão.
4. Limites de validade e fidelidade usada (L0/L1/L2/L3; calibrado ou não).
5. Próximo passo recomendado — incluindo qualquer corrida pesada que precise de autorização.

Não arredondar para valores "bonitos" nem apresentar estimativas L0 como resultados finais.
