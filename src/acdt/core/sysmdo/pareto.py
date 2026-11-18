"""Ferramentas de Pareto (minimização de todos os objetivos).

* ordenação não dominada rápida e distância de aglomeração: Deb, Pratap, Agarwal & Meyarivan, "A fast and elitist
  multiobjective genetic algorithm: NSGA-II", IEEE Trans. Evol. Comput. 6(2):182–197, 2002;
* joelho (*knee*) com dois objetivos: ponto da frente normalizada à maior distância da reta que une os dois extremos
  (Das, "On characterizing the 'knee' of the Pareto curve based on Normal-Boundary Intersection", Struct. Optim.
  18:107–115, 1999). Com três ou mais objetivos: ponto mais próximo do ponto ideal na frente normalizada
  (programação de compromisso, Zeleny 1973) — marcado como tal no relatório;
* hipervolume 2-D (Zitzler & Thiele 1999) só para verificar convergência nos testes.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]


def dominates(a: Sequence[float], b: Sequence[float]) -> bool:
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def pareto_mask(F: Array) -> npt.NDArray[np.bool_]:
    """Máscara dos pontos não dominados (linhas de ``F``, minimização). Linhas com NaN nunca entram."""
    F = np.asarray(F, dtype=float)
    n = F.shape[0]
    ok = np.all(np.isfinite(F), axis=1)
    mask = ok.copy()
    for i in range(n):
        if not ok[i]:
            continue
        le = np.all(F[ok] <= F[i], axis=1)
        lt = np.any(F[ok] < F[i], axis=1)
        if np.any(le & lt):
            mask[i] = False
    return np.asarray(mask, dtype=bool)


def nondominated_sort(F: Array, violation: Sequence[float] | Array | None = None) -> list[list[int]]:
    """Frentes (listas de índices). Com ``violation`` (≥ 0) usa a dominância com restrições de Deb et al. 2002
    §VI: viável domina inviável; entre inviáveis domina a menor violação; entre viáveis a dominância de Pareto."""
    F = np.asarray(F, dtype=float)
    n = F.shape[0]
    cv = np.zeros(n) if violation is None else np.asarray(violation, dtype=float)

    def dom(i: int, j: int) -> bool:
        if cv[i] <= 0.0 and cv[j] > 0.0:
            return True
        if cv[i] > 0.0 and cv[j] > 0.0:
            return bool(cv[i] < cv[j])
        if cv[i] > 0.0:
            return False
        return dominates(F[i], F[j])

    S: list[list[int]] = [[] for _ in range(n)]
    cnt = [0] * n
    fronts: list[list[int]] = [[]]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if dom(i, j):
                S[i].append(j)
            elif dom(j, i):
                cnt[i] += 1
        if cnt[i] == 0:
            fronts[0].append(i)
    k = 0
    while fronts[k]:
        nxt: list[int] = []
        for i in fronts[k]:
            for j in S[i]:
                cnt[j] -= 1
                if cnt[j] == 0:
                    nxt.append(j)
        k += 1
        fronts.append(nxt)
    return fronts[:-1]


def crowding_distance(F: Array) -> Array:
    F = np.asarray(F, dtype=float)
    n, m = F.shape
    d = np.zeros(n)
    if n <= 2:
        return np.full(n, np.inf)
    for k in range(m):
        o = np.argsort(F[:, k], kind="stable")
        span = F[o[-1], k] - F[o[0], k]
        d[o[0]] = d[o[-1]] = np.inf
        if span <= 0.0:
            continue
        d[o[1:-1]] += (F[o[2:], k] - F[o[:-2], k]) / span
    return d


def knee_point(F: Array) -> tuple[int, str]:
    """Índice do joelho de uma frente não dominada ``F`` e o método usado."""
    F = np.asarray(F, dtype=float)
    if F.shape[0] == 0:
        raise ValueError("frente vazia")
    if F.shape[0] <= 2:
        return 0, "frente com ≤ 2 pontos: sem joelho definido (primeiro ponto)"
    lo, hi = F.min(axis=0), F.max(axis=0)
    span = np.where(hi > lo, hi - lo, 1.0)
    Z = (F - lo) / span
    if F.shape[1] == 2:
        a = Z[int(np.argmin(Z[:, 0]))]
        b = Z[int(np.argmin(Z[:, 1]))]
        ab = b - a
        L = float(np.hypot(ab[0], ab[1]))
        if L <= 0.0:
            return int(np.argmin(Z.sum(axis=1))), "extremos coincidentes: mínimo da soma normalizada"
        dist = (ab[0] * (a[1] - Z[:, 1]) - ab[1] * (a[0] - Z[:, 0])) / L  # >0 do lado do ideal
        return int(np.argmax(dist)), "Das 1999: maior distância à reta entre extremos (frente normalizada)"
    return int(np.argmin(np.linalg.norm(Z, axis=1))), "≥3 objetivos: mais próximo do ideal (Zeleny 1973)"


def hypervolume_2d(F: Array, ref: Sequence[float]) -> float:
    F = np.asarray(F, dtype=float)
    F = F[pareto_mask(F)]
    F = F[(F[:, 0] < ref[0]) & (F[:, 1] < ref[1])]
    if F.shape[0] == 0:
        return 0.0
    F = F[np.argsort(F[:, 0])]
    hv, prev = 0.0, float(ref[1])
    for f1, f2 in F:
        hv += (ref[0] - f1) * (prev - f2)
        prev = f2
    return float(hv)
