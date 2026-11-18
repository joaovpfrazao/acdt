# Sessão MCP de demonstração (end-to-end)

`session.py` faz o que um agente de IA faz com o acdt através do servidor MCP (cliente oficial `mcp`, transporte
em memória — as mesmas ferramentas/JSON que em stdio/HTTP):

pedido do utilizador (dict de requisitos com unidades em texto) → `requirements_schema` → `validate_requirements`
→ `size` L0 → `size` L1 (XFOIL/AVL) → `optimize` (definições de demo: pipeline L0, 1 iteração, correção só de valor)
→ `compare_runs` → `hifi_estimate` (o `cfd2d` fica a aguardar autorização do utilizador; nada pesado corre) →
`generate_report`.

```bash
python examples/ai_session/session.py            # ≈1,5 min nesta box; --full: MDO L1, 2 iterações (≈7 min)
```

Saídas em `output/`: `transcript.md` (cada chamada, argumentos e resultado), `dossier.md`; os runs ficam em
`output/runs/` (não versionados). Os pressupostos vêm do modelo `examples/uav_endurance_payload.yaml`, registados
como tal em cada run.

Resultado da corrida versionada (2026-11-18, ver `output/transcript.md`): W0 = 23.38 kg (L0) e 22.87 kg (L1),
b = 4.26 / 4.23 m; MDO (demo) 23.38 → 22.45 kg com AR 14 → 9.8 (limite inferior da região de confiança);
falhas indicativas hq:CAP e hq:spiral (MIL-F-8785C Nível 2, UAV) em todos; em L0 a missão por segmentos dá
2.497 h vs ≥ 2.5 h.
