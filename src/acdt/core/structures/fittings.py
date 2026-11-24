# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Ferragens L1: olhais (lugs) e cavilhas sob carga axial, berço tubular do motor.

Métodos citados (sem curvas inventadas):

* **Olhais sob carga axial** — Melcon & Hoblit (*Product Engineering*, junho 1953), como codificado no
  *Stress Analysis Manual* AFFDL-TR-69-42 (Maddux et al., 1969), §9.3: rotura de apoio/corte à frente do furo
  F_bru,L = K (a/D) F_tu (e/D < 1,5) ou K F_tu (e/D ≥ 1,5), Eq. 9-1, com P_bru,L = F_bru,L D t (Eq. 9-3a) ou
  1,304 F_bry,L D t se F_tu > 1,304 F_ty (Eq. 9-3b); secção útil F_nu = K_n F_tu, P_nu = K_n F_tu (w − D) t (Eq. 9-4,
  9-6a/b). K vem da **Fig. 9-2** (D/t ≤ 5; acima disso a Fig. 9-3 reduz K — aqui fica desconhecido) e K_n da
  **Fig. 9-4** (painéis F_ty/F_tu = 0,6 e 0,8, curvas F_tu/(E ε_u) = 0,1 e 1,0). As tabelas abaixo foram **lidas à
  mão** das figuras do manual (incerteza ±0,03 em K_n, ±0,02 em K); a leitura de K reproduz o exemplo do manual
  (K = 1,46 a e/D = 1,24). Bruhn (1973) cap. D1 dá o mesmo método.
* **Cavilha em corte duplo** — AFFDL-TR-69-42 Eq. 9-12: P_us = 1,571 D² F_su; **flexão da cavilha** Eq. 9-13 a 9-15:
  M = (P/2)(t1/2 + g + t2/4), M_u = 0,0982 k_b D³ F_tu com k_b = 1,56 (material dúctil, > 5 % de alongamento).
* **Berço tubular** — treliça espacial de tubos de aço com nós articulados (PRESSUPOSTO): forças por mínimos
  quadrados do equilíbrio do motor (rigidez igual nos tubos, PRESSUPOSTO); tubos à tração (F_tu) e à compressão por
  Euler–Johnson (Bruhn C2; :func:`frames.euler_johnson`), K = 1 (articulado). Cargas do motor: 14 CFR 23.361
  (binário médio × fator por n.º de cilindros) e 23.363 (lateral ≥ 1,33 g) — regulamento anterior à emenda 23-64.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import frames as fr

# AFFDL-TR-69-42 Fig. 9-2: K vs e/D (D/t ≤ 5), lida à mão.
_FIG92_ED = (0.5, 0.6, 0.8, 1.0, 1.2, 1.4, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4)
_FIG92_K = (2.00, 1.92, 1.73, 1.58, 1.48, 1.36, 1.33, 1.42, 1.60, 1.75, 1.88, 1.97)
# AFFDL-TR-69-42 Fig. 9-4 (c) F_ty/F_tu = 0,8 e (d) 0,6: K_n vs D/w, curvas F_tu/(E ε_u) = 0,1 e 1,0, lidas à mão.
_FIG94_DW = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
_FIG94 = {
    (0.8, 0.1): (0.0, 0.58, 0.81, 0.84, 0.85, 0.86, 0.87, 0.89, 0.92, 0.95, 1.0),
    (0.8, 1.0): (0.0, 0.09, 0.18, 0.26, 0.33, 0.39, 0.46, 0.53, 0.63, 0.78, 1.0),
    (0.6, 0.1): (0.0, 0.50, 0.66, 0.70, 0.72, 0.74, 0.76, 0.79, 0.83, 0.89, 1.0),
    (0.6, 1.0): (0.0, 0.08, 0.17, 0.25, 0.32, 0.38, 0.45, 0.53, 0.62, 0.78, 1.0),
}
FIG_SOURCE = "AFFDL-TR-69-42 (1969) §9.3–9.4, Figs. 9-2 e 9-4 lidas à mão; Melcon & Hoblit (1953); Bruhn D1"
KB_PIN = 1.56          # AFFDL-TR-69-42 §9.4.3: pino dúctil (> 5 % de alongamento)
AN_BOLTS_IN = {"AN3": 3 / 16, "AN4": 1 / 4, "AN5": 5 / 16, "AN6": 3 / 8, "AN7": 7 / 16, "AN8": 1 / 2,
               "AN9": 9 / 16, "AN10": 5 / 8, "AN12": 3 / 4, "AN14": 7 / 8, "AN16": 1.0}   # diâmetro nominal [in]


def k_bearing(e_D: float) -> float:
    """K da Fig. 9-2 (D/t ≤ 5)."""
    return float(np.interp(e_D, _FIG92_ED, _FIG92_K))


def k_net(D_w: float, Fty_Ftu: float, ductility: float | None) -> tuple[float | None, str]:
    """K_n da Fig. 9-4. ``ductility`` = F_tu/(E ε_u); None (alongamento desconhecido) → curva 1,0 (a mais baixa,
    conservativa). Painel por baixo: F_ty/F_tu ≥ 0,8 → (c); ≥ 0,6 → (d); abaixo de 0,6 → desconhecido."""
    if Fty_Ftu >= 0.8:
        panel = 0.8
    elif Fty_Ftu >= 0.6:
        panel = 0.6
    else:
        return None, "F_ty/F_tu < 0,6: fora dos painéis lidos da Fig. 9-4"
    curve = 0.1 if (ductility is not None and ductility <= 0.1) else 1.0
    note = (f"Fig. 9-4 painel F_ty/F_tu = {panel}, curva F_tu/(E ε_u) = {curve}"
            + ("" if ductility is not None else " (alongamento não declarado → curva mais baixa, conservativa)"))
    return float(np.interp(D_w, _FIG94_DW, _FIG94[(panel, curve)])), note


@dataclass
class LugResult:
    P_bru_N: float | None
    P_nu_N: float | None
    P_pin_shear_N: float
    P_pin_bending_N: float
    P_allow_N: float | None
    RF: float | None
    verdict: str
    mode: str
    notes: list[str] = field(default_factory=list)


def lug_joint(P_u: float, D: float, t: float, w: float, e: float, lug: dict[str, Any], pin: dict[str, Any],
              t_clevis: float | None = None, g: float = 0.0, eps_u: float | None = None,
              clevis: dict[str, Any] | None = None, w_clevis: float | None = None, e_clevis: float | None = None,
              eps_u_clevis: float | None = None, D_pin: float | None = None) -> LugResult:
    """Ligação olhal (macho, espessura t) + garfo (2 orelhas de t_clevis) + cavilha de diâmetro D, carga ÚLTIMA
    axial ``P_u`` [N], sem casquilhos. ``lug``/``clevis``/``pin``: dicionários de material (Ftu, Fty, Fsu, E); o
    garfo tem por omissão o material e a geometria do olhal e verifica-se pelo mesmo método (cada orelha leva P/2);
    ``g`` é a folga entre olhal e orelha; ``D_pin`` (omissão D) é o diâmetro da cavilha quando há casquilho
    (o casquilho em si não é verificado). Pino fraco em flexão: fica a Eq. 9-15 sem a redistribuição da Eq. 9-16
    (conservativo)."""
    notes: list[str] = []
    tc = t_clevis if t_clevis is not None else t / 2
    cm = clevis or lug

    def one(tt: float, mat: dict[str, Any], w: float, e: float, eps: float | None
            ) -> tuple[float | None, float | None, str]:
        Ftu, Fty = mat["Ftu"], mat["Fty"]
        if D / tt > 5.0:
            notes.append(f"D/t = {D / tt:.1f} > 5: Fig. 9-3 (redução por esbelteza) não lida — apoio desconhecido")
            P_br = None
        else:
            eD = e / D
            K = k_bearing(eD)
            a = e - D / 2
            Fbr = K * (a / D if eD < 1.5 else 1.0) * Ftu
            Fbry = K * (a / D if eD < 1.5 else 1.0) * Fty
            P_br = Fbr * D * tt if Ftu <= 1.304 * Fty else 1.304 * Fbry * D * tt
        Kn, nn = k_net(D / w, Fty / Ftu, None if eps is None else Ftu / (mat["E"] * eps))
        notes.append(nn)
        P_n = None if Kn is None else (Kn * Ftu * (w - D) * tt if Ftu <= 1.304 * Fty
                                       else 1.304 * Kn * Fty * (w - D) * tt)
        return P_br, P_n, nn

    Pb, Pn, _ = one(t, lug, w, e, eps_u)
    Pbc, Pnc, _ = one(tc, cm, w_clevis or w, e_clevis or e, eps_u_clevis if clevis is not None else eps_u)
    Dp = D_pin or D
    P_us = 1.571 * Dp**2 * pin["Fsu"]
    arm = t / 4 + g + tc / 2                          # Eq. 9-13 com t1 = orelha do garfo, t2 = olhal macho
    P_ub = 0.1963 * KB_PIN * Dp**3 * pin["Ftu"] / arm  # Eq. 9-15
    cands = {"apoio/corte olhal": Pb, "secção útil olhal": Pn,
             "apoio/corte garfo": None if Pbc is None else 2 * Pbc,
             "secção útil garfo": None if Pnc is None else 2 * Pnc,
             "corte duplo cavilha": P_us}
    known = {k: v for k, v in cands.items() if v is not None}
    unknown = [k for k, v in cands.items() if v is None]
    if P_ub < min(known.values(), default=math.inf):
        known["flexão da cavilha"] = P_ub                # pino fraco: Eq. 9-15 governa (sem redistribuição, conservativo)
    mode = min(known, key=lambda k: known[k])
    P_all = known[mode]
    RF = P_all / P_u if P_u > 0 else math.inf
    if RF < 1.0:
        verdict = "falha"
    elif unknown:
        verdict = "desconhecido"
        notes.append("modos não avaliados: " + ", ".join(unknown))
    else:
        verdict = "passa"
    return LugResult(Pb, Pn, P_us, P_ub, P_all, RF, verdict, mode, notes)


def size_lug(P_u: float, lug: dict[str, Any], pin: dict[str, Any], e_D: float = 1.5, w_D: float = 3.0,
             eps_u: float | None = None, t_min: float = 1.0e-3) -> dict[str, Any]:
    """Escolhe a cavilha AN mais pequena e a espessura do olhal (passo 0,5 mm, D/t ≤ 5) que dão RF ≥ 1 sob a carga
    ÚLTIMA ``P_u``. Geometria: e = e_D·D, w = w_D·D (PRESSUPOSTO, olhal de extremidade redonda), garfo de 2 orelhas
    de t/2 + 0,5 mm. Massa: placa w × (e + w) menos o furo, olhal + garfo (PRESSUPOSTO)."""
    last: dict[str, Any] = {}
    for name, d_in in AN_BOLTS_IN.items():
        D = d_in * 0.0254
        t = max(t_min, D / 5.0)
        while t <= 2.0 * D:
            tc = t / 2 + 0.5e-3
            r = lug_joint(P_u, D, t, w_D * D, e_D * D, lug, pin, t_clevis=tc, eps_u=eps_u)
            last = {"bolt": name, "D_m": D, "t_m": t, "t_clevis_m": tc, "w_m": w_D * D, "e_m": e_D * D, "res": r}
            if r.RF is not None and r.RF >= 1.0:
                area = w_D * D * (e_D * D + w_D * D) - math.pi * D**2 / 4
                last["mass_kg"] = area * (t + 2 * tc) * lug["rho"] + pin["rho"] * math.pi * D**2 / 4 * (t + 2 * tc
                                                                                                  + 1.5 * D)
                return last
            t += 0.5e-3
    last["mass_kg"] = None
    return last


# ------------------------------------------------------------------------------------------------ engine mount
def engine_mount(F_limit: np.ndarray, M_limit: np.ndarray, x_cg: float, firewall_half: float, ring_half: float,
                 length: float, tube: dict[str, Any], FS: float = 1.5, t_min: float = 0.89e-3,
                 D_steps: tuple[float, ...] = (12.7e-3, 15.9e-3, 19.1e-3, 22.2e-3, 25.4e-3, 31.8e-3),
                 cases: list[tuple[str, np.ndarray, np.ndarray]] | None = None) -> dict[str, Any]:
    """Berço de 8 tubos: 4 nós na parede de fogo (quadrado de meio-lado ``firewall_half`` em x = 0) e 4 apoios do
    motor (quadrado de meio-lado ``ring_half`` em x = −``length``, à frente). Cada apoio liga a 2 nós da parede de
    fogo (padrão em diagonal, PRESSUPOSTO). ``cases`` = [(nome, F[3], M[3])] LIMITE no CG do motor (x = −x_cg).
    Forças por mínimos quadrados (rigidez igual, PRESSUPOSTO). Devolve tubos dimensionados (D, t) e massa."""
    fw = [np.array([0.0, sy * firewall_half, sz * firewall_half]) for sy, sz in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
    rg = [np.array([-length, sy * ring_half, sz * ring_half]) for sy, sz in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
    bars = [(i, j) for i in range(4) for j in (i, (i + 1) % 4)]
    cg = np.array([-x_cg, 0.0, 0.0])
    A = np.zeros((6, len(bars)))
    L = []
    for k, (i, j) in enumerate(bars):
        v = fw[j] - rg[i]                     # direção do apoio do motor para a parede de fogo (tração +)
        ln = float(np.linalg.norm(v))
        u = v / ln
        L.append(ln)
        A[:3, k] = u
        A[3:, k] = np.cross(rg[i] - cg, u)
    cases = cases or [("limite", np.asarray(F_limit, float), np.asarray(M_limit, float))]
    Nmax = np.zeros(len(bars))
    Nmin = np.zeros(len(bars))
    for _name, F, M in cases:
        rhs = -np.concatenate([F, M])         # forças das barras sobre o motor equilibram as cargas
        N, *_ = np.linalg.lstsq(A, rhs, rcond=None)
        Nmax = np.maximum(Nmax, N)
        Nmin = np.minimum(Nmin, N)
    tubes = []
    mass = 0.0
    for k, (i, j) in enumerate(bars):
        best = None
        for D in D_steps:
            t = t_min
            while t <= D / 4:
                Ai = math.pi / 4 * (D**2 - (D - 2 * t) ** 2)
                Ii = math.pi / 64 * (D**4 - (D - 2 * t) ** 4)
                rho_g = math.sqrt(Ii / Ai)
                sc = fr.euler_johnson(tube["E"], tube["Fcy"], L[k] / rho_g)
                RF_t = tube["Ftu"] * Ai / (FS * Nmax[k]) if Nmax[k] > 0 else math.inf
                RF_c = sc * Ai / (FS * -Nmin[k]) if Nmin[k] < 0 else math.inf
                if min(RF_t, RF_c) >= 1.0:
                    m = Ai * L[k] * tube["rho"]
                    if best is None or m < best["mass_kg"]:
                        best = {"D_m": D, "t_m": t, "mass_kg": m, "RF": min(RF_t, RF_c)}
                    break
                t += 0.25e-3
        tubes.append({"bar": k + 1, "nodes": [f"apoio{i + 1}", f"parede{j + 1}"], "L_m": L[k],
                      "N_tension_limit_N": float(Nmax[k]), "N_compression_limit_N": float(Nmin[k]),
                      **(best or {"D_m": None, "t_m": None, "mass_kg": None, "RF": None})})
        mass += (best or {}).get("mass_kg") or 0.0
    ok = all(tb["RF"] is not None for tb in tubes)
    return {"tubes": tubes, "mass_kg": mass if ok else None, "verdict": "passa" if ok else "falha",
            "nodes_firewall": [p.tolist() for p in fw], "nodes_engine": [p.tolist() for p in rg],
            "method": "treliça espacial articulada, mínimos quadrados (rigidez igual — PRESSUPOSTO); tubos: tração "
                      "F_tu e Euler–Johnson (Bruhn C2), K = 1; FS 1,5"}
