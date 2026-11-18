# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in N0→N1 mission fleet feedback, without changing legacy size_fleet."""
from typing import Any
from . import mission_fleet as M


def register(srv,ann,call):
    tool=srv.tool

    @tool(name="mission_fleet_study",annotations=ann(False,"Mission propulsion fleet feedback over explicit candidates"))
    async def mission_fleet_study(spec: Any,record: bool=True) -> dict[str,Any]:
        """Versioned study: mission envelope + explicit samples, operations, open
        candidates with N0 intervals and onboard recipes, explicit objectives.
        Runs existing prop/onboard pointmass, jet/onboard range integration or
        VTOL/onboard segments; consumption feeds explicit ground service and
        homogeneous fleet recalculation. Unknown energy/capacity cannot enter
        assessed Pareto frontier. No maximum-endurance optimization, autonomous
        architecture search, mixed fleet, queues, hybrid dispatch or fixed-point
        convergence. Missing/unsupported alternatives retained, not discarded.
        schema_version 1.1 (opt-in): derived maximum station time of the fixed
        sized design, upward sizing↔capability closure for prop/jet (and VTOL with
        opt-in aircraft.closure component mass closure) with residual
        history, explicit operational_reserve replacing native fractions once,
        dwell_policy requested|derived_max. No fleet→design loop is invented.
        schema_version 1.2 (opt-in): operations.ground_resources pools + candidate
        ground_process → deterministic DES FIFO queues, fleet↔ground-time loop with
        history, resource_saturated/minimum_stable_counts; no stochastic queues.
        Optional mixed_fleet: bounded station-assignment mixes of assessed types,
        optional shared pools in one DES, Pareto per objective, no weighted winner.
        Hybrid candidates with supplied aircraft.hybrid components run L0 rule-based
        dispatch (series thermostat/load_following, parallel power_split); otherwise
        unassessed. n1.mission_phases + mission.required_phases flag unmodelled phases."""
        return await call(M.mission_fleet_study,spec,record)
