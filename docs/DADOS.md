# Estado de projeto único com unidades (`acdt.design/1`)

O acdt guarda o estado de um projeto num só ficheiro, `design.json`, com um esquema versionado
(`acdt.design/1`, ficheiro [`src/acdt/core/data/design.schema.json`](../src/acdt/core/data/design.schema.json),
JSON Schema 2020-12). O ficheiro junta:

* a **definição** (a entrada YAML tal como escrita, o SHA-256 da fonte e os requisitos já em SI);
* os **resultados por disciplina e nível** (L0…L3, a escada de fidelidade de CAPABILITIES.md), cada bloco com
  método, referências, origem, evidência (ficheiro + SHA-256) e impressão digital de proveniência
  (`acdt.provenance/1`);
* a **matriz de verificação** (resumo e linhas de `acdt.verification/1`);
* a **incerteza** de cada grandeza, quando é conhecida (percentis de `acdt uq`, desvio-padrão ou intervalo).

O núcleo numérico não mudou: continua a trabalhar com números em SI (requisitos) ou na unidade que o nome da
chave declara (`assumptions`). As unidades tratam-se **na fronteira** (entrada e base de dados), com
[pint](https://github.com/hgrecco/pint) (BSD-3-Clause).

## Comandos

```
acdt size missao.yaml -o out/x          # escreve out/x/design.json (revisão seguinte se já existir)
acdt db show out/x                      # resumo: disciplinas × níveis, contagens, verificação
acdt db get out/x W0_kg                 # por nome (todas as disciplinas/níveis)
acdt db get out/x W0_kg --unit lb       # convertido (pint)
acdt db get out/x 'results.aerodinamica.*.aero.C*'      # glob sobre o caminho
acdt db diff a/design.json b/design.json [--rtol 1e-6] [--include 'results.massas.*'] [--json]
acdt db export out/x --format csv|md|json [-o tabela.csv] ['filtro']
acdt db build missao.yaml out/x [-o design.json]        # a partir de uma pasta já corrida
acdt db add-uq out/x output/uq_estudo [--map metrica=nome.da.grandeza]
acdt db validate out/x                  # contra o esquema
```

`acdt verify missao.yaml out/x` reescreve a matriz e, se existir `design.json` na pasta, atualiza a secção
`verification`. `db diff` sai com código 1 quando há diferenças (como `provenance diff`).

## Esquema `acdt.design/1`

```
{
  "schema": "acdt.design/1", "name", "domain", "revision", "created_utc", "updated_utc",
  "definition": {
    "source": {"path", "sha256"},
    "input": { … YAML tal como escrito … },
    "requirements": {"<chave>.<sentido>": {"value" (SI), "unit" (SI, pint), "sense", "raw", "raw_unit",
                                           "source", "id"}}
  },
  "results": {
    "<disciplina>": {
      "L0" | "L1" | "L2" | "L3": {
        "method", "references": [...], "source", "evidence", "evidence_sha256",
        "provenance": {"fingerprint", …}, "updated_utc", "notes": [...], "sections": {"<secção>": "<método>"},
        "quantities": {"<nome.pontuado>": {"value", "unit", ["source"], ["uncertainty"], ["note"]}}
      }
    }
  },
  "verification": {"schema", "evidence", "provenance", "counts", "coverage", "rows": [...]} | null,
  "history": [{"utc", "what"}, …]          (últimas 500 alterações)
}
```

### Regras das grandezas

* `unit` está sempre presente. É uma unidade em sintaxe pint (`"kg"`, `"m/s"`, `"N/m**2"`, `"1/rad"`), `"1"`
  para adimensional **declarado**, ou `null` para **unidade não declarada pela fonte**. Uma grandeza sem unidade
  declarada nunca é tratada como adimensional: `db get --unit` recusa convertê-la e `db diff` assinala a mudança
  de unidade em vez de comparar números.
* `value: null` quer dizer não calculado ou desconhecido, nunca zero. NaN e infinito são guardados como `null`
  com uma nota.
* A origem, o método, o nível e a proveniência herdam-se do bloco. `flatten`/`db get`/`db export` mostram-nos
  já resolvidos por grandeza. Uma grandeza pode sobrepor `source`.
* `uncertainty` só existe quando é conhecida: `{"kind": "percentis" | "desvio_padrao" | "intervalo",
  "source", "p5", "p50", "p95", "sd", "lo", "hi", "n", …}`. Com entradas epistémicas (intervalos sem
  distribuição, `acdt uq`), cada estatística é um intervalo sobre os pontos. Nesse caso guarda-se o envelope
  (`p5` = o menor P5, `p95` = o maior P95), os intervalos de cada estatística, `epistemico: true` e
  `p50: null`, porque não há um só P50.
* Só se guardam escalares. Listas (histórico do MDA, distribuições em envergadura, mensagens) ficam no ficheiro
  de resultados, referenciado pelo SHA-256 do bloco (`evidence_sha256`).

### Caminhos e consulta

* `definition.requirements.<chave>.<sentido>` — p. ex. `definition.requirements.endurance.min`;
* `results.<disciplina>.<nível>.<nome>` — p. ex. `results.dimensionamento.L0.weights.W0_kg`;
* `verification.<ID>` — o valor é o estado (`passa`, `falha`, …).

`query` aceita o caminho exato, um glob (`results.*.L1.*`) ou o fim do nome (`W0_kg`, `weights.W0_kg`).

### Diff

`diff(A, B)` compara por caminho: grandezas novas, removidas e alteradas. Os números comparam-se na unidade de A;
se B estiver noutra unidade com a mesma dimensão, é convertido com pint. 150 kg e 330,69 lb não contam como
diferença. Unidades incompatíveis (`kg` contra `m`) ou uma unidade que passa a não declarada contam como mudança
de unidade. Uma mudança de nível ou de método conta como mudança de fidelidade. A tolerância por omissão é
`rtol = 1e-6`.

### Revisões

`save` valida contra o esquema e incrementa `revision`. O `acdt size` numa pasta que já tem `design.json`
continua a numeração. Substitui os blocos que ele próprio escreveu (origem `acdt size (aircraft)`), por isso
nenhum resultado antigo fica com ar de atual, e mantém os blocos de outras origens, como um L3 de verificação
acrescentado à mão ou por outra ferramenta. Se o `design.json` anterior for inválido, recomeça.

## Unidades na entrada (YAML)

Os YAML antigos, sem unidades em texto, funcionam como antes. Um número simples continua a ser lido em SI nos
requisitos (ou na unidade de `unit:`) e na unidade do nome da chave nas `assumptions`. O teste
`test_examples_unchanged_by_normalisation` confirma que nenhum exemplo do repositório muda.

O que passa a ser aceite:

```yaml
requirements:
  payload_mass: 30 kg                 # = {target: 30, unit: kg}
  endurance: {min: 10 h}
  cruise_speed: {target: 87 kt, altitude: 3000 m}
  stall_speed: {max: 50 kilometer/hour}   # fora da tabela exata → pint, para o SI
assumptions:
  geometry:
    fuselage_length_m: 10.5 ft        # → 3.2004 (a chave declara metros)
    stations_m: [1 ft, 0.5]           # elemento a elemento
  weight_balance:
    lemac_arm_in: {value: 1.2, unit: m}   # → 47.24 in (a chave declara polegadas)
verification:
  requirements:
    - {id: DER-01, quantity: q, comparison: max, threshold: 300 m}
```

* **Requisitos**: as unidades da tabela exata de `acdt.core.units` (NIST SP 811, 2008, Apêndice B) usam o
  fator de sempre. Qualquer outra unidade passa pelo pint para o SI da dimensão do tipo de requisito.
* **`assumptions`, `systems`, `onboard`**: a unidade interna é a que o **sufixo da chave** declara (`_m`,
  `_kg`, `_deg`, `_m_s`, `_kW_per_kg`, `_in`, …; tabela `SUFFIX_UNITS` em `acdt/core/quantities.py`).
* **Erros claros**, com o caminho e as duas dimensões. Exemplos:
  `assumptions.geometry.fuselage_length_m: '8.0 kg' tem dimensão [mass], mas é esperado [length] (unidade
  interna 'm')`. Uma grandeza com unidade numa chave sem sufixo de unidade (`AR: 16 m`) é recusada, porque não se
  adivinha em que unidade o modelo a espera. O `acdt size` sai com código 2 e mostra a mensagem.
* `{value, unit}` só se lê como grandeza numa chave com sufixo de unidade. Nas outras chaves, um mapa continua a
  ser um mapa.
* Temperaturas (`15 degC`) convertem-se pela regra afim do pint.

## Unidade dos resultados

A unidade de cada resultado lê-se pelo sufixo do nome da chave no `result.json` (`W0_kg` → kg, `W_S_N_m2` →
N/m², `CL_alpha_per_rad` → 1/rad, `wing_loading_psf` → lbf/ft²). Chaves sem sufixo reconhecido (`CD0`, `e`,
`V_divergence_eas`) ficam com a unidade **não declarada**. `_g` (fator de carga) fica de fora de propósito,
porque o pint o leria como grama. No exemplo GA (`examples/ga_range_speed.yaml`) 130 das 377 grandezas
numéricas têm unidade declarada. As restantes são sobretudo coeficientes, razões e velocidades `*_eas` sem
sufixo, que ainda não estão marcados.

## Disciplinas e níveis do domínio aircraft

`acdt/domains/aircraft/design_db_run.py` (`SECTION_MAP`) atribui cada secção de topo do `result.json` a uma
disciplina e ao nível que CAPABILITIES.md declara para o método. Quando CAPABILITIES dá uma faixa, fica o nível
de baixo.

PRESSUPOSTO: escolher o nível de baixo é conservador, porque nunca declara mais fidelidade do que a garantida. A
exceção é a aerodinâmica, cujo nível vem da própria corrida (`aero.fidelity: lowfi` → L1).

| secção | disciplina | nível | fonte |
|---|---|---|---|
| `feasible`, `weights`, `design_point`, `weight_initial_source`, `onboard_bridge` | dimensionamento | L0 | §2 |
| `weight_breakdown`, `weight_cross_check`, `weight_balance` | massas | L0 | §3, §20 |
| `geometry` | geometria | L0 | §2 |
| `aero` | aerodinamica | L0 (L1 com `lowfi`) | §4 |
| `aero_lowfi` | aerodinamica | L1 | §4 |
| `avl_cruise_trim`, `stability`, `dynamics` | estabilidade | L1 | §6 |
| `structures`, `wing_box_comparison_kg` | estruturas | L0 | §7 |
| `structures_avl_loading` | estruturas | L1 | §7 |
| `aeroelasticity` | aeroelasticidade | L2 | §8 |
| `landing_gear` | trem | L0 | §20 |
| `performance`, `verified_segment_mission` | desempenho | L0 | §2 |
| `cost` | custo | L0 | §14 |
| `systems` | sistemas | L0 | §12 |
| outra | outros | L0 | assinalada nas `notes` do bloco |

`requirements`, `issues`, `checks` e `mda_history` não entram nos blocos. Os requisitos ficam na definição, os
avisos e verificações na matriz, e as listas ficam no `result.json`.

### Incerteza de `acdt uq`

`acdt db add-uq` liga os resumos de propagação (`propagation.summaries`) às grandezas. As métricas padrão de
`extract_metrics` estão mapeadas pela mesma origem em `report.to_dict`:

| métrica | grandeza |
|---|---|
| `W0_kg`, `We_kg` | `weights.W0_kg`, `weights.We_kg` |
| `Wf_kg` | `weights.Wfuel_or_battery_kg` |
| `E_Wh` | `weights.battery_energy_Wh` |
| `CD0`, `K` | `aero.CD0`, `aero.K` |
| `V_cruise_mps` | `aero.cruise_speed_m_s` |
| `ws_Pa` | `design_point.W_S_N_m2` |

As métricas de `uncertainty.result_metrics` (nome → caminho do `result.json`) ligam-se pelo próprio caminho, que
agora fica guardado em `uq.json` (`model.result_metrics`). `S_m2` não está mapeada, porque `res.S` não foi
confirmado igual a `geometry.wing.S_m2`. Liga-se com `--map S_m2=geometry.wing.S_m2` depois de o confirmar. A
incerteza descreve o estudo que a produziu (fonte com o SHA-256 do `uq.json`). Se o estado e o estudo vierem de
entradas diferentes, cabe a quem os junta confirmar que se aplicam.

## API (Python)

```python
from acdt.core import design_db as D
db = D.load("out/x")                                   # ou D.new(nome, domínio)
D.set_results(db, "aerodinamica", "L3", {"CL": D.quantity(0.494, "1", source="VSPAERO")},
              method="VSPAERO (painéis)", references=["OpenVSP 3.x"], source="hifi")
D.get_value(db, "results.dimensionamento.L0.weights.W0_kg", "lb")
D.query(db, "results.*.L1.*");  D.diff(db_a, db_b);  D.to_csv(db);  D.save(db, "out/x/design.json")
```

Unidades: `acdt.core.quantities` — `to_unit`, `to_dimension_si`, `convert`, `unit_from_key`,
`normalise_tree`, `QuantityError` (subclasse de `ValueError`).

## Integrado e por fazer

Integrado:

* o pipeline aircraft (`acdt size`/`run_pipeline`, etapa `design_db`): definição, resultados de todas as
  etapas e matriz de verificação;
* `acdt verify`, que atualiza a matriz no estado;
* `acdt uq`, por `acdt db add-uq`.

Por fazer, por ordem:

1. **`acdt mdo`**: escrever o ótimo e a frente de Pareto como blocos (nível L2, `source: acdt mdo`), com as
   variáveis de projeto como definição derivada.
2. **`acdt vv`**: um bloco `vv` por caso (estado e erro relativo por grandeza), ou uma ligação do relatório
   `acdt.vv/1` ao estado da framework (não é um estado de projeto de aeronave).
3. **Ferramentas L3** (`acdt hifi`, VSPAERO, CalculiX, pyCycle): blocos L3 por disciplina, para que o `diff`
   L1↔L3 saia direto do estado.
4. **Unidades declaradas para as chaves sem sufixo** no `result.json` (coeficientes como adimensional `"1"`,
   velocidades `*_eas` em m/s EAS), por um mapa de chaves no domínio e não por adivinhação.
5. Leitura de YAML com unidades nas restantes entradas (`acdt mdo`/`uq` specs, bases de componentes).
