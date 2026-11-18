# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in flying-wing shortcuts: size winglets from Raymer Eq. 6.29 c_VT; place tricycle gear."""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly.flying_wing import (
    apply_flying_wing_options,
    enable_tricycle_gear,
    measure_c_vt,
    size_winglets_to_c_vt,
)
from acdt.domains.aircraft.mission import MissionSpec
from acdt.domains.aircraft.sizing import run as size_run

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
FW = json.loads((EX / "integration" / "flying_wing_pusher.json").read_text(encoding="utf-8"))
FW_CLOSED = json.loads((EX / "integration" / "flying_wing_pusher_closed.json").read_text(encoding="utf-8"))
needs_avl = pytest.mark.requires_avl


def test_measure_c_vt_as_drawn():
    assert measure_c_vt(Assembly.from_dict(FW["assembly"])) == pytest.approx(0.028, abs=0.002)


def test_size_winglets_refuses_missing_or_nonpositive_target():
    s = copy.deepcopy(FW)
    r = size_winglets_to_c_vt(s, 0.0)
    assert r["status"] == "unassessed"
    assert "invented" in r["issues"][0].lower() or "non-positive" in r["issues"][0].lower()


def test_size_winglets_scales_chord_toward_c_vt():
    s = copy.deepcopy(FW)
    r = size_winglets_to_c_vt(s, 0.22)
    assert r["status"] == "assessed"
    assert r["c_vt_before"] == pytest.approx(0.028, abs=0.002)
    assert r["c_vt_after"] == pytest.approx(0.22, rel=0.05)
    assert r["scale_chord_total"] > 1.0
    # span / tip station fixed — only chords grow
    w0 = next(c for c in FW["assembly"]["components"] if c["name"] == "winglet")
    w1 = next(c for c in s["assembly"]["components"] if c["name"] == "winglet")
    assert w1["panel"]["span"] == pytest.approx(w0["panel"]["span"])
    assert w1["panel"]["root_chord"] > w0["panel"]["root_chord"]


def test_apply_missing_c_vt_is_unassessed_not_invented():
    s = copy.deepcopy(FW)
    s.setdefault("options", {})["flying_wing"] = {"size_winglets": True}
    out, rep = apply_flying_wing_options(s)
    assert rep["steps"][0]["status"] == "unassessed"
    assert "c_vt" in rep["steps"][0]["issues"][0]
    # drawing unchanged
    assert measure_c_vt(Assembly.from_dict(out["assembly"])) == pytest.approx(
        measure_c_vt(Assembly.from_dict(FW["assembly"])))


def test_apply_omit_block_is_noop():
    s = copy.deepcopy(FW)
    out, rep = apply_flying_wing_options(s)
    assert rep is None and out is s


def test_enable_tricycle_gear_and_pressuposto_band_note():
    s = copy.deepcopy(FW)
    assert (s.get("gear") or {}).get("type") == "none"
    r = enable_tricycle_gear(s, {"nose_fraction": [0.05, 0.22]})
    assert r["status"] == "requested"
    assert s["gear"]["type"] == "tricycle"
    assert list(s["gear"]["nose_fraction"]) == [0.05, 0.22]
    assert "PRESSUPOSTO" in r["nose_fraction_note"]


@pytest.mark.slow
@pytest.mark.requires_avl
def test_baseline_heavy_example_omits_flying_wing_option():
    """examples/heavy/uav150_flying_wing.yaml must stay unchanged when the option is absent."""
    res = size_run(MissionSpec.from_yaml(EX / "heavy" / "uav150_flying_wing.yaml"))
    assert res.sizing.converged
    assert res.assembly_loop is not None
    assert res.assembly_loop.get("flying_wing") is None
    assert (res.assembly_loop.get("spec") or {}).get("gear", {}).get("type") == "none"
    assert res.sizing.W0 == pytest.approx(138.2, abs=2.0)


@pytest.mark.slow
@needs_avl
def test_closed_flying_wing_winglets_and_gear():
    """Opt-in closed example: sized tip fins + tricycle on the mesh; hq/gear assessed, not fake-pass."""
    from acdt.domains.aircraft.phase2 import stability_stage
    res = size_run(MissionSpec.from_yaml(EX / "heavy" / "uav150_flying_wing_closed.yaml"))
    assert res.sizing.converged
    fw = (res.assembly_loop or {}).get("flying_wing")
    assert fw and fw.get("schema") == "flying_wing"
    steps = {s["step"]: s for s in fw.get("steps") or []}
    assert steps["size_winglets"]["status"] in ("assessed", "residual")
    assert steps["size_winglets"]["c_vt_after"] == pytest.approx(0.22, rel=0.08)
    assert steps["place_gear"]["status"] == "requested"
    assert "PRESSUPOSTO" in (steps["place_gear"].get("nose_fraction_note") or "")
    stability_stage(res)
    checks = {c.key: c for c in res.checks}
    assert checks["hq:dutch_roll"].ok is True
    assert checks["hq:spiral"].ok is True
    for k in ("asm:gear_position", "gear:position", "gear:tipback", "gear:nose_load", "gear:rotation"):
        assert checks[k].ok is True, f"{k}: {checks[k].message}"
    assert res.feasible
    assert res.sizing.W0 == pytest.approx(152.3, abs=5.0)
    assert res.S == pytest.approx(2.06, abs=0.15)
