# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Estudo de decisão (applied: false): carga lateral no toque (14 CFR 23.485) com a opção (a) da rajada.

Uso: python examples/studies/toque_cheio/estudo_toque_cheio.py [pasta_de_saída]

Com o veredicto do toque convergido no passo (flightsim/mission.py, TOUCHDOWN_SUBSTEP_S e mudança de lei no instante
do toque), a opção (a) excede o limite lateral. Quantificam-se quatro famílias, e para cada uma a variante mais pequena
que passa:
  (a) aproximação/afundamento: alvo de afundamento do arredondamento (``td_sink_m_s``) e ângulo da rampa;
  (b) decrab: altura do início da asa baixa, decrab só no arredondamento, ou toque caranguejado;
  (c) bitola: semi-bitola do trem principal, com redimensionamento completo (massa, CG, inércia, trem, missão);
  (d) fator de projeto da carga lateral das pernas (× 23.485): massa das pernas pelo modelo existente
      (``gear_devices.size_gear_side_load_structure``, consola de Al 2024-T3), redimensionado com a massa extra.
Veredicto = banda de ``side_load_band`` (±5 % numérico) sobre a razão máxima carga/limite; em (d), sobre a razão ao
limite de projeto k × 23.485. Nada é aplicado ao exemplo, à simulação nem aos valores por omissão."""
from __future__ import annotations

import copy
import json
import multiprocessing as mp
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STUDY = Path(__file__).with_name("toque_cheio.yaml")
sys.path.insert(0, str(ROOT / "examples" / "studies" / "rajada_cheio"))
from estudo_opcao_a import apply_fixed  # noqa: E402

_G: dict = {}


def _load():
    import yaml
    st = yaml.safe_load(STUDY.read_text(encoding="utf-8"))
    assert st.get("applied") is False, "estudo: applied tem de ser false"
    fx = yaml.safe_load((ROOT / st["fixed_from"]).read_text(encoding="utf-8"))
    assert fx.get("applied") is False
    ex = ROOT / st["example"]
    spec_a = apply_fixed(yaml.safe_load(ex.read_text(encoding="utf-8")), fx["fixed"])
    sim = yaml.safe_load((ROOT / st["simulation"]).read_text(encoding="utf-8"))
    return st, ex, spec_a, fx["fixed"], sim


def _size(spec_dict, ex):
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.phase2 import stability_stage
    from acdt.domains.aircraft.sizing import run as size_run
    res = size_run(MissionSpec.from_dict(spec_dict, source=ex))
    stability_stage(res)
    return res


def _landing(sim: dict, **kw) -> dict:
    m = copy.deepcopy(sim)
    for s in m["mission"]["segments"]:
        if s["type"] == "landing":
            for k, v in kw.items():
                if v == "__del__":
                    s.pop(k, None)
                else:
                    s[k] = v
    return m["mission"]


def _mission(res, mission: dict, factor: float = 1.0) -> dict:
    from acdt.domains.aircraft.flightsim.mission import side_load_band
    from acdt.domains.aircraft.flightsim.tailless_sim import tailless_mission, tailless_spec
    with tempfile.TemporaryDirectory() as td:
        r = tailless_mission(res, tailless_spec(res), res.dynamics["tailless"], mission, td, log=lambda m: None)
    seg = {s["type"]: s for s in r.get("segments") or []}
    L = seg.get("landing") or {}
    t = L.get("touchdown") or {}
    ib, ob = t.get("inboard_ratio"), t.get("outboard_ratio")
    out = {"aborted": r.get("aborted"), "sink_m_s": L.get("sink_at_touchdown_m_s"), "V_td_m_s": L.get("V_touchdown_m_s"),
           "drift_m_s": t.get("drift_m_s"), "residual_crab_deg": t.get("residual_crab_deg"),
           "phi_td_deg": t.get("phi_td_deg"), "inboard_ratio": ib, "outboard_ratio": ob,
           "tip_skid_ok": t.get("tip_skid_ok"), "landing_ground_roll_m": L.get("ground_roll_m"),
           "aft_clearance_ok": (r.get("aft_clearance") or {}).get("ok")}
    if ib is None or ob is None:
        out.update({"status": "nao_avaliado", "ok": None, "max_ratio": None})
    else:
        b = side_load_band(ib / factor, ob / factor)
        out.update({"status": b["side_load_status"], "ok": b["side_load_ok"], "max_ratio": b["side_load_max_ratio"],
                    "design_factor": factor})
    return out


def _veredicto(ok):
    return {True: "passa", False: "falha"}.get(ok, "desconhecido")


def _job_mission(args):
    kw, factor = args
    return _mission(_G["res"], _landing(_G["sim"], **kw), factor)


def _job_track(ht):
    from acdt.domains.aircraft.assembly.gear_devices import size_gear_side_load_structure  # noqa: F401
    spec = copy.deepcopy(_G["spec_a"])
    spec["assumptions"]["assembly"]["options"]["flying_wing"]["gear"]["half_track"] = ht
    res = _size(spec, _G["ex"])
    r = _mission(res, _G["sim"]["mission"])
    g = res.assembly["result"].gear
    ck = {c.key: c.ok for c in res.checks}
    r.update({"half_track_m": ht, "W0_kg": res.sizing.W0, "converged": bool(res.sizing.converged),
              "track_m": g.get("track") or (2 * g["half_track"] if g.get("half_track") else None),
              "gear_checks": {k: v for k, v in ck.items() if k.startswith(("asm:gear", "gear:"))},
              "feasible": bool(res.feasible)})
    return r


def _resize_with_item(spec_a, ex, name, dm):
    spec = copy.deepcopy(spec_a)
    spec["assumptions"]["weights"]["components"]["items"].append({"name": name, "mass_kg": round(dm, 4),
                                                                   "group": "structure"})
    return _size(spec, ex)


def main(out_dir: Path) -> dict:
    from acdt.domains.aircraft.assembly.gear_devices import size_gear_side_load_structure
    t0 = time.time()
    st, ex, spec_a, fixed, sim = _load()
    op = st["options"]
    res = _size(spec_a, ex)
    _G.update({"res": res, "sim": sim, "spec_a": spec_a, "ex": ex})
    ctx = mp.get_context("fork")
    base = _mission(res, sim["mission"])
    jobs = ([({"td_sink_m_s": v}, 1.0) for v in op["a_td_sink_m_s"]]
            + [({"glide_deg": v}, 1.0) for v in op["a_glide_deg"]]
            + [({"decrab_height_m": (v if v is not None else "__del__")}, 1.0) for v in op["b_decrab_height_m"]]
            + ([({"decrab": False, "decrab_height_m": "__del__"}, 1.0)] if op.get("b_no_decrab") else []))
    with ctx.Pool(min(6, len(jobs))) as pool:
        rows = pool.map(_job_mission, jobs)
    with ctx.Pool(min(4, len(op["c_half_track_m"]))) as pool:
        tracks = pool.map(_job_track, op["c_half_track_m"])
    A = [{"td_sink_m_s": j[0]["td_sink_m_s"], **r} for j, r in zip(jobs, rows) if "td_sink_m_s" in j[0]]
    A += [{"glide_deg": j[0]["glide_deg"], **r} for j, r in zip(jobs, rows) if "glide_deg" in j[0]]
    B = [{"decrab": j[0].get("decrab", True),
          "decrab_height_m": (None if j[0].get("decrab_height_m") == "__del__" else j[0].get("decrab_height_m")), **r}
         for j, r in zip(jobs, rows) if "decrab_height_m" in j[0]]
    # (d) fator de projeto da carga lateral: massa das pernas pelo modelo existente; verdict = razão / k
    g = res.assembly["result"].gear
    gopt = spec_a["assumptions"]["assembly"]["options"]["flying_wing"]["gear"]
    comps = spec_a["assumptions"]["weights"]["components"]
    lo = {"main_gear_length_m": comps.get("main_gear_length_m"), "nose_gear_length_m": comps.get("nose_gear_length_m")}
    W_N = res.sizing.W0 * 9.80665
    s1 = size_gear_side_load_structure(g, W_N, diameter_m=gopt.get("leg_diameter_m"), length_opts=lo)
    D = []
    for k in op["d_side_factor"]:
        sk = size_gear_side_load_structure(g, W_N, diameter_m=gopt.get("leg_diameter_m"), length_opts=lo,
                                           side_factor=k)
        D.append({"side_factor": k, "legs_mass_kg": sk.get("mass_two_mains_kg"),
                  "d_legs_mass_kg": (sk.get("mass_two_mains_kg") or 0) - (s1.get("mass_two_mains_kg") or 0),
                  "wall_m": sk.get("wall_m"), "structure_ok": sk.get("ok"),
                  **_mission_ratio_only(base, k)})
    dpass = [d for d in D if d["ok"] is True]
    d_resized = None
    if dpass:
        k = min(d["side_factor"] for d in dpass)
        dk = next(d for d in D if d["side_factor"] == k)
        rk = _resize_with_item(spec_a, ex, f"reforço das pernas principais (carga lateral {k:g}× 23.485)",
                               dk["d_legs_mass_kg"])
        mk = _mission(rk, sim["mission"], factor=k)
        d_resized = {"side_factor": k, "W0_kg": rk.sizing.W0, "converged": bool(rk.sizing.converged),
                     "dW0_kg": rk.sizing.W0 - res.sizing.W0, "mission": mk}

    def smallest(rows, key, rev=False):
        ok = [r for r in rows if r.get("ok") is True]
        return (sorted(ok, key=lambda r: r[key] if r[key] is not None else -1, reverse=rev) or [None])[0]

    out = {"schema": "acdt.estudo_toque_cheio/1", "applied": False, "example": st["example"],
           "fixed_from": st["fixed_from"], "fixed": fixed, "simulation": st["simulation"],
           "W0_kg": res.sizing.W0, "converged": bool(res.sizing.converged),
           "criterion": "14 CFR 23.485(c): razão máxima carga lateral 6-DOF / limite (0,5 W para dentro, 0,33 W para "
                        "fora), banda numérica ±5 % (side_load_band); em (d) limite × k",
           "baseline": base, "a_sink": A, "b_decrab": B, "c_track": tracks, "d_side_factor": D,
           "d_resized": d_resized, "side_structure_k1": s1,
           "smallest_passing": {"a_td_sink": smallest([r for r in A if "td_sink_m_s" in r], "td_sink_m_s", rev=True),
                                "a_glide": smallest([r for r in A if "glide_deg" in r], "glide_deg", rev=True),
                                "b_decrab": None,
                                "c_track": smallest(tracks, "half_track_m"),
                                "d_side_factor": d_resized},
           "elapsed_s": None}
    bp = [r for r in B if r.get("ok") is True]
    out["smallest_passing"]["b_decrab"] = bp[0] if bp else None
    for r in (A + B + tracks + D):
        r["veredicto"] = _veredicto(r.get("ok"))
    base["veredicto"] = _veredicto(base.get("ok"))
    out["elapsed_s"] = time.time() - t0
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "toque_cheio.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float),
                                              encoding="utf-8")
    return out


def _mission_ratio_only(base: dict, k: float) -> dict:
    from acdt.domains.aircraft.flightsim.mission import side_load_band
    if base.get("inboard_ratio") is None:
        return {"status": "nao_avaliado", "ok": None, "max_ratio": None}
    b = side_load_band(base["inboard_ratio"] / k, base["outboard_ratio"] / k)
    return {"status": b["side_load_status"], "ok": b["side_load_ok"], "max_ratio": b["side_load_max_ratio"]}


if __name__ == "__main__":
    od = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "examples" / "output" / "toque_cheio"
    r = main(od)
    print(json.dumps({"W0_kg": r["W0_kg"], "baseline": r["baseline"]["max_ratio"], "elapsed_s": r["elapsed_s"]},
                     default=float))
