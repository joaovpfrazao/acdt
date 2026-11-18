"""MCP registration for P6 light N2 shape study."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import Field

from . import shape_n2 as S


def register(srv, ann, call) -> None:
    tool = srv.tool

    @tool(name="shape_bounds", annotations=ann(True, "N2 shape design-variable bounds"))
    async def shape_bounds() -> dict:
        """Extended Shape bounds (sweep, chine, wing z, L/D scales, sensor station)."""
        return await call(S.shape_bounds)

    @tool(name="shape_n2_study", annotations=ann(False, "Light N2 aero/RCS/packaging LHS"))
    async def shape_n2_study(
            result_json: Annotated[str, Field(description="sized result.json path")],
            output: Annotated[str, Field(description="output folder")],
            n_samples: int = 40,
            seed: int = 0,
            payload: Annotated[Optional[dict], Field(description="{volume_l, mass_kg?, …}")] = None,
    ) -> dict[str, Any]:
        """Latin-hypercube over OML vars; Pareto perf / RCS / pack_score. No RANS (Grok Build)."""
        return await call(S.shape_n2_study, result_json, output, n_samples, seed, payload)

    @tool(name="shape_packaging_score", annotations=ann(True, "Heuristic volume/FOV packaging score"))
    async def shape_packaging_score(
            L: float, D: float, x_wing_le: float, sensor_x: float,
            payload: Annotated[Optional[dict], Field(description="{volume_l}")] = None,
    ) -> dict:
        return await call(S.shape_packaging_score, L, D, x_wing_le, sensor_x, payload)
