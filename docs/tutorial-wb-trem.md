# Tutorial — peso e centragem operacional e trem de aterragem

Isto corre dentro de `acdt size`. Não há comando novo nem ferramenta MCP nova (continuam 30).

O que já existia na estabilidade — quatro casos discretos de CG, estações e a asa colocada para a margem
estática alvo — mantém-se. Este passo acrescenta o diagrama de carregamento e o trem ao lado desse trabalho.
As verificações `wb:` e `gear:` aparecem no relatório e em `result.json`, e **não** mudam `feasible` da Fase 1.

## 1. O que é calculado

**Carregamento** (Raymer 2018 Sec. 15.1; Roskam Parte II 1985 Cap. 10):

* cada item fixo, variável ou de combustível entra com massa mínima e máxima;
* os vértices da caixa de carregamento, a face do MTOW e o caminho de queima de combustível;
* o CG é Σ(m x) / Σ m. Com um só depósito, os extremos da queima chegam; com vários, a mudança de depósito
  é um vértice.

**Limites**, se o YAML não os der:

* traseiro: ponto neutro menos a margem estática alvo (Raymer Cap. 16);
* dianteiro: o mais à ré de dois trimagens com o profundor no batente (Nelson 1998 Cap. 2). O caso limpo
  usa a CLmax sem flaps e o Cm0 da asa (Raymer Eq. 16.13). O flare de aterragem usa a CLmax com flaps e
  soma o Cm0 da fuselagem (Multhopp; k₂−k₁ de Lamb, NACA Report 139) e o momento do flap. O efeito de
  solo não entra.

São limites aerodinâmicos de projeto conceptual, não um envelope certificado. Se só um lado for calculável,
só esse lado é verificado. x cresce para trás: o limite dianteiro é o menor x permitido.

**Trem** (Raymer 2018 Cap. 11; Currey 1988; 14 CFR 23.473 na eCFR de 25 de julho de 2017):

* triciclo: o trem principal fica atrás do CG mais traseiro de um ângulo de 15° com a vertical; a capotagem,
  medida no CG dianteiro, não passa de 63°; o nariz leva 8–15 % do peso nesse intervalo;
* convencional: os principais ficam à frente do CG dianteiro pelos mesmos 15°; a capotagem mede-se na roda
  de cauda e o CG crítico é o traseiro; a banda de 8–15 % é só do triciclo;
* velocidade de descida V = 4,4 (W/S)^(1/4) ft/s, com W/S em lb/ft², entre 7 e 10, no peso de aterragem de
  projeto;
* a sustentação da asa pode ir até 2/3 do peso; o fator de inércia de projeto é pelo menos 2,67 e a reação
  no solo pelo menos 2,0;
* o curso é o que desenvolve o `gear_load_factor` já usado nos pesos (Raymer Tabela 11.5, 3,0 para aviação
  geral, por omissão), depois desses pisos. O balanço de energia é o de Currey 1988 §5.3:
  η_s N S + η_t N S_t = V²/(2g) + (1−κ)(S+S_t). O termo de sustentação divide-se por η. Eficiência do
  óleo-pneumático 0,80 e do pneu 0,47 (Raymer Cap. 11). O pneu só entra se `tire_stroke_m` for dado.

## 2. Como pedir

No bloco `assumptions` da missão. Comprimentos do trem, `gear_load_factor` e `landing_weight_fraction`
ficam em `weights.components`, porque as equações de peso já os usam.

```yaml
assumptions:
  weights:
    components:
      landing_gear: tricycle      # tricycle | taildragger | ski | none
      gear_load_factor: 3.0
      landing_weight_fraction: 0.95
      main_gear_length_m: 0.60     # PRESSUPOSTO; Raymer Eq. 15.50 recebe o comprimento como dado
  weight_balance:
    # opcional: limites fixos, em metros a partir do datum. Sem isto, usam-se os limites aerodinâmicos.
    # x_forward_m: 1.90
    # x_aft_m: 2.20
    # forward_limit: [[800, 1.80], [1200, 2.00]]   # [[massa_kg, x_m], ...]
    # aft_limit: [[800, 2.30], [1200, 2.15]]
    extra_items: []                # [{name, x_m, mass_max_kg, mass_min_kg, kind, fuel_order}]
  landing_gear:
    h_cg_m: null                   # null: comprimento do trem principal + metade do diâmetro da fuselagem
    tipback_deg: 15
    overturn_max_deg: 63
    nose_fraction_min: 0.08
    nose_fraction_max: 0.15
```

```powershell
acdt size examples\cessna172_check.yaml -o out\c172
```

No ecrã saem duas linhas, uma de peso e centragem e outra de trem. No relatório, a secção
**12a. Peso e centragem operacional e trem de aterragem** fica entre a estabilidade (§12) e o desempenho
(§13), com `wb_loading.png`. Em `result.json` os resumos estão em `weight_balance` e `landing_gear`.

`landing_gear: none` (os UAV de lançamento por catapulta ou rede) não gera verificações de trem. O
carregamento continua a ser calculado.

## 3. O que a matriz de conformidade recebe

| parágrafo | evidência | quando não há trem | quando a geometria falha | quando o curso é dimensionado e cabe |
|---|---|---|---|---|
| 23.2100 | `wb_cg` | o carregamento continua a contar | não conforme se o CG sai dos limites | — |
| 23.2220 e USAR.471 | `ground_loads` | em aberto | — | requer ensaio (o meio de conformidade inclui ensaio) |
| 23.2305 | `landing_gear` | em aberto | não conforme | requer ensaio se a geometria passa |

O texto da matriz é paráfrase. A fonte oficial continua a ser o URL do catálogo.

## 4. Limites deste passo

* As estações de estrutura são as de Roskam (Parte V, Tabela 8.1) até serem substituídas. Não são um
  layout medido. Tripulação, carga e bateria, se a missão não as der, ficam no CG da massa fixa
  (Raymer 2018 Sec. 15.1, referência `balance`): um item aí não desloca o balanço, por isso não
  alarga o diagrama. Num UAV com massa de tripulação nula não há tripulação. O combustível de asa
  fica a 30 % da CMA. `weight_balance.loading`
  substitui esses montantes: `arm_in` são polegadas atrás da firewall (datum do POH). O C172S usa os
  braços da Secção 6 do POH (bancos 37 e 73 in, bagagem 95 e 123 in, combustível nas asas a 48 in).
* O CG de cada depósito é um ponto fixo. Não há deslocamento dentro do tanque nem separação do combustível
  inutilizável.
* 0,95 W0 é o mínimo que 23.473(b) permite. O código **não** demonstra a cláusula de combustível.
* O entre-eixos fica na banda de Raymer (Cap. 11): entre `(dx+ΔCG)/0,15` e `dx/0,08`, o mais longo que
  mantém o nariz em `x ≥ 0` e o principal dentro da fuselagem. Se nenhum valor da banda cabe, não se
  publica uma roda à frente do avião: `gear:position` falha e as estações ficam por preencher. Dê
  `x_nose_m` e `x_main_m` se a posição já estiver decidida. `x_main_m` sozinho é usado, com aviso, e a
  roda de nariz sai da mesma banda.
* Não entram: spin-up, spring-back, carga lateral, travões, ressalto e rolagem. A fração estática no nariz
  não é a distribuição de uma aterragem nivelada certificada. Por isso 23.2220 não fica conforme só com este
  passo.
* Se o curso é calculado e cabe em `max_stroke_m` (ou esse teto não foi dado), o fator de carga fica por
  decidir: há um valor, não uma declaração de cumprimento. Fica falso se o utilizador deu o curso e a
  energia pede mais do que `gear_load_factor`, ou se o curso necessário passa `max_stroke_m`.
* O curso sem sustentação da asa (κ = 0) é reportado à parte e é maior. κ acima de 2/3 é cortado a 2/3,
  com uma nota.
* `h_cg`, quando não é dado, repete o pressuposto do simulador: comprimento do trem principal mais metade
  do diâmetro da fuselagem, com o CG no plano de simetria. Sem `main_gear_length_m`, esse comprimento é
  0,60 m (PRESSUPOSTO). Sem `x_tail_m`, a roda de cauda fica a 0,95·L (PRESSUPOSTO).
* A face de MTOW do diagrama conserva um canto até 0,05 kg acima de m_max (PRESSUPOSTO de fecho numérico).


## 5. Montagem (opt-in, 9 nov 2026)

No JSON/YAML de montagem, `gear.type` pode ser `tricycle`, `taildragger` (aliases `conventional` /
`tailwheel`) ou `ski`. Métodos: Raymer Cap. 11, Currey 1988, 14 CFR 23.925 (7 in triciclo / 9 in
cauda). `draw_legs: true` acrescenta corpos `gear_leg`; `retract: {main: {hinge, axis, angle_deg}}`
verifica o arco do centro da roda. Sem `ski.length_m` ou sem trajectória → **unassessed**. Exemplos:
`examples/integration/conventional_taildragger.json`, `ski_gear_demo.json`.
