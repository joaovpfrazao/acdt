# Certificação e segurança — cessna172_check

# Matriz de conformidade (acdt)

> Paráfrases do acdt, não o texto oficial — consultar sempre a fonte oficial ligada. Estado automático a nível de projeto conceptual; a aceitação cabe à autoridade.

**Base(s):** cs23

- tripulado, 3 lugares de passageiros e MTOW 1138 kg ≤ 8 618 kg → CS-23 categoria normal, Nível 2, baixa velocidade (CS 23.2005)

| estado | nº |
|---|---|
| conforme | 6 |
| requer ensaio | 14 |
| não conforme | 2 |
| em aberto | 31 |

**Notas:**
- VNO ≈ VC de projeto = 136 kt EAS≈CAS (PRESSUPOSTO para o nível de desempenho)

## EASA CS-23 Amdt 6 / 14 CFR Part 23 Amdt 23-64 (baseada em desempenho)
Fonte oficial: https://www.easa.europa.eu/en/document-library/certification-specifications/group/cs-23-normal-utility-aerobatic-and-commuter-aeroplanes

| parágrafo | título | MoC | evidência acdt | estado |
|---|---|---|---|---|
| 23.2005 | Certification of normal category airplanes | declaration | Nível 2 (3 passageiros), low speed; AC 23.1309 Classe I | conforme |
| 23.2010 | Accepted means of compliance | declaration | — | em aberto |
| 23.2100 | Weight and center of gravity | analysis/inspection | W0 1137.8 kg, We 709.9 kg; SM no CG traseiro 10.0 % (alvo 10 %; dianteiro 11.8 %) — posicionamento da asa por bisseção | conforme |
| 23.2105 | Performance data | analysis/test | alcance 1297 km, autonomia 5.90 h, envelope e T/O/aterragem calculados | requer ensaio |
| 23.2110 | Stall speed | analysis/test | VS1 = 29.4 m/s EAS (57 kt), CLmax limpo 1.53 | requer ensaio |
| 23.2115 | Takeoff performance | analysis/test | corrida 275 m, até 15 m 459 m [requisito do projeto: OK] | requer ensaio |
| 23.2120 | Climb requirements | analysis/test | gradiente de subida após descolagem 9.5 % vs ≥ 8.3 % (potência de descolagem, configuração de descolagem do modelo — verificar flaps/velocidade da regra) | requer ensaio |
| 23.2125 | Climb information | analysis/test | ROC máx. ao nível do mar: 3.642 m/s vs requerido ≥ 3.708 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento); teto de serviço (Anderson): 4504 m vs requerido ≥ 4115 (missão por segmentos — verificação, não altera a viabilidade do dimensionamento) [requisito do projeto: NÃO cumprido] | requer ensaio |
| 23.2130 | Landing | analysis/test | desde 15 m 504 m, corrida 201 m [requisito do projeto: NÃO cumprido] | requer ensaio |
| 23.2135 | Controllability | analysis/test | CLmax limpo (CG dianteiro): δe -8.1°; cruzeiro (CG dianteiro): δe -3.3°; S_h/S atual 0.201 vs mínimo 0.201 (estabilidade 0.201 no CG traseiro, controlo 0.020 a CLmax no CG dianteiro; dimensionante: estabilidade); rolamento τ_R [s] = 0.232 → Nível 1 (N1: ≤ 1.4; MIL-F-8785C Table VII, Classe I, Cat. B) | requer ensaio |
| 23.2140 | Trim | analysis/test | CLmax limpo (CG dianteiro): δe -8.1°; cruzeiro (CG dianteiro): δe -3.3° | requer ensaio |
| 23.2145 | Stability | analysis/test | SM no CG traseiro 10.0 % (alvo 10 %; dianteiro 11.8 %) — posicionamento da asa por bisseção; Vv = 0.040 / short_period nível 1, dutch_roll nível 1, phugoid nível 1 (amortecido se nível ≤ 2, MIL-F-8785C; nível 2 indica qualidade degradada) | requer ensaio |
| 23.2150 | Stall characteristics, stall warning, and spins | test | — | em aberto |
| 23.2155 | Ground and water handling characteristics | test | — | em aberto |
| 23.2160 | Vibration, buffeting, and high-speed characteristics | test | — | em aberto |
| 23.2200 | Structural design envelope | analysis | VA 57.4, VC 69.9, VD 97.8 m/s EAS; n 3.96/-1.96 (rajada) | conforme |
| 23.2210 | Structural design loads | analysis | n = 3.96 (rajada), q a VD = 97.8 m/s EAS; M raiz 43646 N·m (Schrenk (NACA TM 948)) | conforme |
| 23.2215 | Flight load conditions | analysis | n manobra +3.80 vs mínimo 3.80 (2,1+24000/(W+10000) ≤ 3,8 (ASTM F3116 — verificar revisão)) / n rajada a VC 3.96/-1.96 (μg 24.4, Kg 0.723) | conforme |
| 23.2220 | Ground and water load conditions | analysis/test | — | em aberto |
| 23.2230 | Limit and ultimate loads | analysis | n último / n limite = 1.50 (≥ 1,5) | conforme |
| 23.2235 | Structural strength | analysis/test | caixão da asa dimensionado (buckling), massa 96.9 kg; encurvadura de revestimento OK (só asa — fuselagem/empenagens por fazer) | requer ensaio |
| 23.2240 | Structural durability | analysis/test | — | em aberto |
| 23.2245 | Aeroelasticity | analysis/test | divergência torsional V = 367.0 m/s EAS vs 117.4 (= 1.2 V_D); margem +213 %; inversão de aileron: não ocorre (V → ∞) vs 117.4 m/s EAS; flutter binário V = 155.2 m/s EAS vs 117.4 (= 1.2 V_D); margem +32 %; AEER-45 / 23.629(d): F = 0.000981 vs F_max = 0.00418 (balanceamento do aileron não avaliado) | requer ensaio |
| 23.2250 | Design and construction principles | inspection/analysis | — | em aberto |
| 23.2260 | Materials and processes | analysis/test | admissíveis declarados como PRESSUPOSTO/MMPDS típico nas notas estruturais — valores de projeto estatísticos (A/B-basis) por obter | requer ensaio |
| 23.2265 | Special factors of safety | analysis | — | em aberto |
| 23.2270 | Emergency conditions | analysis/test | — | em aberto |
| 23.2300 | Flight control systems | analysis/test/inspection | CLmax limpo (CG dianteiro): δe -8.1°; cruzeiro (CG dianteiro): δe -3.3°; rolamento τ_R [s] = 0.232 → Nível 1 (N1: ≤ 1.4; MIL-F-8785C Table VII, Classe I, Cat. B) | requer ensaio |
| 23.2305 | Landing gear systems | analysis/test | — | em aberto |
| 23.2315 | Means of egress and emergency exits | inspection/test | — | em aberto |
| 23.2320 | Occupant physical environment | test/inspection | — | em aberto |
| 23.2325 | Fire protection | inspection/test | — | em aberto |
| 23.2330 | Fire protection in designated fire zones | analysis/test | — | em aberto |
| 23.2335 | Lightning protection | analysis/test | — | em aberto |
| 23.2400 | Powerplant installation | analysis/test | P_NM 114.6 kW (motor certificado/qualificado em separado) | requer ensaio |
| 23.2410 | Powerplant installation hazard assessment | analysis | — | em aberto |
| 23.2425 | Powerplant operational characteristics | test | — | em aberto |
| 23.2430 | Fuel systems | analysis/test | — | em aberto |
| 23.2435 | Powerplant induction and exhaust systems | analysis/test | — | em aberto |
| 23.2440 | Powerplant fire protection | analysis/test | — | em aberto |
| 23.2500 | Airplane level systems requirements | analysis | — | em aberto |
| 23.2505 | Function and installation | test/inspection | — | em aberto |
| 23.2510 | Equipment, systems, and installations | analysis/test | 3/4 condições de falha quantificadas cumprem o alvo (ac23_1309_class_I); falham: FC-A2; sem alvo ou em aberto: FC-A5, FC-A6 | não conforme |
| 23.2515 | Electrical and electronic system lightning protection | analysis/test | — | em aberto |
| 23.2520 | High-intensity Radiated Fields (HIRF) protection | analysis/test | — | em aberto |
| 23.2525 | System power generation, storage, and distribution | analysis/test | — | em aberto |
| 23.2530 | External and cockpit lighting | inspection/test | — | em aberto |
| 23.2535 | Safety equipment | inspection | — | em aberto |
| 23.2600 | Flightcrew interface | test/inspection | — | em aberto |
| 23.2605 | Installation and operation information | inspection | — | em aberto |
| 23.2610 | Instrument markings, control markings, and placards | inspection | — | em aberto |
| 23.2615 | Flight, navigation, and powerplant instruments | inspection/analysis | 3/4 condições de falha quantificadas cumprem o alvo (ac23_1309_class_I); falham: FC-A2; sem alvo ou em aberto: FC-A5 | não conforme |
| 23.2620 | Airplane flight manual | inspection | — | em aberto |

## Avaliação de segurança (ARP4761 simplificada) — esquema ac23_1309_class_I

Referência dos alvos: FAA AC 23.1309-1E (2011) Fig. 2. Duração de voo considerada T = 1 h (P/h de voo = P(T)/T).

Opções de arquitetura: altímetro de reserva = True, indicador de atitude de reserva (elétrico) = False

| CF | condição de falha | severidade | alvo [/h] | P [/h] | falha única | estado |
|---|---|---|---|---|---|---|
| FC-A1 | perda total de indicação de atitude (IFR) | catastrófica | 1e-06 | 3.09e-07 | — | cumpre |
| FC-A2 | perda da atitude primária | maior | 1e-04 | 6.50e-04 | ai, vac | não cumpre |
| FC-A3 | perda total de indicação de altitude | perigosa | 1e-05 | 3.31e-08 | — | cumpre |
| FC-A4 | perda total de indicação de velocidade | maior | 1e-04 | 6.88e-05 | asi, pitot | cumpre |
| FC-A5 | perda total de indicação de rumo | maior | 1e-04 | — | — | em aberto |
| FC-A6 | perda de potência do motor (informativo — 23.2100/2405, não 1309) | informativo | — | 1.27e-04 | engine | sem alvo |

MTBF requerido do componente dominante (para cumprir o alvo, restantes inalterados):
- FC-A2: attitude_indicator → inatingível só com attitude_indicator; todas as taxas da árvore teriam de baixar ×0.15 (MTBF ×6.5)

Notas:
- FC-A1: AC 23.1309-1E Apêndice 1 (IFR); o coordenador de volta conta como fonte de atitude de reserva (PRESSUPOSTO conservador do acdt)
- FC-A4: estático alternativo/aquecimento do pitot não modelados
- FC-A5: bússola magnética sem taxa de falha publicada na base de dados (NASA GARS não a lista); giro direcional + vácuo isolados = limite superior conservador

### Estudo de redundância (opções de projeto)

| opções | Δm [kg] | ΔW0 [kg] | Δcusto | pior P/alvo | cumpre |
|---|---|---|---|---|---|
| standby_altimeter=False, standby_attitude=False | 0.00 | 0.00 | 0 | 18 | não |
| standby_altimeter=True, standby_attitude=False | 0.37 | 0.71 | n/d | 6.5 | não |
| standby_altimeter=False, standby_attitude=True | 0.73 | 1.40 | n/d | 18 | não |
| standby_altimeter=True, standby_attitude=True | 1.10 | 2.11 | n/d | 6.5 | não |

**Selecionado:** standby_altimeter=True, standby_attitude=False — NENHUM conjunto de opções cumpre — escolhido o com menos condições em incumprimento; requer componentes mais fiáveis (ver MTBF requerido).
Entradas em falta (não contabilizadas): altimeter_cost.

## FMEA

| componente | λ_modo [1/h] | efeito no sistema (condição de falha) | severidade | ponto único de falha | tipo de dado |
|---|---|---|---|---|---|
| indicador de atitude (vácuo) | 0.0004 | FC-A1, FC-A2 | catastrófica | não | published |
| bomba de vácuo | 0.00025 | FC-A1, FC-A2 | catastrófica | não | published |
| coordenador de volta (elétrico) | 0.000476 | FC-A1 | catastrófica | não | published |
| altímetro | 0.000182 | FC-A3 | perigosa | não | published |
| indicador de velocidade | 5.52e-05 | FC-A4 | maior | não | published |
| tubo de pitot | 1.36e-05 | FC-A4 | maior | não | published |
| giro direcional (vácuo) | 0.000294 | — | sem efeito | não | published |
| alternador | 0.000132 | — | sem efeito | não | published |
| motor (Lycoming, ATSB) | 0.000127 | FC-A6 | sem efeito | não | published |
| altímetro de reserva | 0.000182 | FC-A3 | perigosa | não | published |
