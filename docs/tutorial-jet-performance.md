<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Jatos L0 — descolagem, subida e OEI (7 nov 2026)

**Triagem de engenharia, nunca dados para voo ou conformidade CS-25.**

```sh
acdt jet performance --input examples/jet/performance_l0.yaml -o out/jet_performance.json
# O mesmo bloco opcional também funciona em:
acdt jet size --input examples/jet/performance_l0.yaml -o out/jet_size_performance.json
```

MCP: `jet_performance(spec, record=true)`; regista entradas, pressupostos, commit,
versões e JSON em `runs/` (ou `ACDT_RUNS_DIR`). Exige um bloco `performance` explícito.
Primeiro fecha a massa de `jet_size`; depois usa essa MTOW na corrida AEO e a
massa `MTOW × mass_fraction` em cada ponto de subida. As massas das fases são
**PRESSUPOSTOS** declarados, não uma trajetória de descolagem integrada. Não se
altera a queima Raymer da missão, nem se redimensionam motores/asa ou escolhem alternativas.

## Entradas explícitas

`performance.ground` (opcional): `altitude_m`, `liftoff_speed_m_s` (TAS declarada,
**não** VLOF validada), `cl_max`, `cl_ground`, `oswald`, `mu_roll`,
`delta_cd_flaps`, `delta_cd_gear`, `thrust_factor`.
Opcionais: `max_ground_run_m` (limite só da aceleração), `obstacle_height_m`,
`steps`=32 e `max_steps`=1024 (controlos numéricos PRESSUPOSTO).

`performance.climb_points` (opcional, pelo menos um cenário no bloco): lista com
`name`, `altitude_m`, `speed_m_s` (TAS), `mass_fraction`, `cl_max`, `oswald`,
`delta_cd_flaps`, `delta_cd_gear`, `delta_cd_windmilling`, `delta_cd_oei_trim`,
`thrust_factor`; opcionais `min_aeo_gradient`, `min_oei_gradient` (frações, 0,024 =
2,4%) e `reference_clause` (`25.121(a)` a `(d)`). Não há coeficientes de flap,
trem, motor parado ou trimagem preenchidos com zeros ocultos: todos são dados.
Zero declarado também é PRESSUPOSTO se não houver fonte/validação.

A área/alongamento, CD0 limpo e opções do deck vêm do candidato de `jet_size`.
Cada configuração declara o seu e. `thrust_factor` multiplica o empuxo disponível
do deck; não é um mapa validado de rating contínuo, derate, FLEX ou throttle.
O exemplo usa valores hipotéticos de arrasto e rating, identificados em
`assumption_sources`; não são dados de um A320. μ=0,02 é um valor aproximado para
pavimento seco da tabela pública ERAU, não uma propriedade garantida da pista.

## Métodos e saídas

- Corrida AEO: `m dV/dt = T(V) − D(V) − μ(W−L(V))`; integra-se ds/dV e dt/dV.
  Empuxo instalado varia com Mach/altitude pelo turbofan existente. CL de solo é
  constante; peso nas rodas e força aceleradora têm de permanecer não negativos/
  positivos nos pontos avaliados. Não se cortam forças negativas para permitir uma passagem.
- Usa-se Simpson com duplicação de passos (erro estimado /15); tolerâncias
  numéricas max(0,01 m, 1e−5 distância) e max(0,001 s, 1e−5 tempo), não precisão física.
  O parâmetro u=sqrt(V/Vfinal) regulariza a dependência sqrt(M) do deck.
- Subida retilínea estacionária: `T−D=W sinγ`, `L=W cosγ`, polar parabólica.
  Resolve-se o ramo quadrático regular, sem forçar γ positivo; gradiente=tanγ e
  razão de subida=V sinγ. OEI remove **um** motor, soma arrasto de windmilling/
  trimagem declarado e não presume controlo direcional demonstrado.
- Triagem conservadora de sustentação pela velocidade de perda de voo nivelado.
  Domínio implementado: ISA, 0≤h≤15 km, 0<M≤0,3 nos pontos de voo; pista plana,
  vento nulo, motores idênticos, sem crédito de efeito de solo. A polar Korn de
  cruzeiro não é extrapolada para CL elevados de descolagem.
- `ground.distance_m` é apenas aceleração até à velocidade declarada. Rotação e
  transição não são modeladas; `full_takeoff_distance_m` fica **nulo**. A distância
  retilínea idealizada `altura/gradiente` não é distância de descolagem nem prova
  de passagem de obstáculo. Não se soma às escondidas uma distância de transição zero.

Cada ponto de subida fornecido é testado para subida AEO/OEI positiva (objetivo
físico de triagem) e para os mínimos de engenharia que o estudo declare. Ponto
fora do domínio, sem sustentação, sem aceleração ou sem convergência não passa.
Se a massa não convergir, a secção fica `unassessed`, sem avaliação com massa fictícia.

## Contrato aditivo e certificação não avaliada

Sem `performance`, o resultado antigo de `jet_size` não muda. Com o bloco,
acrescentam-se `performance.schema_version: 1.0`, `screening_issues` e
`combined_requested_checks_passed`. O campo antigo `feasible` **continua limitado
a massa/cruzeiro/MTOW**, não inclui a triagem opcional. O novo booleano combina
só os checks de engenharia solicitados; **não demonstra viabilidade completa**.
CLI termina com 1 se algum destes checks falhar, mesmo que `feasible` antigo
seja verdadeiro; 2 para entradas inválidas; 0 significa apenas esses checks passaram.

14 CFR 25.121(a)–(d) fornece tabelas numéricas de gradientes por 2/3/4 motores;
por exemplo (b): 2,4/2,7/3,0%. Em (a), para dois motores, a condição é estritamente
positiva, não ≥0. Contagens fora da tabela não recebem um mínimo inventado.
`regulatory_reference` mostra o limiar e margem, mas `passed` é **sempre nulo**,
mesmo quando `numerical_threshold_met=true`: VLOF/V2/VFTO, rating, configuração,
motor crítico, gelo e condições de demonstração não foram estabelecidos.

Sem `performance.field`, continuam **não avaliados**: VEF/V1/VR/VMC; accelerate-stop;
balanced field; TOD completo. Com `field` opt-in (secção abaixo), ASD/TOD/BFL são
triagem numérica apenas — conformidade CS-25.109/.113 continua **unassessed**.
Permanecem por avaliar em qualquer caso: rotação/transição e trajetória contínua 25.111;
pista molhada/contaminada; trajetória líquida 25.115; VMCG de ensaio; gelo e dados AFM.
Não é uma verificação CS-25, nem o simulador como juiz comum do DESIGN_WORKFLOW.

## Fontes abertas nesta implementação (consulta: 7 nov 2026)

- ERAU, *Introduction to Aerospace Flight Vehicles*, “Takeoff & Landing Performance”,
  análise de descolagem eqs. 1–8:
  https://eaglepubs.erau.edu/introductiontoaerospaceflightvehicles/chapter/takeoff-landing-performance/
- ERAU, “Climbing, Ceiling & Gliding”, equilíbrio de subida eqs. 3–4:
  https://eaglepubs.erau.edu/introductiontoaerospaceflightvehicles/chapter/climbing-ceiling-gliding/
- Raymer §17.8, transcrição pública do caso de corrida (eqs. 17.102–104):
  https://computationaldesignlab.github.io/aircraft-design/performance/takeoff.html
- https://www.law.cornell.edu/cfr/text/14/25.121
- https://www.law.cornell.edu/cfr/text/14/25.111
- https://www.law.cornell.edu/cfr/text/14/25.113
- https://www.law.cornell.edu/cfr/text/14/25.115

## Campo de descolagem opt-in (`performance.field`, 9 nov 2026)

Com `ground` presente, o bloco `field` calcula:

* **TOD AEO** — corrida até VLOF + distância aérea ao ecrã (gradiente estacionário a V2);
  aplica o fator 115 % de 25.113(a)(2) **só numericamente**;
* **ASD** — aceleração AEO até V1, atraso de reconhecimento ≈ V·Δt, travagem com μ_brake
  (sem crédito de reversão salvo `thrust_reverse_factor` > 0);
* **TOD OEI** — AEO até V1, depois OEI até VLOF + subida a V2 com arrasto de windmill/trim;
* **BFL** — procura de V1 que equilibra ASD e TOD OEI (construção Krenkel/Salzman/Roskam/Torenbeek).

V2/VMC/VR/VLOF são entradas explícitas. Sem VMC, o piso de V1 fica **unassessed**
(unknown≠pass). Pista molhada, VMCG de ensaio e conformidade CS-25 continuam por
avaliar. Rotação/transição: ver secção seguinte. Exemplo sem RT:
`examples/jet/performance_field.yaml`.


## Rotação e transição opt-in (10 nov 2026)

Com `include_rotation_transition: true` o TOD AEO/OEI (e portanto o BFL) passa a
incluir segmentos clássicos de triagem (Roskam Part I / Torenbeek):

* rotação: \(s_R = \tfrac12(V_R+V_{\mathrm{LOF}}) t_R\) — `rotation_time_s` obrigatório;
* transição circular: \(R = V_{\mathrm{LOF}}^2 / [g(n-1)]\), `transition_load_factor` \(n>1\);
* subida residual até à altura de ecrã se \(h_{tr} < h_{\mathrm{screen}}\).

`vr_m_s` é obrigatório neste modo. Em falta → `tod_*` **unassessed** (nunca um
airborne de comprimento zero que encurte o campo). Omissão da flag = saída idêntica
à do PR #25. CS-25.111/.113/.115 e VMCG de ensaio permanecem unassessed.

```bash
PYTHONPATH=src acdt jet performance --spec examples/jet/performance_field.yaml
PYTHONPATH=src acdt jet performance --spec examples/jet/performance_field_rotation.yaml
```

Números ilustrativos PRESSUPOSTO (mesmo spec, L0): sem RT TOD_AEO ≈ 1370 m;
com \(t_R=2\,\mathrm{s}\), \(n=1.2\) TOD_AEO ≈ 1665 m (Δ ≈ +296 m; \(s_R=158\,\mathrm{m}\)).
