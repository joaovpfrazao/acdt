# Tutorial — Fase 5: estrutura interna da asa, FEM de cascas e otimização perfil ↔ longarinas ↔ desempenho

Continua o [tutorial da Fase 4](tutorial-fase4.md). A Fase 5 junta, ainda em **baixa fidelidade no ciclo**, a forma
da estrutura interna da asa (posição das longarinas, espessuras, passo das nervuras) com a escolha do perfil
(t/c, curvatura) e a torção, e mede o efeito no **peso** e no **desempenho** (alcance ou autonomia). O compromisso
que se procura é o clássico: perfil mais espesso → mais arrasto de perfil, mas caixão mais alto → menos massa
de revestimento/longarinas → menos peso (e, com MTOW fixo, mais combustível).

Regras: só métodos clássicos citados no código; nenhum número afinado; hipóteses marcadas `ASSUMPTION`.

## 0. Pré-requisitos

```bash
pip install -e ".[dev,aero,mdo,hifi,wingbox]"      # scipy, neuralfoil
pip install -e ".[fastfem]"                        # opcional: pypardiso (MKL) — só acelera o FEM
export PATH=/caminho/Xfoil/bin:/caminho/Avl/bin:$PATH   # o pipeline das Fases 2–3 usa XFOIL/AVL
```

## 1. Correr

```bash
acdt wingbox examples/cessna172_check.yaml -o examples/output/cessna172_check_wingbox --objective range
acdt wingbox examples/uav_endurance_payload.yaml -o examples/output/uav_endurance_payload_wingbox --objective endurance
```

Opções: `--objective weight|range|endurance|mtow`, `--tc 0.10,0.12,…` (varrimento de t/c de raiz),
`--maxiter`, `--no-fem`. Cada corrida demora 3–5 min numa máquina de 4 núcleos e grava:

| ficheiro | conteúdo |
|---|---|
| `<nome>_tc_sweep.png` | massa do caixão, C_D e alcance/autonomia ao longo do t/c (cada ponto otimizado) |
| `<nome>_layout.png` | espessuras, x/c das longarinas e do centro de corte, GJ/EI, cl local e carga ao longo da envergadura |
| `<nome>_structure3d_baseline.png`, `_optimum.png` | pré-visualização 3-D: pele semitransparente, almas (vermelho = dianteira, laranja = traseira), banzos, nervuras (verde), reforçadores (roxo) e dois cortes com o perfil, o caixão, a célula D e o centro de corte |
| `<nome>_wingbox.json` | variáveis, restrições, desempenho, varrimento, verificação FEM |

## 2. O que está por baixo

### 2.1 Secção real (Megson)
`wingbox/section.py` constrói a secção idealizada sobre o **contorno NACA de 4 dígitos** (Abbott & von Doenhoff)
entre as longarinas, com célula D opcional no bordo de ataque, e resolve-a com `core/thinwalled.py` (Megson,
*Aircraft Structures*, Caps. 16–19: centro de corte de secção multicelular, Bredt–Batho para GJ, EI com booms).
O eixo elástico, o momento de torção e GJ/EI usados na aeroelasticidade da Fase 3 vêm agora desta secção
(`structures.box_section_properties`; `assumptions.structures.elastic_axis: section`).

### 2.2 FEM de cascas próprio (`core/fem`)
Quadrilátero plano de 4 nós: membrana QM6 (Taylor, Beresford & Wilson 1976) + placa MITC4 (Bathe & Dvorkin 1985),
rigidez de rotação no plano pequena; vigas de Euler–Bernoulli com excentricidade; estática, encurvadura linear
(K + λ K_G) e modos (eigsh/ARPACK; solver direto pypardiso ou SciPy `splu`). Sanduíche como camada equivalente
com S = G_c d²/t_c (Allen 1969). `wingbox/fem.py` converte a malha CalculiX da Fase 4 (S8R → 4 × Q4, B32 → 2 vigas).

Verificação analítica (`tests/test_fem_core.py`, `tests/test_thinwalled.py`):

| caso | referência | desvio |
|---|---|---|
| placa em consola, flexão | PL³/3EI | −1,15 % |
| consola no plano (com corte) | Timoshenko | −0,95 % |
| placa SS, compressão k = 4 | Timoshenko & Gere | −0,27 % |
| placa SS, corte k_s = 9,34 | Timoshenko & Gere | +1,9 % |
| sanduíche SS (hard), N_E/(1+N_E/2S) | Allen 1969 | +0,7 % |
| 1.ª frequência da consola | Euler–Bernoulli | +0,64 % |
| caixão: taxa de torção | Bredt | +1,06 % |
| caixão: flexão | Euler–Bernoulli | +1,4 % |
| secções (centro de corte, J, I) | Megson, formas fechadas | exato a +0,02 % |

Comparação com CalculiX (mesma malha da Fase 4, cargas últimas):

| grandeza | C172: este FEM / ccx | UAV: este FEM / ccx |
|---|---|---|
| flecha na ponta | 0,3891 / 0,3869 m (+0,57 %) | 0,1558 / 0,1557 m (+0,11 %) |
| torção na ponta | 1,122 / 1,116° (+0,57 %) | 0,774 / 0,773° (+0,14 %) |
| σ_yy médio (revestimentos, reforçadores, banzos) | ±1,3 % (até −3 % nas baías da ponta, σ < 15 MPa) | banzos ±0,2 %; pele sanduíche: ver nota |
| 1.ª flexão | 6,60 / 6,63 Hz (−0,5 %) | 8,92 / 8,93 Hz (−0,1 %) |
| modos seguintes (2–6) | −0,5 a −4,6 % | −0,1 a −0,4 % |
| tempos (estática / encurvadura / modos) | 7 / 23 / 23 s | 2 / 33 / 7 s |

Notas:
* Pele sanduíche do UAV: o CalculiX reporta a média de σ_yy nos pontos de integração de todas as camadas
  (faces + núcleo) = ⅔ da tensão nas faces; 112 MPa × ⅔ = 74,8 MPa vs 74,5 MPa do ccx.
* **Encurvadura**: o UAV dá λ = 0,91 (este FEM, com corte do núcleo) vs 1,83 (ccx). Com o núcleo rígido ao
  corte este FEM dá 1,81 / 2,11 / 2,12 vs 1,83 / 2,13 / 2,19 do ccx: a diferença é a flexibilidade ao corte
  do núcleo, que o elemento S8R composto expandido do CalculiX não representa. Conclusão: **a pele superior do
  UAV junto à raiz encurva (enrugamento/corte do núcleo) a ~0,9 × a carga última** — a verificação da Fase 3 deve
  incluir o termo de corte do núcleo.
* C172: o espetro de encurvadura é denso (almas Kuhn em campo de tração, k ≈ 0,6, desenhadas para encurvar);
  o primeiro modo é local, numa pele superior de calibre mínimo sem reforçadores perto da ponta (λ ≈ 0,02);
  o Lanczos de 4 modos do CalculiX devolve λ ≈ 1,0 e não chega a esses modos.

### 2.3 Aerodinâmica no ciclo
* Polares NeuralFoil de perfis NACA de 4 dígitos contínuos (t/c, curvatura) em Re de raiz e ponta (`wingbox/aero.py`).
* Linha sustentadora de Glauert (Anderson, *Fundamentals of Aerodynamics*, §5.3): c·cl = 4b Σ Aₙ sin nθ,
  C_L = πAR·A₁, C_Di = πAR Σ n Aₙ²; teste: asa elíptica dá C_Di = C_L²/(πAR) e C_Lα = a₀/(1+2/AR).
* **Torção elástica**: θ_e(y) = ∫ T/GJ desde o encastramento, T sobre o centro de corte (sustentação + c_m0),
  iterada com a linha sustentadora em cruzeiro e na manobra → altera a carga e o arrasto induzido.
* C_Lmax da asa pelo método da secção crítica (primeira secção a atingir cl_max na linha sustentadora rígida;
  ver Phillips & Alley 2007, *J. Aircraft* 44(3), que discute o método e as suas limitações); restrição C_Lmax ≥ base.

### 2.4 Problema de otimização (`wingbox/optimize.py`)
Variáveis: x/c das longarinas, t/c de raiz e de ponta, curvatura, torção na ponta, passo das nervuras
(±30–40 % do valor da Fase 3, ver limitações), multiplicador da pele mínima. As espessuras não são variáveis
livres: para cada geometria o caixão é **redimensionado** pelo método da Fase 3 (Farrar/Needham para coberturas
reforçadas, Kuhn para almas, banzos CFRP + sanduíche no UAV; FS 1,5 e calibres mínimos).

Restrições: divergência, inversão e flutter (Fase 3) com margem a 1,2 V_D; C_Lmax ≥ base; volume de combustível
(60 % da envergadura, 85 % útil, 720 kg/m³ — `ASSUMPTION`); afastamento entre longarinas ≥ 0,25 c; longarina
traseira à frente da charneira de bordo de fuga mais avançada menos 3 % c (`HINGE_CLEARANCE`). A charneira
lê-se de `assumptions.stability.aileron_cf_c` (omissão 0,25) ou, numa asa voadora, de
`assembly.options.flying_wing` (`elevon`, `split_aileron`, `aileron`): usa-se o maior cf/c. Se a longarina
traseira de partida (omissão da Fase 3: 0,65 c) ficar atrás desse limite, é recuada e o facto fica no JSON
(`hinge_notes`). A inversão / eficácia de comando (Wright & Cooper 2015 Cap. 9; Bisplinghoff, Ashley &
Halfman 1955 Cap. 8; derivadas de flap de Glauert 1926) corre nas superfícies desenhadas, com o vão real
(`eta_inner`–`eta_outer` na asa voadora, ou a fracção da semi-envergadura exposta a partir da ponta no
aileron convencional). A restrição de inversão usa a superfície de rolamento mais crítica (a elevon, no
exemplo sem deriva). O canal de guinada do split (arrasto de perfil, McCormick Eq. 3.45) não inverte por
este mecanismo e fica unassessed; o V_R do split é só o acoplamento de rolamento com derivadas de flap
liso (PRESSUPOSTO).

Opt-in `assumptions.structures.wingbox.hold_section` (ou `acdt wingbox --hold-section`): t/c, curvatura e
torção geométrica ficam fixos na geometria de partida. Serve para respeitar uma torção que fecha o
equilíbrio (por exemplo a de Panknin de −10° numa asa voadora). Sem a opção o SLSQP pode alterá-las, como
até aqui; o varrimento de t/c também é omitido quando a secção está fixa. A torção de partida lê-se da asa
principal da montagem (ponta menos raiz); sem montagem permanece 0°.

Objetivos: `weight` (massa do caixão), `range` (Breguet com k_R calibrado na base, MTOW fixo: o peso poupado na
asa vira combustível), `endurance` (elétrico: ∝ 1/C_D a V fixa), `mtow` (missão fixa). SLSQP com gradientes por
diferenças finitas em variáveis normalizadas; cada avaliação demora ~0,2 s.

## 3. Resultados

| | C172 base | C172 ótimo (alcance) | UAV base | UAV ótimo (autonomia) |
|---|---|---|---|---|
| longarinas x/c | 0,20 / 0,65 | 0,259 / 0,509 | 0,20 / 0,65 | 0,273 / 0,523 |
| t/c raiz / ponta | 0,12 / 0,12 | 0,156 / 0,098 | 0,13 / 0,11 | 0,097 / 0,094 |
| curvatura, torção ponta | 2 %, 0° | 2,7 %, −2,3° | 4 %, 0° | 4,7 %, −0,7° |
| passo das nervuras | 0,84 m | 0,59 m (limite) | 0,19 m | 0,19 m |
| massa do caixão | 97,8 kg | 76,2 kg (−22 %) | 3,62 kg | 3,53 kg (−2,5 %) |
| C_D cruzeiro (C_Dp asa, C_Di) | 0,04499 (0,00525, 0,00697) | 0,04479 (0,00553, 0,00648) | 0,0331 (0,00781, 0,00935) | 0,0324 (0,00727, 0,00919) |
| L/D cruzeiro | 8,78 | 8,55 | 18,97 | 19,30 |
| e (vão) | 0,974 | 0,984 | 0,958 | 0,968 |
| desempenho | 1185 km | 1308 km (+10,4 %, +21,6 kg comb.) | 1,000 | 1,022 (+2,2 %) |
| W0 para a missão fixa | 1161 kg | 1141 kg | 23,42 kg | 23,33 kg |
| V_F / V_div (EAS) | 151 / 359 m/s | 138 / 378 m/s | 126 / 276 m/s | 84 / 193 m/s |

Leitura:
* **C172**: o ótimo engrossa a raiz (0,12 → 0,156) e afina a ponta, estreita o caixão até ao limite de 0,25 c e
  encurta as nervuras até ao limite; o volume de combustível fica quase ativo. A curvatura sobe para recuperar o
  C_Lmax perdido com a torção negativa. O L/D desce 2,6 %, mas a asa 21,6 kg mais leve vira combustível com MTOW
  fixo: alcance +10 %. Com missão fixa a W0 desce 20 kg.
* **UAV**: está em calibre mínimo quase em toda a parte, por isso o t/c quase não pesa na estrutura e o ótimo vai
  para o perfil **fino** (0,097): menos arrasto direto, como esperado. A margem de flutter desce, mas continua > 1,6.

Verificação FEM do ótimo (cascas, mesma geração de malha da Fase 4): ver `fem_baseline`/`fem_optimum` no JSON.

## 4. Limitações

* **Rigidez da viga vs casca**: a casca dá ~1,9× (C172) e ~1,4× (UAV) a flecha da viga com EI da secção. Parte vem
  da modelação da Fase 4 (reforçadores em lâmina com o centróide 0,52·a para dentro da pele, `ASSUMPTION`; a
  Fase 3 coloca a área do reforçador no plano da pele), o resto de altura do caixão plano vs contorno, corte das
  almas Kuhn e shear lag. Na raiz do C172, a cobertura superior da casca está a −217 MPa contra 184 MPa da tensão de projeto da Fase 3 (+18 %). As margens aeroelásticas e de
  resistência de nível A são, por isso, otimistas; a FEM serve para o verificar, não entra no ciclo.
* **Torção na casca**: a Fase 4 aplica as forças nas longarinas e não inclui a célula D; o binário na raiz difere
  do da Fase 3 (C172: 257 vs −98 N·m), daí torções da ponta com sinais diferentes.
* **Massa das nervuras**: alma de calibre mínimo meio-cheia (Fase 3); sem banzos, reforços nem esmagamento → o
  passo das nervuras fica limitado a ±30–40 % da Fase 3 para não "comprar" coberturas mais leves com nervuras que
  não estão dimensionadas.
* Linha sustentadora sem enflechamento/compressibilidade; polares NeuralFoil (sem XFOIL no ciclo); C_D_rest fixo.
* Encurvadura na otimização = Fase 3 (Farrar/Needham/Kuhn); a encurvadura de casca só é verificada.
* Flechas do UAV ótimo (0,28 m na ponta, 13 % da semienvergadura, cargas últimas) estão no limite da teoria linear.
* SIMP da nervura (topologia) não foi feito nesta fase.
