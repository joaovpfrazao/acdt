"""Atmospheric disturbances for the 6-DOF mission simulator.

* steady wind (speed, direction *from*), NED;
* Dryden continuous turbulence — transfer functions and parameter sets of Beard & McLain, *Small Unmanned
  Aircraft* (2012), Sec. 4.4 and Table 4.1 (after MIL-F-8785C):
  ``H_u = σ_u √(2V/L_u) / (s + V/L_u)``, ``H_v = σ_v √(3V/L_v) (s + V/(√3 L_v)) / (s + V/L_v)²`` (same for w),
  driven by unit-PSD white noise; components in the heading frame (along track, right, down);
* discrete "1 − cos" gusts, CS 25.341(a) shape ``U = U_ds/2 · (1 − cos(π s / H))`` for ``0 ≤ s ≤ 2H``
  (s = distance flown into the gust, H = gust gradient distance), vertical (up +) or lateral.

The field is advanced once per integration step by the mission loop (:meth:`WindField.advance`) and held
constant inside the RK4 sub-steps.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# Beard & McLain (2012) Table 4.1 — Dryden gust model parameters [m, m/s]
DRYDEN_TABLE = {
    ("low", "light"): {"h": 50.0, "L": (200.0, 200.0, 50.0), "sigma": (1.06, 1.06, 0.7)},
    ("low", "moderate"): {"h": 50.0, "L": (200.0, 200.0, 50.0), "sigma": (2.12, 2.12, 1.4)},
    ("medium", "light"): {"h": 600.0, "L": (533.0, 533.0, 533.0), "sigma": (1.5, 1.5, 1.5)},
    ("medium", "moderate"): {"h": 600.0, "L": (533.0, 533.0, 533.0), "sigma": (3.0, 3.0, 3.0)},
}
SOURCE = "Beard & McLain (2012) Sec. 4.4, Table 4.1 (Dryden, MIL-F-8785C)"


def dryden_parameters(h: float, intensity: str) -> dict:
    """Table 4.1 set for altitude ``h`` [m AGL]: 'low' band below 300 m, 'medium' above (PRESSUPOSTO: the
    table gives two altitudes, 50 m and 600 m; the switch at 300 m is ours)."""
    if intensity not in ("light", "moderate"):
        raise ValueError("Dryden: intensity 'light' ou 'moderate' (Beard & McLain Table 4.1); para outro nível "
                         "dar sigma_m_s e L_m explicitamente")
    return DRYDEN_TABLE[("low" if h < 300.0 else "medium", intensity)]


@dataclass
class Gust:
    t0: float                      # start time [s]
    amplitude_m_s: float           # U_ds
    gradient_m: float              # H
    axis: str = "up"               # up | right


@dataclass
class WindField:
    speed_m_s: float = 0.0
    from_deg: float = 0.0
    turbulence: str | None = None          # None | light | moderate
    sigma_m_s: tuple | None = None         # override (u, v, w)
    L_m: tuple | None = None               # override (Lu, Lv, Lw)
    seed: int = 0
    gusts: list = field(default_factory=list)
    scale: float = 1.0                     # 0 disables everything (e.g. extrapolated segments)
    _x: np.ndarray = field(default_factory=lambda: np.zeros(5))
    _a_prev: tuple | None = None
    _cur: np.ndarray = field(default_factory=lambda: np.zeros(3))
    _rng: object = None
    _gust_s: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict | None) -> "WindField":
        d = dict(d or {})
        tb = d.get("turbulence") or {}
        if isinstance(tb, str):
            tb = {"intensity": tb}
        gusts = [Gust(g["t"], g["amplitude_m_s"], g.get("gradient_m", 30.0), g.get("axis", "up"))
                 for g in d.get("gusts", [])]
        return cls(d.get("speed_m_s", 0.0), d.get("from_deg", 0.0), tb.get("intensity"),
                   tuple(tb["sigma_m_s"]) if tb.get("sigma_m_s") is not None else None,
                   tuple(tb["L_m"]) if tb.get("L_m") is not None else None, int(tb.get("seed", 0)), gusts)

    def steady(self) -> np.ndarray:
        a = math.radians(self.from_deg)
        return -self.speed_m_s * np.array([math.cos(a), math.sin(a), 0.0])

    def _params(self, h):
        if self.sigma_m_s is not None:
            return {"L": self.L_m or (533.0, 533.0, 533.0), "sigma": self.sigma_m_s}
        return dryden_parameters(h, self.turbulence)

    def advance(self, t: float, dt: float, Va: float, psi: float, h: float, pos: np.ndarray | None = None) -> None:
        """Advance the Dryden filters by ``dt`` and recompute the current NED wind."""
        Va = max(Va, 1.0)
        turb = np.zeros(3)
        if (self.turbulence or self.sigma_m_s is not None) and self.scale > 0:
            if self._rng is None:
                self._rng = np.random.default_rng(self.seed)
            P = self._params(h)
            (Lu, Lv, Lw), (su, sv, sw) = P["L"], P["sigma"]
            n = self._rng.standard_normal(3) / math.sqrt(dt)   # unit-PSD white noise (discrete)
            x = self._x
            # keep the turbulence continuous when a = V/L changes (altitude band switch, speed change): rescale
            # the filter states to their stationary std for the new a (var x_u = 1/2a; var x1 = 1/4a³, var x2 = 1/4a)
            a_new = (Va / Lu, Va / Lv, Va / Lw)
            if self._a_prev is not None:
                (au0, av0, aw0) = self._a_prev
                x[0] *= math.sqrt(au0 / a_new[0])
                for i, a0, a1 in ((1, av0, a_new[1]), (3, aw0, a_new[2])):
                    x[i] *= math.sqrt((a0 / a1) ** 3)
                    x[i + 1] *= math.sqrt(a0 / a1)
            self._a_prev = a_new
            # u: first order
            au = Va / Lu
            x[0] += dt * (-au * x[0] + n[0])
            turb[0] = su * math.sqrt(2 * au) * x[0]
            # v, w: second order (s + a/√3)/(s + a)², controllable canonical form
            for k, (L, s_, ni) in enumerate(((Lv, sv, n[1]), (Lw, sw, n[2]))):
                a = Va / L
                i = 1 + 2 * k
                x1, x2 = x[i], x[i + 1]
                dx1 = x2
                dx2 = -a * a * x1 - 2 * a * x2 + ni
                x[i] += dt * dx1
                x[i + 1] += dt * dx2
                turb[1 + k] = s_ * math.sqrt(3 * a) * (a / math.sqrt(3) * x[i] + x[i + 1])
        g = np.zeros(3)  # heading frame (along, right, down)
        for j, gu in enumerate(self.gusts):
            if t < gu.t0:
                continue
            s = self._gust_s.get(j, 0.0) + Va * dt
            self._gust_s[j] = s
            if s <= 2 * gu.gradient_m:
                U = 0.5 * gu.amplitude_m_s * (1 - math.cos(math.pi * s / gu.gradient_m))
                if gu.axis == "up":
                    g[2] -= U
                else:
                    g[1] += U
        c, s_ = math.cos(psi), math.sin(psi)
        Rh = np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]])  # heading frame -> NED
        self._cur = self.steady() + self.scale * (Rh @ (turb + g))

    def __call__(self, t, pos) -> np.ndarray:
        return self._cur
