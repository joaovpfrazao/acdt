# acdt — Arquitetura

> **acdt** é uma framework de projeto de engenharia, do conceito ao projeto detalhado. A aeronave
> é o **primeiro domínio**. A framework tem um **núcleo agnóstico de domínio** (`acdt.core`) e
> **plugins de domínio** (`acdt.domains.<domínio>`). Só usamos métodos clássicos e rastreáveis
> (manuais e livros de referência). Ferramentas open-source credíveis entram como *wrappers*
> sempre que cobrem uma etapa melhor do que uma reimplementação.

Índice: 1 Princípios · 2 Núcleo vs. domínios · 3 Modelo de dados · 4 Requisitos abertos ·
5 Escada de fidelidade e critérios de passagem · 6 Fases e módulos (domínio aeronave) ·
7 Eletrónica, sistemas e cablagem · 8 Ferramentas externas (reutilização OSS) ·
9 Normas · 9A Camada AI-native (MCP) · 10 Roadmap · 11 Domínios futuros · 12 Referências

---

## 1. Princípios

1. **Rastreabilidade.** Cada equação tem no docstring a citação da fonte (livro, edição, equação,
   tabela ou secção). Não há "números mágicos": um valor sem fonte entra como **pressuposto do
   projetista** (`assumptions:` no YAML) ou como **dado de exemplo** (rotulado `EXAMPLE_…` /
   `*_class`). Um método que ainda não existe é um *stub* que nomeia o método de referência a
   implementar (`acdt.core._stub.not_implemented`).
2. **Métodos clássicos primeiro.** Raymer, Roskam, Anderson, Torenbeek, USAF DATCOM, Gudmundsson,
   Nicolai e Megson/Bruhn/Niu. A alta fidelidade (CFD/FEM) serve só para **verificar** e vem no
   fim (§5).
3. **Reutilizar antes de reimplementar** (§8). Ferramentas copyleft ou com licença
   restritiva (GPL/AGPL/NOSA) nunca são importadas nem distribuídas. São chamadas como programas externos,
   por ficheiros ou CLI.
4. **Requisitos abertos.** Qualquer subconjunto de requisitos é válido, com unidades e sentido
   (min/max/target/objective). Validamos a consistência antes de dimensionar (§4).
5. **Sem sobre-engenharia.** O orquestrador é uma sequência simples de etapas. Os acoplamentos
   iterativos (MDA) vivem dentro das etapas ou do módulo MDO.
6. **Soluções são opções de projeto, não imposições.** Qualquer solução — flaps de curvatura (*camber
   flaps*), configurações pouco usuais, sistemas alternativos, por mais criativa que seja — entra como uma
   **opção** que o otimizador avalia contra as alternativas, com o mesmo conjunto de requisitos e
   restrições. Só é selecionada quando os requisitos a justificam (ganho medido na função objetivo ou
   restrição que só ela cumpre), e o relatório mostra a comparação. O framework deve explorar o espaço de
   soluções o mais largo possível; o projetista pode fixar ou excluir opções explicitamente.

> **Nota de edição.** Os números de equação e de tabela de Raymer referem-se à
> *Aircraft Design: A Conceptual Approach*, **6.ª ed.** (AIAA, 2018). Noutras edições a numeração
> pode mudar: confirme. Gudmundsson (2014) é citado à secção (Cap. 3, Sec. 3.2). As referências
> completas estão no §12.

---

## 2. Núcleo agnóstico vs. plugins de domínio

```
src/acdt/
├── __init__.py                 # G0, versão
├── cli.py                      # `acdt size <spec.yaml>` / `acdt requirements --domain …`
├── core/                       # ← NÃO contém métodos de nenhum domínio
│   ├── units.py                # conversões SI ↔ imperiais/moeda (USD)
│   ├── atmosphere.py           # ISA (ICAO Doc 7488 / ISO 2533), com ΔT
│   ├── requirements.py         # registo de tipos de requisito, sentidos, validadores por domínio
│   ├── pipeline.py             # Domain, Stage, DesignState, run_pipeline()
│   ├── mdo.py                  # (Fase 3) ponte para OpenMDAO
│   ├── tools/highfidelity.py   # (Fase 4) entradas SU2 / CalculiX → domains/aircraft/hifi (OpenFOAM: stub)
│   ├── systems/                # seleção de componentes, energia, cablagem, massa/CG, normas
│   │   ├── database.py         #   base de dados de componentes (YAML)
│   │   ├── battery.py  electric_propulsion.py  servos.py  avionics.py
│   │   ├── harness.py          #   netlist, bitola (corrente/queda/comprimento), WireViz/DOT
│   │   ├── mass.py             #   inventário de massas e CG
│   │   └── compliance.py       #   checklist de normas aplicáveis
│   └── data/                   # components.yaml, standards.yaml
└── domains/
    └── aircraft/               # ← plugin de domínio (1.º domínio)
        ├── __init__.py         # regista o Domain "aircraft" e as suas etapas
        ├── requirement_types.py# tipos de requisito + validador de consistência do domínio
        ├── mission.py          # leitura do YAML de missão
        ├── weights.py  propulsion.py  geometry.py  constraints.py  cost.py  sizing.py
        ├── aero/ lift.py drag.py interfaces.py  # DATCOM/Raymer + adaptadores AVL/AeroSandbox/NeuralFoil
        ├── systems_integration.py               # fecho sistemas ↔ dimensionamento
        ├── report.py                            # relatório markdown + gráficos + JSON
        ├── structures.py stability.py performance.py weights_detailed.py detailed_sizing.py   # fases 2–4
        └── hifi/              # Fase 4: geometry/vsp_build (OpenVSP), cfd/cfd3d (Gmsh+SU2), fem (CalculiX),
                               #   flutter (modos + DLM PanelAero, p-k), nastran (SOL 103/145), calibration, run (`acdt hifi`)
```

**O que é do núcleo:** unidades, atmosfera, registo de requisitos, orquestrador e estado de
projeto, ciclo MDO, wrappers de CFD/FEM/malhagem, seleção de componentes, elétrica e cablagem,
massa/CG, checklists de normas e relatórios genéricos. Tudo isto serve igualmente para um barco, um
carro ou um robô. A atmosfera ISA vive no núcleo porque é partilhada (aeronaves, e cargas de
vento e altitude noutros domínios).

**O que é do domínio:** os tipos de requisito próprios (p. ex. `stall_speed`), os métodos
clássicos (Raymer/DATCOM…), as etapas do pipeline e o relatório específico.

### 2.1 Como um domínio se liga ao núcleo

```python
from acdt.core.pipeline import Domain, Stage, register_domain
from acdt.core.requirements import RequirementType, register_requirement, register_validator

register_requirement(RequirementType("displacement", "mass", "t", ("sizing",), ("target", "max"),
                                     domains=("marine",), reference="PNA Vol. I"))

@register_validator("marine")
def validate_marine(rs): ...            # devolve list[Issue]

register_domain(Domain("marine", "Navios e embarcações", load_spec=..., stages=[Stage("hydrostatics", ...)]))
```

O YAML escolhe o domínio com `domain: marine` (por omissão `aircraft`), e `acdt size` despacha para
o pipeline desse domínio. O teste `tests/test_requirements.py::test_toy_domain_plugs_into_pipeline`
prova que um domínio novo se liga sem alterar o núcleo.

---

## 3. Modelo de dados (estado de projeto)

O `DesignState` (`core/pipeline.py`) é o contentor que passa entre etapas: `spec` (a especificação
lida do YAML), `result` (resultado do dimensionamento), `systems`, `report_path`, mais `issues` e
`log`. Para a aeronave, o `result.json` persistido (ver `report.to_dict`) contém:

| bloco | conteúdo |
|---|---|
| `requirements` | lista normalizada (chave, sentido, valor SI, unidade original, qualificadores, etapas) |
| `weights` | W0, We, Wf/bateria, payload, frações, energia (Raymer Eq. 3.4) |
| `design_point` | W/S, P/W ou T/W, critério, restrições ativas, todas as curvas |
| `geometry` | asa (S, AR, b, λ, c_r, c_t, MAC, Λ), fuselagem, empenagens, layout do caixão da asa |
| `aero` | CLα, CLmax (limpo/descolagem/aterragem), CD0 por componente, e, K, (L/D)max |
| `cost` | (se pedido) custo unitário Eastlake, em USD |
| `systems` | hélice, motor, ESC, bateria, servos, autopiloto, power budget, cablagem, massa/CG |
| `issues` | erros/avisos de viabilidade, por requisito |

A geometria é **paramétrica** desde a Fase 1. O layout estrutural (longarinas, nervuras, cavernas)
já está na geometria e será analisado na Fase 2: a estrutura deriva da mesma fonte de verdade que a
aerodinâmica.

---

## 4. Requisitos abertos

* Cada requisito tem **chave**, **sentido** (`min`, `max`, `target`, `objective: minimize|maximize`),
  **valor + unidade** e qualificadores (p. ex. `at_altitude`, `at_speed`, `reserve`).
* O **registo** (`core/requirements.py`) define para cada tipo a dimensão física, a unidade por
  omissão, os sentidos admitidos, os **domínios** e as **etapas** que o consomem (`context`,
  `sizing`, `constraint`, `check`, `systems`, `trade`). O comando `acdt requirements` lista-os.
* **Plug-in:** `register_requirement()` + `register_handler(stage, key)` adicionam tipos sem tocar
  no código existente (ver o teste `test_plugin_requirement_without_core_change`).
* **Validação** antes de dimensionar:
  * verificações genéricas do núcleo: unidades, sentidos, target fora dos próprios limites,
    min > max;
  * validador do domínio (`validate_aircraft`): para a aeronave, p. ex. payload ≥ MTOW máximo,
    V_cruise e V_max ≤ 1,2·V_stall, V_cruise > V_max, MTOW ou V_stall acima do limite da categoria
    regulamentar (`CATEGORY_LIMITS`), payload em falta (é necessário para fechar a Raymer Eq. 3.4)
    e falta de range e de endurance (aviso: assume-se um loiter de 30 min).
* Requisitos que não se cumprem dão `INVIÁVEL` com o requisito culpado (exit code 1). Requisitos
  contraditórios dão exit code 2. O dimensionamento escolhe o critério do design point pelos
  objetivos: `max_wing_loading` por omissão (Raymer Sec. 5.1), ou, quando há um objetivo de custo
  ou de MTOW, `min_weight` (menor peso vazio por componentes; `min_power` com o método estatístico).

Exemplos com misturas diferentes de requisitos: `examples/uav_endurance_payload.yaml` (endurance +
payload), `ga_range_speed.yaml` (alcance + velocidade + pista), `trainer_maneuver_cost.yaml` (fator
de carga + taxa de volta + custo como objetivo), `uav_overconstrained.yaml` (inviável) e
`cessna172_check.yaml` (verificação).

---

## 5. Escada de fidelidade e critérios de passagem

| nível | conteúdo | métodos / ferramentas | estado |
|---|---|---|---|
| **L0 — conceptual (Fase 1)** | W0 por regressão (valor inicial) + **pesos por componente iterados** (§5.2) + Breguet/elétrico; diagrama de restrições; geometria 1.ª iteração; CLα/CLmax DATCOM; CD0 por build-up; MDA de ponto fixo | Raymer Cap. 3, 5, 6, 7, 12, 15; Nicolai & Carichner Tab. 5.1; Gudmundsson Cap. 3; DATCOM; Hepperle | **implementado** |
| **L1 — baixa fidelidade com interfaces (Fase 2)** | polares de perfil (XFOIL/NeuralFoil) + VLM (AVL) no ciclo; V-n (CS-23 / STANAG 4671) com n_lim realimentado nos pesos; Schrenk/AVL → V, M, T → viga-caixão (Megson/Bruhn) como cross-check da asa; ponto neutro, margem estática, envelope de CG, volumes de cauda, derivadas de controlo; missão por segmentos, payload–range, subida/teto, pistas · pendente: pesos Classe II (Roskam V), aeroelasticidade clássica, C_h DATCOM | Raymer Cap. 15, 16, 17; Anderson; Etkin & Reid; Nelson; Megson; Bruhn; Schrenk (NACA TM 948); Pratt (gust) · AVL 3.40, XFOIL 6.99, NeuralFoil | **implementado** (§5.3); pendentes são stubs honestos (Fase 3) |
| **L2 — MDA/MDO (Fase 3)** | disciplinas como componentes OpenMDAO; Newton/NLBGS; otimização com gradiente; **aeroestrutura estática** (VLM + viga-caixão: flexão/torção corrigem desempenho e peso da asa) | OpenMDAO, OpenAeroStruct; região de confiança com correção de 1.ª ordem (Alexandrov et al. 1998/2001) | **implementado** (`domains/aircraft/mdo.py`, `acdt optimize`; §5.4); dymos (trajetória) pendente |
| **L3 — alta fidelidade (Fase 4)** | RANS, FEM de casca do caixão, malhagem; **flutter FEM modal + doublet-lattice** com margens de certificação | OpenVSP (geometria, STEP/STL, CompGeom, render 3-D); Gmsh + SU2 8.5 (RANS-SA 2-D com GCI de Celik; Euler 3-D da asa e caso RANS do avião completo preparados); CalculiX 2.23 (casca S8R do caixão: estática, encurvadura, modos); DLM PanelAero + p-k; decks Nastran SOL 103/145 (pyNastran); Roskam V Classe II; nervuras/ligação/superfícies de comando; fatores de calibração L3 → L1/L2 | **implementado** (`domains/aircraft/hifi/`, `acdt hifi`; §5.5, `docs/tutorial-fase4.md`); OpenFOAM: stub; casos 3-D grandes listados para máquina mais potente |

**Critérios de passagem (gates).** Só se sobe um nível quando o anterior cumpre tudo isto:

* **L0 → L1:**
  * todos os requisitos validados e o projeto `VIÁVEL`;
  * MDA convergido (|ΔW0|/W0 < 0,1 %);
  * verificação do caso de referência (Cessna 172S: W0 e We ±15 %, P e W/S ±25 %, em
    `tests/test_sizing_c172.py`);
  * We/W0 por componentes dentro da banda das classes estatísticas aplicáveis (aviso no relatório)
    ou desvio justificado / calibrado com dados próprios;
  * margens de restrição conhecidas.
* **L1 → L2:**
  * pesos Classe II (Roskam V) dentro de ±10 % do build-up de L0, ou diferença explicada;
  * velocidades de divergência, inversão e flutter (estimativa) acima de 1,2 V_D;
  * VLM/AVL e DATCOM concordam em CLα dentro de ±15 % (a verificação AeroSandbox já mede isto);
  * margem estática positiva em todo o envelope de CG;
  * cargas V-n e caixão da asa dimensionados com margem ≥ 0.
* **L2 → L3:**
  * ótimo MDO estável a perturbações dos pressupostos (análise de sensibilidade);
  * geometria congelada em OpenVSP/STEP;
  * estudo de convergência de malha planeado.
  * A L3 serve para **verificar** CD0, CLmax, Cm e tensões/encurvadura, e não para dimensionar.
    Discrepâncias acima da tolerância fazem voltar a L1/L2 com fatores de calibração rastreados.

### 5.1 Aeroelasticidade na escada de fidelidade

| nível | método | ferramenta / referência | estado |
|---|---|---|---|
| L1 (Fase 3) | divergência torsional e inversão de aileron (teoria das faixas, Glauert), flutter binário flexão–torção (modos assumidos, aerodinâmica quase-estacionária); critérios simplificados FAA AEER-45 quando aplicáveis | Wright & Cooper, *Introduction to Aircraft Aeroelasticity and Loads* (2.ª ed., 2015); Bisplinghoff, Ashley & Halfman, *Aeroelasticity* (1955); Hodges & Pierce, *Introduction to Structural Dynamics and Aeroelasticity* (2.ª ed., 2011); FAA AEER No. 45 | **implementado** (`aeroel:*`, margem vs 1,2 V_D) |
| L2 (Fase 3) | acoplamento aeroestrutural **estático**: VLM + viga-caixão; a flexão/torção corrige carregamento, arrasto induzido, torção e peso da asa no ciclo de desempenho | **OpenAeroStruct** (NASA/U. Michigan, Apache-2.0) sobre **OpenMDAO** (Apache-2.0) | **implementado** (`static_aerostructural`: cruzeiro + manobra, K_flex/K → missão flexível) |
| L3 (Fase 4) | modos FEM + aerodinâmica não estacionária **doublet-lattice**, flutter p-k/k, com margens de certificação | modos CalculiX do caixão (casca) + DLM PanelAero (DLR, BSD-3), p-k (Hassig 1971); deck Nastran SOL 145 escrito/lido com pyNastran (BSD-3) para correr num Nastran do utilizador (MSC/Simcenter ou NASTRAN-95, NOSA 1.3) | **implementado** (`hifi/flutter.py`, `hifi/nastran.py`; `k_flutter` calibra o flutter da Fase 3) |

Base de certificação (cláusulas **a verificar** na emenda/edição aplicável antes de usar):
14 CFR 23.2245 / CS 23.2245 (livre de flutter, inversão e divergência dentro e *suficientemente
além* do envelope de projeto estrutural); o antigo 14 CFR 23.629 (antes da Amdt. 23-64) pedia
análise racional até 1,2 V_D e admitia os critérios AEER-45 para V_D < 260 KEAS e M < 0,5;
STANAG 4671 (UAV) USAR.629 "Flutter". Fase 3: margem codificada V > 1,2 V_D (EAS,
`aeroelasticity.margin_factor`) como verificação; a margem final de certificação exige L3.

### 5.2 Estimativa de pesos e ciclo iterativo (Fase 1)

Objetivo: **estimar** o peso vazio a partir da geometria e iterar, em vez de o fixar.

1. Valor inicial estatístico de We/W0 (`assumptions.weights.initial_class`), com fonte:
   Raymer Tab. 3.1 (inclui 3 classes UAV), Nicolai & Carichner (2010) Tab. 5.1
   (We = A·W0^B; UAV de hélice < / > 12 h, ISR turbina, UCAV, alvo, GA ligeira). Os nomes antigos
   `uav_gasoline` e `uav_small_electric` são apenas aliases de Raymer Tab. 3.1 (`uav_tactical_recce_ucav` e
   `uav_small`). Estatística própria da empresa entra como `fixed_fraction` (PRESSUPOSTO com fonte) ou
   regressão (A, C) do utilizador (Raymer Sec. 3.3).
2. Geometria → `weights_detailed.component_weights`: Raymer Eqs. 15.46–15.59 (asa, empenagens,
   fuselagem, trem, motor instalado, combustível, comandos, hidráulica, elétrico, aviónica, interiores),
   fatores de compósito (Tab. 15.4), piso de espessura mínima (Swet × densidade areal do laminado),
   massas reais da Fase 1E (motor/ESC, servos, autopiloto, **cablagem dimensionada × ρCu**), itens
   listados pelo utilizador, margem de crescimento e fatores de calibração.
3. We_comp entra na equação de fecho W0 = (W_crew + W_payload + We)/(1 − Wf/W0) (iteração Classe II);
   repete-se design point → geometria → arrasto → pesos até W0, CD0 e We convergirem.
   Para objetivos de massa/custo, o design point escolhe o W/S de **menor peso vazio**
   (`criterion: min_weight`), porque `min_power` ignora o peso da asa.
4. Relatório: tabela por item/grupo (% W0), composição de W0, histórico (We usado vs We_comp) e
   cross-check com todas as classes estatísticas aplicáveis; aviso se fora de ±15 % da banda.

Limitações: as equações de Raymer são de aviação geral (~1000–8000 lb); abaixo disso são
extrapolação (aviso automático) — calibrar com dados próprios. As equações de UAV de Gundlach
(*Designing Unmanned Aircraft Systems*) não foram verificadas na fonte e não estão implementadas.

### 5.3 Fase 2 — baixa fidelidade no ciclo (L1)

Pipeline: `sizing+systems → stability → performance → report`. O ciclo de ponto fixo da Fase 1
continua a ser o "fecho" de W0; a Fase 2 acrescenta disciplinas **dentro** do ciclo (aero low-fi,
V-n → Nz) e estágios de **verificação** depois dele (estabilidade, desempenho por segmentos).

**Aerodinâmica low-fi** (`aero/lowfi.py`, `assumptions.aero.fidelity: lowfi`):

1. o ciclo converge primeiro com o build-up de manual (Raymer Eq. 12.24 + Oswald Eq. 12.48/12.49);
2. depois liga-se o low-fi e o ciclo reconverge (tolerância `mda.tol_lowfi` = 2e-4, limitada pela
   precisão das saídas AVL/XFOIL);
3. polares de perfil XFOIL 6.99 (NeuralFoil como alternativa) ao Re de cruzeiro com transição
   fixa em `laminar.wing`; clmax ao Re de perda com transição livre (Ncrit 9). Polares guardadas
   em cache a 2 algarismos significativos de Re e interpoladas em log Re para manter o ponto fixo
   contínuo;
4. AVL 3.40 (VLM) a α = 2° e 6°: cl local linear em CL por faixa, e_inv no plano de Trefftz,
   fator de fuselagem de Kroo 1 − 2(d/b)²; sem AVL usa-se Schrenk;
5. o arrasto de perfil da asa integrado por faixas substitui o termo Cf·FF da asa de Raymer
   (mantém-se Q e o fator de fugas/protuberâncias); ajuste parabólico em CL ∈ [0,1; 0,85 CLmax].

**Estruturas** (`structures.py`): V-n de manobra e rajada (CS 23.333/335/337/341, fórmula de
Pratt; STANAG 4671 USAR.333/335/337/341, verificados no texto). n_lim = max(manobra, rajada) entra em
`limit_load_factor` (Nz = 1,5 n_lim nas Eqs. 15.46–15.59) se `structures.load_factor_from_vn`.
Carga Schrenk (ou forma c·cl do AVL) − alívio de inércia → V, M, T → caixão de duas longarinas
(banzos M/(hσ), almas por corte + Bredt–Batho, revestimento por torção, espessuras mínimas,
nervuras, fator não-ótimo 1,25). A massa do caixão é um **cross-check** de Raymer Eq. 15.46 em
cada iteração (`weights.components.wing_method: box` substitui-a).

**Estabilidade** (`stability.py`, `phase2.py`): ponto neutro de manual (Raymer Sec. 16.3,
dε/dα = 2CLα/(πA), deslocamento do a.c. pela fuselagem) e AVL (Xnp, sem fuselagem); a asa é
posicionada por bisseção para SM = 10 % no CG mais recuado; envelope de CG a partir da
decomposição de pesos (estações = PRESSUPOSTOS), volumes de cauda vs classe, derivadas de controlo
(manual vs AVL), compensação do profundor em cruzeiro e a CLmax.

**Desempenho** (`performance.py`): missão por segmentos (descolagem, subida integrada a V_y,
cruzeiro/espera em passos de tempo, descida a (L/D)max, aterragem), alcance/autonomia, payload–range
(A/B/C/D; elétrico O/A/B/D), ROC(h), tetos de serviço/absoluto (Anderson), descolagem (Raymer 17.8)
e aterragem (Raymer 17.9). V_y = max(V_mp, 1,2 V_S1) (CS 23.65(a)), também no diagrama de
restrições. Os resultados `perf:*` são **verificação**: não alteram `feasible`, mas definem
`verified` e aparecem como avisos.

**Limitações conhecidas (Fase 2):**

* low-fi não inclui o arrasto viscoso dependente de CL da fuselagem/cauda nem o arrasto de
  compensação → e_eff (≈0,90–0,93) acima do Oswald de Raymer;
* AVL sem fuselagem (ponto neutro AVL mais à ré; o de manual com fuselagem é o usado);
* estações de CG são pressupostos até existir um layout;
* banzos sem crippling; revestimento verificado como painel NÃO reforçado (falha → tensão
  diagonal de Kuhn, Fase 3); superfícies de comando, ligações e trem/tanques não incluídos no
  caixão → a massa do caixão é um limite inferior;
* aterragem com ângulo de aproximação de 3° (`performance.approach_angle_deg`), conservador
  para aviação ligeira;
* autonomia elétrica: (Fase 3) o dimensionamento usa a energia de descolagem/subida por
  segmentos, a mesma da verificação;
* scissor plot, modos dinâmicos e aeroelasticidade: implementados na Fase 3 (§5.4); Classe II Roskam
  (Parte V, equações USAF/Cessna): Fase 4, como verificação cruzada (`weights_detailed.roskam_class_ii`).

### 5.4 Fase 3 — MDA/MDO e verificações clássicas (L2)

* **MDO** (`domains/aircraft/mdo.py`, `acdt optimize`):
  * formulação MDF em OpenMDAO; MDA NLBGS/Newton; SLSQP;
  * variáveis W/S e AR (P/W vem do envelope do diagrama, ou é variável com `mdo.design_vars`);
  * objetivo e restrições vêm do registo de requisitos;
  * gestão de modelos por região de confiança com correção de 1.ª ordem: modelo de manual
    corrigido vs pipeline completo como alta fidelidade;
  * passos com novas falhas ou ρ ≤ 0,01 são rejeitados.
* **Correções:**
  * energia de descolagem/subida elétrica por segmentos dentro do dimensionamento;
  * ângulo de aproximação `performance.approach_angle_deg` (3° = 5,2 %, CS/14 CFR 23.75(a)(1)).
* **Aeroelasticidade:** `aeroel:*` (divergência, inversão, flutter binário, AEER-45) e
  OpenAeroStruct estático (K_flex/K → missão flexível).
* **Estruturas:** caixão dimensionado por encurvadura (Farrar, Bruhn C5), crippling de Needham e
  Kuhn; comparado com o de resistência e com Raymer Eq. 15.46 (cross-check; Raymer continua a
  ser usado).
* **Estabilidade:** scissor plot, inércias, modos e qualidades de voo `hq:*` (MIL-F-8785C).
* As verificações `perf:*`, `hq:*` e `aeroel:*` não alteram a viabilidade do dimensionamento.
* Detalhes e resultados: `docs/tutorial-fase3.md`.

### 5.5 Fase 4 — verificação de alta fidelidade (L3)

* **Orquestrador** `acdt hifi missão.yaml [-o pasta] [--steps …] [--force]` (`hifi/run.py`): corre
  os passos `geometry, cfd2d, gci, wing_euler, rans_case, fem, flutter, nastran, detailed, calibration`,
  reutiliza o JSON de cada passo já corrido e escreve `report_fase4.md` e `calibration.json`.
* **Guarda de computação** (`hifi/tools.budget`): cada passo estima RAM e tempo antes de correr; o que
  passa o limite da máquina fica preparado (ficheiros + comando) e é listado na secção
  "Para uma máquina mais potente" do relatório.
* **Calibração** (`hifi/calibration.py`): razões L3/L1–L2 do mesmo desenho, com as fontes; aplicadas só
  por grupo e por opção do utilizador (`assumptions.calibration.apply: [aero, flutter]`); os métodos
  L1/L2 não mudam. O relatório L1/L2 mostra os fatores aplicados e a sua origem.
* **Verificação**: GCI (Celik et al. 2008) com erro iterativo verificado (Roache 1998) e
  convergência oscilatória tratada por gama (Stern et al. 2001); FEM contra a viga da Fase 3; DLM p-k
  contra a estimativa de faixas da Fase 3; deck Nastran relido com xref.
* Detalhes e resultados: `docs/tutorial-fase4.md`.

### 5.6 Fase 5 — estrutura interna da asa no ciclo (L1/L2 com secção real e FEM próprio)

* **Secção real** (`wingbox/section.py` + `core/thinwalled.py`): caixão sobre o contorno NACA 4 dígitos, célula D
  opcional; centro de corte, EI e GJ de secção multicelular (Megson). Alimenta o eixo elástico e a aeroelasticidade
  da Fase 3 (`assumptions.structures.elastic_axis: section`).
* **FEM de cascas** (`core/fem`): Q4 QM6 + MITC4, vigas excêntricas, estática / encurvadura / modos; verificado
  contra soluções analíticas e contra o CalculiX da Fase 4 (desvios em `docs/tutorial-fase5.md`). Só verificação:
  não entra no ciclo.
* **Problema asa** (`wingbox/optimize.py`): longarinas, t/c raiz/ponta, curvatura, torção, nervuras, pele mínima;
  caixão redimensionado pela Fase 3 em cada avaliação; NeuralFoil + linha sustentadora de Glauert com torção
  elástica; restrições aeroelásticas, C_Lmax, volume de combustível; objetivos massa / alcance / autonomia / MTOW.
* **CLI** `acdt wingbox missão.yaml [-o pasta] [--objective …] [--tc …]` (`wingbox/study.py`): varrimento de t/c,
  ótimo, verificação FEM e render 3-D da estrutura interna.

### 5.7 Fase 6 — RCS, materiais, secções e caixão à encurvadura calibrado pelo FEM

* **RCS** (`core/em/po.py`, `core/em/validate.py`, `domains/aircraft/rcs/*`): Óptica Física PEC com o integral de
  faceta de Gordon, oclusão e 2.º ressalto SBR; validação canónica (placa, esfera, cilindro, diedro); aeronave
  facetada paramétrica e otimização aero/RCS (DOE LHS em OpenMDAO + ε-restrição COBYLA + Pareto). CLI
  `acdt rcs study|stl|validate`. Baixa fidelidade: sem difração de arestas nem RAM.
* **Materiais** (`core/materials.py`): metais MIL-HDBK-5J; compósitos como **isotrópico equivalente** (CLT +
  *cut-offs* de deformação `ASSUMPTION`); núcleos (H80, balsa). O laminado ortotrópico fica para a alta fidelidade.
* **Secções** (`core/sections.py`): I/C/Z/T/L/hat/tubos/longarina composta, propriedades de linha média, centro
  de corte, encurvadura local e *crippling* (Gerard/Needham); tensão admissível do banzo por tipo de longarina.
* **Caixão Fase 6** (`wingbox/sizing6.py`): revestimento com reforçadores Z (coluna Euler–Johnson, *crippling*,
  sem encurvadura da pele até à carga limite + largura efetiva de von Kármán à última) ou sanduíche (Allen, corte
  do núcleo, enrugamento); banzos pela secção (φ_cap variável); nervuras dimensionadas (esmagamento de Brazier/Niu,
  corte, encurvadura, furos de alívio); n_str e tipo de longarina como variáveis discretas.
* **Calibração viga ↔ cascas** (`wingbox/shell6.py`): FEM de cascas sobre o contorno real (nariz em D, banzos e
  reforçadores excêntricos, nervuras) → k_EI, k_GJ, Δx_sc, k_σ (e GA) por baía, usados dentro do ciclo;
  recalibração no ótimo; verificação no caso de projeto (`wingbox/optimize6.py`, `wingbox/study6.py`,
  CLI `acdt wingbox6`).
* **Geometria**: `geometry.wing_position` high|mid|low (C172 asa alta) no OpenVSP.

### 5.8 Fase 7 — fabrico e custo (escada de fidelidade L0 → L1 → L2)

`domains/aircraft/manufacturing/*`, CLI `acdt manufacture`, ferramentas MCP `manufacturing_plan`,
`cost_estimate`, `process_options` e `compare_materials`. Tutorial: `docs/tutorial-fase7-fabrico-custo.md`.

* **Peças** (`parts.py`): o projeto dimensionado é decomposto em revestimentos, longarinas, nervuras, cascas e
  cavernas. As massas vêm do build-up de pesos e são repartidas por área (gauge uniforme, ASSUMPTION).
* **Processos** (`processes.py`): CNC, chapa rebitada, laminação manual, infusão, prepreg OOA/autoclave,
  enrolamento, FDM e SLS. Cada um tem:
  * viabilidade (classe de material, envelope, gauge mínimo, curvatura, axissimetria);
  * horas FOPV (Gutowski 1994; Bao 2002) e ACCEM (camadas);
  * buy-to-fly (Airbus, DAHER, Gonzalo 2023) e rebites (FAA-H-8083-31 / AC 43.13-1B);
  * ferramental, cura e máquina (entradas).
* **Plano** (`plan.py`, `selection.py`):
  * escolha discreta material × processo por peça, ao custo mínimo viável a N;
  * escala de massa pelos índices de Ashby;
  * preços com proveniência, escalados com o CPI-U (BLS);
  * curvas de aprendizagem Crawford/Wright (`costing.py`).
* **Custo** (`costing.py`, `study.py`): Eastlake modificado (Gudmundsson 2014), DAPCA IV (Raymer 2018), custo
  de operação, validação contra preço público.
* **Escada de fidelidade do custo** (`fidelity.py`, `detailed.py`):
  * **L0**: CERs, assinaladas "fora da base de dados" para configurações não convencionais, não tripuladas ou
    com propulsão nova;
  * **L1**: bottom-up paramétrico (projeto preliminar);
  * **L2**: bottom-up detalhado (lista de peças, camadas, fixadores, BOM, cotações, horas de oficina).

  Cada nível tem confiança e banda AACE 18R-97 (Classes 5/4/3). O nível superior calibra o inferior
  (`cost_calibration.json`: `k_cost_L0_*`, `k_labour_hours_L1`, `k_material_L1`), com aplicação opt-in, como na
  Fase 4.
* **MDO** (`pareto.py`): varrimento W/S × AR × opção de material/processo com o MDA L0. A variação de massa do
  material escolhido é realimentada em W0, a fabricabilidade entra como restrição, e o resultado é uma frente
  W0–custo não dominada.

---


### 5.9 Fase 8 — superfícies de comando e simulador de missão 6-DOF (L1, verificação pelo JSBSim)

`domains/aircraft/flightsim/*`, CLI `acdt controls` e `acdt simulate`, ferramentas MCP `size_control_surfaces`
e `simulate_mission` (jobs). Tutorial: `docs/tutorial-fase8-simulador.md`.

* **Superfícies** (`controls.py`): varrimento da fração de envergadura do aileron e de
  c_f/c do profundor e do leme no AVL; critérios MIL-F-8785C IXa (tempo para inclinar), rotação sobre o trem
  principal (Sadraey Sec. 12.6.3), compensação no envelope de CG × flaps, vento cruzado 14 CFR 23.233, OEI;
  flaps por Raymer Eq. 12.21 invertida; momentos de charneira AVL nas condições 14 CFR 23.455.
* **Modelo de voo** (`aeromodel.py`): tabelas AVL α × flap (forças, momentos, derivadas de comando e
  amortecimento), perda por mistura sigmoide até ao CL_max do projeto; massa e inércias da soma de componentes;
  propulsão do modelo de desempenho do dimensionamento. Gravado em `flight_model.json`.
* **Dinâmica** (`sixdof.py`): equações de Stevens & Lewis em quaterniões, RK4; contacto com o solo por
  molas-amortecedores (trem ou patins a D/2).
* **Piloto automático** (`autopilot.py`): fecho sucessivo de malhas (Beard & McLain Cap. 6), limitador de α,
  seguimento de linhas e órbitas (Eqs. 10.8 / 10.13), zonas de altitude, flare exponencial.
* **Missão** (`mission.py`, `wind.py`): segmentos YAML; Dryden (Beard & McLain Tab. 4.1, estados reescalados
  quando L muda) e rajadas 1−cos (CS 25.341); extrapolação estacionária de segmentos longos; k_energia contra o
  modelo quase-estacionário do dimensionamento. `patrol` é a mesma órbita que `loiter`.
* **Massa pontual** (`pointmass.py`, `sensors.py`, `failures.py`): o mesmo YAML em 3-DOF quase-estacionário
  (Anderson 1999 Cap. 5, Raymer 2018 Cap. 17) para N0/N1, com pegada de sensor no rasto e falhas determinísticas.
  A resposta da falha só é voada aqui; no 6-DOF fica registada. Tutorial: `docs/tutorial-p3-massa-pontual.md`.
* **Verificação** (`jsbsim_export.py`, `jsbsim_runner.py`): exporta o mesmo modelo para XML do JSBSim, corre-o
  no Python do utilizador (`$ACDT_JSBSIM_PYTHON`, processo separado, LGPL não importado) e compara compensação
  e resposta a um doublet.
* **Estudo** (`study.py`): encadeia dimensionamento → superfícies → modelo de voo → missão → JSBSim e escreve
  `simulation_summary.json`.

## 6. Fases e módulos (domínio aeronave)

| fase | módulo | método clássico (citado no código) |
|---|---|---|
| 1 | `core/atmosphere.py` | ISA, ICAO Doc 7488/3, altitude geopotencial |
| 1 | `domains/aircraft/weights.py` | Raymer Eq. 3.4 (W0), Tab. 3.1/3.2/3.4 (frações), Nicolai & Carichner Tab. 5.1 (UAV), classes de prática (J. Frazão), Eqs. 3.5–3.8 (Breguet jato/hélice), Eq. 3.11 (reserva); Hepperle 2012 (elétrico) |
| 1 | `geometry.py` | Raymer Eqs. 7.5, 7.6, 7.12 (MAC, Ȳ, Swet); Tab. 6.3 (fuselagem), Tab. 6.4 (coeficientes de volume) |
| 1 | `aero/lift.py` | Raymer Eq. 12.6 (Helmbold/DATCOM 4.1.3.2), 12.9, 12.15, 12.21 (flaps) |
| 1 | `aero/drag.py` | Raymer Eqs. 12.23–12.32 (build-up, Cf, FF, rugosidade), 12.48/12.49 (Oswald) |
| 1 | `constraints.py` | Raymer Eq. 5.6 (perda), 5.11 (aterragem), Sec. 5.3 (descolagem); Gudmundsson Sec. 3.2 (cruzeiro, volta, subida, teto); Mattingly (fator β) |
| 1 | `cost.py` | Eastlake (Gudmundsson Cap. 2), em USD |
| 1 | `sizing.py` | MDA de ponto fixo W0 ↔ diagrama ↔ geometria ↔ arrasto |
| 1E | `core/systems/*`, `systems_integration.py` | §7 |
| 1 | `weights_detailed.py` | Raymer Eqs. 15.46–15.59 (pesos por componente, aviação geral), Tab. 15.4 (compósitos); CS-23/14 CFR 23.337 (n_lim); massas da Fase 1E; Roskam Parte V Eqs. 5.2, 5.4, 5.12–5.15, 5.25 (Fase 4, verificação cruzada; não realimenta) |
| 2–4 | `aeroelasticity.py`, `hifi/flutter.py` | §5.1: Wright & Cooper; Bisplinghoff, Ashley & Halfman; Hodges & Pierce; AEER-45; OpenAeroStruct; FEM+DLM (pyNastran/Nastran SOL 145, DLR Loads Kernel) |
| 4 | `hifi/*`, `detailed_sizing.py`, `core/systems/harness.py` (KiCad) | OpenVSP; SU2 RANS-SA (Spalart & Allmaras 1992), GCI Celik et al. 2008, Roache 1998, Stern et al. 2001; CalculiX S8R; DLM Rodden, Giesing & Kálmán 1968/1971 (PanelAero), p-k Hassig 1971; Nastran SOL 145; Roskam V; esmagamento de nervuras (Brazier; Niu Cap. 5), ligação da raiz (Bruhn D1, CS 23.625), Roskam VI Cap. 10 (C_h) |
| 2 | `aero/airfoil.py`, `aero/avl.py`, `aero/lowfi.py` | XFOIL 6.99 (Drela 1989) / NeuralFoil; AVL 3.40 (Drela & Youngren); fator de fuselagem de Kroo; Raymer Eq. 12.24 (restantes componentes) |
| 2 | `structures.py` | V-n CS 23.333–23.341 / STANAG 4671 USAR.333–341 (Pratt), Schrenk (NACA TM 948), V/M/T, viga-caixão idealizada (Megson), Bredt–Batho, encurvadura de painéis (Bruhn C5/C11) |
| 2 | `stability.py`, `phase2.py` | Raymer Cap. 16 (ponto neutro, SM, volumes de cauda), Etkin & Reid e Nelson Cap. 2 (derivadas, compensação), AVL (Xnp, derivadas) |
| 2 | `performance.py` | Raymer Cap. 17 (17.8 descolagem, 17.9 aterragem, segmentos), Anderson *Aircraft Performance and Design* (subida, tetos); CS 23.65 |
| 2 | `report_phase2.py` | relatório §10–§13 (polar low-fi, V-n, cargas, caixão, envelope de CG, payload–range, subida) |
| 3 | `domains/aircraft/mdo.py` | OpenMDAO (Gray et al. 2019), MDF + região de confiança (Alexandrov et al. 1998/2001; Conn, Gould & Toint 2000) |
| 3 | `aeroelasticity.py` | Wright & Cooper (faixas, flutter binário), Glauert (1926), AEER-45; OpenAeroStruct (Jasa et al. 2018) |
| 3 | `structures.py` (encurvadura) | Kuhn (NACA TR-1179), Needham (1954), Farrar (1949), Bruhn C5/C7/C11 |
| 3 | `stability.py` (dinâmica) | Torenbeek 1982 Cap. 9 (scissor), Nelson 1998 / Etkin & Reid 1996 (modos), Roskam V (inércias), MIL-F-8785C |
| 4 | `core/tools/highfidelity.py` | SU2 (Economon et al. 2016), OpenFOAM, CalculiX, Gmsh |
| 5 | `core/thinwalled.py`, `wingbox/section.py` | Megson Caps. 16–19 (multicelular, centro de corte, Bredt–Batho); Abbott & von Doenhoff (NACA 4 dígitos) |
| 5 | `core/fem/*` | QM6 (Taylor, Beresford & Wilson 1976), MITC4 (Bathe & Dvorkin 1985), FSDT de laminados (Reddy 2004), sanduíche (Allen 1969), Cook et al. (vigas, K_G) |
| 5 | `wingbox/aero.py`, `wingbox/optimize.py` | linha sustentadora de Glauert (Anderson §5.3), NeuralFoil, secção crítica (Phillips & Alley 2007), Breguet; Farrar/Needham/Kuhn (Fase 3); SLSQP (Kraft 1988) |
| 6 | `core/em/po.py`, `domains/aircraft/rcs/*` | Óptica Física (Knott, Shaeffer & Tuley 1993 Cap. 5; Balanis 2012 §11.3), integral de faceta de Gordon (1975), SBR (Ling, Chou & Lee 1989); POFACETS (referência) |
| 6 | `core/materials.py`, `core/sections.py` | MIL-HDBK-5J; CLT (Jones 1999); Daniel & Ishai Tab. A.4; CMH-17-3G; Megson (centro de corte); Gerard/Needham (*crippling*); Bruhn C5/C7 |
| 7 | `manufacturing/parts.py`, `processes.py`, `plan.py`, `selection.py` | FOPV (Gutowski et al. 1994; Bao & Samareh 2000; Bao 2002), ACCEM (Hagnell & Åkermo 2016), buy-to-fly (Airbus 2018; DAHER/Alma; Gonzalo et al. 2023), rebites (FAA-H-8083-31, AC 43.13-1B), regras de compósitos (Abbott/MIL-HDBK-17F), Ashby (índices de material) |
| 7 | `manufacturing/costing.py`, `study.py`, `fidelity.py`, `detailed.py`, `pareto.py` | DAPCA IV (Raymer 2018 Cap. 18), Eastlake modificado (Gudmundsson 2014 Cap. 2), Crawford 1944 / Wright 1936 (aprendizagem), CPI-U (BLS), AACE 18R-97 (bandas por nível); validação C172 (GAMA 2024, fliegermagazin 2025) |
| 6 | `wingbox/sizing6.py`, `shell6.py`, `optimize6.py` | Bruhn C7/C11 (Euler–Johnson, largura efetiva de von Kármán), Allen 1969 (sanduíche), Niu §5.4 (esmagamento de nervuras), Kuhn; calibração viga ↔ cascas pelo FEM da Fase 5 |
| 8 | `flightsim/*` | Sadraey 2012 Cap. 12 (superfícies), Stevens, Lewis & Johnson 2016 (6-DOF), Beard & McLain 2012 Caps. 4, 6, 10 (Dryden, piloto automático, guiamento), MIL-F-8785C, CS 25.341, 14 CFR 23.233/23.455; JSBSim (verificação externa) |

Para o fluxo detalhado, ver `docs/tutorial-fase1.md`, `docs/tutorial-fase2.md` e `docs/tutorial-fase3.md`.

---

## 7. Eletrónica, sistemas e cablagem (Fase 1E, no núcleo)

Estes módulos são genéricos: servem qualquer veículo com barramento elétrico.

* **Propulsão elétrica:**
  * hélice dimensionada por limite de Mach de ponta e coeficiente de potência estático;
  * motor selecionado por Kv-alvo (modelo DC de 1.ª ordem, Hepperle 2012) e ESC por corrente.
  * Margens e rácios são **pressupostos do projetista**.
* **Bateria:**
  * S×P pelas tensões e pelas energias e correntes pedidas (taxa C);
  * célula escolhida na base de dados e congelada após a 1.ª iteração do fecho;
  * a energia específica intrínseca do pack (com `pack_overhead`) realimenta o dimensionamento.
* **Servos:**
  * momento de charneira H = C_h q S_c c_c (Roskam Parte VI Cap. 10) a V_D;
  * fator de segurança de 1,5;
  * C_hα/C_hδ são pressupostos até à DATCOM 6.1.6 (stub).
* **Aviónica e power budget:**
  * autopiloto escolhido por requisitos de redundância (IMU/baro/CAN) e firmware;
  * cargas média e de pico por barramento.
* **Cablagem:**
  * netlist de fios e conectores;
  * bitola por **ampacidade** e **queda de tensão** (resistividade do cobre a 20 °C com
    coeficiente de temperatura e comprimento de ida e volta);
  * exportação para **WireViz** (YAML), Graphviz DOT e CSV;
  * a tabela de ampacidade é um **exemplo** a substituir pela derating do SAE AS50881 ou do
    fabricante;
  * netlist KiCad (s-expression, formato "E", `harness.net`) para importar no Pcbnew (Fase 4);
    footprints são placeholders `PinHeader_1x<n>` a substituir pelos conectores reais.
* **Massa e CG:** inventário de todos os componentes selecionados e CG em %MAC.
* **Normas:** checklist gerada a partir de `core/data/standards.yaml`, consoante a categoria, o
  MTOW, se é UAS, e as características do projeto (§9).
* **Fecho:** a massa de sistemas e bateria realimenta W0 até convergir (2 iterações no exemplo
  UAV).
* **Componentes:** as entradas `*_class` da base de dados são **dados de exemplo** representativos
  de uma classe. Antes de decidir, substitua-as por fichas técnicas reais.

---

## 8. Ferramentas externas (reutilização open-source)

Critérios: origem credível (NASA, MIT, Stanford, ONERA/Airbus, universidades), licença
compatível com a distribuição do acdt (Apache-2.0) e manutenção ativa. Verificámos licenças e atividade via a API
do GitHub em 2026-10 (detalhe em `THIRD_PARTY.md`).

| etapa | projeto (origem) | licença | manutenção | integração em acdt | porquê |
|---|---|---|---|---|---|
| L1 aero (VLM, build-up) | **AeroSandbox** (MIT, P. Sharpe) | MIT | ativo | dependência opcional `[aero]`; `aero/interfaces.aerosandbox_crosscheck` | VLM e AeroBuildup validados; mesma licença |
| L1 perfis | **NeuralFoil** (MIT) | MIT | ativo | `aero/interfaces.neuralfoil_polar` | polares rápidas, treinadas em XFOIL |
| L1 aero (VLM + estabilidade) | **AVL 3.40** (M. Drela & H. Youngren, MIT) | GPL | estável | `aero/avl.py`: ficheiro `.avl` gerado da geometria paramétrica + comandos em lote, processo externo; CL, CDi, e, Cm, derivadas, Xnp, carga por faixas, compensação | referência clássica para derivadas de estabilidade |
| L1 perfis | **XFOIL 6.99** (M. Drela, MIT) | GPL | estável | `aero/airfoil.py`: lote por stdin, processo externo; NeuralFoil como alternativa | método de painéis + camada-limite de referência |
| Geometria / VSPAERO | **OpenVSP** (NASA) | NOSA 1.3 | ativo | exportação/importação de geometria (Fase 2–4), não embebido | geometria paramétrica padrão da indústria |
| L2 MDO | **OpenMDAO** (NASA Glenn) | Apache-2.0 | ativo | dependência opcional `[mdo]` (Fase 3) | framework MDA/MDO com derivadas analíticas |
| L2 aeroestrutura | **OpenAeroStruct** (U. Michigan / NASA) | Apache-2.0 | manutenção baixa (último push 2025-10) | padrão de referência; uso opcional | modelo VLM + viga acoplado sobre OpenMDAO |
| L2 trajetória | **dymos** (NASA) | Apache-2.0 | ativo | opcional (Fase 3) | otimização de trajetória/missão |
| L2 otimizadores | **pyOptSparse** (MDO Lab) | LGPL-3.0 | ativo | opcional, importação dinâmica | SNOPT/IPOPT/SLSQP |
| L3 CFD | **SU2** (Stanford / SU2 Foundation) | LGPL-2.1 | ativo (testado 8.5.0) | casos gerados por ficheiro, executável externo (Fase 4) | RANS/Euler com adjunto |
| L3 CFD | **OpenFOAM** (OpenFOAM Foundation) | GPL-3.0 | ativo | casos por ficheiro (stub; Fase 4 usa SU2) | verificação CFD independente |
| L3 FEM | **CalculiX** (G. Dhondt) | GPL-2.0 | ativo (testado 2.23) | ficheiro `.inp`, executável externo (Fase 4) | FEM de cascas: estática, encurvadura, modos |
| L3 FEM I/O | **pyNastran** | BSD-3 | ativo | dependência opcional `[structures]`, `[hifi]` | leitura e escrita BDF (SOL 103/145) |
| L3 aeroelasticidade | **PanelAero** (DLR) | BSD-3 | ativo | dependência opcional `[hifi]` | AIC doublet-lattice para o p-k |
| L3 malhagem | **Gmsh** (C. Geuzaine, J.-F. Remacle) | GPL-2.0+ | ativo | executável externo: o acdt escreve `.geo` e corre `gmsh` num processo separado (`hifi/tools.run_gmsh`); nunca importado nem redistribuído | malhas 2D/3D |
| Cablagem | **WireViz** | GPL-3.0 | ativo | geramos o YAML; o utilizador corre o CLI `wireviz` | diagramas de cablagem a partir de texto |
| Cablagem/PCB | **KiCad** | GPL-3.0 | ativo | só o formato da netlist (Fase 4) | EDA de referência |
| Verificação cruzada | **FAST-OAD** (ONERA / ISAE-SUPAERO / Airbus) | GPL-3.0 | ativo (v1.10, 2026-06) | **não importado**; usado só para comparar resultados | MDA de aviões de transporte, validado |
| Verificação cruzada | **RCAIDE** (Stanford ADL / LEADS) | AGPL-3.0 | ativo | **não importado** (AGPL); só para comparação | sucessor do SUAVE, multi-fidelidade |
| — | **SUAVE** (Stanford ADL) | LGPL-2.1 | **substituído** (último push 2024-02) | **não usado** | substituído pelo RCAIDE |

**Instalar AVL e XFOIL (Linux).** Os pacotes não são distribuídos com o acdt. Compilar a partir
das fontes oficiais (páginas MIT acima) com gfortran: primeiro `plotlib/` (e `eispack/` no AVL)
com o `config.make` gfortran, depois `bin/` com `Makefile.gfortran` (AVL) / secção gfortran do
`Makefile` (XFOIL, precisão simples), e copiar `avl`/`xfoil` para o `PATH`. O pacote Debian
`xfoil` (6.99 dfsg) termina com SIGFPE em modo lote viscoso no nosso teste, por isso foi compilado das
fontes. Sem os executáveis o acdt usa NeuralFoil + Schrenk e regista-o nas notas do relatório; os
testes que precisam deles são ignorados (`skipif`).

Regra de licenças: o acdt é Apache-2.0 (`LICENSE`). Só **importamos** projetos MIT/BSD/Apache, e LGPL de forma
dinâmica e opcional. GPL, AGPL e NOSA comunicam **por ficheiros ou processos**, não são
distribuídos e o utilizador instala-os à parte.

---

## 9. Normas (checklist, `core/data/standards.yaml`)

A tabela lista as normas cuja existência e âmbito foram verificados. A aplicabilidade **não**
equivale a um parecer de certificação.

| âmbito | normas |
|---|---|
| UAS regulamentação | Regulamento (UE) 2019/947 e 2019/945; EASA SORA 2.5; EASA SC Light-UAS; STANAG 4703 (<150 kg) e 4671 (USAR) |
| UAS consenso | ASTM F3298, F2910, F3002, F3005, F3201 |
| Aviação geral | CS-23 (Amdt 5, baseado em requisitos), CS-VLA, CS-LSA |
| Elétrico / cablagem | SAE AS50881 (cablagem aeronáutica), IPC/WHMA-A-620 (conjuntos de cabos), MIL-STD-704F (qualidade de energia) |
| Ambiente / SW / HW | RTCA DO-160G, DO-178C, DO-254 |
| Baterias | UN 38.3 (transporte de lítio) |

---

## 9A. Camada AI-native (`acdt.ai`, servidor MCP)

O utilizador descreve o objetivo; um agente de IA usa as ferramentas do acdt para lá chegar. A camada não
acrescenta métodos de engenharia: expõe os existentes com entradas em JSON-schema e saídas estruturadas, e
regista a proveniência de cada passo.

| módulo | papel |
|---|---|
| `ai/mcp_server.py` | servidor MCP (SDK oficial `mcp`, API v2 `MCPServer` ou v1 `FastMCP`): 28 ferramentas, recursos, prompts; stdio ou HTTP streamable (`acdt mcp [--http]`) |
| `ai/toolkit.py` | implementação das ferramentas (sem MCP, testável diretamente): resolve a fonte do projeto (`spec` / `spec_path` / `run_id` / `example`), aplica nível de fidelidade, dados externos e calibração, chama o pipeline, resume a saída |
| `ai/registry.py` | registo de runs em `runs/<id>/run.json` (`ACDT_RUNS_DIR`): entradas, pressupostos com origem (utilizador + citação / externo / omissão), dados externos, calibração, versões (acdt, Python, bibliotecas, executáveis), commit git, saídas, ficheiros, run pai |
| `ai/external.py` | validação de dados pesquisados na web: proveniência obrigatória (URL, data, tipo de fonte), conversão de unidades, gamas de plausibilidade por tipo de material/componente, coerência (G vs E, ν), *fallbacks* explícitos com aviso |
| `ai/guard.py` | guarda de computação dos passos L3: leves correm; pesados (`cfd2d`, `gci`, `wing_euler`) só com `user_approved`; `ACDT_MCP_HEAVY=never` recusa; resultados existentes reutilizados |
| `ai/jobs.py` | trabalhos assíncronos (thread pool, `ACDT_MCP_WORKERS`): a ferramenta espera `wait_s` e devolve o resultado ou um `job_id` (`job_status`) |
| `ai/catalogue.py` | recursos: catálogo de métodos com referências (extraídas das docstrings), fluxo por etapas, materiais, componentes, normas, documentação, exemplos |

Fluxo e regras para o agente: `AGENTS.md`, `docs/ai-agent-guide.md`. Demonstração end-to-end:
`examples/ai_session/` (testada em `tests/test_ai_session.py`). O repositório guarda só uma base de dados pequena
e citada; o agente pesquisa dados atuais (materiais, componentes, preços) e passa-os validados com fonte e data.

---

## 10. Roadmap

Prioridades das próximas capacidades (definidas pelo utilizador, outubro 2026) em
[CAPABILITIES.md](../CAPABILITIES.md#roadmap-prioridades-definidas-pelo-utilizador-outubro-2026):

* **já planeado**: superfícies de comando + JSBSim 6-DOF; jatos subsónicos;
* **ALTA**: matriz de certificação, segurança ARP4761, W&B/CG + trem (Currey), CAD CadQuery;
* **MÉDIA**: VTOL/eVTOL;
* **BAIXA**: o resto.

| fase | entregáveis | gate de saída |
|---|---|---|
| **1 — Conceptual** ✅ | requisitos abertos, W0, diagrama de restrições, geometria, sustentação/arrasto, custo, relatório | §5 L0→L1 |
| **1E — Sistemas** ✅ | hélice/motor/ESC/bateria/servos/autopiloto, power budget, cablagem, massa/CG, checklist de normas | fecho W0 ↔ sistemas |
| **2 — Preliminar (L1)** ✅ | AVL/XFOIL/NeuralFoil no ciclo; estabilidade e controlo; missão por segmentos e payload–range; V-n; Schrenk + viga-caixão; envelope de CG (pendente → Fase 3: Classe II Roskam, aeroelasticidade clássica, C_h DATCOM) | §5 L1→L2 |
| **3 — MDO (L2)** ✅ | disciplinas OpenMDAO (MDF, NLBGS/Newton, SLSQP, região de confiança); aeroestrutura OpenAeroStruct; scissor plot e modos dinâmicos + MIL-F-8785C; divergência/inversão/flutter/AEER-45; Kuhn + crippling + caixão por encurvadura; passo de catálogo para motor, ESC e célula, fixos dentro do SLSQP (pendente → Fase 4: exportação OpenVSP, netlist KiCad, derivadas analíticas, `hq`/`aeroel` como restrições) | §5 L2→L3 |
| **4 — Detalhado (L3)** ✅ | OpenVSP (geometria, render 3-D); Gmsh + SU2 2-D RANS com GCI; CalculiX casca do caixão; modos + DLM p-k e deck SOL 145; Roskam Classe II; nervuras, ligação raiz, superfícies de comando; netlist KiCad; `hq`/`aeroel` como restrições do MDO (opção); fatores de calibração L3 → L1/L2 rastreados e opcionais (pendente: CFD 3-D e FEM fino em máquina mais potente, OpenFOAM, derivadas analíticas, C_h DATCOM) | verificação ±tolerância |
| **5 — Estrutura interna (L1/L2+)** ✅ | secção real (Megson) no eixo elástico; FEM de cascas próprio verificado (analítico + CalculiX); otimização longarinas/t/c/curvatura/torção/nervuras com aeroelasticidade, C_Lmax e combustível; torção elástica na carga e no arrasto induzido; render 3-D (pendente: SIMP das nervuras, massa de nervuras dimensionada, rigidez de reforçadores com excentricidade no nível A) | FEM vs CalculiX ±1 % estática, ±5 % modos |
| **6 — RCS + estrutura à encurvadura (L1/L2+)** ✅ | PO RCS validada e Pareto aero/RCS; materiais isotrópicos (compósito equivalente); secções paramétricas; caixão com reforçadores/sanduíche, banzos pela secção, nervuras dimensionadas; calibração viga ↔ cascas no ciclo; C172 asa alta (SIMP das nervuras como demo 2-D; pendente: RCS de onda completa, laminados ortotrópicos e não linearidade geométrica na alta fidelidade) | calibração: tip w FEM vs viga ±5 %, V/T de raiz ±3/5 % |
| **AI — camada AI-native** ✅ | servidor MCP (ferramentas, recursos, prompts), registo de runs com proveniência, dados externos validados, guarda de computação, trabalhos assíncronos, sessão de demonstração | testes `test_ai*.py` verdes |
| **7 — Fabrico e custo** ✅ | processos por peça (viabilidade, FOPV/ACCEM, B2F, rebites, ferramental, aprendizagem), escolha discreta material × processo, custo bottom-up vs Eastlake/DAPCA IV, escada de fidelidade do custo L0 → L1 → L2 com bandas AACE e calibração para baixo, Pareto W0–custo, 4 ferramentas MCP; validação C172S (pendente: Roskam VIII, montagem final modelada, exemplo L2 com dados reais) | C172: Eastlake/preço 0.3–1.0; testes `test_phase7_*.py` verdes |
| **7B — Simulador de missão** (próximo) | simulação de missão (JSBSim como executável externo) com o projeto dimensionado | a definir |
| **8 — Jatos** | extensão a propulsão a jato | a definir |
| **D — Domínios** | marinho → automóvel → robótica (§11) | testes de cada domínio verdes |

---

## 11. Domínios futuros

Cada domínio novo é um pacote `acdt/domains/<nome>/` que regista os seus tipos de requisito, o seu
validador, os seus métodos clássicos e as suas etapas, e reutiliza o núcleo (unidades, requisitos,
pipeline, sistemas elétricos e cablagem, normas, MDO, wrappers CFD/FEM).

| domínio | requisitos típicos | métodos clássicos (L0–L1) | reutiliza do núcleo | L3 |
|---|---|---|---|---|
| **Marinho / arquitetura naval** | deslocamento, velocidade de serviço, autonomia, GM mínimo, calado máx. | *Principles of Naval Architecture* (SNAME, Lewis ed.); resistência de Holtrop & Mennen (1982/1984); Savitsky (1964) para planantes; Larsson & Raven, *Ship Resistance and Flow*; Molland, Turnock & Hudson, *Ship Resistance and Propulsion* (séries B de hélices); Tupper, *Introduction to Naval Architecture* (hidrostática/estabilidade) | sistemas elétricos e cablagem, baterias, MDO, OpenFOAM | OpenFOAM (interFoam), CalculiX |
| **Automóvel** | massa, aceleração 0–100, velocidade máx., autonomia, aderência lateral | Gillespie, *Fundamentals of Vehicle Dynamics*; Milliken & Milliken, *Race Car Vehicle Dynamics*; Wong, *Theory of Ground Vehicles*; Pacejka, *Tyre and Vehicle Dynamics* | trem elétrico, bateria, cablagem, normas (ISO 26262 a verificar), MDO | OpenFOAM/SU2, CalculiX |
| **Robótica** | carga útil, alcance do braço, repetibilidade, velocidade de junta, autonomia | Craig, *Introduction to Robotics*; Siciliano et al., *Robotics: Modelling, Planning and Control*; Lynch & Park, *Modern Robotics* | seleção de motores/drivers, power budget, cablagem, massa/CG | CalculiX (rigidez de elos) |

As normas desses domínios entram em `standards.yaml` com o campo `domains` **só depois de
verificadas**.

---

## 12. Referências

* Raymer, D. P., *Aircraft Design: A Conceptual Approach*, 6.ª ed., AIAA, 2018.
* Roskam, J., *Airplane Design*, Partes I–VIII, DARcorporation.
* Gudmundsson, S., *General Aviation Aircraft Design*, Butterworth-Heinemann/Elsevier, 2014.
* Anderson, J. D., *Aircraft Performance and Design*, McGraw-Hill, 1999; *Fundamentals of Aerodynamics*.
* Torenbeek, E., *Synthesis of Subsonic Airplane Design*, Delft UP, 1982.
* Hoak, D. E. et al., *USAF Stability and Control DATCOM*, AFFDL, 1978.
* Nicolai, L. M. & Carichner, G. E., *Fundamentals of Aircraft and Airship Design*, Vol. I, AIAA, 2010.
* Megson, T. H. G., *Aircraft Structures for Engineering Students*; Bruhn, E. F., *Analysis and Design of Flight Vehicle Structures*; Niu, M. C.-Y., *Airframe Structural Design*, 1988.
* Mattingly, J. D. et al., *Aircraft Engine Design*, AIAA (fator β e análise de restrições).
* Hepperle, M., "Electric Flight — Potential and Limitations", NATO STO-MP-AVT-209, 2012.
* Schrenk, O., NACA TM 948, 1940. Etkin, B. & Reid, L. D., *Dynamics of Flight*.
* Gray, J. S. et al., "OpenMDAO", *Struct. Multidisc. Optim.* 59, 2019. Jasa, J. P. et al., "Open-source coupled aerostructural optimization using Python", *SMO* 57, 2018.
* Economon, T. D. et al., "SU2: An Open-Source Suite for Multiphysics Simulation and Design", *AIAA J.* 54(3), 2016.
* Holtrop, J. & Mennen, G. G. J., "An approximate power prediction method", *Int. Shipbuilding Progress* 29, 1982. Savitsky, D., "Hydrodynamic design of planing hulls", *Marine Technology* 1, 1964.
