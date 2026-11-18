# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Toolkit wrappers: opt-in lightweight BEMT propeller/rotor and Drela motor deck."""
from __future__ import annotations

from typing import Any

from acdt.ai.toolkit import clean
from acdt.core.systems.motor_deck import assess_motor
from acdt.domains.aircraft.systems_bemt import size_propeller_bemt
from acdt.domains.aircraft.vtol.bemt import assess_rotor_bemt


def bemt_propeller(spec: dict) -> dict[str, Any]:
    """BEMT fixed-pitch propeller (McCormick/Ning). ``spec``: P_shaft_W, V_cruise_m_s, altitude_m?,
    propeller{...} or the geometry keys at the top level."""
    cfg = spec.get("propeller") or spec
    P = float(spec.get("P_shaft_W") or 0)
    V = float(spec.get("V_cruise_m_s") or 0)
    h = float(spec.get("altitude_m") or 0)
    r = size_propeller_bemt(cfg, P, V, h, spec.get("kind", "electric"))
    return clean(dict(r.__dict__))


def bemt_rotor(spec: dict) -> dict[str, Any]:
    """Axial/hover BEMT for one rotor. ``spec`` may nest geometry under ``rotor``."""
    cfg = spec.get("rotor") or spec
    return clean(assess_rotor_bemt(cfg, thrust_per_rotor_N=spec.get("thrust_per_rotor_N"),
                                   V_axial_m_s=float(spec.get("V_axial_m_s") or 0.0),
                                   altitude_m=float(spec.get("altitude_m") or 0.0)))


def motor_deck(spec: dict) -> dict[str, Any]:
    """Drela 2007 first-order motor point. ``spec``: deck + operating{V_V, rpm|I_A|torque_N_m}."""
    deck = spec.get("deck") or spec.get("motor") or spec
    op = spec.get("operating") or spec
    return clean(assess_motor(deck, V_V=op.get("V_V"), rpm=op.get("rpm"), I_A=op.get("I_A"),
                              torque_N_m=op.get("torque_N_m")))
