"""Fase 2 — aerodinâmica de baixa fidelidade (``assumptions.aero.fidelity: lowfi``).

Chain (each step is a classical, cited method; nothing is fitted to the answer):

1. **Section polar** — XFOIL 6.99 (Drela 1989, panel + e^N boundary layer) at the cruise Reynolds
   number of the MAC, transition forced at x/c = ``laminar.wing`` (the same laminar fraction used by
   the handbook build-up, so both are comparable); NeuralFoil (Sharpe 2024) as fallback.
2. **Section clmax** — XFOIL clmax at the *stall* Reynolds number (V_S at the current wing loading,
   free transition, Ncrit 9) replaces the user ``clmax_airfoil`` in Raymer Eq. 12.15/12.21
   (CLmax = 0.9 clmax cos Λ + flap increments).
3. **Span loading and induced drag** — AVL 3.40 (Drela & Youngren) vortex lattice on the parametric
   geometry at two angles of attack; strip cl(y) is linear in CL (basic + additional loading,
   cf. Abbott & von Doenhoff Sec. 8.4), and AVL's Trefftz-plane span efficiency e_inv gives
   CDi = CL²/(π A e_inv). Fuselage correction e = e_inv (1 − 2 (d/b)²) (Kroo, *Aircraft Design:
   Synthesis and Analysis*, Stanford, "Lift-dependent drag"). Without AVL the Schrenk loading
   (NACA TM 948) is used for cl(y) and the Raymer Oswald factor is kept for CDi.
4. **Wing profile drag** — strip integration CDp,wing(CL) = Σ cd(cl_i) S_i / S_ref over the *exposed*
   strips (|y| > fuselage radius), × interference Q_wing; replaces the Cf·FF·Q·Swet wing term of
   Raymer Eq. 12.24. Other components keep the handbook build-up; the leakage/protuberance fraction
   is applied to the total, as in the handbook path.
5. **Parabolic polar** — least-squares fit CD = CD0 + K CL² over CL ∈ [0.1, 0.85 CLmax]
   (the representation used by the constraint/mission equations); the fit residual is reported.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .airfoil import airfoil_polar, xfoil_available
from .avl import avl_available, run_avl_case
from .interfaces import ToolNotAvailable


@dataclass
class LowFiAero:
    CD0: float
    K: float
    e_eff: float               # 1/(π A K) of the fitted parabola
    e_inv: float | None        # AVL Trefftz span efficiency
    e_fuselage: float
    clmax_airfoil: float
    clmax_Re: float
    cm0: float
    cruise_Re: float
    CDp_wing_at_cruise: float
    wing_handbook_CD0: float   # Raymer wing term it replaces (incl. Q, before lp)
    fit_rms: float
    CL_grid: list = field(default_factory=list)
    CD_grid: list = field(default_factory=list)
    CD_handbook_grid: list = field(default_factory=list)
    airfoil_source: str = ""
    span_source: str = ""
    polar_cruise: object | None = None
    polar_stall: object | None = None
    avl_CLa: float | None = None
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {"CD0": self.CD0, "K": self.K, "e_eff": self.e_eff, "e_inv_AVL": self.e_inv,
                "e_fuselage_factor": self.e_fuselage, "clmax_airfoil": self.clmax_airfoil,
                "clmax_Re": self.clmax_Re, "cm0_airfoil": self.cm0, "cruise_Re": self.cruise_Re,
                "CDp_wing_cruise": self.CDp_wing_at_cruise, "wing_CD0_handbook": self.wing_handbook_CD0,
                "fit_rms": self.fit_rms, "airfoil_source": self.airfoil_source, "span_source": self.span_source,
                "AVL_CLalpha": self.avl_CLa, "notes": self.notes}


class _RePolar:
    """Section polar at an arbitrary Re, interpolated in log(Re) between the two neighbouring cached
    polars on a 2-significant-figure Re grid (keeps the MDA fixed point continuous in Re)."""

    def __init__(self, airfoil, Re, mach, xtr, prefer):
        e = math.floor(math.log10(Re)) - 1
        step = 10.0**e
        lo = math.floor(Re / step) * step
        hi = lo + step
        self.lo = airfoil_polar(airfoil, lo, mach, xtr=xtr, prefer=prefer)
        self.hi = airfoil_polar(airfoil, hi, mach, xtr=xtr, prefer=prefer)
        self.w = (math.log(Re) - math.log(lo)) / (math.log(hi) - math.log(lo))
        self.Re = Re
        self.source = self.lo.source
        self.cl, self.cd = self.lo.cl, self.lo.cd  # for plotting

    def _mix(self, a, b):
        return (1 - self.w) * a + self.w * b

    @property
    def clmax(self):
        return self._mix(self.lo.clmax, self.hi.clmax)

    @property
    def cm0(self):
        return self._mix(self.lo.cm0, self.hi.cm0)

    @property
    def alpha0_deg(self):
        """Zero-lift angle [deg], the same linear fit as ``AirfoilPolar.alpha0_deg``, mixed in log(Re)."""
        return self._mix(self.lo.alpha0_deg, self.hi.alpha0_deg)

    def cd_min(self):
        return self._mix(self.lo.cd_min(), self.hi.cd_min())

    def cd_at_cl(self, cl):
        return self._mix(self.lo.cd_at_cl(cl), self.hi.cd_at_cl(cl))


# Tempo-limite das corridas AVL do modelo de faixas: 1.ª tentativa e repetição (s). Uma falha transitória (p.ex.
# tempo-limite com a máquina sobrecarregada) não deve trocar silenciosamente AVL por Schrenk numa iteração do ciclo
# W0: isso desloca o ponto fixo convergido (até ~tol_lowfi) e torna o resultado dependente da carga da máquina.
AVL_TIMEOUTS_S = (60.0, 180.0)


def _avl_pair(config, mach: float):
    """As duas corridas AVL (alpha 2° e 6°), repetidas uma vez com tempo-limite maior se a 1.ª tentativa falhar."""
    last: Exception | None = None
    for tmo in AVL_TIMEOUTS_S:
        try:
            return (run_avl_case(config, alpha_deg=2.0, mach=mach, timeout=tmo),
                    run_avl_case(config, alpha_deg=6.0, mach=mach, timeout=tmo))
        except ToolNotAvailable:
            raise
        except Exception as ex:  # noqa: BLE001 - qualquer falha da corrida externa conta como tentativa falhada
            last = ex
    assert last is not None
    raise last


def _strip_cl_model(config, mach: float, fus_d: float):
    """Return (y, area, cl_fun(CL), e_inv, CLa_avl, source) for the exposed wing strips."""
    w = config.wing
    if avl_available():
        try:
            r1, r2 = _avl_pair(config, mach)
            y = np.array([s["y"] for s in r1.strips])
            A = np.array([s["area"] for s in r1.strips])
            c1 = np.array([s["cl"] for s in r1.strips])
            c2 = np.array([s["cl"] for s in r2.strips])
            m = np.abs(y) > fus_d / 2
            dCL = r2.CL - r1.CL
            slope = (c2 - c1) / dCL
            e_inv = 0.5 * (r1.e + r2.e)
            return (y[m], A[m], lambda CL: c1[m] + slope[m] * (CL - r1.CL), e_inv,
                    dCL / math.radians(4.0), "AVL 3.40 (VLM), 2 ângulos")
        except Exception as ex:  # pragma: no cover - AVL failure
            src_note = f"AVL falhou após {len(AVL_TIMEOUTS_S)} tentativas ({ex}); Schrenk usado"
    else:
        src_note = "AVL não instalado; Schrenk (NACA TM 948) usado"
    from ..structures import spanwise_lift_schrenk
    n = 60
    yb = np.linspace(0, w.span / 2, n + 1)
    yh = 0.5 * (yb[1:] + yb[:-1])
    yy, c, l = spanwise_lift_schrenk(w, w.S)  # lift_total = S → l(y) = c_s(y)
    ch, cs = np.interp(yh, yy, c), np.interp(yh, yy, l)
    m = yh > fus_d / 2
    y = np.concatenate([-yh[m][::-1], yh[m]])
    area = np.concatenate([(ch * np.diff(yb))[m][::-1], (ch * np.diff(yb))[m]])
    shape = cs[m] / ch[m]  # local cl / CL = c_s / c (Schrenk)
    shape = np.concatenate([shape[::-1], shape])
    return y, area, (lambda CL: CL * shape), None, None, src_note


def lowfi_aero(config, buildup, V: float, rho: float, mu: float, a: float, AR: float, laminar_wing: float,
               Q_wing: float, lp_fraction: float, CLmax_wing: float, V_stall: float, e_handbook: float,
               prefer: str = "xfoil", calibration: dict | None = None) -> LowFiAero:
    """``calibration``: Phase-4 factors to apply (hifi/calibration.py ``load``): ``k_clmax`` × section clmax,
    ``k_cd_profile`` × section cd, ``d_cm0`` + section cm0."""
    w, fus = config.wing, config.fuselage
    cal = calibration or {}
    k_cl, k_cd, d_cm = cal.get("k_clmax", 1.0), cal.get("k_cd_profile", 1.0), cal.get("d_cm0", 0.0)
    airfoil = getattr(w, "airfoil", None) or "NACA 0012"
    mach = V / a
    Re = rho * V * w.mac / mu
    notes = []
    src = "XFOIL 6.99" if (prefer == "xfoil" and xfoil_available()) else "NeuralFoil"
    pol = _RePolar(airfoil, Re, round(mach, 2), max(laminar_wing, 0.01), prefer)
    Re_s = rho * V_stall * w.mac / mu
    pol_s = _RePolar(airfoil, Re_s, round(V_stall / a, 2), 1.0, prefer)
    src = getattr(pol, "source", src)
    if not math.isfinite(pol_s.clmax):
        raise ToolNotAvailable("section clmax not found")
    y, area, cl_fun, e_inv, CLa_avl, span_src = _strip_cl_model(config, mach, fus.max_diameter)
    if span_src and not span_src.startswith("AVL 3"):
        notes.append(span_src)
    S = w.S
    f_other = sum(c.f for c in buildup.components if c.name != "wing") + buildup.misc_dq
    wing_c = [c for c in buildup.components if c.name == "wing"][0]
    wing_hb = wing_c.f / S
    d_b = fus.max_diameter / w.span
    e_fus = 1 - 2 * d_b**2
    if e_inv is not None:
        K_i = 1 / (math.pi * AR * e_inv * e_fus)
    else:
        K_i = 1 / (math.pi * AR * e_handbook)
        notes.append(f"CDi com Oswald Raymer e = {e_handbook:.3f} (sem AVL)")

    def cdp_wing(CL):
        cl = cl_fun(CL)
        cd = np.array([pol.cd_at_cl(c) for c in cl])
        cd = k_cd * np.where(np.isfinite(cd), cd, pol.cd_min() * 3)
        return Q_wing * float(np.sum(cd * area)) / S

    CLs = np.linspace(0.1, 0.85 * CLmax_wing, 12)
    CD = np.array([(f_other / S + cdp_wing(c)) * (1 + lp_fraction) + K_i * c**2 for c in CLs])
    Mx = np.vstack([np.ones_like(CLs), CLs**2]).T
    (CD0, K), *_ = np.linalg.lstsq(Mx, CD, rcond=None)
    rms = float(np.sqrt(np.mean((Mx @ [CD0, K] - CD) ** 2)))
    e_eff = 1 / (math.pi * AR * K)
    CDhb = buildup.CD0 + CLs**2 / (math.pi * AR * e_handbook)
    notes.append(f"perfil {airfoil}: Re cruzeiro {Re:.2e} (xtr = {laminar_wing:.2f}), clmax a Re_stall {Re_s:.2e} "
                 f"(transição livre, Ncrit 9)")
    if pol_s.clmax > 1.9:
        notes.append("clmax XFOIL > 1.9: XFOIL tende a sobrestimar clmax em perfis espessos/alto Re — verificar com "
                     "dados experimentais (Abbott & von Doenhoff)")
    if cal:
        notes.append("calibração Fase 4 aplicada: " + ", ".join(f"{k} = {v:.3f}" for k, v in cal.items()
                                                                 if k in ("k_clmax", "k_cd_profile", "d_cm0")))
    return LowFiAero(float(CD0), float(K), float(e_eff), e_inv, e_fus, float(k_cl * pol_s.clmax), Re_s,
                     float(pol.cm0 + d_cm), Re,
                     cdp_wing(0.5), wing_hb, rms, CLs.tolist(), CD.tolist(), CDhb.tolist(), src,
                     span_src if span_src.startswith("AVL 3") else "Schrenk (NACA TM 948)", pol, pol_s, CLa_avl,
                     notes)


def plot_lowfi(lf: LowFiAero, path, title: str = ""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    p = lf.polar_cruise
    if p is not None:
        ax[0].plot(p.cd, p.cl, "b-", label=f"cruzeiro Re {lf.cruise_Re:.2g}")
    if lf.polar_stall is not None:
        ax[0].plot(lf.polar_stall.cd, lf.polar_stall.cl, "r--", label=f"stall Re {lf.clmax_Re:.2g}")
    ax[0].set_xlabel("cd")
    ax[0].set_ylabel("cl")
    ax[0].set_title(f"Polar do perfil ({lf.airfoil_source})")
    ax[0].legend(fontsize=8)
    ax[0].set_xlim(0, 0.04)
    CL = np.array(lf.CL_grid)
    ax[1].plot(lf.CD_grid, CL, "bo", ms=4, label="baixa fidelidade (faixas + CDi AVL)")
    ax[1].plot(lf.CD0 + lf.K * CL**2, CL, "b-", label=f"ajuste CD0 {lf.CD0:.4f}, e {lf.e_eff:.3f}")
    ax[1].plot(lf.CD_handbook_grid, CL, "k--", label="manual (Raymer 12.24 + Oswald)")
    ax[1].set_xlabel("CD")
    ax[1].set_ylabel("CL")
    ax[1].set_title(title or "Polar do avião")
    ax[1].legend(fontsize=7)
    for a_ in ax:
        a_.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
