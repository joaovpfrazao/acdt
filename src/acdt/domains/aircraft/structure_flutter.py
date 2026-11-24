# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Flutter do avião inteiro a partir do modelo de vigas da estrutura paramétrica (incremento E).

Liga o modelo ``acdt.beam/1`` de :mod:`.structure_layout` ao modelo aeroelástico de baixa fidelidade de
:mod:`.aeroelasticity` (Wright & Cooper 2015, cap. 11, aerodinâmica quase-estacionária em faixas):

1. **Modos** — elementos finitos de viga 3-D de Euler–Bernoulli (12 GL por elemento; Przemieniecki, *Theory of
   Matrix Structural Analysis*, 1968, cap. 5), massas concentradas nos nós com excentricidade (massa da faixa no
   CG da secção, fora do eixo elástico) e inércia de rotação c²/12 da faixa; problema livre-livre K φ = ω² M φ.
   Os 6 modos de corpo rígido são retirados (PRESSUPOSTO: flutter de corpo livre fora do âmbito).
2. **Aerodinâmica** — por faixa das superfícies (asa, estabilizador, deriva), a mesma forma quase-estacionária
   de :func:`.aeroelasticity.flutter_matrices`: L' = q c a_w (θ − ḣ/V), M'_ea = e c L' + q c² M_θ̇ θ̇ c/(4V),
   projetada nos modos elásticos (método dos modos assumidos com os modos do modelo de vigas).
3. **Varrimento em V (EAS, ρ0)** dos valores próprios de [[0, I], [−K + A_K, A_D]] (massa modal unitária);
   flutter na primeira V com parte real positiva de uma raiz oscilatória; divergência numa raiz real positiva.

Requisito: livre de flutter até 1,2 V_D (14 CFR 23.629 legado; ESTIMATIVA — a certificação pede ensaio/análise
de alta fidelidade, ver :mod:`.hifi.flutter`). Massa: as superfícies levam a massa do build-up (como em
:mod:`.aeroelasticity`) ∝ corda; o resto do W0 vai para os nós dos corpos ∝ massa estrutural local (PRESSUPOSTO).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.linalg import eigh

from .aeroelasticity import M_THETADOT, WRIGHT_COOPER

PRZEMIENIECKI = "Przemieniecki, Theory of Matrix Structural Analysis, 1968, cap. 5"
SURFACE_AXIS = {"asa": ("y", "z"), "estabilizador": ("y", "z"), "deriva": ("z", "y")}   # (envergadura, normal)
_IDX = {"x": 0, "y": 1, "z": 2}


def _skew(r: np.ndarray) -> np.ndarray:
    out: np.ndarray = np.array([[0.0, -r[2], r[1]], [r[2], 0.0, -r[0]], [-r[1], r[0], 0.0]], float)
    return out


def frame_element_k(p1: np.ndarray, p2: np.ndarray, E: float, G: float, A: float, Iy: float, Iz: float, J: float,
                    v_ref: np.ndarray) -> np.ndarray:
    """Matriz de rigidez 12×12 global de um elemento de pórtico 3-D (Przemieniecki cap. 5). Eixo local x = p1→p2;
    z local = componente de ``v_ref`` normal ao eixo; Iy rege a flexão com deslocamento segundo z local."""
    d = p2 - p1
    L = float(np.linalg.norm(d))
    ex = d / L
    ez = v_ref - np.dot(v_ref, ex) * ex
    ez = ez / np.linalg.norm(ez)
    ey = np.cross(ez, ex)
    k = np.zeros((12, 12))
    a, t = E * A / L, G * J / L
    k[0, 0] = k[6, 6] = a
    k[0, 6] = k[6, 0] = -a
    k[3, 3] = k[9, 9] = t
    k[3, 9] = k[9, 3] = -t
    for (v, th, I, s) in ((1, 5, Iz, 1.0), (2, 4, Iy, -1.0)):
        c1, c2, c3, c4 = 12 * E * I / L**3, 6 * E * I / L**2, 4 * E * I / L, 2 * E * I / L
        k[v, v] = k[v + 6, v + 6] = c1
        k[v, v + 6] = k[v + 6, v] = -c1
        k[v, th] = k[th, v] = s * c2
        k[v, th + 6] = k[th + 6, v] = s * c2
        k[v + 6, th] = k[th, v + 6] = -s * c2
        k[v + 6, th + 6] = k[th + 6, v + 6] = -s * c2
        k[th, th] = k[th + 6, th + 6] = c3
        k[th, th + 6] = k[th + 6, th] = c4
    R = np.vstack([ex, ey, ez])
    T = np.zeros((12, 12))
    for i in range(4):
        T[3 * i:3 * i + 3, 3 * i:3 * i + 3] = R
    kg: np.ndarray = T.T @ k @ T
    return kg


def point_mass_matrix(m: float, r: np.ndarray, J: np.ndarray) -> np.ndarray:
    """6×6 de uma massa m com CG a r do nó e inércia própria J (em torno do CG): energia cinética de
    u + θ × r (corpo rígido)."""
    S = _skew(r)
    M = np.zeros((6, 6))
    M[:3, :3] = m * np.eye(3)
    M[:3, 3:] = -m * S
    M[3:, :3] = m * S
    M[3:, 3:] = J - m * S @ S
    return M


def _v_ref(ex: np.ndarray) -> np.ndarray:
    # superfícies na envergadura y → normal z; deriva (eixo z) → normal y; corpos (eixo x) → z
    if abs(ex[1]) > 0.7:
        return np.array([0.0, 0.0, 1.0])
    if abs(ex[2]) > 0.7:
        return np.array([0.0, 1.0, 0.0])
    return np.array([0.0, 0.0, 1.0])


def assemble(model: dict[str, Any], node_mass: dict[int, np.ndarray], fixed: list[int] | None = None
             ) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """K e M globais (6 GL por nó, ordem dos ids dos nós). ``node_mass``: {id do nó: matriz 6×6}. Nós sem massa
    levam um piso de 1e-3 kg e 1e-5 kg m² (M definida positiva e bem condicionada). ``fixed``: nós encastrados (testes). Nas superfícies
    a área simbólica do modelo neutro (1e-4 m²) dá modos axiais espúrios: aqui A = 1 m² (axialmente rígidas)."""
    E, G = model["material"]["E"], model["material"]["G"]
    ids = [n["id"] for n in model["nodes"]]
    pos = {n["id"]: np.asarray(n["xyz"], float) for n in model["nodes"]}
    ix = {i: k for k, i in enumerate(ids)}
    N = 6 * len(ids)
    K = np.zeros((N, N))
    M = np.zeros((N, N))
    for e in model["elements"]:
        a, b = e["nodes"]
        p1, p2 = pos[a], pos[b]
        if np.linalg.norm(p2 - p1) < 1e-9:
            continue
        A_e = 1.0 if e["component"] in SURFACE_AXIS else e["A"]   # superfícies: axialmente rígidas
        ke = frame_element_k(p1, p2, E, G, A_e, e["I1"], e["I2"], e["J"], _v_ref((p2 - p1) / np.linalg.norm(p2 - p1)))
        dofs = [6 * ix[a] + i for i in range(6)] + [6 * ix[b] + i for i in range(6)]
        K[np.ix_(dofs, dofs)] += ke
    for i in ids:
        d = slice(6 * ix[i], 6 * ix[i] + 6)
        M[d, d] += node_mass.get(i, np.zeros((6, 6)))
        # piso de massa 1 g / 1e-5 kg m² por nó: com 1e-6 kg o problema generalizado ficava mal condicionado
        # (elementos curtos, K até 1e15) e o eigh devolvia modos repetidos espúrios
        M[d, d] += np.diag([1e-3] * 3 + [1e-5] * 3)
    keep = list(range(N))
    if fixed:
        drop = {6 * ix[i] + j for i in fixed for j in range(6)}
        keep = [k for k in keep if k not in drop]
    return K, M, keep


def modes(K: np.ndarray, M: np.ndarray, keep: list[int], n: int, rigid: int) -> tuple[np.ndarray, np.ndarray]:
    """Primeiros n modos elásticos (retira ``rigid`` modos de corpo rígido). Massa modal unitária."""
    Kk, Mk = K[np.ix_(keep, keep)], M[np.ix_(keep, keep)]
    hi = min(rigid + n, len(keep)) - 1
    w2, ph = eigh(Kk, Mk, subset_by_index=[0, hi])
    full = np.zeros((K.shape[0], ph.shape[1]))
    full[keep, :] = ph
    return np.sqrt(np.maximum(w2[rigid:], 0.0)), full[:, rigid:]


def _normal(span: np.ndarray) -> np.ndarray:
    """Normal da superfície: x × ŝ (ŝ sem a componente em x), orientada para +z (ou +y numa deriva vertical)."""
    sp = np.array([0.0, span[1], span[2]])
    n = np.cross(np.array([1.0, 0.0, 0.0]), sp)
    nn = float(np.linalg.norm(n))
    if nn < 1e-12:
        return np.array([0.0, 0.0, 1.0])
    n = n / nn
    if n[2] < -1e-9 or (abs(n[2]) <= 1e-9 and n[1] < 0):
        n = -n
    return n


def strips(model: dict[str, Any], surf: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Faixas aerodinâmicas: uma por nó de superfície (exceto a raiz), largura tributária medida na envergadura
    (distância entre nós sem a componente em x), corda c(η) linear raiz→ponta de cada ramo, componente, vetor da
    envergadura ``s_vec`` e normal ``n_vec`` (diedro, cauda em V e derivas em qualquer posição)."""
    pos = {n["id"]: np.asarray(n["xyz"], float) for n in model["nodes"]}
    out: list[dict[str, Any]] = []
    for comp, sd in surf.items():
        els = [e for e in model["elements"] if e["component"] == comp]
        # nós de cada ramo pela ordem dos elementos (raiz → ponta)
        chains: list[list[int]] = []
        for e in els:
            a, b = e["nodes"]
            for ch in chains:
                if ch[-1] == a:
                    ch.append(b)
                    break
            else:
                chains.append([a, b])
        for ch in chains:
            P = np.array([pos[i] for i in ch])
            dP = np.diff(P, axis=0)
            seg = np.hypot(dP[:, 1], dP[:, 2])
            s = np.concatenate([[0.0], np.cumsum(seg)])
            L = float(s[-1]) or 1.0
            sv = P[-1] - P[0]
            sv = sv / (float(np.linalg.norm(sv)) or 1.0)
            n = _normal(sv)
            for k in range(1, len(ch)):
                lo = 0.5 * (s[k] - s[k - 1])
                hi = 0.5 * (s[k + 1] - s[k]) if k + 1 < len(ch) else 0.0
                c = float(sd["c_root"] + (sd["c_tip"] - sd["c_root"]) * min(s[k] / L, 1.0))
                out.append({"node": ch[k], "comp": comp, "ds": lo + hi, "c": c, "s_vec": sv, "n_vec": n,
                            "e": float(sd["e"]), "x_cg_off": float(sd["x_cg_off"]),
                            "a_w": float(sd["a_w"]), "m_per_c": float(sd["m_per_c"])})
    return out


def strip_masses(strip_list: list[dict[str, Any]]) -> dict[int, np.ndarray]:
    """Massa de cada faixa m = (m/c) c ds no CG da secção (x_cg_off c atrás do eixo elástico), inércia própria
    m c²/12 em torno do eixo da envergadura (secção uniforme — Wright & Cooper cap. 11)."""
    out: dict[int, np.ndarray] = {}
    for st in strip_list:
        m = st["m_per_c"] * st["c"] * st["ds"]
        r = np.array([st["x_cg_off"] * st["c"], 0.0, 0.0])
        sv = np.asarray(st["s_vec"], float)
        J = m * st["c"] ** 2 / 12 * np.outer(sv, sv)
        out[st["node"]] = out.get(st["node"], np.zeros((6, 6))) + point_mass_matrix(m, r, J)
    return out


def aero_matrices(strip_list: list[dict[str, Any]], phi: np.ndarray, node_ix: dict[int, int],
                  M_thetadot: float = M_THETADOT) -> tuple[np.ndarray, np.ndarray]:
    """Matrizes aerodinâmicas generalizadas por unidade de q (A_K) e de q/V (A_D): Q = q A_K η + (q/V) A_D η̇.
    h = deslocamento segundo a normal n; arfagem positiva = bordo de ataque para o lado da normal, rotação em
    torno de n × x (asa: +y; deriva com normal +y: −z)."""
    n = phi.shape[1]
    AK, AD = np.zeros((n, n)), np.zeros((n, n))
    ex = np.array([1.0, 0.0, 0.0])
    for st in strip_list:
        k0 = 6 * node_ix[st["node"]]
        nv = np.asarray(st["n_vec"], float)
        pv = np.cross(nv, ex)
        h = nv @ phi[k0:k0 + 3, :]
        th = pv @ phi[k0 + 3:k0 + 6, :]
        c, ds, a, e = st["c"], st["ds"], st["a_w"], st["e"]
        # L' = q c a (θ − ḣ/V) ; M' = e c L' + q c² M_θ̇ c θ̇ /(4V)
        AK += ds * (np.outer(h, c * a * th) + np.outer(th, e * c**2 * a * th))
        AD += ds * (-np.outer(h, c * a * h) - np.outer(th, e * c**2 * a * h)
                    + np.outer(th, c**3 * M_thetadot / 4 * th))
    return AK, AD


def flutter_sweep(omega: np.ndarray, AK: np.ndarray, AD: np.ndarray, rho: float, V_max: float, n: int = 400
                  ) -> dict[str, Any]:
    """Valores próprios de q̈ = (−Ω² + ½ρV² A_K) q + ½ρV A_D q̇ em V ∈ (0, V_max]; o cruzamento do amortecimento
    é refinado por bisseção. g = −ζ máximo das raízes oscilatórias; modos sem acoplamento aerodinâmico (p. ex.
    flexão no plano) têm ζ = 0 exato e só ruído numérico → limiar 1e-6."""
    m = len(omega)
    Om = np.diag(omega**2)

    def eig(V: float) -> np.ndarray:
        q = 0.5 * rho * V**2
        A = np.block([[np.zeros((m, m)), np.eye(m)], [-Om + q * AK, (q / V) * AD]])
        return np.linalg.eigvals(A)

    def g_of(lam: np.ndarray) -> tuple[float, float]:
        osc = lam[np.abs(lam.imag) > 1e-6]
        if not osc.size:
            return -math.inf, math.nan
        r = osc.real / np.abs(osc)
        k = int(np.argmax(r))
        return float(r[k]), float(abs(osc[k].imag) / (2 * math.pi))

    def div_of(lam: np.ndarray) -> bool:
        real = lam[np.abs(lam.imag) <= 1e-6]
        return bool(real.size and np.any(real.real > 1e-9))

    VF, fF, Vdiv = math.inf, math.nan, math.inf
    Vprev = 0.0
    for V in np.linspace(V_max / n, V_max, n):
        lam = eig(float(V))
        if not math.isfinite(Vdiv) and div_of(lam):
            lo, hi = Vprev, float(V)
            for _ in range(30):
                mid = 0.5 * (lo + hi)
                lo, hi = (lo, mid) if (mid > 0 and div_of(eig(mid))) else (mid, hi)
            Vdiv = hi
        if not math.isfinite(VF) and g_of(lam)[0] > 1e-6:
            lo, hi = Vprev, float(V)
            for _ in range(30):
                mid = 0.5 * (lo + hi)
                lo, hi = (lo, mid) if (mid > 0 and g_of(eig(mid))[0] > 1e-6) else (mid, hi)
            VF, fF = hi, g_of(eig(hi))[1]
        Vprev = float(V)
        if math.isfinite(VF) and math.isfinite(Vdiv):
            break
    return {"V_F": VF, "f_F": fF, "V_div": Vdiv}


def classify(phi: np.ndarray, M: np.ndarray, node_comp: dict[int, str], node_ix: dict[int, int]) -> list[dict[str, Any]]:
    """Componente dominante de cada modo pela energia cinética nodal (φᵀ M φ por nó) e tipo (translação/rotação)."""
    out = []
    for j in range(phi.shape[1]):
        v = phi[:, j]
        e_comp: dict[str, float] = {}
        e_rot = 0.0
        for nid, k in node_ix.items():
            d = slice(6 * k, 6 * k + 6)
            ek = float(v[d] @ M[d, d] @ v[d])
            e_comp[node_comp.get(nid, "?")] = e_comp.get(node_comp.get(nid, "?"), 0.0) + ek
            e_rot += float(v[6 * k + 3:6 * k + 6] @ M[6 * k + 3:6 * k + 6, 6 * k + 3:6 * k + 6] @ v[6 * k + 3:6 * k + 6])
        tot = sum(e_comp.values()) or 1.0
        top = max(e_comp, key=lambda c: e_comp[c])
        out.append({"component": top, "energy_share": e_comp[top] / tot,
                    "rotational_share": min(max(e_rot / tot, 0.0), 1.0)})
    return out


def flutter_from_beam_model(model: dict[str, Any], surf: dict[str, dict[str, Any]], body_mass: dict[int, float],
                            body_radius: dict[int, float], VD_eas: float, margin: float = 1.2, n_modes: int = 16,
                            rho: float = 1.225, fixed: list[int] | None = None) -> dict[str, Any]:
    """Estimativa de flutter do avião inteiro (ver docstring do módulo). ``surf``: {componente: {span, c_root,
    c_tip, e, x_cg_off, a_w, m_per_c}}; ``body_mass``: massa concentrada por nó dos corpos [kg];
    ``body_radius``: raio local (inércia de rolamento m R²/2 — PRESSUPOSTO)."""
    st = strips(model, surf)
    nm = strip_masses(st)
    for nid, m in body_mass.items():
        R = float(body_radius.get(nid, 0.0))
        J = np.diag([0.5 * m * R**2, 0.25 * m * R**2, 0.25 * m * R**2])
        nm[nid] = nm.get(nid, np.zeros((6, 6))) + point_mass_matrix(m, np.zeros(3), J)
    K, M, keep = assemble(model, nm, fixed)
    rigid = 0 if fixed else 6
    om, phi = modes(K, M, keep, n_modes, rigid)
    ids = [n["id"] for n in model["nodes"]]
    node_ix = {i: k for k, i in enumerate(ids)}
    owner: dict[int, str] = {}
    for e in model["elements"]:
        for nid in e["nodes"]:
            owner.setdefault(nid, str(e["component"]))
    for s_ in st:
        owner[s_["node"]] = s_["comp"]
    cls = classify(phi, M, owner, node_ix)
    AK, AD = aero_matrices(st, phi, node_ix)
    sw = flutter_sweep(om, AK, AD, rho, max(4.0 * VD_eas, 150.0))
    Vreq = margin * VD_eas
    ok = sw["V_F"] >= Vreq and sw["V_div"] >= Vreq
    return {"method": f"vigas 3-D ({PRZEMIENIECKI}) + faixas quase-estacionárias ({WRIGHT_COOPER} cap. 11)",
            "V_F_eas": sw["V_F"], "f_F_Hz": sw["f_F"], "V_div_eas": sw["V_div"], "V_required_eas": Vreq,
            "margin": (min(sw["V_F"], sw["V_div"]) / Vreq - 1) if Vreq > 0 else None,
            "verdict": "passa" if ok else "falha",
            "modes": [{"f_Hz": float(w / (2 * math.pi)), **c} for w, c in zip(om, cls)],
            "n_modes": len(om), "n_strips": len(st), "mass_kg": float(np.trace(M[0::6, 0::6]))}


# ------------------------------------------------------------------------------------------------ ligação ao layout
def layout_flutter(res: Any, layout: dict[str, Any], recs: list[dict[str, Any]], o: dict[str, Any]) -> dict[str, Any]:
    """Flutter do avião inteiro para :func:`.structure_layout.analyse_layout`. Superfícies com a massa do build-up
    (itens wing/htail/vtail, como :mod:`.aeroelasticity`) ∝ corda, eixo elástico a meio do caixão da asa, CG da
    secção a ``x_cg_chord`` (0,5 c — Wright & Cooper cap. 11); resto do W0 nos nós dos corpos ∝ massa estrutural
    local (PRESSUPOSTO)."""
    model = layout.get("beam_model")
    st_ = getattr(res, "structures", None)
    if not model or not model.get("elements") or st_ is None or getattr(st_, "vn", None) is None:
        return {"evaluated": False, "verdict": "desconhecido", "reason": "sem modelo de vigas ou sem diagrama V-n"}
    w = res.config.wing
    xf = 0.5 * (w.box.front_spar_xc + w.box.rear_spar_xc)
    xcg = float(o.get("x_cg_chord") or 0.5)
    items = {it.key: float(it.mass) for it in getattr(getattr(res, "weights", None), "items", []) or []}
    surf: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    m_surf = 0.0
    key_of = {"asa": "wing", "estabilizador": "htail", "deriva": "vtail"}
    by_comp: dict[str, list[dict[str, Any]]] = {}
    for r in recs:
        if r.get("beam", True) is not False:
            by_comp.setdefault(r["comp"], []).append(r)
    mass_only = {r["comp"] for r in recs if r.get("beam", True) is False}
    for comp, rs in by_comp.items():
        bx = rs[0].get("box")
        if bx is None or not any(e["component"] == comp for e in model["elements"]):
            notes.append(f"{comp}: sem caixão no modelo de vigas — fora do modelo aeroelástico")
            continue
        cr = float(rs[0].get("c_root_m") or bx.get("c_root_m") or 0.0)
        ct = float(rs[0].get("c_tip_m") or bx.get("c_tip_m") or 0.0)
        area = 0.0
        for r in rs:
            L_p = float(np.hypot(r["span_vec"][1], r["span_vec"][2])) if "span_vec" in r else float(bx.get("semispan_m") or 0.0)
            area += (2 if r.get("mirror", True) else 1) * 0.5 * (float(r.get("c_root_m") or cr)
                                                                 + float(r.get("c_tip_m") or ct)) * L_p
        if area <= 0 or cr <= 0:
            notes.append(f"{comp}: geometria do caixão incompleta — fora do modelo aeroelástico")
            continue
        m_tot = items.get(key_of[comp])
        if m_tot is None:
            m_tot = sum(float((bx.get("masses") or {}).get("total") or 0.0) * float(r.get("share", 1.0))
                        * (2 if r.get("mirror", True) else 1) for r in rs)
            notes.append(f"{comp}: sem item no build-up; massa do caixão paramétrico ({m_tot:.2f} kg)")
        for other in mass_only:        # cauda em V: os painéis levam também a massa da superfície equivalente
            mo = items.get(key_of[other])
            if mo is not None and comp in ("estabilizador", "deriva"):
                m_tot += mo
                notes.append(f"{comp}: painéis da cauda em V levam também a massa de {other} ({mo:.2f} kg, build-up)")
        m_surf += m_tot
        surf[comp] = {"span": float(bx.get("semispan_m") or 0.0), "c_root": cr, "c_tip": ct, "e": xf - 0.25,
                      "x_cg_off": xcg - xf, "a_w": float(o.get("a_w") or 2 * math.pi), "m_per_c": m_tot / area}
    if "asa" not in surf:
        return {"evaluated": False, "verdict": "desconhecido", "reason": "asa fora do modelo de vigas", "notes": notes}
    W0 = float(res.sizing.W0)
    rest = max(W0 - m_surf, 0.0)
    surf_nodes = {n for e in model["elements"] if e["component"] in SURFACE_AXIS for n in e["nodes"][1:]}
    pm: dict[int, float] = {}
    for p in model.get("point_masses", []):
        if p["node"] not in surf_nodes:
            pm[p["node"]] = pm.get(p["node"], 0.0) + float(p["mass_kg"])
    tot = sum(pm.values())
    body_mass = {n: rest * m / tot for n, m in pm.items()} if tot > 0 else {}
    frs = (layout.get("fuselage") or {}).get("frames") or []
    xs = [f["x_m"] for f in frs]
    Rs = [f["R_m"] for f in frs]
    pos = {n["id"]: n["xyz"] for n in model["nodes"]}
    radius = {n: (float(np.interp(pos[n][0], xs, Rs)) if xs else 0.1) for n in body_mass}
    VD = float(st_.vn.VD)
    r = flutter_from_beam_model(model, surf, body_mass, radius, VD, float(o.get("margin_factor") or 1.2),
                                int(o.get("n_modes") or 16))
    ae = getattr(res, "aeroelastic", None)
    r["V_F_strip_eas"] = None if ae is None else float(ae.flutter.get("V_F", math.nan))
    r["V_D_eas"] = VD
    r["evaluated"] = True
    r["surfaces"] = sorted(surf)
    notes += [f"massa: superfícies {m_surf:.1f} kg (build-up) ∝ corda; resto do W0 {rest:.1f} kg nos nós dos corpos "
              "∝ massa estrutural local, inércia de rolamento m R²/2 — PRESSUPOSTO; combustível na asa não "
              "separado (declarar o caso de tanques cheios)",
              "ESTIMATIVA de baixa fidelidade (quase-estacionária, ρ0 → EAS): flutter de corpo livre, superfícies de "
              "comando (massa/folgas/compensação) e efeitos de compressibilidade fora do âmbito — certificação pede "
              ":mod:`hifi.flutter` ou ensaio"]
    # twin-boom: os booms levam a cauda; se a empenagem do modelo não ficou presa a esses booms (sem montagem), o
    # número fica relatado e o veredicto passa a desconhecido
    tb = [str(b.get("id")) for b in layout.get("booms", []) if b.get("evaluated") and b.get("carries_tail")]
    tail_on_booms = any(r.get("placement", "").startswith("montagem") and r["comp"] in ("estabilizador", "deriva")
                        for r in recs)
    if tb and not tail_on_booms:
        r["verdict_computed"] = r["verdict"]
        r["verdict"] = "desconhecido"
        notes.append(f"booms {', '.join(tb)} levam a cauda, mas a empenagem do layout está ao centro (presa ao corpo "
                     f"principal): V_F calculado {r['V_F_eas']:.1f} m/s fica relatado, veredicto desconhecido")
    elif tb:
        notes.append(f"empenagem na posição da montagem, presa aos booms {', '.join(tb)} pela raiz de cada painel")
    r["notes"] = notes
    return r
