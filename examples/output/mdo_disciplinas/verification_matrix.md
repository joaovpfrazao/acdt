# Matriz de verificação

Formato `acdt.verification/1`. Evidência: `` (SHA-256 `—`). Proveniência: impressão digital `2e68a5908d93` (registo escrito no fim da corrida).

Estados: **passa**, **falha**, **no_limite** (dentro da tolerância declarada), **nao_avaliado** (sem avaliador ou etapa não correu), **desconhecido** (correu sem valor). Não avaliado ≠ passa.

| Estado | N.º |
|---|---|
| passa | 5 |
| falha | 1 |
| no_limite | 3 |
| nao_avaliado | 1 |
| desconhecido | 1 |

| ID | Estado | Requisito | Origem | Limiar | Valor | Margem | Avaliador | Método | Fid. (exig./aval.) | Nota |
|---|---|---|---|---|---|---|---|---|---|---|
| REQ-propulsion_type | nao_avaliado | propulsion_type target electric | missao | electric | — | — | — | analise | N0/— | sem avaliador declarado |
| REQ-regulatory_category | desconhecido | regulatory_category target easa_specific | missao | easa_specific | — | — | check:regulatory_category | analise | N0/N1 | easa_specific: no numeric limit |
| REQ-payload_mass | passa | payload_mass target 4.0 kg | missao | = 4.0 kg | 4 kg | +0.000 % | entrada:payload_mass | inspecao | N0/N0 | entrada do dimensionamento (cumprida por construção) |
| REQ-endurance | no_limite | endurance min 2.0 h | missao | ≥ 2.0 h | 2 h | +0.000 % | perf:endurance | analise | N1/N1 | tempo em espera (segmentos); dentro da banda ±0.001 (resolução do avaliador 0.001 (performance_analysis: comparação a 0,1 %)) |
| REQ-cruise_speed | passa | cruise_speed target 22 m/s | missao | = 22 m/s | 22 m/s | +0.000 % | entrada:cruise_speed | inspecao | N0/N0 | entrada do dimensionamento (cumprida por construção) |
| REQ-cruise_altitude | passa | cruise_altitude target 600 m | missao | = 600 m | 600 m | +0.000 % | entrada:cruise_altitude | inspecao | N0/N0 | entrada do dimensionamento (cumprida por construção) |
| REQ-stall_speed | no_limite | stall_speed max 13 m/s | missao | ≤ 13 m/s | 13 m/s | +0.000 % | sizing:stall_speed | analise | N0/N0 | V_s = √(2 (W/S) f_ater / (ρ C_Lmax,ater)) = 13.000 m/s (Raymer Eq. 5.6; W/S 177.0 N/m², f_ater 1, C_Lmax,ater 1.710, h 0 m); dentro da banda ±1e-05 (resolução d |
| REQ-climb_rate | no_limite | climb_rate min 3.0 m/s | missao | ≥ 3.0 m/s | 3 m/s | +0.000 % | perf:climb_rate | analise | N1/N1 | ROC máx. ao nível do mar; dentro da banda ±0.001 (resolução do avaliador 0.001 (performance_analysis: comparação a 0,1 %)) |
| REQ-service_ceiling | passa | service_ceiling min 3000 m | missao | ≥ 3000 m | 9000 m | +200.0 % | perf:service_ceiling | analise | N1/N1 | teto de serviço (Anderson) > 9000 m (não atingido) |
| REQ-wing_span | passa | wing_span max 4.2 m | missao | ≤ 4.2 m | 3.735 m | +11.1 % | resultado:geometry.wing.span_m | analise | N0/N0 |  |
| REQ-mtow | falha | mtow max 25 kg | missao | ≤ 25 kg | 27.98 kg | -11.9 % | resultado:weights.W0_kg | analise | N0/N0 |  |

## Cobertura

* Requisitos sem avaliador (nem filhos): REQ-propulsion_type
* Avaliadores não registados: nenhum
* Evidência sem requisito (26): `check:hq:CAP`, `check:hq:phugoid`, `check:hq:scissor`, `check:hq:short_period`, `check:mtow`, `check:static_margin`, `check:trim`, `check:wb:envelope`, `check:wing_span`, `ciclo_vida:co2e_per_flight_hour_kg`, `ciclo_vida:cost_per_flight_hour_USD`, `ciclo_vida:life_cycle_co2e_kg`, `ciclo_vida:life_cycle_cost_USD`, `custo_serie:break_even_quantity`, `custo_serie:flyaway_cost_USD`, `custo_serie:unit_cost_at_quantity_USD`, `fiabilidade:maintenance.mmh_per_fh`, `fiabilidade:mission_reliability`, `fiabilidade:mtbcf_s`, `fiabilidade:operational_availability`, `gelo:fiki`, `gelo:max_thickness_m`, `gelo:protection.power_W`, `termica:cold_margin_C`, `termica:cooling.drag_area_m2`, `termica:hot_margin_C`
