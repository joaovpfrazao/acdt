# Gestão térmica (disciplina `termica`, L0/L1)

Estado em 18 nov 2026 (ramo `disc-termica`). Código: `acdt/core/thermal/` (núcleo, domínio-agnóstico, mypy
estrito), `acdt/domains/aircraft/thermal.py` (etapa `thermal` do pipeline e acoplamento) e `acdt.api.thermal` /
`acdt.api.thermal_atmosphere` (especificação genérica, desde a API 1.3.0).

## 1. O que faz

* **Fontes de calor a partir dos modelos existentes**: carga elétrica de bordo (aviónica + carga útil), perdas da
  cadeia elétrica (bateria, ESC, motor) pelas eficiências, efeito Joule da bateria (I²R), calor rejeitado pelo
  arrefecimento de um motor térmico (balanço de energia) e fontes declaradas.
* **Compartimentos (baias)**: temperatura em regime permanente (nó do ar + nó da pele) e transitório
  concentrado (capacidade térmica do compartimento), em dias quentes e frios.
* **Arrefecimento**: pele (convecção forçada/natural + radiação + sol), ventilação por ar dinâmico com
  dimensionamento de entrada NACA submersa e conduto (área, caudal, arrasto interno, massa) e ventilador (potência).
* **Atmosferas de projeto**: dia quente 1 % e dia frio 1 %/20 % da **MIL-HDBK-310** (0–30 km quente e frio 1 %;
  0–10 km frio 20 %), ISA ou perfil próprio.
* **Limites de componentes como requisitos**: margens a quente e a frio por componente e por compartimento;
  tipos de requisito `thermal_margin`, `cold_thermal_margin` e `cooling_drag_area`.
* **Acoplamento**: arrasto de arrefecimento na polar (área de arrasto extra), massa do conduto/permutador nos
  pesos, potência do ventilador no balanço elétrico. Por omissão só é relatado; com `coupling: iterar` entra num
  ponto fixo com o dimensionamento.
* **Integração**: etapa `thermal` do pipeline (depois do ruído, antes do relatório), secção `thermal` no
  `result.json`, disciplina `termica`/L0 no `design.json`, avaliador `termica:` na matriz de verificação, métricas
  para UQ e MDO (`thermal.hot_margin_min_C`, `thermal.cooling.drag_area_m2.hi`, …), seis casos V&V.

## 2. Métodos e fontes (cada equação conferida com a fonte)

| Peça | Método | Fonte |
|---|---|---|
| μ do ar | μ = β T^1,5/(T + S), β = 1,458×10⁻⁶, S = 110,4 K | U.S. Standard Atmosphere 1976, Eq. (51) |
| k do ar | k = 2,64638×10⁻³ T^1,5/(T + 245,4·10^(−12/T)) | U.S. Standard Atmosphere 1976, Eq. (53) |
| c_p, ρ | c_p = γR/(γ−1) = 1004,7 J/(kg·K); gás perfeito | PRESSUPOSTO: ar seco, c_p constante |
| Dias quente/frio | perfis 1 % quente (§5.3.1.1.2, com ρ), 1 % frio (§5.3.1.2.2), 20 % frio (Tabela XX, p ISA); sol 1120 W/m² (Tabela I) | MIL-HDBK-310 (1997) |
| Placa plana, laminar | Nu = 0,664 Re^½ Pr^⅓ | Incropera 6.ª ed., Eq. 7.30 |
| Placa plana, mista | Nu = (0,037 Re^⅘ − 871) Pr^⅓ (Re_x,c = 5×10⁵); turbulenta desde o bordo com A = 0 | Incropera, Eq. 7.38 |
| Temperatura de parede adiabática | T_aw = T∞ + r V²/(2c_p), r = Pr^½ (laminar) ou Pr^⅓ (turbulento) | White, *Viscous Fluid Flow*, 3.ª ed. |
| Convecção natural, vertical | Churchill & Chu | Incropera, Eq. 9.26 |
| Convecção natural, horizontal | Eq. 9.30–9.31 (face quente para cima), 9.32 (0,27 Ra^¼, face quente para baixo) | Incropera, Eq. 9.30–9.32 |
| Conduto | Dittus–Boelter (turbulento), Nu = 3,66/4,36 (laminar) | Incropera, Eq. 8.53, 8.55, 8.60 |
| Radiação | q = εσA(T⁴ − T∞⁴), σ = 5,670374419×10⁻⁸ (CODATA 2018) | Incropera, Eq. 1.7 |
| Transitório | C dT/dt = Q − perdas (capacidade concentrada); Bi para validade | Incropera, Eq. 5.5–5.7, 5.10 |
| Caudal de ar | ṁ = Q/(c_p ΔT) | balanço de energia |
| Entrada NACA submersa | A = ṁ/(MFR ρ V), MFR de projeto 0,60 | Hall & Frank, NACA RM A8I29 (1948) |
| Arrasto interno | D = ṁ(V − V_e), V_e = V√(1 − ζ), ζ = (1 − η_r) + perda do conduto em q | Anderson, *Fundamentals of Aerodynamics*, 5.ª ed., Cap. 2–3 (quantidade de movimento e Bernoulli) |
| Ventilador | P = ṁ Δp/(ρ η) | idem |
| Cadeia elétrica | perda total P_bat(1 − η_cadeia); motor P_veio(1/η_m − 1); ESC (P_veio/η_m)(1/η_ESC − 1); bateria I²R ou P(1 − η_bat) | definições de eficiência |
| Motor térmico | P_comb = ṁ_f·PCI; calor de arrefecimento = fração declarada, senão [0, P_comb − P_veio] | Heywood (1988), Cap. 12 |
| PCI por omissão | avgas 43,5 MJ/kg (ASTM D910), Jet A 42,8 MJ/kg (ASTM D1655) | mínimos da especificação — PRESSUPOSTO |

Os exemplos resolvidos de Incropera foram transcritos através do FOSSEE Textbook Companion (IIT Bombay), que
reproduz os enunciados e as respostas do livro.

## 3. Completude: desconhecido ≠ zero, não avaliado ≠ passa

Segue o padrão da disciplina de ruído ([RUIDO.md](RUIDO.md)):

* Cada fonte de calor é um intervalo `[lo, hi]`; `hi = None` significa majorante desconhecido. Uma cadeia
  elétrica sem eficiências por componente dá a cada componente não declarado `[0, resto]` com um **majorante
  partilhado** (a soma nunca excede a perda total da cadeia).
* As temperaturas resolvem-se em todos os vértices da caixa de parâmetros incertos (ε exterior, α solar,
  ε interior e, com escoamento, camada limite laminar/mista ou turbulenta desde o bordo — até 16 vértices): o
  máximo com a potência máxima dá o majorante e o mínimo com a potência mínima dá o minorante. PRESSUPOSTO:
  temperatura monótona em cada parâmetro (o sentido pode mudar: parado ao sol a pele aquece o compartimento e um
  ε interior alto passa a ser o caso quente — por isso não se fixa um «vértice quente» à partida). ε e α não declarados valem o intervalo físico [0, 1] — os resultados ficam largos e o
  utilizador deve declarar as propriedades da tinta/acabamento.
* As margens são intervalos. Requisito mínimo: passa se lo ≥ limiar, falha se hi < limiar, senão `desconhecido`.
  Margem sem minorante nunca passa. Conduto declarado mas não dimensionável → arrasto e massa desconhecidos (nunca 0).
* Componente sem condutância componente→ar (`conductance_W_K` ou `case_area_m2`): T ≥ T_compartimento, majorante
  desconhecido.
* Carga de bordo declarada nula gera uma nota (pode ser omissão do modelo).

## 4. Pressupostos (PRESSUPOSTO) e limites

* Rede de dois nós por compartimento (ar + pele), pele isotérmica, radiação interior linearizada em série com a
  condutância da parede; ar de entrada à temperatura total (recuperação completa da temperatura).
* Conduto aberto em todas as condições salvo `open_conditions` (obturador); sem ele, no dia frio a ventilação
  arrefece o compartimento até perto do ar exterior.
* No dimensionamento do conduto, todo o calor sai pelo ar (pele ignorada) — conservativo.
* No transitório a pele é quase-estacionária; a capacidade tem de ser declarada (`capacity_J_K` ou
  `mass_kg` + `cp_J_kgK`).
* Efeito Meredith (impulso do ar aquecido) desprezado; arrasto externo da entrada só se declarado
  (`external_drag_N`).
* Sol de projeto 1120 W/m² ao nível do mar a qualquer altitude (subestima a irradiância em altitude).
* MIL-HDBK-310 frio 20 % só até 10 km; acima usa-se o 1 %.
* Jatos: calor do motor para compartimentos adjacentes não modelado — declare-o como fonte.
* Fidelidade L0/L1: sem condução multidimensional, sem permutadores líquidos, sem ciclos de refrigeração.

## 5. Uso

### 5.1 No pipeline (`assumptions.thermal` da missão)

```yaml
assumptions:
  thermal:
    coupling: relatorio          # ou iterar (ponto fixo com o dimensionamento)
    hot_atmosphere: mil310_hot_1pct
    cold_atmosphere: mil310_cold_1pct   # ou mil310_cold_20pct (recomendado pela MIL-HDBK-310 para projeto)
    ground_time_s: 300           # transitório no solo antes da descolagem
    electric: {eta_esc: 0.97, eta_motor: 0.90, cell_R_internal_ohm: null}
    engine: {fuel: avgas, cooling_fraction: null, air_temperature_rise_K: 30}
    bays:
      - id: fuselagem
        skin_area_m2: 1.0
        flow_length_m: 1.6
        height_m: 0.2
        eps_ext: 0.85
        alpha_solar: 0.3
        eps_int: [0.1, 0.9]
        sources: [avionica, bateria, esc]
        capacity_J_K: 9000
        components:
          - {id: bateria_pack, source: bateria, conductance_W_K: 10, T_max_C: 60, T_min_C: -20,
             limit_source: "folha de dados da célula"}
        ram_air:
          size_for: cruzeiro_quente
          ram_recovery: 0.8
          duct_loss_q: 0.5
          duct: {length_m: 0.4, areal_density_kg_m2: 1.0}
          open_conditions: [solo_quente, subida_quente, cruzeiro_quente]   # obturador fechado no dia frio
requirements:
  thermal_margin: {min: 0, unit: K, id: TH-01}
  cooling_drag_area: {max: 0.002, unit: m2, id: TH-02}
```

Sem `bays`, o adaptador cria um compartimento `fuselagem` (área π·D·L) com a aviónica e, nos elétricos, a
bateria e o ESC. As condições por omissão são `solo_quente`, `subida_quente`, `cruzeiro_quente` e
`cruzeiro_frio`; a potência da bateria e o consumo de combustível vêm da tabela de segmentos da missão.

### 5.2 Especificação genérica (`acdt.api.thermal`) — qualquer tipo de aeronave

VTOL, jatos e híbridos que não passam pelo adaptador do pipeline usam a especificação direta (esquema
`acdt.thermal/1`): `conditions` (nome, `case` hot/cold, `atmosphere`, `altitude_m`, `V_m_s`, `solar_W_m2`),
`sources` (`heat_W` escalar, intervalo `[lo, hi]`, `null` = desconhecido, ou mapa por condição com `default`),
`bays` (como acima, mais `fan` com `mass_flow_kg_s`, `pressure_rise_Pa`, `efficiency`, `mass_kg`), `reference`
(`S_ref_m2`, `cruise_condition`) e `transient`. `acdt.api.thermal_atmosphere(perfil, altitude_m)` devolve a
atmosfera de projeto.

### 5.3 Acoplamento (`coupling: iterar`)

Dentro da etapa de dimensionamento: injeta `aero.extra_drag_areas_m2.arrefecimento_termico` (majorante do
arrasto), soma a massa conhecida de arrefecimento a `weights.fixed_mass_kg` e, só em aeronaves elétricas, a
potência do ventilador a `propulsion.systems_power_W`; repete até a variação de W0 ficar abaixo de `tol`
(histórico em `thermal.coupling_loop`). Grandezas desconhecidas não são acopladas e ficam listadas em
`not_coupled`.

Com power budget em malha fechada (bloco `systems`, `systems_integration.run_with_systems`) o valor de
`systems_power_W` é substituído pela média do balanço elétrico; por isso a potência do ventilador entra também como
carga `systems.loads` («ventilador de arrefecimento (acdt.thermal)», ciclo 1 — PRESSUPOSTO conservador: corre em
todo o cruzeiro quente). Antes desta correção (ramo `fix-acoplamento-termico`) a potência perdia-se em silêncio
nesses projetos; o teste de regressão
`test_thermal_iterar_fan_power_survives_closed_loop_power_budget` confirma que o W0 sobe com a potência do
ventilador.

## 6. V&V (`acdt vv --discipline termica`)

| Caso | Referência | Calculado | Tolerância |
|---|---|---|---|
| THERMAL-INC-EX5.1 | Incropera Ex. 5.1: D = 0,706 mm, t = 5,2 s | 0,7059 mm; 5,165 s (Bi ≈ 0,0024 < 0,1) | 0,0005 mm; 0,05 s |
| THERMAL-INC-EX7.1 | Ex. 7.1: q′ = 570 W/m | 570,47 W/m | 0,5 % |
| THERMAL-INC-EX9.2 | Ex. 9.2: q = 1060 W | 1060,05 W | 0,5 % |
| THERMAL-INC-EX8.6 | Ex. 8.6: q″ = 304 W/m², T_s,L = 50,7 °C | 304,33 W/m²; 50,72 °C | 0,5 %; 0,15 °C |
| THERMAL-MIL310 | nós das tabelas MIL-HDBK-310 | exatos | exato |
| THERMAL-AIR-PROPS | Incropera Tabela A.4 (300 K): μ, k, Pr | dentro da tolerância | μ 0,5 %; k e Pr 1 % |

Testes: `tests/test_thermal.py` (V&V, fecho do balanço de energia, ordem dos limites, transitório contra a solução
analítica exponencial, cadeia elétrica e majorante partilhado, motor térmico, conduto, avaliador, pipeline elétrico
com acoplamento iterado e pipeline a gasolina).

## 7. Seguimentos

* Adaptadores nativos VTOL/jato no pipeline (hoje pela especificação genérica).
* Perdas do gerador híbrido a partir do bloco `onboard`; potência do ventilador acoplada em aeronaves com motor
  térmico (via `onboard`).
* Efeito Meredith e arrasto externo da entrada (dados NACA de entradas submersas).
* Dados de capacidade térmica por componente; permutadores líquidos; irradiância solar em altitude.
* Alta fidelidade: proposta em [proposta-termica-gelo.md](proposta-termica-gelo.md), sem malha e sem corrida. O L0/L1 não fica validado por essa proposta.
