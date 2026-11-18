"""Phase 5 — structural–aerodynamic wing optimisation (low fidelity, "Level A").

Design variables (continuous): front/rear spar x/c, t/c at root and tip, camber m (NACA 4-digit mean line at the
baseline p), linear geometric twist at the tip (washout < 0), rib pitch and a skin-thickness factor k_skin ≥ 1
(torsional stiffening for the aeroelastic constraints). Planform, MTOW and mission are those of the converged
pipeline design (``res``).

Analysis chain per design (no surrogate; all classical, cited in the called functions):

1. Section aerodynamics: NeuralFoil on the continuous NACA 4-digit coordinates (root and tip t/c, cruise Re) →
   a₀, α_L0, cm0, cl_max, cd(cl) (:mod:`wingbox.aero`).
2. Manoeuvre loads at n_limit and q(V_D) (as Phase 3): Glauert lifting line with **elastic twist**
   θ_e(y) = ∫ T/GJ dy about the shear-centre axis (fixed point), inertia relief ∝ chord → V, M, T.
3. Sizing: the Phase 3 buckling-driven box (:func:`structures.box_beam_sizing_buckling`: Farrar/Needham/Kuhn for
   metal, caps + sandwich for CFRP) on the modified geometry — fully stressed at FS 1.5 by construction —, skins
   × k_skin; section properties of the real multi-cell section (Megson, :func:`structures.box_section_properties`)
   → x_sc, EI, GJ. Loads ↔ sizing ↔ section iterated (``n_pass``).
4. Cruise: lifting line with elastic twist at 1 g → C_Di, span cl → C_Dp (strip integral of NeuralFoil cd);
   C_D = C_D,rest + C_Dp,wing + C_Di, C_D,rest calibrated so that the baseline reproduces the pipeline polar.
5. Constraints (≥ 0): divergence / control reversal / flutter at 1.2 V_D (Phase 3 strip models on the drawn
   trailing-edge surfaces, flutter with the Phase 4 calibration k_flutter if present). ``assumptions.structures.wingbox.hold_section`` (opt-in) freezes t/c, camber and geometric twist at the baseline (drawn washout); C_L,max (critical-section method on the lifting line, NeuralFoil
   cl_max) not below the baseline; fuel volume between the spars (ASSUMPTION: tank span and usable fraction);
   spar-to-hinge clearance and minimum gauges via the bounds / the sizing.
6. Objectives: ``weight`` (wing-box mass), ``range`` (fixed MTOW, fuel = MTOW − empty − payload, Breguet
   R ∝ L/D ln(W0/W1), calibrated on the baseline mission range), ``endurance`` (electric, fixed MTOW energy,
   loiter at the baseline speed: E ∝ 1/C_D) or ``mtow`` (fixed mission; W0 = W_fixed + W_wing + W_fuel(W0) with
   the Breguet fuel fraction — wing loads at the baseline W0, first-order).

Optimiser: SciPy SLSQP (Kraft 1988) with forward-difference gradients on variables scaled to [0, 1]."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

import numpy as np

from acdt.core.atmosphere import isa
from .aero import LiftingLine, cd_of_cl, section_polar
from .section import Contour, camber_from_name

G0 = 9.80665
RHO0 = 1.225
VARS = ("xf", "xr", "tc_root", "tc_tip", "camber", "twist_tip", "rib_pitch", "k_skin")


HINGE_CLEARANCE = 0.03  # fraction of local chord (ASSUMPTION)
HOLD_SECTION_VARS = ("tc_root", "tc_tip", "camber", "twist_tip")


def geometric_twist_tip_deg(res) -> dict:
    """Tip minus root geometric twist [deg] of the drawn main wing, or 0 if there is no assembly.

    The Phase 5 baseline used to start at twist_tip = 0 even when the assembly has washout (e.g. the
    Panknin −10° of the tailless example). That baseline was not the drawn wing.
    """
    lp = getattr(res, "assembly_loop", None) or {}
    spec = lp.get("spec_scaled") or lp.get("spec")
    if not isinstance(spec, dict) or not spec.get("assembly"):
        return {"twist_tip_deg": 0.0, "source": None, "status": "no_assembly"}
    try:
        from ..assembly.assembly import Assembly
        from ..assembly.tailless_trim import wing_planform
        tw = float(wing_planform(Assembly.from_dict(spec["assembly"]))["twist_tip_minus_root_deg"])
        return {"twist_tip_deg": tw, "source": "assembly main wing (tip − root)", "status": "assessed"}
    except Exception as ex:
        return {"twist_tip_deg": 0.0, "source": None, "status": "error", "issue": str(ex)}


def wingbox_hold_section(assumptions: dict | None) -> bool:
    sa = (assumptions or {}).get("structures") or {}
    return bool((sa.get("wingbox") or {}).get("hold_section"))



def trailing_edge_surfaces(assumptions: dict | None) -> list[dict]:
    """Trailing-edge surfaces that put a hinge on the wing rear spar.

    Conventional: ``assumptions.stability.aileron_cf_c`` / ``aileron_span_fraction``
    (defaults 0.25 / 0.35). Flying wing: ``assumptions.assembly.options.flying_wing``
    entries ``elevon``, ``split_aileron`` and ``aileron`` with a ``cf_c``. When those
    named surfaces are present they replace the conventional default (the drawing has
    no separate aileron at 0.25c).
    """
    A = assumptions or {}
    st = A.get("stability") or {}
    fw = ((A.get("assembly") or {}).get("options") or {}).get("flying_wing") or {}
    out: list[dict] = []
    if isinstance(fw, dict):
        for key, role in (("elevon", "roll_pitch"), ("split_aileron", "yaw"), ("aileron", "roll")):
            s = fw.get(key)
            if isinstance(s, dict) and s.get("cf_c") is not None:
                out.append({"name": key, "cf_c": float(s["cf_c"]), "eta_inner": s.get("eta_inner"),
                            "eta_outer": s.get("eta_outer"), "role": role,
                            "source": f"assembly.options.flying_wing.{key}"})
    if not out:
        out.append({"name": "aileron", "cf_c": float(st.get("aileron_cf_c", 0.25)),
                    "span_fraction": float(st.get("aileron_span_fraction", 0.35)), "role": "roll",
                    "source": "assumptions.stability (default aileron_cf_c 0.25 / span 0.35)"})
    return out


def rear_spar_xr_max(assumptions: dict | None, hinge_clearance: float = HINGE_CLEARANCE) -> tuple[float, list[dict]]:
    """Upper bound on rear-spar x/c: most forward TE hinge minus ``hinge_clearance``.

    The rear spar has to sit ahead of every trailing-edge hinge so the surface can be
    hung from it (Megson multi-cell box; the Phase 5 'spar-to-hinge clearance' bound).
    """
    surfs = trailing_edge_surfaces(assumptions)
    cf = max(s["cf_c"] for s in surfs)
    return 1.0 - cf - hinge_clearance, surfs


def clamp_rear_spar(x0: dict, bounds: dict, xr_max: float) -> list[str]:
    """Keep the baseline rear spar and its bounds at or ahead of ``xr_max``. Returns notes."""
    notes = []
    xr0 = float(x0["xr"])
    if xr0 > xr_max + 1e-12:
        notes.append(
            f"PRESSUPOSTO: longarina traseira de partida ({xr0:.3f} c) atrás da charneira mais "
            f"avançada; recuada para xr_max={xr_max:.3f} c (folga de charneira)."
        )
        x0["xr"] = xr_max
    lo, hi = bounds["xr"]
    lo, hi = float(lo), float(xr_max if hi is None else min(hi, xr_max))
    if lo >= hi:
        # keep a non-empty interval just below the hinge; spar_gap is still a constraint
        lo = min(lo, hi - 0.02)
    bounds["xr"] = (lo, hi)
    return notes




def _cum_from_tip(y, f):
    seg = 0.5 * (f[1:] + f[:-1]) * np.diff(y)
    out = np.zeros_like(y)
    out[:-1] = np.cumsum(seg[::-1])[::-1]
    return out


def _cum_from_root(y, f, y0=0.0):
    g = np.where(y >= y0, f, 0.0)
    seg = 0.5 * (g[1:] + g[:-1]) * np.diff(y)
    return np.r_[0.0, np.cumsum(seg)]


@dataclass
class Evaluation:
    x: dict
    mass_box: float
    box: object
    section: dict
    y: np.ndarray
    cruise: dict
    manoeuvre: dict
    aeroelastic: dict
    CLmax_ratio: float
    fuel_volume_m3: float
    perf: dict
    constraints: dict
    objective: float
    load: object = None          # structures.SpanLoad of the manoeuvre case (limit)
    beam: object = None          # structures.BeamLoads (limit; torque about the shear centre)
    wing: object = None          # TrapezoidalWing with the design's spars, t/c, rib pitch
    notes: list = field(default_factory=list)


class WingBoxProblem:
    """Low-fidelity structural–aerodynamic wing problem built around a converged pipeline result ``res``."""

    def __init__(self, res, objective: str = "weight", ny: int = 41, n_pass: int = 3, le_cell: bool = True,
                 tank_span_fraction: float = 0.6, tank_usable: float = 0.85, fuel_density: float = 720.0,
                 hinge_clearance: float = 0.03, n_llt: int = 20, hold_section: bool | None = None):
        from .. import structures as S
        from ..weights_detailed import _merge_opts
        self.S_mod = S
        self.res, self.objective, self.n_pass, self.le_cell = res, objective, n_pass, le_cell
        w = res.config.wing
        self.wing = w
        sr = res.structures
        self.vn = sr.vn
        A = res.spec.assumptions
        sa, wo = A["structures"], _merge_opts(A["weights"].get("components"))
        mat = sa["material"]
        if mat == "auto":
            mat = "cfrp" if wo["material"] == "composite" else "al2024_t3"
        self.material = mat
        self.mat = S.MATERIALS[mat] if isinstance(mat, str) else mat   # dict: external material (acdt.ai)
        self.nonopt = sa["nonoptimum_factor"]
        self.floor = wo["min_areal_density_kg_m2"] or 0.0
        self.y = np.linspace(0, w.span / 2, ny)
        self.c = S.chord_at(w, self.y)
        self.y0 = 0.5 * res.config.fuselage.max_diameter if res.config.fuselage else 0.0
        kind, m, p = camber_from_name(w.airfoil)
        self.p = p if kind == "4" else 0.4
        self.W0 = res.sizing.W0
        self.Wf0 = res.sizing.Wf or 0.0
        self.electric = bool(res.sizing.energy_J)
        self.wing_mass0 = next((it.mass for it in res.weights.items if it.key == "wing"), sr.box.mass)
        leg = res.legs[0]
        self.V_c, self.h_c, self.R0 = leg.V, leg.altitude, leg.value
        self.rho_c = isa(self.h_c).rho
        self.mu_c = isa(self.h_c).mu
        self.CD0, self.K = res.polar.CD0, res.polar.K
        st_o = A.get("stability", {})
        # Legacy Phase 3 outboard-aileron defaults (used only when no TE surface is listed).
        self.ail_f, self.ail_cf = st_o.get("aileron_span_fraction", 0.35), st_o.get("aileron_cf_c", 0.25)
        from ..hifi.calibration import load as _load_cal
        self.k_fl = _load_cal(A).get("k_flutter") or 1.0
        self.ll = LiftingLine(w.span, lambda yy: S.chord_at(w, yy), n_llt)
        self.tank = (tank_span_fraction, tank_usable, fuel_density)
        self.xr_max, self.te_surfaces = rear_spar_xr_max(A, hinge_clearance)
        twist = geometric_twist_tip_deg(res)
        self.twist_info = twist
        self.x0 = {"xf": w.box.front_spar_xc, "xr": w.box.rear_spar_xc, "tc_root": w.tc_root, "tc_tip": w.tc_tip,
                   "camber": m if kind == "4" else 0.02, "twist_tip": float(twist["twist_tip_deg"]),
                   "rib_pitch": w.box.rib_pitch or 0.6 * w.mac, "k_skin": 1.0}
        self.bounds = {"xf": (0.12, 0.30), "xr": (0.50, self.xr_max), "tc_root": (0.09, 0.20),
                       "tc_tip": (0.08, 0.16), "camber": (0.0, 0.05), "twist_tip": (-5.0, 1.0),
                       "rib_pitch": (0.7 * self.x0["rib_pitch"], 1.4 * self.x0["rib_pitch"]), "k_skin": (1.0, 3.0)}
        # keep the drawn section inside the bounds (e.g. Panknin washout of −10° is below the old −5° cap)
        for k in HOLD_SECTION_VARS:
            lo, hi = self.bounds[k]
            v = self.x0[k]
            self.bounds[k] = (min(lo, v), max(hi, v))
        self.hinge_notes = clamp_rear_spar(self.x0, self.bounds, self.xr_max)
        if hold_section is None:
            hold_section = wingbox_hold_section(A)
        self.hold_section = bool(hold_section)
        if self.hold_section:
            for k in HOLD_SECTION_VARS:
                v = float(self.x0[k])
                self.bounds[k] = (v, v)
        # rib pitch kept within ±30–40 % of the Phase 3 value (ASSUMPTION): the Phase 3 rib mass is a minimum-gauge
        # half-solid web (no flanges, stiffeners, crushing/attachment loads), so the Farrar σ ∝ √(1/L) gain of a
        # short pitch would otherwise be bought with ribs that are not really sized
        self.vars = VARS
        self._setup()
        self._cache = {}
        self.base = None
        self.base = self.evaluate(self.x0)

    def _setup(self):
        """Hook for subclasses (extra variables, bounds, materials) — called before the baseline evaluation."""

    def _key(self, x):
        return tuple(round(float(x[k]), 7) for k in self.vars)

    def _section(self, w, box, x):
        return self.S_mod.box_section_properties(w, box, self.material, self.le_cell, camber=(x["camber"], self.p),
                                                 n_cover=10, n_web=4, n_le=12)

    # ------------------------------------------------------------------ helpers
    def _polars(self, x):
        Re_r = self.rho_c * self.V_c * self.wing.c_root / self.mu_c
        Re_t = self.rho_c * self.V_c * self.wing.c_tip / self.mu_c
        r = lambda v, d=4: round(float(v), d)
        pr = section_polar(r(x["camber"]), r(self.p, 3), r(x["tc_root"]), float(f"{Re_r:.2g}"))
        pt = section_polar(r(x["camber"]), r(self.p, 3), r(x["tc_tip"]), float(f"{Re_t:.2g}"))
        return pr, pt

    def _span(self, yy, vr, vt):
        return vr + (vt - vr) * np.abs(yy) / (self.wing.span / 2)

    def _llt_elastic(self, CL, q, x, pol, GJ, xsc, n_it=6):
        """Trimmed lifting line at C_L with elastic twist at dynamic pressure q (loads at the true q)."""
        pr, pt = pol
        yl = self.ll.y
        a0 = self._span(yl, pr["a0"], pt["a0"])
        aL0 = self._span(yl, pr["alpha_L0"], pt["alpha_L0"])
        geo = np.radians(x["twist_tip"]) * yl / (self.wing.span / 2)
        cm0 = self._span(self.y, pr["cm0"], pt["cm0"])
        th_e = np.zeros_like(yl)
        for _ in range(n_it):
            al, A, CLr, CDi, ccl = self.ll.trim(CL, geo + th_e, a0, aL0)
            ccl_y = np.interp(self.y, yl[::-1], ccl[::-1], right=0.0)
            lift = q * ccl_y
            tdist = lift * (xsc - 0.25) * self.c + q * self.c**2 * cm0
            T = _cum_from_tip(self.y, tdist)
            th = _cum_from_root(self.y, T / GJ, self.y0)
            new = np.interp(yl, self.y, th)
            if np.max(np.abs(new - th_e)) < 1e-6:
                th_e = new
                break
            th_e = new
        return {"alpha": al, "A": A, "CL": CLr, "CDi": CDi, "ccl_y": ccl_y, "lift": lift, "T": T, "theta_e": th,
                "cl_y": ccl_y / self.c, "geo": geo}

    def _wing(self, x):
        w = copy.deepcopy(self.wing)
        w.tc_root, w.tc_tip = x["tc_root"], x["tc_tip"]
        w.box.front_spar_xc, w.box.rear_spar_xc, w.box.rib_pitch = x["xf"], x["xr"], x["rib_pitch"]
        return w

    def _size(self, w, x, lift_lim, T_lim, wing_mass):
        S = self.S_mod
        rel = self.vn.n_limit_pos * G0 * (wing_mass / 2) * self.c / np.trapezoid(self.c, self.y)
        load = S.SpanLoad(self.y, self.c, lift_lim, rel, self.vn.n_limit_pos, "LLT + torção elástica (Fase 5)")
        V = _cum_from_tip(self.y, load.net)
        M = _cum_from_tip(self.y, V)
        beam = S.BeamLoads(self.y, V, M, T_lim)
        box = S.box_beam_sizing_buckling(
            w, beam, self.material, 1.5, self.nonopt, rib_pitch=x["rib_pitch"], areal_density_floor=self.floor,
            n_neg_ratio=abs(self.vn.n_limit_neg / self.vn.n_limit_pos) if self.vn.n_limit_pos else 0.4)
        k = x["k_skin"]
        if k > 1.0:      # torsional stiffening: thicker shear skins (box covers), added to the cover mass
            d = box.details
            dt_u, dt_l = (k - 1) * d["skin_upper"], (k - 1) * d["skin_lower"]
            d["skin_upper"], d["skin_lower"] = d["skin_upper"] + dt_u, d["skin_lower"] + dt_l
            d["cover_tbar_upper"], d["cover_tbar_lower"] = d["cover_tbar_upper"] + dt_u, d["cover_tbar_lower"] + dt_l
            box.skin_t = d["skin_upper"]
            dm = 2 * np.trapezoid((dt_u + dt_l) * box.w_box * self.mat["rho"], self.y)
            ms = box.masses
            key = "covers_skin_stringers" if "covers_skin_stringers" in ms else "box_skins"
            ms[key] += dm
            ms["ideal"] += dm
            ms["nonoptimum"] = (box.nonoptimum_factor - 1) * ms["ideal"]
            ms["total"] = box.nonoptimum_factor * ms["ideal"]
        return box, beam, load

    def fuel_volume(self, x):
        """Usable tank volume between the spars, both wings (ASSUMPTION: from the fuselage side to
        tank_span_fraction · b/2, usable fraction tank_usable for ribs/stringers/expansion)."""
        frac, usable, _ = self.tank
        yy = np.linspace(self.y0, frac * self.wing.span / 2, 15)
        cc = self.S_mod.chord_at(self.wing, yy)
        tc = self._span(yy, x["tc_root"], x["tc_tip"])
        xs = np.linspace(x["xf"], x["xr"], 25)
        area = np.array([np.trapezoid(Contour(x["camber"], self.p, t, 1.0).depth(xs), xs) for t in tc]) * cc**2
        return 2 * usable * float(np.trapezoid(area, yy))

    def clmax_critical_section(self, x, pol):
        """C_L at first local stall (critical-section method on the rigid lifting line; see Phillips & Alley 2007,
        J. Aircraft 44(3), for the method and its limits)."""
        pr, pt = pol
        yl = self.ll.y
        a0 = self._span(yl, pr["a0"], pt["a0"])
        aL0 = self._span(yl, pr["alpha_L0"], pt["alpha_L0"])
        clm = self._span(yl, pr["clmax"], pt["clmax"])
        geo = np.radians(x["twist_tip"]) * yl / (self.wing.span / 2)
        A1 = self.ll.solve(np.ones_like(yl), a0)
        A0 = self.ll.solve(geo - aL0, a0)
        c0, c1 = self.ll.coeffs(A0)[2] / self.ll.c, self.ll.coeffs(A1)[2] / self.ll.c
        al = float(np.min((clm - c0) / c1))
        return math.pi * self.ll.AR * (A0[0] + al * A1[0])

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, x: dict) -> Evaluation:
        x = {**self.x0, **x}
        key = self._key(x)
        if key in self._cache:
            return self._cache[key]
        S = self.S_mod
        w = self._wing(x)
        pol = self._polars(x)
        VD = self.vn.VD
        qD = 0.5 * RHO0 * VD**2
        n = self.vn.n_limit_pos
        CLm = n * self.W0 * G0 / (qD * w.S)
        base = self.base
        b3 = self.res.structures.box
        GJ = base.section["GJ"] if base else np.interp(self.y, b3.y, b3.GJ)
        xsc = base.section["x_sc_c"] if base else 0.5 * (x["xf"] + x["xr"]) * np.ones_like(self.y)
        wing_mass = self.wing_mass0
        for _ in range(self.n_pass):
            man = self._llt_elastic(CLm, qD, x, pol, GJ, xsc)
            box, beam, load = self._size(w, x, man["lift"], man["T"], wing_mass)
            sec = self._section(w, box, x)
            GJ, xsc = sec["GJ"], sec["x_sc_c"]
            if base is not None:
                wing_mass = self.wing_mass0 + box.masses["total"] - base.mass_box
        box.EI, box.GJ = sec["EI"], sec["GJ"]
        box.details["x_sc_c"], box.details["z_sc_c"] = sec["x_sc_c"], sec["z_sc_c"]
        m_box = box.masses["total"]
        dW = 0.0 if base is None else m_box - base.mass_box
        # cruise
        Wc = self.W0 + dW - (0.5 * (self.Wf0 - dW) if not self.electric else 0.0)
        qc = 0.5 * self.rho_c * self.V_c**2
        CLc = Wc * G0 / (qc * w.S)
        cr = self._llt_elastic(CLc, qc, x, pol, GJ, xsc)
        cdr = cd_of_cl(pol[0], cr["cl_y"])
        cdt = cd_of_cl(pol[1], cr["cl_y"])
        cd = self._span(self.y, cdr, cdt)
        CDp = 2 * float(np.trapezoid(self.c * cd, self.y)) / w.S
        if base is None:
            self.CD_rest = self.CD0 + self.K * CLc**2 - (CDp + cr["CDi"])
        CD = self.CD_rest + CDp + cr["CDi"]
        cruise = {"CL": CLc, "CD": CD, "CDp_wing": CDp, "CDi": cr["CDi"], "L_D": CLc / CD, "alpha_deg":
                  math.degrees(cr["alpha"]), "theta_e_tip_deg": math.degrees(cr["theta_e"][-1]),
                  "e_span": CLc**2 / (math.pi * self.ll.AR * cr["CDi"]), "cl_y": cr["cl_y"]}
        manoeuvre = {"CL": CLm, "theta_e_tip_deg": math.degrees(man["theta_e"][-1]), "lift": man["lift"],
                     "T": man["T"], "M_root": float(beam.moment[0]), "T_root": float(beam.torque[0])}
        # aeroelastic margins (Phase 3 strip models on the new section)
        from .. import aeroelasticity as AE
        yy = np.linspace(self.y0, w.span / 2, 41)
        cc = S.chord_at(w, yy)
        mw = self.wing_mass0 + dW
        a_w = float(np.mean([pol[0]["a0"], pol[1]["a0"]]))
        xf_s = np.interp(yy, self.y, xsc)
        ws = AE.WingStrip(yy, cc, np.interp(yy, self.y, sec["EI"]), np.interp(yy, self.y, GJ),
                          0.5 * mw * cc / np.trapezoid(cc, yy), xf_s - 0.25, xf_s, 0.5, a_w)
        div = AE.torsional_divergence_speed(ws)
        fl = AE.flutter_estimate_typical_section(ws, V_max=max(4 * VD, 150.0), n=300)
        VF = fl["V_F"] * self.k_fl
        Vreq = 1.2 * VD
        qreq = 0.5 * AE.RHO0 * Vreq ** 2
        controls, V_rev, rev_name = [], None, None
        surfs = list(self.te_surfaces) or [{"name": "aileron", "cf_c": self.ail_cf,
                                            "span_fraction": self.ail_f, "role": "roll"}]
        for s in surfs:
            chi = AE.control_span_mask(ws, s)
            evs = AE.control_effectiveness(ws, chi, float(s["cf_c"]))
            rec = {"name": s["name"], "role": s.get("role", "roll"), "cf_c": float(s["cf_c"]),
                   "eta_inner": s.get("eta_inner"), "eta_outer": s.get("eta_outer"),
                   "span_fraction": s.get("span_fraction"), "V_R": evs["V_R"],
                   "effectiveness_at_1_2_VD": evs["effectiveness"](qreq),
                   "method": "Wright & Cooper 2015 Ch. 9; Bisplinghoff, Ashley & Halfman 1955 Ch. 8; "
                             "Glauert 1926 flap derivatives (sealed plain flap)"}
            if s.get("role") == "yaw":
                rec["yaw_effectiveness"] = "unassessed"
                rec["note"] = (
                    "o canal de guinada do split é arrasto de perfil (McCormick Eq. 3.45) e não inverte "
                    "pelo mecanismo torsional de Bisplinghoff / Wright & Cooper; o V_R e a eficácia aqui "
                    "são só o acoplamento de rolamento, com derivadas de flap liso — PRESSUPOSTO (o split "
                    "não é flap liso; a_C sobrestima o incremento de sustentação)"
                )
            else:
                if V_rev is None or evs["V_R"] < V_rev:
                    V_rev, rev_name = evs["V_R"], s["name"]
            controls.append(rec)
        if V_rev is None:
            evs = AE.aileron_reversal_speed(ws, self.ail_f, 1 - self.ail_cf)
            V_rev, rev_name = evs["V_R"], "aileron"
        ae = {"V_div": div["V_div"], "V_rev": V_rev, "V_F": VF, "V_req": Vreq,
              "reversal_surface": rev_name, "controls": controls}
        # stall, fuel volume, performance
        CLmax = self.clmax_critical_section(x, pol)
        vol = self.fuel_volume(x)
        perf = self._performance(cruise, dW)
        cons = {f"{k}_margin": (min(v, 10 * Vreq) / Vreq - 1) for k, v in
                (("divergence", div["V_div"]), ("reversal", V_rev), ("flutter", VF))}
        cons["CLmax"] = (CLmax / base.perf["CLmax"] - 1) if base else 0.0
        if not self.electric and self.Wf0 > 0:
            ratio = vol / max(perf["fuel_kg"] / self.tank[2], 1e-9)
            if base is None:
                self.fuel_ratio0 = ratio
            # tank volume ≥ fuel needed, or not worse than the baseline if the baseline itself does not fit
            cons["fuel_volume"] = ratio - min(1.0, self.fuel_ratio0)
        cons["spar_gap"] = (x["xr"] - x["xf"]) - 0.25
        perf["CLmax"] = CLmax
        obj = {"weight": m_box, "range": -perf.get("range_m", 0.0), "endurance": -perf.get("endurance_ratio", 0.0),
               "mtow": perf.get("W0", self.W0)}[self.objective]
        ev = Evaluation(x, m_box, box, sec, self.y, cruise, manoeuvre, ae, CLmax / (base.perf["CLmax"] if base else CLmax),
                        vol, perf, cons, obj, load, beam, w)
        self._cache[key] = ev
        return ev

    def _performance(self, cr, dW):
        """Mission figures at fixed MTOW (range / endurance) and the fixed-mission MTOW."""
        b = self.base
        LD = cr["L_D"]
        out = {"L_D": LD}
        if not self.electric and self.Wf0 > 0:
            Wf = self.Wf0 - dW
            if b is None:
                self.k_R = self.R0 / (LD * math.log(self.W0 / (self.W0 - self.Wf0)))
            out["fuel_kg"] = Wf
            out["range_m"] = self.k_R * LD * math.log(self.W0 / (self.W0 - Wf))
            # fixed mission: W0 = W_fixed + W_wing + Wf, Wf/W0 = 1 − exp(−R/(k L/D))
            ff = 1 - math.exp(-self.R0 / (self.k_R * LD))
            out["W0"] = (self.W0 - self.Wf0 + dW) / (1 - ff)
        else:
            if b is None:
                self.CD_loiter0 = cr["CD"]
            out["endurance_ratio"] = self.CD_loiter0 / cr["CD"]
            out["W0"] = self.W0 + dW      # electric: same battery (energy) and payload, lighter/heavier wing
        return out

    # ------------------------------------------------------------------ optimisation
    def _to_x(self, u, free):
        x = dict(self.x0)
        for k, v in zip(free, u):
            lo, hi = self.bounds[k]
            x[k] = lo + v * (hi - lo)
        return x

    def optimise(self, free=VARS, fixed: dict | None = None, maxiter: int = 40, ftol: float = 1e-6,
                 start: dict | None = None):
        from scipy.optimize import minimize
        fixed = {**(getattr(self, "fixed_section", None) or {}), **(fixed or {})}
        if getattr(self, "hold_section", False):
            for k in HOLD_SECTION_VARS:
                fixed.setdefault(k, self.x0[k])
        free = [k for k in free if k not in fixed and (self.bounds[k][1] - self.bounds[k][0]) > 1e-15]
        x0 = {**self.x0, **(start or {}), **fixed}
        x0["xr"] = min(x0["xr"], self.xr_max)
        u0 = np.array([(x0[k] - self.bounds[k][0]) / (self.bounds[k][1] - self.bounds[k][0]) for k in free])
        u0 = np.clip(u0, 0, 1)
        sc = abs(self.base.objective) or 1.0

        def X(u):
            return {**self._to_x(u, free), **(fixed or {})}

        f = lambda u: self.evaluate(X(u)).objective / sc
        names = list(self.base.constraints)
        cons = [{"type": "ineq", "fun": (lambda u, n=n: self.evaluate(X(u)).constraints[n])} for n in names]
        hist = []
        r = minimize(f, u0, method="SLSQP", bounds=[(0, 1)] * len(free), constraints=cons,
                     options={"maxiter": maxiter, "ftol": ftol, "eps": 2e-3},
                     callback=lambda u: hist.append(self.evaluate(X(u)).objective))
        ev = self.evaluate(X(r.x))
        ok = lambda e: all(v >= -1e-3 for v in e.constraints.values())
        feas, msg = ok(ev), str(r.message)
        if not feas:
            # SLSQP stopped at an infeasible point: return the best feasible design it evaluated (same fixed values)
            cand = [e for e in self._cache.values() if ok(e)
                    and all(abs(e.x[k] - v) < 1e-12 for k, v in (fixed or {}).items())]
            if cand:
                ev = min(cand, key=lambda e: e.objective)
                feas, msg = True, msg + " — best feasible point evaluated returned"
        return {"x": ev.x, "eval": ev, "success": bool(r.success), "message": msg, "nit": r.nit,
                "nfev": r.nfev, "feasible": feas, "history": hist}
