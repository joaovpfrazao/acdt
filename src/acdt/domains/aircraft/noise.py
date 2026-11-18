# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Disciplina «ruído» (L0) do domínio aircraft: hélices/rotores → observador no solo (docs/RUIDO.md).

Etapa do pipeline depois do desempenho. Usa o mapa BEMT da hélice de passo fixo (``assumptions.propulsion.propeller``,
:mod:`.propeller`) para os pontos de funcionamento:

* **sobrevoo** à altitude de espera (ou de cruzeiro; ``noise.flyover_altitude_m``) e à velocidade dessa perna,
  empuxo = arrasto a W0 (PRESSUPOSTO: massa de descolagem, o caso de maior empuxo);
* **descolagem/subida** a V_y ao nível do mar com potência de descolagem (só para a verificação da Parte 36 Ap. G).

Fontes (:mod:`acdt.core.acoustics.rotor`): tons de carga de Gutin e banda larga de Schlegel-King-Mull. Propagação,
ponderação A, sobrevoo e deteção auditiva: :mod:`acdt.core.acoustics.propagation`.

**Completude das fontes.** Ruído de espessura, de motor (escape do motor térmico, motor elétrico), de célula e de
interação não estão modelados. O nível calculado é por isso um **limite inferior** do nível real, e o alcance de
deteção também: um requisito «máximo» que este limite inferior já excede **falha**; um que cumpre não passa
(fica desconhecido) enquanto o utilizador não declarar ``noise.other_sources: {status: desprezaveis | incluidas,
justification: …}``. ``noise.engine_noise`` junta um espectro medido do motor (bandas de oitava a uma distância,
com fonte), omnidirecional. Jatos: sem método citado implementado nesta etapa (não avaliado).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from acdt.core.acoustics import certification as cert
from acdt.core.acoustics.levels import spherical_spreading_db
from acdt.core.acoustics.propagation import Atmosphere, Component, detection_range, flyover, received
from acdt.core.acoustics.rotor import GUTIN_REF, SKM_REF, projected_thickness, rotor_components
from acdt.core.atmosphere import isa

LEVEL = "L0"
METHODS = [GUTIN_REF, SKM_REF, "ISO 9613-1:1993 (absorção atmosférica)", "IEC 61672-1:2013 Anexo E (ponderação A)",
           "ISO 226:2003 Tabela 1 (limiar de audição T_f)", "Marte & Kurtz (1970) Ap. C passo 11 (Doppler)"]
DEFAULTS: dict[str, Any] = {
    "enabled": True, "T_C": 15.0, "rh_pct": 70.0, "p_kpa": 101.325, "harmonics": 10,
    "effective_radius_fraction": 0.8, "broadband": True, "blade_thickness_ratio": None,
    "flyover_altitude_m": None, "flyover_speed_m_s": None, "sideline_m": 0.0, "ground_dB": 0.0,
    "ambient_third_octave_dB": None, "detection_margin_dB": 0.0, "other_sources": None, "engine_noise": None,
    "certification": None,
}


def _opts(spec: Any) -> dict[str, Any]:
    o = dict(DEFAULTS)
    o.update((spec.assumptions.get("noise") or {}) if isinstance(spec.assumptions, dict) else {})
    return o


def _not_evaluated(reason: str) -> dict[str, Any]:
    return {"evaluated": False, "level": LEVEL, "reason": reason, "overhead_LAmax_dBA": None,
            "detection_ground_range_m": None, "detection_slant_range_m": None}


def _blade_geometry(prop: Any, o: dict[str, Any], airfoil: str) -> dict[str, Any]:
    from .propeller import X_HUB, chord_shape

    R = prop.D / 2.0
    c075 = prop.c075_D * prop.D
    x = np.linspace(X_HUB, 1.0, 201)
    cs = np.asarray(chord_shape(x), float)
    area_one = float(np.sum(0.5 * (cs[1:] + cs[:-1]) * np.diff(x))) * c075 * R
    tc, tc_src = o.get("blade_thickness_ratio"), "utilizador (noise.blade_thickness_ratio)"
    if tc is None:
        try:  # t/c máximo das coordenadas do mesmo perfil da hélice (base UIUC via AeroSandbox)
            import aerosandbox as asb
            tc = float(asb.Airfoil(airfoil).max_thickness())
            tc_src = f"coordenadas do perfil '{airfoil}' (UIUC Airfoil Coordinates Database, via AeroSandbox)"
        except Exception:  # noqa: BLE001 — sem coordenadas: t/c desconhecido (banda larga sem espectro)
            tc, tc_src = None, f"perfil '{airfoil}' sem coordenadas: dê noise.blade_thickness_ratio"
    return {"R_m": R, "c075_m": c075, "c07_m": float(chord_shape(0.7)) * c075, "blade_area_m2": prop.blades * area_one,
            "blade_area_note": "área em planta das pás fora do corte de raiz 0,15 R (PRESSUPOSTO: A_b de Schlegel "
                               "et al. = área em planta)", "thickness_ratio": tc, "thickness_ratio_source": tc_src}


def _alpha07(prop: Any, cfg: dict[str, Any], J: float) -> float | None:
    """Ângulo de ataque da secção a 0,7 R na solução BEMT (o mesmo perfil e Reynolds de make_propeller)."""
    try:
        from .propeller import SectionPolar, _alpha_at
        mu, rho0 = 1.789e-5, isa(0.0).rho
        nr = prop.rpm_rated / 60.0
        Re = rho0 * 0.75 * math.pi * nr * prop.D * prop.c075_D * prop.D / mu
        sec = SectionPolar.from_airfoil(cfg.get("airfoil", "clarky"), max(Re, 2e4),
                                        prefer=cfg.get("solver", "neuralfoil"))
        sec.blade_ar = (1 - 0.15) / (2 * prop.c075_D)
        return float(_alpha_at(J, prop.D, prop.pitch, prop.blades, prop.c075_D, sec, 0.7))
    except Exception:  # noqa: BLE001 — sem ângulo: a banda larga fica sem espectro (desconhecida, nunca zero)
        return None


def _engine_components(eng: dict[str, Any]) -> list[Component]:
    d = float(eng.get("distance_m", 0) or 0)
    bands = eng.get("octave_dB") or {}
    if d <= 0 or not bands:
        raise ValueError("noise.engine_noise precisa de octave_dB {f: dB} e distance_m (medição com fonte)")
    out: list[Component] = []
    for f, L in bands.items():
        def lev(r: float, th: float, L: float = float(L)) -> float:
            return L + spherical_spreading_db(r, d)
        out.append(Component(f"motor: oitava {float(f):g} Hz", float(f), lev, "motor", "oitava"))
    return out


def _condition(prop: Any, pcfg: dict[str, Any], geo: dict[str, Any], o: dict[str, Any], V: float, h: float,
               op: dict[str, float], label: str) -> tuple[list[Component], dict[str, Any]]:
    a = isa(max(h, 0.0))
    n = max(int(prop.n_props), 1)
    T1, P1, rpm = op["T"] / n, op["P"] / n, op["rpm"]
    h_proj = None
    alpha = None
    if geo["thickness_ratio"] is not None and rpm > 0:
        alpha = _alpha07(prop, pcfg, V / (rpm / 60.0 * prop.D))
        if alpha is not None:
            h_proj = projected_thickness(geo["thickness_ratio"] * geo["c07_m"], geo["c07_m"], alpha)
    comps, info = rotor_components(B=prop.blades, R=geo["R_m"], rpm=rpm, T=T1, P=P1, c=a.a, rho=a.rho, n_rotors=n,
                                   harmonics=int(o["harmonics"]), re_frac=float(o["effective_radius_fraction"]),
                                   blade_area_m2=geo["blade_area_m2"], h_proj_m=h_proj,
                                   broadband=bool(o["broadband"]), label=label)
    vt = rpm / 60.0 * math.pi * prop.D
    info.update({"V_m_s": V, "altitude_m": h, "alpha07_deg": None if alpha is None else math.degrees(alpha),
                 "h_proj_m": h_proj, "tip_mach_helical": math.hypot(vt, V) / a.a})
    return comps, info


def _validity(info: dict[str, Any]) -> list[str]:
    out = []
    mh = float(info.get("tip_mach_helical") or 0.0)
    if mh > 0.8:
        out.append(f"M_tip helicoidal {mh:.2f} > 0,8: ruído de espessura e compressibilidade (não modelados) "
                   "dominam; Gutin fora da gama de validade")
    mt = float(info.get("tip_mach_rot") or 0.0)
    if mt < 0.5:
        out.append(f"M_tip de rotação {mt:.2f} < 0,5: Gutin subestima (Marte & Kurtz 1970 §III.C); a banda larga "
                   "de vórtices tende a dominar")
    return out


def analyse_noise(res: Any) -> dict[str, Any]:
    from .performance import PerfModel, climb_rate, takeoff_distance_integrated
    from .propulsion import is_propeller
    from acdt import G0

    spec = res.spec
    o = _opts(spec)
    if not is_propeller(spec.propulsion_kind):
        return _not_evaluated(f"propulsão '{spec.propulsion_kind}': sem método citado implementado para jatos "
                              "nesta etapa (só hélices/rotores)")
    pcfg = spec.assumptions["propulsion"].get("propeller") or {}
    pm = PerfModel.from_result(res)
    prop = pm.prop
    if prop is None:
        return _not_evaluated("sem mapa de hélice: configure assumptions.propulsion.propeller (passo fixo, BEMT) — "
                              "o ruído precisa de diâmetro, pás, rpm, empuxo e binário")
    W = res.sizing.W0 * G0
    legs = list(getattr(res, "legs", []) or [])
    loiter = [L for L in legs if L.kind != "cruise"]
    leg = loiter[0] if loiter else None
    H = o["flyover_altitude_m"]
    if H is None:
        H = float(leg.altitude) if leg is not None and getattr(leg, "altitude", None) else res.cruise_altitude
    V = o["flyover_speed_m_s"] or (leg.V if leg is not None else res.cruise_speed)
    H, V = float(H), float(V)
    th, op = prop.thrust_for(V, H, pm.drag(W, V, isa(H).rho))
    geo = _blade_geometry(prop, o, str(pcfg.get("airfoil", "clarky")))
    comps, info = _condition(prop, pcfg, geo, o, V, H, op, "hélice")
    assumptions = [
        "PRESSUPOSTO: campo livre, atmosfera homogénea com as condições do solo (noise.T_C/rh_pct/p_kpa; por omissão "
        "a atmosfera de referência da Parte 36 Ap. G, 15 °C e 70 %)",
        "PRESSUPOSTO: eixo da hélice alinhado com a trajetória; Gutin estático (sem efeito convectivo do voo)",
        "PRESSUPOSTO: rotores iguais somados como fontes incoerentes (+10 log10 n)",
        "PRESSUPOSTO: banda larga omnidirecional (a fórmula de Schlegel et al. dá só o nível global a 300 ft)",
        f"PRESSUPOSTO: empuxo de sobrevoo = arrasto a W0 ({res.sizing.W0:.1f} kg)",
        "Fontes não modeladas: espessura, motor, célula, interação — nível = limite inferior",
    ]
    eng = o.get("engine_noise")
    if eng:
        comps = comps + _engine_components(eng)
    other = o.get("other_sources") or {}
    complete = isinstance(other, dict) and other.get("status") in ("desprezaveis", "incluidas") \
        and bool(other.get("justification"))
    if not info["broadband_in_sum"] and o["broadband"]:
        complete = False
    atm = Atmosphere(float(o["T_C"]), float(o["rh_pct"]), float(o["p_kpa"]), isa(H).a)
    gdb = float(o["ground_dB"])
    fly = flyover(comps, H, V, atm, float(o["sideline_m"]), gdb)
    over = received(comps, H, math.pi / 2, atm, 0.0, gdb, detail=True)
    mach = V / atm.c_m_s
    quiet = detection_range(comps, atm, mach, None, 0.0, gdb)
    amb = o.get("ambient_third_octave_dB")
    ambd = {float(k): float(v) for k, v in amb.items()} if isinstance(amb, dict) and amb else None
    det = detection_range(comps, atm, mach, ambd, float(o["detection_margin_dB"]), gdb) if ambd else quiet

    def ground(rs: Any) -> float | None:
        if rs is None:
            return 0.0  # inaudível mesmo a 1 m: alcance nulo (resultado calculado, não desconhecido)
        return math.sqrt(rs * rs - H * H) if rs > H else 0.0

    det_slant = det["range_m"]
    out: dict[str, Any] = {
        "evaluated": True, "level": LEVEL, "methods": METHODS, "assumptions": assumptions,
        "sources_complete": complete,
        "sources_note": ("fontes declaradas completas pelo utilizador: " + str(other.get("justification"))) if complete
        else "nível e alcance são limites inferiores (fontes não modeladas; declare noise.other_sources)",
        "atmosphere": {"T_C": atm.T_C, "rh_pct": atm.rh_pct, "p_kpa": atm.p_kpa, "c_source_m_s": atm.c_m_s},
        "propeller": {k: v for k, v in geo.items()} | {"D_m": prop.D, "blades": prop.blades, "n_props": prop.n_props},
        "flyover": {"altitude_m": H, "speed_m_s": V, "throttle": th, "operating_point": info, **fly,
                    "overhead_LA_dBA": over.LA, "overhead_Lp_dB": over.Lp, "overhead_spectrum": over.components,
                    "absorption_out_of_validity": sorted(set(over.out_of_validity))},
        "overhead_LAmax_dBA": fly["LAmax_dBA"],
        "SEL_dBA": fly["SEL_dBA"],
        "detection": {"quiet": quiet, "ambient": det if ambd else None,
                      "ambient_note": None if ambd else "sem ruído ambiente: limite em silêncio (ISO 226)",
                      "margin_dB": float(o["detection_margin_dB"])},
        "detection_slant_range_m": det_slant,
        "detection_ground_range_m": ground(det_slant),
        "detection_ground_range_quiet_m": ground(quiet["range_m"]),
        "validity": _validity(info),
    }
    c = o.get("certification") or {}
    p36 = c.get("part36_G") if isinstance(c, dict) else None
    if p36 is not None:
        out["part36_G"] = _part36(res, pm, prop, pcfg, geo, o, W, complete, p36 if isinstance(p36, dict) else {},
                                  climb_rate, takeoff_distance_integrated)
    return out


def _part36(res: Any, pm: Any, prop: Any, pcfg: dict[str, Any], geo: dict[str, Any], o: dict[str, Any], W: float,
            complete: bool, p36: dict[str, Any], climb_rate: Any, takeoff: Any) -> dict[str, Any]:
    n_eng = int(res.spec.assumptions["propulsion"].get("n_engines", 1) or 1)
    after = p36.get("single_engine_application_after_2006")
    if after is None:
        after = n_eng == 1  # PRESSUPOSTO: projeto novo (pedido de certificado de tipo depois de 3 fev 2006)
    after = bool(after) and n_eng == 1
    mtow = float(res.sizing.W0)
    lim = cert.part36_g_limit(mtow, after)
    roc, vy = climb_rate(pm, W, 0.0)
    d50 = float(takeoff(pm, W)["total_50ft"])
    H = cert.part36_g_reference_height(d50, roc, vy)
    r: dict[str, Any] = {"reference": cert.REF, "limit_dBA": lim,
                         "rule": "G36.301(c)" if after else "G36.301(b)", "mtow_kg": mtow,
                         "takeoff_50ft_m": d50, "roc_m_s": roc, "V_y_m_s": vy, "reference_height_m": H,
                         "ground_plate_dB": 20 * math.log10(2.0),
                         "notes": ["autoavaliação de projeto conceptual (a autoridade decide)",
                                   "microfone sobre placa (G36.107(a)): +6,02 dB de duplicação de pressão",
                                   "atmosfera de referência G36.111(b): 15 °C, 70 %, 1013,25 hPa"]}
    if lim is None or H is None:
        r.update({"LAmax_dBA": None, "ok": None,
                  "message": "fora do âmbito (MTOW > 8618 kg) ou altura de referência indefinida "
                             "(descolagem a 15 m além de 2500 m / sem subida)"})
        return r
    op = prop.operating_point(vy, 0.0, 1.0)
    comps, info = _condition(prop, pcfg, geo, o, vy, 0.0, op, "hélice (descolagem)")
    if o.get("engine_noise"):
        comps = comps + _engine_components(o["engine_noise"])
    atm = Atmosphere(15.0, 70.0, 101.325, isa(0.0).a)
    fly = flyover(comps, H, vy, atm, 0.0, 20 * math.log10(2.0))
    L = fly["LAmax_dBA"]
    ok: bool | None
    if L > lim:
        ok = False
    else:
        ok = True if complete else None
    r.update({"LAmax_dBA": L, "operating_point": info, "margin_dB": lim - L, "ok": ok,
              "message": f"L_A,max {L:.1f} dB(A) a {H:.0f} m vs limite {lim:.1f} dB(A) ({r['rule']})"
                         + ("" if complete or ok is False else "; limite inferior (fontes incompletas): não passa")})
    return r


def noise_stage(res: Any) -> None:
    from acdt.core.requirements import Issue
    from .sizing import CheckResult

    o = _opts(res.spec)
    if not o.get("enabled", True):
        res.noise = _not_evaluated("noise.enabled: false")
        return
    try:
        res.noise = analyse_noise(res)
    except Exception as ex:  # noqa: BLE001 — a etapa de ruído nunca parte o pipeline; fica desconhecido
        res.noise = _not_evaluated(f"falhou: {type(ex).__name__}: {ex}")
        res.issues.append(Issue("warning", f"ruído não avaliado: {type(ex).__name__}: {ex}"))
        return
    p = (res.noise or {}).get("part36_G")
    if p is not None:
        res.checks.append(CheckResult("noise:part36_G", p.get("ok"), str(p.get("message", ""))))
