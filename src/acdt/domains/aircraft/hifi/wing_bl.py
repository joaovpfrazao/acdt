"""H1: prismatic RANS mesh of the tailless flying wing, and the 3-D grid-convergence decision.

The drawn OML is the starboard wing panel in ``examples/integration/flying_wing_pusher_tailless.json``,
scaled about the origin so the two-sided planform area is the documented post-gear 3.186 m². Sections stay
the symmetric NACA 4-digit thickness of :func:`acdt.domains.aircraft.assembly.components.naca_yt`
(Abbott & von Doenhoff 1959, Eq. 6.2, closed trailing edge) at the declared drawing t/c, 0.15 at the
root and 0.12 at the tip. The thickness digit of the name NACA 4415 is not used when it disagrees.
That name's camber line is not built unless the surface calls
:meth:`~acdt.domains.aircraft.assembly.components.Surface.with_naca4_mean_line` (Eq. 6.4–6.6).
The example and :func:`scaled_wing` stay on the symmetric path. Station frames are
:meth:`Surface._frames`: the span used for the section plane has its x component removed, then the chord
is rotated about that span by the section twist (nose up positive, the same sign as AVL Ainc). The
centerbody, gear and propeller are not in this mesh.

pyHyp (Apache-2.0) extrudes the surface in the existing udocker container. acdt does not import it.
Smoothing coefficients are the ones shipped in pyHyp 2.6.3 ``examples/m6/runM6.py``; N, s0 and marchDist
are this study's. The volume Plot3D file is converted here to an SU2 mesh (hexes, and prisms if an edge
ever collapses). SU2 (LGPL-2.1) stays a separate process. The sharp NACA LE and TE are
opened by :data:`EDGE_OPEN_HALF_CHORD` and closed with a strip: pyHyp 2.6.3 segfaults
in ``setup`` after "Topology complete" when a tip-cap quad repeats that node.

3-D grid spacing in the GCI is h = (1/N)^(1/3). :func:`acdt.domains.aircraft.hifi.cfd.gci` is the Celik
et al. 2008 procedure; its docstring states the 2-D definition h = (1/N)^(1/2). One cruise angle does
not calibrate a polar: an in-band ratio is recorded as eligible and is not applied.

:func:`verify_wing_rans_geometry` compares the loft mesh with the AVL file and the SU2 case
before any wing RANS run. A failed check raises :class:`WingGeometryError`.
:func:`acdt.domains.aircraft.hifi.cfd.launch_wing_rans` calls that check and does not call
the run callable when it fails. A missing CMy is ``nao_avaliado``: that is not a pass, and it
does not by itself block the first run.
"""
from __future__ import annotations

import math
import re
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from ....core.atmosphere import G0, isa
from ..assembly.assembly import Assembly
from ..assembly.components import (
    Surface, naca4_mean_line, naca_yt, naca4_mean_line_record, section_thickness_record,
)
from ..aero.avl import _grab, avl_available
from .cfd import first_cell, gci
from . import tools

# Documented post-gear aircraft (CAPABILITIES §32d-bis). The drawing flight block is the unscaled sketch.
DOCUMENTED_S_M2 = 3.186
DOCUMENTED_W0_KG = 150.4
CRUISE_V_MS = 45.0
CRUISE_ALT_M = 3000.0
FARFIELD_CHORDS = 100.0
# H1 acceptance band. This is not calibration.RATIO_BAND.
H1_RATIO_BAND = (0.7, 1.5)
SU2_MERGE_TOL_M = 1e-7
# Inherited from full_aircraft_rans_case. Not measured on this CPU.
US_PER_CELL_ITER = 4.0e-6
KB_PER_CELL = 1.8e-6  # GB at 1.8 kB/cell
OMP_THREADS = 6
PYHYP_SMOOTHING_SOURCE = "pyHyp 2.6.3 examples/m6/runM6.py"
# Half-thickness / local chord of the flat that replaces a sharp LE or TE.
# Adjacent tip nodes must stay above pyHyp nodeTol (1e-8 m) and the SU2 merge (1e-7 m).
# 5.0e-4 left every tip trailing-edge cell negative from the second layer.
# 2.0e-3 made the first layer positive and left the second negative
# (coarse surface, N=20, s0 of the coarse mesh, growth 1.339, cornerAngle 150).
# A quarter-circle fillet on that flat made the march worse (layer 14 volume -6.9e-6).
# The flat stays on the strips. The tip itself is a semicircle. It is a mesh device, not the analytic OML.
EDGE_OPEN_HALF_CHORD = 2.0e-3
# The N=20 probe with this angle, a 9-point semicircle and growth 1.339 had a positive
# minimum volume on every layer. pyHyp's 60° averages only turns above 120°.
TIP_CORNER_ANGLE = 150.0
# Coarse 72.6 m march, pyHyp 2.6.3, this surface. epsE 1 inverts at layer 19;
# 8 and 16 fold the wall. cMax 5 folded one lower-tip leading-edge cell at layer 25;
# cMax 1.0 inverted only layer 49. These two kept every minimum volume positive.
PYHYP_EPS_E = 4.0
PYHYP_C_MAX = 0.5
PATCH_NAMES = ("upper", "lower", "tip", "le", "te")
SYMMETRY_PATCHES = ("upper", "lower", "le", "te")

# Point counts. Cells along an axis are count − 1. n_chord = (n_wrap − 1) // 2 + 1.
MESH_FAMILY = {
    "coarse": {"n_wrap": 97, "n_span": 33, "n_layers": 49, "yplus": 2.0, "max_time_min": 30.0},
    "medium": {"n_wrap": 137, "n_span": 47, "n_layers": 69, "yplus": math.sqrt(2.0), "max_time_min": 90.0},
    "fine": {"n_wrap": 194, "n_span": 66, "n_layers": 98, "yplus": 1.0, "max_time_min": 240.0},
}
# Direction probe only. Not a GCI level. Short march, stop the real coarse extrusion above 30 min or 4 GB.
PROBE = {"n_wrap": 17, "n_span": 9, "n_layers": 9, "march_m": 2.0}

# VTK hex local faces, outward when (i, j, k) is a right-handed wall-to-far grid.
_FACES = (
    ("km", (0, 3, 2, 1)),
    ("kp", (4, 5, 6, 7)),
    ("jm", (0, 1, 5, 4)),
    ("jp", (3, 7, 6, 2)),
    ("im", (0, 4, 7, 3)),
    ("ip", (1, 2, 6, 5)),
)

DRAWING = {
    "origin": (0.25, 0.0, 0.0),
    "root_chord": 0.9,
    "tip_chord": 0.36,
    "span": 1.9,
    "sweep_le_deg": 28.0,
    "dihedral_deg": 2.0,
    "tc_root": 0.15,
    "tc_tip": 0.12,
    "airfoil": "NACA 4415",
    "twist_tip_deg": -10.0,
}
# faired controls, recorded so a later hinge-moment mesh can reuse this topology
CONTROLS = {
    "elevon": {"eta": (0.20, 0.45), "cf_c": 0.25, "source": "examples/heavy/uav150_flying_wing_tailless.yaml"},
    "split_aileron": {"eta": (0.45, 0.98), "cf_c": 0.40, "source": "examples/heavy/uav150_flying_wing_tailless.yaml"},
}
SCOPE = (
    "Meia asa de estibordo, controlos alinhados (sem deflexão), sem fuselagem, trem ou hélice. "
    "A espessura é a NACA simétrica do t/c declarado (naca_yt). "
    "A curvatura da designação NACA 4415 não entra no loft nem no AVL."
)


def scope_text(surf: Surface) -> str:
    """Scope sentence for a record. The default loft does not build the mean line."""
    if getattr(surf, "naca4_mean_line", False):
        return (
            "Meia asa de estibordo, controlos alinhados (sem deflexão), sem fuselagem, trem ou hélice. "
            "A linha média NACA de 4 dígitos da designação entra no loft e no cartão AVL "
            "(Abbott & von Doenhoff 1959, Eq. 6.4–6.6). "
            "A espessura é naca_yt do t/c declarado, não o dígito de espessura da designação "
            "quando os dois diferem."
        )
    return SCOPE


def drawing_panel(**kw) -> Surface:
    """Unscaled starboard panel. ``planform_area`` is one side, in the panel plane."""
    d = DRAWING
    return Surface.panel(
        "wing", d["root_chord"], d["tip_chord"], d["span"],
        sweep_le_deg=d["sweep_le_deg"], dihedral_deg=d["dihedral_deg"],
        tc_root=d["tc_root"], tc_tip=d["tc_tip"], twist_tip_deg=d["twist_tip_deg"],
        n_sections=kw.pop("n_sections", 2), origin=d["origin"], mirror=True, role="wing",
        airfoil=d["airfoil"], **kw)


def scale_to_documented_area(s_documented: float = DOCUMENTED_S_M2) -> tuple[float, float]:
    """Uniform scale about the origin. Returns (k, two-sided drawing area)."""
    s_draw = 2.0 * drawing_panel().planform_area()
    if s_draw <= 0.0:
        raise ValueError("drawing planform area is not positive")
    return math.sqrt(s_documented / s_draw), s_draw


def scaled_wing() -> tuple[Surface, dict]:
    """Starboard panel scaled so both sides have area ``DOCUMENTED_S_M2``."""
    k, s_draw = scale_to_documented_area()
    d = DRAWING
    origin = tuple(k * v for v in d["origin"])
    surf = Surface.panel(
        "wing", d["root_chord"] * k, d["tip_chord"] * k, d["span"] * k,
        sweep_le_deg=d["sweep_le_deg"], dihedral_deg=d["dihedral_deg"],
        tc_root=d["tc_root"], tc_tip=d["tc_tip"], twist_tip_deg=d["twist_tip_deg"],
        n_sections=2, origin=origin, mirror=True, role="wing", airfoil=d["airfoil"])
    return surf, {"k": k, "S_draw_m2": s_draw, "S_m2": DOCUMENTED_S_M2, "origin_m": origin}


def station_frames(surf: Surface, etas) -> list[tuple]:
    """Local frames at straight-panel fractions. Uses :meth:`Surface._frames` on the interpolated sections.

    Root and tip are ``surf.sections[0]`` and ``surf.sections[-1]``. A straight tapered panel is linear in
    that fraction, which is how :meth:`Surface.panel` places intermediate sections.
    """
    root, tip = surf.sections[0], surf.sections[-1]
    le0 = np.asarray(root["le"], float)
    le1 = np.asarray(tip["le"], float)
    secs = []
    for e in etas:
        e = float(e)
        secs.append({
            "le": (le0 + (le1 - le0) * e).tolist(),
            "chord": float(root["chord"] + (tip["chord"] - root["chord"]) * e),
            "twist_deg": float(root["twist_deg"] + (tip["twist_deg"] - root["twist_deg"]) * e),
            "tc": float(root["tc"] + (tip["tc"] - root["tc"]) * e),
        })
    return Surface(name=surf.name, sections=secs)._frames()


def _global_frame(surf: Surface, frame) -> tuple:
    le, c, t, ch, tc = frame
    sign = surf._sign()
    rot = surf.R
    le_g = surf.to_global([le])[0]
    c_g = np.asarray(c, float) @ rot.T * sign
    t_g = np.asarray(t, float) @ rot.T * sign
    return le_g, c_g / np.linalg.norm(c_g), t_g / np.linalg.norm(t_g), float(ch), float(tc)


def level_counts(level: str) -> dict:
    spec = PROBE if level == "probe" else MESH_FAMILY[level]
    n_chord = (int(spec["n_wrap"]) - 1) // 2 + 1
    # 180° tip semicircle. 9 points is 22.5° per face, under the 30° that cornerAngle 150 averages.
    n_tip = max(9, n_chord // 8)
    return {"n_chord": n_chord, "n_span": int(spec["n_span"]), "n_tip": n_tip,
            "n_layers": int(spec["n_layers"]), "n_wrap": int(spec["n_wrap"])}


def cell_count(n_chord: int, n_span: int, n_tip: int, n_layers: int) -> int:
    """Upper, lower, tip cap, and the LE and TE strips. A collapsed edge would still be one cell."""
    dk = n_layers - 1
    upper = (n_chord - 1) * (n_span - 1) * dk
    tip = (n_chord - 1) * (n_tip - 1) * dk
    strip = (n_tip - 1) * (n_span - 1) * dk
    return 2 * upper + tip + 2 * strip


def _cosine(n: int) -> np.ndarray:
    return 0.5 * (1.0 - np.cos(np.linspace(0.0, math.pi, n)))


def _span_outward(c: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Panel span. ``t = c × sp`` and ``c · sp = 0``, so ``sp = t × c``."""
    sp = np.cross(t, c)
    n = np.linalg.norm(sp)
    if n < 1e-14:
        raise ValueError("section frame has no span direction")
    return sp / n


def _opened_yt(xcs: np.ndarray, tc: float, ch: float) -> tuple[np.ndarray, float]:
    """Analytic half-thickness, with a floor so the LE and TE nodes do not coincide."""
    yt = np.asarray(naca_yt(xcs, tc), float) * ch
    half = EDGE_OPEN_HALF_CHORD * ch
    return np.maximum(yt, half), half


def _surface_mean_line(surf: Surface) -> tuple[float, float]:
    """(m, p) in chord fractions. (0, 0) when the surface has not opted in."""
    if not getattr(surf, "naca4_mean_line", False):
        return 0.0, 0.0
    return surf._naca4_mp()


def _camber_offsets(xcs: np.ndarray, tc: float, ch: float, m: float, p: float):
    """Opened upper/lower offsets in the (chord, thickness) frame, metres, LE → TE.

    Eq. 6.6 with the thickness floor of :data:`EDGE_OPEN_HALF_CHORD` applied before the
    rotation, so the leading and trailing edges stay apart along the mean-line normal.
    """
    x = np.asarray(xcs, float)
    yt = np.asarray(naca_yt(x, tc), float) * ch
    half = EDGE_OPEN_HALF_CHORD * ch
    yt_o = np.maximum(yt, half)
    yc, dy = naca4_mean_line(x, m, p)
    th = np.arctan(dy)
    st = np.sin(th)
    ct = np.cos(th)
    yc_m = np.asarray(yc, float) * ch
    info = {
        "half": half,
        "max_move": float(np.max(yt_o - yt)),
        "le_nc": float(-st[0]),
        "le_nt": float(ct[0]),
        "te_nc": float(-st[-1]),
        "te_nt": float(ct[-1]),
        "le_yc": float(yc_m[0]),
        "te_yc": float(yc_m[-1]),
        "n_c": -st,
        "n_t": ct,
        "yc_m": yc_m,
        "yt_o": yt_o,
    }
    return x * ch - yt_o * st, yc_m + yt_o * ct, x * ch + yt_o * st, yc_m - yt_o * ct, info


def build_patches(surf: Surface, n_chord: int, n_span: int, n_tip: int, flip_i: bool = False) -> dict:
    """Upper, lower (i reversed), tip cap, and LE/TE strips. Normals point out of the solid.

    ``flip_i`` reverses every patch's i index. That is the one retry if pyHyp marches into the wing.
    The strips close the flat of :data:`EDGE_OPEN_HALF_CHORD`. Their i direction is the thickness.
    """
    if min(n_chord, n_span, n_tip) < 2:
        raise ValueError("a patch needs at least two points on each side")
    etas = _cosine(n_span)
    xcs = _cosine(n_chord)
    frames = [_global_frame(surf, fr) for fr in station_frames(surf, etas)]
    upper = np.zeros((n_chord, n_span, 3))
    lower = np.zeros((n_chord, n_span, 3))
    le_strip = np.zeros((n_tip, n_span, 3))
    te_strip = np.zeros((n_tip, n_span, 3))
    ss = np.linspace(-1.0, 1.0, n_tip)
    te_ss = ss[::-1]
    max_move = 0.0
    m_camber, p_camber = _surface_mean_line(surf)
    if m_camber == 0.0:
        for j, (le, c, t, ch, tc) in enumerate(frames):
            yt, half = _opened_yt(xcs, tc, ch)
            analytic = np.asarray(naca_yt(xcs, tc), float) * ch
            max_move = max(max_move, float(np.max(yt - analytic)))
            upper[:, j, :] = le + xcs[:, None] * ch * c + yt[:, None] * t
            xr = xcs[::-1]
            lower[:, j, :] = le + xr[:, None] * ch * c - yt[::-1][:, None] * t
            le_strip[:, j, :] = le + (ss[:, None] * half) * t
            te_strip[:, j, :] = (le + ch * c) + (te_ss[:, None] * half) * t
        le, c, t, ch, tc = frames[-1]
        sp = _span_outward(c, t)
        yt, half = _opened_yt(xcs, tc, ch)
        # Semicircle from upper (+t) to lower (-t), bulging outboard. The flat cap met the
        # sheet at 90° and the second extruded layer folded at the tip trailing edge.
        phi = np.linspace(0.0, math.pi, n_tip)
        ct = np.cos(phi)
        st = np.sin(phi)
        cap = np.zeros((n_chord, n_tip, 3))
        for i, x in enumerate(xcs):
            center = le + float(x) * ch * c
            cap[i, :, :] = center + yt[i] * (ct[:, None] * t + st[:, None] * sp)
        # The strip's tip column is that same arc, so the seam is the arc and not its diameter.
        le_strip[:, -1, :] = le + half * (ct[::-1][:, None] * t + st[::-1][:, None] * sp)
        te_strip[:, -1, :] = (le + ch * c) + half * (ct[:, None] * t + st[:, None] * sp)
        bulge = float(np.max(yt))
    else:
        # Same seams, with the thickness along the mean-line normal (Eq. 6.6).
        # At x = 0 and x = 1 the 4-digit ordinate is 0; the slope is not.
        for j, (le, c, t, ch, tc) in enumerate(frames):
            upper_c, upper_t, lower_c, lower_t, info = _camber_offsets(
                xcs, tc, ch, m_camber, p_camber)
            max_move = max(max_move, info["max_move"])
            upper[:, j, :] = le + upper_c[:, None] * c + upper_t[:, None] * t
            lower[:, j, :] = le + lower_c[::-1][:, None] * c + lower_t[::-1][:, None] * t
            half = info["half"]
            n_le = info["le_nc"] * c + info["le_nt"] * t
            n_te = info["te_nc"] * c + info["te_nt"] * t
            le_strip[:, j, :] = le + info["le_yc"] * t + (ss[:, None] * half) * n_le
            te_point = le + ch * c + info["te_yc"] * t
            te_strip[:, j, :] = te_point + (te_ss[:, None] * half) * n_te
        le, c, t, ch, tc = frames[-1]
        sp = _span_outward(c, t)
        _uc, _ut, _lc, _lt, info = _camber_offsets(xcs, tc, ch, m_camber, p_camber)
        phi = np.linspace(0.0, math.pi, n_tip)
        ct = np.cos(phi)
        st = np.sin(phi)
        cap = np.zeros((n_chord, n_tip, 3))
        for i, x in enumerate(xcs):
            center = le + float(x) * ch * c + float(info["yc_m"][i]) * t
            n_hat = info["n_c"][i] * c + info["n_t"][i] * t
            cap[i, :, :] = center + info["yt_o"][i] * (ct[:, None] * n_hat + st[:, None] * sp)
        half = info["half"]
        n_le = info["le_nc"] * c + info["le_nt"] * t
        n_te = info["te_nc"] * c + info["te_nt"] * t
        le_strip[:, -1, :] = (le + info["le_yc"] * t
                              + half * (ct[::-1][:, None] * n_le + st[::-1][:, None] * sp))
        te_point = le + ch * c + info["te_yc"] * t
        te_strip[:, -1, :] = te_point + half * (ct[:, None] * n_te + st[:, None] * sp)
        bulge = float(np.max(info["yt_o"]))
    i_m, j_m = n_chord // 3, max(0, n_tip // 2 - 1)
    if j_m + 1 >= n_tip:
        j_m = 0
    du = cap[i_m + 1, j_m] - cap[i_m, j_m]
    dv = cap[i_m, j_m + 1] - cap[i_m, j_m]
    if float(np.dot(np.cross(du, dv), sp)) < 0.0:
        cap = cap[:, ::-1, :].copy()
    if flip_i:
        upper = upper[::-1, :, :].copy()
        lower = lower[::-1, :, :].copy()
        cap = cap[::-1, :, :].copy()
        le_strip = le_strip[::-1, :, :].copy()
        te_strip = te_strip[::-1, :, :].copy()
    _require_outward(upper, frames, +1.0, "upper", flipped=flip_i)
    _require_outward(lower, frames, -1.0, "lower", flipped=flip_i)
    _require_chord_outward(le_strip, frames, -1.0, "le", flipped=flip_i)
    _require_chord_outward(te_strip, frames, +1.0, "te", flipped=flip_i)
    return {"upper": upper, "lower": lower, "tip": cap, "le": le_strip, "te": te_strip,
            "etas": etas, "xcs": xcs, "frames": frames, "flip_i": flip_i, "span_tip": sp,
            "edge_opening": {
                "half_over_chord": EDGE_OPEN_HALF_CHORD,
                "max_move_m": max_move,
                "tip": "semicircle",
                "tip_bulge_m": bulge,
            }}


def _require_outward(patch, frames, thickness_sign: float, name: str, flipped: bool) -> None:
    """Mean cell normal aligned with ±t. ``flipped`` reverses the expected sign."""
    ni, nj, _ = patch.shape
    acc = 0.0
    n = 0
    expect = -thickness_sign if flipped else thickness_sign
    for j in range(nj - 1):
        t = frames[j][2]
        for i in range(0, ni - 1, max(1, (ni - 1) // 8)):
            du = patch[i + 1, j] - patch[i, j]
            dv = patch[i, j + 1] - patch[i, j]
            acc += float(np.dot(np.cross(du, dv), t))
            n += 1
    mean = acc / max(n, 1)
    if mean * expect <= 0.0:
        raise RuntimeError(f"{name} normal dot t is {mean:.3e}, expected sign {expect:+.0f}")


def _require_chord_outward(patch, frames, chord_sign: float, name: str, flipped: bool) -> None:
    """Mean cell normal aligned with ±c. ``chord_sign`` +1 is aft (the trailing-edge strip)."""
    ni, nj, _ = patch.shape
    acc = 0.0
    n = 0
    expect = -chord_sign if flipped else chord_sign
    for j in range(0, nj - 1, max(1, (nj - 1) // 8)):
        cvec = frames[j][1]
        for i in range(ni - 1):
            du = patch[i + 1, j] - patch[i, j]
            dv = patch[i, j + 1] - patch[i, j]
            acc += float(np.dot(np.cross(du, dv), cvec))
            n += 1
    mean = acc / max(n, 1)
    if mean * expect <= 0.0:
        raise RuntimeError(f"{name} normal dot c is {mean:.3e}, expected sign {expect:+.0f}")


def control_ranges(etas: np.ndarray, xcs: np.ndarray) -> dict:
    """Index ranges on the LE→TE / root→tip parameter, for a later hinge moment on this same topology."""
    out = {}
    for name, spec in CONTROLS.items():
        e0, e1 = spec["eta"]
        x_hinge = 1.0 - spec["cf_c"]
        js = [j for j, e in enumerate(etas) if e0 - 1e-12 <= float(e) <= e1 + 1e-12]
        iss = [i for i, x in enumerate(xcs) if float(x) + 1e-12 >= x_hinge]
        out[name] = {
            "eta": [e0, e1], "cf_c": spec["cf_c"], "x_hinge": x_hinge,
            "j": [js[0], js[-1]] if js else None,
            "i_le_to_te": [iss[0], iss[-1]] if iss else None,
            "source": spec["source"],
        }
    return out


def root_y_offset(upper: np.ndarray) -> float:
    """Largest |y| on the root airfoil. The chord line is at y = 0; thickness follows t, which has a y part."""
    return float(np.max(np.abs(upper[:, 0, 1])))


def reference_quantities(surf: Surface) -> dict:
    """S, Cref = S/b and Bref, same definitions as :meth:`Assembly.avl_text` (b from the tessellated y extent)."""
    both = 2.0 if surf.mirror else 1.0
    s = surf.planform_area() * both
    v, _ = surf.mesh()
    b = 2.0 * float(np.max(np.abs(v[:, 1]))) if surf.mirror else float(np.ptp(v[:, 1]))
    return {"S_m2": s, "Bref_m": b, "Cref_m": s / b}


def mac_quarter_chord(surf: Surface) -> dict:
    """Quarter-chord of the geometric MAC on the loft. The moment reference uses its x and y = z = 0.

    The span station is the centroid of the linear chord distribution,
    η = (1 + 2λ) / (3(1 + λ)), where the local chord equals the MAC.
    """
    (le0, c0, _t0, ch0, _tc0), (le1, c1, _t1, ch1, _tc1) = station_frames(surf, [0.0, 1.0])
    lam = ch1 / ch0
    eta = (1.0 + 2.0 * lam) / (3.0 * (1.0 + lam))
    # Two sections so _frames has a span; the straight-panel direction does not depend on the neighbour used.
    frame = station_frames(surf, [0.0, eta])[1] if eta > 0.5 else station_frames(surf, [eta, 1.0])[0]
    le, c, t, ch, tc = frame
    le_g, c_g, t_g, ch_g, _tc_g = _global_frame(surf, (le, c, t, ch, tc))
    point = le_g + 0.25 * ch_g * c_g
    c_mac = (2.0 / 3.0) * ch0 * (1.0 + lam + lam * lam) / (1.0 + lam)
    return {"eta": float(eta), "lambda": float(lam), "c_mac_m": float(c_mac),
            "chord_at_station_m": float(ch_g), "loft_xyz_m": [float(v) for v in point],
            "x_ref_m": float(point[0]), "y_ref_m": 0.0, "z_ref_m": 0.0,
            "note": "Xref is the loft quarter-chord x on the centreline. Cref = S/b is the AVL reference length, "
                    "not this geometric MAC."}


def cruise_state(ref: dict, altitude_m: float = CRUISE_ALT_M, v_ms: float = CRUISE_V_MS,
                 w0_kg: float = DOCUMENTED_W0_KG) -> dict:
    """ISA cruise. CL = W/(q S) with W = W0 * g, g from the ISA module. α is not in here: AVL supplies it."""
    at = isa(altitude_m)
    q = 0.5 * at.rho * v_ms * v_ms
    weight = w0_kg * G0
    cref = ref["Cref_m"]
    return {"altitude_m": altitude_m, "V_m_s": v_ms, "W0_kg": w0_kg, "g": G0,
            "T_K": at.T, "p_Pa": at.p, "rho": at.rho, "mu": at.mu, "a_m_s": at.a,
            "Mach": v_ms / at.a, "q_Pa": q, "CL_target": weight / (q * ref["S_m2"]),
            "Re_Cref": at.rho * v_ms * cref / at.mu, "Cref_m": cref}


def first_spacings(re_cref: float, cref: float) -> dict:
    """Wall spacing at Cref. Coarser levels scale y+ with the same ratio as the 2-D family (1, √2, 2)."""
    out = {}
    for name, spec in MESH_FAMILY.items():
        out[name] = {"yplus_target": spec["yplus"], "s0_m": first_cell(re_cref, cref, spec["yplus"]),
                     "note": "y+ alvo na corda de referência Cref = S/b; a raiz fica um pouco acima e a ponta abaixo"}
    return out


def case_estimate(ref: dict, re_cref: float) -> dict:
    """Cell count, RAM and wall time for one angle on ``OMP_THREADS`` cores. The time constant is not a measurement."""
    levels = {}
    for name in MESH_FAMILY:
        c = level_counts(name)
        cells = cell_count(c["n_chord"], c["n_span"], c["n_tip"], c["n_layers"])
        hours = cells * 8000 * US_PER_CELL_ITER / 3600.0 / OMP_THREADS
        levels[name] = {**c, "cells": cells, "ram_GB_1p8kB": cells * KB_PER_CELL,
                        "ram_GB_2p5kB": cells * 2.5e-6, "wall_h": hours,
                        "max_time_min": MESH_FAMILY[name]["max_time_min"],
                        "s0_m": first_cell(re_cref, ref["Cref_m"], MESH_FAMILY[name]["yplus"])}
    return {"levels": levels, "cores": OMP_THREADS, "iters": 8000,
            "time_model": "cells * 8000 * 4e-6 s / n_cores, constant from full_aircraft_rans_case, not measured here"}


def su2_budget(cells: int, max_time_min: float):
    """70 % of available RAM, and the per-mesh time cap. The time cap does not relax the RAM check."""
    hours = cells * 8000 * US_PER_CELL_ITER / 3600.0 / OMP_THREADS
    return tools.budget(cells * KB_PER_CELL, hours * 60.0, max_time_min=max_time_min)


def avl_text(surf: Surface, ref: dict, mach: float, x_ref: float, nchord: int = 12, nspan: int = 40) -> str:
    """AVL of this symmetric wing only. Bodies are not written. YDUPLICATE mirrors the panel."""
    asm = Assembly([surf], expand_mirror=False)
    return asm.avl_text("h1_tailless_wing", mach=mach,
                        ref={"Sref": ref["S_m2"], "Cref": ref["Cref_m"], "Bref": ref["Bref_m"]},
                        cg=(x_ref, 0.0, 0.0), nchord=nchord, nspan=nspan)


def run_avl_cruise(work: Path, surf: Surface, ref: dict, state: dict, x_ref: float) -> dict:
    """External AVL process: α for the cruise CL, and Cm about the same Xref. Not a solver inside acdt."""
    if not avl_available():
        return {"available": False, "alpha_deg": None, "CL": None, "Cmtot": None, "CDtot": None, "CDff": None}
    work.mkdir(parents=True, exist_ok=True)
    geo = work / "wing.avl"
    geo.write_text(avl_text(surf, ref, state["Mach"], x_ref), encoding="utf-8")
    # Same keystroke shape as aero.avl.run_avl_case. The ST file name is local to ``work``.
    cmds = ["oper", f"a c {state['CL_target']:.6f}", f"m\nmn {state['Mach']:.4f}\n",
            "x", "st", "st.txt", "", "quit"]
    for name in ("st.txt",):
        (work / name).unlink(missing_ok=True)
    import shutil
    import subprocess
    exe = shutil.which("avl")
    r = subprocess.run([exe, geo.name], input="\n".join(cmds) + "\n", capture_output=True, text=True,
                       timeout=120, cwd=work)
    (work / "avl_stdout.txt").write_text(r.stdout + "\n" + r.stderr, encoding="utf-8")
    st = work / "st.txt"
    if not st.exists():
        raise RuntimeError(f"AVL failed (no ST). Tail:\n{r.stdout[-1500:]}\n{r.stderr[-500:]}")
    text = st.read_text(encoding="utf-8")
    return {"available": True, "alpha_deg": _grab(text, "Alpha"), "CL": _grab(text, "CLtot"),
            "Cmtot": _grab(text, "Cmtot"), "CDtot": _grab(text, "CDtot"), "CDff": _grab(text, "CDff"),
            "Xref": _grab(text, "Xref"), "Sref": _grab(text, "Sref"), "Cref": _grab(text, "Cref"),
            "Bref": _grab(text, "Bref"), "Mach": state["Mach"],
            "nchord": 12, "nspan": 40,
            "source": "AVL 3.x external process, symmetric wing, YDUPLICATE"}


def write_plot3d_surface(patches: dict, path: Path) -> None:
    """Formatted Plot3D surface. Order matches pyHyp ``readPlot3d.F90``: sizes, then idim, j, i."""
    names = PATCH_NAMES
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as f:
        f.write(f"{len(names)}\n")
        for name in names:
            ni, nj, _ = patches[name].shape
            f.write(f"{ni} {nj} 1\n")
        for name in names:
            p = patches[name]
            ni, nj, _ = p.shape
            for dim in range(3):
                for j in range(nj):
                    for i in range(ni):
                        f.write(f"{p[i, j, dim]:.16g}\n")


def read_plot3d_surface(path: Path) -> list[np.ndarray]:
    """Inverse of :func:`write_plot3d_surface`. Returns patches in file order, shape (i, j, 3)."""
    with Path(path).open(encoding="ascii") as f:
        n_patch = int(next(f).split()[0])
        sizes = []
        while len(sizes) < 3 * n_patch:
            sizes.extend(int(tok) for tok in next(f).split())
        blocks = []
        for b in range(n_patch):
            il, jl, nk = sizes[3 * b:3 * b + 3]
            if nk != 1:
                raise ValueError(f"surface block k dimension is {nk}, expected 1")
            xyz = np.empty((il, jl, 3), dtype=np.float64)
            for dim in range(3):
                for j in range(jl):
                    for i in range(il):
                        xyz[i, j, dim] = float(next(f).split()[0])
            blocks.append(xyz)
    return blocks


def read_plot3d_volume(path: Path) -> list[np.ndarray]:
    """Blocks from pyHyp ``writePlot3d.F90``: per patch il, jl, N, then idim, k, j, i. Returns (i, j, k, 3)."""
    with Path(path).open(encoding="ascii", errors="replace") as f:
        n_patch = int(next(f).split()[0])
        sizes = []
        while len(sizes) < 3 * n_patch:
            sizes.extend(int(tok) for tok in next(f).split())
        blocks = []
        for b in range(n_patch):
            il, jl, nk = sizes[3 * b:3 * b + 3]
            xyz = np.empty((il, jl, nk, 3), dtype=np.float64)
            for dim in range(3):
                for k in range(nk):
                    for j in range(jl):
                        for i in range(il):
                            xyz[i, j, k, dim] = float(next(f).split()[0])
            blocks.append(xyz)
    return blocks


def _eps_e_literal(eps_e: float | Sequence[float] | None, n_layers: int) -> str:
    """Python literal for pyHyp's epsE. A list must have length N-1: entry i is grid level i+2.

    pyHyp's ``_expandPerLayerOption`` copies that list onto layers 2..N. Level 2 forces the
    explicit dissipation to zero, so entry 0 does not smooth the first extruded sheet.
    """
    n_extrude = int(n_layers) - 1
    if eps_e is None:
        return "1.0"
    if isinstance(eps_e, (str, bytes)):
        raise TypeError("eps_e must be a float or a sequence of floats")
    if isinstance(eps_e, Sequence):
        values = [float(v) for v in eps_e]
        if len(values) != n_extrude:
            raise ValueError(f"eps_e list length must be N-1 ({n_extrude}), got {len(values)}")
        return repr(values)
    return repr(float(eps_e))


def write_pyhyp_script(path: Path, surface_name: str, n_layers: int, s0: float, march_dist: float,
                       root_blocks: tuple[int, ...] | None = None,
                       corner_angle: float | None = None,
                       growth_ratio: float | None = None,
                       splay: float | None = None,
                       eps_e: float | Sequence[float] | None = None,
                       c_max: float | None = None) -> None:
    """Container-side script. Imports pyHyp only. Smoothing numbers are the M6 example's, cited in the header."""
    if root_blocks is None:
        root_blocks = tuple(i + 1 for i, name in enumerate(PATCH_NAMES) if name in SYMMETRY_PATCHES)
    # numpy scalars repr as np.float64(...), which the container script cannot evaluate.
    s0 = float(s0)
    march_dist = float(march_dist)
    # None keeps pyHyp's 60°. A larger angle averages nodes whose face normals
    # differ by more than (180° − angle). The 90° tip and the LE flat need that.
    corner_line = ""
    if corner_angle is not None:
        corner_line = f'    "cornerAngle": {float(corner_angle)!r},\n'
    # pyHyp 2.6.3 stores this as a list of length N-1 and rejects a scalar.
    # Setting it makes pyHyp ignore marchDist. Leave it unset on a real mesh
    # so the ratio is the one pyHyp prints for that march.
    growth_line = ""
    if growth_ratio is not None:
        ratio = float(growth_ratio)
        growth_line = f'    "growthRatios": [{ratio!r}] * {int(n_layers) - 1},\n'
    # Dissipation scales with epsE * (scaleDist/marchDist)^slExp. The M6 value 1.0
    # kept a 1.5 cm march positive. On the 72 m march that value inverts at layer 19,
    # a constant 4 stays positive through layer 24, and a constant 8 or 16 folds the wall.
    eps_e_literal = _eps_e_literal(eps_e, n_layers)
    # pyHyp cuts the pseudo-step when (step / local edge) exceeds cMax. The M6 value 5
    # never fired on this wing: the lower tip leading edge folded at layer 25 with cRatio 3.5.
    c_max_val = 5.0 if c_max is None else float(c_max)
    # None keeps pyHyp's 0.25. A larger splay fans a convex edge instead of folding it.
    splay_line = ""
    if splay is not None:
        splay_line = f'    "splay": {float(splay)!r},\n'
    bc_src = "{" + ", ".join(f'{i}: {{"jLow": "ySymm"}}' for i in root_blocks) + "}"
    text = f'''"""Generated by acdt. Do not import acdt. Smoothing: {PYHYP_SMOOTHING_SOURCE}."""
import faulthandler
import json
faulthandler.enable()
print("STAGE import", flush=True)
from pyhyp import pyHyp
print("STAGE imported", flush=True)

options = {{
    "inputFile": {surface_name!r},
    "fileType": "PLOT3D",
    "unattachedEdgesAreSymmetry": True,
    "outerFaceBC": "farfield",
    "autoConnect": True,
    "BC": {bc_src},
    "families": "wall",
    "N": {int(n_layers)},
    "s0": {s0!r},
    "marchDist": {march_dist!r},
{corner_line}{growth_line}{splay_line}    "ps0": -1.0,
    "pGridRatio": -1.0,
    "cMax": {c_max_val!r},
    "epsE": {eps_e_literal},
    "epsI": 2.0,
    "theta": 3.0,
    "volCoef": 0.25,
    "volBlend": 0.0005,
    "volSmoothIter": 100,
    "kspreltol": 1e-4,
}}
print("STAGE construct", flush=True)
hyp = pyHyp(options=options)
print("STAGE constructed", flush=True)
hyp.run()
print("STAGE extruded", flush=True)
hyp.writePlot3D("volume.xyz")
print("STAGE wrote volume", flush=True)
ratios = [float(v) for v in hyp.growthRatios]
meta = {{
    "growth_ratios": ratios,
    "march_distance_m": float(hyp.getUsedMarchDistance()),
    "N": {int(n_layers)},
    "s0_m": {s0!r},
    "smoothing_source": {PYHYP_SMOOTHING_SOURCE!r},
}}
with open("pyhyp_meta.json", "w", encoding="utf-8") as fh:
    json.dump(meta, fh, indent=1)
print("PYHYP_DONE", flush=True)
'''
    Path(path).write_text(text, encoding="utf-8")


def gci_3d(f_fine: float, f_medium: float, f_coarse: float,
           n_fine: int, n_medium: int, n_coarse: int, drifts) -> dict:
    """Celik et al. 2008 via :func:`cfd.gci`, with the 3-D spacing h = (1/N)^(1/3)."""
    hs = tuple((1.0 / float(n)) ** (1.0 / 3.0) for n in (n_fine, n_medium, n_coarse))
    out = gci(float(f_fine), float(f_medium), float(f_coarse), *hs)
    out["h_definition"] = "(1/N)**(1/3)"
    out["dimension"] = 3
    out["iter_drift"] = [None if d is None else float(d) for d in drifts]
    worst = max((0.0 if d is None else abs(float(d))) for d in out["iter_drift"]) if out["iter_drift"] else float("inf")
    if any(d is None for d in out["iter_drift"]):
        worst = float("inf")
    denom = abs(f_fine) if f_fine else float("inf")
    ea21 = abs(f_fine - f_medium) / denom
    # Zero drift against a zero fine–medium gap is iterative convergence. A positive drift against a zero gap is not.
    out["iterative_ok"] = bool(math.isfinite(worst) and worst <= 0.1 * ea21)
    return out


def h1_factor_decision(hifi, lowfi, *, same_quantity: bool, oscillatory: bool = False,
                       iterative_ok: bool = False, gci_defined: bool = False,
                       quantity: str, why: str | None = None) -> dict:
    """Decide whether a ratio may be applied to L1/L2. One angle never applies, even inside the band.

    Missing, zero, or a different quantity → nao_aplicar. Outside [0.7, 1.5] → nao_aplicar and the model
    is reviewed before any later use. Oscillatory GCI or an iterative error that is not small → nao_aplicar.
    Inside the band with a usable GCI → eligible, and still nao_aplicar because the polar was not evaluated.
    """
    lo, hi = H1_RATIO_BAND
    out = {"quantity": quantity, "hifi": hifi, "lowfi": lowfi, "band": [lo, hi],
           "decision": "nao_aplicar", "eligible": False, "ratio": None, "reason": "",
           "valid": False}
    if hifi is None or lowfi is None or not same_quantity:
        out["reason"] = why or "quantidade em falta ou não é a mesma grandeza"
        return out
    try:
        hf, lf = float(hifi), float(lowfi)
    except (TypeError, ValueError):
        out["reason"] = "valor não numérico"
        return out
    if not (math.isfinite(hf) and math.isfinite(lf)):
        out["reason"] = "valor não finito"
        return out
    if lf == 0.0:
        out["reason"] = "referência de baixa fidelidade é zero"
        return out
    ratio = hf / lf
    out["ratio"] = ratio
    if not (lo <= ratio <= hi):
        out["reason"] = f"razão {ratio:.4g} fora de [{lo:g}, {hi:g}]; rever o modelo antes de aplicar"
        return out
    if oscillatory or not iterative_ok or not gci_defined:
        out["reason"] = why or (
            "GCI oscilatório ou erro iterativo não pequeno face à diferença fino–médio")
        return out
    out["eligible"] = True
    out["reason"] = ("razão dentro da banda e GCI aceitável num só α; a polar não foi avaliada, "
                     "por isso o factor não se aplica a L1/L2")
    return out


def factor_record(decision: dict) -> dict:
    """Stored factor. ``valid`` stays false so the 0.2–5 calibration gate cannot apply a one-point ratio."""
    return {"name": decision["quantity"], "value": decision["ratio"], "valid": False,
            "invalid_reason": decision["reason"], "eligible": decision["eligible"],
            "decision": "nao_aplicar", "band": list(H1_RATIO_BAND),
            "note": "H1_RATIO_BAND é [0.7, 1.5]. Não altera calibration.RATIO_BAND."}


def _tri_scalar(a, b, c) -> float:
    return (a[0] * (b[1] * c[2] - b[2] * c[1]) + a[1] * (b[2] * c[0] - b[0] * c[2])
            + a[2] * (b[0] * c[1] - b[1] * c[0]))


def _loop_scalar(pts) -> float:
    s = 0.0
    a = pts[0]
    for i in range(1, len(pts) - 1):
        s += _tri_scalar(a, pts[i], pts[i + 1])
    return s


def _prism_volume(nodes, xyz) -> float:
    p = [xyz[i] for i in nodes]
    faces = (
        (p[0], p[2], p[1]),
        (p[3], p[4], p[5]),
        (p[0], p[1], p[4], p[3]),
        (p[1], p[2], p[5], p[4]),
        (p[2], p[0], p[3], p[5]),
    )
    return sum(_loop_scalar(f) for f in faces) / 6.0


def _collapse(ids8, local) -> tuple | None:
    seq = []
    for a in local:
        n = ids8[a]
        if not seq or seq[-1] != n:
            seq.append(n)
    if len(seq) > 1 and seq[0] == seq[-1]:
        seq.pop()
    if len(set(seq)) < 3:
        return None
    return tuple(seq)


def _orient_prism(nodes, xyz) -> list:
    nodes = list(nodes)
    if _prism_volume(nodes, xyz) < 0.0:
        nodes = [nodes[0], nodes[2], nodes[1], nodes[3], nodes[5], nodes[4]]
    if _prism_volume(nodes, xyz) <= 0.0:
        raise RuntimeError("prism volume is not positive after flipping the bases")
    return nodes


def _su2_volume_nodes(ids8, xyz) -> tuple[int, list]:
    ids = [int(v) for v in ids8]
    nuniq = len(set(ids))
    if nuniq == 8:
        return 12, ids
    if nuniq == 6 and ids[0] == ids[3] and ids[4] == ids[7] and ids[0] != ids[4]:
        return 13, _orient_prism([ids[0], ids[1], ids[2], ids[4], ids[5], ids[6]], xyz)
    if nuniq == 6 and ids[1] == ids[2] and ids[5] == ids[6] and ids[1] != ids[5]:
        return 13, _orient_prism([ids[0], ids[3], ids[1], ids[4], ids[7], ids[5]], xyz)
    raise RuntimeError(f"unsupported collapsed hex with {nuniq} unique nodes: {ids}")


def _merge_id(point, tol: float, bins: dict, coords: list) -> int:
    base = tuple(int(round(float(v) / tol)) for v in point)
    best = None
    best_d = tol * tol
    px, py, pz = float(point[0]), float(point[1]), float(point[2])
    for dz in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for pid in bins.get((base[0] + dx, base[1] + dy, base[2] + dz), ()):
                    cx, cy, cz = coords[pid]
                    d = (cx - px) ** 2 + (cy - py) ** 2 + (cz - pz) ** 2
                    if d <= best_d:
                        best, best_d = pid, d
    if best is not None:
        return best
    pid = len(coords)
    coords.append((px, py, pz))
    bins.setdefault(base, []).append(pid)
    return pid


def _cycle_equal(a: tuple, b: tuple) -> bool:
    n = len(a)
    if len(b) != n:
        return False
    for s in range(n):
        if all(a[i] == b[(s + i) % n] for i in range(n)):
            return True
    return False


def _is_opposite(a: tuple, b: tuple) -> bool:
    return _cycle_equal(a, tuple(reversed(b)))


def write_su2_volume(blocks: list[dict], path: Path, tol: float = SU2_MERGE_TOL_M,
                     reject_below: float = 0.0) -> dict:
    """Node-merged SU2 mesh. ``blocks`` are ``{xyz: (ni,nj,nk,3), symmetry_at_j0: bool}`` with k = 0 on the wall.

    Boundary quads: wall is −k, farfield is +k, symmetry (root) is −j. A collapsed quad is a triangle.
    The audit fails unless every boundary face is one of those markers, with the same winding.

    A cell volume at or below ``reject_below`` raises. The default 0 rejects every non-positive
    cell. A negative floor is only for a counted roundoff sliver; it does not turn an inverted
    march into a valid mesh, and the returned ``min_volume`` stays the real minimum.
    """
    bins: dict = {}
    coords: list = []
    ids = []
    for block in blocks:
        xyz = np.asarray(block["xyz"], float)
        ni, nj, nk, _ = xyz.shape
        grid = np.empty((ni, nj, nk), dtype=np.int64)
        for k in range(nk):
            for j in range(nj):
                for i in range(ni):
                    grid[i, j, k] = _merge_id(xyz[i, j, k], tol, bins, coords)
        ids.append(grid)

    markers = {"wing": [], "symmetry": [], "farfield": []}
    counts = {"hex": 0, "prism": 0}
    min_vol = float("inf")
    faces: dict = {}

    def add_face(loop, marker):
        if loop is None:
            return
        key = tuple(sorted(loop))
        prev = faces.get(key)
        if prev is None:
            faces[key] = [1, loop]
        else:
            prev[0] += 1
            if not _is_opposite(prev[1], loop):
                prev.append("winding")
        if marker:
            markers[marker].append(loop)

    n_elem = 0
    prepared = []
    for grid, block in zip(ids, blocks):
        ni, nj, nk = grid.shape
        sym = bool(block.get("symmetry_at_j0"))
        for k in range(nk - 1):
            for j in range(nj - 1):
                for i in range(ni - 1):
                    local = [int(grid[a]) for a in (
                        (i, j, k), (i + 1, j, k), (i + 1, j + 1, k), (i, j + 1, k),
                        (i, j, k + 1), (i + 1, j, k + 1), (i + 1, j + 1, k + 1), (i, j + 1, k + 1))]
                    kind, nodes = _su2_volume_nodes(local, coords)
                    prepared.append((kind, nodes))
                    n_elem += 1
                    counts["hex" if kind == 12 else "prism"] += 1
                    vol = _closed_volume(local, coords)
                    min_vol = min(min_vol, vol)
                    for tag, idx in _FACES:
                        loop = _collapse(local, idx)
                        marker = None
                        if tag == "km" and k == 0:
                            marker = "wing"
                        elif tag == "kp" and k == nk - 2:
                            marker = "farfield"
                        elif tag == "jm" and j == 0 and sym:
                            marker = "symmetry"
                        add_face(loop, marker)
    if not prepared:
        raise RuntimeError("no volume cells")
    if min_vol <= reject_below:
        raise RuntimeError(f"non-positive cell volume {min_vol:.3e}")

    unmarked = []
    winding_bad = False
    boundary = {}
    for key, rec in faces.items():
        if rec[0] == 1:
            boundary[key] = rec[1]
            unmarked.append(key)
        elif rec[0] != 2 or len(rec) > 2:
            winding_bad = True
    marker_ok = True
    seen = set()
    for name, loops in markers.items():
        for loop in loops:
            key = tuple(sorted(loop))
            if key not in boundary or not _cycle_equal(boundary[key], loop):
                marker_ok = False
            seen.add(key)
    extra = [k for k in unmarked if k not in seen]
    watertight = marker_ok and not extra and not winding_bad and len(seen) == len(boundary)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as f:
        f.write("NDIME= 3\n")
        f.write(f"NELEM= {n_elem}\n")
        for e, (kind, nodes) in enumerate(prepared):
            f.write(str(kind) + " " + " ".join(str(n) for n in nodes) + f" {e}\n")
        f.write(f"NPOIN= {len(coords)}\n")
        for i, (x, y, z) in enumerate(coords):
            f.write(f"{x:.16g} {y:.16g} {z:.16g} {i}\n")
        present = [(name, loops) for name, loops in markers.items() if loops]
        f.write(f"NMARK= {len(present)}\n")
        for name, loops in present:
            f.write(f"MARKER_TAG= {name}\n")
            f.write(f"MARKER_ELEMS= {len(loops)}\n")
            for loop in loops:
                kind = 9 if len(loop) == 4 else 5
                f.write(str(kind) + " " + " ".join(str(n) for n in loop) + "\n")
    return {"points": len(coords), "cells": n_elem, "n_hex": counts["hex"], "n_prism": counts["prism"],
            "n_wing": len(markers["wing"]), "n_symmetry": len(markers["symmetry"]),
            "n_farfield": len(markers["farfield"]), "min_volume": min_vol,
            "watertight": watertight, "unmarked_boundary": len(extra), "winding_ok": marker_ok and not winding_bad,
            "mesh": str(path)}


def _closed_volume(ids8, xyz) -> float:
    s = 0.0
    for _tag, idx in _FACES:
        loop = _collapse(ids8, idx)
        if loop is None:
            continue
        s += _loop_scalar([xyz[i] for i in loop])
    return s / 6.0


def extrusion_check(surface: dict, blocks: list[np.ndarray], march_dist: float, tol: float = 1e-6) -> dict:
    """Which layer is the input surface, and how far the other end marched. Does not invent a growth ratio."""
    names = PATCH_NAMES
    if len(blocks) != len(names):
        return {"ok": False, "reason": f"{len(blocks)} blocks, expected {len(names)}"}
    surface_end = None
    radii = []
    for name, block in zip(names, blocks):
        surf = surface[name]
        if block.shape[:2] != surf.shape[:2]:
            return {"ok": False, "reason": f"{name} shape {block.shape[:2]} != {surf.shape[:2]}"}
        e0 = float(np.max(np.linalg.norm(block[:, :, 0, :] - surf, axis=-1)))
        eN = float(np.max(np.linalg.norm(block[:, :, -1, :] - surf, axis=-1)))
        if e0 <= tol and eN > tol:
            end = 0
        elif eN <= tol and e0 > tol:
            end = -1
        else:
            return {"ok": False, "reason": f"{name} matches neither end (k0 {e0:.3e}, kN {eN:.3e})",
                    "k0_err": e0, "kN_err": eN}
        if surface_end is None:
            surface_end = end
        elif surface_end != end:
            return {"ok": False, "reason": "patches disagree on which layer is the surface"}
        outer = 0 if end == -1 else -1
        radii.append(float(np.mean(np.linalg.norm(block[:, :, outer, :] - block[:, :, end, :], axis=-1))))
    mean_r = float(np.mean(radii))
    outward = mean_r > 0.5 * march_dist
    return {"ok": outward, "surface_k": 0 if surface_end == 0 else "last",
            "mean_march_m": mean_r, "march_requested_m": march_dist,
            "reason": "" if outward else "march distance is far below the request; likely marching inward",
            "per_block_march_m": radii}


def su2_rans_cfg(mesh: str, alpha_deg: float, state: dict, s_half: float, cref: float, x_ref: float,
                 iters: int = 8000) -> str:
    """Compressible RANS-SA, one angle. REF_AREA is S/2 so the half-model CL is the full-aircraft CL."""
    return f"""% acdt H1 — tailless wing half model, compressible RANS-SA
% SU2 v8 (Economon et al., AIAA J 54(3), 2016); SA (Spalart & Allmaras, AIAA 92-0439)
SOLVER= RANS
KIND_TURB_MODEL= SA
MATH_PROBLEM= DIRECT
RESTART_SOL= NO
MACH_NUMBER= {state['Mach']:.6f}
AOA= {alpha_deg:.6f}
SIDESLIP_ANGLE= 0.0
REYNOLDS_NUMBER= {state['Re_Cref']:.6e}
REYNOLDS_LENGTH= {cref:.6f}
FREESTREAM_PRESSURE= {state['p_Pa']:.6f}
FREESTREAM_TEMPERATURE= {state['T_K']:.6f}
REF_ORIGIN_MOMENT_X= {x_ref:.6f}
REF_ORIGIN_MOMENT_Y= 0.0
REF_ORIGIN_MOMENT_Z= 0.0
REF_LENGTH= {cref:.6f}
REF_AREA= {s_half:.6f}
MARKER_HEATFLUX= ( wing, 0.0 )
MARKER_SYM= ( symmetry )
MARKER_FAR= ( farfield )
MARKER_PLOTTING= ( wing )
MARKER_MONITORING= ( wing )
NUM_METHOD_GRAD= WEIGHTED_LEAST_SQUARES
CFL_NUMBER= 5.0
CFL_ADAPT= YES
CFL_ADAPT_PARAM= ( 0.5, 1.2, 5.0, 100.0 )
CONV_NUM_METHOD_FLOW= ROE
MUSCL_FLOW= YES
SLOPE_LIMITER_FLOW= VENKATAKRISHNAN
CONV_NUM_METHOD_TURB= SCALAR_UPWIND
MUSCL_TURB= NO
TIME_DISCRE_FLOW= EULER_IMPLICIT
LINEAR_SOLVER= FGMRES
LINEAR_SOLVER_PREC= ILU
LINEAR_SOLVER_ERROR= 1E-6
LINEAR_SOLVER_ITER= 10
ITER= {iters}
CONV_FIELD= RMS_DENSITY
CONV_RESIDUAL_MINVAL= -8
SCREEN_OUTPUT= ( INNER_ITER, RMS_DENSITY, RMS_NU_TILDE, LIFT, DRAG, MOMENT_Y )
HISTORY_OUTPUT= ( ITER, RMS_RES, AERO_COEFF )
SCREEN_WRT_FREQ_INNER= 100
MESH_FILENAME= {mesh}
MESH_FORMAT= SU2
SOLUTION_FILENAME= restart_flow.dat
RESTART_FILENAME= restart_flow.dat
OUTPUT_FILES= ( RESTART, SURFACE_CSV )
CONV_FILENAME= history
"""


def geometry_record(surf: Surface, meta: dict, patches: dict, ref: dict, mac: dict, state: dict) -> dict:
    return {
        "scope": scope_text(surf),
        "scale_k": meta["k"],
        "S_draw_m2": meta["S_draw_m2"],
        "S_m2": ref["S_m2"],
        "Bref_m": ref["Bref_m"],
        "Cref_m": ref["Cref_m"],
        "mac": mac,
        "origin_m": list(meta["origin_m"]),
        "drawing": DRAWING,
        "airfoil": (
            naca4_mean_line_record(surf.airfoil, surf.sections[0]["tc"], surf.sections[-1]["tc"])
            if getattr(surf, "naca4_mean_line", False)
            else section_thickness_record(
                surf.airfoil, surf.sections[0]["tc"], surf.sections[-1]["tc"])
        ),
        "controls_faired": control_ranges(patches["etas"], patches["xcs"]),
        "root_max_abs_y_m": root_y_offset(patches["upper"]),
        "root_note": ("O diedro inclina o plano da secção: t = c × sp tem componente y, por isso a nervura da raiz "
                      "não está em y = 0. pyHyp ySymm fixa o y inicial de cada nó dessa aresta. "
                      "O valor é o desvio, não uma correcção."),
        "cruise": state,
        "flip_i": patches["flip_i"],
        "edge_opening": {
            **patches["edge_opening"],
            "where": "LE e TE, em todas as secções, fechados por uma faixa; a ponta é um semicírculo",
            "reason": (
                "pyHyp 2.6.3 faz SEGV em setup, depois de 'Topology complete', quando um quad "
                "da tampa repete o nó do bordo de ataque ou de fuga de espessura nula. "
                "Uma face vertical de 5e-4 da corda deixou o bordo de fuga da ponta negativo "
                "desde a segunda camada. Com 2e-3 a primeira camada ficou positiva "
                "(qualidade 0.193, volume 4.09e-11) e a segunda negativa (-1.52e-11), "
                "na superfície grossa, N=20, s0 da malha grossa, razão 1.339, cornerAngle 150. "
                "Um quarto de círculo nessa face piorou a marcha (camada 14, volume -6.87e-6). "
                "splay 1.0, com a omissão do pyHyp em 0.25, não mudou uma linha da tabela: "
                "o canto é uma junção entre patches, não uma aresta livre. "
                "A face vertical de 2e-3 mantém-se nas faixas. "
                "A tampa plana, a 90° da folha, foi substituída por um semicírculo de raio igual "
                "à meia-espessura local, tangente à folha. O avanço é a meia-espessura da ponta. "
                "Com 9 pontos (22,5° por face), cornerAngle 150, N=20 e a razão 1,339, o volume "
                "mínimo foi positivo em todas as camadas e a superfície ficou em k=0, com marcha "
                "média 1,55 cm para o pedido impresso de 1,53 cm. "
                "Na marcha de 72,6 m (N=49, razão impressa 1,339, epsE 4) o cMax 5 do exemplo M6 "
                "deixou o passo chegar a 3,5 arestas e inverteu uma célula da face inferior, "
                "no bordo de ataque da ponta, na camada 25. Com cMax 0,5 o volume mínimo foi "
                "positivo nas 48 camadas extrudidas, a marcha integrada chegou a 72,8 m e a "
                "superfície ficou em k=0, com distância recta média de 59,0 m. "
                "É um artifício da malha, não do OML analítico usado no AVL."
            ),
        },
        "farfield_chords": FARFIELD_CHORDS,
        "pyhyp_smoothing_source": PYHYP_SMOOTHING_SOURCE,
    }


def write_surface_case(work: Path, level: str, patches: dict, s0: float, march_dist: float) -> Path:
    """Surface file plus the container extrude script. Does not run pyHyp."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    fmt = work / "wing.fmt"
    write_plot3d_surface(patches, fmt)
    layers = level_counts(level)["n_layers"]
    write_pyhyp_script(
        work / "extrude.py", "wing.fmt", layers, s0, march_dist,
        corner_angle=TIP_CORNER_ANGLE, eps_e=PYHYP_EPS_E, c_max=PYHYP_C_MAX,
    )
    return fmt


# Acceptance tolerances, declared here and copied into the report.
# On the scaled flying wing (n_chord=17, n_span=9) the span-axis incidence matched
# the AVL Ainc to < 1e-6 deg, the panel area matched Sref to roundoff when the
# inboard chord of each panel is the reference direction, and the span matched
# Bref to < 1e-6 relative. The x-z projection of the tip chord differed from Ainc
# by about 0.006 deg because of dihedral; that projection is reported and is not
# the pass/fail quantity. 0.05 deg is far below the 20 deg sign error and above
# the 0.001 deg rounding of the AVL Ainc field.
INCIDENCE_TOL_DEG = 0.05
AREA_RTOL = 1.0e-3
SPAN_RTOL = 1.0e-3
MOMENT_ORIGIN_TOL_M = 1.0e-4
SYMMETRY_Y_TOL_M = 1.0e-4
SIDESLIP_TOL_DEG = 1.0e-6
LE_MATCH_TOL_M = 1.0e-4
REF_LENGTH_TOL_M = 1.0e-4
REF_AREA_RTOL = 1.0e-4

_AVL_KEYWORDS = {
    "SURFACE", "BODY", "SECTION", "YDUPLICATE", "NACA", "AIRFOIL", "CONTROL",
    "COMPONENT", "INDEX", "SCALE", "TRANSLATE", "ANGLE", "CLAF", "CDCL",
    "NOWAKE", "NOALBE", "NOLOAD", "BFILE", "DESIGN",
}


class WingGeometryError(RuntimeError):
    """The wing mesh, the AVL file and the SU2 case disagree. The RANS run must not start."""

    def __init__(self, report: dict):
        self.report = report
        failed = [c["id"] for c in report["checks"] if c["status"] == "falha"]
        super().__init__("verificação da geometria RANS falhou: " + ", ".join(failed))


def _avl_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        s = raw.split("#", 1)[0].strip()
        if s:
            out.append(s)
    return out


def _float_tokens(line: str) -> list[float] | None:
    parts = line.split()
    try:
        return [float(p) for p in parts]
    except ValueError:
        return None


def parse_avl_geometry(text: str) -> dict:
    """Reference values and section Ainc from an AVL file.

    Comment lines (``#``, as written by :meth:`Assembly.avl_text`) are ignored, so a
    file without those comments parses the same way. A SECTION with fewer than five
    numbers is an error: a missing Ainc is not stored as zero. Ainc is the AVL
    incidence, nose up positive (Drela & Youngren, AVL 3.x user guide; the same
    quantity :meth:`Surface._frames` uses as ``twist_deg``).
    """
    lines = _avl_lines(text)
    if len(lines) < 5:
        raise ValueError("ficheiro AVL sem cabeçalho de referência")
    idx = 1  # title
    try:
        mach = float(lines[idx].split()[0])
        idx += 1
        _iysym, _izsym, _zsym = (float(v) for v in lines[idx].split()[:3])
        idx += 1
        sref, cref, bref = (float(v) for v in lines[idx].split()[:3])
        idx += 1
        xref, yref, zref = (float(v) for v in lines[idx].split()[:3])
        idx += 1
    except (IndexError, ValueError) as exc:
        raise ValueError("cabeçalho AVL incompleto; não se preenche a referência com zero") from exc
    if idx < len(lines) and _float_tokens(lines[idx]) is not None and lines[idx].split()[0] not in _AVL_KEYWORDS:
        idx += 1  # CDp, unused
    surfaces = []
    while idx < len(lines):
        if lines[idx] != "SURFACE":
            if lines[idx] == "BODY":
                idx += 1
                while idx < len(lines) and lines[idx] not in ("SURFACE", "BODY"):
                    idx += 1
                continue
            idx += 1
            continue
        idx += 1
        if idx >= len(lines):
            raise ValueError("SURFACE sem nome")
        name = lines[idx]
        idx += 1
        ydup = False
        sections = []
        while idx < len(lines) and lines[idx] not in ("SURFACE", "BODY"):
            key = lines[idx]
            if key == "YDUPLICATE":
                ydup = True
                idx += 1
                if idx < len(lines) and lines[idx] not in _AVL_KEYWORDS:
                    idx += 1
                continue
            if key == "SECTION":
                idx += 1
                if idx >= len(lines):
                    raise ValueError(f"SECTION sem coordenadas em {name}")
                nums = _float_tokens(lines[idx])
                if nums is None or len(nums) < 5:
                    raise ValueError(
                        f"SECTION incompleta em {name!r}: Ainc em falta não é zero ({lines[idx]!r})")
                sections.append({
                    "le": np.array(nums[:3], float),
                    "chord": float(nums[3]),
                    "ainc_deg": float(nums[4]),
                })
                idx += 1
                continue
            idx += 1
            # CONTROL carries a name and a data line. Other cards carry one payload line.
            payload = 2 if key == "CONTROL" else 1
            skipped = 0
            while idx < len(lines) and lines[idx] not in _AVL_KEYWORDS and skipped < payload:
                idx += 1
                skipped += 1
        if not sections:
            raise ValueError(f"SURFACE {name!r} sem secções")
        surfaces.append({"name": name, "yduplicate": ydup, "sections": sections})
    if not surfaces:
        raise ValueError("AVL sem SURFACE")
    return {
        "mach": mach, "Sref": sref, "Cref": cref, "Bref": bref,
        "Xref": xref, "Yref": yref, "Zref": zref, "surfaces": surfaces,
    }


def _select_surface(parsed: dict, surface: str | None) -> dict:
    surfs = parsed["surfaces"]
    if surface is None:
        if len(surfs) != 1:
            names = ", ".join(s["name"] for s in surfs)
            raise ValueError(f"AVL com várias superfícies ({names}); indique surface=")
        return surfs[0]
    for s in surfs:
        if s["name"] == surface:
            return s
    raise ValueError(f"superfície {surface!r} não está no AVL")


def _cfg_body(text: str) -> str:
    kept = []
    for line in text.splitlines():
        if "%" in line:
            line = line.split("%", 1)[0]
        kept.append(line)
    return "\n".join(kept)


def _cfg_raw(text: str, key: str) -> str | None:
    m = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*(.*?)\s*$", _cfg_body(text))
    if m is None or m.group(1) == "":
        return None
    return m.group(1).strip()


def _cfg_float(text: str, key: str) -> float | None:
    raw = _cfg_raw(text, key)
    if raw is None:
        return None
    token = raw.split()[0].rstrip(",")
    try:
        value = float(token)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def _polyline(sections: list[dict]) -> tuple[np.ndarray, np.ndarray, float]:
    les = np.vstack([s["le"] for s in sections])
    if len(les) == 1:
        return les, np.array([0.0]), 0.0
    seg = np.linalg.norm(np.diff(les, axis=0), axis=1)
    total = float(seg.sum())
    if total < 1e-12:
        raise ValueError("secções AVL coincidentes")
    eta = np.concatenate([[0.0], np.cumsum(seg) / total])
    return les, eta, total


def _project_eta(point: np.ndarray, les: np.ndarray, eta: np.ndarray) -> tuple[float, float]:
    if len(les) == 1:
        return 0.0, float(np.linalg.norm(point - les[0]))
    best_t = 0.0
    best_d = float("inf")
    for i in range(len(les) - 1):
        a, b = les[i], les[i + 1]
        ab = b - a
        L2 = float(np.dot(ab, ab))
        if L2 < 1e-18:
            t_clamped, proj = 0.0, a
        else:
            t_clamped = min(1.0, max(0.0, float(np.dot(point - a, ab) / L2)))
            proj = a + t_clamped * ab
        d = float(np.linalg.norm(point - proj))
        if d < best_d:
            best_d = d
            best_t = float(eta[i] + t_clamped * (eta[i + 1] - eta[i]))
    return best_t, best_d


def _interp_ainc(eta_q: float, sections: list[dict], eta: np.ndarray) -> float:
    aincs = [s["ainc_deg"] for s in sections]
    if eta_q <= float(eta[0]):
        return float(aincs[0])
    if eta_q >= float(eta[-1]):
        return float(aincs[-1])
    for i in range(len(eta) - 1):
        e0, e1 = float(eta[i]), float(eta[i + 1])
        if e0 <= eta_q <= e1:
            span = e1 - e0
            w = 0.0 if span == 0.0 else (eta_q - e0) / span
            return float(aincs[i] + w * (aincs[i + 1] - aincs[i]))
    return float(aincs[-1])


def _span_hat(les: np.ndarray, j: int) -> np.ndarray:
    if j == 0:
        d = les[1] - les[0]
    elif j == len(les) - 1:
        d = les[-1] - les[-2]
    else:
        d = les[j + 1] - les[j - 1]
    sp = np.array(d, float)
    sp[0] = 0.0
    n = float(np.linalg.norm(sp))
    if n < 1e-14:
        raise ValueError(f"secção {j} sem envergadura no plano y-z")
    return sp / n


def _incidence_deg(chord: np.ndarray, span_hat: np.ndarray) -> float:
    """Signed rotation of the chord from +x about the outboard span, degrees.

    Same construction as the loft check: atan2(chord · (k × ex), chord · ex).
    Positive is nose up. This is the AVL Ainc, not the x-z projection.
    """
    ex = np.array([1.0, 0.0, 0.0])
    return math.degrees(math.atan2(
        float(np.dot(chord, np.cross(span_hat, ex))), float(np.dot(chord, ex))))


def _skin_separation(upper: np.ndarray, lower: np.ndarray, j: int) -> np.ndarray:
    n = upper.shape[0]
    i = (n - 1) // 2
    a = upper[i, j]
    b_pair = lower[n - 1 - i, j]
    b_same = lower[i, j]
    b = b_pair if np.linalg.norm(a - b_pair) <= np.linalg.norm(a - b_same) else b_same
    return a - b


def measure_wing_sections(patches: dict, sections: list[dict]) -> dict:
    """Leading-edge, chord and incidence at every span station of ``upper``/``lower``.

    ``lower`` follows :func:`build_patches`: its i index runs from the trailing edge
    back to the leading edge. ``flip_i`` reverses both patches together, so the two
    edges stay paired. The leading edge is the edge closer to the AVL section line,
    not the edge with the smaller x. The tip cap is not a section.
    """
    if "upper" not in patches or "lower" not in patches:
        raise ValueError("a malha precisa das patches upper e lower")
    upper = np.asarray(patches["upper"], float)
    lower = np.asarray(patches["lower"], float)
    if upper.ndim != 3 or lower.shape != upper.shape or upper.shape[0] < 2 or upper.shape[1] < 2:
        raise ValueError("upper e lower têm de ser (i, j, 3) com pelo menos duas estações")
    les_avl, eta_avl, _total = _polyline(sections)
    n_j = upper.shape[1]
    stations = []
    for j in range(n_j):
        edge_a = 0.5 * (upper[0, j] + lower[-1, j])
        edge_b = 0.5 * (upper[-1, j] + lower[0, j])
        _ta, da = _project_eta(edge_a, les_avl, eta_avl)
        _tb, db = _project_eta(edge_b, les_avl, eta_avl)
        if da <= db:
            le, te, dist = edge_a, edge_b, da
        else:
            le, te, dist = edge_b, edge_a, db
        stations.append({"j": j, "le": le, "te": te, "le_distance_m": dist})
    faired = patches.get("faired_te")
    if faired is not None:
        faired = np.asarray(faired, float)
        if faired.shape != (n_j, 3):
            raise ValueError("faired_te tem de ser (n_span, 3); uma corda em falta não se substitui")
        for s in stations:
            s["te_surface"] = s["te"]
            s["te"] = faired[s["j"]]
    les = np.vstack([s["le"] for s in stations])
    tes = np.vstack([s["te"] for s in stations])
    out = []
    for s in stations:
        j = s["j"]
        chord = s["te"] - s["le"]
        eta, _d = _project_eta(s["le"], les_avl, eta_avl)
        span = _span_hat(les, j)
        phi = _incidence_deg(chord, span)
        dx = float(chord[0])
        xz = float("nan")
        if dx != 0.0 or chord[2] != 0.0:
            xz = -math.degrees(math.atan2(float(chord[2]), dx))
        if j == 0:
            role = "raiz"
        elif j == n_j - 1:
            role = "ponta"
        else:
            role = "intermedia"
        out.append({
            "j": j, "papel": role, "eta": eta,
            "ainc_avl_deg": _interp_ainc(eta, sections, eta_avl),
            "incidencia_deg": phi, "incidencia_xz_deg": xz,
            "le_m": [float(v) for v in s["le"]],
            "te_m": [float(v) for v in s["te"]],
            "le_distance_m": float(s["le_distance_m"]),
            "chord_x_m": dx,
        })
    return {"stations": out, "les": les, "tes": tes, "section_eta": eta_avl}


def _panel_area(measured: dict, section_eta: np.ndarray) -> float:
    """Planform area of one side, using each AVL panel's inboard chord direction.

    This is the definition in :meth:`Surface.planform_area` (and therefore of Sref):
    the local chord length times the span element perpendicular to the inboard chord
    of that panel. Using the twisted chord at every station does not match Sref.
    """
    stations = measured["stations"]
    les = measured["les"]
    tes = measured["tes"]
    etas = np.array([s["eta"] for s in stations])
    area = 0.0
    for j in range(len(stations) - 1):
        mid = 0.5 * (float(etas[j]) + float(etas[j + 1]))
        i_panel = int(np.searchsorted(section_eta, mid, side="right") - 1)
        i_panel = min(max(i_panel, 0), len(section_eta) - 2)
        target = float(section_eta[i_panel])
        k = int(np.argmin(np.abs(etas - target)))
        c0 = tes[k] - les[k]
        ch_ref = float(np.linalg.norm(c0))
        if ch_ref < 1e-14:
            raise ValueError("corda nula na malha")
        chat = c0 / ch_ref
        ch0 = float(np.linalg.norm(tes[j] - les[j]))
        ch1 = float(np.linalg.norm(tes[j + 1] - les[j + 1]))
        seg = les[j + 1] - les[j]
        perp = seg - float(np.dot(seg, chat)) * chat
        area += 0.5 * (ch0 + ch1) * float(np.linalg.norm(perp))
    return area


def _check(cid: str, status: str, motivo: str, **extra) -> dict:
    return {
        "id": cid, "status": status, "passou": status == "passa",
        "bloqueia": status == "falha", "motivo": motivo, **extra,
    }


def _rel_ok(measured: float, reference: float, rtol: float, atol: float) -> bool:
    if not (math.isfinite(measured) and math.isfinite(reference)) or reference == 0.0:
        return False
    return abs(measured - reference) <= max(atol, rtol * abs(reference))


def verify_wing_rans_geometry(patches: dict, avl_text: str, cfg_text: str, *,
                              surface: str | None = None,
                              cmy: float | None = None,
                              cm_avl: float | None = None) -> dict:
    """Block a wing RANS case whose mesh does not match its AVL file and SU2 reference.

    Checks, for any wing that can be written as ``upper``/``lower`` patches plus an AVL
    file and an SU2 cfg:

    * span-axis incidence at the root, the intermediate stations and the tip, against
      the AVL Ainc (linear in leading-edge arc length between SECTION cards);
    * axes: span toward +y, thickness along z, chord toward +x, angle of attack in the
      x-z plane (``SIDESLIP_ANGLE`` = 0), symmetry plane y = 0;
    * ``REF_ORIGIN_MOMENT`` against the AVL moment reference, mesh planform area and
      span against Sref and Bref, and the SU2 reference area and length against those
      same values;
    * the case monitors ``MOMENT_Y``. When both CMy and the AVL Cm are supplied and
      nonzero, they must share a sign. A missing or zero moment is ``nao_avaliado``:
      that is not a pass, and it does not by itself block the first run, because the
      RANS coefficient does not exist yet.

    A failed check raises :class:`WingGeometryError` and the caller must not start SU2.
    ``pode_correr`` is true only when no check failed. ``aprovacao_completa`` is true
    only when every check, including the moment sign, passed.
    """
    parsed = parse_avl_geometry(avl_text)
    wing = _select_surface(parsed, surface)
    sections = wing["sections"]
    measured = measure_wing_sections(patches, sections)
    stations = measured["stations"]
    checks = []

    # --- incidence ---
    roles = {s["papel"] for s in stations}
    missing_roles = [r for r in ("raiz", "intermedia", "ponta") if r not in roles]
    worst = 0.0
    le_worst = 0.0
    bad_station = None
    for s in stations:
        err = abs(s["incidencia_deg"] - s["ainc_avl_deg"])
        s["erro_deg"] = s["incidencia_deg"] - s["ainc_avl_deg"]
        s["dentro_da_tolerancia"] = bool(err <= INCIDENCE_TOL_DEG and s["le_distance_m"] <= LE_MATCH_TOL_M)
        worst = max(worst, err)
        le_worst = max(le_worst, s["le_distance_m"])
        if not s["dentro_da_tolerancia"] and bad_station is None:
            bad_station = s
    if missing_roles or bad_station is not None:
        if missing_roles:
            nomes = {"raiz": "raiz", "intermedia": "intermédia", "ponta": "ponta"}
            motivo = ("a malha não tem secção " + ", ".join(nomes[r] for r in missing_roles)
                      + "; uma secção em falta não é aprovação")
        else:
            motivo = (f"incidência ou bordo de ataque fora da tolerância na estação "
                      f"{bad_station['papel']} j={bad_station['j']}: "
                      f"malha {bad_station['incidencia_deg']:.4f}° contra Ainc "
                      f"{bad_station['ainc_avl_deg']:.4f}° "
                      f"(tolerância {INCIDENCE_TOL_DEG:g}°; distância do bordo de ataque "
                      f"{bad_station['le_distance_m']:.3e} m, tolerância {LE_MATCH_TOL_M:g} m)")
        checks.append(_check("incidencia", "falha", motivo, erro_max_deg=worst,
                             le_distance_max_m=le_worst))
    else:
        checks.append(_check(
            "incidencia", "passa",
            f"raiz, secções intermédias e ponta dentro de {INCIDENCE_TOL_DEG:g}° do Ainc",
            erro_max_deg=worst, le_distance_max_m=le_worst))

    from .control_surface import deflection_checks
    checks.extend(deflection_checks(patches))

    # --- axes ---
    root, tip = stations[0], stations[-1]
    dy = tip["le_m"][1] - root["le_m"][1]
    if dy > SYMMETRY_Y_TOL_M:
        checks.append(_check("eixo_envergadura_y", "passa",
                             f"a ponta está a +y da raiz (Δy = {dy:.4f} m)"))
    else:
        checks.append(_check("eixo_envergadura_y", "falha",
                             f"a envergadura não aponta para +y (Δy da raiz à ponta = {dy:.4f} m)"))
    thick_ok = True
    thick_note = ""
    for label, j in (("raiz", 0), ("meio", len(stations) // 2), ("ponta", len(stations) - 1)):
        sep = _skin_separation(np.asarray(patches["upper"], float),
                               np.asarray(patches["lower"], float), j)
        ax = [abs(float(sep[0])), abs(float(sep[1])), abs(float(sep[2]))]
        if not (ax[2] > ax[0] and ax[2] > ax[1] and ax[2] > 1.0e-6):
            thick_ok = False
            thick_note = (f"na {label} a separação entre peles é "
                          f"({sep[0]:.4e}, {sep[1]:.4e}, {sep[2]:.4e}) m; a maior componente não é z")
            break
    checks.append(_check("eixo_sustentacao_z", "passa" if thick_ok else "falha",
                         "a espessura da secção está no eixo z" if thick_ok else thick_note))
    chord_ok = all(s["chord_x_m"] > 0.0 for s in stations)
    checks.append(_check(
        "eixo_corda_x", "passa" if chord_ok else "falha",
        "a corda aponta para +x" if chord_ok else "há uma corda com componente x ≤ 0; o eixo x não é para trás"))
    sideslip = _cfg_float(cfg_text, "SIDESLIP_ANGLE")
    aoa = _cfg_float(cfg_text, "AOA")
    if sideslip is None or aoa is None:
        checks.append(_check("eixo_aoa_xz", "falha",
                             "AOA ou SIDESLIP_ANGLE em falta; não se assume zero"))
    elif abs(sideslip) > SIDESLIP_TOL_DEG:
        checks.append(_check("eixo_aoa_xz", "falha",
                             f"SIDESLIP_ANGLE = {sideslip:g}°; o AOA não está no plano x-z"))
    else:
        checks.append(_check("eixo_aoa_xz", "passa",
                             "SIDESLIP_ANGLE é 0, logo o AOA do caso é a rotação no plano x-z"))

    # --- symmetry ---
    root_le_y = abs(root["le_m"][1])
    avl_root_y = abs(float(sections[0]["le"][1]))
    has_sym = _cfg_raw(cfg_text, "MARKER_SYM") is not None
    le_on_plane = root_le_y <= SYMMETRY_Y_TOL_M and avl_root_y <= SYMMETRY_Y_TOL_M
    starboard = all(s["le_m"][1] >= -SYMMETRY_Y_TOL_M for s in stations)
    if has_sym and le_on_plane and starboard:
        checks.append(_check(
            "simetria_y0", "passa",
            "bordo de ataque da raiz em y = 0, meia asa em y ≥ 0 e MARKER_SYM presente",
            raiz_le_y_m=root["le_m"][1], raiz_te_y_m=root["te_m"][1]))
    else:
        bits = []
        if not has_sym:
            bits.append("MARKER_SYM em falta")
        if not le_on_plane:
            bits.append(f"bordo de ataque da raiz em y = {root['le_m'][1]:.4e} m "
                        f"(AVL {sections[0]['le'][1]:.4e} m)")
        if not starboard:
            bits.append("há uma secção com bordo de ataque em y < 0")
        checks.append(_check("simetria_y0", "falha", "; ".join(bits),
                             raiz_le_y_m=root["le_m"][1], raiz_te_y_m=root["te_m"][1]))

    # --- moment origin. A missing component is not zero. ---
    origin = {k: _cfg_float(cfg_text, f"REF_ORIGIN_MOMENT_{k}") for k in ("X", "Y", "Z")}
    avl_origin = {"X": parsed["Xref"], "Y": parsed["Yref"], "Z": parsed["Zref"]}
    missing = [k for k, v in origin.items() if v is None]
    if missing:
        checks.append(_check(
            "ref_origin", "falha",
            "REF_ORIGIN_MOMENT_" + ", ".join(missing) + " em falta; não se assume zero",
            cfg=origin, avl=avl_origin))
    else:
        deltas = {k: origin[k] - avl_origin[k] for k in "XYZ"}
        if all(abs(deltas[k]) <= MOMENT_ORIGIN_TOL_M for k in "XYZ"):
            checks.append(_check(
                "ref_origin", "passa",
                f"REF_ORIGIN_MOMENT coincide com Xref/Yref/Zref dentro de {MOMENT_ORIGIN_TOL_M:g} m",
                cfg=origin, avl=avl_origin, delta_m=deltas))
        else:
            checks.append(_check(
                "ref_origin", "falha",
                "REF_ORIGIN_MOMENT não coincide com o Xref/Yref/Zref do AVL: Δ = "
                + ", ".join(f"{k} {deltas[k]:+.4e} m" for k in "XYZ"),
                cfg=origin, avl=avl_origin, delta_m=deltas))

    # --- area and span ---
    try:
        area_one = _panel_area(measured, measured["section_eta"])
    except ValueError as exc:
        area_one = float("nan")
        area_note = str(exc)
    else:
        area_note = ""
    ydup = bool(wing["yduplicate"])
    area_ref = 2.0 * area_one if ydup else area_one
    ys = np.concatenate([
        np.asarray(patches["upper"], float)[..., 1].ravel(),
        np.asarray(patches["lower"], float)[..., 1].ravel(),
    ])
    if ydup:
        span = 2.0 * float(np.max(np.abs(ys)))
    else:
        span = float(np.max(ys) - np.min(ys))
    if area_note:
        checks.append(_check("area_sref", "falha", area_note, area_malha_m2=None, Sref_m2=parsed["Sref"]))
    elif parsed["Sref"] == 0.0 or not _rel_ok(area_ref, parsed["Sref"], AREA_RTOL, 0.0):
        motivo = (f"Sref é zero; não é uma aprovação" if parsed["Sref"] == 0.0
                  else (f"área da malha {area_ref:.6g} m² contra Sref {parsed['Sref']:.6g} m² "
                        f"(tolerância relativa {AREA_RTOL:g}"
                        + ("; YDUPLICATE, área da meia asa a dobrar" if ydup else "") + ")"))
        checks.append(_check("area_sref", "falha", motivo, area_malha_m2=area_ref, Sref_m2=parsed["Sref"]))
    else:
        checks.append(_check(
            "area_sref", "passa",
            f"área da malha {area_ref:.6g} m² dentro de {AREA_RTOL:.3g} de Sref",
            area_malha_m2=area_ref, Sref_m2=parsed["Sref"]))
    if parsed["Bref"] == 0.0 or not _rel_ok(span, parsed["Bref"], SPAN_RTOL, 0.0):
        motivo = ("Bref é zero; não é uma aprovação" if parsed["Bref"] == 0.0
                  else f"envergadura da malha {span:.6g} m contra Bref {parsed['Bref']:.6g} m "
                       f"(tolerância relativa {SPAN_RTOL:g})")
        checks.append(_check("envergadura_bref", "falha", motivo, envergadura_m=span, Bref_m=parsed["Bref"]))
    else:
        checks.append(_check(
            "envergadura_bref", "passa",
            f"envergadura da malha {span:.6g} m dentro de {SPAN_RTOL:.3g} de Bref",
            envergadura_m=span, Bref_m=parsed["Bref"]))

    ref_area = _cfg_float(cfg_text, "REF_AREA")
    expected_area = parsed["Sref"] / 2.0 if ydup else parsed["Sref"]
    if ref_area is None:
        checks.append(_check("ref_area", "falha", "REF_AREA em falta; não se assume zero",
                             esperado_m2=expected_area))
    elif not _rel_ok(ref_area, expected_area, REF_AREA_RTOL, 0.0):
        checks.append(_check(
            "ref_area", "falha",
            f"REF_AREA {ref_area:.6g} m² contra {expected_area:.6g} m² "
            f"({'Sref/2, meia asa' if ydup else 'Sref, sem YDUPLICATE'})",
            medido_m2=ref_area, esperado_m2=expected_area))
    else:
        checks.append(_check("ref_area", "passa",
                             f"REF_AREA {ref_area:.6g} m² coincide com a referência do AVL",
                             medido_m2=ref_area, esperado_m2=expected_area))
    ref_length = _cfg_float(cfg_text, "REF_LENGTH")
    if ref_length is None:
        checks.append(_check("ref_length", "falha", "REF_LENGTH em falta; não se assume zero"))
    elif abs(ref_length - parsed["Cref"]) > REF_LENGTH_TOL_M:
        checks.append(_check(
            "ref_length", "falha",
            f"REF_LENGTH {ref_length:.6g} m contra Cref {parsed['Cref']:.6g} m",
            medido_m=ref_length, Cref_m=parsed["Cref"]))
    else:
        checks.append(_check("ref_length", "passa",
                             f"REF_LENGTH dentro de {REF_LENGTH_TOL_M:g} m da Cref",
                             medido_m=ref_length, Cref_m=parsed["Cref"]))

    # --- pitch moment axis and, when both numbers exist, the sign ---
    body = _cfg_body(cfg_text)
    monitors_cmy = "MOMENT_Y" in body
    checks.append(_check(
        "eixo_momento_y", "passa" if monitors_cmy else "falha",
        "o caso monitoriza MOMENT_Y, o momento de picada com estes eixos"
        if monitors_cmy else "MOMENT_Y não está no caso; o momento de picada não é o CMy"))
    solver = _cfg_raw(cfg_text, "SOLVER")
    if solver is None or "RANS" not in solver.upper():
        checks.append(_check("solver_rans", "falha",
                             "SOLVER não é RANS" if solver else "SOLVER em falta; não se assume RANS"))
    else:
        checks.append(_check("solver_rans", "passa", f"SOLVER = {solver}"))

    try:
        cmy_f = None if cmy is None else float(cmy)
        cm_f = None if cm_avl is None else float(cm_avl)
    except (TypeError, ValueError):
        cmy_f, cm_f = float("nan"), float("nan")
    if cmy is None or cm_avl is None:
        sign_status, sign_motivo = "nao_avaliado", (
            "CMy do RANS ou Cm do AVL em falta; não avaliado não é aprovação")
    elif not (math.isfinite(cmy_f) and math.isfinite(cm_f)):
        sign_status, sign_motivo = "falha", "CMy ou Cm não finito"
    elif cmy_f == 0.0 or cm_f == 0.0:
        sign_status, sign_motivo = "nao_avaliado", (
            "um dos momentos é zero; o sinal não se compara e zero não é aprovação")
    elif cmy_f * cm_f > 0.0:
        sign_status, sign_motivo = "passa", "CMy e o Cm do AVL têm o mesmo sinal"
    else:
        sign_status, sign_motivo = "falha", "CMy e o Cm do AVL têm sinais opostos"
    sign = _check("sinal_cmy", sign_status, sign_motivo, cmy=cmy, cm_avl=cm_avl)
    # A moment that was not computed does not block the first run. A computed disagreement does.
    if sign_status == "nao_avaliado":
        sign["bloqueia"] = False
    checks.append(sign)

    report = {
        "surface": wing["name"],
        "yduplicate": ydup,
        "tolerances": {
            "incidence_deg": INCIDENCE_TOL_DEG,
            "area_rtol": AREA_RTOL,
            "span_rtol": SPAN_RTOL,
            "moment_origin_m": MOMENT_ORIGIN_TOL_M,
            "symmetry_y_m": SYMMETRY_Y_TOL_M,
            "sideslip_deg": SIDESLIP_TOL_DEG,
            "le_match_m": LE_MATCH_TOL_M,
            "ref_length_m": REF_LENGTH_TOL_M,
            "ref_area_rtol": REF_AREA_RTOL,
        },
        "pressupostos": [
            "PRESSUPOSTO: a incidência comparada com o Ainc é a rotação da corda em torno da envergadura local, com a componente x removida, como em Surface._frames. A projecção no plano x-z fica no relatório e não decide.",
            "PRESSUPOSTO: entre secções AVL o Ainc interpola-se linearmente na fracção do comprimento do bordo de ataque.",
            "PRESSUPOSTO: a área é a de planta de Surface.planform_area (corda do bordo interior de cada painel). A tampa em semicírculo não entra na área nem na envergadura.",
            "PRESSUPOSTO: com YDUPLICATE a malha é a meia asa de estibordo e Sref/Bref são os da asa completa; REF_AREA do SU2 é Sref/2. Sem YDUPLICATE compara-se a malha directamente com Sref e Bref.",
            "PRESSUPOSTO: o CMy do SU2, com x para trás, z para cima e y para estibordo, compara-se em sinal com o Cmtot do AVL. Sem os dois números o sinal fica nao_avaliado.",
        ] + ([
            "PRESSUPOSTO: com um flap selado, a incidência e a área usam o bordo de fuga alinhado, guardado antes da rotação. O ângulo do flap é a rotação em torno do ponto da linha de corda na coluna da charneira e não entra no Ainc.",
        ] if patches.get("controls") else []),
        "sections": [{k: v for k, v in s.items()} for s in stations],
        "checks": checks,
        "pode_correr": not any(c["bloqueia"] for c in checks),
        "aprovacao_completa": all(c["status"] == "passa" for c in checks),
    }
    if not report["pode_correr"]:
        raise WingGeometryError(report)
    return report
