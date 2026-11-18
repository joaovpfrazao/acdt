"""Top-down cost models, learning curves and operating cost (Phase 7).

* :func:`dapca4` — DAPCA IV (RAND), Raymer (2018) Ch. 18, constant 2012 USD with CPI escalation input.
* :func:`eastlake` — modified Eastlake GA model (Gudmundsson 2014 Ch. 2), see :mod:`acdt.domains.aircraft.cost`.
* :func:`learning_unit`, :func:`learning_cum_avg`, :func:`learning_total` — Crawford (unit) and Wright
  (cumulative-average) learning curves (NASA JSC learning-curve calculator conventions).
* :func:`operating_cost` / :func:`operational_cost_from_dict` — DOC per flight hour (Raymer 2018 Ch. 18
  element structure); rates are dated inputs; missing activated terms → status unassessed/partial
  (never a silent zero). ``unit_price`` may come from Eastlake / DAPCA IV CERs (Gudmundsson 2014 Ch. 2).
  No default prices; no invented L2 vendor quotes (AGENTS.md / HANDOFF MÉDIA §5).

All rates and indices are inputs; the defaults are the cited ones in :mod:`.refdata` (dated).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields

from ..cost import EastlakeInputs, eastlake_unit_cost
from . import refdata as R

LB = 0.45359237
KT = 0.514444


# ------------------------------------------------------------------------------------------------ learning
def _b(slope: float) -> float:
    if not 0.5 <= slope <= 1.0:
        raise ValueError(f"learning slope {slope} outside 0.5..1.0")
    return math.log(slope, 2)


def learning_unit(T1: float, n: float, slope: float = 0.85) -> float:
    """Crawford unit theory (Crawford 1944): cost/time of unit n, T_n = T_1 n^b, b = log2(slope)."""
    return T1 * n ** _b(slope)


def learning_total(T1: float, N: int, slope: float = 0.85, first: int = 1) -> float:
    """Total of units first..first+N-1 under the Crawford unit curve (exact sum)."""
    b = _b(slope)
    return T1 * sum(k**b for k in range(first, first + int(N)))


def learning_cum_avg(T1: float, N: float, slope: float = 0.85, theory: str = "crawford") -> float:
    """Cumulative average of the first N units. ``wright``: Wright (1936) cumulative-average theory, Ȳ_N = T_1 N^b;
    ``crawford``: average of the unit curve (exact sum / N)."""
    if theory == "wright":
        return T1 * N ** _b(slope)
    return learning_total(T1, int(N), slope) / int(N)


def learning_factor(N: float, slope: float = 0.85, theory: str = "crawford") -> float:
    """Average-to-first-unit ratio over N units (1.0 for N = 1)."""
    return learning_cum_avg(1.0, max(N, 1), slope, theory)


# ------------------------------------------------------------------------------------------------ DAPCA IV
@dataclass
class DapcaInputs:
    We_kg: float                 # empty weight
    V_kt: float                  # maximum velocity [kt]
    Q: int                       # production quantity (lesser of quantity or 5-year production)
    FTA: int = 2                 # flight-test aircraft
    cpi: float = 1.0             # CPI(year)/CPI(2012) (refdata.cpi_factor)
    R_E: float = 115.0           # 2012 USD/h wrap rates (Raymer 6th ed. Ch. 18)
    R_T: float = 118.0
    R_Q: float = 108.0
    R_M: float = 98.0
    cargo: bool = False          # H_Q = 0.076 H_M (cargo) else 0.133 H_M
    material_factor: float = 1.0  # Raymer: Al 1.0; graphite-epoxy 1.1-1.8; fibreglass 1.1-1.2; steel 1.5-2.0
    n_engines: int = 1
    engine_cost: float | None = None  # per engine, USD of the run year (piston / electric: give it)
    turbine: dict | None = None  # {T_max_lbf, M_max, T_t4_R} -> C_eng (2012 USD) x cpi
    avionics_cost: float = 0.0   # per aircraft, USD of the run year (Raymer: 5-25 % of flyaway)
    profit_fraction: float = 0.0  # user input (not part of DAPCA)


def dapca4(x: DapcaInputs) -> dict:
    """DAPCA IV (Raymer 2018, Ch. 18, eqs. 18.1-18.9 in fps units, 2012 USD).

    Hours: H_E = 4.86 We^0.777 V^0.894 Q^0.163; H_T = 5.99 We^0.777 V^0.696 Q^0.263;
    H_M = 7.37 We^0.820 V^0.484 Q^0.641; H_Q = 0.076 H_M (cargo) | 0.133 H_M.
    Costs: C_D = 91.3 We^0.630 V^1.3; C_F = 2498 We^0.325 V^0.822 FTA^1.21; C_M = 22.1 We^0.921 V^0.621 Q^0.799;
    turbine engine C_eng = 3112 (0.043 T_max + 243.25 M_max + 0.969 T_t4 − 2228).
    The material factor multiplies engineering, tooling, manufacturing and QC hours (Raymer's composite
    'fudge factors'). Database: military and transport aircraft; Gudmundsson recommends Eastlake for GA."""
    We = x.We_kg / LB
    V, Q = x.V_kt, max(int(x.Q), 1)
    f = x.material_factor
    H_E = 4.86 * We**0.777 * V**0.894 * Q**0.163 * f
    H_T = 5.99 * We**0.777 * V**0.696 * Q**0.263 * f
    H_M = 7.37 * We**0.820 * V**0.484 * Q**0.641 * f
    H_Q = (0.076 if x.cargo else 0.133) * H_M
    c = x.cpi
    C_D = 91.3 * We**0.630 * V**1.3 * c
    C_F = 2498.0 * We**0.325 * V**0.822 * x.FTA**1.21 * c
    C_M = 22.1 * We**0.921 * V**0.621 * Q**0.799 * c
    if x.engine_cost is not None:
        C_eng = x.engine_cost
    elif x.turbine:
        t = x.turbine
        C_eng = 3112.0 * (0.043 * t["T_max_lbf"] + 243.25 * t["M_max"] + 0.969 * t["T_t4_R"] - 2228.0) * c
    else:
        C_eng = 0.0
    lab = {"engineering": H_E * x.R_E * c, "tooling": H_T * x.R_T * c, "manufacturing": H_M * x.R_M * c,
           "quality": H_Q * x.R_Q * c}
    nonrec = lab["engineering"] + lab["tooling"] + C_D + C_F
    rec = lab["manufacturing"] + lab["quality"] + C_M + (C_eng * x.n_engines + x.avionics_cost) * Q
    total = nonrec + rec
    unit = total / Q * (1 + x.profit_fraction)
    return {"method": "DAPCA IV (Raymer 2018 Ch. 18, 2012 USD x CPI)",
            "hours": {"engineering": H_E, "tooling": H_T, "manufacturing": H_M, "quality": H_Q,
                      "manufacturing_per_unit": H_M / Q},
            "costs": {**lab, "dev_support": C_D, "flight_test": C_F, "materials": C_M,
                      "engines_per_aircraft": C_eng * x.n_engines, "avionics_per_aircraft": x.avionics_cost},
            "non_recurring": nonrec, "recurring": rec, "total_program": total,
            "flyaway_per_unit": rec / Q, "unit_cost": unit, "inputs": asdict(x),
            "notes": ["DAPCA IV database is military/transport aircraft; for light GA prefer Eastlake "
                      "(Gudmundsson 2014) and treat DAPCA as an upper reference"]}


def eastlake(**kw) -> dict:
    """Modified Eastlake (Gudmundsson 2014 Ch. 2) as a dict; keyword arguments = :class:`EastlakeInputs`."""
    x = EastlakeInputs(**kw)
    cb = eastlake_unit_cost(x)
    return {"method": "modified Eastlake (Gudmundsson 2014 Ch. 2, 2012 USD x CPI)", **cb.as_dict(), "inputs": asdict(x)}


# ------------------------------------------------------------------------------------------------ operating cost
@dataclass
class OperatingInputs:
    """Direct operating cost per flight hour. All prices are inputs with provenance (no defaults).

    ``profile``:
      * ``elements`` (default) — only terms with enough inputs are assessed; activated-but-incomplete
        terms are unassessed (never a silent zero). Maintenance / depreciation are NOT auto-required.
      * ``full`` — also requires maintenance labour (mmh × wage) and depreciation for ``status=ok``.
    """
    flight_hours_per_year: float
    unit_price: float                       # acquisition price (USD); may come from Eastlake CER
    fuel_kg_per_h: float = 0.0              # from the mission analysis
    fuel_price_per_kg: float | None = None
    energy_kWh_per_h: float = 0.0           # electric: battery energy drawn per flight hour
    electricity_price_per_kWh: float | None = None
    battery_pack_cost: float = 0.0          # electric: replacement cost of the pack set
    battery_cycle_life: float | None = None  # cycles to end of life (datasheet)
    flights_per_hour: float = 1.0           # cycles per flight hour (1 / mean flight duration)
    maintenance_mmh_per_fh: float | None = None  # maintenance man-hours per flight hour
    maintenance_rate_per_h: float | None = None   # wage / shop rate
    maintenance_parts_per_fh: float = 0.0
    engine_overhaul_cost: float = 0.0
    engine_tbo_h: float | None = None
    n_engines: int = 1
    depreciation_years: float | None = None
    residual_fraction: float = 0.0
    insurance_rate_per_year: float = 0.0    # fraction of unit price per year
    attrition_per_fh: float = 0.0           # UAV: losses per flight hour (x unit price)
    crew_cost_per_fh: float = 0.0
    profile: str = "elements"               # elements | full
    sources: dict = field(default_factory=dict)  # {field: source string with date}


def operating_cost(x: OperatingInputs) -> dict:
    """DOC per flight hour = fuel/energy + maintenance + engine overhaul reserve (cost/TBO) + battery
    replacement (pack cost / cycle life × cycles per FH) + depreciation (straight line) + insurance +
    UAV attrition + crew.

    Cost-element structure of Raymer (2018) Ch. 18 *operations and maintenance*; rates are dated
    user/agent inputs. Acquisition ``unit_price`` may be an Eastlake / DAPCA CER (Gudmundsson 2014
    Ch. 2; Raymer 2018 Ch. 18) — that is the CER → operational chain, not a separate Eastlake DOC CER.

    Missing wage, fuel price, utilization, cycle life, TBO, or a CER coefficient for an *activated*
    term → that term is **unassessed** (never a silent zero that understates cost). ``per_flight_hour``
    is set only when ``status == "ok"``; otherwise use ``assessed_sum_per_fh`` with the status flag.
    """
    if x.profile not in ("elements", "full"):
        raise ValueError("profile must be 'elements' or 'full'")
    if not x.flight_hours_per_year or x.flight_hours_per_year <= 0:
        raise ValueError("flight_hours_per_year must be > 0 (utilization)")

    items: dict[str, float] = {}
    unassessed: list[str] = []

    if x.fuel_kg_per_h:
        if x.fuel_price_per_kg is None:
            unassessed.append("fuel_price_per_kg")
        else:
            items["fuel"] = x.fuel_kg_per_h * x.fuel_price_per_kg
    if x.energy_kWh_per_h:
        if x.electricity_price_per_kWh is None:
            unassessed.append("electricity_price_per_kWh")
        else:
            items["energy"] = x.energy_kWh_per_h * x.electricity_price_per_kWh
    if x.battery_pack_cost:
        if not x.battery_cycle_life:
            unassessed.append("battery_cycle_life")
        else:
            items["battery_replacement"] = x.battery_pack_cost / x.battery_cycle_life * x.flights_per_hour

    mmh, rate = x.maintenance_mmh_per_fh, x.maintenance_rate_per_h
    if mmh is not None and rate is not None:
        items["maintenance_labour"] = mmh * rate
    elif mmh is not None or rate is not None:
        unassessed.append("maintenance_mmh_per_fh / maintenance_rate_per_h")
    elif x.profile == "full":
        unassessed.append("maintenance_mmh_per_fh / maintenance_rate_per_h")

    if x.maintenance_parts_per_fh:
        items["maintenance_parts"] = x.maintenance_parts_per_fh

    if x.engine_overhaul_cost:
        if not x.engine_tbo_h:
            unassessed.append("engine_tbo_h")
        else:
            items["engine_overhaul_reserve"] = x.n_engines * x.engine_overhaul_cost / x.engine_tbo_h

    if x.depreciation_years:
        items["depreciation"] = (
            x.unit_price * (1 - x.residual_fraction) / (x.depreciation_years * x.flight_hours_per_year)
        )
    elif x.profile == "full":
        unassessed.append("depreciation_years")

    if x.insurance_rate_per_year:
        items["insurance"] = x.insurance_rate_per_year * x.unit_price / x.flight_hours_per_year
    if x.attrition_per_fh:
        items["attrition"] = x.attrition_per_fh * x.unit_price
    if x.crew_cost_per_fh:
        items["crew"] = x.crew_cost_per_fh

    tot = sum(items.values())
    if unassessed:
        status = "partial" if items else "unassessed"
    else:
        status = "ok"

    # BC alias: missing_inputs == unassessed_terms (activated incomplete + full-profile gaps)
    return {
        "status": status,
        "per_flight_hour": tot if status == "ok" else None,
        "assessed_sum_per_fh": tot,
        "per_year": (tot * x.flight_hours_per_year) if status == "ok" else None,
        "items_per_fh": items,
        "unassessed_terms": unassessed,
        "missing_inputs": list(unassessed),
        "sources": x.sources,
        "profile": x.profile,
        "unit_price": x.unit_price,
        "flight_hours_per_year": x.flight_hours_per_year,
        "method": (
            "DOC element sum (Raymer 2018 Ch. 18 structure); rates are dated inputs; "
            "unit_price may be Eastlake/DAPCA CER (Gudmundsson 2014 Ch. 2 / Raymer 2018 Ch. 18)"
        ),
        "note": (
            None if status == "ok" else
            "unassessed≠zero: assessed_sum_per_fh omits incomplete terms — do not treat as full DOC"
        ),
    }


def operational_cost_from_dict(data: dict, *, unit_price_override: float | None = None) -> dict:
    """Build :class:`OperatingInputs` from a dict; optional Eastlake/DAPCA CER fills ``unit_price``.

    Recognized keys beyond :class:`OperatingInputs` fields:
      * ``eastlake``: dict of :class:`EastlakeInputs` kwargs → ``unit_price`` from modified Eastlake
        (Gudmundsson 2014 Ch. 2).
      * ``dapca`` / ``dapca4``: dict of :class:`DapcaInputs` kwargs → ``unit_price`` from DAPCA IV.
      * ``unit_price_from``: ``"eastlake"`` | ``"dapca4"`` | ``"override"`` (explicit ``unit_price`` /
        override). Default: use ``unit_price`` if given, else first CER block present.

    Does **not** invent vendor quotes or an L2 BOM (HANDOFF MÉDIA §5 remains blocked).
    """
    d = dict(data)
    eastlake_kw = d.pop("eastlake", None)
    dapca_kw = d.pop("dapca", None) or d.pop("dapca4", None)
    unit_from = d.pop("unit_price_from", None)
    notes: list[str] = []
    unit = unit_price_override
    cer_block = None

    def _eastlake_price(kw: dict) -> float:
        ei = EastlakeInputs(**kw)
        return float(eastlake_unit_cost(ei).unit_cost)

    def _dapca_price(kw: dict) -> float:
        return float(dapca4(DapcaInputs(**kw))["unit_cost"])

    if unit is None:
        if unit_from == "eastlake" or (unit_from is None and eastlake_kw and "unit_price" not in d):
            if not eastlake_kw:
                raise ValueError("unit_price_from=eastlake requires an eastlake: block")
            unit = _eastlake_price(eastlake_kw)
            cer_block = {"method": "modified Eastlake (Gudmundsson 2014 Ch. 2)", "unit_cost": unit}
            notes.append("unit_price ← Eastlake CER (Gudmundsson 2014 Ch. 2)")
        elif unit_from == "dapca4" or (unit_from is None and dapca_kw and "unit_price" not in d
                                        and not eastlake_kw):
            if not dapca_kw:
                raise ValueError("unit_price_from=dapca4 requires a dapca/dapca4: block")
            unit = _dapca_price(dapca_kw)
            cer_block = {"method": "DAPCA IV (Raymer 2018 Ch. 18)", "unit_cost": unit}
            notes.append("unit_price ← DAPCA IV CER (Raymer 2018 Ch. 18)")
        elif "unit_price" in d:
            unit = float(d["unit_price"])
        else:
            raise ValueError(
                "unit_price required (explicit, unit_price_override, or eastlake/dapca CER block)"
            )
    else:
        notes.append("unit_price ← override (e.g. sized Eastlake from morph evaluate)")

    d["unit_price"] = float(unit)
    # drop unknown keys that are documentation-only
    for k in ("reference", "notes", "label"):
        d.pop(k, None)
    known = {f.name for f in fields(OperatingInputs)}
    extra = set(d) - known
    if extra:
        raise ValueError(f"unknown operating-cost keys: {sorted(extra)}")
    out = operating_cost(OperatingInputs(**d))
    out["notes"] = notes
    if cer_block:
        out["acquisition_cer"] = cer_block
    return out
