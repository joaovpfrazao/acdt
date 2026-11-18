"""Mass and centre-of-gravity bookkeeping.

Raymer, *Aircraft Design: A Conceptual Approach*, 6th ed., 2018, Sec. 15.1, and Roskam,
*Airplane Design* Part II, 1985, Ch. 10: x_cg = Σ m_i x_i / Σ m_i, reported in % MAC.

Operational loading (the same references): each item sits at a fixed station and its mass lies
between a minimum and a maximum. The centre-of-gravity extremes of that box, including the face
where the total mass equals a maximum take-off mass, are vertices. Fuel is burned tank by tank
in ``fuel_order``; because one tank at a time changes mass, the path kinks only when a tank
empties, and those points are vertices too.

This module does not choose stations. The caller passes each ``x``. Aircraft defaults live in
``stability.DEFAULT_STATIONS``: structure follows Roskam Part V Table 8.1; crew, payload and the
battery, until the mission sets them, sit on the fixed-mass CG (reference ``balance``, Raymer
2018 Sec. 15.1). Wing fuel stays at 30 % MAC. They are not put on the wing as a lump.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field


@dataclass
class MassItem:
    name: str
    mass: float
    x: float | None = None  # [m] from fuselage nose


def cg(items: list[MassItem]) -> float | None:
    pos = [i for i in items if i.x is not None]
    if not pos:
        return None
    m = sum(i.mass for i in pos)
    return sum(i.mass * i.x for i in pos) / m


def percent_mac(x_cg: float, x_le_mac: float, mac: float) -> float:
    return 100 * (x_cg - x_le_mac) / mac


@dataclass
class LoadItem:
    """One station. ``kind`` is ``fixed`` (mass_min == mass_max), ``variable`` (payload, crew) or
    ``fuel`` (burned in ascending ``fuel_order``). ``x`` is metres from the same datum for every item."""

    name: str
    x: float
    mass_min: float
    mass_max: float
    kind: str = "fixed"
    fuel_order: int = 0

    def __post_init__(self) -> None:
        if self.mass_min < -1e-9 or self.mass_max < self.mass_min - 1e-9:
            raise ValueError(f"{self.name}: mass must satisfy 0 ≤ mass_min ≤ mass_max")
        if self.kind not in ("fixed", "variable", "fuel"):
            raise ValueError(f"{self.name}: kind must be fixed, variable or fuel")
        if self.kind == "fixed" and abs(self.mass_max - self.mass_min) > 1e-9:
            raise ValueError(f"{self.name}: a fixed item has one mass")


@dataclass
class LoadingPoint:
    name: str
    mass: float
    x: float
    kind: str  # vertex | fuel


@dataclass
class OperationalEnvelope:
    points: list[LoadingPoint] = field(default_factory=list)
    paths: list[list[LoadingPoint]] = field(default_factory=list)

    @property
    def most_forward(self) -> LoadingPoint | None:
        return min(self.points, key=lambda p: p.x) if self.points else None

    @property
    def most_aft(self) -> LoadingPoint | None:
        return max(self.points, key=lambda p: p.x) if self.points else None


def cg_limit_at(limit: list[tuple[float, float]] | None, mass: float) -> float | None:
    """Piecewise-linear CG limit. One point is a limit that does not change with mass.
    Outside the tabulated masses the end value is held (the table did not say otherwise)."""
    if not limit:
        return None
    pts = sorted((float(m), float(x)) for m, x in limit)
    if len(pts) == 1 or mass <= pts[0][0]:
        return pts[0][1]
    if mass >= pts[-1][0]:
        return pts[-1][1]
    for (m0, x0), (m1, x1) in zip(pts, pts[1:]):
        if m0 <= mass <= m1:
            if m1 == m0:
                return x0
            return x0 + (mass - m0) / (m1 - m0) * (x1 - x0)
    return pts[-1][1]


def outside_limits(points: list[LoadingPoint], forward: list[tuple[float, float]] | None,
                   aft: list[tuple[float, float]] | None, tol: float = 1e-6) -> list[LoadingPoint]:
    """Points with x outside the forward/aft limits at their mass. x increases aft, so the
    forward limit is the smallest allowed x."""
    bad = []
    for p in points:
        lo = cg_limit_at(forward, p.mass)
        hi = cg_limit_at(aft, p.mass)
        if (lo is not None and p.x < lo - tol) or (hi is not None and p.x > hi + tol):
            bad.append(p)
    return bad


def _label(varying: list[LoadItem], masses: list[float]) -> str:
    parts = []
    for it, m in zip(varying, masses):
        span = it.mass_max - it.mass_min
        if span <= 1e-12 or m <= it.mass_min + 1e-6:
            continue
        frac = (m - it.mass_min) / span
        parts.append(it.name if frac > 0.999 else f"{it.name} {100 * frac:.0f}%")
    return " + ".join(parts) if parts else "vazio"


def _moment(fixed: list[LoadItem], varying: list[LoadItem], masses: list[float]) -> tuple[float, float]:
    m = sum(i.mass_min for i in fixed) + sum(masses)
    mx = sum(i.mass_min * i.x for i in fixed) + sum(mi * it.x for mi, it in zip(masses, varying))
    return m, mx


# PRESSUPOSTO: Roskam Part II Ch. 10 draws the MTOW face and does not give a gram tolerance.
# A component build-up that overshoots m_max by less than this is kept.
MTOW_CLOSURE_TOL_KG = 0.05


def operational_loadings(items: list[LoadItem], m_max: float | None = None) -> OperationalEnvelope:
    """Vertices of the loading box, and fuel-burn paths from each non-fuel corner.

    ``m_max`` drops corners above the maximum take-off mass and adds the points where one
    variable item is only partly loaded so that the total equals ``m_max`` (Roskam Part II Ch. 10,
    the loading diagram). A corner up to ``MTOW_CLOSURE_TOL_KG`` (0.05 kg, PRESSUPOSTO) over
    ``m_max`` is kept: component build-ups do not close to the gram. Roskam does not state this band.
    """
    if any(i.mass_max < i.mass_min for i in items):
        raise ValueError("mass_max < mass_min")
    fixed = [i for i in items if i.mass_max <= i.mass_min + 1e-12]
    varying = [i for i in items if i not in fixed]
    n = len(varying)
    if n > 12:
        raise ValueError(f"{n} variable load items: the vertex list is 2^n and stops at 12")
    cap = None if m_max is None else float(m_max)
    found: dict[tuple, LoadingPoint] = {}

    def add(masses: list[float], kind: str) -> LoadingPoint | None:
        m, mx = _moment(fixed, varying, masses)
        if m <= 1e-9:
            return None
        if cap is not None and m > cap + MTOW_CLOSURE_TOL_KG:
            return None
        key = tuple(round(v, 6) for v in masses)
        pt = LoadingPoint(_label(varying, masses), m, mx / m, kind)
        found[key] = pt
        return pt

    masks = list(itertools.product((0, 1), repeat=n)) if n else [()]
    for mask in masks:
        add([varying[j].mass_max if bit else varying[j].mass_min for j, bit in enumerate(mask)], "vertex")
    if cap is not None:
        for free in range(n):
            others = [j for j in range(n) if j != free]
            for mask in itertools.product((0, 1), repeat=len(others)):
                masses = [0.0] * n
                for bit, j in zip(mask, others):
                    masses[j] = varying[j].mass_max if bit else varying[j].mass_min
                m_rest, _ = _moment(fixed, varying, masses)
                need = cap - m_rest
                lo, hi = varying[free].mass_min, varying[free].mass_max
                if lo - 1e-9 <= need <= hi + 1e-9:
                    masses[free] = min(max(need, lo), hi)
                    add(masses, "vertex")

    fuels = sorted([i for i in items if i.kind == "fuel" and i.mass_max > i.mass_min + 1e-12],
                   key=lambda i: i.fuel_order)
    paths: list[list[LoadingPoint]] = []
    if fuels:
        fuel_index = {id(it): k for k, it in enumerate(varying)}
        non_fuel = [i for i in varying if i.kind != "fuel"]
        nf_index = [fuel_index[id(i)] for i in non_fuel]
        for mask in itertools.product((0, 1), repeat=len(non_fuel)):
            masses = [it.mass_min for it in varying]
            for bit, it, idx in zip(mask, non_fuel, nf_index):
                masses[idx] = it.mass_max if bit else it.mass_min
            for it in fuels:
                masses[fuel_index[id(it)]] = it.mass_max
            m_now, _ = _moment(fixed, varying, masses)
            if cap is not None and m_now > cap + 1e-6:
                excess = m_now - cap
                for it in reversed(fuels):
                    idx = fuel_index[id(it)]
                    room = masses[idx] - it.mass_min
                    take = min(room, excess)
                    masses[idx] -= take
                    excess -= take
                    if excess <= 1e-9:
                        break
                if excess > 1e-6:
                    continue
            start = add(masses, "fuel")
            pts = [] if start is None else [start]
            for it in fuels:
                idx = fuel_index[id(it)]
                if masses[idx] > it.mass_min + 1e-9:
                    masses[idx] = it.mass_min
                    nxt = add(masses, "fuel")
                    if nxt is not None:
                        pts.append(LoadingPoint(f"após {it.name}", nxt.mass, nxt.x, "fuel"))
            if len(pts) >= 2:
                paths.append(pts)
    return OperationalEnvelope(list(found.values()), paths)
