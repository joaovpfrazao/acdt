# Relatório de dimensionamento — Cessna 172S (verificação)

_acdt 0.1.0 · Fase 1 (conceptual) + 1E (sistemas) + Fase 2 (baixa fidelidade)_

Requisitos ao estilo do POH do C172S para validar o método.

**Resultado:** ✅ VIÁVEL

**Verificação por segmentos (Fase 2):** ⚠️ pelo menos um requisito não cumprido na missão por segmentos (ver §13)

## 1. Requisitos desta corrida

| requisito | sentido | valor | qualificadores | estágios | avaliado |
|---|---|---|---|---|---|
| propulsion_type | target | piston_prop | - | context | sim |
| regulatory_category | target | cs_23 | - | check, systems | sim |
| crew_mass | target | 77 kg | - | sizing | sim |
| payload_mass | target | 185 kg | - | sizing | sim |
| range | min | 1185 km | - | sizing | sim |
| cruise_speed | target | 122 kt | - | constraint, sizing | sim |
| cruise_altitude | target | 8000 ft | - | context | sim |
| stall_speed | max | 48 kt | - | constraint | sim |
| takeoff_ground_roll | max | 293 m | - | constraint | sim |
| landing_distance | max | 407 m | - | constraint | sim |
| climb_rate | min | 730 ft/min | - | constraint | sim |
| service_ceiling | min | 13500 ft | - | constraint | sim |

Requisitos não definidos (livres / por omissão): endurance, max_speed, load_factor, turn_rate, mtow, wing_span, power_available, thrust_available, unit_cost, noise, mtow_objective

### Validação

- **info**: Nz das equações de massa = 1.5 × n_lim do diagrama V-n (3.96, rajada; cs_23)
- **info**: Massa do caixão da asa (Megson/Bruhn) = 96.95 kg vs Raymer Eq. 15.46 128.89 kg (razão 0.75); usado: Raymer
- **info**: Hélice: chord c/D(0.75R) = 0.0727 calibrated to static rpm 2350 (measured)
- **info**: Hélice: BEMT (McCormick 1995 Ch. 6, Prandtl tip loss; Ning 2014 solver), section clarky Re 2.2e+06 (NeuralFoil (large; XFOIL surrogate))
- **info**: Hélice: static rpm 2349 (rated 2700); engine torque law P ∝ n^1 at full throttle (PRESSUPOSTO)
- **info**: Eficiências da hélice calibradas no mapa (passo fixo): eta_takeoff 0.465, eta_climb 0.679, eta_cruise 0.882 (valores iniciais 0.55, 0.75, 0.80)
- **warning**: Desempenho por segmentos não cumpre: ROC máx. ao nível do mar: 3.642 m/s vs requerido ≥ 3.708 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- **warning**: Desempenho por segmentos não cumpre: distância de aterragem (Raymer 17.9, total 50 ft): 503.9 m vs requerido ≤ 407 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)

## 2. Peso à descolagem (Raymer Cap. 3; Hepperle 2012 para elétrico)

| grandeza | valor |
|---|---|
| W0 [kg] | 1138 |
| We [kg] | 709.9 |
| Combustível/bateria [kg] | 165.9 |
| Payload + tripulação [kg] | 262 |
| We/W0 | 0.6239 |
| Wf/W0 | 0.1458 |
| Energia bateria nominal [Wh] | - |

Pernas da missão: cruise 1185000 (SI) @ V=62.8 m/s, L/D=9.1, h=2438 m

## 2a. Estimativa de pesos por componentes (Raymer 6th ed. Cap. 15 + sistemas)

Valor inicial do peso vazio: Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb) 'ga_single_engine'.

Fator de carga último Nz = 5.93 (1.5 × limite). Iteração: estatística → geometria → componentes → novo We → re-dimensionar, até convergir (histórico na secção 8).

| grupo | item | kg | % W0 | método |
|---|---|---|---|---|
| structure | asa | 128.9 | 11.33 | Raymer Eq. 15.46 |
| structure | empenagem horizontal | 12.21 | 1.073 | Raymer Eq. 15.47 |
| structure | empenagem vertical | 6.344 | 0.5575 | Raymer Eq. 15.48 |
| structure | fuselagem | 97.6 | 8.578 | Raymer Eq. 15.49 (unpressurized) |
| structure | trem principal | 73.15 | 6.429 | Raymer Eq. 15.50 |
| structure | trem de nariz | 17.84 | 1.568 | Raymer Eq. 15.51 |
| propulsion | motor instalado (+hélice, berço, capota) | 202.4 | 17.79 | Raymer Eq. 15.52, Wen from engine datasheet (user) |
| propulsion | sistema de combustível | 26.37 | 2.318 | Raymer Eq. 15.53 |
| equipment | comandos de voo (cabos/hastes) | 18.49 | 1.625 | Raymer Eq. 15.54 |
| equipment | hidráulica | 0.9775 | 0.08591 | Raymer Eq. 15.55 (Kh=0.013, M=0.1) |
| equipment | aviónica instalada | 25.12 | 2.208 | Raymer Eq. 15.57, Wuav 15 kg (user) |
| equipment | sistema elétrico | 63.69 | 5.598 | Raymer Eq. 15.56 |
| equipment | interiores (bancos, cintos...) | 36.74 | 3.229 | Raymer Eq. 15.59 |


Resumo por grupo e composição de W0:

| grupo | kg | % W0 |
|---|---|---|
| structure | 336 | 29.53 |
| propulsion | 228.8 | 20.11 |
| equipment | 145 | 12.75 |
| **peso vazio We** | 709.9 | 62.39 |
| combustível / bateria | 165.9 | 14.58 |
| payload | 185 | 16.26 |
| tripulação | 77 | 6.767 |
| **W0** | 1138 | 100 |


Cross-check estatístico (We/W0 das classes publicadas no W0 obtido; 'fora' = W0 fora do intervalo da base de dados):

| classe | We/W0 | We [kg] | na gama | fonte |
|---|---|---|---|---|
| ga_single_engine | 0.5768 | 656.3 | - | Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb) 'ga_single_engine' |
| homebuilt_composite | 0.5685 | 646.9 | - | Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb) 'homebuilt_composite' |
| nicolai_light_ga | 0.6017 | 684.6 | - | Nicolai & Carichner (AIAA 2010) Table 5.1 (We = A W0^B, lb) 'nicolai_light_ga' |


## 3. Design point (diagrama de restrições)

![constraint diagram](constraint_diagram.png)

- **W0/S = 810.9 N/m² (82.69 kg/m²)**
- **P/W_SL = 100.7 W/kg** → P_SL = 115 kW
- Restrições ativas: Cruzeiro 63 m/s @ 2438 m, Perda 24.7 m/s
- Área alar S = 13.759 m²

## 4. Geometria de primeira iteração

| parâmetro | valor |
|---|---|
| S_m2 | 13.76 |
| AR | 7.32 |
| span_m | 10.04 |
| taper | 0.7 |
| c_root_m | 1.613 |
| c_tip_m | 1.129 |
| MAC_m | 1.385 |
| y_MAC_m | 2.361 |
| sweep_c4_deg | 0 |
| sweep_LE_deg | 1.381 |
| t/c | 0.12 |

Fuselagem: L = 8.06 m, D = 1.151 m. Empenagem horizontal S = 2.759 m², vertical S = 1.142 m², braço = 4.84 m (coef. de volume, Raymer Eq. 6.28–6.29).

Caixão da asa (parametrizado na geometria, análise na Fase 2): longarinas a 20%/65% c, largura na raiz 0.726 m.

## 5. Aerodinâmica (Raymer Cap. 12 / DATCOM)

![polar](drag_polar.png)

- CLα = 4.587 /rad (0.0801 /deg)
- CLmax limpo / descolagem / aterragem = 1.53 / 1.74 / 2.17
- CD0 = 0.03818, K = 0.0470 (e = 0.926), (L/D)max = 11.81 a CL = 0.90

Decomposição do CD0 (component build-up):

| component | Swet_m2 | Cf | FF | Q | CD0 |
|---|---|---|---|---|---|
| wing | 24.34 | 0.003089 | 1.253 | 1 | 0.006844 |
| htail | 5.597 | 0.00337 | 1.202 | 1.04 | 0.001714 |
| vtail | 2.317 | 0.003331 | 1.186 | 1.04 | 0.0006918 |
| fuselage | 23.78 | 0.002545 | 1.192 | 1 | 0.005245 |

D/q adicional (trem, antenas, ...): 0.3000 m²; L&P: 5%

## 6. Verificações

- ✅ `regulatory_category` — cs_23: W0 1137.8 kg <= 8618 kg
- ✅ `static_margin` — SM no CG traseiro 10.0 % (alvo 10 %; dianteiro 11.8 %) — posicionamento da asa por bisseção
- ✅ `trim` — CLmax limpo (CG dianteiro): δe -8.1°; cruzeiro (CG dianteiro): δe -3.3°
- ✅ `hq:scissor` — S_h/S atual 0.201 vs mínimo 0.201 (estabilidade 0.201 no CG traseiro, controlo 0.020 a CLmax no CG dianteiro; dimensionante: estabilidade)
- ✅ `hq:short_period` — período curto ζ = 0.817 → Nível 1 (N1: 0.30–2.00; MIL-F-8785C Table IV, Classe I, Cat. B)
- ✅ `hq:CAP` — CAP = ω²/(n/α) [1/(g s²)] = 1.52 → Nível 1 (N1: 0.085–3.6; MIL-F-8785C Figs. 1–3, Classe I, Cat. B)
- ✅ `hq:phugoid` — fugóide ζ = 0.0907 → Nível 1 (N1: ≥ 0.04; MIL-F-8785C 3.2.1.2, Classe I, Cat. B)
- ✅ `hq:dutch_roll` — rolamento holandês ζ / ζω / ω = 0.153 / 0.231 / 1.50 → Nível 1 (N1: 0.08 / 0.15 / 0.4; MIL-F-8785C Table VI, Classe I, Cat. B)
- ✅ `hq:roll` — rolamento τ_R [s] = 0.232 → Nível 1 (N1: ≤ 1.4; MIL-F-8785C Table VII, Classe I, Cat. B)
- ✅ `hq:spiral` — espiral T2 [s] (∞ = estável) = inf → Nível 1 (N1: ≥ 20; MIL-F-8785C Table VIII, Classe I, Cat. B)
- ✅ `aeroel:divergence` — divergência torsional V = 367.0 m/s EAS vs 117.4 (= 1.2 V_D); margem +213 %
- ✅ `aeroel:reversal` — inversão de aileron: não ocorre (V → ∞) vs 117.4 m/s EAS
- ✅ `aeroel:flutter` — flutter binário V = 155.2 m/s EAS vs 117.4 (= 1.2 V_D); margem +32 %
- ✅ `aeroel:aeer45` — AEER-45 / 23.629(d): F = 0.000981 vs F_max = 0.00418 (balanceamento do aileron não avaliado)
- ✅ `perf:range` — distância de cruzeiro (segmentos): 1233 km vs requerido ≥ 1185 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ✅ `perf:service_ceiling` — teto de serviço (Anderson): 4504 m vs requerido ≥ 4115 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ❌ `perf:climb_rate` — ROC máx. ao nível do mar: 3.642 m/s vs requerido ≥ 3.708 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ✅ `perf:takeoff_ground_roll` — corrida de descolagem (Raymer 17.8): 274.6 m vs requerido ≤ 293 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ❌ `perf:landing_distance` — distância de aterragem (Raymer 17.9, total 50 ft): 503.9 m vs requerido ≤ 407 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)

## 8. Histórico do ciclo MDA (peso ↔ design point ↔ geometria ↔ arrasto)

| iter | W0 | We/W0 usado | We | Wf | n_lim (V-n) | asa Raymer [kg] | asa caixão [kg] | We_comp | We_comp/W0 | CD0 | W/S | P/W | L/D_max | aero |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 920.9 | 0.5992 | 551.8 | 107.1 | 3.8 | 99.99 | 74.96 | 620.5 | 0.6737 | 0.04284 | 778.1 | 9.677 | 10.55 | manual |
| 2 | 1049 | 0.5912 | 620.5 | 167 | 3.8 | 117.9 | 88.94 | 679.1 | 0.6471 | 0.03909 | 778.1 | 11.82 | 11.05 | manual |
| 3 | 1110 | 0.6121 | 679.1 | 168.4 | 3.8 | 126.4 | 95.68 | 701.2 | 0.6319 | 0.03763 | 778.1 | 10.97 | 11.26 | manual |
| 4 | 1132 | 0.6196 | 701.2 | 168.5 | 3.8 | 129.5 | 98.2 | 709.2 | 0.6267 | 0.03713 | 778.1 | 10.66 | 11.34 | manual |
| 5 | 1140 | 0.6222 | 709.2 | 168.6 | 3.8 | 130.7 | 99.13 | 712.2 | 0.6248 | 0.03695 | 778.1 | 10.61 | 11.36 | manual |
| 6 | 1143 | 0.6232 | 712.2 | 168.7 | 3.8 | 131.1 | 99.48 | 713.3 | 0.6241 | 0.03689 | 778.1 | 10.59 | 11.37 | manual |
| 7 | 1144 | 0.6235 | 713.3 | 168.7 | 3.8 | 131.3 | 99.61 | 713.7 | 0.6239 | 0.03686 | 778.1 | 10.59 | 11.38 | manual |
| 8 | 1144 | 0.6237 | 713.7 | 168.7 | 3.8 | 131.3 | 99.66 | 713.9 | 0.6238 | 0.03685 | 778.1 | 10.58 | 11.38 | manual |
| 9 | 1145 | 0.6237 | 713.9 | 168.7 | 3.8 | 131.4 | 99.67 | 714 | 0.6238 | 0.03685 | 778.1 | 10.58 | 11.38 | manual |
| 10 | 1145 | 0.6237 | 714 | 168.7 | 3.8 | 131.4 | 99.68 | 714 | 0.6238 | 0.03685 | 778.1 | 10.58 | 11.38 | manual |
| 11 | 1145 | 0.6237 | 714 | 168.7 | 3.8 | 131.4 | 99.68 | 714 | 0.6237 | 0.03685 | 778.1 | 10.58 | 11.38 | manual |
| 12 | 1145 | 0.6237 | 714 | 168.7 | 3.8 | 131.4 | 99.68 | 714 | 0.6237 | 0.03685 | 778.1 | 10.58 | 11.38 | manual |
| 13 | 1145 | 0.6237 | 714 | 168.7 | 3.987 | 131.4 | 102.1 | 714 | 0.6237 | 0.03694 | 778.1 | 10.58 | 12.02 | lowfi |
| 14 | 1142 | 0.625 | 714 | 166.5 | 3.954 | 129.9 | 97.28 | 712.3 | 0.6235 | 0.03811 | 812.2 | 10.01 | 11.82 | lowfi |
| 15 | 1140 | 0.6246 | 712.3 | 166 | 3.955 | 129.2 | 97.2 | 710.7 | 0.6233 | 0.03812 | 811 | 10.26 | 11.81 | lowfi |
| 16 | 1139 | 0.6242 | 710.7 | 165.9 | 3.956 | 129 | 97.01 | 710.1 | 0.6237 | 0.03816 | 811 | 10.26 | 11.81 | lowfi |
| 17 | 1138 | 0.624 | 710.1 | 165.9 | 3.956 | 128.9 | 96.96 | 709.9 | 0.6238 | 0.03818 | 811 | 10.27 | 11.81 | lowfi |
| 18 | 1138 | 0.6239 | 709.9 | 165.9 | 3.958 | 128.9 | 96.95 | 709.9 | 0.6239 | 0.03818 | 810.9 | 10.27 | 11.81 | lowfi |

## 10. Aerodinâmica de baixa fidelidade (Fase 2: XFOIL + AVL)

![lowfi](lowfi_polar.png)

- Perfil: XFOIL 6.99 (Ncrit 9, xtr ≤ 0.10); Re de cruzeiro 4.89e+06, cm0 = -0.0509
- clmax do perfil (Re de perda 2.29e+06) = 1.698 → CLmax limpo 1.528 (Raymer Eq. 12.15)
- Carga em envergadura: AVL 3.40 (VLM), 2 ângulos; e_inv = 0.994, fator de fuselagem (Kroo) 0.9737
- CDp da asa (integração em faixas, CL = 0.5) = 0.00743 vs termo do manual 0.00684
- **Polar usada no ciclo: CD0 = 0.03818, K = 0.04698 (e = 0.926)**

- perfil NACA 2412: Re cruzeiro 4.89e+06 (xtr = 0.10), clmax a Re_stall 2.29e+06 (transição livre, Ncrit 9)

### Comparação AVL / baixa fidelidade vs métodos de manual

| grandeza | manual | AVL / baixa fid. | método manual | nota |
|---|---|---|---|---|
| CLα asa [/rad] | 4.587 | 5.106 | DATCOM / Raymer Eq. 12.6 | AVL: avião completo (asa + cauda), sem fuselagem |
| CDi a CL = 0.428 | 0.009581 | 0.008008 | Oswald Raymer e = 0.830 | AVL e (Trefftz) = 0.993; Oswald inclui arrasto viscoso dependente de CL |
| x̄_NP [MAC] | 0.5061 | 0.5746 | Raymer Eq. 16.9 + Torenbeek (fuselagem) | sem fuselagem: 0.536 (AVL não modela a fuselagem) |
| CLδe [/rad] | 0.4498 | 0.5086 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) |  |
| Cmδe [/rad] | -1.57 | -1.677 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) | AVL: Cmδe no CG traseiro; Cnδr com convenção de sinal AVL |
| |Clδa| [/rad] | 0.3553 | 0.2325 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) |  |
| Cnδr [/rad] | -0.08167 | 0.07288 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) | AVL: Cmδe no CG traseiro; Cnδr com convenção de sinal AVL |
| CD0 (polar ajustada) | 0.03811 | 0.03818 | Raymer Eq. 12.24 | perfil XFOIL 6.99 (Ncrit 9, xtr ≤ 0.10); ajuste rms 2.4e-04 |
| e efetivo | 0.8299 | 0.9255 | Raymer Eq. 12.49 | baixa fid.: AVL e_inv × Kroo (fuselagem) + cd(cl) do perfil |
| cl_max do perfil | 1.6 | 1.698 | pressuposto do utilizador | XFOIL/NeuralFoil a Re = 2.29e+06 |

## 11. Estruturas: V-n, cargas na asa e caixão (Fase 2)

![V-n](vn_diagram.png)

| grandeza | valor |
|---|---|
| regulation | cs_23 |
| category | normal |
| VS1_EAS_m_s | 29.44 |
| VA_EAS_m_s | 57.39 |
| VC_EAS_m_s | 69.87 |
| VD_EAS_m_s | 97.81 |
| n_manoeuvre_pos | 3.8 |
| n_manoeuvre_neg | -1.52 |
| n_gust_VC | 3.958 / -1.958 |
| n_gust_VD | 3.070 / -1.070 |
| mu_g | 24.37 |
| Kg | 0.7228 |
| n_limit_pos | 3.958 |
| n_limit_neg | -1.958 |
| governing | rajada |
| n_ultimate | 5.936 |

Cláusulas aplicadas: 23.333 (envelope); 23.335(a) VC ≥ 33.0√(W/S) kt = 136 kt EAS; 23.335(b) VD ≥ max(1.25 VC, 1.40 VC,min); 23.335(c) VA ≥ VS√n; 23.337 limit manoeuvring load factors; 23.341 gust load factors (Pratt–Walker)


Condição crítica de dimensionamento: n = 3.96 (rajada), q a VD = 97.8 m/s EAS.

![loads](wing_loads.png)

Raiz (limite): V = 19572.1 N, M = 43645.8 N·m, T = 114.4 N·m.

![box](wing_box.png)

| parcela | massa [kg] |
|---|---|
| caps | 0 |
| covers_skin_stringers | 53.33 |
| core | 0 |
| webs | 3.658 |
| web_uprights | 0.9201 |
| LE_TE_skins | 17.88 |
| ribs | 1.771 |
| ideal | 77.56 |
| nonoptimum | 19.39 |
| total | 96.95 |

Cross-check da massa da asa:

| método | massa da asa [kg] |
|---|---|
| Raymer Eq. 15.46 (estatístico) | 128.9 |
| caixão Megson/Bruhn, carga Schrenk (Al 2024-T3 (MMPDS typical — verify)) | 96.95 |
| caixão Megson/Bruhn, carga AVL | 94.53 |

- Revestimentos reforçados (Z): σ ótimo de Farrar F = 0.81 com corte por crippling de Needham 234 MPa (b'/t = 12 — PRESSUPOSTO); passo de reforçadores na raiz 49 mm (≈ 15 reforçadores/painel); σ raiz 185 MPa
- Almas: tensão diagonal de Kuhn, k raiz = 0.61, montantes a d = h (PRESSUPOSTO), C1 = C2 ≈ 0 (α ≈ 45°, banzos rígidos — PRESSUPOSTO); admissível de τ_max = Fsu (curva Bruhn Fig. C11.19 não digitalizada — LIMITAÇÃO)
- Banzo inferior: tração Ftu e compressão no caso negativo n_neg/n_pos = 0.49
- MMPDS typical 2024-T3 sheet: Fcy 269 MPa, Ftu 434 MPa, Fsu 262 MPa, G 27.6 GPa — verify
- 16 nervuras (passo 0.83 m)
- fator não-ótimo 1.25 (PRESSUPOSTO)
- superfícies de comando, flaps e carenagens NÃO incluídos (secundários)
- Eixo elástico = centro de corte da secção real (Megson, multicélula, com bordo de ataque D): x_sc/c raiz 0.360 (meio do caixão 0.425); EI/GJ da secção idealizada no contorno do perfil

## 12. Estabilidade e controlo (Fase 2: Raymer Cap. 16, Etkin & Reid, Nelson)

![cg](cg_envelope.png)

- asa posicionada para SM = 10% no CG mais recuado (ápice a 14.7% L); ápice da asa a x = 1.187 m
- Ponto neutro x̄_NP = 0.506 MAC (manual), 0.575 (AVL); dε/dα = 0.399
- **Margem estática: 11.8 % (CG dianteiro) … 10.0 % (CG traseiro)**
- AVL, cruzeiro compensado no CG traseiro: α = 3.10°, δe = -1.25°, Cnβ = 0.0887, Clβ = -0.0736, Cmq = -17.52
- Coef. de volume: V_h = 0.700, V_v = 0.0400 (Raymer Table 6.4: 0.7 / 0.04)

| caso | massa [kg] | x_cg [m] | x̄_cg [MAC] | SM |
|---|---|---|---|---|
| vazio + tripulação | 786.9 | 1.807 | 0.4061 | 0.1 |
| sem payload | 952.7 | 1.781 | 0.3877 | 0.1185 |
| MTOW | 1138 | 1.784 | 0.3897 | 0.1165 |
| sem combustível (ZFW) | 971.9 | 1.805 | 0.405 | 0.1012 |

Compensação (trim) no CG dianteiro:

| condição | CL | δe [°] | ok (|δe| ≤ máx.) |
|---|---|---|---|
| CLmax limpo (CG dianteiro) | 1.528 | -8.063 | True |
| cruzeiro (CG dianteiro) | 0.4276 | -3.307 | True |

- Clδa comparado em módulo (convenções de sinal do aileron diferem entre AVL e Nelson).
- Estações de CG dos componentes: PRESSUPOSTOS (Roskam Part V Table 8.1, valores típicos) — substituir pelas posições do layout real em assumptions.stability.stations.

## 13. Desempenho por segmentos (Fase 2: Raymer Cap. 17, Anderson)

Orçamento utilizável: Wf / 1.06 (reserva + não utilizável 6 %, Raymer Eq. 3.11).

Missão requerida (segmentos):

| segmento | t [min] | dist [km] | consumo [kg] | h [m] | V [m/s] | nota |
|---|---|---|---|---|---|---|
| aquecimento + descolagem | 0 | 0 | 34.13 | 0→0 | 0 | Raymer Table 3.2 (0.970) |
| subida (V_y) | 14.08 | 34.75 | 4.889 | 0→2438 | 41.23 | potência de subida, integrado (V médio) |
| cruzeiro | 314.8 | 1186 | 107.7 | 2438→2438 | 62.76 |  |
| descida (L/D máx, ralenti) + aterragem | 12.64 | 28.79 | 5.494 | 2438→0 | 37.96 | Raymer 0.995 (combustível) |

Missão até esgotar o orçamento: **alcance 1296.8 km, endurance 5.90 h**.

| segmento | t [min] | dist [km] | consumo [kg] | h [m] | V [m/s] | nota |
|---|---|---|---|---|---|---|
| aquecimento + descolagem | 0 | 0 | 34.13 | 0→0 | 0 | Raymer Table 3.2 (0.970) |
| subida (V_y) | 14.08 | 34.75 | 4.889 | 0→2438 | 41.23 | potência de subida, integrado (V médio) |
| cruzeiro | 327.5 | 1233 | 111.9 | 2438→2438 | 62.76 | estendido até esgotar o orçamento |
| descida (L/D máx, ralenti) + aterragem | 12.67 | 28.79 | 5.494 | 2438→0 | 37.87 | Raymer 0.995 (combustível) |

Requisitos vs desempenho por segmentos:

| requisito | grandeza | obtido | requerido | unidade | ok |
|---|---|---|---|---|---|
| range | distância de cruzeiro (segmentos) | 1233 | 1185 | km | ✅ |
| service_ceiling | teto de serviço (Anderson) | 4504 | 4115 | m | ✅ |
| climb_rate | ROC máx. ao nível do mar | 3.642 | 3.708 | m/s | ❌ |
| takeoff_ground_roll | corrida de descolagem (Raymer 17.8) | 274.6 | 293 | m | ✅ |
| landing_distance | distância de aterragem (Raymer 17.9, total 50 ft) | 503.9 | 407 | m | ❌ |

![payload-range](payload_range.png)

| ponto | payload_kg | combustível_kg | massa_kg | range_km |
|---|---|---|---|---|
| A | 185 | 0 | 971.9 | 0 |
| B | 185 | 165.9 | 1138 | 1297 |
| C | 185 | 165.9 | 1138 | 1297 |
| D (ferry) | 0 | 165.9 | 952.8 | 1444 |

Nota: capacidade de combustível 165.9 kg (= combustível de projeto, PRESSUPOSTO — dar performance.fuel_capacity_kg).

![climb](climb_ceiling.png)

- ROC máx. ao nível do mar 3.64 m/s; teto de serviço 4504 m; teto absoluto 5290 m
- Descolagem (Raymer 17.8): corrida 275 m, total sobre 15 m 459 m (V_TO 30.4 m/s)
- Aterragem (Raymer 17.9): corrida 201 m, total sobre 15 m 504 m (μ_travagem 0.4; aproximação γ = 3° — `performance.approach_angle_deg`, por omissão o máximo de 5.2 % / 3° de CS/14 CFR 23.75(a)(1))

- Os resultados de segmentos usam a mesma polar e reservas do dimensionamento; diferenças face aos requisitos vêm da subida/descida integradas vs. frações históricas (Raymer Table 3.2).

## 14. Caixão da asa dimensionado à estabilidade (Fase 3: Bruhn C5/C7/C11, Farrar, Kuhn)

| caixão | massa [kg] | / Raymer 15.46 |
|---|---|---|
| resistência (Fase 2, limite inferior) | 84.18 | 0.6531 |
| encurvadura (Fase 3, Al 2024-T3 (MMPDS typical — verify)) | 96.95 | 0.7522 |
| Raymer Eq. 15.46 (asa completa, estatístico) | 128.9 | 1 |

Parcelas (caixão de encurvadura):

| parcela | massa [kg] |
|---|---|
| caps | 0 |
| covers_skin_stringers | 53.33 |
| core | 0 |
| webs | 3.658 |
| web_uprights | 0.9201 |
| LE_TE_skins | 17.88 |
| ribs | 1.771 |
| ideal | 77.56 |
| nonoptimum | 19.39 |
| total | 96.95 |

- Almas Kuhn: fator de tração diagonal k máx. 0.614 (k = 0: alma resistente ao corte, sem tração diagonal)
- Passo dos reforçadores: 28–140 mm (encurvadura local do revestimento, k = 4)
- Revestimentos reforçados (Z): σ ótimo de Farrar F = 0.81 com corte por crippling de Needham 234 MPa (b'/t = 12 — PRESSUPOSTO); passo de reforçadores na raiz 49 mm (≈ 15 reforçadores/painel); σ raiz 185 MPa
- Almas: tensão diagonal de Kuhn, k raiz = 0.61, montantes a d = h (PRESSUPOSTO), C1 = C2 ≈ 0 (α ≈ 45°, banzos rígidos — PRESSUPOSTO); admissível de τ_max = Fsu (curva Bruhn Fig. C11.19 não digitalizada — LIMITAÇÃO)
- Banzo inferior: tração Ftu e compressão no caso negativo n_neg/n_pos = 0.49
- MMPDS typical 2024-T3 sheet: Fcy 269 MPa, Ftu 434 MPa, Fsu 262 MPa, G 27.6 GPa — verify
- 16 nervuras (passo 0.83 m)
- fator não-ótimo 1.25 (PRESSUPOSTO)
- superfícies de comando, flaps e carenagens NÃO incluídos (secundários)
- Eixo elástico = centro de corte da secção real (Megson, multicélula, com bordo de ataque D): x_sc/c raiz 0.360 (meio do caixão 0.425); EI/GJ da secção idealizada no contorno do perfil

## 15. Aeroelasticidade clássica (Fase 3)

V_D = 97.8 m/s EAS.

| fenómeno | V [m/s EAS] | requerido 1.2 V_D | margem | ok | método |
|---|---|---|---|---|---|
| divergência torsional | 367 | 117.4 | +213 % | ✅ | W&C 8.3 / Bisplinghoff 8-2 (faixas + FE) |
| inversão do aileron | n/a | 117.4 | sem ocorrência | ✅ | W&C 8.4, Glauert (flap 2D) |
| flutter binário (flexão–torção) | 155.2 | 117.4 | +32 % | ✅ | W&C 11 (modos assumidos, quase-estacionário) |

- Frequências desacopladas: flexão 8.51 Hz, torção 26.7 Hz; flutter a 21.9 Hz
- AEER-45 (fator de flexibilidade torsional da asa): F = 9.811e-04 vs F_max = 200/V_D² = 4.178e-03 → OK

![flutter](flutter_vg.png)

### Acoplamento aero-estrutural estático (OpenAeroStruct, VLM + caixão)

| ponto | modelo | α [°] | CL | CDi | CLα [/rad] | flecha ponta [m] | torção ponta [°] |
|---|---|---|---|---|---|---|---|
| cruise | rígido | 5.276 | 0.4276 | 0.007737 | 4.629 | 4.16e-06 | 1.933e-05 |
| cruise | flexível | 5.168 | 0.4276 | 0.007752 | 4.729 | 0.04188 | 0.1944 |
| manobra (n_lim, V_D EAS, nível do mar) | rígido | 6.764 | 0.5477 | 0.01269 | 4.615 | 1.643e-05 | 7.634e-05 |
| manobra (n_lim, V_D EAS, nível do mar) | flexível | 6.327 | 0.5477 | 0.01278 | 4.948 | 0.1678 | 0.7769 |

- Efeito da forma deformada no arrasto induzido de cruzeiro: K_flex/K = 1.0020
- Missão por segmentos: rígido 1296.8 km / 5.904 h → flexível 1296.2 km / 5.901 h (comparação com o resultado desacoplado da Fase 2)
- OpenAeroStruct VLM (sem viscoso/onda: só arrasto induzido) + FEM de caixão 'wingbox' acoplados por NLBGS; rígido = E, G × 10⁴
- secção do caixão: NACA-4 entre longarinas; espessuras de alma/revestimento do caixão acdt (5 pontos de controlo); revestimento único equivalente que reproduz EI(y) do caixão acdt e G ajustado para GJ (PRESSUPOSTO)
- sem alívio de peso estrutural nem de combustível na asa (conservativo para a deformação)
- índice de falha OAS (von Mises/KS, σ_adm = σ_cap/1.5) na manobra: +0.488 (< 0 = OK) — critério de resistência do OAS sobre o revestimento equivalente — INDICATIVO (o dimensionamento é o do caixão acdt)
- massa da asa 128.89 kg distribuída ∝ corda; CG da secção a 0.50 c; eixo elástico a 0.339 c (centro de corte da secção, média), e = 0.089 c atrás do c.a.; a_w = 6.283/rad (2D, teoria das faixas — sem correção 3D/compressibilidade)
- encastramento na parede da fuselagem y0 = 0.576 m; EI/GJ do caixão buckling
- requisito: livre de flutter/divergência/inversão até 1.2 V_D = 117.4 m/s EAS (14 CFR 23.629(c) legado; CS/14 CFR 23.2245 'suficientemente além'; STANAG 4671 USAR.629 — verificar)
- flutter: modelo binário de modos assumidos (W&C Cap. 11), aerodinâmica quase-estacionária — ESTIMATIVA; a análise racional exige modos FEM + DLM (Fase 4)

## 16. Diagrama de tesoura, modos dinâmicos e qualidades de voo (Fase 3)

![scissor](scissor.png)

- S_h/S atual 0.201; requerido 0.201 (estabilidade 0.201, controlo 0.02; dimensionante: estabilidade) → ✅ (Torenbeek Cap. 9)
- linha de controlo: trim a CLmax limpo 1.53 com δe = −25°, τ_e = 0.661, Cm0 = -0.0400 (Raymer 16.13); momento dos flaps e efeito de solo NÃO incluídos
- massa da cauda não realimentada (posição da asa e braço fixos)

![modes](root_locus.png)

| modo | ωn [rad/s] | ζ | período [s] | τ / T [s] |
|---|---|---|---|---|
| período curto | 4.218 | 0.8172 | 2.584 | - |
| fugóide | 0.174 | 0.09072 | 36.27 | - |
| rolamento holandês | 1.504 | 0.1535 | 4.227 | - |
| rolamento (constante de tempo) | - | - | - | 0.2321 |
| espiral estável | - | - | - | 15.4 |

- n/α = 11.7 g/rad, CAP = 1.52 1/(g s²)
- Inércias (Roskam V, soma por componentes): Ixx 2.43e+03, Iyy 1.91e+03, Izz 3.89e+03 kg·m²
- derivadas de taxa e laterais: AVL (sem fuselagem) + Cnβ da fuselagem (Raymer 16.47) -0.0644
- Cmα = −CLα·SM no CG de MTOW (ponto neutro de manual com fuselagem)
- inércias por soma de componentes (Roskam Parte V) — PRESSUPOSTOS de estações

Qualidades de voo — MIL-F-8785C, Classe I, categoria B (nível exigido 1):

| modo | valor | nível | limite N1 | ref |
|---|---|---|---|---|
| período curto ζ | 0.8172 | 1 | 0.30–2.00 | MIL-F-8785C Table IV |
| CAP = ω²/(n/α) [1/(g s²)] | 1.523 | 1 | 0.085–3.6 | MIL-F-8785C Figs. 1–3 |
| fugóide ζ | 0.09072 | 1 | ≥ 0.04 | MIL-F-8785C 3.2.1.2 |
| rolamento holandês ζ / ζω / ω | 0.153 / 0.231 / 1.50 | 1 | 0.08 / 0.15 / 0.4 | MIL-F-8785C Table VI |
| rolamento τ_R [s] | 0.2321 | 1 | ≤ 1.4 | MIL-F-8785C Table VII |
| espiral T2 [s] (∞ = estável) | n/a | 1 | ≥ 20 | MIL-F-8785C Table VIII |


## Pressupostos usados

```yaml
weights:
  method: components
  initial_class: null
  fixed_fraction: null
  A: null
  C: null
  tech_factor: 1.0
  Kvs: 1.0
  fixed_mass_kg: 0.0
  components:
    material: metal
    landing_gear: tricycle
    main_gear_length_m: 0.65
    nose_gear_length_m: 0.55
    engine_dry_mass_kg: 121.6
    avionics_uninstalled_kg: 15
    n_tanks: 2
aero:
  AR: 7.32
  taper: 0.7
  sweep_c4_deg: 0.0
  tc_root: 0.12
  tc_tip: 0.12
  xc_max_t: 0.3
  airfoil: NACA 2412
  clmax_airfoil: 1.6
  flap:
    kind: slotted
    flapped_area_ratio: 0.55
  oswald: null
  cfe: 0.0055
  swet_sref: 4.0
  laminar:
    wing: 0.1
    htail: 0.1
    vtail: 0.1
    fuselage: 0.0
  roughness: smooth_paint
  Q:
    wing: 1.0
  lp_fraction: 0.05
  extra_drag_areas_m2:
    fixed_landing_gear: 0.2
    cooling_and_engine: 0.1
  CL_ground: 0.5
  dCD0_takeoff: 0.01
  mu_roll: 0.04
  fidelity: lowfi
  airfoil_solver: xfoil
propulsion:
  eta_cruise: 0.8820548696499505
  eta_climb: 0.6787442650415285
  eta_takeoff: 0.46511631058242714
  bsfc_lb_hp_h: null
  tsfc_1_h: 0.5
  battery_Wh_kg: 200.0
  eta_total: 0.7
  dod: 0.8
  energy_reserve: 0.2
  systems_power_W: 0.0
  n_engines: 1
  propeller:
    type: fixed_pitch
    rpm_rated: 2700
    blades: 2
    diameter_m: 1.93
    pitch_m: 1.524
    static_rpm: 2350
    airfoil: clarky
geometry:
  fuselage_length_m: null
  fuselage_diameter_m: null
  fuselage_fineness: 7.0
  fuselage_class: null
  tail_class: null
  c_ht: null
  c_vt: null
  tail_arm_fraction: 0.6
  ar_h: 4.0
  ar_v: 1.5
  wing_position: high
constraints:
  cruise_weight_fraction: 1.0
  landing_weight_fraction: 1.0
  approach_distance_ft: 600.0
  margin: 0.0
  ws_initial_psf: 17.0
  ws_min: 50.0
  ws_max: 3000.0
  default_cruise_altitude_m: 0.0
  ws_fixed: null
  value_fixed: null
mda:
  max_iter: 30
  tol: 1.0e-05
  tol_lowfi: 0.0002
structures:
  regulation: auto
  load_factor_from_vn: true
  material: auto
  nonoptimum_factor: 1.25
  VH_eas_m_s: null
  elastic_axis: section
  le_cell: true
stability:
  target_static_margin: 0.1
  wing_apex_x_fraction: null
  stations: {}
  inertia_method: roskam
  roskam_reference: cessna_172m
  radii_of_gyration: null
  elevator_max_deg: 25.0
  use_avl: true
  dynamics: true
  hq_category: B
  hq_required_level: 1
performance:
  fuel_capacity_kg: null
  max_payload_kg: null
  mu_brake: 0.4
  approach_angle_deg: 3.0
aeroelasticity:
  enabled: true
  a_w: 6.283185307179586
  x_cg_chord: null
  margin_factor: 1.2
  static_aerostructural: true
mdo:
  objective: null
  solver: nlbgs
  trust_region_iterations: 8
  trust_region_radius: 0.3
  design_vars:
  - ws
  - AR
  AR_bounds:
  - 5.0
  - 16.0
  ws_bounds_factor:
  - 0.6
  - 1.4
  pw_bounds_factor:
  - 0.6
  - 1.6
  maxiter: 60
  tol: 1.0e-06
  hq_aeroel_constraints: false
cost: {}
calibration:
  file: null
  apply: []
  factors: {}
```

## Referências

- Raymer, D. P., *Aircraft Design: A Conceptual Approach*, 6th ed., AIAA, 2018 (equation numbers as in the 6th ed.).
- Roskam, J., *Airplane Design*, Parts I–VIII, DARcorporation.
- Gudmundsson, S., *General Aviation Aircraft Design: Applied Methods and Procedures*, Elsevier, 2014.
- Anderson, J. D., *Aircraft Performance and Design*, McGraw-Hill, 1999.
- Torenbeek, E., *Synthesis of Subsonic Airplane Design*, Delft Univ. Press, 1982.
- USAF Stability and Control DATCOM, 1978.
- Hepperle, M., "Electric Flight – Potential and Limitations", NATO STO-MP-AVT-209, 2012.
- Niu, M. C. Y., *Airframe Structural Design*, Conmilit, 1988.
- Drela, M., "First-Order DC Electric Motor Model", MIT, 2007.
- ISO 2533:1975 Standard Atmosphere.
- Nicolai, L. M., Carichner, G. E., *Fundamentals of Aircraft and Airship Design*, Vol. I, AIAA, 2010 (Table 5.1, We = A·W0^B incl. UAV classes).
- EASA CS-23 (Amdt. 4 and earlier) / 14 CFR 23.337 (pre-Amdt. 23-64): limit manoeuvring load factors.
- IEC 60028:1925, International standard of resistance for copper (ρCu = 8890 kg/m³).
- FAA Type Certificate Data Sheet 1E10 (Lycoming O-360/IO-360 series) — engine dry mass in the C172 check.
- Drela, M., "XFOIL: An Analysis and Design System for Low Reynolds Number Airfoils", 1989; XFOIL 6.99 (GPL).
- Drela, M., Youngren, H., AVL 3.40 (Athena Vortex Lattice), MIT, 2022 (GPL).
- Sharpe, P., NeuralFoil, MIT, 2024 (fallback section polars).
- Schrenk, O., "A Simple Approximation Method for Obtaining the Spanwise Lift Distribution", NACA TM 948, 1940.
- Megson, T. H. G., *Aircraft Structures for Engineering Students*, 5th ed., 2013 (Ch. 16, 19–23).
- Bruhn, E. F., *Analysis and Design of Flight Vehicle Structures*, 1973 (Ch. A3, C5, C11).
- Etkin, B., Reid, L. D., *Dynamics of Flight: Stability and Control*, 3rd ed., Wiley, 1996.
- Nelson, R. C., *Flight Stability and Automatic Control*, 2nd ed., McGraw-Hill, 1998.
- Kroo, I., *Aircraft Design: Synthesis and Analysis*, Stanford (lift-dependent drag, fuselage span-efficiency factor).
- EASA CS-23 Amdt. 4 / 14 CFR 23.333–23.341 (flight envelope, design speeds, gust loads); 14 CFR/CS 23.65 (climb speed).
- NATO STANAG 4671 Ed. 1 (USAR), 2009: USAR.303, .333, .335, .337, .341.
- Abbott, I. H., von Doenhoff, A. E., *Theory of Wing Sections*, Dover, 1959.
