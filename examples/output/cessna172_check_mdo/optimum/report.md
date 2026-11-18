# Relatório de dimensionamento — Cessna 172S (verificação)

_acdt 0.1.0 · Fase 1 (conceptual) + 1E (sistemas) + Fase 2 (baixa fidelidade)_

Requisitos ao estilo do POH do C172S para validar o método.

**Resultado:** ❌ INVIÁVEL / requisitos não cumpridos

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

- **info**: Nz das equações de massa = 1.5 × n_lim do diagrama V-n (3.80, manobra; cs_23)
- **info**: Massa do caixão da asa (Megson/Bruhn) = 81.41 kg vs Raymer Eq. 15.46 97.67 kg (razão 0.83); usado: Raymer
- **error**: Infeasible: fixed W/S 822.1 N/m² above the W/S limit 822.1
- **warning**: Desempenho por segmentos não cumpre: distância de aterragem (Raymer 17.9, total 50 ft): 503.1 m vs requerido ≤ 407 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)

## 2. Peso à descolagem (Raymer Cap. 3; Hepperle 2012 para elétrico)

| grandeza | valor |
|---|---|
| W0 [kg] | 1121 |
| We [kg] | 676.1 |
| Combustível/bateria [kg] | 182.6 |
| Payload + tripulação [kg] | 262 |
| We/W0 | 0.6033 |
| Wf/W0 | 0.1629 |
| Energia bateria nominal [Wh] | - |

Pernas da missão: cruise 1185000 (SI) @ V=62.8 m/s, L/D=8.4, h=2438 m

## 2a. Estimativa de pesos por componentes (Raymer 6th ed. Cap. 15 + sistemas)

Valor inicial do peso vazio: Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb) 'ga_single_engine'.

Fator de carga último Nz = 5.70 (1.5 × limite). Iteração: estatística → geometria → componentes → novo We → re-dimensionar, até convergir (histórico na secção 8).

| grupo | item | kg | % W0 | método |
|---|---|---|---|---|
| structure | asa | 97.67 | 8.716 | Raymer Eq. 15.46 |
| structure | empenagem horizontal | 13.66 | 1.219 | Raymer Eq. 15.47 |
| structure | empenagem vertical | 5.081 | 0.4534 | Raymer Eq. 15.48 |
| structure | fuselagem | 95.93 | 8.56 | Raymer Eq. 15.49 (unpressurized) |
| structure | trem principal | 72.3 | 6.452 | Raymer Eq. 15.50 |
| structure | trem de nariz | 17.69 | 1.578 | Raymer Eq. 15.51 |
| propulsion | motor instalado (+hélice, berço, capota) | 202.4 | 18.06 | Raymer Eq. 15.52, Wen from engine datasheet (user) |
| propulsion | sistema de combustível | 28.27 | 2.523 | Raymer Eq. 15.53 |
| equipment | comandos de voo (cabos/hastes) | 16.3 | 1.455 | Raymer Eq. 15.54 |
| equipment | hidráulica | 0.9657 | 0.08618 | Raymer Eq. 15.55 (Kh=0.013, M=0.1) |
| equipment | aviónica instalada | 25.12 | 2.241 | Raymer Eq. 15.57, Wuav 15 kg (user) |
| equipment | sistema elétrico | 64.88 | 5.79 | Raymer Eq. 15.56 |
| equipment | interiores (bancos, cintos...) | 35.74 | 3.189 | Raymer Eq. 15.59 |


Resumo por grupo e composição de W0:

| grupo | kg | % W0 |
|---|---|---|
| structure | 302.3 | 26.98 |
| propulsion | 230.7 | 20.59 |
| equipment | 143 | 12.76 |
| **peso vazio We** | 676.1 | 60.33 |
| combustível / bateria | 182.6 | 16.29 |
| payload | 185 | 16.51 |
| tripulação | 77 | 6.871 |
| **W0** | 1121 | 100 |


Cross-check estatístico (We/W0 das classes publicadas no W0 obtido; 'fora' = W0 fora do intervalo da base de dados):

| classe | We/W0 | We [kg] | na gama | fonte |
|---|---|---|---|---|
| ga_single_engine | 0.5784 | 648.2 | - | Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb) 'ga_single_engine' |
| homebuilt_composite | 0.5693 | 638 | - | Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb) 'homebuilt_composite' |
| nicolai_light_ga | 0.6021 | 674.8 | - | Nicolai & Carichner (AIAA 2010) Table 5.1 (We = A W0^B, lb) 'nicolai_light_ga' |


## 3. Design point (diagrama de restrições)

![constraint diagram](constraint_diagram.png)

- **W0/S = 822.1 N/m² (83.83 kg/m²)**
- **P/W_SL = 120.3 W/kg** → P_SL = 135 kW
- Restrições ativas: Cruzeiro 63 m/s @ 2438 m, Perda 24.7 m/s
- Área alar S = 13.369 m²

## 4. Geometria de primeira iteração

| parâmetro | valor |
|---|---|
| S_m2 | 13.37 |
| AR | 5 |
| span_m | 8.176 |
| taper | 0.7 |
| c_root_m | 1.924 |
| c_tip_m | 1.347 |
| MAC_m | 1.652 |
| y_MAC_m | 1.924 |
| sweep_c4_deg | 0 |
| sweep_LE_deg | 2.021 |
| t/c | 0.12 |

Fuselagem: L = 8.03 m, D = 1.147 m. Empenagem horizontal S = 3.208 m², vertical S = 0.907 m², braço = 4.82 m (coef. de volume, Raymer Eq. 6.28–6.29).

Caixão da asa (parametrizado na geometria, análise na Fase 2): longarinas a 20%/65% c, largura na raiz 0.866 m.

## 5. Aerodinâmica (Raymer Cap. 12 / DATCOM)

![polar](drag_polar.png)

- CLα = 4.083 /rad (0.0713 /deg)
- CLmax limpo / descolagem / aterragem = 1.56 / 1.76 / 2.20
- CD0 = 0.03828, K = 0.0695 (e = 0.916), (L/D)max = 9.69 a CL = 0.74

Decomposição do CD0 (component build-up):

| component | Swet_m2 | Cf | FF | Q | CD0 |
|---|---|---|---|---|---|
| wing | 22.86 | 0.002996 | 1.253 | 1 | 0.006417 |
| htail | 6.509 | 0.003324 | 1.202 | 1.04 | 0.002024 |
| vtail | 1.841 | 0.0034 | 1.186 | 1.04 | 0.0005774 |
| fuselage | 23.61 | 0.002547 | 1.192 | 1 | 0.005363 |

D/q adicional (trem, antenas, ...): 0.3000 m²; L&P: 5%

## 6. Verificações

- ✅ `regulatory_category` — cs_23: W0 1120.7 kg <= 8618 kg
- ✅ `static_margin` — SM no CG traseiro 10.0 % (alvo 10 %; dianteiro 12.0 %) — posicionamento da asa por bisseção
- ✅ `trim` — CLmax limpo (CG dianteiro): δe -8.1°; cruzeiro (CG dianteiro): δe -3.2°
- ✅ `hq:scissor` — S_h/S atual 0.240 vs mínimo 0.240 (estabilidade 0.240 no CG traseiro, controlo 0.020 a CLmax no CG dianteiro; dimensionante: estabilidade)
- ✅ `hq:short_period` — período curto ζ = 0.987 → Nível 1 (N1: 0.30–2.00; MIL-F-8785C Table IV, Classe I, Cat. B)
- ✅ `hq:CAP` — CAP = ω²/(n/α) [1/(g s²)] = 2.08 → Nível 1 (N1: 0.085–3.6; MIL-F-8785C Figs. 1–3, Classe I, Cat. B)
- ✅ `hq:phugoid` — fugóide ζ = 0.0983 → Nível 1 (N1: ≥ 0.04; MIL-F-8785C 3.2.1.2, Classe I, Cat. B)
- ❌ `hq:dutch_roll` — rolamento holandês ζ / ζω / ω = 0.103 / 0.127 / 1.24 → Nível 2 (N1: 0.08 / 0.15 / 0.4; MIL-F-8785C Table VI, Classe I, Cat. B)
- ✅ `hq:roll` — rolamento τ_R [s] = 0.258 → Nível 1 (N1: ≤ 1.4; MIL-F-8785C Table VII, Classe I, Cat. B)
- ✅ `hq:spiral` — espiral T2 [s] (∞ = estável) = inf → Nível 1 (N1: ≥ 20; MIL-F-8785C Table VIII, Classe I, Cat. B)
- ✅ `aeroel:divergence` — divergência torsional V = 245.2 m/s EAS vs 118.2 (= 1.2 V_D); margem +107 %
- ✅ `aeroel:reversal` — inversão de aileron V = 241.5 m/s EAS vs 118.2 (= 1.2 V_D); margem +104 %
- ✅ `aeroel:flutter` — flutter binário V = 141.4 m/s EAS vs 118.2 (= 1.2 V_D); margem +20 %
- ✅ `aeroel:aeer45` — AEER-45 / 23.629(d): F = 0.000946 vs F_max = 0.00412 (balanceamento do aileron não avaliado)
- ✅ `perf:range` — distância de cruzeiro (segmentos): 1223 km vs requerido ≥ 1185 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ✅ `perf:service_ceiling` — teto de serviço (Anderson): 4486 m vs requerido ≥ 4115 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ✅ `perf:climb_rate` — ROC máx. ao nível do mar: 5.302 m/s vs requerido ≥ 3.708 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ✅ `perf:takeoff_ground_roll` — corrida de descolagem (Raymer 17.8): 179.9 m vs requerido ≤ 293 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ❌ `perf:landing_distance` — distância de aterragem (Raymer 17.9, total 50 ft): 503.1 m vs requerido ≤ 407 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)

## 8. Histórico do ciclo MDA (peso ↔ design point ↔ geometria ↔ arrasto)

| iter | W0 | We/W0 usado | We | Wf | n_lim (V-n) | asa Raymer [kg] | asa caixão [kg] | We_comp | We_comp/W0 | CD0 | W/S | P/W | L/D_max | aero |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 953.7 | 0.5954 | 567.8 | 123.8 | 3.8 | 79.75 | 65.85 | 609.9 | 0.6395 | 0.0433 | 822.1 | 10.14 | 9.038 | manual |
| 2 | 1055 | 0.5781 | 609.9 | 183 | 3.8 | 90.58 | 75.11 | 654.6 | 0.6205 | 0.04032 | 822.1 | 13.52 | 9.366 | manual |
| 3 | 1101 | 0.5945 | 654.6 | 184.4 | 3.8 | 95.54 | 79.43 | 669.9 | 0.6085 | 0.03914 | 822.1 | 12.8 | 9.507 | manual |
| 4 | 1116 | 0.6002 | 669.9 | 184.3 | 3.8 | 97.19 | 80.87 | 674.9 | 0.6046 | 0.03877 | 822.1 | 12.52 | 9.552 | manual |
| 5 | 1121 | 0.602 | 674.9 | 184.3 | 3.8 | 97.73 | 81.34 | 676.5 | 0.6034 | 0.03865 | 822.1 | 12.43 | 9.566 | manual |
| 6 | 1123 | 0.6025 | 676.5 | 184.3 | 3.8 | 97.91 | 81.49 | 677.1 | 0.603 | 0.03861 | 822.1 | 12.4 | 9.571 | manual |
| 7 | 1123 | 0.6027 | 677.1 | 184.3 | 3.8 | 97.96 | 81.54 | 677.2 | 0.6029 | 0.0386 | 822.1 | 12.4 | 9.573 | manual |
| 8 | 1123 | 0.6028 | 677.2 | 184.3 | 3.8 | 97.98 | 81.56 | 677.3 | 0.6028 | 0.0386 | 822.1 | 12.39 | 9.573 | manual |
| 9 | 1124 | 0.6028 | 677.3 | 184.3 | 3.8 | 97.99 | 81.57 | 677.3 | 0.6028 | 0.03859 | 822.1 | 12.39 | 9.573 | manual |
| 10 | 1124 | 0.6028 | 677.3 | 184.3 | 3.8 | 97.99 | 81.57 | 677.3 | 0.6028 | 0.03859 | 822.1 | 12.39 | 9.573 | manual |
| 11 | 1124 | 0.6028 | 677.3 | 184.3 | 3.8 | 97.99 | 81.57 | 677.3 | 0.6028 | 0.03859 | 822.1 | 12.39 | 9.573 | manual |
| 12 | 1124 | 0.6028 | 677.3 | 184.3 | 3.8 | 97.99 | 81.68 | 677.3 | 0.6028 | 0.03826 | 822.1 | 12.39 | 9.703 | lowfi |
| 13 | 1122 | 0.6037 | 677.3 | 182.7 | 3.8 | 97.82 | 81.53 | 676.5 | 0.603 | 0.03825 | 822.1 | 12.25 | 9.695 | lowfi |
| 14 | 1121 | 0.6034 | 676.5 | 182.6 | 3.8 | 97.72 | 81.45 | 676.2 | 0.6032 | 0.03827 | 822.1 | 12.26 | 9.692 | lowfi |
| 15 | 1121 | 0.6033 | 676.2 | 182.6 | 3.8 | 97.68 | 81.41 | 676.1 | 0.6032 | 0.03828 | 822.1 | 12.26 | 9.691 | lowfi |
| 16 | 1121 | 0.6033 | 676.1 | 182.6 | 3.8 | 97.67 | 81.41 | 676.1 | 0.6033 | 0.03828 | 822.1 | 12.26 | 9.691 | lowfi |

## 10. Aerodinâmica de baixa fidelidade (Fase 2: XFOIL + AVL)

![lowfi](lowfi_polar.png)

- Perfil: XFOIL 6.99 (Ncrit 9, xtr ≤ 0.10); Re de cruzeiro 5.83e+06, cm0 = -0.0510
- clmax do perfil (Re de perda 2.73e+06) = 1.731 → CLmax limpo 1.558 (Raymer Eq. 12.15)
- Carga em envergadura: AVL 3.40 (VLM), 2 ângulos; e_inv = 0.978, fator de fuselagem (Kroo) 0.9606
- CDp da asa (integração em faixas, CL = 0.5) = 0.00649 vs termo do manual 0.00642
- **Polar usada no ciclo: CD0 = 0.03828, K = 0.06954 (e = 0.916)**

- perfil NACA 2412: Re cruzeiro 5.83e+06 (xtr = 0.10), clmax a Re_stall 2.73e+06 (transição livre, Ncrit 9)

### Comparação AVL / baixa fidelidade vs métodos de manual

| grandeza | manual | AVL / baixa fid. | método manual | nota |
|---|---|---|---|---|
| CLα asa [/rad] | 4.083 | 4.564 | DATCOM / Raymer Eq. 12.6 | AVL: avião completo (asa + cauda), sem fuselagem |
| CDi a CL = 0.433 | 0.01328 | 0.0121 | Oswald Raymer e = 0.901 | AVL e (Trefftz) = 0.989; Oswald inclui arrasto viscoso dependente de CL |
| x̄_NP [MAC] | 0.4782 | 0.5589 | Raymer Eq. 16.9 + Torenbeek (fuselagem) | sem fuselagem: 0.505 (AVL não modela a fuselagem) |
| CLδe [/rad] | 0.5384 | 0.6051 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) |  |
| Cmδe [/rad] | -1.57 | -1.679 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) | AVL: Cmδe no CG traseiro; Cnδr com convenção de sinal AVL |
| |Clδa| [/rad] | 0.3162 | 0.1923 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) |  |
| Cnδr [/rad] | -0.08167 | 0.07219 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) | AVL: Cmδe no CG traseiro; Cnδr com convenção de sinal AVL |
| CD0 (polar ajustada) | 0.03866 | 0.03828 | Raymer Eq. 12.24 | perfil XFOIL 6.99 (Ncrit 9, xtr ≤ 0.10); ajuste rms 1.9e-04 |
| e efetivo | 0.9007 | 0.9155 | Raymer Eq. 12.49 | baixa fid.: AVL e_inv × Kroo (fuselagem) + cd(cl) do perfil |
| cl_max do perfil | 1.6 | 1.731 | pressuposto do utilizador | XFOIL/NeuralFoil a Re = 2.73e+06 |

## 11. Estruturas: V-n, cargas na asa e caixão (Fase 2)

![V-n](vn_diagram.png)

| grandeza | valor |
|---|---|
| regulation | cs_23 |
| category | normal |
| VS1_EAS_m_s | 29.35 |
| VA_EAS_m_s | 57.22 |
| VC_EAS_m_s | 70.34 |
| VD_EAS_m_s | 98.48 |
| n_manoeuvre_pos | 3.8 |
| n_manoeuvre_neg | -1.52 |
| n_gust_VC | 3.606 / -1.606 |
| n_gust_VD | 2.824 / -0.824 |
| mu_g | 23.13 |
| Kg | 0.7159 |
| n_limit_pos | 3.8 |
| n_limit_neg | -1.606 |
| governing | manobra |
| n_ultimate | 5.7 |

Cláusulas aplicadas: 23.333 (envelope); 23.335(a) VC ≥ 33.0√(W/S) kt = 137 kt EAS; 23.335(b) VD ≥ max(1.25 VC, 1.40 VC,min); 23.335(c) VA ≥ VS√n; 23.337 limit manoeuvring load factors; 23.341 gust load factors (Pratt–Walker)


Condição crítica de dimensionamento: n = 3.80 (manobra), q a VD = 98.5 m/s EAS.

![loads](wing_loads.png)

Raiz (limite): V = 19055.6 N, M = 34676.8 N·m, T = 2738.9 N·m.

![box](wing_box.png)

| parcela | massa [kg] |
|---|---|
| caps | 0 |
| covers_skin_stringers | 41.43 |
| core | 0 |
| webs | 3.555 |
| web_uprights | 0.8874 |
| LE_TE_skins | 17.37 |
| ribs | 1.89 |
| ideal | 65.13 |
| nonoptimum | 16.28 |
| total | 81.41 |

Cross-check da massa da asa:

| método | massa da asa [kg] |
|---|---|
| Raymer Eq. 15.46 (estatístico) | 97.67 |
| caixão Megson/Bruhn, carga Schrenk (Al 2024-T3 (MMPDS typical — verify)) | 81.41 |
| caixão Megson/Bruhn, carga AVL | 79.06 |

- Revestimentos reforçados (Z): σ ótimo de Farrar F = 0.81 com corte por crippling de Needham 234 MPa (b'/t = 12 — PRESSUPOSTO); passo de reforçadores na raiz 48 mm (≈ 18 reforçadores/painel); σ raiz 126 MPa
- Almas: tensão diagonal de Kuhn, k raiz = 0.65, montantes a d = h (PRESSUPOSTO), C1 = C2 ≈ 0 (α ≈ 45°, banzos rígidos — PRESSUPOSTO); admissível de τ_max = Fsu (curva Bruhn Fig. C11.19 não digitalizada — LIMITAÇÃO)
- Banzo inferior: tração Ftu e compressão no caso negativo n_neg/n_pos = 0.42
- MMPDS typical 2024-T3 sheet: Fcy 269 MPa, Ftu 434 MPa, Fsu 262 MPa, G 27.6 GPa — verify
- 12 nervuras (passo 0.99 m)
- fator não-ótimo 1.25 (PRESSUPOSTO)
- superfícies de comando, flaps e carenagens NÃO incluídos (secundários)

## 12. Estabilidade e controlo (Fase 2: Raymer Cap. 16, Etkin & Reid, Nelson)

![cg](cg_envelope.png)

- asa posicionada para SM = 10% no CG mais recuado (ápice a 14.0% L); ápice da asa a x = 1.121 m
- Ponto neutro x̄_NP = 0.478 MAC (manual), 0.559 (AVL); dε/dα = 0.520
- **Margem estática: 12.0 % (CG dianteiro) … 10.0 % (CG traseiro)**
- AVL, cruzeiro compensado no CG traseiro: α = 3.88°, δe = -1.50°, Cnβ = 0.0904, Clβ = -0.0773, Cmq = -14.54
- Coef. de volume: V_h = 0.700, V_v = 0.0400 (Raymer Table 6.4: 0.7 / 0.04)

| caso | massa [kg] | x_cg [m] | x̄_cg [MAC] | SM |
|---|---|---|---|---|
| vazio + tripulação | 753.1 | 1.805 | 0.3729 | 0.1053 |
| sem payload | 935.6 | 1.781 | 0.3587 | 0.1196 |
| MTOW | 1121 | 1.793 | 0.3655 | 0.1127 |
| sem combustível (ZFW) | 938.1 | 1.814 | 0.3782 | 0.1 |

Compensação (trim) no CG dianteiro:

| condição | CL | δe [°] | ok (|δe| ≤ máx.) |
|---|---|---|---|
| CLmax limpo (CG dianteiro) | 1.558 | -8.124 | True |
| cruzeiro (CG dianteiro) | 0.4335 | -3.22 | True |

- Clδa comparado em módulo (convenções de sinal do aileron diferem entre AVL e Nelson).
- Estações de CG dos componentes: PRESSUPOSTOS (Roskam Part V Table 8.1, valores típicos) — substituir pelas posições do layout real em assumptions.stability.stations.

## 13. Desempenho por segmentos (Fase 2: Raymer Cap. 17, Anderson)

Orçamento utilizável: Wf / 1.06 (reserva + não utilizável 6 %, Raymer Eq. 3.11).

Missão requerida (segmentos):

| segmento | t [min] | dist [km] | consumo [kg] | h [m] | V [m/s] | nota |
|---|---|---|---|---|---|---|
| aquecimento + descolagem | 0 | 0 | 33.62 | 0→0 | 0 | Raymer Table 3.2 (0.970) |
| subida (V_y) | 9.862 | 21.75 | 4.659 | 0→2438 | 37 | potência de subida, integrado (V médio) |
| cruzeiro | 314.8 | 1186 | 124.7 | 2438→2438 | 62.76 |  |
| descida (L/D máx, ralenti) + aterragem | 9.44 | 23.63 | 5.412 | 2438→0 | 41.72 | Raymer 0.995 (combustível) |

Missão até esgotar o orçamento: **alcance 1268.0 km, endurance 5.73 h**.

| segmento | t [min] | dist [km] | consumo [kg] | h [m] | V [m/s] | nota |
|---|---|---|---|---|---|---|
| aquecimento + descolagem | 0 | 0 | 33.62 | 0→0 | 0 | Raymer Table 3.2 (0.970) |
| subida (V_y) | 9.862 | 21.75 | 4.659 | 0→2438 | 37 | potência de subida, integrado (V médio) |
| cruzeiro | 324.7 | 1223 | 128.5 | 2438→2438 | 62.76 | estendido até esgotar o orçamento |
| descida (L/D máx, ralenti) + aterragem | 9.459 | 23.63 | 5.412 | 2438→0 | 41.64 | Raymer 0.995 (combustível) |

Requisitos vs desempenho por segmentos:

| requisito | grandeza | obtido | requerido | unidade | ok |
|---|---|---|---|---|---|
| range | distância de cruzeiro (segmentos) | 1223 | 1185 | km | ✅ |
| service_ceiling | teto de serviço (Anderson) | 4486 | 4115 | m | ✅ |
| climb_rate | ROC máx. ao nível do mar | 5.302 | 3.708 | m/s | ✅ |
| takeoff_ground_roll | corrida de descolagem (Raymer 17.8) | 179.9 | 293 | m | ✅ |
| landing_distance | distância de aterragem (Raymer 17.9, total 50 ft) | 503.1 | 407 | m | ❌ |

![payload-range](payload_range.png)

| ponto | payload_kg | combustível_kg | massa_kg | range_km |
|---|---|---|---|---|
| A | 185 | 0 | 938.1 | 0 |
| B | 185 | 182.6 | 1121 | 1268 |
| C | 185 | 182.6 | 1121 | 1268 |
| D (ferry) | 0 | 182.6 | 935.7 | 1435 |

Nota: capacidade de combustível 182.6 kg (= combustível de projeto, PRESSUPOSTO — dar performance.fuel_capacity_kg).

![climb](climb_ceiling.png)

- ROC máx. ao nível do mar 5.30 m/s; teto de serviço 4486 m; teto absoluto 5016 m
- Descolagem (Raymer 17.8): corrida 180 m, total sobre 15 m 383 m (V_TO 30.4 m/s)
- Aterragem (Raymer 17.9): corrida 200 m, total sobre 15 m 503 m (μ_travagem 0.4; aproximação γ = 3° — `performance.approach_angle_deg`, por omissão o máximo de 5.2 % / 3° de CS/14 CFR 23.75(a)(1))

- Os resultados de segmentos usam a mesma polar e reservas do dimensionamento; diferenças face aos requisitos vêm da subida/descida integradas vs. frações históricas (Raymer Table 3.2).

## 14. Caixão da asa dimensionado à estabilidade (Fase 3: Bruhn C5/C7/C11, Farrar, Kuhn)

| caixão | massa [kg] | / Raymer 15.46 |
|---|---|---|
| resistência (Fase 2, limite inferior) | 66.04 | 0.6762 |
| encurvadura (Fase 3, Al 2024-T3 (MMPDS typical — verify)) | 81.41 | 0.8335 |
| Raymer Eq. 15.46 (asa completa, estatístico) | 97.67 | 1 |

Parcelas (caixão de encurvadura):

| parcela | massa [kg] |
|---|---|
| caps | 0 |
| covers_skin_stringers | 41.43 |
| core | 0 |
| webs | 3.555 |
| web_uprights | 0.8874 |
| LE_TE_skins | 17.37 |
| ribs | 1.89 |
| ideal | 65.13 |
| nonoptimum | 16.28 |
| total | 81.41 |

- Almas Kuhn: fator de tração diagonal k máx. 0.653 (k = 0: alma resistente ao corte, sem tração diagonal)
- Passo dos reforçadores: 30–168 mm (encurvadura local do revestimento, k = 4)
- Revestimentos reforçados (Z): σ ótimo de Farrar F = 0.81 com corte por crippling de Needham 234 MPa (b'/t = 12 — PRESSUPOSTO); passo de reforçadores na raiz 48 mm (≈ 18 reforçadores/painel); σ raiz 126 MPa
- Almas: tensão diagonal de Kuhn, k raiz = 0.65, montantes a d = h (PRESSUPOSTO), C1 = C2 ≈ 0 (α ≈ 45°, banzos rígidos — PRESSUPOSTO); admissível de τ_max = Fsu (curva Bruhn Fig. C11.19 não digitalizada — LIMITAÇÃO)
- Banzo inferior: tração Ftu e compressão no caso negativo n_neg/n_pos = 0.42
- MMPDS typical 2024-T3 sheet: Fcy 269 MPa, Ftu 434 MPa, Fsu 262 MPa, G 27.6 GPa — verify
- 12 nervuras (passo 0.99 m)
- fator não-ótimo 1.25 (PRESSUPOSTO)
- superfícies de comando, flaps e carenagens NÃO incluídos (secundários)

## 15. Aeroelasticidade clássica (Fase 3)

V_D = 98.5 m/s EAS.

| fenómeno | V [m/s EAS] | requerido 1.2 V_D | margem | ok | método |
|---|---|---|---|---|---|
| divergência torsional | 245.2 | 118.2 | +107 % | ✅ | W&C 8.3 / Bisplinghoff 8-2 (faixas + FE) |
| inversão do aileron | 241.5 | 118.2 | +104 % | ✅ | W&C 8.4, Glauert (flap 2D) |
| flutter binário (flexão–torção) | 141.4 | 118.2 | +20 % | ✅ | W&C 11 (modos assumidos, quase-estacionário) |

- Frequências desacopladas: flexão 13.5 Hz, torção 30.8 Hz; flutter a 24.8 Hz
- AEER-45 (fator de flexibilidade torsional da asa): F = 9.460e-04 vs F_max = 200/V_D² = 4.121e-03 → OK

![flutter](flutter_vg.png)

### Acoplamento aero-estrutural estático (OpenAeroStruct, VLM + caixão)

| ponto | modelo | α [°] | CL | CDi | CLα [/rad] | flecha ponta [m] | torção ponta [°] |
|---|---|---|---|---|---|---|---|
| cruise | rígido | 6.058 | 0.4335 | 0.01158 | 4.08 | 2.146e-06 | 2.095e-05 |
| cruise | flexível | 5.944 | 0.4335 | 0.01159 | 4.16 | 0.02158 | 0.2106 |
| manobra (n_lim, V_D EAS, nível do mar) | rígido | 7.357 | 0.5259 | 0.01704 | 4.066 | 8.141e-06 | 7.946e-05 |
| manobra (n_lim, V_D EAS, nível do mar) | flexível | 6.918 | 0.5259 | 0.01711 | 4.333 | 0.0829 | 0.8075 |

- Efeito da forma deformada no arrasto induzido de cruzeiro: K_flex/K = 1.0011
- Missão por segmentos: rígido 1268.0 km / 5.733 h → flexível 1268.0 km / 5.733 h (comparação com o resultado desacoplado da Fase 2)
- OpenAeroStruct VLM (sem viscoso/onda: só arrasto induzido) + FEM de caixão 'wingbox' acoplados por NLBGS; rígido = E, G × 10⁴
- secção do caixão: NACA-4 entre longarinas; espessuras de alma/revestimento do caixão acdt (5 pontos de controlo); revestimento único equivalente que reproduz EI(y) do caixão acdt e G ajustado para GJ (PRESSUPOSTO)
- sem alívio de peso estrutural nem de combustível na asa (conservativo para a deformação)
- índice de falha OAS (von Mises/KS, σ_adm = σ_cap/1.5) na manobra: +0.179 (< 0 = OK) — critério de resistência do OAS sobre o revestimento equivalente — INDICATIVO (o dimensionamento é o do caixão acdt)
- massa da asa 97.67 kg distribuída ∝ corda; CG da secção a 0.50 c; eixo elástico a 0.425 c (meio do caixão), e = 0.175 c atrás do c.a.; a_w = 6.283/rad (2D, teoria das faixas — sem correção 3D/compressibilidade)
- encastramento na parede da fuselagem y0 = 0.574 m; EI/GJ do caixão buckling
- requisito: livre de flutter/divergência/inversão até 1.2 V_D = 118.2 m/s EAS (14 CFR 23.629(c) legado; CS/14 CFR 23.2245 'suficientemente além'; STANAG 4671 USAR.629 — verificar)
- flutter: modelo binário de modos assumidos (W&C Cap. 11), aerodinâmica quase-estacionária — ESTIMATIVA; a análise racional exige modos FEM + DLM (Fase 4)

## 16. Diagrama de tesoura, modos dinâmicos e qualidades de voo (Fase 3)

![scissor](scissor.png)

- S_h/S atual 0.240; requerido 0.24 (estabilidade 0.24, controlo 0.02; dimensionante: estabilidade) → ✅ (Torenbeek Cap. 9)
- linha de controlo: trim a CLmax limpo 1.56 com δe = −25°, τ_e = 0.661, Cm0 = -0.0364 (Raymer 16.13); momento dos flaps e efeito de solo NÃO incluídos
- massa da cauda não realimentada (posição da asa e braço fixos)

![modes](root_locus.png)

| modo | ωn [rad/s] | ζ | período [s] | τ / T [s] |
|---|---|---|---|---|
| período curto | 4.628 | 0.9871 | 8.491 | - |
| fugóide | 0.1736 | 0.09827 | 36.36 | - |
| rolamento holandês | 1.236 | 0.1029 | 5.109 | - |
| rolamento (constante de tempo) | - | - | - | 0.2577 |
| espiral estável | - | - | - | 4.854 |

- n/α = 10.3 g/rad, CAP = 2.08 1/(g s²)
- Inércias (Roskam V, soma por componentes): Ixx 1.44e+03, Iyy 1.6e+03, Izz 3.03e+03 kg·m²
- derivadas de taxa e laterais: AVL (sem fuselagem) + Cnβ da fuselagem (Raymer 16.47) -0.0806
- Cmα = −CLα·SM no CG de MTOW (ponto neutro de manual com fuselagem)
- inércias por soma de componentes (Roskam Parte V) — PRESSUPOSTOS de estações

Qualidades de voo — MIL-F-8785C, Classe I, categoria B (nível exigido 1):

| modo | valor | nível | limite N1 | ref |
|---|---|---|---|---|
| período curto ζ | 0.9871 | 1 | 0.30–2.00 | MIL-F-8785C Table IV |
| CAP = ω²/(n/α) [1/(g s²)] | 2.076 | 1 | 0.085–3.6 | MIL-F-8785C Figs. 1–3 |
| fugóide ζ | 0.09827 | 1 | ≥ 0.04 | MIL-F-8785C 3.2.1.2 |
| rolamento holandês ζ / ζω / ω | 0.103 / 0.127 / 1.24 | 2 | 0.08 / 0.15 / 0.4 | MIL-F-8785C Table VI |
| rolamento τ_R [s] | 0.2577 | 1 | ≤ 1.4 | MIL-F-8785C Table VII |
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
  AR: 5.0
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
  eta_cruise: 0.8
  eta_climb: 0.75
  eta_takeoff: 0.55
  bsfc_lb_hp_h: null
  tsfc_1_h: 0.5
  battery_Wh_kg: 200.0
  eta_total: 0.7
  dod: 0.8
  energy_reserve: 0.2
  systems_power_W: 0.0
  n_engines: 1
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
constraints:
  cruise_weight_fraction: 1.0
  landing_weight_fraction: 1.0
  approach_distance_ft: 600.0
  margin: 0.0
  ws_initial_psf: 17.0
  ws_min: 50.0
  ws_max: 3000.0
  default_cruise_altitude_m: 0.0
  ws_fixed: 822.0553013110884
  value_fixed: null
  criterion: fixed_ws
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
stability:
  target_static_margin: 0.1
  wing_apex_x_fraction: null
  stations: {}
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
cost: {}
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
