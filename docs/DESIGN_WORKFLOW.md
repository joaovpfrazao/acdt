# Workflow de design por níveis de fidelidade crescente

Aprovado pelo João a 30 out 2026. **Substitui** o esquema de loops de [workflow-design.md](workflow-design.md),
que fica como referência histórica e como mapa das ferramentas por loop. Aplica-se a todos os estudos novos.

> Ferramenta de apoio ao projeto. Os resultados não substituem a análise de engenharia nem a certificação.

## 1. Princípios

1. **O utilizador só descreve o problema.** A IA define a missão, os requisitos, as alternativas e o que
   avaliar. Não há esquema fixo de entradas.
2. **A IA pensa, as ferramentas avaliam.** As ferramentas do acdt são primitivas determinísticas, citadas e
   componíveis (dicionário → dicionário, com `method` e `validity`). Nenhuma ferramenta escolhe a
   configuração.
3. **Nunca assumir a configuração convencional.** A configuração é sempre uma alternativa avaliada, em todas
   as dimensões: asa, fuselagem e radome, cauda, propulsão, energia, lançamento e recuperação, materiais,
   trem, etc. Os exemplos deste documento são **sementes, não listas fechadas**.
4. **Todas as disciplinas e sistemas iteram juntos, em todos os níveis**, com alternativas abertas e
   fidelidade crescente. Não só aero, estruturas e RCS, mas também:
   * seleção da carga útil (radar, EO/IR, AIS, ESM…);
   * arquitetura elétrica e componentes (geração, distribuição, baterias, orçamento de potência);
   * aviónica, comunicações, datalink e SATCOM;
   * energia (combustível, bateria, híbrido) e propulsão;
   * fabrico, manutenção e custo (aquisição, operação, custo por hora de voo).
5. **Simulador de missão como juiz comum.** Em cada nível, as alternativas são ordenadas pelos resultados
   da missão (cobertura, probabilidade de deteção, autonomia útil, custo por hora de voo…) e não só por
   métricas isoladas (L/D, RCS, massa). O simulador sobe de fidelidade com o nível (§4).
6. **Não inventar números.** Cada valor é um resultado de ferramenta, um dado pesquisado com fonte e data, ou
   um **PRESSUPOSTO** justificado. Baixa fidelidade primeiro, calibrar depois.
7. **Corridas pesadas só no PC do utilizador com autorização explícita** (guarda de computação do MCP,
   `user_approved=true`).

### Implementação transversal disponível (7 nov 2026)

Os princípios acima são o processo pretendido, **não** um único otimizador integrado.
Carga útil e elétrica pertencem a **todas** as arquiteturas. `onboard_size` / `acdt onboard size`
é a entrada opt-in comum que chama `sizing.run` (hélice térmica/elétrica), `jet_size` e
`vtol_size`: payload/equipamento → massa, hotel → bateria, extração fornecida → consumo e
margem de potência/tração. VTOL conserva o MTOW inclusivo e verifica a alocação de massa, ou, com `aircraft.closure` opt-in, resolve o MTOW por componentes (itens tornam-se massas fixas).
As entradas nativas antigas não passam automaticamente a consumir este esquema.

Volume/calor declarados e montagem/CG/FOV com geometria explícita são verificações paralelas,
não fecho térmico ou realimentação espacial automática. Pointmass com estes loads existe no
prop; jato/VTOL continuam sem esse acoplamento dinâmico comum. Híbrido só faz balanços alocados,
sem dispatch. O simulador como juiz **comum a todos** continua a ser um objetivo parcialmente
implementado. Ver [contrato e limites](tutorial-onboard.md).

### Primeiro feedback missão–propulsão–frota disponível (7 nov 2026)

`mission_fleet_study` / `acdt fleet study` liga envelopes/amostras N0 e receitas N1
fornecidas a `onboard_size`, consumo nativo, serviço em terra e contagem de frota.
As alternativas e os casos por avaliar permanecem visíveis; não há preseleção de forma
no N0. Pareto é condicional à mesma missão amostrada e cobertura das fases.
Prop tem pointmass nivelado já em altitude; jet/VTOL usam Breguet/segmentos por omissão, ou o juiz comum opt-in (`common_sim` / `simulate_common_mission`) — não dinâmica
6-DOF comum. É **uma passagem com feedback**, não solver iterativo convergido nem procura de
autonomia máxima. A IA/utilizador revê os envelopes entre corridas. **Estado 9 nov 2026:**
filas 1.2, frota mista, reservas 1.1, dispatch híbrido L0, fases comuns e juiz comum opt-in
já entregues; 6-DOF de falhas / pyCycle / CFD permanecem no PC do João.
Com `schema_version: "1.1"` (9 nov 2026) o N1 devolve também a autonomia máxima derivada do
projeto fixo, um fecho iterativo dimensionamento↔capacidade (só prop/jato, com resíduos) e
reserva operacional explícita contada uma vez; a frota pode usar a permanência máxima derivada.
Não há laço frota→projeto enquanto os recursos forem dedicados. O fecho iterativo frota ↔ propulsão ↔ projeto ao nível do sistema está em `acdt mdo` (`closure:` com
as alternativas de propulsão no ciclo exterior; [MDO.md](MDO.md)).
Ver [contrato e exemplos](tutorial-mission-fleet.md).

## 2. Visão geral

```
Problema (texto)
  N0  Missão sem forma de avião  → requisitos de desempenho + requisitos de integração
  N1  Arquitetura                → matriz morfológica aberta, dezenas de combinações em baixa fidelidade,
                                   ficam 2–3 vivas
  N2  Forma                      → otimização paramétrica da OML de cada sobrevivente, escolha da vencedora
  N3+ Fecho                      → alta fidelidade, congelamento progressivo até uma forma produzível
```

Em cada nível repete-se o mesmo ciclo: **gerar alternativas → avaliar (com o simulador de missão como juiz)
→ cortar as dominadas → subir a fidelidade**. Se um nível inferior parte uma decisão de um nível superior,
volta-se atrás (§7).

## 3. Os níveis

### N0 — Missão sem forma de avião

**Entrada:** o problema em texto livre. **Saída:** requisitos de desempenho, requisitos de integração,
arquitetura de frota candidata, pressupostos e perguntas (`study.json` + `report.md`).

* **Requisitos de desempenho**: carga alar W/S, potência ou tração por peso, autonomia, alcance, velocidades
  (cruzeiro, patrulha, perda), teto, tempo de resposta. Saem das primitivas de conceito e frota
  (`transit_time`, `sweep_coverage`, `persistent_coverage`, `radar_horizon`, `sensor_footprint`,
  `johnson_range`, `fleet_reliability`, `size_fleet` em L0, `compare_alternatives`).
* **Requisitos de integração**, derivados da missão. Cada componente ou sensor (radar, gimbal EO/IR,
  SATCOM, datalink LOS, aviónica, combustível, baterias, gerador…) é declarado com:
  * volume (envelope) e massa;
  * potência elétrica (média e de pico) e calor a dissipar;
  * **cone de campo de visão** (azimute e elevação), por exemplo radar 360° em azimute e até −10° de
    elevação, gimbal para baixo e para a frente, SATCOM com céu livre;
  * zonas de exclusão (*keep-out*): hélice, escape, interferência eletromagnética, acesso de manutenção;
  * condições de posicionamento **como restrições** ("este cone tem de estar livre", "este volume tem de
    caber aqui", "perto do CG"), nunca como posições fixas.
* **Sistemas já em N0**: alternativas de carga útil (catálogo pesquisado ao vivo), de energia (combustível,
  bateria, híbrido), de ligação (LOS, relay, SATCOM) e um orçamento de potência de primeira ordem.
* **Simulador de missão N0**: massa pontual com polar estimada (L/D e consumo de literatura), sobre a
  geografia real, para dar a cobertura, a probabilidade de deteção e a autonomia útil de cada arquitetura
  de frota.

### N1 — Arquitetura

**Saída:** 2–3 configurações vivas, cada uma com o porquê, e as rejeitadas com o motivo.

* **Matriz morfológica aberta** (Zwicky 1969), com uma linha por dimensão. Sementes, não listas fechadas:
  * asa: baixa, média, alta, asa voadora, *box wing*, *joined wing*, asa em tandem;
  * fuselagem e radome: pod, corpo misturado (*blended*), *lifting body*, vigas, radome ventral ou dorsal;
  * cauda: convencional, em T, em V, V invertido, em H, canard, *tailless*;
  * propulsão: tratora, propulsora, distribuída, nas vigas; motor a pistão, elétrico, híbrido;
  * lançamento e recuperação: pista, catapulta, rede, paraquedas, VTOL;
  * materiais, trem, energia, aviónica e ligações, carga útil.
* **Regras para a IA:**
  * acrescentar opções além das sementes;
  * propor **pelo menos uma alternativa fora do habitual** por nível;
  * justificar cada exclusão por escrito (registo de decisões, §6);
  * as combinações incompatíveis cortam-se com um motivo físico, não por hábito.
* **Avaliação multidisciplinar completa de cada configuração (o conjunto inteiro, não só aero/RCS),**
  dezenas de combinações em baixa fidelidade:
  * **aerodinâmica:** VLM/AVL do **conjunto** (polar, L/D, CL máx., interferência asa–fuselagem–cauda)
    e perfis XFOIL/NeuralFoil;
  * **estabilidade e controlo:** margem estática, modos dinâmicos (período curto, fugóide, rolamento
    holandês, espiral), trimagem em todo o envelope e autoridade de controlo (superfícies, diedro);
  * **estruturas, massa e CG:** dimensionamento (`acdt size` L0/L1), pesos por componente, estruturas L1
    (viga, SP-8007, envelope ASTM F3116 quando aplicável), peso e centragem;
  * **packaging e sensores:** encaixe dos componentes e verificação dos cones de visão e das zonas de
    exclusão;
  * **propulsão e energia:** hélice, motor, combustível ou bateria, orçamento de potência elétrica;
  * **RCS (quando relevante para a missão):** Óptica Física do **conjunto** — posição vertical da asa,
    ligação asa–fuselagem, forma da fuselagem e do radome, posição das vigas e cauda, não só a cauda;
  * **trem, lançamento e recuperação:** posição do trem, folga da hélice, *tail-strike*, catapulta/rede/
    paraquedas quando aplicável;
  * **fabrico e custo:** custo L0 e producibilidade grosseira;
  * **o simulador de missão é o juiz final:** as disciplinas acima alimentam-no, e a decisão faz-se pelo
    resultado da missão (§4), não por métricas isoladas.
* **Simulador de missão N1**: por configuração, com a polar do VLM e o consumo real de combustível ou
  energia (incluindo a potência elétrica da carga útil).
* **Projeto por conjuntos (*set-based design*, Sobek, Ward & Liker 1999):** mantêm-se 2–3 configurações
  vivas. Só se corta uma alternativa quando é **claramente dominada tendo em conta a banda de incerteza do
  nível** (L0/L1 têm bandas largas).

### N2 — Forma

**Saída:** a configuração vencedora, com a OML paramétrica otimizada.

* Para cada configuração viva, otimiza-se a geometria paramétrica com aero, RCS, estruturas e packaging
  acoplados:
  * secção e comprimento da fuselagem, radome;
  * posição vertical e longitudinal da asa e concordância asa–fuselagem;
  * ângulos da cauda, chines, enflechamento, diedro;
  * posição dos sensores e antenas dentro dos cones de visão.
* As ferramentas sobem um nível: painéis ou Euler (com autorização se for pesado), RCS por PO mais fino (mais
  facetas, mais bandas e elevações), FEM linear do caixão (`wingbox6`), MDO (`acdt optimize`).
* Sistemas reavaliados com a nova forma: arquitetura elétrica com componentes reais, aviónica e
  redundância (`certify`/`safety`), escolha da carga útil, propulsão e hélice, manutenção e custo L1.
* **Simulador de missão N2**: 6-DOF com controlo, vento e rajadas, modelo do sensor e falhas.
* **A vencedora escolhe-se aqui**, pelo resultado da missão e pelas restrições, com as rejeitadas
  registadas.

### N3 em diante — Fecho

* Alta fidelidade: CFD (Euler/RANS), FEM não linear, flutter, fabrico, custo L2 com cotações, certificação.
  As corridas pesadas só correm no PC do utilizador **com autorização explícita**; antes, `hifi_estimate`.
* Fatores de calibração voltam aos modelos L1/L2.
* **Congelamento progressivo**: cada variável fica fixa quando a sensibilidade da decisão o permite, até
  haver uma forma produzível que cumpre todos os requisitos.
* Volta-se atrás quando um resultado parte uma decisão de cima (§7).

## 4. Simulador de missão como juiz comum

| nível | modelo | entra | sai |
|---|---|---|---|
| N0 | massa pontual, polar estimada | geografia, bases, alvos, sensor (faixa de datasheet) | cobertura, POD, autonomia útil, surtidas, custo por hora de voo |
| N1 | massa pontual por configuração | polar VLM, consumo real de combustível ou energia, potência da carga útil | as mesmas métricas, por configuração |
| N2+ | 6-DOF (JSBSim) | controlo, vento e rajadas, modelo do sensor e de deteção, falhas | as mesmas métricas, com dispersão |

As alternativas de cada nível ordenam-se por estes resultados, com os requisitos como restrições e a frente
de Pareto (`compare_alternatives`). Métricas isoladas (L/D, RCS, massa) servem para explicar, não para decidir.

## 5. Fidelidade por necessidade

* Subir a fidelidade **só onde a sensibilidade ou a relevância para a decisão é alta**. Se o RCS não decide
  entre duas configurações, não vale a pena calculá-lo com mais detalhe.
* A IA mede a sensibilidade das métricas de missão às variáveis (e às incertezas de cada modelo) e gasta o
  esforço onde a decisão muda.

## 6. Registo de decisões

Cada decisão fica escrita com:

* o que se decidiu e porquê (resultados de ferramentas citados);
* o nível de fidelidade em que se decidiu;
* as alternativas rejeitadas e o motivo;
* **as condições que a invalidam** (por exemplo "se a massa do radar passar 25 kg", "se o Euler der CLα
  10 % abaixo").

Assim dá para voltar atrás com critério e rever quando os requisitos mudam.

## 7. Gates e reavaliação

* No fim de cada nível há um gate: requisitos cumpridos dentro da banda de incerteza, decisões registadas,
  o que fica em aberto declarado.
* Quando um resultado de um nível inferior cumpre uma condição de invalidação, a decisão afetada reabre e
  as alternativas guardadas voltam a ser avaliadas.
* **Ferramenta (opt-in, 10 nov 2026):** `acdt decisions gate --level N1 --metrics …` /
  MCP `decisions_gate` → `pass` | `fail` | `unassessed` (unknown≠pass). Com `--reopen`, lista
  alternativas rejeitadas a reavaliar sem escolher vencedor (set-based). Ver
  [tutorial-p5-decisoes.md](tutorial-p5-decisoes.md) e CAPABILITIES §26.

## 8. Como a framework evita bloquear a imaginação

* **Geometria genérica por componentes** (corpos, superfícies sustentadoras, vigas, naceles, radomes), para
  que qualquer configuração, incluindo uma que ninguém previu, se monte e avalie com as mesmas ferramentas
  (aero, RCS, estruturas, packaging, CAD).
* **Requisitos de integração como restrições** (volumes, cones de visão, zonas de exclusão), não como
  posições fixas.
* **Sem enumerações fechadas de configuração como único caminho.** Os tipos com nome (`tail_type`,
  `wing_position`, …) ficam como atalhos para montar componentes, nunca como a lista do que é possível. Em `acdt size`, `geometry.configuration: V|inverted_V|twin_boom`, `geometry.dihedral_deg` e `assembly.options.flying_wing` (incluindo `yaw_control: split_aileron` + SAS, asa voadora sem superfícies verticais, 10 nov 2026; com charneira/servos de catálogo, atuador com atraso no SAS, rajada lateral, equilíbrio de picada (com `clmax: trimmed`, `useful_load_at: empty_cg`, banda de margem estática 0,02–0,08 de NACA TR-796 e verificação da torção por Panknin; 11 nov 2026: packaging do combustível no CG, fugóide com manutenção de atitude, opções para a rajada lateral, taxa da elevon e C_m dos corpos como sensibilidade; 12 nov 2026: arrasto da pré-deflexão no polar quando escolhida) e ensaio lateral 6-DOF/JSBSim em todos os casos de massa (concordância JSBSim ≈ 2 % nos casos estáveis); `acdt simulate --fidelity 6dof` voa a missão com o laço de derrapagem pelo split, decrab e cargas laterais no toque contra 14 CFR 23.485; 12 nov 2026: `gear.ground_attitude_deg` para descolar sem rodar na atitude de descolagem, verificação de rotação de Sadraey Sec. 9.6.2 e toques das pontas) e `gear.type` taildragger/ski + `draw_legs`/`retract` (Raymer Ch. 11 / 14 CFR 23.925; 9 nov 2026) são esses atalhos L0. Itens `shape: sphere|cylinder` e corpos rodados no AVL → unassessed (9 nov 2026) mantêm primitivas abertas.
* As regras do §3 N1 (acrescentar opções, uma alternativa fora do habitual, justificar exclusões) estão no
  prompt do agente, não em código.

## 9. Mapa para o acdt de hoje e lacunas

| nível | já existe | lacunas |
|---|---|---|
| N0 | camada de conceito e frota (`concept_study_*`, `geo_measure`, `transit_time`, `sweep_coverage`, `persistent_coverage`, `radar_horizon`, `sensor_footprint`, `johnson_range`, `fleet_reliability`, `size_fleet`, `compare_alternatives`, prompt `concept_trade`); `validate_requirements`; `acdt simulate --fidelity pointmass` (massa pontual com o bloco `aircraft`) | objetos de requisito de integração (volume, massa, potência, calor, cone de visão, zonas de exclusão); catálogo e trade de carga útil; orçamento de potência elétrica; ~~busca de barreira~~ (**FEITO** L0 `barrier_search`) |
| N1 | `acdt morph` (matriz/gerar/avaliar/podar) + `acdt size` L0/L1 (Raymer, diagrama de restrições, AVL, XFOIL/NeuralFoil); pesos por componente; estruturas L1 (`structures_l1`, SP-8007); W&B e trem dentro de `size` (`weight_balance`, `landing_gear`); `acdt rcs study` (PO, aeronave facetada paramétrica, Pareto aero/RCS); `flap-options`; sistemas (hélice, motor, bateria, servos, cablagem); `cost_estimate` L0; `certify`/`safety`; `acdt simulate <projeto> <missão> --fidelity pointmass` (polar e consumo do dimensionamento, sem modelo de voo AVL) | geometria genérica por componentes; gerador morfológico; avaliador multidisciplinar do conjunto completo (aero, estabilidade e controlo, estruturas/massa/CG, packaging/FOV, propulsão/energia, RCS quando relevante, trem/lançamento/recuperação, fabrico/custo; o juiz de massa pontual já existe e falta o avaliador que o chama); verificador de packaging e cones de visão; poda por conjuntos com bandas de incerteza; ~~tipos de cauda e vigas (V invertido, bivigas) no `size`~~ / ~~diedro e espiral~~ / ~~winglets de asa voadora + trem nessa layout~~ (atalhos L0 9 nov 2026); ~~asa voadora sem deriva com split ailerons + SAS~~ (L1 opt-in 10 nov 2026; dimensão morfológica extra `yaw_control`); arquitetura elétrica; ~~registo de decisões~~ / ~~gate fim de nível~~ (P5 + gate 10 nov 2026) |
| N2 | `acdt optimize` (OpenMDAO, OpenAeroStruct, passo de catálogo); `wingbox`/`wingbox6`; `acdt controls`; `acdt simulate` (6-DOF, piloto automático, Dryden, rajadas; o mesmo YAML traz a pegada de sensor no rasto e o registo de falhas); `acdt cad` (DXF/STEP, `--oml`); `acdt manufacture` L1 | otimização paramétrica da OML acoplada aero/RCS/estruturas/packaging; painéis; dinâmica de malha fechada das falhas no 6-DOF; Monte Carlo de falhas; ferramenta de sensibilidade (fidelidade por necessidade) |
| N3+ | `acdt hifi` (OpenVSP, SU2 2-D/GCI/Euler/RANS, CalculiX, flutter DLM, Nastran), calibração; `acdt manufacture` L2; `acdt certify` (matriz, ARP4761, SORA) | FEM não linear (`fem_nl`); custo L2 com cotações reais; contenção SORA e taxas de fornecedor; manutenção |

Ordem de implementação e prioridades: [HANDOFF.md §5](HANDOFF.md).

## 10. Lições da primeira aplicação completa

A primeira aplicação completa da framework (o problema do benchmark `examples/benchmarks/nansei_jcg/`) motivou
este workflow:

* a configuração tem de ser uma alternativa avaliada, não um ponto de partida assumido;
* os trades aero/RCS têm de variar a interação entre componentes, não só um componente de cada vez;
* os sensores (cones de visão, volumes) condicionam a forma;
* a decisão usa o resultado da missão, não métricas isoladas (L/D, RCS médio, massa).

Os pontos em aberto que daí resultaram estão no HANDOFF.

## Referências

* Zwicky, F. (1969). *Discovery, Invention, Research through the Morphological Approach*. Macmillan.
* Sobek, D. K., Ward, A. C. & Liker, J. K. (1999). Toyota's principles of set-based concurrent engineering.
  *Sloan Management Review* 40(2).
* Raymer, D. P. (2018). *Aircraft Design: A Conceptual Approach*, 6.ª ed. AIAA.
* INCOSE (2015). *Systems Engineering Handbook*, 4.ª ed. (rastreabilidade de decisões).
