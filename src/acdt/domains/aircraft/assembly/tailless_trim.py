# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Opt-in tailless trim closure of the W0 loop (``assembly.options.flying_wing.clmax: trimmed``, 10 nov 2026).

A flying wing without a flap cannot use the fixed-type ``CLmax_landing`` (clean CLmax + the
``assumptions.aero.flap`` increment, Raymer Sec. 12.4). Its usable maximum lift is the **trimmed** one: the
elevon must hold C_m = 0 about the CG while the wing reaches its local stall. Here, after a sizing pass, the
largest trimmed C_L of the drawn (scaled, balanced) assembly is computed for every loading case
(:func:`.tailless_approach.approach_consistency`: linear AVL trim with the symmetric elevon limited to
``elevon.max_deg``, Etkin & Reid 1996 Sec. 2.4, capped by the critical-section estimate with the user's
``clmax_airfoil``, Phillips & Alley 2007). The minimum over the cases replaces clean / take-off / landing CLmax
(``assumptions.aero.CLmax_trimmed``) and the design is re-sized until that value changes by < 0.01 (≤ 5
passes). The stall-speed requirement is kept: a lower CLmax makes the wing larger, it does not relax V_S.

PRESSUPOSTOS: linear lift up to the trimmed point; the take-off CLmax equals the landing one (no flap, no
rotation increment); ground effect ignored.
"""
from __future__ import annotations

import copy
import math

import numpy as np

from acdt.core.atmosphere import isa

TOL = 0.01
MAX_PASSES = 8
# Under-relaxation of the CLmax fixed-point (PRESSUPOSTO, numerical). A direct substitution
# CLmax_used ← CLmax_drawing can oscillate once the bodies' Cm term (Torenbeek NP shift)
# is in the main trim, because that couples trim, static margin and wing area.
RELAX = 0.5


def clmax_trimmed_requested(lp: dict | None) -> bool:
    spec = (lp or {}).get("spec") or {}
    fw = ((spec.get("options") or {}).get("flying_wing") or {})
    return str(fw.get("clmax") or "").lower() == "trimmed"


def trimmed_clmax_of(res) -> dict:
    """Per-case and minimum trimmed CLmax of the scaled assembly of ``res`` (no flap)."""
    from acdt import G0
    from . import tailless as T
    from . import tailless_approach as TA
    from .assembly import Assembly
    from .sizing import analyse, flight_from_design, main_wing
    lp = res.assembly_loop
    spec = lp["spec_scaled"]
    fw = T.options(spec) or ((spec.get("options") or {}).get("flying_wing") or {})
    el = fw.get("elevon")
    if not el:
        return {"status": "unassessed", "issue": "sem elevon (flying_wing.elevon) — CLmax equilibrado desconhecido"}
    out = analyse(spec, flight_from_design(res))
    asm = Assembly.from_dict(spec["assembly"])
    S = main_wing(asm)[1]["S"]
    at = isa(res.cruise_altitude)
    W = res.sizing.W0 * G0
    CLc = W / (0.5 * at.rho * res.cruise_speed**2 * S)
    # Sizing CLmax stays on the AVL wing: do not take a CLmax credit from the body Cm term
    # (C_m0 = 0 PRESSUPOSTO). The reported main trim (approach_consistency default) still includes it.
    rep = TA.approach_consistency(asm, res, out, fw, el, res.cruise_speed / at.a, W, S, None, CLc, None,
                                  include_bodies=False)
    vals = {k: v["trimmed_max"]["CL_max_effective"] for k, v in rep["cases"].items() if v.get("trimmed_max")}
    if not vals:
        return {"status": "unassessed", "issue": "AVL sem casos de carga avaliados"}
    k = min(vals, key=vals.get)
    return {"status": "assessed", "CLmax_trimmed": vals[k], "binding_case": k, "cases": vals,
            "static_margin": dict(out.static_margin or {})}


def close_trimmed_clmax(res, spec, runner):
    """Re-size with ``assumptions.aero.CLmax_trimmed`` until it matches the drawing's trimmed CLmax."""
    from acdt.core.requirements import Issue
    hist = []
    for _ in range(MAX_PASSES):
        if not res.sizing.converged or not res.assembly_loop:
            break
        try:
            t = trimmed_clmax_of(res)
        except Exception as ex:  # pragma: no cover - AVL failure
            t = {"status": "error", "issue": str(ex)}
        used = (spec.assumptions.get("aero") or {}).get("CLmax_trimmed") or res.highlift.CLmax_landing
        hist.append({"CLmax_used": used, **{k: v for k, v in t.items() if k != "static_margin"},
                     "W0": res.sizing.W0, "S": res.S})
        if t.get("status") != "assessed":
            res.issues.append(Issue("warning", "CLmax equilibrado (asa sem deriva) não avaliado: "
                                    + str(t.get("issue"))))
            break
        c = float(t["CLmax_trimmed"])
        if c <= 0:
            res.issues.append(Issue("warning", f"CLmax equilibrado {c:.3f} ≤ 0: a asa não equilibra — não usado"))
            break
        if abs(c - used) < TOL:
            break
        c_next = used + RELAX * (c - used)
        hist[-1]["CLmax_next"] = c_next
        sp = copy.deepcopy(spec)
        sp.assumptions.setdefault("aero", {})["CLmax_trimmed"] = c_next
        spec = sp
        res = runner(sp)
    # If the last action was a re-size, evaluate the design actually returned (honest residual).
    used_final = (spec.assumptions.get("aero") or {}).get("CLmax_trimmed")
    if (res.sizing.converged and res.assembly_loop and used_final is not None
            and (not hist or hist[-1].get("CLmax_used") != used_final or hist[-1].get("W0") != res.sizing.W0)):
        try:
            t = trimmed_clmax_of(res)
        except Exception as ex:  # pragma: no cover
            t = {"status": "error", "issue": str(ex)}
        hist.append({"CLmax_used": used_final, **{k: v for k, v in t.items() if k != "static_margin"},
                     "W0": res.sizing.W0, "S": res.S, "final_eval": True})
    c_final = used_final
    res.tailless_trim = {"history": hist, "CLmax_trimmed": c_final, "converged": bool(
        hist and hist[-1].get("status") == "assessed" and abs(hist[-1]["CLmax_trimmed"] - hist[-1]["CLmax_used"]) < TOL),
        "relax": RELAX,
        "method": __doc__.split("\n\n")[1].replace("\n", " ")}
    if c_final:
        res.issues.append(Issue("info", f"CLmax equilibrado da asa sem deriva (sem flap) = {c_final:.3f} usado como "
                                "CLmax limpo/descolagem/aterragem (flying_wing.clmax: trimmed; trim linear AVL "
                                "Etkin & Reid 2.4 + secção crítica Phillips & Alley 2007); "
                                f"{len(hist)} passagens, W0 {res.sizing.W0:.1f} kg"))
    return res, spec


# ------------------------------------------------------------------------------------------- Panknin cross-check
PANKNIN_SOURCE = ("Panknin 1989 ('Flying Rainbows', MARCS Symposium), formula as reproduced by B. & B. Kuhlman, "
                  "b2streamlines.com/Panknin/Panknin.html (worked example: 120 in span, chords 13/11 in, 17°, "
                  "E 222/E 230, C_L 0.6, σ 0.05 → −8.6° total, −3.2° geometric with their rounded K1 = 0.52; "
                  "−8.8° / −3.4° unrounded)")


def panknin_twist_deg(aspect_ratio_mean_chord: float, sweep_c4_deg: float, taper: float, CL: float, static_margin: float,
                      cm_root: float = 0.0, cm_tip: float = 0.0, a0_root_deg: float = 0.0,
                      a0_tip_deg: float = 0.0) -> dict:
    """Total aerodynamic and geometric washout [deg] (negative = washout) for a swept tailless wing:
    α_tot = (K1·C_m,root + K2·C_m,tip − C_L·σ) / (1.4e-5 · λ^1.43 · Λ), K1 = ¼(3 + 2t + t²)/(1 + t + t²),
    K2 = 1 − K1, λ = b / mean chord, Λ = quarter-chord sweep [deg]; α_geo = α_tot − (α0L,root − α0L,tip)."""
    if sweep_c4_deg <= 0:
        return {"status": "unassessed", "issue": "fórmula de Panknin só para asas com flecha positiva"}
    t = taper
    K1 = 0.25 * (3 + 2 * t + t * t) / (1 + t + t * t)
    K2 = 1 - K1
    tot = (K1 * cm_root + K2 * cm_tip - CL * static_margin) / (1.4e-5 * aspect_ratio_mean_chord**1.43 * sweep_c4_deg)
    return {"status": "assessed", "total_deg": tot, "geometric_deg": tot - (a0_root_deg - a0_tip_deg), "K1": K1,
            "K2": K2, "source": PANKNIN_SOURCE}


def wing_planform(asm) -> dict:
    """Root/tip chord, span, mean-chord aspect ratio, quarter-chord sweep and tip twist of the main wing."""
    from .sizing import main_wing
    w, gw = main_wing(asm)
    secs = sorted(w.sections, key=lambda s: s["le"][1])
    r, tp = secs[0], secs[-1]
    semi = float(tp["le"][1] - r["le"][1])
    xq_r = r["le"][0] + 0.25 * r["chord"]
    xq_t = tp["le"][0] + 0.25 * tp["chord"]
    b = 2 * semi
    cm = 0.5 * (r["chord"] + tp["chord"])
    return {"root_chord": float(r["chord"]), "tip_chord": float(tp["chord"]), "b": b, "AR_mean_chord": b / cm,
            "taper": float(tp["chord"] / r["chord"]), "sweep_c4_deg": math.degrees(math.atan2(xq_t - xq_r, semi)),
            "twist_tip_minus_root_deg": float(tp["twist_deg"] - r["twist_deg"])}


def washout_check(asm, CL: float, static_margin: float) -> dict:
    """Panknin total washout for the drawn planform (symmetric sections in AVL: C_m0 = α0L = 0) vs the drawn twist."""
    pl = wing_planform(asm)
    pk = panknin_twist_deg(pl["AR_mean_chord"], pl["sweep_c4_deg"], pl["taper"], CL, static_margin)
    return {**pl, "CL": CL, "static_margin_wing": static_margin, "panknin": pk,
            "note": "PRESSUPOSTO: secções simétricas (como no modelo AVL); σ = margem AVL sem corpos; a verificação "
                    "que conta é o equilíbrio AVL — Panknin é a estimativa de partida"}


# ------------------------------------------------------------------------------------------- packaging at the CG
FUEL_DENSITY_KG_L = 0.72          # avgas typical — same PRESSUPOSTO as weights_detailed.fuel_density_kg_L
FUEL_EXPANSION = 0.02             # 14 CFR 23.969 (pre-Amdt 23-64): expansion space ≥ 2 % of tank capacity
PACKAGING_NOTE = ("volume BRUTO dentro do corpo central e da asa (pontos de grelha com Body/Surface.contains), sem "
                  "estrutura, longarinas, motor, trem nem sistemas: é um limite superior — se não cabe, falha; se "
                  "cabe, é condição necessária mas não suficiente (packaging fino unassessed)")


def cg_packaging(asm, out, step: float = 0.015, a_max: float = 0.6) -> dict:
    """Does the useful load lumped on the fixed-mass CG (``useful_load_at: empty_cg``) fit near that CG?

    Fuel: volume = m/ρ (ρ 0.72 kg/L, PRESSUPOSTO) × (1 + 2 % expansion, 14 CFR 23.969). The axial slab
    |x − x_cg| ≤ a is widened until the gross interior volume of the bodies + main wing in it holds the fuel; the
    slab volume centroid is reported against x_cg. Payload: its volume is unknown (no item size) → the mean
    density it would need to fit in what is left of the slab is reported (unassessed otherwise)."""
    rows = (out.loading.get("rows") or {}).get("cheio") or []
    fuel = sum(r[1] for r in rows if r[0] == "combustível não posicionado")
    pay = sum(r[1] for r in rows if r[0] == "carga não posicionada")
    vz = out.loading["cases"]["vazio"]["cg"]
    x_cg = float(vz[0])
    comps = [c for c in asm.components if c.__class__.__name__ in ("Body", "Surface")
             and getattr(c, "role", None) not in ("item", "propeller")]
    items = [c for c in asm.components if getattr(c, "role", None) == "item"]
    if not comps:
        return {"status": "unassessed", "issues": ["sem corpos/superfícies"]}
    lo = np.min([np.asarray(c.bbox()[0], float) for c in comps], axis=0)
    hi = np.max([np.asarray(c.bbox()[1], float) for c in comps], axis=0)
    xs = np.arange(max(lo[0], x_cg - a_max), min(hi[0], x_cg + a_max) + 1e-9, step)
    ys = np.arange(lo[1], hi[1] + 1e-9, step)
    zs = np.arange(lo[2], hi[2] + 1e-9, step)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    inside = np.zeros(len(P), bool)
    owner = np.full(len(P), "", dtype=object)
    for c in comps:
        m_ = (np.asarray(c.contains(P), float) > 0.0) & ~inside
        owner[m_] = c.name
        inside |= m_
    for c in items:   # drawn equipment occupies its own volume
        inside &= ~(np.asarray(c.contains(P), float) > 0.0)
    Pin, own = P[inside], owner[inside]
    dv = step**3
    v_fuel = fuel / FUEL_DENSITY_KG_L / 1e3 * (1 + FUEL_EXPANSION) if fuel else 0.0
    res = {"x_cg_empty": x_cg, "fuel_kg": fuel, "payload_unpositioned_kg": pay, "fuel_volume_m3": v_fuel,
           "fuel_density_kg_L": FUEL_DENSITY_KG_L, "expansion": FUEL_EXPANSION, "grid_step_m": step,
           "note": PACKAGING_NOTE,
           "sources": ["14 CFR 23.969 (pré-Amdt 23-64): espaço de expansão ≥ 2 % da capacidade do tanque",
                       "ρ gasolina de aviação 0,72 kg/L — PRESSUPOSTO (como weights_detailed)"]}
    best = None
    for a in np.arange(step, a_max + 1e-9, step):
        sel = np.abs(Pin[:, 0] - x_cg) <= a
        V = sel.sum() * dv
        if V >= v_fuel:
            best = (a, sel, V)
            break
    if best is None:
        V = len(Pin) * dv
        res.update({"status": "assessed", "fuel_fits": False, "slab_volume_m3": V,
                    "issue": f"o combustível ({v_fuel * 1e3:.1f} L) não cabe no volume bruto a ±{a_max:.2f} m do CG"})
        return res
    a, sel, V = best
    by = {}
    for nm in set(own[sel]):
        by[nm] = float((own[sel] == nm).sum() * dv)
    xc = float(Pin[sel, 0].mean())
    # payload: the next widening that leaves room for it at a mean density ρ_p (unknown) — report the density
    dens = {}
    for a2 in (a + 0.05, a + 0.10, a + 0.20):
        V2 = float((np.abs(Pin[:, 0] - x_cg) <= a2 + 1e-9).sum() * dv)
        free = V2 - v_fuel
        dens[f"{a2:.2f}"] = {"slab_volume_m3": V2, "free_m3": free,
                             "payload_density_needed_kg_L": (pay / (free * 1e3)) if (pay and free > 0) else None}
    # bodies only (centre-body): the wing slab includes thin outboard sections
    body_names = {c.name for c in comps if c.__class__.__name__ == "Body"}
    isb = np.array([o in body_names for o in own], bool)
    body_fit = None
    for a3 in np.arange(step, a_max + 1e-9, step):
        Vb = float((isb & (np.abs(Pin[:, 0] - x_cg) <= a3)).sum() * dv)
        if Vb >= v_fuel:
            body_fit = {"fits": True, "slab_half_width_m": float(a3), "slab_volume_m3": Vb}
            break
    if body_fit is None:
        body_fit = {"fits": False, "volume_within_a_max_m3": float((isb & (np.abs(Pin[:, 0] - x_cg) <= a_max)).sum() * dv),
                    "a_max_m": a_max}
    res["bodies_only"] = body_fit
    res.update({"status": "assessed", "fuel_fits": True, "slab_half_width_m": float(a), "slab_volume_m3": float(V),
                "slab_by_component_m3": by, "slab_centroid_x": xc, "slab_centroid_offset_m": xc - x_cg,
                "payload_density_needed": dens,
                "payload_volume": "unassessed (sem dimensões dos itens de carga)"})
    return res


def _interior_grid(asm, out, step: float, a_max: float):
    """Gross interior points of bodies + wing, minus drawn items, around the empty CG."""
    rows = (out.loading.get("rows") or {}).get("cheio") or []
    fuel = sum(r[1] for r in rows if r[0] == "combustível não posicionado")
    pay = sum(r[1] for r in rows if r[0] == "carga não posicionada")
    vz = out.loading["cases"]["vazio"]["cg"]
    x_cg = float(vz[0])
    comps = [c for c in asm.components if c.__class__.__name__ in ("Body", "Surface")
             and getattr(c, "role", None) not in ("item", "propeller")]
    items = [c for c in asm.components if getattr(c, "role", None) == "item"]
    if not comps:
        return None
    lo = np.min([np.asarray(c.bbox()[0], float) for c in comps], axis=0)
    hi = np.max([np.asarray(c.bbox()[1], float) for c in comps], axis=0)
    xs = np.arange(max(lo[0], x_cg - a_max), min(hi[0], x_cg + a_max) + 1e-9, step)
    ys = np.arange(lo[1], hi[1] + 1e-9, step)
    zs = np.arange(lo[2], hi[2] + 1e-9, step)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    inside = np.zeros(len(P), bool)
    owner = np.full(len(P), "", dtype=object)
    for c in comps:
        m_ = (np.asarray(c.contains(P), float) > 0.0) & ~inside
        owner[m_] = c.name
        inside |= m_
    for c in items:
        inside &= ~(np.asarray(c.contains(P), float) > 0.0)
    body_names = {c.name for c in comps if c.__class__.__name__ == "Body"}
    Pin, own = P[inside], owner[inside]
    isb = np.array([o in body_names for o in own], bool)
    v_fuel = fuel / FUEL_DENSITY_KG_L / 1e3 * (1 + FUEL_EXPANSION) if fuel else 0.0
    return {"Pin": Pin, "own": own, "isb": isb, "dv": step ** 3, "x_cg_empty": x_cg,
            "fuel_kg": fuel, "payload_kg": pay, "fuel_volume_m3": v_fuel, "step": step}


def fine_packaging(asm, out, step: float = 0.015, a_max: float = 0.6) -> dict:
    """Place unpositioned fuel (and, as a sensitivity, payload) in the gross interior, not forced to the empty CG.

    Fuel is packed first into the centre-body, then the wing, taking cells nearest the empty CG
    (Raymer 2018 Sec. 15.1: keep the useful load near the CG). The packed fuel centroid is the
    volume centroid of those cells. Payload has no drawn volume: the leftover-centroid is a
    *candidate* station only; payload volume stays unassessed. Loading-case CGs are then rebuilt
    with fuel/payload at those stations (the main ``useful_load_at: empty_cg`` trim is unchanged).
    Static margin uses the assembly NP when present. Missing interior → unassessed.
    """
    g = _interior_grid(asm, out, step, a_max)
    if g is None:
        return {"status": "unassessed", "issues": ["sem corpos/superfícies"]}
    Pin, own, isb, dv = g["Pin"], g["own"], g["isb"], g["dv"]
    x_cg, fuel, pay, v_fuel = g["x_cg_empty"], g["fuel_kg"], g["payload_kg"], g["fuel_volume_m3"]
    n_need = int(np.ceil(v_fuel / dv)) if v_fuel > 0 else 0
    res = {"status": "assessed", "x_cg_empty": x_cg, "fuel_kg": fuel, "payload_kg": pay,
           "fuel_volume_m3": v_fuel, "grid_step_m": step,
           "note": ("packaging fino: combustível empacotado no volume bruto (corpo, depois asa) nas células "
                    "mais perto do CG vazio; a carga não tem volume desenhado — estação candidata no residual, "
                    "volume unassessed. Não substitui useful_load_at: empty_cg no equilíbrio principal. "
                    + PACKAGING_NOTE),
           "sources": ["Raymer 2018 Sec. 15.1 (carga útil junto do CG)",
                       "14 CFR 23.969 (pré-Amdt 23-64): espaço de expansão ≥ 2 %",
                       "ρ gasolina de aviação 0,72 kg/L — PRESSUPOSTO"]}
    # order: body cells nearest empty CG, then wing cells nearest empty CG
    def _order(mask):
        idx = np.flatnonzero(mask)
        if idx.size == 0:
            return idx
        d2 = np.sum((Pin[idx] - np.array([x_cg, 0.0, Pin[idx, 2].mean()])) ** 2, axis=1)
        return idx[np.argsort(d2)]

    body_idx, wing_idx = _order(isb), _order(~isb)
    order = np.concatenate([body_idx, wing_idx]) if (body_idx.size or wing_idx.size) else np.array([], int)
    if n_need and len(order) < n_need:
        res.update({"fuel_fits": False,
                    "issue": f"o combustível ({v_fuel * 1e3:.1f} L) não cabe no volume bruto a ±{a_max:.2f} m do CG"})
        return res
    fuel_idx = order[:n_need]
    left_idx = order[n_need:]
    if v_fuel > 0 and n_need:
        xf = float(Pin[fuel_idx, 0].mean())
        yf = float(Pin[fuel_idx, 1].mean())
        zf = float(Pin[fuel_idx, 2].mean())
        n_body = int(np.isin(fuel_idx, body_idx).sum()) if body_idx.size else 0
        res["fuel"] = {"fits": True, "centroid_m": [xf, yf, zf], "offset_from_empty_cg_m": xf - x_cg,
                       "volume_in_bodies_m3": n_body * dv,
                       "volume_in_wing_m3": (n_need - n_body) * dv}
    else:
        xf, yf, zf = x_cg, 0.0, float(out.loading["cases"]["vazio"]["cg"][2])
        res["fuel"] = {"fits": True, "centroid_m": [xf, yf, zf], "offset_from_empty_cg_m": 0.0, "note": "sem combustível"}
    # payload candidate: leftover centroid (volume unassessed)
    if pay and left_idx.size:
        xp, yp, zp = (float(Pin[left_idx, 0].mean()), float(Pin[left_idx, 1].mean()),
                      float(Pin[left_idx, 2].mean()))
        free = left_idx.size * dv
        res["payload"] = {"volume": "unassessed (sem dimensões dos itens de carga)",
                          "candidate_centroid_m": [xp, yp, zp],
                          "offset_from_empty_cg_m": xp - x_cg,
                          "leftover_gross_m3": free,
                          "density_needed_kg_L": pay / (free * 1e3) if free > 0 else None}
    elif pay:
        xp, yp, zp = x_cg, 0.0, float(out.loading["cases"]["vazio"]["cg"][2])
        res["payload"] = {"volume": "unassessed", "candidate_centroid_m": [xp, yp, zp],
                          "issue": "sem volume residual no grelha após o combustível"}
    else:
        xp, yp, zp = x_cg, 0.0, float(out.loading["cases"]["vazio"]["cg"][2])
        res["payload"] = {"volume": "n/a", "candidate_centroid_m": [xp, yp, zp]}
    # rebuild CGs (point masses at the packed / candidate stations)
    vz = out.loading["cases"]["vazio"]
    m_e, xe, ye, ze = float(vz["mass_kg"]), float(vz["cg"][0]), float(vz["cg"][1]), float(vz["cg"][2])

    def _cg(mf, xf_, xp_):
        m = m_e + mf + (pay if xp_ is not None else 0.0)
        x = (m_e * xe + mf * xf_ + ((pay * xp_) if xp_ is not None else 0.0)) / m
        return m, x

    cases = {
        "vazio": {"mass_kg": m_e, "x_cg": xe, "dx_m": 0.0},
        "combustível": {"mass_kg": m_e + fuel, "x_cg": _cg(fuel, xf, None)[1],
                        "dx_m": _cg(fuel, xf, None)[1] - xe},
        "carga": {"mass_kg": m_e + pay, "x_cg": _cg(0.0, xf, xp)[1],
                  "dx_m": _cg(0.0, xf, xp)[1] - xe},
        "cheio": {"mass_kg": m_e + fuel + pay, "x_cg": _cg(fuel, xf, xp)[1],
                  "dx_m": _cg(fuel, xf, xp)[1] - xe},
    }
    # lumped-at-empty-CG (the main-trim hypothesis) vs packed
    for name, cs in (out.loading.get("cases") or {}).items():
        if name in cases:
            cases[name]["x_cg_lumped_empty"] = float(cs["cg"][0])
            cases[name]["dx_vs_lumped_m"] = cases[name]["x_cg"] - float(cs["cg"][0])
    res["cases"] = cases
    # SM from assembly NP (Torenbeek if present)
    npd = getattr(out, "np", None) or {}
    xnp = npd.get("x_np_torenbeek") or npd.get("x_np") or npd.get("x_np_no_bodies")
    mac = npd.get("mac")
    if mac is None:
        try:
            from .sizing import main_wing
            mac = main_wing(asm)[1]["mac"]
        except Exception:
            mac = None
    if xnp is not None and mac:
        sm = {k: (float(xnp) - v["x_cg"]) / float(mac) for k, v in cases.items()}
        res["static_margin_packed"] = sm
        res["x_np_m"] = float(xnp)
        res["mac_m"] = float(mac)
        outside = {k: v for k, v in sm.items() if not (0.02 - 1e-3 <= v <= 0.08 + 1e-3)}
        res["static_margin_band"] = {"band": [0.02, 0.08], "outside": outside,
                                     "source": "NACA TR-796 0,02–0,08"}
        res["sm_in_band"] = not outside
    # fuel position assessed; payload volume unassessed → overall ok is None unless fuel does not fit or SM leaves the band
    if res.get("fuel", {}).get("fits") is False:
        res["ok"] = False
    elif res.get("static_margin_packed") is not None and res.get("sm_in_band") is False:
        res["ok"] = False
        res["issue"] = ("com o combustível e a carga nas estações empacotadas, a margem estática sai da banda "
                        "0,02–0,08 de NACA TR-796: " +
                        ", ".join(f"{k} {v:.3f}" for k, v in res["static_margin_band"]["outside"].items()))
    else:
        res["ok"] = None  # payload volume still unassessed; not a pass of a complete packaging
    return res
