# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in cabin pressurization bookkeeping for jet L0 (mass increment lives in weights).

Structural shell increment W_press = 11.9 (Vp_ft³·ΔP_psi)^0.271 lb is evaluated
inside ``raymer_transport_fuselage`` when cabin volume and ΔP are supplied
(Raymer, Aircraft Design, Sec. 15.3.3 GA fuselage add-on; AeroSandbox GA
transcription). This module only validates the optional study-level extraction
contract: bleed/electrical offtakes are NEVER invented. Without an explicit
supplied auxiliary extraction model the extraction check stays unassessed
(unknown ≠ pass). No ECS pack map, no ISA cabin schedule, no CS-25.841 claim.
"""
from __future__ import annotations
from copy import deepcopy
from acdt.core.energy_storage import mapping, number

PSI = 6894.757293168


def validate_pressurization(settings: dict) -> None:
    mapping(settings, {"cabin_volume_m3", "delta_p_Pa", "source", "extraction"}, "pressurization")
    if not isinstance(settings.get("source"), str) or not settings["source"].strip():
        raise ValueError("pressurization.source required (PRESSUPOSTO or citation)")
    number("cabin_volume_m3", settings.get("cabin_volume_m3"), positive=True, maximum=1e4)
    number("delta_p_Pa", settings.get("delta_p_Pa"), maximum=1e6)
    if "extraction" in settings:
        e = settings["extraction"]
        mapping(e, {"mode", "fuel_flow_kg_s", "thrust_penalty_N", "source", "note"}, "pressurization.extraction")
        if e.get("mode") != "supplied_auxiliary":
            raise ValueError("pressurization.extraction.mode must be supplied_auxiliary (no invented bleed map)")
        if not isinstance(e.get("source"), str) or not e["source"].strip():
            raise ValueError("extraction.source required")
        number("fuel_flow_kg_s", e.get("fuel_flow_kg_s"), maximum=10)
        number("thrust_penalty_N", e.get("thrust_penalty_N"), maximum=1e6)
        if e["fuel_flow_kg_s"] == 0 and e["thrust_penalty_N"] == 0:
            raise ValueError("extraction must declare a nonzero fuel_flow_kg_s and/or thrust_penalty_N, or omit extraction")


def assess_extraction(settings: dict | None) -> dict:
    """Return extraction status for the size_jet report. Missing data → unassessed, never a pass."""
    if not settings:
        return {"status": "not_requested", "checks": [], "auxiliary_increments": None}
    validate_pressurization(settings)
    base = {"cabin_volume_m3": settings["cabin_volume_m3"], "delta_p_Pa": settings["delta_p_Pa"],
            "delta_p_psi": settings["delta_p_Pa"] / PSI, "source": settings["source"],
            "structural_mass": "W_press only when raymer_transport_fuselage supplies the same cabin pair; "
                               "transport fuselage regression already embeds historical pressurised metal transports"}
    if "extraction" not in settings:
        return {**base, "status": "unassessed",
                "checks": [{"name": "pressurization_extraction", "passed": None,
                            "reason": "cabin declared without supplied bleed/electrical extraction model"}],
                "auxiliary_increments": None,
                "issues": ["pressurization_extraction_unassessed"]}
    e = settings["extraction"]
    return {**base, "status": "assessed_supplied_auxiliary",
            "checks": [{"name": "pressurization_extraction", "passed": True,
                        "reason": "user-supplied constant auxiliary offtake; not an ECS pack map"}],
            "auxiliary_increments": {"fuel_flow_kg_s": e["fuel_flow_kg_s"], "thrust_penalty_N": e["thrust_penalty_N"],
                                     "source": e["source"], "mode": e["mode"]},
            "issues": [], "inputs": deepcopy(e),
            "limitations": ["No pack thermodynamics, no ISA cabin altitude schedule, no CS-25.841 compliance, "
                            "no takeoff/OEI extraction availability model"]}
