# Relatório de dimensionamento — GA tourer 2 lugares

_acdt 0.1.0 · Fase 1 (conceptual) + 1E (sistemas) + Fase 2 (baixa fidelidade)_

Avião de viagem rápido, 2 ocupantes + bagagem, CS-23 nível 1, motor a pistão + hélice de passo fixo.

**Resultado:** ✅ VIÁVEL

**Verificação por segmentos (Fase 2):** ⚠️ pelo menos um requisito não cumprido na missão por segmentos (ver §13)

## 1. Requisitos desta corrida

| requisito | sentido | valor | qualificadores | estágios | avaliado |
|---|---|---|---|---|---|
| propulsion_type | target | piston_prop | - | context | sim |
| regulatory_category | target | cs_23 | - | check, systems | sim |
| crew_mass | target | 85 kg | - | sizing | sim |
| payload_mass | target | 115 kg | - | sizing | sim |
| range | min | 1300 km | - | sizing | sim |
| cruise_speed | min | 150 kt | altitude=2438.4 | constraint, sizing | sim |
| max_speed | min | 165 kt | altitude=0 | constraint | sim |
| stall_speed | max | 55 kt | - | constraint | sim |
| takeoff_ground_roll | max | 350 m | - | constraint | sim |
| landing_distance | max | 500 m | - | constraint | sim |
| climb_rate | min | 1000 ft/min | - | constraint | sim |
| service_ceiling | min | 16000 ft | - | constraint | sim |

Requisitos não definidos (livres / por omissão): endurance, cruise_altitude, load_factor, turn_rate, mtow, wing_span, power_available, thrust_available, unit_cost, noise, mtow_objective

### Validação

- **info**: Nz das equações de massa = 1.5 × n_lim do diagrama V-n (3.80, manobra; cs_23)
- **info**: Massa do caixão da asa (Megson/Bruhn) = 74.74 kg vs Raymer Eq. 15.46 109.36 kg (razão 0.68); usado: Raymer
- **warning**: Desempenho por segmentos não cumpre: distância de aterragem (Raymer 17.9, total 50 ft): 557.5 m vs requerido ≤ 500 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)

## 2. Peso à descolagem (Raymer Cap. 3; Hepperle 2012 para elétrico)

| grandeza | valor |
|---|---|
| W0 [kg] | 1177 |
| We [kg] | 769.3 |
| Combustível/bateria [kg] | 207.6 |
| Payload + tripulação [kg] | 200 |
| We/W0 | 0.6537 |
| Wf/W0 | 0.1764 |
| Energia bateria nominal [Wh] | - |

Pernas da missão: cruise 1300000 (SI) @ V=77.2 m/s, L/D=8.0, h=0 m

## 2a. Estimativa de pesos por componentes (Raymer 6th ed. Cap. 15 + sistemas)

Valor inicial do peso vazio: Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb) 'ga_single_engine'.

Fator de carga último Nz = 5.70 (1.5 × limite). Iteração: estatística → geometria → componentes → novo We → re-dimensionar, até convergir (histórico na secção 8).

| grupo | item | kg | % W0 | método |
|---|---|---|---|---|
| structure | asa | 109.4 | 9.292 | Raymer Eq. 15.46 |
| structure | empenagem horizontal | 9.812 | 0.8336 | Raymer Eq. 15.47 |
| structure | empenagem vertical | 5.272 | 0.4479 | Raymer Eq. 15.48 |
| structure | fuselagem | 116 | 9.858 | Raymer Eq. 15.49 (unpressurized) |
| structure | trem principal | 72.66 | 6.173 | Raymer Eq. 15.50 |
| structure | trem de nariz | 16.78 | 1.425 | Raymer Eq. 15.51 |
| propulsion | motor instalado (+hélice, berço, capota) | 258.5 | 21.97 | Raymer Eq. 15.52, Wen = P/1.1 kW/kg (ASSUMPTION — give engine_dry_mass_kg) |
| propulsion | sistema de combustível | 31.04 | 2.637 | Raymer Eq. 15.53 |
| equipment | comandos de voo (cabos/hastes) | 18.15 | 1.542 | Raymer Eq. 15.54 |
| equipment | hidráulica | 1.004 | 0.08533 | Raymer Eq. 15.55 (Kh=0.013, M=0.1) |
| equipment | aviónica instalada | 25.12 | 2.134 | Raymer Eq. 15.57, Wuav 15 kg (user) |
| equipment | sistema elétrico | 66.58 | 5.656 | Raymer Eq. 15.56 |
| equipment | interiores (bancos, cintos...) | 39.02 | 3.315 | Raymer Eq. 15.59 |


Resumo por grupo e composição de W0:

| grupo | kg | % W0 |
|---|---|---|
| structure | 329.9 | 28.03 |
| propulsion | 289.6 | 24.6 |
| equipment | 149.9 | 12.73 |
| **peso vazio We** | 769.3 | 65.37 |
| combustível / bateria | 207.6 | 17.64 |
| payload | 115 | 9.771 |
| tripulação | 85 | 7.222 |
| **W0** | 1177 | 100 |


Cross-check estatístico (We/W0 das classes publicadas no W0 obtido; 'fora' = W0 fora do intervalo da base de dados):

| classe | We/W0 | We [kg] | na gama | fonte |
|---|---|---|---|---|
| ga_single_engine | 0.5733 | 674.8 | - | Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb) 'ga_single_engine' |
| homebuilt_composite | 0.5668 | 667.1 | - | Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb) 'homebuilt_composite' |
| nicolai_light_ga | 0.6006 | 706.9 | - | Nicolai & Carichner (AIAA 2010) Table 5.1 (We = A W0^B, lb) 'nicolai_light_ga' |


## 3. Design point (diagrama de restrições)

![constraint diagram](constraint_diagram.png)

- **W0/S = 1050.3 N/m² (107.10 kg/m²)**
- **P/W_SL = 148.2 W/kg** → P_SL = 174 kW
- Restrições ativas: Vmax 85 m/s @ 0 m, Perda 28.3 m/s
- Área alar S = 10.989 m²

## 4. Geometria de primeira iteração

| parâmetro | valor |
|---|---|
| S_m2 | 10.99 |
| AR | 8 |
| span_m | 9.376 |
| taper | 0.5 |
| c_root_m | 1.563 |
| c_tip_m | 0.7814 |
| MAC_m | 1.215 |
| y_MAC_m | 2.084 |
| sweep_c4_deg | 0 |
| sweep_LE_deg | 2.386 |
| t/c | 0.135 |

Fuselagem: L = 8.12 m, D = 1.160 m. Empenagem horizontal S = 1.918 m², vertical S = 0.846 m², braço = 4.87 m (coef. de volume, Raymer Eq. 6.28–6.29).

Caixão da asa (parametrizado na geometria, análise na Fase 2): longarinas a 20%/65% c, largura na raiz 0.703 m.

## 5. Aerodinâmica (Raymer Cap. 12 / DATCOM)

![polar](drag_polar.png)

- CLα = 4.717 /rad (0.0823 /deg)
- CLmax limpo / descolagem / aterragem = 1.44 / 1.71 / 2.14
- CD0 = 0.03196, K = 0.0491 (e = 0.811), (L/D)max = 12.62 a CL = 0.81

Decomposição do CD0 (component build-up):

| component | Swet_m2 | Cf | FF | Q | CD0 |
|---|---|---|---|---|---|
| wing | 18.9 | 0.002675 | 1.337 | 1 | 0.00615 |
| htail | 3.892 | 0.002951 | 1.241 | 1.04 | 0.001349 |
| vtail | 1.716 | 0.002899 | 1.225 | 1.04 | 0.0005764 |
| fuselage | 24.15 | 0.002282 | 1.192 | 1 | 0.005979 |

D/q adicional (trem, antenas, ...): 0.1800 m²; L&P: 5%

## 6. Verificações

- ✅ `regulatory_category` — cs_23: W0 1177.0 kg <= 8618 kg
- ✅ `static_margin` — SM no CG traseiro 10.0 % (alvo 10 %; dianteiro 12.0 %) — posicionamento da asa por bisseção
- ✅ `trim` — CLmax limpo (CG dianteiro): δe -7.7°; cruzeiro (CG dianteiro): δe -2.7°
- ✅ `hq:scissor` — S_h/S atual 0.175 vs mínimo 0.175 (estabilidade 0.175 no CG traseiro, controlo 0.020 a CLmax no CG dianteiro; dimensionante: estabilidade)
- ✅ `hq:short_period` — período curto ζ = 0.786 → Nível 1 (N1: 0.30–2.00; MIL-F-8785C Table IV, Classe I, Cat. B)
- ✅ `hq:CAP` — CAP = ω²/(n/α) [1/(g s²)] = 1.47 → Nível 1 (N1: 0.085–3.6; MIL-F-8785C Figs. 1–3, Classe I, Cat. B)
- ✅ `hq:phugoid` — fugóide ζ = 0.105 → Nível 1 (N1: ≥ 0.04; MIL-F-8785C 3.2.1.2, Classe I, Cat. B)
- ❌ `hq:dutch_roll` — rolamento holandês ζ / ζω / ω = -0.885 / -0.282 / 0.32 → Nível >3 (N1: 0.08 / 0.15 / 0.4; MIL-F-8785C Table VI, Classe I, Cat. B)
- ✅ `hq:roll` — rolamento τ_R [s] = 0.157 → Nível 1 (N1: ≤ 1.4; MIL-F-8785C Table VII, Classe I, Cat. B)
- ✅ `hq:spiral` — espiral T2 [s] (∞ = estável) = inf → Nível 1 (N1: ≥ 20; MIL-F-8785C Table VIII, Classe I, Cat. B)
- ✅ `aeroel:divergence` — divergência torsional V = 229.9 m/s EAS vs 133.2 (= 1.2 V_D); margem +73 %
- ✅ `aeroel:reversal` — inversão de aileron V = 226.4 m/s EAS vs 133.2 (= 1.2 V_D); margem +70 %
- ✅ `aeroel:flutter` — flutter binário V = 137.8 m/s EAS vs 133.2 (= 1.2 V_D); margem +3 %
- ✅ `aeroel:aeer45` — AEER-45 / 23.629(d): F = 0.00122 vs F_max = 0.00325 (balanceamento do aileron não avaliado)
- ✅ `perf:range` — distância de cruzeiro (segmentos): 1328 km vs requerido ≥ 1300 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ✅ `perf:service_ceiling` — teto de serviço (Anderson): 6324 m vs requerido ≥ 4877 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ✅ `perf:climb_rate` — ROC máx. ao nível do mar: 7.975 m/s vs requerido ≥ 5.08 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ✅ `perf:takeoff_ground_roll` — corrida de descolagem (Raymer 17.8): 213.7 m vs requerido ≤ 350 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ❌ `perf:landing_distance` — distância de aterragem (Raymer 17.9, total 50 ft): 557.5 m vs requerido ≤ 500 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)

## 8. Histórico do ciclo MDA (peso ↔ design point ↔ geometria ↔ arrasto)

| iter | W0 | We/W0 usado | We | Wf | n_lim (V-n) | asa Raymer [kg] | asa caixão [kg] | We_comp | We_comp/W0 | CD0 | W/S | P/W | L/D_max | aero |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 862.5 | 0.6063 | 522.9 | 139.6 | 3.8 | 74.09 | 49.58 | 534.9 | 0.6201 | 0.03944 | 1050 | 10.78 | 11.36 | manual |
| 2 | 918.8 | 0.5821 | 534.9 | 184 | 3.8 | 80.25 | 53.85 | 666.3 | 0.7252 | 0.03773 | 1050 | 18.36 | 11.62 | manual |
| 3 | 1076 | 0.6193 | 666.3 | 209.7 | 3.8 | 97.78 | 66.32 | 751.5 | 0.6985 | 0.0339 | 1050 | 17.62 | 12.26 | manual |
| 4 | 1164 | 0.6455 | 751.5 | 212.6 | 3.8 | 107.9 | 73.66 | 776.5 | 0.667 | 0.03218 | 1050 | 15.95 | 12.58 | manual |
| 5 | 1187 | 0.6543 | 776.5 | 210.2 | 3.8 | 110.5 | 75.57 | 776.6 | 0.6544 | 0.03179 | 1050 | 15.21 | 12.66 | manual |
| 6 | 1185 | 0.6554 | 776.6 | 208.4 | 3.8 | 110.3 | 75.42 | 772.6 | 0.652 | 0.03182 | 1050 | 15.03 | 12.65 | manual |
| 7 | 1180 | 0.6546 | 772.6 | 207.7 | 3.8 | 109.7 | 75.03 | 770.2 | 0.6525 | 0.0319 | 1050 | 15.05 | 12.64 | manual |
| 8 | 1178 | 0.654 | 770.2 | 207.6 | 3.8 | 109.4 | 74.81 | 769.3 | 0.6532 | 0.03194 | 1050 | 15.08 | 12.63 | manual |
| 9 | 1177 | 0.6537 | 769.3 | 207.6 | 3.8 | 109.4 | 74.73 | 769.2 | 0.6536 | 0.03196 | 1050 | 15.1 | 12.62 | manual |
| 10 | 1177 | 0.6536 | 769.2 | 207.6 | 3.8 | 109.3 | 74.73 | 769.3 | 0.6537 | 0.03196 | 1050 | 15.11 | 12.62 | manual |
| 11 | 1177 | 0.6536 | 769.3 | 207.6 | 3.8 | 109.3 | 74.73 | 769.3 | 0.6537 | 0.03196 | 1050 | 15.11 | 12.62 | manual |
| 12 | 1177 | 0.6536 | 769.3 | 207.6 | 3.8 | 109.4 | 74.74 | 769.3 | 0.6537 | 0.03196 | 1050 | 15.11 | 12.62 | manual |
| 13 | 1177 | 0.6537 | 769.3 | 207.6 | 3.8 | 109.4 | 74.74 | 769.3 | 0.6537 | 0.03196 | 1050 | 15.11 | 12.62 | manual |
| 14 | 1177 | 0.6537 | 769.3 | 207.6 | 3.8 | 109.4 | 74.74 | 769.3 | 0.6537 | 0.03196 | 1050 | 15.11 | 12.62 | manual |

### Comparação AVL / baixa fidelidade vs métodos de manual

| grandeza | manual | AVL / baixa fid. | método manual | nota |
|---|---|---|---|---|
| CLα asa [/rad] | 4.717 | 5.588 | DATCOM / Raymer Eq. 12.6 | AVL: avião completo (asa + cauda), sem fuselagem |
| CDi a CL = 0.288 | 0.004071 | 0.003509 | Oswald Raymer e = 0.811 | AVL e (Trefftz) = 0.931; Oswald inclui arrasto viscoso dependente de CL |
| x̄_NP [MAC] | 0.5008 | 0.536 | Raymer Eq. 16.9 + Torenbeek (fuselagem) | sem fuselagem: 0.542 (AVL não modela a fuselagem) |
| CLδe [/rad] | 0.3916 | 0.4142 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) |  |
| Cmδe [/rad] | -1.57 | -1.572 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) | AVL: Cmδe no CG traseiro; Cnδr com convenção de sinal AVL |
| |Clδa| [/rad] | 0.3215 | 0.2409 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) |  |
| Cnδr [/rad] | -0.08167 | 0.07013 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) | AVL: Cmδe no CG traseiro; Cnδr com convenção de sinal AVL |

## 11. Estruturas: V-n, cargas na asa e caixão (Fase 2)

![V-n](vn_diagram.png)

| grandeza | valor |
|---|---|
| regulation | cs_23 |
| category | normal |
| VS1_EAS_m_s | 34.51 |
| VA_EAS_m_s | 67.27 |
| VC_EAS_m_s | 79.26 |
| VD_EAS_m_s | 111 |
| n_manoeuvre_pos | 3.8 |
| n_manoeuvre_neg | -1.52 |
| n_gust_VC | 3.491 / -1.491 |
| n_gust_VD | 2.744 / -0.744 |
| mu_g | 30.5 |
| Kg | 0.7497 |
| n_limit_pos | 3.8 |
| n_limit_neg | -1.52 |
| governing | manobra |
| n_ultimate | 5.7 |

Cláusulas aplicadas: 23.333 (envelope); 23.335(a) VC ≥ 32.9√(W/S) kt = 154 kt EAS; 23.335(b) VD ≥ max(1.25 VC, 1.40 VC,min); 23.335(c) VA ≥ VS√n; 23.337 limit manoeuvring load factors; 23.341 gust load factors (Pratt–Walker)


Condição crítica de dimensionamento: n = 3.80 (manobra), q a VD = 111.0 m/s EAS.

![loads](wing_loads.png)

Raiz (limite): V = 19887.1 N, M = 40394.2 N·m, T = 4693.9 N·m.

![box](wing_box.png)

| parcela | massa [kg] |
|---|---|
| caps | 0 |
| covers_skin_stringers | 39.24 |
| core | 0 |
| webs | 3.328 |
| web_uprights | 1.414 |
| LE_TE_skins | 14.28 |
| ribs | 1.532 |
| ideal | 59.79 |
| nonoptimum | 14.95 |
| total | 74.74 |

Cross-check da massa da asa:

| método | massa da asa [kg] |
|---|---|
| Raymer Eq. 15.46 (estatístico) | 109.4 |
| caixão Megson/Bruhn, carga Schrenk (Al 2024-T3 (MMPDS typical — verify)) | 74.74 |
| caixão Megson/Bruhn, carga AVL | 73.66 |

- Revestimentos reforçados (Z): σ ótimo de Farrar F = 0.81 com corte por crippling de Needham 234 MPa (b'/t = 12 — PRESSUPOSTO); passo de reforçadores na raiz 42 mm (≈ 17 reforçadores/painel); σ raiz 175 MPa
- Almas: tensão diagonal de Kuhn, k raiz = 0.68, montantes a d = h (PRESSUPOSTO), C1 = C2 ≈ 0 (α ≈ 45°, banzos rígidos — PRESSUPOSTO); admissível de τ_max = Fsu (curva Bruhn Fig. C11.19 não digitalizada — LIMITAÇÃO)
- Banzo inferior: tração Ftu e compressão no caso negativo n_neg/n_pos = 0.40
- MMPDS typical 2024-T3 sheet: Fcy 269 MPa, Ftu 434 MPa, Fsu 262 MPa, G 27.6 GPa — verify
- 16 nervuras (passo 0.73 m)
- fator não-ótimo 1.25 (PRESSUPOSTO)
- superfícies de comando, flaps e carenagens NÃO incluídos (secundários)

## 12. Estabilidade e controlo (Fase 2: Raymer Cap. 16, Etkin & Reid, Nelson)

![cg](cg_envelope.png)

- asa posicionada para SM = 10% no CG mais recuado (ápice a 14.2% L); ápice da asa a x = 1.150 m
- Ponto neutro x̄_NP = 0.501 MAC (manual), 0.536 (AVL); dε/dα = 0.375
- **Margem estática: 12.0 % (CG dianteiro) … 10.0 % (CG traseiro)**
- AVL, cruzeiro compensado no CG traseiro: α = -15.54°, δe = 21.75°, Cnβ = 0.0807, Clβ = -0.0454, Cmq = -19.39
- Coef. de volume: V_h = 0.700, V_v = 0.0400 (Raymer Table 6.4: 0.7 / 0.04)

| caso | massa [kg] | x_cg [m] | x̄_cg [MAC] | SM |
|---|---|---|---|---|
| vazio + tripulação | 854.3 | 1.724 | 0.4008 | 0.1 |
| sem payload | 1062 | 1.7 | 0.3811 | 0.1197 |
| MTOW | 1177 | 1.703 | 0.3829 | 0.1179 |
| sem combustível (ZFW) | 969.3 | 1.724 | 0.4007 | 0.1001 |

Compensação (trim) no CG dianteiro:

| condição | CL | δe [°] | ok (|δe| ≤ máx.) |
|---|---|---|---|
| CLmax limpo (CG dianteiro) | 1.44 | -7.748 | True |
| cruzeiro (CG dianteiro) | 0.288 | -2.717 | True |

- Clδa comparado em módulo (convenções de sinal do aileron diferem entre AVL e Nelson).
- Estações de CG dos componentes: PRESSUPOSTOS (Roskam Part V Table 8.1, valores típicos) — substituir pelas posições do layout real em assumptions.stability.stations.

## 13. Desempenho por segmentos (Fase 2: Raymer Cap. 17, Anderson)

Orçamento utilizável: Wf / 1.06 (reserva + não utilizável 6 %, Raymer Eq. 3.11).

Missão requerida (segmentos):

| segmento | t [min] | dist [km] | consumo [kg] | h [m] | V [m/s] | nota |
|---|---|---|---|---|---|---|
| aquecimento + descolagem | 0 | 0 | 35.31 | 0→0 | 0 | Raymer Table 3.2 (0.970) |
| subida (V_y) | 0 | 0 | 0 | 0→0 | 0 | potência de subida, integrado (V médio) |
| cruzeiro | 280.8 | 1300 | 151.6 | 0→0 | 77.17 |  |
| descida (L/D máx, ralenti) + aterragem | 0 | 0 | 5.708 | 0→0 | 42.28 | Raymer 0.995 (combustível) |

Missão até esgotar o orçamento: **alcance 1328.0 km, endurance 4.78 h**.

| segmento | t [min] | dist [km] | consumo [kg] | h [m] | V [m/s] | nota |
|---|---|---|---|---|---|---|
| aquecimento + descolagem | 0 | 0 | 35.31 | 0→0 | 0 | Raymer Table 3.2 (0.970) |
| subida (V_y) | 0 | 0 | 0 | 0→0 | 0 | potência de subida, integrado (V médio) |
| cruzeiro | 286.8 | 1328 | 154.8 | 0→0 | 77.17 | estendido até esgotar o orçamento |
| descida (L/D máx, ralenti) + aterragem | 0 | 0 | 5.708 | 0→0 | 42.21 | Raymer 0.995 (combustível) |

Requisitos vs desempenho por segmentos:

| requisito | grandeza | obtido | requerido | unidade | ok |
|---|---|---|---|---|---|
| range | distância de cruzeiro (segmentos) | 1328 | 1300 | km | ✅ |
| service_ceiling | teto de serviço (Anderson) | 6324 | 4877 | m | ✅ |
| climb_rate | ROC máx. ao nível do mar | 7.975 | 5.08 | m/s | ✅ |
| takeoff_ground_roll | corrida de descolagem (Raymer 17.8) | 213.7 | 350 | m | ✅ |
| landing_distance | distância de aterragem (Raymer 17.9, total 50 ft) | 557.5 | 500 | m | ❌ |

![payload-range](payload_range.png)

| ponto | payload_kg | combustível_kg | massa_kg | range_km |
|---|---|---|---|---|
| A | 115 | 0 | 969.3 | 0 |
| B | 115 | 207.6 | 1177 | 1328 |
| C | 115 | 207.6 | 1177 | 1328 |
| D (ferry) | 0 | 207.6 | 1062 | 1389 |

Nota: capacidade de combustível 207.6 kg (= combustível de projeto, PRESSUPOSTO — dar performance.fuel_capacity_kg).

![climb](climb_ceiling.png)

- ROC máx. ao nível do mar 7.98 m/s; teto de serviço 6324 m; teto absoluto 6834 m
- Descolagem (Raymer 17.8): corrida 214 m, total sobre 15 m 373 m (V_TO 34.8 m/s)
- Aterragem (Raymer 17.9): corrida 251 m, total sobre 15 m 557 m (μ_travagem 0.4; aproximação γ = 3° — `performance.approach_angle_deg`, por omissão o máximo de 5.2 % / 3° de CS/14 CFR 23.75(a)(1))

- Os resultados de segmentos usam a mesma polar e reservas do dimensionamento; diferenças face aos requisitos vêm da subida/descida integradas vs. frações históricas (Raymer Table 3.2).

## 14. Caixão da asa dimensionado à estabilidade (Fase 3: Bruhn C5/C7/C11, Farrar, Kuhn)

| caixão | massa [kg] | / Raymer 15.46 |
|---|---|---|
| resistência (Fase 2, limite inferior) | 67.45 | 0.6168 |
| encurvadura (Fase 3, Al 2024-T3 (MMPDS typical — verify)) | 74.74 | 0.6834 |
| Raymer Eq. 15.46 (asa completa, estatístico) | 109.4 | 1 |

Parcelas (caixão de encurvadura):

| parcela | massa [kg] |
|---|---|
| caps | 0 |
| covers_skin_stringers | 39.24 |
| core | 0 |
| webs | 3.328 |
| web_uprights | 1.414 |
| LE_TE_skins | 14.28 |
| ribs | 1.532 |
| ideal | 59.79 |
| nonoptimum | 14.95 |
| total | 74.74 |

- Almas Kuhn: fator de tração diagonal k máx. 0.676 (k = 0: alma resistente ao corte, sem tração diagonal)
- Passo dos reforçadores: 26–119 mm (encurvadura local do revestimento, k = 4)
- Revestimentos reforçados (Z): σ ótimo de Farrar F = 0.81 com corte por crippling de Needham 234 MPa (b'/t = 12 — PRESSUPOSTO); passo de reforçadores na raiz 42 mm (≈ 17 reforçadores/painel); σ raiz 175 MPa
- Almas: tensão diagonal de Kuhn, k raiz = 0.68, montantes a d = h (PRESSUPOSTO), C1 = C2 ≈ 0 (α ≈ 45°, banzos rígidos — PRESSUPOSTO); admissível de τ_max = Fsu (curva Bruhn Fig. C11.19 não digitalizada — LIMITAÇÃO)
- Banzo inferior: tração Ftu e compressão no caso negativo n_neg/n_pos = 0.40
- MMPDS typical 2024-T3 sheet: Fcy 269 MPa, Ftu 434 MPa, Fsu 262 MPa, G 27.6 GPa — verify
- 16 nervuras (passo 0.73 m)
- fator não-ótimo 1.25 (PRESSUPOSTO)
- superfícies de comando, flaps e carenagens NÃO incluídos (secundários)

## 15. Aeroelasticidade clássica (Fase 3)

V_D = 111.0 m/s EAS.

| fenómeno | V [m/s EAS] | requerido 1.2 V_D | margem | ok | método |
|---|---|---|---|---|---|
| divergência torsional | 229.9 | 133.2 | +73 % | ✅ | W&C 8.3 / Bisplinghoff 8-2 (faixas + FE) |
| inversão do aileron | 226.4 | 133.2 | +70 % | ✅ | W&C 8.4, Glauert (flap 2D) |
| flutter binário (flexão–torção) | 137.8 | 133.2 | +3 % | ✅ | W&C 11 (modos assumidos, quase-estacionário) |

- Frequências desacopladas: flexão 8.46 Hz, torção 31 Hz; flutter a 24 Hz
- AEER-45 (fator de flexibilidade torsional da asa): F = 1.217e-03 vs F_max = 200/V_D² = 3.246e-03 → OK

![flutter](flutter_vg.png)

### Acoplamento aero-estrutural estático (OpenAeroStruct, VLM + caixão)

| ponto | modelo | α [°] | CL | CDi | CLα [/rad] | flecha ponta [m] | torção ponta [°] |
|---|---|---|---|---|---|---|---|
| cruise | rígido | 3.436 | 0.288 | 0.003193 | 4.797 | 5.095e-06 | 3.204e-05 |
| cruise | flexível | 3.281 | 0.288 | 0.0032 | 5.026 | 0.05196 | 0.3262 |
| manobra (n_lim, V_D EAS, nível do mar) | rígido | 6.323 | 0.5293 | 0.01079 | 4.777 | 1.93e-05 | 0.0001213 |
| manobra (n_lim, V_D EAS, nível do mar) | flexível | 5.719 | 0.5293 | 0.01086 | 5.3 | 0.2012 | 1.258 |

- Efeito da forma deformada no arrasto induzido de cruzeiro: K_flex/K = 1.0020
- Missão por segmentos: rígido 1328.0 km / 4.781 h → flexível 1328.0 km / 4.781 h (comparação com o resultado desacoplado da Fase 2)
- OpenAeroStruct VLM (sem viscoso/onda: só arrasto induzido) + FEM de caixão 'wingbox' acoplados por NLBGS; rígido = E, G × 10⁴
- secção do caixão: NACA-4 entre longarinas; espessuras de alma/revestimento do caixão acdt (5 pontos de controlo); revestimento único equivalente que reproduz EI(y) do caixão acdt e G ajustado para GJ (PRESSUPOSTO)
- sem alívio de peso estrutural nem de combustível na asa (conservativo para a deformação)
- índice de falha OAS (von Mises/KS, σ_adm = σ_cap/1.5) na manobra: +0.208 (< 0 = OK) — critério de resistência do OAS sobre o revestimento equivalente — INDICATIVO (o dimensionamento é o do caixão acdt)
- massa da asa 109.36 kg distribuída ∝ corda; CG da secção a 0.50 c; eixo elástico a 0.425 c (meio do caixão), e = 0.175 c atrás do c.a.; a_w = 6.283/rad (2D, teoria das faixas — sem correção 3D/compressibilidade)
- encastramento na parede da fuselagem y0 = 0.580 m; EI/GJ do caixão buckling
- requisito: livre de flutter/divergência/inversão até 1.2 V_D = 133.2 m/s EAS (14 CFR 23.629(c) legado; CS/14 CFR 23.2245 'suficientemente além'; STANAG 4671 USAR.629 — verificar)
- flutter: modelo binário de modos assumidos (W&C Cap. 11), aerodinâmica quase-estacionária — ESTIMATIVA; a análise racional exige modos FEM + DLM (Fase 4)

## 16. Diagrama de tesoura, modos dinâmicos e qualidades de voo (Fase 3)

![scissor](scissor.png)

- S_h/S atual 0.175; requerido 0.175 (estabilidade 0.175, controlo 0.02; dimensionante: estabilidade) → ✅ (Torenbeek Cap. 9)
- linha de controlo: trim a CLmax limpo 1.44 com δe = −25°, τ_e = 0.661, Cm0 = -0.0400 (Raymer 16.13); momento dos flaps e efeito de solo NÃO incluídos
- massa da cauda não realimentada (posição da asa e braço fixos)

![modes](root_locus.png)

| modo | ωn [rad/s] | ζ | período [s] | τ / T [s] |
|---|---|---|---|---|
| período curto | 5.101 | 0.786 | 1.992 | - |
| fugóide | 0.1431 | 0.1048 | 44.14 | - |
| rolamento holandês | 0.3183 | -0.8853 | - | - |
| rolamento (constante de tempo) | - | - | - | 0.1566 |
| espiral estável | - | - | - | 0.5918 |

- n/α = 17.7 g/rad, CAP = 1.47 1/(g s²)
- Inércias (Roskam V, soma por componentes): Ixx 1.94e+03, Iyy 1.77e+03, Izz 3.71e+03 kg·m²
- derivadas de taxa e laterais: AVL (sem fuselagem) + Cnβ da fuselagem (Raymer 16.47) -0.0884
- Cmα = −CLα·SM no CG de MTOW (ponto neutro de manual com fuselagem)
- inércias por soma de componentes (Roskam Parte V) — PRESSUPOSTOS de estações

Qualidades de voo — MIL-F-8785C, Classe I, categoria B (nível exigido 1):

| modo | valor | nível | limite N1 | ref |
|---|---|---|---|---|
| período curto ζ | 0.786 | 1 | 0.30–2.00 | MIL-F-8785C Table IV |
| CAP = ω²/(n/α) [1/(g s²)] | 1.473 | 1 | 0.085–3.6 | MIL-F-8785C Figs. 1–3 |
| fugóide ζ | 0.1048 | 1 | ≥ 0.04 | MIL-F-8785C 3.2.1.2 |
| rolamento holandês ζ / ζω / ω | -0.885 / -0.282 / 0.32 | 4 | 0.08 / 0.15 / 0.4 | MIL-F-8785C Table VI |
| rolamento τ_R [s] | 0.1566 | 1 | ≤ 1.4 | MIL-F-8785C Table VII |
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
    engine_kW_per_kg: 1.1
    avionics_uninstalled_kg: 15
aero:
  AR: 8
  taper: 0.5
  sweep_c4_deg: 0.0
  tc_root: 0.15
  tc_tip: 0.12
  xc_max_t: 0.3
  airfoil: NACA 23015
  clmax_airfoil: 1.6
  flap:
    kind: slotted
    flapped_area_ratio: 0.6
  oswald: null
  cfe: 0.0055
  swet_sref: 4.0
  laminar:
    wing: 0.2
    htail: 0.2
    vtail: 0.2
    fuselage: 0.05
  roughness: smooth_paint
  Q: {}
  lp_fraction: 0.05
  extra_drag_areas_m2:
    fixed_gear_faired: 0.12
    cooling_and_misc: 0.06
  CL_ground: 0.5
  dCD0_takeoff: 0.01
  mu_roll: 0.04
  fidelity: handbook
  airfoil_solver: xfoil
propulsion:
  eta_cruise: 0.82
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
