# Dados de ensaio e calibração de modelos (`acdt calib`)

Esta camada liga **dados medidos** (túnel, ensaio em voo, ensaio estático, banco de motor, valores publicados) aos
modelos do acdt. Tem três partes, todas domínio-agnósticas em `src/acdt/core/calibration/`:

1. **Ingestão** (`ingest.py`, esquema `acdt.testdata/1`): tabela de canais com unidade explícita, metadados,
   incerteza de instrumento por canal e SHA-256 do ficheiro;
2. **Ajuste** (`fitting.py`): mínimos quadrados ponderados com incerteza dos parâmetros, ou calibração bayesiana
   leve à Kennedy & O'Hagan com termo de discrepância;
3. **Registo e decisão** (`record.py`, esquema `acdt.calib/1`): fatores ± incerteza, resíduos, gama de validade,
   critérios de aceitação declarados e a decisão `aplicar`/`nao_aplicar`. Daqui saem os fatores para o modelo, as
   entradas para `acdt uq` e o bloco no estado de projeto (`acdt.design/1`).

Regras que a camada impõe:

* **desconhecido ≠ zero**: um canal sem incerteza declarada não tem incerteza zero (o σ estima-se pelos
  resíduos e fica escrito); ν = n − p < 1 ou parâmetros não identificáveis → incerteza **desconhecida** e
  `nao_aplicar`; célula vazia = valor em falta, nunca zero;
* **unidade não declarada ≠ adimensional**: um canal usado no modelo sem unidade é um erro;
* **nunca se aplica fora da gama de validade** nem com a condição do ponto de aplicação em falta;
* **sem critérios de aceitação declarados → `nao_aplicar`**; um critério que não se consegue avaliar conta como
  não cumprido;
* **dados sintéticos** têm de vir marcados `synthetic: true`, com a origem (modelo, parâmetros, semente). Nunca são
  aplicados, salvo `allow_synthetic: true` declarado no estudo, que fica no registo e no relatório. Serve só para
  demonstração e testes.

## Comandos

```
acdt calib ingest dados.csv [--meta dados.meta.yaml] [--topic airspeed] [-o resumo.json]
acdt calib fit estudo.yaml -o output/calib_x          # calibration_record.json, calibration.md, residuals.csv
acdt calib show output/calib_x/calibration_record.json
acdt calib export output/calib_x/calibration_record.json --at "load=1500 N" [--at Re=3e5] [-o pasta]
acdt calib db output/calib_x/calibration_record.json --db out/projeto/design.json
```

`export` escreve, para o ponto de aplicação dado em `--at`:

* `calibration_factors.json`: fatores do domínio (`k_EI`, `k_clmax`, …) no formato de
  `assumptions.calibration.file`, com `decision`, `sd`, `ci95` e `validity`. Um fator que não pode ser aplicado
  no ponto sai com `valid: false` e `decision: nao_aplicar`, e o carregador recusa-o;
* `calibration_overlay.yaml`: substituições de caminhos `assumptions.…` (p. ex. `assumptions.aero.oswald`), só
  das que podem ser aplicadas no ponto;
* `calibration_uq.yaml`: fragmento da secção `uncertainty` de `acdt uq`, com as entradas normais N(valor, σ), as
  correlações de postos tiradas da covariância do ajuste e `calibration.file` para os fatores.

## Ingestão (`acdt.testdata/1`)

| Formato | Leitor | Licença | Notas |
|---|---|---|---|
| CSV | biblioteca padrão | — | cabeçalho `alpha [deg]`, `alpha (deg)` ou sufixo da convenção do acdt (`V_m_s`, `alpha_deg`); linhas `#` são comentários |
| Parquet | pandas + pyarrow (extra `[dados]`) | BSD-3 / Apache-2.0 | unidade pelo nome da coluna ou pelos metadados; colunas de texto ignoradas |
| PX4 ULog (`.ulg`) | pyulog (extra `[dados]`) | BSD-3-Clause | canais `tópico.campo`; `timestamp` em µs (convenção uORB do PX4); unidade pelo sufixo do campo (`true_airspeed_m_s`) ou não declarada |
| ArduPilot `.bin`/`.tlog` | — | — | **não lido no processo**: o leitor de referência (pymavlink) é LGPL-3.0. Converta fora do processo (`mavlogdump.py --format csv`) e ingira o CSV |

Metadados: ficheiro `<dados>.meta.yaml` ao lado dos dados (ou `--meta`):

```yaml
source: "Relatório de ensaio RT-123, túnel X, 2026-05-02"   # obrigatório (ou synthetic: true + source)
date: 2026-05-02            # desconhecida → null (nunca «hoje»)
kind: tunel                 # tunel | voo | estatico | bancada | publicado | outro
instrument: "balança de 6 componentes, calibração 2026-04"
conditions: {Re: 3.0e5, V_m_s: "25 m/s", T: "15 degC"}      # unidades em texto convertidas pelo sufixo
channels:
  CD: {uncertainty: {sd: 0.0004, source: "certificado de calibração da balança"}}
  V:  {unit: kt, uncertainty: {resolution: 1, source: "leitura ao kt"}}
  alpha: {unit: deg, rename: alpha_deg}
```

Incerteza por canal (GUM, JCGM 100:2008), na unidade do canal: `sd` (incerteza-padrão, tipo A ou B),
`half_width: a` (retangular, u = a/√3, GUM 4.3.7), `resolution: δ` (resolução de leitura, u = δ/(2√3), GUM
F.2.2.1) ou `rel: r` (u = r·|valor|). Toda a declaração de incerteza precisa de `source`.

## Estudo de calibração

```yaml
calibration:
  name: flexao_asa
  discipline: estruturas
  level: L1                  # nível do modelo calibrado (L0…L3)
  data: {file: flexao.csv, where: {config: 1}}       # meta: <ficheiro>.meta.yaml por omissão
  model:
    expr: "w_beam / k_EI"    # canais, parâmetros e constantes; + − × ÷ **, sqrt log exp abs sin cos tan …
    output: w                # canal medido
    units: {w: m, w_beam: m, load: N}                # unidade em que cada canal entra na expressão
    constants: {g: {value: 9.80665, source: "gravidade padrão"}}
  method: wls                # wls | koh
  parameters:
    k_EI: {initial: 1.0, bounds: [0.2, 5.0], nominal: 1.0, factor: k_EI, group: structures}
    # ou target: assumptions.aero.oswald  (substitui um caminho de parâmetro)
    # koh: prior: {mean, sd, source} obrigatório em todos
  validity: {channels: [load], only_channels: true}  # gama de validade nas condições de aplicação
  acceptance:                # sem nenhum critério → nao_aplicar
    min_points: 6
    require_instrument_uncertainty: true
    max_chi2_red: 2.0        # χ²/ν com σ do instrumento
    max_rel_sd: 0.05         # σ/|θ| (número ou mapa por parâmetro)
    max_rmse: 0.001          # na unidade da saída
    band: {k_EI: [0.5, 2.0]}
    max_prior_shift_sigma: 3 # koh: |θ − μ₀|/σ₀
    allow_synthetic: false
```

A previsão do modelo do acdt nas condições do ensaio entra como **canal** (`w_beam`, `CLmax_modelo`), calculada
antes e guardada com a sua proveniência. Assim, qualquer saída de qualquer disciplina pode ser calibrada pela
mesma camada. O fator passa a ser um parâmetro de uma expressão simples: `k · previsão`, `previsão / k` ou
`previsão + d`.

## Métodos

**Mínimos quadrados ponderados (`wls`).** Região de confiança com limites (SciPy `least_squares`). Pesos 1/σ²:

* σ é a incerteza-padrão da saída medida;
* quando as entradas também têm incerteza, usa-se a **variância efetiva** σ² = σ_y² + Σ (∂η/∂x_j σ_xj)² (Orear,
  Am. J. Phys. 50 (1982) 912), recalculada no ótimo;
* a covariância dos parâmetros é (JᵀWJ)⁻¹ (Bard 1974, Cap. 7; Seber & Wild 1989).

Casos especiais:

* **Sem σ de instrumento:** σ estima-se pelos resíduos, s² = SSR/ν, e a covariância é s²(JᵀJ)⁻¹. Fica escrito
  `sigma_source: residuos`.
* **Com σ declarado e χ²/ν > 1:** a covariância é multiplicada por χ²/ν (razão de Birge, 1932; Bevington &
  Robinson 2003 §8.2), porque o instrumento sozinho não explica a dispersão. O critério `max_chi2_red` decide se
  essa falta de ajuste é aceitável.

Saem também:

* IC 95 % pela t de Student com ν graus de liberdade (GUM G.3);
* matriz de correlação;
* resíduos por ponto, brutos e normalizados;
* desvio ao valor nominal em σ;
* parâmetros nos limites, que ficam sinalizados e com `nao_aplicar`.

**Kennedy & O'Hagan leve (`koh`).** O modelo é y = η(x, θ) + δ(x) + ε:

* a discrepância δ ~ PG(0, σ_δ² exp(−|x−x'|²/2ℓ²)) nas entradas normalizadas a [0, 1];
* o ruído ε tem o σ do instrumento ou é estimado como hiperparâmetro.

O ajuste é o máximo a posteriori conjunto de θ e dos hiperparâmetros. A covariância de θ vem da aproximação de
Laplace, (JᵀC⁻¹J + Σ_prior⁻¹)⁻¹, com os hiperparâmetros fixos no MAP. É a abordagem modular de Bayarri et al.,
Technometrics 49 (2007) e Liu, Bayarri & Berger (2009).

* **Prior normal informativo obrigatório** em cada parâmetro: sem ele, θ e δ não se separam (Brynjarsdóttir &
  O'Hagan, Inverse Problems 30 (2014) 114007).
* **Não é MCMC**: a posterior é aproximada por uma normal.
* O registo guarda σ_δ, ℓ, o RMS de δ nos dados, a razão σ_posterior/σ_prior e o desvio ao prior em σ.

## Ligações ao resto da framework

* **Fatores existentes** (`assumptions.calibration`): o ficheiro de fatores de ensaio usa o mesmo formato dos
  fatores de alta fidelidade da Fase 4 e as mesmas regras:
  * opt-in por grupo em `apply`;
  * `STRUCTURES_APPLIED`;
  * `factor_acceptable`, que agora também recusa `decision: nao_aplicar`.

  Os fatores com efeito no modelo são os mesmos de sempre: `k_clmax`, `k_cd_profile`, `d_cm0` (aero),
  `k_flutter` e `k_EI`/`k_GJ` (estruturas).
* **Parâmetros de entrada** (`target: assumptions.…`, p. ex. `aero.oswald` e `propulsion.eta_cruise`): o
  `overlay` só traz os que podem ser aplicados no ponto.
* **UQ** (`acdt uq`):
  * os fatores de ensaio em `uncertainty.calibration.file` entram como N(valor, σ do ajuste), em vez da uniforme
    ±GCI usada para os fatores de alta fidelidade;
  * os `target` entram por `calibration_uq.yaml`, com as correlações de postos ρ_S = (6/π)·asin(ρ/2) da
    covariância (normal bivariada; Kruskal, JASA 53 (1958) 814), impostas por Iman & Conover.

  Por isso, as colunas probabilísticas da matriz de verificação (`P(passa)`, `estado_probabilistico`) passam a
  usar a distribuição calibrada.
* **Estado de projeto** (`acdt calib db`): bloco `results.calibracao.<nível>` com `fidelity: ensaio`. Cada
  parâmetro fica como grandeza `<registo>.<parâmetro>` com incerteza do tipo `desvio_padrao`, e ficam também a
  decisão, n, RMSE e χ²/ν. Vários registos no mesmo nível juntam-se, não se substituem. O campo `fidelity`
  (`modelo` | `ensaio`) é novo e opcional no esquema `acdt.design/1`, e `flatten` herda-o.
* **Proveniência**: `fit` escreve `provenance.json` na pasta de saída, com o SHA-256 do estudo e dos dados.

## Exemplos (dados SINTÉTICOS)

`examples/calibration/` tem dois estudos com dados **sintéticos** gerados por `gerar_sintetico.py`, com fatores
verdadeiros conhecidos e semente explícita. Servem só para testar a framework e não são ensaios reais:

| Estudo | Verdadeiro | Ajustado (± σ) | Decisão |
|---|---|---|---|
| `polar_tunel_sintetico.yaml` (CD0, e de Oswald → `assumptions.aero.oswald`) | CD0 0,0250; e 0,78 | CD0 0,02505 ± 0,00016; e 0,7789 ± 0,0053 | aplicar (só com `allow_synthetic`) |
| `flexao_estatica_sintetica.yaml` (`k_EI`, grupo `structures`) | 0,92 | 0,927 ± 0,011 | aplicar na gama de carga 200–2000 N |

## Dados publicados: C172S

O teste `test_c172s_published_stall_point_is_not_enough` usa só valores publicados que já estão no repositório,
com citação:

* do Cessna 172S Information Manual (1998): V_S0 48 KCAS, MTOW 1157 kg e S 16,2 m²;
* incerteza de leitura de 1 kt, tratada como resolução (GUM F.2.2.1);
* o modelo comparado é o CLmax de aterragem L0 (Raymer 12.15/12.21) do exemplo.

O fator ajusta-se, mas com um só ponto ν = 0. A incerteza fica **desconhecida** e a decisão é `nao_aplicar`.
Um valor publicado isolado não chega para calibrar; é preciso uma série (curva de sustentação, polar de voo
planado) com a sua incerteza.

## Limitações e próximos passos

* Os modelos são expressões de canais. Ligar diretamente uma função do pipeline como η(x, θ) (re-correr o modelo
  do acdt dentro do ajuste) fica para depois. Hoje a previsão entra como canal.
* `koh` é MAP + Laplace com núcleo isotrópico. Fica para depois: MCMC, núcleo com ℓ por entrada e emulador do
  modelo (o «η» de KOH como PG).
* A ingestão de ULog não reamostra: cada tópico tem a sua base de tempo. Alinhar tópicos e cortar segmentos de
  voo em regime estabilizado (ensaio de desempenho) fica por fazer.
* Ainda não há relatórios de ensaio reais no repositório; a calibração real fica à espera desses dados.
