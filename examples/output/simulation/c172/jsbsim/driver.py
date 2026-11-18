
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
