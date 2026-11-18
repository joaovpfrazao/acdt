# MDO global de sistema (`acdt mdo`)

Camada nova (16 nov 2026, ramo `eng-mdo`): um construtor genérico de problemas de otimização multidisciplinar **ao
nível do sistema**, em OpenMDAO, a partir de um YAML. Qualquer caminho da missão (pressupostos, geometria,
requisitos, escolhas discretas como o tipo de propulsão) pode ser variável de projeto; os objetivos podem ser
um ou vários; as restrições saem **automaticamente** do registo de requisitos rastreáveis (#74) com a tolerância
declarada; cada projeto avaliado fica com o estado de cada requisito da matriz de verificação. Os exemplos de
avião são só casos de teste.

```
acdt mdo MISSAO.yaml [--spec MDO.yaml] -o PASTA [--strategy slsqp|epsilon|nsga2|ga|doe] [--seed S]
         [--pop-size N] [--max-gen G] [--workers W] [--fidelity handbook] [--skip-stage aeroelasticity] [--no-plots]
```

Saída em `PASTA`: `mdo.json` (formato `acdt.mdo/1`), `mdo.md`, `evaluations.csv` (todas as avaliações: variáveis,
objetivos, margens das restrições, métricas e **estado de cada requisito**), `pareto.png` (com ≥ 2 objetivos),
`verification_matrix.{json,md,csv}` do projeto escolhido (joelho da frente, ou o ótimo) e `provenance.json`
(commit, versões, executáveis, entradas e sementes `mdo.<estratégia>.seed`, `mdo.robust.seed`).

## O que já existia e o que foi acrescentado

| Já existia | Acrescentado (`acdt mdo`) |
|---|---|
| `core/mdo.py`: montagem OpenMDAO domínio-agnóstica (disciplinas → componentes, NLBGS/Newton, SLSQP) | inalterado; `core/sysmdo/` reutiliza o OpenMDAO mas com o **sistema inteiro** como um componente |
| `acdt optimize` (`domains/aircraft/mdo.py`): MDF do dimensionamento — W/S, P/W, AR contínuos, disciplinas acopladas, região de confiança L0↔L1, passo de catálogo (motor/ESC/célula) fora do SLSQP, `hq`/`aeroel` como restrições opcionais | inalterado; continua a ser o MDO **dentro** do dimensionamento. O `acdt mdo` fica por cima: o pipeline (que já fecha o seu MDA de massa) é a análise |
| Paretos dedicados por disciplina: aero/RCS (`rcs/study.py`), W0–custo (`manufacturing/pareto.py`), poda morfológica e `compare_alternatives` (Deb 2001) | uma frente genérica para quaisquer objetivos, NSGA-II, ε-restrição e joelho |
| `acdt fleet study` (N0→N1, frota revista uma vez; "não há laço frota→projeto") | **fecho por iteração** de uma variável discreta (frota) com o projeto, por cada alternativa exterior (propulsão) |
| `acdt uq` (#75): modelo do pipeline por amostra, substituto quadrático com Q² | o mesmo modelo (`AircraftModel`) é o modelo de sistema; objetivo **robusto** (média + k·σ) e restrição P(passa) sobre o substituto |
| registo de requisitos e matriz (#74) | restrições geradas do registo; estado da matriz em cada avaliação |

## Formulação

* **MDF ao nível do sistema** (Martins & Lambe, AIAA J. 51(9), 2013): o modelo de sistema fecha o seu próprio MDA
  (no avião, o fecho de W0 com a montagem); o otimizador só vê variáveis → objetivos e restrições. O componente
  OpenMDAO (`core/sysmdo/om_problem.py`) tem as variáveis interiores como entradas, os objetivos (em minimização)
  e as margens das restrições como saídas. Derivadas: diferenças finitas avançadas do sistema, **em lote** (as
  perturbações correm em paralelo no modelo), passo relativo à amplitude da variável (`options.fd_step`).
* **Variáveis de projeto** (`design_variables`): `path` (caminho no YAML da missão), `type` `continuous` |
  `integer` | `discrete` (`values`: qualquer valor YAML, incluindo texto ou um bloco inteiro), `lower`/`upper`,
  `x0` (omissão: valor nominal da missão), `source` (sem origem → PRESSUPOSTO no relatório). As discretas e inteiras
  vão por omissão para o **ciclo exterior** (produto completo, ou `outer.combos` explícito); com `placement: inner`
  entram no GA/NSGA-II/DOE como índice inteiro. Escalamento: [lower, upper] → [0, 1] no SLSQP.
* **Objetivos** (`objectives`): métricas do modelo (no avião: `W0_kg`, `We_kg`, `Wf_kg`, `E_Wh`, `S_m2`, `CD0`, `K`,
  `req:<ID>` = valor de cada requisito numérico, e as de `result_metrics` por caminho no `result.json`), métricas
  derivadas (`derived`, expressões seguras: `+ − × ÷ ** ceil floor round min max abs sqrt log exp`; nomes com `:`/`-`
  passam a `_`) ou robustas (`robust:<m>`). `sense: min | max`, `ref` para escalamento.
* **Restrições** (`constraints`):
  * `requirements: all | none | [IDs]` (+ `exclude`): cada requisito numérico (`min`, `max`, `target`) passa a
    restrição g ≥ 0 com a margem relativa de `verification.classify` — (v − limiar)/|limiar| para `min`,
    (limiar − v)/|limiar| para `max`, tolerância − desvio para `target` — calculada com o limiar e a tolerância
    **da própria avaliação** (um requisito pode ser variável de projeto). Requisitos `bool`/`categoria` ficam como
    **filtros**: o estado é reportado em cada projeto mas não restringe (o otimizador não os consegue mover).
  * `policy`: `limiar` (omissão: cumprir o limiar; um projeto no limiar é `no_limite` na matriz, como acontece
    com as restrições ativas do diagrama de restrições), `passa` (folga além da banda de tolerância → `passa` na
    matriz) ou `no_limite` (aceita a banda declarada).
  * `metrics`: limites `lower`/`upper` em qualquer métrica (com `source`).
  * Viabilidade: margem ≥ −`feas_tol` (omissão 1e-6, ruído dos fechos iterativos; PRESSUPOSTO listado) ou, com a
    política `limiar`, `no_limite` da matriz só pela resolução do avaliador (tolerância declarada 0).
  * **Desconhecido ≠ zero**: uma restrição sem valor conta como violada (margem −1 para o otimizador) e o projeto
    nunca é viável; avaliações falhadas ficam no arquivo como `falhou`, com objetivos de penalidade só para orientar
    o otimizador, e nunca são reportadas como projeto.
* **Sobreposições fixas** (`fixed`): caminho → valor aplicado a todas as avaliações (p. ex. o modo de reescala da
  montagem). Aviso automático quando um objetivo não muda entre projetos diferentes (caminho não usado pelo modelo).

## Estratégias

| `strategy` | driver | uso |
|---|---|---|
| `slsqp` | `ScipyOptimizeDriver` SLSQP (Kraft 1988) | 1 objetivo, variáveis interiores contínuas, modelo suave |
| `epsilon` | SLSQP em série: âncoras mono-objetivo e min f₁ s.a. f₂ ≤ ε em `n_points` níveis, arranque a quente (Haimes, Lasdon & Wismer, IEEE Trans. SMC 1(3), 1971) | frente de 2 objetivos com modelo suave (encontra também partes não convexas) |
| `nsga2` | `NSGA2Driver` do acdt (subclasse de `openmdao.core.driver.Driver`): ordenação não dominada, dominância com restrições (§VI), aglomeração, SBX + mutação polinomial (Deb et al., IEEE TEC 6(2), 2002; Deb & Agrawal 1995) | vários objetivos, variáveis inteiras/discretas, modelo não suave; avalia a população em lote paralelo |
| `ga` | `SimpleGADriver` do OpenMDAO (penalidade) | 1 objetivo com variáveis discretas |
| `doe` | `DOEDriver` (`ListGenerator`) com LHS (McKay et al. 1979) ou fatorial completo | exploração; a frente sai das avaliações |

O `SimpleGADriver` com vários objetivos usa soma ponderada (não encontra partes não convexas da frente), por isso
a frente multi-objetivo é NSGA-II ou ε-restrição. O `pymooDriver` do OpenMDAO precisaria do pymoo (não instalado).

**Frente e joelho** (`core/sysmdo/pareto.py`): conjunto não dominado de **todas** as avaliações viáveis da decisão
final (Deb et al. 2002); joelho com 2 objetivos = ponto da frente normalizada à maior distância da reta entre os
extremos (Das, Struct. Optim. 18, 1999); com ≥ 3 objetivos, o mais próximo do ideal normalizado (Zeleny 1973).

## Ciclo exterior discreto e fecho por iteração (frota ↔ propulsão ↔ projeto)

A regra do workflow (a frota do N0 é provisória, a propulsão compara-se no N1, fecha-se por iteração) escreve-se
assim: as alternativas de propulsão são uma variável discreta exterior; a frota é uma variável de **fecho**:

```yaml
closure:
  name: n                      # valor provisório do N0
  x0: 2
  apply: {requirements.endurance: "t_out + t_back + (t_out + t_back + t_ta) / (n - 1)"}   # n → requisito do avião
  update: "ceil((endurance_h - t_out - t_back + t_out + t_back + t_ta) / (endurance_h - t_out - t_back) - 1e-9)"
  max_iter: 5
  source: "Ha 2010 (acdt.core.concept.ops.cycle)"
```

Para cada combinação exterior: aplica `apply` com o n atual → otimização interior → `update` com as métricas do
projeto escolhido (joelho/ótimo; sem projeto viável, o de menor violação, marcado) → repete até n não mudar
(`convergiu`), voltar a um valor anterior (`ciclo`), ficar sem valor (`desconhecido`) ou esgotar `max_iter`. Só a
última iteração de cada combinação entra na decisão final. Exemplo: `examples/mdo/uav150_fleet_propulsion_closure.yaml`.

## Objetivo robusto (modo barato, só no substituto)

```yaml
robust:
  inputs: [{path: assumptions.propulsion.eta_cruise, dist: normal, cv: 0.03, pressuposto: "…"}]  # como em acdt uq
  metrics: [W0_kg]     # → robust:W0_kg = média + k·σ, mean:W0_kg, std:W0_kg
  k: 2
  p_pass: {MIS-TO-01: 0.9}   # restrição P(passa) ≥ 0,9
  n: 256               # amostras das entradas incertas por projeto (no substituto)
  n_train: 40          # corridas do modelo verdadeiro (LHS conjunto variáveis × incertezas)
  q2_min: 0.95
```

O modelo verdadeiro corre só `n_train` vezes; a superfície quadrática de `acdt uq` (aceite com Q² por PRESS ≥
`q2_min`) dá média e σ em cada projeto com números aleatórios comuns (formulação média-desvio; Du & Chen, J. Mech.
Des. 122(4), 2000). P(passa) = fração das amostras `passa` pela `classify` de sempre. Substituto rejeitado → métrica
robusta sem valor (desconhecida) e a razão no `mdo.json`.

## Verificação

`tests/test_mdo_system.py`:

* **Sellar** (Sellar, Batill & Renaud, AIAA 96-0714, 1996; ótimo publicado na documentação do OpenMDAO): f* =
  3,18339, z* = (1,97764; 0), x* = 0, y₁ = 3,16 — com g₁/g₂ declarados como requisitos rastreáveis;
* **ZDT1** (Zitzler, Deb & Thiele 2000) com NSGA-II: hipervolume > 0,85 (frente verdadeira 0,877 com referência
  (1,1; 1,1)), mediana do afastamento a f₂ = 1 − √f₁ < 0,02, joelho no interior;
* **ε-restrição** num problema convexo com frente analítica f₂ = (2 − √f₁)²;
* política `passa` empurra a margem para além da banda; DOE + ciclo exterior com região de valor desconhecido
  (nunca viável); fecho por iteração 1 → 2 aviões; robusto média + 2σ com ótimo analítico a* = 1 − 1/√12;
  requisito como variável de projeto; sobreposições fixas e aviso de variável sem efeito;
* pipeline real (`uav_150kg_stanag4671.yaml`, handbook, 3 avaliações): restrições do registo, filtros, estado da
  matriz em cada avaliação, ficheiros de saída e matriz do projeto escolhido.

## Exemplo de teste: asa voadora sem deriva

`examples/mdo/uav150_tailless_mdo.yaml` (MTOW × autonomia; AR, autonomia e velocidade de perda como variáveis;
NSGA-II com 12 corridas, handbook, sem aeroelasticidade).

Corrida de 16–17 nov 2026 no box (`acdt mdo examples/heavy/uav150_flying_wing_tailless.yaml --spec
examples/mdo/uav150_tailless_mdo.yaml -o /workspace/mdo_tailless`; ficheiros fora do repositório):

* NSGA-II, **12 avaliações** (12 corridas do pipeline, 0 falhadas, 12 viáveis); frente de Pareto com **8 projetos**
  não dominados (min W0 × max autonomia).
* Joelho da frente (Das 1999, maior distância à reta entre extremos na frente normalizada): avaliação 4, com
  `assumptions.assembly.options.AR` = 13,74, `requirements.endurance` = 12,87 h e `requirements.stall_speed` =
  27,29 m/s → **W0 = 163,94 kg**, autonomia **13,26 h**.
* Extremos: menor W0 151,59 kg (AR 15,63, autonomia exigida 8,83 h → 9,34 h); maior autonomia 14,09 h
  (AR 19,70, 13,82 h exigidas, W0 172,85 kg). O ponto de partida (AR 16, 10 h, 26 m/s) dá 154,01 kg e 10,52 h.
* Atenção na leitura: a velocidade de perda é **variável de troca** neste estudo; o joelho relaxa-a de 26 para
  27,29 m/s, o que não cumpre o MIS-STALL-01 da missão original. A matriz do projeto escolhido dá passa 10,
  falha 0, no_limite 1, nao_avaliado 8, desconhecido 1. DER-TO-XW-01 não é avaliado por este modelo (não é
  restrição e nunca conta como passa).
* 12 avaliações é um orçamento de teste da camada, não uma frente convergida: as conclusões de projeto pedem
  população e gerações maiores no PC do João.

## Limites

* Derivadas por diferenças finitas do sistema (sem parciais analíticas; o pipeline tem fechos iterativos com ruído
  ~1e-7 relativo, por isso `fd_step` não deve ser pequeno de mais).
* Com o pipeline do avião cada avaliação custa de segundos (exemplos simples) a minutos (montagem + AVL): use
  `--fidelity handbook`, `skip_stages`, poucas variáveis e NSGA-II/DOE com orçamento pequeno no box; as corridas
  grandes são para o PC do João.
* O modelo por avaliação é o de `acdt uq` (L0/L1 do `acdt size`): 6-DOF, SORA e FOV continuam `nao_avaliado`.
* O substituto robusto ignora variáveis inteiras interiores e correlações das entradas incertas.
* O fecho por iteração é de ponto fixo (sem garantia de convergência; ciclos e não convergência são reportados).
