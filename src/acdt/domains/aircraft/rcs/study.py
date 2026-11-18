"""Aero / RCS shape trade study (Phase 6, LOW FIDELITY).

* RCS: Physical Optics on the faceted parametric aircraft (:mod:`.geometry`, :mod:`acdt.core.em.po`), monostatic,
  frontal sector |az| ≤ 30°, elevations {−5°, 0°, +5°}, VV (single-bounce PO co-polar monostatic σ is
  polarisation independent: ê·[n̂×(k̂×ê)] = −n̂·k̂, so HH = VV; polarisation enters only through the 2nd bounce,
  evaluated on the picks); metric = arithmetic mean of σ (m², reported in
  dBsm), plus median and max.
* Aero: the existing low-fi drag build-up (Raymer Eq. 12.24/12.27/12.30/12.31 via :mod:`acdt.domains.aircraft.aero.drag`)
  applied *differentially* — ΔCD0 between the candidate and the baseline faceted shape is added to the baseline
  CD0 of the sized aircraft (``result.json``); the Oswald factor is scaled by the Nita & Scholz (2012) ratio
  e(Λ, λ)/e(Λ0, λ0) (sweep/taper effect; e_theo = 1/(1 + f(λ−Δλ)A), Δλ = −0.357 + 0.45 e^{−0.0375 Λ25}).
  Objective: cruise L/D at the sized W0 and cruise speed.
* V-tail area from the Purser & Campbell projected-area rule (NACA Rep. 823).
* OpenMDAO model (DOE / Latin hypercube) → non-dominated (Pareto) set of (L/D max-is-better, frontal RCS
  min-is-better); optional ε-constraint refinement with COBYLA.

``LIMITATIONS``: see :data:`acdt.core.em.po.LIMITATIONS`; plus no wing-weight penalty for sweep, no stability/
control re-trim for the V-tail, faceted (diamond) sections only in the RCS model — the aero build-up uses form
factors for a 50 %-thickness section."""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

from ....core.atmosphere import isa
from ....core.em import po
from ..aero.drag import ff_body, ff_lifting_surface, skin_friction
from . import geometry as G

FREQ_DEFAULT = 10e9


def oswald_nita_scholz(AR, taper, sweep_c4_deg, d_f_over_b=0.0, ke_D0=0.804):
    """Nita & Scholz (2012), DLRK paper 'Estimating the Oswald factor from basic aircraft geometrical parameters':
    e = e_theo·k_eF·k_eD0·k_eM (k_eM = 1 below M 0.3; k_eD0 = 0.804 general aviation)."""
    dl = -0.357 + 0.45 * math.exp(-0.0375 * sweep_c4_deg)
    x = taper - dl
    f = 0.0524 * x ** 4 - 0.15 * x ** 3 + 0.1659 * x ** 2 - 0.0706 * x + 0.0119
    e_theo = 1 / (1 + f * AR)
    return e_theo * (1 - 2 * d_f_over_b ** 2) * ke_D0


def baseline_from_result(path) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    g, a = d["geometry"], d["aero"]
    w = g["wing"]
    base = {"name": d.get("name", Path(path).parent.name), "S": w["S_m2"], "b": w["span_m"], "taper": w["taper"],
            "tc": w["t/c"], "sweep_le_deg": w.get("sweep_LE_deg", 0.0), "L": g["fuselage"]["length_m"],
            "D": g["fuselage"]["diameter_m"], "S_h": g["htail"]["S_m2"], "S_v": g["vtail"]["S_m2"],
            "tail_arm": g["htail"].get("arm_m"), "CD0": a["CD0"], "K": a["K"], "V": a["cruise_speed_m_s"],
            "h": a["cruise_altitude_m"], "W0_kg": d["weights"]["W0_kg"], "AR": w["AR"]}
    items = {i["key"]: i["mass"] for i in d.get("weight_breakdown", {}).get("items", [])}
    base["m_wing"] = items.get("wing", 0.0)
    base["m_tails"] = items.get("htail", 0.0) + items.get("vtail", 0.0)
    base["m_fuselage"] = items.get("fuselage", 0.0)
    base["e"] = 1 / (math.pi * base["AR"] * base["K"])
    return base


def baseline_shape(base) -> G.Shape:
    """Faceted equivalent of the sized aircraft: its LE sweep, baseline taper, 45° chine (ASSUMPTION), V-tail cant
    giving the same projected areas (tan²Γ = S_v/S_h, Purser & Campbell)."""
    return G.Shape(base["sweep_le_deg"], 0.0, 45.0, math.degrees(math.atan(math.sqrt(base["S_v"] / base["S_h"]))))


def _components(base, shape, info, V, rho, mu, a):
    M = V / a
    pl = info["planform"]
    lam = pl["taper"]
    mac = 2 / 3 * pl["c_root"] * (1 + lam + lam ** 2) / (1 + lam)
    comps = {}
    cf = skin_friction(rho * V * mac / mu, M, 0.10)
    comps["wing"] = cf * ff_lifting_surface(base["tc"], 0.5, M, math.radians(pl["sweep_c2_deg"])) * 1.0 \
        * info["wet"]["wing"]
    ct = info["tail_c_root"] * (1 + 0.5) / 2
    cf = skin_friction(rho * V * ct / mu, M, 0.10)
    comps["vtail"] = cf * ff_lifting_surface(G.DEFAULTS["tail_tc"], 0.5, M, math.radians(max(shape.sweep_le_deg, 15)))\
        * 1.04 * info["wet"]["vtail"]
    De = math.sqrt(4 * info["fuselage"]["area"] / math.pi)
    cf = skin_friction(rho * V * base["L"] / mu, M, 0.0)
    comps["fuselage"] = cf * ff_body(base["L"] / De) * info["wet"]["fuselage"]
    return comps


def aero_eval(base, shape: G.Shape, info, ref=None) -> dict:
    st = isa(base["h"])
    rho, mu, a = st.rho, st.mu, st.a
    V = base["V"]
    comps = _components(base, shape, info, V, rho, mu, a)
    f = sum(comps.values()) * 1.05                       # 5 % leakage & protuberances, as the Phase 1 build-up
    pl = info["planform"]
    e_ns = oswald_nita_scholz(base["AR"], pl["taper"], pl["sweep_c4_deg"], info["fuselage"]["W"] / base["b"])
    # structural-mass trends (fixed payload/battery; no re-sizing snowball):
    #   wing — Raymer Eq. 15.46 (GA): W ∝ (A/cos²Λ)^0.6 λ^0.04 (100 t/c / cosΛ)^−0.3  → ∝ cos(Λ)^−0.9 λ^0.04
    #   tails — minimum-gauge wetted-area law of the sized aircraft (kg/m², Phase 1 user layup) → ∝ S_wet
    #   fuselage — Raymer Eq. 15.49: W ∝ S_f^1.086
    cl = math.cos(math.radians(pl["sweep_c4_deg"]))
    wing_t = cl ** -0.9 * max(pl["taper"], 1e-3) ** 0.04
    if ref is None:
        return {"f_m2": f, "e_ns": e_ns, "wing_t": wing_t, "wet": dict(info["wet"])}
    dm = (base["m_wing"] * (wing_t / ref["wing_t"] - 1)
          + base["m_fuselage"] * ((info["wet"]["fuselage"] / ref["wet"]["fuselage"]) ** 1.086 - 1)
          + base["m_tails"] * (info["wet"]["vtail"] / ref["wet"]["vtail"] - 1))
    CD0 = base["CD0"] + (f - ref["f_m2"]) / base["S"]
    e = base["e"] * e_ns / ref["e_ns"]
    K = 1 / (math.pi * base["AR"] * e)
    q = 0.5 * rho * V * V
    W = base["W0_kg"] + dm
    CL = W * 9.80665 / (q * base["S"])
    CD = CD0 + K * CL * CL
    # electric endurance (fixed battery energy) and range at fixed cruise speed both scale with (L/D)/W
    perf = (CL / CD / W) / (ref["LD0"] / base["W0_kg"]) if "LD0" in ref else 1.0
    return {"CD0": CD0, "e": e, "CL": CL, "CD": CD, "LD": CL / CD, "perf_ratio": perf, "P_req_W": W * 9.80665 * V * CD / CL, "LD_max": 0.5 / math.sqrt(CD0 * K),
            "taper": pl["taper"], "dW_struct_kg": dm, "W_kg": W, "sweep_c4_deg": pl["sweep_c4_deg"], "S_vtail": info["S_vtail"],
            "components_f_m2": comps}


def rcs_eval(mesh, freq=FREQ_DEFAULT, az_lim=30.0, daz=0.5, els=(-5.0, 0.0, 5.0), pols=("VV",),
             occlusion=True, bounces=1, n_sub_max=12) -> dict:
    az = np.arange(-az_lim, az_lim + 1e-9, daz)
    out = {}
    allv = []
    for p in pols:
        s = np.stack([po.monostatic(mesh, freq, az, e, p, occlusion=occlusion, bounces=bounces, n_sub_max=n_sub_max)
                      for e in els])
        out[p] = po.sector_metrics(s)
        allv.append(s)
    out["all"] = po.sector_metrics(np.stack(allv))
    out.update({"freq_Hz": freq, "az_lim_deg": az_lim, "daz_deg": daz, "els_deg": list(els), "pols": list(pols),
                "occlusion": occlusion, "bounces": bounces})
    return out


class Evaluator:
    def __init__(self, base, freq=FREQ_DEFAULT, daz=0.5):
        self.base, self.freq, self.daz = base, freq, daz
        self.s0 = baseline_shape(base)
        m0, i0 = G.aircraft_mesh(base, self.s0)
        self.ref = aero_eval(base, self.s0, i0)
        self.ref["LD0"] = aero_eval(base, self.s0, i0, self.ref)["LD"]
        self.n_eval = 0

    def __call__(self, shape: G.Shape, daz=None, bounces=1) -> dict:
        self.n_eval += 1
        m, info = G.aircraft_mesh(self.base, shape)
        ae = aero_eval(self.base, shape, info, self.ref)
        rc = rcs_eval(m, self.freq, daz=daz or self.daz, bounces=bounces)
        return {"shape": shape.to_dict(), "aero": ae, "rcs": rc, "n_facets": m.n_facets,
                "ok": 0.15 <= info["planform"]["taper"] <= 1.2}


BOUNDS = {"sweep_le_deg": (0.0, 50.0), "align": (0.0, 1.0), "chine_deg": (20.0, 70.0), "tail_cant_deg": (20.0, 70.0)}


def build_problem(ev: Evaluator, n_samples=80, seed=0):
    """OpenMDAO problem: IndepVarComp-style design vars → one ExplicitComponent (aero + PO RCS)."""
    import openmdao.api as om

    class AeroRCS(om.ExplicitComponent):
        def setup(self):
            for k, (lo, hi) in BOUNDS.items():
                self.add_input(k, val=getattr(ev.s0, k) if lo <= getattr(ev.s0, k) <= hi else lo)
            self.add_output("perf")
            self.add_output("rcs_dbsm")
            self.add_output("taper")
            self.cache = []

        def compute(self, i, o):
            sh = G.Shape(*(float(i[k][0]) for k in BOUNDS))
            r = ev(sh)
            o["perf"], o["rcs_dbsm"], o["taper"] = r["aero"]["perf_ratio"], r["rcs"]["all"]["mean_dbsm"], r["aero"]["taper"]
            self.cache.append(r)

    p = om.Problem(reports=False)
    comp = p.model.add_subsystem("ar", AeroRCS(), promotes=["*"])
    for k, (lo, hi) in BOUNDS.items():
        p.model.add_design_var(k, lower=lo, upper=hi)
    p.model.add_objective("rcs_dbsm")
    p.model.add_constraint("taper", lower=0.15, upper=1.2)
    # Latin hypercube from SciPy (qmc, optimised for low discrepancy) fed to OpenMDAO's DOEDriver (ListGenerator);
    # avoids the optional pyDOE dependency of om.LatinHypercubeGenerator
    from scipy.stats import qmc
    u = qmc.LatinHypercube(d=len(BOUNDS), seed=seed, optimization="random-cd").random(n_samples)
    lo = np.array([b[0] for b in BOUNDS.values()])
    hi = np.array([b[1] for b in BOUNDS.values()])
    X = lo + u * (hi - lo)
    cases = [[(k, float(x[j])) for j, k in enumerate(BOUNDS)] for x in X]
    p.driver = om.DOEDriver(om.ListGenerator(cases))
    p.setup()
    return p, comp


def pareto_mask(LD, R):
    """Non-dominated set: maximise LD, minimise R."""
    LD, R = np.asarray(LD), np.asarray(R)
    keep = np.ones(len(LD), bool)
    for i in range(len(LD)):
        dom = (LD >= LD[i]) & (R <= R[i]) & ((LD > LD[i]) | (R < R[i]))
        keep[i] = not dom.any()
    return keep


def refine_eps(ev: Evaluator, start: G.Shape, eps_dbsm: float, maxiter=60):
    """ε-constraint: maximise L/D subject to frontal RCS ≤ ε (COBYLA, derivative-free — PO RCS is non-smooth)."""
    from scipy.optimize import minimize
    keys = list(BOUNDS)
    lo = np.array([BOUNDS[k][0] for k in keys])
    hi = np.array([BOUNDS[k][1] for k in keys])
    x0 = (np.array([getattr(start, k) for k in keys]) - lo) / (hi - lo)
    memo = {}

    def run(x):
        key = tuple(np.round(x, 6))
        if key not in memo:
            xx = lo + np.clip(x, 0, 1) * (hi - lo)
            memo[key] = ev(G.Shape(*map(float, xx)))
        return memo[key]
    cons = [{"type": "ineq", "fun": lambda x: eps_dbsm - run(x)["rcs"]["all"]["mean_dbsm"]},
            {"type": "ineq", "fun": lambda x: run(x)["aero"]["taper"] - 0.15},
            {"type": "ineq", "fun": lambda x: 1.2 - run(x)["aero"]["taper"]}]
    cons += [{"type": "ineq", "fun": (lambda x, i=i: x[i])} for i in range(len(keys))]
    cons += [{"type": "ineq", "fun": (lambda x, i=i: 1 - x[i])} for i in range(len(keys))]
    res = minimize(lambda x: -run(x)["aero"]["perf_ratio"], x0, method="COBYLA", constraints=cons,
                   options={"maxiter": maxiter, "rhobeg": 0.15})
    best = run(res.x)
    return best, int(res.nfev)


# ------------------------------------------------------------------------------------------------ plots
def plot_polar(curves, path, title, freq):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(7.5, 7))
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    for lab, az, s in curves:
        ax.plot(np.radians(az), po.dbsm(s), lw=0.8, label=lab)
    top = max(float(np.max(po.dbsm(s))) for _, _, s in curves)
    ax.set_rlim(top - 70, top + 3)
    ax.set_rlabel_position(135)
    ax.set_title(f"{title}\nPO monostatic RCS [dBsm], {freq / 1e9:.1f} GHz (nose = 0°) — LOW FIDELITY", fontsize=9)
    ax.legend(loc="lower left", fontsize=7, bbox_to_anchor=(-0.1, -0.12))
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def plot_pareto(rows, front, refined, base_pt, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    LD = np.array([r["aero"]["perf_ratio"] for r in rows])
    R = np.array([r["rcs"]["all"]["mean_dbsm"] for r in rows])
    sw = np.array([r["shape"]["sweep_le_deg"] for r in rows])
    fig, ax = plt.subplots(figsize=(7.5, 5))
    sc = ax.scatter(R, LD, c=sw, cmap="viridis", s=18, label="DOE (LHS)")
    ax.plot([r["rcs"]["all"]["mean_dbsm"] for r in front], [r["aero"]["perf_ratio"] for r in front], "r-o", ms=4,
            lw=1.2, label="non-dominated (Pareto: DOE + ε + baseline)")
    if refined:
        ax.plot([r["rcs"]["all"]["mean_dbsm"] for r in refined], [r["aero"]["perf_ratio"] for r in refined], "k^", ms=7,
                label="ε-constraint (COBYLA)")
    ax.plot(base_pt[1], base_pt[0], "ks", ms=8, mfc="none", label="baseline (faceted)")
    plt.colorbar(sc, label="Λ_LE [deg]")
    ax.set_xlabel("frontal-sector mean RCS (|az|≤30°, el −5/0/5°, VV) [dBsm]")
    ax.set_ylabel("endurance / range ratio at fixed V and energy, (L/D)/W ÷ baseline")
    ax.set_title(title + " — PO low fidelity", fontsize=9)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def full_polar(mesh, freq, el=0.0, daz=0.25, pols=("VV", "HH"), occlusion=True, bounces=1):
    az = np.arange(-180, 180 + 1e-9, daz)
    return az, {p: po.monostatic(mesh, freq, az, el, p, occlusion=occlusion, bounces=bounces) for p in pols}


def render_mesh(mesh, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig = plt.figure(figsize=(7, 5))
    ax = fig.add_subplot(111, projection="3d")
    light = np.array([-0.4, -0.5, 0.75])
    sh = 0.35 + 0.65 * np.clip(mesh.n @ (light / np.linalg.norm(light)), 0, 1)
    pc = Poly3DCollection(mesh.P, facecolors=plt.cm.Greys(0.25 + 0.6 * sh), edgecolors="k", linewidths=0.2)
    ax.add_collection3d(pc)
    lo, hi = mesh.V.min(0), mesh.V.max(0)
    c, r = (lo + hi) / 2, (hi - lo).max() / 2
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r / 2, c[2] + r / 2)
    ax.view_init(28, -130)
    ax.set_title(title, fontsize=9)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ------------------------------------------------------------------------------------------------ driver
def run_study(result_json, out_dir, freq=FREQ_DEFAULT, n_samples=80, refine=(), seed=0, log=print) -> dict:
    t0 = time.time()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = baseline_from_result(result_json)
    ev = Evaluator(base, freq)
    b0 = ev(ev.s0)
    log(f"baseline: perf 1.000, L/D {b0['aero']['LD']:.2f}, frontal RCS {b0['rcs']['all']['mean_dbsm']:.2f} dBsm")
    p, comp = build_problem(ev, n_samples, seed)
    p.run_driver()
    rows = [r for r in comp.cache if r["ok"]]
    p.cleanup()
    LD = [r["aero"]["perf_ratio"] for r in rows]
    R = [r["rcs"]["all"]["mean_dbsm"] for r in rows]
    mask = pareto_mask(LD, R)
    front = sorted([r for r, m in zip(rows, mask) if m], key=lambda r: r["rcs"]["all"]["mean_dbsm"])
    log(f"DOE {len(rows)} feasible samples, {len(front)} non-dominated")
    refined = []
    for eps in refine:
        ok = [r for r in front if r["rcs"]["all"]["mean_dbsm"] <= eps]          # feasible start if one exists
        st = max(ok, key=lambda r: r["aero"]["perf_ratio"]) if ok else \
            min(front, key=lambda r: abs(r["rcs"]["all"]["mean_dbsm"] - eps))
        best, nfev = refine_eps(ev, G.Shape(**st["shape"]), eps)
        if best["rcs"]["all"]["mean_dbsm"] > eps + 0.05 and ok:                  # COBYLA ended infeasible
            best = st
        best = dict(best, eps_dbsm=eps, nfev=nfev)
        refined.append(best)
        log(f"ε = {eps:.1f} dBsm: perf {best['aero']['perf_ratio']:.3f}, L/D {best['aero']['LD']:.2f}, RCS {best['rcs']['all']['mean_dbsm']:.2f} ({nfev} ev)")
    # combined non-dominated set (DOE + ε-refined + baseline); picks: best perf, lowest RCS, knee
    # (largest normalised distance from the chord joining the two extremes — Das 1999 / Branke et al. 2004)
    pool = rows + [r for r in refined if r["rcs"]["all"]["mean_dbsm"] <= r["eps_dbsm"] + 0.05] + [b0]
    pm = pareto_mask([r["aero"]["perf_ratio"] for r in pool], [r["rcs"]["all"]["mean_dbsm"] for r in pool])
    allf = sorted([r for r, m in zip(pool, pm) if m], key=lambda r: r["rcs"]["all"]["mean_dbsm"])
    a = max(allf, key=lambda r: r["aero"]["perf_ratio"])
    z = min(allf, key=lambda r: r["rcs"]["all"]["mean_dbsm"])

    def knee_d(r):
        x1, y1 = a["rcs"]["all"]["mean_dbsm"], a["aero"]["perf_ratio"]
        x2, y2 = z["rcs"]["all"]["mean_dbsm"], z["aero"]["perf_ratio"]
        sx, sy = max(abs(x2 - x1), 1e-9), max(abs(y2 - y1), 1e-9)
        x, y = (r["rcs"]["all"]["mean_dbsm"] - x1) / sx, (r["aero"]["perf_ratio"] - y1) / sy
        ex, ey = (x2 - x1) / sx, (y2 - y1) / sy
        return -abs(ex * y - ey * x) / math.hypot(ex, ey)
    knee = min(allf, key=knee_d)
    picks = {"best_LD": a, "min_RCS": z, "knee": knee}
    files = {}
    plot_pareto(rows, allf, refined, (b0["aero"]["perf_ratio"], b0["rcs"]["all"]["mean_dbsm"]), out / "rcs_pareto.png",
                f"{base['name']}: aero/RCS trade, {freq / 1e9:.0f} GHz")
    files["pareto"] = str((out / "rcs_pareto.png").resolve())
    curves = []
    for lab, r in [("baseline", b0)] + list(picks.items()):
        sh = G.Shape(**r["shape"])
        m, _ = G.aircraft_mesh(base, sh)
        az, s = full_polar(m, freq)
        if lab == "baseline" or r is not b0:
            curves.append((f"{lab} VV (Λ {sh.sweep_le_deg:.0f}°, a {sh.align:.2f}, φ {sh.chine_deg:.0f}°, "
                           f"Γ {sh.tail_cant_deg:.0f}°)", az, s["VV"]))
        else:
            curves[0] = (curves[0][0].replace("baseline", "baseline = " + lab), *curves[0][1:])
        if lab in ("baseline", "min_RCS"):
            render_mesh(m, out / f"rcs_mesh_{lab}.png", f"{base['name']} faceted PO mesh — {lab}")
            files[f"mesh_{lab}"] = str((out / f"rcs_mesh_{lab}.png").resolve())
        # 2-bounce check of the frontal metric on the picks (coarser az)
        # coarse SBR check (el 0°, 2° steps, ≤ 12² rays per facet — ray tubes larger than λ/6: indicative only)
        r["rcs_2bounce"] = {p: rcs_eval(m, freq, daz=2.0, els=(0.0,), bounces=2, pols=(p,))["all"]
                            for p in ("VV", "HH")}
        r["rcs_1bounce_el0"] = rcs_eval(m, freq, daz=2.0, els=(0.0,), bounces=1)["all"]
    plot_polar(curves, out / "rcs_polar.png", f"{base['name']} — baseline and Pareto picks", freq)
    files["polar"] = str((out / "rcs_polar.png").resolve())
    res = {"base": base, "freq_Hz": freq, "baseline": b0, "n_doe": n_samples, "n_feasible": len(rows),
           "pareto_doe": front, "pareto": allf, "refined": refined, "picks": picks, "files": files, "wall_s": time.time() - t0,
           "n_evaluations": ev.n_eval, "limitations": po.LIMITATIONS, "assumptions": G.DEFAULTS}
    (out / "rcs_study.json").write_text(json.dumps(res, indent=1, default=float))
    return res


def stl_polar(stl_path, out_png, freq=FREQ_DEFAULT, el=0.0, daz=0.5, title=None, nose=(-1, 0, 0), occlusion=False):
    """RCS polar of a triangulated STL (e.g. the OpenVSP CompGeom export). Facet normals must be outward."""
    m = po.read_stl(stl_path)
    az, s = full_polar(m, freq, el, daz, occlusion=occlusion)
    plot_polar([(p, az, v) for p, v in s.items()], out_png, title or Path(stl_path).stem, freq)
    fr = np.abs(az) <= 30
    return {"n_facets": m.n_facets, "frontal": {p: po.sector_metrics(v[fr]) for p, v in s.items()},
            "all_aspects": {p: po.sector_metrics(v) for p, v in s.items()}, "png": str(Path(out_png).resolve())}


# ------------------------------------------------------------------------------------------------ assembly path
# When an assembly JSON is supplied, RCS (and aero, when flight is present) read that geometry — including
# Body.chine hexagonal edges and box/sphere/cylinder items — instead of the parallel parametric faceted
# aircraft of :func:`geometry.aircraft_mesh`. Shape DOE variables that cannot be mapped onto the assembly are
# listed as unassessed (never silently dropped; unknown ≠ zero / unassessed ≠ pass).

ASSEMBLY_SHAPE_VARS = {
    "chine_deg": "maps to Body.chine.angle_deg on already-chined fuselage-role bodies",
    "sweep_le_deg": "no faithful map onto arbitrary Surface LE without rewriting planform — unassessed",
    "align": "taper/TE alignment is a parametric-aircraft construct — unassessed on assembly",
    "tail_cant_deg": "V-tail cant would require mutating Surface.dihedral; not auto-applied — unassessed",
}


def _items_from_spec(spec) -> list:
    from ..assembly.integration import Item
    return [Item.from_dict(d) for d in (spec.get("items") or [])]


def eval_assembly(spec: dict, *, freq=FREQ_DEFAULT, daz=2.0, fine: int = 1,
                  chine_deg: float | None = None) -> dict:
    """Single aero/RCS evaluation that reads the assembly (opt-in path).

    * RCS: :func:`~acdt.domains.aircraft.assembly.rcs_bridge.build_rcs_mesh` + :func:`rcs_eval`
    * Aero: :func:`~acdt.domains.aircraft.assembly.sizing.analyse` CD0/L/D when ``flight`` is in the spec;
      otherwise ``aero.status = unassessed``
    * Optional ``chine_deg`` mutates already-chined fuselage bodies for the DOE
    """
    from ..assembly import Assembly
    from ..assembly.rcs_bridge import apply_chine_deg, build_rcs_mesh

    asm = Assembly.from_dict(spec["assembly"])
    items = _items_from_spec(spec)
    mapped, unmapped = [], []
    if chine_deg is not None:
        touched = apply_chine_deg(asm, chine_deg, roles=("fuselage",), only_already_chined=True)
        if touched:
            mapped.append({"var": "chine_deg", "value": float(chine_deg), "bodies": touched,
                           "how": ASSEMBLY_SHAPE_VARS["chine_deg"]})
        else:
            unmapped.append({"var": "chine_deg", "value": float(chine_deg),
                             "reason": "no already-chined fuselage body to receive chine_deg "
                                       "(opt-in Body.chine required; unknown ≠ invent)"})
    for var, how in ASSEMBLY_SHAPE_VARS.items():
        if var == "chine_deg":
            continue
        unmapped.append({"var": var, "reason": how})

    mesh, inv = build_rcs_mesh(asm, items=items, fine=fine)
    rc = rcs_eval(mesh, freq, daz=daz, bounces=1, occlusion=True)

    aero: dict = {"status": "unassessed",
                  "reason": "no flight block — assembly aero not evaluated (unassessed ≠ pass)"}
    if spec.get("flight"):
        from ..assembly.sizing import analyse
        sz = analyse(spec, spec["flight"])
        drag = sz.drag
        aero = {
            "status": "assessed",
            "CD0_nominal": drag.get("CD0_nominal", drag.get("CD0")),
            "CD0": drag.get("CD0"),
            "CD0_pessimistic": drag.get("CD0_pessimistic"),
            "S_m2": drag.get("Sref") or drag.get("S_ref") or drag.get("S"),
            "notes": list(sz.notes) if getattr(sz, "notes", None) else [],
            "method": "assembly.sizing.analyse (Raymer wet-area CD0; K/L/D only when provided)",
        }
        K = drag.get("K")
        if K is None and hasattr(sz, "summary"):
            K = sz.summary().get("K")
        if K is not None and aero.get("S_m2") and aero.get("CD0"):
            from ....core.atmosphere import isa as _isa
            fl = spec["flight"]
            V, h = float(fl["V_m_s"]), float(fl.get("altitude_m", 0.0))
            W = float(fl["W0_kg"]) * 9.80665
            S = float(aero["S_m2"])
            st = _isa(h)
            q = 0.5 * st.rho * V * V
            CL = W / (q * S)
            CD = float(aero["CD0"]) + float(K) * CL * CL
            aero.update({"CL": CL, "CD": CD, "LD": CL / CD, "K": float(K), "V_m_s": V, "h_m": h})
        else:
            aero["ld_note"] = "K not in assembly drag result — L/D left unassessed (not zero)"

    return {
        "source": "assembly",
        "shape": {"chine_deg": chine_deg},
        "mapped_shape_vars": mapped,
        "unassessed_shape_vars": unmapped,
        "inventory": inv,
        "aero": aero,
        "rcs": rc,
        "n_facets": int(mesh.n_facets),
        "ok": True,
        "limits": [
            "PO RCS only (Gordon facet integral) — no full-wave, no edge diffraction, no RAM",
            "assembly path does not rebuild the parallel parametric faceted aircraft",
            "unmapped Shape DOE vars are unassessed, never silently zeroed",
            po.LIMITATIONS,
        ],
    }


def run_assembly_study(spec_path, out_dir, freq=FREQ_DEFAULT, n_samples=12, seed=0,
                       chine_bounds=(20.0, 70.0), daz=2.0, log=print) -> dict:
    """LHS over ``chine_deg`` on an assembly that already has a chined fuselage; aero/RCS from the assembly.

    Opt-in and backward compatible: the parametric :func:`run_study` path is unchanged. Writes
    ``assembly_rcs_study.json`` (+ markdown summary) under ``out_dir``.
    """
    t0 = time.time()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = Path(spec_path)
    spec = json.loads(path.read_text(encoding="utf-8"))
    if "assembly" not in spec:
        raise ValueError(f"{path}: expected JSON with top-level 'assembly'")

    # baseline at the body's declared chine (or mid-bound if absent → will be unassessed)
    from ..assembly import Assembly
    from ..assembly.components import Body
    asm0 = Assembly.from_dict(spec["assembly"])
    declared = [c.chine["angle_deg"] for c in asm0.components
                if isinstance(c, Body) and c.chine]
    ch0 = float(declared[0]) if declared else float(sum(chine_bounds) / 2)

    from scipy.stats.qmc import LatinHypercube
    u = LatinHypercube(d=1, seed=seed).random(n_samples)
    lo, hi = chine_bounds
    samples = [ch0] + [float(lo + ui[0] * (hi - lo)) for ui in u]

    rows = []
    for i, ch in enumerate(samples):
        r = eval_assembly(spec, freq=freq, daz=daz, chine_deg=ch)
        rows.append({
            "id": "baseline" if i == 0 else f"s{i}",
            "chine_deg": ch,
            "rcs_mean_dbsm": r["rcs"]["all"]["mean_dbsm"],
            "rcs_median_dbsm": r["rcs"]["all"]["median_dbsm"],
            "n_facets": r["n_facets"],
            "aero": r["aero"],
            "mapped_shape_vars": r["mapped_shape_vars"],
            "unassessed_shape_vars": r["unassessed_shape_vars"],
            "inventory": r["inventory"] if i == 0 else None,
        })
        log(f"  assembly sample {i}/{len(samples)-1}: φ={ch:.1f}°  RCS mean {rows[-1]['rcs_mean_dbsm']:.2f} dBsm")

    # Pareto on RCS only when aero is unassessed; else (LD max, RCS min) if LD present
    has_ld = all(isinstance(r["aero"], dict) and r["aero"].get("LD") is not None for r in rows)
    if has_ld:
        mask = pareto_mask([r["aero"]["LD"] for r in rows], [r["rcs_mean_dbsm"] for r in rows])
    else:
        # minimise RCS; every point with the unique minimum is non-dominated
        best = min(r["rcs_mean_dbsm"] for r in rows)
        mask = np.array([abs(r["rcs_mean_dbsm"] - best) < 1e-9 for r in rows])

    front = [r for r, m in zip(rows, mask) if m]
    report = {
        "schema": "acdt.assembly_rcs_study/1",
        "source": str(path),
        "freq_Hz": freq,
        "n_samples": n_samples,
        "chine_bounds_deg": list(chine_bounds),
        "rows": rows,
        "pareto_ids": [r["id"] for r in front],
        "baseline_rcs_mean_dbsm": rows[0]["rcs_mean_dbsm"],
        "inventory": rows[0]["inventory"],
        "unassessed_shape_vars": rows[0]["unassessed_shape_vars"],
        "elapsed_s": time.time() - t0,
        "limits": [
            "PO only — no full-wave RCS",
            "DOE variable on assembly path: chine_deg → Body.chine (opt-in); other Shape vars unassessed",
            "aero assessed only when spec.flight is present (sizing.analyse)",
            "propeller discs excluded (PRESSUPOSTO); unassessed ≠ pass",
        ],
    }
    (out / "assembly_rcs_study.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=float),
                                                 encoding="utf-8")
    md = ["# Assembly aero/RCS study (PO)", "",
          f"Source: `{path.name}`. Freq {freq/1e9:.1f} GHz. Baseline φ={ch0:.1f}° → "
          f"{rows[0]['rcs_mean_dbsm']:.2f} dBsm.", "",
          "## Inventory (baseline)", ""]
    inv = rows[0]["inventory"] or {}
    for lab, key in (("Included", "included"), ("Excluded (PRESSUPOSTO)", "excluded_presupposto"),
                     ("Unassessed", "unassessed")):
        md.append(f"### {lab}")
        for e in inv.get(key, []):
            md.append(f"* {e}")
        md.append("")
    md += ["## Samples", "", "| id | chine_deg | RCS mean dBsm | aero |", "|---|---|---|---|"]
    for r in rows:
        ae = r["aero"]
        aestr = (f"L/D {ae['LD']:.2f}" if isinstance(ae, dict) and ae.get("LD") is not None
                 else ae.get("status", "?"))
        md.append(f"| {r['id']} | {r['chine_deg']:.1f} | {r['rcs_mean_dbsm']:.2f} | {aestr} |")
    md += ["", "## Limits", ""] + [f"* {x}" for x in report["limits"]]
    (out / "assembly_rcs_study.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    report["files"] = {"json": str(out / "assembly_rcs_study.json"), "md": str(out / "assembly_rcs_study.md")}
    log(f"[acdt] assembly RCS study: {len(rows)} samples, Pareto {report['pareto_ids']} in {report['elapsed_s']:.1f}s")
    return report
