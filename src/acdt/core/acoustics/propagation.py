# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Do espectro da fonte ao observador: nível, sobrevoo e alcance de deteção auditiva.

Cadeia por componente (tom ou banda de oitava), campo livre, atmosfera homogénea:

1. nível da fonte à distância r e ângulo θ (a fonte já inclui a divergência esférica: Gutin ∝ 1/r; a banda larga
   escala por −20 log10(r/r_ref));
2. absorção atmosférica −α(f)·r com α da ISO 9613-1 (:mod:`.absorption`), à frequência recebida;
3. frequência recebida com o efeito Doppler da fonte em movimento, f_obs = f/(1 − M cos θ) (Marte & Kurtz, JPL TR
   32-1462, 1970, Apêndice C, passo 11: «fundamental frequency nB/[2π(1 − M_F cos θ)]»);
4. reflexão no solo: ΔL declarado pelo utilizador (0 dB = campo livre; +6,02 dB = duplicação de pressão num
   microfone sobre placa rígida, como em 14 CFR 36 Ap. G, G36.107(a) — Kinsler et al., *Fundamentals of
   Acoustics*, 4.ª ed., 2000, reflexão numa fronteira rígida);
5. ponderação A à frequência recebida (:mod:`.weighting`); bandas de oitava ponderadas no centro da banda
   (PRESSUPOSTO, prática de soma por bandas);
6. soma energética de todos os componentes (fontes incoerentes; :mod:`.levels`).

Sobrevoo: trajetória retilínea nivelada à altura H, observador no solo com afastamento lateral y; L_A,max é o
máximo de L_A(t) e L_AE (nível de exposição sonora) = 10 log10 ∫ 10^(L_A(t)/10) dt / 1 s (ISO 1996-1:2016,
definição de nível de exposição sonora). O eixo da hélice é o da trajetória (PRESSUPOSTO: atitude e ângulo de
subida desprezados).

Deteção auditiva: um componente é audível quando o seu nível recebido iguala ou excede o limiar
max(T_f(f), L_ambiente(f) + margem), com T_f da ISO 226:2003 (:mod:`.hearing`; definição de limiar = 50 % de
deteção) e o ruído ambiente em bandas de 1/3 de oitava dado pelo utilizador. As bandas de oitava da banda larga
repartem-se igualmente pelas três bandas de 1/3 de oitava (−10 log10 3 dB cada; PRESSUPOSTO de espectro plano na
oitava). O alcance de deteção usa a pior direção da fonte (máximo em θ) a cada distância — limite superior
(conservador para quem quer não ser ouvido). Sem ruído ambiente o resultado é o limite em silêncio. Com ruído
ambiente a regra «nível ≥ banda ambiente + margem» não é o modelo de deteção de sinais de Fidell et al. (1974) e
pode subestimar o alcance (um tom pode ser detetável abaixo do nível da banda de 1/3 de oitava): por isso o
alcance em silêncio é sempre reportado também.

Opcional, e só com ``ground`` declarado (:class:`~acdt.core.acoustics.ground.GroundPath`): subtrai-se A_gr da
ISO 9613-2:1996 §7.3.1 (Tabela 3) e, se C_0 vier declarado, C_met do §8. Esse termo substitui ``ground_dB``;
os dois não se somam. Sem o mapa, a cadeia é a de cima (``ground_dB`` declarado pelo utilizador). A_gr em falta
não é 0 dB: o nível corrigido fica por avaliar. O alcance com A_gr continua a ser um limite superior pela pior
direção. Omitir A_gr não dá, por si, esse sinal, porque nas bandas graves a tabela amplifica.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .absorption import alpha_iso9613, in_validity
from .ground import (GroundPath, annotate_ground, c_met_dB, ground_attenuation_dB, ground_distance_m,
                    octave_band_hz)
from .hearing import threshold_iso226
from .levels import level_sum
from .weighting import a_weighting

LevelFn = Callable[[float, float], float]  # (r [m], θ [rad]) → L_p campo livre sem absorção [dB]
THIRD = 2.0 ** (1.0 / 3.0)


@dataclass
class Component:
    """Um tom (``band='tom'``) ou uma banda de oitava (``band='oitava'``) de uma fonte."""

    name: str
    f_Hz: float
    level: LevelFn
    kind: str = "tonal"        # tonal | banda_larga | motor | outro
    band: str = "tom"          # tom | oitava


@dataclass
class Atmosphere:
    T_C: float = 15.0
    rh_pct: float = 70.0
    p_kpa: float = 101.325
    c_m_s: float = 340.294     # velocidade do som na fonte (ISA 0 m por omissão; o chamador passa a da altitude)


@dataclass
class Received:
    LA: float
    Lp: float
    components: list[dict[str, float | str]] = field(default_factory=list)
    out_of_validity: list[str] = field(default_factory=list)
    ground: dict[str, Any] | None = None


def doppler(f: float, mach: float, theta: float) -> float:
    return f / max(1.0 - mach * math.cos(theta), 1e-6)


def _propagated(c: Component, r: float, theta: float, atm: Atmosphere, mach: float, ground_dB: float,
                ground: GroundPath | None) -> tuple[float | None, float, dict[str, Any]]:
    """Nível recebido sem ponderar. None se o solo foi pedido e A_gr (ou C_met declarado) é desconhecido."""
    f = doppler(c.f_Hz, mach, theta)
    info: dict[str, Any] = {"name": c.name, "f_source_Hz": c.f_Hz, "f_received_Hz": f, "L0_finite": False}
    L0 = c.level(r, theta)
    if not math.isfinite(L0):
        return None, f, info
    info["L0_finite"] = True
    L = L0 - alpha_iso9613(f, atm.T_C, atm.rh_pct, atm.p_kpa) * r
    if ground is None:
        return L + ground_dB, f, info
    if ground_dB != 0.0:
        info["ground_dB_ignored"] = ground_dB
    dp = ground_distance_m(r, ground.hs_m, ground.hr_m)
    band = octave_band_hz(f)
    agr = None if dp is None else ground_attenuation_dB(f, dp, ground.hs_m, ground.hr_m, ground.Gs, ground.Gr,
                                                       ground.Gm)
    info.update({"dp_m": dp, "band_Hz": band, "A_gr_dB": agr, "short_range": dp == 0.0})
    if agr is None:
        info["ground"] = "nao_avaliado"
        return None, f, info
    L = L - agr
    if ground.C0_dB is None:
        info["C_met"] = "nao_aplicado"
        info["C_met_dB"] = None
    else:
        cm = None if dp is None else c_met_dB(dp, ground.hs_m, ground.hr_m, ground.C0_dB)
        info["C_met_dB"] = cm
        if cm is None:
            info["ground"] = "nao_avaliado"
            return None, f, info
        info["C_met"] = "aplicado"
        L = L - cm
    info["ground"] = "aplicado"
    return L, f, info


def _summarize_ground(infos: Sequence[dict[str, Any]], ground: GroundPath, ground_dB: float) -> dict[str, Any]:
    finite = [i for i in infos if i.get("L0_finite")]
    unknown = [i for i in finite if i.get("ground") != "aplicado"]
    applied = [i for i in finite if i.get("ground") == "aplicado"]
    status = "aplicado" if finite and not unknown else "nao_avaliado"
    notes: list[str] = []
    if any(i.get("short_range") for i in applied):
        notes.append("d_p = 0 m em algum componente: limite do §7.3; os termos (1−exp) anulam-se. O valor não foi "
                     "substituído por zero.")
    if ground_dB != 0.0:
        notes.append("ground_dB declarado foi ignorado para não somar a placa rígida a A_gr.")
    if ground.C0_dB is None:
        notes.append("C_0 ausente: C_met não aplicado (propagação favorável, Eq. 6).")
    elif ground.C0_dB > 5.0:
        notes.append("C_0 acima de +5 dB (nota 22): usa-se o valor declarado.")
    reason = ""
    if status != "aplicado":
        reason = ("A_gr ou C_met desconhecido em pelo menos um componente com nível finito. Esses componentes não "
                  "entram na soma e o total corrigido não se publica (desconhecido não é 0 dB).")
    out = {
        "status": status, "veredicto": "nao_avaliado", "calibracao": "nao_aplicar",
        "metodo": "ISO 9613-2:1996 §7.3.1 Tabela 3 Eq. (9)"
                  + ("; §8 Eq. (21)–(22)" if ground.C0_dB is not None else ""),
        "hs_m": ground.hs_m, "hr_m": ground.hr_m, "Gs": ground.Gs, "Gr": ground.Gr, "Gm": ground.Gm,
        "C0_dB": ground.C0_dB,
        "C_met": "nao_aplicado" if ground.C0_dB is None else "aplicado",
        "ground_dB_ignored": ground_dB != 0.0,
        "components": [{k: i.get(k) for k in ("name", "f_received_Hz", "band_Hz", "dp_m", "A_gr_dB", "C_met_dB",
                                              "ground")} for i in finite],
        "omitted": [i.get("name") for i in unknown],
        "notas": notes, "reason": reason,
        "pressuposto": "PRESSUPOSTO: a Tabela 3, de bandas de oitava, aplica-se à frequência recebida (depois do "
                       "Doppler). d_p é a projeção no solo da distância r já usada pela fonte.",
    }
    return annotate_ground(out, applied=status == "aplicado", c0_declared=ground.C0_dB is not None,
                           components_omitted=bool(unknown))


def received(comps: Sequence[Component], r: float, theta: float, atm: Atmosphere, mach: float = 0.0,
             ground_dB: float = 0.0, detail: bool = False, *, ground: GroundPath | None = None) -> Received:
    lps: list[float] = []
    las: list[float] = []
    rows: list[dict[str, float | str]] = []
    oov: list[str] = []
    infos: list[dict[str, Any]] = []
    for c in comps:
        L, f, info = _propagated(c, r, theta, atm, mach, ground_dB, ground)
        infos.append(info)
        if L is None or not math.isfinite(L):
            continue
        if not in_validity(f, atm.T_C, atm.rh_pct, atm.p_kpa):
            oov.append(c.name)
        la = L + a_weighting(f)
        lps.append(L)
        las.append(la)
        if detail:
            rows.append({"name": c.name, "kind": c.kind, "band": c.band, "f_source_Hz": c.f_Hz, "f_received_Hz": f,
                         "Lp_dB": L, "LA_dBA": la})
    summary = None if ground is None else _summarize_ground(infos, ground, ground_dB)
    if summary is not None and summary["status"] != "aplicado":
        summary["LA_parcial_dBA"] = level_sum(las) if las else None
        summary["Lp_parcial_dB"] = level_sum(lps) if lps else None
        return Received(math.nan, math.nan, [], oov, summary)
    return Received(level_sum(las), level_sum(lps), rows, oov, summary)


def flyover(comps: Sequence[Component], H: float, V: float, atm: Atmosphere, y: float = 0.0,
            ground_dB: float = 0.0, n: int = 241, span: float = 15.0, *,
            ground: GroundPath | None = None) -> dict[str, Any]:
    """L_A,max e L_AE de uma passagem retilínea à altura H [m] e velocidade V [m/s]."""
    mach = V / atm.c_m_s
    d0 = math.hypot(H, y)
    xs = [d0 * span * (2.0 * i / (n - 1) - 1.0) for i in range(n)]
    las: list[float] = []
    complete = True
    for s in xs:
        r = math.sqrt(s * s + d0 * d0)
        th = math.acos(max(-1.0, min(1.0, -s / r)))
        rec = received(comps, r, th, atm, mach, ground_dB, ground=ground)
        if ground is not None and (rec.ground is None or rec.ground.get("status") != "aplicado"):
            complete = False
        las.append(rec.LA if math.isfinite(rec.LA) else -math.inf)
    i = max(range(n), key=lambda k: las[k] if math.isfinite(las[k]) else -math.inf)
    dt = (xs[1] - xs[0]) / V if V > 0 else 0.0
    finite = [v for v in las if math.isfinite(v) and v > -math.inf]
    sel = 10.0 * math.log10(sum(10.0 ** (v / 10.0) for v in finite) * dt) if dt > 0 and finite else math.nan
    r_max = math.sqrt(xs[i] ** 2 + d0 ** 2)
    out: dict[str, Any] = {
        "LAmax_dBA": las[i], "SEL_dBA": sel, "theta_at_max_deg": math.degrees(math.acos(-xs[i] / r_max)),
        "r_at_max_m": r_max,
    }
    if ground is not None:
        out["ground_complete"] = complete
    return out


def _thirds(c: Component, f: float, L: float) -> list[tuple[float, float]]:
    if c.band == "oitava":
        d = 10.0 * math.log10(3.0)
        return [(f / THIRD, L - d), (f, L - d), (f * THIRD, L - d)]
    return [(f, L)]


def _ambient(amb: Mapping[float, float] | None, f: float) -> float | None:
    """Banda ambiente de 1/3 de oitava que contém f (a de centro mais próximo em log f, até meia banda)."""
    if not amb:
        return None
    fc = min(amb, key=lambda k: abs(math.log10(k) - math.log10(f)))
    return float(amb[fc]) if abs(math.log10(fc) - math.log10(f)) <= math.log10(THIRD) / 2.0 + 1e-9 else None


def audibility_margin(comps: Sequence[Component], r: float, theta: float, atm: Atmosphere, mach: float = 0.0,
                      ambient: Mapping[float, float] | None = None, margin_dB: float = 0.0,
                      ground_dB: float = 0.0, *, ground: GroundPath | None = None,
                      omitted: list[str] | None = None) -> tuple[float, str]:
    """max_componentes (L_recebido − limiar) [dB] e o componente que manda; −inf se nenhum tem limiar definido.

    Com solo ISO, um componente cujo A_gr é desconhecido não conta (não é audível nem silêncio). O nome entra
    em ``omitted`` quando esse argumento é uma lista.
    """
    best, who = -math.inf, ""
    for c in comps:
        L, f, info = _propagated(c, r, theta, atm, mach, ground_dB, ground)
        if L is None or not math.isfinite(L):
            if ground is not None and info.get("L0_finite") and info.get("ground") == "nao_avaliado" and omitted is not None:
                omitted.append(c.name)
            continue
        for ff, LL in _thirds(c, f, L):
            tf = threshold_iso226(ff)
            if tf is None:
                continue
            amb = _ambient(ambient, ff)
            thr = tf if amb is None else max(tf, amb + margin_dB)
            if LL - thr > best:
                best, who = LL - thr, c.name
    return best, who


def detection_range(comps: Sequence[Component], atm: Atmosphere, mach: float = 0.0,
                    ambient: Mapping[float, float] | None = None, margin_dB: float = 0.0, ground_dB: float = 0.0,
                    r_min: float = 1.0, r_max: float = 100_000.0, n_theta: int = 37, *,
                    ground: GroundPath | None = None) -> dict[str, Any]:
    """Distância oblíqua máxima a que a fonte é audível (pior direção). None se nem a r_min é audível."""
    note_rmin = None
    if ground is not None:
        gap = abs(ground.hs_m - ground.hr_m)
        if r_min < gap:
            r_min = gap
            note_rmin = "r_min elevado a |h_s − h_r|: abaixo disso a geometria do d_p é inconsistente."
    thetas = [math.pi * i / (n_theta - 1) for i in range(n_theta)]

    def m(r: float) -> tuple[float, str, float, list[str]]:
        best = (-math.inf, "", 0.0)
        omitted: list[str] = []
        for th in thetas:
            v, who = audibility_margin(comps, r, th, atm, mach, ambient, margin_dB, ground_dB, ground=ground,
                                       omitted=omitted)
            if v > best[0]:
                best = (v, who, th)
        return best[0], best[1], best[2], omitted

    def pack(range_m: float | None, who: str | None, theta: float | None, omitted: list[str]) -> dict[str, Any]:
        out: dict[str, Any] = {"range_m": range_m, "governing": who, "theta_deg": theta}
        if ground is not None:
            names = sorted(set(omitted))
            out["ground_status"] = "aplicado" if not names else "nao_avaliado"
            out["ground_omitted"] = names
            out["range_bound"] = "superior"
            if note_rmin:
                out["r_min_note"] = note_rmin
        return out

    lo_m = m(r_min)
    if lo_m[0] < 0.0:
        return pack(None, None, None, lo_m[3])
    if m(r_max)[0] >= 0.0:
        far = m(r_max)
        return pack(r_max, far[1], None, far[3])
    lo, hi = r_min, r_max
    for _ in range(60):
        mid = math.sqrt(lo * hi)
        if m(mid)[0] >= 0.0:
            lo = mid
        else:
            hi = mid
        if hi / lo < 1.0005:
            break
    g = m(lo)
    return pack(lo, g[1], math.degrees(g[2]), g[3])
