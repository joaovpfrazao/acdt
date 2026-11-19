# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0

# Proposta: térmica e gelo de alta fidelidade

Estado em 18 nov 2026, ramo `termico-gelo-proposta`. Nada foi corrido. Não se escreveu malha.
O L0 e o L1 não ficam validados nem calibrados. A comparação fica `nao_avaliado`. Decisão
`nao_aplicar`. O yaml dos exemplos não muda.

Registo: `examples/output/termico_gelo_proposta/proposta.json` e `proposta.csv`.

## Térmica

O L0/L1 é a rede de dois nós de [TERMICA.md](TERMICA.md) (Incropera, conduto NACA RM A8I29).
O exemplo já publicado no HANDOFF dá, no compartimento declarado, 50–52 °C em cruzeiro e
64–70 °C na subida e no solo. Esses números não foram recalculados aqui.

Malha. Não há sólido da baía. A contagem de células fica em falta, e em falta não é zero.
Se um sólido existir, a pele exterior pode usar `first_cell` com y+ = 1, a receita já em
`hifi/cfd.py`. O ar interior e a condução na parede não têm receita neste repositório.

Solver. O candidato externo é o `SU2_CFD`, em processo separado, sem importação. Os `.cfg`
já escritos põem `MARKER_HEATFLUX = 0`. Uma parede adiabática não é o balanço do
compartimento, por isso não serve de comparação. Não há caso conjugado no repositório.
O OpenFOAM está em `THIRD_PARTY.md` como GPL-3.0 e é um stub: também só como processo
separado, e não foi arrancado.

Custo. Sem malha não há GB nem horas. `tools.budget` continua a recusar uma estimativa
acima de 70 % da RAM livre ou de 45 min. Não se inventou uma contagem para passar essa guarda.

## Gelo

O L0/L1 é o da linha de estagnação em [GELO.md](GELO.md): 14 CFR 25 Apêndice C via Jeck,
Langmuir e Blodgett, Messinger via Anderson, NASA/CR-2004-212875. O exemplo já publicado
tem 14,1–57,2 mm no estabilizador e 11,3–45,4 mm na asa. Não foi recalculado.

Malha. Não se escreveu malha do bordo de ataque limpo nem da superfície com acreção.
Os casos `ICING-AND-B1`, `ICING-AND-B2` e o raio do NACA 0012 continuam a ser o V&V L1,
sem volume. O Apêndice O fica de fora: as tabelas não estão verificadas e um SLD em falta
não é zero.

Solver. O LEWICE já é a referência citada do desvio de β₀. Não está em `THIRD_PARTY.md`,
a licença não está neste repositório, e não foi instalado nem importado. Uma corrida futura
seria um processo separado. As formas medidas da NASA IRT não estão no repositório, por isso
essa comparação fica `nao_avaliado`.

Custo. A mesma regra da térmica: sem malha, o custo fica `nao_avaliado`.
