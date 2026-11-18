# Tutorial — Fase 3: MDA/MDO (OpenMDAO), aeroestrutura, aeroelasticidade, encurvadura, qualidades de voo

Continua o [tutorial da Fase 2](tutorial-fase2.md). A Fase 3 junta à baixa fidelidade da Fase 2:

* verificações aeroelásticas clássicas;
* dimensionamento do caixão por encurvadura;
* scissor plot e modos dinâmicos com qualidades de voo;
* acoplamento aeroestrutural estático (OpenAeroStruct);
* otimização multidisciplinar em OpenMDAO.

Regras: só métodos clássicos citados no código; stubs honestos onde o método não está
implementado; nenhum número afinado para passar verificações.

## 0. Pré-requisitos

* `pip install -e ".[dev,aero,mdo]"`: o extra `mdo` instala OpenMDAO (≥ 3.30, testado 3.45.1)
  e OpenAeroStruct (≥ 2.7, testado 2.12.0), ambos Apache-2.0 (ver `THIRD_PARTY.md`);
* `avl` e `xfoil` no `PATH`, como na Fase 2. As derivadas de estabilidade dos modos dinâmicos
  vêm do AVL; sem ele usam-se as de manual e o relatório indica-o.

Sem OpenMDAO/OpenAeroStruct, `acdt size` continua a funcionar: a secção aeroestrutural fica
marcada como não corrida e `acdt optimize` devolve o código 2.

## 1. Correções pendentes da Fase 2

**Energia de descolagem e subida (elétrico).** O dimensionamento usava a estimativa de energia
potencial de Hepperle (m g h / η), enquanto a verificação integrava a potência por segmentos.
Agora o ciclo de dimensionamento usa a mesma energia de segmento da verificação
(`performance.takeoff_climb_energy`: corrida de descolagem e subida com a potência e a polar do
iterado; `weights.py`, `prop.takeoff_climb_J_per_kg`). Se a subida não chega à altitude de
cruzeiro, é emitido um aviso.

Consequência honesta: o UAV elétrico de exemplo (AR 14 fixado à mão) precisa de mais bateria e
de mais asa, e passa a violar o limite de envergadura de 4,2 m (b = 4,28 m). O YAML **não** foi
alterado para esconder isto; a otimização (§7) resolve o problema.

**Ângulo de aproximação.** O ângulo passa a ser um parâmetro documentado:

```yaml
performance:
  approach_angle_deg: 3.0
```

* 3° corresponde ao gradiente máximo de 5,2 % da aproximação estabilizada de CS/14 CFR
  23.75(a)(1) (aviação ligeira).
* Ângulos maiores só são admissíveis se forem demonstrados, limitados e indicados
  (23.75(a)(2)).
* A distância de aterragem segue Raymer Sec. 17.9 (obstáculo de 50 ft).

## 2. Aeroelasticidade clássica (`aeroelasticity.py`)

O modelo é uma viga/faixa por semi-asa (`WingStrip`), encastrada na raiz. EI e GJ vêm do caixão
da Fase 2 e a massa por unidade de envergadura vem da asa dos pesos. O eixo elástico é o centro
de corte do caixão e o centro de massa da secção é um pressuposto indicado.

| verificação | método | critério |
|---|---|---|
| divergência torsional | teoria das faixas, problema de valores próprios K θ = q A θ (Wright & Cooper 2015; Bisplinghoff, Ashley & Halfman) | V_div > 1,2 V_D (EAS) |
| inversão de aileron | faixas + derivadas de flap de Glauert (1926) a_C, b_C (Wright & Cooper Cap. 9) | V_rev > 1,2 V_D |
| flutter binário | modos assumidos flexão (y/s)² + torção y/s, aerodinâmica de faixas quase-estacionária com o termo de amortecimento M_θ̇ = −1,2 (Wright & Cooper 2015, Cap. 11), integrada na envergadura com c, EI, GJ, m(y); varrimento de valores próprios em V; diagrama V–g (`flutter_vg.png`) | V_F > 1,2 V_D |
| AEER-45 | critérios simplificados FAA (antigo 23.629(d) / AC 23.629-1B): fator de flexibilidade torsional F da asa na envergadura do aileron | F ≤ F_max; aplica-se só a V_D < 260 KEAS e M < 0,5; para UAV (STANAG 4671) é informativo |

Os resultados aparecem como verificações `aeroel:*` e na §15 do relatório. Tal como `perf:*`,
são verificações e **não** alteram a viabilidade do dimensionamento. O flutter quase-estacionário
é uma estimativa: a margem final exige modos FEM e doublet-lattice (Fase 4).

## 3. Estruturas: tensão diagonal de Kuhn, crippling e caixão por encurvadura

O caixão da Fase 2 era dimensionado só à resistência, o que dava um limite inferior irrealista.
A Fase 3 dimensiona-o também à encurvadura (`structures.py`, §14 do relatório):

* **revestimento e reforçadores:** painel reforçado à compressão no ótimo de Farrar
  σ_F = F √(N E / L), F = 0,81 (Farrar 1949; Megson; Niu), L = passo das nervuras, com a
  interação de encurvadura do revestimento ao corte e à compressão R_c + R_s² ≤ 1 (Bruhn C5);
* **banzos/longarinas:** crippling de Needham (1954), Bruhn Eq. C7.6:
  F_cs = C_e √(F_cy E)/(b'/t)^0,75 ≤ F_cy;
* **almas:** tensão diagonal incompleta de Kuhn (NACA TR-1179; Bruhn Cap. C11),
  k = tanh(0,5 log10(τ/τ_cr)), com dimensionamento dos montantes (crippling de Needham e
  crippling forçado, Bruhn Eq. C11.40). Os pressupostos estão indicados no código.

A massa do caixão por encurvadura volta a ser comparada com Raymer Eq. 15.46:

| exemplo | resistência [kg] | encurvadura [kg] | Raymer 15.46 [kg] | encurvadura / Raymer |
|---|---|---|---|---|
| Cessna 172S | 86.2 | 99.9 | 132.1 | 0.76 |
| GA 2 lugares | 67.5 | 74.7 | 109.4 | 0.68 |
| treinador | 127.7 | 161.6 | 214.7 | 0.75 |
| UAV elétrico 25 kg | 3.40 | 3.63 | 4.66 | 0.78 |
| UAV sobre-restringido | 4.75 | 5.09 | 6.73 | 0.76 |
| UAV gasolina 150 kg | 3.55 | 4.75 | 13.6 | 0.35 |

A razão de 0,7–0,8 é plausível: o caixão não inclui superfícies de comando, bordos, nervuras,
ligações nem fixações, que Raymer inclui estatisticamente. O UAV a gasolina (0,35) mostra que a
Eq. 15.46 (aviação geral) não se aplica bem a um UAV de 150 kg. A massa usada no
dimensionamento continua a ser a de Raymer, e o caixão é o cross-check.

## 4. Acoplamento aeroestrutural estático (OpenAeroStruct)

`aeroelasticity.static_aerostructural` constrói um problema OpenAeroStruct: VLM com uma viga de
caixão (`wingbox`) com a planta, o perfil e as espessuras do caixão acdt, e o material da Fase 2.
Resolve-o em dois casos:

* cruzeiro, na condição 1 g;
* manobra, a n_lim.

Para cada caso obtém CL, CDi e e rígido e flexível, a deflexão e a torção na ponta, e o índice
de falha (indicativo). O efeito da deformação no desempenho é passado à missão: K_flex/K multiplica
o fator de arrasto induzido e a missão por segmentos é recalculada (§15 do relatório,
"flexível vs desacoplado").

Cessna 172S:

* K_flex/K = 1,0034;
* alcance 1277,2 → 1276,6 km (flexível);
* deflexão na ponta de 0,056 m em cruzeiro e 0,227 m na manobra.

Este é o efeito esperado numa asa de aviação geral rígida e não enflechada.

## 5. Scissor plot, modos dinâmicos e qualidades de voo (`stability.py`)

* **Scissor plot** (Torenbeek 1982, Cap. 9; Raymer Cap. 16): mostra S_h/S necessário para
  estabilidade (CG traseiro com a margem estática alvo) e para controlo (CG dianteiro,
  compensação em aproximação com δe máx). O ficheiro é `scissor.png`. O momento dos flaps não está
  incluído, o que está indicado.
* **Inércias:** soma por componentes em torno do CG à MTOW (Roskam Parte V, Cap. 10), com as
  estações típicas de CG dos componentes (pressuposto indicado).
* **Modos:** são calculados a partir de matrizes de estado longitudinais e laterais
  (Nelson 1998, Caps. 4–5; Etkin & Reid 1996) com as derivadas do AVL: período curto, fugóide,
  rolamento holandês, espiral e rolamento. O lugar das raízes está em `root_locus.png`.
* **Qualidades de voo:** MIL-F-8785C, Classe I, Categoria B (`stability.hq_category`), nível
  exigido 1. As grandezas verificadas são:
  * ζ do período curto e CAP (Figs. 1–3);
  * ζ da fugóide;
  * ζ, ζω e ω do rolamento holandês (Table VI);
  * τ_R (Table VII);
  * T2 da espiral (Table VIII).

  Os resultados aparecem como verificações `hq:*` (§16). Para UAV a MIL-F-8785C é indicativa:
  não há piloto a bordo e o autopiloto aumenta a estabilidade.

Resultados dos exemplos:

* Cessna 172S: tudo no Nível 1; S_h/S = 0,202 = necessário (limitado pela estabilidade).
* UAV elétrico: CAP = 7,8 (Nível 2) e espiral instável com T2 = 11,6 s (Nível 2).
* GA 2 lugares: rolamento holandês instável (Nível > 3), indicado como falha para revisão da
  empenagem vertical/diedro.

## 6. MDO em OpenMDAO (`mdo.py`, `acdt optimize`)

```bash
acdt optimize examples/uav_endurance_payload.yaml -o out/uav_mdo              # objetivo do registo ou W0
acdt optimize examples/cessna172_check.yaml --objective range -o out/c172_rng  # W0 ≤ W0 base
```

**Disciplinas e formulação.**

* As disciplinas (pesos, aerodinâmica, estruturas, desempenho e estabilidade) são componentes
  OpenMDAO num grupo MDF. São elas:
  * o envelope do diagrama de restrições, que dá P/W = máx(curvas) × (1 + margem), como no
    design point;
  * a geometria;
  * a polar;
  * o caixão/asa e o n_lim do V-n;
  * o fecho de W0 (Raymer Eq. 3.4 com pesos por componente);
  * a missão (energia/combustível);
  * a compensação e a margem estática.
* O MDA usa NLBGS (Gauss–Seidel não linear com Aitken) ou Newton (`--solver newton`).
* As derivadas parciais são calculadas por diferenças finitas e os totais pelo sistema linear
  acoplado.
* O otimizador é SLSQP.

**Variáveis de projeto:**

* W/S e AR;
* opcionalmente P/W (`mdo.design_vars: [ws, pw, AR]`): nesse caso as curvas do diagrama
  passam a ser restrições.

**Objetivo e restrições vêm do registo de requisitos.**

* Objetivos possíveis: `W0`, `energy`, `cost`, `endurance` e `range`.
* Restrições:
  * limites de W/S (perda, aterragem);
  * envergadura;
  * MTOW;
  * compensação;
  * W0 ≤ W0 base nos objetivos de desempenho.

**Gestão de modelos por região de confiança.**

* Bibliografia: Alexandrov, Dennis, Lewis & Torczon 1998; Alexandrov et al. 2001; Conn, Gould
  & Toint 2000, Alg. 6.1.1.
* **Modelo de alta fidelidade:** o pipeline completo da Fase 2/3, que inclui:
  * XFOIL/AVL no ciclo;
  * a re-seleção de sistemas;
  * a estabilidade e a aeroelasticidade;
  * a missão por segmentos.
* **Modelo de baixa fidelidade:** o modelo OpenMDAO de manual, com duas correções que fazem
  coincidir o valor e o gradiente com o pipeline completo no iterado x_k (consistência de 1.ª
  ordem):
  * uma correção β multiplicativa da polar;
  * uma correção aditiva de 1.ª ordem de W0 (e de E, no objetivo de energia).

  O gradiente de alta fidelidade é calculado por diferenças finitas progressivas de 2 %.
* **Cada passo:**
  1. otimiza-se o modelo em ±Δ·x_k;
  2. corre-se o pipeline completo no ponto obtido;
  3. calcula-se ρ = redução real / redução prevista do mérito φ = f/|f0| + 10·violação;
  4. o passo é aceite se ρ > 0,01 e não houver novas falhas de dimensionamento/desempenho;
  5. Δ é atualizado: ρ < 0,25 → Δ/2; ρ > 0,75 com o passo na fronteira → 2Δ.
* **Paragem:** Δ < 0,02, redução prevista < 1e-5 ou 8 iterações.

O modelo de alta fidelidade é **descontínuo**: a seleção de sistemas é discreta. Por exemplo, o
motor do UAV salta de outrunner 50xx (2,6 kW) para 63xx (4,5 kW), cerca de +2 kg. Os passos que
caem num salto destes dão ρ < 0 e são rejeitados, o que fica registado no relatório
`mdo_report.md`. As verificações `hq:*` e `aeroel:*` são reportadas, mas ainda não são
restrições do otimizador.

Saída em `out/<caso>_mdo/`:

* `mdo_report.md`, com a tabela da região de confiança, base vs ótimo do modelo e base vs ótimo
  no pipeline completo;
* `mdo.json`;
* `baseline/` e `optimum/` (relatórios completos).

## 7. Resultados: base vs ótimo (pipeline completo)

Os valores são do pipeline completo, re-corrido no ponto aceite; os ficheiros estão em
`examples/output/*_mdo*/mdo_report.md`. As margens são V/(1,2 V_D) − 1.

| caso | objetivo | base → ótimo | margens aeroelásticas div / inv / flutter | falhas base → ótimo |
|---|---|---|---|---|
| Cessna 172S | min W0 | W0 1161 → 1121 kg (−3,4 %); AR 7,32 → 5,0 (limite inferior ativo); W/S 811 → 822 N/m²; b 10,14 → 8,18 m; alcance 1277 → 1268 km; 4 it., todas aceites (ρ ≈ 1) | +64/+61/−4 % → +108/+104/+20 % | aeroel:flutter, perf:landing_distance → hq:dutch_roll (Nível 2), perf:landing_distance |
| Cessna 172S | max alcance, W0 ≤ 1161 kg | alcance (segmentos) 1277 → 1443 km (+13 %); AR 5,0; Wf 178,6 → 205,7 kg; autonomia 5,80 → 6,51 h | → +106/+103/+19 % | idem |
| UAV elétrico 25 kg | min W0 | W0 23,42 → 21,75 kg (−7,1 %); AR 14 → 11,11; b 4,28 → 3,67 m (limite de 4,2 m cumprido); E 1766 → 1756 Wh; autonomia 2,77 → 2,74 h; 7 it. (4 rejeitadas por saltos de motor) | +386/+379/+188 % → +492/+484/+253 % | wing_span, hq:CAP, hq:spiral → hq:CAP, hq:spiral |
| UAV elétrico 25 kg | max autonomia, W0 ≤ 25 kg | autonomia (segmentos) 2,77 → 2,99 h (+8,1 %); W0 24,73 kg; AR 8,74; b 3,45 m; E 1766 → 2293 Wh; alcance 214 → 234 km; passos que violavam o MTOW rejeitados | → +590/+581/+315 % | idem |

Leitura:

* No C172 o otimizador reduz o AR até ao limite inferior (5). A asa mais curta é mais leve e
  mais rígida, o que resolve o flutter estimado, mas o rolamento holandês passa ao Nível 2 porque
  a cauda vertical é mantida pelo coeficiente de volume.
* A distância de aterragem (504 m vs ≤ 407 m, com aproximação a 3°) continua a falhar, tanto na
  base como no ótimo.
* No UAV o MDO resolve a envergadura. CAP e espiral (Nível 2) continuam, porque não são
  restrições do otimizador.
* Caixão por encurvadura / Raymer no ótimo: C172 81,4 / 97,7 kg (0,83); UAV 3,31 / 3,63 kg
  (0,91).

## 8. Limitações conhecidas

* O modelo do otimizador é de manual com correções; a consistência de 1.ª ordem só é garantida
  no iterado, e as derivadas são por diferenças finitas (não analíticas).
* O SLSQP trata W/S, P/W e AR. O motor, o ESC e a célula ficam fixos nesse subproblema e só mudam
  num passo de catálogo, aceite quando o mérito do pipeline melhora (Geoffrion 1972). A hélice continua
  a ser o diâmetro contínuo de Raymer Sec. 10.3: não há catálogo de hélices. Os servos são reescolhidos
  no fecho.
* `hq:*` e `aeroel:*` não são restrições do MDO. No C172, o ótimo de W0 em AR = 5 (limite
  inferior ativo) resolve o flutter, mas falha no rolamento holandês.
* O flutter é quase-estacionário e de secção típica; o scissor plot não inclui o momento dos
  flaps; as inércias são estatísticas (Roskam V).
* O caixão por encurvadura não tem nervuras, ligações nem superfícies de comando; Raymer continua
  a ser a massa usada.
* OpenAeroStruct: viga equivalente e VLM sem fuselagem; o índice de falha é indicativo.

## 9. Testes

`tests/test_phase3.py` cobre:

* divergência contra a forma fechada q_D = π² GJ/(4 s² e c² a_w);
* as derivadas de Glauert;
* flutter < divergência; AEER-45;
* Kuhn e Needham;
* caixão por encurvadura ≥ caixão de resistência;
* modos e qualidades de voo do C172 (Nível 1);
* as margens aeroelásticas do C172;
* a energia de subida elétrica;
* o MDO do UAV: reproduz a base e reduz W0 com a envergadura cumprida.


## HQ / aeroelasticidade como restrições do MDO (opt-in, 9 nov 2026)

Por omissão, `hq:*` e `aeroel:*` só entram no filtro de aceitação *depois* do passo (legado).
Com `assumptions.mdo.hq_aeroel_constraints: true` passam a restrições na violação do mérito
φ = f/|f₀| + 10·violação: margens de faixas g = 1 − V/V_req ≤ 0; níveis MIL / scissor / AEER
como g ∈ {0,1}. Unassessed (`ok is None`) **não** é satisfeito. Allow-list: `mdo.hq_aeroel_keys`.
Demo: `examples/mdo/hq_aeroel_constraints_demo.py`.
