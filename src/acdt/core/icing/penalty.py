# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Penalização aerodinâmica do gelo — só intervalos publicados (docs/GELO.md).

Fonte única verificada: Broeren, Addy, Bragg, Busch, Guffond & Montreuil, *Aerodynamic Simulation of Ice Accretion
on Airfoils*, NASA/TP-2011-216929 (2011), §5 e §10.1: perfil NACA 23012 de 1,83 m de corda, ONERA F1,
Re = 15,9×10⁶, M = 0,20, com moldagens 3-D de gelo do IRT. C_l,max limpo 1,85; com gelo 0,52 (crista «spanwise
ridge») a 1,28 (rugosidade EG1134); corno («horn») 0,86; rugosidade/linear 1,09–1,28. Razão C_l,max,gelo/C_l,max,limpo
∈ [0,52/1,85; 1,28/1,85] = [0,281; 0,692].

PRESSUPOSTO (assinalado no resultado): transferir a razão de um único perfil para a asa em estudo. Incremento de
arrasto: a fonte dá C_d,min com gelo de rugosidade/linear 0,0082–0,0106, mas não o C_d,min limpo nas mesmas
condições no texto consultado → ΔC_D0 **desconhecido**.
"""
from __future__ import annotations

import math
from typing import Any

SOURCE = "Broeren et al., NASA/TP-2011-216929 (2011), NACA 23012, Re 15,9×10⁶, M 0,20"
CLMAX_CLEAN = 1.85
CLMAX_ICED = (0.52, 1.28)
CLMAX_RATIO = (CLMAX_ICED[0] / CLMAX_CLEAN, CLMAX_ICED[1] / CLMAX_CLEAN)


def penalty(iced: bool | None) -> dict[str, Any]:
    """Penalização para uma superfície sustentadora com gelo (``iced`` True), sem gelo (False) ou desconhecido."""
    if iced is False:
        return {"applies": False, "clmax_ratio": {"lo": 1.0, "hi": 1.0}, "stall_speed_factor": {"lo": 1.0, "hi": 1.0},
                "delta_CD0": {"lo": 0.0, "hi": 0.0}, "source": "sem acreção prevista"}
    r_lo, r_hi = CLMAX_RATIO
    return {"applies": True if iced else None,
            "clmax_ratio": {"lo": r_lo, "hi": r_hi},
            # V_s ∝ 1/√C_L,max (W/S = ½ ρ V_s² C_L,max)
            "stall_speed_factor": {"lo": 1.0 / math.sqrt(r_hi), "hi": 1.0 / math.sqrt(r_lo)},
            "delta_CD0": {"lo": None, "hi": None},
            "source": SOURCE,
            "notes": ["PRESSUPOSTO: razão de C_l,max medida num único perfil (NACA 23012) transferida para esta asa",
                      "ΔC_D0 desconhecido (C_d,min limpo de referência não disponível na fonte consultada)"]}
