# Benchmark Nansei / JCG — enunciado

**Só o problema e os resultados de referência.** O estudo completo (scripts, figuras, narrativa)
permanece no ramo `estudo-nansei` e **não** deve ser fundido na `main`.

## Problema (palavras do utilizador)

> Fazer um/vários UAVs para a Japan Coast Guard vigiar as águas da cadeia Nansei.

## Interpretação de referência (agente, 2026-10-30)

Necessidade de consciência situacional marítima 24/7 sobre o mar territorial + zona contígua das
Senkaku (atividade CCG), a partir de aeroportos existentes do 11.º Distrito, entregando o track aos
navios-patrulha, com o menor custo de aquisição / horas de voo / perdas.

## Área e janela (números de referência)

| grandeza | valor |
|---|---|
| Área TS+ZC Senkaku | 15 224 km² |
| Mar territorial (validação) | ≈ 4 495 km² |
| Janela de deteção (12 NM @ 10 kn) | 1,20 h |
| Distância Ishigaki → área | ≈ 162 km |
| Endurance mínima (curfew Ishigaki 08–21, vento 10 m/s) | ≥ 16,7 h |

Ver `reference_results.json` → `geography` / `operations`.

## Requisitos

Tabela completa em `requirements.json` (RM* missão, RA* aeronave). Limiares chave:

* `p_enough_available` ≥ 0,95
* POD na janela ≥ 0,9 (pesqueiro)
* C2 LoS ≤ horizonte rádio ≈ 248 km
* Operar a partir de Ishigaki (ou Naha 24 h)

## O que o benchmark mede na framework

Ao re-correr o trade com as ferramentas actuais, comparar com `reference_results.json`:

1. Área / trânsito / endurance de curfew (geo + `transit_time`).
2. Variantes dimensionadas L12/L18/L24/XL24/M12 (`W0`, endurance Breguet, falhas `hq:*`/`gear:*`).
3. Frente de Pareto da frota e recomendação (A10 no registo de 2026-10-30).

Diferenças são esperadas quando a framework ganha capacidade (P1–P7); documentar o delta no HANDOFF.

## Fora deste pacote

* Scripts `examples/concept/nansei_jcg/*` e `examples/output/concept/nansei_jcg/**` do ramo.
* Figuras, polares RCS regeneradas, caixão F3116, trades de trem da iteração 3.
* Commits de framework no ramo (`landing_gear` tail-strike, `structures` F3116) — merge à parte,
  só com decisão explícita.
