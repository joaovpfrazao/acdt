# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Fontes de calor a partir dos modelos que já existem (genérico: hélice térmica/elétrica, VTOL, jato, híbrido).

Cada fonte é um intervalo [lo, hi] em W; ``hi = None`` → majorante desconhecido. Métodos (todos conservação de
energia; os rendimentos, resistências e frações são **entradas** com fonte — nada é estimado aqui):

* Carga elétrica (aviónica, carga útil, sistemas de bordo): toda a potência elétrica consumida a bordo vira calor
  no compartimento onde está, menos a fração radiada para fora (RF, laser) se declarada.
* Cadeia elétrica de propulsão (bateria → ESC/inversor → motor): perda total P_bat·(1 − η_cadeia), com
  η_cadeia = η_total/η_hélice do dimensionamento (Hepperle 2012; ``weights.py``). Repartição: motor P_veio·(1/η_m − 1), ESC
  (P_veio/η_m)·(1/η_ESC − 1), bateria I²R (I = P/V_nom, PRESSUPOSTO tensão nominal) ou P·(1 − η_bat), quando
  declarados. Componente não declarado: [0, perda total − perdas conhecidas]; um único componente em falta fica
  determinado pela diferença.
* Motor térmico (pistão, turbo-hélice, gerador de híbrido): potência do combustível ṁ_f·PCI; calor rejeitado ao
  arrefecimento = fração declarada da potência do combustível, ou intervalo [0, ṁ_f·PCI − P_veio] (o resto sai
  pelo escape; Heywood, *Internal Combustion Engine Fundamentals*, 1988, Cap. 12 — balanço de energia do motor).
  PCI por omissão: mínimos das especificações ASTM D910 (avgas, 43,5 MJ/kg) e ASTM D1655 (Jet A/A-1,
  42,8 MJ/kg) — PRESSUPOSTO: combustível no mínimo da especificação.
* Gerador elétrico (híbrido): P_veio·(1 − η_gerador), com η declarado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

LHV_MJ_KG = {"avgas": 43.5, "jet_a": 42.8}
LHV_REF = {"avgas": "ASTM D910, Tabela 1: poder calorífico inferior mín. 43,5 MJ/kg (todas as classes)",
           "jet_a": "ASTM D1655: poder calorífico inferior mín. 42,8 MJ/kg (Jet A e Jet A-1)"}
ICE_REF = "Heywood, Internal Combustion Engine Fundamentals (McGraw-Hill, 1988), Cap. 12 (balanço de energia)"


@dataclass
class HeatSource:
    id: str
    lo: float
    hi: float | None
    method: str
    notes: list[str] = field(default_factory=list)
    group: str | None = None  # fontes que partilham um majorante comum (p. ex. perdas por repartir da cadeia)
    group_cap: float | None = None

    @property
    def known(self) -> bool:
        return self.hi is not None and abs(self.hi - self.lo) <= 1e-9 * max(1.0, abs(self.hi))

    def scaled(self, f: float) -> "HeatSource":
        return HeatSource(self.id, self.lo * f, None if self.hi is None else self.hi * f, self.method, list(self.notes),
                          self.group, None if self.group_cap is None else self.group_cap * f)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id, "lo_W": self.lo, "hi_W": self.hi, "method": self.method,
                             "notes": self.notes}
        if self.group:
            d.update(group=self.group, group_cap_W=self.group_cap)
        return d


def from_spec(sid: str, v: Any, method: str = "declarado pelo utilizador") -> HeatSource:
    """``heat_W``: número, [lo, hi] ou None (desconhecido)."""
    if v is None:
        return HeatSource(sid, 0.0, None, method, ["valor desconhecido: majorante em aberto"])
    if isinstance(v, (list, tuple)) and len(v) == 2:
        lo, hi = float(v[0]), (None if v[1] is None else float(v[1]))
        return HeatSource(sid, lo, hi, method)
    return HeatSource(sid, float(v), float(v), method)


def electrical_load(sid: str, P_W: float, radiated_fraction: float = 0.0, method: str = "") -> HeatSource:
    q = max(P_W, 0.0) * (1.0 - radiated_fraction)
    return HeatSource(sid, q, q, method or "potência elétrica consumida a bordo → calor (conservação de energia)",
                      [] if radiated_fraction else ["PRESSUPOSTO: nenhuma fração radiada para fora da aeronave"])


def electric_chain(P_batt_W: float, eta_chain: float, *, eta_esc: float | None = None, eta_motor: float | None = None,
                   eta_battery: float | None = None, R_pack_ohm: float | None = None, V_nom: float | None = None,
                   prefix: str = "") -> dict[str, HeatSource]:
    """Perdas da cadeia bateria → ESC → motor, repartidas pelo que for declarado."""
    if not 0.0 < eta_chain <= 1.0:
        raise ValueError(f"η_cadeia = {eta_chain} fora de ]0, 1]")
    P = max(P_batt_W, 0.0)
    L = P * (1.0 - eta_chain)
    meth = f"perda total da cadeia P_bat·(1 − η_cadeia), η_cadeia = {eta_chain:.3f}"
    known: dict[str, float] = {}
    notes: dict[str, list[str]] = {"bateria": [], "esc": [], "motor": []}
    if eta_battery is not None:
        known["bateria"] = P * (1.0 - eta_battery)
        notes["bateria"].append(f"P·(1 − η_bat), η_bat = {eta_battery}")
    elif R_pack_ohm is not None and V_nom:
        I = P / V_nom
        known["bateria"] = I * I * R_pack_ohm
        notes["bateria"].append(f"I²R, I = P/V_nom = {I:.2f} A (PRESSUPOSTO: tensão nominal), R = {R_pack_ohm:.4g} Ω")
    P_shaft = P * eta_chain  # potência no veio (conhecida pelo dimensionamento)
    if eta_motor is not None:
        known["motor"] = P_shaft * (1.0 / eta_motor - 1.0)
        notes["motor"].append(f"P_veio·(1/η_m − 1), η_m = {eta_motor}")
        if eta_esc is not None:
            known["esc"] = P_shaft / eta_motor * (1.0 / eta_esc - 1.0)
            notes["esc"].append(f"P_in,m·(1/η_ESC − 1), η_ESC = {eta_esc}")
    out: dict[str, HeatSource] = {}
    k_sum = sum(known.values())
    missing = [c for c in ("bateria", "esc", "motor") if c not in known]
    rest = max(L - k_sum, 0.0)
    for c in ("bateria", "esc", "motor"):
        if c in known:
            out[c] = HeatSource(prefix + c, known[c], known[c], meth, notes[c])
        elif len(missing) == 1:
            out[c] = HeatSource(prefix + c, rest, rest, meth, ["determinado pela diferença (único componente não "
                                                                "declarado)"])
        else:
            out[c] = HeatSource(prefix + c, 0.0, rest, meth, ["repartição desconhecida: [0, perda total − perdas "
                                                              "conhecidas] (declare η_ESC, η_motor, R_interna); "
                                                              "majorante partilhado com os outros não declarados"],
                                group=prefix + "cadeia_por_repartir", group_cap=rest)
    if k_sum > L * (1 + 1e-6):
        for hs in out.values():
            hs.notes.append(f"perdas declaradas ({k_sum:.1f} W) excedem a perda total do dimensionamento ({L:.1f} W): "
                           "η inconsistentes com η_total")
    out["cadeia_total"] = HeatSource(prefix + "cadeia_total", L, L, meth)
    return out


def ice_cooling(sid: str, P_shaft_W: float, fuel_flow_kg_s: float, lhv_J_kg: float,
                cooling_fraction: float | None = None, heat_rejection_W: float | None = None) -> HeatSource:
    """Calor rejeitado ao sistema de arrefecimento de um motor térmico."""
    P_fuel = max(fuel_flow_kg_s, 0.0) * lhv_J_kg
    waste = max(P_fuel - max(P_shaft_W, 0.0), 0.0)
    meth = f"balanço de energia do motor ({ICE_REF}): P_comb = ṁ_f·PCI = {P_fuel:.0f} W, P_veio = {P_shaft_W:.0f} W"
    if heat_rejection_W is not None:
        return HeatSource(sid, float(heat_rejection_W), float(heat_rejection_W), "declarado pelo utilizador")
    if cooling_fraction is not None:
        q = cooling_fraction * P_fuel
        return HeatSource(sid, q, q, meth + f"; fração ao arrefecimento declarada {cooling_fraction}")
    return HeatSource(sid, 0.0, waste, meth, ["fração ao arrefecimento não declarada: [0, P_comb − P_veio] "
                                              "(o resto sai pelo escape)"])


def generator_loss(sid: str, P_shaft_W: float, eta_gen: float | None) -> HeatSource:
    if eta_gen is None:
        return HeatSource(sid, 0.0, None, "gerador sem rendimento declarado", ["η_gerador desconhecido"])
    q = max(P_shaft_W, 0.0) * (1.0 - eta_gen)
    return HeatSource(sid, q, q, f"P_veio·(1 − η_gerador), η = {eta_gen}")


def total(sources: Mapping[str, HeatSource] | list[HeatSource]) -> tuple[float, float | None]:
    """Soma de intervalos; fontes do mesmo ``group`` somam no máximo ``group_cap`` (majorante partilhado)."""
    it = list(sources.values()) if isinstance(sources, Mapping) else list(sources)
    lo = sum(s.lo for s in it)
    if any(s.hi is None for s in it):
        return lo, None
    hi = 0.0
    groups: dict[str, list[HeatSource]] = {}
    for s in it:
        if s.group:
            groups.setdefault(s.group, []).append(s)
        else:
            hi += float(s.hi or 0.0)
    for g in groups.values():
        sh = sum(float(s.hi or 0.0) for s in g)
        cap = g[0].group_cap
        hi += sh if cap is None else min(sh, max(cap, sum(s.lo for s in g)))
    return lo, hi
