"""Fleet reliability: k-of-N binomial, sortie success from a constant failure rate, fleet size for a confidence.

* k-out-of-n system of independent identical units: P(X ≥ k) = Σ_{i=k..n} C(n,i) p^i (1−p)^{n−i} —
  O'Connor, P. D. T. & Kleyner, A. (2012), "Practical Reliability Engineering", 5th ed., Wiley
  ("k-out-of-n" redundancy); MIL-HDBK-338B (1998), §6.
* Sortie success with a constant failure rate λ over t hours: R = exp(−λt) (exponential law; same model as the
  acdt ARP4761 FTA, :mod:`acdt.core.safety.fta`).

Validity: independence (no common-cause events such as weather grounding the whole fleet); constant rates.
"""
from __future__ import annotations

import math

REF_KN = "O'Connor & Kleyner 2012 'Practical Reliability Engineering' 5th ed.; MIL-HDBK-338B §6"


def k_of_n(n: int, k: int, p: float) -> float:
    """P(at least k of n independent units succeed), each with probability p."""
    n, k, p = int(n), int(k), float(p)
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return min(1.0, sum(math.comb(n, i) * p ** i * (1.0 - p) ** (n - i) for i in range(k, n + 1)))


def sortie_success(lambda_per_fh: float, t_h: float) -> float:
    """exp(−λ t): probability that a sortie of t hours has no event of rate λ [1/FH]."""
    return math.exp(-float(lambda_per_fh) * float(t_h))


def min_n_for(k: int, p: float, confidence: float, n_max: int = 200) -> int | None:
    """Smallest n with P(≥ k of n) ≥ confidence (None if above n_max)."""
    for n in range(max(int(k), 1), int(n_max) + 1):
        if k_of_n(n, k, p) >= confidence:
            return n
    return None
