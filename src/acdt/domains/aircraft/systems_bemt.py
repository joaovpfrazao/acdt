# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in BEMT propeller sizing for the systems cycle (Phase 1E).

Reuses the existing McCormick / Glauert / Ning blade-element/momentum solver
in :mod:`acdt.domains.aircraft.propeller` (already used in Phase 9
performance). This module does **not** invent a second BEMT or a propeller
catalogue.

Default systems behaviour remains Raymer Sec. 10.3 statistics + a user
C_P / J (`electric_propulsion.size_propeller`). Request BEMT with
``systems.propeller.method: bemt``. Missing diameter/tip-Mach, pitch or
auto-design speed, chord or auto-design speed, section polar (named airfoil
or a sourced table), or rated rpm → the term is unassessed; the statistical
path is not silently presented as a BEMT result.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from acdt.core.atmosphere import isa
from acdt.core.systems.electric_propulsion import PropellerSizing
from acdt.domains.aircraft.propeller import SectionPolar, make_propeller

BEMT_SOURCE = ("McCormick, Aerodynamics, Aeronautics and Flight Mechanics, 2nd ed., 1995, Ch. 6; "
               "Glauert in Durand, Aerodynamic Theory Vol. IV, 1935; Ning, Wind Energy 17, 2014; "
               "Adkins & Liebeck, J. Aircraft 31(2), 1994 (design-cl / auto pitch and chord)")


def section_polar_from_cfg(cfg: dict) -> tuple[SectionPolar | None, list[str], list[str]]:
    """Build a section polar. Named airfoil or a sourced (alpha, cl, cd) table. No invented vendor polars."""
    notes, un = [], []
    sec = cfg.get("section")
    if isinstance(sec, dict):
        src = sec.get("source")
        if not (isinstance(src, str) and src.strip()):
            return None, notes, ["section.source missing — polar not applied (unassessed≠pass)"]
        try:
            a = np.asarray(sec["alpha_deg"], float)
            cl = np.asarray(sec["cl"], float)
            cd = np.asarray(sec["cd"], float)
        except (KeyError, TypeError, ValueError):
            return None, notes, ["section table needs alpha_deg, cl, cd (numeric arrays)"]
        if a.size < 3 or a.size != cl.size or a.size != cd.size:
            return None, notes, ["section table too short or length mismatch"]
        polar = SectionPolar(a, cl, cd, src.strip())
        notes.append(f"seção tabular: {polar.source}")
        return polar, notes, un
    airfoil = cfg.get("airfoil")
    if not airfoil:
        return None, notes, ["airfoil or sourced section table required for BEMT (no silent Clark-Y)"]
    Re = float(cfg.get("Re", 1.5e5))
    try:
        polar = SectionPolar.from_airfoil(str(airfoil), max(Re, 2e4), prefer=cfg.get("solver", "neuralfoil"))
    except Exception as e:  # noqa: BLE001 — polar tool missing or failed
        return None, notes, [f"section polar unassessed ({airfoil}): {e}"]
    notes.append(f"seção {polar.source}")
    return polar, notes, un


def size_propeller_bemt(cfg: dict, P_shaft_W: float, V_cruise: float, altitude_m: float = 0.0,
                        kind: str = "electric") -> PropellerSizing:
    """BEMT-matched propeller for one motor. Returns ``PropellerSizing`` with status/unassessed_terms."""
    un: list[str] = []
    notes: list[str] = [BEMT_SOURCE]
    cfg = dict(cfg or {})
    empty = PropellerSizing(float("nan"), float("nan"), float("nan"), float("nan"), float("nan"),
                            "BEMT unassessed", method="bemt", status="unassessed")

    if not cfg.get("rpm_rated"):
        un.append("rpm_rated")
    if not cfg.get("diameter_m") and not cfg.get("tip_mach"):
        un.append("diameter_m or tip_mach")
    if cfg.get("tip_mach") and not (V_cruise and cfg.get("rpm_rated")):
        un.append("tip_mach needs V_cruise and rpm_rated")
    polar, pn, pu = section_polar_from_cfg(cfg)
    notes += pn
    un += pu
    pitch, chord = cfg.get("pitch_m", "auto"), cfg.get("chord_075_over_D", "auto")
    if pitch in (None, "auto") and not V_cruise:
        un.append("pitch_m 'auto' needs a design (cruise) speed")
    if chord in (None, "auto") and not V_cruise:
        un.append("chord_075_over_D 'auto' needs a design (cruise) speed")
    if not P_shaft_W or not math.isfinite(float(P_shaft_W)) or float(P_shaft_W) <= 0:
        un.append("P_shaft_W")
    if un:
        empty.unassessed_terms = un
        empty.notes = notes + ["BEMT pedido mas inputs em falta — não se usa a estatística Raymer como resultado BEMT"]
        empty.note = "BEMT unassessed: " + "; ".join(un)
        return empty

    try:
        prop = make_propeller(cfg, float(P_shaft_W), kind, V_design=V_cruise, h_design=altitude_m or 0.0,
                             n_props=1, polar=polar)
    except Exception as e:  # noqa: BLE001
        empty.unassessed_terms = [f"BEMT solve failed: {e}"]
        empty.notes = notes
        empty.note = str(e)
        return empty

    h = altitude_m or 0.0
    at = isa(h)
    op = prop.operating_point(V_cruise, h, 1.0)
    tip = math.sqrt((math.pi * (op["rpm"] / 60.0) * prop.D) ** 2 + V_cruise ** 2) / at.a
    # static / max-power rpm (full throttle, V=0) for motor Kv targeting, as in size_propeller
    st = prop.operating_point(0.0, 0.0, 1.0)
    ps = PropellerSizing(
        float(prop.D), float(st["rpm"]), float(op["rpm"]), float(op["J"]), float(tip),
        "BEMT (McCormick 1995 Ch. 6 / Ning 2014); " + "; ".join(prop.notes[:2]),
        method="bemt", status="ok", eta_cruise=float(op["eta"]),
        CT_cruise=float(prop.coeffs(op["J"])[0]), CP_cruise=float(prop.coeffs(op["J"])[1]),
        notes=notes + list(prop.notes),
        polar_source=prop.polar_source,
        pitch_m=float(prop.pitch),
        c075_D=float(prop.c075_D),
        rpm_static=float(st["rpm"]),
        P_shaft_cruise_W=float(op["P"]),
        T_cruise_N=float(op["T"]),
    )
    return ps
