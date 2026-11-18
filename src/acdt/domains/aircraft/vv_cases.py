"""Casos V&V do domínio aircraft (``acdt vv``; docs/VV.md): aerodinâmica, cargas regulamentares, dimensionamento.

Só valores com citação completa; tolerâncias declaradas aqui com a justificação. Os casos C172 são **validação**
(modelo conceptual contra o avião real); os restantes são verificação contra soluções fechadas ou o texto da norma.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping

import numpy as np

from acdt.core.vv import Reference, builder

ANDERSON = ("Anderson, Fundamentals of Aerodynamics, 5.ª ed., McGraw-Hill 2011, §5.3.1 — linha sustentadora de "
            "Prandtl, asa elíptica sem torção: e = 1, C_Di = C_L²/(π AR), a = a0/(1 + a0/(π AR))")
_aero = builder("aerodinamica")


@_aero("AERO-LL-ELLIPTIC", "Linha sustentadora: asa elíptica",
       "Asa elíptica b = 10 m, c0 = 1 m (AR = 12,73), a0 = 2π, sem torção, C_L = 0,5; `LiftingLine` (20 estações) "
       "do caixão de asa. Arrasto induzido e declive de sustentação contra Prandtl.", "verificacao",
       [Reference("CDi_over_CL2_piAR", 1.0, "", ANDERSON, tol_rel=1e-3,
                  tol_source="20 estações: ±0,1 % (teste existente)"),
        Reference("a_over_prandtl", 1.0, "", ANDERSON, tol_rel=2e-3, tol_source="20 estações: ±0,2 % (teste "
                  "existente)")],
       tests=("tests/test_wingbox.py::test_lifting_line_elliptic",))
def _ll() -> Mapping[str, float | None]:
    from acdt.domains.aircraft.wingbox.aero import LiftingLine

    b, c0 = 10.0, 1.0
    ll = LiftingLine(b, lambda y: c0 * np.sqrt(np.clip(1 - (2 * np.asarray(y) / b) ** 2, 1e-12, None)), 20)
    a0 = 2 * math.pi * np.ones(ll.n)
    al, _A, CL, CDi, _ = ll.trim(0.5, np.zeros(ll.n), a0, np.zeros(ll.n))  # type: ignore[no-untyped-call]
    return {"CDi_over_CL2_piAR": float(CDi / (CL ** 2 / (math.pi * ll.AR))),
            "a_over_prandtl": float((CL / al) / (2 * math.pi / (1 + 2 / ll.AR)))}


CFR337 = ("14 CFR 23.337(a)(1) (texto até à Amdt. 23-63) / CS-23.337(a)(1): n ≥ 2,1 + 24 000/(W + 10 000), W em "
          "lb, não sendo preciso exceder 3,8 (normal); 4,4 (utility) e 6,0 (aerobatic) por 23.337(a)(2)–(3)")
_reg = builder("cargas")


@_reg("REG-23337-N", "Fator de carga de manobra mínimo (14 CFR/CS 23.337)",
      "Fator de carga positivo mínimo de projeto para W = 1157 kg (normal, cortado a 3,8), 5000 kg (normal, "
      "fórmula), 1000 kg utility e aerobatic.", "verificacao",
      [Reference("n_normal_1157kg", 3.8, "", CFR337, tol_abs=1e-9, tol_source="texto da norma (exato)"),
       Reference("n_normal_5000kg", 2.1 + 24000 / (5000 / 0.45359237 + 10000), "", CFR337, tol_abs=1e-9,
                 tol_source="texto da norma (exato; 1 lb = 0,45359237 kg)"),
       Reference("n_utility", 4.4, "", CFR337, tol_abs=1e-9, tol_source="texto da norma (exato)"),
       Reference("n_aerobatic", 6.0, "", CFR337, tol_abs=1e-9, tol_source="texto da norma (exato)")],
      tests=("tests/test_phase2.py::test_manoeuvre_load_factors_clauses",))
def _n337() -> Mapping[str, float | None]:
    from acdt.domains.aircraft.structures import regulation_min_n

    return {"n_normal_1157kg": regulation_min_n(1157, "normal", "cs_23"),
            "n_normal_5000kg": regulation_min_n(5000, "normal", "cs_23"),
            "n_utility": regulation_min_n(1000, "utility", "cs_23"),
            "n_aerobatic": regulation_min_n(1000, "aerobatic", "cs_23")}


C172S = ("Cessna Aircraft Company, Model 172S Skyhawk SP Information Manual (1998), Secção 1: MTOW 2550 lb = 1157 kg, "
         "peso vazio padrão 1663 lb = 754 kg, 180 hp = 134 kW, S = 174 ft² = 16,2 m², W/S = 71,4 kg/m²")
_TOL_W = "métodos conceptuais (Raymer Cap. 15, montagem por componentes): ±15 % declarado no teste existente"
_TOL_C = "dimensionamento conceptual: ±25 % declarado no teste existente"
_siz = builder("dimensionamento")
_C172_RESULT: dict[str, float | None] = {}


def _c172() -> dict[str, float | None]:
    if not _C172_RESULT:
        from acdt import G0
        from acdt.domains.aircraft.mission import MissionSpec
        from acdt.domains.aircraft.sizing import run

        ex = Path(__file__).resolve().parents[4] / "examples" / "cessna172_check.yaml"
        if not ex.is_file():
            from acdt.core.vv import NotAssessed
            raise NotAssessed(f"exemplo em falta: {ex}")
        r = run(MissionSpec.from_yaml(ex))
        _C172_RESULT.update(W0=r.sizing.W0, We=r.sizing.We,
                            P_sl_kW=None if r.power_sl is None else float(r.power_sl) / 1e3, S=r.S,
                            WS=r.design_point.ws / G0)
    return dict(_C172_RESULT)


@_siz("SIZ-C172S", "Cessna 172S: dimensionamento conceptual contra o avião real",
      "Missão `examples/cessna172_check.yaml` (requisitos do C172S) pelo dimensionamento L0/L1 (`acdt size`, "
      "sem sistemas): MTOW, peso vazio, potência ao nível do mar, área alar e carga alar.", "validacao",
      [Reference("W0", 1157.0, "kg", C172S, tol_rel=0.15, tol_source=_TOL_W),
       Reference("We", 754.0, "kg", C172S, tol_rel=0.15, tol_source=_TOL_W),
       Reference("P_sl_kW", 134.0, "kW", C172S, tol_rel=0.25, tol_source=_TOL_C),
       Reference("S", 16.2, "m²", C172S, tol_rel=0.25, tol_source=_TOL_C),
       Reference("WS", 71.4, "kg/m²", C172S, tol_rel=0.25, tol_source=_TOL_C)],
      cost="medio", tests=("tests/test_sizing_c172.py",),
      notes="Validação de nível conceptual: as bandas largas são as do método, não do código.")
def _c172_case() -> Mapping[str, float | None]:
    return _c172()
