# Estrutura paramétrica L1: estudo em exemplos convencionais (applied: false)

Gerado a 24 nov 2026 por `python examples/studies/estrutura_parametrica/estudo_estrutura_parametrica.py` (cerca de
2 min). Liga `structure_layout` em memória em `examples/cessna172_check.yaml`, `examples/uav_150kg_stanag4671.yaml` e
`examples/uav_twin_boom_shortcut.yaml` (twin-boom, booms lidos da montagem);
os yaml ficam iguais. Por caso: `*_membros.csv` (tabela única de membros), `*_resumo.json` (orçamento de massa/CG/
inércia, comparação com a viga L1 e Raymer, cavernas pesadas), `*_vigas.json` (`acdt.beam/1`) e `*_vigas.bdf`
(texto tipo Nastran). Método e leitura em docs/ESTRUTURA_PARAMETRICA.md §5–6.

Ronda 3 (24 nov 2026): superfícies na posição real (asa alta, diedro, deriva no topo; caudas da montagem nos booms)
e escora da asa nos casos C172 (só em memória). Os novos casos `tailless`
(`examples/heavy/uav150_flying_wing_tailless.yaml`) e `inverted_v` (`examples/uav_inverted_v_shortcut.yaml`) só
servem para o render. Imagens: `c172_estrutura_3d*.png`, `twin_boom_estrutura_3d*.png`,
`tailless_estrutura_3d*.png`, `inverted_v_estrutura_3d*.png` (cor por tipo e por RF). docs/ESTRUTURA_PARAMETRICA.md §12.

