# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Avaliação de ruído de rotores dados explicitamente (qualquer tipo de aeronave: hélice, rotor VTOL, multirrotor).

Sem pipeline: o chamador dá o ponto de funcionamento (empuxo e potência de **um** rotor, rpm) e a geometria; devolve
o sobrevoo (L_A,max, L_AE), o espectro na vertical e os alcances de deteção auditiva (:mod:`.propagation`). Usado por
:func:`acdt.api.rotor_noise` e pela etapa do domínio aircraft (que tira o ponto de funcionamento do mapa BEMT).
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .ground import (GroundPath, annotate_ground, iso_chain_applied, parse_ground_spec, refraction_status)
from .propagation import Atmosphere, Component, Received, detection_range, flyover, received
from .rotor import rotor_components, thickness_noise_status

_Chain = tuple[Received, dict[str, Any], dict[str, Any], dict[str, Any] | None]


def _chain(comps: Sequence[Component], altitude_m: float, speed_m_s: float, atm: Atmosphere, mach: float,
           ground_dB: float, ambient: Mapping[float, float] | None, margin_dB: float,
           path: GroundPath | None) -> _Chain:
    over = received(comps, altitude_m, math.pi / 2, atm, 0.0, ground_dB, detail=True, ground=path)
    if speed_m_s > 0:
        fly = flyover(comps, altitude_m, speed_m_s, atm, 0.0, ground_dB, ground=path)
    else:
        fly = {"LAmax_dBA": over.LA, "SEL_dBA": None, "theta_at_max_deg": 90.0, "r_at_max_m": altitude_m}
        if path is not None:
            fly["ground_complete"] = bool(over.ground and over.ground.get("status") == "aplicado")
    quiet = detection_range(comps, atm, mach, None, 0.0, ground_dB, ground=path)
    amb = detection_range(comps, atm, mach, ambient, margin_dB, ground_dB, ground=path) if ambient else None
    return over, fly, quiet, amb


def rotor_noise(*, blades: int, diameter_m: float, rpm: float, thrust_N: float, power_W: float, n_rotors: int = 1,
                altitude_m: float = 100.0, speed_m_s: float = 0.0, rho: float = 1.225, c_m_s: float = 340.294,
                blade_area_m2: float | None = None, projected_thickness_m: float | None = None,
                harmonics: int = 10, T_C: float = 15.0, rh_pct: float = 70.0, p_kpa: float = 101.325,
                ground_dB: float = 0.0, ambient_third_octave_dB: Mapping[float, float] | None = None,
                detection_margin_dB: float = 0.0, ground_spec: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Ruído L0 de ``n_rotors`` rotores iguais (Gutin + Schlegel-King-Mull) num observador no solo.

    ``thrust_N``/``power_W``: de um rotor. ``speed_m_s`` = 0 → pairar (o L_A,max é o nível na vertical).
    Sem ``blade_area_m2`` não há banda larga; sem ``projected_thickness_m`` a banda larga fica fora da soma."""
    comps, info = rotor_components(B=int(blades), R=diameter_m / 2.0, rpm=rpm, T=thrust_N, P=power_W, c=c_m_s,
                                   rho=rho, n_rotors=n_rotors, harmonics=harmonics, blade_area_m2=blade_area_m2,
                                   h_proj_m=projected_thickness_m, broadband=blade_area_m2 is not None)
    atm = Atmosphere(T_C, rh_pct, p_kpa, c_m_s)
    mach = speed_m_s / c_m_s
    path, block = parse_ground_spec(ground_spec)
    over, fly, quiet, amb = _chain(comps, altitude_m, speed_m_s, atm, mach, ground_dB, ambient_third_octave_dB,
                                   detection_margin_dB, path)
    applied = path is not None and iso_chain_applied(over.ground, fly, quiet, amb)
    if path is not None and not applied:
        detail = over.ground
        over, fly, quiet, amb = _chain(comps, altitude_m, speed_m_s, atm, mach, ground_dB, ambient_third_octave_dB,
                                       detection_margin_dB, None)
        if detail:
            block.update({k: detail[k] for k in ("components", "omitted", "notas", "reason", "pressuposto", "C_met")
                          if k in detail})
        block["status"] = "nao_avaliado"
        block["nivel_reportado"] = "sem_A_gr"
    elif applied and over.ground:
        block.update(over.ground)
        block["nivel_reportado"] = "com_A_gr"
    else:
        block["nivel_reportado"] = "sem_A_gr"
    omitted = bool(block.get("omitted")) or (path is not None and not applied)
    annotate_ground(block, applied=applied, c0_declared=bool(path and path.C0_dB is not None),
                    components_omitted=omitted)

    def ground(r: Any) -> float:
        if r is None:
            return 0.0
        return math.sqrt(r * r - altitude_m ** 2) if r > altitude_m else 0.0

    return {"source": info, "overhead_LA_dBA": over.LA, "overhead_Lp_dB": over.Lp,
            "overhead_spectrum": over.components, "flyover": fly,
            "detection": {"quiet": quiet, "ambient": amb},
            "detection_ground_range_quiet_m": ground(quiet["range_m"]),
            "detection_ground_range_m": ground((amb or quiet)["range_m"]),
            "sources_note": "só tons de carga (Gutin) e banda larga de vórtices: nível e alcances são limites "
                            "inferiores (espessura, motor e célula não modelados)",
            "thickness_noise": thickness_noise_status(), "refraction": refraction_status(),
            "iso9613_ground": block}
