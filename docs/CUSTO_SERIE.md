# Custo de produção em série (disciplina `custo_serie`, L0)

Estado em 18 nov 2026 (ramo `disc-custo-serie`). Código: `acdt/domains/aircraft/manufacturing/series.py` (estudo
genérico, mypy estrito), `acdt/domains/aircraft/series_cost.py` (etapa `series_cost` do pipeline) e
`acdt.api.series_cost` / `acdt.api.learning_curve` (desde a API 1.6.0).

Não há CER nova. Reutiliza o que já existia em `manufacturing.costing`: o Eastlake modificado (Gudmundsson 2014
Cap. 2, `cost.py`), o DAPCA IV (Raymer 2018 Cap. 18) e as curvas de aprendizagem de Crawford (unitária) e Wright
(média acumulada). Acrescenta lotes, amortizações, o varrimento em quantidade e o ponto de equilíbrio.

## 1. O que faz

* **Custo em função de N**: a CER (Eastlake ou DAPCA IV) é avaliada em cada quantidade do varrimento. Para cada N dá
  o RDT&E, as ferramentas, o custo recorrente, o custo unitário de saída de fábrica (*flyaway*), o custo unitário
  médio e as amortizações por unidade do RDT&E e das ferramentas.
* **Lote**: entre duas quantidades do varrimento, o custo recorrente incremental rec(N₂) − rec(N₁) e a sua média por
  unidade.
* **Rota de baixo para cima** (`method: learning`): custo recorrente da 1.ª unidade T1 (p. ex. do plano de fabrico
  `manufacturing.plan` com `hours_basis: first_unit`) com uma curva de aprendizagem. Dá o custo da unidade N, os
  lotes declarados (`lots: [2, 3, 5]`), a média, o NRE amortizado e o total.
* **Ponto de equilíbrio**: o menor N em que a receita P·N cobre o custo do programa(N), para o preço nominal
  (`price`) e para uma tabela de preços (`prices`).
* **Integração**: etapa `series_cost` do pipeline (depois da fiabilidade, antes do relatório) e secção
  `series_cost` no `result.json`. No `design.json` é a disciplina `custo_serie`/L0, com unidades `USD` pelas chaves
  `*_USD`. Os requisitos são `unit_cost_at_quantity`, `flyaway_cost` (ambos com qualificador `quantity`) e
  `break_even_quantity`, com o avaliador `custo_serie:<caminho>`. Para UQ e MDO, as métricas saem pelos caminhos
  `series_cost.*` (`result_metrics`). Há três casos V&V.

## 2. Métodos e fontes (cada equação conferida com a fonte)

| Peça | Método | Fonte |
|---|---|---|
| Expoente | b = log(S)/log(2), S = declive (0,9 → b = −0,15200) | FAA Pricing Handbook (1998) Cap. 18, Eq. 18-4 e exemplo |
| Curva unitária | T_n = T1 n^b; total do lote = Σ T_n (exato) | Crawford (1944); FAA Eq. 18-1/18-8 |
| Aproximação do lote | T1/(1+b) [(L+½)^(1+b) − (F−½)^(1+b)] | FAA Eq. 18-9 (lote com a 1.ª unidade) e 18-10 (lote F..L); Conway & Schultz (1959) |
| Média acumulada | Ȳ_N = T1 N^b; total = N Ȳ_N; lote = total(L) − total(F−1) | Wright (1936); FAA Eq. 18-2/18-7 e Caso 18-2 |
| Unidade implícita em Wright | T_n = T1 [n^(1+b) − (n−1)^(1+b)] | diferença dos totais da Eq. 18-7 |
| Ponto médio do lote | x tal que T1 x^b = média do lote | definição de *lot midpoint* (FAA Cap. 18; ICEAA CEBoK Mód. 7) |
| CER em N | Eastlake: horas de engenharia ∝ N^0,183, ferramentas ∝ N^0,178 Q_m^0,066, fabrico ∝ N^0,524, materiais ∝ N^0,792 | Gudmundsson (2014) Eq. 2.2–2.13 (já em `cost.py`) |
| | DAPCA IV: H_E ∝ Q^0,163, H_T ∝ Q^0,263, H_M ∝ Q^0,641, C_M ∝ Q^0,799 | Raymer (2018) Cap. 18 (já em `costing.dapca4`) |
| Equilíbrio | menor N com P·N ≥ C_programa(N) | definição; custos fixos/variáveis de Gudmundsson (2014) Cap. 2 |

**Decomposição RDT&E / produção (PRESSUPOSTO).** RDT&E = engenharia + apoio ao desenvolvimento + ensaios em voo.
Produção não recorrente = ferramentas. Produção recorrente = fabrico + controlo de qualidade + materiais + itens por
aeronave (motor, hélice, aviónica, extras). É a classificação fixo/variável que `CostBreakdown.fixed` e
`costing.dapca4` já usavam (Gudmundsson 2014 Cap. 2), com as ferramentas atribuídas à produção.

**Sem curva por cima da CER.** As horas e o material das CER já dependem de N, ou seja, a aprendizagem está embutida
nos expoentes de quantidade. Aplicar uma curva de aprendizagem ao resultado de uma CER contaria o efeito duas vezes.
A curva usa-se só na rota `learning`, a partir de uma 1.ª unidade.

**Cadência de produção.** Só entra o que o Eastlake já tem (ferramentas ∝ Q_m^0,066). Não há outro modelo de
cadência porque não encontrei uma fonte verificável.

## 3. Entrada (`assumptions.series_cost`)

```yaml
assumptions:
  series_cost:
    method: eastlake          # eastlake (omissão) | dapca4 | learning
    quantity: 200             # N nominal (omissão: assumptions.cost.N ou 500)
    quantities: [1, 10, 50, 100, 500]   # varrimento
    price: 150000             # preço de venda nominal (USD) → break_even_quantity
    prices: [50000, 100000]   # tabela N de equilíbrio vs preço
    n_max: 10000              # procura do equilíbrio até aqui
    dapca: {cpi: 1.2, FTA: 2, engine_cost: 20000}   # só method: dapca4 (We e V vêm do dimensionamento)
    learning: {T1: 18000, slope: 0.85, slope_source: "…", theory: crawford, nre: 2.5e6,
               per_aircraft_items: 4000, lots: [5, 20, 75]}             # só method: learning
requirements:
  unit_cost_at_quantity: {max: 40000, quantity: 100, id: CS-01}
  flyaway_cost: {max: 30000, quantity: 500, id: CS-02}
  break_even_quantity: {max: 300, id: CS-03}
```

Com `method: eastlake` as entradas são as mesmas do custo unitário do dimensionamento
(`sizing.eastlake_inputs`): massa da estrutura = fração × We, V_H = `max_speed` ou cruzeiro, motor, fração de
compósito e atuadores. Só N varia. A etapa só corre com `assumptions.series_cost` declarado ou com um dos três
requisitos; caso contrário fica «não avaliada».

## 4. Desconhecidos e validade

* Sem preço → `break_even_quantity = None` e o requisito fica **desconhecido**. Equilíbrio não atingido até `n_max`
  → `None` com o estado «não atingido» (nunca zero).
* Rota `learning` sem `nre` → o custo médio e o equilíbrio são **limites inferiores**: num requisito `max` o custo
  médio nunca passa, e o equilíbrio fica `lower_bound_quantity`.
* Declive sem `slope_source` → nota PRESSUPOSTO.
* Validade do Eastlake: aviação geral (Part 23/CS-23). Num UAS é extrapolação e fica uma nota; nesse caso prefira a
  rota `learning`. O DAPCA IV vem de aeronaves militares e de transporte.
* Moeda: USD de 2012 × `cpi` (CER). Na rota `learning`, T1 e NRE declaram-se em USD. Não há conversão cambial.

## 5. V&V

| Caso | Referência | Tolerância |
|---|---|---|
| CS-FAA18-SLOPE | FAA Pricing Handbook Cap. 18: S = 0,9 → b = −0,15200; 2 unidades: 190 (unitária) vs 180 (média acumulada) | 5×10⁻⁵; exato |
| CS-FAA18-CUMAV-LOT | idem Caso 18-2: Y = 103,45 X^−0,04, lote 11–15 = 1392 − 943 = 449 h | 1 h (totais intermédios arredondados) |
| CS-FAA18-UNIT-APPROX | idem Caso 18-2: Y = 102,73 X^−0,15, lote 1–2 ≈ 196 h (Eq. 18-9), lote 11–15 ≈ 350 h (Eq. 18-10); soma exata 350,0 | 0,5 h |

Testes: `tests/test_series_cost.py`. Eles confirmam que a decomposição reproduz o custo unitário do Eastlake e o
programa do DAPCA, a tendência com N, os lotes, o equilíbrio (incluindo «não atingido»), a forma fechada de Wright,
os desconhecidos, a API e a etapa do pipeline com requisitos e `design.json`.

## 6. Acoplamentos e o que falta

* **Acoplamentos**: lê o projeto dimensionado (We, V, motor, compósito). Não muda W0. Alimenta o ciclo de vida
  (RDT&E, aquisição).
* **Falta**:
  * ligar T1 automaticamente ao plano de fabrico (`manufacturing.plan`; hoje T1 é declarado);
  * curvas com degraus (alterações de projeto a meio da série, FAA Cap. 18, «step functions»);
  * modelo de cadência com fonte;
  * custo de RDT&E distribuído no tempo (isso fica no ciclo de vida).
