# Fase 4 — verificação de alta fidelidade: Cessna 172S (verificação) (`cessna172_check`)

L3 verifica o desenho L1/L2 (não redimensiona). Cada número abaixo vem de um ficheiro nesta pasta; casos pesados demais para esta máquina estão escritos com estimativa e comando (secção 9).

## 1. Geometria (OpenVSP → STEP/STL)

não corrido: —

## 2. Secção: SU2 RANS-SA 2-D vs XFOIL (L1)

| grandeza | RANS | XFOIL | razão/dif. |
|---|---|---|---|
| cl_max (Re de perda) | 1.82 | 1.71 | 1.06 |
| cd @ cl 0.5 (Re cruzeiro) | 0.0119 | 0.00834 | 1.43 |
| cm0 | -0.057 | -0.0501 | -0.00694 |

Malha 34248 células; RANS totalmente turbulento (SA) vs XFOIL com transição (cruzeiro xtr ≤ 0.10): parte da diferença em cd é física (transição), não erro de nenhum modelo. Por isso `k_cd_profile` é reportado e não é aplicado. RANS estacionário perto da perda: ±10 % em cl_max (NASA TMR).

## 3. Convergência de malha (GCI, Celik et al. 2008)

| grandeza | fina | média | grossa | extrapolada | ordem p | GCI fina % | oscilatória (U %) | deriva iterativa máx % | erro iterativo desprezável |
|---|---|---|---|---|---|---|---|---|---|
| cl | 0.484 | 0.491 | 0.487 | None | 2.11 | None | sim (0.73) | 0.00522 | sim |
| cd | 0.0108 | 0.0116 | 0.0129 | 0.01 | 2.59 | 8.9 | não | 0.0754 | sim |
| cm | -0.0572 | -0.0589 | -0.058 | None | 2.19 | None | sim (1.51) | 0.0158 | sim |

Células [59450, 34248, 21132]; iterações por malha [12000, 16000, 12000]. A GCI só é válida se o erro iterativo for ≪ erro de discretização (Roache 1998; Celik et al. 2008): critério aqui deriva nos últimos 10 % das iterações < 0,1 × |f_fina − f_média|/f_fina. Convergência oscilatória: sem extrapolação de Richardson, incerteza U = ½(f_max − f_min) (Stern et al. 2001).

## 4. Asa 3-D: SU2 Euler vs AVL

CLα Euler = 4.69 /rad vs AVL 4.64 /rad → k_CLα = 1.01 (malha 825464 células, M = 0.184).

CL a α = 0 está 0.0346 acima do AVL da asa, com a mesma inclinação (k_CLα = 1.01): equivale a 0.42° de incidência (ΔCL / CLα). AVL e o STEP usam a mesma incidência (`geometry.wing_incidence_deg`, omissão 0). Não é a área de referência: S_ref = S/2 e um fator 2 mudaria o CL e o CLα juntos.

| α ° | CL | CD | CDi | aceite |
|---|---|---|---|---|
| 0 | 0.207 | -0.049 | 0.00224 | não |
| 4 | 0.534 | -0.0348 | 0.0149 | não |

CD de Euler subsónico devia ser ≥ 0 e próximo de CL²/(π e AR) (Raymer Eq. 12.5 com CD0 = 0; paradoxo de d'Alembert). O CD gravado é o eixo de vento do SU2 (CFx cos α + CFz sin α), com S_ref = S/2 e `MARKER_MONITORING` só na asa. O sinal não se troca: a integral de pressão é mesmo para a frente. Não se aplica como calibração.

## 5. Caixão da asa: CalculiX (cascas S8R + vigas B32) vs viga Fase 3

| grandeza | FEM | Fase 3 |
|---|---|---|
| flecha de ponta (último) m | 0.382 | 0.203 |
| torção de ponta ° | 1.13 | -0.151 |
| λ encurvadura mín. (último) | 0.997 | 1 |
| 1.ª flexão Hz | 6.7 | 8.54 |
| 1.ª torção Hz | 23.5 | 26.8 |

30471 nós, 7696 cascas, 2808 vigas; 196 s.

## 6. Flutter: modos FEM + DLM (p-k) vs estimativa de faixas da Fase 3

| caso | V_F g=0 m/s EAS | V_F g=0.03 m/s EAS | f_F Hz |
|---|---|---|---|
| symmetric | 166 | 171 | 17 |
| antisymmetric | 163 | 168 | 17.4 |

Requisito 1.2 V_D = 118 m/s EAS (1.2 V_D, g ≤ 0.03 (AC 23.629-1B prática; verificar)); margem +43 % → OK. Fase 3 (faixas): V_F = 155 m/s. 

Diagrama V-g-f: `flutter/cessna172_check_vgf.png`.

Deck Nastran SOL 145 (mesma malha/massas/DLM) em `nastran/` — lido de volta com pyNastran; não corrido (sem MSC/NX Nastran aqui).

## 7. Dimensionamento detalhado

**Nervuras** (esmagamento Brazier, Niu Cap. 5): passo 0.828 m, 7 por semi-asa, massa 6.04 kg (Fase 3: 1.76 kg).

| y_m | M_ult_Nm | w_crush_N_per_m | t_web_mm | governed_by |
|---|---|---|---|---|
| 0 | 6.51e+04 | 1.2e+04 | 1.6 | crushing |
| 0.828 | 4.33e+04 | 7.83e+03 | 1.34 | crushing |
| 1.66 | 2.63e+04 | 4.45e+03 | 1.07 | crushing |
| 2.48 | 1.39e+04 | 2.03e+03 | 0.793 | crushing |
| 3.31 | 5.66e+03 | 610 | 0.511 | crushing |
| 4.14 | 1.27e+03 | 63.7 | 0.51 | t_min |
| 4.97 | 2.36 | 0.000346 | 0.51 | t_min |

**Ligação à raiz** (Bruhn D1, fator de ferragem 1.15): P_banzo = 4.97e+05 N → 5 × AN7 (Ø 11.1 mm) em corte duplo, MS = 0.01; chapa de ferragem ≥ 11.5 mm; e ≥ 22.2 mm, passo ≥ 44.4 mm.

**Superfícies de comando** (momento de charneira a V_D, Roskam VI Cap. 10; C_h PRESSUPOSTOS):

| surface | S_c_m2 | c_c_m | H_Nm | torque_req_Nm |
|---|---|---|---|---|
| aileron (each) | 0.545 | 0.311 | 297 | 445 |
| elevator | 0.955 | 0.295 | 493 | 740 |
| rudder | 0.396 | 0.315 | 218 | 327 |

**Pesos Classe II (Roskam Parte V)** vs Raymer (W_TO = 2506 lb, n_ult = 5.93):

| item | Roskam kg | Raymer kg | razão | usado |
|---|---|---|---|---|
| wing (USAF) | 115 | 128 | 0.896 | sim |
| wing (Cessna) | 175 | 128 | 1.37 | sim |
| htail (USAF) | 19.1 | 12.1 | 1.58 | sim |
| htail (Cessna) | 56.4 | 12.1 | 4.67 | não |
| vtail (USAF) | 6.47 | 6.28 | 1.03 | sim |
| vtail (Cessna) | 248 | 6.28 | 39.5 | não |
| fuselage (USAF) | 103 | 97.5 | 1.05 | sim |

- V_H ≈ 1.1 V_C (PRESSUPOSTO); altura da deriva b_v = √(A_v S_v); n_ult = 1.5 n_lim; equações verificadas no texto de Roskam Parte V (págs. 67–76)
- Cessna (asa): inclui comandos e carenagem de ponta; exclui tanques e carry-through
- Cessna Eqs. 5.12–5.13 (empenagem) mostradas só por transparência e EXCLUÍDAS da comparação: dão valores implausíveis (para o C172 várias vezes o peso real da empenagem) — possível erro de impressão; não corrigidas por ajuste

## 8. Fatores de calibração L3 → L1/L2

Rastreáveis: cada fator = razão (ou diferença) alta/baixa fidelidade do mesmo desenho. Aplicados só com `assumptions.calibration.apply: [aero, flutter]` e `file: <esta pasta>/calibration.json`; os de estruturas são só reportados.

| fator | grupo | valor | alta fidelidade | baixa fidelidade | o quê | aplicado |
|---|---|---|---|---|---|---|
| `k_clmax` | aero | 1.060 | 1.815 | 1.713 | section clmax at stall Re, SU2 RANS-SA / XFOIL | não |
| `k_cd_profile` | aero | 1.426 | 0.0119 | 0.008344 | section cd at cl 0.5, cruise Re, SU2 RANS-SA (fully turbulent) / XFOIL | inválido |
| `d_cm0` | aero | -0.007 | -0.057 | -0.05007 | section cm0 (c/4), RANS − XFOIL | não |
| `k_EI` | structures | 0.533 | 0.3816 | 0.2034 | effective bending stiffness ratio = tip deflection beam(Phase 3 EI) / FEM | não |
| `k_GJ` | structures | -0.133 | 1.135 | -0.1513 | effective torsional stiffness ratio = tip twist beam(Phase 3 GJ) / FEM | inválido |
| `k_sigma_cover` | structures | 1.033 | -134.1 | 129.7 | upper-cover stringer σ at ultimate, bay 1 (y = 1.68 m) | não |
| `lambda_buckling` | structures | 0.997 | 0.9969 | 1 | linear buckling eigenvalue at ultimate load (Phase 3 sized to 1.0) | não |
| `k_f_bending` | structures | 0.785 | 6.705 | 8.536 | 1st bending frequency FEM / strip | não |
| `k_f_torsion` | structures | 0.877 | 23.52 | 26.82 | 1st torsion frequency FEM / strip | não |
| `k_flutter` | flutter | 1.083 | 168.3 | 155.4 | flutter speed FEM+DLM p-k (g = 0.03, min sym/antisym) / Phase 3 strip V_F | não |

## 9. Para uma máquina mais potente

- RANS-SA avião completo (meio modelo, `rans_case/`): ≈ 1.4e+07 células, RAM ≈ 25 GB, ≈ 47 h em 8 núcleos / 5.9 h em 64 (3 α). Comandos: `gmsh aircraft_rans.geo -3 -format su2 -o aircraft_half.su2`; `mpirun -n <N> SU2_CFD aircraft_rans.cfg   # AOA in the cfg; repeat for α = 0, 2, 4 (+ stall sweep)`
- Nastran SOL 145: `nastran/*.bdf` (MSC/NX Nastran ou equivalente).
- FEM fino: `fem/` com ds menor (`fem.run_box_fem(res, work, ds=…)`).
