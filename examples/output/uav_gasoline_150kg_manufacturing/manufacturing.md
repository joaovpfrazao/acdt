# Fabrico e custo — N = 50, USD 2025

CPI-U 2025/2012 = 1.4022; fração compósita da estrutura f_comp = 1.00

## Custo unitário (top-down vs bottom-up)

| modelo | custo unitário (USD) |
|---|---:|
| Eastlake (Gudmundsson 2014) | 247,064 |
| DAPCA IV (Raymer 2018) | 463,559 |
| bottom-up (peças + comprados + NRC Eastlake) | 184,815 |

## Escada de fidelidade (L0 → L1 → L2)

| nível | método | custo unitário (USD) | confiança | banda AACE 18R-97 (80 %) |
|---|---|---:|---|---|
| L0 | top-down CERs (modified Eastlake central; DAPCA IV as second CER) | 247,064 | low | Classe 5: 123,532 – 494,129 (-50 % / +100 %) |
| L1 | parametric bottom-up by part/process (preliminary design) | 184,815 | low | Classe 4: 129,370 – 277,222 (-30 % / +50 %) |

Nível recomendado: **L1** (CERs outside their database: the part/process model is the better basis). CERs fora da base de dados: sim — unmanned (uav_tactical_recce_ucav): both CER databases are crewed aircraft. Dispersão Eastlake/DAPCA IV: 1.88x.

L1: labour level anchored to Eastlake (L0 → L1, the reverse of the ladder): only the RELATIVE part/process ranking is bottom-up; replace with shop data or L2

Fatores de calibração (nível superior → inferior; `cost_calibration.json`; aplicados: nenhum):

- `k_cost_L0_eastlake` = 0.748 (unit cost L1 bottom-up / eastlake CER (same design, N, USD year)) — NÃO independente
- `k_cost_L0_dapca4` = 0.399 (unit cost L1 bottom-up / dapca4 CER (same design, N, USD year)) — NÃO independente

## Plano de fabrico (processo escolhido por peça)

| peça | n | material | processo | massa (kg) | h/peça | B2F | custo/aeronave (USD) |
|---|---:|---|---|---:|---:|---:|---:|
| wing skin | 4 | cf_fabric_handlayup | wet_layup | 2.91 | 32.3 | 1.40 | 27,344 |
| wing spar | 4 | cf_fabric_handlayup | wet_layup | 0.47 | 29.1 | 1.40 | 16,649 |
| wing rib | 28 | cf_fabric_handlayup | wet_layup | 0.02 | 6.7 | 1.40 | 22,434 |
| htail skin | 4 | cf_fabric_handlayup | wet_layup | 0.08 | 13.2 | 1.40 | 7,193 |
| htail spar | 2 | cf_fabric_handlayup | wet_layup | 0.01 | 10.3 | 1.40 | 2,437 |
| htail rib | 8 | cf_fabric_handlayup | wet_layup | 0.00 | 4.9 | 1.40 | 4,551 |
| vtail skin | 2 | cf_fabric_handlayup | wet_layup | 0.20 | 15.8 | 1.40 | 4,744 |
| vtail spar | 1 | cf_fabric_handlayup | wet_layup | 0.02 | 11.7 | 1.40 | 1,430 |
| vtail rib | 3 | cf_fabric_handlayup | wet_layup | 0.01 | 6.4 | 1.40 | 2,248 |
| fuselage shell | 2 | cf_fabric_handlayup | wet_layup | 3.23 | 39.1 | 1.40 | 21,190 |
| fuselage frame | 7 | cf_fabric_handlayup | wet_layup | 0.05 | 12.2 | 1.40 | 10,829 |

Totais/aeronave: material 2,073, mão-de-obra 86,600 (772 h), fixadores 0, máquina 0, ferramental/N 32,377 — total 121,049 USD; comprado 31 kg para 22 kg voados

## Calibração

Eastlake (fabrico+QC+material)/N = 150,922 USD vs bottom-up estrutura 88,672 USD (razão 1.70). Eastlake manufacturing covers the whole airframe (parts, assembly, systems installation) while the bottom-up covers the structural parts — a ratio > 1 is expected; a ratio << 1 means the FOPV parameters (transport-wing parts) overestimate these parts: set labour_calibration from shop data (or 'eastlake')

## Notas

- part masses: component masses (weight build-up) split by face area — uniform equivalent gauge (ASSUMPTION)
- wing rib pitch 0.6 MAC (Phase 2 box-sizing ASSUMPTION)
- fuselage frames: 7 at 0.5 m pitch; web depth 0.05 D (layout ASSUMPTION — no cited value, override)
- labour: FOPV/process hours taken as first-unit time, averaged over N=50 with a 85% crawford curve -> LF=0.510 (ASSUMPTION; hours_basis='standard' for LF=1)
- structure parts: bottom-up process model; final assembly/systems installation NOT included (give final_assembly_hours)
- non-recurring engineering/development/flight test taken from Eastlake (no bottom-up model)

## Referências

- AACE International (2020). Recommended Practice 18R-97: Cost Estimate Classification System - as applied in engineering, procurement and construction for the process industries, Table 1 (expected accuracy ranges at 80 % confidence: Class 5 L -20..-50 % H +30..+100 %; Class 4 L -15..-30 % H +20..+50 %; Class 3 L -10..-20 % H +10..+30 %; Class 2 L -5..-15 % H +5..+20 %; Class 1 L -3..-10 % H +3..+15 %); generic principles in RP 17R-97. Ranges widen with technological complexity and weak reference data <https://web.aacei.org/docs/default-source/toc/toc_18r-97.pdf> (retrieved 2026-10-28)
- Abbott, R. (2019). Analysis and Design of Composite and Metallic Flight Vehicle Structures, 3rd ed., Sec. 4.1.8 (after MIL-HDBK-17F Vol. 3 Sec. 9.3): ply drop-offs >= 20:1 in the load direction, <= 2 plies per termination; do not buck rivets in composite laminate; fastener edge distance >= 3.0D (2.5D off-axis) in composites <https://www.abbottaerospace.com/aa-sb-001/4-materials/4-1-composite-materials/4-1-8-general-laminate-design-guidelines/> (retrieved 2026-10-28)
- Bao, H.P. (2002). Process Cost Modeling for Multi-Disciplinary Design Optimization. Final report, NASA grant NAG-1-2195 (ODU), Table 4.1 'V0 and tau values for generic wing' (eq. 3.3) <https://ntrs.nasa.gov/api/citations/20020065232/downloads/20020065232.pdf> (retrieved 2026-10-28)
- U.S. Bureau of Labor Statistics, CPI-U, U.S. city average, all items (CUUR0000SA0), annual averages <https://data.bls.gov/timeseries/CUUR0000SA0> (retrieved 2026-10-28)
- Gonzalo et al. (2023). Automated recycling of unidirectional preimpregnated carbon fibre scraps (Scipedia), citing Blanco et al. (MATCOMP 2018): aeronautical composite parts buy-to-fly 1.1-1.4, scrap up to 30 % <https://www.scipedia.com/public/Gonzalo_et_al_2023a> (retrieved 2026-10-28)
- Gudmundsson, S. (2014). General Aviation Aircraft Design: Applied Methods and Procedures, Elsevier, Ch. 2 (modified Eastlake model, 2012 USD; labour cost = 2.0969 H R CPI; R_ENG 92, R_TOOL 61, R_MFG 53 USD/h; avionics 15000 USD; piston engine 174 P_BHP; constant-speed propeller 209.66 N D^2 (P/D)^0.12) <https://computationaldesignlab.github.io/aircraft-design/cost/unit_cost.html> (retrieved 2026-10-28)
- Gutowski, T.G., Hoult, D., Dillon, G., Neoh, E.T., Muter, S., Kim, E., Tse, M. (1994). Development of a theoretical cost model for advanced composite fabrication. Composites Manufacturing 5(4):231-239 <https://doi.org/10.1016/0956-7143(94)90138-4>
- NASA JSC Cost Estimating — Learning Curve Calculator (Wright cumulative-average and Crawford unit theories; aerospace 85 %) <https://web.archive.org/web/20120830021941/http://cost.jsc.nasa.gov/learn.html> (retrieved 2026-10-28)
- Raymer, D.P. (2018). Aircraft Design: A Conceptual Approach, 6th ed., AIAA, Ch. 18 (DAPCA IV, constant 2012 USD): H_E = 4.86 We^0.777 V^0.894 Q^0.163, H_T = 5.99 We^0.777 V^0.696 Q^0.263, H_M = 7.37 We^0.820 V^0.484 Q^0.641, H_Q = 0.076 H_M (cargo) / 0.133 H_M; C_D = 91.3 We^0.630 V^1.3; C_F = 2498 We^0.325 V^0.822 FTA^1.21; C_M = 22.1 We^0.921 V^0.621 Q^0.799; C_eng = 3112 (0.043 T_max + 243.25 M_max + 0.969 T_t4 - 2228); wrap rates R_E 115, R_T 118, R_Q 108, R_M 98 USD/h. Cross-checked against Ozgen (METU AE452 'Cost of an airplane', 2016) and the SI form of the same equations (5.18/7.22/10.5/67.4/1947/31.2 in kg, km/h) <http://ae.metu.edu.tr/~ae452/cost.pdf> (retrieved 2026-10-28)
