# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Shared opt-in payload/electrical coupling, not a global MDA or hybrid dispatch."""
from typing import Any
from . import onboard as O


def register(srv, ann, call):
    tool = srv.tool

    @tool(name="onboard_size",annotations=ann(False,"Cross-aircraft payload / electrical sizing coupling"))
    async def onboard_size(spec: Any, record: bool=True) -> dict[str,Any]:
        """Versioned recipe: schema_version=1.0, model prop|jet|vtol|hybrid,
        aircraft native input mapping, onboard common versioned inventory/sources/loads.
        Runs native sizing with owned masses and actual hotel energy/fuel/extraction.
        Missing extraction models stop as unassessed (no free electricity). VTOL MTOW
        is inclusive and fixed. Hybrid accounting only. Optional closure screens thermal/CG/spatial/FOV with open primitives; Spatial/thermal/CG limitations
        and composite tri-state checks remain explicit. No certification claim."""
        return await call(O.onboard_size,spec,record)
