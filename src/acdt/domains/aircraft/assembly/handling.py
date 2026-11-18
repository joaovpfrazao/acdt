"""Handling qualities and landing-gear checks read from the generic assembly (P1b follow-up).

With ``assumptions.assembly`` the drawn aircraft is the assembly, not the fixed-type Configuration (wing +
fuselage + htail + vtail from c_ht / c_vt). Until now ``hq:*`` and ``gear:*`` read only the fixed type, so a
flying wing's winglets or a twin boom's placed gear never reached them. This module re-evaluates them on the
assembly as sized and balanced in the W0 loop and replaces the fixed-type rows (same keys, same limits):

* Lateral-directional and rate derivatives — AVL 3.x (Drela & Youngren) of the whole assembly without bodies
  (the same AVL model as the default ``np_source``), at the cruise CL of W0 about the full-load CG of the
  assembly: CYβ, Clβ, Cnβ, CYp, Clp, Cnp, CYr, Clr, Cnr, Cmq, CLα. Every axis-aligned body adds the Raymer
  (2018) Eq. 16.47 fuselage term Cnβ = −1.3·Vol/(S·b)·(D/W), with the volume of its closed mesh.
* Cmα = −CLα·SM with SM = (x_np − x_cg)/c̄ of the assembly (x_np from ``neutral_point``), Cmα̇ from every
  horizontal / V tail aft of the CG, −2·η·V̄_h·CLα_h·(l_t/c̄)·dε/dα (Nelson 1998 Eq. 4.?; Etkin & Reid 1996),
  horizontal share S·cos²Γ (Purser & Campbell 1945, NACA Rep. 823), dε/dα = 2·CLα_w/(π·AR) (Raymer Eq. 16.13
  far-field). CLα_h by the DATCOM/Helmbold slope (Raymer Eq. 12.6).
* Inertias — component summation (Roskam, Airplane Design Part V, Ch. 10) about the full-load CG: every
  structural part spread over its own mesh surface (area-weighted, the chord-proportional spanwise rule of
  Roskam for a surface), every listed or placed mass as a point mass with its x, y and z offsets.
* Modes and levels — :func:`..stability.longitudinal_matrix`, :func:`..stability.lateral_matrix`,
  :func:`..stability.handling_qualities` (MIL-F-8785C, Class I). No limit is changed.
* Gear — the gear the assembly places (tricycle / taildragger / ski) (``gear_layout``: 15° tip-back ray from the aft CG, 8–15 % nose-load
  band, Raymer 2018 Ch. 11; rotation to the first mesh vertex aft of the main wheels; overturn ≤ 63°) feeds
  ``gear:position``, ``gear:tipback``, ``gear:nose_load``, ``gear:overturn`` and ``gear:rotation``. ``gear:stroke``
  (14 CFR 23.473 / 23.725) stays from :mod:`..landing_gear`. A drawing with ``gear: {type: none}`` leaves the
  fixed-type ``gear:*`` as they were, with a note.

``hq:scissor`` stays on the fixed type: the scissor plot is written for one horizontal tail (Torenbeek Ch. 9).
``assumptions.assembly.options.checks_from: fixed_type`` keeps the old behaviour.
"""
from __future__ import annotations

import math

import numpy as np

from .assembly import Assembly
from .components import Body
from .sizing import _parts, main_wing, run_assembly_avl

ASSUMPTIONS = [
    "PRESSUPOSTO: os modos da montagem usam o AVL sem corpos (o mesmo do np_source por omissão) mais a Eq. 16.47 "
    "de Raymer por corpo; sem deflexão de comando (o AVL da montagem não tem superfícies de comando), em α para "
    "o CL de cruzeiro de W0.",
    "PRESSUPOSTO: CG e inércias no caso «cheio» da montagem; a massa estrutural espalhada na superfície da "
    "malha de cada peça (casca), as massas listadas como pontos; Ixz desprezado (eixos de estabilidade ≈ corpo). "
    "Massa e inércias multiplicadas por W0/m_cheio quando as massas por peça não fecham com W0.",
    "PRESSUPOSTO: Cmα̇ só das caudas horizontais e em V atrás do CG (parcela S·cos²Γ); asa sem cauda → 0 "
    "(contribuição α̇ da própria asa desprezada, Etkin & Reid 1996 Sec. 5.5).",
    "PRESSUPOSTO: η_h = 0,9 (o mesmo ETA_H do tipo fixo).",
]

GEAR_KEYS = ("gear:position", "gear:tipback", "gear:nose_load", "gear:overturn", "gear:rotation")


# ------------------------------------------------------------------------------------------- inertia
def _shell(comp, fine: int = 2):
    """Triangle centroids and areas of a closed component mesh."""
    V, F = comp.mesh(fine)
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    return (a + b + c) / 3.0, 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)


def inertias(asm: Assembly, out, case: str = "cheio") -> dict:
    """Ixx, Iyy, Izz [kg·m²] of the assembly at a loading case (component summation, Roskam Part V Ch. 10)."""
    ld = out.loading["cases"][case]
    cg = np.asarray(ld["cg"], float)
    m_tot = float(ld["mass_kg"])
    Ixx = Iyy = Izz = 0.0
    m_spread = 0.0
    for p in out.structure:
        comps = [asm.get(p.name)]
        try:
            comps.append(asm.get(p.name + "~m"))
        except (KeyError, ValueError):
            pass
        P, A = zip(*(_shell(c) for c in comps))
        P, A = np.concatenate(P), np.concatenate(A)
        w = p.mass_kg * A / A.sum()
        # the shell about its own area centroid, then moved to the part CG (parallel axes)
        d = P - (A[:, None] * P).sum(axis=0) / A.sum() + (np.asarray(p.cg, float) - cg)
        Ixx += float((w * (d[:, 1] ** 2 + d[:, 2] ** 2)).sum())
        Iyy += float((w * (d[:, 0] ** 2 + d[:, 2] ** 2)).sum())
        Izz += float((w * (d[:, 0] ** 2 + d[:, 1] ** 2)).sum())
        m_spread += p.mass_kg
    m_point = 0.0
    names = {p.name for p in out.structure}
    rows = out.loading.get("rows", {}).get(case) if isinstance(out.loading.get("rows"), dict) else None
    for nm, m, r in rows or []:
        if nm in names:
            continue
        d = np.asarray(r, float) - cg
        Ixx += m * (d[1] ** 2 + d[2] ** 2)
        Iyy += m * (d[0] ** 2 + d[2] ** 2)
        Izz += m * (d[0] ** 2 + d[1] ** 2)
        m_point += m
    return {"m": m_tot, "x_cg": float(cg[0]), "z_cg": float(cg[2]), "Ixx": Ixx, "Iyy": Iyy, "Izz": Izz,
            "m_structure_spread": m_spread, "m_point": m_point}


# ------------------------------------------------------------------------------------------- derivatives
def body_cnb(asm: Assembly, S: float, b: float) -> tuple[float, dict]:
    """Σ Raymer Eq. 16.47 over the axis-aligned bodies: Cnβ = −1.3·Vol/(S·b)·(D_f/W_f) [1/rad]."""
    _, bodies, _, _, _ = _parts(asm)
    tot, per = 0.0, {}
    for bd in bodies:
        n = 2 if bd.mirror else 1
        D = max(s["h"] for s in bd.stations)
        W = max(s["w"] for s in bd.stations)
        c = -1.3 * n * abs(bd.volume()) / (S * b) * (D / W if W > 0 else 1.0)
        per[bd.name] = c
        tot += c
    return tot, per


def vertical_volume(asm: Assembly, x_ref: float) -> float:
    """Measured vertical-tail volume Σ S·|sin Γ|·l_v/(S_w·b) (Raymer Eq. 6.29 with the projected side area)."""
    surfs, _, _, geos, kinds = _parts(asm)
    _, gw = main_wing(asm)
    v = 0.0
    for s in surfs:
        if kinds[s.name] in ("vtail", "vee"):
            g = geos[s.name]
            v += g["S"] * abs(math.sin(math.radians(g["dihedral_deg"]))) * (g["x_ac"] - x_ref)
    return v / (gw["S"] * gw["b"])


def _cmad(asm: Assembly, x_cg: float, CLa_w: float, mach: float) -> tuple[float, list]:
    from ..aero.lift import lift_curve_slope
    from ..stability import ETA_H
    surfs, _, _, geos, kinds = _parts(asm)
    _, gw = main_wing(asm)
    deps = 2 * CLa_w / (math.pi * gw["AR"])
    tot, used = 0.0, []
    for s in surfs:
        k = kinds[s.name]
        if k not in ("htail", "vee"):
            continue
        g = geos[s.name]
        lt = g["x_ac"] - x_cg
        if lt <= 0:
            continue
        Sh = g["S"] * math.cos(math.radians(abs(g["dihedral_deg"]))) ** 2
        Vh = Sh * lt / (gw["S"] * gw["mac"])
        CLa_h = lift_curve_slope(g["AR"], mach, g["sweep_maxt"])
        tot += -2 * ETA_H * Vh * CLa_h * (lt / gw["mac"]) * deps
        used.append(s.name)
    return tot, used


def dynamics(res, spec: dict, out, opts: dict | None = None) -> dict:
    """Modes of the assembly about trimmed-CL level cruise, in the shape :func:`..stability.dynamic_modes` returns.
    ``opts.hq_case`` picks the loading case of the assembly (default «cheio», the MTOW case of the fixed type)."""
    from acdt import G0
    from acdt.core.atmosphere import isa
    from ..aero.lift import lift_curve_slope
    from ..stability import _modes_lat, _modes_long, lateral_matrix, longitudinal_matrix
    asm = Assembly.from_dict(spec["assembly"])
    _, gw = main_wing(asm)
    at = isa(res.cruise_altitude)
    u0 = float(res.cruise_speed)
    mach = u0 / at.a
    S, b, c = gw["S"], gw["b"], gw["mac"]
    qS = 0.5 * at.rho * u0**2 * S
    case = (opts or {}).get("hq_case", "cheio")
    I = inertias(asm, out, case)
    # per-part masses that do not close on W0 are scaled so the full case weighs W0 (PRESSUPOSTO)
    m_full = float(out.loading["cases"]["cheio"]["mass_kg"])
    k_m = float(res.sizing.W0) / m_full if m_full > 0 else 1.0
    m = I["m"] * k_m
    for key in ("Ixx", "Iyy", "Izz"):
        I[key] *= k_m
    I["scale_W0_over_assembly"] = k_m
    CL = m * G0 / qS
    CD = res.polar.CD0 + res.polar.K * CL**2
    x_cg, z_cg = I["x_cg"], I["z_cg"]
    avl = run_assembly_avl(asm, mach=mach, x_ref=x_cg, z_ref=z_cg, with_bodies=False, CL=CL)
    cnb_b, cnb_per = body_cnb(asm, S, b)
    d = {k: float(avl.get(k, 0.0) or 0.0) for k in ("CYb", "CYp", "CYr", "Clb", "Clp", "Clr", "Cnb", "Cnp", "Cnr")}
    Cnb_avl = d["Cnb"]
    d["Cnb"] = Cnb_avl + cnb_b
    CLa = float(avl["CLa"])
    x_np = out.np.get("x_np")
    SM = (x_np - x_cg) / c if x_np is not None else float(-avl["Cma"] / CLa)
    Cma = -CLa * SM
    CLa_w = lift_curve_slope(gw["AR"], mach, gw["sweep_maxt"])
    Cmad, tails = _cmad(asm, x_cg, CLa_w, mach)
    Cmq = float(avl.get("Cmq", 0.0) or 0.0)
    kprop = 3.0 if res.spec.propulsion_kind in ("electric", "piston", "turboprop") else 2.0
    Alon = longitudinal_matrix(CL, CD, res.polar.K, CLa, Cma, Cmad, Cmq, kprop, qS, c, m, I["Iyy"], u0)
    Alat = lateral_matrix(d, qS, b, m, I["Ixx"], I["Izz"], u0)
    c_vt = vertical_volume(asm, gw["x_ac"])
    I_out = {"m": m, "x_cg": x_cg, "z_cg": z_cg, "Ixx": I["Ixx"], "Iyy": I["Iyy"], "Izz": I["Izz"],
             "m_assembly": I["m"], "scale_W0_over_assembly": k_m, "case": case}
    return {"longitudinal": _modes_long(Alon, u0, qS, CLa, m, I_out), "lateral": _modes_lat(Alat),
            "inertia": I_out, "source": "montagem (AVL sem corpos)",
            "derivatives": {"CLa": CLa, "Cma": Cma, "Cmad": Cmad, "Cmq": Cmq, "CL": CL, "CD": CD, "SM": SM,
                            "Cnb_avl": Cnb_avl, "Cnb_bodies": cnb_b, "Cnb_bodies_per": cnb_per, "Cnb_total": d["Cnb"],
                            "Clb": d["Clb"], "Clp": d["Clp"], "Cnr": d["Cnr"], "CYb": d["CYb"],
                            "alpha_deg": avl.get("alpha_deg"), "c_vt_measured": c_vt, "tails_cmad": tails},
            "A_lon": Alon, "A_lat": Alat, "u0": u0,
            "notes": [f"modos da montagem: AVL sem corpos no CL de cruzeiro {CL:.3f} (α {avl.get('alpha_deg', 0):.2f}°) "
                      f"em torno do CG «{case}» x = {x_cg:.3f} m; Cnβ AVL {Cnb_avl:+.4f} + corpos (Raymer 16.47) "
                      f"{cnb_b:+.4f} = {d['Cnb']:+.4f}/rad",
                      f"volume vertical medido na montagem {c_vt:.3f} (Raymer Eq. 6.29, área projetada S·sin Γ, braço ao CA da asa)",
                      f"Cmα = −CLα·SM com SM {SM:.1%} (x_np da montagem); Cmα̇ de {tails or 'nenhuma cauda'}",
                      "inércias por soma de componentes na montagem (Roskam Parte V Cap. 10), casca por peça"]
                     + list(ASSUMPTIONS)}


# ------------------------------------------------------------------------------------------- gear

def _gear_rows_taildragger(g: dict, overturn_max: float = 63.0) -> list:
    """Taildragger ``gear:*`` from assembly layout (Raymer Cap. 11; 14 CFR 23.925 9 in)."""
    rows = []
    if g.get("status") == "unassessed":
        msg = (g.get("checks") or [[None, None, "taildragger unassessed"]])[0][2]
        return [("gear:position", None, f"montagem: {msg}")]
    xm, xt = g.get("x_main"), g.get("x_tail")
    tip = g.get("tipback_deg")
    tip_min = float(g.get("tipback_min_deg", 15.0))
    rows.append(("gear:position", xm is not None and xt is not None and xm < xt,
                 f"montagem: principal x = {xm:.3f} m, cauda x = {xt:.3f} m, h_cg {g.get('h_cg', float('nan')):.3f} m"
                 if xm is not None and xt is not None else "montagem: taildragger sem estações"))
    rows.append(("gear:tipback", bool(tip is not None and tip + 0.05 >= tip_min),
                 f"montagem: ângulo de nariz {tip:.1f}° no CG dianteiro (mínimo {tip_min:.0f}°, Raymer Cap. 11)"))
    # nose_load is tricycle-only — leave unassessed rather than inventing a band pass
    tf = g.get("tail_fraction")
    if tf is not None:
        rows.append(("gear:nose_load", None,
                     f"montagem: fração na roda de cauda {100 * tf[0]:.1f}–{100 * tf[1]:.1f} % "
                     f"(reportada; banda 8–15 % é só triciclo, Raymer Cap. 11)"))
    else:
        rows.append(("gear:nose_load", None, "montagem: carga na cauda não calculada"))
    if g.get("overturn_deg") is not None:
        ov = g["overturn_deg"]
        rows.append(("gear:overturn", bool(ov <= overturn_max + 1e-6),
                     f"montagem: capotagem {ov:.1f}° (máximo {overturn_max:.0f}°, Raymer Cap. 11)"))
    else:
        tmin = g.get("half_track_min")
        ok = tmin is not None and __import__("math").isfinite(tmin)
        rows.append(("gear:overturn", bool(ok),
                     f"montagem: bitola mínima {2 * tmin:.3f} m para {overturn_max:.0f}° (Raymer Cap. 11)"
                     if ok else "montagem: capotagem sem solução"))
    rows.append(("gear:rotation", None,
                 "montagem: folga de rotação (tail-strike) é critério de triciclo; "
                 "taildragger sentado em três pontos — ver asm:gear_prop_clearance (14 CFR 23.925 9 in)"))
    return rows


def _gear_rows_ski(g: dict, overturn_max: float = 63.0) -> list:
    """Ski ``gear:*`` from assembly layout."""
    if g.get("status") == "unassessed":
        msg = (g.get("checks") or [[None, None, "ski unassessed"]])[0][2]
        return [("gear:position", None, f"montagem: {msg}")]
    by = {c[0]: c for c in (g.get("checks") or [])}
    rows = []
    for key, gkey in (("gear:position", "asm:gear_position"), ("gear:tipback", "asm:gear_tipback"),
                      ("gear:overturn", "asm:gear_overturn")):
        if gkey in by:
            rows.append((key, by[gkey][1], f"montagem: {by[gkey][2]}"))
        else:
            rows.append((key, None, f"montagem: {key} unassessed"))
    rows.append(("gear:nose_load", None,
                 "montagem: banda 8–15 % é só triciclo; esqui reporta contacto fore/aft (Raymer Cap. 11)"))
    rows.append(("gear:rotation", None,
                 "montagem: rotação/tail-strike triciclo não aplica ao esqui; ver folga hélice/ventre"))
    return rows


def gear_rows(g: dict, nose_band=(0.08, 0.15), overturn_max: float = 63.0, rotation_min: float = 10.0) -> list:
    """``gear:*`` rows from the assembly's placed gear (:func:`.sizing.gear_layout`)."""
    kind = (g.get("type") or "tricycle")
    if kind in ("taildragger", "conventional", "tailwheel"):
        return _gear_rows_taildragger(g, overturn_max)
    if kind in ("ski", "skis"):
        return _gear_rows_ski(g, overturn_max)
    if g.get("status") == "unassessed":
        return [("gear:position", None, f"montagem: {g.get('note') or 'trem unassessed'}")]
    lo, hi = nose_band
    rows = []
    xn, xm = g.get("x_nose"), g.get("x_main")
    tip = g.get("tipback_deg")
    tip_min = float(g.get("tipback_min_deg", 15.0))
    if xn is None:
        rows.append(("gear:position", False, f"montagem: sem entre-eixos na banda {lo:.0%}–{hi:.0%} com o nariz "
                                             f"dentro do corpo (principal x = {xm:.3f} m; Raymer Cap. 11)"))
        rows.append(("gear:tipback", bool(tip is not None and tip + 0.05 >= tip_min),
                     f"montagem: tombo {tip:.1f}° no CG traseiro (mínimo {tip_min:.0f}°, Raymer Cap. 11)"))
        rows.append(("gear:nose_load", False, "montagem: sem posição de nariz"))
        rows.append(("gear:overturn", False, "montagem: sem posição de nariz"))
    else:
        rows.append(("gear:position", xn < xm, f"montagem: nariz x = {xn:.3f} m, principal x = {xm:.3f} m, "
                                              f"entre-eixos {xm - xn:.3f} m, h_cg {g['h_cg']:.3f} m"))
        rows.append(("gear:tipback", bool(tip + 0.05 >= tip_min),
                     f"montagem: tombo {tip:.1f}° no CG traseiro (mínimo {tip_min:.0f}°, Raymer Cap. 11)"))
        fa, ff = g["nose_fraction"]
        ok = lo - 1e-3 <= min(fa, ff) and max(fa, ff) <= hi + 1e-3
        rows.append(("gear:nose_load", bool(ok), f"montagem: fração na roda de nariz {fa:.1%} (CG traseiro) … "
                                                 f"{ff:.1%} (CG dianteiro); banda {lo:.0%}–{hi:.0%} (Raymer Cap. 11)"))
        if g.get("overturn_deg") is not None:
            ov = g["overturn_deg"]
            rows.append(("gear:overturn", bool(ov <= overturn_max + 1e-6),
                         f"montagem: capotagem {ov:.1f}° (máximo {overturn_max:.0f}°, Raymer Cap. 11)"))
        else:
            t = g.get("half_track_min")
            ok = t is not None and math.isfinite(t)
            rows.append(("gear:overturn", bool(ok), f"montagem: bitola mínima {2 * t:.3f} m para {overturn_max:.0f}° "
                                                    "(Raymer Cap. 11)" if ok else "montagem: capotagem sem solução"))
    rot = g.get("rotation_deg")
    if rot is not None:
        rows.append(("gear:rotation", bool(rot + 1e-6 >= rotation_min),
                     f"montagem: rotação até tocar {rot:.1f}° (mínimo {rotation_min:.0f}°, Raymer Cap. 11 10–15°); "
                     f"primeiro ponto {g.get('rotation_first_contact')}"))
    return rows


# ------------------------------------------------------------------------------------------- pipeline hook
def _replace(checks, rows, keys, make):
    """Replace (or append) the rows whose key is in ``keys``; returns the replaced originals."""
    old = [c for c in checks if (c.key if hasattr(c, "key") else c[0]) in keys]
    keep = [c for c in checks if (c.key if hasattr(c, "key") else c[0]) not in keys]
    checks[:] = keep + [make(*r) for r in rows]
    return old


def apply(res, spec: dict, out) -> dict:
    """Swap the fixed-type ``hq:*`` (not the scissor) and ``gear:*`` rows for the assembly ones. Returns a record
    {hq: ..., gear: ..., fixed_type: {checks}} stored in ``res.assembly['checks_from_assembly']``."""
    from acdt.core.requirements import Issue
    from ..sizing import CheckResult
    from ..systems_integration import is_uas
    from ..stability import handling_qualities
    o = spec.get("options") or {}
    rec = {"hq": None, "gear": None, "fixed_type": {}}
    if o.get("checks_from", "assembly") != "assembly":
        rec["note"] = "checks_from: fixed_type — hq:* e gear:* do tipo fixo"
        return rec
    area = next((c for c in out.checks if c[0] == "asm:wing_area"), None)
    if area is not None and not area[1]:
        # drawn wing ≠ sized wing (in_loop: false): the drawing is not the sized aeroplane
        rec["note"] = "asm:wing_area falha: a montagem não é a asa dimensionada; hq:* e gear:* ficam do tipo fixo"
        res.issues.append(Issue("info", rec["note"]))
        return rec
    dy = getattr(res, "dynamics", None)
    if isinstance(dy, dict) and dy.get("modes") is not None:
        try:
            md = dynamics(res, spec, out, o)
            cat, lreq = dy.get("hq_category", "B"), int(dy.get("hq_required_level", 1))
            hq = handling_qualities(md, cat)
            uav = is_uas(res.spec)
            # Tailless with split ailerons (opt-in): bare airframe + SAS through the split ailerons
            tl, hq_sas, auth_ok = None, None, None
            from . import tailless as _tl
            if _tl.options(spec) is not None:
                try:
                    tl = _tl.evaluate(res, spec, md, uav)
                except Exception as ex:
                    tl = {"schema": "tailless_split_aileron", "error": str(ex)}
                    res.issues.append(Issue("warning", f"Asa voadora sem deriva (split ailerons) falhou: {ex}"))
                for msg_tl in (tl or {}).get("issues") or []:
                    res.issues.append(Issue("warning", f"split ailerons: {msg_tl}"))
                sas = (tl or {}).get("sas") or {}
                if (tl or {}).get("sas_enabled") and sas.get("status") == "ok":
                    hq_sas = {r["key"]: r for r in handling_qualities(
                        {**md, "lateral": _tl._modes_lat_closed(sas["A_lat_cruise"])}, cat)}
                    auth_ok = ((tl.get("authority") or {}).get("ok"))
            _A = getattr(getattr(res, "spec", None), "assumptions", None)
            geo = (_A.get("geometry") if isinstance(_A, dict) else None) or {}
            dih_declared = geo.get("dihedral_deg") is not None
            # Only force spiral unassessed when the mission geometry block is present
            # (real MissionSpec). Stub DesignResults in unit tests have no assumptions.
            require_explicit_dihedral = isinstance(_A, dict) and "geometry" in _A
            # Wing dihedral from the drawn assembly (largest surface), else geometry assumption.
            wing_dih = None
            try:
                from .sizing import main_wing as _mw
                wing_dih = float(_mw(Assembly.from_dict(spec["assembly"]))[1]["dihedral_deg"])
            except Exception:
                wing_dih = float(geo["dihedral_deg"]) if dih_declared else 3.0
            rows = []
            for r in hq:
                v = r["valor"]
                vs = f"{v:.3g}" if isinstance(v, float) else str(v)
                ok = r["nível"] <= lreq
                extra = ""
                if r["key"] == "spiral":
                    extra = (f"; Clβ via AVL montagem com Γ_asa≈{wing_dih:g}° "
                             "(Etkin & Reid / Nelson)")
                    if (not dih_declared) and require_explicit_dihedral:
                        ok = None
                        rows.append(("hq:spiral", None,
                                     f"montagem: espiral unassessed: declare assumptions.geometry.dihedral_deg "
                                     f"(Γ_asa desenho≈{wing_dih:g}°; Clβ/espiral — Etkin & Reid 1996 Ch. 6 / "
                                     "MIL-F-8785C Table VIII)"))
                        continue
                msg = (f"montagem: {r['modo']} = {vs} → Nível {r['nível'] if r['nível'] < 4 else '>3'} "
                       f"(N1: {r['limite N1']}; {r['ref']}, Classe I, Cat. {cat})"
                       + extra + (" — UAV: indicativo" if uav else ""))
                if tl is not None and r["key"] in ("dutch_roll", "spiral", "roll"):
                    ok, msg = _tl.hq_row(r, ok, msg, hq_sas, auth_ok, lreq, tl)
                rows.append(("hq:" + r["key"], ok, msg))
            if tl is not None:
                rows += _tl.extra_rows(tl)
            keys = {"hq:" + r["key"] for r in (dy.get("hq") or [])} | {r[0] for r in rows}
            # Preserve ok=None (unassessed); do not coerce with bool().
            old = _replace(res.checks, rows, keys, lambda k, ok, msg: CheckResult(k, ok, msg))
            rec["fixed_type"]["hq"] = [(c.key, c.ok, c.message) for c in old]
            dy["fixed_type"] = {"modes": dy.get("modes"), "hq": dy.get("hq")}
            dy["modes"], dy["hq"], dy["source"] = md, hq, "assembly"
            rec["hq"] = {"derivatives": md["derivatives"], "inertia": md["inertia"]}
            if tl is not None:
                dy["tailless"] = rec["tailless"] = tl
                if hq_sas:
                    dy["hq_sas"] = list(hq_sas.values())
        except Exception as ex:
            res.issues.append(Issue("warning", f"Modos da montagem falharam; hq:* ficam do tipo fixo: {ex}"))
    lg = getattr(res, "landing_gear", None)
    g = out.gear or {}
    gtype = g.get("type")
    asm_kinds = {"tricycle", "taildragger", "conventional", "tailwheel", "ski", "skis"}
    # Map fixed-type kind aliases to assembly types
    lg_kind = (lg.kind if lg is not None else None)
    lg_aliases = {"taildragger": asm_kinds, "tricycle": {"tricycle"}, "ski": {"ski", "skis"},
                  "conventional": asm_kinds, "tailwheel": asm_kinds}
    match = lg is not None and gtype in asm_kinds and (
        (lg_kind == "tricycle" and gtype == "tricycle")
        or (lg_kind in ("taildragger", "conventional", "tailwheel") and gtype in ("taildragger", "conventional", "tailwheel"))
        or (lg_kind in ("ski", "skis") and gtype in ("ski", "skis"))
        or (lg_kind == gtype)
    )
    if match:
        gopt = spec.get("gear") or {}
        band = tuple(gopt.get("nose_fraction", (0.08, 0.15)))
        g = {**g, "tipback_min_deg": float(gopt.get("tipback_deg", 15.0))}
        rows = gear_rows(g, band, float(gopt.get("overturn_max_deg", 63.0)), float(gopt.get("rotation_min_deg", 10.0)))
        keys = set(GEAR_KEYS)
        def _cr(k, ok, msg):
            return CheckResult(k, ok, msg)  # preserve None = unassessed
        old = _replace(res.checks, rows, keys, _cr)
        rec["fixed_type"]["gear"] = [(c.key, c.ok, c.message) for c in old]
        _replace(lg.checks, rows, keys, lambda k, ok, msg: (k, ok, msg))
        geom = [ok for key, ok, _ in lg.checks if key != "gear:stroke" and ok is not None]
        lg.geometry_ok = (bool(geom) and all(geom)) if geom else None
        lg.tipback_deg = g.get("tipback_deg")
        lg.overturn_deg = g.get("overturn_deg")
        lg.rotation_deg = g.get("rotation_deg")
        if g.get("nose_fraction"):
            lg.nose_fraction_aft, lg.nose_fraction_fwd = g["nose_fraction"]
        if g.get("x_tail") is not None:
            lg.x_tail_m = g.get("x_tail")
        if g.get("x_main") is not None:
            lg.x_main_m = g.get("x_main")
        if g.get("x_nose") is not None:
            lg.x_nose_m = g.get("x_nose")
        lg.notes.append("gear:* geométricos lidos da montagem (trem colocado no CG da montagem, quadro da "
                        "montagem); estações e o curso continuam do tipo fixo (viga L1, 23.473) quando aplicável.")
        lg.geometry_summary = (
            f"montagem ({gtype}): main {g.get('x_main')}, nose {g.get('x_nose')}, tail {g.get('x_tail')}, "
            f"h_cg {g.get('h_cg')}; tombo {g.get('tipback_deg')}")
        rec["gear"] = {k: v for k, v in g.items() if k != "checks"}
    elif lg is not None and lg.kind != "none":
        why = "a montagem não desenha trem (gear: none)" if g.get("type") in ("none", None) else \
            f"trem da montagem '{g.get('type')}' sem método / tipo fixo '{lg.kind}' não corresponde"
        lg.notes.append(f"gear:* do tipo fixo: {why}.")
        rec["gear_note"] = why
    return rec
