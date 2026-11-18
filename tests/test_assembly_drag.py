"""P1b drag terms of the generic assembly: Raymer 12.5.5 junction Q, upsweep (Eq. 12.36), base (Eq. 12.37),
protuberances (Hoerner), L&P band, nominal / pessimistic CD0 and calibration factors."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from acdt.domains.aircraft.assembly import Assembly
from acdt.domains.aircraft.assembly.drag import base_Dq, upsweep_Dq
from acdt.domains.aircraft.assembly.sizing import cd0_buildup

EX = Path(__file__).resolve().parents[1] / "examples" / "integration"
TWIN = json.loads((EX / "twin_boom_pusher.json").read_text(encoding="utf-8"))
FC = (40.0, 1.112, 1.758e-5, 336.4)


def _cd0(comps, **drag):
    return cd0_buildup(Assembly.from_dict({"components": comps}), *FC, opts=drag)


def _simple(upsweep=0.0, wing_z=0.0, pod_y=None):
    c = [{"type": "body", "name": "f", "role": "fuselage",
          "pod": {"length": 3.0, "width": 0.4, "tail_frac": 0.4, "tail_scale": 0.1, "upsweep_deg": upsweep}},
         {"type": "surface", "name": "w", "role": "wing", "origin": [1.0, 0, wing_z], "mirror": True,
          "panel": {"root_chord": 0.6, "tip_chord": 0.4, "span": 2.5}}]
    if pod_y is not None:
        c.append({"type": "body", "name": "store", "role": "store", "origin": [0.9, pod_y, -0.14],
                  "pod": {"length": 0.8, "width": 0.15}})
    return c


def test_twin_boom_junctions_from_geometry():
    d = cd0_buildup(Assembly.from_dict(TWIN["assembly"]), *FC)
    q = {r["component"]: r["Q"] for r in d["components"]}
    assert q["pod"] == 1.0 and q["wing"] == 1.0 and q["tail"] == pytest.approx(1.03)
    assert q["boom"] == q["radome"] == q["satcom_dome"] == 1.5          # mounted directly (Raymer 12.5.5)
    assert d["CD0"] > d["CD0_clean"] and d["interference_dq_m2"] > 0
    pod = next(r for r in d["components"] if r["component"] == "pod")
    assert pod["base_m2"] == 0.0 and "carenada" in pod["base_note"]   # pusher hub fairs the base


def test_store_distance_categories():
    near = {r["component"]: r["Q"] for r in _cd0(_simple(pod_y=1.0))["components"]}
    assert near["store"] == 1.3
    far = {r["component"]: r["Q"] for r in _cd0([
        *_simple()[:2], {"type": "body", "name": "store", "role": "store", "origin": [0.9, 1.2, -1.5],
                         "pod": {"length": 0.8, "width": 0.15}}])["components"]}
    assert far["store"] == 1.0


def test_low_wing_unfilleted_vs_filleted():
    low = {r["component"]: r for r in _cd0(_simple(wing_z=-0.15))["components"]}["w"]
    assert low["Q"] == 1.25 and low["Q_pessimistic"] == 1.4
    fil = {r["component"]: r for r in _cd0(_simple(wing_z=-0.15), wing_fillet=True)["components"]}["w"]
    mid = {r["component"]: r for r in _cd0(_simple(wing_z=0.0))["components"]}["w"]
    assert fil["Q"] == mid["Q"] == 1.0


def test_upsweep_raises_cd0_raymer_12_36():
    clean, swept = _cd0(_simple(0.0)), _cd0(_simple(12.0))
    assert swept["upsweep_dq_m2"] > 0 and clean["upsweep_dq_m2"] == 0
    assert swept["CD0"] > clean["CD0"]
    b = Assembly.from_dict({"components": _simple(12.0)}).get("f")
    dq, u = upsweep_Dq(b)
    assert math.degrees(u) == pytest.approx(12.0, abs=0.01)
    assert dq == pytest.approx(3.83 * u ** 2.5 * float(b.section_area([1.8])[0]), rel=1e-6)


def test_base_drag_raymer_12_37():
    b = Assembly.from_dict({"components": _simple()}).get("f")
    dq, _ = base_Dq(b, 0.3, [])
    Ab = float(b.section_area([3.0])[0])
    assert dq == pytest.approx((0.139 + 0.419 * (0.3 - 0.161) ** 2) * Ab)


def test_band_protuberance_and_calibration():
    base = _cd0(_simple())
    assert base["CD0_pessimistic"] >= base["CD0_rss"] >= base["CD0"]
    p = _cd0(_simple(), protuberances=[{"name": "turret", "shape": "sphere", "diameter_m": 0.25,
                                        "exposed_fraction": 0.5}])
    dq = 0.47 * math.pi * 0.25 ** 2 / 4 * 0.5
    assert p["protuberance_dq_m2"] == pytest.approx(dq)
    assert p["CD0"] == pytest.approx(base["CD0"] + dq / base["Sref"] * 1.05)
    with pytest.raises(ValueError):
        _cd0(_simple(), protuberances=[{"name": "x", "shape": "cube", "diameter_m": 0.1}])
    k = _cd0(_simple(), calibration={"f": 1.2})
    f_row = {r["component"]: r for r in base["components"]}["f"]
    assert k["CD0"] == pytest.approx(base["CD0"] + 0.2 * f_row["f_m2"] / base["Sref"] * 1.05)
    assert k["calibration"] == {"f": 1.2}
    allk = _cd0(_simple(), calibration={"*": 0.9})
    assert allk["CD0"] == pytest.approx(0.9 * base["CD0"])
