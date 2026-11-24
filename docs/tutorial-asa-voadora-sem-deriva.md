# Tutorial — asa voadora sem superfícies verticais (split ailerons + SAS)

Isto corre dentro de `acdt size`. Não há comando novo nem ferramenta MCP nova. Tudo é opt-in: um desenho
sem `yaw_control` fica exatamente como estava.

## 1. Ligar

Em `assumptions.assembly.options.flying_wing` (ver `examples/heavy/uav150_flying_wing_tailless.yaml`):

```yaml
flying_wing:
  yaw_control: split_aileron   # sem deriva nem winglets no desenho
  sas: true                    # por omissão true num UAV, false nos outros
  split_aileron: {eta_inner: 0.45, eta_outer: 0.98, cf_c: 0.40, delta_max_deg: 60, rate_max_deg_s: 200}
  elevon: {eta_inner: 0.20, eta_outer: 0.45, cf_c: 0.25, max_deg: 25}
  turbulence: moderate         # light | moderate | severe (Dryden, MIL-F-8785C)
  # crosswind_kt: 12           # opcional; por omissão 0,2 V_S0 (14 CFR 23.233(a))
  clmax: trimmed               # CLmax de dimensionamento = C_L máximo equilibrado do desenho (sem flap)
```

e, para o equilíbrio de picada (secção 5 abaixo):

```yaml
assumptions:
  aero:
    flap: {kind: none}         # a asa sem deriva do exemplo não tem flap
  assembly:
    options:
      static_margin_min: 0.02          # limite inferior de NACA TR-796
      useful_load_at: empty_cg         # carga/combustível sem posição → CG das massas fixas
      balance: {static_margin: 0.05}   # dentro da banda 0,02–0,08 de NACA TR-796
```

```
acdt size examples/heavy/uav150_flying_wing_tailless.yaml -o out/fw_tailless
```

Os resultados ficam em `res.dynamics["tailless"]` (e no registo da montagem), com linhas `hq:*` novas.

## 2. O que o modelo faz

1. **Arrasto de um split aileron aberto** (McCormick 1995, Eq. 3.45): ΔC_D = K_f (c_f/c)^1.38 (S_f/S) sin²δ, com
   K_f = 1,7 por folha. Abrir as duas folhas de um lado dá guinada ΔC_n = ΔC_D·ȳ_f/b. PRESSUPOSTO: as duas
   folhas somam. O **AVL é invíscido**: não vê este arrasto, só a célula nua e as elevons.
2. **Efeitos secundários**: com folhas simétricas, ΔC_l ≈ ΔC_m ≈ 0 em escoamento colado (Löchert et al. 2019,
   MULDICON, α ≤ 10°, |β| ≤ 10°). Fora desse envelope aparece um aviso e o efeito fica unassessed. O momento
   de picada do arrasto fora da altura do CG é calculado.
3. **Casos de dimensionamento**, cada um com a deflexão e a fração de envergadura necessárias:
   * vento cruzado em derrapagem estabilizada a 1,1 V_S0 (Roskam AFD I §4.2; 14 CFR 23.233(a));
   * coordenação contra a guinada adversa da elevon (MIL-F-8785C Tabela IXa);
   * turbulência lateral Dryden a 50 ft (MIL-F-8785C), que é o caso de autoridade do SAS (3σ).
4. **SAS** u = k_β β − k_r r̂: procura os ganhos mais pequenos que dão Nível 1 no rolamento holandês e na
   espiral (MIL-F-8785C Tabelas VI e VIII; Cat. C na aproximação). O `hq` só passa se a autoridade e a taxa
   do servo chegarem. A célula **nua** é sempre reportada.

5. **Atuadores** (10 nov 2026). O momento de charneira de cada folha do split vem de NACA TN 690 (Figs. 17–18,
   |C_hf| até 0,64 a 60°). O da elevon vem do AVL (`HM`). Ambos seguem o calendário de 14 CFR 23.455(a)(2):
   deflexão total em V_A e 1/3 em V_D. O servo escolhido é o mais leve do `actuators.catalog` que segura o
   binário com o fator de segurança e dá a taxa exigida pelo SAS. Os dados vêm dos datasheets da Volz, no YAML.
   Com `max_per_surface: 2` podem trabalhar dois servos em paralelo. A massa entra no orçamento de componentes.
6. **Atraso do atuador no SAS**. Sem dados do servo, o modelo usa um atraso de 0,10 s, que é o limite do
   Nível 1 de MIL-F-8785C 3.5.3 (PRESSUPOSTO). O SAS é dimensionado já com esse atraso, e a margem de atraso
   aparece em `hq:sas_time_delay`.
7. **Rajada lateral** (`hq:lateral_gust`). É uma 1−cos de 50 ft/s EAS em V_C, com 25 c̄ de comprimento
   (14 CFR 23.443/23.333(c)). O caso é separado da turbulência e tem bank hold pela elevon.
8. **Equilíbrio de picada** (`hq:pitch_trim_tailless`). A elevon simétrica é equilibrada em cada caso de massa,
   e o resultado inclui o C_L máximo equilibrado. A mensagem também dá a margem estática por caso face à
   banda 0,02–0,08 de NACA TR-796, o δe de cruzeiro por caso e a torção desenhada face à de Panknin.
9. **Vento cruzado que falha** (`asm:crosswind_options`). Para cada opção, o modelo diz se fecha e a que custo:
   split maior, elevon maior, aproximação mais rápida, crab/decrab e tração diferencial.
10. **6-DOF**: `acdt simulate exemplo.yaml missão.yaml --fidelity 6dof [--jsbsim]`. Com asa sem deriva faz o
    ensaio lateral, com rajada, célula nua e SAS, em cada caso de massa que equilibra o cruzeiro. Voa também a
    missão (caso `cheio`): derrapagem pelo split, decrab e cargas laterais no toque (14 CFR 23.485).

## 3. Números do exemplo (UAV 150 kg, depois da correção de picada)

| item | valor |
|---|---|
| W0 / S | 138,3 kg / 2,905 m² (converge, viável; antes da correção: 157,0 kg / 2,124 m²); com o trem de 12 nov: 150,4 kg / 3,186 m² |
| CLmax de dimensionamento | 1,128 = C_L máximo equilibrado (caso 'carga'), sem flap; antes 1,75 com um flap que não existe |
| V_S0 / aproximação | iguais (o requisito de V_S mantém-se; a asa cresce); aproximação 1,1 V_S0 = 28,6 m/s |
| margem estática (vazio / carga / combustível / cheio) | 0,051 / 0,063 / 0,051 / 0,061 (Torenbeek), banda TR-796 0,02–0,08 |
| δe de cruzeiro | +7,6° / +1,7° / +5,0° / −0,9° (limite ±25°) |
| torção | −10° desenhada; Panknin −8,1° (C_L 0,51, σ 0,073) |
| equilíbrio de picada | **passa** |
| rolamento holandês nu (cruzeiro) | instável → acima do Nível 3 (informativo) |
| com SAS (k_β 0, k_r 0,075) e atraso de 0,10 s | ζ 0,113, ω 2,29 rad/s; cruzeiro ζ 0,118, aproximação ζ 0,088 → Nível 1; margem de atraso 0,18 s |
| autoridade em turbulência moderada | 3σ ΔC_n 0,0037 vs capacidade 0,0215; taxa 76 °/s vs 96 °/s |
| charneira | split 33,5 N·m por folha → 2× Volz DA 30 (5,04 kg no total); elevon 6,0 N·m → 2× DA 26 por lado (1,08 kg); taxa exigida da elevon 100 °/s ≤ 121 °/s → `hq:actuators` passa |
| packaging no CG | combustível 31,6 L (com 2 % de expansão) cabe em volume bruto a ±0,075 m do CG vazio (±0,39 m só no corpo central); carga de 27 kg precisa de 1,15 kg/L a ±0,12 m → `None` (necessário, não suficiente) |
| C_m dos corpos (sensibilidade) | δe de cruzeiro +11,4/+6,8/+9,8/+5,1°; C_L equilibrado ≥ 1,68 |
| coordenação | split 13,5° → passa |
| vento cruzado 10,1 kt | **passa**: split 40,6°, elevon −17,6°; máximo 14,5 kt |
| rajada lateral 17,7 m/s TAS | amortece com SAS (split 10,8°, elevon 14,7°), mas toca no limite de taxa durante 0,5 % do tempo → **falha** (critério estrito). Fecham: servo ×5 (478 °/s) ou pré-deflexão δ0 = 2° (ΔC_D +0,7 % de C_D0, fora do polar) |
| período curto / fugóide | ζ 0,335 Nível 1 / célula nua ζ 0,039 **Nível 2**; com manutenção de atitude (piloto automático, Beard & McLain 6.4.1) raízes reais −0,54/−0,17 → **Nível 1** |
| 6-DOF (4 casos) | trim α 6,6–10,9°, δe +9,4…+0,3°; o SAS reduz o β final em todos (ex.: 'cheio' 2,3° nu → 0,09°) |
| JSBSim vs 6-DOF (doublet 3 %, 8 s) | NRMS β carga/combustível/cheio 0,019–0,020; vazio 0,119 (célula nua instável, duplica em 11,6 s; a sensibilidade do próprio modelo dá 0,08). Causas corrigidas: δe no arrasto induzido, latitude do IC, guinada do AERORP e −D·sinβ |

A tabela acima é de 10–11 nov 2026. Os valores do exemplo no main a 18 nov 2026 (W0 149,7 kg, trem a 19°)
estão na tabela seguinte.

| verificação (18 nov 2026) | resultado |
|---|---|
| rajada lateral, modelo linear (`hq:lateral_gust`) | **passa** com δ0 = 2°: split 9,9°, 49 °/s, sem limite de taxa |
| rajada lateral, 6-DOF não linear (`lateral_gust_6dof`, mesmo critério estrito) | vazio/carga/combustível passam (pico 43/73/53 °/s); **cheio falha**: toca no limite de taxa em 0,54 % do tempo; sem limite pediria 100 °/s contra 84 °/s na superfície (×1,20). Reportado, nada alterado no desenho |
| fugóide | célula nua ζ 0,042 (no limite do Nível 1, ζ ≥ 0,04, MIL-F-8785C 3.2.1.2); com manutenção de atitude ζ 0,96 → **Nível 1** |
| taxa da elevon | exigida 99 °/s (bank hold na rajada) ≤ 117 °/s do Volz DA 30 na superfície → passa |
| JSBSim vs 6-DOF (doublet 3 %, 8 s) | NRMS β carga/combustível/cheio 0,022/0,021/0,024; vazio 0,055 (sensibilidade própria 0,037) |
| C_m0 dos corpos (Multhopp, sensibilidade) | +0,0101 (α_0L,f +3,9°, finura 8,8, k2−k1 0,93); δe de cruzeiro passaria de +11,4/+6,8/+9,9/+5,3° para +15,8/+11,2/+14,2/+9,6°, todos equilibráveis |
| decrab na missão 6-DOF | crab −9,0° a 30 m → resíduo −0,3°, deriva 0,35 m/s; cargas 23.485 0,60×/0,62× → passa |

### Como se chegou aqui (estudo, 10 nov 2026)

Antes da correção, só o caso 'vazio' equilibrava. Os casos com carga tinham margem estática 0,34–0,49 e
pediam δe −92…−168°. A carga e o combustível sem posição iam para o centróide do corpo, longe do CG.
Foram estudadas três alavancas:

| opção | resultado |
|---|---|
| só elevon maior (mesmo CG) | não fecha: δe −166…−354° nos casos com carga; C_mδe quase não cresce com c_f/c numa elevon interior em flecha |
| CG: carga no CG das massas fixas + SM 0,05 (TR-796), torção −4° | W0 151,0 kg, CLmax equilibrado 0,86 |
| idem, torção −8° | W0 146,2 kg, CLmax 1,06 |
| **idem, torção −10° (escolhida)** | **W0 146,0 kg, CLmax 1,15** (com os servos antigos; com os servos escolhidos, 138,3 kg) |
| idem, −10° + elevon desde η 0,10 | W0 146,1 kg, CLmax 1,20 (sem ganho; mais elevon a mover) |
| idem, torção −12° | diverge (W0 289 kg; K sobe) |

A opção −10° é a de menor W0 e não mexe na elevon. A área da elevon, sozinha, não resolve: o que
manda é o CG (margem estática). Depois disso, a torção dá o C_m0 positivo.

Fontes: NACA TR-796 (Donlan 1944, banda de margem estática; com uma margem grande, a deflexão de equilíbrio
é grande); Panknin 1989 (via b2streamlines); Raymer 2018 Sec. 15.1; Etkin & Reid 1996 Sec. 2.4; Phillips &
Alley 2007.

## 4. Limites

* A carga e o combustível ficam no CG das massas fixas (`useful_load_at: empty_cg`). Verifica-se só o volume
  bruto à volta desse CG (`asm:useful_load_packaging`); o packaging fino (estrutura, sistemas) e o volume da
  carga ficam **unassessed**. O C_m dos corpos (Torenbeek) entra no equilíbrio principal desde 12 nov; o C_m0
  dos corpos é 0 (PRESSUPOSTO) por omissão, e a estimativa de Multhopp é sempre reportada
  (`flying_wing.body_cm0: multhopp` usa-a no equilíbrio principal; 18 nov 2026). A torção foi escolhida
  pelo estudo, não por um otimizador.
* A pré-deflexão de 2° do split é agora opção de projeto e o seu arrasto (ΔC_D0 0,000202, McCormick Eq. 3.45)
  está no polar: W0 138,6 kg, e a rajada lateral passa.
* A missão 6-DOF corre (`acdt simulate examples/heavy/uav150_flying_wing_tailless.yaml examples/simulation/uav150_tailless_crosswind.yaml --fidelity 6dof`).
  O decrab deixa −0,2° de crab no toque.
* **Trem (12 nov 2026)**. Numa asa sem cauda a elevon não consegue levantar a roda do nariz: a força para baixo
  da elevon anula quase todo o momento em torno das rodas. Com o corpo nivelado não há posição do trem que
  cumpra o tip-back e a rotação (Sadraey 2012 Sec. 9.6.2). Por isso o exemplo fica pousado já na atitude de
  descolagem (`gear.ground_attitude_deg: 19`, perna do nariz 0,35 m mais comprida) e descola sem rodar:
  - δe −17,7°, V_LOF 1,15 V_S, rolagem 293 m (massa pontual) / 299 m (6-DOF em ar calmo) contra 300 m;
    329 m com vento cruzado de 5,2 m/s;
  - nariz 14–15 % (Raymer 8–15 %), meia-bitola 0,554 m;
  - cargas laterais no toque 0,50×/0,58× dos limites de 14 CFR 23.485 (dentro);
  - W0 sobe para 150,4 kg (pernas mais compridas no peso do trem de Raymer).
  Com vento cruzado as pontas ainda tocam (até ~190 N): alargar a bitola tira os toques mas põe a carga
  lateral para fora a ~1,5× do limite. Fica reportado; patins de ponta ou mais rolamento no solo ficam por
  avaliar. Catapulta e aterragem de ventre têm agora uma verificação de 1.ª ordem opt-in
  (`assumptions.launch_recovery`, 14 nov 2026). Com 8 g, o curso é de 5,2 m; no ventre, a hélice propulsora
  fica 0,13 m abaixo da linha do ventre, por isso é preciso pará-la e alinhá-la ou dobrá-la (ver HANDOFF).
* **Corrida com vento cruzado e arrasto do trem (16 nov 2026)**. Quando a corrida 6-DOF passa os 300 m, a missão
  junta `takeoff_options` (e `takeoff_options.md`): o que cada opção exige e se fecha. No exemplo (Linux,
  325 m com vento cruzado, 296 m em ar calmo) fecham um vento de frente ≥ 1,35 m/s (pista a ≤ 75° do vento),
  tração ×1,066, S ×1,079 ou −4,9 kg; a atitude não fecha e a catapulta precisa do bloco `launch_recovery`.
  Nada é aplicado ao exemplo. `gear.apply_scaled_drag: true` leva a área do trem escalada pelas pernas ao polar
  (+0,0216 m², ΔC_D0 +0,0068): opt-in, não ligado no exemplo (ver HANDOFF).
* **Folga traseira dinâmica (14 nov 2026)**. O 6-DOF mede, na descolagem e na aterragem, a folga ao solo do
  ponto traseiro que toca primeiro na rotação (hélice/bordo de fuga, `aft_strike`), com a compressão do trem
  e a atitude reais (Sadraey 2012 Sec. 9.5.1.3, Eq. 9.2–9.3). No exemplo: α_C 45,2° com o trem descomprimido,
  24–25,6° com a compressão máxima do toque (0,15 m, mola PRESSUPOSTO); θ máximo perto do solo 22,6° na
  descolagem; folga mínima **0,062 m** (descolagem) e 0,100 m (aterragem); sem contacto em 9 corridas com o
  vento perturbado. Passa, com margem pequena (~2–3° de atitude). Opções reportadas: limite de atitude no
  piloto automático, extensão das pernas e para-choques de cauda por energia (N_des ≈ 4,9 kN a 1,17 m/s).
* A longarina traseira do caixão (Fase 5/6, `acdt wingbox` / `wingbox6`) tem de ficar à frente da
  charneira mais avançada. No exemplo o split aileron tem cf/c = 0,40 (charneira a 0,60 c) e a omissão
  da Fase 3 (0,65 c) ficava atrás; o estudo recua a longarina (folga 0,03 c). O exemplo liga
  `assumptions.structures.wingbox.hold_section`, para o otimizador não baixar a torção de Panknin de
  −10° nem o t/c do desenho. O estudo de 12 nov fixou 0,13/0,10. Em 14 nov o desenho passou ao t/c
  do yaml, 0,15/0,12; as massas do caixão abaixo são as de 12 nov e não foram recalculadas. Com a secção fixa, a Fase 6 (viga
  calibrada) dá caixão 6,18 → 5,47 kg, longarinas 0,30/0,55 c (0,05 c à frente do split, 0,20 c à
  frente da elevon), 6 nervuras/semi-asa (passo 0,40 m), peles no calibre mínimo 0,5 mm e núcleo de
  5,6 mm na raiz. Não há inversão na elevon (V_R = ∞; eficácia de rolamento η = 1,09 a 1,2 V_D,
  Wright & Cooper Cap. 9; BAH Cap. 8; Glauert 1926). O canal de guinada do split (McCormick Eq. 3.45)
  não inverte por este mecanismo e fica unassessed. Sem divergência nem flutter até 4 V_D. O factor de
  reserva de encurvadura é 1,00 nas peles (interacção Allen/Zenkert) e nas nervuras interiores; 1,36
  na nervura da ponta (bitola mínima). Sem `hold_section`, o ótimo livre tinha baixado a torção para
  −2,1° e o t/c de raiz para 0,104, com o caixão a 5,57 kg — essa geometria já não fecha o picado.
* Ficam por avaliar (unassessed): o curso dos servos sem dado do fabricante (só o
  DA 26 tem ±45°); a rigidez; o C_h da folha superior e a c_f/c = 0,40 (fora dos 0,15–0,25c ensaiados); a
  estrutura do trem para as cargas laterais; ΔC_D medido para o perfil (o K_f pode ser
  substituído por um valor medido).
* Na aproximação, o trim AVL dá α ≈ 12–20° conforme o caso (antes ≈ 22°). Continua fora do envelope de Löchert (α ≤ 10°), por isso os avisos se mantêm.
* **RANS de um α (13 nov 2026)**. Três malhas da meia asa, controlos alinhados, α = 9,52° do cruzeiro AVL.
  O CL do SU2 fica em 0,87 nas três; o AVL dá 0,503. A razão 1,74 está fora de [0,7, 1,5] e o momento tem
  o sinal oposto ao Cmtot do AVL. O factor não entra no L1/L2. Este ponto não substitui o polar do AVL nem
  avalia o split ou a charneira. Números em `examples/output/uav150_flying_wing_tailless_hifi_win/h1_wing_gci.json`.
  Esse loft tinha a torção com o sinal trocado. Em 14 nov 2026 a ponta passou a washout e a malha grossa,
  no mesmo α, deu CL 0,416 / 0,503 = 0,83 e CMy com o mesmo sinal do AVL. A razão fica dentro da banda e
  o factor continua por aplicar. Números em `h1_twist_diagnostico.json`.
  Antes de qualquer RANS de asa, `verify_wing_rans_geometry` compara a malha com o AVL e com o caso
  SU2 (incidência, eixos, Sref/Bref, origem do momento). A falha bloqueia. Nessa etapa não houve
  corrida e não entrou factor. As malhas do GCI de 13 nov continuam inválidas.
* **Espessura (14 nov 2026)**. O loft e o AVL passam a usar o t/c do yaml, 0,15/0,12, na espessura
  NACA simétrica. A curvatura do 4415 (4 % da corda a 0,4 c) não é construída. Com a mesma planta, a
  mesma torção e o mesmo cabeçalho, a α = 9,52° dá CLtot 0,50293 e Cmtot 0,02886 tanto em 0013/0010
  como em 0015/0012. ΔCL = 0 e ΔCm = 0 no dígito impresso do AVL. CLAF não foi escrito, por isso este
  zero não avalia a curvatura nem a viscosidade da espessura. Não entra factor. Números em
  `h1_seccao_avl.json`.
* **GCI v2 (15 nov 2026)**. As três malhas foram refeitas com esta espessura e com a torção certa.
  No α de cruzeiro o CL fino é 0,419 e o do AVL 0,503 (razão 0,83); o CMy tem o mesmo sinal e a
  razão 1,10. Os dois caem dentro de [0,7, 1,5], mas a série de malha do CL e do CMy oscila e o
  factor não entra. O CD desce de 0,031 na malha grossa para 0,025 na fina; o GCI fino é 22 % e
  esse CD não é o CDtot do AVL. A malha média chegou a rms −8. A grossa ficou em −7,23 e a fina
  em −7,97. Números em `h1_wing_gci_v2.json`. A linha média do 4415 passou a existir como
  opt-in (`with_naca4_mean_line`, Abbott & von Doenhoff 1959, Eq. 6.4–6.6). O exemplo continua
  com a espessura simétrica. Na malha grossa, com esse opt-in e no mesmo α, o SU2 deu CL 0,730
  e CMy −0,073 contra o AVL 4415/4412 (0,814 e −0,080). As razões 0,897 e 0,917 ficam na banda e
  o factor não entra: é uma malha e um α. Números em `h1_curvatura_grossa.json`.
  Na grossa simétrica, a polar vai de −2° a 24°. O CLmax com os controlos alinhados é 1,059 a 20°
  e o CD0 viscoso, já sem o arrasto induzido do AVL, é 0,0198. Nenhum factor entra: uma malha, sem GCI,
  e o CLmax equilibrado do L1 (1,118) não é esta grandeza. Números em `h1_polar_grossa.json`.
  Na mesma grossa, a elevon selada (charneira a 0,75c, η 0,20–0,45) correu a α = 9,52° em δ −10°,
  +10° e −25°. A split fica por avaliar: a fenda não cabe na extrusão fechada. O RANS deu CL 0,319,
  0,513 e 0,173, e Ch −0,000535, −0,001614 e +0,000438. O AVL com as estações da elevon e a torção
  linear em graus dá CL 0,416 a δ = 0, ao lado do RANS limpo; o cartão de duas secções (0,503)
  corresponde a um bordo de fuga recto. δ positivo sobe o CL nos dois. O momento de charneira a −10°
  não tem o mesmo sinal que o HM do AVL por lado. Nenhum factor entra: uma malha, um α, sem GCI.
  Os atuadores não mudam. Números em `h1_controlos_grossa.json`.
* **CalculiX (18 nov 2026)**. O caixão do dimensionamento actual, t/c 0,15/0,12, pesa 6,429 kg.
  A flecha de ponta do FEM é 0,05786 m e a da viga 0,03301 m (k_EI = 0,571, dentro da banda e por
  aplicar: o exemplo não liga o grupo). A torção muda de sinal (−0,483° no FEM, +0,430° na viga) e
  k_GJ fica inválido. O primeiro factor de encurvadura linear à carga última é 0,854. Os 5,47 kg e o
  RF 1,00 da pele são o estudo de 12 nov, com outro t/c, e não entram nesta comparação. O DLM cruza
  a 285 m/s; o modelo de faixas não cruza. Não há factor de flutter. A inversão por DLM fica por
  avaliar, porque a grelha não tem flap. O NLGEOM do caixão não convergiu e o Riks não foi escrito.
  Nenhum factor entra no exemplo. Números em `h2_calculix.json`.
* **pyGeo (18 nov 2026)**. O loft entra numa caixa FFD e o pyGeo, dentro do contentor MDO Lab,
  devolve os mesmos 537 pontos (desvio 9,8×10⁻¹³ m) quando não há variável de projecto. Não houve
  solução ADflow nem TACS de cruzeiro, por isso não há comparação com o CL da grossa nem com a
  flecha do CalculiX. Nenhum factor entra. Números em `h3_mphys.json`.
* **RCS (18 nov 2026)**. O mesmo loft, com a torção de ponta −10° e o bordo de fuga acima do bordo
  de ataque, foi avaliado em óptica física a 10 GHz. Com uma reflexão a média no sector frontal é
  −10,03 dBsm. Com duas, passa a −7,49 dBsm em VV e −9,73 dBsm em HH. O máximo fica perto de 8 dBsm.
  A malha tem 192 facetas e uma baía em envergadura; não é uma convergência. Fuselagem, derivas,
  trem, hélice e a deflexão dos comandos ficam por avaliar. A onda completa não correu. Nenhum
  factor entra. Números em `h6_rcs_bounces2.json`.
* **OpenVSP (18 nov 2026)**. O mesmo loft, com a torção de ponta −10° no bordo de ataque e t/c 0,15/0,12, foi exportado pelo OpenVSP 3.48.2 do contentor. O Windows não tem OpenVSP. O VSPAERO de superfície fina, no α do AVL, dá CL 0,494 contra 0,503 e CDi 0,0143 contra o CDff 0,0145. O momento é 0,042 contra 0,029, com o mesmo sinal. A malha e as cinco iterações de esteira não são as do AVL. Nenhum factor entra. Números em `h7_openvsp.json`.


## 5. Decisão da rajada lateral no caso «cheio» (23 nov 2026, estudo `applied: false`)

No 6-DOF não linear, o caso `cheio` falha a rajada lateral de 14 CFR 23.443 pelo critério estrito de
`hq:lateral_gust`: sem saturação, sem limite de taxa e β amortecido. O limite de taxa é tocado em 0,54 % do tempo, e
sem limite o pico seria 99,9 °/s contra 83,5 °/s na superfície (2× Volz DA 30 por folha). O estudo
`examples/studies/rajada_cheio/` quantifica as três opções com as ferramentas que já existem: `lateral_test`,
`select_servo` com o catálogo Volz do exemplo, `actuator_dynamics` (MIL-F-8785C 3.5.3), autoridade 3σ em turbulência e
o arrasto da pré-deflexão (McCormick Eq. 3.45). **Nada é aplicado**: o yaml do exemplo e os valores por omissão
ficam iguais. Resultados em `examples/output/rajada_cheio/rajada_cheio.json`. A escolha é do João.

| Opção (menor que passa) | `cheio` | 4 casos | Margem de taxa mín. (disponível / pico) | Massa dos servos do split | Arrasto (ΔC_D0 / C_D0) | Rolamento holandês cruzeiro / aprox. | Margem de atraso Nível 1 |
|---|---|---|---|---|---|---|---|
| Base: 83,5 °/s, δ0 2°, k_r 0,075 | **falha** (0,54 % em limite; pede 99,9 °/s) | — | — | 5,04 kg (8× DA 30) | 0,74 % | Nível 1 / 1 (ζ 0,149) | 0,234 s |
| (a) servo 2× Volz DA 30-HT por folha, 111,4 °/s | passa | passa | 1,115 (`cheio`) | 8,80 kg (+3,76 kg, +2,5 % do W0) | 0,74 % (igual) | igual | igual (0,234 s) |
| (b) pré-deflexão δ0 = 5,5° | passa | passa | 1,032 (`cheio`) | 5,04 kg | 5,61 % | igual | igual |
| (b') δ0 = 6° | passa | não corrido | 1,127 (`cheio`) | 5,04 kg | 6,67 % | igual | igual |
| (c) k_r × 0,75 = 0,0563 | passa | passa | 1,031 (`cheio`) | 5,04 kg | 0,74 % | Nível 1 / 1 (ζ 0,105) | 0,150 s |

Pormenores:

* **(a) Servo mais rápido.** 100 e 110 °/s passam com 2× DA 30-HT por folha (G que dá 111,4 °/s na superfície). A
  partir de 120 °/s o catálogo só tem o DA 58-D (22,4 kg nas 4 folhas). A potência mecânica por folha à taxa exigida,
  P = FoS·|H_op|·ω, sobe de 25,3 W (83,5 °/s) para 30,3 W (100 °/s). A potência elétrica fica **desconhecida**,
  porque o datasheet não dá rendimento. O modelo linear do SAS não depende da taxa, por isso o Nível e a margem de
  atraso não mudam. O W0 não foi redimensionado com a massa extra.
* **(b) Pré-deflexão maior.** δ0 = 3, 4 e 5° continuam a tocar o limite (0,04 % do tempo; pedem 88,8–89,5 °/s).
  5,5° passa, com 3 % de margem; 6° dá 12,7 %; 8° dá 50 % mas custa 11,8 % do C_D0. A capacidade de guinada fica
  igual (2δ0 ≤ δ_max = 60°). O arrasto entraria no polar de dimensionamento, e o W0 e o combustível não foram
  redimensionados.
* **(c) Outros ganhos.** k_β do exemplo é 0, por isso só k_r conta. A janela é estreita e não monótona: k_r × 0,7 e
  × 0,75 passam; × 0,8, × 0,9 e × 1,5 voltam a tocar o limite; × 0,5 e × 0,6 passam a rajada mas o rolamento
  holandês desce para o Nível 2 (falha). Com × 0,75 a margem de atraso cai de 0,234 para 0,150 s (o projeto usa
  0,10 s, porque a Volz não dá largura de banda) e a margem de taxa é de 3 %. A autoridade 3σ em turbulência cumpre
  em todas as variantes de ganho (ΔC_n 0,0024–0,0048 contra a capacidade de 0,0215).

**Recomendação (só recomendação; a decisão fica com o João):** a opção (a). É a única que passa os 4 casos com uma
margem de taxa de dois dígitos (11,5 %) sem mexer no SAS nem no arrasto. Custa +3,76 kg de servos (≈ 2,5 % do W0),
que obrigam a redimensionar e a atualizar o orçamento de massa. As opções (b) e (c) passam com margens de ~3 %. A (c)
depende do atraso real do atuador, que é desconhecido, e de uma janela de ganhos não monótona. A (b) com 6° é a
alternativa sem massa extra, a ~6,7 % de C_D0 de arrasto.


### 5.1 Opção (a) escolhida: redimensionamento com 2× Volz DA 30-HT por folha (24 nov 2026, `applied: false`)

O João escolheu a opção (a). O estudo `examples/studies/rajada_cheio/estudo_opcao_a.py` corre o mesmo código duas
vezes: com o exemplo tal como está (base) e com os `fixed` de `opcao_a.yaml` aplicados só em memória. Esses `fixed`
são dois:

* o item de massa dos servos do split passa a 8,80 kg (8× DA 30-HT a 1,100 kg cada, do datasheet que já está no
  catálogo);
* a taxa de projeto do split fica ≥ 100 °/s, pela chave opcional nova `actuators.split_rate_required_deg_s`. A escolha
  do servo usa a maior entre esta taxa e a taxa 3σ da turbulência; sem a chave, nada muda.

O W0 é fechado de novo. Depois volta-se a correr o equilíbrio e a margem estática dos 4 casos, as HQ, a rajada lateral
no 6-DOF com o critério estrito nos 4 casos, o vento cruzado e a missão 6-DOF, já com a massa e a inércia novas. O
exemplo e os valores por omissão não mudam. Resultados em `examples/output/rajada_cheio/opcao_a.json`.

| Grandeza | Base (2× DA 30) | Opção (a) (2× DA 30-HT) |
|---|---|---|
| W0 (convergido) | 149,67 kg | **157,67 kg (+8,00 kg, +5,3 %)** |
| Massa vazia | 95,90 kg | 102,94 kg |
| Servos (split + elevon) | 6,30 kg | 10,06 kg (dentro do orçamento declarado) |
| I_xx / I_zz | 16,2 / 50,3 kg·m² | 17,5 / 56,2 kg·m² |
| \|H\| do split (23.455) | 38,3 N·m | 39,9 N·m |
| Taxa do split na superfície | 83,5 °/s | 107,0 °/s (G 0,93; o \|H\| subiu com o W0, por isso fica abaixo dos 111,4 °/s do estudo de decisão) |
| Potência mecânica por folha, P = FoS·\|H_op\|·ω | 25,3 W | 34,0 W (a 107 °/s); elétrica **desconhecida** (os datasheets Volz não dão rendimento) |
| Equilíbrio, 4 casos (cruzeiro e aproximação) | passa | passa (C_L máx. equilibrado 1,116 → 1,145) |
| Margem estática, vazio / carga / combustível / cheio | 0,051 / 0,065 / 0,051 / 0,063 | 0,050 / 0,062 / 0,050 / 0,060 (banda 0,02–0,08: passa) |
| Rolamento holandês com SAS (`hq:dutch_roll`) | ζ 0,142 → Nível 1, passa | ζ 0,133 → Nível 1, passa |
| Margem de atraso para o Nível 1 | 0,234 s | 0,223 s |
| Espiral (`hq:spiral`) | estável, Nível 1, passa | estável, Nível 1, passa |
| Fugóide da célula nua (`hq:phugoid`, indicativo em UAV) | ζ 0,0419 → Nível 1, passa | **ζ 0,0391 → Nível 2, falha (nova)** |
| Fugóide com manutenção de atitude (`hq:phugoid_autopilot`) | ζ 0,960 → Nível 1, passa | ζ 0,965 → Nível 1, passa |
| Rajada no 6-DOF, critério estrito: vazio / carga / combustível / cheio | passa / passa / passa / **falha** (pede 99,9 °/s) | passa / passa / passa / **passa** |
| Margem de taxa (disponível / pico): vazio / carga / combustível / cheio | 1,94 / 1,15 / 1,57 / — | 2,62 / 1,41 / 1,77 / **1,071** |
| Vento cruzado 10,1 kt (`hq:yaw_crosswind`) | passa (máx. 14,7 kt) | passa (máx. 14,2 kt) |
| Missão 6-DOF, corrida de descolagem com vento cruzado (requisito 300 m) | 325 m (já acima; tabela de opções existente) | 332 m |
| Missão 6-DOF, carga lateral no toque (14 CFR 23.485), convergida no passo (§5.2), dt 0,02 s | passa (interior 0,595, exterior 0,22) | **excede: interior 1,228, falha (nova)** |
| Mesma carga com dt 0,01 / 0,025 s | passa (0,605) / passa (0,611) | excede (1,232) / excede (1,213) |
| Descida e deriva no toque | 1,06 m/s, 0,34 m/s | 1,26 m/s, 0,41 m/s |

Leitura:

* **A rajada do «cheio» fica resolvida**: passa nos 4 casos. Mas a margem de taxa mínima é de **7 %** (pico de
  99,9 °/s contra 107,0 °/s) e não dos 11,5 % previstos sem redimensionar. O efeito bola de neve (+3,76 kg de servos
  → +8,0 kg de W0) sobe o \|H\| e a inércia.
* **Falha nova, `hq:phugoid` da célula nua**: ζ desce de 0,0419 para 0,0391, abaixo do limite do Nível 1 (0,04). O
  caso de projeto do UAV é com piloto automático (manutenção de atitude), que fica no Nível 1 com ζ 0,965, por isso
  isto é informação. Mas antes estava no limite e agora está do lado errado.
* **Falha nova na missão 6-DOF: carga lateral do trem principal no toque.** Com o veredicto já convergido no passo (§5.2), a razão interior fica em 1,21–1,23 > 1 nos passos 0,01 / 0,02 / 0,025 s, contra 0,60–0,61 na base. Opções em §5.3.
* O resto mantém-se: equilíbrio, margem estática, rolamento holandês, espiral, vento cruzado e autoridade em
  turbulência. Nenhuma verificação passou a desconhecida.

### 5.2 Veredicto do toque (14 CFR 23.485) convergido no passo do 6-DOF (24 nov 2026)

Antes desta correção, o veredicto da carga lateral no toque mudava com o passo da missão. A base passava a 0,01 e
0,02 s e excedia a 0,025 s (exterior 1,23); a opção (a) dava razões de 1,19 a 1,23. A razão interior já era estável;
os saltos estavam todos na razão exterior, que é a que oscilava. Há duas causas no 6-DOF (`flightsim/mission.py`,
`flightsim/sixdof.py`):

1. **Mudança de lei atrasada (deteção de evento).** O contacto só era detetado no início do passo seguinte. A lei do
   arredondamento (asa baixa, elevon ≈ −17°) ainda ficava aplicada no solo durante mais um passo inteiro (20–25 ms)
   antes da lei de rolagem. Nesse intervalo, a velocidade lateral da roda do nariz (deriva ~0,4 m/s) criava uma
   guinada forte e picos espúrios para fora nas rodas principais. O pico dependia de quanto tempo dentro do passo o
   contacto tinha começado. Correção: no contacto, o passo pára no sub-passo do evento e a lei de rolagem entra na
   mesma iteração.
2. **Lei de atrito lateral rígida para RK4 explícito.** F_y = −μ N tanh(v_y / v_ε), com v_ε = 0,5 m/s, comporta-se
   como um amortecedor lateral c ≈ μN/v_ε ≈ 1,2 kN·s/m por roda principal. Correção: na janela do toque (h < 5 m no
   arredondamento, ≤ 3 s depois do toque) a integração faz-se em sub-passos de ≤ 2,5 ms (`TOUCHDOWN_SUBSTEP_S`). Os
   comandos ficam fixos ao ritmo do piloto automático e os picos são amostrados em cada sub-passo. Só com a correção 1,
   sem sub-passos, a 20 ms a razão exterior dava 0,08 na base e 0,11 na opção (a), contra 0,22 e 0,33 com
   sub-passos: os picos ficavam por amostrar entre passos.

Convergência (razão máxima carga/limite, missão com vento cruzado completa):

| Passo da missão | 5 ms | 10 ms | 20 ms | 25 ms |
|---|---|---|---|---|
| Base: interior / exterior | 0,606 / 0,18 | 0,605 / 0,21 | 0,595 / 0,22 | 0,611 / 0,25 |
| Opção (a): interior / exterior | 1,221 / 0,31 | 1,232 / 0,36 | 1,228 / 0,33 | 1,213 / 0,62 |

Com o passo da missão a 20 ms, mudar o sub-passo para 5 / 2,5 / 1,25 ms dá 1,252 / 1,247 / 1,243 na opção (a).

Os valores das corridas de 5 ms e do varrimento de sub-passo vêm de corridas de diagnóstico sem `res`. Nessas
corridas, a subida usa o modelo de voo e não `PerfModel`, por isso as trajetórias diferem um pouco das do pipeline.
As outras colunas vêm de `examples/output/rajada_cheio/opcao_a.json`.

A dispersão fica em ±1,5 % na base e ±1 % na opção (a), dentro da banda numérica de ±5 % de `side_load_band`. Os
veredictos ficam convergidos: **base passa** e **opção (a) excede**. O teste `tests/test_touchdown_convergence.py`
usa os dois modelos de voo gravados numa aterragem curta. Exige o mesmo veredicto e uma dispersão ≤ 10 % a 10 / 20 /
25 ms, e ≤ 5 % entre sub-passos. No código anterior o teste falha: a opção (a) dava 0,98 / 0,91 / 1,02, ou seja,
três veredictos diferentes.

PRESSUPOSTO, que fica como estava: a lei de atrito (μ_lat 0,8, v_ε 0,5 m/s) e a mola/amortecedor vertical
(deflexão estática 0,07 m, ζ 0,7). A convergência é numérica e não valida o modelo de pneu.

### 5.3 Decisão: carga lateral no toque com a opção (a) (24 nov 2026, estudo `applied: false`)

O estudo `examples/studies/toque_cheio/` parte do desenho da opção (a) (W0 157,67 kg; razão interior 1,228 no toque)
e testa quatro famílias. Para cada uma procura-se a variante mais pequena que passa. **Nada é aplicado.**
Resultados em `examples/output/toque_cheio/toque_cheio.json`.

Critério: razão máxima entre a carga lateral do 6-DOF e o limite de 23.485(c) (0,5 W para dentro, 0,33 W para fora),
com a banda numérica de ±5 % (`passa` ≤ 0,95; `no_limite` = desconhecido; `excede` > 1,05). Na família (d), a razão
é ao limite de projeto k × 23.485.

| Família | Variante | Razão máx. | Veredicto | Afundamento / deriva no toque | Custo / efeitos |
|---|---|---|---|---|---|
| (a) Afundamento alvo do arredondamento (0,3 m/s) | 0,2 / 0,15 / 0,1 / 0,05 m/s | 1,27 / 1,26 / 1,26 / 1,28 | falha em todas | 1,33–1,50 m/s / 0,39–0,41 m/s | o afundamento real sobe: a lei não atinge o alvo (o atraso do arredondamento domina) |
| (a) Ângulo da rampa (2°) | 1,5° / 2,5° / 3° | 2,03 / 0,99 / 1,94 | falha / **desconhecido** (no limite) / falha | 2,08 / 1,61 / 2,08 m/s | não monótono; nenhuma variante passa |
| (b) Decrab (asa baixa a partir de 30 m) | 60 m | 28,9 | falha | 24,6 m/s | perda de controlo antes do toque (desvio de 18°, colisão da cauda) |
| (b) | **45 m** | **0,85** | **passa** | 1,16 / 0,34 m/s | sem massa; corrida no solo 249 m |
| (b) | 20 m / 10 m | 1,23 / 1,24 | falha | 1,26 / 0,40–0,44 m/s | — |
| (b) | decrab só no arredondamento | 0,93 | passa (margem de 2 %) | 1,03 / **0,65 m/s** | deriva maior no toque |
| (b) | sem decrab (toque caranguejado) | 1,65 | falha | 1,49 m/s; desvio 9,9° | — |
| (c) Semi-bitola (0,48 m), redimensionado | 0,55 / 0,60 / 0,70 m | 1,19 / 1,17 / 1,07 | falha | 1,24–1,27 / ~0,40 m/s | W0 igual (157,67 kg) |
| (c) | 0,80 m | 0,97 | **desconhecido** (no limite) | 1,24 / 0,40 m/s | nenhuma variante até 0,80 m passa; `asm:gear_max_track_9532` já falhava na base |
| (d) Fator de projeto lateral das pernas | 1,1 / 1,2 | 1,12 / 1,02 | falha / desconhecido | — | +0,10 kg |
| (d) | **1,3 × 23.485**, redimensionado | **0,91** (1,185 / 1,3) | **passa** | 1,19 / 0,40 m/s | pernas +0,21 kg (0,39 → 0,60 kg); **W0 +0,42 kg** (158,09 kg) |

Leitura:

* A carga no toque é muito sensível às condições da aproximação. Basta mudar a rampa de 2° para 1,5° ou 3° para a
  razão subir para ~2. O decrab também não é monótono: 45 m passa, 30 m e 20 m falham e 60 m perde o controlo.
* As famílias (a) e (c) não dão nenhuma variante que passe com margem.
* A família (d) passa com 9 % de margem e custo de massa pequeno. O modelo de pernas existente (consola de Al 2024-T3,
  FS 1,5) cresce a parede em degraus de 25 %. As ferragens de ligação e a estrutura da asa no ponto do trem **não
  são avaliadas**: ficam desconhecidas, não passam.

**Recomendação (só recomendação; a decisão fica com o João):** a família (d), pernas projetadas para 1,3 × as
cargas laterais de 23.485 (+0,21 kg; W0 158,09 kg). É a única que passa com margem sem mudar o procedimento de voo,
e cobre a aproximação nominal medida. Como reforço opcional, a variante de decrab a 45 m baixa a carga para 0,85.
Mas sozinha não se recomenda, porque a janela é estreita (30 m falha, 60 m perde o controlo). Antes de aplicar, falta
avaliar as ferragens e a ligação à asa, e a dispersão das condições de aproximação (rajadas, erro de rampa).

