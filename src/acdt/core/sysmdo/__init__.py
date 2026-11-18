"""MDO global ao nível do sistema (``acdt mdo``; docs/MDO.md).

Constrói, a partir de um YAML, um problema OpenMDAO sobre um *modelo de sistema* caixa-preta (o mesmo protocolo de
``acdt uq``: ``run(points) -> [Sample]`` com métricas e estado de cada requisito): variáveis de projeto por caminho
(contínuas, inteiras ou discretas), um ou vários objetivos, restrições geradas a partir do registo de requisitos
rastreáveis (com a tolerância declarada), estratégias SLSQP / GA / NSGA-II / DOE / ε-restrição, ciclo exterior
discreto com fecho por iteração (frota ↔ projeto) e objetivo robusto opcional sobre o substituto de ``acdt uq``.
"""
from __future__ import annotations

from .spec import MDOSpec, MDOSpecError, parse_spec
from .pareto import crowding_distance, hypervolume_2d, knee_point, nondominated_sort, pareto_mask
from .run import run_mdo

__all__ = ["MDOSpec", "MDOSpecError", "parse_spec", "crowding_distance", "hypervolume_2d", "knee_point",
           "nondominated_sort", "pareto_mask", "run_mdo"]
