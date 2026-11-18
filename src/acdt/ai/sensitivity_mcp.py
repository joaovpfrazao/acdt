"""MCP registration for P7 sensitivity."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import Field

from . import sensitivity as S


def register(srv, ann, call) -> None:
    tool = srv.tool

    @tool(name="sensitivity_from_samples", annotations=ann(True, "OAT elasticities from samples"))
    async def sensitivity_from_samples(
            baseline: Annotated[dict, Field(description="{metric: number} at nominal")],
            samples: Annotated[list, Field(description="[{variable, x0, x1, metrics}]")],
            threshold: Annotated[float, Field(description="|ε| for fidelity hints")] = 0.5,
    ) -> dict[str, Any]:
        """Local elasticities ε=(Δy/y)/(Δx/x) + fidelity-by-need hints (DESIGN_WORKFLOW §5)."""
        return await call(S.sensitivity_from_samples, baseline, samples, threshold)

    @tool(name="sensitivity_pipeline", annotations=ann(False, "OAT via size pipeline (handbook)"))
    async def sensitivity_pipeline(
            mission: Annotated[str, Field(description="mission YAML path")],
            variables: Annotated[list, Field(description="[{path, rel_step?}] dotted paths")],
            rel_step: float = 0.05,
            no_systems: bool = True,
            handbook: bool = True,
            threshold: float = 0.5,
            output: Annotated[Optional[str], Field(description="folder for sensitivity.json")] = None,
    ) -> dict[str, Any]:
        """Perturb assumption/requirement paths, re-size L0 handbook, rank elasticities."""
        return await call(S.sensitivity_pipeline, mission, variables, rel_step, no_systems,
                          handbook, threshold, output)

    @tool(name="sensitivity_sobol", annotations=ann(False, "Sobol S1/ST global sensitivity (opt-in)"))
    async def sensitivity_sobol(
            evaluate_table: Annotated[Optional[dict], Field(
                description="Y_A, Y_B, Y_AB or evaluations+metric+names"
            )] = None,
            mission: Annotated[Optional[str], Field(description="mission YAML for handbook pipeline")] = None,
            variables: Annotated[Optional[list], Field(
                description="[{path, low?, high?, rel_span?}] for pipeline"
            )] = None,
            n: Annotated[int, Field(description="Saltelli N (total evals N*(k+2))")] = 32,
            metric: str = "W0_kg",
            seed: int = 0,
            bootstrap: Annotated[int, Field(description="0=point estimates; >0 percentile CIs")] = 0,
            conf: float = 0.95,
            no_systems: bool = True,
            handbook: bool = True,
            rel_span: float = 0.10,
    ) -> dict[str, Any]:
        """Saltelli/Jansen Sobol' indices. Missing/degenerate → unassessed (never silent zero)."""
        return await call(
            S.sensitivity_sobol,
            evaluate_table=evaluate_table,
            n=n,
            seed=seed,
            bootstrap=bootstrap,
            conf=conf,
            mission=mission,
            variables=variables,
            metric=metric,
            no_systems=no_systems,
            handbook=handbook,
            rel_span=rel_span,
        )

    @tool(name="sensitivity_mc", annotations=ann(False, "Monte Carlo / LHS UQ (opt-in)"))
    async def sensitivity_mc(
            inputs: Annotated[Optional[list], Field(
                description="[{name, dist, low, high, …}] uniform|triangular|normal"
            )] = None,
            mission: Annotated[Optional[str], Field(description="mission YAML for handbook UQ")] = None,
            evaluate_table: Annotated[Optional[dict], Field(
                description="precomputed {samples:[{inputs,metrics,ok?}]}"
            )] = None,
            n: int = 64,
            method: Annotated[str, Field(description="lhs|mc")] = "lhs",
            seed: int = 0,
            percentiles: Annotated[Optional[list], Field(description="e.g. [5,50,95]")] = None,
            metric_keys: Annotated[Optional[list[str]], Field(description="subset of metrics")] = None,
            no_systems: bool = True,
            handbook: bool = True,
    ) -> dict[str, Any]:
        """Propagate input distributions; missing/failed → unassessed (never silent zero)."""
        return await call(
            S.sensitivity_mc,
            inputs,
            evaluate_table=evaluate_table,
            mission=mission,
            n=n,
            method=method,
            seed=seed,
            percentiles=percentiles,
            metric_keys=metric_keys,
            no_systems=no_systems,
            handbook=handbook,
        )
