# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Momento de picada a sustentação nula dos corpos (C_m0 dos corpos) pelo método de Multhopp.

Método (citado)
---------------
* Multhopp, H. 1942, "Aerodynamics of the fuselage", NACA TM 1036; na forma de Nelson, R. C. 1998, *Flight
  Stability and Automatic Control*, 2.ª ed., Sec. 2.3 (contribuição da fuselagem) e de Tulapurkara, E. G.,
  NPTEL "Flight dynamics I" (IIT Madras), Cap. 2, Eq. 2.56 e Exemplo 2.4:

      C_m0,f = (k2 − k1) / (36,5 S c̄) · Σ w_f² (α_0L,f + i_f) Δx       [ângulos em graus]

  36,5 = 2·57,3/π, por isso em radianos C_m0,f = (k2 − k1)·π/(2 S c̄) · Σ w_f² (α_0L,f + i_f) Δx.
  w_f é a largura média em Δx, α_0L,f o ângulo de sustentação nula da asa relativo à linha de referência da
  fuselagem (α_0L,w + i_w) e i_f a incidência da linha média do corpo relativa a essa linha, negativa para
  nariz descaído ou cauda levantada (aft upsweep).
* (k2 − k1): coeficientes de massa aparente do esferoide prolato de Lamb (Hydrodynamics, 6.ª ed., §373), como
  em Munk 1924, NACA TR-184; razão de finura l_f/d_e com d_e o diâmetro equivalente da secção máxima
  ((π/4) d_e² = A_max). Os valores tabelados de Munk (l/d 4: k1 0,082, k2 0,860; l/d 10: 0,021, 0,960) são
  reproduzidos no teste.

PRESSUPOSTOS
------------
* Escoamento local sobre o corpo = α_0L,f + i_f (sem o campo de upwash/downwash da asa no termo de C_m0, como
  na Eq. 2.56); o termo de C_mα dos corpos é o desvio Torenbeek do ponto neutro já usado no trim.
* Numa asa voadora o corpo central está parcialmente imerso na asa; a fórmula é aplicada ao corpo inteiro.
* Corpos rodados (eixo fora de x) ficam **unassessed** (a fórmula é para corpos ao longo de x).
"""
from __future__ import annotations

import math

MULTHOPP_SOURCE = ("Multhopp 1942, NACA TM 1036; Nelson 1998, Flight Stability and Automatic Control 2.ª ed., "
                   "Sec. 2.3; Tulapurkara, NPTEL Flight dynamics I (IIT Madras) Cap. 2 Eq. 2.56 e Exemplo 2.4; "
                   "k2 − k1 do esferoide prolato de Lamb (§373) / Munk 1924, NACA TR-184")


def munk_k1_k2(fineness: float) -> tuple[float, float]:
    """Coeficientes de massa aparente longitudinal (k1) e transversal (k2) de um esferoide prolato de razão de
    finura ``fineness`` = comprimento / diâmetro (Lamb §373; Munk 1924)."""
    f = float(fineness)
    if f <= 1.0:
        return 0.5, 0.5   # esfera
    e = math.sqrt(1.0 - 1.0 / f ** 2)
    L = math.log((1 + e) / (1 - e))
    a0 = 2 * (1 - e ** 2) / e ** 3 * (0.5 * L - e)
    b0 = 1 / e ** 2 - (1 - e ** 2) / (2 * e ** 3) * L
    return a0 / (2 - a0), b0 / (2 - b0)


def lame_area(w: float, h: float, n: float = 2.0) -> float:
    """Área da secção de Lamé |y/a|^n + |z/b|^n = 1 com a = w/2, b = h/2 (elipse para n = 2)."""
    a, b = 0.5 * w, 0.5 * h
    return 4 * a * b * math.gamma(1 + 1 / n) ** 2 / math.gamma(1 + 2 / n)


def multhopp_cm0_sum(widths, dxs, angles_deg, k2_k1: float, S: float, c: float) -> float:
    """Eq. 2.56 com uma tabela de estações (largura média, Δx, α_0L,f + i_f em graus)."""
    s = sum(w * w * a * dx for w, dx, a in zip(widths, dxs, angles_deg))
    return k2_k1 * s / (36.5 * S * c)


def body_cm0(body, alpha0_frl_deg: float, S: float, c: float) -> dict:
    """C_m0 de um corpo da montagem (``Body`` com estações x, w, h, zc, n). Espelhado → ×2."""
    st = body.stations
    xs = [float(s["x"]) for s in st]
    lf = xs[-1] - xs[0]
    if lf <= 0:
        return {"status": "unassessed", "issue": "comprimento nulo"}
    amax = max(lame_area(float(s["w"]), float(s["h"]), float(s.get("n", 2.0))) for s in st)
    de = math.sqrt(4 * amax / math.pi)
    fin = lf / de if de > 0 else float("inf")
    k1, k2 = munk_k1_k2(fin)
    rows = []
    for s0, s1 in zip(st[:-1], st[1:]):
        dx = float(s1["x"]) - float(s0["x"])
        if dx <= 0:
            continue
        wf = 0.5 * (float(s0["w"]) + float(s1["w"]))
        i_f = -math.degrees(math.atan2(float(s1["zc"]) - float(s0["zc"]), dx))   # cauda levantada → negativo
        rows.append({"dx": dx, "w_f": wf, "i_f_deg": i_f, "angle_deg": alpha0_frl_deg + i_f})
    cm0 = multhopp_cm0_sum([r["w_f"] for r in rows], [r["dx"] for r in rows], [r["angle_deg"] for r in rows],
                           k2 - k1, S, c)
    mult = 2 if getattr(body, "mirror", False) else 1
    return {"status": "assessed", "Cm0": cm0 * mult, "fineness": fin, "k1": k1, "k2": k2, "k2_minus_k1": k2 - k1,
            "length_m": lf, "d_e_m": de, "mirrored": bool(mult == 2), "stations": rows}


def bodies_cm0(asm, alpha0_frl_deg: float) -> dict:
    """Soma de Multhopp sobre os corpos da montagem (sem os itens internos). Corpos rodados → unassessed."""
    from .sizing import _body_is_rotated, _parts, main_wing
    _, gw = main_wing(asm)
    _, bodies, _, _, _ = _parts(asm)
    per, rotated = {}, []
    for b in bodies:
        if _body_is_rotated(b):
            rotated.append(b.name)
            continue
        per[b.name] = body_cm0(b, alpha0_frl_deg, gw["S"], gw["mac"])
    out = {"method": MULTHOPP_SOURCE, "alpha0L_frl_deg": alpha0_frl_deg, "S": gw["S"], "mac": gw["mac"],
           "bodies": per, "rotated_bodies_unassessed": rotated,
           "assumptions": ["PRESSUPOSTO: Eq. 2.56 sem o campo de upwash da asa no termo de C_m0",
                           "PRESSUPOSTO: corpo central parcialmente imerso na asa tratado como corpo inteiro"]}
    if rotated:
        out["status"] = "unassessed"
        out["Cm0"] = None
        out["issue"] = f"corpos rodados sem método: {rotated} (desconhecido ≠ 0)"
        return out
    vals = [v["Cm0"] for v in per.values() if v.get("status") == "assessed"]
    out["status"] = "assessed"
    out["Cm0"] = float(sum(vals))
    return out
