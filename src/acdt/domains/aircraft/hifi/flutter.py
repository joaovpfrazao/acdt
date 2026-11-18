"""Phase 4 flutter: CalculiX normal modes + doublet-lattice unsteady aerodynamics (PanelAero, DLR — Rodden,
Giesing & Kálmán 1968/1971 DLM with the VLM steady part) + p-k method (Hassig, J. Aircraft 8(11) 1971), and the
certification margin check. A Nastran SOL 145 deck of the same model is written with pyNastran for an
independent run elsewhere.

Spline: beam spline — every rib/station section is rigid chordwise (ribs), so the plunge and pitch of a section
come from the front/rear spar mid-height lines of the FEM: h(x, y) = w_f(y) + (x − x_f)(w_r − w_f)/(x_r − x_f)
(Rodden, *Theoretical and Computational Aeroelasticity* 2011, Ch. 6). Inboard of the FEM root (fuselage) the
wing is rigid. Cantilever modes (fuselage/rigid-body freedoms not modelled — as the Phase 3 strip model).

Sign conventions: z up, x aft; downwash w = −(∂h/∂x + i k h), k = ω/V (dimensional, PanelAero); Δcp = Q_jj w;
panel force +z = q A Δcp.

Margin (legacy 14 CFR 23.629 / AC 23.629-1B practice, CS-23 Amdt 4 CS 23.2245 'sufficiently beyond', STANAG
4671 USAR.629 — verify the applicable basis): flutter-free up to 1.2 V_D with the V-g curves computed with zero
structural damping not crossing g = +0.03 (the structural damping that may be assumed); g = 0 crossing also
reported."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from ..aero.interfaces import ToolNotAvailable

DLM_REF = ("PanelAero (DLR, BSD-3): DLM Rodden et al. 1968/1971 + VLM; p-k: Hassig 1971; "
           "beam spline: Rodden 2011 Ch. 6")
G_ALLOW = 0.03
KR = (0.001, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.45, 0.6, 0.8, 1.0, 1.3, 1.7, 2.2)


def aero_grid(wing, nx: int = 8, ny_half: int = 20) -> dict:
    """Flat DLM panel grid of the full wing, panels ordered left → right (PanelAero convention)."""
    s = wing.span / 2
    tanL = math.tan(wing.sweep_at(0.0))
    eta = 0.5 * (1 - np.cos(np.linspace(0, math.pi, 2 * ny_half + 1)))  # cosine, fine at tips and root
    ys = -s + 2 * s * eta
    P1, P3, J, Lp, K, A, N, l = ([] for _ in range(8))
    for j in range(len(ys) - 1):
        ya, yb = ys[j], ys[j + 1]
        ym = 0.5 * (ya + yb)
        for i in range(nx):
            def xat(y, f):
                c = wing.c_root + (wing.c_tip - wing.c_root) * abs(y) / s
                return abs(y) * tanL + f * c
            f0, f1 = i / nx, (i + 1) / nx
            xa0, xa1, xb0, xb1 = xat(ya, f0), xat(ya, f1), xat(yb, f0), xat(yb, f1)
            ch = 0.5 * ((xa1 - xa0) + (xb1 - xb0))
            P1.append([xa0 + 0.25 * (xa1 - xa0), ya, 0.0])
            P3.append([xb0 + 0.25 * (xb1 - xb0), yb, 0.0])
            xm0, xm1 = xat(ym, f0), xat(ym, f1)
            J.append([xm0 + 0.75 * (xm1 - xm0), ym, 0.0])
            Lp.append([xm0 + 0.25 * (xm1 - xm0), ym, 0.0])
            K.append([xm0 + 0.5 * (xm1 - xm0), ym, 0.0])
            A.append(ch * (yb - ya))
            N.append([0.0, 0.0, 1.0])
            l.append(ch)
    a = lambda v: np.array(v, float)  # noqa: E731
    return {"n": len(A), "offset_P1": a(P1), "offset_P3": a(P3), "offset_j": a(J), "offset_l": a(Lp),
            "offset_k": a(K), "A": a(A), "N": a(N), "l": a(l)}


def spline_modes(modes: dict, pts: np.ndarray, y0: float, sym: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Mode heave h and slope ∂h/∂x at points (x, y) from the spar-line shapes (beam spline)."""
    y = np.asarray(modes["y"])
    xf, xr = np.asarray(modes["x_f"]), np.asarray(modes["x_r"])
    H = np.zeros((len(pts), len(modes["shapes"])))
    S = np.zeros_like(H)
    ay = np.abs(pts[:, 1])
    sg = np.ones(len(pts)) if sym else np.sign(pts[:, 1])
    inb = ay < y0
    xf_p, xr_p = np.interp(ay, y, xf), np.interp(ay, y, xr)
    for k, sh in enumerate(modes["shapes"]):
        wf = np.interp(ay, y, sh["wf"])
        wr = np.interp(ay, y, sh["wr"])
        sl = (wr - wf) / (xr_p - xf_p)
        h = wf + (pts[:, 0] - xf_p) * sl
        h[inb], sl[inb] = 0.0, 0.0
        H[:, k], S[:, k] = sg * h, sg * sl
    return H, S


def gaf(grid: dict, modes: dict, y0: float, mach: float, cref: float, sym: bool = True, kr=KR) -> dict:
    """Generalised aerodynamic forces Q_hh(k) (per unit q) on the *semispan* basis of the mass-normalised
    cantilever modes (full-span aerodynamics ÷ 2)."""
    try:
        from panelaero import DLM
    except ImportError as ex:  # pragma: no cover
        raise ToolNotAvailable("PanelAero not installed (pip install PanelAero)") from ex
    Hj, Sj = spline_modes(modes, grid["offset_j"], y0, sym)
    Hl, _ = spline_modes(modes, grid["offset_l"], y0, sym)
    Q = []
    for k in kr:
        kd = 2 * k / cref
        Qjj = DLM.calc_Qjj(grid, mach, kd)
        w = -(Sj + 1j * kd * Hj)
        cp = Qjj @ w
        Q.append(0.5 * (Hl * grid["A"][:, None]).T @ cp)
    return {"kr": np.array(kr), "Q": np.array(Q), "b": cref / 2}


def pk_flutter(freqs_hz, Qd: dict, V_list, rho: float = 1.225, damping=None, max_it: int = 60) -> dict:
    """p-k (Hassig): [p² I + K − q Q^R(k) − (q b / (V k)) Q^I(k) p] u = 0 per mode, k = Im(p) b / V iterated.
    Mass-normalised modes (M = I). Returns frequency [Hz] and g = 2 Re(p)/Im(p) per mode and speed."""
    w = 2 * math.pi * np.asarray(freqs_hz)
    n = len(w)
    K = np.diag(w**2)
    kr, Qs, b = Qd["kr"], Qd["Q"], Qd["b"]

    def Qat(k):
        k = min(max(k, kr[0]), kr[-1])
        re = np.array([[np.interp(k, kr, Qs[:, i, j].real) for j in range(n)] for i in range(n)])
        im = np.array([[np.interp(k, kr, Qs[:, i, j].imag) for j in range(n)] for i in range(n)])
        return re, im

    F = np.full((len(V_list), n), np.nan)
    G = np.full((len(V_list), n), np.nan)
    prev = [complex(0, wi) for wi in w]
    for iv, V in enumerate(V_list):
        q = 0.5 * rho * V**2
        for m in range(n):
            p_ref = prev[m]
            k = max(abs(p_ref.imag) * b / V, kr[0])
            p_sel = p_ref
            for _ in range(max_it):
                QR, QI = Qat(k)
                A = np.block([[np.zeros((n, n)), np.eye(n)], [-(K - q * QR), q * b / (V * k) * QI]])
                lam = np.linalg.eigvals(A)
                cand = lam[lam.imag > 1e-6] if np.any(lam.imag > 1e-6) else lam
                p_sel = cand[np.argmin(np.abs(cand - p_ref))]
                k_new = max(abs(p_sel.imag) * b / V, kr[0])
                if abs(k_new - k) < 1e-5 * max(k, 1e-3):
                    k = k_new
                    break
                k = 0.5 * (k + k_new)
            prev[m] = p_sel
            F[iv, m] = abs(p_sel.imag) / (2 * math.pi)
            G[iv, m] = 2 * p_sel.real / abs(p_sel.imag) if abs(p_sel.imag) > 1e-9 else np.sign(p_sel.real) * 9
    return {"V": np.asarray(V_list), "f": F, "g": G}


def crossing(V, g, level: float) -> tuple[float, int]:
    """Lowest speed where any mode's g rises through ``level`` (linear interpolation)."""
    best, mode = math.inf, -1
    for m in range(g.shape[1]):
        for i in range(1, len(V)):
            a, b_ = g[i - 1, m], g[i, m]
            if np.isfinite(a) and np.isfinite(b_) and a < level <= b_:
                Vc = V[i - 1] + (V[i] - V[i - 1]) * (level - a) / (b_ - a)
                if Vc < best:
                    best, mode = float(Vc), m
                break
    return best, mode


def flutter_margin_check(VF_g003: float, VF_g0: float, VD: float, factor: float = 1.2) -> dict:
    Vreq = factor * VD
    return {"V_required": Vreq, "V_F_g0": VF_g0, "V_F_g003": VF_g003,
            "margin_g003": VF_g003 / Vreq - 1 if math.isfinite(VF_g003) else math.inf,
            "ok": bool(VF_g003 >= Vreq), "basis": f"{factor:g} V_D, g ≤ {G_ALLOW} (AC 23.629-1B prática; verificar)"}


def run_flutter(res, fem_out: dict, work: str | Path, V_max_factor: float = 2.5, nV: int = 60,
                include=("bending", "torsion")) -> dict:
    """FEM modes (from :func:`fem.run_box_fem`) → DLM → p-k, symmetric and antisymmetric, EAS at sea level."""
    from ....core.atmosphere import isa

    modes = fem_out.get("modes")
    if not modes:
        raise ToolNotAvailable("no FEM modes (run fem.run_box_fem with the frequency step)")
    keep = [i for i, t in enumerate(fem_out["mode_types"]) if t in include]
    md = {**modes, "shapes": [modes["shapes"][i] for i in keep]}
    fr = [fem_out["frequencies_Hz"][i] for i in keep]
    w = res.config.wing
    VD = res.structures.vn.VD
    mach = min(VD / isa(0.0).a, 0.7)
    grid = aero_grid(w)
    y0 = fem_out["meta"]["y0"]
    Vs = np.linspace(0.1 * VD, V_max_factor * VD, nV)
    out = {"VD_eas": VD, "mach_dlm": mach, "modes_used": [fem_out["mode_types"][i] for i in keep], "freqs_Hz": fr,
           "panels": grid["n"], "ref": DLM_REF}
    for sym in (True, False):
        Qd = gaf(grid, md, y0, mach, w.mac, sym)
        pk = pk_flutter(fr, Qd, Vs)
        V0, m0 = crossing(pk["V"], pk["g"], 0.0)
        V3, m3 = crossing(pk["V"], pk["g"], G_ALLOW)
        key = "symmetric" if sym else "antisymmetric"
        out[key] = {"V": pk["V"].tolist(), "f": pk["f"].tolist(), "g": pk["g"].tolist(), "V_F_g0": V0,
                    "mode_g0": m0, "V_F_g003": V3, "mode_g003": m3,
                    "f_F_Hz": float(pk["f"][np.searchsorted(pk["V"], V3) - 1, m3]) if m3 >= 0 else None}
    V3 = min(out["symmetric"]["V_F_g003"], out["antisymmetric"]["V_F_g003"])
    V0 = min(out["symmetric"]["V_F_g0"], out["antisymmetric"]["V_F_g0"])
    out["margin"] = flutter_margin_check(V3, V0, VD)
    if res.aeroelastic is not None:
        out["strip_V_F"] = res.aeroelastic.flutter["V_F"]
    Path(work).mkdir(parents=True, exist_ok=True)
    (Path(work) / "flutter_results.json").write_text(json.dumps(out, indent=1, default=float))
    return out


def plot_vgf(fl: dict, path, title: str = ""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    for c, key in enumerate(("symmetric", "antisymmetric")):
        d = fl[key]
        V, f, g = np.array(d["V"]), np.array(d["f"]), np.array(d["g"])
        for m in range(f.shape[1]):
            lab = f"{fl['modes_used'][m]} {fl['freqs_Hz'][m]:.1f} Hz"
            ax[0, c].plot(V, f[:, m], label=lab)
            ax[1, c].plot(V, g[:, m], label=lab)
        for a in ax[:, c]:
            a.axvline(fl["VD_eas"], color="k", ls="--", lw=0.8)
            a.axvline(1.2 * fl["VD_eas"], color="r", ls=":", lw=0.8)
            a.grid(alpha=0.3)
        ax[1, c].axhline(G_ALLOW, color="r", lw=0.8)
        ax[1, c].axhline(0, color="k", lw=0.6)
        ax[1, c].set_ylim(-0.5, 0.2)
        ax[0, c].set_title(f"{'simétrico' if key == 'symmetric' else 'antissimétrico'}: V_F(g=0.03) = "
                           f"{d['V_F_g003']:.0f} m/s EAS")
        ax[1, c].set_xlabel("V EAS [m/s]")
    ax[0, 0].set_ylabel("f [Hz]")
    ax[1, 0].set_ylabel("g")
    ax[0, 0].legend(fontsize=7)
    fig.suptitle(title or "Flutter p-k: modos CalculiX + DLM (PanelAero)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return str(path)
