# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""MCP registration for subsonic jet transport L0 (analysis aids only)."""
from typing import Any
from . import jet as J


def register(srv, ann, call) -> None:
    @srv.tool(name="jet_wave_drag", annotations=ann(True, "Jet Korn–Mason wave drag L0"))
    async def jet_wave_drag(mach: float, cl: float = 0.5, thickness_ratio: float = 0.12,
                            sweep_deg: float = 25.0, technology_factor: float = 0.95) -> dict[str, Any]:
        """Representative wing: Mcrit, Mdd and Lock drag rise; defaults are PRESSUPOSTO."""
        return await call(J.jet_wave_drag, mach, cl, thickness_ratio, sweep_deg, technology_factor)

    @srv.tool(name="jet_turbofan", annotations=ann(True, "Generic installed turbofan L0"))
    async def jet_turbofan(mach: float, altitude_m: float, thrust_sl_N: float = 120000.0,
                           installation_factor: float = 0.97, throttle_ratio: float = 1.05,
                           tsfc_multiplier: float = 1.0) -> dict[str, Any]:
        """One engine, maximum-rating thrust [N], TSFC [kg/(N s)], fuel flow [kg/s]; not pyCycle."""
        return await call(J.jet_turbofan, mach, altitude_m, thrust_sl_N, installation_factor,
                          throttle_ratio, tsfc_multiplier)

    @srv.tool(name="jet_loads", annotations=ann(True, "Transport maneuver V-n L0"))
    async def jet_loads(mass_kg: float, wing_area_m2: float, vc_eas_m_s: float,
                        cl_max: float = 1.5, cl_min: float = -1.0, vd_ratio: float = 1.25) -> dict[str, Any]:
        """EAS m/s, clean symmetric maneuver envelope only, NOT CS-25 compliance."""
        return await call(J.jet_loads, mass_kg, wing_area_m2, vc_eas_m_s, cl_max, cl_min, vd_ratio)

    @srv.tool(name="jet_analyse", annotations=ann(True, "Fixed-MTOW transport analysis L0"))
    async def jet_analyse(spec: Any) -> dict[str, Any]:
        """SI dict or JSON/YAML path: mtow_kg, wing_area_m2, aspect_ratio, mach, altitude_m,
        range_m, thrust_sl_N per engine. Optional wave/engine/loads dicts. Not full sizing."""
        return await call(J.jet_analyse, spec)

    @srv.tool(name="jet_check", annotations=ann(True, "Jet public reference order-of-magnitude check"))
    async def jet_check(reference: Any) -> dict[str, Any]:
        """Dict or JSON/YAML path with spec, published.oew_kg, sources. We vs OEW coarse check only."""
        return await call(J.jet_check, reference)


    @srv.tool(name="jet_size", annotations=ann(False, "Coupled jet mass closure L0 with provenance"))
    async def jet_size(spec: Any, record: bool = True) -> dict[str, Any]:
        """Optional weights.mode=components: partial transport regressions plus supplied
        remaining masses; absent weights preserves statistics. One explicit jet_transport candidate: configuration_id, payload_kg, crew_kg,
        wing_area_m2, aspect_ratio, mach, altitude_m, range_m, thrust_sl_N per engine,
        n_engines, mass_bounds_kg=[lo,hi]. Optional wave/engine/solver dicts, cd0,
        oswald, reserve_fraction, mtow_limit_kg. Integrates mass-dependent Breguet;
        reports convergence/residual and thrust checks. Not full MDA or CS-25 compliance.
        Writes a provenance run by default; record=false is pure calculation."""
        return await call(J.jet_size, spec, record)


    @srv.tool(name="jet_performance", annotations=ann(False, "Jet L0 takeoff/climb/OEI engineering screening"))
    async def jet_performance(spec: Any, record: bool = True) -> dict[str, Any]:
        """Closes jet mass then screens explicit performance.ground / climb_points
        with ISA/engine lapse and configuration drag. All speeds/configuration drag,
        CLmax, friction, mass fractions and rating factors must be declared. Ground
        acceleration and steady AEO/OEI points only: NOT balanced field/V1/VMC/V2,
        a certified takeoff distance, net path or CS-25 compliance. Legacy feasible
        retains its mass/cruise meaning; see combined_requested_checks_passed.
        Uses the jet_size spec plus a required performance block; records provenance."""
        return await call(J.jet_performance, spec, record)


    @srv.tool(name="jet_weights", annotations=ann(False, "Transport partial component weights / explicit baseline"))
    async def jet_weights(spec: Any, record: bool = True) -> dict[str, Any]:
        """Partial Raymer TRANSPORT wing/HT/VT plus explicit remaining group masses.
        spec: mass_kg, wing_area_m2, aspect_ratio, weights. Explicit statistical mode
        remains available. Missing/duplicate coverage cannot become zero; historical
        metal transport applicability must be declared. No OEW fit, GA weights or
        full component/MDA claim. jet_size accepts the same opt-in weights block."""
        return await call(J.jet_weights, spec, record)
