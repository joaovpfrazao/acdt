"""Phase 5 study driver: baseline → t/c sweep (each point optimised) → full optimum → in-house FEM check of the
optimum → plots, 3-D structure previews and JSON (``acdt wingbox``)."""
from __future__ import annotations

import copy
import json
import math
import time
from pathlib import Path

import numpy as np

from .optimize import VARS, WingBoxProblem
from .render import render_wing_structure


def _summ(ev, P) -> dict:
    return {"x": {k: float(v) for k, v in ev.x.items()}, "box_mass_kg": float(ev.mass_box),
            "masses": {k: float(v) for k, v in ev.box.masses.items()},
            "x_sc_c_root": float(ev.section["x_sc_c"][0]), "GJ_root": float(ev.section["GJ"][0]),
            "EI_root": float(ev.section["EI"][0]),
            "cruise": {k: float(v) for k, v in ev.cruise.items() if np.ndim(v) == 0},
            "manoeuvre": {k: float(v) for k, v in ev.manoeuvre.items() if np.ndim(v) == 0},
            "aeroelastic_eas": {k: float(v) for k, v in ev.aeroelastic.items() if np.ndim(v) == 0 and not isinstance(v, (str, type(None)))},
            "reversal_surface": ev.aeroelastic.get("reversal_surface"),
            "controls": ev.aeroelastic.get("controls") or [],
            "buckling_reserve": (ev.box.details or {}).get("buckling_reserve"),
            "perf": {k: float(v) for k, v in ev.perf.items()}, "fuel_volume_m3": float(ev.fuel_volume_m3),
            "constraints": {k: float(v) for k, v in ev.constraints.items()}, "objective": float(ev.objective)}


def fem_check(res, ev, ds: float | None = None, modal: bool = False) -> dict:
    """In-house shell FEM (:mod:`wingbox.fem`) of the design ``ev`` at ultimate load vs beam theory with the
    Megson section EI/GJ (clamped at the fuselage side)."""
    from .. import structures as S
    from . import fem as wf
    r2 = copy.copy(res)
    r2.config = copy.copy(res.config)
    r2.config.wing = ev.wing
    box = copy.deepcopy(ev.box)
    r2.structures = S.StructuresResult(res.structures.vn, ev.load, ev.beam, box, res.structures.wing_mass_raymer,
                                       res.structures.condition)
    t = time.time()
    out = {k: v for k, v in wf.run(r2, ds, n_buckle=0, n_modes=4 if modal else 0).items() if not k.startswith("_")}
    out["t_s"] = time.time() - t
    # beam theory with the section properties, ultimate, clamped at y0
    y0 = 0.5 * res.config.fuselage.max_diameter if res.config.fuselage else 0.0
    y = np.linspace(y0, ev.wing.span / 2, 200)
    M = 1.5 * np.interp(y, ev.beam.y, ev.beam.moment)
    T = 1.5 * np.interp(y, ev.beam.y, ev.beam.torque)
    EI = np.interp(y, box.y, box.EI)
    GJ = np.interp(y, box.y, box.GJ)
    k = M / EI
    slope = np.r_[0, np.cumsum(0.5 * (k[1:] + k[:-1]) * np.diff(y))]
    w = np.r_[0, np.cumsum(0.5 * (slope[1:] + slope[:-1]) * np.diff(y))]
    tw = np.r_[0, np.cumsum(0.5 * (T[1:] / GJ[1:] + T[:-1] / GJ[:-1]) * np.diff(y))]
    out["tip_w_beam_m"], out["tip_twist_beam_deg"] = float(w[-1]), math.degrees(tw[-1])
    return out


def run_study(res, out_dir, objective: str, name: str, tc_sweep=None, maxiter: int = 40, sweep_maxiter: int = 20,
              fem: bool = True, hold_section: bool | None = None, log=print) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    P = WingBoxProblem(res, objective, hold_section=hold_section)
    b = P.base
    log(f"[{name}] baseline: caixão {b.mass_box:.2f} kg, L/D {b.cruise['L_D']:.2f}, obj {b.objective:.4g}"
        + (f"; secção fixa (t/c {P.x0['tc_root']:.3f}/{P.x0['tc_tip']:.3f}, m {P.x0['camber']:.3f}, "
           f"torção {P.x0['twist_tip']:.2f}°)" if P.hold_section else ""))
    sweep = []
    if P.hold_section:
        log(f"[{name}] hold_section: t/c, curvatura e torção geométrica fixos na base; sem varrimento de t/c")
    else:
        # t/c sweep: root t/c fixed, tip t/c with the baseline tip/root ratio, the other variables optimised
        ratio = P.x0["tc_tip"] / P.x0["tc_root"]
        tcs = tc_sweep if tc_sweep is not None else np.round(np.arange(0.10, 0.185, 0.02), 3)
        for tc in tcs:
            fixed = {"tc_root": float(tc), "tc_tip": float(min(max(tc * ratio, P.bounds["tc_tip"][0]),
                                                                P.bounds["tc_tip"][1]))}
            r = P.optimise(fixed=fixed, maxiter=sweep_maxiter)
            e = r["eval"]
            sweep.append({"tc_root": float(tc), "feasible": r["feasible"], **_summ(e, P)})
            log(f"[{name}] t/c {tc:.3f}: caixão {e.mass_box:.2f} kg, CD {e.cruise['CD']:.5f}, L/D {e.cruise['L_D']:.2f}, "
                f"obj {e.objective:.4g}, viável {r['feasible']}")
    ropt = P.optimise(maxiter=maxiter)
    e = ropt["eval"]
    log(f"[{name}] ótimo: {ropt['message']} ({ropt['nit']} it, {ropt['nfev']} aval.), caixão {e.mass_box:.2f} kg, "
        f"L/D {e.cruise['L_D']:.2f}, obj {e.objective:.4g}, viável {ropt['feasible']}")
    summary = {"name": name, "objective": objective, "variables": list(VARS),
               "bounds": {k: list(v) for k, v in P.bounds.items()},
               "baseline": _summ(b, P), "optimum": {**_summ(e, P), "success": ropt["success"],
                                                    "message": str(ropt["message"]), "nit": ropt["nit"],
                                                    "nfev": ropt["nfev"], "feasible": ropt["feasible"]},
               "sweep": sweep, "phase3_box_mass_kg": float(res.structures.box.masses["total"]),
               "calibration": {"CD_rest": float(P.CD_rest), "k_flutter": float(P.k_fl)},
               "assumptions": {"tank_span_fraction": P.tank[0], "tank_usable": P.tank[1], "fuel_density": P.tank[2],
                               "xr_max (TE hinge − clearance)": P.xr_max,
                               "te_surfaces": getattr(P, "te_surfaces", []),
                               "hinge_notes": getattr(P, "hinge_notes", []),
                               "hold_section": bool(P.hold_section),
                               "twist": getattr(P, "twist_info", None),
                               "reversal_model": {
                                   "surfaces": ev.aeroelastic.get("controls") if (ev := e) else [],
                                   "binding": ev.aeroelastic.get("reversal_surface"),
                                   "note": "Wright & Cooper Ch. 9 / BAH Ch. 8 on the drawn TE surfaces; "
                                           "yaw of a split drag-rudder is unassessed (McCormick profile drag)"
                               }}}
    paths = {"sweep": str(out / f"{name}_tc_sweep.png"), "layout": str(out / f"{name}_layout.png"),
             "render_baseline": str(out / f"{name}_structure3d_baseline.png"),
             "render_optimum": str(out / f"{name}_structure3d_optimum.png")}
    plot_sweep(summary, paths["sweep"])
    plot_layout(P, b, e, paths["layout"], name)
    render_wing_structure(P.wing, b.x, b.box, paths["render_baseline"], f"{name} — base (Fase 3)", P.p,
                          b.section["x_sc_c"])
    render_wing_structure(e.wing, e.x, e.box, paths["render_optimum"], f"{name} — ótimo ({objective})", P.p,
                          e.section["x_sc_c"])
    if fem:
        try:
            summary["fem_baseline"] = fem_check(res, b)
            summary["fem_optimum"] = fem_check(res, e)
        except Exception as ex:  # pragma: no cover
            summary["fem_error"] = repr(ex)
    summary["paths"] = paths
    summary["wall_s"] = time.time() - t0
    (out / f"{name}_wingbox.json").write_text(json.dumps(summary, indent=1, default=float))
    return summary


def plot_sweep(s: dict, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sw = s["sweep"]
    if not sw:
        fig, ax = plt.subplots(figsize=(8, 3.2))
        x = s["baseline"]["x"]
        ax.text(0.5, 0.6, "secção fixa (hold_section): sem varrimento de t/c", ha="center", va="center",
                transform=ax.transAxes, fontsize=11)
        ax.text(0.5, 0.35, f"t/c {x['tc_root']:.3f}/{x['tc_tip']:.3f}, m {x['camber']:.3f}, "
                f"torção {x['twist_tip']:.2f}°", ha="center", va="center", transform=ax.transAxes, fontsize=9)
        ax.axis("off")
        fig.suptitle(f"{s['name']} — t/c, curvatura e torção fixos na geometria de partida", fontsize=10)
        fig.tight_layout()
        fig.savefig(path, dpi=110)
        plt.close(fig)
        return
    tc = [p["tc_root"] for p in sw]
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    ax[0].plot(tc, [p["box_mass_kg"] for p in sw], "o-", label="caixão ótimo para cada t/c")
    ax[0].plot(s["baseline"]["x"]["tc_root"], s["baseline"]["box_mass_kg"], "ks", label="base")
    ax[0].plot(s["optimum"]["x"]["tc_root"], s["optimum"]["box_mass_kg"], "r*", ms=13, label="ótimo global")
    ax[0].set_xlabel("t/c raiz")
    ax[0].set_ylabel("massa do caixão [kg]")
    ax[1].plot(tc, [p["cruise"]["CD"] for p in sw], "o-", label="C_D total")
    ax[1].plot(tc, [p["cruise"]["CDp_wing"] + s["calibration"]["CD_rest"] for p in sw], "s--", label="C_D,rest + C_Dp asa")
    ax[1].plot(s["baseline"]["x"]["tc_root"], s["baseline"]["cruise"]["CD"], "ks")
    ax[1].plot(s["optimum"]["x"]["tc_root"], s["optimum"]["cruise"]["CD"], "r*", ms=13)
    ax[1].set_xlabel("t/c raiz")
    ax[1].set_ylabel("C_D cruzeiro")
    ax[2].scatter([p["cruise"]["CD"] for p in sw], [p["box_mass_kg"] for p in sw], c=tc, cmap="viridis", s=50)
    for p in sw:
        ax[2].annotate(f"{p['tc_root']:.2f}", (p["cruise"]["CD"], p["box_mass_kg"]), fontsize=7)
    ax[2].plot(s["baseline"]["cruise"]["CD"], s["baseline"]["box_mass_kg"], "ks", label="base")
    ax[2].plot(s["optimum"]["cruise"]["CD"], s["optimum"]["box_mass_kg"], "r*", ms=13, label="ótimo")
    ax[2].set_xlabel("C_D cruzeiro")
    ax[2].set_ylabel("massa do caixão [kg]")
    ax[2].set_title("compromisso massa–arrasto (t/c anotado)", fontsize=9)
    obj = s["objective"]
    ax3 = ax[0].twinx()
    key = {"range": ("range_m", 1e-3, "alcance [km]"), "endurance": ("endurance_ratio", 1, "E/E_base"),
           "mtow": ("W0", 1, "MTOW [kg]"), "weight": ("W0", 1, "MTOW [kg]")}[obj]
    ax3.plot(tc, [p["perf"].get(key[0], math.nan) * key[1] for p in sw], "g^:", label=key[2])
    ax3.set_ylabel(key[2], color="g")
    for a in ax:
        a.grid(alpha=0.3)
    ax[0].legend(fontsize=7, loc="upper left")
    ax[1].legend(fontsize=7)
    ax[2].legend(fontsize=7)
    fig.suptitle(f"{s['name']} — varrimento de t/c (cada ponto otimizado: longarinas, torção, nervuras, k_pele, "
                 f"curvatura), objetivo {obj}", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_layout(P, b, e, path, name):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 3, figsize=(15, 7.5))
    for ev, st, lab in ((b, "k--", "base"), (e, "r-", "ótimo")):
        d, bx = ev.box.details, ev.box
        ax[0, 0].plot(bx.y, d["cover_tbar_upper"] * 1e3, st, label=f"t̄ sup. ({lab})")
        ax[0, 0].plot(bx.y, d["skin_upper"] * 1e3, st, lw=0.8, alpha=0.6)
        ax[0, 1].plot(bx.y, bx.web_t * 1e3, st, label=lab)
        ax[0, 2].plot(ev.y, ev.section["x_sc_c"], st, label=f"x_sc/c ({lab})")
        ax[0, 2].axhline(ev.x["xf"], color=st[0], lw=0.6)
        ax[0, 2].axhline(ev.x["xr"], color=st[0], lw=0.6)
        ax[1, 0].plot(ev.y, ev.section["GJ"] / 1e3, st, label=f"GJ ({lab})")
        ax[1, 0].plot(ev.y, ev.section["EI"] / 1e3 / 10, st, lw=0.8, alpha=0.6)
        yl = P.ll.y
        ax[1, 1].plot(ev.y, ev.cruise["cl_y"], st, label=f"cl cruzeiro ({lab})")
        ax[1, 2].plot(ev.y, ev.manoeuvre["lift"] / 1e3, st, label=f"carga n_lim V_D ({lab})")
    ax[0, 0].set_ylabel("espessura [mm] (t̄ grosso, pele fino)")
    ax[0, 1].set_ylabel("alma [mm]")
    ax[0, 2].set_ylabel("x/c (linhas: longarinas)")
    ax[1, 0].set_ylabel("GJ [kN·m²] (fino: EI/10)")
    ax[1, 1].set_ylabel("cl local")
    ax[1, 2].set_ylabel("carga [kN/m]")
    for a in ax.flat:
        a.set_xlabel("y [m]")
        a.grid(alpha=0.3)
        a.legend(fontsize=7)
    xo = e.x
    fig.suptitle(f"{name}: longarinas {xo['xf']:.3f}/{xo['xr']:.3f} c, t/c {xo['tc_root']:.3f}/{xo['tc_tip']:.3f}, "
                 f"m {xo['camber']:.3f}, torção ponta {xo['twist_tip']:.2f}°, nervuras {xo['rib_pitch']:.2f} m, "
                 f"k_pele {xo['k_skin']:.2f} — caixão {b.mass_box:.1f} → {e.mass_box:.1f} kg", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
