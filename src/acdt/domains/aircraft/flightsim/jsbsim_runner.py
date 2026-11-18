"""Execução do JSBSim **como processo separado** (LGPL-2.1; o ACDT não o importa no seu processo).

Um script-piloto (texto em :data:`DRIVER`) é escrito numa pasta temporária e corrido com o interpretador indicado
em ``$ACDT_JSBSIM_PYTHON`` (por omissão o mesmo ``sys.executable``, que deve ter o pacote ``jsbsim`` instalado).
A troca de dados é por JSON (entrada: modelo, condição inicial, tarefas; saída: trim e históricos temporais).

Tarefas suportadas:
* ``trim``: equilíbrio longitudinal (α, δe, manete) por mínimos quadrados sobre u̇, ẇ, q̇ do próprio JSBSim
  (``run_ic`` com o estado imposto) — o FGTrim do JSBSim exige motores, e a tração aqui é uma reacção externa.
* ``run``: integra ``T`` segundos a partir do trim, com comandos por tabela temporal (degraus/doublets),
  registando propriedades.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ..aero.interfaces import ToolNotAvailable

DRIVER = r'''
import json, math, sys
import numpy as np
import jsbsim
from scipy.optimize import least_squares
job = json.load(open(sys.argv[1]))
fdm = jsbsim.FGFDMExec(job["root"])
fdm.set_debug_level(0)
fdm.load_model(job["model"])
fdm.set_dt(job.get("dt", 1.0 / 120.0))
for _p in ("aero/force/L_basic", "aero/force/D_basic", "aero/moment/Pitch_basic", "aero/moment/Roll"):
    if not fdm.get_property_manager().hasNode(_p):
        raise SystemExit(f"JSBSim model incomplete: property {_p} missing (XML rejected)")
FT = 3.280839895
lim = job["limits"]
out = {"version": jsbsim.__version__}

def set_state(V, h, alpha, gamma, de, thr, flap):
    # static trim: JSBSim derives alphadot from consecutive IC calls, so the alphadot term is gated off here
    fdm["acdt/alphadot-enable"] = 0.0
    # latitude 45°: JSBSim's WGS-84 gravity there ≈ the standard g0 = 9.80665 m/s² of the in-house 6-DOF (the
    # default IC latitude 0° has ~0.3 % less effective gravity → ~0.02–0.04° trim-α offset, 11 nov 2026)
    fdm["ic/lat-geod-deg"] = job.get("lat_deg", 45.0)
    fdm["ic/h-sl-ft"] = h * FT
    fdm["ic/vt-fps"] = V * FT
    fdm["ic/alpha-rad"] = alpha
    fdm["ic/beta-rad"] = 0.0
    fdm["ic/gamma-rad"] = gamma
    fdm["ic/phi-rad"] = 0.0
    fdm["ic/psi-true-rad"] = 0.0
    fdm["ic/p-rad_sec"] = 0.0
    fdm["ic/q-rad_sec"] = 0.0
    fdm["ic/r-rad_sec"] = 0.0
    fdm["fcs/elevator-cmd-norm"] = de / math.radians(lim["elevator"])
    fdm["fcs/pitch-trim-cmd-norm"] = 0.0
    fdm["fcs/aileron-cmd-norm"] = 0.0
    fdm["fcs/rudder-cmd-norm"] = 0.0
    fdm["fcs/throttle-cmd-acdt"] = thr
    fdm["fcs/flap-cmd-deg"] = flap
    fdm.run_ic()

trim = None
for task in job["tasks"]:
    if task["type"] == "trim":
        V, h, g, fl = task["V"], task["h"], task.get("gamma", 0.0), task.get("flap", 0.0)
        def res(z):
            set_state(V, h, z[0], g, z[1], z[2], fl)
            return [fdm["accelerations/udot-ft_sec2"] / FT / 9.80665, fdm["accelerations/wdot-ft_sec2"] / FT / 9.80665,
                    fdm["accelerations/qdot-rad_sec2"]]
        # JSBSim's IC path is not smooth at 1e-8 (single-precision steps inside): finite differences of 1e-4
        sol = least_squares(res, task.get("x0", [0.05, 0.0, 0.5]), bounds=([-0.3, -0.6, 0.0], [0.4, 0.6, 1.0]),
                            xtol=1e-12, ftol=1e-12, diff_step=1e-4)
        set_state(V, h, sol.x[0], g, sol.x[1], sol.x[2], fl)
        fdm["acdt/alphadot-enable"] = 1.0
        trim = {"alpha_deg": math.degrees(sol.x[0]), "delta_e_deg": math.degrees(sol.x[1]), "throttle": float(sol.x[2]),
                "residual": float(np.max(np.abs(sol.fun))), "V": V, "h": h, "gamma_deg": math.degrees(g), "flap": fl,
                "thrust_N": fdm["external_reactions/thrust/magnitude"] * 4.4482216}
        out["trim"] = trim
        trim["_z"] = list(sol.x)
    elif task["type"] == "run":
        if trim is None:
            raise SystemExit("run requires a previous trim")
        z = trim["_z"]
        set_state(trim["V"], trim["h"], z[0], math.radians(trim["gamma_deg"]), z[1], z[2], trim["flap"])
        T, dt = task["T"], fdm.get_delta_t()
        props = task.get("log", [])
        hist = {p: [] for p in ["t"] + props}
        sched = task.get("inputs", [])  # [{"t0","t1","de"/"da"/"dr" (rad increment)}]
        base = {"de": z[1], "da": 0.0, "dr": 0.0}
        t = 0.0
        k = 0
        every = max(1, int(round(task.get("log_dt", 0.05) / dt)))
        while t <= T + 1e-9:
            u = dict(base)
            for s in sched:
                if s["t0"] <= t < s["t1"]:
                    for kk in ("de", "da", "dr"):
                        u[kk] += s.get(kk, 0.0)
            fdm["fcs/elevator-cmd-norm"] = u["de"] / math.radians(lim["elevator"])
            fdm["fcs/aileron-cmd-norm"] = u["da"] / math.radians(lim["aileron"])
            fdm["fcs/rudder-cmd-norm"] = u["dr"] / math.radians(lim["rudder"])
            if k % every == 0:
                hist["t"].append(t)
                for p in props:
                    hist[p].append(fdm[p])
            fdm.run()
            t += dt
            k += 1
        out.setdefault("runs", []).append(hist)
if trim:
    trim.pop("_z", None)
json.dump(out, open(sys.argv[2], "w"))
'''


def jsbsim_python() -> str:
    return os.environ.get("ACDT_JSBSIM_PYTHON", sys.executable)


def jsbsim_available() -> bool:
    try:
        r = subprocess.run([jsbsim_python(), "-c", "import jsbsim"], capture_output=True, timeout=60)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def run_jsbsim(fm, tasks: list[dict], work_dir: str | Path | None = None, name: str = "acdt", dt: float = 1 / 120,
               timeout: float = 240.0) -> dict:
    """Export ``fm`` to JSBSim XML and run ``tasks`` in a separate process. Returns the parsed JSON output plus
    the XML path."""
    from .jsbsim_export import write_jsbsim_aircraft
    if not jsbsim_available():
        raise ToolNotAvailable("JSBSim não disponível (pip install jsbsim no interpretador de $ACDT_JSBSIM_PYTHON)")
    wd = (Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="acdt_jsbsim_"))).resolve()
    wd.mkdir(parents=True, exist_ok=True)
    xml = write_jsbsim_aircraft(fm, wd, name)
    job = {"root": str(wd), "model": name, "dt": dt, "limits": fm.aero.limits, "tasks": tasks}
    (wd / "job.json").write_text(json.dumps(job))
    (wd / "driver.py").write_text(DRIVER)
    from acdt.core.provenance import tool_used
    tool_used("python (jsbsim)", jsbsim_python())
    r = subprocess.run([jsbsim_python(), str(wd / "driver.py"), str(wd / "job.json"), str(wd / "out.json")],
                       capture_output=True, text=True, timeout=timeout, cwd=wd)
    if r.returncode != 0:
        raise RuntimeError(f"JSBSim falhou (rc {r.returncode}):\n{r.stderr[-3000:]}")
    out = json.loads((wd / "out.json").read_text(encoding="utf-8"))
    out["xml"] = str(xml)
    out["work_dir"] = str(wd)
    return out


LOG_PROPS = ["aero/alpha-rad", "aero/beta-rad", "attitude/theta-rad", "attitude/phi-rad", "velocities/q-rad_sec",
             "velocities/p-rad_sec", "velocities/r-rad_sec", "velocities/vt-fps", "position/h-sl-ft"]


def compare_with_jsbsim(fm, V: float, h: float, flap: float = 0.0, inputs: list[dict] | None = None, T: float = 10.0,
                        work_dir: str | Path | None = None, plot: str | Path | None = None) -> dict:
    """Trim both models at the same (V, h, flap), apply the same open-loop control schedule and compare the time
    histories (cross-check of the in-house 6-DOF against an independent integrator/atmosphere; same aero data).
    ``inputs`` = [{"t0", "t1", "de"/"da"/"dr" [rad, increment over trim]}]."""
    import math
    import numpy as np
    from .sixdof import SixDOF, trim, Controls, euler_from_quat

    inputs = inputs or [{"t0": 1.0, "t1": 2.0, "de": math.radians(-3)}, {"t0": 2.0, "t1": 3.0, "de": math.radians(3)}]
    sim = SixDOF(fm)
    tr = trim(sim, V, h, flap=flap)
    z0 = [math.radians(tr["alpha_deg"]), math.radians(tr["delta_e_deg"]), min(1.0, tr["throttle"])]
    out = run_jsbsim(fm, [{"type": "trim", "V": V, "h": h, "flap": flap, "x0": z0},
                          {"type": "run", "T": T, "inputs": inputs, "log": LOG_PROPS, "log_dt": 0.05}], work_dir=work_dir)
    jt, js = out["trim"], out["runs"][0]
    # in-house run with the same schedule
    dt = 0.01
    x = tr["x"].copy()
    c0 = tr["controls"]
    tt, ours = [], {k: [] for k in ("alpha", "beta", "theta", "phi", "q", "p", "r", "V", "h")}
    t = 0.0
    every = 5
    k = 0
    while t <= T + 1e-9:
        u = {"de": c0.de, "da": c0.da, "dr": c0.dr}
        for s_ in inputs:
            if s_["t0"] <= t < s_["t1"]:
                for kk in ("de", "da", "dr"):
                    u[kk] += s_.get(kk, 0.0)
        c = Controls(de=u["de"], da=u["da"], dr=u["dr"], throttle=c0.throttle, flap=flap)
        if k % every == 0:
            info = {}
            sim.derivatives(t, x, c, info)
            ph, th, _ = euler_from_quat(x[6:10])
            tt.append(t)
            for key, val in (("alpha", info["alpha"]), ("beta", info["beta"]), ("theta", th), ("phi", ph),
                             ("q", x[11]), ("p", x[10]), ("r", x[12]), ("V", info["Va"]), ("h", -x[2])):
                ours[key].append(float(val))
        x = sim.step(t, x, c, dt)
        t += dt
        k += 1
    FTm = 0.3048
    jmap = {"alpha": np.array(js["aero/alpha-rad"]), "beta": np.array(js["aero/beta-rad"]),
            "theta": np.array(js["attitude/theta-rad"]), "phi": np.array(js["attitude/phi-rad"]),
            "q": np.array(js["velocities/q-rad_sec"]), "p": np.array(js["velocities/p-rad_sec"]),
            "r": np.array(js["velocities/r-rad_sec"]), "V": np.array(js["velocities/vt-fps"]) * FTm,
            "h": np.array(js["position/h-sl-ft"]) * FTm}
    tj = np.array(js["t"])
    err = {}
    for key in ours:
        o = np.interp(tj, tt, ours[key])
        d = o - jmap[key]
        span = max(np.ptp(jmap[key]), np.ptp(o), 1e-9)
        err[key] = {"rms": float(np.sqrt(np.mean(d**2))), "max": float(np.max(np.abs(d))), "range": float(span),
                    "nrms": float(np.sqrt(np.mean(d**2)) / span)}
    res = {"trim_ours": {k: tr[k] for k in ("alpha_deg", "delta_e_deg", "throttle", "residual")},
           "trim_jsbsim": {k: jt[k] for k in ("alpha_deg", "delta_e_deg", "throttle", "residual")},
           "errors": err, "xml": out.get("xml"), "inputs": inputs, "T": T, "V": V, "h": h, "flap": flap}
    if plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        keys = [("alpha", "α [°]", 57.2958), ("q", "q [°/s]", 57.2958), ("theta", "θ [°]", 57.2958),
                ("V", "V [m/s]", 1.0), ("h", "h [m]", 1.0), ("phi", "φ [°]", 57.2958), ("p", "p [°/s]", 57.2958),
                ("r", "r [°/s]", 57.2958), ("beta", "β [°]", 57.2958)]
        fig, axs = plt.subplots(3, 3, figsize=(12, 8), sharex=True)
        for ax, (key, lab, f) in zip(axs.flat, keys):
            ax.plot(tt, np.array(ours[key]) * f, "b-", label="acdt 6-DOF")
            ax.plot(tj, jmap[key] * f, "r--", label="JSBSim")
            ax.set_ylabel(lab)
            ax.grid(alpha=0.3)
        axs[0, 0].legend()
        for ax in axs[-1]:
            ax.set_xlabel("t [s]")
        fig.suptitle(f"acdt 6-DOF vs JSBSim (mesmos dados aero) — V={V:.1f} m/s, h={h:.0f} m, flap={flap:.0f}°")
        fig.tight_layout()
        fig.savefig(plot, dpi=110)
        plt.close(fig)
        res["plot"] = str(plot)
    return res
