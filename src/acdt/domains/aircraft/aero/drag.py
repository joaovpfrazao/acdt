"""Parasite and induced drag (Raymer 6th ed. Ch. 12 'component build-up').

CD0 = Σ(Cf_c FF_c Q_c S_wet,c)/S_ref + Σ(D/q)_misc/S_ref + CD_L&P      (Raymer Eq. 12.24)

* Skin friction: laminar Cf = 1.328/√Re (Eq. 12.25 / Blasius); turbulent
  Cf = 0.455/((log10 Re)^2.58 (1+0.144 M²)^0.65) (Eq. 12.26, Prandtl–Schlichting
  with compressibility); cutoff Reynolds number for surface roughness
  Re_cutoff = 38.21 (l/k)^1.053 (Eq. 12.28, subsonic). Roughness k from Table 12.5.
* Form factors: wing/tail FF = [1 + 0.6/(x/c)_m (t/c) + 100 (t/c)^4][1.34 M^0.18 (cos Λ_m)^0.28]
  (Eq. 12.30); fuselage FF = 1 + 60/f³ + f/400 (Eq. 12.31); nacelle FF = 1 + 0.35/f (Eq. 12.32).
* Interference factors Q: Raymer Sec. 12.5.5.
* Leakage & protuberance as a fraction of CD0 (Raymer Sec. 12.5.9).
* Equivalent skin-friction first guess (pre-geometry): CD0 = Cfe Swet/Sref (Eq. 12.23, Table 12.3).
* Oswald efficiency: Raymer Eq. 12.48 (straight wing) and 12.49 (Λ_LE > 30°).
* Parabolic polar CD = CD0 + K CL², K = 1/(π A e) and (L/D)max = 1/(2√(CD0 K))
  (Anderson, *Aircraft Performance and Design*, Ch. 2 & 5).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

__all__ = ["skin_friction", "ff_lifting_surface", "ff_body", "ff_nacelle", "oswald_raymer", "DragPolar",
           "ComponentDrag", "component_buildup", "ROUGHNESS", "CFE_RAYMER", "cd0_equivalent_skin_friction"]

FT = 0.3048
# Raymer Table 12.5: skin roughness k [ft] -> m
ROUGHNESS = {
    "camouflage_paint_al": 3.33e-5 * FT, "smooth_paint": 2.08e-5 * FT, "production_sheet_metal": 1.33e-5 * FT,
    "polished_sheet_metal": 0.50e-5 * FT, "smooth_molded_composite": 0.17e-5 * FT,
}
# Raymer Table 12.3: equivalent skin-friction coefficient Cfe
CFE_RAYMER = {
    "bomber_civil_transport": 0.0030, "military_cargo": 0.0035, "air_force_fighter": 0.0035,
    "navy_fighter": 0.0040, "clean_supersonic_cruise": 0.0025, "light_single_engine": 0.0055,
    "light_twin": 0.0045, "prop_seaplane": 0.0065, "jet_seaplane": 0.0040,
}


def cd0_equivalent_skin_friction(cfe: float, swet_sref: float) -> float:
    """Raymer Eq. 12.23: CD0 = Cfe · Swet/Sref."""
    return cfe * swet_sref


def skin_friction(Re: float, mach: float = 0.0, laminar_fraction: float = 0.0, length: float | None = None,
                  roughness: float | None = None) -> float:
    """Flat-plate Cf, mixed laminar/turbulent by area-weighting (Raymer Sec. 12.5.3).
    Re is limited to the roughness cutoff (Raymer Eq. 12.28) if length & k are given."""
    if length is not None and roughness:
        Re = min(Re, 38.21 * (length / roughness) ** 1.053)
    cf_t = 0.455 / (math.log10(Re) ** 2.58 * (1 + 0.144 * mach**2) ** 0.65)
    cf_l = 1.328 / math.sqrt(Re)
    return laminar_fraction * cf_l + (1 - laminar_fraction) * cf_t


def ff_lifting_surface(tc: float, xc_max: float, mach: float, sweep_maxt: float) -> float:
    """Raymer Eq. 12.30."""
    return (1 + 0.6 / xc_max * tc + 100 * tc**4) * (1.34 * mach**0.18 * math.cos(sweep_maxt) ** 0.28)


def ff_body(fineness: float) -> float:
    """Raymer Eq. 12.31: FF = 1 + 60/f³ + f/400."""
    return 1 + 60 / fineness**3 + fineness / 400


def ff_nacelle(fineness: float) -> float:
    """Raymer Eq. 12.32: FF = 1 + 0.35/f."""
    return 1 + 0.35 / fineness


def oswald_raymer(AR: float, sweep_le: float = 0.0) -> float:
    """Raymer Eq. 12.48 (straight) / 12.49 (swept, Λ_LE > 30°)."""
    if abs(sweep_le) <= math.radians(30):
        return 1.78 * (1 - 0.045 * AR**0.68) - 0.64
    return 4.61 * (1 - 0.045 * AR**0.68) * math.cos(sweep_le) ** 0.15 - 3.1


@dataclass
class DragPolar:
    """Parabolic polar CD = CD0 + K CL² (Raymer Eq. 12.5), optionally with a camber-flap envelope correction
    ``camber`` (:class:`.camber_flap.CamberSchedule`): CD(CL) += ΔCD_env(CL) ≤ 0, the profile-drag saving of the
    best flap setting at that CL (Thomas, *Fundamentals of Sailplane Design*, Ch. 3). With ``camber`` the
    optimum-CL properties are found numerically on the envelope polar."""
    CD0: float
    K: float  # induced drag factor 1/(pi A e)
    camber: object | None = None

    @classmethod
    def from_oswald(cls, CD0: float, AR: float, e: float) -> "DragPolar":
        return cls(CD0, 1 / (math.pi * AR * e))

    def CD(self, CL):
        cd = self.CD0 + self.K * np.asarray(CL) ** 2
        if self.camber is not None:
            cd = cd + self.camber.dcd(CL)
        return cd

    def dcd(self, CL):
        """Camber-flap envelope correction ΔCD(CL) (0 without camber flaps)."""
        return self.camber.dcd(CL) if self.camber is not None else 0.0 * np.asarray(CL, float)

    def _num_opt(self, p: float) -> float:
        """CL maximising CL^p / CD on the envelope polar (p = 1: L/D max; p = 1.5: minimum power)."""
        hi = min(self.camber.CL[-1], 3.0 * math.sqrt(3 * self.CD0 / self.K))
        cl = np.linspace(0.05, hi, 600)
        return float(cl[int(np.argmax(cl**p / self.CD(cl)))])

    @property
    def LD_max(self) -> float:
        if self.camber is not None:
            cl = self.CL_LDmax
            return cl / float(self.CD(cl))
        return 1 / (2 * math.sqrt(self.CD0 * self.K))

    @property
    def CL_LDmax(self) -> float:
        return self._num_opt(1.0) if self.camber is not None else math.sqrt(self.CD0 / self.K)

    @property
    def CL_min_power(self) -> float:
        """CL for minimum power required, √(3 CD0/K) (Anderson APD Ch. 5); numerical with camber flaps."""
        return self._num_opt(1.5) if self.camber is not None else math.sqrt(3 * self.CD0 / self.K)

    @property
    def LD_min_power(self) -> float:
        cl = self.CL_min_power
        return cl / float(self.CD(cl))  # = 0.866 (L/D)max

    def speed_for_CL(self, CL: float, wing_loading: float, rho: float) -> float:
        return math.sqrt(2 * wing_loading / (rho * CL))


@dataclass
class ComponentDrag:
    name: str
    Swet: float
    Cf: float
    FF: float
    Q: float

    @property
    def f(self) -> float:  # equivalent flat-plate area Cf FF Q Swet [m^2]
        return self.Cf * self.FF * self.Q * self.Swet


@dataclass
class BuildupResult:
    CD0: float
    components: list[ComponentDrag] = field(default_factory=list)
    misc_dq: float = 0.0
    lp_fraction: float = 0.0

    def table(self, Sref: float) -> list[dict]:
        return [{"component": c.name, "Swet_m2": c.Swet, "Cf": c.Cf, "FF": c.FF, "Q": c.Q, "CD0": c.f / Sref}
                for c in self.components]


def component_buildup(config, V: float, rho: float, mu: float, a: float, laminar: dict | None = None,
                      roughness: float = ROUGHNESS["smooth_paint"], Q: dict | None = None,
                      lp_fraction: float = 0.05) -> BuildupResult:
    """Raymer Eq. 12.24 for a :class:`acdt.domains.aircraft.geometry.Configuration`."""
    M = V / a
    laminar = {"wing": 0.10, "htail": 0.10, "vtail": 0.10, "fuselage": 0.0, **(laminar or {})}
    Q = {"wing": 1.0, "fuselage": 1.0, "htail": 1.04, "vtail": 1.04, **(Q or {})}
    w = config.wing
    sw = config.wetted_areas()
    comps = []
    for name, surf in (("wing", w), ("htail", config.htail.as_wing()), ("vtail", config.vtail.as_wing())):
        L = surf.mac
        Re = rho * V * L / mu
        cf = skin_friction(Re, M, laminar[name], L, roughness)
        ff = ff_lifting_surface(surf.tc_mean, surf.xc_max_t, M, surf.sweep_at(surf.xc_max_t))
        comps.append(ComponentDrag(name, sw[name], cf, ff, Q[name]))
    fus = config.fuselage
    Re = rho * V * fus.length / mu
    cf = skin_friction(Re, M, laminar["fuselage"], fus.length, roughness)
    comps.append(ComponentDrag("fuselage", sw["fuselage"], cf, ff_body(fus.fineness), Q["fuselage"]))
    dq = sum(config.extra_drag_areas.values())
    cd0 = (sum(c.f for c in comps) + dq) / w.S
    cd0 *= 1 + lp_fraction
    return BuildupResult(cd0, comps, dq, lp_fraction)
