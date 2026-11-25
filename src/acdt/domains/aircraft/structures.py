"""Fase 2 — estruturas de baixa fidelidade, embebidas na geometria paramétrica.

The parametric layout (spars, ribs, skins) lives in :mod:`acdt.domains.aircraft.geometry`
(``WingBoxLayout``). This module implements the classical first-cut wing structural
analysis, all evaluated on that layout:

1. **V-n diagram** (flight + gust envelope):
   * CS-23 (Amdt. 4 and earlier) / 14 CFR Part 23 pre-Amdt. 23-64: §23.333 (flight
     envelope, gusts Ude = 50 ft/s at VC and 25 ft/s at VD up to 20 000 ft, linear
     reduction to 25/12.5 ft/s at 50 000 ft), §23.335 (design airspeeds: VC ≥ 33√(W/S)
     kt [psf] normal/utility, 36√(W/S) aerobatic, factor reduced linearly to 28.6 at
     W/S = 100 psf; VD ≥ 1.25 VC and ≥ 1.40/1.50/1.55 VC,min; VA ≥ VS√n),
     §23.337 (n ≥ 2.1 + 24 000/(W+10 000) ≤ 3.8 normal, 4.4 utility, 6.0 aerobatic;
     n_neg ≥ 0.4 n (normal/utility), 0.5 n aerobatic) and §23.341 (Pratt–Walker gust
     load factor n = 1 + Kg ρ0 Ude V a /(2 W/S), Kg = 0.88 μg/(5.3+μg),
     μg = 2(W/S)/(ρ c̄ a g)).  Current 14 CFR 23.2200–23.2215 are performance-based and
     accept these as means of compliance (ASTM F3116).
   * STANAG 4671 (USAR) Ed. 1: USAR.333 (same envelope; gusts 15.24 m/s at VC and 7.62 m/s
     at VD as a minimum), USAR.335 (VC from operating requirements; VD ≥ 1.25 VC; VA ≥ VS√n),
     USAR.337 (n ≥ min(2.1 + 10 900/(W+4536) [kg], 3.8); n_neg ≥ 0.4 n), USAR.341 (gust loads per
     USAR.333(c); AMC.341 refers to ESDU 04024 — the Pratt formula above is used as the
     classical first cut), USAR.303 (factor of safety 1.5).
   * CS-22 Amdt. 3 (planadores, ED Decision 2021/013/R): 22.333 (envelope de manobra A–D–E–G; rajadas
     15 m/s a VB e 7,5 m/s a VD), 22.335 (VA = VS1 √n1, VB ≥ VA — usado VB = VA; VD escolhido pelo requerente
     mas ≥ 18 ∛(W/S [daN/m²]) √(1/CD,min) km/h na categoria U, 3,5 W/S + 200 km/h na A), 22.337 (U: n1 +5,3,
     n2 +4,0 a VD, n3 −1,5 a VD, n4 −2,65; A: ±7,0/−5,0), 22.341 (n = 1 ± (k/2) ρ0 U V a/(m g/S),
     k = 0,96 (μ/(H/l_m))/(0,475 + μ/(H/l_m)), μ = 2 (m/S)/(ρ l_m a), H = (12,17 + 0,191 μ) l_m; n positivo
     não precisa de exceder 1,25 (V/VS1)²), 22.1505 (VNE ≤ 0,9 VDF ≤ 0,9 VD).
2. **Spanwise lift** by Schrenk's approximation (Schrenk 1940, NACA TM 948): average of the
   planform chord and the elliptic chord of equal area; cross-checked against AVL strips.
3. **Shear, bending and torsion** by integration from the tip (beam theory: Megson,
   *Aircraft Structures for Engineering Students*, Ch. 16/19; Bruhn, *Analysis and Design of
   Flight Vehicle Structures*, Ch. A), with inertia relief of the wing structure (mass ∝ chord)
   and *no* wing-fuel relief (conservative, cf. USAR AMC.343).
4. **Box-beam sizing** (Megson structural idealisation: booms carry direct stress, panels
   carry shear; Bredt–Batho shear flow q = T/(2A) for torsion): spar caps from bending,
   spar webs from shear + torsion, box skins from torsion, minimum gauges; ribs and the
   LE/TE skins at minimum gauge; *non-optimum* factor for joints, fasteners and cut-outs
   (Torenbeek 1982, App. C, concept of non-optimum weight) — ASSUMPTION value, reported.
5. **Skin panel buckling** (Bruhn Ch. C5; Timoshenko & Gere): long simply supported flat plate,
   compression k = 4.0, shear k_s = 5.35 — used as a *check* on the box skins.

The box-beam wing mass is a cross-check of Raymer Eq. 15.46 inside the weight loop
(``weights.components.wing_method: box`` makes it the value used).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from acdt import G0
from acdt.core.atmosphere import isa

KT, FT, LB, PSF = 0.514444, 0.3048, 0.45359237, 47.880259
RHO0 = 1.225

# Material allowables. Al 2024-T3: typical MMPDS (sheet, A/B-basis order of magnitude) values —
# VERIFY against MMPDS for the actual product form and thickness. CFRP: ASSUMPTIONS for a
# first cut (UD carbon/epoxy caps, ±45 fabric skins/webs, room-temperature dry with knock-down),
# replace by qualified laminate allowables.
MATERIALS = {
    "al2024_t3": {"name": "Al 2024-T3 (MMPDS typical — verify)", "rho": 2780.0, "E": 72.4e9, "nu": 0.33,
                  "sigma_cap": 269e6, "tau": 262e6, "t_min_skin": 0.41e-3, "t_min_web": 0.51e-3,
                  "cap_min_area": 20e-6, "G": 27.6e9, "sigma_tu": 434e6,
                  "note": "MMPDS typical 2024-T3 sheet: Fcy 269 MPa, Ftu 434 MPa, Fsu 262 MPa, G 27.6 GPa — verify"},
    "cfrp": {"name": "CFRP (UD caps / ±45 fabric — ASSUMPTION)", "rho": 1550.0, "E": 60e9, "nu": 0.30,
             "E_cap": 120e9, "sigma_cap": 500e6, "tau": 100e6, "t_min_skin": 0.25e-3, "t_min_web": 0.25e-3,
             "cap_min_area": 5e-6, "G": 20e9, "sigma_tu": 500e6,
             "core": {"name": "PVC/PMI foam (ASSUMPTION)", "rho": 75.0, "E": 70e6, "G": 30e6, "t_min": 2.0e-3},
             "note": "allowables are ASSUMPTIONS (knock-down for environment/damage)"},
}


def resolve_material(mat, composite: bool = False):
    """``structures.material``: ``auto`` (cfrp se weights.components.material = composite, senão al2024_t3), uma
    chave de :data:`MATERIALS`, ou um caixão compósito da biblioteca de materiais equivalentes (Fase 6,
    :func:`acdt.core.materials.composite_box_material`) dado como ``{skin, cap, core}`` — p. ex. planador em vidro
    ``{skin: gfrp_pm45, cap: gfrp_ud_cap, core: pvc_foam_h80}``. Devolve a chave (str) ou o dicionário."""
    if isinstance(mat, dict):
        from acdt.core.materials import composite_box_material
        return composite_box_material(mat.get("skin", "cfrp_qi"), mat.get("cap", "cfrp_cap"),
                                      mat.get("core", "pvc_foam_h80"))
    if mat == "auto":
        return "cfrp" if composite else "al2024_t3"
    return mat


# ---------------------------------------------------------------- V-n diagram
@dataclass
class VnDiagram:
    regulation: str
    category: str
    W_S: float  # N/m^2
    VS1: float  # EAS m/s (1 g, clean)
    VA: float
    VC: float
    VD: float
    VG: float
    n_pos: float
    n_neg: float
    gust: dict  # Ude values and gust load factors at VC/VD (+/-)
    mu_g: float
    Kg: float
    CLalpha: float
    CLmax: float
    CNmin: float
    clauses: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def n_gust_max(self) -> float:
        return max(self.gust["n_VC_pos"], self.gust["n_VD_pos"])

    @property
    def n_gust_min(self) -> float:
        return min(self.gust["n_VC_neg"], self.gust["n_VD_neg"])

    @property
    def n_limit_pos(self) -> float:
        """Design positive limit load factor = max(manoeuvre, gust) on the envelope."""
        return max(self.n_pos, self.n_gust_max)

    @property
    def n_limit_neg(self) -> float:
        return min(self.n_neg, self.n_gust_min)

    @property
    def governing(self) -> str:
        return "rajada" if self.n_gust_max > self.n_pos else "manobra"

    def n_gust(self, V, sign=1):
        """Gust line through (0, 1) for the Ude applicable at V (linear between VC and VD values)."""
        V = np.asarray(V, dtype=float)
        ude = np.where(V <= self.VC, self.gust["Ude_VC"], np.interp(V, [self.VC, self.VD],
                                                                    [self.gust["Ude_VC"], self.gust["Ude_VD"]]))
        return 1 + sign * self.Kg * RHO0 * ude * V * self.CLalpha / (2 * self.W_S)

    def envelope(self, n_pts: int = 200):
        """Manoeuvre envelope boundary (V EAS, n) — positive then negative side."""
        V = np.linspace(0, self.VD, n_pts)
        q = 0.5 * RHO0 * V**2
        if self.regulation == "cs_22":      # CS 22.333 Fig. 1: A (VA, n1) → D (VD, n2); G (VA, n4) → E (VD, n3)
            g = self.gust
            hi = np.where(V <= self.VA, self.n_pos, np.interp(V, [self.VA, self.VD], [self.n_pos, g["n2_VD"]]))
            lo = np.where(V <= self.VA, self.n_neg, np.interp(V, [self.VA, self.VD], [self.n_neg, g["n3_VD"]]))
            return V, np.minimum(q * self.CLmax / self.W_S, hi), np.maximum(q * self.CNmin / self.W_S, lo)
        n_up = np.minimum(q * self.CLmax / self.W_S, self.n_pos)
        n_lo = np.maximum(q * self.CNmin / self.W_S, np.where(V <= self.VC, self.n_neg,
                                                               self.n_neg * (self.VD - V) / (self.VD - self.VC)))
        return V, n_up, n_lo

    def summary(self) -> dict:
        return {"regulation": self.regulation, "category": self.category, "VS1_EAS_m_s": self.VS1,
                "VA_EAS_m_s": self.VA, "VC_EAS_m_s": self.VC, "VD_EAS_m_s": self.VD, "n_manoeuvre_pos": self.n_pos,
                "n_manoeuvre_neg": self.n_neg, "n_gust_VC": [self.gust["n_VC_pos"], self.gust["n_VC_neg"]],
                "n_gust_VD": [self.gust["n_VD_pos"], self.gust["n_VD_neg"]], "mu_g": self.mu_g, "Kg": self.Kg,
                "n_limit_pos": self.n_limit_pos, "n_limit_neg": self.n_limit_neg, "governing": self.governing,
                "n_ultimate": 1.5 * self.n_limit_pos}


def regulation_min_n(W0_kg: float, category: str, regulation: str) -> float:
    """Minimum positive limit manoeuvring load factor: 14 CFR/CS 23.337(a), USAR.337(a) or CS 22.337 (n1)."""
    if regulation == "cs_22":
        return CS22_N[cs22_category(category)][0]
    if regulation == "stanag_4671":
        return min(2.1 + 10900 / (W0_kg + 4536), 3.8)
    if category == "utility":
        return 4.4
    if category == "aerobatic":
        return 6.0
    return min(2.1 + 24000 / (W0_kg / LB + 10000), 3.8)


CS22_N = {"U": (5.3, 4.0, -1.5, -2.65), "A": (7.0, 7.0, -5.0, -5.0)}   # CS 22.337: n1, n2, n3, n4


def cs22_category(category: str) -> str:
    """Categoria CS-22 (U utilitária / A acrobática) a partir de structural_category."""
    c = str(category or "U").strip().lower()
    return "A" if c in ("a", "aerobatic", "acrobatic") else "U"


def cs22_vd_min(ws_N_m2: float, CD_min: float | None, category: str = "U") -> float | None:
    """VD mínimo de CS 22.335(f) [m/s EAS]; W/S em daN/m². U precisa de CD,min (desconhecido → None)."""
    ws_daN = ws_N_m2 / 10.0
    if cs22_category(category) == "A":
        return (3.5 * ws_daN + 200.0) / 3.6
    if not CD_min or CD_min <= 0:
        return None
    return 18.0 * ws_daN ** (1 / 3) * math.sqrt(1.0 / CD_min) / 3.6


def cs22_gust_k(ws_N_m2: float, lm: float, a: float, rho: float) -> tuple[float, float]:
    """CS 22.341(a): (k, μ) com μ = 2 (m/S)/(ρ l_m a), H/l_m = 12,17 + 0,191 μ."""
    mu = 2 * (ws_N_m2 / G0) / (rho * lm * a)
    r = mu / (12.17 + 0.191 * mu)
    return 0.96 * r / (0.475 + r), mu


def _v_n_cs22(W0_kg: float, S: float, CLmax: float, CLalpha: float, lm: float, category: str, altitude: float,
              CNmin: float, n_pos: float | None, VD_eas: float | None, CD_min: float | None,
              V_cruise_eas: float) -> VnDiagram:
    cat = cs22_category(category)
    n1, n2, n3, n4 = CS22_N[cat]
    notes: list[str] = []
    if n_pos is not None and n_pos > n1:
        n1 = float(n_pos)
    elif n_pos is not None and n_pos < n1 - 1e-9:
        notes.append(f"n_lim = {n_pos:.2f} < n1 = {n1:.2f} de CS 22.337 — ignorado (n1 regulamentar usado)")
    ws = W0_kg * G0 / S
    VS1 = math.sqrt(2 * ws / (RHO0 * CLmax))
    VA = VS1 * math.sqrt(n1)
    VB = VA
    vd_min = cs22_vd_min(ws, CD_min, cat)
    if VD_eas:
        VD = float(VD_eas)
        if vd_min is not None and VD < vd_min - 1e-6:
            notes.append(f"VD = {VD * 3.6:.0f} km/h < mínimo de CS 22.335(f) {vd_min * 3.6:.0f} km/h — falha")
    elif vd_min is not None:
        VD = vd_min
        notes.append(f"VD = mínimo de CS 22.335(f) com CD,min {CD_min:.4f}: {VD * 3.6:.0f} km/h EAS")
    else:
        VD = 1.25 * max(V_cruise_eas, VA)
        notes.append("VD sem valor declarado (structures.VD_eas_m_s) nem CD,min: 1,25 max(V_cruzeiro, VA) — "
                     "PRESSUPOSTO, declarar VD (VNE/0,9, CS 22.1505)")
    rho = isa(altitude).rho
    k, mu = cs22_gust_k(ws, lm, CLalpha, rho)

    def ng(V: float, U: float, s: int) -> float:
        n = 1 + s * k / 2 * RHO0 * U * V * CLalpha / ws
        return min(n, 1.25 * (V / VS1) ** 2) if s > 0 else n       # CS 22.341(b): n positivo limitado
    gust = {"Ude_VC": 15.0, "Ude_VD": 7.5, "n_VC_pos": ng(VB, 15.0, 1), "n_VC_neg": ng(VB, 15.0, -1),
            "n_VD_pos": ng(VD, 7.5, 1), "n_VD_neg": ng(VD, 7.5, -1), "n2_VD": n2, "n3_VD": n3,
            "VB_EAS_m_s": VB, "VD_min_EAS_m_s": vd_min, "lm_m": lm, "category_cs22": cat}
    clauses = ["CS 22.333 (envelope A–D–E–G; rajadas 15 m/s a VB, 7,5 m/s a VD)", "CS 22.335(a) VA = VS1 √n1",
               "CS 22.335(c) VB ≥ VA (usado VB = VA)", "CS 22.335(f) VD mínimo", f"CS 22.337 categoria {cat}",
               "CS 22.341 k = 0,96 (μ/(H/l_m))/(0,475 + μ/(H/l_m)), H = (12,17 + 0,191 μ) l_m"]
    return VnDiagram("cs_22", cat, ws, VS1, VA, VB, VD, VB, n1, n4, gust, mu, k, CLalpha, CLmax, CNmin,
                     clauses, notes)


def v_n_diagram(W0_kg: float, S: float, CLmax: float, CLalpha: float, mac: float, V_cruise_eas: float,
                category: str = "normal", regulation: str = "cs_23", altitude: float = 0.0,
                CNmin: float | None = None, n_pos: float | None = None, VH_eas: float | None = None,
                VD_eas: float | None = None, CD_min: float | None = None,
                lm: float | None = None) -> VnDiagram:
    """Flight and gust V-n envelope (see module docstring for the clauses). Speeds EAS [m/s].
    ``regulation='cs_22'`` (planadores): ``lm`` corda média geométrica S/b (None → ``mac``), ``CD_min`` para o VD
    mínimo de 22.335(f)."""
    W = W0_kg * G0
    ws = W / S
    CNmin = -0.8 * CLmax if CNmin is None else CNmin
    if regulation == "cs_22":
        return _v_n_cs22(W0_kg, S, CLmax, CLalpha, lm or mac, category, altitude, CNmin, n_pos, VD_eas, CD_min,
                         V_cruise_eas)
    nmin_reg = regulation_min_n(W0_kg, category, regulation)
    notes, clauses = [], []
    if n_pos is None:
        n_pos = nmin_reg
    elif n_pos < nmin_reg - 1e-9:
        notes.append(f"n_lim = {n_pos:.2f} < mínimo regulamentar {nmin_reg:.2f} — só aceitável com proteção de "
                     "envelope que impeça excedê-lo (USAR.337(c) / 23.337)")
    n_neg = -(0.5 if category == "aerobatic" else 0.4) * n_pos
    VS1 = math.sqrt(2 * ws / (RHO0 * CLmax))
    ws_psf = ws / PSF
    if regulation == "stanag_4671":
        VC = V_cruise_eas
        clauses += ["USAR.333 (envelope)", "USAR.335(a)(1) VC from operating requirements",
                    "USAR.335(b)(1) VD ≥ 1.25 VC", "USAR.335(c) VA ≥ VS√n", "USAR.337", "USAR.341 / USAR.333(c)",
                    "USAR.303 FS = 1.5"]
        VD = VD_eas or 1.25 * VC
    else:
        k = 36.0 if category == "aerobatic" else 33.0
        if ws_psf > 20:
            k = k + (28.6 - k) * min((ws_psf - 20) / 80, 1.0)
        VCmin = k * math.sqrt(ws_psf) * KT
        VC = max(V_cruise_eas, VCmin)
        if VH_eas:
            VC = min(VC, max(0.9 * VH_eas, V_cruise_eas))
            if VC < VCmin:
                clauses.append("23.335(a)(2): VC limited to 0.9 VH")
        fac = {"normal": 1.40, "utility": 1.50, "aerobatic": 1.55}.get(category, 1.40)
        VD = VD_eas or max(1.25 * VC, fac * VCmin)
        clauses += [f"23.333 (envelope)", f"23.335(a) VC ≥ {k:.1f}√(W/S) kt = {VCmin / KT:.0f} kt EAS",
                    f"23.335(b) VD ≥ max(1.25 VC, {fac:.2f} VC,min)", "23.335(c) VA ≥ VS√n",
                    "23.337 limit manoeuvring load factors", "23.341 gust load factors (Pratt–Walker)"]
    VA = min(VS1 * math.sqrt(n_pos), VC)
    VG = math.sqrt(2 * ws * abs(n_neg) / (RHO0 * abs(CNmin)))
    rho = isa(altitude).rho
    mu = 2 * ws / (rho * mac * CLalpha * G0)
    Kg = 0.88 * mu / (5.3 + mu)
    h_ft = altitude / FT
    if h_ft <= 20000:
        u_c, u_d = 50.0, 25.0
    else:
        f = min((h_ft - 20000) / 30000, 1.0)
        u_c, u_d = 50 - 25 * f, 25 - 12.5 * f
    u_c, u_d = u_c * FT, u_d * FT

    def ng(V, u, s):
        return 1 + s * Kg * RHO0 * u * V * CLalpha / (2 * ws)

    gust = {"Ude_VC": u_c, "Ude_VD": u_d, "n_VC_pos": ng(VC, u_c, 1), "n_VC_neg": ng(VC, u_c, -1),
            "n_VD_pos": ng(VD, u_d, 1), "n_VD_neg": ng(VD, u_d, -1)}
    # gust points above the stall line are limited by CLmax (classical envelope): report but keep design value
    vn = VnDiagram(regulation, category, ws, VS1, VA, VC, VD, VG, n_pos, n_neg, gust, mu, Kg, CLalpha, CLmax,
                   CNmin, clauses, notes)
    n_stall_VD = RHO0 * VD**2 * CLmax / (2 * ws)
    if vn.n_limit_pos > n_stall_VD:
        notes.append(f"n_lim = {vn.n_limit_pos:.2f} está acima da linha de perda mesmo a VD (n = {n_stall_VD:.2f} com "
                     "CLmax quase-estático): valor CONSERVATIVO mantido (a perda dinâmica numa rajada pode excedê-lo); "
                     "VC baixo face a VS1 — rever VC/CLmax antes de dimensionar")
    return vn


def plot_vn(vn: VnDiagram, path, title: str = ""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    V, up, lo = vn.envelope()
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ax.plot(V, up, "b-", lw=2, label="manobra")
    ax.plot(V, lo, "b-", lw=2)
    ax.plot([vn.VD, vn.VD], [lo[-1], up[-1]], "b-", lw=2)
    Vg = np.linspace(0, vn.VD, 50)
    for s in (1, -1):
        ax.plot(Vg, vn.n_gust(Vg, s), "r--", lw=1.2, label="rajada (Pratt)" if s == 1 else None)
    for nm, v in (("VS1", vn.VS1), ("VA", vn.VA), ("VC", vn.VC), ("VD", vn.VD)):
        ax.axvline(v, color="0.7", lw=0.8)
        ax.text(v, ax.get_ylim()[0] if False else vn.n_limit_neg - 0.6, nm, ha="center", fontsize=8)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("V EAS [m/s]")
    ax.set_ylabel("n [-]")
    ax.set_title(title or f"V-n ({vn.regulation}, {vn.category})")
    ax.set_ylim(vn.n_limit_neg - 1.0, vn.n_limit_pos + 1.0)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


# ---------------------------------------------------------- spanwise loading
@dataclass
class SpanLoad:
    y: np.ndarray        # semispan stations [m], root (0) to tip
    chord: np.ndarray
    lift: np.ndarray     # air load per unit span [N/m] (one side)
    inertia: np.ndarray  # structural inertia relief per unit span [N/m] (positive down)
    n: float
    source: str

    @property
    def net(self):
        return self.lift - self.inertia


def chord_at(wing, y):
    b2 = wing.span / 2
    return wing.c_root + (wing.c_tip - wing.c_root) * np.abs(y) / b2


def spanwise_lift_schrenk(wing, lift_total: float, n_stations: int = 81) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Schrenk (NACA TM 948): c_s(y) = ½[c(y) + (4S/πb)√(1−(2y/b)²)]; l(y) = L c_s(y)/S.
    Returns (y, chord, lift per unit span) on one semispan; ∫ over the full span = ``lift_total``."""
    b2 = wing.span / 2
    y = np.linspace(0, b2, n_stations)
    c = chord_at(wing, y)
    c_ell = 4 * wing.S / (math.pi * wing.span) * np.sqrt(np.clip(1 - (y / b2) ** 2, 0, None))
    cs = 0.5 * (c + c_ell)
    return y, c, lift_total * cs / wing.S


def span_load(wing, W_N: float, n: float, wing_mass_kg: float, avl_strips: list[dict] | None = None,
              n_stations: int = 81) -> SpanLoad:
    """Air load n·W (whole lift on the wing, tail load neglected — ASSUMPTION) distributed by Schrenk,
    or by the AVL strip c·cl shape when given; inertia relief of the wing mass ∝ chord."""
    y, c, l = spanwise_lift_schrenk(wing, n * W_N, n_stations)
    src = "Schrenk (NACA TM 948)"
    if avl_strips:
        ys = np.array([s["y"] for s in avl_strips if s["y"] > 0])
        ccl = np.array([s["c_cl"] for s in avl_strips if s["y"] > 0])
        if len(ys) > 3:
            shape = np.interp(y, ys, ccl, left=ccl[0], right=0.0)
            l = shape * (n * W_N / 2) / np.trapezoid(shape, y)
            src = "AVL strip loading (c·cl shape)"
    rel = n * G0 * (wing_mass_kg / 2) * c / np.trapezoid(c, y)
    return SpanLoad(y, c, l, rel, n, src)


@dataclass
class BeamLoads:
    y: np.ndarray
    shear: np.ndarray    # [N]
    moment: np.ndarray   # [N m]
    torque: np.ndarray   # [N m] about the elastic axis, + nose-up


def _cum_from_tip(y, f):
    """∫_y^{tip} f dη (trapezoidal)."""
    seg = 0.5 * (f[1:] + f[:-1]) * np.diff(y)
    out = np.zeros_like(y)
    out[:-1] = np.cumsum(seg[::-1])[::-1]
    return out


def shear_moment_diagram(load: SpanLoad, wing=None, q_dyn: float = 0.0, cm0: float = 0.0,
                         x_ea=None) -> BeamLoads:
    """V(y) = ∫ w dη, M(y) = ∫ V dη from the tip (Megson beam theory; Bruhn Ch. A).
    Torsion about the elastic axis from the lift acting at c/4 and the section pitching moment q c² cm0.
    ``x_ea`` (x/c, scalar or per station): shear-centre axis from :func:`box_section_properties` (Phase 5);
    default mid-box (x_fs + x_rs)/2 (Phases 2–4)."""
    V = _cum_from_tip(load.y, load.net)
    M = _cum_from_tip(load.y, V)
    T = np.zeros_like(V)
    if wing is not None:
        if x_ea is None:
            x_ea = 0.5 * (wing.box.front_spar_xc + wing.box.rear_spar_xc)
        t_dist = load.lift * (x_ea - 0.25) * load.chord + q_dyn * load.chord**2 * cm0
        T = _cum_from_tip(load.y, t_dist)
    return BeamLoads(load.y, V, M, T)


# -------------------------------------------------------------- box beam sizing
def naca4_half_thickness(xc, tc):
    """NACA 4-digit thickness distribution (Abbott & von Doenhoff 1959, Eq. 6.2), half thickness / c."""
    x = np.asarray(xc)
    return 5 * tc * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1015 * x**4)


@dataclass
class PanelBuckling:
    sigma_cr: float
    tau_cr: float
    applied_tau: float
    ok: bool
    note: str


def skin_panel_buckling(panel: dict, material: dict) -> PanelBuckling:
    """Long, simply supported flat plate (Bruhn Ch. C5; Timoshenko & Gere):
    σcr = k π²E/(12(1−ν²)) (t/b)², k = 4.0 (compression); τcr with k_s = 5.35 (shear).
    ``panel`` = {"t": thickness, "b": short side (rib pitch or box width), "tau": applied shear}."""
    E, nu = material["E"], material["nu"]
    f = math.pi**2 * E / (12 * (1 - nu**2)) * (panel["t"] / panel["b"]) ** 2
    s_cr, t_cr = 4.0 * f, 5.35 * f
    tau = panel.get("tau", 0.0)
    ok = tau <= t_cr
    note = "" if ok else ("τ > τcr (painel NÃO reforçado entre nervuras/longarinas): entra em tensão diagonal — reforçadores/longarinas ou núcleo sanduíche "
                          "(análise Bruhn C11 / Kuhn na Fase 3)")
    return PanelBuckling(float(s_cr), float(t_cr), float(tau), bool(ok), note)


@dataclass
class WingBoxResult:
    y: np.ndarray
    cap_area: np.ndarray      # each flange (upper and lower), [m^2]
    web_t: np.ndarray         # each spar web [m]
    skin_t: np.ndarray        # box skins [m]
    h_box: np.ndarray
    w_box: np.ndarray
    masses: dict              # [kg], both wing halves
    material: str
    nonoptimum_factor: float
    n_ult: float
    buckling: PanelBuckling | None = None
    notes: list[str] = field(default_factory=list)
    method: str = "strength"
    EI: np.ndarray | None = None   # bending stiffness about the chord-plane axis [N m^2]
    GJ: np.ndarray | None = None   # Bredt–Batho torsional stiffness [N m^2]
    details: dict = field(default_factory=dict)

    @property
    def mass(self) -> float:
        return self.masses["total"]


def box_beam_sizing(wing, loads: BeamLoads, material: str | dict = "al2024_t3", n_ult_factor: float = 1.5,
                    nonoptimum_factor: float = 1.25, rib_pitch: float | None = None, areal_density_floor: float = 0.0,
                    fuselage_width: float = 0.0) -> WingBoxResult:
    """Idealised two-spar box (Megson): ultimate loads = FS × limit loads (USAR.303 / 23.303, FS 1.5).

    * caps (upper = lower):  A = M_u / (h σ_cap)
    * spar webs (two):       t_w = (V_u/(2h) + q_T)/τ, q_T = T_u/(2 A_box) (Bredt–Batho)
    * box skins:             t_s = max(q_T/τ, t_min)
    * ribs at minimum gauge (half-solid), LE/TE skins at minimum gauge.
    Box depth = mean NACA-4 thickness at the two spar stations × 0.95 (cap centroid inset, ASSUMPTION).
    Sized from the root (y = 0): the carry-through inside the fuselage is included at the root section."""
    m = MATERIALS[material] if isinstance(material, str) else material
    y, c = loads.y, chord_at(wing, loads.y)
    tc = wing.tc_root + (wing.tc_tip - wing.tc_root) * y / (wing.span / 2)
    fs, rs = wing.box.front_spar_xc, wing.box.rear_spar_xc
    h = 0.95 * c * (naca4_half_thickness(fs, tc) + naca4_half_thickness(rs, tc))  # mean of the two spar depths
    w = (rs - fs) * c
    Mu, Vu, Tu = n_ult_factor * np.abs(loads.moment), n_ult_factor * np.abs(loads.shear), n_ult_factor * np.abs(loads.torque)
    A = np.maximum(Mu / (h * m["sigma_cap"]), m["cap_min_area"])
    qT = Tu / (2 * w * h)
    tw = np.maximum((Vu / (2 * h) + qT) / m["tau"], m["t_min_web"])
    ts = np.maximum(qT / m["tau"], m["t_min_skin"])
    rho = m["rho"]
    caps = 2 * np.trapezoid(2 * A * rho, y)
    webs = 2 * np.trapezoid(2 * h * tw * rho, y)
    box_skin = 2 * np.trapezoid(2 * w * ts * rho, y)
    perim_rest = np.maximum(2.04 * c - 2 * w, 0)
    sec_skin = 2 * np.trapezoid(perim_rest * m["t_min_skin"] * rho, y)
    skin_floor = 0.0
    if areal_density_floor:
        # user layup floor over the whole wetted wing (both surfaces), as in the weight build-up
        skin_floor = 2 * np.trapezoid(2.04 * c * areal_density_floor, y)
        if skin_floor > box_skin + sec_skin:
            box_skin, sec_skin = box_skin * skin_floor / (box_skin + sec_skin), sec_skin * skin_floor / (box_skin + sec_skin)
    pitch = rib_pitch or wing.box.rib_pitch or 0.6 * wing.mac
    n_ribs = 2 * (math.ceil((wing.span / 2) / pitch) + 1)
    rib_area = 0.685 * np.mean(tc * c**2)  # NACA 4-digit section area ≈ 0.685 t c (Abbott & von Doenhoff)
    ribs = n_ribs * 0.5 * rib_area * m["t_min_web"] * rho
    ideal = caps + webs + box_skin + sec_skin + ribs
    masses = {"caps": caps, "webs": webs, "box_skins": box_skin, "LE_TE_skins": sec_skin, "ribs": ribs,
              "ideal": ideal, "nonoptimum": (nonoptimum_factor - 1) * ideal, "total": nonoptimum_factor * ideal}
    masses = {k: float(v) for k, v in masses.items()}
    i = int(np.argmax(qT))
    buck = skin_panel_buckling({"t": ts[i], "b": min(pitch, w[i]), "tau": qT[i] / ts[i]}, m)
    notes = [m["note"], f"{n_ribs} nervuras (passo {pitch:.2f} m, espessura mínima, 50 % aligeiradas — PRESSUPOSTO)",
             f"fator não-ótimo {nonoptimum_factor:g} (juntas, fixadores, recortes — PRESSUPOSTO, Torenbeek App. C)",
             "superfícies de comando, flaps e carenagens NÃO incluídos (secundários)"]
    if not buck.ok:
        notes.append(buck.note)
    Ecap = m.get("E_cap", m["E"])
    EI = Ecap * 2 * A * (h / 2) ** 2 + m["E"] * (2 * ts * w * (h / 2) ** 2 + 2 * tw * h**3 / 12)
    GJ = bredt_gj(w, h, ts, ts, tw, m.get("G", m["E"] / (2 * (1 + m["nu"]))))
    return WingBoxResult(y, A, tw, ts, h, w, masses, m["name"], nonoptimum_factor, n_ult_factor, buck, notes,
                         "strength", EI, GJ)


def bredt_gj(w, h, t_upper, t_lower, t_web, G):
    """Single-cell Bredt–Batho torsion constant GJ = 4 A² G / ∮ ds/t (Megson Eq. 18.4), rectangular cell w × h."""
    A = w * h
    return 4 * A**2 * G / (w / t_upper + w / t_lower + 2 * h / t_web)


# ------------------------------------------------- Phase 3: stability-driven (buckling) box sizing
PLATE_K_C, PLATE_K_S = 4.0, 5.35  # long simply supported plate (Bruhn C5.2 / Timoshenko & Gere)
FARRAR_F_Z = 0.81                 # Farrar efficiency, Z-stringer panel optimum (Farrar 1949; Megson Sec. 9 / Niu)
NEEDHAM_CE = 0.342                # Needham crippling, angle units with one free edge (Z / channel), Bruhn C7.3
NEEDHAM_BT = 12.0                 # stringer flange b'/t — ASSUMPTION (typical extrusion)


def plate_buckling_stress(E, nu, t, b, k):
    """σ_cr = k π² E /(12(1−ν²)) (t/b)² (Bruhn Eq. C5.1)."""
    return k * math.pi**2 * E / (12 * (1 - nu**2)) * (t / b) ** 2


def needham_crippling(Fcy, E, bt=NEEDHAM_BT, Ce=NEEDHAM_CE):
    """Needham (1954) crippling of formed/extruded sections, Bruhn Eq. C7.6: F_cs = Ce √(Fcy E)/(b'/t)^0.75 ≤ Fcy."""
    return min(Ce * math.sqrt(Fcy * E) / bt**0.75, Fcy)


def kuhn_web(q, t, h, d, E, nu, tau_allow, Fcy, alpha_deg=45.0):
    """Kuhn incomplete diagonal tension web (NACA TR-1179; Bruhn Ch. C11), flat web, uprights at pitch d.

    τ_cr: k_s = 5.35 + 4 (b/a)² (short side b, long side a), simply supported edges (conservative).
    k = tanh(0.5 log10(τ/τ_cr)) (Bruhn Eq. C11.32); τ_max ≈ τ (1 + k² C1)(1 + k C2) with C1 = C2 ≈ 0 for
    α ≈ 45° and stiff flanges (ASSUMPTION, stated). Upright stress σ_u = k τ tan α /(A_u/(d t) + 0.5 (1 − k))
    (Bruhn Eq. C11.17, double uprights, A_ue = A_u); upright allowable = min(Needham crippling, forced crippling
    σ_0 = 26 000 k^(2/3) (t_u/t)^(1/3) psi, Bruhn Eq. C11.40 for 2024-T3 with t_u = t — ASSUMPTION).
    Returns dict with τ, τ_cr, k, required upright area A_u [m²] (0 if τ ≤ τ_cr) and ok."""
    tau = q / t
    a, b = max(h, d), min(h, d)
    tcr = plate_buckling_stress(E, nu, t, b, 5.35 + 4 * (b / a) ** 2)
    if tau <= tcr:
        return {"tau": tau, "tau_cr": tcr, "k": 0.0, "A_u": 0.0, "sigma_u": 0.0, "ok": tau <= tau_allow}
    k = math.tanh(0.5 * math.log10(tau / tcr))
    s_all = min(needham_crippling(Fcy, E), 26000 * 6894.76 * k ** (2 / 3))
    ratio = k * tau * math.tan(math.radians(alpha_deg)) / s_all - 0.5 * (1 - k)
    Au = max(ratio, 0.0) * d * t
    return {"tau": tau, "tau_cr": tcr, "k": k, "A_u": Au, "sigma_u": s_all if ratio > 0 else
            k * tau / (0.5 * (1 - k)), "ok": tau <= tau_allow}


def sandwich_core(Nx, Nxy, b, t_f, Ef, nu, core, t_lim=0.05):
    """Thinnest core so that a sandwich panel (faces t_f, simply supported, width b) satisfies
    R_c + R_s² ≤ 1 (Bruhn C5 interaction), N_cr = k π² D / b², D = E_f t_f d²/(2(1−ν²)), d = t_c + t_f
    (thin-face sandwich, Allen 1969 Eq. 2.6), k = 4 (compression), 5.35 (shear). Core shear flexibility
    neglected (ASSUMPTION; small for foam cores at these b/d). Returns (t_c, D, ok)."""
    def margin(tc):
        D = Ef * t_f * (tc + t_f) ** 2 / (2 * (1 - nu**2)) if tc > 0 else Ef * (2 * t_f) ** 3 / (12 * (1 - nu**2))
        nc, ns = PLATE_K_C * math.pi**2 * D / b**2, PLATE_K_S * math.pi**2 * D / b**2
        return Nx / nc + (Nxy / ns) ** 2
    if margin(0.0) <= 1.0:
        return 0.0, True
    lo, hi = 0.0, t_lim
    if margin(hi) > 1.0:
        return hi, False
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if margin(mid) > 1.0 else (lo, mid)
    return max(hi, core.get("t_min", 0.0)), True


def box_beam_sizing_buckling(wing, loads: BeamLoads, material: str | dict = "al2024_t3", n_ult_factor: float = 1.5,
                             nonoptimum_factor: float = 1.25, rib_pitch: float | None = None,
                             areal_density_floor: float = 0.0, n_neg_ratio: float = 0.4,
                             fuselage_width: float = 0.0) -> WingBoxResult:
    """Phase 3 stability-driven two-spar box (same layout, loads and factors as :func:`box_beam_sizing`).

    **Metal (stiffened covers, Z-stringers):** the covers carry bending, N = M_u/(h w) [N/m].
    Compression cover at the Farrar optimum σ_F = F √(N E / L), F = 0.81 (Farrar 1949), L = rib pitch, capped by
    Needham crippling of the stringers (Bruhn C7) and Fcy; smeared thickness t̄ = N/σ, skin t_s = t̄/2.5
    (A_st/(b t) = 1.5, Farrar optimum) and stringer pitch from local skin buckling at σ: b = t_s √(3.62 E/σ)
    (k = 4, Bruhn C5). Tension cover t̄ = N/Ftu, but also sized as a compression cover for the negative
    limit case (n_neg/n_pos, CS/USAR 23.337(b)). Skins ≥ q_T/Fsu and minimum gauge.
    Spar webs: Kuhn incomplete diagonal tension with uprights at d = h (:func:`kuhn_web`).
    **CFRP (caps + sandwich skins):** UD caps carry bending (A = M_u/(h σ_cap)); the skins follow the cap strain,
    σ_skin = E ε_cap, faces t_f (torsion / minimum gauge) and a foam core sized by :func:`sandwich_core`;
    face wrinkling checked with σ_wr = 0.5 (E_f E_c G_c)^(1/3) (Hoff & Mautner 1945). Webs: monolithic if
    τ ≤ τ_cr, else sandwich (shear only).
    Ribs, LE/TE skins and the non-optimum factor as in the strength box."""
    m = MATERIALS[material] if isinstance(material, str) else material
    E, nu, rho = m["E"], m["nu"], m["rho"]
    G = m.get("G", E / (2 * (1 + nu)))
    y, c = loads.y, chord_at(wing, loads.y)
    tc = wing.tc_root + (wing.tc_tip - wing.tc_root) * y / (wing.span / 2)
    fs, rs = wing.box.front_spar_xc, wing.box.rear_spar_xc
    h = 0.95 * c * (naca4_half_thickness(fs, tc) + naca4_half_thickness(rs, tc))
    w = (rs - fs) * c
    Mu, Vu, Tu = n_ult_factor * np.abs(loads.moment), n_ult_factor * np.abs(loads.shear), n_ult_factor * np.abs(loads.torque)
    L = rib_pitch or wing.box.rib_pitch or 0.6 * wing.mac
    qT = Tu / (2 * w * h)
    nst = len(y)
    composite = "E_cap" in m
    tu, tl, ts_u, ts_l = (np.zeros(nst) for _ in range(4))
    tw, Au_web, core_t, web_core = (np.zeros(nst) for _ in range(4))
    pitch_str, sig_u = np.full(nst, np.nan), np.zeros(nst)
    A = np.zeros(nst)
    kuhn_k = np.zeros(nst)
    notes = []
    tmin = m["t_min_skin"]
    if not composite:
        Fcc = needham_crippling(m["sigma_cap"], E)

        def comp_cover(N):
            if N <= 0:
                return tmin, tmin, math.nan, 0.0
            sig = min(FARRAR_F_Z * math.sqrt(N * E / L), Fcc)
            tbar = N / sig
            t_s = max(tbar / 2.5, tmin)
            tbar = max(tbar, t_s)
            b = t_s * math.sqrt(3.62 * E / sig)
            return tbar, t_s, b, sig

        for i in range(nst):
            N = Mu[i] / (h[i] * w[i])
            tbu, tsu, b, sg = comp_cover(N)
            tbl_c, tsl_c, _, _ = comp_cover(n_neg_ratio * N)
            tbl = max(N / m["sigma_tu"], tbl_c, tmin)
            tsl = max(tsl_c, tmin)
            tsu, tsl = max(tsu, qT[i] / m["tau"]), max(tsl, qT[i] / m["tau"])
            tu[i], tl[i], ts_u[i], ts_l[i], pitch_str[i], sig_u[i] = max(tbu, tsu), max(tbl, tsl), tsu, tsl, b, sg
            qw = Vu[i] / (2 * h[i]) + qT[i]
            t_web = max(qw / m["tau"], m["t_min_web"])
            kw = kuhn_web(qw, t_web, h[i], h[i], E, nu, m["tau"], m["sigma_cap"])
            tw[i], Au_web[i], kuhn_k[i] = t_web, kw["A_u"], kw["k"]
        covers = 2 * np.trapezoid((tu + tl) * w * rho, y)
        uprights = 2 * np.trapezoid(2 * Au_web * rho, y)  # 2 webs; upright A_u of length h every d = h -> A_u ρ per m
        webs = 2 * np.trapezoid(2 * h * tw * rho, y)
        caps = 0.0
        cores = 0.0
        EIa = _ei_two_covers(E, tu * w, tl * w, h) + E * 2 * tw * h**3 / 12
        GJ = bredt_gj(w, h, ts_u, ts_l, tw, G)
        A = tu * w  # equivalent "flange" area of the compression cover (for plots)
        skin_out = ts_u
        notes += [f"Revestimentos reforçados (Z): σ ótimo de Farrar F = {FARRAR_F_Z} com corte por crippling de "
                  f"Needham {Fcc / 1e6:.0f} MPa (b'/t = {NEEDHAM_BT:g} — PRESSUPOSTO); passo de reforçadores na raiz "
                  f"{pitch_str[0] * 1e3:.0f} mm (≈ {w[0] / pitch_str[0]:.0f} reforçadores/painel); σ raiz "
                  f"{sig_u[0] / 1e6:.0f} MPa",
                  f"Almas: tensão diagonal de Kuhn, k raiz = {kuhn_k[0]:.2f}, montantes a d = h (PRESSUPOSTO), "
                  "C1 = C2 ≈ 0 (α ≈ 45°, banzos rígidos — PRESSUPOSTO); admissível de τ_max = Fsu (curva Bruhn "
                  "Fig. C11.19 não digitalizada — LIMITAÇÃO)",
                  f"Banzo inferior: tração Ftu e compressão no caso negativo n_neg/n_pos = {n_neg_ratio:.2f}"]
    else:
        core = m["core"]
        Ecap = m["E_cap"]
        A = np.maximum(Mu / (h * m["sigma_cap"]), m["cap_min_area"])
        wr = 0.5 * (E * core["E"] * core["G"]) ** (1 / 3)
        wr_ok = True
        for i in range(nst):
            tf = max(qT[i] / m["tau"] / 2, tmin)  # two faces share the torsion shear flow
            eps = Mu[i] / h[i] / (Ecap * A[i] + E * 2 * tf * w[i])  # cover strain (cap + faces share M/h)
            sig_s = E * eps
            Nx, Nxy = sig_s * 2 * tf, qT[i]
            b = min(w[i], L)
            t_c, ok = sandwich_core(Nx, Nxy, b, tf, E, nu, core)
            if t_c > 0 and sig_s > wr:
                wr_ok = False
            ts_u[i] = ts_l[i] = 2 * tf
            core_t[i] = t_c
            qw = Vu[i] / (2 * h[i]) + qT[i]
            t_web = max(qw / m["tau"], m["t_min_web"])
            tcw, _ = sandwich_core(0.0, qw, min(h[i], L), t_web / 2, E, nu, core)
            tw[i], web_core[i] = t_web, tcw
        caps = 2 * np.trapezoid(2 * A * rho, y)
        covers = 2 * np.trapezoid(2 * ts_u * w * rho, y)
        cores = 2 * np.trapezoid((2 * core_t * w + 2 * web_core * h) * core["rho"], y)
        webs = 2 * np.trapezoid(2 * h * tw * rho, y)
        uprights = 0.0
        EIa = Ecap * 2 * A * (h / 2) ** 2 + E * (2 * ts_u * w * (h / 2) ** 2 + 2 * tw * h**3 / 12)
        GJ = bredt_gj(w, h, ts_u, ts_l, tw, G)
        tu, tl = ts_u, ts_l
        skin_out = ts_u
        notes += [f"Revestimentos em sanduíche: núcleo {core['name']} ρ = {core['rho']:g} kg/m³, E_c = {core['E'] / 1e6:g} "
                  f"MPa, G_c = {core['G'] / 1e6:g} MPa (PRESSUPOSTO); núcleo na raiz {core_t[0] * 1e3:.1f} mm, máx. "
                  f"{core_t.max() * 1e3:.1f} mm; interação R_c + R_s² ≤ 1 (Bruhn C5)",
                  f"Enrugamento das faces σ_wr = 0.5 (E_f E_c G_c)^(1/3) = {wr / 1e6:.0f} MPa (Hoff & Mautner) → "
                  + ("OK" if wr_ok else "FALHA em algumas estações (rever núcleo)"),
                  f"Almas: núcleo sanduíche onde τ > τ_cr (máx. {web_core.max() * 1e3:.1f} mm)"]
    # secondary items as in the strength box
    perim_rest = np.maximum(2.04 * c - 2 * w, 0)
    sec_skin = 2 * np.trapezoid(perim_rest * tmin * rho, y)
    if areal_density_floor:
        floor = 2 * np.trapezoid(2.04 * c * areal_density_floor, y)
        tot = covers + sec_skin
        if floor > tot:
            covers, sec_skin = covers * floor / tot, sec_skin * floor / tot
    n_ribs = 2 * (math.ceil((wing.span / 2) / L) + 1)
    rib_area = 0.685 * np.mean(tc * c**2)
    ribs = n_ribs * 0.5 * rib_area * m["t_min_web"] * rho
    ideal = caps + covers + cores + webs + uprights + sec_skin + ribs
    masses = {"caps": caps, "covers_skin_stringers" if not composite else "box_skins": covers, "core": cores,
              "webs": webs, "web_uprights": uprights, "LE_TE_skins": sec_skin, "ribs": ribs, "ideal": ideal,
              "nonoptimum": (nonoptimum_factor - 1) * ideal, "total": nonoptimum_factor * ideal}
    masses = {k: float(v) for k, v in masses.items()}
    j = int(np.argmax(qT))
    b_chk = min(L, w[j]) if composite else (pitch_str[j] if pitch_str[j] == pitch_str[j] else min(L, w[j]))
    buck = PanelBuckling(float(plate_buckling_stress(E, nu, skin_out[j], b_chk, PLATE_K_C)),
                         float(plate_buckling_stress(E, nu, skin_out[j], b_chk, PLATE_K_S)), float(qT[j] / skin_out[j]),
                         True, "dimensionado à encurvadura (Fase 3)")
    notes += [m["note"], f"{n_ribs} nervuras (passo {L:.2f} m)", f"fator não-ótimo {nonoptimum_factor:g} (PRESSUPOSTO)",
              "superfícies de comando, flaps e carenagens NÃO incluídos (secundários)"]
    det = {"skin_upper": ts_u, "skin_lower": ts_l, "cover_tbar_upper": tu, "cover_tbar_lower": tl,
           "stringer_pitch": pitch_str, "sigma_cover": sig_u, "web_upright_area": Au_web, "kuhn_k": kuhn_k,
           "core_t": core_t, "web_core_t": web_core}
    return WingBoxResult(y, A, tw, skin_out, h, w, masses, m["name"], nonoptimum_factor, n_ult_factor, buck, notes,
                         "buckling", EIa, GJ, det)


def _ei_two_covers(E, A_u, A_l, h):
    """Two-flange idealisation, flanges at ±h/2, neutral axis at the area centroid (Megson Ch. 16)."""
    z = (A_u - A_l) / (A_u + A_l) * h / 2
    return E * (A_u * (h / 2 - z) ** 2 + A_l * (h / 2 + z) ** 2)


def box_section_properties(wing, box: WingBoxResult, material: str | dict = "al2024_t3", le_cell: bool = True,
                           k_h: float = 0.95, camber: tuple | None = None, **section_kw) -> dict:
    """Phase 5: real section properties of the sized box at every station — idealised multi-cell section on the
    airfoil contour (Megson; :mod:`acdt.core.thinwalled`, :func:`wingbox.section.wing_section`): shear centre
    x_sc/c (the elastic axis), EI about the horizontal centroidal axis and GJ (box + optional D-nose cell of
    minimum-gauge LE skin). Metal covers: skin t_s carries shear, t̄ (skin + smeared stringers) direct stress;
    CFRP: faces + UD caps (E_cap/E). ``camber`` = (m, p) overrides the airfoil's mean line (NACA 4-digit,
    continuous — used by the Phase 5 optimiser); ``section_kw`` goes to :func:`wingbox.section.wing_section`."""
    from .wingbox.section import Contour, wing_section

    m = MATERIALS[material] if isinstance(material, str) else material
    E, nu = m["E"], m["nu"]
    G = m.get("G", E / (2 * (1 + nu)))
    det = box.details
    y = box.y
    c = chord_at(wing, y)
    tc = wing.tc_root + (wing.tc_tip - wing.tc_root) * y / (wing.span / 2)
    fs, rs = wing.box.front_spar_xc, wing.box.rear_spar_xc
    composite = "E_cap" in m
    xsc, zsc, EI, GJ = (np.zeros(len(y)) for _ in range(4))
    for i in range(len(y)):
        ct = (Contour(camber[0], camber[1], float(tc[i]), k_h) if camber is not None
              else Contour.from_airfoil(getattr(wing, "airfoil", "NACA 0012"), float(tc[i]), k_h))
        tu = float(det.get("skin_upper", box.skin_t)[i])
        tl = float(det.get("skin_lower", box.skin_t)[i])
        if composite:
            # Phase 3 A is the cap area per cover: one cap at each spar
            kw = dict(cap_area=float(box.cap_area[i]) / 2, cap_E_ratio=m["E_cap"] / E)
        else:
            kw = dict(tbar_up=float(det.get("cover_tbar_upper", box.skin_t)[i]),
                      tbar_lo=float(det.get("cover_tbar_lower", box.skin_t)[i]))
        s = wing_section(float(c[i]), ct, fs, rs, t_up=tu, t_lo=tl, t_wf=float(box.web_t[i]),
                         t_wr=float(box.web_t[i]), t_le=m["t_min_skin"] if le_cell else None, E=E, G=G, **kw, **section_kw)
        xsc[i], zsc[i], EI[i], GJ[i] = s.x_sc / c[i], s.z_sc / c[i], s.EIxx, s.GJ
    return {"x_sc_c": xsc, "z_sc_c": zsc, "EI": EI, "GJ": GJ, "le_cell": le_cell,
            "ref": "Megson multi-cell idealised section (Eq. 20.1 booms, shear centre from zero twist, Bredt–Batho "
                   "multi-cell torsion)"}


@dataclass
class StructuresResult:
    vn: VnDiagram
    load: SpanLoad
    beam: BeamLoads
    box: WingBoxResult
    wing_mass_raymer: float | None
    condition: str
    box_strength: WingBoxResult | None = None  # Phase 2 strength-only box, kept for comparison

    def summary(self) -> dict:
        return {"vn": self.vn.summary(), "condition": self.condition, "load_source": self.load.source,
                "root_shear_N": float(self.beam.shear[0]), "root_moment_Nm": float(self.beam.moment[0]),
                "root_torque_Nm": float(self.beam.torque[0]), "wing_box_mass_kg": self.box.masses,
                "wing_mass_raymer_kg": self.wing_mass_raymer,
                "box_over_raymer": (self.box.mass / self.wing_mass_raymer if self.wing_mass_raymer else None),
                "skin_buckling": vars(self.box.buckling) if self.box.buckling else None, "notes": self.box.notes,
                "box_method": self.box.method,
                "strength_box_mass_kg": self.box_strength.mass if self.box_strength is not None else None}


def wing_structure(res_like: dict) -> StructuresResult:
    """Run V-n → span load at the critical point (n_limit at VA/VC) → V/M/T → box sizing.

    ``res_like`` keys: wing, W0, CLmax, CLalpha, V_cruise_eas, category, regulation, altitude, cm0, CNmin,
    n_pos, wing_mass_raymer, material, avl_strips, VH_eas, areal_density_floor, fuselage_width, nonoptimum_factor."""
    d = res_like
    w = d["wing"]
    vn = v_n_diagram(d["W0"], w.S, d["CLmax"], d["CLalpha"], w.mac, d["V_cruise_eas"], d.get("category", "normal"),
                     d.get("regulation", "cs_23"), d.get("altitude", 0.0), d.get("CNmin"), d.get("n_pos"),
                     d.get("VH_eas"), d.get("VD_eas"), d.get("CD_min"), w.S / w.span if w.span else None)
    n = vn.n_limit_pos
    # critical bending case: positive limit n; torsion at VD (highest q) with the same n — conservative
    # combination for a first cut (PHAA/PLAA cases of Bruhn A3 treated as one envelope corner)
    V_crit = vn.VD
    cond = f"n = {n:.2f} ({vn.governing}), q a VD = {V_crit:.1f} m/s EAS"
    wm = d.get("wing_mass_raymer") or 0.0
    # massa extra distribuída na asa que alivia a flexão (p. ex. lastro de água nos tanques da asa — ∝ corda,
    # PRESSUPOSTO) e caso da massa máxima das partes não sustentadoras (TCDS de planadores): ar = (W_nlp + asa) n g,
    # alívio = asa. Fica o caso de maior momento na raiz (envolvente simples dos dois carregamentos).
    extra = float(d.get("wing_relief_extra_kg") or 0.0)
    load = span_load(w, d["W0"] * G0, n, wm + extra, d.get("avl_strips"))
    nlp = d.get("non_lifting_max_kg")
    if extra:
        cond += f"; alívio extra na asa {extra:.1f} kg (structures.wing_relief_extra_kg)"
    if nlp:
        load_nlp = span_load(w, (float(nlp) + wm) * G0, n, wm, d.get("avl_strips"))
        m_a = float(np.trapezoid((load.lift - load.inertia) * load.y, load.y))
        m_b = float(np.trapezoid((load_nlp.lift - load_nlp.inertia) * load_nlp.y, load_nlp.y))
        if m_b > m_a:
            load = load_nlp
            cond += (f"; caso das partes não sustentadoras {float(nlp):.0f} kg + asa {wm:.1f} kg governa "
                     f"(M_raiz {m_b / max(m_a, 1e-9):.2f}× o do W0)")
        else:
            cond += f"; caso W0 governa face às partes não sustentadoras {float(nlp):.0f} kg"
    qd = 0.5 * RHO0 * V_crit**2
    mat = d.get("material", "al2024_t3")

    def size(beam):
        box_s = box_beam_sizing(w, beam, mat, 1.5, d.get("nonoptimum_factor", 1.25),
                                areal_density_floor=d.get("areal_density_floor", 0.0),
                                fuselage_width=d.get("fuselage_width", 0.0))
        if d.get("box_method", "buckling") == "strength":
            return box_s, box_s
        return box_s, box_beam_sizing_buckling(
            w, beam, mat, 1.5, d.get("nonoptimum_factor", 1.25), areal_density_floor=d.get("areal_density_floor", 0.0),
            n_neg_ratio=abs(vn.n_limit_neg / vn.n_limit_pos) if vn.n_limit_pos else 0.4)

    beam = shear_moment_diagram(load, w, qd, d.get("cm0", 0.0))
    box_s, box = size(beam)
    if d.get("elastic_axis", "section") == "section":
        # Phase 5: torque about the real shear-centre axis of the sized section, re-size once, then the
        # section EI/GJ (multi-cell, airfoil contour) replace the two-flange/Bredt single-cell values
        le = d.get("le_cell", True)
        sp = box_section_properties(w, box, mat, le)
        beam = shear_moment_diagram(load, w, qd, d.get("cm0", 0.0), x_ea=sp["x_sc_c"])
        box_s, box = size(beam)
        sp = box_section_properties(w, box, mat, le)
        box.details["EI_phase3"], box.details["GJ_phase3"] = box.EI, box.GJ
        box.EI, box.GJ = sp["EI"], sp["GJ"]
        box.details["x_sc_c"], box.details["z_sc_c"] = sp["x_sc_c"], sp["z_sc_c"]
        box.notes.append(f"Eixo elástico = centro de corte da secção real (Megson, multicélula{', com bordo de ataque D' if le else ''}): "
                         f"x_sc/c raiz {sp['x_sc_c'][0]:.3f} (meio do caixão {0.5 * (w.box.front_spar_xc + w.box.rear_spar_xc):.3f}); "
                         f"EI/GJ da secção idealizada no contorno do perfil")
    if box.method == "strength" and wm and box.mass / wm < 0.5:
        box.notes.append(
            f"caixão/Raymer = {box.mass / wm:.2f}: o caixão é dimensionado só por RESISTÊNCIA (+ espessuras mínimas) e "
            "é um LIMITE INFERIOR — sem estabilidade (o revestimento não reforçado falha à encurvadura; núcleo "
            "sanduíche/reforçadores acrescentam massa), sem superfícies de comando, ligações, trem/tanques na asa. "
            "Raymer Eq. 15.46 é uma regressão de aviação geral metálica tripulada, extrapolada para esta escala. "
            "A massa real fica entre os dois; o loop usa Raymer salvo weights.components.wing_method: box")
    return StructuresResult(vn, load, beam, box, d.get("wing_mass_raymer"), cond, box_s)


def plot_wing_loads(sr: StructuresResult, path, title: str = ""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    y = sr.load.y
    fig, ax = plt.subplots(2, 2, figsize=(10, 6.5))
    yy, cc, ll = spanwise_lift_schrenk_like(sr)
    ax[0, 0].plot(y, sr.load.lift, "b-", label=f"carga aerodinâmica ({sr.load.source})")
    ax[0, 0].plot(yy, ll, "g:", label="Schrenk")
    ax[0, 0].plot(y, -sr.load.inertia, "r--", label="alívio de inércia")
    ax[0, 0].set_ylabel("N/m")
    ax[0, 0].legend(fontsize=7)
    ax[0, 1].plot(y, sr.beam.shear / 1e3, "b-")
    ax[0, 1].set_ylabel("esforço transverso V [kN]")
    ax[1, 0].plot(y, sr.beam.moment / 1e3, "b-")
    ax[1, 0].set_ylabel("momento fletor M [kN·m]")
    ax[1, 1].plot(y, sr.beam.torque, "b-")
    ax[1, 1].set_ylabel("torção T [N·m]")
    for a in ax.flat:
        a.set_xlabel("y [m]")
        a.grid(alpha=0.3)
    fig.suptitle(title or f"Cargas na asa — {sr.condition} (limite)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def spanwise_lift_schrenk_like(sr: StructuresResult):
    return spanwise_lift_schrenk(_WingProxy(sr), float(2 * np.trapezoid(sr.load.lift, sr.load.y)))


class _WingProxy:
    """Minimal wing view rebuilt from a span load (for the Schrenk overlay)."""

    def __init__(self, sr):
        y, c = sr.load.y, sr.load.chord
        self.span = 2 * y[-1]
        self.c_root, self.c_tip = c[0], c[-1]
        self.S = float(2 * np.trapezoid(c, y))


def plot_wing_box(sr: StructuresResult, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    b = sr.box
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    ax[0].plot(b.y, b.cap_area * 1e6, "b-")
    ax[0].set_ylabel("área do banzo (cada) [mm²]")
    ax[1].plot(b.y, b.web_t * 1e3, "r-", label="alma da longarina")
    ax[1].plot(b.y, b.skin_t * 1e3, "g--", label="revestimento do caixão")
    ax[1].set_ylabel("espessura [mm]")
    ax[1].legend(fontsize=8)
    for a in ax:
        a.set_xlabel("y [m]")
        a.grid(alpha=0.3)
    fig.suptitle(f"Caixão da asa ({b.material}) — massa {b.mass:.2f} kg")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
