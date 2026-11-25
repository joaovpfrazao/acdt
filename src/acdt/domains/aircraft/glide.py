# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Desempenho em voo planado (planador sem motor, ``propulsion_type: none``).

Polar parabólica do dimensionamento ``CD = CD0 + K CL²`` (Anderson, *Aircraft Performance and Design*, 1999,
§5.4 e §8.5; Thomas, *Fundamentals of Sailplane Design*, 1999, cap. 4):

* razão de planeio máxima ``(L/D)max = 1 / (2 √(CD0 K))`` em ``CL* = √(CD0/K)``;
* taxa de afundamento mínima em ``CL = √(3 CD0/K)`` (potência mínima), ``w = V CD/CL``;
* velocidades a uma massa ``m``: ``V = √(2 m g / (ρ S CL))``; a polar de velocidades escala com ``√(m/m_ref)``
  (Thomas §4.3), por isso a comparação com polares publicadas faz-se à mesma massa.

Limitação (escrita nas notas): a polar parabólica não reproduz o "balde" laminar dos perfis de planador
(Wortmann/Althaus): subestima o afundamento a alta velocidade e na zona do balde. É uma estimativa L0.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from acdt.core.atmosphere import isa

G0 = 9.80665


@dataclass
class GlidePolar:
    mass_kg: float
    rho: float
    S: float
    CD0: float
    K: float
    CLmax: float
    LD_max: float
    V_best_LD: float          # m/s TAS
    sink_min: float           # m/s
    V_min_sink: float         # m/s TAS
    V_stall: float            # m/s TAS, CLmax limpo
    points: list[tuple[float, float]] = field(default_factory=list)   # (V m/s, afundamento m/s)
    notes: list[str] = field(default_factory=list)

    def sink(self, V: float) -> float:
        """Afundamento [m/s] à velocidade V [m/s] (voo planado de pequeno ângulo, L ≈ W)."""
        CL = 2 * self.mass_kg * G0 / (self.rho * V**2 * self.S)
        return V * (self.CD0 + self.K * CL**2) / CL

    def summary(self) -> dict:
        return {"massa_kg": self.mass_kg, "L/D_max": self.LD_max, "V_LDmax_km_h": 3.6 * self.V_best_LD,
                "afundamento_min_m_s": self.sink_min, "V_afund_min_km_h": 3.6 * self.V_min_sink,
                "V_perda_km_h": 3.6 * self.V_stall, "CD0": self.CD0, "K": self.K, "CLmax": self.CLmax,
                "polar_km_h_m_s": [(3.6 * v, w) for v, w in self.points], "notas": list(self.notes)}


def glide_polar(S: float, CD0: float, K: float, CLmax: float, mass_kg: float, altitude_m: float = 0.0,
                speeds_m_s=None) -> GlidePolar:
    """Polar de velocidades do planador à massa ``mass_kg`` e altitude ``altitude_m`` (ISA)."""
    if not (S > 0 and CD0 > 0 and K > 0 and CLmax > 0 and mass_kg > 0):
        raise ValueError("glide_polar precisa de S, CD0, K, CLmax e massa positivos")
    rho = isa(altitude_m).rho
    W = mass_kg * G0
    CL_ld = math.sqrt(CD0 / K)
    CL_ms = min(math.sqrt(3 * CD0 / K), CLmax)
    V = lambda CL: math.sqrt(2 * W / (rho * S * CL))  # noqa: E731
    V_ms = V(CL_ms)
    notes = ["polar parabólica CD0 + K CL² (Anderson 1999 §5.4): não reproduz o balde laminar — estimativa L0"]
    if CL_ms < math.sqrt(3 * CD0 / K):
        notes.append("CL de afundamento mínimo limitado por CLmax")
    Vs = V(CLmax)
    vs = list(speeds_m_s) if speeds_m_s is not None else [Vs * (1.05 + 0.1 * i) for i in range(30)]
    gp = GlidePolar(mass_kg, rho, S, CD0, K, CLmax, 1 / (2 * math.sqrt(CD0 * K)), V(CL_ld), 0.0, V_ms, Vs,
                    notes=notes)
    gp.sink_min = gp.sink(V_ms)
    gp.points = [(v, gp.sink(v)) for v in vs if v >= Vs]
    return gp


def glide_from_result(res, mass_kg: float | None = None, altitude_m: float = 0.0) -> GlidePolar:
    """Polar do resultado do dimensionamento (``res.polar``, ``res.highlift.CLmax_clean``) à massa dada
    (por defeito W0)."""
    return glide_polar(res.S, res.polar.CD0, res.polar.K, res.highlift.CLmax_clean,
                       mass_kg if mass_kg is not None else res.sizing.W0, altitude_m)
