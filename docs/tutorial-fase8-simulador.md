# Tutorial — Fase 8: superfícies de comando e simulador de missão 6-DOF

A Fase 8 junta ao projeto dimensionado:

* o **dimensionamento das superfícies de comando** (ailerons, profundor, leme e flaps) por requisitos de
  desempenho, com AVL;
* um **simulador de missão 6-DOF** de baixa fidelidade, com piloto automático clássico, vento, turbulência e
  rajadas;
* uma **verificação cruzada com o JSBSim**, que corre como processo separado (LGPL, nunca importado).

A regra é a de sempre: métodos clássicos e citados, nenhum número inventado, baixa fidelidade primeiro e depois
calibração. Os parâmetros que não vêm de uma fonte (ganhos de projeto, ventos do caso de teste, ângulo de
aproximação…) estão marcados no código e nos YAML como **escolhas de projeto** ou **PRESSUPOSTO**.

## 1. Comandos

```bash
source /workspace/acdt_env.sh
# só as superfícies de comando (dimensionamento + momentos de charneira)
acdt controls examples/cessna172_check.yaml -o output/c172_controls
# missão 6-DOF do C172S, com as superfícies dimensionadas e verificação JSBSim
acdt simulate examples/cessna172_check.yaml examples/simulation/c172_check.yaml -o output/c172_sim --jsbsim
# missão de endurance do UAV com vento, turbulência Dryden e rajada
acdt simulate examples/uav_endurance_payload.yaml examples/simulation/uav_endurance.yaml -o output/uav_sim
```

`--layout current` simula com as superfícies que estão no projeto em vez das dimensionadas. Os dois comandos
dimensionam primeiro o avião (como `acdt size`, L1) e precisam do `avl` no `PATH`. O `--jsbsim` precisa de um
Python com o pacote `jsbsim` em `$ACDT_JSBSIM_PYTHON`.

O mesmo YAML corre também em massa pontual, que é o juiz de N0/N1 e não precisa de AVL:
`acdt simulate examples/simulation/n0_patrol.yaml --fidelity pointmass`. O `dt` do YAML é o passo do 6-DOF;
`pointmass_dt` é o passo da massa pontual (omissão 1 s). Ver [tutorial-p3-massa-pontual.md](tutorial-p3-massa-pontual.md).

Ficheiros escritos:

* `controls/controls.json`, `controls_roll.png`, `controls_trim.png`;
* `flight_model.json` (tabelas AVL α × flap, massa, inércias, propulsão, solo);
* `mission/mission_time_history.png`, `mission_trajectory_3d.png`, `mission_ground_track.png`,
  `mission_history.csv`, `mission_summary.json`;
* `jsbsim_pitch.png` (com `--jsbsim`) e `simulation_summary.json`.

Os resultados de referência estão em `examples/output/simulation/`.

Pelo MCP há duas ferramentas novas, ambas como *job* (`job_status` para acompanhar):

* `size_control_surfaces`: o estudo das superfícies (`options` substitui `assumptions.stability.controls`);
* `simulate_mission`: a missão 6-DOF. A missão entra como `mission` (dicionário), `mission_path` ou
  `mission_example` (`c172_check`, `uav_endurance`); `layout` e `jsbsim_check` como no CLI.

## 2. A missão em YAML

```yaml
mission:
  name: C172S verificação POH
  dt: 0.02                       # passo RK4 [s]
  extrapolate_after_s: 60        # segmentos longos: depois de 60 s dinâmicos, extrapola em regime estacionário
  wind: {speed_m_s: 4, from_deg: 270, turbulence: {intensity: light, seed: 3},
         gusts: [{t: 200, amplitude_m_s: 3, gradient_m: 20}]}
  segments:
    - {type: takeoff, flap: 10}
    - {type: climb, to_altitude_m: 600}                     # V_Y do modelo de desempenho se não for dada
    - {type: cruise, time_min: 3, speed_m_s: 55}
    - {type: turn, heading_change_deg: 90, load_factor: 1.4}
    - {type: waypoints, points_km: [[3, 0], [3, 3]]}        # [N, E] em km
    - {type: loiter, time_min: 30, load_factor: 1.15}       # órbita sobre o último ponto
    - {type: descent, to_altitude_m: 150, vertical_speed_m_s: 3, speed_m_s: 40}
    - {type: landing, flap: 30, glide_deg: 3}
```

Comportamento de cada segmento:

* **descolagem**: corrida com travões soltos e manete total, rotação a 1.1 V_S,TO, subida até 15 m (50 ft).
  Sem trem de aterragem (`kind: none`), é um lançamento a 1.3 V_S,TO a 15 m (PRESSUPOSTO, anotado).
* **subida, cruzeiro, viragem, waypoints**: malhas de altitude, velocidade e rumo de Beard & McLain (Cap. 6);
  linhas pela Eq. 10.8.
* **espera**: órbita (Eq. 10.13). O raio é dimensionado para a velocidade-solo máxima (V + vento) com o
  pranchamento limitado a φ_max − 5°; se `load_factor` pedir mais, o raio cresce e fica uma nota.
* **descida**: sem `vertical_speed_m_s`, é a zona de descida de Beard & McLain (ralenti, velocidade por picada).
  Com `vertical_speed_m_s` ou `gamma_deg`, segue uma rampa de altitude com a velocidade na manete. Se a rampa
  for mais íngreme do que o planeio em ralenti, passa à zona de descida e anota. A captura da altitude final é
  exponencial (sem degrau no comando).
* **aterragem**: rampa de `glide_deg` até ao ponto de toque, flare exponencial, corrida com travões. Se o avião
  vier rápido demais em ralenti acima dos 15 m, desacelera por picada e volta a ancorar a rampa (nota).

Saídas por segmento: tempo, distância, combustível ou energia, n_z mín./máx., α máx., tempo em perda,
saturação dos comandos e da manete, e `k_energia` = consumo 6-DOF / consumo quase-estacionário com o mesmo
modelo de desempenho do dimensionamento. Na descolagem e na aterragem saem as distâncias.

## 3. Superfícies de comando

| superfície | requisito | método |
|---|---|---|
| aileron | tempo para inclinar: MIL-F-8785C Tab. IXa (Classe I: 60° em 1.7 s Cat. B; 30° em 1.3 s Cat. C); CS/14 CFR 23.157 | AVL (C_lδa, C_lp), resposta de 1.ª ordem (Sadraey Sec. 12.4.2) |
| profundor | rotação na descolagem sobre o trem principal; compensação em todo o envelope de CG × flaps | Sadraey Sec. 12.6.3 com C_m do AVL |
| leme | vento cruzado ≥ 0.2 V_S0 (14 CFR 23.233); OEI em multimotores | AVL (C_nδr, C_nβ + fuselagem por Raymer Eq. 16.47) |
| flaps | CL_max pedido pela perda e pela distância de aterragem | Raymer Eq. 12.21 invertida |

Os momentos de charneira saem do AVL nas condições da 14 CFR 23.455 (V_A deflexão total; V_D 1/3) e dão o
binário de servo (UAV) ou a indicação para verificar forças no manche (CS 23.143).

## 4. Validação — C172S

Referência: Cessna 172S POH / Information Manual, Rev. 5 (2004), "Performance – Specifications" (2550 lb, nível
do mar, ISA, pista seca, vento nulo). Projeto: `examples/cessna172_check.yaml`; missão:
`examples/simulation/c172_check.yaml`.

| grandeza | POH | 6-DOF acdt | desvio |
|---|---|---|---|
| corrida de descolagem | 960 ft (293 m) | 270 m | −8 % |
| descolagem até 50 ft | 1630 ft (497 m) | 451 m | −9 % |
| corrida de aterragem | 575 ft (175 m) | 191 m | +9 % |
| aterragem desde 50 ft | 1335 ft (407 m) | 500 m | +23 % |
| razão de subida ao nível do mar | 730 ft/min (3.7 m/s) | 5.8 m/s (média 16 → 600 m) | +56 % |

Leitura:

* **Descolagem**: dentro de 10 %, mas por compensação de erros. O simulador roda a 1.1 V_S,TO e descola a
  34.8 m/s (68 kt), acima dos 51 KIAS da técnica de pista curta do POH, e a tração disponível é demasiado alta
  (ver subida).
* **Aterragem**: a corrida bate (+9 %). A distância total é maior porque a aproximação é uma rampa de 3° desde
  os 15 m (309 m no ar). A técnica de pista curta do POH (61 KIAS, flaps 30, potência reduzida) é mais
  inclinada. O ângulo de aproximação é uma escolha de projeto (`glide_deg`).
* **Subida**: +56 %. A causa está no modelo de propulsão do dimensionamento (potência nominal e rendimento da
  hélice constantes), não no 6-DOF: o modelo quase-estacionário dá o mesmo consumo (k = 0.97). Uma hélice de
  passo fixo a 70 kt não absorve a potência nominal. É o próximo ponto de calibração (roadmap).

Verificação cruzada com o JSBSim (mesmo modelo exportado para XML, cruzeiro a 55 m/s e 597 m):

| | α_trim | δe_trim | manete |
|---|---|---|---|
| acdt 6-DOF | 3.54° | −1.54° | 0.675 |
| JSBSim 1.3.3 | 3.53° | −1.53° | 0.682 |

Resposta a um doublet de profundor: erro RMS normalizado α 2.7 %, q 2.9 %, θ 2.3 %, V 2.2 %, h 1.3 %. Esta
verificação confirma as equações do movimento e a integração, **não** a aerodinâmica, porque os dois correm as
mesmas tabelas.

Inércias: a soma de componentes dá Ixx 2439, Iyy 1660, Izz 4093 kg m². O modelo `c172p` do JSBSim (dados
públicos, "educational and entertainment purposes only" no cabeçalho) tem 1285, 1825 e 2667 kg m². Iyy bate
(−9 %), mas Ixx (×1.9) e Izz (×1.5) estão altos. O rolamento simulado é por isso conservador. Pode-se impor as
inércias com `options: {inertia_kgm2: {Ixx: …, Iyy: …, Izz: …}}` (MCP `simulate_mission`) quando houver dados
medidos ou publicados (calibração progressiva).

Qualidades de voo (cruzeiro): período curto ζ 0.83, CAP 2.2, fugoide ζ 0.13, rolamento holandês ζ 0.18 /
ω 1.5 rad/s, τ_R 0.22 s, espiral estável. Tudo Nível 1 (MIL-F-8785C).

Superfícies dimensionadas vs históricas. O Cessna 182 é o avião da mesma família nas tabelas de Sadraey
(2012) Cap. 12:

| | dimensionado (acdt) | Cessna 182 (Sadraey) | requisito ativo |
|---|---|---|---|
| aileron (fração da semienvergadura) | 0.20 (c_a/c 0.25) | 0.49 (0.46 → 0.95), c_a/c 0.20 | 30° em 1.08 s ≤ 1.3 s (Cat. C, aproximação) |
| profundor c_e/c_h | 0.20 | 0.44 | rotação e compensação com margem ≥ 14° |
| leme c_r/c_v | 0.20 | 0.42 | vento cruzado 9.6 kt (0.2 V_S0); máx. 37 kt |

Os requisitos mínimos de certificação cumprem-se com superfícies bem menores do que as do avião real. As
superfícies reais são dimensionadas também por critérios que esta fase não avalia: recuperação de vrille
(CS 23.221), forças e harmonia no manche, controlo a baixa velocidade com potência, folgas para variantes. Por
isso, o mínimo dimensionado é um **limite inferior**, não a recomendação final.

## 5. Missão de endurance do UAV

Projeto: `examples/uav_endurance_payload.yaml` (requisito: 2.5 h de espera); missão:
`examples/simulation/uav_endurance.yaml`. Condições: vento 4 m/s de oeste, turbulência Dryden ligeira e uma
rajada 1−cos de 3 m/s.

| segmento | tempo | energia | k_energia (6-DOF / quase-estacionário) |
|---|---|---|---|
| lançamento + subida a 300 m | 1.6 min | 40 Wh | 1.05 |
| 3 waypoints (≈ 7.5 km) | 6.0 min | 43 Wh | 1.11 |
| espera 120 min (raio 122 m) | 120 min | 782 Wh | 0.96 |
| descida em ralenti + aterragem (rampa 2°) | 5.2 min | 5 Wh | — |
| **em voo** | | | **0.97** |

Leitura:

* **k de 0.96 a 1.11** nos segmentos em voo. Nos waypoints, a turbulência faz a manete "perseguir" a velocidade e
  não há regeneração em ralenti. Na espera, a órbita foi dimensionada com φ 25° (n = 1.15 pediria 30°), por
  isso gasta menos do que a viragem n = 1.15 do modelo quase-estacionário.
* **Endurance**: o dimensionamento dá 2.77 h com o orçamento de energia completo. Com k_energia = 0.97 o 6-DOF
  confirma a margem sobre as 2.5 h pedidas.
* **Aterragem**: o UAV planeia em ralenti a menos de 3°, por isso a missão usa `glide_deg: 2` (escolha de
  projeto). Mesmo assim desacelera por picada uma vez antes da rampa (nota). Toque a 22.5 m/s (V_REF 19.4) com
  0.35 m/s de razão de descida, sobre os patins. O UAV não tem flaps nem travões aerodinâmicos para
  gastar a energia na aproximação.
* **Qualidades de voo**: CAP 8.7 (Nível 2: período curto rápido para um avião deste tamanho) e espiral
  instável com T2 8.7 s (Nível 2). Estes níveis são indicativos para UAV. O piloto automático estabiliza a
  espiral.

## 6. Limites

* Aerodinâmica L1: AVL potencial sem fuselagem (C_nβ e C_m corrigidos por Raymer), perda por mistura sigmoide
  até ao CL_max do projeto (Beard & McLain), sem efeito de solo nem sopro da hélice.
* Inércias da soma de componentes (ver o C172).
* Modelo de propulsão herdado do dimensionamento (subida do C172 otimista).
* O piloto automático é um piloto automático de UAV (Beard & McLain): no C172 representa um piloto "perfeito",
  não a técnica do POH.
* Turbulência Dryden só nas intensidades ligeira/moderada abaixo e acima dos 300 m (Beard & McLain Tab. 4.1;
  a troca de banda aos 300 m é escolha nossa, com reescala dos estados do filtro).
* Recuperação de vrille não avaliada. A MIL-F-8785C é indicativa para UAV.
