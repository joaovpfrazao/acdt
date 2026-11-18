"""AVL (Drela & Youngren, MIT; GPL-2.0) adapter — vortex-lattice analysis of the parametric geometry.

AVL is used **only as an external program** (input file + keystroke script, output files parsed),
never linked or bundled, so the licence of acdt is unaffected (THIRD_PARTY.md).
File formats and commands: *AVL 3.40 User Primer* (``avl_doc.txt``), Sections "Input files",
"OPER", "ST"/"FS"/"FT" output.

What is extracted for one trimmed or untrimmed operating point:

* CL, CDi (Trefftz plane), span efficiency e, Cm about the reference point;
* stability-axis derivatives (CLα, Cmα, CYβ, Clβ, Cnβ, CLq, Cmq, Clp, Cnr, ...),
  stick-fixed neutral point ``Xnp`` (AVL ST output);
* control derivatives per declared control (flap, aileron, elevator, rudder);
* spanwise strip loading of the wing (y, chord, c·cl, cl) — used by structures.py
  as a cross-check of the Schrenk distribution.

Control-surface layout (ASSUMPTIONS, typical values in Raymer 6th ed. Sec. 6.5 / Fig. 6.3:
aileron over the outer ~35–40 % of the semispan with 20–25 % chord; elevator/rudder
25–50 % chord) is given by :class:`ControlLayout` and is reported.
"""
from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .interfaces import ToolNotAvailable, _naca_digits


@dataclass
class ControlLayout:
    aileron_span_fraction: float = 0.35   # outer fraction of semispan (Raymer Fig. 6.3 guideline)
    aileron_hinge_xc: float = 0.75        # 25 % chord aileron
    flap_hinge_xc: float = 0.75           # inboard of the aileron
    elevator_hinge_xc: float = 0.70       # 30 % chord elevator
    rudder_hinge_xc: float = 0.65         # 35 % chord rudder
    wing_incidence_deg: float = 0.0


def wing_x_ac(w) -> float:
    """Quarter-MAC x position measured from the wing root leading edge (Raymer Eq. 7.6 station)."""
    return w.y_mac * math.tan(w.sweep_at(0.0)) + 0.25 * w.mac


def write_avl_file(config, path: str | Path, name: str = "acdt", mach: float = 0.0, x_ref: float | None = None,
                   cd0: float = 0.0, nchord: int = 10, nspan: int = 20, controls: ControlLayout | None = None,
                   tail_airfoil: str = "0012", fin_airfoil: str = "0010", wing_twist_deg=None) -> Path:
    """Write the AVL geometry: wing (flap + aileron panels), horizontal tail (elevator),
    vertical tail (rudder). x aft from wing root LE, y right, z up (AVL convention).
    ``x_ref`` is the moment reference / CG (default: wing quarter-MAC).
    ``wing_twist_deg(y)`` is the nose-up elastic twist [deg] at semispan station y [m], written as
    the SECTION incidence (positive nose up, AVL ``ainc``). Tails stay at zero."""
    c = controls or ControlLayout()
    w, ht, vt = config.wing, config.htail.as_wing(), config.vtail.as_wing()
    x_ac = wing_x_ac(w)
    x_ref = x_ac if x_ref is None else x_ref
    x_ht = x_ac + config.htail.arm - (0.25 * ht.mac + ht.y_mac * math.tan(ht.sweep_at(0.0)))
    x_vt = x_ac + config.vtail.arm - 0.25 * vt.mac
    af = _naca_digits(w.airfoil)

    def ainc_at(y: float) -> float:
        return 0.0 if wing_twist_deg is None else float(wing_twist_deg(y))

    def sec(xle, yle, zle, chord, digits, ctrl="", ainc=0.0):
        s = f"SECTION\n{xle:.5f} {yle:.5f} {zle:.5f} {chord:.5f} {ainc:.5f}\n"
        if digits:
            s += f"NACA\n{digits}\n"
        return s + ctrl

    b2 = w.span / 2
    tanle, tand = math.tan(w.sweep_at(0.0)), math.tan(w.dihedral)
    ya = (1 - c.aileron_span_fraction) * b2
    ca = w.c_root + (w.c_tip - w.c_root) * ya / b2
    flap = f"CONTROL\nflap 1.0 {c.flap_hinge_xc:.3f} 0. 1. 0. 1.0\n"
    ail = f"CONTROL\naileron 1.0 {c.aileron_hinge_xc:.3f} 0. 1. 0. -1.0\n"
    out = [f"{name}\n{mach:.3f}\n0 0 0.0\n{w.S:.5f} {w.mac:.5f} {w.span:.5f}\n{x_ref:.5f} 0.0 0.0\n{cd0:.5f}\n"]
    out.append(f"SURFACE\nWing\n{nchord} 1.0 {nspan} -2.0\nCOMPONENT\n1\nYDUPLICATE\n0.0\n"
               f"ANGLE\n{c.wing_incidence_deg:.3f}\n")
    out.append(sec(0, 0, 0, w.c_root, af, flap, ainc_at(0.0)))
    out.append(sec(ya * tanle, ya, ya * tand, ca, af, flap + ail, ainc_at(ya)))
    out.append(sec(b2 * tanle, b2, b2 * tand, w.c_tip, af, ail, ainc_at(b2)))
    hb2 = ht.span / 2
    ele = f"CONTROL\nelevator 1.0 {c.elevator_hinge_xc:.3f} 0. 1. 0. 1.0\n"
    out.append(f"SURFACE\nHtail\n{nchord} 1.0 {max(nspan // 2, 6)} -2.0\nCOMPONENT\n2\nYDUPLICATE\n0.0\nANGLE\n0.0\n")
    out.append(sec(x_ht, 0, 0, ht.c_root, tail_airfoil, ele))
    out.append(sec(x_ht + hb2 * math.tan(ht.sweep_at(0.0)), hb2, 0, ht.c_tip, tail_airfoil, ele))
    vh = config.vtail.S / ((vt.c_root + vt.c_tip) / 2)  # single fin height
    rud = f"CONTROL\nrudder 1.0 {c.rudder_hinge_xc:.3f} 0. 0. 1. 1.0\n"
    out.append(f"SURFACE\nVtail\n{nchord} 1.0 {max(nspan // 2, 6)} -2.0\nCOMPONENT\n3\n")
    out.append(sec(x_vt, 0, 0, vt.c_root, fin_airfoil, rud))
    out.append(sec(x_vt + vh * math.tan(vt.sweep_at(0.0)), 0, vh, vt.c_tip, fin_airfoil, rud))
    p = Path(path)
    p.write_text("".join(out))
    return p


CONTROL_NAMES = ("flap", "aileron", "elevator", "rudder")  # AVL control index d1..d4 in this order


@dataclass
class AVLResult:
    alpha_deg: float
    CL: float
    CDi: float
    e: float
    Cm: float
    x_ref: float
    Xnp: float
    derivatives: dict[str, float] = field(default_factory=dict)
    controls: dict[str, dict[str, float]] = field(default_factory=dict)  # per control, per radian
    deflections_deg: dict[str, float] = field(default_factory=dict)
    strips: list[dict] = field(default_factory=list)  # wing strips (both halves), y ascending
    mach: float = 0.0
    source: str = "AVL 3.40 (Drela & Youngren), vortex lattice"
    hinge: dict[str, float] = field(default_factory=dict)  # Chinge per control (ref. Sref·Cref), if requested
    CD_tot: float = float("nan")  # CDtot (inviscid + profile cd0 of the AVL file)
    surfaces: dict[str, dict] = field(default_factory=dict)  # per surface: CL (ref. Sref), CL_surf (ref. own area)

    @property
    def CLalpha(self) -> float:
        return self.derivatives["CLa"]

    @property
    def Cmalpha(self) -> float:
        return self.derivatives["Cma"]


_NUM = r"(-?\d+\.?\d*(?:[EeDd][+-]?\d+)?|NaN|\*+)"


def _grab(text: str, key: str) -> float:
    m = re.search(rf"(?<![\w']){re.escape(key)}\s*=\s*{_NUM}", text)
    if not m:
        raise KeyError(key)
    v = m.group(1)
    return float("nan") if v.startswith("*") else float(v.replace("D", "E"))


def _parse_strips(fs: str, surface_names=("Wing", "Wing (YDUP)")) -> list[dict]:
    strips = []
    blocks = re.split(r"\n\s*Surface #\s*\d+\s+", fs)
    for blk in blocks[1:]:
        name = blk.splitlines()[0].strip()
        if name not in surface_names:
            continue
        rows = blk.split("Strip Forces referred to Strip Area, Chord")[1].splitlines()[2:]
        for ln in rows:
            parts = ln.split()
            if len(parts) < 10 or not parts[0].isdigit():
                break
            strips.append({"y": float(parts[2]), "chord": float(parts[4]), "area": float(parts[5]),
                           "c_cl": float(parts[6]), "cl": float(parts[9]), "cm_c4": float(parts[12])})
    return sorted(strips, key=lambda s: s["y"])


def _parse_surfaces(fs: str) -> dict[str, dict]:
    """Per-surface lift from the FS output, YDUPLICATE halves merged (CL on Sref summed; CL_surf on the
    surface's own area averaged by area)."""
    out: dict[str, dict] = {}
    blocks = re.split(r"\n\s*Surface #\s*\d+\s+", fs)
    for blk in blocks[1:]:
        name = blk.splitlines()[0].strip().replace(" (YDUP)", "")
        try:
            area = _grab(blk, "Ssurf")
            cls = re.findall(rf"CLsurf\s*=\s*{_NUM}", blk)
        except KeyError:
            continue
        if len(cls) < 2:
            continue
        d = out.setdefault(name, {"CL": 0.0, "area": 0.0, "_cla": 0.0})
        d["CL"] += float(cls[0])
        d["area"] += area
        d["_cla"] += float(cls[1]) * area
    for d in out.values():
        d["CL_surf"] = d.pop("_cla") / d["area"] if d["area"] else float("nan")
    return out


def avl_available(exe: str = "avl") -> bool:
    return shutil.which(exe) is not None


def run_avl_case(config, CL: float | None = None, alpha_deg: float | None = None, mach: float = 0.0,
                 x_ref: float | None = None, trim_elevator: bool = False, deflections: dict | None = None,
                 controls: ControlLayout | None = None, exe: str = "avl", timeout: float = 60,
                 keep_dir: str | Path | None = None, hinge_moments: bool = False,
                 wing_twist_deg=None) -> AVLResult:
    """Run one AVL operating point on the parametric geometry and parse ST/FS output.

    Either ``CL`` (alpha found by AVL to match it) or ``alpha_deg`` is given. With
    ``trim_elevator`` the elevator is set by AVL for Cm = 0 about ``x_ref``. ``hinge_moments`` also writes
    the AVL ``HM`` output: inviscid hinge-moment coefficients Chinge = H/(q Sref Cref) per control (sum over the
    duplicated halves, with the control gains)."""
    exe_path = shutil.which(exe)
    if exe_path is None:
        raise ToolNotAvailable("AVL binary not found on PATH (build: docs/ARCHITECTURE.md §6 / THIRD_PARTY.md)")
    tmp = Path(keep_dir) if keep_dir else Path(tempfile.mkdtemp(prefix="acdt_avl_"))
    tmp.mkdir(parents=True, exist_ok=True)
    geo = write_avl_file(config, tmp / "model.avl", mach=mach, x_ref=x_ref, controls=controls,
                         wing_twist_deg=wing_twist_deg)
    cmds = ["oper"]
    if CL is not None:
        cmds.append(f"a c {CL:.6f}")
    else:
        cmds.append(f"a a {alpha_deg if alpha_deg is not None else 0.0:.6f}")
    for i, nm in enumerate(CONTROL_NAMES, start=1):
        if trim_elevator and nm == "elevator":
            cmds.append(f"d{i} pm 0")
        elif deflections and nm in deflections:
            cmds.append(f"d{i} d{i} {deflections[nm]:.4f}")
    cmds += [f"m\nmn {mach:.4f}\n", "x", "st", str(tmp / "st.txt"), "fs", str(tmp / "fs.txt")]
    if hinge_moments:
        cmds += ["hm", str(tmp / "hm.txt")]
    cmds += ["", "quit"]
    for f in ("st.txt", "fs.txt", "hm.txt"):
        (tmp / f).unlink(missing_ok=True)
    from acdt.core.provenance import tool_used
    tool_used("avl", exe_path)
    r = subprocess.run([exe_path, geo.name], input="\n".join(cmds) + "\n", capture_output=True, text=True,
                       timeout=timeout, cwd=tmp)
    if not (tmp / "st.txt").exists():
        raise RuntimeError(f"AVL failed (no ST output). Last output:\n{r.stdout[-1500:]}")
    st, fs = (tmp / "st.txt").read_text(encoding="utf-8"), (tmp / "fs.txt").read_text(encoding="utf-8")
    der = {}
    for k in ("CLa", "CYb", "Clb", "Cma", "Cnb", "CLq", "Cmq", "Clp", "Cnp", "Clr", "Cnr", "CYr", "CYp", "CYq"):
        try:
            der[k] = _grab(st, k)
        except KeyError:
            pass
    ctrl, defl = {}, {}
    for i, nm in enumerate(CONTROL_NAMES, start=1):
        d = {}
        for coef in ("CL", "CY", "Cl", "Cm", "Cn", "CD"):
            key = f"{coef}d{i:02d}" if coef != "CD" else f"CDffd{i:02d}"
            try:
                d[coef] = _grab(st, key) * 180 / math.pi  # AVL control derivatives are per degree
            except KeyError:
                pass
        ctrl[nm] = d
        try:
            defl[nm] = _grab(st, nm)
        except KeyError:
            pass
    hinge = {}
    if hinge_moments and (tmp / "hm.txt").exists():
        for ln in (tmp / "hm.txt").read_text(encoding="utf-8").splitlines():
            parts = ln.split()
            if len(parts) == 2 and parts[0] in CONTROL_NAMES:
                hinge[parts[0]] = float(parts[1].replace("D", "E"))
    res = AVLResult(_grab(st, "Alpha"), _grab(st, "CLtot"), _grab(st, "CDff"), _grab(st, "e"), _grab(st, "Cmtot"),
                    _grab(st, "Xref"), _grab(st, "Xnp"), der, ctrl, defl, _parse_strips(fs), mach, hinge=hinge,
                    CD_tot=_grab(st, "CDtot"), surfaces=_parse_surfaces(fs))
    if not keep_dir:
        shutil.rmtree(tmp, ignore_errors=True)
    return res
