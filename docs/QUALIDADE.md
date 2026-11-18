# Qualidade de software — CI, tipos, cobertura e tolerâncias numéricas

Estado em 16 nov 2026 (ramo `eng-ci`, PR #71). Este documento descreve o que corre em cada PR e no `main`, o que
fica de fora e porquê, e a política de tolerâncias entre plataformas.

## 1. Integração contínua (GitHub Actions)

Ficheiro: `.github/workflows/ci.yml`. Corre em cada PR, em cada push para `main` e à mão (`workflow_dispatch`).
Um push novo no mesmo ramo cancela a corrida anterior (`concurrency`).

| Job | SO | Python | O que faz |
|---|---|---|---|
| `testes` | `ubuntu-latest` | 3.13 | instala `acdt[dev,aero,mdo,structures,hifi,wingbox,ai,cert,sim]`, compila o AVL, `pytest -n auto` com cobertura |
| `testes` | `windows-latest` | 3.13 | o mesmo, com o binário oficial do AVL, mas só `-m "not slow"` (ver abaixo) |
| `mypy` | `ubuntu-latest` | 3.13 | `python -m mypy` no subconjunto estrito (secção 2) — tem de passar |

* **Uma só versão de Python** (3.13, a do desenvolvimento local e do PC Windows). O `requires-python` continua
  `>=3.10`; o mypy verifica a sintaxe/tipos para 3.10 (`python_version = "3.10"`). Mais versões na matriz custam
  minutos de Actions (contavam enquanto o repositório era privado; o Windows contava a dobrar).
* **Cache:** pip (`actions/setup-python`, chave em `pyproject.toml`) e o executável do AVL compilado no Linux
  (`actions/cache`, chave `avl-3.40b-matrixf-v1-Linux`).
* **Tempo de referência:** os runners usados (repositório então privado) tinham **2 vCPU** (`created: 2/2 workers`). O Linux leva
  ~35 min de pytest (1058 passaram na corrida 43888447544; soma dos tempos dos testes 4000 s).
* **Windows só com `not slow` (ramo `eng-ci-windows`).** Diagnóstico das corridas 43888447544 e 43896605776, que
  ficaram «in_progress» > 1,5 h: **não havia bloqueio**. O log (obtido depois de cancelar) mostra os dois
  workers a avançar sem parar — 88 % (937 testes passados, nenhum falhado) aos 87 min, a meio de
  `test_sizing_c172.py::test_converged_and_feasible`. O Windows é ~2,5x mais lento do que o Linux nos mesmos testes
  (criação de processos e do `avl.exe`, `spawn` dos workers do xdist, importações); a suite completa ia passar das
  2 h. Solução: o marcador `slow` (registado em `tests/conftest.py`) está nos 51 testes que levaram ≥ 20 s no Linux
  (88 % do tempo total — ciclos de dimensionamento completos, 6-DOF dos exemplos, Sobol, sessão de IA). O Linux
  corre tudo; o Windows corre os outros ~1028, que incluem todos os testes rápidos do AVL (onde as diferenças de
  compilação aparecem, secção 4). Correr à mão no Windows a suite completa: `python -m pytest -n auto`.
  **Regra:** um teste novo que demore ≥ 20 s no Linux leva `@pytest.mark.slow`.
* **Limites:** `timeout-minutes` 75 (Linux) e 60 (Windows) no job; `pytest --timeout=900 --timeout-method=thread`
  por teste (o método `signal` não existe no Windows; `thread` também apanha um subprocesso à espera de stdin). Um
  teste pendurado falha com a pilha de todas as threads em vez de esgotar o job sem diagnóstico, e
  `--durations=25` mostra os mais lentos.

### Ferramentas externas

O AVL (GPL) é só um executável externo, nunca importado.

* **Linux:** compilado da fonte oficial `avl3.40b.tgz` (MIT, Drela & Youngren) da mesma maneira que a cópia de
  desenvolvimento em `/workspace/tools/Avl`: `plotlib` com `make gfortran`, `eispack.f` em `libeispack.a`, e
  `bin/Makefile.gfortran` com o solver próprio `matrix.f` (`MATRIX=matrix.o MLIBS=`, sem LAPACK). Por isso os
  dígitos coincidem com os da máquina de desenvolvimento Linux.
* **Windows:** binário oficial `avl3.40_execs/WIN64/avl.exe`. Os últimos dígitos diferem do Linux (secção 4).
* **JSBSim** (LGPL) vem do extra `sim` e corre noutro processo (`$ACDT_JSBSIM_PYTHON`).
* **XFOIL, Gmsh, CalculiX, SU2, OpenVSP, CadQuery** não são instalados na CI. Os testes que precisam deles saltam e
  a contagem aparece no resumo do job.

### Marcadores e saltos (nunca passa em silêncio)

`tests/conftest.py` regista `requires_avl`, `requires_xfoil` e `requires_jsbsim`. Um teste que precisa da ferramenta
declara o marcador; sem a ferramenta o teste **salta** com o motivo `requires_<ferramenta>`. No fim da sessão o
pytest imprime «testes saltados por motivo» e, na CI, escreve a mesma tabela em `$GITHUB_STEP_SUMMARY`.

`ACDT_REQUIRE_TOOLS=avl,jsbsim` (definido nos jobs de teste) transforma um salto destes numa **falha**: se a
instalação do AVL partir, a CI fica vermelha em vez de verde-por-salto.

Os saltos de Gmsh/CalculiX/CadQuery continuam com `skipif` próprios e aparecem como `outros: <motivo>`.

Contagem na primeira corrida Linux (sem XFOIL, Gmsh, CalculiX, CadQuery): **1058 passaram, 8 saltaram** —
3 CalculiX, 2 Gmsh, 2 CadQuery, 1 `requires_xfoil`. Sem AVL nenhum (corrida local com o PATH reduzido), saltam 32
testes por `requires_avl` nos ficheiros que o usam; antes deste ramo 23 deles **falhavam** em vez de saltar
(fixtures do modelo de voo e polares do C172 chamavam o AVL sem o declarar).

## 2. mypy gradual

Configuração em `pyproject.toml` (`[tool.mypy]`):

* `strict = true`, mas só na lista `files`;
* `follow_imports = "silent"`: os módulos importados são analisados para inferir tipos, mas os erros deles não
  contam;
* `ignore_missing_imports = true` para bibliotecas de terceiros sem tipos.

Subconjunto estrito actual (limpo em `mypy --strict`):

* `acdt/core/atmosphere.py`
* `acdt/core/units.py`
* `acdt/core/requirements.py` (registo aberto de requisitos — anotações de `Callable`, `Iterator`)
* `acdt/domains/aircraft/aero/gear_drag.py` (módulo novo do PR #70)
* `acdt/core/provenance.py` (módulo novo, ramo `eng-proveniencia`)

Linha de base do pacote inteiro em modo **não** estrito: 1124 erros em 106 de 254 ficheiros (16 nov 2026). Em
modo estrito, os candidatos seguintes tinham: `flightsim/ground_clearance.py` 12, `launch_recovery.py` 19,
`flightsim/takeoff_options.py` 70, `aero/drag.py` 16.

**Plano para alargar** (por ordem):

1. Todo o módulo **novo** entra em `files` no PR que o cria (estrito desde o início).
2. Módulos pequenos e muito usados do núcleo: `core/sections.py`, `core/materials.py`, `core/pipeline.py`.
3. Os candidatos acima (`ground_clearance`, `launch_recovery`, `aero/drag`), um por PR, só com correcções de
   anotação (sem mudar comportamento).
4. Quando a linha de base não estrita do pacote baixar de ~1100 para um número gerível, acrescentar um segundo
   passo no job: o pacote inteiro em modo não estrito, com a contagem a não poder subir.

Correr localmente: `python -m mypy` (na raiz do repositório).

## 3. Cobertura

`pytest-cov` (`--cov=acdt --cov-report=xml --cov-report=term:skip-covered`); `coverage.xml` e `junit.xml` ficam
como artefacto do job e o total vai para o resumo. **Sem limiar** por agora.

Linha de base (Linux CI, 16 nov 2026, commit `6da7b53`): **82 %** de linhas (39664 instruções, 7145 por cobrir).
Os processos filhos (JSBSim, CadQuery, executáveis externos) não são medidos. O próximo passo é um limiar que não
deixe a cobertura descer (por exemplo 80 %) e depois cobertura por módulo novo.

## 4. Tolerâncias numéricas entre plataformas

Regra: **um teste não fixa dígitos que dependem da compilação ou do SO.** As ferramentas externas (AVL, XFOIL,
CalculiX, SU2) dão resultados diferentes nos últimos dígitos entre compilações. Exemplo medido (asa voadora, o
mesmo ficheiro de entrada): AVL Windows CL 0,50293, Cm 0,02886, CD 0,01611; AVL Linux 0,50204, 0,02893, 0,01665.

Política:

1. **Comparação na mesma compilação** — o que o teste quer provar (p. ex. «a espessura não muda o CL sem CLAF», «a
   opção aumenta a corrida») compara duas corridas feitas no mesmo executável, com tolerância apertada.
2. **Banda de sanidade** para os valores absolutos medidos numa plataforma — PRESSUPOSTO declarado no teste
   (p. ex. 1 % no CL, 5 % no CDtot invíscido, 0,001 absoluto no Cm), com a plataforma e a data da medição.
3. **Tendências e sinais** em vez de números quando a trajectória integrada diverge entre plataformas (p. ex. o
   6-DOF da asa voadora no toque com vento cruzado: o Windows sai noutro ramo).
4. Tolerâncias próprias do método (convergência, critério de paragem) continuam a vir do método.

Casos já nesta forma: `tests/test_section_thickness.py::test_avl_cl_cm_at_frozen_references` (PR #64),
`tests/test_tailless_split_aileron.py` (bandas do `side_load_band`, PR #65).

## 5. Correr localmente

```bash
source /workspace/acdt_env.sh   # venv + AVL/XFOIL/gmsh no PATH
python -m pytest -q -n auto     # ~11 min em 8 núcleos
python -m pytest -q -n auto --cov=acdt --cov-report=term:skip-covered
python -m mypy
ACDT_REQUIRE_TOOLS=avl python -m pytest -q -m requires_avl   # só os testes do AVL, a exigir o executável
```

## 6. Proveniência e reprodutibilidade

Cada resultado escrito leva um registo `acdt.provenance/1` (`acdt/core/provenance.py`; CAPABILITIES §32i). A
regra da secção 4 («comparar só contra a mesma compilação») passa a ser verificável: o registo guarda o SHA-256 de
cada executável usado, o SO e o commit.

* **Onde fica:** `<pasta de saída>/provenance.json`, `<ficheiro>.provenance.json`, ou `run.json["provenance"]`.
* **Comparar:** `acdt provenance diff A B` (pastas, ficheiros de resultado, registos ou `run.json`). Pesos: `alto`
  (commit, árvore suja diferente, binário, SO/arquitectura, entradas, sementes, ferramenta só num lado), `medio`
  (Python, bibliotecas, versão do formato, comando), `info` (caminhos, versão do SO). Árvore suja gera ainda um
  aviso de reprodutibilidade: o commit sozinho não reproduz o resultado.
* **Testes:** independentes da máquina (estrutura do registo, binários falsos em `tmp_path`, registos sintéticos
  para o `diff`).
* **Sem rede**; corre `git` e, só para Gmsh/CalculiX, a opção de versão com 5 s de limite. `ACDT_PROVENANCE=0`
  desliga a escrita.

## 7. Em aberto

* XFOIL na CI (compilar `xfoil6.99` no Linux; binário oficial no Windows) — hoje 1 teste salta.
* Gmsh/CalculiX na CI (pacotes do sistema no Linux) — 5 testes saltam.
* Limiar de cobertura e mypy não estrito no pacote inteiro (secções 2 e 3).
* Testes de propriedades/invariantes (`hypothesis`).
