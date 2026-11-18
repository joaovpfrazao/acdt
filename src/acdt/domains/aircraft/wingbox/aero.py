"""Low-fidelity wing aerodynamics for the Phase 5 loop.

* Section data from NeuralFoil (Sharpe 2024, MIT) on continuous NACA 4-digit coordinates: cl(α), cd(cl), cm,
  a₀, α_L0, cl_max — cached per (m, p, t/c, Re).
* Prandtl lifting line, Glauert's Fourier solution of the monoplane equation (Anderson, *Fundamentals of
  Aerodynamics*, §5.3; Glauert 1926): symmetric loading, odd terms, collocation in (0, π/2].
  α_eff(θ) − α_L0(θ) = Σ A_n sin nθ (4b/(a₀ c) + n/sin θ);  C_L = π AR A₁,  C_Di = π AR Σ n A_n²,
  local c·cl = 4b Σ A_n sin nθ.
* Static aero-elastic coupling: twist θ_e(y) = ∫ T/GJ about the shear-centre axis (streamwise twist for an unswept
  wing, the two examples' Λ ≈ 0), iterated with the span load (fixed point; diverges only above q_D)."""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from .section import naca4


@lru_cache(maxsize=512)
def section_polar(m: float, p: float, tc: float, Re: float):
    import neuralfoil as nf
    xu, zu, xl, zl = naca4(m, p, tc, 101)
    co = np.vstack([np.c_[xu[::-1], zu[::-1]], np.c_[xl[1:], zl[1:]]])
    al = np.linspace(-8, 22, 61)
    a = nf.get_aero_from_coordinates(co, alpha=al, Re=Re, model_size="large")
    cl, cd, cm = np.asarray(a["CL"]), np.asarray(a["CD"]), np.asarray(a["CM"])
    i0 = np.searchsorted(cl, 0.0)
    lin = (al >= -4) & (al <= 4)
    a0 = float(np.polyfit(np.radians(al[lin]), cl[lin], 1)[0])
    aL0 = float(np.radians(np.interp(0.0, cl[: np.argmax(cl) + 1], al[: np.argmax(cl) + 1])))
    k = int(np.argmax(cl))
    cm0 = float(np.interp(0.0, cl[: k + 1], cm[: k + 1]))
    return {"alpha": al, "cl": cl, "cd": cd, "cm": cm, "a0": a0, "alpha_L0": aL0, "cm0": cm0,
            "clmax": float(cl[k]), "alpha_clmax": float(al[k]), "i0": int(i0),
            "conf": float(np.mean(np.asarray(a["analysis_confidence"])[lin]))}


def cd_of_cl(pol, cl):
    k = int(np.argmax(pol["cl"]))
    c, d = pol["cl"][: k + 1], pol["cd"][: k + 1]
    lo = int(np.argmin(d))     # use the branch from cd_min upwards for cl > cl(cd_min), downwards otherwise
    cl = np.asarray(cl, float)
    up = np.interp(cl, c[lo:], d[lo:])
    dn = np.interp(cl, c[: lo + 1], d[: lo + 1])
    return np.where(cl >= c[lo], up, dn)


class LiftingLine:
    """Glauert solution on a straight tapered wing (full span b, chord c(|y|)); ``n`` odd terms."""

    def __init__(self, span: float, chord_fn, n: int = 24):
        self.b, self.n = span, n
        self.th = np.arange(1, n + 1) * (math.pi / 2) / n          # (0, π/2]
        self.y = 0.5 * span * np.cos(self.th)                       # semispan stations, tip → root
        self.c = chord_fn(self.y)
        self.S = 2 * np.trapezoid(chord_fn(np.linspace(0, span / 2, 201)), np.linspace(0, span / 2, 201))
        self.AR = span**2 / self.S
        self.nn = 2 * np.arange(n) + 1

    def solve(self, alpha_eff_minus_L0, a0):
        """A_n for the given (α + twist − α_L0)(θ) and section slope a₀(θ) (arrays at self.th)."""
        th, nn = self.th[:, None], self.nn[None, :]
        Mx = np.sin(nn * th) * (4 * self.b / (a0[:, None] * self.c[:, None]) + nn / np.sin(th))
        return np.linalg.solve(Mx, alpha_eff_minus_L0)

    def coeffs(self, A):
        CL = math.pi * self.AR * A[0]
        CDi = math.pi * self.AR * float(np.sum(self.nn * A**2))
        ccl = 4 * self.b * np.sin(np.outer(self.th, self.nn)) @ A      # c·cl = 4b Σ A_n sin nθ (l = ρVΓ, Γ = 2bV ΣA_n sin nθ)
        return CL, CDi, ccl

    def trim(self, CL_target, twist, a0, aL0):
        """Root α giving CL_target (linear in α): returns α, A, CL, CDi, c·cl."""
        A1 = self.solve(np.ones_like(self.th), a0)          # response to unit α
        A0 = self.solve(twist - aL0, a0)
        CL1, CL0 = math.pi * self.AR * A1[0], math.pi * self.AR * A0[0]
        al = (CL_target - CL0) / CL1
        A = A0 + al * A1
        CL, CDi, ccl = self.coeffs(A)
        return al, A, CL, CDi, ccl
