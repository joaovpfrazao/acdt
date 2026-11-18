# TODO — Modelo estrutural L1 com deformação → aero no ciclo de `size`

Objetivo: ter massas e deflexões estruturais já em baixa fidelidade para a performance aerodinâmica (e o orçamento de massa/CG) fecharem com o efeito da flexibilidade desde cedo. Cada análise mais detalhada (L2/L3) só reduz a incerteza.

Data: 29 out 2026. Dividido para implementação em paralelo (ramos diferentes).

## Tarefas (podem ser atribuídas a ramos separados)

### 1. Nome e organização (baixo risco, bom para começar)
- [x] Criar `src/acdt/core/structures/` (ou renomear/agrupar o existente).
- [x] Nome curto: **BoxFEM** (FEM de cascas próprio já existente) + **BeamAero** (viga calibrada + acoplamento).
- [x] Mover/agrupar de forma não-destrutiva o que já é estrutural L1 (`core/fem`, `core/sections`, partes de `domains/aircraft/structures.py`). O FEM e as secções ficaram no sítio; `BoxFEM` é um alias.
- [x] Atualizar imports e testes. Critério: suite continua a passar.

### 2. Torção elástica da asa de volta à aero (ganho rápido)
- [x] No ciclo de `acdt size` (não só no `optimize`), depois das cargas da asa:
  - calcular torção elástica (viga existente ou BoxFEM),
  - passar essa torção à linha sustentadora / AVL (já existe suporte parcial na Fase 5),
  - recalcular CL, CD_i, ponto neutro.
- [x] Opção `assumptions.structures.flex: true` (ou `aero.elastic: true`).
- [x] Critério: performance (alcance ou subida) muda de forma monotónica e estável; testes do C172 e UAVs continuam a passar (com tolerância se os números mudarem ligeiramente).

### 3. Modelo de cargas da aeronave completa
- [x] `structures/loads.py`:
  - Asa: reutilizar V-n + Schrenk/AVL.
  - Fuselagem: manobra (n·W), aterragem, propulsão, cargas de empenagem.
  - Empenagens: equilíbrio + manobra.
  - Trem: cargas de aterragem (ligar ao curso já existente).
- [x] Saídas claras para o modelo de vigas.

### 4. Modelo de vigas da aeronave (massa + deflexão)
- [x] `structures/beam.py`:
  - Asa: viga-caixão existente, calibrada pelo BoxFEM.
  - Fuselagem: viga equivalente (2–3 secções) com EI/GJ a partir de revestimento + longarinas/cavernas paramétricas.
  - Empenagens: vigas simples.
- [x] Saídas: flecha, torção, massas por componente, CG estrutural.
- [x] Cross-check: massa da fuselagem dentro de ±25 % da equação de Raymer.

### 5. Acoplamento completo no ciclo de `size`
- [x] Integrar no MDA de ponto fixo já existente:
  ```
  geometria → aero L1 → cargas → estruturas L1 → deflexões → aero atualizada → pesos → W0 → repete
  ```
- [x] Tolerância: |ΔW0|/W0 < 0,1 % e deflexão estável.
- [x] Campos novos no `result.json` / DesignState:
  - `structures.masses`
  - `structures.deflections`
  - `aero.elastic_correction`
  - aplicar `calibration.k_EI` / `k_GJ` também em L1.

### 6. Documentação e critérios
- [x] `docs/structures-l1.md` (ou secção no ARCHITECTURE / CAPABILITIES) com a interface e os limites.
- [x] Tutorial curto ou nota no HANDOFF.
- [x] Critérios de aceitação finais:
  - Asa: flecha e torção dentro de ±30 % do BoxFEM.
  - Massa estrutural fecha o ciclo de W0.
  - `flex: true` não quebra a suite.

Feito num único ramo, `estruturas-l1`, em 30 out 2026. Ver `docs/structures-l1.md`.

## Ordem sugerida (se for sequencial)
1. Tarefa 1 (nome + organização)
2. Tarefa 2 (torção da asa → aero) — ganho mais rápido
3. Tarefa 3 + 4 (cargas + vigas fuselagem/empenagens)
4. Tarefa 5 (ciclo completo)
5. Tarefa 6 (docs)

## Notas para trabalho em paralelo
- Cada tarefa pode ir num ramo próprio a partir de `main`.
- Evitar editar os mesmos ficheiros ao mesmo tempo (`cli.py`, `sizing.py`, `mcp_server.py`, `AGENTS.md`, `HANDOFF.md`).
- No mesmo PC: usar `git worktree` (recomendado) ou checkouts separados.
- Antes de cada push: `pytest -q` (ou os testes da área).
- No fim: merge sequencial (ou rebase) com resolução de conflitos.

## Referências já no repositório
- BoxFEM: `core/fem` (QM6+MITC4)
- Viga-caixão / cargas asa: `domains/aircraft/structures.py`
- OpenAeroStruct (referência de acoplamento L2): Fase 3
- Fatores de calibração: já existem (`k_EI`, `k_GJ`, …)
