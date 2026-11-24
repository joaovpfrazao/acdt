# Rajada lateral do caso «cheio»: estudo de decisão (applied: false)

Gerado a 23 nov 2026 por `python examples/studies/rajada_cheio/estudo_rajada_cheio.py`, sobre
`examples/heavy/uav150_flying_wing_tailless.yaml` sem alterações (W0 149,7 kg, cerca de 190 s). Corrido duas vezes,
com resultados iguais. Nada é aplicado ao exemplo. A tabela e a recomendação estão em
docs/tutorial-asa-voadora-sem-deriva.md §5, e a decisão é do João.

`opcao_a.json` (24 nov 2026): redimensionamento com a opção (a) escolhida pelo João, gerado por
`python examples/studies/rajada_cheio/estudo_opcao_a.py` (cerca de 8 min; base e opção a correm com o mesmo código).
É `applied: false` e só usa os `fixed` de `examples/studies/rajada_cheio/opcao_a.yaml`, aplicados em memória.
Resumo e tabela em docs/tutorial-asa-voadora-sem-deriva.md §5.1.

`opcao_a.json` foi regenerado a 24 nov 2026 com o toque convergido no passo (docs/tutorial-asa-voadora-sem-deriva.md §5.2). Só os números do toque na missão 6-DOF mudaram.

`consolidado.json` (24 nov 2026): opção (a) com as pernas a 1,3 × 23.485, gerado por
`python examples/studies/rajada_cheio/estudo_consolidado.py` (cerca de 8 min; exemplo, opção (a) e consolidado correm
com o mesmo código). É `applied: false` e usa os `fixed` de `consolidado.yaml` e `opcao_a.yaml`, aplicados em
memória. Tabela em docs/tutorial-asa-voadora-sem-deriva.md §5.4.
