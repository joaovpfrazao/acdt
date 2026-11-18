# Relatório de dimensionamento — UAV ISR elétrico 25 kg

_acdt 0.1.0 · Fase 1 (conceptual) + 1E (sistemas) + Fase 2 (baixa fidelidade)_

UAV de asa fixa lançado por catapulta e recuperado por paraquedas/rede, com gimbal EO/IR. Sem requisito de pista (não há restrição de descolagem/aterragem).


**Resultado:** ❌ INVIÁVEL / requisitos não cumpridos

**Verificação por segmentos (Fase 2):** ⚠️ pelo menos um requisito não cumprido na missão por segmentos (ver §13)

## 1. Requisitos desta corrida

| requisito | sentido | valor | qualificadores | estágios | avaliado |
|---|---|---|---|---|---|
| propulsion_type | target | electric | - | context | sim |
| regulatory_category | target | easa_specific | - | check, systems | sim |
| payload_mass | target | 4.0 kg | - | sizing | sim |
| endurance | min | 2.5 h | - | sizing | sim |
| cruise_speed | target | 22 m/s | - | constraint, sizing | sim |
| cruise_altitude | target | 600 m | - | context | sim |
| stall_speed | max | 13 m/s | - | constraint | sim |
| climb_rate | min | 3.0 m/s | - | constraint | sim |
| service_ceiling | min | 3000 m | - | constraint | sim |
| wing_span | max | 4.2 m | - | check | sim |
| mtow | max | 25 kg | - | check | sim |

Requisitos não definidos (livres / por omissão): crew_mass, range, max_speed, load_factor, turn_rate, takeoff_ground_roll, landing_distance, power_available, thrust_available, unit_cost, noise, mtow_objective

### Validação

- **info**: Valor inicial estatístico We/W0 = 0.67 não fecha (We/W0 + Wf/W0 > 0.98); iteração por componentes reiniciada com We/W0 = 0.30.
- **info**: Nz das equações de massa = 1.5 × n_lim do diagrama V-n (5.36, rajada; stanag_4671)
- **warning**: n_lim = 5.36 está acima da linha de perda mesmo a VD (n = 3.21 com CLmax quase-estático): valor CONSERVATIVO mantido (a perda dinâmica numa rajada pode excedê-lo); VC baixo face a VS1 — rever VC/CLmax antes de dimensionar
- **info**: Massa do caixão da asa (Megson/Bruhn) = 3.62 kg vs Raymer Eq. 15.46 4.66 kg (razão 0.78); usado: Raymer
- **warning**: Massa da fuselagem L1 / Raymer Eq. 15.49 = 1.47 (1.7 kg vs 1.2 kg).
- **info**: Energia de descolagem + subida no dimensionamento = 99.1 Wh (modelo de segmentos: 1 min à potência de descolagem + subida integrada a V_y — o mesmo da verificação; Hepperle só energia potencial daria 61.7 Wh)
- **info**: Sem trem de aterragem (landing_gear: none) — lançamento/recuperação como itens do utilizador.
- **info**: W0 = 23 kg está abaixo da base de dados das equações GA de Raymer (~1000–8000 lb): extrapolação — calibrar com dados próprios (calibration).
- **warning**: We/W0 por componentes = 0.499 fora da banda estatística [0.77, 0.89] (±15 %) — rever itens em falta (recuperação, suportes, pintura, cablagem de sinal) ou calibrar com dados próprios.

## 2. Peso à descolagem (Raymer Cap. 3; Hepperle 2012 para elétrico)

| grandeza | valor |
|---|---|
| W0 [kg] | 23.42 |
| We [kg] | 11.69 |
| Combustível/bateria [kg] | 7.731 |
| Payload + tripulação [kg] | 4 |
| We/W0 | 0.4991 |
| Wf/W0 | 0.3301 |
| Energia bateria nominal [Wh] | 1766 |

Pernas da missão: loiter 9000 (SI) @ V=22.0 m/s, L/D=19.0, h=600 m

## 2a. Estimativa de pesos por componentes (Raymer 6th ed. Cap. 15 + sistemas)

Valor inicial do peso vazio: Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb) 'uav_small'.

Fator de carga último Nz = 8.05 (1.5 × limite). Iteração: estatística → geometria → componentes → novo We → re-dimensionar, até convergir (histórico na secção 8).

| grupo | item | kg | % W0 | método |
|---|---|---|---|---|
| structure | asa | 4.658 | 19.89 | Raymer Eq. 15.46; composite x0.875 (Raymer Table 15.4) |
| structure | empenagem horizontal | 0.3763 | 1.607 | minimum gauge: Swet 0.418 m² x 0.9 kg/m² (user layup) > Raymer Eq. 15.47 |
| structure | empenagem vertical | 0.3096 | 1.322 | minimum gauge: Swet 0.344 m² x 0.9 kg/m² (user layup) > Raymer Eq. 15.48 |
| structure | fuselagem | 1.091 | 4.658 | Raymer Eq. 15.49 (unpressurized); composite x0.925 (Raymer Table 15.4) |
| propulsion | motor(es) + ESC(s) | 1.05 | 4.483 | selected components (Phase 1E database) |
| propulsion | hélice(s) | 0.08 | 0.3416 | user (datasheet) |
| equipment | comandos (hastes/charneiras) | 0.07691 | 0.3284 | Raymer Eq. 15.54 |
| equipment | servos | 0.17 | 0.7259 | selected components (Phase 1E) |
| equipment | autopiloto + aviónica + extras | 0.075 | 0.3202 | selected components / user list |
| equipment | cablagem de potência | 0.29 | 1.238 | sized wire gauges x length x ρCu (IEC 60028) x1.3 insulation + 5 connectors x 0.01 kg (ASSUMPTIONS) |
| user_items | paraquedas de recuperação + ejetor | 1 | 4.27 | user-listed item |
| user_items | suporte/amortecimento do gimbal | 0.3 | 1.281 | user-listed item |
| equipment | datalink C2 + antenas | 0.25 | 1.067 | user-listed item |
| equipment | GNSS + bússola (x2) | 0.1 | 0.427 | user-listed item |
| equipment | pitot/ADS-B | 0.1 | 0.427 | user-listed item |
| equipment | cablagem de sinal + conectores | 0.3 | 1.281 | user-listed item |
| user_items | ferragens/fixações/pintura | 0.4 | 1.708 | user-listed item |
| allowance | margem de crescimento/integração | 1.063 | 4.538 | 10% of the build-up (ASSUMPTION, labelled) |


Resumo por grupo e composição de W0:

| grupo | kg | % W0 |
|---|---|---|
| structure | 6.435 | 27.48 |
| propulsion | 1.13 | 4.825 |
| equipment | 1.362 | 5.815 |
| user_items | 1.7 | 7.259 |
| allowance | 1.063 | 4.538 |
| **peso vazio We** | 11.69 | 49.91 |
| combustível / bateria | 7.731 | 33.01 |
| payload | 4 | 17.08 |
| tripulação | 0 | 0 |
| **W0** | 23.42 | 100 |


Notas do build-up:

- Sem trem de aterragem (landing_gear: none) — lançamento/recuperação como itens do utilizador.
- W0 = 23 kg está abaixo da base de dados das equações GA de Raymer (~1000–8000 lb): extrapolação — calibrar com dados próprios (calibration).

Cross-check estatístico (We/W0 das classes publicadas no W0 obtido; 'fora' = W0 fora do intervalo da base de dados):

| classe | We/W0 | We [kg] | na gama | fonte |
|---|---|---|---|---|
| uav_small | 0.7656 | 17.93 | - | Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb) 'uav_small' |
| uav_tactical_recce_ucav | 0.8885 | 20.81 | - | Raymer 6th ed. Table 3.1 (We/W0 = A W0^C, W0 in lb) 'uav_tactical_recce_ucav' |
| nicolai_uav_prop_endurance_lt12h | 1.051 | 24.61 | - | Nicolai & Carichner (AIAA 2010) Table 5.1 (We = A W0^B, lb) 'nicolai_uav_prop_endurance_lt12h' |
| nicolai_uav_prop_endurance_gt12h | 0.8002 | 18.74 | - | Nicolai & Carichner (AIAA 2010) Table 5.1 (We = A W0^B, lb) 'nicolai_uav_prop_endurance_gt12h' |


## 3. Design point (diagrama de restrições)

![constraint diagram](constraint_diagram.png)

- **W0/S = 175.6 N/m² (17.91 kg/m²)**
- **P/W_SL = 50.55 W/kg** → P_SL = 1.18 kW
- Restrições ativas: RC 3.0 m/s @ 0 m, Perda 13.0 m/s
- Área alar S = 1.308 m²

## 4. Geometria de primeira iteração

| parâmetro | valor |
|---|---|
| S_m2 | 1.308 |
| AR | 14 |
| span_m | 4.279 |
| taper | 0.6 |
| c_root_m | 0.382 |
| c_tip_m | 0.2292 |
| MAC_m | 0.312 |
| y_MAC_m | 0.9805 |
| sweep_c4_deg | 0 |
| sweep_LE_deg | 1.023 |
| t/c | 0.12 |

Fuselagem: L = 1.80 m, D = 0.220 m. Empenagem horizontal S = 0.206 m², vertical S = 0.170 m², braço = 0.99 m (coef. de volume, Raymer Eq. 6.28–6.29).

Caixão da asa (parametrizado na geometria, análise na Fase 2): longarinas a 20%/65% c, largura na raiz 0.172 m.

## 5. Aerodinâmica (Raymer Cap. 12 / DATCOM)

![polar](drag_polar.png)

- CLα = 5.119 /rad (0.0893 /deg)
- CLmax limpo / descolagem / aterragem = 1.29 / 1.36 / 1.70
- CD0 = 0.02316, K = 0.0252 (e = 0.902), (L/D)max = 20.69 a CL = 0.96

Decomposição do CD0 (component build-up):

| component | Swet_m2 | Cf | FF | Q | CD0 |
|---|---|---|---|---|---|
| wing | 2.497 | 0.004246 | 1.033 | 1 | 0.008377 |
| htail | 0.4181 | 0.004566 | 0.9916 | 1.04 | 0.001505 |
| vtail | 0.344 | 0.004134 | 0.9782 | 1.04 | 0.001106 |
| fuselage | 1.047 | 0.003471 | 1.13 | 1 | 0.003141 |

D/q adicional (trem, antenas, ...): 0.0080 m²; L&P: 5%

## 6. Verificações

- ➖ `regulatory_category` — easa_specific: no numeric limit
- ❌ `wing_span` — b = 4.28 m vs max 4.20 m
- ✅ `mtow` — W0 = 23.4 kg vs max 25.0 kg
- ✅ `static_margin` — SM no CG traseiro 10.0 % (alvo 10 %; dianteiro 10.0 %) — posicionamento da asa por bisseção
- ✅ `trim` — CLmax limpo (CG dianteiro): δe -11.0°; cruzeiro (CG dianteiro): δe -7.6°
- ✅ `hq:scissor` — S_h/S atual 0.158 vs mínimo 0.158 (estabilidade 0.158 no CG traseiro, controlo 0.091 a CLmax no CG dianteiro; dimensionante: estabilidade)
- ✅ `hq:short_period` — período curto ζ = 0.713 → Nível 1 (N1: 0.30–2.00; MIL-F-8785C Table IV, Classe I, Cat. B) — UAV: indicativo
- ❌ `hq:CAP` — CAP = ω²/(n/α) [1/(g s²)] = 7.62 → Nível 2 (N1: 0.085–3.6; MIL-F-8785C Figs. 1–3, Classe I, Cat. B) — UAV: indicativo
- ✅ `hq:phugoid` — fugóide ζ = 0.0628 → Nível 1 (N1: ≥ 0.04; MIL-F-8785C 3.2.1.2, Classe I, Cat. B) — UAV: indicativo
- ✅ `hq:dutch_roll` — rolamento holandês ζ / ζω / ω = 0.188 / 0.687 / 3.65 → Nível 1 (N1: 0.08 / 0.15 / 0.4; MIL-F-8785C Table VI, Classe I, Cat. B) — UAV: indicativo
- ✅ `hq:roll` — rolamento τ_R [s] = 0.0672 → Nível 1 (N1: ≤ 1.4; MIL-F-8785C Table VII, Classe I, Cat. B) — UAV: indicativo
- ➖ `hq:spiral` — espiral unassessed: declare assumptions.geometry.dihedral_deg (current TrapezoidalWing default Γ=3° is PRESSUPOSTO only; Clβ/spiral need an explicit dihedral — Etkin & Reid 1996 Ch. 6 / MIL-F-8785C Table VIII)
- ✅ `wb:envelope` — Todos os 3 carregamentos dentro dos limites conceptuais; extremos 0.729 m (vazio, 19 kg) e 0.729 m (payload, 23 kg).
- ✅ `aeroel:divergence` — divergência torsional V = 277.5 m/s EAS vs 32.1 (= 1.2 V_D); margem +766 %
- ✅ `aeroel:reversal` — inversão de aileron: não ocorre (V → ∞) vs 32.1 m/s EAS
- ✅ `aeroel:flutter` — flutter binário V = 126.0 m/s EAS vs 32.1 (= 1.2 V_D); margem +293 %
- ✅ `aeroel:aeer45` — AEER-45 / 23.629(d): F = 0.00142 vs F_max = 0.056 (balanceamento do aileron não avaliado)
- ✅ `perf:endurance` — tempo em espera (segmentos): 2.5 h vs requerido ≥ 2.5 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ✅ `perf:service_ceiling` — teto de serviço (Anderson) > 9000 m (não atingido): 9000 m vs requerido ≥ 3000 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)
- ✅ `perf:climb_rate` — ROC máx. ao nível do mar: 3 m/s vs requerido ≥ 3 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento)

## 8. Histórico do ciclo MDA (peso ↔ design point ↔ geometria ↔ arrasto)

| iter | W0 | We/W0 usado | We | Wf | E descolagem+subida [Wh] | n_lim (V-n) | asa Raymer [kg] | asa caixão [kg] | We_comp | We_comp/W0 | CD0 | W/S | P/W | L/D_max | aero |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 11.42 | 0.3 | 3.427 | 3.996 | 53.86 | 5.271 | 1.715 | 1.721 | 7.74 | 0.6776 | 0.03161 | 177 | 5.251 | 15.13 | manual |
| 2 | 20.9 | 0.3704 | 7.74 | 9.158 | 91.3 | 5.045 | 3.983 | 3.19 | 10.78 | 0.516 | 0.02251 | 177 | 5.576 | 17.93 | manual |
| 3 | 22.98 | 0.4692 | 10.78 | 8.197 | 100.2 | 5.005 | 4.389 | 3.517 | 11.34 | 0.4935 | 0.02152 | 177 | 5.337 | 18.34 | manual |
| 4 | 23.52 | 0.4822 | 11.34 | 8.18 | 102.4 | 4.996 | 4.501 | 3.602 | 11.49 | 0.4887 | 0.02129 | 177 | 5.311 | 18.43 | manual |
| 5 | 23.68 | 0.4854 | 11.49 | 8.185 | 103.1 | 4.993 | 4.534 | 3.626 | 11.54 | 0.4874 | 0.02123 | 177 | 5.305 | 18.46 | manual |
| 6 | 23.73 | 0.4864 | 11.54 | 8.188 | 103.3 | 4.992 | 4.544 | 3.634 | 11.55 | 0.487 | 0.02121 | 177 | 5.303 | 18.47 | manual |
| 7 | 23.74 | 0.4866 | 11.55 | 8.188 | 103.3 | 4.992 | 4.548 | 3.636 | 11.56 | 0.4868 | 0.0212 | 177 | 5.303 | 18.47 | manual |
| 8 | 23.75 | 0.4867 | 11.56 | 8.189 | 103.3 | 4.992 | 4.549 | 3.637 | 11.56 | 0.4868 | 0.0212 | 177 | 5.303 | 18.47 | manual |
| 9 | 23.75 | 0.4868 | 11.56 | 8.189 | 103.3 | 4.991 | 4.549 | 3.637 | 11.56 | 0.4868 | 0.0212 | 177 | 5.303 | 18.47 | manual |
| 10 | 23.75 | 0.4868 | 11.56 | 8.189 | 103.3 | 4.991 | 4.549 | 3.637 | 11.56 | 0.4868 | 0.0212 | 177 | 5.303 | 18.47 | manual |
| 11 | 23.75 | 0.4868 | 11.56 | 8.189 | 103.3 | 4.991 | 4.549 | 3.637 | 11.56 | 0.4868 | 0.0212 | 177 | 5.303 | 18.47 | manual |
| 12 | 23.75 | 0.4868 | 11.56 | 8.189 | 100.3 | 5.335 | 4.549 | 3.652 | 11.56 | 0.4868 | 0.02309 | 177 | 5.303 | 20.72 | lowfi |
| 13 | 23.18 | 0.4987 | 11.56 | 7.623 | 98.19 | 5.366 | 4.587 | 3.586 | 11.6 | 0.5002 | 0.02326 | 175.6 | 5.153 | 20.64 | lowfi |
| 14 | 23.32 | 0.4973 | 11.6 | 7.721 | 98.69 | 5.366 | 4.635 | 3.609 | 11.66 | 0.5 | 0.0232 | 175.6 | 5.158 | 20.67 | lowfi |
| 15 | 23.39 | 0.4984 | 11.66 | 7.73 | 98.98 | 5.363 | 4.652 | 3.62 | 11.68 | 0.4994 | 0.02317 | 175.6 | 5.156 | 20.68 | lowfi |
| 16 | 23.41 | 0.4989 | 11.68 | 7.732 | 99.07 | 5.364 | 4.656 | 3.623 | 11.69 | 0.4992 | 0.02316 | 175.6 | 5.155 | 20.69 | lowfi |
| 17 | 23.42 | 0.4991 | 11.69 | 7.73 | 99.09 | 5.363 | 4.658 | 3.624 | 11.69 | 0.4992 | 0.02316 | 175.6 | 5.155 | 20.69 | lowfi |
| 18 | 23.42 | 0.4991 | 11.69 | 7.731 | 99.1 | 5.363 | 4.658 | 3.624 | 11.69 | 0.4991 | 0.02316 | 175.6 | 5.155 | 20.69 | lowfi |

## 9. Sistemas e eletrónica (Fase 1E)

- **Hélice**: D = 0.560 m (22.0 in), rpm máx ≈ 4232, rpm cruzeiro ≈ 3367 (J = 0.7), Mach de ponta 0.36 — limited by geometric D_max (0.560 m). Passo a escolher com dados de hélice (UIUC Propeller Data Site / APC) para o J de cruzeiro.
- **Motor**: Kv alvo 173 rpm/V, P_eixo máx 1184 W, I máx 56.9 A @ 28.8 V → outrunner_63xx_170kv_class; **ESC** → esc_80a_12s_class
- **Bateria**: 8S3P de `liion_pouch_high_energy_class` (li_ion), 60.0 Ah, 29.6 V nom., 1776 Wh, massa 7.78 kg (228 Wh/kg pack), C pico 1.02 (OK), dimensionada por energy. Massa atribuída no sizing: 7.73 kg.

Servos (momentos de charneira a V_D):

| superfície | S_c m² | c_c m | H N·m | binário req. N·m | servo | n |
|---|---|---|---|---|---|---|
| aileron (each) | 0.05006 | 0.06686 | 0.46 | 0.69 | servo_mini_8kgcm_class | 2 |
| elevator | 0.07212 | 0.08109 | 0.8038 | 1.206 | servo_standard_20kgcm_class | 1 |
| rudder | 0.05934 | 0.122 | 0.9953 | 1.493 | servo_standard_20kgcm_class | 1 |

- **Autopiloto**: `cubepilot_cube_orange_plus` (IMU×3, baro×2, CAN×2, massa≈0.075 kg) — https://docs.cubepilot.org/user-guides/autopilot/the-cube-module-overview
  - rejeitados: holybro_pixhawk_6c: IMU 2<3, baro 1<2; generic_f7_fc_class: IMU 1<3, baro 1<2, CAN 0<1

Power budget:

| load | bus | P_W | duty | P_avg_W | P_peak_W |
|---|---|---|---|---|---|
| autopilot cubepilot_cube_orange_plus | avionics | 2.5 | 1 | 2.5 | 2.5 |
| GNSS + compass (x2) | avionics | 1.5 | 1 | 1.5 | 1.5 |
| C2 datalink radio | avionics | 6 | 1 | 6 | 10 |
| payload EO/IR gimbal | payload | 15 | 1 | 15 | 30 |
| airspeed + ADS-B out | avionics | 2 | 1 | 2 | 2 |
| servo aileron (each) x2 | servo | 2 | 1 | 2 | 25.2 |
| servo elevator x1 | servo | 1 | 1 | 1 | 25.2 |
| servo rudder x1 | servo | 1 | 1 | 1 | 25.2 |

Média 31.0 W, pico 121.6 W; regulador aviónica ≥ 24.0 W, servos ≥ 113.4 W.

Cablagem de potência (secção por corrente e queda de tensão):

| fio | AWG | mm² | ΔV V | ΔV % | governado por |
|---|---|---|---|---|---|
| W1 | 6 | 13.3 | 0.06827 | 0.2371 | ampacity |
| W2 | 6 | 13.3 | 0.06827 | 0.2371 | ampacity |
| W3 | 22 | 0.3255 | 0.1177 | 2.353 | voltage drop |
| W4 | 22 | 0.3255 | 0.1177 | 2.353 | voltage drop |
| W5 | 12 | 3.309 | 0.1628 | 1.938 | voltage drop |
| W6 | 12 | 3.309 | 0.1628 | 1.938 | voltage drop |

Exportado: `harness.wireviz.yml` (WireViz), `harness.dot` (Graphviz), `netlist.csv`, `harness.net` (netlist KiCad, formato "E" — importar no Pcbnew).

Massas de sistemas selecionados:

| item | kg |
|---|---|
| motor(s) | 0.9 |
| ESC(s) | 0.15 |
| servo aileron (each) | 0.05 |
| servo elevator | 0.06 |
| servo rudder | 0.06 |
| autopilot cubepilot_cube_orange_plus | 0.075 |
| battery | 7.776 |

Fecho massa/energia sistemas → sizing:

| iter | W0 | We | systems_kg | battery_Wh_kg | pack_Wh_kg | systems_power_W | budget_W | battery_mass_alloc | battery_mass_sel |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 22.87 | 10.19 | 1.295 | 200 | 228.4 | 30 | 31 | 8.674 | 7.776 |
| 2 | 23.42 | 11.69 | 1.295 | 228.4 | 228.4 | 31 | 31 | 7.731 | 7.776 |
| 3 | 23.42 | 11.69 | 1.295 | 228.4 | 228.4 | 31 | 31 | 7.731 | 7.776 |

### Checklist de normas (categoria: `easa_specific`, MTOW 23.4 kg, UAS, features: li_battery)

> Orientação de primeira análise. A base de certificação é acordada com a autoridade; confirmar sempre a edição em vigor de cada documento.

- [ ] **EU-2019/947-945** — Commission Implementing Reg. (EU) 2019/947 & Delegated Reg. (EU) 2019/945 — UAS operations & products (European Commission / EASA). <https://www.easa.europa.eu/en/domains/civil-drones>
  - [ ] operational category (open/specific/certified)
  - [ ] operator registration
  - [ ] remote ID
  - [ ] class marking
- [ ] **EASA-SORA-2.5** — SORA 2.5 — AMC1 to Art. 11 of Reg. (EU) 2019/947 (ED Decision 2025/018/R, Sept 2025) (EASA (based on JARUS SORA v2.5, 2024)). <https://www.easa.europa.eu/en/document-library/agency-decisions/ed-decision-2025018r>
  - [ ] ConOps
  - [ ] intrinsic ground risk class
  - [ ] air risk class
  - [ ] SAIL
  - [ ] operational safety objectives (OSO)
  - [ ] containment
- [ ] **EASA-SC-Light-UAS** — Special Condition Light-UAS Medium Risk (Issue 01, 2020) + FTB MoC SC Light-UAS (SAIL III and below) (EASA). <https://www.easa.europa.eu/en/special-condition-sc-light-uas-medium-risk>
  - [ ] design verification
  - [ ] flight test
  - [ ] system safety
  - [ ] C2 link
  - [ ] software/AEH assurance proportional to SAIL
- [ ] **ASTM-F3298-24** — ASTM F3298-24 Design and Construction of Lightweight UAS (fixed-wing) (ASTM F38.01). <https://www.astm.org/f3298-24.html>
  - [ ] structure
  - [ ] propulsion
  - [ ] systems
  - [ ] C2
  - [ ] launch & recovery
  - [ ] verification
- [ ] **ASTM-F2910-22** — ASTM F2910-22 Design and Construction of a Small UAS (sUAS) (ASTM F38.01). <https://www.astm.org/f2910-22.html>
  - [ ] sUAS design & construction baseline
- [ ] **ASTM-F3002-22** — ASTM F3002-22 Design of the Command and Control System for sUAS (generally <= 25 kg) (ASTM F38.01). <https://www.astm.org/f3002-22.html>
  - [ ] C2 link
  - [ ] spectrum
  - [ ] lost-link and fly-away functionality
- [ ] **ASTM-F3005-22** — ASTM F3005-22 Batteries for Use in sUAS (ASTM F38.01). <https://www.astm.org/f3005-22.html>
  - [ ] battery design
  - [ ] BMS
  - [ ] marking
  - [ ] testing
- [ ] **ASTM-F3201** — ASTM F3201 Ensuring Dependability of Software Used in UAS (ASTM F38.01). <https://www.astm.org/f3201-26.html>
  - [ ] software development assurance proportional to risk
- [ ] **UN-38.3** — UN Manual of Tests and Criteria, Part III, Sub-section 38.3 — Lithium batteries (transport) (UNECE). <https://unece.org/transport/dangerous-goods>
  - [ ] altitude
  - [ ] thermal
  - [ ] vibration
  - [ ] shock
  - [ ] external short circuit
  - [ ] impact
  - [ ] overcharge tests; transport certification
- [ ] **SAE-AS50881** — SAE AS50881 Wiring, Aerospace Vehicle (SAE). <https://www.sae.org/standards/content/as50881/>
  - [ ] wire selection & derating
  - [ ] voltage drop
  - [ ] bundle routing
  - [ ] separation
  - [ ] protection
  - [ ] identification
- [ ] **IPC-WHMA-A-620** — IPC/WHMA-A-620 Requirements and Acceptance for Cable and Wire Harness Assemblies (IPC / WHMA). <https://www.ipc.org>
  - [ ] crimping
  - [ ] soldering
  - [ ] splices
  - [ ] connectors
  - [ ] workmanship classes 1–3 (use class 3 for flight-critical)
- [ ] **RTCA-DO-160G** — RTCA DO-160G Environmental Conditions and Test Procedures for Airborne Equipment (EUROCAE ED-14G) (RTCA / EUROCAE). <https://www.rtca.org>
  - [ ] temperature/altitude
  - [ ] vibration
  - [ ] EMC (Sect. 20/21)
  - [ ] lightning
  - [ ] power input (Sect. 16)
- [ ] **RTCA-DO-178C** — RTCA DO-178C / ED-12C Software Considerations in Airborne Systems (awareness; DAL per safety assessment) (RTCA / EUROCAE). <https://www.rtca.org>
  - [ ] software development assurance; SC Light-UAS / SORA high-SAIL may require equivalent evidence
- [ ] **RTCA-DO-254** — RTCA DO-254 / ED-80 Design Assurance for Airborne Electronic Hardware (awareness) (RTCA / EUROCAE). <https://www.rtca.org>
  - [ ] complex electronic hardware (FPGA/ASIC) assurance


## 10. Aerodinâmica de baixa fidelidade (Fase 2: XFOIL + AVL)

![lowfi](lowfi_polar.png)

- Perfil: XFOIL 6.99 (Ncrit 9, xtr ≤ 0.30); Re de cruzeiro 4.48e+05, cm0 = -0.0975
- clmax do perfil (Re de perda 3.04e+05) = 1.435 → CLmax limpo 1.292 (Raymer Eq. 12.15)
- Carga em envergadura: AVL 3.40 (VLM), 2 ângulos; e_inv = 0.949, fator de fuselagem (Kroo) 0.9947
- CDp da asa (integração em faixas, CL = 0.5) = 0.01021 vs termo do manual 0.00838
- **Polar usada no ciclo: CD0 = 0.02316, K = 0.02522 (e = 0.902)**

- perfil NACA 4412: Re cruzeiro 4.48e+05 (xtr = 0.30), clmax a Re_stall 3.04e+05 (transição livre, Ncrit 9)

### Comparação AVL / baixa fidelidade vs métodos de manual

| grandeza | manual | AVL / baixa fid. | método manual | nota |
|---|---|---|---|---|
| CLα asa [/rad] | 5.119 | 5.719 | DATCOM / Raymer Eq. 12.6 | AVL: avião completo (asa + cauda), sem fuselagem |
| CDi a CL = 0.628 | 0.01362 | 0.009168 | Oswald Raymer e = 0.658 | AVL e (Trefftz) = 0.977; Oswald inclui arrasto viscoso dependente de CL |
| x̄_NP [MAC] | 0.4624 | 0.4947 | Raymer Eq. 16.9 + Torenbeek (fuselagem) | sem fuselagem: 0.486 (AVL não modela a fuselagem) |
| CLδe [/rad] | 0.3535 | 0.4155 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) |  |
| Cmδe [/rad] | -1.122 | -1.211 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) | AVL: Cmδe no CG traseiro; Cnδr com convenção de sinal AVL |
| |Clδa| [/rad] | 0.3741 | 0.286 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) |  |
| Cnδr [/rad] | -0.06125 | 0.05982 | Nelson Ch. 2/5 (τ: Raymer Fig. 16.7 / DATCOM) | AVL: Cmδe no CG traseiro; Cnδr com convenção de sinal AVL |
| CD0 (polar ajustada) | 0.02126 | 0.02316 | Raymer Eq. 12.24 | perfil XFOIL 6.99 (Ncrit 9, xtr ≤ 0.30); ajuste rms 2.8e-04 |
| e efetivo | 0.6581 | 0.9016 | Raymer Eq. 12.49 | baixa fid.: AVL e_inv × Kroo (fuselagem) + cd(cl) do perfil |
| cl_max do perfil | 1.45 | 1.435 | pressuposto do utilizador | XFOIL/NeuralFoil a Re = 3.04e+05 |

## 11. Estruturas: V-n, cargas na asa e caixão (Fase 2)

![V-n](vn_diagram.png)

| grandeza | valor |
|---|---|
| regulation | stanag_4671 |
| category | utility |
| VS1_EAS_m_s | 14.9 |
| VA_EAS_m_s | 21.37 |
| VC_EAS_m_s | 21.37 |
| VD_EAS_m_s | 26.71 |
| n_manoeuvre_pos | 4.4 |
| n_manoeuvre_neg | -1.76 |
| n_gust_VC | 5.363 / -3.363 |
| n_gust_VD | 3.727 / -1.727 |
| mu_g | 17.45 |
| Kg | 0.675 |
| n_limit_pos | 5.363 |
| n_limit_neg | -3.363 |
| governing | rajada |
| n_ultimate | 8.045 |

Cláusulas aplicadas: USAR.333 (envelope); USAR.335(a)(1) VC from operating requirements; USAR.335(b)(1) VD ≥ 1.25 VC; USAR.335(c) VA ≥ VS√n; USAR.337; USAR.341 / USAR.333(c); USAR.303 FS = 1.5

- ⚠️ n_lim = 5.36 está acima da linha de perda mesmo a VD (n = 3.21 com CLmax quase-estático): valor CONSERVATIVO mantido (a perda dinâmica numa rajada pode excedê-lo); VC baixo face a VS1 — rever VC/CLmax antes de dimensionar

Condição crítica de dimensionamento: n = 5.36 (rajada), q a VD = 26.7 m/s EAS.

![loads](wing_loads.png)

Raiz (limite): V = 493.2 N, M = 461.1 N·m, T = 8.6 N·m.

![box](wing_box.png)

| parcela | massa [kg] |
|---|---|
| caps | 0.182 |
| box_skins | 1.47 |
| core | 0.1807 |
| webs | 0.09569 |
| web_uprights | 0 |
| LE_TE_skins | 0.931 |
| ribs | 0.04005 |
| ideal | 2.899 |
| nonoptimum | 0.7248 |
| total | 3.624 |

Cross-check da massa da asa:

| método | massa da asa [kg] |
|---|---|
| Raymer Eq. 15.46 (estatístico) | 4.658 |
| caixão Megson/Bruhn, carga Schrenk (CFRP (UD caps / ±45 fabric — ASSUMPTION)) | 3.624 |
| caixão Megson/Bruhn, carga AVL | 3.619 |

- Revestimentos em sanduíche: núcleo PVC/PMI foam (ASSUMPTION) ρ = 75 kg/m³, E_c = 70 MPa, G_c = 30 MPa (PRESSUPOSTO); núcleo na raiz 2.0 mm, máx. 2.0 mm; interação R_c + R_s² ≤ 1 (Bruhn C5)
- Enrugamento das faces σ_wr = 0.5 (E_f E_c G_c)^(1/3) = 251 MPa (Hoff & Mautner) → OK
- Almas: núcleo sanduíche onde τ > τ_cr (máx. 2.0 mm)
- allowables are ASSUMPTIONS (knock-down for environment/damage)
- 26 nervuras (passo 0.19 m)
- fator não-ótimo 1.25 (PRESSUPOSTO)
- superfícies de comando, flaps e carenagens NÃO incluídos (secundários)
- Eixo elástico = centro de corte da secção real (Megson, multicélula, com bordo de ataque D): x_sc/c raiz 0.339 (meio do caixão 0.425); EI/GJ da secção idealizada no contorno do perfil

### Viga L1: fuselagem, empenagens e torção elástica

Fuselagem 1.7 kg, Raymer Eq. 15.49 1.2 kg (razão 1.47). Estabilizador 0.2 kg, deriva 0.2 kg. CG estrutural 0.7691233315844792 m (não move as estações Roskam do peso e centragem).
Deflexão da cauda no caso limite 0.1 mm; torção da deriva 0.013°.
Correção elástica de cruzeiro: aplicada = não; K_flex/K_rígido = 0.9994; torção de ponta -0.036°; CLα flexível 5.196 /rad. O CLα de manual do resultado mantém-se.
- Fuselagem: casca circular não reforçada, γ de NASA SP-8007 (1968) na encurvadura clássica 0,605 E t/R (Timoshenko & Gere, ν = 0,3). Longarinas só com área mínima (o momento já está no revestimento).
- Piso 0.45 L × 0.75 D, duas anteparas π R² à espessura mínima (Torenbeek 1982 App. D lista estes itens; a espessura é a mínima do material — PRESSUPOSTO). Fator não-ótimo 1.25 só em revestimento + longarinas + cavernas.
- Envelope de manobra: sustentação atingível do estabilizador a VA (Raymer 12.15), equilíbrio + 23.423(b), inércia do motor e aterragem (23.473). 23.427 (rajada) e 23.441 (leme) não estão modelados. Torção assimétrica do estabilizador omitida.
- Estação da asa neste fecho: x = 0.69 m (centro aerodinâmico: ápice colocado pela estabilidade + quarto da corda média).
- γ de SP-8007 é uma correlação de cilindros de alumínio. Em CFRP entra como PRESSUPOSTO conservativo, não como ensaio do laminado.
- Empenagens: caixão de duas longarinas (Megson), carga em envergadura uniforme — PRESSUPOSTO, M_raiz = L b/8 por semienvergadura, mais pesado em flexão do que uma elipse. c_lmax de secção 1 (estabilizador) e 0.8 (deriva), não o da asa; CLmax pela Eq. 12.15 de Raymer.
- k_EI e k_GJ multiplicam EI e GJ da asa (razão viga/BoxFEM). A fuselagem não os usa.
- Massa da fuselagem L1 / Raymer Eq. 15.49 = 1.47. A regressão de Raymer inclui portas, janelas e suportes que esta casca não tem.

## 12. Estabilidade e controlo (Fase 2: Raymer Cap. 16, Etkin & Reid, Nelson)

![cg](cg_envelope.png)

- asa posicionada para SM = 10% no CG mais recuado (ápice a 33.3% L); ápice da asa a x = 0.599 m
- Ponto neutro x̄_NP = 0.462 MAC (manual), 0.495 (AVL); dε/dα = 0.233
- **Margem estática: 10.0 % (CG dianteiro) … 10.0 % (CG traseiro)**
- AVL, cruzeiro compensado no CG traseiro: α = 2.73°, δe = -2.66°, Cnβ = 0.0671, Clβ = -0.0783, Cmq = -11.89
- Coef. de volume: V_h = 0.500, V_v = 0.0300 (Raymer Table 6.4: - / -)

| caso | massa [kg] | x_cg [m] | x̄_cg [MAC] | SM |
|---|---|---|---|---|
| vazio + bateria | 19.42 | 0.7295 | 0.3624 | 0.1 |
| MTOW | 23.42 | 0.7295 | 0.3624 | 0.1 |

Compensação (trim) no CG dianteiro:

| condição | CL | δe [°] | ok (|δe| ≤ máx.) |
|---|---|---|---|
| CLmax limpo (CG dianteiro) | 1.292 | -10.96 | True |
| cruzeiro (CG dianteiro) | 0.6278 | -7.564 | True |

- Clδa comparado em módulo (convenções de sinal do aileron diferem entre AVL e Nelson).
- Estações de estrutura: PRESSUPOSTOS (Roskam Part V Table 8.1, valores típicos). Tripulação, carga e bateria, se a missão não as der, ficam no CG da massa fixa (Raymer 2018 Sec. 15.1: a estação que não desloca o balanço). Um UAV sem massa de tripulação não leva tripulação. O combustível de asa fica a 30 % da CMA. Substituir em assumptions.stability.stations.

## 12a. Peso e centragem operacional e trem de aterragem

Peso e centragem (Raymer 2018 Sec. 15.1; Roskam Parte II Cap. 10). Os limites, quando não são dados no ficheiro, são os conceptuais: margem estática alvo atrás e, à frente, o mais à ré entre o trim no CLmax limpo e o flare com flaps.

![carregamento](wb_loading.png)

Todos os 3 carregamentos dentro dos limites conceptuais; extremos 0.729 m (vazio, 19 kg) e 0.729 m (payload, 23 kg).

| carregamento | massa [kg] | x_cg [m] | x̄ [% CMA] |
|---|---|---|---|
| vazio | 19.42 | 0.7295 | 36.24 |
| payload | 23.42 | 0.7295 | 36.24 |
| payload | 23.42 | 0.7295 | 36.24 |

Limites a W0: dianteiro 0.7206542562936984 m, traseiro 0.7294658432608819 m.

- Limite dianteiro conceptual: dimensiona «flare com flaps» a 0.721 m. Casos: limpo a 0.663 m (CL 1.29, Cm0 -0.0853), flare com flaps a 0.721 m (CL 1.70, Cm0 -0.2767). Nelson 1998 Cap. 2, |δe| = 25°. Cm0 da asa = -0.0853 (Raymer Eq. 16.13, cm0 do perfil) Cm0,f = -0.0213 entra no flare (Multhopp, Nelson 1998 Cap. 2; k2−k1 da tabela de Lamb em Tuckerman, NACA Report 139; α0 = -3.97°. Largura constante igual a D e i_f = 0, PRESSUPOSTO — fuselagem de revolução, Torenbeek App. F, sem segmentar nariz e cauda) ΔCm do flap = -0.1700 entra no flare (Glauert 1926, b_C·δ·S_f/S; δ = 30° (PRESSUPOSTO, omissão de flightsim/controls.py — substituir em assumptions.aero.flap.landing_deg); c_f/c = 0.25 (PRESSUPOSTO, omissão de flightsim/controls.py — substituir em assumptions.aero.flap.cf_c); S_f/S = 0.500; corda da parte com flap igual à CMA, PRESSUPOSTO). Efeito de solo no flare: CLα da cauda × 1.010 (φ = 0.970 = 1 − exp[−2.48 (2h/b)^0.768], Torenbeek 1982, citado por Phillips e Hunsaker, Journal of Aircraft, Vol. 50, No. 4, 2013, Eq. (4); h/b = 0.782, h = 0.710 m, trem + 0.5 D, omissão 0.60 m (PRESSUPOSTO, weights_detailed.DEFAULT_MAIN_GEAR_LENGTH_M); PRESSUPOSTO: o centro aerodinâmico da cauda está à altura do eixo da fuselagem). 1/CLα = 1/a0 + φ/(π AR), a0 = 0.95·2π, e = 1 (PRESSUPOSTO). O quociente multiplica o CLα livre e não substitui o declive de Helmbold. O CLmax não aumenta e o dε/dα do ponto neutro não é reduzido: essa redução é a penalização de rotação, não um alívio do flare. Na tesoura, φ repete-se em cada S_h/S porque a envergadura muda com a área. O flare fica em efeito de solo só neste declive. O fator de Hoerner e Borst não é usado como CLα.
- Limite traseiro conceptual: ponto neutro menos a margem estática alvo (Raymer Cap. 16).
- Estações de CG: as da estabilidade. Estrutura: Roskam Parte V, Tabela 8.1 (PRESSUPOSTO). Tripulação, carga e bateria, se a missão não as der, ficam no CG da massa fixa (Raymer 2018 Sec. 15.1); combustível de asa a 30 % da CMA. Substituir em assumptions.stability.stations, weight_balance.loading ou extra_items. O combustível arde na estação do tanque; não há combustível inutilizável separado.
- A tripulação, quando existe, vai em todos os carregamentos.

**Trem (none).** sem trem

sem trem; 14 CFR 23.473 não aplicado

- Sem trem de aterragem (landing_gear: none) — lançamento e recuperação ficam por analisar.

## 13. Desempenho por segmentos (Fase 2: Raymer Cap. 17, Anderson)

Orçamento utilizável: E_nom 1766 Wh × DoD 0.85 / (1 + reserva 0.2).

Missão requerida (segmentos):

| segmento | t [min] | dist [km] | consumo [Wh] | h [m] | V [m/s] | nota |
|---|---|---|---|---|---|---|
| descolagem | 1 | 0 | 17.5 | 0→0 | 0 | 1 min potência de descolagem (PRESSUPOSTO) |
| subida (V_y) | 3.346 | 3.588 | 81.6 | 0→600 | 18.12 | potência de subida, integrado (V médio) |
| espera (loiter) | 150 | 198 | 1152 | 600→600 | 22 |  |
| descida (L/D máx, ralenti) + aterragem | 11.79 | 12.41 | 0 | 600→0 | 17.55 | planado, energia ≈ 0 |

Missão até esgotar o orçamento: **alcance 214.0 km, endurance 2.77 h**.

| segmento | t [min] | dist [km] | consumo [Wh] | h [m] | V [m/s] | nota |
|---|---|---|---|---|---|---|
| descolagem | 1 | 0 | 17.5 | 0→0 | 0 | 1 min potência de descolagem (PRESSUPOSTO) |
| subida (V_y) | 3.346 | 3.588 | 81.6 | 0→600 | 18.12 | potência de subida, integrado (V médio) |
| espera (loiter) | 150 | 198 | 1152 | 600→600 | 22 | estendido até esgotar o orçamento |
| descida (L/D máx, ralenti) + aterragem | 11.79 | 12.41 | 0 | 600→0 | 17.55 | planado, energia ≈ 0 |

Requisitos vs desempenho por segmentos:

| requisito | grandeza | obtido | requerido | unidade | ok |
|---|---|---|---|---|---|
| endurance | tempo em espera (segmentos) | 2.5 | 2.5 | h | ✅ |
| service_ceiling | teto de serviço (Anderson) > 9000 m (não atingido) | 9000 | 3000 | m | ✅ |
| climb_rate | ROC máx. ao nível do mar | 3 | 3 | m/s | ✅ |

![payload-range](payload_range.png)

| ponto | payload_kg | massa_kg | range_km | endurance_h |
|---|---|---|---|---|
| O | 4 | 23.42 | 0 | 0 |
| A | 4 | 23.42 | 214 | 2.769 |
| B (projeto) | 4 | 23.42 | 214 | 2.769 |
| D (sem payload) | 0 | 19.42 | 235.3 | 3.059 |

Nota: elétrico: massa de bateria fixa; menos payload → menor massa → mais alcance.

![climb](climb_ceiling.png)

- ROC máx. ao nível do mar 3.00 m/s; teto de serviço > 9000 m; teto absoluto > 9000 m
- Descolagem (Raymer 17.8): corrida 64 m, total sobre 15 m 208 m (V_TO 16.0 m/s)
- Aterragem (Raymer 17.9): corrida 79 m, total sobre 15 m 373 m (μ_travagem 0.4; aproximação γ = 3° — `performance.approach_angle_deg`, por omissão o máximo de 5.2 % / 3° de CS/14 CFR 23.75(a)(1))

- Os resultados de segmentos usam a mesma polar e reservas do dimensionamento; diferenças face aos requisitos vêm da subida/descida integradas vs. frações históricas (Raymer Table 3.2).

## 14. Caixão da asa dimensionado à estabilidade (Fase 3: Bruhn C5/C7/C11, Farrar, Kuhn)

| caixão | massa [kg] | / Raymer 15.46 |
|---|---|---|
| resistência (Fase 2, limite inferior) | 3.398 | 0.7295 |
| encurvadura (Fase 3, CFRP (UD caps / ±45 fabric — ASSUMPTION)) | 3.624 | 0.778 |
| Raymer Eq. 15.46 (asa completa, estatístico) | 4.658 | 1 |

Parcelas (caixão de encurvadura):

| parcela | massa [kg] |
|---|---|
| caps | 0.182 |
| box_skins | 1.47 |
| core | 0.1807 |
| webs | 0.09569 |
| web_uprights | 0 |
| LE_TE_skins | 0.931 |
| ribs | 0.04005 |
| ideal | 2.899 |
| nonoptimum | 0.7248 |
| total | 3.624 |

- Almas Kuhn: fator de tração diagonal k máx. 0.000 (k = 0: alma resistente ao corte, sem tração diagonal)
- Revestimentos em sanduíche: núcleo PVC/PMI foam (ASSUMPTION) ρ = 75 kg/m³, E_c = 70 MPa, G_c = 30 MPa (PRESSUPOSTO); núcleo na raiz 2.0 mm, máx. 2.0 mm; interação R_c + R_s² ≤ 1 (Bruhn C5)
- Enrugamento das faces σ_wr = 0.5 (E_f E_c G_c)^(1/3) = 251 MPa (Hoff & Mautner) → OK
- Almas: núcleo sanduíche onde τ > τ_cr (máx. 2.0 mm)
- allowables are ASSUMPTIONS (knock-down for environment/damage)
- 26 nervuras (passo 0.19 m)
- fator não-ótimo 1.25 (PRESSUPOSTO)
- superfícies de comando, flaps e carenagens NÃO incluídos (secundários)
- Eixo elástico = centro de corte da secção real (Megson, multicélula, com bordo de ataque D): x_sc/c raiz 0.339 (meio do caixão 0.425); EI/GJ da secção idealizada no contorno do perfil

## 15. Aeroelasticidade clássica (Fase 3)

V_D = 26.7 m/s EAS.

| fenómeno | V [m/s EAS] | requerido 1.2 V_D | margem | ok | método |
|---|---|---|---|---|---|
| divergência torsional | 277.5 | 32.06 | +766 % | ✅ | W&C 8.3 / Bisplinghoff 8-2 (faixas + FE) |
| inversão do aileron | n/a | 32.06 | sem ocorrência | ✅ | W&C 8.4, Glauert (flap 2D) |
| flutter binário (flexão–torção) | 126 | 32.06 | +293 % | ✅ | W&C 11 (modos assumidos, quase-estacionário) |

- Frequências desacopladas: flexão 10.4 Hz, torção 78.9 Hz; flutter a 62.8 Hz
- AEER-45 (fator de flexibilidade torsional da asa): F = 1.422e-03 vs F_max = 200/V_D² = 5.601e-02 → OK

![flutter](flutter_vg.png)

### Acoplamento aero-estrutural estático (OpenAeroStruct, VLM + caixão)

| ponto | modelo | α [°] | CL | CDi | CLα [/rad] | flecha ponta [m] | torção ponta [°] |
|---|---|---|---|---|---|---|---|
| cruise | rígido | 6.725 | 0.6278 | 0.008809 | 5.326 | 1.594e-06 | 6.359e-06 |
| cruise | flexível | 6.688 | 0.6278 | 0.008816 | 5.358 | 0.01598 | 0.0637 |
| manobra (n_lim, V_D EAS, nível do mar) | rígido | 23.65 | 2.155 | 0.1031 | 4.943 | 8.028e-06 | 3.184e-05 |
| manobra (n_lim, V_D EAS, nível do mar) | flexível | 23.35 | 2.155 | 0.1035 | 5.048 | 0.08066 | 0.3198 |

- Efeito da forma deformada no arrasto induzido de cruzeiro: K_flex/K = 1.0008
- Missão por segmentos: rígido 214.0 km / 2.769 h → flexível 213.8 km / 2.766 h (comparação com o resultado desacoplado da Fase 2)
- ponto de manobra: CL = 2.16 > CLmax limpo 1.29 (n_lim de rajada acima da linha de perda) — caso de carga válido para a deformação (VLM linear), α não físico
- OpenAeroStruct VLM (sem viscoso/onda: só arrasto induzido) + FEM de caixão 'wingbox' acoplados por NLBGS; rígido = E, G × 10⁴
- secção do caixão: NACA-4 entre longarinas; espessuras de alma/revestimento do caixão acdt (5 pontos de controlo); revestimento único equivalente que reproduz EI(y) do caixão acdt e G ajustado para GJ (PRESSUPOSTO)
- sem alívio de peso estrutural nem de combustível na asa (conservativo para a deformação)
- índice de falha OAS (von Mises/KS, σ_adm = σ_cap/1.5) na manobra: -0.295 (< 0 = OK) — critério de resistência do OAS sobre o revestimento equivalente — INDICATIVO (o dimensionamento é o do caixão acdt)
- massa da asa 4.66 kg distribuída ∝ corda; CG da secção a 0.50 c; eixo elástico a 0.340 c (centro de corte da secção, média), e = 0.090 c atrás do c.a.; a_w = 6.283/rad (2D, teoria das faixas — sem correção 3D/compressibilidade)
- encastramento na parede da fuselagem y0 = 0.110 m; EI/GJ do caixão buckling
- requisito: livre de flutter/divergência/inversão até 1.2 V_D = 32.1 m/s EAS (14 CFR 23.629(c) legado; CS/14 CFR 23.2245 'suficientemente além'; STANAG 4671 USAR.629 — verificar)
- flutter: modelo binário de modos assumidos (W&C Cap. 11), aerodinâmica quase-estacionária — ESTIMATIVA; a análise racional exige modos FEM + DLM (Fase 4)
- UAV (STANAG 4671): AEER-45 é um critério FAA para aviação geral — informativo

## 16. Diagrama de tesoura, modos dinâmicos e qualidades de voo (Fase 3)

![scissor](scissor.png)

- S_h/S atual 0.158; requerido 0.158 (estabilidade 0.158, controlo 0.0906; dimensionante: estabilidade) → ✅ (Torenbeek Cap. 9)
- linha de controlo: o x̄ mais à ré entre o CLmax limpo 1.29 (Cm0 asa -0.0853) e o flare com flaps (CLmax aterragem 1.70, Cm0 -0.2767), δe = −25°, τ_e = 0.661. Cm0 da asa = -0.0853 (Raymer Eq. 16.13, cm0 do perfil) Cm0,f = -0.0213 entra no flare (Multhopp, Nelson 1998 Cap. 2; k2−k1 da tabela de Lamb em Tuckerman, NACA Report 139; α0 = -3.97°. Largura constante igual a D e i_f = 0, PRESSUPOSTO — fuselagem de revolução, Torenbeek App. F, sem segmentar nariz e cauda) ΔCm do flap = -0.1700 entra no flare (Glauert 1926, b_C·δ·S_f/S; δ = 30° (PRESSUPOSTO, omissão de flightsim/controls.py — substituir em assumptions.aero.flap.landing_deg); c_f/c = 0.25 (PRESSUPOSTO, omissão de flightsim/controls.py — substituir em assumptions.aero.flap.cf_c); S_f/S = 0.500; corda da parte com flap igual à CMA, PRESSUPOSTO). Efeito de solo no flare: CLα da cauda × 1.010 (φ = 0.970 = 1 − exp[−2.48 (2h/b)^0.768], Torenbeek 1982, citado por Phillips e Hunsaker, Journal of Aircraft, Vol. 50, No. 4, 2013, Eq. (4); h/b = 0.782, h = 0.710 m, trem + 0.5 D, omissão 0.60 m (PRESSUPOSTO, weights_detailed.DEFAULT_MAIN_GEAR_LENGTH_M); PRESSUPOSTO: o centro aerodinâmico da cauda está à altura do eixo da fuselagem). 1/CLα = 1/a0 + φ/(π AR), a0 = 0.95·2π, e = 1 (PRESSUPOSTO). O quociente multiplica o CLα livre e não substitui o declive de Helmbold. O CLmax não aumenta e o dε/dα do ponto neutro não é reduzido: essa redução é a penalização de rotação, não um alívio do flare. Na tesoura, φ repete-se em cada S_h/S porque a envergadura muda com a área. O flare fica em efeito de solo só neste declive. O fator de Hoerner e Borst não é usado como CLα.
- massa da cauda não realimentada (posição da asa e braço fixos)
- gama de CG: a mesma do trim (extremos dos casos de carregamento)

![modes](root_locus.png)

| modo | ωn [rad/s] | ζ | período [s] | τ / T [s] |
|---|---|---|---|---|
| período curto | 8.192 | 0.7127 | 1.093 | - |
| fugóide | 0.4975 | 0.06279 | 12.65 | - |
| rolamento holandês | 3.655 | 0.1879 | 1.75 | - |
| rolamento (constante de tempo) | - | - | - | 0.06716 |
| espiral instável | - | - | - | 11.59 |

- n/α = 8.81 g/rad, CAP = 7.62 1/(g s²)
- Inércias (Roskam V, soma por componentes): Ixx 6.26, Iyy 1.51, Izz 7.73 kg·m²
- derivadas de taxa e laterais: AVL (sem fuselagem) + Cnβ da fuselagem (Raymer 16.47) -0.0134
- Cmα = −CLα·SM no CG de MTOW (ponto neutro de manual com fuselagem)
- inércias por soma de componentes (Roskam Parte V) — PRESSUPOSTOS de estações

Qualidades de voo — MIL-F-8785C, Classe I, categoria B (nível exigido 1):

| modo | valor | nível | limite N1 | ref |
|---|---|---|---|---|
| período curto ζ | 0.7127 | 1 | 0.30–2.00 | MIL-F-8785C Table IV |
| CAP = ω²/(n/α) [1/(g s²)] | 7.62 | 2 | 0.085–3.6 | MIL-F-8785C Figs. 1–3 |
| fugóide ζ | 0.06279 | 1 | ≥ 0.04 | MIL-F-8785C 3.2.1.2 |
| rolamento holandês ζ / ζω / ω | 0.188 / 0.687 / 3.65 | 1 | 0.08 / 0.15 / 0.4 | MIL-F-8785C Table VI |
| rolamento τ_R [s] | 0.06716 | 1 | ≤ 1.4 | MIL-F-8785C Table VII |
| espiral T2 [s] (∞ = estável) | 11.59 | 2 | ≥ 20 | MIL-F-8785C Table VIII |


## Pressupostos usados

```yaml
weights:
  method: components
  initial_class: uav_small
  fixed_fraction: null
  A: null
  C: null
  tech_factor: 1.0
  Kvs: 1.0
  fixed_mass_kg: 0.0
  components:
    material: composite
    structural_category: utility
    landing_gear: none
    min_areal_density_kg_m2: 0.9
    propeller_mass_kg: 0.08
    items:
    - name: paraquedas de recuperação + ejetor
      mass_kg: 1.0
    - name: suporte/amortecimento do gimbal
      mass_kg: 0.3
    - name: datalink C2 + antenas
      mass_kg: 0.25
      group: equipment
    - name: GNSS + bússola (x2)
      mass_kg: 0.1
      group: equipment
    - name: pitot/ADS-B
      mass_kg: 0.1
      group: equipment
    - name: cablagem de sinal + conectores
      mass_kg: 0.3
      group: equipment
    - name: ferragens/fixações/pintura
      mass_kg: 0.4
    growth_allowance: 0.1
aero:
  AR: 14
  taper: 0.6
  sweep_c4_deg: 0.0
  tc_root: 0.13
  tc_tip: 0.11
  xc_max_t: 0.3
  airfoil: NACA 4412
  clmax_airfoil: 1.45
  flap:
    kind: plain
    flapped_area_ratio: 0.5
  oswald: null
  cfe: 0.0055
  swet_sref: 3.5
  laminar:
    wing: 0.3
    htail: 0.3
    vtail: 0.3
    fuselage: 0.1
  roughness: smooth_molded_composite
  Q: {}
  lp_fraction: 0.05
  extra_drag_areas_m2:
    gimbal_eo_ir: 0.006
    antennas_pitot: 0.002
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
  battery_Wh_kg: 228.39506172839506
  eta_total: 0.62
  dod: 0.85
  energy_reserve: 0.2
  systems_power_W: 31.0
  n_engines: 1
  propeller: null
geometry:
  fuselage_length_m: 1.8
  fuselage_diameter_m: 0.22
  fuselage_fineness: 7.0
  fuselage_class: null
  tail_class: null
  c_ht: 0.5
  c_vt: 0.03
  tail_arm_fraction: 0.55
  ar_h: 4.0
  ar_v: 1.5
  dihedral_deg: null
  configuration: conventional
  tail_dihedral_deg: null
  boom_span_fraction: 0.35
  pod_length_fraction: 0.55
  boom_width_m: null
  taper_v: 0.5
constraints:
  cruise_weight_fraction: 1.0
  landing_weight_fraction: 1.0
  approach_distance_ft: 600.0
  margin: 0.0
  ws_initial_psf: 6
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
  flex: false
  mass_in_loop: false
  wingbox:
    hold_section: false
stability:
  target_static_margin: 0.1
  wing_apex_x_fraction: null
  stations: {}
  inertia_method: components
  roskam_reference: null
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
  hq_aeroel_keys: null
cost: {}
calibration:
  file: null
  apply: []
  factors: {}
weight_balance:
  crew_optional: false
  extra_items: []
  x_forward_m: null
  x_aft_m: null
  forward_limit: null
  aft_limit: null
  lemac_arm_in: null
  mac_in: null
landing_gear:
  h_cg_m: null
  tipback_deg: 15.0
  overturn_max_deg: 63.0
  nose_fraction_min: 0.08
  nose_fraction_max: 0.15
  wing_lift_fraction: 0.6666666666666666
  absorber: oleo
  eta: null
  stroke_m: null
  tire_stroke_m: 0.0
  max_stroke_m: null
  rotation_min_deg: 10.0
  x_nose_m: null
  x_main_m: null
  x_tail_m: null
  track_m: null
  x_nose_min_m: 0.0
  x_main_max_m: null
launch_recovery: null
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
