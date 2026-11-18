"""Shell section stiffness: membrane A [N/m], bending D [N m], transverse shear A_s [N/m] (symmetric sections,
B = 0). Classical lamination theory (Jones, *Mechanics of Composite Materials*, 2nd ed. 1999, Ch. 4) with
first-order shear deformation (Reddy, *Mechanics of Laminated Composite Plates and Shells*, 2nd ed. 2004, Ch. 3);
sandwich panels as an equivalent single layer: faces + core, transverse shear governed by the core
(A_s ≈ G_c d²/t_c, Allen, *Analysis and Design of Structural Sandwich Panels*, 1969, Ch. 2)."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class ShellSection:
    A: np.ndarray          # 3×3 membrane stiffness (local material axes 1-2) [N/m]
    D: np.ndarray          # 3×3 bending stiffness [N m]
    As: np.ndarray         # 2×2 transverse shear stiffness [N/m]
    rho_A: float           # areal mass [kg/m²]
    t: float               # total thickness [m]
    E_face: float = 0.0    # for stress recovery: modulus of the load-carrying faces (0 = homogeneous)
    note: str = ""

    def rotated(self, theta: float) -> "ShellSection":
        """Section expressed in axes rotated by ``theta`` [rad] from the material 1-axis (Jones Eq. 2.84)."""
        if abs(theta) < 1e-12:
            return self
        T = _Tbar(theta)
        return ShellSection(T.T @ self.A @ T, T.T @ self.D @ T, _rot_shear(self.As, theta), self.rho_A, self.t,
                            self.E_face, self.note)


def _Tbar(th):
    """Strain transformation (engineering shear) so that Q̄ = Tᵀ Q T maps global strains to material axes."""
    c, s = math.cos(th), math.sin(th)
    return np.array([[c * c, s * s, c * s], [s * s, c * c, -c * s], [-2 * c * s, 2 * c * s, c * c - s * s]])


def _rot_shear(As, th):
    c, s = math.cos(th), math.sin(th)
    R = np.array([[c, s], [-s, c]])
    return R.T @ As @ R


def plane_stress_Q(E1, E2, nu12, G12):
    nu21 = nu12 * E2 / E1
    d = 1 - nu12 * nu21
    return np.array([[E1 / d, nu12 * E2 / d, 0], [nu12 * E2 / d, E2 / d, 0], [0, 0, G12]])


def isotropic(E: float, nu: float, t: float, rho: float, k_s: float = 5 / 6) -> ShellSection:
    G = E / (2 * (1 + nu))
    Q = plane_stress_Q(E, E, nu, G)
    return ShellSection(Q * t, Q * t**3 / 12, np.eye(2) * k_s * G * t, rho * t, t, E, "isotropic")


def orthotropic(E1, E2, nu12, G12, t, rho, G13=None, G23=None, k_s=5 / 6) -> ShellSection:
    Q = plane_stress_Q(E1, E2, nu12, G12)
    return ShellSection(Q * t, Q * t**3 / 12, np.diag([k_s * (G13 or G12) * t, k_s * (G23 or G12) * t]), rho * t, t,
                        E1, "orthotropic")


def laminate(layers) -> ShellSection:
    """Symmetric stack, ``layers`` = [(t, Q(3×3), G_transverse, rho, angle_rad), …] bottom → top.
    A = Σ Q̄ t, D = Σ Q̄ (z_k³ − z_{k−1}³)/3; A_s from the equivalent shear compliance h²/Σ(t/G) with k = 5/6 for a
    homogeneous stack (reduces to Allen's G_c d²/t_c for a thin-face sandwich)."""
    h = sum(L[0] for L in layers)
    z = -h / 2
    A, D = np.zeros((3, 3)), np.zeros((3, 3))
    comp, rhoA = 0.0, 0.0
    for t, Q, Gt, rho, ang in layers:
        T = _Tbar(ang)
        Qb = T.T @ Q @ T
        A += Qb * t
        D += Qb * ((z + t) ** 3 - z**3) / 3
        comp += t / Gt
        rhoA += rho * t
        z += t
    Gs = h / comp
    ks = 5 / 6 if len({round(L[2], 3) for L in layers}) == 1 else 1.0
    return ShellSection(A, D, np.eye(2) * ks * Gs * h, rhoA, h, 0.0, "laminate")


def sandwich(E_f, nu_f, t_face, core_E, core_G, t_core, rho_f, rho_c) -> ShellSection:
    """Two equal isotropic faces + core (core in-plane stiffness included)."""
    Gf = E_f / (2 * (1 + nu_f))
    Qf = plane_stress_Q(E_f, E_f, nu_f, Gf)
    nu_c = 0.3
    Qc = plane_stress_Q(core_E, core_E, nu_c, core_G)
    if t_core <= 0:
        s = isotropic(E_f, nu_f, 2 * t_face, rho_f)
        return s
    s = laminate([(t_face, Qf, Gf, rho_f, 0.0), (t_core, Qc, core_G, rho_c, 0.0), (t_face, Qf, Gf, rho_f, 0.0)])
    # transverse shear stiffness of a sandwich: S = G_c d²/t_c, d = t_c + t_f (Allen 1969, Eq. 2.5; Zenkert 1995)
    d = t_core + t_face
    s.As = np.eye(2) * core_G * d**2 / t_core
    s.E_face, s.note = E_f, "sandwich"
    return s
