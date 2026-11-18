# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""MCP registration for VTOL / eVTOL L0."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import Field

from . import vtol as V


def register(srv, ann, call) -> None:
    tool = srv.tool

    @tool(name="vtol_hover", annotations=ann(True, "VTOL hover power (momentum theory)"))
    async def vtol_hover(
            mass_kg: Annotated[float, Field(description="vehicle mass [kg]")],
            n_rotors: Annotated[int, Field(description="number of equal lift rotors")] = 4,
            diameter_m: Annotated[Optional[float], Field(description="rotor diameter [m]")] = None,
            disk_loading_N_m2: Annotated[Optional[float], Field(description="disk loading if no diameter")] = None,
            FM: Annotated[float, Field(description="figure of merit (PRESSUPOSTO 0.70)")] = 0.70,
            altitude_m: float = 0.0,
            download_factor: float = 1.0,
            bemt: dict | None = None,
    ) -> dict[str, Any]:
        """P_ideal = T^1.5/sqrt(2 rho A), P = P_ideal/FM, DL, v_i, tip/blade-loading limits (Johnson 1980 Ch. 2).

        Optional ``bemt`` geometry/polar runs axial BEMT and, when assessed, replaces shaft power and FM.
        Unassessed BEMT leaves momentum numbers marked as such (unassessed≠pass)."""
        return await call(V.vtol_hover, mass_kg, n_rotors, diameter_m, disk_loading_N_m2, FM, altitude_m,
                          download_factor, bemt)

    @tool(name="vtol_size", annotations=ann(True, "VTOL/eVTOL L0 sizing for one architecture"))
    async def vtol_size(
            spec: Annotated[Any, Field(description="spec dict or JSON/YAML path (architecture, mass_kg, rotors, "
                                                   "mission, cruise, transition, electric); or, instead of mass_kg, "
                                                   "an opt-in closure block {mass_bounds_kg, components, fixed_items}")],
    ) -> dict[str, Any]:
        """Hover/climb/transition/cruise energy, battery mass (energy vs power limited), margins, PRESSUPOSTOs.

        Opt-in ``closure`` solves MTOW from components (NDARC AFDD00 rotors, NASA15 motors, sourced fractions/masses,
        native battery) by bracketed bisection; reports closure.status/history/residual; missing component ≠ zero."""
        return await call(V.vtol_size, spec)

    @tool(name="vtol_compare", annotations=ann(True, "Compare multirotor / lift+cruise / tilt-rotor"))
    async def vtol_compare(
            spec: Annotated[Any, Field(description="spec dict or JSON/YAML path (mass + mission)")],
            architectures: Annotated[Optional[list], Field(description="subset of architectures")] = None,
            overrides: Annotated[Optional[dict], Field(description="{arch: partial spec}")] = None,
    ) -> dict[str, Any]:
        """Same mass and mission across architectures; ranks by battery mass."""
        return await call(V.vtol_compare, spec, architectures, overrides)
