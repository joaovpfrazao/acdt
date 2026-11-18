"""P1b: the generic assembly inside the W0 loop of ``acdt size`` (rescaled each pass, per-part masses and
assembly CD0 in the loop and in performance), the pessimistic-CD0 closure check and the calibration hook."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly.loop import AssemblyLoop, scale_spec
from acdt.domains.aircraft.assembly.sizing import main_wing
from acdt.domains.aircraft.mission import MissionSpec
from acdt.domains.aircraft.sizing import run

EX = Path(__file__).resolve().parents[1] / "examples"
TWIN = EX / "integration" / "twin_boom_pusher.json"
FW = EX / "integration" / "flying_wing_pusher.json"


def _spec(path, **opts):
    spec = MissionSpec.from_yaml(EX / "uav_gasoline_150kg.yaml")
    spec.assumptions["assembly"] = {"file": str(path), "options": {"check_pessimistic": False, **opts}}
    return spec


def test_planform_fed_to_the_mission_is_plain_floats():
    """c_tip/c_root is a numpy scalar unless cast. The sizing report dumps assumptions as YAML."""
    import numpy as np
    import yaml

    from acdt.domains.aircraft.report import _yaml_ready

    loop = AssemblyLoop(json.loads(FW.read_text(encoding="utf-8")))
    plan = loop.planform()
    assert type(plan["taper"]) is float
    assert plan["taper"] == pytest.approx(0.36 / 0.9)
    dumped = yaml.safe_dump(_yaml_ready({"aero": {**plan, "taper": np.float64(plan["taper"])}}))
    assert "taper" in dumped


def test_scale_spec_keeps_proportions_and_matches_area():
    sp = json.loads(TWIN.read_text(encoding="utf-8"))
    S0 = main_wing(Assembly.from_dict(sp["assembly"]))[1]["S"]
    k = 1.3
    s2 = scale_spec(sp, k)
    g = main_wing(Assembly.from_dict(s2["assembly"]))[1]
    assert g["S"] == pytest.approx(S0 * k * k, rel=1e-9)
    g0 = main_wing(Assembly.from_dict(sp["assembly"]))[1]
    assert g["AR"] == pytest.approx(g0["AR"]) and g["taper"] == pytest.approx(g0["taper"])
    boom = next(c for c in s2["assembly"]["components"] if c["name"] == "boom")
    assert boom["origin"][1] == pytest.approx(0.9 * k)
    radar = next(i for i in s2["items"] if i["name"] == "radar")
    assert radar["size_m"] == [0.4, 0.34, 0.12]          # equipment is not scaled
    assert radar["position"][0] == pytest.approx(1.95 * k)
    assert s2["base"]["cg"][0] == pytest.approx(1.25 * k)   # illustrative structure CG scales with the drawing
    band = next(c for c in s2["constraints"] if c["type"] == "cg_range")
    assert band["min"] == pytest.approx(1.35 * k) and band["max"] == pytest.approx(1.85 * k)


@pytest.mark.slow
@pytest.mark.parametrize("path", [TWIN, FW], ids=["twin_boom", "flying_wing"])
def test_assembly_sized_inside_loop_converges(path):
    res = run(_spec(path))
    lp = res.assembly_loop
    assert lp is not None, [i.message for i in res.issues]
    assert res.sizing.converged and lp["converged"] and lp["iterations"] > 1
    # rescaled drawing matches the sized wing exactly
    S_sc = main_wing(Assembly.from_dict(lp["spec_scaled"]["assembly"]))[1]["S"]
    assert S_sc == pytest.approx(res.S, rel=1e-6)
    assert lp["k"] == pytest.approx(math.sqrt(res.S / lp["S_drawn_m2"]), rel=1e-9)
    # the polar used for performance is the assembly CD0, and the masses are the per-part ones
    assert res.polar.CD0 == pytest.approx(lp["drag"]["CD0_nominal"], rel=1e-9)
    keys = {i.key for i in res.weights.items if i.group == "structure"}
    assert not keys & {"wing", "htail", "vtail", "fuselage"}
    assert {"asm:wing"} <= keys
    assert lp["drag"]["CD0_pessimistic"] >= lp["drag"]["CD0_nominal"]
    assert res.config.wing.AR == pytest.approx(main_wing(Assembly.from_dict(lp["spec"]["assembly"]))[1]["AR"])


@pytest.mark.slow
def test_pessimistic_check_and_close_on_pessimistic():
    res = run(_spec(FW, check_pessimistic=True))
    c = {k.key: k for k in res.checks}["asm:closes_pessimistic_cd0"]
    assert c.ok is not None and "pessimista" in c.message
    pes = res.assembly_loop["pessimistic"]
    assert pes["W0"] >= res.sizing.W0
    assert res.feasible                                  # asm: checks do not change feasibility
    r2 = run(_spec(FW, close_on="pessimistic"))
    assert r2.polar.CD0 == pytest.approx(r2.assembly_loop["drag"]["CD0_pessimistic"], rel=1e-9)
    assert r2.sizing.W0 == pytest.approx(pes["W0"], rel=1e-3)
    assert "asm:closes_pessimistic_cd0" in {k.key for k in r2.checks}


@pytest.mark.slow
def test_calibration_factor_moves_loop_cd0():
    base = run(_spec(FW))
    sp = _spec(FW)
    sp.assumptions["assembly"]["drag"] = {**json.loads(FW.read_text(encoding="utf-8")).get("drag", {}),
                                          "calibration": {"*": 1.2}}
    cal = run(sp)
    assert cal.assembly_loop["drag"]["calibration"]
    assert cal.polar.CD0 > base.polar.CD0
    assert cal.sizing.W0 > base.sizing.W0


@pytest.mark.slow
def test_fixed_type_unchanged_without_assembly():
    spec = MissionSpec.from_yaml(EX / "cessna172_check.yaml")
    assert not spec.assumptions.get("assembly")
    res = run(spec)
    assert res.assembly_loop is None
    assert {"wing", "fuselage"} <= {i.key for i in res.weights.items}
