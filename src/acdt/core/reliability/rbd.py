# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Diagramas de blocos de fiabilidade (RBD) com taxas constantes (lei exponencial).

Fontes (MIL-HDBK-338B, 1 out. 1998):

* série P_S = Π P_i (Eq. 6.20–6.23); paralelo ativo P_S = 1 − Π (1 − P_i) (Eq. 6.24–6.27); configurações não
  série-paralelo pela decomposição P_S = P_S(X bom) R_X + P_S(X mau) Q_X (Eq. 6.19) — aqui por enumeração exata
  dos estados dos componentes dos caminhos mínimos (``paths``), equivalente à aplicação repetida da Eq. 6.19;
* k-de-n: soma binomial P(k, n, p) (§7.5.5.1; :func:`acdt.core.concept.reliability.k_of_n`) e, com unidades
  diferentes, a distribuição de Poisson-binomial (mesma soma, probabilidades distintas);
* R(t) = e^{−λt} (Eq. 5.57); MTTF = ∫₀^∞ R(t) dt (Eq. 5.73); n unidades idênticas em paralelo ativo têm
  MTTF = (1/λ) Σ_{i=1..n} 1/i (§7.5.5, Fig. 7.5-9: o primeiro redundante dá +50 %);
* **MTBF básica** (procura de manutenção e logística: todos os componentes em série) e **MTBCF / fiabilidade de
  missão** (modelo com redundâncias) — §6.4.2 e definições da Secção 3.

Intervalos: R é monótona em cada λ, por isso ``lo`` usa os λ_hi e ``hi`` os λ_lo. Componente com λ desconhecido:
``lo`` com R = 0 e ``hi`` com R = 1 (limites válidos, nunca λ = 0 como valor). MTTF majorante infinito → ``None``.
PRESSUPOSTOS: avarias independentes (sem causa comum), taxas constantes, redundância ativa sem comutação, sem
reparação durante a missão.
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Callable, Mapping, Sequence

from acdt.core.concept.reliability import k_of_n as _k_of_n_identical

NodeT = Any  # str (id) | Mapping (bloco)
TYPES = ("series", "parallel", "k_of_n", "paths")
MAX_PATH_COMPONENTS = 20


def _children(node: Mapping[str, Any]) -> list[NodeT]:
    b = node.get("blocks")
    if not isinstance(b, list) or not b:
        raise ValueError(f"bloco {node.get('type')!r} precisa de 'blocks' (lista não vazia)")
    return b


def validate(node: NodeT, comp_ids: set[str], _seen: set[str] | None = None) -> set[str]:
    """Valida a árvore e devolve os ids usados; um id não se repete fora de ``paths`` (independência)."""
    seen = set() if _seen is None else _seen
    if isinstance(node, str):
        if node not in comp_ids:
            raise ValueError(f"RBD: componente {node!r} não declarado")
        if node in seen:
            raise ValueError(f"RBD: componente {node!r} repetido (use 'paths' para estruturas com partilha)")
        seen.add(node)
        return seen
    if not isinstance(node, Mapping):
        raise ValueError(f"RBD: nó inválido {node!r}")
    t = node.get("type")
    if t not in TYPES:
        raise ValueError(f"RBD: tipo {t!r} ({', '.join(TYPES)})")
    if t == "k_of_n" and node.get("block") is not None:
        validate(node["block"], comp_ids, seen)
        n, k = int(node.get("n", 0)), int(node.get("k", 0))
        if not 1 <= k <= n:
            raise ValueError("k_of_n idêntico: 1 ≤ k ≤ n")
        return seen
    if t == "paths":
        paths = node.get("paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, list) and p for p in paths):
            raise ValueError("paths: lista de caminhos mínimos (listas de ids)")
        ids = {str(c) for p in paths for c in p}
        bad = ids - comp_ids
        if bad:
            raise ValueError(f"paths: componentes não declarados {sorted(bad)}")
        if ids & seen:
            raise ValueError(f"paths: componentes já usados noutro bloco {sorted(ids & seen)}")
        if len(ids) > MAX_PATH_COMPONENTS:
            raise ValueError(f"paths: no máximo {MAX_PATH_COMPONENTS} componentes (enumeração exata)")
        seen |= ids
        return seen
    for c in _children(node):
        validate(c, comp_ids, seen)
    if t == "k_of_n":
        k = int(node.get("k", 0))
        if not 1 <= k <= len(node["blocks"]):
            raise ValueError("k_of_n: 1 ≤ k ≤ len(blocks)")
    return seen


def multiplicity(node: NodeT, n_of: Mapping[str, int], out: dict[str, int] | None = None) -> dict[str, int]:
    """Unidades físicas de cada componente na árvore (para a MTBF básica): folha → n; k-de-n idêntico → N·n."""
    out = {} if out is None else out
    if isinstance(node, str):
        out[node] = out.get(node, 0) + int(n_of.get(node, 1))
        return out
    t = node["type"]
    if t == "k_of_n" and node.get("block") is not None:
        sub = multiplicity(node["block"], n_of, {})
        for cid, m in sub.items():
            out[cid] = out.get(cid, 0) + m * int(node["n"])
        return out
    if t == "paths":
        for cid in {str(c) for p in node["paths"] for c in p}:
            out[cid] = out.get(cid, 0) + int(n_of.get(cid, 1))
        return out
    for c in _children(node):
        multiplicity(c, n_of, out)
    return out


def _poisson_binomial_at_least(k: int, ps: Sequence[float]) -> float:
    dist = [1.0]
    for p in ps:
        nxt = [0.0] * (len(dist) + 1)
        for i, q in enumerate(dist):
            nxt[i] += q * (1.0 - p)
            nxt[i + 1] += q * p
        dist = nxt
    return min(1.0, sum(dist[k:]))


def prob(node: NodeT, p: Callable[[str], float]) -> float:
    """Probabilidade de sucesso da estrutura dadas as probabilidades de sucesso dos componentes ``p(id)``."""
    if isinstance(node, str):
        return p(node)
    t = node["type"]
    if t == "series":
        return math.prod(prob(c, p) for c in _children(node))
    if t == "parallel":
        return 1.0 - math.prod(1.0 - prob(c, p) for c in _children(node))
    if t == "k_of_n":
        k = int(node["k"])
        if node.get("block") is not None:
            return _k_of_n_identical(int(node["n"]), k, prob(node["block"], p))
        return _poisson_binomial_at_least(k, [prob(c, p) for c in _children(node)])
    # paths: enumeração exata dos estados (equivalente à Eq. 6.19 aplicada repetidamente)
    paths = [[str(c) for c in pth] for pth in node["paths"]]
    ids = sorted({c for pth in paths for c in pth})
    pv = {c: p(c) for c in ids}
    tot = 0.0
    for state in itertools.product((True, False), repeat=len(ids)):
        up = {c for c, s in zip(ids, state) if s}
        if any(all(c in up for c in pth) for pth in paths):
            tot += math.prod(pv[c] if s else 1.0 - pv[c] for c, s in zip(ids, state))
    return tot


def reliability(node: NodeT, lam: Mapping[str, float | None], t_h: float, unknown_R: float) -> float:
    """R(t) da estrutura; ``lam[id]`` = λ efetivo do bloco [1/h] ou ``None`` (desconhecido → ``unknown_R``)."""
    def p(cid: str) -> float:
        v = lam.get(cid)
        return unknown_R if v is None else math.exp(-float(v) * float(t_h))
    return prob(node, p)


def mttf(node: NodeT, lam: Mapping[str, float | None], unknown_R: float) -> float | None:
    """MTTF = ∫₀^∞ R(t) dt (MIL-HDBK-338B Eq. 5.73); ``None`` se R não tende para 0 (majorante infinito)."""
    from scipy.integrate import quad

    known = [float(v) for v in lam.values() if v is not None and v > 0]
    if not known:
        return None
    tau = 1.0 / max(known)
    t_far = 1e3 / min(known)
    if reliability(node, lam, t_far, unknown_R) > 1e-12:
        return None
    f = lambda t: reliability(node, lam, t, unknown_R)  # noqa: E731
    # troços em escalas de tempo crescentes (taxas muito diferentes): precisão relativa ~1e-9
    edges = [0.0]
    x = tau
    while x < t_far:
        edges.append(x)
        x *= 10.0
    edges.append(t_far)
    tot = sum(quad(f, a, b, limit=200, epsabs=0.0, epsrel=1e-11)[0] for a, b in zip(edges[:-1], edges[1:]))
    tot += quad(f, t_far, math.inf, limit=200)[0]
    return tot


def series_of(ids: Sequence[str]) -> dict[str, Any]:
    return {"type": "series", "blocks": list(ids)}


def parallel_identical_mttf(lam: float, n: int) -> float:
    """MTTF de n unidades idênticas em paralelo ativo: (1/λ) Σ 1/i (MIL-HDBK-338B §7.5.5, Fig. 7.5-9)."""
    return sum(1.0 / i for i in range(1, int(n) + 1)) / float(lam)


def k_of_n_identical_mttf(lam: float, n: int, k: int) -> float:
    """MTTF de k-de-n idênticas ativas: (1/λ) Σ_{i=k..n} 1/i (integração de ∫ P(≥k de n) dt com p = e^{−λt})."""
    return sum(1.0 / i for i in range(int(k), int(n) + 1)) / float(lam)
