
"""P4 morphological energy / hybrid / datalink / SATCOM axes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from acdt.ai import morph as M
from acdt.domains.aircraft.morphology import (
    assess_energy_and_comms, cut_incompatible, default_matrix, generate_architectures,
    prune_set_based,
)
from acdt.domains.aircraft.morphology.matrix import MorphMatrix, option_id
from acdt.domains.aircraft.morphology.evaluate import evaluate_architectures

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "examples" / "morphology" / "n1_energy_comms_matrix.json"
SYSTEMS = ROOT / "examples" / "morphology" / "n1_energy_comms_systems.json"
LEGACY = ROOT / "examples" / "morphology" / "n1_uav_isr_matrix.json"


def test_seeds_include_energy_comms_shortcuts():
    m = default_matrix()
    assert "hybrid_series" in m.dimensions["energy"]
    assert "datalink_LOS" in m.dimensions["avionics_link"]
    assert "SATCOM_Ku" in m.dimensions["avionics_link"]
    # legacy seeds kept
    assert "fuel" in m.dimensions["energy"]
    assert "LOS" in m.dimensions["avionics_link"]


def test_option_dict_generate_preserves_meta():
    m = MorphMatrix(dimensions={
        "energy": [{"id": "battery_LiIon", "source": "PRESSUPOSTO"}],
        "avionics_link": [{"id": "datalink_LOS", "power_W": 10, "source": "PRESSUPOSTO"}],
        "propulsion_kind": ["electric"],
    })
    gen = generate_architectures(m, max_combinations=10)
    assert gen["n"] == 1
    a = gen["architectures"][0]
    assert a["choices"]["energy"] == "battery_LiIon"
    assert a["option_meta"]["avionics_link"]["power_W"] == 10


def test_hybrid_series_piston_cut():
    arches = [{
        "id": "X", "choices": {
            "energy": "hybrid_series", "propulsion_kind": "piston",
            "wing": "high", "tail": "conventional",
        }
    }]
    cut = cut_incompatible(arches)
    assert cut["cut"] and "série" in cut["cut"][0]["reason"].lower() or "serie" in cut["cut"][0]["reason"].lower() or "elétrico" in cut["cut"][0]["reason"]


def test_hybrid_parallel_electric_cut():
    arches = [{"id": "Y", "choices": {"energy": "hybrid_parallel", "propulsion_kind": "electric"}}]
    cut = cut_incompatible(arches)
    assert any(c["id"] == "Y" for c in cut["cut"])


def test_assess_comms_unassessed_without_power():
    out = assess_energy_and_comms(
        {"avionics_link": "SATCOM_custom", "energy": "battery"},
        {"avionics_link": {"id": "SATCOM_custom"}},
    )
    assert "avionics_link" in out["unassessed_axes"]
    assert "comms_power_W" not in out["metrics"]  # never silent zero


def test_assess_comms_with_source():
    out = assess_energy_and_comms(
        {"avionics_link": "datalink_LOS", "energy": "battery", "propulsion_kind": "electric"},
        {"avionics_link": {"id": "datalink_LOS", "power_W": 25, "source": "PRESSUPOSTO"}},
    )
    assert out["unassessed_axes"] == []
    assert out["metrics"]["comms_power_W"] == 25


def test_assess_hybrid_needs_template():
    out = assess_energy_and_comms(
        {"energy": "hybrid_series", "propulsion_kind": "hybrid"},
        {},
        hybrid_templates={},
    )
    assert "energy" in out["unassessed_axes"]


def test_assess_hybrid_with_template():
    sysd = json.loads(SYSTEMS.read_text(encoding="utf-8"))
    out = assess_energy_and_comms(
        {"energy": "hybrid_series", "propulsion_kind": "hybrid"},
        {},
        hybrid_templates=sysd["hybrid_templates"],
        mission_context=sysd["mission_context"],
    )
    assert "energy" not in out["unassessed_axes"]
    assert out["metrics"].get("hybrid_fuel_kg") is not None
    assert out["reports"]["hybrid"]["status"] == "assessed"


def test_legacy_matrix_unchanged_generate():
    dims = json.loads(LEGACY.read_text(encoding="utf-8"))["dimensions"]
    out = M.morph_generate(dimensions=dims, seeds=False, max_combinations=500,
                           use_dimensions=["wing", "tail", "propulsion_kind", "energy",
                                           "landing_gear", "launch_recovery"])
    assert out["generated"] > 0
    assert out["n_cut"] >= 1  # flying_wing + conventional etc.


@pytest.mark.slow
def test_example_matrix_evaluate_mixed(tmp_path):
    dims = json.loads(MATRIX.read_text(encoding="utf-8"))["dimensions"]
    sysd = json.loads(SYSTEMS.read_text(encoding="utf-8"))
    gen = M.morph_generate(dimensions=dims, seeds=False, max_combinations=50)
    # pick three: battery+LOS, hybrid_series+Ku, custom_h2+SATCOM_custom
    want = []
    for a in gen["kept"]:
        ch = a["choices"]
        if ch["energy"] == "battery_LiIon" and ch["avionics_link"] == "datalink_LOS":
            want.append(a)
        elif ch["energy"] == "hybrid_series" and ch["avionics_link"] == "SATCOM_Ku":
            want.append(a)
        elif ch["energy"] == "custom_h2" and ch["avionics_link"] == "SATCOM_custom":
            want.append(a)
    assert len(want) >= 3
    # ensure option_meta present for dict options
    out = evaluate_architectures(
        want[:3], ROOT / "examples/uav_endurance_payload.yaml",
        sim_path=None, level="L0", run_mission=False,
        hybrid_templates=sysd["hybrid_templates"],
        link_catalog=sysd.get("link_catalog"),
        mission_context=sysd["mission_context"],
    )
    by_energy = {r["choices"]["energy"]: r for r in out["rows"]}
    # battery + LOS should be systems assessed
    bat = by_energy["battery_LiIon"]
    assert bat["systems_assessed"] is True
    assert bat["metrics"]["comms_power_W"] == 25
    assert "W0_kg" in bat["metrics"]
    # hybrid series assessed
    hy = by_energy["hybrid_series"]
    assert "energy" not in hy["unassessed_axes"]
    assert hy["metrics"].get("hybrid_fuel_kg") is not None
    # custom missing → unassessed energy + comms
    cu = by_energy["custom_h2"]
    assert "energy" in cu["unassessed_axes"]
    assert "avionics_link" in cu["unassessed_axes"]
    assert cu["feasible"] is False or cu["systems_assessed"] is False


def test_prune_holds_unassessed():
    rows = [
        {"id": "A", "evaluable": True, "metrics": {"W0_kg": 20.0, "endurance_min": 100.0},
         "unassessed_axes": []},
        {"id": "U", "evaluable": True, "metrics": {"W0_kg": 99.0, "endurance_min": 10.0},
         "unassessed_axes": ["avionics_link"]},
    ]
    out = prune_set_based(rows, objectives={"W0_kg": "min", "endurance_min": "max"},
                          band=0.15, keep=2)
    assert "U" in out["alive"]
    assert out["n_unassessed_held"] == 1
