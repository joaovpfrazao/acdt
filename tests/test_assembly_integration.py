"""P1: generic component geometry, integration requirements, packaging + FOV checker (DESIGN_WORKFLOW §3 N0/N1)."""
import copy
import json
import math

import numpy as np
import pytest

from acdt.domains.aircraft.assembly import Assembly, Body, Disc, Surface, check
from acdt.domains.aircraft.assembly.components import _signed_volume, naca_yt
from acdt.domains.aircraft.assembly.integration import cast, direction

from conftest import EX

SPEC = json.loads((EX / "integration" / "twin_boom_pusher.json").read_text(encoding="utf-8"))


def _run(spec):
    return check(spec["assembly"], spec["items"], spec["constraints"], spec.get("base"))


def _get(res, typ, item=None, **kw):
    return [c for c in res["constraints"] if c["type"] == typ and (item is None or c.get("item") == item)
            and all(c.get(k) == v for k, v in kw.items())]


# ------------------------------------------------------------------ primitives against closed-form values
def test_body_volume_closed_form():
    """Constant elliptic section: V = π/4·w·h·L (Lamé n = 2); mesh volume converges to it; outward normals."""
    b = Body(name="cyl", stations=[{"x": 0, "w": 0.4, "h": 0.3}, {"x": 2.0, "w": 0.4, "h": 0.3}])
    exact = math.pi / 4 * 0.4 * 0.3 * 2.0
    assert b.volume() == pytest.approx(exact, rel=1e-9)
    V, F = b.mesh(fine=4)
    assert _signed_volume(V, F) == pytest.approx(exact, rel=0.01)
    # rectangle limit n → large: A → w·h
    r = Body(name="box", stations=[{"x": 0, "w": 0.4, "h": 0.3, "n": 200}, {"x": 1, "w": 0.4, "h": 0.3, "n": 200}])
    assert r.volume() == pytest.approx(0.12, rel=0.02)
    m = b.contains([[1.0, 0, 0], [1.0, 0.2, 0], [1.0, 0.0, 0.2]])
    assert m[0] == pytest.approx(0.15) and abs(m[1]) < 1e-12 and m[2] < 0


def test_naca_thickness_and_surface_volume():
    """NACA 00xx: max half-thickness t/2 at x/c ≈ 0.30 (Abbott & von Doenhoff 1959); section area 0.685·t·c²."""
    x = np.linspace(0, 1, 2001)
    yt = naca_yt(x, 0.12)
    assert yt.max() == pytest.approx(0.06, rel=0.01) and x[yt.argmax()] == pytest.approx(0.30, abs=0.01)
    assert 2 * np.trapezoid(yt, x) == pytest.approx(0.685 * 0.12, rel=0.01)
    w = Surface.panel("w", 1.0, 1.0, 2.0, tc_root=0.12)
    assert w.volume() == pytest.approx(0.685 * 0.12 * 1.0 * 2.0, rel=0.02)
    assert w.planform_area() == pytest.approx(2.0)
    assert w.contains([[0.3, 1.0, 0.0]])[0] == pytest.approx(0.06, rel=0.01)
    assert w.contains([[0.3, 1.0, 0.07]])[0] < 0 and w.contains([[0.3, 2.5, 0.0]])[0] < 0


def test_any_dihedral_and_mirror():
    """Same primitive gives a vertical fin (90°), an inverted V (negative dihedral) and a mirrored image."""
    fin = Surface.panel("fin", 0.5, 0.3, 1.0, dihedral_deg=90)
    V, _ = fin.mesh()
    assert V[:, 2].max() == pytest.approx(1.0, abs=1e-9) and abs(V[:, 1]).max() < 0.05
    a = Assembly([Surface.panel("iv", 0.4, 0.3, 1.0, dihedral_deg=-35, mirror=True, origin=(3, 0, 0.5))])
    assert [c.name for c in a.components] == ["iv", "iv~m"]
    for c in a.components:
        V, F = c.mesh()
        assert _signed_volume(V, F) > 0                              # outward normals after mirroring
    Vm, _ = a.get("iv~m").mesh()
    assert Vm[:, 1].min() == pytest.approx(-math.cos(math.radians(35)), abs=0.02)   # + thickness
    assert Vm[:, 2].min() == pytest.approx(0.5 - math.sin(math.radians(35)), abs=0.02)


def test_moller_trumbore_and_directions():
    tri = np.array([[[0, -1, -1], [0, 1, -1], [0, 0, 1.0]]])
    t = cast(np.array([[-2.0, 0, 0], [-2.0, 0, 0]]), np.array([[1.0, 0, 0], [-1.0, 0, 0]]), tri)
    assert t[0, 0] == pytest.approx(2.0) and math.isinf(t[1, 0])
    assert np.allclose(direction(0, 0), [-1, 0, 0]) and np.allclose(direction(90, 0), [0, 1, 0])
    assert np.allclose(direction(0, 90), [0, 0, 1], atol=1e-12)


# ------------------------------------------------------------------ the twin-boom pusher example
def test_twin_boom_pusher_passes():
    r = _run(SPEC)
    assert r["ok"], r["violations"]
    radar = _get(r, "fov", "radar")[0]
    assert radar["n_rays"] > 300 and radar["blocked_frac"] == 0          # 360° azimuth, down-look clear
    assert _get(r, "fov", "eoir_gimbal")[0]["ok"] and _get(r, "fov", "satcom")[0]["name"] == "sky_view"
    # fuel tank is drawn inside its x window (the placer is for items without a position)
    assert "fuel_tank" not in r["placement"] and 1.6 <= r["positions"]["fuel_tank"][0] <= 2.15
    assert _get(r, "within", "fuel_tank")[0]["margin"] >= 0
    mp = r["mass_properties"]
    m = sum(i["mass_kg"] for i in SPEC["items"]) + SPEC["base"]["mass_kg"]
    assert mp["mass_kg"] == pytest.approx(m)
    x = sum(v["mass_kg"] * v["r"][0] for v in mp["breakdown"].values()) / m
    assert mp["cg"][0] == pytest.approx(x) and abs(mp["cg"][1]) < 1e-9
    assert r["power_w"] == {"avg": 385.0, "peak": 660.0}
    assert r["missing_inputs"] == {"power_w or heat_w not given": ["fuel_tank", "payload_bay"]}
    assert any("PRESSUPOSTO" in a for a in r["assumptions"])
    assert r == _run(SPEC)                                               # deterministic


def test_low_booms_block_gimbal_horizon_view():
    """Booms hung below the wing (z = −0.25), gimbal on the aft belly with a horizon-search requirement up to
    +5° elevation: the starboard and port booms obstruct the side sectors (with the booms at wing level, z = +0.1,
    the same view is clear)."""
    s = copy.deepcopy(SPEC)
    boom = next(c for c in s["assembly"]["components"] if c["name"] == "boom")
    boom["origin"][2] = -0.25
    g = next(i for i in s["items"] if i["name"] == "eoir_gimbal")
    g["position"] = [3.0, 0, -0.30]                                       # belly, aft of the radome and the pusher disc
    g["fov"] = [{"name": "stbd_horizon", "band": "optical", "az_deg": [45, 100], "el_deg": [-10, 5], "step_deg": 2},
                {"name": "port_horizon", "band": "optical", "az_deg": [-100, -45], "el_deg": [-10, 5], "step_deg": 2}]
    r = _run(s)
    assert not r["ok"]
    stb, prt = _get(r, "fov", "eoir_gimbal")
    assert not stb["ok"] and stb["margin"] < 0 and set(stb["blocked_by"]) == {"boom"}
    assert not prt["ok"] and set(prt["blocked_by"]) == {"boom~m"}
    assert stb["blocked_el_range_deg"][1] > 0                                # the look-up part of the cone
    assert all(v["type"] == "fov" for v in r["violations"])
    boom["origin"][2] = 0.10
    assert all(f["ok"] for f in _get(_run(s), "fov", "eoir_gimbal"))


def test_satcom_aft_blocked_by_propeller():
    """SATCOM moved aft (x = 2.20, 0.28 m ahead of the pusher disc): the propeller disc blocks the low-elevation
    aft sky; the RF-transparent dome around it never counts as a blocker."""
    s = copy.deepcopy(SPEC)
    next(c for c in s["assembly"]["components"] if c["name"] == "satcom_dome")["origin"][0] = 1.90
    next(i for i in s["items"] if i["name"] == "satcom")["position"][0] = 2.20   # 0.28 m ahead of the disc at x = 2.48
    r = _run(s)
    f = _get(r, "fov", "satcom")[0]
    assert not f["ok"] and 0 < f["blocked_frac"] < 0.1 and "prop" in f["blocked_by"]
    assert "satcom_dome" not in f["blocked_by"]


def test_overlap_separation_keepout_and_unknown_item():
    s = copy.deepcopy(SPEC)
    s["items"].append({"name": "battery", "mass_kg": 5, "size_m": [0.2, 0.2, 0.2], "position": [2.48, 0, 0]})
    s["constraints"].append({"type": "min_separation", "a": "radar", "b": "satcom", "distance_m": 1.0})
    r = _run(s)
    bad = {(v["type"], v.get("item") or v.get("a")) for v in r["violations"]}
    assert ("keep_out", "battery") in bad and ("min_separation", "radar") in bad
    s["items"][-1]["position"] = list(s["items"][0]["position"])        # same place as the radar
    r = _run(s)
    assert any(v["type"] == "no_overlap" for v in r["violations"])
    with pytest.raises(ValueError):
        check(SPEC["assembly"], SPEC["items"], [{"type": "range", "item": "nope", "axis": "x"}])


def test_adapters_rcs_stl_avl(tmp_path):
    a = Assembly.from_dict(SPEC["assembly"])
    m = a.to_rcs_mesh()
    assert m.n_facets > 1000 and float(np.einsum("ij,ij->i", m.c, m.n).sum()) != 0
    p = a.write_stl(tmp_path / "a.stl")
    assert p.read_text(encoding="utf-8").count("facet normal") == sum(len(a.mesh(c.name)[1]) for c in a.components)
    txt = a.avl_text()
    assert txt.count("SURFACE") == 2 and txt.count("YDUPLICATE") == 2   # wing + tail, mirrored once
    assert "NACA\n0014" in txt
    assert "1.80000 0.00000 0.10000 0.55000 0.000" in txt          # wing root LE, chord
    assert "4.05000 0.90000 0.10000 0.66500 0.000" in txt          # inverted-V root LE, chord
    summ = a.summary()
    assert summ["components"]["wing"]["planform_area_m2"] == pytest.approx(0.5 * (0.55 + 0.35) * 2.6, rel=1e-3)


def test_mcp_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("ACDT_RUNS_DIR", str(tmp_path))
    from acdt.ai import assembly as A
    r = A.integration_check(SPEC["assembly"], SPEC["items"], SPEC["constraints"], SPEC["base"])
    assert r["ok"] and r["run_id"] and set(r["files"]) >= {"assembly_stl", "avl", "result"}
    g = A.assembly_geometry(SPEC["assembly"], write_files=False)
    assert "wing~m" in g["components"]
