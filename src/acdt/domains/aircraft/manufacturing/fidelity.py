"""Fidelity ladder for cost (Phase 7), like aero/structures: L0 → L1 → L2, each higher level calibrating the lower.

* **L0 — top-down CERs** (modified Eastlake, DAPCA IV) from W_e, V_H, N. Statistical: valid only inside the
  database they were fitted to (Eastlake: general-aviation aircraft, Gudmundsson 2014 Ch. 2; DAPCA IV: military
  and transport aircraft, Raymer 2018 Ch. 18). Unconventional configurations, unmanned aircraft and new
  propulsion are OUTSIDE those databases → low confidence, flagged.
* **L1 — parametric bottom-up** by part and process from the PRELIMINARY design (:mod:`.parts` decomposition of
  the sized configuration + :mod:`.processes` models).
* **L2 — detailed bottom-up** from the DETAILED design (:mod:`.detailed`: actual part list, geometry, ply and
  fastener counts, BOM with researched supplier prices, quotes, shop hours).

Calibration (higher → lower, same quantity of the same design, stored like the Phase 4 aero/structures factors
in ``cost_calibration.json``; applied only when listed in ``cost_calibration.apply``):

* group ``cost_L0``: ``k_cost_L0_eastlake``, ``k_cost_L0_dapca4`` = unit cost of the highest available bottom-up
  level / CER unit cost. Applied as a multiplier on the CER unit cost (design neighbourhood only).
* group ``cost_L1``: ``k_labour_hours_L1`` and ``k_material_L1`` = L2 / L1 over the matched parts (L2 ``l1_part``
  or group + kind). Applied as the labour and material multipliers of the L1 plan. ``k_unit_cost_L1`` and the
  per-part ratios are reported.

Uncertainty bands per level: AACE International RP 18R-97 Table 1 expected accuracy ranges (80 % confidence) —
L0 ↔ Class 5 (concept screening, parametric), L1 ↔ Class 4 (study/feasibility, factored/parametric), L2 ↔
Class 3 (semi-detailed unit costs; Class 2 only with a forced detailed take-off of quotes). AACE states the
range moves to its wide end with technological complexity and weak reference data: the position inside each
class range is chosen by the rules in :func:`levels` (ASSUMPTION — documented mapping, not a fitted value)."""
from __future__ import annotations

import json
import math
from pathlib import Path

AACE = {  # (low narrow, low wide), (high narrow, high wide) — RP 18R-97 Table 1
    5: ((-0.20, -0.50), (0.30, 1.00)), 4: ((-0.15, -0.30), (0.20, 0.50)), 3: ((-0.10, -0.20), (0.10, 0.30)),
    2: ((-0.05, -0.15), (0.05, 0.20)), 1: ((-0.03, -0.10), (0.03, 0.15)),
}
LEVEL_CLASS = {"L0": 5, "L1": 4, "L2": 3}
GROUPS = ("cost_L0", "cost_L1")
CONVENTIONAL = ("conventional", "", None)


def band(value: float, cls: int, w: float) -> dict:
    """AACE band at position ``w`` (0 = narrow end, 1 = wide end) of the class range."""
    w = min(max(float(w), 0.0), 1.0)
    (ln, lw), (hn, hw) = AACE[cls]
    lo, hi = ln + w * (lw - ln), hn + w * (hw - hn)
    return {"aace_class": cls, "position": w, "low": value * (1 + lo), "high": value * (1 + hi),
            "low_pct": 100 * lo, "high_pct": 100 * hi, "source": "aace_18r97"}


def cer_applicability(res, mcfg: dict) -> dict:
    """Why the top-down CERs may not apply to this design (outside their statistical database)."""
    spec = res.spec
    reasons = []
    conf = mcfg.get("configuration", (spec.assumptions.get("cost") or {}).get("configuration"))
    feats = conf if isinstance(conf, (list, tuple)) else ([] if conf in CONVENTIONAL else [conf])
    if feats:
        reasons.append("unconventional configuration (" + ", ".join(map(str, feats)) + "): no aircraft of this "
                       "kind in the Eastlake (GA) or DAPCA IV (military/transport) databases")
    if str(spec.aircraft_class).startswith("uav"):
        reasons.append(f"unmanned ({spec.aircraft_class}): both CER databases are crewed aircraft")
    if spec.propulsion_kind not in ("piston_prop", "turboprop", "jet", "turbofan", "turbojet"):
        reasons.append(f"propulsion '{spec.propulsion_kind}' not represented in the CER databases")
    for r in mcfg.get("cer_outside_database_reasons") or []:
        reasons.append(str(r))
    return {"outside_database": bool(reasons), "reasons": reasons,
            "confidence": "low" if reasons else "medium",
            "databases": {"eastlake": "general-aviation aircraft (Gudmundsson 2014 Ch. 2)",
                          "dapca4": "military and transport aircraft (Raymer 2018 Ch. 18)"}}


def levels(td: dict, l1: dict, l2: dict | None, appl: dict, l1_anchor: str, applied: list[str],
           cal: dict | None = None) -> dict:
    """Estimates, confidence and AACE bands of each level available. ``l1_anchor``: 'input' | 'shop' | 'eastlake'
    | 'L2' (how the L1 labour level was set)."""
    el, dp = td["eastlake"]["unit_cost"], td["dapca4"]["unit_cost"]
    F = (cal or {}).get("factors", {})
    out = {}
    l0_val = el
    l0_cal = None
    if "cost_L0" in applied and "k_cost_L0_eastlake" in F:
        l0_cal = el * F["k_cost_L0_eastlake"]["value"]
    l0 = {"method": "top-down CERs (modified Eastlake central; DAPCA IV as second CER)",
          "unit_cost": l0_cal or l0_val, "eastlake": el, "dapca4": dp, "calibrated": l0_cal is not None,
          "model_spread": {"min": min(el, dp), "max": max(el, dp), "ratio_max_min": max(el, dp) / min(el, dp)},
          **appl}
    w0 = 1.0 if appl["outside_database"] else 0.0
    if l0_cal is not None:
        w0 = 0.5 * w0  # calibrated in the design neighbourhood: half-way (ASSUMPTION)
        l0["confidence"] = "medium" if appl["outside_database"] else "medium-high"
    l0["band"] = band(l0["unit_cost"], 5, w0)
    l0["band_rule"] = ("wide end if outside the CER database, narrow end inside; half-way after a cost_L0 "
                       "calibration")
    out["L0"] = l0
    v1 = l1["unit_cost"]
    if l1_anchor == "L2":
        w1, c1 = 0.0, "medium-high"
    elif l1_anchor == "shop":
        w1, c1 = 0.5, "medium"
    elif l1_anchor == "eastlake":
        w1, c1 = 1.0, appl["confidence"]
    else:
        w1, c1 = 1.0, "low-medium"
    out["L1"] = {"method": "parametric bottom-up by part/process (preliminary design)", "unit_cost": v1,
                 "labour_anchor": l1_anchor, "confidence": c1, "band": band(v1, 4, w1),
                 "band_rule": "wide end with uncalibrated public process parameters or Eastlake anchoring (inherits "
                              "L0 confidence); middle with a shop labour factor; narrow end after cost_L1 (L2) "
                              "calibration"}
    if l1_anchor == "eastlake":
        out["L1"]["note"] = ("labour level anchored to Eastlake (L0 → L1, the reverse of the ladder): only the "
                             "RELATIVE part/process ranking is bottom-up; replace with shop data or L2")
    if l2:
        q = l2["quoted_share_of_recurring"]
        cls = 2 if q >= 1.0 - 1e-9 and not l2["unresolved_parts"] else 3
        w2 = 1.0 - q if cls == 3 else 0.5
        out["L2"] = {"method": "detailed bottom-up (part list, geometry, plies, fasteners, BOM, quotes)",
                     "unit_cost": l2["totals"]["unit_cost"], "quoted_share_of_recurring": q,
                     "confidence": "high" if cls == 2 else ("medium-high" if q >= 0.5 else "medium"),
                     "band": band(l2["totals"]["unit_cost"], cls, w2),
                     "band_rule": "Class 3, position = 1 − quoted share of the recurring cost; Class 2 when every "
                                  "recurring item is a quote"}
    if l2:
        best, why = "L2", "detailed bottom-up available"
    elif l1_anchor in ("L2", "shop") or appl["outside_database"]:
        best, why = "L1", ("L1 calibrated (" + l1_anchor + ")" if l1_anchor in ("L2", "shop") else
                           "CERs outside their database: the part/process model is the better basis")
    else:
        best, why = "L0", ("conventional design inside the CER database and L1 not calibrated by shop/L2 data "
                           "(public FOPV parameters): keep the CER as the reference, use L1 for relative choices")
    return {"levels": out, "recommended": best, "recommended_why": why,
            "note": "use the recommended level; lower levels are kept for traceability and calibrated by the "
                    "higher one (cost_calibration)"}


def _agg(rows, key, val):
    d = {}
    for r in rows:
        if r.get(val) is None:
            continue
        d[r[key]] = d.get(r[key], 0.0) + r[val]
    return d


def build(design: str, td: dict, l1: dict, l1_rows: list[dict], l2: dict | None, l1_independent: bool,
          sources: dict | None = None) -> dict:
    """Calibration factors higher → lower (cost_L0 from the best bottom-up level, cost_L1 from L2)."""
    F = {}
    ref_level, ref = ("L2", l2["totals"]["unit_cost"]) if l2 else ("L1", l1["unit_cost"])
    indep = True if l2 else l1_independent
    for k, v in (("eastlake", td["eastlake"]["unit_cost"]), ("dapca4", td["dapca4"]["unit_cost"])):
        F[f"k_cost_L0_{k}"] = {"group": "cost_L0", "value": ref / v, "hifi": ref, "lowfi": v, "hifi_level": ref_level,
                               "independent": indep,
                               "what": f"unit cost {ref_level} bottom-up / {k} CER (same design, N, USD year)"}
        if not indep:
            F[f"k_cost_L0_{k}"]["note"] = "L1 labour anchored to Eastlake: NOT independent — do not apply"
    if l2:
        # L1 per matched key (group:kind or the L1 part name) — per-aircraft values
        l1h = {}
        for r in l1_rows:
            s = r["selected"]
            if s is None:
                continue
            for k in (r["part"]["name"], f"{r['part']['group']}:{r['part']['kind']}"):
                e = l1h.setdefault(k, {"labour_hours": 0.0, "material_cost": 0.0, "unit_cost": 0.0})
                e["labour_hours"] += (s["labour_hours"] or 0.0) * s["count"] * l1["learning_factor"]
                e["material_cost"] += (s["material_cost"] or 0.0) * s["count"]
                e["unit_cost"] += s["unit_cost"] or 0.0
        rows = [r for r in l2["parts"] if r.get("unit_cost") is not None]
        keys = sorted({r["key"] for r in rows} & set(l1h))
        miss = sorted({r["key"] for r in rows} - set(l1h))
        mod = [r for r in rows if r["key"] in keys and r.get("labour_hours") is not None]
        h2, m2 = _agg(mod, "key", "labour_hours"), _agg(mod, "key", "material_cost")
        u2 = _agg([r for r in rows if r["key"] in keys], "key", "unit_cost")
        mk = sorted(h2)
        if mk:
            H2, H1 = sum(h2[k] for k in mk), sum(l1h[k]["labour_hours"] for k in mk)
            M2, M1 = sum(m2.get(k, 0.0) for k in mk), sum(l1h[k]["material_cost"] for k in mk)
            if H1 > 0:
                F["k_labour_hours_L1"] = {"group": "cost_L1", "value": H2 / H1, "hifi": H2, "lowfi": H1,
                                          "parts": mk, "what": "labour hours per aircraft, L2 / L1, matched parts"}
            if M1 > 0:
                F["k_material_L1"] = {"group": "cost_L1", "value": M2 / M1, "hifi": M2, "lowfi": M1, "parts": mk,
                                      "what": "material cost per aircraft, L2 / L1, matched parts"}
        if keys:
            U2, U1 = sum(u2[k] for k in keys), sum(l1h[k]["unit_cost"] for k in keys)
            if U1 > 0:
                F["k_unit_cost_L1"] = {"group": "cost_L1", "value": U2 / U1, "hifi": U2, "lowfi": U1, "parts": keys,
                                       "applied": False,
                                       "what": "structure cost per aircraft, L2 / L1, matched parts (reported)"}
            F["per_part_L1"] = {"group": "cost_L1", "applied": False, "value": None,
                                "ratios": {k: {"unit_cost": u2[k] / l1h[k]["unit_cost"] if l1h[k]["unit_cost"] else None,
                                               "labour_hours": (h2[k] / l1h[k]["labour_hours"]
                                                                if k in h2 and l1h[k]["labour_hours"] else None)}
                                           for k in keys},
                                "unmatched_L2_keys": miss, "what": "per matched part L2 / L1 (reported)"}
    return {"design": design, "kind": "cost", "factors": F, "sources": sources or {},
            "note": "ratios higher/lower fidelity of the same design; applied only if the group is listed in "
                    "manufacturing.cost_calibration.apply (cost_L0, cost_L1)"}


def write(cal: dict, path) -> Path:
    p = Path(path)
    p.write_text(json.dumps(cal, indent=1, default=str), encoding="utf-8")
    return p


def load(mcfg: dict, base: Path | None = None) -> tuple[dict, list[str]]:
    """``manufacturing.cost_calibration: {file?, factors?: {name: value | {value}}, apply: [cost_L0, cost_L1]}``."""
    c = mcfg.get("cost_calibration") or {}
    F = {}
    if c.get("file"):
        p = Path(c["file"])
        if not p.is_absolute() and base is not None:
            p = base / p
        F.update(json.loads(p.read_text(encoding="utf-8")).get("factors", {}))
    for k, v in (c.get("factors") or {}).items():
        F[k] = v if isinstance(v, dict) else {"value": float(v), "group": _group(k)}
    apply = [g for g in (c.get("apply") or []) if g in GROUPS]
    bad = [g for g in (c.get("apply") or []) if g not in GROUPS]
    if bad:
        raise ValueError(f"cost_calibration.apply: unknown group(s) {bad}; use {GROUPS}")
    for k, f in F.items():
        if f.get("group") in apply and f.get("independent") is False:
            raise ValueError(f"{k} is not independent (L1 anchored to Eastlake): cannot apply it to L0")
    return {"factors": F}, apply


def _group(k: str) -> str:
    return "cost_L0" if "L0" in k else "cost_L1"


def factor(cal: dict, name: str, default: float = 1.0) -> float:
    f = (cal or {}).get("factors", {}).get(name)
    v = None if f is None else f.get("value")
    return default if v is None or not math.isfinite(v) else float(v)
