# Verificação e validação como produto (`acdt vv`)

Biblioteca de casos de referência **publicados**, por disciplina, corrida pelo `acdt vv` e na CI (só os baratos).
Gera um relatório de V&V versionado (`vv_report.json` + `vv_report.md`, formato `acdt.vv/1`) com o estado de cada
caso e o registo de proveniência da corrida. O exemplo da asa voadora não entra aqui: os casos validam a framework.

```
acdt vv                       # casos baratos (os da CI) → output/vv
acdt vv --cost medio -o vv    # + casos de custo médio (dimensionamento C172, ~20 s)
acdt vv --case MDO-SELLAR     # um caso (ignora o filtro de custo)
acdt vv --discipline estruturas --strict
acdt vv --list                # registo, versão e impressão digital
```

Código de saída: 1 se algum caso falhar (com `--strict`, também com `nao_avaliado`/`desconhecido`); 2 se pedir um
caso que não existe.

## O que é um caso

Cada caso (`acdt.core.vv.Case`) tem:

* **enunciado** do problema (geometria, cargas, entradas);
* **tipo** (Oberkampf & Roy, Verification and Validation in Scientific Computing, CUP 2010, Cap. 1–2):
  `verificacao` (código contra solução exata/analítica ou norma que define a grandeza) ou `validacao` (modelo
  contra dados físicos publicados);
* **valores de referência** com a **citação completa** (`Reference`: grandeza, valor, unidade, citação);
* **tolerância declarada a priori** por grandeza (`tol_abs` + `tol_rel`·|ref|, ou limite `min`/`max`) com a
  justificação (`tol_source`) — o registo recusa casos sem citação ou sem tolerância;
* o **avaliador** do acdt que produz o valor comparado, o **custo** (`barato` < ~10 s, corre na CI; `medio`;
  `pesado`, só no PC) e as ferramentas/módulos exigidos (`avl`, `py:openmdao`);
* os testes pytest que já cobriam a verificação (inventário).

Estados: `passa` (todas as grandezas dentro da tolerância), `falha`, `nao_avaliado` (ferramenta/dependência em
falta, `NotAssessed`, ou caso acima do custo pedido — **nunca conta como passa**) e `desconhecido` (o avaliador
correu e não deu valor, ou levantou exceção — nunca zero).

O relatório é versionado: versão do registo (`REGISTRY_VERSION`), impressão digital SHA-256 das definições de todos
os casos (ids, enunciados, referências, tolerâncias — muda quando um caso muda) e o registo `acdt.provenance/1`
(commit, árvore suja, versões, SO, executáveis com SHA-256). Comparar dois relatórios: `acdt provenance diff`.

## Casos (registo 2026.11.17)

Corrida de 17 nov 2026 no box Linux (`acdt vv --cost medio`): **22 passa, 0 falha**.

| Caso | Disciplina | Tipo | Custo | Referência | Tolerância |
|---|---|---|---|---|---|
| ATM-ISA-SL | atmosfera | verificação | barato | ISO 2533:1975 / U.S. Standard Atmosphere 1976: T, p, ρ, a, μ ao nível do mar | valores definidores exatos; tabelados ao último algarismo |
| ATM-ISA-11KM | atmosfera | verificação | barato | idem, H = 11 km: 216,65 K, 22 632,1 Pa, 0,36392 kg/m³ | 1e-5 / 5e-5 relativo |
| ATM-ISA-20KM | atmosfera | verificação | barato | idem, H = 20 km: 216,65 K, 5474,89 Pa, 0,088035 kg/m³ | 1e-5 / 5e-5 relativo |
| SA-SOBOL-ISHIGAMI | sensibilidade | verificação | barato | Homma & Saltelli 1996; Saltelli et al. 2008 (índices analíticos, a = 7, b = 0,1) | ±0,03 com N = 8192 |
| MDO-SELLAR | mdo | verificação | barato | Sellar, Batill & Renaud 1996 (AIAA 96-0714); f* = 3,18339395 (docs OpenMDAO) | ±2e-4 em f, ±5e-3 em x, z |
| MDO-ZDT1 | mdo | verificação | barato | Zitzler, Deb & Thiele 2000; hipervolume analítico 0,87667 ao ponto (1,1; 1,1) | HV ≥ 0,85; mediana do desvio ≤ 0,02 |
| STR-BEAM-CANTILEVER | estruturas | verificação | barato | Timoshenko & Gere 1997: δ = PL³/(3EI), θ = TL/(GJ) | ±0,5 % |
| STR-FEM-CANTILEVER | estruturas | verificação | barato | idem, consola em cascas do `acdt.core.fem` | ±2 % |
| STR-FEM-PLATE-BUCKLING | estruturas | verificação | barato | Timoshenko & Gere 1961 §9.2: N_cr = 4π²D/b² | ±2 % |
| STR-SP8007-KNOCKDOWN | estruturas | verificação | barato | NASA SP-8007 (1968): γ(R/t = 100) = 0,5813 | ±1e-4 |
| EM-PO-01…09 | em | verificação | barato | Knott, Shaeffer & Tuley 1993 Tab. 6.1; Balanis 2012 §11.3 (placa, esfera, cilindro, diedro) | 0,01–1 dB (bandas de `core/em/validate.py`) |
| AERO-LL-ELLIPTIC | aerodinâmica | verificação | barato | Anderson 2011 §5.3.1 (Prandtl, asa elíptica: e = 1) | ±0,1 % / ±0,2 % |
| REG-23337-N | cargas | verificação | barato | 14 CFR 23.337(a) (até à Amdt. 23-63) / CS-23.337(a) | exato |
| NOISE-SKM-EXAMPLE | ruido | verificação | barato | Marte & Kurtz, JPL TR 32-1462 (1970) Ap. C: 78,7 dB a 300 ft, 68,2 dB a 1000 ft, 556 Hz | 0,1 dB; 0,3 % (arredondamentos do exemplo) |
| NOISE-AWEIGHT | ruido | verificação | barato | IEC 61672-1:2013 Tabela 3 (ponderação A, 31,5 Hz – 16 kHz) | 0,05 dB |
| NOISE-ISO9613-ALPHA | ruido | verificação | barato | α da ISO 9613-1 (4 atmosferas × 7 oitavas), tabela reproduzida pela ETH Zürich | meia unidade do último algarismo + 0,01 dB/km |
| NOISE-P36G-LIMITS | ruido | verificação | barato | 14 CFR 36 Ap. G, G36.301(b)/(c) | exato |
| THERMAL-INC-EX5.1 | termica | verificação | barato | Incropera 6.ª ed. Ex. 5.1 (termopar, capacidade concentrada): D = 0,706 mm, t = 5,2 s | 0,0005 mm; 0,05 s |
| THERMAL-INC-EX7.1 | termica | verificação | barato | Incropera Ex. 7.1 (placa plana laminar, Eq. 7.30): q′ = 570 W/m | 0,5 % |
| THERMAL-INC-EX9.2 | termica | verificação | barato | Incropera Ex. 9.2 (Churchill & Chu, Eq. 9.26): q = 1060 W | 0,5 % |
| THERMAL-INC-EX8.6 | termica | verificação | barato | Incropera Ex. 8.6 (conduto, Dittus–Boelter): q″ = 304 W/m², T_s,L = 50,7 °C | 0,5 %; 0,15 °C |
| THERMAL-MIL310 | termica | verificação | barato | MIL-HDBK-310 (1997) §5.3.1.1.2, §5.3.1.2.2, Tabela I | exato |
| THERMAL-AIR-PROPS | termica | verificação | barato | Incropera Tabela A.4 (ar a 300 K): μ, k, Pr | 0,5 %; 1 %; 1 % |
| ICING-AND-B1 | gelo | verificação | barato | Anderson, NASA/CR-2004-212875 (2004) Ap. B.1 (NACA 0012, 40 µm): K 12,56, K₀ 3,350, β₀ 0,789, A_c 2,293, h_c, b, φ, θ, n₀ 0,518, p_st | 0,1 % (θ 0,2 %; p_st 0,05 %); β₀ ±0,0005; n₀ ±0,001; φ ±0,01 K |
| ICING-AND-B2 | gelo | verificação | barato | idem Ap. B.2 (20 µm): K 4,09, K₀ 1,381, β₀ 0,629, A_c 1,265, n₀ 0,598 | idem |
| ICING-APPC-JECK | gelo | verificação | barato | 14 CFR 25 Ap. C via Jeck, DOT/FAA/AR-00/30 (2002) Tabelas 1–2 (cinco nós) e Parte I(c) (0,35 g/m³) | 0,0005 g/m³; descolagem exata |
| ICING-NACA0012-RLE | gelo | verificação | barato | Abbott & von Doenhoff via Anderson: r_le = 1,58 % c | 10⁻⁴ (ver nota) |
| SIZ-C172S | dimensionamento | **validação** | médio | Cessna 172S Information Manual (1998): MTOW 1157 kg, vazio 754 kg, 134 kW, 16,2 m², 71,4 kg/m² | ±15 % massas, ±25 % resto (método conceptual) |

Nota sobre `ICING-NACA0012-RLE`: a fórmula r_le = 1,1019 t² c dá 1,587 % e a referência imprime 1,58 %; com a
meia unidade do último algarismo (5×10⁻⁵) o caso falhou na primeira corrida. A tolerância foi alargada a 10⁻⁴
(arredondamento da tabela, não ajuste do modelo) e fica registada aqui e na `tol_source` do caso.

Achado ao montar a biblioteca: o primeiro valor de referência escrito para o SP-8007 (0,5806) estava errado; a
fórmula publicada dá 0,5813 e o caso falhou até ser corrigido — é para isto que a tolerância é declarada antes.

## Inventário dos testes de validação que já existiam

Embrulhados como casos: ISA (`test_atmosphere_units`), Ishigami (`test_uq`, `test_sensitivity_sobol`), Sellar e
ZDT1 (`test_mdo_system`), consola, placa e SP-8007 (`test_fem_core`, `test_structures_l1`), PO canónicos
(`test_phase6_rcs`), linha sustentadora elíptica (`test_wingbox`), 23.337 (`test_phase2`), C172S
(`test_sizing_c172`). Os testes continuam; os casos acrescentam o relatório e as citações.

Ficaram **de fora** por não haver um valor publicado que se possa citar com precisão no repositório:

* XFOIL NACA 2412 (`test_phase2::test_xfoil_naca2412_polar`): o teste usa a banda cl(0) ∈ [0,20; 0,30] com a nota
  «Abbott & von Doenhoff App. IV ≈ 0,25». Falta o valor tabelado exato (e o Re) do apêndice.
* AVL (`test_avl_wrapper_lift_slope_and_efficiency`): compara com Helmbold × 1,1 (fator de cauda arbitrário), não
  com dados publicados. Um caso AVL de asa elíptica/retangular contra Prandtl ou um ensaio NACA fica por fazer.
* Comparações C172 de desempenho (subida, descolagem, perda) contra o POH: os números do POH não estão
  transcritos no repositório com página/tabela.
* CFD (H1 GCI), CalculiX, 6-DOF/JSBSim: pesados ou sem referência publicada; ficam no PC do João.

## Acrescentar um caso

```python
from acdt.core.vv import Reference, builder
_c = builder("estruturas")

@_c("STR-NOVO", "Título", "Enunciado completo …", "verificacao",
    [Reference("w", 1.23e-3, "m", "Autor, Título, Ed., Ano, §/Tab./Eq.", tol_rel=0.02,
               tol_source="porquê ±2 % (malha, arredondamento da fonte, …)")],
    cost="barato", requires=("py:openmdao",), tests=("tests/test_x.py::test_y",))
def _novo():
    return {"w": ...}   # None = desconhecido, nunca zero
```

Os módulos de casos estão em `acdt.core.vv.CASE_MODULES` (`acdt.core.vv_cases`, `acdt.domains.aircraft.vv_cases`).
Nunca acrescentar um valor de referência sem fonte que se possa verificar; sem fonte, o caso não entra.

## CI

Job `vv` em `.github/workflows/ci.yml` (Linux): `acdt vv --cost barato -o vv_report`, resumo no sumário do job e o
relatório como artefacto. `tests/test_vv.py` corre também cada caso barato como teste (parametrizado) e o C172S
como `slow`.

## Limites

* Só casos baratos na CI; os de custo médio correm com `--cost medio` (localmente ou no PC).
* A maior parte é verificação; a validação contra dados físicos resume-se ao C172S de nível conceptual. Faltam
  dados de ensaio (túnel, voo, banco de motor) com fonte — ver «Ficaram de fora».
* Os casos PO usam as formas fechadas de ótica física (não a medição); a validação RCS contra medições fica por
  fazer.
