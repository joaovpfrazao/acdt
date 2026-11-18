# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""MCP registration for opt-in SIMP rib-web mass in the structural budget."""
from __future__ import annotations

from typing import Any

from . import rib_simp as R


def register(srv, ann, call):
    tool = srv.tool

    @tool(name="rib_simp_mass", annotations=ann(True, "Opt-in SIMP rib-web mass in the box budget"))
    async def rib_simp_mass(spec: dict[str, Any]) -> dict[str, Any]:
        """2-D SIMP (Bendsøe/Sigmund) mass of the rib web, fed into the Phase 6 budget when masses+ribs
        are supplied. Volume fraction, thickness source and material density source are required.
        Missing inputs → unassessed; sized size_ribs masses are not presented as a SIMP result.
        Lightweight Q4 plane-stress only — not TACS, ADflow, or nonlinear FEM."""
        return await call(R.rib_simp_mass, spec)
