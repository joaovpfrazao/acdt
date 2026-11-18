# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""MCP registration for opt-in lightweight BEMT and the Drela motor deck."""
from __future__ import annotations

from typing import Any

from . import bemt as B


def register(srv, ann, call):
    @srv.tool(name="bemt_propeller", annotations=ann(True, "Opt-in BEMT propeller (systems cycle)"))
    async def bemt_propeller(spec: dict[str, Any]) -> dict[str, Any]:
        """Fixed-pitch BEMT (McCormick 1995 Ch. 6, Ning 2014). Missing geometry or sourced section
        polar → unassessed, never a silent Raymer statistic. Inputs are not vendor maps."""
        return await call(B.bemt_propeller, spec)

    @srv.tool(name="bemt_rotor", annotations=ann(True, "Opt-in axial/hover rotor BEMT"))
    async def bemt_rotor(spec: dict[str, Any]) -> dict[str, Any]:
        """Axial BEMT for one rotor; FM from P_ideal/P_shaft (Leishman 2006). Unassessed if
        geometry or polar is missing. No yawed flight, no rotor–rotor interference."""
        return await call(B.bemt_rotor, spec)

    @srv.tool(name="motor_deck", annotations=ann(True, "Drela 2007 first-order motor deck"))
    async def motor_deck(spec: dict[str, Any]) -> dict[str, Any]:
        """Kv, R, I0 and a source are required. Numeric-only records are not applied
        (unassessed ≠ η=0.85). Out-of-domain I or V is flagged, not clipped."""
        return await call(B.motor_deck, spec)
