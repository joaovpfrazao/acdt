"""Deterministic failure hooks for the shared mission YAML.

The block is a list of events plus, optionally, one seeded draw from a catalogue. That draw is a single
``random.Random(seed).choices`` call. It is not a Monte Carlo: there is no sample of outcomes, and the weights
are scenario weights given by the caller, not failure rates (those stay in the ARP4761 assessment). A catalogue
without a seed is refused, so a run cannot become quietly random.

What each event does to the point-mass aircraft is a change of inputs to the cited performance model, not a new
failure model:

* ``engine_out`` — thrust of the failed fraction is removed (identical engines, PRESSUPOSTO). The default is
  all engines out, and the glide that follows is Anderson 1999 Ch. 5.
* ``sensor_loss`` — coverage stops. The path changes only when the response says so.
* ``link_loss`` — no change to force or energy. The response is still flown.
* ``fuel_degradation`` / ``battery_degradation`` — from the trigger on, the fuel flow or battery power of
  Anderson / Raymer is multiplied by ``factor`` (a scenario multiplier, PRESSUPOSTO, not an ageing law).
  Optional ``remaining_fraction`` reduces the usable remainder without changing mass.

Responses flown by the point-mass integrator and only logged by the 6-DOF runner: ``continue``, ``rtb``,
``divert``. Triggers that are set are combined with AND: ``t_s``, ``segment`` plus ``t_into_s``,
``altitude_m_below``, ``altitude_m_above``, ``fuel_fraction_below``.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

TYPES = {"engine_out", "sensor_loss", "link_loss", "fuel_degradation", "battery_degradation"}
RESPONSES = {"continue", "rtb", "divert"}
_DEGRADATION = {"fuel_degradation", "battery_degradation"}


@dataclass
class FailureEvent:
    type: str
    response: str
    t_s: float | None = None
    segment: str | None = None
    t_into_s: float = 0.0
    altitude_m_below: float | None = None
    altitude_m_above: float | None = None
    fuel_fraction_below: float | None = None
    factor: float | None = None
    remaining_fraction: float | None = None
    divert_km: tuple | None = None
    then: str = "land"
    loiter_min: float | None = None
    engines_out: int | None = None
    weight: float = 1.0
    source: str = "event"
    seed: int | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "type": self.type, "response": self.response, "source": self.source,
            "t_s": self.t_s, "segment": self.segment, "t_into_s": self.t_into_s,
            "altitude_m_below": self.altitude_m_below, "altitude_m_above": self.altitude_m_above,
            "fuel_fraction_below": self.fuel_fraction_below, "factor": self.factor,
            "remaining_fraction": self.remaining_fraction,
            "divert_km": list(self.divert_km) if self.divert_km is not None else None,
            "then": self.then, "loiter_min": self.loiter_min, "engines_out": self.engines_out,
            "weight": self.weight, "seed": self.seed,
        }
        return {k: v for k, v in d.items() if v is not None}

    def matches(self, t: float, seg_name: str, seg_type: str, t_into: float, h: float,
                fuel_fraction: float | None) -> bool:
        cond = []
        if self.t_s is not None:
            cond.append(t + 1e-9 >= self.t_s)
        if self.segment is not None:
            cond.append(self.segment in (seg_name, seg_type) and t_into + 1e-9 >= self.t_into_s)
        if self.altitude_m_below is not None:
            cond.append(h <= self.altitude_m_below + 1e-9)
        if self.altitude_m_above is not None:
            cond.append(h + 1e-9 >= self.altitude_m_above)
        if self.fuel_fraction_below is not None:
            cond.append(fuel_fraction is not None and fuel_fraction <= self.fuel_fraction_below + 1e-12)
        return bool(cond) and all(cond)

    def next_time(self, t: float, seg_name: str | None, seg_type: str | None, seg_t0: float | None) -> float | None:
        """Soonest absolute time strictly after ``t`` at which a clock trigger can become true. Altitude and
        fuel triggers are checked every step; they have no closed-form time."""
        times = []
        if self.t_s is not None and self.t_s > t + 1e-12:
            times.append(self.t_s)
        if self.segment is not None and seg_t0 is not None and self.segment in (seg_name, seg_type):
            tt = seg_t0 + self.t_into_s
            if tt > t + 1e-12:
                times.append(tt)
        return min(times) if times else None


def _km_pair(v, what: str) -> tuple:
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        raise ValueError(f"{what} deve ser [norte_km, este_km]")
    return (float(v[0]) * 1000.0, float(v[1]) * 1000.0)


def _parse(raw: dict, source: str) -> FailureEvent:
    if not isinstance(raw, dict):
        raise ValueError("cada evento de falha é um dicionário")
    typ = raw.get("type")
    if typ not in TYPES:
        raise ValueError(f"falha {typ!r} desconhecida; válidas: {sorted(TYPES)}")
    resp = raw.get("response", "continue")
    if resp not in RESPONSES:
        raise ValueError(f"resposta {resp!r} desconhecida; válidas: {sorted(RESPONSES)}")
    triggers = ("t_s", "segment", "altitude_m_below", "altitude_m_above", "fuel_fraction_below")
    if not any(k in raw for k in triggers):
        raise ValueError(f"falha {typ}: falta um instante ou uma condição ({', '.join(triggers)})")
    factor = raw.get("factor")
    if typ in _DEGRADATION:
        if factor is None:
            raise ValueError(f"{typ} precisa de factor (> 0) sobre o consumo")
        if float(factor) <= 0:
            raise ValueError(f"{typ}: factor tem de ser > 0")
    rem = raw.get("remaining_fraction")
    if rem is not None and not 0.0 <= float(rem) <= 1.0:
        raise ValueError("remaining_fraction tem de estar em [0, 1]")
    then = raw.get("then", "land")
    if then not in ("land", "loiter"):
        raise ValueError("then: land ou loiter")
    n_out = raw.get("engines_out")
    if n_out is not None and int(n_out) < 1:
        raise ValueError("engines_out tem de ser ≥ 1")
    w = float(raw.get("weight", 1.0))
    if w < 0:
        raise ValueError("weight do catalogue tem de ser ≥ 0")
    return FailureEvent(
        type=typ, response=resp, t_s=float(raw["t_s"]) if "t_s" in raw else None,
        segment=raw.get("segment"), t_into_s=float(raw.get("t_into_s", 0.0)),
        altitude_m_below=float(raw["altitude_m_below"]) if "altitude_m_below" in raw else None,
        altitude_m_above=float(raw["altitude_m_above"]) if "altitude_m_above" in raw else None,
        fuel_fraction_below=float(raw["fuel_fraction_below"]) if "fuel_fraction_below" in raw else None,
        factor=float(factor) if factor is not None else None,
        remaining_fraction=float(rem) if rem is not None else None,
        divert_km=_km_pair(raw["divert_km"], "divert_km") if "divert_km" in raw else None,
        then=then, loiter_min=float(raw["loiter_min"]) if "loiter_min" in raw else None,
        engines_out=int(n_out) if n_out is not None else None, weight=w, source=source,
    )


def validate_failures(block: dict) -> None:
    """Schema check only. The seeded draw happens in :func:`resolve_failures`, once per run."""
    if not isinstance(block, dict):
        raise ValueError("failures tem de ser um dicionário {events, catalogue, seed}")
    for raw in block.get("events") or []:
        _parse(raw, "event")
    cat = block.get("catalogue") or []
    if not isinstance(cat, list):
        raise ValueError("failures.catalogue é uma lista de eventos")
    for raw in cat:
        _parse(raw, "seed")
    seed = block.get("seed", None)
    if cat and seed is None:
        raise ValueError("failures.catalogue precisa de seed (um sorteio reproduzível; "
                         "Monte Carlo não está implementado)")
    if seed is not None and not cat:
        raise ValueError("failures.seed só se usa com catalogue")
    if cat and sum(float(c.get("weight", 1.0)) for c in cat) <= 0:
        raise ValueError("os pesos do catalogue têm de somar mais de zero")


def resolve_failures(mission: dict) -> list[FailureEvent]:
    """Explicit events, plus one catalogue row when ``seed`` is set. Divert targets fall back to the
    mission's ``divert_km``. The same seed always returns the same row."""
    block = mission.get("failures")
    if not block:
        return []
    validate_failures(block)
    events = [_parse(raw, "event") for raw in (block.get("events") or [])]
    cat = block.get("catalogue") or []
    if block.get("seed", None) is not None:
        seed = int(block["seed"])
        weights = [float(c.get("weight", 1.0)) for c in cat]
        pick = random.Random(seed).choices(range(len(cat)), weights=weights, k=1)[0]
        drawn = _parse(cat[pick], "seed")
        drawn.seed = seed
        events.append(drawn)
    fallback = _km_pair(mission["divert_km"], "divert_km") if mission.get("divert_km") is not None else None
    for e in events:
        if e.response == "divert" and e.divert_km is None:
            if fallback is None:
                raise ValueError(f"{e.type}: resposta divert precisa de divert_km no evento ou na missão")
            e.divert_km = fallback
        if e.response == "divert" and e.then == "loiter" and e.loiter_min is None:
            raise ValueError(f"{e.type}: divert com then=loiter precisa de loiter_min")
    return events
