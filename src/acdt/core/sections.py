"""Parametric thin-walled beam cross-sections (Phase 6): I, C (channel), Z, T, angle, hat, rectangular and
circular tubes, built-up spar (caps + web).

Every profile is a set of straight mid-line segments ``(i, j, t)`` between points ``(y, z)``. Section properties
follow classical thin-walled beam theory:

* A, centroid, I_yy = ∫z² dA, I_zz = ∫y² dA, I_yz (exact for linear segments, Simpson-exact integrands);
* St-Venant torsion constant: open parts J = Σ b t³/3; closed single cell (tubes) Bredt–Batho
  J = 4 A_e² / ∮ds/t (Megson, *Aircraft Structures*, 6th ed., §§18–19);
* open sections: shear centre and warping constant Γ from the sectorial coordinate ω (Vlasov 1961; Megson §27;
  Timoshenko & Gere, *Theory of Elastic Stability* 1961, §5.?). Closed doubly-symmetric tubes have the shear centre
  at the centroid and Γ ≈ 0 (thin-walled, neglected).

Strength / stability (allowable compressive stress of the whole member, short column — crippling):

* local plate buckling of each segment: σ_cr = k π²E/(12(1−ν²)) (t/b)², k = 4.0 (both edges supported, long
  plate) or k = 0.43 (one edge free) — Bruhn, *Analysis & Design of Flight Vehicle Structures* 1973, Fig. C5.2;
  NACA TN 3781 (Gerard & Becker 1957);
* crippling (Gerard 1958, NACA TN 3784 / Bruhn §C7.7):
  - sections with distorted unloaded edges (angles, tubes, multi-corner): F_cs/F_cy = 0.56 [(g t²/A)(E/F_cy)^½]^0.85
  - sections with straight unloaded edges (T, cruciform, H/I): F_cs/F_cy = 0.67 [(g t²/A)(E/F_cy)^½]^0.40
  - two-corner sections (Z, J, channel): F_cs/F_cy = 3.2 [(t²/A)(E/F_cy)^⅓]^0.75
  with g = number of flanges + cuts (Gerard): angle 2, T 3, cruciform 4, I/H 7, square tube 12, hat 17.
* Needham (1954) angle-unit method as cross-check: F_cs = C_e √(F_cy E)/(b'/t)^0.75, C_e = 0.316 (two edges free),
  0.342 (one edge free), 0.366 (no edge free); b' = (a+b)/2 per angle unit.
* thin circular tubes: classical axial buckling 0.605 E t/R × NASA SP-8007 (1968) knock-down
  γ = 1 − 0.901(1 − e^−φ), φ = √(R/t)/16.

``LIMITATION``: Bruhn Table C7.1 cut-off values of F_cs/F_cy were not retrieved; crippling is capped at F_cy
(``cutoff`` argument, default 1.0 × F_cy, user-settable)."""
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np

K_SS = 4.0          # long plate, both unloaded edges simply supported
K_FREE = 0.43       # long plate, one unloaded edge free (0.425)


@dataclass
class Profile:
    kind: str
    pts: np.ndarray                    # (n, 2) mid-line points (y, z)
    segs: list                         # [(i, j, t)]
    closed: bool = False
    gerard: str = "multi_corner"       # multi_corner | straight_edges | two_corner | tube
    g: float = 2.0
    dims: dict = field(default_factory=dict)

    # --------------------------------------------------------------------------------- basic integrals
    def _seg_arrays(self):
        p = self.pts
        i = np.array([s[0] for s in self.segs])
        j = np.array([s[1] for s in self.segs])
        t = np.array([s[2] for s in self.segs], float)
        L = np.hypot(*(p[j] - p[i]).T)
        return i, j, t, L

    @staticmethod
    def _int2(fi, fj, gi, gj, tL):
        """∫ f g dA for linear f, g along a segment (exact)."""
        return tL / 6.0 * (2 * fi * gi + 2 * fj * gj + fi * gj + fj * gi)

    def properties(self) -> dict:
        p = self.pts
        i, j, t, L = self._seg_arrays()
        tL = t * L
        A = tL.sum()
        yc = np.sum(tL * (p[i, 0] + p[j, 0]) / 2) / A
        zc = np.sum(tL * (p[i, 1] + p[j, 1]) / 2) / A
        y, z = p[:, 0] - yc, p[:, 1] - zc
        Iyy = np.sum(self._int2(z[i], z[j], z[i], z[j], tL))
        Izz = np.sum(self._int2(y[i], y[j], y[i], y[j], tL))
        Iyz = np.sum(self._int2(y[i], y[j], z[i], z[j], tL))
        out = {"A": A, "yc": yc, "zc": zc, "Iyy": Iyy, "Izz": Izz, "Iyz": Iyz}
        if self.closed:
            # single cell polygon through the segment loop (Bredt–Batho)
            Ae = abs(0.5 * np.sum(p[i, 0] * p[j, 1] - p[j, 0] * p[i, 1]))
            out["J"] = 4 * Ae ** 2 / np.sum(L / t)
            out["Ae"] = Ae
            out["y_sc"], out["z_sc"] = (self.dims.get("y_sc", yc), self.dims.get("z_sc", zc))
            out["Gamma"] = 0.0
        else:
            out["J"] = float(np.sum(L * t ** 3) / 3.0)
            out.update(self._shear_centre_open(y, z, i, j, t, L, Iyy, Izz, Iyz))
            out["y_sc"] += yc
            out["z_sc"] += zc
        out["r_min"] = math.sqrt(min(np.linalg.eigvalsh([[Iyy, Iyz], [Iyz, Izz]])) / A)
        return out

    def _sectorial(self, y, z, i, j, pole):
        """Sectorial coordinate ω at every point (tree traversal from point 0), pole (y0, z0)."""
        adj = defaultdict(list)
        for s, (a, b) in enumerate(zip(i, j)):
            adj[a].append((b, s))
            adj[b].append((a, s))
        w = np.full(len(y), np.nan)
        w[i[0]] = 0.0
        dq = deque([i[0]])
        y0, z0 = pole
        while dq:
            a = dq.popleft()
            for b, _ in adj[a]:
                if np.isnan(w[b]):
                    w[b] = w[a] + ((y[a] - y0) * (z[b] - z0) - (z[a] - z0) * (y[b] - y0))
                    dq.append(b)
        return w

    def _shear_centre_open(self, y, z, i, j, t, L, Iyy, Izz, Iyz):
        tL = t * L
        w = self._sectorial(y, z, i, j, (0.0, 0.0))
        I = self._int2
        Iwy = np.sum(I(w[i], w[j], y[i], y[j], tL))
        Iwz = np.sum(I(w[i], w[j], z[i], z[j], tL))
        # ω_S = ω_P − Δy z + Δz y  (pole moved to (Δy, Δz)); orthogonality ∫ω_S y = ∫ω_S z = 0
        M = np.array([[-Iyz, Izz], [-Iyy, Iyz]])
        rhs = -np.array([Iwy, Iwz])
        try:
            dy, dz = np.linalg.solve(M, rhs)
        except np.linalg.LinAlgError:
            dy, dz = 0.0, 0.0
        ws = w - dy * z + dz * y
        A = tL.sum()
        w0 = np.sum(tL * (ws[i] + ws[j]) / 2) / A
        wn = ws - w0
        Gamma = float(np.sum(I(wn[i], wn[j], wn[i], wn[j], tL)))
        return {"y_sc": float(dy), "z_sc": float(dz), "Gamma": max(Gamma, 0.0)}

    # --------------------------------------------------------------------------------- stability
    def local_buckling(self, E: float, nu: float) -> dict:
        """Lowest local plate-buckling stress over the segments (k = 4 internal, 0.43 free-edge flange)."""
        deg = defaultdict(int)
        for a, b, _ in self.segs:
            deg[a] += 1
            deg[b] += 1
        best = (math.inf, None)
        if self.kind == "circular_tube":
            R, t = self.dims["R"], self.dims["t"]
            phi = math.sqrt(R / t) / 16.0
            gam = 1 - 0.901 * (1 - math.exp(-phi))
            return {"sigma_cr": gam * 0.605 * E * t / R, "segment": None, "gamma_SP8007": gam}
        for (a, b, tt), s in zip(self.segs, self._segment_plates()):
            if s is None:
                continue
            bw, free = s
            k = K_FREE if free else K_SS
            sc = k * math.pi ** 2 * E / (12 * (1 - nu ** 2)) * (tt / bw) ** 2
            if sc < best[0]:
                best = (sc, (a, b))
        return {"sigma_cr": best[0], "segment": best[1]}

    def _segment_plates(self):
        """Merge collinear chains into plates; returns per-segment (plate width, has_free_edge)."""
        deg = defaultdict(int)
        for a, b, _ in self.segs:
            deg[a] += 1
            deg[b] += 1
        p = self.pts
        out = []
        widths = self.dims.get("plates")
        for k, (a, b, tt) in enumerate(self.segs):
            if widths is not None:
                out.append(widths[k])
                continue
            L = float(np.hypot(*(p[b] - p[a])))
            out.append((L, deg[a] == 1 or deg[b] == 1))
        return out

    def crippling(self, E: float, Fcy: float, nu: float = 0.33, method: str = "gerard", cutoff: float = 1.0) -> dict:
        """Crippling (short-column) stress F_cs of the whole section (see module docstring)."""
        pr = self.properties()
        A = pr["A"]
        t = self.dims.get("t_ref") or float(np.average([s[2] for s in self.segs],
                                                          weights=self._seg_arrays()[3]))
        if self.kind == "circular_tube":
            Fcs = self.local_buckling(E, nu)["sigma_cr"]
            return {"Fcs": min(Fcs, cutoff * Fcy), "method": "SP-8007 cylinder", "ratio": Fcs / Fcy}
        if method == "needham":
            units = self.dims.get("needham_units") or []
            if not units:
                raise ValueError("Needham method needs 'needham_units' [(a, b, t, edges_free)]")
            num = den = 0.0
            Ce = {2: 0.316, 1: 0.342, 0: 0.366}
            for (a, b, tt, nf) in units:
                bp = (a + b) / 2
                f = Ce[nf] * math.sqrt(Fcy * E) / (bp / tt) ** 0.75
                Au = (a + b) * tt
                num += min(f, cutoff * Fcy) * Au
                den += Au
            return {"Fcs": num / den, "method": "needham", "ratio": num / den / Fcy}
        if self.gerard == "two_corner":
            r = 3.2 * ((t * t / A) * (E / Fcy) ** (1 / 3)) ** 0.75
        elif self.gerard == "straight_edges":
            r = 0.67 * ((self.g * t * t / A) * math.sqrt(E / Fcy)) ** 0.40
        else:
            r = 0.56 * ((self.g * t * t / A) * math.sqrt(E / Fcy)) ** 0.85
        return {"Fcs": min(r, cutoff) * Fcy, "method": f"gerard/{self.gerard}", "ratio": r, "g": self.g}

    def allowable(self, E, Fcy, nu=0.33, composite=False, cutoff=1.0) -> dict:
        """Short-column allowable: metals → Gerard crippling; composite equivalents (no plasticity, no post-buckling
        credit, conservative) → min(F_cy, local buckling)."""
        lb = self.local_buckling(E, nu)["sigma_cr"]
        if composite:
            return {"F": min(Fcy, lb), "local": lb, "Fcs": None}
        cr = self.crippling(E, Fcy, nu, cutoff=cutoff)["Fcs"]
        return {"F": min(cr, cutoff * Fcy), "local": lb, "Fcs": cr}


# ------------------------------------------------------------------------------------------------ factories
def _mk(kind, pts, segs, **kw):
    return Profile(kind, np.asarray(pts, float), segs, **kw)


def i_section(h, b, tf, tw, b_bot=None, tf_bot=None) -> Profile:
    """I / H section, outer depth h, flange width b (top) / b_bot, flange thickness tf, web tw (mid-line model)."""
    b2, t2 = b_bot or b, tf_bot or tf
    hw = h - (tf + t2) / 2
    pts = [(-b / 2, hw / 2), (0, hw / 2), (b / 2, hw / 2), (0, -hw / 2), (-b2 / 2, -hw / 2), (b2 / 2, -hw / 2)]
    segs = [(0, 1, tf), (1, 2, tf), (1, 3, tw), (4, 3, t2), (3, 5, t2)]
    plates = [(b / 2, True), (b / 2, True), (hw, False), (b2 / 2, True), (b2 / 2, True)]
    return _mk("I", pts, segs, gerard="straight_edges", g=7.0,
               dims={"h": h, "b": b, "tf": tf, "tw": tw, "plates": plates, "t_ref": None,
                     "needham_units": [(b / 2, hw / 2, (tf + tw) / 2, 1)] * 2 + [(b2 / 2, hw / 2, (t2 + tw) / 2, 1)] * 2})


def channel(h, b, tf, tw) -> Profile:
    """C (channel), web on y = 0, flanges towards +y."""
    hw = h - tf
    bf = b - tw / 2
    pts = [(bf, hw / 2), (0, hw / 2), (0, -hw / 2), (bf, -hw / 2)]
    segs = [(0, 1, tf), (1, 2, tw), (2, 3, tf)]
    plates = [(bf, True), (hw, False), (bf, True)]
    return _mk("C", pts, segs, gerard="two_corner", g=None,
               dims={"h": h, "b": b, "tf": tf, "tw": tw, "plates": plates,
                     "needham_units": [(bf, hw / 2, (tf + tw) / 2, 1)] * 2})


def z_section(h, b, tf, tw) -> Profile:
    hw = h - tf
    bf = b - tw / 2
    pts = [(bf, hw / 2), (0, hw / 2), (0, -hw / 2), (-bf, -hw / 2)]
    segs = [(0, 1, tf), (1, 2, tw), (2, 3, tf)]
    plates = [(bf, True), (hw, False), (bf, True)]
    return _mk("Z", pts, segs, gerard="two_corner", g=None,
               dims={"h": h, "b": b, "tf": tf, "tw": tw, "plates": plates,
                     "needham_units": [(bf, hw / 2, (tf + tw) / 2, 1)] * 2})


def t_section(h, b, tf, tw) -> Profile:
    hw = h - tf / 2
    pts = [(-b / 2, 0), (0, 0), (b / 2, 0), (0, -hw)]
    segs = [(0, 1, tf), (1, 2, tf), (1, 3, tw)]
    plates = [(b / 2, True), (b / 2, True), (hw, True)]
    return _mk("T", pts, segs, gerard="straight_edges", g=3.0, dims={"h": h, "b": b, "tf": tf, "tw": tw,
                                                                       "plates": plates})


def angle(a, b, t) -> Profile:
    pts = [(0, a - t / 2), (0, 0), (b - t / 2, 0)]
    segs = [(0, 1, t), (1, 2, t)]
    return _mk("L", pts, segs, gerard="multi_corner", g=2.0,
               dims={"a": a, "b": b, "t": t, "plates": [(a - t / 2, True), (b - t / 2, True)],
                     "needham_units": [(a, b, t, 2)]})


def hat(h, b_top, b_flange, t, b_bot=None) -> Profile:
    """Hat stringer: crown width b_top, webs depth h, attachment flanges b_flange, bottom opening b_bot (= b_top)."""
    bb = b_bot or b_top
    hw = h - t
    pts = [(-bb / 2 - b_flange, 0), (-bb / 2, 0), (-b_top / 2, hw), (b_top / 2, hw), (bb / 2, 0), (bb / 2 + b_flange, 0)]
    segs = [(0, 1, t), (1, 2, t), (2, 3, t), (3, 4, t), (4, 5, t)]
    web = math.hypot(hw, (bb - b_top) / 2)
    plates = [(b_flange, True), (web, False), (b_top, False), (web, False), (b_flange, True)]
    return _mk("hat", pts, segs, gerard="multi_corner", g=17.0, dims={"h": h, "b_top": b_top, "t": t, "plates": plates})


def rect_tube(h, b, t, tw=None) -> Profile:
    tw = tw or t
    H, B = h - t, b - tw
    pts = [(-B / 2, -H / 2), (B / 2, -H / 2), (B / 2, H / 2), (-B / 2, H / 2)]
    segs = [(0, 1, t), (1, 2, tw), (2, 3, t), (3, 0, tw)]
    return _mk("rect_tube", pts, segs, closed=True, gerard="multi_corner", g=12.0,
               dims={"h": h, "b": b, "t": t, "tw": tw, "plates": [(B, False), (H, False), (B, False), (H, False)],
                     "y_sc": 0.0, "z_sc": 0.0})


def circular_tube(D, t, n=72) -> Profile:
    R = (D - t) / 2
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    pts = np.c_[R * np.cos(th), R * np.sin(th)]
    segs = [(k, (k + 1) % n, t) for k in range(n)]
    return _mk("circular_tube", pts, segs, closed=True, gerard="tube", g=None,
               dims={"D": D, "R": R, "t": t, "plates": [None] * n, "y_sc": 0.0, "z_sc": 0.0})


def builtup_spar(h, b_cap, t_cap, t_web) -> Profile:
    """Built-up spar: web plate + two back-to-back angle caps at each end (riveted). Mid-line model: horizontal cap
    legs (b_cap total, thickness t_cap) and vertical cap legs (length b_cap/2) doubling the web locally
    (t_web + 2 t_cap). Crippling by Gerard multi-corner on the angle caps (g = 2 per angle, Bruhn C7)."""
    hw = h - t_cap
    leg = b_cap / 2
    pts = [(-leg, hw / 2), (0, hw / 2), (leg, hw / 2), (0, hw / 2 - leg), (0, -hw / 2 + leg), (-leg, -hw / 2),
           (0, -hw / 2), (leg, -hw / 2)]
    td = t_web + 2 * t_cap
    segs = [(0, 1, t_cap), (1, 2, t_cap), (1, 3, td), (3, 4, t_web), (6, 4, td), (5, 6, t_cap), (6, 7, t_cap)]
    plates = [(leg, True), (leg, True), (leg, True), (max(hw - 2 * leg, 1e-6), False), (leg, True), (leg, True),
              (leg, True)]
    return _mk("builtup", pts, segs, gerard="multi_corner", g=2.0,
               dims={"h": h, "b_cap": b_cap, "t_cap": t_cap, "t_web": t_web, "plates": plates, "t_ref": t_cap,
                     "needham_units": [(leg, leg, t_cap, 2)] * 4})


FACTORIES = {"I": i_section, "C": channel, "Z": z_section, "T": t_section, "L": angle, "hat": hat,
             "rect_tube": rect_tube, "circular_tube": circular_tube, "builtup": builtup_spar}


def spar(kind: str, h: float, b: float, tf: float, tw: float) -> Profile:
    """Spar profile of a given type for the wing-box sizing (caps = flanges)."""
    if kind == "builtup":
        return builtup_spar(h, b, tf, tw)
    if kind in ("I", "C", "Z"):
        return FACTORIES[kind](h, b, tf, tw)
    raise ValueError(f"spar section {kind!r} not supported (I, C, Z, builtup)")


def cap_area(kind: str, b: float, tf: float) -> float:
    """Area of ONE cap (flange or angle pair horizontal legs + vertical legs) of a spar section."""
    if kind == "builtup":
        return 2 * b * tf             # two angles (2 legs of b/2 each, ×2 angles)
    return b * tf


def compression_cap(kind: str, h: float, b: float, tf: float, tw: float) -> Profile:
    """Compressed half of a spar section under bending (flange/cap + half web), the member whose crippling governs
    the cap allowable. Conservative: the half-web is treated as uniformly compressed whereas its stress actually
    falls linearly to zero at the neutral axis (Bruhn §C7 practice of including the attached web)."""
    stub = max(h / 2 - tf / 2, 1e-6)
    if kind == "I":
        return t_section(stub + tf / 2, b, tf, tw)
    if kind in ("C", "Z"):
        return angle(stub + tf / 2, b, (tf * b + tw * stub) / (b + stub))
    if kind == "builtup":
        leg = b / 2
        td = tw + 2 * tf
        tstem = (td * min(leg, stub) + tw * max(stub - leg, 0)) / stub
        return t_section(stub + tf / 2, b, tf, tstem)
    raise ValueError(kind)


def spar_cap_allowable(kind, h, b, tf, tw, E, Fcy, nu=0.33, composite=False, cutoff=1.0) -> dict:
    """Allowable compressive stress of a spar cap: min(F_cy, crippling of the compressed half section) for metals;
    composite equivalents: min(F_cy, local buckling of the free flange) (no post-buckling credit)."""
    p = compression_cap(kind, h, b, tf, tw)
    a = p.allowable(E, Fcy, nu, composite=composite, cutoff=cutoff)
    a["profile"] = p.kind
    return a
