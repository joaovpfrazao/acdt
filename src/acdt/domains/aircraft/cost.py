"""Unit production cost — modified Eastlake model for GA aircraft.

Source: Gudmundsson, S. (2014). *General Aviation Aircraft Design: Applied Methods and Procedures*, Elsevier,
Ch. 2 ("Aircraft Cost Analysis"), modified Eastlake (1986) cost-estimating relationships (eqs. 2.2-2.13).
Units: W_airframe [lb] (structural airframe weight: empty weight minus engine, avionics, seats, furnishings,
controls ...), V_H [KTAS], N = units produced over 5 years, costs in 2012 USD x CPI factor.

* Labour costs are ``2.0969 · H · R · CPI`` (2.0969 escalates the Eastlake 1986 hours-rate basis to 2012),
  with Gudmundsson's 2012 rates R_ENG 92, R_TOOL 61, R_MFG 53 USD/h.
* Composite fraction ``f_comp``: F_COMP = 1 + f_comp (engineering, tooling), 1 + 0.25 f_comp (manufacturing),
  1 + 0.5 f_comp (development support, quality control) — Gudmundsson Sec. 2.2.2 (the manufacturing factor is
  cross-checked in the RWTH eVTOL cost model that re-uses it).
* Engine: piston C = 174 N P_BHP CPI (2012 USD); propeller: fixed pitch 3145 N CPI, constant speed
  209.66 N CPI D^2 (P_SHP/D)^0.12 (D in ft).

Validity: GA aircraft (piston/turboprop, Part 23 / CS-23). Out of its database for small UAS: use the bottom-up
part cost (:mod:`acdt.domains.aircraft.manufacturing`) there. The coefficients are those of the cited book;
check them against your copy before relying on absolute values.
"""
from __future__ import annotations

from dataclasses import dataclass, field

LB = 0.45359237
CPI_1986_TO_2012 = 2.0969  # Gudmundsson (2014) eqs. 2.5-2.7


@dataclass
class EastlakeInputs:
    W_airframe_kg: float
    V_H_kt: float
    N: int = 500  # units produced over 5 years
    Q_m: float = 10.0  # production rate per month
    N_P: int = 2  # prototypes
    rate_eng: float = 92.0  # USD/h (2012, Gudmundsson Sec. 2.2.2)
    rate_tool: float = 61.0
    rate_mfg: float = 53.0
    cpi: float = 1.0  # CPI relative to 2012 (see manufacturing.refdata.cpi_factor)
    F_CERT: float = 1.0  # 1 = 14 CFR Part 23 (LSA factors per CER: see Gudmundsson Sec. 2.2.2)
    F_CF: float = 1.03  # complex flap; 1.0 simple
    F_COMP: float = 1.0  # legacy single factor (= 1 + f_comp); prefer f_comp
    F_PRESS: float = 1.0  # pressurised: 1.03
    F_TAPER: float = 1.0  # 0.95 untapered wing
    engine_cost: float = 0.0  # per aircraft (USD, already escalated); piston: piston_engine_cost()
    avionics_cost: float = 15000.0  # per aircraft (USD of the run year; Gudmundsson default 15000 USD 2012)
    propeller_cost: float = 0.0  # per aircraft (USD, already escalated); see propeller_cost()
    f_comp: float | None = None  # composite fraction of the airframe (0..1)
    extra_unit_cost: float = 0.0  # per aircraft (USD, already escalated): e.g. flap actuators (Phase 9 options)
    liability_fraction: float = 0.0  # product liability as a fraction of unit cost (user input; not in the CERs)


@dataclass
class CostBreakdown:
    engineering: float
    tooling: float
    manufacturing: float
    dev_support: float
    flight_test: float
    quality: float
    materials: float
    per_unit_variable: float
    unit_cost: float
    hours: dict = field(default_factory=dict)
    fixed: float = 0.0           # non-recurring: engineering + dev support + flight test + tooling
    variable_per_unit: float = 0.0  # recurring per aircraft (mfg + QC + materials)/N + engine + prop + avionics

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("engineering", "tooling", "manufacturing", "dev_support",
                                              "flight_test", "quality", "materials", "per_unit_variable",
                                              "unit_cost", "fixed", "variable_per_unit")} | {"hours": self.hours}


def piston_engine_cost(P_bhp: float, n_engines: int = 1, cpi: float = 1.0) -> float:
    """Gudmundsson (2014) Sec. 2.2: C_PP = 174 N_PP P_BHP CPI (2012 USD)."""
    return 174.0 * n_engines * P_bhp * cpi


def propeller_cost(kind: str = "fixed", n: int = 1, cpi: float = 1.0, D_ft: float | None = None,
                   P_shp: float | None = None) -> float:
    """Gudmundsson (2014) Sec. 2.2: fixed pitch C = 3145 N CPI; constant speed C = 209.66 N CPI D^2 (P/D)^0.12."""
    if kind == "fixed":
        return 3145.0 * n * cpi
    if D_ft is None or P_shp is None:
        raise ValueError("constant-speed propeller cost needs D_ft and P_shp")
    return 209.66 * n * cpi * D_ft**2 * (P_shp / D_ft) ** 0.12


def _fcomp(x: EastlakeInputs) -> dict:
    f = x.f_comp if x.f_comp is not None else max(x.F_COMP - 1.0, 0.0)
    return {"eng": 1 + f, "tool": 1 + f, "mfg": 1 + 0.25 * f, "dev": 1 + 0.5 * f, "qc": 1 + 0.5 * f}


def eastlake_unit_cost(x: EastlakeInputs) -> CostBreakdown:
    """Modified Eastlake model (Gudmundsson 2014 eqs. 2.2-2.13): hours, fixed and variable costs, unit cost.

    unit cost = (C_ENG + C_DEV + C_FT + C_TOOL + C_MFG + C_QC + C_MAT)/N + engine + propeller + avionics,
    then x (1 + liability_fraction)."""
    W = x.W_airframe_kg / LB
    V, N = x.V_H_kt, x.N
    fc = _fcomp(x)
    H_eng = 0.0396 * W**0.791 * V**1.526 * N**0.183 * x.F_CERT * x.F_CF * fc["eng"] * x.F_PRESS
    H_tool = 1.0032 * W**0.764 * V**0.899 * N**0.178 * x.Q_m**0.066 * x.F_TAPER * x.F_CF * fc["tool"] * x.F_PRESS
    H_mfg = 9.6613 * W**0.74 * V**0.543 * N**0.524 * x.F_CERT * x.F_CF * fc["mfg"]
    k = CPI_1986_TO_2012 * x.cpi
    C_eng = k * H_eng * x.rate_eng
    C_tool = k * H_tool * x.rate_tool
    C_mfg = k * H_mfg * x.rate_mfg
    C_dev = 0.06458 * W**0.873 * V**1.89 * x.N_P**0.346 * x.cpi * x.F_CERT * x.F_CF * fc["dev"] * x.F_PRESS
    C_ft = 0.009646 * W**1.16 * V**1.3718 * x.N_P**1.281 * x.cpi * x.F_CERT
    C_qc = 0.13 * C_mfg * x.F_CERT * fc["qc"]
    C_mat = 24.896 * W**0.689 * V**0.624 * N**0.792 * x.cpi * x.F_CERT * x.F_CF * x.F_PRESS
    var = x.engine_cost + x.avionics_cost + x.propeller_cost + x.extra_unit_cost
    fixed = C_eng + C_dev + C_ft + C_tool
    recurring = C_mfg + C_qc + C_mat
    unit = (fixed + recurring) / N + var
    unit *= 1.0 + x.liability_fraction
    return CostBreakdown(C_eng, C_tool, C_mfg, C_dev, C_ft, C_qc, C_mat, var, unit,
                         hours={"engineering": H_eng, "tooling": H_tool, "manufacturing": H_mfg,
                                "manufacturing_per_unit": H_mfg / N},
                         fixed=fixed, variable_per_unit=recurring / N + var)
