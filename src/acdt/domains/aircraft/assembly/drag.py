"""P1b — CD0 of a generic assembly: Raymer component build-up plus the junction, upsweep, base and protuberance
terms, an uncertainty band (nominal / pessimistic) and per-component calibration factors (hook for N2 CFD).

Methods (published; anything not in a source is marked PRESSUPOSTO in :data:`DRAG_ASSUMPTIONS`):

* Skin friction and form factors — Raymer, *Aircraft Design: A Conceptual Approach*, 6th ed., Eq. 12.24 with
  Cf Eqs. 12.25–12.28, FF Eq. 12.30 (surfaces), 12.31 (bodies), 12.32 (nacelles / pods / stores), on the exposed
  wetted area of the meshes.
* Interference factor Q per junction — Raymer Sec. 12.5.5 ("Component interference factors"): nacelle or store
  mounted directly on the fuselage or wing 1.5, less than about one diameter away 1.3, beyond one diameter 1.0;
  high, mid or well-filleted low wing 1.0, unfilleted low wing 1.1–1.4; fuselage 1.0; tails: V-tail 1.03,
  conventional 1.04–1.05, H-tail 1.08. Hoerner, *Fluid-Dynamic Drag* (1965) Ch. VIII is the background.
* Aft-fuselage upsweep — Raymer Eq. 12.36: (D/q)_upsweep = 3.83·u^2.5·A_max (u in rad).
* Base drag of a blunt aft end, subsonic — Raymer Eq. 12.37: (D/q)_base = [0.139 + 0.419·(M − 0.161)²]·A_base.
* Protuberances (turret, dome, antenna not modelled as parts) — (D/q) = C_D·A_frontal with C_D of the shape from
  Hoerner 1965 Ch. III (sphere 0.47 subcritical; circular cylinder in cross-flow 1.2, 2-D subcritical), or a
  D/q given with its source.
* Leakage and protuberance (L&P) — Raymer Sec. 12.5.10: 5–10 % of parasite drag for propeller aircraft (2–5 %
  jet transports): nominal 5 %, pessimistic 10 %.
"""
from __future__ import annotations

import math
import re

import numpy as np

from .assembly import Assembly
from .components import Body, Disc, Surface

XC_MAX_T_NACA4 = 0.30            # NACA 4-digit: max thickness at 30 % chord (Abbott & von Doenhoff 1959)
CD_SHAPE = {"sphere": (0.47, "Hoerner 1965 Ch. III (esfera, subcrítico)"),
            "cylinder": (1.2, "Hoerner 1965 Ch. III (cilindro circular em escoamento cruzado, 2-D, subcrítico)"),
            "box": (1.05, "Hoerner 1965 Ch. III (cubo com uma face normal ao escoamento)")}

# Per-term relative uncertainty of the nominal value (PRESSUPOSTO: no source gives a band for these terms at
# conceptual level; they are the designer's stated confidence and are overridable in ``drag.uncertainty``).
UNCERTAINTY = {"surface": 0.05, "body": 0.10, "nacelle": 0.10, "upsweep": 0.30, "base": 0.20,
               "protuberance": 0.30, "misc": 0.20}

DRAG_ASSUMPTIONS = [
    "PRESSUPOSTO: a asa é 'baixa' quando o bordo de ataque da raiz fica abaixo de zc − h/4 do corpo principal "
    "nessa estação; sem `drag.wing_fillet: true`, Q da asa baixa = 1,25 nominal (meio da banda 1,1–1,4 de Raymer "
    "Sec. 12.5.5), pessimista 1,4.",
    "PRESSUPOSTO: lanças (booms), radomes e cúpulas são tratados como 'nacelle or external store' de Raymer Sec. "
    "12.5.5 (1,5 / 1,3 / 1,0 pela distância à fuselagem ou asa em diâmetros do próprio corpo); pessimista = "
    "categoria seguinte (1,0 → 1,3 → 1,5).",
    "PRESSUPOSTO: canard e winglets usam Q 1,04 (cauda convencional, Raymer não dá valor próprio); pessimista "
    "1,05 (V 1,03 → 1,05; canard 1,08 como a cauda em H).",
    "PRESSUPOSTO: a base de um corpo com um disco (hélice propulsora) a menos de um diâmetro da base não tem "
    "arrasto de base (o cubo / spinner carena a base).",
    "PRESSUPOSTO: a incerteza relativa por termo (`drag.uncertainty`) é uma confiança declarada, não um valor "
    "de fonte; o CD0 pessimista soma linearmente os extremos (pior caso), o RSS também é reportado.",
    "PRESSUPOSTO: os fatores de calibração (`drag.calibration`, por componente, '*' para todos) multiplicam o "
    "D/q do componente (fricção·FF·Q + upsweep + base); por omissão 1,0 até haver CFD/ensaio (N2).",
    "PRESSUPOSTO: protuberâncias automáticas (`drag.auto_protuberances`, por omissão ligado): a parte da caixa de "
    "um item posicionado que fica fora de todas as peças (amostragem 7×7×7) é uma protuberância com o C_D de "
    "Hoerner 1965 Ch. III em escoamento livre (forma do item: `protuberance_shape` box | sphere | cylinder, "
    "omissão box = cubo 1,05) sobre a área frontal exposta (projeção y–z das colunas com pontos de fora). Não "
    "desconta a imersão na camada limite (conservador).",
]


def _parts(asm: Assembly):
    from .sizing import _parts as p
    return p(asm)


def exposed_and_full(asm: Assembly, fine: int = 2) -> tuple[dict, dict, dict]:
    """Exposed wetted area (triangles inside another non-disc part removed), full wetted area and the
    fraction of each part's area buried in others (junction flag)."""
    from .sizing import exposed_wetted_areas
    exp = exposed_wetted_areas(asm, fine)
    full = {}
    for c in asm.components:
        if isinstance(c, Disc):
            continue
        key = c.name[:-2] if c.mirrored_image else c.name
        full[key] = full.get(key, 0.0) + c.wetted_area()
    return exp, full, {k: 1.0 - exp.get(k, 0.0) / v if v > 0 else 0.0 for k, v in full.items()}


def _main_body(bodies):
    fus = [b for b in bodies if re.search(r"fuselag|fuselage|centerbody|corpo", (b.role or "").lower())]
    pool = fus or bodies
    return max(pool, key=lambda b: b.volume()) if pool else None


def _surface_samples(c, h: float) -> np.ndarray:
    """Points on the mesh triangles of ``c`` with spacing ≤ h (barycentric grid per triangle, capped)."""
    V, F = c.mesh(1)
    out = [V]
    for tri in V[F]:
        e = max(np.linalg.norm(tri[1] - tri[0]), np.linalg.norm(tri[2] - tri[1]), np.linalg.norm(tri[0] - tri[2]))
        m = int(min(max(math.ceil(e / h), 1), 60))
        if m <= 1:
            continue
        i, j = np.meshgrid(np.arange(m + 1), np.arange(m + 1), indexing="ij")
        ok = (i + j) <= m
        a, b = i[ok] / m, j[ok] / m
        out.append(tri[0] + a[:, None] * (tri[1] - tri[0]) + b[:, None] * (tri[2] - tri[0]))
    return np.concatenate(out)


def _min_gap(asm: Assembly, c, targets, h: float = 0.02) -> float:
    """Smallest distance from the mesh of ``c`` to the surface samples of ``targets`` (spacing h)."""
    V = _surface_samples(c, h)
    best = math.inf
    for t in targets:
        if t is c:
            continue
        W = _surface_samples(t, h)
        try:
            from scipy.spatial import cKDTree
            d = float(cKDTree(W).query(V)[0].min())
        except ImportError:                      # scipy is an optional extra: chunked brute force
            d = min(float(np.sqrt(((V[i:i + 256, None, :] - W[None]) ** 2).sum(-1)).min())
                    for i in range(0, len(V), 256))
        best = min(best, d)
    return best


def _store_Q(gap_over_d: float, attached: bool) -> tuple[float, float, str]:
    if attached:
        return 1.5, 1.5, "montado diretamente (Raymer 12.5.5: 1,5)"
    if gap_over_d < 1.0:
        return 1.3, 1.5, f"a {gap_over_d:.2f} diâmetros (< 1: Raymer 12.5.5 1,3)"
    return 1.0, 1.3, f"a {gap_over_d:.2f} diâmetros (> 1: Raymer 12.5.5 1,0)"


def junction_Q(asm: Assembly, opts: dict | None = None, swet: tuple | None = None) -> dict:
    """{component: (Q_nominal, Q_pessimistic, reason)} from the geometry (Raymer Sec. 12.5.5)."""
    o = {"wing_fillet": False, **(opts or {})}
    surfs, bodies, _, geos, kinds = _parts(asm)
    exp, full, buried = swet or exposed_and_full(asm)
    main = _main_body(bodies)
    out = {}
    for s in surfs:
        k = kinds[s.name]
        if k == "wing":
            q = (1.0, 1.0, "asa alta/média ou sem corpo (Raymer 12.5.5: 1,0)")
            if main is not None and buried.get(s.name, 0.0) > 1e-3:
                le = s.to_global([s.sections[0]["le"]])[0]
                xl = float(main.to_local(np.array([le]))[0, 0])
                sec = main._section(np.array([xl]))
                zc = main.origin[2] + float(sec["zc"][0])
                if le[2] < zc - 0.25 * float(sec["h"][0]):
                    q = (1.0, 1.0, "asa baixa com carenagem (Raymer 12.5.5: 1,0)") if o["wing_fillet"] else \
                        (1.25, 1.4, "asa baixa sem carenagem (Raymer 12.5.5: 1,1–1,4; nominal 1,25 PRESSUPOSTO)")
            out[s.name] = q
        elif k == "vee":
            out[s.name] = (1.03, 1.05, "cauda em V (Raymer 12.5.5: 1,03)")
        elif k == "canard":
            out[s.name] = (1.04, 1.08, "canard (PRESSUPOSTO 1,04 como cauda convencional)")
        elif re.search(r"winglet", (s.role or "").lower()):
            out[s.name] = (1.04, 1.05, "winglet (PRESSUPOSTO 1,04 como cauda convencional)")
        else:
            out[s.name] = (1.04, 1.05, "cauda convencional (Raymer 12.5.5: 1,04–1,05)")
    targets = [c for c in asm.components if isinstance(c, Surface) and kinds.get(c.name.removesuffix("~m")) == "wing"]
    if main is not None:
        targets += [c for c in asm.components if isinstance(c, Body) and c.name.removesuffix("~m") == main.name]
    for b in bodies:
        if b is main or re.search(r"fuselag|centerbody", (b.role or "").lower()):
            out[b.name] = (1.0, 1.0, "fuselagem (Raymer 12.5.5: 1,0)")
            continue
        d = max(max(math.sqrt(max(st["w"], 0) * max(st["h"], 0)) for st in b.stations), 1e-6)
        attached = buried.get(b.name, 0.0) > 1e-3 or any(
            float(t.contains(b.mesh(1)[0]).max()) > 0 for t in targets if t is not b)
        gap = 0.0 if attached else _min_gap(asm, b, [t for t in targets if t.name.removesuffix("~m") != b.name],
                                             h=max(d / 8, 1e-3))
        out[b.name] = _store_Q(gap / d, attached)
    return out


def upsweep_Dq(b: Body) -> tuple[float, float]:
    """Raymer Eq. 12.36 on the aft body: u from the max-area station centreline to the tail-end centreline."""
    xs = np.linspace(b.stations[0]["x"], b.stations[-1]["x"], 201)
    A = b.section_area(xs)
    i = int(np.argmax(A))
    # last station of maximum area (constant-section pods: the start of the tail cone)
    i = int(np.nonzero(A >= A[i] * (1 - 1e-9))[0][-1])
    zc = b._section(xs)["zc"]
    dx = xs[-1] - xs[i]
    u = math.atan2(zc[-1] - zc[i], dx) if dx > 0 else 0.0
    if u <= 0:
        return 0.0, 0.0
    return 3.83 * u ** 2.5 * float(A.max()), u


def base_Dq(b: Body, M: float, discs) -> tuple[float, str]:
    """Raymer Eq. 12.37 (subsonic) on the base area of the body; 0 when a disc fairs the base (PRESSUPOSTO)."""
    xe = b.stations[-1]["x"]
    Ab = float(b.section_area(np.array([xe]))[0])
    if Ab <= 1e-9:
        return 0.0, "sem base"
    db = math.sqrt(4 * Ab / math.pi)
    sec = b._section(np.array([xe]))
    pc = b.to_global(np.array([[xe, float(sec["yc"][0]), float(sec["zc"][0])]]))[0]
    for d in discs:
        if float(np.linalg.norm(np.asarray(d.origin, float) - pc)) < max(db, 1e-6) + 1e-9:
            return 0.0, f"base carenada pelo disco {d.name!r} (PRESSUPOSTO)"
    return (0.139 + 0.419 * (M - 0.161) ** 2) * Ab, f"Raymer Eq. 12.37, A_base {Ab:.4f} m²"


def auto_protuberances(asm: Assembly, items, positions: dict | None = None, n: int = 7) -> tuple[list, list]:
    """Protuberances from the equipment items whose box sticks out of the assembly (Hoerner 1965 Ch. III).

    ``items``: item dicts (``size_m``, ``position`` or ``positions[name]``, optional ``protuberance_shape``).
    Returns (protuberance dicts for :func:`protuberance_Dq`, notes). Items without a position are skipped with a
    note (they are placed later by :func:`.integration.place`)."""
    hosts = [c for c in asm.components if not isinstance(c, Disc) and c.role != "item"]
    out, notes = [], []
    for it in items or []:
        if it.get("protuberance", True) is False:
            continue
        pos = (positions or {}).get(it["name"]) if positions else None
        pos = pos if pos is not None else it.get("position")
        L = np.asarray(it.get("size_m") or (0, 0, 0), float)
        if pos is None:
            if L.max() > 0:
                notes.append(f"item {it['name']!r} sem posição: protuberância não avaliada")
            continue
        if L.min() <= 0:
            continue
        g = [np.linspace(-0.5, 0.5, n) * L[k] for k in range(3)]
        X, Y, Z = np.meshgrid(*g, indexing="ij")
        P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1) + np.asarray(pos, float)
        inside = np.zeros(len(P), bool)
        for c in hosts:
            inside |= np.asarray(c.contains(P), float) >= 0.0
        out_m = (~inside).reshape(n, n, n)
        if not out_m.any():
            continue
        cols = out_m.any(axis=0)                       # (y, z) columns with an outside point
        frac = float(cols.mean())
        shape = it.get("protuberance_shape", "box")
        A_box = float(L[1] * L[2])
        if shape == "sphere":
            A = math.pi * float(max(L[1], L[2])) ** 2 / 4
        elif shape == "cylinder":
            A = float(max(L[1], L[2]) * L[0]) if it.get("cylinder_axis", "z") == "z" else A_box
        else:
            A = A_box
        out.append({"name": f"item:{it['name']}", "shape": shape, "frontal_area_m2": A, "exposed_fraction": frac,
                    "auto": True, "component": None})
    return out, notes


def protuberance_Dq(p: dict) -> tuple[float, str]:
    if p.get("D_q_m2") is not None:
        if not p.get("source"):
            return float(p["D_q_m2"]), "D/q dado (PRESSUPOSTO: sem fonte indicada)"
        return float(p["D_q_m2"]), f"D/q dado ({p['source']})"
    shape = p.get("shape", "sphere")
    if shape not in CD_SHAPE:
        raise ValueError(f"protuberance {p.get('name')!r}: shape {shape!r} sem C_D de fonte; use "
                         f"{sorted(CD_SHAPE)} ou D_q_m2 com source")
    cd, src = CD_SHAPE[shape]
    if p.get("frontal_area_m2") is not None:
        A = float(p["frontal_area_m2"])
    elif shape == "sphere":
        A = math.pi * float(p["diameter_m"]) ** 2 / 4
    else:
        A = float(p["diameter_m"]) * float(p["length_m"])
    A *= float(p.get("exposed_fraction", 1.0))
    return cd * A, f"C_D {cd} × {A:.4f} m² ({src})"


def cd0_buildup(asm: Assembly, V: float, rho: float, mu: float, a: float, Sref: float | None = None,
                opts: dict | None = None, swet: tuple | None = None, items=None, positions: dict | None = None) -> dict:
    """Component build-up with junction Q, upsweep, base, protuberances, L&P, uncertainty band and calibration.

    ``opts`` (= spec ``drag``): Q {component: value} (wins over the junction rule), laminar, roughness,
    lp_fraction (nominal, default 0.05) and lp_fraction_pessimistic (0.10), extra_drag_areas_m2, protuberances
    [{name, shape | D_q_m2, diameter_m | frontal_area_m2, length_m?, source?, component?}], wing_fillet,
    auto_Q (True), upsweep (True), base (True), uncertainty {kind: rel}, calibration {component | '*': factor},
    auto_protuberances (True: items of ``items`` sticking out of the parts, :func:`auto_protuberances`).
    """
    from ..aero.drag import ROUGHNESS, ff_body, ff_lifting_surface, ff_nacelle, skin_friction
    o = {"Q": {}, "laminar": {}, "roughness": "smooth_paint", "lp_fraction": 0.05, "lp_fraction_pessimistic": 0.10,
         "extra_drag_areas_m2": {}, "protuberances": [], "auto_Q": True, "upsweep": True, "base": True,
         "uncertainty": {}, "calibration": {}, "auto_protuberances": True, **(opts or {})}
    unc = {**UNCERTAINTY, **(o["uncertainty"] or {})}
    cal = dict(o["calibration"] or {})
    k = ROUGHNESS[o["roughness"]] if isinstance(o["roughness"], str) else float(o["roughness"])
    surfs, bodies, discs, geos, kinds = _parts(asm)
    from .sizing import main_wing
    _, gw = main_wing(asm)
    Sref = Sref or gw["S"]
    sw = swet or exposed_and_full(asm)
    exp = sw[0]
    jq = junction_Q(asm, o, sw) if o["auto_Q"] else {}
    M = V / a
    rows = []

    def qof(name, kind):
        if name in o["Q"]:
            v = float(o["Q"][name])
            return v, v, "dado pelo utilizador"
        if name in jq:
            return jq[name]
        v = 1.0 if kind in ("wing", "body", "nacelle") else 1.04
        return v, v, "valor fixo (auto_Q desligado)"

    for s in surfs:
        g = geos[s.name]
        L = g["mac"]
        lam = float(o["laminar"].get(s.name, 0.10))
        cf = skin_friction(rho * V * L / mu, M, lam, L, k)
        ff = ff_lifting_surface(g["tc_mean"], XC_MAX_T_NACA4, M, g["sweep_maxt"])
        Q, Qp, why = qof(s.name, kinds[s.name])
        f0 = cf * ff * exp[s.name]
        rows.append({"component": s.name, "kind": kinds[s.name], "Swet_m2": exp[s.name], "Cf": cf, "FF": ff,
                     "Q": Q, "Q_pessimistic": Qp, "Q_reason": why, "f_clean_m2": f0, "f_friction_m2": f0 * Q,
                     "upsweep_m2": 0.0, "base_m2": 0.0, "unc": unc["surface"], "f_pess_m2": f0 * Qp * (1 + unc["surface"])})
    for b in bodies:
        L = b.length
        d = max(max(math.sqrt(max(st["w"], 0) * max(st["h"], 0)) for st in b.stations), 1e-6)
        fr = L / d
        nac = bool(re.search(r"nacel|store|pod\b|pylon", (b.role or "").lower()))
        kind = "nacelle" if nac else "body"
        lam = float(o["laminar"].get(b.name, 0.0))
        cf = skin_friction(rho * V * L / mu, M, lam, L, k)
        ff = ff_nacelle(fr) if nac else ff_body(fr)
        Q, Qp, why = qof(b.name, kind)
        n = 2 if b.mirror else 1
        up, u = upsweep_Dq(b) if o["upsweep"] else (0.0, 0.0)
        bs, bwhy = base_Dq(b, M, discs) if o["base"] else (0.0, "desligado")
        up, bs = up * n, bs * n
        f0 = cf * ff * exp[b.name]
        uc = unc[kind]
        rows.append({"component": b.name, "kind": kind, "Swet_m2": exp[b.name], "Cf": cf, "FF": ff, "Q": Q,
                     "Q_pessimistic": Qp, "Q_reason": why, "fineness": fr, "f_clean_m2": f0, "f_friction_m2": f0 * Q,
                     "upsweep_m2": up, "upsweep_deg": math.degrees(u), "base_m2": bs, "base_note": bwhy, "unc": uc,
                     "f_pess_m2": f0 * Qp * (1 + uc) + up * (1 + unc["upsweep"]) + bs * (1 + unc["base"])})
    prot = []
    auto, auto_notes = (auto_protuberances(asm, items, positions) if (o["auto_protuberances"] and items)
                        else ([], []))
    manual = {p.get("name") for p in o["protuberances"] or []}
    for p in list(o["protuberances"] or []) + [p for p in auto if p["name"] not in manual]:
        dq, why = protuberance_Dq(p)
        prot.append({"name": p.get("name", "protuberância"), "D_q_m2": dq, "method": why, "auto": bool(p.get("auto")),
                     "component": p.get("component"), "f_pess_m2": dq * (1 + unc["protuberance"])})
    for r in rows:
        kf = float(cal.get(r["component"], cal.get("*", 1.0)))
        r["calibration"] = kf
        r["f_m2"] = kf * (r["f_friction_m2"] + r["upsweep_m2"] + r["base_m2"])
        r["f_pess_m2"] *= kf
    for p in prot:
        kf = float(cal.get(p["name"], cal.get(p.get("component") or "", cal.get("*", 1.0))))
        p["calibration"] = kf
        p["D_q_m2"] *= kf
        p["f_pess_m2"] *= kf
    dq_misc = float(sum((o["extra_drag_areas_m2"] or {}).values()))
    f_nom = sum(r["f_m2"] for r in rows) + sum(p["D_q_m2"] for p in prot) + dq_misc
    f_pes = sum(r["f_pess_m2"] for r in rows) + sum(p["f_pess_m2"] for p in prot) + dq_misc * (1 + unc["misc"])
    lp, lpp = float(o["lp_fraction"]), float(o["lp_fraction_pessimistic"])
    cd0 = f_nom / Sref * (1 + lp)
    cd0_p = f_pes / Sref * (1 + max(lp, lpp))
    rss = math.sqrt(sum((r["f_pess_m2"] - r["f_m2"]) ** 2 for r in rows)
                    + sum((p["f_pess_m2"] - p["D_q_m2"]) ** 2 for p in prot) + (dq_misc * unc["misc"]) ** 2)
    cd0_rss = (f_nom + rss) / Sref * (1 + max(lp, lpp))
    f_clean = sum(r["f_clean_m2"] for r in rows)
    for r in rows:
        r["CD0"] = r["f_m2"] / Sref
    cd0, cd0_p, cd0_rss = float(cd0), float(cd0_p), float(cd0_rss)
    return {"CD0": cd0, "CD0_nominal": cd0, "CD0_pessimistic": cd0_p, "CD0_rss": cd0_rss,
            "CD0_clean": float(f_clean / Sref) * (1 + lp), "Sref": Sref, "Swet_total": sum(r["Swet_m2"] for r in rows),
            "components": rows, "protuberances": prot, "misc_dq_m2": dq_misc, "lp_fraction": lp,
            "lp_fraction_pessimistic": max(lp, lpp),
            "interference_dq_m2": sum(r["f_friction_m2"] - r["f_clean_m2"] for r in rows),
            "upsweep_dq_m2": sum(r["upsweep_m2"] for r in rows), "base_dq_m2": sum(r["base_m2"] for r in rows),
            "protuberance_dq_m2": sum(p["D_q_m2"] for p in prot), "protuberance_notes": auto_notes,
            "calibration": {r["component"]: r["calibration"] for r in rows if r["calibration"] != 1.0},
            "uncertainty": unc, "assumptions": list(DRAG_ASSUMPTIONS),
            "method": "Raymer Eq. 12.24 (Cf 12.25–12.28, FF 12.30 / 12.31 / 12.32), Q Sec. 12.5.5 por junção, "
                      "upsweep Eq. 12.36, base Eq. 12.37, L&P Sec. 12.5.10, protuberâncias Hoerner 1965 Ch. III; "
                      "área molhada exposta das malhas"}
