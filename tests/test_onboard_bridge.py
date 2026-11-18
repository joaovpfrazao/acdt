# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in onboard → native size/jet/VTOL burn bridge (Nansei hotel→fuel slice)."""
from copy import deepcopy
from pathlib import Path
import pytest
from acdt.ai.jet import load_spec, jet_size
from acdt.domains.aircraft.mission import MissionSpec
from acdt.domains.aircraft.onboard_bridge import (
    apply_onboard_to_jet_spec, apply_onboard_to_size_dict, apply_onboard_to_vtol_spec,
)
from acdt.domains.aircraft.vtol.size import size_vtol

ROOT = Path(__file__).resolve().parents[1]


def _prop_onboard(power_W=400, with_bsfc=True):
    src = {
        "id": "bus", "kind": "generator", "item_id": "alternator",
        "delivery_efficiency": 0.9, "continuous_W": 1000, "peak_W": 1000,
        "generator_efficiency": 0.75, "shaft_limit_W": 1500,
        "source": "PRESSUPOSTO test",
    }
    if with_bsfc:
        src["bsfc_kg_kWh_shaft"] = 0.35
    return {
        "schema_version": "1.0",
        "source": "PRESSUPOSTO test — not a datasheet",
        "items": [
            {"id": "radar", "role": "payload", "mass_kg": 2.0,
             "mass_accounting": "incremental", "source": "PRESSUPOSTO"},
            {"id": "alternator", "role": "equipment", "mass_kg": 1.0,
             "mass_accounting": "incremental", "source": "PRESSUPOSTO"},
        ],
        "loads": [{"id": "radar_load", "item_id": "radar", "source_id": "bus",
                   "power_W": power_W, "peak_W": power_W * 1.5, "duty": 1.0,
                   "source": "PRESSUPOSTO"}],
        "sources": [src],
    }


def test_bridge_noop_without_onboard():
    d, rep = apply_onboard_to_size_dict({"requirements": {"propulsion_type": "piston_prop"}})
    assert rep["applied"] is False
    assert "auxiliary_fuel_flow_kg_s" not in (d.get("assumptions") or {}).get("propulsion", {})


def test_prop_bridge_sets_auxiliary_and_scales_with_power():
    base = {
        "requirements": {"propulsion_type": "piston_prop",
                         "payload_mass": {"target": 10, "unit": "kg"}},
        "assumptions": {"propulsion": {}, "weights": {}},
        "onboard": _prop_onboard(400),
        "duration": {"precruise_s": 60, "postcruise_s": 30},
    }
    d1, r1 = apply_onboard_to_size_dict(base)
    assert r1["applied"] and r1["fuel_flow_kg_s"] > 0
    assert d1["assumptions"]["propulsion"]["auxiliary_fuel_flow_kg_s"] == pytest.approx(r1["fuel_flow_kg_s"])
    assert d1["assumptions"]["propulsion"]["auxiliary_shaft_W"] == pytest.approx(r1["shaft_extraction_W"])
    assert d1["requirements"]["payload_mass"]["target"] == pytest.approx(12.0)  # +2 incremental
    assert d1["assumptions"]["weights"]["fixed_mass_kg"] == pytest.approx(1.0)
    assert "onboard" not in d1

    d2, r2 = apply_onboard_to_size_dict({**base, "onboard": _prop_onboard(800)})
    assert r2["fuel_flow_kg_s"] == pytest.approx(2 * r1["fuel_flow_kg_s"])


def test_prop_missing_bsfc_is_unassessed_not_zero():
    base = {
        "requirements": {"propulsion_type": "piston_prop"},
        "assumptions": {"propulsion": {}},
        "onboard": _prop_onboard(with_bsfc=False),
    }
    with pytest.raises(ValueError, match="unassessed|extraction"):
        apply_onboard_to_size_dict(base)


def test_hybrid_onboard_raises_unassessed():
    d = {
        "requirements": {"propulsion_type": "hybrid"},
        "onboard": _prop_onboard(),
    }
    with pytest.raises(ValueError, match="unassessed|hybrid"):
        apply_onboard_to_size_dict(d)


def test_legacy_overlap_refused():
    d = {
        "requirements": {"propulsion_type": "piston_prop"},
        "assumptions": {"propulsion": {"auxiliary_fuel_flow_kg_s": 1e-5, "auxiliary_shaft_W": 10}},
        "onboard": _prop_onboard(),
    }
    with pytest.raises(ValueError, match="already has hotel"):
        apply_onboard_to_size_dict(d)


def test_mission_spec_from_dict_applies_bridge():
    raw = load_spec(ROOT / "examples/onboard/prop_size_radar_hotel.yaml")
    m = MissionSpec.from_dict(raw)
    p = m.assumptions["propulsion"]
    assert p["auxiliary_fuel_flow_kg_s"] > 0
    assert p["auxiliary_shaft_W"] > 0
    assert m.assumptions["onboard_bridge"]["applied"] is True


@pytest.mark.slow
def test_acdt_size_fuel_rises_with_radar_hotel():
    """Runnable numbers: same mission with vs without onboard hotel load.

    Fecho automático no size: MissionSpec.from_dict applies onboard_bridge; DesignResult /
    result.json / toolkit summary expose it — no separate onboard_size step.
    """
    from acdt.ai.toolkit import size as Tsize
    with_h = Tsize(spec_path=str(ROOT / "examples/onboard/prop_size_radar_hotel.yaml"),
                   level="L0", no_systems=True)
    no_h = Tsize(spec_path=str(ROOT / "examples/onboard/prop_size_baseline_no_hotel.yaml"),
                 level="L0", no_systems=True)
    wf = with_h["summary"]["weights"]["Wfuel_or_battery_kg"]
    wo = no_h["summary"]["weights"]["Wfuel_or_battery_kg"]
    assert wf > wo
    # hotel-only contribution order of magnitude: ~400 W / η / BSFC over ~10 h cruise
    # (mass also rises; assert both fuel and bridge report)
    assert with_h["summary"]["weights"]["W0_kg"] > no_h["summary"]["weights"]["W0_kg"]
    br = with_h["summary"].get("onboard_bridge")
    assert br and br.get("applied") is True
    assert br.get("fuel_flow_kg_s", 0) > 0
    assert br.get("incremental_payload_kg", 0) > 0
    # absent block → legacy: no bridge report, and no auto hotel
    assert no_h["summary"].get("onboard_bridge") in (None, {})
    msgs = " ".join(i.get("message", "") for i in with_h["summary"].get("issues", []) if isinstance(i, dict))
    assert "onboard auto-closed" in msgs


def test_design_result_exposes_onboard_bridge_via_sizing_run():
    """Direct DesignResult path (sizing.run / acdt size) surfaces onboard_bridge."""
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.report import to_dict
    from acdt.domains.aircraft.sizing import run as size_run
    spec = MissionSpec.from_yaml(ROOT / "examples/onboard/prop_size_radar_hotel.yaml")
    res = size_run(spec)
    assert res.onboard_bridge and res.onboard_bridge.get("applied")
    d = to_dict(res)
    assert d["onboard_bridge"]["applied"] is True
    assert any("onboard auto-closed" in i.message for i in res.issues)
    # baseline without onboard stays None
    base = MissionSpec.from_yaml(ROOT / "examples/onboard/prop_size_baseline_no_hotel.yaml")
    r0 = size_run(base)
    assert r0.onboard_bridge is None


def test_jet_bridge_increases_fuel_and_missing_raises():
    base = load_spec(ROOT / "examples/jet/coupled_size.yaml")
    r0 = jet_size(deepcopy(base), record=False)
    onboard = {
        "schema_version": "1.0",
        "source": "PRESSUPOSTO test",
        "items": [
            {"id": "radar", "role": "payload", "mass_kg": 50,
             "mass_accounting": "incremental", "source": "PRESSUPOSTO"},
            {"id": "gen", "role": "equipment", "mass_kg": 20,
             "mass_accounting": "incremental", "source": "PRESSUPOSTO"},
        ],
        "loads": [{"id": "L", "item_id": "radar", "source_id": "bus",
                   "power_W": 2000, "peak_W": 3000, "duty": 1.0, "source": "PRESSUPOSTO"}],
        "sources": [{"id": "bus", "kind": "generator", "item_id": "gen",
                     "delivery_efficiency": 0.9, "continuous_W": 5000, "peak_W": 5000,
                     "fuel_kg_kWh_terminal": 0.4, "thrust_penalty_N_per_W_terminal": 0.001,
                     "source": "PRESSUPOSTO"}],
    }
    spec = deepcopy(base)
    spec["onboard"] = onboard
    spec["duration"] = {"precruise_s": 600, "postcruise_s": 300}
    r1 = jet_size(spec, record=False)
    assert r1["weights"]["fuel_mass_kg"] > r0["weights"]["fuel_mass_kg"]
    assert r1["onboard_bridge"]["applied"] is True
    assert r1["auxiliary"]["fuel_flow_kg_s"] > 0

    bad = deepcopy(base)
    bad["onboard"] = deepcopy(onboard)
    del bad["onboard"]["sources"][0]["fuel_kg_kWh_terminal"]
    with pytest.raises(ValueError, match="unassessed|extraction|fuel_kg_kWh"):
        jet_size(bad, record=False)


def test_vtol_bridge_increases_energy():
    recipe = load_spec(ROOT / "examples/onboard/vtol.yaml")
    ac = recipe["aircraft"]
    if isinstance(ac, str):
        ac = load_spec(ROOT / "examples/onboard" / ac)
    base = deepcopy(ac)
    base.setdefault("electric", {}).pop("systems_power_W", None)
    base["electric"].pop("systems_peak_power_W", None)
    r0 = size_vtol(deepcopy(base))
    spec = deepcopy(ac)
    spec["onboard"] = recipe["onboard"]
    spec.setdefault("electric", {}).pop("systems_power_W", None)
    spec["electric"].pop("systems_peak_power_W", None)
    r1 = size_vtol(spec)
    assert r1["energy_Wh"] > r0["energy_Wh"]
    assert r1["onboard_bridge"]["applied"] is True
    assert r1["onboard_bridge"]["systems_power_W"] > 0


def test_electric_bridge_sets_onboard_power_W():
    d = {
        "requirements": {"propulsion_type": "electric",
                         "payload_mass": {"target": 4, "unit": "kg"}},
        "assumptions": {"propulsion": {}, "weights": {}},
        "onboard": {
            "schema_version": "1.0",
            "source": "PRESSUPOSTO",
            "items": [{"id": "inst", "role": "payload", "mass_kg": 1,
                       "mass_accounting": "incremental", "source": "PRESSUPOSTO"}],
            "loads": [{"id": "L", "item_id": "inst", "source_id": "bus",
                       "power_W": 50, "peak_W": 100, "duty": 0.5, "source": "PRESSUPOSTO"}],
            "sources": [{"id": "bus", "kind": "main_battery", "delivery_efficiency": 0.9,
                         "continuous_W": 1000, "peak_W": 1000, "source": "PRESSUPOSTO"}],
        },
    }
    out, rep = apply_onboard_to_size_dict(d)
    assert rep["applied"]
    assert out["assumptions"]["propulsion"]["onboard_power_W"] == pytest.approx(25 / 0.9)
