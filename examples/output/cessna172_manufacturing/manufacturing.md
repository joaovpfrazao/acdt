# Fabrico e custo — N = 820, USD 2025

CPI-U 2025/2012 = 1.4022; fração compósita da estrutura f_comp = 0.00

## Custo unitário (top-down vs bottom-up)

| modelo | custo unitário (USD) |
|---|---:|
| Eastlake (Gudmundsson 2014) | 280,909 |
| DAPCA IV (Raymer 2018) | 793,595 |
| bottom-up (peças + comprados + NRC Eastlake) | 691,875 |

## Escada de fidelidade (L0 → L1 → L2)

| nível | método | custo unitário (USD) | confiança | banda AACE 18R-97 (80 %) |
|---|---|---:|---|---|
| L0 | top-down CERs (modified Eastlake central; DAPCA IV as second CER) | 280,909 | medium | Classe 5: 224,727 – 365,181 (-20 % / +30 %) |
| L1 | parametric bottom-up by part/process (preliminary design) | 691,875 | low-medium | Classe 4: 484,313 – 1,037,813 (-30 % / +50 %) |

Nível recomendado: **L0** (conventional design inside the CER database and L1 not calibrated by shop/L2 data (public FOPV parameters): keep the CER as the reference, use L1 for relative choices). CERs fora da base de dados: não. Dispersão Eastlake/DAPCA IV: 2.83x.

Fatores de calibração (nível superior → inferior; `cost_calibration.json`; aplicados: nenhum):

- `k_cost_L0_eastlake` = 2.463 (unit cost L1 bottom-up / eastlake CER (same design, N, USD year))
- `k_cost_L0_dapca4` = 0.872 (unit cost L1 bottom-up / dapca4 CER (same design, N, USD year))

Preço público: 499,000 USD — fliegermagazin 2025-05-05: Cessna 172 Skyhawk list price USD 499,000

Razões modelo/preço: Eastlake 0.56, DAPCA IV 1.59, bottom-up 1.39 (models give manufacturer COST; a list PRICE adds profit, liability, distribution — ratio < 1 expected)

## Plano de fabrico (processo escolhido por peça)

| peça | n | material | processo | massa (kg) | h/peça | B2F | custo/aeronave (USD) |
|---|---:|---|---|---:|---:|---:|---:|
| wing skin | 4 | al2024_t3 | sheet_metal_riveted | 27.66 | 185.3 | 2.00 | 94,445 |
| wing spar | 4 | al2024_t3 | sheet_metal_riveted | 3.75 | 144.1 | 2.00 | 67,296 |
| wing rib | 14 | al2024_t3 | sheet_metal_riveted | 0.46 | 53.8 | 2.00 | 85,632 |
| htail skin | 4 | al2024_t3 | sheet_metal_riveted | 2.88 | 100.4 | 2.00 | 47,384 |
| htail spar | 2 | al2024_t3 | cnc_machining | 0.28 | 72.3 | 6.67 | 16,404 |
| htail rib | 8 | al2024_t3 | cnc_machining | 0.06 | 37.5 | 6.67 | 33,836 |
| vtail skin | 2 | al2024_t3 | sheet_metal_riveted | 2.99 | 92.7 | 2.00 | 21,784 |
| vtail spar | 1 | al2024_t3 | cnc_machining | 0.29 | 64.1 | 6.67 | 7,282 |
| vtail rib | 3 | al2024_t3 | cnc_machining | 0.09 | 38.7 | 6.67 | 13,103 |
| fuselage shell | 2 | al2024_t3 | sheet_metal_riveted | 43.04 | 250.5 | 2.00 | 65,960 |
| fuselage frame | 17 | al2024_t3 | sheet_metal_riveted | 0.75 | 81.4 | 2.00 | 158,389 |

Totais/aeronave: material 13,937, mão-de-obra 579,528 (5166 h), fixadores 4,685, máquina 0, ferramental/N 13,366 — total 611,516 USD; comprado 508 kg para 250 kg voados

## Calibração

Eastlake (fabrico+QC+material)/N = 187,183 USD vs bottom-up estrutura 598,150 USD (razão 0.31). Eastlake manufacturing covers the whole airframe (parts, assembly, systems installation) while the bottom-up covers the structural parts — a ratio > 1 is expected; a ratio << 1 means the FOPV parameters (transport-wing parts) overestimate these parts: set labour_calibration from shop data (or 'eastlake')

## Notas

- part masses: component masses (weight build-up) split by face area — uniform equivalent gauge (ASSUMPTION)
- wing rib pitch 0.6 MAC (Phase 2 box-sizing ASSUMPTION)
- fuselage frames: 17 at 0.5 m pitch; web depth 0.05 D (layout ASSUMPTION — no cited value, override)
- labour: FOPV/process hours taken as first-unit time, averaged over N=820 with a 85% crawford curve -> LF=0.270 (ASSUMPTION; hours_basis='standard' for LF=1)
- structure parts: bottom-up process model; final assembly/systems installation NOT included (give final_assembly_hours)
- non-recurring engineering/development/flight test taken from Eastlake (no bottom-up model)

## Referências

- AACE International (2020). Recommended Practice 18R-97: Cost Estimate Classification System - as applied in engineering, procurement and construction for the process industries, Table 1 (expected accuracy ranges at 80 % confidence: Class 5 L -20..-50 % H +30..+100 %; Class 4 L -15..-30 % H +20..+50 %; Class 3 L -10..-20 % H +10..+30 %; Class 2 L -5..-15 % H +5..+20 %; Class 1 L -3..-10 % H +3..+15 %); generic principles in RP 17R-97. Ranges widen with technological complexity and weak reference data <https://web.aacei.org/docs/default-source/toc/toc_18r-97.pdf> (retrieved 2026-10-28)
- Airbus (2018-04). Metals and composites: finding the right material for each application — 'only 10-20 percent of what we buy ends up in use on an aircraft' (subtractive metal parts) <https://www.airbus.com/en/newsroom/stories/2018-04-metals-and-composites-finding-the-right-material-for-each-application> (retrieved 2026-10-28)
- Bao, H.P. (2002). Process Cost Modeling for Multi-Disciplinary Design Optimization. Final report, NASA grant NAG-1-2195 (ODU), Table 4.1 'V0 and tau values for generic wing' (eq. 3.3) <https://ntrs.nasa.gov/api/citations/20020065232/downloads/20020065232.pdf> (retrieved 2026-10-28)
- U.S. Bureau of Labor Statistics, CPI-U, U.S. city average, all items (CUUR0000SA0), annual averages <https://data.bls.gov/timeseries/CUUR0000SA0> (retrieved 2026-10-28)
- Alma CAM / DAHER-Socata (Tarbes) case study: routed aluminium sheet parts, automatic nesting reduced offcuts from 65 % to 50 % <https://www.casestudies.com/company/alma-cam/case-study/intelligent-nesting-software-for-routing-socatas-aluminium-parts> (retrieved 2026-10-28)
- FAA-H-8083-31 Aviation Maintenance Technician Handbook - Airframe Vol. 1, Ch. 4: rivet pitch 4-6 rivet diameters (typical), transverse pitch 75 % of pitch, rivet diameter about 3x the thicker sheet; AC 43.13-1B par. 4-57: minimum edge distance 2D, minimum pitch 3D (single row) / 4D (multi-row) <https://www.faa.gov/documentlibrary/media/advisory_circular/ac_43.13-1b_w-chg1.pdf> (retrieved 2026-10-28)
- Gudmundsson, S. (2014). General Aviation Aircraft Design: Applied Methods and Procedures, Elsevier, Ch. 2 (modified Eastlake model, 2012 USD; labour cost = 2.0969 H R CPI; R_ENG 92, R_TOOL 61, R_MFG 53 USD/h; avionics 15000 USD; piston engine 174 P_BHP; constant-speed propeller 209.66 N D^2 (P/D)^0.12) <https://computationaldesignlab.github.io/aircraft-design/cost/unit_cost.html> (retrieved 2026-10-28)
- Gutowski, T.G., Hoult, D., Dillon, G., Neoh, E.T., Muter, S., Kim, E., Tse, M. (1994). Development of a theoretical cost model for advanced composite fabrication. Composites Manufacturing 5(4):231-239 <https://doi.org/10.1016/0956-7143(94)90138-4>
- NASA JSC Cost Estimating — Learning Curve Calculator (Wright cumulative-average and Crawford unit theories; aerospace 85 %) <https://web.archive.org/web/20120830021941/http://cost.jsc.nasa.gov/learn.html> (retrieved 2026-10-28)
- Raymer, D.P. (2018). Aircraft Design: A Conceptual Approach, 6th ed., AIAA, Ch. 18 (DAPCA IV, constant 2012 USD): H_E = 4.86 We^0.777 V^0.894 Q^0.163, H_T = 5.99 We^0.777 V^0.696 Q^0.263, H_M = 7.37 We^0.820 V^0.484 Q^0.641, H_Q = 0.076 H_M (cargo) / 0.133 H_M; C_D = 91.3 We^0.630 V^1.3; C_F = 2498 We^0.325 V^0.822 FTA^1.21; C_M = 22.1 We^0.921 V^0.621 Q^0.799; C_eng = 3112 (0.043 T_max + 243.25 M_max + 0.969 T_t4 - 2228); wrap rates R_E 115, R_T 118, R_Q 108, R_M 98 USD/h. Cross-checked against Ozgen (METU AE452 'Cost of an airplane', 2016) and the SI form of the same equations (5.18/7.22/10.5/67.4/1947/31.2 in kg, km/h) <http://ae.metu.edu.tr/~ae452/cost.pdf> (retrieved 2026-10-28)
