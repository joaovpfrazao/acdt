# Requisitos rastreáveis e matriz de verificação

Estado em 16 nov 2026 (ramo `eng-requisitos`). Código: `acdt/core/verification.py` (núcleo, domínio-agnóstico,
mypy estrito), `acdt/domains/aircraft/verification_evaluators.py` (avaliadores do domínio aircraft) e
`acdt/domains/aircraft/verification_run.py` (etapa do pipeline e `acdt verify`). Formato da matriz:
`acdt.verification/1`.

## 1. O que é

Cada requisito tem um **ID estável** e fica ligado ao avaliador que o verifica, ao valor obtido, à margem, ao
ficheiro de evidência e ao registo de proveniência da corrida (`acdt.provenance/1`, QUALIDADE.md §6). No fim de
cada `acdt size … -o PASTA` o pipeline escreve:

* `verification_matrix.json` — matriz completa (linhas, cobertura, problemas da árvore, ligação à proveniência);
* `verification_matrix.md` — tabela para revisão de projeto;
* `verification_matrix.csv` — para folha de cálculo.

Os requisitos **não mudam o dimensionamento**: os campos de rastreabilidade são lidos à parte.

## 2. Estados

| Estado | Quando |
|---|---|
| `passa` | o avaliador correu, devolveu valor (ou veredicto) e cumpre fora da banda de tolerância |
| `falha` | o avaliador correu e não cumpre fora da banda |
| `no_limite` | o valor está dentro da banda ±tolerância em torno do limiar (a mesma regra de `side_load_band`) |
| `nao_avaliado` | sem avaliador; avaliador não registado; a etapa que o alimenta não correu; ou correu com fidelidade abaixo da exigida |
| `desconhecido` | o avaliador correu mas não deu valor nem veredicto (NaN, dados em falta, «não avaliado» interno, avaliador partido) |

Regras: nunca `passa` sem o avaliador ter corrido e devolvido valor ou veredicto (desconhecido ≠ zero; não avaliado ≠
passa). A banda é `max(tolerância declarada, resolução do avaliador)`. Exemplo: a missão por segmentos compara a
0,1 % (`performance_analysis`), por isso um teto de 4999,8 m contra 5000 m fica `no_limite`, não `passa`. Com
tolerância e resolução nulas, um valor exatamente no limiar (|margem| < 1e-9) conta como cumprido.

**Margem** (relativa ao |limiar|): `max` → (limiar − valor)/|limiar|; `min` → (valor − limiar)/|limiar|; `target`
→ tolerância − |desvio|. Positiva é folga.

**Fidelidade:** o requisito declara a fidelidade exigida (N0…N3, DESIGN_WORKFLOW.md) e o avaliador a fidelidade que
entrega. Um `passa` com fidelidade abaixo da exigida passa a `nao_avaliado`. Uma `falha` mantém-se: é um sinal
mesmo em baixa fidelidade.

**Árvore:** `parent`/`parents` liga um requisito derivado aos pais. Um pai **sem** avaliador próprio fica com o pior
estado dos filhos (ordem: falha, desconhecido, nao_avaliado, no_limite, passa). Um pai com avaliador mantém o seu
estado, e a coluna `children_worst` mostra o pior estado dos filhos. São reportados IDs repetidos, pais desconhecidos
e ciclos.

## 3. Métodos de verificação

`analise`, `simulacao`, `ensaio`, `inspecao`, `demonstracao`, `revisao` (também aceita os nomes em inglês: analysis,
simulation, test, inspection, demonstration, review). O vocabulário segue o NASA Systems Engineering Handbook
(NASA/SP-2016-6105 Rev2: test, analysis, inspection, demonstration) e a ECSS-E-ST-10-02C (test, analysis,
review-of-design, inspection). `simulacao` é análise por modelo dinâmico (6-DOF, missão por segmentos); fica separada
apenas para facilitar a leitura.

## 4. Como declarar

### Requisitos da missão (`requirements:`)

Acrescentam-se campos de rastreabilidade à entrada que já existia:

```yaml
requirements:
  takeoff_ground_roll: {max: 300, unit: m, id: MIS-TO-01, text: "Corrida de descolagem ≤ 300 m",
                        parent: MIS-OPS-01, source: missao, method: analise, fidelity: N1, tolerance: 0.02,
                        tolerance_source: "…", evaluator: perf:takeoff_ground_roll, goal: 250}
```

Campos (`TRACE_KEYS`): `id`, `text`, `source`, `source_kind` (missao, regulamento, norma, sora, utilizador,
derivado), `parent`/`parents`, `method`, `fidelity`, `tolerance` (relativa), `tolerance_source`, `evaluator`, `goal`
(objetivo, melhor do que o limiar; a coluna `meets_goal` diz se o cumpre) e `notes`.

* Sem `id`, o ID é `REQ-<chave>` (`REQ-<chave>-<sentido>` quando a mesma chave tem vários sentidos). É estável, mas
  nos exemplos usam-se IDs explícitos.
* Sem `evaluator`, usa-se o avaliador por omissão do domínio (secção 5). Sem nenhum dos dois, o estado é
  `nao_avaliado` e o requisito aparece na cobertura.

### Requisitos derivados, regulamentares, SORA ou do utilizador (`verification.requirements:`)

```yaml
verification:
  requirements:
    - {id: REG-23233-01, text: "Controlo direcional com vento cruzado a 90° ≥ 0,2 V_S0",
       source: "14 CFR 23.233(a) (pré-Amdt 23-64)", source_kind: regulamento, parent: MIS-OPS-01,
       comparison: bool, evaluator: "check:hq:yaw_crosswind", method: analise, fidelity: N1}
    - {id: DER-TO-XW-01, text: "…", comparison: max, threshold: 300, unit: m, method: simulacao, fidelity: N2}
```

`comparison` ∈ `min`, `max`, `target`, `bool`, `categoria`, `objetivo`. O limiar e o objetivo convertem-se para SI
pela unidade (`dimension:` desfaz ambiguidades como `g` ou `%`). Campos desconhecidos dão erro.

## 5. Avaliadores

| Avaliador | O que lê | Método / fidelidade |
|---|---|---|
| `resultado:<caminho>` (núcleo) | escalar em `result.json`, p. ex. `resultado:weights.W0_kg` | análise N0 |
| `ficheiro:<relativo>#<caminho>` (núcleo) | escalar noutro JSON da pasta de saída (p. ex. a saída de `acdt simulate` copiada para lá); ficheiro em falta → `nao_avaliado` | análise N0 |
| `check:<chave>` | veredicto de `res.checks` (`hq:…`, `gear:…`, `asm:…`, `aeroel:…`, `lr:…`, …); `ok=None` → `desconhecido`; chave ausente → `nao_avaliado` | análise N1 |
| `perf:<requisito>` | `performance.requirements` (missão por segmentos, Raymer 2018 Cap. 17, Anderson 1999), convertido para SI; resolução 0,1 % | análise N1 |
| `sizing:stall_speed` | V_s = √(2 (W/S) f_ater / (ρ C_Lmax,ater)), a inversa da restrição de perda (Raymer 2018 Eq. 5.6); a resolução é o fecho do MDA (`assumptions.mda.tol`/`tol_lowfi`) | análise N0 |
| `entrada:<requisito>` | entradas do dimensionamento (velocidade e altitude de cruzeiro, payload, tripulação): cumpridas por construção | inspeção N0 |

**Por omissão (aircraft):** range, endurance, service_ceiling, climb_rate, takeoff_ground_roll, landing_distance →
`perf:`; stall_speed → `sizing:stall_speed`; mtow → `resultado:weights.W0_kg`; wing_span →
`resultado:geometry.wing.span_m`; cruise_speed, cruise_altitude, payload_mass, crew_mass → `entrada:`;
regulatory_category, unit_cost, power_available, thrust_available, noise → `check:`. As outras chaves ficam sem
avaliador (`nao_avaliado`) até alguém o registar.

**Registar um avaliador novo** (num domínio):

```python
from acdt.core.verification import Evaluator, Evidence, register_evaluator, register_default_evaluator
def _meu(req, ctx, arg):          # arg = sufixo depois de "meu:"
    v = ctx.result.get("x")
    return Evidence(ran=False) if v is None else Evidence(float(v), "m", pointer="x")
register_evaluator(Evaluator("meu:", _meu, "descrição", "analise", "N1", "referência", ("aircraft",)))
register_default_evaluator("aircraft", "minha_chave", "meu:x", "analise", "N1")
```

## 6. Cobertura

A secção «Cobertura» da matriz lista:

* **requisitos sem avaliador** (e sem filhos que os cubram);
* **avaliadores não registados** (nomes com erro, ou avaliadores de um domínio que não foi carregado);
* **evidência sem requisito**: verificações e comparações de desempenho calculadas nesta corrida a que nenhum
  requisito está ligado. São candidatas a requisitos derivados.

`fracao_avaliada` = (passa + falha + no_limite) / total.

## 7. Ligação à proveniência

* `evidence` = `result.json#<caminho>` e `evidence_sha256` = SHA-256 do ficheiro de evidência.
* `provenance_fingerprint` = SHA-256 canónico do registo `acdt.provenance/1` **sem** datas, comando, notas e
  manifesto de saídas (`verification.provenance_fingerprint`). Cobre commit, árvore suja e hash do diff, versão do
  acdt, Python, bibliotecas, SO/arquitetura, SHA-256 de cada executável, entradas e sementes. É igual quando
  calculado durante a corrida e depois, a partir do `provenance.json`. Por isso a matriz escrita dentro do pipeline
  (antes de o registo existir no disco) liga-se a ele.
* `provenance.sha256`: o SHA-256 do `provenance.json` fica preenchido quando o registo já existe e tem a mesma
  impressão digital (p. ex. em `acdt verify`). Se a pasta tiver o `provenance.json` de uma corrida anterior, esse
  ficheiro é ignorado.

## 8. CLI

```
acdt size MISSAO.yaml -o PASTA        # escreve também verification_matrix.{json,md,csv}
acdt verify MISSAO.yaml PASTA [--all] [--strict]
```

`acdt verify` volta a avaliar uma pasta já corrida contra a missão atual (p. ex. depois de acrescentar IDs ou
requisitos derivados), sem correr análises. Código de saída: 1 se houver `falha`; com `--strict`, 1 também com
`nao_avaliado` ou `desconhecido`; 2 se a pasta não tiver `result.json`.

## 9. Exemplos

`examples/cessna172_check.yaml` (IDs `C172-*`, origem POH 172S, mais 3 derivados: rolamento holandês, espiral e
folga de rotação) e `examples/heavy/uav150_flying_wing_tailless.yaml` (IDs `MIS-*`, `REG-*`, `NRM-*`, `DER-*`,
`SORA-*`, `PL-*`). Os testes (`tests/test_verification.py`) verificam a estrutura e a lógica dos estados, não números
desta máquina.

Matriz da asa voadora sem deriva (corrida local de 16 nov 2026, Linux, AVL compilado da fonte): 20 requisitos —
passa 11, falha 0, no_limite 3, nao_avaliado 4, desconhecido 2.

* `no_limite`:
  * MIS-STALL-01: restrição ativa, V_s = 26,000 m/s, dentro da resolução do MDA;
  * MIS-CEIL-01: teto 4999,8 m, dentro da resolução de 0,1 %;
  * MIS-OPS-01: agregado dos filhos.
* `nao_avaliado`:
  * MIS-CFG-01: escolha de configuração;
  * DER-TO-XW-01: corrida 6-DOF com vento cruzado, ainda não ligada à pasta;
  * SORA-01: `acdt certify`;
  * PL-FOV-01: `acdt integration`.
* `desconhecido`:
  * MIS-CERT-01: `easa_specific` sem limite numérico;
  * DER-PKG-01: packaging junto ao CG não decidido.

## 10. Em aberto

* Ligar automaticamente as saídas de `acdt simulate`, `acdt certify` (SORA) e `acdt integration` (FOV) à mesma pasta
  ou matriz. Hoje faz-se com `ficheiro:` depois de copiar a saída, ou fica `nao_avaliado`.
* Avaliadores para as chaves sem omissão (max_speed, turn_rate, load_factor, …): hoje são verificadas pelo diagrama
  de restrições por construção, sem valor reportado.
* Requisitos com incerteza (intervalos ou distribuições), quando entrar a etapa de incerteza e sensibilidade.
* Matriz agregada de várias corridas (níveis N0…N3) com histórico por ID.
