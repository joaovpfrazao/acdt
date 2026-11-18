"""Avaliadores de verificação do domínio aircraft (acdt.core.verification).

Leem o ``result.json`` (``report.to_dict``) — por isso servem tanto no fim do pipeline como depois, em
``acdt verify``. Nenhum faz física nova, exceto ``sizing:stall_speed``, que inverte a restrição de perda do
diagrama de restrições (Raymer 2018 Eq. 5.6: W/S = ½ ρ V_s² C_Lmax, com a fração de peso de aterragem
de ``assumptions.constraints``).

* ``check:<chave>`` — o veredicto de ``res.checks`` (``hq:…``, ``gear:…``, ``asm:…``, ``aeroel:…``, ``perf:…``,
  ``lr:…``…). ``ok=None`` → desconhecido; chave ausente → não avaliado (a etapa não correu).
* ``perf:<requisito>`` — valor de ``performance.requirements`` (missão por segmentos, Raymer Cap. 17, Anderson),
  convertido para SI. Resolução 0,1 % (a mesma de ``performance_analysis.add``).
* ``sizing:stall_speed`` — V_s em configuração de aterragem a partir de W/S e C_Lmax,aterragem.
* ``ruido:<grandeza>`` — grandeza escalar da secção ``noise`` (noise.py; docs/RUIDO.md), p. ex.
  ``overhead_LAmax_dBA``, ``detection_ground_range_m``, ``SEL_dBA``, ``part36_G.LAmax_dBA``. Com fontes de ruído
  incompletas o valor é um **limite inferior**: num requisito ``max`` um valor acima do limiar falha, um valor abaixo
  fica desconhecido (nunca passa).
* ``termica:<caminho>`` — grandeza da secção ``thermal`` (thermal.py; docs/TERMICA.md), p. ex. ``hot_margin_C``,
  ``cold_margin_C``, ``cooling.drag_area_m2``, ``components.<id>.by_condition.<cond>.hot_margin_C``. As grandezas
  térmicas são **intervalos** {lo, hi}: num requisito ``min`` passa só se ``lo`` ≥ limiar, falha se ``hi`` < limiar;
  num ``max`` passa só se ``hi`` ≤ limiar, falha se ``lo`` > limiar; o resto (ou majorante desconhecido) fica
  desconhecido — nunca passa por omissão.
* ``entrada:<requisito>`` — entradas do dimensionamento (velocidade/altitude de cruzeiro, payload, tripulação)
  lidas do que o dimensionamento usou: cumprido por construção, verificação por inspeção.
"""
from __future__ import annotations

import math
from typing import Any

from acdt.core import units
from acdt.core.atmosphere import isa
from acdt.core.requirements import REGISTRY
from acdt.core.verification import (Evaluator, Evidence, TracedRequirement, VerificationContext,
                                    register_default_evaluator, register_evaluator, register_evidence_lister)

PERF_RESOLUTION = 1e-3
PERF_RESOLUTION_SOURCE = "performance_analysis: comparação a 0,1 %"


def _checks(ctx: VerificationContext) -> list[dict[str, Any]]:
    c = ctx.result.get("checks")
    return c if isinstance(c, list) else []


def _eval_check(req: TracedRequirement, ctx: VerificationContext, key: str) -> Evidence:
    for i, c in enumerate(_checks(ctx)):
        if isinstance(c, dict) and c.get("key") == key:
            ok = c.get("ok")
            return Evidence(None, ok=ok if isinstance(ok, bool) else None, message=str(c.get("message", "")),
                            pointer=f"checks[{i}]")
    return Evidence(ran=False, message=f"verificação '{key}' ausente nos resultados (etapa não correu ou não se "
                                       "aplica a esta configuração)")


def _eval_perf(req: TracedRequirement, ctx: VerificationContext, key: str) -> Evidence:
    perf = ctx.result.get("performance")
    if not isinstance(perf, dict):
        return Evidence(ran=False, message="etapa de desempenho não correu")
    rows = perf.get("requirements") or []
    for i, c in enumerate(rows):
        if isinstance(c, dict) and c.get("requisito") == key:
            v, u = c.get("obtido"), str(c.get("unidade", ""))
            if not isinstance(v, (int, float)) or not math.isfinite(float(v)):
                return Evidence(None, message=f"{key}: sem valor", pointer=f"performance.requirements[{i}]")
            rt = REGISTRY.get(key)
            dim = rt.dimension if rt is not None else ""
            try:
                vsi = units.to_si(float(v), u, dim) if dim else float(v)
                usi = units.default_unit(dim) if dim else u
            except units.UnitError:
                return Evidence(None, message=f"{key}: unidade '{u}' não convertível",
                                pointer=f"performance.requirements[{i}]")
            return Evidence(vsi, usi, message=str(c.get("grandeza", "")), pointer=f"performance.requirements[{i}]",
                            display=f"{float(v):.4g} {u}", resolution=PERF_RESOLUTION,
                            resolution_source=PERF_RESOLUTION_SOURCE)
    return Evidence(ran=False, message=f"desempenho não comparou '{key}' nesta corrida")


def _eval_stall(req: TracedRequirement, ctx: VerificationContext, _: str) -> Evidence:
    dp, aero = ctx.result.get("design_point") or {}, ctx.result.get("aero") or {}
    ws, cl = dp.get("W_S_N_m2"), aero.get("CLmax_landing")
    if not isinstance(ws, (int, float)) or not isinstance(cl, (int, float)):
        return Evidence(ran=False, message="ponto de projeto ou C_Lmax de aterragem ausentes")
    if not (math.isfinite(ws) and math.isfinite(cl) and cl > 0 and ws > 0):
        return Evidence(None, message=f"W/S {ws} ou C_Lmax {cl} inválidos", pointer="design_point.W_S_N_m2")
    spec = ctx.extra.get("spec")
    h, f_land, note = 0.0, None, ""
    tol, tol_src = 0.0, ""
    if spec is not None:
        A = getattr(spec, "assumptions", {}) or {}
        f_land = (A.get("constraints") or {}).get("landing_weight_fraction")
        r = spec.requirements.get("stall_speed")
        if r is not None:
            h = float(r.params.get("altitude", 0.0))
        mda = A.get("mda") or {}
        lowfi = (A.get("aero") or {}).get("fidelity") == "lowfi"
        t = float(mda.get("tol", 1e-5))
        tol = max(t, float(mda.get("tol_lowfi", 2e-4))) if lowfi else t
        tol_src = "fecho do MDA (assumptions.mda.tol" + ("/tol_lowfi" if lowfi else "") + ")"
    if not isinstance(f_land, (int, float)):
        f_land, note = 1.0, "fração de aterragem 1,0 (PRESSUPOSTO conservador: missão não carregada)"
    vs = math.sqrt(2.0 * ws * float(f_land) / (isa(h).rho * cl))
    msg = (f"V_s = √(2 (W/S) f_ater / (ρ C_Lmax,ater)) = {vs:.3f} m/s (Raymer Eq. 5.6; W/S {ws:.1f} N/m², "
           f"f_ater {float(f_land):g}, C_Lmax,ater {cl:.3f}, h {h:g} m)" + (f"; {note}" if note else ""))
    return Evidence(vs, "m/s", message=msg, pointer="design_point.W_S_N_m2", resolution=tol,
                    resolution_source=tol_src)


_INPUT_PATHS = {"cruise_speed": ("aero.cruise_speed_m_s", "m/s"), "cruise_altitude": ("aero.cruise_altitude_m", "m"),
                "payload_mass": ("weights.payload_kg", "kg"), "crew_mass": ("weights.crew_kg", "kg")}


def _eval_input(req: TracedRequirement, ctx: VerificationContext, key: str) -> Evidence:
    from acdt.core.verification import json_path

    if key not in _INPUT_PATHS:
        return Evidence(ran=False, message=f"entrada '{key}' sem caminho conhecido")
    path, u = _INPUT_PATHS[key]
    try:
        v = json_path(ctx.result, path)
    except KeyError:
        return Evidence(ran=False, message=f"'{path}' ausente")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return Evidence(None, message=f"'{path}' sem valor", pointer=path)
    return Evidence(float(v), u, message="entrada do dimensionamento (cumprida por construção)", pointer=path)


def _list_evidence(ctx: VerificationContext) -> list[str]:
    out = [f"check:{c['key']}" for c in _checks(ctx) if isinstance(c, dict) and "key" in c
           and not str(c["key"]).startswith("perf:")]
    perf = ctx.result.get("performance")
    if isinstance(perf, dict):
        out += [f"perf:{c['requisito']}" for c in perf.get("requirements") or [] if isinstance(c, dict)]
    nz = ctx.result.get("noise")
    if isinstance(nz, dict) and nz.get("evaluated"):
        out += ["ruido:overhead_LAmax_dBA", "ruido:detection_ground_range_m"]
    th = ctx.result.get("thermal")
    if isinstance(th, dict) and th.get("evaluated"):
        out += ["termica:hot_margin_C", "termica:cold_margin_C", "termica:cooling.drag_area_m2"]
    return out


register_evaluator(Evaluator("check:", _eval_check, "veredicto de res.checks (hq/gear/asm/aeroel/lr/…)",
                             "analise", "N1", domains=("aircraft",)))
register_evaluator(Evaluator("perf:", _eval_perf, "missão por segmentos / comprimentos de pista / teto",
                             "analise", "N1", "Raymer 2018 Cap. 17; Anderson 1999", ("aircraft",)))
register_evaluator(Evaluator("sizing:stall_speed", _eval_stall, "V_s de aterragem a partir de W/S e C_Lmax",
                             "analise", "N0", "Raymer 2018 Eq. 5.6", ("aircraft",)))
def _eval_noise(req: TracedRequirement, ctx: VerificationContext, key: str) -> Evidence:
    from acdt.core.verification import json_path

    nz = ctx.result.get("noise")
    if not isinstance(nz, dict):
        return Evidence(ran=False, message="etapa de ruído não correu")
    if not nz.get("evaluated"):
        return Evidence(ran=False, message=f"ruído não avaliado: {nz.get('reason', '')}")
    try:
        v = json_path(nz, key)
    except (KeyError, ValueError):
        return Evidence(ran=False, message=f"noise.{key} não existe", pointer=f"noise.{key}")
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(float(v)):
        return Evidence(None, message=f"noise.{key} sem valor", pointer=f"noise.{key}")
    x = float(v)
    if not nz.get("sources_complete") and req.comparison == "max" and req.threshold is not None \
            and x <= float(req.threshold):
        return Evidence(None, message=f"noise.{key} = {x:.4g} é limite inferior (fontes incompletas: "
                        f"{nz.get('sources_note', '')}); não pode passar", pointer=f"noise.{key}", fidelity="N0")
    return Evidence(x, req.unit, pointer=f"noise.{key}", fidelity="N0",
                    message="" if nz.get("sources_complete") else "limite inferior (fontes incompletas)")


register_evaluator(Evaluator("ruido:", _eval_noise, "disciplina ruído L0 (Gutin, Schlegel-King-Mull, ISO 9613-1, "
                             "IEC 61672-1, ISO 226); limite inferior com fontes incompletas", "analise", "N0",
                             "Marte & Kurtz 1970; ISO 9613-1; IEC 61672-1; ISO 226", ("aircraft",)))
def _eval_thermal(req: TracedRequirement, ctx: VerificationContext, key: str) -> Evidence:
    from acdt.core.verification import json_path

    th = ctx.result.get("thermal")
    if not isinstance(th, dict):
        return Evidence(ran=False, message="etapa térmica não correu")
    if not th.get("evaluated"):
        return Evidence(ran=False, message=f"térmica não avaliada: {th.get('reason', '')}")
    try:
        v = json_path(th, key)
    except (KeyError, ValueError, IndexError, TypeError):
        return Evidence(ran=False, message=f"thermal.{key} não existe", pointer=f"thermal.{key}")
    rt = REGISTRY.get(req.quantity)
    u = units.default_unit(rt.dimension) if rt is not None else req.unit

    def num(x: Any) -> float | None:
        return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x)) \
            else None

    if isinstance(v, dict) and ("lo" in v or "hi" in v):
        lo, hi = num(v.get("lo")), num(v.get("hi"))
        thr = num(req.threshold)
        rng = f"[{'?' if lo is None else f'{lo:.4g}'}, {'?' if hi is None else f'{hi:.4g}'}]"
        if thr is not None and req.comparison == "min":
            if lo is not None and lo >= thr:
                return Evidence(lo, u, pointer=f"thermal.{key}.lo", fidelity="N0", message=f"intervalo {rng}: "
                                "o minorante cumpre")
            if hi is not None and hi < thr:
                return Evidence(hi, u, pointer=f"thermal.{key}.hi", fidelity="N0", message=f"intervalo {rng}: "
                                "nem o majorante cumpre")
            return Evidence(None, message=f"thermal.{key} = {rng} atravessa o limiar ou tem extremo desconhecido "
                            "(declare as entradas em falta)", pointer=f"thermal.{key}", fidelity="N0")
        if thr is not None and req.comparison == "max":
            if hi is not None and hi <= thr:
                return Evidence(hi, u, pointer=f"thermal.{key}.hi", fidelity="N0", message=f"intervalo {rng}: "
                                "o majorante cumpre")
            if lo is not None and lo > thr:
                return Evidence(lo, u, pointer=f"thermal.{key}.lo", fidelity="N0", message=f"intervalo {rng}: "
                                "nem o minorante cumpre")
            return Evidence(None, message=f"thermal.{key} = {rng} atravessa o limiar ou tem extremo desconhecido "
                            "(declare as entradas em falta)", pointer=f"thermal.{key}", fidelity="N0")
        return Evidence(None, message=f"thermal.{key} é um intervalo {rng}: só comparações min/max",
                        pointer=f"thermal.{key}")
    x = num(v)
    if x is None:
        return Evidence(None, message=f"thermal.{key} sem valor", pointer=f"thermal.{key}")
    return Evidence(x, u, pointer=f"thermal.{key}", fidelity="N0")


register_evaluator(Evaluator("termica:", _eval_thermal, "disciplina térmica L0/L1 (Incropera et al. 6.ª ed., "
                             "MIL-HDBK-310, NACA RM A8I29); intervalos — desconhecido se atravessa o limiar",
                             "analise", "N0", "Incropera et al. 2007; MIL-HDBK-310; NACA RM A8I29", ("aircraft",)))
register_evaluator(Evaluator("entrada:", _eval_input, "entrada do dimensionamento (por construção)",
                             "inspecao", "N0", domains=("aircraft",)))
register_evidence_lister("aircraft", _list_evidence)

for _k in ("range", "endurance", "service_ceiling", "climb_rate", "takeoff_ground_roll", "landing_distance"):
    register_default_evaluator("aircraft", _k, f"perf:{_k}", "analise", "N1")
register_default_evaluator("aircraft", "stall_speed", "sizing:stall_speed", "analise", "N0")
register_default_evaluator("aircraft", "mtow", "resultado:weights.W0_kg", "analise", "N0")
register_default_evaluator("aircraft", "wing_span", "resultado:geometry.wing.span_m", "analise", "N0")
for _k in _INPUT_PATHS:
    register_default_evaluator("aircraft", _k, f"entrada:{_k}", "inspecao", "N0")
register_default_evaluator("aircraft", "noise", "ruido:overhead_LAmax_dBA", "analise", "N0")
register_default_evaluator("aircraft", "aural_detection_range", "ruido:detection_ground_range_m", "analise", "N0")
register_default_evaluator("aircraft", "thermal_margin", "termica:hot_margin_C", "analise", "N0")
register_default_evaluator("aircraft", "cold_thermal_margin", "termica:cold_margin_C", "analise", "N0")
register_default_evaluator("aircraft", "cooling_drag_area", "termica:cooling.drag_area_m2", "analise", "N0")
for _k in ("regulatory_category", "unit_cost", "power_available", "thrust_available"):
    register_default_evaluator("aircraft", _k, f"check:{_k}", "analise", "N0")
