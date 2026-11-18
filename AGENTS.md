# AGENTS.md — rules for AI agents using or editing acdt

> **Repository:** development happens in the public repository `joaovpfrazao/acdt` (Apache-2.0) since
> 18 Nov 2026. Branches and pull requests go there; the former private repository is an archive only.

acdt is meant to be driven by an AI agent: the user describes the aircraft they want, the agent calls the acdt
tools (MCP server `acdt mcp`, see README) and reports back. Full guide (PT): [docs/ai-agent-guide.md](docs/ai-agent-guide.md).
Current status, known issues and next steps: [docs/HANDOFF.md](docs/HANDOFF.md); Windows / Cursor setup:
[docs/DEV-SETUP-WINDOWS.md](docs/DEV-SETUP-WINDOWS.md) (`.cursor/mcp.json` registers the server, `.cursor/rules/acdt.mdc` the rules).
The MCP server also serves this file and the guide as the resource `acdt://agents-guide`.
What acdt can and cannot do, per area (PT, user-facing): [CAPABILITIES.md](CAPABILITIES.md), resource
`acdt://capabilities` — read it before promising the user an analysis, and keep it in sync when you add or
remove a capability (it must only claim what the code does; `tests/test_ai.py` checks its commands/tools).

## Non-negotiable rules

1. **Never invent numbers.** Every number you report comes from a tool result, a cited assumption
   (`assumption_sources`), or external data with provenance (`source_url`, `retrieved` date, `source_type`)
   validated by `validate_material` / `validate_component`. If you do not have a value, say so, or look it up.
2. **Classical, cited methods only.** acdt implements published methods (Raymer, Roskam, Gudmundsson, Nicolai,
   Torenbeek, Anderson, Etkin, Hoerner, Bruhn, Niu, MMPDS, CMH-17, Bisplinghoff, Knott, ...). See the
   resource `acdt://methods`. Do not replace them with your own formulas; if a method is missing, say so.
3. **Low fidelity first, then calibrate.** L0 (handbook) → L1 (XFOIL/AVL) → L2 (MDO, wing box) → L3 (hifi:
   SU2/CalculiX/DLM) → `apply_calibration` → re-run L1. Do not jump to L3.
4. **Flag validity limits.** Every result has `checks` (pass/fail with margins) and `issues`. Report failed
   checks, assumed defaults that drive the answer and the validity range of the method (class, Re, Mach, …).
5. **Compute guard.** `cfd2d`, `gci`, `wing_euler` are heavy: run them only after the user explicitly approves
   that run on that machine (`user_approved=true`, `approval_note` with who/when). The user's own PC is used only
   with permission. Always call `hifi_estimate` first and show the user the plan.
6. **Provenance is recorded.** Every tool call creates a run under `runs/` (`$ACDT_RUNS_DIR`) with inputs,
   assumptions (user / external / assumed default), external data, calibration, tool versions and git commit.
   Cite run ids in your answers.

7. **Solutions are design options.** Any solution (camber flaps, unusual configurations, alternative systems,
   however creative) is an option the optimizer evaluates against the alternatives under the same requirements;
   it is selected only when the requirements justify it, and you report the comparison. Explore broadly; the
   user can pin or exclude options explicitly.

## Workflow (order)

Design process by levels (N0 mission without shape → N1 architecture trade → N2 shape → N3+ closure), with the
configuration always an evaluated alternative and the mission simulator as common judge: see
`docs/DESIGN_WORKFLOW.md`. The tool order below is the single-configuration pipeline used inside each level.

requirements (`requirements_schema`, `validate_requirements`) → conceptual sizing (`size` L0) → design point
(in `size`) → components / systems (`systems`, external components researched on the web) → preliminary sizing
(`size` L1) → high-lift / camber-flap options (`flap_options`: compares none / plain / camber / flaperon
with same-area plain references; adopt camber only if `justified` is true) and MDO (`optimize`) → wing box (`wingbox` phase 5, then 6) → RCS if signature matters (`rcs`) →
control surfaces and mission simulation (`size_control_surfaces`, then
`simulate_mission` with fidelity pointmass for N0/N1 or 6dof for the sized aircraft; examples in `examples/simulation/`) → detailed (`hifi` step `detailed`) → high fidelity (`hifi_estimate`, `hifi` with approval) → calibration
(`apply_calibration`, then `size` again) → manufacturing and cost (`cost_estimate` L0 → `manufacturing_plan`
L1, then L2 with `detailed`; `process_options` and `compare_materials` for single parts) → certification and
safety (`certify`: basis, compliance matrix, FHA/FTA/FMEA, redundancy trade re-sized into W0, SORA; quick what-ifs
with `safety_assessment`) → `generate_report`. Operational weight and balance and the landing-gear layout run inside
`size` (after stability): the `wb:` and `gear:` checks are reported and do not flip Phase-1 feasibility, and
ground-load spin-up, side load and brakes stay open.

**Certification rules:** the catalogue holds paraphrases, never quote regulation text as official; the status is a
conceptual-design self-assessment (the authority decides). Failure rates of kind `assumption` are PRESSUPOSTOS:
report the required MTBF and ask for supplier data. Redundancy options are selected only when a target fails
(report the trade table); a severity override needs a written justification from the user. Report non-compliant
and open items honestly.

## Web research (materials, components, costs)

* Prefer: manufacturer datasheets, MMPDS / CMH-17 / ESDU, standards bodies, peer-reviewed papers, textbooks.
  Retailer pages are acceptable for price and mass only; forums and AI-generated pages are not sources.
* Give each value with its unit as printed in the source ("42 ksi", "5000 mAh"); acdt converts and checks
  plausibility. Record `source_url`, `retrieved` (ISO date), `source_type`, `datasheet`, and for metals the
  allowable `basis` (A/B/S/typical).
* Prices change: always date them.
* **Prices are inputs.** Research each one from a dated distributor or manufacturer page, or a written quote.
  Pass it as `price: {usd_per_kg, year, provenance: {source_url, retrieved, source_type}}`; for a BOM item or a
  quote, use `{usd, year, provenance}`.
  * Retail prices (for example Aircraft Spruce) are above what an OEM pays. Flag them as retail in the report.
  * Record the price year; acdt escalates it with CPI-U. Never invent a price: an item without one is reported
    as missing.
  * For a material that only exists on one process route (a VARI laminate, a prepreg), set
    `processes: [vacuum_infusion]`.
  * Give `labour_calibration` as a number only with its `labour_calibration_source` (shop data). `'eastlake'`
    is a stopgap: it anchors L1 to L0.

## Cost fidelity ladder (L0 → L1 → L2)

The top-down CERs are statistical: Eastlake covers general aviation and DAPCA IV covers military/transport.
Treat them as unreliable for **unconventional** designs (flying wing, BWB, VTOL, distributed or electric
propulsion, unmanned). Escalate the cost fidelity the same way as aero and structures:

1. **L0** (`cost_estimate`, or the top-down section of `manufacturing_plan`). Pass `configuration`
   (unconventional features), `unmanned` and `propulsion`. When the design is outside the CER databases, report
   the L0 as **low confidence**, with the AACE Class 5 band (−50 %/+100 %) and the Eastlake/DAPCA spread. Never
   present it as the cost.
2. **L1** (`manufacturing_plan` on the preliminary design): bottom-up by part and process. This is the
   recommended level for unconventional designs. Report the AACE Class 4 band.
3. **L2** (`manufacturing_plan` with `manufacturing.detailed`): use it once the detailed design exists. Inputs:
   the actual part list (geometry, ply counts, fastener counts, `l1_part` mapping), a BOM with researched
   supplier prices, quotes, shop hours, final-assembly hours and non-recurring cost. Report the AACE Class 3 band
   and the quoted share; it becomes Class 2 when every recurring item is quoted.
4. **Calibrate downwards.** The higher level calibrates the lower one through `cost_calibration.json`:
   * `cost_L0`: `k_cost_L0_*` multiplies the CERs.
   * `cost_L1`: `k_labour_hours_L1` and `k_material_L1` multiply the L1 plan.

   Apply the factors with `manufacturing.cost_calibration: {file, apply: [cost_L1, cost_L0]}`, only for
   variants in the neighbourhood of the design. Never apply factors marked `independent: false`.
5. **Report** for every level: the estimate, the confidence, the band and the recommended level with its
   reason. Also report which calibration factors were applied.

## Reporting

Short summary first (feasible? key numbers with units and run ids), then failed checks and their margins, then
the assumptions that matter (and which were assumed defaults), then validity limits and the next recommended
step (including any compute that needs approval). `generate_report` writes a dossier (`dossier.md/json`).

## Editing the code (for coding agents)

* Licence: our code is Apache-2.0 (`LICENSE`, `NOTICE`); third-party credits live in THIRD_PARTY.md. New files
  start with `# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0`.
* GPL/LGPL tools (AVL, XFOIL, SU2, CalculiX, Gmsh, OpenFOAM, WireViz, KiCad; JSBSim for the Phase 8 cross-check) are **external executables
  only** — never import them.
* Every new method: docstring with the reference (author, year, equation/section) — the methods catalogue is
  built from those docstrings — and a test against a published value.
* Environment on the reference box: `source /workspace/acdt_env.sh`; tests: `python -m pytest -q`.

## Concept trade (free-text problems)

When the user describes a problem rather than an aircraft (e.g. "watch this sea area for illegal fishing"),
follow the MCP prompt `concept_trade` ([docs/ai-concept-trade.md](docs/ai-concept-trade.md)). YOU define the
mission, requirements and alternatives; the `concept_*`, coverage, fleet and `compare_alternatives` tools only
calculate, and `study_id` records every call (`acdt concept replay` checks them).
