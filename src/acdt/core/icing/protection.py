# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Potência de proteção contra o gelo (docs/GELO.md) — balanço de Messinger na linha de estagnação.

Base: o mesmo balanço de Anderson, NASA/CR-2004-212875, Eq. (3.52)–(3.59), com a superfície aquecida e **sem
congelação** (n = 0):

* **anti-gelo térmico «running-wet», mínimo** (superfície a 0 °C, toda a água fica líquida): o calor a fornecer é
  q_rw,min = h_c θ + ṁ c_p,ws φ = h_c b (φ + θ/b) = n₀,analítico · ṁ · Λ_f — o calor que impede a congelação é o
  calor latente que a fração n₀ libertaria (identidade direta da Eq. 3.59). Minorante: com a superfície acima de 0 °C
  as perdas crescem (PRESSUPOSTO: monotonia em T_s).
* **anti-gelo totalmente evaporativo à temperatura de superfície T_s declarada** (majorante do «running-wet» a essa
  temperatura, porque na estagnação não entra água de outro sítio — Anderson §3.5.11 — e a evaporação não pode
  exceder a água captada): q_fe(T_s) = h_c (T_s − T_st − V²/(2 c_p,a)) + ṁ [c_p,ws (T_s − T_st) + Λ_v(T_s)] −
  ṁ V²/2, com Λ_v da Eq. (A.21)–(A.22) e c_p,ws da Eq. (A.2) (PRESSUPOSTO: validade da Eq. A.2 é −40…40 °F; acima
  de 4,4 °C é extrapolada — assinalado).
* **degelo eletrotérmico cíclico**: potência média ≥ q_rw,min × A_cíclica × ciclo de trabalho (o aquecedor tem de,
  pelo menos, vencer as perdas a 0 °C enquanto está ligado) + tira de separação («parting strip») em anti-gelo;
  majorante só com a densidade de potência do aquecedor declarada (W/m²) — senão desconhecido.
* PRESSUPOSTO: o fluxo da linha de estagnação aplicado a toda a área protegida (convecção e captação são máximas na
  estagnação; o gelo de retorno «runback» a jusante **não** é modelado — fica assinalado).
* Botas pneumáticas e ar sangrado: potência não modelada (desconhecido); o ar sangrado não entra no balanço
  elétrico.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import properties as pr
from .accretion import StagnationResult, _hc

SOURCE = ("Messinger (1953) via Anderson, NASA/CR-2004-212875, Eq. (3.52)–(3.59), (A.2), (A.21); superfície sem "
          "congelação")


def running_wet_min_flux(st: StagnationResult) -> float:
    """q_rw,min [W/m²] = h_c θ + ṁ c_p,ws φ (superfície a 0 °C, n = 0). Nunca negativo (0 → não é preciso calor)."""
    return max(0.0, st.h_c * st.theta + st.m_imp * st.cp_ws * st.phi)


def evaporative_flux(st: StagnationResult, d_m: float, V: float, Ts_C: float) -> tuple[float, list[str]]:
    """q_fe(T_s) [W/m²] com a superfície a ``Ts_C`` (≥ 0 °C): toda a água captada evapora."""
    notes: list[str] = []
    Ts = pr.T0 + Ts_C
    if Ts_C < 0:
        raise ValueError("superfície anti-gelo tem de estar a ≥ 0 °C")
    if Ts_C > 40.0 / 1.8 - 32.0 / 1.8 + 1e-9:  # 40 °F
        notes.append(f"c_p,ws (Eq. A.2) extrapolada a T_s = {Ts_C:.0f} °C (validade −40…40 °F)")
    hc = _hc(d_m, V, st.T_st, st.p_st, Ts)[5]
    cw = pr.cp_water_surface(Ts)
    q = (hc * (Ts - st.T_st - V * V / (2.0 * pr.CP_AIR))
         + st.m_imp * (cw * (Ts - st.T_st) + pr.lambda_vaporisation(Ts)) - st.m_imp * V * V / 2.0)
    return max(0.0, q), notes


@dataclass(frozen=True)
class ProtectionPower:
    kind: str
    flux_W_m2: dict[str, float | None]
    power_W: dict[str, float | None]
    electric: bool
    notes: tuple[str, ...]


def protection_power(kind: str, st: StagnationResult, *, d_m: float, V: float, area_m2: float | None,
                     surface_temperature_C: float | None = None, parting_strip_area_m2: float = 0.0,
                     duty_cycle: float | None = None, power_density_W_m2: float | None = None,
                     electric: bool | None = None) -> ProtectionPower:
    """Potência (intervalo) de um sistema ``anti_ice_thermal`` | ``deice_electrothermal`` | ``boots`` | ``none``."""
    notes: list[str] = []
    q_min = running_wet_min_flux(st)
    if kind == "none":
        return ProtectionPower(kind, {"lo": 0.0, "hi": 0.0}, {"lo": 0.0, "hi": 0.0}, False, ())
    if area_m2 is None or area_m2 < 0:
        return ProtectionPower(kind, {"lo": q_min, "hi": None}, {"lo": None, "hi": None}, bool(electric),
                               ("área protegida não declarada: potência desconhecida",))
    if kind == "anti_ice_thermal":
        q_hi: float | None = None
        if surface_temperature_C is not None:
            q_hi, n2 = evaporative_flux(st, d_m, V, float(surface_temperature_C))
            notes += n2
            q_hi = max(q_hi, q_min)
        else:
            notes.append("temperatura de superfície do anti-gelo não declarada: majorante desconhecido")
        notes.append("fluxo da estagnação aplicado a toda a área; gelo de retorno (runback) não modelado")
        return ProtectionPower(kind, {"lo": q_min, "hi": q_hi},
                               {"lo": q_min * area_m2, "hi": None if q_hi is None else q_hi * area_m2},
                               True if electric is None else bool(electric), tuple(notes))
    if kind == "deice_electrothermal":
        if duty_cycle is None or not 0.0 < duty_cycle <= 1.0:
            return ProtectionPower(kind, {"lo": q_min, "hi": None}, {"lo": None, "hi": None}, True,
                                   ("ciclo de trabalho (duty_cycle) não declarado: potência desconhecida",))
        lo = q_min * area_m2 * duty_cycle + q_min * parting_strip_area_m2
        hi = None
        if power_density_W_m2 is not None:
            hi = max(lo, power_density_W_m2 * (area_m2 * duty_cycle + parting_strip_area_m2))
        else:
            notes.append("densidade de potência do aquecedor não declarada: majorante desconhecido")
        notes.append("minorante: perdas a 0 °C durante o tempo ligado; tira de separação em running-wet a 0 °C")
        return ProtectionPower(kind, {"lo": q_min, "hi": power_density_W_m2}, {"lo": lo, "hi": hi}, True,
                               tuple(notes))
    if kind == "boots":
        return ProtectionPower(kind, {"lo": None, "hi": None}, {"lo": None, "hi": None}, False,
                               ("botas pneumáticas: potência/ar de serviço não modelados (desconhecido)",))
    raise ValueError(f"proteção desconhecida: {kind!r} (none | anti_ice_thermal | deice_electrothermal | boots)")


def finite(x: float | None) -> bool:
    return x is not None and math.isfinite(x)
