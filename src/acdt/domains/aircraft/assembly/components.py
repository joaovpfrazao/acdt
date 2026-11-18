"""Generic, composable geometry components placed in one aircraft frame (P1 of docs/DESIGN_WORKFLOW.md).

Any configuration (conventional, twin boom, canard, tailless, flying wing, box / joined wing, V / inverted-V /
H tails, pusher / tractor, podded sensors...) is assembled from three primitives — there is **no fixed
configuration enum**; the optional ``role`` is a free-text label only:

* :class:`Body` — fuselage, pod, boom, nacelle, radome, fairing, gear leg: super-elliptic cross-sections
  (Lamé curve |y/a|^n + |z/b|^n = 1; n = 2 ellipse, n → ∞ rectangle, n < 2 diamond-like) given at stations
  along the local x axis, linearly interpolated. Opt-in ``chine: {angle_deg, crown_frac?}`` replaces the
  Lamé ring with a hexagonal section that has sharp longitudinal chines (same construction as
  :mod:`acdt.domains.aircraft.rcs.geometry`) so the PO RCS mesh sees the edge.
* :class:`Surface` — wing, tail, canard, fin, winglet, box-wing tip fin, joined-wing panel: chord sections
  with leading-edge point, chord, twist and t/c, any dihedral / cant (V, inverted V, vertical, ring segments),
  NACA 4-digit symmetric thickness (Abbott & von Doenhoff 1959, Eq. 6.2, closed-TE coefficient −0.1036).
  The 4-digit mean line (Eq. 6.4–6.6) is off unless the surface calls :meth:`Surface.with_naca4_mean_line`.
* :class:`Disc` — propeller / rotor disc (obstruction and keep-out), thin cylinder.

Frame (same as :mod:`acdt.domains.aircraft.rcs.geometry` and AVL): x aft, y starboard, z up. Each component has
an ``origin`` and an ``orientation`` {yaw, pitch, roll} [deg] (rotation local → aircraft R = Rz·Ry·Rx), and
``mirror: true`` adds its image in the y = 0 plane (twin booms, wing halves). Every component triangulates to a
closed mesh with outward normals (:meth:`mesh`), which feeds the FOV ray caster, the RCS (PO) mesh, STL/AVL
export and wetted areas. ``contains`` returns a signed clearance [m] (positive inside) used by packaging.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

ASSUMPTIONS = [
    "PRESSUPOSTO: folga dentro de um corpo aproximada por (1 − s)·min(w, h)/2, s = nível da super-elipse "
    "(exata para secção circular; aproximada para secções alongadas ou n ≠ 2).",
    "PRESSUPOSTO: superfícies com espessura NACA 4 dígitos simétrica (t/c por secção); folga = meia espessura "
    "local − |distância ao plano médio| (painéis lineares entre secções).",
    "PRESSUPOSTO: a linha média NACA de 4 dígitos (Abbott & von Doenhoff 1959, Eq. 6.4–6.6) só entra "
    "quando a superfície pede with_naca4_mean_line. Por omissão a curvatura não é zero: fica por construir.",
    "PRESSUPOSTO: disco da hélice como cilindro fino (espessura por omissão 0,05 m), opacidade 1 (conservador; "
    "pode-se dar a solidez das pás).",
]


def rotation(yaw=0.0, pitch=0.0, roll=0.0) -> np.ndarray:
    """Local → aircraft rotation R = Rz(yaw)·Ry(pitch)·Rx(roll) [deg], right-handed about the aircraft axes."""
    y, p, r = (math.radians(v) for v in (yaw, pitch, roll))
    Rz = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]])
    Ry = np.array([[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
    return Rz @ Ry @ Rx


def naca_yt(xc, tc):
    """NACA 4-digit half-thickness / chord (Abbott & von Doenhoff 1959, Eq. 6.2; closed TE, a4 = −0.1036)."""
    x = np.clip(np.asarray(xc, float), 0.0, 1.0)
    return 5 * tc * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4)


def naca4_designation(airfoil: str | None) -> dict | None:
    """Read a NACA 4-digit name. Does not build the mean line.

    The digits are the same reading as :func:`acdt.domains.aircraft.wingbox.section.camber_from_name`:
    the first is the maximum camber in percent of chord, the second its location in tenths of chord,
    and the last two the thickness in percent of chord (Abbott & von Doenhoff 1959, the 4-digit family
    whose thickness is Eq. 6.2). Five-digit names, ``naca4``, and any other text return None.
    Unknown is not stored as zero camber.
    """
    if airfoil is None:
        return None
    digits = "".join(ch for ch in str(airfoil).upper() if ch.isdigit())
    if len(digits) != 4:
        return None
    return {
        "designation": f"NACA {digits}",
        "camber_percent_chord": int(digits[0]),
        "camber_position_tenths": int(digits[1]),
        "thickness_percent_chord": int(digits[2:]),
    }


def symmetric_naca_code(tc: float) -> str:
    """AVL ``NACA`` card for a symmetric section of thickness ``tc`` (chord fraction)."""
    tc = float(tc)
    if not math.isfinite(tc) or tc <= 0.0:
        raise ValueError("t/c declarado tem de ser positivo e finito; não se substitui por zero")
    return f"00{max(1, min(99, round(100.0 * tc))):02d}"


def naca4_mean_line(xc, m: float, p: float):
    """Mean-line ordinate and slope, yc/c and d(yc)/dx (Abbott & von Doenhoff 1959, Eq. 6.4 and 6.5).

    ``m`` and ``p`` are fractions of chord. ``m = 0`` returns a flat line and does not divide by
    ``p²``, so a symmetric section stays the current loft, including a second digit of 0.
    ``m > 0`` with ``p`` outside (0, 1) is refused. That case is not a 4-digit mean line: it is
    not stored as a flat line and it is not stored as zero camber.
    """
    x_in = np.asarray(xc, float)
    scalar = x_in.ndim == 0
    x = np.atleast_1d(x_in)
    m = float(m)
    p = float(p)
    yc = np.zeros(x.shape, dtype=float)
    dy = np.zeros(x.shape, dtype=float)
    if m == 0.0:
        if scalar:
            return yc[0], dy[0]
        return yc, dy
    if not math.isfinite(m) or m < 0.0 or not (0.0 < p < 1.0):
        raise ValueError(
            "p = 0 com curvatura não é uma linha média de 4 dígitos; "
            "não se trata como plana nem como zero"
        )
    fwd = x < p
    yc[fwd] = (m / p**2) * (2.0 * p * x[fwd] - x[fwd] ** 2)
    dy[fwd] = (2.0 * m / p**2) * (p - x[fwd])
    aft = ~fwd
    yc[aft] = (m / (1.0 - p) ** 2) * (1.0 - 2.0 * p + 2.0 * p * x[aft] - x[aft] ** 2)
    dy[aft] = (2.0 * m / (1.0 - p) ** 2) * (p - x[aft])
    if scalar:
        return yc[0], dy[0]
    return yc, dy


def naca4_surface(xc, tc: float, m: float, p: float):
    """Upper and lower coordinates as fractions of chord (Abbott & von Doenhoff 1959, Eq. 6.6).

    Returns ``xu, zu, xl, zl``. ``m = 0`` is ``xu = x``, ``zu = naca_yt``, ``xl = x``, ``zl = -naca_yt``,
    the same numbers as the symmetric loft. Thickness stays :func:`naca_yt` of the declared ``tc``.
    """
    x = np.asarray(xc, float)
    yt = np.asarray(naca_yt(x, tc), float)
    if float(m) == 0.0:
        return x, yt, x, -yt
    yc, dy = naca4_mean_line(x, m, p)
    th = np.arctan(dy)
    st, ct = np.sin(th), np.cos(th)
    return x - yt * st, yc + yt * ct, x + yt * st, yc - yt * ct


def naca4_section_code(camber_percent: int, position_tenths: int, tc: float) -> str:
    """AVL ``NACA`` card: camber digits from the designation, thickness from the declared t/c.

    The last two digits use the same rounding as :func:`symmetric_naca_code`. A position digit
    of 0 is refused.
    """
    camber_percent = int(camber_percent)
    position_tenths = int(position_tenths)
    if not 1 <= camber_percent <= 9:
        raise ValueError("a curvatura da designação tem de ser 1–9 % da corda; zero não é opt-in")
    if not 1 <= position_tenths <= 9:
        raise ValueError(
            "p = 0 com curvatura não é uma linha média de 4 dígitos; "
            "não se trata como plana nem como zero"
        )
    return f"{camber_percent}{position_tenths}{symmetric_naca_code(tc)[2:]}"


def naca4_mean_line_record(airfoil: str | None, tc_root: float, tc_tip: float) -> dict:
    """Record for a surface that has opted in to the 4-digit mean line.

    Raises when the name is not a cambered 4-digit designation. Unknown camber is not filled in.
    The loft thickness remains the declared t/c, not the thickness digits, when the two differ.
    """
    parsed = naca4_designation(airfoil)
    if parsed is None or parsed["camber_percent_chord"] == 0:
        raise ValueError(
            "a linha média pede uma designação NACA de 4 dígitos com curvatura; "
            "não se inventa nem se trata como zero"
        )
    if parsed["camber_position_tenths"] == 0:
        raise ValueError(
            "p = 0 com curvatura não é uma linha média de 4 dígitos; "
            "não se trata como plana nem como zero"
        )
    camber = parsed["camber_percent_chord"]
    pos = parsed["camber_position_tenths"]
    name = str(airfoil).strip()
    return {
        "airfoil": name,
        "designation": parsed["designation"],
        "parsed": parsed,
        "tc_root": float(tc_root),
        "tc_tip": float(tc_tip),
        "naca_root": naca4_section_code(camber, pos, tc_root),
        "naca_tip": naca4_section_code(camber, pos, tc_tip),
        "camber": "construida",
        "m": camber / 100.0,
        "p": pos / 10.0,
        "motivo": (
            f"{parsed['designation']}: linha média construída "
            "(Abbott & von Doenhoff 1959, Eq. 6.4–6.6). "
            f"Curvatura máxima {camber} % da corda a {pos / 10:.1f} c. "
            "A espessura do loft continua a ser naca_yt do t/c declarado, "
            "não o dígito de espessura da designação quando os dois diferem."
        ),
        "pressupostos": [
            "PRESSUPOSTO: a mesma linha média (m, p) em todas as secções da superfície.",
            "PRESSUPOSTO: a espessura é naca_yt do t/c declarado, perpendicular à linha média (Eq. 6.6).",
            "PRESSUPOSTO: o cartão AVL usa os dígitos de curvatura da designação e a espessura "
            "arredondada do t/c da secção. CLAF não é escrito.",
        ],
    }


def camber_clearance(xi, ze, tc: float, ch: float, m: float, p: float, n_iter: int = 20):
    """Signed clearance [m] to one cambered section. Positive is inside.

    The station on the mean line is the one whose normal passes through the point
    (Eq. 6.6). Outside the chord interval the overrun is the symmetric one: past the
    leading or trailing edge is outside. PRESSUPOSTO: a 4-digit mean line meets the
    chord at both ends, so that interval is the section. ``m = 0`` matches the
    symmetric clearance.
    """
    xi_b, ze_b, tc_b, ch_b = np.broadcast_arrays(
        np.asarray(xi, float), np.asarray(ze, float),
        np.asarray(tc, float), np.asarray(ch, float))
    flat_xi = np.array(xi_b, dtype=float, copy=True).ravel()
    flat_ze = np.array(ze_b, dtype=float, copy=True).ravel()
    flat_tc = np.array(tc_b, dtype=float, copy=True).ravel()
    flat_ch = np.array(ch_b, dtype=float, copy=True).ravel()
    x = np.clip(flat_xi, 0.0, 1.0)
    zeta = flat_ze / flat_ch

    def residual(xx):
        yc, dy = naca4_mean_line(xx, m, p)
        th = np.arctan(dy)
        return (flat_xi - xx) * np.cos(th) + (zeta - yc) * np.sin(th), th, yc

    for _ in range(int(n_iter)):
        r, _th, _yc = residual(x)
        eps = 1e-6
        xp = np.minimum(x + eps, 1.0)
        xm = np.maximum(x - eps, 0.0)
        rp, _, _ = residual(xp)
        rm, _, _ = residual(xm)
        dr = (rp - rm) / np.maximum(xp - xm, 1e-15)
        step = np.divide(r, dr, out=np.zeros_like(r), where=np.abs(dr) > 1e-14)
        x = np.clip(x - step, 0.0, 1.0)
    r, th, yc = residual(x)
    bad = np.abs(r) > 1e-8
    if np.any(bad):
        grid = np.linspace(0.0, 1.0, 81)
        yc_g, dy_g = naca4_mean_line(grid, m, p)
        th_g = np.arctan(dy_g)
        for i in np.flatnonzero(bad):
            rr = (flat_xi[i] - grid) * np.cos(th_g) + (zeta[i] - yc_g) * np.sin(th_g)
            x[i] = grid[int(np.argmin(np.abs(rr)))]
        r, th, yc = residual(x)
    s = -(flat_xi - x) * np.sin(th) + (zeta - yc) * np.cos(th)
    yt = np.asarray(naca_yt(x, flat_tc), float)
    margin = (yt - np.abs(s)) * flat_ch
    overrun = -np.maximum(-flat_xi, flat_xi - 1.0) * flat_ch - np.abs(flat_ze)
    inside = (flat_xi >= 0.0) & (flat_xi <= 1.0)
    return np.where(inside, margin, overrun).reshape(xi_b.shape)


def section_thickness_record(airfoil: str | None, tc_root: float, tc_tip: float) -> dict:
    """Declared symmetric thickness, and the camber that the loft and the AVL file do not build.

    Drela & Youngren, AVL 3.40 user guide (``avl_doc.txt``): the ``NACA`` keyword sets the camber
    line, and the default camber line is a flat plate. A 00xx card is that flat line. ``CLAF`` is
    not written, so the guide's estimate ``CLaf = 1 + 0.77 t/c`` stays out (the same page says
    viscosity reduces the 0.77, and this record does not invent that factor).
    """
    name = None if airfoil is None else str(airfoil).strip()
    parsed = None if not name or name.lower() == "naca4" else naca4_designation(name)
    if not name or name.lower() == "naca4":
        camber = "desconhecida"
        designation = None
        motivo = "sem designação NACA de 4 dígitos; a curvatura não é tratada como zero"
    elif parsed is None:
        camber = "desconhecida"
        designation = name
        motivo = (f"a designação {name!r} não é NACA de 4 dígitos; "
                  "a curvatura não foi inventada nem tratada como zero")
    elif parsed["camber_percent_chord"] == 0:
        camber = "ausente_na_designacao"
        designation = parsed["designation"]
        motivo = "a designação NACA é simétrica; a linha média da designação é plana"
    else:
        camber = "lacuna"
        designation = parsed["designation"]
        pos = parsed["camber_position_tenths"] / 10.0
        motivo = (
            f"{designation}: a designação traz {parsed['camber_percent_chord']} % da corda de curvatura "
            f"máxima a {pos:.1f} c. A linha média não é construída. "
            "PRESSUPOSTO: o loft e o AVL ficam com a espessura NACA simétrica do t/c declarado."
        )
    return {
        "airfoil": name,
        "designation": designation,
        "parsed": parsed,
        "tc_root": float(tc_root),
        "tc_tip": float(tc_tip),
        "naca_root": symmetric_naca_code(tc_root),
        "naca_tip": symmetric_naca_code(tc_tip),
        "camber": camber,
        "motivo": motivo,
        "pressupostos": [
            "PRESSUPOSTO: a espessura do loft é naca_yt do t/c declarado, não o dígito de espessura da designação quando os dois diferem.",
            "PRESSUPOSTO: entre a raiz e a ponta o t/c varia linearmente na fracção do comprimento do bordo de ataque.",
            "PRESSUPOSTO: o AVL recebe NACA 00xx dessa espessura. A palavra NACA define a linha média (Drela & Youngren, avl_doc.txt); 00xx é plana. CLAF não é escrito.",
        ],
    }


def _signed_volume(V, F) -> float:
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def _outward(V, F):
    """Closed mesh: flip all faces if the divergence-theorem volume is negative (consistent winding assumed)."""
    return F[:, ::-1].copy() if _signed_volume(V, F) < 0 else F


@dataclass
class Component:
    name: str
    role: str = ""                       # free-text label (fuselage, boom, radome, wing, tail, ...) — no enum
    origin: tuple = (0.0, 0.0, 0.0)
    orientation: dict = field(default_factory=dict)   # {yaw, pitch, roll} [deg]
    mirror: bool = False
    mass_kg: float | None = None
    cg: tuple | None = None              # aircraft frame; default = geometric centroid (PRESSUPOSTO)
    transparent_to: tuple = ()           # bands this part does not block, e.g. ("rf",) for a radome
    opacity: float = 1.0                 # fraction of a ray blocked when hit (1 = opaque)
    mirrored_image: bool = False         # set on the generated y-mirror instance

    @property
    def R(self) -> np.ndarray:
        o = self.orientation or {}
        return rotation(o.get("yaw", 0.0), o.get("pitch", 0.0), o.get("roll", 0.0))

    def _sign(self):
        return np.array([1.0, -1.0, 1.0]) if self.mirrored_image else np.ones(3)

    def to_global(self, P):
        P = np.atleast_2d(np.asarray(P, float))
        return (P @ self.R.T + np.asarray(self.origin, float)) * self._sign()

    def to_local(self, P):
        P = np.atleast_2d(np.asarray(P, float)) * self._sign()
        return (P - np.asarray(self.origin, float)) @ self.R

    def _finish(self, Vl, F):
        V = self.to_global(Vl)
        if self.mirrored_image:
            F = F[:, ::-1]
        F = _outward(V, np.asarray(F, int))
        return V, F

    def mirrored(self):
        import copy
        m = copy.deepcopy(self)
        m.name, m.mirror, m.mirrored_image = self.name + "~m", False, True
        if m.cg is not None:
            m.cg = (m.cg[0], -m.cg[1], m.cg[2])
        return m

    # interface
    def mesh(self, fine: int = 1):
        raise NotImplementedError

    def contains(self, P):
        raise NotImplementedError

    def volume(self) -> float:
        V, F = self.mesh(fine=2)
        return _signed_volume(V, F)

    def wetted_area(self) -> float:
        V, F = self.mesh(fine=2)
        a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
        return float(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum())

    def centroid(self) -> np.ndarray:
        V, F = self.mesh(fine=2)
        a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
        w = np.einsum("ij,ij->i", a, np.cross(b, c))                # 6 × tetra volume (origin apex)
        if abs(w.sum()) < 1e-15:
            return V.mean(axis=0)
        return ((a + b + c) / 4.0 * w[:, None]).sum(axis=0) / w.sum()

    def bbox(self):
        V, _ = self.mesh()
        return V.min(axis=0), V.max(axis=0)


# --------------------------------------------------------------------------------------------- Body
@dataclass
class Body(Component):
    """Stations ``[{x, w, h, zc=0, yc=0, n=2}]`` (local x from origin, full width w and height h [m]).

    Optional ``chine={{angle_deg, crown_frac?}}``: hexagonal cross-section with sharp longitudinal chines
    at z = 0 (same construction as :func:`acdt.domains.aircraft.rcs.geometry.hexagon_section` /
    ``_section_pts``). Open geometric primitive for PO RCS — not a closed airframe catalog. Default
    (no chine) keeps the smooth Lamé section.
    """
    stations: list = field(default_factory=list)
    chine: dict | None = None   # {angle_deg: float, crown_frac?: float}

    def __post_init__(self):
        st = sorted(({"zc": 0.0, "yc": 0.0, "n": 2.0, **s} for s in self.stations), key=lambda s: s["x"])
        if len(st) < 2:
            raise ValueError(f"body {self.name!r}: needs ≥ 2 stations")
        self.stations = st
        if self.chine is not None:
            if not isinstance(self.chine, dict) or self.chine.get("angle_deg") is None:
                raise ValueError(f"body {self.name!r}: chine needs {{angle_deg, crown_frac?}}")
            self.chine = {
                "angle_deg": float(self.chine["angle_deg"]),
                "crown_frac": float(self.chine.get("crown_frac", 0.35)),  # PRESSUPOSTO = RCS DEFAULTS
            }

    @classmethod
    def pod(cls, name, length, width, height=None, nose_frac=0.2, tail_frac=0.3, tail_scale=0.15, n=2.0,
            nose_scale=0.0, upsweep_deg=0.0, chine=None, chine_deg=None, crown_frac=None, **kw):
        """Shorthand pod/boom/nacelle: nose taper over nose_frac·L, constant section, tail taper over
        tail_frac·L to tail_scale (all are design variables, PRESSUPOSTO when not set by the study).
        ``upsweep_deg`` raises the tail-cone centreline linearly (aft-fuselage upsweep u of Raymer Eq. 12.36).
        ``chine`` / ``chine_deg`` opts into a hexagonal chined section for the PO RCS mesh."""
        h = height or width
        x = [0.0, nose_frac * length, (1 - tail_frac) * length, length]
        sc = [nose_scale, 1.0, 1.0, tail_scale]
        zc = [0.0, 0.0, 0.0, math.tan(math.radians(upsweep_deg)) * tail_frac * length]
        if chine is None and chine_deg is not None:
            chine = {"angle_deg": float(chine_deg),
                     "crown_frac": float(crown_frac) if crown_frac is not None else 0.35}
        return cls(name=name, stations=[{"x": xi, "w": width * s, "h": h * s, "n": n, "zc": z}
                                        for xi, s, z in zip(x, sc, zc)], chine=chine, **kw)

    def chine_ring(self, w: float, h: float, yc: float = 0.0, zc: float = 0.0):
        """Six (y, z) vertices of the hexagonal section (chines at z=0).

        Station ``w,h`` set the equivalent diameter D = √(w·h) so the section area matches the
        ellipse π·w·h/4; ``chine.angle_deg`` and ``crown_frac`` then fix W, H, w_t via the same
        :func:`acdt.domains.aircraft.rcs.geometry.hexagon_section` used by the parametric PO mesh
        (area-preserving DOE on the facet angle).
        """
        if not self.chine:
            raise ValueError("no chine on this body")
        from acdt.domains.aircraft.rcs.geometry import hexagon_section
        D = math.sqrt(max(w * h, 1e-18))
        W, H, wt = hexagon_section(D, float(self.chine["angle_deg"]), float(self.chine["crown_frac"]))
        return np.array([
            (yc + W / 2, zc + 0.0), (yc + wt / 2, zc + H / 2), (yc - wt / 2, zc + H / 2),
            (yc - W / 2, zc + 0.0), (yc - wt / 2, zc - H / 2), (yc + wt / 2, zc - H / 2),
        ], float)

    def _section(self, x):
        xs = np.array([s["x"] for s in self.stations])
        out = {}
        for k in ("w", "h", "zc", "yc", "n"):
            out[k] = np.interp(x, xs, [s[k] for s in self.stations])
        return out

    def contains(self, P):
        L = self.to_local(P)
        x0, x1 = self.stations[0]["x"], self.stations[-1]["x"]
        s = self._section(L[:, 0])
        mx = np.minimum(L[:, 0] - x0, x1 - L[:, 0])
        if self.chine is None:
            a, b = np.maximum(s["w"] / 2, 1e-9), np.maximum(s["h"] / 2, 1e-9)
            n = s["n"]
            lev = (np.abs((L[:, 1] - s["yc"]) / a) ** n + np.abs((L[:, 2] - s["zc"]) / b) ** n) ** (1.0 / n)
            m = (1.0 - lev) * np.minimum(a, b)
            return np.minimum(m, mx)
        # Hexagon: signed clearance ≈ min distance to edges (2-D), times scale (PRESSUPOSTO L0).
        out = np.empty(len(L))
        for i, (xi, yi, zi) in enumerate(L):
            w = float(np.interp(xi, [s["x"] for s in self.stations], [s["w"] for s in self.stations]))
            h = float(np.interp(xi, [s["x"] for s in self.stations], [s["h"] for s in self.stations]))
            yc = float(np.interp(xi, [s["x"] for s in self.stations], [s.get("yc", 0.0) for s in self.stations]))
            zc = float(np.interp(xi, [s["x"] for s in self.stations], [s.get("zc", 0.0) for s in self.stations]))
            if w * h < 1e-12:
                out[i] = min(mx[i], -1.0)
                continue
            ring = self.chine_ring(w, h, yc, zc)
            # winding / ray: inside if all cross products with edges have consistent sign
            yz = np.array([yi, zi])
            cross = []
            for a, b in zip(ring, np.roll(ring, -1, axis=0)):
                edge = b - a
                cross.append(edge[0] * (yz[1] - a[1]) - edge[1] * (yz[0] - a[0]))
            inside = all(c >= -1e-9 for c in cross) or all(c <= 1e-9 for c in cross)
            # distance to nearest edge
            dmin = math.inf
            for a, b in zip(ring, np.roll(ring, -1, axis=0)):
                ab = b - a
                t = np.clip(np.dot(yz - a, ab) / (np.dot(ab, ab) + 1e-16), 0.0, 1.0)
                dmin = min(dmin, float(np.linalg.norm(yz - (a + t * ab))))
            out[i] = min(mx[i], dmin if inside else -dmin)
        return out

    def section_area(self, x):
        """Lamé-curve area, or hexagonal area when ``chine`` is set: A = (2 w_t + W − w_t)·H/2."""
        s = self._section(x)
        if self.chine is None:
            g = np.vectorize(lambda n: math.gamma(1 + 1 / n) ** 2 / math.gamma(1 + 2 / n))
            return s["w"] * s["h"] * g(s["n"])
        # Area preserved vs ellipse of the station: A = π·w·h/4 = π·D²/4 with D=√(w·h)
        w, h = np.asarray(s["w"], float), np.asarray(s["h"], float)
        return 0.25 * math.pi * w * h

    def mesh(self, fine: int = 1):
        xs = []
        for a, b in zip(self.stations[:-1], self.stations[1:]):
            k = max(1, int(math.ceil((b["x"] - a["x"]) / max(self.length / (12 * fine), 1e-6))))
            xs += list(np.linspace(a["x"], b["x"], k, endpoint=False))
        xs.append(self.stations[-1]["x"])
        V, F, rings = [], [], []
        if self.chine is not None:
            nc = 6  # sharp chine edges — do not subdivide away the feature
            for x in xs:
                s = self._section(np.array([x]))
                w, h, zc, yc = (float(s[k][0]) for k in ("w", "h", "zc", "yc"))
                if w * h < 1e-12:
                    rings.append([len(V)])
                    V.append((x, yc, zc))
                    continue
                ring_yz = self.chine_ring(w, h, yc, zc)
                rings.append(list(range(len(V), len(V) + nc)))
                V += [(x, float(y), float(z)) for y, z in ring_yz]
        else:
            nc = 24 * fine
            t = np.linspace(0, 2 * np.pi, nc, endpoint=False)
            for x in xs:
                s = self._section(np.array([x]))
                w, h, zc, yc, n = (float(s[k][0]) for k in ("w", "h", "zc", "yc", "n"))
                if w * h < 1e-12:
                    rings.append([len(V)])
                    V.append((x, yc, zc))
                    continue
                e = 2.0 / n
                yy = yc + w / 2 * np.sign(np.cos(t)) * np.abs(np.cos(t)) ** e
                zz = zc + h / 2 * np.sign(np.sin(t)) * np.abs(np.sin(t)) ** e
                rings.append(list(range(len(V), len(V) + nc)))
                V += [(x, a, b) for a, b in zip(yy, zz)]
        for ra, rb in zip(rings[:-1], rings[1:]):
            if len(ra) == 1 and len(rb) == 1:
                continue
            if len(ra) == 1:
                F += [(ra[0], rb[(i + 1) % nc], rb[i]) for i in range(nc)]
            elif len(rb) == 1:
                F += [(ra[i], ra[(i + 1) % nc], rb[0]) for i in range(nc)]
            else:
                for i in range(nc):
                    j = (i + 1) % nc
                    F += [(ra[i], ra[j], rb[j]), (ra[i], rb[j], rb[i])]
        for r, end in ((rings[0], 0), (rings[-1], 1)):
            if len(r) > 1:
                c = len(V)
                V.append((xs[0] if end == 0 else xs[-1], float(np.mean([V[i][1] for i in r])),
                          float(np.mean([V[i][2] for i in r]))))
                F += [(c, r[(i + 1) % nc], r[i]) if end == 0 else (c, r[i], r[(i + 1) % nc]) for i in range(nc)]
        return self._finish(np.array(V, float), np.array(F, int))

    @property
    def length(self):
        return self.stations[-1]["x"] - self.stations[0]["x"]

    def volume(self) -> float:
        x = np.linspace(self.stations[0]["x"], self.stations[-1]["x"], 401)
        return float(np.trapezoid(self.section_area(x), x))


# --------------------------------------------------------------------------------------------- Surface
@dataclass
class Surface(Component):
    """Sections ``[{le: [x, y, z], chord, twist_deg=0, tc=0.12}]`` in local coordinates, root → tip; the chord
    lies along local +x rotated by twist (nose up +) about the local span direction.

    ``naca4_mean_line`` is off by default. The loft is then the symmetric thickness. Opt in with
    :meth:`with_naca4_mean_line`; that does not run unless the designation is a cambered 4-digit NACA.
    """
    sections: list = field(default_factory=list)
    airfoil: str = "naca4"
    naca4_mean_line: bool = False

    def __post_init__(self):
        self.sections = [{"twist_deg": 0.0, "tc": 0.12, **s} for s in self.sections]
        if len(self.sections) < 2:
            raise ValueError(f"surface {self.name!r}: needs ≥ 2 sections")
        if self.naca4_mean_line:
            naca4_mean_line_record(self.airfoil, self.sections[0]["tc"], self.sections[-1]["tc"])

    def _naca4_mp(self) -> tuple[float, float]:
        rec = naca4_mean_line_record(self.airfoil, self.sections[0]["tc"], self.sections[-1]["tc"])
        return float(rec["m"]), float(rec["p"])

    @classmethod
    def panel(cls, name, root_chord, tip_chord, span, sweep_le_deg=0.0, dihedral_deg=0.0, tc_root=0.12,
              tc_tip=None, twist_tip_deg=0.0, n_sections=2, **kw):
        """Straight-tapered panel shorthand: span measured along the panel (dihedral 90° = vertical fin,
        negative = anhedral; inverted V = negative dihedral or a roll on placement)."""
        G = math.radians(dihedral_deg)
        tl = math.tan(math.radians(sweep_le_deg))
        secs = []
        for e in np.linspace(0, 1, max(2, n_sections)):
            yb = e * span
            secs.append({"le": [yb * tl, yb * math.cos(G), yb * math.sin(G)],
                         "chord": root_chord + (tip_chord - root_chord) * e,
                         "twist_deg": twist_tip_deg * e,
                         "tc": tc_root + ((tc_tip if tc_tip is not None else tc_root) - tc_root) * e})
        return cls(name=name, sections=secs, **kw)

    def _frames(self):
        """Per section: LE point, chord unit vector, thickness unit vector (local frame)."""
        le = np.array([s["le"] for s in self.sections], float)
        span = np.zeros_like(le)
        d = np.diff(le, axis=0)
        span[:-1] += d
        span[1:] += d
        out = []
        for i, s in enumerate(self.sections):
            sp = span[i] - span[i][0] * np.array([1, 0, 0])             # spanwise ⟂ x
            sp = sp / max(np.linalg.norm(sp), 1e-12)
            th = math.radians(s["twist_deg"])
            c0 = np.array([1.0, 0.0, 0.0])
            # Rodrigues rotation of +x about the outboard span by +twist.
            # Positive twist is nose up (TE below the LE). Same sign as AVL Ainc.
            k = sp
            c = (c0 * math.cos(th) + np.cross(k, c0) * math.sin(th) + k * np.dot(k, c0) * (1 - math.cos(th)))
            t = np.cross(c, sp)
            t = t / np.linalg.norm(t)
            out.append((le[i], c, t, s["chord"], s["tc"]))
        return out

    def contains(self, P):
        L = self.to_local(P)
        fr = self._frames()
        best = np.full(len(L), -np.inf)
        m_camber, p_camber = self._naca4_mp() if self.naca4_mean_line else (0.0, 0.0)
        for (p0, c0, t0, ch0, tc0), (p1, c1, t1, ch1, tc1) in zip(fr[:-1], fr[1:]):
            s = p1 - p0
            e = s - np.dot(s, c0) * c0
            eta = (L - p0) @ e / max(np.dot(e, e), 1e-12)
            et = np.clip(eta, 0, 1)[:, None]
            le = p0 + et * s
            c = c0 + et * (c1 - c0)
            c /= np.linalg.norm(c, axis=1)[:, None]
            t = t0 + et * (t1 - t0)
            t /= np.linalg.norm(t, axis=1)[:, None]
            ch = ch0 + et[:, 0] * (ch1 - ch0)
            tc = tc0 + et[:, 0] * (tc1 - tc0)
            r = L - le
            xi = np.einsum("ij,ij->i", r, c) / ch
            ze = np.einsum("ij,ij->i", r, t)
            if self.naca4_mean_line:
                m = camber_clearance(xi, ze, tc, ch, m_camber, p_camber)
            else:
                m = naca_yt(xi, tc) * ch - np.abs(ze)
                m = np.where((xi < 0) | (xi > 1), -np.maximum(-xi, xi - 1) * ch - np.abs(ze), m)
            span_out = np.maximum(-eta, eta - 1) * math.sqrt(np.dot(e, e))
            m = np.where(span_out > 0, np.minimum(m, -span_out), m)
            best = np.maximum(best, m)
        return best

    def mesh(self, fine: int = 1):
        if self.naca4_mean_line:
            return self._mesh_naca4(fine)
        nx = 12 * fine
        xs = 0.5 * (1 - np.cos(np.linspace(0, np.pi, nx + 1)))          # cosine spacing 0..1
        V, loops = [], []
        for p, c, t, ch, tc in self._frames():
            yt = naca_yt(xs, tc) * ch
            up = [p + x * ch * c + y * t for x, y in zip(xs[::-1], yt[::-1])]     # TE → LE (upper)
            lo = [p + x * ch * c - y * t for x, y in zip(xs[1:-1], yt[1:-1])]     # LE+ → TE- (lower)
            loops.append(list(range(len(V), len(V) + len(up) + len(lo))))
            V += up + lo
        n = len(loops[0])
        F = []
        for la, lb in zip(loops[:-1], loops[1:]):
            for i in range(n):
                j = (i + 1) % n
                F += [(la[i], la[j], lb[j]), (la[i], lb[j], lb[i])]
        for loop, end in ((loops[0], 0), (loops[-1], 1)):
            c = len(V)
            V.append(np.mean([V[i] for i in loop], axis=0))
            F += [(c, loop[(i + 1) % n], loop[i]) if end == 0 else (c, loop[i], loop[(i + 1) % n]) for i in range(n)]
        return self._finish(np.array(V, float), np.array(F, int))

    def _mesh_naca4(self, fine: int = 1):
        """Closed mesh with the opted-in mean line. Same panel count as :meth:`mesh`."""
        m, p = self._naca4_mp()
        nx = 12 * fine
        xs = 0.5 * (1 - np.cos(np.linspace(0, np.pi, nx + 1)))
        V, loops = [], []
        for le, c, t, ch, tc in self._frames():
            xu, zu, xl, zl = naca4_surface(xs, tc, m, p)
            up = [le + float(xu_) * ch * c + float(zu_) * ch * t
                  for xu_, zu_ in zip(xu[::-1], zu[::-1])]
            lo = [le + float(xl_) * ch * c + float(zl_) * ch * t
                  for xl_, zl_ in zip(xl[1:-1], zl[1:-1])]
            loops.append(list(range(len(V), len(V) + len(up) + len(lo))))
            V += up + lo
        n = len(loops[0])
        F = []
        for la, lb in zip(loops[:-1], loops[1:]):
            for i in range(n):
                j = (i + 1) % n
                F += [(la[i], la[j], lb[j]), (la[i], lb[j], lb[i])]
        for loop, end in ((loops[0], 0), (loops[-1], 1)):
            c = len(V)
            V.append(np.mean([V[i] for i in loop], axis=0))
            F += [(c, loop[(i + 1) % n], loop[i]) if end == 0 else (c, loop[i], loop[(i + 1) % n])
                  for i in range(n)]
        return self._finish(np.array(V, float), np.array(F, int))

    def planform_area(self) -> float:
        """Area of the panels on their own planes, Σ ½(c_i + c_i+1)·|spanwise ⟂ chord| (one instance)."""
        fr = self._frames()
        a = 0.0
        for (p0, c0, _t0, ch0, _), (p1, _c1, _t1, ch1, _) in zip(fr[:-1], fr[1:]):
            s = p1 - p0
            a += 0.5 * (ch0 + ch1) * float(np.linalg.norm(s - np.dot(s, c0) * c0))
        return a

    def with_declared_thickness(self, tc_root: float, tc_tip: float, airfoil: str | None = None):
        """Copy whose section t/c follows the declared root and tip. Planform and twist stay.

        Intermediate stations are linear in leading-edge arc length. ``airfoil`` is stored as the
        designation; it does not add a mean line. The record says whether that camber is a gap.
        A mean line already opted in stays on, and the designation then has to be a cambered
        4-digit name. This method does not turn the opt-in on.
        """
        import copy
        tc_root = float(tc_root)
        tc_tip = float(tc_tip)
        if not (math.isfinite(tc_root) and math.isfinite(tc_tip)) or tc_root <= 0.0 or tc_tip <= 0.0:
            raise ValueError("t/c declarado tem de ser positivo e finito; não se substitui por zero")
        out = copy.deepcopy(self)
        les = np.array([s["le"] for s in out.sections], float)
        seg = np.linalg.norm(np.diff(les, axis=0), axis=1)
        total = float(seg.sum()) if len(seg) else 0.0
        if total < 1e-12:
            raise ValueError("secções coincidentes; o t/c não é interpolado")
        frac = np.concatenate([[0.0], np.cumsum(seg) / total])
        for sec, f in zip(out.sections, frac):
            sec["tc"] = float(tc_root + (tc_tip - tc_root) * float(f))
        if airfoil is not None:
            out.airfoil = str(airfoil)
        if out.naca4_mean_line:
            return out, naca4_mean_line_record(out.airfoil, tc_root, tc_tip)
        return out, section_thickness_record(out.airfoil, tc_root, tc_tip)

    def with_naca4_mean_line(self):
        """Copy that builds the NACA 4-digit mean line of ``self.airfoil``.

        Opt-in, per surface. The default loft is unchanged. The designation must be four digits
        with camber, and the camber position must be 1–9 tenths of chord. ``p = 0`` is refused.
        Planform, twist and the declared t/c stay. The thickness digits of the name do not
        replace that t/c.
        """
        import copy
        rec = naca4_mean_line_record(self.airfoil, self.sections[0]["tc"], self.sections[-1]["tc"])
        out = copy.deepcopy(self)
        out.naca4_mean_line = True
        return out, rec


# --------------------------------------------------------------------------------------------- Disc
@dataclass
class Disc(Component):
    """Propeller / rotor disc: ``origin`` = hub centre, local x = shaft axis (use orientation to tilt)."""
    diameter: float = 1.0
    thickness: float = 0.05
    hub_diameter: float = 0.0

    def contains(self, P):
        L = self.to_local(P)
        r = np.hypot(L[:, 1], L[:, 2])
        return np.minimum(self.diameter / 2 - r, self.thickness / 2 - np.abs(L[:, 0]))

    def mesh(self, fine: int = 1):
        nc = 32 * fine
        t = np.linspace(0, 2 * np.pi, nc, endpoint=False)
        R, h = self.diameter / 2, self.thickness / 2
        V = [(-h, 0, 0), (h, 0, 0)] + [(-h, R * math.cos(a), R * math.sin(a)) for a in t] + \
            [(h, R * math.cos(a), R * math.sin(a)) for a in t]
        F = []
        for i in range(nc):
            j = (i + 1) % nc
            a0, a1, b0, b1 = 2 + i, 2 + j, 2 + nc + i, 2 + nc + j
            F += [(0, a1, a0), (1, b0, b1), (a0, a1, b1), (a0, b1, b0)]
        return self._finish(np.array(V, float), np.array(F, int))

    def volume(self) -> float:
        return math.pi * self.diameter ** 2 / 4 * self.thickness


TYPES = {"body": Body, "surface": Surface, "disc": Disc}
