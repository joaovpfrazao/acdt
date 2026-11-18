# Tutorial VTOL / eVTOL — L0 (pairar, transição, arquiteturas)

## Ideia

Primeira fatia L0 para VTOL e eVTOL: potência de pairar pela teoria da quantidade de movimento
(disco atuador), energia da missão, massa de bateria e comparação de arquiteturas
(multirrotor, lift + cruise, tilt-rotor) à **mesma massa e missão**.

## Métodos

* Pairar: P_ideal = T^(3/2) / √(2ρA), v_h = √(T/(2ρA)); P = P_ideal / FM (Johnson, *Helicopter Theory*, 1980,
  Cap. 2; Leishman, *Principles of Helicopter Aerodynamics*, 2.ª ed., 2006, Cap. 2).
* Subida axial: P = T (V_c/2 + √((V_c/2)² + v_h²)) / FM (Leishman 2006 §2.6).
* Transição (asa): varrimento 0 → V_asa com aceleração constante; a asa suporta W (V/V_asa)², os rotores o resto,
  com o escoamento induzido de Glauert (Leishman 2006 §2.14). Tilt-rotor com penalização de conversão 1,10.
* Cruzeiro: P = W V / (L/D · η_p) (Raymer 2018 §17.2).
* Bateria: E_nom = E (1 + reserva) / DoD (Hepperle 2012, mesma convenção do `acdt size`);
  massa = max(E_nom / Wh/kg, P_pico / (C_máx · Wh/kg)).
* Referência de métodos eVTOL: NDARC (Johnson, NASA/TP-2015-218751) e Johnson, Silva & Solis 2018
  (só referência, nada importado).

## PRESSUPOSTOS por omissão

FM 0,70 (gama 0,5–0,8), η_motor 0,85, η_ESC 0,95, pacote 180 Wh/kg, reserva 20 %, DoD 0,8, C máx 6,
T/W máx 1,5, Mach de ponta 0,6, solidez 0,10, C_T/σ máx 0,13, fração de bateria máx 0,40.
Por arquitetura: carga de disco, L/D, η_p, fator de *download*, tempos de transição
(`acdt.domains.aircraft.vtol.size.ARCHITECTURES`). O JSON de saída lista em `pressupostos`
tudo o que ficou por omissão.

## CLI

```bash
export PYTHONPATH=src

# ponto de pairar
acdt vtol hover --mass 5 --n-rotors 4 --diameter 0.38 --fm 0.65 -o /tmp/hover.json

# uma arquitetura
acdt vtol size --input examples/vtol/quadrotor_inspection.json -o /tmp/quad.json
acdt vtol size --input examples/vtol/lift_cruise_25kg.yaml -o /tmp/lc.json

# comparar arquiteturas (mesma massa e missão)
acdt vtol compare --input examples/vtol/lift_cruise_25kg.yaml -o /tmp/cmp.json
```

## MCP

`vtol_hover`, `vtol_size`, `vtol_compare`.

## Fecho de massa opt-in (`closure`)

Sem `mass_kg` e com um bloco `closure`, `vtol size` resolve o MTOW m de m = Σ mᵢ(m) por bisseção com
mudança de sinal dentro de `mass_bounds_kg` (Burden & Faires 2011 §2.1). Cada tentativa recalcula a
missão nativa (pairar, potência de pico, bateria, diâmetro se for dada carga de disco).

| componente | métodos | notas |
|---|---|---|
| `rotors` | `AFDD00` (NDARC Cap. 27-2: pá + cubo; `n_blades`, `flap_frequency_per_rev`, χ opcionais) ou `supplied` | R e V_ponta do pairar nativo; corda c = σπR/N_b; f_tilt = 1,17940 só em tilt-rotor; **extrapolação** marcada |
| `motors` | `NASA15` (NDARC Cap. 22-4, binário de pico Q = P_pico/Ω; `torque_class` explícito) ou `supplied` | um motor por rotor, transmissão direta PRESSUPOSTO (`gear_ratio`); classe verificada (Q/W > 3,5 ft·lb/lb) |
| `controllers` | `fraction_of_motor` (com fonte) ou `supplied` | NDARC cita 10–30 %, até 70 % em motores pequenos — só contexto |
| `rotor_support` | `fraction_of_mtow` (forma NDARC W_supt = f_supt W_MTO, f_supt fornecido) ou `supplied` | braços/pilones |
| `airframe` | `fraction_of_mtow` ou `supplied` (com fonte) | sem correlação citada para UAV pequeno |
| `tilt_mechanism` / `cruise_propulsor` | idem | obrigatórios em tilt-rotor / lift + cruise |
| `other`, `fixed_items` | listas de massas com fonte | `onboard_size` preenche `fixed_items` com os itens |

Componente obrigatório em falta → `incomplete_component_coverage` (nunca zero). Estados:
`converged`, `not_bracketed`, `max_iterations`, `outside_model_domain`. Verificações: fecho de massa,
verificações nativas (fração de bateria, taxa C, C_T/σ), consistência da classe de motor, `mtow_limit_kg`.

```bash
acdt vtol size --input examples/vtol/quadrotor_closure.yaml -o /tmp/vc.json
# → converged, MTOW 9,302 kg, 17 iterações, bateria 2,19 kg (limitada por potência) — números PRESSUPOSTOS
```

No estudo de frota 1.1, um candidato VTOL com `aircraft.closure` passa a ter fecho
dimensionamento↔capacidade (como prop/jato): o projeto é fechado no tempo de estação de projeto e a
capacidade é procurada com o MTOW e a bateria instalada fixos (`vtol_mass_closure` na saída).

## Limites (adiados)

* sem `closure`, massa dada (comportamento anterior); sem MDA do `acdt size`;
* BEMT axial/pairar é opt-in (`rotors.bemt` ou `acdt bemt rotor --input examples/vtol/bemt_hover_illustrative.json`):
  T=61,30 N, P=1077 W/rotor, FM=0,643 vs FM L0=0,70 (988 W) no mesmo disco de 0,50 m — polar EXAMPLE, não mapa
  de fornecedor. Sem geometria ou polar o estado é unassessed e a potência L0 não é um resultado BEMT.
  Continua em aberto: voo avançado, interferência rotor–rotor / rotor–asa (só fator de *download*);
* regressões NDARC (legado de helicópteros/tiltrotores) extrapoladas para eVTOL pequeno; mecanismo de
  basculamento, propulsor de cruzeiro e estrutura só por fração/massa fornecida;
* sem ruído, sem dinâmica/compensação da transição, sem caso OEI.
