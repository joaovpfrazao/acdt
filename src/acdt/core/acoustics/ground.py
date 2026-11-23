# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Atenuação do solo e correção meteorológica — ISO 9613-2:1996.

Método geral do §7.3.1, só para solo plano ou de inclinação constante. Oito bandas
nominais (63 Hz a 8 kHz). Eq. (9):

    A_gr = A_s + A_r + A_m

q = 0 quando d_p ≤ 30(h_s + h_r); senão q = 1 − 30(h_s + h_r)/d_p.

A_s usa (G_s, h_s) e A_r usa (G_r, h_r), Tabela 3:

    63 Hz: −1,5
    125: −1,5 + G·a'(h)
    250: −1,5 + G·b'(h)
    500: −1,5 + G·c'(h)
    1000: −1,5 + G·d'(h)
    2000, 4000 e 8000: −1,5·(1 − G)

A_m: −3q em 63 Hz; −3q·(1 − G_m) de 125 Hz a 8 kHz.

    a'(h) = 1,5 + 3,0·exp(−0,12·(h−5)²)·(1−exp(−d_p/50)) + 5,7·exp(−0,09·h²)·(1−exp(−2,8×10⁻⁶·d_p²))
    b'(h) = 1,5 + 8,6·exp(−0,09·h²)·(1−exp(−d_p/50))
    c'(h) = 1,5 + 14,0·exp(−0,46·h²)·(1−exp(−d_p/50))
    d'(h) = 1,5 + 5,0·exp(−0,9·h²)·(1−exp(−d_p/50))

O primeiro expoente é −0,12·(h−5)².

Correção meteorológica do §8, fonte pontual de emissão constante, Eq. (21)–(22):

    C_met = 0                                          se d_p ≤ 10(h_s + h_r)
    C_met = C_0 · [1 − 10(h_s + h_r)/d_p]             se d_p > 10(h_s + h_r)

C_0 não tem omissão. Sem C_0, C_met não se aplica: o nível fica o de propagação
favorável (vento a favor ou inversão moderada junto ao solo). A média de longo prazo
é L_AT(LT) = L_AT(DW) − C_met (Eq. 6), pelo que esse nível é um limite superior da
média. A nota 22 indica que C_0, na prática, vai de 0 a cerca de +5 dB e que valores
acima de 2 dB são excecionais; um C_0 declarado acima de 5 dB calcula-se na mesma e
fica anotado.

Não está aplicada a forma de 2024 com K_geo (edição diferente; não é a Tabela 3 de 1996).
Barreiras, reflexões e folhagem não foram verificadas.

G em falta ou fora de [0, 1], altura negativa, d_p < 0 ou frequência fora das oito bandas
→ None. Desconhecido não é 0 dB. d_p = 0 está no limite do método: q = 0 e os termos
(1−exp) anulam-se; o valor calcula-se e o chamador regista o alcance curto.

PRESSUPOSTO: a Tabela 3 é de bandas de oitava. Um tom puro usa a banda nominal que o
contém, com limites f/√2 … f·√2. O par 63 Hz / 125 Hz não é uma oitava exacta e os
intervalos sobrepõem-se cerca de 0,7 Hz; no overlap fica a banda de centro mais próximo
em logaritmo, e um empate exacto devolve None.

Os coeficientes foram conferidos com duas transcrições públicas da edição de 1996: a ajuda
do Arup Strutt («ISO9613.2 1996») e o dossiê PUC EL19-003, KM Exhibit 9 (Tabela 3 e
Eq. 21–22). Não se copia o texto da norma.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

NOMINAL_HZ: tuple[float, ...] = (63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0)
ISO9613_2 = ("ISO 9613-2:1996 §7.3.1 (método geral, Tabela 3, Eq. 9) e §8 (Eq. 6, 21 e 22)")
#: ISO 9613-2:1996 §1 (âmbito), conferido na transcrição pública KM Exhibit 9 (PUC EL19-003); a edição de 2024
#: mantém a frase: o método é para fontes no solo e «não se aplica ao som de aeronaves em voo».
SCOPE_NOTE = ("ISO 9613-2:1996 §1: o método é para fontes no solo (estrada, ferrovia, indústria, construção) e não se "
              "aplica ao som de aeronaves em voo. Aqui a fonte é uma aeronave em voo, por isso A_gr e C_met entram só "
              "como extrapolação fora do âmbito (PRESSUPOSTO), nunca como resultado validado da norma.")


def scope_block() -> dict[str, Any]:
    """Âmbito da ISO 9613-2 para uma fonte em voo: fora do âmbito, aplicado só como PRESSUPOSTO."""
    return {"dentro_do_ambito": False, "fonte": "aeronave em voo", "referencia": "ISO 9613-2:1996 §1",
            "nota": SCOPE_NOTE}
_SQRT2 = math.sqrt(2.0)


def _finite(x: float) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _g_ok(G: float | None) -> bool:
    return G is not None and _finite(G) and 0.0 <= G <= 1.0


def octave_band_hz(f_Hz: float) -> float | None:
    """Banda nominal da Tabela 3 que contém ``f_Hz``, ou None fora das oito bandas."""
    if not _finite(f_Hz) or f_Hz <= 0.0:
        return None
    hits = [fc for fc in NOMINAL_HZ if fc / _SQRT2 <= f_Hz <= fc * _SQRT2]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        ranked = sorted(hits, key=lambda fc: abs(math.log(f_Hz / fc)))
        d0 = abs(math.log(f_Hz / ranked[0]))
        d1 = abs(math.log(f_Hz / ranked[1]))
        if abs(d0 - d1) <= 1e-12:
            return None
        return ranked[0]
    return None


def ground_factor_q(dp_m: float, hs_m: float, hr_m: float) -> float | None:
    """q do §7.3.1. None se a geometria não é a do método."""
    if not _finite(dp_m) or not _finite(hs_m) or not _finite(hr_m):
        return None
    if dp_m < 0.0 or hs_m < 0.0 or hr_m < 0.0:
        return None
    limit = 30.0 * (hs_m + hr_m)
    if dp_m <= limit:
        return 0.0
    return 1.0 - limit / dp_m


def a_prime(h_m: float, dp_m: float) -> float:
    return (1.5
            + 3.0 * math.exp(-0.12 * (h_m - 5.0) ** 2) * (1.0 - math.exp(-dp_m / 50.0))
            + 5.7 * math.exp(-0.09 * h_m * h_m) * (1.0 - math.exp(-2.8e-6 * dp_m * dp_m)))


def b_prime(h_m: float, dp_m: float) -> float:
    return 1.5 + 8.6 * math.exp(-0.09 * h_m * h_m) * (1.0 - math.exp(-dp_m / 50.0))


def c_prime(h_m: float, dp_m: float) -> float:
    return 1.5 + 14.0 * math.exp(-0.46 * h_m * h_m) * (1.0 - math.exp(-dp_m / 50.0))


def d_prime(h_m: float, dp_m: float) -> float:
    return 1.5 + 5.0 * math.exp(-0.9 * h_m * h_m) * (1.0 - math.exp(-dp_m / 50.0))


def region_dB(band_Hz: float | None, G: float | None, h_m: float, dp_m: float) -> float | None:
    """A_s ou A_r [dB] de uma banda nominal. None se G, a banda ou a geometria não servem."""
    if (G is None or not _g_ok(G) or band_Hz not in NOMINAL_HZ or not _finite(h_m) or not _finite(dp_m)
            or h_m < 0.0 or dp_m < 0.0):
        return None
    g = G
    if band_Hz == 63.0:
        return -1.5
    if band_Hz == 125.0:
        return -1.5 + g * a_prime(h_m, dp_m)
    if band_Hz == 250.0:
        return -1.5 + g * b_prime(h_m, dp_m)
    if band_Hz == 500.0:
        return -1.5 + g * c_prime(h_m, dp_m)
    if band_Hz == 1000.0:
        return -1.5 + g * d_prime(h_m, dp_m)
    return -1.5 * (1.0 - g)


def middle_dB(band_Hz: float | None, Gm: float | None, q: float | None) -> float | None:
    """A_m [dB]. None se G_m ou q não estão na definição da tabela."""
    if Gm is None or not _g_ok(Gm) or band_Hz not in NOMINAL_HZ or q is None or not _finite(q) or q < 0.0:
        return None
    if band_Hz == 63.0:
        return -3.0 * q
    return -3.0 * q * (1.0 - Gm)


def ground_distance_m(r_m: float, hs_m: float, hr_m: float) -> float | None:
    """d_p = √(r² − (h_s − h_r)²). None se r < |h_s − h_r| (geometria inconsistente)."""
    if not _finite(r_m) or not _finite(hs_m) or not _finite(hr_m):
        return None
    if r_m < 0.0 or hs_m < 0.0 or hr_m < 0.0:
        return None
    dh = hs_m - hr_m
    if r_m < abs(dh):
        return None
    return math.sqrt(r_m * r_m - dh * dh)


def ground_attenuation_dB(f_Hz: float, dp_m: float, hs_m: float, hr_m: float, Gs: float | None,
                          Gr: float | None, Gm: float | None) -> float | None:
    """A_gr [dB] da Eq. (9). None se algum dado sai da Tabela 3 (não é 0 dB)."""
    band = octave_band_hz(f_Hz)
    q = ground_factor_q(dp_m, hs_m, hr_m)
    As = region_dB(band, Gs, hs_m, dp_m)
    Ar = region_dB(band, Gr, hr_m, dp_m)
    Am = middle_dB(band, Gm, q)
    if As is None or Ar is None or Am is None:
        return None
    total = As + Ar + Am
    return 0.0 if total == 0.0 else total


def c_met_dB(dp_m: float, hs_m: float, hr_m: float, C0_dB: float | None) -> float | None:
    """C_met [dB] das Eq. (21)–(22). None se C_0 não foi declarado ou não é ≥ 0.

    None significa «não aplicado», não zero. Zero só quando a equação dá zero
    (C_0 = 0, ou d_p ≤ 10(h_s + h_r) com C_0 declarado).
    """
    if C0_dB is None:
        return None
    if not _finite(C0_dB) or C0_dB < 0.0 or not _finite(dp_m) or not _finite(hs_m) or not _finite(hr_m):
        return None
    if dp_m < 0.0 or hs_m < 0.0 or hr_m < 0.0:
        return None
    limit = 10.0 * (hs_m + hr_m)
    if dp_m <= limit:
        return 0.0
    return float(C0_dB) * (1.0 - limit / dp_m)


@dataclass(frozen=True)
class GroundPath:
    """Alturas [m], factores de solo G ∈ [0, 1] e, se declarado, C_0 [dB]."""

    hs_m: float
    hr_m: float
    Gs: float
    Gr: float
    Gm: float
    C0_dB: float | None = None

    def valid(self) -> bool:
        return (_finite(self.hs_m) and _finite(self.hr_m) and self.hs_m >= 0.0 and self.hr_m >= 0.0
                and _g_ok(self.Gs) and _g_ok(self.Gr) and _g_ok(self.Gm)
                and (self.C0_dB is None or (_finite(self.C0_dB) and self.C0_dB >= 0.0)))


def _block(status: str, reason: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": status, "veredicto": "nao_avaliado", "calibracao": "nao_aplicar",
        "metodo": ISO9613_2, "A_gr_dB": None, "C_met_dB": None, "reason": reason,
    }
    out.update(extra)
    return out


def parse_ground_spec(raw: object) -> tuple[GroundPath | None, dict[str, Any]]:
    """Lê ``noise.iso9613_ground``. Sem o mapa, ou com G em falta, não assume 0 nem 1."""
    if raw is None:
        return None, _block(
            "nao_pedido",
            "Sem hs, hr e G declarados, a atenuação de solo não entra. A omissão não é 0 dB. "
            "O alcance de deteção mantém-se o da pior direção das fontes modeladas, sem correção de solo com sinal.")
    if not isinstance(raw, Mapping):
        return None, _block("nao_avaliado", "iso9613_ground tem de ser um mapa com hs_m, hr_m, Gs, Gr e Gm.")
    missing = [k for k in ("hs_m", "hr_m", "Gs", "Gr", "Gm") if raw.get(k) is None]
    if missing:
        return None, _block("nao_avaliado", "Faltam " + ", ".join(missing) + ". Desconhecido não é 0 dB.")
    try:
        c0 = None if raw.get("C0_dB") is None else float(raw["C0_dB"])
        path = GroundPath(float(raw["hs_m"]), float(raw["hr_m"]), float(raw["Gs"]), float(raw["Gr"]),
                          float(raw["Gm"]), c0)
    except (TypeError, ValueError):
        return None, _block("nao_avaliado", "hs_m, hr_m, G ou C0_dB não são numéricos.")
    if not path.valid():
        return None, _block(
            "nao_avaliado",
            "G fora de [0, 1], altura negativa ou C_0 negativo. Esses dados não entram como 0 dB.")
    notes: list[str] = []
    if path.C0_dB is None:
        notes.append("C_0 ausente: C_met não se aplica. O nível, se A_gr entrar, é o de propagação favorável "
                     "(Eq. 6), limite superior da média de longo prazo.")
    elif path.C0_dB > 5.0:
        notes.append("C_0 declarado acima de +5 dB, fora do intervalo prático da nota 22. O valor declarado "
                     "calcula-se; não foi substituído.")
    elif path.C0_dB > 2.0:
        notes.append("C_0 declarado acima de 2 dB: a nota 22 trata esse valor como excecional.")
    return path, _block(
        "declarado", "", hs_m=path.hs_m, hr_m=path.hr_m, Gs=path.Gs, Gr=path.Gr, Gm=path.Gm,
        C0_dB=path.C0_dB, C_met="nao_aplicado" if path.C0_dB is None else "declarado", notas=notes)


def refraction_status() -> dict[str, Any]:
    """Refração geométrica, barreiras, reflexões e folhagem: não avaliadas."""
    return {
        "evaluated": False, "veredicto": "nao_avaliado", "correction_dB": None,
        "reason": (
            "Não há equação de refração por traçado de raios verificada. A ISO 9613-2:1996 trata a meteorologia "
            "no §8: sem C_met o nível é o de propagação favorável (vento a favor ou inversão moderada) e a média "
            "de longo prazo é L_AT(LT) = L_AT(DW) − C_met (Eq. 6). C_met só entra com C_0 declarado (Eq. 21–22). "
            "Barreiras (A_bar), reflexões e folhagem não foram verificadas e não entram como 0 dB. A forma de 2024 "
            "com K_geo não é a Tabela 3 de 1996 e não está aplicada. A ISO 9613-2 (§1) não se aplica a aeronaves "
            "em voo. Nord2000 e Harmonoise não foram verificados equação a equação contra uma fonte pública e não "
            "estão implementados."
        ),
        "ambito_iso9613_2": scope_block(),
    }


def iso_chain_applied(over_ground: Mapping[str, Any] | None, fly: Mapping[str, Any],
                     *detections: Mapping[str, Any] | None) -> bool:
    """Verdadeiro só quando o nível, o sobrevoo e os alcances pediram A_gr e nenhum componente ficou de fora."""
    if over_ground is None or over_ground.get("status") != "aplicado":
        return False
    if fly.get("ground_complete") is not True:
        return False
    for det in detections:
        if det is not None and det.get("ground_status") != "aplicado":
            return False
    return True


def annotate_ground(block: dict[str, Any], *, applied: bool, c0_declared: bool, components_omitted: bool) -> dict[str, Any]:
    """Separa a verificação da tabela do alcance, que não fica validado."""
    block["tabela"] = {
        "veredicto": "validado" if applied else "nao_avaliado",
        "calibracao": "nao_aplicar",
        "nota": ("A Tabela 3 (e C_met, se C_0 foi declarado) correu com os dados desta chamada. "
                 "Isto verifica a fórmula; não é medição de voo." if applied else
                 "A tabela não fechou nesta chamada. O nível publicado não inclui A_gr."),
    }
    block["alcance"] = {
        "veredicto": "nao_avaliado", "range_bound": "superior",
        "reasons": range_bound_notes(ground_applied=applied, c0_declared=c0_declared,
                                    components_omitted=components_omitted),
    }
    block["ambito"] = scope_block()
    block["veredicto"] = block["tabela"]["veredicto"]
    block["calibracao"] = "nao_aplicar"
    block["range_bound"] = "superior"
    block["range_bound_reasons"] = block["alcance"]["reasons"]
    return block


def range_bound_notes(*, ground_applied: bool, c0_declared: bool, components_omitted: bool) -> list[str]:
    """Porque é que o alcance publicado não é uma distância ISO validada."""
    notes = [
        "O alcance usa a pior direção da fonte (máximo em θ) a cada distância: limite superior das fontes modeladas.",
    ]
    if not ground_applied:
        notes.append(
            "A_gr não entrou no alcance. Nas bandas graves a Tabela 3 dá A_gr negativo (amplificação), pelo que "
            "omitir o solo não torna o alcance um limite superior.")
    elif not c0_declared:
        notes.append(
            "C_0 não declarado: C_met não aplicado. O nível é o caso favorável da Eq. (6), limite superior da "
            "média de longo prazo.")
    if components_omitted:
        notes.append(
            "Há componentes fora das oito bandas ou com geometria inconsistente. Não entram no alcance corrigido: "
            "desconhecido não é audível nem silêncio.")
    if ground_applied:
        notes.append("A ISO 9613-2:1996 §1 não se aplica a aeronaves em voo: A_gr entrou como extrapolação "
                     "(PRESSUPOSTO), não como distância da norma.")
    notes.append(
        "Ruído de espessura não modelado: o nível das fontes que entram é um limite inferior, e o alcance da "
        "espessura não está avaliado.")
    return notes
