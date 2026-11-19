# Passagem de testemunho — estado do acdt (5 nov 2026)

Repositório público `joaovpfrazao/acdt` (Apache-2.0), ramo `main`. Desde 18 nov 2026 todo o desenvolvimento (ramos, PRs, CI) é feito aqui; o antigo
repositório privado fica só como arquivo. Instalação no Windows:
[DEV-SETUP-WINDOWS.md](DEV-SETUP-WINDOWS.md). Regras para agentes: [../AGENTS.md](../AGENTS.md) e
`.cursor/rules/acdt.mdc`. O que a ferramenta faz e os limites de cada área: [../CAPABILITIES.md](../CAPABILITIES.md).
Workflow de design (problema → design final): **[DESIGN_WORKFLOW.md](DESIGN_WORKFLOW.md)** (níveis N0–N3+, aprovado a
30 out 2026). O esquema anterior de loops fica em [workflow-design.md](workflow-design.md) como referência.

Suite de referência no Linux: **233 testes** (13 min 37 s, com AVL/XFOIL/Gmsh/SU2/CalculiX/OpenVSP/JSBSim).
No Windows, com Python 3.13.15, o extra completo e os binários de alta fidelidade, `pytest -q` deu
**274 passaram**, 124 avisos, 20 min 00 s (29 out 2026). Com o modelo estrutural L1 a mesma suite deu
**289 passaram**, 124 avisos, 21 min 28 s (30 out 2026). Uma corrida anterior falhou só em
`test_calculix_static_tip_within_half_of_the_beam`: a flecha da viga ficou 0,10996 m, igual ao JSON
guardado, e a ponta do CalculiX saiu negativa; o teste isolado e a suite seguinte passaram.
Com o CAD paramétrico a mesma suite deu **292 passaram**, 124 avisos, 21 min 28 s (30 out 2026).
Com o passo de catálogo no MDO a mesma suite deu **298 passaram**, 124 avisos, 22 min 05 s (30 out 2026).
Com a massa pontual (P3) a mesma suite no Windows deu **370 passaram**, 129 avisos, 32 min 18 s (5 nov 2026).
Com NeuralFoil o W0 do UAV de referência passa
o limite de 25 kg: os testes desse exemplo aceitam `mtow` além de `wing_span`.

> **Estudo conceptual de frota** (em `main` desde `b4fa856`, 29 out 2026): um problema em linguagem livre dá a
> missão, os requisitos e a arquitetura de frota. Inclui 13 ferramentas MCP, o prompt `concept_trade` e o
> comando `acdt concept replay|report`, mais o exemplo de pesca ilegal em
> `examples/output/concept/illegal_fishing/`. Ver CAPABILITIES §21 e [ai-concept-trade.md](ai-concept-trade.md).

## 1. Estado por fase

| fase | conteúdo | estado | tutorial |
|---|---|---|---|
| 1 / 1E | requisitos abertos, W0 (Raymer, Breguet, elétrico), diagrama de restrições, sistemas (hélice, motor, bateria, servos, cablagem) | ✅ | `tutorial-fase1.md`, `-fase2.md` |
| 2 | AVL + XFOIL/NeuralFoil no ciclo | ✅ | `tutorial-fase2.md` |
| 3 | MDA/MDO OpenMDAO, OpenAeroStruct | ✅ (limites abaixo) | `tutorial-fase3.md` |
| 4 | alta fidelidade: OpenVSP, SU2 2-D/GCI/Euler 3-D, CalculiX, flutter DLM, deck Nastran, calibração | ✅ local; corridas grandes pendentes (§4) | `tutorial-fase4.md` |
| 5 / 6 | caixão de asa (FEM de cascas próprio, encurvadura, nervuras); RCS (Óptica Física) | ✅ | `tutorial-fase5.md`, `-fase6.md` |
| 7 | fabrico e custo L0/L1/L2 | ✅; falta exemplo L2 real | `tutorial-fase7-fabrico-custo.md` |
| 8 | superfícies de comando + simulador 6-DOF (JSBSim em processo separado) | ✅ | `tutorial-fase8-simulador.md` |
| 9 | hélice BEMT de passo fixo, inércias Roskam V, flaps de camber como opção | ✅ | `tutorial-fase9-camber-flaps.md` |
| 10 | base de certificação, matriz de conformidade, FHA/FTA/FMEA (ARP4761 baixa fidelidade), redundância → W0, SORA 2.5 | ✅ | `tutorial-fase10-certificacao-seguranca.md` |
| AI | servidor MCP `acdt mcp`: 43 ferramentas (13 do estudo conceptual), recursos, prompts, registo de corridas, guarda de computação | ✅ | `ai-agent-guide.md` |
| — | peso e centragem operacional e trem, dentro de `acdt size` (sem comando novo) | ✅ baixa fidelidade; limites em §3 | `tutorial-wb-trem.md` |
| — | asa voadora sem deriva: split ailerons + SAS, dentro de `acdt size` (opt-in); charneira/servos, atuador no SAS, rajada lateral, equilíbrio de picada, 6-DOF lateral (10 nov 2026); GCI RANS de um α, factor não aplicado (13 nov 2026, §4); torção do loft corrigida, malha grossa CL 0,83, factor continua por aplicar (14 nov 2026, §4); verificação da geometria da malha antes de qualquer RANS de asa, sem corrida e sem factor (14 nov 2026, §4); t/c do loft e do AVL alinhado ao yaml 0,15/0,12, curvatura do NACA 4415 por construir, ΔCL do AVL 0 à precisão impressa, sem factor (14 nov 2026, §4); GCI v2 com essa secção e a torção certa, CL fino/AVL 0,833 e CMy 1,097 dentro da banda mas oscilatórios, factor não aplicado (15 nov 2026, §4) | ✅ L1; limites na secção própria | `tutorial-asa-voadora-sem-deriva.md` |

## 2. Últimos commits

Ramo `p1c-optimizer-assembly` (3 nov 2026, a partir de `p1b-assembly-size`, por integrar; suite 342 passed):

```
fd893c1 P1b(g): harness de validação do modelo de corpos do AVL
74c52df P1b(f): STEP facetado e entrada RCS da montagem
42f4c6e P1b(a): MDO lê a montagem
1f86513 P1b(b–e): escala 'surfaces', K da AVL (Kroo), balanceamento, protuberâncias automáticas
e50ed84 Docs: ADflow+TACS (MPhys) como opção N2/N3; HANDOFF §4b
```

Segunda revisão de 29 out 2026, um commit por ponto, em `main`:

```
ad02b93 O teste da placa de encurvadura corre com uma thread
ff88d30 O .geo da meia-asa deixa de apontar para C:/Users
464df2b O M6 confirma os eixos do Euler; o CD do C172 não se inverte
d39ce51 A inércia do C172 compara-se com os braços do POH
4806aa4 O C172 passa o envelope de CG, o trem e a tesoura
c58f3cb Corrige a encurvadura do CalculiX que caía no shift σ=1
3b1aef9 Corrige a comparação de torção do FEM com o GJ de Bredt da Fase 3
62201bc UAV de 150 kg: a carga útil fica no CG da massa fixa e o trim cabe
```

A passagem anterior do mesmo dia (trem, k_cd_profile, caminhos relativos, CD de Euler rejeitado) vai de
`db42ed8` a `ca1a681` e está resumida em `de3ac0a`. `git log --oneline` para o histórico completo.

## 3. Problemas conhecidos e limitações

* **Fase 10**: estado de conformidade conceptual (a autoridade decide); FTA com taxas constantes, sem modos
  comuns, bloqueio/hardover de servos nem software; sem taxas públicas para C2 e bússola (FC em aberto); taxas
  de motor UAV, FCC, bateria e cablagem são PRESSUPOSTOS na ausência de `supplier_rates`; ΔCusto n/d sem preços;
  SORA passo #8 (contenção, Tabelas 8–13 + Anexo E § E.4) é opt-in — sem densidade adjacente, ajuntamentos ou
  evidência citada fica unassessed (nunca pass silencioso); mitigações estratégicas de ar (Anexo C) não
  automatizadas; abrigo em UA > 3 m (Anexo F) não creditado; as opções de redundância são estudo +
  redimensionamento, não variáveis do MDO. C2 (FC-U4) só fecha com taxa de fornecedor com fonte e data.
  Resultados honestos: C172 falha a atitude primária na Classe I (AI de vácuo GARS); UAV STANAG 4671 falha a
  perda de propulsão com um só motor de 2 tempos.
* **Rolamento holandês do GA**: no ótimo MDO do C172 (AR = 5, limite inferior ativo) o flutter fica resolvido
  mas o rolamento holandês falha; com `mdo.hq_aeroel_constraints: true` passam a restrições reais na
  violação de φ (omissão = filtro pós-ótimo legado) — ver item MÉDIA 6.
* **Catálogo no MDO**: o SLSQP não muda o motor, o ESC nem a célula. Esses três mudam num passo à parte,
  aceite só quando o mérito do pipeline melhora. Não há catálogo de hélices (diâmetro contínuo, Raymer
  Sec. 10.3). Os servos continuam a ser reescolhidos no fecho, e o motor a pistão não entra neste catálogo.
* **CAD**: a montagem STEP é a estrutura interna. A espessura do revestimento é a do `WingBoxLayout`,
  não a da encurvadura, e é aplicada na vertical (PRESSUPOSTO). A casca exterior só entra com `--oml`.
  O OpenVSP 3.56.0 está instalado neste PC (18 nov 2026, §4b).
* **SIMP das nervuras**: demo 2-D da alma (layout) e, **opt-in**, massa da alma no orçamento de massa
  (`wingbox/rib_simp_mass.py`, `acdt rib-simp`, `assumptions.structures.rib_simp_mass`). Continua 2-D
  linear, um caso de carga, volume fixo; o resto nariz/cauda não é SIMP; sem extrapolação da raiz;
  não entra no SLSQP. Não é FEM não linear nem campanha de TO (isso fica no PC do João).
* **Custo L2**: falta um exemplo com cotações reais (BOM, fornecedores com fonte e data).
* **Camber flaps**: arrasto de compensação HT e gap são **opt-in** (`trim_drag` / `gap`); omissão = legado.
* **Aterragem do C172**: 503,8 m contra 407 m requeridos (anterior à Fase 9; ligado ao CP da hélice a J baixo e
  ao modelo de travagem — investigar Raymer 17.9 vs POH). A subida fica em 3,634 m/s contra ≥ 3,708 m/s.
* Inércias: com os braços do POH, o Iyy de Roskam (Parte V, Eqs. 3.7–3.9, raios da Tabela B2 do Cessna 172M) é 2011 kg·m² contra 2002 da reconstrução do c172p do JSBSim a 2550 lb (modelo educativo: tensor vazio mais as massas que fecham o peso). O Ixx fica 12,9 % abaixo de 2770. A banda do teste mantém-se: Roskam a ±25 % e a soma por componentes a ±30 %, nos três eixos. O valor 2502,7 kg·m² era o mesmo Iyy com a carga a 50 % de L, numa massa um pouco maior; nesta geometria esse braço dá cerca de 2500 kg·m². Flutter de baixa fidelidade quase-estacionário.
* **Peso e centragem operacional e trem** (baixa fidelidade, dentro de `acdt size`):
  * as estações de estrutura continuam a ser os pressupostos de Roskam (Parte V, Tabela 8.1) até serem
    substituídas. Tripulação, carga e bateria, se a missão não as der, ficam no CG da massa fixa
    (estrutura, sistemas e motor). Um UAV não leva tripulação. O combustível de asa continua a 30 % da
    CMA. É um PRESSUPOSTO de layout (Raymer 2018 Cap. 15), não a Tabela 8.1. O C172S usa os braços do
    POH (Secção 6) medidos desde a firewall (`weight_balance.loading`). O CG de cada depósito é fixo
    e o combustível inutilizável não é separado;
  * o limite dianteiro é o mais à ré do caso limpo (CLmax sem flaps, Cm0 da asa) e do flare de
    aterragem (CLmax com flaps, Cm0 da asa + fuselagem + flap). No flare, o declive de sustentação da
    cauda usa o φ de Torenbeek 1982 (Phillips e Hunsaker, JoA 2013, Eq. 4), à altura PRESSUPOSTO do
    comprimento do trem principal mais metade do diâmetro da fuselagem. O CLmax não sobe e o dε/dα do
    ponto neutro não muda. O flap slotted, fowler e multi-slotted usa o centro de pressões incremental
    do DATCOM 1978 Sec. 6.1.2.1, a 44 % da corda estendida. Plain e split mantêm o Glauert;
  * o curso segue Currey 1988 §5.3: N = [V²/(2g) + (1−κ)(S+S_t)] / (η_s S + η_t S_t);
  * 0,60 m de comprimento do trem principal, a roda de cauda a 0,95·L e a tolerância de 0,05 kg na face
    de MTOW são PRESSUPOSTOS;
  * 0,95 W0 é o piso que 14 CFR 23.473(b) permite, não a demonstração da cláusula de combustível;
  * o entre-eixos do triciclo fica na banda de fração no nariz da missão (omissão 8–15 %, Raymer Cap. 11)
    e dentro da fuselagem; se não houver solução, `gear:position` falha e o nariz não é colocado. O C172S
    substitui a omissão por 16,8–35,7 %, dos braços da lista de equipamento do POH (−6,8 in e 58,2 in) e
    da base de 65 in (Secção 1): o envelope certificado fica fora dos 8–15 %. PRESSUPOSTO: esses braços
    são os da lista, na atitude de solo publicada, não uma ficha de pesagem preenchida;
  * não há spin-up, spring-back, carga lateral, travões nem rolagem; a fração estática no nariz não é a
    distribuição de aterragem nivelada;
  * quando o curso é dimensionado e cabe, `load_factor_ok` fica por decidir e a matriz fica em "requer ensaio";
  * `landing_gear: none` deixa 23.2220, 23.2305 e USAR.471 em aberto;
  * as verificações `wb:` e `gear:` não alteram a viabilidade da Fase 1. Os quatro casos discretos da
    estabilidade mantêm-se ao lado do diagrama operacional.
* **`acdt size` em 29 out 2026, depois desta revisão** (pastas temporárias, sem gravar por cima dos
  exemplos). O «antes» é a medição do mesmo dia, anterior aos pontos da carga útil e do flare.

  * Cessna 172S. A Fase 1 fica viável nos dois lados (W0 = 1137 kg, L = 8,059 m, ápice a 19,7 % de L).
    A gama de estabilidade mantém-se em 27,1–39,6 % da CMA dimensionada (margem estática 0,225 / 0,100).
    * Antes: `wb:envelope` falha. Extremos 2,019 m (vazio, 786 kg) e 2,265 m (bancos traseiros + bagagem,
      1025 kg), cerca de 27–45 % da CMA dimensionada. `hq:scissor` falha no controlo: S_h/S 0,200 contra
      0,297. `gear:position` e `gear:tipback` falham na banda 8–15 %, sem posição. O trim cabe
      (δe −14,1° na CLmax limpa e −5,0° em cruzeiro).
    * Depois: `wb:envelope`, `gear:position` e `hq:scissor` passam. Extremos 2,019 m (vazio, 786 kg,
      22,6 % pela fórmula do POH) e 2,190 m (bancos traseiros + bagagem 1 + bagagem 2 + combustível,
      1066 kg, 34,1 %). A nuvem de carregamentos é um subconjunto do polígono certificado (cerca de
      15,5–36,4 % da CMA do POH) e não começa nos 15,5 %. S_h/S atual 0,200, mínimo 0,200, limitado pela
      estabilidade (controlo 0,151). Nariz 0,560 m, principal 2,518 m, fração no nariz 25,5 % à frente e
      16,8 % atrás. Trim δe −14,1° e −5,0°. `gear:rotation` continua a falhar (6,7° contra o mínimo de
      10° na barriga cilíndrica) e `geometry_ok` fica falso. `perf:climb_rate` (3,634 m/s contra ≥ 3,708)
      e `perf:landing_distance` (503,8 m contra ≤ 407 m) continuam a falhar. Não alteram a viabilidade
      da Fase 1.
  * UAV a gasolina de 150 kg. W0 = 136 kg nos dois lados. L = 3,200 m.
    * Antes: inviável (o processo terminava com código 1). CG de −26 % a 32 % da CMA, δe −52° na CLmax
      e −32° em cruzeiro, `hq:scissor` com o mínimo de controlo não finito, carga útil a 50 % de L.
      `wb:envelope` falha (extremos 0,835 m no vazio, 86 kg, e 1,033 m com carga, 116 kg).
      `gear:position` e `gear:tipback` falham.
    * Depois: a Fase 1 fica viável. Não há tripulação. A carga e a bateria ficam no CG da massa fixa e
      o combustível a 30 % da CMA. O trim e a tesoura leem a mesma gama, 33,6–34,5 % da CMA (margem
      estática 0,109 / 0,100). δe −12,1° na CLmax e −8,9° em cruzeiro, ambos aceites. O ápice passa de
      28,3 % para 18,3 % de L. `hq:scissor` continua a falhar, agora com números finitos: S_h/S 0,097
      contra 0,135, limitado pelo controlo. `wb:envelope` continua a falhar por pouco: extremos 0,720 m
      (combustível, 106 kg) e 0,723 m (vazio, 86 kg), à frente do limite de flare. `gear:position` e
      `gear:tipback` continuam sem solução na banda 8–15 % dentro da fuselagem. O curso é 0,170 m com
      n_g = 3,00. A fugóide cumpre o Nível 1. O rolamento holandês fica no Nível 2. Estes `wb:`, `gear:`
      e `hq:` não tiram a viabilidade da Fase 1. Os segmentos de desempenho cumprem.
  * UAV a gasolina de 150 kg, 30 out 2026, ramo `fix-validacao`. O «depois» acima é o estado com `c_ht` 0,50. O exemplo passa a `c_ht` 0,55. A intersecção da tesoura neste MDA é 0,543; 0,55 é o arredondamento à centésima acima dela. PRESSUPOSTO: só esse arredondamento. Critério: Torenbeek 1982 Cap. 9 e Raymer Cap. 16 (linha de controlo de Nelson; flap plain de Glauert 1926). A tolerância de 0,5 % de S_h/S mantém-se. O motor fica a 8 % de L (Roskam Parte V, Tabela 8.1, tractor).
    * Antes (`c_ht` 0,50): `hq:scissor` falha, S_h/S 0,097 contra 0,135, limitado pelo controlo. `wb:envelope` falha: extremos 0,720–0,723 m, limite dianteiro 0,727 m, atrás dos dois extremos.
    * Depois (`c_ht` 0,55): W0 = 136,3 kg. `hq:scissor` passa: S_h/S 0,107 contra 0,107, limitado pela estabilidade (controlo 0,101). `wb:envelope` passa: extremos 0,715 m (combustível, 106 kg) e 0,720 m (carga, 116 kg); limite dianteiro 0,714 m; limite traseiro 0,720 m. Gama 35,6–36,9 % da CMA. δe −11,3° na CLmax e −8,2° em cruzeiro. A cauda cabe em L = 3,20 m.
    * `gear:position` e `gear:tipback` continuam sem entre-eixos. Causa: h_cg = 0,55 m e o raio de 15° põem o principal cerca de 0,15 m atrás do CG traseiro (x ≈ 0,87 m). A banda 8–15 % pede um entre-eixos mínimo de cerca de 1,01 m, e o nariz sairia para x ≈ −0,15 m. O texto do exemplo descreve hélice propulsora; a estação usada é a de tractor (motor a 8 % de L, hélice em x = 0). Não há no repositório uma fração publicada para motor propulsor. 0,40 L é o limiar em que o nariz cai no datum com o braço atual: é o limiar da verificação, não uma estação com fonte, e fica de fora. Encurtar a perna de 0,35 m ou alargar 8–15 % também fica de fora. Para fechar: grupo motopropulsor atrás da estação de tractor, com lança de cauda ou com braço mais curto e cauda revista pela tesoura, e uma fonte para o comprimento do motor.
  * Cessna 172S, mesma data, sem mudança de modelo. Comparação com o POH 172S, Secção 1 (2550 lb, atmosfera padrão, pista pavimentada, nivelada, seca, sem vento): descolagem 960 ft no solo e 1630 ft sobre 50 ft; aterragem 575 ft no solo e 1335 ft sobre 50 ft; subida 730 ft/min. O modelo pesa 1137 kg (2506 lb).
    * Subida: 3,634 m/s (715 ft/min) contra 3,708 m/s, desvio −2,0 %. Anderson Cap. 5 com hélice de passo fixo (BEMT). A verificação usa 0,1 %; o teste de modelo admite 5 %. A verificação continua a falhar.
    * Descolagem: corrida 274,4 m contra 293 m (960 ft), desvio −6,3 %, cumpre. Total sobre 50 ft: 458,9 m contra 496,8 m (1630 ft), desvio −7,6 %. Este total não é uma verificação.
    * Aterragem: total 503,8 m contra 407 m (1335 ft), desvio +23,8 %. Solo do modelo 200,7 m contra 175,3 m (575 ft), +14,5 %. Ar (aproximação 278,5 m + flare 24,6 m) 303,1 m contra 231,6 m (760 ft), +30,8 %. V_TD 28,4 m/s implica perda a 48 kt, igual à do POH. γ = 3° é o gradiente máximo de 5,2 % de 14 CFR / CS 23.75(a)(1). Uma recta a 3° desde 50 ft já mede cerca de 291 m de ar, mais do que os 232 m do POH: a aproximação de pista curta demonstrada é mais íngreme do que 3°. O POH não publica o ângulo para o substituir. O efeito de solo no arrasto induzido (Hoerner e Borst 1975; McCormick 1979) reduz o arrasto e alonga a travagem; o flutuamento no flare alonga o ar. Fica de fora. μ = 0,4 e os 3 s de rolagem livre mantêm-se.
    * Rotação: 6,7° contra o mínimo de 10° (Raymer Cap. 11, 10–15°). O ventre do modelo é um cilindro com o diâmetro máximo até à cauda. O POH dá a folga da hélice ao solo e não o ângulo de toque da cauda nem a lei do raio. Para fechar: o contorno inferior da fuselagem, com fonte.

## 4. Corridas de alta fidelidade pendentes (no PC, com autorização)

Pré-requisitos: SU2, CalculiX, Gmsh, OpenVSP configurados (DEV-SETUP-WINDOWS §3–4). Cada passo grava JSON e é
reutilizado; `--force` recorre. Os fatores de calibração voltam ao L1/L2 (`apply_calibration` ou
`calibration.json`).

```powershell
# GCI da secção (convergência de malha, Celik 2008) e Euler 3-D da meia-asa (CLα vs AVL)
acdt hifi examples\cessna172_check.yaml -o examples\output\cessna172_check_hifi --steps geometry,cfd2d,gci,wing_euler,calibration
# RANS 3-D do avião completo: o passo só ESCREVE o caso e a estimativa de RAM/tempo
acdt hifi examples\cessna172_check.yaml -o examples\output\cessna172_check_hifi --steps rans_case
cd examples\output\cessna172_check_hifi\rans_case
mpiexec -n <N> SU2_CFD aircraft_rans.cfg      # repetir por α (0, 2, 4…) conforme o README do caso
# FEM fino + flutter (CalculiX + DLM PanelAero) e deck Nastran SOL 145 (verificado por releitura pyNastran)
acdt hifi examples\uav_endurance_payload.yaml -o examples\output\uav_endurance_payload_hifi --steps fem,flutter,nastran,detailed,calibration
nastran <deck>.bdf                            # só com licença MSC/NX Nastran; comparar com o p-k do acdt
```

Corrida de validação neste PC (28 out 2026), em pastas novas para não substituir os resultados de referência:
`examples/output/cessna172_check_hifi_win` e `examples/output/uav_endurance_payload_hifi_win`.

* `cfd2d` do C172 correu (cruzeiro 791 s, perda 1999 s). cl_max RANS 1.815 contra 1.816 da referência; cd a cl 0.5 foi 0.01190 contra 0.01181.
* `gci` correu com três malhas e um só α (2°): 59450 / 34248 / 21132 células, r32 = 1,27 (abaixo de 1,3). Em cd, ordem p = 2,59 e GCI fino 8,9 %. cl e cm oscilam (U = 0,73 % e 1,51 %). A 4.ª malha foi corrida a 18 nov 2026 (107922 células, refine = 2, α = 2°); os α 0° e 4° continuam por correr. O ângulo por omissão do `acdt hifi` continua a ser 2° e três malhas. Números no parágrafo de 18 nov e em `h5_c172_gci.json`.
* `k_cd_profile` (~1,43 no C172, ~1,40 no UAV) compara RANS-SA totalmente turbulento com XFOIL com transição. O número e o GCI ficam no relatório; `valid` é falso e o fator não é aplicado. Um fator inline com o mesmo nome, sem `valid: false`, continua a aplicar-se.
* `wing_euler` do C172 correu uma vez (`--max-time-min 420`; a omissão da guarda continua 45 min) e não foi repetido. Malha de 825464 tetras, 900 s, α = 0° e 4°, residual −9. CLα Euler 4,69 /rad contra AVL 4,64 /rad (k = 1,01). CL a 0° foi 0,207 contra 0,172 do AVL: o desvio equivale a 0,42° (ΔCL / CLα). O STEP tem o ápice em x = 0 e incidência 0 (NACA 2412), como o `vsp_spec`. O CD é o eixo de vento do SU2 (−0,049 e −0,035), com S_ref = S/2 e monitorização só na asa. A mesma fórmula, no tutorial invíscido ONERA M6 do SU2 (582752 tetras, M = 0,8395, α = 3,06°, SU2 8.5.0, residual −12 em 129 s), devolve CL 0,284858 e CD +0,011967. O eixo e o sinal do binário estão certos. O CD negativo do C172 é a integral de pressão desta malha grosseira subsónica. Continua rejeitado (devia ser ≥ 0 e próximo de CL²/(π e AR)) e não entra como calibração. Não se correu um Euler novo do C172.
* FEM do C172 neste PC, com SPOOLES no estático e na encurvadura: flecha de ponta 0,382 m contra 0,203 m da viga (fora de ±50 %). A referência Linux, noutro dimensionamento, dava 0,249 m contra 0,276 m. Frequências 6,7 Hz e 23,5 Hz contra 8,54 Hz e 26,8 Hz. λ de encurvadura guardado 0,997 (ver o ponto do `*BUCKLE`). k_EI = 0,533 (válido). A comparação de torção usava o momento no quarto de corda e saía com o sinal trocado (k_GJ = −0,133). Passa a usar o momento a meio do caixão e o GJ de Bredt–Batho da Fase 3 (Megson Eq. 18.4, `details['GJ_phase3']`): a viga prevê +1,03° e o FEM guardado dá +1,14° (k_GJ ≈ 0,91). O FEM não foi refeito. Um caixão retangular fechado recupera θ′ = T/(GJ), com q = T/(2A), a 3 %. O PaStiX dava 1,47 mm e foi abandonado. Flutter a g = 0,03: 171 m/s e 168 m/s; requisito 1,2 V_D = 118 m/s.
* `rans_case` só escreveu o caso: cerca de 1.4e7 células, 25 GB, 47 h em 8 núcleos. Não há `mpiexec`.
* O OpenVSP continua em falta. O Euler e o RANS usaram o STEP já versionado.
* UAV: CalculiX 2.23 com SPOOLES no estático e na encurvadura. Flecha de ponta 0,154 m contra 0,11 m da viga (dentro de ±50 %; o PaStiX dava −8,8×10⁻⁷ m). λ guardado = 0,983 (o valor perto de 1 é o agrupamento do shift; ver abaixo). Frequências 9,03 Hz e 76,9 Hz contra 10,5 Hz e 79,8 Hz da viga. Flutter a g = 0,03: 132 m/s, referência Linux 127 m/s. k_EI = 0,715 (válido). A torção comparava o FEM com um GJ que não era o da viga (k_GJ = 0,217, cerca de 4,6×). Com o GJ de Bredt da Fase 3 e o momento a meio do caixão, a viga prevê +0,81° e o FEM guardado dá +0,77° (k_GJ ≈ 1,05). O FEM não foi refeito.
* Encurvadura `*BUCKLE` do CalculiX 2.23: o shift está fixo em σ = 1. O mesmo deck do UAV, com SPOOLES, dava λ 0,98–1,02 em 12 threads e 1,871 / 2,179 / 2,233 / 2,588 numa thread. O conjunto 1,83 / 2,13 / 2,19 / 2,54 do tutorial é esse espetro, noutro dimensionamento. O número de modos e a tolerância 1e-3 não mudam o fator. Um `*STATIC` anterior não é a pré-carga. Quando o fator verdadeiro está muito abaixo de 1, mesmo uma thread agrupa os modos em torno de 1; a carga é escalada até o fator sair do shift (placa de Timoshenko e Gere, k = 4, com λ = 0,05). Os `.inp` e `.dat` desse caso no Windows estão em `tests/data/ccx_buckle_win`. Os JSON de FEM já guardados não foram reescritos. O `*BUCKLE` corre com uma thread; o `*STATIC` mantém várias. O teste da placa faz o mesmo: com `OMP_NUM_THREADS=6` herdado, o fator escalado saiu 0,030 em vez de 0,050.
* Asa voadora sem deriva, um α (13 nov 2026, ramo `h1-tailless-wing-gci`). SU2 8.5.0 RANS-SA, OpenMP, 6 threads. Meia asa de estibordo, controlos alinhados, sem corpo, trem ou hélice. A espessura é a NACA simétrica do loft (`naca_yt`); o NACA 4415 do yaml é só o registo de tipo fixo. α = 9,52057° do AVL para o CL alvo 0,503, Mach 0,137, Re na Cref 1,755×10⁶, Xref 0,980 m, REF_AREA = S/2 = 1,593 m². A RefForce do SU2 é 1466,28 N, a 0,004 % de q·S/2. Três malhas pyHyp 2.6.3 (epsE 4, cMax 0,5, cornerAngle 150, campo a 100 cordas): 190464 / 512448 / 1451702 hexes, todas estanques e de volume positivo. Nenhuma chegou a rms[Rho] = −8 em 8000 iterações: grosseira −6,91 em 4148 s, média −7,48 em 11437 s, fina −7,67 em 33070 s. CL 0,87114 / 0,87547 / 0,87331 contra o AVL 0,50293. A razão do fino é 1,74, fora de [0,7, 1,5]. As três malhas concordam entre si. O GCI do CL é oscilatório (Stern et al. 2001; U = 0,25 % do CL fino) e o erro iterativo não é pequeno face à diferença fino–médio, porque essa diferença já é menor do que a deriva das últimas 10 % das iterações. CMy −0,04293 / −0,04010 / −0,03595 contra Cmtot do AVL +0,02889: razão −1,24, também fora da banda. Esse GCI não oscila, a ordem aparente é 0,93, o GCI fino é 38 % e o erro iterativo também não passa; a extrapolação continua negativa. CD 0,135 / 0,126 / 0,120 não se compara com o CDtot invíscido 0,01611. `valid` é falso nos três factores. Nenhum entra no L1/L2 e o yaml do exemplo não foi alterado. A constante de planeamento 4×10⁻⁶ s/célula/iter era cerca de 4 vezes baixa nesta CPU (taxa medida na malha grossa, 1,63×10⁻⁵ s/célula/iter por thread). A estimativa de RAM a 1,8 kB/célula dava 2,6 GB na malha fina; o conjunto de trabalho no início das iterações foi 8,4 GB, abaixo de 70 % dos 19,6 GB livres no arranque. Na malha fina o pyHyp imprimiu um volume nodal de −1,38×10⁻¹⁴ na camada 3; o hex correspondente no SU2 tem volume mínimo +1,62×10⁻¹⁴. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_wing_gci.json`. Polar, CLmax equilibrado, ΔCD/Cn do split e momentos de charneira não foram corridos.
* Diagnóstico da torção (14 nov 2026, ramo `h1-tailless-diagnostico`). O loft e o AVL escreviam a mesma torção de ponta, −10°, mas `Surface._frames` rodava a corda pela fórmula de Rodrigues com o ângulo trocado. Na malha grossa do cruzeiro a ponta media +9,994° de nariz para cima, com o bordo de fuga 72 mm abaixo do bordo de ataque, e a rotação era em torno do bordo de ataque. O AVL guarda `twist_deg` directamente no `Ainc` (nariz para cima positivo). O sinal do loft passou a ser o da docstring da classe. A ponta do desenho fica a −9,994° (bordo de fuga 72,07 mm acima do bordo de ataque) e o φ em torno da envergadura é −10,000°. O bordo de ataque não se move. Um caso de sanidade, torção 0° e α = 5°, na malha grossa, deu CL SU2 0,38260 contra CL AVL 0,36614 (razão 1,045) e CMy −0,01255 contra Cmtot −0,00537, os dois nariz para baixo. A referência e a normalização por S/2 ficam de pé: a RefForce foi 1466,28 N. Com a torção corrigida repetiu-se só o cruzeiro, α = 9,52057°, malha grossa nova em `cruise_washout` (190464 hexes, estanque, volume mínimo positivo, 4151 s, rms[Rho] −7,100). As pastas `coarse`, `medium` e `fine` não foram reescritas e o GCI não foi repetido. CL 0,41563 / 0,50293 = 0,826. CMy +0,03237 / Cmtot +0,02886 = 1,122. O Cmtot 0,02889 do `avl/st.txt` de 13 nov é o mesmo caso com Cref 0,72639 m; aqui a Cref do tessellation é 0,72712 m e o Xref mantém-se 0,98016 m. As duas razões caem dentro de [0,7, 1,5]. `h1_factor_decision` deixa `eligible` e `valid` falsos porque não há GCI novo e um só α não calibra a polar. Decisão `nao_aplicar`. O yaml não foi editado: `aero.tc_root` 0,15 e `tc_tip` 0,12 com NACA 4415 continuam a ser o registo de tipo fixo; o loft e o AVL usam t/c 0,13/0,10. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_twist_diagnostico.json`.
* Verificação da geometria antes de qualquer RANS de asa (14 nov 2026, ramo `h1-verificacao-geometria`). `verify_wing_rans_geometry` (`hifi/wing_bl.py`) corre dentro de `launch_wing_rans` (`hifi/cfd.py`) para qualquer asa com patches `upper`/`lower`, ficheiro AVL e caso SU2. Não houve corrida SU2 nem pyHyp; o acdt não os importa. A falha levanta `WingGeometryError` e o executável não é chamado. Mede a incidência real da raiz, das secções intermédias e da ponta e compara com o Ainc (tolerância declarada 0,05°). Confirma envergadura em +y, espessura em z, corda em +x, AOA no plano x-z (`SIDESLIP_ANGLE` = 0) e simetria em y = 0 (`MARKER_SYM`, bordo de ataque da raiz). Compara `REF_ORIGIN_MOMENT` com o Xref/Yref/Zref (1×10⁻⁴ m), a área e a envergadura da malha com Sref/Bref (tolerância relativa 1×10⁻³), `REF_AREA` e `REF_LENGTH` com a referência do AVL, e exige `SOLVER` RANS e `MOMENT_Y`. O sinal do CMy contra o Cm do AVL só passa quando os dois existem, são finitos, têm o mesmo sinal e nenhum é zero. Em falta ou zero fica `nao_avaliado`: não é aprovação e não bloqueia a primeira corrida, porque o coeficiente RANS ainda não existe. Sinais opostos bloqueiam. `pode_correr` é a ausência de falhas; `aprovacao_completa` exige que todos os itens, incluindo o sinal, passem. Na asa voadora escalada (n_chord = 17, n_span = 9) a incidência em torno da envergadura coincidiu com o Ainc a menos de 1×10⁻⁶ °; a projecção x-z da ponta afasta-se cerca de 0,006° pelo diedro e fica no relatório sem decidir. A área com a corda do bordo interior de cada painel reproduz Sref ao arredondamento (a corda local torcida dava 3,189 m² contra 3,186 m²). A envergadura, sem a tampa em semicírculo, fica a menos de 1×10⁻⁶ relativa de Bref. O AVL escreve o Xref com 5 decimais (no exemplo, 0,98016 m contra 0,980156 m). PRESSUPOSTO: o Ainc entre secções interpola-se na fracção do comprimento do bordo de ataque; a área é a de `Surface.planform_area`; com YDUPLICATE a malha é a meia asa de estibordo, Sref e Bref são os da asa completa e `REF_AREA` é Sref/2. Decisão `nao_aplicar`: nenhum factor entra no L1/L2. As malhas média e fina e o GCI de 13 nov continuam inválidos. O t/c 0,15/0,12 do yaml e a curvatura do NACA 4415 não foram alterados; a curvatura que fica de fora não foi inventada. A suite em `df96ad9`, antes desta alteração e com o AVL no PATH, foi 1027 testes a passar e 1 a falhar já no main: `test_tailless_example_closes_bare_fails_sas_passes` (`side_load_ok` no toque, `flightsim/mission.py`). Este ramo não mexe nesse teste. Testes novos, sem SU2: `tests/test_wing_rans_geometry.py`. A suite deste ramo, com o AVL no PATH, foi 1039 a passar e o mesmo teste a falhar (52 min).
* Espessura declarada no loft e no AVL (14 nov 2026, ramo `h1-seccao`). O exemplo declara t/c 0,15/0,12 e NACA 4415. O desenho e o `DRAWING` do H1 usavam 0,13/0,10. Os dois passam a 0,15 na raiz e 0,12 na ponta. A espessura do loft é `naca_yt` (Abbott & von Doenhoff 1959, Eq. 6.2, bordo de fuga fechado). O dígito 15 da designação não substitui o t/c declarado quando diferem; a ponta 0,12 não tem nome próprio. Entre a raiz e a ponta o t/c varia linearmente na fracção do comprimento do bordo de ataque. O JSON tem três secções: no meio, η = 0,5 e t/c = 0,135, e o cartão AVL é NACA 0014 porque `round(13,5)` = 14. O t/c guardado continua 0,135. O H1 tem duas secções, 0015 e 0012. A palavra NACA no AVL define a linha média (Drela & Youngren, AVL 3.40, `avl_doc.txt`, https://web.mit.edu/drela/Public/web/avl/avl_doc.txt); 00xx é plana. CLAF não é escrito, por isso a estimativa do guia CLaf = 1 + 0,77 t/c fica de fora: o mesmo texto diz que a viscosidade reduz o 0,77, e não há dado de secção. A curvatura do 4415 (4 % da corda a 0,4 c) lê-se nos dígitos e não é construída: estado `lacuna`, não zero. Uma designação que não é NACA de 4 dígitos fica `desconhecida`, também sem ser zero. O comentário em português entra no `.avl` só quando o estado é `lacuna`. O caixão estrutural continua a ler a designação pela função já existente `camber_from_name`; esta etapa não o altera, e o OML e o AVL da montagem não recebem essa linha média. O escritor AVL do tipo fixo, que escreve os dígitos com curvatura, também não muda. Os desenhos `flying_wing_pusher.json`, `flying_wing_pusher_closed.json` e os winglets ficam em 0,13/0,10. Comparação AVL externa, mesma planta, mesma torção −10°, mesmo cabeçalho (Sref 3,186 m², Cref 0,72712 m, Bref 4,38168 m, Xref 0,98016 m, Mach 0,13695, cartão `mn` 0,1370). A α = 9,52057°: 0013/0010 e 0015/0012 dão CLtot 0,50293, Cmtot 0,02886 e CDtot 0,01611. ΔCL = 0 e ΔCm = 0 no dígito impresso do `st.txt`. No CL alvo 0,50293 o α fica 9,52057° nos dois ficheiros. PRESSUPOSTO: sem CLAF o vórtice não vê o t/c, por isso o ΔCL = 0 não avalia a curvatura nem o efeito viscoso da espessura. A área de planta não muda. A envergadura da malha passa de 4,38168 m para 4,38187 m (o diedro dá à espessura uma componente y) e a Cref = S/b de 0,72712 m para 0,72709 m; essa mudança não entrou na comparação. Decisão `nao_aplicar`: não há factor para o L1/L2. `calibration.RATIO_BAND` e `H1_RATIO_BAND` não mudam. Não houve SU2 nem pyHyp. As malhas do GCI de 13 nov continuam inválidas. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_seccao_avl.json`. A suite deste ramo, com o AVL no PATH, foi 1047 a passar e 1 a falhar (54 min): o registo trazia um URL e `test_case_paths_stay_relative_and_tool_installs_are_basenames` lê `s:/` dentro de `https://` como caminho de Windows. O URL saiu do JSON e esse teste passou. O `side_load_ok`, que falhava no main, nesta corrida passou. A suite inteira não foi repetida depois de tirar o URL.
* GCI v2 da asa sem deriva, um α (15 nov 2026, ramo `h1-gci-v2`). Três malhas novas, secção `naca_yt` 0,15/0,12 e torção certa. `verify_wing_rans_geometry` passou nas três. 190464 / 512448 / 1451702 hex, pyHyp 2.6.3, campo a 100 cordas. Grossa e média com volume mínimo positivo. A fina tem um hex de −1,02×10⁻¹³ m³ na faixa do bordo de fuga, junto à ponta, na segunda camada; o pyHyp imprimiu volumes de camada positivos. `write_su2_volume` recusa volume não positivo por omissão. Esta família usou o piso `reject_below` = −1×10⁻¹² m³ e o auditor devolve o mínimo real. α = 9,52057° do AVL deste PC (CL 0,50293, Cmtot 0,02886, CDtot 0,01611). Publica-se, em cada malha, o final com rms[Rho] mais baixo. Grossa: 8000 iterações, rms −7,230, CL 0,41702, CD 0,03111, CMy +0,03191, 4434 s. Mais 4000 com CFL máximo 100 pioraram o rms para −6,25 (o CL mudou 0,24 %) e uma prova com CFL máximo 200 foi interrompida cerca do iter 100. Média: as 8000 iterações chegaram a −7,695 em 11371 s; a continuação com CFL de partida 100 cumpriu −8,001 ao iter 2674 (CL 0,41680, CD 0,02751, CMy +0,03215, 3811 s). Fina: 8000 iterações em 32407 s, rms −7,776; mais 4500 com CFL 100, 17231 s, ficaram em −7,968 (CL 0,41879, CD 0,02505, CMy +0,03166). Não se fez outra continuação. Celik et al., ASME J. Fluids Eng. 130 (2008) 078001, Fs = 1,25, h = (1/N)^(1/3), r21 = 1,415, r32 = 1,391. CL e CMy oscilam (Stern et al., ASME JFE 123 (2001) 793): U = 0,238 % do CL fino e 0,777 % do CMy fino, e `gci_fine` fica nulo. A deriva do CL na grossa (0,088 % nas últimas 10 %) é maior que 0,1 × |fino−médio|/|fino|, por isso `iterative_ok` é false. Razões do fino sobre o AVL: CL 0,833 e CMy 1,097, dentro de [0,7, 1,5], mas não elegíveis. O CD desce com a malha (p = 1,27, GCI fino 22,1 %, `iterative_ok` true, extrapolação de Richardson 0,0206). Não é o CDtot invíscido do AVL e a razão não é formada. Decisão `nao_aplicar`, `valid: false`. Um só α não aplicaria o factor mesmo com GCI monótono. O L1/L2 e o yaml não mudam. O `h1_wing_gci.json` de 13 nov não foi reescrito. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_wing_gci_v2.json`. Polar, CLmax equilibrado, split e charneira não foram corridos. A curvatura do 4415 continua por construir neste ramo. Suite no `main` `46dafcb`, com o AVL no PATH: 1056 passed e 1 failed (`test_case_paths`, caminhos absolutos escritos nos `mesh_audit.json` durante a preparação). Corrigidos para `wing.su2`, o scanner e `test_h1_wing_rans_mesh` deram 16 passed. A suite inteira não foi repetida.
* Linha média NACA de 4 dígitos (15 nov 2026, ramo `h1-curvatura`). `Surface.with_naca4_mean_line` liga, por superfície, a linha média de Abbott & von Doenhoff 1959, Eq. 6.4 (ordenada), Eq. 6.5 (inclinação) e Eq. 6.6 (coordenadas da pele). O loft por omissão, o `scaled_wing` e o yaml do exemplo ficam simétricos: cartões 0015/0012 e estado `lacuna`. `m = 0` não divide por p² e reproduz o loft simétrico. Uma designação sem curvatura, que não seja de 4 dígitos, ou com o segundo dígito 0, é recusada; não se trata como plana nem como zero. A espessura continua a ser `naca_yt` do t/c declarado. No opt-in da asa voadora o AVL passa a 4415 na raiz e 4412 na ponta (a meio, 0,135, o cartão é 4414). CLAF não é escrito. A malha de superfície com curvatura passa `verify_wing_rans_geometry`. A malha grossa RANS, 190464 hex da mesma família do GCI v2, correu com esse opt-in no α 9,52057° da malha simétrica. A verificação passou antes do SU2. 8000 iterações em 4134 s, rms[Rho] −6,673: não chegou a −8. CL 0,73034, CD 0,05173, CMy −0,07298. A deriva nas últimas 10 % é 0,20 % no CL, 0,32 % no CD e 0,51 % no CMy. O menor rms do histórico é −6,751 no iter 6921 (CL 0,73245) e não substitui o final. Mais 4000 iterações com CFL de partida 100, 2038 s, acabaram em rms −6,644 e pioraram o final. Não se usou CFL 200. AVL deste PC, cartões 4415/4412, no mesmo α: CLtot 0,81407, Cmtot −0,07963, CDtot 0,03893. Razões SU2/AVL: CL 0,897 e CMy 0,917, o mesmo sinal no momento, as duas dentro de [0,7, 1,5]. O equilíbrio AVL ao CL alvo 0,50293 baixa o α para 5,1714° (Cmtot −0,07409); esse α não foi corrido em RANS. Face à grossa simétrica (CL 0,41702, CD 0,03111, CMy +0,03191): ΔCL +0,313, ΔCD +0,021, ΔCMy −0,105. A Cref passa de 0,727086 m para 0,72715 m (Re 1,75638×10⁶) porque a curvatura muda a envergadura da malha; REF_AREA continua 1,593 m². Decisão `nao_aplicar`, `valid: false`. Uma malha e um α não são um GCI, e o CD do RANS não é o CDtot invíscido. O delta entre as duas grossas é geometria, não factor. O exemplo e o `scaled_wing` não foram editados. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_curvatura_grossa.json`.
* Polar da grossa simétrica (16 nov 2026, ramo `h1-polar`). O GCI não elegeu malha, por isso o varrimento usa a grossa de 190464 hex, cartões 0015/0012, controlos alinhados. A fina seria cerca de 9 h por α. Dezassete pontos, de −2° a 24°, com passo de 1° em 19° e 21°, 19,8 h no total. Nenhum chegou a rms −8. O cruzeiro a 9,52057° repetiu o GCI v2 (CL 0,41702). O CLmax com controlos alinhados é 1,059 a 20° (CD 0,123, CMy +0,0115, rms −6,75; a 19° é 1,037 e a 21° é 1,023). O momento não é nulo, portanto não está equilibrado. O CD viscoso é o CD do RANS menos o CDff do AVL no mesmo α (Trefftz). No ajuste CD viscoso = CD0 + K CL² para α ≤ 16°, antes da quebra de CD, CD0 = 0,0198. O buildup L1 dá CD0 da asa 0,00911 e da montagem 0,0272 nominal / 0,0324 pessimista. A razão da asa é 2,17, fora de [0,7, 1,5]. O CLmax equilibrado que fecha o dimensionamento L1 é 1,118. A razão 0,948 não é a mesma grandeza: o L1 leva a elevon ao batente −25° e o α linear a 32–39°, e a secção crítica corta o CL perto de 1,25. Esse ponto não foi corrido em RANS. Decisão `nao_aplicar`, `valid: false`. O exemplo não muda. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_polar_grossa.json`.
* Controlos da elevon na grossa (17 nov 2026, ramo `h1-controlos`). A split aberta não entra na extrusão: o pyHyp desta asa parte de uma superfície fechada, e rodar só a folha superior deixa de ser estanque. Um sólido sem fenda é outro dispositivo. A abertura assimétrica também não cabe numa meia asa com `MARKER_SYM`. ΔCD, Cn e C_h da folha superior ficam `nao_avaliado`. O L1 (McCormick 1995 Eq. 3.45, K_f = 1,7; NACA TN 690 Figs. 17–18 para |C_hf|) fica no registo como previsão, não como calibração. C1 desta asa é 0,01431 e Sf/S é 0,08641. PRESSUPOSTO já no L1: cf/c 0,40 está fora dos 0,15–0,25 da TN 690. C_hf = H/(q cf Sf) não é o Ch = H/(q Sref Cref) da elevon. A elevon é um flap selado, opt-in, η 0,20–0,45, charneira a 0,75c. δ positivo baixa o bordo de fuga. PRESSUPOSTO: com três ou mais estações, as dos extremos levam metade do ângulo (edge_scale 0,5); o cartão AVL aplica o ângulo pedido em todo o flap. Três malhas grossas próprias, 190464 hex, estanques, volume mínimo 1,71×10⁻¹¹ m³, marcha média 59,05 m. A verificação de geometria passou, inclusive o ângulo da pele. α = 9,52057°. O δ = 0 não foi re-corrido: é a grossa da polar (CL 0,41702, CD 0,03111, CMy 0,03191, rms −7,230). Essa polar não gravou a pressão de superfície, por isso não há ΔCh do RANS. Publica-se o final das 8000 iterações. Nenhum chegou a rms −8 e não houve continuação com CFL 100. A RefForce foi 1466,28 N nos três. δ = −10°: 4148 s, rms −7,105, CL 0,31891, CD 0,02868, CMy 0,04914, charneira 128/128, H −1,142 N·m, Ch −0,000535. δ = +10°: 4349 s, rms −7,160, CL 0,51329, CD 0,03961, CMy 0,01511, H −3,442 N·m, Ch −0,001614. δ = −25°: 4271 s, rms −7,101, CL 0,17273, CD 0,03321, CMy 0,07509, H +0,934 N·m, Ch +0,000438. AVL deste PC, cartão de quatro secções (raiz, η 0,20 a −2°, η 0,45 a −4,5°, ponta a −10°), mesmo α, cartão elevon com SgnDup +1. A δ = 0: CL 0,41633, Cmtot 0,03319, CDtot 0,01188, hm_raw −0,000812. δ = −10°: CL 0,28528, Cmtot 0,05807, hm_raw +0,001344 (por lado +0,000672). δ = +10°: CL 0,54643, Cmtot 0,00852, hm_raw −0,002962 (por lado −0,001481). δ = −25°: CL 0,08695, Cmtot 0,09577, hm_raw +0,004587 (por lado +0,002294). δ positivo sobe o CL e desce o CMy nos dois. Incrementos contra o δ = 0 de cada método: razões ΔCL 0,749, 0,740 e 0,742; razões ΔCMy 0,693, 0,681 e 0,690. O Ch compara-se com hm_raw/2. A +10° a razão é 1,09, o mesmo sinal. A −25° a razão é 0,191, o mesmo sinal, fora de [0,7, 1,5]. A −10° os sinais são opostos (Ch −0,000535 contra +0,000672) e a razão é −0,797. O integrador não foi invertido. O CD do RANS não se compara ao CDtot invíscido. O cartão de duas secções da polar, no mesmo α, continua a dar CL 0,50293. Estações intermédias com o Ainc de um bordo de fuga recto (−0,905° e −2,454°) recuperam CL 0,50308. A torção linear em graus dá CL 0,41633, ao lado do RANS 0,41702 (razão 1,002). Trocar o dígito de espessura deixa esse CL no mesmo sítio. A comparação da elevon usa o cartão de quatro secções. O GCI v2 não foi reescrito. Decisão `nao_aplicar`, `valid: false`, `eligible: false`. Uma malha e um α não aplicam factor, mesmo quando a razão cai em [0,7, 1,5]. O yaml mantém 8× Volz DA 30 (5,04 kg) nas splits e 2× Volz DA 30 (1,26 kg) nas elevons. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h1_controlos_grossa.json`.
* CalculiX do caixão (18 nov 2026, ramo `h2-calculix`). O caixão malhado é o do dimensionamento actual, t/c 0,15/0,12, método de encurvadura, CFRP por pressuposto do material: 6,429 kg (cordoalhas 0,355, peles do caixão 2,212, núcleo 0,788, almas 0,263, peles de bordo 1,401, nervuras 0,124). 3558 nós, SPOOLES. No arranque havia 19,16 GB livres (guarda 13,41 GB) e 208 GB de disco; a estimativa foi 0,78 GB e 0,32 min. A estática levou 7,64 s. Flecha de ponta: FEM 0,05786 m, viga da Fase 3 0,03301 m, k_EI = 0,571, dentro de [0,2, 5], `valid` true. Torção: FEM −0,483° e viga +0,430°. Os sinais são opostos, k_GJ = −0,891, `valid` false. O sinal não foi invertido. O primeiro factor de encurvadura linear à carga última é 0,854 (depois 1,059, 1,543 e 1,643). Não é o RF 1,00 da pele da Fase 6. Este dimensionamento trouxe `buckling_reserve` vazio e a base do caixão com a secção em espera trouxe nulo; os RF publicados não foram copiados. A primeira flexão FEM é 20,96 Hz (razão 0,750 com as faixas) e a primeira torção é 89,90 Hz (razão 0,949). O DLM p-k usa a grelha plana sem flap. Não houve cruzamento de g = 0,03 até 2,5 V_D; o varrimento até 6 V_D dá 279,7 m/s em g = 0 e 284,6 m/s em g = 0,03, margem 3,89 acima de 1,2 V_D (58,15 m/s). As faixas deste dimensionamento não cruzam até 4 V_D. A razão de flutter não é finita. A corrida gravou k_flutter = 0 ao dividir pela velocidade não finita; esse 0 não é uma medição e o código deixa de formar a razão. A inversão de comando por DLM fica `nao_avaliado`. Nas faixas, a base com `hold_section` (xf 0,20, xr 0,57, passo de nervura 0,462 m, não re-optimizada) pesa 5,885 kg. A elevon dessa base tem V_R não finito e η = 1,016 a 1,2 V_D. A η = 1,088 e os 5,47 kg são o estudo de 12 nov, t/c 0,13/0,10, e não são a mesma grandeza. O NLGEOM é `*STEP, NLGEOM` e `*STATIC`, incremento inicial 0,2 no período 1 (PRESSUPOSTO, automático, SPOOLES). Não é Riks. Um tubo com 20 N na ponta converge com esse cartão. O caixão à carga última (cerca de 3961 N e 3403 N·m) acabou aos 33,5 s com o código 201 e a mensagem de demasiados recuos do incremento, que chegou a 4,88×10⁻⁵. Não há flecha não linear. A flecha linear mantém-se. Riks fica `nao_avaliado`: esta versão lista a não-linearidade geométrica e a encurvadura linear, e não lista comprimento de arco. Decisão `nao_aplicar`. k_EI fica válido e de fora, porque o yaml não lista `structures` em `assumptions.calibration.apply`. k_GJ e k_flutter não são válidos. O exemplo não muda. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h2_calculix.json`.
* Ponte pyGeo do loft (18 nov 2026, ramo `h3-mphys`). Não há Docker Desktop neste PC. A imagem `mdolab/public:u22-gcc-ompi-stable`, actualizada a 17 nov, corre em udocker 1.3.17 no modo P1. Dentro dela importam ADflow 2.13.1, TACS 3.10.1, pyGeo 1.17.1, pyHyp 2.6.3, IDWarp 2.6.4 e MPhys 2.0.0. O processo acdt não importa nenhum deles. A ponte escreve a superfície do loft (17 por 9 por 9, 537 pontos únicos) e uma caixa FFD de 6 por 8 por 4. PRESSUPOSTO: a caixa é o limite alinhado aos eixos, aumentado 5 % em cada lado. No contentor, sem variável de projecto, o pyGeo devolve os mesmos pontos a 9,8×10⁻¹³ m. Isto confirma que o loft cabe na caixa. Não é uma malha de volume. Não há deck ADflow nem TACS deste loft, por isso o caso aeroestrutural de cruzeiro fica `nao_avaliado`. O CL 0,417 e o CMy 0,0319 da grossa SU2, e a flecha 0,0579 m do CalculiX, não são a mesma grandeza e não formam razão. `nao_aplicar`. O exemplo não muda. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h3_mphys.json`.
* Quarta malha do GCI da secção do C172 (18 nov 2026, ramo `h5-c172-gci`). NACA 2412, Re 4,873×10⁶, Mach 0,15, α = 2°. Malha refine = 2, 107922 células. Quatro rondas de 4000 iterações, a primeira mais três continuações a partir do restart. SU2 OpenMP, 6 threads, um processo. Cada continuação estimou 0,94 GB e 2,25 min; a ronda medida leva cerca de 11,6 min e a primeira levou 485 s. No arranque havia 19,6 GB livres e 198 GB de disco. Publica-se o final da última ronda, não o de menor residual: CL 0,47990, CD 0,010421, Cm −0,05605, rms[Rho] −3,99. A ronda anterior tinha rms −5,64. Deriva nas últimas 10 %: CL 4,5×10⁻⁴, CD 4,16×10⁻³, Cm 6,9×10⁻⁴. O critério 0,001 não foi cumprido no CD e não houve quarta continuação. O tripleto novo junta esta malha às 59450 e às 34248 células já guardadas. h = (1/N)^(1/2), r21 = 1,347, r32 = 1,318, os dois acima de 1,3. Celik et al. 2008, Fs = 1,25. CL monótono, p = 2,13, GCI fino 1,21 %, extrapolação 0,4753, `iterative_ok` true. CD monótono, p = 3,02, GCI fino 3,00 %, extrapolação 0,01017, `iterative_ok` false: a deriva excede 0,1 vezes a diferença relativa fino–médio. Cm monótono, p = 1,79, GCI fino 3,54 %, extrapolação −0,05446, `iterative_ok` true. O `gci/gci.json` não foi reescrito. Os α 0° e 4° não foram corridos. PRESSUPOSTO: são vizinhos da comparação cl = 0,5, não uma receita citada. O default continua a ser α = 2° e três malhas. `nao_aplicar`: um α, e o erro iterativo do CD não é pequeno. O yaml não muda. Registo: `examples/output/cessna172_check_hifi_win/h5_c172_gci.json`.
* RANS da asa e da fuselagem do C172 (18 nov 2026, o mesmo ramo). A fórmula de `full_aircraft_rans_case`, só com a área molhada da asa e da fuselagem (24,15 m² e 23,77 m²), dá 1,21×10⁷ células, 21,7 GB e 40 h em 8 núcleos para três α. O limite era 13,7 GB, 70 % de 19,6 GB livres. Não cabe. Engrossar o espaçamento de mac/100 para 0,0183 m baixa a conta para 6,9×10⁶ células e 12,4 GB. À taxa medida na asa voadora, 1,63×10⁻⁵ s/célula/iteração por thread, um α dessa malha leva 42 h, acima das 24 h autorizadas. PRESSUPOSTO: essa taxa, e o conjunto de trabalho 8,4 GB contra 2,6 GB da fórmula, são da malha hex da asa voadora e não foram medidos aqui. Com esse factor, 12,4 GB passam a cerca de 40 GB. Uma malha de cerca de 4,0×10⁶ células caberia em 24 h num α pela taxa medida e em 7,2 GB pela fórmula, mas o mesmo factor de memória passa o limite. Não há sólido só de asa e fuselagem, e a camada de prismas 3-D do caso escrito continua por verificar. Não se correu. O avião completo do `rans_case/estimate.json` (1,40×10⁷ células, 25,3 GB, 47 h) inclui as empenagens, não foi reescrito e não foi corrido. Trem e hélice não entram nessa área molhada e também não foram malhados. Ficam proposta escrita.
* RANS da asa e da fuselagem, nova medição (18 nov 2026, ramo `c172-rans-asa-fuselagem`). A mesma fórmula, com a área molhada viva da asa e da fuselagem (24,1507 m² e 23,7664 m²), volta a dar 1,207×10⁷ células, 21,731 GB e 40,24 h em 8 núcleos para três α. `int` dos triângulos de superfície dá 251517. Nesta medição havia 16,32 GB livres, limite 11,42 GB, disco 193,85 GB. `os.cpu_count` devolveu 12; isso não muda a taxa da fórmula. A guarda recusa: 21,7 GB passam o limite e 2415 min passam os 45 min de `tools.budget`. O solver não arrancou. Não se escreveu malha nem `.geo`: não há sólido só de asa e fuselagem e a camada de prismas 3-D continua por verificar. O plano de checkpoints é o que `su2_euler_cfg` já escreve (`RESTART_SOL`, `restart_flow.dat`, saídas `RESTART` e `SURFACE_CSV`; Economon et al., AIAA J. 54(3), 2016). O comprimento de cada bloco fica por escolher e não há ficheiro de restart. A malha engrossada já recusada não foi repetida. A polar L1 deste exemplo tem CD0 0,03855318, K 0,04690768 e CLmax limpo 1,54177 (Raymer Eq. 12.5 e Eq. 12.15). Não é CL, CD e Cm de um ângulo, por isso não há razão. O POH 172S no yaml traz velocidade, perda, subida e distâncias, e não traz uma tabela de CL, CD e Cm. As duas comparações ficam `nao_avaliado`. Decisão `nao_aplicar`. O L1 não fica validado nem calibrado. O yaml não muda. O `rans_case/estimate.json` do avião completo não foi reescrito. Registo: `examples/output/cessna172_check_hifi_win/h5_c172_rans_asa_fuselagem.json` e `h5_c172_rans_asa_fuselagem.csv`.
* pyCycle (18 nov 2026, ramo `h8-pycycle`). Não há deck termodinâmico L1 no caminho dos jatos. A comparação é com `turbofan_point`, a correlação L0 de turbofan de alta razão de bypass (Mattingly, Heiser e Pratt 2002, cap. 2; Ihme 2025, Eq. 2.77). Não foi rebatizada de L1. O pyCycle não entrou no `.venv` do acdt nem no processo: `om-pycycle` 4.4.0 e OpenMDAO 3.45.2 ficam noutro intérprete, apontado por `ACDT_PYCYCLE_PYTHON`. O caso é o `example_cycles/simple_turbojet.py` publicado (Hendricks e Gray, Aerospace 2019, 6, 87). No NumPy 2.5.5 a 4.4.0 pára em `ThermoAdd` antes do solver; a corrida usou um ajuste local, só nesse ambiente, que reduz um vector de comprimento 1 a um escalar e conserva o tipo, incluindo o passo complexo. Esse ajuste não está no repositório. Estimativa: 19,47 GB livres, limite 13,63 GB, tecto 1,5 GB, disco 197,5 GB, 15 min. O solver levou 2,11 s. Ponto de projecto, Mach cerca de 0, altitude 0, empuxo alvo 11800 lbf, T4 2370 R, razão de pressões 13,5: empuxo 11799,998 lbf (52489,0 N), TSFC 0,79852 lb/(lbf·h), OPR 13,5. A correlação L0 no mesmo Mach e altitude dá TSFC 0,400. Razão 1,996. Fora de projecto a Mach 0,2 e 1524 m, com empuxo comandado de 8000 lbf: TSFC 0,82951 contra 0,48150 da L0 em regime máximo, razão 1,723. O empuxo do pyCycle nesse ponto é a meta, não uma previsão; o empuxo máximo da L0 é 35068 N e não forma razão. O aviso de raiz quadrada em `static_ps_resid` apareceu; o empuxo cumpriu a meta a menos de 0,002 lbf. Isso não é um residual de Newton impresso. PRESSUPOSTO: o turbojato do exemplo (razão 13,5, T4 2370 R) não é o turbofan de alta razão de bypass da correlação. A razão de TSFC perto de 2 é diferença de classe de motor, não um factor. O empuxo ao nível do mar foi alinhado por escolha do empuxo estático da L0; esse alinhamento é de construção, e o TSFC da L0 não depende desse empuxo. A função L0 não foi editada. Decisão `nao_aplicar`. Registo: `examples/output/jet_pycycle/h8_pycycle.json`.
* pyCycle sem ajuste local (18 nov 2026, ramo `pycycle-sem-ajuste`). A etiqueta publicada 4.4.0, com OpenMDAO 3.41.0 e NumPy 1.26.4, em Python 3.12.0 e noutro intérprete, resolve o `example_cycles/simple_turbojet.py` dessa etiqueta sem editar `ThermoAdd`. O processo acdt não importa pyCycle. O script descarregado não foi alterado. O SHA-256 é `ad5a9378b341cc8a8c5e27592c8945e02bf2476c96ad07419e8ddd3ece8d13a4`. No arranque havia 16,86 GB livres, limite 11,80 GB, disco 193,9 GB. O tecto de 1,5 GB é o da corrida com o ajuste local e não é a memória medida deste processo. A impressão dos três pontos saiu em 3,66 s. O processo acabou com código 1 porque `map_plots` chama `plot_compressor_maps` e o matplotlib não está instalado. Os números impressos ficam e o gráfico não foi produzido. Apareceu o mesmo aviso de raiz quadrada em `static_ps_resid` e o aviso do NumPy 1.26 na linha de impressão. O empuxo impresso coincide com o alvo (11800,0 / 11000,0 / 8000,0 lbf). Isso não é um residual de Newton. Ponto de projecto, Mach de entrada 1×10⁻⁶ (impresso 0,00000), altitude 0, OPR 13,500, TSFC 0,79852 lb/(lbf·h). OD0: OPR 12,859, TSFC 0,78364. OD1: Mach 0,20000, 5000 ft = 1524 m, Fg 8812,5 lbf, Fram 812,5 lbf, OPR 12,203, TSFC 0,82951. A correlação L0 (Mattingly, Heiser e Pratt 2002, cap. 2; Ihme 2025, Eq. 2.77) dá TSFC 0,40000045 nos dois pontos ao nível do mar e 0,48150375 no OD1. As razões impressas são 1,996, 1,959 e 1,723, fora de [0,7, 1,5]. `same_quantity` é falso, por isso a razão de decisão fica ausente e a razão impressa não calibra. O empuxo L0 é o de classificação máxima (116342,96 N ao nível do mar e 77765,93 N no OD1, com `thrust_sl_N` por omissão) e o Fn do pyCycle é o alvo comandado. Não se forma razão de empuxo. Não há deck termodinâmico L1. `engine_map` aceita, e este turbojato não tem, os campos de tabela `source`, `mach`, `altitude_m`, `throttle`, `thrust_lapse`, `thrust_installed_N` e `TSFC_kg_N_s`, nem os de tabela corrigida `source`, `mach`, `altitude_m`, `throttle`, `F_over_delta`, `SFC_over_sqrt_theta` e `totals`. O mapa também não guarda OPR, W, Fg, Fram, FAR, Wfuel, T4, `comp_eff`, `turb_eff`, Nmech nem totais de estação. `examples/jet/engine_map_table.yaml` é uma tabela PRESSUPOSTO de transporte, amostrada da correlação L0, e não foi editada. O `h8_pycycle.json` do ajuste local não foi reescrito. Decisão `nao_aplicar`. O modelo L0 não fica validado nem calibrado. O modelo L1 fica `nao_avaliado`. O yaml dos exemplos não muda. Registo: `examples/output/jet_pycycle/h8_pycycle_sem_ajuste.json` e `h8_pycycle_sem_ajuste.csv`.
* OpenVSP e VSPAERO (18 nov 2026, ramo `h7-openvsp`). O Windows não tem executável OpenVSP e `ACDT_VSP_PYTHON` está vazio. Não se descarregou instalador. A corrida é o OpenVSP 3.48.2 do contentor MDO Lab (udocker, modo P1). O visor do VSPAERO não está na imagem. O contentor não vê o disco do Windows: o caso é copiado para a pasta pessoal partilhada com o contentor e as saídas voltam depois. Isto não substitui o OpenVSP do Windows. O processo acdt não importa `openvsp`. O gestor de análises escreve o caso com `StopBeforeRun` e o binário `vspaero` 7.2.2 corre à parte, porque o lançamento pelo gestor não regressa. LenUnit lido de volta é 2, igual a `LEN_M`: o STEP está em metros. Asa voadora, sem fuselagem nem caudas: torção 0°/−10° com Twist_Location 0, ThickChord 0,15/0,12, curvatura 0, enflechamento 28° no bordo de ataque, diedro 2°. A ponta medida tem nariz −10,0° e o bordo de fuga 72,1 mm acima do bordo de ataque. Os bordos de ataque coincidem com o loft. O amostrador de t/c da API não mede a pele (os dois parâmetros de contorno caem no mesmo ponto). Na STL, 2704 triângulos, a 40 % da corda, dz/c na raiz é 0,145. Não é o máximo de Abbott. O painel grosso escreveu um `.vspgeom` de 770787 bytes, o solver carregou-o e saiu com código 1: não encontrou a aresta global da esteira (nós 1363 e 1364). Sem histórico e sem coeficientes. A superfície fina (`GeomSet` vazio, `ThinGeomSet` em todas) escreveu 276696 bytes e o solver acabou com código 0 em 0,44 s. Estimativa no arranque: 19,53 GB livres, limite 13,67 GB, tecto 0,8 GB, disco 197,9 GB, 20 min. O tecto é um pressuposto de um VLM, não uma medição. Referência forçada: Sref 3,186 m², Cref 0,727086 m, Bref 4,38187 m, Xcg 0,980156 m, Mach 0,136954, α 9,52057°, WakeIters 5, StallModel 0, NCPU 4. ReCref 1,756×10⁶ fica escrito e não é uma solução viscosa. Vinf 100 e Rho 0,002377 ficaram nos defaults; com StallModel 0 não escalam o CL. Não se alterou a unidade da densidade. Iteração 5: CLtot 0,49394, CDi 0,014302, CDtot 0,02231, CDo 0,008005, CMytot 0,04164. O CDi da esteira (coluna CDiw) é 0,01666 e não é o número comparado. AVL deste PC, cartão de duas secções, o mesmo α: CL 0,50293, CDff 0,014536, Cmtot 0,02886, CDtot 0,01611. Razões 0,982, 0,984 e 1,443. O momento tem o mesmo sinal. O CDtot do AVL não é o CDtot do VSPAERO e o CDo não é o arrasto parasita do avião. A geometria é a mesma (bordo de ataque medido). A malha não é: tess 41 por 16 contra nchord 12 e nspan 40. PRESSUPOSTO: cinco iterações de esteira não são convergência. O residual L2 na iteração 5 é −1,92 e ainda descia desde a iteração 3. O CL das iterações 3 a 5 fica em 0,4940. A banda [0,7, 1,5] é SU2/AVL e não se aplica aqui. Decisão `nao_aplicar`. O yaml não muda. O C172 foi exportado e não teve VSPAERO. Asa: z 0,52943 m, incidência 0, diedro 3°, enflechamento 0 em c/4, ThickChord 0,12, curvatura 0,02 em 0,4, torção 0. Áreas molhadas, sem o MeshGeom: fuselagem 10,310, asa 13,495, estabilizador 2,227, deriva 0,811, soma 26,843 m². O CompGeom Linux 3.55.0 já guardado soma 54,991 m², cerca do dobro em cada componente. A planta da asa é 13,90 m², perto da molhada 3.48.2 e de metade da molhada 3.55.0. Não é uma conversão pé/metro (esse factor seria cerca de 10,8). A diferença de versão não é uma exportação falhada. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h7_openvsp.json`.
* RCS com duas reflexões (18 nov 2026, ramo `h6-rcs-bounces2`). O loft é o da asa sem deriva já com a torção corrigida: ponta −10°, bordo de fuga 72,1 mm acima do bordo de ataque, incidência −9,994° (nariz para baixo), t/c 0,15/0,12, linha média por construir. As duas metades entram, 192 facetas, uma baía em envergadura de cada lado. PO a 10 GHz, Gordon 1975 e Knott, Shaeffer e Tuley 1993, cap. 5. A segunda reflexão é Ling, Chou e Lee, IEEE TAP 37(2) 1989. Sector |az| ≤ 30°, passo 0,5°, elevações −5°, 0° e 5°, VV e HH, oclusão ligada. Estimativa 0,05 GB e 1,6 min; havia 19,6 GB livres e 198 GB de disco. Uma reflexão, 1,17 s: média −10,03 dBsm, mediana −34,95 dBsm, máximo 8,24 dBsm, e VV coincide com HH. Duas reflexões, 136 s: VV média −7,49 dBsm, mediana −14,65 dBsm, máximo 8,06 dBsm; HH média −9,73 dBsm, mediana −25,16 dBsm, máximo 8,37 dBsm. O acréscimo da média é 2,54 dB em VV e 0,30 dB em HH. No nariz (az = 0°, el = 0°, VV) passa de −41,13 dBsm para −18,55 dBsm. Esse aspecto é de bordo e o PO aí é fraco; o número não é uma medição. Fuselagem, derivas de ponta, trem, hélice, deflexão e difracção de bordo ficam `nao_avaliado`, não zero. A onda completa (MoM/MLFMM ou FDTD) não correu: fica proposta. `nao_aplicar`. Não há RCS medido e a malha não tem convergência. O exemplo não muda. Registo: `examples/output/uav150_flying_wing_tailless_hifi_win/h6_rcs_bounces2.json`.
* Proposta térmica e de gelo de alta fidelidade (18 nov 2026, ramo `termico-gelo-proposta`). Não se correu solver nem se escreveu malha. O compartimento L0/L1 continua um nó de dois (Incropera; [TERMICA.md](TERMICA.md)): não há sólido, por isso a contagem de células fica em falta e não é zero. Os `.cfg` já escritos têm `MARKER_HEATFLUX = 0`; parede adiabática não é o balanço do compartimento e não há caso conjugado. O OpenFOAM permanece stub GPL-3.0, processo separado, sem arranque. No gelo, a linha de estagnação (Apêndice C, Langmuir e Blodgett, Messinger via Anderson) não ganha malha de acreção. O LEWICE não está em `THIRD_PARTY.md`, não foi instalado e não entra no processo. O Apêndice O e as formas da NASA IRT continuam ausentes. Sem malha, o custo em GB e em horas fica `nao_avaliado`; a guarda de `tools.budget` não foi contornada com um número inventado. O L0 e o L1 não ficam validados nem calibrados. Decisão `nao_aplicar`. O yaml não muda. Registo: `examples/output/termico_gelo_proposta/proposta.json`. Texto: [proposta-termica-gelo.md](proposta-termica-gelo.md).
* Proposta de RCS de onda completa (18 nov 2026, PR #27, ramo `rcs-onda-completa-proposta`). Não se correu o openEMS e não se escreveu grelha. O PO a 10 GHz, já em `h6_rcs_bounces2.json`, tem média frontal VV de −7,491 dBsm com duas reflexões. Não é onda completa e não forma razão. λ = c/f = 0,029979 m, com c = 299 792 458 m/s. PRESSUPOSTO: Δx = λ/10. Sem caixa de cálculo, o número de células fica em falta. O openEMS está em `THIRD_PARTY.md` como GPL-3.0 e só como executável externo; não foi arrancado e não entra no processo. Não há binário MoM/MLFMM escolhido. O custo do PO, 0,05 GB, não é o custo FDTD. O L1 fica `nao_avaliado`. Decisão `nao_aplicar`. O yaml não muda. Registo: `examples/output/rcs_onda_completa_proposta/proposta.json`. Texto: [proposta-rcs-onda-completa.md](proposta-rcs-onda-completa.md).
* Os JSON de HiFi em `*_hifi_win` guardam caminhos relativos à pasta do caso. O executável fica só com o nome (`ccx.EXE`). As referências Linux em `*_hifi` não foram reescritas. O `wing_half.geo` do Euler do C172 aponta o STEP com `../../cessna172_check_hifi/geometry/cessna172_check_wing.step`, porque o Gmsh arranca na pasta do `.geo`. Já não leva `C:/Users/...`. O `.su2` e o `wing_euler.json` não foram reescritos.

* **FEM não linear** (18 nov 2026, ramo `h2-calculix`). O cartão é `*STEP, NLGEOM` seguido de `*STATIC`
  (incremento inicial 0,2, período 1, PRESSUPOSTO). A estática linear mantém-se. Não há cartão de Riks e o
  passo não entrou na lista por omissão de `acdt hifi`. No caixão da asa sem deriva, à carga última, o
  solver devolveu o código 201 e não há flecha. O número está no parágrafo do CalculiX e em `h2_calculix.json`.
* Guarda de computação: casos acima de 70 % da RAM são recusados; via MCP os passos pesados exigem
  `user_approved=true` (e `ACDT_MCP_HEAVY` ≠ `never`).

## 4b. Para o Grok Build (pesado, no PC do João)

Regra (João, 3 nov 2026): tudo o que é pesado corre no PC do João pelo Grok Build, nunca no box da nuvem.
O ramo `p1c-optimizer-assembly` só implementa os caminhos de código, as interfaces e testes pequenos.
Cada corrida abaixo grava o resultado num JSON; o critério de aceitação diz quando o resultado volta ao L1/L2.

### H1. GCI RANS-SA da asa sem deriva — um α (13 nov 2026)

Meia asa do exemplo `uav150_flying_wing_tailless`, controlos alinhados, um α de cruzeiro. O critério era a banda [0,7, 1,5] em CL e em Cm, contra o AVL da mesma asa simétrica, no mesmo α e no mesmo Xref, e um GCI de Celik et al. 2008 com h = (1/N)^(1/3). Um só α não calibra a polar: mesmo dentro da banda o factor fica elegível e não se aplica.

**Resultado.** Corre no PC (SU2 OpenMP, sem `mpiexec`). CL fino / CL AVL = 1,74 e CMy / Cmtot = −1,24, os dois fora da banda. O CD do RANS não é a mesma grandeza que o CDtot invíscido. Decisão `nao_aplicar`, `valid: false`. O L1/L2 e o W0 do exemplo ficam como estavam. O G3 (CD0 da montagem, por componente) não foi feito: esta malha não tem corpo, trem nem hélice. Detalhe e números em §4 e em `examples/output/uav150_flying_wing_tailless_hifi_win/h1_wing_gci.json`.

**Torção (14 nov 2026).** Aquele loft tinha a ponta a +10° com o valor escrito −10°. O sinal em `Surface._frames` foi alinhado com o `Ainc` do AVL. Sanidade a α = 5° e torção 0°: razão de CL 1,045. Cruzeiro repetido só na malha grossa: CL 0,826 e CMy 1,122, dentro da banda, mesmo sinal no momento. Continua `nao_aplicar`: não há GCI novo e o α é um só. Nessa correcção o t/c 0,15/0,12 do yaml ainda não estava alinhado com o 0,13/0,10 do loft. Números em `h1_twist_diagnostico.json`.

**Geometria antes do RANS (14 nov 2026).** Qualquer RANS de asa passa primeiro por `verify_wing_rans_geometry`: incidência da malha contra o Ainc (0,05°), eixos, origem do momento, área e envergadura contra Sref/Bref. A falha bloqueia a corrida. Sem os dois momentos, o sinal do CMy fica `nao_avaliado` e não conta como aprovação. Não houve SU2 nem pyHyp. Decisão `nao_aplicar`. O GCI de 13 nov, com a torção trocada nas malhas média e fina, permanece inválido. O t/c do yaml e a curvatura ficam para a etapa seguinte.

**Espessura (14 nov 2026).** O loft e o AVL usam agora o t/c do yaml, 0,15/0,12, na espessura NACA simétrica (`naca_yt`). A linha média do NACA 4415 não é construída (`lacuna`). Com o mesmo cabeçalho e a mesma α = 9,52057°, passar de NACA 0013/0010 para 0015/0012 não mexe no CLtot 0,50293 nem no Cmtot 0,02886. CLAF não foi escrito. Decisão `nao_aplicar`. O GCI de 13 nov continua inválido. O GCI v2, com esta secção, está no parágrafo seguinte. Números em `h1_seccao_avl.json`.

**GCI v2 (15 nov 2026).** Três malhas novas, t/c 0,15/0,12 simétrico e torção certa, no α do AVL deste PC. CL fino/AVL = 0,833 e CMy/Cmtot = 1,097, os dois dentro de [0,7, 1,5]. CL e CMy oscilam (U = 0,24 % e 0,78 % do valor fino) e o erro iterativo do CL não é pequeno face à diferença fino–médio. O CD tem GCI fino 22 % e não se compara ao CDtot invíscido. A média cumpriu rms −8; a grossa ficou em −7,23 e a fina em −7,97 depois de mais 4500 iterações. Decisão `nao_aplicar`, `valid: false`. Um α não calibra a polar. O yaml e o L1/L2 não mudam. Números em `h1_wing_gci_v2.json`.

**Linha média (15 nov 2026).** O opt-in `with_naca4_mean_line` constrói a linha média NACA de 4 dígitos (Abbott & von Doenhoff 1959, Eq. 6.4–6.6) no loft e no cartão AVL. O exemplo e o `scaled_wing` continuam simétricos. `p = 0` com curvatura é recusado. A grossa com o 4415 real, no α da malha simétrica, deu CL 0,73034 e CMy −0,07298 contra o AVL 4415/4412 (0,81407 e −0,07963): razões 0,897 e 0,917, dentro da banda e com o mesmo sinal. Não chegou a rms −8 (final −6,673; a continuação com CFL 100 piorou). Decisão `nao_aplicar`: uma malha, um α, sem GCI. O CD não é a mesma grandeza que o CDtot. Números em `h1_curvatura_grossa.json`.

**Polar grossa (16 nov 2026).** Dezassete α na grossa simétrica, porque o GCI não elegeu malha. CLmax com controlos alinhados: 1,059 a 20°. CD0 viscoso, RANS menos CDff do AVL, ajuste até 16°: 0,0198, contra 0,00911 da asa no buildup (razão 2,17, fora da banda). O CLmax equilibrado do L1 é 1,118 e não é a mesma grandeza. `nao_aplicar`. Números em `h1_polar_grossa.json`.

**Controlos (17 nov 2026).** Elevon selada na grossa, α 9,52057°, δ −10°, +10° e −25°. A split fica `nao_avaliado`: a fenda não cabe na extrusão fechada e a abertura assimétrica não cabe na meia asa. O C_hf da TN 690 não é o Ch da elevon. O δ = 0 é o da polar (CL 0,41702). RANS: CL 0,31891 / 0,51329 / 0,17273 e Ch −0,000535 / −0,001614 / +0,000438, charneira 128/128. O AVL de quatro secções, com a torção linear em graus, dá CL 0,41633 a δ = 0, ao lado desse RANS; o cartão de duas secções (CL 0,50293) recupera-se com um bordo de fuga recto. δ positivo sobe o CL e desce o CMy nos dois. O Ch a −10° tem o sinal oposto ao HM por lado; a −25° a razão é 0,191; a +10° é 1,09. `nao_aplicar`: uma malha, um α, sem GCI. Os atuadores não mudam. Números em `h1_controlos_grossa.json`.

**Estruturas / CalculiX (18 nov 2026).** Caixão do dimensionamento actual, t/c 0,15/0,12, 6,429 kg, 3558 nós, SPOOLES, 7,64 s. k_EI = 0,571, válido em [0,2, 5] e por aplicar: o yaml não liga o grupo `structures`. k_GJ = −0,891, sinais opostos, inválido. A encurvadura linear mínima à carga última é 0,854 e não é o RF 1,00 da Fase 6. Esse estudo (5,47 kg, t/c 0,13/0,10, η = 1,088) não foi repetido. A base com a secção actual, sem re-optimizar, pesa 5,885 kg e a elevon tem η = 1,016. O DLM p-k cruza a 284,6 m/s (g = 0,03), acima de 1,2 V_D; as faixas não cruzam até 4 V_D. k_flutter não é uma razão finita. A inversão por DLM fica `nao_avaliado`. O NLGEOM do caixão acabou com o código 201, sem flecha. Riks não é um cartão desta versão. `nao_aplicar`. Números em `h2_calculix.json`.

**MPhys / pyGeo (18 nov 2026).** A imagem pública do MDO Lab corre em udocker, sem Docker Desktop. ADflow 2.13.1, TACS 3.10.1, pyGeo 1.17.1 e MPhys 2.0.0 importam dentro do contentor. O FFD do loft, 537 pontos, fica no sítio a 9,8×10⁻¹³ m quando não há variável de projecto. O cruzeiro ADflow+TACS não correu: a caixa não é uma malha de volume e não há deck. Não há razão contra o CL 0,417 da grossa nem contra a flecha do CalculiX. `nao_aplicar`. Números em `h3_mphys.json`.

**Secção do C172 (18 nov 2026).** A quarta malha do NACA 2412, 107922 células, α = 2°, não é esta asa. Não altera a banda [0,7, 1,5], o yaml nem os factores do H1. O CD dessa malha fica com deriva 0,42 % e `iterative_ok` false. O RANS da asa com fuselagem do C172 estima 21,7 GB e não correu. `nao_aplicar`. Números em `examples/output/cessna172_check_hifi_win/h5_c172_gci.json`.

**RANS asa e fuselagem, nova medição (18 nov 2026).** A fórmula volta a dar 21,731 GB e 40,24 h. Havia 16,32 GB livres e o limite era 11,42 GB. O solver não arrancou. O plano de restart do SU2 fica escrito e sem bloco de iterações, porque não há corrida. A polar L1 (CD0 0,03855, K 0,04691, CLmax 1,542) e o POH do exemplo não são CL, CD e Cm desta malha. `nao_avaliado`. `nao_aplicar`. Números em `h5_c172_rans_asa_fuselagem.json`.

**RCS, duas reflexões (18 nov 2026).** No loft com a torção corrigida, o PO a 10 GHz dá média frontal −10,03 dBsm com uma reflexão e −7,49 dBsm em VV com duas (HH −9,73 dBsm). VV e HH coincidem na primeira reflexão. Não há RCS medido, a malha tem uma baía em envergadura, e a onda completa não correu. `nao_aplicar`. A banda do H1 não entra. Números em `h6_rcs_bounces2.json`.

**Térmica e gelo de alta fidelidade (18 nov 2026).** Proposta apenas. Não há sólido da baía nem malha de acreção, e não se inventou a contagem de células. O `SU2_CFD` adiabático e o LEWICE não foram arrancados. O L0 e o L1 ficam `nao_avaliado`. `nao_aplicar`. Números em `examples/output/termico_gelo_proposta/proposta.json`.

**pyCycle (18 nov 2026).** O turbojato simples do pyCycle 4.4.0, noutro intérprete, dá TSFC 0,79852 lb/(lbf·h) no ponto de projecto. A correlação L0 de turbofan de alta razão de bypass dá 0,400. Não há deck L1. A instalação limpa no NumPy 2.5.5 não chega a resolver; os números saíram depois de um ajuste local que não está no repositório. `nao_aplicar`. A correlação não muda. Números em `h8_pycycle.json`.

**pyCycle sem ajuste (18 nov 2026).** OpenMDAO 3.41.0 e NumPy 1.26.4, com a 4.4.0 publicada e sem editar `ThermoAdd`, imprimem TSFC 0,79852 / 0,78364 / 0,82951. A correlação L0 dá 0,40000045 / 0,40000045 / 0,48150375. A razão de decisão fica ausente: as classes de motor diferem e a razão impressa não calibra. O L0 não fica validado nem calibrado. O L1 fica `nao_avaliado`: não há grelha deste turbojato. Os campos em falta estão no JSON. O gráfico final não correu e o código de saída foi 1, depois dos três pontos. `nao_aplicar`. Números em `h8_pycycle_sem_ajuste.json`. O `h8_pycycle.json` não foi reescrito.

**OpenVSP / VSPAERO (18 nov 2026).** Nesse registo o Windows ainda não tinha OpenVSP. O 3.48.2 do contentor exporta a asa e o C172 e não substitui o instalador. O VSPAERO fino, no α do AVL, dá CL 0,49394 contra 0,50293, CDi 0,014302 contra CDff 0,014536 e CMytot 0,04164 contra Cmtot 0,02886. O painel grosso morreu na esteira e não entra na comparação. Cinco iterações não são convergência. `nao_aplicar`. A banda do H1 não entra. O VSPAERO do C172 não correu. Números em `h7_openvsp.json`.

**Painel grosso no Windows (18 nov 2026, ramo `win-openvsp-esteira`).** O OpenVSP 3.56.0 está neste PC: o zip `OpenVSP-3.56.0-win64-Python3.13` descarregou e `import openvsp` imprime essa versão. O processo acdt não importa `openvsp`. O gestor escreve o caso com `StopBeforeRun` e o `vspaero.exe` corre noutro processo, 4 threads, 2,19 s. Asa voadora, tess 41×16, sem fuselagem nem caudas. Conjunto grosso: GeomSet 0 (`SET_ALL`) e ThinGeomSet −1 (`SET_NONE`). A esteira escrita e lida de volta é o default desta versão: WakeNumIter 5, NumWakeNodes 8, WakeRelax 1, FixedWakeFlag 0, ImplicitWake 0. O CHANGELOG 3.45.0 (2025-07-18) descreve a esteira implícita; ImplicitWake fica 0. A linha do 3.46.0, «Fix TE wake detection for VSPAERO», não é tomada como causa. O `ComputeCompGeom` deixa dois `MeshGeom`. Com eles dentro do `SET_ALL` a história saiu não finita, por isso são apagados antes do solver. Iteração 5: CL 0,52862, CDi 0,024897, CDtot 0,039919, CMytot 0,035399, CLiw 0,54191, CDiw 0,019933, residual L2 −0,695 (na iteração 4 era +0,256). Rho 0,002377 e Vinf 100 são os do cabeçalho. StallModel 0, portanto o ReCref escrito não torna a solução viscosa. O AVL desta corrida, cartão de duas secções, dá α 9,52057°, CL 0,50293, CDff 0,014536, Cmtot 0,02886 e CDtot 0,01611. Razões CL 1,051 e Cm 1,227, o mesmo sinal. A razão informativa CDi/CDff é 1,713 e fica fora de [0,7, 1,5]. CDiw/CDff é 1,371. O CDtot do VSPAERO inclui o CDo. Cinco iterações não são convergência. Decisão `nao_aplicar`, `valid` false, `applied` false. O modelo L1 (AVL) não fica validado e não é calibrado. O yaml não muda. RAM livre 17,01 GB, limite da guarda 11,91 GB; o teto de 0,8 GB vem do registo fino e não é uma medição desta malha. Números em `h7_vspaero_painel.json` e `h7_vspaero_painel.csv`. O 3.48.2 continua em `h7_openvsp.json`.

**RCS de onda completa (18 nov 2026, PR #27).** Proposta apenas. O openEMS não arrancou. A média PO de −7,491 dBsm não é onda completa. Sem caixa de cálculo, as células ficam em falta. `nao_avaliado`. `nao_aplicar`. Números em `examples/output/rcs_onda_completa_proposta/proposta.json`.

### Cadeia H1–H8 do Build (18 nov 2026), integrada

O histórico público começa em `dcca304`, que já inclui o GCI v2, a linha média 4415 e a polar da grossa (todos `nao_aplicar`). As etapas seguintes foram portadas do repositório privado e merged no `main` (até `4959ffe`), todas `nao_aplicar`, sem alterar os yaml dos exemplos:

1. #1 `h1-controlos`: elevon na grossa, CL 0,31891 / 0,51329 / 0,17273 em δ −10° / +10° / −25°.
2. #2 `h2-calculix`: k_EI 0,571 válido e por aplicar; k_GJ −0,891 inválido; NLGEOM com código 201.
3. #3 `h3-mphys`: FFD com desvio 9,8×10⁻¹³ m; cruzeiro ADflow+TACS por avaliar.
4. #4 `h5-c172-gci`: GCI fino de CD 3,0 % com erro iterativo; RANS de asa e fuselagem não coube (21,7 GB).
5. #5 `h6-rcs-bounces2`: duas reflexões, VV −7,49 dBsm; onda completa por correr.
6. #6 `h7-openvsp`: VSPAERO fino, CL 0,49394 contra AVL 0,50293.
7. #7 `h8-pycycle`: TSFC 0,79852 contra 0,400 da correlação L0 (classe de motor diferente).

O que fica para o João: o visor do VSPAERO no contentor 3.48.2; a onda completa do RCS, só como proposta; o RANS de asa e fuselagem do C172, medido de novo com 16,32 GB livres e limite 11,42 GB, que continua sem correr (21,731 GB e 40,24 h); um deck L1 de motor, que não existe; a térmica e o gelo de alta fidelidade, que ficam em proposta sem malha e sem corrida (`proposta.json`). A instalação publicada de pyCycle 4.4.0 com OpenMDAO 3.41.0 e NumPy 1.26.4 resolve o turbojato sem o ajuste local de `ThermoAdd`. O deck L1 continua ausente: faltam os campos de `table` e de `corrected_table` listados em `h8_pycycle_sem_ajuste.json`, e o mapa não guarda OPR, T4, eficiências, FAR, caudais nem totais de estação. A comparação L1 fica `nao_avaliado`. O OpenVSP 3.56.0 no Windows e o painel grosso, com a esteira no default documentado, estão feitos e ficam `nao_aplicar`, sem factor. Nenhum factor foi aplicado e o yaml dos exemplos não mudou. Os ficheiros pesados que já estavam fora do git continuam fora.

### Estado das cinco tarefas (18–19 nov 2026)

Os cinco PR desta cadeia entram no `main` por esta ordem.

1. PR #23, `win-openvsp-esteira`, integrado (`5c58b68`). O OpenVSP 3.56 no Windows correu o painel grosso com a esteira nos defaults lidos de volta. O AVL não fica validado nem calibrado. `nao_aplicar`. Não está bloqueado.
2. PR #24, `pycycle-sem-ajuste`, integrado (`3062bd6`). OpenMDAO 3.41.0 e NumPy 1.26.4 resolvem o turbojato publicado sem o ajuste de `ThermoAdd`. O gráfico final falhou depois da impressão. O L0 fica `nao_aplicar` (outra classe de motor). O L1 fica `nao_avaliado`: o deck não existe e os campos em falta estão no JSON. Não está bloqueado por solver; o deck é que continua ausente.
3. PR #25, `c172-rans-asa-fuselagem`, integrado (`454a2d4`) e bloqueado na corrida. A fórmula já registada dá 21,731 GB e 40,24 h, com 2415 min contra 45 min. Na primeira medição havia 16,32 GB livres e o limite era 11,42 GB. Nova leitura de `Win32_OperatingSystem`: 16,34 GB livres de 31,86 GB, limite 11,44 GB. A fórmula não foi refeita. O solver não arrancou. A malha não foi engrossada. O L1 fica `nao_avaliado`. `nao_aplicar`.
4. PR #26, `termico-gelo-proposta`, integrado (`a4156db`). Só proposta: sem sólido da baía, sem malha de acreção e sem corrida. O L0 e o L1 ficam `nao_avaliado`. `nao_aplicar`.
5. PR #27, `rcs-onda-completa-proposta`, neste merge. Só proposta. O openEMS (GPL-3.0, processo separado) não arrancou. Sem caixa de cálculo, as células ficam em falta. O PO não é onda completa. `nao_avaliado`. `nao_aplicar`.

O visor do VSPAERO no contentor e o deck L1 de motor continuam por fazer. O yaml dos exemplos não mudou em nenhum destes ramos.

### G1. Cadeia ADflow + TACS (MPhys) — preparação, sem corridas no box

1. Imagem Docker do MDO Lab (MPI, PETSc, CGNS já compilados), por exemplo `mdolab/public:u22-gcc-ompi-stable`
   (confirmar a etiqueta atual em https://hub.docker.com/r/mdolab/public antes de puxar).
2. Dentro do contentor: `pip install mphys` (Apache-2.0) e confirmar `python -c "import adflow, tacs, pygeo, pyhyp, idwarp"`.
3. Caso de referência pequeno do próprio MPhys (`examples/aerostructural/supersonic_panel` ou o `mach_tutorials`
   da asa retangular) com `mpirun -np 4`; aceitação: o caso converge como no README do exemplo.
4. Só depois: OML da montagem → STEP (`acdt integration <spec> --step`, ver G4) → pyGeo/pyHyp. Em 18 nov 2026
   a ponte do loft para um FFD pyGeo existe e corre no contentor. O STEP da montagem e o cruzeiro
   ADflow+TACS continuam por fazer.

**Resultado (4 nov 2026, ramo `heavy-g1-g5`).** A imagem `mdolab/public:u22-gcc-ompi-stable` correu em udocker
1.3.17 (PRoot): neste PC não há Docker Desktop nem `newuidmap`. O `bash -lc` da imagem não carrega o
ambiente; é preciso `source /home/mdolabuser/.bashrc_mdolab`. Depois disso importam `adflow`, `tacs`, `pygeo`,
`pyhyp`, `idwarp` e `mphys` 2.0.0. O `mpirun -np 4` do `examples/aerostructural/supersonic_panel` (teoria do
pistão mais uma viga, não uma solução ADflow+TACS) fechou como o README desse exemplo: objetivo escalado
0,0087329876, massa 8,733e-5, 22 iterações, 24 avaliações da função, 22 do gradiente, aoa ≈ [10,526; 18,231]°,
`geometry_morph_param` = 0,1. O exemplo em v2.0.0 publica coordenadas com nomes que o `Scenario` instalado já
não liga; uma cópia de trabalho, fora do acdt, alinhou só esses nomes. O tutorial ADflow da asa retangular não
correu. A ponte OML → pyGeo não foi feita. Registo: `examples/output/heavy_g1_g5/g1_mphys.json`.

### G2. Validação do BODY do AVL (ponto neutro) contra referências publicadas

O harness existe (`acdt.domains.aircraft.assembly.validation`, `acdt integration <caso>.json --np-validation`).
Falta o que não se pode inventar: os valores de referência.

1. Para cada caso de túnel ou CFD publicado (asa + fuselagem com x̄_np ou Cm_α medido), escrever
   `examples/validation/avl_bodies/<caso>.json` = montagem + `"validation": {"mach": M, "reference":
   {"xbar_np": valor, "source": "citação completa (relatório, figura/tabela)", "conditions": "Re, Mach,
   transição"}}`. Sem `source` o harness recusa a referência.
2. Correr: `for f in examples/validation/avl_bodies/*.json; do acdt integration "$f" -o out/avlv/$(basename "$f" .json) --np-validation; done`
   (2 corridas AVL por caso, segundos).
3. Saída: `np_validation.json` / `.md` por caso com x̄_np AVL c/ corpos, s/ corpos, +Torenbeek, limite de Munk e
   `error_mac`, `best`.
4. Aceitação: se em ≥ 3 casos o AVL com corpos tiver |erro| < 3 % da CMA e menor que o de Torenbeek, propor a
   João mudar `options.np_source` por omissão; caso contrário fica `avl_torenbeek`. Nos dois exemplos do
   repositório o AVL com corpos continua a exceder o limite de Munk.

**Resultado (4 nov 2026, ramo `heavy-g1-g5`).** Quatro combinações do NACA Report 540 (Jacobs e Ward, 1936),
Tabela V, asa retangular NACA 0012 (c = 5 in, b = 30 in, AR geométrico 6) e fuselagem redonda. x̄_np = 0,25 − n₀,
a partir do bordo de ataque da CMA. Casos em `examples/validation/avl_bodies/`. |erro| do AVL com corpos / de
Torenbeek, em fração da CMA: combinação 1 (d/c = 0,64) 0,061 / 0,024; combinação 7 (d/c = 0) 0,035 / 0,018;
combinação 13 (d/c = −0,75) 0,013 / 0,016; combinação 15 (k/c = 0,16) 0,039 / 0,015. Só a 13 cumpre os dois
critérios. O AVL com corpos fica dentro do limite de Munk nos quatro. `options.np_source` mantém-se
`avl_torenbeek`. Não se propõe a mudança. A referência da fuselagem é a secção máxima (estação 8,000 in), como
está escrito em cada JSON.

### G3. Calibração do CD0 da montagem com CFD (N2)

1. `acdt size <missão>.yaml -o out/m` → `out/m/assembly_scaled.json`; `acdt integration out/m/assembly_scaled.json -o out/m/int --step`
   → `assembly.step` (facetado; para CFD preferir o OML OpenVSP do `acdt hifi`).
2. Corrida SU2 (RANS SA, já integrada em `acdt hifi`) da montagem a CL de cruzeiro, refinamento de malha em 3
   níveis (Richardson).
3. Extrair D/q por componente (integração das forças por marcador) e escrever no JSON da
   montagem `"drag": {"calibration": {componente: D/q_CFD ÷ D/q_buildup}}`.
4. Aceitação: fatores entre 0,7 e 1,5 por componente e CD0 total da montagem dentro da banda
   nominal–pessimista; fora disso, rever Q/FF antes de aplicar.

**Resultado (4 nov 2026, ramo `heavy-g1-g5`).** Não se calculou nem se aplicou fator. A geometria é a
combinação 7 do NACA TR 540, loft suave em Gmsh 4.15.2 / OpenCASCADE (o STEP facetado não serve de superfície
de CFD; o OpenVSP não está instalado neste Windows). O buildup em
`examples/output/heavy_g1_g5/su2_tr540_c07/buildup.json` dá CD0 nominal 0,01543 e pessimista 0,01724
(Sref = 0,096774 m², Re_c = 3,1×10⁶, Mach 0,15). Não houve integração de forças RANS-SA. O Gmsh 4.15 documenta
o campo `BoundaryLayer` como restrição 2D (`FacesList` é opção desconhecida); `Extrude { Layers }` em
OpenCASCADE responde que a extrusão de camada limite não existe nesse kernel; `ClassifySurfaces` + `Extrude`
seguido de `gmsh -3` escreveu tetraedros e zero prismas. A malha isotrópica tem H = 0,008 m. A y+ ≈ 1 neste
ponto é da ordem de 10⁻⁶ m, por isso essa malha não calibra o buildup. Q e FF não foram revistos.
`drag.calibration` continua 1,0. Registo: `drag_calibration.json` na mesma pasta. A polar da asa (16 nov 2026, `h1_polar_grossa.json`) separa o CD viscoso do induzido e não calibra este CD0 de montagem: a malha não tem corpo, trem nem hélice, e a razão do CD0 da asa é 2,17, fora da banda.

### G4. RCS e STEP da montagem (polar completo)

1. `acdt integration <montagem>.json -o out/r --rcs --step` (leve: STL + 3 azimutes).
2. Pesado: `acdt rcs stl out/r/assembly_rcs.stl -o out/r/polar --freq 10 --daz 0.25` e repetir a 3 e 15 GHz; se
   houver tempo, `bounces=2` (SBR) no estudo.
3. Aceitação: simetria ±0,5 dB entre ±az; o pico frontal a 0° vem das tampas facetadas dos corpos — com
   `fine=2` deve baixar; registar a diferença.

**Resultado (4 nov 2026, ramo `heavy-g1-g5`).** Montagem `examples/integration/twin_boom_pusher.json`, PO
monostático com oclusão e uma reflexão (Knott, Shaeffer e Tuley 1993, Cap. 5). `fine=1` (3552 facetas), esfera
completa com daz = 0,25° a 3, 10 e 15 GHz. Nariz, VV: 10,68 / 16,67 / 12,31 dBsm. HH coincide com VV a cerca de
10⁻¹³ dB: no co-pol monostático deste PO, ê·k̂ᵢ = 0 e o factor da faceta reduz-se a −n̂·k̂. A simetria de ±0,5 dB
em todos os pares ±az não se cumpre. |Δ| máximo 20,0 / 13,4 / 27,4 dB, mediana 0,57 / 0,86 / 0,98 dB; os
máximos estão em nulos (a 3 GHz, ±61,75°: −27,2 contra −47,2 dBsm). `fine=2` (12864 facetas) a 267 s por
azimute daria cerca de 642 h para a esfera completa, por isso ficou uma amostra de 19 azimutes, com 0° e os
pares ±az. Nariz: 9,11 / 16,91 / 19,61 dBsm. Diferença fine=1 − fine=2: +1,57 / −0,24 / −7,30 dB. A baixa
esperada das tampas facetadas aparece a 3 GHz e não a 10 nem a 15 GHz. `bounces=2` não correu: em fine=1 o
maior lado vale 2,609 m e n_sub a 10 GHz chega ao tecto de 40, acima de 6. Registo:
`examples/output/heavy_g1_g5/rcs/polar_summary.json`. A verificação leve a 10 GHz, sem oclusão, em −30/0/30°:
−26,50 / 16,56 / −26,50 dBsm (`rcs_light/rcs_quick.json`).

### G5. MDO com a montagem (trust-region completo)

1. `acdt optimize <missão com assumptions.assembly>.yaml -o out/opt` (uniforme: só W/S; com
   `options.scaling: surfaces`: W/S e AR). Opcional `assumptions.mdo.assembly_close_on: pessimistic`.
2. Saída: `mdo_report.md`, `mdo.json`; cada iteração corre o pipeline completo (minutos por iteração).
3. Aceitação: o ótimo verificado fecha (`sizing.converged`), sem cheques novos a falhar, e W0 ≤ base.

**Resultado (4 nov 2026, ramo `heavy-g1-g5`).** Missão `examples/heavy/uav150_flying_wing.yaml` (a de
`examples/uav_gasoline_150kg.yaml` com a montagem asa voadora; escala uniforme, fecho no CD0 nominal). Três
iterações de região de confiança; parou porque o modelo não prevê melhoria. W0 133,026 → 121,661 kg, AR 6,032
inalterado, W/S 715,8 → 429,5 N/m², S 1,822 → 2,778 m². O dimensionamento fecha e o conjunto de falhas não
muda: `hq:CAP`, `hq:dutch_roll`, `gear:position`, `gear:tipback`, `asm:static_margin`. W0 fica abaixo da base.
`assembly_close_on: pessimistic` não foi usado. A linha «asa (pesos)» do relatório sai NaN: o relatório procura
a chave `wing` no grupo de pesos. Não entra na aceitação. Registo: `examples/output/heavy_g1_g5/opt/mdo.json`
e `mdo_report.md`.

### Exemplos a fechar: bivigas e asa voadora (ramo `fix-balance-examples`)

Não é um MDO novo. Um `size` de cada exemplo, com os cheques de layout e de estabilidade a passar. A corrida
G5 acima fica como estava.

**Bivigas** (`examples/integration/twin_boom_pusher.json`, missão `examples/uav_gasoline_150kg.yaml`).

Causa da margem ~−140 % e do trem sem nariz: o motor instalado e o sistema de combustível (~50 kg no
dimensionamento) ficam no disco propulsor, cerca de 1,4 CMA atrás do ponto neutro (AVL sem corpos + Torenbeek
App. E). As lanças pesam ~3 kg e não são a causa. A carga e o combustível estavam à frente, e a viagem do CG
(~0,27 m) era cerca do dobro do que a banda de 8–15 % admite a esta altura (Raymer Cap. 11). `place_tricycle`
devolve `None` quando a banda fica vazia; não empurra o principal para trás do raio de 15°.

Desenho: pod mais curto, hélice logo atrás do bordo de fuga, V invertido mais atrás e com mais corda, tanque
e baía de carga junto do CG de vazio, EO/IR no nariz. `options.balance.static_margin` 0,12. No `size` (k ≈ 1,16,
S 2,34 → 3,15 m², W0 ≈ 246 kg, CD0 nominal 0,055) a margem publicada fica em 12 % e a carga no nariz em
8,0–13,9 % (no limite de 8 % do CG traseiro). O primeiro vértice na rotação é a ponta da lança, não o disco;
a folga da hélice cumpre 14 CFR 23.925(a)(1).

O tipo fixo dessa missão (fuselagem 3,2 m, c_vt 0,03, estações de tractor) continua a falhar `gear:position`,
`gear:tipback`, `hq:CAP` e `hq:dutch_roll`. Nesse ramo esses cheques não liam a montagem. Não se mexeu no yaml
convencional para os fazer passar. Desde o ramo `hq-gear-assembly` lêem-na (subsecção seguinte).

**Asa voadora** (`examples/heavy/uav150_flying_wing.yaml` + `flying_wing_pusher.json`). Base G5, antes deste
ramo: W0 133,026 kg, `hq:CAP` = 7,02 (Nível 2), `hq:dutch_roll` ζ/ζω/ω = −0,108/−0,304/2,82 (Nível >3),
`gear:position` e `gear:tipback` sem entre-eixos na fuselagem 0–3,2 m (CG ~0,67 m, h_cg 0,55 m),
`asm:static_margin` −25 % (vazio, x_np 0,748 m).

Dois modelos (antes do ramo `hq-gear-assembly`). `hq:*` e `gear:*` liam a Configuration de tipo fixo (c_ht, c_vt, fuselagem, estações). `asm:*`
lê a montagem. Não se alterou nenhum limite MIL-F-8785C nem a banda de 8–15 %: o rolamento holandês instável
era Cnβ quase nulo com c_vt 0,03 (Raymer Eq. 16.47 na fuselagem e o volume da deriva), não um cheque errado
para uma asa sem cauda.

Remédio, com um `size` (não um `optimize`): motor a 72 % L (pusher; PRESSUPOSTO, no lugar dos 8 % L do tractor
de Roskam Parte V Tabela 8.1), aviónica a 12 % L, para a inércia de picada por componentes (Roskam Parte V
Cap. 10) subir sem alargar a viagem — combustível e carga no CG da massa fixa (Raymer 2018 Sec. 15.1).
Fuselagem 3,4 × 0,34 m. c_ht mantém-se 0,55 (a tesoura é escrita para uma cauda horizontal). c_vt 0,10
(Raymer Eq. 6.29). Braço 0,80 L: com o volume fixo, C_nr cresce com l_v/b (Nelson, C_nr = −2 V_v (l_v/b) C_Lα_v)
e ζ_d passa de 0,063 (a 0,50 L) para acima de 0,08. `options.balance` a 10 %. Winglets maiores no desenho;
o volume vertical medido neles é 0,028, não 0,10. Nesse ramo o cheque hq não os lia; desde `hq-gear-assembly`
lê-os, e o rolamento holandês falha (subsecção seguinte).

Depois: W0 137,3 kg, S 1,879 m². `hq:CAP` = 2,95 (Nível 1; Iyy 15,1 → 37,1 kg·m²). `hq:dutch_roll`
0,094 / 0,448 / 4,78 (Nível 1). `gear:position` nariz 0,209 m, principal 1,951 m. `gear:tipback` 15°.
`asm:static_margin` 10,0 % (x_np 0,998 m). Tesoura 0,120 contra 0,120, ainda a passar. Carga no nariz no
limite de 8 %. Nota, não é cheque falhado: o bordo de fuga da cauda de tipo fixo fica a 4,66 m, à frente de
um corpo de 3,40 m. `regulatory_category` (`easa_specific` sem limite numérico) continua a falhar, como na G5.

Correcções do ciclo, com teste: as massas do trem só vão para as rodas quando as duas estações existem; o
combustível de missão além do tanque desenhado fica no CG dos tanques; a escala uniforme escala o CG de base
e a `cg_range`; a secante não fica abaixo do alvo que o cheque exige; a última passagem de W0 é reequilibrada
antes de publicar a montagem.

### `hq:*` e `gear:*` lidos da montagem (ramo `hq-gear-assembly`, 5 nov 2026)

Com `assumptions.assembly`, o `stability_stage` substitui as linhas `hq:*` (menos `hq:scissor`) e as linhas
geométricas `gear:*` (`position`, `tipback`, `nose_load`, `overturn`, `rotation`) pelas da montagem, com a
mensagem a começar por «montagem:». Módulo `assembly/handling.py`. Os limites são os mesmos (MIL-F-8785C pelo
`stability.handling_qualities`; Raymer Cap. 11: 15°, 8–15 %, 63°, 10°). Sem montagem nada muda.
`options.checks_from: fixed_type` volta às linhas antigas; com `asm:wing_area` a falhar (`in_loop: false`)
ficam também as do tipo fixo.

Métodos: AVL da montagem sem corpos, sobre o CG do caso, ao CL de cruzeiro (C_Yβ, C_lβ, C_nβ, C_lp, C_np,
C_lr, C_nr, C_mq; Drela e Youngren); C_nβ dos corpos por Raymer Eq. 16.47 com o volume da malha; C_mα =
−C_Lα·ME com o ponto neutro publicado (AVL + Torenbeek App. E); C_mα̇ das caudas atrás do CG (Etkin e Reid
Sec. 5.5; downwash 2C_Lα/(πA); cauda em V por S·cos²Γ), 0 sem cauda; inércias por soma de componentes
(Roskam Parte V Cap. 10: casca de cada peça distribuída pela área, massas pontuais do caso); matrizes de
estado de Nelson / Etkin e Reid, as mesmas do tipo fixo (`stability.longitudinal_matrix`,
`lateral_matrix`). Trem: o triciclo que a montagem já coloca (`asm:gear_*`). PRESSUPOSTOS: caso «cheio»
(`options.hq_case`), I_xz desprezado, massa e inércias escaladas a W0/m_cheio, η_h 0,9, sem deflexão de
comandos. `res.dynamics['fixed_type']` e `res.assembly['checks_from_assembly']` guardam as linhas antigas.

**Bivigas** (`size` de `uav_gasoline_150kg.yaml` + `twin_boom_pusher.json`, W0 245,5 kg, S 3,146 m²):

| cheque | tipo fixo | montagem |
|---|---|---|
| `gear:position` | falha (sem entre-eixos na fuselagem 0–3,2 m) | passa: nariz 0,687 m, principal 2,720 m, h_cg 0,607 m |
| `gear:tipback` | falha | 15,0° |
| `gear:nose_load` | — | 8,0–13,9 % |
| `gear:overturn` / `gear:rotation` | — | meia-via mínima 0,365 m (via 0,730 m) / 13,9° |
| `hq:dutch_roll` ζ/ζω/ω | 0,079 / 0,193 / 2,43 (Nível 2) | 0,152 / 0,300 / 1,97 (Nível 1) |
| `hq:CAP` | 4,9 (Nível 2) | 4,37 (Nível 2, falha) |
| período curto ζ / τ rolamento / T2 espiral | 0,503 / 0,193 s / 23,8 s | 0,65 / 0,106 s / 50,3 s |

C_nβ = +0,0858 (AVL) − 0,0536 (corpos) = +0,032; c_V medido 0,097; Iyy 131,9 contra 35,9 kg·m² do tipo
fixo; ME no caso cheio 34,6 %.

**Asa voadora** (`examples/heavy/uav150_flying_wing.yaml`, W0 137,35 kg, S 1,879 m²):

| cheque | tipo fixo (c_vt 0,10) | montagem (winglets) |
|---|---|---|
| `hq:dutch_roll` ζ/ζω/ω | 0,094 / 0,448 / 4,78 (Nível 1) | −0,026 / −0,150 / 5,74 (Nível >3) |
| `hq:short_period` ζ | 0,761 | 0,147 (Nível >3) |
| `hq:CAP` | 2,95 (Nível 1) | 21,9 (Nível 3) |
| fugóide / rolamento / espiral | Nível 1 | Nível 1 (ζ 0,065; τ 0,091 s; T2 23,4 s) |
| `gear:*` | tipo fixo | tipo fixo (o desenho tem `gear: none`), com nota |

C_nβ = +0,0724 (AVL) − 0,0044 (corpo) = +0,068, mas C_nr −0,040 contra −0,417 do tipo fixo: os winglets
(c_V 0,028 desenhado, 0,017 depois do balanceamento e da escala) não amortecem a guinada. Iyy 12,25 contra
37,1 kg·m²; C_mq −3,6; C_mα̇ 0; α 12°; ME cheio 32,9 %. A resposta passa a ser honesta: a asa voadora não
fecha o rolamento holandês, o período curto nem o CAP com estes winglets. `res.feasible` não muda (`hq:` e
`gear:` são verificação/layout). Caso «vazio» (informativo): bivigas CAP 2,19 (Nível 1); asa voadora CAP 6,43
(Nível 2), ζ_sp 0,229, rolamento holandês ζ −0,005.

Fica do tipo fixo: `hq:scissor` (escrita para uma cauda horizontal), `gear:stroke` e as posições x_nose_m /
x_main_m que a viga L1 da fuselagem usa (`_refresh_structures_l1`).

## 5. TODO principal — implementar para fechar o workflow de design

**Instrução para agentes:** Lê este HANDOFF + [DESIGN_WORKFLOW.md](DESIGN_WORKFLOW.md) + [TODO-structures-l1.md](TODO-structures-l1.md). Implementa as tarefas por ordem de prioridade. Faz commit pequeno após cada tarefa concluída, corre `pytest -q` (ou os testes da área), atualiza este ficheiro (marca feito ou move para “feito”) e continua. Para quando a suite falhar de forma que não consigas resolver ou quando todas as tarefas PRIORITÁRIAS e ALTA estiverem feitas.

### PRIORITÁRIA — workflow por níveis ([DESIGN_WORKFLOW.md](DESIGN_WORKFLOW.md)), por ordem de implementação

A ordem conta: cada peça usa as anteriores. Regra para todas: nada de enumerações fechadas de configuração
como único caminho; os tipos com nome são atalhos para montar componentes.

P1. **Geometria genérica por componentes + requisitos de integração** (primeiro: tudo depende disto).
    **EM CURSO — 1.ª peça integrada na `main` (merge 3cf8800, 2 nov 2026):**
    `acdt.domains.aircraft.assembly` (Body / Surface / Disc, Assembly com malha PO, STL e AVL das superfícies;
    Item + restrições; `check` de packaging, FOV por raios, massa/CG/inércia, potência e calor; colocação
    determinística em grelha), MCP `assembly_geometry` e `integration_check`, CLI `acdt integration`, exemplo
    `examples/integration/twin_boom_pusher.json`, testes `tests/test_assembly_integration.py`.
    **2.ª peça (P1b) no ramo `p1b-assembly-size` (2 nov 2026, por integrar):** `assembly/sizing.py` avalia a
    montagem como aeronave: massas por peça e papel (Raymer 15.46 a 15.49, V dividido por Purser & Campbell),
    CD0 por áreas molhadas, AVL da montagem com BODY e sem corpos mais Torenbeek App. E, CG e margem estática
    nos 4 casos de carga, trem triciclo sobre a geometria (rotação pela malha, folga da hélice 23.925) e
    cheques `asm:*` de layout. Entra no `size` por `assumptions.assembly`, com o adaptador
    `assembly_from_design` para os tipos fixos (validado no C172), a ferramenta MCP `assembly_sizing`, o
    `acdt integration --size`, o exemplo de asa voadora e `tests/test_assembly_sizing.py`.
    **3.ª peça (P1c, mesmo ramo, 2 nov 2026):** a montagem entra **dentro do ciclo de W0** (`assembly/loop.py`):
    reescala uniforme k = √(S/S₀) em cada iteração, massas por peça no lugar de asa/caudas/fuselagem do tipo
    fixo, CD0 da montagem na polar e no desempenho; `assembly/drag.py` junta Q por junção (Raymer 12.5.5),
    upsweep (Eq. 12.36), base (Eq. 12.37), protuberâncias (Hoerner Ch. III), L&P 5/10 % (12.5.10), banda
    nominal/pessimista/RSS e fatores de calibração por componente para N2; `options.close_on: pessimistic` e
    o cheque `asm:closes_pessimistic_cd0`; testes `tests/test_assembly_drag.py`, `tests/test_assembly_loop.py`.
    `options.in_loop: false` mantém o modo antigo.
    **4.ª peça (ramo `p1c-optimizer-assembly`, 3 nov 2026, por integrar):** restos da P1b, a–g, todos com
    testes (`tests/test_assembly_p1b_leftovers.py`, `test_assembly_export.py`, `test_assembly_validation.py`):
    (a) MDO lê a montagem (CD0, massas por peça, `mdo.assembly_close_on`, AR fora das variáveis em escala
    uniforme); (b) `scaling: "surfaces"`; (c) K pelo AVL (Kroo 2001) com recurso a Oswald; (d) balanceamento
    (ponto neutro e trem realimentam o ciclo, `options.balance`); (e) protuberâncias automáticas dos itens
    (Hoerner Ch. III); (f) STEP facetado e entrada RCS (`acdt integration --step --rcs`, `assembly_scaled.json`
    no `size`); (g) harness de validação do BODY do AVL (`--np-validation`). Detalhe em CAPABILITIES §22.
    **Falta na P1:**
    * ~~MDO a ler a montagem~~, ~~reescala `surfaces`~~, ~~K pelo AVL~~, ~~ponto neutro e trem no ciclo~~,
      ~~protuberâncias dos itens~~, ~~STEP a partir da montagem~~ — feitos no ramo `p1c-optimizer-assembly`;
    * ~~`hq:*` e `gear:*` a lerem a montagem~~ — feito no ramo `hq-gear-assembly` (§4b, a seguir aos exemplos);
      ~~dimensionar winglets/deriva da asa voadora pela estabilidade e desenhar trem nela~~
      — **FEITO L0 opt-in 9 nov 2026** (`options.flying_wing`, Raymer Eq. 6.29 + Ch. 11 / 14 CFR 23.925;
      exemplo `uav150_flying_wing_closed.yaml`; baseline sem a flag inalterado);

    * calibrar os fatores de arrasto com CFD em N2 (o gancho `drag.calibration` já existe; corrida em §4b G3);
    * ~~trem convencional e de esquis e pernas desenhadas~~ — **FEITO L0 opt-in 9 nov 2026**
      (`gear.type` taildragger/ski, `draw_legs`, Raymer Ch. 11 / 14 CFR 23.925; exemplos
      `conventional_taildragger.json`, `ski_gear_demo.json`);
    * ~~corpos rodados no AVL~~ — **FEITO L0 9 nov 2026**: omitidos → unassessed (nunca stand-in alinhado; `asm:avl_bodies`);
    * validar o BODY do AVL contra dados de túnel (harness feito; faltam as referências publicadas, §4b G2);
    * ~~malha RCS com o chine e o estudo aero/RCS a lerem a montagem~~ — **FEITO L0 opt-in 9 nov 2026**
      (`Body.chine` / `pod.chine_deg`, `rcs_bridge`, `acdt rcs study` + `acdt shape study --assembly` leem a
      montagem; inventário included/excluded/unassessed; exemplo `chine_fuselage_rcs.json`);
    * ~~cinemática do trem~~ — **FEITO L0 geométrico 9 nov 2026** (`gear.retract` arco do centro da
      roda vs estrutura/disco; missing path → unassessed; sem dinâmica/FEM);
    * ~~cilindros e esferas como forma do equipamento~~ — **FEITO L0 opt-in 9 nov 2026** (`Item.shape` sphere|cylinder; Meriam & Kraige; exemplo `shapes_and_rotated_body.json`);
    * validar o lançamento de raios contra um caso publicado.
    * **Alta fidelidade aero-estrutural N2/N3 (planeado, 3 nov 2026):** ADflow (LGPL-2.1, RANS SA com adjunto
      discreto, malhas estruturadas sobrepostas) + TACS (Apache-2.0, cascas compósitas com adjunto e
      encurvadura) acoplados por MPhys sobre OpenMDAO (MDO Lab), como opção ao lado do SU2. Correm só como
      processos separados (imagem Docker com MPI); o acdt só escreve a geometria e os scripts e lê os
      resultados. Caminho da malha a partir da montagem: OML da montagem (STEP/IGES) → pyGeo (FFD) → malha de
      superfície estruturada → pyHyp (extrusão) → overset (cgnsUtilities) → ADflow; caixão e revestimentos
      → TACS (BDF via pyNastran). É trabalho para o **Grok Build no PC do João** (§4b); licenças em THIRD_PARTY.md.
    * Corpos, superfícies sustentadoras, vigas, naceles e radomes como peças genéricas, montáveis em qualquer
      configuração e lidas pelas mesmas ferramentas (aero, RCS, estruturas, W&B, CAD).
    * Objetos de requisito de integração: volume, massa, potência (média e pico), calor, cone de campo de
      visão, zonas de exclusão, condições de posicionamento como restrições.
    * Verificador de packaging e de cones de visão (oclusão pela própria aeronave, hélice, trem).
P2. **Gerador morfológico N1 + avaliador + poda por conjuntos.** **FEITO (fatia vertical) — 6 nov 2026**,
    ramo `p2-morphological-n1`.
    * Matriz aberta (Zwicky 1969) com sementes; a IA acrescenta opções; `morph_generate` combina e corta
      incompatibilidades físicas com motivo (`morphology/generate.py`).
    * Avaliador L0/L1: `size` + juiz de massa pontual opcional (`morphology/evaluate.py`). Métricas
      multidisciplinares completas (AVL do conjunto, RCS PO, packaging FOV, custo L0 fino) ficam para
      ligar quando os tipos genéricos de cauda/vigas (P1) e o packaging estiverem no mesmo ciclo.
    * Poda set-based com banda N1 ±15 % PRESSUPOSTO (`morphology/prune.py`; Sobek/Ward/Liker 1999).
    * CLI `acdt morph`, MCP `morph_*`, tutorial `docs/tutorial-p2-morfologico.md`.
P3. **Simulador de missão como juiz comum** (DESIGN_WORKFLOW §4). **FEITO — 5 nov 2026**, na `main`
    (merge do ramo `p3-sim-pointmass`).
    * Massa pontual 3-DOF (`flightsim/pointmass.py`): o mesmo YAML do 6-DOF (subida, cruzeiro, espera e
      patrulha, waypoints, descida, vento constante). Equilíbrio de Anderson 1999 Cap. 5 e Raymer 2018
      Cap. 17; a posição é Euler explícito. N0 lê o bloco `aircraft` (os DEFAULT_ASSUMPTIONS de
      dimensionamento não entram). N1 lê o dimensionamento, sem modelo de voo AVL. A comparação com o
      6-DOF usa a polar e a tração desse modelo. CLI `acdt simulate --fidelity pointmass|6dof` e MCP
      `simulate_mission` (o 6-DOF continua a ser a omissão). `dt` é o passo 6-DOF; `pointmass_dt` é o
      da massa pontual (omissão 1 s). Exemplo: `examples/simulation/n0_patrol.yaml` (números PRESSUPOSTO).
      Tutorial: `docs/tutorial-p3-massa-pontual.md`.
    * Sensor no rasto (`flightsim/sensors.py`), com as primitivas de conceito: pegada, faixa, horizonte,
      Johnson, POD e ciclo de Ha 2010. Saídas: tempo em estação, área varrida, POD.
    * Falhas determinísticas (`flightsim/failures.py`): motor, sensor, ligação, degradação de
      combustível ou bateria, num instante ou numa condição. A massa pontual voa continua / regresso /
      desvio. Um catalogue com seed é um sorteio reproduzível, não um Monte Carlo. No 6-DOF a resposta
      fica registada (`executed: false`) e a trajetória não muda.
    * Consistência, cruzeiro de 0,4 min do C172 a 50 m/s e 600 m (`dt` 0,02, `extrapolate_after_s` 120,
      sem qualidades de voo), tolerância 15 % (a mesma banda do k_energia): massa pontual 1,200000 km,
      0,400000 min, 0,0977616 kg; 6-DOF 1,201000 km, 0,400333 min, 0,0977436 kg. Alcance específico
      12,2748 contra 12,2872 km/kg; autonomia específica 4,09159 contra 4,09575 min/kg. k_energia do
      6-DOF nesse troço 0,99896. Diferenças relativas cerca de 0,08 % no alcance e na autonomia e
      0,10 % no específico.
    * Adiado: resposta de falha em malha fechada no 6-DOF; Monte Carlo; geografia real; custo por hora
      de voo; chamada automática de `compare_alternatives`; ~~busca de barreira~~ (feito L0 9 nov 2026); trade de carga útil a
      partir de catálogo; arquitetura elétrica. As métricas ficam no resumo para o agente as passar.
P4. **Sistemas no mesmo ciclo, com alternativas abertas.** **FEITO (fatia vertical) — 6 nov 2026**,
    ramo `p4-systems-payload`.
    * Arquitetura elétrica + orçamento de potência (MIL-E-7016F; Moir & Seabridge): geração, baterias de
      aviónica, cargas por barramento, margens N1 PRESSUPOSTO; `acdt systems-p4 electrical` /
      `electrical_analyse`. Catálogo EXAMPLE em `core/data/payloads.yaml` (substituir por datasheets).
    * Trade de carga útil (massa, potência, volume, FOV) via Pareto: `acdt systems-p4 payload-trade` /
      `payload_trade`. A IA acrescenta linhas com `source` + `retrieved`.
    * Custo por hora de voo: agregação directa (`cost-fh` / `cost_per_flight_hour`; preços do utilizador).
    * ~~fecho automático no `size`~~ — **FEITO L0 10 nov 2026** (`size-auto-onboard-close`): bloco
      `onboard` na missão → `MissionSpec.from_dict` / `onboard_bridge` aplica hotel+massa dentro de
      `acdt size` / `jet_size` / `size_vtol`; `DesignResult.onboard_bridge` + `result.json` / summary;
      sem bloco → legado; BSFC/η em falta → unassessed. `onboard_size` fica para ecrãs CG/FOV/closure.
    * ~~energia/híbrido/datalink/SATCOM como alternativas morfológicas~~ — **FEITO L0 opt-in 10 nov 2026**
      (`p4-morph-energy-comms`): eixos `energy` / `avionics_link` com atalhos (hybrid_series/parallel,
      datalink_LOS, SATCOM_Ku, …) + opções-dict `{id,source,retrieved?,power_W?}`; evaluate usa
      `hybrid_dispatch` / hotel de link quando há modelo+source; em falta → `unassessed_axes`
      (nunca massa/potência zero); cortes físicos série/paralelo (Pornet & Isikveren 2015); poda
      set-based mantém unassessed vivos. Exemplos `n1_energy_comms_*.json`.
    * ~~Eastlake/CER de custo operacional no mesmo passo morfológico~~ — **FEITO L0 opt-in
      10 nov 2026** (`p4-eastlake-ops-cost`): DOC Raymer 2018 Cap. 18; `unit_price` via Eastlake
      (Gudmundsson 2014 Cap. 2) / DAPCA IV / `unit_price_from=size`; `acdt systems-p4 ops-cost` /
      MCP `operational_cost`; morph `--systems.operating_cost` anexa `cost_per_fh` só se
      `status=ok`; termo em falta → unassessed (nunca zero silencioso); poda set-based com
      `cost_per_fh` se presente; `cost-fh` legado intacto; L2 cotações (MÉDIA §5) continua
      bloqueado. Exemplos `ops_cost_eastlake_complete.json`, `ops_cost_unassessed_fuel.json`,
      `n1_ops_cost_{arches,systems,unassessed_systems}.json`.
P5. **Registo de decisões (ferramenta + MCP).** **FEITO (fatia vertical) — 6 nov 2026**, ramo
    `p5-decision-record`.
    * `acdt decisions` / MCP `decisions_*`: what/why/fidelity, rejected[], conditions[] (valor absoluto ou
      desvio % vs baseline), check + reopen; `decisions.json` + `decisions.md`.
    * Refs: INCOSE SE Handbook 4th ed.; Sobek/Ward/Liker 1999; DESIGN_WORKFLOW §6–7.
    * ~~gate automático de fim de nível~~ / ~~re-avaliação das rejeitadas~~ — **FEITO L0 opt-in 10 nov 2026**
      (`p5-level-gate`): `acdt decisions gate` / `decisions_gate` → status `pass`|`fail`|`unassessed`
      (métrica ausente / `ok:null` ≠ pass); não escolhe vencedor ponderado; com `--reopen` lista
      `rejected_reevaluation` para o agente reavaliar. Exemplos `gate_n1_{pass,fail,unassessed}.json`.
P6. **Otimização paramétrica da OML em N2.** **FEITO (fatia leve) — 6 nov 2026**, ramo
    `p6-shape-opt-light`.
    * Shape alargado (`wing_z_frac`, `x_wing_le_frac`, `L_scale`, `D_scale`, `sensor_x_frac`) +
      `acdt shape study` LHS aero/RCS/packaging (Pareto). Heurística de volume/FOV; FOV completo =
      `assembly.integration`.
    * **Ainda aberto (pesado / Grok Build):** RANS/ADflow + TACS, OML suave pyGeo, concordâncias,
      acoplamento estruturas no mesmo MDA.
P7. **Ferramenta de sensibilidade (fidelidade por necessidade).** **FEITO (fatia vertical) — 6 nov 2026**,
    ramo `p7-sensitivity`.
    * OAT local ε=(Δy/y)/(Δx/x) a partir de amostras ou `acdt sensitivity pipeline` (handbook/`no_systems`);
      ranking + `fidelity_hints` (DESIGN_WORKFLOW §5; Saltelli 2008 screening).
    * MCP `sensitivity_from_samples` / `sensitivity_pipeline`; tutorial `tutorial-p7-sensibilidade.md`.
    * ~~Sobol/global~~ — **FEITO L0 opt-in 10 nov 2026** (`p7-sobol-global`): `acdt sensitivity sobol` /
      `sensitivity_sobol` — índices S1 e ST (Jansen / Saltelli 2008–2010) a partir de Y_A/Y_B/Y_AB ou
      pipeline handbook; bootstrap percentil opcional; variância nula / amostras em falta → unassessed
      (nunca zero silencioso). Exemplo Ishigami `examples/sensitivity/sobol_ishigami.json`.
    * ~~Monte Carlo (UQ/propagação)~~ / ~~acoplamento ao gate N1/N2~~ — **FEITO L0 opt-in 10 nov 2026**
      (`p7-mc-gate-uq`): `acdt sensitivity mc` / `sensitivity_mc` — LHS (McKay/Helton) ou MC i.i.d.
      com percentis/mean/std; falhas → unassessed. Gate: `--uq` / `--require-uq` consome
      `gate_metrics` + `interval_checks` (missing UQ ≠ pass). Exemplos `mc_linear_demo.json`,
      `gate_n1_uq_{pass,fail,unassessed}.json`.

**Acrescento 10 nov 2026 (P4 morph energia/comms):** eixos abertos energy/híbrido/datalink/SATCOM no `acdt morph`; unassessed≠pass.

**Acrescento 10 nov 2026 (P4 Eastlake/CER ops-cost):** DOC Raymer 2018 Cap. 18 + Eastlake/DAPCA
unit_price; morph opt-in; unassessed≠zero; `cost-fh` legado mantém-se.

**Acrescento 10 nov 2026 (P7 MC UQ + gate):** `sensitivity mc` (LHS/MC) + `decisions gate --uq/--require-uq`.

**Acrescento 10 nov 2026 (P7 Sobol global):** `sensitivity sobol` / Saltelli–Jansen S1/ST; OAT inalterado.

**Acrescento 10 nov 2026 (P5 gate de fim de nível):** `level_gate` / `decisions_gate` (DESIGN_WORKFLOW §7).
Opt-in; CLI/MCP default inalterados sem `gate`. Unassessed≠pass; set-based sem auto-vencedor.

**Benchmark Nansei na `main` (6 nov 2026):** `examples/benchmarks/nansei_jcg/` — só enunciado +
`requirements.json` + `reference_results.json`. O estudo completo não é público.

**Pontos em aberto do estudo Nansei** (para fazer junto com P1–P4, quando tocarem a mesma área):

* ~~diedro como entrada e estabilidade espiral~~ — **FEITO L0 9 nov 2026**: `geometry.dihedral_deg`
  explícito; `hq:spiral` via Clβ AVL (Etkin & Reid / Nelson); sem diedro declarado → unassessed.
* ~~potência elétrica do radar (e da restante carga útil) no consumo de combustível~~ — **FEITO L0 opt-in 9 nov 2026**
  (+ fecho automático no size **10 nov 2026**):
  `onboard_bridge` liga `onboard` a `acdt size` / `jet_size` / `size_vtol` (hotel → combustível/energia);
  potência/BSFC/`fuel_kg_kWh_terminal` são entradas com fonte ou PRESSUPOSTO; **não** inventa W Gabbiano;
  incompleto → unassessed; híbrido sem dispatch → unassessed; sem `onboard` → inalterado.
  Resultado expõe `onboard_bridge` (issues info + summary/JSON). Exemplos `prop_size_radar_hotel.yaml` /
  baseline; `tests/test_onboard_bridge.py`.
* ~~discrepância de MTOW entre `size_fleet` e `acdt size` para a mesma missão~~ — **FEITO 9 nov 2026**:
  causa = `size_fleet` forçava `level=L0` e sobrescrevia `aero.fidelity: lowfi` do YAML; `acdt size` não.
  Agora omitir `level` = mesma fidelidade que `acdt size`; `compare_size_fleet_mtow` + testes de regressão;
  Δ medido antes: +4,79 kg (`uav_gasoline_150kg`), +7,48 kg (`illegal_fishing/variant_L`).
* ~~cauda em V invertido e bivigas como tipos no `acdt size`~~ — **FEITO L0 9 nov 2026**:
  `geometry.configuration: V|inverted_V|twin_boom` (`assembly/shortcuts.py`, Purser & Campbell /
  Raymer 6.28–6.29); atalhos montam componentes, nunca lista fechada; exemplos
  `uav_inverted_v_shortcut.yaml`, `uav_twin_boom_shortcut.yaml`.
* ~~busca de barreira (*barrier search*) nas primitivas de cobertura~~ — **FEITO L0 opt-in 9 nov 2026**
  (`barrier_search` / `acdt concept barrier`; Koopman/Washburn; missing W/V/endurance → unassessed;
  exemplos `examples/concept/barrier_patrol_demo.json`, `barrier_unassessed_width.json`);
* largura real de varrimento do radar escolhido (Gabbiano), com fonte e data —
  **ainda aberto**: o demo de barreira usa W PRESSUPOSTO (ex. 20,4 km do `reference_results`), **não** o
  datasheet Gabbiano; sem fonte datada a POD radar-específica continua unassessed.

### ALTA (necessárias para o workflow completo)

1. **FEITO — modelo estrutural L1 com deformação → aero no ciclo de `size`** (30 out 2026).  
   Fuselagem em casca circular (NASA SP-8007), empenagens em caixão e torção de cruzeiro na linha sustentadora, dentro do MDA.  
   `structures.flex` e `structures.mass_in_loop` ficam desligados por omissão: o C172 rígido mantém W0, a polar e o ponto neutro.  
   Ver [structures-l1.md](structures-l1.md) e [TODO-structures-l1.md](TODO-structures-l1.md).

2. **FEITO — concept trade em `main` (`8d22417`, `2b926e6`, `b4fa856`).** Não voltar a integrar o ramo. Ver «Já feito».

3. **FEITO — CAD paramétrico** (30 out 2026).  
   `acdt cad` escreve `cad_spec.json`, um DXF em milímetros (planta da asa, longarinas, rectângulo da fuselagem e secção do caixão) e, com o extra `acdt[cad]`, a montagem STEP da estrutura (revestimentos, longarinas, nervuras, cavernas e quatro longarinas da fuselagem). O CadQuery e o OpenCASCADE correm só em `cad_build.py`. A casca exterior entra com `--oml`; sem esse ficheiro a montagem é só a estrutura.  
   Ver [cad-parametrico.md](cad-parametrico.md).

4. **FEITO — formulação inteira-mista no MDO** (30 out 2026).  
   O SLSQP fica em W/S, P/W e AR, com o motor, o ESC e a célula fixos. Um passo de catálogo reescolhe o mais leve que cumpre a potência e a corrente e só é aceite se o mérito do pipeline melhora, sem verificações novas a falhar (Geoffrion, *J. Optim. Theory Appl.* 10, 1972). Não há catálogo de hélices. Os servos continuam a ser reescolhidos no fecho.  
   Ver [tutorial-fase3.md](tutorial-fase3.md) §8.

### MÉDIA

5. **Exemplo e fluxo de custo L2 com cotações reais** (BOM, fornecedores com fonte e data).
6. ~~`hq:*` e `aeroel:*` como restrições reais do MDO** (não só filtros).~~
   **FEITO L0 opt-in 9 nov 2026**: `assumptions.mdo.hq_aeroel_constraints: true` (allow-list
   `hq_aeroel_keys`) — entram na violação de φ e margens aeroelásticas no SLSQP; unassessed ≠ pass;
   omissão = filtro pós-ótimo. Exemplo `examples/mdo/hq_aeroel_constraints_demo.py`;
   `tests/test_mdo_hq_aeroel_constraints.py`. Sem FEM/flutter novos.
7. **FEM não-linear.** O cartão `*STEP, NLGEOM` e `run_nlgeom` existem (18 nov 2026) e não são um passo por omissão de `acdt hifi`. No caixão da asa sem deriva, à carga última, o código de saída foi 201 e não há flecha. Riks continua por avaliar.
8. ~~**Contenção SORA + taxas de falha de fornecedor** (C2, FCC, motor UAV).~~
   **FEITO L0 opt-in 10 nov 2026**: `core/certification/containment.py` + `SoraInput.containment`;
   `certification.safety.supplier_rates` (λ ou MTBF + source + retrieved; número sem fonte não é
   aplicado). Exemplos `examples/certification/sora_containment_{assessed,unassessed}.json` e
   `supplier_rates_illustrative.json` (EXAMPLE/PRESSUPOSTO, não dados reais). CLI `acdt safety sora`.
   Em aberto: Anexo C estratégico, Anexo F (abrigo > 3 m), Critério #2 qualitativo (não auto-pass),
   bússola sem taxa pública.
9. ~~**BEMT / deck de motor mais completo** no ciclo de sistemas (além da estatística atual).~~
   **FEITO L0 opt-in 10 nov 2026**: `systems.propeller.method: bemt` reutiliza o BEMT McCormick/Ning
   da Fase 9; `systems.motor.deck` é o modelo DC de 1ª ordem de Drela 2007 (Kv, R, I0 + source).
   Rotor axial/pairar opt-in em `rotors.bemt`. CLI `acdt bemt {propeller|rotor}`, `acdt motor-deck`;
   MCP `bemt_propeller`, `bemt_rotor`, `motor_deck`. Exemplos em `examples/systems/` e
   `examples/vtol/bemt_hover_*.json` (EXAMPLE/PRESSUPOSTO, não mapas de fornecedor).
   Por omissão o ciclo continua Raymer Sec. 10.3. Em aberto: catálogo de hélices, BEMT em voo
   avançado, interferência rotor–rotor, ilhas de eficiência de fornecedor, QPROP/XROTOR.

### MENOR / mais tarde

10. ~~VTOL / híbrido / eVTOL.~~ **FEITO 6 nov 2026 (L0)**: `acdt vtol {hover|size|compare}`, MCP `vtol_hover`,
    `vtol_size`, `vtol_compare`; módulo `domains/aircraft/vtol` (quantidade de movimento + FM, transição com
    Glauert, bateria por energia/potência); exemplos em `examples/vtol/`; ver [tutorial-vtol.md](tutorial-vtol.md).
    **Fecho de massa VTOL opt-in FEITO 9 nov 2026** (`vtol/closure.py`, bloco `closure`): NDARC AFDD00
    rotor + NASA15 motor + frações/massas com fonte + bateria nativa, bisseção com histórico/resíduo/estados;
    ligado a `onboard_size` e à frota 1.1. **BEMT axial/pairar opt-in FEITO 10 nov 2026**
    (`vtol/bemt.py`, `rotors.bemt`). Adiado: MDA completo, BEMT em voo avançado / interferência,
    correlações de fuselagem/asa para UAV pequeno, calibração χ com massas medidas, ruído,
    dinâmica da transição, OEI, híbrido.
11. ~~Jatos subsónicos (arrasto de onda, turbofan, CS-25).~~ **FEITO L0 6 nov 2026**:
    `acdt jet {wave-drag|turbofan|loads|analyse|check|size|performance|weights}`; MCP `jet_wave_drag`, `jet_turbofan`,
    `jet_loads`, `jet_analyse`, `jet_check`, `jet_size`, `jet_performance`, `jet_weights`; Korn–Mason/Lock, correlação turbofan Mattingly/Ihme,
    We estatístico `jet_transport` de Raymer, Breguet e envelope V-n de manobra (EAS).
    **Fecho acoplado L0 feito (6 nov 2026):** `jet size` / `jet_size` resolve m0 para carga útil/tripulação
    e uma alternativa explícita de geometria/motores fixos, com We Raymer e Breguet diferencial integrado
    com CL/CDonda/L/D dependentes da massa e TSFC do turbofan. Histórico/resíduo, refinamento RK4,
    intervalo explícito e estados de falha; empuxo/MTOW verificados separadamente da convergência.
    Registo de proveniência; sem L/D imposto, seleção de arquitetura ou fallback GA.
    **Triagem de performance L0 feita (7 nov 2026):** bloco opcional `performance` em `jet size`
    e ferramenta `jet performance`/`jet_performance`: corrida AEO integrada e pontos AEO/OEI
    de subida com n−1 motores, massa do fecho e configuração/arrasto/rating explícitos.
    Preserva `feasible` antigo; `combined_requested_checks_passed` é só triagem de engenharia.
    Referências numéricas 25.121(a)–(d) por número de motores têm conformidade não avaliada,
    não falsos passes; rotação/transição e trajetória 25.111/.115 continuavam abertos
    (campo ASD/TOD/BFL + rotação/transição opt-in — ver abaixo). Ver [tutorial-jet-performance.md](tutorial-jet-performance.md).

**Acrescento 9 nov 2026 (campo de descolagem L0):** `performance.field` opt-in —
ASD, TOD AEO/OEI, BFL com procura de V1; CS-25 compliance unassessed; exemplo
`performance_field.yaml`.

**Acrescento 10 nov 2026 (rotação/transição opt-in):** `include_rotation_transition`
com `rotation_time_s`, `transition_load_factor`, `vr_m_s` — Roskam/Torenbeek
s_R=½(VR+VLOF)t_R e arco R=V_LOF²/(g(n−1)); TOD/BFL incluem os segmentos quando
ligado; omissão = saída PR #25 inalterada; dados em falta → unassessed (nunca
airborne de comprimento zero). VMCG de ensaio continua fora de âmbito. Exemplo
`performance_field_rotation.yaml`; `tests/test_jet_field_takeoff.py`.

    **Build-up parcial de pesos feito (7 nov 2026):** `jet weights`/`jet_weights` e
    `weights.mode: components` opt-in em `jet_size`/`jet_performance`: asa/HT/VT Raymer
    transporte verificados, termos de massa recalculados na bissecção, restantes grupos
    com massas totais/fontes explícitas ou exclusão justificada. Cobertura duplicada é
    erro; desconhecida/fora de domínio bloqueia fecho sem subtotal/fallback GA/estatístico.
    Regressões só para transporte metálico convencional declarado; overrides fornecidos
    permitem outras alternativas sem extrapolar correlações. Sem resíduo ajustado ao OEW.
    Estatística antiga mantém-se por omissão. Tripulação/carga/todo combustível fora do
    inventário; depósitos secos uma vez, storage não soma massas outra vez. Combustível
    inutilizável de storage continua sem feedback no MTOW; não chamar ao inventário OEW.
    Exemplos comparativo/sensibilidade/cobertura em `examples/jet/`; todos os novos inputs
    são PRESSUPOSTOS. **Acrescento 9 nov 2026:** regressões Raymer Sec.15.3.2 restantes + W_press
    opt-in + extração fornecida; `engines_dry` continua fornecido. Pendente: montagem/CG,
    calibração, mapas ECS; cobertura não prova precisão.
    O `acdt size` genérico não foi alterado: as suas ligações de geometria/pesos/propulsão não justificam
    ainda um MDA de transporte. Referência pública A320 ilustrativa, sem precisão de certificação ou CS-25.
    Ver [tutorial-jet.md](tutorial-jet.md) e `examples/jet/`.
    **Acrescento 9 nov 2026 (mapas leves):** `engine.map` table/corrected_table opt-in
    (`jet/engine_map.py`); default continua Mattingly/Ihme. Fora do domínio = unassessed.
    Exemplo `engine_map_table.yaml`. Motor η(P) opcional em `core/motor_map.py`.
    Adiado L2 (PC do João): pyCycle/NPSS/GasTurb/T-MATS/CFD, fecho MDA completo do jato,
    mapas ECS/bleed, build-up Torenbeek completo;
    validação CFD/ensaio, deck real, referência 737 e envelopes de rajada/Mach/buffet.
12. ~~Arrasto de compensação/folga dos camber flaps.~~
    **FEITO L0 opt-in 10 nov 2026**: `camber_flap.trim_drag` (HT induced, Nelson/Etkin a partir de Δcm0)
    e `camber_flap.gap` (`sealed`+fonte ou `dCD`+fonte; chord_ratio sozinho → unassessed ≠ zero).
    Envolvente loiter/alta velocidade inalterada por omissão. Demo `examples/camber/`;
    `tests/test_camber_trim_gap.py`. Sem correlação DATCOM inventada nem solver novo.
13. Modelo de aterragem do C172 mais próximo do POH. Medido em 30 out 2026: total 504 m contra 407 m (+24 %). A corrida de descolagem cumpre (274 m contra 293 m, −6 %) e o total sobre 50 ft fica em 459 m contra 497 m (−8 %). A subida fica em 715 ft/min contra 730 (−2 %). Fechar a aterragem pede o ângulo de aproximação demonstrado, publicado no lugar dos 3° de 14 CFR / CS 23.75(a)(1). O efeito de solo alonga a distância (Hoerner e Borst 1975; McCormick 1979) e não entra. A rotação pede o contorno inferior, com fonte: o cilindro dá 6,7° e Raymer pede 10–15°. Ver §3.
14. ~~Massa das nervuras SIMP no orçamento.~~ **FEITO L0 opt-in 10 nov 2026**:
    `wingbox/rib_simp_mass.py` alimenta `m_web = mean(ρ_SIMP)·w·h·t·ρ` no orçamento Fase 6
    (`size_ribs` / Niu §5.4 para `t`; densidade da ficha com fonte). Opt-in via
    `assumptions.structures.rib_simp_mass: {vol, penal, nelx?, iters?, stations: all}` ou
    `acdt wingbox6 --rib-simp-mass`, e CLI/MCP autónomos `acdt rib-simp` / `rib_simp_mass`.
    Inputs em falta ou estações ≠ all → unassessed (massas size_ribs retidas; nunca zero
    silencioso nem unassessed=pass; sem extrapolação). Por omissão o estudo não muda a massa.
    Exemplos EXAMPLE/PRESSUPOSTO em `examples/wingbox/rib_simp_mass_*.json`; testes
    `tests/test_rib_simp_mass.py`. Não é FEM não linear, TACS, ADflow ou campanha de TO.
15. RCS de onda completa (hoje só Óptica Física — suficiente para o início).

### Já feito (referência)

- Workflow por níveis N0–N3+ documentado em `DESIGN_WORKFLOW.md` (30 out 2026); implementação em P1–P7.
- Estruturas L1 no ciclo de `size` (fuselagem, empenagens, torção → K). Flags `flex` e `mass_in_loop` desligadas por omissão. Ver `structures-l1.md`.
- CAD paramétrico da estrutura interna (`acdt cad`): DXF sempre; STEP com o extra `acdt[cad]`. A casca exterior só entra com `--oml`. Ver `cad-parametrico.md`.
- MDO: motor, ESC e célula fora do SLSQP, num passo de catálogo aceite pelo mérito do pipeline. Ver `tutorial-fase3.md` §8.
- Peso e centragem operacional e trem (baixa fidelidade) — ver `tutorial-wb-trem.md`.
- Fases 1–10, RCS L1, simulate 6-DOF, manufacture L0/L1, certify, camada MCP.
- Estudo conceptual de frota (`acdt concept`, 13 ferramentas MCP, exemplo de pesca ilegal).
- UAV de 150 kg: sem tripulação, carga no CG da massa fixa, trim e tesoura na mesma gama. A Fase 1 fica viável. `hq:scissor` e `wb:envelope` passam com `c_ht` 0,55 (tesoura; 0,50 era o arranque da Tabela 6.4). `gear:position` e `gear:tipback` continuam sem solução (§3).
- Torção do FEM contra o GJ de Bredt da Fase 3. Encurvadura `*BUCKLE` fora do shift σ = 1, com o caso pequeno em `tests/data/ccx_buckle_win`.
- `hq:*` (menos a tesoura) e `gear:*` geométricos lidos da montagem quando há `assumptions.assembly` (ramo `hq-gear-assembly`, `assembly/handling.py`). A asa voadora passa a falhar o rolamento holandês, o período curto e o CAP com os winglets desenhados; o bivigas passa `gear:position` e `gear:tipback` (§4b).
- C172: `wb:envelope`, `gear:position` e `hq:scissor`. A rotação (6,7° no cilindro, mínimo 10°, Raymer Cap. 11), a subida (715 ft/min contra 730 do POH, −2,0 %, BEMT, Anderson Cap. 5) e a aterragem (504 m contra 407 m, +24 %, Raymer Sec. 17.9 a 3°) continuam a falhar (§3, ponto 13).
- Euler: o ONERA M6 confirma o eixo de vento. O CD negativo do C172 permanece rejeitado. O `.geo` da meia-asa já não tem caminho absoluto.

## 6. Como trabalhar

* Comandos de referência: README §"Início rápido"; `acdt <comando> --help`.
* Antes de cada push: `pytest -q` (ou pelo menos os testes da área tocada); commits pequenos; push para
  `main` em cada sub-etapa testada.
* Nova biblioteca, dado ou método → `THIRD_PARTY.md` (licença; GPL/LGPL só como processo externo).
* Instalação Windows conferida a 28 out 2026 com Python 3.13.15 (o 3.12 permanece instalado ao lado).
  O `venv` do repositório foi recriado com `py -3.13 -m venv .venv` na raiz, e
  `pip install -e ".[dev,aero,mdo,hifi,wingbox,ai,sim,cert]"` concluiu. `PYTHONUTF8=1` já estava definido.
  Binários fora do git, em `C:\acdt-tools`: AVL 3.40 e XFOIL 6.99 e Gmsh 4.15.2 em `bin` (no `Path` do
  utilizador, para o `shutil.which` do AVL e do XFOIL); CalculiX 2.23 como `ccx.exe` (cópia de
  `ccx_dynamic.exe`, com as DLL MKL na mesma pasta) em `calculix\calculix_2.23_4win`; SU2 8.5.0 «Harrier»
  OpenMP em `su2\win64-omp\bin`. `ACDT_HIFI_BIN` (utilizador) junta essas três pastas, separadas por `;`.
  O build MPI do SU2 ficou em `su2\win64-mpi` e não entra no `ACDT_HIFI_BIN`: o executável importa
  `msmpi.dll`. O `winget` não instalou o Microsoft MPI (o instalador é só de máquina e esta sessão não
  elevou). O OpenVSP 3.55.0 para Python 3.13 não foi descarregado a 28 out 2026: `openvsp.org` fechava o handshake TLS
  neste PC. A 18 nov 2026 o zip `OpenVSP-3.56.0-win64-Python3.13.zip` descarregou de
  `https://openvsp.org/download.php?file=zips/current/windows/OpenVSP-3.56.0-win64-Python3.13.zip`
  para `C:\acdt-tools\openvsp`. O pacote `openvsp` 3.56.0 está no venv `C:\acdt-tools\openvsp\py313`.
  `import openvsp` imprime `OpenVSP 3.56.0`. O contentor MDO Lab mantém o 3.48.2 e não substitui esta instalação.
  `ACDT_VSP_PYTHON` aponta para o `python.exe` desse venv. O processo acdt não importa `openvsp`.
  JSBSim 1.3.3 importa no venv. A validação SU2 e CalculiX deste PC está no §4
  (pastas `*_hifi_win`, 28 out 2026).
* **Trabalho em paralelo (vários Grok Builds / agentes no mesmo PC)**:
  * Cada tarefa grande num ramo próprio a partir de `main`.
  * Preferir `git worktree` (vários checkouts no mesmo repositório sem conflitos de working tree).
  * Evitar editar os mesmos ficheiros em simultâneo.
  * Merge sequencial no fim (ou rebase). Ver também [TODO-structures-l1.md](TODO-structures-l1.md).
* **Para um único agente implementar tudo:** lê a secção 5 deste ficheiro e executa por ordem. Atualiza o HANDOFF após cada tarefa.


## Energia comum — camada L0 feita (7 nov 2026)

`acdt storage check` / MCP `storage_check`, núcleo `acdt.core.energy_storage` e
adaptadores finos de produtores existentes em `aircraft.storage`. Não duplica o
consumo/propulsão. Combustível utilizável, reserva/enchimento/DoD explícitos uma vez;
pack completo, nunca célula tomada como pack; massa/volume por dados fornecidos,
restrições abertas de volume alocado por portador ou total partilhado.

Exemplos executáveis de hélice térmica/elétrico pointmass, fecho jet e segmentos VTOL;
bloco opcional `storage` em jet/VTOL não muda massa, missão nem `feasible` antigos.
Dados em falta não passam. Massa inventariada não se soma ao que já foi dimensionado;
alocação de combustível/pack existente é verificada sem estimativa GA de depósito.
Ver [tutorial-energy-storage.md](tutorial-energy-storage.md).

**Estado 9 nov 2026 (não recomeçar):** fecho de massa VTOL opt-in, despacho híbrido L0,
fases comuns, filas/solo 1.2, frotas mistas, mapas leves de motor e `closure` térmico/CG/FOV
já estão em `main`. **Acrescento agora:** juiz comum jet/VTOL opt-in
(`flightsim/common_mission.py`, `operations.common_sim.enabled`) — pointmass+`engine_point`
para jato; timeline de energia nativa para VTOL. **Ainda pendente:** 6-DOF de falhas,
pyCycle/NPSS/CFD (PC do João), Torenbeek completo, mapas ECS, volume/CG/segurança de
storage no fecho de massa, certificação.
Build-up parcial de transporte posteriormente entregue no item 11: não é build-up completo.

**Acrescento 9 nov 2026 (jato componentes/pressurização):** regressões Raymer
transporte restantes e W_press opt-in; extração só com auxiliar fornecido. Exemplo
`components_raymer_extended.yaml`. Torenbeek completo e mapas ECS pendentes; campo ASD/TOD/BFL de triagem em `performance.field`.


## Carga útil/elétrica transversais — FEITO L0 opt-in, 7 nov 2026

Correção de âmbito pedida pelo João: payload e elétrica aplicam-se a todas as aeronaves,
não só a hélice. `acdt onboard size` / `onboard_size`, esquema 1.0, chama os dimensionadores
existentes com inventário/proveniência e propriedade de massas explícitos. Prop/jato recebem
payload/equipamento no fecho; elétrico/VTOL recebem hotel real na energia/pack; prop térmico/jato
recebem consumo e extração **fornecidos**, sem correlações de acessórios inventadas. No jato,
equipamento no build-up parcial é um item fornecido, não ajuste ao OEW. VTOL mantém MTOW
inclusivo e verifica orçamento com resto não-bateria declarado. Reserva/DoD uma vez só.

`mission` pointmass opcional só para prop, efetivamente com loads/extração acoplados, sem segundo
fecho. Capacidade/pico/volume/calor declarados e montagem/CG/FOV são checks separados, com
`null` para dados em falta. O adaptador não faz da P4 isolada nem dos comandos antigos um MDA
universal. Sem modelo de extração não corre dimensionamento com energia grátis.

**Acrescento 9 nov 2026 (fecho térmico/CG/espacial/FOV):** bloco opt-in `closure` em
`onboard_size` (`core/onboard_closure.py`) com primitivas abertas; exemplo
`closure_electric.yaml`. Screens L0, unknown≠pass.

**Acrescento 9 nov 2026 (hotel → burn nativo):** `onboard_bridge` — `acdt size`/`MissionSpec`,
`jet_size` e `size_vtol` consomem opt-in `onboard` para os hooks auxiliares/hotel já citados
(MIL-E-7016F / Moir & Seabridge via `analyse_onboard`; BSFC/η/`fuel_kg_kWh_terminal` entradas).
Sem bloco → no-op. Modelo incompleto ou híbrido sem dispatch → unassessed (nunca zero silencioso).
Não publica nem altera o estudo Nansei; não inventa potência de radar.

**Acrescento 10 nov 2026 (fecho automático no size):** o mesmo `onboard` no input de `acdt size`
fecha massa + combustível/energia **dentro** do ciclo (sem passo manual `onboard_size` /
`onboard_bridge` esquecível). `DesignResult.onboard_bridge` + `to_dict` / toolkit summary;
issue info «onboard auto-closed inside size». Ecrãs CG/FOV/`closure` e trades P4 continuam em
`acdt onboard size` / `systems-p4`. Morfológico energia/híbrido/datalink/SATCOM **feito** (10 nov 2026);
Eastlake/CER operacional **feito** (10 nov 2026, opt-in).

**Estado 9 nov 2026:** dispatch híbrido L0, fecho VTOL, mapas leves, `closure` espacial/térmico/CG/FOV
e juiz comum jet/VTOL (opt-in `common_sim`) já entregues — não relistar como “por fazer”.
**Por fazer de verdade:** extração BEMT/passo fixo e 6-DOF térmica; redundância/falhas/OEI de
geração; seleção combinada por pico do pack prop; realimentação automática no otimizador /
projeto ECS; pyCycle/NPSS/GasTurb/T-MATS/CFD no PC do João. Nada disto é certificação.
Exemplos `examples/onboard/` com deltas reproduzíveis; [tutorial](tutorial-onboard.md).
Nenhuma alteração ao estudo Nansei, nenhum solver pesado ou dependência nova.

## Feedback missão–propulsão–frota — FEITO primeiro encadeamento L0, 7 nov 2026

`mission_fleet_study` / `acdt fleet study`: N0 com intervalos/amostras sem forma →
receitas N1 `onboard_size` abertas → consumo real existente → serviço em terra →
frota homogénea revista. Prop térmico/elétrico usa pointmass nivelado já em voo;
jet usa Breguet equivalente e tempos pré/pós fornecidos; VTOL usa segmentos nativos
com MTOW inclusivo. Carga útil/hotel/extração não são metadados soltos. Híbrido fica
preservado por avaliar, sem dispatch inventado. Recarga E/(eta*P) com recurso dedicado,
ou tempo total fornecido com fonte. Checks desconhecidos críticos não entram em Pareto;
comparações só por amostra e cobertura das fases. Nenhum vencedor automático.

**Estado 9 nov 2026:** o esquema 1.1 (autonomia/fecho iterativo), 1.2 (filas partilhadas),
frotas mistas, fases comuns, hybrid dispatch, `closure` espacial/térmico/CG/FOV e juiz comum
jet/VTOL opt-in já estão feitos — ver secções abaixo. **Ainda aberto:** incerteza probabilística
acoplada, 6-DOF de falhas, MDA/otimizador com realimentação espacial, pyCycle no PC do João.
Nenhum motor/deck novo ou solver pesado. Ver `tutorial-mission-fleet.md` e `examples/fleet/`.

## Missão–frota iterativa — FEITO esquema 1.1 L0, 9 nov 2026

`acdt fleet study` / `mission_fleet_study` com `schema_version: "1.1"`: autonomia máxima
derivada por candidato (prop pointmass com alocações nativas de descolagem/subida retidas,
jato a MTOW fixo com os mesmos termos do fecho, VTOL até ao orçamento de massa inclusivo);
fecho iterativo dimensionamento↔capacidade só onde há dependência (prop/jato "rubber"),
com histórico de resíduos e estados de não-convergência; reserva operacional explícita
aplicada uma vez (fração nativa substituída e registada; prop térmico por avaliar);
frota pela permanência pedida ou máxima derivada. `1.0` inalterado.
**Acrescento 9 nov 2026:** VTOL com `aircraft.closure` (fecho de massa por componentes, `vtol/closure.py`)
entra no fecho iterativo como "rubber" (`n1.vtol_mass_closure`); exemplo `iter_vtol_closure.yaml`.
**Esquema 1.2 (9 nov 2026):** recursos de solo partilhados com filas FIFO determinísticas
(`core/concept/ground_queue.py`, DES Law 2015, ρ<1 Kleinrock 1975, Little 1961), laço
frota↔tempo de solo com histórico; exemplo `shared_vtol.yaml`. Frotas mistas por atribuição de
estações (`mission_fleet_mixed.py`), enumeração limitada, Pareto; exemplo `mixed_vtol_fixed_wing.yaml`.
Despacho híbrido L0 por regras (`hybrid_dispatch.py`) e cobertura de fases comuns (`mission_phases.py`,
`mission.required_phases`); exemplo `hybrid_dispatch.yaml`.

**Pendente:** filas estocásticas (Erlang), alternância de tipos na mesma estação, otimização de
velocidade de loiter, vento, volume de tanques, reservas regulamentares, mapas de motor/BSFC,
otimização de despacho (ECMS/DP), massa híbrida fechada. **Acrescento:** juiz comum jet/VTOL
opt-in (`common_sim` → pointmass+mapas / timeline VTOL). Mapas leves feitos; pyCycle/NPSS/GasTurb/T-MATS
continuam no PC do João.


## Juiz comum jet/VTOL — FEITO L0 opt-in, 9 nov 2026

`flightsim/common_mission.py`: jato voa fases canónicas no pointmass existente com
`engine_point` (Mattingly/Ihme ou mapa); VTOL sequencia potências nativas de `size_vtol`
nas mesmas fases. Fases não modeladas (táxi jato, descent VTOL, …) ficam `not_modeled` /
unassessed, nunca pass por omissão. Frota: `operations.common_sim.enabled` (ex.
`examples/fleet/jet_common_sim.yaml`, `vtol_common_sim.yaml`); 1.0/1.1/1.2 sem a flag
mantêm Breguet / segmentos nativos. Sem 6-DOF novo, sem CFD/JSBSim decks não validáveis.


## Atalhos V / bivigas + diedro — FEITO L0 opt-in, 9 nov 2026

`geometry.configuration: V|inverted_V|twin_boom` gera uma montagem de componentes
(`assembly/shortcuts.py`) consumida pelo ciclo `assumptions.assembly` já existente
(pesos Raymer 15.46–15.49, Purser & Campbell, `hq:*`/`gear:*` da montagem). Um
`assumptions.assembly` fornecido nunca é sobrescrito. `geometry.dihedral_deg` explícito
alimenta a asa e o `hq:spiral` (Clβ AVL); sem ele a espiral fica unassessed.
## Asa voadora — winglets + trem — FEITO L0 opt-in, 9 nov 2026

`assumptions.assembly.options.flying_wing` (off by default): `size_winglets` + required `c_vt`
(Raymer Eq. 6.29; chord-only iterative scale of tip fins/winglets) and/or `place_gear` (tricycle via
`gear_layout`, Raymer Ch. 11 tip-back / nose-load / rotation + 14 CFR 23.925). Missing method or
geometry → unassessed; empty tip-back band → infeasible with residuals (PRESSUPOSTO wider
`nose_fraction` only when documented). `extend_fuselage_for_gear` reverts on fail. Baseline
`uav150_flying_wing.yaml` (no flag) unchanged; closed example
`uav150_flying_wing_closed.yaml` + `flying_wing_pusher_closed.json` (W0≈152 kg, c_VT≈0.22,
dutch-roll/spiral Nível 1, gear tip-back/nose/rotation green with PRESSUPOSTO band [0.05, 0.22]).


## Trem convencional / esquis / pernas / cinemática — FEITO L0 opt-in, 9 nov 2026

`gear.type`: `taildragger`/`conventional`/`tailwheel` | `ski` | `tricycle` | `none` on the assembly
(`assembly/gear_devices.py` + `gear_layout` dispatch). Unknown → unassessed (no silent tricycle).
Taildragger: Raymer Ch. 11 tip-forward + overturn about tail wheel + 14 CFR 23.925 **9 in**.
Ski: requires `ski.length_m`. `draw_legs` writes `gear_leg` Body pods; `retract` samples a wheel-centre
arc for interference. Example numbers: taildragger W0-flight demo x_main≈0.86 m, x_tail=3.05 m,
tipback 15°, prop clearance 0.229 m (=9 in), overturn 52°; ski L=1.4 m, overturn 60.8° with
half_track 0.60 m. Baseline tricycle / omit-option unchanged.


## Formas de equipamento + corpos rodados AVL — FEITO L0 opt-in, 9 nov 2026

`Item.shape`: box (default) | sphere | cylinder (`cylinder_axis`). Packaging / FOV / volume / inertia
use the solid (Meriam & Kraige); AABB separation stays conservative. Rotated `Body.orientation` cannot
be written faithfully as AVL BODY (along x only) nor as Torenbeek App. E fuselage shift → contribution
**unassessed** (`bodies_avl_status`, `asm:avl_bodies`; `asm:static_margin` unassessed when
`np_source: avl_bodies`). Example numbers (`shapes_and_rotated_body.json`): eo_ball sphere V≈0.00305 m³,
I_sphere < I_box AABB; side_boom yaw 20° omitted from BODY; x_np_status unassessed under avl_bodies.

## Asa voadora sem deriva — split ailerons + SAS — FEITO L1 opt-in, 10 nov 2026

`assumptions.assembly.options.flying_wing.yaw_control: split_aileron` (ramo `tailless-split-aileron`,
`assembly/tailless.py`): guinada por split ailerons (arrasto McCormick 1995 Eq. 3.45, K_f = 1,7, por folha;
ΔC_l ≈ ΔC_m ≈ 0 de Löchert et al. 2019 em escoamento colado), SAS ativo por omissão no UAV (pedido do João:
piloto automático ativo é hipótese base no UAV). Casos: vento cruzado em derrapagem (14 CFR 23.233(a)),
coordenação (MIL-F-8785C IXa), turbulência Dryden (MIL-F-8785C, h = 50 ft) como autoridade do SAS. Célula nua
sempre reportada. Exemplo `uav150_flying_wing_tailless.yaml`: fecha a W0 ≈ 136 kg; célula nua ζ_d ≈ −0,03
(falha, informativo); com SAS k_β 0,01/rad, k_r 0,30 → Nível 1; autoridade 3σ 0,012 vs 0,021 e taxa 191 vs
200 °/s; vento cruzado 10,1 kt falha (máx ≈ 8,3 kt). Em aberto (ver o seguimento abaixo): decrab, ΔC_D medido para o perfil.

### Seguimento — o que faltava avaliar (10 nov 2026, ramo `tailless-unassessed`)

Novos módulos `assembly/tailless_actuation.py`, `tailless_approach.py`, `tailless_followup.py` e
`flightsim/tailless_sim.py`; linhas novas `hq:sas_time_delay`, `hq:lateral_gust`, `hq:actuators`,
`hq:pitch_trim_tailless`, `asm:actuator_mass`, `asm:crosswind_options`.

* Charneira: split por NACA TN 690 Figs. 17–18 (|C_hf| ≤ 0,64 até 60°), elevon por AVL HM; calendário
  14 CFR 23.455(a)(2). Servos do catálogo Volz (datasheets lidos a 10 nov 2026: DA 26, DA 30, DA 30-HT,
  DA 58-D) no YAML do exemplo; escolha 2× DA 30-HT por folha do split e 2× DA 26 por elevon; 9,9 kg no
  orçamento → W0 136 → 157 kg.
* Atuador no SAS: atraso 0,10 s (limite Nível 1 de MIL-F-8785C 3.5.3, PRESSUPOSTO por falta de dados do
  servo); SAS redimensionado com o atuador → Nível 1 em cruzeiro e aproximação, margem de atraso 0,14 s.
* Rajada lateral 14 CFR 23.443/23.333(c) como caso próprio: falha por tocar no limite de taxa (0,35 % do
  tempo, singularidade da lei sin² em δ = 0); de resto amortece.
* Vento cruzado: opções avaliadas; fecha só com aproximação a 1,2 V_S0 (rolagem ×1,19). Requisito não relaxado.
* α ≈ 22° na aproximação: o exemplo **não equilibra em picada** com elevons de 25° nos casos com carga
  (margem estática 0,34–0,49) e o `CLmax_landing` inclui um flap que o desenho não tem. Assinalado em
  `hq:pitch_trim_tailless`; corrigido depois no ramo `tailless-pitch-trim` (ver abaixo).
* 6-DOF: modelo de voo da montagem + ensaio lateral + doublet no JSBSim (NRMS ≈ 3 %); missão 6-DOF não corre.

### Correção do equilíbrio de picada (10 nov 2026, ramo `tailless-pitch-trim`)

Novo módulo `assembly/tailless_trim.py`. As opções novas são todas opt-in:

* `options.useful_load_at: empty_cg`: carga sem posição e combustível sem tanque vão para o CG das massas
  fixas (Raymer 2018 Sec. 15.1). Packaging unassessed.
* Banda de margem estática 0,02–0,08 de NACA TR-796, com aviso fora da banda.
* Verificação da torção por Panknin (exemplo publicado reproduzido no teste).
* `flying_wing.clmax: trimmed`: CLmax de dimensionamento = C_L máximo equilibrado; re-dimensiona até
  |Δ| < 0,01.
* 6-DOF lateral em todos os casos que equilibram.

O exemplo passou para: carga no CG das massas fixas, SM alvo 0,05, torção −10°, sem flap, servos do split
DA 30. Resultados:

* W0 157,0 → 138,3 kg; CLmax 1,128.
* SM 0,051–0,063; δe de cruzeiro +7,6…−0,9°.
* `hq:pitch_trim_tailless` e `hq:yaw_crosswind` passam (máximo 14,5 kt).
* Fugóide desce para Nível 2 (ζ 0,039).
* Só aumentar a elevon não fecha (δe −166…−354°).

Os testes estão em `tests/test_tailless_pitch_trim.py` e no teste do exemplo.

Em aberto: packaging da carga no CG; C_m dos corpos no trim; fugóide em Nível 2; JSBSim vs 6-DOF pior no
exemplo corrigido (NRMS ≈ 0,2–0,3, por explicar); taxa da elevon; curso/rigidez dos servos sem dados; C_h da folha
superior/0,40c; decrab e carga lateral no trem; missão 6-DOF sem deriva; ΔC_D medido.

### Itens em aberto tratados (11 nov 2026, ramo `tailless-open-items`)

* **JSBSim vs 6-DOF** (`flightsim/jsbsim_export.py`, `jsbsim_runner.py`, `sixdof.py`, `tailless_sim.py`). Causas
  encontradas e corrigidas:
  1. O doublet a 30 % da capacidade fazia a célula nua divergir (β 40–80°), fora das tabelas lineares. Passou a
     3 % (`JSBSIM_DOUBLET_FRACTION`).
  2. O export não tinha o arrasto induzido de C_Lδe·δe e C_Lq·q̂, o que dava manete de trim 0,612 vs 0,547.
  3. A latitude do IC no JSBSim era 0°, com g cerca de 0,3 % menor e Δα de trim 0,02–0,04°. Passou para 45°.
  4. A força lateral aplicada no AERORP deslocado criava guinada a mais (corrigida com a função
     `Yaw_aerorp_side_force_correction`). Faltava também a componente −D·sinβ na força lateral de corpo do 6-DOF
     (é dominante numa asa voadora: C_Yβ ≈ −0,001 contra C_D ≈ 0,03). As forças passaram para eixos de vento
     (JSBSim Reference Manual, DRAG/SIDE/LIFT).

  Com os momentos pontuais iguais a ≈ 0,03 %, a NRMS β (8 s) fica em carga 0,019, combustível 0,020, cheio 0,020
  e vazio 0,119. No caso vazio, a célula nua é instável e oscilatória (σ 0,060 1/s, duplica em 11,6 s; C_nβ < 0 no
  α de trim). A sensibilidade do próprio modelo a Δα 0,007° já dá NRMS 0,08, o que explica o resíduo.
  `jsbsim_cases` traz os 4 casos.
* **Rajada lateral** (`hq:lateral_gust`): mantém-se **falha**, com critério estrito (não se encontrou norma citável
  que admita saturação de taxa breve). As opções que a fecham são reportadas:
  * servo ×2 (191 °/s): não fecha;
  * servo ×5 (478 °/s): fecha;
  * pré-deflexão simétrica δ0 = 2° (lei 2C₁ sin2δ0 sin2d, linear em zero; Rajput, Zhang & Qu 2014; Wang, Wang
    & Jia 2011): fecha, com taxa de pico 46 °/s e ΔC_D +0,7 % de C_D0, que não está no polar de dimensionamento.
    Os custos de 4/6/8/10° são 2,9/6,5/11,5/17,8 %.
* **Fugóide com piloto automático** (`hq:phugoid_autopilot`, Beard & McLain 2012 Sec. 6.4.1). Com manutenção de
  atitude, ganhos k_pθ −1,74 e k_dθ −0,72 s, raízes reais −0,537 e −0,167 → Nível 1. O período curto fica com
  ζ 0,75. A célula nua continua com ζ 0,039 (Nível 2), reportada.
* **Packaging da carga útil no CG** (`asm:useful_load_packaging`, `tailless_trim.cg_packaging`). O combustível
  ocupa 31,6 L (0,72 kg/L PRESSUPOSTO + 2 % de expansão, 14 CFR 23.969) e cabe em volume bruto a ±0,075 m do
  CG vazio (asa 27 L + corpo 6 L). Só no corpo central precisa de ±0,39 m. Para a carga de 27 kg, a densidade
  média necessária é 1,15/0,64/0,33 kg/L a ±0,12/0,17/0,28 m. A linha fica **None**: o volume bruto é condição
  necessária, não suficiente.
* **Taxa da elevon**: a exigida é 100 °/s (pico do bank hold na rajada), contra 121 °/s do DA 26 → `hq:actuators`
  passa.
* **C_m dos corpos**: entra como sensibilidade (Torenbeek, ΔX_np), sem mudar o resultado principal. Dá δe de
  cruzeiro +11,4/+6,8/+9,8/+5,1° e C_L equilibrado (limite da elevon) ≥ 1,68.

Testes: `tests/test_tailless_open_items.py`, `test_export_consistency_fixes_11nov2026`,
`test_drag_has_body_side_component_with_sideslip`, e o teste do exemplo atualizado.

Em aberto: packaging fino (estrutura/sistemas) e volume da carga; servo/curso/rigidez sem dados; C_h da folha
superior/0,40c; ΔC_D medido (os outros itens foram tratados a 12 nov, abaixo).

### Pré-deflexão no polar, decrab e missão 6-DOF sem deriva (12 nov 2026, ramo `tailless-bias-decrab-mission`)

* **Pré-deflexão no polar**: `split_aileron.bias_deg` (opt-in) soma ΔC_D0 = 2·K_f(c_f/c)^1,38(S_f/S)·2sin²δ0
  (McCormick Eq. 3.45, as duas asas) ao C_D0 do dimensionamento (`assembly_loop.drag.split_bias`). Com chaves
  em falta → unassessed, nunca 0. O exemplo usa 2°: ΔC_D0 0,000202 (0,7 %), W0 138,3 → 138,6 kg, S 2,906 →
  2,909 m². `hq:lateral_gust` passa: split 8,8°, 46 °/s, sem limite de taxa. No 6-DOF do caso `cheio`, o limite
  de taxa é tocado em 0,04 % do tempo (pico 95 °/s).
* **Missão 6-DOF**: o laço de derrapagem usa o split (k_β, k_r do SAS; washout τ 4,2 s, MIT 16.333 Lecture 12,
  PRESSUPOSTO). Decrab por PD+I de rumo no eixo de guinada (Beard & McLain 2012 Eq. 6.7–6.8 e Sec. 6.5;
  e_ψ,max 20° PRESSUPOSTO) com feed-forward −C_nβ β. Trem da montagem e para-choques nas pontas de asa.
  Direção no solo com o mesmo canal (sinal do leme de arrasto).
* **Exemplo** (`examples/simulation/uav150_tailless_crosswind.yaml`, 5,2 m/s a 90° da pista): 11,2 min. Crab
  −9,1° no início do decrab a 30 m → resíduo −0,2°, deriva 0,35 m/s, φ −0,8°. Cargas laterais no trem principal:
  744 N para dentro (1,07×) e 732 N para fora (1,59×) dos limites de 14 CFR 23.485 (0,5 W / 0,33 W, pré-Amdt
  23-64). As pontas de asa tocam (93/15 N) com a bitola mínima 0,42 m → `side_load_ok` False. Descolagem
  limitada pela rotação: rolagem 1053 m (pedido 300 m), elevon saturada a −25°.

Testes: `tests/test_tailless_mission.py` e o teste do exemplo atualizado (missão incluída).

Em aberto: rotação na descolagem (trem principal mais perto do CG ou mais elevon); bitola/estrutura do trem para
as cargas laterais; inclinação contra a deriva no toque; o limite de taxa a 0,04 % no `cheio`; sensibilidade ao
modelo de atrito; servo/curso/rigidez; C_h da folha superior/0,40c; ΔC_D medido; C_m dos corpos no resultado
principal; packaging fino.

### Trem da asa sem deriva: rotação e bitola (12 nov 2026, ramo `tailless-gear-rotation-track`)

* **Diagnóstico**: com o corpo nivelado a rotação é impossível. A elevon de uma asa sem cauda quase não tem
  momento em torno das rodas (o C_Lδe para baixo cancela-o) e C_L(α=0) = −0,29. Tip-back pede d ≥ 0,114 m e a
  rotação (Sadraey 2012 Sec. 9.6.2, θ̈ ≥ 8 °/s² PRESSUPOSTO para UAV) pede d ≤ 0,053 m: banda vazia; a elevon
  precisaria de −108°.
* **Correção (opt-in)**: `gear.ground_attitude_deg: 19` (atitude de descolagem; extensão da perna do nariz,
  exceção B-52 da mesma secção) e `gear.wheelbase: shortest`. `gear_layout` mede tip-back, rotação e hélice
  na atitude; nova linha `gear:takeoff_rotation` (`flightsim/tailless_takeoff.py`); 6-DOF arranca na atitude,
  descola em `fly_off` e conta toques de ponta/traseira. Sem a opção, nada muda.
* **Exemplo**: principal x 1,307 m, nariz x 0,289 m, extensão 0,351 m, nariz 14,1–15,0 % (Raymer 8–15 %),
  meia-bitola 0,554 m. Rolagem 293 m (massa pontual) / 299,4 m (6-DOF, ar calmo) / 329,5 m (vento cruzado)
  contra 300 m. Cargas laterais no toque 0,50×/0,58× de 23.485. Folga das pontas 11,2° na atitude. W0 138,6 →
  150,4 kg. Bitola maior (0,8–1,0 m) tira os toques mas leva a carga para fora a ~1,5× — rejeitada como
  único remédio. 14 CFR 23.233(a) 0,2 V_S0 não é relaxado. O hold de rolamento no solo já estava activo
  (fly-off e rolagem de aterragem) e não chega com ~11° de folga.

### Patins de ponta (12 nov 2026, ramo `tailless-tip-skids`)

Opt-in `gear.tip_skids` (`assembly/gear_devices.size_tip_skids`, ligado no exemplo). Sapatas de ponta à
maneira de outrigger / tip gear (Raymer 2018 Ch. 11) dimensionadas por energia E = η N δ (Currey 1988;
Raymer Sec. 18.2; Sadraey 2012 Sec. 9.7) para a massa efectiva da ponta a cair a folga estática. Curso
25 mm, η ≈ 0,5 e piso de instalação 0,08 kg/lado são PRESSUPOSTO (sapata sólida, não oleo; nunca massa
silenciosa a zero). A massa (0,16 kg no exemplo) fica no relatório; não entra no laço de W0 neste passo
(evita desviar o CG depois da margem estática já fechada; ~0,1 % de W0). Contacto de patim dimensionado deixa de falhar `side_load_ok` (14 CFR 23.485 fica no
trem principal); reporta-se `tip_skid_ok` / `skid_contacts_N`. A secção teórica é Al 2024-T3 (MMPDS Fcy).

Testes: `tests/test_tailless_gear.py` (energia e `apply_gear_devices`) e o teste do exemplo atualizado.

O 6-DOF no exemplo (vento 10 kt) ainda regista `aft_strike` no eixo (hélice/bordo de fuga, folga estática
~0,18 m na atitude de 19°) junto com o contacto do patim (~192 N na descolagem, ~65 N na rolagem). Não é
evento de patim e não falha `side_load_ok`; fica reportado, não tratado como passa.

### Rolagem, estrutura 23.485, arrasto das pernas e Sadraey 9.5.3.2 (12 nov 2026, ramo `tailless-landing-roll-gear`)

A atitude de 19° já tem a roda do nariz no solo: o nariz não pode baixar na rolagem. O 6-DOF passa a
levar a elevon ao batente de descarga de sustentação após 1 s (analogia aos spoilers / lift-dump de
Raymer 2018 Sec. 17.9). `lift_dump` fica nas métricas da aterragem. A margem de atitude à perda (4,3°)
é informativa; o critério citado continua V_LOF/V_S ≥ 1,1 (Raymer Sec. 17.8), já 1,15 no exemplo.

Opt-in `gear.assess_structure` (ligado no exemplo):

* Área equivalente `fixed_gear` 0,03 m² era da família UAV 150 kg com pernas 0,35/0,30 m; aqui 0,47/0,78 m
  → factor 1,72 (0,0516 m²). Reportada, **não aplicada** ao polar neste passo (1,72× no C_D0 arriscaria
  a margem 299 m ≤ 300 m da descolagem).
* Pernas principais como consolas verticais (PRESSUPOSTO, sem braço de arrasto) às cargas 14 CFR 23.485
  (0,5 W para dentro / 0,33 W para fora, vertical 1,33× a carga estática na roda), Al 2024-T3 MMPDS, FS 1,5.
* Sadraey 2012 Sec. 9.5.3.2: viga simplesmente apoiada nas rodas, δ = W T³/(48 EI) com EI conservador
  (caixão à espessura mínima MMPDS, 0,25–0,70 c, PRESSUPOSTO). O δ admissível do livro não é citado → a
  deflexão e o ΔΓ são reportados, o passa/falha fica unassessed (desconhecido ≠ passa).

Testes: `tests/test_tailless_gear.py` (energia, lift-dump, escala de arrasto, 23.485, Sadraey 9.5.3.2).

Em aberto (depois deste passo): contacto aft/hélice-bordo de fuga na missão com vento cruzado; posição de
fixação e inclinação das pernas PRESSUPOSTO; catapulta/ventre só mencionados; área de trem escalada ainda
não aplicada ao polar.


### Trim principal com C_m dos corpos, packaging fino, atrito e taxa do split (12 nov 2026, ramo `tailless-trim-packaging-friction`)

O C_m dos corpos (desvio Torenbeek do ponto neutro, C_m += C_N k com k = −ΔX_np/c̄ = **+0,0279 c̄** no
exemplo; o mesmo termo da margem estática e do 6-DOF) entra no equilíbrio de picada principal. C_m0 dos
corpos = 0 (PRESSUPOSTO). O trim só com a asa AVL fica em `avl_wing` (sensibilidade). `hq:pitch_trim_tailless`
passa. δe de cruzeiro (com corpos / só asa AVL): vazio +11,5/+7,4°, carga +6,9/+1,7°, combustível +10,0/+4,9°,
cheio +5,4/−0,8°.

O laço W0 do CLmax equilibrado **não** usa este termo como crédito. Com C_m0 = 0 PRESSUPOSTO, tomá-lo
subia o CLmax 1,15→1,24, encolhia S 3,186→2,873 m² e a rolagem fly-off ia a 307 m > 300 m. O CLmax de
dimensionamento permanece o da asa AVL (`approach_consistency(..., include_bodies=False)` só nesse laço).
Sub-relaxação ω = 0,5 (PRESSUPOSTO numérico) e avaliação final do desenho devolvido ficam no fecho, para o
ponto fixo não oscilar se o termo voltar a acoplar. W0 **150,4 kg**, S 3,186 m², inalterados.

Packaging fino (`tailless_trim.fine_packaging`, linha `asm:fine_packaging`): combustível empacotado no volume
bruto, primeiro no corpo e depois na asa, nas células mais perto do CG vazio (Raymer 2018 Sec. 15.1). No
exemplo o combustível (33,6 L) cabe todo no corpo, centróide −106 mm do CG vazio; a carga não tem volume
desenhado — estação candidata +75 mm no residual (0,15 kg/L no volume bruto livre), volume unassessed. CG
cheio vs lumping no CG vazio +6 mm. SM empacotada (NACA TR-796): vazio 0,050, combustível 0,076, carga 0,029,
cheio 0,054 — dentro da banda. `ok` é None (volume da carga unassessed; desconhecido ≠ passa). O equilíbrio
principal mantém `useful_load_at: empty_cg`.

Sensibilidade ao atrito (`friction_sensitivity`): primeira ordem, cinemática congelada no toque. Rácios
23.485 neste voo (μ 0,8): 0,71× para dentro / 0,66× para fora (numa missão anterior, 0,50×/0,58×). Banda
PRESSUPOSTO μ 0,6 / 0,8 / 1,0: 0,53/0,49, 0,71/0,66, 0,89/0,82 — todos ≤ 1. μ_travão 0,3–0,5 (Raymer 2018
Table 17.1) só como contexto. Não é uma re-simulação 6-DOF.

O contacto com o limite de taxa do split no `cheio` deixa de ser um passa silencioso: `yaw_split` inclui
`rate_max_deg_s` e `rate_limit_note`. Neste voo o limite (84 °/s na superfície, já com desmultiplicação) foi
tocado em 0,21 % do tempo; o pico reportado é a taxa já limitada. Sem saturação de comando. Sem alteração de
bias/ganhos. A missão é avaliada à parte (derrapagem, decrab).

Rolagem de aterragem com lift-dump (já em main, PR #59), medida neste teste: **258 m** (era 307 m sem
descarga de sustentação). `side_load_ok` e `tip_skid_ok` True; contacto de patim 112 N; `aft_strike` residual
113 N, reportado, não tratado como passa.

Testes: `test_body_cm_derivatives_enter_trim`, `test_friction_sensitivity_scales_with_mu`, e o teste do
exemplo (`bodies_in_main_trim`, `avl_wing`, `fine_packaging` com SM na banda e `ok is None`,
`friction_sensitivity`, campos de taxa).

Em aberto: contacto aft/hélice-bordo de fuga; fixação/inclinação das pernas PRESSUPOSTO; catapulta/ventre
só mencionados; área de trem escalada não aplicada ao polar; volume da carga (sem dimensões dos itens);
curso/rigidez do DA 30 sem ficha; C_h da folha superior a 0,40c; ΔC_D medido do perfil.

### Itens em aberto da asa sem deriva, ronda 2 (18 nov 2026, ramo `tailless-open-items-2`)

Revisão dos sete itens da ronda 2 no main público (`a686d82`), com o exemplo a W0 149,7 kg:

| item | estado | onde / números |
|---|---|---|
| limite de taxa na rajada lateral | linear fechado a 11–12 nov (δ0 = 2°); **6-DOF graduado agora** | `lateral_gust_6dof` (abaixo): o caso `cheio` falha pelo critério estrito |
| fugóide Nível 2 (MIL-F-8785C) | fechado a 11 nov (`hq:phugoid_autopilot`) | célula nua ζ 0,042 (no limite do Nível 1, ζ ≥ 0,04); com manutenção de atitude ζ 0,96 → Nível 1 |
| JSBSim vs 6-DOF | fechado a 11 nov; reverificado | NRMS β carga/combustível/cheio 0,022/0,021/0,024; vazio 0,055 com sensibilidade própria 0,037 (célula nua instável) |
| packaging da carga/combustível no CG | combustível fechado a 11–12 nov; **carga em aberto (dados)** | 33,7 L cabem no corpo; volume da carga sem dimensões dos itens → `None` |
| taxa exigida da elevon | fechado a 11 nov; reverificado | 99 °/s ≤ 117 °/s (1× Volz DA 30 na superfície) |
| C_m dos corpos no trim | Torenbeek no trim principal desde 12 nov; **C_m0 de Multhopp agora** | +0,0101 (abaixo) |
| decrab / missão 6-DOF com vento cruzado | fechado a 12 nov; reverificado | crab −9,0° a 30 m → resíduo −0,3°, deriva 0,35 m/s; 23.485 0,60×/0,62× → passa |

* **C_m0 dos corpos** (`assembly/body_moment.py`): Multhopp 1942 (NACA TM 1036), na forma de Nelson 1998
  Sec. 2.3 e de Tulapurkara (NPTEL, IIT Madras) Eq. 2.56: C_m0,f = (k2−k1)/(36,5 S c̄) Σ w_f² (α_0L,f + i_f) Δx,
  com i_f negativo para cauda levantada. k2−k1 vem do esferoide prolato de Lamb (§373) / Munk 1924 (NACA TR-184).
  Os testes reproduzem a tabela de Munk (l/d 2, 4, 6, 10) e o Exemplo 2.4 de Tulapurkara (C_m0,f −0,0357).
  α_0L,f = −C_L0/C_Lα da asa AVL a δe = 0. PRESSUPOSTOS: sem o campo de upwash no termo de C_m0; o corpo central
  parcialmente imerso é tratado como corpo inteiro; corpos rodados ficam unassessed. O valor é sempre
  reportado (`approach_consistency['bodies_cm0']`, `body_cm0_alternative` por caso). Só entra no trim
  principal com `flying_wing.body_cm0: multhopp`; por omissão C_m0 = 0 (PRESSUPOSTO), como antes. O laço W0
  do CLmax continua sem termo dos corpos. No exemplo (opção desligada) dá C_m0 +0,0101, com α_0L,f +3,9°
  (torção −10°), finura 8,8 e k2−k1 0,93. O δe de cruzeiro passaria de +11,4/+6,8/+9,9/+5,3° para
  +15,8/+11,2/+14,2/+9,6° (vazio/carga/combustível/cheio), todos dentro de ±25°.
* **Rajada lateral no 6-DOF** (`flightsim/tailless_sim.gust_verdict_6dof`, `lateral_gust_6dof` no resultado de
  `acdt simulate … --fidelity 6dof`): aplica o mesmo critério estrito de `hq:lateral_gust` em cada caso de
  massa: sem saturação, sem limite de taxa e β amortecido. Se o limite de taxa for tocado, volta a voar a
  rajada sem limite e reporta a taxa exigida. Antes o contacto só ficava reportado; agora é uma falha.
  No exemplo, vazio/carga/combustível passam (picos 43/73/53 °/s), mas o **cheio falha**: toca o limite em 0,54 %
  do tempo e, sem limite, o pico é 100 °/s contra os 84 °/s do split na superfície (2× Volz DA 30 por folha,
  ×1,20). O modelo linear passa (49 °/s), porque a diferença está na não linearidade do 6-DOF. O desenho não foi
  alterado. As opções (servo mais rápido, mais pré-deflexão, ganhos) ficam para decisão.

Testes: `tests/test_tailless_open_items_2.py` e o teste do exemplo (`bodies_cm0`, `lateral_gust_6dof`).

Em aberto: volume da carga (precisa das dimensões dos itens); escolher o remédio da rajada 6-DOF no `cheio`
(o servo a ≥ 100 °/s na superfície ou δ0 > 2° re-verificado no 6-DOF); validar o C_m0 de Multhopp de um corpo
imerso contra ensaio/CFD (pesado, PC do João); curso/rigidez do DA 30; C_h da folha superior a 0,40c;
ΔC_D medido.

### Longarina traseira vs charneira (12 nov 2026, ramo `tailless-wingbox-hinge`)

A Fase 5/6 lê agora todas as superfícies de bordo de fuga de `options.flying_wing` (elevon, split aileron,
aileron) e põe a longarina traseira à frente da charneira mais avançada, menos 3 % c (`rear_spar_xr_max`).
No exemplo sem deriva o split tem cf/c = 0,40 (charneira a 0,60 c) e a omissão da Fase 3 (0,65 c) ficava
atrás; a partida é recuada (`hinge_notes`). Sem essas chaves, o comportamento legado
(`stability.aileron_cf_c`, omissão 0,25 → xr_max = 0,72) não muda. A inversão de aileron das superfícies
desenhadas ficou **unassessed** neste ramo; tratada a seguir.

### Secção fixa, inversão nas superfícies reais e RF de encurvadura (12 nov 2026, ramo `wingbox-hold-section-controls`)

* **`assumptions.structures.wingbox.hold_section`** (opt-in; também `acdt wingbox --hold-section` e
  `wingbox6 --hold-section`). Fixa t/c, curvatura e torção geométrica na geometria de partida. A torção
  de partida lê-se da asa principal da montagem (ponta menos raiz); sem montagem permanece 0°. Sem a
  opção o SLSQP continua a poder alterá-las (legado). O varrimento de t/c da Fase 5 é omitido quando a
  secção está fixa. O exemplo `uav150_flying_wing_tailless.yaml` liga a opção: a torção de Panknin de
  −10° que fecha o equilíbrio em picada deixa de ser baixada para ≈ −2°.
* **Inversão / eficácia de comando** nas superfícies desenhadas (`control_effectiveness`, Wright & Cooper
  2015 Cap. 9; Bisplinghoff, Ashley & Halfman 1955 Cap. 8; Glauert 1926). A restrição usa a superfície de
  rolamento mais crítica (elevon no exemplo). O canal de guinada do split (McCormick Eq. 3.45) não inverte
  por este mecanismo e fica unassessed; o V_R do split é só o acoplamento de rolamento com derivadas de
  flap liso (PRESSUPOSTO). A interface antiga `aileron_reversal_speed` (aileron exterior) mantém-se.
* **Factor de reserva de encurvadura** na Fase 6 (`box.details.buckling_reserve`): factor de carga até à
  envolvente para as peles (interacção Allen/Zenkert no sanduíche; condição de pele metálica à carga
  limite) e para cada nervura (encurvadura de corte ∝ t³, esmagamento ∝ t³, corte ∝ t). RF > 1 à bitola
  mínima.

Testes: `tests/test_wingbox.py` (hold, torção da montagem, inversão na elevon), `test_phase3.py`
(eficácia no vão interior), `test_phase6_wingbox.py` (RF numérico). Suite completa: 1003 passed, 6 skipped.

Estudo do exemplo sem deriva com `hold_section` (Fase 5 depois Fase 6, 12 nov 2026):

* Torção −10°, t/c 0,13/0,10 e curvatura 0,04 fixos (antes o ótimo livre ia a torção −2,1° e t/c de raiz 0,104). Em 14 nov 2026 o desenho da asa sem deriva passou a t/c 0,15/0,12; este estudo de massas não foi repetido.
* Fase 5: caixão 5,91 → 5,25 kg; longarinas 0,25/0,50 c. Sem inversão (V_R = ∞) na elevon; eficácia de
  rolamento a 1,2 V_D η = 1,028 (ligeiramente acima do rígido; o eixo fica à frente o bastante para
  não haver reversão). Flutter V_F 187 m/s (margem +2,21). Split: η de rolamento 1,018; guinada unassessed.
* Fase 6 (compósito, viga calibrada): caixão 6,18 → 5,47 kg; longarinas 0,30/0,55 c (0,05 c à frente do
  split, 0,20 c à frente da elevon); 6 nervuras/semi-asa, passo 0,40 m; peles no calibre mínimo 0,5 mm,
  núcleo 5,6 mm na raiz. Sem divergência nem flutter até 4 V_D (varrimento do modelo de faixas). Elevon
  η = 1,088 a 1,2 V_D, V_R = ∞. RF de encurvadura mínimo das peles = 1,00 (dimensionadas à interacção
  Allen/Zenkert); nervuras RF 1,00 nas cinco interiores (esmagamento / encurvadura de corte) e 1,36 na
  da ponta (bitola mínima).

### Carga lateral 23.485 no toque: banda de tolerância declarada (14 nov 2026, ramo `fix-side-load-tolerance`)

O teste `test_tailless_example_closes_bare_fails_sas_passes` falhava no Windows em `side_load_ok` e passava
no Linux. Medido no Linux (15 corridas da missão de vento cruzado do exemplo, velocidade do vento perturbada
em 0, ±1e-12, ±1e-9, 1e-6, ±1e-5, ±1e-4, ±3e-4, ±1e-3 relativo): razão para dentro **0,588–0,632** do limite
0,5 W, para fora **0,018–0,574** do limite 0,33 W (bimodal: a roda que fica com a carga para fora muda
de corrida para corrida). O projeto **não está no limite** no Linux: margem mínima ≈ 0,37. A falha do
Windows não é, por isso, arredondamento à volta de 1,0: a trajetória do toque diverge noutra plataforma (a
missão de ~30 min é sensível às condições iniciais). Os números do Windows não estão disponíveis aqui.

Alteração (`flightsim/mission.side_load_band`): veredicto em banda com a tolerância numérica declarada
`SIDE_LOAD_RATIO_TOL` = ±5 % (a dispersão medida da razão para dentro, ±3,6 % em torno de 0,61,
arredondada; PRESSUPOSTO numérico, não margem de certificação). Razão máxima ≤ 1 − tol → `passa` (True);
> 1 + tol → `excede` (False); entre os dois → `no_limite` (None, não avaliado ≠ passa). Nunca transforma uma
excedência em passa. Reporta-se sempre `side_load_margin` = 1 − razão máxima, `side_load_status` e a fonte da
tolerância. Sem contacto do trem principal na janela do toque → `nao_avaliado` com nota. O teste do exemplo
exige `passa` e, se falhar, mostra no log as razões, as cargas por roda, φ, deriva, crab residual, contactos
de para-choques e a razão de descida, para diagnosticar a corrida do Windows. Teste unitário novo:
`test_side_load_band_declared_tolerance`.

Em aberto: a corrida do Windows (precisa das razões que o teste passa a imprimir); a origem da divergência
entre plataformas (AVL do Windows, BLAS ou a ordem das operações) não foi isolada.

### Folga traseira dinâmica: hélice / bordo de fuga / cauda (14 nov 2026, ramo `gear-aft-strike`)

Módulo novo `flightsim/ground_clearance.py`, genérico (qualquer aeronave com contactos `aft_*` ou
`tail_strike` no modelo de solo do 6-DOF). Geometria de Sadraey 2012 Sec. 9.5.1.3, Eq. 9.2–9.3: o avião roda
em torno do contacto principal; um ponto a AB atrás e H acima toca a α_C = atan(H/AB); exige-se α_C > α_TO,
e o mesmo texto aplica-o à aterragem a α alto. O `asm:gear_rotation` (Raymer Ch. 11, 10–15°) continua a
verificação estática. O 14 CFR 23.925(a)(1) (7 in) aplica-se às atitudes de descolagem nivelada e de rolagem
e já está em `asm:gear_prop_clearance`; não se aplica à rotação nem ao flare, onde o contacto da hélice é
reportado como toque.

* `AftMonitor` amostra a cada passo da descolagem e da aterragem, com a roda principal a menos de 0,5 m do
  solo (PRESSUPOSTO): folga de cada ponto traseiro, θ, q, velocidade de descida do ponto, compressão do
  trem principal e força de contacto.
* `assess_aft_clearance` junta as fases: folga mínima e fase, θ máximo perto do solo, α_C descomprimido e
  α_C com a compressão máxima medida, margem de atitude e `ok` (folga > `min_clearance_m`, PRESSUPOSTO 0 m;
  Sadraey cita ~30 cm para transportes, não escalado). Opções sempre reportadas, nenhuma aplicada: limite
  de atitude no piloto automático (α_C comprimido − 2°, PRESSUPOSTO), extensão das duas pernas Δh e
  para-choques de cauda por energia (E = ½ m_eff v², N_des = n_ult E/(η δ), Currey 1988 / Raymer Sec. 18.2
  / Sadraey Sec. 9.7; m_eff = 1/(1/m + l²/I_yy); v = pico do 6-DOF da descida do ponto traseiro, PRESSUPOSTO;
  curso, η e piso de massa iguais aos patins de ponta). Opções configuráveis na chave `aft_clearance` da
  missão.
* Resultado em `mission.aft_clearance`, por fase em `segments[*].aft_clearance`; a CLI imprime uma linha.

Exemplo sem deriva (vento cruzado 5,2 m/s, caso `cheio`): ponto crítico `aft_strike` (AB 0,283 m, H 0,285 m),
α_C 45,2° descomprimido e 24,1–25,6° com a compressão máxima do toque (0,150–0,158 m). θ máximo perto do solo
22,6° (descolagem fly-off, 3,6° acima da atitude estática). Folga mínima **0,062 m** na descolagem e 0,100 m
na aterragem. Sem contacto em 9 corridas com o vento perturbado (0 a ±1e-3 relativo); `ok` True. Margem de
atitude pequena (~2–3°). Para-choques, se for preciso: m_eff 60,6 kg, v 1,16–1,17 m/s, E ≈ 41 J, N_des ≈ 4,9 kN,
massa 0,08 kg (piso). Δh das pernas 0 (não é preciso). O `aft_strike` de 113 N registado a 12 nov não se
repete no main atual (depois do PR #60); não foi reconstituída a causa.

Testes: `tests/test_aft_clearance.py` (Eq. 9.3, monitor contra a geometria do pivô, opções, não avaliado) e o
teste do exemplo (estrutura do veredicto, sem fixar `ok`).

Em aberto: a compressão vem da mola do modelo de solo (deflexão estática 0,07 m, PRESSUPOSTO), não de um
amortecedor dimensionado; só o ponto que toca primeiro na rotação nivelada é monitorizado (não o pior ponto
com rolamento); a velocidade de projeto do para-choques não é uma razão de descida de certificação.

### Catapulta e aterragem de ventre, 1.ª ordem e opt-in (14 nov 2026, ramo `launch-recovery-catapult-belly`)

Módulo novo `launch_recovery.py`, genérico para qualquer UAV de asa fixa. Só corre com
`assumptions.launch_recovery` (omissão `None`: nada corre e nenhuma verificação é acrescentada). As
verificações `lr:*` são reportadas como as de layout (`LAYOUT_PREFIXES`) e não mudam a viabilidade da Fase 1.

* **Catapulta** (`catapult`): Fahlstrom, Gleason & Sadraey 2022, *Introduction to UAV Systems* 5.ª ed.,
  Cap. 17 (17.3). Usa L = V²/(2a), o balanço de energia e F_shuttle = (W + W_shuttle)(a/g + sin θ). V_fim ≥
  k V_S com k = 1,1 (PRESSUPOSTO, análogo ao V_LOF ≥ 1,1 V_S de Raymer 2018 Sec. 17.8); o vento de frente
  conta. ΔE_propulsão = 0 e perdas = 0 (PRESSUPOSTO, como no texto). Entradas: `accel_g` ou `stroke_m`,
  `rail_angle_deg`, `shuttle_mass_kg`, `stroke_max_m`, `airframe_nx_limit_g`, `payload_nx_limit_g`. Sem limite,
  a verificação fica não avaliada (None).
* **Ventre** (`belly_landing`): energia de Currey 1988 §5.3 (`landing_gear.gear_load_factor`) no curso do
  patim, com a descida de 14 CFR 23.473(d) e κ ≤ 2/3 (23.473(e)). Curso 25 mm e η 0,5 são PRESSUPOSTO, como nos
  patins de ponta. O deslize parte de V_TD = 1,15 V_S (Raymer Sec. 17.9) e dá V²/(2 μ g) sem sustentação. O μ
  não tem omissão: sem ele, a distância fica não avaliada. A abrasão não é avaliada, porque não há dados de
  desgaste; só se reportam o trabalho de atrito e a pressão de contacto quando é dada a área. A folga da hélice
  mede-se acima da linha do ventre, pelo ponto mais baixo da estrutura sem trem, às atitudes 0/5/10°
  (PRESSUPOSTO, `attitudes_deg`). O 14 CFR 23.925 não se aplica.

Exemplo sem deriva, com o bloco acrescentado só no teste (o yaml do exemplo não muda): W0 150,4 kg, S 3,17 m²,
CLmax equilibrado 1,125 e V_S 26,0 m/s.
* Catapulta a 8 g e 10° de rampa: V_fim 28,6 m/s, curso **5,21 m**, 0,36 s, energia 62,9 kJ, força no shuttle
  12,1 kN sem a massa do shuttle e potência de pico 345 kW. Curso e g ficam não avaliados, porque faltam os
  limites do lançador, da célula e da carga útil.
* Ventre: descida 2,37 m/s (23.473(d)) e **n ≈ 23,6** com 25 mm de curso (34,7 kN), não avaliado sem o limite da
  célula. Com μ 0,5 (dado no teste), o deslize é ≥ 91 m. A hélice propulsora fica **0,13 m abaixo** da linha do
  ventre a 0° e 0,23 m a 10°, por isso `lr:belly_prop_clearance` dá False. As opções reportadas são parar e
  alinhar a hélice, usar uma hélice dobrável ou subir o disco ou o patim.

Testes: `tests/test_launch_recovery.py` (L = V²/(2a), força, energia, vento, limites None; Currey/23.473 e
deslize; omissão None; exemplo com AVL).

Em aberto: limites de g da célula e da carga útil e o curso do lançador são dados que faltam; a afundada e a
cabragem depois da largada não são avaliadas; o curso do patim de ventre é PRESSUPOSTO (n 23,6 indica que é
curto); o μ de deslize e o desgaste não têm fonte.

### Arrasto do trem no polar e opções da corrida com vento cruzado (16 nov 2026, ramo `l1-trem-ventocruzado`)

**A. Área de arrasto do trem no polar** (`aero/gear_drag.py`, genérico, opt-in). O trem entra no C_D0 como termo
(D/q)_misc da soma por componentes (Raymer 2018 Eq. 12.24). A área continua a ser um dado
(`aero.extra_drag_areas_m2`); nenhum valor de tabela é inventado.

* Trem fixo: a área dada (`fixed_gear`) já entrava sempre no polar (cruzeiro, subida, descolagem, aterragem) e
  continua a entrar. O que faltava era a área **escalada** com o comprimento das pernas (`gear_devices`, só
  reportada). `gear.apply_scaled_drag: true` no bloco do trem da montagem (ou `aero.gear_drag.scale_with_legs`
  sem montagem) soma a diferença como `fixed_gear_length_increment`. A chave dada não muda, por isso o relatório
  `asm:gear_drag_area` escala o mesmo número. Sem comprimentos das pernas nada é somado e a linha fica
  unassessed (desconhecido ≠ factor 1).
* Trem retráctil: `aero.gear_drag.retractable: true` tira as chaves do trem do polar de cruzeiro e soma
  ΔC_D0 = Σ(D/q)/S só nas configurações com trem em baixo (corrida de descolagem e aterragem, transição), por cima
  de `dCD0_takeoff` (Raymer 2018 Sec. 17.8). PRESSUPOSTO declarado: `dCD0_takeoff` passa a ter só os flaps.
  Consumidores: restrição de corrida do laço W0, `PerfModel` (descolagem/aterragem integradas, massa pontual) e
  MDO (ΔC_D0 na S da base, PRESSUPOSTO).
* Linha nova `aero:gear_drag` e `res.gear_drag`. Sem as opções nada muda.

Exemplo sem deriva (Linux): 0,03 m² × 1,72 = 0,0516 m², **+0,0216 m²**. Na S da base (3,161 m²) é
**ΔC_D0 +0,00683** (C_D0 0,02726 → 0,03409). Com a aeronave fixa:

| | sem trem escalado | com trem escalado |
|---|---|---|
| corrida de descolagem Raymer 17.8 (integrada) | 226,9 m | 231,9 m |
| descolagem até 15 m | 455,3 m | 485,4 m |
| corrida de aterragem Raymer 17.9 | 239,9 m | 237,5 m |
| fly-off massa pontual (`gear:takeoff_rotation`) | 291,0 m | 299,3 m |
| 6-DOF ar calmo | 296,2 m | **305,2 m** |
| 6-DOF vento cruzado 5,2 m/s | 325,1 m | 334,1 m |

Redimensionado com a opção ligada: W0 149,7 → **161,7 kg**, S 3,161 → 3,430 m², C_D0 0,02726 → 0,03259
(+0,00630 na S nova), potência 12,9 → 14,9 kW. Corridas: Raymer 210,4 m, aterragem 238,3 m, fly-off a
1,14 V_S, 6-DOF com vento cruzado **299,4 m**, aterragem 6-DOF 243,1 m. **Não ligado no exemplo**: escalar a
área inteira com ΣL (rodas incluídas) é um limite superior PRESSUPOSTO e o redimensionamento muda a aeronave.
Fica para decisão do João.

**B. Opções para a corrida de descolagem com vento cruzado** (`flightsim/takeoff_options.py`, genérico). Corre na
missão 6-DOF quando a corrida passa o requisito `takeoff_ground_roll` (ou sempre com
`mission.takeoff_options: true`; `false` desliga). Não altera a aeronave. A corrida de massa pontual integra o
balanço de forças de Raymer 2018 Sec. 17.8 com as forças do modelo de voo (μ 0,04 Raymer Table 17.1; fly-off à
atitude da perna do nariz, Sadraey 2012 Sec. 9.6.2; rotação com V_LOF = 1,1 V_S). Vento: forças na velocidade do
ar, distância na velocidade em relação ao solo (PRESSUPOSTO de método). Transferência para o 6-DOF: k =
S_6DOF/S_massa_pontual no vento da missão, constante entre opções (PRESSUPOSTO). O vento de frente e a tração são
re-voados no 6-DOF (só a descolagem), com k corrigido até fechar (≤ 4 voos), e o veredicto passa a ser o do
6-DOF. Saída: `mission['takeoff_options']`, `takeoff_options.md` na pasta da missão e uma linha na CLI.

Exemplo (Linux, aeronave do exemplo sem alterações; `examples/output/uav150_flying_wing_tailless_takeoff/`):
6-DOF 325,1 m com vento cruzado, 296,2 m em ar calmo (penalização 28,9 m), massa pontual 291,0 m, k 1,117.

| Opção | O que é preciso | Corrida [m] | Fecha |
|---|---|---|---|
| a. vento de frente / rumo da pista | ≥ 1,35 m/s no 6-DOF (vento a ≤ 75° da pista, cruzado restante 5,0 m/s) | 6-DOF 301,5 → 300,1 → 299,4 | sim (operacional) |
| b. tração | ×1,066 no 6-DOF (×1,060 massa pontual) | 6-DOF 302,2 → 299,8 | sim (massa do motor não iterada) |
| c. carga alar | S ×1,079 | 299,9 (estimada) | sim (massa da asa não iterada) |
| d. massa | −4,9 kg | 299,9 (estimada) | sim (combustível/carga útil) |
| e. atitude θ_g | nenhuma: mínimo 322,4 m a 19,5° (C_D sobe com θ; perda a ≈ 23,4°) | — | não |
| f. catapulta | bloco `launch_recovery.catapult` ausente no exemplo | — | unassessed (com o bloco do PR #67, 8 g: curso 5,21 m, V_fim atingida) |
| g. menos vento cruzado demonstrado | abaixo de 0,2 V_S0 falha 14 CFR 23.233(a) | ar calmo 296,2 | não admissível |

Nenhuma opção foi aplicada ao exemplo. O requisito de 300 m e o vento de 0,2 V_S0 não foram relaxados.

Testes: `tests/test_gear_drag_takeoff_options.py` (opção ausente, escala aplicada uma vez, sem pernas →
unassessed, retráctil só em baixo, bloco da asa voadora, exemplo rápido de tipo fixo com `PerfModel`;
componentes do vento, tendências da corrida, tabela que fecha com os números que reporta) e o teste do exemplo
sem deriva (estrutura da tabela quando a corrida 6-DOF passa os 300 m).

Em aberto: separar a área do trem em rodas e pernas (só a perna escala com o comprimento); massa do mecanismo de
retração; ΔC_D0 do trem retráctil em baixo no modelo 6-DOF (o 6-DOF usa o C_D0 de cruzeiro); as opções c/d não são
re-voadas no 6-DOF; potência/massa das opções b/c não entram num novo ciclo W0; limites do lançador para a
catapulta.

### CI Linux + Windows, mypy gradual e cobertura (16 nov 2026, ramo `eng-ci`, PR #71)

Pormenor completo em [QUALIDADE.md](QUALIDADE.md).

* `.github/workflows/ci.yml`: testes em `ubuntu-latest` e `windows-latest` (Python 3.13) com AVL instalado e
  cobertura; job `mypy` obrigatório. Uma corrida no Linux leva ~42 min (4 vCPU, com cobertura).
* `tests/conftest.py`: marcadores `requires_avl`, `requires_xfoil`, `requires_jsbsim`, tabela de saltos por motivo e
  `ACDT_REQUIRE_TOOLS`. Os `needs_avl`/`skipif(which("avl"))` dispersos passaram a usar o marcador. 23 testes que
  chamavam o AVL sem o declarar (fixtures do modelo de voo, C172, asa voadora) falhavam sem AVL e agora saltam.
  `test_assembly_p1b_leftovers.py` deixou de correr o AVL na recolha dos testes.
* mypy estrito em `core/atmosphere`, `core/units`, `core/requirements`, `aero/gear_drag` (anotações acrescentadas em
  `requirements` e `gear_drag`, sem mudança de comportamento).
* Cobertura de base 82 % (Linux CI).

Em aberto: XFOIL/Gmsh/CalculiX na CI; limiar de cobertura; alargar o mypy (plano em QUALIDADE.md).

### Proveniência dos resultados (16 nov 2026, ramo `eng-proveniencia`)

Pormenor em [QUALIDADE.md](QUALIDADE.md) §6 e CAPABILITIES §32i.

* `acdt/core/provenance.py` (mypy estrito): registo `acdt.provenance/1` — commit/árvore suja (+ hash do diff),
  Python e bibliotecas, SO, identidade (SHA-256) de cada executável usado, hash canónico das entradas, sementes,
  UTC + Europe/Lisbon, comando; manifesto da pasta de saída.
* Ligado em `cli.main` (âmbito por subcomando; `-o` pasta → `provenance.json`, ficheiro → `x.provenance.json`),
  `run_pipeline(output=…)`, `run_hifi`, `hifi.tools.run`, `ai/registry.py` (`run.json["provenance"]`). `tool_used`
  junto de cada `subprocess` do AVL (5 sítios), XFOIL, JSBSim e CadQuery.
* `acdt provenance show|capture|diff`. O `diff` foi pensado para o caso AVL Windows vs Linux: diz «binário de avl
  diferente» e «SO diferente» em vez de deixar a diferença de CL no 3.º algarismo por explicar.
* Nenhum número mudou; os testes (`tests/test_provenance.py`) verificam estrutura e usam binários falsos.

Em aberto: `hifi/wing_bl.py` e `hifi/cfd.py` não foram tocados (ramos do Build em curso); os JSON em
`examples/output` só ganham registo quando forem regenerados.

### Requisitos rastreáveis e matriz de verificação (16 nov 2026, ramo `eng-requisitos`)

Pormenor em [REQUISITOS.md](REQUISITOS.md) e CAPABILITIES §32j.

* `acdt/core/verification.py` (mypy estrito): `TracedRequirement`, registo de avaliadores (exatos ou por prefixo),
  `classify` (regra única dos 5 estados), `evaluate` (agregação pai/filhos), `coverage`, `check_tree`,
  `provenance_fingerprint`, escrita JSON/MD/CSV.
* `core/requirements.py`: `TRACE_KEYS` aceites em cada entrada de requisito → `Requirement.trace` (o dimensionamento
  não os lê). `MissionSpec.verification` guarda a secção `verification:`.
* `domains/aircraft/verification_evaluators.py` + `verification_run.py`: avaliadores `check:`, `perf:`,
  `sizing:stall_speed`, `entrada:` e omissões; etapa `verification` no fim do pipeline (nunca parte o pipeline:
  um erro fica como aviso); `acdt verify`.
* Exemplos C172 e asa voadora sem deriva com IDs; testes em `tests/test_verification.py` e `test_cli_uav`.

Em aberto: ligar as saídas de simulate/certify/integration (6-DOF, SORA, FOV); avaliadores para as chaves sem
omissão; requisitos com incerteza; histórico por ID entre corridas.

### Incerteza e sensibilidade (16 nov 2026, ramo `eng-incerteza`)

Pormenor em [INCERTEZA.md](INCERTEZA.md) e CAPABILITIES §32k.

* `acdt/core/sensitivity/{distributions,stats,gsa,study,surrogate}.py` (mypy estrito): entradas incertas com origem
  obrigatória ou PRESSUPOSTO (normal, lognormal, uniforme, triangular, intervalo epistémico), LHS/MC com correlações
  de postos (Iman & Conover 1982), percentis com IC, convergência, Sobol' (Saltelli 2010 / Jansen 1999) e Morris
  (Campolongo 2007), substituto quadrático aceite só com Q² (PRESS) ≥ limiar.
* `domains/aircraft/uq_run.py` + `acdt uq`: o pipeline L0/L1 como modelo; fatores de calibração de alta fidelidade
  entram com o seu GCI (registos H1 `nao_aplicar` nunca entram); P(passa) por requisito com IC de Wilson e estado
  probabilístico na matriz de verificação, sem mudar o estado determinístico.
* `acdt sensitivity` e o gate N1 (`--uq`) ficam como estavam. Testes analíticos (Ishigami, Morris linear, Wilson)
  em `tests/test_uq.py`.

Em aberto: modelo por amostra sem simulate/certify/integration (6-DOF, SORA e FOV continuam `nao_avaliado`);
Sobol' ignora correlações; intervalos só nos extremos.

Correções de 17 nov (ramo `eng-uq-fixes`): treino do substituto inclui os extremos dos intervalos (os «100 % fora da
caixa» eram artefacto) e a extrapolação sai por entrada; P(no_limite)/P(falha) com IC também com intervalos e
estado novo `prob_no_limite`; Sobol' com saídas centradas (Sobol' 2001; sem isso ΣS1 > 1 e S1 > ST quando
|média|/σ ≫ 1) e verificação de consistência. Resultados do exemplo sem deriva em INCERTEZA.md.

### MDO global de sistema (16 nov 2026, ramo `eng-mdo`)

Pormenor em [MDO.md](MDO.md) e CAPABILITIES §32l.

* `acdt/core/sysmdo/` (mypy estrito): `spec` (YAML → `MDOSpec`), `evaluate` (avaliador com cache e lotes, restrições
  do registo de requisitos, arquivo de todas as avaliações com o estado da matriz), `om_problem` (componente
  OpenMDAO do sistema, FD em lote, `NSGA2Driver`), `run` (SLSQP, ε-restrição, NSGA-II, GA, DOE; ciclo exterior
  discreto; fecho por iteração), `robust` (média + k·σ e P(passa) no substituto de `acdt uq`), `pareto`, `expr`,
  `report`, `toy` (Sellar, ZDT1, modelo de função).
* `domains/aircraft/mdo_system.py` + `acdt mdo`: o modelo é o `AircraftModel` de `acdt uq` com `with_overrides`
  (valores discretos, blocos YAML). `uq_run.run_point` passa agora o limiar e a tolerância de cada requisito na
  amostra (para requisitos que são variáveis de projeto).
* Exemplos: `examples/mdo/uav150_tailless_mdo.yaml` (MTOW × autonomia) e
  `examples/mdo/uav150_fleet_propulsion_closure.yaml` (propulsão exterior + fecho da frota, ciclo de Ha 2010).
* Achado: na asa voadora com montagem e reescala `uniform`, `assumptions.aero.AR` não muda o projeto (o AR é o do
  desenho); o estudo usa `fixed: {assumptions.assembly.options.scaling: surfaces}` e a variável
  `assumptions.assembly.options.AR`. O `acdt mdo` avisa quando um objetivo não muda entre projetos.
* `acdt optimize` e `core/mdo.py` ficam como estavam.

Resultado do exemplo (`acdt mdo ... --spec examples/mdo/uav150_tailless_mdo.yaml -o /workspace/mdo_tailless`, 16–17
nov 2026): NSGA-II, 12 avaliações (0 falhadas, 12 viáveis), frente com 8 projetos; joelho AR 13,74,
`requirements.endurance` 12,87 h, `requirements.stall_speed` 27,29 m/s → W0 163,94 kg, autonomia 13,26 h (relaxa a
perda de 26 para 27,29 m/s: é variável de troca). Pormenor em MDO.md («Exemplo de teste»).

Em aberto: derivadas analíticas/complex-step do pipeline; MDO de sistema com a fidelidade L1 completa (no PC);
fecho de frota com disponibilidade e várias estações (só o ciclo de Ha 2010 por expressão); `pymoo` não instalado.

### Biblioteca de V&V (17 nov 2026, ramo `eng-vv`)

Pormenor em [VV.md](VV.md) e CAPABILITIES §32m.

* `acdt/core/vv.py` (mypy estrito): `Reference`, `Case`, registo com validação (citação e tolerância
  obrigatórias), `run_case` (passa/falha/nao_avaliado/desconhecido; ferramenta em falta e `NotAssessed` →
  nao_avaliado; exceção → desconhecido), filtro de custo, relatório `acdt.vv/1` com versão, impressão digital SHA-256
  das definições e proveniência; `acdt vv`.
* Casos em `acdt/core/vv_cases.py` (ISA, Ishigami, Sellar, ZDT1, consola/placa/SP-8007, PO) e
  `acdt/domains/aircraft/vv_cases.py` (linha sustentadora elíptica, 23.337, C172S). 22 casos, todos passam.
* CI: job `vv` com os casos baratos; `tests/test_vv.py`.

Em aberto: casos XFOIL/AVL e desempenho C172 contra o POH precisam dos valores publicados transcritos com
página/tabela (Abbott & von Doenhoff App. IV; POH 172S Secção 5); validação RCS contra medições; dados de ensaio
(túnel/voo/banco).

### Publicação (18 nov 2026, ramo `publicacao`)

O acdt passou a open-source (Apache-2.0) e o desenvolvimento continua no repositório público `joaovpfrazao/acdt`.

* `LICENSE` (texto integral Apache-2.0), `NOTICE`, `pyproject.toml` (`Apache-2.0`, classificador OSI); cabeçalhos
  `SPDX-License-Identifier: Apache-2.0`. Mantém-se a regra: nada GPL/LGPL no processo.
* Removida a cópia local do relatório NASA NAG-1-2195 (Bao 2002); a citação aponta para o NTRS 20020065232.
* We/W0 inicial: removidas as classes fixas não publicadas. `uav_gasoline` e `uav_small_electric` ficam como
  aliases de Raymer Tab. 3.1 (`uav_tactical_recce_ucav`, `uav_small`); `FIXED_EMPTY_FRACTION` vem vazio e serve
  para estatística própria (`fixed_fraction` ou regressão do utilizador, PRESSUPOSTO com fonte). Os exemplos UAV
  passaram a usar as classes de Raymer e as saídas em `examples/output` foram regeneradas.
* Do estudo Nansei só fica o benchmark (`examples/benchmarks/nansei_jcg/`).

### Estado de projeto único com unidades (18 nov 2026, ramo `eng-dados`)

Pormenor em [DADOS.md](DADOS.md) e CAPABILITIES §32n.

* `acdt/core/quantities.py` (mypy estrito): unidades na fronteira com pint (dependência nova, BSD-3-Clause,
  carregada só quando aparece uma unidade fora da tabela exata). Inclui `to_unit`, `to_dimension_si`, `convert`,
  `unit_from_key` (tabela `SUFFIX_UNITS`) e `normalise_tree`. O erro é `QuantityError`, subclasse de
  `UnitError`/`ValueError`.
* Ligado em `MissionSpec.from_dict` (`assumptions`, `systems`, `onboard`), em `parse_requirement` (valores e
  qualificadores em texto) e em `verification.from_dict` (limiar e objetivo em texto). O `acdt size` sai com código
  2 numa unidade inválida.
* `acdt/core/design_db.py` (mypy estrito), esquema `acdt.design/1`:
  * `new`, `quantity`, `quantities_from_tree`, `set_results`, `set_uncertainty`, `attach_uq`,
    `set_verification`;
  * `save`/`load`, que validam com jsonschema quando está instalado (agora no extra `dev`) e, sem ele, com
    verificações essenciais;
  * `flatten`, `query`, `get_value`, `diff`/`explain_diff`, `to_csv`/`to_markdown`/`summary`.
* `acdt/domains/aircraft/design_db_run.py`:
  * `SECTION_MAP` (secção → disciplina, nível e método, com a secção de CAPABILITIES);
  * a etapa `design_db` no fim do pipeline, que nunca o parte e, em caso de erro, deixa um aviso;
  * `build_from_output` e `uq_into_db` (`UQ_METRIC_MAP`). O `uq.json` passa a guardar `model.result_metrics`.
* `acdt verify` atualiza a secção `verification` do `design.json` da pasta.
* Testes: `tests/test_design_db.py` cobre unidades, erros de dimensão, ida e volta, esquema, consulta, diff,
  incerteza, export, compatibilidade dos exemplos e o pipeline com a CLI (marcado `slow`).

Em aberto, por ordem:
1. `acdt mdo`: o ótimo e o Pareto como blocos L2.
2. `acdt vv`.
3. Blocos L3 das ferramentas de alta fidelidade.
4. Mapa de unidades para as chaves de resultado sem sufixo. No exemplo GA, 130 das 377 grandezas numéricas têm
   unidade declarada.
5. Unidades em texto nas specs de `mdo`/`uq`.

### Dados de ensaio e calibração (18 nov 2026, ramo `eng-calibracao`)

Pormenor em [CALIBRACAO.md](CALIBRACAO.md) e CAPABILITIES §32o.

* `acdt/core/calibration/` (mypy estrito), domínio-agnóstico:
  * `ingest.py` (`acdt.testdata/1`):
    * `load` (CSV/Parquet/ULog + `<dados>.meta.yaml`) e `from_arrays`;
    * `Channel.to`/`sd_to`, com conversão afim pint;
    * `standard_uncertainty` (GUM: `sd`, `half_width`, `resolution`, `rel`);
    * o `.bin` do ArduPilot é recusado com a indicação de converter fora do processo.
  * `fitting.py`:
    * `ModelSpec`/`Parameter` sobre uma expressão vetorial segura (sem `eval`);
    * `fit` → `FitResult`, com dois métodos: `wls` (variância efetiva, Birge, ν < 1 → covariância `None`) e
      `koh` (MAP + Laplace, prior obrigatório).
  * `record.py` (`acdt.calib/1`):
    * `decide` (critérios em `CRITERIA`; sem critérios → `nao_aplicar`), `build_record` e `applicable_at` (todas
      as entradas da gama são obrigatórias);
    * exportações: `factors_file`, `overlay`, `uq_inputs` (ρ de Pearson → postos) e `to_design_db`;
    * `run_study`, `to_markdown` e `residuals_csv`.
* Alterações fora do pacote:
  * `hifi/calibration.factor_acceptable` também recusa `decision: nao_aplicar`;
  * `uq_run.calibration_inputs` aceita fatores de ensaio (`fidelity: ensaio` ou `calibration`) como N(valor, σ);
  * `design_db.set_results(..., fidelity=)`, com `FIDELITIES = ("modelo", "ensaio")`, campo opcional no esquema
    e herdado por `flatten`.
* CLI `acdt calib`. Novo extra `[dados]` (pandas, pyarrow, pyulog); THIRD_PARTY atualizado.
* Exemplos SINTÉTICOS em `examples/calibration/` (`gerar_sintetico.py`, polar de túnel e flexão estática).
* Testes: `tests/test_calibration.py` (17).

Em aberto, por ordem:
1. Ligar uma função do pipeline como η(x, θ). Hoje a previsão do modelo entra como canal.
2. ULog: alinhar tópicos e detetar segmentos estabilizados (ensaio de desempenho em voo).
3. KOH completo: MCMC, ℓ por entrada e emulador PG do modelo.
4. Dados de ensaio reais (túnel, voo ou estático) com relatório e incerteza. Sem eles, nenhum fator de ensaio é
   aplicado a um projeto.

### API pública, documentação, CLI e notebooks (18 nov 2026, ramo `eng-api`)

Pormenor em [API.md](API.md) e CAPABILITIES §32p.

* `acdt/api/` (mypy estrito):
  * `__init__.py`: superfície pública (`__all__`), `API_VERSION = "1.0.0"`, funções finas sobre `run_pipeline`,
    `verification_run`, `uq_run`/`sensitivity.study`, `mdo_system`/`sysmdo.run`, `vv`, `calibration`,
    `design_db` (importações tardias: `import acdt.api` é leve);
  * `_deprecation.py`: `deprecated`, `ACDTDeprecationWarning`, registo `DEPRECATED`;
  * `stability.py` + `api_surface.json`: `surface`, `check` (regras SemVer), `python -m acdt.api.stability
    [--write]`.
* `acdt/cli.py`: `build_parser()` separado de `main()`; `EXIT_CODES`; `--json`/`--debug` acrescentados a todos os
  subcomandos que não os tinham (`db` e `provenance` mantêm o `--json` próprio); `_emit(...)` preenche o `result`
  do envelope em `size`, `verify`, `uq`, `mdo`, `vv`, `calib fit`; exceções não tratadas → código 4.
* Versão do pacote 0.2.0 (`pyproject.toml` e `acdt.__version__`, verificado por teste).
* Documentação: `mkdocs.yml`, `docs/index.md`, `docs/API.md`, `docs/referencia/{api,cli}.md`, hook
  `docs/hooks/cli_ref.py`; extras `[docs]` e `[notebooks]`; `site/` no `.gitignore`.
* CI: jobs `docs` e `notebooks` em `ci.yml`; `docs-pages.yml` só publica com `workflow_dispatch` ou com a
  variável `PAGES_ENABLED = "true"` (e o Pages ativado em Settings → Pages → GitHub Actions).
* Testes: `tests/test_api.py` (10), `tests/test_cli_contract.py` (7), `tests/test_notebooks.py` (4).

Em aberto, por ordem:
1. Alargar `acdt.api` (sistemas, fabrico/custo, certificação, simulação) — cada acréscimo sobe a MENOR e regenera
   `api_surface.json`.
2. `result` estruturado no `--json` dos restantes comandos.
3. Ativar o GitHub Pages (decisão do João) e, quando houver API 2.x, documentação por versão.

### Relatórios automáticos de revisão SRR/PDR/CDR (18 nov 2026, ramo `eng-relatorios`)

Pormenor em [RELATORIOS.md](RELATORIOS.md) e CAPABILITIES §32q.

* `acdt/core/review/` (mypy estrito):
  * `criteria.py`: critérios SRR/PDR/CDR de NPR 7123.1D Ap. G (Tabelas G-4, G-6, G-7) como dados, com
    excertos literais conferidos no NODIS, avaliador ou `None` (revisão humana) e interpretação;
    `DEFAULT_REQUIRED_LEVEL` (PRESSUPOSTO SRR L0, PDR L1, CDR L2);
  * `bundle.py`: recolhe `design.json`, `verification_matrix.json`, `provenance.json`, `result.json` e os
    registos `uq.json`/`mdo.json`/`vv_report.json`/`calibration_record.json` (descoberta até 3 níveis, mais os
    dados explicitamente), figuras PNG e SHA-256 registados;
  * `profile.py`: `ReviewProfile`/`register_profile` (o aircraft regista-se em
    `domains/aircraft/review_profile.py`);
  * `evaluate.py`: 14 avaliadores e `verdict()` (`nao_pronto` > `insuficiente` > `pronto`);
  * `build.py`: relatório `acdt.review/1` (requisitos, resumo, fidelidade, itens em aberto, UQ, MDO, V&V,
    calibração, rastreabilidade, figuras), ficheiro de critérios (`waivers`/`tailoring` com justificação);
  * `render.py`: blocos → Markdown e HTML autónomo (figuras base64); PDF só com WeasyPrint instalado.
* CLI `acdt report` (códigos 0/1/3/2; a saída não pode ser a pasta do `design.json`); API `acdt.api.report`
  (API_VERSION 1.1.0, `api_surface.json` regenerado; `errors()` inclui `ReviewInputError`).
* Testes: `tests/test_review.py` (17), exemplo `tests/data/review_small/` gerado por `gerar.py` (normalizado;
  `.gitattributes` `-text` para os SHA-256 não mudarem no Windows) e `relatorio_pdr.golden.md`. Se o formato do
  relatório mudar de propósito, regenerar com `python tests/data/review_small/gerar.py` e rever o diff do golden.

Em aberto, por ordem:
1. Gerar figuras em falta (Pareto, histogramas UQ) a partir dos registos.
2. Critérios das revisões MDR/SDR, TRR e PRR (Tabelas G-5, G-10, G-8).
3. Registo de decisões (`acdt decisions`) como evidência dos estudos de compromisso; `acdt certify` nos critérios
   de segurança; ficha RID/RFA.

### Ruído acústico L0 (18 nov 2026, ramo `disc-ruido`)

Primeiro item das «disciplinas em falta». Núcleo `acdt/core/acoustics/` (Gutin, Schlegel-King-Mull, ISO 9613-1,
IEC 61672-1, ISO 226, 14 CFR 36 Ap. G), etapa `noise` do pipeline (`domains/aircraft/noise.py`), disciplina `ruido`
no `design.json`, requisitos `noise` e `aural_detection_range`, avaliador `ruido:`, `acdt.api.rotor_noise` (API
1.2.0) e quatro casos V&V (todos passam). Doc: [RUIDO.md](RUIDO.md); CAPABILITIES §32r.

* **Regra de completude**: só tons de carga e banda larga de vórtices. Sem `noise.other_sources` declarado, o nível
  é um limite inferior: falha se já excede, desconhecido se cumpre (nunca passa). Idem para a Parte 36.
* **Exemplo (teste, `examples/cessna172_check.yaml`, sem alterar o projeto)**: sobrevoo a 2438 m e 62,8 m/s,
  2700 rpm: L_A,max 46,2 dB(A), L_AE 60,4 dB(A), alcance de deteção em silêncio 27,5 km no solo (tom fundamental
  de 90 Hz; limite superior sem refração nem atenuação do solo). M_tip helicoidal 0,85 > 0,8: aviso de validade
  (espessura não modelada). Parte 36 Ap. G (com `certification.part36_G`): MTOW 1138 kg → limite 80,7 dB(A)
  (G36.301(c)); altura de referência 204 m; L_A,max 70,8 dB(A) — limite inferior, por isso «desconhecido».
* **Seguimentos**: validação contra medições publicadas; espessura (Deming) e voo (Garrick & Watkins); ruído de
  motor; Fidell et al. (1974) depois de consultar o original; ICAO Anexo 16 Cap. 10; ligação ao `acdt vtol`.

### Gestão térmica L0/L1 (18 nov 2026, ramo `disc-termica`, PR #16)

Segundo item das «disciplinas em falta». Núcleo `acdt/core/thermal/` (ar USSA 1976, MIL-HDBK-310, correlações de
Incropera, conduto NACA RM A8I29, fontes de calor), etapa `thermal` do pipeline (`domains/aircraft/thermal.py`),
disciplina `termica` no `design.json`, requisitos `thermal_margin`, `cold_thermal_margin` e `cooling_drag_area`,
avaliador `termica:`, `acdt.api.thermal`/`thermal_atmosphere` (API 1.3.0) e seis casos V&V (todos passam). Doc:
[TERMICA.md](TERMICA.md); CAPABILITIES §32s.

* **Regra de completude**: fontes e temperaturas em intervalo; fonte sem majorante → margem a quente nunca passa;
  ε/α não declarados valem [0, 1] (resultados largos: declarar a tinta); limites por enumeração dos vértices.
* **Exemplo (teste, `examples/uav_endurance_payload.yaml` com um compartimento declarado, sem alterar o projeto)**:
  η_ESC 0,97 e η_motor 0,90 declarados; cruzeiro quente (MIL-HDBK-310 1 %, 1120 W/m²) 102 W no compartimento,
  entrada NACA dimensionada 7,1 cm², arrasto 0,096 N (ΔC_D0 2,8×10⁻⁴), conduto 0,038 kg. Compartimento 50–52 °C
  em cruzeiro, 64–70 °C na subida e no solo ao sol; pacote a 60 °C máx. → margem a quente −28 a −23 K (falha: o
  conduto foi dimensionado para o cruzeiro, não para a subida). Dia frio com obturador fechado: −40 a −35 °C,
  margem a frio −14 a −9 K. `coupling: iterar`: W0 25,20 → 25,43 kg, converge em 3 iterações.
* **Seguimentos**: no ciclo `iterar` o ponto de funcionamento usa o ponto de projeto enquanto a tabela de missão
  não existe (área de arrasto da iteração ≈ 7 % abaixo da final); adaptadores VTOL/jato nativos; perdas do gerador
  híbrido (`onboard`); potência de ventilador acoplada em motores térmicos; efeito Meredith e arrasto externo da
  entrada; capacidade térmica por componente; permutadores líquidos; irradiância em altitude; Bernardi (baterias).

### Gelo L0/L1 (18 nov 2026, ramo `disc-gelo`, PR #17)

Terceiro item das «disciplinas em falta». Núcleo `acdt/core/icing/` (propriedades, captação, Messinger, envelopes
do Ap. C, proteção, penalização, estudo genérico), etapa `icing` do pipeline (`domains/aircraft/icing.py`),
disciplina `gelo` no `design.json`, requisitos `ice_protection_power`, `max_ice_thickness` e
`flight_into_known_icing`, avaliador `gelo:`, `acdt.api.icing`/`icing_envelope` (API 1.4.0) e quatro casos V&V
(todos passam). Doc: [GELO.md](GELO.md); CAPABILITIES §32t.

* **Regra de completude**: espessura `lo` só com exposição padrão e condições dentro do envelope, `hi` com a
  condição inteira, β₀/0,953 e ρ_i −10 %; FIKI nunca passa por análise; botas, gelo residual e ΔC_D0 desconhecidos.
* **Exemplo (teste, `examples/uav_endurance_payload.yaml` sem alterar o projeto)**: superfícies por omissão sem
  proteção; exposição 28–163 min (subida, espera, descida); espessura máxima 14,1–57,2 mm no estabilizador
  horizontal (d = 5,4 mm); asa 11,3–45,4 mm; C_L,max com gelo 0,28–0,69 do limpo (Broeren, PRESSUPOSTO). Com degelo
  eletrotérmico declarado na asa (0,2 m², ciclo 0,1, 10 kW/m², 0,3 kg) e `coupling: iterar`: 251 W no balanço,
  W0 25,20 → 34,31 kg, converge em 2 iterações.
* **Achados**: a Tabela 3 de Jeck (intermitente −30 °C/35 µm, 0,398) não bate com a Tabela 1 (0,350/1,100 = 0,318);
  o power budget em malha fechada substitui `systems_power_W`, pelo que a proteção entra também como carga
  `systems.loads` (a mesma lacuna da térmica foi corrigida no ramo `fix-acoplamento-termico`).
* **Seguimentos**: Ap. O (SLD); β local e gelo de retorno/intercíclico; geometria a evoluir com a acreção;
  penalização por tipo de gelo e ΔC_D0; ar sangrado e botas; encontros mistos; adaptadores VTOL/jato nativos; validação contra formas de gelo medidas (NASA IRT).

### Acoplamento térmico no balanço em malha fechada (18 nov 2026, ramo `fix-acoplamento-termico`)

* **Erro corrigido**: com bloco `systems` (power budget em malha fechada, `run_with_systems`) o `systems_power_W`
  é substituído pela média do balanço, pelo que a potência do ventilador do modo `iterar` da térmica se perdia em
  silêncio. Agora entra também como carga `systems.loads` (ciclo 1, conservador), como já fazia o gelo. Helper
  comum `thermal.with_load` (substitui a carga com o mesmo nome; o gelo reutiliza-o). Teste de regressão: o W0
  sobe com a pressão do ventilador (10 → 2000 Pa, mesmo caudal).
* **Gelo**: a potência de proteção passa a contar só na fração da missão em segmentos dentro do envelope
  (`icing.power_schedule: exposicao`, omissão; pico inalterado); `missao` ou durações desconhecidas → ciclo 1.
  O resultado do exemplo de teste do PR #17 (W0 25,20 → 34,31 kg com ciclo 1) passa a ser mais baixo com a
  omissão; `power_schedule: missao` reproduz o majorante.

### Custo do ciclo de vida e CO₂e L0 (18 nov 2026, ramo `disc-ciclo-vida`)

Núcleo `acdt/core/lcc/` (`discount`: SPV/UPV/UPV*/taxas NIST HB 135; `lcc`: categorias OSD CAPE com calendário,
intervalos e `present_value`; `environment`: FCF ICAO, LC CORSIA, rede declarada, baterias IVL C 444) e etapa
`life_cycle` (`domains/aircraft/life_cycle.py`, depois de `series_cost`, só se pedida). Reutiliza o custo de série
(RDT&E, produção/aeronave, frota), o custo operacional da fiabilidade ou `costing.operating_cost` (sem depreciação)
e `reliability.mission_duration_h`. Disciplina `ciclo_vida`, quatro requisitos, avaliador `ciclo_vida:`, API 1.7.0,
quatro casos V&V (NIST HB 135 e CORSIA), todos a passar. Doc: [CICLO_VIDA.md](CICLO_VIDA.md); CAPABILITIES §32w.

* **Falta**: fabrico da estrutura e fim de vida na pegada, efeitos não-CO₂, fatores PV por item no calendário.

### Custo de produção em série L0 (18 nov 2026, ramo `disc-custo-serie`, PR #20)

Estudo `manufacturing/series.py` e etapa `series_cost` (`domains/aircraft/series_cost.py`, depois da fiabilidade, só
se pedida). Reutiliza `cost.py` (Eastlake), `costing.dapca4` e as curvas de `costing`, acrescentando
`learning_lot`, `wright_unit`, `lot_midpoint` e `learning_b`. `sizing.eastlake_inputs` foi extraído de
`unit_cost_estimate` sem mudar o resultado. Ficam também a disciplina `custo_serie` no `design.json` e os requisitos
`unit_cost_at_quantity`/`flyaway_cost` (qualificador novo `quantity` em `core/requirements.py`) e
`break_even_quantity`. A API sobe a 1.6.0 (`series_cost`, `learning_curve`) e há três casos V&V do FAA Pricing
Handbook Cap. 18, todos a passar. O avaliador genérico `eval_section_interval` serve as próximas disciplinas. Doc:
[CUSTO_SERIE.md](CUSTO_SERIE.md); CAPABILITIES §32v.

* **Falta**: T1 automático a partir do plano de fabrico, curvas com degraus, modelo de cadência com fonte.

### Fiabilidade e manutenção de frota L0 (18 nov 2026, ramo `disc-fiabilidade`, PR #19)

Núcleo `acdt/core/reliability/` (taxas com proveniência, RBD série/paralelo/k-de-n/caminhos, manutibilidade e
disponibilidades, sobressalentes Poisson, frota, estudo genérico), etapa `reliability` do pipeline
(`domains/aircraft/reliability.py`, depois do gelo), disciplina `fiabilidade` no `design.json`, requisitos
`mission_reliability`, `mtbcf`, `mtbf`, `operational_availability`, `maintenance_man_hours_per_fh` e `fleet_size`,
avaliador `fiabilidade:`, `acdt.api.reliability`/`availability`/`spares_stock` (API 1.5.0) e cinco casos V&V do
MIL-HDBK-338B (todos passam). Doc: [FIABILIDADE.md](FIABILIDADE.md); CAPABILITIES §32u.

* **Reutilização**: taxas de `core/data/failure_rates.yaml` e de fornecedor (`core/safety/rates.py`, as mesmas do
  ARP4761/SORA), `concept.reliability.k_of_n`, `concept.ops.availability`, `fleet_feedback.fleet` (Ha 2010) e o
  custo operacional de `manufacturing.costing` (o custo de manutenção/FH entra nesse módulo, não num novo).
* **Regra de completude**: taxa sem fonte → desconhecido (R = 0 no minorante, 1 no majorante; MTBF básica só com
  majorante); entradas `kind: assumption` da base só com `accept_assumptions: true`; MTTR em falta → disponibilidades
  desconhecidas; atrasos logísticos não declarados → A_o só com majorante; MMH ou custo de peças em falta → custo
  operacional `partial`/`unassessed`, nunca zero.
* **Ganchos**: `fleet_feedback.fleet` aceita `availability: {reliability: …}` (minorante de A_o; desconhecido →
  erro); `attach_operating_cost` do morfológico aceita `operating_cost.reliability`.
* **Exemplo (teste, `examples/uav_endurance_payload.yaml` sem alterar o projeto)**: com a FCC só da base (não
  aceite) R_missão [0; 0,9994]; com `accept_assumptions: true` R_missão 0,9975–0,9992 (2,73 h), MTBCF 632–918 h,
  MTBF básica 330–411 h, A_o 0,47–0,86 (atraso logístico 2–24 h), MMH/FH 0,042–0,043, frota 1–2 (2 surtidas/dia,
  turno de 12 h).
* **Achado**: o Exemplo 3 do §10.4.1.1 soma M_ct + M_pt em vez de ponderar pelas frequências; o código pondera e o
  caso V&V dá M̄ como o texto.
* **Seguimentos**: redundância em espera e reparação em missão; missões por fases e `duty` por segmento; Weibull e
  vida limitada; causa comum (β) e ligação à FTA; METRIC multi-escalão; abortos na cobertura.

### Teste instável de reutilização de `run_id` (18 nov 2026, PR #12)

Causa medida: falha transitória do AVL numa iteração intermédia do ciclo W0 → Schrenk só nessa iteração → ponto
fixo diferente (≤ `tol_lowfi`). Corrigido com repetição do AVL (180 s), aviso de mudança de fonte entre iterações e
reutilização do `result.json` em `size_fleet(run_id=…)`. Pormenor em [QUALIDADE.md](QUALIDADE.md) §4.

## Melhorias futuras em espera

Ver `docs/FUTURE_IMPROVEMENTS.md`: ideias registadas mas não aprovadas (forma defletida a 1g, laminados por componente e aeroelastic tailoring).

## Esteira do painel grosso, 255 iterações (19 nov 2026, ramo `vspaero-esteira-residual`)

Base `e9726e4`. O registo de cinco iterações em `h7_vspaero_painel.json` não foi reescrito. O default documentado da esteira continua WakeNumIter 5, NumWakeNodes 8, WakeRelax 1, FixedWakeFlag 0 e ImplicitWake 0. Esta corrida só pede WakeNumIter 255, o tecto do parâmetro em `VSPAEROMgr.cpp` do OpenVSP 3.56.0 (`Init` 5, 3, 255), lido de volta como 255. Os outros campos ficam no default.

O critério de paragem é o de `src/vsp_aero/Solver/VSP_Solver.C` dessa etiqueta: `log10(MaxResidual_) <= log10(0.001 * NonLinearConvergenceFactor_)`. O factor não é escrito pelo acdt. `wing.vspaero` leu 1,0, logo o limiar é −3. As colunas da história já são log10. O critério do GMRES não entra nesta decisão.

`vspaero.exe` noutro processo, código 0, 255 linhas, 56,6 s. No arranque havia 15,32 GB livres e o limite da guarda era 10,73 GB. O teto de 0,8 GB não mede esta malha. α 9,52057° do AVL de duas secções desta corrida. Iteração 255: CL 0,52875, CDi 0,024911, CDtot 0,039934, CMytot 0,035397, CDiw 0,019907, L2 −2,237, Max −1,182. O tecto esgotou-se e o Max continua acima de −3. O solver não declarou convergência.

AVL desta corrida: CL 0,50293, CDff 0,014536, Cmtot 0,02886. Razões CL 1,051 e Cm 1,227, mesmo sinal, dentro de [0,7, 1,5]. Não se propõe calibração, porque o residual não cumpre o critério. CDi/CDff informativo 1,714 fica fora da banda e é outra grandeza. Veredicto `nao_aplicar`. Calibração `nao_aplicar`. `valid` false, `applied` false, `example_yaml_edited` false. O yaml não muda. O AVL L1 não fica validado nem calibrado.

Números em `examples/output/uav150_flying_wing_tailless_hifi_win/h7_vspaero_esteira.json` e `examples/output/uav150_flying_wing_tailless_hifi_win/h7_vspaero_esteira.csv`.
