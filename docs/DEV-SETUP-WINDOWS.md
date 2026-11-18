# Ambiente de desenvolvimento no Windows (Cursor / Grok Build)

Guia para continuar o desenvolvimento do acdt num PC Windows 10/11. Versões testadas no ambiente de
desenvolvimento (Linux): Python 3.13.5, numpy 2.5, scipy 1.18, matplotlib 3.11, OpenMDAO 3.45, OpenAeroStruct
2.12, AeroSandbox 4.2.10, NeuralFoil 0.3.3, pyNastran 1.3.4, PanelAero 2025.8, mcp 2.3.0, jsbsim 1.3.3, openpyxl
3.1.5, pypardiso 0.4.7; SU2 8.5, CalculiX 2.23. O pacote exige Python ≥ 3.10 (recomendado 3.12 ou 3.13).

## 1. Pré-requisitos

| ferramenta | onde | nota |
|---|---|---|
| Git for Windows | https://git-scm.com/download/win | ativar "Git Credential Manager" |
| GitHub CLI (opcional) | https://cli.github.com/ | `gh auth login` (só para contribuir) |
| Python 3.13 (64-bit) | https://www.python.org/downloads/windows/ | marcar "Add python.exe to PATH" |
| Cursor | https://cursor.com/ | abre a pasta do repositório; lê `.cursor/` |

## 2. Clonar e instalar

```powershell
git clone https://github.com/joaovpfrazao/acdt.git
cd acdt
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1          # se bloqueado: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install -U pip
pip install -e ".[dev,aero,mdo,hifi,wingbox,ai,sim,cert]"   # completo
# opcional: pip install -e ".[fastfem]"   (pypardiso/MKL, acelera o FEM de cascas)
# mínimo:   pip install -e ".[dev]"
```

Extras (ver `pyproject.toml`): `dev` pytest · `aero` AeroSandbox + NeuralFoil · `mdo` OpenMDAO + OpenAeroStruct ·
`structures`/`hifi` pyNastran, PanelAero, scipy, kinparse · `wingbox` scipy + NeuralFoil · `fastfem` pypardiso ·
`ai` servidor MCP · `sim` scipy + JSBSim (corre só em processo separado) · `cert` openpyxl (XLSX da matriz).

**UTF-8 (obrigatório)**: os relatórios usam →, ≤, Δ; com a página de código cp1252 a escrita falha. Defina uma vez:

```powershell
setx PYTHONUTF8 1        # abrir um novo terminal depois
```

A CLI avisa se o modo UTF-8 não estiver ativo; o `.cursor/mcp.json` já o define para o servidor MCP.

## 3. Executáveis externos (GPL/LGPL: nunca importados, só processos)

Todos opcionais: sem eles os testes correspondentes são saltados e o acdt usa os métodos de baixa
fidelidade. Crie uma pasta, por exemplo `C:\acdt-tools\bin`, e ponha-a no `PATH` (ou em `ACDT_HIFI_BIN`).

| executável | uso no acdt | download (Windows) | nome esperado |
|---|---|---|---|
| AVL (Drela & Youngren, MIT) | VLM, Fases 2, 8, 9 | https://web.mit.edu/drela/Public/web/avl/ (executável Windows na página) | `avl.exe` no `PATH` (renomear `avl3.xx.exe`) |
| XFOIL (Drela, MIT) | polares de secção, Fases 2, 9 | https://web.mit.edu/drela/Public/web/xfoil/ (`XFOIL6.99.zip`) | `xfoil.exe` no `PATH` |
| Gmsh | malhas 2-D/3-D (Fase 4) | https://gmsh.info/#Download, ou `pip install gmsh` no venv (instala `gmsh.exe` em `.venv\Scripts`) | `gmsh.exe` |
| SU2 8.x | CFD Euler/RANS (Fase 4) | https://su2code.github.io/download.html (binários Windows); MPI: Microsoft MPI https://learn.microsoft.com/message-passing-interface/microsoft-mpi | `SU2_CFD.exe`; `mpiexec` para corridas paralelas |
| CalculiX 2.2x | FEM de cascas, modos (Fases 4–6) | https://www.calculix.de/ (ligações para builds Windows, p. ex. bConverged) | `ccx.exe` (renomear `ccx_2.xx.exe`) |
| OpenVSP | geometria STEP/STL (Fase 4) | https://openvsp.org/download.php (zip Windows com o pacote Python `openvsp`) | ver `ACDT_VSP_PYTHON` |
| JSBSim | verificação do simulador 6-DOF (Fase 8) | `pip install jsbsim` (extra `sim`; rodas Windows no PyPI) | processo separado |
| WireViz / KiCad (opcional) | diagramas de cablagem | https://github.com/wireviz/WireViz, https://www.kicad.org/download/windows/ | `wireviz` |

Alternativa recomendada para SU2/CalculiX/Gmsh quando os binários Windows dão problemas: **WSL2** (Ubuntu) com
`conda`/Miniforge (`conda install -c conda-forge su2 calculix gmsh`) e o acdt instalado também dentro do WSL.

O acdt procura cada executável primeiro nas pastas de `ACDT_HIFI_BIN` (separadas por `;` no Windows) e depois no
`PATH`; os sufixos `.exe` são resolvidos automaticamente (PATHEXT).

## 4. Variáveis de ambiente

| variável | significado | exemplo (PowerShell) |
|---|---|---|
| `PYTHONUTF8` | modo UTF-8 do Python (obrigatório no Windows) | `setx PYTHONUTF8 1` |
| `ACDT_HIFI_BIN` | pastas com `SU2_CFD`, `ccx`, `gmsh`, `mpiexec` | `setx ACDT_HIFI_BIN "C:\acdt-tools\bin;C:\SU2\bin"` |
| `ACDT_VSP_PYTHON` | Python com `import openvsp` a funcionar (pode ser outro venv) | `setx ACDT_VSP_PYTHON "C:\vsp-venv\Scripts\python.exe"` |
| `ACDT_JSBSIM_PYTHON` | Python com `jsbsim` (por omissão o do acdt) | `setx ACDT_JSBSIM_PYTHON "C:\...\python.exe"` |
| `ACDT_RUNS_DIR` | registo de corridas do MCP (por omissão `.\runs`) | `setx ACDT_RUNS_DIR "D:\acdt-runs"` |
| `ACDT_MCP_HEAVY` | política de passos pesados: `approval` (omissão) ou `never` | `setx ACDT_MCP_HEAVY approval` |
| `ACDT_MCP_WORKERS` | trabalhos MCP em paralelo (omissão 1) | `setx ACDT_MCP_WORKERS 2` |
| `ACDT_POLAR_CACHE` | cache de polares (omissão `%USERPROFILE%\.cache\acdt\polars`; `0` desliga) | |

OpenVSP: crie um venv com a versão de Python indicada no zip do OpenVSP e instale o pacote `openvsp` que vem
no zip (`python\openvsp`); teste com `"%ACDT_VSP_PYTHON%" -c "import openvsp"`.

## 5. Testes

```powershell
pytest -q                     # tudo (~14 min no Linux de desenvolvimento; 233 testes)
pytest -q tests\test_certification.py tests\test_safety_assessment.py tests\test_safety_core.py   # Fase 10, segundos
pytest -q -x -k "not hifi"    # exemplo de filtro
```

Não há marcadores próprios: os testes que precisam de binários ou extras são **saltados automaticamente**:

| teste | precisa de |
|---|---|
| `test_phase2.py` (partes), `test_aeromodel.py`, `test_controls.py`, `test_sixdof.py`, `test_ai.py::test_toolkit_simulation_tools` | `avl` no PATH |
| `test_phase2.py` (partes XFOIL) | `xfoil` no PATH |
| `test_phase4.py` (malhas) | `gmsh` (PATH ou `ACDT_HIFI_BIN`) |
| `test_phase3.py::test_mdo_model_…` | OpenMDAO (`[mdo]`) |
| `test_jsbsim.py` | `jsbsim` |
| testes com `importorskip` | aerosandbox, neuralfoil, pyNastran, scipy, kinparse, mcp |

Use `pytest -rs` para ver o que foi saltado e porquê.

## 6. Cursor / Grok Build

* `.cursor/mcp.json` regista o servidor `acdt` (`.venv\Scripts\acdt.exe mcp`, stdio) — o venv tem de se chamar
  `.venv` na raiz do repositório (ou edite o caminho). Em Cursor: Settings → MCP → confirmar `acdt` ativo
  (43 ferramentas).
* `.cursor/rules/acdt.mdc` carrega as regras do projeto em todas as conversas; `AGENTS.md` tem o fluxo de
  trabalho para agentes e `docs/HANDOFF.md` o estado atual e os próximos passos.
* Servidor HTTP (outro cliente): `acdt mcp --http --port 8765` → `http://localhost:8765/mcp`.

## 7. Problemas frequentes

| sintoma | causa / solução |
|---|---|
| `UnicodeEncodeError: 'charmap' codec…` | falta `PYTHONUTF8=1` (secção 2) |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| "AVL binary not on PATH" e testes saltados | `where avl` deve devolver `avl.exe`; abrir novo terminal após `setx` |
| AVL/XFOIL abrem janela gráfica ou ficam parados | o acdt corre-os em modo batch (stdin) com timeout; usar as versões de consola, desligar `PLOP` gráfico se pedido |
| `SU2_CFD not found ($ACDT_HIFI_BIN or PATH)` | apontar `ACDT_HIFI_BIN` para a pasta `bin` do SU2; MS-MPI instalado para corridas paralelas |
| `OpenVSP Python API ($ACDT_VSP_PYTHON) não encontrado` | a variável tem de apontar para o `python.exe` onde `import openvsp` funciona |
| erro a compilar ao instalar extras | usar Python 64-bit com rodas disponíveis (3.12/3.13); atualizar `pip` |
| `pypardiso`/MKL falha | opcional: desinstalar, o FEM volta ao `scipy` `splu` |
| servidor MCP não arranca no Cursor | testar no terminal `.\.venv\Scripts\acdt.exe mcp` (deve ficar à espera em stdio); ver o log MCP do Cursor |
| caminhos longos no Windows (>260) em saídas de corridas | ativar "LongPathsEnabled" ou usar `ACDT_RUNS_DIR` curto (`D:\r`) |
