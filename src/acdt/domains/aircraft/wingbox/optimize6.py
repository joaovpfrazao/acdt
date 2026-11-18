"""Phase 6 wing optimisation: the Phase 5 aero-structural problem (:mod:`wingbox.optimize`) with the Phase 6 box
(:mod:`wingbox.sizing6`) — buckling-sized stiffened (metal) or sandwich (composite) covers, spar caps from the spar
cross-section, sized ribs with lightening holes — and the beam stiffness / stress factors calibrated on the
contour shell FEM (:mod:`wingbox.shell6`).

Extra variables: φ_cap (continuous, cap share of the cover + cap area, metal) and the discrete choices n_str
(stringers per cover, metal) and spar section type (I / C / Z / built-up) — enumerated outside SLSQP (each
combination is a separate continuous problem; the cheapest discrete options are pre-screened at the baseline).
Rib-pitch bounds relaxed to 0.4–2.5× the Phase 3 pitch now that the ribs are sized (A3).

Calibration loop: calibrate at the baseline → optimise → recalibrate at the optimum → re-optimise (warm start) →
final FEM check of the optimum (:func:`run_study6`)."""
from __future__ import annotations

import math

import numpy as np

from . import sizing6 as Z
from .optimize import VARS, WingBoxProblem

VARS6 = VARS + ("phi_cap",)


class WingBoxProblem6(WingBoxProblem):
    def __init__(self, res, objective="weight", *, material="metal", n_str=6, spar_type="I", calib=None, **kw):
        self.mat6 = Z.phase6_material(material)
        self.kind = material if isinstance(material, str) else "metal"
        self.n_str = 0 if material == "composite" else int(n_str)
        self.spar_type = spar_type
        self.calib = calib or Z.Calibration()
        super().__init__(res, objective, **kw)

    def _setup(self):
        self.vars = VARS6
        self.x0["phi_cap"] = 0.0 if self.kind == "composite" else 0.15
        self.x0["n_str"] = self.n_str
        self.bounds["phi_cap"] = (0.0, 0.0) if self.kind == "composite" else (0.02, 0.6)
        L0 = self.x0["rib_pitch"]
        self.bounds["rib_pitch"] = (0.4 * L0, 2.5 * L0)
        self.mat = self.mat6
        self.material = self.mat6["name"]

    def _key(self, x):
        return ("p6", self.kind, self.n_str, self.spar_type, id(self.calib)) + tuple(round(float(x[k]), 7)
                                                                                 for k in self.vars)

    def _size(self, w, x, lift_lim, T_lim, wing_mass):
        S = self.S_mod
        G0 = 9.80665
        rel = self.vn.n_limit_pos * G0 * (wing_mass / 2) * self.c / np.trapezoid(self.c, self.y)
        load = S.SpanLoad(self.y, self.c, lift_lim, rel, self.vn.n_limit_pos, "LLT + torção elástica (Fase 6)")
        from .optimize import _cum_from_tip
        V = _cum_from_tip(self.y, load.net)
        M = _cum_from_tip(self.y, V)
        beam = S.BeamLoads(self.y, V, M, T_lim)
        xx = {**x, "n_str": self.n_str}
        box = Z.size_box6(w, beam, self.mat6, xx, y0=self.y0, nonopt=self.nonopt, areal_floor=self.floor,
                          n_neg_ratio=abs(self.vn.n_limit_neg / self.vn.n_limit_pos) if self.vn.n_limit_pos else 0.4,
                          calib=self.calib, spar_type=self.spar_type)
        return box, beam, load

    def _section(self, w, box, x):
        return Z.section6(w, box, self.mat6, camber=(x["camber"], self.p), calib=self.calib, y0=self.y0,
                          le_cell=self.le_cell)

    def free_vars(self):
        return [k for k in self.vars if self.bounds[k][1] > self.bounds[k][0]]

    def set_calibration(self, calib):
        """New FEM factors: re-evaluate the baseline (objective scaling, performance references kept from Phase 5
        baseline semantics — the baseline is re-sized with the new factors)."""
        self.calib = calib
        self.base = None
        self.base = self.evaluate(self.x0)


def screen_discrete(res, objective, material, n_str_list=(0, 2, 4, 6, 8, 10, 12), spar_types=Z.SPAR_TYPES,
                    calib=None, log=print, **kw):
    """Baseline box mass for each discrete option (n_str × spar type) — returns sorted list of
    (mass, n_str, spar_type)."""
    out = []
    ns = (0,) if material == "composite" else n_str_list
    for st in spar_types:
        for n in ns:
            P = WingBoxProblem6(res, objective, material=material, n_str=n, spar_type=st, calib=calib, **kw)
            out.append((P.base.mass_box, n, st))
            log(f"  rastreio: {material} n_str {n:2d} longarina {st:8s} → caixão {P.base.mass_box:.2f} kg")
    out.sort()
    return out
