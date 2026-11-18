# Tutorial — Fase 2: baixa fidelidade (AVL, XFOIL, V-n, caixão, estabilidade, desempenho)

Continua o [tutorial da Fase 1](tutorial-fase1.md). Na Fase 2 o design point da Fase 1 é
verificado e corrigido com métodos de baixa fidelidade, sempre clássicos e citados no código.

## 0. Pré-requisitos

* `pip install -e ".[dev,aero]"` (NeuralFoil é a alternativa ao XFOIL);
* opcional, mas recomendado: os executáveis `avl` (3.40) e `xfoil` (6.99) no `PATH`
  (compilação: `docs/ARCHITECTURE.md` §8). Sem eles o acdt usa NeuralFoil + Schrenk e diz isso
  nas notas do relatório.

## 1. Ligar a Fase 2 num ficheiro de missão

```yaml
assumptions:
  aero:
    fidelity: lowfi          # handbook (Fase 1) | lowfi (XFOIL/NeuralFoil + AVL dentro do ciclo)
    airfoil_solver: xfoil    # xfoil | neuralfoil
  structures:
    regulation: auto         # auto: STANAG 4671 se UAS, senão CS-23
    load_factor_from_vn: true  # Nz das equações de massa = 1.5 × n_lim do diagrama V-n
    material: auto           # compósito → cfrp, senão al2024_t3 (allowables = PRESSUPOSTOS)
  stability:
    target_static_margin: 0.10
    stations: {}             # posições x [m] dos componentes; vazio → valores típicos (PRESSUPOSTO)
  performance:
    fuel_capacity_kg: null   # capacidade do tanque (payload–range); null → combustível de projeto
    approach_angle_deg: 3.0  # Raymer 17.9
weights:
  components:
    wing_method: raymer      # raymer | box (usa a massa do caixão no ciclo)
```

Estabilidade, estruturas e desempenho correm sempre. Só a aerodinâmica low-fi é opcional, porque
custa ~10 s por exemplo.

## 2. O que acontece por dentro

1. **Ciclo da Fase 1** até convergir (manual: Raymer Eq. 12.24 + Oswald).
2. **Low-fi no ciclo.** XFOIL dá polares do perfil ao Re de cruzeiro e o clmax ao Re de perda.
   O AVL dá a carga por faixas e o e_inv. O arrasto de perfil da asa integrado substitui o termo
   da asa de Raymer. O ciclo reconverge com a nova polar (CD0, K) e o novo CLmax.
3. **V-n em cada iteração.** Manobra (CS 23.337 / USAR.337) e rajada de Pratt (CS 23.341 /
   USAR.341). O n_lim alimenta o Nz das Eqs. 15.46–15.59. O caixão (Megson/Bruhn) é dimensionado
   e comparado com Raymer Eq. 15.46.
4. **Estabilidade** (depois do ciclo). A asa é posicionada para SM = 10 % no CG mais recuado; o
   AVL corre no CL de cruzeiro compensado, com x_ref no CG traseiro.
5. **Desempenho.** A missão é simulada segmento a segmento com a polar final e comparada com os
   requisitos (`verified`).

## 3. Resultados de referência

**Cessna 172S** (`examples/cessna172_check.yaml`, valores reais entre parênteses):

* W0 = 1161 kg (1157); CD0 low-fi 0,0377, e_eff 0,93; clmax XFOIL 1,70 (NACA 2412).
* V-n CS-23 normal: VC = VC,min = 136 kt EAS; rajada a VC n = 3,95 > 3,8 → n_lim = 3,95.
* Caixão: 86 kg vs Raymer 132 kg (razão 0,65 — o caixão é dimensionado por resistência e é um
  limite inferior).
* SM 11,9 … 10,0 %; ponto neutro 0,506 MAC (manual), 0,574 (AVL, sem fuselagem).
* Alcance de cruzeiro 1228 km ≥ 1185 km; teto 5249 m (POH 4115 m); ROC 5,4 m/s (3,7);
  corrida 200 m (293); aterragem 504 m (407) ❌ porque a aproximação a 3° é conservadora.

**UAV elétrico 25 kg** (`examples/uav_endurance_payload.yaml`):

* W0 = 22,1 kg; V-n STANAG 4671: rajada a VC governa, n_lim = 5,39 (acima da linha de perda
  quase-estática a VD; valor conservativo, ver nota no relatório).
* Caixão CFRP 3,2 kg vs Raymer 4,3 kg; SM 10,8 … 10,0 %.
* Espera por segmentos 2,42 h vs 2,5 h ❌: o dimensionamento (Hepperle) só conta a energia
  potencial da subida (~16 Wh); a missão por segmentos integra descolagem + subida (~94 Wh).
  É precisamente o tipo de discrepância que a verificação da Fase 2 deve revelar. A correção é
  aumentar a energia (bateria) ou o requisito de reserva, não o modelo.

## 4. Ler o relatório

O relatório tem quatro secções novas:

* §10 — polar low-fi vs manual e tabela AVL vs manual (CLα, CDi, ponto neutro, derivadas de
  controlo);
* §11 — V-n com as cláusulas aplicadas, cargas V/M/T, caixão e cross-check da massa da asa;
* §12 — envelope de CG, margem estática, volumes de cauda e compensação;
* §13 — segmentos, payload–range, subida/teto e requisitos vs desempenho.

O `result.json` tem as mesmas grandezas.

## 5. Limitações

Ver `docs/ARCHITECTURE.md` §5.3. As principais:

* falta o arrasto viscoso dependente de CL da fuselagem/cauda;
* o AVL não modela a fuselagem;
* as estações de CG são pressupostos;
* o caixão não verifica crippling nem encurvadura reforçada;
* a aproximação de 3° é conservadora para aviação ligeira.
