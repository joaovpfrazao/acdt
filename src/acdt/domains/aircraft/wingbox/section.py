"""Airfoil-contour wing-box sections for :class:`acdt.core.thinwalled.ThinWalledSection`.

Geometry: NACA 4-digit with continuous parameters (camber m, position p, thickness t/c) — Abbott & von Doenhoff,
*Theory of Wing Sections* (1959), §6.4, Eqs. 6.1–6.4 (closed trailing-edge coefficient −0.1036 not used: the
original −0.1015). Covers run on the contour between the spars, inset by the factor ``k_h`` on the thickness
(0.95, the Phase 2/3 allowance for skin/caps depth); webs are straight. Optional D-nose cell: leading-edge skin from
the front spar around the nose (closed cell, as in a riveted LE skin — Megson Ch. 23 "two-cell wing" examples).
The trailing-edge region is open (control surfaces) and not included.

Smeared stiffened covers (Phase 3 metal): the wall shear thickness is the skin t_s while its direct-stress
thickness is t̄ (skin + stringers); represented with E_ratio = t̄/t_s on the wall (exact for the idealisation)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from acdt.core.thinwalled import ThinWalledSection


# NACA 5-digit standard mean lines 210…250 (Abbott & von Doenhoff 1959, §6.6): (m, k1)
NACA5_MEANLINE = {"210": (0.0580, 361.4), "220": (0.1260, 51.64), "230": (0.2025, 15.957),
                  "240": (0.2900, 6.643), "250": (0.3910, 3.230)}


def camber_from_name(airfoil: str):
    """('4', m, p) for NACA 4-digit, ('5', m_ml, k1) for the standard 5-digit mean lines, else ('4', 0, 0.4)."""
    d = airfoil.upper().replace("NACA", "").strip()
    if d.isdigit() and len(d) == 4:
        return ("4", int(d[0]) / 100, int(d[1]) / 10 or 0.4)
    if d.isdigit() and len(d) == 5 and d[:3] in NACA5_MEANLINE:
        return ("5",) + NACA5_MEANLINE[d[:3]]
    return ("4", 0.0, 0.4)


def naca4(m: float, p: float, t: float, n: int = 161, five=None):
    """Upper and lower surfaces (x, z) of a NACA 4-digit section with continuous m, p, t (chord 1),
    cosine spacing. Returns (xu, zu, xl, zl)."""
    beta = np.linspace(0, np.pi, n)
    x = 0.5 * (1 - np.cos(beta))
    yt = 5 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1015 * x**4)
    if five is not None:
        r, k1 = five
        yc = np.where(x < r, k1 / 6 * (x**3 - 3 * r * x**2 + r**2 * (3 - r) * x), k1 * r**3 / 6 * (1 - x))
        dyc = np.where(x < r, k1 / 6 * (3 * x**2 - 6 * r * x + r**2 * (3 - r)), -k1 * r**3 / 6)
    elif m > 0 and 0 < p < 1:
        yc = np.where(x < p, m / p**2 * (2 * p * x - x**2), m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x - x**2))
        dyc = np.where(x < p, 2 * m / p**2 * (p - x), 2 * m / (1 - p) ** 2 * (p - x))
    else:
        yc, dyc = np.zeros_like(x), np.zeros_like(x)
    th = np.arctan(dyc)
    return x - yt * np.sin(th), yc + yt * np.cos(th), x + yt * np.sin(th), yc - yt * np.cos(th)


@dataclass
class Contour:
    """Box-depth contour z_upper(x), z_lower(x) per unit chord, thickness scaled by k_h about the camber line."""
    m: float = 0.0
    p: float = 0.4
    tc: float = 0.12
    k_h: float = 0.95
    five: tuple | None = None        # (r, k1) of a NACA 5-digit mean line (overrides m, p)

    @classmethod
    def from_airfoil(cls, airfoil: str, tc: float, k_h: float = 0.95) -> "Contour":
        kind, a, b = camber_from_name(airfoil)
        return cls(a, b, tc, k_h) if kind == "4" else cls(0.0, 0.4, tc, k_h, (a, b))

    def __post_init__(self):
        xu, zu, xl, zl = naca4(self.m, self.p, self.tc, five=self.five)
        self._u, self._l = (xu, zu), (xl, zl)

    def z(self, x):
        zu = np.interp(x, *self._u)
        zl = np.interp(x, *self._l)
        mid = 0.5 * (zu + zl)
        return mid + self.k_h * (zu - mid), mid - self.k_h * (zu - mid)

    def depth(self, x):
        zu, zl = self.z(x)
        return zu - zl


def wing_section(chord: float, contour: Contour, xf: float, xr: float, *, t_up: float, t_lo: float,
                 t_wf: float, t_wr: float, tbar_up: float | None = None, tbar_lo: float | None = None,
                 cap_area=0.0, cap_E_ratio: float = 1.0, stringers_up=(), stringers_lo=(), A_str: float = 0.0,
                 t_le: float | None = None, E: float = 70e9, G: float = 27e9, n_cover: int = 14, n_web: int = 6,
                 n_le: int = 18) -> ThinWalledSection:
    """Build the idealised section of the two-spar box at a station (all lengths in m).

    cap_area: one value or 4 (front-up, rear-up, rear-lo, front-lo) — concentrated cap areas (E ratio cap_E_ratio,
    e.g. UD CFRP caps on a fabric box); stringers_up/lo: x/c positions of discrete stringers of area A_str (snapped
    to the nearest cover node). Returns a solved :class:`ThinWalledSection` (x from the LE, z from the chord line)."""
    tbar_up = t_up if tbar_up is None else tbar_up
    tbar_lo = t_lo if tbar_lo is None else tbar_lo
    xs = np.linspace(xf, xr, n_cover + 1)
    zu, zl = contour.z(xs)
    pts, area = [], []
    up = list(range(n_cover + 1))
    pts += [(x * chord, z * chord) for x, z in zip(xs, zu)]
    zr = np.linspace(zu[-1], zl[-1], n_web + 1)[1:-1]
    rw = [len(pts) + k for k in range(len(zr))]
    pts += [(xr * chord, z * chord) for z in zr]
    lo0 = len(pts)
    pts += [(x * chord, z * chord) for x, z in zip(xs[::-1], zl[::-1])]
    lo = list(range(lo0, lo0 + n_cover + 1))           # rear → front
    zf = np.linspace(zl[0], zu[0], n_web + 1)[1:-1]
    fw = [len(pts) + k for k in range(len(zf))]
    pts += [(xf * chord, z * chord) for z in zf]
    area = np.zeros(len(pts))
    walls = []

    def chain(ids, t, er):
        for a, b in zip(ids[:-1], ids[1:]):
            walls.append((a, b, t, 1.0, er, True))

    chain(up, t_up, tbar_up / t_up)
    chain([up[-1]] + rw + [lo[0]], t_wr, 1.0)
    chain(lo, t_lo, tbar_lo / t_lo)
    chain([lo[-1]] + fw + [up[0]], t_wf, 1.0)
    box_cell = [k + 1 for k in range(len(walls))]
    caps = np.broadcast_to(np.asarray(cap_area, float), (4,))
    for node, a in zip((up[0], up[-1], lo[0], lo[-1]), caps):
        area[node] += cap_E_ratio * a
    for xs_s, ids, xs_c in ((stringers_up, up, xs), (stringers_lo, lo, xs[::-1])):
        for xc in xs_s:
            area[ids[int(np.argmin(np.abs(xs_c - xc)))]] += A_str
    cells = [box_cell]
    if t_le:
        # LE skin: from the front-spar top along the upper surface to the nose and back along the lower surface
        xu_, zu_ = contour._u
        xl_, zl_ = contour._l
        bu = np.linspace(xf, 0.0, n_le // 2 + 1) ** 1.0
        su = np.interp(bu, xu_, zu_)
        sl = np.interp(bu[::-1], xl_, zl_)
        mid_u = 0.5 * (np.interp(bu, xu_, zu_) + np.interp(bu, xl_, zl_))
        zu_s = mid_u + contour.k_h * (su - mid_u)
        mid_l = mid_u[::-1]
        zl_s = mid_l + contour.k_h * (sl - mid_l)
        ids = [up[0]]
        for x, z in list(zip(bu[1:], zu_s[1:])) + list(zip(bu[::-1][1:-1], zl_s[1:-1])):
            ids.append(len(pts))
            pts.append((x * chord, z * chord))
            area = np.append(area, 0.0)
        ids.append(lo[-1])
        k0 = len(walls)
        chain(ids, t_le, 1.0)
        nle = len(walls) - k0
        # D-nose cell: LE skin (up→nose→lo) then front web lo→up (front web walls are traversed + in the box loop)
        fweb = [k + 1 for k in range(len(walls)) if walls[k][0] in [lo[-1]] + fw and walls[k][1] in fw + [up[0]]]
        cells.append([k0 + 1 + k for k in range(nle)] + fweb)
    return ThinWalledSection(np.array(pts, float), area, walls, cells, E, G).solve()
