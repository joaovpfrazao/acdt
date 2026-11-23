# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Estudo de decisão (applied: false): rajada lateral 6-DOF do caso «cheio» da asa voadora sem deriva.

Uso: python examples/studies/rajada_cheio/estudo_rajada_cheio.py [pasta_de_saída]

Opções postas à decisão do João (nenhuma é aplicada; o exemplo e os valores por omissão não mudam):
  (a) servo mais rápido (taxa na superfície ≥ 100 °/s);
  (b) pré-deflexão simétrica maior (``split_aileron.bias_deg``);
  (c) outros ganhos do SAS (k_β, k_r).
Ferramentas já existentes: ``flightsim.tailless_sim.lateral_test`` (6-DOF não linear, rajada 1−cos de 14 CFR 23.443 e
o critério estrito de ``hq:lateral_gust``), ``tailless_actuation.select_servo`` (catálogo Volz do exemplo, regra
G·T ≥ FoS·|H|, ω/G ≥ taxa), ``tailless_actuation.actuator_dynamics`` (Nível do rolamento holandês e margem de
atraso, MIL-F-8785C 3.5.3), ``tailless_actuation.turbulence_sigma_actuated`` (autoridade 3σ em turbulência na
aproximação) e ``tailless.side_effects`` (arrasto da pré-deflexão, McCormick 1995 Eq. 3.45)."""
from __future__ import annotations

import copy
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "heavy" / "uav150_flying_wing_tailless.yaml"
CASE = "cheio"
STUDY = Path(__file__).with_name("rajada_cheio.yaml")


def _grid() -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    import yaml
    o = yaml.safe_load(STUDY.read_text(encoding="utf-8"))
    assert o.get("applied") is False, "estudo de decisão: applied tem de ser false"
    op = o["options"]
    # k_β do SAS do exemplo é 0 (só amortecedor de guinada): varia-se k_r; k_β × fator não mudaria nada
    return (tuple(float(x) for x in op["a_servo_rates_deg_s"]), tuple(float(x) for x in op["b_bias_deg"]),
            tuple(float(x) for x in op["c_kr_factors"]))


RATES, BIASES, KR_FACTORS = _grid()


def main(out_dir: Path) -> dict:
    from acdt.domains.aircraft.assembly import tailless as T
    from acdt.domains.aircraft.assembly import tailless_actuation as TX
    from acdt.domains.aircraft.flightsim.tailless_sim import (build_tailless_flight_model, lateral_test,
                                                              tailless_spec)
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.phase2 import stability_stage
    from acdt.domains.aircraft.sizing import run as size_run

    # captura dos argumentos lineares usados pelo próprio estágio (sem mudar código): matriz lateral, q̄Sb/Izz, …
    cap: dict = {}
    o_ad, o_ts = TX.actuator_dynamics, TX.turbulence_sigma_actuated

    def ad(A4, kb, kr, qSb_Izz, b, U, cat, lag, dly):  # noqa: ANN001, ANN202
        cap.setdefault("ad", []).append((A4, qSb_Izz, b, U, cat, lag, dly))
        return o_ad(A4, kb, kr, qSb_Izz, b, U, cat, lag, dly)

    def ts(A, kb, kr, qSb_Izz, b, U, sv, Lv, lag, dly):  # noqa: ANN001, ANN202
        cap["ts"] = (A, qSb_Izz, b, U, sv, Lv, lag, dly)
        return o_ts(A, kb, kr, qSb_Izz, b, U, sv, Lv, lag, dly)

    TX.actuator_dynamics, TX.turbulence_sigma_actuated = ad, ts
    t0 = time.time()
    res = size_run(MissionSpec.from_yaml(EXAMPLE))
    stability_stage(res)
    TX.actuator_dynamics, TX.turbulence_sigma_actuated = o_ad, o_ts
    tl = res.dynamics["tailless"]
    spec = tailless_spec(res)
    fw = T.options(spec) or {}
    sa_cfg = fw["split_aileron"]
    acfg = fw["actuators"]
    sa = tl["split_aileron"]
    C1, dmax = sa["C1"], sa["delta_max_deg"]
    sas = tl["sas"]
    kb0, kr0 = sas["k_beta"], sas["k_r"]
    rate0 = tl["actuators"]["rate_max_effective_deg_s"]
    bias0 = float(sa_cfg.get("bias_deg") or 0.0)
    CD0 = float(res.polar.CD0)
    V, h = float(res.cruise_speed), float(res.cruise_altitude)
    fm = build_tailless_flight_model(res, spec, tl, CASE)
    cr_calls = [c for c in cap["ad"] if abs(c[3] - V) < 1e-6]
    ap_calls = [c for c in cap["ad"] if abs(c[3] - V) >= 1e-6]
    (A_cr, qSb_cr, b, U_cr, cat_cr, lag, dly), (A_ap, qSb_ap, _b, U_ap, _cat, _l, _d) = cr_calls[-1], ap_calls[-1]
    A_ts, qSb_ts, _b2, U_ts, sv, Lv, lag_ts, dly_ts = cap["ts"]
    sh = tl["actuators"]["split_aileron"]
    fos, nmax = float(acfg.get("factor_of_safety", 1.5)), int(acfg.get("max_per_surface", 1))
    z_cg = float(res.dynamics.get("modes", {}).get("inertia", {}).get("z_cg", 0.0) or 0.0)

    def gust(rate=None, bias=None, kb=None, kr=None) -> dict:
        t = copy.deepcopy(tl)
        t["actuators"]["rate_max_effective_deg_s"] = rate0 if rate is None else rate
        t.setdefault("lateral_gust", {})["bias_deg"] = bias0 if bias is None else bias
        t["sas"]["k_beta"] = kb0 if kb is None else kb
        t["sas"]["k_r"] = kr0 if kr is None else kr
        r = lateral_test(fm, t, V, h)
        v = r["gust_verdict"]
        s = r["sas"]
        return {"veredicto": "passa" if v.get("ok") is True else ("falha" if v.get("ok") is False else "desconhecido"),
                "settled": v.get("settled"), "saturated": v.get("saturated"), "rate_limited": v.get("rate_limited"),
                "rate_limited_fraction": v.get("rate_limited_fraction"), "peak_rate_deg_s": v.get("peak_rate_deg_s"),
                "rate_required_deg_s": v.get("rate_required_deg_s"), "beta_peak_deg": s["peak"]["beta_deg"],
                "beta_final_deg": s["final_beta_amp_deg"], "split_peak_deg": s["peak"]["split_deg"],
                "elevon_peak_deg": s["peak"]["elevon_deg"], "issue": v.get("issue")}

    def robust(kb, kr) -> dict:
        dc = TX.actuator_dynamics(A_cr, kb, kr, qSb_cr, b, U_cr, cat_cr, lag, dly)
        da = TX.actuator_dynamics(A_ap, kb, kr, qSb_ap, b, U_ap, "C", lag, dly)
        sg = TX.turbulence_sigma_actuated(A_ts, kb, kr, qSb_ts, b, U_ts, sv, Lv, lag_ts, dly_ts)
        capn = T.capacity(C1, dmax)
        three = 3 * sg["sigma_u"] if sg else None
        ms = [d.get("delay_margin_level1_s") for d in (dc, da)]
        return {"level_cruise": dc.get("level"), "level_approach": da.get("level"),
                "zeta_dr_cruise": (dc.get("dutch_roll") or {}).get("zeta"),
                "delay_margin_level1_s": None if any(m is None for m in ms) else min(ms),
                "turb_dCn_3sigma": three, "turb_capacity_dCn": capn,
                "turb_authority_ok": bool(three <= capn) if three is not None else None}

    def servo_for(rate) -> dict:
        s = TX.select_servo(acfg.get("catalog") or [], sh["H_max_Nm"], rate, fos, sh.get("H_operating_Nm"), nmax, dmax)
        pick = s.get("servo")
        H_op = sh.get("H_operating_Nm") or sh["H_max_Nm"]
        # potência mecânica na superfície por folha à taxa exigida: P = FoS·|H_op|·ω (P = T·ω); elétrica: desconhecida
        P = fos * abs(H_op) * math.radians(rate) if rate else None
        return {"ok": s.get("ok"), "servo": pick["name"] if pick else None,
                "n_per_surface": pick["n_per_surface"] if pick else None,
                "rate_at_surface_deg_s": pick["rate_at_surface_deg_s"] if pick else None,
                "mass_split_kg": 4 * pick["n_per_surface"] * pick["unit_mass_kg"] if pick else None,
                "P_mech_per_leaf_W": P, "issue": s.get("issue")}

    base_servo = servo_for(rate0)
    out: dict = {"schema": "acdt.estudo_rajada_cheio/1", "applied": False, "example": str(EXAMPLE.relative_to(ROOT)),
                 "case": CASE, "W0_kg": res.sizing.W0, "V_m_s": V, "h_m": h,
                 "baseline": {"rate_deg_s": rate0, "bias_deg": bias0, "k_beta": kb0, "k_r": kr0,
                              "gust": gust(), "robustness": robust(kb0, kr0), "servo": base_servo,
                              "bias_dCD_over_CD0_pct": 100 * 2 * T.side_effects(sa, C1, bias0, z_cg)["dCD"] / CD0},
                 "criterion": "critério estrito de hq:lateral_gust no 6-DOF (sem saturação, sem limite de taxa, β "
                              "amortecido ≤ 10 % do pico no último quarto)",
                 "a_servo": {}, "b_bias": {}, "c_gains": {}}
    for R in RATES:
        out["a_servo"][f"{R:g}"] = {"rate_deg_s": R, "gust": gust(rate=R), "servo": servo_for(R)}
    for b0 in BIASES:
        row = {"bias_deg": b0, "gust": gust(bias=b0),
               "capacity_unchanged": 2 * b0 <= dmax,
               "dCD_over_CD0_pct": 100 * 2 * T.side_effects(sa, C1, b0, z_cg)["dCD"] / CD0}
        out["b_bias"][f"{b0:g}"] = row
    for fr in KR_FACTORS:
        kr = kr0 * fr
        rb = robust(kb0, kr)
        g = gust(kr=kr)
        lvl_ok = rb["level_cruise"] == 1 and rb["level_approach"] == 1
        out["c_gains"][f"kr×{fr:g}"] = {"k_beta": kb0, "k_r": kr, "gust": g, "robustness": rb,
                                        "level1_kept": lvl_ok,
                                        "veredicto": ("passa" if g["veredicto"] == "passa" and lvl_ok else
                                                      ("falha" if g["veredicto"] == "falha" or not lvl_ok
                                                       else "desconhecido"))}
    # margem de taxa = taxa disponível / pico de taxa no 6-DOF (opções que passam); a mais pequena de cada família
    # é voada também nos outros casos de massa que equilibram (vazio/carga/combustível)
    from acdt.domains.aircraft.flightsim.tailless_sim import trimmable_cases

    def first_pass(rows, key):  # noqa: ANN001, ANN202
        ok = [r for r in rows if (r.get("veredicto") or r["gust"]["veredicto"]) == "passa"]
        return min(ok, key=key) if ok else None

    fa = first_pass(list(out["a_servo"].values()), lambda r: r["rate_deg_s"])
    fb = first_pass(list(out["b_bias"].values()), lambda r: r["bias_deg"])
    fc = first_pass(list(out["c_gains"].values()), lambda r: -r["k_r"])
    picks = {}
    if fa:
        picks["a"] = {"rate_deg_s": fa["servo"]["rate_at_surface_deg_s"] or fa["rate_deg_s"]}
    if fb:
        picks["b"] = {"bias_deg": fb["bias_deg"]}
    if fc:
        picks["c"] = {"kr": fc["k_r"]}
    allc = {}
    for fam, kw in picks.items():
        rows = {}
        for cn in trimmable_cases(tl):
            fmc = build_tailless_flight_model(res, spec, tl, cn)
            t = copy.deepcopy(tl)
            t["actuators"]["rate_max_effective_deg_s"] = kw.get("rate_deg_s", rate0)
            t.setdefault("lateral_gust", {})["bias_deg"] = kw.get("bias_deg", bias0)
            t["sas"]["k_r"] = kw.get("kr", kr0)
            v = lateral_test(fmc, t, V, h)["gust_verdict"]
            avail = kw.get("rate_deg_s", rate0)
            rows[cn] = {"ok": v.get("ok"), "peak_rate_deg_s": v.get("peak_rate_deg_s"),
                        "rate_margin": (avail / v["peak_rate_deg_s"]) if v.get("ok") and v.get("peak_rate_deg_s")
                        else None}
        allc[fam] = {"option": kw, "cases": rows,
                     "all_pass": all(r["ok"] is True for r in rows.values()),
                     "rate_margin_min": min((r["rate_margin"] for r in rows.values() if r["rate_margin"]),
                                            default=None)}
    out["all_cases_check"] = allc
    out["actuator_mass_baseline"] = tl["actuators"].get("mass")
    out["elapsed_s"] = time.time() - t0
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rajada_cheio.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float),
                                               encoding="utf-8")
    return out


if __name__ == "__main__":
    od = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "examples" / "output" / "rajada_cheio"
    r = main(od)
    print(json.dumps({k: r[k] for k in ("W0_kg", "elapsed_s")}, default=float))
