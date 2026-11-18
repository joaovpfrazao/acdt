"""MCP registration for morphological N1 tools."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import Field

from . import morph as M


def register(srv, ann, call) -> None:
    tool = srv.tool

    @tool(name="morph_matrix", annotations=ann(True, "Open morphological seed matrix (Zwicky)"))
    async def morph_matrix(
            extra: Annotated[Optional[dict], Field(description="{dimension: [options...]} to add")] = None
    ) -> dict[str, Any]:
        """Return the open N1 seed matrix. Add options freely; seeds are not a closed list."""
        return M.morph_matrix(extra)

    @tool(name="morph_generate", annotations=ann(True, "Combine matrix and cut incompatibilities"))
    async def morph_generate(
            dimensions: Annotated[Optional[dict], Field(
                description="override/extend {dim: [opts]} — opts may be str or {id,source,…}"
            )] = None,
            use_dimensions: Annotated[Optional[list[str]], Field(description="subset of dimensions")] = None,
            max_combinations: int = 200,
    ) -> dict[str, Any]:
        """Cartesian product + physical incompatibility cuts with written reasons."""
        return M.morph_generate(dimensions=dimensions, use_dimensions=use_dimensions,
                                max_combinations=max_combinations,
                                seeds=dimensions is None)

    @tool(name="morph_evaluate", annotations=ann(False, "Size + point-mass + P4 energy/comms assess"))
    async def morph_evaluate(
            architectures: Annotated[list, Field(description="list of {id, choices, option_meta?}")],
            mission: Annotated[str, Field(description="base mission YAML for size")],
            sim: Annotated[Optional[str], Field(description="point-mass mission YAML (judge)")] = None,
            level: str = "L0",
            limit: Annotated[Optional[int], Field(description="max architectures to run")] = 12,
            hybrid_templates: Annotated[Optional[dict], Field(
                description="{energy_id: hybrid_dispatch block with source}"
            )] = None,
            link_catalog: Annotated[Optional[dict], Field(
                description="{link_id: {power_W, mass_kg?, source, retrieved?}}"
            )] = None,
            mission_context: Annotated[Optional[dict], Field(
                description="hybrid context {distance_km, speed_m_s, station_h}"
            )] = None,
            operating_cost: Annotated[Optional[dict], Field(
                description="DOC inputs (Raymer 2018 Ch. 18); optional eastlake/dapca or unit_price_from=size"
            )] = None,
    ) -> dict[str, Any]:
        """Low-fi evaluate. Missing hybrid/comms source → unassessed_axes (never silent pass).
        Optional operating_cost attaches cost_per_fh when status=ok (unassessed≠zero)."""
        return await call(M.morph_evaluate, architectures, mission, sim, level, limit,
                          hybrid_templates, link_catalog, mission_context, operating_cost)

    @tool(name="morph_prune", annotations=ann(True, "Set-based prune with N1 uncertainty band"))
    async def morph_prune(
            rows: Annotated[list, Field(description="evaluate rows with metrics")],
            band: float = 0.15,
            keep: int = 3,
            objectives: Annotated[Optional[dict], Field(description="{metric: min|max}")] = None,
    ) -> dict[str, Any]:
        """Keep 2–3 alive; cut only when clearly dominated inside the N1 band (Sobek/Ward/Liker 1999)."""
        return M.morph_prune(rows, band=band, keep=keep, objectives=objectives)
