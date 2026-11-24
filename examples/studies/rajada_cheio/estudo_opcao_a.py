# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Redimensionamento com a opção (a) da rajada lateral do caso «cheio» (applied: false, 24 nov 2026).

Uso: python examples/studies/rajada_cheio/estudo_opcao_a.py [pasta_de_saída]

Corre o exemplo da asa voadora sem deriva duas vezes com o mesmo código: tal como está (base) e com os `fixed` de
``opcao_a.yaml`` aplicados em memória (servos 2× Volz DA 30-HT por folha, massa do orçamento 8,80 kg, taxa de projeto
do split ≥ 100 °/s). Em cada corrida: fecho de W0, equilíbrio e margem estática dos 4 casos, HQ (rolamento holandês,
espiral, fugóide), rajada lateral no 6-DOF com o critério estrito nos 4 casos, vento cruzado e a missão 6-DOF com a
massa e inércia novas. A potência mecânica por folha é P = FoS·|H_op|·ω; a elétrica fica desconhecida (os datasheets
Volz não dão rendimento). Nada é aplicado ao exemplo nem aos valores por omissão."""
from __future__ import annotations

import copy
import json
import math
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STUDY = Path(__file__).with_name("opcao_a.yaml")
TOUCHDOWN_DTS = (0.01, 0.025)   # passo do yaml de simulação = 0,02 s
HQ_KEYS = ("hq:dutch_roll", "hq:spiral", "hq:phugoid", "hq:phugoid_autopilot", "hq:lateral_gust", "hq:yaw_crosswind",
           "hq:sas_authority", "hq:sas_time_delay", "hq:actuators", "asm:actuator_mass", "hq:pitch_trim_tailless")


def apply_fixed(d: dict, fixed: dict) -> dict:
    """Cópia do dicionário do exemplo com os `fixed` do estudo (substituição de itens pelo nome e chaves por caminho)."""
    d = copy.deepcopy(d)
    items = d["assumptions"]["weights"]["components"]["items"]
    for r in fixed.get("replace_items") or []:
        idx = [i for i, it in enumerate(items) if str(it.get("name", "")).startswith(r["match"])]
        assert len(idx) == 1, f"item '{r['match']}' tem de existir uma vez"
        items[idx[0]] = dict(r["item"])
    for path, val in (fixed.get("set") or {}).items():
        node = d
        *head, last = path.split(".")
        for k in head:
            node = node[k]
        node[last] = val
    return d


def _ck(res) -> dict:  # noqa: ANN001
    return {c.key: {"ok": c.ok, "message": c.message} for c in res.checks}


def run_one(spec_dict: dict, src: Path, sim_yaml: Path, label: str) -> dict:
    from acdt.domains.aircraft.flightsim.study import simulation_study
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.phase2 import stability_stage
    from acdt.domains.aircraft.sizing import run as size_run

    t0 = time.time()
    res = size_run(MissionSpec.from_dict(spec_dict, source=src))
    stability_stage(res)
    ck = _ck(res)
    t = res.dynamics["tailless"]
    act = t.get("actuators") or {}
    sh = act.get("split_aileron") or {}
    pick = (sh.get("servo") or {}).get("servo") or {}
    fos = float(act.get("factor_of_safety", 1.5))
    H_op = sh.get("H_operating_Nm") or sh.get("H_max_Nm")
    rate = act.get("rate_max_effective_deg_s")
    ap = t.get("approach_consistency") or {}
    sas = t.get("sas") or {}
    ad = t.get("actuator_dynamics") or {}
    cw = t.get("crosswind") or {}
    inert = (res.dynamics.get("modes") or {}).get("inertia") or {}
    gl = t.get("lateral_gust") or {}
    with tempfile.TemporaryDirectory() as td:
        sim = simulation_study(res, sim_yaml, td, log=lambda m: None)
    g6 = sim.get("lateral_gust_6dof") or {}
    cases6 = {}
    for cn, v in (g6.get("cases") or {}).items():
        pk, av = v.get("peak_rate_deg_s"), v.get("rate_available_deg_s")
        cases6[cn] = {"ok": v.get("ok"), "veredicto": {True: "passa", False: "falha"}.get(v.get("ok"), "desconhecido"),
                      "rate_limited": v.get("rate_limited"), "saturated": v.get("saturated"),
                      "peak_rate_deg_s": pk, "rate_required_deg_s": v.get("rate_required_deg_s"),
                      "rate_available_deg_s": av,
                      "rate_margin": (av / pk) if (v.get("ok") and pk and av) else None}
    ms = sim.get("mission") or {}
    seg = {s["type"]: s for s in ms.get("segments") or []}
    td_ = (seg.get("landing") or {}).get("touchdown") or {}
    # sensibilidade da carga lateral no toque ao passo de integração (o veredicto do 6-DOF depende da trajetória)
    import yaml
    sens = {}
    sd = yaml.safe_load(sim_yaml.read_text(encoding="utf-8"))
    for dt in TOUCHDOWN_DTS:
        s2 = copy.deepcopy(sd)
        s2["mission"]["dt"] = dt
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "sim.yaml"
            f.write_text(yaml.safe_dump(s2, allow_unicode=True), encoding="utf-8")
            m2 = (simulation_study(res, f, td, log=lambda m: None).get("mission") or {})
        t2 = ({x["type"]: x for x in m2.get("segments") or []}.get("landing") or {}).get("touchdown") or {}
        sens[f"{dt:g}"] = {k: t2.get(k) for k in ("side_load_status", "inboard_ratio", "outboard_ratio")}
    to = seg.get("takeoff") or {}
    out = {
        "label": label, "W0_kg": res.sizing.W0, "converged": bool(res.sizing.converged),
        "iterations": getattr(res.sizing, "iterations", None), "feasible": bool(res.feasible),
        "We_kg": getattr(res.sizing, "We", None), "inertia": {k: inert.get(k) for k in ("Ixx", "Iyy", "Izz", "Ixz")},
        "servo_split": {"name": pick.get("name"), "n_per_surface": pick.get("n_per_surface"),
                        "rate_at_surface_deg_s": pick.get("rate_at_surface_deg_s"), "gearing": pick.get("gearing")},
        "split_rate_required_design_deg_s": act.get("split_rate_required_design_deg_s"),
        "rate_max_effective_deg_s": rate, "actuator_mass": act.get("mass"),
        "P_mech_per_leaf_W": (fos * abs(H_op) * math.radians(rate)) if (H_op and rate) else None,
        "P_elec_per_leaf_W": None, "P_elec_note": "desconhecida: datasheets Volz sem rendimento",
        "trim": {"tailless_trim_converged": (res.tailless_trim or {}).get("converged"),
                 "CLmax_trimmed": (res.tailless_trim or {}).get("CLmax_trimmed"),
                 "cases_ok": {cn: bool(c["cruise"]["ok"] and c["approach"]["ok"])
                              for cn, c in (ap.get("cases") or {}).items()},
                 "static_margin": (ap.get("static_margin_band") or {}).get("cases"),
                 "sm_outside_band": (ap.get("static_margin_band") or {}).get("outside")},
        "hq": {k: ck.get(k) for k in HQ_KEYS},
        "dutch_roll_zeta_bare_cruise": ((t.get("bare") or {}).get("cruise") or {}).get("dutch_roll", {}).get("zeta"),
        "sas": {"k_beta": sas.get("k_beta"), "k_r": sas.get("k_r")},
        "delay_margin_level1_s": ad.get("delay_margin_level1_s"),
        "phugoid_zeta_bare": (t.get("pitch_hold") or {}).get("bare_phugoid_zeta"),
        "crosswind": {"kt": cw.get("crosswind_kt"), "max_kt": cw.get("crosswind_max_kt")},
        "lateral_gust_linear": {"ok": gl.get("ok"), "rate_limited": ((gl.get("sas") or {}).get("actuator") or {})
                                .get("rate_limited")},
        "gust_6dof": {"ok": g6.get("ok"), "cases": cases6,
                      "rate_margin_min": min((c["rate_margin"] for c in cases6.values() if c["rate_margin"]),
                                             default=None)},
        "mission_6dof": {"status": ms.get("status"), "aborted": ms.get("aborted"),
                         "takeoff_ground_roll_m": to.get("ground_roll_m"),
                         "touchdown_side_load_status": td_.get("side_load_status"),
                         "inboard_ratio": td_.get("inboard_ratio"), "outboard_ratio": td_.get("outboard_ratio"),
                         "residual_crab_deg": td_.get("residual_crab_deg"),
                         "tip_skid_ok": td_.get("tip_skid_ok"),
                         "touchdown_diag": {k: td_.get(k) for k in ("phi_td_deg", "drift_m_s", "main_side_N",
                                                                    "main_vertical_peak_N", "W_N", "side_load_margin",
                                                                    "bumper_contacts_N", "issue")},
                         "sink_at_touchdown_m_s": (seg.get("landing") or {}).get("sink_at_touchdown_m_s"),
                         "touchdown_dt_sensitivity": sens,
                         "yaw_split_rate_limited_fraction": (ms.get("yaw_split") or {}).get("rate_limited_fraction"),
                         "yaw_split_saturated": (ms.get("yaw_split") or {}).get("actuator_saturated"),
                         "aft_clearance_min_m": (ms.get("aft_clearance") or {}).get("min_clearance_m"),
                         "aft_clearance_ok": (ms.get("aft_clearance") or {}).get("ok")},
        "checks": {k: v["ok"] for k, v in ck.items()},
        "elapsed_s": time.time() - t0}
    return out


def main(out_dir: Path) -> dict:
    import yaml
    st = yaml.safe_load(STUDY.read_text(encoding="utf-8"))
    assert st.get("applied") is False, "estudo: applied tem de ser false"
    ex = ROOT / st["example"]
    base = yaml.safe_load(ex.read_text(encoding="utf-8"))
    opt = apply_fixed(base, st["fixed"])
    sim = ROOT / st["simulation"]
    rb = run_one(base, ex, sim, "base")
    ra = run_one(opt, ex, sim, "opcao_a")
    changed = {k: {"base": rb["checks"].get(k), "opcao_a": ra["checks"].get(k)}
               for k in sorted(set(rb["checks"]) | set(ra["checks"])) if rb["checks"].get(k) != ra["checks"].get(k)}
    out = {"schema": "acdt.estudo_rajada_cheio_opcao_a/1", "applied": False, "example": st["example"],
           "simulation": st["simulation"], "fixed": st["fixed"], "base": rb, "opcao_a": ra,
           "delta": {"W0_kg": ra["W0_kg"] - rb["W0_kg"], "W0_pct": 100 * (ra["W0_kg"] / rb["W0_kg"] - 1)},
           "checks_changed": changed,
           "new_failures": sorted(k for k, v in changed.items() if v["opcao_a"] is False),
           "new_unknown": sorted(k for k, v in changed.items() if v["opcao_a"] is None)}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "opcao_a.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float),
                                          encoding="utf-8")
    return out


if __name__ == "__main__":
    od = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "examples" / "output" / "rajada_cheio"
    r = main(od)
    print(json.dumps({"delta": r["delta"], "new_failures": r["new_failures"], "new_unknown": r["new_unknown"]},
                     default=float))
