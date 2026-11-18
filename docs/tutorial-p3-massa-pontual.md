# Tutorial — P3: simulador de missão em massa pontual (N0/N1)

O mesmo ficheiro de missão corre em duas fidelidades. A massa pontual é o juiz enquanto ainda não há
forma, ou quando a forma já foi dimensionada mas ainda não vale a pena o 6-DOF. O 6-DOF (piloto
automático, Dryden, rajadas) continua a ser a omissão de `acdt simulate` e está no
[tutorial da Fase 8](tutorial-fase8-simulador.md).

A regra é a de sempre: métodos citados, nenhum número inventado, e cada omissão marcada como
**PRESSUPOSTO**.

## 1. O que cada fidelidade faz

| | massa pontual | 6-DOF |
|---|---|---|
| Equações | equilíbrio de Anderson 1999 Cap. 5 e Raymer 2018 Cap. 17; posição por Euler explícito | Stevens & Lewis, piloto de Beard & McLain |
| Avião | bloco `aircraft` (N0) ou o resultado de `size` (N1, sem modelo de voo AVL) | tabelas AVL do projeto dimensionado |
| Vento | só o vento constante (triângulo de velocidades, Anderson Cap. 3) | constante + Dryden + rajadas 1−cos |
| Falhas | a resposta é voada (continua, regresso, desvio) | a falha é registada e a trajetória não muda |
| Passo | `pointmass_dt` (omissão 1 s) | `dt` (RK4) |

A aceleração ao longo da trajetória não é integrada: a velocidade do segmento é imediata (PRESSUPOSTO).
Terra plana, sem terreno, polar parabólica. A deteção é oportunidade de busca (esforço de varrimento),
não a curva do fabricante.

## 2. Comandos

```bash
# N0 — sem projeto. O YAML traz o bloco aircraft. Não precisa de AVL.
acdt simulate examples/simulation/n0_patrol.yaml --fidelity pointmass -o output/n0_patrol

# N1 — polar, propulsão e massa do dimensionamento. O bloco aircraft, se existir, é ignorado.
acdt simulate examples/cessna172_check.yaml examples/simulation/c172_check.yaml --fidelity pointmass

# N2 — 6-DOF (omissão). Precisa de AVL. --layout e --jsbsim são só desta fidelidade.
acdt simulate examples/cessna172_check.yaml examples/simulation/c172_check.yaml --fidelity 6dof
```

Na ferramenta MCP o argumento é `fidelity` (`pointmass` ou `6dof`) de `simulate_mission`. Sem um projeto,
a massa pontual exige o bloco `aircraft` na missão ou o argumento `aircraft`. Esse bloco substitui os
pressupostos de dimensionamento: a corrida regista que os DEFAULT_ASSUMPTIONS não foram usados.

Os números de `examples/simulation/n0_patrol.yaml` são **PRESSUPOSTO** (não são uma aeronave real).
Trazem uma patrulha curta, um sensor e o esquema de falhas em comentário, para o exemplo chegar ao fim.

## 3. Missão

Os tipos são os do 6-DOF, mais `patrol` (a mesma órbita que `loiter`, contada como tempo em estação):

`takeoff`, `climb`, `cruise`, `turn`, `waypoints`, `loiter`, `patrol`, `descent`, `landing`.

* A subida em voo usa a tração de cruzeiro (η de cruzeiro). `eta_climb` só entra na descolagem de Raymer 17.8.
* Sem `speed_m_s`, a velocidade é a de (L/D)max ou de potência mínima (Anderson Cap. 5), com chão de
  1,2 V_S. O 6-DOF, em vez disso, reutiliza a velocidade anterior com chão de 1,3 V_S.
* Uma descida sem rampa pedida é o planeio em (L/D)max: o alcance em ar calmo é a altura vezes (L/D).
* A distância de descolagem e de aterragem é a de Raymer 17.8 e 17.9. O tempo da corrida de descolagem
  integra V̇ = g(K_T − K_A V²); não é uma segunda fórmula de distância.
* `eta_takeoff` em falta numa hélice faz a descolagem falhar. Não se aplica 0,80 por omissão.
* O orçamento `battery_Wh` ou `fuel_kg` já é o utilizável. Não se volta a aplicar a profundidade de
  descarga.

## 4. Sensor e falhas

O bloco `sensor` usa as primitivas que já existiam: pegada plana, horizonte (Skolnik 2001), alcance de
Johnson (1958), POD de Koopman e o ciclo de presença de Ha 2010 (`persistent.turnaround_h` é obrigatório
se o bloco existir). A faixa efetiva é a menor entre a pegada geométrica, o horizonte e o alcance de
Johnson no solo.

O bloco `failures` aceita `engine_out`, `sensor_loss`, `link_loss`, `fuel_degradation` e
`battery_degradation`, com `response` `continue`, `rtb` ou `divert`. O gatilho é um instante (`t_s`),
um segmento, uma altitude ou uma fração de combustível; os que estiverem escritos combinam-se com E.
`factor` multiplica o consumo de Anderson/Raymer a partir daí (cenário dado, não uma lei de
envelhecimento). `remaining_fraction` tira energia utilizável sem mudar a massa.

```yaml
failures:
  events:
    - {type: engine_out, t_s: 400, response: rtb}
  catalogue:
    - {type: sensor_loss, t_s: 500, response: continue, weight: 1}
  seed: 1          # obrigatório se houver catalogue; um sorteio, sempre o mesmo
```

Sem `seed`, um catalogue é recusado. Não há amostra de Monte Carlo.

## 5. O que sai

`mission_summary.json`, `mission_history.csv`, `mission_time_history.png` e `mission_ground_track.png`.
O resumo traz, além dos segmentos, `metrics` (tempo em estação, autonomia, alcance, área varrida, POD),
`sensor`, `failures` e a lista de notas, incluindo cada PRESSUPOSTO.

Num cruzeiro de 0,4 min do C172 a 50 m/s e 600 m, as duas fidelidades deram alcance e autonomia dentro
de 0,1 % (a tolerância publicada do teste é 15 %, a mesma banda do k_energia). Os valores estão no
HANDOFF, P3.

## 6. O que esta peça não faz

Resposta de falha em malha fechada no 6-DOF, Monte Carlo, geografia real, custo por hora de voo, chamada
automática de `compare_alternatives`, busca de barreira, trade de carga útil e arquitetura elétrica.
Ficam para as peças seguintes do workflow.
