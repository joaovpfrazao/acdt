# Fase 4 — verificação de alta fidelidade: Cessna 172S (verificação) (`cessna172_check`)

L3 verifica o desenho L1/L2 (não redimensiona). Cada número abaixo vem de um ficheiro nesta pasta; casos pesados demais para esta máquina estão escritos com estimativa e comando (secção 9).

## 1. Geometria (OpenVSP → STEP/STL)

| componente | Swet VSP m² | Swet L0 m² | razão |
|---|---|---|---|
| fuselage | 20.8 | 24 | 0.866 |
| wing | 27.8 | 24.6 | 1.13 |
| htail | 4.57 | 5.66 | 0.807 |
| vtail | 1.81 | 2.34 | 0.77 |

Total VSP/L0 = 0.972. CompGeom exclui as interseções (asa–fuselagem, cauda–fuselagem); L0: Raymer Eq. 7.12 com área exposta e Torenbeek App. F para a fuselagem

Render 3-D: `geometry/cessna172_check_3d.png`; STEP: `geometry/cessna172_check.step` (metros).

## 2. Secção: SU2 RANS-SA 2-D vs XFOIL (L1)

| grandeza | RANS | XFOIL | razão/dif. |
|---|---|---|---|
| cl_max (Re de perda) | 1.82 | 1.7 | 1.07 |
| cd @ cl 0.5 (Re cruzeiro) | 0.0118 | 0.00817 | 1.45 |
| cm0 | -0.0565 | -0.0509 | -0.00557 |

Malha 34162 células; RANS totalmente turbulento (SA) vs XFOIL com transição (cruzeiro xtr ≤ 0.10): parte da diferença em cd é física (transição), não erro de nenhum modelo. Por isso `k_cd_profile` é reportado e não é aplicado. RANS estacionário perto da perda: ±10 % em cl_max (NASA TMR).

## 3. Convergência de malha (GCI, Celik et al. 2008)

não corrido: passo não pedido nesta corrida (--steps)

## 4. Asa 3-D: SU2 Euler vs AVL

não corrido: passo não pedido nesta corrida (--steps)

## 5. Caixão da asa: CalculiX (cascas S8R + vigas B32) vs viga Fase 3

| grandeza | FEM | Fase 3 |
|---|---|---|
| flecha de ponta (último) m | 0.249 | 0.276 |
| torção de ponta ° | 1.06 | 1.01 |
| λ encurvadura mín. (último) | 0.978 | 1 |
| 1.ª flexão Hz | 8.14 | 7.25 |
| 1.ª torção Hz | 23.6 | 23.5 |

16647 nós, 4240 cascas, 1404 vigas; 152 s.

## 6. Flutter: modos FEM + DLM (p-k) vs estimativa de faixas da Fase 3

| caso | V_F g=0 m/s EAS | V_F g=0.03 m/s EAS | f_F Hz |
|---|---|---|---|
| symmetric | 158 | 164 | 17.7 |
| antisymmetric | 156 | 162 | 17.7 |

Requisito 1.2 V_D = 117 m/s EAS (1.2 V_D, g ≤ 0.03 (AC 23.629-1B prática; verificar)); margem +38 % → OK. Fase 3 (faixas): V_F = 113 m/s. 

Diagrama V-g-f: `flutter/cessna172_check_vgf.png`.

Deck Nastran SOL 145 (mesma malha/massas/DLM) em `nastran/` — lido de volta com pyNastran; não corrido (sem MSC/NX Nastran aqui).

## 7. Dimensionamento detalhado

**Nervuras** (esmagamento Brazier, Niu Cap. 5): passo 0.839 m, 7 por semi-asa, massa 7.42 kg (Fase 3: 1.81 kg).

| y_m | M_ult_Nm | w_crush_N_per_m | t_web_mm | governed_by |
|---|---|---|---|---|
| 0 | 6.73e+04 | 2.05e+04 | 1.93 | crushing |
| 0.839 | 4.48e+04 | 1.36e+04 | 1.62 | crushing |
| 1.68 | 2.72e+04 | 7.91e+03 | 1.31 | crushing |
| 2.52 | 1.43e+04 | 3.75e+03 | 0.983 | crushing |
| 3.36 | 5.85e+03 | 1.22e+03 | 0.649 | crushing |
| 4.2 | 1.31e+03 | 156 | 0.51 | t_min |
| 5.04 | 2.44 | 0.000875 | 0.51 | t_min |

**Ligação à raiz** (Bruhn D1, fator de ferragem 1.15): P_banzo = 5.07e+05 N → 6 × AN7 (Ø 11.1 mm) em corte duplo, MS = 0.19; chapa de ferragem ≥ 9.73 mm; e ≥ 22.2 mm, passo ≥ 44.4 mm.

**Superfícies de comando** (momento de charneira a V_D, Roskam VI Cap. 10; C_h PRESSUPOSTOS):

| surface | S_c_m2 | c_c_m | H_Nm | torque_req_Nm |
|---|---|---|---|---|
| aileron (each) | 0.56 | 0.316 | 307 | 461 |
| elevator | 0.99 | 0.3 | 517 | 776 |
| rudder | 0.41 | 0.321 | 229 | 343 |

**Pesos Classe II (Roskam Parte V)** vs Raymer (W_TO = 2560 lb, n_ult = 5.93):

| item | Roskam kg | Raymer kg | razão | usado |
|---|---|---|---|---|
| wing (USAF) | 118 | 132 | 0.895 | sim |
| wing (Cessna) | 178 | 132 | 1.35 | sim |
| htail (USAF) | 19.6 | 12.6 | 1.56 | sim |
| htail (Cessna) | 57.4 | 12.6 | 4.56 | não |
| vtail (USAF) | 6.66 | 6.53 | 1.02 | sim |
| vtail (Cessna) | 259 | 6.53 | 39.6 | não |
| fuselage (USAF) | 104 | 98.9 | 1.05 | sim |

- V_H ≈ 1.1 V_C (PRESSUPOSTO); altura da deriva b_v = √(A_v S_v); n_ult = 1.5 n_lim; equações verificadas no texto de Roskam Parte V (págs. 67–76)
- Cessna (asa): inclui comandos e carenagem de ponta; exclui tanques e carry-through
- Cessna Eqs. 5.12–5.13 (empenagem) mostradas só por transparência e EXCLUÍDAS da comparação: dão valores implausíveis (para o C172 várias vezes o peso real da empenagem) — possível erro de impressão; não corrigidas por ajuste

## 8. Fatores de calibração L3 → L1/L2

Rastreáveis: cada fator = razão (ou diferença) alta/baixa fidelidade do mesmo desenho. Aplicados só com `assumptions.calibration.apply: [aero, flutter]` e `file: <esta pasta>/calibration.json`; os de estruturas são só reportados.

| fator | grupo | valor | alta fidelidade | baixa fidelidade | o quê | aplicado |
|---|---|---|---|---|---|---|
| `k_clmax` | aero | 1.069 | 1.816 | 1.699 | section clmax at stall Re, SU2 RANS-SA / XFOIL | não |
| `k_cd_profile` | aero | 1.446 | 0.01181 | 0.00817 | section cd at cl 0.5, cruise Re, SU2 RANS-SA (fully turbulent) / XFOIL | inválido |
| `d_cm0` | aero | -0.006 | -0.05647 | -0.0509 | section cm0 (c/4), RANS − XFOIL | não |
| `k_EI` | structures | 1.112 | 0.2486 | 0.2764 | effective bending stiffness ratio = tip deflection beam(Phase 3 EI) / FEM | não |
| `k_GJ` | structures | 0.948 | 1.064 | 1.009 | effective torsional stiffness ratio = tip twist beam(Phase 3 GJ) / FEM | não |
| `k_sigma_cover` | structures | 0.989 | -128 | 129.4 | upper-cover stringer σ at ultimate, bay 1 (y = 1.70 m) | não |
| `lambda_buckling` | structures | 0.978 | 0.9781 | 1 | linear buckling eigenvalue at ultimate load (Phase 3 sized to 1.0) | não |
| `k_f_bending` | structures | 1.122 | 8.137 | 7.25 | 1st bending frequency FEM / strip | não |
| `k_f_torsion` | structures | 1.003 | 23.59 | 23.51 | 1st torsion frequency FEM / strip | não |
| `k_flutter` | flutter | 1.434 | 162 | 113 | flutter speed FEM+DLM p-k (g = 0.03, min sym/antisym) / Phase 3 strip V_F | não |

## 9. Para uma máquina mais potente

- RANS-SA avião completo (meio modelo, `rans_case/`): ≈ 1.4e+07 células, RAM ≈ 25 GB, ≈ 47 h em 8 núcleos / 5.8 h em 64 (3 α). Comandos: `gmsh aircraft_rans.geo -3 -format su2 -o aircraft_half.su2`; `mpirun -n <N> SU2_CFD aircraft_rans.cfg   # AOA in the cfg; repeat for α = 0, 2, 4 (+ stall sweep)`
- Asa 3-D Euler (`wing_euler/`): malha tetraédrica Gmsh + SU2 Euler; ver secção 4.
- Nastran SOL 145: `nastran/*.bdf` (MSC/NX Nastran ou equivalente).
- FEM fino: `fem/` com ds menor (`fem.run_box_fem(res, work, ds=…)`).
