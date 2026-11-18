"""Euler–Bernoulli / St-Venant beam and a thin circular tube.

* Cantilever integration: θ′ = T / GJ, w″ = M / EI, clamped at ``y_clamp`` (Megson, *Aircraft
  Structures for Engineering Students*, beam theory). The integrator is the trapezoidal rule.
* Thin circular tube: A = 2πRt, I = πR³t, J = 2πR³t (Bredt–Batho torsion constant of a
  single-cell circular shell, Megson Eq. 18.4 specialised to a circle). Booms on a circle add
  I_boom = n A_b R² / 2 (Megson idealisation: direct stress in the booms).
* Cylinder bending / compression: classical stress σ_cl = 0.605 E t / R for ν = 0.3
  (Timoshenko & Gere, *Theory of Elastic Stability*, axial buckling of a circular cylinder;
  bending of a long cylinder is taken at the same classical stress, which is conservative
  relative to the pure-bending factor ≈ 1.3). Knockdown γ from NASA SP-8007 (1968), the
  lower-bound correlation γ = 1 − 0.901 (1 − exp(−φ)), φ = √(R/t) / 16.
"""
from __future__ import annotations

import math

import numpy as np

# Timoshenko & Gere, ν = 0.3: E / sqrt(3(1−ν²)) = 0.605 E.
CLASSICAL_K = 0.605


def _trap_from_clamp(y: np.ndarray, f: np.ndarray, y_clamp: float) -> np.ndarray:
    """∫_{y_clamp}^{y} f dη, with the integrand zero inboard of the clamp. ``y`` increases."""
    g = np.where(np.asarray(y, float) >= y_clamp, np.asarray(f, float), 0.0)
    seg = 0.5 * (g[1:] + g[:-1]) * np.diff(np.asarray(y, float))
    out = np.zeros(len(y))
    out[1:] = np.cumsum(seg)
    return out


def cantilever_response(y, moment, torque, EI, GJ, y_clamp: float = 0.0) -> dict:
    """Tip-up deflection and nose-up twist of a beam clamped at ``y_clamp``.

    ``y`` increases from the root toward the free end. ``EI`` and ``GJ`` are multiplied by the
    caller when a calibration factor is in use (k_EI, k_GJ): this function does not know them.
    Returns slope [rad], deflection [m] and twist [rad] at the stations of ``y``.
    """
    y = np.asarray(y, float)
    EI = np.maximum(np.asarray(EI, float), 1e-12)
    GJ = np.maximum(np.asarray(GJ, float), 1e-12)
    kappa = np.asarray(moment, float) / EI
    twist_rate = np.asarray(torque, float) / GJ
    slope = _trap_from_clamp(y, kappa, y_clamp)
    deflection = _trap_from_clamp(y, slope, y_clamp)
    twist = _trap_from_clamp(y, twist_rate, y_clamp)
    return {"slope_rad": slope, "deflection_m": deflection, "twist_rad": twist}


def thin_circular_tube(R: float, t: float, n_booms: int = 0, A_boom: float = 0.0) -> dict:
    """Section of a thin circular shell, optional equal booms on the radius (Megson).

    I is about a diameter. J is the Bredt–Batho torsion constant of the skin cell (booms do not
    close an extra cell). Valid for t ≪ R.
    """
    if R <= 0 or t <= 0:
        raise ValueError("thin_circular_tube needs R > 0 and t > 0")
    A_skin = 2 * math.pi * R * t
    I_skin = math.pi * R**3 * t
    J = 2 * math.pi * R**3 * t
    I_boom = n_booms * A_boom * R**2 / 2
    return {"A": A_skin + n_booms * A_boom, "I": I_skin + I_boom, "J": J, "A_skin": A_skin,
            "I_skin": I_skin, "I_boom": I_boom}


def cylinder_axial_knockdown(R_over_t: float) -> float:
    """NASA SP-8007 (1968) lower-bound knockdown for isotropic circular cylinders in axial compression.

    φ = √(R/t) / 16, γ = 1 − 0.901 (1 − e^{−φ}). Clamped to (0.25, 1): the correlation was not
    fitted below the usual thin-shell range, and γ > 1 is outside the formula.
    """
    if R_over_t <= 1.0:
        return 1.0
    phi = math.sqrt(R_over_t) / 16.0
    gamma = 1.0 - 0.901 * (1.0 - math.exp(-phi))
    return float(min(1.0, max(0.25, gamma)))


def tube_thickness(M: float, T: float, V: float, R: float, E: float, sigma_cap: float, tau_allow: float,
                  t_min: float) -> dict:
    """Skin thickness of a thin circular fuselage bay (ultimate M, T, V already).

    * Yield: σ = M / (π R² t) ≤ σ_cap (Megson, thin-wall bending).
    * Buckling: σ ≤ γ σ_cl, σ_cl = 0.605 E t / R, γ from :func:`cylinder_axial_knockdown`.
      The thickness is the fixed point of that inequality (γ depends on R/t).
    * Torsion: τ = T / (2 π R² t) ≤ τ_allow (Bredt–Batho, q = T / (2πR²)).
    * Transverse shear: τ_max = V / (π R t) ≤ τ_allow (thin circular tube, Megson).

    The bay is sized by the envelope of the four thicknesses and ``t_min``.
    """
    if R <= 0 or E <= 0 or sigma_cap <= 0 or tau_allow <= 0:
        raise ValueError("tube_thickness needs positive R, E, allowables")
    M, T, V = abs(M), abs(T), abs(V)
    t_yield = M / (math.pi * R**2 * sigma_cap) if M else 0.0
    t_torsion = T / (2 * math.pi * R**2 * tau_allow) if T else 0.0
    t_shear = V / (math.pi * R * tau_allow) if V else 0.0
    t = max(t_min, t_yield, t_torsion, t_shear, 1e-6)
    t_buckling = 0.0
    gamma = 1.0
    for _ in range(16):
        gamma = cylinder_axial_knockdown(R / t)
        # M / (π R² t) = γ * 0.605 * E * t / R  →  t² = M / (π R γ 0.605 E)
        if M > 0 and gamma > 0:
            t_buckling = math.sqrt(M / (math.pi * R * gamma * CLASSICAL_K * E))
        t_new = max(t_min, t_yield, t_torsion, t_shear, t_buckling)
        if abs(t_new - t) <= 1e-6 * t:
            t = t_new
            break
        t = t_new
    gamma = cylinder_axial_knockdown(R / t)
    sigma = M / (math.pi * R**2 * t) if t else 0.0
    sigma_cr = gamma * CLASSICAL_K * E * t / R
    return {"t": float(t), "t_yield": float(t_yield), "t_buckling": float(t_buckling),
            "t_torsion": float(t_torsion), "t_shear": float(t_shear), "gamma": float(gamma),
            "sigma": float(sigma), "sigma_cr": float(sigma_cr)}
