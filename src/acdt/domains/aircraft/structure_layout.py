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
    "booms": [],                      # [{id, x0_m, length_m, diameter_m, y_m, z_m, x_attach_m, loads: [{x_m, Fz_N, Fy_N, T_Nm}]}]
    "booms_from_assembly": True,      # corpos com papel «boom» na montagem + cauda/rotores que lá se apoiam
    "rotor_thrust_factor": 1.5,       # T_lim/(W0 g/n) dos rotores de elevação — PRESSUPOSTO, declarar
    "tails": {"method": "buckling"},  # buckling: dimensionador por estabilidade da asa; strength: caixão L1
    "export": {"beam_model": True},
}


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
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


def material_dict(key: str) -> dict[str, Any]:
    m = matlib.get(key)
    return {"key": m.key, "name": m.name, "E": m.E, "G": m.G, "nu": m.nu, "rho": m.rho, "Ftu": m.Ftu, "Fty": m.Fty,
            "Fcy": m.Fcy, "Fsu": m.Fsu, "t_min": m.t_min, "source": m.source, "kind": m.kind}


def _material_key(res: Any, o: dict[str, Any]) -> str:
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
           section: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    return {"id": mid, "component": component, "kind": kind, "mass_kg": mass, "x_m": x, "y_m": y, "z_m": z,
            "I_own_kg_m2": list(I_own), "RF_min": RF, "verdict": verdict or fr.verdict(RF), "method": method,
            "source": source, "section": section or {}, **extra}


def budget(members: list[dict[str, Any]]) -> dict[str, Any]:
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


# ------------------------------------------------------------------------------------------------ lifting surfaces
_BOX_KINDS = {"caps": "banzo_longarina", "webs": "alma_longarina", "web_uprights": "montante_alma",
              "box_skins": "revestimento_caixao", "covers_skin_stringers": "painel_reforcado", "core": "nucleo",
              "LE_TE_skins": "revestimento_bordos", "ribs": "nervura", "nonoptimum": "nao_otimo"}


def box_members(comp: str, box: dict[str, Any], x: float, y0: float = 0.0, z0: float = 0.0, axis: str = "y",
                mirror: bool = True, source: str = "") -> list[dict[str, Any]]:
    """Linhas da tabela de membros de um caixão já dimensionado (asa ou empenagem; ``box`` no formato de
    :func:`.structures_l1._tail_box_summary`). A massa distribui-se ∝ corda na envergadura (PRESSUPOSTO) para a
    inércia própria; com ``mirror`` o caixão tem duas metades simétricas (centroide no plano de simetria)."""
    y = np.asarray(box["y"], float)
    c = box["c_root_m"] + (box["c_tip_m"] - box["c_root_m"]) * y / max(box["semispan_m"], 1e-9)
    w = c / np.trapezoid(c, y)
    y1 = float(np.trapezoid(w * y, y))
    y2 = float(np.trapezoid(w * y**2, y))
    buck_ok = box.get("buckling_ok")
    rows = []
    for key, m in box["masses"].items():
        if key in ("ideal", "total"):
            continue
        m = float(m)
        if key in ("caps", "webs", "web_uprights"):
            ver = "passa"           # dimensionados a RF = 1 (A = M_u/(h σ), t = q/τ, Kuhn) ou espessura mínima
        elif key in ("box_skins", "covers_skin_stringers", "core"):
            ver = "desconhecido" if buck_ok is None else ("passa" if buck_ok else "falha")
        else:
            ver = "desconhecido"    # espessura mínima / fator — não verificado
        off = 0.0 if mirror else y1     # metade única (deriva): centroide fora do eixo
        if axis == "z":
            pos = (x, y0, z0 + off)
            I_own = (m * (y2 - off**2), m * (y2 - off**2), 0.0)
        else:
            pos = (x, y0 + off, z0)
            I_own = (m * (y2 - off**2), 0.0, m * (y2 - off**2))
        rows.append(member(f"{comp}.{key}", comp, _BOX_KINDS.get(key, key), m, *pos, I_own=I_own, verdict=ver,
                           method=f"caixão {box.get('method')} (Megson/Bruhn) — {box.get('material')}; secção: "
                                  f"{box.get('section', '')}", source=source))
    return rows


def wing_box_summary(res: Any) -> dict[str, Any] | None:
    st = getattr(res, "structures", None)
    if st is None or getattr(st, "box", None) is None:
        return None
    box, wing = st.box, res.config.wing
    return {"y": np.asarray(box.y, float).tolist(), "masses": {k: float(v) for k, v in box.masses.items()},
            "method": box.method, "material": box.material,
            "buckling_ok": None if box.buckling is None else bool(box.buckling.ok),
            "EI": None if box.EI is None else np.asarray(box.EI, float).tolist(),
            "GJ": None if box.GJ is None else np.asarray(box.GJ, float).tolist(),
            "section": "multicélula (Fase 5)" if "x_sc_c" in box.details else "duas mesas / Bredt",
            "semispan_m": float(wing.span / 2), "c_root_m": float(wing.c_root), "c_tip_m": float(wing.c_tip)}


def structures_material(res: Any) -> str:
    """Material do caixão como em :func:`.sizing.structures_inputs` (``structures.material``)."""
    from .weights_detailed import _merge_opts
    A = res.spec.assumptions
    mat = A["structures"]["material"]
    if mat == "auto":
        mat = "cfrp" if _merge_opts(A["weights"].get("components"))["material"] == "composite" else "al2024_t3"
    return str(mat)


def tail_boxes(res: Any, o: dict[str, Any]) -> tuple[dict[str, dict[str, Any] | None], list[str]]:
    """Empenagens pelo caminho da asa: ``tails.method: buckling`` (omissão) redimensiona o caixão com o
    dimensionador por estabilidade da asa (Fase 3: painéis reforçados, almas de Kuhn) sob a carga de projeto da L1
    (carga uniforme, cima e baixo — PRESSUPOSTO), depois a secção multicélula da Fase 5 dá EI/GJ. ``strength``
    usa o caixão L1 tal como está (só resistência). A deriva é encastrada só na raiz (``single_sided``: metade de
    uma asa espelhada de altura b, M_raiz = L b/2); o caixão L1 da deriva trata-a como duas metades de altura b/2."""
    from .structures_l1 import _tail_box_summary, _uniform_tail
    l1 = getattr(res, "structures_l1", None)
    tails = getattr(l1, "tails", None) or {}
    meth = str((o.get("tails") or {}).get("method", "buckling"))
    notes: list[str] = []
    out: dict[str, dict[str, Any] | None] = {}
    nonopt = float(res.spec.assumptions["structures"].get("nonoptimum_factor", 1.25))
    mat = structures_material(res)
    for key, surf in (("htail", res.config.htail), ("vtail", res.config.vtail)):
        lift = tails.get(f"{key}_limit_lift_N")
        if surf is None or lift is None:
            out[key] = None
            continue
        if meth == "buckling":
            try:
                ss = key == "vtail"
                box = _uniform_tail(surf, float(lift), mat, nonopt, method="buckling", single_sided=ss)
                out[key] = _tail_box_summary(surf, box, mat, single_sided=ss)
                continue
            except Exception as ex:  # noqa: BLE001 — recua para o caixão L1, com nota
                notes.append(f"{key}: dimensionamento por estabilidade falhou ({type(ex).__name__}: {ex}); caixão L1")
        out[key] = tails.get(f"{key}_box")
    return out, notes


def surface_records(res: Any, o: dict[str, Any], fus: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Superfícies sustentadoras: asa (caixão existente) e empenagens (caminho da asa). Cada registo leva a
    posição de encastramento e o eixo da envergadura para a tabela de membros e o modelo de vigas."""
    recs: list[dict[str, Any]] = []
    x_w = float(fus.get("x_wing_m") or 0.35 * res.config.fuselage.length)
    wb = wing_box_summary(res)
    recs.append({"comp": "asa", "box": wb, "x": x_w, "y0": 0.0, "z0": 0.0, "axis": "y", "mirror": True,
                 "source": "structures.box (existente)"})
    tb, notes = tail_boxes(res, o)
    meth = str((o.get("tails") or {}).get("method", "buckling"))
    src = ("structures_l1 cargas + structures.box_beam_sizing_buckling + secção Fase 5" if meth == "buckling"
           else "structures_l1.tails (existente)")
    recs.append({"comp": "estabilizador", "box": tb.get("htail"), "x": float(fus.get("x_ht_m") or 0.0), "y0": 0.0,
                 "z0": 0.0, "axis": "y", "mirror": True, "source": src})
    recs.append({"comp": "deriva", "box": tb.get("vtail"), "x": float(fus.get("x_vt_m") or 0.0), "y0": 0.0,
                 "z0": 0.0, "axis": "z", "mirror": False, "source": src})
    return recs, notes


def surface_members(rec: dict[str, Any]) -> list[dict[str, Any]]:
    if rec["box"] is None:
        return [member(f"{rec['comp']}.caixao", rec["comp"], "caixao", None, rec["x"], verdict="desconhecido",
                       method="caixão em falta", source=rec["source"])]
    return box_members(rec["comp"], rec["box"], rec["x"], rec["y0"], rec["z0"], rec["axis"], rec["mirror"],
                       rec["source"])


# ------------------------------------------------------------------------------------------------ fuselage
def _xpos(d: dict[str, Any], L: float) -> float | None:
    if d.get("x_m") is not None:
        return float(d["x_m"])
    if d.get("x_frac") is not None:
        return float(d["x_frac"]) * L
    return None


def _split(F: float, thetas: list[float], comp: str = "Fz") -> list[fr.RingLoad]:
    n = max(len(thetas), 1)
    return [fr.RingLoad(float(t), **{comp: F / n}) for t in thetas]


def auto_frame_loads(fus: dict[str, Any], o: dict[str, Any], wing: Any, n_lim: float = 0.0) -> tuple[dict[str, list[tuple[float, str, list[fr.RingLoad]]]],
                                                         list[str]]:
    """Cargas LIMITE concentradas por caso: {caso: [(x, id, [RingLoad])]} a partir da viga-fuselagem L1."""
    f = o["fuselage"]
    notes: list[str] = []
    cases: dict[str, list[Any]] = {"manobra": [], "aterragem": []}
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


def _user_loads(o: dict[str, Any], L: float, n_lim: float, n_land: float) -> tuple[dict[str, list[Any]], list[str]]:
    f = o["fuselage"]
    cases: dict[str, list[Any]] = {}
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
                 frame_loads: dict[str, list[Any]], bulkheads: list[dict[str, Any]], fo: dict[str, Any], mat: dict[str, Any], nonopt: float,
                 y0: float = 0.0, z0: float = 0.0, x_off: float = 0.0) -> dict[str, Any]:
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
            ids_ = special.setdefault(round(float(xx), 4), [])
            if lid not in ids_:
                ids_.append(lid)
    for bk in bulkheads:
        special.setdefault(round(float(bk["x_m"]), 4), []).append(str(bk["id"]))
    reg = [float(v) for v in np.arange(x[0], x[-1] + 1e-9, pitch)]
    st_x = sorted(set([v for v in reg if all(abs(v - s) > 0.3 * pitch for s in special)] + list(special)))
    st_x = [v for v in st_x if x[0] - 1e-9 <= v <= x[-1] + 1e-9]
    rows: list[dict[str, Any]] = []
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
        chk: dict[str, Any] = {}
        worst = None
        loop: dict[str, Any] = dict(cases_here) if cases_here else {"_": None}
        for case, ring in loop.items():
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


def fuselage_layout(res: Any, o: dict[str, Any], mat: dict[str, Any]) -> dict[str, Any]:
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
    cases: dict[str, list[Any]] = {}
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


def _boom_loads_integrate(s: np.ndarray, xa: float, pts: list[tuple[float, float, float, float]]
                          ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Duas consolas a partir da ligação ``xa``: cargas atrás de xa fletem a parte de trás, à frente a da frente.
    ``pts`` = [(p, Fz, Fy, T)] (p relativo ao início do boom), somadas com sinal por plano (z, y) e combinadas
    vetorialmente; na própria ligação fica o maior dos dois lados (cada consola descarrega na ferragem).
    Devolve |V|, |M|, |T| por estação."""
    acc = {side: [np.zeros_like(s) for _ in range(5)] for side in ("tras", "frente")}
    for p, Fz, Fy, Tq in pts:
        side = "tras" if p >= xa else "frente"
        on = ((s >= xa) & (s <= p)) if side == "tras" else ((s <= xa) & (s >= p))
        arm = np.abs(p - s)
        Vz, Mz, Vy, My, T = acc[side]
        Vz += np.where(on, Fz, 0.0)
        Mz += np.where(on, Fz * arm, 0.0)
        Vy += np.where(on, Fy, 0.0)
        My += np.where(on, Fy * arm, 0.0)
        T += np.where(on, Tq, 0.0)
    res = []
    for k in range(3):
        if k == 2:
            a_, f_ = np.abs(acc["tras"][4]), np.abs(acc["frente"][4])
        else:
            a_ = np.hypot(acc["tras"][k], acc["tras"][k + 2])          # (Vz, Vy) ou (Mz, My)
            f_ = np.hypot(acc["frente"][k], acc["frente"][k + 2])
        res.append(np.where(s > xa, a_, np.where(s < xa, f_, np.maximum(a_, f_))))
    return res[0], res[1], res[2]


def boom_layout(bd: dict[str, Any], o: dict[str, Any], mat: dict[str, Any], nonopt: float) -> dict[str, Any]:
    """Boom (corpo tubular) ligado à asa em ``x_attach_m`` (omissão: início do boom), com cargas LIMITE pontuais
    (cauda, rotor, trem — ``loads: [{id, x_m, Fz_N, Fy_N, T_Nm}]``, x global): duas consolas a partir da ligação."""
    bid = str(bd.get("id") or "boom")
    try:
        x0, Lb, D = float(bd["x0_m"]), float(bd["length_m"]), float(bd["diameter_m"])
    except (KeyError, TypeError, ValueError):
        return {"evaluated": False, "reason": f"{bid}: falta x0_m/length_m/diameter_m", "members": []}
    loads = bd.get("loads") or []
    if not loads:
        return {"evaluated": False, "reason": f"{bid}: sem cargas declaradas — desconhecido", "members": []}
    xa_raw = bd.get("x_attach_m")
    xa = min(max((x0 if xa_raw is None else float(xa_raw)) - x0, 0.0), Lb)
    s = np.linspace(0.0, Lb, 41)
    pts = [(float(ld["x_m"]) - x0, float(ld.get("Fz_N") or 0.0), float(ld.get("Fy_N") or 0.0),
            float(ld.get("T_Nm") or 0.0)) for ld in loads]
    s = np.unique(np.concatenate([s, [p for p, *_r in pts if 0 <= p <= Lb], [xa]]))
    cases = [str(ld.get("case") or "limite") for ld in loads]
    V = np.zeros_like(s)
    M = np.zeros_like(s)
    T = np.zeros_like(s)
    fl: dict[str, list[Any]] = {}
    for c in dict.fromkeys(cases):       # envolvente dos casos (cada caso com as suas cargas em simultâneo)
        sel = [pt for pt, ci in zip(pts, cases) if ci == c]
        Vc, Mc, Tc = _boom_loads_integrate(s, xa, sel)
        V, M, T = np.maximum(V, Vc), np.maximum(M, Mc), np.maximum(T, Tc)
        fl[c] = []
    for ld, (p, Fz, Fy, Tq), c in zip(loads, pts, cases):
        fl[c].append((min(max(p, 0.0), Lb), str(ld.get("id") or "carga"),
                      [fr.RingLoad(180.0, Fy=Fy, Fz=Fz)] + ([fr.RingLoad(0.0, M=Tq)] if Tq else [])))
    fo = _merge(DEFAULTS["fuselage"], {k: v for k, v in bd.items() if k in DEFAULTS["fuselage"]})
    fo["frame_pitch_m"] = fo.get("frame_pitch_m") or 0.3
    if fo["stringers"].get("n") is None:
        fo["stringers"]["n"] = max(4, math.ceil(math.pi * D / float(fo["stringers"].get("pitch_m") or 0.12)))
    if fo["longerons"].get("n") is None:
        fo["longerons"]["n"] = 0
    R = np.full_like(s, D / 2)
    bks = [{"id": "ligacao", "x_m": xa, "pressure_Pa": 0.0}]
    out = analyse_body(bid, s, R, M, V, T, fl, bks, fo, mat, nonopt, float(bd.get("y_m") or 0.0),
                       float(bd.get("z_m") or 0.0), x0)
    out["evaluated"] = True
    out["notes"] = [f"cargas do boom LIMITE ({', '.join(str(ld.get('id')) for ld in loads)}); consolas a partir da "
                    f"ligação x = {xa + x0:.3f} m; casca circular de diâmetro equivalente {D:.3f} m (PRESSUPOSTO)"]
    out["root_moment_limit_Nm"] = float(np.max(M))
    out["geometry"] = {"x0_m": x0, "length_m": Lb, "diameter_m": D, "x_attach_m": xa + x0,
                       "y_m": float(bd.get("y_m") or 0.0), "z_m": float(bd.get("z_m") or 0.0)}
    return out


_ROTOR_WORDS = ("rotor", "lift", "elevac", "vtol")


def booms_from_assembly(asm_spec: dict[str, Any] | None, W0_kg: float, tails: dict[str, Any], o: dict[str, Any],
                        x_attach: float | None) -> tuple[list[dict[str, Any]], list[str]]:
    """Booms da geometria de montagem (``assembly``): corpos com papel «boom» (as imagens espelhadas contam como
    booms separados), com as cargas que lá se apoiam:

    * empenagens (superfícies cujo papel contém «tail»/«cauda»/«empenagem») na extensão do boom mais próximo:
      sustentação de projeto do estabilizador e da deriva da L1 repartida igualmente pelos booms que levam cauda
      (PRESSUPOSTO; uma cauda em V/V invertido entra com as superfícies equivalentes da L1), mais a torção L_deriva ×
      0,4 × semienvergadura da deriva (o mesmo braço da L1, PRESSUPOSTO);
    * rotores de elevação (discos cujo papel contém rotor/lift; hélices de propulsão excluídas): T_lim =
      ``rotor_thrust_factor`` × W0 g / n_rotores (fator PRESSUPOSTO, 1,5 por omissão — declarar o do projeto);
      o binário de reação do rotor não é conhecido aqui e fica fora (desconhecido, listado).

    Eixo dos booms paralelo a x (PRESSUPOSTO). Ligação à asa em ``x_attach`` (centro aerodinâmico da asa)."""
    notes: list[str] = []
    if not asm_spec:
        return [], notes
    from .assembly.assembly import Assembly
    from .assembly.components import Body, Disc, Surface
    try:
        asm = Assembly.from_dict(asm_spec.get("assembly", asm_spec))
    except Exception as ex:  # noqa: BLE001
        return [], [f"montagem ilegível para booms: {type(ex).__name__}: {ex}"]
    booms: list[dict[str, Any]] = []
    for c in asm.components:
        if isinstance(c, Body) and "boom" in (c.role or "").lower():
            st = c.stations
            xs = [float(s_["x"]) for s_ in st]
            D = max(math.sqrt(float(s_["w"]) * float(s_.get("h") or s_["w"])) for s_ in st)
            ox, oy, oz = (float(v) for v in c.origin)
            if c.mirrored_image:
                oy = -oy
            booms.append({"id": c.name, "x0_m": ox + min(xs), "length_m": max(xs) - min(xs), "diameter_m": D,
                          "y_m": oy, "z_m": oz, "loads": [],
                          "x_attach_m": x_attach if x_attach is not None else ox + min(xs)})
    if not booms:
        return [], notes

    def nearest(x: float, y: float, z: float, margin: float = 0.5) -> dict[str, Any] | None:
        best, dbest = None, math.inf
        for b in booms:
            if b["x0_m"] - margin <= x <= b["x0_m"] + b["length_m"] + margin:
                d = math.hypot(y - b["y_m"], z - b["z_m"])
                if d < dbest:
                    best, dbest = b, d
        return best

    tail_hits: list[tuple[dict[str, Any], float]] = []
    for c in asm.components:
        role = (c.role or "").lower()
        if isinstance(c, Surface) and any(w in role for w in ("tail", "cauda", "empenagem")):
            ox, oy, oz = (float(v) for v in c.origin)
            if c.mirrored_image:
                oy = -oy
            b = nearest(ox, oy, oz)
            if b is not None and b not in [t[0] for t in tail_hits]:
                tail_hits.append((b, ox))
    if tail_hits:
        L_ht = float(tails.get("htail_limit_lift_N") or 0.0)
        L_vt = float(tails.get("vtail_limit_lift_N") or 0.0)
        vb = tails.get("vtail_box") or {}
        z_cp = 0.4 * float(vb.get("semispan_m") or 0.0)
        n = len(tail_hits)
        for b, x in tail_hits:
            b["loads"].append({"id": "cauda", "kind": "tail", "case": "voo_cauda", "x_m": min(x, b["x0_m"] + b["length_m"]),
                               "Fz_N": -L_ht / n, "Fy_N": L_vt / n, "T_Nm": L_vt / n * z_cp})
        notes.append(f"cauda nos booms: L_estab {L_ht:.0f} N e L_deriva {L_vt:.0f} N (L1) repartidas por {n} booms "
                     "— PRESSUPOSTO")
    rotors = [c for c in asm.components if isinstance(c, Disc)
              and any(w in (c.role or "").lower() for w in _ROTOR_WORDS) and "propul" not in (c.role or "").lower()]
    if rotors:
        k = float(o.get("rotor_thrust_factor") or 1.5)
        T = k * W0_kg * G0 / len(rotors)
        for c in rotors:
            ox, oy, oz = (float(v) for v in c.origin)
            if c.mirrored_image:
                oy = -oy
            b = nearest(ox, oy, oz)
            if b is None:
                notes.append(f"rotor {c.name}: sem boom próximo — carga não atribuída (desconhecida)")
                continue
            b["loads"].append({"id": f"rotor:{c.name}", "kind": "rotor", "case": "pairar_rotores", "x_m": min(max(ox, b["x0_m"]),
                                                                                b["x0_m"] + b["length_m"]),
                               "Fz_N": T, "Fy_N": 0.0, "T_Nm": 0.0})
        notes.append(f"rotores de elevação: {len(rotors)} × T_lim = {k:g} × W0 g / n = {T:.0f} N (fator PRESSUPOSTO); "
                     "binário de reação dos rotores não modelado (desconhecido)")
    return booms, notes


# ------------------------------------------------------------------------------------------------ beam model
def beam_model(mat: dict[str, Any], bodies: list[dict[str, Any]], surfaces: list[dict[str, Any]],
               members: list[dict[str, Any]]) -> dict[str, Any]:
    """Modelo de vigas neutro ``acdt.beam/1`` do avião inteiro: corpos (fuselagem, booms: eixo x a (y0, z0)) e
    superfícies (asa/estabilizador em ±y, deriva em +z) com EI/GJ por estação; cada superfície liga ao nó de corpo
    mais próximo da sua raiz (ou cria um). Massas concentradas no nó mais próximo; barras sem massa."""
    nodes: list[dict[str, Any]] = []
    elems: list[dict[str, Any]] = []
    E, G = mat["E"], mat["G"]

    def node(x: float, y: float, z: float) -> int:
        nodes.append({"id": len(nodes) + 1, "xyz": [x, y, z]})
        return len(nodes)

    missing: list[str] = []
    body_nodes: list[int] = []
    owner: dict[int, str] = {}
    attach: list[tuple[str, list[int], float, dict[str, Any]]] = []
    for bd in bodies:
        bm = bd.get("beam")
        if not bm or not bm.get("x"):
            missing.append(str(bd["comp"]))
            continue
        ids = [node(float(x), float(bd.get("y0", 0.0)), float(bd.get("z0", 0.0))) for x in bm["x"]]
        if bd.get("attach_x") is not None and body_nodes:
            attach.append((str(bd["comp"]), ids, float(bd["attach_x"]), bm))   # boom: liga depois à asa
        else:
            body_nodes += ids
        owner.update({i: str(bd["comp"]) for i in ids})
        for k in range(len(ids) - 1):
            Iav = 0.5 * (bm["I"][k] + bm["I"][k + 1])
            elems.append({"id": len(elems) + 1, "component": bd["comp"], "nodes": [ids[k], ids[k + 1]],
                          "A": 0.5 * (bm["A"][k] + bm["A"][k + 1]), "I1": Iav, "I2": Iav,
                          "J": 0.5 * (bm["J"][k] + bm["J"][k + 1])})
    for sf in surfaces:
        bx = sf.get("box")
        if not bx or not bx.get("EI") or not bx.get("GJ"):
            missing.append(f"{sf['comp']} (EI/GJ do caixão)")
            continue
        xr, yr, zr = float(sf["x"]), float(sf.get("y0", 0.0)), float(sf.get("z0", 0.0))
        cand = body_nodes + [i for _c, ids_b, _x, _b in attach for i in ids_b]
        if cand:
            d = [math.dist(nodes[i - 1]["xyz"], [xr, yr, zr]) for i in cand]
            root = cand[int(np.argmin(d))]
        else:
            root = node(xr, yr, zr)
        for side in ((1.0, -1.0) if sf.get("mirror", True) else (1.0,)):
            prev = root
            for k, s_ in enumerate(bx["y"]):
                if s_ <= 1e-9:
                    continue
                pos = [xr, yr + side * float(s_), zr] if sf.get("axis", "y") == "y" else [xr, yr, zr + float(s_)]
                nid = node(*pos)
                EI = 0.5 * (bx["EI"][k - 1] + bx["EI"][k])
                GJ = 0.5 * (bx["GJ"][k - 1] + bx["GJ"][k])
                elems.append({"id": len(elems) + 1, "component": sf["comp"], "nodes": [prev, nid], "A": 1e-4,
                              "I1": EI / E, "I2": 10 * EI / E, "J": GJ / G})
                owner[nid] = str(sf["comp"])
                prev = nid
    for comp, ids, xa, bm in attach:   # ligação rígida do boom ao nó mais próximo de outro componente
        k = int(np.argmin([abs(nodes[i - 1]["xyz"][0] - xa) for i in ids]))
        others = [i for i in owner if owner[i] != comp and i not in ids]
        if not others:
            missing.append(f"{comp}: sem nó de ligação")
            continue
        j = others[int(np.argmin([math.dist(nodes[i - 1]["xyz"], nodes[ids[k] - 1]["xyz"]) for i in others]))]
        elems.append({"id": len(elems) + 1, "component": f"ligacao:{comp}", "nodes": [j, ids[k]],
                      "A": 10 * max(bm["A"]), "I1": 10 * max(bm["I"]), "I2": 10 * max(bm["I"]),
                      "J": 10 * max(bm["J"])})
    masses = []
    for m in members:
        if not nodes or m["mass_kg"] is None or m["mass_kg"] <= 0:
            continue
        p = [m["x_m"], m["y_m"], m["z_m"]]
        nid = int(np.argmin([math.dist(n["xyz"], p) for n in nodes])) + 1
        masses.append({"node": nid, "mass_kg": m["mass_kg"], "member": m["id"]})
    return {"format": "acdt.beam/1", "units": "SI (m, N, kg, Pa)",
            "material": {"id": 1, "E": E, "G": G, "nu": mat["nu"], "rho": 0.0, "source": mat["source"]},
            "nodes": nodes, "elements": elems, "point_masses": masses, "missing": missing,
            "note": "barras sem massa (ρ = 0): a massa estrutural entra só como massas concentradas no nó mais próximo; "
                    "nas superfícies A simbólica (1e-4 m²), I1 = EI/E (flexão para fora do plano), I2 = 10 I1 "
                    "(rigidez no plano — PRESSUPOSTO), J = GJ/G; a raiz de cada superfície partilha o nó de corpo mais "
                    "próximo (ligação rígida — PRESSUPOSTO); cada boom liga ao nó mais próximo de outro componente na estação "
                    "de ligação por um elemento 10× mais rígido que o boom (PRESSUPOSTO). Para análise externa (p. ex. CalculiX via Build)."}


def _f8(v: float) -> str:
    s = f"{v:.6g}"
    if len(s) > 8:
        s = f"{v:.2e}"
    return s[:8].ljust(8)


def to_nastran(model: dict[str, Any]) -> str:
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
def _assembly_spec(res: Any) -> dict[str, Any] | None:
    a = res.spec.assumptions.get("assembly") if isinstance(res.spec.assumptions, dict) else None
    if not a:
        return None
    lp = getattr(res, "assembly_loop", None)
    if lp and lp.get("spec_scaled"):
        return dict(lp["spec_scaled"])
    from .assembly.loop import load_spec
    return dict(load_spec(res.spec, a))


def analyse_layout(res: Any) -> dict[str, Any]:
    o = options(res.spec)
    mkey = _material_key(res, o)
    mat = material_dict(mkey)
    notes: list[str] = []
    members: list[dict[str, Any]] = []
    fus: dict[str, Any] = (fuselage_layout(res, o, mat) if o["fuselage"].get("enabled", True)
                           else {"evaluated": False, "reason": "desligada"})
    l1 = getattr(res, "structures_l1", None)
    fus_l1 = (getattr(l1, "fuselage", None) or {}) if l1 is not None else {}
    recs, n_s = surface_records(res, o, fus_l1)
    notes += n_s
    for rec in recs:
        members += surface_members(rec)
    if fus.get("evaluated"):
        members += fus["members"]
    else:
        members.append(member("fuselagem", "fuselagem", "casca", None, 0.0, verdict="desconhecido",
                              method=str(fus.get("reason"))))
    nonopt = float(res.spec.assumptions["structures"].get("nonoptimum_factor", 1.25))
    boom_defs = list(o.get("booms") or [])
    if o.get("booms_from_assembly", True):
        try:
            ab, n_b = booms_from_assembly(_assembly_spec(res), float(res.sizing.W0),
                                          (getattr(l1, "tails", None) or {}) if l1 is not None else {}, o,
                                          fus_l1.get("x_wing_m"))
        except Exception as ex:  # noqa: BLE001 — booms da montagem ficam desconhecidos, com a razão
            ab, n_b = [], [f"booms da montagem não lidos: {type(ex).__name__}: {ex}"]
        user_ids = {str(b.get("id")) for b in boom_defs}
        boom_defs += [b for b in ab if b["id"] not in user_ids]
        notes += n_b
    booms = []
    bodies = [{"comp": "fuselagem", "beam": fus.get("beam") if fus.get("evaluated") else None}]
    for bd in boom_defs:
        b = boom_layout(bd, o, mat, nonopt)
        booms.append({k: v for k, v in b.items() if k not in ("members", "shell_table")})
        if b.get("evaluated"):
            members += b["members"]
            bodies.append({"comp": b["members"][0]["component"], "beam": b["beam"],
                           "y0": b["geometry"]["y_m"], "z0": b["geometry"]["z_m"],
                           "attach_x": b["geometry"]["x_attach_m"]})
        else:
            members.append(member(str(bd.get("id") or "boom"), str(bd.get("id") or "boom"), "boom", None,
                                  float(bd.get("x0_m") or 0.0), float(bd.get("y_m") or 0.0),
                                  float(bd.get("z_m") or 0.0), verdict="desconhecido", method=str(b.get("reason"))))
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
                           "booms": booms, "notes": notes,
                           "surfaces": {r["comp"]: None if r["box"] is None else
                                        {"mass_kg": r["box"]["masses"].get("total"), "method": r["box"].get("method"),
                                         "section": r["box"].get("section"), "buckling_ok": r["box"].get("buckling_ok"),
                                         "source": r["source"]} for r in recs}}
    if o["coupling"] == "iterar":
        notes.append("acoplamento iterar ainda não implementado: resultado relatado, não aplicado ao dimensionamento")
    if l1 is not None and fus.get("evaluated"):
        fm = bud["by_component_kg"].get("fuselagem")
        out["comparison"] = {"fuselage_layout_kg": fm, "fuselage_L1_kg": l1.masses.get("fuselage_kg"),
                             "fuselage_raymer_kg": l1.masses.get("fuselage_raymer_kg"),
                             "wing_box_kg": l1.masses.get("wing_box_kg"),
                             "htail_layout_kg": bud["by_component_kg"].get("estabilizador"),
                             "htail_L1_kg": l1.masses.get("htail_kg"),
                             "vtail_layout_kg": bud["by_component_kg"].get("deriva"),
                             "vtail_L1_kg": l1.masses.get("vtail_kg")}
    if o.get("export", {}).get("beam_model", True):
        out["beam_model"] = beam_model(mat, bodies, recs, members)
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
