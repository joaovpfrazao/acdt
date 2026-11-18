# Certificação e segurança — uav_gasoline_150kg

# Matriz de conformidade (acdt)

> Paráfrases do acdt, não o texto oficial — consultar sempre a fonte oficial ligada. Estado automático a nível de projeto conceptual; a aceitação cabe à autoridade.

**Base(s):** stanag4703  ·  **SORA:** sim

- UAV com MTOW 136.3 kg → STANAG 4703 (< 150 kg)
- UAS na categoria específica EASA → avaliação SORA (AMC1 Art. 11, Reg. (EU) 2019/947)

| estado | nº |
|---|---|
| conforme | 5 |
| requer ensaio | 10 |
| não conforme | 0 |
| em aberto | 6 |

**Notas:**
- VNO ≈ VC de projeto = 75 kt EAS≈CAS (PRESSUPOSTO para o nível de desempenho)
- EASA SC Light-UAS (Medium Risk): verificação de projeto para operações SAIL III–IV na categoria específica (SAIL III por declaração; SAIL IV com Design Verification Report da EASA) — https://www.easa.europa.eu/en/special-condition-sc-light-uas-medium-risk
- Meios de conformidade EASA (p.ex. MoC Light-UAS.2510-01 para SAIL IV) — https://www.easa.europa.eu/en/document-library/product-certification-consultations/final-means-compliance-uas-2510-01-sail-iv
- SAIL V–VI ou GRC final > 7: certificação de tipo da UAS (categoria certificada / alto risco) — verificar a base aplicável com a EASA; o STANAG 4671 é usado aqui como referência técnica.
- 'CS-LUAS' (JARUS) é uma recomendação, não um código EASA adotado; usar apenas como orientação.
- servo redundante = mesmo servo selecionado (0.180 kg, 5 canais; superfície dividida, PRESSUPOSTO conservador)
- aileron (each): 2 servos por partilha de binário (não redundância); a FTA considera um canal por superfície e a opção 'dual' duplica-os todos
- rudder: sem servo na base de dados para 6.0 N·m — massa da redundância deste canal não contabilizada (em aberto)
- FCC redundante = generic_f7_fc_class (0.01 kg; não certificado — massa de referência)
- SORA: velocidade máxima = V_D 48.5 m/s (PRESSUPOSTO conservador)

## STANAG 4703 Ed. 1 (AEP-83) — UAS ligeiros de asa fixa < 150 kg
Fonte oficial: https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/391827/20140916-STANAG-4703_AEP-83_A__1_.pdf

| parágrafo | título | MoC | evidência acdt | estado |
|---|---|---|---|---|
| UL.1 | Structural design criteria | declaration | VA 38.8, VC 38.8, VD 48.5 m/s EAS; n 4.40/-1.76 (manobra) | conforme |
| UL.2 | Margin beyond operating envelope | analysis | n último / n limite = 1.50 (≥ 1,5) | conforme |
| UL.5 | Flight loads | analysis | n = 4.40 (manobra), q a VD = 48.5 m/s EAS; M raiz 3121 N·m (Schrenk (NACA TM 948)) / n manobra +4.40/-1.76 (critério definido pelo requerente) | conforme |
| UL.6 | Ground loads | analysis/test | — | em aberto |
| UL.7 | Structural dynamic load response | test | — | em aberto |
| UL.8 | Aeroservoelastic effects | analysis/test | divergência torsional V = 267.6 m/s EAS vs 58.1 (= 1.2 V_D); margem +360 %; inversão de aileron: não ocorre (V → ∞) vs 58.1 m/s EAS; flutter binário V = 119.2 m/s EAS vs 58.1 (= 1.2 V_D); margem +105 %; AEER-45 / 23.629(d): F = 0.00158 vs F_max = 0.017 (balanceamento do aileron não avaliado) | requer ensaio |
| UL.9 | Material allowables | analysis | admissíveis declarados como PRESSUPOSTO/MMPDS típico nas notas estruturais — valores de projeto estatísticos (A/B-basis) por obter | conforme |
| UL.11 | Fatigue | analysis/test | — | em aberto |
| UL.16 | Engine | test | P_NM 12.7 kW (motor certificado/qualificado em separado) | requer ensaio |
| UL.19 | Fuel system | analysis/test | — | em aberto |
| UL.20 | Electric power subsystem | analysis/test | — | em aberto |
| UL.30 | System safety assessment | analysis | 1/1 condições de falha quantificadas cumprem o alvo (stanag4703); soma catastrófica 3.8e-06/h vs 1.1e-05 (STANAG 4703 Annex G): cumpre; sem alvo ou em aberto: FC-U2, FC-U3, FC-U4 | conforme |
| UL.41 | Stalling speeds | analysis/test | VS1 = 29.6 m/s EAS (57 kt), CLmax limpo 1.39 | requer ensaio |
| UL.42 | Takeoff / launch | analysis/test | corrida 297 m, até 15 m 507 m [requisito do projeto: OK] | requer ensaio |
| UL.43 | Climb and descent | analysis/test | ROC máx. ao nível do mar: 4.709 m/s vs requerido ≥ 3 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento); teto de serviço (Anderson): 5419 m vs requerido ≥ 5000 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento) [requisito do projeto: OK] | requer ensaio |
| UL.45 | Glide | analysis/test | L/D máx 15.9 → razão de planeio ≈ 16:1 | requer ensaio |
| UL.46 | Landing | analysis/test | desde 15 m 526 m, corrida 221 m | requer ensaio |
| UL.47 | Controllability and Manoeuvrability | analysis/test | CLmax limpo (CG dianteiro): δe -11.3°; cruzeiro (CG dianteiro): δe -8.2°; S_h/S atual 0.107 vs mínimo 0.107 (estabilidade 0.107 no CG traseiro, controlo 0.100 a CLmax no CG dianteiro; dimensionante: estabilidade); rolamento τ_R [s] = 0.203 → Nível 1 (N1: ≤ 1.4; MIL-F-8785C Table VII, Classe I, Cat. B) — UAV: indicativo | requer ensaio |
| UL.48 | Trim | analysis/test | CLmax limpo (CG dianteiro): δe -11.3°; cruzeiro (CG dianteiro): δe -8.2° | requer ensaio |
| UL.50 | Stability | analysis/test | SM no CG traseiro 10.0 % (alvo 10 %; dianteiro 11.3 %) — posicionamento da asa por bisseção; Vv = 0.030 / short_period nível 1, dutch_roll nível 2, phugoid nível 1 (amortecido se nível ≤ 2, MIL-F-8785C; nível 2 indica qualidade degradada) | requer ensaio |
| UL.53 | Emergency recovery capability | analysis/test | — | em aberto |

## Avaliação de segurança (ARP4761 simplificada) — esquema stanag4703

Referência dos alvos: STANAG 4703 (AEP-83) UL.30 + Annex G (cumulative catastrophic). Duração de voo considerada T = 10 h (P/h de voo = P(T)/T).

Opções de arquitetura: servos por eixo (superfície dividida) = dual, computador de voo = dual, bateria de reserva = True

| CF | condição de falha | severidade | alvo [/h] | P [/h] | falha única | estado |
|---|---|---|---|---|---|---|
| FC-U1 | perda de controlo da aeronave | catastrófica | 1e-05 | 3.81e-06 | — | cumpre |
| FC-U2 | perda de propulsão (aterragem forçada) | perigosa | — | 9.95e-04 | engine | sem alvo |
| FC-U3 | perda de controlo direcional (leme) | maior | — | 2.59e-06 | — | sem alvo |
| FC-U4 | perda da ligação C2 (comando e controlo) | maior | — | — | — | em aberto |

Soma das condições catastróficas: 3.81e-06 /h vs 1.10e-05 (STANAG 4703 Annex G) → cumpre

Notas:
- FC-U4: sem taxa de falha pública da ligação C2 — depende do rádio, do espetro e do procedimento de perda de ligação (OSO#06); estado em aberto

### Estudo de redundância (opções de projeto)

| opções | Δm [kg] | ΔW0 [kg] | Δcusto | pior P/alvo | cumpre |
|---|---|---|---|---|---|
| servo=single, fcc=simplex, backup_battery=False | -1.50 | -3.18 | n/d | 1.6e+02 | não |
| servo=single, fcc=dual, backup_battery=False | -1.49 | -3.16 | n/d | 1.5e+02 | não |
| servo=single, fcc=triplex, backup_battery=False | -1.48 | -3.14 | n/d | 1.5e+02 | não |
| servo=dual, fcc=simplex, backup_battery=False | -0.60 | -1.27 | n/d | 1.1e+02 | não |
| servo=dual, fcc=dual, backup_battery=False | -0.59 | -1.25 | n/d | 1e+02 | não |
| servo=dual, fcc=triplex, backup_battery=False | -0.58 | -1.23 | n/d | 1e+02 | não |
| servo=single, fcc=simplex, backup_battery=True | 0.00 | 0.00 | 0 | 56 | não |
| servo=single, fcc=dual, backup_battery=True | 0.01 | 0.02 | n/d | 47 | não |
| servo=single, fcc=triplex, backup_battery=True | 0.02 | 0.04 | n/d | 47 | não |
| servo=dual, fcc=simplex, backup_battery=True | 0.90 | 1.91 | n/d | 9.4 | não |
| servo=dual, fcc=dual, backup_battery=True | 0.91 | 1.93 | n/d | 0.35 | sim |
| servo=dual, fcc=triplex, backup_battery=True | 0.92 | 1.95 | n/d | 0.36 | sim |

**Selecionado:** servo=dual, fcc=dual, backup_battery=True — conjunto mais leve que cumpre todos os alvos quantitativos e a regra de falha única.
Entradas em falta (não contabilizadas): fcc_cost, servo_cost.

## FMEA

| componente | λ_modo [1/h] | efeito no sistema (condição de falha) | severidade | ponto único de falha | tipo de dado |
|---|---|---|---|---|---|
| motor de combustão | 0.001 | FC-U1, FC-U2 | catastrófica | não | assumption |
| gerador acionado pelo motor | 0.000132 | FC-U1 | catastrófica | não | published |
| computador de voo 1 | 0.0001 | FC-U1 | catastrófica | não | assumption |
| computador de voo 2 | 0.0001 | FC-U1 | catastrófica | não | assumption |
| servo profundor 1 | 0.0005 | FC-U1 | catastrófica | não | vendor_claim |
| cablagem profundor 1 | 1e-05 | FC-U1 | catastrófica | não | assumption |
| servo profundor 2 | 0.0005 | FC-U1 | catastrófica | não | vendor_claim |
| cablagem profundor 2 | 1e-05 | FC-U1 | catastrófica | não | assumption |
| servo aileron esq. 1 | 0.0005 | FC-U1 | catastrófica | não | vendor_claim |
| cablagem aileron esq. 1 | 1e-05 | — | sem efeito | não | assumption |
| servo aileron esq. 2 | 0.0005 | FC-U1 | catastrófica | não | vendor_claim |
| cablagem aileron esq. 2 | 1e-05 | — | sem efeito | não | assumption |
| servo aileron dir. 1 | 0.0005 | FC-U1 | catastrófica | não | vendor_claim |
| cablagem aileron dir. 1 | 1e-05 | — | sem efeito | não | assumption |
| servo aileron dir. 2 | 0.0005 | FC-U1 | catastrófica | não | vendor_claim |
| cablagem aileron dir. 2 | 1e-05 | — | sem efeito | não | assumption |
| servo leme 1 | 0.0005 | FC-U3 | maior | não | vendor_claim |
| cablagem leme 1 | 1e-05 | FC-U3 | maior | não | assumption |
| servo leme 2 | 0.0005 | FC-U3 | maior | não | vendor_claim |
| cablagem leme 2 | 1e-05 | FC-U3 | maior | não | assumption |
| bateria de reserva | 0.0001 | FC-U1 | catastrófica | não | assumption |

## SORA 2.5 (vista do projetista)

Fonte: EASA AMC1 Article 11 Reg. (EU) 2019/947 (SORA 2.5), ED Decision 2025/018/R — https://www.easa.europa.eu/en/document-library/acceptable-means-of-compliance-and-guidance-materials/amc-gm-regulation-eu-2019947

- coluna da Tabela 1: 8 m / 75 m/s (envergadura 5.37 m, v_max 48.5 m/s)
- densidade populacional (PRESSUPOSTO do operador): <50 hab/km² → iGRC 5
- mitigações: nenhuma → GRC final 5
- AEC 5: > 120 m AGL, não controlado, sobre zona rural → ARC-c (residual c), TMPR médio
- **SAIL IV** — categoria específica
- via de verificação do projeto: Design Verification Report (DVR) da EASA — SC Light-UAS Medium Risk / MoC Light-UAS.2510-01

| OSO | objetivo | robustez | projetista |
|---|---|---|---|
| OSO#01 | operador competente e/ou com provas dadas | alta |  |
| OSO#02 | UAS projetado e produzido por entidade competente | média | sim |
| OSO#03 | manutenção do UAS | média |  |
| OSO#04 | componentes essenciais projetados segundo uma norma de aeronavegabilidade (ADS) | média | sim |
| OSO#05 | UAS projetado considerando segurança e fiabilidade de sistemas | média | sim |
| OSO#06 | características da ligação C3 adequadas à operação | média | sim |
| OSO#07 | verificação de conformidade da configuração do UAS | média |  |
| OSO#08 | procedimentos operacionais definidos, validados e cumpridos | alta | sim |
| OSO#09 | tripulação remota treinada e atualizada | média |  |
| OSO#13 | serviços externos adequados à operação | alta |  |
| OSO#16 | coordenação multi-tripulação | média |  |
| OSO#17 | tripulação remota apta para operar | média |  |
| OSO#18 | proteção automática do envelope de voo contra erro humano | média | sim |
| OSO#19 | recuperação segura de erro humano | média | sim |
| OSO#20 | avaliação de fatores humanos; HMI adequada | média | sim |
| OSO#23 | condições ambientais para operação segura definidas e mensuráveis | média | sim |
| OSO#24 | UAS projetado e qualificado para condições ambientais adversas | alta | sim |

### Passo #8 — contenção

- estado: requisito unassessed, conformidade unassessed (status unassessed)
- robustez exigida: — (tabela n/d)
- Passo #8 contenção não pedido — requisito e conformidade unassessed (nunca pass silencioso)
- termos unassessed: containment inputs (passo #8 não pedido)

Em aberto:
- Passo #8 contenção (Tabelas 8–13) — por avaliar pelo operador (área adjacente, ajuntamentos); unassessed≠pass
- Mitigações estratégicas de risco aéreo (Anexo C) não aplicadas — ARC residual = ARC inicial
