"""Phase 6 in-loop wing-box sizing: stiffened or sandwich covers sized against buckling, spar caps from a real
spar cross-section (:mod:`acdt.core.sections`), ribs sized for crushing / shear / buckling with lightening holes,
and FEM-calibrated stiffness and stress factors (:mod:`wingbox.shell6`).

Per station (ultimate loads = 1.5 × limit; cover force P = k_σ · M_u / h, k_σ from the shell-FEM calibration,
1 before calibration; covers, stringers and caps at the same strain → σ = min of their allowables):

**Metal (stiffened skin, n_str Z-stringers per cover — a design variable).** Stringer Z of depth h_s ≤ 0.3 h,
flanges 0.4 h_s (ASSUMPTION), thickness t_st = k_t t_s, k_t ∈ {1, 1.5, 2, 3}. For each (h_s/t_st, k_t) in a grid,
the thinnest t_s (bisection)
for which σ_all·A_cover ≥ P, with σ_all = min of
  * skin between stringers, b = w/(n_str+1), long plate k = 4 with shear interaction R_c + R_s² ≤ 1,
    k_s = 5.35 + 4 (b/a)², a = rib pitch (Bruhn C5.2, C5.8) — by default required only up to LIMIT load, the skin
    then working at ultimate with the von Kármán effective width b_e = 1.9 t √(E/σ_st) (Bruhn C7.11);
    ``skin_buckling='ultimate'`` keeps it unbuckled to ultimate (full skin effective);
  * stringer crippling, Gerard two-corner (NACA TN 3784; Bruhn C7.7) ≤ F_cy;
  * stringer + skin column between ribs, Euler–Johnson parabola, fixity c = 1 (ASSUMPTION, conservative; Bruhn
    C7.15): σ = σ_cc − σ_cc²/(4π²E)·(L/ρ)² when σ_E > σ_cc/2, else σ_E = π²E/(L/ρ)², with the effective skin;
  * spar-cap allowable: crippling of the compressed half of the spar section (I, C, Z or built-up, b/t = 10 —
    ASSUMPTION) — :func:`sections.spar_cap_allowable`; F_cy.
  Lower cover: max(tension P/F_tu, compression at n_neg/n_pos). Skins ≥ q_T/F_su, minimum gauge.
  Caps: A_cap = φ_cap/(1−φ_cap) · A_cover / 2 per spar (φ_cap = cap share of the cover-plus-caps area — design
  variable).
**Composite (sandwich covers + UD caps, equivalent-isotropic CLT materials, :mod:`acdt.core.materials`).**
Design strain ε = min(F_cy/E of faces, cap allowable/E_cap, face wrinkling σ_wr/E_f with σ_wr = 0.5 (E_f E_c G_c)^⅓
(Hoff & Mautner 1945)); caps carry what the faces do not: A_cap = (P/ε − 2 t_f w E_f)/(2 E_cap). For each face
thickness t_f in a grid, the thinnest core t_c (bisection) with N_x/N_cr + (N_xy/N_xy,cr)² ≤ 1, where
N_cr = N_E/(1 + N_E/S) (core-shear-flexible sandwich panel, Allen 1969 Eq. 8.? / Zenkert 1995 §6), S = G_c d²/t_c,
N_E = k π² D/b², D = E_f t_f d²/(2(1−ν²)), d = t_c + t_f, b = box width, a = rib pitch, k = min_m (m b/a + a/(m b))²
(simply supported plate, Timoshenko & Gere §9.2) — crimping (N_x ≤ S) is the N_E → ∞ limit of the same formula.
**Webs:** q = V_u/(2h) + q_T; metal Kuhn incomplete diagonal tension (as Phase 3); composite sandwich core where
τ > τ_cr (Phase 3).
**Ribs (each rib, A3):** crushing pressure from the curved covers p = 2 σ² t̄ L/(E h) per unit chord (Niu,
*Airframe Structural Design* 1988 §5.4; the cover force N = σ t̄ turning through the curvature 2σ/(E h)), rib web as
a wide pinned column of height h: π²E t_r²/(12(1−ν²)h²) ≥ p/(t_r f_net); shear of the bay air load ΔV/2 into
each spar: τ = ΔV/(2 h t_r) ≤ F_su f_net and ≤ τ_cr f_net, τ_cr with k_s = 5.35 + 4(h/w)². Lightening holes
D/h ∈ {0, 0.25, 0.5} (D/h ≤ 0.5 — ASSUMPTION), pitch 2D: area removed π D/(8 h), net-section factor
f_net = 1 − D/(2D) = 0.5 (ASSUMPTION, conservative; NACA TN 2003 / Kuhn holes in shear webs not digitised); the
lightest option is kept. Rib flanges and stiffeners are not modelled (LIMITATION). Nose and tail parts of the rib:
minimum gauge, 50 % holes (as Phase 3)."""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from acdt.core import materials as MAT
from acdt.core import sections as SEC

Z_FLANGE = 0.4          # Z-stringer flange / depth (ASSUMPTION)
CAP_BT = 10.0           # spar-cap flange b/t (ASSUMPTION)
HOLE_DH = (0.0, 0.25, 0.5)
SPAR_TYPES = ("I", "C", "Z", "builtup")


def phase6_material(kind) -> dict:
    """Material dict for the Phase 6 sizing: 'metal' → Al 2024-T3 (library), 'composite' → CFRP equivalents, or a
    metal in structures form (dict, e.g. external data validated by ``acdt.ai.external``; isotropic only)."""
    if isinstance(kind, dict):
        if kind.get("composite"):
            raise ValueError("Phase 6: external composite equivalents are not supported (laminate + cap data "
                             "needed); use 'composite' (library CFRP) or a metal dict")
        d = dict(kind)
        d["composite"] = False
        d.setdefault("cap_min_area", 20e-6)   # same minimum cap area as the library metal
        return d
    if kind == "composite":
        d = MAT.composite_box_material()
        d["cap"] = MAT.get("cfrp_cap").as_structures_dict()
        d["composite"] = True
    else:
        d = MAT.get("al2024_t3").as_structures_dict()
        d["composite"] = False
        d["cap_min_area"] = 20e-6
    return d


@lru_cache(maxsize=4096)
def _z_crippling_ratio(t_over_h: float, E_over_F: float) -> float:
    """Gerard two-corner F_cs/F_cy of a Z with flanges Z_FLANGE·h and uniform t (scale-free: depends on t/h only)."""
    p = SEC.z_section(1.0, Z_FLANGE, t_over_h, t_over_h)
    A = p.properties()["A"]
    return min(3.2 * ((t_over_h ** 2 / A) * E_over_F ** (1 / 3)) ** 0.75, 1.0)


def _kplate(a, b):
    """Simply supported plate in compression, aspect a/b: k = min_m (m b/a + a/(m b))² (Timoshenko & Gere §9.2)."""
    r = np.maximum(a / b, 1e-6)
    m = np.maximum(np.floor(r), 1.0)
    k1 = (m / r + r / m) ** 2
    k2 = ((m + 1) / r + r / (m + 1)) ** 2
    return np.minimum(k1, k2)


def cap_geometry(kind: str, A_cap: float) -> tuple[float, float]:
    """Spar cap as an extrusion (ASSUMPTION): flange width b = CAP_BT·t_f and a vertical leg b/2 of the same
    thickness — I spar: T cap (flange b both sides of the leg), C / Z spar: angle (flange b on one side);
    built-up: two angles b/2 × b/2 back to back on the web. Returns (b, t_f) for the cap area A_cap."""
    k = 2.0 if kind == "builtup" else 1.5
    tf = math.sqrt(max(A_cap, 1e-12) / (k * CAP_BT))
    return CAP_BT * tf, tf


def cap_allowable(kind: str, h: float, A_cap: float, t_web: float, mat: dict) -> float:
    """Compressive allowable of the spar cap (:func:`cap_geometry`) — crippling (metal, Gerard/Needham) or free-flange
    local buckling (composite) of the compressed cap profile, :func:`sections.spar_cap_allowable`. The thin shear
    web next to the cap is not counted in the crippling section (its compression falls to zero at the neutral
    axis); the built-up cap includes the web between its angles."""
    capm = mat.get("cap", mat)
    if A_cap <= 0:
        return capm["sigma_cap"]
    b, tf = cap_geometry(kind, A_cap)
    tw = max(t_web, 0.3e-3) if kind == "builtup" else tf
    a = SEC.spar_cap_allowable(kind, b + tf, b, tf, tw, capm["E"], capm["sigma_cap"], capm.get("nu", 0.3),
                               composite=mat["composite"])
    return float(a["F"])


# ------------------------------------------------------------------------------------------------ metal covers
def metal_cover(P, qT, w, h, L, n_str, phi_cap, sig_cap, mat, tension=False, skin_buckling="limit", n_ult=1.5):
    """Vectorised over stations. Returns dict of t_s, h_s, A_str, A_cover (skin + stringers), A_cap, sigma (mean
    ultimate stress on cover + caps), mass (area). ``skin_buckling`` = 'limit': skin panels may buckle between
    limit and ultimate load (no buckling up to limit, σ_cr ≥ σ_u/n_ult with the limit shear — FAR 23.305 no
    detrimental deformation at limit), at ultimate the skin works with the von Kármán effective width
    b_e = 1.9 t √(E/σ_st) per bay (Bruhn C7.11) next to stringers at σ_st; 'ultimate': no skin buckling up to
    ultimate (conservative, full skin effective)."""
    E, nu, Fcy, tau, tmin = mat["E"], mat["nu"], mat["sigma_cap"], mat["tau"], mat["t_min_skin"]
    P = np.maximum(np.asarray(P, float), 0.0)
    ns = len(P)
    b = w / (n_str + 1)
    ratios = np.array([8.0, 10.0, 12.0, 15.0, 18.0, 22.0, 27.0, 33.0, 40.0]) if n_str > 0 else np.array([10.0])
    best = None
    kcap = phi_cap / max(1 - phi_cap, 1e-6) / 2
    ks = 5.35 + 4 * (np.minimum(b, L) / np.maximum(b, L)) ** 2
    kp = 4 * math.pi**2 * E / (12 * (1 - nu**2))
    combos = [(r, kt) for r in ratios for kt in ((1.0, 1.5, 2.0, 3.0) if n_str > 0 else (1.0,))]
    for r, kt in combos:
        crip = _z_crippling_ratio(round(1 / r, 5), round(E / Fcy, 1)) * Fcy

        def state(ts):
            tz = kt * ts
            hs = np.minimum(r * tz, 0.3 * h)
            A_z = tz * hs * (1 + 2 * Z_FLANGE) if n_str > 0 else 0 * ts
            A_c = w * ts + n_str * A_z
            A_cap = kcap * A_c
            A_tot = A_c + 2 * A_cap
            if tension:
                return np.full_like(ts, mat["sigma_tu"]) * A_tot >= P, A_c, A_cap, hs, A_z
            s_cr = kp * (ts / b) ** 2
            t_cr = ks / 4 * kp * (ts / b) ** 2
            # stringer (+ effective skin) allowable
            sig_s = np.full_like(ts, Fcy)
            if phi_cap > 0:
                sig_s = np.minimum(sig_s, sig_cap)
            if n_str > 0:
                sig_s = np.minimum(sig_s, crip)
                for _ in range(2):              # effective width depends on σ_st
                    be = np.minimum(b, 1.9 * ts * np.sqrt(E / sig_s)) if skin_buckling == "limit" else b
                    Ab = be * ts
                    zc = A_z * (hs / 2) / (A_z + Ab)
                    I = 0.2833 * tz * hs**3 + A_z * (hs / 2 - zc) ** 2 + Ab * zc**2
                    rho2 = I / (A_z + Ab)
                    sE = math.pi**2 * E * rho2 / L**2
                    sEJ = np.where(sE > crip / 2, crip - crip**2 / (4 * math.pi**2 * E) * L**2 / rho2, sE)
                    sig_s = np.minimum(sig_s, sEJ)
            if skin_buckling == "limit":
                be = np.minimum(b, 1.9 * ts * np.sqrt(E / sig_s))
                A_eff = n_str * A_z + (n_str + 1) * be * ts + 2 * A_cap
                Rs = np.minimum(qT / n_ult / ts / t_cr, 0.999)
                ok = (sig_s * A_eff >= P) & (s_cr * (1 - Rs**2) * A_tot >= P / n_ult)
            else:
                Rs = np.minimum(qT / ts / t_cr, 0.999)
                sig = np.minimum(sig_s, s_cr * (1 - Rs**2))
                ok = sig * A_tot >= P
            return ok, A_c, A_cap, hs, A_z

        t_lo = np.maximum(np.full(ns, tmin), qT / tau)
        lo, hi = t_lo.copy(), np.full(ns, 0.05)
        ok_lo = state(lo)[0]
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            good = state(mid)[0]
            hi = np.where(good, mid, hi)
            lo = np.where(good, lo, mid)
        ts = np.where(ok_lo, t_lo, hi)
        _, A_c, A_cap, hs, A_z = state(ts)
        mass = A_c + 2 * A_cap
        cand = {"t_s": ts, "h_s": hs, "A_str": A_z, "A_cover": A_c, "A_cap": A_cap,
                "sigma": P / np.maximum(mass, 1e-12), "mass": mass, "ratio": np.full(ns, r), "t_str": kt * ts}
        if best is None:
            best = cand
        else:
            sel = mass < best["mass"]
            best = {k: np.where(sel, cand[k], best[k]) for k in best}
    return best


# ------------------------------------------------------------------------------------------------ sandwich covers
def sandwich_cover(P, qT, w, L, eps_all, mat):
    E, nu, rho = mat["E"], mat["nu"], mat["rho"]
    core, capm = mat["core"], mat["cap"]
    Ec, Gc = core["E"], core["G"]
    P = np.maximum(np.asarray(P, float), 0.0)
    ns = len(P)
    k = _kplate(L, w)
    ks = 5.35 + 4 * (np.minimum(w, L) / np.maximum(w, L)) ** 2
    best = None
    tfs = mat["t_min_skin"] * np.array([1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.5, 8.0, 10.0])
    for tf in tfs:
        tfv = np.maximum(np.full(ns, tf), qT / mat["tau"] / 2)
        A_cap = np.maximum((P / eps_all - 2 * tfv * w * E) / (2 * capm["E"]), mat["cap_min_area"])
        eps = P / (2 * tfv * w * E + 2 * A_cap * capm["E"])          # actual cover strain (≤ ε_all)
        Nx = E * eps * 2 * tfv

        def margin(tc):
            d = tc + tfv
            D = np.where(tc > 0, E * tfv * d**2 / (2 * (1 - nu**2)), E * (2 * tfv) ** 3 / (12 * (1 - nu**2)))
            S = np.where(tc > 0, Gc * d**2 / np.maximum(tc, 1e-9), np.inf)
            NE, NsE = k * math.pi**2 * D / w**2, ks * math.pi**2 * D / w**2
            Ncr, Nscr = NE / (1 + NE / S), NsE / (1 + NsE / S)
            return Nx / Ncr + (qT / Nscr) ** 2
        zero_ok = margin(np.zeros(ns)) <= 1.0
        lo, hi = np.zeros(ns), np.full(ns, 0.06)
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            g = margin(mid) <= 1.0
            hi = np.where(g, mid, hi)
            lo = np.where(g, lo, mid)
        tc = np.where(zero_ok, 0.0, np.maximum(hi, core.get("t_min") or 0.0))
        mass = (2 * tfv * w * rho + tc * w * core["rho"]) + 2 * A_cap * capm["rho"]
        cand = {"t_f": tfv, "t_core": tc, "A_cap": A_cap, "mass_pl": mass, "eps": eps,
                "ok": (margin(tc) <= 1.0 + 1e-6).astype(float)}
        if best is None:
            best = cand
        else:
            sel = mass < best["mass_pl"]
            best = {kk: np.where(sel, cand[kk], best[kk]) for kk in best}
    return best



def _load_factor_interaction(Rc, Rs):
    """Load factor λ such that λ Rc + (λ Rs)² = 1 (compression + shear² interaction)."""
    Rc, Rs = np.asarray(Rc, float), np.asarray(Rs, float)
    out = np.full_like(Rc, np.inf, dtype=float)
    shear = np.abs(Rs) > 1e-12
    comp = (~shear) & (Rc > 1e-12)
    out[comp] = 1.0 / Rc[comp]
    disc = Rc[shear] ** 2 + 4.0 * Rs[shear] ** 2
    out[shear] = (-Rc[shear] + np.sqrt(np.maximum(disc, 0.0))) / (2.0 * Rs[shear] ** 2)
    return out


def sandwich_usage(Nx, qT, w, L, tf, tc, mat):
    """Allen/Zenkert sandwich interaction Rc + Rs² and the load reserve λ (N_cr = N_E/(1+N_E/S))."""
    E, nu = mat["E"], mat["nu"]
    Gc = mat["core"]["G"]
    k = _kplate(L, w)
    ks = 5.35 + 4 * (np.minimum(w, L) / np.maximum(w, L)) ** 2
    d = tc + tf
    D = np.where(tc > 0, E * tf * d**2 / (2 * (1 - nu**2)), E * (2 * tf) ** 3 / (12 * (1 - nu**2)))
    S = np.where(tc > 0, Gc * d**2 / np.maximum(tc, 1e-9), np.inf)
    NE = k * math.pi**2 * D / np.maximum(w, 1e-12) ** 2
    NsE = ks * math.pi**2 * D / np.maximum(w, 1e-12) ** 2
    Ncr = NE / (1 + NE / S)
    Nscr = NsE / (1 + NsE / S)
    Rc = Nx / np.maximum(Ncr, 1e-30)
    Rs = qT / np.maximum(Nscr, 1e-30)
    return Rc, Rs, _load_factor_interaction(Rc, Rs), Ncr, Nscr


def metal_skin_buckling_RF(P, qT, w, L, n_str, ts, A_tot, mat, n_ult=1.5):
    """Load reserve of the limit-load no-skin-buckling check (FAR 23.305 / metal_cover 'limit').

    At load factor λ relative to limit, λ (P/n_ult) = σ_cr (1 − (λ Rs)²) A_tot with
    Rs = (qT/n_ult) / (t_s τ_cr) and σ_cr of a simply-supported plate (Timoshenko & Gere §9.2).
    """
    E, nu = mat["E"], mat["nu"]
    b = w / (n_str + 1)
    ks = 5.35 + 4 * (np.minimum(b, L) / np.maximum(b, L)) ** 2
    kp = 4 * math.pi**2 * E / (12 * (1 - nu**2))
    s_cr = kp * (ts / np.maximum(b, 1e-12)) ** 2
    t_cr = ks / 4 * kp * (ts / np.maximum(b, 1e-12)) ** 2
    Rs = np.where(ts * t_cr > 0, (qT / n_ult) / (ts * t_cr), 0.0)
    # λ² (σ_cr Rs² A) + λ (P/n_ult) − σ_cr A = 0
    A = np.maximum(A_tot, 1e-30)
    a = s_cr * Rs ** 2 * A
    bq = P / n_ult
    c = -s_cr * A
    out = np.full_like(P, np.inf, dtype=float)
    quad = np.abs(a) > 1e-18
    lin = (~quad) & (bq > 1e-18)
    out[lin] = (s_cr * A)[lin] / bq[lin]
    disc = np.maximum(bq[quad] ** 2 - 4 * a[quad] * c[quad], 0.0)
    out[quad] = (-bq[quad] + np.sqrt(disc)) / (2 * a[quad])
    return out, s_cr, Rs


# ------------------------------------------------------------------------------------------------ ribs
def size_ribs(y_rib, sigma_c, tbar, h, w, dV, mat):
    """Box part of every rib (one semispan): t_r and hole option minimising mass. Returns arrays."""
    E, nu, tau, tmin = mat["E"], mat["nu"], mat["tau"], mat["t_min_web"]
    out = {"t": [], "D_h": [], "mass_factor": [], "p_crush": [], "governs": [],
           "t_crush": [], "t_shear": [], "t_shear_buckling": [],
           "RF_crush": [], "RF_shear": [], "RF_shear_buckling": [], "RF": []}
    for s, tb, hh, ww, dv in zip(sigma_c, tbar, h, w, dV):
        p = 2 * s**2 * tb / (E * hh)                 # [N/m per metre of rib pitch] × L below
        best = None
        for Dh in HOLE_DH:
            fnet = 1.0 if Dh == 0 else 0.5
            frac = math.pi * Dh / 8 if Dh else 0.0
            t_cr = (12 * (1 - nu**2) * hh**2 * p / (math.pi**2 * E * fnet)) ** (1 / 3) if p > 0 else 0.0
            t_sh = dv / (2 * hh * tau * fnet)
            kss = 5.35 + 4 * (min(hh, ww) / max(hh, ww)) ** 2
            t_sb = (dv / (2 * hh) * 12 * (1 - nu**2) * min(hh, ww) ** 2 / (kss * math.pi**2 * E * fnet)) ** (1 / 3)
            t = max(tmin, t_cr, t_sh, t_sb)
            gov = ["min gauge", "crushing", "shear", "shear buckling"][int(np.argmax([tmin, t_cr, t_sh, t_sb]))]
            m = t * (1 - frac)
            if best is None or m < best[0]:
                best = (m, t, Dh, 1 - frac, gov, t_cr, t_sh, t_sb)
        t = best[1]
        t_cr, t_sh, t_sb = best[5], best[6], best[7]
        # load reserve: crushing and shear buckling size as t³ (wide-column / plate), shear strength as t
        rf_c = (t / t_cr) ** 3 if t_cr > 1e-12 else math.inf
        rf_s = t / t_sh if t_sh > 1e-12 else math.inf
        rf_b = (t / t_sb) ** 3 if t_sb > 1e-12 else math.inf
        rf = min(rf_c, rf_s, rf_b)
        out["t"].append(t)
        out["D_h"].append(best[2])
        out["mass_factor"].append(best[3])
        out["p_crush"].append(p)
        out["governs"].append(best[4])
        out["t_crush"].append(t_cr)
        out["t_shear"].append(t_sh)
        out["t_shear_buckling"].append(t_sb)
        out["RF_crush"].append(rf_c)
        out["RF_shear"].append(rf_s)
        out["RF_shear_buckling"].append(rf_b)
        out["RF"].append(rf)
    return {k: (np.array(v) if k != "governs" else v) for k, v in out.items()}


# ------------------------------------------------------------------------------------------------ calibration
class Calibration:
    """Shell-FEM → beam factors on the normalised span η = (y − y0)/(s − y0): k_EI, k_GJ (FEM/section), shear-centre
    offset Δx_sc/c (FEM − section) and the cover-force factor k_σ (FEM cover force / (M/h)). Identity by default."""

    def __init__(self, eta=None, k_EI=None, k_GJ=None, dx_sc=None, k_sigma=None, source="none"):
        self.eta = np.array([0.0, 1.0]) if eta is None else np.asarray(eta, float)
        one = np.ones_like(self.eta)
        self.k_EI = one if k_EI is None else np.asarray(k_EI, float)
        self.k_GJ = one if k_GJ is None else np.asarray(k_GJ, float)
        self.dx_sc = 0 * one if dx_sc is None else np.asarray(dx_sc, float)
        self.k_sigma = one if k_sigma is None else np.asarray(k_sigma, float)
        self.source = source

    def at(self, name, eta):
        return np.interp(eta, self.eta, getattr(self, name))

    def to_dict(self):
        ga = getattr(self, "GA", None)
        return {"GA_N": None if ga is None else [float(v) for v in ga],"eta": self.eta.tolist(), "k_EI": self.k_EI.tolist(), "k_GJ": self.k_GJ.tolist(),
                "dx_sc_c": self.dx_sc.tolist(), "k_sigma": self.k_sigma.tolist(), "source": self.source}


# ------------------------------------------------------------------------------------------------ full box
def size_box6(wing, beam, mat, x, *, y0=0.0, n_ult=1.5, nonopt=1.25, n_neg_ratio=0.4, areal_floor=0.0,
              calib: Calibration | None = None, spar_type="I", camber=None, skin_buckling="limit"):
    """Size the Phase 6 box on the beam loads (limit) for design ``x`` (needs xf, xr, tc_root, tc_tip, rib_pitch,
    k_skin, phi_cap, n_str). Returns a :class:`structures.WingBoxResult` (Phase 3 field conventions)."""
    from .. import structures as S
    calib = calib or Calibration()
    y = beam.y
    c = S.chord_at(wing, y)
    s = wing.span / 2
    eta = np.clip((y - y0) / (s - y0), 0, 1)
    tc = wing.tc_root + (wing.tc_tip - wing.tc_root) * y / s
    fs, rs = x["xf"], x["xr"]
    h = 0.95 * c * (S.naca4_half_thickness(fs, tc) + S.naca4_half_thickness(rs, tc))
    w = (rs - fs) * c
    L = x["rib_pitch"]
    Mu, Vu, Tu = (n_ult * np.abs(a) for a in (beam.moment, beam.shear, beam.torque))
    ks = calib.at("k_sigma", eta)
    P = ks * Mu / h
    qT = Tu / (2 * w * h)
    E, nu, rho, G = mat["E"], mat["nu"], mat["rho"], mat["G"]
    tmin = mat["t_min_skin"]
    comp = mat["composite"]
    ns = len(y)
    qw = Vu / (2 * h) + qT
    tw = np.maximum(qw / mat["tau"], mat["t_min_web"])
    det = {"spar_type": spar_type, "n_str": int(x.get("n_str", 0)), "phi_cap": float(x.get("phi_cap", 0.0)),
           "k_sigma": ks}
    if not comp:
        n = int(round(x.get("n_str", 0)))
        phi = float(x.get("phi_cap", 0.15))
        sig_cap = np.full(ns, mat["sigma_cap"])
        for _ in range(2):
            up = metal_cover(P, qT, w, h, L, n, phi, sig_cap, mat, skin_buckling=skin_buckling, n_ult=n_ult)
            sig_cap = np.array([cap_allowable(spar_type, hh, a, t, mat) for hh, a, t in zip(h, up["A_cap"], tw)])
        lo_t = metal_cover(P, qT, w, h, L, n, phi, sig_cap, mat, tension=True)
        lo_c = metal_cover(n_neg_ratio * P, qT, w, h, L, n, phi, sig_cap, mat, skin_buckling=skin_buckling,
                           n_ult=n_ult)
        sel = lo_t["mass"] >= lo_c["mass"]
        lo = {k: np.where(sel, lo_t[k], lo_c[k]) for k in lo_t}
        Au, Al = up["A_cover"], lo["A_cover"]
        A_cap = np.maximum(np.maximum(up["A_cap"], lo["A_cap"]), mat["cap_min_area"] if phi > 0 else 0.0)
        ts_u, ts_l = up["t_s"], lo["t_s"]
        k = x.get("k_skin", 1.0)
        ts_u, ts_l = ts_u * k, ts_l * k
        Au, Al = Au + (k - 1) * up["t_s"] * w, Al + (k - 1) * lo["t_s"] * w
        Au_web, kk = np.zeros(ns), np.zeros(ns)
        for i in range(ns):
            kw = S.kuhn_web(qw[i], tw[i], h[i], h[i], E, nu, mat["tau"], mat["sigma_cap"])
            Au_web[i], kk[i] = kw["A_u"], kw["k"]
        covers = 2 * np.trapezoid((Au + Al) * rho, y)
        caps = 2 * np.trapezoid(4 * A_cap * rho, y)
        uprights = 2 * np.trapezoid(2 * Au_web * rho, y)
        webs = 2 * np.trapezoid(2 * h * tw * rho, y)
        cores = 0.0
        core_t, web_core = np.zeros(ns), np.zeros(ns)
        sig_u = P / np.maximum(Au + 2 * A_cap, 1e-12)
        det.update({"h_str": up["h_s"], "A_str": up["A_str"], "stringer_pitch": w / (n + 1), "cap_allow": sig_cap,
                    "web_upright_area": Au_web, "kuhn_k": kk, "cover_sigma_allow": up["sigma"]})
        tbu, tbl = Au / w, Al / w
        cover_key = "covers_skin_stringers"
        E_cap = E
    else:
        capm = mat["cap"]
        wr = 0.5 * (E * mat["core"]["E"] * mat["core"]["G"]) ** (1 / 3)
        sig_cap = np.full(ns, capm["sigma_cap"])
        for _ in range(2):
            eps_all = np.minimum.reduce([np.full(ns, mat["sigma_cap"] / E), sig_cap / capm["E"], np.full(ns, wr / E)])
            up = sandwich_cover(P, qT, w, L, eps_all, mat)
            sig_cap = np.array([cap_allowable(spar_type, hh, a, t, mat) for hh, a, t in zip(h, up["A_cap"], tw)])
        k = x.get("k_skin", 1.0)
        tf = up["t_f"] * k
        A_cap = up["A_cap"]
        ts_u = ts_l = 2 * tf
        core_t = up["t_core"]
        web_core = np.zeros(ns)
        for i in range(ns):
            web_core[i], _ = S.sandwich_core(0.0, qw[i], min(h[i], L), tw[i] / 2, E, nu, mat["core"])
        covers = 2 * np.trapezoid(2 * 2 * tf * w * rho, y)
        cores = 2 * np.trapezoid((2 * core_t * w + 2 * web_core * h) * mat["core"]["rho"], y)
        caps = 2 * np.trapezoid(4 * A_cap * capm["rho"], y)
        webs = 2 * np.trapezoid(2 * h * tw * rho, y)
        uprights = 0.0
        sig_u = E * up["eps"]
        tbu = tbl = 2 * tf
        det.update({"cap_allow": sig_cap, "eps_cover": up["eps"], "eps_allow": eps_all, "sandwich_ok": up["ok"],
                    "stringer_pitch": np.full(ns, np.nan)})
        cover_key = "box_skins"
        E_cap = capm["E"]
    # LE/TE skins, floor
    perim_rest = np.maximum(2.04 * c - 2 * w, 0)
    sec_skin = 2 * np.trapezoid(perim_rest * tmin * rho, y)
    if areal_floor:
        floor = 2 * np.trapezoid(2.04 * c * areal_floor, y)
        tot = covers + sec_skin
        if floor > tot:
            covers, sec_skin = covers * floor / tot, sec_skin * floor / tot
    # ribs
    n_bays = max(1, math.ceil((s - y0) / L - 1e-6))
    y_rib = np.linspace(y0, s, n_bays + 1)
    Lr = (s - y0) / n_bays
    net = -np.gradient(beam.shear, y) * n_ult                     # ultimate running net load [N/m]
    dV = np.abs(np.interp(y_rib, y, net)) * Lr
    rib_s = np.interp(y_rib, y, np.abs(sig_u))
    rib_tb = np.interp(y_rib, y, tbu)
    rib_h, rib_w, rib_c = np.interp(y_rib, y, h), np.interp(y_rib, y, w), np.interp(y_rib, y, c)
    ribs6 = size_ribs(y_rib, rib_s, rib_tb * Lr, rib_h, rib_w, dV, mat)      # p uses t̄ L (force per chord)
    tc_r = np.interp(y_rib, y, tc)
    box_part = ribs6["t"] * ribs6["mass_factor"] * rib_w * rib_h * rho
    rest = np.maximum(0.685 * tc_r * rib_c**2 - rib_w * rib_h, 0) * mat["t_min_web"] * 0.5 * rho
    ribs = 2 * float(np.sum(box_part + rest))
    ideal = caps + covers + cores + webs + uprights + sec_skin + ribs
    masses = {"caps": caps, cover_key: covers, "core": cores, "webs": webs, "web_uprights": uprights,
              "LE_TE_skins": sec_skin, "ribs": ribs, "ideal": ideal, "nonoptimum": (nonopt - 1) * ideal,
              "total": nonopt * ideal}
    masses = {kk_: float(v) for kk_, v in masses.items()}
    det.update({"skin_upper": ts_u, "skin_lower": ts_l, "cover_tbar_upper": tbu, "cover_tbar_lower": tbl,
                "sigma_cover": sig_u, "core_t": core_t, "web_core_t": web_core, "cap_each": A_cap, "E_cap": E_cap,
                "ribs": {"y": y_rib.tolist(), "h_m": rib_h.tolist(), "w_m": rib_w.tolist(), "dV_N": dV.tolist(),
                         "t_mm": (ribs6["t"] * 1e3).tolist(), "t_m": ribs6["t"].tolist(),
                         "D_h": ribs6["D_h"].tolist(), "mass_factor": ribs6["mass_factor"].tolist(),
                         "box_part_kg": box_part.tolist(), "rest_kg": rest.tolist(),
                         "governs": ribs6["governs"], "p_crush_N_m": ribs6["p_crush"].tolist(),
                         "RF": [float(v) for v in ribs6["RF"]],
                         "RF_crush": [float(v) for v in ribs6["RF_crush"]],
                         "RF_shear": [float(v) for v in ribs6["RF_shear"]],
                         "RF_shear_buckling": [float(v) for v in ribs6["RF_shear_buckling"]]},
                "n_ribs_semispan": int(n_bays + 1), "rib_pitch_actual": float(Lr)})
    if "web_upright_area" not in det:
        det["web_upright_area"], det["kuhn_k"] = np.zeros(ns), np.zeros(ns)
    # numeric buckling reserve (load factor to the interaction = 1); min-gauge panels/ribs have RF > 1
    rib_rf = np.asarray(ribs6["RF"], float)
    if comp:
        capm = mat["cap"]
        eps_act = P / np.maximum(2 * tf * w * E + 2 * A_cap * capm["E"], 1e-30)
        Nx = E * eps_act * 2 * tf
        Rc, Rs, rf_sk, _, _ = sandwich_usage(Nx, qT, w, L, tf, core_t, mat)
        skin_kind = "sandwich (Allen/Zenkert interaction, load factor)"
    else:
        A_tot = Au + 2 * A_cap
        rf_sk, _, _ = metal_skin_buckling_RF(P, qT, w, L, int(x.get("n_str", 0)), ts_u, A_tot, mat, n_ult=n_ult)
        skin_kind = "metal skin at limit (FAR 23.305 / plate interaction, load factor)"
    rf_sk = np.asarray(rf_sk, float)
    det["buckling_reserve"] = {
        "skin_kind": skin_kind,
        "skin_RF": [float(v) for v in rf_sk],
        "skin_RF_min": float(np.nanmin(rf_sk)) if rf_sk.size else math.nan,
        "skin_y_m": [float(v) for v in y],
        "rib_RF": [float(v) for v in rib_rf],
        "rib_RF_min": float(np.nanmin(rib_rf)) if rib_rf.size else math.nan,
        "rib_governs": list(ribs6["governs"]),
        "note": "RF é o factor de carga até à envolvente de encurvadura (pele) ou até à carga que esgota "
                "o critério dimensionante da nervura (encurvadura de corte ∝ t³, esmagamento ∝ t³, "
                "corte ∝ t). RF > 1 nas estações à bitola mínima.",
    }
    notes = [f"Fase 6: {'sanduíche + banzos UD' if comp else f'{det['n_str']} reforçadores Z/revestimento'}, "
             f"longarina {spar_type}, φ_cap {det['phi_cap']:.2f}, {n_bays + 1} nervuras dimensionadas"]
    box = S.WingBoxResult(y, 2 * A_cap, tw, ts_u, h, w, masses, mat["name"], nonopt, n_ult, None, notes, "phase6",
                          None, None, det)
    return box


def section6(wing, box, mat, camber=None, calib: Calibration | None = None, y0=0.0, le_cell=True, raw=False,
             n_cover=10, n_web=4, n_le=12):
    """Megson multi-cell section on the contour (D-nose cell, caps as booms, stringers smeared in t̄) → x_sc/c, EI,
    GJ, then the FEM calibration (k_EI, k_GJ, Δx_sc) unless ``raw``."""
    from .. import structures as S
    from .section import Contour, wing_section
    det = box.details
    y = box.y
    c = S.chord_at(wing, y)
    s = wing.span / 2
    tc = wing.tc_root + (wing.tc_tip - wing.tc_root) * y / s
    fs, rs = wing.box.front_spar_xc, wing.box.rear_spar_xc
    E, G = mat["E"], mat["G"]
    xsc, zsc, EI, GJ = (np.zeros(len(y)) for _ in range(4))
    for i in range(len(y)):
        ct = (Contour(camber[0], camber[1], float(tc[i])) if camber is not None
              else Contour.from_airfoil(getattr(wing, "airfoil", "NACA 0012"), float(tc[i])))
        tu, tl = float(det["skin_upper"][i]), float(det["skin_lower"][i])
        sec = wing_section(float(c[i]), ct, fs, rs, t_up=tu, t_lo=tl, t_wf=float(box.web_t[i]), t_wr=float(box.web_t[i]),
                           tbar_up=float(det["cover_tbar_upper"][i]), tbar_lo=float(det["cover_tbar_lower"][i]),
                           cap_area=float(det["cap_each"][i]), cap_E_ratio=det["E_cap"] / E,
                           t_le=mat["t_min_skin"] if le_cell else None, E=E, G=G, n_cover=n_cover, n_web=n_web,
                           n_le=n_le)
        xsc[i], zsc[i], EI[i], GJ[i] = sec.x_sc / c[i], sec.z_sc / c[i], sec.EIxx, sec.GJ
    out = {"x_sc_c_raw": xsc.copy(), "EI_raw": EI.copy(), "GJ_raw": GJ.copy(), "z_sc_c": zsc, "le_cell": le_cell}
    if not raw and calib is not None:
        eta = np.clip((y - y0) / (s - y0), 0, 1)
        EI = EI * calib.at("k_EI", eta)
        GJ = GJ * calib.at("k_GJ", eta)
        xsc = xsc + calib.at("dx_sc", eta)
        if getattr(calib, "GA", None) is not None:
            out["GA"] = np.interp(eta, calib.eta, calib.GA)     # FEM transverse-shear stiffness (deflection only)
    out.update({"x_sc_c": xsc, "EI": EI, "GJ": GJ})
    return out
