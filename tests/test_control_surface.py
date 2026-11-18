# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Sealed plain flap and the split-leaf pose. No SU2 and no pyHyp."""
import math

import numpy as np
import pytest

from acdt.domains.aircraft.assembly.components import Surface
from acdt.domains.aircraft.hifi.control_surface import (
    ControlDeflectionError, apply_plain_flap, avl_text_plain_flap, marker_hinge_moment,
    measured_flap_angle_deg, pressure_from_conservative, pressure_hinge_moment,
    read_su2_marker, read_surface_csv_pressure, split_leaf_pose,
)
from acdt.domains.aircraft.hifi.wing_bl import (
    CONTROLS, WingGeometryError, avl_text, build_patches, cruise_state, h1_factor_decision,
    mac_quarter_chord, reference_quantities, scaled_wing, su2_rans_cfg, verify_wing_rans_geometry,
    write_su2_volume,
)


def _wing_patches(n_chord=17, n_span=17, n_tip=5, flip_i=False):
    surf, _ = scaled_wing()
    return surf, build_patches(surf, n_chord, n_span, n_tip, flip_i=flip_i)


def _elevon(patches, delta):
    spec = CONTROLS["elevon"]
    return apply_plain_flap(
        patches, name="elevon", eta=spec["eta"], x_hinge=1.0 - spec["cf_c"], delta_deg=delta)


def test_zero_deflection_matches_the_faired_loft():
    _surf, patches = _wing_patches()
    out = _elevon(patches, 0.0)
    for key in ("upper", "lower", "tip", "le"):
        assert np.allclose(out[key], patches[key], atol=1e-12, rtol=0.0)
    assert np.allclose(out["te"], patches["te"], atol=1e-9, rtol=0.0)
    assert out["controls"][0]["delta_deg"] == 0.0
    assert measured_flap_angle_deg(out, out["controls"][0]) == pytest.approx(0.0, abs=1e-8)


def test_positive_deflection_lowers_the_trailing_edge_and_keeps_the_hinge():
    _surf, patches = _wing_patches()
    out = _elevon(patches, 12.0)
    spec = out["controls"][0]
    assert spec["x_hinge"] == pytest.approx(0.75)
    assert spec["x_hinge_mesh"] <= 0.75 + 1e-12
    assert measured_flap_angle_deg(out, spec) == pytest.approx(12.0, abs=1e-6)
    j = spec["j"][0]
    i_h = spec["i_hinge_upper"]
    assert np.allclose(out["upper"][i_h, j], patches["upper"][i_h, j], atol=1e-12, rtol=0.0)
    frame = patches["frames"][j]
    t = np.asarray(frame[2], float)
    i_te = patches["upper"].shape[0] - 1
    before = float(np.dot(patches["upper"][i_te, j] - patches["upper"][i_h, j], t))
    after = float(np.dot(out["upper"][i_te, j] - out["upper"][i_h, j], t))
    assert after < before


def test_negative_deflection_raises_the_trailing_edge():
    _surf, patches = _wing_patches()
    out = _elevon(patches, -25.0)
    spec = out["controls"][0]
    assert measured_flap_angle_deg(out, spec) == pytest.approx(-25.0, abs=1e-6)
    j = (spec["j"][0] + spec["j"][1]) // 2
    i_h = spec["i_hinge_upper"]
    i_te = -1
    t = np.asarray(patches["frames"][j][2], float)
    before = float(np.dot(patches["upper"][i_te, j] - patches["upper"][i_h, j], t))
    after = float(np.dot(out["upper"][i_te, j] - out["upper"][i_h, j], t))
    assert after > before


def test_flipped_index_keeps_the_same_angle():
    _surf, patches = _wing_patches(flip_i=True)
    out = _elevon(patches, 8.0)
    assert measured_flap_angle_deg(out, out["controls"][0]) == pytest.approx(8.0, abs=1e-6)


def test_geometry_gate_uses_the_faired_chord():
    surf, patches = _wing_patches()
    out = _elevon(patches, -10.0)
    ref = reference_quantities(surf)
    mac = mac_quarter_chord(surf)
    state = cruise_state(ref)
    text = avl_text(surf, ref, state["Mach"], mac["x_ref_m"])
    cfg = su2_rans_cfg("wing.su2", 3.0, state, ref["S_m2"] / 2.0, ref["Cref_m"], mac["x_ref_m"])
    report = verify_wing_rans_geometry(out, text, cfg)
    assert report["pode_correr"] is True
    flap = next(c for c in report["checks"] if c["id"] == "deflexao")
    assert flap["status"] == "passa"
    assert flap["angulo_deg"] == pytest.approx(-10.0, abs=1e-6)
    tip = next(s for s in report["sections"] if s["papel"] == "ponta")
    assert tip["incidencia_deg"] == pytest.approx(-10.0, abs=1e-6)
    bare = dict(out)
    bare.pop("faired_te")
    with pytest.raises(WingGeometryError):
        verify_wing_rans_geometry(bare, text, cfg)


def test_coarse_family_holds_the_sadraey_stop():
    """±25° on the coarse wrap. Sadraey 2012 Sec. 12.4.4 is the elevon stop."""
    from acdt.domains.aircraft.hifi.wing_bl import level_counts
    counts = level_counts("coarse")
    surf, patches = _wing_patches(counts["n_chord"], counts["n_span"], counts["n_tip"])
    for delta in (25.0, -25.0):
        out = _elevon(patches, delta)
        assert measured_flap_angle_deg(out, out["controls"][0]) == pytest.approx(delta, abs=1e-6)
        assert out["controls"][0]["x_hinge_mesh"] == pytest.approx(0.75, abs=0.04)
    ref = reference_quantities(surf)
    mac = mac_quarter_chord(surf)
    state = cruise_state(ref)
    text = avl_text(surf, ref, state["Mach"], mac["x_ref_m"])
    cfg = su2_rans_cfg("wing.su2", 3.0, state, ref["S_m2"] / 2.0, ref["Cref_m"], mac["x_ref_m"])
    report = verify_wing_rans_geometry(_elevon(patches, -25.0), text, cfg)
    assert report["pode_correr"] is True


def test_faired_gate_records_no_deflection():
    surf, patches = _wing_patches(n_chord=11, n_span=7)
    ref = reference_quantities(surf)
    mac = mac_quarter_chord(surf)
    state = cruise_state(ref)
    text = avl_text(surf, ref, state["Mach"], mac["x_ref_m"])
    cfg = su2_rans_cfg("wing.su2", 3.0, state, ref["S_m2"] / 2.0, ref["Cref_m"], mac["x_ref_m"])
    report = verify_wing_rans_geometry(patches, text, cfg)
    flap = next(c for c in report["checks"] if c["id"] == "deflexao")
    assert flap["status"] == "passa" and "sem deflexão" in flap["motivo"]


def test_tip_station_and_over_rotation_are_refused():
    _surf, patches = _wing_patches(n_span=5)
    with pytest.raises(ControlDeflectionError):
        apply_plain_flap(patches, name="tip", eta=(0.5, 1.0), x_hinge=0.7, delta_deg=5.0)
    with pytest.raises(ControlDeflectionError):
        apply_plain_flap(patches, name="too", eta=(0.2, 0.4), x_hinge=0.7, delta_deg=91.0)


def test_split_leaf_opens_upward_and_does_not_mesh():
    surf = Surface.panel(
        "wing", 1.0, 1.0, 2.0, sweep_le_deg=0.0, dihedral_deg=0.0,
        tc_root=0.15, tc_tip=0.15, twist_tip_deg=0.0, n_sections=2, mirror=True)
    patches = build_patches(surf, 15, 11, 5)
    spec = CONTROLS["split_aileron"]
    closed = split_leaf_pose(
        patches, name="split_aileron", eta=spec["eta"], x_hinge=1.0 - spec["cf_c"], delta_deg=0.0)
    opened = split_leaf_pose(
        patches, name="split_aileron", eta=spec["eta"], x_hinge=1.0 - spec["cf_c"], delta_deg=20.0)
    assert closed["te_rise_m"] == pytest.approx(0.0, abs=1e-9)
    assert opened["te_rise_m"] > 0.0
    assert opened["x_hinge"] == pytest.approx(0.60)
    assert opened["watertight_single_body"] is False
    assert opened["rans"] == "bloqueado"
    assert opened["asymmetric_rans"] == "bloqueado"
    assert "nao_avaliado" in opened["motivo"]
    assert np.allclose(patches["upper"], build_patches(surf, 15, 11, 5)["upper"])
    with pytest.raises(ControlDeflectionError):
        split_leaf_pose(patches, name="split_aileron", eta=spec["eta"], x_hinge=0.6, delta_deg=-5.0)


def test_constant_pressure_hinge_moment_on_a_flat_flap():
    n_c, n_s, n_t = 3, 3, 2
    xcs = np.array([0.0, 0.6, 1.0])
    etas = np.array([0.0, 0.5, 1.0])
    upper = np.zeros((n_c, n_s, 3))
    lower = np.zeros((n_c, n_s, 3))
    frames = []
    for j, y in enumerate(etas):
        le = np.array([0.0, float(y), 0.0])
        c = np.array([1.0, 0.0, 0.0])
        t = np.array([0.0, 0.0, 1.0])
        frames.append((le, c, t, 1.0, 0.12))
        for i, x in enumerate(xcs):
            upper[i, j] = le + float(x) * c
            lower[n_c - 1 - i, j] = le + float(x) * c - 0.01 * t
    te = np.zeros((n_t, n_s, 3))
    le_s = np.zeros((n_t, n_s, 3))
    for j in range(n_s):
        te[:, j] = np.linspace(upper[-1, j], lower[0, j], n_t)
        le_s[:, j] = np.linspace(upper[0, j], lower[-1, j], n_t)
    patches = {
        "upper": upper, "lower": lower, "te": te, "le": le_s, "tip": np.zeros((n_c, n_t, 3)),
        "etas": etas, "xcs": xcs, "frames": frames, "flip_i": False,
    }
    out = apply_plain_flap(patches, name="flap", eta=(0.0, 0.5), x_hinge=0.6, delta_deg=0.0)
    moment = pressure_hinge_moment(out, {"upper": 1000.0, "lower": 0.0}, name="flap",
                                   q_pa=500.0, sref_m2=2.0, cref_m=1.0)
    assert moment["H_Nm"] == pytest.approx(40.0, rel=1e-9)
    assert moment["Ch_ref"] == pytest.approx(40.0 / (500.0 * 2.0 * 1.0), rel=1e-9)
    missing = pressure_hinge_moment(out, {"upper": 1000.0, "lower": 0.0}, name="flap")
    assert missing["Ch_ref"] is None


def test_avl_card_is_symmetric_and_only_on_the_flap():
    surf, _meta = scaled_wing()
    ref = reference_quantities(surf)
    mac = mac_quarter_chord(surf)
    text = avl_text_plain_flap(
        surf, ref, 0.14, mac["x_ref_m"], name="elevon", eta=(0.20, 0.45), x_hinge=0.75)
    assert "CONTROL" in text
    assert "elevon 1.0 0.7500 0. 1. 0. 1.0" in text
    assert " -1.0" not in text
    # The root and the tip are outside η 0.20–0.45, so the file still has sections without a control.
    assert text.count("CONTROL") < text.count("\nSECTION\n") + text.count("\nSECTION")


def test_missing_gci_uses_the_caller_reason():
    plain = h1_factor_decision(0.51, 0.50, same_quantity=True, oscillatory=False, iterative_ok=False,
                               gci_defined=False, quantity="Ch")
    assert "GCI" in plain["reason"] and plain["decision"] == "nao_aplicar"
    told = h1_factor_decision(
        0.51, 0.50, same_quantity=True, oscillatory=False, iterative_ok=False, gci_defined=False,
        quantity="Ch", why="uma malha e um α, sem GCI; o factor não entra")
    assert told["reason"] == "uma malha e um α, sem GCI; o factor não entra"
    assert told["eligible"] is False and told["decision"] == "nao_aplicar"
    assert math.isfinite(told["ratio"])


def _flat_flap(delta_deg: float):
    n_c, n_s, n_t = 3, 3, 2
    xcs = np.array([0.0, 0.6, 1.0])
    etas = np.array([0.0, 0.5, 1.0])
    upper = np.zeros((n_c, n_s, 3))
    lower = np.zeros((n_c, n_s, 3))
    frames = []
    for j, y in enumerate(etas):
        le = np.array([0.0, float(y), 0.0])
        c = np.array([1.0, 0.0, 0.0])
        t = np.array([0.0, 0.0, 1.0])
        frames.append((le, c, t, 1.0, 0.12))
        for i, x in enumerate(xcs):
            upper[i, j] = le + float(x) * c
            lower[n_c - 1 - i, j] = le + float(x) * c - 0.01 * t
    te = np.zeros((n_t, n_s, 3))
    le_s = np.zeros((n_t, n_s, 3))
    for j in range(n_s):
        te[:, j] = np.linspace(upper[-1, j], lower[0, j], n_t)
        le_s[:, j] = np.linspace(upper[0, j], lower[-1, j], n_t)
    patches = {
        "upper": upper, "lower": lower, "te": te, "le": le_s, "tip": np.zeros((n_c, n_t, 3)),
        "etas": etas, "xcs": xcs, "frames": frames, "flip_i": False,
    }
    return apply_plain_flap(patches, name="flap", eta=(0.0, 0.5), x_hinge=0.6, delta_deg=delta_deg)


def _write_skin_volume(path, patches) -> None:
    def stack(patch, direction):
        wall = np.asarray(patch, float)
        return np.stack((wall, wall + 0.01 * np.asarray(direction, float)), axis=2)

    blocks = [
        {"xyz": stack(patches["upper"], (0.0, 0.0, 1.0)), "symmetry_at_j0": False},
        {"xyz": stack(patches["lower"], (0.0, 0.0, -1.0)), "symmetry_at_j0": False},
    ]
    write_su2_volume(blocks, path, reject_below=-1.0)


def _node_pressure(coords, patches) -> np.ndarray:
    pressure = np.full(len(coords), np.nan)
    upper = patches["upper"].reshape(-1, 3)
    lower = patches["lower"].reshape(-1, 3)
    for pid, point in enumerate(coords):
        du = float(np.min(np.linalg.norm(upper - point, axis=1)))
        dl = float(np.min(np.linalg.norm(lower - point, axis=1)))
        if du <= 1e-8 and du <= dl:
            pressure[pid] = 1000.0
        elif dl <= 1e-8:
            pressure[pid] = 0.0
    return pressure


def test_marker_hinge_matches_the_structured_integral(tmp_path):
    faired = _flat_flap(0.0)
    mesh = tmp_path / "wing.su2"
    _write_skin_volume(mesh, faired)
    coords, faces = read_su2_marker(mesh)
    moment = marker_hinge_moment(
        faired, faces, coords, _node_pressure(coords, faired), name="flap",
        q_pa=500.0, sref_m2=2.0, cref_m=1.0)
    assert moment["completo"] is True
    assert moment["H_Nm"] == pytest.approx(40.0, rel=1e-9)
    assert moment["Ch_ref"] == pytest.approx(40.0 / (500.0 * 2.0 * 1.0), rel=1e-9)
    turned = _flat_flap(10.0)
    turned_mesh = tmp_path / "turned.su2"
    _write_skin_volume(turned_mesh, turned)
    t_coords, t_faces = read_su2_marker(turned_mesh)
    t_pressure = _node_pressure(t_coords, turned)
    from_marker = marker_hinge_moment(
        turned, t_faces, t_coords, t_pressure, name="flap", q_pa=500.0, sref_m2=2.0, cref_m=1.0)
    from_patch = pressure_hinge_moment(
        turned, {"upper": 1000.0, "lower": 0.0}, name="flap", q_pa=500.0, sref_m2=2.0, cref_m=1.0)
    assert from_marker["completo"] is True
    assert from_marker["H_Nm"] == pytest.approx(from_patch["H_Nm"], rel=1e-9, abs=1e-9)
    pressure = _node_pressure(coords, faired)
    incomplete = None
    for k in range(len(faces)):
        trial = marker_hinge_moment(
            faired, faces[:k] + faces[k + 1:], coords, pressure, name="flap",
            q_pa=500.0, sref_m2=2.0, cref_m=1.0)
        if not trial["completo"]:
            incomplete = trial
            break
    assert incomplete is not None and incomplete["Ch_ref"] is None
    bad = pressure.copy()
    flap_node = next(
        pid for pid, point in enumerate(coords)
        if point[0] > 0.7 and abs(point[2]) < 1e-8 and 0.0 <= point[1] <= 0.5)
    bad[flap_node] = np.nan
    with pytest.raises(ControlDeflectionError, match="pressão em falta"):
        marker_hinge_moment(faired, faces, coords, bad, name="flap", q_pa=500.0, sref_m2=2.0, cref_m=1.0)


def test_surface_csv_pressure_uses_conservative_variables(tmp_path):
    # p = 1000 with ρ = 2 and m = (2, 0, 0): ½|m|²/ρ = 1, so E = 1 + 1000/0.4.
    assert pressure_from_conservative(2.0, (2.0, 0.0, 0.0), 2501.0) == pytest.approx(1000.0)
    with pytest.raises(ControlDeflectionError):
        pressure_from_conservative(0.0, (0.0, 0.0, 0.0), 10.0)
    csv_path = tmp_path / "surface.csv"
    csv_path.write_text(
        '"PointID","x","y","z","Density","Momentum_x","Momentum_y","Momentum_z","Energy","Nu_Tilde"\n'
        "0, 0, 0, 0, 2, 2, 0, 0, 2501, 0\n"
        "3, 1, 0, 0, 1, 0, 0, 0, 2500, 0\n",
        encoding="utf-8")
    pressure, mode = read_surface_csv_pressure(csv_path)
    assert mode == "conservative"
    assert pressure[0] == pytest.approx(1000.0)
    assert pressure[3] == pytest.approx(1000.0)
    assert np.isnan(pressure[1]) and np.isnan(pressure[2])
    direct = tmp_path / "pressure.csv"
    direct.write_text('"PointID","Pressure"\n0, 250\n', encoding="utf-8")
    got, mode = read_surface_csv_pressure(direct)
    assert mode == "Pressure" and got[0] == pytest.approx(250.0)
