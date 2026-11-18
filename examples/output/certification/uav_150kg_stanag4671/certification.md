# Certificação e segurança — uav_150kg_stanag4671

# Matriz de conformidade (acdt)

> Paráfrases do acdt, não o texto oficial — consultar sempre a fonte oficial ligada. Estado automático a nível de projeto conceptual; a aceitação cabe à autoridade.

**Base(s):** stanag4671  ·  **SORA:** sim

- UAV com MTOW 153.2 kg → STANAG 4671 (USAR.1: 150–20 000 kg)
- UAS na categoria específica EASA → avaliação SORA (AMC1 Art. 11, Reg. (EU) 2019/947)

| estado | nº |
|---|---|
| conforme | 6 |
| requer ensaio | 13 |
| não conforme | 3 |
| em aberto | 11 |

**Notas:**
- VNO ≈ VC de projeto = 75 kt EAS≈CAS (PRESSUPOSTO para o nível de desempenho)
- EASA SC Light-UAS (Medium Risk): verificação de projeto para operações SAIL III–IV na categoria específica (SAIL III por declaração; SAIL IV com Design Verification Report da EASA) — https://www.easa.europa.eu/en/special-condition-sc-light-uas-medium-risk
- Meios de conformidade EASA (p.ex. MoC Light-UAS.2510-01 para SAIL IV) — https://www.easa.europa.eu/en/document-library/product-certification-consultations/final-means-compliance-uas-2510-01-sail-iv
- SAIL V–VI ou GRC final > 7: certificação de tipo da UAS (categoria certificada / alto risco) — verificar a base aplicável com a EASA; o STANAG 4671 é usado aqui como referência técnica.
- 'CS-LUAS' (JARUS) é uma recomendação, não um código EASA adotado; usar apenas como orientação.
- servo redundante = mesmo servo selecionado (0.180 kg, 5 canais; superfície dividida, PRESSUPOSTO conservador)
- aileron (each): 2 servos por partilha de binário (não redundância); a FTA considera um canal por superfície e a opção 'dual' duplica-os todos
- rudder: sem servo na base de dados para 7.7 N·m — massa da redundância deste canal não contabilizada (em aberto)
- FCC redundante = generic_f7_fc_class (0.01 kg; não certificado — massa de referência)
- SORA: velocidade máxima = V_D 48.5 m/s (PRESSUPOSTO conservador)

## STANAG 4671 Ed. 1 (USAR) — UAV de asa fixa 150–20 000 kg
Fonte oficial: https://nso.nato.int

| parágrafo | título | MoC | evidência acdt | estado |
|---|---|---|---|---|
| USAR.1 | Applicability | declaration | UAV, MTOW 153.2 kg | conforme |
| USAR.25 | Weight Limits | analysis/inspection | W0 153.2 kg, We 93.3 kg; SM no CG traseiro 10.0 % (alvo 10 %; dianteiro 11.0 %) — posicionamento da asa por bisseção; 4 carregamento(s) fora dos limites conceptuais; extremos 0.707 m (combustível, 115 kg) e 0.711 m (vazio, 93 kg). Os limites são de projeto (margem estática e trim), não um envelope aprovado. | não conforme |
| USAR.49 | Stalling Speed | analysis/test | VS1 = 29.5 m/s EAS (57 kt), CLmax limpo 1.40 | requer ensaio |
| USAR.53 | Take-off Performance | analysis/test | corrida 297 m, até 15 m 502 m [requisito do projeto: OK] | requer ensaio |
| USAR.65 | Climb: All Engines Operating | analysis/test | gradiente de subida após descolagem 8.4 % vs ≥ 5.0 % (potência de descolagem, configuração de descolagem do modelo — verificar flaps/velocidade da regra) | requer ensaio |
| USAR.71 | Glide | analysis/test | L/D máx 16.6 → razão de planeio ≈ 17:1 | requer ensaio |
| USAR.75 | Landing Distance | analysis/test | desde 15 m 526 m, corrida 222 m | requer ensaio |
| USAR.143 | General (controllability) | analysis/test | CLmax limpo (CG dianteiro): δe -12.3°; cruzeiro (CG dianteiro): δe -9.0°; S_h/S atual 0.103 vs mínimo 0.131 (estabilidade 0.103 no CG traseiro, controlo 0.131 a CLmax no CG dianteiro; dimensionante: controlo); rolamento τ_R [s] = 0.202 → Nível 1 (N1: ≤ 1.4; MIL-F-8785C Table VII, Classe I, Cat. B) — UAV: indicativo | não conforme |
| USAR.161 | Trim | analysis/test | CLmax limpo (CG dianteiro): δe -12.3°; cruzeiro (CG dianteiro): δe -9.0° | requer ensaio |
| USAR.171 | General (stability) | analysis/test | SM no CG traseiro 10.0 % (alvo 10 %; dianteiro 11.0 %) — posicionamento da asa por bisseção; Vv = 0.030 / short_period nível 1, dutch_roll nível 2, phugoid nível 1 (amortecido se nível ≤ 2, MIL-F-8785C; nível 2 indica qualidade degradada) | requer ensaio |
| USAR.201 | Wings Level Stall | test | — | em aberto |
| USAR.251 | Vibration and Buffeting | test | — | em aberto |
| USAR.301 | Loads | analysis | n = 4.40 (manobra), q a VD = 48.5 m/s EAS; M raiz 3699 N·m (Schrenk (NACA TM 948)) | conforme |
| USAR.303 | Factor of Safety | analysis | n último / n limite = 1.50 (≥ 1,5) | conforme |
| USAR.305 | Strength and Deformation | analysis/test | caixão da asa dimensionado (buckling), massa 5.4 kg; encurvadura de revestimento OK (só asa — fuselagem/empenagens por fazer) | requer ensaio |
| USAR.333 | Flight Envelope | analysis | VA 38.8, VC 38.8, VD 48.5 m/s EAS; n 4.40/-1.76 (manobra) | conforme |
| USAR.337 | Limit Manoeuvring Load Factors | analysis | n manobra +4.40 vs mínimo 3.80 (USAR.337) | conforme |
| USAR.341 | Gust Load Factors | analysis | n rajada a VC 3.28/-1.28 (μg 81.3, Kg 0.826) | conforme |
| USAR.471 | General (ground loads) | analysis/test | W_aterragem 146 kg (95 % de W0; 14 CFR 23.473(b) permite 95 % sem verificar a cláusula de combustível); W/S 14.79 lb/ft²; V = 8.63 ft/s (2.63 m/s, 23.473(d)); n_inércia 3.67; n_reação 3.00; curso 0.171 m para n_g = 3.00 (fator já usado no peso, com pisos de 14 CFR 23.473(g)); η = 0.80 (oleo); κ = 0.667 (teto regulamentar 2/3). Sem sustentação da asa o curso sobe para 0.252 m. Spin-up, mola de retorno, carga lateral e travões não entram neste passo. | requer ensaio |
| USAR.573 | Damage tolerance and fatigue evaluation of structure | analysis/test | — | em aberto |
| USAR.613 | Material strength properties and design values | analysis/test | admissíveis declarados como PRESSUPOSTO/MMPDS típico nas notas estruturais — valores de projeto estatísticos (A/B-basis) por obter | requer ensaio |
| USAR.629 | Flutter | analysis/test | divergência torsional V = 260.0 m/s EAS vs 58.1 (= 1.2 V_D); margem +347 %; inversão de aileron: não ocorre (V → ∞) vs 58.1 m/s EAS; flutter binário V = 116.0 m/s EAS vs 58.1 (= 1.2 V_D); margem +99 %; AEER-45 / 23.629(d): F = 0.00167 vs F_max = 0.017 (balanceamento do aileron não avaliado) | requer ensaio |
| USAR.671 | General (control systems) | analysis/test | CLmax limpo (CG dianteiro): δe -12.3°; cruzeiro (CG dianteiro): δe -9.0°; rolamento τ_R [s] = 0.202 → Nível 1 (N1: ≤ 1.4; MIL-F-8785C Table VII, Classe I, Cat. B) — UAV: indicativo | requer ensaio |
| USAR.903 | Engines and auxiliary power units | analysis/test | P_NM 14.2 kW (motor certificado/qualificado em separado) | requer ensaio |
| USAR.951 | General (fuel system) | analysis/test | — | em aberto |
| USAR.1309 | Equipment, systems and installations | analysis/test | 1/3 condições de falha quantificadas cumprem o alvo (stanag4671); falham: FC-U1, FC-U2; soma catastrófica 3.8e-06/h vs 1.0e-05 (STANAG 4671 AMC.1309 (alternativa: soma ≤ 1e-5)): cumpre; sem alvo ou em aberto: FC-U4 | não conforme |
| USAR.1351 | General (electrical) | analysis/test | — | em aberto |
| USAR.1353 | Storage battery or emergency power supply design and installation | analysis/test | — | em aberto |
| USAR.U1412 | Emergency recovery capability | analysis/test | — | em aberto |
| USAR.U1490 | General (flight termination) | analysis/test | — | em aberto |
| USAR.U1601 | General (C2 data link) | analysis/test | — | em aberto |
| USAR.U1613 | Command and control data link loss strategy | analysis/test | — | em aberto |
| USAR.U1701 | General (UCS) | analysis/test/inspection | — | em aberto |

## Avaliação de segurança (ARP4761 simplificada) — esquema stanag4671

Referência dos alvos: STANAG 4671 Ed. 1 USAR.1309 / AMC.1309 (Annex A definitions). Duração de voo considerada T = 10 h (P/h de voo = P(T)/T).

Opções de arquitetura: servos por eixo (superfície dividida) = dual, computador de voo = dual, bateria de reserva = True

| CF | condição de falha | severidade | alvo [/h] | P [/h] | falha única | estado |
|---|---|---|---|---|---|---|
| FC-U1 | perda de controlo da aeronave | catastrófica | 1e-06 | 3.81e-06 | — | não cumpre |
| FC-U2 | perda de propulsão (aterragem forçada) | perigosa | 1e-05 | 9.95e-04 | engine | não cumpre |
| FC-U3 | perda de controlo direcional (leme) | maior | 1e-04 | 2.59e-06 | — | cumpre |
| FC-U4 | perda da ligação C2 (comando e controlo) | maior | 1e-04 | — | — | em aberto |

Soma das condições catastróficas: 3.81e-06 /h vs 1.00e-05 (STANAG 4671 AMC.1309 (alternativa: soma ≤ 1e-5)) → cumpre

MTBF requerido do componente dominante (para cumprir o alvo, restantes inalterados):
- FC-U1: uav_servo → inatingível só com uav_servo; todas as taxas da árvore teriam de baixar ×0.51 (MTBF ×1.96)
- FC-U2: uav_two_stroke_engine → 1e+05 h (atual 1e+03 h)

Notas:
- FC-U4: sem taxa de falha pública da ligação C2 — depende do rádio, do espetro e do procedimento de perda de ligação (OSO#06); estado em aberto

### Estudo de redundância (opções de projeto)

| opções | Δm [kg] | ΔW0 [kg] | Δcusto | pior P/alvo | cumpre |
|---|---|---|---|---|---|
| servo=single, fcc=simplex, backup_battery=False | -1.50 | -3.16 | n/d | 1.7e+03 | não |
| servo=single, fcc=dual, backup_battery=False | -1.49 | -3.14 | n/d | 1.6e+03 | não |
| servo=single, fcc=triplex, backup_battery=False | -1.48 | -3.12 | n/d | 1.6e+03 | não |
| servo=dual, fcc=simplex, backup_battery=False | -0.60 | -1.27 | n/d | 1.2e+03 | não |
| servo=dual, fcc=dual, backup_battery=False | -0.59 | -1.24 | n/d | 1.1e+03 | não |
| servo=dual, fcc=triplex, backup_battery=False | -0.58 | -1.22 | n/d | 1.1e+03 | não |
| servo=single, fcc=simplex, backup_battery=True | 0.00 | 0.00 | 0 | 6.1e+02 | não |
| servo=single, fcc=dual, backup_battery=True | 0.01 | 0.02 | n/d | 5.1e+02 | não |
| servo=single, fcc=triplex, backup_battery=True | 0.02 | 0.04 | n/d | 5.1e+02 | não |
| servo=dual, fcc=simplex, backup_battery=True | 0.90 | 1.90 | n/d | 1e+02 | não |
| servo=dual, fcc=dual, backup_battery=True | 0.91 | 1.92 | n/d | 1e+02 | não |
| servo=dual, fcc=triplex, backup_battery=True | 0.92 | 1.94 | n/d | 1e+02 | não |

**Selecionado:** servo=dual, fcc=dual, backup_battery=True — NENHUM conjunto de opções cumpre — escolhido o com menos condições em incumprimento; requer componentes mais fiáveis (ver MTBF requerido).
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

- coluna da Tabela 1: 8 m / 75 m/s (envergadura 5.68 m, v_max 48.5 m/s)
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
