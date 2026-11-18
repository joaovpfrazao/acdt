<!-- Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0 -->
# Armazenamento de energia comum L0 — 7 nov 2026

Uma camada comum para combustível e baterias, **não um segundo simulador**.
Serve hélice térmica, jatos, elétricos e VTOL por balanços dos mesmos portadores.
Não escolhe disposição, propulsão ou despacho híbrido. Reutiliza consumos existentes.

## Executar exemplos reais dos modelos existentes

```sh
PYTHONPATH=src python examples/storage/check_examples.py
acdt storage check --input examples/storage/fuel_prop.yaml --source-kind mission --result out/storage/examples/prop_producer.json --reserve-fraction 0.15 -o out/storage/prop_check.json
acdt storage check --input examples/storage/jet.yaml --source-kind jet_size --result out/storage/examples/jet_producer.json -o out/storage/jet_check.json
acdt storage check --input examples/storage/vtol.yaml --source-kind vtol_size --result out/storage/examples/vtol_producer.json -o out/storage/vtol_check.json
```

O script voa dois perfis curtos **pointmass** (hélice térmica/elétrico), chama
`jet_size` existente e integra os segmentos do `size_vtol` existente. Nada é
apresentado como dado certificado ou configuração validada de aeronave/pack.
Todos os valores de densidade, volume disponível, embalagem e rating destes exemplos
são **PRESSUPOSTOS**, não dados de fornecedor. O volume de combustível e o espaço
alocado do exemplo de jato não são volumes publicados do A320.

MCP/Python: `storage_check(spec, source_kind="direct", result=None,
reserve_fraction=None, record=True)`. Cada chamada regista proveniência, incluindo
resultado produtor e pressupostos; `record=False` permite cálculo puro.
CLI: 0 passa a triagem, 1 falha conhecida, 2 entrada inválida, 3 não avaliado.

## Contrato e fronteira de contabilização

`spec` tem `storage` e, só para `source_kind=direct`, `demand`:

```yaml
storage:
  battery:
    nominal_Wh: 1250
    dod: 0.8
    pack_Wh_kg: 200
    pack_Wh_L: 250
    available_volume_m3: 0.005
  assumption_sources: {"*": "PRESSUPOSTO: pack completo e alocação líquida"}
demand:
  battery: {trip_Wh: 800, reserve_Wh: 200}
```

- `demand.fuel`: `trip_kg`, `reserve_kg`; `demand.battery`: `trip_Wh`, `reserve_Wh`,
  opcional `peak_W`. Ambas as reservas são **quantidades utilizáveis adicionais**,
  não percentagens do total instalado nem requisitos regulamentares. Zero é explícito.
- Combustível: capacidade mássica `capacity_kg` **ou** derivação
  `density_kg_m3 × tank_internal_volume_m3 × fill_fraction`. Se ambos forem dados,
  verifica-se também que a capacidade declarada cabe no volume interno com esse
  enchimento/densidade. A capacidade mássica declarada já inclui o limite de enchimento;
  não se multiplica outra vez por fill_fraction.
- `loaded_mass_kg` é a carga efetiva, **não** se assume depósito cheio. A capacidade
  limita a carga; `unusable_mass_kg` é combustível inacessível absoluto. Disponível
  utilizável = carga − inacessível; exigido = trip + reserva. Não voltar a incluir
  combustível inacessível numa reserva que já o contém.
- Pack: utilizável = `nominal_Wh × dod`. A energia de missão é nos terminais do pack:
  perdas de motor/ESC/hélice já contabilizadas no produtor não se dividem de novo.
  Não há multiplicador de eficiência nesta camada. Se a energia recebida estiver no
  veio, a conversão deve ser feita a montante com perdas explícitas; não é aceite
  como se fossem Wh terminais. O pack nominal refere-se à energia elétrica entregue
  nas condições declaradas, não à energia química ideal.
- Massa do pack: `pack_mass_kg` **ou** `nominal_Wh/pack_Wh_kg`.
  Volume: `pack_volume_m3` **ou** `nominal_Wh/pack_Wh_L/1000`.
  Não se aceitam as duas representações concorrentes. Wh/L e Wh/kg têm de ser do
  **pack completo**, incluindo a embalagem declarada, nunca de células sem correção.
  Não se converte automaticamente o volume geométrico de células num pack. Um
  `BatteryPack` já dimensionado em `core.systems.battery` fornece nominal_Wh =
  energy_nom_J/3600 e pack_mass_kg = mass; não se reaplica overhead de embalagem.
  Falta ainda fornecer o seu envelope de pack/volume útil, nunca volume de célula.
- `max_continuous_power_W` permite comparar `peak_W`, conservadoramente sem crédito
  de pulso. Se o pico é conhecido e falta o rating, a triagem fica não avaliada.
  Se o próprio pico é desconhecido, `battery:peak_power` fica não avaliado e o
  booleano só cobre energia/volume/massa alocada, **não prova potência suficiente**.

## Volume aberto e massas sem dupla contagem

`fuel.tank_external_volume_m3` é o envelope instalado, não só o líquido ou volume
interno. Compara-se com `fuel.available_volume_m3`. Para pack usa-se o envelope do
pack completo, deixando folgas, arrefecimento externo, serviço e exclusões fora do
volume líquido disponível declarado. Espaço útil não se deduz do volume bruto da
fuselagem. Há duas opções de restrição, sem listas de posições fixas:

1. `available_volume_m3` por portador, com alocações **disjuntas** declaradas;
2. `storage.shared_available_volume_m3`, que limita a **soma** dos envelopes;
   nesse caso podem omitir-se alocações individuais. Se forem fornecidas, também
   se verificam. Falta de envelope/volume útil é não avaliada, nunca aprovação.

Esta desigualdade escalar é necessária, não suficiente para caber em 3-D. A
colocação/colisões/keep-outs e CG continuam nas ferramentas `integration`/`assembly`.
O relatório dá massa de combustível carregado, pack e `tank_dry_mass_kg` opcional.
Não estima peso de depósito por equações GA; se faltar massa seca, o inventário
total fica nulo. Um inventário parcial não é fecho de massa.

Massa já contada no produtor **não se soma outra vez**. `jet_size` fornece a alocação
de combustível; `vtol_size`, a massa completa da bateria (incluindo limitação por
potência). Quando uma nova carga/pack excede a massa que já estava alocada, falha
`existing_mass_allocation`: é preciso voltar ao dimensionamento. Uma massa menor
não altera automaticamente a massa conservadora usada na missão. A massa seca de
depósito não recebe inclusão fictícia em We; a sua integração continua por demonstrar.

## Adaptadores, não novo suporte de simulação dinâmica

- `jet_size`: exige convergência; usa `weights.trip_burn_kg` e `reserve_fuel_kg`
  uma vez. A reserva do modelo é massa adicional, não uma missão de desvio/espera
  integrada. O utilizador declara separadamente combustível inacessível, sem
  duplicar uma provisão de trapped fuel; as frações empíricas não são decompostas
  automaticamente. Não reutiliza o dimensionamento GA.
- `vtol_size`: usa `energy_Wh` (já elétrica e com sistemas), adiciona a reserva dos
  `inputs_resolved` uma vez; usa o pico existente. **Não** trata `energy_nominal_Wh`
  como energia de viagem nem reaplica o DoD original.
- `mission`: aceita o resultado bruto pointmass/6-DOF ou o envelope `simulate_mission`
  com `summary.total_used` e `unit=kg|Wh`. Exige `aborted=null` e `reserve_fraction`
  explícita, relativa ao consumo observado. Não usa o orçamento inicial já líquido
  de reservas como se fosse consumo. Missão abortada/incompleta ou degradação/falhas
  identificadas fica não avaliada: o consumo parcial não prova a missão completa.
  Não garante que uma simulação não abortada satisfaz todos os objetivos/condições de voo.

Em `jet size` e `vtol size`, um bloco opcional `storage` acrescenta apenas a secção
`storage`; os campos antigos `feasible`, massas, consumos e checks não mudam de
âmbito. Estes CLI antigos mantêm os seus códigos de saída; **ler storage_feasible**
ou usar `acdt storage check` para uma decisão exclusiva desta camada. O resultado
produtor pode falhar noutra disciplina e passar capacidade; ver `producer.source_feasible`.

Campos novos: `storage_feasible` (true/false/null), `capacity_feasible`,
`packaging_feasible`, `checks` com margens/unidades, `issues` e `unassessed`.
Uma falha conhecida prevalece sobre informação em falta (campo omitido ou null).
Não há passe vazio. A comparação usa tolerância numérica relativa de 10⁻¹²
(com piso de uma unidade), não uma margem física de capacidade.

Pendentes: motor/deck de jato e transição VTOL ligados ao simulador dinâmico comum;
missão de reservas operacional; despacho/recarga híbridos e transferências; efeitos
de massa/volume no MDA; CG/sistemas/térmica/segurança detalhados. Esta camada aceita
os dois portadores se forem declaradas duas demandas, **não cria uma política híbrida**.

Fontes verificadas em 7 nov 2026: NIST SP 811 (2008), Apêndice B.8 (1 L=10⁻³ m³,
1 Wh=3600 J); Hepperle (2012), *Electric Flight — Potential and Limitations*, §3.2,
contexto de cadeias energéticas. **Não se atribui a Hepperle uma regra de reserva
ou DoD:** são convenções explícitas deste balanço. URLs em THIRD_PARTY e docstrings.
