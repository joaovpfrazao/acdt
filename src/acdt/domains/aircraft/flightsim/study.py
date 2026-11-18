"""Fase 8 — orchestration used by the CLI (``acdt controls`` / ``acdt simulate``) and the AI toolkit.

``controls_study``: control-surface sizing of a converged design (:func:`.controls.size_controls`).
``simulation_study``: sized (or current) control layout → AVL flight model → 6-DOF mission with the classic
autopilot, optional JSBSim cross-check (separate process, LGPL) → files in ``out_dir``."""
from __future__ import annotations

import json
from pathlib import Path

from .controls import ControlLayout, size_controls


def _js(o):
    try:
        return o.item()
    except AttributeError:
        return str(o)


def controls_study(res, out_dir, opts: dict | None = None) -> dict:
    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    r = size_controls(res, opts, od)
    s = r.summary()
    (od / "controls.json").write_text(json.dumps(s, indent=1, default=_js, ensure_ascii=False))
    s["files"] = {"controls_json": str(od / "controls.json"), **s.get("plots", {})}
    return s


def layout_from_dict(d: dict) -> ControlLayout:
    return ControlLayout(aileron_span_fraction=d["aileron_span_fraction"], aileron_hinge_xc=1 - d["aileron_cf_c"],
                         flap_hinge_xc=1 - d["flap_cf_c"], elevator_hinge_xc=1 - d["elevator_cf_c"],
                         rudder_hinge_xc=1 - d["rudder_cf_c"])


def simulation_study(res, mission, out_dir, *, layout: str = "sized", jsbsim_check: bool = False,
                     opts: dict | None = None, log=print) -> dict:
    """``mission``: dict or YAML path (see docs/tutorial-fase8-simulador.md). ``layout``: 'sized' (run the
    control sizing first and fly the sized surfaces) or 'current' (the spec's surfaces)."""
    from .aeromodel import build_flight_model
    from .mission import simulate_mission_6dof
    from .tailless_sim import tailless_simulation_study, tailless_spec
    if tailless_spec(res) is not None:
        # tailless split-aileron flying wing: no fin/rudder for the fixed-type model → flight model from the
        # assembly, lateral gust test and the mission with the yaw channel through the split aileron (tailless_sim)
        log("asa voadora sem deriva (split ailerons): modelo da montagem + ensaio lateral + missão (guinada pelo split)")
        return tailless_simulation_study(res, out_dir, jsbsim_check=jsbsim_check, log=log, mission=mission)
    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    out = {}
    L = None
    if layout == "sized":
        log("dimensionamento das superfícies de controlo (AVL)…")
        cs = controls_study(res, od / "controls", opts)
        L = layout_from_dict(cs["layout_sized"])
        out["controls"] = {"layout_sized": cs["layout_sized"], "layout_current": cs["layout_current"],
                           "files": cs["files"]}
    elif layout != "current":
        raise ValueError("layout: 'sized' ou 'current'")
    log("modelo de voo (tabelas AVL α × flap)…")
    fm = build_flight_model(res, opts, layout=L)
    p_fm = fm.save(od)
    log("simulação 6-DOF da missão…")
    r = simulate_mission_6dof(fm, mission, res=res, out_dir=od / "mission")
    out.update(r)
    out["files"] = {**r.get("files", {}), "flight_model_json": str(p_fm)}
    if jsbsim_check:
        from .jsbsim_runner import compare_with_jsbsim, jsbsim_available
        if not jsbsim_available():
            out["jsbsim"] = {"error": "JSBSim indisponível (pip install jsbsim no Python de $ACDT_JSBSIM_PYTHON)"}
        else:
            log("verificação cruzada com JSBSim (processo separado)…")
            cr = sorted((s for s in r["segments"] if s["type"] in ("cruise", "waypoints", "loiter", "climb")),
                        key=lambda s: s["type"] == "climb")
            V = cr[0]["V_target_m_s"] if cr else None
            h = cr[0]["h0_m"] if cr else 1000.0
            if V:
                c = compare_with_jsbsim(fm, V, max(h, 300.0), work_dir=od / "jsbsim", plot=od / "jsbsim_pitch.png")
                out["jsbsim"] = {"V_m_s": V, "h_m": float(max(h, 300.0)), "trim_ours": c["trim_ours"], "trim_jsbsim": c["trim_jsbsim"],
                                 "input": "doublet de profundor (longitudinal)",
                                 "nrms": {k: c["errors"][k]["nrms"] for k in ("alpha", "q", "theta", "V", "h")},
                                 "plot": str(od / "jsbsim_pitch.png")}
    (od / "simulation_summary.json").write_text(json.dumps(out, indent=1, default=_js, ensure_ascii=False))
    out["files"]["simulation_summary_json"] = str(od / "simulation_summary.json")
    return out
