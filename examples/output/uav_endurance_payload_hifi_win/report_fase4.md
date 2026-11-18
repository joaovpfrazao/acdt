# Fase 4 — verificação de alta fidelidade: UAV ISR elétrico 25 kg (`uav_endurance_payload`)

L3 verifica o desenho L1/L2 (não redimensiona). Cada número abaixo vem de um ficheiro nesta pasta; casos pesados demais para esta máquina estão escritos com estimativa e comando (secção 9).

## 1. Geometria (OpenVSP → STEP/STL)

não corrido: passo não pedido nesta corrida (--steps)

## 2. Secção: SU2 RANS-SA 2-D vs XFOIL (L1)

não corrido: passo não pedido nesta corrida (--steps)

## 3. Convergência de malha (GCI, Celik et al. 2008)

não corrido: passo não pedido nesta corrida (--steps)

## 4. Asa 3-D: SU2 Euler vs AVL

não corrido: passo não pedido nesta corrida (--steps)

## 5. Caixão da asa: CalculiX (cascas S8R + vigas B32) vs viga Fase 3

| grandeza | FEM | Fase 3 |
|---|---|---|
| flecha de ponta (último) m | 0.154 | 0.11 |
| torção de ponta ° | 0.774 | 0.168 |
| λ encurvadura mín. (último) | 0.983 | 1 |
| 1.ª flexão Hz | 9.03 | 10.5 |
| 1.ª torção Hz | 76.9 | 79.8 |

8700 nós, 2232 cascas, 308 vigas; 15.4 s.

## 6. Flutter: modos FEM + DLM (p-k) vs estimativa de faixas da Fase 3

| caso | V_F g=0 m/s EAS | V_F g=0.03 m/s EAS | f_F Hz |
|---|---|---|---|
| symmetric | 128 | 132 | 54.7 |
| antisymmetric | 127 | 132 | 54.9 |

Requisito 1.2 V_D = 32.1 m/s EAS (1.2 V_D, g ≤ 0.03 (AC 23.629-1B prática; verificar)); margem +311 % → OK. Fase 3 (faixas): V_F = 127 m/s. varrimento estendido até 6 V_D (sem cruzamento até 2.5 V_D)

Diagrama V-g-f: `flutter/uav_endurance_payload_vgf.png`.

Deck Nastran SOL 145 (mesma malha/massas/DLM) em `nastran/` — lido de volta com pyNastran; não corrido (sem MSC/NX Nastran aqui).

## 7. Dimensionamento detalhado

**Nervuras** (esmagamento Brazier, Niu Cap. 5): passo 0.185 m, 12 por semi-asa, massa 0.0748 kg (Fase 3: 0.0392 kg).

| y_m | M_ult_Nm | w_crush_N_per_m | t_web_mm | governed_by |
|---|---|---|---|---|
| 0 | 677 | 875 | 0.288 | crushing |
| 0.371 | 436 | 629 | 0.25 | t_min |
| 0.741 | 252 | 380 | 0.25 | t_min |
| 1.11 | 123 | 170 | 0.25 | t_min |
| 1.48 | 43 | 39 | 0.25 | t_min |
| 1.85 | 6 | 1.36 | 0.25 | t_min |

**Ligação à raiz** (Bruhn D1, fator de ferragem 1.15): P_banzo = 2.03e+04 N → 2 × AN3 (Ø 4.76 mm) em corte duplo, MS = 0.82; chapa de ferragem ≥ 4.26 mm; e ≥ 9.52 mm, passo ≥ 19 mm.

**Superfícies de comando** (momento de charneira a V_D, Roskam VI Cap. 10; C_h PRESSUPOSTOS):

| surface | S_c_m2 | c_c_m | H_Nm | torque_req_Nm |
|---|---|---|---|---|
| aileron (each) | 0.0491 | 0.0662 | 0.421 | 0.631 |
| elevator | 0.0699 | 0.0799 | 0.725 | 1.09 |
| rudder | 0.0576 | 0.12 | 0.897 | 1.35 |

**Pesos Classe II (Roskam Parte V)** vs Raymer (W_TO = 51 lb, n_ult = 8):

| item | Roskam kg | Raymer kg | razão | usado |
|---|---|---|---|---|
| wing (USAF) | 3.39 | 4.55 | 0.745 | sim |
| wing (Cessna) | 54.4 | 4.55 | 12 | não |
| htail (USAF) | 0.763 | 0.365 | 2.09 | sim |
| htail (Cessna) | 1.84 | 0.365 | 5.03 | não |
| vtail (USAF) | 0.536 | 0.3 | 1.79 | sim |
| vtail (Cessna) | 5.05 | 0.3 | 16.8 | não |
| fuselage (USAF) | 0.84 | 1.09 | 0.772 | sim |

- V_H ≈ 1.1 V_C (PRESSUPOSTO); altura da deriva b_v = √(A_v S_v); n_ult = 1.5 n_lim; equações verificadas no texto de Roskam Parte V (págs. 67–76)
- Cessna (asa): inclui comandos e carenagem de ponta; exclui tanques e carry-through
- Cessna Eqs. 5.12–5.13 (empenagem) mostradas só por transparência e EXCLUÍDAS da comparação: dão valores implausíveis (para o C172 várias vezes o peso real da empenagem) — possível erro de impressão; não corrigidas por ajuste
- W_TO = 51 lb: fora da base estatística (aviação geral) — extrapolação, só indicativo; Cessna (asa, ∝ A^1.712) excluída

## 8. Fatores de calibração L3 → L1/L2

Rastreáveis: cada fator = razão (ou diferença) alta/baixa fidelidade do mesmo desenho. Aplicados só com `assumptions.calibration.apply: [aero, flutter]` e `file: <esta pasta>/calibration.json`; os de estruturas são só reportados.

| fator | grupo | valor | alta fidelidade | baixa fidelidade | o quê | aplicado |
|---|---|---|---|---|---|---|
| `k_EI` | structures | 0.715 | 0.1538 | 0.11 | effective bending stiffness ratio = tip deflection beam(Phase 3 EI) / FEM | não |
| `k_GJ` | structures | 0.217 | 0.7736 | 0.1677 | effective torsional stiffness ratio = tip twist beam(Phase 3 GJ) / FEM | não |
| `k_sigma_cap` | structures | 0.362 | -180.8 | 500 | spar-cap abs(σ) at ultimate / allowable (Phase 3 sizing target ≤ 1) | não |
| `lambda_buckling` | structures | 0.983 | 0.9834 | 1 | linear buckling eigenvalue at ultimate load (Phase 3 sized to 1.0) | não |
| `k_f_bending` | structures | 0.860 | 9.034 | 10.51 | 1st bending frequency FEM / strip | não |
| `k_f_torsion` | structures | 0.964 | 76.88 | 79.77 | 1st torsion frequency FEM / strip | não |
| `k_flutter` | flutter | 1.040 | 131.7 | 126.7 | flutter speed FEM+DLM p-k (g = 0.03, min sym/antisym) / Phase 3 strip V_F | não |

## 9. Para uma máquina mais potente

- Asa 3-D Euler (`wing_euler/`): malha tetraédrica Gmsh + SU2 Euler; ver secção 4.
- Nastran SOL 145: `nastran/*.bdf` (MSC/NX Nastran ou equivalente).
- FEM fino: `fem/` com ds menor (`fem.run_box_fem(res, work, ds=…)`).
