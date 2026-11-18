"""P2 morphological N1: matrix, incompatibilities, set-based prune, light evaluate."""
from __future__ import annotations

from pathlib import Path

import pytest

from acdt.domains.aircraft.morphology import (
    cut_incompatible, default_matrix, generate_architectures, prune_set_based,
)
from acdt.domains.aircraft.morphology.evaluate import apply_choice_patches, evaluate_architectures
from acdt.domains.aircraft.mission import MissionSpec

ROOT = Path(__file__).resolve().parents[1]


def test_default_matrix_is_open_and_extendable():
    m = default_matrix({"wing": ["gull"], "novel": ["a", "b"]})
    assert "gull" in m.dimensions["wing"]
    assert "flying_wing" in m.dimensions["wing"]  # seed kept
    assert m.dimensions["novel"] == ["a", "b"]
    d = m.to_dict()
    assert "Zwicky" in d["reference"]


def test_generate_and_cut_flying_wing_conventional_tail():
    from acdt.domains.aircraft.morphology.matrix import MorphMatrix
    m = MorphMatrix(dimensions={
        "wing": ["high", "flying_wing"],
        "tail": ["conventional", "tailless"],
        "propulsion_kind": ["electric", "piston"],
        "energy": ["battery", "fuel"],
        "landing_gear": ["none", "tricycle"],
        "launch_recovery": ["catapult", "runway"],
    })
    gen = generate_architectures(m, max_combinations=200)
    assert gen["n"] == 2 * 2 * 2 * 2 * 2 * 2
    cut = cut_incompatible(gen["architectures"])
    bad = [c for c in cut["cut"]
           if c["choices"].get("wing") == "flying_wing" and c["choices"].get("tail") == "conventional"]
    assert bad, "asa voadora + cauda convencional tinha de ser cortada"
    assert all("reason" in c for c in cut["cut"])
    ef = [c for c in cut["cut"]
          if c["choices"].get("propulsion_kind") == "electric" and c["choices"].get("energy") == "fuel"]
    assert ef


def test_prune_set_based_keeps_non_dominated_under_band():
    rows = [
        {"id": "A", "evaluable": True, "metrics": {"W0_kg": 20.0, "endurance_min": 100.0, "range_km": 50.0}},
        # clearly worse than A even after ±15% optimistic/pessimistic widening
        {"id": "B", "evaluable": True, "metrics": {"W0_kg": 40.0, "endurance_min": 50.0, "range_km": 20.0}},
        {"id": "C", "evaluable": True, "metrics": {"W0_kg": 22.0, "endurance_min": 95.0, "range_km": 48.0}},
    ]
    out = prune_set_based(rows, objectives={"W0_kg": "min", "endurance_min": "max", "range_km": "max"},
                          band=0.15, keep=3)
    assert "A" in out["alive"]
    assert "B" in [r["id"] for r in out["rejected"]]


def test_apply_choice_patches_propulsion_and_gear():
    spec = MissionSpec.from_yaml(ROOT / "examples/uav_endurance_payload.yaml")
    notes = apply_choice_patches(spec, {"propulsion_kind": "electric", "landing_gear": "none",
                                        "launch_recovery": "catapult", "wing": "high"})
    assert spec.propulsion_kind == "electric"
    assert spec.assumptions["weights"]["components"]["landing_gear"] == "none"
    assert any("PRESSUPOSTO" in n and "wing=" in n for n in notes)


@pytest.mark.slow
def test_evaluate_two_architectures_l0(tmp_path):
    """Light integration: two kept architectures through size L0 (no mission judge)."""
    arches = [
        {"id": "A0001", "choices": {"propulsion_kind": "electric", "landing_gear": "none",
                                    "launch_recovery": "catapult", "energy": "battery"}},
        {"id": "A0002", "choices": {"propulsion_kind": "electric", "landing_gear": "tricycle",
                                    "launch_recovery": "runway", "energy": "battery"}},
    ]
    out = evaluate_architectures(arches, ROOT / "examples/uav_endurance_payload.yaml",
                                 sim_path=None, level="L0", run_mission=False, limit=2)
    assert out["n"] == 2
    assert all(r.get("evaluable") for r in out["rows"])
    assert all("W0_kg" in r["metrics"] for r in out["rows"])
