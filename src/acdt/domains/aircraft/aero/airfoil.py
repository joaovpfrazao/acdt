"""Airfoil polars: XFOIL (Drela 1989; GPL-2.0, run as an external program) with NeuralFoil
(Sharpe & Hansman 2024, MIT; neural surrogate trained on XFOIL) as the fallback.

Used for:

* section ``clmax`` / ``clmin`` at the stall Reynolds number -> wing CLmax by
  Raymer Eq. 12.15 (CLmax = 0.9 clmax cos Λ) instead of the user-assumed clmax;
* section profile drag ``cd(cl)`` at the cruise Reynolds number, integrated over the
  exposed span with the spanwise cl from AVL (or Schrenk) -> wing profile drag
  (strip theory, Anderson *Fundamentals of Aerodynamics* Sec. 5.3 / Raymer Sec. 12.5
  "airfoil-data" method), replacing the wing's flat-plate Cf·FF term;
* ``cm0`` for the wing torsion load (structures.py) and ``clα`` for the lift slope.

Transition: free (e^N, Ncrit = 9 by default), with forced transition no later than the
user's laminar-flow fraction (``aero.laminar.wing``) — consistent with the handbook
skin-friction assumption. Real-surface roughness is *not* modelled by XFOIL (optimistic
for riveted metal; Raymer Sec. 12.5 cut-off Reynolds number applies to the build-up only).
"""
from __future__ import annotations

import functools
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .interfaces import ToolNotAvailable, _naca_digits


@dataclass
class AirfoilPolar:
    airfoil: str
    Re: float
    mach: float
    alpha: np.ndarray
    cl: np.ndarray
    cd: np.ndarray
    cm: np.ndarray
    source: str
    notes: list[str] = field(default_factory=list)

    @property
    def clmax(self) -> float:
        return float(np.max(self.cl))

    @property
    def alpha_clmax(self) -> float:
        return float(self.alpha[int(np.argmax(self.cl))])

    @property
    def clmin(self) -> float:
        return float(np.min(self.cl))

    def _linear(self, lo=-2.0, hi=6.0):
        m = (self.alpha >= lo) & (self.alpha <= hi)
        if m.sum() < 3:
            m = slice(None)
        return np.polyfit(np.radians(self.alpha[m]), self.cl[m], 1)

    @property
    def cl_alpha(self) -> float:
        """Section lift slope [1/rad], linear fit over −2…6 deg."""
        return float(self._linear()[0])

    @property
    def alpha0_deg(self) -> float:
        a, b = self._linear()
        return math.degrees(-b / a)

    @property
    def cm0(self) -> float:
        return float(np.interp(0.0, self.cl, self.cm)) if np.all(np.diff(self.cl) > 0) else \
            float(self.cm[int(np.argmin(np.abs(self.cl)))])

    def cd_at_cl(self, cl):
        """Profile drag on the attached branch (between clmin and clmax), clipped at the ends."""
        i0, i1 = int(np.argmin(self.cl)), int(np.argmax(self.cl))
        c, d = self.cl[i0:i1 + 1], self.cd[i0:i1 + 1]
        order = np.argsort(c)
        return np.interp(cl, c[order], d[order])

    def cd_min(self) -> float:
        return float(np.min(self.cd))


def xfoil_available(exe: str = "xfoil") -> bool:
    return shutil.which(exe) is not None


def _xfoil_geometry_cmd(airfoil: str, tmp: Path) -> str:
    d = _naca_digits(airfoil)
    if d:
        return f"NACA {d}\n"
    # coordinates from the UIUC database bundled with AeroSandbox (MIT) when not a NACA designation
    try:
        import aerosandbox as asb
    except ImportError as e:  # pragma: no cover
        raise ToolNotAvailable(f"airfoil '{airfoil}' is not NACA 4/5-digit; pip install aerosandbox for UIUC "
                               "coordinates") from e
    xy = asb.Airfoil(airfoil).coordinates
    f = tmp / "af.dat"
    f.write_text(airfoil + "\n" + "\n".join(f"{x:.6f} {y:.6f}" for x, y in xy) + "\n")
    return f"LOAD {f}\n"


def _xfoil_flap_cmd(flap: tuple | None) -> str:
    """XFOIL GDES/FLAP: plain (sealed-gap) trailing-edge flap hinged at x/c = flap[0] on the camber line
    (y/t = 0.5), deflected flap[1] degrees (+ down), then eXecuted on the current airfoil."""
    if not flap or abs(flap[1]) < 1e-9:
        return ""
    return f"GDES\nFLAP\n{flap[0]:.4f}\n999\n0.5\n{flap[1]:.3f}\nX\n\n"


def xfoil_polar(airfoil: str, Re: float, mach: float = 0.0, alpha_max: float = 22.0, alpha_min: float = -16.0,
                step: float = 0.5, ncrit: float = 9.0, xtr: float = 1.0, exe: str = "xfoil",
                timeout: float = 120, flap: tuple | None = None) -> AirfoilPolar:
    """Viscous polar by XFOIL in batch mode (sweeps 0→alpha_max and 0→alpha_min from a fresh BL).
    ``flap = (x_hinge/c, delta_deg)`` deflects a plain trailing-edge flap first (GDES FLAP)."""
    exe_path = shutil.which(exe)
    if exe_path is None:
        raise ToolNotAvailable("XFOIL binary not found on PATH (see THIRD_PARTY.md for the source build)")
    if flap and flap[1]:
        # deflected-flap runs can stall XFOIL's Newton loop post-stall; the partial polar written so far is kept
        timeout = min(timeout, 25.0)
        alpha_max, alpha_min = min(alpha_max, 18.0), max(alpha_min, -12.0)  # attached range is all we schedule
    tmp = Path(tempfile.mkdtemp(prefix="acdt_xf_"))
    rows = []
    try:
        for a1, st in ((alpha_max, step), (alpha_min, -step)):
            pol = tmp / f"pol_{'p' if st > 0 else 'n'}.txt"
            cmd = ("PLOP\nG F\n\n" + _xfoil_geometry_cmd(airfoil, tmp) + _xfoil_flap_cmd(flap) + "PANE\nOPER\n"
                   f"VPAR\nN {ncrit:g}\nXTR {xtr:.3f} {xtr:.3f}\n\n"
                   f"VISC {Re:.0f}\nMACH {mach:.3f}\nITER 150\nPACC\n{pol}\n\n"
                   f"ASEQ 0 {a1:g} {st:g}\nPACC\n\nQUIT\n")
            try:
                from acdt.core.provenance import tool_used
                tool_used("xfoil", exe_path)
                subprocess.run([exe_path], input=cmd, capture_output=True, text=True, timeout=timeout, cwd=tmp)
            except subprocess.TimeoutExpired:
                pass
            if pol.exists():
                for ln in pol.read_text(encoding="utf-8").splitlines():
                    p = ln.split()
                    if len(p) >= 5:
                        try:
                            rows.append([float(v) for v in p[:5]])
                        except ValueError:
                            continue
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if len(rows) < 8:
        raise RuntimeError(f"XFOIL returned {len(rows)} converged points for {airfoil} at Re={Re:.3g}")
    arr = np.array(sorted({r[0]: r for r in rows}.values()))
    pol = AirfoilPolar(airfoil, Re, mach, arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 4],
                       f"XFOIL 6.99 (Ncrit {ncrit:g}, xtr ≤ {xtr:.2f}"
                       + (f", flap {flap[1]:+g}° at x/c {flap[0]:.2f})" if flap and flap[1] else ")"))
    if pol.alpha_clmax >= alpha_max - 1e-6:
        pol.notes.append("clmax at the end of the sweep (stall not captured) — value is a lower bound")
    return pol


def neuralfoil_polar_obj(airfoil: str, Re: float, mach: float = 0.0, ncrit: float = 9.0, xtr: float = 1.0,
                         model_size: str = "large", flap: tuple | None = None) -> AirfoilPolar:
    try:
        import aerosandbox as asb
        import neuralfoil as nf
    except ImportError as e:  # pragma: no cover
        raise ToolNotAvailable("pip install neuralfoil aerosandbox") from e
    d = _naca_digits(airfoil)
    af = asb.Airfoil(f"naca{d}" if d else airfoil)
    if flap and flap[1]:
        af = af.add_control_surface(deflection=flap[1], hinge_point_x=flap[0])  # AeroSandbox (MIT) geometry
    al = np.arange(-16, 22.01, 0.5)
    r = nf.get_aero_from_airfoil(af, alpha=al, Re=Re, n_crit=ncrit, xtr_upper=xtr, xtr_lower=xtr,
                                 model_size=model_size)
    return AirfoilPolar(airfoil, Re, mach, al, np.asarray(r["CL"]), np.asarray(r["CD"]), np.asarray(r["CM"]),
                        f"NeuralFoil ({model_size}; XFOIL surrogate"
                        + (f", flap {flap[1]:+g}° at x/c {flap[0]:.2f})" if flap and flap[1] else ")"))


def _disk_cache_path(key: str):
    """Persistent polar cache (XFOIL runs are seconds each; camber-flap studies need dozens).
    ``ACDT_POLAR_CACHE`` = directory, or ``0``/``off`` to disable. Default ~/.cache/acdt/polars."""
    import hashlib
    import os
    d = os.environ.get("ACDT_POLAR_CACHE", "")
    if d.lower() in ("0", "off", "false", "no"):
        return None
    root = Path(d) if d else Path.home() / ".cache" / "acdt" / "polars"
    return root / (hashlib.sha1(key.encode()).hexdigest()[:20] + ".json")


def _disk_load(key):
    f = _disk_cache_path(key)
    if f is None or not f.exists():
        return None
    try:
        import json
        d = json.loads(f.read_text(encoding="utf-8"))
        return AirfoilPolar(d["airfoil"], d["Re"], d["mach"], np.array(d["alpha"]), np.array(d["cl"]),
                            np.array(d["cd"]), np.array(d["cm"]), d["source"], d.get("notes", []))
    except Exception:  # corrupt entry → recompute
        return None


def _disk_save(key, p: AirfoilPolar):
    f = _disk_cache_path(key)
    if f is None:
        return
    try:
        import json
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"key": key, "airfoil": p.airfoil, "Re": p.Re, "mach": p.mach,
                                 "alpha": p.alpha.tolist(), "cl": p.cl.tolist(), "cd": p.cd.tolist(),
                                 "cm": p.cm.tolist(), "source": p.source, "notes": list(p.notes)}))
    except OSError:
        pass


_CACHE_VERSION = "1"


@functools.lru_cache(maxsize=512)
def _cached(airfoil, Re_r, mach_r, xtr_r, prefer, flap=None):
    key = f"v{_CACHE_VERSION}|{airfoil}|{Re_r:g}|{mach_r:g}|{xtr_r:g}|{prefer}|{flap}"
    hit = _disk_load(key)
    if hit is not None:
        return hit
    p = _compute(airfoil, Re_r, mach_r, xtr_r, prefer, flap)
    _disk_save(key, p)
    return p


def _compute(airfoil, Re_r, mach_r, xtr_r, prefer, flap=None):
    errors = []
    for src in (("xfoil", "neuralfoil") if prefer == "xfoil" else ("neuralfoil", "xfoil")):
        try:
            if src == "xfoil":
                return xfoil_polar(airfoil, Re_r, mach_r, xtr=xtr_r, flap=flap)
            return neuralfoil_polar_obj(airfoil, Re_r, mach_r, xtr=xtr_r, flap=flap)
        except (ToolNotAvailable, RuntimeError) as e:
            errors.append(f"{src}: {e}")
    raise ToolNotAvailable("; ".join(errors))


def airfoil_polar(airfoil: str, Re: float, mach: float = 0.0, xtr: float = 1.0, prefer: str = "xfoil",
                  flap: tuple | None = None) -> AirfoilPolar:
    """XFOIL first, NeuralFoil as fallback. Cached on (airfoil, Re to 2 s.f., Mach to 0.01, xtr, flap).
    ``flap = (x_hinge/c, delta_deg)``: plain trailing-edge flap (camber flap) deflected before the sweep."""
    Re_r = float(f"{Re:.2g}")
    fl = (round(float(flap[0]), 3), round(float(flap[1]), 2)) if flap and abs(flap[1]) > 1e-9 else None
    return _cached(airfoil, Re_r, round(min(mach, 0.6), 2), round(min(max(xtr, 0.01), 1.0), 2), prefer, fl)
