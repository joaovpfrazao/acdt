# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Análise de gelo genérica (esquema ``acdt.icing/1``) para qualquer tipo de aeronave (docs/GELO.md).

Para cada condição de voo (altitude-pressão, velocidade, duração) e cada superfície (diâmetro de referência
d = 2 r_le), varre o Apêndice C (envelopes contínuo/intermitente/descolagem, temperaturas do envelope a essa altitude
e MVD 15–40 µm) e calcula na linha de estagnação: temperatura total, captação (Langmuir & Blodgett), fração de
congelação e tipo de gelo (Messinger), espessura acumulada e potência de proteção.

Completude (desconhecido ≠ zero, não avaliado ≠ passa): cada grandeza é um intervalo ``{lo, hi}`` do **caso
crítico** (máximo sobre o varrimento):

* espessura: ``hi`` com β₀/0,953, ρ_i = 0,9 × 917 kg/m³ (incerteza «talvez até 10 %» de Anderson, Eq. A.27) e a
  condição inteira em gelo (HE = V·τ, F ajustado); ``lo`` com β₀/1,0023, ρ_i = 917 kg/m³ e exposição só à
  distância padrão (17,4/2,6 nmi), limitada à duração;
* potência: ``lo`` = running-wet a 0 °C; ``hi`` = evaporativo à T_s declarada (ou densidade do aquecedor declarada),
  senão ``None``;
* tempo de exposição: ``lo`` = Σ exposições à distância padrão, ``hi`` = Σ durações das condições no envelope;
* fora das tabelas/gamas → ``None`` com a razão; ``fronteira``/``possivel`` do envelope altitude–temperatura contam
  para ``hi`` mas não para ``lo``.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from acdt.core.atmosphere import isa

from . import envelopes as env
from . import properties as pr
from .accretion import stagnation
from .impingement import naca4_le_radius
from .penalty import penalty
from .protection import protection_power

SCHEMA = "acdt.icing/1"
RHO_ICE_LO = 0.9 * pr.RHO_ICE
KINDS = ("continuous", "intermittent", "takeoff")
PROTECTIONS = ("none", "anti_ice_thermal", "deice_electrothermal", "boots")


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def surface_d(s: Mapping[str, Any]) -> tuple[float, str]:
    """Dimensão característica d [m] = 2 r_le (Anderson §3.2) ou diâmetro do cilindro."""
    if _f(s.get("d_m")):
        return float(s["d_m"]), "d_m declarado"
    if _f(s.get("le_radius_m")):
        return 2.0 * float(s["le_radius_m"]), "2 × le_radius_m declarado"
    c, t = _f(s.get("chord_m")), _f(s.get("t_c"))
    if c and t:
        return 2.0 * naca4_le_radius(t, c), ("2 r_le, r_le = 1,1019 t² c (Abbott & von Doenhoff, NACA 4 dígitos) — "
                                             "PRESSUPOSTO se o perfil não for NACA de 4 dígitos")
    raise ValueError(f"superfície {s.get('id')!r}: dê d_m, le_radius_m ou chord_m + t_c")


def _imax(vals: list[float | None]) -> float | None:
    """Máximo de uma lista com desconhecidos: qualquer None → None (o máximo pode ser esse)."""
    if not vals:
        return 0.0
    if any(v is None for v in vals):
        return None
    return max(v for v in vals if v is not None)


def _sum(vals: list[float | None]) -> float | None:
    if any(v is None for v in vals):
        return None
    return float(sum(v for v in vals if v is not None))


def _cases(cond: Mapping[str, Any], kinds: list[str], mvds: list[float]) -> list[dict[str, Any]]:
    alt = float(cond.get("altitude_m", 0.0) or 0.0)
    out: list[dict[str, Any]] = []
    for k in ([str(cond["envelope"])] if cond.get("envelope") else kinds):
        if k == "takeoff":
            if alt / env.FT <= env.TAKEOFF["height_agl_ft"] + 1e-6 and cond.get("phase") in (None, "takeoff",
                                                                                               "descolagem"):
                out.append({"kind": k, "T_C": env.TAKEOFF["T_C"], "mvd_um": env.TAKEOFF["mvd_um"],
                            "status": "dentro"})
            continue
        Tc = _f(cond.get("T_C"))
        temps = [Tc] if Tc is not None else env.envelope_temperatures(k, alt)
        for T in temps:
            assert T is not None
            st = env.in_envelope(k, alt, T)
            if st == "fora":
                continue
            for m in mvds:
                out.append({"kind": k, "T_C": T, "mvd_um": m, "status": st})
    return out


def analyse(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Executa a análise de gelo genérica. Ver docs/GELO.md §5.2 para o esquema."""
    kinds = [str(k) for k in (spec.get("envelopes") or ["continuous", "intermittent"])]
    for k in kinds:
        if k not in KINDS:
            raise ValueError(f"envelope desconhecido: {k!r} ({', '.join(KINDS)})")
    mvds = [float(m) for m in (spec.get("mvd_um") or env.MVDS_UM)]
    conds = list(spec.get("conditions") or [])
    surfs = list(spec.get("surfaces") or [])
    if not conds or not surfs:
        raise ValueError("a especificação de gelo precisa de conditions e surfaces")
    notes: list[str] = []
    res_conds: dict[str, Any] = {}
    exp_lo: list[float | None] = []
    exp_hi: list[float | None] = []
    surf_out: dict[str, Any] = {}
    for s in surfs:
        prot = str(s.get("protection", "none"))
        if prot not in PROTECTIONS:
            raise ValueError(f"superfície {s.get('id')!r}: proteção {prot!r} ({', '.join(PROTECTIONS)})")
        d, dsrc = surface_d(s)
        surf_out[str(s["id"])] = {"d_m": d, "d_source": dsrc, "protection": prot, "by_condition": {},
                                  "lifting": bool(s.get("lifting", False)), "critical": bool(s.get("critical", True))}
    for c in conds:
        cn = str(c["name"])
        alt = float(c.get("altitude_m", 0.0) or 0.0)
        V = float(c["V_m_s"])
        dur = _f(c.get("duration_s"))
        a = isa(alt, float(c.get("isa_dT_K", 0.0) or 0.0))
        p_st = float(c.get("p_st_Pa") or a.p)
        cases = _cases(c, kinds, mvds)
        in_lo = any(x["status"] == "dentro" for x in cases)
        tau_std: float | None = None
        if cases and dur is not None:
            std_he = min(env.STANDARD_HE_NMI.get(x["kind"], 0.0) for x in cases if x["kind"] != "takeoff") \
                if any(x["kind"] != "takeoff" for x in cases) else None
            tau_std = dur if std_he is None else min(dur, std_he * env.NMI / max(V, 1e-9))
        exp_hi.append(dur if cases else 0.0)
        exp_lo.append((tau_std if in_lo else 0.0) if cases else 0.0)
        res_conds[cn] = {"altitude_m": alt, "V_m_s": V, "duration_s": dur, "p_st_Pa": p_st,
                         "T_tot_C_at_envelope": None, "n_cases": len(cases),
                         "envelope_status": sorted({x["status"] for x in cases}) or ["fora"],
                         "exposure_s": {"lo": exp_lo[-1], "hi": exp_hi[-1]}}
        if not cases:
            for sid in surf_out:
                surf_out[sid]["by_condition"][cn] = {"in_envelope": False, "thickness_mm": {"lo": 0.0, "hi": 0.0},
                                                     "power_W": {"lo": 0.0, "hi": 0.0}}
            continue
        Ttot = [pr.total_temperature(pr.T0 + x["T_C"], V) - pr.T0 for x in cases]
        res_conds[cn]["T_tot_C_at_envelope"] = {"lo": min(Ttot), "hi": max(Ttot)}
        for s in surfs:
            sid = str(s["id"])
            so = surf_out[sid]
            d = so["d_m"]
            th_lo: list[float | None] = []
            th_hi: list[float | None] = []
            p_lo: list[float | None] = []
            p_hi: list[float | None] = []
            worst: dict[str, Any] | None = None
            cnotes: set[str] = set()
            for x in cases:
                kind = x["kind"]
                try:
                    stg = stagnation(T_st=pr.T0 + x["T_C"], V=V, d_m=d, mvd_m=x["mvd_um"] * 1e-6,
                                     lwc_kg_m3=1e-3, p_st=p_st)
                except ValueError as ex:
                    cnotes.add(str(ex))
                    th_lo.append(None), th_hi.append(None), p_lo.append(None), p_hi.append(None)
                    continue
                tau_hi = dur
                if kind == "intermittent" and dur is not None:
                    # Fig. 6 só define F até ≈ 5 nmi: o encontro intermitente fica limitado a 5 nmi (o resto da
                    # condição é coberto pelo envelope contínuo; encontros mistos não são combinados — nota)
                    tau_hi = min(dur, env.INTERMITTENT_F[-1][0] * env.NMI / max(V, 1e-9))
                    if tau_hi < dur:
                        cnotes.add("intermitente máximo limitado a 5 nmi (Fig. 6); encontros mistos contínuo+"
                                   "intermitente não combinados")
                he_full = None if tau_hi is None else V * tau_hi / env.NMI
                L_hi = env.design_lwc(kind, x["T_C"], x["mvd_um"], he_full if kind != "takeoff" else None,
                                      short_bound=True)
                L_lo = env.design_lwc(kind, x["T_C"], x["mvd_um"], None)
                if L_hi.note:
                    cnotes.add(L_hi.note)
                lwc_hi = L_hi.lwc_g_m3
                lwc_lo = L_lo.lwc_g_m3
                # recalcula com o LWC de projeto (b, n₀ e ṁ dependem do LWC)
                stg_hi = stagnation(T_st=pr.T0 + x["T_C"], V=V, d_m=d, mvd_m=x["mvd_um"] * 1e-6,
                                    lwc_kg_m3=(lwc_hi or 0.0) * 1e-3, p_st=p_st) if lwc_hi else None
                stg_lo = stagnation(T_st=pr.T0 + x["T_C"], V=V, d_m=d, mvd_m=x["mvd_um"] * 1e-6,
                                    lwc_kg_m3=(lwc_lo or 0.0) * 1e-3, p_st=p_st) if lwc_lo else None
                ok_lo = x["status"] == "dentro"
                if tau_hi is None or lwc_hi is None:
                    t_hi = None
                elif stg_hi is None:
                    t_hi = 0.0
                else:
                    b_hi = stg_hi.imp.beta0_hi
                    t_hi = stg_hi.n0 * b_hi * lwc_hi * 1e-3 * V * float(tau_hi or 0.0) / RHO_ICE_LO
                tau_k = None if dur is None else (dur if kind == "takeoff" else
                                                   min(dur, env.STANDARD_HE_NMI[kind] * env.NMI / max(V, 1e-9)))
                if not ok_lo or tau_k is None or lwc_lo is None or stg_lo is None:
                    t_lo: float | None = 0.0 if (not ok_lo or stg_lo is None) and lwc_lo is not None else None
                else:
                    t_lo = stg_lo.n0 * stg_lo.imp.beta0_lo * lwc_lo * 1e-3 * V * tau_k / pr.RHO_ICE
                th_lo.append(None if t_lo is None else t_lo * 1e3)
                th_hi.append(None if t_hi is None else t_hi * 1e3)
                if so["protection"] != "none":
                    pp = protection_power(so["protection"], stg_hi or stg, d_m=d, V=V,
                                          area_m2=_f(s.get("protected_area_m2")),
                                          surface_temperature_C=_f(s.get("surface_temperature_C")),
                                          parting_strip_area_m2=float(s.get("parting_strip_area_m2", 0.0) or 0.0),
                                          duty_cycle=_f(s.get("duty_cycle")),
                                          power_density_W_m2=_f(s.get("power_density_W_m2")),
                                          electric=s.get("electric"))
                    cnotes.update(pp.notes)
                    p_lo.append(pp.power_W["lo"])
                    p_hi.append(pp.power_W["hi"])
                    so["electric"] = pp.electric
                if t_hi is not None and stg_hi is not None and (worst is None or t_hi * 1e3 > worst["thickness_hi_mm"]):
                    worst = {"envelope": kind, "T_C": x["T_C"], "mvd_um": x["mvd_um"], "lwc_g_m3": lwc_hi,
                             "F": L_hi.F, "he_nmi": L_hi.he_used_nmi, "K0": stg_hi.imp.K0, "beta0": stg_hi.imp.beta0,
                             "n0": stg_hi.n0, "n0_analytic": stg_hi.n0_raw, "ice_type": stg_hi.ice_type,
                             "b": stg_hi.b, "phi_K": stg_hi.phi, "theta_K": stg_hi.theta, "h_c_W_m2K": stg_hi.h_c,
                             "T_tot_C": stg_hi.T_tot - pr.T0, "accretion_rate_mm_min": stg_hi.accretion_rate_m_s * 6e4,
                             "thickness_hi_mm": t_hi * 1e3, "status": x["status"]}
            entry: dict[str, Any] = {"in_envelope": True,
                                     "thickness_mm": {"lo": _imax(th_lo), "hi": _imax(th_hi)},
                                     "critical_case": worst, "notes": sorted(cnotes)}
            if so["protection"] != "none":
                entry["power_W"] = {"lo": _imax(p_lo), "hi": _imax(p_hi)}
            else:
                entry["power_W"] = {"lo": 0.0, "hi": 0.0}
            so["by_condition"][cn] = entry
    # ---- agregados
    max_unprot: list[float | None] = []
    max_unprot_lo: list[float | None] = []
    tot_lo: list[float | None] = []
    tot_hi: list[float | None] = []
    el_lo: list[float | None] = []
    el_hi: list[float | None] = []
    for sid, so in surf_out.items():
        tl = [e["thickness_mm"]["lo"] for e in so["by_condition"].values()]
        thh = [e["thickness_mm"]["hi"] for e in so["by_condition"].values()]
        # acreção acumulada ao longo da missão (superfície sem proteção não liberta gelo): majorante = soma das
        # condições (todas em gelo); minorante = o maior encontro padrão isolado. PRESSUPOSTO: geometria limpa
        # (β₀ e h_c não mudam com o gelo acumulado — Anderson §3.4)
        so["thickness_mm"] = {"lo": _imax(tl), "hi": _sum(thh)}
        pl = [e["power_W"]["lo"] for e in so["by_condition"].values()]
        ph = [e["power_W"]["hi"] for e in so["by_condition"].values()]
        so["power_W"] = {"lo": _imax(pl), "hi": _imax(ph)}
        if so["protection"] == "none":
            max_unprot.append(so["thickness_mm"]["hi"])
            max_unprot_lo.append(so["thickness_mm"]["lo"])
            so["residual_ice"] = "acreção sem proteção"
        else:
            so["residual_ice"] = "desconhecido (gelo de retorno/intercíclico não modelado)"
        tot_lo.append(so["power_W"]["lo"])
        tot_hi.append(so["power_W"]["hi"])
        if so.get("electric"):
            el_lo.append(so["power_W"]["lo"])
            el_hi.append(so["power_W"]["hi"])
        if so["lifting"]:
            lo, hi = so["thickness_mm"]["lo"], so["thickness_mm"]["hi"]
            if so["protection"] == "none":
                iced = True if (lo or 0.0) > 0 else (False if hi == 0.0 else None)
            else:
                iced = None
            so["penalty"] = penalty(iced)
    lo_unp = [v for v in max_unprot_lo if v is not None]
    out: dict[str, Any] = {
        "schema": SCHEMA, "evaluated": True,
        "envelopes": kinds, "mvd_um": mvds, "conditions": res_conds, "surfaces": surf_out,
        "exposure_s": {"lo": _sum(exp_lo), "hi": _sum(exp_hi)},
        "exposure_min": {"lo": None if _sum(exp_lo) is None else float(_sum(exp_lo) or 0.0) / 60.0,
                         "hi": None if _sum(exp_hi) is None else float(_sum(exp_hi) or 0.0) / 60.0},
        "max_thickness_mm": {"lo": max(lo_unp) if len(lo_unp) == len(max_unprot_lo) and lo_unp else
                             (0.0 if not max_unprot_lo else None), "hi": _imax(max_unprot)},
        "protection": {"power_W": {"lo": _sum(tot_lo), "hi": _sum(tot_hi)},
                       "electrical_power_W": {"lo": _sum(el_lo), "hi": _sum(el_hi)}},
        "notes": notes,
        "methods": {"envelopes": env.SOURCE_LWC + "; " + env.SOURCE_F + "; " + env.SOURCE_TO + "; " + env.SOURCE_ALT,
                    "impingement": "Langmuir & Blodgett (1946) via Anderson NASA/CR-2004-212875 Eq. (3.5)–(3.13)",
                    "heat_balance": "Messinger (1953) via Anderson NASA/CR-2004-212875 Eq. (3.26)–(3.59), Ap. A",
                    "penalty": "Broeren et al. NASA/TP-2011-216929 (2011)"},
    }
    mt = out["max_thickness_mm"]
    out["max_thickness_m"] = {k: (None if mt[k] is None else mt[k] * 1e-3) for k in ("lo", "hi")}
    out["fiki"] = fiki_assessment(spec.get("fiki"), out)
    return out


def fiki_assessment(declared: Any, out: Mapping[str, Any]) -> dict[str, Any]:
    """«Voo em gelo conhecido» declarado: ``falha`` se alguma superfície crítica sem proteção acumula gelo
    (minorante > 0); nunca ``passa`` a este nível (a certificação exige demonstração — 14 CFR 25.1419); senão
    ``desconhecido``."""
    if declared is None:
        return {"declared": None, "verdict": None, "reason": "não declarado"}
    want = str(declared).lower() in ("true", "yes", "sim", "1")
    if not want:
        return {"declared": False, "verdict": None, "reason": "voo em gelo conhecido não pretendido: só relatado"}
    bad = [sid for sid, so in out["surfaces"].items() if so["critical"] and so["protection"] == "none"
           and (so["thickness_mm"]["lo"] or 0.0) > 0.0]
    if bad:
        return {"declared": True, "verdict": False, "reason": f"superfícies críticas sem proteção com gelo: {bad}"}
    return {"declared": True, "verdict": None, "reason": "análise L0 não demonstra voo em gelo conhecido "
            "(14 CFR 25.1419 exige ensaios/análise certificada); sem falhas detetadas"}
