"""acdt MCP server — exposes :mod:`acdt.ai.toolkit` to AI agents (Cursor, Claude, Grok Build, …).

Run: ``acdt mcp`` (stdio, default) or ``acdt mcp --http --port 8765`` (streamable HTTP at ``/mcp``).
Needs the optional ``mcp`` package (``pip install 'acdt[ai]'``); supports SDK v2 (``MCPServer``) and v1
(``FastMCP``).

Long analyses (size, systems, optimize, wingbox, rcs, hifi, manufacturing_plan, size_control_surfaces, flap_options,
simulate_mission, certify) follow the async job pattern: the call waits up to
``wait_s`` seconds and returns the result, or returns a ``job_id`` to poll with ``job_status``. Heavy
high-fidelity steps are refused unless ``user_approved=true`` (see :mod:`acdt.ai.guard`)."""
from __future__ import annotations

import json
from typing import Annotated, Any, Optional

from pydantic import Field

from . import catalogue, external, toolkit as T

try:  # SDK v2
    from mcp.server import MCPServer as _Server
except ImportError:  # SDK v1
    from mcp.server.fastmcp import FastMCP as _Server
try:
    from mcp.types import ToolAnnotations
except ImportError:  # pragma: no cover
    ToolAnnotations = None

import anyio

INSTRUCTIONS = """acdt — aircraft conceptual→detailed design tools (classical, cited methods; low fidelity first).
Workflow: requirements_schema → validate_requirements → size(level L0 then L1) → systems (electric UAV) →
optimize (MDO) → wingbox (phase 5, then 6) → rcs (if signature matters) → manufacturing_plan / cost_estimate /
process_options / compare_materials (prices researched on the web with source_url + date) →
size_control_surfaces → simulate_mission (point-mass is the N0/N1 judge when fidelity is pointmass; 6-DOF stays the default. Failure responses are flown only in point-mass) → certify (basis, compliance matrix,
FHA/FTA/FMEA, redundancy trade into W0, SORA; safety_assessment for quick what-ifs) → hifi_estimate → hifi (heavy steps only
with explicit user approval) → apply_calibration → size again → generate_report.
Rules: never invent numbers — every value comes from a tool, a cited assumption (assumption_sources) or
external data with source_url + retrieved date (validate_material / validate_component). Report validity limits,
failed checks and assumptions. Cost is fidelity-progressive: L0 CERs (low confidence outside their database —
unconventional/unmanned/new propulsion) → L1 part/process bottom-up → L2 detailed (part list, BOM, quotes); report
each level's confidence and AACE band; higher levels calibrate lower ones (cost_calibration.json).
Read acdt://agents-guide first; acdt://capabilities lists what acdt can (and cannot) do per area.
Free-text problems ("watch this sea area for illegal fishing"): prompt concept_trade — YOU derive mission,
requirements and alternatives; concept_* / geo_measure / sweep_coverage / persistent_coverage / barrier_search / size_fleet /
compare_alternatives only calculate (study_id records the audit trail)."""

Src = dict(
    spec=Annotated[Optional[dict], Field(description="mission dict (name, aircraft_class, requirements, assumptions, "
                                                     "assumption_sources, systems)")],
    spec_path=Annotated[Optional[str], Field(description="path of a mission YAML")],
    run_id=Annotated[Optional[str], Field(description="previous run whose spec is reused (and linked)")],
    example=Annotated[Optional[str], Field(description="name of an examples/*.yaml (see list_examples)")],
)
Wait = Annotated[float, Field(description="seconds to wait before returning a job_id instead of the result", ge=0,
                              le=600)]


def _ann(read_only: bool, title: str):
    if ToolAnnotations is None:
        return None
    return ToolAnnotations(title=title, read_only_hint=read_only, destructive_hint=False, open_world_hint=False)


async def _call(fn, *a, **kw):
    return await anyio.to_thread.run_sync(lambda: fn(*a, **kw))


def build_server(name: str = "acdt") -> Any:
    srv = _Server(name, instructions=INSTRUCTIONS)
    tool = srv.tool

    # ---------------------------------------------------------------- requirements
    @tool(name="requirements_schema", annotations=_ann(True, "Requirement types, units, defaults"))
    async def requirements_schema(domain: str = "aircraft") -> dict[str, Any]:
        """Requirement types (key, dimension, units, senses, qualifiers, choices, implemented, method), aircraft
        classes, spec layout and the default assumptions."""
        return await _call(T.requirements_schema, domain)

    @tool(name="validate_requirements", annotations=_ann(False, "Validate and normalise requirements"))
    async def validate_requirements(
            spec: Annotated[dict, Field(description="mission dict; requirement values may be strings like '2.5 h'")],
            record: bool = True) -> dict[str, Any]:
        """Validate + normalise a mission request: SI values, static consistency issues, which values are assumed
        (defaults) vs given, hints on missing requirements. Records a 'requirements' run (run_id → size)."""
        return await _call(T.validate_requirements, spec, record)

    # ---------------------------------------------------------------- analyses (jobs)
    @tool(name="size", annotations=_ann(False, "Size the aircraft (L0/L1)"))
    async def size(spec: Src["spec"] = None, spec_path: Src["spec_path"] = None, run_id: Src["run_id"] = None,
                   example: Src["example"] = None,
                   level: Annotated[str, Field(description="L0 = handbook (Raymer) aero; L1 = XFOIL/AVL low-fi")] = "L1",
                   no_systems: bool = False,
                   assumptions: Annotated[Optional[dict], Field(description="overrides merged over the spec "
                                                                            "assumptions (cite them in spec.assumption_sources)")] = None,
                   materials: Annotated[Optional[dict], Field(description="{'structure': library key or external "
                                                                          "material dict with provenance}")] = None,
                   components: Annotated[Optional[dict], Field(description="{'motors'|'escs'|'cells'|'servos'|"
                                                                           "'autopilots': [component with provenance]}")] = None,
                   wait_s: Wait = 50.0) -> dict[str, Any]:
        """Conceptual sizing + design point (constraint diagram, MDA), structures (V-n, wing box), stability,
        aeroelasticity, performance, cost if requested, report + plots. Returns the summary, failed checks and
        files; or a job_id if still running after wait_s."""
        return await _call(T.start, "size", wait_s, spec=spec, spec_path=spec_path, run_id=run_id, example=example,
                           level=level, no_systems=no_systems, assumptions=assumptions, materials=materials,
                           components=components)

    @tool(name="systems", annotations=_ann(False, "Systems selection and wiring harness"))
    async def systems(spec: Src["spec"] = None, spec_path: Src["spec_path"] = None, run_id: Src["run_id"] = None,
                      example: Src["example"] = None, components: Optional[dict] = None,
                      level: Optional[str] = None, wait_s: Wait = 50.0) -> dict[str, Any]:
        """Electric-UAV systems (propeller, motor, ESC, battery, servos, autopilot, power budget) closed with the
        sizing; harness (WireViz/Graphviz/CSV/KiCad netlist) and compliance checklist. Needs spec.systems."""
        return await _call(T.start, "systems", wait_s, spec=spec, spec_path=spec_path, run_id=run_id,
                           example=example, components=components, level=level)

    @tool(name="optimize", annotations=_ann(False, "MDO (OpenMDAO trust region)"))
    async def optimize(spec: Src["spec"] = None, spec_path: Src["spec_path"] = None, run_id: Src["run_id"] = None,
                       example: Src["example"] = None,
                       objective: Annotated[Optional[str], Field(description="W0 | energy | cost | endurance | range; "
                                                                             "default from the requirements")] = None,
                       solver: Annotated[Optional[str], Field(description="nlbgs | newton (MDA solver)")] = None,
                       max_iter: Annotated[Optional[int], Field(description="trust-region iterations (default "
                                                                            "assumptions.mdo, 8)")] = None,
                       level: Annotated[Optional[str], Field(description="fidelity of the verifying pipeline: L0 "
                                                                         "handbook (fast exploration) | L1 XFOIL/AVL "
                                                                         "(default of the spec)")] = None,
                       consistency_order: Annotated[Optional[int], Field(description="1 (default): value+gradient "
                                                                                     "correction (finite differences of "
                                                                                     "the full pipeline); 0: value only, "
                                                                                     "fewer runs")] = None,
                       assumptions: Optional[dict] = None,
                       wait_s: Wait = 50.0) -> dict[str, Any]:
        """Preliminary MDO: OpenMDAO model (handbook disciplines, calibrated at each iterate) inside a trust
        region, every step verified with the full pipeline. Returns baseline vs optimum and reports. Minutes at
        L1 (each full-pipeline evaluation ≈ 30 s on the box); use L0 first."""
        return await _call(T.start, "optimize", wait_s, spec=spec, spec_path=spec_path, run_id=run_id,
                           example=example, objective=objective, solver=solver, max_iter=max_iter, level=level,
                           consistency_order=consistency_order, assumptions=assumptions)

    @tool(name="wingbox", annotations=_ann(False, "Wing-box study (phase 5/6)"))
    async def wingbox(spec: Src["spec"] = None, spec_path: Src["spec_path"] = None, run_id: Src["run_id"] = None,
                      example: Src["example"] = None,
                      phase: Annotated[int, Field(description="5: spars/t-c/thickness + FEM check; 6: stringers, "
                                                              "ribs, panels (isotropic equivalents)")] = 5,
                      objective: Annotated[Optional[str], Field(description="weight | range | endurance | mtow "
                                                                            "(default: range, endurance if electric)")] = None,
                      material: Annotated[Optional[str], Field(description="phase 6: 'metal'|'composite'")] = None,
                      maxiter: Optional[int] = None, fem: bool = True, materials: Optional[dict] = None,
                      wait_s: Wait = 50.0) -> dict[str, Any]:
        """Wing-box structural study on the sized design (passes a phase-5 run_id to phase 6 to reuse it)."""
        return await _call(T.start, "wingbox", wait_s, spec=spec, spec_path=spec_path, run_id=run_id,
                           example=example, phase=phase, objective=objective, material=material, maxiter=maxiter,
                           fem=fem, materials=materials)

    @tool(name="rcs", annotations=_ann(False, "Radar cross-section (physical optics)"))
    async def rcs(spec: Src["spec"] = None, spec_path: Src["spec_path"] = None, run_id: Src["run_id"] = None,
                  example: Src["example"] = None,
                  mode: Annotated[str, Field(description="validate | study | stl")] = "study",
                  freq_ghz: float = 10.0, samples: int = 80, refine: Optional[list[float]] = None, seed: int = 0,
                  stl_path: Optional[str] = None, wait_s: Wait = 50.0) -> dict[str, Any]:
        """Faceted physical-optics RCS: canonical validation, aero/RCS shaping trade (Pareto) on a sized design
        (pass the size run_id) or the polar of an STL. Indicative only — see limitations in the output."""
        return await _call(T.start, "rcs", wait_s, spec=spec, spec_path=spec_path, run_id=run_id, example=example,
                           mode=mode, freq_ghz=freq_ghz, samples=samples, refine=refine, seed=seed, stl_path=stl_path)

    @tool(name="hifi_estimate", annotations=_ann(True, "High-fidelity cost estimate / guard"))
    async def hifi_estimate(steps: Optional[list[str]] = None, continue_run: Optional[str] = None,
                            force: bool = False) -> dict[str, Any]:
        """Cost class, measured times and permission decision of each hifi step on this machine (no compute).
        Steps: geometry, cfd2d, gci, wing_euler, rans_case, fem, flutter, nastran, detailed, calibration."""
        return await _call(T.hifi_estimate, steps, continue_run, force)

    @tool(name="hifi", annotations=_ann(False, "High-fidelity chain (guarded)"))
    async def hifi(spec: Src["spec"] = None, spec_path: Src["spec_path"] = None, run_id: Src["run_id"] = None,
                   example: Src["example"] = None, steps: Optional[list[str]] = None,
                   user_approved: Annotated[bool, Field(description="TRUE ONLY if the user explicitly approved "
                                                                    "these heavy steps on this machine")] = False,
                   approval_note: Annotated[Optional[str], Field(description="the user's words approving")] = None,
                   continue_run: Optional[str] = None, force: bool = False, wait_s: Wait = 50.0) -> dict[str, Any]:
        """OpenVSP geometry, SU2 2-D/3-D CFD, CalculiX FEM, flutter, Nastran decks, detailed sizing and
        calibration factors. Heavy steps are refused without user_approved; the full RANS is only written."""
        return await _call(T.start, "hifi", wait_s, spec=spec, spec_path=spec_path, run_id=run_id, example=example,
                           steps=steps, user_approved=user_approved, approval_note=approval_note,
                           continue_run=continue_run, force=force)

    @tool(name="job_status", annotations=_ann(True, "Status/result of a job"))
    async def job_status(job_id: str, wait_s: Wait = 0.0) -> dict[str, Any]:
        """Status, log tail and (when done) the result of an async job."""
        return await _call(T.job_status, job_id, wait_s)

    @tool(name="list_jobs", annotations=_ann(True, "List jobs"))
    async def list_jobs() -> dict[str, Any]:
        """Jobs of this server session."""
        return T.list_jobs()

    # ---------------------------------------------------------------- manufacturing / cost (phase 7)
    @tool(name="manufacturing_plan", annotations=_ann(False, "Manufacturing plan + cost (bottom-up/top-down)"))
    async def manufacturing_plan(spec: Src["spec"] = None, spec_path: Src["spec_path"] = None,
                                 run_id: Src["run_id"] = None, example: Src["example"] = None,
                                 manufacturing: Annotated[Optional[dict], Field(description=(
                                     "assumptions.manufacturing: {year, N, materials: {key: {base?|kind, rho, E, "
                                     "Ftu, price: {usd_per_kg, year, provenance: {source_url, retrieved, "
                                     "source_type}}}}, groups: {default: key, wing|htail|vtail|fuselage: key}, "
                                     "choices, process_inputs, labour_calibration (number|'eastlake'), tooling, "
                                     "purchased, validation, operating, configuration (conventional | list of "
                                     "unconventional features → L0 CERs flagged), detailed (L2: parts, bom, "
                                     "final_assembly_hours, non_recurring_usd), cost_calibration: {file, factors, "
                                     "apply: [cost_L0, cost_L1]}}"))] = None,
                                 pareto: Annotated[Optional[dict], Field(description=(
                                     "W0–cost Pareto sweep: {options: {label: {weights_material: metal|composite, "
                                     "manufacturing: overrides}}, ws_factors, AR_values, cost_metric}"))] = None,
                                 level: Annotated[str, Field(description="L0 (default, fast) | L1 sizing")] = "L0",
                                 wait_s: Wait = 50.0) -> dict[str, Any]:
        """Per-part process + material selection at quantity N (feasibility, hours, buy-to-fly, rivets, tooling,
        learning), bottom-up unit cost vs modified Eastlake and DAPCA IV, validation vs a public price, optional
        W0–cost Pareto. Cost fidelity ladder L0 (CERs) → L1 (part/process bottom-up) → L2 (detailed: part list,
        BOM, quotes) with confidence + AACE 18R-97 bands per level and calibration factors higher → lower
        (cost_calibration.json). Prices are INPUTS: research them first (dated source_url)."""
        return await _call(T.start, "manufacturing_plan", wait_s, spec=spec, spec_path=spec_path, run_id=run_id,
                           example=example, manufacturing=manufacturing, pareto=pareto, level=level)

    # ---------------------------------------------------------------- flight (phase 8)
    @tool(name="size_control_surfaces", annotations=_ann(False, "Control-surface sizing (AVL)"))
    async def size_control_surfaces(spec: Src["spec"] = None, spec_path: Src["spec_path"] = None,
                                    run_id: Src["run_id"] = None, example: Src["example"] = None,
                                    options: Annotated[Optional[dict], Field(description=(
                                        "overrides of assumptions.stability.controls (design choices): "
                                        "aileron_max_deg, elevator_max_deg, rudder_max_deg, flap_takeoff_deg, "
                                        "flap_landing_deg, crosswind_kt, engine_y_m, roll_level, candidate "
                                        "ranges, inertia_kgm2, cg_height_m…"))] = None,
                                    wait_s: Wait = 50.0) -> dict[str, Any]:
        """Size aileron (roll time-to-bank, CS-23.157 / MIL-F-8785C), elevator (take-off rotation, trim over CG
        range and flaps), rudder (crosswind, OEI) and flaps with AVL; hinge moments and servo torques. Returns the
        current vs sized layout with the margin of every requirement."""
        return await _call(T.start, "size_control_surfaces", wait_s, spec=spec, spec_path=spec_path, run_id=run_id,
                           example=example, options=options)

    @tool(name="flap_options", annotations=_ann(False, "Trailing-edge option study (camber flaps)"))
    async def flap_options(spec: Src["spec"] = None, spec_path: Src["spec_path"] = None,
                           run_id: Src["run_id"] = None, example: Src["example"] = None,
                           options: Annotated[Optional[list[str]], Field(description=(
                               "subset of none, plain, camber, flaperon (default all)"))] = None,
                           objective: Annotated[Optional[str], Field(description=(
                               "W0 | cost | energy | endurance | range | V_max (default from the spec objectives)"))]
                           = None,
                           min_gain: Annotated[Optional[float], Field(description=(
                               "relative gain camber/flaperon must show over the best simple option (default 0.01)"))]
                           = None,
                           per_option: Annotated[Optional[dict], Field(description=(
                               "per-option overrides, e.g. {camber: {chord_ratio, eta_out, actuators, actuator_mass_kg, "
                               "surface_mass_kg_m2, actuator_cost_usd, deltas_deg, landing_deflection}}"))] = None,
                           sweep: Annotated[Optional[dict], Field(description=(
                               "requirement sweep for a Pareto plot: {key: 'max_speed', values_si: [30, 34, 38]}"))]
                           = None,
                           wait_s: Wait = 50.0) -> dict[str, Any]:
        """Camber (cruise) flaps as a design OPTION: sizes the mission with none / plain / camber / flaperon
        (envelope polar of XFOIL flapped sections, flap schedule δ(CL), ΔCLmax, actuator mass/cost) and selects
        camber only when it beats the best simple option by min_gain. Returns the rows, selection, deltas and plots."""
        return await _call(T.start, "flap_options", wait_s, spec=spec, spec_path=spec_path, run_id=run_id,
                           example=example, options=options, objective=objective, min_gain=min_gain,
                           per_option=per_option, sweep=sweep)

    @tool(name="certify", annotations=_ann(False, "Certification compliance matrix + safety assessment"))
    async def certify(spec: Src["spec"] = None, spec_path: Src["spec_path"] = None,
                      run_id: Src["run_id"] = None, example: Src["example"] = None,
                      certification: Annotated[Optional[dict], Field(description=(
                          "certification block: {basis: cs23|cs25|stanag4671|stanag4703, max_passenger_seats, "
                          "safety: {t_flight_h, options, baseline, unit: {servo_kg, battery_kg, altimeter_kg, "
                          "*_cost}, rate_overrides, supplier_rates, latent_exposure, severity_overrides}, "
                          "sora: {population, aec, mitigations, v_max_m_s, vlos, containment}}"))] = None,
                      wait_s: Wait = 50.0) -> dict[str, Any]:
        """Phase 10: select the certification basis (CS-23 Amdt 6 levels, CS-25, STANAG 4671/4703, SORA), build the
        compliance matrix (paragraph → means of compliance → acdt evidence → compliant/non-compliant/open/needs-test;
        CSV/XLSX/MD), run the low-fi ARP4761 assessment (FHA targets per AC 23.1309-1E / AMC 25.1309 / USAR.1309,
        FTA cut sets, FMEA, required MTBF) and the redundancy trade fed back into W0, plus SORA SAIL/OSOs."""
        return await _call(T.start, "certify", wait_s, spec=spec, spec_path=spec_path, run_id=run_id,
                           example=example, certification=certification)

    @tool(name="safety_assessment", annotations=_ann(True, "Quick FHA/FTA + SORA (no sizing)"))
    async def safety_assessment(template: Annotated[str, Field(description="uas | ga_piston")] = "uas",
                                scheme: Annotated[str, Field(description=(
                                    "ac23_1309_class_I..IV | amc25_1309 | stanag4671 | stanag4703"))] = "stanag4671",
                                t_flight_h: float = 1.0, mtow_kg: float = 150.0,
                                options: Annotated[Optional[dict], Field(description=(
                                    "uas: {servo: single|dual, fcc: simplex|dual|triplex, backup_battery: bool}; "
                                    "ga_piston: {standby_altimeter, standby_attitude}"))] = None,
                                trade: bool = False,
                                unit: Annotated[Optional[dict], Field(description=(
                                    "option unit masses/costs for the trade, e.g. {servo_kg: 0.18, battery_kg: 1.5}"))]
                                = None,
                                baseline: Optional[dict] = None, rate_overrides: Optional[dict] = None,
                                severity_overrides: Optional[dict] = None,
                                supplier_rates: Annotated[Optional[dict], Field(description=(
                                    "{key: {lambda_per_h|mtbf_h, source, retrieved}} — unsourced entries unassessed"
                                ))] = None,
                                sora: Annotated[Optional[dict], Field(description=(
                                    "{span_m, v_max_m_s, population: controlled|<5|<50|<500|<5000|<50000|>50000, "
                                    "aec: 1..12, mitigations: {M1A|M1B|M1C|M2: low|medium|high}, vlos, "
                                    "containment: {adjacent_population_density_per_km2, outdoor_assembly, "
                                    "sheltering?, claimed_robustness?, p_exit_operational_volume_per_fh?, sources?}}"
                                ))] = None
                                ) -> dict[str, Any]:
        """Fault-tree assessment of a template architecture: probability per flight hour of each failure condition
        vs the scheme target, minimal cut sets, single-point failures, required MTBF; optional redundancy trade
        and SORA (iGRC, final GRC, ARC, SAIL, OSO robustness, opt-in Step #8 containment)."""
        return await _call(T.safety_assessment, template, scheme, t_flight_h, mtow_kg, options, trade, unit,
                           baseline, rate_overrides, severity_overrides, sora, supplier_rates)

    @tool(name="simulate_mission", annotations=_ann(False, "Mission simulation (point-mass or 6-DOF)"))
    async def simulate_mission(spec: Src["spec"] = None, spec_path: Src["spec_path"] = None,
                               run_id: Src["run_id"] = None, example: Src["example"] = None,
                               mission: Annotated[Optional[dict], Field(description=(
                                   "simulation mission: {name, dt, pointmass_dt, extrapolate_after_s, initial: "
                                   "{altitude_m, speed_m_s}, wind: {speed_m_s, from_deg, turbulence: {intensity: "
                                   "light|moderate, seed} | {sigma_m_s, L_m}, gusts: [{t, amplitude_m_s, gradient_m, "
                                   "axis}]}, aircraft: N0 block, sensor, failures, segments: [takeoff{flap} | "
                                   "climb{to_altitude_m, speed_m_s} | cruise{time_min|distance_km, speed_m_s, "
                                   "heading_deg} | turn{heading_change_deg, load_factor} | waypoints{points_km} | "
                                   "loiter|patrol{time_min, load_factor|radius_m} | descent{to_altitude_m, "
                                   "vertical_speed_m_s|gamma_deg, speed_m_s} | landing{flap, glide_deg}]}"))] = None,
                               mission_path: Annotated[Optional[str], Field(description="simulation mission YAML")]
                               = None,
                               mission_example: Annotated[Optional[str], Field(description=(
                                   "name of an examples/simulation/*.yaml"))] = None,
                               fidelity: Annotated[str, Field(description=(
                                   "pointmass (N0/N1 quasi-steady 3-DOF, Anderson/Raymer, no AVL flight model) | "
                                   "6dof (default)"))] = "6dof",
                               aircraft: Annotated[Optional[dict], Field(description=(
                                   "N0 aircraft block (mass, polar, propulsion) when fidelity is pointmass and "
                                   "there is no design source. Not the sizing DEFAULT_ASSUMPTIONS."))] = None,
                               layout: Annotated[str, Field(description="6-DOF: sized (default) | current")] = "sized",
                               jsbsim_check: Annotated[bool, Field(description=(
                                   "6-DOF only: also trim + doublets in JSBSim (separate process) and report nrms"))]
                               = False,
                               options: Optional[dict] = None, wait_s: Wait = 50.0) -> dict[str, Any]:
        """Same YAML at two fidelities. pointmass: quasi-steady 3-DOF (Anderson 1999 Ch. 5, Raymer 2018 Ch. 17)
        from an N0 aircraft block or from a sizing result, with sensor footprint along the track and deterministic
        failure responses (continue, RTB, divert). 6dof (default): AVL tables → 6-DOF + classic autopilot
        (Beard & McLain), Dryden and 1−cos gusts; failure responses are logged and not flown."""
        return await _call(T.start, "simulate_mission", wait_s, spec=spec, spec_path=spec_path, run_id=run_id,
                           example=example, mission=mission, mission_path=mission_path,
                           mission_example=mission_example, fidelity=fidelity, aircraft=aircraft, layout=layout,
                           jsbsim_check=jsbsim_check, options=options)

    @tool(name="cost_estimate", annotations=_ann(True, "Top-down cost (Eastlake / DAPCA IV)"))
    async def cost_estimate(We_kg: float, V_H_kt: float, N: int, year: int = 2025,
                            method: Annotated[str, Field(description="eastlake | dapca4 | both")] = "both",
                            power_bhp: Optional[float] = None, n_engines: int = 1,
                            engine_cost: Annotated[Optional[dict], Field(description="{usd, year, source_url}")] = None,
                            avionics_cost: Optional[dict] = None, propeller_cost: Optional[dict] = None,
                            f_comp: Annotated[float, Field(description="composite fraction of the airframe 0..1")] = 0.0,
                            airframe_fraction_of_empty: float = 0.65, n_flight_test: int = 2,
                            eastlake: Optional[dict] = None, dapca: Optional[dict] = None,
                            learning: Annotated[Optional[dict], Field(description="{slope, theory}")] = None,
                            operating: Annotated[Optional[dict], Field(description="OperatingInputs fields")] = None,
                            configuration: Annotated[Optional[list[str]], Field(description=(
                                "unconventional features (e.g. ['blended wing body']); with unmanned/propulsion "
                                "flags the L0 CERs as outside their database"))] = None,
                            unmanned: bool = False,
                            propulsion: Annotated[Optional[str], Field(description=(
                                "piston_prop | turboprop | jet | electric | hybrid ..."))] = None
                            ) -> dict[str, Any]:
        """Unit production cost from empty mass, max speed and quantity (CPI-U escalated), with learning-curve
        factors and an optional operating-cost element build-up. Cost, not price (no profit)."""
        return await _call(T.cost_estimate, We_kg=We_kg, V_H_kt=V_H_kt, N=N, year=year, method=method,
                           power_bhp=power_bhp, n_engines=n_engines, engine_cost=engine_cost,
                           avionics_cost=avionics_cost, propeller_cost=propeller_cost, f_comp=f_comp,
                           airframe_fraction_of_empty=airframe_fraction_of_empty, n_flight_test=n_flight_test,
                           eastlake=eastlake, dapca=dapca, learning=learning, operating=operating,
                           configuration=configuration, unmanned=unmanned, propulsion=propulsion)

    @tool(name="process_options", annotations=_ann(True, "Process options for one part"))
    async def process_options(part: Annotated[dict, Field(description=(
                                  "{name, kind (skin|spar|rib|frame|shell|fitting|fairing…), mass_kg, area_m2, "
                                  "perimeter_m, max_dim_m, thickness_m, count, double_curvature, axisymmetric, "
                                  "n_plies, material}"))],
                              materials: Annotated[dict, Field(description="{key: library key | material dict with "
                                                                           "price + provenance}")],
                              N: int = 100, year: int = 2025, processes: Optional[list[str]] = None,
                              process_inputs: Optional[dict] = None, learning: Optional[dict] = None,
                              tooling_pool: Optional[float] = None) -> dict[str, Any]:
        """Feasibility (material class, envelope, gauge, curvature, rivet rules), hours, B2F, cycle time, tooling
        and unit cost of one part for each material × process at N; the cheapest feasible option is selected."""
        return await _call(T.process_options, part=part, materials=materials, N=N, year=year, processes=processes,
                           process_inputs=process_inputs, learning=learning, tooling_pool=tooling_pool)

    @tool(name="compare_materials", annotations=_ann(True, "Ashby material comparison"))
    async def compare_materials(materials: Annotated[dict, Field(description="{key: library key | material dict "
                                                                             "with price + provenance}")],
                                requirement: Annotated[str, Field(description="tie|beam|panel _stiffness|_strength")]
                                = "panel_stiffness",
                                reference: Optional[str] = None, year: int = 2025,
                                b2f: Optional[dict] = None) -> dict[str, Any]:
        """Relative mass and bought-material cost of candidate materials for one governing requirement (Ashby
        performance indices, equal geometry envelope)."""
        return await _call(T.compare_materials, materials=materials, requirement=requirement, reference=reference,
                           year=year, b2f=b2f)

    # ---------------------------------------------------------------- external data
    @tool(name="validate_material", annotations=_ann(True, "Validate an external material (with source)"))
    async def validate_material(
            material: Annotated[dict, Field(description="{key, name, kind: metal|composite_equivalent|core|wood, "
                                                        "E, G?, nu?, rho, Ftu, Fty?, Fcy?, Fsu?, t_min? (values "
                                                        "'72 GPa' or {value, unit}), provenance: {source_url, "
                                                        "retrieved YYYY-MM-DD, source_type, datasheet?, basis?}}")]
    ) -> dict[str, Any]:
        """Unit conversion, plausibility ranges and consistency checks of researched material data; returns the
        structures-ready dict to pass as size(materials={'structure': ...})."""
        return T.clean(external.validate_material(material))

    @tool(name="validate_component", annotations=_ann(True, "Validate an external component (with source)"))
    async def validate_component(
            category: Annotated[str, Field(description="motors | escs | cells | servos | autopilots")],
            component: Annotated[dict, Field(description="fields of components.yaml for the category + id + "
                                                         "provenance {source_url, retrieved, source_type, ...}")]
    ) -> dict[str, Any]:
        """Validate a researched component (units, ranges, specific energy/power) for systems.components."""
        return T.clean(external.validate_component(category, component))

    # ---------------------------------------------------------------- registry
    @tool(name="list_examples", annotations=_ann(True, "List example missions"))
    async def list_examples() -> dict[str, Any]:
        """Example mission specs shipped with acdt (usable as templates: example=<name>)."""
        return T.list_examples()

    @tool(name="get_run", annotations=_ann(True, "Get a run record"))
    async def get_run(run_id: str, include: Optional[list[str]] = None) -> dict[str, Any]:
        """Run record: inputs, assumptions with sources, versions, git hash, outputs, files, calibration,
        external data provenance."""
        return T.get_run(run_id, include)

    @tool(name="list_runs", annotations=_ann(True, "List runs"))
    async def list_runs(tool: Optional[str] = None, limit: int = 50) -> dict[str, Any]:
        """Runs in the registry (newest first), optionally filtered by tool."""
        return T.list_runs(tool, limit)

    @tool(name="compare_runs", annotations=_ann(True, "Compare runs"))
    async def compare_runs(run_ids: list[str], metrics: Optional[list[str]] = None) -> dict[str, Any]:
        """Differences of numeric outputs (relative change vs the first run) and of the assumptions."""
        return T.compare_runs(run_ids, metrics)

    @tool(name="get_calibration", annotations=_ann(True, "Read calibration factors"))
    async def get_calibration(run_id: Optional[str] = None, path: Optional[str] = None) -> dict[str, Any]:
        """Calibration factors (L3 → L1/L2) of a hifi run or a calibration.json."""
        return T.get_calibration(run_id, path)

    @tool(name="apply_calibration", annotations=_ann(False, "Set calibration on a design"))
    async def apply_calibration(spec: Src["spec"] = None, spec_path: Src["spec_path"] = None,
                                run_id: Src["run_id"] = None, example: Src["example"] = None,
                                calibration_run: Optional[str] = None, calibration_file: Optional[str] = None,
                                apply: Annotated[Optional[list[str]], Field(description="groups: aero, flutter")] = None,
                                factors: Optional[dict] = None) -> dict[str, Any]:
        """Attach calibration (file and/or inline factors; groups to apply) to a design → new run_id to size."""
        return await _call(T.apply_calibration, spec=spec, spec_path=spec_path, run_id=run_id, example=example,
                           calibration_run=calibration_run, calibration_file=calibration_file, apply=apply,
                           factors=factors)

    @tool(name="generate_report", annotations=_ann(False, "Design dossier over runs"))
    async def generate_report(run_ids: list[str], title: str = "acdt design dossier",
                              notes: Optional[str] = None) -> dict[str, Any]:
        """Markdown + JSON dossier: runs, key results, assumptions and sources, external data, calibration,
        validity limits, links to the full reports."""
        return await _call(T.report, run_ids, title, notes)

    @tool(name="get_reference", annotations=_ann(True, "Reference data / methods / docs"))
    async def get_reference(
            kind: Annotated[str, Field(description="methods | materials | components | standards | docs | "
                                                   "doc:<name> | agents-guide")]) -> dict[str, Any]:
        """Same content as the resources, for clients without resource support."""
        return {"kind": kind, "content": _reference(kind)}

    # ---------------------------------------------------------------- resources
    @srv.resource("acdt://methods", name="methods", mime_type="application/json",
                  description="Methods catalogue with the citations of each module + workflow map")
    def r_methods() -> str:
        return json.dumps(catalogue.methods(), ensure_ascii=False)

    @srv.resource("acdt://materials", name="materials", mime_type="application/json",
                  description="Small cited reference material library (SI)")
    def r_materials() -> str:
        return json.dumps(T.clean(catalogue.materials()), ensure_ascii=False)

    @srv.resource("acdt://components", name="components", mime_type="application/json",
                  description="Example component DB (generic classes; verify datasheets)")
    def r_components() -> str:
        return json.dumps(T.clean(catalogue.components()), ensure_ascii=False)

    @srv.resource("acdt://standards", name="standards", mime_type="application/json",
                  description="Standards / regulations referenced by the compliance checklist")
    def r_standards() -> str:
        return json.dumps(T.clean(catalogue.standards()), ensure_ascii=False)

    @srv.resource("acdt://capabilities", name="capabilities", mime_type="text/markdown",
                  description="What acdt can do today, per area (methods, fidelity, CLI/MCP, limits), roadmap and "
                              "suggested capabilities (CAPABILITIES.md, Portuguese)")
    def r_capabilities() -> str:
        return catalogue.doc("CAPABILITIES")

    @srv.resource("acdt://agents-guide", name="agents-guide", mime_type="text/markdown",
                  description="Rules and workflow for AI agents (AGENTS.md + docs/ai-agent-guide.md)")
    def r_guide() -> str:
        return _reference("agents-guide")

    @srv.resource("acdt://docs/{name}", name="docs", mime_type="text/markdown",
                  description="Repository docs (README, ARCHITECTURE, tutorials, ai-agent-guide, THIRD_PARTY)")
    def r_doc(name: str) -> str:
        return catalogue.doc(name)

    @srv.resource("acdt://runs/{run_id}", name="run", mime_type="application/json",
                  description="A run record of the registry")
    def r_run(run_id: str) -> str:
        return json.dumps(T.get_run(run_id), ensure_ascii=False)

    # ---------------------------------------------------------------- prompts
    @srv.prompt(name="design_from_requirements", description="Full design workflow from a plain-language request")
    def design_from_requirements(description: str, constraints: str = "") -> str:
        return PROMPT_DESIGN.format(description=description, constraints=constraints or "(none stated)")

    @srv.prompt(name="research_component", description="Research a current component/material with sources")
    def research_component(need: str, category: str = "motors") -> str:
        return PROMPT_RESEARCH.format(need=need, category=category)

    @srv.prompt(name="hifi_verification", description="Plan and request approval for high-fidelity verification")
    def hifi_verification(run_id: str) -> str:
        return PROMPT_HIFI.format(run_id=run_id)

    from . import concept_mcp      # concept trade: free-text problem → mission, requirements, architectures
    concept_mcp.register(srv, _ann, _call)
    from . import assembly_mcp     # P1: generic component geometry + integration (packaging / FOV) checker
    assembly_mcp.register(srv, _ann, _call)
    from . import morph_mcp        # P2: morphological N1 generate / evaluate / prune
    morph_mcp.register(srv, _ann, _call)
    from . import systems_p4_mcp  # P4: electrical + payload trade
    systems_p4_mcp.register(srv, _ann, _call)
    from . import decisions_mcp  # P5: decision log
    decisions_mcp.register(srv, _ann, _call)
    from . import sensitivity_mcp  # P7: sensitivity / fidelity-by-need
    sensitivity_mcp.register(srv, _ann, _call)
    from . import shape_n2_mcp  # P6 light N2 shape
    shape_n2_mcp.register(srv, _ann, _call)
    from . import vtol_mcp  # VTOL / eVTOL L0
    vtol_mcp.register(srv, _ann, _call)
    from . import bemt_mcp  # opt-in lightweight BEMT + Drela motor deck
    bemt_mcp.register(srv, _ann, _call)
    from . import rib_simp_mcp  # opt-in SIMP rib-web mass in the structural budget
    rib_simp_mcp.register(srv, _ann, _call)
    from . import jet_mcp  # Subsonic jet transport L0
    jet_mcp.register(srv, _ann, _call)
    from . import storage_mcp  # Common energy-storage balances, not a simulator replacement
    storage_mcp.register(srv, _ann, _call)
    from . import onboard_mcp
    onboard_mcp.register(srv, _ann, _call)
    from . import mission_fleet_mcp
    mission_fleet_mcp.register(srv, _ann, _call)
    return srv


def _reference(kind: str):
    if kind == "methods":
        return catalogue.methods()
    if kind == "materials":
        return T.clean(catalogue.materials())
    if kind == "components":
        return T.clean(catalogue.components())
    if kind == "standards":
        return T.clean(catalogue.standards())
    if kind == "docs":
        return {k: str(v) for k, v in catalogue.docs().items()}
    if kind == "agents-guide":
        parts = []
        for n in ("AGENTS", "ai-agent-guide"):
            try:
                parts.append(catalogue.doc(n))
            except KeyError:
                pass
        return "\n\n---\n\n".join(parts) or INSTRUCTIONS
    if kind.startswith("doc:"):
        return catalogue.doc(kind[4:])
    raise T.ToolError("kind: methods | materials | components | standards | docs | doc:<name> | agents-guide")


PROMPT_DESIGN = """Design an aircraft with acdt for this request:

{description}

Constraints / preferences: {constraints}

Follow acdt://agents-guide. In order:
1. requirements_schema; translate the request into a mission spec (requirements with units; aircraft_class;
   only assumptions you can cite — put the citation in assumption_sources). Ask the user when a requirement is
   ambiguous instead of guessing. validate_requirements → fix errors.
2. size(level='L0') then size(level='L1'); read failed_checks/issues; iterate the spec (cite every change).
3. If electric UAV: systems. For real components/materials, research current datasheets on the web (credible
   sources, date them) and pass them through validate_component / validate_material.
4. optimize (MDO) with the objective from the requirements; compare_runs baseline vs optimum.
5. wingbox phase 5, then phase 6 (run_id of phase 5). rcs only if signature is a requirement.
6. hifi_estimate; heavy steps ONLY after the user explicitly approves (they use this machine's CPU/RAM).
7. generate_report over the run ids; answer with: the design (numbers from the tools only), what is assumed,
   validity limits, failed checks, next steps."""

PROMPT_RESEARCH = """Research current data for: {need} (acdt category: {category}).
Use credible sources (manufacturer datasheet first; MMPDS / CMH-17 for allowables; standards; peer-reviewed).
For each candidate record source_url, retrieved date (today), source_type, datasheet revision, and the values
with units. Validate each with validate_component (or validate_material) and fix/flag every issue. Do not
fill gaps with guesses: leave the optional field out (acdt flags the default it uses) or say it is missing."""

PROMPT_HIFI = """Plan the high-fidelity verification of run {run_id}.
1. hifi_estimate (all steps) and show the user the table: light steps, heavy steps with the measured times, the
   machine (cores, free RAM) and that the full RANS is only written as a case.
2. Ask the user for explicit approval of the heavy steps (and on which machine). Without it run only the light
   steps (hifi with those steps).
3. After approval: hifi(run_id={run_id}, steps=..., user_approved=true, approval_note=<their words>).
4. get_calibration → apply_calibration (groups the user agrees with) → size again → compare_runs."""


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="acdt mcp", description="acdt MCP server")
    ap.add_argument("--http", action="store_true", help="streamable HTTP instead of stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--path", default="/mcp")
    a = ap.parse_args(argv)
    srv = build_server()
    if not a.http:
        srv.run("stdio")
        return 0
    try:   # SDK v2: transport options in run()
        srv.run("streamable-http", host=a.host, port=a.port, streamable_http_path=a.path)
    except TypeError:   # SDK v1: options in settings
        srv.settings.host, srv.settings.port, srv.settings.streamable_http_path = a.host, a.port, a.path
        srv.run("streamable-http")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
