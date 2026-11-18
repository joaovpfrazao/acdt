"""Control-surface hinge moments and servo selection.

* Hinge moment H = C_h q S_c c_c (definition: Roskam, *Airplane Design* Part VI,
  Ch. 10; Etkin & Reid, *Dynamics of Flight*, Ch. 2), with
  C_h = C_hα α + C_hδ δ. C_hα, C_hδ are user inputs here; the DATCOM
  Sec. 6.1.6 / Roskam Part VI method is the foreseen estimator (stub below).
* Design speed: dive speed V_D = 1.25 V_C (14 CFR 23.335(b)(1) legacy rule /
  ASTM F3116) unless a V_D is given.
* Surface geometry defaults within Raymer 6th ed. Sec. 6.5 typical ranges
  (ailerons ~ 50–90 % outer semispan, ~ 20–25 % chord; elevator/rudder 25–50 % chord).
* Servo torque = |H| · linkage ratio · factor of safety (default 1.5, by analogy with
  the structural factor of safety, CS 23.2230 / 14 CFR 25.303).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SurfaceLoad:
    name: str
    area: float
    chord: float
    hinge_moment: float
    torque_required: float
    servo: dict | None
    n_servos: int


def hinge_moment(q: float, S_c: float, c_c: float, Ch_alpha: float, Ch_delta: float, alpha: float,
                 delta: float) -> float:
    """H = (C_hα α + C_hδ δ) q S_c c_c [N m] (Roskam Part VI Ch. 10)."""
    return (Ch_alpha * alpha + Ch_delta * delta) * q * S_c * c_c


def ch_datcom(*args, **kwargs):  # pragma: no cover - Phase 3
    """Foreseen: USAF DATCOM Sec. 6.1.6 (control hinge-moment derivatives) / Roskam Part VI Sec. 10.3."""
    raise NotImplementedError("Phase 3 — DATCOM 6.1.6 hinge-moment derivatives")


def select_servo(servos: list[dict], torque: float, v_bus: float) -> dict | None:
    c = [s for s in servos if s["torque"] >= torque and s["v_max"] >= v_bus]
    return min(c, key=lambda s: s["mass"]) if c else None


def size_control_surfaces(config, V_dive: float, rho: float, servos: list[dict], v_servo: float = 8.4,
                          Ch_alpha: float = -0.25, Ch_delta: float = -0.60, alpha_deg: float = 8.0,
                          delta_deg: float = 25.0, aileron_span_frac: float = 0.35, aileron_chord_frac: float = 0.25,
                          elevator_chord_frac: float = 0.35, rudder_chord_frac: float = 0.35,
                          linkage_ratio: float = 1.0, fos: float = 1.5) -> list[SurfaceLoad]:
    """Size servos for aileron/elevator/rudder at V_D.

    ``Ch_alpha``/``Ch_delta``, deflections and chord/span fractions are **user design assumptions**
    (placeholder defaults, to be replaced by DATCOM Sec. 6.1.6 derivatives — see :func:`ch_datcom`).
    """
    q = 0.5 * rho * V_dive**2
    a, d = math.radians(alpha_deg), math.radians(delta_deg)
    w, ht, vt = config.wing, config.htail.as_wing(), config.vtail.as_wing()
    out = []
    # aileron: outer portion of each semispan, chord at ~75 % semispan
    c_loc = w.c_root + (w.c_tip - w.c_root) * 0.75
    span_a = aileron_span_frac * w.span / 2
    cc = aileron_chord_frac * c_loc
    surfaces = [("aileron (each)", span_a * cc, cc, 2),
                ("elevator", elevator_chord_frac * ht.S, elevator_chord_frac * ht.mac, 1),
                ("rudder", rudder_chord_frac * config.vtail.S, rudder_chord_frac * vt.mac, 1)]
    for name, Sc, c_c, n in surfaces:
        H = abs(hinge_moment(q, Sc, c_c, Ch_alpha, Ch_delta, a, d))
        T = H * linkage_ratio * fos
        out.append(SurfaceLoad(name, Sc, c_c, H, T, select_servo(servos, T, v_servo), n))
    return out
