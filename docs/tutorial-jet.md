<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Jatos de transporte subsónicos — primeira fatia L0

Ferramentas rápidas para explorar a classe A320/737; **não demonstram conformidade CS-25**.
Não alteram o `acdt size` genérico. `jet size` fecha a massa de uma alternativa
com geometria/motores dados (§ seguinte), não um MDA completo de transporte.

```sh
acdt jet wave-drag --mach 0.79 --cl 0.55 --sweep 25 --thickness-ratio 0.12
acdt jet turbofan --mach 0.79 --altitude 11277.6 --thrust 120000
acdt jet loads --mass 77000 --area 122.6 --vc 160
acdt jet analyse --input examples/jet/transport_l0.yaml -o output/jet.json
acdt jet check --input examples/jet/a320_ref.json -o output/jet_check.json
```

A saída é JSON (também impressa); código de saída 0: checks passam, 1: falha num
check com resultado guardado, 2: entrada inválida. Todos os valores são SI: empuxo
por motor em N (SLS **não instalado**), TSFC em kg/(N s), massa em kg e alcance em m.
A velocidade do envelope é sempre **EAS m/s**, não TAS, CAS ou Mach.
O VC do exemplo é escolhido para uma condição de manobra distinta do cruzeiro.

## Métodos e PRESSUPOSTOS

- **Korn–Mason/Lock:** Mdd por tecnologia, espessura, sustentação e flecha a meia corda;
  Mcrit=Mdd−(0,1/80)^(1/3); CDonda=20 max(M−Mcrit,0)^4. A divergência tem
  declive dCD/dM=0,1. Equivalente de uma faixa de asa, não integração da asa.
  Fonte: Mason (2006), *Configuration Aerodynamics*, cap. 7, equações 7-3, 7-6–7-8;
  Gur, Mason e Schetz (2010), *Journal of Aircraft*, doi:10.2514/1.47557;
  Raymer (2018), cap. 12. **PRESSUPOSTO:** κ=0,95, t/c=0,12, flecha=25°, CL=0,5
  quando omitidos. Limites implementados: M≤0,9, flecha≤45°, 0≤CL≤1,2.
- **Turbofan:** correlação de empuxo de alto bypass de Mattingly, Heiser e Pratt
  (2002), *Aircraft Engine Design*, cap. 2, com razões totais de pressão/temperatura;
  TSFC=(0,4+0,45 M) sqrt(T/288,15) lb/(lbf h), Ihme (2025), ME257, eq. 2.77.
  Conversão: dividir por g0×3600 para kg/(N s). **PRESSUPOSTOS:** TR=1,05,
  instalação=0,97, multiplicador TSFC=1, ISA, empuxo SLS=120 kN/motor se omitido.
  Não se aplica uma segunda penalização de instalação ao TSFC já instalado.
  Domínio: 0≤M≤0,9 e 0≤h≤15 km. O empuxo cai com altitude; a recuperação de
  pressão pode torná-lo **não monótono em Mach** no cruzeiro (não forçar um declive falso).
- **Massas:** regressão `jet_transport` existente de Raymer (2018), tabela 3.1,
  We/W0=1,02 W0_lb^−0,06. **Não** é OEW de uma companhia nem build-up Torenbeek.
  Breguet e frações de segmento reutilizam `weights.py` (tabela 3.2, eqs. 3.5/3.11).
  **PRESSUPOSTOS:** massa de cruzeiro 0,85 MTOW; CD0=0,020, e=0,82;
  L/D de missão=17 (independente do ponto de polar); reserva/combustível preso=6%
  do combustível calculado; tripulação=800 kg; 2 motores se omitidos.
  O orçamento devolve carga útil restante, não resolve MTOW nem limita volume de combustível.
- **V-n:** paráfrases das provisões 25.335/.337: n+ limitado à banda 2,5–3,8
  com peso em lb; n−=−1 até VC, linear até zero em VD; VA=VS1 sqrt(n+).
  **PRESSUPOSTOS:** CLmax limpo=1,5, CLmin=−1; VD/VC=1,25 escolhe a opção
  simples de margem de velocidade de 25.335(b), não uma margem universal obrigatória.
  VC=160 m/s EAS por omissão no `analyse`. VC que não comporte os cantos de
  sustentação é rejeitado. Sem rajadas, buffet, limite Mach ou cargas de flap.

Os resultados identificam os pressupostos e as verificações que falham.
O check A320 usa números públicos com URL/data por campo no JSON (6 nov 2026),
compara We com OEW e mostra margens de empuxo e massa. A tolerância de 25% é
**PRESSUPOSTO**, não uma banda de precisão validada; alcance e empuxo são entradas,
não validações independentes. As variantes públicas são ilustrativas e não casadas.

## Continuação L2

pyCycle/OpenMDAO fica fora do processo acdt. Um adaptador futuro deverá fornecer os mesmos campos
`thrust_installed_N` e `TSFC_kg_N_s` por Mach/altitude/rating, com dados e versão do
deck, e calibrar a correlação L0. A 18 nov 2026 o turbojato simples publicado correu noutro
intérprete (pyCycle 4.4.0). O TSFC no ponto de projecto foi 0,799 lb/(lbf·h), contra 0,400
desta correlação de turbofan. Não há deck L1, e nenhum factor entrou. A correlação não mudou.
Faltam fecho MDA de jato, mapas ECS, build-up Torenbeek completo,
ajuste de throttle, rajadas/Mach/buffet e validação CFD/ensaio e referência 737.

Fontes públicas abertas:
- https://archive.aoe.vt.edu/mason/Mason_f/ConfigAeroTransonics.pdf
- https://ihmegroup.github.io/assets/pdf/ME257.pdf
- https://www.law.cornell.edu/cfr/text/14/25.335
- https://www.law.cornell.edu/cfr/text/14/25.337
- Proveniência da referência: `examples/jet/a320_ref.json`.

## Fecho acoplado de massa — `jet size` (6 nov 2026)

```sh
acdt jet size --input examples/jet/coupled_size.yaml -o output/jet_size.json
```

MCP: `jet_size(spec, record=true)`. A chamada regista entradas, pressupostos,
versões, commit e resultado em `runs/` (`ACDT_RUNS_DIR` pode mudar a raiz).
`record=false` é cálculo puro; a função de domínio é `size_jet(dict)`.
Não usar esta semente como uma arquitetura escolhida: cada alternativa tem um
`configuration_id` e deve ser avaliada à mesma missão. A ferramenta não escolhe
configuração, área alar, motor ou vencedor de um trade. A integração com o
simulador como juiz comum de DESIGN_WORKFLOW continua pendente.

### O que agora fecha

Entradas obrigatórias: `configuration_id`, `aircraft_class: jet_transport`,
`payload_kg`, `crew_kg`, `mass_bounds_kg: [inferior, superior]`, `wing_area_m2`,
`aspect_ratio`, `mach`, `altitude_m`, `range_m`, `thrust_sl_N` por motor e `n_engines`.
O intervalo é uma escolha numérica explícita, não uma massa publicada/validada.
`mtow_limit_kg` é uma restrição opcional, não a massa que o solver tem de reproduzir.

Para cada massa tentativa:

1. Sem bloco `weights` (ou com `mode: statistical`), We vem da regressão
   Raymer `jet_transport` existente. `mode: components` opt-in usa a soma descrita abaixo.
2. As frações Raymer de descolagem/aquecimento e subida dão a massa inicial de
   cruzeiro; a fração de aterragem aplica-se no fim. Não se simulam estas fases.
3. Integra-se Breguet diferencial `dm/dx = −TSFC D(m)/V` a Mach/altitude constantes.
   CL vem da massa instantânea; CD = CD0 + CL²/(π AR e) + CDonda(Korn–Mason).
   O TSFC vem do turbofan L0 no mesmo Mach/altitude. Assim o L/D varia ao longo do
   cruzeiro e com cada massa tentativa: **não há `mission_ld` imposto**.
4. Combustível total = (1 + reserva) × queima de viagem. A reserva fica a bordo
   na aterragem; não é retirada duas vezes nem tratada como alcance gratuito.
5. Resolve-se `m0 − We(m0) − carga útil − tripulação − combustível = 0` por
   bissecção num intervalo com mudança de sinal. A integração usa RK4 clássico,
   duplicação de passos e estimativa de erro por Richardson (diferença / 15).
6. Verifica-se empuxo disponível contra o maior arrasto ao longo do cruzeiro e,
   se dado, o limite de MTOW. Massa convergida **não implica viabilidade**.

`solver` permite `mass_atol_kg` (0,01), `mass_rtol` (1e−7), `max_iterations` (80),
`cruise_steps` (32), `max_cruise_steps` (1024). São **PRESSUPOSTOS numéricos**,
não precisão física validada. Convergência exige resíduo ≤ max(atol, rtol×m0);
a tolerância da integração é derivada para limitar a estimativa de erro do
resíduo a 10% dessa tolerância. O resultado guarda resíduo absoluto/relativo,
intervalo final, histórico de avaliações, refinamento e trajetória CL/CD/L/D.

Estados de falha são explícitos: `not_bracketed`, `max_iterations`,
`outside_model_domain` ou `integration_not_converged`. Nestes casos `mtow_kg`,
`weights` e `cruise` são nulos, `converged=false` e CLI termina com código 1.
Não ter mudança de sinal **não prova inviabilidade global**: pode haver raízes
fora do intervalo ou várias raízes dentro dele. Dividir o intervalo e avaliar
as alternativas é responsabilidade do estudo; não se afirma unicidade/ótimo.
Entradas inválidas ou uma classe sem método suportado são rejeitadas (CLI 2),
sem recorrer a equações GA, L/D fixo ou valores substitutos ocultos.

### Limites desta fatia

- Geometria, CD0/e, número/rating dos motores e tecnologia da asa são dados.
  Não há redimensionamento de asa/motor, peso de motor variável, volume de
  combustível realimentado ou fuselagem pressurizada. No modo estatístico, alterar
  AR/asa afeta a aerodinâmica, mas não a estrutura. No modo por componentes,
  só asa/caudas têm correlações estruturais; motores e restante continuam dados. Não usar este L0 isolado
  para ordenar alternativas muito diferentes com falsa precisão.
- **PRESSUPOSTO:** o TSFC da correlação de rating máximo serve ao empuxo requerido;
  não há mapa de throttle. Empuxo insuficiente é reportado, nunca corrigido
  inventando um motor. Sem o bloco opcional `performance`, não se avaliam pontos de
  descolagem/subida/OEI; com ele há só triagem L0, nunca trajetória/regulamento completo.
- `jet analyse` mantém o seu orçamento antigo com L/D de missão dado; `jet size`
  é a ferramenta acoplada distinta. O pipeline `acdt size` não foi alterado:
  a sua geometria, motores e fases posteriores ainda não constituem este fecho
  de jato. Evita-se ligá-lo a pressupostos GA de cauda/estrutura por defeito.
- A classe do fecho continua `jet_transport`. O modo estatístico e as regressões
  por componente não são validados para configurações não convencionais; estas
  exigem massas fornecidas com fonte e inventário explícito, não fallback GA.
- Testes analíticos cobrem o limite de Breguet a L/D constante e o caso sem
  cruzeiro contra a equação Raymer existente; não são validação de um A320 real.

Referência numérica: Hairer, Nørsett e Wanner (1993), *Solving Ordinary
Differential Equations I*, cap. II (Runge–Kutta). Sem novas dependências.

## Triagem opcional de descolagem/subida/OEI (7 nov 2026)

`acdt jet performance --input examples/jet/performance_l0.yaml` fecha massa e
avalia corrida AEO e pontos de subida AEO/OEI com configurações explícitas.
Também disponível por `jet size` com bloco `performance` e MCP `jet_performance`.
Contrato aditivo: `feasible` mantém o âmbito antigo; o novo
`combined_requested_checks_passed` cobre a triagem solicitada, **não certificação**.
Ver [tutorial-jet-performance](tutorial-jet-performance.md) para métodos, fontes,
limites e os campos regulamentares/trajectória que ficam não avaliados.


## Build-up parcial de transporte — opt-in (7 nov 2026)

```bash
acdt jet weights --input examples/jet/component_weights.yaml -o output/jet_weights.json
acdt jet size --input examples/jet/coupled_components.yaml -o output/jet_components.json
PYTHONPATH=src python examples/jet/compare_component_weights.py
```

MCP: `jet_weights(spec, record=true)`; spec contém `mass_kg`, `wing_area_m2`,
`aspect_ratio`, `weights`. Avalia o inventário à massa dada, sem fechar missão.
`jet_size`/`jet_performance` aceitam **o mesmo bloco `weights`**, sem alterar os
restantes inputs. Omissão ou `{mode: statistical}` mantém o resultado antigo.
O script compara o mesmo candidato estatístico/por componentes, perturba a
carga última em +10% e mostra o caso de fuselagem ausente. Não escolhe arquitetura.

### O que é calculado, e o que continua a ser entrada

Implementam-se apenas **asa, estabilizador horizontal e deriva** Raymer,
*Aircraft Design: A Conceptual Approach*, 5.ª ed. (2012), §15.3.2 cargo/transport.
Equações/unidades verificadas na transcrição pública AeroSandbox e nas lâminas
46/54 de *Chapter 15 Weight and Balance* (2022-11-23): URLs em [THIRD_PARTY](../THIRD_PARTY.md).
Coeficientes imperiais usam Wdg em lb, áreas em ft² e comprimentos em ft;
conversão SI usa lb=0,45359237 kg e ft=0,3048 m, sem multiplicar por g duas vezes.

`mode: components` exige `configuration_description` livre e declaração booleana
`conventional_metal_transport`. As regressões são históricas de transportes
metálicos convencionais, sem precisão quantitativa validada para este candidato.
Com declaração falsa, a regressão fica **out_of_domain**, não é corrigida por um
fator inventado. Pode substituir-se qualquer grupo por massa fornecida; uma
configuração não convencional com todas as massas externas continua uma opção.
Não há penalização de posição do motor, fator automático de compósitos ou
seleção de arquitetura. Bandas de inputs são guardas numéricas, não domínio
experimental garantido da correlação.

- `ultimate_n` é explícito, não vem de um default GA/CS-25. No exemplo, 3,75 é
  **PRESSUPOSTO** de estudo, não prova de dimensionamento regulamentar.
- Asa: área/AR vêm do candidato do fecho; espessura **na raiz**, afilamento,
  flecha a 25% da corda e área total de comandos são entradas estruturais.
  Não confundir com t/c da tira equivalente/flecha a meia corda de Korn.
- Caudas: área, AR, flecha a 25%, braços e raios de giração são explícitos.
  Braço horizontal: distância entre quartos de CMA de asa e estabilizador;
  largura da fuselagem no estabilizador e área de profundor são dadas.
  Não se supõe Ky=0,3 Lt ou Kz=Lt. Declaram-se ainda cauda horizontal toda móvel
  e razão de altura Ht/Hv da montagem da cauda na deriva (0–1).
- Fuselagem, trem (main+nose), naceles, acessórios, APU, comandos, hidráulica,
  elétrica+aviónica, ambiente (AC+anti-gelo), interiores e combustível seco têm
  métodos `raymer_transport_*` opt-in (Raymer Sec.15.3.2; fuselagem L/D = esbeltez
  estrutural ADAC/SUAVE; Vstall do trem em **knots**). Motores secos, itens
  operacionais e `other_empty_items` continuam **massas fornecidas**.
- Pressurização: par `pressurized_volume_m3` + `delta_p_Pa` no método de fuselagem
  acrescenta W_press (Raymer Sec.15.3.3). O bloco `pressurization` no `jet size`
  só valida extração (`supplied_auxiliary`); sem ela fica **unassessed**.
- Exemplo: `examples/jet/components_raymer_extended.yaml`. Sem ajuste ao OEW do A320.

### Cobertura e contabilidade

`items` tem nomes únicos, `covers`, `method` e `source` obrigatório:

- `supplied`: `mass_kg` **total**, não por motor. Ausente ou nula significa
  desconhecida, nunca zero. Um conjunto conhecido pode cobrir vários grupos e
  conta uma vez; não é dividido artificialmente em subtotais.
- `not_applicable`: exclusão explícita com `reason` e fonte, não uma massa escondida.
- `raymer_transport_*` (asa/HT/VT/fuselagem/trem/naceles/sistemas):
  todos os `inputs` explícitos, só cobrem o seu grupo, sem massa fornecida em paralelo.

A WBS contabilística obrigatória está no exemplo/`weights.COVERAGE` e aceita
`additional_required_groups` para equipamento adicional; não é lista fechada de
configurações. Cobertura duplicada é erro. Grupo desconhecido não declarado é erro.
Tripulação, carga útil e **todo combustível** ficam fora do inventário vazio.
Óleos/fluidos instalados devem constar uma vez no grupo do sistema ou dos itens
operacionais. O exemplo inclui depósitos/bombas em `fuel_system_dry`; o pós-check
`storage` não soma esse inventário novamente. **Limite:** combustível inutilizável
no `storage` continua sem feedback no MTOW; combustível do fecho = viagem + reserva.
Não esconder essa massa no vazio para fingir que a missão a modelou.

`coverage.complete` é cobertura **declarada**, não prova independente de que a
lista está fisicamente completa. `known_subtotal_kg` e `known_group_subtotals_kg`
são só diagnósticos; `group_totals_kg` e subtotal seco de estrutura ficam nulos
onde houver cobertura desconhecida ou um conjunto sem repartição justificável.
`operating_empty_mass_kg` fica nulo: este inventário sem combustível/tripulação
não é OEW operacional/certificado. Não adicioná-lo outra vez à montagem nem à bateria.

No fecho, cada tentativa recalcula os termos em Wdg. `weight_build_up` mostra
itens/fontes/aplicabilidade e cobertura; `solver.history` inclui massas vazia e
modelada por tentativa. Falta de cobertura ou regressão fora de domínio dá
`incomplete_weight_build_up`, sem MTOW, sem fallback estatístico e sem usar o
subtotal conhecido para fechar. Inventário vazio não positivo é fora do domínio;
resíduo sem mudança de sinal ou iterações esgotadas mantém os estados anteriores.
Os checks de inventário à massa dada não impedem explorar o limite inferior do
intervalo: pode ter vazio > massa tentativa antes de se encontrar uma raiz válida.

**Todos os novos valores do exemplo são PRESSUPOSTOS ilustrativos**, não massas
publicadas ou ajustadas de um avião. Testes verificam as equações publicadas por
cálculo imperial independente, expoentes, conversões, contabilidade, falhas e
compatibilidade; **não** validam a precisão dos pesos contra uma aeronave real.
Pendente: calibração do build-up, peso de motor associado ao rating, mapas ECS,
ligação física montagem/CG, balanced field/V1/TOD pleno, MDA completo, Torenbeek
completo e pyCycle.
