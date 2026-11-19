# acdt — Capacidades

O que o acdt faz **hoje**, verificado contra o código (outubro 2026). Para cada área:

* o que faz;
* métodos e referências (as citações completas estão no código e em `acdt://methods`);
* o nível de fidelidade;
* o comando CLI e a ferramenta MCP;
* um exemplo do que pedir à IA;
* os limites conhecidos.

Escada de fidelidade: **L0** (manual/estatístico) → **L1** (baixa fidelidade: XFOIL/AVL, vigas) → **L2**
(MDO, estrutura dimensionada) → **L3** (alta fidelidade: CFD/FEM externos, para verificar e calibrar).
Detalhes em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). O workflow de design por níveis (N0 missão → N1 arquitetura →
N2 forma → N3+ fecho), com o mapa destas capacidades e as lacunas de cada nível, está em
[docs/DESIGN_WORKFLOW.md](docs/DESIGN_WORKFLOW.md).

> Ferramenta de apoio ao projeto. Os resultados não substituem a análise de engenharia nem a certificação.

---

## 1. Requisitos

* **O que faz**: um registo aberto de requisitos. Há 23 tipos, entre eles:
  * alcance, autonomia, carga útil, velocidades e teto;
  * pistas, perda, subida, volta e fator de carga;
  * MTOW, envergadura, categoria regulamentar, custo unitário e tipo de propulsão.

  Cada requisito tem sentido (`min`/`max`/`target`/`objective`) e unidades convertidas para SI (kt, km/h, ft, h, lb, …; NIST SP 811).
  Valida os limites da categoria regulamentar.
* **Fidelidade**: —
* **CLI / MCP**: `acdt requirements` / `requirements_schema`, `validate_requirements`.
* **Pedir à IA**: "Valida estes requisitos: UAV de 150 kg, 10 h de autonomia, 20 kg de carga, pista de 300 m."
* **Limites**: o tipo `noise` (L_A,max na vertical) e `aural_detection_range` são avaliados pela etapa de ruído
  (§32r); sem mapa de hélice ou em jatos ficam "não avaliado".

## 2. Conceptual / dimensionamento

* **O que faz**: W0 por frações e Breguet (hélice, jato, elétrico). Seguem-se o diagrama de restrições (P/W ou
  T/W vs W/S) com ponto de projeto automático e a geometria de primeira ordem. Tudo é iterado num MDA de ponto
  fixo (W0 ↔ restrições ↔ geometria ↔ arrasto ↔ pesos).
* **Métodos**: Raymer 6.ª ed. Caps. 3, 5–7 e 19; Gudmundsson 2014 Cap. 3; Hepperle 2012 (elétrico).
* **Fidelidade**: L0 (L1 com `aero.fidelity: lowfi`).
* **CLI / MCP**: `acdt size <missão.yaml>` / `size(level="L0"|"L1")`.
* **Pedir à IA**: "Dimensiona um GA de 2 lugares para 1200 km a 130 kt e mostra o diagrama de restrições."
* **Limites**: estatística de aviação geral e UAV. Neste `size` genérico, jatos só têm fecho estatístico; equações GA não se aplicam.
  O `jet size` separado tem build-up parcial opt-in (§30). O pipeline GA está validado no Cessna 172S
  (W0 e peso vazio a ±15 %); isso não valida os métodos de transporte.

## 3. Pesos

* **O que faz**: We/W0 estatístico, usado só como valor inicial. Segue-se o build-up por componentes (Classe
  II), que fecha o ciclo de pesos, a comparação com Roskam Parte V e o balanço de massa/CG.
* **Métodos**: Raymer Tab. 3.1 e Eqs. 15.46–15.59 (Tab. 15.4 para compósitos); Nicolai & Carichner Tab. 5.1
  (UAV); Roskam Parte V (métodos USAF e Cessna, para comparação).
* **Fidelidade**: L0–L1.
* **CLI / MCP**: dentro de `acdt size` / `size`.
* **Pedir à IA**: "Qual a quebra de pesos por componente e o envelope de CG do UAV de 150 kg?"
* **Limites**: as equações de componentes são de aviação geral. Os compósitos entram por fatores de Raymer.
  O diagrama de carregamento operacional e o trem estão na §20 e correm dentro de `acdt size`.

## 4. Aerodinâmica de baixa fidelidade

* **O que faz**:
  * sustentação: Helmbold/DATCOM, CLmax e flaps;
  * arrasto: build-up por componentes (Cf, FF, Q, rugosidade) e Oswald;
  * na fidelidade L1, polares XFOIL ou NeuralFoil, AVL (VLM) para a distribuição de carga e as derivadas, e
    Schrenk como alternativa;
  * na Fase 5, linha sustentadora de Glauert com torção elástica.
* **Métodos**: Raymer Cap. 12; DATCOM 4.1.3.2; XFOIL (Drela 1989); AVL (Drela & Youngren); NeuralFoil (Sharpe &
  Hansman 2024).
* **Fidelidade**: L0 (manual) e L1 (XFOIL/AVL). O L3 de verificação está na §13.
* **CLI / MCP**: `acdt size` com `assumptions.aero.fidelity: lowfi` / `size(level="L1")`.
* **Pedir à IA**: "Corre o L1 com XFOIL e AVL e compara o CD0 e o CLmax com o manual."
* **Limites**: subsónico incompressível na prática, sem compressibilidade transónica. XFOIL e AVL são
  executáveis externos opcionais; sem eles o acdt usa NeuralFoil e Schrenk.

## 5. Propulsão e energia

* **O que faz**:
  * lapse de potência: pistão por Gagg & Ferrar; turbo proporcional a σ; elétrico constante;
  * UAV elétrico: diâmetro e rpm da hélice (limite de Mach na ponta), Kv e potência do motor, ESC;
  * opt-in BEMT de hélice de passo fixo no ciclo de sistemas (`systems.propeller.method: bemt`), reutilizando
    o solver McCormick/Ning já usado na Fase 9; polar com aerofólio nomeado ou tabela com fonte;
  * opt-in deck de motor Drela 2007 (`systems.motor.deck`: Kv, R, I0 + source) e tabela η(P) já existente
    (`motor_map`); bateria: configuração S/P, energia com reserva e profundidade de descarga, verificação da taxa C.
* **Métodos**: Gudmundsson Sec. 7.2; Anderson (desempenho); Raymer Sec. 10.3; McCormick 1995 Cap. 6 e Ning 2014
  (BEMT); Adkins & Liebeck 1994 (passo/corda auto); Drela 2007 (modelo DC de 1ª ordem); Hepperle 2012.
* **Fidelidade**: L0–L1.
* **CLI / MCP**: `acdt size` (bloco `systems`), `acdt bemt propeller`, `acdt motor-deck` /
  `systems`, `bemt_propeller`, `motor_deck`.
* **Pedir à IA**: "Escolhe motor, hélice e bateria para o UAV elétrico de 25 kg. Pesquisa motores reais e
  valida-os."
* **Exemplos** (EXAMPLE/PRESSUPOSTO, não mapas de fornecedor): `examples/systems/bemt_propeller_illustrative.json`
  (D=0,50 m, passo 0,30 m, J=0,440, η=0,723, rpm cruzeiro 5995, P=749 W vs 1000 W nominais, rpm estático 4652);
  sem diâmetro/polar o estado é unassessed (`bemt_propeller_unassessed.json`). Deck Drela ilustrativo
  (`motor_deck_illustrative.json`): Kv=500 rpm/V, R=0,15 Ω, I0=0,6 A, V=22 V, 8000 rpm → I=40,0 A,
  P_veio≈630 W, η≈0,716; sem R/fonte ou com I>I_max o η não é aplicado (nunca 0,85 silencioso).
* **Limites**: por omissão o ciclo de sistemas continua a ser estatística Raymer Sec. 10.3 + C_P/J do utilizador;
  BEMT e o deck são opt-in. Sem geometria, polar com fonte ou Kv/R/I0+fonte o termo fica unassessed
  (nunca zero/pass silencioso; a estatística não é apresentada como BEMT). Sem catálogo de hélices. Sem
  ilhas de eficiência inventadas. Não há deck de turbofan neste pipeline; a ferramenta separada
  `jet_turbofan` é L0 (§30). A base de componentes é EXEMPLO; os componentes reais entram via
  `validate_component`, com a fonte.

## 6. Estabilidade e qualidades de voo

* **O que faz**:
  * ponto neutro (manual e AVL), margem estática sobre o envelope de CG, volumes de cauda, derivadas de
    controlo e compensação;
  * scissor plot;
  * modos dinâmicos longitudinais (fugoide e período curto) e laterais (espiral, entre outros);
  * níveis MIL-F-8785C; no MDO, por omissão, só filtro pós-ótimo; com
    `assumptions.mdo.hq_aeroel_constraints: true` passam a restrições reais na violação do mérito φ
    (níveis discretos g∈{0,1}; unassessed ≠ satisfeito). Allow-list opcional `mdo.hq_aeroel_keys`.
* **Métodos**: Raymer Cap. 16; Nelson; Etkin & Reid; Torenbeek Cap. 9; Roskam V (inércias); MIL-F-8785C.
* **Fidelidade**: L1–L2.
* **CLI / MCP**: `acdt size` (L1) e `acdt optimize` / `size`, `optimize`.
* **Pedir à IA**: "A margem estática é suficiente em todo o envelope de CG? E os modos cumprem a MIL-F-8785C?"
* **Limites**: a MIL-F-8785C é norma para aviões pilotados (indicativa para UAV). O C_h ainda não vem de DATCOM
  (é entrada). A simulação 6-DOF e o dimensionamento das superfícies de comando estão na secção 17. Os quatro
  casos discretos de CG desta secção mantêm-se; o diagrama operacional (combustível e carga) está na §20.

## 7. Estruturas

* **Viga e cargas**: V-n (CS-23 §23.333–341 / STANAG 4671), Schrenk/AVL → V, M, T, viga-caixão idealizada
  (Megson, Bredt–Batho), encurvadura de painéis (Bruhn), Kuhn, crippling de Needham, caixão por encurvadura
  (Farrar). **L1–L2**.
* **Viga L1 da aeronave** (`structures_l1.py`): fuselagem em tubo (NASA SP-8007), empenagens em caixão e
  torção de cruzeiro na linha sustentadora de Glauert. `structures.flex` e `structures.mass_in_loop` ficam
  desligados por omissão, por isso a polar e as massas de Raymer do ciclo não mudam. Sem pressurização.
* **Secções** (`core/sections.py`): I, C, Z, T, L, hat, tubos e longarina composta. Calcula centro de corte,
  encurvadura local e crippling (Gerard/Needham).
* **Materiais** (`core/materials.py`):
  * metais MIL-HDBK-5J;
  * compósitos como isotrópico equivalente (CLT, Jones), com cut-offs de deformação;
  * núcleos H80 e balsa;
  * materiais externos via `validate_material`, com a fonte.
* **FEM de cascas próprio** (`core/fem`): QM6 + MITC4, vigas excêntricas, laminados e sanduíche (FSDT); análise
  estática, de encurvadura linear e modal. Verificado contra soluções analíticas e o CalculiX (±1 % na estática,
  ±5 % nos modos).
* **Nervuras**: esmagamento (Brazier/Niu), corte e encurvadura, furos de alívio. SIMP 2-D da alma
  (Bendsøe 1989; Bendsøe & Sigmund 2003; filtro Bruns & Tortorelli 2001; OC Sigmund 2001 / Andreassen
  et al. 2011) como demo de layout, e **opt-in** no orçamento de massa: `m_web = mean(ρ)·w·h·t·ρ_mat`
  com `t` de `size_ribs` (Niu §5.4) e `ρ` da ficha de material com fonte; o resto nariz/cauda fica o
  PRESSUPOSTO de 50 % de `size_ribs` (fora do domínio SIMP). Fração de volume e penalização são entradas
  obrigatórias (não inventadas). Só na raiz, ou inputs em falta → unassessed; massas dimensionadas retidas;
  nunca zero silencioso nem unassessed=pass; sem extrapolação entre estações. Não entra no SLSQP.
  Exemplo `examples/wingbox/rib_simp_mass_illustrative.json` (EXAMPLE/PRESSUPOSTO, não resultado FEM/fornecedor).
* **CLI / MCP**: `acdt size`, `acdt wingbox`, `acdt wingbox6`, `acdt rib-simp`, `acdt cad` / `size`, `wingbox(phase=5|6)`, `rib_simp_mass`.
* **CAD da estrutura**: `acdt cad` escreve um DXF em milímetros (planta da asa, duas longarinas, rectângulo
  da fuselagem e secção do caixão na raiz) e, com o extra `acdt[cad]`, uma montagem STEP (revestimentos,
  longarinas, nervuras, cavernas e quatro longarinas da fuselagem). O OpenCASCADE corre noutro processo.
  Sem `--oml` a montagem não traz a casca exterior. Não é um desenho cotado de produção.
* **Pedir à IA**: "Dimensiona o caixão da asa do C172 com reforçadores Z e verifica a encurvadura com o FEM de
  cascas."
* **Limites**:
  * laminado ortotrópico só na alta fidelidade;
  * FEM linear (sem não linearidade geométrica);
  * fuselagem com viga L1 (casca circular NASA SP-8007, longarinas e cavernas mínimas, empenagens em caixão) e torção elástica da asa no ciclo de `size` (`structures.flex` e `structures.mass_in_loop`, ambos desligados por omissão); sem pressurização;
  * sem fadiga nem tolerância ao dano.

## 8. Aeroelasticidade

* **O que faz**:
  * divergência torsional e inversão de aileron;
  * flutter binário em faixas e critérios simplificados AEER-45 (com verificação de aplicabilidade);
  * acoplamento aeroestrutural estático com OpenAeroStruct (VLM + caixão FEM);
  * no L3, modos CalculiX + DLM p-k (PanelAero) e deck Nastran SOL 145.
* **Métodos**: Wright & Cooper; Bisplinghoff, Ashley & Halfman; Hodges & Pierce; AEER-45; Rodden et al. (DLM);
  Hassig 1971 (p-k).
* **Fidelidade**: L2 (L3 na §13).
* **CLI / MCP**: `acdt optimize`, `acdt hifi --steps flutter` / `optimize`, `hifi`.
* **Pedir à IA**: "Qual a margem de flutter a 1.2 V_D? Usa o p-k com DLM e compara com a estimativa de
  faixas."
* **Limites**: só a asa (não a cauda). O deck SOL 145 não é corrido aqui (não há licença Nastran).

## 9. MDO

* **O que faz**: OpenMDAO na formulação MDF, com NLBGS ou Newton e SLSQP. Gestão de modelos por região de
  confiança sobre o pipeline completo. Com `mdo.hq_aeroel_constraints: true`, `hq:*`/`aeroel:*` entram na
  violação de φ e as margens aeroelásticas de faixas também como g≤0 no SLSQP; omissão = comportamento legado
  (filtro pós-ótimo). Unassessed nunca conta como restrição satisfeita.
* **Métodos**: Gray et al. 2019 (OpenMDAO); Alexandrov et al. 1998/2001; Conn, Gould & Toint 2000;
  Geoffrion 1972 (atribuição inteira do motor, do ESC e da célula fora do SLSQP).
* **Fidelidade**: L2.
* **CLI / MCP**: `acdt optimize` / `optimize`.
* **Pedir à IA**: "Minimiza W0 do UAV com restrições de pista e margem estática. Começa em L0 e depois verifica
  em L1."
* **MDO de sistema**: `acdt mdo` (§32l, [docs/MDO.md](docs/MDO.md)) fica por cima deste: qualquer caminho da missão
  como variável, restrições do registo de requisitos, NSGA-II/ε-restrição/DOE e fecho frota ↔ propulsão.
* **Limites**: o SLSQP é contínuo (W/S, P/W, AR). Motor, ESC e célula mudam num passo de catálogo
  separado e ficam fixos dentro do SLSQP. Sem catálogo de hélices (diâmetro de Raymer Sec. 10.3). Os servos
  são reescolhidos no fecho. Sem derivadas analíticas. A verificação L1 no ciclo custa minutos por iteração.

## 10. Caixão da asa (estrutura interna)

* **O que faz**:
  * **Fase 5**: secção real (Megson multicelular) no eixo elástico. Otimiza a posição das longarinas, t/c,
    curvatura, torção e passo de nervuras, com NeuralFoil + linha sustentadora, aeroelasticidade, C_Lmax e
    combustível. Inclui render 3-D.
  * **Fase 6**: revestimento com reforçadores ou sanduíche, dimensionado à encurvadura. Banzos pela secção e
    nervuras dimensionadas. O nº de reforçadores e o tipo de longarina são variáveis discretas. A viga é
    calibrada pelo FEM de cascas dentro do ciclo.
* **Métodos**: Megson; Bruhn C5/C7/C11; Allen 1969; Niu §5.4; Kuhn; Glauert; Kraft 1988 (SLSQP).
* **Fidelidade**: L1–L2+.
* **CLI / MCP**: `acdt wingbox`, `acdt wingbox6`, `acdt rib-simp` / `wingbox`, `rib_simp_mass`.
* **Pedir à IA**: "Otimiza o caixão da asa em compósito sanduíche e compara a massa com a versão metálica
  reforçada."
* **Limites**: perfis NACA de 4 dígitos. A topologia SIMP das nervuras é 2-D linear, um caso de carga,
  volume fixo (não é FEM não linear nem campanha de TO; não chama TACS/ADflow/OpenVSP). A massa SIMP só
  entra no orçamento quando pedida (`assumptions.structures.rib_simp_mass` ou `acdt rib-simp` /
  `wingbox6 --rib-simp-mass`); por omissão o estudo Fase 6 não muda a massa do caixão. Sem fração de
  volume, fonte de ρ/t, geometria ou cargas, ou com SIMP só numa estação, o termo fica unassessed.
  A longarina traseira tem de ficar à frente de todas as charneiras de bordo de fuga (folga 0,03 c,
  PRESSUPOSTO): numa asa voadora o limite lê o maior cf/c de `options.flying_wing` (elevon / split
  aileron / aileron), não só `stability.aileron_cf_c`. A inversão / eficácia de comando (Wright &
  Cooper 2015 Cap. 9; Bisplinghoff, Ashley & Halfman 1955 Cap. 8; derivadas de flap de Glauert 1926)
  corre nas superfícies desenhadas, com o vão real (`eta_inner`–`eta_outer` ou a fracção a partir da
  ponta no aileron convencional). O canal de guinada do split (arrasto de perfil, McCormick Eq. 3.45)
  não inverte por este mecanismo e fica unassessed; o V_R reportado para o split é só o acoplamento
  de rolamento, com derivadas de flap liso (PRESSUPOSTO). A Fase 6 devolve um factor de reserva de
  encurvadura numérico (factor de carga até à envolvente) para peles e nervuras. Opt-in
  `assumptions.structures.wingbox.hold_section` (ou `acdt wingbox --hold-section` /
  `wingbox6 --hold-section`) fixa t/c, curvatura e torção geométrica na geometria de partida (por
  exemplo a torção de Panknin de −10° que fecha o equilíbrio em picada); sem a opção o SLSQP pode
  alterá-las, como até aqui.

## 11. RCS (assinatura radar)

* **O que faz**: Óptica Física PEC com o integral de faceta de Gordon, oclusão e 2.º ressalto (SBR). Validada
  contra casos canónicos (placa, esfera, cilindro, diedro). Inclui a aeronave facetada paramétrica e o Pareto
  aero/RCS (DOE LHS + ε-restrição). **Opt-in (9 nov 2026)**: a montagem pode alimentar o mesmo caminho PO —
  `Body.chine: {angle_deg, crown_frac?}` gera a secção hexagonal com chines longitudinais agudos (mesma
  construção que `rcs.geometry.hexagon_section`); `acdt rcs study <montagem.json>` / `acdt shape study
  --assembly` lê corpos, superfícies, discos e itens box/sphere/cylinder da montagem em vez da geometria
  paramétrica paralela; o inventário marca excluídos (PRESSUPOSTO, ex. hélice) e **unassessed** (nunca
  silêncio; unknown≠zero). Variáveis Shape não mapeáveis (`sweep_le_deg`, `align`, `tail_cant_deg`) ficam
  unassessed no caminho da montagem.
* **Métodos**: Knott, Shaeffer & Tuley 1993; Balanis 2012; Gordon 1975; Ling, Chou & Lee 1989; Nita & Scholz
  2012 (Oswald, no caminho paramétrico).
* **Fidelidade**: L1 (baixa fidelidade).
* **CLI / MCP**: `acdt rcs validate|study|stl` (study aceita `result.json` **ou** JSON de montagem);
  `acdt shape study --assembly`; `acdt integration … --rcs` escreve `rcs_inventory.json` /
  `rcs(mode="validate"|"study")`.
* **Pedir à IA**: "Qual o RCS frontal médio do UAV e quanto baixa com fuselagem facetada a 30°?" /
  "Corre o estudo aero/RCS sobre a montagem com chine."
* **Limites**: só PEC, sem difração de arestas e sem RAM. Não é um solver de onda completa. A proposta de 18 nov 2026, PR #27 (`docs/proposta-rcs-onda-completa.md`), não corre o openEMS e não conta células: sem caixa de cálculo, o número fica em falta. O PO não fica validado por essa proposta. No co-pol
  monostático o factor da faceta reduz-se a −n̂·k̂, por isso VV e HH coincidem. Numa malha facetada da montagem
  os nulos à esquerda e à direita podem diferir vários dB (HANDOFF §4b G4). O DOE da montagem varia
  `chine_deg` nos corpos já com chine; não inventa uma aeronave facetada paralela.

## 12. Sistemas, cablagem e KiCad

* **O que faz**:
  * servos por momentos de charneira a V_D;
  * autopiloto por filtro de requisitos;
  * balanço elétrico de potência;
  * cablagem: secção do condutor por ampacidade e queda de tensão, netlist;
  * exportação para WireViz (`harness.wireviz.yml`), Graphviz, `netlist.csv` e **netlist KiCad**
    (`harness.net`);
  * checklist de normas aplicáveis;
  * fecho massa/energia com o dimensionamento.
* **Métodos**: MIL-E-7016F; Moir & Seabridge; IEC 60028; ASTM B258; SAE AS50881 (referência); Roskam VI
  (charneira).
* **Fidelidade**: L0–L1.
* **CLI / MCP**: `acdt size` (bloco `systems`) / `systems`.
* **Pedir à IA**: "Faz o balanço de potência e a cablagem do UAV, e exporta o netlist para o KiCad."
* **Limites**:
  * a tabela de ampacidade por omissão é EXEMPLO;
  * a checklist diz que normas se aplicam, mas não avalia a conformidade;
  * C_hα e C_hδ são entradas.

## 13. Alta fidelidade (verificação e calibração, L3)

| passo | o que faz | onde corre |
|---|---|---|
| `geometry` | OpenVSP: .vsp3, STEP, STL, render, verificação da área molhada | aqui (leve) |
| `cfd2d`, `gci` | SU2 RANS-SA 2-D da secção (Gmsh), polares, convergência de malha (GCI, Celik 2008) | aqui, **pesado**: precisa de aprovação explícita |
| `wing_euler` | SU2 Euler 3-D da meia-asa, CLα vs AVL | aqui, **pesado**: precisa de aprovação |
| `rans_case` | RANS 3-D do avião completo: **só escreve o caso** e a estimativa de memória e tempo | **máquina maior** |
| `fem` | CalculiX S8R do caixão: estática, encurvadura, modos | aqui (leve) |
| `flutter` | modos + DLM p-k (PanelAero) | aqui (leve) |
| `nastran` | deck SOL 145 (pyNastran), verificado por releitura | escrito aqui; corre noutro sítio, com licença |
| `detailed` | nervuras, ligação da raiz, superfícies de comando, Roskam Classe II | aqui |
| `calibration` | fatores L3 → L1/L2 (`k_clmax`, `k_flutter`, `k_EI`, …), aplicados por opção. `k_cd_profile` da comparação RANS-SA turbulento / XFOIL com transição é reportado e não é aplicado | aqui |

* **CLI / MCP**: `acdt hifi --steps …` / `hifi_estimate` (plano e custo computacional), `hifi`
  (`user_approved` para os passos pesados), `get_calibration`, `apply_calibration`.
* **Pedir à IA**: "Estima o custo do L3 e corre a geometria, o FEM e o flutter. Os passos de CFD pesados só
  depois de eu aprovar."
* **Limites**:
  * o OpenFOAM é um stub;
  * o CFD 3-D grande e o FEM fino precisam de uma máquina mais potente;
  * a guarda de computação recusa o que não cabe;
  * as ferramentas são executáveis externos (GPL fora do processo);
  * o GCI RANS-SA de um α da asa sem deriva correu (13 nov 2026, §32d-ter) com a torção do loft trocada e ficou inválido. Com o sinal certo, só a malha grossa foi repetida (CL SU2/AVL 0,83); o factor não é aplicado. Antes de qualquer RANS de asa, a malha é comparada com o AVL e com o caso SU2; a falha bloqueia a corrida e não aplica factor. O loft e o AVL dessa asa usam o t/c declarado 0,15/0,12; a curvatura do NACA 4415 não é construída e o ΔCL do AVL, no mesmo α, foi 0. Sem factor. O GCI v2 (15 nov 2026, §32d-ter) repete as três malhas com essa secção: CL fino/AVL 0,833 e CMy 1,097, dentro da banda, oscilatórios, factor não aplicado. A linha média de 4 dígitos existe como opt-in e o exemplo continua simétrico. A grossa com o 4415 real deu CL SU2/AVL 0,897 e CMy 0,917, dentro da banda, e o factor não é aplicado: uma malha e um α, sem GCI. A polar da grossa simétrica dá CLmax 1,059 a 20° com controlos alinhados e CD0 viscoso 0,0198; nenhum dos dois factores se aplica. A elevon selada na mesma grossa, a α de cruzeiro e em δ −10°, +10° e −25°, também não aplica factor: uma malha, sem GCI. A split fica por avaliar. O CalculiX do caixão actual (t/c 0,15/0,12, 6,429 kg) marca k_EI 0,571 como válido e não o aplica: o yaml não liga `structures`. k_GJ tem sinais opostos. O DLM cruza a cerca de 285 m/s e as faixas não cruzam. O NLGEOM à carga última não converge. Riks e a inversão por DLM ficam por avaliar. O FFD pyGeo do loft embute 537 pontos e não os move. O cruzeiro ADflow+TACS fica por avaliar. A quarta malha da secção do C172 (18 nov 2026, 107922 células, α = 2°) tem GCI fino de CL 1,2 % e de CD 3,0 %; a deriva do CD é 0,42 % e o erro iterativo não é pequeno. O factor não entra. O RANS da asa com fuselagem estima 22 GB e não correu. O PO da asa com a torção corrigida, a 10 GHz, dá média frontal −10,0 dBsm com uma reflexão e −7,5 dBsm em VV com duas. Não é onda completa e o factor não entra. O OpenVSP 3.48.2 do contentor exporta a asa voadora e o C172; o Windows continua sem OpenVSP. O VSPAERO de superfície fina, no α do AVL, dá CL 0,494 contra 0,503 e CDi 0,01430 contra CDff 0,01454. O CMytot é 0,0416 contra Cmtot 0,0289. Cinco iterações de esteira não são uma convergência. O factor não entra. O RANS do avião completo continua por correr. O pyCycle 4.4.0, noutro intérprete, correu o turbojato simples publicado: TSFC 0,799 lb/(lbf·h) no ponto de projecto, contra 0,400 da correlação L0 de turbofan de alta razão de bypass. Não há deck L1. O factor não entra.

## 14. Fabrico e custo (Fase 7)

* **O que faz**:
  * decomposição do projeto em peças;
  * processo e material por peça: CNC, chapa rebitada, laminação manual, infusão, prepreg, enrolamento, FDM,
    SLS;
  * por cada opção: viabilidade, horas, buy-to-fly, rebites, ferramental e aprendizagem;
  * custo bottom-up comparado com o Eastlake e o DAPCA IV;
  * custo de operação;
  * Pareto W0–custo com realimentação da massa;
  * escada de fidelidade do custo:
    * **L0**: CERs, assinaladas "fora da base" para aeronaves não convencionais, não tripuladas ou com
      propulsão nova;
    * **L1**: bottom-up paramétrico;
    * **L2**: bottom-up detalhado (lista de peças, BOM, cotações);
    * bandas AACE 18R-97 por nível e calibração do nível superior para o inferior.
* **Métodos**:
  * horas: FOPV (Gutowski 1994; Bao 2002) e ACCEM;
  * custo: DAPCA IV (Raymer 2018) e Eastlake (Gudmundsson 2014);
  * aprendizagem: Crawford e Wright;
  * materiais: Ashby;
  * escalada: CPI-U (BLS).
* **Fidelidade**: L0 → L1 → L2.
* **CLI / MCP**: `acdt manufacture <cfg.yaml> [--pareto]` / `manufacturing_plan`, `cost_estimate`,
  `process_options`, `compare_materials`.
* **Pedir à IA**: "Pesquisa preços atuais de tecido de carbono e epóxi, e estima o custo unitário do UAV para
  uma série de 50, com bandas de incerteza."
* **Limites**:
  * Roskam VIII não está implementado;
  * o FOPV sobrestima peças pequenas e precisa de calibração;
  * os processos de compósito não se distinguem em horas sem dados de oficina;
  * a montagem final é uma entrada;
  * os preços pesquisados são de retalho;
  * não há exemplo L2 com dados reais.

  Validado no C172S: Eastlake/preço de tabela = 0.56.

## 15. Camada de IA (MCP)

* **O que faz**:
  * servidor MCP (stdio ou HTTP) com 43 ferramentas (30 + 13 do estudo conceptual, §21), recursos e prompts;
  * registo de runs com proveniência (entradas, pressupostos e respetiva fonte, versões, git hash);
  * validação de dados externos (fonte, data, unidades, plausibilidade);
  * trabalhos assíncronos e guarda de computação.
* **Recursos**:
  * `acdt://capabilities` (este documento);
  * `acdt://methods`, `acdt://materials`, `acdt://components`, `acdt://standards`;
  * `acdt://agents-guide`, `acdt://docs/{name}`, `acdt://runs/{run_id}`.
* **Prompts**: `design_from_requirements`, `research_component`, `hifi_verification`.
* **CLI**: `acdt mcp [--http --port 8765]`.
* **Pedir à IA**: "Lê `acdt://capabilities` e diz-me como chegar de requisitos a um projeto verificado do meu
  UAV."
* **Limites**: os jobs vivem em memória (os resultados persistem no registo). Os passos pesados exigem
  aprovação do utilizador.

## 16. Relatórios

* **O que faz**:
  * relatórios Markdown + JSON por fase (`report.md`, relatório da Fase 2, `report_fase4.md`,
    `manufacturing.md`), com gráficos;
  * dossier consolidado de vários runs (`dossier.md`/`dossier.json`);
  * comparação de runs.
* **CLI / MCP**: saída de cada comando / `generate_report`, `compare_runs`, `get_run`, `list_runs`.
* **Pedir à IA**: "Gera o dossier com o dimensionamento, o MDO e o custo, e resume o que falhou."
* **Limites**: só Markdown e JSON (sem PDF/Word nativo).

## 17. Superfícies de comando e simulador de missão 6-DOF (Fase 8)

* **O que faz**:
  * dimensiona ailerons (tempo para inclinar, MIL-F-8785C IXa / CS 23.157), profundor (rotação na
    descolagem sobre o trem principal, compensação em todo o envelope de CG e flaps), leme (vento cruzado
    ≥ 0.2 V_S0, OEI em multimotores) e flaps (CL_max pedido pela perda e pela aterragem), com AVL;
  * momentos de charneira (AVL) e binário de servo nas condições da 14 CFR 23.455;
  * modelo de voo com tabelas AVL α × flap e simulação 6-DOF própria (quaterniões, RK4, contacto com o solo);
  * piloto automático clássico (fecho sucessivo de malhas) e seguimento de linhas, waypoints e órbitas;
  * missão em YAML: descolagem, subida, cruzeiro, viragem, waypoints, espera, descida e aterragem com
    flare; vento, turbulência Dryden e rajadas 1−cos;
  * saídas por segmento: combustível/energia, distâncias, n_z, α, saturação dos comandos, k_energia
    (6-DOF / quase-estacionário), qualidades de voo; gráficos PNG (histórico, trajetória 3D, rasto) e CSV;
  * verificação cruzada opcional com o JSBSim (processo separado): compensação e resposta a um doublet.
* **Métodos**: Sadraey (2012) Cap. 12; Stevens, Lewis & Johnson (2016); Beard & McLain (2012) Cap. 4, 6, 10;
  MIL-F-8785C; CS 25.341 (forma da rajada); 14 CFR 23.233 / 23.455; Raymer Eq. 12.21 (flaps).
* **Fidelidade**: L1 (AVL potencial + polares do perfil), com o JSBSim como verificação independente.
* **CLI / MCP**: `acdt controls <projeto.yaml>`, `acdt simulate <projeto.yaml> <missão.yaml>` / `size_control_surfaces`, `simulate_mission`.
  Opções do `simulate`: `--layout sized|current` (superfícies dimensionadas ou as do projeto) e `--jsbsim`.
  Missões de exemplo em `examples/simulation/`. O mesmo YAML em massa pontual (N0/N1) está na secção 23.
* **Pedir à IA**: "Dimensiona as superfícies de comando do UAV e simula a missão de patrulha com vento de
  4 m/s e turbulência ligeira. Quanto difere a energia do modelo quase-estacionário?"
* **Limites**:
  * aerodinâmica de baixa fidelidade: sem fuselagem no AVL, perda por mistura sigmoide, sem efeito de
    solo nem sopro da hélice;
  * as inércias vêm da soma de componentes (no C172, Ixx ≈ 1.9× o modelo c172p do JSBSim);
  * (corrigido na Fase 9) a hélice é agora de passo fixo limitada em rpm: subida do C172 715 fpm vs POH 730 (−2,0 %);
  * recuperação de vrille não avaliada; MIL-F-8785C é indicativa para UAV;
  * segmentos longos são extrapolados em regime estacionário depois de `extrapolate_after_s`.
* **Validação**: ver [docs/tutorial-fase8-simulador.md](docs/tutorial-fase8-simulador.md) (C172S vs POH e
  vs JSBSim; missão de endurance do UAV).

---

## 18. Hélice de passo fixo, inércias e flaps de camber como opção de projeto (Fase 9)

* **O que faz**:
  * hélice de passo fixo por BEMT, limitada a rpm máximas, no dimensionamento (η de descolagem, subida e
    cruzeiro calibradas no ciclo) e no simulador; C172S: subida 715 fpm vs POH 730 (−2,0 %);
  * inércias por Roskam Part V (Eqs. 3.7–3.9, raios de giração da Tabela B2) mais componentes;
  * flaps de camber / cruzeiro e flaperons: polares de secção com δf de −10 a +15° (XFOIL GDES/FLAP como
    processo separado, ou NeuralFoil), envelope e escalonamento δf(CL), ΔCD(CL) da asa por faixas, ΔCLmax e
    Δcm0; entram no diagrama de restrições, na missão e no MDO;
  * `acdt flap-options` / MCP `flap_options`: compara none / plain / camber / flaperon, mais as referências
    justas `plain_same_area` e `droop_flaperon` (flap simples com a mesma área), incluindo massa do sistema
    de flap, atuadores e custo (Eastlake F_CF 1.03); só seleciona camber/flaperon se o ganho sobre a melhor
    opção simples for ≥ `min_gain` (1 %); varrimento de requisitos para Pareto (`--sweep`).
* **Métodos**: Thomas (1999); Althaus & Wortmann (1981); Boermans & Waibel (ICAS-88), Boermans (2006);
  Raymer 12.21 e Tabela 12.2; Gudmundsson 2.2.2. Créditos em THIRD_PARTY.md.
* **Limitações**: sem arrasto de compensação do Δcm0 nem de folga/fuga da articulação; carga de envergadura
  da asa limpa; convergência do XFOIL a δ grandes (coordenadas FX67-K-150 falham, por isso a demo usa SD7062);
  Eastlake não é válido para UAV; em W0 o camber só ganha com dash muito alto: na demo loiter+dash o cruzamento fica entre 60 e 70 m/s e, a 70 m/s, dá −1.5 % de W0 face ao plain com a mesma área (ver tutorial, secção 4).
* **Trim / folga (opt-in, 10 nov 2026)**: `camber_flap.trim_drag: true` adiciona ΔCD de
  compensação da HT a partir de Δcm0(δ*) (Nelson / Etkin, V_H); `camber_flap.gap` com `sealed: true`+fonte
  ou `dCD`+fonte; `gap.chord_ratio` sozinho → unassessed (nunca correlação inventada). Omissão = polar de
  envolvente legada (dois pontos loiter/alta velocidade). Demo `examples/camber/trim_gap_demo.py`.
* **Tutorial**: [docs/tutorial-fase9-camber-flaps.md](docs/tutorial-fase9-camber-flaps.md).

---

## 19. Base de certificação, matriz de conformidade e avaliação de segurança ARP4761 (Fase 10)

* **O que faz**:
  * seleção da base (`core/certification/basis.py`): CS-23 Amdt 6 / Part 23 com nível (1–4) e velocidade
    (baixa/alta) pela CS 23.2005 e classe AC 23.1309-1E; CS-25; STANAG 4671 (UAV 150–20 000 kg); STANAG 4703
    (UAV < 150 kg); SORA 2.5 para UAS na categoria específica. O C172 sai em **CS-23 Nível 2, baixa velocidade**;
  * catálogo estruturado (`core/data/cert_catalogue.yaml`): por parágrafo, **paráfrase** do acdt (nunca o texto
    oficial), meios de conformidade (MoC 0–9), regras de aplicabilidade e ligação à fonte oficial;
  * matriz de conformidade (`core/certification/matrix.py`): parágrafo → MoC → evidência do acdt → estado
    automático (conforme / não conforme / requer ensaio / em aberto); exporta CSV, XLSX (extra `[cert]`) e MD,
    mais o gráfico-resumo; requisitos do cliente (descolagem, subida) aparecem só como informação;
  * avaliação de segurança de baixa fidelidade (`core/safety`, `domains/aircraft/safety_assessment.py`): FHA com
    alvos por classe (AC 23.1309-1E Fig. 2, AMC 25.1309, STANAG 4671 USAR.1309 com a alternativa "soma
    catastrófica ≤ 1e-5", STANAG 4703 Anexo G 0.0015/MTOW); FTA com cortes mínimos (MOCUS), probabilidade exata,
    importância Fussell–Vesely e exposição latente; FMEA a partir das taxas com fonte (`failure_rates.yaml`:
    NASA GARS, ATSB, Volz; os PRESSUPOSTOS estão marcados); MTBF requerido para cada alvo falhado;
  * estudo de redundância (servos duplos, FCC dupla/tripla, bateria de reserva; altímetro e atitude de reserva
    no GA): as opções só são escolhidas se um alvo falhar; Δm relativa à configuração base, ΔW0 = (dW0/dm) × Δm
    (dW0/dm do próprio dimensionamento, ≈ 1.9–2.1) e W0 final redimensionado com a massa adicionada;
  * SORA 2.5 (`core/certification/sora.py`): iGRC (Tabela 1), mitigações M1A/M1B/M1C/M2 (Tabela 5), ARC pela
    AEC (Anexo C), SAIL (Tabela 3), robustez das OSO (Tabela 14), TMPR e via de projeto (SC Light-UAS / DVR);
    passo #8 de contenção opt-in (`core/certification/containment.py`, Tabelas 8–13 e Anexo E § E.4):
    raio adjacente = 3 min × Vmax (piso 5 km, tecto 35 km), robustez exigida pelo mais estrito entre
    densidade média e ajuntamentos; conformidade só com evidência citada ou P(sair do VO) com fonte/data;
    MTOM < 250 g → contenção baixa; UA de 3 m exige `sheltering` explícito (Tabelas 9 vs 10);
  * taxas de fornecedor (`certification.safety.supplier_rates` ou `--supplier-rates`): λ ou MTBF com
    `source` e `retrieved`; entradas incompletas ficam unassessed (nunca zero silencioso). C2 (`uav_c2_link`)
    é o único caminho para fechar FC-U4;
  * `acdt certify <missão>` (pipeline completo + tudo o acima), `acdt safety uas|ga_piston` (rápido, sem
    dimensionamento) e `acdt safety sora --input …` (SORA + contenção opt-in); MCP `certify` (trabalho longo) e `safety_assessment`.
* **Exemplos** (`examples/output/certification/`):
  * C172 (CS-23 N2): 6 conforme, 14 requer ensaio, 2 não conforme, 31 em aberto; perda total de atitude
    3.1e-7/h (alvo 1e-6) cumpre; atitude primária 6.5e-4/h (alvo 1e-4) **não cumpre** (AI + bomba de vácuo da GARS:
    todas as taxas ×0.15, MTBF ×6.5); altímetro de reserva selecionado (+0.37 kg, ΔW0 +0.71 kg);
  * UAV 136 kg (STANAG 4703): 5 / 10 / 0 / 6; perda de controlo 3.8e-6/h vs acumulado 1.1e-5 cumpre com servos
    duplos + FCC dupla + bateria (Δm 0.91 kg, ΔW0 1.9 kg); SORA iGRC 5 → ARC-c → **SAIL IV**;
    exemplo de contenção (`examples/certification/sora_containment_assessed.json`, 5.37 m / 48.5 m/s,
    SAIL IV, Tabela 11): raio adjacente 8.73 km; densidade 20/km² e ajuntamentos <40k → robustez exigida **low**;
    P(sair do VO) EXAMPLE 5e-4/FH vs alvo Anexo E 1e-3/FH → conformidade ok (PRESSUPOSTO, não ensaio);
    sem densidade/ajuntamentos o requisito fica unassessed (`sora_containment_unassessed.json`);
  * UAV 153 kg (STANAG 4671): 7 / 13 / 1 / 12; perda de propulsão 9.9e-4/h vs 1e-5 (hazardous) **não cumpre**
    com um só motor de 2 tempos (taxa PRESSUPOSTO) → USAR.1309 não conforme.
* **Limitações**: estado de conformidade a nível conceptual (a autoridade decide); taxas constantes, sem modos
  comuns, bloqueio/hardover de servos nem software (DO-178C); sem taxas públicas para C2 nem bússola (C2 só
  fecha com `supplier_rates` com fonte e data; bússola continua em aberto); taxas de motor UAV, FCC, bateria e
  cablagem são PRESSUPOSTOS na ausência de taxas de fornecedor citadas; ΔCusto n/d sem preços de fornecedor;
  SORA passo #8 é opt-in (unassessed ≠ pass); mitigações estratégicas de ar (Anexo C) e crédito de abrigo
  em UA > 3 m (Anexo F) não automatizados; população/AEC por defeito são PRESSUPOSTOS; o otimizador usa
  estudo + redimensionamento, não uma variável MDO.
* **Tutorial**: [docs/tutorial-fase10-certificacao-seguranca.md](docs/tutorial-fase10-certificacao-seguranca.md).
* **Cargas no solo**: 23.2220 e USAR.471 lêem `ground_loads`; 23.2305 lê `landing_gear`. Sem trem, esses
  parágrafos ficam em aberto. Com trem, a geometria que falha fica não conforme; o curso dimensionado que
  cabe fica em "requer ensaio", porque o meio de conformidade inclui ensaio. O detalhe está na §20.

---

## 20. Peso e centragem operacional e trem de aterragem

* **O que faz**: no fim da estabilidade de `acdt size`, constrói o diagrama de carregamento (vazio, tripulação,
  carga, combustível e itens extra) e compara-o com os limites dianteiro e traseiro. Em seguida posiciona o
  trem face a esse intervalo de CG, verifica tombo, capotagem, fração estática no nariz e folga de rotação, e
  dimensiona o curso do amortecedor para a aterragem limite. O relatório ganha a secção **12a** e a figura
  `wb_loading.png`. As verificações `wb:` e `gear:` são reportadas e **não** mudam a viabilidade da Fase 1.
* **Métodos**: Raymer 2018 Sec. 15.1 e Cap. 11; Roskam Parte II 1985 Cap. 10; Currey 1988 §5.3 (o termo de
  sustentação do curso divide-se por η); limite dianteiro = o mais à ré do caso limpo e do flare com flaps
  (Nelson 1998 Cap. 2; Cm0 da asa pela Eq. 16.13 de Raymer; Cm0 da fuselagem por Multhopp, com k₂−k₁ de
  Lamb, NACA Report 139). Flap simples e split: Glauert. Flap slotted: centro de pressão a 44 % da
  corda estendida (USAF DATCOM 1978, Sec. 6.1.2.1). No flare, o CLα da cauda leva o φ de Torenbeek
  (1982), citado por Phillips e Hunsaker (Journal of Aircraft, 2013, Eq. 4); o CLmax e o dε/dα do
  ponto neutro não mudam. Limite traseiro = ponto neutro menos a margem
  estática alvo (Raymer Cap. 16). Velocidade de descida, sustentação da asa até 2/3 e pisos de fator de
  carga de 14 CFR 23.473 na eCFR de 25 de julho de 2017. Eficiência do óleo-pneumático 0,80 e do pneu 0,47
  (Raymer Cap. 11).
* **Fidelidade**: L0–L1. Não entra no ciclo interno do MDO.
* **CLI / MCP**: dentro de `acdt size` / `size`. Não há comando nem ferramenta MCP novos (continuam 30).
* **Pedir à IA**: "Mostra o diagrama de carregamento e diz se o trem de triciclo cabe no CG, com o curso para
  a aterragem limite."
* **Limites**:
  * as estações de estrutura continuam a ser os pressupostos de Roskam (Parte V, Tabela 8.1), salvo
    `stability.stations`. Tripulação, carga e bateria, por omissão, ficam no CG da massa fixa
    (Raymer 2018 Sec. 15.1, referência `balance`): é a estação que não alarga o diagrama. O
    combustível de asa fica a 30 % da CMA. `weight_balance.loading` (com `arm_in` atrás da firewall) ou
    `extra_items` substituem a carga útil; o CG de cada depósito é fixo e o combustível inutilizável
    não é separado;
  * os limites por omissão são aerodinâmicos, não um envelope certificado; o utilizador pode dar
    `x_forward_m` / `x_aft_m` ou uma poligonal `forward_limit` / `aft_limit`;
  * `landing_weight_fraction` 0,95 é o piso permitido por 23.473(b), não a prova da cláusula de combustível;
  * o entre-eixos fica na banda 8–15 % de Raymer e dentro da fuselagem; sem solução, `gear:position` falha
    e o nariz não é escrito à frente do datum;
  * não há spin-up, spring-back, carga lateral, travões nem rolagem; a fração estática não é a distribuição
    de aterragem nivelada;
  * `landing_gear: none` não gera verificações de trem e deixa 23.2220, 23.2305 e USAR.471 em aberto;
  * h_cg, se não for dado, é o comprimento do trem principal mais metade do diâmetro da fuselagem (o mesmo
    pressuposto do simulador). Sem `main_gear_length_m`, esse comprimento é 0,60 m (PRESSUPOSTO). Sem
    `x_tail_m`, a roda de cauda fica a 0,95·L (PRESSUPOSTO). A face de MTOW aceita até 0,05 kg acima de
    m_max (PRESSUPOSTO de fecho numérico).
* **Tutorial**: [docs/tutorial-wb-trem.md](docs/tutorial-wb-trem.md).

---

## 21. Estudo conceptual conduzido pela IA (missão → requisitos → arquitetura de frota)

* **O que faz**: o utilizador descreve um problema em linguagem livre, por exemplo "vigiar esta área de mar por
  causa de pesca ilegal". O agente de IA define a missão, deriva requisitos mensuráveis, gera arquiteturas (1
  grande, N pequenas, mistas, criativas, incluindo as não dimensionáveis) e avalia-as com primitivas
  determinísticas. Depois compara pela frente de Pareto e recomenda. Não há esquema fixo de entradas nem
  heurísticas que escolham a arquitetura: o raciocínio é da IA e fica registado (`study.json` + `report.md`,
  repetível com `acdt concept replay`).
* **Métodos**:
  * distâncias e áreas: Sinnott 1984; Chamberlain & Duquette 2007 (JPL 07-03);
  * pesquisa e POD: Koopman 1946/1980; Washburn 2002;
  * **busca de barreira** (opt-in, 9 nov 2026): patrulha em linha/corredor que o evasor tem de cruzar —
    factor z = n·W·V/(L·u), POD aleatória / cookie-cutter, revisitação τ = 2L/(n·V), fecho quando τ ≤ T;
    manobra contínua opcional via Ha 2010 (`barrier_search` / `acdt concept barrier`);
  * cobertura contínua: Ha 2010 (AFIT-OR-MS-ENS-10-03);
  * disponibilidade: Blanchard & Fabrycky 2011; MIL-HDBK-338B;
  * k-de-N: O'Connor & Kleyner 2012;
  * horizonte radar: Skolnik 2001;
  * critérios de Johnson (1958);
  * Pareto: Deb 2001; pesos normalizados: Marler & Arora 2004;
  * frota: o pipeline `size` + `cost_estimate` + `safety_assessment` + base de certificação.
* **Fidelidade**: L0 (conceptual). Uma frota de 1 dá o mesmo que `acdt size` **quando `level` é omitido**
  (mesma `aero.fidelity` do YAML). `level=L0|L1` força handbook/lowfi e pode diferir do `acdt size` nu —
  a diferença fica em `mtow_alignment` (corrigido 9 nov 2026; antes o default L0 gerava um Δ MTOW silencioso).
* **CLI / MCP**: `acdt concept` (incl. barrier subcommand) / `concept_study_start`, `concept_study_add`, `concept_study_report`, `geo_measure`, `transit_time`, `sweep_coverage`, `persistent_coverage`, `barrier_search`, `fleet_reliability`, `radar_horizon`, `sensor_footprint`, `johnson_range`, `size_fleet`, `compare_alternatives`.
* **Prompt MCP**: `concept_trade` (o fluxo de raciocínio do agente, `src/acdt/ai/prompts/concept_trade.md`).
* **Pedir à IA**: "Quero vigiar esta área de mar porque há barcos estrangeiros a fazer pesca ilegal — que
  sistema devo ter?"
* **Limites**:
  * só asa fixa (VTOL L0 existe à parte em `acdt vtol`, §29; aeróstatos, navios e satélites ficam como alternativas não avaliáveis);
  * a largura de varrimento é a do datasheet para a classe de alvo, sem desordem do mar nem falsos alarmes;
    se W falta, a POD da barreira fica **unassessed** (nunca inventar o W do Gabbiano);
  * barreira: revisitação reciprocante sem tempo de viragem; POD é oportunidade Koopman, não Pd do fabricante;
  * sem meteorologia nem espaço aéreo; disponibilidade independente;
  * custo de aquisição pelo CER L0 (baixa confiança para UAV); custo de operação só com taxas pesquisadas;
  * perda por surtida pelo template ARP4761 low-fi (taxas genéricas).
* **Tutorial**: [docs/tutorial-concept-trade.md](docs/tutorial-concept-trade.md); guia
  [docs/ai-concept-trade.md](docs/ai-concept-trade.md).

## 22. Geometria por componentes e requisitos de integração (P1 do workflow por níveis)

* **O que faz**: monta **qualquer** configuração a partir de três peças genéricas, sem enumeração fechada de
  configurações: corpos (fuselagem, pod, viga, nacele, radome, carenagem, perna de trem) com secções
  super-elípticas ao longo de x (opt-in `chine: {angle_deg, crown_frac?}` → secção hexagonal com chines
  longitudinais para a malha PO); superfícies sustentadoras (asa, cauda, canard, deriva, winglet, painéis de
  box wing ou joined wing) com secções de bordo de ataque, corda, torção e t/c, com qualquer diedro (V, V
  invertido, vertical); e discos (hélice ou rotor). Cada peça tem posição, orientação, espelho em y = 0 e
  bandas a que é transparente (radome transparente a `rf`). Sobre a montagem verifica os requisitos de
  integração do equipamento, escritos como restrições e não como posições fixas:
  * encaixe dentro do corpo hospedeiro, com a folga em metros;
  * sobreposições, separação mínima e distância máxima (cabo, guia de onda);
  * zonas de exclusão (disco da hélice, caixa, esfera ou componente);
  * campos de visão por az/el ou por cone, e vista do céu para SATCOM ou GNSS, com oclusão pela própria
    aeronave (asa, vigas, cauda, hélice, radome opaco na banda ótica, torretas externas);
  * janela de CG e fração de enchimento do volume.
  Devolve a margem de cada restrição e as violações (com quem bloqueia e em que sector), a massa, o CG e a
  inércia, a potência média e de pico e o calor. O equipamento sem posição é colocado por uma pesquisa
  determinística em grelha dentro do hospedeiro (`prefer` x/y/z).
* **Métodos**: espessura NACA 4 dígitos (Abbott & von Doenhoff 1959, Eq. 6.2); área da secção de Lamé
  w·h·Γ(1+1/n)²/Γ(1+2/n); volume pelo teorema da divergência; lançamento de raios Möller & Trumbore (1997);
  amostragem do cone em rede de Fibonacci (González 2010); inércia de caixas com Steiner.
* **Adaptadores**: malha PO para o RCS (`to_rcs_mesh` / `rcs_bridge.build_rcs_mesh` com inventário e itens
  box|sphere|cylinder), STL (lido pelo modo STL do `rcs` e por visualizadores CAD) e ficheiro AVL das
  superfícies (`avl_text`; com corpos em `assembly.sizing.avl_geometry`).
* **Fidelidade**: N1 / baixa fidelidade. Equipamento como caixa alinhada com os eixos; campo de visão amostrado
  por raios discretos (passo por omissão de 5°); sem multipercurso, perdas do radome nem diagrama de antena;
  sem análise térmica nem de EMI além das distâncias. Os PRESSUPOSTOS vêm no resultado.
* **CLI / MCP**: `acdt integration` / `assembly_geometry`, `integration_check`.
* **Montagem como aeronave (P1b)**: `assembly.sizing.analyse` avalia qualquer montagem desenhada:
  * massas estruturais por peça e por papel: asa Raymer Eq. 15.46; cauda horizontal e canard 15.47; deriva e
    winglet 15.48; cauda em V ou V invertido dividida em S·cos²Γ (15.47) e S·sin²Γ (15.48), áreas projetadas
    de Purser & Campbell (NACA Rep. 823); cada corpo (fuselagem, pod, viga, radome) pela 15.49 com a sua área
    molhada exposta; fatores de compósito da Tabela 15.4;
  * CD0 por áreas molhadas expostas (Raymer Eq. 12.24, FF 12.30 a 12.32) com os termos que faltavam
    (`assembly/drag.py`): Q por junção lido da geometria (Raymer Sec. 12.5.5: nacele, loja, viga ou radome
    montado diretamente 1,5, a menos de um diâmetro 1,3, além 1,0; asa baixa sem carenagem 1,1–1,4; cauda em
    V 1,03, convencional 1,04–1,05), upsweep do cone de cauda (Eq. 12.36, `pod.upsweep_deg` ou estações com
    `zc`), arrasto de base subsónico (Eq. 12.37; base carenada por uma hélice propulsora fica a zero,
    PRESSUPOSTO), protuberâncias (torreta, cúpula, antena) com C_D de Hoerner 1965 Ch. III (esfera 0,47,
    cilindro 1,2) ou D/q com fonte, e L&P de 5 % nominal e 10 % pessimista (Raymer Sec. 12.5.10, aviões a
    hélice 5–10 %);
  * **banda de incerteza do CD0**: incerteza relativa por termo (`drag.uncertainty`, PRESSUPOSTO: superfícies
    5 %, corpos 10 %, upsweep 30 %, base 20 %, protuberâncias 30 %), Q no extremo da banda de Raymer e L&P a
    10 % dão `CD0_pessimistic` (soma linear, pior caso) e `CD0_rss`, além do `CD0_nominal`;
  * **calibração para N2**: `drag.calibration {componente | "*": fator}` (por omissão 1,0) multiplica o D/q do
    componente, para receber correções de CFD ou ensaio; os fatores usados vêm no resultado. A corrida SU2 da
    combinação 7 do NACA TR 540 (HANDOFF §4b G3, 4 nov 2026) não produziu fator: não há malha com y+ ≈ 1. A
    omissão mantém-se 1,0;
  * ponto neutro do AVL da montagem com corpos (BODY/BFILE, corpo redondo de área igual) e sem corpos, mais o
    desvio da fuselagem de Torenbeek (App. E). A margem usa por omissão o AVL sem corpos com o desvio de
    Torenbeek: no adaptador do C172 o BODY do AVL avança o ponto neutro 17,7 % da CMA, cerca de 4 vezes o
    valor do manual, e o manual do AVL avisa que o modelo de corpos tem validação limitada. O valor com BODY
    vem sempre no resultado (`options.np_source` para o escolher), com nota quando os dois diferem mais de
    5 % da CMA;
  * CG a partir das peças, do equipamento colocado (com `group` payload/fuel/equipment/propulsion) e das
    massas dadas, nos casos vazio, carga, combustível e cheio;
  * trem triciclo posicionado sobre a geometria com o módulo `landing_gear`: tip-back, rotação até ao primeiro
    vértice da malha a tocar (no bivigas propulsor é a ponta da lança, não o disco), folga da hélice de 7 in
    (14 CFR 23.925(a)(1)), ventre, banda de carga no nariz de 8 a 15 % e capotamento;
  * cheques `asm:*` do tipo layout: são reportados e não mudam a viabilidade.
  * **No `size`, dentro do ciclo de W0** (`assumptions.assembly: {file: montagem.json}` relativo ao yaml, ou
    inline): em cada iteração a montagem é reescalada para a área de asa dimensionada por semelhança
    geométrica (k = √(S/S_desenho) em todos os comprimentos, posições de itens e restrições de posição;
    caixas de equipamento, distâncias de cabo e `mass_kg` dados não escalam, PRESSUPOSTO); as massas
    estruturais por peça substituem asa, caudas e fuselagem do tipo fixo e o CD0 da montagem (nominal, ou
    pessimista com `options.close_on: pessimistic`) substitui o da polar, que é a usada no desempenho e na
    verificação da missão. AR, afilamento, flecha e t/c da asa do tipo fixo passam a ser os da asa da montagem.
    `res.assembly_loop` traz k, S, CD0 da banda, massas por peça, iterações e a montagem escalada; o cheque
    `asm:closes_pessimistic_cd0` redimensiona com o CD0 pessimista e diz se o projeto ainda fecha (com W0).
    Quem chama o `size` (`run`: opções de projeto, certificação, integração de sistemas) herda a montagem e o
    `close_on`.
  * **Reescala `surfaces`** (`options.scaling: "surfaces"`, `options.AR` opcional): corpos, discos, itens, trem e
    restrições ficam como desenhados (fuselagem pela carga, Raymer Sec. 7.2/9.1); a asa principal escala em
    envergadura k_b e corda k_c com k_b·k_c = S/S₀ e k_b/k_c = AR/AR₀; cada cauda/canard escala para manter o
    coeficiente de volume do desenho (Raymer Eqs. 6.28 e 6.29; V em S·cos²Γ / S·sin²Γ, Purser & Campbell), com
    o braço recalculado por ponto fixo. Itens e discos montados na asa não a acompanham (PRESSUPOSTO).
  * **K da polar pelo AVL** (`options.K_source: "avl"`, por omissão): K = 1/(π·AR·e_inv·s) + 0,38·CD0 (Kroo
    2001), e_inv do AVL sem corpos da montagem escalada, s = 1 − 2(d_f/b)²; sem AVL (ou `"oswald"`) fica o
    Oswald de Raymer, com nota. `res.assembly_loop["K"]` traz e_inv, s, e e o K clássico.
  * **Balanceamento** (`options.balance: {static_margin: 0.10, move: [...], tol, gear_masses}`, desligado por
    omissão): depois do ciclo, desloca em x as peças de `move` (por omissão a asa) até a margem estática mínima
    nos casos de carga igualar o alvo (Raymer Sec. 16.3; x_np pela fonte por omissão, AVL sem corpos +
    Torenbeek), recoloca o trem pelo CG e põe as massas das duas pernas nas rodas. Se o nariz não tem estação
    (banda de Raymer vazia), nenhuma massa de trem é movida — o principal não fica sozinho no raio de tombo.
    O MDA é refeito com a montagem balanceada (≤ 3 passagens externas) e a asa é colocada outra vez sobre as
    massas desse último fecho, para o cheque publicado não ficar abaixo do alvo. A secante, se parar aquém do
    alvo, dá mais um passo. Resultado em `res.assembly_loop["balance"]`.
    O combustível de missão que excede a massa desenhada dos tanques fica no CG desses tanques (Raymer: o
    combustível vai nos tanques); sem tanque desenhado, no centróide do corpo.
  * **Protuberâncias automáticas** (`drag.auto_protuberances`, ligado por omissão): cada item posicionado que
    sai das peças (amostragem 7×7×7 da caixa contra o interior das peças) soma C_D·A_frontal·fração exposta,
    com `protuberance_shape` box 1,05 / sphere 0,47 / cylinder 1,2 (Hoerner 1965 Ch. III); `protuberance:
    false` exclui o item; protuberâncias manuais com o mesmo nome têm prioridade.
  * **MDO** (`mdo.py`): o AircraftMDO usa a montagem — CD0 e massas por peça reescalados a cada (S, AR), K
    Oswald calibrado (β) ao K da base (sem AVL por avaliação); `assumptions.mdo.assembly_close_on:
    pessimistic` aplica-se depois do β (o β não anula a troca); com escala uniforme o AR sai das variáveis de
    projeto (é o do desenho); em `surfaces` o `verification_spec` passa o AR ótimo a `options.AR`. A corrida
    uniforme de `examples/heavy/uav150_flying_wing.yaml` (HANDOFF §4b G5) fechou o dimensionamento, manteve as
    mesmas falhas e baixou W0 de 133,026 kg para 121,661 kg. O ramo `fix-balance-examples` não repete esse MDO:
    reequilibra os dois exemplos para os cheques `hq:CAP`, `hq:dutch_roll`, `gear:position`, `gear:tipback` e
    `asm:static_margin` passarem num `size` (HANDOFF, a seguir a G5), ainda com `hq:*` e `gear:*` do tipo fixo.
  * **Qualidades de voo e trem da montagem** (`assembly/handling.py`): com `assumptions.assembly`, as linhas
    `hq:*` (menos `hq:scissor`) e `gear:position|tipback|nose_load|overturn|rotation` saem da montagem, com a
    mensagem «montagem: …» e os mesmos limites (MIL-F-8785C; Raymer Cap. 11). Derivadas laterais e C_mq do AVL
    da montagem sobre o CG ao CL de cruzeiro; C_nβ dos corpos por Raymer Eq. 16.47; C_mα̇ das caudas atrás do
    CG (Etkin e Reid), 0 sem cauda; inércias por componentes (Roskam Parte V Cap. 10); as matrizes de Nelson do
    tipo fixo. Trem: o triciclo colocado na montagem. PRESSUPOSTOS: caso «cheio» (`options.hq_case`), I_xz
    desprezado, massa escalada a W0. `options.checks_from: fixed_type` volta ao tipo fixo; com a montagem sem
    trem (`gear: none`) os `gear:*` ficam do tipo fixo, com nota. Resultados por exemplo no HANDOFF §4b.
  * **Exportações**: `acdt integration montagem.json --step` (STEP facetado, uma peça por componente, CadQuery
    num processo à parte) e `--rcs` (malha PEC sem hélices + STL para `acdt rcs stl`, e verificação PO a 10 GHz
    em 3 azimutes); `acdt size` escreve `assembly_scaled.json` (a montagem dimensionada) quando há montagem.
    A polar pesada do bivigas (HANDOFF §4b G4) está em
    `examples/output/heavy_g1_g5/rcs/polar_summary.json`: esfera completa em `fine=1` a 3, 10 e 15 GHz; em
    `fine=2` só uma amostra de azimutes. A simetria de ±0,5 dB em todos os pares ±az não se cumpre, e o nariz
    a `fine=2` só baixa a 3 GHz.
  * **Validação do BODY do AVL** (`assembly/validation.py`, `acdt integration … --np-validation`): x̄_np com e
    sem corpos, com Torenbeek e com o limite de Munk (NACA Rep. 184, 1924: ΔCm_α ≤ 2·Vol/(S·c)); compara com
    uma referência publicada só quando o caso a traz com fonte (`validation.reference`). Nos dois exemplos o
    desvio do AVL com corpos excede o limite de Munk (bivigas −25 % vs −14 % da CMA; asa voadora −5,2 % vs
    −1,4 %). Quatro combinações do NACA TR 540 estão em `examples/validation/avl_bodies/`: o AVL com corpos
    fica dentro do limite de Munk, mas só a combinação 13 (asa atrás) tem |erro| < 3 % da CMA e menor que
    Torenbeek. A fonte por omissão continua `avl_torenbeek` (HANDOFF §4b G2).
    `options.in_loop: false` volta ao modo antigo (avaliação depois do dimensionamento, sem reescalar, com
    `asm:wing_area` a avisar). `res.assembly["comparison"]` compara S, massa estrutural e CD0 com os tipos
    fixos.
  * **Tipos fixos**: `assembly_from_design(res)` converte a Configuration (asa, fuselagem, cauda horizontal e
    deriva) numa montagem, com as massas nas estações da estabilidade. No C172 reproduz S, a janela de CG
    (±4 % da CMA) e o ponto neutro do AVL sem fuselagem (±3 % da CMA).
  * **CLI / MCP**: `acdt integration montagem.json --size` (usa o `flight` do JSON) / `assembly_sizing`.
* **Pedir à IA**: "O radar precisa de 360° em azimute e de olhar para baixo, o gimbal para a frente e para baixo,
  e o SATCOM de céu livre acima de 10°. Cabem no bivigas propulsor e ninguém tapa ninguém?"
* **Limites**:
  * o balanceamento só desloca peças em x (não redimensiona caudas pela estabilidade); o K pelo AVL não
    inclui corpos (o s de Kroo é a correção da fuselagem); a validação do BODY do AVL contra o NACA TR 540 não
    justifica mudar a fonte por omissão (HANDOFF §4b G2);
  * ~~trem só triciclo~~ — taildragger / ski / pernas desenhadas / recolha geométrica L0 opt-in (§32e, 9 nov 2026);
    corpos com rotação: BODY AVL / Torenbeek App. E → **unassessed** (nunca stand-in alinhado; §32f);
    não há equação de massa para lanças nem canards em Raymer GA (usa-se 15.49 e 15.47, PRESSUPOSTO);
  * o STEP da montagem é facetado (sem superfícies ajustadas); o CAD paramétrico da estrutura interna ainda
    não lê a montagem;
  * a colocação automática é uma procura de viabilidade, não uma otimização (a otimização fica para a P6);
  * o trem de aterragem modela-se como corpos; cinemática L0 = envelope de arco do centro da roda (§32e), sem dinâmica de mecanismo.
* **Exemplos**: [examples/integration/twin_boom_pusher.json](examples/integration/twin_boom_pusher.json)
  (`options.balance` a 12 % de margem; combustível e carga junto do CG de vazio para a banda de 8–15 % do
  nariz) e [examples/integration/flying_wing_pusher.json](examples/integration/flying_wing_pusher.json) com a
  missão [examples/heavy/uav150_flying_wing.yaml](examples/heavy/uav150_flying_wing.yaml) (pusher a 72 % L,
  c_vt 0,10 e braço 0,80 L no tipo fixo, balanceamento a 10 %). Os winglets desenhados têm c_V ≈ 0,028
  (Raymer Eq. 6.29); o cheque `hq:dutch_roll` lê-os e falha (ζ_d −0,026, Nível >3; com o c_vt 0,10 do tipo
  fixo, guardado em `res.dynamics['fixed_type']`, passava). Opt-in (9 nov 2026, §32d):
  `examples/heavy/uav150_flying_wing_closed.yaml` + `flying_wing_pusher_closed.json` dimensiona os
  winglets a `c_vt` Raymer 6.29 e coloca o triciclo (Raymer Ch. 11 / 14 CFR 23.925); baseline sem a
  flag inalterado. O bivigas passa `gear:position` e `gear:tipback` com o trem colocado na montagem.

---

## 23. Simulador de missão em massa pontual (P3, N0/N1)

* **O que faz**:
  * corre o mesmo YAML da secção 17 em equilíbrio quase-estacionário (norte, este, altitude). A velocidade
    e o ângulo de trajetória são o equilíbrio de Anderson 1999 Cap. 5 e de Raymer 2018 Cap. 17; a posição
    é um Euler explícito. A aceleração ao longo da trajetória não é integrada (PRESSUPOSTO: a velocidade
    do segmento é imediata);
  * N0: polar, propulsão e massa vêm do bloco `aircraft`. Os DEFAULT_ASSUMPTIONS de dimensionamento não
    entram. N1: vêm do resultado de `size`, sem construir o modelo de voo AVL. A comparação com o 6-DOF
    usa a polar e a tração do modelo de voo;
  * segmentos: descolagem (distância de Raymer 17.8; o tempo da corrida é a integração de V̇ = g(K_T − K_A V²)),
    subida, cruzeiro, viragem coordenada, waypoints, espera e patrulha, descida e planeio (tan γ = 1/(L/D)),
    aterragem (Raymer 17.9). Vento constante pelo triângulo de velocidades (Anderson Cap. 3). A turbulência
    Dryden e as rajadas 1−cos ficam no 6-DOF e são ignoradas aqui, com nota;
  * sensor ao longo do rasto, com as primitivas já existentes: pegada, faixa varrida, horizonte, alcance
    de Johnson, POD e ciclo de presença. Saídas: tempo em estação, área varrida e POD;
  * falhas determinísticas num instante ou numa condição (motor, sensor, ligação, degradação de combustível
    ou de bateria). A massa pontual voa a resposta (continua, regresso à base, desvio). Um catalogue com
    seed faz um único sorteio reproduzível. Não há Monte Carlo. No 6-DOF a mesma falha é registada e a
    trajetória não muda.
* **Métodos**: Anderson, *Aircraft Performance and Design* (1999), Cap. 3 e 5; Raymer (2018) Cap. 17
  (17.8 e 17.9). Pegada, horizonte, Johnson, POD e ciclo: as primitivas de `acdt.core.concept.search` e
  `acdt.core.concept.ops` (Koopman 1946, Johnson 1958, Skolnik 2001, Ha 2010).
* **Fidelidade**: N0 (polar dada no bloco) e N1 (polar e consumo do dimensionamento). O 6-DOF continua
  a ser a omissão.
* **CLI / MCP**: `acdt simulate <missão.yaml> --fidelity pointmass` e `acdt simulate <projeto.yaml> <missão.yaml> --fidelity pointmass` / `simulate_mission`.
  O `dt` do YAML é o passo do 6-DOF. `pointmass_dt` é o passo da massa pontual (omissão 1 s).
  Exemplo N0: `examples/simulation/n0_patrol.yaml` (números PRESSUPOSTO, não uma aeronave real).
  Tutorial: `docs/tutorial-p3-massa-pontual.md`.
* **Pedir à IA**: "Sem desenhar o avião, simula esta patrulha em massa pontual com a polar estimada e diz
  o tempo em estação e a área varrida. Depois repete com o avião dimensionado."
* **Limites**:
  * equilíbrio quase-estacionário, terra plana, sem terreno, só vento constante, polar parabólica;
  * a deteção é oportunidade de busca (esforço W·L, passagens repetidas contam outra vez), não a curva
    de POD do fabricante nem clutter;
  * a resposta de falha não é voada no 6-DOF; não há Monte Carlo;
  * custo por hora de voo, geografia real, busca de barreira e a chamada automática de
    `compare_alternatives` não entram nesta corrida. O resumo traz tempo em estação, autonomia, alcance,
    área e POD para o agente os passar.
* **Consistência**: num cruzeiro de 0,4 min do C172 a 50 m/s e 600 m, alcance, autonomia, alcance
  específico e autonomia específica das duas fidelidades ficam dentro de 15 % (a banda já usada para o
  k_energia). Os números medidos estão no HANDOFF, P3.

---


## 24. Matriz morfológica N1 e poda por conjuntos (P2)

* **Módulos**: `domains/aircraft/morphology/` (`matrix`, `generate`, `evaluate`, `prune`).
* **P4 energy/comms (10 nov 2026)**: eixos abertos `energy` (fuel/battery/hybrid_series/parallel/…) e
  `avionics_link` (datalink_LOS/relay, SATCOM_L/Ku, …); opções como dict com `source`/`retrieved`/
  `power_W`; `morph evaluate --systems` liga `hybrid_templates` + `link_catalog`; em falta →
  `unassessed_axes` (nunca 0 W/kg silencioso); poda mantém unassessed vivos (set-based).
* **P4 ops-cost (10 nov 2026)**: `operating_cost` / `operating` no `--systems` anexa DOC
  (Raymer 2018 Cap. 18; `unit_price` via Eastlake/DAPCA CER ou `unit_price_from=size`);
  `metrics.cost_per_fh` só com `status=ok`; termo em falta → unassessed (nunca zero silencioso);
  poda usa `cost_per_fh` se presente (Pareto/set-based, sem vencedor ponderado).
* **Métodos**: Zwicky 1969 (matriz aberta); cortes por incompatibilidade física com motivo; avaliador L0/L1
  via `size` + juiz de massa pontual (Anderson 1999 Cap. 5, Raymer 2018 Cap. 17); poda set-based
  (Sobek, Ward & Liker 1999) com banda N1 PRESSUPOSTO ±15 % e Pareto (Deb 2001).
* **CLI**: `acdt morph matrix|generate|evaluate|prune`.
* **MCP**: `morph_matrix`, `morph_generate`, `morph_evaluate`, `morph_prune`.
* **Exemplo / tutorial**: `examples/morphology/n1_uav_isr_matrix.json`, `docs/tutorial-p2-morfologico.md`.
* **Limite atual**: asas/caudas/fuselagens ainda sem mapa geométrico no `size` (HANDOFF P1); ficam no
  registo da arquitetura. O juiz de missão usa a polar do dimensionamento da missão base.


## 25. Arquitetura elétrica e trade de carga útil (P4)

* **O que faz**:
  * orçamento de potência com geração + baterias de aviónica + cargas por barramento (média, pico,
    margem N1);
  * trade Pareto de carga útil (massa, potência, volume, FOV) a partir de catálogo;
  * custo por hora de voo como soma directa (preços do utilizador) — `cost-fh`;
  * **DOC operacional Eastlake/CER** (10 nov 2026): elementos Raymer 2018 Cap. 18 com
    `unit_price` de Eastlake (Gudmundsson 2014 Cap. 2) / DAPCA IV ou preço explícito;
    hook opt-in no `morph evaluate` (`operating_cost` no JSON `--systems`).
* **Métodos**: MIL-E-7016F; Moir & Seabridge, *Aircraft Systems*, 3rd ed., Ch. 5; Deb 2001 (Pareto);
  Raymer 2018 Cap. 18 (DOC); Gudmundsson 2014 Cap. 2 (Eastlake unit CER → aquisição).
* **Fidelidade**: L0–L1.
* **CLI / MCP**: `acdt systems-p4 {catalog|electrical|payload-trade|cost-fh|ops-cost}` /
  `electrical_catalog`, `electrical_analyse`, `payload_catalog`, `payload_trade`,
  `cost_per_flight_hour`, `operational_cost`.
* **Pedir à IA**: "Compara radars do catálogo (ou datasheets que pesquisaste) em massa e potência, e
  verifica se o PMA de 400 W cobre a arquitectura com EO/IR e AIS."
* **Limites**:
  * o YAML embutido é EXAMPLE DATA;
  * margens 1,25 / 1,20 são PRESSUPOSTO N1;
  * ~~fecho automático no `size`~~ — **FEITO 10 nov 2026**: bloco `onboard` na missão → hotel + massa
    acoplados dentro de `acdt size` / `jet_size` / `size_vtol` via `onboard_bridge` (ver §32);
    `DesignResult.onboard_bridge` no JSON/summary. Sem bloco → legado. `onboard_size` / `systems-p4`
    continuam para ecrãs CG/FOV/closure e trades Pareto — não substituem o fecho de massa/energia;
  * ~~alternativas morfológicas energia/híbrido/datalink/SATCOM~~ — feitas no morph N1 (ver §24);
  * ~~Eastlake/CER de custo operacional no passo morfológico~~ — **FEITO L0 opt-in 10 nov 2026**
    (`p4-eastlake-ops-cost`): `systems-p4 ops-cost` / `operational_cost`; morph `--systems`
    com `operating_cost`; `status` ok|partial|unassessed; `per_flight_hour` só se ok;
    `cost-fh` de agregação directa mantém-se; L2 BOM com cotações reais continua bloqueado
    (HANDOFF MÉDIA §5).


## 26. Registo de decisões (P5)

* **O que faz**:
  * grava decisões com porquê, fidelidade, alternativas rejeitadas e condições de invalidação;
  * avalia condições face a métricas novas e reabre decisões (set-based);
  * escreve `decisions.json` + `decisions.md`;
  * **gate de fim de nível opt-in** (`decisions gate` / `decisions_gate`, 10 nov 2026): avalia
    decisões do nível (N0/N1/…) + checks pendentes → `pass` | `fail` | `unassessed`; com
    `reopen` lista alternativas rejeitadas a reavaliar (sem escolher vencedor).
* **Métodos**: INCOSE SE Handbook 4th ed. (decision record); Sobek/Ward/Liker 1999; DESIGN_WORKFLOW §6–7.
* **Fidelidade**: transversal (N0–N3).
* **CLI / MCP**: `acdt decisions {open|add|check|gate|list|report}` /
  `decisions_open`, `decisions_add`, `decisions_check`, `decisions_gate`, `decisions_list`,
  `decisions_report`.
* **Pedir à IA**: "Regista a escolha twin-boom em N1 com as rejeitadas e a condição 'radar > 25 kg';
  depois corre o gate N1 com as métricas e checks actuais."
* **Limites**:
  * não decide nem re-corre o avaliador — o gate só classifica e, com reopen, assinala o que
    reavaliar; o agente volta a `morph_evaluate` / `size` / `compare_alternatives`;
  * condições só numéricas e planas;
  * checks têm de ser fornecidos pelo chamador (`ok: null` → unassessed, nunca pass);
  * acoplamento UQ opt-in (10 nov 2026): `--uq` / `require_uq` consome resumos MC/Sobol;
    UQ em falta ou `unassessed` ≠ pass; sem vencedor ponderado.


## 27. Sensibilidade OAT / Sobol e fidelidade por necessidade (P7)

* **O que faz**:
  * elasticidades locais ε=(Δy/y)/(Δx/x) por OAT (amostras ou `size` handbook);
  * ranking e dicas de onde subir a fidelidade (|ε| ≥ limiar);
  * banda de incerteza ±pct em parâmetros de modelo (helper);
  * **Sobol' global opt-in (10 nov 2026)**: índices de primeira ordem (S1) e efeito total (ST) via
    matrizes Saltelli A/B/A_B^(i) e estimadores Jansen; amostra fornecida ou gerada no mesmo
    avaliador handbook/`no_systems` do OAT; bootstrap percentil opcional (senão point estimates).
  * **Monte Carlo / LHS UQ opt-in (10 nov 2026)**: propaga distribuições de entrada (uniform /
    triangular / normal) por LHS (McKay 1979; Helton & Davis 2003) ou MC i.i.d.; reporta mean/std/
    percentis; avaliações falhadas excluídas (nunca incerteza zero silenciosa).
  * **Gate + UQ**: `decisions gate --uq/--require-uq` funde `gate_metrics` e `interval_checks`.
* **Métodos**: Saltelli et al. 2008 (OAT + Saltelli design); Jansen 1999 / Saltelli 2010 (S1/ST);
  McKay et al. 1979 / Helton & Davis 2003 (LHS); Efron & Tibshirani 1993 (bootstrap Sobol);
  DESIGN_WORKFLOW §5 / §7.
* **Fidelidade**: transversal.
* **CLI / MCP**: `acdt sensitivity {from-samples|pipeline|sobol|mc}` /
  `sensitivity_from_samples`, `sensitivity_pipeline`, `sensitivity_sobol`, `sensitivity_mc`.
* **Pedir à IA**: "Corre OAT/Sobol/MC em AR e Wh/kg e usa o p95 no gate N1 com --require-uq."
* **Limites**:
  * OAT / Sobol / gate-sem-UQ inalterados quando as opções novas são omitidas;
  * Sobol/MC: evidência em falta → `unassessed` (nunca 0 silencioso);
  * `pipeline`/`sobol`/`mc` por omissão handbook + sem systems; N pequeno = smoke;
  * dicas de disciplina são heurísticas por caminho.


## 28. Forma OML N2 leve — aero/RCS/packaging (P6 light)

* **O que faz**:
  * DOE LHS sobre Shape alargado (sweep, chine, cant, wing z, L/D scales, sensor station);
  * métricas aero (perf_ratio) + RCS PO + score de packaging (volume/FOV heurístico);
  * frente de Pareto tri-objectivo.
* **Métodos**: estudo RCS existente (PO + Nita–Scholz); Saltelli LHS; packaging PRESSUPOSTO.
* **Fidelidade**: N2 baixa (sem RANS).
* **CLI / MCP**: `acdt shape {study|bounds|packaging}` / `shape_n2_study`, `shape_bounds`,
  `shape_packaging_score`.
* **Pedir à IA**: "Corre um N2 leve no result.json do UAV e mostra o Pareto aero/RCS/pack."
* **Limites**:
  * sem RANS/ADflow/TACS (Grok Build);
  * FOV completo continua em `assembly.integration`;
  * facetas só (não OML suave).

## 29. VTOL / eVTOL L0 — pairar, transição e arquiteturas

* **O que faz**:
  * potência de pairar e de subida pela teoria da quantidade de movimento, com FM, carga de disco,
    limite de Mach de ponta e C_T/σ;
  * energia de missão (pairar, subida, transição, cruzeiro, espera) e massa de bateria
    (limitada por energia ou por potência);
  * comparação multirrotor / lift + cruise / tilt-rotor à mesma massa e missão.
* **Métodos**: Johnson, *Helicopter Theory* 1980 Cap. 2; Leishman 2006 Cap. 2 (FM, subida, Glauert);
  Raymer 2018 §17.2; Hepperle 2012 (bateria); NDARC (NASA/TP-2015-218751) como referência de métodos eVTOL.
* **Fidelidade**: L0.
* **CLI / MCP**: `acdt vtol {hover|size|compare}`, `acdt bemt rotor` /
  `vtol_hover`, `vtol_size`, `vtol_compare`, `bemt_rotor`.
* **Pedir à IA**: "Compara multirrotor, lift + cruise e tilt-rotor para 25 kg e 40 km e diz qual
  precisa de menos bateria."
* **Fecho de massa opt-in (9 nov 2026)**: bloco `closure` (sem `mass_kg`) resolve o MTOW por bisseção
  com sinal no intervalo `mass_bounds_kg` (Burden & Faires 2011 §2.1): itens fixos/carga útil + rotores
  (NDARC AFDD00 pá+cubo, Cap. 27-2, ou massa fornecida) + motores (NDARC NASA15 vs binário de pico,
  Cap. 22-4, ou fornecida) + ESC (fração do motor com fonte) + suportes/braços (forma NDARC
  W_supt = f_supt·W_MTO, f_supt fornecido) + estrutura (fração/massa com fonte) + mecanismo de basculamento
  (obrigatório em tilt-rotor) / propulsor de cruzeiro (obrigatório em lift + cruise) + bateria nativa.
  Histórico, resíduo, estados `converged|not_bracketed|max_iterations|outside_model_domain|incomplete_component_coverage`;
  componente em falta ≠ zero. Regressões NDARC sempre marcadas como extrapolação para eVTOL pequeno.
  Acoplado a `onboard_size` (itens tornam-se massas fixas) e ao estudo de frota 1.1 (VTOL deixa de ser
  `not_applicable` quando há `closure`). Exemplos `examples/vtol/quadrotor_closure.yaml`,
  `examples/fleet/iter_vtol_closure.yaml`.
* **Limites**:
  * sem `closure`, massa dada (comportamento anterior inalterado); sem MDA;
  * BEMT axial/pairar é opt-in (`rotors.bemt` ou `acdt bemt rotor`); voo avançado, interferência
    rotor–rotor e ruído não automatizados; sem dinâmica de transição, OEI; sem correlação de
    fuselagem/asa/trem para UAV pequeno (fração/massa fornecida);
  * defaults por arquitetura são PRESSUPOSTOS. Exemplo `examples/vtol/bemt_hover_illustrative.json`:
    T=61,30 N, P=1077 W, FM=0,643 (vs FM L0=0,70 → 988 W no mesmo disco); polar EXAMPLE, não mapa de fornecedor.

## 30. Jatos de transporte subsónicos — L0

* **O que faz**: Mach crítico/divergência e arrasto de onda equivalente de asa (Korn–Mason/Lock);
  empuxo instalado e TSFC genéricos por Mach/altitude; We estatístico de transporte e orçamento
  de combustível/carga útil a MTOW dada; envelope V-n limpo de manobra em EAS.
  `jet size` fecha a massa de uma alternativa de geometria/motores fixos, acoplando
  CL/CDonda/L/D dependentes da massa ao Breguet diferencial e TSFC/empuxo do turbofan;
  reporta convergência/resíduo, refinamento numérico e falhas de empuxo/limite MTOW.
  A alternativa e o intervalo de massa são explícitos; não seleciona arquitetura.
  **Build-up parcial opt-in (7 nov 2026; alargado 9 nov 2026):** `weights.mode: components`
  recalcula regressões Raymer TRANSPORT Sec.15.3.2 (asa/HT/VT + fuselagem com L/D estrutural
  ADAC/SUAVE, trem main+nose com Wl e Vstall em kt, naceles, acessórios, APU, comandos,
  hidráulica, elétrica+aviónica, AC+anti-gelo, interiores, combustível seco) em cada tentativa;
  `engines_dry`/itens operacionais/`other_empty_items` continuam fornecidos (sem correlação
  empuxo→massa seca). W_press (Raymer Sec.15.3.3) opt-in na fuselagem; extração bleed/elétrica
  só como `pressurization.extraction` auxiliar fornecido (senão unassessed). Cobertura/fontes/
  aplicabilidade; falta ≠ zero nem fallback estatístico. Sem resíduo ajustado ao OEW.
  Triagem opcional `performance` (7 nov 2026): corrida AEO com T(V), polar de
  configuração e atrito explícitos; subida estacionária AEO/OEI por equilíbrio de
  forças, com n−1 motores e arrastos declarados. Margens de engenharia separadas
  de referências 25.121 (conformidade sempre não avaliada). Opt-in `performance.field` (9 nov 2026): ASD/TOD AEO·OEI/BFL com V1 procurado;
distância completa AEO preenchida quando o campo corre. Opt-in
`include_rotation_transition` (10 nov 2026): rotação + transição circular
(Roskam/Torenbeek) no TOD/BFL; omissão = modelo PR #25; dados em falta →
unassessed. Conformidade CS-25 e VMCG de ensaio continuam unassessed.
  O `feasible` antigo não muda; consultar `combined_requested_checks_passed` para
  os checks opcionais, nunca como prova de viabilidade completa.
* **Métodos**: Mason 2006 cap. 7; Gur/Mason/Schetz 2010; Mattingly 2002; Ihme 2025 eq. 2.77;
  Raymer 2018 tabelas 3.1/3.2, Breguet; Raymer 2012, 5.ª ed. §15.3.2 (asa/HT/VT/fuselagem/trem/sistemas) e §15.3.3 W_press;
  ERAU, equilíbrios de corrida/subida;
  provisões 14 CFR 25.335/.337 e referências numéricas 25.121(a)–(d) (paráfrases).
* **CLI / MCP**: `acdt jet {wave-drag|turbofan|loads|analyse|check|size|performance|weights}` /
  `jet_wave_drag`, `jet_turbofan`, `jet_loads`, `jet_analyse`, `jet_check`, `jet_size`, `jet_performance`, `jet_weights`.
* **Mapas L0/L1 opt-in (9 nov 2026)**: `engine.map` em `jet_size` / performance / analyse —
  `correlation` (default Mattingly/Ihme), `table` (grelha Mach×altitude×throttle com
  `thrust_lapse`/`TSFC`) ou `corrected_table` (F/δ, SFC/√θ; Walsh & Fletcher). Fora do domínio
  → `unassessed` (nunca extrapola em silêncio). O processo acdt não corre pyCycle, NPSS,
  GasTurb, T-MATS nem CFD.
  Exemplo `examples/jet/engine_map_table.yaml` (MTOW idêntico ao default em cruzeiro Π=1).
  Motor elétrico: `core.motor_map` η(P) opcional no hybrid dispatch; mapas de motor térmico
  de ciclo continuam pendentes no PC do João.
  A instalação publicada `om-pycycle` 4.4.0, OpenMDAO 3.41.0 e NumPy 1.26.4, noutro
  intérprete, resolve o turbojato simples da etiqueta 4.4.0 sem ajuste local de `ThermoAdd`.
  A comparação com a correlação L0 de turbofan de alta razão de bypass fica `nao_aplicar`:
  o L0 não fica validado nem calibrado. O deck termodinâmico L1 deste turbojato não existe
  (`nao_avaliado`). Faltam, na grelha que `engine_map` aceita, `source`, `mach`,
  `altitude_m`, `throttle`, `thrust_lapse`, `thrust_installed_N` e `TSFC_kg_N_s`, e na
  tabela corrigida `F_over_delta`, `SFC_over_sqrt_theta` e `totals`. O mapa também não
  guarda OPR, caudais, empuxos bruto e de ram, FAR, T4, eficiências, rotação nem totais
  de estação. O yaml ilustrativo não foi editado. Registo:
  `examples/output/jet_pycycle/h8_pycycle_sem_ajuste.json`.
* **Exemplo**: `examples/jet/a320_ref.json` (URL/data por campo) e
  [tutorial-jet](docs/tutorial-jet.md) e [triagem](docs/tutorial-jet-performance.md). Check apenas de ordem de grandeza We/OEW,
  tolerância PRESSUPOSTO de 25%; alcance e empuxo são entradas, não validações independentes.
* **Limites**: cruzeiro M≤0,9; triagem de corrida/subida M≤0,3; motor ISA até 15 km;
  faixa de asa representativa, pressupostos explícitos;
  empuxo não globalmente monótono em Mach por recuperação de pressão; We não é OEW operacional;
  sem MDA completo de transporte (há fecho de massa em geometria fixa); mapas leves de mesa OK, pyCycle/NPSS/GasTurb/T-MATS/CFD adiados; build-up Torenbeek completo, mapas ECS, rajadas/Mach/buffet,
  CFD ou precisão de certificação. Componentes fornecidos ou modelados são totais (não por motor),
  sem tripulação/carga/combustível; depósitos secos entram uma vez. Cobertura declarada
  não garante inventário físico completo; sem precisão quantitativa calibrada.
  Combustível inutilizável em storage não realimenta a massa; não é OEW operacional nem integração
  física montagem/CG. `examples/jet/component_weights.yaml`, `coupled_components.yaml` e `components_raymer_extended.yaml`:
  todos os inputs novos são PRESSUPOSTOS, não ajuste ao A320.
  **Não demonstra conformidade CS-25.**

## 31. Armazenamento de energia comum — L0 (7 nov 2026)

* **O que faz**: balanço de combustível utilizável/carga/capacidade, pack nominal×DoD,
  reserva explícita uma vez, massa/volume com densidade e propriedades **de pack**
  fornecidas; limites de volume líquido alocado por portador ou soma num espaço comum.
  Dados ausentes ficam não avaliados. Inventário não é massa a somar novamente ao avião.
* **Reutilização**: adaptadores de resultados `jet_size`, `vtol_size` e missão existente
  pointmass/6-DOF (kg/Wh; hélice térmica/elétrico). Bloco `storage` opcional em jet/VTOL
  acrescenta checks separados, sem mudar o `feasible` antigo ou realimentar a massa.
* **CLI/MCP**: `acdt storage check` / `storage_check`; [tutorial](docs/tutorial-energy-storage.md),
  exemplos executáveis em `examples/storage/` (quatro produtores reais de modelos L0).
* **Método**: identidades massa/densidade/volume e E/m/E/V; NIST SP 811 (2008) unidades;
  contexto energético Hepperle 2012. Densidades, DoD, reservas e embalagens são entradas,
  sem constantes empíricas novas. Propriedades de células não viram Wh/L de pack.
* **Limites**: desigualdades escalares, não prova de ajuste 3-D/CG/segurança; pico/rating
  ausentes não provam potência. Massa seca de depósito ausente não vira zero.
  Adaptador de demanda **não é novo suporte do simulador dinâmico para jatos/VTOL**.
  Aceita dois portadores declarados, mas despacho híbrido está por implementar;
  sem fecho MDA/feedback de massa, nem certificação.

## 32. Carga útil e elétrica transversais — adaptador L0 opt-in

* **CLI / MCP**: `acdt onboard size --input examples/onboard/jet.yaml` / `onboard_size`.
  Receita versionada 1.0 com inventário, proveniência, inclusão de massa e alocação de loads.
* **Efetivo:** massa de payload/equipamento afeta o fecho prop (térmico/elétrico) e `jet_size`;
  hotel afeta energia/bateria do elétrico/VTOL; gerador com coeficientes explícitos afeta combustível
  e potência/tração disponível no prop/jato. VTOL mantém MTOW inclusivo fornecido e verifica a
  margem com o resto de massa declarado, sem fingir fecho MTOW. Pesos de jato continuam parciais.
* Média/duty, pico simultâneo, eficiência da distribuição, limites de geração/bateria e capacidade
  dedicada são separados. Reserva/DoD nativas uma vez. Sem modelo de extração não há eletricidade
  grátis; sem capacidade/dados geométricos o check é `null`, não pass. `feasible` nativo separado
  de `combined_checks_passed`; nenhum default antigo altera sem opt-in.
* `mission` opcional executa pointmass existente **só no prop**, com consumo acoplado. Jato e VTOL
  continuam sem simulador dinâmico comum. Híbrido: balanço alocado apenas, dispatch não implementado.
* Calor/volume declarados e `assembly.integration.check` (posições/CG/FOV fornecidos) são screens
  independentes aplicáveis a todos, não uma solução térmica/CG/FOV integrada no otimizador.
  Sem extração térmica 6-DOF/BEMT ou falhas/OEI de geração; pico combinado do pack prop por avaliar.
* **Fecho L0 opt-in `closure` (9 nov 2026)**: térmico (calor declarado ± perdas de conversão vs
  capacidade/`Q=ṁ cp ΔT`), CG (Σm·r vs envelope), espacial (baías/caixas AABB) e FOV (raios vs
  caixa/esfera). Dados em falta → `null`, nunca pass. Exemplo `examples/onboard/closure_electric.yaml`.
  FOV com malha completa continua em `assembly.integration`. Não é projeto ECS, envelope certificado
  nem otimizador de packaging.
* **Ponte nativa + fecho automático no size (9–10 nov 2026)**: bloco `onboard` em `acdt size` /
  `MissionSpec`, `jet_size` e `size_vtol` → `onboard_bridge` (`domains/aircraft/onboard_bridge.py`)
  mapeia hotel citado para os hooks nativos (`auxiliary_fuel_flow_kg_s`+`auxiliary_shaft_W`,
  `onboard_power_W`, `auxiliary` jato, `electric.systems_power_W` VTOL) **dentro** do ciclo de size —
  sem segundo passo manual. `DesignResult.onboard_bridge` + `result.json` / toolkit summary; issue
  info «onboard auto-closed inside size». Sem `onboard` → no-op (casos antigos iguais).
  Coeficientes de extração/BSFC/`fuel_kg_kWh_terminal` são **entradas** (PRESSUPOSTO ou fonte);
  incompletos → `ValueError` unassessed (nunca energia grátis / zero silencioso). Híbrido sem
  `hybrid_dispatch` → unassessed. Não inventa potência Gabbiano nem outros datasheets.
  Exemplos `examples/onboard/prop_size_radar_hotel.yaml` (+ baseline sem hotel) com Δ combustível
  reproduzível; testes `tests/test_onboard_bridge.py`. `onboard_size` continua para closure/CG/FOV.
* [Tutorial e contrato de contabilização](docs/tutorial-onboard.md), exemplos em `examples/onboard/`;
  todos os novos valores exemplificativos são PRESSUPOSTOS.


## 32b. Juiz comum de missão jet/VTOL — L0 opt-in (9 nov 2026)

* **API**: `simulate_common_mission` / frota `operations.common_sim.enabled`.
* Jato: pointmass Anderson/Raymer + `engine_point` (correlação ou mapa). VTOL: timeline de
  energia a partir de `size_vtol`. Fases pedidas mas não modeladas → `unassessed`.
* Exemplos `examples/fleet/jet_common_sim.yaml`, `vtol_common_sim.yaml`. Default da frota
  sem a flag inalterado. Sem 6-DOF/CFD/pyCycle.

## 32c. Atalhos de configuração e diedro — L0 opt-in (9 nov 2026)

* **API**: `assumptions.geometry.configuration`: `conventional` (omissão) | `V` | `inverted_V` |
  `twin_boom`. Named types assemble generic components (`assembly/shortcuts.py`); a supplied
  `assumptions.assembly` drawing always wins. Missing Γ / volumes → refuse (no silent H+V substitute).
* V / inverted-V panel area: Purser & Campbell (NACA Rep. 823) projections + Raymer 2018 Eqs. 6.28–6.29.
* **`geometry.dihedral_deg`**: explicit wing dihedral. Spiral (`hq:spiral`) uses Clβ from AVL (Etkin &
  Reid / Nelson); without an explicit dihedral the spiral check is **unassessed** (unknown≠pass).
* Examples: `examples/uav_inverted_v_shortcut.yaml`, `examples/uav_twin_boom_shortcut.yaml`.
* Flying-wing winglet sizing + gear on that layout: see §32d (9 nov 2026).


## 32d. Asa voadora — winglets/deriva + trem — L0 opt-in (9 nov 2026)

* **API**: `assumptions.assembly.options.flying_wing` (off by default). Shortcuts mutate the generic
  drawing before the W0 loop (`assembly/flying_wing.py`); a drawing that omits the block is unchanged.
* `size_winglets: true` + required `c_vt` (Raymer 2018 Eq. 6.29 vertical volume
  `(S·|sin Γ|·l_v)/(S_w·b)`, same projection as `handling.vertical_volume`). Chord-only iterative
  scale of winglet/fin/vtail panels (span and tip station fixed). Missing `c_vt` or no directional
  surface → **unassessed** (never a silent invented volume). Dutch-roll / spiral stay the existing
  MIL-F-8785C `hq:*` checks after AVL (Nelson / Etkin & Reid).
* `place_gear: true`: switch `gear.type` to `tricycle` and let `gear_layout` place tip-back /
  nose-load / rotation / 14 CFR 23.925 prop clearance on the mesh. Empty Raymer Ch. 11 8–15 % band
  for the CG travel → infeasible/unassessed with residuals (no fake pass). Optional PRESSUPOSTO
  `gear.nose_fraction` wider band and `extend_fuselage_for_gear` (revert-on-fail).
* Examples: `examples/heavy/uav150_flying_wing_closed.yaml` +
  `examples/integration/flying_wing_pusher_closed.json`. Baseline
  `examples/heavy/uav150_flying_wing.yaml` (no flag) unchanged.
* Named types remain shortcuts that assemble generic components, never a closed list.


## 32d-bis. Asa voadora sem superfícies verticais — split ailerons + SAS — L1 opt-in (10 nov 2026)

* **API**: `assumptions.assembly.options.flying_wing.yaw_control: split_aileron` (off by default; o desenho
  não tem deriva nem winglets), `sas` (por omissão **true num UAV** — o piloto automático ativo é a hipótese
  base no UAV —, false nos outros), `split_aileron: {eta_inner, eta_outer, cf_c, delta_max_deg,
  rate_max_deg_s, K_f}`, `elevon: {eta_inner, eta_outer, cf_c, max_deg}`, `crosswind_kt`, `turbulence:
  light|moderate|severe`. Código: `assembly/tailless.py`, ligado em `handling.apply`. `size_winglets` é
  ignorado (unassessed) com `yaw_control: split_aileron`.
* **Arrasto do split aileron** (o que gera a guinada): McCormick 1995, Eqs. 3.45–3.46,
  ΔC_D = K_f (c_f/c)^1.38 (S_f/S) sin²δ, K_f = 1,7 (flaps simples/split), por folha (PRESSUPOSTO: as duas folhas
  somam). Equação e K_f lidos em fontes secundárias que citam o livro (Sun et al. 2020, OpenAP; Ananda & Selig
  2016 Eq. 5); `K_f` pode ser substituído por um valor medido. ΔC_n = ΔC_D·ȳ_f/b. Efeitos secundários:
  ΔC_l ≈ ΔC_m ≈ 0 com folhas iguais (Löchert et al. 2019, DLR, escoamento colado α ≤ 10°, |β| ≤ 10°); fora
  desse envelope ficam **unassessed** (aviso). ΔC_m da resistência fora da altura do CG é calculado.
  **O AVL é invíscido e não vê este arrasto** — só dá a célula nua e a elevon (C_lδa, C_nδa).
* **Casos de dimensionamento** (saem deflexão necessária e fração de envergadura necessária, por caso):
  vento cruzado em derrapagem estabilizada (≥ 0,2 V_S0, 14 CFR 23.233(a) pré-Amdt 64, U = 1,1 V_S0,
  Roskam AFD I 4.2); coordenação contra guinada adversa (MIL-F-8785C Tabela IXa, entrada/rolamento/viragem a
  30°); turbulência lateral (Dryden MIL-F-8785C baixa altitude, h = 50 ft) como autoridade do SAS.
  Aproximação em crab: decrab **unassessed**.
* **SAS**: amortecedor de guinada + aumento de C_nβ pelos split ailerons, u = k_β β − k_r r̂; ganhos mínimos em
  autoridade que cumprem MIL-F-8785C Nível 1 (Tabela VI da categoria em cruzeiro e Cat. C na aproximação,
  Tabela VIII). `hq:dutch_roll`/`hq:spiral`/`hq:roll` com SAS só passam se 3σ_u ≤ capacidade 2·C₁·sin²δ_max e
  a taxa ≤ `rate_max_deg_s`; dados em falta → None (unassessed ≠ pass). A célula nua é sempre reportada
  (mensagem e `res.dynamics['tailless']['bare']`). Novas linhas `hq:yaw_crosswind`, `hq:yaw_coordination`,
  `hq:sas_authority`.
* **Seguimento (10 nov 2026, `assembly/tailless_actuation.py`, `tailless_approach.py`, `tailless_followup.py`)**:
  * **Momentos de charneira e servos** (`hq:actuators`, `asm:actuator_mass`): folha do split com
    |C_hf| = H/(q c_f S_f) de NACA TN 690 (Wenzinger & Rogallo 1939) Figs. 17–18 (dados de NACA TN 498, split
    flaps 0,15c/0,25c, Clark Y), envolvente lida dos gráficos δ 0/15/30/45/60° → 0,135/0,30/0,43/0,555/0,64;
    δ > 60° → unassessed. PRESSUPOSTOS: c_f/c = 0,40 extrapolado dos 0,15–0,25c ensaiados; folha superior com o
    mesmo |C_hf|. Elevon: C_h do AVL (`HM`, invíscido, sem compensação). Calendário 14 CFR 23.455(a)(2)
    (pré-Amdt 64): deflexão total em V_A, 1/3 em V_D (o mesmo de `flightsim.controls`). Servo do
    `actuators.catalog` (dados do fabricante, nenhum inventado): G = max(FoS·H/T_pico, FoS·H_op/T_nominal),
    taxa na superfície ω_nominal/G, curso G·δ_max ≤ curso do datasheet quando dado (senão unassessed);
    `max_per_surface` servos iguais em paralelo (PRESSUPOSTO: partilha igual). A taxa efetiva do servo
    escolhido substitui `rate_max_deg_s`. Massa por superfície comparada com os itens de
    `weights.components.items` com "servo/atuador" no nome.
  * **Dinâmica do atuador no laço do SAS** (`hq:sas_time_delay`): atraso de transporte (Padé 2) + lag de 1.ª
    ordem; o SAS é dimensionado já com o atuador. Atraso/lag desconhecidos → atraso equivalente puro de 0,10 s
    = limite Nível 1 de MIL-F-8785C 3.5.3 (0,10/0,20/0,25 s Níveis 1/2/3; citado em NASA NTRS 19910005040
    §2.1.1 e AIAA doi:10.2514/3.20149) — PRESSUPOSTO. Margem de atraso até sair do Nível 1 reportada. No tempo:
    limite de taxa, saturação e lei ΔC_n = 2C₁ sin²|s|.
  * **Rajada lateral discreta** (`hq:lateral_gust`), separada da turbulência Dryden: 1−cos de 50 ft/s EAS em
    V_C, comprimento 25 c̄ (14 CFR 23.443(a)/(b) e 23.333(c), pré-Amdt 64 — 23.443 é de cargas em superfícies
    verticais, aqui PRESSUPOSTO como caso de guinada); modelo lateral linear com bank hold pela elevon
    (Beard & McLain 2012 Sec. 6.3.1) e SAS pelo atuador. Passa só sem saturação, sem limite de taxa e com β
    amortecido (≤ 10 % do pico no último quarto).
  * **Equilíbrio de picada** (`hq:pitch_trim_tailless`): trim linear (Etkin & Reid 2.4) com a elevon simétrica
    no AVL por caso de massa; C_L máximo equilibrado (limite da elevon) e C_L de secção crítica (Phillips &
    Alley 2007, `clmax_airfoil`). Assinala que o `CLmax_landing` do tipo fixo inclui o flap de
    `assumptions.aero.flap`, que o desenho sem deriva não tem.
  * **Opções para o vento cruzado** (`asm:crosswind_options`, quando `hq:yaw_crosswind` falha; o requisito
    não é relaxado): (a) split maior (c_f/c ou envergadura), (b) elevon maior (AVL), (c) aproximação mais
    rápida (k·V_S0, custo rolagem ∝ V², Raymer 17.9), (d) crab + decrab com piloto automático (resíduo no toque;
    carga lateral no trem e dinâmica do decrab unassessed), (e) tração diferencial (só com > 1 motor).
    STANAG 4671 não é citado (texto do vento cruzado não verificado).
  * **6-DOF / JSBSim** (`flightsim/tailless_sim.py`): `acdt simulate … --fidelity 6dof` com uma asa sem deriva
    constrói o modelo de voo **da montagem** (AVL α −4…16° com a elevon simétrica e antissimétrica) e põe o
    canal do leme = ΔC_n do split (C_nδr = 1, C_Yδr = C_lδr = 0) com ΔC_D = (b/ȳ_f)|ΔC_n|
    (`AeroModel.yaw_drag_per_Cn`, 0 por omissão → modelos existentes inalterados; exportado para o JSBSim como
    `D_drag_rudder`). Corre o ensaio lateral (trim de cruzeiro no caso de massa que equilibra, rajada 23.443,
    célula nua vs SAS com o atuador) e, com `--jsbsim`, um doublet de ΔC_n em malha aberta no JSBSim.
    **Missão 6-DOF** (12 nov 2026): com `--mission`, voa a missão no caso `cheio`. O laço de derrapagem do
    piloto automático passa pelo split (`AeroModel.yaw_sas`, `Autopilot.yaw`): u = k_β β − k_r r̂ com washout
    τs/(τs+1), τ 4,2 s (MIT 16.333 Lecture 12, How 2004; PRESSUPOSTO), e o mesmo `SplitActuator` (pré-deflexão,
    taxa, atraso). Na aterragem, decrab por PD de rumo no eixo de guinada (forma de Beard & McLain 2012
    Eq. 6.7–6.8: k_ψ = ΔC_n,max/e_ψ,max, e_ψ,max 20° PRESSUPOSTO, ζ 0,707; integral k_ψω_ψ/2 com anti-windup,
    Sec. 6.5; feed-forward −C_nβ(α)β da própria tabela). Opções do segmento: `heading_deg`, `decrab`,
    `decrab_height_m`. Trem triciclo da montagem (x, h_cg, bitola) e para-choques nas pontas de asa. No toque:
    crab residual, deriva, φ, β e picos das cargas laterais por roda contra os limites de **14 CFR 23.485**
    (pré-Amdt 23-64, Amdt 23-45: só rodas principais, vertical 1,33, 0,5 W para dentro num lado e 0,33 W para
    fora no outro). Um contacto de para-choques dá `side_load_ok` False.
* **Exemplo antes da correção** (histórico): `examples/heavy/uav150_flying_wing_tailless.yaml` + `flying_wing_pusher_tailless.json`: fecha
  com W0 ≈ 157 kg (eram 136 kg; a subida vem dos 9,9 kg de servos do catálogo Volz no orçamento de
  componentes); célula nua com rolamento holandês instável; com SAS (k_β 0, k_r 0,30) e atraso de 0,10 s:
  cruzeiro ζ 0,16 / ω 3,28 rad/s, aproximação ζ 0,09 / ω 4,80 rad/s → Nível 1, margem de atraso 0,14 s.
  Charneira por folha do split 20,9 N·m (V_A, 60°) → 2× Volz DA 30-HT por folha (G 0,49, 204 °/s ≥ 202 °/s
  exigidos), 8,8 kg; elevon 4,0 N·m → 2× DA 26 por lado (curso 27,5° ≤ 45°), 1,1 kg. Rajada lateral 17,7 m/s
  TAS, 14,8 m: com SAS β pico 21°, split 21,4°, elevon 23,4°, amortece, mas toca no limite de taxa (0,35 % do
  tempo, nas passagens por δ = 0 da lei sin²) → **falha** pelo critério estrito. **Equilíbrio de picada falha**:
  só o caso 'vazio' equilibra o cruzeiro (δe −22°); 'carga'/'combustível'/'cheio' (margem estática
  0,34–0,49) precisam de δe ≈ −92…−168°; C_L máximo equilibrado 0,15–0,57 ≪ CLmax_landing 1,75 — o α ≈ 22° da
  aproximação é o sintoma. Vento cruzado de 10,1 kt **falha** (split 70,6° > 60°); fecha só com aproximação
  a 1,2 V_S0 (31,2 m/s, rolagem ×1,19); split maior fecha a guinada mas não a elevon; crab/decrab
  unassessed. 6-DOF ('vazio'): trim α 12,4°, δe −20,5°; rajada: β pico 19,8° (nua e SAS), β final 0,54° nua
  vs ≈ 0 com SAS; elevon satura nos 25°; JSBSim vs 6-DOF (doublet de ΔC_n) NRMS β 0,031, p 0,027, r 0,033.
* **Correção do equilíbrio de picada (10 nov 2026, ramo `tailless-pitch-trim`, `assembly/tailless_trim.py`)**.
  Tudo opt-in. Os outros exemplos ficam iguais.
  * `assumptions.assembly.options.useful_load_at: empty_cg`: a carga sem item posicionado e o combustível sem
    tanque desenhado vão para o CG das massas fixas (Raymer 2018 Sec. 15.1, como a estação de 'balance' do tipo
    fixo). Assim o combustível não mexe no CG. Antes iam para o centróide do corpo, e a variação do CG era
    enorme. PRESSUPOSTO: o volume/packaging nesse ponto fica **unassessed**; para o verificar, use itens posicionados.
  * Banda de margem estática 0,02–0,08 de NACA TR-796 (Donlan 1944, "a range of ultimate static margin from 0.02
    to 0.08 appears to be reasonable for tailless airplanes"; o CG nunca fica atrás do centro aerodinâmico).
    Está em `approach_consistency['static_margin_band']`. Uma margem fora da banda gera um aviso, mas não reprova.
  * Verificação da torção pela fórmula de Panknin (1989, "Flying Rainbows", MARCS Symposium; reproduzida por
    Kuhlman em b2streamlines.com/Panknin/Panknin.html). O teste reproduz o exemplo publicado: −8,6° total e
    ≈ −3,2° geométrica com o K1 arredondado do site. O resultado está em `approach_consistency['washout_check']`.
    PRESSUPOSTO: secções simétricas, como no AVL. Quem decide é o equilíbrio AVL; Panknin é só a estimativa de partida.
  * `options.flying_wing.clmax: trimmed`: o CLmax de dimensionamento (limpo, descolagem e aterragem) passa a
    ser o **C_L máximo equilibrado** do desenho escalado e balanceado. É o mínimo sobre os casos de massa,
    com a elevon limitada a `max_deg` e a secção crítica. O W0 é re-dimensionado até a variação ficar abaixo
    de 0,01 (no máximo 5 passagens), com o resultado em `res.tailless_trim`. O requisito de V_S mantém-se:
    um CLmax menor dá uma asa maior e não alivia a velocidade de perda. Com `assumptions.aero.flap.kind: none`
    não há flap.
  * O ensaio lateral 6-DOF corre em **todos** os casos de massa que equilibram o cruzeiro
    (`lateral_tests`). O caso de referência continua a ser o de menor |δe|.
* **Exemplo** (`examples/heavy/uav150_flying_wing_tailless.yaml` + `flying_wing_pusher_tailless.json`, depois
  da correção). As alterações foram: carga útil no CG das massas fixas, `balance.static_margin` 0,10 → 0,05,
  torção da ponta −4° → −10°, sem flap, `clmax: trimmed`, e servos do split DA 30-HT → DA 30 (8,8 → 5,04 kg),
  que são os escolhidos para a nova charneira. A elevon fica igual (0,20–0,45, c_f/c 0,25, ±25°).
  * Fecha com W0 **138,3 kg** (antes 157,0) e S 2,905 m².
  * CLmax equilibrado: 1,33 → 1,109 → 1,128, convergido. O caso que manda é 'carga'.
  * V_S0 fica igual, porque o requisito se mantém (aproximação a 1,1 V_S0 = 28,6 m/s).
  * Margem estática Torenbeek por caso (vazio / carga / combustível / cheio): 0,051 / 0,063 / 0,051 / 0,061,
    todas dentro da banda TR-796. A margem AVL sem corpos é ≈ +0,02.
  * δe de cruzeiro: +7,6° / +1,7° / +5,0° / −0,9°.
  * Torção desenhada −10° contra Panknin −8,1° (C_L 0,51, σ 0,073).
  * `hq:pitch_trim_tailless` **passa**.
  * Vento cruzado de 10,1 kt **passa**: split 40,6°, elevon −17,6°, máximo 14,5 kt.
  * SAS (k_r 0,075): rolamento holandês ζ 0,113, ω 2,29 rad/s → Nível 1. Com o atuador: cruzeiro ζ 0,118,
    aproximação ζ 0,088 → Nível 1, margem de atraso 0,18 s.
  * Autoridade 3σ 0,0037 contra 0,0215; taxa 76 °/s contra 96 °/s (2× Volz DA 30 por folha). Elevon 2× DA 26
    por lado.
  * A rajada lateral continua a **falhar** por tocar no limite de taxa (0,5 % do tempo).
  * Período curto ζ 0,335 → Nível 1. O fugóide desceu para ζ 0,039 → **Nível 2** (antes 0,059; L/D maior;
    indicativo num UAV).
  * 6-DOF nos 4 casos: trim α 6,6–10,9°, δe +9,4…+0,3°; o SAS reduz o β final em todos.
  * JSBSim contra 6-DOF (doublet de ΔC_n, caso 'cheio'): NRMS β 0,23, r 0,27, φ 0,28. A concordância piorou
    em relação aos ≈ 3 % anteriores (caso 'vazio' antigo) e fica **por explicar**: a célula nua é instável e
    diverge durante os 8 s.
  * Estudo de alternativas (dimensionamentos completos, SM 0,05, carga no CG, CLmax equilibrado), com os servos
    antigos: torção −4° → W0 151,0 kg (CLmax 0,86); −8° → 146,2 kg (1,06); −10° → 146,0 kg (1,15); −10° com
    elevon desde η 0,10 → 146,1 kg (1,20); −12° → diverge (W0 289 kg). **Só elevon maior** (sem mexer no CG):
    os casos com carga continuam a pedir δe −166…−354°. O C_mδe quase não cresce com c_f/c numa elevon
    interior em flecha, e a perda de C_Lδe aumenta, por isso a área da elevon sozinha não fecha.
* **Itens em aberto tratados (11 nov 2026)**:
  * **JSBSim vs 6-DOF** (doublet de 3 % da capacidade, 8 s, os 4 casos em `jsbsim_cases`). O resíduo foi
    explicado e corrigido em quatro pontos:
    * O doublet de 30 % levava a célula nua a β 40–80°, fora das tabelas lineares.
    * O export não tinha o arrasto induzido de C_Lδe·δe/C_Lq·q̂ (manete 0,612 vs 0,547).
    * A latitude do IC era 0° (g −0,3 %); passou a 45°.
    * A força lateral no AERORP deslocado gerava guinada (a função `Yaw_aerorp_side_force_correction` cancela-a),
      e faltava −D·sinβ na força lateral do 6-DOF. As forças do 6-DOF passaram a eixos de vento (JSBSim
      Reference Manual, DRAG/SIDE/LIFT).

    Resultados:
    * NRMS β 0,019/0,020/0,020 em carga/combustível/cheio.
    * No caso vazio, 0,119. A célula nua é instável e oscilatória (σ 0,060 1/s, duplica em 11,6 s; C_nβ < 0 no α
      de trim), e o próprio modelo, re-equilibrado com o Δα de 0,007°, já dá 0,08 (`self_sensitivity_nrms_beta`,
      `bare_modes`).
  * **Rajada lateral**: o critério estrito mantém-se (sem norma citável que admita saturação de taxa breve), por
    isso continua a falhar. `lateral_gust.options` reporta o que a fecha:
    * servo ×2 não fecha; ×5 (478 °/s) fecha;
    * pré-deflexão simétrica δ0 = 2° (ΔC_n = 2C₁ sin2δ0 sin2d, linear em zero; Rajput, Zhang & Qu 2014, Appl.
      Mech. Mater. 643:54; Wang, Wang & Jia 2011, Acta Aeronaut. Astronaut. Sin. 32(8):1392) fecha, com pico de
      46 °/s e ΔC_D +0,7 % de C_D0 (McCormick Eq. 3.45). **12 nov 2026**: `split_aileron.bias_deg` é opção de
      projeto (opt-in). O ΔC_D0 = 2·K_f(c_f/c)^1,38(S_f/S)·2sin²δ0 (as duas asas) entra no polar de
      dimensionamento (`assembly_loop.drag.split_bias`; chaves em falta → unassessed, ΔC_D0 None, nunca 0).
      No exemplo, com δ0 2°, ΔC_D0 = 0,000202; C_D0 0,02806 → 0,02824; W0 138,3 → 138,6 kg; `hq:lateral_gust`
      passa (split 8,8°, 46 °/s, sem limite de taxa no modelo linear). No 6-DOF, o caso `cheio` ainda toca o
      limite de taxa em 0,04 % do tempo (pico 95 °/s). 4/6/8/10° custam
      2,9/6,5/11,5/17,8 %.
  * **Fugóide com manutenção de atitude** (`hq:phugoid_autopilot`; Beard & McLain 2012 Sec. 6.4.1, níveis de
    MIL-F-8785C 3.2.1.2 em malha fechada; e_θ,max 10° e ζ 0,707 PRESSUPOSTO). k_pθ −1,74, k_dθ −0,72 s; raízes
    reais −0,537/−0,167 → Nível 1; período curto ζ 0,75. A célula nua tem ζ 0,039 (Nível 2), reportada.
  * **Packaging no CG** (`asm:useful_load_packaging`, `tailless_trim.cg_packaging`): grelha de pontos com
    `contains` dos corpos e da asa, menos os itens desenhados. Combustível 22,3 kg = 31,6 L (0,72 kg/L
    PRESSUPOSTO; 2 % de expansão, 14 CFR 23.969 pré-Amdt 64), cabe em volume bruto a ±0,075 m do CG vazio
    (asa 27 L + corpo 6 L; centróide −6 mm). Só no corpo central, ±0,39 m. A carga de 27 kg precisaria de
    1,15/0,64/0,33 kg/L a ±0,12/0,17/0,28 m. A linha é None (necessário, não suficiente); se não couber, False.
  * **Taxa exigida da elevon**: pico do bank hold na rajada, 100 °/s ≤ 121 °/s do DA 26 → `hq:actuators` passa.
  * **C_m dos corpos** (12 nov 2026, ramo `tailless-trim-packaging-friction`): entra no equilíbrio de picada
    principal (`bodies_in_main_trim`; C_m += C_N k, k = −ΔX_np/c̄ = +0,0279 c̄ no exemplo, Torenbeek; C_m0 dos
    corpos = 0, PRESSUPOSTO). O trim só com a asa AVL fica em `avl_wing` (sensibilidade). δe de cruzeiro
    (corpos / asa AVL): +11,5/+7,4, +6,9/+1,7, +10,0/+4,9, +5,4/−0,8° (vazio/carga/combustível/cheio).
    O laço W0 do CLmax **não** toma este termo como crédito (com ele CLmax 1,15→1,24, S 3,186→2,873 m²,
    rolagem fly-off 307 m > 300 m). CLmax de dimensionamento, W0 150,4 kg e S 3,186 m² inalterados.
  * **Packaging fino** (`asm:fine_packaging`, `tailless_trim.fine_packaging`): combustível empacotado no volume
    bruto (corpo, depois asa) nas células mais perto do CG vazio (Raymer 2018 Sec. 15.1). Exemplo: 33,6 L
    cabem no corpo, centróide −106 mm do CG vazio; carga candidata +75 mm no residual (volume unassessed);
    CG cheio vs lumping +6 mm; SM empacotada 0,050/0,076/0,029/0,054 (NACA TR-796, dentro da banda). `ok` é
    None (volume da carga unassessed). O equilíbrio principal mantém `useful_load_at: empty_cg`.
  * **Sensibilidade ao atrito** (`friction_sensitivity` na missão 6-DOF): primeira ordem, cinemática congelada
    no toque. Neste voo, μ 0,8 → rácios 23.485 0,71×/0,66×; banda PRESSUPOSTO 0,6/0,8/1,0 todos ≤ 1
    (0,53/0,49, 0,71/0,66, 0,89/0,82). μ_travão 0,3–0,5 (Raymer 2018 Table 17.1) só como contexto.
  * **Limite de taxa do split no `cheio`**: `yaw_split` reporta `rate_max_deg_s` e `rate_limit_note`. Neste voo
    o limite (84 °/s na superfície) foi tocado em 0,21 % do tempo; o pico é a taxa já limitada. Não é um
    passa silencioso. Sem saturação de comando; sem mudança de bias/ganhos. A missão é avaliada à parte.
* **Missão do exemplo** (`examples/simulation/uav150_tailless_crosswind.yaml`: vento 5,2 m/s de 270°, pista 0°;
  12 nov 2026): avaliada, 11,2 min, 0,24 kg de combustível. Curvas com β máx 7,9°; split no pico ΔC_n 0,0117
  (55 % da capacidade), 0,14 % do tempo no limite de taxa. Aterragem: V_REF 34,2 m/s; crab −9,1° no início do
  decrab (30 m AGL), **resíduo −0,2°** e deriva 0,35 m/s no toque; φ −0,8°, afundamento 1,21 m/s. Cargas
  laterais no trem principal: 744 N para dentro (1,07× o limite 23.485 de 697 N) e 732 N para fora (1,59× de
  460 N). Há contacto das pontas de asa (93 N / 15 N) com a bitola mínima de capotamento (0,42 m, PRESSUPOSTO;
  ângulo de folga 11,6°) → `side_load_ok` False. **Descolagem limitada pela rotação**: a elevon satura a −25°,
  a roda do nariz não levanta (trem principal 0,11 m atrás do CG; 5 % no nariz), descolagem a 40,8 m/s e
  rolagem de 1053 m contra 300 m pedidos. Sem decrab, o crab residual seria 9,3° (cargas 1,60/3,95×). Os
  resultados no toque dependem do modelo de atrito (μ_lateral 0,8, tanh(v_y/0,5)).
* **Trem da asa sem deriva: rotação e bitola (12 nov 2026, ramo `tailless-gear-rotation-track`; opt-in
  `gear.ground_attitude_deg`, `gear.wheelbase: longest|shortest`, `flying_wing.takeoff_rotation`)**:
  * **Rotação** (`flightsim/tailless_takeoff.py`, linha `gear:takeoff_rotation`): Sadraey 2012 Sec. 9.6.2
    (Eq. 9.35 V_R = 1,1–1,3 V_S; Eq. 9.52–9.53 momentos em torno do contacto do trem principal; Table 9.6
    θ̈ ≥ 8 °/s², GA ligeira normal; UAV não listado → PRESSUPOSTO; μ 0,04, Raymer Table 17.1). Numa asa sem cauda
    a elevon perde quase todo o momento em torno das rodas (o C_Lδe para baixo cancela-o: potência líquida
    c̄C_mδe + C_Lδe(d + μh)), e com o corpo nivelado C_L(α=0) = −0,29. A banda é vazia: tip-back pede d ≥ 0,114 m,
    rotação a 1,3 V_S pede d ≤ 0,053 m; a elevon teria de ir a −108°. Por isso o exemplo usa a alternativa
    citada na mesma secção (B-52, descola sem rodar): **atitude no solo = atitude de descolagem**, θ_g 19°, por
    extensão da perna do nariz. A descolagem verifica δe de trim (C_m = 0), V_LOF ≥ 1,1 V_S (Raymer 2018
    Sec. 17.8) e a rolagem por integração de massa pontual (sem efeito de solo, PRESSUPOSTO) contra o requisito
    `takeoff_ground_roll`.
  * **Geometria em atitude** (`assembly/sizing.gear_layout`): tip-back na atitude estática (atan(d/h) − θ_g ≥ 15°,
    Raymer Ch. 11); rotação até tocar medida a partir da atitude estática (10–15°); folga da hélice (14 CFR
    23.925(a)(1), 7 in) na pior das duas atitudes; fração no nariz e capotamento no referencial estático.
    `place_tricycle(prefer="shortest")` usa o menor entre-eixos que cumpre a banda (perna do nariz mais curta).
    Com `ground_attitude_deg` 0 (omissão) o resultado é igual ao anterior (teste).
  * **6-DOF**: arranque na atitude e altura estáticas, contacto do nariz com a extensão, descolagem `fly_off`
    (mantém a atitude desde t0; `rotation_speed_factor` para o modo com rotação), para-choques na traseira e nas
    pontas, contagem de toques (`strikes_N`; contacto de patim dimensionado vai para `skid_contacts_N`). Um
    `aft_strike` (hélice/bordo de fuga) no mesmo voo é reportado à parte e não falha `side_load_ok`.
    Carga lateral 14 CFR 23.485 no toque em banda (`side_load_band`): tolerância numérica declarada ±5 %
    (dispersão medida do 6-DOF); `passa` só abaixo de 1 − tol, `excede` acima de 1 + tol, `no_limite` (None)
    entre os dois; `side_load_margin` sempre reportada.
    Folga traseira dinâmica (`flightsim/ground_clearance`, qualquer aeronave com contacto `aft_*`/`tail_strike`):
    folga mínima do ponto traseiro na descolagem e na aterragem, θ perto do solo, α_C descomprimido e comprimido
    (Sadraey 2012 Sec. 9.5.1.3 Eq. 9.2–9.3), com opções reportadas (limite de atitude, extensão das pernas,
    para-choques de cauda por energia Currey/Raymer 18.2) em `mission.aft_clearance`.
    Catapulta e aterragem de ventre opt-in (`assumptions.launch_recovery`, `launch_recovery.py`, verificações
    `lr:*`): curso L = V²/(2a), n_x, energia e força no shuttle (Fahlstrom, Gleason & Sadraey 2022 Cap. 17);
    energia de ventre Currey §5.3 com 14 CFR 23.473(d)/(e), deslize V²/(2μg) e folga da hélice sobre a linha do
    ventre. Limites em falta → não avaliado.
  * **Exemplo** (`uav150_flying_wing_tailless.yaml`): banda do nariz de volta a 8–15 % (Raymer; o exemplo tinha
    5–22 %), tip-back 15°, θ_g 19°, `wheelbase: shortest`, meia-bitola 0,48 m (0,554 m na montagem escalada),
    pernas 0,47/0,78 m nas Eqs. 15.50/15.51 de Raymer (mesmas alturas de fixação, pernas verticais,
    PRESSUPOSTO); elevon com 1× Volz DA 30 por lado (o DA 26 deixa de caber; curso do DA 30 sem dado →
    unassessed). Resultado: principal x 1,307 m, nariz x 0,289 m (entre-eixos 1,018 m), extensão do nariz
    0,351 m, h_cg 0,485/0,568 m (corpo/estático), nariz 14,1–15,0 %, tip-back 15,0°, rotação a partir da atitude
    23,3°, hélice 0,178 m, capotamento 53,7°, folga das pontas em torno da roda 18,6° nivelado / 11,2° na
    atitude (≥ 5°, base Torenbeek 1982 / CS 25.149). `gear:takeoff_rotation` passa: δe trim −17,7°,
    V_LOF 30,2 m/s = 1,15 V_S, margem de perda 4,3°, rolagem 293 m ≤ 300 m (o cálculo de rotação a partir da
    atitude também fecha, a 1,15 V_S, θ̈ +53 °/s² a 1,3 V_S). W0 138,6 → **150,4 kg** (trem
    principal 13,2 kg, nariz 7,4 kg), S 3,186 m², C_D0 0,02670. Fugóide nua ζ 0,041.
  * **Missão 6-DOF com o trem novo** (vento 5,2 m/s a 90°): 10,9 min, 0,239 kg. Descolagem `fly_off` 329,5 m,
    V_LOF 33,0 m/s, com toque da ponta direita (~192 N); em ar calmo 299,4 m sem toques. Toque: crab −0,21°,
    deriva 0,42 m/s, φ −1,2°, afundamento 1,06 m/s; cargas laterais 0,50× (para dentro) e 0,58× (para fora) dos
    limites 23.485 → **dentro**. Rolagem de aterragem 307 m (a atitude mantém sustentação).
  * **Bitola / patins de ponta** (12 nov 2026, ramo `tailless-tip-skids`; opt-in `gear.tip_skids`): com o vento
    cruzado a 19° de α o diedro efetivo rola a asa enquanto a elevon divide picada (−18°) e rolamento.
    Varrimento da meia-bitola: 0,554 m → toques na descolagem e ~65 N na aterragem, cargas 23.485 dentro;
    0,8 m → sem toques na descolagem, 52 N na aterragem, carga para fora ~1,5×; 1,0 m → sem toques, carga para
    fora 1,51×. **Nenhuma bitola cumpre as duas coisas**; a bitola fica a 0,554 m. Não se desce o vento
    demonstrado abaixo de 0,2 V_S0 (14 CFR 23.233(a)). O hold de rolamento no solo (já activo em fly-off e
    na rolagem) não chega com folga estática ~11°. Remédio leve: patins de ponta (`gear_devices.size_tip_skids`,
    Raymer 2018 Ch. 11 outrigger / tip gear; energia E = η N δ, Currey 1988 / Raymer Sec. 18.2 / Sadraey 2012
    Sec. 9.7; curso 25 mm, η 0,5 e 0,08 kg/lado PRESSUPOSTO). Contacto de patim dimensionado não falha
    `side_load_ok` (23.485 só no trem principal); `tip_skid_ok` / `skid_contacts_N`.
  * **Rolagem / estrutura / arrasto / Sadraey 9.5.3.2** (12 nov 2026, ramo `tailless-landing-roll-gear`;
    opt-in `gear.assess_structure`): a atitude de 19° fixa o nariz no solo, por isso a rolagem descarrega
    sustentação com a elevon ao batente após 1 s (`lift_dump`, analogia Raymer Sec. 17.9), em vez de baixar
    o nariz. Margem de atitude à perda 4,3° reportada; o critério citado é V_LOF/V_S ≥ 1,1 (Raymer 17.8).
    Rolagem de aterragem com lift-dump, no teste do exemplo: 258 m (era 307 m sem descarga).
    Área `fixed_gear` 0,03 m² (família 0,35/0,30 m) escala a 0,0516 m² com as pernas 0,47/0,78 m (factor
    1,72) — reportada, não aplicada ao polar (arriscaria 299 m ≤ 300 m). Pernas às cargas 23.485 (consola
    vertical PRESSUPOSTO, Al 2024-T3, FS 1,5). Sadraey 9.5.3.2: δ = W T³/(48 EI) com EI conservador
    (caixão à espessura mínima); δ admissível do livro não citado → deflexão reportada, passa/falha
    unassessed.
* **Ronda 2 (18 nov 2026, ramo `tailless-open-items-2`)**:
  * **C_m0 dos corpos** (`assembly/body_moment.py`): Multhopp 1942 (NACA TM 1036; Nelson 1998 Sec. 2.3;
    Tulapurkara NPTEL Eq. 2.56), C_m0,f = (k2−k1)/(36,5 S c̄) Σ w_f²(α_0L,f + i_f)Δx, com k2−k1 do esferoide de
    Lamb/Munk (NACA TR-184). Sempre reportado (`approach_consistency['bodies_cm0']`, `body_cm0_alternative`).
    Entra no trim principal só com `flying_wing.body_cm0: multhopp`; por omissão C_m0 = 0 PRESSUPOSTO.
    No exemplo dá +0,0101, e o δe de cruzeiro passaria a +15,8…+9,6°, ainda equilibrável.
  * **Rajada lateral 6-DOF** (`lateral_gust_6dof`): o critério estrito de `hq:lateral_gust` passa a ser
    aplicado ao 6-DOF em cada caso, com a taxa exigida quando o limite é tocado. No exemplo, o `cheio` falha:
    precisa de 100 °/s contra 84 °/s; os outros casos passam.
  * Itens reverificados: fugóide nua ζ 0,042 e, com manutenção de atitude, Nível 1; JSBSim NRMS β 0,02–0,06;
    taxa da elevon 99 ≤ 117 °/s; decrab com resíduo −0,3° e 23.485 0,60×/0,62×.
* **Não faz**: rigidez/curso dos servos sem dados do fabricante, C_h medido da folha superior e a c_f/c = 0,40,
  ΔC_D medido para o perfil concreto; volume da carga (sem dimensões dos itens — o packaging fino avalia o
  combustível e deixa a carga como estação candidata); passo automático de torção; inclinação contra a deriva
  no toque; catapulta ou aterragem de ventre (só mencionadas). Aplicar a área de trem escalada ao polar
  é opt-in desde 16 nov 2026 (`gear.apply_scaled_drag`, secção 32g), não ligado no exemplo. A sensibilidade ao atrito não relança o 6-DOF. O C_m dos
  corpos não é crédito de CLmax no laço W0 (no exemplo isso rebentava os 300 m); o C_m0 de Multhopp só é
  reportado por omissão.
* No gerador morfológico: dimensão extra `yaw_control` (não é semente); `split_aileron` liga a opção na
  montagem da base; regra física `yaw_control=rudder` × `tail=tailless` cortada.


## 32d-ter. GCI RANS-SA da asa sem deriva — um α (13 nov 2026)

* **O que correu**: meia asa de estibordo do exemplo tailless, controlos alinhados, sem corpo, trem ou hélice.
  Espessura NACA simétrica do loft (`naca_yt`). SU2 8.5.0 RANS-SA, três malhas pyHyp, α = 9,52057° do AVL
  para o CL de cruzeiro. Código: `hifi/wing_bl.py`. O acdt escreve a malha e o `.cfg` e chama o executável;
  não importa o pyHyp nem o SU2.
* **Decisão**: CL fino 0,87331 / CL AVL 0,50293 = 1,74, fora de [0,7, 1,5]. CMy fino −0,03595 contra Cmtot
  +0,02889, razão −1,24. As três malhas concordam no CL (0,871–0,875); o desvio não é de malha. GCI do CL
  oscilatório (U = 0,25 %). GCI do CMy = 38 %, erro iterativo não pequeno. CD do RANS não se compara com o
  CDtot invíscido. `nao_aplicar`, `eligible: false`, `valid: false`. Nenhum factor entra no L1/L2.
  `calibration.RATIO_BAND` não muda. O yaml do exemplo e o W0 não foram retocados.
* **Não correu**: polar, CLmax equilibrado, ΔCD/Cn do split, momentos de charneira, RANS do avião completo.
* **Registo**: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_wing_gci.json`. Narrativa em
  `docs/HANDOFF.md` §4 e §4b.
* **Torção do loft (14 nov 2026)**: `Surface._frames` rodava a corda por −twist. O `Ainc` do AVL é
  `twist_deg`, nariz para cima positivo, e a rotação é em torno do bordo de ataque. A ponta do cruzeiro
  media +9,994° em vez de washout. O sinal ficou o da docstring. Sanidade (torção 0°, α = 5°, malha
  grossa): CL 0,38260 / 0,36614 = 1,045, CMy e Cmtot ambos negativos. Cruzeiro corrigido, só a malha
  grossa, α = 9,52057°: CL 0,41563 / 0,50293 = 0,826 e CMy 0,03237 / 0,02886 = 1,122. Dentro de
  [0,7, 1,5], mesmo sinal no momento. `nao_aplicar`, `eligible: false`, `valid: false`: não há GCI
  novo e um α não calibra a polar. As malhas do GCI não foram reescritas. O yaml mantinha t/c 0,15/0,12
  e NACA 4415; nessa data o loft e o AVL ainda usavam 0,13/0,10. Registo:
  `examples/output/uav150_flying_wing_tailless_hifi_win/h1_twist_diagnostico.json`.
* **Verificação da geometria (14 nov 2026)**: `verify_wing_rans_geometry` mede na malha a incidência da raiz, das secções intermédias e da ponta e compara com o Ainc (tolerância 0,05°). Confirma os eixos (envergadura y, sustentação z, AOA no plano x-z, simetria em y = 0), `REF_ORIGIN_MOMENT` contra o Xref (1×10⁻⁴ m) e a área e a envergadura contra Sref/Bref (tolerância relativa 1×10⁻³). `launch_wing_rans` não arranca o caso se houver falha. O sinal do CMy, sem os dois números, fica `nao_avaliado` e não é aprovação. Não houve corrida SU2. `nao_aplicar`. As malhas do GCI de 13 nov não foram reescritas. O alinhamento do t/c está no ponto seguinte. PRESSUPOSTO: incidência em torno da envergadura local (a projecção x-z não decide); Ainc interpolado no bordo de ataque; área pela corda interior de cada painel, sem a tampa; YDUPLICATE trata a malha como meia asa.
* **Espessura declarada (14 nov 2026)**: o loft (`naca_yt`, Abbott & von Doenhoff 1959, Eq. 6.2) e o AVL usam o t/c do yaml, 0,15/0,12. A designação NACA 4415 traz 4 % de curvatura a 0,4 c; a linha média não é construída (`lacuna`, não zero). O cartão AVL é NACA 00xx. CLAF não é escrito (o guia AVL estima CLaf = 1 + 0,77 t/c e diz que a viscosidade reduz o 0,77; sem dado de secção o factor não entra). No mesmo cabeçalho e a α = 9,52057°, 0013/0010 e 0015/0012 dão CLtot 0,50293 e Cmtot 0,02886. ΔCL = 0 e ΔCm = 0 no dígito impresso. Isso não avalia a curvatura nem o RANS. `nao_aplicar`. O GCI de 13 nov continua inválido. O caixão estrutural continua a ler a designação; o OML não leva essa linha. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_seccao_avl.json`.
* **GCI v2 (15 nov 2026)**: três malhas novas (190464 / 512448 / 1451702 hex), `naca_yt` 0,15/0,12, torção certa, α = 9,52057°. A verificação de geometria passou. A fina tem uma lasca de −1,02×10⁻¹³ m³ no bordo de fuga; o piso −1×10⁻¹² m³ é explícito e o default do auditor continua a recusar volume não positivo. Publicado o final de menor rms: grossa CL 0,41702 (rms −7,23, o critério −8 não foi cumprido), média CL 0,41680 (rms −8,00), fina CL 0,41879 (rms −7,97). Celik et al. 2008, Fs = 1,25, h = (1/N)^(1/3). CL e CMy oscilam (U = 0,24 % e 0,78 %); razões 0,833 e 1,097, dentro de [0,7, 1,5], não elegíveis. CD monótono, GCI fino 22 %, e não é o CDtot do AVL. `nao_aplicar`, `valid: false`. Um α não calibra a polar. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_wing_gci_v2.json`.
* **Linha média NACA de 4 dígitos (15 nov 2026)**: `Surface.with_naca4_mean_line` constrói a linha média (Abbott & von Doenhoff 1959, Eq. 6.4–6.6) no loft, na malha de superfície e no cartão AVL. É opt-in por superfície. Por omissão o loft continua `naca_yt` simétrico e o cartão continua 00xx; o exemplo não muda. `m = 0` reproduz esse loft. `p = 0` com curvatura é recusado: não é plano nem zero. A espessura continua a ser o t/c declarado, por isso o opt-in da asa voadora escreve 4415 na raiz e 4412 na ponta. CLAF não é escrito. A malha grossa RANS com o 4415 real correu no α 9,52057°: CL 0,73034 e CMy −0,07298 contra o AVL 0,81407 e −0,07963 (razões 0,897 e 0,917, mesmo sinal). rms[Rho] −6,673 em 8000 iterações; mais 4000 com CFL 100 não chegaram a −8. `nao_aplicar`, `valid: false`. Uma malha e um α não calibram. O exemplo não muda. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_curvatura_grossa.json`.
* **Polar RANS da grossa simétrica (16 nov 2026)**: dezassete α de −2° a 24°, passo de 2° e de 1° junto da perda, na malha grossa do GCI v2. O GCI não elegeu malha. CLmax com controlos alinhados: 1,059 a 20° (CMy +0,0115, não equilibrado). CD viscoso = CD RANS − CDff AVL; CD0 = 0,0198 no ajuste até 16°. Razão para o CD0 da asa no buildup: 2,17, fora de [0,7, 1,5]. O CLmax equilibrado do L1 é 1,118 e não é a mesma grandeza. `nao_aplicar`, `valid: false`. O exemplo não muda. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_polar_grossa.json`.
* **Controlos (17 nov 2026)**: elevon selada, opt-in, η 0,20–0,45, charneira a 0,75c, na grossa de 190464 hex. δ −10°, +10° e −25°, α 9,52057°. PRESSUPOSTO: os extremos levam metade do ângulo. A split não deforma o loft; ΔCD, Cn e C_h ficam `nao_avaliado` (fenda fora da extrusão fechada; assimetria fora da meia asa). O C_hf da TN 690 não é o Ch da elevon. RANS publicado, final das 8000 iterações, rms cerca de −7,1: CL 0,31891 / 0,51329 / 0,17273 e Ch −0,000535 / −0,001614 / +0,000438 (128/128). O AVL de quatro secções dá CL 0,41633 a δ = 0, ao lado do RANS da polar (0,41702). O cartão de duas secções (0,50293) corresponde a um bordo de fuga recto, não à torção linear em graus. δ positivo sobe o CL e desce o CMy nos dois. O Ch a −10° tem o sinal oposto ao HM por lado; a razão a −25° é 0,191 e a +10° é 1,09. `nao_aplicar`, `eligible: false`, `valid: false`. Uma malha e um α não aplicam factor. Os atuadores e o yaml não mudam. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_controlos_grossa.json`.
* **CalculiX do caixão (18 nov 2026)**: o caixão malhado é o do dimensionamento actual, t/c 0,15/0,12, 6,429 kg, 3558 nós, SPOOLES, 7,64 s. k_EI = 0,571 (flecha FEM 0,05786 m, viga 0,03301 m), dentro de [0,2, 5], `valid` true, e não entra: o yaml não lista `structures` em `assumptions.calibration.apply`. k_GJ = −0,891, torção FEM −0,483° contra viga +0,430°, `valid` false. O sinal não foi invertido. O primeiro valor próprio de encurvadura linear à carga última é 0,854. Não é o RF 1,00 da pele do estudo de 12 nov (5,47 kg, t/c 0,13/0,10), que não foi repetido. A base com `hold_section`, sem re-optimizar, pesa 5,885 kg e a elevon tem η = 1,016 a 1,2 V_D, contra η = 1,088 desse estudo. O DLM p-k, grelha plana sem flap, cruza a 284,6 m/s em g = 0,03 (margem 3,89 acima de 1,2 V_D). As faixas não cruzam até 4 V_D, por isso k_flutter não é uma razão finita. A inversão por DLM fica `nao_avaliado`. O NLGEOM (`*STEP, NLGEOM` e `*STATIC`, incremento inicial 0,2, PRESSUPOSTO) converge num tubo de 20 N e, no caixão à carga última, acaba com o código 201, sem flecha. Riks fica `nao_avaliado`. `nao_aplicar`. O exemplo não muda. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h2_calculix.json`.
* **pyGeo do loft (18 nov 2026)**: a imagem `mdolab/public:u22-gcc-ompi-stable` corre em udocker 1.3.17, modo P1, sem Docker Desktop. ADflow 2.13.1, TACS 3.10.1, pyGeo 1.17.1 e MPhys 2.0.0 importam no contentor e não no processo acdt. O loft (537 pontos) entra numa caixa FFD de 6×8×4. PRESSUPOSTO: a caixa é o limite alinhado aos eixos, com 5 % de margem. Sem variável de projecto o pyGeo move os pontos 9,8×10⁻¹³ m. O caso aeroestrutural de cruzeiro fica `nao_avaliado`: não há malha de volume nem deck ADflow ou TACS. O CL 0,417 da grossa e a flecha 0,0579 m do CalculiX não são a mesma grandeza. `nao_aplicar`. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h3_mphys.json`.
* **Secção do C172 (18 nov 2026)**: quarta malha, 107922 células, α = 2°. Não é esta asa e não muda os factores. O CD não cumpre a deriva de 0,001 (`iterative_ok` false, GCI fino 3,0 %). O CL é monótono, GCI fino 1,2 %, `iterative_ok` true, e um α não calibra a polar. O RANS da asa com fuselagem não coube: 21,7 GB pela fórmula, limite 13,7 GB. `nao_aplicar`. Registo: `examples/output/cessna172_check_hifi_win/h5_c172_gci.json`. Nova medição no mesmo dia, ramo `c172-rans-asa-fuselagem`: 16,32 GB livres, limite 11,42 GB, a fórmula mantém 21,731 GB e 40,24 h. O solver não arrancou. O restart do SU2 fica planeado e sem bloco de iterações. A polar L1 e o POH do exemplo não são CL, CD e Cm desta malha, por isso a comparação fica `nao_avaliado` e o L1 não fica validado nem calibrado. Registo: `h5_c172_rans_asa_fuselagem.json`.
* **RCS com duas reflexões (18 nov 2026)**: o loft com torção de ponta −10° (bordo de fuga 72 mm acima do bordo de ataque), t/c 0,15/0,12, sem linha média. PO a 10 GHz, |az| ≤ 30°, elevações −5°, 0° e 5°, oclusão ligada, 192 facetas. Uma reflexão: média −10,03 dBsm, e VV coincide com HH. Duas reflexões: média VV −7,49 dBsm e HH −9,73 dBsm. O máximo fica perto de 8 dBsm nos dois. Fuselagem, derivas de ponta, trem, hélice, deflexão e difracção de bordo ficam `nao_avaliado`. A onda completa (MoM/MLFMM ou FDTD) não correu. `nao_aplicar`. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h6_rcs_bounces2.json`.
* **Painel grosso VSPAERO no Windows (18 nov 2026)**: OpenVSP 3.56.0, `vspaero.exe` noutro processo, 4 threads, 2,19 s. Asa voadora, tess 41×16, GeomSet `SET_ALL`, ThinGeomSet `SET_NONE`. Esteira lida de volta: WakeNumIter 5, NumWakeNodes 8, WakeRelax 1, FixedWakeFlag 0, ImplicitWake 0 (default desta versão; o CHANGELOG 3.45.0 descreve a esteira implícita). Dois `MeshGeom` do CompGeom foram apagados antes do solver: com eles no `SET_ALL` a história era não finita. Iteração 5: CL 0,52862, CDi 0,024897, CDtot 0,039919, CMytot 0,035399, CDiw 0,019933, L2 −0,695. AVL desta corrida: CL 0,50293, CDff 0,014536, Cmtot 0,02886. Razões CL 1,051 e Cm 1,227, mesmo sinal. CDi/CDff 1,713 fica fora de [0,7, 1,5]. CDiw/CDff 1,371 é outra grandeza. Cinco iterações não são convergência. `nao_aplicar`, `valid` false. O AVL L1 não fica validado nem calibrado. O yaml não muda. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h7_vspaero_painel.json`.
* **OpenVSP e VSPAERO (18 nov 2026)**: nesse registo o Windows ainda não tinha o instalador. A exportação é o OpenVSP 3.48.2 do contentor. O visor do VSPAERO falta nessa imagem. O gestor de análises escreve o caso e pára; o binário corre à parte, porque o lançamento pelo gestor não regressa. A asa voadora lê a torção de ponta −10° em torno do bordo de ataque (bordo de fuga 72,1 mm acima) e ThickChord 0,15/0,12. A pele da STL, numa estação a 40 % da corda, tem dz/c 0,145 na raiz. O painel grosso carregou e morreu ao ligar a esteira, sem coeficientes. A superfície fina, no α 9,52057° do cartão AVL de duas secções, deu CL 0,49394, CDi 0,014302 e CMytot 0,04164, contra CL 0,50293, CDff 0,014536 e Cmtot 0,02886. Razões 0,982, 0,984 e 1,443, o mesmo sinal no momento. Cinco iterações de esteira, com residual L2 ainda a descer, não são uma convergência. A malha 41 por 16 não é a malha AVL 12 por 40. Rho e Vinf ficaram nos defaults do solver. O C172 foi lido (2412, z 0,529 m, incidência 0) e o VSPAERO do C172 não correu. As áreas molhadas do 3.48.2 são cerca de metade das do 3.55.0 já guardadas; a unidade lida é o metro e a diferença de versão não é uma exportação falhada. `nao_aplicar`. A banda do H1 não entra. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h7_openvsp.json`.

## 32e. Trem convencional / esquis / pernas / cinemática — L0 opt-in (9 nov 2026)

* **API**: `assumptions.assembly` gear block / integration `gear.type`: `tricycle` (default) |
  `taildragger`|`conventional`|`tailwheel` | `ski` | `none`. Unknown type → **unassessed** (never a
  silent tricycle substitute). Named types remain shortcuts assembling generic components.
* **Taildragger** (`assembly/gear_devices.layout_taildragger`): Raymer Ch. 11 main-ahead tip angle,
  overturn about the tail wheel (aft CG), tail load share *reported* (8–15 % band is tricycle-only),
  propeller clearance **9 in** (14 CFR 23.925(a)(1) tail-wheel). Fixed-type `analyse_landing_gear`
  already had taildragger; assembly mesh path is new.
* **Ski**: requires `gear.ski.length_m` (optional `attach_x`, `thickness_m`). Missing length →
  unassessed. Fore/aft contacts for tip-back / overturn / prop clearance (Raymer Ch. 11 alternate
  landing device; Currey 1988). No snow dynamics.
* **`draw_legs: true`**: Body pods `role: gear_leg` (strut cylinders, PRESSUPOSTO diameter 0.06 m)
  for CAD/STEP/DXF via `leg_drawing_lines` / `append_gear_lines_to_drawing`.
* **`retract`**: geometric wheel-centre arc about supplied hinge/axis/angle; interference with
  structure/discs → `asm:gear_retract`. Missing path → unassessed. No FEM / mechanism dynamics.
* **`tip_skids`** (opt-in, 12 nov 2026): wing-tip shoes sized by E = η N δ (Currey 1988 / Raymer
  Sec. 18.2 / Sadraey 2012 Sec. 9.7) for a narrow-track layout (Raymer Ch. 11 outrigger / tip gear).
  See §32d-bis for the tailless example.
* **`assess_structure`** (opt-in, 12 nov 2026): scale the lumped `fixed_gear` area with strut
  length; check vertical legs under 14 CFR 23.485; report Sadraey 9.5.3.2 mid-span deflection.
  See §32d-bis.
* Examples: `examples/integration/conventional_taildragger.json`, `ski_gear_demo.json`.
* Tricycle path and examples that omit the new options stay unchanged.


## 32f. Formas de equipamento + corpos rodados no AVL — L0 opt-in (9 nov 2026)

* **Item.shape**: `box` (default) | `sphere` | `cylinder` (+ `cylinder_axis: x|y|z`). Open primitives for
  packaging samples, FOV occlusion mesh (`_item_body`), volume and inertia (Meriam & Kraige solid +
  Steiner). AABB separation stays conservative. `protuberance_shape` (Hoerner) remains independent for drag.
* Existing box items unchanged when `shape` is omitted.
* **Rotated Body in AVL**: AVL BODY is always along aircraft x (avl_doc.txt slender bodies). Non-zero
  `orientation` → body omitted from BODY **and** from Torenbeek App. E fuselage shift; `bodies_avl_status`
  / `asm:avl_bodies` / (when `np_source: avl_bodies`) `asm:static_margin` → **unassessed**. Never an
  axis-aligned stand-in.
* Example: `examples/integration/shapes_and_rotated_body.json`.

## 32g. Arrasto do trem no polar e opções da corrida de descolagem — L0/L1 opt-in (16 nov 2026)

* **Arrasto do trem** (`aero/gear_drag.py`): o trem é um (D/q)_misc do C_D0 (Raymer 2018 Eq. 12.24). A área é
  dado do utilizador (`aero.extra_drag_areas_m2`). Trem fixo: a área dada entra sempre no polar (como antes).
  `gear.apply_scaled_drag: true` (bloco do trem da montagem, incluindo `options.flying_wing.gear`) ou
  `aero.gear_drag.scale_with_legs: true` soma a diferença da área escalada com ΣL das pernas
  (`gear_devices.scale_fixed_gear_drag_area`), uma só vez. Sem comprimentos das pernas fica unassessed.
  `aero.gear_drag.retractable: true`: o trem sai do polar de cruzeiro e entra como ΔC_D0 = Σ(D/q)/S só com trem em
  baixo (descolagem/aterragem; Raymer 2018 Sec. 17.8), em `PerfModel`, na restrição de corrida e no MDO.
  Linha `aero:gear_drag`, `res.gear_drag`.
* **Opções da corrida de descolagem** (`flightsim/takeoff_options.py`): quando a corrida da missão 6-DOF passa
  o requisito `takeoff_ground_roll` (ou com `mission.takeoff_options: true`). A corrida de massa pontual usa as
  forças do modelo de voo (Raymer 2018 Sec. 17.8, μ Table 17.1; fly-off Sadraey 2012 Sec. 9.6.2 ou V_LOF = 1,1
  V_S). k = 6-DOF/massa pontual é constante entre opções (PRESSUPOSTO). Opções: vento de frente/rumo da pista,
  tração, carga alar, massa, atitude de descolagem (limites δe, V_LOF ≥ 1,1 V_S e α_C da folga traseira),
  catapulta (`launch_recovery`) e menos vento cruzado demonstrado (não admissível abaixo de 0,2 V_S0, 14 CFR
  23.233(a)). Vento de frente e tração são re-voados no 6-DOF até fechar. Saída em
  `mission['takeoff_options']` e `takeoff_options.md`.
* **Exemplo sem deriva** (Linux): +0,0216 m², ΔC_D0 +0,00683 na S da base. Com a aeronave fixa, 6-DOF em ar calmo
  296 → 305 m e com vento cruzado 325 → 334 m. Redimensionado: W0 161,7 kg e 6-DOF com vento cruzado 299,4 m. Não
  ligado no exemplo (decisão do projetista). Corrida com vento cruzado 325,1 m contra 300 m: fecham o vento de
  frente ≥ 1,35 m/s (6-DOF), a tração ×1,066 (6-DOF), S ×1,079 e −4,9 kg. A atitude não fecha (mínimo 322 m) e a
  catapulta fica unassessed sem o bloco. Nada aplicado ao exemplo.
* **Não faz**: divisão roda/perna da área; massa do mecanismo de retração; trem retráctil em baixo no 6-DOF;
  novo ciclo W0 para as opções.

## 32h. Qualidade de software: CI Linux + Windows, mypy gradual, cobertura (16 nov 2026)

* **CI (GitHub Actions, `.github/workflows/ci.yml`):** `ubuntu-latest` e `windows-latest`, Python 3.13, `pytest -n
  auto` com cobertura, cache do pip. AVL instalado nos dois SO (Linux compilado da fonte oficial 3.40b como a cópia
  de desenvolvimento; Windows o binário oficial WIN64), JSBSim pelo extra `sim`, sempre fora do processo.
* **Marcadores `requires_avl` / `requires_xfoil` / `requires_jsbsim`** (`tests/conftest.py`): sem a ferramenta o teste
  salta com o motivo; a sessão imprime a contagem de saltos por motivo (e escreve-a no resumo do job).
  `ACDT_REQUIRE_TOOLS=avl,jsbsim` torna esses saltos em falhas — nunca verde-por-salto.
* **mypy** estrito num subconjunto (`core/atmosphere`, `core/units`, `core/requirements`, `aero/gear_drag`), job
  obrigatório; plano para alargar em `docs/QUALIDADE.md`.
* **Cobertura** (pytest-cov, XML + resumo, sem limiar): linha de base 82 % no Linux.
* **Política de tolerâncias** entre plataformas: comparação na mesma compilação + bandas de sanidade (PRESSUPOSTO)
  para valores absolutos de ferramentas externas.
* **Não faz:** XFOIL, Gmsh, CalculiX, SU2, OpenVSP e CadQuery não correm na CI (os testes saltam e são contados);
  sem limiar de cobertura; mypy não cobre o pacote inteiro.

## 32i. Proveniência dos resultados (16 nov 2026)

* **O que faz**: cada corrida que escreve resultados deixa um registo `acdt.provenance/1` ao lado deles
  (`acdt/core/provenance.py`), sem mudar nenhum número. Uma pasta de saída recebe `provenance.json`; um ficheiro
  `x.json` recebe `x.provenance.json`; uma corrida MCP guarda-o em `run.json` (chave `provenance`). O registo tem:
  * versão do acdt, *commit*, ramo, árvore suja e SHA-256 do `git diff HEAD` quando está suja;
  * Python e versões das bibliotecas que mexem nos números (numpy, scipy, OpenMDAO, OpenAeroStruct, NeuralFoil…);
  * SO, versão e arquitectura;
  * cada executável externo **usado** (AVL, XFOIL, SU2, CalculiX, Gmsh, mpirun, intérpretes de JSBSim/CadQuery/
    OpenVSP): caminho, SHA-256 do binário, tamanho, data e versão quando há opção não-interactiva (Gmsh, CalculiX;
    o AVL e o XFOIL são interactivos, a identidade é o hash);
  * SHA-256 canónico das entradas YAML/JSON (comentários, ordem das chaves e espaços não contam) e dos bytes;
  * sementes (`--seed` e afins), instante em UTC e Europe/Lisbon, comando, argumentos e pasta de trabalho;
  * manifesto da pasta de saída (SHA-256, tamanho, escrito nesta corrida ou não).
* **Onde se liga** (pontos centrais): `acdt.cli.main` (um âmbito por subcomando), `run_pipeline(output=…)`,
  `run_hifi`, `hifi.tools.run` (pasta de cada caso SU2/CalculiX/Gmsh/OpenVSP) e o registo MCP. As chamadas ao AVL,
  XFOIL, JSBSim e CadQuery registam o executável com `tool_used`.
* **CLI**: `acdt provenance show <saída>`, `acdt provenance capture [-o f.json]` (identidade desta máquina sem
  correr análises), `acdt provenance diff A B` (explica porque dois resultados podem diferir: binário diferente,
  SO, árvore suja, commit, entradas, sementes, bibliotecas; código de saída 0 se a proveniência é a mesma).
* **Fidelidade**: — (rastreabilidade). Sem rede. `ACDT_PROVENANCE=0` desliga a escrita.
* **Limites**: as ferramentas de uma corrida MCP são as usadas pelo processo até ao fim dela (majorante quando há
  corridas em paralelo); a verificação da geometria RANS (`hifi/wing_bl.py`, AVL) e os JSON escritos por scripts
  fora da CLI/pipeline/hifi só ficam cobertos quando passam por estes pontos; os ficheiros de `examples/output`
  já guardados não têm registo até serem regenerados.

## 32j. Requisitos rastreáveis e matriz de verificação (16 nov 2026)

* **O que faz**: cada requisito tem um ID estável, texto, origem (missão, regulamento, norma, SORA, utilizador,
  derivado), pais, grandeza/unidade/comparação/limiar (+ objetivo), tolerância, método de verificação (análise,
  simulação, ensaio, inspeção, demonstração, revisão — NASA/SP-2016-6105 Rev2, ECSS-E-ST-10-02C), fidelidade
  exigida (N0…N3) e o avaliador que o verifica (`acdt/core/verification.py`, formato `acdt.verification/1`).
* **Estados**: `passa`, `falha`, `no_limite` (dentro da banda ±max(tolerância declarada, resolução do avaliador)),
  `nao_avaliado` (sem avaliador, etapa não correu, fidelidade abaixo da exigida), `desconhecido` (correu sem
  valor/veredicto). Nunca passa sem o avaliador ter corrido.
* **Saída**: etapa final do pipeline aircraft → `verification_matrix.{json,md,csv}` na pasta de saída, com valor,
  margem, avaliador, evidência (`result.json#caminho` + SHA-256) e impressão digital da proveniência (§32i).
  `acdt verify MISSAO PASTA [--all] [--strict]` reavalia uma pasta já corrida.
* **Árvore e cobertura**: pais/filhos (pai sem avaliador = pior estado dos filhos), IDs repetidos, pais desconhecidos,
  ciclos; requisitos sem avaliador, avaliadores não registados, evidência calculada sem requisito.
* **Avaliadores aircraft**: `check:<chave>` (res.checks), `perf:<requisito>` (missão por segmentos), `sizing:stall_speed`
  (Raymer Eq. 5.6), `entrada:<requisito>` (por construção); núcleo: `resultado:<caminho>`, `ficheiro:<rel>#<caminho>`.
  Omissões por chave da missão; YAML: campos de rastreabilidade em `requirements:` e `verification.requirements:`.
* **Exemplos**: C172 (15 requisitos) e asa voadora sem deriva (20 requisitos: 11 passa, 3 no_limite, 4
  nao_avaliado, 2 desconhecido). Pormenor em [docs/REQUISITOS.md](docs/REQUISITOS.md).
* **Fidelidade**: — (rastreabilidade); não muda nenhum número.
* **Limites**: as saídas de `acdt simulate`/`certify`/`integration` não são ligadas automaticamente (SORA, FOV e a
  corrida 6-DOF ficam `nao_avaliado` nos exemplos); chaves sem avaliador por omissão (max_speed, turn_rate, …).

## 32k. Incerteza e sensibilidade como camada de primeira classe (16 nov 2026)

* **O que faz**: `acdt uq MISSAO [--spec UQ.yaml] -o PASTA` declara qualquer parâmetro da missão como incerto
  (`normal`, `lognormal`, `uniform`, `triangular` ou `interval`, com `source` obrigatório ou `pressuposto`
  marcado; correlações de postos opcionais, Iman & Conover 1982), propaga por MC ou LHS com semente (registada na
  proveniência), dá P5/P50/P95 com IC (Conover 1999), média corrida e convergência SE/média, e calcula **P(passa)**
  de cada requisito da matriz de verificação com IC de Wilson e um **estado probabilístico** novo (`prob_passa`,
  `prob_falha`, `inconclusivo`, `nao_avaliado`, `desconhecido`); o estado determinístico não muda.
* **Sensibilidade global**: Sobol' nas distribuições declaradas, várias saídas de um desenho (S1 de Saltelli et al.
  2010, ST de Jansen 1999, IC por bootstrap) e Morris (Morris 1991; μ* de Campolongo et al. 2007) para rastreio.
* **Intervalos** (sem distribuição): ciclo exterior nos extremos → resultados e P(passa) em [mín, máx] (Ferson et al.
  2003; Oberkampf & Roy 2010 Cap. 13).
* **Calibração**: fatores de alta fidelidade aplicados entram como incertos com ±GCI fino (Celik et al. 2008) ou
  U_osc (Stern et al. 2001); H1 `nao_aplicar` e fatores sem GCI ficam listados como não propagados.
* **Substituto**: superfície de resposta quadrática por saída, aceite só com Q² (PRESS, Allen 1974) ≥ limiar
  declarado; saídas rejeitadas e requisitos não numéricos usam as amostras de treino do modelo verdadeiro.
* **Saída**: `uq.json` (`acdt.uq/1`), `uq.md`, PNG, `verification_matrix.*` com `p_passa`/`estado_probabilistico`.
* **Fidelidade**: a do pipeline L0/L1 por amostra (declarada, ou `--fidelity handbook`); verificado contra Ishigami
  (índices analíticos), Morris linear exato e P(passa) normal analítica (`tests/test_uq.py`).
* **Já existia** (§27, inalterado): OAT, Sobol' uniforme de uma saída, MC/LHS e `uq_interval_checks` do gate N1.
* **Limites**: o modelo por amostra não inclui `simulate`/`certify`/`integration`; Sobol' e o treino do substituto
  ignoram correlações; intervalos só nos extremos. Pormenor em [docs/INCERTEZA.md](docs/INCERTEZA.md).

## 32l. MDO global de sistema com Pareto (16 nov 2026)

* **O que faz**: `acdt mdo MISSAO [--spec MDO.yaml] -o PASTA` constrói em OpenMDAO um problema de otimização ao
  nível do sistema a partir de YAML: variáveis de projeto por caminho da missão (contínuas, inteiras ou discretas —
  qualquer valor YAML, p. ex. o tipo de propulsão), um ou vários objetivos (métricas, `req:<ID>`, derivadas por
  expressão segura, robustas), **restrições geradas do registo de requisitos** (#74; margem relativa de
  `classify` com o limiar e a tolerância de cada avaliação; políticas `limiar`/`passa`/`no_limite`; não numéricos
  ficam como filtros reportados) e limites em métricas. Cada avaliação guarda o estado de cada requisito.
* **Estratégias**: SLSQP (`ScipyOptimizeDriver`, diferenças finitas do sistema em lote paralelo); ε-restrição com
  SLSQP (Haimes, Lasdon & Wismer 1971); NSGA-II próprio como driver OpenMDAO (Deb et al. 2002; dominância com
  restrições; SBX/mutação polinomial); `SimpleGADriver` (1 objetivo, discretas); `DOEDriver` (LHS/fatorial). Frente
  não dominada de todas as avaliações viáveis e joelho (Das 1999; ≥3 objetivos: Zeleny 1973).
* **Ciclo exterior + fecho**: discretas no ciclo exterior (produto completo ou lista); fecho por iteração de ponto
  fixo de uma variável discreta (frota ↔ propulsão ↔ projeto, regra do workflow N0/N1) com estado `convergiu` /
  `ciclo` / `desconhecido` / não convergiu.
* **Robusto (barato)**: média + k·σ e P(passa) ≥ alvo sobre o substituto quadrático de `acdt uq` (Q² por PRESS).
* **Saída**: `mdo.json` (`acdt.mdo/1`), `mdo.md`, `evaluations.csv`, `pareto.png`, `verification_matrix.*` do
  projeto escolhido e `provenance.json` com as sementes.
* **Verificação**: Sellar (ótimo publicado 3,18339), ZDT1 (hipervolume), ε-restrição com frente analítica, robusto
  com ótimo analítico, fecho 1 → 2 aviões, pipeline real (`tests/test_mdo_system.py`).
* **Já existia** (§9, inalterado): `acdt optimize` = MDF dentro do dimensionamento (W/S, P/W, AR; região de
  confiança; catálogo); Paretos dedicados (aero/RCS, W0–custo, morfologia); `acdt fleet study` sem laço frota→projeto.
* **Limites**: diferenças finitas sobre um pipeline com ruído ~1e-7; cada avaliação da montagem + AVL custa minutos
  (no box: handbook, poucas variáveis, orçamentos pequenos); 6-DOF/SORA/FOV continuam `nao_avaliado` no modelo por
  avaliação. Pormenor em [docs/MDO.md](docs/MDO.md).

## 32m. Biblioteca de V&V como produto (17 nov 2026)

* **O que faz**: `acdt vv [--cost barato|medio|pesado] [--case ID] [--discipline D] -o PASTA` corre um registo de
  casos de referência publicados por disciplina (atmosfera, sensibilidade, MDO, estruturas, EM, aerodinâmica,
  cargas, dimensionamento) e escreve `vv_report.json` (`acdt.vv/1`) + `vv_report.md` com passa/falha/
  nao_avaliado/desconhecido por grandeza e por caso, versão e impressão digital do registo e proveniência.
* **Cada caso**: enunciado, tipo (verificação/validação, Oberkampf & Roy 2010), valores com citação completa,
  tolerância declarada a priori com justificação, avaliador do acdt, custo e ferramentas exigidas. O registo
  recusa casos sem citação ou sem tolerância.
* **Casos (registo 2026.11.17)**: 22, todos a passar no box — ISA (3), Sobol' Ishigami, Sellar, ZDT1, consola
  (viga e cascas), encurvadura de placa, SP-8007, 9 casos PO canónicos, linha sustentadora elíptica, 14 CFR 23.337
  e a validação conceptual do C172S (custo médio).
* **CI**: job `vv` (casos baratos, relatório como artefacto); `tests/test_vv.py`.
* **Limites**: pouca validação contra dados físicos (só o C172S); XFOIL/AVL/POH de desempenho ficam de fora até
  haver valores publicados transcritos com fonte. Pormenor em [docs/VV.md](docs/VV.md).

## 32n. Estado de projeto único com unidades (18 nov 2026)

* **O que faz**: um ficheiro `design.json` com esquema versionado `acdt.design/1` (JSON Schema em
  `src/acdt/core/data/design.schema.json`). Guarda a definição (entrada YAML, SHA-256 e requisitos em SI), os
  resultados por disciplina e nível L0…L3 (método, referências, origem, evidência e proveniência por bloco), a
  matriz de verificação e a incerteza por grandeza, quando é conhecida.
* **Grandezas**: cada uma tem unidade explícita em sintaxe pint, `"1"` para adimensional declarado ou `null` para
  não declarada (nunca se presume adimensional). `value: null` quer dizer desconhecido, nunca zero.
* **Unidades na entrada** (pint, BSD-3-Clause): requisitos e `assumptions` aceitam `"150 kg"`, `"27 m/s"` ou
  `{value, unit}`. Os valores são convertidos para o SI dos requisitos ou para a unidade que o sufixo da chave
  declara (`_m`, `_kg`, `_in`, …), e uma dimensão errada dá um erro claro com o caminho. Os YAML sem unidades
  continuam iguais, verificado sobre todos os exemplos.
* **CLI**: `acdt db show | get | diff | export | build | validate | add-uq`. `acdt size -o PASTA` escreve
  `design.json` e continua a revisão; `acdt verify` atualiza a matriz. O `diff` converte unidades e assinala as
  mudanças de unidade e de fidelidade.
* **Fidelidade**: — (dados). Não muda nenhum número do dimensionamento.
* **Integrado**: o pipeline aircraft (todas as etapas), a matriz de verificação e `acdt uq`, por `db add-uq`,
  com envelope para entradas epistémicas.
* **Por fazer**: `acdt mdo` (ótimo e Pareto como blocos L2), `acdt vv`, os blocos L3 das ferramentas de alta
  fidelidade, e unidades declaradas para as chaves de resultado sem sufixo. Pormenor em
  [docs/DADOS.md](docs/DADOS.md).

## 32o. Dados de ensaio e calibração de modelos (18 nov 2026)

* **O que faz**: ingere dados medidos e calibra fatores e parâmetros dos modelos contra eles, com incerteza,
  gama de validade e uma decisão explícita `aplicar`/`nao_aplicar`, tomada contra critérios de aceitação
  declarados. Nunca se aplica fora da gama de validade.
* **Ingestão** (`acdt.testdata/1`):
  * formatos CSV, Parquet e PX4 ULog (pyulog, BSD-3-Clause), com unidades pint por canal;
  * metadados obrigatórios (origem, data, tipo, condições, instrumento);
  * incerteza de instrumento conforme o GUM, e SHA-256 do ficheiro;
  * o ArduPilot `.bin` não é lido no processo, porque o pymavlink é LGPL: converte-se para CSV fora do processo.
* **Métodos**:
  * mínimos quadrados ponderados (Bard 1974; Seber & Wild 1989), com variância efetiva para entradas incertas
    (Orear 1982), σ pelos resíduos quando não é declarado, escala de Birge e IC t de Student;
  * Kennedy & O'Hagan (2001) leve: discrepância PG + MAP/Laplace modular (Bayarri et al. 2007), com prior
    obrigatório.
* **Registo** (`acdt.calib/1`): fatores ± σ, IC 95 %, covariância e correlação, resíduos por ponto, gama de
  validade e critérios avaliados.
* **Exportações**: fatores no formato de `assumptions.calibration.file` (mesmas regras de opt-in dos fatores da
  Fase 4), overlay de `assumptions`, entradas normais e correlacionadas para `acdt uq`, e bloco
  `results.calibracao.<nível>` com `fidelity: ensaio` no `design.json`.
* **CLI**: `acdt calib ingest | fit | show | export | db`.
* **Fidelidade**: ensaio (dados). Não muda nenhum número do modelo enquanto o utilizador não ativar o grupo ou
  o overlay.
* **Validado**: testes com dados sintéticos de fatores verdadeiros conhecidos:
  * recuperação dentro da incerteza;
  * cobertura empírica do IC 95 % em 200 réplicas;
  * KOH com discrepância de forma.

  Com o ponto publicado do C172S (V_S0), ν = 0, por isso a incerteza fica desconhecida e a decisão é
  `nao_aplicar`.
* **Por fazer**: o modelo do acdt diretamente como η(x, θ) dentro do ajuste; MCMC/emulador para KOH;
  alinhamento de tópicos ULog e segmentos estabilizados; dados de ensaio reais. Pormenor em
  [docs/CALIBRACAO.md](docs/CALIBRACAO.md).

## 32p. API pública versionada, documentação gerada, CLI coerente e notebooks (18 nov 2026)

* **O que faz**: dá ao acdt uma porta de entrada estável para scripts, notebooks e outras ferramentas, com
  versionamento semântico verificado por teste, documentação gerada do código e uma CLI com convenções comuns.
* **API Python `acdt.api`** (API 1.2.0 desde §32r — `rotor_noise`; 1.1.0 desde §32q; pacote 0.2.0):
  * `load_mission`, `size`, `analyse`, `verify`, `uq`, `uq_study`, `mdo`, `mdo_study`, `function_model`,
    `vv_cases`, `vv`, `calibrate`, `load_test_data`, `db_load`/`db_save`/`db_get`/`db_diff`/`db_validate`,
    `version_info`, `errors`;
  * resultados em `dict`/`list` serializáveis; desconhecido = `None`; `level` L0/L1/`None` igual a `acdt size`;
  * `function_model` torna qualquer função Python num modelo de sistema com requisitos rastreáveis, para UQ e MDO
    genéricos.
* **Versões e descontinuação**: `api_surface.json` fixa as assinaturas; o teste falha se uma assinatura mudar ou
  um nome sair sem subir a MAIOR, ou se um nome entrar sem subir a MENOR. `deprecated(since, removed_in=,
  alternative=)` emite `ACDTDeprecationWarning` e só deixa remover numa MAIOR.
* **CLI**: `acdt --version`; `--help`, `--json` (envelope `acdt.cli/1` em stdout, texto humano em stderr) e
  `--debug` em todos os comandos; códigos de saída documentados (0 sucesso, 1 falha avaliada, 2 entrada,
  3 indeterminado, 4 erro interno, 130 interrompido).
* **Documentação**: MkDocs + mkdocs-material + mkdocstrings (BSD-2/MIT/ISC); referência da API a partir das
  docstrings e da CLI a partir do próprio parser; guia do utilizador com as páginas pt-PT; job `docs` no CI
  (`mkdocs build --strict`) e workflow do GitHub Pages pronto mas inativo até ativar o Pages.
* **Notebooks** (`examples/notebooks/`): dimensionamento rápido L0, incerteza + verificação (Ishigami, Sobol'
  contra o analítico), MDO NSGA-II na ZDT1 com a frente verdadeira; guardados sem saídas e executados no CI
  (nbmake).
* **Fidelidade**: não muda nenhum resultado de engenharia; é uma camada sobre as funções existentes.
* **Validado**: `tests/test_api.py` (estabilidade, regras de versão, descontinuação, contratos de `size`/
  `verify`/`db`/UQ/MDO), `tests/test_cli_contract.py` (todos os comandos com `--help`, `--json`, códigos de
  saída) e `tests/test_notebooks.py`; os três notebooks correm em ~20 s.
* **Por fazer**: alargar a API a sistemas, fabrico/custo, certificação e simulação; `result` estruturado no
  `--json` dos restantes comandos; documentação por versão da API. Pormenor em [docs/API.md](docs/API.md).

## 32q. Relatórios automáticos de revisão de projeto SRR/PDR/CDR (18 nov 2026)

* **O que faz**: `acdt report <design.json|pasta> --level SRR|PDR|CDR` gera o relatório da revisão a partir do
  estado de projeto (`acdt.design/1`) e dos registos de verificação, proveniência, UQ, MDO, V&V e calibração, em
  Markdown, HTML autónomo e JSON (`acdt.review/1`). O PDF é opcional, com WeasyPrint (BSD-3-Clause), se estiver
  instalado. Termina num **veredito calculado**: `pronto`, `nao_pronto` ou `insuficiente`, com os códigos de
  saída 0, 1 e 3.
* **Norma**: NASA NPR 7123.1D (2023, Alteração 2), Apêndice G. Usa a Tabela G-4 para a SRR, a G-6 para a PDR e
  a G-7 para a CDR. Os excertos são literais e foram conferidos com o NODIS.
  * Os critérios estão declarados como dados (`acdt/core/review/criteria.py`). Cada um tem um avaliador
    automático, que dá `cumpre`, `nao_cumpre` ou `insuficiente`, ou fica para `revisao_humana`.
  * A ligação entre o texto da NPR e o teste é uma interpretação do acdt (PRESSUPOSTO), apoiada na adaptação
    que o G.1.2 prevê.
* **Conteúdo do relatório**:
  * conformidade com os requisitos nos cinco estados, sem nunca contar `nao_avaliado` como passa;
  * resumo do projeto com unidades;
  * fidelidade por disciplina e o que ainda está em L0/L1;
  * itens em aberto e riscos (não avaliados, PRESSUPOSTOs, calibração sintética, fora da validade ou
    `nao_aplicar`, V&V em falha, P(passa) abaixo do alvo, grandezas sem unidade, evidência alterada);
  * incerteza (P5/P50/P95, P(passa) com intervalo de confiança);
  * frente de Pareto do MDO;
  * rastreabilidade com SHA-256 (confere, difere, sem_registo, em_falta);
  * figuras já produzidas.
* **Adaptação por projeto** (`--criteria`): nível exigido, disciplinas primárias, grandezas de resumo, dispensas
  de requisitos e adaptação de critérios. Dispensas e adaptações exigem justificação.
  * PRESSUPOSTO: o nível exigido por omissão é L0 na SRR, L1 na PDR e L2 na CDR.
* **Genérico**: o domínio só regista um perfil (`register_profile`); o do aircraft está em
  `domains/aircraft/review_profile.py`. Sem perfil, todas as disciplinas do estado de projeto são primárias.
* **API**: `acdt.api.report(...)` (API 1.1.0) e `--json` com o envelope `acdt.cli/1`.
* **Fidelidade**: não muda nenhum resultado de engenharia; só lê registos.
* **Validado**: `tests/test_review.py` (17 testes), incluindo o relatório de referência byte a byte de um
  exemplo analítico pequeno (`tests/data/review_small/`).
* **Por fazer**:
  * gerar figuras em falta;
  * MDR/SDR, TRR e PRR;
  * registo de decisões e `acdt certify` como evidência;
  * ficha RID/RFA.

  Pormenor em [docs/RELATORIOS.md](docs/RELATORIOS.md).

## 32r. Ruído acústico de hélices e rotores — L0 (18 nov 2026)

* **O que faz**: etapa `noise` do pipeline (depois do desempenho) para aviões a hélice com mapa BEMT
  (`assumptions.propulsion.propeller`): ponto de funcionamento de sobrevoo (empuxo = arrasto a W0 na perna de
  espera ou cruzeiro) e de subida a V_y. Calcula L_p e L_A na vertical, **L_A,max** e **L_AE** de uma passagem,
  espectro por componente e **alcance de deteção auditiva** (silêncio e, opcional, ruído ambiente em 1/3 de
  oitava). Opcional: verificação de **14 CFR 36 Ap. G** (limite G36.301 e altura de referência G36.111, microfone
  sobre placa). `acdt.api.rotor_noise` avalia rotores dados explicitamente (multirrotor, VTOL, hélice sem mapa).
* **Métodos**: tons de carga de Gutin (1936; Garrick & Watkins 1954; Marte & Kurtz 1970 Eq. 1), banda larga de
  vórtices de Schlegel, King & Mull (1966; Marte & Kurtz 1970 Eq. 3, Fig. 10a), absorção ISO 9613-1, ponderação A
  IEC 61672-1 (Eq. E.6), limiar de audição ISO 226:2003 (T_f), Doppler (Marte & Kurtz Ap. C).
* **Fidelidade**: L0. Gutin estático; fontes de espessura, motor, célula e interação não modeladas, por isso
  **nível e alcance são limites inferiores**: um requisito máximo excedido falha, um cumprido fica desconhecido até
  o utilizador declarar `noise.other_sources` com justificação (ou juntar `noise.engine_noise` medido). Avisos de
  validade para M_tip < 0,5 e M_tip helicoidal > 0,8.
* **Integração**: secção `noise` no `result.json`; disciplina `ruido`/L0 no `design.json`; requisitos `noise` e
  `aural_detection_range` e avaliador `ruido:<grandeza>` na matriz; verificação `noise:part36_G`; métricas de UQ e
  MDO por `result_metrics` (p. ex. `noise.overhead_LAmax_dBA`) ou `req:<ID>`.
* **V&V**: `NOISE-SKM-EXAMPLE` (exemplo de Marte & Kurtz 1970), `NOISE-AWEIGHT` (IEC 61672-1 Tab. 3),
  `NOISE-ISO9613-ALPHA` (tabela de α ISO 9613-1), `NOISE-P36G-LIMITS` (G36.301) — todos passam. Sem caso de
  validação contra medições ainda.
* **Validado**: `tests/test_noise.py` (forma SI de Gutin contra a forma inglesa, V&V, deteção, semântica de
  limite inferior, pipeline C172 com Parte 36, API).
* **Limites**: jatos não avaliados; Hamilton Standard/SAE AIR1407, Hanson, Fidell (deteção de sinais) e ICAO
  Anexo 16 Cap. 10 não implementados (fontes não verificadas); sem refração, atenuação do solo ou barreiras.
  Pormenor em [docs/RUIDO.md](docs/RUIDO.md).

## 32s. Gestão térmica — L0/L1 (18 nov 2026)

* **O que faz**: etapa `thermal` do pipeline (depois do ruído) para qualquer aeronave do adaptador `aircraft`
  (elétrica, motor térmico, turbo-hélice; jatos com fontes declaradas). Fontes de calor a partir dos modelos
  existentes (carga elétrica de bordo/carga útil, perdas da cadeia elétrica pelas eficiências, I²R da bateria,
  calor rejeitado pelo motor térmico por balanço de energia), temperaturas de compartimento em regime permanente e
  transitório concentrado, arrefecimento pela pele, por ar dinâmico (entrada NACA submersa + conduto) e por
  ventilador, em dias quente e frio da MIL-HDBK-310. Limites de componentes como requisitos. `acdt.api.thermal`
  aceita uma especificação genérica (VTOL, jatos, híbridos).
* **Métodos**: Incropera 6.ª ed. (Eq. 1.7, 5.5–5.7, 5.10, 7.30, 7.38, 8.53/8.55/8.60, 9.26, 9.30–9.32), μ e k da
  U.S. Standard Atmosphere 1976 (Eq. 51, 53), fator de recuperação (White), MIL-HDBK-310 (1997) perfis 1 %/20 %
  e sol 1120 W/m², NACA RM A8I29 (MFR 0,60), arrasto interno pela quantidade de movimento (Anderson), Heywood
  (1988) Cap. 12, PCI mínimos ASTM D910/D1655 (PRESSUPOSTO).
* **Completude**: fontes, propriedades óticas e temperaturas são intervalos; fonte sem majorante → temperatura
  máxima desconhecida → margem nunca passa; ε/α não declarados valem [0, 1]; conduto não dimensionável → arrasto
  e massa desconhecidos (nunca 0).
* **Acoplamento**: arrasto de arrefecimento (área de arrasto extra na polar), massa de conduto/permutador nos
  pesos, potência do ventilador no balanço elétrico (elétricos). `coupling: relatorio` (omissão) só relata;
  `coupling: iterar` faz ponto fixo com o dimensionamento.
* **Integração**: secção `thermal` no `result.json`; disciplina `termica`/L0 no `design.json`; requisitos
  `thermal_margin`, `cold_thermal_margin`, `cooling_drag_area` e avaliador `termica:<caminho>`; métricas de UQ e
  MDO pelos caminhos `thermal.*`; API 1.3.0 (`thermal`, `thermal_atmosphere`).
* **V&V**: `THERMAL-INC-EX5.1`, `-EX7.1`, `-EX9.2`, `-EX8.6` (exemplos resolvidos de Incropera), `THERMAL-MIL310`,
  `THERMAL-AIR-PROPS` — todos passam. Sem validação contra ensaios ainda.
* **Validado**: `tests/test_thermal.py`.
* **Limites**: rede de dois nós por compartimento; sem permutadores líquidos, refrigeração, efeito Meredith ou
  arrasto externo da entrada (só declarado); sol ao nível do mar a qualquer altitude; adaptadores VTOL/jato nativos
  em falta. Pormenor em [docs/TERMICA.md](docs/TERMICA.md). A proposta de alta fidelidade (18 nov 2026, ramo `termico-gelo-proposta`) não correu: não há sólido da baía, o `MARKER_HEATFLUX = 0` não é o balanço do compartimento, e o custo fica `nao_avaliado`. O L0/L1 não fica validado. Ver [docs/proposta-termica-gelo.md](docs/proposta-termica-gelo.md).

## 32t. Gelo — L0/L1 (18 nov 2026)

* **O que faz**: etapa `icing` do pipeline (depois da térmica) para qualquer aeronave do adaptador `aircraft`
  (condições a partir dos segmentos da missão); `acdt.api.icing` aceita uma especificação genérica (VTOL, jatos,
  sondas, cilindros). Envelopes do 14 CFR 25 Apêndice C (contínuo, intermitente, descolagem) com fator de extensão
  horizontal e envelope altitude–temperatura; na linha de estagnação de cada superfície: temperatura total,
  captação β₀, fração de congelação e tipo de gelo (rime/glaze), espessura acumulada na missão; potência de
  anti-gelo térmico e de degelo eletrotérmico; penalização aerodinâmica só como intervalo publicado.
* **Métodos**: 14 CFR 25 Ap. C transcrito de Jeck, DOT/FAA/AR-00/30 (2002), Tabelas 1–2 (Figs. 2 e 5 lidas da
  grelha, banda ±500 ft/±2 °F); Langmuir & Blodgett (1946), Messinger (1953), propriedades e balanço via Anderson,
  NASA/CR-2004-212875 (2004), Eq. (3.5)–(3.59) e Ap. A; r_le de Abbott & von Doenhoff; penalização de Broeren et al.,
  NASA/TP-2011-216929 (2011). Sem LEWICE (nem outro código GPL) em processo. Apêndice O não implementado.
* **Completude**: espessura, captação, potência e penalização em intervalo (β₀ com o desvio publicado vs LEWICE,
  ρ_i ±10 %, exposição padrão vs condição inteira); fora das tabelas → desconhecido; botas e gelo residual →
  desconhecido; ΔC_D0 desconhecido; FIKI nunca passa por análise (só falha ou desconhecido).
* **Acoplamento**: potência elétrica de proteção (majorante) no balanço elétrico (`systems_power_W` + carga do power
  budget, elétricos) e massa declarada nos pesos; `coupling: relatorio` (omissão) só relata, `coupling: iterar` faz
  ponto fixo com o dimensionamento (envolve o ciclo térmico).
* **Integração**: secção `icing` no `result.json`; disciplina `gelo`/L0 no `design.json`; requisitos
  `ice_protection_power`, `max_ice_thickness`, `flight_into_known_icing` e avaliador `gelo:<caminho>`; métricas de
  UQ e MDO pelos caminhos `icing.*`; API 1.4.0 (`icing`, `icing_envelope`).
* **V&V**: `ICING-AND-B1`, `ICING-AND-B2` (exemplos de Anderson Ap. B), `ICING-APPC-JECK`, `ICING-NACA0012-RLE` —
  todos passam. Sem validação contra formas de gelo medidas.
* **Validado**: `tests/test_icing.py`.
* **Limites**: só a linha de estagnação com geometria limpa; sem gelo de retorno nem intercíclico; sem SLD
  (Ap. O); ar sangrado e botas sem potência; encontros mistos não combinados; adaptadores VTOL/jato nativos em
  falta. Pormenor em [docs/GELO.md](docs/GELO.md). A proposta de alta fidelidade não escreveu malha de acreção nem correu o LEWICE. O Apêndice O e as formas da NASA IRT continuam ausentes. O L0/L1 não fica validado. Ver [docs/proposta-termica-gelo.md](docs/proposta-termica-gelo.md).

## 32u. Fiabilidade e manutenção de frota — L0 (18 nov 2026)

* **O que faz**: etapa `reliability` do pipeline (depois do gelo) para qualquer aeronave do adaptador `aircraft`
  (duração da missão a partir dos segmentos); `acdt.api.reliability` aceita uma especificação genérica
  (`acdt.reliability/1`, qualquer sistema). Fiabilidade de missão e MTBCF a partir de um RBD (série, paralelo ativo,
  k-de-n idêntico ou diferente, caminhos mínimos), MTBF básica, M_ct, MTBM, M̄, MMH/FH a partir de tarefas corretivas
  e preventivas declaradas, disponibilidades intrínseca/atingida/operacional, sobressalentes por Poisson, frota para
  cobertura contínua ou taxa de surtidas, custo de manutenção por FH no custo operacional existente.
* **Métodos**: MIL-HDBK-338B (1998) Eq. 5.57, 5.58, 5.73, 5.75, 6.19–6.27, 6.30, §7.5.5 (k-de-n, Fig. 7.5-9),
  §10.4.1 (Eq. 10.18, 10.21, 10.22, 10.24), definições de MTBCF e DMMH/MA (Secção 3); frota por cobertura com Ha
  (2010) via `fleet_feedback.fleet`; custo de manutenção na estrutura DOC de `manufacturing.costing` (Raymer 2018
  Cap. 18).
* **Taxas**: só de fornecedor (com fonte e data), da base pública `failure_rates.yaml` (as mesmas do ARP4761/SORA)
  ou declaradas com fonte; sem fonte → desconhecido; entradas `kind: assumption` só com `accept_assumptions: true`
  (PRESSUPOSTO).
* **Completude**: tudo em intervalo; taxa desconhecida → limites R = 0/1 (nunca λ = 0); MTTR, MMH, custo de peças ou
  atrasos logísticos em falta → a grandeza correspondente fica só com um limite ou desconhecida; custo operacional
  `partial`/`unassessed`; requisitos desconhecidos nunca passam.
* **Integração**: secção `reliability` no `result.json`; disciplina `fiabilidade`/L0 no `design.json`; requisitos
  `mission_reliability`, `mtbcf`, `mtbf`, `operational_availability`, `maintenance_man_hours_per_fh`, `fleet_size` e
  avaliador `fiabilidade:<caminho>`; métricas de UQ e MDO pelos caminhos `reliability.*`; ganchos na frota
  (`availability: {reliability: …}`) e no morfológico (`operating_cost.reliability`); API 1.5.0 (`reliability`,
  `availability`, `spares_stock`).
* **V&V**: `FIAB-338B-AVAIL-EX3`, `FIAB-338B-AAV-EX4`, `FIAB-338B-POISSON-5381`, `FIAB-338B-EQ630`,
  `FIAB-338B-PARALLEL-MTBF` — todos passam.
* **Validado**: `tests/test_reliability.py`.
* **Limites**: taxas constantes, avarias independentes, redundância ativa sem reparação em missão; sem espera
  fria/quente, fases, Weibull, causa comum nem METRIC; não altera o W0. Pormenor em
  [docs/FIABILIDADE.md](docs/FIABILIDADE.md).

## 32v. Custo de produção em série — L0 (18 nov 2026)

* **O que faz**: etapa `series_cost` do pipeline (depois da fiabilidade; só corre se pedida) e
  `acdt.api.series_cost` / `learning_curve`. Varre as CER existentes (Eastlake modificado, DAPCA IV) em quantidade.
  Para cada N separa RDT&E / ferramentas / recorrente e dá o custo unitário de saída de fábrica, o custo médio, as
  amortizações de RDT&E e de ferramentas e o custo recorrente por lote. Tem também uma rota de baixo para cima (T1 +
  curva de aprendizagem Crawford/Wright, lotes, NRE) e o ponto de equilíbrio contra o preço (nominal e tabela).
* **Métodos**: Gudmundsson (2014) Cap. 2 (Eastlake, já em `cost.py`); Raymer (2018) Cap. 18 (DAPCA IV, já em
  `costing.dapca4`); Wright (1936), Crawford (1944), FAA Pricing Handbook (1998) Cap. 18 Eq. 18-4/18-7/18-9/18-10
  (lotes, aproximação contínua); ponto médio do lote por definição.
* **PRESSUPOSTOS**: a decomposição RDT&E/ferramentas/recorrente (classificação fixo/variável de Gudmundsson, com as
  ferramentas na produção); o declive sem fonte declarada. Não há curva por cima da CER (a aprendizagem já está
  nos expoentes de N) nem modelo de cadência além do Q_m do Eastlake.
* **Completude**: sem preço → equilíbrio desconhecido; equilíbrio não atingido → `None` («não atingido até n_max»);
  NRE não declarado na rota de aprendizagem → limites inferiores. Os requisitos desconhecidos nunca passam.
* **Integração**: secção `series_cost` (chaves `*_USD`); disciplina `custo_serie`/L0 no `design.json`; requisitos
  `unit_cost_at_quantity` e `flyaway_cost` (qualificador `quantity`) e `break_even_quantity`; avaliador
  `custo_serie:`; métricas UQ/MDO pelos caminhos `series_cost.*`; API 1.6.0.
* **V&V**: `CS-FAA18-SLOPE`, `CS-FAA18-CUMAV-LOT`, `CS-FAA18-UNIT-APPROX` — todos passam.
* **Validado**: `tests/test_series_cost.py`.
* **Limites**: a validade do Eastlake é a aviação geral (num UAS é extrapolação, com nota). T1 ainda não vem
  automaticamente do plano de fabrico e não há curvas com degraus. Pormenor em
  [docs/CUSTO_SERIE.md](docs/CUSTO_SERIE.md).

## 32w. Custo do ciclo de vida e CO₂e — L0 (18 nov 2026)

* **O que faz**: etapa `life_cycle` do pipeline (depois de `series_cost`; só corre se pedida) e
  `acdt.api.life_cycle_cost` / `life_cycle_emissions` / `present_value`. LCC = RDT&E + produção + O&S + abate −
  residual, com calendário (RDT&E, entregas, vida útil), em dólares constantes e em valor presente à taxa real
  declarada; custo por hora de voo e por missão; CO₂ de combustão, CO₂e do poço à esteira, eletricidade da rede e
  fabrico de baterias, por FH, por missão, por aeronave e da frota.
* **Métodos**: OSD CAPE O&S Cost-Estimating Guide (2020) §2.1 (categorias); NIST Handbook 135 (1995) Eq. 5.1,
  Tabela 3-1, Eq. 3.6–3.13 (SPV, UPV, UPV*, taxas real/nominal); ICAO Anexo 16 Vol. IV Parte II Cap. 2 (FCF 3,16/3,10);
  CORSIA LC 89/95 gCO₂e/MJ; IVL C 444 (2019) 61–106 kg CO₂e/kWh para baterias NMC.
* **PRESSUPOSTOS**: calendário uniforme; residual 0 por omissão; frota = quantidade de série; combustível/FH e
  energia/FH a partir do dimensionamento (majorantes); PCI mínimo da norma; fator IVL (veículos) aplicado à
  aeronave. A intensidade da rede não tem valor por omissão: é sempre declarada.
* **Completude**: custo desconhecido → majorante desconhecido (nunca zero); sem taxa → VP desconhecido; sem
  rendimento de carga → só minorante da eletricidade; sem fator de bateria → fabrico desconhecido.
* **Integração**: secção `life_cycle`; disciplina `ciclo_vida`/L0 no `design.json`; requisitos `life_cycle_cost`,
  `life_cycle_cost_per_fh`, `co2e_per_flight_hour`, `life_cycle_co2e`; avaliador `ciclo_vida:`; métricas UQ/MDO
  pelos caminhos `life_cycle.*`; reutiliza `series_cost`, `reliability.operating_cost` e
  `manufacturing.costing.operating_cost` (depreciação retirada); API 1.7.0.
* **V&V**: `LCC-NIST135-FACTORS`, `LCC-NIST135-RATES`, `LCC-NIST135-EX51A`, `LCA-CORSIA-FCF` — todos passam.
* **Validado**: `tests/test_life_cycle.py`.
* **Limites**: sem fabrico da estrutura/motores, fim de vida nem efeitos não-CO₂. Pormenor em
  [docs/CICLO_VIDA.md](docs/CICLO_VIDA.md).

## 33. Feedback missão–propulsão–frota N0→N1 — L0 opt-in

* **CLI / MCP:** `acdt fleet study --input estudo.yaml` / `mission_fleet_study`.
* N0 sem geometria: envelopes e amostras explícitos, alternativas abertas e fontes.
  N1 usa `onboard_size` → dimensionamento e consumo nativos → tempo em terra →
  frota homogénea revista; payload/elétrica/extração são efetivamente acoplados.
* Prop: pointmass nivelado **já em voo**, sem fases de saída/chegada. Jet: Breguet
  equivalente em alcance com tempos não-cruzeiro fornecidos. VTOL: segmentos de potência
  existentes com MTOW inclusivo. Não é simulador dinâmico comum nem busca autónoma.
* Recarga por energia terminal realmente consumida / eficiência / potência média alocada,
  recurso dedicado por aeronave; ou tempo total em terra fornecido com proveniência.
* Inviáveis/desconhecidos/híbridos mantidos. Pareto condicional por amostra **e cobertura
  das fases**; capacidade/extração desconhecida não ganha. Sem vencedor ponderado.
* Missão de duração fixa, não autonomia máxima; uma passagem com histórico, **não**
  convergência N0↔N1 (isso é o esquema 1.1). Check espacial/térmico ausente não pedido é
  excluído explicitamente, não declarado resolvido. Filas/infraestrutura partilhada, frota
  mista, despacho híbrido L0 e cobertura de fases comuns estão no esquema 1.2 abaixo.
* **Esquema 1.1 (opt-in, 9 nov 2026):** autonomia máxima derivada do projeto fixo (bisseção
  conservadora, estados explícitos), fecho real dimensionamento↔capacidade no prop/jato
  e no VTOL com `aircraft.closure` opt-in (correção para cima, resíduos e não-convergência); VTOL de MTOW
  fornecido continua sem laço, reserva
  operacional explícita que substitui a fração nativa uma vez (prop térmico por avaliar) e
  `dwell_policy: requested|derived_max`. Frota continua aritmética direta, sem laço frota→projeto.
* **Esquema 1.2 (opt-in, 9 nov 2026) — recursos de solo partilhados:** `operations.ground_resources`
  (contagens de carregadores/pontos de abastecimento/equipas) e `candidate.ground_process` (atividades
  em série: fixas, carga E/(η·P) ou abastecimento m/caudal). Simulação de eventos discretos determinística
  (Law 2015) com filas FIFO; estabilidade ρ<1 (Kleinrock 1975), cota inferior de frota por Little (1961);
  laço frota↔tempo de solo com histórico (frota sobe só por lançamentos falhados); estados
  `converged|resource_saturated|not_steady|fleet_search_limit`; contagens mínimas estáveis reportadas.
  Sem filas estocásticas (Erlang), avarias ou prioridades. 1.0/1.1 inalterados.
* **Frotas mistas (1.2, `mixed_fleet`)**: enumeração limitada (≤512) de subconjuntos de tipos
  avaliados × repartições das estações (cada estação servida por um tipo), com recursos de solo
  partilhados numa única DES ou tipos independentes; `min_stations_by_type` como requisito de missão
  explícito; métricas totais (frota, MTOW da frota, energia/combustível por hora de cobertura);
  Pareto por objetivo (Deb 2001), sem vencedor ponderado. Sem alternância de tipos na mesma estação.
* **Despacho híbrido L0 (1.2)**: `recipe.model: hybrid` com `aircraft.hybrid` fornecido (série ou paralelo,
  MTOW inclusivo fixo, BSFC/eficiências constantes, bateria com SOC/taxa C, capacidade de combustível)
  e regra heurística (Guzzella & Sciarretta 2013 Cap. 8): série `thermostat`/`load_following`, paralelo
  `power_split` com fases só elétricas. Potência por fase: nivelado Raymer §17.2, subida/descida por
  potência em excesso (Anderson 1999 §5.10), táxi/descolagem/aterragem fornecidos. Combustível e
  recarga em terra alimentam `ground_process`. Sem dados → continua `unassessed`.
* **Fases operacionais comuns (1.2)**: `n1.mission_phases` para prop/jato/VTOL/híbrido com estados
  `flown|allowance|lumped:<fase>|supplied_duration|not_applicable|not_modeled`; `mission.required_phases`
  torna por avaliar (nunca aprovado) um candidato cujo adaptador não representa uma fase exigida.
* [Contrato/limites](docs/tutorial-mission-fleet.md), exemplos `examples/fleet/`.

## Roadmap (prioridades definidas pelo utilizador, outubro 2026)

### Já planeado

1. ~~**Superfícies de comando + simulador de missão 6-DOF**~~ — feito (Fase 8, secção 17). Próximo:
   C_h por DATCOM / Roskam VI, inércias calibradas, modelo de hélice de passo fixo, efeito de solo.
   **Próxima etapa**: flaps de curvatura (*camber flaps*) como opção de projeto avaliada pelo otimizador contra
   as alternativas (princípio: soluções são opções selecionadas só quando os requisitos as justificam).
2. **Jatos de transporte subsónicos** — **L0 feito 6 nov 2026 (§30)**:
   * Korn/Mason, turbofan L0, We Raymer, V-n de manobra, check público A320 e fecho
     de massa acoplado a geometria/motores fixos (`jet size`, sem fallback GA);
   * triagem L0 de corrida AEO/subida AEO-OEI ligada à massa feita 7 nov 2026
     (`jet performance`); campo ASD/TOD/BFL de triagem opt-in 9 nov 2026; trajetória contínua
     com rotação/transição e conformidade CS-25 pendentes;
   * build-up parcial opt-in feito 7 nov 2026 e alargado 9 nov 2026 (fuselagem/trem/sistemas
     Raymer + W_press + extração fornecida); `engines_dry` continua fornecido;
   * adiado L2: pyCycle/OpenMDAO, fecho MDA, Torenbeek completo, mapas ECS;
   * faltam validação CFD/ensaio e 737, rajadas/Mach/buffet; sem afirmar conformidade CS-25.
3. **Corridas de alta fidelidade pendentes**: CFD 3-D grande e FEM fino preparados para correr no PC do
   utilizador, com a sua autorização. Os fatores de calibração voltam ao L1/L2.
4. **Fabrico**: exemplo L2 com dados reais (cotações), Roskam VIII se as equações forem verificadas na fonte,
   modelo de montagem final.

### Prioridade ALTA

5. ~~Matriz de conformidade de certificação~~ e 6. ~~Segurança e fiabilidade (ARP4761)~~ — feitos na Fase 10 (§19).
7. ~~**Peso e centragem / envelope de CG** e **trem de aterragem: dimensionamento e cargas** (Currey)~~ — feitos na §20, dentro de `acdt size`.
8. ~~**Exportação CAD paramétrica**~~ — feito: `acdt cad` escreve o DXF e, com `acdt[cad]`, o STEP da
   estrutura interna. A casca exterior entra com `--oml`. Ver `docs/cad-parametrico.md`.

### Prioridade MÉDIA

9. **Configurações VTOL, híbrido e eVTOL.** — L0 feito (6 nov 2026, §29, `acdt vtol`); fecho de massa opt-in feito (9 nov 2026); despacho híbrido L0 por regras + fases comuns no estudo de frota 1.2 feitos (9 nov 2026); BEMT axial/pairar opt-in feito (10 nov 2026); falta massa híbrida fechada, BEMT em voo avançado, ruído no `acdt vtol` (a `acdt.api.rotor_noise` já aceita rotores dados, §32r), ECMS/DP.

### Prioridade BAIXA (útil, mais tarde)

10. Restantes sugestões, por esta ordem: projeto de hélice, fadiga e tolerância ao dano, UQ e modelos
    substitutos, calibração com ensaio em voo, ruído, gelo, gestão térmica, LCA/LCC, BOM com preços em direto,
    gémeo digital (e a pressurização da fuselagem, que vem com os jatos).

Detalhe de cada sugestão (valor e método a reutilizar) na tabela seguinte.

## Sugestões de capacidades (por prioridade)

| # | prioridade | capacidade | valor | método clássico / open source a reutilizar |
|---|---|---|---|---|
| 1 | ALTA | **Matriz de conformidade de certificação** | rastrear cada requisito CS-23, CS-25, STANAG 4671 ou SORA (UAV) até à análise do acdt que o demonstra | tabelas de cláusulas (a partir das checklists atuais) + ligação aos runs; SORA JARUS para a categoria específica UAS |
| 2 | ALTA | **Segurança e fiabilidade** | FHA, FTA e FMEA ligadas à arquitetura de sistemas; taxa de falha vs categoria | SAE ARP4761 / ARP4754A; árvores de falhas (por exemplo a biblioteca `scram`, executável externo) |
| 3 | feita | **Peso e centragem / envelope de CG** | ferramenta de carregamento operacional, limites dianteiro e traseiro, combustível e carga (§20) | Raymer Sec. 15.1; Roskam II Cap. 10 (expande `core/systems/mass.py`) |
| 4 | feita | **Trem de aterragem: dimensionamento e cargas** | posição vs CG, ângulos de tombo e capotagem, cargas de aterragem, curso do amortecedor (§20) | Currey, *Aircraft Landing Gear Design*; Raymer Cap. 11; 14 CFR 23.473 (25 jul 2017). Spin-up, carga lateral e travões ficam de fora |
| 5 | feita | **Exportação CAD paramétrica** | DXF da planta e da secção do caixão; STEP da estrutura interna (`acdt cad`) | CadQuery 2.8 (Apache-2.0) noutro processo. A casca OpenVSP entra com `--oml` |
| 6 | L0 feita | **Configurações VTOL, híbrido e eVTOL** | multirrotor, lift + cruise, tilt-rotor; dimensionamento da potência de pairar e da transição | teoria da quantidade de movimento; Johnson, *Helicopter Theory*; métodos de dimensionamento eVTOL (NDARC como referência) |
| 7 | BAIXA (L0 opt-in no ciclo de sistemas 10 nov 2026) | **Hélice: projeto e análise** | substitui a hélice estatística quando pedido; rendimento em cruzeiro; base para o ruído | BEMT McCormick/Ning já no repositório; Adkins & Liebeck 1994 (passo/corda auto); QPROP/XROTOR (Drela, executáveis externos) ficam de fora |
| 8 | BAIXA | **Fadiga e tolerância ao dano** | vida da estrutura e intervalos de inspeção | Miner (dano acumulado); Paris/NASGRO (propagação de fendas); espetros de carga FAA/ESDU |
| 9 | BAIXA | **UQ e projeto robusto** | bandas nos resultados (W0, custo, margens) em vez de pontos; projeto pouco sensível | Monte Carlo / LHS; caos polinomial (Chaospy, MIT); OpenMDAO + UQ |
| 10 | BAIXA | **Modelos substitutos / ML** para MDO rápido | MDO com L1/L3 a custo L0; exploração de espaço de projeto | krigagem (SMT, BSD); redes neuronais; multifidelidade (co-krigagem) |
| 11 | BAIXA | **Ingestão de dados de ensaio em voo** | calibrar polares, desempenho e estabilidade com dados reais (como a Fase 4 faz com CFD) | identificação de sistemas (output-error, Klein & Morelli); logs PX4/ArduPilot |
| 12 | BAIXA (L0 feito 18 nov 2026, §32r) | **Ruído** | ruído de hélice para certificação e aceitação (UAV urbano) | feito: Gutin, Schlegel-King-Mull, ISO 9613-1, IEC 61672-1, ISO 226, Parte 36 Ap. G; falta Hanson, espessura, motor, ICAO Anexo 16 |
| 13 | BAIXA (L0/L1 feito 18 nov 2026, §32t) | **Gelo** | penalização aerodinâmica e necessidade de proteção | feito: 14 CFR 25 Ap. C (Jeck), Langmuir & Blodgett, Messinger (Anderson), potência de proteção, penalização em intervalo (Broeren); falta Ap. O (SLD), gelo de retorno, formas de gelo (LEWICE só como referência externa) |
| 14 | BAIXA (L0/L1 feito 18 nov 2026, §32s) | **Gestão térmica** de aviónica e baterias | temperatura de células e eletrónica; dimensionamento de arrefecimento | feito: parâmetros concentrados (Incropera), MIL-HDBK-310, entradas NACA; falta modelo térmico de Bernardi (baterias), permutadores líquidos |
| 15 | ~~BAIXA~~ L0 feito (§32w) | **Custo do ciclo de vida, carbono e LCA** | custo total de posse e pegada (fabrico, operação, fim de vida) | feito: OSD CAPE 2020, NIST HB 135, ICAO Anexo 16 Vol. IV/CORSIA, IVL C 444; falta: fabrico da estrutura, fim de vida, ISO 14040/44 completa |
| 16 | BAIXA | **Cadeia de abastecimento / BOM com preços em direto** | L2 do custo alimentado por preços atuais de distribuidores | pesquisa da IA com proveniência (já é a regra) + cache datada de cotações |
| 17 | BAIXA | **Gémeo digital** | modelo calibrado continuamente com dados de operação | depende de #11 e #9; registo de runs como base de proveniência |
| 18 | BAIXA | **Pressurização da fuselagem** | a viga L1 (casca SP-8007, sem pressão) já entra no dimensionamento; falta a casca pressurizada para jatos | Niu Cap. 12; Megson (cascas pressurizadas) |
| 19 | BAIXA (L0 feito 18 nov 2026, §32u) | **Fiabilidade e manutenção de frota** | fiabilidade de missão, disponibilidade, MMH/FH, sobressalentes, dimensão da frota e custo de manutenção | feito: MIL-HDBK-338B (RBD, k-de-n, Eq. 10.18–10.24, Poisson), Ha 2010; falta espera fria/quente, fases, Weibull, causa comum, METRIC |

## 34. Blocos MDO, V&V e L3 no estado de projeto (19 nov 2026)

* **CLI:** `acdt db add-mdo`, `acdt db add-vv`, `acdt db add-hifi` (um ficheiro hifi avulso leva `--step`). Não há nome novo na API pública (continua 1.7.0).
* Copiam escalares finitos já gravados. Não dimensionam o avião e não lançam VSPAERO, CalculiX nem pyCycle. Um valor em falta não entra como zero. `nao_avaliado` não passa a `passa`.
* MDO → `results.mdo.L2` e `definition.derived.mdo` (o `definition.input` mantém-se). PRESSUPOSTO: L2 é a casa pedida em [docs/DADOS.md](docs/DADOS.md), não uma análise L2. Sem `chosen`, não há ótimo inventado. `n_pareto` é o comprimento da lista; os identificadores ficam no `mdo.json`.
* V&V → um bloco `results.vv.L0`. PRESSUPOSTO: é o relatório `acdt.vv/1` da framework, não a fidelidade do avião. O `delta_rel` é o que o relatório já gravou. Linha `nao_avaliado` ou `desconhecido` não copia erro.
* L3 por passo de `acdt hifi`, com o nome prefixado pelo passo para dois passos da mesma disciplina se juntarem. PRESSUPOSTO: a pasta do passo escolhe a disciplina. `rans_case` sem `CL` finito não cria aerodinâmica. Passo `skipped` ou desconhecido não escreve números. `inf` e listas ficam de fora. A unidade sai do sufixo da folha.
* `mdo` e `vv` não são disciplinas primárias da revisão. O diff L1↔L3 continua a ser `acdt db diff`.
* Itens ainda por fazer em [docs/DADOS.md](docs/DADOS.md): unidades para chaves sem sufixo e YAML com unidades nas specs de `acdt mdo`/`uq`.
* **Registo:** `examples/output/design_db_blocos/resultado.json`. Veredicto `validado` só para a transcrição do ensaio analítico `tests/data/review_small` (escolha 4, 9 avaliações, frente com 9 pontos, f1 = 0,7190488072346632 e f2 = 1,3271789813488566 com unidade não declarada; caso `ATM-ISA-SL` com `delta_rel` de `rho` = 1,479533701902775×10⁻⁸, unidade `1`). Calibração `nao_aplicar`. O excerto hifi desse registo é sintético e fica `nao_avaliado` como resultado físico. O YAML de exemplo não foi editado e nada foi aplicado.
