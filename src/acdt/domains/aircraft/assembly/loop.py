"""P1b — the generic assembly INSIDE the sizing W0 loop (``acdt size`` with ``assumptions.assembly``).

Each pass of the MDA rescales the drawn assembly to the sized wing area and takes from it the structure masses
(Raymer GA Eqs. 15.46–15.49 per part, :func:`.sizing.structure_weights`) and the zero-lift drag (component
build-up with junction, upsweep, base and protuberance terms, :mod:`.drag`).

Scaling rules (``options.scaling``):

* ``"uniform"`` (default): geometric similarity of the whole drawing about the frame origin with the linear
  factor k = √(S_sized / S_drawn) — every length (stations, chords, spans, origins, disc diameters, item
  positions, range and cg_range constraints, keep-out zones, and the illustrative base CG) × k, so
  proportions and relative placement are kept and the wing area matches exactly. Equipment boxes
  (``size_m``) are NOT scaled (real equipment), separation / cable
  distances are not scaled, and ``mass_kg`` on a part is kept. The aspect ratio is the drawing's.
* ``"surfaces"``: the bodies (fuselage, pods, booms, radomes), discs, items, gear and constraints keep their drawn
  size and place (a payload-driven fuselage, Raymer Sec. 7.2 / 9.1: the fuselage is laid out around the
  payload and crew). The main wing is rescaled about its own origin: span factor k_b and chord factor k_c with
  k_b·k_c = S/S₀ and k_b/k_c = AR/AR₀ (``options.AR`` or the drawing's AR), sweep of the leading edge and
  dihedral kept. Every other lifting surface is rescaled about its origin (uniformly, AR and dihedral kept) to
  keep the drawing's tail volume coefficient (Raymer 6th ed. Eq. 6.28 c_HT = L_HT·S_HT/(c̄_W·S_W) for
  horizontal tails and canards, Eq. 6.29 c_VT = L_VT·S_VT/(b_W·S_W) for fins; V-tails on both projected shares
  S·cos²Γ / S·sin²Γ of Purser & Campbell, NACA Rep. 823, taking the larger requirement), with the arm L from
  the c/4 of the wing MAC to the c/4 of the tail MAC recomputed by a fixed point.

Induced drag (``options.K_source``, default ``"avl"``): K = 1/(π·AR·e) with the Kroo (2001) decomposition
1/(π·AR·e) = 1/(π·AR·e_inv·s) + 0.38·CD0 — e_inv the inviscid span efficiency of AVL (surfaces only, Trefftz
plane), s = 1 − 2(d_f/b)² the fuselage factor of the widest body, 0.38·CD0 the viscous lift-dependent term
(I. Kroo, *Aircraft Design: Synthesis and Analysis*, Stanford, 2001, "Lift-dependent drag"). Without AVL
(or ``K_source: "oswald"``) the polar keeps the classical Oswald factor (Raymer Eq. 12.48/12.49).

Flying-wing shortcuts (``options.flying_wing``, off by default): size tip fins/winglets to a
supplied Raymer Eq. 6.29 ``c_vt`` and/or place a tricycle gear on the mesh
(:mod:`.flying_wing`); omitted drawings stay unchanged.

Balance (``options.balance``, off by default): after the W0 loop closes, the components in ``balance.move``
(default: the main wing) are shifted along x so that the minimum static margin over the loading cases equals
``balance.static_margin`` (Raymer Sec. 16.3: the wing is placed to give the desired margin), with x_np from
:func:`.sizing.neutral_point` (default AVL without bodies + Torenbeek App. E) and the gear re-placed from the
new CG (tip-back, nose-load band); the main / nose gear masses are then put at their legs. Secant iteration.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

from .assembly import Assembly

LOOP_ASSUMPTIONS = [
    "PRESSUPOSTO: semelhança geométrica (k = √(S/S_desenho)) de toda a montagem em cada iteração; caixas de "
    "equipamento, distâncias de separação/cabo e mass_kg dados não escalam.",
    "PRESSUPOSTO: AR, afilamento, flecha c/4 e t/c da asa do tipo fixo passam a ser os da asa principal da "
    "montagem (para que restrições, estabilidade e estruturas usem a mesma asa).",
    "PRESSUPOSTO: com montagem no ciclo, as massas estruturais wing/htail/vtail/fuselage do tipo fixo são "
    "substituídas pelas massas por peça da montagem; trem, sistemas, propulsão e itens ficam do tipo fixo.",
    "PRESSUPOSTO (scaling 'surfaces'): corpos, discos, itens, trem e restrições ficam como desenhados; itens ou "
    "discos montados na asa não acompanham a asa.",
    "PRESSUPOSTO (balance): a massa de cada perna do trem fica a meia altura entre o chão e o CG, na estação da "
    "roda; o deslocamento máximo da peça movida é ±1 CMA por iteração.",
]
TAIL_KINDS = ("htail", "vtail", "vee", "canard")
FIXED_STRUCTURE_KEYS = ("wing", "htail", "vtail", "fuselage")


def load_spec(mission_spec, a: dict) -> dict:
    """``assumptions.assembly`` = inline spec or ``{file: path, ...overrides}`` (path relative to the yaml)."""
    if "file" in a:
        p = Path(a["file"])
        if not p.is_absolute() and getattr(mission_spec, "source", None):
            p = Path(mission_spec.source).parent / p
        return {**json.loads(p.read_text(encoding="utf-8")), **{k: v for k, v in a.items() if k != "file"}}
    return dict(a)


def _s(v, k):
    return [float(x) * k for x in v]


def scale_spec(spec: dict, k: float) -> dict:
    """Copy of an assembly spec with every length × k (see module docstring for what is not scaled)."""
    out = copy.deepcopy(spec)
    for c in out["assembly"]["components"]:
        for key in ("origin", "cg"):
            if c.get(key) is not None:
                c[key] = _s(c[key], k)
        if "pod" in c:
            for key in ("length", "width", "height"):
                if c["pod"].get(key) is not None:
                    c["pod"][key] = float(c["pod"][key]) * k
        if "panel" in c:
            for key in ("root_chord", "tip_chord", "span"):
                if key in c["panel"]:
                    c["panel"][key] = float(c["panel"][key]) * k
        for st in c.get("stations") or []:
            for key in ("x", "w", "h", "zc", "yc"):
                if key in st:
                    st[key] = float(st[key]) * k
        for sec in c.get("sections") or []:
            sec["le"] = _s(sec["le"], k)
            sec["chord"] = float(sec["chord"]) * k
        for key in ("diameter", "thickness", "hub_diameter"):
            if c.get("type") == "disc" and c.get(key) is not None:
                c[key] = float(c[key]) * k
    for it in out.get("items") or []:
        if it.get("position") is not None:
            it["position"] = _s(it["position"], k)
    for m in out.get("masses") or []:
        if m.get("position") is not None:
            m["position"] = _s(m["position"], k)
    base = out.get("base") or {}
    if base.get("cg") is not None:
        base["cg"] = _s(base["cg"], k)
    for cn in out.get("constraints") or []:
        if cn.get("type") in ("range", "cg_range"):
            for key in ("min", "max"):
                if cn.get(key) is not None:
                    cn[key] = float(cn[key]) * k
        z = cn.get("zone") or {}
        if "sphere" in z:
            z["sphere"] = {**z["sphere"], "center": _s(z["sphere"]["center"], k),
                           "radius": float(z["sphere"]["radius"]) * k}
        if "box" in z:
            z["box"] = [_s(v, k) for v in z["box"]]
    g = out.get("gear") or {}
    for key in ("x_main", "x_nose", "ground_z", "half_track"):
        if g.get(key) is not None:
            g[key] = float(g[key]) * k
    for p in (out.get("drag") or {}).get("protuberances") or []:
        for key in ("diameter_m", "length_m"):
            if p.get(key) is not None:
                p[key] = float(p[key]) * k
        if p.get("frontal_area_m2") is not None:
            p["frontal_area_m2"] = float(p["frontal_area_m2"]) * k * k
    return out


def _scale_surface(c: dict, kb: float, kc: float) -> None:
    """In place: span-wise lengths × kb, chords × kc (about the component origin; LE sweep and dihedral kept).

    A surface given by absolute sections has no origin field: the first section stays put and the others move
    relative to it, which is the same rule as a panel scaled about its origin (the tail does not leave its boom).
    """
    if "panel" in c:
        c["panel"]["span"] = float(c["panel"]["span"]) * kb
        for key in ("root_chord", "tip_chord"):
            if key in c["panel"]:
                c["panel"][key] = float(c["panel"][key]) * kc
    secs = c.get("sections") or []
    if secs:
        root = [float(x) for x in secs[0]["le"]]
        for sec in secs:
            le = [float(x) for x in sec["le"]]
            sec["le"] = [root[i] + (le[i] - root[i]) * kb for i in range(3)]
            sec["chord"] = float(sec["chord"]) * kc


def _tail_volume(kind: str, gw: dict, gt: dict) -> tuple[float, float]:
    """(horizontal, vertical) volume coefficient of one tail about the wing (Raymer Eqs. 6.28 / 6.29)."""
    L = abs(gt["x_ac"] - gw["x_ac"])
    g = math.radians(gt["dihedral_deg"])
    if kind in ("htail", "canard"):
        Sh, Sv = gt["S"], 0.0
    elif kind == "vtail":
        Sh, Sv = 0.0, gt["S"]
    else:
        Sh, Sv = gt["S"] * math.cos(g) ** 2, gt["S"] * math.sin(g) ** 2
    return L * Sh / (gw["mac"] * gw["S"]), L * Sv / (gw["b"] * gw["S"])


def scale_spec_surfaces(spec: dict, S: float, AR: float | None = None, shift: tuple | None = None) -> tuple[dict, dict]:
    """``scaling: "surfaces"`` (see module docstring). ``shift`` = (component names, dx): balance shift applied
    after the wing rescale and before the tails are sized (so the tail arm is the balanced one).
    Returns (scaled spec, {k_b, k_c, tails: {name: k_t}})."""
    from .sizing import _parts, main_wing, surface_geometry
    asm0 = Assembly.from_dict(spec["assembly"])
    w0, gw0 = main_wing(asm0)
    surfs, _, _, geos0, kinds = _parts(asm0)
    r = S / gw0["S"]
    q = (AR / gw0["AR"]) if AR else 1.0
    kb, kc = math.sqrt(r * q), math.sqrt(r / q)
    out = copy.deepcopy(spec)
    comps = {c["name"]: c for c in out["assembly"]["components"]}
    _scale_surface(comps[w0.name], kb, kc)
    if shift and shift[1]:
        out = _shift_x(out, shift[0], shift[1])
        comps = {c["name"]: c for c in out["assembly"]["components"]}
    gw = main_wing(Assembly.from_dict(out["assembly"]))[1]
    info = {"k_b": kb, "k_c": kc, "tails": {}, "volume_coefficients": {}}
    for s in surfs:
        kind = kinds[s.name]
        if s.name == w0.name or kind not in TAIL_KINDS:
            continue
        vh0, vv0 = _tail_volume(kind, gw0, geos0[s.name])
        kt = 1.0
        for _ in range(30):
            c = copy.deepcopy(comps[s.name])
            _scale_surface(c, kt, kt)
            gt = surface_geometry(Assembly.from_dict({"components": [c]}).components[0])
            vh, vv = _tail_volume(kind, gw, gt)
            ratio = max(vh0 / vh if vh > 0 else 0.0, vv0 / vv if vv > 0 else 0.0) or 1.0
            kt_new = kt * math.sqrt(ratio)
            if abs(kt_new / kt - 1) < 1e-9:
                break
            kt = kt_new
        _scale_surface(comps[s.name], kt, kt)
        info["tails"][s.name] = kt
        info["volume_coefficients"][s.name] = {"c_H": vh0, "c_V": vv0, "kind": kind}
    return out, info


def _shift_x(spec: dict, names, dx: float) -> dict:
    """Copy of ``spec`` with the components ``names`` (and items / masses hosted on them) moved by dx along x."""
    out = copy.deepcopy(spec)
    names = set(names)
    for c in out["assembly"]["components"]:
        if c["name"] in names:
            o = list(c.get("origin") or [0.0, 0.0, 0.0])
            o[0] = float(o[0]) + dx
            c["origin"] = o
            if c.get("cg") is not None:
                c["cg"] = [float(c["cg"][0]) + dx, *c["cg"][1:]]
    for it in out.get("items") or []:
        if it.get("host") in names and it.get("position") is not None:
            it["position"] = [float(it["position"][0]) + dx, *it["position"][1:]]
    for m in out.get("masses") or []:
        if m.get("component") in names and m.get("position") is not None:
            m["position"] = [float(m["position"][0]) + dx, *m["position"][1:]]
    return out


class AssemblyLoop:
    """State of the assembly inside one MDA run (unscaled drawing, scale per pass, history)."""

    def __init__(self, spec: dict, options: dict | None = None):
        from .sizing import main_wing
        self.spec = spec
        o = {"in_loop": True, "close_on": "nominal", "check_pessimistic": True, "scaling": "uniform", "AR": None,
             "K_source": "avl", "balance": None, **(spec.get("options") or {}), **(options or {})}
        if o["scaling"] not in ("uniform", "surfaces"):
            raise ValueError(f"assembly options.scaling {o['scaling']!r}: uniform | surfaces")
        if o["close_on"] not in ("nominal", "pessimistic"):
            raise ValueError("assembly options.close_on: nominal | pessimistic")
        if o["K_source"] not in ("avl", "oswald"):
            raise ValueError("assembly options.K_source: avl | oswald")
        if o["AR"] is not None and o["scaling"] == "uniform":
            raise ValueError("assembly options.AR só com scaling 'surfaces' (a reescala uniforme mantém o AR do desenho)")
        self.options = o
        self.asm0 = Assembly.from_dict(spec["assembly"])
        w, gw = main_wing(self.asm0)
        self.wing_surface, self.wing0 = w, gw
        self.S0 = gw["S"]
        self.dx_balance = float(o.get("_dx") or 0.0)          # balance shift carried between outer passes
        self.gear_masses: list = list(o.get("_gear_masses") or [])
        self._cache: dict = {}
        self._K: dict = {}
        self.K_notes: list = []
        self.history: list = []

    @classmethod
    def from_mission(cls, mission_spec):
        A = mission_spec.assumptions
        a = A.get("assembly") if isinstance(A, dict) else None
        if not a:
            return None
        spec = load_spec(mission_spec, a)
        from .flying_wing import apply_flying_wing_options
        mf = None
        try:
            req = mission_spec.requirements
            mf = {
                "W0_kg": float(req.value("mtow") or req.value("payload_mass") or 0) or 140.0,
                "payload_kg": float(req.value("payload_mass") or 0) or 20.0,
                "V_m_s": float(req.value("cruise_speed") or 40),
                "altitude_m": float(req.value("cruise_altitude") or 1000),
                "Wf_kg": 25.0,  # PRESSUPOSTO seed for gear stretch only; size() recomputes fuel
            }
            if mf["W0_kg"] < 50:
                mf["W0_kg"] = 140.0
        except Exception:
            mf = None
        spec, fw = apply_flying_wing_options(spec, mission_flight=mf)
        if fw is not None and isinstance(A, dict):
            # Persist the mutated inline drawing (drop file) so outer MDA/balance passes keep it.
            keep = {k: spec[k] for k in ("assembly", "gear", "options", "masses", "material", "flight",
                                         "items", "constraints", "base") if k in spec}
            A["assembly"] = keep
        if not (spec.get("options") or {}).get("in_loop", True):
            return None
        loop = cls(spec)
        loop.flying_wing_report = fw
        return loop

    # ---------------------------------------------------------------- geometry
    @property
    def AR(self) -> float:
        return float(self.options["AR"] or self.wing0["AR"])

    def k(self, S: float) -> float:
        return math.sqrt(S / self.S0)

    def _key(self, S, AR):
        # fine rounding: the MDO partials are relative finite differences of 1e-6 (core.mdo)
        return (round(self.k(S), 12), round(float(AR), 12) if AR else None, round(self.dx_balance, 9),
                len(self.gear_masses))

    def scaled(self, S: float, AR: float | None = None) -> tuple[dict, Assembly]:
        if self.options["scaling"] == "uniform":
            AR = None
        else:
            AR = AR or self.options["AR"]
        key = self._key(S, AR)
        if key not in self._cache:
            if len(self._cache) > 64:
                self._cache.clear()
            if self.options["scaling"] == "uniform":
                sp, info = scale_spec(self.spec, key[0]), {"k": key[0]}
            else:
                sp, info = scale_spec_surfaces(self.spec, S, AR, (self.balance_names(), self.dx_balance))
            if self.dx_balance and self.options["scaling"] == "uniform":
                sp = _shift_x(sp, self.balance_names(), self.dx_balance)
            if self.gear_masses:
                keys = {m["key"] for m in self.gear_masses}
                sp["masses"] = [m for m in sp.get("masses") or [] if m.get("key") not in keys] + \
                    copy.deepcopy(self.gear_masses)
            sp["_scaling"] = info
            self._cache[key] = (sp, Assembly.from_dict(sp["assembly"]))
        return self._cache[key]

    def planform(self) -> dict:
        """Main-wing planform of the drawing for the fixed-type geometry (AR, taper, sweep c/4, t/c)."""
        g = self.wing0
        return {"AR": float(self.AR), "taper": float(g["taper"]),
                "sweep_c4_deg": float(math.degrees(g["sweep_c4"])),
                "tc_root": float(g["tc_root"]), "tc_tip": float(self.wing_surface.sections[-1]["tc"])}

    # ---------------------------------------------------------------- disciplines
    def structure(self, S: float, W0: float, Nz: float, q: float, material: str, Wfw_kg: float = 0.0,
                  AR: float | None = None):
        from .sizing import structure_weights
        sp, asm = self.scaled(S, AR)
        return structure_weights(asm, W0, Nz, q, sp.get("material", material), Wfw_kg)

    def drag(self, S: float, V: float, rho: float, mu: float, a: float, extra: dict | None = None,
             AR: float | None = None) -> dict:
        """CD0 of the scaled drawing; ``extra`` (the mission's aero.extra_drag_areas_m2, e.g. fixed gear) is
        added unless the assembly gives its own ``drag.extra_drag_areas_m2``. Items with a position that stick
        out of the parts add their Hoerner protuberance drag (``drag.auto_protuberances``)."""
        from .sizing import cd0_buildup
        sp, asm = self.scaled(S, AR)
        o = dict(sp.get("drag") or {})
        if "extra_drag_areas_m2" not in o and extra:
            o["extra_drag_areas_m2"] = dict(extra)
        d = cd0_buildup(asm, V, rho, mu, a, opts=o, items=sp.get("items"))
        from . import tailless as _T
        bd = _T.bias_drag(sp, asm) if _T.options(sp) is not None else None
        if bd:   # opt-in split pre-deflection (tailless): cruise profile drag of both splits at δ0
            d = dict(d)
            d["split_bias"] = bd
            if bd.get("dCD0"):
                for k in ("CD0", "CD0_nominal", "CD0_pessimistic"):
                    if d.get(k) is not None:
                        d[k] = d[k] + bd["dCD0"]
        return d

    def cd0(self, d: dict) -> float:
        return d["CD0_pessimistic"] if self.options["close_on"] == "pessimistic" else d["CD0_nominal"]

    def K(self, S: float, mach: float, CD0: float, K_classical: float, AR: float | None = None) -> tuple[float, dict]:
        """Induced-drag factor of the scaled assembly (Kroo 2001 with the AVL e_inv; see module docstring).
        Falls back to ``K_classical`` (Oswald) without AVL or with ``K_source: oswald``."""
        if self.options["K_source"] != "avl":
            return K_classical, {"source": "oswald"}
        from .sizing import _parts, main_wing, run_assembly_avl
        sp, asm = self.scaled(S, AR)
        key = self._key(S, AR if self.options["scaling"] == "surfaces" else None) + (round(mach, 3),)
        if key not in self._K:
            try:
                r = run_assembly_avl(asm, alpha_deg=2.0, mach=mach, with_bodies=False)
                e_inv = float(r["e"])
                if not (0.3 < e_inv <= 1.2):
                    raise RuntimeError(f"e AVL fora da gama física ({e_inv})")
            except Exception as ex:           # ToolNotAvailable / RuntimeError → classical fallback
                self._K[key] = None
                msg = f"K da polar: AVL indisponível ({ex}); Oswald clássico"
                if msg not in self.K_notes:
                    self.K_notes.append(msg)
            else:
                _, gw = main_wing(asm)
                _, bodies, _, _, _ = _parts(asm)
                df = max((max(st["w"] for st in b.stations) for b in bodies if not b.mirror), default=0.0)
                s = 1.0 - 2.0 * (df / gw["b"]) ** 2
                self._K[key] = {"e_inv": e_inv, "s": s, "AR": gw["AR"], "b": gw["b"], "d_f": df}
        info = self._K[key]
        if info is None:
            return K_classical, {"source": "oswald (AVL indisponível)"}
        K = 1.0 / (math.pi * info["AR"] * info["e_inv"] * info["s"]) + 0.38 * CD0
        e = 1.0 / (math.pi * info["AR"] * K)
        return K, {**info, "source": "avl (Kroo 2001)", "K": K, "e": e, "K_classical": K_classical}

    def apply_masses(self, bd, S: float, W0: float, q: float, material: str, AR: float | None = None):
        """Replace the fixed-type structure items of a WeightBreakdown by the per-part assembly masses."""
        from ..weights_detailed import WeightItem
        parts = self.structure(S, W0, bd.Nz, q, material, AR=AR)
        bd.items = [i for i in bd.items if not (i.group == "structure" and i.key in FIXED_STRUCTURE_KEYS)]
        for p in parts:
            bd.items.append(WeightItem("asm:" + p.name, "structure", f"{p.name} ({p.kind}, montagem)", float(p.mass_kg),
                                       p.method + f"; montagem escalada k = {self.k(S):.4f}"))
        return parts

    # ---------------------------------------------------------------- balance (neutral point + gear feedback)
    def balance_names(self) -> list:
        b = self.options.get("balance") or {}
        mv = b.get("move") or [self.wing_surface.name]
        return [mv] if isinstance(mv, str) else list(mv)

    def balance(self, S: float, flight: dict, AR: float | None = None, max_iter: int = 8) -> dict:
        """Shift ``balance.move`` along x until min static margin = ``balance.static_margin`` (secant), with the
        gear re-placed from the CG and the gear masses at their legs. Returns the iteration record; the shift is
        kept (``dx_balance``) so :meth:`scaled` returns the balanced drawing."""
        from .sizing import analyse
        b = {"static_margin": 0.10, "tol": 0.002, "gear_masses": True, **(self.options.get("balance") or {})}
        target = float(b["static_margin"])
        rec = {"target_static_margin": target, "move": self.balance_names(), "iterations": []}

        def eval_at(dx):
            self.dx_balance = dx
            sp, _ = self.scaled(S, AR)
            out = analyse(sp, flight, {"static_margin_min": target})
            sm = min(out.static_margin.values()) if out.static_margin else math.nan
            return out, sm

        x0 = self.dx_balance
        out, sm0 = eval_at(x0)
        mac = out.np.get("mac") or self.wing0["mac"]
        rec["iterations"].append({"dx_m": x0, "SM_min": sm0})
        if not math.isfinite(sm0):
            rec["note"] = out.np.get("note", "sem ponto neutro (AVL indisponível): balanceamento não feito")
            self.dx_balance = x0
            return rec
        # first step: moving the wing by dx moves x_np by about dx and the CG by (m_moved/m)·dx → start with
        # the full error on the wing (secant corrects the CG share)
        x1 = x0 + (target - sm0) * mac
        xa, fa, sm1 = x0, sm0 - target, sm0
        for _ in range(max_iter):
            x1 = max(xa - mac, min(xa + mac, x1))
            out, sm1 = eval_at(x1)
            rec["iterations"].append({"dx_m": x1, "SM_min": sm1})
            fb = sm1 - target
            if abs(fb) < b["tol"]:
                break
            if abs(fb - fa) < 1e-12:
                break
            xa, fa, x1 = x1, fb, x1 - fb * (x1 - xa) / (fb - fa)
        g = out.gear
        # Both legs, or neither. A nose that could not be placed (Raymer band empty) must not leave only the
        # main-gear mass on the tip-back ray: that shifts the CG with a gear the aeroplane does not have.
        both = g.get("x_nose") is not None and g.get("x_main") is not None
        if b["gear_masses"] and both and g.get("ground_z") is not None and g.get("h_cg") is not None:
            z = g["ground_z"] + 0.5 * g["h_cg"]
            st = {"main_gear": g.get("x_main"), "nose_gear": g.get("x_nose")}
            ms = [m for m in flight.get("other_masses") or [] if st.get(m.get("key")) is not None]
            self.gear_masses = [{"name": m["name"], "key": m["key"], "group": "structure", "mass_kg": m["mass_kg"],
                                 "position": [float(st[m["key"]]), 0.0, float(z)]} for m in ms]
            if self.gear_masses:
                out, sm1 = eval_at(self.dx_balance)
                rec["iterations"].append({"dx_m": self.dx_balance, "SM_min": sm1, "gear_masses_at_legs": True})
        elif b["gear_masses"]:
            self.gear_masses = []
            rec["gear_note"] = ("trem incompleto: as massas do nariz e do principal ficam no centróide até as duas "
                                "estações existirem (Raymer Ch. 11)")
        # The secant stops at |SM − target| < tol, so it can finish just below the target. The published
        # check is SM >= static_margin_min (the same number). Step until the margin is on or above it.
        for _ in range(4):
            if not math.isfinite(sm1) or sm1 + 1e-9 >= target:
                break
            # Aim a tenth of a percent above the floor: the CG moves with the wing, so one
            # linear step can finish just under the check (smin >= static_margin_min).
            step = max(-mac, min(mac, (target + 1e-3 - sm1) * mac))
            out, sm1 = eval_at(self.dx_balance + step)
            rec["iterations"].append({"dx_m": self.dx_balance, "SM_min": sm1, "raised_to_target": True})
        rec.update({"dx_m": self.dx_balance, "SM_min": sm1, "converged": bool(abs(sm1 - target) < b["tol"] * 2.5),
                    "x_np": out.np.get("x_np"), "gear": {k: v for k, v in out.gear.items() if k != "checks"},
                    "checks": [{"key": k, "ok": ok, "message": m} for k, ok, m in out.checks
                               if k == "asm:static_margin" or k.startswith("asm:gear")]})
        return rec
