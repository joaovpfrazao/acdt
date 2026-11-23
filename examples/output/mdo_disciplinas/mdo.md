# MDO de sistema (`acdt mdo`)

Modelo: pipeline aircraft L0/L1 (`uav_endurance_payload.yaml`), fidelidade handbook, sem aeroelasticity; um pipeline por amostra.

Estratégia: **nsga2**; 10 avaliações (10 corridas do modelo, 0 falhadas, 4 viáveis). Política das restrições de requisitos: `limiar`.

## Variáveis de projeto

| caminho | tipo | onde | limites/valores | origem |
|---|---|---|---|---|
| `assumptions.aero.AR` | continuous | inner | [7, 13], x0 9 | PRESSUPOSTO: banda de AR do estudo |
| `requirements.endurance` | discrete | inner | [2.0, 2.5, 3.0] | PRESSUPOSTO: troca de autonomia em torno do requisito de 2,5 h |

Sobreposições fixas do estudo: {'assumptions.aero.fidelity': 'handbook', 'assumptions.stability.use_avl': False, 'assumptions.thermal': {'coupling': 'iterar', 'ground_time_s': 300, 'electric': {'eta_esc': 0.97, 'eta_motor': 0.9}, 'bays': [{'id': 'fuselagem', 'skin_area_m2': 1.0, 'flow_length_m': 1.6, 'height_m': 0.2, 'eps_ext': 0.85, 'alpha_solar': 0.3, 'eps_int': [0.1, 0.9], 'sources': ['avionica', 'bateria', 'esc'], 'capacity_J_K': 9000.0, 'components': [{'id': 'bateria_pack', 'source': 'bateria', 'conductance_W_K': 10.0, 'T_max_C': 60, 'T_min_C': -20, 'limit_source': 'teste (limite declarado)'}], 'ram_air': {'size_for': 'cruzeiro_quente', 'ram_recovery': 0.8, 'duct_loss_q': 0.5, 'duct': {'length_m': 0.4, 'areal_density_kg_m2': 1.0}}}]}, 'assumptions.icing': {'coupling': 'iterar', 'surfaces': [{'id': 'asa', 'chord_m': 0.3, 't_c': 0.12, 'lifting': True, 'protection': 'deice_electrothermal', 'protected_area_m2': 0.2, 'duty_cycle': 0.1, 'power_density_W_m2': 10000, 'mass_kg': 0.3}]}, 'assumptions.reliability': {'components': [{'id': 'motor', 'lambda_per_h': 0.0001, 'source': 'teste', 'mttr_h': 2.0, 'mmh_per_action': 3.0, 'replacement_cost': 500.0}, {'id': 'servo', 'lambda_per_h': 0.0005, 'source': 'teste', 'mttr_h': 0.5, 'mmh_per_action': 1.0, 'replacement_cost': 200.0}], 'rbd': {'type': 'series', 'blocks': ['motor', {'type': 'k_of_n', 'k': 3, 'n': 4, 'block': 'servo'}]}, 'preventive': [{'id': 'inspecao', 'interval_fh': 50.0, 'duration_h': 1.0, 'mmh': 2.0}], 'logistics': {'mean_logistic_delay_h': 4.0, 'mean_admin_delay_h': 1.0}, 'fleet': {'mode': 'sorties', 'sorties_per_day': 3, 'turnaround_h': 1.0, 'operating_hours_per_day': 16}}, 'assumptions.series_cost': {'quantity': 50, 'price': 60000}, 'assumptions.life_cycle': {'service_life_years': 10, 'production_rate_per_year': 20, 'rdte_years': 2, 'fh_per_aircraft_per_year': {'lo': 300, 'hi': 500}, 'cost_per_fh_USD': {'lo': 40, 'hi': 90}, 'disposal_per_aircraft_USD': 0.0, 'discount_rate': 0.05, 'environment': {'grid_intensity_kgCO2e_per_kWh': {'lo': 0.1, 'hi': 0.4, 'source': 'teste'}, 'charge_efficiency': 0.9, 'battery_footprint': 'ivl_c444_2019', 'battery_cycle_life': 400, 'flights_per_fh': 0.25}}}.

## Objetivos

* min `W0_kg`
* min `lcc_pv_hi_USD`

## Restrições

| nome | tipo | nota |
|---|---|---|
| `req:REQ-payload_mass` | requisito | target = 4.0 kg (tol ±0); política limiar |
| `req:REQ-endurance` | requisito | min ≥ 2.5 h (tol ±0); política limiar |
| `req:REQ-cruise_speed` | requisito | target = 22 m/s (tol ±0); política limiar |
| `req:REQ-cruise_altitude` | requisito | target = 600 m (tol ±0); política limiar |
| `req:REQ-stall_speed` | requisito | max ≤ 13 m/s (tol ±0); política limiar |
| `req:REQ-climb_rate` | requisito | min ≥ 3.0 m/s (tol ±0); política limiar |
| `req:REQ-service_ceiling` | requisito | min ≥ 3000 m (tol ±0); política limiar |
| `req:REQ-wing_span` | requisito | max ≤ 4.2 m (tol ±0); política limiar |
| `met:mission_reliability_lo` | metrica | PRESSUPOSTO do estudo (requisito RL-01 de tests/test_reliability.py) |
| `met:availability_op_lo` | metrica | PRESSUPOSTO do estudo (requisito RL-02 de tests/test_reliability.py) |
| `met:ice_power_hi_W` | metrica | PRESSUPOSTO do estudo (requisito IC-03 de tests/test_icing.py) |

Filtros (estado reportado por projeto, não restrição):

* `REQ-propulsion_type`: requisito não numérico: filtro (estado reportado por projeto), não restrição
* `REQ-regulatory_category`: requisito não numérico: filtro (estado reportado por projeto), não restrição

## Resultado

Joelho da frente: avaliação **0** (Das 1999: maior distância à reta entre extremos (frente normalizada)).
* melhor viável em `W0_kg`: avaliação 6
* melhor viável em `lcc_pv_hi_USD`: avaliação 7

| id | x | objetivos | viável | estado dos requisitos |
|---|---|---|---|---|
| 6 | assumptions.aero.AR = 9.4039, requirements.endurance = 2 | W0_kg = 27.912, lcc_pv_hi_USD = 1.5892e+07 | sim | desconhecido 1, falha 1, nao_avaliado 1, no_limite 3, passa 5 |
| 0 | assumptions.aero.AR = 9, requirements.endurance = 2 | W0_kg = 27.98, lcc_pv_hi_USD = 1.5885e+07 | sim | desconhecido 1, falha 1, nao_avaliado 1, no_limite 3, passa 5 |
| 7 | assumptions.aero.AR = 7.9041, requirements.endurance = 2 | W0_kg = 28.173, lcc_pv_hi_USD = 1.5866e+07 | sim | desconhecido 1, falha 1, nao_avaliado 1, no_limite 3, passa 5 |

Frente de Pareto: 3 projetos não dominados (todas as avaliações viáveis da decisão final; Deb et al. 2002).

Matriz de verificação do projeto escolhido: `verification_matrix.md` ({'passa': 5, 'falha': 1, 'no_limite': 3, 'nao_avaliado': 1, 'desconhecido': 1}).

## PRESSUPOSTOS

* viabilidade com margem relativa ≥ −1e-6 (ruído numérico dos fechos iterativos; options.feas_tol)
* fidelidade handbook em todas as avaliações (mais barata; muda o modelo)

Todas as avaliações (com o estado de cada requisito) em `evaluations.csv`.
