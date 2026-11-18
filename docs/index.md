# acdt — documentação

Framework open-source (Apache-2.0) de projeto de engenharia, do requisito ao projeto detalhado; a aeronave de asa
fixa (incluindo UAS) é o primeiro domínio. Só métodos clássicos e rastreáveis, citados no código; valores sem fonte
ficam marcados como **PRESSUPOSTO**; desconhecido nunca é zero e "não avaliado" nunca conta como "passa".

## Por onde começar

| quero… | ver |
|---|---|
| instalar e correr o primeiro dimensionamento | [Início rápido](#inicio-rapido) |
| usar o acdt a partir de Python | [API pública](API.md) e [referência `acdt.api`](referencia/api.md) |
| usar a linha de comandos | [referência da CLI](referencia/cli.md) |
| perceber a arquitetura | [Arquitetura](ARCHITECTURE.md) |
| requisitos e matriz de verificação | [Requisitos](REQUISITOS.md) |
| incerteza e sensibilidade | [Incerteza](INCERTEZA.md) |
| MDO global e frente de Pareto | [MDO](MDO.md) |
| casos de referência (V&V) | [V&V](VV.md) |
| estado de projeto com unidades | [Dados](DADOS.md) |
| calibrar com dados de ensaio | [Calibração](CALIBRACAO.md) |
| relatório de revisão SRR/PDR/CDR com veredito | [Relatórios](RELATORIOS.md) |
| ruído de hélices/rotores, deteção auditiva, Parte 36 Ap. G | [Ruído](RUIDO.md) |
| gestão térmica: compartimentos, dias quente/frio MIL-HDBK-310, arrefecimento e arrasto | [Térmica](TERMICA.md) |
| gelo: envelopes 14 CFR 25 Ap. C, captação, rime/glaze, espessura, potência de proteção | [Gelo](GELO.md) |
| fiabilidade de missão, MTBF/MTBCF, disponibilidades, MMH/FH, sobressalentes, frota (MIL-HDBK-338B) | [Fiabilidade](FIABILIDADE.md) |
| custo de série: CER em função de N, RDT&E vs produção, aprendizagem Wright/Crawford, ponto de equilíbrio | [Custo de série](CUSTO_SERIE.md) |
| CI, mypy, tolerâncias | [Qualidade](QUALIDADE.md) |

O que o acdt faz, área a área, está em
[CAPABILITIES.md](https://github.com/joaovpfrazao/acdt/blob/main/CAPABILITIES.md).

## Início rápido

```bash
pip install -e ".[dev]"            # extras opcionais: aero, mdo, structures, hifi, docs, notebooks…
acdt --version
acdt size examples/uav_gasoline_150kg.yaml -o out/uav --json     # resumo JSON em stdout
```

```python
from acdt import api

r = api.size("examples/uav_gasoline_150kg.yaml", "out/uav", level="L0", no_systems=True)
print(r["feasible"], r["W0_kg"], r["verification"]["por_estado"])
```

Notebooks executáveis em `examples/notebooks/` (dimensionamento rápido, incerteza + verificação, MDO com frente
de Pareto).
