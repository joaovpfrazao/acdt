"""Phase 3 — OpenMDAO multidisciplinary design optimisation of the aircraft (MDF formulation).

Disciplines (each a classical method already used by the fixed-point MDA of :mod:`.sizing`, wrapped by
:mod:`acdt.core.mdo` as OpenMDAO components):

* **geometry + aero** — (W0, W/S, AR) → wing/fuselage/tails (:func:`.sizing.build_configuration`), CD0 by
  component build-up (Raymer Eq. 12.24 / Hoerner form factors), Oswald e (Raymer Eq. 12.49), K = 1/(π A e).
  *Handbook fidelity inside the loop*; XFOIL/AVL low-fi is used in the verification re-run.
* **structures** — V-n diagram (CS 23.333–23.341 / STANAG 4671) → n_lim, and the buckling-sized wing box
  (Bruhn/Megson/Farrar, :mod:`.structures`), whose mass replaces Raymer's wing equation if
  ``weights.components.wing_method: box``.
* **weights** — component build-up (Raymer Ch. 15 + selected systems masses) with Nz = 1.5 n_lim.
* **mission** — fuel fraction (Breguet, Raymer Ch. 3) or battery energy (Hepperle 2012) with the take-off +
  climb energy of the segment model (:func:`.performance.takeoff_climb_energy`).
* **closure** — W0 = payload + crew + fixed + We + Wf (Raymer Eq. 3.4).

Post-cycle: installed power/thrust ≤ the baseline selection (systems frozen), the constraint diagram (each requirement curve as g = req(W/S)/(P/W) − 1 ≤ 0, W/S lines as
W/S / limit − 1 ≤ 0), span/MTOW requirement checks, stability (wing placement for the target SM, trim at
CLmax at the forward CG: |δe|/δe_max − 1 ≤ 0) and the cost model (Eastlake). The objective comes from the
requirement registry (``mtow_objective`` → W0, ``unit_cost`` → cost) or ``assumptions.mdo.objective`` /
``acdt optimize --objective`` ∈ {W0, energy, cost, endurance, range}. For ``endurance``/``range`` the requirement
value becomes a design variable that is maximised with W0 ≤ the MTOW requirement (or the baseline W0).

Stated assumptions: inside SLSQP the motor, ESC and cell are a fixed integer assignment (Geoffrion,
J. Optim. Theory Appl. 10, 1972 — the continuous subproblem does not cross a catalog change). A separate
master step may re-select the lightest feasible triple and is accepted only when the full-pipeline merit
improves. The propeller diameter stays Raymer's continuous statistic (no propeller catalogue). Tail volume
coefficients and the tail arm fraction are fixed (tails scale with the wing); the wing placement is
re-solved inside the stability discipline. Servos are still re-selected inside the systems closure.
"""
from __future__ import annotations

import copy
import math
from dataclasses import replace
from types import SimpleNamespace

import numpy as np

from acdt import G0
from acdt.core.atmosphere import isa
from acdt.core.mdo import Discipline, build_openmdao_problem

from .aero.drag import ROUGHNESS, DragPolar, component_buildup, oswald_raymer
from .aero.lift import HighLiftDevice, high_lift_summary, lift_curve_slope
from .constraints import AeroContext, Constraint, ConstraintContext, PropContext, _cruise_tw, build_constraints
from .propulsion import is_propeller
from .sizing import (_legs, _prop_data, build_configuration, constraint_requirements, structures_inputs,
                     unit_cost_estimate)
from .weights import battery_energy, fuel_fraction

OBJECTIVES = ("W0", "energy", "cost", "endurance", "range")


def objective_from_registry(spec, override: str | None = None) -> str:
    """Objective: CLI/assumption override, else the requirement registry objectives, else min W0."""
    o = override or spec.assumptions.get("mdo", {}).get("objective")
    if o:
        if o not in OBJECTIVES:
            raise ValueError(f"MDO objective '{o}' unknown ({', '.join(OBJECTIVES)})")
        return o
    keys = [r.key for r in spec.requirements.objectives()]
    if "unit_cost" in keys:
        return "cost"
    return "W0"


class AircraftMDO:
    """Discipline functions on a frozen baseline (spec after the systems closure + selected systems)."""

    def __init__(self, spec, systems=None, baseline=None):
        from .systems_integration import is_uas
        self.spec = spec = copy.deepcopy(spec)
        spec.assumptions["aero"]["fidelity"] = "handbook"
        A = spec.assumptions
        from .aero import gear_drag as _GD
        if _GD.requested(A):      # same opt-in gear drag as the sizing loop (aero/gear_drag.py)
            _GD.prepare(A)
        # retracted-gear ΔC_D0 = Σ(D/q)/S at the baseline wing (the optimiser's S moves; PRESSUPOSTO)
        self._S_gear = float(getattr(baseline, "S", 0.0) or 0.0) or None
        # P1b: the generic assembly (assumptions.assembly) gives the polar CD0 and the per-part structure
        # masses inside the optimiser too, rescaled to each (S, AR) exactly as in the sizing loop. The induced
        # factor inside the optimiser is the classical Oswald one, β-calibrated (k_fac) to the baseline's
        # (AVL / Kroo) K — no AVL call per optimiser evaluation.
        from .assembly.loop import AssemblyLoop
        self.asm = AssemblyLoop.from_mission(spec) if A.get("assembly") else None
        self.asm_close_on = None
        if self.asm is not None:
            self.asm.options["K_source"] = "oswald"
            A["aero"].update(self.asm.planform())
            self.asm_close_on = (A.get("mdo") or {}).get("assembly_close_on")
            if self.asm_close_on not in (None, "nominal", "pessimistic"):
                raise ValueError("assumptions.mdo.assembly_close_on: nominal | pessimistic")
        self.A, self.reqs, self.kind = A, spec.requirements, spec.propulsion_kind
        self.systems = systems
        self.uas = is_uas(spec)
        aa = A["aero"]
        fl = aa.get("flap") or {"kind": "none"}
        self.hl = high_lift_summary(aa["clmax_airfoil"], math.radians(aa["sweep_c4_deg"]),
                                    HighLiftDevice(fl.get("kind", "plain"), fl.get("flapped_area_ratio", 0.6),
                                                   fl.get("chord_extension", 1.0)))
        self.h = self.reqs.value("cruise_altitude", A["constraints"]["default_cruise_altitude_m"])
        self.at = isa(self.h)
        self.pdata = _prop_data(spec)
        p = A["propulsion"]
        self.pctx = PropContext(self.kind, p["eta_cruise"], p["eta_climb"], p["eta_takeoff"])
        self.creqs, _ = constraint_requirements(spec)
        self.payload = self.reqs.value("payload_mass", 0.0)
        self.crew = self.reqs.value("crew_mass", 0.0)
        self.fixed = A["weights"]["fixed_mass_kg"]
        self.climb_alt = max([self.h] + [r.params.get("altitude", 0) for r in self.reqs])
        wo = dict(A["weights"].get("components") or {})
        self.wing_method = wo.pop("wing_method", "raymer")
        self.user_n = wo.get("limit_load_factor")
        self.wopts = wo
        self.vn_feed = A["structures"]["load_factor_from_vn"] and not self.user_n
        self.n_eng = int(p.get("n_engines", 1))
        self.req_kind = None  # "endurance" | "range" when the requirement value is a design variable
        # first-order additive correction of W0 (closure) and E_Wh (mission) to the full pipeline at x_k
        # (Haftka 1991; Alexandrov et al. 2001): {"W0"|"E_Wh": {"x0": {...}, "a": float, "c": {var: float}}}
        self.corr: dict = {}
        # P/W: from the constraint envelope at W/S (as the pipeline's design point) unless it is a design
        # variable (then installed power is frozen at the baseline selection: g_power)
        self.pw_free = "pw" in (A.get("mdo", {}).get("design_vars") or [])
        # systems frozen at the baseline selection → installed power/thrust may not exceed the selected one
        self.P_installed = None
        if baseline is not None:
            self.P_installed = baseline.power_sl if is_propeller(self.kind) else baseline.thrust_sl
        # multi-fidelity calibration: zeroth-order multiplicative ("β") correction of the handbook polar to the
        # baseline low-fi (XFOIL/AVL) polar, held fixed during the optimisation (Haftka, AIAA J. 29(9), 1991;
        # Alexandrov et al., Struct. Multidisc. Optim. 21, 2001). CLmax from the low-fi section polar.
        self.cd0_fac = self.k_fac = 1.0
        self.calibration = "none (handbook baseline)"
        # Phase 9 camber-flap option: the baseline envelope correction ΔCD(CL) and ΔCLmax are held fixed
        # (frozen schedule; its weak Reynolds dependence on W/S and AR is neglected inside the optimiser)
        self.camber = getattr(getattr(baseline, "polar", None), "camber", None)
        if self.camber is not None:
            self.hl = baseline.highlift
        if baseline is not None and getattr(baseline, "lowfi", None) is not None:
            self.hl = baseline.highlift
            self.cd0_fac, self.k_fac = 1.0, 1.0
            cfg0 = baseline.config
            pol_hb, _ = self.polar(cfg0, baseline.cruise_speed)
            self.cd0_fac = baseline.polar.CD0 / pol_hb.CD0
            self.k_fac = baseline.polar.K / pol_hb.K
            self.calibration = (f"β = CD0_lowfi/CD0_manual = {self.cd0_fac:.3f}, K_lowfi/K_manual = {self.k_fac:.3f} "
                                f"no ponto base; CLmax limpo {self.hl.CLmax_clean:.3f} (XFOIL)")
        elif baseline is not None and self.asm is not None and getattr(baseline, "polar", None) is not None:
            pol_a, _ = self.polar(baseline.config, baseline.cruise_speed)
            self.cd0_fac = baseline.polar.CD0 / pol_a.CD0
            self.k_fac = baseline.polar.K / pol_a.K
            self.calibration = (f"montagem: β CD0 = {self.cd0_fac:.3f}, K_base/K_Oswald = {self.k_fac:.3f} no ponto base")
        if self.asm is not None and self.asm_close_on:
            # switched AFTER the β calibration, so β does not cancel the pessimistic closure
            self.asm.options["close_on"] = self.asm_close_on
            self.calibration += f"; CD0 da montagem fechado em {self.asm_close_on}"

    # ------------------------------------------------------------------ helpers
    def config(self, W0, ws, AR):
        return build_configuration(self.spec, W0, ws, AR)

    def polar(self, cfg, Vc):
        aa = self.A["aero"]
        bu = component_buildup(cfg, Vc, self.at.rho, self.at.mu, self.at.a, aa["laminar"],
                               ROUGHNESS[aa["roughness"]], aa["Q"], aa["lp_fraction"])
        e = aa["oswald"] or oswald_raymer(cfg.wing.AR, cfg.wing.sweep_at(0.0))
        pol = DragPolar.from_oswald(bu.CD0, cfg.wing.AR, e)
        if self.asm is not None:
            d = self.asm.drag(cfg.wing.S, Vc, self.at.rho, self.at.mu, self.at.a, aa.get("extra_drag_areas_m2"),
                              AR=self._asm_AR(cfg.wing.AR))
            pol = DragPolar(self.asm.cd0(d), pol.K)
        return DragPolar(pol.CD0 * self.cd0_fac, pol.K * self.k_fac), bu

    def _asm_AR(self, AR):
        return AR if (self.asm is not None and self.asm.options["scaling"] == "surfaces") else None

    @staticmethod
    def ar_is_free(spec) -> bool:
        """False when an assembly with uniform scaling fixes the aspect ratio (the drawing's)."""
        a = (spec.assumptions or {}).get("assembly")
        if not a:
            return True
        from .assembly.loop import load_spec
        o = load_spec(spec, a).get("options") or {}
        return not o.get("in_loop", True) or o.get("scaling", "uniform") == "surfaces"

    def legs(self, CD0, K, ws, req_value=None):
        lg = _legs(self.spec, DragPolar(CD0, K, self.camber), ws, self.hl.CLmax_clean, self.h)
        if self.req_kind and req_value is not None:
            k = "loiter" if self.req_kind == "endurance" else "cruise"
            lg = [replace(L, value=req_value) if L.kind == k else L for L in lg]
        return lg

    def Vc(self, CD0, K, ws):
        return self.reqs.value("cruise_speed") or max(L.V for L in self.legs(CD0, K, ws))

    def CLa(self, cfg, Vc):
        w = cfg.wing
        return lift_curve_slope(w.AR, Vc / self.at.a, w.sweep_at(w.xc_max_t),
                                S_exp_over_S_ref=w.exposed_area(cfg.fuselage.max_diameter) / w.S,
                                fuselage_diameter=cfg.fuselage.max_diameter, span=w.span)

    def P_sl(self, pw, W0):
        return pw * W0 * G0 if is_propeller(self.kind) else None

    # ------------------------------------------------------------------ disciplines
    def geom_aero(self, W0, ws, AR):
        cfg = self.config(W0, ws, AR)
        Vc = self.reqs.value("cruise_speed")
        if Vc:
            pol, _ = self.polar(cfg, Vc)
        else:  # leg-rule cruise speed depends on the polar: inner fixed point (as the MDA's previous-iterate)
            pol = DragPolar.from_oswald(0.03, AR, self.A["aero"]["oswald"] or oswald_raymer(AR, cfg.wing.sweep_at(0)))
            for _ in range(8):
                Vc = max(L.V for L in _legs(self.spec, pol, ws, self.hl.CLmax_clean, self.h))
                pol, _ = self.polar(cfg, Vc)
        return {"S": cfg.wing.S, "span": cfg.wing.span, "CD0": pol.CD0, "K": pol.K}

    def structures(self, W0, ws, AR, CD0, K):
        from .structures import wing_structure
        cfg = self.config(W0, ws, AR)
        Vc = self.Vc(CD0, K, ws)
        sr = wing_structure(structures_inputs(self.spec, W0, cfg, self.hl.CLmax_clean, self.CLa(cfg, Vc), Vc,
                                              self.h, None, self.uas, 0.0))
        return {"n_lim": sr.vn.n_limit_pos, "m_box": sr.box.mass, "_sr": sr}

    def weights(self, W0, Wf, ws, AR, pw, n_lim, CD0, K, m_box):
        from .weights_detailed import component_weights
        cfg = self.config(W0, ws, AR)
        Vc = self.Vc(CD0, K, ws)
        wo = {**self.wopts, "limit_load_factor": n_lim} if self.vn_feed else self.wopts
        bd = component_weights(W0, Wf, self.kind, cfg, 0.5 * self.at.rho * Vc**2, Vc / self.at.a,
                               self.P_sl(pw, W0), wo, self.uas, self.systems, self.n_eng, self.payload + self.crew)
        if self.wing_method == "box":
            it = [i for i in bd.items if i.key == "wing"][0]
            bd.empty += m_box - it.mass
            it.mass = m_box
        if self.asm is not None:
            self.asm.apply_masses(bd, cfg.wing.S, W0, 0.5 * self.at.rho * Vc ** 2,
                                  self.wopts.get("material") or "metal", AR=self._asm_AR(AR))
            m_wing = sum(i.mass for i in bd.items if i.key == "asm:" + self.asm.wing_surface.name)
        else:
            m_wing = [i.mass for i in bd.items if i.key == "wing"][0]
        return {"We": bd.empty, "m_wing": m_wing, "_bd": bd}

    def _corr(self, name, **x):
        c = self.corr.get(name)
        if not c:
            return 0.0
        return c["a"] + sum(ck * (x[k] - c["x0"][k]) for k, ck in c["c"].items())

    def mission(self, W0, ws, pw, AR, CD0, K, req_value=0.0):
        legs = self.legs(CD0, K, ws, req_value if self.req_kind else None)
        if self.kind == "electric":
            from .performance import PerfModel, takeoff_climb_energy
            S = W0 * G0 / ws
            pol = DragPolar(CD0, K, self.camber)
            pm = PerfModel.from_state(self.spec, S, pol, self.hl, pw * W0 * G0, None)
            tce = takeoff_climb_energy(pm, W0, self.h)
            pdat = replace(self.pdata, takeoff_climb_J_per_kg=tce["total"] / W0)
            E = battery_energy(W0, legs, pdat, self.climb_alt) / 3600
            E += self._corr("E_Wh", ws=ws, AR=AR, req_value=req_value)
            return {"Wf": E * 3600 / pdat.e_spec, "E_Wh": E}
        Wf = fuel_fraction(legs, self.pdata) * W0 + self._corr("E_Wh", ws=ws, AR=AR, req_value=req_value)
        return {"Wf": Wf, "E_Wh": Wf}  # fuel: "energy" objective = fuel mass [kg]

    def closure(self, We, Wf, ws=0.0, AR=0.0, req_value=0.0):
        return {"W0": self.payload + self.crew + self.fixed + We + Wf
                + self._corr("W0", ws=ws, AR=AR, req_value=req_value)}

    def constraint_list(self, CD0, K, ws):
        Vc = self.Vc(CD0, K, ws)
        con_a = self.A["constraints"]
        aa = self.A["aero"]
        actx = AeroContext(CD0, K, self.hl.CLmax_clean, self.hl.CLmax_takeoff, self.hl.CLmax_landing,
                           aa["CL_ground"], _gear_dcd0(aa, self._S_gear), aa["mu_roll"], self.camber)
        ctx = ConstraintContext(actx, self.pctx, self.h, Vc, con_a["cruise_weight_fraction"],
                                con_a["landing_weight_fraction"], con_a["approach_distance_ft"])
        cons = build_constraints(self.creqs, ctx)
        if not any(c.key == "cruise_speed" for c in cons):
            rho_c = self.at.rho
            cons.append(Constraint(f"Cruzeiro implícito {Vc:.0f} m/s", "implied_cruise", "curve",
                                   lambda w, rho_c=rho_c, Vc=Vc, a=actx: _cruise_tw(w, rho_c, Vc, a),
                                   lambda w, Vc=Vc: w * 0 + Vc, self.h, self.pctx.eta_cruise))
        return cons

    def constraint_keys(self, CD0, K, ws):
        return [c.key for c in self.constraint_list(CD0, K, ws) if self.pw_free or c.kind != "curve"]

    def envelope(self, ws, CD0, K):
        """P/W (or T/W) at W/S = upper envelope of the curve constraints × (1 + margin) (Raymer Ch. 5/19)."""
        margin = self.A["constraints"]["margin"]
        req = [float(c.required(np.array([ws]), self.pctx)[0]) for c in self.constraint_list(CD0, K, ws)
               if c.kind == "curve"]
        return {"pw": max(req) * (1 + margin)}

    def constraints(self, ws, pw, CD0, K, W0, span):
        margin = self.A["constraints"]["margin"]
        out = {}
        for c in self.constraint_list(CD0, K, ws):
            if c.kind == "curve":
                req = float(c.required(np.array([ws]), self.pctx)[0]) * (1 + margin)
                out["g_" + c.key] = req / pw - 1
            else:
                out["g_" + c.key] = ws / c.ws_limit - 1
        if self.P_installed and self.pw_free:
            out["g_power"] = pw * W0 * G0 / self.P_installed - 1
        if not self.pw_free:
            out = {k: v for k, v in out.items() if k[2:] in self.constraint_keys(CD0, K, ws) or k in ("g_span", "g_mtow")}
        b = self.reqs.get("wing_span")
        out["g_span"] = span / b.value - 1 if b is not None and b.sense == "max" else -1.0
        mt = self.reqs.get("mtow")
        out["g_mtow"] = W0 / mt.value - 1 if mt is not None and mt.sense == "max" else -1.0
        return out

    def namespace(self, W0, Wf, ws, AR, pw, n_lim, CD0, K, m_box):
        """Minimal DesignResult-like object for stability_analysis / performance."""
        cfg = self.config(W0, ws, AR)
        Vc = self.Vc(CD0, K, ws)
        bd = self.weights(W0, Wf, ws, AR, pw, n_lim, CD0, K, m_box)["_bd"]
        sz = SimpleNamespace(W0=W0, Wf=Wf, We=bd.empty, crew=self.crew, payload=self.payload, converged=True)
        return SimpleNamespace(spec=self.spec, config=cfg, weights=bd, sizing=sz, CLalpha=self.CLa(cfg, Vc),
                               highlift=self.hl, lowfi=None, polar=DragPolar(CD0, K, self.camber), cruise_speed=Vc,
                               cruise_altitude=self.h, S=cfg.wing.S, avl=None, issues=[])

    def stability(self, W0, Wf, ws, AR, pw, n_lim, CD0, K, m_box):
        from .stability import stability_analysis
        ns = self.namespace(W0, Wf, ws, AR, pw, n_lim, CD0, K, m_box)
        o = self.A["stability"]
        st = stability_analysis(ns, None, o)
        dmax = o.get("elevator_max_deg", 25.0)
        de = max(abs(t["delta_e_deg"]) for t in st.trim.values())
        return {"SM_aft": st.SM_aft, "g_trim": de / dmax - 1, "x_apex_frac": st.x_wing_apex / ns.config.fuselage.length}

    def hq_aeroel_gs(self, W0, Wf, ws, AR, pw, n_lim, CD0, K, m_box):
        """Inequality residuals g ≤ 0 for opted-in aeroelastic strip margins inside SLSQP.

        Reuses :func:`.aeroelasticity.aeroelastic_analysis` (Wright & Cooper / Bisplinghoff strip
        model on the wing box). OAS static coupling is forced off in-loop. HQ discrete levels stay
        on the trust-region hi-fi path (MIL levels are not smooth in the OpenMDAO model).
        Missing structures → each selected aeroel g = 1 (unassessed ≠ free).
        """
        keys = _hq_aeroel_key_set(self.A.get("mdo"))
        out = {}
        for name in ("divergence", "reversal", "flutter"):
            k = "aeroel:" + name
            if keys is not None and k not in keys:
                continue
            out["g_" + name] = 1.0  # default unassessed / fail-closed
        try:
            sr = self.structures(W0, ws, AR, CD0, K)["_sr"]
            ns = self.namespace(W0, Wf, ws, AR, pw, n_lim, CD0, K, m_box)
            ns.structures = sr
            from .aeroelasticity import aeroelastic_analysis
            ae_opts = dict(self.A.get("aeroelasticity") or {})
            ae_opts["static_aerostructural"] = False
            ae = aeroelastic_analysis(ns, ae_opts)
            for name, m in ae.margins.items():
                k = "aeroel:" + name
                if keys is not None and k not in keys:
                    continue
                if math.isfinite(m.get("margin", float("nan"))):
                    out["g_" + name] = 1.0 - m["V_eas"] / m["V_required"]
                else:
                    out["g_" + name] = -1.0 if m.get("ok") else 1.0
        except Exception:
            pass  # leave fail-closed ones at 1.0
        return out

    def cost(self, We, W0, pw, CD0, K, ws):
        return {"cost": unit_cost_estimate(self.spec, We, self.P_sl(pw, W0), self.Vc(CD0, K, ws)).unit_cost}


def _disc(name, fn, inputs, outputs, ref=""):
    return Discipline(name, lambda **kw: fn(**kw), inputs, outputs, reference=ref)


def build_problem(model: AircraftMDO, x0: dict, objective: str = "W0", solver: str = "nlbgs",
                  design_vars=("ws", "pw", "AR"), bounds: dict | None = None, W0_cap: float | None = None,
                  maxiter: int = 60, tol: float = 1e-6, init: dict | None = None):
    """OpenMDAO problem around ``model``; ``x0`` = baseline design variables {ws, pw, AR[, req_value]};
    ``init`` = baseline coupling values (W0, We, Wf, n_lim, CD0, K, m_box) used as initial guesses/scales."""
    i0 = {"W0": 1.0, "We": 0.5, "Wf": 0.2, "n_lim": 3.8, "CD0": 0.03, "K": 0.05, "m_box": 0.1, "S": 1.0,
          "span": 1.0, "E_Wh": 1.0, "m_wing": 0.1, **(init or {})}
    req = model.req_kind is not None
    rv = {"req_value": x0.get("req_value", 0.0)} if req else {}
    cycle = [
        _disc("geom_aero", model.geom_aero, {"W0": i0["W0"], "ws": x0["ws"], "AR": x0["AR"]},
              {"S": i0["S"], "span": i0["span"], "CD0": i0["CD0"], "K": i0["K"]}),
        *([] if model.pw_free else [_disc("envelope", model.envelope, {"ws": x0["ws"], "CD0": i0["CD0"], "K": i0["K"]},
                                          {"pw": x0["pw"]})]),
        _disc("structures", lambda **k: {kk: v for kk, v in model.structures(**k).items() if kk[0] != "_"},
              {"W0": i0["W0"], "ws": x0["ws"], "AR": x0["AR"], "CD0": i0["CD0"], "K": i0["K"]},
              {"n_lim": i0["n_lim"], "m_box": i0["m_box"]}),
        _disc("mission", model.mission, {"W0": i0["W0"], "ws": x0["ws"], "pw": x0["pw"], "AR": x0["AR"],
                                         "CD0": i0["CD0"], "K": i0["K"], **rv}, {"Wf": i0["Wf"], "E_Wh": i0["E_Wh"]}),
        _disc("weights", lambda **k: {kk: v for kk, v in model.weights(**k).items() if kk[0] != "_"},
              {"W0": i0["W0"], "Wf": i0["Wf"], "ws": x0["ws"], "AR": x0["AR"], "pw": x0["pw"], "n_lim": i0["n_lim"],
               "CD0": i0["CD0"], "K": i0["K"], "m_box": i0["m_box"]}, {"We": i0["We"], "m_wing": i0["m_wing"]}),
        _disc("closure", model.closure, {"We": i0["We"], "Wf": i0["Wf"], "ws": x0["ws"], "AR": x0["AR"], **rv},
              {"W0": i0["W0"]}),
    ]
    gkeys = ["g_" + k for k in model.constraint_keys(i0["CD0"], i0["K"], x0["ws"])]
    gkeys += [g for g, r in (("g_span", "wing_span"), ("g_mtow", "mtow"))
              if model.reqs.get(r) is not None and model.reqs.get(r).sense == "max"]
    if model.P_installed and model.pw_free:
        gkeys.append("g_power")
    post = [
        _disc("constraints", model.constraints, {"ws": x0["ws"], "pw": x0["pw"], "CD0": i0["CD0"], "K": i0["K"],
                                                 "W0": i0["W0"], "span": i0["span"]}, {k: 0.0 for k in gkeys}),
        _disc("stability", model.stability, {"W0": i0["W0"], "Wf": i0["Wf"], "ws": x0["ws"], "AR": x0["AR"],
                                             "pw": x0["pw"], "n_lim": i0["n_lim"], "CD0": i0["CD0"], "K": i0["K"],
                                             "m_box": i0["m_box"]}, {"SM_aft": 0.1, "g_trim": 0.0, "x_apex_frac": 0.3}),
        _disc("cost", model.cost, {"We": i0["We"], "W0": i0["W0"], "pw": x0["pw"], "CD0": i0["CD0"], "K": i0["K"],
                                   "ws": x0["ws"]}, {"cost": 1.0}),
    ]
    hq_ae_gkeys = []
    if bool((model.A.get("mdo") or {}).get("hq_aeroel_constraints", False)):
        ae_outs = model.hq_aeroel_gs(i0["W0"], i0["Wf"], x0["ws"], x0["AR"], x0["pw"], i0["n_lim"],
                                     i0["CD0"], i0["K"], i0["m_box"])
        hq_ae_gkeys = [k for k in ae_outs.keys() if k.startswith("g_")]
        if hq_ae_gkeys:
            post.append(_disc(
                "hq_aeroel", model.hq_aeroel_gs,
                {"W0": i0["W0"], "Wf": i0["Wf"], "ws": x0["ws"], "AR": x0["AR"], "pw": x0["pw"],
                 "n_lim": i0["n_lim"], "CD0": i0["CD0"], "K": i0["K"], "m_box": i0["m_box"]},
                {k: 0.0 for k in hq_ae_gkeys}))
    if model.reqs.get("unit_cost") is None and objective != "cost":
        post = [d for d in post if d.name != "cost"]
    b = bounds or {}
    dvs = {}
    for k in design_vars:
        lo, hi = b.get(k, (0.5 * x0[k], 2.0 * x0[k]))
        dvs[k] = {"val": min(max(x0[k], lo), hi), "lower": lo, "upper": hi, "ref": x0[k]}
    if req:
        lo, hi = b.get("req_value", (0.3 * x0["req_value"], 5 * x0["req_value"]))
        dvs["req_value"] = {"val": x0["req_value"], "lower": lo, "upper": hi, "ref": x0["req_value"]}
    obj = {"W0": ("W0", {"ref": i0["W0"]}), "energy": ("E_Wh", {"ref": i0["E_Wh"]}),
           "cost": ("cost", {"ref": 1e5}), "endurance": ("req_value", {"ref": -x0.get("req_value", 1.0)}),
           "range": ("req_value", {"ref": -x0.get("req_value", 1.0)})}[objective]
    cons = {k: {"upper": 0.0} for k in gkeys}
    cons["g_trim"] = {"upper": 0.0}
    for k in hq_ae_gkeys:
        cons[k] = {"upper": 0.0}
    if req:
        cons["W0"] = {"upper": W0_cap, "ref": W0_cap}
    prob = build_openmdao_problem(cycle, post, dvs, obj, cons, solver=solver, opt_maxiter=maxiter, opt_tol=tol)
    for k, v in i0.items():
        try:
            prob.set_val(k, v)
        except Exception:  # pragma: no cover - not a variable of this problem
            pass
    return prob, gkeys + hq_ae_gkeys


def evaluate(prob, x: dict) -> dict:
    for k, v in x.items():
        prob.set_val(k, v)
    prob.run_model()
    return snapshot(prob)


VARS = ("ws", "pw", "AR", "req_value", "W0", "We", "Wf", "E_Wh", "S", "span", "CD0", "K", "n_lim", "m_box", "m_wing",
        "SM_aft", "g_trim", "x_apex_frac", "cost", "g_divergence", "g_reversal", "g_flutter")


def snapshot(prob) -> dict:
    out = {}
    for k in VARS:
        try:
            out[k] = float(prob.get_val(k)[0])
        except Exception:
            pass
    for k in prob.model.get_constraints():
        try:
            out[k] = float(prob.get_val(k)[0])
        except Exception:
            pass
    return out


def global_bounds(res, mo: dict) -> dict:
    fw, fp = mo.get("ws_bounds_factor", [0.6, 1.4]), mo.get("pw_bounds_factor", [0.6, 1.6])
    ws, pw = res.design_point.ws, res.design_point.value
    return {"ws": (fw[0] * ws, fw[1] * ws), "pw": (fp[0] * pw, fp[1] * pw), "AR": tuple(mo.get("AR_bounds", [5.0, 16.0]))}


def optimize(res, systems=None, objective: str | None = None, solver: str | None = None,
             bounds: dict | None = None, W0_cap: float | None = None, hifi: dict | None = None) -> dict:
    """Baseline vs optimum in the same OpenMDAO model. ``res``: converged DesignResult (calibration point);
    ``bounds``: design-variable box (default: from ``assumptions.mdo`` around ``res``); ``W0_cap``: W0 limit
    for endurance/range objectives (default: MTOW requirement, else the W0 of ``res``); ``hifi``: full-pipeline
    values and gradients at x_k ({"x", "W0", "dW0", "E_Wh", "dE_Wh"}) → first-order consistent correction."""
    import time

    import openmdao.api as om  # noqa: F401  (ImportError → caller reports the missing extra)
    spec = res.spec
    mo = spec.assumptions.get("mdo", {})
    objective = objective_from_registry(spec, objective)
    solver = solver or mo.get("solver", "nlbgs")
    model = AircraftMDO(spec, systems, res)
    x0 = {"ws": res.design_point.ws, "pw": res.design_point.value, "AR": res.config.wing.AR}
    cap, W0_cap = W0_cap, None
    if objective in ("endurance", "range"):
        r = spec.requirements.get(objective)
        if r is None:
            raise ValueError(f"objective '{objective}' needs a '{objective}' requirement in the spec")
        model.req_kind = objective
        x0["req_value"] = r.value
        mt = spec.requirements.get("mtow")
        W0_cap = cap or (mt.value if (mt is not None and mt.sense == "max") else res.sizing.W0)
    bounds = bounds or global_bounds(res, mo)
    init = {"W0": res.sizing.W0, "We": res.sizing.We, "Wf": res.sizing.Wf, "CD0": res.polar.CD0, "K": res.polar.K,
            "n_lim": res.structures.vn.n_limit_pos if res.structures else 3.8,
            "m_box": res.structures.box.mass if res.structures else 0.1, "S": res.S, "span": res.config.wing.span,
            "E_Wh": (res.sizing.energy_J or 0) / 3600 or res.sizing.Wf, "m_wing": res.sizing.We * 0.15}
    dvars = [d for d in mo.get("design_vars", ["ws", "AR"]) if d != "AR" or AircraftMDO.ar_is_free(spec)]
    prob, gkeys = build_problem(model, x0, objective, solver, tuple(dvars),
                                bounds, W0_cap, mo.get("maxiter", 60), mo.get("tol", 1e-6), init)
    cons = {}
    if hifi:
        names = ["W0"] + (["E_Wh"] if objective == "energy" else [])
        cons = enforce_consistency(model, prob, x0, hifi, names)
    base = evaluate(prob, x0)
    t = time.time()
    fail = prob.run_driver()
    opt = snapshot(prob)
    dr = prob.driver
    ok = bool(fail.success) if hasattr(fail, "success") else not fail
    sr = getattr(dr, "result", None)
    info = {"success": ok, "message": str(getattr(sr, "message", "")), "iterations": int(getattr(sr, "nit", 0) or 0),
            "time_s": time.time() - t, "n_driver_iters": int(dr.iter_count)}
    act = [k for k in gkeys + ["g_trim"] if k in opt and opt[k] > -1e-3]
    return {"objective": objective, "solver": solver, "baseline": base, "optimum": opt, "driver": info,
            "active_constraints": act, "bounds": bounds, "calibration": model.calibration, "consistency": cons,
            "W0_cap": W0_cap, "design_vars": list(dvars)
            + (["req_value"] if W0_cap is not None else []), "constraint_keys": gkeys + ["g_trim"]}


def enforce_consistency(model: AircraftMDO, prob, x: dict, hifi: dict, names) -> dict:
    """Set the additive corrections so that the coupled model matches the full pipeline at x_k in value and
    gradient (first-order consistency, Alexandrov et al. 2001). The correction enters the closure / mission
    output and is amplified by the coupled growth factor G = ∂W0/∂a, estimated by a secant step."""
    dv = list(hifi["dW0"])
    info = {}
    for _ in range(2):  # two passes: W0 and E_Wh corrections interact through the closure
        for n in names:
            model.corr[n] = model.corr.get(n) or {"x0": dict(x), "a": 0.0, "c": {k: 0.0 for k in dv}}
            c = model.corr[n]
            v0 = evaluate(prob, x)[n]
            da = 1e-3 * max(abs(hifi[n]), 1e-6)
            c["a"] += da
            G = (evaluate(prob, x)[n] - v0) / da
            c["a"] += (hifi[n] - v0) / G - da
            tot = prob.compute_totals(of=[n], wrt=dv, return_format="flat_dict")
            for k in dv:
                g_lo = float(np.ravel(tot[(n, k)])[0])
                c["c"][k] += (hifi["d" + n][k] - g_lo) / G
            info[n] = {"G": G, "a": c["a"], "c": dict(c["c"]), "hifi": hifi[n], "grad_hifi": hifi["d" + n]}
    chk = evaluate(prob, x)
    tot = prob.compute_totals(of=list(names), wrt=dv, return_format="flat_dict")
    for n in names:
        info[n]["after"] = chk[n]
        info[n]["grad_after"] = {k: float(np.ravel(tot[(n, k)])[0]) for k in dv}
    return info


def verification_spec(spec, opt: dict):
    """Spec for the full-pipeline re-run (low-fi aero, systems closure, stability, aeroelasticity, mission
    segments) at the optimum: AR and W/S fixed (design-point criterion ``fixed_ws``); P/W from the envelope."""
    s = copy.deepcopy(spec)
    o = opt["optimum"]
    if "AR" in o:
        s.assumptions["aero"]["AR"] = round(o["AR"], 4)
    a = s.assumptions.get("assembly")
    if a and "AR" in o and AircraftMDO.ar_is_free(s):
        from .assembly.loop import load_spec
        m = load_spec(s, a)               # merged file + overrides (an "options" override replaces the file's)
        m.pop("file", None)
        s.assumptions["assembly"] = {**m, "options": {**(m.get("options") or {}), "AR": round(o["AR"], 4)}}
    s.assumptions["constraints"]["criterion"] = "fixed_ws"
    s.assumptions["constraints"]["ws_fixed"] = o["ws"]
    if "req_value" in o and opt["objective"] in ("endurance", "range"):
        r = s.requirements.get(opt["objective"])
        r.value = o["req_value"]
    return s


def _pipeline_row(res) -> dict:
    """Key results of a full pipeline run (for the baseline vs optimum table)."""
    pf, ae, sr = res.performance, res.aeroelastic, res.structures
    row = {"W0 [kg]": res.sizing.W0, "We [kg]": res.sizing.We, "Wf/bateria [kg]": res.sizing.Wf,
           "W/S [N/m²]": res.design_point.ws, f"{res.design_point.metric} [W/N | -]": res.design_point.value,
           "AR": res.config.wing.AR, "S [m²]": res.S, "b [m]": res.config.wing.span, "CD0": res.polar.CD0,
           "(L/D)max": res.polar.LD_max}
    if res.sizing.energy_J:
        row["energia bateria [Wh]"] = res.sizing.energy_J / 3600
    if res.power_sl:
        row["P_SL [kW]"] = res.power_sl / 1e3
    if sr is not None:
        row["caixão da asa [kg]"] = sr.box.mass
        row["asa (pesos) [kg]"] = next((i.mass for i in res.weights.items if i.key == "wing"), math.nan) \
            if res.weights else math.nan
    if pf is not None:
        row["alcance (segmentos) [km]"] = pf.mission.range_m / 1e3
        row["autonomia (segmentos) [h]"] = pf.mission.endurance_s / 3600
    if ae is not None:
        for k, m in ae.margins.items():
            row[f"margem {k} vs 1.2 V_D"] = m["margin"]
    if res.cost is not None:
        row["custo unitário"] = res.cost.unit_cost
    row["viável (dimensionamento)"] = res.feasible
    row["verificado (fase 2/3)"] = res.verified
    row["falhas"] = ", ".join(c.key for c in res.checks if c.ok is False) or "—"
    return row


def _hq_aeroel_key_set(mo: dict | None) -> set[str] | None:
    """Optional allow-list of ``hq:*`` / ``aeroel:*`` keys (or bare suffixes). None → all such checks."""
    if not mo:
        return None
    keys = mo.get("hq_aeroel_keys")
    if not keys:
        return None
    out = set()
    for k in keys:
        s = str(k).strip()
        if not s:
            continue
        if ":" in s:
            out.add(s)
        else:
            out.add("hq:" + s)
            out.add("aeroel:" + s)
    return out


def _hq_aeroel_selected(key: str, allow: set[str] | None) -> bool:
    if not key.startswith(("hq:", "aeroel:")):
        return False
    return allow is None or key in allow


def hq_aeroel_constraint_status(res, *, enabled: bool, keys: set[str] | None = None) -> dict:
    """Classify ``hq:*`` / ``aeroel:*`` as active / violated / unassessed for the MDO constraint path.

    Unassessed (``ok is None``) is **never** treated as satisfied when ``enabled`` (unknown ≠ pass).
    When ``enabled`` is False the lists are empty and the legacy filter-after behaviour applies.
    """
    active, violated, unassessed, values = [], [], [], {}
    if not enabled:
        return {"enabled": False, "active": active, "violated": violated, "unassessed": unassessed,
                "values": values, "violation": 0.0}
    margins = {}
    ae = getattr(res, "aeroelastic", None)
    if ae is not None:
        margins = getattr(ae, "margins", None) or {}
    v_extra = 0.0
    smooth_aeroel = set()
    for name, m in margins.items():
        key = "aeroel:" + name
        if not _hq_aeroel_selected(key, keys):
            continue
        if math.isfinite(m.get("margin", float("nan"))):
            g = 1.0 - m["V_eas"] / m["V_required"]
            values[key] = g
            smooth_aeroel.add(key)
            active.append(key)
            if g > 0:
                violated.append(key)
                v_extra += max(0.0, g)
            # infinite V (no singularity) → g = −∞ effectively satisfied; skip
        else:
            # V → ∞: margin inf → satisfied if ok else fall through to checks
            active.append(key)
            values[key] = -1.0 if m.get("ok") else 1.0
            if not m.get("ok"):
                violated.append(key)
                v_extra += 1.0
    for c in getattr(res, "checks", []) or []:
        if not _hq_aeroel_selected(c.key, keys):
            continue
        if c.key in smooth_aeroel:
            continue  # already counted via strip margins
        active.append(c.key)
        if c.ok is None:
            unassessed.append(c.key)
            values[c.key] = None
            v_extra += 1.0  # unassessed ≠ satisfied constraint
        elif c.ok is False:
            violated.append(c.key)
            values[c.key] = 1.0
            v_extra += 1.0
        else:
            values[c.key] = 0.0
    return {"enabled": True, "active": active, "violated": violated, "unassessed": unassessed,
            "values": values, "violation": v_extra}


def _hifi(res, objective: str, W0_cap: float | None, hq_aeroel: bool = False,
         hq_aeroel_keys: set[str] | None = None):
    """Objective, constraint violation, failed-check set and HQ/aeroel constraint status.

    ``hq_aeroel`` (``assumptions.mdo.hq_aeroel_constraints``): selected ``hq:*`` / ``aeroel:*`` become
    inequality constraints inside the trust-region merit φ = f/|f₀| + μ·violation — not only a
    post-hoc acceptance filter. Aeroelastic strip margins enter as g = 1 − V/V_req ≤ 0 (Wright &
    Cooper / Bisplinghoff strip model; Phase 4 ``k_flutter`` when calibrated). Discrete MIL-F-8785C
    level / scissor / AEER checks enter as g = 0 (pass) or 1 (fail). Unassessed checks (``ok is
    None``, e.g. ``hq:spiral`` without explicit dihedral) add a unit violation and are listed —
    never treated as satisfied. Default ``hq_aeroel=False`` keeps the legacy filter-after behaviour
    (hq:/aeroel: excluded from both violation and the failed set used by acceptance).
    """
    sz, rq = res.sizing, res.spec.requirements
    if objective == "W0":
        f = sz.W0
    elif objective == "energy":
        f = sz.energy_J / 3600 if sz.energy_J else sz.Wf
    elif objective == "cost":
        f = res.cost.unit_cost if res.cost is not None else math.nan
    else:
        f = -rq.get(objective).value
    v = 0.0
    b = rq.get("wing_span")
    if b is not None and b.sense == "max" and res.config is not None:
        v += max(0.0, res.config.wing.span / b.value - 1)
    mt = rq.get("mtow")
    if mt is not None and mt.sense == "max":
        v += max(0.0, sz.W0 / mt.value - 1)
    if W0_cap and objective in ("endurance", "range"):
        v += max(0.0, sz.W0 / W0_cap - 1)
    if not sz.converged:
        v += 1.0
    # A pinned motor/ESC/cell that misses its rating is not a lighter aircraft: count it as one violation
    # so the continuous step cannot profit from dropping the component mass.
    sy = getattr(res, "systems", None)
    if sy is not None and not getattr(sy, "pinned_ok", True):
        v += 1.0
    status = hq_aeroel_constraint_status(res, enabled=hq_aeroel, keys=hq_aeroel_keys)
    v += status["violation"]
    failed = set()
    for c in res.checks:
        if c.ok is not False:
            continue
        if c.key.startswith(("hq:", "aeroel:")):
            if not hq_aeroel:
                continue  # legacy: filter-after only — omit from failed set
            if not _hq_aeroel_selected(c.key, hq_aeroel_keys):
                continue  # not in the selected constraint set
        failed.add(c.key)
    # opted-in unassessed keys are not "failed" (ok is not False) but are not satisfied either —
    # they already contribute to v; surface them in status for the report.
    return f, v, failed, status


def _lofi_viol(snap: dict, W0_cap) -> float:
    v = sum(max(0.0, snap.get(k, -1.0)) for k in ("g_span", "g_mtow"))
    if W0_cap:
        v += max(0.0, snap["W0"] / W0_cap - 1)
    return v


def discrete_improves(phi_k: float, phi_new: float, failed_k, failed_new) -> bool:
    """Accept a new motor/ESC/cell assignment when the merit falls and no new check fails.

    Geoffrion, J. Optim. Theory Appl. 10(4), 1972: the integer master is decided outside the continuous
    subproblem. The cutoff 1e-5 is the same one ``optimize_pipeline`` uses for a predicted reduction of zero.
    """
    return (phi_k - phi_new) > 1e-5 and not (set(failed_new) - set(failed_k))


def _catalog_master(res_point, spec_geometry, *, objective, W0_cap, hqa, phi_k, failed_k, ids_now,
                    cell_fixed, ref, mu, hqa_keys=None) -> dict:
    """Re-select the catalog at ``res_point``. A full pipeline runs only when that selection differs.

    ``spec_geometry`` is the pinned spec already placed at the trial W/S and AR. The returned spec, when
    accepted, carries the new pin. The continuous model is not touched here.
    """
    from acdt.core.pipeline import run_pipeline

    from .systems_integration import apply_catalog_pin, catalog_ids, clear_catalog_pin, select_systems

    if getattr(res_point.spec, "propulsion_kind", None) != "electric":
        return {"accepted": False, "same": True}
    probe_spec = clear_catalog_pin(copy.deepcopy(res_point.spec), keep_cell=cell_fixed)
    probe = copy.copy(res_point)
    probe.spec = probe_spec
    proposed = catalog_ids(select_systems(probe))
    if proposed == ids_now or not any(proposed.values()):
        return {"accepted": False, "same": True}
    sv_d = clear_catalog_pin(copy.deepcopy(spec_geometry), keep_cell=cell_fixed)
    st_d = run_pipeline("aircraft", sv_d)
    r_d = st_d["result"]
    ids_final = catalog_ids(st_d.get("systems"))
    if not r_d.sizing.converged or r_d.config is None or ids_final == ids_now:
        return {"accepted": False, "same": ids_final == ids_now, "to": ids_final,
                "reason": "fecho não convergiu" if ids_final != ids_now else None}
    f_d, v_d, F_d, _st_d = _hifi(r_d, objective, W0_cap, hqa, hqa_keys if hqa_keys is not None else _hq_aeroel_key_set((getattr(r_d.spec, "assumptions", {}) or {}).get("mdo")))
    if not math.isfinite(f_d):
        return {"accepted": False, "to": ids_final, "reason": "mérito não finito"}
    phi_d = f_d / ref + mu * v_d
    info = {"from": ids_now, "to": ids_final, "phi": phi_d, "accepted": False}
    if discrete_improves(phi_k, phi_d, failed_k, F_d):
        apply_catalog_pin(sv_d, ids_final, cell_fixed=cell_fixed)
        info.update(accepted=True, result=r_d, systems=st_d.get("systems"), spec=sv_d, failed=F_d)
    return info


def _take_catalog(info: dict, state: dict, objective, gb, order) -> dict:
    """Apply an accepted catalog decision to the trust-region state. ``state`` holds res/sys/spec/phi/F/hg."""
    public = {k: info[k] for k in ("accepted", "same", "from", "to", "phi", "reason") if k in info and info[k] is not None}
    if not info.get("accepted"):
        return public
    state["res"] = info["result"]
    state["sys"] = info["systems"]
    state["spec"] = info["spec"]
    state["phi"] = info["phi"]
    state["failed"] = info["failed"]
    if order >= 1:
        state["hg"] = hifi_gradient(state["spec"], state["res"], objective, gb)
    return public


def _hifi_values(res, objective) -> dict:
    sz = res.sizing
    return {"W0": sz.W0, "E_Wh": sz.energy_J / 3600 if sz.energy_J else sz.Wf}


def hifi_gradient(spec, res, objective: str, gb: dict, rel_step: float = 0.02) -> dict:
    """Forward finite differences of the full pipeline (W0, E_Wh) w.r.t. W/S, AR [, requirement value] at
    the iterate ``res`` (P/W follows the constraint envelope in the pipeline, so it is not a free variable
    there: its correction gradient is zero)."""
    from acdt.core.pipeline import run_pipeline
    x = {"ws": res.design_point.ws, "AR": res.config.wing.AR}
    if not AircraftMDO.ar_is_free(spec):
        x.pop("AR")                       # assembly with uniform scaling: AR is the drawing's
    if objective in ("endurance", "range"):
        x["req_value"] = res.spec.requirements.get(objective).value
    v0 = _hifi_values(res, objective)
    out = {"x": dict(x), **v0, "dW0": {}, "dE_Wh": {}, "steps": {}}
    for k in x:
        h = rel_step * x[k]
        if k in gb and x[k] + h > gb[k][1]:
            h = -h
        for hh in (h, -h):  # forward, then backward if the perturbed design does not close
            xp = {**x, k: x[k] + hh}
            r = run_pipeline("aircraft", verification_spec(spec, {"optimum": xp, "objective": objective}))["result"]
            v = _hifi_values(r, objective)
            if math.isfinite(v["W0"]) and math.isfinite(v["E_Wh"]):
                out["dW0"][k] = (v["W0"] - v0["W0"]) / hh
                out["dE_Wh"][k] = (v["E_Wh"] - v0["E_Wh"]) / hh
                out["steps"][k] = hh
                break
        # (no finite difference available → that variable keeps the zeroth-order correction only)
    return out


def optimize_pipeline(spec_path, out, objective: str | None = None, solver: str | None = None,
                      max_iter: int | None = None, verbose: bool = True) -> dict:
    """Full workflow of ``acdt optimize``.

    Trust-region model management (Alexandrov, Dennis, Lewis & Torczon, Struct. Optim. 15, 1998; Alexandrov
    et al., Struct. Multidisc. Optim. 21, 2001; Conn, Gould & Toint, *Trust-Region Methods*, SIAM 2000,
    Alg. 6.1.1): the OpenMDAO model (handbook disciplines, β-calibrated — zeroth-order consistent — at the
    current iterate x_k, motor/ESC/cell pinned) is optimised inside a box ±Δ·x_k; the step is evaluated with
    the full pipeline ("high fidelity": XFOIL/AVL polar in the sizing loop, the same pinned catalog, stability,
    aeroelasticity, segment mission); ρ = actual/predicted reduction of the merit φ = f/|f_0| + μ·violation
    (μ = 10) decides acceptance (ρ > η₁ = 0.01 and no new failed sizing/performance check) and the radius
    (ρ < 0.25 → Δ/2; ρ > 0.75 and step on the boundary → 2Δ). A catalog master then re-selects the lightest
    feasible motor, ESC and cell and accepts that assignment only when φ improves (Geoffrion 1972). Writes
    ``mdo_report.md`` + ``mdo.json`` and the full reports of the baseline and of the accepted optimum."""
    import json
    from pathlib import Path

    from acdt.core.pipeline import run_pipeline
    from .systems_integration import apply_catalog_pin, catalog_ids
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stb = run_pipeline("aircraft", spec_path, output=out / "baseline")
    rb = stb["result"]
    if not rb.sizing.converged or rb.config is None:
        raise RuntimeError("baseline did not converge — nothing to optimise")
    spec0 = stb["spec"]
    mo = spec0.assumptions.get("mdo", {})
    objective = objective_from_registry(spec0, objective)
    max_iter = max_iter or int(mo.get("trust_region_iterations", 8))
    gb = global_bounds(rb, mo)
    W0_cap = None
    if objective in ("endurance", "range"):
        mt = spec0.requirements.get("mtow")
        W0_cap = mt.value if (mt is not None and mt.sense == "max") else rb.sizing.W0
    hqa = bool(mo.get("hq_aeroel_constraints", False))
    hqa_keys = _hq_aeroel_key_set(mo)
    f0, v0, F0, st0 = _hifi(rb, objective, W0_cap, hqa, hqa_keys)
    ref, mu = abs(f0) or 1.0, 10.0
    res_k, sys_k, spec_k = rb, stb.get("systems"), spec0
    phi_k, F_k = f0 / ref + mu * v0, F0
    delta, dmax, dmin = float(mo.get("trust_region_radius", 0.3)), 1.0, 0.02
    hist, first, last_opt = [], None, None
    order = mo.get("consistency_order", 1)
    cell_fixed = bool((spec0.systems or {}).get("cell_id"))
    if any(catalog_ids(sys_k).values()):
        apply_catalog_pin(spec0, catalog_ids(sys_k), cell_fixed=cell_fixed)
    state = {"res": res_k, "sys": sys_k, "spec": spec_k, "phi": phi_k, "failed": F_k, "hg": None}
    sv_base = verification_spec(spec_k, {"optimum": {"AR": res_k.config.wing.AR, "ws": res_k.design_point.ws,
                                                     "pw": res_k.design_point.value}, "objective": objective})
    info0 = _catalog_master(res_k, sv_base, objective=objective, W0_cap=W0_cap, hqa=hqa, phi_k=phi_k,
                            failed_k=F_k, ids_now=catalog_ids(sys_k), cell_fixed=cell_fixed, ref=ref, mu=mu,
                            hqa_keys=hqa_keys)
    _take_catalog(info0, state, objective, gb, 0)
    res_k, sys_k, spec_k = state["res"], state["sys"], state["spec"]
    phi_k, F_k = state["phi"], state["failed"]
    hg = hifi_gradient(spec_k, res_k, objective, gb) if order >= 1 else None
    for it in range(1, max_iter + 1):
        xk = {"ws": res_k.design_point.ws, "pw": res_k.design_point.value, "AR": res_k.config.wing.AR}
        bnd = {k: (max(gb[k][0], xk[k] * (1 - delta)), min(gb[k][1], xk[k] * (1 + delta))) for k in xk}
        if W0_cap is not None:
            r0 = res_k.spec.requirements.get(objective).value
            bnd["req_value"] = (r0 * (1 - delta), r0 * (1 + delta))
        try:
            opt = optimize(res_k, sys_k, objective, solver, bounds=bnd, W0_cap=W0_cap, hifi=hg)
        except Exception as e:  # the model failed inside the region (e.g. a geometry with no closure)
            hist.append({"iter": it, "delta": delta, "x_k": xk, "x_trial": {}, "predicted": math.nan,
                         "status": f"modelo falhou ({type(e).__name__}); Δ reduzido"})
            delta *= 0.5
            if delta < dmin:
                break
            continue
        first = first or opt
        b_, o_ = opt["baseline"], opt["optimum"]
        key = {"W0": "W0", "energy": "E_Wh", "cost": "cost"}.get(objective, "req_value")
        sgn = -1.0 if objective in ("endurance", "range") else 1.0
        pred = (sgn * (b_[key] - o_[key])) / ref + mu * (_lofi_viol(b_, W0_cap) - _lofi_viol(o_, W0_cap))
        row = {"iter": it, "delta": delta, "x_k": xk, "x_trial": {k: o_[k] for k in list(xk) + (
            ["req_value"] if "req_value" in o_ else [])}, "predicted": pred, "lofi_success": opt["driver"]["success"]}
        if pred < 1e-5:
            row.update(status="convergiu (modelo não prevê melhoria)")
            hist.append(row)
            break
        sv = verification_spec(spec_k, opt)
        st = run_pipeline("aircraft", sv)
        r_new = st["result"]
        f, v, F, st = _hifi(r_new, objective, W0_cap, hqa, hqa_keys)
        phi = f / ref + mu * v
        actual = phi_k - phi
        rho = actual / pred
        new_fail = sorted(F - F_k)
        on_edge = any(abs(o_[k] - bnd[k][0]) < 1e-6 * abs(bnd[k][0]) + 1e-9 or
                      abs(o_[k] - bnd[k][1]) < 1e-6 * abs(bnd[k][1]) + 1e-9 for k in xk)
        accept = rho > 0.01 and not new_fail
        row.update(actual=actual, rho=rho, f_hifi=f, viol_hifi=v, new_failures=new_fail, accepted=accept,
                   W0_hifi=r_new.sizing.W0, hq_aeroel_status=st)
        if accept:
            res_k, sys_k, spec_k, phi_k, F_k, last_opt = r_new, st.get("systems"), sv, phi, F, opt
            if order >= 1 and it < max_iter:
                hg = hifi_gradient(sv, r_new, objective, gb)
        if rho < 0.25 or not accept:
            delta *= 0.5
        elif rho > 0.75 and on_edge:
            delta = min(2 * delta, dmax)
        state = {"res": res_k, "sys": sys_k, "spec": spec_k, "phi": phi_k, "failed": F_k, "hg": hg}
        info_d = _catalog_master(r_new, sv, objective=objective, W0_cap=W0_cap, hqa=hqa, phi_k=phi_k,
                                 failed_k=F_k, ids_now=catalog_ids(sys_k), cell_fixed=cell_fixed, ref=ref, mu=mu,
                                 hqa_keys=hqa_keys)
        row["discrete"] = _take_catalog(info_d, state, objective, gb, order if it < max_iter else 0)
        res_k, sys_k, spec_k = state["res"], state["sys"], state["spec"]
        phi_k, F_k, hg = state["phi"], state["failed"], state["hg"]
        row["delta_next"] = delta
        hist.append(row)
        if verbose:
            cat = row["discrete"]
            cat_txt = ""
            if cat.get("accepted"):
                cat_txt = f" catálogo aceite ({(cat.get('to') or {}).get('motor_id')})"
            elif cat.get("to") and not cat.get("same"):
                cat_txt = " catálogo rejeitado"
            print(f"[acdt] TR {it}: Δ={row['delta']:.3f} pred={pred:.4f} act={actual:.4f} ρ={rho:.2f} "
                  f"{'aceite' if accept else 'rejeitado'} {new_fail or ''} W0={r_new.sizing.W0:.4g}{cat_txt}")
        if delta < dmin:
            row["status"] = "convergiu (Δ < Δ_min)"
            break
    # report of the accepted optimum
    if hist and "status" not in hist[-1]:
        hist[-1]["status_note"] = "limite de iterações"
    if res_k is rb:
        ro = rb
        st_final = st0
    else:
        ro = run_pipeline("aircraft", spec_k, output=out / "optimum")["result"]
        _, _, _, st_final = _hifi(ro, objective, W0_cap, hqa, hqa_keys)
    rep = {"objective": objective, "solver": first["solver"], "first_lofi": first, "last_lofi": last_opt or first,
           "trust_region": hist, "W0_cap": W0_cap, "global_bounds": gb, "merit": "φ = f/|f0| + 10·violação",
           "consistency_order": order, "hq_aeroel_constraints": hqa,
           "hq_aeroel_keys": sorted(hqa_keys) if hqa_keys is not None else None,
           "hq_aeroel_status": st_final,
           "improved": ro is not rb,
           "pipeline": {"baseline": _pipeline_row(rb), "optimum": _pipeline_row(ro)},
           "x_baseline": {"ws": rb.design_point.ws, "pw": rb.design_point.value, "AR": rb.config.wing.AR},
           "x_optimum": {"ws": ro.design_point.ws, "pw": ro.design_point.value, "AR": ro.config.wing.AR}}
    if W0_cap is not None:
        rep["x_baseline"]["req_value"] = rb.spec.requirements.get(objective).value
        rep["x_optimum"]["req_value"] = ro.spec.requirements.get(objective).value
    (out / "mdo.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    write_mdo_report(rep, out / "mdo_report.md", spec0.name)
    return {"opt": rep, "baseline": rb, "optimum": ro, "report": out / "mdo_report.md"}


def _fmt(v):
    if isinstance(v, bool) or v is None:
        return {True: "sim", False: "não", None: "n/a"}[v]
    if isinstance(v, float):
        return f"{v:.4g}" if math.isfinite(v) else "∞"
    return str(v)


def write_mdo_report(rep: dict, path, name: str = ""):
    fo = rep["first_lofi"]
    L = [f"# Otimização multidisciplinar (OpenMDAO) — {name}", "",
         f"* objetivo: **{rep['objective']}** (registo de requisitos / `assumptions.mdo.objective` / `--objective`)"
         + (f"; W0 ≤ {rep['W0_cap']:.4g} kg" if rep["W0_cap"] else ""),
         f"* formulação MDF; MDA {rep['solver'].upper()} (Gauss–Seidel não linear com Aitken, ou Newton); "
         "derivadas parciais por diferenças finitas centrais de cada disciplina; totais pelo sistema linear "
         "acoplado; SLSQP (scipy)",
         f"* variáveis de projeto: {', '.join(fo['design_vars'])}; limites globais: "
         + "; ".join(f"{k} ∈ [{a:.4g}, {b:.4g}]" for k, (a, b) in rep["global_bounds"].items()),
         "* gestão de modelos por região de confiança (Alexandrov et al. 1998/2001; Conn, Gould & Toint 2000): "
         "modelo OpenMDAO (métodos de manual com correção β multiplicativa da polar, mais correção aditiva de "
         f"ordem {rep['consistency_order']} de W0 (e E) — valor"
         + (" e gradiente (diferenças finitas do pipeline completo)" if rep["consistency_order"] else "")
         + " iguais ao pipeline completo no iterado x_k —, sistemas congelados no iterado) otimizado em ±Δ·x_k; cada passo "
         "verificado no pipeline completo (XFOIL/AVL no ciclo, catálogo de motor/ESC/célula fixo, estabilidade, "
         f"aeroelasticidade, missão por segmentos). Mérito: {rep['merit']}.",
         f"* resultado: {'melhoria aceite no pipeline completo' if rep['improved'] else 'nenhum passo aceite — o ponto base é (localmente) ótimo para o pipeline completo'}",
         "", "## Iterações da região de confiança", "",
         "| it | Δ | x_k (W/S, P/W, AR) | passo (modelo) | redução prevista | real | ρ | estado |", "|---|---|---|---|---|---|---|---|"]
    for h in rep["trust_region"]:
        xk = ", ".join(f"{h['x_k'][k]:.4g}" for k in ("ws", "pw", "AR"))
        xt = ", ".join(f"{k} {v:.4g}" for k, v in h["x_trial"].items())
        stt = "" if "accepted" not in h else ("aceite" if h["accepted"] else "rejeitado" + (
            f" (novas falhas: {', '.join(h['new_failures'])})" if h.get("new_failures") else ""))
        d = h.get("discrete") or {}
        if d.get("accepted"):
            who = (d.get("to") or {}).get("motor_id") or (d.get("to") or {}).get("cell_id") or "catálogo"
            stt = "; ".join(x for x in (stt, f"catálogo aceite ({who})") if x)
        elif d.get("to") and not d.get("same"):
            stt = "; ".join(x for x in (stt, "catálogo rejeitado") if x)
        stt = "; ".join(x for x in (stt, h.get("status"), h.get("status_note")) if x)
        L.append(f"| {h['iter']} | {h['delta']:.3g} | {xk} | {xt} | {h['predicted']:.4f} | "
                 f"{_fmt(h.get('actual'))} | {_fmt(h.get('rho'))} | {stt} |")
    L += ["", "## Primeira otimização do modelo (calibrado no ponto base): base vs ótimo do modelo", "",
          "| grandeza | base | ótimo (modelo) |", "|---|---|---|"]
    for k in fo["baseline"]:
        L.append(f"| {k} | {_fmt(fo['baseline'][k])} | {_fmt(fo['optimum'].get(k))} |")
    L += ["", f"Ativas: {', '.join(fo['active_constraints']) or '—'}; calibração: {fo['calibration']}. "
          "Restrições g ≤ 0 (g = requisito/valor − 1).", "",
          "## Pipeline completo: base vs ótimo aceite", "", "| grandeza | base | ótimo |", "|---|---|---|"]
    pb, po = rep["pipeline"]["baseline"], rep["pipeline"]["optimum"]
    for k in pb:
        L.append(f"| {k} | {_fmt(pb[k])} | {_fmt(po.get(k))} |")
    L += ["", "Notas: o SLSQP só vê W/S, P/W e AR, com o motor, o ESC e a célula fixos (Geoffrion, J. Optim. "
          "Theory Appl. 10, 1972: o subproblema contínuo não atravessa a atribuição inteira). Um passo de catálogo "
          "à parte reescolhe o mais leve que cumpre a potência e a corrente, e só é aceite se o mérito do pipeline "
          "melhora e não há verificações novas a falhar. Não há catálogo de hélices: o diâmetro segue Raymer "
          "Sec. 10.3. Os servos continuam a ser reescolhidos no fecho. " + (
          "Restrições HQ/aeroelásticas ATIVAS (`mdo.hq_aeroel_constraints`): `hq:*`/`aeroel:*` entram na "
          "violação do mérito φ (margens aeroelásticas suaves; níveis MIL / scissor / AEER como g∈{0,1}); "
          "unassessed ≠ satisfeito (listados em `hq_aeroel_status`). " + (
              f"Estado: violadas={rep.get('hq_aeroel_status', {}).get('violated')}; "
              f"unassessed={rep.get('hq_aeroel_status', {}).get('unassessed')}."
          ) if rep.get("hq_aeroel_constraints")
          else "As verificações hq:/aeroel: não são restrições do MDO (omissão = filtro pós-ótimo legado; "
          "ativar com `assumptions.mdo.hq_aeroel_constraints: true`) — ver as falhas na tabela."),
          "", "Relatórios completos: `baseline/report.md`" + (", `optimum/report.md`." if rep["improved"] else "."), ""]
    from pathlib import Path
    Path(path).write_text("\n".join(L), encoding="utf-8")
    return path


def _gear_dcd0(aa: dict, S):
    from .aero.gear_drag import dcd0_takeoff
    return dcd0_takeoff(aa, S)
