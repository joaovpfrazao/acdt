# Tutorial — Fase 9: hélice de passo fixo, inércias Roskam e camber flaps como opção de projeto

A Fase 9 tem duas partes:

* **Calibração (passo 0).** Hélice de passo fixo BEMT usada pelo dimensionamento e pelo simulador. Subida do C172
  revista face ao POH. Inércias pelos raios de giração de Roskam (Part V). Corrigido o caminho do JSBSim.
* **Camber flaps (cruise flaps) como OPÇÃO.** O otimizador compara `none` / `plain` / `camber` / `flaperon`
  e só escolhe camber se o ganho for justificado.

As regras são as de sempre:

* métodos clássicos e citados;
* nenhum número inventado;
* XFOIL, AVL e JSBSim correm sempre como processos separados.

Os valores que são escolhas de projeto estão marcados **PRESSUPOSTO** no código e nos YAML.

## 1. Hélice de passo fixo (sizing + simulador)

O modelo `propeller.py` usa:

* BEMT com perdas de Prandtl/Glauert (McCormick 1995; resíduo de Ning 2014);
* pós-perda de Viterna;
* polares NeuralFoil do Clark Y;
* geometria de Adkins & Liebeck quando o utilizador não a dá.

Para o C172S a hélice é a McCauley 1C160/DTM7557: 76 in de diâmetro, 60 in de passo. As rpm estáticas são
calibradas para as 2350 rpm do POH.

O motor está limitado a 2700 rpm. Em subida e a baixa velocidade a hélice limita as rpm e, por isso, a potência
disponível.

No `sizing.run`, as eficiências constantes `eta_takeoff`, `eta_climb` e `eta_cruise` são substituídas, por
calibração progressiva (no máximo 5 passagens), pelos valores do mapa da hélice. O resultado fica em
`result.propeller_calibration`.

| C172S (MTOW 2550 lb) | acdt (Fase 9) | POH C172S | desvio |
|---|---|---|---|
| ROC máx. ao nível do mar | 3,634 m/s = **715 ft/min** | 730 ft/min | −2,0 % |
| η descolagem / subida / cruzeiro | 0.465 / 0.679 / 0.882 | — | — |
| rpm estáticas | 2349 | 2300–2400 | ✓ |
| teto de serviço | 4504 m | requisito do YAML ≥ 4115 m | ✓ |

O teste `test_performance_c172` aceita a subida a ±5 % do requisito. A verificação `perf:climb_rate` usa 0,1 %
e continua a falhar. O resultado do modelo, medido a 30 out 2026, é 715 ft/min (−2,0 % face às 730 do POH).

O trim 6-DOF de cruzeiro é feito a 0.95·Vc. A 8000 ft a hélice está limitada pelas 2700 rpm e o arrasto 6-DOF é
~3 % superior ao do dimensionamento.

## 2. Inércias: Roskam Part V vs soma por componentes vs c172p

`assumptions.stability.inertia_method` tem dois modos:

* `roskam`: Eqs. 3.7–3.9 com os raios de giração adimensionais R̄x, R̄y, R̄z da Tabela B2. A referência é
  `roskam_reference`, p. ex. `cessna_172m` = 0.242 / 0.386 / 0.403. Aplica-se à massa vazia operacional e soma-se a
  carga paga e o combustível por componentes.
* `components` (por omissão).

O utilizador pode dar os seus próprios `radii_of_gyration`.

| C172 carregado 2550 lb [kg·m²] | Ixx | Iyy | Izz |
|---|---|---|---|
| JSBSim c172p (só referência) | 2770 | 2002 | 4153 |
| acdt Roskam (C172M, Tab. B2) | 2430 (−12 %) | 1907 (−5 %) | 3888 (−6 %) |
| acdt soma por componentes | 2269 (−18 %) | 1617 (−19 %) | 3880 (−7 %) |

O exemplo `cessna172_check.yaml` usa agora `inertia_method: roskam`. O `jsbsim_pitch.png` foi regenerado, com o
trim do JSBSim a coincidir com o nosso (α 3.54° vs 3.53°, δe −1.52° vs −1.51°). Os nrms longitudinais do doublet
são 1–3 %.

## 3. Camber flaps — o método

Um camber flap é um flap simples de bordo de fuga com 15–25 % da corda, defletido em voo:

* negativo a alta velocidade (CL baixo);
* positivo em loiter (CL alto).

Assim, cada CL é voado com a secção cujo "balde" de baixo arrasto o contém. O avião segue a **envolvente** das
polares (Thomas 1999 cap. 3 e 5; Althaus & Wortmann 1981; Boermans 2006).

1. **Polares da secção vs δf.** O XFOIL usa `GDES/FLAP` (charneira na linha média em x/c = 1 − c_f/c). A
   alternativa é o NeuralFoil sobre a geometria defletida do AeroSandbox. Por omissão δf vai de −10° a +15°, em
   passos de 2.5°. As polares ficam em cache em disco (`~/.cache/acdt/polars`; `ACDT_POLAR_CACHE=off` desliga a
   cache).
2. **Envolvente da secção.** cd_env(cl) = min_δ cd_δ(cl), só com deflexões em regime colado:
   cl_min + 0.05 < cl < cl_max − 0.15.
3. **Envolvente da asa.** A carga em envergadura é a da asa limpa (AVL, ou Schrenk). Para cada CL do avião
   escolhe-se UM δ para todo o vão com flap, e ΔCD(CL) = Q(1+fuga)·Σ(cd_δ − cd_0)·S_i/S ≤ 0. A `DragPolar` passa a
   ter `camber`. L/D max, CL(L/D max) e CL de potência mínima são então calculados numericamente.
4. **Hipersustentação.** O ΔCLmax é dado por Raymer Eq. 12.21 com o incremento da secção (XFOIL a δmax, ao Re de
   perda). Com `landing_deflection: true` (PRESSUPOSTO, prática de planadores: Thomas cap. 5), o camber flap serve
   também de flap de aterragem. Nesse caso recebe pelo menos o incremento do flap simples de Raymer (Tab. 12.2)
   na sua área.
5. **Entradas a jusante:**
   * diagrama de restrições: cruzeiro/Vmax, subida e Vy com CL_opt;
   * missão: segmentos e descida;
   * MDO: polar congelada da base;
   * massa: atuadores e ferragens, só com valores do utilizador;
   * custo: Eastlake F_CF 1.03 para flaps complexos (Gudmundsson 2.2.2), mais o custo dos atuadores.

```yaml
assumptions:
  design_options:
    flaps:
      options: [none, plain, camber, flaperon]
      objective: W0            # W0 | cost | energy | endurance | range | V_max
      min_gain: 0.01           # camber/flaperon só se ganharem >= 1 % (PRESSUPOSTO)
      camber: {chord_ratio: 0.20, eta_out: 0.65, actuators: 2,
               actuator_mass_kg: 0.06, surface_mass_kg_m2: 0.15, actuator_cost_usd: 60}
      flaperon: {chord_ratio: 0.20, eta_out: 0.95, actuators: 0, surface_mass_kg_m2: 0.10}
```

### Comparação justa

Um camber flap com mais área do que o flap simples do utilizador ganharia só por ter um flap de aterragem maior.
Por isso o estudo junta automaticamente duas alternativas sem escalonamento em cruzeiro:

* `plain_same_area`: flap simples com a mesma S_flapped/S do camber;
* `droop_flaperon`: flaperon descaído só na aterragem.

O camber ou o flaperon só é escolhido se melhorar o objetivo em ≥ `min_gain` face à melhor destas opções simples.

```bash
acdt flap-options examples/uav_loiter_dash_camber.yaml -o output/ld
acdt flap-options examples/uav_endurance_payload.yaml --objective W0
acdt flap-options examples/uav_loiter_dash_camber.yaml --sweep max_speed=40,50,60,70   # Pareto
```

No MCP, a ferramenta é `flap_options`: aceita `options`, `objective`, `min_gain`, `per_option` e `sweep`, e corre
como job.

## 4. Resultados das demos

Objetivo W0 em todas as demos e margem mínima de 1 % sobre a melhor opção simples (none / plain /
plain_same_area / droop_flaperon). Os números abaixo vêm dos `flap_options.json` de cada pasta.

### 4.1 Onde o camber ganha: UAV loiter + dash (`examples/uav_loiter_dash_camber.yaml`)

O cenário pede 4 h de loiter a 22 m/s, um dash de 70 m/s, perda ≤ 17 m/s e MTOW ≤ 35 kg (PRESSUPOSTO do
cenário).

| opção | W0 [kg] | S [m²] | P_sl [kW] | P_loiter [W] | bateria [kg] | sistema de flap [kg] | custo unit. [$] | estado |
|---|---|---|---|---|---|---|---|---|
| none | 37.68 | 1.461 | 7.21 | 385 | 19.90 | 0 | 30 373 | inviável (envergadura, MTOW) |
| plain | 36.80 | 1.113 | 6.29 | 409 | 20.86 | 0 | 28 814 | inviável (MTOW) |
| **camber** | **31.62** | 0.913 | 5.38 | 329 | 17.04 | 0.14 | 28 118 | **selecionado** |
| flaperon | 31.65 | 0.825 | 5.18 | 342 | 17.64 | 0.01 | 27 476 | viável |
| plain_same_area | 32.11 | 0.927 | 5.78 | 337 | 17.45 | 0 | 27 693 | viável (melhor opção simples) |
| droop_flaperon | 32.29 | 0.841 | 5.56 | 350 | 18.05 | 0 | 27 326 | viável |

Camber face à melhor opção simples (plain_same_area):

* W0 −0.49 kg (−1.5 %);
* bateria −0.41 kg;
* potência instalada −0.40 kW (−6.9 %);
* P_loiter −7.8 W (−2.3 %);
* sistema de flap +0.14 kg;
* custo +$425.

Endurance (4.18 h) e V_max (69.7 m/s) ficam iguais, porque são requisitos ativos. Face ao plain com a área
original, o camber poupa −5.18 kg e torna o projeto viável.

O camber e o flaperon ficam praticamente empatados (0.03 kg). O flaperon é $642 mais barato e o seu
sistema de flap é mais leve. Se o custo pesar, escolhe-se o flaperon com `--objective cost`.

**Varrimento do dash** (`pareto_max_speed.json`):

| dash [m/s] | plain | camber | flaperon | plain_same_area | melhor em W0 |
|---|---|---|---|---|---|
| 40 | 27.39 | 27.98 | 29.12 | 27.88 | plain |
| 50 | 27.80 | 28.27 | 29.29 | 28.20 | plain |
| 60 | 29.24 | 29.37 | 30.17 | 29.41 | plain |
| 70 | 36.80 (inviável) | **31.62** | 31.65 | 32.11 | camber |

Até 60 m/s o camber não se justifica em W0. A massa do sistema de flap pesa mais do que o ganho de cerca de
0.5 % na potência de loiter. A W0 é dominada pela energia de loiter a CL ≈ 1.2, onde o envelope pouco
melhora a polar.

O cruzamento dá-se entre 60 e 70 m/s. Aí o dash a CL muito baixo, com δf negativo, reduz a potência
instalada, e o motor e a bateria deixam de crescer. Em potência instalada, o camber/flaperon ganha já a
partir de 50 m/s: a 60 m/s fica em 3.42 / 3.29 kW, contra 3.54 kW do plain_same_area.

### 4.2 Onde o camber não ganha

* **UAV existente** (`uav_endurance_payload`): o selecionado é o droop_flaperon (20.55 kg). O flaperon com
  escalonamento de camber dá 20.51 kg, um ganho de 0.19 % < 1 %, por isso não se justifica.
* **Cessna 172S** (`cessna172_check`, `--options none,plain,camber`):

  | opção | W0 [kg] | S [m²] |
  |---|---|---|
  | plain (flap slotted do utilizador) | 1137.8 | 13.76 |
  | camber | 1160.8 | 15.13 |
  | plain_same_area | 1160.7 | 15.13 |
  | none | 1273.1 | 21.74 |

  O selecionado é o plain. O camber fica igual ao plain_same_area (+0.06 kg), sem ganho a Re ≈ 5×10⁶ e com
  um perfil NACA 2412 turbulento. O exemplo não define a massa dos atuadores do C172, por isso `flap sys`
  aparece como 0.

### 4.3 Gráficos (caminhos absolutos)

* `examples/output/flap_options/uav_loiter_dash/camber_camber.png`:
  envelope da polar e escalonamento δf(CL).
* `examples/output/flap_options/uav_loiter_dash/camber_flaperon.png`
* `examples/output/flap_options/uav_loiter_dash/design_point_shift.png`:
  deslocamento do ponto de projeto.
* `examples/output/flap_options/uav_loiter_dash/pareto_max_speed_W0.png`
* `examples/output/flap_options/uav_loiter_dash/pareto_max_speed_power.png`
* `examples/output/flap_options/uav_endurance/{camber_camber,camber_flaperon,design_point_shift}.png`
* `examples/output/flap_options/c172/{camber_camber,design_point_shift}.png`
* `examples/output/simulation/c172/jsbsim_pitch.png`

## 5. Limitações

* Não é modelado o arrasto de compensação devido ao Δcm0 do camber (cerca de −0.003/°). Também não é
  modelado o arrasto de folga e fuga da articulação.
* O ΔCD(CL) da asa usa a carga de envergadura da asa limpa.
* O XFOIL converge mal a δ grandes e com as coordenadas FX67-K-150 da UIUC (clmax 1.19), por isso a demo usa
  SD7062. Os timeouts de XFOIL caem no NeuralFoil.
* A transição natural na demo (laminar 1.0) é um PRESSUPOSTO, e o ganho do camber depende dela.
* A estimativa de custo de Eastlake não é válida para UAV; serve só para comparação relativa.
* O CP da hélice tem um comportamento estranho a J baixo. A aterragem do C172 dá 504 m contra 407 m
  requeridos (problema anterior a esta fase).
* As inércias Roskam ficam 5–12 % abaixo das do c172p.
* A W0 resulta de um MDA de baixa fidelidade com histerese de Re de ±8 %. Diferenças abaixo de cerca de
  0.5 % estão dentro do ruído numérico, e daí a margem de 1 %.


## Arrasto de compensação e folga (opt-in, 10 nov 2026)

Por omissão a polar de envolvente (loiter / alta velocidade) **não** inclui arrasto de compensação
nem de folga — só o ΔCD de perfil da melhor δ(CL) (Thomas / Althaus). Opt-in:

```yaml
assumptions:
  aero:
    camber_flap:
      trim_drag: true   # HT: CL_h = −ΔCm/(η V_H); CD_i,h = CL_h²/(π e AR_h)·(S_h/S) — Nelson/Etkin
      gap:
        sealed: true
        source: "XFOIL GDES/FLAP sealed-gap assumption"
        # ou: {dCD: 0.001, source: "DATCOM/ensaio — datado"}
        # chord_ratio sozinho → unassessed (não se inventa correlação gap→ΔCD)
```

Sem geometria de HT / cm0, ou gap sem `dCD`/`sealed` → check `aero:camber_trim_drag` /
`aero:camber_gap_drag` com `ok: null` (unassessed ≠ pass). Demo:
`PYTHONPATH=src python examples/camber/trim_gap_demo.py`.
