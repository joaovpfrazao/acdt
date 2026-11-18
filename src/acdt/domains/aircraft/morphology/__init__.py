"""P2 — N1 morphological matrix, physical incompatibility cuts, multidisciplinary evaluate, set-based prune.

Zwicky, F. (1969), "Discovery, Invention, Research through the Morphological Approach".
Sobek, D. K., Ward, A. C. & Liker, J. K. (1999), "Toyota's Principles of Set-Based Concurrent Engineering",
Sloan Management Review 40(2). Pareto dominance: Deb (2001) via :mod:`acdt.core.concept.tradeoff`.
P4 (10 nov 2026): energy / hybrid / datalink / SATCOM open axes with unassessed≠pass.
"""
from .matrix import SEED_DIMENSIONS, MorphMatrix, default_matrix, option_id, option_meta
from .generate import generate_architectures, cut_incompatible
from .evaluate import evaluate_architectures, assess_energy_and_comms, attach_operating_cost
from .prune import prune_set_based

__all__ = [
    "SEED_DIMENSIONS", "MorphMatrix", "default_matrix", "option_id", "option_meta",
    "generate_architectures", "cut_incompatible",
    "evaluate_architectures", "assess_energy_and_comms", "attach_operating_cost", "prune_set_based",
]
