# Incerteza e sensibilidade (`acdt uq`)

Camada de primeira classe (16 nov 2026, ramo `eng-incerteza`): qualquer parâmetro da missão pode ser declarado
incerto, com origem obrigatória; o estudo propaga essa incerteza pelo pipeline, dá percentis com intervalo de
confiança, mede a convergência, dá a **probabilidade de cumprir cada requisito** da matriz de verificação e
ordena as entradas que mandam no resultado (Sobol' e Morris). O exemplo da asa voadora é só um caso de teste.

```
acdt uq MISSAO.yaml [--spec UQ.yaml] -o PASTA [-n N] [--seed S] [--method lhs|mc] [--workers W]
        [--fidelity handbook] [--skip-stage aeroelasticity] [--sobol N] [--morris R] [--no-gsa] [--no-plots]
```

Saída em `PASTA`: `uq.json` (formato `acdt.uq/1`), `uq.md`, `verification_matrix.{json,md,csv}` com as colunas
novas `p_passa`, `p_passa_ic`, `estado_probabilistico`, PNG (histogramas e barras Sobol') e `provenance.json`
com as sementes (`uq.seed`, `uq.surrogate.seed`, `uq.sobol.seed`, `uq.morris.seed`).

## O que já existia e o que foi acrescentado

| Já existia (P7, `acdt sensitivity`) | Acrescentado (`acdt uq`) |
|---|---|
| OAT/elasticidades e dicas de fidelidade (`oat.py`) | inalterado |
| Sobol' Jansen com fatores **uniformes** e uma saída (`sobol.py`) | Sobol' sobre as **distribuições declaradas**, várias saídas de um só desenho, estimador de 1.ª ordem de Saltelli et al. 2010 + total de Jansen 1999, IC por bootstrap (`gsa.py`) |
| MC/LHS uniforme, triangular, normal (`monte_carlo.py`) | + lognormal e **intervalo** (epistémico, caixa de probabilidade), correlações de postos (Iman & Conover 1982), origem obrigatória/PRESSUPOSTO (`distributions.py`) |
| percentis P5/P50/P95 | + IC dos percentis (Conover 1999), média corrida, SE/média e critério de convergência (`stats.py`) |
| — | **Morris** (Morris 1991; μ* de Campolongo 2007) para rastreio |
| `uq_interval_checks` para o gate N1 | **P(passa) por requisito** com IC de Wilson e estado probabilístico na matriz de verificação |
| — | fatores de calibração de alta fidelidade como entradas incertas com o seu **GCI** |
| — | **substituto** quadrático validado por PRESS quando o pipeline é caro (`surrogate.py`) |

O `acdt sensitivity` e o gate N1 (`--uq`) ficam como estavam; o `acdt uq` reutiliza o LHS e a função quantil
normal de `monte_carlo.py` e a função de Ishigami de `sobol.py`. Não há dependências novas (só numpy). O SALib é
MIT e poderia ser usado, mas os estimadores são curtos e ficam verificados contra casos analíticos.

## Declarar a incerteza

Na missão (`uncertainty:`) ou num ficheiro próprio (`--spec`). Cada entrada tem `path` (caminho no YAML da
missão; para `assumptions.*` ausentes conta o valor por omissão do domínio), `dist` e **`source`** (referência ou
dados). Sem origem é obrigatório `pressuposto: "<justificação>"`; essas entradas aparecem marcadas como PRESSUPOSTO
no relatório.

| `dist` | parâmetros | nota |
|---|---|---|
| `normal` | `mean` (omissão: nominal), `std` ou `cv`; `low`/`high` opcionais | corte (clip) registado |
| `lognormal` | `mean` (omissão: nominal) ou `median`; `cv` ou `sigma_ln` | σ² = ln(1+cv²), μ = ln(média) − σ²/2 (Ang & Tang 2007) |
| `uniform` | `low`/`high` ou `rel` (± fração do nominal) | |
| `triangular` | `low`/`high`/`mode` (omissão: nominal) ou `rel` | |
| `interval` | `low`/`high` ou `rel` | **sem distribuição**: ciclo exterior nos 2^k extremos (k ≤ 6) |

```yaml
uncertainty:
  method: lhs          # lhs | mc
  n: 200
  seed: 1
  confidence: 0.95     # IC dos percentis e de P(passa)
  target_probability: 0.90
  target_source: "…"   # sem origem → marcado PRESSUPOSTO (omissão 0,95, também PRESSUPOSTO)
  requirement_targets: {MIS-TO-01: 0.99}   # alvo por requisito (opcional)
  rel_tol: 0.01        # convergência: SE/média ≤ rel_tol (omissão PRESSUPOSTO)
  metrics: [W0_kg, "req:MIS-TO-01"]        # omissão: todas
  result_metrics: {L_D: "performance.LD_cruise"}   # saídas extra por caminho no result.json
  model: {workers: auto, fidelity: handbook, skip_stages: [aeroelasticity]}
  inputs:
    - {path: assumptions.aero.mu_roll, dist: uniform, low: 0.03, high: 0.05, source: "Raymer 2018 Tab. 17.1"}
    - {path: assumptions.propulsion.eta_cruise, dist: normal, cv: 0.03, pressuposto: "sem ensaio de banco"}
  correlations:
    - {a: assumptions.propulsion.eta_takeoff, b: assumptions.propulsion.eta_cruise, rho: 0.5, pressuposto: "…"}
  calibration: {file: calibration.json}    # fatores L3 → L1/L2 com GCI
  surrogate: {n_train: 48, q2_min: 0.95}   # opcional
  sobol: {n: 1024, bootstrap: 200, metrics: [...]}
  morris: {r: 20, levels: 4}
```

As saídas são as métricas do dimensionamento (`W0_kg`, `We_kg`, `Wf_kg`, `E_Wh`, `S_m2`, `CD0`, `K`, …) e,
para cada requisito com valor numérico na matriz, `req:<ID>` (p. ex. `req:MIS-TO-01` = corrida de descolagem).

## Métodos

* **Amostragem**: MC i.i.d. ou LHS (McKay, Beckman & Conover 1979), com transformação pela função quantil.
  Correlações de postos impostas por Iman & Conover (1982), que preserva as marginais e a estratificação; precisa
  de N > k + 1. A semente é sempre explícita e fica no registo de proveniência.
* **Estatísticas**: média, σ, erro-padrão s/√N (conservador para LHS, Stein 1987), percentis P5/P50/P95 com IC
  por estatísticas de ordem (Conover 1999 §3.2; `—` quando N é pequeno de mais para esse percentil), média corrida
  em N = 2, 4, 8, … e `converged` = SE/média ≤ `rel_tol`.
* **Intervalos**: entradas sem distribuição entram num ciclo exterior (Ferson et al. 2003, SAND2002-4015; Oberkampf
  & Roy 2010, Cap. 13). Todas as estatísticas e P(passa) saem como [mínimo, máximo] sobre os extremos; nunca se
  inventa uma distribuição uniforme para os combinar. Na sensibilidade global o intervalo é varrido uniformemente:
  é rastreio de influência, não probabilidade.
* **P(passa)**: em cada amostra a matriz de verificação é avaliada com a regra de sempre (`classify`). P(passa) =
  n_passa / N_total: amostras falhadas, `no_limite`, `desconhecido` e `nao_avaliado` **não** contam como passa.
  IC de Wilson (1927; Agresti & Coull 1998) para P(passa), P(no_limite) e P(falha), todas sobre N_total.
  Estado probabilístico: `prob_passa` (limite inferior de P(passa) ≥ alvo), `prob_no_limite` (P(passa) com
  limite superior < alvo, mas limite inferior de P(passa ∪ no_limite) ≥ alvo: cumpre só dentro da tolerância
  declarada, sem margem — análogo do `no_limite` determinístico, decisão do engenheiro, não falha),
  `prob_falha` (limite superior < alvo e não `prob_no_limite`), `inconclusivo` (mais amostras), `nao_avaliado`
  (nenhuma amostra avaliada), `desconhecido` (correu sem valor). Com intervalos, cada probabilidade e o seu IC
  saem como [mín, máx] sobre os extremos. Pais sem avaliador: pior estado dos filhos. O `status`
  determinístico da corrida nominal **não muda**.
* **Sobol'**: desenho A, B, A_B^(i) (Saltelli 2002) nas distribuições declaradas; 1.ª ordem pelo estimador recomendado por
  Saltelli et al. (2010, Tab. 2) e total pelo de Jansen (1999), na mesma tabela; custo N(k+2); IC por bootstrap das linhas.
  Assume entradas independentes (as correlações são ignoradas aqui e avisado). Variância nula → `nao_avaliado`.
  As saídas são **centradas** (f − f̂0, f̂0 = média de [f(A); f(B)]) antes dos estimadores (Sobol', Math. Comput.
  Simul. 55 (2001) 271–280): o estimador de 1.ª ordem não é invariante a uma constante em amostra finita e, sem
  centragem, o ruído em S1 é ≈ (|média|/σ)·√(2·ST/N) — no exemplo (W0 ≈ 150 kg, σ ≈ 7 kg) dava ΣS1 = 1,01 e
  S1 > ST; na autonomia (média/σ ≈ 100) dava S1 negativos. Verificação de consistência por saída: S1 ≤ ST, S1 ≥ 0
  e ΣS1 ≤ 1, com o IC bootstrap ou, sem bootstrap, folga de 0,05 (PRESSUPOSTO); violações vão para `avisos`.
* **Morris**: r trajetórias numa grelha de p níveis (par), Δ = p/(2(p−1)) (Morris 1991); μ, μ* = média de |EE|
  (Campolongo et al. 2007) e σ; custo r(k+1). Nas marginais ilimitadas a grelha vai dos quantis 1 % a 99 %
  (PRESSUPOSTO). Serve para pôr de lado entradas sem influência antes de um Sobol' caro.
* **Calibração de alta fidelidade**: `uncertainty.calibration.file` aceita o `calibration.json` de `acdt hifi` e o
  registo H1 (`h1_wing_gci.json`). Só entram os fatores que a corrida determinística aplica
  (`assumptions.calibration.apply` + `factor_acceptable`); registos H1 `nao_aplicar` nunca entram. Incerteza:
  uniforme ±GCI_fino·|valor| (Celik et al. 2008; Roache 1998, Fs = 1,25 ≈ banda de 95 %) ou ±U_osc (Stern et al.
  2001) quando a convergência é oscilatória — PRESSUPOSTO: só o erro de discretização da alta fidelidade. Sem GCI
  o fator não é propagado e fica listado («incerteza desconhecida», nunca zero).
* **Substituto** (opcional): quando cada corrida custa minutos, o modelo verdadeiro corre `n_train` vezes num LHS
  de treino (intervalos varridos uniformemente) e cada saída ganha uma superfície de resposta quadrática (completa se
  N ≥ 1,5·termos; senão sem interações), aceite só se Q² por PRESS (Allen 1974; Myers, Montgomery &
  Anderson-Cook 2016) ≥ `q2_min`. Propagação, P(passa) dos requisitos numéricos (com a mesma `classify`), Sobol' e
  Morris correm no substituto. Saídas rejeitadas e requisitos não numéricos ficam com as amostras de treino do
  modelo verdadeiro (fonte indicada em cada linha). A fração de amostras fora da caixa de treino fica registada,
  no total e por entrada (fração e excursão máxima em larguras da caixa). Os intervalos entram no treino numa
  coluna estratificada que **inclui os extremos** ({0, 1/(n−1), …, 1}), porque a propagação só os avalia nos
  extremos: antes o LHS deixava-os a até 1/n do extremo e 100 % das amostras ficavam «fora da caixa» (só por esse
  motivo). Entradas limitadas deixam ≈ 2/(n_treino+1) fora; caudas normal/lognormal deixam mais.

## Verificação

`tests/test_uq.py`: Ishigami (a = 7, b = 0,1) contra os índices analíticos (Saltelli et al. 2008; S1 = 0,3139,
0,4424, 0; ST = 0,5576, 0,4424, 0,2437) a ±0,04 com N = 8192; Y = 2a + b normal (S_a = 0,5 exato); Morris linear
(μ* = |c_i|, σ = 0 exatos); P(y ≤ 1,5) com y ~ N(1; 0,5) = Φ(1) = 0,841 dentro do IC de Wilson; Wilson 0/10 e
5/10 contra Agresti & Coull; média/cv da lognormal; estratificação LHS e correlação de postos após Iman & Conover;
envelope de um intervalo; substituto aceite (Q² ≈ 1) e rejeitado (função descontínua); fatores de calibração com
GCI; registo H1 `nao_aplicar` nunca propagado; estudo pequeno no pipeline real; matriz com a coluna nova sem
mudar o estado determinístico.

## Exemplo de teste: asa voadora sem deriva

`examples/uq/uav150_tailless_uq.yaml` sobre `examples/heavy/uav150_flying_wing_tailless.yaml`. As dispersões são
ilustrativas (PRESSUPOSTO, salvo μ_roll de Raymer Tab. 17.1); os números testam a camada, não o avião.

Corrida de 17 nov 2026 no box (`acdt uq ... -o /workspace/uq_tailless_v2 --workers 4`, ~1 h; ficheiros fora do
repositório), já com as correções deste ramo: 48 corridas do pipeline de treino (0 falhadas), LHS N = 4000 no
substituto, aviónica 5–7 kg como intervalo (resultados em [mín, máx] sobre os 2 extremos).

* **Substituto**: aceites W0, We, Wf, S, CD0, MIS-TO-01, MIS-END-01, MIS-CLB-01 (Q² 0,959–0,9999); rejeitados K,
  ws, MIS-CEIL-01 (Q² < 0,95) e as saídas constantes (V_cruise, MIS-STALL-01). Fora da caixa de treino: **9,3 %**
  das amostras (antes 100 %, artefacto do intervalo), 0 % na aviónica; maior excursão na lognormal do trem
  (0,55 larguras da caixa) e na normal da η de cruzeiro (0,33).

| Saída | Nominal | P5 | P50 | P95 |
|---|---|---|---|---|
| W0 [kg] | 149,7 | [137,1; 141,1] | [147,3; 151,6] | [159,7; 164,3] |
| Corrida de descolagem MIS-TO-01 [m] (limite 300) | 226,9 | [203,2; 206,3] | [225,5; 228,6] | [253,1; 256,2] |
| Autonomia MIS-END-01 [h] (mínimo 10) | 10,47 | [10,29; 10,31] | [10,47; 10,49] | [10,63; 10,64] |

* **Sobol'** (N = 4096 no substituto, saídas centradas; ΣS1 0,97–0,99 com IC que contém 1; S1 ≈ ST, quase sem
  interações): W0 ← margem de crescimento de massa (ST 0,59) e área de arrasto do trem (0,34); descolagem ← η da
  hélice na corrida (0,72), trem (0,17), μ_roll (0,12); autonomia ← trem (0,78), margem de massa (0,12), η de
  cruzeiro (0,09). A aviónica (intervalo) pesa < 3 % em todas. Morris (r = 20) dá a mesma ordem em W0 e na descolagem; na
  autonomia põe a η de cruzeiro antes da margem de massa (μ* mede o efeito por unidade de quantil, não variância).
* **P(passa)** (alvo 0,90, PRESSUPOSTO): `prob_passa` em MIS-TO-01, MIS-END-01, MIS-CLB-01 (substituto, P = 1,000,
  IC [0,999; 1]) e nos requisitos sem substituto vindos das 48 amostras de treino (IC [0,926; 1]);
  **`prob_no_limite`** em MIS-STALL-01, MIS-CEIL-01 e MIS-OPS-01 (todas as amostras `no_limite`: o dimensionamento
  fixa a perda e o teto no requisito); `nao_avaliado` em MIS-CFG-01, DER-TO-XW-01, SORA-01, PL-FOV-01;
  `desconhecido` em MIS-CERT-01 e DER-PKG-01. Nenhum `prob_falha`.
* Comparação com a corrida anterior às correções (16 nov): os percentis praticamente não mudam; mudam a fração
  fora da caixa (100 % → 9,3 %), as colunas P(no_limite)/P(falha)/IC (antes «—»), o estado dos três requisitos
  `no_limite` (antes `prob_falha`) e o Sobol' (antes ΣS1 = 1,01 e 1,15, S1 > ST no trem e S1 negativos na
  autonomia, por falta de centragem).

## Estudo de demonstração: disciplinas novas na incerteza (23 nov 2026)

Estudo `examples/studies/uq_disciplinas/uq_disciplinas.yaml` (`applied: false`) sobre o exemplo de teste
`uav_endurance_payload`; os blocos das disciplinas novas entram pela chave nova **`uncertainty.fixed`** (como
`mdo.fixed`: caminho → número, texto ou bloco YAML; o yaml da missão não muda), com os dados de teste dos testes
unitários. Sete entradas uniformes (energia específica da bateria 180–220 Wh/kg, η_total 0,58–0,66, η do ESC
0,95–0,98, custo por hora de voo 40–90 USD, 300–500 h/ano, intensidade da rede 0,1–0,4 kg CO₂e/kWh, taxa de
desconto 3–7 %; as três primeiras e a taxa como PRESSUPOSTO, as outras com o intervalo de teste como origem).
Substituto quadrático com 28 corridas do modelo verdadeiro (LHS, semente 20261123). Resultados em
`examples/output/uq_disciplinas/` (`uq.json`, `uq.md`, histogramas, `provenance.json`, `rastreio_postos.json`).

* **Substituto**: aceite só para a área de arrasto de arrefecimento (Q² = 0,97). Rejeitado (Q² < 0,95) para W0,
  LCC (0,92), CO₂e, custo unitário, margem quente, potência anti-gelo e fiabilidade. Causa: o W0 não é suave nesta
  caixa — com bateria e η_total baixos o fecho de massa entra em espiral (W0 60 e 88 kg em duas corridas, contra
  31–47 kg nas restantes) e a margem quente cai de −64 K para −166 a −286 K. O Sobol' e o Morris dessas saídas
  ficam `nao_avaliado` (nunca se usa um substituto rejeitado).
* **Sobol' (área de arrasto de arrefecimento)**: η_total S1 = 0,94 (IC [0,88; 0,98]); o resto ≤ 0,02.
* **Rastreio por postos** (Spearman 1904; Helton & Davis 2003 §6, sobre as 26 corridas verdadeiras válidas;
  `examples/studies/uq_disciplinas/rastreio_postos.py`): ordena influências monótonas, não decompõe a variância.
  * W0 (31–88 kg): energia específica da bateria ρ = −0,84 (p < 0,001), η_total −0,58 (p = 0,002).
  * LCC em valor atual (6,8–15,6 M USD): custo por hora de voo ρ = +0,79 (p < 0,001); h/ano +0,36 (p = 0,07);
    o projeto (W0) quase não entra, porque a operação e suporte vêm do custo por hora declarado.
  * CO₂e por hora de voo (0,41–1,58 kg): intensidade da rede ρ = +0,71, η_total −0,68 (ambos p < 0,001).
  * CO₂e do ciclo de vida: intensidade da rede +0,66, η_total −0,49 (p = 0,012).
  * Custo unitário e margem quente seguem o W0 (bateria e η_total). Fiabilidade de missão 0,99971–0,99972: varia
    só pela duração da missão.
* **Requisitos**: `REQ-mtow` e `REQ-wing_span` com P(passa) = 0 (o mesmo achado do MDO: a proteção anti-gelo e o
  arrefecimento passam o W0 dos 25 kg).
* **Falhas**: 2 das 28 corridas falharam no transitório/regime da baia térmica (`brentq` com f(242,15 K) = NaN em
  `core/thermal/network.solve_bay_steady`); as entradas estão em `uq.json` (`training_samples`, `ok: false`).
  Contam como não-passa. Causa isolada depois (TERMICA §10): o dimensionamento não converge (espiral de massa) e
  chega NaN à térmica. Agora estas corridas ficam `nao_avaliado` com o motivo, em vez do erro do `brentq`.

Veredicto: ligação das disciplinas novas à UQ **validado** (saídas por `result_metrics`, `fixed` testado em
`tests/test_uq_fixed.py`); sensibilidade global de W0/LCC/CO₂e por Sobol' **nao_avaliado** (substituto rejeitado),
substituída por rastreio de postos. Números de um caso de teste com dados de teste: `nao_aplicar` ao projeto.

## Limites

* O modelo por amostra é o pipeline L0/L1 do `acdt size` (sem `acdt simulate`/`certify`/`integration`): o 6-DOF,
  a SORA e o FOV continuam `nao_avaliado` também na coluna probabilística.
* Com `skip_stages` ou `--fidelity handbook` o modelo muda; a corrida nominal do estudo usa o mesmo modelo e o
  relatório diz qual foi.
* Sobol' ignora correlações (hipótese do método); o desenho de treino do substituto também.
* Intervalos: ciclo exterior só nos extremos (exato para respostas monótonas; não deteta um extremo interior).
* Os índices de Morris são por unidade de quantil, não variância; ordenam, não quantificam.
