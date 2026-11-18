"""MCP registration for P4 electrical architecture and payload catalog trade."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import Field

from . import systems_p4 as S


def register(srv, ann, call) -> None:
    tool = srv.tool

    @tool(name="electrical_catalog", annotations=ann(True, "Example generators / avionics batteries / payloads"))
    async def electrical_catalog(
            path: Annotated[Optional[str], Field(description="YAML override (payloads.yaml shape)")] = None,
    ) -> dict[str, Any]:
        """Return EXAMPLE generators, batteries_avionics and payloads. Prefer researched rows with source+date."""
        return await call(S.electrical_catalog, path)

    @tool(name="electrical_analyse", annotations=ann(True, "MIL-E-7016F load vs generation/battery capacity"))
    async def electrical_analyse(
            architecture: Annotated[dict, Field(description="id, generation_ids|generation, battery_ids|batteries, "
                                                            "loads[{name,power_w,duty?,peak_w?,bus?}], payload_ids?, "
                                                            "endurance_h?, margins?")],
            catalog_path: Annotated[Optional[str], Field(description="YAML catalog path")] = None,
    ) -> dict[str, Any]:
        """Average/peak load analysis, generation and battery capacity with N1 margins (MIL-E-7016F)."""
        return await call(S.electrical_analyse, architecture, catalog_path)

    @tool(name="payload_catalog", annotations=ann(True, "Payload EXAMPLE catalog (mass/power/volume/FOV)"))
    async def payload_catalog(
            path: Annotated[Optional[str], Field(description="YAML override")] = None,
            extra: Annotated[Optional[list], Field(description="researched rows prepended (source+retrieved)")] = None,
    ) -> list:
        """List payload options. Built-in rows are EXAMPLE DATA — replace with live datasheets."""
        return await call(S.payload_catalog, path, extra)

    @tool(name="payload_trade", annotations=ann(True, "Pareto trade on payload catalog"))
    async def payload_trade(
            payloads: Annotated[Optional[list], Field(description="rows to compare; default = catalog (+extra)")] = None,
            catalog_path: Annotated[Optional[str], Field(description="YAML catalog")] = None,
            extra: Annotated[Optional[list], Field(description="researched rows to prepend")] = None,
            objectives: Annotated[Optional[dict], Field(description="{metric: min|max}")] = None,
            constraints: Annotated[Optional[dict], Field(description="{metric: {min?, max?}}")] = None,
            kinds: Annotated[Optional[list[str]], Field(description="filter kind: eo_ir|radar|ais|esm|…")] = None,
    ) -> dict[str, Any]:
        """Pareto set on mass / power / FOV (defaults). Does not pick a winner."""
        return await call(S.payload_trade, payloads, catalog_path, extra, objectives, constraints, kinds)

    @tool(name="cost_per_flight_hour", annotations=ann(True, "Simple €/h aggregation (user prices)"))
    async def cost_per_flight_hour(
            fuel_or_energy_per_h: Annotated[float, Field(description="kg/h or kWh/h matching unit_price")],
            unit_price: Annotated[float, Field(description="€/kg or €/kWh (user input)")],
            maintenance_per_h: float = 0.0,
            other_per_h: float = 0.0,
    ) -> dict[str, Any]:
        """Direct sum of energy + maintenance + other. Prices are user inputs (PRESSUPOSTO)."""
        return await call(S.cost_per_flight_hour, fuel_or_energy_per_h, unit_price,
                          maintenance_per_h, other_per_h)


    @tool(name="operational_cost", annotations=ann(True, "DOC €/h Raymer 2018; Eastlake/DAPCA unit_price"))
    async def operational_cost(
            operating: Annotated[dict, Field(description="OperatingInputs fields + optional eastlake/dapca4 "
                                                         "CER block for unit_price; sources{}; profile elements|full")],
    ) -> dict[str, Any]:
        """Direct operating cost per FH. Missing wage/fuel/utilization/CER → unassessed (never silent zero)."""
        return await call(S.operational_cost, operating)

