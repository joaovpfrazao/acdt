"""Combine matrix options and cut physical incompatibilities with a written reason.

Incompatibilities are physical (or energy-balance) contradictions, not habit. The agent may pass
extra rules. Unknown combinations stay; only matching rules cut.
"""
from __future__ import annotations

from itertools import product
from typing import Iterable

from .matrix import MorphMatrix, index_option_meta, normalize_dimensions, option_id

# Each rule: (dimension_a, option_a_or_None=any, dimension_b, option_b_or_None, reason_pt)
# option None = any value of that dimension.
DEFAULT_INCOMPATIBILITIES: list[tuple] = [
    ("tail", "tailless", "wing", "low",
     "asa baixa convencional com cauda exige empennagem; tailless implica asa voadora / blended"),
    ("tail", "conventional", "wing", "flying_wing",
     "asa voadora não leva empennagem convencional (Raymer Cap. 4; tailless)"),
    ("tail", "T", "wing", "flying_wing",
     "asa voadora é tailless; cauda em T incompatível"),
    ("tail", "H", "wing", "flying_wing",
     "asa voadora é tailless; cauda em H incompatível"),
    ("tail", "canard", "wing", "flying_wing",
     "asa voadora tipicamente sem canard separado; usar opção canard+asa distinta"),
    # yaw control (extra dimension the user may add; not a seed — named options are shortcuts)
    ("yaw_control", "rudder", "tail", "tailless",
     "sem superfície vertical não há leme; tailless usa split_aileron (drag rudder) ou outra guinada"),
    ("propulsion_layout", "on_booms", "fuselage", "pod",
     "propulsão nas vigas exige configuração com vigas (twin_boom), não só pod"),
    ("fuselage", "twin_boom", "tail", "canard",
     "bivigas clássico leva a cauda atrás nas vigas; canard à frente é outra família"),
    ("landing_gear", "none", "launch_recovery", "runway",
     "pista exige trem ou esquis; landing_gear=none só com catapulta/rede/paraquedas/VTOL"),
    ("landing_gear", "tricycle", "launch_recovery", "catapult",
     "lançamento por catapulta tipicamente sem trem (Raymer Cap. 11; PRESSUPOSTO operacional)"),
    ("landing_gear", "taildragger", "launch_recovery", "catapult",
     "catapulta tipicamente sem trem convencional"),
    # energy ↔ propulsion (legacy + expanded shortcuts)
    ("energy", "fuel", "propulsion_kind", "electric",
     "propulsão só elétrica não usa combustível como energia primária"),
    ("energy", "fuel_avgas", "propulsion_kind", "electric",
     "propulsão só elétrica não usa AVGAS como energia primária"),
    ("energy", "fuel_jetA", "propulsion_kind", "electric",
     "propulsão só elétrica não usa Jet-A como energia primária"),
    ("energy", "battery", "propulsion_kind", "piston",
     "pistão requer combustível; bateria só não alimenta pistão"),
    ("energy", "battery_LiIon", "propulsion_kind", "piston",
     "pistão requer combustível; pack Li-ion só não alimenta pistão"),
    ("propulsion_kind", "hybrid", "energy", "fuel",
     "híbrido precisa de combustível e bateria — usar energy=hybrid|hybrid_series|hybrid_parallel"),
    ("propulsion_kind", "hybrid", "energy", "fuel_avgas",
     "híbrido precisa de combustível e bateria — usar energy=hybrid|hybrid_series|hybrid_parallel"),
    ("propulsion_kind", "hybrid", "energy", "fuel_jetA",
     "híbrido precisa de combustível e bateria — usar energy=hybrid|hybrid_series|hybrid_parallel"),
    ("propulsion_kind", "hybrid", "energy", "battery",
     "híbrido precisa de combustível e bateria — usar energy=hybrid|hybrid_series|hybrid_parallel"),
    ("propulsion_kind", "hybrid", "energy", "battery_LiIon",
     "híbrido precisa de combustível e bateria — usar energy=hybrid|hybrid_series|hybrid_parallel"),
    # series hybrid: shaft is electric (Pornet & Isikveren 2015) — piston-only kind contradicts
    ("energy", "hybrid_series", "propulsion_kind", "piston",
     "híbrido série: o eixo propulsor é elétrico (Pornet & Isikveren 2015); "
     "propulsion_kind=piston puro é fisicamente inconsistente — usar hybrid ou electric"),
    # parallel hybrid needs a mechanical engine path — pure electric kind contradicts
    ("energy", "hybrid_parallel", "propulsion_kind", "electric",
     "híbrido paralelo: motor térmico no eixo + assistência elétrica (Pornet & Isikveren 2015); "
     "propulsion_kind=electric puro omite o ramo térmico — usar hybrid"),
]


def _match(choice: dict, dim: str, opt: str | None) -> bool:
    if dim not in choice:
        return False
    return opt is None or choice[dim] == opt


def cut_incompatible(architectures: list[dict],
                     extra_rules: Iterable[tuple] | None = None) -> dict:
    """Split into ``kept`` and ``cut``; each cut row has ``id``, ``choices``, ``reason``."""
    rules = list(DEFAULT_INCOMPATIBILITIES) + list(extra_rules or [])
    kept, cut = [], []
    for a in architectures:
        ch = a["choices"]
        reason = None
        for da, oa, db, ob, why in rules:
            if _match(ch, da, oa) and _match(ch, db, ob):
                if da == db and oa == ob:
                    continue
                reason = why
                break
        if reason:
            cut.append({**a, "reason": reason})
        else:
            kept.append(a)
    return {"kept": kept, "cut": cut,
            "reference": "incompatibilidades físicas com motivo escrito (DESIGN_WORKFLOW § N1); "
                         "não por hábito de projeto; energia/híbrido P4 (Pornet & Isikveren 2015)"}


def generate_architectures(matrix: MorphMatrix, dimensions: list[str] | None = None,
                           max_combinations: int = 500) -> dict:
    """Cartesian product over selected dimensions (default: all). Caps at ``max_combinations``.

    PRESSUPOSTO: um tecto evita explosão combinatória; a IA estreita a matriz antes de gerar.
    Option dicts contribute their ``id`` to choices; full meta is attached under ``option_meta``.
    """
    dims = dimensions or list(matrix.dimensions.keys())
    missing = [d for d in dims if d not in matrix.dimensions or not matrix.dimensions[d]]
    if missing:
        raise ValueError(f"dimensões sem opções: {missing}")
    keys = dims
    id_dims = normalize_dimensions({k: matrix.dimensions[k] for k in keys})
    meta = index_option_meta({k: matrix.dimensions[k] for k in keys})
    values = [id_dims[d] for d in keys]
    n = 1
    for v in values:
        n *= len(v)
    if n > max_combinations:
        raise ValueError(
            f"{n} combinações > max_combinations={max_combinations}; "
            "estreitar a matriz (menos opções por dimensão) ou subir o tecto com consciência")
    arch = []
    for i, combo in enumerate(product(*values)):
        choices = dict(zip(keys, combo))
        choice_meta = {d: meta[d][choices[d]] for d in keys}
        arch.append({"id": f"A{i:04d}", "choices": choices, "option_meta": choice_meta})
    return {"architectures": arch, "n": len(arch), "dimensions": keys,
            "reference": "Zwicky 1969 — combinação morfológica; cortes em cut_incompatible; "
                         "option_meta preserva source/retrieved das opções-dict"}
