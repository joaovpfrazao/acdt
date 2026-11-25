"""Parametric structure for manufacture: a JSON spec, a DXF drawing, and a STEP assembly.

The STEP file is written by :file:`cad_build.py` in another process. That process is the one that
imports CadQuery and therefore OpenCASCADE (LGPL). This module does not import either.

What is drawn is the structure already defined for the size loop, not a new loft of the outer
mould line. The outer surface stays the OpenVSP STEP when the caller passes one (``oml_step``);
without OpenVSP the assembly is the structure alone.

* Wing, stabiliser and fin: skins, spars and ribs. The section is the NACA 4-digit thickness
  (Abbott & von Doenhoff 1959, Eq. 6.2) between the spar fractions of :class:`WingBoxLayout`
  (Niu 1988 Ch. 8). Skin gauge is ``skin_thickness``. The spar web is the material minimum
  ``t_min_web``. Thickness is applied vertically, not along the surface normal (PRESSUPOSTO).
* Fuselage: frames at ``frame_pitch`` on the same equivalent radius as the L1 beam, and four
  longerons of square side √(cap_min_area). No pressure shell, no doors.
* Drawing: one DXF, millimetres, planform plus the root wing-box section. Not a dimensioned
  production sheet.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from .aero.avl import wing_x_ac
from .structures import MATERIALS, naca4_half_thickness
from .structures_l1 import _radius

_BUILD = Path(__file__).with_name("cad_build.py")
_FRAME_DEPTH_M = 0.025   # Niu Ch. 11, same flange used by the L1 mass model
_FRAME_WIDTH_M = 0.008   # axial thickness of the drawn frame. PRESSUPOSTO, so the ring is a solid.


def _ys(half_span: float, pitch: float) -> list[float]:
    if pitch <= 0 or half_span <= 0:
        return [0.0, half_span]
    ys = [0.0]
    y = pitch
    while y < half_span - 0.25 * pitch:
        ys.append(y)
        y += pitch
    if ys[-1] != half_span:
        ys.append(half_span)
    return ys


def _quad(wing, y: float, origin, vertical: bool, t_skin: float, t_web: float):
    """Closed sections of the upper skin, lower skin, front spar and rear spar at station ``y``."""
    b2 = wing.span / 2.0
    frac = min(abs(y) / b2, 1.0) if b2 else 0.0
    chord = wing.c_root + (wing.c_tip - wing.c_root) * frac
    tc = wing.tc_root + (wing.tc_tip - wing.tc_root) * frac
    x_le = abs(y) * math.tan(wing.sweep_at(0.0))
    z_le = abs(y) * math.tan(wing.dihedral)
    box = wing.box

    def xyz(xc: float, z_off: float) -> list[float]:
        x = x_le + xc * chord
        z = z_le + z_off
        if vertical:
            return [origin[0] + x, origin[1] + z, origin[2] + y]
        return [origin[0] + x, origin[1] + y, origin[2] + z]

    def half(xc: float) -> float:
        return float(naca4_half_thickness(xc, tc)) * chord

    front, rear = box.front_spar_xc, box.rear_spar_xc
    zf, zr = half(front), half(rear)
    upper = [xyz(front, zf), xyz(rear, zr), xyz(rear, zr - t_skin), xyz(front, zf - t_skin)]
    lower = [xyz(front, -zf), xyz(front, -zf + t_skin), xyz(rear, -zr + t_skin), xyz(rear, -zr)]
    front_spar = [xyz(front, zf - t_skin), xyz(front, -zf + t_skin),
                  xyz(front + t_web / chord, -zf + t_skin), xyz(front + t_web / chord, zf - t_skin)]
    rear_spar = [xyz(rear - t_web / chord, zr - t_skin), xyz(rear - t_web / chord, -zr + t_skin),
                 xyz(rear, -zr + t_skin), xyz(rear, zr - t_skin)]
    return {"upper": upper, "lower": lower, "front": front_spar, "rear": rear_spar,
            "chord": chord, "x_le": x_le, "z_le": z_le}


def _loft(name: str, root_sec, tip_sec) -> dict:
    return {"name": name, "kind": "loft", "sections": [root_sec, tip_sec]}


def _surface_parts(name: str, wing, origin, vertical: bool, t_skin: float, t_web: float) -> list[dict]:
    pitch = wing.box.rib_pitch or 0.6 * wing.mac
    half = wing.span / 2.0
    sides = [1.0] if vertical else [1.0, -1.0]
    parts = []
    for sign in sides:
        side = "right" if sign > 0 else "left"
        root = _quad(wing, 0.0, origin, vertical, t_skin, t_web)
        tip = _quad(wing, sign * half, origin, vertical, t_skin, t_web)
        for key in ("upper", "lower", "front", "rear"):
            label = {"upper": "upper_skin", "lower": "lower_skin", "front": "front_spar",
                     "rear": "rear_spar"}[key]
            parts.append(_loft(f"{name}_{label}_{side}", root[key], tip[key]))
        rib_t = max(t_web, 1e-3)
        for y in _ys(half, pitch):
            if y == 0.0 and sign < 0:
                continue
            y0 = sign * y
            y1 = sign * min(half, y + rib_t)
            if abs(y1 - y0) < 1e-6:
                y0 = sign * max(0.0, y - rib_t)
            a = _quad(wing, y0, origin, vertical, t_skin, t_web)
            b = _quad(wing, y1, origin, vertical, t_skin, t_web)
            # Inner box: front-upper, rear-upper, rear-lower, front-lower.
            rib = [a["upper"][3], a["upper"][2], a["lower"][2], a["lower"][1]]
            rib_b = [b["upper"][3], b["upper"][2], b["lower"][2], b["lower"][1]]
            parts.append(_loft(f"{name}_rib_{side}_y{abs(y):.2f}", rib, rib_b))
    return parts


def _draw_plan(lines, pts):
    for a, b in zip(pts, pts[1:]):
        lines.append({"layer": "plan", "a": a, "b": b})


def assembly_spec(config, *, x_wing_apex: float | None = None, wing_z: float = 0.0,
                  oml_step: str | None = None) -> dict:
    """Solids and drawing lines for one :class:`~acdt.domains.aircraft.geometry.Configuration`."""
    wing, fus = config.wing, config.fuselage
    mat = MATERIALS.get(wing.box.material, MATERIALS["al2024_t3"])
    t_skin = float(wing.box.skin_thickness)
    t_web = float(mat["t_min_web"])
    x_apex = 0.35 * fus.length if x_wing_apex is None else float(x_wing_apex)
    # as_wing() inherits the wing default dihedral. A tail is not installed at that angle.
    ht = replace(config.htail.as_wing(), dihedral=0.0)
    vt = replace(config.vtail.as_wing(), dihedral=0.0)
    x_ac = wing_x_ac(wing)
    x_ht = x_ac + config.htail.arm - (0.25 * ht.mac + ht.y_mac * math.tan(ht.sweep_at(0.0)))
    x_vt = x_ac + config.vtail.arm - 0.25 * vt.mac
    parts = _surface_parts("wing", wing, (0.0, 0.0, wing_z), False, t_skin, t_web)
    parts += _surface_parts("htail", ht, (x_ht, 0.0, 0.0), False, t_skin, t_web)
    parts += _surface_parts("vtail", vt, (x_vt, 0.0, 0.0), True, t_skin, t_web)

    L, R = fus.length, fus.max_diameter / 2.0
    xs = np.arange(0.0, L + 1e-9, fus.frames.frame_pitch)
    if len(xs) == 0 or xs[-1] < L - 1e-6:
        xs = np.append(xs, L)
    radii = _radius(xs, L, R, getattr(fus, "profile", None))
    nose = -x_apex
    for i, (x, radius) in enumerate(zip(xs, radii)):
        parts.append({"name": f"fuselage_frame_{i:03d}", "kind": "ring", "x": float(nose + x),
                      "R": float(radius), "t_radial": _FRAME_DEPTH_M, "width": _FRAME_WIDTH_M})
    side = math.sqrt(float(mat["cap_min_area"]))
    for k, ang in enumerate((45.0, 135.0, 225.0, 315.0)):
        rad = math.radians(ang)
        r_in = max(float(np.min(radii)) - _FRAME_DEPTH_M - side, 0.05)
        parts.append({"name": f"longeron_{k}", "kind": "rod", "x0": float(nose), "x1": float(nose + L),
                      "y": r_in * math.cos(rad), "z": r_in * math.sin(rad), "side": side})

    lines = []
    root = _quad(wing, 0.0, (0.0, 0.0, wing_z), False, t_skin, t_web)
    tip = _quad(wing, wing.span / 2.0, (0.0, 0.0, wing_z), False, t_skin, t_web)
    _draw_plan(lines, [root["upper"][0][:2], tip["upper"][0][:2], tip["upper"][1][:2], root["upper"][1][:2],
                       root["upper"][0][:2]])
    _draw_plan(lines, [root["front"][0][:2], tip["front"][0][:2]])
    _draw_plan(lines, [root["rear"][0][:2], tip["rear"][0][:2]])
    _draw_plan(lines, [[nose, -R], [nose + L, -R], [nose + L, R], [nose, R], [nose, -R]])
    # Root section, drawn beside the planform. x is chordwise, y is up.
    gap = wing.span / 2.0 + 1.0
    section = [root["upper"][0], root["upper"][1], root["lower"][3], root["lower"][0], root["upper"][0]]
    for a, b in zip(section, section[1:]):
        lines.append({"layer": "section",
                      "a": [a[0] + gap, a[2]], "b": [b[0] + gap, b[2]]})
    notes = [
        "Espessura do revestimento = WingBoxLayout.skin_thickness; alma da longarina = t_min_web do material. "
        "Não é a espessura dimensionada por encurvadura.",
        "A espessura é aplicada na vertical, não segundo a normal do perfil (PRESSUPOSTO).",
        "A fuselagem desenhada são as cavernas e as longarinas. A casca exterior continua a ser o STEP do "
        "OpenVSP quando esse ficheiro é passado; sem OpenVSP a montagem é só a estrutura.",
        f"Estação do ápice da asa: x = {x_apex:.3f} m a partir do nariz (o nariz do desenho fica em {-x_apex:.3f} m).",
    ]
    return {"units": "m", "parts": parts, "drawing": lines, "oml_step": oml_step, "notes": notes,
            "span_m": wing.span, "root_box_chord_m": (wing.box.rear_spar_xc - wing.box.front_spar_xc) * wing.c_root,
            "n_frames": int(len(xs)), "n_parts": len(parts)}


def write_dxf(spec: dict, path: str | Path) -> Path:
    """R12-style DXF, coordinates in millimetres, one LINE entity per drawing segment."""
    path = Path(path)
    chunks = ["0", "SECTION", "2", "ENTITIES"]
    for seg in spec["drawing"]:
        ax, ay = (1000.0 * float(v) for v in seg["a"])
        bx, by = (1000.0 * float(v) for v in seg["b"])
        chunks += ["0", "LINE", "8", seg["layer"], "10", f"{ax:.4f}", "20", f"{ay:.4f}", "30", "0.0",
                   "11", f"{bx:.4f}", "21", f"{by:.4f}", "31", "0.0"]
    chunks += ["0", "ENDSEC", "0", "EOF", ""]
    path.write_text("\n".join(chunks), encoding="utf-8")
    return path


def cadquery_available() -> bool:
    """True when this interpreter can import CadQuery. The import runs in a child process."""
    probe = subprocess.run([sys.executable, "-c", "import cadquery"], capture_output=True, text=True)
    return probe.returncode == 0


def export_cad(config, out: str | Path, **spec_kwargs) -> dict:
    """Write ``cad_spec.json``, ``structure.dxf`` and, when CadQuery is installed, ``structure.step``."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    spec = assembly_spec(config, **spec_kwargs)
    spec_path = out / "cad_spec.json"
    spec_path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    dxf = write_dxf(spec, out / "structure.dxf")
    result = {"spec": str(spec_path), "dxf": str(dxf), "step": None, "notes": list(spec["notes"]),
              "n_parts": spec["n_parts"]}
    if not cadquery_available():
        result["notes"].append("CadQuery não está instalado (pip install 'acdt[cad]'): o STEP não foi escrito.")
        return result
    from acdt.core.provenance import tool_used
    tool_used("python (cadquery)", sys.executable)
    run = subprocess.run([sys.executable, str(_BUILD), str(spec_path), str(out)],
                         capture_output=True, text=True)
    if run.returncode != 0:
        raise RuntimeError(f"cad_build falhou:\n{run.stderr[-2000:]}")
    result["step"] = str(out / "structure.step")
    return result


def append_gear_lines_to_drawing(drawing_lines: list, gear_lines: list[dict]) -> list:
    """Append plan/side gear strut segments (metres → same units as ``drawing``) for DXF.

    ``gear_lines`` from :func:`acdt.domains.aircraft.assembly.gear_devices.leg_drawing_lines`.
    Side view uses (x,z); plan uses (x,y). Existing drawing is wing plan in x–y millimetres later.
    """
    out = list(drawing_lines)
    for g in gear_lines or []:
        a, b = g.get("a"), g.get("b")
        if not a or not b:
            continue
        out.append({"name": f"gear_{g.get('name', 'leg')}_{g.get('view', '')}", "a": list(a), "b": list(b)})
    return out
