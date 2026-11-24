# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Estudo consolidado (applied: false): opção (a) + pernas do trem a 1,3 × 23.485 no caso «cheio» (24 nov 2026).

Uso: python examples/studies/rajada_cheio/estudo_consolidado.py [pasta_de_saída]

Três corridas com o mesmo código e o pipeline completo (``run_pipeline``, sem pasta de saída): o exemplo tal como
está, a opção (a) (``opcao_a.yaml``) e a consolidada (opção (a) + ``gear.side_load_factor`` 1,3 + massa do reforço
das pernas, recalculada no W0 convergido até fechar). Em cada uma: fecho do W0, equilíbrio e margem estática dos 4
casos, HQ (rolamento holandês com SAS, espiral, fugóide nua e com piloto automático), margem de atraso, rajada 6-DOF
estrita nos 4 casos e margens de taxa, vento cruzado, corrida de descolagem (ponto-massa e 6-DOF), carga lateral no
toque convergida e a matriz de verificação dos requisitos. Nada é aplicado ao exemplo nem aos valores por omissão."""
from __future__ import annotations

import copy
import json
import math
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from estudo_opcao_a import HQ_KEYS, apply_fixed  # noqa: E402

STUDY = HERE / "consolidado.yaml"
_GEAR_CACHE: dict = {}   # trem da montagem da última corrida (para recalcular o reforço das pernas)


def _set(d: dict, fixed: dict) -> dict:
    return apply_fixed(d, {"set": fixed.get("set") or {}})


def run_variant(spec_dict: dict, src: Path, sim_yaml: Path, label: str) -> dict:
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.flightsim.study import simulation_study
    from acdt.domains.aircraft.mission import MissionSpec

    t0 = time.time()
    spec = MissionSpec.from_dict(spec_dict, source=src)
    st = run_pipeline("aircraft", spec)
    res = st["result"]
    ck = {c.key: {"ok": c.ok, "message": c.message} for c in res.checks}
    t = res.dynamics["tailless"]
    act = t.get("actuators") or {}
    sh = act.get("split_aileron") or {}
    pick = (sh.get("servo") or {}).get("servo") or {}
    fos = float(act.get("factor_of_safety", 1.5))
    H_op = sh.get("H_operating_Nm") or sh.get("H_max_Nm")
    rate = act.get("rate_max_effective_deg_s")
    ap = t.get("approach_consistency") or {}
    ad = t.get("actuator_dynamics") or {}
    cw = t.get("crosswind") or {}
    gear = res.assembly["result"].gear
    _GEAR_CACHE["last"] = gear
    with tempfile.TemporaryDirectory() as td:
        sim = simulation_study(res, sim_yaml, td, log=lambda m: None)
    g6 = sim.get("lateral_gust_6dof") or {}
    cases6 = {}
    for cn, v in (g6.get("cases") or {}).items():
        pk, av = v.get("peak_rate_deg_s"), v.get("rate_available_deg_s")
        cases6[cn] = {"ok": v.get("ok"), "peak_rate_deg_s": pk, "rate_available_deg_s": av,
                      "rate_required_deg_s": v.get("rate_required_deg_s"),
                      "rate_margin": (av / pk) if (v.get("ok") and pk and av) else None}
    ms = sim.get("mission") or {}
    seg = {s["type"]: s for s in ms.get("segments") or []}
    td_ = (seg.get("landing") or {}).get("touchdown") or {}
    to = seg.get("takeoff") or {}
    vm = st.get("verification") or {}
    rows = [{"id": r["id"], "status": r["status"], "value": r.get("value_display"), "goal": r.get("display"),
             "text": r.get("text")} for r in vm.get("rows") or []]
    counts: dict = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "label": label, "W0_kg": res.sizing.W0, "converged": bool(res.sizing.converged), "feasible": bool(res.feasible),
        "We_kg": getattr(res.sizing, "We", None),
        "inertia": {k: ((res.dynamics.get("modes") or {}).get("inertia") or {}).get(k) for k in ("Ixx", "Iyy", "Izz")},
        "servo_split": {"name": pick.get("name"), "n_per_surface": pick.get("n_per_surface")},
        "rate_max_effective_deg_s": rate,
        "P_mech_per_leaf_W": (fos * abs(H_op) * math.radians(rate)) if (H_op and rate) else None,
        "P_elec_per_leaf_W": None,
        "actuator_mass_kg": (act.get("mass") or {}).get("total_known_kg"),
        "gear_side_load_factor": gear.get("side_load_factor", 1.0),
        "gear_side_structure": {k: (gear.get("side_load_structure") or {}).get(k)
                                for k in ("mass_two_mains_kg", "RF_bending", "RF_shear", "RF_buckling", "ok",
                                          "side_factor", "wall_m")},
        "trim_cases_ok": {cn: bool(c["cruise"]["ok"] and c["approach"]["ok"]) for cn, c in (ap.get("cases") or {}).items()},
        "static_margin": (ap.get("static_margin_band") or {}).get("cases"),
        "hq": {k: (ck.get(k) or {}).get("ok") for k in HQ_KEYS},
        "dutch_roll_msg": (ck.get("hq:dutch_roll") or {}).get("message", "")[:160],
        "phugoid_bare_zeta": (t.get("pitch_hold") or {}).get("bare_phugoid_zeta"),
        "delay_margin_level1_s": ad.get("delay_margin_level1_s"),
        "crosswind": {"kt": cw.get("crosswind_kt"), "max_kt": cw.get("crosswind_max_kt")},
        "perf_checks": {k: v["ok"] for k, v in ck.items() if k.startswith("perf:")},
        "gust_6dof": {"ok": g6.get("ok"), "cases": cases6,
                      "rate_margin_min": min((c["rate_margin"] for c in cases6.values() if c["rate_margin"]),
                                             default=None)},
        "takeoff_6dof": {"ground_roll_m": to.get("ground_roll_m"), "mode": to.get("mode"),
                         "options_closing": sorted(k for k, o in ((ms.get("takeoff_options") or {}).get("options")
                                                                   or {}).items() if o.get("closes") is True)},
        "touchdown": {k: td_.get(k) for k in ("side_load_status", "side_load_ok", "inboard_ratio", "outboard_ratio",
                                              "inboard_ratio_23_485", "outboard_ratio_23_485",
                                              "design_side_load_factor", "drift_m_s", "residual_crab_deg",
                                              "tip_skid_ok")},
        "sink_at_touchdown_m_s": (seg.get("landing") or {}).get("sink_at_touchdown_m_s"),
        "aft_clearance_ok": (ms.get("aft_clearance") or {}).get("ok"),
        "verification": {"counts": counts, "rows": rows},
        "checks": {k: v["ok"] for k, v in ck.items()},
        "failing_checks": {k: v["message"][:200] for k, v in ck.items() if v["ok"] is False},
        "elapsed_s": time.time() - t0}


def _leg_delta(res_gear: dict, W_N: float, spec: dict, k: float) -> float:
    from acdt.domains.aircraft.assembly.gear_devices import size_gear_side_load_structure
    comps = spec["assumptions"]["weights"]["components"]
    gopt = spec["assumptions"]["assembly"]["options"]["flying_wing"]["gear"]
    lo = {"main_gear_length_m": comps.get("main_gear_length_m"), "nose_gear_length_m": comps.get("nose_gear_length_m")}
    m = [size_gear_side_load_structure(res_gear, W_N, diameter_m=gopt.get("leg_diameter_m"), length_opts=lo,
                                       side_factor=f)["mass_two_mains_kg"] for f in (1.0, k)]
    return m[1] - m[0]


def main(out_dir: Path) -> dict:
    import yaml
    st = yaml.safe_load(STUDY.read_text(encoding="utf-8"))
    assert st.get("applied") is False
    oa = yaml.safe_load((ROOT / st["option_a"]).read_text(encoding="utf-8"))
    assert oa.get("applied") is False
    ex = ROOT / st["example"]
    sim = ROOT / st["simulation"]
    base = yaml.safe_load(ex.read_text(encoding="utf-8"))
    spec_a = apply_fixed(base, oa["fixed"])
    k = float(st["fixed"]["set"]["assumptions.assembly.options.flying_wing.gear.side_load_factor"])
    it = st["fixed"]["leg_reinforcement_item"]
    out: dict = {"schema": "acdt.estudo_cheio_consolidado/1", "applied": False, "example": st["example"],
                 "simulation": st["simulation"], "fixed_option_a": oa["fixed"], "fixed": st["fixed"]}
    out["exemplo"] = run_variant(base, ex, sim, "exemplo")
    out["opcao_a"] = run_variant(spec_a, ex, sim, "opcao_a")
    # consolidada: reforço das pernas recalculado no W0 convergido até fechar (degraus de parede do modelo)
    dm, hist = float(it["mass_kg_initial"]), []
    for _ in range(4):
        spec_c = _set(spec_a, st["fixed"])
        spec_c["assumptions"]["weights"]["components"]["items"].append(
            {"name": it["name"], "mass_kg": round(dm, 4), "group": it.get("group", "structure")})
        rc = run_variant(spec_c, ex, sim, "consolidado")
        # massa do reforço com a geometria do trem e o W0 desta corrida
        new = _leg_delta(_GEAR_CACHE["last"], rc["W0_kg"] * 9.80665, spec_c, k)
        hist.append({"leg_item_kg": dm, "W0_kg": rc["W0_kg"], "leg_delta_model_kg": new})
        if abs(new - dm) <= 1e-3:
            break
        dm = new
    out["consolidado"] = rc
    out["leg_reinforcement_iterations"] = hist
    out["leg_reinforcement_closed"] = abs(hist[-1]["leg_delta_model_kg"] - hist[-1]["leg_item_kg"]) <= 1e-3
    E, A, C = out["exemplo"], out["opcao_a"], out["consolidado"]
    out["delta_W0_vs_exemplo_kg"] = C["W0_kg"] - E["W0_kg"]
    out["delta_W0_vs_opcao_a_kg"] = C["W0_kg"] - A["W0_kg"]
    out["checks_changed_vs_exemplo"] = {kk: {"exemplo": E["checks"].get(kk), "consolidado": C["checks"].get(kk)}
                                        for kk in sorted(set(E["checks"]) | set(C["checks"]))
                                        if E["checks"].get(kk) != C["checks"].get(kk)}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "consolidado.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float),
                                              encoding="utf-8")
    return out


if __name__ == "__main__":
    od = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "examples" / "output" / "rajada_cheio"
    r = main(od)
    print(json.dumps({"W0": [r[x]["W0_kg"] for x in ("exemplo", "opcao_a", "consolidado")],
                      "legs": r["leg_reinforcement_iterations"]}, default=float))
