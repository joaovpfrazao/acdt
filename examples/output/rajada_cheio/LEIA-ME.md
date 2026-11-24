# Rajada lateral do caso «cheio»: estudo de decisão (applied: false)

Gerado a 23 nov 2026 por `python examples/studies/rajada_cheio/estudo_rajada_cheio.py`, sobre
`examples/heavy/uav150_flying_wing_tailless.yaml` sem alterações (W0 149,7 kg, cerca de 190 s). Corrido duas vezes,
com resultados iguais. Nada é aplicado ao exemplo. A tabela e a recomendação estão em
docs/tutorial-asa-voadora-sem-deriva.md §5, e a decisão é do João.

`opcao_a.json` (24 nov 2026): redimensionamento com a opção (a) escolhida pelo João, gerado por
`python examples/studies/rajada_cheio/estudo_opcao_a.py` (cerca de 8 min; base e opção a correm com o mesmo código).
É `applied: false` e só usa os `fixed` de `examples/studies/rajada_cheio/opcao_a.yaml`, aplicados em memória.
Resumo e tabela em docs/tutorial-asa-voadora-sem-deriva.md §5.1.
