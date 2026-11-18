# UAV ISR — sessão de demonstração

Gerado: 2026-11-18T11:30:31+00:00 · acdt 0.1.0 · git 633283811f

Demo scripted session (examples/ai_session/session.py).

## Corridas

| run | ferramenta | estado | criado |
|---|---|---|---|
| `20261118-112905-size-uav_isr_pedido_do_utilizador-3f8d` | size | done | 2026-11-18T11:29:05+00:00 |
| `20261118-112912-size-uav_isr_pedido_do_utilizador-6333` | size | done | 2026-11-18T11:29:12+00:00 |
| `20261118-112922-optimize-uav_isr_pedido_do_utilizador-e475` | optimize | done | 2026-11-18T11:29:22+00:00 |

## size — UAV ISR (pedido do utilizador) (`20261118-112905-size-uav_isr_pedido_do_utilizador-3f8d`)

- Viável: **True**; W0 = 23.38 kg, We/W0 = 0.434, bateria = 1846 Wh
- W/S = 18.05 kg/m², P/W = 5.307; ativas: RC 3.0 m/s @ 0 m, Perda 13.0 m/s
- Asa: S = 1.295 m², b = 4.258 m, AR = 14
- FALHA hq:CAP: CAP = ω²/(n/α) [1/(g s²)] = 8.77 → Nível 2 (N1: 0.085–3.6; MIL-F-8785C Figs. 1–3, Classe I, Cat. B) — UAV: indicativo

Pressupostos fornecidos (fonte):

- `weights.method` = `"components"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `weights.initial_class` = `"uav_small"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `weights.components` = `{"material": "composite", "structural_category": "utility", "landing_gear": "non` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.AR` = `14` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.taper` = `0.6` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.tc_root` = `0.13` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.tc_tip` = `0.11` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.airfoil` = `"NACA 4412"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.clmax_airfoil` = `1.45` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.flap.kind` = `"plain"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.flap.flapped_area_ratio` = `0.5` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.cfe` = `0.0055` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.swet_sref` = `3.5` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.laminar.wing` = `0.3` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.laminar.htail` = `0.3` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.laminar.vtail` = `0.3` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.laminar.fuselage` = `0.1` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.roughness` = `"smooth_molded_composite"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.extra_drag_areas_m2` = `{"gimbal_eo_ir": 0.006, "antennas_pitot": 0.002}` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.fidelity` = `"handbook"` — user — tool argument level=L0
- `propulsion.eta_cruise` = `0.8` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.eta_climb` = `0.75` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.battery_Wh_kg` = `200` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.eta_total` = `0.62` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.dod` = `0.85` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.energy_reserve` = `0.2` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.systems_power_W` = `30` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.fuselage_length_m` = `1.8` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.fuselage_diameter_m` = `0.22` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.c_ht` = `0.5` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.c_vt` = `0.03` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.tail_arm_fraction` = `0.55` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `constraints.ws_initial_psf` = `6` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- 117 valores por omissão do acdt (DEFAULT_ASSUMPTIONS; ver `run.json`).
- Relatório: [report.md](examples/ai_session/output/runs/20261118-112905-size-uav_isr_pedido_do_utilizador-3f8d/size/report.md)
- Relatório: [verification_matrix.md](examples/ai_session/output/runs/20261118-112905-size-uav_isr_pedido_do_utilizador-3f8d/size/verification_matrix.md)

Limitações / avisos:

- [warning] n_lim = 5.00 está acima da linha de perda mesmo a VD (n = 3.22 com CLmax quase-estático): valor CONSERVATIVO mantido (a perda dinâmica numa rajada pode excedê-lo); VC baixo face a VS1 — rever VC/CLmax antes de dimensionar
- [warning] Massa da fuselagem L1 / Raymer Eq. 15.49 = 1.49 (1.7 kg vs 1.2 kg).
- [warning] We/W0 por componentes = 0.434 fora da banda estatística [0.77, 0.89] (±15 %) — rever itens em falta (recuperação, suportes, pintura, cablagem de sinal) ou calibrar com dados próprios.

## size — UAV ISR (pedido do utilizador) (`20261118-112912-size-uav_isr_pedido_do_utilizador-6333`)

- Viável: **True**; W0 = 22.87 kg, We/W0 = 0.4458, bateria = 1735 Wh
- W/S = 17.9 kg/m², P/W = 5.162; ativas: RC 3.0 m/s @ 0 m, Perda 13.0 m/s
- Asa: S = 1.278 m², b = 4.229 m, AR = 14
- FALHA hq:CAP: CAP = ω²/(n/α) [1/(g s²)] = 8.7 → Nível 2 (N1: 0.085–3.6; MIL-F-8785C Figs. 1–3, Classe I, Cat. B) — UAV: indicativo

Pressupostos fornecidos (fonte):

- `weights.method` = `"components"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `weights.initial_class` = `"uav_small"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `weights.components` = `{"material": "composite", "structural_category": "utility", "landing_gear": "non` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.AR` = `14` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.taper` = `0.6` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.tc_root` = `0.13` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.tc_tip` = `0.11` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.airfoil` = `"NACA 4412"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.clmax_airfoil` = `1.45` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.flap.kind` = `"plain"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.flap.flapped_area_ratio` = `0.5` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.cfe` = `0.0055` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.swet_sref` = `3.5` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.laminar.wing` = `0.3` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.laminar.htail` = `0.3` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.laminar.vtail` = `0.3` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.laminar.fuselage` = `0.1` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.roughness` = `"smooth_molded_composite"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.extra_drag_areas_m2` = `{"gimbal_eo_ir": 0.006, "antennas_pitot": 0.002}` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.fidelity` = `"lowfi"` — user — tool argument level=L1
- `propulsion.eta_cruise` = `0.8` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.eta_climb` = `0.75` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.battery_Wh_kg` = `200` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.eta_total` = `0.62` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.dod` = `0.85` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.energy_reserve` = `0.2` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.systems_power_W` = `30` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.fuselage_length_m` = `1.8` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.fuselage_diameter_m` = `0.22` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.c_ht` = `0.5` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.c_vt` = `0.03` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.tail_arm_fraction` = `0.55` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `constraints.ws_initial_psf` = `6` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- 117 valores por omissão do acdt (DEFAULT_ASSUMPTIONS; ver `run.json`).
- Relatório: [report.md](examples/ai_session/output/runs/20261118-112912-size-uav_isr_pedido_do_utilizador-6333/size/report.md)
- Relatório: [verification_matrix.md](examples/ai_session/output/runs/20261118-112912-size-uav_isr_pedido_do_utilizador-6333/size/verification_matrix.md)

Limitações / avisos:

- [warning] n_lim = 5.37 está acima da linha de perda mesmo a VD (n = 3.21 com CLmax quase-estático): valor CONSERVATIVO mantido (a perda dinâmica numa rajada pode excedê-lo); VC baixo face a VS1 — rever VC/CLmax antes de dimensionar
- [warning] Massa da fuselagem L1 / Raymer Eq. 15.49 = 1.47 (1.7 kg vs 1.2 kg).
- [warning] We/W0 por componentes = 0.446 fora da banda estatística [0.77, 0.89] (±15 %) — rever itens em falta (recuperação, suportes, pintura, cablagem de sinal) ou calibrar com dados próprios.

## optimize — UAV ISR (pedido do utilizador) (`20261118-112922-optimize-uav_isr_pedido_do_utilizador-e475`)

- Objetivo W0 (nlbgs); melhoria aceite: True
- W0 [kg]: 23.38 → 22.45
- AR: 14 → 9.8
- W/S [N/m²]: 177 → 177
- b [m]: 4.258 → 3.491
- energia bateria [Wh]: 1846 → 1924
- autonomia (segmentos) [h]: 2.73 → 2.707
- alcance (segmentos) [km]: 212.6 → 211.5
- falhas: hq:CAP → hq:CAP

Pressupostos fornecidos (fonte):

- `weights.method` = `"components"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `weights.initial_class` = `"uav_small"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `weights.components` = `{"material": "composite", "structural_category": "utility", "landing_gear": "non` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.AR` = `14` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.taper` = `0.6` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.tc_root` = `0.13` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.tc_tip` = `0.11` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.airfoil` = `"NACA 4412"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.clmax_airfoil` = `1.45` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.flap.kind` = `"plain"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.flap.flapped_area_ratio` = `0.5` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.cfe` = `0.0055` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.swet_sref` = `3.5` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.laminar.wing` = `0.3` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.laminar.htail` = `0.3` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.laminar.vtail` = `0.3` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.laminar.fuselage` = `0.1` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.roughness` = `"smooth_molded_composite"` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.extra_drag_areas_m2` = `{"gimbal_eo_ir": 0.006, "antennas_pitot": 0.002}` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `aero.fidelity` = `"handbook"` — user — tool argument level=L0
- `propulsion.eta_cruise` = `0.8` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.eta_climb` = `0.75` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.battery_Wh_kg` = `200` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.eta_total` = `0.62` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.dod` = `0.85` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.energy_reserve` = `0.2` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `propulsion.systems_power_W` = `30` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.fuselage_length_m` = `1.8` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.fuselage_diameter_m` = `0.22` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.c_ht` = `0.5` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.c_vt` = `0.03` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `geometry.tail_arm_fraction` = `0.55` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `constraints.ws_initial_psf` = `6` — user — template examples/uav_endurance_payload.yaml (sources in its comments)
- `mdo.consistency_order` = `0` — user — tool argument consistency_order
- 117 valores por omissão do acdt (DEFAULT_ASSUMPTIONS; ver `run.json`).
- Relatório: [mdo_report](examples/ai_session/output/runs/20261118-112922-optimize-uav_isr_pedido_do_utilizador-e475/mdo/mdo_report.md)
- Relatório: [baseline_report](examples/ai_session/output/runs/20261118-112922-optimize-uav_isr_pedido_do_utilizador-e475/mdo/baseline/report.md)
- Relatório: [optimum_report](examples/ai_session/output/runs/20261118-112922-optimize-uav_isr_pedido_do_utilizador-e475/mdo/optimum/report.md)

---
Métodos clássicos citados nos módulos (ver recurso `acdt://methods`). Valores por omissão e pressupostos estão marcados; nenhum valor foi inventado pelo agente — os dados externos têm fonte e data.
