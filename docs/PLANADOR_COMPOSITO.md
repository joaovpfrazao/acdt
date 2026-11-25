<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Planador em compósito — LS4 dimensionado pelo acdt e comparado com o avião real

Este estudo dimensiona um planador clássico em compósito com o acdt e compara o resultado com um avião real com dados
públicos: o **Rolladen-Schneider LS4** (Classe Standard, 15 m, GRP).

* Exemplo: `examples/benchmarks/ls4/ls4.yaml`.
* Dados de referência, com fonte e qualidade de cada número: `examples/benchmarks/ls4/reference_data.json`.
* Estudo (`applied: false`): `examples/studies/planador_ls4/` (`python examples/studies/planador_ls4/estudo_planador_ls4.py`, cerca de 2 min).
* Resultados: `examples/output/ls4/comparacao.md` e `comparacao.json`.
* Renders: `examples/output/ls4/estrutura_ls4_geometria_ls4.png` (tipo de membro) e `..._rf.png` (RF).
* Testes: `tests/test_sailplane_composite.py`.

## 1. Porquê o LS4

* Tem TCDS público da EASA (A.095, secção L) com massas, velocidades, centragem e a massa máxima das partes não sustentadoras.
* O manual de voo, a massa de referência da FAI (massa da asa, 128 kg), o Jane's e uma polar medida estão todos acessíveis.
* É um projeto "tradicional": casca de GRP em sanduíche com espuma, longarina com banzos de rovings UD, poucas nervuras,
  cauda em T e lastro de água nas asas.

## 2. Fontes

| chave | fonte | URL | qualidade |
|---|---|---|---|
| tcds | EASA TCDS A.095, secção L (LS4) | https://www.easa.europa.eu/en/downloads/7339/en | primária |
| fm | Manual de voo LS4 (TN 4049) | https://www.aeroclubdesardennes.be/assets/files/FM_LS4_TN4049.pdf | primária |
| fai_refmass | FAI, massas de referência (asa 128 kg) | https://www-2025.fai.org/sites/default/files/documents/8_1_3_a_refmass_bureau_edited.pdf | primária |
| janes | Jane's via Wikipedia | https://en.wikipedia.org/wiki/Rolladen-Schneider_LS4 | secundária |
| cumulus | polar a 320 kg ("Not Verified") | https://www.cumulus-soaring.com/store/polar-data-rolladen-schneider | terciária |
| spottingworld | dimensões do cockpit | https://plane.spottingworld.com/Rolladen-Schneider_LS4 | terciária |
| cs22 | EASA CS-22 Amdt 3 | https://www.easa.europa.eu/en/downloads/131414/en | primária |
| uiuc | perfis (FX 79-162/133 modificados) | https://m-selig.ae.illinois.edu/ads/aircraft.html | secundária |
| patching_wood | admissível de banzos GFRP (Janus) | https://journals.sfu.ca/ts/index.php/ts/article/view/708 | secundária |
| hoff_gratton | Hoff, Gratton & Gee 2010, massas pesadas (Std Cirrus) | https://ts.ostiv.org/index.php/ts/article/download/42/38/155 | secundária (análogo) |

## 3. O que foi acrescentado ao acdt

1. **Planador sem propulsão:** `requirements.propulsion_type: none` (W0 = We + carga; sem combustível) e polar de planeio
   (`acdt.domains.aircraft.glide`): (L/D)max = 1/(2√(CD0·K)), afundamento mínimo a CL = √(3CD0/K) (Anderson §5.4).
2. **CS-22** (`regulatory_category: cs_22`, `structures.regulation: cs_22`): fatores de carga da categoria U
   (+5,3/+4,0/−1,5/−2,65, CS 22.337), rajadas de 15 m/s a VB e 7,5 m/s a VD (CS 22.333), fator k e teto
   1,25(V/VS1)² (CS 22.341), VD mínimo (CS 22.335), massa máxima de 750 kg (CS 22.1).
3. **Alívio do lastro de água e partes não sustentadoras:** `structures.wing_relief_extra_kg` e `non_lifting_max_kg`
   (TCDS) — caso de flexão adicional, que governa no LS4 (M raiz 1,6× o caso a W0).
4. **Perfil da fuselagem** (`geometry.fuselage_profile`, quebras [x/L, R/Rmax], 0 < R/Rmax ≤ 1).
5. **Estrutura paramétrica em modo compósito monocasca** (`structure_layout.construction: composito_monocasca`, ver
   [ESTRUTURA_PARAMETRICA.md](ESTRUTURA_PARAMETRICA.md) §14): casca em sanduíche sem reforçadores, poucas cavernas,
   nervuras só nas estações declaradas, cauda em T (`surfaces.estabilizador.on_fin_tip`).
6. **Verificação de parede em sanduíche** (`acdt.core.structures.sandwich`): faces (compressão, tração, corte),
   encurvadura de flexão (Donnell com redução NASA SP-8007), de torção (SP-8007 com casca isotrópica equivalente),
   interação R_b + R_s² (Bruhn C8) e enrugamento (Hoff-Mautner).
7. **Bordos de ataque e de fuga em sanduíche** (`structures.secondary_skin: sanduiche`): faces mínimas + núcleo mínimo
   em vez de laminado simples à espessura mínima.
8. **Correção da viga L1 da fuselagem na aterragem:** forma fechada do esforço transverso e do momento (antes ficava um
   momento residual na cauda).

## 4. Dois casos

* `dimensionado`: W/S fixada no valor real (472 kg / 10,5 m²); S e b saem de W0 do acdt.
* `geometria_ls4`: S = 10,5 m² e b = 15 m impostos (ponto fixo em `constraints.ws_fixed`) — compara massas com a
  mesma geometria.

## 5. Resultados (caso `geometria_ls4`, 25 nov 2026)

| grandeza | acdt | real | Δ | fonte |
|---|---|---|---|---|
| W0 [kg] | 383 | 472 (MTOM) | −19 % | tcds |
| massa vazia [kg] | 149 | 238 | −37 % | janes |
| asa [kg] | 62,6 | 128 | −51 % | fai_refmass |
| fuselagem + deriva + trem + comandos + aviónica [kg] | 82,6 | 123,0 (Std Cirrus, análogo) | −33 % | hoff_gratton |
| estabilizador [kg] | 2,5 | 7,0 (Std Cirrus, análogo) | −64 % | hoff_gratton |
| asa / massa vazia | 0,42 | 0,46–0,55 | — | hoff_gratton |
| CG [mm atrás do BA da raiz] | 331–357 | 225–375 | dentro | tcds |
| (L/D)max a 320 kg | 39,3 | 40 | −2 % | cumulus |
| afundamento a 95 / 148 / 200 km/h [m/s] | 0,690 / 1,771 / 4,076 | 0,660 / 1,426 / 2,995 | +5 / +24 / +36 % | cumulus |
| VA [km/h] | 179 | 180 | −0 % | tcds |
| flutter V_F [km/h EAS] | 200 (falha vs 1,2 VD) | sem flutter até VD | — | tcds |

O W0 do acdt é a massa com piloto de 110 kg e 124 kg de água (FM), não o MTOM; a diferença vem toda da massa vazia.
O caso `dimensionado` e a sensibilidade ao e do AVL estão em `comparacao.md`.

## 6. Porque é que a asa sai com metade da massa

A asa do acdt (62,6 kg) é a **estrutura primária dimensionada à resistência**. Decomposição do caixão numa corrida
de desenvolvimento com W0 ≈ 385 kg (total 64,4 kg): banzos 19,0, revestimento do caixão 9,6, núcleo 5,6, almas 2,8,
bordos 14,1, nervuras 0,5 e não-ótimo 12,9 kg. A verificação à mão dos banzos
(M_u/(h · 300 MPa)) confirma-a. A asa pesada (128 kg) inclui também itens que o modelo não tem:

1. **Itens não estruturais e secundários** (não modelados, massa desconhecida): gelcoat e massa de acabamento (a
   Wikipedia refere que o gelcoat do LS4 é espesso o bastante para reperfilar), ailerons e dobradiças, caixas e lâminas
   dos travões, sacos e válvulas do lastro de água, comandos dentro da asa.
2. **Raiz:** espigões da longarina com sobreposição na fuselagem, pinos e casquilhos. O fator de ligação ≥ 1,15
   (CS 22.625) e o fator de 1,725 do ensaio estático da LBA (FVK/91: j = 1,15 × 1,5) não estão aplicados aos banzos.
   Também não há redução do admissível a 54 °C (AMC 22.613).
3. **Rigidez:** o modelo dimensiona só à resistência e dá flutter a 200 km/h EAS, abaixo de VD. O LS4 real não tem
   flutter até VD, logo a asa real é mais rígida (torção) do que a asa mínima do acdt. Um caixão dimensionado também à
   rigidez seria mais pesado.
4. **Espessuras mínimas** de laminação (0,25 mm por face) e núcleo mínimo — PRESSUPOSTO, sem dado do fabricante.

A opção `secondary_skin: sanduiche` (item 7 da §3) foi a única correção aplicada (asa 53 → 63 kg), porque tem
justificação física direta: uma casca sem reforçadores entre seis nervuras não funciona em laminado simples. Os
restantes itens não têm massas publicadas para o LS4 e ficam como desconhecido, sem fatores inventados.

## 7. Outras diferenças

* **Fuselagem e estabilizador** abaixo do análogo (Std Cirrus): a casca é dimensionada à resistência com faces mínimas.
  Faltam o reforço local do cockpit e da raiz da deriva, o canópia, o gancho e o trem retrátil com a caixa. O trem é a
  extrapolação de Raymer (≈ 23 kg) — sem dado do LS4.
* **Polar a alta velocidade** pior do que a medida (+24 % e +36 % de afundamento): sem flaps, laminaridade constante e
  perfil substituto (FX 67-K-150 em vez do FX 79 modificado) com NeuralFoil. O XFOIL deixa de convergir a 12° neste
  perfil, por isso o exemplo usa `airfoil_solver: neuralfoil`.
* **e do AVL** inclui a empenagem não equilibrada (0,862 vs 0,977 só com a asa); com a asa só, (L/D)max = 42,4.

## 8. Itens em aberto (decisão do utilizador)

* Coordenadas reais do perfil LS4 (FX 79-162/133 modificados) para a polar.
* Massas reais da fuselagem, empenagem e trem do LS4 (pesagem ou fabricante).
* Planta real (afilamento 0,45 é PRESSUPOSTO).
* Dimensionar a asa também à rigidez/flutter e aplicar os fatores CS 22.619/625 e LBA aos banzos (opção a criar).
* Massa dos itens secundários da asa (travões, ailerons, lastro, gelcoat) — sem fonte pública encontrada.
