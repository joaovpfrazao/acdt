"""P1b (g): validation harness of the AVL body model (neutral point with bodies).

For each case (an assembly spec JSON, optionally with a ``validation`` block) it reports, in fractions of the
wing MAC, the neutral point from

* AVL with BODY (slender-body source + doublet lines, Drela & Youngren, avl_doc.txt "slender bodies");
* AVL without bodies (surfaces only) + the Torenbeek 1982 App. E fuselage shift (the default x_np source of
  :func:`.sizing.neutral_point`);
* AVL without bodies + Munk's upper bound of the body destabilising moment (M. M. Munk, "The aerodynamic forces
  on airship hulls", NACA Rep. 184, 1924: ΔCm_α ≤ 2·Vol/(S·c) per rad for (k₂ − k₁) → 1, so
  Δx̄_np ≥ −2·Vol/(S·c·CL_α) per body);

and, when the case carries a reference measurement, the error of each against it. Reference values are NEVER
built in: a case gets ``validation.reference`` = {"xbar_np": value (fraction of MAC from the MAC leading
edge), "source": full citation, "conditions": "..."} only from a published report (wind tunnel / CFD) that
João or the Grok Build run supplies — see docs/HANDOFF.md §4b (G2). Without a reference the harness only
checks consistency: the AVL-with-bodies shift must not exceed the Munk bound by more than ``munk_tol``.

Each case is 2 AVL runs (light). Sweeps over many cases / Mach numbers belong to the Grok Build list.
"""
from __future__ import annotations

import json
from pathlib import Path

from .assembly import Assembly
from .sizing import _parts, main_wing, neutral_point


def munk_shift(asm: Assembly, CLa: float) -> dict:
    """Munk (1924) upper bound of the forward x_np shift per body, Δx̄ = 2·Vol/(S·c·CL_α) (fraction of MAC)."""
    _, gw = main_wing(asm)
    _, bodies, _, _, _ = _parts(asm)
    out = {b.name: 2.0 * b.volume() * (2 if b.mirror else 1) / (gw["S"] * gw["mac"] * CLa) for b in bodies}
    return {"per_body": out, "total": sum(out.values())}


def run_case(spec: dict, name: str = "case", mach: float = 0.0, munk_tol: float = 0.0) -> dict:
    asm = Assembly.from_dict(spec["assembly"])
    npd = neutral_point(asm, mach=mach)
    if "x_np" not in npd:
        return {"name": name, "note": npd.get("note", "sem AVL")}
    mac, xle = npd["mac"], npd["x_mac_le"]

    def xb(x):
        return (x - xle) / mac

    bare = xb(npd["x_np_no_bodies"])
    munk = munk_shift(asm, npd["avl_no_bodies"]["CLa"])
    row = {"name": name, "mach": mach, "mac_m": mac,
           "xbar_np": {"avl_bodies": xb(npd["x_np_avl_bodies"]), "avl_no_bodies": bare,
                       "avl_torenbeek": xb(npd["x_np_torenbeek"]), "munk_bound": bare - munk["total"]},
           "shift_mac": {"avl_bodies": xb(npd["x_np_avl_bodies"]) - bare,
                         "torenbeek": xb(npd["x_np_torenbeek"]) - bare, "munk_bound": -munk["total"]},
           "munk_per_body": munk["per_body"]}
    # consistency: the AVL body shift should not be more forward than Munk's bound
    row["avl_within_munk"] = bool(row["shift_mac"]["avl_bodies"] >= row["shift_mac"]["munk_bound"] - munk_tol)
    ref = (spec.get("validation") or {}).get("reference")
    if ref and ref.get("xbar_np") is not None:
        if not ref.get("source"):
            raise ValueError(f"{name}: validation.reference needs a 'source' (citation)")
        r = float(ref["xbar_np"])
        row["reference"] = ref
        row["error_mac"] = {k: v - r for k, v in row["xbar_np"].items()}
        row["best"] = min(row["error_mac"], key=lambda k: abs(row["error_mac"][k]))
    return row


def run_cases(paths, mach: float = 0.0) -> list[dict]:
    rows = []
    for p in paths:
        p = Path(p)
        spec = json.loads(p.read_text(encoding="utf-8"))
        rows.append(run_case(spec, p.stem, float((spec.get("validation") or {}).get("mach", mach))))
    return rows


def write_report(rows: list[dict], path) -> Path:
    L = ["# Validação do modelo de corpos do AVL (ponto neutro)", "",
         "x̄_np em fração da CMA a partir do bordo de ataque da CMA. Munk: limite de NACA Rep. 184 (1924); "
         "Torenbeek 1982 App. E; AVL avl_doc.txt.", "",
         "| caso | Mach | AVL c/ corpos | AVL s/ corpos | + Torenbeek | limite Munk | AVL dentro de Munk | "
         "referência | melhor |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "xbar_np" not in r:
            L.append(f"| {r['name']} | — | {r.get('note', '')} | | | | | | |")
            continue
        x = r["xbar_np"]
        ref = r.get("reference")
        L.append(f"| {r['name']} | {r['mach']:.2f} | {x['avl_bodies']:.3f} | {x['avl_no_bodies']:.3f} | "
                 f"{x['avl_torenbeek']:.3f} | {x['munk_bound']:.3f} | {'sim' if r['avl_within_munk'] else 'NÃO'} | "
                 f"{(format(ref['xbar_np'], '.3f') + ' (' + ref['source'] + ')') if ref else 'sem referência'} | "
                 f"{r.get('best', '—')} |")
    Path(path).write_text("\n".join(L) + "\n", encoding="utf-8")
    return Path(path)
