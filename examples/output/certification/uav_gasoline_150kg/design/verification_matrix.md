# Matriz de verificação

Formato `acdt.verification/1`. Evidência: `result.json` (SHA-256 `2584442546b3`). Proveniência: impressão digital `40bd84ecde22` (registo escrito no fim da corrida).

Estados: **passa**, **falha**, **no_limite** (dentro da tolerância declarada), **nao_avaliado** (sem avaliador ou etapa não correu), **desconhecido** (correu sem valor). Não avaliado ≠ passa.

| Estado | N.º |
|---|---|
| passa | 7 |
| falha | 0 |
| no_limite | 1 |
| nao_avaliado | 1 |
| desconhecido | 1 |

| ID | Estado | Requisito | Origem | Limiar | Valor | Margem | Avaliador | Método | Fid. (exig./aval.) | Nota |
|---|---|---|---|---|---|---|---|---|---|---|
| REQ-propulsion_type | nao_avaliado | propulsion_type target piston_prop | missao | piston_prop | — | — | — | analise | N0/— | sem avaliador declarado |
| REQ-regulatory_category | desconhecido | regulatory_category target easa_specific | missao | easa_specific | — | — | check:regulatory_category | analise | N0/N1 | easa_specific: no numeric limit |
| REQ-payload_mass | passa | payload_mass target 30 kg | missao | = 30 kg | 30 kg | +0.000 % | entrada:payload_mass | inspecao | N0/N0 | entrada do dimensionamento (cumprida por construção) |
| REQ-endurance | passa | endurance min 10 h | missao | ≥ 10 h | 10.45 h | +4.5 % | perf:endurance | analise | N1/N1 | tempo em espera (segmentos) |
| REQ-cruise_speed | passa | cruise_speed target 45 m/s | missao | = 45 m/s | 45 m/s | +0.000 % | entrada:cruise_speed | inspecao | N0/N0 | entrada do dimensionamento (cumprida por construção) |
| REQ-cruise_altitude | passa | cruise_altitude target 3000 m | missao | = 3000 m | 3000 m | +0.000 % | entrada:cruise_altitude | inspecao | N0/N0 | entrada do dimensionamento (cumprida por construção) |
| REQ-stall_speed | no_limite | stall_speed max 26 m/s | missao | ≤ 26 m/s | 26 m/s | -0.000 % | sizing:stall_speed | analise | N0/N0 | V_s = √(2 (W/S) f_ater / (ρ C_Lmax,ater)) = 26.000 m/s (Raymer Eq. 5.6; W/S 742.1 N/m², f_ater 1, C_Lmax,ater 1.792, h 0 m); dentro da banda ±0.0002 (resolução  |
| REQ-climb_rate | passa | climb_rate min 3.0 m/s | missao | ≥ 3.0 m/s | 4.709 m/s | +57.0 % | perf:climb_rate | analise | N1/N1 | ROC máx. ao nível do mar |
| REQ-service_ceiling | passa | service_ceiling min 5000 m | missao | ≥ 5000 m | 5419 m | +8.4 % | perf:service_ceiling | analise | N1/N1 | teto de serviço (Anderson) |
| REQ-takeoff_ground_roll | passa | takeoff_ground_roll max 300 m | missao | ≤ 300 m | 296.9 m | +1.0 % | perf:takeoff_ground_roll | analise | N1/N1 | corrida de descolagem (Raymer 17.8) |

## Cobertura

* Requisitos sem avaliador (nem filhos): REQ-propulsion_type
* Avaliadores não registados: nenhum
* Evidência sem requisito (17): `check:aeroel:aeer45`, `check:aeroel:divergence`, `check:aeroel:flutter`, `check:aeroel:reversal`, `check:gear:position`, `check:gear:stroke`, `check:gear:tipback`, `check:hq:CAP`, `check:hq:dutch_roll`, `check:hq:phugoid`, `check:hq:roll`, `check:hq:scissor`, `check:hq:short_period`, `check:hq:spiral`, `check:static_margin`, `check:trim`, `check:wb:envelope`
