# Tutorial — Fase 10: base de certificação, matriz de conformidade e segurança (ARP4761)

> Avaliação de **projeto conceptual**. O catálogo tem paráfrases do acdt, não o texto oficial; a ligação à fonte
> oficial está em cada linha e prevalece sempre. A aceitação de qualquer meio de conformidade é da autoridade
> (EASA, FAA, autoridade militar). Créditos e fontes: [THIRD_PARTY.md](../THIRD_PARTY.md).

## 1. O que a fase faz

```
missão YAML ──► pipeline (dimensionamento, sistemas, estrutura, controlos…)
              ├─► base de certificação (CS-23 nível/classe, CS-25, STANAG 4671/4703, SORA)
              ├─► FHA → FTA → FMEA (taxas com fonte) → MTBF requerido
              ├─► estudo de redundância (opções) → Δm → ΔW0 → W0 redimensionado
              ├─► SORA 2.5: iGRC → GRC final → ARC → SAIL → OSO → passo #8 contenção (opt-in)
              └─► matriz de conformidade: parágrafo → MoC → evidência acdt → estado (CSV/XLSX/MD + PNG)
```

Comandos:

```bash
pip install -e '.[cert]'                                   # openpyxl, só para o XLSX
acdt certify examples/cessna172_check.yaml -o out/c172     # completo (≈ 40 s)
acdt certify examples/uav_gasoline_150kg.yaml -o out/uav
acdt safety uas --scheme stanag4703 --mtow 136 --t-flight 10 --trade \
     --unit servo_kg=0.18 --unit battery_kg=1.5 --baseline backup_battery=true   # rápido, sem dimensionar
acdt safety ga_piston --scheme ac23_1309_class_I --options standby_altimeter=true
acdt safety sora --input examples/certification/sora_containment_assessed.json -o out/sora.json
acdt safety uas --scheme stanag4671 --mtow 150 --t-flight 10 \
     --supplier-rates examples/certification/supplier_rates_illustrative.json
```

Para agentes de IA (MCP): `certify` (trabalho longo, devolve `run_id`) e `safety_assessment` (rápido; aceita
`sora: {span_m, v_max_m_s, population, aec, mitigations, containment?}` e `supplier_rates`).

## 2. Bloco `certification:` na missão

```yaml
certification:
  basis: stanag4671            # opcional: forçar a base (senão é escolhida pela classe e MTOW)
  max_passenger_seats: 3       # CS 23.2005: nível pelo nº de lugares
  safety:
    t_flight_h: 10.0           # duração média do voo (probabilidade por hora de voo = P(T)/T)
    baseline: {backup_battery: true}   # opções já incluídas na massa do projeto
    unit: {battery_kg: 1.5}    # massas/custos unitários das opções (com fonte)
    options: {}                # forçar opções (o utilizador decide)
    rate_overrides: {}         # legado: {componente: λ por hora} (kind=user; pode não ter data)
    supplier_rates: {}         # {uav_c2_link|uav_flight_computer|uav_two_stroke_engine: {lambda_per_h|mtbf_h, source, retrieved}}
    severity_overrides: {}     # só com justificação escrita (ex.: zona de aterragem de emergência)
  sora:
    population: "<50"          # PRESSUPOSTO se omitido; pessoas/km²
    aec: 5                     # Anexo C (AEC 1–12)
    mitigations: {M2: medium}  # M1A/M1B/M1C/M2: low|medium|high
    containment:               # opt-in, passo #8; omitir → unassessed≠pass
      adjacent_population_density_per_km2: 20
      outdoor_assembly: "<40k" # <40k | 40k-400k | >400k
      sheltering: false        # obrigatório se a coluna for 3 m (Tabelas 9 vs 10)
```

## 3. Base de certificação

* **Tripulado** ≤ 8 618 kg e ≤ 19 lugares → CS-23 Amdt 6 (Part 23 Amdt 23-64). Nível pela CS 23.2005
  (0–1 lugares N1, 2–6 N2, 7–9 N3, 10–19 N4); alta velocidade se VNO/VMO > 250 KCAS ou MMO > 0.6. Classe AC
  23.1309-1E por motor e massa. O C172 (3 lugares de passageiros; VC do projeto usada como VNO, ≤ 250 KCAS) dá **Nível 2, baixa
  velocidade, Classe I**.
* **UAV** ≥ 150 kg → STANAG 4671 (USAR); < 150 kg → STANAG 4703 (AEP-83). Na EASA o UAS vai para a
  categoria específica → **SORA**.
* Fora destes limites → CS-25 (AMC 25.1309).

## 4. Matriz de conformidade

Cada linha: base, parágrafo, título, paráfrase, meios de conformidade (MoC 0–9), evidência do acdt, ferramenta,
estado e fonte oficial. Regra do estado:

| situação | estado |
|---|---|
| sem evidência do acdt | **em aberto** |
| alguma verificação falha | **não conforme** |
| evidência OK e o MoC inclui ensaio (MoC 4–8) | **requer ensaio** |
| evidência OK e só análise / semelhança | **conforme** (determinação feita) |

Os requisitos do cliente (descolagem, subida, alcance) não são requisitos de certificação; aparecem como
"[requisito do projeto: …]" sem mudar o estado. Ficheiros: `compliance_matrix.csv/.xlsx/.md` e
`compliance_summary.png` (barra por estado e faixa por parágrafo).

## 5. Avaliação de segurança (ARP4761 de baixa fidelidade)

1. **FHA**: condições de falha (FC) com severidade e alvo por hora de voo:

   | esquema | catastrófica | perigosa | maior | menor |
   |---|---|---|---|---|
   | AC 23.1309-1E Classe I | 1e-6 | 1e-5 | 1e-4 | 1e-3 |
   | AMC 25.1309 | 1e-9 | 1e-7 | 1e-5 | 1e-3 |
   | STANAG 4671 USAR.1309 | 1e-6 | 1e-5 | 1e-4 | 1e-3 |
   | STANAG 4703 Anexo G | soma catastrófica ≤ 0.0015/MTOW [kg] | — | — | — |

   STANAG 4671 aceita em alternativa "soma das catastróficas ≤ 1e-5/h"; o acdt reporta as duas.
2. **FTA**: árvore gerada da arquitetura (FCC simplex/dupla/tripla 2-de-3, servos por canal com cablagem,
   energia = (gerador OU motor) E bateria). Cortes mínimos por MOCUS, probabilidade exata, importância
   Fussell–Vesely, exposição latente opcional. PNG `fta_<FC>.png`.
3. **FMEA**: `fmea.csv` com cada componente, taxa, FC afetadas, severidade, falha única e tipo de fonte
   (`published`, `vendor_claim`, `assumption`).
4. **MTBF requerido**: para cada FC falhada, o MTBF que o componente dominante precisa. Se nem com
   esse componente perfeito chega, o fator uniforme de todas as taxas.

## 6. Estudo de redundância (opções, não imposições)

São avaliadas todas as combinações de opções (UAS: servo single/dual, FCC simplex/dual/triplex, bateria de
reserva; GA: altímetro e atitude de reserva). Para cada uma: Δm em relação à base (o que já está no orçamento de
massa), ΔW0 = (dW0/dm) × Δm, com dW0/dm medido redimensionando com +1 kg de massa fixa (≈ 1.9–2.1). Escolha:

* o conjunto **mais leve que cumpre todos os alvos** e a regra de falha única catastrófica;
* se nenhum cumpre: o com menos FC em falha, depois menor razão P/alvo, depois menor Δm (reporta-se o
  MTBF requerido). O W0 final é redimensionado com `fixed_mass_kg += Δm`. Gráfico `redundancy_trade.png`.

## 7. SORA 2.5

iGRC pela Tabela 1 (coluna = a mais exigente entre envergadura e velocidade máxima; linha = densidade
populacional), mitigações M1A/M1B/M1C/M2 (Tabela 5, sem descer abaixo do valor de área controlada da coluna),
ARC pela AEC (Anexo C), SAIL pela Tabela 3 (GRC > 7 → categoria certificada), TMPR e robustez de cada OSO
(Tabela 14), assinalando as do projetista. Via de projeto: SAIL IV → DVR da EASA (SC Light-UAS / MoC
Light-UAS.2510-01). **Passo #8 contenção (opt-in):** Tabelas 8–13 e Anexo E § E.4 (EASA AMC1 Article 11).
Raio da área adjacente = distância voada em 3 min a Vmax, piso 5 km e tecto 35 km; MTOM < 250 g → contenção
baixa sem limites adjacentes. A robustez exigida é a mais estrita entre densidade média e ajuntamentos a
1 km. Conformidade Anexo E só com `claimed_robustness` + fonte ou `p_exit_operational_volume_per_fh` com
fonte e data (alvos: low/medium < 1e-3/FH, high < 1e-4/FH). Sem esses inputs o termo fica **unassessed**,
nunca pass silencioso; fora de âmbito ≠ pass. Abrigo em UA > 3 m (Anexo F) não é creditado. **Não
automatizado:** mitigações estratégicas de ar (Anexo C); o Critério #2 (terminação imediata ao sair do
volume operacional) é qualitativo e não é dado como cumprido automaticamente.

Exemplo ilustrativo (`examples/certification/sora_containment_assessed.json`, 5.37 m / 48.5 m/s, SAIL IV,
Tabela 11): raio 8.73 km; densidade 20/km² e ajuntamentos <40k → robustez **low**; P(sair do VO) EXAMPLE
5e-4/FH (PRESSUPOSTO, não é ensaio nem taxa de fornecedor) vs alvo 1e-3/FH → conformidade ok. O mesmo UAV
sem densidade/ajuntamentos (`sora_containment_unassessed.json`) deixa o requisito unassessed.

## 8. Exemplos (saídas em `examples/output/certification/`)

| exemplo | base | conforme / ensaio / não conf. / aberto | FC principais (P/h vs alvo) | redundância | W0 |
|---|---|---|---|---|---|
| `cessna172_check` | CS-23 N2, baixa vel., Classe I | 6 / 14 / 2 / 31 | atitude total 3.1e-7 vs 1e-6 ✔; atitude primária 6.5e-4 vs 1e-4 ✘; altitude 3.3e-8 vs 1e-5 ✔ (com reserva); velocidade 6.9e-5 vs 1e-4 ✔; rumo em aberto | altímetro de reserva (+0.37 kg) | 1137.8 → 1138.5 kg |
| `uav_gasoline_150kg` | STANAG 4703 + SORA | 5 / 10 / 0 / 6 | perda de controlo 3.8e-6 vs 1.1e-5 (acumulado) ✔ | servos duplos + FCC dupla + bateria (Δm 0.91 kg, ΔW0 1.9 kg) | 136.4 → 138.3 kg |
| `uav_150kg_stanag4671` | STANAG 4671 + SORA | 7 / 13 / 1 / 12 | controlo 3.8e-6 vs 1e-6 ✘ (alternativa soma 3.8e-6 ≤ 1e-5 ✔); propulsão 9.9e-4 vs 1e-5 ✘; leme 2.6e-6 vs 1e-4 ✔; C2 em aberto | igual (Δm 0.91 kg) | 153.2 → 155.1 kg |

SORA nos dois UAV (envergadura 5.4 m, VD ≈ 48 m/s → coluna 8 m / 75 m/s; população < 50/km² e AEC 5, ambos
PRESSUPOSTO): iGRC 5 → GRC 5, ARC-c → **SAIL IV**.

Leitura honesta:

* C172: a atitude primária (AI de vácuo + bomba, MTBF da NASA GARS) falha a classe I por um fator 6.5; o
  standby de atitude não ajuda nesta FC (só na perda total) e por isso não foi escolhido. A solução real é um AI
  elétrico/AHRS com MTBF do fornecedor (`rate_overrides`).
* UAV 4671: com um só motor de 2 tempos (taxa 1e-3/h, PRESSUPOSTO) a perda de propulsão "perigosa" exige MTBF
  1e5 h — impossível. Opções: motor com dados melhores, ou reclassificar a severidade **com justificação**
  (aterragem de emergência controlada, paraquedas) via `severity_overrides`.
* Os servos de aileron já são 2 por superfície por partilha de binário: isso não é redundância (nota no
  relatório). O leme não tem servo na base de dados para o binário pedido: a sua massa de redundância fica em aberto.

## 9. Limitações

Taxas constantes (exponencial); sem modos comuns, bloqueio/hardover de servos nem software (DO-178C/DO-254);
sem taxas públicas para C2 e bússola (C2 / FC-U4 só fecha com `supplier_rates` com fonte e data — ver
`examples/certification/supplier_rates_illustrative.json`, valores EXAMPLE/PRESSUPOSTO, não cotações reais;
bússola continua em aberto); motor UAV, FCC, bateria e cablagem são PRESSUPOSTOS na ausência de taxas
citadas de fornecedor; servo pela vida declarada da Volz; controlabilidade com meia superfície é PRESSUPOSTO;
ΔCusto n/d sem preços; SORA passo #8 é opt-in (unassessed ≠ pass); mitigações estratégicas de ar (Anexo C) e
crédito de abrigo > 3 m (Anexo F) não automatizados; o otimizador usa estudo + redimensionamento (as opções
não são variáveis do MDO).
