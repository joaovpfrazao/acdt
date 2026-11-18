# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Tailless flying wing with NO vertical surface: split ailerons (drag rudders / decelerons) for yaw and an
active yaw stability augmentation system (SAS). Opt-in under ``assumptions.assembly.options.flying_wing``::

    flying_wing:
      yaw_control: split_aileron      # no fin / winglet; yaw from asymmetric drag of a split surface
      sas: true                       # default: true for a UAV (is_uas), false otherwise
      split_aileron: {eta_inner: 0.70, eta_outer: 0.98, cf_c: 0.30, delta_max_deg: 60,
                      rate_max_deg_s: 200, K_f: 1.7}
      elevon: {eta_inner: 0.30, eta_outer: 0.70, cf_c: 0.25, max_deg: 25}
      crosswind_kt: null              # default 0.2 V_S0 (14 CFR 23.233(a), pre-Amdt 23-64)
      turbulence: moderate            # MIL-F-8785C low-altitude W20: light 15 / moderate 30 / severe 45 kt

Absent block → nothing here runs (the baseline and every existing example are unchanged).

Methods (classical, cited)
--------------------------
* **Split-aileron drag.** Each leaf of the split surface (upper leaf up, lower leaf down) is treated as a split
  flap; profile-drag increment of McCormick, *Aerodynamics, Aeronautics, and Flight Mechanics*, 2nd ed., Wiley
  1995, Eqs. 3.45–3.46 (p. 109)::

      ΔC_D = K_f (c_f/c)^1.38 (S_f/S) sin²δ_f,    K_f = 1.7 (plain and split flaps), 0.9 (slotted)

  The equation and the constants were read in secondary sources that quote McCormick (Sun, Hoekstra &
  Ellerbroek 2020, Transp. Res. C 114 — OpenAP drag model "Eq. 3.45–3.46 in McCormick, p. 109"; Ananda & Selig
  2016, AIAA 2016-3541, Eq. 5 with K_f = 1.7); the book page itself was not opened. ``K_f`` may be overridden
  with a measured value (``split_aileron.K_f``) — e.g. from NACA split-flap section data (Wenzinger & Harris
  1939, NACA Rep. 668). PRESSUPOSTO: the two leaves superpose, ΔC_D = K_f (c_f/c)^1.38 (S_f/S)(sin²δ_u + sin²δ_l),
  the upper leaf behaving as an inverted split flap.
* **Yaw moment.** The drag acts at the span-wise area centroid ȳ_f of the split surface on one side:
  ΔC_n = ΔC_D · ȳ_f / b  (moment arm about the plane of symmetry; Etkin & Reid 1996 body axes).
* **Side effects.** With equal leaf deflections the lift increments of the two leaves cancel: ΔC_L ≈ ΔC_l ≈ 0.
  Löchert, Huber, Ghoreyshi & Allen (2019, DLR elib 128954, MULDICON split flap δ_u = 45°/δ_l = 32°) report
  ΔC_n ≈ −0.016 "with ΔC_l and ΔC_m ≈ 0" for attached flow up to α = 10°, |β| = 10°; at higher α the
  rolling moment grows (×3 at α = 14°) — outside that envelope the split aileron is **unassessed**. The pitching
  moment of the drag acting off the CG height is kept: ΔC_m = −ΔC_D (z_f − z_cg)/c̄.
* **AVL is inviscid**: it cannot see the profile drag of an opened split surface (the dominant effect), so the
  split aileron is never modelled in AVL. AVL (Drela & Youngren) is used only for the bare-airframe
  derivatives and for the elevon (C_lδa, C_nδa, C_Yδa) with an AVL ``CONTROL`` (SgnDup −1) on the wing.
* **Crosswind** — steady straight sideslip, nose on the runway (Roskam, *Airplane Flight Dynamics* Part I
  Sec. 4.2; same as :mod:`..flightsim.controls`): C_Yβ β + C_Yδa δa + C_L sin φ = 0, C_lβ β + C_lδa δa = 0,
  C_nβ β + C_nδa δa + ΔC_n,split = 0 at U = 1.1 V_S0 (Sadraey 2012 Sec. 12.6.2.3), 90° crosswind ≥ 0.2 V_S0
  (14 CFR 23.233(a), pre-Amdt 23-64) or the user value.
* **Coordinated roll / turn against adverse yaw** — MIL-F-8785C Table IXa (Class I) bank change with the
  single-DOF roll model (Sadraey Eqs. 12.34–12.46): ΔC_n,split = −(C_nδa δa + C_np p̂) at the roll entry
  (p̂ = 0) and at the steady roll rate; steady coordinated turn at the reached bank φ = Δφ/2 (r = g sin φ / V):
  δa = −C_lr r̂/C_lδa, ΔC_n,split = −(C_nr r̂ + C_nδa δa).
* **SAS** — yaw damper plus C_nβ augmentation, both commanded through the split ailerons:
  u = ΔC_n,cmd = k_β β_air − k_r r̂ ⇒ C_nβ,aug = C_nβ + k_β, C_nr,aug = C_nr − k_r (Nelson 1998 Ch. 10;
  Etkin & Reid 1996 Ch. 10 — the lateral matrix of :func:`..stability.lateral_matrix`). Gains are the smallest
  turbulence-authority point of a (k_β, k_r) grid that meets MIL-F-8785C Level 1: Table VI Dutch-roll row of
  the hq category at cruise (default B) and of Category C at approach, Table VIII spiral, evaluated on the loop with
  the actuator model (first-order lag + transport delay, :mod:`.tailless_actuation`; unknown → 0.10 s equivalent
  delay, the MIL-F-8785C 3.5.3 Level-1 limit). Gains scheduled as coefficients (dimensional gains ∝ 1/q̄).
* **Authority / rate** — lateral turbulence of MIL-F-8785C (Dryden, low-altitude model, h = 50 ft — the 14 CFR
  23.75 screen height): σ_w = 0.1 W20, σ_v = σ_w/(0.177 + 0.000823 h)^0.4, L_v = h/(0.177 + 0.000823 h)^1.2 [ft],
  H_v(s) ∝ (1 + √3 L_v s/V)/(1 + L_v s/V)² (spectrum form verified in the MathWorks Aerospace Blockset
  documentation of the MIL-F-8785C Dryden model). σ_u of the SAS command from the Lyapunov covariance of the
  closed loop. PRESSUPOSTO: [β, p, r] subsystem (the autopilot bank-hold loop keeps φ ≈ 0), r_g gust neglected,
  peak = 3σ, SAS demand = 3σ_u (the steady crosswind demand is its own check; the sum is reported),
  rate = δ(3σ_u)·ω_d,closed (harmonic swing).
  With SAS active ``hq:dutch_roll/spiral`` pass only if that demand is within the split-aileron capability
  2·C₁·sin²δ_max and the rate within ``rate_max_deg_s``; unknown inputs → unassessed (never a pass).

Bare-airframe modes are always reported (``bare``), as information — the failure is never hidden.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

K_SPLIT_MCCORMICK = 1.7
SPLIT_DRAG_SOURCE = ("McCormick 1995, Aerodynamics, Aeronautics, and Flight Mechanics 2nd ed., Eqs. 3.45–3.46 "
                     "p. 109: ΔC_D = K_f (c_f/c)^1.38 (S_f/S) sin²δ, K_f = 1.7 plain/split "
                     "(via Sun et al. 2020 TR-C 114 / OpenAP; Ananda & Selig 2016 AIAA 2016-3541 Eq. 5)")
SIDE_EFFECT_SOURCE = ("Löchert, Huber, Ghoreyshi & Allen 2019 (DLR elib 128954): split flap ΔC_l ≈ ΔC_m ≈ 0 in "
                      "attached flow, α ≤ 10°, |β| ≤ 10°")
CROSSWIND_SOURCE = "14 CFR 23.233(a) (pré-Amdt 23-64): vento cruzado a 90° ≥ 0,2 V_S0; U = 1,1 V_S0 (Sadraey 12.6.2.3)"
# MIL-F-8785C 3.7 low-altitude turbulence: wind speed at 20 ft, knots
W20_KT = {"light": 15.0, "moderate": 30.0, "severe": 45.0}
# Design targets for the SAS: MIL-F-8785C Level 1 — Table VI Dutch-roll row (ζ, ζω, ω) of the flight-phase
# category (cruise: the hq category, default B; approach: C) and Table VIII spiral T2.
SPIRAL_T2_MIN = {"A": 12.0, "B": 20.0, "C": 12.0}


def _dr_target(cat: str) -> tuple:
    from ..stability import MIL_F_8785C
    return tuple(MIL_F_8785C["dutch_roll"][cat][0])
ATTACHED_FLOW_ALPHA_MAX_DEG = 10.0   # Löchert et al. 2019 envelope of ΔC_l ≈ ΔC_m ≈ 0
ELEVON_MAX_DEFAULT_DEG = 25.0        # Sadraey 2012 Sec. 12.4.4 step 10 (aileron ±25 typical)
SCREEN_HEIGHT_FT = 50.0              # 14 CFR 23.75 landing-distance screen height
KT = 0.514444


# ------------------------------------------------------------------------------------------- split drag
def split_drag_increment(cf_c: float, Sf_S: float, delta_u_deg: float, delta_l_deg: float | None = None,
                         K_f: float = K_SPLIT_MCCORMICK) -> float:
    """ΔC_D of one split aileron (both leaves): K_f (c_f/c)^1.38 (S_f/S)(sin²δ_u + sin²δ_l) (McCormick 1995 Eq. 3.45;
    leaf superposition PRESSUPOSTO). ``delta_l_deg`` defaults to ``delta_u_deg`` (symmetric opening)."""
    dl = delta_u_deg if delta_l_deg is None else delta_l_deg
    return K_f * cf_c ** 1.38 * Sf_S * (math.sin(math.radians(delta_u_deg)) ** 2 + math.sin(math.radians(dl)) ** 2)


def split_geometry(asm, eta_inner: float, eta_outer: float, cf_c: float) -> dict:
    """Area, span-wise centroid and height of one side's split surface on the main wing (linear chord between the
    drawn sections; η = y_local / semispan)."""
    from .sizing import main_wing
    w, gw = main_wing(asm)
    if not w.mirror:
        raise ValueError("split ailerons need a y-mirrored main wing")
    if not (0.0 <= eta_inner < eta_outer <= 1.0):
        raise ValueError(f"split aileron: need 0 ≤ eta_inner < eta_outer ≤ 1 (got {eta_inner}, {eta_outer})")
    ys = np.array([float(s["le"][1]) for s in w.sections])
    ch = np.array([float(s["chord"]) for s in w.sections])
    ymax = float(ys.max())
    y = np.linspace(eta_inner * ymax, eta_outer * ymax, 201)
    c = np.interp(y, ys, ch)
    A = float(np.trapezoid(c, y))
    yc = float(np.trapezoid(c * y, y) / A)
    le = np.array([np.interp(yc, ys, [float(s["le"][k]) for s in w.sections]) for k in range(3)])
    cc = float(np.interp(yc, ys, ch))
    P = w.to_global([le])[0]
    y0 = float(w.origin[1]) if hasattr(w, "origin") else 0.0
    return {"S_f": cf_c * A, "S_strip": A, "y_bar": yc + y0, "eta_bar": yc / ymax, "chord_at_ybar": cc,
            "x_f": float(P[0] + (1 - 0.5 * cf_c) * cc), "z_f": float(P[2]), "semispan": ymax,
            "S": gw["S"], "b": gw["b"], "mac": gw["mac"], "cf_c": cf_c, "eta_inner": eta_inner,
            "eta_outer": eta_outer}


def yaw_power(geom: dict, K_f: float = K_SPLIT_MCCORMICK) -> float:
    """C₁ such that ΔC_n = C₁ (sin²δ_u + sin²δ_l): C₁ = K_f (c_f/c)^1.38 (S_f/S) ȳ_f/b."""
    return K_f * geom["cf_c"] ** 1.38 * geom["S_f"] / geom["S"] * geom["y_bar"] / geom["b"]


def capacity(C1: float, delta_max_deg: float) -> float:
    """Largest |ΔC_n| of one side, both leaves at δ_max: 2·C₁·sin²δ_max."""
    return 2.0 * C1 * math.sin(math.radians(delta_max_deg)) ** 2


def deflection_for(dCn: float, C1: float) -> float | None:
    """Symmetric leaf deflection [deg] giving |ΔC_n| on one side; None when beyond 90° (impossible)."""
    s2 = abs(dCn) / (2.0 * C1) if C1 > 0 else math.inf
    if s2 > 1.0:
        return None
    return math.degrees(math.asin(math.sqrt(s2)))


def side_effects(geom: dict, C1: float, delta_deg: float, z_cg: float, K_f: float = K_SPLIT_MCCORMICK) -> dict:
    """ΔC_D, ΔC_n, ΔC_l (≈ 0, Löchert et al. 2019), ΔC_m of the drag off the CG height, for one side at δ (both leaves)."""
    dCD = split_drag_increment(geom["cf_c"], geom["S_f"] / geom["S"], delta_deg, None, K_f)
    return {"dCD": dCD, "dCn": dCD * geom["y_bar"] / geom["b"], "dCl": 0.0,
            "dCm": -dCD * (geom["z_f"] - z_cg) / geom["mac"], "dCl_source": SIDE_EFFECT_SOURCE}


def span_required(asm, demand: float, eta_outer: float, cf_c: float, delta_max_deg: float,
                  K_f: float = K_SPLIT_MCCORMICK) -> float | None:
    """Smallest span fraction (η_outer − η_inner, η_outer fixed) whose capacity covers ``demand``; None if the
    whole semispan inboard of η_outer is not enough."""
    if demand <= 0:
        return 0.0
    lo, hi = 0.0, eta_outer - 1e-3
    def cap(eta_in):
        g = split_geometry(asm, eta_in, eta_outer, cf_c)
        return capacity(yaw_power(g, K_f), delta_max_deg)
    if cap(lo) < demand:
        return None
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if cap(mid) >= demand:
            lo = mid
        else:
            hi = mid
    return eta_outer - lo


# ------------------------------------------------------------------------------------------- AVL + elevon
def _avl_text_elevon(asm, ref: dict, cg: tuple, mach: float, eta_in: float, eta_out: float, cf_c: float,
                     with_sym: bool = False) -> str:
    """Assembly AVL file (same as :meth:`Assembly.avl_text`) with the main wing re-sectioned at η_in/η_out and an
    antisymmetric ``CONTROL elevon`` (SgnDup −1) between them (AVL 3.x user guide). ``with_sym`` adds a second,
    symmetric control ``elevsym`` (SgnDup +1) on the same hinge (pitch use of the elevon)."""
    from .components import Surface
    from .sizing import main_wing
    w, _ = main_wing(asm)
    surfs = [c for c in asm.components if isinstance(c, Surface) and not c.mirrored_image]
    out = ["acdt_tailless", "#Mach", f"{mach:g}", "#IYsym IZsym Zsym", "0 0 0.0", "#Sref Cref Bref",
           f"{ref['Sref']:.5f} {ref['Cref']:.5f} {ref['Bref']:.5f}", "#Xref Yref Zref",
           f"{cg[0]:.5f} {cg[1]:.5f} {cg[2]:.5f}", "#CDp", "0.0"]
    for s in surfs:
        out += ["#" + "=" * 60, "SURFACE", s.name, "#Nchord Cspace Nspan Sspace", "8 1.0 16 1.0"]
        if s.mirror:
            out += ["YDUPLICATE", "0.0"]
        secs = [dict(sec) for sec in s.sections]
        if s is w:
            ys = [float(sec["le"][1]) for sec in secs]
            ymax = max(ys)
            for eta in (eta_in, eta_out):
                yy = eta * ymax
                if any(abs(yy - v) < 1e-6 * max(ymax, 1) for v in ys):
                    continue
                new = {"le": [float(np.interp(yy, ys, [sc["le"][k] for sc in s.sections])) for k in range(3)],
                       "chord": float(np.interp(yy, ys, [sc["chord"] for sc in s.sections])),
                       "twist_deg": float(np.interp(yy, ys, [sc["twist_deg"] for sc in s.sections])),
                       "tc": float(np.interp(yy, ys, [sc["tc"] for sc in s.sections]))}
                secs.append(new)
            secs.sort(key=lambda sc: sc["le"][1])
        for sec in secs:
            le = s.to_global([sec["le"]])[0]
            out += ["SECTION", "#Xle Yle Zle Chord Ainc",
                    f"{le[0]:.5f} {le[1]:.5f} {le[2]:.5f} {sec['chord']:.5f} {sec['twist_deg']:.3f}",
                    "NACA", f"00{max(1, min(99, round(100 * sec['tc']))):02d}"]
            if s is w:
                eta = float(sec["le"][1]) / ymax
                if eta_in - 1e-6 <= eta <= eta_out + 1e-6:
                    out += ["CONTROL", f"elevon 1.0 {1 - cf_c:.4f} 0. 1. 0. -1.0"]
                    if with_sym:
                        out += ["CONTROL", f"elevsym 1.0 {1 - cf_c:.4f} 0. 1. 0. 1.0"]
    return "\n".join(out) + "\n"


def avl_with_elevon(asm, CL: float, mach: float, x_ref: float, z_ref: float, elevon: dict,
                    exe: str = "avl", timeout: float = 60) -> dict:
    """One AVL trim-to-CL point of the assembly (no bodies) with the elevon; stability-axis derivatives per rad
    plus C_Yδa, C_lδa, C_nδa [1/rad] (AVL ST output, d01, converted from per degree)."""
    from ..aero.avl import _grab
    from ..aero.interfaces import ToolNotAvailable
    from .sizing import main_wing
    exe_path = shutil.which(exe)
    if exe_path is None:
        raise ToolNotAvailable("AVL binary not found on PATH")
    _, gw = main_wing(asm)
    tmp = Path(tempfile.mkdtemp(prefix="acdt_tailless_avl_"))
    try:
        txt = _avl_text_elevon(asm, {"Sref": gw["S"], "Cref": gw["mac"], "Bref": gw["b"]}, (x_ref, 0.0, z_ref),
                               mach, float(elevon["eta_inner"]), float(elevon["eta_outer"]), float(elevon["cf_c"]))
        (tmp / "t.avl").write_text(txt, encoding="utf-8")
        cmds = ["oper", f"a c {CL:.6f}", f"m\nmn {mach:.4f}\n", "x", "st", "st.txt", "", "quit"]
        from acdt.core.provenance import tool_used
        tool_used("avl", exe_path)
        r = subprocess.run([exe_path, "t.avl"], input="\n".join(cmds) + "\n", capture_output=True, text=True,
                           timeout=timeout, cwd=tmp)
        if not (tmp / "st.txt").exists():
            raise RuntimeError(f"AVL failed (tailless elevon run). Last output:\n{r.stdout[-1200:]}")
        st = (tmp / "st.txt").read_text(encoding="utf-8")
        out = {"alpha_deg": _grab(st, "Alpha"), "CL": _grab(st, "CLtot")}
        for k in ("CYb", "Clb", "Cnb", "CYp", "Clp", "Cnp", "CYr", "Clr", "Cnr"):
            out[k] = _grab(st, k)
        for k, key in (("CYda", "CYd01"), ("Clda", "Cld01"), ("Cnda", "Cnd01")):
            out[k] = _grab(st, key) * 180.0 / math.pi
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def avl_elevon_point(asm, mach: float, x_ref: float, z_ref: float, elevon: dict, CL: float | None = None,
                     alpha_deg: float | None = None, anti_deg: float = 0.0, sym_deg: float = 0.0,
                     trim_sym: bool = False, hinge: bool = False, strips: bool = False, exe: str = "avl",
                     timeout: float = 60) -> dict:
    """One AVL point with antisymmetric (d1, ``elevon``) and symmetric (d2, ``elevsym``) elevon controls:
    stability derivatives, control derivatives per rad (C_Yδa, C_lδa, C_nδa; C_Lδe, C_mδe), optional Cm = 0 trim
    with the symmetric elevon, AVL HM hinge coefficients (ref. Sref·Cref) and wing strip c_l."""
    from ..aero.avl import _grab, _parse_strips
    from ..aero.interfaces import ToolNotAvailable
    from .sizing import main_wing
    exe_path = shutil.which(exe)
    if exe_path is None:
        raise ToolNotAvailable("AVL binary not found on PATH")
    w, gw = main_wing(asm)
    tmp = Path(tempfile.mkdtemp(prefix="acdt_tailless_avl_"))
    try:
        txt = _avl_text_elevon(asm, {"Sref": gw["S"], "Cref": gw["mac"], "Bref": gw["b"]}, (x_ref, 0.0, z_ref),
                               mach, float(elevon["eta_inner"]), float(elevon["eta_outer"]), float(elevon["cf_c"]),
                               with_sym=True)
        (tmp / "t.avl").write_text(txt, encoding="utf-8")
        cmds = ["oper", f"a c {CL:.6f}" if CL is not None else f"a a {alpha_deg or 0.0:.6f}",
                f"d1 d1 {anti_deg:.4f}", "d2 pm 0" if trim_sym else f"d2 d2 {sym_deg:.4f}",
                f"m\nmn {mach:.4f}\n", "x", "st", "st.txt", "fs", "fs.txt"]
        if hinge:
            cmds += ["hm", "hm.txt"]
        cmds += ["", "quit"]
        from acdt.core.provenance import tool_used
        tool_used("avl", exe_path)
        r = subprocess.run([exe_path, "t.avl"], input="\n".join(cmds) + "\n", capture_output=True, text=True,
                           timeout=timeout, cwd=tmp)
        if not (tmp / "st.txt").exists():
            raise RuntimeError(f"AVL failed (tailless elevon point). Last output:\n{r.stdout[-1200:]}")
        st = (tmp / "st.txt").read_text(encoding="utf-8")
        out = {"alpha_deg": _grab(st, "Alpha"), "CL": _grab(st, "CLtot"), "Cm": _grab(st, "Cmtot"),
               "CDi": _grab(st, "CDff"), "elevsym_deg": _grab(st, "elevsym"), "elevon_deg": _grab(st, "elevon")}
        for k in ("CLa", "Cma", "CLq", "Cmq", "CYb", "Clb", "Cnb", "CYp", "Clp", "Cnp", "CYr", "Clr", "Cnr"):
            try:
                out[k] = _grab(st, k)
            except KeyError:
                out[k] = 0.0
        for k, key in (("CYda", "CYd01"), ("Clda", "Cld01"), ("Cnda", "Cnd01"), ("CLde", "CLd02"), ("Cmde", "Cmd02")):
            out[k] = _grab(st, key) * 180.0 / math.pi
        if hinge and (tmp / "hm.txt").exists():
            hm = {}
            for ln in (tmp / "hm.txt").read_text(encoding="utf-8").splitlines():
                parts = ln.split()
                if len(parts) == 2 and parts[0] in ("elevon", "elevsym"):
                    hm[parts[0]] = float(parts[1].replace("D", "E"))
            out["hinge"] = hm
        if strips:
            names = (w.name, f"{w.name} (YDUP)")
            out["strips"] = _parse_strips((tmp / "fs.txt").read_text(encoding="utf-8"), surface_names=names)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------------------------------- sizing cases
def crosswind_case(d: dict, CL: float, U: float, Vw: float, C1: float | None, delta_max_deg: float | None,
                   elevon_max_deg: float) -> dict:
    """Steady straight sideslip (Roskam AFD I Sec. 4.2) with elevon roll and split-aileron yaw."""
    beta = math.atan2(Vw, U)
    da = -d["Clb"] * beta / d["Clda"]
    dCn = -(d["Cnb"] * beta + d["Cnda"] * da)
    sphi = -(d["CYb"] * beta + d["CYda"] * da) / CL
    out = {"U_m_s": U, "crosswind_m_s": Vw, "crosswind_kt": Vw / KT, "beta_deg": math.degrees(beta),
           "delta_a_deg": math.degrees(da), "bank_deg": math.degrees(math.asin(max(-1.0, min(1.0, sphi)))),
           "dCn_required": dCn, "dCn_from_Cnb": -d["Cnb"] * beta, "dCn_from_elevon": -d["Cnda"] * da,
           "elevon_ok": abs(math.degrees(da)) <= elevon_max_deg, "fonte": CROSSWIND_SOURCE}
    if C1 is None or delta_max_deg is None:
        out.update({"status": "unassessed", "ok": None})
        return out
    dreq = deflection_for(dCn, C1)
    cap = capacity(C1, delta_max_deg)
    out.update({"delta_split_deg": dreq, "capacity_dCn": cap,
                "ok": bool(dreq is not None and dreq <= delta_max_deg and out["elevon_ok"]), "status": "assessed"})
    # largest crosswind (linear in β up to the capacity and the elevon limit)
    per_rad = abs(d["Cnb"] - d["Cnda"] * d["Clb"] / d["Clda"])
    da_per_rad = abs(d["Clb"] / d["Clda"])
    lim = min(cap / per_rad if per_rad > 0 else math.inf,
              math.radians(elevon_max_deg) / da_per_rad if da_per_rad > 0 else math.inf, math.radians(80))
    out["crosswind_max_kt"] = U * math.tan(lim) / KT
    return out


def coordination_case(d: dict, V: float, rho: float, S: float, b: float, Ixx: float, category: str,
                      level: int, elevon_max_deg: float, C1: float | None, delta_max_deg: float | None) -> dict:
    """Roll entry / steady roll / steady coordinated turn against adverse yaw (MIL-F-8785C Table IXa)."""
    from acdt import G0
    from ..flightsim.controls import MIL_8785C_ROLL_CLASS_I, roll_response, time_to_bank
    dphi_deg, ts = MIL_8785C_ROLL_CLASS_I[category]
    t_req = ts[level - 1]
    dphi = math.radians(dphi_deg)

    def t_of(da):
        rr = roll_response(d["Clp"], d["Clda"], da, V, rho, S, b, Ixx)
        return time_to_bank(dphi, rr["p_ss"], rr["tau"]), rr
    da_max = math.radians(elevon_max_deg)
    t_max, rr_max = t_of(da_max)
    roll_ok = t_max <= t_req
    if roll_ok:
        lo, hi = 1e-4, da_max
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            if t_of(mid)[0] > t_req:
                lo = mid
            else:
                hi = mid
        da = hi
    else:
        da = da_max
    rr = t_of(da)[1]
    sgn = 1.0 if rr["p_ss"] >= 0 else -1.0
    p_hat = rr["p_ss"] * b / (2 * V)
    entry = -(d["Cnda"] * da)
    steady = -(d["Cnda"] * da + d["Cnp"] * p_hat)
    phi = 0.5 * dphi
    r_hat = sgn * G0 * math.sin(phi) / V * b / (2 * V)
    da_t = -d["Clr"] * r_hat / d["Clda"]
    turn = -(d["Cnr"] * r_hat + d["Cnda"] * da_t)
    dem = max(abs(entry), abs(steady), abs(turn))
    out = {"requirement": f"MIL-F-8785C Table IXa Classe I Cat. {category} Nível {level}: {dphi_deg:.0f}° em {t_req} s",
           "roll_ok": roll_ok, "t_to_bank_s_at_max": t_max, "delta_a_deg": math.degrees(da), "p_hat": p_hat,
           "dCn_entry": entry, "dCn_steady_roll": steady, "turn_bank_deg": math.degrees(phi), "r_hat_turn": r_hat,
           "delta_a_turn_deg": math.degrees(da_t), "dCn_turn": turn, "dCn_required": dem}
    if C1 is None or delta_max_deg is None:
        out.update({"status": "unassessed", "ok": None})
        return out
    dreq = deflection_for(dem, C1)
    out.update({"delta_split_deg": dreq, "capacity_dCn": capacity(C1, delta_max_deg),
                "ok": bool(dreq is not None and dreq <= delta_max_deg), "status": "assessed"})
    return out


# ------------------------------------------------------------------------------------------- SAS
def _dr_level_ok(lat: dict, target: tuple) -> bool:
    dr = lat.get("dutch_roll")
    if not dr:
        return False   # no oscillatory pair: two real roots — treat as not meeting the ζω/ω rows
    z, wn = dr["zeta"], dr["wn"]
    return z >= target[0] and z * wn >= target[1] and wn >= target[2]


def _spiral_ok(lat: dict, cat: str) -> bool:
    sp = lat.get("spiral")
    if not sp:
        return False
    return sp["stable"] or sp["T2_s"] >= SPIRAL_T2_MIN[cat]


def close_loop(A: np.ndarray, kb: float, kr: float, qSb_Izz: float, b: float, u0: float) -> np.ndarray:
    """Lateral matrix [β, p, r, φ] with u = k_β β − k_r r̂ through N only (ΔC_l ≈ 0 for a symmetric split)."""
    Acl = np.array(A, float).copy()
    Acl[2, 0] += qSb_Izz * kb
    Acl[2, 2] += -qSb_Izz * kr * b / (2 * u0)
    return Acl


def dryden_lateral(h_m: float, W20_kt: float) -> dict:
    """MIL-F-8785C low-altitude Dryden lateral intensity and scale (h < 1000 ft)."""
    h = h_m / 0.3048
    den = 0.177 + 0.000823 * h
    sw = 0.1 * W20_kt * KT
    return {"sigma_v": sw / den ** 0.4, "L_v_m": h / den ** 1.2 * 0.3048, "sigma_w": sw, "h_ft": h,
            "W20_kt": W20_kt}


def turbulence_sigma_u(A: np.ndarray, kb: float, kr: float, qSb_Izz: float, b: float, U: float,
                       sigma_v: float, L_v: float) -> float | None:
    """σ of the SAS command ΔC_n,cmd in Dryden lateral turbulence, [β, p, r] subsystem (Lyapunov covariance)."""
    from scipy.linalg import solve_continuous_lyapunov
    a = L_v / U
    Ag = np.array([[0.0, 1.0], [-1.0 / a**2, -2.0 / a]])
    Bg = np.array([[0.0], [1.0]])
    Cg = np.array([[1.0 / a**2, math.sqrt(3.0) / a]])
    Pg = solve_continuous_lyapunov(Ag, -Bg @ Bg.T)
    sF = sigma_v / math.sqrt(float((Cg @ Pg @ Cg.T).item()))
    A3 = np.array(A, float)[:3, :3]
    Acl = close_loop(np.pad(A3, ((0, 1), (0, 1))), kb, kr, qSb_Izz, b, U)[:3, :3]
    Bu = np.array([0.0, 0.0, qSb_Izz])
    E = -np.array(A, float)[:3, 0]                       # aerodynamic β column sees β − β_g
    Gin = (E - Bu * kb)[:, None] * (sF / U) @ Cg         # β_g = sF·C_g x_g / U
    Aa = np.block([[Acl, Gin], [np.zeros((2, 3)), Ag]])
    if np.max(np.linalg.eigvals(Aa).real) >= 0:
        return None
    Ba = np.vstack([np.zeros((3, 1)), Bg])
    P = solve_continuous_lyapunov(Aa, -Ba @ Ba.T)
    K = np.concatenate([[kb, 0.0, -kr * b / (2 * U)], -kb * sF / U * Cg[0]])
    return math.sqrt(max(float(K @ P @ K), 0.0))


def modes_with_actuator(A4, kb: float, kr: float, qSb_Izz: float, b: float, u0: float, lag_s: float,
                        delay_s: float) -> dict:
    """Lateral modes of the SAS loop with the actuator (lag + Padé delay), in :func:`..stability._modes_lat` format:
    each mode is the eigenvalue of the augmented loop closest to the ideal-loop mode."""
    from ..stability import _modes_lat, _pair
    from .tailless_actuation import augmented_loop
    ideal = _modes_lat(close_loop(A4, kb, kr, qSb_Izz, b, u0))
    lam = np.linalg.eigvals(augmented_loop(A4, kb, kr, qSb_Izz, b, u0, lag_s, delay_s))
    out = {"eig": [complex(x) for x in lam]}
    cpl = [l for l in lam if l.imag > 1e-9]
    rea = [l.real for l in lam if abs(l.imag) <= 1e-9]
    if ideal.get("dutch_roll") and cpl:
        ref = complex(ideal["dutch_roll"].get("eig", 0j)) if "eig" in ideal["dutch_roll"] else None
        if ref is None:
            z, w = ideal["dutch_roll"]["zeta"], ideal["dutch_roll"]["wn"]
            ref = complex(-z * w, w * math.sqrt(max(1 - z * z, 0.0)))
        out["dutch_roll"] = _pair(min(cpl, key=lambda l: abs(l - ref)))
    for key, pick in (("spiral", "lambda"), ("roll", "lambda")):
        if ideal.get(key) and rea:
            ref = ideal[key][pick]
            lr = min(rea, key=lambda x: abs(x - ref))
            if key == "spiral":
                out[key] = {"lambda": lr, "T2_s": math.log(2) / lr if lr > 0 else math.inf,
                            "T_half_s": math.log(2) / -lr if lr < 0 else math.inf, "stable": lr < 0}
            else:
                out[key] = {"lambda": lr, "tau_s": -1 / lr if lr < 0 else math.inf}
    out["stable"] = bool(np.max(lam.real) < 0)
    return out


def design_sas(A_cr: np.ndarray, cr: dict, A_ap: np.ndarray | None, ap: dict | None, turb: dict | None,
               cat_cruise: str = "B", kb_max: float = 0.4, kr_max: float = 1.5, n: int = 41,
               actuator: tuple | None = None) -> dict:
    """Smallest-turbulence-authority (k_β, k_r) meeting MIL-F-8785C Level 1 (Tables VI, VIII) at cruise (category
    ``cat_cruise``) and at approach (Category C) when given. ``actuator`` = (lag_s, delay_s): the levels and the
    turbulence σ are those of the loop with the actuator model (:mod:`.tailless_actuation`)."""
    from ..stability import _modes_lat
    t_cr, t_ap = _dr_target(cat_cruise), _dr_target("C")
    best = None
    feasible = 0
    lag, dly = actuator if actuator is not None else (0.0, 0.0)

    def modes(A, c, kb, kr):
        if actuator is None:
            return _modes_lat(close_loop(A, kb, kr, c["qSb_Izz"], c["b"], c["u0"]))
        mm = modes_with_actuator(A, kb, kr, c["qSb_Izz"], c["b"], c["u0"], lag, dly)
        return mm if mm.get("stable") else {}
    for kb in np.linspace(0.0, kb_max, n):
        for kr in np.linspace(0.0, kr_max, n):
            lat_c = modes(A_cr, cr, kb, kr)
            if not (_dr_level_ok(lat_c, t_cr) and _spiral_ok(lat_c, cat_cruise)):
                continue
            lat_a = None
            if A_ap is not None:
                lat_a = modes(A_ap, ap, kb, kr)
                if not (_dr_level_ok(lat_a, t_ap) and _spiral_ok(lat_a, "C")):
                    continue
            feasible += 1
            J = None
            if A_ap is not None and turb is not None:
                if actuator is None:
                    J = turbulence_sigma_u(A_ap, kb, kr, ap["qSb_Izz"], ap["b"], ap["u0"], turb["sigma_v"],
                                           turb["L_v_m"])
                else:
                    from .tailless_actuation import turbulence_sigma_actuated
                    sg = turbulence_sigma_actuated(A_ap, kb, kr, ap["qSb_Izz"], ap["b"], ap["u0"], turb["sigma_v"],
                                                   turb["L_v_m"], lag, dly)
                    J = sg["sigma_u"] if sg else None
                if J is None:
                    continue
            score = J if J is not None else kb + kr
            if best is None or score < best["score"]:
                best = {"k_beta": float(kb), "k_r": float(kr), "score": score, "sigma_u": J,
                        "lat_cruise": lat_c, "lat_approach": lat_a}
    if best is None:
        return {"status": "infeasible", "feasible_points": 0,
                "issues": [f"nenhum ganho (k_β ≤ {kb_max}, k_r ≤ {kr_max}) cumpre MIL-F-8785C Nível 1 "
                           f"(Tabela VI Cat. {cat_cruise}/C, Tabela VIII)"]}
    best.update({"status": "ok", "feasible_points": feasible,
                 "actuator_in_design": ({"lag_s": lag, "delay_s": dly} if actuator is not None else None),
                 "target": {"dutch_roll_cruise": t_cr, "dutch_roll_approach": t_ap,
                            "spiral_T2_min_s": {cat_cruise: SPIRAL_T2_MIN[cat_cruise], "C": SPIRAL_T2_MIN["C"]},
                            "source": f"MIL-F-8785C Tabela VI Nível 1 (cruzeiro Cat. {cat_cruise}, aproximação Cat. C) "
                                      "e Tabela VIII"}})
    return best


def sas_authority(sas: dict, crosswind: dict | None, C1: float | None, delta_max_deg: float | None,
                  rate_max_deg_s: float | None) -> dict:
    """SAS demand 3σ_u (Dryden turbulence at approach) vs capacity; rate δ(3σ_u)·ω_d,closed vs the actuator rate.
    The steady crosswind demand is its own check (``hq:yaw_crosswind``); the sum is reported as information."""
    out = {"status": "unassessed", "ok": None, "issues": []}
    if sas.get("status") != "ok":
        out["issues"].append("SAS sem ganhos viáveis")
        out["ok"] = False
        out["status"] = "infeasible"
        return out
    if sas.get("sigma_u") is None:
        out["issues"].append("σ_u em turbulência não calculado (falta caso de aproximação)")
        return out
    if C1 is None or delta_max_deg is None:
        out["issues"].append("split_aileron (eta_inner/eta_outer/cf_c/delta_max_deg) em falta — capacidade unassessed")
        return out
    cw = abs(crosswind["dCn_required"]) if crosswind and crosswind.get("dCn_required") is not None else None
    three = 3.0 * sas["sigma_u"]
    demand = three
    cap = capacity(C1, delta_max_deg)
    d3 = deflection_for(three, C1)
    lat_a = sas.get("lat_approach") or {}
    wd = (lat_a.get("dutch_roll") or {}).get("wn")
    rate = math.degrees(math.radians(d3) * wd) if (d3 is not None and wd) else None
    out.update({"dCn_crosswind_info": cw, "combined_with_crosswind_ok": (cw + three <= cap) if cw is not None else None,
                "dCn_3sigma_turbulence": three, "demand_dCn": demand, "capacity_dCn": cap,
                "delta_demand_deg": deflection_for(demand, C1), "delta_3sigma_deg": d3,
                "omega_d_closed_approach": wd, "rate_required_deg_s": rate, "rate_max_deg_s": rate_max_deg_s,
                "authority_ok": demand <= cap})
    if rate_max_deg_s is None:
        out["issues"].append("split_aileron.rate_max_deg_s em falta — taxa unassessed")
        out["ok"], out["status"] = (False if demand > cap else None), "partial"
        return out
    out["rate_ok"] = rate is not None and rate <= rate_max_deg_s
    out["ok"] = bool(out["authority_ok"] and out["rate_ok"])
    out["status"] = "assessed"
    return out


# ------------------------------------------------------------------------------------------- orchestration
def options(spec: dict) -> dict | None:
    """The flying_wing block when it asks for split-aileron yaw control, else None."""
    fw = (spec.get("options") or {}).get("flying_wing")
    if isinstance(fw, dict) and str(fw.get("yaw_control") or "").lower() == "split_aileron":
        return fw
    return None


BIAS_SOURCE = ("pré-deflexão simétrica δ0 dos dois split ailerons (ΔC_n = 2C₁ sin2δ0 sin2d, linear em ΔC_n = 0: "
               "Rajput, Zhang & Qu 2014, Appl. Mech. Mater. 643:54; Wang, Wang & Jia 2011, Acta Aeronaut. Astronaut. "
               "Sin. 32(8):1392); arrasto de perfil McCormick 1995 Eq. 3.45 por folha, dois lados")


def bias_deg(spec: dict) -> float:
    """``split_aileron.bias_deg`` of a split-aileron tailless spec (0 when absent: opt-in)."""
    fw = options(spec) or {}
    sa = fw.get("split_aileron") if isinstance(fw.get("split_aileron"), dict) else {}
    return float(sa.get("bias_deg") or 0.0)


def bias_drag(spec: dict, asm) -> dict | None:
    """Cruise ΔC_D0 of the split pre-deflection δ0 (``split_aileron.bias_deg``, opt-in): both sides, both leaves
    open δ0 → 2·K_f (c_f/c)^1.38 (S_f/S)·2 sin²δ0 (McCormick 1995 Eq. 3.45). None when no bias. The bias must keep
    2δ0 ≤ δ_max so the yaw capacity is unchanged (the far side closes to 0 at full differential)."""
    b0 = bias_deg(spec)
    if b0 <= 0:
        return None
    fw = options(spec) or {}
    sa = fw.get("split_aileron") or {}
    miss = _req(sa, ("eta_inner", "eta_outer", "cf_c", "delta_max_deg"))
    if miss:
        return {"bias_deg": b0, "status": "unassessed", "dCD0": None,
                "issues": [f"split_aileron sem {miss} — arrasto da pré-deflexão unassessed"]}
    geom = split_geometry(asm, float(sa["eta_inner"]), float(sa["eta_outer"]), float(sa["cf_c"]))
    K_f = float(sa.get("K_f") or K_SPLIT_MCCORMICK)
    one = split_drag_increment(geom["cf_c"], geom["S_f"] / geom["S"], b0, None, K_f)
    out = {"bias_deg": b0, "status": "assessed", "dCD0": 2 * one, "dCD0_one_side": one, "K_f": K_f,
           "source": BIAS_SOURCE}
    if 2 * b0 > float(sa["delta_max_deg"]) + 1e-9:
        out["issues"] = [f"2·δ0 = {2 * b0:g}° > δ_max {sa['delta_max_deg']}°: a capacidade de guinada diminui"]
    return out


def _req(block: dict | None, keys) -> list[str]:
    return [k for k in keys if not isinstance(block, dict) or block.get(k) is None]


def evaluate(res, spec: dict, md: dict, uav: bool) -> dict:
    """Split-aileron sizing cases + bare/SAS lateral modes for a tailless assembly (see module docstring).

    ``md`` is the bare-airframe output of :func:`.handling.dynamics` at cruise. Never raises for missing inputs:
    the affected parts are ``unassessed``."""
    from acdt import G0
    from acdt.core.atmosphere import isa
    from ..stability import _modes_lat, lateral_matrix
    from .assembly import Assembly
    from .handling import body_cnb, vertical_volume
    from .sizing import main_wing, run_assembly_avl
    fw = options(spec) or {}
    asm = Assembly.from_dict(spec["assembly"])
    _, gw = main_wing(asm)
    S, b, c = gw["S"], gw["b"], gw["mac"]
    I = md["inertia"]
    m, Ixx, Izz = I["m"], I["Ixx"], I["Izz"]
    x_cg, z_cg = I["x_cg"], I.get("z_cg", 0.0)
    rep: dict = {"schema": "tailless_split_aileron", "level": "L1", "issues": [], "notes": [],
                 "sources": {"split_drag": SPLIT_DRAG_SOURCE, "side_effects": SIDE_EFFECT_SOURCE,
                             "crosswind": CROSSWIND_SOURCE,
                             "avl": "AVL é invíscido: não vê o arrasto de perfil do split aileron (efeito dominante); "
                                    "usado só para a célula nua e a elevon"}}
    c_vt = vertical_volume(asm, gw["x_ac"])
    rep["c_vt_measured"] = c_vt
    if c_vt > 1e-6:
        rep["issues"].append(f"yaw_control=split_aileron mas a montagem tem superfície vertical (c_VT {c_vt:.3f}); "
                             "avaliado na mesma, com a deriva desenhada")
    sas_on = fw.get("sas")
    sas_on = bool(uav) if sas_on is None else bool(sas_on)
    rep["sas_enabled"] = sas_on
    rep["sas_default_note"] = ("PRESSUPOSTO (João, 10 nov 2026): piloto automático ativo é hipótese base no UAV"
                               if fw.get("sas") is None and uav else None)
    # ---- split aileron geometry
    sa = fw.get("split_aileron") if isinstance(fw.get("split_aileron"), dict) else None
    K_f = float((sa or {}).get("K_f") or K_SPLIT_MCCORMICK)
    miss = _req(sa, ("eta_inner", "eta_outer", "cf_c", "delta_max_deg"))
    C1 = dmax = geom = None
    if miss:
        rep["issues"].append(f"split_aileron sem {miss} — capacidade de guinada unassessed (nunca coeficientes inventados)")
    else:
        geom = split_geometry(asm, float(sa["eta_inner"]), float(sa["eta_outer"]), float(sa["cf_c"]))
        C1 = yaw_power(geom, K_f)
        dmax = float(sa["delta_max_deg"])
        rep["split_aileron"] = {**geom, "K_f": K_f, "C1": C1, "delta_max_deg": dmax,
                                "capacity_dCn": capacity(C1, dmax),
                                "dCD_at_max_one_side": split_drag_increment(geom["cf_c"], geom["S_f"] / S, dmax, None, K_f),
                                "side_effects_at_max": side_effects(geom, C1, dmax, z_cg, K_f),
                                "rate_max_deg_s": sa.get("rate_max_deg_s"),
                                "rate_source": sa.get("rate_source")}
    el = fw.get("elevon") if isinstance(fw.get("elevon"), dict) else None
    miss_el = _req(el, ("eta_inner", "eta_outer", "cf_c"))
    el_max = float((el or {}).get("max_deg") or ELEVON_MAX_DEFAULT_DEG)
    if miss_el:
        rep["issues"].append(f"elevon sem {miss_el} — C_lδa/C_nδa desconhecidos: vento cruzado e coordenação unassessed")
    elif sa is not None and not miss:
        if float(el["eta_outer"]) > float(sa["eta_inner"]) + 1e-9 and float(el["eta_inner"]) < float(sa["eta_outer"]):
            rep["issues"].append("elevon e split aileron sobrepõem-se em envergadura — PRESSUPOSTO: comandos somados "
                                 "na mesma superfície (não verificado)")
    cnb_body, _ = body_cnb(asm, S, b)
    # ---- cruise
    at = isa(res.cruise_altitude)
    u0 = float(res.cruise_speed)
    mach = u0 / at.a
    qS = 0.5 * at.rho * u0**2 * S
    A_cr = np.array(md["A_lat"], float)
    cr = {"qSb_Izz": qS * b / Izz, "b": b, "u0": u0}
    d_cr = None
    if not miss_el:
        d_cr = avl_with_elevon(asm, md["derivatives"]["CL"], mach, x_cg, z_cg, el)
        d_cr["Cnb"] += cnb_body
        rep["elevon_cruise"] = {k: d_cr[k] for k in ("alpha_deg", "Clda", "Cnda", "CYda")}
        if d_cr["alpha_deg"] > ATTACHED_FLOW_ALPHA_MAX_DEG:
            rep["issues"].append(f"α de cruzeiro (AVL) {d_cr['alpha_deg']:.1f}° > {ATTACHED_FLOW_ALPHA_MAX_DEG:.0f}°: fora do "
                                 "envelope em que ΔC_l ≈ ΔC_m ≈ 0 do split (Löchert et al. 2019) — efeitos secundários "
                                 "unassessed")
    # ---- approach (sea level, U = 1.1 V_S0)
    rho0 = isa(0.0).rho
    W = m * G0
    hl = getattr(res, "highlift", None)
    CLmax_l = getattr(hl, "CLmax_landing", None) if hl is not None else None
    ap = A_ap = d_ap = None
    if CLmax_l:
        Vs0 = math.sqrt(2 * W / (rho0 * S * CLmax_l))
        U = 1.1 * Vs0
        q_ap = 0.5 * rho0 * U**2
        CL_ap = W / (q_ap * S)
        mach_ap = U / isa(0.0).a
        if not miss_el:
            d_ap = avl_with_elevon(asm, CL_ap, mach_ap, x_cg, z_cg, el)
        else:
            a2 = run_assembly_avl(asm, mach=mach_ap, x_ref=x_cg, z_ref=z_cg, with_bodies=False, CL=CL_ap)
            d_ap = {k: float(a2.get(k, 0.0) or 0.0) for k in ("CYb", "CYp", "CYr", "Clb", "Clp", "Clr", "Cnb", "Cnp", "Cnr")}
            d_ap["alpha_deg"] = a2.get("alpha_deg")
        d_ap["Cnb"] += cnb_body
        A_ap = lateral_matrix(d_ap, q_ap * S, b, m, Ixx, Izz, U)
        ap = {"qSb_Izz": q_ap * S * b / Izz, "b": b, "u0": U, "V_S0": Vs0, "U": U, "CL": CL_ap,
              "CLmax_landing": CLmax_l, "alpha_deg": d_ap.get("alpha_deg"), "Cnb_total": d_ap["Cnb"],
              "Cnr": d_ap["Cnr"], "Clb": d_ap["Clb"]}
        rep["approach"] = dict(ap)
        if d_ap.get("alpha_deg") is not None and d_ap["alpha_deg"] > ATTACHED_FLOW_ALPHA_MAX_DEG:
            rep["issues"].append(f"α de aproximação (AVL) {d_ap['alpha_deg']:.1f}° > {ATTACHED_FLOW_ALPHA_MAX_DEG:.0f}°: "
                                 "fora do envelope em que ΔC_l ≈ ΔC_m ≈ 0 (Löchert et al. 2019) — efeitos "
                                 "secundários do split aileron unassessed nessa condição; derivadas AVL (lineares) "
                                 "a este α são indicativas")
            rep["approach"]["outside_side_effect_envelope"] = True
    else:
        rep["issues"].append("CLmax de aterragem desconhecido — caso de aproximação unassessed")
    # ---- bare airframe (information, never hidden)
    lat_bare_cr = _modes_lat(A_cr)
    rep["bare"] = {"cruise": lat_bare_cr, "approach": _modes_lat(A_ap) if A_ap is not None else None,
                   "derivatives_cruise": {k: md["derivatives"].get(k) for k in ("Cnb_total", "Cnr", "Clb", "Clp")}}
    # ---- sizing cases
    cw_kt = fw.get("crosswind_kt")
    if ap is not None and d_ap is not None and not miss_el:
        Vw = float(cw_kt) * KT if cw_kt is not None else 0.2 * ap["V_S0"]
        rep["crosswind"] = crosswind_case(d_ap, ap["CL"], ap["U"], Vw, C1, dmax, el_max)
        if cw_kt is not None:
            rep["crosswind"]["fonte"] = "utilizador (crosswind_kt)"
        rep["crosswind"]["crab_note"] = ("aproximação em crab: β aerodinâmico ≈ 0 e o termo C_nβ·β desaparece; o "
                                         "decrab no toque é dinâmico e fica unassessed — o caso dimensionante "
                                         "aqui é a derrapagem estabilizada (Roskam AFD I 4.2 / Sadraey 12.6.2.3)")
    else:
        rep["crosswind"] = {"status": "unassessed", "ok": None,
                            "issues": ["falta elevon ou caso de aproximação (C_nδa desconhecido ≠ 0)"]}
    if d_cr is not None:
        rep["coordination"] = coordination_case(d_cr, u0, at.rho, S, b, Ixx, "B", 1, el_max, C1, dmax)
    else:
        rep["coordination"] = {"status": "unassessed", "ok": None, "issues": ["falta elevon (C_nδa desconhecido ≠ 0)"]}
    rep["lateral_gust"] = None
    turb = None
    tcat = str(fw.get("turbulence") or "moderate").lower()
    if tcat in W20_KT:
        turb = dryden_lateral(SCREEN_HEIGHT_FT * 0.3048, W20_KT[tcat])
        turb["category"] = tcat
        turb["source"] = ("MIL-F-8785C 3.7 Dryden baixa altitude (W20 15/30/45 kt), h = 50 ft (14 CFR 23.75); "
                          "forma verificada na documentação MathWorks Aerospace Blockset")
        rep["turbulence"] = turb
    else:
        rep["issues"].append(f"turbulence '{tcat}' desconhecida (light/moderate/severe) — autoridade unassessed")
    # ---- SAS
    if sas_on:
        from .tailless_actuation import TIME_DELAY_LIMITS_S
        acfg = fw.get("actuators") if isinstance(fw.get("actuators"), dict) else {}
        lag_d, dly_d = acfg.get("lag_s"), acfg.get("delay_s")
        act = (float(lag_d or 0.0), float(dly_d) if dly_d is not None else
               (0.0 if lag_d is not None else TIME_DELAY_LIMITS_S[0]))
        sas = design_sas(A_cr, cr, A_ap, ap, turb, cat_cruise=_cat_cruise(res), actuator=act)
        if sas.get("status") != "ok":
            ideal = design_sas(A_cr, cr, A_ap, ap, turb, cat_cruise=_cat_cruise(res))
            sas["ideal_actuator"] = {k: ideal.get(k) for k in ("status", "k_beta", "k_r", "sigma_u")}
        rep["sas"] = {k: v for k, v in sas.items() if k != "score"}
        if sas.get("status") == "ok":
            rep["sas"]["Cnb_aug_cruise"] = md["derivatives"].get("Cnb_total", 0.0) + sas["k_beta"]
            rep["sas"]["Cnr_aug_cruise"] = md["derivatives"].get("Cnr", 0.0) - sas["k_r"]
            rep["sas"]["A_lat_cruise"] = close_loop(A_cr, sas["k_beta"], sas["k_r"], cr["qSb_Izz"], b, u0)
            rep["sas"]["feedback"] = ("u = ΔC_n,cmd = k_β·β − k_r·r̂ (r̂ = r b/2V) pelos split ailerons; ganhos "
                                      "escolhidos com o modelo de atuador (lag + atraso, tailless_actuation); "
                                      "ganhos em coeficiente (∝ 1/q̄)")
        rep["authority"] = sas_authority(sas, rep.get("crosswind"), C1, dmax,
                                         (sa or {}).get("rate_max_deg_s"))
    # ---- required span fraction per case (η_outer, c_f/c and δ_max fixed); None = whole semispan not enough
    if geom is not None:
        cases = {"crosswind": (rep.get("crosswind") or {}).get("dCn_required"),
                 "coordination": (rep.get("coordination") or {}).get("dCn_required"),
                 "sas_turbulence": (rep.get("authority") or {}).get("demand_dCn")}
        sr = {"eta_outer": geom["eta_outer"], "cf_c": geom["cf_c"], "delta_max_deg": dmax,
              "span_fraction_current": geom["eta_outer"] - geom["eta_inner"]}
        for k, v in cases.items():
            if v is not None:
                sr[k] = {"demand_dCn": abs(v),
                         "span_fraction": span_required(asm, abs(v), geom["eta_outer"], geom["cf_c"], dmax, K_f)}
        rep["span_required"] = sr
    rep["mass_note"] = ("massa dos atuadores do split aileron: incluir em weights.components.items (momento de "
                        "charneira de split flap sem método citado no acdt — servo unassessed)")
    # ---- follow-up assessments (actuator dynamics, hinge/servo/mass, lateral gust, trim, crosswind options)
    from . import tailless_followup as _fu
    ctx = {"fw": fw, "sa": sa, "el": el, "el_max": el_max, "geom": geom, "C1": C1, "dmax": dmax, "K_f": K_f,
           "S": S, "b": b, "c": c, "m": m, "Ixx": Ixx, "Izz": Izz, "x_cg": x_cg, "z_cg": z_cg, "A_cr": A_cr,
           "cr": cr, "A_ap": A_ap, "ap": ap, "d_cr": d_cr, "d_ap": d_ap if not miss_el else None,
           "mach_cr": mach, "mach_ap": (ap["U"] / isa(0.0).a) if ap else None, "rho_cr": at.rho,
           "cnb_body": cnb_body, "cat_cruise": _cat_cruise(res)}
    try:
        _fu.extend(rep, res, spec, md, asm, ctx)
    except Exception as ex:  # never hide the core assessment behind a follow-up failure
        rep["followup_error"] = str(ex)
        rep["issues"].append(f"avaliações complementares falharam: {ex}")
    return rep


def _cat_cruise(res) -> str:
    dy = getattr(res, "dynamics", None)
    return str(dy.get("hq_category", "B")) if isinstance(dy, dict) else "B"


# ------------------------------------------------------------------------------------------- hq rows
def _modes_lat_closed(A) -> dict:
    from ..stability import _modes_lat
    return _modes_lat(np.array(A, float))


def hq_row(r: dict, ok_bare, msg_bare: str, hq_sas: dict | None, auth_ok, lreq: int, tl: dict):
    """hq:dutch_roll / spiral / roll for a split-aileron tailless: with SAS active the closed-loop level decides,
    and only when the required authority/rate is within the split-aileron capability (unknown → None)."""
    lv_b = r["nível"]
    bare_txt = f"célula nua (sem SAS): Nível {lv_b if lv_b < 4 else '>3'} — informativo"
    if tl.get("error"):
        return ok_bare, msg_bare + f" [split ailerons: avaliação falhou — {bare_txt}]"
    if not tl.get("sas_enabled"):
        return ok_bare, msg_bare + f" [asa voadora sem deriva, split ailerons, SAS desligado: {bare_txt}]"
    sas = tl.get("sas") or {}
    if sas.get("status") != "ok" or not hq_sas or r["key"] not in hq_sas:
        return False, msg_bare + f" [SAS sem ganhos viáveis — {bare_txt}]"
    rs = hq_sas[r["key"]]
    v = rs["valor"]
    vs = f"{v:.3g}" if isinstance(v, float) else str(v)
    lv_ok = rs["nível"] <= lreq
    if ok_bare is None and r["key"] == "spiral":
        return None, msg_bare + " [com SAS: espiral também depende de Γ declarado]"
    a = tl.get("authority") or {}
    dyn = tl.get("actuator_dynamics") or {}
    act_txt = ""
    if r["key"] == "dutch_roll" and dyn.get("level_worst") is not None:
        lv_act = dyn["level_worst"]
        act_txt = (f"; com atuador (lag {dyn['lag_s']:.3f} s, atraso {dyn['delay_s']:.3f} s): Nível "
                   f"{lv_act if lv_act < 4 else '>3'}")
        lv_ok = lv_ok and lv_act <= lreq
    if auth_ok is True:
        ok = lv_ok
        tag = "autoridade e taxa dentro da capacidade dos split ailerons"
    elif auth_ok is False:
        ok = False
        tag = "autoridade/taxa necessária EXCEDE a capacidade dos split ailerons"
    else:
        ok = None
        tag = "autoridade/taxa unassessed (" + "; ".join(a.get("issues") or ["dados em falta"]) + ")"
    msg = (f"montagem com SAS (k_β {sas['k_beta']:.3f}/rad, k_r {sas['k_r']:.3f}): {rs['modo']} = {vs} → Nível "
           f"{rs['nível'] if rs['nível'] < 4 else '>3'} ({rs['ref']}){act_txt}; {tag}; {bare_txt}")
    return ok, msg


def extra_rows(tl: dict) -> list:
    """hq:yaw_crosswind, hq:yaw_coordination, hq:sas_authority (verification keys; unknown → None)."""
    rows = []
    if tl.get("error"):
        return [("hq:yaw_crosswind", None, f"split ailerons: avaliação falhou ({tl['error']})")]
    cw = tl.get("crosswind") or {}
    if cw.get("status") == "assessed":
        d = cw.get("delta_split_deg")
        rows.append(("hq:yaw_crosswind", cw["ok"],
                     f"vento cruzado {cw['crosswind_kt']:.1f} kt a U {cw['U_m_s']:.1f} m/s (β {cw['beta_deg']:.1f}°): "
                     f"ΔC_n {cw['dCn_required']:+.5f} → split {('%.1f°' % d) if d is not None else '>90°'} "
                     f"(máx {tl['split_aileron']['delta_max_deg']:.0f}°), elevon {cw['delta_a_deg']:+.1f}°, "
                     f"pranchamento {cw['bank_deg']:+.1f}°; máx. {cw.get('crosswind_max_kt', float('nan')):.1f} kt "
                     f"({cw['fonte']})"))
    else:
        rows.append(("hq:yaw_crosswind", None, "split ailerons: vento cruzado unassessed — "
                     + "; ".join(cw.get("issues") or tl.get("issues") or ["dados em falta"])))
    co = tl.get("coordination") or {}
    if co.get("status") == "assessed":
        d = co.get("delta_split_deg")
        rows.append(("hq:yaw_coordination", co["ok"],
                     f"coordenação contra guinada adversa ({co['requirement']}): ΔC_n entrada {co['dCn_entry']:+.5f}, "
                     f"rolamento {co['dCn_steady_roll']:+.5f}, viragem {co['turn_bank_deg']:.0f}° "
                     f"{co['dCn_turn']:+.5f} → split {('%.1f°' % d) if d is not None else '>90°'}"))
    else:
        rows.append(("hq:yaw_coordination", None, "split ailerons: coordenação unassessed — "
                     + "; ".join(co.get("issues") or ["dados em falta"])))
    if tl.get("sas_enabled"):
        a = tl.get("authority") or {}
        if a.get("demand_dCn") is not None:
            rr = a.get("rate_required_deg_s")
            rows.append(("hq:sas_authority", a.get("ok"),
                         f"SAS: 3σ turbulência (Dryden MIL-F-8785C, aproximação) |ΔC_n| "
                         f"{a['dCn_3sigma_turbulence']:.5f} vs capacidade {a['capacity_dCn']:.5f}"
                         + (f" (somado ao vento cruzado {a['dCn_crosswind_info']:.5f}: "
                            f"{'cabe' if a.get('combined_with_crosswind_ok') else 'não cabe'})"
                            if a.get('dCn_crosswind_info') is not None else "") + f"; taxa {('%.0f' % rr) if rr is not None else '?'} °/s vs "
                         + (f"{a['rate_max_deg_s']:.0f}" if a.get('rate_max_deg_s') is not None else '? (unassessed)') + " °/s"
                         + (lambda w: (f"; com atuador: 3σ {w['dCn_3sigma']:.5f}, taxa "
                                       f"{('%.0f' % w['rate_required_deg_s']) if w.get('rate_required_deg_s') is not None else '?'} °/s"
                                       if w.get("dCn_3sigma") is not None else f"; com atuador: {w.get('issue', 'unassessed')}")
                            if w else "")(a.get("with_actuator"))))
        else:
            rows.append(("hq:sas_authority", a.get("ok"), "SAS: autoridade " + (a.get("status") or "unassessed")
                         + " — " + "; ".join(a.get("issues") or [])))
    from . import tailless_followup as _fu
    rows += _fu.rows(tl)
    return rows
