"""Light N2 OML shape trade: Latin-hypercube over extended Shape + packaging volume/FOV score.

Builds on :mod:`acdt.domains.aircraft.rcs.study` (PO RCS + differential drag). Adds fuselage L/D
scales, wing vertical station, wing LE station and a payload aperture station; scores packaging
with a low-fidelity volume/FOV heuristic (full assembly FOV stays in ``assembly.integration``).

Heavy RANS / ADflow–TACS coupling is out of scope here (Grok Build / user PC).

References: Saltelli 2008 (LHS screening); existing RCS study (PO + Nita–Scholz); DESIGN_WORKFLOW N2.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

from ..rcs import geometry as G
from ..rcs import study as St
from ....core.concept.tradeoff import compare

REF = ("rcs.study (PO + Nita–Scholz differential aero); Saltelli 2008 LHS; "
       "packaging volume PRESSUPOSTO usable_frac=0.35; DESIGN_WORKFLOW N2")

# Extended bounds: Phase-6 vars + P6 stations/scales
BOUNDS_N2 = {
    **St.BOUNDS,
    "wing_z_frac": (-0.6, 0.9),       # low to high wing
    "x_wing_le_frac": (0.22, 0.45),
    "L_scale": (0.90, 1.15),
    "D_scale": (0.90, 1.15),
    "sensor_x_frac": (0.08, 0.35),
}


def packaging_score(info: dict, payload: dict | None = None,
                    usable_frac: float = 0.35) -> dict[str, Any]:
    """Low-fi packaging: fuselage usable volume vs payload volume; FOV clearance vs wing LE.

    ``payload``: ``{volume_l, fov_cross_deg?, mass_kg?}`` (EXAMPLE or researched).
    PRESSUPOSTO: usable internal volume = usable_frac · (π/4 D² L); FOV clear if
    sensor_x + 0.05·L < x_wing_le (forward-looking aperture ahead of wing).
    """
    L = float(info.get("L") or 0.0)
    D = float(info.get("D") or 0.0)
    vol_m3 = usable_frac * (math.pi / 4.0) * D * D * L
    need_l = float((payload or {}).get("volume_l") or 0.0)
    need_m3 = need_l / 1000.0
    vol_ok = need_m3 <= vol_m3 if need_l > 0 else True
    margin_m3 = vol_m3 - need_m3
    sensor_x = float(info.get("sensor_x") or 0.0)
    x_le = float(info.get("x_wing_le") or 0.0)
    clearance = (x_le - sensor_x) / L if L else 0.0
    fov_ok = clearance >= 0.05  # PRESSUPOSTO 5 % L
    return {
        "usable_volume_m3": vol_m3,
        "payload_volume_m3": need_m3,
        "volume_margin_m3": margin_m3,
        "volume_ok": vol_ok,
        "sensor_x_m": sensor_x,
        "x_wing_le_m": x_le,
        "fov_clearance_frac_L": clearance,
        "fov_ok": fov_ok,
        "pack_ok": bool(vol_ok and fov_ok),
        "pack_score": (1.0 if vol_ok else 0.0) + max(0.0, min(1.0, clearance / 0.2)),
        "pressuposto": f"usable_frac={usable_frac}; FOV clear se sensor+0.05L < x_wing_le",
        "reference": "heurística N2 — FOV completo em assembly.integration.check_fov",
    }


def _shape_from_dict(d: dict) -> G.Shape:
    keys = [f.name for f in G.Shape.__dataclass_fields__.values()]  # type: ignore[attr-defined]
    return G.Shape(**{k: d[k] for k in keys if k in d})


def evaluate_n2(ev: St.Evaluator, shape: G.Shape, payload: dict | None = None) -> dict:
    r = ev(shape)
    # info is inside mesh path — re-get from aircraft_mesh
    _, info = G.aircraft_mesh(ev.base, shape)
    pack = packaging_score(info, payload=payload)
    r["packaging"] = pack
    r["ok"] = bool(r.get("ok")) and pack["pack_ok"]
    r["info"] = {k: info[k] for k in ("L", "D", "x_wing_le", "z_wing", "sensor_x") if k in info}
    return r


def run_n2_study(result_json: str | Path, out_dir: str | Path, *,
                 n_samples: int = 40, seed: int = 0, payload: dict | None = None,
                 freq: float = St.FREQ_DEFAULT, log=print) -> dict:
    """LHS over :data:`BOUNDS_N2`, Pareto on (perf_ratio max, −RCS, pack_score max)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = St.baseline_from_result(result_json)
    ev = St.Evaluator(base, freq=freq, daz=1.0)  # coarser az for speed
    # baseline row
    s0 = G.Shape()
    # copy baseline shape fields from ev.s0
    for k in St.BOUNDS:
        setattr(s0, k, getattr(ev.s0, k))
    rows = []
    t0 = time.time()
    from scipy.stats.qmc import LatinHypercube
    keys = list(BOUNDS_N2)
    lo = np.array([BOUNDS_N2[k][0] for k in keys])
    hi = np.array([BOUNDS_N2[k][1] for k in keys])
    u = LatinHypercube(d=len(keys), seed=seed, optimization="random-cd").random(n_samples)
    X = lo + u * (hi - lo)
    # include baseline
    samples = [s0.to_dict()] + [{k: float(X[i, j]) for j, k in enumerate(keys)} for i in range(n_samples)]
    for i, sd in enumerate(samples):
        sh = _shape_from_dict(sd)
        try:
            r = evaluate_n2(ev, sh, payload=payload)
        except Exception as e:  # pragma: no cover
            log(f"  sample {i} failed: {e}")
            continue
        rows.append({
            "id": "baseline" if i == 0 else f"s{i}",
            "shape": r["shape"],
            "metrics": {
                "perf_ratio": r["aero"]["perf_ratio"],
                "LD": r["aero"]["LD"],
                "rcs_mean_dbsm": r["rcs"]["all"]["mean_dbsm"],
                "pack_score": r["packaging"]["pack_score"],
                "volume_margin_m3": r["packaging"]["volume_margin_m3"],
                "fov_clearance_frac_L": r["packaging"]["fov_clearance_frac_L"],
            },
            "packaging": r["packaging"],
            "ok": r["ok"],
            "info": r.get("info"),
        })
        if i % 10 == 0:
            log(f"  N2 sample {i}/{len(samples)}  t={time.time()-t0:.1f}s")

    alts = [{"id": r["id"], "metrics": r["metrics"]} for r in rows if r["ok"]
            or r["metrics"].get("perf_ratio") is not None]
    # still include failed pack in compare with constraint
    cmp = compare(
        [{"id": r["id"], "metrics": r["metrics"]} for r in rows],
        objectives={"perf_ratio": "max", "rcs_mean_dbsm": "min", "pack_score": "max"},
        constraints={"pack_score": {"min": 1.0}},  # vol_ok + some clearance
    )
    # attach shape to pareto
    by_id = {r["id"]: r for r in rows}
    for row in cmp["rows"]:
        row["shape"] = by_id.get(row["id"], {}).get("shape")
        row["packaging"] = by_id.get(row["id"], {}).get("packaging")

    report = {
        "schema": "acdt.shape_n2/1",
        "reference": REF,
        "baseline": result_json if isinstance(result_json, str) else str(result_json),
        "n_samples": n_samples,
        "bounds": BOUNDS_N2,
        "payload": payload,
        "rows": rows,
        "compare": cmp,
        "pareto": cmp["pareto"],
        "n_eval": ev.n_eval,
        "elapsed_s": time.time() - t0,
        "limits": [
            "PO RCS + handbook differential aero only — sem RANS/ADflow",
            "packaging volume/FOV é heurística; FOV completo = assembly.integration",
            "sem estruturas/TACS neste passo",
        ],
    }
    (out / "shape_n2.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                                       encoding="utf-8")
    md = ["# Estudo N2 leve — forma OML (aero/RCS/packaging)", "",
          f"Amostras LHS: {n_samples}+baseline. Pareto: {', '.join(cmp['pareto']) or 'vazia'}.", "",
          "## Limites", ""] + [f"* {x}" for x in report["limits"]] + ["",
          "## Frente de Pareto", "",
          "| id | perf_ratio | RCS dBsm | pack_score |", "|---|---|---|---|"]
    for pid in cmp["pareto"]:
        m = by_id[pid]["metrics"]
        md.append(f"| {pid} | {m['perf_ratio']:.3f} | {m['rcs_mean_dbsm']:.2f} | {m['pack_score']:.2f} |")
    (out / "shape_n2.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    report["files"] = {"shape_n2.json": str(out / "shape_n2.json"), "shape_n2.md": str(out / "shape_n2.md")}
    log(f"[acdt] shape N2: {len(rows)} amostras, Pareto {cmp['pareto']} em {report['elapsed_s']:.1f}s")
    return report
