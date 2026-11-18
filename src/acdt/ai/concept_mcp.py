"""MCP registration of the concept-trade tools (:mod:`acdt.ai.concept`) and the ``concept_trade`` prompt.

Kept apart from :mod:`acdt.ai.mcp_server` so the concept layer stays additive; ``build_server`` calls
:func:`register`."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Optional

from pydantic import Field

from . import concept as C

PROMPT_FILE = Path(__file__).with_name("prompts") / "concept_trade.md"
Sid = Annotated[Optional[str], Field(description="concept study id (concept_study_start) — logs the call and result "
                                                  "in the audit trail")]


def prompt_text(problem: str, context: str = "") -> str:
    return PROMPT_FILE.read_text(encoding="utf-8").replace("{problem}", problem).replace(
        "{context}", context or "(nenhum)")


def register(srv, ann, call) -> None:
    tool = srv.tool

    @tool(name="concept_study_start", annotations=ann(False, "Open a concept study (audit trail)"))
    async def concept_study_start(
            title: str,
            problem: Annotated[str, Field(description="the user's problem in their own words (free text)")],
            output_dir: Optional[str] = None) -> dict[str, Any]:
        """Start an AI-driven conceptual study. YOU (the agent) define the mission, requirements and alternatives;
        the tools only calculate. Read the prompt `concept_trade` (or docs/ai-concept-trade.md) for the
        workflow. Returns study_id: pass it to every calculation so the trail is recorded."""
        return C.study_start(title, problem, output_dir)

    @tool(name="concept_study_add", annotations=ann(False, "Add reasoning to a concept study"))
    async def concept_study_add(
            study_id: str,
            kind: Annotated[str, Field(description="interpretation | assumption | question | requirement | "
                                                   "alternative | source | finding | recommendation | note")],
            content: Annotated[Any, Field(description="text or dict. assumption {text, rationale, source?} "
                                                      "(it is a PRESSUPOSTO); requirement {text, metric, threshold, "
                                                      "justification}; alternative {id, text, evaluable, how|reason}; "
                                                      "source {text, url, retrieved}; recommendation {text, chosen, "
                                                      "rationale, sensitivities, not_evaluated, next_steps}")]
    ) -> dict[str, Any]:
        """Record the agent's reasoning (what was assumed and why, derived requirements, every alternative
        considered — including those acdt cannot size yet, flagged evaluable=false — sources researched)."""
        return C.study_add(study_id, kind, content)

    @tool(name="concept_study_report", annotations=ann(False, "Write the concept study report"))
    async def concept_study_report(study_id: str) -> dict[str, Any]:
        """Write report.md + study.json (requirements, assumptions, alternatives, comparisons with Pareto plot,
        recommendation, every tool call). Lists completeness gaps."""
        return C.study_report(study_id)

    @tool(name="geo_measure", annotations=ann(True, "Great-circle distances and polygon area"))
    async def geo_measure(points: Annotated[Optional[dict], Field(description="{name: [lat_deg, lon_deg]}")] = None,
                          legs: Annotated[Optional[list], Field(description="[[from, to], ...] point names")] = None,
                          polygon: Annotated[Optional[list], Field(description="[[lat, lon], ...] area")] = None,
                          study_id: Sid = None) -> dict[str, Any]:
        """Haversine distances (Sinnott 1984) and spherical polygon area (Chamberlain & Duquette 2007)."""
        return C.geo_measure(points=points, legs=legs, polygon=polygon, study_id=study_id)

    @tool(name="transit_time", annotations=ann(True, "Transit time with wind"))
    async def transit_time(distance_km: float, airspeed_m_s: float, headwind_m_s: float = 0.0,
                           study_id: Sid = None) -> dict[str, Any]:
        """Outbound / return / round-trip transit time [h] with a steady along-track wind."""
        return C.transit_time(distance_km=distance_km, airspeed_m_s=airspeed_m_s, headwind_m_s=headwind_m_s,
                              study_id=study_id)

    @tool(name="sweep_coverage", annotations=ann(True, "Search sweep rate, revisit and POD"))
    async def sweep_coverage(area_km2: float,
                             sweep_width_km: Annotated[float, Field(description="effective sweep width for the "
                                                                                "target class (datasheet)")],
                             speed_m_s: float, n_on_station: float = 1.0, time_h: Optional[float] = None,
                             pod_target: Optional[float] = None, study_id: Sid = None) -> dict[str, Any]:
        """Sweep rate W·V, time to sweep the area once, POD after time_h (Koopman random search / parallel
        sweep) and the time to reach pod_target."""
        return C.sweep_coverage(area_km2=area_km2, sweep_width_km=sweep_width_km, speed_m_s=speed_m_s,
                                n_on_station=n_on_station, time_h=time_h, pod_target=pod_target, study_id=study_id)

    @tool(name="persistent_coverage", annotations=ann(True, "Fleet for continuous presence"))
    async def persistent_coverage(
            endurance_h: float, turnaround_h: float, distance_km: Optional[float] = None,
            airspeed_m_s: Optional[float] = None, headwind_m_s: float = 0.0, t_out_h: Optional[float] = None,
            t_back_h: Optional[float] = None, reserve_h: float = 0.0, handoff_overlap_h: float = 0.0,
            n_stations: int = 1,
            availability: Annotated[Any, Field(description="number in (0,1] or {mtbf_h, mttr_h} or "
                                                           "{mtbm_h, mdt_h}")] = 1.0,
            confidence: Optional[float] = None, fleet_size: Optional[int] = None,
            study_id: Sid = None) -> dict[str, Any]:
        """Time on station, aircraft per station (Ha 2010 cyclic schedule), fleet needed with availability
        (expected and for a confidence, binomial), presence of a given fleet."""
        return C.persistent_coverage(endurance_h=endurance_h, turnaround_h=turnaround_h, distance_km=distance_km,
                                     airspeed_m_s=airspeed_m_s, headwind_m_s=headwind_m_s, t_out_h=t_out_h,
                                     t_back_h=t_back_h, reserve_h=reserve_h, handoff_overlap_h=handoff_overlap_h,
                                     n_stations=n_stations, availability=availability, confidence=confidence,
                                     fleet_size=fleet_size, study_id=study_id)

    @tool(name="barrier_search", annotations=ann(True, "Barrier / barrier-patrol search (Koopman/Washburn)"))
    async def barrier_search(
            barrier_length_km: float,
            speed_m_s: Optional[float] = None,
            sweep_width_km: Annotated[Optional[float], Field(description="effective sweep width for the target "
                                                                          "class (sourced datasheet); omit → POD "
                                                                          "unassessed — do not invent")] = None,
            evader_speed_m_s: Optional[float] = None,
            crossing_window_h: Optional[float] = None,
            corridor_width_km: Optional[float] = None,
            n_on_station: float = 1.0,
            endurance_h: Optional[float] = None,
            turnaround_h: Optional[float] = None,
            distance_km: Optional[float] = None,
            airspeed_m_s: Optional[float] = None,
            headwind_m_s: float = 0.0,
            t_out_h: Optional[float] = None,
            t_back_h: Optional[float] = None,
            reserve_h: float = 0.0,
            handoff_overlap_h: float = 0.0,
            availability: Annotated[Any, Field(description="number in (0,1] or {mtbf_h, mttr_h}")] = 1.0,
            study_id: Sid = None) -> dict[str, Any]:
        """Barrier patrol on a line/corridor the evader must cross: Koopman z=n·W·V/(L·u) POD, reciprocating
        revisit τ=2L/(n·V), cookie-cutter closed when τ≤window; optional Ha 2010 continuous manning.
        Missing speed/sweep width/endurance → unassessed (never silent pass)."""
        return C.barrier_search(barrier_length_km=barrier_length_km, speed_m_s=speed_m_s,
                                sweep_width_km=sweep_width_km, evader_speed_m_s=evader_speed_m_s,
                                crossing_window_h=crossing_window_h, corridor_width_km=corridor_width_km,
                                n_on_station=n_on_station, endurance_h=endurance_h, turnaround_h=turnaround_h,
                                distance_km=distance_km, airspeed_m_s=airspeed_m_s, headwind_m_s=headwind_m_s,
                                t_out_h=t_out_h, t_back_h=t_back_h, reserve_h=reserve_h,
                                handoff_overlap_h=handoff_overlap_h, availability=availability,
                                study_id=study_id)

    @tool(name="radar_horizon", annotations=ann(True, "Radar / optical horizon"))
    async def radar_horizon(h_sensor_m: float, h_target_m: float = 0.0, k: float = 4.0 / 3.0,
                            study_id: Sid = None) -> dict[str, Any]:
        """Horizon range [km] (4/3-earth radar, Skolnik 2001; k=1 geometric)."""
        return C.radar_horizon(h_sensor_m=h_sensor_m, h_target_m=h_target_m, k=k, study_id=study_id)

    @tool(name="sensor_footprint", annotations=ann(True, "Sensor ground footprint"))
    async def sensor_footprint(altitude_m: float, fov_cross_deg: float, fov_along_deg: Optional[float] = None,
                               depression_deg: float = 90.0, study_id: Sid = None) -> dict[str, Any]:
        """Flat-earth nadir swath or oblique near/far range of an imaging sensor."""
        return C.sensor_footprint(altitude_m=altitude_m, fov_cross_deg=fov_cross_deg, fov_along_deg=fov_along_deg,
                                  depression_deg=depression_deg, study_id=study_id)

    @tool(name="johnson_range", annotations=ann(True, "Johnson-criteria range"))
    async def johnson_range(target_dim_m: float, task: str = "detection", ifov_rad: Optional[float] = None,
                            pixel_pitch_um: Optional[float] = None, focal_mm: Optional[float] = None,
                            fov_deg: Optional[float] = None, pixels: Optional[int] = None,
                            study_id: Sid = None) -> dict[str, Any]:
        """Max slant range for detection/orientation/recognition/identification (Johnson 1958, 50 %)."""
        return C.johnson_range(target_dim_m=target_dim_m, task=task, ifov_rad=ifov_rad,
                               pixel_pitch_um=pixel_pitch_um, focal_mm=focal_mm, fov_deg=fov_deg, pixels=pixels,
                               study_id=study_id)

    @tool(name="fleet_reliability", annotations=ann(True, "k-of-N fleet mission success"))
    async def fleet_reliability(n: int, k: int, p_success: Optional[float] = None, p_fail: Optional[float] = None,
                                lambda_per_fh: Optional[float] = None, t_h: Optional[float] = None,
                                confidence: Optional[float] = None, study_id: Sid = None) -> dict[str, Any]:
        """Binomial P(≥ k of n succeed); unit success from p_success, 1−p_fail or exp(−λt)."""
        return C.fleet_reliability(n=n, k=k, p_success=p_success, p_fail=p_fail, lambda_per_fh=lambda_per_fh,
                                   t_h=t_h, confidence=confidence, study_id=study_id)

    @tool(name="size_fleet", annotations=ann(False, "Size and aggregate a fleet of variants"))
    async def size_fleet(
            variants: Annotated[list, Field(description="[{id, spec|spec_path|example|run_id, quantity, level?, "
                                                        "assumptions?, cost?: {N, year?, V_H_kt?, ...cost_estimate}, "
                                                        "safety?: {template?, scheme?, options?}, per_aircraft?: "
                                                        "{metric: value}}]")],
            level: Annotated[Optional[str], Field(description="omit = mission YAML fidelity (same as acdt size); L0=handbook | L1=lowfi override")] = None,
            study_id: Sid = None) -> dict[str, Any]:
        """Size each variant with the same run_pipeline as acdt size and aggregate the fleet (Σ W0/We/power/cost/metrics),
        certification basis and per-sortie loss. Omit level → YAML fidelity (fleet of 1 ≡ acdt size); level=L0|L1 overrides."""
        return await call(C.size_fleet, variants=variants, level=level, study_id=study_id)

    @tool(name="compare_alternatives", annotations=ann(False, "Pareto / multi-criteria comparison"))
    async def compare_alternatives(
            alternatives: Annotated[list, Field(description="[{id, metrics: {name: value}}]")],
            objectives: Annotated[dict, Field(description="{metric: 'min'|'max'}")],
            constraints: Annotated[Optional[dict], Field(description="{metric: {min?, max?}}")] = None,
            weights: Annotated[Optional[dict], Field(description="only if the user/agent justifies them")] = None,
            plot: Annotated[Optional[dict], Field(description="{x, y, labels?, file?}")] = None,
            title: Optional[str] = None, show: Optional[list] = None, study_id: Sid = None) -> dict[str, Any]:
        """Constraint screening + Pareto front (no default weights; a weighted score only if weights are given,
        with each normalised term). With study_id the table and plot go into the study report."""
        return C.compare(alternatives, objectives, constraints, weights, plot, title, show, study_id)

    @srv.prompt(name="concept_trade", description="AI-driven conceptual trade from a free-text problem "
                                                  "(mission, requirements, alternatives, fleet architecture)")
    def concept_trade(problem: str, context: str = "") -> str:
        return prompt_text(problem, context)
