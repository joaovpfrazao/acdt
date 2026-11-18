# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in control deflection on an H1 wing loft. No SU2 and no pyHyp.

A sealed plain flap (the elevon) rotates both skins about the chord-line
hinge. The hinge column stays put, so the surface stays C0, and the cell
just aft of it shears. Positive ``delta_deg`` lowers the trailing edge:
right-hand rotation about the outboard span ``t × c``.

An upper split leaf is not that flap. Opening it leaves a slot. The pyHyp
extrusion used here is one closed wing surface, and a solid wedge without a
slot is a different device. :func:`split_leaf_pose` records the rigid leaf and
marks the RANS case blocked. It does not deform the loft.

The faired trailing edge is kept on the patches (``faired_te``). The geometry
gate then checks wing incidence on that edge, and the flap angle separately.

:func:`marker_hinge_moment` integrates a hinge moment from an already written
SU2 wing marker and nodal pressures. It does not run SU2.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from .wing_bl import _check

# SU2 default when the case does not set GAMMA_VALUE. The H1 cfg does not.
GAMMA_AIR = 1.4
# pyHyp may move a wall node by about 1e-6 m (extrusion_check). The opened
# trailing edge is about 2e-3 of the chord, so 1e-4 m still separates the skins.
MARKER_MATCH_TOL_M = 1.0e-4


class ControlDeflectionError(ValueError):
    """The requested deflection is not a usable sealed surface."""


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-14:
        raise ControlDeflectionError("eixo de charneira nulo")
    return np.asarray(v, float) / n


def _rotate_about(point, origin, axis, deg: float) -> np.ndarray:
    """Right-hand rotation of one point about ``axis`` through ``origin``."""
    th = math.radians(deg)
    c, s = math.cos(th), math.sin(th)
    k = _unit(axis)
    v = np.asarray(point, float) - np.asarray(origin, float)
    return np.asarray(origin, float) + v * c + np.cross(k, v) * s + k * float(np.dot(k, v)) * (1.0 - c)


def _signed_angle_deg(v0, v1, axis) -> float:
    """Right-hand angle from ``v0`` to ``v1`` about ``axis``, degrees."""
    k = _unit(axis)
    a = np.asarray(v0, float)
    b = np.asarray(v1, float)
    return math.degrees(math.atan2(float(np.dot(k, np.cross(a, b))), float(np.dot(a, b))))


def _copy_patches(patches: dict) -> dict:
    out = dict(patches)
    for key, value in patches.items():
        if isinstance(value, np.ndarray):
            out[key] = value.copy()
        elif key == "controls" and isinstance(value, list):
            out[key] = [dict(item) for item in value]
        elif key == "edge_opening" and isinstance(value, dict):
            out[key] = dict(value)
    return out


def _x_upper(i: int, n_i: int, xcs: np.ndarray, flip: bool) -> float:
    return float(xcs[n_i - 1 - i] if flip else xcs[i])


def _x_lower(i: int, n_i: int, xcs: np.ndarray, flip: bool) -> float:
    return float(xcs[i] if flip else xcs[n_i - 1 - i])


def _hinge_upper_index(xcs: np.ndarray, x_hinge: float, flip: bool) -> int:
    """Last upper index at or ahead of the hinge. The column itself does not move."""
    n_i = len(xcs)
    found = None
    for i in range(n_i):
        if _x_upper(i, n_i, xcs, flip) <= x_hinge + 1e-12:
            found = i
    if found is None:
        raise ControlDeflectionError("não há coluna de corda em ou à frente da charneira")
    if not any(_x_upper(i, n_i, xcs, flip) > x_hinge + 1e-12 for i in range(n_i)):
        raise ControlDeflectionError("não há coluna atrás da charneira")
    return found


def _te_indices(n_i: int, flip: bool) -> tuple[int, int]:
    """Upper and lower indices of the trailing edge."""
    if flip:
        return 0, n_i - 1
    return n_i - 1, 0


def _stored_edges(upper: np.ndarray, lower: np.ndarray, flip: bool) -> tuple[np.ndarray, np.ndarray]:
    """Leading-edge and trailing-edge midpoints in stored index order."""
    i_u, i_l = _te_indices(upper.shape[0], flip)
    i_ul = 0 if not flip else upper.shape[0] - 1
    i_ll = upper.shape[0] - 1 if not flip else 0
    le = 0.5 * (upper[i_ul] + lower[i_ll])
    te = 0.5 * (upper[i_u] + lower[i_l])
    return le, te


def _span_axis(frame) -> np.ndarray:
    _le, c, t, _ch, _tc = frame
    return _unit(np.cross(np.asarray(t, float), np.asarray(c, float)))


def _stations_in(etas: np.ndarray, eta) -> list[int]:
    e0, e1 = float(eta[0]), float(eta[1])
    if not (0.0 <= e0 < e1 <= 1.0):
        raise ControlDeflectionError(f"η tem de cumprir 0 ≤ η_in < η_out ≤ 1 (veio {e0}, {e1})")
    return [j for j, e in enumerate(etas) if e0 - 1e-12 <= float(e) <= e1 + 1e-12]


def _cell_area(p0, p1, p2) -> np.ndarray:
    return 0.5 * np.cross(np.asarray(p1, float) - p0, np.asarray(p2, float) - p0)


def _assert_no_reversed_quad(patch, expect_at, name: str) -> None:
    """``expect_at(i, j)`` is the outward direction of the quad whose aft-root corner is (i, j)."""
    ni, nj, _ = patch.shape
    for j in range(nj - 1):
        for i in range(ni - 1):
            du = patch[i + 1, j] - patch[i, j]
            dv = patch[i, j + 1] - patch[i, j]
            area = np.cross(du, dv)
            expect = expect_at(i, j)
            if float(np.dot(area, expect)) <= 0.0:
                raise ControlDeflectionError(
                    f"a face {name} i={i} j={j} inverteu a normal; a deflexão não fica estanque")


def apply_plain_flap(patches: dict, *, name: str, eta, x_hinge: float, delta_deg: float) -> dict:
    """Sealed plain flap. Returns a new patch dict. The input is not changed.

    δ > 0 lowers the trailing edge. The hinge node is the last chord station at or
    ahead of ``x_hinge``; that node stays fixed. Both skins rotate about the
    chord-line point at that station, so the trailing-edge gap rotates as a
    rigid flap. The cell just aft of the hinge shears.

    PRESSUPOSTO: the spanwise end of the surface is the one grid cell between a
    deflected station and its undeflected neighbour, not a physical end rib.
    The tip cap is not rotated. A control that includes the tip station is refused.
    """
    for key in ("upper", "lower", "te", "frames", "etas", "xcs"):
        if key not in patches:
            raise ControlDeflectionError(f"a deflexão precisa de {key}")
    x_hinge = float(x_hinge)
    delta_deg = float(delta_deg)
    if not (0.0 < x_hinge < 1.0):
        raise ControlDeflectionError("a charneira tem de estar entre 0 e 1 da corda")
    if abs(delta_deg) > 90.0:
        raise ControlDeflectionError("deflexão acima de 90° não é um flap selado deste loft")
    out = _copy_patches(patches)
    names = [c["name"] for c in out.get("controls") or []]
    if name in names:
        raise ControlDeflectionError(f"o controlo {name} já foi deflectido")
    upper = out["upper"]
    lower = out["lower"]
    te = out["te"]
    xcs = np.asarray(out["xcs"], float)
    etas = np.asarray(out["etas"], float)
    flip = bool(out.get("flip_i", False))
    n_i, n_j, _ = upper.shape
    if lower.shape != upper.shape:
        raise ControlDeflectionError("upper e lower não têm a mesma forma")
    js = _stations_in(etas, eta)
    if not js:
        raise ControlDeflectionError("nenhuma estação de envergadura cai no intervalo de η")
    if "tip" in out and js[-1] == n_j - 1:
        raise ControlDeflectionError(
            "a estação da ponta está no intervalo; a tampa em semicírculo não roda com o flap")
    i_h = _hinge_upper_index(xcs, x_hinge, flip)
    x_mesh = _x_upper(i_h, n_i, xcs, flip)
    i_u_te, i_l_te = _te_indices(n_i, flip)
    # A 25° jump in one spanwise cell turned the lower skin inside out on the
    # coarse wrap. The two end stations take half the angle when there is an
    # interior station left at the full angle. PRESSUPOSTO, recorded below.
    edge_scale = 0.5 if len(js) >= 3 else 1.0

    def station_delta(j: int) -> float:
        if edge_scale < 1.0 and (j == js[0] or j == js[-1]):
            return delta_deg * edge_scale
        return delta_deg
    if "faired_upper_te" not in out:
        out["faired_upper_te"] = upper[i_u_te].copy()
        out["faired_lower_te"] = lower[i_l_te].copy()
        _le, te_mid = _stored_edges(upper, lower, flip)
        out["faired_te"] = te_mid.copy()
    for j in js:
        frame = out["frames"][j]
        le, c, t, ch, _tc = frame
        le = np.asarray(le, float)
        c = np.asarray(c, float)
        sp = _span_axis(frame)
        # One axis for both skins. Two skin pivots swing the thin trailing-edge
        # gap shut, because that gap is much smaller than the hinge thickness.
        hinge = le + x_mesh * float(ch) * c
        local = station_delta(j)
        for i in range(n_i):
            if _x_upper(i, n_i, xcs, flip) > x_mesh + 1e-12:
                upper[i, j] = _rotate_about(upper[i, j], hinge, sp, local)
            if _x_lower(i, n_i, xcs, flip) > x_mesh + 1e-12:
                lower[i, j] = _rotate_about(lower[i, j], hinge, sp, local)
        def _ahead(point, i):
            rel = np.asarray(point, float) - le
            xc = float(np.dot(rel, c) / float(ch))
            if xc < x_mesh - 1e-3:
                raise ControlDeflectionError(
                    f"a estação j={j} i={i} passou para a frente da charneira "
                    f"(x/c {xc:.4f} < {x_mesh:.4f}); o flap intersecta a asa")

        for i in range(n_i):
            if _x_upper(i, n_i, xcs, flip) > x_mesh + 1e-12:
                _ahead(upper[i, j], i)
            if _x_lower(i, n_i, xcs, flip) > x_mesh + 1e-12:
                _ahead(lower[i, j], i)
        u_te = upper[i_u_te, j]
        l_te = lower[i_l_te, j]
        n_te = te.shape[0]
        # Unflipped, index 0 of the strip is the upper skin. flip_i reverses that.
        first, second = (l_te, u_te) if flip else (u_te, l_te)
        for k in range(n_te):
            a = k / (n_te - 1)
            te[k, j] = (1.0 - a) * first + a * second
        opened = np.asarray(u_te, float) - np.asarray(l_te, float)
        t_rot = _rotate_about(le + np.asarray(t, float), le, sp, local) - le
        if float(np.dot(opened, t_rot)) <= 0.0:
            raise ControlDeflectionError("o bordo de fuga deflectido cruzou as duas peles")
    deltas = {j: station_delta(j) for j in js}
    _assert_skins_outward(out, deltas, x_mesh, flip)
    record = {
        "name": name,
        "kind": "plain",
        "eta": [float(eta[0]), float(eta[1])],
        "x_hinge": x_hinge,
        "x_hinge_mesh": x_mesh,
        "delta_deg": delta_deg,
        "sign": "positivo baixa o bordo de fuga (rotação direita em torno da envergadura para fora)",
        "j": [js[0], js[-1]],
        "i_hinge_upper": int(i_h),
        "sealed": True,
        "edge_scale": edge_scale,
        "pressuposto": (
            "PRESSUPOSTO: flap selado, as duas peles rodam juntas em torno do ponto "
            "da linha de corda na coluna da charneira. A célula imediatamente atrás "
            "cisalha. Com três ou mais estações, as dos extremos levam metade do "
            "ângulo: um salto de 25° numa só célula invertia a pele inferior na "
            "malha grossa. A tampa da ponta não entra."
        ),
    }
    out["controls"] = list(out.get("controls") or []) + [record]
    return out


def _turned(frame, vector, deg: float) -> np.ndarray:
    vector = np.asarray(vector, float)
    if abs(deg) < 1e-12:
        return vector
    return _rotate_about(np.asarray(frame[0], float) + vector, frame[0], _span_axis(frame), deg) - np.asarray(frame[0], float)


def _assert_skins_outward(patches, deltas: dict, x_mesh: float, flip: bool) -> None:
    upper = patches["upper"]
    lower = patches["lower"]
    te = patches["te"]
    xcs = np.asarray(patches["xcs"], float)
    n_i = upper.shape[0]
    frames = patches["frames"]

    def skin_expect(side_sign, i, j, x_of):
        # Lower i runs TE→LE, so the chord test cannot reuse the upper index.
        aft = (
            x_of(i) > x_mesh + 1e-12
            or x_of(min(i + 1, n_i - 1)) > x_mesh + 1e-12
        )
        frame = frames[j]
        t = np.asarray(frame[2], float)
        if not aft:
            direction = t
        else:
            direction = _turned(frame, t, deltas.get(j, 0.0)) + _turned(frames[j + 1], frames[j + 1][2], deltas.get(j + 1, 0.0))
        expect = side_sign * direction
        if flip:
            expect = -expect
        return expect

    _assert_no_reversed_quad(
        upper, lambda i, j: skin_expect(+1.0, i, j, lambda k: _x_upper(k, n_i, xcs, flip)), "upper")
    _assert_no_reversed_quad(
        lower, lambda i, j: skin_expect(-1.0, i, j, lambda k: _x_lower(k, n_i, xcs, flip)), "lower")

    def te_expect(i, j):
        frame = frames[j]
        c = np.asarray(frame[1], float)
        direction = _turned(frame, c, deltas.get(j, 0.0)) + _turned(frames[j + 1], frames[j + 1][1], deltas.get(j + 1, 0.0))
        if flip:
            direction = -direction
        return direction

    _assert_no_reversed_quad(te, te_expect, "te")


def measured_flap_angle_deg(patches: dict, spec: dict) -> float:
    """TE-down angle of the upper skin at the mid deflected station, degrees."""
    if "faired_upper_te" not in patches:
        raise ControlDeflectionError("falta o bordo de fuga alinhado; o ângulo não se mede")
    xcs = np.asarray(patches["xcs"], float)
    etas = np.asarray(patches["etas"], float)
    flip = bool(patches.get("flip_i", False))
    n_i = patches["upper"].shape[0]
    i_h = _hinge_upper_index(xcs, float(spec["x_hinge"]), flip)
    i_u_te, _i_l_te = _te_indices(n_i, flip)
    js = _stations_in(etas, spec["eta"])
    if not js:
        raise ControlDeflectionError("o intervalo de η não tem estações")
    j = js[len(js) // 2]
    frame = patches["frames"][j]
    le, c, _t, ch, _tc = frame
    sp = _span_axis(frame)
    x_mesh = _x_upper(i_h, n_i, xcs, flip)
    hinge = np.asarray(le, float) + x_mesh * float(ch) * np.asarray(c, float)
    v0 = np.asarray(patches["faired_upper_te"][j], float) - hinge
    v1 = np.asarray(patches["upper"][i_u_te, j], float) - hinge
    return _signed_angle_deg(v0, v1, sp)


def deflection_checks(patches: dict) -> list[dict]:
    """Geometry-gate rows for the declared deflections. A missing angle is not a pass."""
    controls = list(patches.get("controls") or [])
    if not controls:
        return [_check(
            "deflexao", "passa",
            "sem deflexão declarada; a corda da malha é a do controlo alinhado")]
    rows = []
    for spec in controls:
        name = spec.get("name", "?")
        if spec.get("kind") != "plain":
            rows.append(_check(
                "deflexao", "falha",
                f"{name}: esta malha fechada não representa uma split aberta; não avaliado não é aprovação"))
            continue
        try:
            angle = measured_flap_angle_deg(patches, spec)
        except ControlDeflectionError as exc:
            rows.append(_check("deflexao", "falha", f"{name}: {exc}"))
            continue
        asked = float(spec["delta_deg"])
        err = abs(angle - asked)
        if err <= 0.05:
            rows.append(_check(
                "deflexao", "passa",
                f"{name}: a pele superior rodou {angle:.3f}° (pedido {asked:.3f}°) em torno da charneira",
                angulo_deg=angle, pedido_deg=asked, x_hinge_mesh=spec.get("x_hinge_mesh")))
        else:
            rows.append(_check(
                "deflexao", "falha",
                f"{name}: ângulo medido {angle:.3f}° contra o pedido {asked:.3f}°",
                angulo_deg=angle, pedido_deg=asked))
    return rows


def split_leaf_pose(patches: dict, *, name: str, eta, x_hinge: float, delta_deg: float) -> dict:
    """Rigid pose of the upper split leaf. Does not modify ``patches``.

    δ > 0 opens the leaf upward (trailing edge toward +t). The hinge is the
    straight line between the upper-skin hinge points at the inboard and
    outboard stations. A twisted wing does not put every hinge point on that
    line; ``hinge_gap_m`` is the largest distance.

    The slot is not meshed. ``rans`` is ``bloqueado``.
    """
    for key in ("upper", "frames", "etas", "xcs"):
        if key not in patches:
            raise ControlDeflectionError(f"a split precisa de {key}")
    delta_deg = float(delta_deg)
    x_hinge = float(x_hinge)
    if delta_deg < -1e-9:
        raise ControlDeflectionError("a abertura da split é um ângulo positivo; um valor negativo não é zero")
    if delta_deg > 90.0:
        raise ControlDeflectionError("abertura acima de 90° está fora do mecanismo")
    upper = np.asarray(patches["upper"], float)
    xcs = np.asarray(patches["xcs"], float)
    etas = np.asarray(patches["etas"], float)
    flip = bool(patches.get("flip_i", False))
    n_i = upper.shape[0]
    js = _stations_in(etas, eta)
    if not js:
        raise ControlDeflectionError("nenhuma estação de envergadura cai no intervalo de η")
    i_h = _hinge_upper_index(xcs, x_hinge, flip)
    x_mesh = _x_upper(i_h, n_i, xcs, flip)
    i_u_te, _i_l = _te_indices(n_i, flip)
    p0 = upper[i_h, js[0]]
    p1 = upper[i_h, js[-1]]
    axis = p1 - p0
    axis_n = float(np.linalg.norm(axis))
    if axis_n < 1e-9:
        raise ControlDeflectionError("a charneira da split tem comprimento nulo")
    hat = axis / axis_n
    gap = 0.0
    for j in js:
        w = upper[i_h, j] - p0
        dist = float(np.linalg.norm(w - hat * float(np.dot(w, hat))))
        gap = max(gap, dist)
    # Opening upward is the opposite of the sealed-flap sign (TE down).
    open_deg = -delta_deg
    moved = []
    rises = []
    for j in js:
        frame = patches["frames"][j]
        le, _c, t, _ch, _tc = frame
        t = np.asarray(t, float)
        sp = _span_axis(frame)
        for i in range(n_i):
            if _x_upper(i, n_i, xcs, flip) + 1e-12 < x_mesh:
                continue
            src = upper[i, j]
            dst = src if abs(delta_deg) < 1e-12 else _rotate_about(src, upper[i_h, j], sp, open_deg)
            if i == i_u_te:
                rises.append(float(np.dot(dst - src, t)))
            moved.append(dst)
    return {
        "name": name,
        "kind": "split_upper",
        "leaf": "upper",
        "eta": [float(eta[0]), float(eta[1])],
        "x_hinge": x_hinge,
        "x_hinge_mesh": x_mesh,
        "delta_deg": delta_deg,
        "sign": "positivo abre a folha para cima, no sentido de +t",
        "j": [js[0], js[-1]],
        "n_points": len(moved),
        "hinge_gap_m": gap,
        "te_rise_m": float(np.median(rises)) if rises else None,
        "watertight_single_body": False,
        "rans": "bloqueado",
        "symmetric_rans": "bloqueado",
        "asymmetric_rans": "bloqueado",
        "motivo": (
            "A folha superior da split abre uma fenda. A extrusão pyHyp desta asa é uma "
            "superfície fechada. Rodar só essa pele deixa de ser estanque, e um sólido "
            "sem fenda é outro dispositivo: o ΔCD não é o da split. A abertura assimétrica "
            "também não cabe numa meia asa com MARKER_SYM. ΔCD, Cn e C_h ficam nao_avaliado. "
            "Não avaliado não é aprovação."
        ),
        "pressuposto": (
            "PRESSUPOSTO: a charneira é o segmento entre os pontos da pele superior nos "
            "extremos do intervalo de η. Numa asa com torção esses pontos intermédios não "
            "estão todos no segmento; hinge_gap_m é o maior afastamento."
        ),
    }


def pressure_hinge_moment(patches: dict, pressure, *, name: str, q_pa: float | None = None,
                          sref_m2: float | None = None, cref_m: float | None = None) -> dict:
    """Moment about the chord-line hinge from a static pressure on the sealed flap.

    ``pressure`` is a Pascal value on every flap face, or a dict ``{"upper", "lower"}``.
    The force on the body is −p times the outward area vector. The scalar is the
    component along the outboard span, positive when it drives the trailing edge down.
    ``Ch_ref`` = H / (q Sref Cref), the AVL HM definition, when q, Sref and Cref are given.
    A missing reference is None, not zero.
    """
    spec = next((c for c in patches.get("controls") or [] if c["name"] == name), None)
    if spec is None or spec.get("kind") != "plain":
        raise ControlDeflectionError(f"{name} não é um flap selado declarado na malha")
    if isinstance(pressure, dict):
        pu = pressure.get("upper")
        pl = pressure.get("lower")
        if pu is None or pl is None:
            raise ControlDeflectionError("faltam as pressões upper e lower; não se assume zero")
    else:
        pu = pl = float(pressure)
    upper = np.asarray(patches["upper"], float)
    lower = np.asarray(patches["lower"], float)
    xcs = np.asarray(patches["xcs"], float)
    etas = np.asarray(patches["etas"], float)
    flip = bool(patches.get("flip_i", False))
    n_i = upper.shape[0]
    i_h = _hinge_upper_index(xcs, float(spec["x_hinge"]), flip)
    x_mesh = _x_upper(i_h, n_i, xcs, flip)
    js = _stations_in(etas, spec["eta"])
    js_set = set(js)
    h_sum = 0.0
    area = 0.0

    def accumulate(patch, p_pa, x_of):
        nonlocal h_sum, area
        for j in range(patch.shape[1] - 1):
            if j not in js_set or (j + 1) not in js_set:
                continue
            frame = patches["frames"][j]
            le, c, _t, ch, _tc = frame
            sp = _span_axis(frame)
            hinge = np.asarray(le, float) + x_mesh * float(ch) * np.asarray(c, float)
            for i in range(n_i - 1):
                aft = x_of(i) > x_mesh + 1e-12 or x_of(i + 1) > x_mesh + 1e-12
                if not aft:
                    continue
                p00, p10 = patch[i, j], patch[i + 1, j]
                p01, p11 = patch[i, j + 1], patch[i + 1, j + 1]
                for tri in ((p00, p10, p11), (p00, p11, p01)):
                    avec = _cell_area(*tri)
                    a = float(np.linalg.norm(avec))
                    if a < 1e-16:
                        continue
                    centroid = (tri[0] + tri[1] + tri[2]) / 3.0
                    force = -float(p_pa) * avec
                    moment = np.cross(centroid - hinge, force)
                    h_sum += float(np.dot(moment, sp))
                    area += a

    accumulate(upper, float(pu), lambda i: _x_upper(i, n_i, xcs, flip))
    accumulate(lower, float(pl), lambda i: _x_lower(i, n_i, xcs, flip))
    out = {"name": name, "H_Nm": h_sum, "flap_area_m2": area, "sign": spec["sign"]}
    if q_pa is None or sref_m2 is None or cref_m is None:
        out["Ch_ref"] = None
        out["Ch_ref_note"] = "q, Sref ou Cref em falta; o coeficiente não se assume zero"
    elif q_pa == 0.0 or sref_m2 == 0.0 or cref_m == 0.0:
        out["Ch_ref"] = None
        out["Ch_ref_note"] = "referência nula; o coeficiente não se calcula"
    else:
        out["Ch_ref"] = h_sum / (float(q_pa) * float(sref_m2) * float(cref_m))
        out["Ch_ref_note"] = "H / (q Sref Cref), a mesma definição do HM do AVL"
    return out


def pressure_from_conservative(density, momentum, energy, gamma: float = GAMMA_AIR) -> float:
    """Static pressure from SU2 conservative variables. A bad density is an error, not zero.

    p = (γ − 1) (E − ½ |m|² / ρ). E and m are the conservative energy and momentum.
    """
    rho = float(density)
    m = np.asarray(momentum, float).reshape(3)
    total = float(energy)
    if (not math.isfinite(rho) or rho <= 0.0 or not math.isfinite(total)
            or not bool(np.all(np.isfinite(m)))):
        raise ControlDeflectionError("variável conservativa inválida; a pressão não se assume")
    kinetic = 0.5 * float(np.dot(m, m)) / rho
    return (float(gamma) - 1.0) * (total - kinetic)


def read_surface_csv_pressure(path, gamma: float = GAMMA_AIR) -> tuple[np.ndarray, str]:
    """Nodal pressure indexed by PointID. Missing ids stay NaN. They are not zero.

    A ``Pressure`` column is used when the file has one. Otherwise the pressure
    comes from Density, Momentum and Energy.
    """
    path = Path(path)
    with path.open(encoding="utf-8", newline="") as fh:
        rows = csv.reader(fh)
        try:
            header = [cell.strip().strip('"') for cell in next(rows)]
        except StopIteration as exc:
            raise ControlDeflectionError("surface.csv vazio") from exc
        index = {name: i for i, name in enumerate(header)}
        if "PointID" not in index:
            raise ControlDeflectionError("surface.csv sem PointID")
        if "Pressure" in index:
            mode = "Pressure"
        else:
            needed = ("Density", "Momentum_x", "Momentum_y", "Momentum_z", "Energy")
            missing = [name for name in needed if name not in index]
            if missing:
                raise ControlDeflectionError(
                    "surface.csv sem Pressure e sem " + ", ".join(missing))
            mode = "conservative"
        samples = []
        for row in rows:
            if not row or len(row) < len(header):
                continue
            pid = int(float(row[index["PointID"]]))
            if mode == "Pressure":
                pressure = float(row[index["Pressure"]])
                if not math.isfinite(pressure):
                    raise ControlDeflectionError(f"pressão não finita no ponto {pid}")
            else:
                pressure = pressure_from_conservative(
                    row[index["Density"]],
                    [row[index[name]] for name in ("Momentum_x", "Momentum_y", "Momentum_z")],
                    row[index["Energy"]], gamma=gamma)
            samples.append((pid, pressure))
    if not samples:
        raise ControlDeflectionError("surface.csv sem pontos")
    out = np.full(max(pid for pid, _pressure in samples) + 1, np.nan)
    for pid, pressure in samples:
        out[pid] = pressure
    return out, mode


def read_su2_marker(path, marker: str = "wing") -> tuple[np.ndarray, list[tuple[int, ...]]]:
    """Point coordinates and one marker's faces from an SU2 mesh. Does not run SU2.

    The point index is the trailing integer on each ``NPOIN`` line, the same
    PointID the surface CSV uses. Triangles (type 5) and quads (type 9) are kept.
    """
    lines = Path(path).read_text(encoding="ascii", errors="replace").splitlines()
    coords = None
    faces: list[tuple[int, ...]] = []
    found = False
    i = 0
    while i < len(lines):
        text = lines[i].strip()
        if text.startswith("NPOIN"):
            n_poin = int(text.split("=", 1)[1])
            coords = np.zeros((n_poin, 3))
            for _k in range(n_poin):
                i += 1
                parts = lines[i].split()
                pid = int(parts[-1])
                coords[pid, :] = [float(part) for part in parts[:3]]
        elif text.startswith("MARKER_TAG"):
            tag = text.split("=", 1)[1].strip()
            i += 1
            n_elem = int(lines[i].split("=", 1)[1])
            if tag == marker:
                found = True
                for _k in range(n_elem):
                    i += 1
                    parts = lines[i].split()
                    kind = int(parts[0])
                    n_vert = {5: 3, 9: 4}.get(kind)
                    if n_vert is None:
                        raise ControlDeflectionError(
                            f"elemento de marcador {kind} não é triângulo nem quad")
                    faces.append(tuple(int(part) for part in parts[1:1 + n_vert]))
            else:
                i += n_elem
        i += 1
    if coords is None or not found:
        raise ControlDeflectionError(f"malha sem pontos ou sem marcador {marker}")
    return coords, faces


def _skin_table(upper: np.ndarray, lower: np.ndarray, tol: float) -> dict:
    table: dict = {}
    for side, patch in (("upper", upper), ("lower", lower)):
        ni, nj, _ = patch.shape
        for i in range(ni):
            for j in range(nj):
                key = tuple(int(round(float(v) / tol)) for v in patch[i, j])
                table.setdefault(key, []).append((side, i, j))
    return table


def _lookup_skin(point, upper, lower, table, tol: float):
    """Nearest upper/lower node inside ``tol``. Two different nodes inside the tol is ambiguous."""
    base = tuple(int(round(float(v) / tol)) for v in point)
    hits = []
    for dz in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                hits.extend(table.get((base[0] + dx, base[1] + dy, base[2] + dz), ()))
    ranked = []
    limit = tol * tol
    for side, i, j in hits:
        src = upper[i, j] if side == "upper" else lower[i, j]
        dist = float(np.sum((src - point) ** 2))
        if dist <= limit:
            ranked.append((dist, side, i, j))
    if not ranked:
        return None
    ranked.sort()
    _dist, side, i, j = ranked[0]
    for _other, o_side, o_i, o_j in ranked[1:]:
        if (o_side, o_i, o_j) != (side, i, j):
            return None
    return side, i, j


def _loop_area(coords: np.ndarray, loop: tuple[int, ...]) -> np.ndarray:
    pts = [coords[i] for i in loop]
    acc = np.zeros(3)
    origin = pts[0]
    for a, b in zip(pts[1:-1], pts[2:]):
        acc += _cell_area(origin, a, b)
    return acc


def marker_hinge_moment(patches: dict, faces, coords, node_pressure, *, name: str,
                        q_pa: float | None = None, sref_m2: float | None = None,
                        cref_m: float | None = None, match_tol_m: float = MARKER_MATCH_TOL_M) -> dict:
    """Hinge moment from SU2 wing-marker faces of a sealed flap.

    A face counts when its nodes match one upper or lower quad that
    :func:`pressure_hinge_moment` would integrate. The face pressure is the
    mean of those nodes. A missing nodal pressure is an error, not zero.

    ``write_su2_volume`` winds the wall as the −k face, opposite the outward
    skin normal, so the force on the body is +p times that area vector. The
    hinge line and the span axis are the ones of :func:`pressure_hinge_moment`.
    ``Ch_ref`` is published only when every expected flap quad was found.
    """
    spec = next((c for c in patches.get("controls") or [] if c["name"] == name), None)
    if spec is None or spec.get("kind") != "plain":
        raise ControlDeflectionError(f"{name} não é um flap selado declarado na malha")
    upper = np.asarray(patches["upper"], float)
    lower = np.asarray(patches["lower"], float)
    xcs = np.asarray(patches["xcs"], float)
    etas = np.asarray(patches["etas"], float)
    flip = bool(patches.get("flip_i", False))
    n_i = upper.shape[0]
    i_h = _hinge_upper_index(xcs, float(spec["x_hinge"]), flip)
    x_mesh = _x_upper(i_h, n_i, xcs, flip)
    js = set(_stations_in(etas, spec["eta"]))
    pressure = np.asarray(node_pressure, float)
    expected = set()

    def consider(side: str, x_of) -> None:
        for j in range(upper.shape[1] - 1):
            if j not in js or (j + 1) not in js:
                continue
            for i in range(n_i - 1):
                aft = x_of(i) > x_mesh + 1e-12 or x_of(i + 1) > x_mesh + 1e-12
                if aft:
                    expected.add((side, i, j))

    consider("upper", lambda i: _x_upper(i, n_i, xcs, flip))
    consider("lower", lambda i: _x_lower(i, n_i, xcs, flip))
    table = _skin_table(upper, lower, float(match_tol_m))
    coords = np.asarray(coords, float)
    h_sum = 0.0
    area = 0.0
    seen = set()

    def corner_of(loop):
        found = []
        for pid in loop:
            hit = _lookup_skin(coords[pid], upper, lower, table, float(match_tol_m))
            if hit is None:
                return None
            found.append(hit)
        if any(item[0] != found[0][0] for item in found):
            return None
        iis = sorted({item[1] for item in found})
        jjs = sorted({item[2] for item in found})
        if (len(found) == 4 and len(iis) == 2 and len(jjs) == 2
                and iis[1] == iis[0] + 1 and jjs[1] == jjs[0] + 1):
            return found[0][0], iis[0], jjs[0]
        return None

    for loop in faces:
        corner = corner_of(loop)
        if corner is None or corner not in expected:
            continue
        if corner in seen:
            raise ControlDeflectionError(f"a face do flap {corner} está repetida no marcador")
        seen.add(corner)
        samples = []
        for pid in loop:
            if pid < 0 or pid >= pressure.shape[0] or not math.isfinite(float(pressure[pid])):
                raise ControlDeflectionError(
                    f"pressão em falta no nó {pid}; não se assume zero")
            samples.append(float(pressure[pid]))
        p_face = float(np.mean(samples))
        avec = _loop_area(coords, loop)
        a = float(np.linalg.norm(avec))
        if a < 1e-16:
            continue
        _side, _i0, j0 = corner
        frame = patches["frames"][j0]
        le, c, _t, ch, _tc = frame
        hinge = np.asarray(le, float) + x_mesh * float(ch) * np.asarray(c, float)
        centroid = np.mean([coords[pid] for pid in loop], axis=0)
        # Marker normal points into the solid. Force on the body is +p times it.
        force = p_face * avec
        moment = np.cross(centroid - hinge, force)
        h_sum += float(np.dot(moment, _span_axis(frame)))
        area += a
    complete = seen == expected
    out = {
        "name": name,
        "H_Nm": h_sum,
        "flap_area_m2": area,
        "completo": complete,
        "n_expected": len(expected),
        "n_matched": len(seen),
        "sign": spec["sign"],
        "match_tol_m": float(match_tol_m),
        "pressao_da_face": "média dos nós",
        "forca": (
            "p vezes a área do marcador wing. write_su2_volume escreve a parede "
            "como a face −k, oposta à normal exterior da pele."
        ),
    }
    if not complete:
        out["Ch_ref"] = None
        out["Ch_ref_note"] = (
            f"integral incompleta ({len(seen)} de {len(expected)} quads); "
            "o coeficiente não se publica"
        )
    elif q_pa is None or sref_m2 is None or cref_m is None:
        out["Ch_ref"] = None
        out["Ch_ref_note"] = "q, Sref ou Cref em falta; o coeficiente não se assume zero"
    elif q_pa == 0.0 or sref_m2 == 0.0 or cref_m == 0.0:
        out["Ch_ref"] = None
        out["Ch_ref_note"] = "referência nula; o coeficiente não se calcula"
    else:
        out["Ch_ref"] = h_sum / (float(q_pa) * float(sref_m2) * float(cref_m))
        out["Ch_ref_note"] = "H / (q Sref Cref), a mesma definição do HM do AVL"
    return out


def avl_text_plain_flap(surf, ref: dict, mach: float, x_ref: float, *, name: str, eta,
                        x_hinge: float, nchord: int = 12, nspan: int = 40) -> str:
    """Wing AVL file with sections at the flap ends and one symmetric CONTROL.

    SgnDup is +1 (the same deflection on both sides). The hinge vector is +y, as in
    the elevon card of the tailless assembly. Gain is 1. This does not run AVL.
    """
    from ..assembly.assembly import Assembly
    from ..assembly.components import Surface

    e0, e1 = float(eta[0]), float(eta[1])
    secs = [dict(s) for s in surf.sections]
    ys = np.array([float(s["le"][1]) for s in secs])
    ymax = float(np.max(np.abs(ys)))
    if ymax <= 0.0:
        raise ControlDeflectionError("a asa não tem envergadura para colocar o flap")
    for eta_cut in (e0, e1):
        yy = eta_cut * ymax
        if np.any(np.abs(ys - yy) <= 1e-6 * ymax):
            continue
        order = np.argsort(ys)
        ys_s = ys[order]
        secs_s = [secs[int(k)] for k in order]
        secs.append({
            "le": [float(np.interp(yy, ys_s, [s["le"][k] for s in secs_s])) for k in range(3)],
            "chord": float(np.interp(yy, ys_s, [s["chord"] for s in secs_s])),
            "twist_deg": float(np.interp(yy, ys_s, [s["twist_deg"] for s in secs_s])),
            "tc": float(np.interp(yy, ys_s, [s["tc"] for s in secs_s])),
        })
        ys = np.array([float(s["le"][1]) for s in secs])
    secs.sort(key=lambda s: float(s["le"][1]))
    winged = Surface(
        name=surf.name, sections=secs, airfoil=surf.airfoil,
        naca4_mean_line=bool(getattr(surf, "naca4_mean_line", False)),
        mirror=surf.mirror, origin=tuple(surf.origin), role=surf.role,
        orientation=dict(surf.orientation or {}))
    text = Assembly([winged], expand_mirror=False).avl_text(
        "h1_tailless_wing", mach=mach,
        ref={"Sref": ref["S_m2"], "Cref": ref["Cref_m"], "Bref": ref["Bref_m"]},
        cg=(x_ref, 0.0, 0.0), nchord=nchord, nspan=nspan)
    # Tag the sections whose local η falls inside the flap. η = y / y_max of the written sections.
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        if lines[i] == "SECTION" and i + 2 < len(lines):
            coords = lines[i + 2].split()
            y = float(coords[1])
            eta_y = y / ymax
            out.append(lines[i + 1])
            out.append(lines[i + 2])
            i += 3
            if i < len(lines) and lines[i] == "NACA":
                out.append(lines[i])
                out.append(lines[i + 1])
                i += 2
                if e0 - 1e-6 <= eta_y <= e1 + 1e-6:
                    out.append("CONTROL")
                    out.append(f"{name} 1.0 {x_hinge:.4f} 0. 1. 0. 1.0")
            continue
        i += 1
    return "\n".join(out) + "\n"
