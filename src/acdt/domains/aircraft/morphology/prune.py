"""Set-based pruning with an N1 uncertainty band (Sobek, Ward & Liker 1999).

A configuration is cut only when another clearly dominates it even after widening the dominatee's
metrics by the band (and narrowing the dominator's). PRESSUPOSTO: banda por omissão ±15 % nas
métricas de missão e massa — a mesma ordem do k_energia / tolerância P3.
"""
from __future__ import annotations

from acdt.core.concept.tradeoff import compare

DEFAULT_BAND = 0.15  # PRESSUPOSTO N1
DEFAULT_OBJECTIVES = {
    "time_on_station_min": "max",
    "range_km": "max",
    "endurance_min": "max",
    "W0_kg": "min",
    "unit_cost": "min",
    "cost_per_fh": "min",  # P4 ops-cost when morph evaluate attached it
}


def _band_metrics(metrics: dict, band: float, sense_for_pessimistic: dict, for_dominatee: bool) -> dict:
    """Widen dominatee (make worse) or narrow dominator (make worse for it = less dominant)."""
    out = {}
    for k, v in metrics.items():
        if not isinstance(v, (int, float)):
            continue
        sense = sense_for_pessimistic.get(k)
        if sense is None:
            out[k] = float(v)
            continue
        # for dominatee: make worse → max objectives decrease, min objectives increase
        # for dominator: make worse (harder to dominate) → max decrease, min increase — same direction
        # Actually for clear dominance under uncertainty:
        # A dominates B clearly if A_pessimistic dominates B_optimistic
        # A_pess: max↓ min↑; B_opt: max↑ min↓
        if for_dominatee:
            # optimistic for dominatee (harder to be dominated): max↑ min↓
            if sense == "max":
                out[k] = float(v) * (1.0 + band)
            else:
                out[k] = float(v) * (1.0 - band)
        else:
            # pessimistic for candidate dominator
            if sense == "max":
                out[k] = float(v) * (1.0 - band)
            else:
                out[k] = float(v) * (1.0 + band)
    return out


def prune_set_based(rows: list[dict], objectives: dict | None = None, band: float = DEFAULT_BAND,
                    keep: int = 3, constraints: dict | None = None) -> dict:
    """Keep up to ``keep`` non-dominated architectures under the uncertainty band.

    Uses available metrics only (intersection with objectives present on at least one row).
    """
    obj = dict(objectives or DEFAULT_OBJECTIVES)
    # drop objectives nobody has
    present = set()
    for r in rows:
        present.update((r.get("metrics") or {}).keys())
    obj = {k: v for k, v in obj.items() if k in present}
    if not obj:
        return {"alive": [r["id"] for r in rows if r.get("evaluable")], "rejected": [],
                "band": band, "keep": keep, "note": "sem métricas objetivas — nada a podar",
                "reference": "Sobek, Ward & Liker 1999; Deb 2001"}

    # Clear dominance under band: A cuts B if A_pess dominates B_opt on objectives
    rejected = []
    alive_ids = []
    # P4: architectures with unassessed energy/comms stay alive — cannot be cut as dominated
    # on incomplete evidence (set-based; unknown≠dominated).
    hold = [r for r in rows if r.get("evaluable") and r.get("unassessed_axes")]
    hold_ids = {r["id"] for r in hold}
    evaluable = [r for r in rows if r.get("evaluable") and r.get("metrics")
                 and not r.get("unassessed_axes")]
    for b in evaluable:
        b_opt = _band_metrics(b["metrics"], band, obj, for_dominatee=True)
        dominated = False
        by = []
        for a in evaluable:
            if a["id"] == b["id"]:
                continue
            a_pess = _band_metrics(a["metrics"], band, obj, for_dominatee=False)
            # reuse compare on a pair
            pair = compare(
                [{"id": a["id"], "metrics": a_pess}, {"id": b["id"], "metrics": b_opt}],
                obj, constraints)
            brow = next(x for x in pair["rows"] if x["id"] == b["id"])
            if a["id"] in brow.get("dominated_by", []):
                dominated = True
                by.append(a["id"])
        if dominated:
            rejected.append({"id": b["id"], "dominated_by": by,
                             "reason": f"dominada com banda N1 ±{band:.0%} (Sobek/Ward/Liker 1999; Deb 2001)"})
        else:
            alive_ids.append(b["id"])

    for hid in hold_ids:
        if hid not in alive_ids:
            alive_ids.append(hid)

    # Cap alive to `keep` by a simple weighted score on available objectives if too many
    # (unassessed held rows are not dropped by the cap — evidence incomplete)
    if len(alive_ids) > keep:
        protected = [i for i in alive_ids if i in hold_ids]
        candidates = [i for i in alive_ids if i not in hold_ids]
        alts = [{"id": r["id"], "metrics": r["metrics"]} for r in evaluable if r["id"] in candidates]
        if alts:
            cmp = compare(alts, obj, constraints)
            pareto = cmp["pareto"]
            rest = [i for i in candidates if i not in pareto]
            slots = max(0, keep - len(protected))
            kept_c = (pareto + rest)[:slots]
        else:
            pareto, rest, kept_c = [], [], []
        alive_ids = protected + kept_c
        for r in rest:
            if r not in alive_ids:
                rejected.append({"id": r, "dominated_by": [],
                                 "reason": f"fora do tecto de {keep} vivas (set-based); Pareto preferido"})

    return {"alive": alive_ids, "rejected": rejected, "band": band, "keep": keep,
            "objectives": obj, "n_evaluable": len(evaluable),
            "n_unassessed_held": len(hold_ids),
            "pressuposto": f"banda ±{band:.0%} nas métricas (ordem do k_energia / P3); "
                           "eixos energy/comms unassessed ficam vivos (P4)",
            "reference": "Sobek, Ward & Liker 1999 (set-based); Deb 2001 (Pareto); "
                         "DESIGN_WORKFLOW § N1; P4 energy/comms unassessed≠cut"}
