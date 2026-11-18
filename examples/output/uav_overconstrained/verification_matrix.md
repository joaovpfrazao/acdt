# Matriz de verificação

Formato `acdt.verification/1`. Evidência: `result.json` (SHA-256 `11958c7dbd4a`). Proveniência: impressão digital `d9092718ad90` (registo escrito no fim da corrida).

Estados: **passa**, **falha**, **no_limite** (dentro da tolerância declarada), **nao_avaliado** (sem avaliador ou etapa não correu), **desconhecido** (correu sem valor). Não avaliado ≠ passa.

| Estado | N.º |
|---|---|
| passa | 4 |
| falha | 2 |
| no_limite | 3 |
| nao_avaliado | 1 |
| desconhecido | 1 |

| ID | Estado | Requisito | Origem | Limiar | Valor | Margem | Avaliador | Método | Fid. (exig./aval.) | Nota |
|---|---|---|---|---|---|---|---|---|---|---|
| REQ-propulsion_type | nao_avaliado | propulsion_type target electric | missao | electric | — | — | — | analise | N0/— | sem avaliador declarado |
| REQ-regulatory_category | desconhecido | regulatory_category target easa_specific | missao | easa_specific | — | — | check:regulatory_category | analise | N0/N1 | easa_specific: no numeric limit |
| REQ-payload_mass | passa | payload_mass target 4.0 kg | missao | = 4.0 kg | 4 kg | +0.000 % | entrada:payload_mass | inspecao | N0/N0 | entrada do dimensionamento (cumprida por construção) |
| REQ-endurance | no_limite | endurance min 3.5 h | missao | ≥ 3.5 h | 3.5 h | +0.000 % | perf:endurance | analise | N1/N1 | tempo em espera (segmentos); dentro da banda ±0.001 (resolução do avaliador 0.001 (performance_analysis: comparação a 0,1 %)) |
| REQ-cruise_speed | passa | cruise_speed target 22 m/s | missao | = 22 m/s | 22 m/s | +0.000 % | entrada:cruise_speed | inspecao | N0/N0 | entrada do dimensionamento (cumprida por construção) |
| REQ-cruise_altitude | passa | cruise_altitude target 600 m | missao | = 600 m | 600 m | +0.000 % | entrada:cruise_altitude | inspecao | N0/N0 | entrada do dimensionamento (cumprida por construção) |
| REQ-stall_speed | no_limite | stall_speed max 13 m/s | missao | ≤ 13 m/s | 13 m/s | +0.000 % | sizing:stall_speed | analise | N0/N0 | V_s = √(2 (W/S) f_ater / (ρ C_Lmax,ater)) = 13.000 m/s (Raymer Eq. 5.6; W/S 177.0 N/m², f_ater 1, C_Lmax,ater 1.710, h 0 m); dentro da banda ±1e-05 (resolução d |
| REQ-climb_rate | no_limite | climb_rate min 3.0 m/s | missao | ≥ 3.0 m/s | 3 m/s | +0.000 % | perf:climb_rate | analise | N1/N1 | ROC máx. ao nível do mar; dentro da banda ±0.001 (resolução do avaliador 0.001 (performance_analysis: comparação a 0,1 %)) |
| REQ-service_ceiling | passa | service_ceiling min 3000 m | missao | ≥ 3000 m | 9000 m | +200.0 % | perf:service_ceiling | analise | N1/N1 | teto de serviço (Anderson) > 9000 m (não atingido) |
| REQ-wing_span | falha | wing_span max 4.2 m | missao | ≤ 4.2 m | 5.05 m | -20.2 % | resultado:geometry.wing.span_m | analise | N0/N0 |  |
| REQ-mtow | falha | mtow max 25 kg | missao | ≤ 25 kg | 32.89 kg | -31.5 % | resultado:weights.W0_kg | analise | N0/N0 |  |

## Cobertura

* Requisitos sem avaliador (nem filhos): REQ-propulsion_type
* Avaliadores não registados: nenhum
* Evidência sem requisito (16): `check:aeroel:aeer45`, `check:aeroel:divergence`, `check:aeroel:flutter`, `check:aeroel:reversal`, `check:hq:CAP`, `check:hq:dutch_roll`, `check:hq:phugoid`, `check:hq:roll`, `check:hq:scissor`, `check:hq:short_period`, `check:hq:spiral`, `check:mtow`, `check:static_margin`, `check:trim`, `check:wb:envelope`, `check:wing_span`
