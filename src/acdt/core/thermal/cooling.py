# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Arrefecimento por ar dinâmico (entrada NACA submersa ou tomada de pitot + conduta), ventilador, arrasto,
massa e potência de arrefecimento.

* Caudal necessário: Q = ṁ·c_p·(T_lim − T_entrada) (1.ª lei num sistema aberto em regime permanente, Incropera et al. 6.ª ed., Cap. 1),
  com T_entrada = temperatura total do ar (PRESSUPOSTO: mistura perfeita, o ar sai à temperatura limite).
* Área da entrada: A = ṁ/(MFR·ρ·V). Entrada NACA submersa: MFR de projeto 0,60 — NACA RM A8I29 (Hall & Frank,
  1948): «these submerged inlets should be designed to operate near 0.60 mass-flow ratio» (a recuperação de
  pressão dinâmica é máxima entre 0,60 e 0,80). A recuperação de pressão dinâmica η_r (ram-recovery ratio
  (H − p)/(H₀ − p) do mesmo relatório) depende da instalação e é **entrada** do utilizador.
* Arrasto interno (quantidade de movimento num volume de controlo + Bernoulli incompressível; Anderson,
  *Fundamentals of Aerodynamics*, 5.ª ed., 2011, Cap. 2 e 3): com perda de pressão total ζ·q∞ entre o infinito e a
  saída (ζ = (1 − η_r) + perdas da conduta e do permutador em unidades de q∞) e saída à pressão estática ambiente,
  V_s = V·√(1 − ζ) e D = ṁ·(V − V_s). PRESSUPOSTO: efeito de Meredith (empuxo do aquecimento do ar) desprezado —
  majorante para um ζ dado; arrasto externo da entrada (transbordo, rampa) **não incluído** salvo se declarado.
  ζ desconhecido → D ∈ [0, ṁ·V] (perda total da quantidade de movimento é o majorante físico).
* Ventilador (parado / pairar / ζ ≥ 1): potência elétrica P = ṁ·Δp/(ρ·η) (potência de fluido / rendimento), com
  Δp e η declarados (sem valores por omissão).
* Massa da conduta: parede de secção circular com a área da entrada, m = 2√(πA)·L·m″ (m″ = massa por área
  declarada); massa do permutador e do ventilador: entradas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .air import CP_AIR

NACA_RM_A8I29 = ("Hall, C. F. & Frank, J. L., Ram-Recovery Characteristics of NACA Submerged Inlets at High Subsonic "
                 "Speeds, NACA RM A8I29 (1948) — MFR de projeto ≈ 0,60")
MOMENTUM_REF = "Anderson, Fundamentals of Aerodynamics, 5.ª ed. (2011), Cap. 2 (quantidade de movimento) e 3 (Bernoulli)"
NACA_MFR_DESIGN = 0.60
# A entrada fica com a maior área pedida pelos segmentos em voo (o pior), não com a de um segmento nomeado.
WORST_SEGMENT = "pior_segmento"


@dataclass
class RamDuct:
    """Resultado do dimensionamento de uma entrada de ar + conduta para um calor Q a rejeitar."""

    m_dot_kg_s: float | None
    inlet_area_m2: float | None
    drag_N_lo: float | None
    drag_N_hi: float | None
    exit_velocity_m_s: float | None
    zeta: float | None
    needs_fan: bool
    duct_mass_kg: float | None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def required_mass_flow(Q_W: float, T_limit_K: float, T_in_K: float) -> float | None:
    """ṁ = Q/(c_p·(T_lim − T_entrada)); None se T_entrada ≥ T_lim (o ar não arrefece)."""
    dT = T_limit_K - T_in_K
    if Q_W <= 0:
        return 0.0
    if dT <= 0:
        return None
    return Q_W / (CP_AIR * dT)


def internal_drag(m_dot: float, V: float, zeta: float | None) -> tuple[float, float, float | None]:
    """(D_lo, D_hi, V_saída) para perda ζ·q∞; ζ None → [0, ṁV]."""
    if m_dot <= 0 or V <= 0:
        return 0.0, 0.0, None
    if zeta is None:
        return 0.0, m_dot * V, None
    Ve = V * math.sqrt(max(0.0, 1.0 - zeta))
    D = m_dot * (V - Ve)
    return D, D, Ve


def size_ram_duct(Q_W: float, T_limit_K: float, T_in_K: float, rho: float, V: float, *, mfr: float = NACA_MFR_DESIGN,
                  ram_recovery: float | None = None, duct_loss_q: float | None = None, duct_length_m: float | None = None,
                  areal_density_kg_m2: float | None = None, fixed_mass_kg: float = 0.0) -> RamDuct:
    """Entrada + conduta para rejeitar Q com o ar à saída limitado a T_lim."""
    notes: list[str] = []
    m = required_mass_flow(Q_W, T_limit_K, T_in_K)
    if m is None:
        return RamDuct(None, None, None, None, None, None, True, None,
                       [f"ar de entrada a {T_in_K - 273.15:.1f} °C ≥ limite {T_limit_K - 273.15:.1f} °C: ar dinâmico "
                        "não arrefece (precisa de ciclo de refrigeração ou de outro dissipador)"])
    if V <= 0.5:
        return RamDuct(m, None, None, None, None, None, True, None,
                       ["parado/pairar: sem pressão dinâmica — precisa de ventilador (declare thermal fan)"])
    A = m / (mfr * rho * V)
    zeta = None if ram_recovery is None or duct_loss_q is None else (1.0 - ram_recovery) + duct_loss_q
    if zeta is None:
        notes.append("perdas de pressão total desconhecidas (ram_recovery e duct_loss_q): arrasto interno ∈ [0, ṁV]")
    lo, hi, Ve = internal_drag(m, V, zeta)
    fan = zeta is not None and zeta >= 1.0
    if fan:
        notes.append(f"ζ = {zeta:.2f} ≥ 1: a pressão dinâmica não vence as perdas — precisa de ventilador")
    mass: float | None
    if m <= 0:
        mass = 0.0
    elif duct_length_m is None or areal_density_kg_m2 is None:
        mass = None
        notes.append("massa da conduta desconhecida: declare duct.length_m e duct.areal_density_kg_m2 (com fonte)")
    else:
        mass = 2.0 * math.sqrt(math.pi * A) * duct_length_m * areal_density_kg_m2 + fixed_mass_kg
    notes.append("arrasto externo da entrada (transbordo/rampa) não incluído; efeito de Meredith desprezado")
    return RamDuct(m, A, lo, hi, Ve, zeta, fan, mass, notes)


def fan_power(m_dot: float, rho: float, pressure_rise_Pa: float | None, efficiency: float | None) -> float | None:
    """P_elétrica = ṁ·Δp/(ρ·η); None se Δp ou η não declarados."""
    if m_dot <= 0:
        return 0.0
    if pressure_rise_Pa is None or efficiency is None or efficiency <= 0:
        return None
    return m_dot * pressure_rise_Pa / (rho * efficiency)
