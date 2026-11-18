"""Interfaces to established open-source low-fidelity aerodynamic tools.

The handbook methods (lift.py / drag.py) are the first cut. These adapters
let the same :class:`acdt.domains.aircraft.geometry.Configuration` be evaluated by:

* **NeuralFoil** (MIT; Sharpe & Hansman, 2024; trained on XFOIL) — airfoil polars.
  Optional dependency ``pip install neuralfoil``.
* **XFOIL** (Drela, GPL-2.0) — airfoil panel + boundary layer; run as an external
  binary (not linked, so the licence of acdt is unaffected).
* **AVL** (Drela & Youngren, GPL-2.0) — vortex-lattice; we *write* the standard
  ``.avl`` input file (format: AVL User Primer, avl_doc.txt) and run the binary
  if found on PATH.
* **OpenVSP / VSPAERO** (NASA Open Source Agreement 1.3) — geometry + VLM/panel;
  Phase 3 adapter via the OpenVSP Python API (stub below).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class ToolNotAvailable(RuntimeError):
    pass


def neuralfoil_polar(airfoil: str, alphas_deg, Re: float, model_size: str = "large"):
    """Airfoil CL/CD/CM via NeuralFoil (``neuralfoil.get_aero_from_airfoil``; incompressible)."""
    try:
        import aerosandbox as asb  # noqa: F401
        import neuralfoil as nf
    except ImportError as e:  # pragma: no cover - optional
        raise ToolNotAvailable("pip install neuralfoil aerosandbox") from e
    import aerosandbox as asb
    af = asb.Airfoil(airfoil)
    return nf.get_aero_from_airfoil(af, alpha=alphas_deg, Re=Re, model_size=model_size)


def _naca_digits(airfoil: str) -> str | None:
    s = airfoil.upper().replace("NACA", "").strip()
    return s if s.isdigit() and len(s) in (4, 5) else None


def write_avl(config, path: str | Path, name: str = "acdt", mach: float = 0.0, x_cg: float | None = None,
              cd0: float = 0.0, nchord: int = 8, nspan: int = 16) -> Path:
    """Write an AVL geometry file (wing, horizontal & vertical tail) for ``config``.

    Coordinates: x aft from wing root LE, y right, z up (AVL convention).
    """
    import math

    w, ht, vt = config.wing, config.htail.as_wing(), config.vtail.as_wing()
    x_ac = w.y_mac * math.tan(w.sweep_at(0.0)) + 0.25 * w.mac
    x_cg = x_ac if x_cg is None else x_cg
    x_ht = x_ac + config.htail.arm - 0.25 * ht.mac - ht.y_mac * math.tan(ht.sweep_at(0.0))
    x_vt = x_ac + config.vtail.arm - 0.25 * vt.mac

    def section(xle, yle, zle, chord, af):
        d = _naca_digits(af)
        s = f"SECTION\n{xle:.4f} {yle:.4f} {zle:.4f} {chord:.4f} 0.0\n"
        return s + (f"NACA\n{d}\n" if d else "")

    out = [f"{name}\n{mach:.3f}\n0 0 0.0\n{w.S:.5f} {w.mac:.5f} {w.span:.5f}\n{x_cg:.4f} 0.0 0.0\n{cd0:.5f}\n"]
    b2 = w.span / 2
    out.append(f"SURFACE\nWing\n{nchord} 1.0 {nspan} -2.0\nYDUPLICATE\n0.0\nANGLE\n2.0\n")
    out.append(section(0, 0, 0, w.c_root, w.airfoil))
    out.append(section(b2 * math.tan(w.sweep_at(0.0)), b2, b2 * math.tan(w.dihedral), w.c_tip, w.airfoil))
    hb2 = ht.span / 2
    out.append(f"SURFACE\nHtail\n{nchord} 1.0 {nspan // 2} -2.0\nYDUPLICATE\n0.0\nANGLE\n0.0\n")
    out.append(section(x_ht, 0, 0, ht.c_root, "0012"))
    out.append(section(x_ht + hb2 * math.tan(ht.sweep_at(0.0)), hb2, 0, ht.c_tip, "0012"))
    vh = config.vtail.S / ((vt.c_root + vt.c_tip) / 2)  # height of the single fin
    out.append(f"SURFACE\nVtail\n{nchord} 1.0 {nspan // 2} -2.0\n")
    out.append(section(x_vt, 0, 0, vt.c_root, "0010"))
    out.append(section(x_vt + vh * math.tan(vt.sweep_at(0.0)), 0, vh, vt.c_tip, "0010"))
    p = Path(path)
    p.write_text("".join(out))
    return p


def run_avl(avl_file: str | Path, commands: str, exe: str = "avl", timeout: float = 60) -> str:
    """Run AVL in batch mode with a keystroke script (AVL User Primer)."""
    exe_path = shutil.which(exe)
    if exe_path is None:
        raise ToolNotAvailable("AVL binary not found on PATH (https://web.mit.edu/drela/Public/web/avl/)")
    from acdt.core.provenance import tool_used
    tool_used("avl", exe_path)
    r = subprocess.run([exe_path, str(avl_file)], input=commands, capture_output=True, text=True, timeout=timeout)
    return r.stdout


def openvsp_export(config, path: str | Path):  # pragma: no cover - Phase 3
    """Phase 3: build the OpenVSP model through the ``openvsp`` Python API
    (WingGeom/FuselageGeom with the same parameters) and run VSPAERO (VLM/panel)."""
    raise NotImplementedError("Phase 3 — OpenVSP Python API adapter (see docs/ARCHITECTURE.md §6)")

# --- AeroSandbox (MIT; Sharpe, MIT PhD thesis 2021) ---------------------------
def to_aerosandbox(config, airfoil_tail: str = "naca0012"):
    """Convert an acdt ``Configuration`` into an ``aerosandbox.Airplane`` (wing, tails, fuselage)."""
    import math

    try:
        import aerosandbox as asb
    except ImportError as e:  # pragma: no cover - optional
        raise ToolNotAvailable("pip install aerosandbox") from e
    w = config.wing
    d = _naca_digits(w.airfoil)
    af = asb.Airfoil(f"naca{d}" if d else w.airfoil)
    b2 = w.span / 2
    x_ac = w.y_mac * math.tan(w.sweep_at(0.0)) + 0.25 * w.mac
    wing = asb.Wing(name="Wing", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[0, 0, 0], chord=w.c_root, airfoil=af),
        asb.WingXSec(xyz_le=[b2 * math.tan(w.sweep_at(0.0)), b2, b2 * math.tan(w.dihedral)], chord=w.c_tip,
                     airfoil=af)])
    ht, vt = config.htail.as_wing(), config.vtail.as_wing()
    x_ht = x_ac + config.htail.arm - 0.25 * ht.mac
    x_vt = x_ac + config.vtail.arm - 0.25 * vt.mac
    taf = asb.Airfoil(airfoil_tail)
    htail = asb.Wing(name="Htail", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[x_ht, 0, 0], chord=ht.c_root, airfoil=taf),
        asb.WingXSec(xyz_le=[x_ht + ht.span / 2 * math.tan(ht.sweep_at(0.0)), ht.span / 2, 0], chord=ht.c_tip,
                     airfoil=taf)])
    h_v = config.vtail.S / ((vt.c_root + vt.c_tip) / 2)
    vtail = asb.Wing(name="Vtail", symmetric=False, xsecs=[
        asb.WingXSec(xyz_le=[x_vt, 0, 0], chord=vt.c_root, airfoil=taf),
        asb.WingXSec(xyz_le=[x_vt + h_v * math.tan(vt.sweep_at(0.0)), 0, h_v], chord=vt.c_tip, airfoil=taf)])
    f = config.fuselage
    x0 = x_ac - 0.4 * f.length  # wing quarter-MAC at 40 % of fuselage length (layout assumption)
    fus = asb.Fuselage(name="Fuselage", xsecs=[
        asb.FuselageXSec(xyz_c=[x0 + f.length * s, 0, 0], radius=f.max_diameter / 2 * r)
        for s, r in ((0, 0.05), (0.1, 0.8), (0.3, 1.0), (0.6, 0.8), (1.0, 0.2))])
    return asb.Airplane(name="acdt", xyz_ref=[x_ac, 0, 0], wings=[wing, htail, vtail], fuselages=[fus])


def aerosandbox_crosscheck(config, V: float, altitude: float, alpha_deg: float = 2.0, method: str = "vlm"):
    """Low-fidelity cross-check of the handbook aerodynamics with AeroSandbox.

    ``method='vlm'``: ``asb.VortexLatticeMethod`` (inviscid CL, CDi);
    ``method='buildup'``: ``asb.AeroBuildup`` (semi-empirical, includes viscous drag).
    Returns a dict with CL, CD (and CL_alpha estimate by finite difference)."""
    import aerosandbox as asb

    ap = to_aerosandbox(config)
    Solver = asb.VortexLatticeMethod if method == "vlm" else asb.AeroBuildup

    def solve(a):
        op = asb.OperatingPoint(atmosphere=asb.Atmosphere(altitude=altitude), velocity=V, alpha=a)
        return Solver(airplane=ap, op_point=op).run()

    import math

    import numpy as np

    def sc(x):
        return float(np.asarray(x).ravel()[0])

    r0, r1 = solve(alpha_deg), solve(alpha_deg + 1.0)
    return {"CL": sc(r0["CL"]), "CD": sc(r0["CD"]),
            "CL_alpha_per_rad": (sc(r1["CL"]) - sc(r0["CL"])) / math.radians(1.0), "method": method}


# --- WireViz (GPL-3.0) — used through its command-line tool only --------------
def render_wireviz(yaml_path: str | Path) -> Path:
    """Render a harness YAML produced by ``Harness.to_wireviz_yaml`` with the WireViz CLI."""
    exe = shutil.which("wireviz")
    if exe is None:
        raise ToolNotAvailable("pip install wireviz  (and Graphviz 'dot')")
    subprocess.run([exe, str(yaml_path)], check=True, capture_output=True)
    return Path(yaml_path).with_suffix(".svg")
