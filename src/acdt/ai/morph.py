"""Toolkit wrappers for P2 morphological N1 (generate / cut / evaluate / prune)."""
from __future__ import annotations

from acdt.domains.aircraft.morphology import (
    cut_incompatible, default_matrix, evaluate_architectures, generate_architectures, prune_set_based,
)
from acdt.domains.aircraft.morphology.matrix import MorphMatrix


def morph_matrix(extra: dict | None = None) -> dict:
    return default_matrix(extra).to_dict()


def morph_generate(dimensions: dict[str, list] | None = None,
                   use_dimensions: list[str] | None = None,
                   max_combinations: int = 200,
                   extra_rules: list | None = None,
                   seeds: bool = True) -> dict:
    """Build matrix, generate combinations, cut incompatibilities.

    If ``dimensions`` is given and ``seeds`` is False, use only that matrix (typical for a YAML/JSON
    example). If ``seeds`` is True (default), merge into the Zwicky seed matrix.
    Options may be strings or ``{id, source, retrieved?, …}`` dicts (P4 energy/comms).
    """
    if dimensions and not seeds:
        m = MorphMatrix(dimensions={k: list(v) for k, v in dimensions.items()})
        m.notes.append("matriz fornecida pelo utilizador/agente (sem fundir as sementes)")
    else:
        m = default_matrix(dimensions)
    gen = generate_architectures(m, dimensions=use_dimensions, max_combinations=max_combinations)
    cut = cut_incompatible(gen["architectures"], extra_rules=extra_rules)
    return {"matrix": m.to_dict(), "generated": gen["n"], "kept": cut["kept"], "cut": cut["cut"],
            "n_kept": len(cut["kept"]), "n_cut": len(cut["cut"]),
            "reference": gen["reference"] + "; " + cut["reference"]}


def morph_evaluate(architectures: list[dict], mission: str, sim: str | None = None,
                   level: str = "L0", limit: int | None = 12,
                   hybrid_templates: dict | None = None,
                   link_catalog: dict | None = None,
                   mission_context: dict | None = None,
                   operating_cost: dict | None = None) -> dict:
    """Evaluate architectures. Pass ``hybrid_templates`` / ``link_catalog`` to assess P4 axes.

    ``operating_cost``: optional DOC block (Raymer 2018 Ch. 18; Eastlake/DAPCA for unit_price).
    """
    return evaluate_architectures(
        architectures, mission, sim_path=sim, level=level,
        run_mission=bool(sim), limit=limit,
        hybrid_templates=hybrid_templates, link_catalog=link_catalog,
        mission_context=mission_context,
        operating_cost=operating_cost,
    )


def morph_prune(rows: list[dict], band: float = 0.15, keep: int = 3,
                objectives: dict | None = None) -> dict:
    return prune_set_based(rows, objectives=objectives, band=band, keep=keep)
