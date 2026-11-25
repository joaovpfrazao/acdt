# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Casca cilíndrica em sanduíche (ou monolítica) sem reforçadores — fuselagem monocasca em compósito.

Verificações por estação, à carga ÚLTIMA (limite × 1,5), de uma casca de raio R com duas faces de espessura
``t_f`` e núcleo ``t_c`` (``t_c = 0`` → laminado monolítico de espessura 2 t_f):

* **Faces — resistência**: fluxo axial da flexão N = M/(π R²) e fluxo de corte q = V/(π R) + T/(2 π R²)
  (tubo de parede fina, Megson 2013 §16/§17), divididos pelas duas faces: σ = N/(2 t_f) ≤ F_cy, τ = q/(2 t_f) ≤ F_su.
* **Encurvadura global da casca em flexão**: N_cr = γ · 2 √(D · E h)/R (forma clássica de Donnell para cascas
  com rigidez de flexão D e de membrana E h; no laminado isotrópico dá E t²/(R √(3(1−ν²)))), com o fator de
  correlação de NASA SP-8007 (1968) para flexão γ = 1 − 0,731 (1 − e^(−φ)), φ = (1/29,8) √(R / √(D/(E h)))
  (forma para sanduíche/ortotrópica; no isotrópico reduz-se a φ = √(R/t)/16).
* **Encurvadura por corte/torção**: casca isotrópica equivalente com a mesma D e E h (t_e = √(12 (1−ν²) D/(E h)),
  E_e = E h / t_e); comprimento médio (SP-8007): τ_cr = 0,747 γ_t^(3/4) E_e (t_e/R)^(5/4) (R/L)^(1/2) / (1−ν²)^(5/8),
  γ_t = 0,67; cilindro longo (Timoshenko & Gere 1961 §11.11): τ_cr = E_e (t_e/R)^(3/2) / (3 √2 (1−ν²)^(3/4));
  usa-se o maior (o longo é a assíntota). L = baía entre cavernas/anteparas.
* **Interação** flexão + corte: R_b + R_s² ≤ 1 (Bruhn 1973 C8.15, cilindros) → RF = 1/(R_b + R_s²) aproximado
  pela raiz positiva de R_b x + R_s² x² = 1.
* **Enrugamento das faces** (só sanduíche): σ_wr = 0,5 (E_f E_c G_c)^(1/3) (Hoff & Mautner 1945).

PRESSUPOSTO: flexibilidade ao corte do núcleo desprezada na encurvadura global (Allen 1969: pequena para núcleos de
espuma com d ≪ R); corte transversal no núcleo e descolamento não verificados (desconhecido, não zero).
Dimensionamento: a combinação (t_f, t_c) de menor massa por área numa grelha, com RF ≥ 1 em todas as verificações.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

GAMMA_TORSION = 0.67      # NASA SP-8007 §4.1.3 (torção, cilindros isotrópicos)


@dataclass(frozen=True)
class Face:
    E: float
    nu: float
    rho: float
    Fcy: float
    Ftu: float
    Fsu: float


@dataclass(frozen=True)
class Core:
    E: float
    G: float
    rho: float


def stiffness(t_f: float, t_c: float, face: Face) -> tuple[float, float]:
    """(D [N m], E h [N/m]) da parede: sanduíche de faces finas D = E_f t_f d²/(2(1−ν²)), d = t_c + t_f
    (Allen 1969 Eq. 2.6); monolítico (t_c = 0) D = E t³/(12(1−ν²)), t = 2 t_f."""
    Eh = 2.0 * face.E * t_f
    if t_c > 0:
        d = t_c + t_f
        D = face.E * t_f * d**2 / (2.0 * (1.0 - face.nu**2))
    else:
        D = face.E * (2.0 * t_f) ** 3 / (12.0 * (1.0 - face.nu**2))
    return D, Eh


def bending_knockdown(R: float, D: float, Eh: float) -> float:
    """NASA SP-8007: γ = 1 − 0,731 (1 − e^(−φ)), φ = √(R/√(D/Eh))/29,8."""
    phi = math.sqrt(R / math.sqrt(D / Eh)) / 29.8
    return 1.0 - 0.731 * (1.0 - math.exp(-phi))


def check_wall(N: float, q: float, R: float, L_bay: float, t_f: float, t_c: float, face: Face,
               core: Core | None) -> dict:
    """RFs de uma parede sob fluxos ÚLTIMOS N (axial de flexão, compressão no pior lado) e q (corte) [N/m]."""
    D, Eh = stiffness(t_f, t_c, face)
    out: dict = {"t_face_m": t_f, "t_core_m": t_c, "D_Nm": D, "Eh_N_m": Eh}
    sig = N / (2.0 * t_f)
    tau = q / (2.0 * t_f)
    out["RF_face_compression"] = face.Fcy / sig if sig > 0 else math.inf
    out["RF_face_tension"] = face.Ftu / sig if sig > 0 else math.inf
    out["RF_face_shear"] = face.Fsu / tau if tau > 0 else math.inf
    gam = bending_knockdown(R, D, Eh)
    Ncr = gam * 2.0 * math.sqrt(D * Eh) / R
    te = math.sqrt(12.0 * (1.0 - face.nu**2) * D / Eh)
    Ee = Eh / te
    L = max(L_bay, 1e-3)
    tau_mod = (0.747 * GAMMA_TORSION**0.75 * Ee * (te / R) ** 1.25 * math.sqrt(R / L)
               / (1.0 - face.nu**2) ** 0.625)
    tau_long = Ee * (te / R) ** 1.5 / (3.0 * math.sqrt(2.0) * (1.0 - face.nu**2) ** 0.75)
    qcr = max(tau_mod, tau_long) * te
    Rb, Rs = (N / Ncr if Ncr > 0 else math.inf), (q / qcr if qcr > 0 else math.inf)
    out.update({"gamma_bending": gam, "N_cr_N_m": Ncr, "q_cr_N_m": qcr,
                "RF_buckling_bending": 1.0 / Rb if Rb > 0 else math.inf,
                "RF_buckling_shear": 1.0 / Rs if Rs > 0 else math.inf})
    # R_b x + R_s² x² = 1 → x = RF da interação
    if Rs > 0:
        x = (-Rb + math.sqrt(Rb**2 + 4.0 * Rs**2)) / (2.0 * Rs**2)
    else:
        x = 1.0 / Rb if Rb > 0 else math.inf
    out["RF_buckling_interaction"] = x
    if t_c > 0 and core is not None:
        swr = 0.5 * (face.E * core.E * core.G) ** (1.0 / 3.0)
        out["sigma_wrinkling_Pa"] = swr
        out["RF_wrinkling"] = swr / sig if sig > 0 else math.inf
    else:
        out["RF_wrinkling"] = math.inf
    keys = ("RF_face_compression", "RF_face_tension", "RF_face_shear", "RF_buckling_interaction", "RF_wrinkling")
    out["RF_min"] = min(out[k] for k in keys)
    out["governing"] = min(keys, key=lambda k: out[k])
    out["areal_mass_kg_m2"] = 2.0 * t_f * face.rho + (t_c * core.rho if (core is not None and t_c > 0) else 0.0)
    return out


def size_wall(N: float, q: float, R: float, L_bay: float, face: Face, core: Core | None,
              t_faces: list[float], t_cores: list[float]) -> dict:
    """Parede mais leve da grelha (t_f × t_c) com RF_min ≥ 1; se nenhuma serve, a de maior RF (verdict falha)."""
    best, best_rf = None, None
    for tc in t_cores:
        if tc > 0 and core is None:
            continue
        for tf in t_faces:
            c = check_wall(N, q, R, L_bay, tf, tc, face, core)
            if c["RF_min"] >= 1.0 and (best is None or c["areal_mass_kg_m2"] < best["areal_mass_kg_m2"]):
                best = c
            if best_rf is None or c["RF_min"] > best_rf["RF_min"]:
                best_rf = c
    if best is not None:
        return {**best, "ok": True}
    assert best_rf is not None
    return {**best_rf, "ok": False}
