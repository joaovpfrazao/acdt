# Ruído acústico (disciplina `ruido`, L0)

Estado em 18 nov 2026 (ramo `disc-ruido`). Código: `acdt/core/acoustics/` (núcleo, domínio-agnóstico, mypy
estrito), `acdt/domains/aircraft/noise.py` (etapa do pipeline) e `acdt.api.rotor_noise` (rotores dados
explicitamente, desde a API 1.2.0).

## 1. O que faz

* **Fontes de hélice/rotor**: tons de carga de **Gutin** (harmónicos da frequência de passagem das pás) e banda
  larga de vórtices de **Schlegel, King & Mull**.
* **Propagação**: divergência esférica, **absorção atmosférica ISO 9613-1**, efeito Doppler da fonte em movimento,
  reflexão no solo declarada (0 dB = campo livre).
* **Métricas no observador**: L_p e L_A (**ponderação A IEC 61672-1**) na vertical, **L_A,max** e **L_AE** de uma
  passagem retilínea, espectro por componente.
* **Deteção auditiva**: distância a que a aeronave se ouve, com o **limiar de audição ISO 226:2003** (silêncio) e,
  opcionalmente, ruído ambiente em bandas de 1/3 de oitava. É um tipo de requisito (`aural_detection_range`).
* **Certificação (opcional)**: limites de **14 CFR Parte 36, Apêndice G** (G36.301) com a altura de referência da
  trajetória de dois segmentos (G36.111).
* **Integração**: etapa `noise` do pipeline (depois do desempenho), secção `noise` no `result.json`, disciplina
  `ruido`/L0 no `design.json`, requisitos na matriz de verificação (avaliador `ruido:`), métricas para UQ e MDO,
  quatro casos V&V.

## 2. Métodos e fontes (cada equação conferida com a fonte)

| Peça | Método | Fonte |
|---|---|---|
| Tons de carga | p_m = (mBΩ/(2√2 π c r))·\|T cos θ − Q c/(Ω R_e²)\|·J_mB(mBΩR_e sin θ/c), R_e = 0,8 R | Gutin (1936), NACA TM 1195; Garrick & Watkins, NACA Report 1198 (1954), Eq. 31–34 com V = 0; Marte & Kurtz, JPL TR 32-1462 (1970), Eq. (1) |
| Banda larga | SPL₃₀₀ft = 10 log(6,1×10⁻²⁷ A_b V₀,₇⁶/10⁻¹⁶) + 20 log(C_L/0,4); f_pico = V₀,₇·0,28/h; espectro de oitavas da Fig. 10a | Schlegel, King & Mull (1966), USAAVLABS TR 66-4, em Marte & Kurtz (1970) Eq. (3), Fig. 10a e Apêndice C |
| Absorção | α(f, T, HR, p), Eq. 3–5 e Anexo B | ISO 9613-1:1993 |
| Ponderação A | Eq. (E.6), f1…f4, A1000 = −2,000 dB | IEC 61672-1:2013, Anexo E |
| Limiar de audição | T_f (50 % de deteção, binaural, campo livre, 18–25 anos), 20 Hz – 12,5 kHz | ISO 226:2003, Tabela 1 |
| Doppler | f_obs = f/(1 − M cos θ) | Marte & Kurtz (1970), Apêndice C, passo 11 |
| Limites Parte 36 | G36.301(b): 76 dB(A) até 600 kg, +9,83/duplicação até 88; (c): 70 até 570 kg, +10,75/duplicação até 85 | 14 CFR 36 Ap. G (eCFR) |
| Altura de referência | 15 m (50 ft) + (2500 m − d₁₅)·tan γ a V_y com potência de descolagem | 14 CFR 36 Ap. G, G36.111 |
| Microfone sobre placa | +6,02 dB (duplicação de pressão numa fronteira rígida) | G36.107(a); Kinsler et al., *Fundamentals of Acoustics*, 4.ª ed. |

A forma SI de Gutin foi conferida com a forma de engenharia em unidades inglesas (169,3 = 478,8/(2√2); o 0,76 do
termo de binário corresponde a c ≈ 1131 ft/s): `tests/test_noise.py`.

## 3. Pressupostos (PRESSUPOSTO) e limites

* **Fontes não modeladas**: ruído de espessura, de motor (escape do motor térmico, motor elétrico), de célula e de
  interação pá-esteira. O nível e o alcance calculados são **limites inferiores**. `sources_complete` só fica
  verdadeiro quando o utilizador declara `noise.other_sources: {status: desprezaveis | incluidas, justification: …}`.
  Até lá, um requisito `max` que o limite inferior já excede **falha**, e um que cumpre fica **desconhecido**,
  nunca passa. O mesmo vale para a verificação da Parte 36. `noise.engine_noise` junta um espectro medido do motor
  (bandas de oitava a uma distância, com fonte).
* Gutin estático (sem efeito convectivo do voo); eixo da hélice alinhado com a trajetória; rotores iguais somados
  como fontes incoerentes (+10 log n).
* Validade de Gutin (Marte & Kurtz 1970): bom acordo nos primeiros harmónicos a velocidades de ponta moderadas;
  com M_tip entre 0,5 e 0,3 subestima (domina a banda larga); acima de M_tip helicoidal 0,8 dominam espessura e
  compressibilidade. As duas situações aparecem em `noise.validity`.
* Banda larga: constante «not firmly established» (Marte & Kurtz), ±10 dB a 500 ft; omnidirecional; área das pás =
  área em planta fora do corte de raiz; t/c do perfil das coordenadas do mesmo perfil da hélice (base UIUC via
  AeroSandbox) e α a 0,7 R da solução BEMT. Sem t/c ou α a banda larga fica fora da soma e as fontes ficam
  incompletas.
* Atmosfera homogénea com as condições do solo (por omissão a de referência da Parte 36: 15 °C, 70 %,
  101,325 kPa). Sem refração, turbulência, atenuação do solo nem barreiras.
* Sobrevoo: empuxo = arrasto a W0 (o caso de maior empuxo) à altitude e velocidade da perna de espera (ou de
  cruzeiro).
* Deteção: pior direção da fonte a cada distância (limite superior do alcance). Com ruído ambiente a regra «nível ≥
  banda ambiente + margem» **não** é o modelo de deteção de sinais de Fidell et al. (1974) e pode subestimar o
  alcance; por isso o alcance em silêncio é sempre reportado. Fora de 20 Hz – 12,5 kHz não há limiar (componente
  ignorado na deteção).
* Bandas acima de 10 kHz ficam fora da gama da ISO 9613-1 e são listadas em `absorption_out_of_validity`.
* Jatos: sem método citado implementado (não avaliado). Hamilton Standard / SAE AIR1407 e Hanson: não
  implementados (documentos não verificados).

## 4. Como usar

Na missão (precisa de `assumptions.propulsion.propeller`, o mapa BEMT de passo fixo):

```yaml
requirements:
  noise: {max: 45, unit: dBA, id: NZ-01, text: "L_A,max ≤ 45 dB(A) na vertical em espera"}
  aural_detection_range: {max: 2, unit: km, id: NZ-02, text: "Inaudível a mais de 2 km (silêncio)"}
assumptions:
  noise:
    T_C: 15
    rh_pct: 70
    flyover_altitude_m: 1500          # por omissão a altitude da perna de espera / cruzeiro
    ambient_third_octave_dB: {100: 35, 125: 33, 160: 31}   # opcional, medido, com fonte
    other_sources: {status: desprezaveis, justification: "motor elétrico; medição …"}
    certification: {part36_G: {single_engine_application_after_2006: true}}
```

Avaliadores: `ruido:overhead_LAmax_dBA` (omissão de `noise`), `ruido:detection_ground_range_m` (omissão de
`aural_detection_range`), e qualquer escalar da secção, p. ex. `ruido:SEL_dBA`, `ruido:part36_G.LAmax_dBA`. UQ e MDO:
`result_metrics: {LAmax: noise.overhead_LAmax_dBA, deteccao: noise.detection_ground_range_m}` ou `req:<ID>`.

Rotores dados explicitamente (multirrotor, VTOL, hélice sem mapa BEMT):

```python
from acdt import api
r = api.rotor_noise(blades=2, diameter_m=0.6, rpm=6000, thrust_N=60, power_W=3000, n_rotors=4,
                    altitude_m=100, blade_area_m2=0.02, projected_thickness_m=0.004)
r["overhead_LA_dBA"], r["detection_ground_range_quiet_m"]
```

## 5. V&V (`acdt vv --discipline ruido`)

| Caso | Referência | Resultado |
|---|---|---|
| `NOISE-SKM-EXAMPLE` | Exemplo do Apêndice C de Marte & Kurtz (1970): 78,7 dB a 300 ft, 68,2 dB a 1000 ft, f = 556 Hz, banda do pico 64,2 dB | passa (78,75 / 68,30 / 557,4 Hz / 64,30) |
| `NOISE-AWEIGHT` | IEC 61672-1 Tabela 3, oitavas de 31,5 Hz a 16 kHz | passa (desvio máx. 0,04 dB) |
| `NOISE-ISO9613-ALPHA` | Tabela de α calculada com a ISO 9613-1 (4 atmosferas × 7 oitavas) | passa |
| `NOISE-P36G-LIMITS` | Texto de G36.301(b) e (c) | passa (exato) |

Não há ainda caso de **validação** contra medições de ruído de hélice com citação (seguimento).

## 6. Exemplo (teste, não muda o projeto)

`examples/cessna172_check.yaml` (corrida normal do exemplo, sem alterar o projeto; `certification.part36_G` só nesta corrida de teste):

| Grandeza | Valor |
|---|---|
| sobrevoo | 2438 m, 62,8 m/s, 2700 rpm, aceleração total |
| L_A,max / L_AE | 46,2 dB(A) / 60,4 dB(A) (limites inferiores) |
| alcance de deteção em silêncio | 27,5 km no solo (tom fundamental de 90 Hz; sem refração nem atenuação do solo) |
| aviso de validade | M_tip helicoidal 0,85 > 0,8 (espessura não modelada) |
| Parte 36 Ap. G | MTOW 1138 kg → limite 80,7 dB(A) (G36.301(c)); altura de referência 204 m; L_A,max 70,8 dB(A) → desconhecido (limite inferior) |

## 7. Seguimentos

* Validação contra medições publicadas (p. ex. níveis da Parte 36 de aviões certificados, ou medições de hélices
  de UAV em túnel), com citação.
* Ruído de espessura (Deming) e efeito do voo (Garrick & Watkins com V ≠ 0) ou Hanson, se verificados.
* Ruído de motor (escape) por método citado; jatos (SAE ARP876) se verificado.
* Modelo de deteção de Fidell et al. (1974) quando o artigo original for consultado (coeficientes exatos).
* ICAO Anexo 16 Vol. I Cap. 10 quando o texto for verificado.
* Ligar ao `acdt vtol` (ponto de pairar) e ao estudo de frota.
