# acdt — sessão MCP de demonstração (transcrição)

Gerado por `examples/ai_session/session.py`; números tal como devolvidos pelas ferramentas.

| # | ferramenta | s | nota |
|---|---|---|---|
| 1 | `requirements_schema` | 0.0 | learn requirement keys, units and senses |
| 2 | `validate_requirements` | 0.3 | validate + normalise the user's request |
| 3 | `size` | 6.9 | conceptual sizing, handbook (L0) |
| 4 | `size` | 10.3 | low-fidelity sizing, XFOIL/AVL in the loop (L1) |
| 5 | `optimize` | 69.2 | MDO, trust region (demo settings) |
| 6 | `compare_runs` | 0.0 | L0 vs L1 (the MDO result carries its own baseline vs optimum) |
| 7 | `hifi_estimate` | 0.0 | compute plan for verification — cfd2d is heavy and needs the user's approval |
| 8 | `generate_report` | 0.0 | design dossier |

## 1. `requirements_schema` — learn requirement keys, units and senses

argumentos:
```json
{}
```
resultado (excerto):
```json
{
 "(omitted)": "schema",
 "n_types": 23
}
```

## 2. `validate_requirements` — validate + normalise the user's request

argumentos:
```json
{"spec": {"name": "UAV ISR (pedido do utilizador)", "aircraft_class": "uav_small", "requirements": {"propulsion_type": "electric", "payload_mass": "4 kg", "endurance": {"min": "2.5 h"}, "mtow": {"max": "25 kg"}, "wing_span": {"max": "4.5 m"}, "cruise_speed": {"target": "22 m/s"}, "cruise_altitude": {"target": "600 m"}, "stall_speed": {"max": "13 m/s"}, "climb_rate": {"min": "3 m/s"}, "service_ceiling": {"min": "3000 m"}, "regulatory_category": "easa_specific"}}}
```
resultado (excerto):
```json
{
 "ok": true,
 "requirements": [
  {
   "key": "propulsion_type",
   "sense": "target",
   "value_si": "electric",
   "si_unit": null,
   "given": "electric",
   "unit": null,
   "qualifiers_si": {},
   "implemented": true
  },
  {
   "key": "payload_mass",
   "sense": "target",
   "value_si": 4.0,
   "si_unit": "kg",
   "given": 4.0,
   "unit": "kg",
   "qualifiers_si": {},
   "implemented": true
  },
  {
   "key": "endurance",
   "sense": "min",
   "value_si": 9000.0,
   "si_unit": "s",
   "given": 2.5,
   "unit": "h",
   "qualifiers_si": {},
   "implemented": true
  },
  {
   "key": "mtow",
   "sense": "max",
   "value_si": 25.0,
   "si_unit": "kg",
   "given": 25.0,
   "unit": "kg",
   "qualifiers_si": {},
   "implemented": true
  },
  {
   "key": "wing_span",
   "sense": "max",
   "value_si": 4.5,
   "si_unit": "m",
   "given": 4.5,
   "unit": "m",
   "qualifiers_si": {},
   "implemented": true
  },
  {
   "key": "cruise_speed",
   "sense": "target",
   "value_si": 22.0,
   "si_unit": "m/s",
   "given": 22.0,
   "unit": "m/s",
   "qualifiers_si": {},
   "implemented": true
  },
  {
   "key": "cruise_altitude",
   "sense": "target",
   "value_si": 600.0,
   "si_unit": "m",
   "given": 600.0,
   "unit": "m",
   "qualifiers_si": {},
   "implemented": true
  },
  {
   "key": "stall_speed",
   "sense": "max",
   "value_si": 13.0,
   "si_unit": "m/s",
   "given": 13.0,
   "unit": "m/s",
   "qualifiers_si": {},
   "implemented": true
  },
  {
   "key": "climb_rate",
   "sense": "min",
   "value_si": 3.0,
   "si_unit": "m/s",
   "given": 3.0,
   "unit": "m/s",
   "qualifiers_si": {},
   "implemented": true
  },
  {
   "key": "service_ceiling",
   "sense": "min",
   "value_si": 3000.0,
   "si_unit": "m",
   "given": 3000.0,
   "unit": "m",
   "qualifiers_si": {},
   "implemented": true
  },
  {
   "key": "regulatory_category",
   "sense": "target",
   "value_si": "easa_specific",
   "si_unit": null,
   "given": "easa_specific",
   "unit": null,
   "qualifiers_si": {},
   "implemented": true
  }
 ],
 "issues": [],
 "hints": [],
 "normalised_spec": {
  "name": "UAV ISR (pedido do utilizador)",
  "aircraft_class": "uav_small",
  "requirements": {
   "propulsion_type": "electric",
   "payload_mass": {
    "target": 4.0,
    "unit": "kg"
   },
   "endurance": {
    "min": 2.5,
    "unit": "h"
   },
   "mtow": {
    "max": 25.0,
    "unit": "kg"
   },
   "wing_span": {
    "max": 4.5,
    "unit": "m"
   },
   "cruise_speed": {
    "target": 22.0,
    "unit": "m/s"
   },
   "cruise_altitude": {
    "target": 600.0,
    "unit": "m"
   },
   "stall_speed": {
    "max": 13.0,
    "unit": "m/s"
   },
   "climb_rate": {
    "min": 3.0,
    "unit": "m/s"
   },
   "service_ceiling": {
    "min": 3000.0,
    "unit": "m"
   },
   "regulatory_category": "easa_specific"
  }
 },
 "assumptions": {
  "n_total": 150,
  "user": [],
  "n_defaults": 150,
  "note": "defaults are the acdt DEFAULT_ASSUMPTIONS (cited in mission.py and the modules); set and cite your own in assumptions/assumption_sources"
 },
 "run_id": "20261118-112904-requirements-uav_isr_pedido_do_utilizador-7bfa",
 "spec_path": "examples/ai_session/output/runs/20261118-112904-requirements-uav_isr_pedido_do_utilizador-7bfa/uav_isr_pedido_do_utilizador.yaml"
}
```

## 3. `size` — conceptual sizing, handbook (L0)

argumentos:
```json
{"spec": {"name": "UAV ISR (pedido do utilizador)", "description": "template: examples/uav_endurance_payload.yaml (assumptions, systems); requirements from the user", "aircraft_class": "uav_small", "requirements": {"propulsion_type": "electric", "payload_mass": {"target": 4.0, "unit": "kg"}, "endurance": {"min": 2.5, "unit": "h"}, "mtow": {"max": 25.0, "unit": "kg"}, "wing_span": {"max": 4.5, "unit": "m"}, "cruise_speed": {"target": 22.0, "unit": "m/s"}, "cruise_altitude": {"target": 600.0, "unit": "m"}, "stall_speed": {"max": 13.0, "unit": "m/s"}, "climb_rate": {"min": 3.0, "unit": "m/s"}, "service_ceiling": {"min": 3000.0, "unit": "m"}, "regulatory_category": "easa_specific"}, "assumptions": {"weights": {"method": "components", "initial_class": "uav_small", "components": {"material": "composite", "structural_category": "utility", "landing_gear": "none", "min_areal_density_kg_m2": 0.9, "propeller_mass_kg": 0.08, "items": [{"name": "paraquedas de recuperação + ejetor", "mass_kg": 1.0}, {"name": "suporte/amortecimento do gimbal", "mass_kg": 0.3}, {"name": "datalink C2 + antenas", "mass_kg": 0.25, "group": "equipment"}, {"name": "GNSS + bússola (x2)", "mass_kg": 0.1, "group": "equipment"}, {"name": "pitot/ADS-B", "mass_kg": 0.1, "group": "equipment"}, {"name": "cablagem de sinal + conectores", "mass_kg": 0.3, "group": "equipment"}, {"name": "ferragens/fixações/pintura", "mass_kg": 0.4}], "growth_allowance": 0.1}}, "aero": {"fidelity": "lowfi", "AR": 14, "taper": 0.6, "tc_root":
```
resultado (excerto):
```json
{
 "run_id": "20261118-112905-size-uav_isr_pedido_do_utilizador-3f8d",
 "status": "done",
 "level": "L0",
 "summary": {
  "name": "UAV ISR (pedido do utilizador)",
  "feasible": true,
  "weights": {
   "W0_kg": 23.377596043803422,
   "We_kg": 10.14677965276509,
   "Wfuel_or_battery_kg": 9.230816390148055,
   "payload_kg": 4.0,
   "crew_kg": 0.0,
   "We_W0": 0.4340386254323461,
   "Wf_W0": 0.39485738280582616,
   "battery_energy_Wh": 1846.1632780296109
  },
  "design_point": {
   "W_S_N_m2": 177.00637761886898,
   "W_S_kg_m2": 18.04962730584542,
   "metric": "P/W",
   "value": 5.306531287122047,
   "active_constraints": [
    "RC 3.0 m/s @ 0 m",
    "Perda 13.0 m/s"
   ],
   "P_SL_W": 1216.5536180096863,
   "T_SL_N": null
  },
  "geometry": {
   "wing": {
    "S_m2": 1.2951844183637258,
    "AR": 14,
    "span_m": 4.2582369423380095,
    "taper": 0.6,
    "c_root_m": 0.38019972699446514,
    "c_tip_m": 0.22811983619667908,
    "MAC_m": 0.31049644371214646,
    "y_MAC_m": 0.9758459659524605,
    "sweep_c4_deg": 0.0,
    "sweep_LE_deg": 1.0230301886678357,
    "t/c": 0.12
   },
   "fuselage": {
    "length_m": 1.8,
    "diameter_m": 0.22
   }
  },
  "aero": {
   "CD0": 0.02135276992119555,
   "K": 0.03455106489906122,
   "LD_max": 18.408236081469063,
   "CL_alpha_per_rad": 5.118756874776653,
   "CLmax_clean": 1.305,
   "CLmax_takeoff": 1.368,
   "CLmax_landing": 1.71,
   "cruise_speed_m_s": 22.0,
   "cruise_altitude_m": 600.0,
   "elastic_correction": {
    "applied": false,
    "CLa_rigid_per_rad": 5.1786989367070975,
    "CLa_flex_per_rad": 5.195786173290641,
    "CDi_rigid": 0.009547405568448873,
    "CDi_flex": 0.009554177421679855,
    "K_ratio": 1.000709287269974,
    "xac_w_mac": 0.25,
    "tip_twist_deg": 0.04415837800315959,
    "tip_deflection_m": 0.01774602815608982,
    "stations": [
     {
      "y_m": 0.0,
      "twist_deg": 0.0,
      "deflection_m": 0.0
     },
     {
      "y_m": 0.2661398088961256,
      "twist_deg": 0.004618634149807486,
      "deflection_m": 0.00012828121463237432
     },
     {
      "y_m": 0.5322796177922512,
      "twist_deg": 0.012867884530361326,
      "deflection_m": 0.0009911815166555734
     },
     {
      "y_m": 0.7984194266883768,
      "twist_deg": 0.020774031736874282,
      "deflection_m": 0.00261135529389573
     },
     {
      "y_m": 1.0645592355845024,
      "twist_deg": 0.028109389645340585,
      "deflection_m": 0.004894391453654171
     },
     {
      "y_m": 1.330699044480628,
      "twist_deg": 0.03457186715130245,
      "deflection_m": 0.007712827293271985
     },
     {
      "y_m": 1.5968388533767537,
      "twist_deg": 0.03975258778705155,
      "deflection_m": 0.010906371403320299
     },
     {
      "y_m": 1.8629786622728792,
      "twist_deg": 0.04311371370687019,
      "deflection_m": 0.014296813792212511
     },
     {
      "y_m": 2.1291184711690048,
      "twist_deg": 0.04415837800315959,
      "deflection_m": 0.01774602815608982
     }
    ],
    "notes": [
     "Linha sustentadora de Glauert (Anderson §5.3) com a₀ = 0,95·2π (Raymer §12.4.1) e α_L0 = 0. A torção elástica entra no ângulo local. Sem NeuralFoil neste caminho."
    ]
   }
  },
  "failed_checks": [
   {
    "key": "hq:CAP",
    "ok": false,
    "message": "CAP = ω²/(n/α) [1/(g s²)] = 8.77 → Nível 2 (N1: 0.085–3.6; MIL-F-8785C Figs. 1–3, Classe I, Cat. B) — UAV: indicativo"
   }
  ],
  "checks": [
   {
    "key": "mtow",
    "ok": true,
    "message": "W0 = 23.4 kg vs max 25.0 kg"
   },
   {
    "key": "wing_span",
    "ok": true,
    "message": "b = 4.26 m vs max 4.50 m"
   },
   {
    "key": "regulatory_category",
    "ok": null,
    "message": "easa_specific: no numeric limit"
   },
   {
    "key": "static_margin",
    "ok": true,
    "message": "SM no CG traseiro 10.0 % (alvo 10 %; dianteiro 10.0 %) — posicionamento da asa por bisseção"
   },
   {
    "key": "trim",
    "ok": true,
    "message": "CLmax limpo (CG dianteiro): δe -8.9°; cruzeiro (CG dianteiro): δe -5.5°"
   },
   {
    "key": "h
```

## 4. `size` — low-fidelity sizing, XFOIL/AVL in the loop (L1)

argumentos:
```json
{"run_id": "20261118-112905-size-uav_isr_pedido_do_utilizador-3f8d", "level": "L1", "wait_s": 600}
```
resultado (excerto):
```json
{
 "run_id": "20261118-112912-size-uav_isr_pedido_do_utilizador-6333",
 "status": "done",
 "level": "L1",
 "summary": {
  "name": "UAV ISR (pedido do utilizador)",
  "feasible": true,
  "weights": {
   "W0_kg": 22.86745659372587,
   "We_kg": 10.193711023120002,
   "Wfuel_or_battery_kg": 8.673745569383014,
   "payload_kg": 4.0,
   "crew_kg": 0.0,
   "We_W0": 0.4457737125831845,
   "Wf_W0": 0.37930521629426966,
   "battery_energy_Wh": 1734.749113876603
  },
  "design_point": {
   "W_S_N_m2": 175.5251424227394,
   "W_S_kg_m2": 17.898583351372732,
   "metric": "P/W",
   "value": 5.161693325331201,
   "active_constraints": [
    "RC 3.0 m/s @ 0 m",
    "Perda 13.0 m/s"
   ],
   "P_SL_W": 1157.525952465077,
   "T_SL_N": null
  },
  "geometry": {
   "wing": {
    "S_m2": 1.2776126548569582,
    "AR": 14,
    "span_m": 4.22925255429342,
    "taper": 0.6,
    "c_root_m": 0.3776118352047696,
    "c_tip_m": 0.22656710112286174,
    "MAC_m": 0.3083829987505618,
    "y_MAC_m": 0.9692037103589087,
    "sweep_c4_deg": 0.0,
    "sweep_LE_deg": 1.0230301886678357,
    "t/c": 0.12
   },
   "fuselage": {
    "length_m": 1.8,
    "diameter_m": 0.22
   }
  },
  "aero": {
   "CD0": 0.023396962271904326,
   "K": 0.025236782354797732,
   "LD_max": 20.576583920925692,
   "CL_alpha_per_rad": 5.118756874776653,
   "CLmax_clean": 1.29069562256911,
   "CLmax_takeoff": 1.356556498055288,
   "CLmax_landing": 1.69569562256911,
   "cruise_speed_m_s": 22.0,
   "cruise_altitude_m": 600.0,
   "elastic_correction": {
    "applied": false,
    "CLa_rigid_per_rad": 5.178698936707099,
    "CLa_flex_per_rad": 5.1956729520219245,
    "CDi_rigid": 0.009388283828470815,
    "CDi_flex": 0.009382634726335985,
    "K_ratio": 0.9993982817053636,
    "xac_w_mac": 0.25,
    "tip_twist_deg": -0.03588851024189288,
    "tip_deflection_m": 0.0171066423797312,
    "stations": [
     {
      "y_m": 0.0,
      "twist_deg": 0.0,
      "deflection_m": 0.0
     },
     {
      "y_m": 0.26432828464333874,
      "twist_deg": -0.0033087119103712825,
      "deflection_m": 0.0001232445826994152
     },
     {
      "y_m": 0.5286565692866775,
      "twist_deg": -0.009260060651218111,
      "deflection_m": 0.0009527604005371835
     },
     {
      "y_m": 0.7929848539300163,
      "twist_deg": -0.015082102379363077,
      "deflection_m": 0.0025115118372591515
     },
     {
      "y_m": 1.057313138573355,
      "twist_deg": -0.020686379796588206,
      "deflection_m": 0.004709874658569637
     },
     {
      "y_m": 1.3216414232166938,
      "twist_deg": -0.025925667882382607,
      "deflection_m": 0.007426005201240757
     },
     {
      "y_m": 1.5859697078600326,
      "twist_deg": -0.03056177081379172,
      "deflection_m": 0.010506095772930012
     },
     {
      "y_m": 1.8502979925033713,
      "twist_deg": -0.03418627005230783,
      "deflection_m": 0.013777781140142147
     },
     {
      "y_m": 2.11462627714671,
      "twist_deg": -0.03588851024189288,
      "deflection_m": 0.0171066423797312
     }
    ],
    "notes": [
     "Linha sustentadora de Glauert (Anderson §5.3) com a₀ = 0,95·2π (Raymer §12.4.1) e α_L0 = 0. A torção elástica entra no ângulo local. Sem NeuralFoil neste caminho."
    ]
   }
  },
  "failed_checks": [
   {
    "key": "hq:CAP",
    "ok": false,
    "message": "CAP = ω²/(n/α) [1/(g s²)] = 8.7 → Nível 2 (N1: 0.085–3.6; MIL-F-8785C Figs. 1–3, Classe I, Cat. B) — UAV: indicativo"
   }
  ],
  "checks": [
   {
    "key": "mtow",
    "ok": true,
    "message": "W0 = 22.9 kg vs max 25.0 kg"
   },
   {
    "key": "wing_span",
    "ok": true,
    "message": "b = 4.23 m vs max 4.50 m"
   },
   {
    "key": "regulatory_category",
    "ok": null,
    "message": "easa_specific: no numeric limit"
   },
   {
    "key": "static_margin",
    "ok": true,
    "message": "SM no CG traseiro 10.0 % (alvo 10 %; dianteiro 10.0 %) — posicionamento da asa por bisseção"
   },
   {
    "key": "trim",
    "ok": true,
    "message": "CLmax limpo (CG dianteiro): δe -10.9°; cruzeiro (CG diant
```

## 5. `optimize` — MDO, trust region (demo settings)

argumentos:
```json
{"run_id": "20261118-112912-size-uav_isr_pedido_do_utilizador-6333", "max_iter": 1, "wait_s": 600, "level": "L0", "consistency_order": 0}
```
resultado (excerto):
```json
{
 "run_id": "20261118-112922-optimize-uav_isr_pedido_do_utilizador-e475",
 "status": "done",
 "summary": {
  "objective": "W0",
  "solver": "nlbgs",
  "improved": true,
  "trust_region_iterations": 1,
  "trust_region": [
   {
    "iter": 1,
    "delta": 0.3,
    "predicted": 0.039605749813189074,
    "actual": 0.039604374033944345,
    "rho": 0.9999652631435785,
    "accepted": true,
    "new_failures": [],
    "status": null,
    "status_note": "limite de iterações"
   }
  ],
  "W0_cap_kg": null,
  "x_baseline": {
   "ws": 177.00637761886898,
   "pw": 5.306531287122047,
   "AR": 14
  },
  "x_optimum": {
   "ws": 177.006377618869,
   "pw": 5.481344479569878,
   "AR": 9.8
  },
  "baseline": {
   "W0 [kg]": 23.377596043803422,
   "We [kg]": 10.14677965276509,
   "Wf/bateria [kg]": 9.230816390148055,
   "W/S [N/m²]": 177.00637761886898,
   "P/W [W/N | -]": 5.306531287122047,
   "AR": 14,
   "S [m²]": 1.2951844183637258,
   "b [m]": 4.2582369423380095,
   "CD0": 0.02135276992119555,
   "(L/D)max": 18.408236081469063,
   "energia bateria [Wh]": 1846.1632780296109,
   "P_SL [kW]": 1.2165536180096863,
   "caixão da asa [kg]": 3.5794198383075444,
   "asa (pesos) [kg]": 4.463276473130021,
   "alcance (segmentos) [km]": 212.63034195908432,
   "autonomia (segmentos) [h]": 2.7301885777144093,
   "margem divergence vs 1.2 V_D": 7.680273245903193,
   "margem reversal vs 1.2 V_D": null,
   "margem flutter vs 1.2 V_D": 2.9447653994218808,
   "viável (dimensionamento)": true,
   "verificado (fase 2/3)": false,
   "falhas": "hq:CAP"
  },
  "optimum": {
   "W0 [kg]": 22.451740986070174,
   "We [kg]": 8.833899088121502,
   "Wf/bateria [kg]": 9.61784189781123,
   "W/S [N/m²]": 177.006377618869,
   "P/W [W/N | -]": 5.481344479569878,
   "AR": 9.8,
   "S [m²]": 1.243889450215912,
   "b [m]": 3.491434749800709,
   "CD0": 0.021368136439888736,
   "(L/D)max": 16.565664391852874,
   "energia bateria [Wh]": 1923.568379562246,
   "P_SL [kW]": 1.2068625068864358,
   "caixão da asa [kg]": 3.3618046306790355,
   "asa (pesos) [kg]": 3.321585374593111,
   "alcance (segmentos) [km]": 211.5269846489166,
   "autonomia (segmentos) [h]": 2.7071920234513107,
   "margem divergence vs 1.2 V_D": 10.554972091905876,
   "margem reversal vs 1.2 V_D": null,
   "margem flutter vs 1.2 V_D": null,
   "viável (dimensionamento)": true,
   "verificado (fase 2/3)": false,
   "falhas": "hq:CAP"
  }
 },
 "files": {
  "mdo_report": "examples/ai_session/output/runs/20261118-112922-optimize-uav_isr_pedido_do_utilizador-e475/mdo/mdo_report.md",
  "mdo_json": "examples/ai_session/output/runs/20261118-112922-optimize-uav_isr_pedido_do_utilizador-e475/mdo/mdo.json",
  "baseline_report": "examples/ai_session/output/runs/20261118-112922-optimize-uav_isr_pedido_do_utilizador-e475/mdo/baseline/report.md",
  "optimum_report": "examples/ai_session/output/runs/20261118-112922-optimize-uav_isr_pedido_do_utilizador-e475/mdo/optimum/report.md"
 },
 "job_id": "job-52a713b8"
}
```

## 6. `compare_runs` — L0 vs L1 (the MDO result carries its own baseline vs optimum)

argumentos:
```json
{"run_ids": ["20261118-112905-size-uav_isr_pedido_do_utilizador-3f8d", "20261118-112912-size-uav_isr_pedido_do_utilizador-6333"]}
```
resultado (excerto):
```json
{
 "runs": [
  {
   "run_id": "20261118-112905-size-uav_isr_pedido_do_utilizador-3f8d",
   "tool": "size",
   "name": "UAV ISR (pedido do utilizador)",
   "created": "2026-11-18T11:29:05+00:00"
  },
  {
   "run_id": "20261118-112912-size-uav_isr_pedido_do_utilizador-6333",
   "tool": "size",
   "name": "UAV ISR (pedido do utilizador)",
   "created": "2026-11-18T11:29:12+00:00"
  }
 ],
 "differences": [
  {
   "metric": "aero.CD0",
   "values": [
    0.02135276992119555,
    0.023396962271904326
   ],
   "rel_change_vs_first": [
    0.0,
    0.09573429387630106
   ]
  },
  {
   "metric": "aero.CLmax_clean",
   "values": [
    1.305,
    1.29069562256911
   ],
   "rel_change_vs_first": [
    0.0,
    -0.01096120875930262
   ]
  },
  {
   "metric": "aero.CLmax_landing",
   "values": [
    1.71,
    1.69569562256911
   ],
   "rel_change_vs_first": [
    0.0,
    -0.008365133000520442
   ]
  },
  {
   "metric": "aero.CLmax_takeoff",
   "values": [
    1.368,
    1.356556498055288
   ],
   "rel_change_vs_first": [
    0.0,
    -0.008365133000520553
   ]
  },
  {
   "metric": "aero.K",
   "values": [
    0.03455106489906122,
    0.025236782354797732
   ],
   "rel_change_vs_first": [
    0.0,
    -0.26958018722359456
   ]
  },
  {
   "metric": "aero.LD_max",
   "values": [
    18.408236081469063,
    20.576583920925692
   ],
   "rel_change_vs_first": [
    0.0,
    0.11779226591076974
   ]
  },
  {
   "metric": "aero.elastic_correction.CDi_flex",
   "values": [
    0.009554177421679855,
    0.009382634726335985
   ],
   "rel_change_vs_first": [
    0.0,
    -0.017954732026915665
   ]
  },
  {
   "metric": "aero.elastic_correction.CDi_rigid",
   "values": [
    0.009547405568448873,
    0.009388283828470815
   ],
   "rel_change_vs_first": [
    0.0,
    -0.01666649005714227
   ]
  },
  {
   "metric": "aero.elastic_correction.CLa_flex_per_rad",
   "values": [
    5.195786173290641,
    5.1956729520219245
   ],
   "rel_change_vs_first": [
    0.0,
    -2.1790979255253973e-05
   ]
  },
  {
   "metric": "aero.elastic_correction.CLa_rigid_per_rad",
   "values": [
    5.1786989367070975,
    5.178698936707099
   ],
   "rel_change_vs_first": [
    0.0,
    4.440892098500626e-16
   ]
  },
  {
   "metric": "aero.elastic_correction.K_ratio",
   "values": [
    1.000709287269974,
    0.9993982817053636
   ],
   "rel_change_vs_first": [
    0.0,
    -0.0013100763441369345
   ]
  },
  {
   "metric": "aero.elastic_correction.tip_deflection_m",
   "values": [
    0.01774602815608982,
    0.0171066423797312
   ],
   "rel_change_vs_first": [
    0.0,
    -0.036029796117459933
   ]
  },
  {
   "metric": "aero.elastic_correction.tip_twist_deg",
   "values": [
    0.04415837800315959,
    -0.03588851024189288
   ],
   "rel_change_vs_first": [
    0.0,
    -1.8127225651115402
   ]
  },
  {
   "metric": "aeroelasticity_margins.divergence.V_eas",
   "values": [
    278.26197987491906,
    279.2602961544673
   ],
   "rel_change_vs_first": [
    0.0,
    0.0035876848141345175
   ]
  },
  {
   "metric": "aeroelasticity_margins.divergence.margin",
   "values": [
    7.680273245903193,
    7.711415330410057
   ],
   "rel_change_vs_first": [
    0.0,
    0.004054814654345318
   ]
  },
  {
   "metric": "aeroelasticity_margins.flutter.V_eas",
   "values": [
    126.4566447494354,
    126.76889494182767
   ],
   "rel_change_vs_first": [
    0.0,
    0.0024692272439377216
   ]
  },
  {
   "metric": "aeroelasticity_margins.flutter.margin",
   "values": [
    2.9447653994218808,
    2.9545059216170766
   ],
   "rel_change_vs_first": [
    0.0,
    0.003307741321977087
   ]
  },
  {
   "metric": "design_point.P_SL_W",
   "values": [
    1216.5536180096863,
    1157.525952465077
   ],
   "rel_change_vs_first": [
    0.0,
    -0.04852039784418227
   ]
  },
  {
   "metric": "design_point.W_S_N_m2",
   "values": [
    177.00637761886898,
    175.5251424227394
   ],
   "rel_change_vs_first": [
    0.0,
    -0.008368258907139325
   ]
  },
  {
   "metric": "design_point.W_S_kg_
```

## 7. `hifi_estimate` — compute plan for verification — cfd2d is heavy and needs the user's approval

argumentos:
```json
{"steps": ["fem", "flutter", "cfd2d"]}
```
resultado (excerto):
```json
{
 "verdict": "needs_user_approval",
 "steps": [
  {
   "step": "fem",
   "class": "light",
   "decision": "run",
   "basis": "CalculiX wing-box shell model; measured 49 s (uav) / 152 s (C172)"
  },
  {
   "step": "flutter",
   "class": "light",
   "decision": "run",
   "basis": "FEM modes + DLM p-k in python; not timed"
  },
  {
   "step": "cfd2d",
   "class": "heavy",
   "decision": "needs_approval",
   "basis": "SU2 2-D RANS cruise polar + stall sweep; measured 276 s + 1067 s (uav_endurance_payload) and 346 s + 1578 s (cessna172_check) — examples/output/*_hifi/cfd2d"
  }
 ],
 "needs_approval": [
  "cfd2d"
 ],
 "refused": [],
 "policy": "approval",
 "message": "heavy steps cfd2d need EXPLICIT user approval (ask the user; then call again with user_approved=true). They will use the CPU/RAM of the machine running this MCP server.",
 "machine": {
  "cpu_cores": 8,
  "mem_available_gb": 13.3
 }
}
```

## 8. `generate_report` — design dossier

argumentos:
```json
{"run_ids": ["20261118-112905-size-uav_isr_pedido_do_utilizador-3f8d", "20261118-112912-size-uav_isr_pedido_do_utilizador-6333", "20261118-112922-optimize-uav_isr_pedido_do_utilizador-e475"], "title": "UAV ISR — sessão de demonstração", "notes": "Demo scripted session (examples/ai_session/session.py)."}
```
resultado (excerto):
```json
{
 "run_id": "20261118-113031-report-uav_isr_sess_o_de_demonstra_o-ea2e",
 "status": "done",
 "files": {
  "dossier_md": "examples/ai_session/output/runs/20261118-113031-report-uav_isr_sess_o_de_demonstra_o-ea2e/dossier.md",
  "dossier_json": "examples/ai_session/output/runs/20261118-113031-report-uav_isr_sess_o_de_demonstra_o-ea2e/dossier.json"
 }
}
```
