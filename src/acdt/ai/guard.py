"""Compute guard for the high-fidelity (L3) steps of ``acdt hifi``.

Policy (AGENTS.md):

* ``light`` steps (python only, or minutes on a laptop) run when asked;
* ``heavy`` steps (2-D RANS polars, grid convergence, 3-D Euler) run **only** with ``user_approved=True``, i.e. the
  human explicitly authorised that run on *this* machine (the MCP server may be running on the user's PC);
* the full-aircraft RANS is never run by acdt here: ``rans_case`` only writes the case, mesh-size and memory
  estimate (:func:`acdt.domains.aircraft.hifi.cfd3d.full_aircraft_rans_case`), to run on a cluster;
* ``ACDT_MCP_HEAVY=never`` on the server refuses heavy steps even with approval;
* an existing step JSON in the output folder is *reused* (no compute) unless ``force``.

Each step also keeps its own capacity check (:func:`acdt.domains.aircraft.hifi.tools.budget`: memory > 70 % of the
available RAM or time > 45 min → the case is written, not run).

The cost figures are *measured* wall times stored in ``examples/output/*_hifi`` (this repository's reference
runs, 2026-10) where available; otherwise the class only (no invented number)."""
from __future__ import annotations

import os
from pathlib import Path

from acdt.domains.aircraft.hifi.run import STEPS

# step: (class, output json relative to the hifi folder, basis of the estimate)
STEP_COST: dict[str, dict] = {
    "geometry": {"class": "light", "json": "geometry/geometry.json",
                 "basis": "OpenVSP model + STEP/STL export (external OpenVSP python); not timed"},
    "cfd2d": {"class": "heavy", "json": "cfd2d/section_verification.json",
              "basis": "SU2 2-D RANS cruise polar + stall sweep; measured 276 s + 1067 s (uav_endurance_payload) "
                       "and 346 s + 1578 s (cessna172_check) — examples/output/*_hifi/cfd2d"},
    "gci": {"class": "heavy", "json": "gci/gci.json",
            "basis": "3 nested 2-D grids (Roache GCI); did not finish within 9 min on the reference box"},
    "wing_euler": {"class": "heavy", "json": "wing_euler/wing_euler.json",
                   "basis": "SU2 3-D Euler half-wing (gmsh tetra mesh); not timed — treat as heavy"},
    "rans_case": {"class": "light", "json": "rans_case/estimate.json",
                  "basis": "writes the full-aircraft RANS case + estimate only (≈14–16 M cells, 25–29 GB RAM in "
                           "the reference cases) — never executed here"},
    "fem": {"class": "light", "json": "fem/fem_results.json",
            "basis": "CalculiX wing-box shell model; measured 49 s (uav) / 152 s (C172)"},
    "flutter": {"class": "light", "json": "flutter/flutter_results.json",
                "basis": "FEM modes + DLM p-k in python; not timed"},
    "nastran": {"class": "light", "json": "nastran/nastran.json", "basis": "writes SOL 145 decks only"},
    "detailed": {"class": "light", "json": "detailed/detailed.json", "basis": "python (Roskam class II, ribs)"},
    "calibration": {"class": "light", "json": "calibration.json", "basis": "python (factor table)"},
}
assert set(STEP_COST) == set(STEPS)


def estimate(steps, out: str | Path | None = None, force: bool = False, user_approved: bool = False) -> dict:
    """Per-step decision ``run`` / ``cached`` / ``needs_approval`` / ``refused`` and the overall verdict."""
    policy = os.environ.get("ACDT_MCP_HEAVY", "approval").lower()
    out = Path(out) if out else None
    rows, need, refused = [], [], []
    for s in steps:
        if s not in STEP_COST:
            raise ValueError(f"unknown hifi step {s!r} (steps: {', '.join(STEPS)})")
        c = STEP_COST[s]
        cached = bool(out and not force and (out / c["json"]).exists())
        if cached:
            dec = "cached"
        elif c["class"] == "light":
            dec = "run"
        elif policy == "never":
            dec = "refused"
            refused.append(s)
        elif user_approved:
            dec = "run"
        else:
            dec = "needs_approval"
            need.append(s)
        rows.append({"step": s, "class": c["class"], "decision": dec, "basis": c["basis"]})
    verdict = "refused" if refused else ("needs_user_approval" if need else "ok")
    return {"verdict": verdict, "steps": rows, "needs_approval": need, "refused": refused, "policy": policy,
            "message": ({"ok": "all requested steps are light or cached, or approved by the user",
                         "needs_user_approval": "heavy steps " + ", ".join(need) + " need EXPLICIT user approval "
                         "(ask the user; then call again with user_approved=true). They will use the CPU/RAM of "
                         "the machine running this MCP server.",
                         "refused": "server policy ACDT_MCP_HEAVY=never: heavy steps " + ", ".join(refused)
                         + " are not run on this machine"})[verdict]}
