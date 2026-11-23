# UQ de demonstração com as disciplinas novas (applied: false)

Gerado em 23 nov 2026 por
`acdt uq examples/uav_endurance_payload.yaml --spec examples/studies/uq_disciplinas/uq_disciplinas.yaml -o examples/output/uq_disciplinas`
e `python examples/studies/uq_disciplinas/rastreio_postos.py examples/output/uq_disciplinas` (proveniência em
`provenance.json`). Dados de teste, não de projeto; o exemplo não muda. Análise em docs/INCERTEZA.md.

Regenerado a 23 nov 2026 depois da correção da térmica (PR #46): as 2 corridas falhadas ficam com «dimensionamento não
convergiu» em vez do erro NaN do `brentq`. Os números não mudam.
