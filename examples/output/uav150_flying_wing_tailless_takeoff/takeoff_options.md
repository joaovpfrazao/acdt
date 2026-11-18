<!-- Gerado por flightsim/takeoff_options.py: exemplo uav150_flying_wing_tailless.yaml + uav150_tailless_crosswind.yaml, Linux, 16 nov 2026. Os números do 6-DOF dependem da plataforma. -->
# Opções da corrida de descolagem (fly_off)

* Requisito: 300 m. 6-DOF na missão: 325.1 m (vento de frente 0.0 m/s, cruzado 5.2 m/s).
* 6-DOF em ar calmo: 296.2 m; penalização do vento cruzado 28.9 m.
* Massa pontual: 291.0 m no vento da missão, 291.0 m em ar calmo; k = 6-DOF/massa pontual 1.117 (PRESSUPOSTO: razão 6-DOF/massa pontual medida no vento da missão, mantida constante entre opções).

| Opção | O que é preciso | Corrida estimada [m] | Fecha | Custo / nota |
|---|---|---|---|---|
| a. vento de frente / rumo da pista | vento de frente ≥ 1.2 m/s (vento a ≤ 76° da pista, cruzado restante 5.0 m/s); no 6-DOF ≥ 1.35 m/s (rumo 195°, vento a ≤ 75° da pista) | 299.8 (6-DOF 301.5 → 300.1 → 299.4) | sim | operacional: escolha da pista face ao vento; a capacidade de 90° de 14 CFR 23.233(a) continua a ser demonstrada à parte |
| b. tração | ×1.060 (6-DOF ×1.066) | 299.9 (6-DOF 302.2 → 299.8) | sim | massa do motor/hélice e consumo não iterados (PRESSUPOSTO) — novo ciclo W0 necessário |
| c. carga alar (S maior) | S ×1.079 | 299.9 | sim | massa e arrasto da asa maiores não iterados (PRESSUPOSTO); C_L de cruzeiro desce |
| d. massa de descolagem | −4.9 kg | 299.9 | sim | menos combustível/carga útil → menos autonomia ou payload (requisito) |
| e. atitude de descolagem | nenhuma fecha: mínimo 322.4 m a θ_g 19.5° (C_D cresce com θ; perda a θ ≈ 23.4°) | — | não | perna do nariz mais longa (massa, Raymer Eq. 15.51); folga traseira e hélice menores; α_C 25.3° |
| f. catapulta | bloco launch_recovery.catapult | — | unassessed | assumptions.launch_recovery.catapult ausente — opção não avaliada (≠ passa) |
| g. vento cruzado demonstrado menor | não admissível | ar calmo 6-DOF 296.2 | não | abaixo de 0,2 V_S0 falha 14 CFR 23.233(a) (pré-Amdt 64) — não relaxado |

Fecham: a_vento_de_frente, b_tracao, c_carga_alar, d_massa.

Fontes: Raymer 2018 Sec. 17.8 (V_TO = 1,1 V_S, μ Table 17.1); Sadraey 2012 Sec. 9.6.2 (atitude de descolagem sem rotação) e Sec. 9.5.1.3 (folga traseira); 14 CFR 23.233(a) pré-Amdt 64 (vento cruzado ≥ 0,2 V_S0); Fahlstrom, Gleason & Sadraey 2022 Ch. 17 (catapulta).
