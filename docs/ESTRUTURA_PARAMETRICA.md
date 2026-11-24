# Estrutura paramétrica de baixa fidelidade (disciplina `structure_layout`, L1)

Funcionalidade geral do acdt, independente da configuração (convencional, sem cauda, UAV, VTOL, booms). Permite
definir por parâmetros os membros estruturais do avião — longarinas, nervuras, revestimentos, cavernas, anteparas,
reforçadores/longarinas da fuselagem, booms e apoios —, verificá-los com métodos clássicos citados, dimensioná-los e
passar o resultado às outras análises: orçamento de massa/CG/inércia, modelo de vigas para análise externa e
relatórios.

Incremento 1 (24 nov 2026): esquema único, cavernas/anteparas/reforçadores explícitos na fuselagem e nos booms
(o que faltava), tabela única de membros com a asa e as empenagens **embrulhadas** (não redimensionadas) e exportação
de um modelo de vigas neutro. Estudo de exemplo em aviões convencionais (C172 e UAV de 150 kg), `applied: false`.

## 1. O que já existia (levantamento)

| Área | Onde | O que faz |
|---|---|---|
| Cargas | `domains/aircraft/structures.py` | Diagrama V-n (CS-23 / 14 CFR 23 / STANAG 4671), sustentação em envergadura (Schrenk ou faixas do AVL), V/M/T por integração da ponta |
| Caixão da asa (Fase 2/3) | `structures.py` | Caixão de duas longarinas por resistência (Megson) e por estabilidade: painéis reforçados (Farrar), almas de Kuhn com montantes, crippling de Needham, revestimento sanduíche |
| Secção real (Fase 5) | `core/thinwalled.py`, `wingbox/section.py` | Solver multicélula de parede fina (Megson): centro de corte, EI, GJ no contorno do perfil, célula D do bordo de ataque |
| Caixão Fase 6 | `wingbox/sizing6.py`, `shell6.py`, `optimize*.py`, `study*.py`, `render.py` | Painéis metálicos/sanduíche, banzos I/C/Z/compostos, nervuras dimensionadas com aligeiramentos, FEM de casca, otimização, desenho |
| Nervuras por topologia | `wingbox/rib_simp.py`, `rib_simp_mass.py` | SIMP das nervuras e massa no orçamento |
| Secções e materiais | `core/sections.py`, `core/materials.py` | Perfis I/C/Z/T/cantoneira/ómega/tubos, encurvadura local, crippling de Gerard/Needham; metais MIL-HDBK-5J, compósitos por CLT, núcleos |
| Viga-fuselagem L1 | `structures_l1.py` | Tubo circular (NASA SP-8007), longarinas e cavernas à espessura **mínima**, piso e **duas anteparas à espessura mínima** (sem verificação), envelope cauda a VA / motor / aterragem 23.473; empenagens como caixões de carga uniforme (só massa) |
| Pormenor | `detailed_sizing.py`, `assembly/gear_devices.py` | Esmagamento de nervuras, ligação de raiz por parafusos, superfícies de comando; pernas do trem |
| Aeroelasticidade / alta fidelidade | `aeroelasticity.py`, `hifi/nastran.py`, `hifi/fem.py` | Divergência, inversão, flutter binário, AEER-45; escritor SOL 145 da asa |

**Lacunas** que este incremento ataca: não havia cavernas explícitas nas estações das cargas concentradas (ligação
da asa, trem, berço do motor, carga útil, cauda), nem verificação de anel de caverna, de instabilidade geral, de
reforçadores entre cavernas ou de anteparas; os booms não tinham estrutura; não havia uma tabela única de membros
nem um modelo de vigas do avião inteiro.

## 2. Arquitetura

```
assumptions.structure_layout            (opt-in; enabled: false por omissão)
├── material: auto | chave de acdt.core.materials
├── coupling: relatorio | iterar          (iterar ainda não implementado — relatado)
├── fuselage:                             (corpo tubular principal)
│   ├── frame_pitch_m, frame_section {kind: z|channel|hat|i, h_m, b_m}
│   ├── stringers {n | pitch_m, kind, h_m, b_m, t_m}, longerons {n, area_m2, theta_deg}, skin_t_m
│   ├── bulkheads [{id, x_m | x_frac, pressure_Pa, edge: simply_supported|clamped}]
│   ├── auto_loads (cargas da viga L1), wing_attach_theta_deg, engine_mount_theta_deg, gear_theta_deg, tail_theta_deg
│   └── loads [{id, kind, x_m | x_frac, theta_deg, Fz_N, Fy_N, M_Nm, mass_kg, case}]
├── booms [{id, x0_m, length_m, diameter_m, y_m, z_m, loads [{x_m, Fz_N, Fy_N, T_Nm}], …mesmas chaves da fuselagem}]
└── export {beam_model: true}
```

* **Coordenadas**: x para trás a partir do nariz, y para a direita, z para cima. Nas cavernas, θ é medido a partir
  do topo, positivo para +y (90° = lado direito, 180° = fundo).
* **Superfícies sustentadoras** (asa, estabilizador, deriva, e no futuro superfícies de VTOL): o caixão continua a
  ser o de `structures.py`/`wingbox` (já dimensionado e verificado). A disciplina embrulha-o na tabela de membros
  (banzos, almas, painéis, núcleo, bordos, nervuras, não-ótimo) e no modelo de vigas (EI e GJ por estação).
* **Corpos tubulares** (fuselagem, booms): o código novo é genérico (`acdt/core/structures/frames.py`, sem
  dependência do domínio). O adaptador (`domains/aircraft/structure_layout.py`) traduz as cargas do avião.
* **Saídas** (`result.structure_layout`): `members` (tabela única: id, componente, tipo, massa, posição, inércia
  própria, RF mínimo, veredicto passa/falha/desconhecido, método, fonte, secção, cargas), `budget` (massa, CG,
  Ixx/Iyy/Izz no CG estrutural, por componente, massas desconhecidas listadas), `comparison` (fuselagem paramétrica
  vs viga L1 vs Raymer Eq. 15.49), `fuselage` (cavernas, tabela da casca por estação, casos de carga, notas),
  `booms`, `beam_model` (`acdt.beam/1`). `to_nastran(beam_model)` dá o mesmo modelo em texto de campos curtos
  (GRID/MAT1/PBAR/CBAR/CONM2), escrito pelo acdt (sem código GPL), para correr fora (p. ex. CalculiX por subprocesso,
  via Build).

## 3. Cargas

* **Envelope da casca**: M, V e T LIMITE por estação da viga-fuselagem L1 (`structures_l1.fuselage_beam`): cauda a VA
  (Raymer 12.15) ou equilíbrio + 23.423(b), inércia do motor, aterragem 23.473 (com as mesmas omissões: 23.427 e
  23.441 não modelados). Fator de segurança 1,5 (23.303 / USAR.303).
* **Cavernas pesadas** (cargas concentradas LIMITE, por caso):
  * *manobra*: sustentação de projeto da cauda nas fixações da cauda (+ torção da deriva como binário), inércia do
    motor n·m·g nos quatro apoios do berço (±45°, ±135° — PRESSUPOSTO), e as duas ligações da asa (longarinas da
    frente e de trás, posição pela corda de raiz no centro aerodinâmico — PRESSUPOSTO) a equilibrar força e momento
    destas cargas;
  * *aterragem*: reações do trem da viga L1 (frente a 180°, trás a ±150° — PRESSUPOSTO, trem na fuselagem), inércia
    do motor ao fator de inércia da aterragem e metade da sustentação em cada longarina da asa (PRESSUPOSTO);
  * cargas do utilizador (`loads`): massa × n e forças declaradas, reagidas pela casca na própria caverna.
* A inércia distribuída da casca vai para o revestimento e os reforçadores, não para as cavernas (PRESSUPOSTO).

## 4. Verificações (todas com RF = admissível/aplicado)

| Membro | Verificação | Método |
|---|---|---|
| Caverna pesada | anel sob cargas concentradas reagidas pelo fluxo de corte da casca q(θ) = (F_z sin θ − F_y cos θ)/(πR) + T/(2πR²); hiperestático de grau 3 resolvido por Castigliano (só flexão, anel fino); σ = max(|N|/A + |M| c/I) ≤ F_cy | Megson (tubo fino; métodos energéticos); Timoshenko, *Strength of Materials* (anéis); verificado contra o anel comprimido por duas forças (P R/π e P R (1/2 − 1/π)) |
| Caverna (todas) | crippling da secção | Gerard (`core/sections.py`; Bruhn C7) |
| Caverna (todas) | instabilidade geral: EI ≥ C_f M_ult D²/L, C_f = 1/16 000 | Shanley (1949); Niu (1988) cap. 11 |
| Reforçadores/longarinas | σ = M z/I em booms com largura efetiva de von Kármán b_e = 1,9 t √(E/σ); coluna entre cavernas Euler–Johnson com corte no crippling de Gerard, c = 1 (PRESSUPOSTO), raio de giração para fora do plano da pele (PRESSUPOSTO: a pele estabiliza o modo lateral) | Megson Eq. 20.1; Bruhn C2/C7 |
| Revestimento | τ = q/t ≤ F_su com q = V/(πR) + T/(2πR²); painel plano simplesmente apoiado k_c = 4, k_s = 5,35 + 4 (b/a)², interação R_c + R_s² ≤ 1 à carga LIMITE (sem encurvadura até à limite — PRESSUPOSTO; curvatura desprezada, conservativo) | Megson; Bruhn C5 |
| Antepara | placa circular sob pressão: apoiada 3(3+ν) p a²/(8t²), encastrada 3 p a²/(4t²), ≤ F_ty | Timoshenko & Woinowsky-Krieger §15–16 |

**Dimensionamento por membro**: cavernas — espessura em passos de 0,1 mm desde a mínima do material até 6 mm; se
não chegar, altura × 1,25 até 0,12 D (PRESSUPOSTO); a secção escolhida é verificada contra todos os casos da estação.
Revestimento e reforçadores — espessuras por estação em passos de 0,1 mm até passarem (corte/encurvadura → pele;
coluna/tração → reforçador). Anteparas — espessura da placa pela pressão, mínima sem pressão. Fator não-ótimo
`structures.nonoptimum_factor` (Torenbeek 1982 App. C) como linha própria.

**Desconhecido ≠ passa**: cavernas sem momento do corpo, anteparas sem pressão declarada (o corte da alma sob cargas
concentradas não está modelado), bordos/nervuras/não-ótimo da asa (espessura mínima, não verificados) e booms sem
cargas ficam «desconhecido».

## 5. Estudo de exemplo (`applied: false`)

`python examples/studies/estrutura_parametrica/estudo_estrutura_parametrica.py` (cerca de 2 min). Liga
`structure_layout` em memória em `examples/cessna172_check.yaml` e `examples/uav_150kg_stanag4671.yaml` (e, desde o incremento A, no twin-boom `examples/uav_twin_boom_shortcut.yaml`, §6); escreve
em `examples/output/estrutura_parametrica/` a tabela de membros (CSV), o resumo (JSON), o modelo de vigas (JSON) e o
`.bdf`. Material Al 2024-T3 (MIL-HDBK-5J), cavernas Z, reforçadores Z 20 × 12 mm a passo de 0,12 m (PRESSUPOSTO).

| Caso | W0 | Fuselagem paramétrica | Viga L1 | Raymer 15.49 | Pele | Reforçadores | Cavernas (leves + pesadas) | Anteparas | Não-ótimo |
|---|---|---|---|---|---|---|---|---|---|
| C172 | 1137,8 kg | **106,0 kg** | 85,1 kg | 97,6 kg | 58,1 kg | 12,3 kg | 3,2 + 10,3 kg | 0,9 kg | 21,2 kg |
| UAV 150 kg | 153,2 kg | **12,1 kg** | 5,5 kg | 7,3 kg | 7,2 kg | 1,7 kg | 0,1 + 0,6 kg | 0,1 kg | 2,4 kg |

No C172 a fuselagem paramétrica fica 9 % acima de Raymer (que inclui portas, janelas e piso que este modelo ainda
não tem, e não inclui a encurvadura à carga limite): o revestimento é dimensionado pela encurvadura dos painéis à
carga limite. As seis cavernas pesadas passam, com a do trem principal a subir para 54 mm de altura e 4,7 mm de
espessura (aterragem) e a da cauda para 5,2 mm. No UAV de 150 kg a massa é dominada pelas espessuras mínimas
(0,41 mm de pele, reforçadores e cavernas mínimas): o modelo é conservativo a esta escala, e o resultado só deve
ser lido como limite superior até haver um material/processo de UAV (compósito, `material: cfrp_qi`). Nenhum
membro falha; os desconhecidos (7 em cada caso) são os listados acima.

## 6. Empenagens, booms e modelo de vigas do avião inteiro (incremento A)

**Empenagens pelo caminho do caixão da asa.** `assumptions.structure_layout.tails.method` = `buckling` (omissão)
redimensiona o caixão de cada empenagem com o dimensionador por estabilidade da asa
(`structures.box_beam_sizing_buckling`: painéis reforçados, almas de Kuhn — Bruhn C5/C11, Megson) sob a sustentação
de projeto da L1 (carga uniforme, cima e baixo com n_neg = 1 — PRESSUPOSTO); depois a secção multicélula da Fase 5
(`box_section_properties`, Megson) dá EI, GJ e o centro de corte por estação. `strength` usa o caixão L1 tal como
está. `structures_l1` passa a expor `tails.htail_box`/`vtail_box` (estações, massas por grupo, EI/GJ, secção) — aditivo.

A deriva é **encastrada só na raiz**: é tratada como metade de uma asa espelhada de altura b e área 2S (mesmas
cordas), com M_raiz = L b/2. O caixão L1 existente (`_uniform_tail` sem `single_sided`) trata a deriva como duas
metades de altura b/2, o que dá um momento na raiz 4× menor; esse caminho L1 **não foi alterado** (as massas L1 e o
W0 dos exemplos ficam iguais) e fica como achado para decisão.

**Booms ligados à geometria de montagem.** Com `booms_from_assembly: true` (omissão), cada corpo da montagem
(`assumptions.assembly`) com papel «boom» passa a ser um boom (as imagens espelhadas contam à parte): x0/comprimento
das estações, diâmetro equivalente √(w·h) máximo, eixo paralelo a x (PRESSUPOSTO), ligação à asa no centro
aerodinâmico da asa (`x_wing_m`, PRESSUPOSTO). Cargas LIMITE que lá se apoiam, por caso:

* `voo_cauda`: superfícies com papel «tail/cauda/empenagem» na extensão do boom mais próximo recebem a sustentação de
  projeto do estabilizador (−z) e da deriva (+y) da L1 repartidas pelos booms com cauda, e a torção
  L_deriva × 0,4 × semienvergadura (o braço da L1) — PRESSUPOSTO;
* `pairar_rotores`: discos com papel rotor/lift/elevação (hélices de propulsão excluídas) recebem
  T_lim = `rotor_thrust_factor` × W0 g / n_rotores (1,5 por omissão, PRESSUPOSTO — declarar o do projeto). O binário
  de reação dos rotores não está modelado (desconhecido, listado nas notas).

O boom é verificado como **duas consolas a partir da ligação** (cargas atrás fletem a parte de trás, à frente a da
frente; somadas com sinal por plano e combinadas vetorialmente; na ligação fica o maior dos dois lados) e envolvente
dos casos; depois as mesmas cavernas, anteparas, reforçadores e casca da fuselagem (§2–4). Booms declarados em
`booms:` substituem os da montagem com o mesmo `id`.

**Modelo de vigas do avião inteiro.** `acdt.beam/1` passa a ter corpos (fuselagem, booms em (y0, z0)) e superfícies
(asa e estabilizador em ±y, deriva em +z) com EI/GJ por estação; a raiz de cada superfície partilha o nó de corpo mais
próximo e cada boom liga ao nó mais próximo de outro componente na estação de ligação por um elemento 10× mais
rígido (PRESSUPOSTO). O modelo é uma árvore ligada (elementos = nós − 1).

| Caso | Estabilizador: layout / L1 | Deriva: layout / L1 | Booms | Vigas (nós / elementos) |
|---|---|---|---|---|
| C172 | 11,16 / 10,54 kg | 4,31 / 4,11 kg | — | árvore ligada, sem componentes em falta |
| UAV 150 kg | 0,36 / 0,25 kg | 0,34 / 0,23 kg | — | idem |
| Twin-boom (`uav_twin_boom_shortcut`, W0 167,0 kg) | 0,45 / 0,31 kg | 0,51 / 0,35 kg | 2 × 2,84 kg; M_lig 279 N·m (cauda) | idem, com 2 ligações rígidas |

Os caixões das empenagens pelo caminho da asa passam a encurvadura (`buckling_ok`); no C172 o caixão L1 só de
resistência não passa (`buckling_ok` falso). Nos UAV pequenos mandam as espessuras mínimas (layout acima da L1). No twin-boom, as cavernas à
frente da ligação ficam «desconhecido» (sem carga nesse troço) e a cauda é uma superfície equivalente única da L1
(duas derivas reais não separadas — PRESSUPOSTO). O caso VTOL (quadplane com 4 rotores de elevação em 2 booms) está
coberto por um teste com uma montagem em linha, porque os exemplos `examples/vtol/` não têm geometria de montagem.

## 7. Ferragens e berço do motor (incremento B)

Módulo genérico `acdt/core/structures/fittings.py` e `fittings_layout` em `structure_layout` (opção `fittings`,
ligada por omissão quando a disciplina está ligada). Cada ferragem entra na tabela de membros (componente
`ligacoes`, tipos `ferragem` e `berco_motor`) com massa, posição, RF, veredicto, método e a origem da carga.

**Olhal + garfo + cavilha sob carga axial** — Melcon & Hoblit (*Product Engineering*, 1953) como codificado no
*Stress Analysis Manual* AFFDL-TR-69-42 (Maddux et al., 1969) §9.3–9.4, o mesmo método de Bruhn (1973) cap. D1:

* apoio/corte à frente do furo: F_bru,L = K (a/D) F_tu (e/D < 1,5) ou K F_tu (e/D ≥ 1,5) (Eq. 9-1), P = F D t ou
  1,304 F_bry,L D t se F_tu > 1,304 F_ty (Eq. 9-3). K da **Fig. 9-2** (D/t ≤ 5); acima de D/t = 5 a Fig. 9-3 não
  foi lida e o modo fica **desconhecido**;
* secção útil: P = K_n F_tu (w − D) t (Eq. 9-4, 9-6), K_n da **Fig. 9-4** (painéis F_ty/F_tu = 0,6 e 0,8, curvas
  F_tu/(E ε_u) = 0,1 e 1,0). Sem alongamento declarado (`fittings.eps_u`) usa-se a curva 1,0, a mais baixa
  (conservativa); F_ty/F_tu < 0,6 fica desconhecido;
* cavilha: corte duplo P = 1,571 D² F_su (Eq. 9-12) e flexão P = 0,1963 k_b D³ F_tu / (t1/2 + g + t2/4)
  (Eq. 9-13 a 9-15, k_b = 1,56); a redistribuição do pino fraco (Eq. 9-16) não é usada (conservativo).

As tabelas de K e K_n foram **lidas à mão** das figuras do manual (±0,02 em K, ±0,03 em K_n). A leitura reproduz o
exemplo do manual §9.6: K = 1,46 a e/D = 1,24 e 1,33 a 1,5; apoio do olhal macho 76 800 lbf (manual 77 000), corte
da cavilha 72 460 lbf (72 400), flexão da cavilha 30 040 lbf (30 100). O K_n lido (0,72) fica abaixo do 0,74 do
exemplo. Dimensionamento: cavilha AN mais pequena e espessura em passos de 0,5 mm com D/t ≤ 5, e = 1,5 D,
w = 3 D, garfo de 2 orelhas de t/2 + 0,5 mm (PRESSUPOSTO). Olhal em Al 7075-T6 e cavilha em aço 4130 por omissão.
Carga última = 1,5 × fator de ferragem 1,15 (14 CFR 23.625) × carga limite.

**Ligações avaliadas** (cargas LIMITE das fontes já existentes; partilhas PRESSUPOSTO):

| Ligação | Carga | Olhais |
|---|---|---|
| asa–fuselagem | M_raiz (`structures.beam`, asa em consola) / h (0,9 t/c c_raiz) / 2 longarinas | 8 (2 longarinas × banzo superior/inferior × 2 lados) |
| trem principal / frente | reações de aterragem da viga L1 (23.473) / pernas / 2 | 4 / 2 |
| estabilizador | sustentação de projeto / 4 (contínuo através da fuselagem) | 4 |
| deriva | T_fin (= L_deriva × z_cp, viga L1) / h_raiz / 2 longarinas | 4 |
| booms | M na ligação / diâmetro do boom | 2 por boom |

Quando a cauda está nos booms, as ferragens da cauda na fuselagem não são geradas.

**Berço tubular do motor**: treliça de 8 tubos de aço 4130 entre 4 nós na parede de fogo e 4 apoios do motor
(quadrados de 0,30 D e 0,20 D de meio-lado, comprimento 0,35 D, CG do motor no plano dos apoios — PRESSUPOSTO,
declaráveis), nós articulados, forças por mínimos quadrados do equilíbrio do motor (rigidez igual, PRESSUPOSTO).
Tubos: tração F_tu e compressão por Euler–Johnson (Bruhn C2), K = 1, FS 1,5, de 12,7 × 0,89 mm para cima. Casos:
n_lim vertical; 14 CFR 23.363 lateral 1,33 g com 1 g vertical; 14 CFR 23.361 binário médio P/ω × fator por
n.º de cilindros (23.361(c): 1,33 para ≥ 5, 2/3/4/8 para 4/3/2/1) com 0,75 n_lim (regulamento anterior à emenda
23-64). Sem P/W, rpm ou motor alternativo, ou sem n.º de cilindros declarado, o berço fica **desconhecido**. A tração
do hélice só entra se declarada (`engine_mount.thrust_N`).

| Caso | Asa–fuselagem | Trem principal | Cauda | Booms | Berço do motor | Total ligações |
|---|---|---|---|---|---|---|
| C172 (4 cilindros, só em memória) | 8 × AN16, 13,5 kg, RF 1,01 | 4 × AN5, 0,16 kg | estab. 4 × AN3, deriva 4 × AN4, 0,11 kg | — | 1,39 kg, RF 1,09, passa (binário 2 × 405 N·m) | 15,2 kg |
| UAV 150 kg | 8 × AN8, 1,72 kg | 4 × AN3 | 0,03 kg | — | 0,41 kg, desconhecido (sem binário) | 2,18 kg |
| Twin-boom | 8 × AN9, 2,10 kg | 4 × AN3 | (cauda nos booms) | 2 × 2 × AN3, 0,03 kg | 0,41 kg, desconhecido | 2,57 kg |

Leitura: o C172 tem asa escorada, mas a escora não está modelada no acdt (o caixão da asa também é dimensionado em
consola), por isso as ferragens da raiz são um limite superior: com a escora, o binário na raiz é muito menor. O
berço do motor do C172 (1,4 kg só de tubos) fica abaixo de um berço real, que tem também apoios elásticos, olhais e
soldaduras (não modelados). Nenhuma ferragem falha; os desconhecidos novos são os berços sem binário avaliado.

## 8. Acoplamento `iterar`: massa e CG da estrutura paramétrica no W0 e no balanço (incremento C)

Com `assumptions.structure_layout: {enabled: true, coupling: iterar}`, a etapa de dimensionamento corre um ponto
fixo (`size_with_structure`, por fora dos acoplamentos térmico e de gelo, como estes): dimensionamento →
estrutura paramétrica sobre esse resultado → nova volta com

* **massa**: para cada parte com item no build-up de massas (asa, fuselagem, estabilizador, deriva) um item de
  correção `estrutura_parametrica:<item>` = massa paramétrica − item atual (pode ser negativo); booms e ligações, sem
  item no build-up, entram inteiros. Com a montagem (`assumptions.assembly`), as partes já são itens `asm:<parte>` com
  nomes do utilizador: entra uma correção única (Σ paramétrica − Σ asm) no CG paramétrico (PRESSUPOSTO);
* **CG e inércia**: as estações do balanço (`stability.stations`) do item original e da correção passam para o CG
  paramétrico da parte (`["m", x]`), por isso item + correção têm a massa e o momento da estrutura paramétrica; as
  inércias por soma de componentes (Roskam Parte V) e o balanço operacional usam essas estações.

Pára quando |ΔW0|/W0 < `tol` (10⁻³) ou ao fim de `max_iter` (8) voltas. Exige o build-up de massas (`res.weights`);
sem ele, ou se o dimensionamento não converge, fica «não avaliado» com o motivo. Membros sem massa (desconhecidos)
não entram e ficam listados. Tudo só em memória (o yaml do exemplo não muda; o teste confirma).

| Caso | W0 relatório | W0 iterar | Voltas | Correções na última volta | CG MTOW (x, SM) |
|---|---|---|---|---|---|
| C172 | 1137,8 kg | **1115,9 kg** (−21,9 kg) | 3 | asa −31,4; estab. −1,0; deriva −2,0; fuselagem +7,8; ligações +14,9 kg | 2,193 → 2,297 m; SM 0,10 → 0,11 (crítico passa a ZFW, 0,10) |
| Twin-boom | 167,0 kg | **168,9 kg** (+1,8 kg) | 4 | correção da montagem +0,72 kg | 0,761 → 0,767 m; SM 0,114 |

Leitura: no C172 a asa paramétrica (caixão em consola: revestimentos, almas, nervuras, bordos e não-ótimo) pesa
31 kg menos do que a Raymer 15.46, que inclui superfícies de comando, flaps, ferragens e a escora; a fuselagem
paramétrica ainda não tem piso, portas e janelas (incremento D). O W0 acoplado é por isso um resultado de
**âmbito incompleto**, não uma redução de massa a aplicar. Quando o âmbito da estrutura paramétrica cobrir esses
itens, a comparação fica direta. O posicionamento da asa no estágio de estabilidade reajusta-se ao novo CG (a
margem estática alvo mantém-se no caso crítico).

## 9. Detalhe da fuselagem: piso, aberturas, secções não circulares e pressurização (incremento D)

Tudo em `structure_layout.fuselage` (só em memória nos estudos) e em `core/structures/frames.py`.

**Secção não circular** — `section: {w_m, h_m, n_exp}` dá a superelipse |y/a|ⁿ + |z/b|ⁿ = 1 na estação máxima,
escalada com R(x) da viga L1. `section_points` coloca os booms em perímetro igual; I = Σ B z², corte
S/(π R_eq) com R_eq = P/(2π) (exato no círculo, PRESSUPOSTO fora dele) + Bredt T/(2A) (Megson cap. 18), J = 4A²t/P
no modelo de vigas e massa do revestimento pelo perímetro real. As cavernas são analisadas como anel de raio
√(w h)/2 (PRESSUPOSTO; Niu 1988 cap. 11 trata a flexão do anel não circular à parte).

**Aberturas** — `cutouts: [{id, x0_m|x0_frac, x1_m|x1_frac, theta_deg, width_deg}]` (θ a partir do topo, +y).
Nas estações dentro do intervalo os reforçadores e o painel do arco saem da idealização (I menor) e o fluxo de
corte sobe P/(P − L_aberta) (redistribuição pelos painéis restantes, PRESSUPOSTO). As duas cavernas de bordo passam
a fortes com o par de forças tangenciais F = q (x1 − x0)/2 nos bordos do arco (moldura de corte, Niu 1988 cap. 13 —
PRESSUPOSTO) e há duas soleiras (Z, Euler–Johnson + Gerard, comprimento x1 − x0) que levam metade da força última dos
reforçadores e painel removidos à tensão máxima da estação, prolongadas um passo de cavernas para cada lado.

**Piso** — `floor: {enabled: auto|true|false, x0_m, x1_m, z_frac, q_Pa}`; auto liga-o com tripulação+carga > 0 e
D ≥ 0,9 m (cabine habitável — PRESSUPOSTO). Por omissão vai da parede de fogo a 0,5 L, a 0,6 R abaixo do eixo.
Carga LIMITE uniforme q = (tripulação + carga) g n_lim / área (ou `q_Pa` declarada), última × 1,5. Vigas
transversais em cada caverna, simplesmente apoiadas (M = w L²/8, V = w L/2, perfil C de largura 0,4 h, banzo
comprimido com crippling de Gerard, alma τ = V/(h t)); painel entre vigas como placa retangular simplesmente
apoiada σ = β q b²/t² (Roark & Young 7.ª ed., Tab. 11.4 caso 1a; β de 0,2874 a a/b = 1 até 0,75), espessura em
passos de 0,1 mm. As cargas de emergência dos assentos (9 g), as ancoragens e as calhas ficam desconhecidas.

**Pressurização** — `pressure_Pa` (diferencial LIMITE) e `pressure_x_m` (zona; omissão: corpo inteiro). Pele:
aro σ = p R/t com 1,33 p (14 CFR 25.365(d), pressão sozinha) × 1,5; reforçadores: tração p A/ΣB somada à tração de
flexão. Cavernas: quinhão do aro por compatibilidade de extensão N_f = 1,33 p R b A_f/(A_f + b t) (derivado,
PRESSUPOSTO), como caso «pressurizacao» do anel. Em secção não circular a flexão do anel/painel sob pressão não é
modelada → desconhecido.

**Números** (estudo, `applied: false`):

| Caso | Fuselagem paramétrica | Detalhe |
|---|---|---|
| C172 (piso por omissão) | 125,6 kg (106,0 sem piso) | piso 2,70 m², q_lim 3,8 kPa, 15,7 kg (painel maciço 1,8 mm — limite superior face a sandwich) |
| C172 + 2 portas + 25 kPa hipotéticos | 129,6 kg | soleiras 4 × 0,68 kg (RF 1,02); aro RF 12 na pele dimensionada pela encurvadura |
| Twin-boom, casulo superelíptico 0,40 × 0,30 m (n = 3), piso 3 kPa, alçapão | 13,3 kg (12,2) | piso 1,4 kg; soleiras RF 2,35 |

Com o piso, o C172 `iterar` passa a 1137,8 → 1153,9 kg (a área do piso é integrada no intervalo declarado, contínua
com o comprimento da fuselagem — com a área entre cavernas o ponto fixo oscilava entre 1150 e 1153 kg).

## 10. Render 3-D da estrutura (`structure_render.py`)

`render_layout(res.structure_layout, "aviao.png", color_by="kind" | "RF")` desenha, fora do ecrã (matplotlib
Agg), o que a tabela de membros e a nova chave `geometry` do layout descrevem: revestimento exterior
semitransparente (fuselagem, booms, plantas das superfícies), longarinas e nervuras dos caixões (passo do
dimensionamento: `box.rib_pitch` ou 0,6 CMA), cavernas (fortes a vermelho e mais grossas), anteparas, reforçadores
e longarinas da fuselagem, piso (vigas e painel), soleiras das aberturas, ferragens e berço do motor. Com
`color_by="RF"` cada peça toma a cor do RF_min do seu membro (vermelho RF = 1, verde RF ≥ 3, cinzento =
desconhecido). Linha de comandos: `python -m acdt.domains.aircraft.structure_render exemplo.yaml saida.png [--rf]`.
No estudo, os casos com `render: true` gravam `<caso>_estrutura_3d.png` e `<caso>_estrutura_3d_rf.png` em
`examples/output/estrutura_parametrica/` (C172 com portas e twin-boom com casulo superelíptico).

O desenho mostra as simplificações do layout tal como estão: superfícies no plano z0 do registo (a asa alta do C172
aparece no eixo; diedro não modelado), empenagem do twin-boom ao centro (uma só deriva — ver pendentes da §6) e
longarinas e nervuras sem a geometria das mesas.

## 11. Próximos incrementos

1. ~~Fuselagem: piso, aberturas, secções não circulares, pressurização~~ — feito (§9). Falta: longarinas reais
   (flexão lateral e torção), alma das anteparas sob cargas concentradas, cantos das janelas, assentos 9 g, flexão
   do anel não circular.
2. ~~Empenagens pelo caminho `wingbox` e no modelo de vigas; booms ligados à geometria de `assembly`~~ — feito
   (§6). Falta: binário de reação dos rotores, duas derivas separadas no twin-boom.
3. ~~Apoios e ferragens: berço do motor, olhais e cavilhas das ligações~~ — feito (§7). Falta: olhais sob carga
   transversal/oblíqua (AFFDL-TR-69-42 Fig. 9-8, interação 1,6), casquilhos, juntas aparafusadas em tração
   (parafusos em tração e corte combinados), escora da asa, apoios elásticos do motor.
4. ~~Acoplamento `iterar`~~ — feito (§8). Falta: âmbito completo (superfícies de comando, piso, portas) antes de
   ler o W0 acoplado como estimativa; estações por parte no modo montagem.
5. Estimativa de flutter com o modelo de vigas (modos da asa + massas concentradas) ligada a `aeroelasticity.py`.
6. Exportação para CalculiX por subprocesso (via Build, no PC do João) e comparação viga vs casca.
