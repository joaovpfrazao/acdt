# Fase 4 — verificação de alta fidelidade: UAV ISR elétrico 25 kg (`uav_endurance_payload`)

L3 verifica o desenho L1/L2 (não redimensiona). Cada número abaixo vem de um ficheiro nesta pasta; casos pesados demais para esta máquina estão escritos com estimativa e comando (secção 9).

## 1. Geometria (OpenVSP → STEP/STL)

| componente | Swet VSP m² | Swet L0 m² | razão |
|---|---|---|---|
| fuselage | 0.867 | 1.05 | 0.828 |
| wing | 2.52 | 2.5 | 1.01 |
| htail | 0.39 | 0.418 | 0.932 |
| vtail | 0.337 | 0.344 | 0.98 |

Total VSP/L0 = 0.955. CompGeom exclui as interseções (asa–fuselagem, cauda–fuselagem); L0: Raymer Eq. 7.12 com área exposta e Torenbeek App. F para a fuselagem

Render 3-D: `geometry/uav_endurance_payload_3d.png`; STEP: `geometry/uav_endurance_payload.step` (metros).

## 2. Secção: SU2 RANS-SA 2-D vs XFOIL (L1)

| grandeza | RANS | XFOIL | razão/dif. |
|---|---|---|---|
| cl_max (Re de perda) | 1.69 | 1.44 | 1.17 |
| cd @ cl 0.5 (Re cruzeiro) | 0.0158 | 0.0113 | 1.4 |
| cm0 | -0.103 | -0.0975 | -0.00568 |

Malha 29096 células; RANS totalmente turbulento (SA) vs XFOIL com transição (cruzeiro xtr ≤ 0.10): parte da diferença em cd é física (transição), não erro de nenhum modelo. Por isso `k_cd_profile` é reportado e não é aplicado. RANS estacionário perto da perda: ±10 % em cl_max (NASA TMR).

## 3. Convergência de malha (GCI, Celik et al. 2008)

não corrido: passo não pedido nesta corrida (--steps)

## 4. Asa 3-D: SU2 Euler vs AVL

não corrido: passo não pedido nesta corrida (--steps)

## 5. Caixão da asa: CalculiX (cascas S8R + vigas B32) vs viga Fase 3

| grandeza | FEM | Fase 3 |
|---|---|---|
| flecha de ponta (último) m | 0.0987 | 0.147 |
| torção de ponta ° | 0.734 | 0.82 |
| λ encurvadura mín. (último) | 3.54 | 1 |
| 1.ª flexão Hz | 11.4 | 9 |
| 1.ª torção Hz | 76.6 | 68.4 |

8700 nós, 2232 cascas, 308 vigas; 49.2 s.

## 6. Flutter: modos FEM + DLM (p-k) vs estimativa de faixas da Fase 3

| caso | V_F g=0 m/s EAS | V_F g=0.03 m/s EAS | f_F Hz |
|---|---|---|---|
| symmetric | 122 | 127 | 56.8 |
| antisymmetric | 121 | 127 | 57.4 |

Requisito 1.2 V_D = 32.1 m/s EAS (1.2 V_D, g ≤ 0.03 (AC 23.629-1B prática; verificar)); margem +296 % → OK. Fase 3 (faixas): V_F = 92.4 m/s. varrimento estendido até 6 V_D (sem cruzamento até 2.5 V_D)

Diagrama V-g-f: `flutter/uav_endurance_payload_vgf.png`.

Deck Nastran SOL 145 (mesma malha/massas/DLM) em `nastran/` — lido de volta com pyNastran; não corrido (sem MSC/NX Nastran aqui).

## 7. Dimensionamento detalhado

**Nervuras** (esmagamento Brazier, Niu Cap. 5): passo 0.187 m, 12 por semi-asa, massa 0.0815 kg (Fase 3: 0.0401 kg).

| y_m | M_ult_Nm | w_crush_N_per_m | t_web_mm | governed_by |
|---|---|---|---|---|
| 0 | 692 | 1.4e+03 | 0.339 | crushing |
| 0.374 | 445 | 1.05e+03 | 0.288 | crushing |
| 0.749 | 257 | 673 | 0.25 | t_min |
| 1.12 | 125 | 320 | 0.25 | t_min |
| 1.5 | 43.9 | 76.7 | 0.25 | t_min |
| 1.87 | 6.12 | 2.67 | 0.25 | t_min |

**Ligação à raiz** (Bruhn D1, fator de ferragem 1.15): P_banzo = 2.05e+04 N → 2 × AN3 (Ø 4.76 mm) em corte duplo, MS = 0.80; chapa de ferragem ≥ 4.3 mm; e ≥ 9.52 mm, passo ≥ 19 mm.

**Superfícies de comando** (momento de charneira a V_D, Roskam VI Cap. 10; C_h PRESSUPOSTOS):

| surface | S_c_m2 | c_c_m | H_Nm | torque_req_Nm |
|---|---|---|---|---|
| aileron (each) | 0.0501 | 0.0669 | 0.434 | 0.651 |
| elevator | 0.0721 | 0.0811 | 0.758 | 1.14 |
| rudder | 0.0593 | 0.122 | 0.939 | 1.41 |

**Pesos Classe II (Roskam Parte V)** vs Raymer (W_TO = 52 lb, n_ult = 8.04):

| item | Roskam kg | Raymer kg | razão | usado |
|---|---|---|---|---|
| wing (USAF) | 3.47 | 4.66 | 0.744 | sim |
| wing (Cessna) | 55.1 | 4.66 | 11.8 | não |
| htail (USAF) | 0.78 | 0.376 | 2.07 | sim |
| htail (Cessna) | 1.85 | 0.376 | 4.92 | não |
| vtail (USAF) | 0.549 | 0.31 | 1.77 | sim |
| vtail (Cessna) | 5.21 | 0.31 | 16.8 | não |
| fuselage (USAF) | 0.844 | 1.09 | 0.774 | sim |

- V_H ≈ 1.1 V_C (PRESSUPOSTO); altura da deriva b_v = √(A_v S_v); n_ult = 1.5 n_lim; equações verificadas no texto de Roskam Parte V (págs. 67–76)
- Cessna (asa): inclui comandos e carenagem de ponta; exclui tanques e carry-through
- Cessna Eqs. 5.12–5.13 (empenagem) mostradas só por transparência e EXCLUÍDAS da comparação: dão valores implausíveis (para o C172 várias vezes o peso real da empenagem) — possível erro de impressão; não corrigidas por ajuste
- W_TO = 52 lb: fora da base estatística (aviação geral) — extrapolação, só indicativo; Cessna (asa, ∝ A^1.712) excluída

## 8. Fatores de calibração L3 → L1/L2

Rastreáveis: cada fator = razão (ou diferença) alta/baixa fidelidade do mesmo desenho. Aplicados só com `assumptions.calibration.apply: [aero, flutter]` e `file: <esta pasta>/calibration.json`; os de estruturas são só reportados.

| fator | grupo | valor | alta fidelidade | baixa fidelidade | o quê | aplicado |
|---|---|---|---|---|---|---|
| `k_clmax` | aero | 1.175 | 1.686 | 1.435 | section clmax at stall Re, SU2 RANS-SA / XFOIL | não |
| `k_cd_profile` | aero | 1.403 | 0.0158 | 0.01126 | section cd at cl 0.5, cruise Re, SU2 RANS-SA (fully turbulent) / XFOIL | inválido |
| `d_cm0` | aero | -0.006 | -0.1032 | -0.0975 | section cm0 (c/4), RANS − XFOIL | não |
| `k_EI` | structures | 1.487 | 0.09872 | 0.1468 | effective bending stiffness ratio = tip deflection beam(Phase 3 EI) / FEM | não |
| `k_GJ` | structures | 1.116 | 0.7341 | 0.8195 | effective torsional stiffness ratio = tip twist beam(Phase 3 GJ) / FEM | não |
| `k_sigma_cap` | structures | 0.266 | -132.8 | 500 | spar-cap |σ| at ultimate / allowable (Phase 3 sizing target ≤ 1) | não |
| `lambda_buckling` | structures | 3.536 | 3.536 | 1 | linear buckling eigenvalue at ultimate load (Phase 3 sized to 1.0) | não |
| `k_f_bending` | structures | 1.262 | 11.36 | 9.003 | 1st bending frequency FEM / strip | não |
| `k_f_torsion` | structures | 1.119 | 76.58 | 68.44 | 1st torsion frequency FEM / strip | não |
| `k_flutter` | flutter | 1.373 | 126.8 | 92.37 | flutter speed FEM+DLM p-k (g = 0.03, min sym/antisym) / Phase 3 strip V_F | não |

## 9. Para uma máquina mais potente

- RANS-SA avião completo (meio modelo, `rans_case/`): ≈ 1.59e+07 células, RAM ≈ 29 GB, ≈ 53 h em 8 núcleos / 6.6 h em 64 (3 α). Comandos: `gmsh aircraft_rans.geo -3 -format su2 -o aircraft_half.su2`; `mpirun -n <N> SU2_CFD aircraft_rans.cfg   # AOA in the cfg; repeat for α = 0, 2, 4 (+ stall sweep)`
- Asa 3-D Euler (`wing_euler/`): malha tetraédrica Gmsh + SU2 Euler; ver secção 4.
- Nastran SOL 145: `nastran/*.bdf` (MSC/NX Nastran ou equivalente).
- FEM fino: `fem/` com ds menor (`fem.run_box_fem(res, work, ds=…)`).
