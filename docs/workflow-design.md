# Workflow de design — do problema ao design final validado

Referência do fluxo lógico de engenharia no acdt (asa fixa / UAS).  
Data: 29 out 2026.

> **Substituído** pelo workflow por níveis N0–N3+ em [DESIGN_WORKFLOW.md](DESIGN_WORKFLOW.md) (30 out 2026).
> Este documento fica como referência histórica e como mapa das ferramentas por loop.

O processo é uma sucessão de **loops** que começam com muitas opções e vão fechando até um design fixo e validado.  
**RCS, custo, producibilidade, sistemas, propulsão e engenharia elétrica** avançam em paralelo com o design físico em todos os loops (não são etapas finais).

## Visão geral

```
Problema (texto)
  → Loop 0: requisitos + arquiteturas candidatas
    → Loop 1: estudo conceptual (design point + forma genérica + performance literatura)
      → Loop 2: formas + otimização low-fi (aero + estrutura + RCS + sistemas + custo)
        → Loop 3: fixar design e refinar detalhe
          → Loop 4: alta fidelidade + missão complexa + fecho
```

Cada loop produz artefactos (`result.json`, relatórios, calibrações) que o seguinte consome. A IA (ou o projetista) só avança quando os gates da etapa estão aceites ou documenta explicitamente o que ficou em aberto.

---

## Loop 0 — Problema → requisitos (ainda sem avião)

**Input:** texto livre do problema.  
**Tools:** `concept_study_*`, `geo_measure`, `transit_time`, `sweep_coverage`, `persistent_coverage`, `sensor_footprint`, `johnson_range`, `radar_horizon`… (camada concept).

- Interpreta o problema.
- Gera requisitos mensuráveis para uma ou mais soluções (1 UAV grande vs frota, com/sem relay, etc.).
- Já pode incluir objetivos ou restrições de RCS, custo, disponibilidade, etc.
- **Output:** requisitos + arquiteturas candidatas + pressupostos (`study.json` + `report.md`).

---

## Loop 1 — Estudo conceptual (design point + forma genérica + performance de literatura)

**Tools:** `validate_requirements` → `acdt size` (L0) + `size_fleet` + `compare_alternatives`.  
Opcionalmente `acdt rcs` em modo rápido.

- Diagrama de restrições, design point (W/S, P/W), geometria de primeira ordem.
- Pesos por componentes (Raymer), performance de missão por métodos de literatura.
- Sistemas, propulsão e elétrica de primeira ordem (motor/hélice/bateria, power budget, cablagem).
- Custo L0 (CER) e producibilidade grosseira.
- **Output:** formas genéricas + estimativas de performance na missão + ranking Pareto. Muitas opções ainda vivas.

---

## Loop 2 — Primeira forma(s) + otimização low-fi multi-objetivo

**Tools:** `acdt size` (L1, AVL/NeuralFoil) + `acdt rcs` + modelo estrutural L1 (viga/BoxFEM, com deflexão quando disponível) + `acdt optimize` ou trade.

- Aero low-fi + estrutura low-fi (massa + deflexões) + RCS (Óptica Física) no mesmo ciclo.
- Objetivo principal: performance na missão; RCS, massa ou custo como segundo objetivo ou restrição.
- Sistemas/propulsão/elétrica e custo/producibilidade reavaliados com a nova geometria.
- **Output:** 1–3 configurações promissoras (forma, estrutura preliminar, RCS, performance, custos). Espaço de opções já bem mais fechado.

---

## Loop 3 — Fixar o design e refinar o detalhe

**Tools:** `acdt optimize` (L2, OpenAeroStruct se útil) + `wingbox`/`wingbox6` + `acdt cad` + atualização de `systems` + `acdt manufacture` (L1) + W&B/trem.

- Escolha da configuração (ou último trade).
- Refinamento de geometria, caixão, pesos, CG, propulsão e arquitetura elétrica.
- Performance de missão recalculada com modelos L1/L2.
- **Output:** design congelado a nível preliminar. Pronto para verificação.

---

## Loop 4 — Alta fidelidade para validar e fechar

**Tools:** `acdt hifi` (OpenVSP, SU2, CalculiX, flutter…) + `acdt controls` + `acdt simulate` (6-DOF) + `acdt manufacture` (L1/L2) + `acdt certify` / `safety`.

- Confirmação de aero, estrutura, flutter e missão realista.
- Fatores de calibração L3 → L1/L2 quando fizer sentido.
- Custo, producibilidade, sistemas e certificação fechados com o design detalhado.
- **Output:** design final validado (STEP, relatórios L3, missão 6-DOF fechada, matriz de conformidade, custo) ou lista clara do que ainda falha.

---

## Temas que andam em paralelo em todos os loops

| Tema | Tools principais | Quando |
|------|------------------|--------|
| Propulsão + elétrica | bloco `systems` | Todos |
| Custo + producibilidade | `cost` / `acdt manufacture` | Todos (L0 → L1 → L2) |
| RCS | `acdt rcs` | Sempre que a geometria mudar o suficiente |
| Estrutura | pesos por componentes → viga/BoxFEM → L3 | Progressivo |
| Certificação / segurança | `acdt certify` / `safety` | A partir do Loop 3–4 (pode começar mais cedo como checklist) |

---

## Notas

- O estudo conceptual de frota (`acdt concept`) está em `main` e cobre o Loop 0 e parte do Loop 1.
- O modelo estrutural L1 com deflexão → aero no ciclo de `size` (ver `TODO-structures-l1.md`) melhora especialmente o Loop 2.
- A estrutura interna do Loop 3 sai com `acdt cad`: DXF em milímetros e, com o extra `acdt[cad]`, STEP dos revestimentos, longarinas, nervuras, cavernas e longarinas da fuselagem. A casca exterior continua a ser o STEP do OpenVSP, passado com `--oml`. Ver `cad-parametrico.md`.
- Alta fidelidade (Loop 4) verifica e calibra; não dimensiona.
- Todos os resultados são de apoio ao projeto. Não substituem análise de engenharia nem certificação.
