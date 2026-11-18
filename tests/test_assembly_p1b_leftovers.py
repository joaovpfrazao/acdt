"""P1b leftovers: ``surfaces`` scaling (bodies fixed, tail volume coefficients kept), K from AVL (Kroo 2001)
with the Oswald fallback, automatic protuberances from items (Hoerner Ch. III) and the balance loop (neutral
point + gear fed back into the drawing).

Most cases are one AVL call. ``test_balance_reaches_target_static_margin`` and
``test_flying_wing_heavy_example_layout_and_assembly_hq`` each size an example once.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly import sizing as asz
from acdt.domains.aircraft.assembly.drag import auto_protuberances, cd0_buildup
from acdt.domains.aircraft.assembly.integration import check
from acdt.domains.aircraft.assembly.loop import AssemblyLoop, _tail_volume, scale_spec_surfaces
from acdt.domains.aircraft.assembly.sizing import _parts, main_wing
from acdt.domains.aircraft.mission import MissionSpec
from acdt.domains.aircraft.sizing import run

EX = Path(__file__).resolve().parents[1] / "examples"
TWIN = EX / "integration" / "twin_boom_pusher.json"


def _twin():
    return json.loads(TWIN.read_text(encoding="utf-8"))


def _spec(**opts):
    spec = MissionSpec.from_yaml(EX / "uav_gasoline_150kg.yaml")
    spec.assumptions["assembly"] = {"file": str(TWIN), "options": {"check_pessimistic": False, **opts}}
    return spec


needs_avl = pytest.mark.requires_avl


def test_surfaces_scaling_keeps_bodies_area_AR_and_tail_volumes():
    sp = _twin()
    asm0 = Assembly.from_dict(sp["assembly"])
    _, gw0 = main_wing(asm0)
    surfs, _, _, geos0, kinds = _parts(asm0)
    S, AR = 1.3 * gw0["S"], 1.1 * gw0["AR"]
    s2, info = scale_spec_surfaces(sp, S, AR)
    asm = Assembly.from_dict(s2["assembly"])
    _, gw = main_wing(asm)
    assert gw["S"] == pytest.approx(S, rel=1e-9) and gw["AR"] == pytest.approx(AR, rel=1e-9)
    assert info["k_b"] * info["k_c"] == pytest.approx(1.3) and info["k_b"] / info["k_c"] == pytest.approx(1.1)
    c0 = {c["name"]: c for c in sp["assembly"]["components"]}
    c2 = {c["name"]: c for c in s2["assembly"]["components"]}
    for n in ("pod", "boom"):                               # bodies kept as drawn
        assert c2[n] == c0[n]
    assert s2["items"] == sp["items"]
    _, _, _, geos, _ = _parts(asm)
    assert info["tails"]
    for n, v in info["volume_coefficients"].items():
        vh, vv = _tail_volume(v["kind"], gw, geos[n])
        req = [(a, b) for a, b in ((v["c_H"], vh), (v["c_V"], vv)) if a > 0]
        assert max(a / b for a, b in req) == pytest.approx(1.0, rel=1e-4)   # the governing coefficient is kept


def test_uniform_scaling_rejects_AR_option():
    with pytest.raises(ValueError):
        AssemblyLoop(_twin(), {"AR": 12.0})


def test_K_oswald_option_and_fallback_without_avl(monkeypatch):
    sp = _twin()
    lo = AssemblyLoop(sp, {"K_source": "oswald"})
    S0 = lo.S0
    assert lo.K(S0, 0.1, 0.03, 0.05) == (0.05, {"source": "oswald"})

    def boom(*a, **k):
        raise RuntimeError("no avl")
    monkeypatch.setattr(asz, "run_assembly_avl", boom)
    la = AssemblyLoop(sp)
    K, info = la.K(S0, 0.1, 0.03, 0.05)
    assert K == 0.05 and "oswald" in info["source"] and la.K_notes


@needs_avl
def test_K_from_avl_kroo():
    lo = AssemblyLoop(_twin())
    K, info = lo.K(lo.S0, 0.1, 0.03, 0.05)
    assert info["source"].startswith("avl")
    expect = 1 / (math.pi * info["AR"] * info["e_inv"] * info["s"]) + 0.38 * 0.03
    assert K == pytest.approx(expect) and 0.5 < info["e"] < 1.0 and 0.8 < info["s"] <= 1.0


def test_auto_protuberance_from_protruding_item():
    sp = _twin()
    asm = Assembly.from_dict(sp["assembly"])
    pos = check(asm, sp["items"], sp.get("constraints"))["positions"]
    pr, _ = auto_protuberances(asm, sp["items"], pos)
    names = {p["name"]: p for p in pr}
    g = names["item:eoir_gimbal"]                            # the turret hangs below the pod
    assert g["shape"] == "sphere" and g["exposed_fraction"] > 0.5 and g["auto"]
    assert "item:radar" not in names and "item:fuel_tank" not in names     # buried items give nothing
    kw = dict(V=40.0, rho=1.1, mu=1.75e-5, a=338.0)
    d_on = cd0_buildup(asm, kw["V"], kw["rho"], kw["mu"], kw["a"], items=sp["items"], positions=pos)
    d_off = cd0_buildup(asm, kw["V"], kw["rho"], kw["mu"], kw["a"], opts={"auto_protuberances": False},
                        items=sp["items"], positions=pos)
    assert d_on["CD0"] > d_off["CD0"]
    it = copy.deepcopy(sp["items"])
    next(i for i in it if i["name"] == "eoir_gimbal")["protuberance"] = False
    assert not auto_protuberances(asm, it, pos)[0]


@pytest.mark.slow
def test_surfaces_mode_in_sizing_loop_uses_option_AR():
    res = run(_spec(scaling="surfaces", AR=11.0, K_source="oswald"))
    lp = res.assembly_loop
    assert lp is not None and res.sizing.converged, [i.message for i in res.issues]
    g = main_wing(Assembly.from_dict(lp["spec_scaled"]["assembly"]))[1]
    assert g["S"] == pytest.approx(res.S, rel=1e-6) and g["AR"] == pytest.approx(11.0, rel=1e-6)
    pod0 = next(c for c in _twin()["assembly"]["components"] if c["name"] == "pod")
    assert next(c for c in lp["spec_scaled"]["assembly"]["components"] if c["name"] == "pod") == pod0


def test_balance_places_gear_masses_only_when_both_legs_exist(monkeypatch):
    """A missing nose station must not park the main-gear mass alone on the tip-back ray (Raymer Ch. 11)."""
    lo = AssemblyLoop(_twin(), {"balance": {"static_margin": 0.12}, "K_source": "oswald"})
    flight = {"other_masses": [
        {"key": "main_gear", "name": "main_gear", "mass_kg": 10.0},
        {"key": "nose_gear", "name": "nose_gear", "mass_kg": 3.0},
    ]}

    class _Out:
        def __init__(self, nose):
            self.static_margin = {"vazio": 0.12}
            self.np = {"mac": 0.5, "x_np": 1.0}
            self.gear = {"ground_z": -0.5, "h_cg": 0.5, "x_main": 1.8, "x_nose": nose, "checks": []}
            self.checks = []

    monkeypatch.setattr(asz, "analyse", lambda *a, **k: _Out(None))
    rec = lo.balance(lo.S0, flight)
    assert lo.gear_masses == [] and "trem incompleto" in rec["gear_note"]

    monkeypatch.setattr(asz, "analyse", lambda *a, **k: _Out(0.2))
    rec = lo.balance(lo.S0, flight)
    parked = {m["key"]: m["position"] for m in lo.gear_masses}
    assert set(parked) == {"main_gear", "nose_gear"}
    assert parked["nose_gear"][0] == pytest.approx(0.2) and parked["main_gear"][0] == pytest.approx(1.8)
    assert parked["main_gear"][2] == pytest.approx(-0.25)          # halfway from the ground to the CG
    assert rec["iterations"][-1].get("gear_masses_at_legs") is True


@pytest.mark.slow
@needs_avl
def test_balance_reaches_target_static_margin():
    """The published assembly checks, not only the balance record, close at 12 % with a nose gear."""
    from acdt.domains.aircraft.phase2 import stability_stage
    res = run(_spec(balance={"static_margin": 0.12}, static_margin_min=0.12))
    lp = res.assembly_loop
    assert lp is not None and res.sizing.converged, [i.message for i in res.issues]
    b = lp["balance"]
    last = b["passes"][-1]
    assert abs(last["SM_min"] - 0.12) < 0.01, b
    keys = {m["key"] for m in b["gear_masses"]}
    assert keys == {"main_gear", "nose_gear"}                         # both legs, from the CG
    stability_stage(res)
    checks = {c.key: c for c in res.checks}
    for k in ("asm:static_margin", "asm:gear_position", "asm:gear_tipback", "asm:integration"):
        assert k in checks and checks[k].ok, getattr(checks.get(k), "message", "missing")
    # the fixed-type gear (fuselage 0–3.2 m, no wheelbase) is replaced by the gear placed on the assembly
    for k in ("gear:position", "gear:tipback", "gear:nose_load", "gear:rotation"):
        assert checks[k].ok and checks[k].message.startswith("montagem:"), checks[k].message
    assert checks["hq:dutch_roll"].message.startswith("montagem:")
    assert res.dynamics["modes"]["derivatives"]["c_vt_measured"] == pytest.approx(0.10, abs=0.01)
    assert lp["K"]["source"].startswith("avl")


@pytest.mark.slow
@needs_avl
def test_flying_wing_heavy_example_layout_and_assembly_hq():
    """The 150 kg flying wing closes the layout checks that the G5 run left open.

    The checks that were already green on that run stay green: the scissor (still written for the
    fixed-type horizontal tail), the CG envelope and the gear stroke. Since the hq:* rows read the
    assembly (winglets only, c_vt ≈ 0.028 drawn), the dutch roll, short period and CAP fail: that is the
    honest answer of the same MIL-F-8785C limits; the old fixed-type rows (c_vt 0.10) are kept in
    ``res.dynamics['fixed_type']`` and still pass.
    """
    from acdt.domains.aircraft.phase2 import aeroelastic_stage, performance_stage, stability_stage
    res = run(MissionSpec.from_yaml(EX / "heavy" / "uav150_flying_wing.yaml"))
    assert res.sizing.converged, [i.message for i in res.issues]
    stability_stage(res)
    performance_stage(res)
    aeroelastic_stage(res)
    checks = {c.key: c for c in res.checks}
    must = ("gear:position", "gear:tipback", "asm:static_margin",
            "static_margin", "trim", "hq:scissor", "hq:phugoid", "hq:roll",
            "hq:spiral", "wb:envelope", "gear:stroke", "gear:nose_load", "asm:wing_area",
            "perf:endurance", "perf:service_ceiling", "perf:climb_rate", "perf:takeoff_ground_roll",
            "aeroel:divergence", "aeroel:reversal", "aeroel:flutter", "aeroel:aeer45")
    bad = [f"{k}: {checks[k].message if k in checks else 'missing'}" for k in must if k not in checks or not checks[k].ok]
    assert not bad, bad
    for k in ("hq:dutch_roll", "hq:short_period", "hq:CAP"):
        assert checks[k].message.startswith("montagem:") and not checks[k].ok, checks[k].message
    dy = res.dynamics
    assert dy["source"] == "assembly"
    assert dy["modes"]["derivatives"]["c_vt_measured"] < 0.03        # winglets only
    assert dy["modes"]["lateral"]["dutch_roll"]["zeta"] < 0            # divergent with the drawn winglets
    fixed = {r["key"]: r["nível"] for r in dy["fixed_type"]["hq"]}
    assert fixed["dutch_roll"] == 1 and fixed["CAP"] == 1               # the old c_vt = 0.10 answer
    assert res.feasible                                                 # hq:/gear: stay verification/layout
    assert any("gear: none" in n for n in res.landing_gear.notes)       # drawing has no gear: fixed type


# ------------------------------------------------------------------------------------------- P1b (a): MDO
@pytest.mark.slow
def test_mdo_uses_assembly_polar_masses_and_pessimistic_closure():
    pytest.importorskip("openmdao")
    from acdt.domains.aircraft.mdo import AircraftMDO, build_problem, evaluate, verification_spec
    spec = _spec(K_source="oswald")
    res = run(spec)
    assert res.assembly_loop is not None and res.sizing.converged
    m = AircraftMDO(spec, None, res)
    assert m.asm is not None and not AircraftMDO.ar_is_free(spec)
    pol, _ = m.polar(res.config, res.cruise_speed)
    assert pol.CD0 == pytest.approx(res.polar.CD0, rel=1e-6) and pol.K == pytest.approx(res.polar.K, rel=1e-6)
    w = m.weights(res.sizing.W0, res.sizing.Wf, res.design_point.ws, res.config.wing.AR, res.design_point.value,
                  res.structures.vn.n_limit_pos if res.structures else 3.8, pol.CD0, pol.K, 0.1)
    keys = {i.key for i in w["_bd"].items}
    assert "asm:wing" in keys and "wing" not in keys and w["m_wing"] > 0
    # pessimistic closure in the optimiser: switched after β, so CD0 rises
    sp = copy.deepcopy(spec)
    sp.assumptions.setdefault("mdo", {})["assembly_close_on"] = "pessimistic"
    mp = AircraftMDO(sp, None, res)
    assert mp.polar(res.config, res.cruise_speed)[0].CD0 > pol.CD0 * 1.01
    # uniform scaling: AR is not a design variable; one coupled evaluation closes near the baseline W0
    x0 = {"ws": res.design_point.ws, "pw": res.design_point.value, "AR": res.config.wing.AR}
    prob, _ = build_problem(m, x0, "W0", "nlbgs", ("ws",), None, None, 5, 1e-6,
                            {"W0": res.sizing.W0, "We": res.sizing.We, "Wf": res.sizing.Wf, "CD0": pol.CD0,
                             "K": pol.K})
    out = evaluate(prob, {"ws": x0["ws"]})
    assert out["W0"] == pytest.approx(res.sizing.W0, rel=0.08)
    vs = verification_spec(spec, {"optimum": {"ws": x0["ws"], "AR": 99.0}, "objective": "W0"})
    assert vs.assumptions["assembly"] == spec.assumptions["assembly"]      # uniform: drawing AR kept


def test_verification_spec_sets_assembly_AR_in_surfaces_mode():
    from acdt.domains.aircraft.mdo import AircraftMDO, verification_spec
    spec = _spec(scaling="surfaces")
    assert AircraftMDO.ar_is_free(spec)
    vs = verification_spec(spec, {"optimum": {"ws": 600.0, "AR": 12.3}, "objective": "W0"})
    o = vs.assumptions["assembly"]["options"]
    assert o["AR"] == 12.3 and o["scaling"] == "surfaces" and "file" not in vs.assumptions["assembly"]
