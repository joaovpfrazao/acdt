# API pública, versões e CLI

O acdt tem duas portas de entrada estáveis: a **API Python `acdt.api`** e a **linha de comandos `acdt`**. Tudo o
resto (`acdt.core`, `acdt.domains`, `acdt.ai`, os internos de `acdt.cli`) é interno e pode mudar entre versões do
pacote sem aviso. Referência gerada: [API Python](referencia/api.md) · [CLI](referencia/cli.md).

## 1. Superfície pública (`acdt.api`, API 1.7.0)

| grupo | funções |
|---|---|
| versões e erros | `version_info()`, `errors()`, `API_VERSION`, `__version__`, `LEVELS` |
| projeto | `load_mission(missão, level=)`, `size(missão, saída, level=, no_systems=)`, `analyse(…)`, `verify(missão, saída)` |
| incerteza | `uq(missão, saída, uq_file=, overrides=)`, `uq_study(bloco, modelo)` |
| MDO | `mdo(missão, saída, mdo_file=, overrides=)`, `mdo_study(bloco, modelo)` |
| modelos genéricos | `function_model(fn, params, requirements, name)` — qualquer função Python como modelo de sistema |
| V&V | `vv_cases()`, `vv(cases=, disciplines=, max_cost=, output=)` |
| dados de ensaio | `load_test_data(ficheiro, meta)`, `calibrate(estudo, saída)` |
| estado de projeto | `db_load`, `db_save`, `db_get`, `db_diff`, `db_validate` |
| revisões de projeto | `report(design, level, saída, uq=, mdo=, vv=, calib=, criteria=, discover=, pdf=)` — SRR/PDR/CDR (desde 1.1.0; [RELATORIOS.md](RELATORIOS.md)) |
| ruído | `rotor_noise(blades=, diameter_m=, rpm=, thrust_N=, power_W=, n_rotors=, altitude_m=, speed_m_s=, …)` — ruído L0 de rotores/hélices dados explicitamente (desde 1.2.0; [RUIDO.md](RUIDO.md)) |
| térmica | `thermal(spec)` — compartimentos, margens e arrefecimento a partir de uma especificação genérica `acdt.thermal/1`; `thermal_atmosphere(perfil, altitude_m, T_sl_C=)` — dias quente/frio MIL-HDBK-310 (desde 1.3.0; [TERMICA.md](TERMICA.md)) |
| gelo | `icing(spec)` — envelopes do 14 CFR 25 Ap. C, captação, fração de congelação, espessura, potência de proteção e penalização a partir de uma especificação genérica `acdt.icing/1`; `icing_envelope(tipo, T_C, mvd_um, horizontal_extent_nmi=, altitude_m=)` — LWC de projeto e estado face ao envelope (desde 1.4.0; [GELO.md](GELO.md)) |
| fiabilidade | `reliability(spec)` — fiabilidade de missão, MTBF/MTBCF, M_ct, MMH/FH, disponibilidades A_i/A_a/A_o, sobressalentes, frota e custo de manutenção a partir de uma especificação genérica `acdt.reliability/1`; `availability(*, mtbf_h=, mttr_h=, mtbm_h=, m_bar_h=, mdt_h=, ready_time_h=)` — Eq. 10.18/10.21/10.22 do MIL-HDBK-338B; `spares_stock(lambda_per_h, hours, confidence)` — stock Poisson (desde 1.5.0; [FIABILIDADE.md](FIABILIDADE.md)) |
| custo de série | `series_cost(spec)` — CER Eastlake/DAPCA IV varrida em N (RDT&E, ferramentas, recorrente, *flyaway*, custo médio, amortizações, lotes), rota de aprendizagem com T1 e ponto de equilíbrio vs preço; `learning_curve(T1, slope, first, last, theory=, method=)` — lote, média, unidade e ponto médio (Crawford/Wright, FAA Eq. 18-9/18-10) (desde 1.6.0; [CUSTO_SERIE.md](CUSTO_SERIE.md)) |
| ciclo de vida | `life_cycle_cost(spec)` — LCC por categorias (OSD CAPE) com calendário, dólares constantes e valor presente (NIST HB 135), custo por FH e por missão; `life_cycle_emissions(spec)` — CO₂ de combustão (ICAO Anexo 16 Vol. IV), CO₂e do poço à esteira (CORSIA), rede declarada, fabrico de baterias (IVL C 444); `present_value(items, discount_rate)` — VP de fluxos (Eq. 5.1) (desde 1.7.0; [CICLO_VIDA.md](CICLO_VIDA.md)) |
| descontinuação | `deprecated(since, removed_in=, alternative=)`, `ACDTDeprecationWarning`, `DEPRECATED` |

Contratos comuns:

* as funções devolvem `dict`/`list`/números/texto serializáveis em JSON (exceto `load_mission`, `function_model` e
  `load_test_data`, que devolvem objetos para passar a outras funções da API);
* `missão` é um caminho de YAML ou o mesmo conteúdo como `dict` (caminhos relativos dentro do `dict` resolvem-se a
  partir da pasta atual);
* `level`: `"L0"` (handbook), `"L1"` (low-fi XFOIL/AVL) ou `None` (o que a missão declara, igual a `acdt size`);
* `saída=None` não escreve ficheiros; com uma pasta, escreve o mesmo que o comando equivalente (relatório,
  `result.json`, `design.json`, matriz de verificação, `provenance.json`);
* grandezas desconhecidas são `None`, nunca zero; estados de verificação `passa`/`falha`/`no_limite`/
  `nao_avaliado`/`desconhecido` (docs/REQUISITOS.md);
* erros de entrada levantam as exceções de `api.errors()` (`InfeasibleError`, `RequirementError`, `UnitError`,
  `UncertaintySpecError`, `MDOSpecError`, `CalibrationError`, `IngestError`, `ReviewInputError`) ou
  `FileNotFoundError`/`KeyError`.

```python
from acdt import api

r = api.size("examples/uav_gasoline_150kg.yaml", "out/uav", level="L0", no_systems=True)
m = api.verify("examples/uav_gasoline_150kg.yaml", "out/uav")
db = api.db_load("out/uav")
print(r["W0_kg"], m["coverage"]["por_estado"], api.db_validate(db))
```

## 2. Versões (versionamento semântico)

Há duas versões, ambas `MAIOR.MENOR.CORREÇÃO`:

* **`acdt.api.API_VERSION`** (1.5.0; 1.0.0 → 1.1.0 acrescentou `report`; 1.1.0 → 1.2.0 acrescentou `rotor_noise`; 1.2.0 → 1.3.0 acrescentou `thermal` e `thermal_atmosphere`; 1.3.0 → 1.4.0 acrescentou `icing` e `icing_envelope`; 1.4.0 → 1.5.0 acrescentou `reliability`, `availability` e `spares_stock`) — versão do contrato da API pública:
  * **MAIOR** — mudança incompatível: nome removido, parâmetro removido/renomeado/reordenado, tipo ou valor por
    omissão alterado, chave removida de um resultado documentado;
  * **MENOR** — acréscimo compatível: função nova, parâmetro novo com valor por omissão no fim, chave nova num
    resultado;
  * **CORREÇÃO** — sem mudança de assinatura (correções, documentação, métodos internos).
* **`acdt.__version__`** (0.2.0, igual a `pyproject.toml`) — versão do pacote. Enquanto for 0.x, os módulos internos
  não têm garantia; a API pública segue a sua própria versão.

O ficheiro `src/acdt/api/api_surface.json` fixa a assinatura de cada nome de `__all__`. O teste
`tests/test_api.py::test_public_surface_matches_snapshot_or_version_bumped` falha quando:

* uma assinatura muda ou um nome sai sem subir a MAIOR;
* um nome entra sem subir pelo menos a MENOR;
* a versão desce.

Depois de subir `API_VERSION` conforme a regra, regenerar o ficheiro (o comando recusa se a regra não for cumprida):

```bash
python -m acdt.api.stability --write      # sem --write: só verifica (código 1 se houver problemas)
```

## 3. Descontinuação

```python
from acdt.api import deprecated

@deprecated("1.2.0", removed_in="2.0.0", alternative="acdt.api.size")
def dimensionar(...): ...
```

* o nome continua a funcionar e emite `ACDTDeprecationWarning` (subclasse de `DeprecationWarning`; ver com
  `python -W default::DeprecationWarning`), com a versão, a versão de saída e a alternativa;
* `removed_in` tem de ser uma versão MAIOR (`X.0.0`) acima de `since`; o nome fica registado em
  `acdt.api.DEPRECATED`;
* só sai numa versão MAIOR, depois de ter passado por pelo menos uma MENOR já descontinuado; o teste
  `test_no_deprecated_name_past_its_removal` falha se um nome descontinuado sobreviver à versão de saída.

## 4. CLI: convenções comuns

* `acdt --version` → `acdt 0.2.0 (API 1.5.0)`;
* `acdt <comando> --help` em todos os comandos (teste `tests/test_cli_contract.py` percorre-os todos);
* `--json` em todos os comandos: o texto humano vai para stderr e stdout recebe um envelope `acdt.cli/1`:

  ```json
  {"schema": "acdt.cli/1", "acdt": "0.2.0", "api": "1.5.0", "command": "vv", "exit_code": 0,
   "exit_meaning": "sucesso", "result": {"counts": {"passa": 1, …}, …}, "files": ["vv/vv_report.json", …]}
  ```

  `result` é preenchido por `size`, `verify`, `uq`, `mdo`, `vv` e `calib fit`; nos outros comandos é `null` e
  `files` lista os ficheiros de `-o/--output`. Em `db` e `provenance`, `--json` é o formato próprio do comando
  (sem envelope).
* `--debug` (ou `ACDT_DEBUG=1`): pilha completa num erro interno;
* `-o/--output`: pasta (ou ficheiro) de saída nos comandos que escrevem.

Códigos de saída (iguais em todos os comandos):

| código | significado |
|---|---|
| 0 | sucesso |
| 1 | resultado avaliado com falha (inviável, requisito em falha, nenhum projeto viável, caso V&V em falha) |
| 2 | erro de utilização ou de entrada (argumentos, ficheiro em falta, especificação inválida, unidades) |
| 3 | indeterminado (o comando distingue "desconhecido"/"não avaliado" de passa/falha; p.ex. `storage`) |
| 4 | erro interno (exceção não tratada; `--debug` mostra a pilha) |
| 130 | interrompido (Ctrl-C) |

## 5. Documentação gerada

* MkDocs (BSD-2) + mkdocs-material (MIT) + mkdocstrings-python (ISC): `mkdocs.yml` na raiz, páginas em `docs/`;
  extra `pip install -e ".[docs]"`;
* `mkdocs build --strict` (pasta `site/`, ignorada pelo git); `mkdocs serve` para ver localmente;
* a [referência da API](referencia/api.md) vem das docstrings (estilo Google: `Args:`/`Returns:`/`Raises:`);
  a [referência da CLI](referencia/cli.md) é gerada do próprio parser (hook `docs/hooks/cli_ref.py`);
* as ligações das páginas pt-PT para ficheiros do repositório fora de `docs/` (código, exemplos, CAPABILITIES) são
  só informação na construção, não erro;
* CI: job `docs` constrói o site em cada PR e push (artefacto `site`). O workflow `docs-pages.yml` publica no
  GitHub Pages **só quando o Pages estiver ativado** nas definições do repositório (Settings → Pages → Source:
  GitHub Actions) — até lá corre apenas à mão (`workflow_dispatch`) e o passo de publicação não é executado.

## 6. Notebooks

`examples/notebooks/` (guardados sem saídas; o teste `tests/test_notebooks.py` falha se um notebook tiver saídas
ou contagens de execução):

| notebook | o que mostra | custo |
|---|---|---|
| `01_dimensionamento_rapido.ipynb` | `api.size` L0 do UAV de 150 kg, resumo, matriz de verificação, estado de projeto | ~10 s |
| `02_incerteza_verificacao.ipynb` | `function_model` + `uq_study` (Ishigami, Sobol' contra o analítico) e P(passa) de um requisito | ~10 s |
| `03_mdo_pareto.ipynb` | `mdo_study` NSGA-II na ZDT1 com a frente verdadeira e o joelho | ~15 s |

Executados no CI pelo job `notebooks` (`pytest --nbmake examples/notebooks`, nbmake Apache-2.0). Localmente:
`pip install -e ".[notebooks]"` e `pytest --nbmake examples/notebooks`.

## 7. Em aberto

* alargar `acdt.api` a mais disciplinas (sistemas, fabrico/custo, certificação, simulação) — cada acréscimo sobe a
  versão MENOR;
* `--json` com `result` estruturado nos restantes comandos (hoje só `files`);
* versões da documentação por versão da API (p.ex. `mike`) quando houver uma segunda versão MAIOR.
