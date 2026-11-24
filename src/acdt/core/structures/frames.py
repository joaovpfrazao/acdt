# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Cavernas, anteparas, longarinas/reforçadores e revestimento de corpos tubulares (fuselagens, booms) — L0/L1.

Genérico (sem dependência do domínio aircraft): um corpo de secção circular de raio R(x), cavernas em estações x,
reforçadores (longarinas/stringers) em posições angulares e revestimento. Métodos clássicos citados:

* **Anel de caverna sob cargas concentradas** reagidas pelo fluxo de corte da casca. O fluxo de reação de uma casca
  circular fina a uma força no plano F e a um binário T é q(θ) = (F_z sin θ − F_y cos θ)/(π R) + T/(2 π R²)
  (teoria de vigas de parede fina, Megson, *Aircraft Structures*, cap. 17/20 — tubo circular fino: q = S sin θ/(π R)).
  O anel é hiperestático de grau 3: corta-se em θ = 0 e as três redundantes saem do teorema de Castigliano com
  energia só de flexão (anel fino, R ≫ altura da secção; Timoshenko, *Strength of Materials* Pt. I, anéis
  circulares; Megson cap. 5). Verificação: anel comprimido por duas forças opostas P → M = P R/π no ponto de
  carga e P R (1/π − 1/2) a 90° (Timoshenko; Roark, *Formulas for Stress and Strain*, cap. 9).
* **Instabilidade geral (cavernas leves)**: critério de Shanley (1949, J. Aero. Sci. 16) EI_caverna ≥ C_f M D²/L,
  C_f = 1/16 000 (também em Niu 1988, *Airframe Structural Design*, cap. 11).
* **Reforçadores**: idealização em booms (Megson Eq. 20.1 com largura efetiva), σ = M z/I; coluna entre cavernas
  Euler–Johnson com tensão de corte = crippling de Gerard (Bruhn C2/C7; :mod:`acdt.core.sections`), c = 1
  (articulado nas cavernas — PRESSUPOSTO conservativo).
* **Revestimento**: corte q = V/(π R) + T/(2 π R²) (Megson), resistência τ ≤ F_su; encurvadura do painel entre
  reforçadores como placa plana simplesmente apoiada (k_c = 4, k_s = 5,35; Bruhn C5 — curvatura desprezada,
  PRESSUPOSTO conservativo) com interação R_c + R_s² ≤ 1 à carga LIMITE (sem encurvadura até à carga limite —
  PRESSUPOSTO); largura efetiva de von Kármán b_e = 1,9 t √(E/σ) (Bruhn C7) quando encurva.
* **Antepara plana sob pressão** (placa circular, Timoshenko & Woinowsky-Krieger, *Theory of Plates and Shells*,
  §15–16): apoiada σ_max = 3(3+ν) p a²/(8 t²); encastrada σ_max = 3 p a²/(4 t²).

Fatores de reserva RF = admissível/aplicado; veredicto passa (RF ≥ 1) / falha / desconhecido (dado em falta).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from acdt.core import sections

SHANLEY_CF = 1.0 / 16000.0
N_RING = 720


def verdict(rf: float | None) -> str:
    if rf is None or not math.isfinite(rf):
        return "desconhecido"
    return "passa" if rf >= 1.0 else "falha"


# ------------------------------------------------------------------------------------------------ ring analysis
@dataclass
class RingLoad:
    """Carga no plano da caverna, aplicada no ponto do anel a θ (graus, a partir do topo, positivo para +y).

    Coordenadas da secção: y lateral (+ direita), z para cima. ``Fy``, ``Fz`` [N] força aplicada ao anel;
    ``M`` [N m] binário concentrado (positivo de y para z)."""
    theta_deg: float
    Fy: float = 0.0
    Fz: float = 0.0
    M: float = 0.0


def _cross(p, F):
    """Momento 2-D (y, z) de F aplicada em p: p_y F_z − p_z F_y."""
    return p[..., 0] * F[..., 1] - p[..., 1] * F[..., 0]


def ring_internal_forces(R: float, loads: list[RingLoad], shell_reaction: bool = True, n: int = N_RING) -> dict:
    """Esforços internos M(θ), N(θ), V(θ) num anel circular fino de raio R.

    Cargas concentradas ``loads``; com ``shell_reaction`` a resultante (força e binário) é reagida pelo fluxo de corte
    da casca q(θ) (Megson). Sem ela as cargas têm de estar em equilíbrio. Castigliano (só flexão) nas 3 redundantes.
    Sinal de M arbitrário mas consistente; devolve-se |M|max, a sua posição e o N concomitante."""
    th = np.linspace(0.0, 2 * math.pi, n + 1)
    pos = R * np.stack([np.sin(th), np.cos(th)], axis=1)
    tan = np.stack([np.cos(th), -np.sin(th)], axis=1)          # d(pos)/dθ / R
    Fy = sum(ld.Fy for ld in loads)
    Fz = sum(ld.Fz for ld in loads)
    Mtot = sum(ld.M + float(_cross(R * np.array([math.sin(math.radians(ld.theta_deg)),
                                                     math.cos(math.radians(ld.theta_deg))]),
                                        np.array([ld.Fy, ld.Fz]))) for ld in loads)
    if shell_reaction:
        a, b = -Fy / (math.pi * R), Fz / (math.pi * R)
        # binário do fluxo tangencial: r × t = −R → M_q = −2 π R² c; equilíbrio M_q = −M_tot
        c = Mtot / (2 * math.pi * R**2)
        q = a * np.cos(th) + b * np.sin(th) + c
    else:
        if abs(Fy) + abs(Fz) > 1e-9 * (1 + sum(abs(ld.Fy) + abs(ld.Fz) for ld in loads)) or abs(Mtot) > 1e-6 * (1 + R):
            raise ValueError("cargas do anel não equilibradas e sem reação da casca")
        q = np.zeros_like(th)
    # forças elementares da casca (por elemento de arco, regra do trapézio nos nós)
    dth = th[1] - th[0]
    fq = (q * R * dth)[:, None] * tan
    fq[0] *= 0.5
    fq[-1] *= 0.5
    # momento estático (cargas no arco [0, θ]) avaliado em cada secção θ_i — vetorizado por somas acumuladas
    cumF = np.cumsum(fq, axis=0)
    cumM = np.cumsum(_cross(pos, fq))           # Σ p × f
    F_arc = cumF.copy()
    M0 = cumM.copy()
    for ld in loads:
        t = math.radians(ld.theta_deg) % (2 * math.pi)
        p = R * np.array([math.sin(t), math.cos(t)])
        F = np.array([ld.Fy, ld.Fz])
        on = th > t + 1e-12
        F_arc[on] += F
        M0[on] += float(_cross(p, F)) + ld.M
    # momento em θ_i das forças no arco [0, θ_i] (sobre o ponto pos_i): Σ (p − pos_i) × f = M0 − pos_i × F_arc
    Ms = M0 - _cross(pos, F_arc)
    # redundantes na secção de corte (aplicadas no início do arco): X1 binário, X2 força y, X3 força z em pos_0
    p0 = pos[0]
    m1 = np.ones_like(th)
    m2 = -(p0[1] - pos[:, 1])                     # (p0 − pos) × e_y = −(p0_z − pos_z)
    m3 = p0[0] - pos[:, 0]                        # (p0 − pos) × e_z = p0_y − pos_y
    Mb = np.stack([m1, m2, m3], axis=1)
    w = np.full_like(th, dth)
    w[0] = w[-1] = 0.5 * dth
    A = (Mb * w[:, None]).T @ Mb
    rhs = -(Mb * w[:, None]).T @ Ms
    X = np.linalg.solve(A, rhs)
    M = Ms + Mb @ X
    F_int = F_arc + np.array([X[1], X[2]])
    N = np.einsum("ij,ij->i", F_int, tan)          # componente tangencial da resultante do arco
    V = np.einsum("ij,ij->i", F_int, pos / R)
    i = int(np.argmax(np.abs(M)))
    return {"theta_deg": np.degrees(th), "M": M, "N": N, "V": V, "q_shell": q,
            "M_max_abs": float(abs(M[i])), "theta_M_max_deg": float(np.degrees(th[i])), "N_at_M_max": float(N[i]),
            "N_max_abs": float(np.max(np.abs(N))), "redundants": X.tolist(),
            "closure_residual": float(abs(M[-1] - M[0]))}


# ------------------------------------------------------------------------------------------------ frame member
FRAME_SECTIONS = ("z", "channel", "hat", "i")


def frame_profile(kind: str, h: float, b: float, t: float) -> sections.Profile:
    if kind == "z":
        return sections.z_section(h, b, t, t)
    if kind == "channel":
        return sections.channel(h, b, t, t)
    if kind == "i":
        return sections.i_section(h, b, t, t)
    if kind == "hat":
        return sections.hat(h, b, 0.5 * b, t)
    raise ValueError(f"secção de caverna desconhecida: {kind} (use {FRAME_SECTIONS})")


def frame_check(prof: sections.Profile, mat: dict, M_u, N_u, M_lim_body: float | None,
                D: float, pitch: float) -> dict:
    """Verificações de uma caverna. ``M_u``, ``N_u``: esforços ÚLTIMOS no anel (escalares ou distribuições M(θ),
    N(θ) do mesmo comprimento); ``M_lim_body``: momento fletor LIMITE do corpo na estação (Shanley).

    Resistência: σ = max_θ(|N|/A + |M| c/I) ≤ F_cy (tração/compressão tomadas iguais — PRESSUPOSTO);
    crippling: σ ≤ F_cs (Gerard, :mod:`acdt.core.sections`); Shanley: EI ≥ C_f M_ult D²/L (Shanley 1949)."""
    pr = prof.properties()
    A, I = pr["A"], pr["Iyy"]
    zs = prof.pts[:, 1] - pr["zc"]
    c = float(max(abs(zs.max()), abs(zs.min())))
    Mv, Nv = np.abs(np.atleast_1d(np.asarray(M_u, float))), np.abs(np.atleast_1d(np.asarray(N_u, float)))
    sig = float(np.max(Nv / A + Mv * c / I)) if I > 0 else math.inf
    rf_s = mat["Fcy"] / sig if sig > 0 else math.inf
    cr = prof.crippling(mat["E"], mat["Fcy"], mat.get("nu", 0.33))["Fcs"]
    rf_c = cr / sig if sig > 0 else math.inf
    out: dict[str, Any] = {"A_m2": A, "I_m4": I, "c_m": c, "sigma_Pa": sig, "Fcs_Pa": cr,
                           "RF_strength": rf_s, "RF_crippling": rf_c}
    if M_lim_body is None:
        out["RF_shanley"] = None
    else:
        EI_req = SHANLEY_CF * 1.5 * abs(M_lim_body) * D**2 / pitch
        out["EI_req_Nm2"] = EI_req
        out["RF_shanley"] = (mat["E"] * I / EI_req) if EI_req > 0 else math.inf
    known = [r for r in (out["RF_strength"], out["RF_crippling"], out["RF_shanley"]) if r is not None]
    out["RF_min"] = min(known)
    out["verdict"] = verdict(out["RF_min"])
    if out["RF_shanley"] is None and out["verdict"] == "passa":
        out["verdict"] = "desconhecido"   # sem momento do corpo não há verificação de instabilidade geral
    return out


def size_frame(kind: str, h: float, b: float, t_min: float, mat: dict, M_u, N_u,
               M_lim_body: float | None, D: float, pitch: float, t_max: float = 6e-3, dt: float = 0.1e-3,
               h_max: float | None = None) -> dict:
    """Secção de caverna mínima que passa todas as verificações conhecidas: espessura em passos de ``dt`` até
    ``t_max``; se não chegar, altura × 1,25 (largura proporcional) até ``h_max`` (omissão 0,12 D — PRESSUPOSTO)."""
    h_max = 0.12 * D if h_max is None else h_max
    bh = b / h
    chk: dict = {}
    while True:
        t = t_min
        while t <= t_max + 1e-12:
            chk = frame_check(frame_profile(kind, h, bh * h, t), mat, M_u, N_u, M_lim_body, D, pitch)
            if chk["RF_min"] >= 1.0:
                chk.update({"t_m": t, "h_m": h, "b_m": bh * h})
                return chk
            t += dt
        if h * 1.25 > h_max + 1e-12:
            break
        h *= 1.25
    chk.update({"t_m": t - dt, "h_m": h, "b_m": bh * h,
                "note": f"não passa até t = {t_max * 1e3:.1f} mm e h = {h * 1e3:.0f} mm: rever a introdução da carga"})
    return chk


# ------------------------------------------------------------------------------------------------ bulkhead plate
def pressure_bulkhead(a: float, t: float, p: float, mat: dict, edge: str = "simply_supported") -> dict:
    """Placa circular plana de raio a sob pressão p (Timoshenko & Woinowsky-Krieger §15–16), carga ÚLTIMA."""
    nu = mat.get("nu", 0.33)
    if edge == "clamped":
        s = 3 * p * a**2 / (4 * t**2)
    else:
        s = 3 * (3 + nu) * p * a**2 / (8 * t**2)
    rf = mat["Fty"] / s if s > 0 else math.inf
    return {"sigma_Pa": s, "RF": rf, "verdict": verdict(rf), "edge": edge}


def size_pressure_bulkhead(a: float, p: float, mat: dict, t_min: float, edge: str = "simply_supported") -> dict:
    nu = mat.get("nu", 0.33)
    k = 3 / 4 if edge == "clamped" else 3 * (3 + nu) / 8
    t = max(t_min, math.sqrt(k * p * a**2 / mat["Fty"])) if p > 0 else t_min
    out = pressure_bulkhead(a, t, p, mat, edge)
    out["t_m"] = t
    return out


# ------------------------------------------------------------------------------------------------ stiffened shell
def euler_johnson(E: float, Fcc: float, L_rho: float) -> float:
    """Tensão crítica de coluna (Bruhn C2): Euler π²E/(L'/ρ)²; Johnson Fcc − Fcc² (L'/ρ)²/(4π²E) se σ_E > Fcc/2."""
    if L_rho <= 0:
        return Fcc
    se = math.pi**2 * E / L_rho**2
    if se > 0.5 * Fcc:
        return Fcc - Fcc**2 * L_rho**2 / (4 * math.pi**2 * E)
    return se


@dataclass
class ShellStation:
    x: float
    R: float
    M_lim: float        # momento fletor LIMITE [N m]
    V_lim: float        # esforço transverso LIMITE [N]
    T_lim: float = 0.0  # torção LIMITE [N m]


@dataclass
class ShellLayout:
    n_stringers: int
    stringer_kind: str = "z"         # z | hat | angle | channel
    stringer_h: float = 0.020
    stringer_b: float = 0.012
    stringer_t: float = 0.8e-3
    skin_t: float = 0.6e-3
    frame_pitch: float = 0.5
    longeron_area: float = 0.0       # área adicional por longarina [m²] (0 → só reforçadores)
    longeron_theta_deg: list = field(default_factory=list)


def stringer_profile(kind: str, h: float, b: float, t: float) -> sections.Profile:
    if kind == "z":
        return sections.z_section(h, b, t, t)
    if kind == "hat":
        return sections.hat(h, b, 0.5 * b, t)
    if kind == "angle":
        return sections.angle(h, b, t)
    if kind == "channel":
        return sections.channel(h, b, t, t)
    raise ValueError(f"secção de reforçador desconhecida: {kind}")


def shell_station_check(st: ShellStation, lay: ShellLayout, mat: dict, fs: float = 1.5) -> dict:
    """Verificações da casca reforçada numa estação (ver docstring do módulo)."""
    E, nu = mat["E"], mat.get("nu", 0.33)
    n = max(int(lay.n_stringers), 1)
    prof = stringer_profile(lay.stringer_kind, lay.stringer_h, lay.stringer_b, lay.stringer_t)
    pr = prof.properties()
    A_s = pr["A"]
    # raio de giração para flexão para fora do plano do revestimento (eixo paralelo à pele): o revestimento
    # estabiliza o modo lateral/torsional — PRESSUPOSTO (Bruhn C2/C7: coluna reforçador + pele)
    rho_s = math.sqrt(pr["Iyy"] / A_s)
    th = 2 * math.pi * np.arange(n) / n
    z = st.R * np.cos(th)
    A_b = np.full(n, A_s)
    for tl in lay.longeron_theta_deg:
        A_b[int(np.argmin(np.abs(((th - math.radians(tl)) + math.pi) % (2 * math.pi) - math.pi)))] += lay.longeron_area
    b = 2 * math.pi * st.R / n
    t = lay.skin_t
    Mu, Vu, Tu = fs * abs(st.M_lim), fs * abs(st.V_lim), fs * abs(st.T_lim)
    # largura efetiva: começa com o painel inteiro e itera com a tensão nos reforçadores comprimidos (von Kármán)
    be = np.full(n, b)
    sig = np.zeros(n)
    for _ in range(8):
        B = A_b + be * t
        I = float(np.sum(B * z**2))
        sig = Mu * z / I if I > 0 else np.full(n, math.inf)
        comp = np.maximum(sig, 0.0)    # z > 0 comprimido para momento que flete a cauda para cima (convenção)
        be_new = np.where(comp > 0, np.minimum(b, 1.9 * t * np.sqrt(E / np.maximum(comp, 1.0))), b)
        if np.allclose(be_new, be, rtol=1e-4):
            break
        be = be_new
    s_c = float(np.max(np.abs(sig)))
    Fcs = prof.crippling(E, mat["Fcy"], nu)["Fcs"]
    s_col = euler_johnson(E, Fcs, lay.frame_pitch / rho_s)
    rf_col = s_col / s_c if s_c > 0 else math.inf
    rf_ten = mat["Ftu"] / s_c if s_c > 0 else math.inf
    q = Vu / (math.pi * st.R) + Tu / (2 * math.pi * st.R**2)
    tau = q / t
    rf_sh = mat["Fsu"] / tau if tau > 0 else math.inf
    # encurvadura do painel à carga limite (sem encurvadura até à limite — PRESSUPOSTO)
    a_p = lay.frame_pitch
    bb = min(a_p, b)
    f = math.pi**2 * E / (12 * (1 - nu**2)) * (t / bb) ** 2
    k_s = 5.35 + 4.0 * (bb / max(a_p, b)) ** 2      # Bruhn C5 (simplesmente apoiada, lados a × b)
    sc_cr, ts_cr = 4.0 * f, k_s * f
    s_lim_c = s_c / fs
    tau_lim = tau / fs
    # fator de carga λ que leva a interação λ R_c + (λ R_s)² a 1 (Bruhn C5): raiz positiva da quadrática
    Rc, Rs = s_lim_c / sc_cr, tau_lim / ts_cr
    if Rs > 0:
        rf_pb = (-Rc + math.sqrt(Rc**2 + 4 * Rs**2)) / (2 * Rs**2)
    else:
        rf_pb = 1.0 / Rc if Rc > 0 else math.inf
    rfs = {"RF_stringer_column": rf_col, "RF_stringer_tension": rf_ten, "RF_skin_shear": rf_sh,
           "RF_skin_buckling_limit": rf_pb}
    rmin = min(rfs.values())
    return {"x_m": st.x, "R_m": st.R, "I_m4": I, "sigma_stringer_max_Pa": s_c, "Fcs_Pa": Fcs,
            "sigma_column_Pa": s_col, "L_over_rho": lay.frame_pitch / rho_s, "q_skin_N_m": q, "tau_skin_Pa": tau,
            "sigma_cr_panel_Pa": sc_cr, "tau_cr_panel_Pa": ts_cr, "b_eff_min_m": float(be.min()),
            "stringer_area_m2": A_s, "panel_width_m": b, **rfs, "RF_min": rmin, "verdict": verdict(rmin)}


def size_shell(stations: list[ShellStation], lay: ShellLayout, mat: dict, t_skin_min: float,
               t_str_max: float = 4e-3, t_skin_max: float = 4e-3, dt: float = 0.1e-3, fs: float = 1.5) -> list[dict]:
    """Por estação: aumenta a espessura do revestimento (corte e encurvadura) e a do reforçador (coluna/tração)
    em passos de ``dt`` até todas as verificações passarem. Devolve a tabela por estação (com t_skin, t_stringer)."""
    out = []
    for st in stations:
        ts, tstr = max(t_skin_min, lay.skin_t), lay.stringer_t
        chk: dict = {}
        for _ in range(400):
            L2 = ShellLayout(**{**lay.__dict__, "skin_t": ts, "stringer_t": tstr})
            chk = shell_station_check(st, L2, mat, fs)
            if chk["RF_min"] >= 1.0:
                break
            grew = False
            if min(chk["RF_skin_shear"], chk["RF_skin_buckling_limit"]) < 1.0 and ts < t_skin_max:
                ts += dt
                grew = True
            if min(chk["RF_stringer_column"], chk["RF_stringer_tension"]) < 1.0 and tstr < t_str_max:
                tstr += dt
                grew = True
            if not grew:
                chk["note"] = "limite de espessura atingido: rever passo de cavernas, n.º/altura de reforçadores"
                break
        chk["t_skin_m"], chk["t_stringer_m"] = ts, tstr
        out.append(chk)
    return out
