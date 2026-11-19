# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Ruído de hélices e rotores, L0: tonal de carga (Gutin) e banda larga de vórtices (Schlegel, King & Mull).

**Tonal (rotacional) de carga — Gutin (1936)**, forma de campo afastado com raio efetivo, valor rms do harmónico m
(SI; Garrick & Watkins, NACA Report 1198, 1954, Eq. 31–34 com V = 0; Marte & Kurtz, JPL TR 32-1462, 1970, Eq. 1):

    p_m = (m B Ω / (2√2 π c r)) · | T cos θ − Q c / (Ω R_e²) | · J_mB(m B Ω R_e sin θ / c)

T empuxo e Q binário de **um** rotor [N, N·m], B pás, Ω [rad/s], r distância ao centro do disco [m], θ ângulo
entre o eixo do empuxo (para a frente) e o observador, R_e = 0,8 R (raio efetivo; Garrick & Watkins 1954:
«an effective radius of the order of 0.8R is considered reasonable for adoption in initial calculations»).
Forma de engenharia em unidades inglesas (Marte & Kurtz 1970, Eq. 1; Hubbard, NACA TN 1354): p [dyn/cm²] =
169,3 m B R M_t/(S A) · (0,76 P_h/M_t² − T cos θ) · J_mB(0,8 M_t m B sin θ) — o teste confirma que as duas formas
coincidem (169,3 = 478,8/(2√2), 1 lbf/ft² = 478,8 dyn/cm²).

Validade (Marte & Kurtz 1970, §III.C): «reasonable agreement with experimental results for the first few harmonics
of conventional propellers operating at moderate tip speeds and forward velocities»; para M_t entre 0,5 e 0,3 as
medições divergem para cima (domina o ruído de vórtices). Não inclui ruído de espessura (Deming), efeito
convectivo do voo (Garrick & Watkins), interação pá-esteira nem ruído de motor — PRESSUPOSTOS declarados no
resultado.

**Banda larga (vórtices) — Schlegel, King & Mull (1966)**, USAAVLABS TR 66-4, como apresentado por Marte & Kurtz
(1970), Eq. (3) e Apêndice C:

    SPL_300ft = 10 log10( 6,1×10⁻²⁷ A_b V_0,7⁶ / 10⁻¹⁶ ) + 20 log10( C_L / 0,4 )   [dB re 20 µPa a 300 ft]

A_b área total das pás [ft²], V_0,7 velocidade da secção a 0,7 R [ft/s], C_L coeficiente de sustentação médio
baseado em V_0,7: C_L = T/(½ ρ V_0,7² A_b) (é a definição que reproduz a forma ao nível do mar de Marte & Kurtz,
SPL = 10 (2 log V + 2 log T − log A_b − 3,57), com ρ = 0,002378 slug/ft³). Frequência de pico f = V_0,7·St/h com
St = 0,28 e h = t cos α + c sin α (espessura projetada); espectro em bandas de oitava de pá não perdida da
Fig. 10a (passos do exemplo do Apêndice C): f/2 −8, f −4, 2f −8, 4f −9, 8f −13, 16f −14 dB relativos ao nível
global. Marte & Kurtz: a constante «is not firmly established»; precisão ±10 dB no campo afastado a 500 ft.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from scipy.special import jv

if TYPE_CHECKING:
    from .propagation import Component

FT = 0.3048
R_EFF = 0.8
GUTIN_REF = ("Gutin (1936), NACA TM 1195 (1948); forma de campo afastado com raio efetivo: Garrick & Watkins, NACA "
             "Report 1198 (1954); Marte & Kurtz, JPL TR 32-1462 (1970), Eq. (1)")
SKM_REF = ("Schlegel, King & Mull (1966), USAAVLABS TR 66-4, como em Marte & Kurtz, JPL TR 32-1462 (1970), Eq. (3), "
           "Fig. 10a e Apêndice C")
SKM_K = 6.1e-27
SKM_R_REF = 300.0 * FT  # 91,44 m
SKM_ST = 0.28
SKM_OCTAVES: tuple[tuple[float, float], ...] = ((0.5, -8.0), (1.0, -4.0), (2.0, -8.0), (4.0, -9.0), (8.0, -13.0),
                                                (16.0, -14.0))
RHO_SL_SLUG_FT3 = 0.002378


def thickness_noise_status() -> dict[str, Any]:
    """Espessura (Deming) e Hanson: não avaliadas. Não devolve um SPL.

    NACA TN 605 (Deming, 1937, NTRS 19930081380) é de domínio público, mas a equação não foi
    transcrita de uma cópia legível. Hanson e SAE AIR1407 continuam por verificar equação a
    equação. Não avaliado não é zero nem passa.
    """
    return {
        "evaluated": False, "veredicto": "nao_avaliado", "method": None, "spl_dB": None,
        "reason": (
            "Ruído de espessura de Deming (NACA TN 605, 1937, «Noise from Propellers with Symmetrical "
            "Sections at Zero Blade Angle», NTRS 19930081380) não foi transcrito: a equação não está conferida. "
            "Hanson e SAE AIR1407 não foram verificados equação a equação. Não se devolve um nível."),
        "sources": [
            "Deming, A. F., NACA TN 605 (1937), NTRS 19930081380 — equação não transcrita",
            "Hanson — não verificado",
            "SAE AIR1407 — não verificado",
        ],
    }


def gutin_prms(m: int, B: int, omega: float, T: float, Q: float, r: float, theta: float, c: float,
               R: float, re_frac: float = R_EFF) -> float:
    """p_m rms [Pa] do harmónico m de um rotor (SI). θ [rad] a partir do eixo do empuxo (para a frente)."""
    Re = re_frac * R
    k = m * B
    amp = k * omega / (2.0 * math.sqrt(2.0) * math.pi * c * r)
    load = abs(T * math.cos(theta) - Q * c / (omega * Re * Re))
    return float(amp * load * abs(jv(k, k * omega * Re * math.sin(theta) / c)))


def gutin_english_dyn_cm2(m: int, B: int, R_ft: float, Mt: float, S_ft: float, P_hp: float, T_lb: float,
                          theta: float) -> float:
    """Forma de engenharia de Marte & Kurtz (1970) Eq. (1) [dyn/cm²] — só para verificar a forma SI."""
    A = math.pi * R_ft ** 2
    k = m * B
    return float(169.3 * k * R_ft * Mt / (S_ft * A) * abs(0.76 * P_hp / Mt ** 2 - T_lb * math.cos(theta))
                 * abs(jv(k, 0.8 * Mt * k * math.sin(theta))))


@dataclass(frozen=True)
class VortexNoise:
    spl_300ft_dB: float          # nível global a 300 ft (91,44 m), dB re 20 µPa
    f_peak_Hz: float | None      # None sem espessura projetada
    CL: float
    V07_m_s: float
    Ab_m2: float

    def octave_bands(self) -> list[tuple[float, float]]:
        """[(frequência central [Hz], SPL a 300 ft [dB])] — Fig. 10a (pá não perdida)."""
        if self.f_peak_Hz is None:
            return []
        return [(self.f_peak_Hz * k, self.spl_300ft_dB + d) for k, d in SKM_OCTAVES]


def vortex_noise(T: float, Ab_m2: float, V07: float, rho: float, h_proj_m: float | None) -> VortexNoise:
    """Ruído de vórtices de um rotor: T [N], A_b área total das pás [m²], V_0,7 [m/s], ρ [kg/m³]."""
    CL = T / (0.5 * rho * V07 ** 2 * Ab_m2)
    Ab_ft2 = Ab_m2 / FT ** 2
    V_fts = V07 / FT
    spl = 10.0 * math.log10(SKM_K * Ab_ft2 * V_fts ** 6 / 1e-16) + 20.0 * math.log10(max(CL, 1e-12) / 0.4)
    fp = V07 * SKM_ST / h_proj_m if h_proj_m and h_proj_m > 0 else None
    return VortexNoise(spl, fp, CL, V07, Ab_m2)


def projected_thickness(t_m: float, chord_m: float, alpha_rad: float) -> float:
    """h = b cos α + a sin α (Marte & Kurtz 1970, Apêndice C, passo 5)."""
    return t_m * math.cos(alpha_rad) + chord_m * math.sin(alpha_rad)


def rotor_components(*, B: int, R: float, rpm: float, T: float, P: float, c: float, rho: float,
                     n_rotors: int = 1, harmonics: int = 10, re_frac: float = R_EFF, blade_area_m2: float | None = None,
                     h_proj_m: float | None = None, broadband: bool = True, label: str = "rotor"
                     ) -> tuple[list["Component"], dict[str, object]]:
    """Componentes de ruído de ``n_rotors`` rotores iguais e incoerentes (T e P de **um** rotor).

    Tons: harmónicos m = 1…``harmonics`` de Gutin à frequência m·B·rpm/60. Banda larga: bandas de oitava de
    Schlegel-King-Mull quando há área das pás e espessura projetada (sem elas, só o nível global é reportado e a
    banda larga fica fora da soma — indicado em ``info['broadband_in_sum']``)."""
    from .levels import lp_from_prms
    from .propagation import Component

    omega = rpm / 60.0 * 2.0 * math.pi
    Q = P / omega if omega > 0 else 0.0
    add = 10.0 * math.log10(max(n_rotors, 1))
    comps: list[Component] = []
    for m in range(1, harmonics + 1):
        def lev(r: float, th: float, m: int = m) -> float:
            return lp_from_prms(gutin_prms(m, B, omega, T, Q, r, th, c, R, re_frac)) + add
        comps.append(Component(f"{label}: tom m={m}", m * B * rpm / 60.0, lev, "tonal", "tom"))
    V07 = 0.7 * omega * R
    tip_mach = omega * R / c
    info: dict[str, object] = {"B": B, "R_m": R, "rpm": rpm, "T_N": T, "P_W": P, "Q_Nm": Q, "n_rotors": n_rotors,
                               "tip_mach_rot": tip_mach, "bpf_Hz": B * rpm / 60.0, "harmonics": harmonics,
                               "re_frac": re_frac, "broadband_in_sum": False, "vortex": None}
    if broadband and blade_area_m2 and blade_area_m2 > 0 and V07 > 0:
        vn = vortex_noise(T, blade_area_m2, V07, rho, h_proj_m)
        info["vortex"] = {"SPL_300ft_dB": vn.spl_300ft_dB + add, "f_peak_Hz": vn.f_peak_Hz, "CL_mean": vn.CL,
                          "V07_m_s": vn.V07_m_s, "Ab_m2": vn.Ab_m2}
        for fc, L300 in vn.octave_bands():
            def levb(r: float, th: float, L300: float = L300) -> float:
                return L300 + add - 20.0 * math.log10(r / SKM_R_REF)
            comps.append(Component(f"{label}: banda larga {fc:.0f} Hz", fc, levb, "banda_larga", "oitava"))
        info["broadband_in_sum"] = vn.f_peak_Hz is not None
    return comps, info
