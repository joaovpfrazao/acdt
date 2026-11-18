# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Runnable numbers: camber profile ΔCD vs +trim vs +gap (synthetic section, no XFOIL).

Run: PYTHONPATH=src python examples/camber/trim_gap_demo.py
"""
from types import SimpleNamespace

import numpy as np

from acdt.domains.aircraft.aero.airfoil import AirfoilPolar
from acdt.domains.aircraft.aero.camber_flap import (
    CamberSchedule, SectionEnvelope, apply_trim_and_gap,
)


def polar(cm0):
    alpha = np.linspace(-4.0, 14.0, 25)
    cl = 0.1 + 0.1 * alpha
    cl = np.clip(cl, -0.4, 1.4)
    cd = 0.01 + 0.04 * (cl - 0.25) ** 2
    cm = np.full_like(cl, cm0)
    return AirfoilPolar("SYN", 1e6, 0.0, alpha, cl, cd, cm, source="synthetic PRESSUPOSTO")


def main():
    deltas = [-5.0, 0.0, 5.0, 10.0]
    # Stronger Δcm0 so HT trim CD is visible in the printed totals (synthetic PRESSUPOSTO).
    sec = SectionEnvelope("SYN", 1e6, 0.8, deltas,
                          [polar(-0.02 - 0.08 * (d / 5.0)) for d in deltas], 0.15, "synthetic")
    CL = np.linspace(0.25, 1.0, 16)
    dCD = -0.0025 * np.ones_like(CL)
    delta = np.linspace(-3.0, 9.0, CL.size)
    base = CamberSchedule("camber", CL, dCD.copy(), delta, 0.90, 0.40, 0.25, 10.0, 0.02, section=sec, opts={})
    cfg = SimpleNamespace(wing=SimpleNamespace(S=12.0, mac=1.1, span=11.0),
                          htail=SimpleNamespace(S=2.4, arm=5.5, AR=4.5))

    def run(label, opts):
        sch = CamberSchedule("camber", CL, dCD.copy(), delta, 0.90, 0.40, 0.25, 10.0, 0.02,
                             section=sec, opts={}, notes=[])
        apply_trim_and_gap(sch, cfg, opts)
        c = float(sch.CL[-1])  # high-CL end of the two-point envelope (largest |δ| here)
        trim_v = (float(np.interp(c, sch.CL, sch.dCD_trim)) if sch.dCD_trim is not None else 0.0)
        gap_v = float(sch.dCD_gap or 0.0) if sch.gap_drag_status == "assessed" else None
        tmax = float(np.max(sch.dCD_trim)) if sch.dCD_trim is not None else 0.0
        print(f"{label}: CL={c:.2f} δ={float(sch.delta_at(c)):.1f}°  "
              f"profile={float(np.interp(c, sch.CL, sch.dCD)):.5f}  "
              f"dCD_trim={trim_v:.5f} (max {tmax:.5f})  dCD_gap={gap_v}  "
              f"total_dcd={float(sch.dcd(c)):.5f}  "
              f"trim={sch.trim_drag_status}  gap={sch.gap_drag_status}")
        return sch

    common = dict(kind="camber", chord_ratio=0.2, eta_in=0.0, eta_out=0.65,
                  deltas_deg=deltas, cl_margin=0.15, actuators=2, landing_deflection=True,
                  trim_e_ht=0.8, trim_SM=0.1, actuator_mass_kg=None, surface_mass_kg_m2=None,
                  actuator_cost_usd=0.0)
    run("omitted (legacy)", {**common, "trim_drag": False, "gap": None})
    run("trim on", {**common, "trim_drag": True, "gap": None})
    run("trim+gap dCD", {**common, "trim_drag": True,
                         "gap": {"dCD": 0.0012, "source": "PRESSUPOSTO demo — replace with DATCOM/test"}})
    run("trim+sealed gap", {**common, "trim_drag": True,
                            "gap": {"sealed": True, "source": "XFOIL GDES/FLAP sealed-gap assumption"}})
    sch_u = run("gap/c only (unassessed)", {**common, "trim_drag": True,
                                            "gap": {"chord_ratio": 0.005, "source": "measured"}})
    assert sch_u.gap_drag_status == "unassessed"


if __name__ == "__main__":
    main()
