"""Parametric first-cut geometry, with the structural layout embedded in it.

Sources
-------
* Trapezoidal wing relations (MAC, spanwise MAC station, sweep conversion):
  Raymer 6th ed. Sec. 7.3 (Fig. 7.5, Eqs. 7.5–7.10); Torenbeek (1982) App. A.
* Wetted areas: Raymer Sec. 7.4 (wing Swet = Sexp (1.977 + 0.52 t/c), Eq. 7.12);
  fuselage body of revolution: Torenbeek, *Synthesis of Subsonic Airplane Design*
  (1982), App. F: Swet = pi D L (1 - 2/f)^(2/3) (1 + 1/f^2) for streamlined bodies.
* Tail sizing by volume coefficients: Raymer Sec. 6.4, Eqs. 6.28–6.29, Table 6.4.
* Fuselage length statistics: Raymer Table 6.3 (L = a W0^C, ft & lb).
* Structural layout defaults (spar chord stations, rib pitch, frame pitch):
  Niu, *Airframe Structural Design* (1988), Ch. 8 (wing box) and Ch. 11 (fuselage)
  typical ranges. These are *parameters*, analysed in Phase 2 (see structures.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

LB, FT = 0.45359237, 0.3048

# Raymer Table 6.3: fuselage length L[ft] = a W0[lb]^C
RAYMER_FUSELAGE_LENGTH = {
    "sailplane_unpowered": (0.86, 0.48), "sailplane_powered": (0.71, 0.48),
    "homebuilt_metal_wood": (3.68, 0.23), "homebuilt_composite": (3.50, 0.23),
    "ga_single_engine": (4.37, 0.23), "ga_twin_engine": (0.86, 0.42), "agricultural": (4.04, 0.23),
    "twin_turboprop": (0.37, 0.51), "flying_boat": (1.05, 0.40), "jet_trainer": (0.79, 0.41),
    "jet_fighter": (0.93, 0.39), "military_cargo_bomber": (0.23, 0.50), "jet_transport": (0.67, 0.43),
}
# Raymer Table 6.4: (c_HT, c_VT)
RAYMER_TAIL_VOLUME = {
    "sailplane": (0.50, 0.02), "homebuilt": (0.50, 0.04), "ga_single_engine": (0.70, 0.04),
    "ga_twin_engine": (0.80, 0.07), "agricultural": (0.50, 0.04), "twin_turboprop": (0.90, 0.08),
    "flying_boat": (0.70, 0.06), "jet_trainer": (0.70, 0.06), "jet_fighter": (0.40, 0.07),
    "military_cargo_bomber": (1.00, 0.08), "jet_transport": (1.00, 0.09),
}


@dataclass
class WingBoxLayout:
    """Parametric wing-box structure, defined in the wing's own coordinates so it
    morphs with the geometry variables (span, chords, t/c). Defaults: Niu (1988) Ch. 8."""

    front_spar_xc: float = 0.20
    rear_spar_xc: float = 0.65
    rib_pitch: float | None = None  # [m]; None -> 0.6 * MAC (ASSUMPTION; used by the Phase 2 box sizing)
    skin_thickness: float = 1.0e-3  # [m] initial; Phase 2 sizes it in structures.box_beam_sizing
    spar_cap_area: float = 50e-6  # [m^2] initial; Phase 2 sizes it in structures.box_beam_sizing
    material: str = "al2024_t3"

    def box_width(self, chord: float) -> float:
        return (self.rear_spar_xc - self.front_spar_xc) * chord


@dataclass
class TrapezoidalWing:
    S: float  # reference (trapezoidal, through fuselage) area [m^2]
    AR: float
    taper: float = 0.5
    sweep_c4: float = 0.0  # [rad]
    tc_root: float = 0.12
    tc_tip: float = 0.12
    xc_max_t: float = 0.30  # chordwise station of max thickness (form factor, Raymer Eq. 12.30)
    dihedral: float = math.radians(3)
    airfoil: str = "NACA 23015"
    box: WingBoxLayout = field(default_factory=WingBoxLayout)

    @property
    def span(self) -> float:
        return math.sqrt(self.AR * self.S)

    @property
    def c_root(self) -> float:
        return 2 * self.S / (self.span * (1 + self.taper))

    @property
    def c_tip(self) -> float:
        return self.taper * self.c_root

    @property
    def mac(self) -> float:
        """Raymer Eq. 7.5: c̄ = (2/3) c_r (1+λ+λ²)/(1+λ)."""
        lam = self.taper
        return 2 / 3 * self.c_root * (1 + lam + lam**2) / (1 + lam)

    @property
    def y_mac(self) -> float:
        """Raymer Eq. 7.6: Ȳ = (b/6)(1+2λ)/(1+λ)."""
        lam = self.taper
        return self.span / 6 * (1 + 2 * lam) / (1 + lam)

    def sweep_at(self, xc: float) -> float:
        """Sweep of the x/c line from the quarter-chord sweep (standard planform relation,
        e.g. DATCOM Sec. 2.2.2 / Raymer Sec. 7.3): tan Λn = tan Λm − 4/AR · (n−m)(1−λ)/(1+λ)."""
        lam = self.taper
        return math.atan(math.tan(self.sweep_c4) - 4 / self.AR * (xc - 0.25) * (1 - lam) / (1 + lam))

    @property
    def tc_mean(self) -> float:
        return 0.5 * (self.tc_root + self.tc_tip)

    def exposed_area(self, fuselage_width: float) -> float:
        """Area outboard of the fuselage side (trapezoid, linear chord)."""
        b = self.span
        y0 = min(fuselage_width / 2, 0.45 * b)
        c_at = self.c_root + (self.c_tip - self.c_root) * (2 * y0 / b)
        return 2 * 0.5 * (c_at + self.c_tip) * (b / 2 - y0)

    def wetted_area(self, fuselage_width: float = 0.0) -> float:
        """Raymer Eq. 7.12 (t/c > 0.05): Swet = Sexp (1.977 + 0.52 t/c)."""
        return self.exposed_area(fuselage_width) * (1.977 + 0.52 * self.tc_mean)

    def summary(self) -> dict:
        return {"S_m2": self.S, "AR": self.AR, "span_m": self.span, "taper": self.taper,
                "c_root_m": self.c_root, "c_tip_m": self.c_tip, "MAC_m": self.mac, "y_MAC_m": self.y_mac,
                "sweep_c4_deg": math.degrees(self.sweep_c4), "sweep_LE_deg": math.degrees(self.sweep_at(0.0)),
                "t/c": self.tc_mean}


@dataclass
class FuselageFrameLayout:
    """Parametric fuselage structure (Niu 1988, Ch. 11): frames, longerons, skin."""

    frame_pitch: float = 0.5  # [m] (light aircraft: ~0.4–0.6 m)
    n_longerons: int = 4
    skin_thickness: float = 0.8e-3


@dataclass
class Fuselage:
    length: float
    max_diameter: float
    frames: FuselageFrameLayout = field(default_factory=FuselageFrameLayout)

    @property
    def fineness(self) -> float:
        return self.length / self.max_diameter

    def wetted_area(self) -> float:
        """Torenbeek (1982) App. F body-of-revolution approximation."""
        f = self.fineness
        return math.pi * self.max_diameter * self.length * (1 - 2 / f) ** (2 / 3) * (1 + 1 / f**2)

    @staticmethod
    def from_raymer(W0_kg: float, aircraft_class: str, fineness: float = 7.0) -> "Fuselage":
        a, C = RAYMER_FUSELAGE_LENGTH[aircraft_class]
        L = a * (W0_kg / LB) ** C * FT
        return Fuselage(L, L / fineness)


@dataclass
class TailSurface:
    S: float
    AR: float
    taper: float
    arm: float  # wing MAC/4 -> tail MAC/4 [m]
    tc: float = 0.10
    sweep_c4: float = 0.0

    def as_wing(self) -> TrapezoidalWing:
        return TrapezoidalWing(self.S, self.AR, self.taper, self.sweep_c4, self.tc, self.tc)


def size_tails(wing: TrapezoidalWing, arm: float, c_ht: float, c_vt: float,
               ar_h: float = 4.0, ar_v: float = 1.5, taper_h: float = 0.6, taper_v: float = 0.5):
    """Tail areas from volume coefficients (Raymer Eqs. 6.28–6.29):
    S_HT = c_HT c̄_W S_W / L_HT;  S_VT = c_VT b_W S_W / L_VT.
    Aspect ratio/taper defaults within Raymer Table 4.3 ranges."""
    S_h = c_ht * wing.mac * wing.S / arm
    S_v = c_vt * wing.span * wing.S / arm
    return TailSurface(S_h, ar_h, taper_h, arm), TailSurface(S_v, ar_v, taper_v, arm, sweep_c4=math.radians(20))


@dataclass
class Configuration:
    wing: TrapezoidalWing
    fuselage: Fuselage
    htail: TailSurface
    vtail: TailSurface
    extra_drag_areas: dict[str, float] = field(default_factory=dict)  # D/q [m^2] (gear, antennas...)

    def wetted_areas(self) -> dict[str, float]:
        return {"wing": self.wing.wetted_area(self.fuselage.max_diameter), "fuselage": self.fuselage.wetted_area(),
                "htail": self.htail.as_wing().wetted_area(), "vtail": self.vtail.as_wing().wetted_area()}
