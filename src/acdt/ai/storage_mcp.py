# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""MCP registration for common storage accounting (not a mission simulator)."""
from typing import Any
from . import storage as S


def register(srv, ann, call):
    @srv.tool(name="storage_check", annotations=ann(False, "Common L0 fuel/battery storage screen"))
    async def storage_check(spec: Any, source_kind: str = "direct", result: dict[str, Any] | None = None,
                            reserve_fraction: float | None = None, record: bool = True) -> dict[str, Any]:
        """Common fuel/battery capacity and scalar allocated-volume screen. spec has
        storage and (for direct) demand with explicit trip/reserve kg or pack-terminal Wh.
        source_kind=jet_size|vtol_size|mission consumes an existing result; NOT full
        jet/VTOL dynamic simulator support. Mission needs explicit reserve_fraction;
        others already contain reserve. Pack Wh/L is never cell Wh/L. Missing data
        stays unassessed. Does not add inventory mass again or invent hybrid dispatch."""
        return await call(S.storage_check, spec, source_kind, result, reserve_fraction, record)
