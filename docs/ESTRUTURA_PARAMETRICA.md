# Estrutura paramétrica de baixa fidelidade (disciplina `structure_layout`, L1)

Funcionalidade geral do acdt, independente da configuração (convencional, sem cauda, UAV, VTOL, booms). Permite
definir por parâmetros os membros estruturais do avião — longarinas, nervuras, revestimentos, cavernas, anteparas,
reforçadores/longarinas da fuselagem, booms e apoios —, verificá-los com métodos clássicos citados, dimensioná-los e
passar o resultado às outras análises: orçamento de massa/CG/inércia, modelo de vigas para análise externa e
relatórios.

Incremento 1 (24 nov 2026): esquema único, cavernas/anteparas/reforçadores explícitos na fuselagem e nos booms
(o que faltava), tabela única de membros com a asa e as empenagens **embrulhadas** (não redimensionadas) e exportação
de um modelo de vigas neutro. Estudo de exemplo em aviões convencionais (C172 e UAV de 150 kg), `applied: false`.

## 1. O que já existia (levantamento)

| Área | Onde | O que faz |
|---|---|---|
| Cargas | `domains/aircraft/structures.py` | Diagrama V-n (CS-23 / 14 CFR 23 / STANAG 4671), sustentação em envergadura (Schrenk ou faixas do AVL), V/M/T por integração da ponta |
| Caixão da asa (Fase 2/3) | `structures.py` | Caixão de duas longarinas por resistência (Megson) e por estabilidade: painéis reforçados (Farrar), almas de Kuhn com montantes, crippling de Needham, revestimento sanduíche |
| Secção real (Fase 5) | `core/thinwalled.py`, `wingbox/section.py` | Solver multicélula de parede fina (Megson): centro de corte, EI, GJ no contorno do perfil, célula D do bordo de ataque |
| Caixão Fase 6 | `wingbox/sizing6.py`, `shell6.py`, `optimize*.py`, `study*.py`, `render.py` | Painéis metálicos/sanduíche, banzos I/C/Z/compostos, nervuras dimensionadas com aligeiramentos, FEM de casca, otimização, desenho |
| Nervuras por topologia | `wingbox/rib_simp.py`, `rib_simp_mass.py` | SIMP das nervuras e massa no orçamento |
| Secções e materiais | `core/sections.py`, `core/materials.py` | Perfis I/C/Z/T/cantoneira/ómega/tubos, encurvadura local, crippling de Gerard/Needham; metais MIL-HDBK-5J, compósitos por CLT, núcleos |
| Viga-fuselagem L1 | `structures_l1.py` | Tubo circular (NASA SP-8007), longarinas e cavernas à espessura **mínima**, piso e **duas anteparas à espessura mínima** (sem verificação), envelope cauda a VA / motor / aterragem 23.473; empenagens como caixões de carga uniforme (só massa) |
| Pormenor | `detailed_sizing.py`, `assembly/gear_devices.py` | Esmagamento de nervuras, ligação de raiz por parafusos, superfícies de comando; pernas do trem |
| Aeroelasticidade / alta fidelidade | `aeroelasticity.py`, `hifi/nastran.py`, `hifi/fem.py` | Divergência, inversão, flutter binário, AEER-45; escritor SOL 145 da asa |

**Lacunas** que este incremento ataca: não havia cavernas explícitas nas estações das cargas concentradas (ligação
da asa, trem, berço do motor, carga útil, cauda), nem verificação de anel de caverna, de instabilidade geral, de
reforçadores entre cavernas ou de anteparas; os booms não tinham estrutura; não havia uma tabela única de membros
nem um modelo de vigas do avião inteiro.

## 2. Arquitetura

```
assumptions.structure_layout            (opt-in; enabled: false por omissão)
├── material: auto | chave de acdt.core.materials
├── coupling: relatorio | iterar          (iterar ainda não implementado — relatado)
├── fuselage:                             (corpo tubular principal)
│   ├── frame_pitch_m, frame_section {kind: z|channel|hat|i, h_m, b_m}
│   ├── stringers {n | pitch_m, kind, h_m, b_m, t_m}, longerons {n, area_m2, theta_deg}, skin_t_m
│   ├── bulkheads [{id, x_m | x_frac, pressure_Pa, edge: simply_supported|clamped}]
│   ├── auto_loads (cargas da viga L1), wing_attach_theta_deg, engine_mount_theta_deg, gear_theta_deg, tail_theta_deg
│   └── loads [{id, kind, x_m | x_frac, theta_deg, Fz_N, Fy_N, M_Nm, mass_kg, case}]
├── booms [{id, x0_m, length_m, diameter_m, y_m, z_m, loads [{x_m, Fz_N, Fy_N, T_Nm}], …mesmas chaves da fuselagem}]
└── export {beam_model: true}
```

* **Coordenadas**: x para trás a partir do nariz, y para a direita, z para cima. Nas cavernas, θ é medido a partir
  do topo, positivo para +y (90° = lado direito, 180° = fundo).
* **Superfícies sustentadoras** (asa, estabilizador, deriva, e no futuro superfícies de VTOL): o caixão continua a
  ser o de `structures.py`/`wingbox` (já dimensionado e verificado). A disciplina embrulha-o na tabela de membros
  (banzos, almas, painéis, núcleo, bordos, nervuras, não-ótimo) e no modelo de vigas (EI e GJ por estação).
* **Corpos tubulares** (fuselagem, booms): o código novo é genérico (`acdt/core/structures/frames.py`, sem
  dependência do domínio). O adaptador (`domains/aircraft/structure_layout.py`) traduz as cargas do avião.
* **Saídas** (`result.structure_layout`): `members` (tabela única: id, componente, tipo, massa, posição, inércia
  própria, RF mínimo, veredicto passa/falha/desconhecido, método, fonte, secção, cargas), `budget` (massa, CG,
  Ixx/Iyy/Izz no CG estrutural, por componente, massas desconhecidas listadas), `comparison` (fuselagem paramétrica
  vs viga L1 vs Raymer Eq. 15.49), `fuselage` (cavernas, tabela da casca por estação, casos de carga, notas),
  `booms`, `beam_model` (`acdt.beam/1`). `to_nastran(beam_model)` dá o mesmo modelo em texto de campos curtos
  (GRID/MAT1/PBAR/CBAR/CONM2), escrito pelo acdt (sem código GPL), para correr fora (p. ex. CalculiX por subprocesso,
  via Build).

## 3. Cargas

* **Envelope da casca**: M, V e T LIMITE por estação da viga-fuselagem L1 (`structures_l1.fuselage_beam`): cauda a VA
  (Raymer 12.15) ou equilíbrio + 23.423(b), inércia do motor, aterragem 23.473 (com as mesmas omissões: 23.427 e
  23.441 não modelados). Fator de segurança 1,5 (23.303 / USAR.303).
* **Cavernas pesadas** (cargas concentradas LIMITE, por caso):
  * *manobra*: sustentação de projeto da cauda nas fixações da cauda (+ torção da deriva como binário), inércia do
    motor n·m·g nos quatro apoios do berço (±45°, ±135° — PRESSUPOSTO), e as duas ligações da asa (longarinas da
    frente e de trás, posição pela corda de raiz no centro aerodinâmico — PRESSUPOSTO) a equilibrar força e momento
    destas cargas;
  * *aterragem*: reações do trem da viga L1 (frente a 180°, trás a ±150° — PRESSUPOSTO, trem na fuselagem), inércia
    do motor ao fator de inércia da aterragem e metade da sustentação em cada longarina da asa (PRESSUPOSTO);
  * cargas do utilizador (`loads`): massa × n e forças declaradas, reagidas pela casca na própria caverna.
* A inércia distribuída da casca vai para o revestimento e os reforçadores, não para as cavernas (PRESSUPOSTO).

## 4. Verificações (todas com RF = admissível/aplicado)

| Membro | Verificação | Método |
|---|---|---|
| Caverna pesada | anel sob cargas concentradas reagidas pelo fluxo de corte da casca q(θ) = (F_z sin θ − F_y cos θ)/(πR) + T/(2πR²); hiperestático de grau 3 resolvido por Castigliano (só flexão, anel fino); σ = max(|N|/A + |M| c/I) ≤ F_cy | Megson (tubo fino; métodos energéticos); Timoshenko, *Strength of Materials* (anéis); verificado contra o anel comprimido por duas forças (P R/π e P R (1/2 − 1/π)) |
| Caverna (todas) | crippling da secção | Gerard (`core/sections.py`; Bruhn C7) |
| Caverna (todas) | instabilidade geral: EI ≥ C_f M_ult D²/L, C_f = 1/16 000 | Shanley (1949); Niu (1988) cap. 11 |
| Reforçadores/longarinas | σ = M z/I em booms com largura efetiva de von Kármán b_e = 1,9 t √(E/σ); coluna entre cavernas Euler–Johnson com corte no crippling de Gerard, c = 1 (PRESSUPOSTO), raio de giração para fora do plano da pele (PRESSUPOSTO: a pele estabiliza o modo lateral) | Megson Eq. 20.1; Bruhn C2/C7 |
| Revestimento | τ = q/t ≤ F_su com q = V/(πR) + T/(2πR²); painel plano simplesmente apoiado k_c = 4, k_s = 5,35 + 4 (b/a)², interação R_c + R_s² ≤ 1 à carga LIMITE (sem encurvadura até à limite — PRESSUPOSTO; curvatura desprezada, conservativo) | Megson; Bruhn C5 |
| Antepara | placa circular sob pressão: apoiada 3(3+ν) p a²/(8t²), encastrada 3 p a²/(4t²), ≤ F_ty | Timoshenko & Woinowsky-Krieger §15–16 |

**Dimensionamento por membro**: cavernas — espessura em passos de 0,1 mm desde a mínima do material até 6 mm; se
não chegar, altura × 1,25 até 0,12 D (PRESSUPOSTO); a secção escolhida é verificada contra todos os casos da estação.
Revestimento e reforçadores — espessuras por estação em passos de 0,1 mm até passarem (corte/encurvadura → pele;
coluna/tração → reforçador). Anteparas — espessura da placa pela pressão, mínima sem pressão. Fator não-ótimo
`structures.nonoptimum_factor` (Torenbeek 1982 App. C) como linha própria.

**Desconhecido ≠ passa**: cavernas sem momento do corpo, anteparas sem pressão declarada (o corte da alma sob cargas
concentradas não está modelado), bordos/nervuras/não-ótimo da asa (espessura mínima, não verificados) e booms sem
cargas ficam «desconhecido».

## 5. Estudo de exemplo (`applied: false`)

`python examples/studies/estrutura_parametrica/estudo_estrutura_parametrica.py` (cerca de 75 s). Liga
`structure_layout` em memória em `examples/cessna172_check.yaml` e `examples/uav_150kg_stanag4671.yaml`; escreve
em `examples/output/estrutura_parametrica/` a tabela de membros (CSV), o resumo (JSON), o modelo de vigas (JSON) e o
`.bdf`. Material Al 2024-T3 (MIL-HDBK-5J), cavernas Z, reforçadores Z 20 × 12 mm a passo de 0,12 m (PRESSUPOSTO).

| Caso | W0 | Fuselagem paramétrica | Viga L1 | Raymer 15.49 | Pele | Reforçadores | Cavernas (leves + pesadas) | Anteparas | Não-ótimo |
|---|---|---|---|---|---|---|---|---|---|
| C172 | 1137,8 kg | **106,0 kg** | 85,1 kg | 97,6 kg | 58,1 kg | 12,3 kg | 3,2 + 10,3 kg | 0,9 kg | 21,2 kg |
| UAV 150 kg | 153,2 kg | **12,1 kg** | 5,5 kg | 7,3 kg | 7,2 kg | 1,7 kg | 0,1 + 0,6 kg | 0,1 kg | 2,4 kg |

No C172 a fuselagem paramétrica fica 9 % acima de Raymer (que inclui portas, janelas e piso que este modelo ainda
não tem, e não inclui a encurvadura à carga limite): o revestimento é dimensionado pela encurvadura dos painéis à
carga limite. As seis cavernas pesadas passam, com a do trem principal a subir para 54 mm de altura e 4,7 mm de
espessura (aterragem) e a da cauda para 5,2 mm. No UAV de 150 kg a massa é dominada pelas espessuras mínimas
(0,41 mm de pele, reforçadores e cavernas mínimas): o modelo é conservativo a esta escala, e o resultado só deve
ser lido como limite superior até haver um material/processo de UAV (compósito, `material: cfrp_qi`). Nenhum
membro falha; os desconhecidos (7 em cada caso) são os listados acima.

## 6. Próximos incrementos

1. Fuselagem: piso e vigas de piso, portas/aberturas (molduras), secções não circulares, longarinas reais
   (cargas de flexão lateral e torção), alma das anteparas sob cargas concentradas, pressurização no anel.
2. Empenagens pelo caminho `wingbox` (secção, EI/GJ por estação) e entrada no modelo de vigas; booms ligados à
   geometria de `assembly` (twin-boom, VTOL).
3. Apoios e ferragens: berço do motor (treliça tubular, Euler–Johnson), ligações asa–fuselagem e trem (parafusos e
   olhais com métodos citados), cargas dos rotores de VTOL nos booms.
4. Acoplamento `iterar`: massa estrutural paramétrica no fecho do W0, CG/inércia no balanço.
5. Estimativa de flutter com o modelo de vigas (modos da asa + massas concentradas) ligada a `aeroelasticity.py`.
6. Exportação para CalculiX por subprocesso (via Build, no PC do João) e comparação viga vs casca.
