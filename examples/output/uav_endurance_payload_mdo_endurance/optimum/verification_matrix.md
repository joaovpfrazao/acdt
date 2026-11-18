# Matriz de verificação

Formato `acdt.verification/1`. Evidência: `result.json` (SHA-256 `3275c640c089`). Proveniência: impressão digital `e07bbc235977` (registo escrito no fim da corrida).

Estados: **passa**, **falha**, **no_limite** (dentro da tolerância declarada), **nao_avaliado** (sem avaliador ou etapa não correu), **desconhecido** (correu sem valor). Não avaliado ≠ passa.

| Estado | N.º |
|---|---|
| passa | 7 |
| falha | 0 |
| no_limite | 2 |
| nao_avaliado | 1 |
| desconhecido | 1 |

| ID | Estado | Requisito | Origem | Limiar | Valor | Margem | Avaliador | Método | Fid. (exig./aval.) | Nota |
|---|---|---|---|---|---|---|---|---|---|---|
| REQ-propulsion_type | nao_avaliado | propulsion_type target electric | missao | electric | — | — | — | analise | N0/— | sem avaliador declarado |
| REQ-regulatory_category | desconhecido | regulatory_category target easa_specific | missao | easa_specific | — | — | check:regulatory_category | analise | N0/N1 | easa_specific: no numeric limit |
| REQ-payload_mass | passa | payload_mass target 4.0 kg | missao | = 4.0 kg | 4 kg | +0.000 % | entrada:payload_mass | inspecao | N0/N0 | entrada do dimensionamento (cumprida por construção) |
| REQ-endurance | no_limite | endurance min 2.5 h | missao | ≥ 2.5 h | 2.686 h | -0.052 % | perf:endurance | analise | N1/N1 | tempo em espera (segmentos); dentro da banda ±0.001 (resolução do avaliador 0.001 (performance_analysis: comparação a 0,1 %)) |
| REQ-cruise_speed | passa | cruise_speed target 22 m/s | missao | = 22 m/s | 22 m/s | +0.000 % | entrada:cruise_speed | inspecao | N0/N0 | entrada do dimensionamento (cumprida por construção) |
| REQ-cruise_altitude | passa | cruise_altitude target 600 m | missao | = 600 m | 600 m | +0.000 % | entrada:cruise_altitude | inspecao | N0/N0 | entrada do dimensionamento (cumprida por construção) |
| REQ-stall_speed | passa | stall_speed max 13 m/s | missao | ≤ 13 m/s | 12.93 m/s | +0.5 % | sizing:stall_speed | analise | N0/N0 | V_s = √(2 (W/S) f_ater / (ρ C_Lmax,ater)) = 12.932 m/s (Raymer Eq. 5.6; W/S 175.6 N/m², f_ater 1, C_Lmax,ater 1.715, h 0 m) |
| REQ-climb_rate | no_limite | climb_rate min 3.0 m/s | missao | ≥ 3.0 m/s | 3 m/s | +0.001 % | perf:climb_rate | analise | N1/N1 | ROC máx. ao nível do mar; dentro da banda ±0.001 (resolução do avaliador 0.001 (performance_analysis: comparação a 0,1 %)) |
| REQ-service_ceiling | passa | service_ceiling min 3000 m | missao | ≥ 3000 m | 9000 m | +200.0 % | perf:service_ceiling | analise | N1/N1 | teto de serviço (Anderson) > 9000 m (não atingido) |
| REQ-wing_span | passa | wing_span max 4.2 m | missao | ≤ 4.2 m | 4.192 m | +0.2 % | resultado:geometry.wing.span_m | analise | N0/N0 |  |
| REQ-mtow | passa | mtow max 25 kg | missao | ≤ 25 kg | 24.25 kg | +3.0 % | resultado:weights.W0_kg | analise | N0/N0 |  |

## Cobertura

* Requisitos sem avaliador (nem filhos): REQ-propulsion_type
* Avaliadores não registados: nenhum
* Evidência sem requisito (16): `check:aeroel:aeer45`, `check:aeroel:divergence`, `check:aeroel:flutter`, `check:aeroel:reversal`, `check:hq:CAP`, `check:hq:dutch_roll`, `check:hq:phugoid`, `check:hq:roll`, `check:hq:scissor`, `check:hq:short_period`, `check:hq:spiral`, `check:mtow`, `check:static_margin`, `check:trim`, `check:wb:envelope`, `check:wing_span`
