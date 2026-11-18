"""Integration requirements (equipment items + placement constraints) and the packaging / field-of-view checker.

Items are equipment with mass, a geometric shape (default axis-aligned box; opt-in sphere or cylinder),
power (average / peak), heat, an optional aperture and any
number of field-of-view requirements. Placement is expressed as **constraints**, never as fixed slots; an item
without ``position`` is placed by a deterministic grid search inside its host body (:func:`place`).

Methods (low fidelity, documented):

* Fit: sampling of each item's shape (27-point box grid; sphere/cylinder surface samples) against the host's
  signed clearance (:mod:`.components`); overlap/separation uses the AABB of the shape (conservative).
* FOV: ray casting from the aperture through a deterministic sample of the required solid angle (az/el grid
  or Fibonacci-lattice cone, González 2010) against the triangulated assembly, Möller–Trumbore 1997
  ray/triangle test. Blocked fraction = mean over rays of the opacity of the first opaque hit (parts transparent
  in the constraint's band are skipped, e.g. a radome for ``rf``). Margin = allowed − blocked fraction.
* Mass properties: Σ m, CG = Σ m·r / Σ m; inertia of items as uniform solid box / sphere / cylinder
  (Meriam & Kraige) + Steiner; components as point masses at their CG (PRESSUPOSTO).

Directions: azimuth from the nose (−x) towards starboard (+y), elevation positive up (z):
d = (−cos el cos az, cos el sin az, sin el)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .assembly import Assembly
from .components import ASSUMPTIONS as GEOM_ASSUMPTIONS, Body, Surface

ASSUMPTIONS = GEOM_ASSUMPTIONS + [
    "PRESSUPOSTO: equipamento por omissão como caixa alinhada com os eixos (massa uniforme); shape=sphere|cylinder usa sólido homogéneo (Meriam & Kraige). A separação entre itens usa a AABB da forma (conservador).",
    "PRESSUPOSTO: campo de visão amostrado por raios discretos (passo por omissão 5° em az/el); obstruções "
    "menores que o passo podem escapar — reduzir `step_deg` para confirmar.",
    "PRESSUPOSTO: fração bloqueada admissível por omissão 0 (campo totalmente livre).",
    "PRESSUPOSTO: CG de cada componente sem `cg` = centróide geométrico do volume.",
]
METHOD = ("packaging: signed clearance of shape sample points (Lamé / NACA thickness); "
          "AABB of the shape for overlap/separation. FOV: ray casting, Möller & Trumbore (1997), az/el or "
          "Fibonacci cone (González 2010). Mass: Σm·r; solid box/sphere/cylinder + Steiner (Meriam & Kraige).")


def direction(az_deg, el_deg):
    az, el = np.radians(az_deg), np.radians(el_deg)
    return np.stack([-np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)], axis=-1)


@dataclass
class Item:
    name: str
    mass_kg: float = 0.0
    size_m: tuple = (0.0, 0.0, 0.0)          # bounding box lx, ly, lz (aircraft axes)
    position: tuple | None = None            # box centroid; None → placed by :func:`place`
    host: str | None = None                  # body / surface it must be inside (shortcut for 'within')
    cg_offset: tuple = (0.0, 0.0, 0.0)
    aperture_offset: tuple | None = None     # FOV origin relative to the centroid (default: centroid)
    power_w: dict = field(default_factory=dict)   # {avg, peak}
    heat_w: float | None = None
    fov: list = field(default_factory=list)  # [{name, band, az_deg:[a,b], el_deg:[a,b] | axis, half_angle_deg,
    #                                            step_deg, max_blocked_frac, range_m, ignore}]
    prefer: dict = field(default_factory=dict)    # placement preference {x|y|z: value | "min" | "max"}
    obstructs: bool = False                  # external item (turret, antenna) that also blocks other FOVs
    transparent_to: tuple = ()
    protuberance: bool = True                # counted as an automatic protuberance where it leaves the parts
    protuberance_shape: str = "box"          # box | sphere | cylinder (drag.CD_SHAPE, Hoerner 1965 Ch. III)
    shape: str = "box"                       # box | sphere | cylinder — packaging / FOV / volume / inertia
    cylinder_axis: str = "x"                 # aircraft axis of the cylinder generator (x|y|z)
    group: str = ""                          # mass group for sizing (payload | fuel | equipment | propulsion)
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        d = dict(d)
        for k in ("size_m", "position", "cg_offset", "aperture_offset"):
            if d.get(k) is not None:
                d[k] = tuple(float(v) for v in d[k])
        if isinstance(d.get("power_w"), (int, float)):
            d["power_w"] = {"avg": float(d["power_w"]), "peak": float(d["power_w"])}
        if isinstance(d.get("fov"), dict):
            d["fov"] = [d["fov"]]
        unknown = set(d) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"item {d.get('name')!r}: unknown fields {sorted(unknown)}")
        it = cls(**d)
        sh = (it.shape or "box").lower()
        if sh not in ("box", "sphere", "cylinder"):
            raise ValueError(f"item {it.name!r}: shape must be box|sphere|cylinder (got {it.shape!r})")
        ax = (it.cylinder_axis or "x").lower()
        if ax not in ("x", "y", "z"):
            raise ValueError(f"item {it.name!r}: cylinder_axis must be x|y|z (got {it.cylinder_axis!r})")
        it.shape, it.cylinder_axis = sh, ax
        return it

    def half_extents(self):
        """AABB half-sizes [m] of the shape (sphere → (r,r,r); cylinder → L/2 along axis, r elsewhere)."""
        s = np.asarray(self.size_m, float)
        if self.shape == "sphere":
            r = 0.5 * float(np.max(s)) if np.any(s) else 0.0
            return np.array([r, r, r])
        if self.shape == "cylinder":
            ax = "xyz".index(self.cylinder_axis)
            length = float(s[ax])
            others = [s[i] for i in range(3) if i != ax]
            diam = float(max(others)) if others else 0.0
            if diam <= 0 and length > 0:
                diam = length  # PRESSUPOSTO when only the axial size is given
            h = np.array([diam / 2, diam / 2, diam / 2])
            h[ax] = length / 2
            return h
        return s / 2

    def volume_m3(self) -> float:
        """Homogeneous solid volume (Meriam & Kraige geometry)."""
        s = np.asarray(self.size_m, float)
        if self.shape == "sphere":
            r = 0.5 * float(np.max(s))
            return 4.0 / 3.0 * math.pi * r ** 3
        if self.shape == "cylinder":
            h = self.half_extents()
            ax = "xyz".index(self.cylinder_axis)
            r = float(max(h[i] for i in range(3) if i != ax))
            return math.pi * r * r * (2 * float(h[ax]))
        return float(np.prod(s))

    def box(self, pos=None):
        c = np.asarray(self.position if pos is None else pos, float)
        h = self.half_extents()
        return c - h, c + h

    def samples(self, pos=None):
        """Interior/surface sample points for host fit (shape-aware; box keeps the 27-point grid)."""
        c = np.asarray(self.position if pos is None else pos, float)
        if self.shape == "box":
            lo, hi = self.box(pos)
            g = [np.array([lo[i], (lo[i] + hi[i]) / 2, hi[i]]) for i in range(3)]
            return np.array(np.meshgrid(*g, indexing="ij")).reshape(3, -1).T
        h = self.half_extents()
        if self.shape == "sphere":
            r = float(h[0])
            pts = [c]
            for i in range(3):
                e = np.zeros(3)
                e[i] = r
                pts += [c + e, c - e]
            for i in range(3):
                for j in range(i + 1, 3):
                    e = np.zeros(3)
                    e[i] = r / math.sqrt(2)
                    e[j] = r / math.sqrt(2)
                    pts.append(c + e)
                    e2 = e.copy(); e2[j] = -e2[j]; pts.append(c + e2)
            return np.asarray(pts, float)
        ax = "xyz".index(self.cylinder_axis)
        length_h = float(h[ax])
        r = float(max(h[i] for i in range(3) if i != ax))
        pts = [c]
        e_ax = np.zeros(3); e_ax[ax] = length_h
        pts += [c + e_ax, c - e_ax]
        comps = [i for i in range(3) if i != ax]
        for k in range(8):
            th = 2 * math.pi * k / 8
            e = np.zeros(3)
            e[comps[0]] = r * math.cos(th)
            e[comps[1]] = r * math.sin(th)
            pts.append(c + e)
            pts.append(c + e + 0.5 * e_ax)
            pts.append(c + e - 0.5 * e_ax)
        return np.asarray(pts, float)

    def aperture(self, pos=None):
        c = np.asarray(self.position if pos is None else pos, float)
        return c + np.asarray(self.aperture_offset or (0, 0, 0), float)

    def inertia_about_centroid(self) -> np.ndarray:
        """3×3 inertia [kg·m²] of a uniform solid about the item centroid (Meriam & Kraige)."""
        m = float(self.mass_kg)
        if m <= 0:
            return np.zeros((3, 3))
        if self.shape == "sphere":
            r = float(self.half_extents()[0])
            I = 2.0 / 5.0 * m * r * r
            return np.diag([I, I, I])
        if self.shape == "cylinder":
            h = self.half_extents()
            ax = "xyz".index(self.cylinder_axis)
            L = 2 * float(h[ax])
            r = float(max(h[i] for i in range(3) if i != ax))
            I_ax = 0.5 * m * r * r
            I_tr = 0.25 * m * r * r + m * L * L / 12.0
            I = np.diag([I_tr, I_tr, I_tr])
            I[ax, ax] = I_ax
            return I
        a, b, cc = np.asarray(self.size_m, float)
        return m / 12.0 * np.diag([b * b + cc * cc, a * a + cc * cc, a * a + b * b])


def _box_gap(a, b):
    """Separation [m] between two AABBs (negative = penetration depth along the least-overlap axis)."""
    (a0, a1), (b0, b1) = a, b
    gap = np.maximum(b0 - a1, a0 - b1)
    if np.all(gap < 0):
        return float(gap.max())
    return float(np.linalg.norm(np.maximum(gap, 0)))


# --------------------------------------------------------------------------------------------- rays
def cast(origins, dirs, tris, eps=1e-9, chunk=128):
    """First-hit distance per ray per triangle (Möller & Trumbore 1997); returns t (nr, nt) with inf = no hit."""
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    out = []
    for s in range(0, len(dirs), chunk):
        D = dirs[s:s + chunk][:, None, :]
        O = origins[s:s + chunk][:, None, :]
        p = np.cross(D, e2[None])
        det = np.einsum("rtk,tk->rt", p, e1)
        ok = np.abs(det) > eps
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = O - v0[None]
        u = np.einsum("rtk,rtk->rt", tv, p) * inv
        q = np.cross(tv, e1[None])
        v = np.einsum("rk,rtk->rt", D[:, 0], q) * inv
        t = np.einsum("rtk,tk->rt", q, e2) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6)
        out.append(np.where(hit, t, np.inf))
    return np.concatenate(out)


def fov_directions(spec: dict):
    """Deterministic sample of the required solid angle: az/el grid or a Fibonacci cone about ``axis``."""
    step = float(spec.get("step_deg", 5.0))
    if "axis" in spec or "half_angle_deg" in spec:
        ax = np.asarray(spec.get("axis", (0, 0, 1)), float)
        ax /= np.linalg.norm(ax)
        ha = math.radians(float(spec["half_angle_deg"]))
        n = max(16, int(math.ceil(2 * math.pi * (1 - math.cos(ha)) / math.radians(step) ** 2)))
        i = np.arange(n) + 0.5
        cz = 1 - i / n * (1 - math.cos(ha))                         # uniform in solid angle
        ph = i * math.pi * (3 - math.sqrt(5))
        sz = np.sqrt(1 - cz ** 2)
        loc = np.stack([sz * np.cos(ph), sz * np.sin(ph), cz], axis=1)
        a = np.array([1.0, 0, 0]) if abs(ax[0]) < 0.9 else np.array([0, 1.0, 0])
        u = np.cross(ax, a)
        u /= np.linalg.norm(u)
        w = np.cross(ax, u)
        d = loc[:, :1] * u + loc[:, 1:2] * w + loc[:, 2:] * ax
        return d, None
    az0, az1 = spec.get("az_deg", (-180.0, 180.0))
    el0, el1 = spec.get("el_deg", (-90.0, 90.0))
    full = (az1 - az0) >= 360 - 1e-9
    naz = max(1, int(math.ceil((az1 - az0) / step)))
    az = np.linspace(az0, az1, naz if full else naz + 1, endpoint=not full)
    el = np.linspace(el0, el1, max(1, int(math.ceil((el1 - el0) / step))) + 1)
    A, E = np.meshgrid(az, el, indexing="ij")
    return direction(A.ravel(), E.ravel()), np.stack([A.ravel(), E.ravel()], axis=1)


def check_fov(asm: Assembly, origin, spec: dict, tris_owner=None) -> dict:
    tris, owner = tris_owner or asm.triangles()
    band = spec.get("band")
    ignore = set(spec.get("ignore", ()))
    keep = np.array([not (c.name in ignore or (band and band in c.transparent_to) or c.opacity <= 0)
                     for c in asm.components])
    sel = keep[owner]
    tris, owner = tris[sel], owner[sel]
    dirs, azel = fov_directions(spec)
    O = np.repeat(np.asarray(origin, float)[None], len(dirs), axis=0)
    rng = float(spec.get("range_m", math.inf))
    blocked = np.zeros(len(dirs))
    by = {}
    if len(tris):
        t = cast(O, dirs, tris)
        j = np.argmin(t, axis=1)
        tmin = t[np.arange(len(dirs)), j]
        hit = tmin < rng
        op = np.array([c.opacity for c in asm.components])
        blocked = np.where(hit, op[owner[j]], 0.0)
        for k in np.flatnonzero(hit):
            nm = asm.components[owner[j[k]]].name
            by[nm] = by.get(nm, 0.0) + blocked[k] / len(dirs)
    frac = float(blocked.mean()) if len(dirs) else 0.0
    allow = float(spec.get("max_blocked_frac", 0.0))
    res = {"name": spec.get("name", "fov"), "band": band, "n_rays": int(len(dirs)), "blocked_frac": frac,
           "max_blocked_frac": allow, "margin": allow - frac, "ok": frac <= allow + 1e-12,
           "blocked_by": dict(sorted(by.items(), key=lambda kv: -kv[1]))}
    if azel is not None and frac > 0:
        bad = azel[blocked > 0]
        res["blocked_samples_az_el_deg"] = bad[:: max(1, len(bad) // 24)][:24].tolist()
        res["blocked_az_range_deg"] = [float(bad[:, 0].min()), float(bad[:, 0].max())]
        res["blocked_el_range_deg"] = [float(bad[:, 1].min()), float(bad[:, 1].max())]
    return res


# --------------------------------------------------------------------------------------------- constraints
def _zone_margin(zone: dict, P, asm: Assembly):
    """Signed clearance of points to a keep-out zone (positive = outside): box, sphere or a component name."""
    P = np.atleast_2d(P)
    if "component" in zone:
        return -asm.get(zone["component"]).contains(P) - float(zone.get("clearance_m", 0.0))
    if "sphere" in zone:
        c, r = np.asarray(zone["sphere"]["center"], float), float(zone["sphere"]["radius"])
        return np.linalg.norm(P - c, axis=1) - r
    if "box" in zone:
        lo, hi = (np.asarray(v, float) for v in zone["box"])
        d = np.maximum(lo - P, P - hi)
        return np.where(np.all(d < 0, axis=1), d.max(axis=1), np.linalg.norm(np.maximum(d, 0), axis=1))
    raise ValueError(f"keep_out zone needs component | sphere | box: {zone}")


def _eval_item_constraints(asm, items, it: Item, pos, cons, placed: dict, with_fov=True, tris_owner=None):
    """Constraints touching one item at ``pos``; returns a list of results (for placement and checking)."""
    res = []
    P = it.samples(pos)
    hosts = ([it.host] if it.host else []) + [c["body"] for c in cons
                                              if c["type"] == "within" and c.get("item") == it.name]
    for h in hosts:
        m = float(asm.get(h).contains(P).min())
        res.append({"type": "within", "item": it.name, "body": h, "margin": m, "unit": "m", "ok": m >= 0})
    c = np.asarray(pos, float)
    for k in cons:
        t = k["type"]
        if t == "range" and k.get("item") == it.name:
            i = "xyz".index(k["axis"])
            lo, hi = k.get("min", -math.inf), k.get("max", math.inf)
            m = float(min(c[i] - lo, hi - c[i]))
            res.append({"type": "range", "item": it.name, "axis": k["axis"], "value": float(c[i]), "margin": m,
                        "unit": "m", "ok": m >= 0})
        elif t == "keep_out" and (k.get("items", "*") == "*" or it.name in k.get("items", ())):
            m = float(_zone_margin(k["zone"], P, asm).min())
            res.append({"type": "keep_out", "item": it.name, "zone": k.get("name", str(k["zone"])), "margin": m,
                        "unit": "m", "ok": m >= 0})
        elif t in ("min_separation", "max_distance") and it.name in (k["a"], k["b"]):
            other = k["b"] if k["a"] == it.name else k["a"]
            if other not in placed:
                continue
            g = _box_gap(it.box(pos), items[other].box(placed[other]))
            if t == "min_separation":
                m = g - float(k["distance_m"])
            else:
                g = float(np.linalg.norm(c - np.asarray(placed[other], float)))
                m = float(k["distance_m"]) - g
            res.append({"type": t, "a": k["a"], "b": k["b"], "value": g, "margin": m, "unit": "m", "ok": m >= 0})
    for o, op in placed.items():                                    # implicit: no overlap between items
        if o == it.name:
            continue
        g = _box_gap(it.box(pos), items[o].box(op))
        if g < 0:
            res.append({"type": "no_overlap", "a": it.name, "b": o, "margin": g, "unit": "m", "ok": False})
    if with_fov:
        fovs = list(it.fov) + [{"name": "sky_view", "band": k.get("band", "rf"),
                                "axis": (0, 0, 1), "half_angle_deg": 90.0 - float(k.get("el_min_deg", 10.0)),
                                **{x: k[x] for x in ("step_deg", "max_blocked_frac", "ignore") if x in k}}
                               for k in cons if k["type"] == "sky_view" and k.get("item") == it.name]
        for f in fovs:
            r = check_fov(asm, it.aperture(pos), f, tris_owner)
            res.append({"type": "fov", "item": it.name, **r, "unit": "fraction"})
    return res


def _item_body(it: Item) -> Body:
    """Mesh used as an FOV / packaging obstacle. Box stays a rectangular Body; sphere / cylinder use
    circular Lamé sections (n=2) along the generator — open primitives, not a closed catalog."""
    c = np.asarray(it.position, float)
    h = it.half_extents()
    if it.shape == "sphere":
        r = float(h[0])
        xs = np.linspace(0.0, 2 * r, 9)
        stations = []
        for x in xs:
            rr = math.sqrt(max(r * r - (x - r) ** 2, 0.0))
            stations.append({"x": float(x), "w": 2 * rr, "h": 2 * rr, "n": 2.0})
        return Body(name="item:" + it.name, role="item",
                    origin=(float(c[0] - r), float(c[1]), float(c[2])),
                    stations=stations, transparent_to=tuple(it.transparent_to))
    if it.shape == "cylinder":
        ax = it.cylinder_axis
        L = 2 * float(h["xyz".index(ax)])
        r = float(max(h[i] for i in range(3) if i != "xyz".index(ax)))
        stations = [{"x": 0.0, "w": 2 * r, "h": 2 * r, "n": 2.0},
                    {"x": L, "w": 2 * r, "h": 2 * r, "n": 2.0}]
        if ax == "x":
            origin = (float(c[0] - L / 2), float(c[1]), float(c[2]))
            ori = {}
        elif ax == "y":
            origin = (float(c[0]), float(c[1] - L / 2), float(c[2]))
            ori = {"yaw": 90.0}
        else:
            origin = (float(c[0]), float(c[1]), float(c[2] - L / 2))
            ori = {"pitch": -90.0}
        return Body(name="item:" + it.name, role="item", origin=origin, orientation=ori,
                    stations=stations, transparent_to=tuple(it.transparent_to))
    lx, ly, lz = (float(v) for v in it.size_m)
    x0 = float(c[0] - lx / 2)
    return Body(name="item:" + it.name, role="item", origin=(x0, float(c[1]), float(c[2])),
                stations=[{"x": 0.0, "w": ly, "h": lz, "n": 12.0}, {"x": lx, "w": ly, "h": lz, "n": 12.0}],
                transparent_to=tuple(it.transparent_to))


def mass_properties(asm: Assembly, items: dict, positions: dict, base: dict | None = None) -> dict:
    m_list = []
    for it in items.values():
        if positions.get(it.name) is None or it.mass_kg <= 0:
            continue
        r = np.asarray(positions[it.name], float) + np.asarray(it.cg_offset, float)
        m_list.append((it.name, it.mass_kg, r, it))
    for c in asm.components:
        if c.mass_kg and c.role != "item":
            m_list.append((c.name, float(c.mass_kg),
                           np.asarray(c.cg if c.cg is not None else c.centroid(), float), None))
    if base:
        m_list.append(("base", float(base["mass_kg"]), np.asarray(base["cg"], float), None))
    if not m_list:
        return {"mass_kg": 0.0}
    M = sum(m for _, m, _, _ in m_list)
    cg = sum(m * r for _, m, r, _ in m_list) / M
    I = np.zeros((3, 3))
    shapes = {}
    for name, m, r, it in m_list:
        if it is not None:
            Ib = it.inertia_about_centroid()
            shapes[name] = it.shape
        else:
            Ib = np.zeros((3, 3))
        d = r - cg
        I += Ib + m * (np.dot(d, d) * np.eye(3) - np.outer(d, d))
    return {"mass_kg": M, "cg": cg.tolist(),
            "inertia_kg_m2": {"Ixx": I[0, 0], "Iyy": I[1, 1], "Izz": I[2, 2], "Ixz": -I[0, 2]},
            "item_shapes": shapes,
            "breakdown": {n: {"mass_kg": m, "r": r.tolist(),
                              **({"shape": it.shape, "volume_m3": it.volume_m3()} if it is not None else {})}
                          for n, m, r, it in m_list}}



def place(asm, items: dict, cons, positions: dict, tris_owner=None, max_fov_evals=40) -> dict:
    """Deterministic placement of items without ``position``: grid over the host bounding box (pitch =
    max(smallest item side / 2, host size / 40)), keep candidates meeting the geometric constraints with the
    items already placed (in input order), rank by ``prefer`` (default: closest to the host centroid) and take
    the first that also clears its FOV requirements. Not an optimiser: a feasibility search (P6 does shape/
    placement optimisation)."""
    log = {}
    for it in items.values():
        if positions.get(it.name) is not None:
            continue
        host = it.host or next((c["body"] for c in cons if c["type"] == "within" and c.get("item") == it.name), None)
        if host is None:
            log[it.name] = {"placed": False, "reason": "no position and no host/within constraint"}
            continue
        h = asm.get(host)
        lo, hi = h.bbox()
        pitch = max(min(s for s in it.size_m if s > 0) / 4 if any(it.size_m) else 0.02, float(np.max(hi - lo)) / 60)
        ref = h.centroid()
        axes = []
        for i in range(3):                       # grid centred on the host centroid (symmetric hosts → y = 0 row)
            a0, a1 = lo[i] + it.size_m[i] / 2, hi[i] - it.size_m[i] / 2
            k0, k1 = math.ceil((a0 - ref[i]) / pitch - 1e-9), math.floor((a1 - ref[i]) / pitch + 1e-9)
            axes.append(ref[i] + pitch * np.arange(k0, k1 + 1))
        if any(len(a) == 0 for a in axes):
            log[it.name] = {"placed": False, "reason": f"item larger than host {host!r} bounding box"}
            continue
        C = np.array(np.meshgrid(*axes, indexing="ij")).reshape(3, -1).T
        S = it.samples((0, 0, 0))
        inside = h.contains((C[:, None, :] + S[None]).reshape(-1, 3)).reshape(len(C), -1).min(axis=1) >= 0
        C = C[inside]
        ok = [c for c in C if all(r["ok"] for r in _eval_item_constraints(asm, items, it, c, cons, positions,
                                                                          with_fov=False))]
        if not ok:
            log[it.name] = {"placed": False, "reason": "no grid point meets the geometric constraints",
                            "host": host, "pitch_m": pitch}
            continue
        ok = np.array(ok)
        score = np.zeros(len(ok))
        span = np.maximum(hi - lo, 1e-9)
        for ax, v in (it.prefer or {}).items():
            i = "xyz".index(ax)
            if v == "min":
                score += (ok[:, i] - lo[i]) / span[i]
            elif v == "max":
                score += (hi[i] - ok[:, i]) / span[i]
            else:
                score += np.abs(ok[:, i] - float(v)) / span[i]
        if not it.prefer:
            score = np.linalg.norm((ok - ref) / span, axis=1)
        order = np.lexsort((ok[:, 2], ok[:, 1], ok[:, 0], score))
        chosen = None
        for n, k in enumerate(order[:max_fov_evals]):
            r = _eval_item_constraints(asm, items, it, ok[k], cons, positions, with_fov=True, tris_owner=tris_owner)
            if all(x["ok"] for x in r if x["type"] == "fov"):
                chosen = ok[k]
                break
        if chosen is None:
            log[it.name] = {"placed": False, "reason": f"FOV blocked at the {min(len(order), max_fov_evals)} "
                                                       "best-ranked feasible points", "host": host}
            continue
        positions[it.name] = tuple(float(v) for v in chosen)
        log[it.name] = {"placed": True, "position": list(positions[it.name]), "host": host, "pitch_m": pitch,
                        "n_feasible": int(len(ok))}
    return log


def check(assembly: dict | Assembly, items: list, constraints: list | None = None, base: dict | None = None,
          place_unpositioned: bool = True) -> dict:
    """Packaging + FOV + mass-properties check of equipment items in an assembly.

    ``constraints`` (any number, any combination): ``within {item, body}``; ``range {item, axis, min, max}``;
    ``min_separation {a, b, distance_m}`` (box gap, e.g. EMI / thermal); ``max_distance {a, b, distance_m}``
    (centroids, e.g. cable / waveguide length); ``keep_out {name, zone: {box | sphere | component,
    clearance_m}, items: '*' | [...]}``; ``sky_view {item, el_min_deg, band}`` (SATCOM / GNSS); ``cg_range
    {axis, min, max}`` on the total; ``max_packing_fraction {body, max}``. FOV requirements live on the items
    (``fov``). Returns per-constraint margins, violations, placements, mass / CG / inertia, power and heat."""
    asm = assembly if isinstance(assembly, Assembly) else Assembly.from_dict(assembly)
    its = [Item.from_dict(i) if isinstance(i, dict) else i for i in items]
    names = [i.name for i in its]
    if len(set(names)) != len(names):
        raise ValueError("duplicate item names")
    items = {i.name: i for i in its}
    cons = [dict(c) for c in (constraints or [])]
    for c in cons:
        if "type" not in c:
            raise ValueError(f"constraint without type: {c}")
        for k in ("item", "a", "b"):
            if k in c and c[k] not in items:
                raise ValueError(f"constraint {c['type']}: unknown item {c[k]!r}")
    positions = {n: i.position for n, i in items.items() if i.position is not None}
    ext = [n for n, i in items.items() if i.obstructs and i.position is not None]
    if ext:   # positioned external items become box obstacles (self excluded from its own FOV)
        asm = Assembly(list(asm.components) + [_item_body(items[n]) for n in ext], expand_mirror=False)
        for n in ext:
            items[n].fov = [{**f, "ignore": list(f.get("ignore", ())) + ["item:" + n]} for f in items[n].fov]
    to = asm.triangles()
    placement = place(asm, items, cons, positions, to) if place_unpositioned else {}
    results, done = [], {}
    for it in its:
        if positions.get(it.name) is None:
            results.append({"type": "placement", "item": it.name, "ok": False, "margin": None,
                            "detail": placement.get(it.name, {"reason": "no position"})})
            continue
        r = _eval_item_constraints(asm, items, it, positions[it.name], cons, done, tris_owner=to)
        results += r
        done[it.name] = positions[it.name]
    mp = mass_properties(asm, items, positions, base)
    for c in cons:
        if c["type"] == "cg_range" and "cg" in mp:
            i = "xyz".index(c.get("axis", "x"))
            v = mp["cg"][i]
            m = min(v - c.get("min", -math.inf), c.get("max", math.inf) - v)
            results.append({"type": "cg_range", "axis": c.get("axis", "x"), "value": v, "margin": m, "unit": "m",
                            "ok": m >= 0})
        if c["type"] == "max_packing_fraction":
            vol = asm.get(c["body"]).volume()
            iv = sum(items[n].volume_m3() for n in positions
                     if items[n].host == c["body"] or any(k["type"] == "within" and k.get("item") == n
                                                          and k["body"] == c["body"] for k in cons))
            f = iv / vol
            results.append({"type": "max_packing_fraction", "body": c["body"], "value": f,
                            "margin": float(c["max"]) - f, "unit": "fraction", "ok": f <= float(c["max"])})
    packing = {}
    for b in asm.components:
        if isinstance(b, (Body, Surface)):
            inside = [n for n, i in items.items() if positions.get(n) is not None and i.host == b.name]
            if inside:
                iv = sum(items[n].volume_m3() for n in inside)
                packing[b.name] = {"volume_m3": b.volume(), "items": inside, "items_volume_m3": iv,
                                   "fraction": iv / b.volume()}
    pw = {"avg": sum(i.power_w.get("avg", 0.0) for i in its), "peak": sum(i.power_w.get("peak", 0.0) for i in its)}
    missing = [i.name for i in its if not i.power_w] + [i.name for i in its if i.heat_w is None]
    viol = [r for r in results if not r["ok"]]
    return {"ok": not viol, "n_constraints": len(results), "n_violations": len(viol), "violations": viol,
            "constraints": results, "positions": {n: list(p) for n, p in positions.items() if p is not None},
            "placement": placement, "mass_properties": mp, "packing": packing,
            "power_w": pw, "heat_w": sum(i.heat_w or 0.0 for i in its),
            "missing_inputs": sorted(set(missing)) and {"power_w or heat_w not given": sorted(set(missing))},
            "assumptions": ASSUMPTIONS, "method": METHOD,
            "validity": "low fidelity (N1): shape sampling + AABB separation, discrete rays, no multipath / "
                        "radome loss / antenna pattern, no thermal or EMI beyond separation distances"}
