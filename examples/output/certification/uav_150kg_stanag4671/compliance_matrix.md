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
