# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina «estrutura paramétrica» (L0/L1) do domínio aircraft — docs/ESTRUTURA_PARAMETRICA.md.

Esquema único e independente da configuração (``structure_layout`` nos pressupostos) que coloca membros por
componente — superfícies sustentadoras, fuselagem, booms, apoios — e devolve UMA tabela de membros, o orçamento de
massa/CG/inércia estrutural e um modelo de vigas neutro (JSON ``acdt.beam/1`` e texto tipo Nastran, sem GPL).

* **Superfícies sustentadoras** (asa, empenagens): NÃO são redimensionadas aqui. A asa usa o caixão já dimensionado
  em :mod:`.structures` (Megson/Bruhn, Fase 2/3/5) e as empenagens as massas de :mod:`.structures_l1`; esta
  disciplina só as embrulha na tabela de membros e no modelo de vigas.
* **Fuselagem e booms** (novo): cavernas explícitas em estações (leves a passo regular, pesadas nas estações de
  cargas concentradas — ligação da asa, trem, berço do motor, carga útil, cauda), anteparas, reforçadores/longarinas
  e revestimento, com as verificações de :mod:`acdt.core.structures.frames` (anel por Castigliano com reação da
  casca, Shanley, Euler–Johnson/Gerard, encurvadura de painéis, antepara sob pressão) e dimensionamento por membro.

Cargas: o envelope LIMITE da viga-fuselagem L1 (:func:`.structures_l1.fuselage_beam`: cauda a VA, inércia do motor,
aterragem 23.473) e as forças concentradas desse mesmo modelo, mais ``loads`` do utilizador. Desconhecido ≠ zero:
o que falta fica «desconhecido» com a razão.

**Acoplamento**: ``relatorio`` (omissão) — só relata; ``iterar`` ainda não implementado (relatado como tal).
"""
from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np

from acdt import G0
from acdt.core import materials as matlib
from acdt.core.structures import frames as fr

LEVEL = "L1"
DEFAULTS: dict[str, Any] = {
    "enabled": False, "coupling": "relatorio", "material": "auto",
    "fuselage": {
        "enabled": True, "frame_pitch_m": None,
        # secção das cavernas: altura PRESSUPOSTO max(15 mm, 3 % D) (Niu 1988 cap. 11: cavernas leves de pequena altura)
        "frame_section": {"kind": "z", "h_m": None, "b_m": None},
        # n None → n = ⌈π D_max / pitch_m⌉ com passo 0,12 m (PRESSUPOSTO, ordem de grandeza de aviação ligeira)
        "stringers": {"n": None, "pitch_m": 0.12, "kind": "z", "h_m": 0.020, "b_m": 0.012, "t_m": None},
        "longerons": {"n": None, "area_m2": 0.0, "theta_deg": None},
        "skin_t_m": None,
        "bulkheads": None,            # [{id, x_m | x_frac, pressure_Pa, edge}] ; None → parede de fogo + fecho traseiro
        "auto_loads": True,
        "wing_attach_theta_deg": [90.0, -90.0],
        "engine_mount_theta_deg": [45.0, -45.0, 135.0, -135.0],
        "gear_theta_deg": {"fwd": [180.0], "aft": [150.0, -150.0]},
        "tail_theta_deg": [90.0, -90.0],
        "loads": [],                  # [{id, kind, x_m | x_frac, theta_deg, Fz_N, Fy_N, M_Nm, mass_kg, case}]
    },
    "booms": [],                      # [{id, x0_m, length_m, diameter_m, y_m, z_m, loads: [{x_m, Fz_N, Fy_N, T_Nm}]}]
    "export": {"beam_model": True},
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def options(spec: Any) -> dict[str, Any]:
    user = (spec.assumptions.get("structure_layout") or {}) if isinstance(spec.assumptions, dict) else {}
    return _merge(DEFAULTS, user)


def _not_evaluated(reason: str) -> dict[str, Any]:
    return {"evaluated": False, "level": LEVEL, "reason": reason, "members": [], "budget": None}


def material_dict(key: str) -> dict:
    m = matlib.get(key)
    return {"key": m.key, "name": m.name, "E": m.E, "G": m.G, "nu": m.nu, "rho": m.rho, "Ftu": m.Ftu, "Fty": m.Fty,
            "Fcy": m.Fcy, "Fsu": m.Fsu, "t_min": m.t_min, "source": m.source, "kind": m.kind}


def _material_key(res: Any, o: dict) -> str:
    k = o.get("material", "auto")
    if k and k != "auto":
        return str(k)
    sa = res.spec.assumptions.get("structures", {})
    mk = sa.get("material", "auto")
    if mk in ("cfrp",):
        return "cfrp_qi"
    if mk and mk != "auto" and mk in matlib.library():
        return str(mk)
    return "al2024_t3"


# ------------------------------------------------------------------------------------------------ member rows
def member(mid: str, component: str, kind: str, mass: float | None, x: float, y: float = 0.0, z: float = 0.0,
           *, I_own: tuple[float, float, float] = (0.0, 0.0, 0.0), RF: float | None = None,
           verdict: str | None = None, method: str = "", source: str = "estrutura_parametrica",
           section: dict | None = None, **extra: Any) -> dict:
    return {"id": mid, "component": component, "kind": kind, "mass_kg": mass, "x_m": x, "y_m": y, "z_m": z,
            "I_own_kg_m2": list(I_own), "RF_min": RF, "verdict": verdict or fr.verdict(RF), "method": method,
            "source": source, "section": section or {}, **extra}


def budget(members: list[dict]) -> dict:
    """Massa, CG e inércia (em torno do CG estrutural, eixos x para trás, y direita, z para cima) dos membros com
    massa conhecida; os de massa desconhecida ficam listados (desconhecido ≠ zero)."""
    known = [m for m in members if m["mass_kg"] is not None and math.isfinite(m["mass_kg"])]
    unknown = [m["id"] for m in members if m not in known]
    M = sum(m["mass_kg"] for m in known)
    if M <= 0:
        return {"mass_kg": 0.0, "cg_m": None, "inertia_kg_m2": None, "unknown_mass": unknown}
    cg = [sum(m["mass_kg"] * m[k] for m in known) / M for k in ("x_m", "y_m", "z_m")]
    Ixx = Iyy = Izz = 0.0
    for m in known:
        dx, dy, dz = m["x_m"] - cg[0], m["y_m"] - cg[1], m["z_m"] - cg[2]
        ix, iy, iz = m["I_own_kg_m2"]
        Ixx += ix + m["mass_kg"] * (dy**2 + dz**2)
        Iyy += iy + m["mass_kg"] * (dx**2 + dz**2)
        Izz += iz + m["mass_kg"] * (dx**2 + dy**2)
    by: dict[str, float] = {}
    for m in known:
        by[m["component"]] = by.get(m["component"], 0.0) + m["mass_kg"]
    return {"mass_kg": M, "cg_m": cg, "inertia_kg_m2": {"Ixx": Ixx, "Iyy": Iyy, "Izz": Izz},
            "by_component_kg": by, "unknown_mass": unknown,
            "note": "inércia própria: anéis (m R², m R²/2), linhas ao longo de x (m L²/12), placas (m R²/4, m R²/2); "
                    "superfícies sustentadoras distribuídas ∝ corda na envergadura — PRESSUPOSTO"}


# ------------------------------------------------------------------------------------------------ wrapped surfaces
def wing_members(res: Any, x_wing: float) -> tuple[list[dict], dict | None]:
    """Embrulha o caixão já dimensionado (:mod:`.structures`) — sem o redimensionar."""
    st = getattr(res, "structures", None)
    if st is None or getattr(st, "box", None) is None:
        return [member("asa", "asa", "caixao", None, x_wing, verdict="desconhecido", method="caixão em falta",
                       source="structures (não correu)")], None
    box, wing = st.box, res.config.wing
    y = np.asarray(box.y, float)
    c = np.asarray(wing.c_root + (wing.c_tip - wing.c_root) * y / (wing.span / 2), float)
    w = c / np.trapezoid(c, y)
    y2 = float(np.trapezoid(w * y**2, y))      # ⟨y²⟩ de uma semiasa (massa ∝ corda — PRESSUPOSTO)
    buck_ok = box.buckling is None or bool(box.buckling.ok)
    rows = []
    kinds = {"caps": "banzo_longarina", "webs": "alma_longarina", "web_uprights": "montante_alma",
             "box_skins": "revestimento_caixao", "covers_skin_stringers": "painel_reforcado", "core": "nucleo",
             "LE_TE_skins": "revestimento_bordos", "ribs": "nervura", "nonoptimum": "nao_otimo"}
    for key, m in box.masses.items():
        if key in ("ideal", "total"):
            continue
        m = float(m)
        if key in ("caps", "webs", "web_uprights"):
            ver = "passa"           # dimensionados a RF = 1 (A = M_u/(h σ), t = q/τ, Kuhn) ou espessura mínima
        elif key in ("box_skins", "covers_skin_stringers", "core"):
            ver = "passa" if buck_ok else "falha"
        else:
            ver = "desconhecido"    # espessura mínima / fator — não verificado
        rows.append(member(f"asa.{key}", "asa", kinds.get(key, key), m, x_wing, 0.0, 0.0, I_own=(m * y2, 0.0, m * y2),
                           verdict=ver, method=f"caixão {box.method} (Megson/Bruhn) — {box.material}",
                           source="structures.box (existente)"))
    beam = {"y": y.tolist(), "EI": None if box.EI is None else np.asarray(box.EI, float).tolist(),
            "GJ": None if box.GJ is None else np.asarray(box.GJ, float).tolist(), "x_m": x_wing}
    return rows, beam


def tail_members(res: Any, fus: dict) -> list[dict]:
    l1 = getattr(res, "structures_l1", None)
    tails = getattr(l1, "tails", None) or {}
    rows = []
    for key, comp, xk in (("htail_kg", "estabilizador", "x_ht_m"), ("vtail_kg", "deriva", "x_vt_m")):
        m = tails.get(key)
        rows.append(member(f"{comp}.caixao", comp, "caixao", None if m is None else float(m),
                           float(fus.get(xk, 0.0) or 0.0), 0.0, 0.0,
                           verdict="passa" if m is not None else "desconhecido",
                           method="caixão de duas longarinas, carga uniforme (structures_l1)",
                           source="structures_l1.tails (existente)"))
    return rows


# ------------------------------------------------------------------------------------------------ fuselage
def _xpos(d: dict, L: float) -> float | None:
    if d.get("x_m") is not None:
        return float(d["x_m"])
    if d.get("x_frac") is not None:
        return float(d["x_frac"]) * L
    return None


def _split(F: float, thetas: list[float], comp: str = "Fz") -> list[fr.RingLoad]:
    n = max(len(thetas), 1)
    return [fr.RingLoad(float(t), **{comp: F / n}) for t in thetas]


def auto_frame_loads(fus: dict, o: dict, wing: Any, n_lim: float = 0.0) -> tuple[dict[str, list[tuple[float, str, list[fr.RingLoad]]]],
                                                         list[str]]:
    """Cargas LIMITE concentradas por caso: {caso: [(x, id, [RingLoad])]} a partir da viga-fuselagem L1."""
    f = o["fuselage"]
    notes: list[str] = []
    cases: dict[str, list] = {"manobra": [], "aterragem": []}
    x_w = float(fus["x_wing_m"])
    fs, rs = wing.box.front_spar_xc, wing.box.rear_spar_xc
    c_r = wing.c_root
    x_f, x_r = x_w + (fs - 0.25) * c_r, x_w + (rs - 0.25) * c_r
    notes.append(f"ligação da asa: longarinas a x = {x_f:.3f} m e {x_r:.3f} m (corda de raiz no centro aerodinâmico "
                 "— PRESSUPOSTO); fixações a θ = " + ", ".join(f"{t:g}°" for t in f["wing_attach_theta_deg"]))
    # manobra: cauda (sustentação de projeto a VA + torção da deriva), motor; a asa equilibra as forças concentradas
    pts: list[tuple[float, str, list[fr.RingLoad], float]] = []
    Lt = float(fus.get("L_tail_design_N") or 0.0)
    if Lt:
        loads = _split(-Lt, f["tail_theta_deg"])
        Tf = float(fus.get("T_fin_Nm") or 0.0)
        if Tf:
            loads.append(fr.RingLoad(0.0, M=Tf))
        pts.append((float(fus["x_ht_m"]), "cauda", loads, -Lt))
    Fe = float(fus.get("F_engine_limit_N") or 0.0)
    if Fe:
        pts.append((float(fus["x_engine_m"]), "berco_motor", _split(-Fe, f["engine_mount_theta_deg"]), -Fe))
    Fsum = sum(p[3] for p in pts)
    Msum = sum(p[3] * (p[0] - x_f) for p in pts)
    # reações nas duas longarinas: R_f + R_r = −F, R_r (x_r − x_f) = −M
    R_r = -Msum / (x_r - x_f) if abs(x_r - x_f) > 1e-6 else -Fsum / 2
    R_f = -Fsum - R_r
    for x, i, lds, _F in pts:
        cases["manobra"].append((x, i, lds))
    cases["manobra"].append((x_f, "asa_longarina_frente", _split(R_f, f["wing_attach_theta_deg"])))
    cases["manobra"].append((x_r, "asa_longarina_tras", _split(R_r, f["wing_attach_theta_deg"])))
    notes.append("manobra: as forças concentradas (cauda, motor) são equilibradas pelas duas ligações da asa; a "
                 "inércia distribuída da casca vai para revestimento/reforçadores, não para as cavernas — PRESSUPOSTO")
    # aterragem: reações do trem, inércia do motor, sustentação na asa (metade em cada longarina — PRESSUPOSTO)
    lr = fus.get("landing_reactions_N") or {}
    if lr:
        cases["aterragem"].append((float(fus["x_gear_fwd_m"]), "trem_frente",
                                   _split(float(lr.get("forward", 0.0)), f["gear_theta_deg"]["fwd"])))
        cases["aterragem"].append((float(fus["x_gear_aft_m"]), "trem_tras",
                                   _split(float(lr.get("aft", 0.0)), f["gear_theta_deg"]["aft"])))
        n_i = float(lr.get("n_inertia", 0.0))
        if Fe and n_lim > 0 and n_i > 0:
            # F_engine_limit = n_lim m g → reescalado para o fator de inércia da aterragem
            cases["aterragem"].append((float(fus["x_engine_m"]), "berco_motor",
                                       _split(-Fe * n_i / n_lim, f["engine_mount_theta_deg"])))
        Lw = float(fus.get("wing_lift_landing_N") or 0.0)
        if Lw:
            cases["aterragem"].append((x_f, "asa_longarina_frente", _split(0.5 * Lw, f["wing_attach_theta_deg"])))
            cases["aterragem"].append((x_r, "asa_longarina_tras", _split(0.5 * Lw, f["wing_attach_theta_deg"])))
        notes.append("aterragem: reações do trem (23.473, viga L1) e metade da sustentação em cada longarina da asa; "
                     "trem preso à fuselagem — se o trem principal está na asa, declarar gear_theta_deg/loads")
    return cases, notes


def _user_loads(o: dict, L: float, n_lim: float, n_land: float) -> tuple[dict[str, list], list[str]]:
    f = o["fuselage"]
    cases: dict[str, list] = {}
    notes: list[str] = []
    for k, ld in enumerate(f.get("loads") or []):
        x = _xpos(ld, L)
        lid = str(ld.get("id") or f"carga_{k}")
        if x is None:
            notes.append(f"carga {lid}: sem x_m/x_frac — desconhecida, não entra")
            continue
        th = ld.get("theta_deg") or [180.0]
        th = th if isinstance(th, list) else [th]
        for case in ([ld["case"]] if ld.get("case") else ["manobra", "aterragem"]):
            n = n_lim if case == "manobra" else n_land
            Fz = float(ld.get("Fz_N") or 0.0) - (n * G0 * float(ld["mass_kg"]) if ld.get("mass_kg") else 0.0)
            Fy = float(ld.get("Fy_N") or 0.0)
            lds = [fr.RingLoad(float(t), Fy=Fy / len(th), Fz=Fz / len(th)) for t in th]
            if ld.get("M_Nm"):
                lds.append(fr.RingLoad(0.0, M=float(ld["M_Nm"])))
            cases.setdefault(case, []).append((x, lid, lds))
    if cases:
        notes.append("cargas do utilizador: massa × n (n_lim em manobra, n_inércia em aterragem) + forças declaradas, "
                     "reagidas pela casca na própria caverna; NÃO reequilibradas nas ligações da asa — declarar as "
                     "reações se forem relevantes")
    return cases, notes


def analyse_body(cid: str, x: np.ndarray, R: np.ndarray, M: np.ndarray, V: np.ndarray, T: np.ndarray,
                 frame_loads: dict[str, list], bulkheads: list[dict], fo: dict, mat: dict, nonopt: float,
                 y0: float = 0.0, z0: float = 0.0, x_off: float = 0.0) -> dict:
    """Cavernas + anteparas + casca reforçada de um corpo tubular. x relativo ao início do corpo (+ x_off global)."""
    L = float(x[-1] - x[0])
    D = 2 * float(np.max(R))
    pitch = float(fo.get("frame_pitch_m") or 0.5)
    fsec = fo["frame_section"]
    h = float(fsec.get("h_m") or max(0.015, 0.03 * D))
    b = float(fsec.get("b_m") or 0.6 * h)
    kind = fsec.get("kind", "z")
    t_min = float(mat["t_min"])
    # estações das cavernas: passo regular + estações de carga + anteparas (as regulares a < 0,3 passo saem)
    special: dict[float, list[str]] = {}
    for case, items in frame_loads.items():
        for xx, lid, _l in items:
            special.setdefault(round(float(xx), 4), []).append(lid)
    for bk in bulkheads:
        special.setdefault(round(float(bk["x_m"]), 4), []).append(str(bk["id"]))
    reg = [float(v) for v in np.arange(x[0], x[-1] + 1e-9, pitch)]
    st_x = sorted(set([v for v in reg if all(abs(v - s) > 0.3 * pitch for s in special)] + list(special)))
    st_x = [v for v in st_x if x[0] - 1e-9 <= v <= x[-1] + 1e-9]
    rows: list[dict] = []
    frames_out = []
    for xs in st_x:
        Rf = float(np.interp(xs, x, R))
        Mb = float(np.interp(xs, x, np.abs(M)))
        ids = special.get(round(xs, 4), [])
        cases_here = {}
        for case, items in frame_loads.items():
            lds = [ld for xx, _i, ll in items if abs(float(xx) - xs) < 1e-4 for ld in ll]
            if lds:
                cases_here[case] = fr.ring_internal_forces(Rf, lds)
        chk: dict = {}
        worst = None
        for case, ring in (cases_here or {"_": None}).items():
            Mu = 1.5 * ring["M"] if ring else 0.0
            Nu = 1.5 * ring["N"] if ring else 0.0
            c_ = fr.size_frame(kind, h, b, t_min, mat, Mu, Nu, Mb, D, pitch)
            if not chk or c_["A_m2"] > chk["A_m2"]:
                chk, worst = c_, case
        # verificação final da secção escolhida contra TODOS os casos da estação
        prof = fr.frame_profile(kind, chk["h_m"], chk["b_m"], chk["t_m"])
        allc = [fr.frame_check(prof, mat, 1.5 * rg["M"], 1.5 * rg["N"], Mb, D, pitch) for rg in cases_here.values()]
        if allc:
            note = chk.get("note")
            chk = {**min(allc, key=lambda c: c["RF_min"]), "t_m": chk["t_m"], "h_m": chk["h_m"], "b_m": chk["b_m"]}
            if note:
                chk["note"] = note
        t_need = chk["t_m"]
        A = chk["A_m2"]
        m = mat["rho"] * A * 2 * math.pi * Rf
        heavy = bool(cases_here)
        fid = f"{cid}.caverna@{xs + x_off:.3f}"
        rows.append(member(fid, cid, "caverna_pesada" if heavy else "caverna", m, xs + x_off, y0, z0,
                           I_own=(m * Rf**2, 0.5 * m * Rf**2, 0.5 * m * Rf**2), RF=chk["RF_min"],
                           verdict=chk["verdict"],
                           method="anel Castigliano + reação da casca (Megson), Gerard, Shanley (1949)",
                           section={"kind": kind, "h_m": chk["h_m"], "b_m": chk["b_m"], "t_m": t_need, "A_m2": A,
                                    "I_m4": chk["I_m4"]}, note=chk.get("note"),
                           loads=ids, governing_case=None if worst == "_" else worst,
                           ring={k: {"M_max_Nm": v["M_max_abs"], "theta_deg": v["theta_M_max_deg"],
                                     "N_max_N": v["N_max_abs"]} for k, v in cases_here.items()},
                           checks={k: chk.get(k) for k in ("RF_strength", "RF_crippling", "RF_shanley")}))
        frames_out.append({"x_m": xs + x_off, "R_m": Rf, "t_m": t_need, "heavy": heavy})
    # anteparas: placa circular (pressão) + anel já contado como caverna na mesma estação
    for bk in bulkheads:
        xs = float(bk["x_m"])
        Rb = float(np.interp(xs, x, R))
        p = float(bk.get("pressure_Pa") or 0.0)
        edge = str(bk.get("edge") or "simply_supported")
        pb = fr.size_pressure_bulkhead(Rb, 1.5 * p, mat, t_min, edge)
        m = mat["rho"] * math.pi * Rb**2 * pb["t_m"]
        ver = pb["verdict"] if p > 0 else "desconhecido"
        rows.append(member(f"{cid}.antepara.{bk['id']}", cid, "antepara", m, xs + x_off, y0, z0,
                           I_own=(0.5 * m * Rb**2, 0.25 * m * Rb**2, 0.25 * m * Rb**2),
                           RF=pb["RF"] if p > 0 else None, verdict=ver,
                           method="placa circular sob pressão (Timoshenko & Woinowsky-Krieger §15–16)",
                           section={"t_m": pb["t_m"], "pressure_Pa": p, "edge": edge},
                           note=None if p > 0 else "sem pressão declarada: alma à espessura mínima; corte da alma "
                                                   "sob cargas concentradas não modelado (desconhecido)"))
    # casca reforçada por estação
    so, lo = fo["stringers"], fo["longerons"]
    n_l = int(lo.get("n") or 0)
    lay = fr.ShellLayout(n_stringers=int(so.get("n") or 0) or 12, stringer_kind=so.get("kind", "z"),
                         stringer_h=float(so.get("h_m") or 0.02), stringer_b=float(so.get("b_m") or 0.012),
                         stringer_t=float(so.get("t_m") or t_min), skin_t=float(fo.get("skin_t_m") or t_min),
                         frame_pitch=pitch, longeron_area=float(lo.get("area_m2") or 0.0),
                         longeron_theta_deg=list(lo.get("theta_deg") or
                                                 [45.0 + 360.0 * k / n_l for k in range(n_l)] if n_l else []))
    stations = [fr.ShellStation(float(xi), float(ri), float(mi), float(vi), float(ti))
                for xi, ri, mi, vi, ti in zip(x, R, M, V, T)]
    tab = fr.size_shell(stations, lay, mat, t_min)
    ts = np.array([r["t_skin_m"] for r in tab])
    tstr = np.array([r["t_stringer_m"] for r in tab])
    A_str = np.array([fr.stringer_profile(lay.stringer_kind, lay.stringer_h, lay.stringer_b, t_).properties()["A"]
                      for t_ in tstr])
    rho = mat["rho"]
    dm_skin = rho * 2 * math.pi * R * ts
    dm_str = rho * lay.n_stringers * A_str
    m_skin = float(np.trapezoid(dm_skin, x))
    m_str = float(np.trapezoid(dm_str, x))
    m_lon = rho * n_l * lay.longeron_area * L
    x_skin = float(np.trapezoid(x * dm_skin, x) / m_skin) if m_skin else 0.5 * L
    x_str = float(np.trapezoid(x * dm_str, x) / m_str) if m_str else 0.5 * L
    rf_shell = min(r["RF_min"] for r in tab)
    i_w = int(np.argmin([r["RF_min"] for r in tab]))
    R2 = float(np.mean(R**2))
    rows.append(member(f"{cid}.revestimento", cid, "revestimento", m_skin, x_skin + x_off, y0, z0,
                       I_own=(m_skin * R2, m_skin * (0.5 * R2 + L**2 / 12), m_skin * (0.5 * R2 + L**2 / 12)),
                       RF=min(min(r["RF_skin_shear"], r["RF_skin_buckling_limit"]) for r in tab),
                       method="corte V/(πR)+T/(2πR²) (Megson); painel plano k=4/5,35 à carga limite (Bruhn C5)",
                       section={"t_max_m": float(ts.max()), "t_min_m": float(ts.min())}))
    rows.append(member(f"{cid}.reforcadores", cid, "reforcador", m_str, x_str + x_off, y0, z0,
                       I_own=(m_str * R2, m_str * (0.5 * R2 + L**2 / 12), m_str * (0.5 * R2 + L**2 / 12)),
                       RF=min(min(r["RF_stringer_column"], r["RF_stringer_tension"]) for r in tab),
                       method="booms + largura efetiva de von Kármán; Euler–Johnson com crippling de Gerard (Bruhn)",
                       section={"n": lay.n_stringers, "kind": lay.stringer_kind, "h_m": lay.stringer_h,
                                "b_m": lay.stringer_b, "t_max_m": float(tstr.max())}))
    if n_l and lay.longeron_area > 0:
        rows.append(member(f"{cid}.longarinas", cid, "longarina", m_lon, 0.5 * L + x[0] + x_off, y0, z0,
                           I_own=(m_lon * R2, m_lon * L**2 / 12, m_lon * L**2 / 12), RF=rf_shell,
                           method="booms adicionais na idealização da casca",
                           section={"n": n_l, "area_m2": lay.longeron_area, "theta_deg": lay.longeron_theta_deg}))
    ideal = sum(r["mass_kg"] for r in rows)
    rows.append(member(f"{cid}.nao_otimo", cid, "nao_otimo", (nonopt - 1.0) * ideal,
                       float(sum(r["mass_kg"] * r["x_m"] for r in rows) / ideal) if ideal else x_off, y0, z0,
                       verdict="desconhecido", method=f"fator não-ótimo {nonopt:g} (Torenbeek 1982 App. C) — PRESSUPOSTO"))
    beam = {"x": (x + x_off).tolist(), "A": [], "I": [], "J": []}
    for r, t_ in zip(tab, ts):
        beam["A"].append(float(2 * math.pi * r["R_m"] * t_ + lay.n_stringers * r["stringer_area_m2"]))
        beam["I"].append(float(r["I_m4"]))
        beam["J"].append(float(2 * math.pi * r["R_m"] ** 3 * t_))
    return {"members": rows, "frames": frames_out, "shell_table": tab, "worst_shell_station": tab[i_w],
            "beam": beam, "layout": {"frame_pitch_m": pitch, "frame_h_m": h, "frame_b_m": b,
                                     "n_stringers": lay.n_stringers, "n_longerons": n_l}}


def fuselage_layout(res: Any, o: dict, mat: dict) -> dict:
    l1 = getattr(res, "structures_l1", None)
    fus = getattr(l1, "fuselage", None) or {}
    if not fus or "V_limit_N" not in fus:
        return {"evaluated": False, "reason": "viga-fuselagem L1 (structures_l1) não disponível"}
    cfg = res.config
    fo = copy.deepcopy(o["fuselage"])
    fo["frame_pitch_m"] = fo.get("frame_pitch_m") or cfg.fuselage.frames.frame_pitch
    fo["skin_t_m"] = fo.get("skin_t_m") or cfg.fuselage.frames.skin_thickness
    if fo["longerons"].get("n") is None:
        fo["longerons"]["n"] = 0
    if fo["stringers"].get("n") is None:
        fo["stringers"]["n"] = max(4, math.ceil(math.pi * cfg.fuselage.max_diameter
                                                / float(fo["stringers"].get("pitch_m") or 0.12)))
    L = float(cfg.fuselage.length)
    x = np.asarray(fus["x"], float)
    R = np.asarray(fus["R_m"], float)
    M = np.asarray(fus["M_limit_Nm"], float)
    V = np.asarray(fus["V_limit_N"], float)
    T = np.asarray(fus["T_limit_Nm"], float)
    notes: list[str] = []
    cases: dict[str, list] = {}
    n_lim = float(res.structures.vn.n_limit_pos) if getattr(res, "structures", None) is not None else 0.0
    lr = fus.get("landing_reactions_N") or {}
    if fo.get("auto_loads", True):
        cases, n1 = auto_frame_loads(fus, o, cfg.wing, n_lim)
        notes += n1
    uc, n2 = _user_loads(o, L, n_lim, float(lr.get("n_inertia", 0.0)))
    notes += n2
    for k, v in uc.items():
        cases.setdefault(k, []).extend(v)
    bks = fo.get("bulkheads")
    if bks is None:
        bks = [{"id": "parede_de_fogo", "x_m": float(fus.get("x_engine_m", 0.12 * L)), "pressure_Pa": 0.0},
               {"id": "fecho_traseiro", "x_m": 0.95 * L, "pressure_Pa": 0.0}]
        notes.append("anteparas por omissão: parede de fogo no berço do motor e fecho traseiro a 0,95 L "
                     "(as duas da viga L1) — PRESSUPOSTO")
    bks = [{**b, "x_m": _xpos(b, L)} for b in bks if _xpos(b, L) is not None]
    nonopt = float(res.spec.assumptions["structures"].get("nonoptimum_factor", 1.25))
    out = analyse_body("fuselagem", x, R, M, V, T, cases, bks, fo, mat, nonopt)
    out["notes"] = notes
    out["evaluated"] = True
    out["load_cases"] = {k: [{"x_m": xx, "id": i, "loads": [vars(ld) for ld in ll]} for xx, i, ll in v]
                         for k, v in cases.items()}
    out["l1_fuselage_kg"] = float(fus.get("mass_kg", 0.0))
    return out


def boom_layout(bd: dict, o: dict, mat: dict, nonopt: float) -> dict:
    """Boom em consola a partir da raiz (x0): cargas pontuais do utilizador → V, M, T por integração da ponta."""
    bid = str(bd.get("id") or "boom")
    try:
        x0, Lb, D = float(bd["x0_m"]), float(bd["length_m"]), float(bd["diameter_m"])
    except (KeyError, TypeError, ValueError):
        return {"evaluated": False, "reason": f"{bid}: falta x0_m/length_m/diameter_m", "members": []}
    loads = bd.get("loads") or []
    if not loads:
        return {"evaluated": False, "reason": f"{bid}: sem cargas declaradas — desconhecido", "members": []}
    s = np.linspace(0.0, Lb, 41)
    pts = sorted(float(ld["x_m"]) - x0 for ld in loads)
    s = np.unique(np.concatenate([s, [p for p in pts if 0 <= p <= Lb]]))
    V = np.zeros_like(s)
    M = np.zeros_like(s)
    T = np.zeros_like(s)
    fl: dict[str, list] = {"limite": []}
    for ld in loads:
        p = float(ld["x_m"]) - x0
        F = math.hypot(float(ld.get("Fz_N") or 0.0), float(ld.get("Fy_N") or 0.0))
        V += np.where(s <= p, F, 0.0)
        M += np.where(s <= p, F * (p - s), 0.0)
        T += np.where(s <= p, abs(float(ld.get("T_Nm") or 0.0)), 0.0)
        fl["limite"].append((p, str(ld.get("id") or "carga"),
                             [fr.RingLoad(180.0, Fy=float(ld.get("Fy_N") or 0.0), Fz=float(ld.get("Fz_N") or 0.0))]
                             + ([fr.RingLoad(0.0, M=float(ld["T_Nm"]))] if ld.get("T_Nm") else [])))
    fo = _merge(DEFAULTS["fuselage"], {k: v for k, v in bd.items() if k in DEFAULTS["fuselage"]})
    fo["frame_pitch_m"] = fo.get("frame_pitch_m") or 0.3
    if fo["stringers"].get("n") is None:
        fo["stringers"]["n"] = 8
    if fo["longerons"].get("n") is None:
        fo["longerons"]["n"] = 0
    R = np.full_like(s, D / 2)
    bks = [{"id": "raiz", "x_m": 0.0, "pressure_Pa": 0.0}]
    out = analyse_body(bid, s, R, M, V, T, fl, bks, fo, mat, nonopt, float(bd.get("y_m") or 0.0),
                       float(bd.get("z_m") or 0.0), x0)
    out["evaluated"] = True
    out["notes"] = ["cargas do boom: LIMITE declaradas pelo utilizador (cauda/rotor/trem), consola da raiz"]
    return out


# ------------------------------------------------------------------------------------------------ beam model
def beam_model(mat: dict, fus: dict | None, wing: dict | None, members: list[dict]) -> dict:
    """Modelo de vigas neutro ``acdt.beam/1``: nós, barras (A, I1, I2, J), material e massas concentradas."""
    nodes: list[dict] = []
    elems: list[dict] = []
    E, G = mat["E"], mat["G"]

    def node(x: float, y: float, z: float) -> int:
        nodes.append({"id": len(nodes) + 1, "xyz": [x, y, z]})
        return len(nodes)

    missing = []
    fus_ids: list[int] = []
    if fus and fus.get("x"):
        xs = fus["x"]
        fus_ids = [node(float(x), 0.0, 0.0) for x in xs]
        for k in range(len(xs) - 1):
            elems.append({"id": len(elems) + 1, "component": "fuselagem", "nodes": [fus_ids[k], fus_ids[k + 1]],
                          "A": 0.5 * (fus["A"][k] + fus["A"][k + 1]), "I1": 0.5 * (fus["I"][k] + fus["I"][k + 1]),
                          "I2": 0.5 * (fus["I"][k] + fus["I"][k + 1]), "J": 0.5 * (fus["J"][k] + fus["J"][k + 1])})
    else:
        missing.append("fuselagem")
    if wing and wing.get("EI") and wing.get("GJ"):
        xw = float(wing["x_m"])
        root = fus_ids[int(np.argmin([abs(n["xyz"][0] - xw) for n in nodes]))] if fus_ids else node(xw, 0.0, 0.0)
        for side in (1.0, -1.0):
            prev = root
            for k, y in enumerate(wing["y"]):
                if y <= 1e-9:
                    continue
                nid = node(xw, side * float(y), 0.0)
                EI = 0.5 * (wing["EI"][k - 1] + wing["EI"][k])
                GJ = 0.5 * (wing["GJ"][k - 1] + wing["GJ"][k])
                elems.append({"id": len(elems) + 1, "component": "asa", "nodes": [prev, nid], "A": 1e-4,
                              "I1": EI / E, "I2": 10 * EI / E, "J": GJ / G})
                prev = nid
    else:
        missing.append("asa (EI/GJ do caixão)")
    missing.append("empenagens e booms (EI/GJ não guardados — próximo incremento)")
    masses = []
    for m in members:
        if not nodes or m["mass_kg"] is None or m["mass_kg"] <= 0:
            continue
        p = np.array([m["x_m"], m["y_m"], m["z_m"]])
        nid = int(np.argmin([np.linalg.norm(np.array(n["xyz"]) - p) for n in nodes])) + 1
        masses.append({"node": nid, "mass_kg": m["mass_kg"], "member": m["id"]})
    return {"format": "acdt.beam/1", "units": "SI (m, N, kg, Pa)",
            "material": {"id": 1, "E": E, "G": G, "nu": mat["nu"], "rho": 0.0, "source": mat["source"]},
            "nodes": nodes, "elements": elems, "point_masses": masses, "missing": missing,
            "note": "barras sem massa (ρ = 0): a massa estrutural entra só como massas concentradas no nó mais próximo; "
                    "A da asa simbólica (1e-4 m²) e I2 = 10 I1 (rigidez no plano — PRESSUPOSTO); eixo I1 = flexão "
                    "vertical. Para análise externa (p. ex. CalculiX por subprocesso via Build)."}


def _f8(v: float) -> str:
    s = f"{v:.6g}"
    if len(s) > 8:
        s = f"{v:.2e}"
    return s[:8].ljust(8)


def to_nastran(model: dict) -> str:
    """Texto em formato de campos curtos tipo Nastran (GRID/MAT1/PBAR/CBAR/CONM2). Gerado aqui, sem código GPL."""
    out = ["$ acdt estrutura paramétrica — modelo de vigas (acdt.beam/1)", "$ unidades SI", "BEGIN BULK"]
    mt = model["material"]
    out.append("MAT1    " + "1".ljust(8) + _f8(mt["E"]) + _f8(mt["G"]) + _f8(mt["nu"]) + _f8(0.0))
    for n in model["nodes"]:
        x, y, z = n["xyz"]
        out.append("GRID    " + str(n["id"]).ljust(8) + " " * 8 + _f8(x) + _f8(y) + _f8(z))
    for e in model["elements"]:
        out.append("PBAR    " + str(e["id"]).ljust(8) + "1".ljust(8) + _f8(e["A"]) + _f8(e["I1"]) + _f8(e["I2"])
                   + _f8(e["J"]))
        a, b = e["nodes"]
        orient = (0.0, 0.0, 1.0)
        out.append("CBAR    " + str(e["id"]).ljust(8) + str(e["id"]).ljust(8) + str(a).ljust(8) + str(b).ljust(8)
                   + "".join(_f8(v) for v in orient))
    for k, pm in enumerate(model["point_masses"]):
        out.append("CONM2   " + str(100000 + k).ljust(8) + str(pm["node"]).ljust(8) + "0".ljust(8) + _f8(pm["mass_kg"]))
    out.append("ENDDATA")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------------ stage
def analyse_layout(res: Any) -> dict:
    o = options(res.spec)
    mkey = _material_key(res, o)
    mat = material_dict(mkey)
    notes: list[str] = []
    members: list[dict] = []
    fus = fuselage_layout(res, o, mat) if o["fuselage"].get("enabled", True) else {"evaluated": False,
                                                                                  "reason": "desligada"}
    x_w = float(((getattr(res.structures_l1, "fuselage", None) or {}).get("x_wing_m"))
                or 0.35 * res.config.fuselage.length) if getattr(res, "structures_l1", None) else 0.0
    wrows, wbeam = wing_members(res, x_w)
    members += wrows
    members += tail_members(res, (getattr(res.structures_l1, "fuselage", None) or {})
                            if getattr(res, "structures_l1", None) else {})
    if fus.get("evaluated"):
        members += fus["members"]
    else:
        members.append(member("fuselagem", "fuselagem", "casca", None, 0.0, verdict="desconhecido",
                              method=str(fus.get("reason"))))
    nonopt = float(res.spec.assumptions["structures"].get("nonoptimum_factor", 1.25))
    booms = []
    for bd in o.get("booms") or []:
        b = boom_layout(bd, o, mat, nonopt)
        booms.append({k: v for k, v in b.items() if k != "members"})
        if b.get("evaluated"):
            members += b["members"]
        else:
            members.append(member(str(bd.get("id") or "boom"), str(bd.get("id") or "boom"), "boom", None, 0.0,
                                  verdict="desconhecido", method=str(b.get("reason"))))
    bud = budget(members)
    counts: dict[str, int] = {}
    for m in members:
        counts[m["verdict"]] = counts.get(m["verdict"], 0) + 1
    if "falha" in counts:
        overall = "falha"
    elif "desconhecido" in counts:
        overall = "desconhecido"
    else:
        overall = "passa"
    out: dict[str, Any] = {"evaluated": True, "level": LEVEL, "material": mat, "coupling_mode": o["coupling"],
                           "members": members, "budget": bud, "verdict_counts": counts, "verdict": overall,
                           "fuselage": {k: v for k, v in fus.items() if k not in ("members",)},
                           "booms": booms, "notes": notes}
    if o["coupling"] == "iterar":
        notes.append("acoplamento iterar ainda não implementado: resultado relatado, não aplicado ao dimensionamento")
    l1 = getattr(res, "structures_l1", None)
    if l1 is not None and fus.get("evaluated"):
        fm = bud["by_component_kg"].get("fuselagem")
        out["comparison"] = {"fuselage_layout_kg": fm, "fuselage_L1_kg": l1.masses.get("fuselage_kg"),
                             "fuselage_raymer_kg": l1.masses.get("fuselage_raymer_kg"),
                             "wing_box_kg": l1.masses.get("wing_box_kg")}
    if o.get("export", {}).get("beam_model", True):
        out["beam_model"] = beam_model(mat, fus.get("beam") if fus.get("evaluated") else None, wbeam, members)
    return out


def structure_layout_stage(res: Any) -> None:
    from acdt.core.requirements import Issue
    o = options(res.spec)
    if not o.get("enabled", False):
        res.structure_layout = _not_evaluated("structure_layout.enabled: false (opt-in)")
        return
    try:
        res.structure_layout = analyse_layout(res)
    except Exception as ex:  # noqa: BLE001 — nunca parte o pipeline; fica desconhecido
        res.structure_layout = _not_evaluated(f"falhou: {type(ex).__name__}: {ex}")
        res.issues.append(Issue("warning", f"estrutura paramétrica não avaliada: {type(ex).__name__}: {ex}"))
