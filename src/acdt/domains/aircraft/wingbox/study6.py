"""Phase 6 study driver (``acdt wingbox6``): discrete screening (stringer count) → shell-FEM calibration at the
baseline → optimisation → recalibration at the optimum → re-optimisation (warm start) → FEM check of baseline and
optimum, spar-type / n_str neighbourhood at the optimum, plots and JSON; comparison with the Phase 5 result."""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

from . import shell6
from . import sizing6 as Z
from .optimize6 import VARS6, WingBoxProblem6
from .render import render_wing_structure
from .study import _summ


def _material_kind(res):
    from ..weights_detailed import _merge_opts
    A = res.spec.assumptions
    mat = A["structures"]["material"]
    if isinstance(mat, dict):          # external metal (structures form) → used as given
        return mat
    if mat == "auto":
        mat = "cfrp" if _merge_opts(A["weights"].get("components"))["material"] == "composite" else "al2024_t3"
    return "composite" if "cfrp" in mat else "metal"


def _calibrate(P, ev, log, name, tag):
    sec_raw = Z.section6(ev.wing, ev.box, P.mat6, camber=(ev.x["camber"], P.p), y0=P.y0, raw=True)
    cal, diag, _ = shell6.calibrate(ev.wing, ev.box, P.mat6, ev.x, P.y0, (ev.x["camber"], P.p), sec_raw, ev.beam)
    log(f"[{name}] calibração FEM ({tag}): {diag['nodes']} nós, {diag['t_s']:.1f} s; k_EI "
        f"{np.round(cal.k_EI, 3).tolist()}, k_GJ {np.round(cal.k_GJ, 3).tolist()}, Δx_sc/c "
        f"{np.round(cal.dx_sc, 3).tolist()}, k_σ {np.round(cal.k_sigma, 3).tolist()}")
    return cal, diag


def _check(P, ev):
    pr, pt = P._polars(ev.x)
    cm0 = P._span(P.y, pr["cm0"], pt["cm0"])
    qD = 0.5 * 1.225 * P.vn.VD**2
    return shell6.fem_check6(ev.wing, ev.box, P.mat6, ev.x, P.y0, (ev.x["camber"], P.p), ev.manoeuvre["lift"], cm0,
                             qD, ev.beam, ev.section)


def _summ6(ev, P):
    s = _summ(ev, P)
    d = ev.box.details
    s["phase6"] = {"n_str": int(d["n_str"]), "spar_type": d["spar_type"], "phi_cap": float(d["phi_cap"]),
                   "n_ribs_semispan": d["n_ribs_semispan"], "rib_pitch_actual": d["rib_pitch_actual"],
                   "ribs": d["ribs"], "skin_root_mm": float(d["skin_upper"][0] * 1e3),
                   "tbar_root_mm": float(d["cover_tbar_upper"][0] * 1e3),
                   "cap_root_mm2": float(d["cap_each"][0] * 1e6), "sigma_cover_root_MPa": float(d["sigma_cover"][0] / 1e6),
                   "core_root_mm": float(np.max(d["core_t"]) * 1e3),
                   "buckling_reserve": d.get("buckling_reserve")}
    if "h_str" in d:
        s["phase6"]["stringer_root_h_mm"] = float(d["h_str"][0] * 1e3)
        s["phase6"]["stringer_root_A_mm2"] = float(d["A_str"][0] * 1e6)
    return s


def run_study6(res, out_dir, objective: str, name: str, material: str | None = None, maxiter: int = 30,
               fem: bool = True, n_str_list=(6, 10, 14, 18), phase5_json: str | None = None,
               rib_simp_mass: dict | None = None, hold_section: bool | None = None, log=print) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    kind = material or _material_kind(res)
    metal = kind == "metal" or isinstance(kind, dict)       # dict: external isotropic metal
    label = kind if isinstance(kind, str) else f"metal {kind.get('name', 'externo')}"
    # 1) discrete screening at the (uncalibrated) baseline
    scr = []
    if metal:
        for n in n_str_list:
            Pn = WingBoxProblem6(res, objective, material=kind, n_str=n, hold_section=hold_section)
            scr.append({"n_str": n, "box_mass_kg": Pn.base.mass_box})
            log(f"[{name}] rastreio n_str {n:2d}: caixão base {Pn.base.mass_box:.2f} kg")
        n_best = min(scr, key=lambda r: r["box_mass_kg"])["n_str"]
    else:
        n_best = 0
    P = WingBoxProblem6(res, objective, material=kind, n_str=n_best, hold_section=hold_section)
    b0 = P.base
    log(f"[{name}] base Fase 6 ({label}, n_str {n_best}, sem calibração): caixão {b0.mass_box:.2f} kg, "
        f"L/D {b0.cruise['L_D']:.2f}"
        + (f"; secção fixa (t/c {P.x0['tc_root']:.3f}/{P.x0['tc_tip']:.3f}, m {P.x0['camber']:.3f}, "
           f"torção {P.x0['twist_tip']:.2f}°)" if P.hold_section else ""))
    # 2) calibrate at the baseline → optimise
    cal1, d1 = _calibrate(P, b0, log, name, "base")
    P.set_calibration(cal1)
    b = P.base
    free = P.free_vars()
    r1 = P.optimise(free=free, maxiter=maxiter)
    e1 = r1["eval"]
    log(f"[{name}] ótimo 1: {r1['message']} ({r1['nit']} it), caixão {e1.mass_box:.2f} kg, L/D "
        f"{e1.cruise['L_D']:.2f}, obj {e1.objective:.4g}, viável {r1['feasible']} ({time.time() - t0:.0f} s)")
    # 3) recalibrate at the optimum → re-optimise from it
    cal2, d2 = _calibrate(P, e1, log, name, "ótimo 1")
    x1 = dict(e1.x)
    P.set_calibration(cal2)
    b2 = P.base
    r2 = P.optimise(free=free, maxiter=max(8, maxiter // 2), start=x1)          # warm start: half budget
    e2 = r2["eval"]
    log(f"[{name}] ótimo 2 (recalibrado): {r2['message']} ({r2['nit']} it), caixão {e2.mass_box:.2f} kg, L/D "
        f"{e2.cruise['L_D']:.2f}, obj {e2.objective:.4g}, viável {r2['feasible']} ({time.time() - t0:.0f} s)")
    # 4) neighbourhood of the discrete choices at the optimum (box mass only, same continuous x)
    neigh = []
    n_set = (sorted({max(n_best - 4, 0), max(n_best - 2, 0), n_best, n_best + 2, n_best + 4})
             if metal else [0])
    combos = [(st, n_best) for st in Z.SPAR_TYPES] + [(P.spar_type, n) for n in n_set if n != n_best]
    for st, n in combos:
        Pq = WingBoxProblem6.__new__(WingBoxProblem6)
        Pq.__dict__.update(P.__dict__)
        Pq.n_str, Pq.spar_type, Pq._cache = n, st, {}
        ev = Pq.evaluate(e2.x)
        neigh.append({"spar_type": st, "n_str": n, "box_mass_kg": ev.mass_box,
                      "feasible": all(v >= -1e-3 for v in ev.constraints.values())})
    log(f"[{name}] vizinhança discreta: {len(neigh)} avaliações ({time.time() - t0:.0f} s)")
    # 4b) optional rib topology demo (SIMP) at the root rib of the optimum — layout suggestion only
    rib_png = None
    try:
        from .rib_simp import rib_simp, plot_rib
        rb = e2.box.details["ribs"]
        k0 = 0
        rs = rib_simp(rb["w_m"][k0], rb["h_m"][k0], rb["p_crush_N_m"][k0], rb["dV_N"][k0])
        rib_png = out / f"{name}_rib_simp.png"
        plot_rib(rs, rib_png, f"{name}: nervura da raiz, SIMP (demo; volume {rs['vol']:.2f}, {rs['iters']} it)")
        log(f"[{name}] SIMP nervura da raiz: {rs['nelx']}×{rs['nely']} elementos, {rs['iters']} it ({time.time() - t0:.0f} s)")
    except Exception as exc:                                  # demo must never break the study
        log(f"[{name}] SIMP nervura: não executado ({exc})")
    # 4c) opt-in: feed SIMP web mass into the structural budget (does not re-run SLSQP)
    cfg = rib_simp_mass
    if cfg is None:
        cfg = (res.spec.assumptions.get("structures") or {}).get("rib_simp_mass")
    if cfg is False or cfg is None:
        cfg = None
    if isinstance(cfg, dict) and cfg.get("enabled", True) is False:
        cfg = None
    simp_mass_report = None
    if cfg:
        from .rib_simp_mass import apply_to_box
        mat = P.mat6
        payload = dict(cfg)
        payload.setdefault("rho_kg_m3", mat.get("rho"))
        payload.setdefault("rho_source", mat.get("note") or mat.get("source") or mat.get("name"))
        payload.setdefault("nu", mat.get("nu", 0.33))
        simp_mass_report = apply_to_box(e2.box, payload, material=mat)
        if simp_mass_report.get("status") == "ok":
            e2.mass_box = e2.box.masses["total"]
            log(f"[{name}] SIMP no orçamento: nervuras {simp_mass_report['ribs_sized_kg']:.3f} → "
                f"{simp_mass_report['ribs_simp_kg']:.3f} kg (Δ {simp_mass_report['delta_kg']:+.3f} kg); "
                f"caixão {e2.mass_box:.3f} kg")
        else:
            log(f"[{name}] SIMP no orçamento unassessed: "
                f"{', '.join(simp_mass_report.get('unassessed_terms') or [])} — massas size_ribs retidas")
    # 5) FEM checks
    checks = {}
    if fem:
        for tag, ev in (("baseline", b2), ("optimum", e2)):
            checks[tag] = _check(P, ev)
            c = checks[tag]
            log(f"[{name}] FEM ({tag}): ponta w FEM {c['tip_w_fem_m']:.4f} vs viga {c['tip_w_beam_m']:.4f} m; "
                f"torção FEM {c['tip_twist_fem_deg']:.3f}° vs viga {c['tip_twist_beam_deg']:.3f}° (só torção {c['tip_twist_beam_pure_torsion_deg']:.3f}°)")
    p5 = None
    if phase5_json and Path(phase5_json).exists():
        p5 = json.loads(Path(phase5_json).read_text(encoding="utf-8"))
    summary = {"name": name, "objective": objective, "material": kind, "variables": list(VARS6),
               "bounds": {k: list(v) for k, v in P.bounds.items()},
               "hold_section": bool(P.hold_section), "twist": getattr(P, "twist_info", None),
               "screening_n_str": scr, "n_str": n_best,
               "baseline_uncalibrated": _summ6(b0, P), "baseline": _summ6(b2, P),
               "optimum_1": {**_summ6(e1, P), "message": str(r1["message"]), "nit": r1["nit"], "feasible": r1["feasible"]},
               "optimum": {**_summ6(e2, P), "success": r2["success"], "message": str(r2["message"]), "nit": r2["nit"],
                           "nfev": r2["nfev"], "feasible": r2["feasible"]},
               "calibration_baseline": {**cal1.to_dict(), "bays": d1["bays"], "nodes": d1["nodes"]},
               "calibration_optimum": {**cal2.to_dict(), "bays": d2["bays"], "nodes": d2["nodes"]},
               "discrete_neighbourhood": neigh,
               "fem_check": {k: {kk: vv for kk, vv in v.items() if not isinstance(vv, list)} for k, v in checks.items()},
               "phase3_box_mass_kg": float(res.structures.box.masses["total"])}
    if p5:
        summary["phase5"] = {"baseline_box_kg": p5["baseline"]["box_mass_kg"], "optimum_box_kg": p5["optimum"]["box_mass_kg"],
                             "baseline_L_D": p5["baseline"]["cruise"]["L_D"], "optimum_L_D": p5["optimum"]["cruise"]["L_D"],
                             "optimum_perf": p5["optimum"]["perf"], "optimum_x": p5["optimum"]["x"]}
    paths = {"calibration": str(out / f"{name}_calibration.png"), "fem_check": str(out / f"{name}_fem_check.png"),
             "layout": str(out / f"{name}_layout6.png"), "render_optimum": str(out / f"{name}_structure3d_fase6.png")}
    plot_calibration(summary, paths["calibration"])
    if checks:
        plot_fem(checks, paths["fem_check"], name)
    plot_layout6(b2, e2, paths["layout"], name, p5)
    render_wing_structure(e2.wing, e2.x, e2.box, paths["render_optimum"], f"{name} — ótimo Fase 6 ({objective})",
                          P.p, e2.section["x_sc_c"])
    if rib_png is not None:
        paths["rib_simp"] = str(rib_png)
    if simp_mass_report is not None:
        # drop bulky per-rib compliance histories from the JSON summary
        slim = {k: v for k, v in simp_mass_report.items() if k != "per_rib"}
        slim["per_rib"] = [{kk: rr[kk] for kk in rr if kk != "compliance"}
                             for rr in simp_mass_report.get("per_rib") or []]
        summary["rib_simp_mass"] = slim
    summary["paths"] = paths
    summary["wall_s"] = time.time() - t0
    (out / f"{name}_wingbox6.json").write_text(json.dumps(summary, indent=1, default=float))
    return summary


def plot_calibration(s, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 4, figsize=(16, 3.8))
    for key, st in (("calibration_baseline", "o--"), ("calibration_optimum", "s-")):
        c = s[key]
        lab = "base" if "baseline" in key else "ótimo"
        for a, k, t in zip(ax, ("k_EI", "k_GJ", "dx_sc_c", "k_sigma"),
                           ("k_EI = EI_FEM / EI_secção", "k_GJ = GJ_FEM / GJ_secção", "Δx_sc/c (FEM − secção)",
                            "k_σ = F_cobertura,FEM / (M/h)")):
            a.plot(c["eta"], c[k], st, label=lab)
            a.set_title(t, fontsize=9)
            a.set_xlabel("η = (y − y0)/(b/2 − y0)")
            a.grid(alpha=0.3)
    ax[0].legend(fontsize=8)
    fig.suptitle(f"{s['name']} — calibração da viga pelo FEM de cascas (contorno + célula D), por baía de nervuras",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_fem(checks, path, name):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    for tag, st in (("baseline", "k"), ("optimum", "r")):
        c = checks[tag]
        ax[0].plot(c["y"], c["w_fem"], st + "o", ms=3, label=f"FEM cascas ({tag})")
        ax[0].plot(c["y_beam"], c["w_beam"], st + "-", label=f"viga calibrada ({tag})")
        ax[1].plot(c["y"], c["theta_fem_deg"], st + "o", ms=3, label=f"FEM ({tag})")
        ax[1].plot(c["y_beam"], c["theta_beam_deg"], st + "-", label=f"viga ({tag})")
    ax[0].set_ylabel("deflexão w [m] (carga última)")
    ax[1].set_ylabel("torção θ [°] (nariz acima +)")
    for a in ax:
        a.set_xlabel("y [m]")
        a.grid(alpha=0.3)
        a.legend(fontsize=7)
    fig.suptitle(f"{name} — verificação FEM vs viga (sustentação em c/4 + c_m0, inércia no centro de corte)",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_layout6(b, e, path, name, p5=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 3, figsize=(15, 7.5))
    for ev, st, lab in ((b, "k--", "base"), (e, "r-", "ótimo")):
        d, bx = ev.box.details, ev.box
        ax[0, 0].plot(bx.y, d["cover_tbar_upper"] * 1e3, st, label=f"t̄ sup. ({lab})")
        ax[0, 0].plot(bx.y, d["skin_upper"] * 1e3, st, lw=0.8, alpha=0.6)
        ax[0, 1].plot(bx.y, d["cap_each"] * 1e6, st, label=f"banzo ({lab})")
        ax[0, 2].plot(bx.y, d["sigma_cover"] / 1e6, st, label=f"σ cobertura ({lab})")
        r = d["ribs"]
        ax[1, 0].step(r["y"], r["t_mm"], st, where="mid", label=f"nervura t ({lab})")
        ax[1, 1].plot(ev.y, ev.section["GJ"] / 1e3, st, label=f"GJ ({lab})")
        ax[1, 1].plot(ev.y, ev.section["EI"] / 1e4, st, lw=0.8, alpha=0.6)
        ax[1, 2].plot(ev.y, ev.cruise["cl_y"], st, label=f"cl cruzeiro ({lab})")
    labels = [("t̄ / pele [mm]", 0, 0), ("área do banzo [mm²]", 0, 1), ("σ média última [MPa]", 0, 2),
              ("espessura nervura [mm]", 1, 0), ("GJ [kN·m²] (fino EI/10)", 1, 1), ("cl local", 1, 2)]
    for t, i, j in labels:
        ax[i, j].set_ylabel(t)
        ax[i, j].set_xlabel("y [m]")
        ax[i, j].grid(alpha=0.3)
        ax[i, j].legend(fontsize=7)
    xo = e.x
    p5t = f" | Fase 5: {p5['optimum']['box_mass_kg']:.1f} kg" if p5 else ""
    fig.suptitle(f"{name} Fase 6: longarinas {xo['xf']:.3f}/{xo['xr']:.3f} c, t/c {xo['tc_root']:.3f}/{xo['tc_tip']:.3f}, "
                 f"nervuras {xo['rib_pitch']:.2f} m, φ_cap {xo.get('phi_cap', 0):.2f}, n_str {e.box.details['n_str']} — "
                 f"caixão {b.mass_box:.1f} → {e.mass_box:.1f} kg{p5t}", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_section_examples(path, h=0.15, b=0.06, tf=3e-3, tw=1.6e-3, mat=None):
    """Gallery of the parametric beam sections (:mod:`acdt.core.sections`) with centroid, shear centre, A, I, J and
    the cap allowable of the compressed half (Al 2024-T3 unless ``mat``)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from acdt.core import sections as SEC
    m = mat or Z.phase6_material("metal")
    profs = [("I", SEC.i_section(h, b, tf, tw)), ("C", SEC.channel(h, b, tf, tw)), ("Z", SEC.z_section(h, b, tf, tw)),
             ("built-up", SEC.builtup_spar(h, b, tf, tw)), ("T", SEC.t_section(h / 2, b, tf, tw)),
             ("ângulo", SEC.angle(h / 2, b, tf)), ("hat", SEC.hat(0.04, 0.025, 0.015, 1.2e-3)),
             ("tubo rect.", SEC.rect_tube(h, b, tf, tw))]
    fig, ax = plt.subplots(2, 4, figsize=(15, 8))
    for a, (name, p) in zip(ax.flat, profs):
        pr = p.properties()
        for i, j, t in p.segs:
            P1, P2 = p.pts[i] * 1e3, p.pts[j] * 1e3
            a.plot([P1[0], P2[0]], [P1[1], P2[1]], "-", color="steelblue", lw=max(1.0, t * 1e3 * 2.2),
                   solid_capstyle="butt")
        a.plot(pr["yc"] * 1e3, pr["zc"] * 1e3, "k+", ms=12, label="centróide")
        a.plot(pr["y_sc"] * 1e3, pr["z_sc"] * 1e3, "rx", ms=10, label="centro de corte")
        al = p.allowable(m["E"], m["sigma_cap"], m["nu"])
        a.set_title(f"{name}: A {pr['A'] * 1e6:.0f} mm², I_yy {pr['Iyy'] * 1e8:.1f} cm⁴\nJ {pr['J'] * 1e12:.0f} mm⁴, "
                    f"F_cc {al['F'] / 1e6:.0f} MPa", fontsize=9)
        a.set_aspect("equal")
        a.grid(alpha=0.3)
        a.set_xlabel("y [mm]")
        a.set_ylabel("z [mm]")
    ax[0, 0].legend(fontsize=7)
    fig.suptitle("Secções paramétricas (acdt.core.sections): propriedades de linha média, centro de corte (Megson) e "
                 "tensão admissível de compressão (Gerard/Needham, Al 2024-T3)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
