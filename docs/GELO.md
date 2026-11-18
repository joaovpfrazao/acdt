# Gelo (disciplina `gelo`, L0/L1)

Estado em 18 nov 2026 (ramo `disc-gelo`). Código: `acdt/core/icing/` (núcleo, domínio-agnóstico, mypy estrito),
`acdt/domains/aircraft/icing.py` (etapa `icing` do pipeline e acoplamento) e `acdt.api.icing` /
`acdt.api.icing_envelope` (especificação genérica, desde a API 1.4.0).

## 1. O que faz

* **Envelopes de projeto do 14 CFR Parte 25, Apêndice C**: contínuo máximo (nuvens estratiformes, 17,4 nmi) e
  intermitente máximo (cumuliformes, 2,6 nmi) — LWC × MVD × temperatura, fator de extensão horizontal F — e o gelo de
  descolagem (0,35 g/m³, 20 µm, −9 °C, até 1500 ft). Envelope altitude–temperatura (Figs. 2 e 5).
* **Linha de estagnação** de cada superfície (asa, estabilizadores, sondas, cilindros): temperatura total,
  captação β₀ (Langmuir & Blodgett), fração de congelação n₀ e tipo de gelo (rime/glaze/sem gelo, Messinger), taxa
  de acreção e espessura acumulada.
* **Tempo de exposição** a partir dos segmentos da missão (só os pontos dentro do envelope).
* **Potência de proteção**: anti-gelo térmico (running-wet mínimo e evaporativo à temperatura de superfície
  declarada), degelo eletrotérmico (ciclo de trabalho, tira de separação), botas (desconhecido); potência elétrica
  acoplada ao balanço elétrico.
* **Penalização aerodinâmica** só como intervalo publicado (razão de C_L,max e fator da velocidade de perda);
  ΔC_D0 desconhecido.
* **Integração**: etapa `icing` do pipeline (depois da térmica, antes do relatório), secção `icing` no
  `result.json`, disciplina `gelo`/L0 no `design.json`, requisitos `ice_protection_power`, `max_ice_thickness` e
  `flight_into_known_icing`, avaliador `gelo:` na matriz de verificação, métricas para UQ/MDO pelos caminhos
  `icing.*` (p. ex. `icing.max_thickness_mm.hi`, `icing.protection.power_W.hi`, `icing.exposure_s.hi`), quatro
  casos V&V.

## 2. Métodos e fontes (cada equação e coeficiente conferidos com a fonte)

| Peça | Método | Fonte |
|---|---|---|
| LWC × MVD × T (Figs. 1 e 4) | valores à distância padrão transcritos exatamente; bilinear em (T, MVD) entre nós — PRESSUPOSTO | 14 CFR 25 Ap. C via Jeck, DOT/FAA/AR-00/30 (FAA, 2002), Tabelas 1 e 2 |
| Fator F (Figs. 3 e 6) | nós de Jeck; linear em log(HE) — PRESSUPOSTO | idem |
| Gelo de descolagem | 0,35 g/m³, 20 µm, −9 °C, solo–1500 ft | 14 CFR 25 Ap. C, Parte I(c) (eCFR) |
| Envelope altitude–T (Figs. 2 e 5) | vértices lidos na grelha da figura: Fig. 2 (0 ft, 32 °F), (12 000, 32), (22 000, −4), (22 000, −22), (0, −22); Fig. 5 sólido (4000, 26), (12 000, 26), (22 000, −10), (22 000, −22), (14 000, −22), (4000, 14), tracejado até (19 000, −40) e (30 000, −40) | Figs. 2 e 5 reproduzidas em Jeck — **leitura gráfica**, banda ±500 ft/±2 °F → `fronteira` |
| Propriedades | c_p,a = 0,240 cal/(g·K); k_a, μ_a, D_v, p_sat (água/gelo, Pruppacher & Klett), c_p,ws, Λ_f, Λ_v, ρ_i = 917 kg/m³ | Anderson, *Manual of Scaling Methods*, NASA/CR-2004-212875 (2004), Ap. A, Eq. (A.1)–(A.29) |
| Temperatura/pressão | T_tot = T_st + V²/(2c_p,a); p_st compressível | idem, Eq. (A.16), (A.7) |
| Inércia | K = ρ_w δ² V/(18 d μ_a); d = diâmetro ou 2 r_le | Langmuir & Blodgett (1946) via Anderson Eq. (3.5) |
| Alcance | λ/λ_Stokes = 1/(0,8388 + 0,001483 Re_δ + 0,1847 √Re_δ) (±0,2 % para 14 ≤ Re_δ ≤ 600) | idem, Eq. (3.12) |
| Inércia modificada | K₀ = 1/8 + (λ/λ_Stokes)(K − 1/8); K ≤ 1/8 → sem impacto | idem, Eq. (3.8) |
| Captação | β₀ = 1,40 (K₀ − 1/8)^0,84/(1 + 1,40 (K₀ − 1/8)^0,84); vs LEWICE −4,7 %…+0,23 % | idem, Eq. (3.13) |
| Raio do bordo de ataque | r_le = 1,1019 t² c (NACA 4 dígitos) | Abbott & von Doenhoff (1959); Anderson Ap. B (1,58 % para o 0012) |
| Convecção | Nu = 1,14 Pr^0,4 Re^0,5 (estagnação de cilindro, Kreith), propriedades à T de filme | Anderson Eq. (3.32)–(3.35) |
| Massa | h_G = (h_c/c_p,a)(Pr/Sc)^0,67 | idem, Eq. (3.47)–(3.48) |
| Balanço de Messinger | b = LWC V β₀ c_p,ws/h_c; φ = t_f − t_st − V²/(2c_p,ws); θ (forma compressível de Ruff); n₀ = (c_p,ws/Λ_f)(φ + θ/b) | Messinger (1953) via Anderson Eq. (3.55)–(3.59) |
| Espessura | Δ = n₀ β₀ LWC V τ/ρ_i; A_c = LWC V τ/(ρ_i d) | Anderson Eq. (3.23), (3.26), (3.29) |
| Anti-gelo running-wet mínimo | q = h_c θ + ṁ c_p,ws φ = n₀ ṁ Λ_f (superfície a 0 °C, n = 0) | balanço de Messinger sem congelação (Anderson Eq. 3.52–3.59) |
| Anti-gelo evaporativo | q_fe(T_s) = h_c(T_s − T_st − V²/2c_p,a) + ṁ[c_p,ws(T_s − T_st) + Λ_v(T_s)] − ṁV²/2 | idem + Eq. (A.21)–(A.22) |
| Degelo eletrotérmico | P ≥ q_rw,min (A_cíclica·ciclo + A_tira); majorante com densidade do aquecedor declarada | idem — PRESSUPOSTO |
| Penalização | C_l,max com gelo/limpo ∈ [0,52; 1,28]/1,85 = [0,281; 0,692]; V_s ∝ 1/√C_L,max | Broeren et al., NASA/TP-2011-216929 (2011), NACA 23012, Re 15,9×10⁶, M 0,20 |

Não se usa LEWICE nem outro código de acreção em processo. SAE AIR1168/4 não foi usado (não verificável).
O Apêndice O (gotas grandes, SLD) **não** está implementado: não foi possível verificar tabelas transcritas — fica
como seguimento.

## 3. Completude: desconhecido ≠ zero, não avaliado ≠ passa

Segue o padrão do ruído e da térmica ([RUIDO.md](RUIDO.md), [TERMICA.md](TERMICA.md)):

* **Varrimento**: para cada condição, envelopes (contínuo e intermitente por omissão; descolagem se pedido),
  temperaturas do envelope àquela altitude (extremos e nós 0/−10/−20/−30 °C) e MVD 15–40 µm. O resultado é o
  **caso crítico** (máximo) com intervalo `{lo, hi}`.
* **Espessura**: `hi` com β₀/0,953 (desvio publicado vs LEWICE), ρ_i = 0,9 × 917 kg/m³ («talvez até 10 %»,
  Anderson Eq. A.27) e a condição inteira em gelo (HE = V·τ, F ajustado; contínuo acima de 300 nmi com F(300) —
  conservador; abaixo de 5 nmi majorante LWC(5 nmi)·5/HE; intermitente limitado a 5 nmi); `lo` com β₀/1,0023,
  917 kg/m³ e exposição só à distância padrão. Superfície sem proteção acumula ao longo da missão: `hi` = soma das
  condições, `lo` = maior encontro isolado.
* **Fronteiras do envelope** lidas da figura (`fronteira`, `possivel`) contam para `hi` mas não para `lo`.
* Fora das tabelas (T < −30 °C, MVD fora de 15–40 µm, HE fora da gama) → `None` com a razão. Acima de 0 °C não
  há gelo de projeto do Apêndice C (espessura 0, não desconhecida).
* **Potência**: área, ciclo de trabalho ou temperatura de superfície em falta → `None`; o total fica `None` se
  alguma parcela o for. Botas pneumáticas: desconhecido.
* **Gelo residual** em superfícies protegidas (retorno/runback, intercíclico): desconhecido; `max_thickness_*`
  refere-se só às superfícies sem proteção.
* **FIKI** (`flight_into_known_icing: sim`): falha se uma superfície crítica sem proteção acumula gelo (minorante
  > 0); caso contrário fica `desconhecido` — uma análise L0 não demonstra o 14 CFR 25.1419. `nao` passa por
  declaração.
* Requisito `max`: passa se `hi` ≤ limiar; falha se `lo` > limiar; senão `desconhecido`.

## 4. Pressupostos (PRESSUPOSTO) e limites

* Ar saturado em relação à água (p_w = p_sat(T_st)); superfície vidrada a 0 °C; radiação, sublimação, condução e
  retorno desprezados no balanço (Anderson §3.5).
* Geometria limpa durante toda a acreção (β₀ e h_c não mudam com o gelo).
* Fluxo da estagnação aplicado a toda a área protegida (convecção e captação máximas na estagnação).
* c_p,ws (Eq. A.2) extrapolada acima de 40 °F na superfície do anti-gelo evaporativo (assinalado).
* Superfícies por omissão com perfil NACA de 4 dígitos (r_le = 1,1019 t² c) e d = 2 r_le na corda média.
* Encontros mistos contínuo + intermitente não combinados.
* Altitude dos segmentos tratada como altitude-pressão ISA (pressão estática da ISA).
* Penalização de um único perfil transferida para a asa em estudo.

Achado ao transcrever: a Tabela 3 de Jeck dá 0,398 para intermitente −30 °C/35 µm, mas a Tabela 1 dá
0,350/1,100 = 0,318; o módulo usa as Tabelas 1 e 2 (valores diretos).

## 5. Uso

### 5.1 No pipeline (`assumptions.icing` da missão)

```yaml
assumptions:
  icing:
    coupling: relatorio          # ou iterar (ponto fixo com o dimensionamento)
    envelopes: [continuous, intermittent]   # + takeoff
    temperature: envelope        # ou isa (só a temperatura ISA + isa_dT_K de cada segmento)
    fiki: true
    surfaces:
      - id: asa
        chord_m: 0.30
        t_c: 0.12
        lifting: true
        protection: deice_electrothermal   # none | anti_ice_thermal | deice_electrothermal | boots
        protected_chord_fraction: 0.08     # ou protected_area_m2
        duty_cycle: 0.1
        parting_strip_area_m2: 0.01
        power_density_W_m2: 20000
        mass_kg: 0.4
      - {id: pitot, d_m: 0.01, protection: anti_ice_thermal, protected_area_m2: 0.002, surface_temperature_C: 20}
requirements:
  max_ice_thickness: {max: 5, unit: mm, id: IC-01}
  ice_protection_power: {max: 1, unit: kW, id: IC-02}
  flight_into_known_icing: {target: sim, id: IC-03}
```

Sem `surfaces`, o adaptador usa asa e estabilizadores da configuração, sem proteção.

### 5.2 Especificação genérica (`acdt.api.icing`) — qualquer tipo de aeronave

Esquema `acdt.icing/1`: `envelopes`, `mvd_um`, `conditions` (`name`, `altitude_m`, `V_m_s`, `duration_s`, opcional
`T_C`, `envelope`, `isa_dT_K`, `p_st_Pa`), `surfaces` (como acima: `d_m` | `le_radius_m` | `chord_m` + `t_c`,
`protection`, …) e `fiki`. `acdt.api.icing_envelope(tipo, T_C, mvd_um, horizontal_extent_nmi=, altitude_m=)` devolve
o LWC de projeto e o estado face ao envelope.

### 5.3 Acoplamento (`coupling: iterar`)

Dentro da etapa de dimensionamento: soma o majorante da potência elétrica de proteção a
`propulsion.systems_power_W` e, porque o power budget em malha fechada substitui esse valor pela média do
balanço, também como carga `systems.loads` com ciclo 1 (toda a missão — PRESSUPOSTO conservador) (só aeronaves
elétricas), e a massa declarada dos sistemas a `weights.fixed_mass_kg`;
repete até a variação ficar abaixo de `tol` (histórico em `icing.coupling_loop`). Desconhecidos não são acoplados
e ficam em `not_coupled`. Compõe-se com o acoplamento térmico (o ciclo do gelo envolve o térmico).

## 6. V&V (`acdt vv --discipline gelo`)

Nos casos de Anderson usa-se d = 0,0316 c (o valor do próprio exemplo) e as entradas exatas em unidades inglesas.

| Caso | Referência | Calculado | Tolerância |
|---|---|---|---|
| ICING-AND-B1 | Anderson Ap. B.1: K 12,56, K₀ 3,350, β₀ 0,789, A_c 2,293, h_c 2,690×10⁵ cal/(h·m²·K), b 0,7134, φ 14,02 K, θ 19,23 K, n₀ 0,518, p_st 9,700×10⁴ Pa | 12,555; 3,351; 0,789; 2,293; 2,689×10⁵; 0,7137; 14,02; 19,25; 0,518; 97 003 | 0,1 % (K, K₀, A_c, h_c, b); θ 0,2 %; p_st 0,05 %; β₀ ±0,0005; n₀ ±0,001; φ ±0,01 K |
| ICING-AND-B2 | Ap. B.2: K 4,09, K₀ 1,381, β₀ 0,629, A_c 1,265, h_c 3,068×10⁵, b 0,1662, φ 5,94 K, θ 6,88 K, n₀ 0,598, p_st 9,492×10⁴ Pa | 4,090; 1,381; 0,629; 1,265; 3,068×10⁵; 0,1662; 5,94; 6,88; 0,598; 94 916 | idem |
| ICING-APPC-JECK | Jeck Tabelas 1–2 (cinco nós: 0,800; 0,191; 0,009; 3,915; 1,041 g/m³) e Ap. C Parte I(c) (0,35 g/m³) | iguais à 3.ª casa | 0,0005 g/m³; descolagem exata |
| ICING-NACA0012-RLE | r_le = 1,58 % c (Anderson/Abbott & von Doenhoff) | 1,587 % | 10⁻⁴ (ver nota) |

Nota: o caso do raio do bordo de ataque falhou na primeira corrida com a meia unidade (5×10⁻⁵): a fórmula dá 1,587 %
e a tabela imprime 1,58 %. A tolerância foi alargada a 10⁻⁴ e fica registada aqui e no caso.

Testes: `tests/test_icing.py` (V&V, propriedades e validade, limites da captação, regimes rime/glaze/sem gelo,
identidade running-wet = n₀ṁΛ_f, limites da potência, geometria do envelope e desconhecidos, estudo genérico com
intervalos, FIKI, API, pipeline com requisitos e acoplamento iterado).

## 7. Seguimentos

* Apêndice O (SLD) e Parte 33/35 (motores, hélices) quando houver tabelas verificáveis.
* β local fora da estagnação, limites de impacto e gelo de retorno; geometria a evoluir com a acreção.
* Penalização por tipo de gelo (corno, crista, rugosidade) com mais perfis; ΔC_D0 com referência limpa.
* Ar sangrado (caudal/temperatura) e potência de botas; mapa de calibração IRT.
* Carga de proteção no balanço só durante a fração de exposição (hoje ciclo 1).
* O acoplamento térmico (`thermal.py`) só escreve `systems_power_W`, que o power budget em malha fechada
  substitui: a potência do ventilador pode perder-se nesses projetos — rever como aqui.
* Combinação de encontros contínuo + intermitente; temperatura do dia (MIL-HDBK-310 frio) em vez do varrimento.
