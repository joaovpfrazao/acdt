"""Aeroelasticity — fidelity ladder (docs/ARCHITECTURE.md §5.1).

Phase 3 (implemented here): classical low-fidelity checks on the wing box sized in
:mod:`structures` (EI(y), GJ(y) of the buckling-driven box, Bredt–Batho GJ = 4A²G/∮ds/t):

* **Torsional divergence** — strip theory on the cantilever wing, (GJ θ')' + q e c² a_w θ = 0, θ(root) = 0,
  GJ θ'(tip) = 0, solved as a generalised eigenproblem with linear finite elements (Wright & Cooper 2015,
  Ch. 8; Bisplinghoff, Ashley & Halfman 1955, Ch. 8). Verified against the uniform closed form
  q_D = π² GJ / (4 e c² a_w s²).
* **Aileron reversal** — same strip model with the aileron term on its span,
  (GJ θ')' + q e c² a_w θ = −q c² (e a_C + b_C) β, rolling moment ∫ y c (a_w θ + a_C β) dy = 0 (Wright & Cooper
  Ch. 9). Flap effectiveness from thin-aerofoil theory (Glauert 1926): a_C = 2(π − φ_h + sin φ_h),
  b_C = −½ sin φ_h (1 − cos φ_h), φ_h = arccos(2E − 1), E = flap chord ratio.
* **Binary bending–torsion flutter** — Wright & Cooper (2015) Ch. 11 assumed-modes model: bending (y/s)²,
  torsion y/s about the flexural axis, quasi-steady strip aerodynamics with the unsteady pitch-damping term
  M_θ̇ = −1.2; M q̈ + ρV B q̇ + (ρV² C + K) q = 0 integrated spanwise with c(y), EI(y), GJ(y), m(y);
  eigenvalues swept in V (sea-level ρ, so V is EAS).
* **FAA AEER-45 simplified criteria** (Airframe & Equipment Engineering Report 45, accepted by legacy
  14 CFR 23.629(d) / AC 23.629-1B): wing torsional flexibility factor F = Σ s θ c² / M over the aileron span
  [ft, rad/(ft·lb)]; applicability: V_D < 260 KEAS, M < 0.5, no large outer-wing mass, no T-tail, fixed
  stabiliser. The limit curve is used in the approximation F_max = 200/V_D² [V_D in mph] (Sport Aviation, July
  1992, transcription of AEER-45 Fig. 1 — VERIFY against the original). Aileron mass-balance (K/I) criteria need
  aileron inertia data → reported "not evaluated".
* **Margins**: legacy 14 CFR 23.629(c) — free from flutter/divergence/reversal up to 1.2 V_D (EAS); current
  14 CFR / CS 23.2245 "sufficiently beyond" the envelope; STANAG 4671 USAR.629 (verify edition).

Phase 3 also: **static aero-structural coupling** :func:`static_aerostructural` — OpenAeroStruct
(Jasa et al., SMO 2018; NASA/U. Michigan MDO Lab, Apache-2.0) VLM + wingbox FEM on OpenMDAO.

Phase 4: FEM modal + doublet-lattice flutter (p-k) in :mod:`.hifi.flutter` (CalculiX + PanelAero), Nastran
SOL 145 deck via pyNastran (:mod:`.hifi.nastran`); certification margin check; optional calibration of the strip
V_F (``assumptions.calibration.apply: [flutter]``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from acdt import G0
from acdt.core._stub import not_implemented
from acdt.core.atmosphere import RHO0, isa

WRIGHT_COOPER = "Wright & Cooper, Introduction to Aircraft Aeroelasticity and Loads, 2nd ed., 2015"
BAH = "Bisplinghoff, Ashley & Halfman, Aeroelasticity, 1955"
HODGES_PIERCE = "Hodges & Pierce, Introduction to Structural Dynamics and Aeroelasticity, 2nd ed., 2011"
AEER45 = "FAA Airframe & Equipment Engineering Report No. 45 (Simplified Flutter Prevention Criteria); AC 23.629-1B"
M_THETADOT = -1.2  # Wright & Cooper unsteady pitch-damping derivative (quasi-steady model)


# ----------------------------------------------------------------- strip model of the wing
@dataclass
class WingStrip:
    """Spanwise beam/strip model of one wing half, root clamped at y0 (fuselage side)."""
    y: np.ndarray        # nodes [m], y0 ... s
    c: np.ndarray        # chord [m]
    EI: np.ndarray       # [N m²]
    GJ: np.ndarray       # [N m²]
    m: np.ndarray        # mass per unit span [kg/m]
    e: float | np.ndarray    # flexural axis aft of the aerodynamic centre, fraction of chord (per node, Phase 5)
    x_f: float | np.ndarray  # flexural (elastic) axis, fraction of chord from LE
    x_cg: float          # section mass centre, fraction of chord from LE
    a_w: float           # section lift-curve slope [1/rad]
    note: str = ""


def strip_model(wing, box, wing_mass_kg: float, a_w: float = 2 * math.pi, x_cg: float | None = None,
                y_root: float = 0.0, n: int = 60) -> WingStrip:
    """Build the strip model from the parametric wing and a :class:`structures.WingBoxResult`.
    Elastic axis at mid-box (consistent with the torsion loads of :func:`structures.shear_moment_diagram`).
    Mass per span ∝ chord (as the inertia relief); chordwise mass centre default = mid-chord (uniform section,
    Wright & Cooper Ch. 11 assumption)."""
    from .structures import chord_at
    s = wing.span / 2
    y = np.linspace(y_root, s, n + 1)
    c = chord_at(wing, y)
    EI = np.interp(y, box.y, box.EI)
    GJ = np.interp(y, box.y, box.GJ)
    area_half = np.trapezoid(c, y)
    m = 0.5 * wing_mass_kg * c / area_half
    if box.details.get("x_sc_c") is not None:      # Phase 5: shear centre of the real section
        x_f = np.interp(y, box.y, box.details["x_sc_c"])
    else:
        x_f = 0.5 * (wing.box.front_spar_xc + wing.box.rear_spar_xc)
    return WingStrip(y, c, EI, GJ, m, x_f - 0.25, x_f, 0.5 if x_cg is None else x_cg, a_w)


def _fe_torsion(ws: WingStrip, weight):
    """Linear FE: K = ∫ GJ N_i' N_j', A = ∫ w N_i N_j (w = weight(y) per node, element mean). Root node removed."""
    y, ne = ws.y, len(ws.y) - 1
    K = np.zeros((ne + 1, ne + 1))
    A = np.zeros_like(K)
    for k in range(ne):
        L = y[k + 1] - y[k]
        gj = 0.5 * (ws.GJ[k] + ws.GJ[k + 1])
        wk = 0.5 * (weight[k] + weight[k + 1])
        K[k:k + 2, k:k + 2] += gj / L * np.array([[1, -1], [-1, 1]])
        A[k:k + 2, k:k + 2] += wk * L / 6 * np.array([[2, 1], [1, 2]])
    return K[1:, 1:], A[1:, 1:]


def torsional_divergence_speed(ws: WingStrip, rho: float = RHO0) -> dict:
    """Divergence dynamic pressure q_D (smallest positive eigenvalue of K θ = q A θ, A from e c² a_w) and the
    corresponding speed at density ``rho`` (EAS if rho = ρ0). e ≤ 0 (axis ahead of the a.c.) → no divergence."""
    if np.all(np.asarray(ws.e) <= 0):
        return {"q_D": math.inf, "V_div": math.inf, "note": "eixo elástico à frente do c.a.: sem divergência"}
    K, A = _fe_torsion(ws, ws.e * ws.c**2 * ws.a_w)
    lam = np.linalg.eigvals(np.linalg.solve(A, K)).real
    lam = lam[lam > 0]
    qD = float(lam.min()) if lam.size else math.inf
    return {"q_D": qD, "V_div": math.sqrt(2 * qD / rho), "note": "teoria das faixas, a_w 2D"}


def glauert_flap(E: float) -> tuple[float, float]:
    """Thin-aerofoil flap derivatives (Glauert 1926): a_C = ∂cl/∂β, b_C = ∂cm_c/4/∂β [1/rad], E = c_f/c."""
    ph = math.acos(2 * E - 1)
    return 2 * (math.pi - ph + math.sin(ph)), -0.5 * math.sin(ph) * (1 - math.cos(ph))


def control_span_mask(ws: WingStrip, surface: dict) -> np.ndarray:
    """Spanwise flap mask χ(y) ∈ {0, 1} for a trailing-edge surface.

    Flying-wing surfaces give ``eta_inner`` / ``eta_outer`` as fractions of the *full* semi-span
    (centreline to tip, as in ``assembly.tailless.split_geometry``). A conventional aileron gives
    ``span_fraction`` of the *exposed* semi-span, measured inboard from the tip (Phase 3 default).
    """
    s, y0 = float(ws.y[-1]), float(ws.y[0])
    if surface.get("eta_inner") is not None and surface.get("eta_outer") is not None:
        yi = float(surface["eta_inner"]) * s
        yo = float(surface["eta_outer"]) * s
        return ((ws.y >= yi - 1e-9) & (ws.y <= yo + 1e-9)).astype(float)
    frac = float(surface.get("span_fraction", 0.35))
    return (ws.y >= s - frac * (s - y0) - 1e-9).astype(float)


def control_effectiveness(ws: WingStrip, chi, cf_c: float, rho: float = RHO0) -> dict:
    """Torsional roll-control effectiveness of a trailing-edge flap with spanwise mask ``χ`` and
    chord ratio ``c_f/c``.

    Reversal q_R is the first dynamic pressure where the rolling moment per unit flap angle
    R(q) = ∫ y c (a_w θ₁ + a_C χ) dy = 0, with θ₁ from (K − q A) θ₁ = q f and
    f = −c² (e a_C + b_C) χ (Wright & Cooper 2015 Ch. 9; Bisplinghoff, Ashley & Halfman 1955 Ch. 8).
    Flap derivatives a_C, b_C from Glauert 1926 (sealed plain flap). Also returns the effectiveness
    η(q) = R(q)/R(0) below divergence.
    """
    from scipy.optimize import brentq
    chi = np.asarray(chi, float)
    aC, bC = glauert_flap(cf_c)
    K, A = _fe_torsion(ws, ws.e * ws.c**2 * ws.a_w)
    fdist = -ws.c**2 * (ws.e * aC + bC) * chi
    F = np.zeros(len(ws.y))
    for k in range(len(ws.y) - 1):
        L = ws.y[k + 1] - ws.y[k]
        F[k] += L / 6 * (2 * fdist[k] + fdist[k + 1])
        F[k + 1] += L / 6 * (fdist[k] + 2 * fdist[k + 1])
    F = F[1:]

    def R(q):
        th = np.concatenate([[0.0], np.linalg.solve(K - q * A, q * F)])
        return float(np.trapezoid(ws.y * ws.c * (ws.a_w * th + aC * chi), ws.y))

    R0 = R(0.0)
    qD = torsional_divergence_speed(ws, rho)["q_D"]
    qhi = 0.999 * qD if math.isfinite(qD) else 1e7

    def effectiveness(q):
        if not math.isfinite(q) or q < 0:
            return math.nan
        if math.isfinite(qD) and q >= 0.999 * qD:
            return math.nan
        if abs(R0) < 1e-18:
            return math.nan
        return R(q) / R0

    qs = np.geomspace(1.0, qhi, 200)
    vals = np.array([R(q) for q in qs])
    idx = np.where(np.sign(vals[:-1]) != np.sign(vals[1:]))[0]
    if idx.size == 0:
        return {"q_R": math.inf, "V_R": math.inf, "a_C": aC, "b_C": bC, "R": R, "R0": R0,
                "q_D": qD, "effectiveness": effectiveness, "chi": chi}
    qR = brentq(R, qs[idx[0]], qs[idx[0] + 1])
    return {"q_R": qR, "V_R": math.sqrt(2 * qR / rho), "a_C": aC, "b_C": bC, "R": R, "R0": R0,
            "q_D": qD, "effectiveness": effectiveness, "chi": chi}


def aileron_reversal_speed(ws: WingStrip, aileron_span_fraction: float, hinge_xc: float,
                           rho: float = RHO0) -> dict:
    """Reversal of a conventional outboard aileron (legacy Phase 3 interface).

    ``hinge_xc`` is the hinge x/c (so c_f/c = 1 − hinge_xc); ``aileron_span_fraction`` is the
    exposed-semispan fraction inboard from the tip. See :func:`control_effectiveness`.
    """
    chi = control_span_mask(ws, {"span_fraction": aileron_span_fraction})
    return control_effectiveness(ws, chi, 1.0 - hinge_xc, rho)


def flutter_matrices(ws: WingStrip, M_thetadot: float = M_THETADOT):
    """Generalised M, K, B, C of the Wright & Cooper binary model (heave up, nose-up positive),
    modes φ_b = (η/s')², φ_t = η/s', η = y − y0, s' = s − y0."""
    y = ws.y
    eta = y - y[0]
    sp = eta[-1]
    pb, pt = (eta / sp) ** 2, eta / sp
    d2pb, dpt = 2 / sp**2, 1 / sp
    I = np.trapezoid
    xcg = (ws.x_cg - ws.x_f) * ws.c          # mass centre aft of the flexural axis [m]
    Icg = ws.m * ws.c**2 / 12                # uniform section about its centre
    M = np.array([[I(ws.m * pb**2, y), -I(ws.m * xcg * pb * pt, y)],
                  [-I(ws.m * xcg * pb * pt, y), I((Icg + ws.m * xcg**2) * pt**2, y)]])
    K = np.diag([I(ws.EI * d2pb**2, y), I(ws.GJ * dpt**2, y)])
    aw, e, c = ws.a_w, ws.e, ws.c
    B = 0.5 * np.array([[aw * I(c * pb**2, y), 0.0],
                        [aw * I(e * c**2 * pb * pt, y), -M_thetadot / 4 * I(c**3 * pt**2, y)]])
    C = 0.5 * np.array([[0.0, -aw * I(c * pb * pt, y)], [0.0, -aw * I(e * c**2 * pt**2, y)]])
    return M, K, B, C


def flutter_estimate_typical_section(ws: WingStrip, rho: float = RHO0, V_max: float = 300.0, n: int = 600,
                                     M_thetadot: float = M_THETADOT) -> dict:
    """Binary flutter sweep: eigenvalues of [[0, I], [−M⁻¹(K + ρV²C), −ρV M⁻¹B]] for V in (0, V_max].
    Flutter = first V where an oscillatory root's real part becomes positive (ζ < 0)."""
    M, K, B, C = flutter_matrices(ws, M_thetadot)
    Minv = np.linalg.inv(M)
    Vs = np.linspace(V_max / n, V_max, n)
    freq, damp = [], []
    VF, fF, Vdiv = math.inf, math.nan, math.inf
    prev = None
    for V in Vs:
        Aq = np.block([[np.zeros((2, 2)), np.eye(2)], [-Minv @ (K + rho * V**2 * C), -rho * V * Minv @ B]])
        lam = np.linalg.eigvals(Aq)
        osc = lam[lam.imag > 1e-9]
        osc = osc[np.argsort(osc.imag)]
        if len(osc) == 2:
            fr, zt = osc.imag / (2 * math.pi), -osc.real / np.abs(osc)
        else:  # one mode has become real (static divergence of the 2-DOF model)
            fr = np.array([osc.imag[0] / (2 * math.pi) if len(osc) else math.nan, math.nan])
            zt = np.array([-osc.real[0] / abs(osc[0]) if len(osc) else math.nan, math.nan])
            if not math.isfinite(Vdiv) and np.any((lam.real > 0) & (np.abs(lam.imag) < 1e-9)):
                Vdiv = float(V)
        freq.append(fr)
        damp.append(zt)
        if not math.isfinite(VF) and len(osc) and np.any(osc.real > 0):
            # interpolate the zero-damping crossing
            if prev is not None:
                j = int(np.argmax(osc.real))
                V0, z0 = prev
                z1 = zt[j] if j < len(zt) else 0.0
                VF = float(V0 + (V - V0) * z0[j] / (z0[j] - z1)) if np.isfinite(z0[j]) and z0[j] != z1 else float(V)
            else:
                VF = float(V)
            fF = float(osc.imag.max() / (2 * math.pi))
        prev = (V, zt)
    w0 = np.sqrt(np.diag(K) / np.diag(M)) / (2 * math.pi)
    return {"V_F": VF, "f_F": fF, "V_div_2dof": Vdiv, "V": Vs, "freq": np.array(freq), "damp": np.array(damp),
            "f_bending_Hz": float(w0[0]), "f_torsion_Hz": float(w0[1]), "M": M, "K": K, "B": B, "C": C}


FT, LBF = 0.3048, 4.4482216


def simplified_flutter_criteria_aeer45(ws: WingStrip, aileron_span_fraction: float, VD_eas: float,
                                       applicability: dict) -> dict:
    """AEER-45 wing torsional flexibility factor F = Σ s θ c²/M (aileron span) vs F_max = 200/V_D² [mph]."""
    s, y0 = ws.y[-1], ws.y[0]
    flex = np.concatenate([[0.0], np.cumsum(np.diff(ws.y) / (0.5 * (ws.GJ[1:] + ws.GJ[:-1])))])  # θ/M [rad/(N m)]
    on = ws.y >= s - aileron_span_fraction * (s - y0) - 1e-9
    yy, cc, ff = ws.y[on], ws.c[on], flex[on]
    integrand = (cc / FT) ** 2 * ff * (FT * LBF)  # c² [ft²] × θ/M [rad/(ft lb)]
    F = float(np.trapezoid(integrand, yy / FT))
    VD_mph = VD_eas / 0.44704
    Fmax = 200.0 / VD_mph**2
    V_crit = math.sqrt(200.0 / F) * 0.44704 if F > 0 else math.inf
    reasons = [k for k, ok in applicability.items() if not ok]
    return {"F": F, "F_max": Fmax, "V_crit_eas": V_crit, "ok": F <= Fmax, "applicable": not reasons,
            "not_applicable_because": reasons,
            "aileron_balance": "não avaliado — critérios K/I de equilíbrio de massa do aileron exigem a inércia do "
                               "aileron (Fase 4: dados de detalhe)"}


# ----------------------------------------------------------- static aero-structural (OpenAeroStruct)
def oas_available() -> bool:
    try:
        import openaerostruct  # noqa: F401
        import openmdao  # noqa: F401
        return True
    except ImportError:
        return False


def _oas_surface(wing, box, material: dict, ny: int = 15, nx: int = 3, stiff_factor: float = 1.0):
    """OpenAeroStruct ``wingbox`` surface built from the parametric wing and the acdt box.

    Mesh: trapezoidal planform (symmetry, left half, LE sweep from the c/4 sweep), linear chordwise spacing.
    Wing-box section: NACA-4 half-thickness between the spars (``data_x/y``), spar and skin thickness control
    points from the box at the OAS spanwise stations (CP order tip → root). OAS has one E, one G and equal upper
    and lower skins, so an *equivalent* skin matching EI(y) of the acdt box is used (E = E_cap for CFRP), and G is
    scaled to match GJ (ASSUMPTION; documented). The OAS von Mises failure index is therefore indicative only."""
    from .structures import chord_at, naca4_half_thickness
    s = wing.span / 2
    yy = np.linspace(-s, 0.0, ny)
    c = chord_at(wing, np.abs(yy))
    tanLE = math.tan(wing.sweep_at(0.0))
    mesh = np.zeros((nx, ny, 3))
    for i, f in enumerate(np.linspace(0, 1, nx)):
        mesh[i, :, 0] = np.abs(yy) * tanLE + f * c
        mesh[i, :, 1] = yy
    fs, rs = wing.box.front_spar_xc, wing.box.rear_spar_xc
    xd = np.linspace(fs, rs, 21)
    ht = naca4_half_thickness(xd, wing.tc_root)
    ycp = np.abs(np.linspace(-s, 0.0, 5))  # 5 CPs tip -> root (OAS b-spline, tip first)
    E = material.get("E_cap", material["E"])
    G = material.get("G", material["E"] / (2 * (1 + material["nu"])))
    web = np.interp(ycp, box.y, box.web_t)
    # equivalent single skin (OAS uses equal upper/lower skins): match EI(y) of the acdt box, then G to match GJ
    h, wb, tw = box.h_box, box.w_box, box.web_t
    teq = np.maximum((box.EI / E - 2 * tw * h**3 / 12) / (2 * wb * (h / 2) ** 2), 1e-4)
    skin = np.interp(ycp, box.y, teq)
    G_eff = float(np.median(box.GJ * (2 * wb / teq + 2 * h / tw) / (4 * (wb * h) ** 2)))
    return {
        "name": "wing", "symmetry": True, "S_ref_type": "projected", "mesh": mesh, "fem_model_type": "wingbox",
        "data_x_upper": xd.astype(complex), "data_x_lower": xd.astype(complex),
        "data_y_upper": ht.astype(complex), "data_y_lower": (-ht).astype(complex),
        "twist_cp": np.zeros(5), "spar_thickness_cp": np.maximum(web, 1e-4), "skin_thickness_cp": np.maximum(skin, 1e-4),
        "t_over_c_cp": np.interp(ycp, [0, s], [wing.tc_root, wing.tc_tip]),
        "original_wingbox_airfoil_t_over_c": wing.tc_root, "CL0": 0.0, "CD0": 0.0,
        "with_viscous": False, "with_wave": False, "k_lam": 0.05, "c_max_t": wing.xc_max_t,
        "E": E * stiff_factor, "G": G_eff * stiff_factor, "yield": material["sigma_cap"], "safety_factor": 1.5,
        "mrho": material["rho"], "strength_factor_for_upper_skin": 1.0, "wing_weight_ratio": 1.0,
        "exact_failure_constraint": False, "struct_weight_relief": False, "distributed_fuel_weight": False,
    }


def _oas_problem(surface, V, rho, a, mu=1.8e-5):
    import openmdao.api as om
    from openaerostruct.integration.aerostruct_groups import AerostructGeometry, AerostructPoint
    p = om.Problem(reports=False)
    iv = om.IndepVarComp()
    iv.add_output("v", val=V, units="m/s")
    iv.add_output("alpha", val=2.0, units="deg")
    iv.add_output("Mach_number", val=V / a)
    iv.add_output("re", val=rho * V / mu, units="1/m")
    iv.add_output("rho", val=rho, units="kg/m**3")
    iv.add_output("CT", val=1e-4, units="1/s")
    iv.add_output("R", val=1e6, units="m")
    iv.add_output("W0", val=1000.0, units="kg")
    iv.add_output("speed_of_sound", val=a, units="m/s")
    iv.add_output("load_factor", val=1.0)
    iv.add_output("empty_cg", val=np.zeros(3), units="m")
    p.model.add_subsystem("prob_vars", iv, promotes=["*"])
    p.model.add_subsystem("wing", AerostructGeometry(surface=surface))
    pt = "AS_point_0"
    p.model.add_subsystem(pt, AerostructPoint(surfaces=[surface]),
                          promotes_inputs=["v", "alpha", "Mach_number", "re", "rho", "CT", "R", "W0",
                                           "speed_of_sound", "empty_cg", "load_factor"])
    com = pt + ".wing_perf."
    for k in ("local_stiff_transformed", "nodes", "mesh"):
        p.model.connect("wing." + k, pt + ".coupled.wing." + k)
    p.model.connect("wing.nodes", com + "nodes")
    p.model.connect("wing.cg_location", pt + ".total_perf.wing_cg_location")
    p.model.connect("wing.structural_mass", pt + ".total_perf.wing_structural_mass")
    for k in ("Qz", "J", "A_enc", "htop", "hbottom", "hfront", "hrear", "spar_thickness", "t_over_c"):
        p.model.connect("wing." + k, com + k)
    p.setup()
    p.model.AS_point_0.coupled.nonlinear_solver = om.NonlinearBlockGS(maxiter=100, atol=1e-9, rtol=1e-9, iprint=-1,
                                                                      use_aitken=True)
    p.model.AS_point_0.coupled.linear_solver = om.LinearBlockGS(iprint=-1, maxiter=30, use_aitken=True)
    return p


def _oas_solve_CL(p, CL_target):
    """Angle of attack for CL = CL_target by secant iteration (VLM + linear FEM: CL(α) almost linear)."""
    def cl(al):
        p["alpha"] = al
        p.run_model()
        return float(p["AS_point_0.CL"][0])
    a0, a1 = 0.0, 4.0
    c0, c1 = cl(a0), cl(a1)
    for _ in range(12):
        a2 = a1 + (CL_target - c1) * (a1 - a0) / (c1 - c0)
        a0, c0, a1 = a1, c1, a2
        c1 = cl(a1)
        if abs(c1 - CL_target) < 1e-6 * max(1.0, abs(CL_target)):
            break
    if not np.isfinite(c1) or abs(c1 - CL_target) > 1e-3:
        raise RuntimeError(f"OAS: CL alvo {CL_target:.3f} não atingido (CL = {c1:.3f}) — possível divergência estática")
    al = a1
    mesh0, dm = p["wing.mesh"], p["AS_point_0.coupled.wing.def_mesh"]
    tip_dz = float(dm[0, 0, 2] - mesh0[0, 0, 2]) if dm.shape == mesh0.shape else float(np.max(np.abs(
        p["AS_point_0.coupled.wing.disp"][:, 2])))
    disp = p["AS_point_0.coupled.wing.disp"]
    return {"alpha_deg": al, "CL": float(p["AS_point_0.CL"][0]), "CDi": float(p["AS_point_0.CD"][0]),
            "tip_deflection_m": float(disp[0, 2]), "tip_twist_deg": float(np.degrees(disp[0, 4])),
            "failure": float(p["AS_point_0.wing_perf.failure"][0]), "struct_mass": float(p["wing.structural_mass"][0]),
            "_tip_dz": tip_dz}


def static_aerostructural(design, backend: str = "openaerostruct", ny: int = 15) -> dict:
    """Static aero-structural coupling with OpenAeroStruct (VLM + wingbox FEM, NLBGS-coupled) at the
    cruise point (n = 1) and the structural design point (n_lim at V_D EAS, sea level), compared with a
    rigid reference (E, G × 10⁴). ``design``: a DesignResult with ``structures`` (Phase 2/3 box).

    Returned performance effect: K_flex = K · CDi_flex/CDi_rigid at cruise CL (span-load redistribution by
    bending/twist), applied to the parabolic polar of the segment mission."""
    if backend != "openaerostruct":
        not_implemented(f"static aero-structural backend '{backend}'", "AeroSandbox (MIT)", "Phase 4")
    if design is None or getattr(design, "structures", None) is None:
        raise ValueError("static_aerostructural needs a converged design with the wing box (structures stage)")
    if not oas_available():
        raise ImportError("openaerostruct/openmdao not installed (pip install 'acdt[mdo]')")
    from .structures import MATERIALS
    res = design
    sr = res.structures
    w = res.config.wing
    mat = MATERIALS[w.box.material] if isinstance(w.box.material, str) else w.box.material
    W = res.sizing.W0 * G0
    at = isa(res.cruise_altitude)
    pts = {"cruise": (res.cruise_speed, at.rho, at.a, 1.0),
           "manobra (n_lim, V_D EAS, nível do mar)": (sr.vn.VD, RHO0, isa(0.0).a, sr.vn.n_limit_pos)}
    out = {"points": {}, "notes": []}
    for tag, stiff in (("flex", 1.0), ("rigid", 1e4)):
        surf = _oas_surface(w, sr.box, mat, ny=ny, stiff_factor=stiff)
        for name, (V, rho, a, n) in pts.items():
            p = _oas_problem(surf, V, rho, a)
            CLt = n * W / (0.5 * rho * V**2 * w.S)
            r = _oas_solve_CL(p, CLt)
            # lift-curve slope at the point (central difference in alpha)
            al = r["alpha_deg"]
            cls = []
            for d in (-0.25, 0.25):
                p["alpha"] = al + d
                p.run_model()
                cls.append(float(p["AS_point_0.CL"][0]))
            r["CLalpha_per_rad"] = (cls[1] - cls[0]) / math.radians(0.5)
            r["L_Di"] = r["CL"] / r["CDi"] if r["CDi"] > 0 else math.inf
            out["points"].setdefault(name, {})[tag] = r
    CLm = n * W / (0.5 * RHO0 * sr.vn.VD**2 * w.S)
    if CLm > res.highlift.CLmax_clean:
        out["notes"].append(f"ponto de manobra: CL = {CLm:.2f} > CLmax limpo {res.highlift.CLmax_clean:.2f} (n_lim de "
                            "rajada acima da linha de perda) — caso de carga válido para a deformação (VLM linear), α "
                            "não físico")
    cr = out["points"]["cruise"]
    ratio = cr["flex"]["CDi"] / cr["rigid"]["CDi"]
    out["K_ratio"] = ratio
    out["K_rigid"], out["K_flex"] = res.polar.K, res.polar.K * ratio
    out["notes"] += [
        "OpenAeroStruct VLM (sem viscoso/onda: só arrasto induzido) + FEM de caixão 'wingbox' acoplados por NLBGS; "
        "rígido = E, G × 10⁴",
        "secção do caixão: NACA-4 entre longarinas; espessuras de alma/revestimento do caixão acdt (5 pontos de "
        "controlo); revestimento único equivalente que reproduz EI(y) do caixão acdt e G ajustado para GJ (PRESSUPOSTO)",
        "sem alívio de peso estrutural nem de combustível na asa (conservativo para a deformação)",
        f"índice de falha OAS (von Mises/KS, σ_adm = σ_cap/1.5) na manobra: "
        f"{out['points']['manobra (n_lim, V_D EAS, nível do mar)']['flex']['failure']:+.3f} (< 0 = OK) — critério de "
        "resistência do OAS sobre o revestimento equivalente — INDICATIVO (o dimensionamento é o do caixão acdt)"]
    return out


def flexible_performance(res, aes: dict) -> dict:
    """Re-run the segment mission with K_flex (deformed-shape induced drag) and compare with the rigid polar."""
    from dataclasses import replace

    from .performance import PerfModel, mission_budget, simulate_mission
    m0 = PerfModel.from_result(res)
    m1 = replace(m0, K=aes["K_flex"])
    budget, _ = mission_budget(res)
    cruise = [L for L in res.legs if L.kind == "cruise"]
    loiter = [L for L in res.legs if L.kind != "cruise"]
    Vc = cruise[0].V if cruise else res.cruise_speed
    Vl = loiter[0].V if loiter else None
    out = {}
    for tag, m in (("rígido", m0), ("flexível", m1)):
        sim = simulate_mission(m, res.sizing.W0, budget, res.legs, res.cruise_altitude, Vc, Vl, stop="budget")
        out[tag] = {"range_km": sim.range_m / 1e3, "endurance_h": sim.endurance_s / 3600, "K": m.K}
    return out


# ------------------------------------------------------------------------- Phase 3 stage wrapper
@dataclass
class AeroelasticResult:
    VD_eas: float
    divergence: dict
    reversal: dict
    flutter: dict
    aeer45: dict
    margins: dict
    strip: WingStrip
    static: dict | None = None
    flex_perf: dict | None = None
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        f = self.flutter
        return {"VD_eas": self.VD_eas, "V_divergence_eas": self.divergence["V_div"],
                "V_reversal_eas": self.reversal["V_R"], "V_flutter_eas": f["V_F"], "f_flutter_Hz": f["f_F"],
                "f_bending_Hz": f["f_bending_Hz"], "f_torsion_Hz": f["f_torsion_Hz"],
                "aeer45": {k: v for k, v in self.aeer45.items()}, "margins": self.margins,
                "static_aerostructural": ({k: v for k, v in self.static.items()} if self.static else None),
                "flexible_performance": self.flex_perf, "notes": self.notes}


def aeer45_applicability(res, VD_eas: float) -> dict:
    """14 CFR 23.629(d) conditions for the AEER-45 simplified criteria (legacy Part 23)."""
    A = res.spec.assumptions
    VD_tas = VD_eas / math.sqrt(isa(res.cruise_altitude).sigma)
    tail = str(A.get("geometry", {}).get("tail_type", "conventional")).lower()
    n_eng = int(A["propulsion"].get("n_engines", 1))
    return {"V_D < 260 KEAS": VD_eas / 0.514444 < 260.0,
            "M < 0.5 (V_D à altitude de cruzeiro)": VD_tas / isa(res.cruise_altitude).a < 0.5,
            "sem cauda em T / não convencional": tail in ("conventional", "convencional"),
            "sem massas concentradas na asa exterior (motores na asa)": n_eng == 1,
            "estabilizador fixo, distribuição de massa usual (PRESSUPOSTO)": True}


def aeroelastic_analysis(res, opts: dict | None = None) -> AeroelasticResult:
    """Phase 3 aeroelastic checks on the converged design (wing box from :mod:`structures`)."""
    o = {"a_w": 2 * math.pi, "x_cg_chord": None, "margin_factor": 1.2, "static_aerostructural": True,
         **(opts or {})}
    sr = res.structures
    w = res.config.wing
    st_o = res.spec.assumptions.get("stability", {})
    ail_f, ail_cf = st_o.get("aileron_span_fraction", 0.35), st_o.get("aileron_cf_c", 0.25)
    wm = sr.wing_mass_raymer or sr.box.mass
    if res.weights is not None:
        wm = next((it.mass for it in res.weights.items if it.key == "wing"), wm)
    y_root = 0.5 * res.config.fuselage.max_diameter if res.config.fuselage else 0.0
    ws = strip_model(w, sr.box, wm, o["a_w"], o["x_cg_chord"], y_root)
    VD = sr.vn.VD
    div = torsional_divergence_speed(ws)
    rev = aileron_reversal_speed(ws, ail_f, 1 - ail_cf)
    fl = flutter_estimate_typical_section(ws, V_max=max(4 * VD, 150.0))
    from .hifi.calibration import load as _load_cal
    k_fl = _load_cal(res.spec.assumptions).get("k_flutter")
    if k_fl:
        fl["V_F_strip_uncalibrated"] = fl["V_F"]
        fl["V_F"] = fl["V_F"] * k_fl
        fl["k_flutter"] = k_fl
    ap = aeer45_applicability(res, VD)
    ae45 = simplified_flutter_criteria_aeer45(ws, ail_f, VD, ap)
    Vreq = o["margin_factor"] * VD
    margins = {}
    for k, V in (("divergence", div["V_div"]), ("reversal", rev["V_R"]), ("flutter", fl["V_F"])):
        margins[k] = {"V_eas": V, "V_required": Vreq, "margin": V / Vreq - 1 if math.isfinite(V) else math.inf,
                      "ok": V >= Vreq}
    notes = [f"massa da asa {wm:.2f} kg distribuída ∝ corda; CG da secção a {ws.x_cg:.2f} c; eixo elástico a "
             f"{float(np.mean(ws.x_f)):.3f} c ({'centro de corte da secção, média' if np.ndim(ws.x_f) else 'meio do caixão'}), "
             f"e = {float(np.mean(ws.e)):.3f} c atrás do c.a.; a_w = {ws.a_w:.3f}/rad (2D, teoria das "
             "faixas — sem correção 3D/compressibilidade)",
             f"encastramento na parede da fuselagem y0 = {y_root:.3f} m; EI/GJ do caixão {sr.box.method}",
             f"requisito: livre de flutter/divergência/inversão até {o['margin_factor']:g} V_D = {Vreq:.1f} m/s EAS "
             "(14 CFR 23.629(c) legado; CS/14 CFR 23.2245 'suficientemente além'; STANAG 4671 USAR.629 — verificar)",
             "flutter: modelo binário de modos assumidos (W&C Cap. 11), aerodinâmica quase-estacionária — ESTIMATIVA; "
             "a análise racional exige modos FEM + DLM (Fase 4)"]
    if k_fl:
        notes.append(f"flutter calibrado com a Fase 4 (FEM + DLM p-k): V_F = {k_fl:.3f} × V_F faixas "
                     f"({fl['V_F_strip_uncalibrated']:.1f} → {fl['V_F']:.1f} m/s EAS)")
    if not ae45["applicable"]:
        notes.append("AEER-45 NÃO aplicável: " + "; ".join(ae45["not_applicable_because"]) + " — valor informativo")
    if res.spec.assumptions.get("structures", {}).get("regulation", "") == "stanag_4671" or "stanag" in str(
            sr.vn.regulation):
        notes.append("UAV (STANAG 4671): AEER-45 é um critério FAA para aviação geral — informativo")
    out = AeroelasticResult(VD, div, rev, fl, ae45, margins, ws, notes=notes)
    if o["static_aerostructural"] and oas_available():
        try:
            out.static = static_aerostructural(res)
            out.flex_perf = flexible_performance(res, out.static)
        except Exception as ex:  # pragma: no cover
            out.notes.append(f"OpenAeroStruct falhou: {ex}")
    elif o["static_aerostructural"]:
        out.notes.append("OpenAeroStruct não instalado (pip install 'acdt[mdo]'): acoplamento estático não corrido")
    return out


def plot_flutter(ae: AeroelasticResult, path, title: str = ""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    f = ae.flutter
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    for j, lab in enumerate(("modo 1", "modo 2")):
        ax[0].plot(f["V"], f["freq"][:, j], label=lab)
        ax[1].plot(f["V"], 100 * f["damp"][:, j], label=lab)
    for a in ax:
        a.axvline(ae.VD_eas, color="k", ls="--", lw=0.8, label="V_D")
        a.axvline(1.2 * ae.VD_eas, color="r", ls=":", lw=0.8, label="1.2 V_D")
        a.set_xlabel("V EAS [m/s]")
        a.grid(alpha=0.3)
    ax[1].axhline(0, color="k", lw=0.6)
    ax[0].set_ylabel("frequência [Hz]")
    ax[1].set_ylabel("amortecimento ζ [%]")
    ax[1].legend(fontsize=7)
    fig.suptitle(title or "Flutter binário (Wright & Cooper, quase-estacionário)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


# ------------------------------------------------------------------------------------------- Phase 4
def flutter_fem_dlm(design, fem_out: dict, work, **kw) -> dict:
    """FEM modal + doublet-lattice p-k flutter (CalculiX modes from hifi.fem.run_box_fem, PanelAero DLM,
    Hassig p-k) — see :func:`acdt.domains.aircraft.hifi.flutter.run_flutter`. A Nastran SOL 145 deck of the
    same model: :func:`acdt.domains.aircraft.hifi.nastran.write_sol145`."""
    from .hifi.flutter import run_flutter
    return run_flutter(design, fem_out, work, **kw)


def flutter_margin_check(VF_g003: float, VF_g0: float, VD: float, factor: float = 1.2) -> dict:
    """Certification margin on a FEM/DLM V-g-f result: flutter-free to ``factor`` V_D with g ≤ 0.03
    (AC 23.629-1B practice; legacy 14 CFR 23.629; CS/14 CFR 23.2245; STANAG 4671 USAR.629 — verify)."""
    from .hifi.flutter import flutter_margin_check as _m
    return _m(VF_g003, VF_g0, VD, factor)
