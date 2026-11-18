"""Casos V&V do núcleo (domínio-agnósticos): atmosfera, sensibilidade, MDO, estruturas (FEM/viga), EM (PO).

Valores de referência só com citação completa; tolerâncias declaradas aqui (a priori), com a sua justificação.
Os casos embrulham verificações que já existiam como testes (``tests``) e passam a produzir um relatório versionado.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np

from .vv import NotAssessed, Reference, builder

# ------------------------------------------------------------------------------------------------ atmosfera
ISO2533 = ("ISO 2533:1975 Standard Atmosphere (= ICAO Doc 7488/3, 1993); NOAA/NASA/USAF, U.S. Standard "
           "Atmosphere 1976, NOAA-S/T 76-1562, Tab. I (altitude geopotencial)")
_atm = builder("atmosfera")


@_atm("ATM-ISA-SL", "ISA ao nível do mar",
      "Atmosfera padrão a H = 0: temperatura, pressão, massa volúmica, velocidade do som e viscosidade dinâmica "
      "(Sutherland) definidas pela norma.", "verificacao",
      [Reference("T", 288.15, "K", ISO2533, tol_abs=1e-6, tol_source="valor definidor (exato)"),
       Reference("p", 101325.0, "Pa", ISO2533, tol_abs=1e-3, tol_source="valor definidor (exato)"),
       Reference("rho", 1.225, "kg/m³", ISO2533, tol_rel=1e-4, tol_source="valor tabelado com 4 algarismos"),
       Reference("a", 340.294, "m/s", ISO2533, tol_rel=1e-5, tol_source="valor tabelado com 6 algarismos"),
       Reference("mu", 1.7894e-5, "Pa·s", ISO2533, tol_rel=1e-4, tol_source="valor tabelado com 5 algarismos")],
      tests=("tests/test_atmosphere_units.py::test_isa_sea_level",))
def _isa_sl() -> Mapping[str, float | None]:
    from acdt.core.atmosphere import isa

    s = isa(0.0)
    return {"T": s.T, "p": s.p, "rho": s.rho, "a": s.a, "mu": s.mu}


@_atm("ATM-ISA-11KM", "ISA na tropopausa (H = 11 km)",
      "Base da 1.ª camada isotérmica, H = 11 000 m geopotenciais: T = T0 − 6,5 K/km·H, p e ρ pela integração "
      "hidrostática.", "verificacao",
      [Reference("T", 216.65, "K", ISO2533, tol_abs=1e-6, tol_source="valor definidor (exato)"),
       Reference("p", 22632.1, "Pa", ISO2533, tol_rel=1e-5, tol_source="pressão de base da camada b = 1 (6 algarismos)"),
       Reference("rho", 0.36392, "kg/m³", ISO2533 + "; ρ = P·M0/(R*·T), M0 = 28,9644 kg/kmol, R* = 8314,32 J/(kmol·K)", tol_rel=5e-5, tol_source="5 algarismos")],
      tests=("tests/test_atmosphere_units.py::test_isa_11km_and_stratosphere",))
def _isa_11() -> Mapping[str, float | None]:
    from acdt.core.atmosphere import isa

    s = isa(11000.0)
    return {"T": s.T, "p": s.p, "rho": s.rho}


@_atm("ATM-ISA-20KM", "ISA na base da 2.ª camada (H = 20 km)",
      "H = 20 000 m geopotenciais (fim da camada isotérmica de 216,65 K).", "verificacao",
      [Reference("T", 216.65, "K", ISO2533, tol_abs=1e-6, tol_source="valor definidor (exato)"),
       Reference("p", 5474.89, "Pa", ISO2533, tol_rel=1e-5, tol_source="pressão de base da camada b = 2 (6 algarismos)"),
       Reference("rho", 0.088035, "kg/m³", ISO2533 + "; ρ = P·M0/(R*·T), M0 = 28,9644 kg/kmol, R* = 8314,32 J/(kmol·K)", tol_rel=5e-5, tol_source="5 algarismos")])
def _isa_20() -> Mapping[str, float | None]:
    from acdt.core.atmosphere import isa

    s = isa(20000.0)
    return {"T": s.T, "p": s.p, "rho": s.rho}


# ------------------------------------------------------------------------------------------------ sensibilidade
ISHIGAMI = ("Ishigami & Homma, Proc. ISUMA '90 (1990) 398–403 (função); Homma & Saltelli, Reliab. Eng. Syst. Saf. "
            "52 (1996) 1–17 (índices analíticos, a = 7, b = 0,1); Saltelli et al., Global Sensitivity Analysis: "
            "The Primer, Wiley 2008, §4.6 (S1 = 0,3139, 0,4424, 0; ST = 0,5576, 0,4424, 0,2437)")
_TOL_SOBOL = ("Monte Carlo N = 8192 (custo N(k+2) = 40 960): ±0,03 absoluto ≈ 3 erros-padrão de bootstrap "
              "observados para este N (PRESSUPOSTO declarado)")
_sa = builder("sensibilidade")


def _ish_exact() -> dict[str, float]:
    a, b = 7.0, 0.1
    V = a * a / 8 + b * math.pi ** 4 / 5 + b * b * math.pi ** 8 / 18 + 0.5
    V1 = 0.5 * (1 + b * math.pi ** 4 / 5) ** 2
    V2 = a * a / 8
    V13 = 8 * b * b * math.pi ** 8 / 225
    return {"S1_x1": V1 / V, "S1_x2": V2 / V, "S1_x3": 0.0, "ST_x1": (V1 + V13) / V, "ST_x2": V2 / V,
            "ST_x3": V13 / V}


_IE = _ish_exact()


@_sa("SA-SOBOL-ISHIGAMI", "Índices de Sobol' da função de Ishigami",
     "Y = sin x1 + a sin² x2 + b x3⁴ sin x1, xi ~ U(−π, π), a = 7, b = 0,1; índices de 1.ª ordem e totais pelo "
     "desenho de Saltelli e pelos estimadores de `acdt uq` (Saltelli 2010 / Jansen 1999, saídas centradas).",
     "verificacao",
     [Reference(k, round(v, 4), "", ISHIGAMI, tol_abs=0.03, tol_source=_TOL_SOBOL) for k, v in _IE.items()],
     tests=("tests/test_uq.py::test_sobol_ishigami_analytic",
            "tests/test_sensitivity_sobol.py::test_ishigami_sobol_matches_analytic"))
def _sobol_ishigami() -> Mapping[str, float | None]:
    from acdt.core.sensitivity import distributions as D
    from acdt.core.sensitivity import gsa
    from acdt.core.sensitivity.sobol import ishigami

    ins = [D.parse_input({"path": f"x{i}", "dist": "uniform", "low": -math.pi, "high": math.pi,
                          "source": "Ishigami & Homma 1990"}) for i in (1, 2, 3)]

    def f(pts: Any) -> list[Mapping[str, float] | None]:
        return [{"Y": ishigami(p["x1"], p["x2"], p["x3"])} for p in pts]

    r = gsa.sobol(ins, f, ["Y"], n=8192, seed=11)["metrics"]["Y"]
    out: dict[str, float | None] = {}
    for x in r["indices"]:
        v = x["variable"]
        out[f"S1_{v}"] = x["S1"]
        out[f"ST_{v}"] = x["ST"]
    return out


# ------------------------------------------------------------------------------------------------ MDO
SELLAR = ("Sellar, Batill & Renaud, Response surface based, concurrent subspace optimization for multidisciplinary "
          "system design, AIAA 96-0714 (1996); ótimo MDF f* = 3,18339395, z* = (1,97763888, 0), x* = 0 como "
          "publicado na documentação do OpenMDAO (Sellar MDF)")
ZDT = ("Zitzler, Deb & Thiele, Comparison of multiobjective evolutionary algorithms: empirical results, Evol. "
       "Comput. 8(2) (2000) 173–195 — ZDT1, frente verdadeira f2 = 1 − √f1, f1 ∈ [0, 1]; hipervolume ao ponto "
       "(1,1; 1,1) = 0,1 + 2/3 + 0,11 = 0,87667 (integração analítica da frente publicada)")
_mdo = builder("mdo")


@_mdo("MDO-SELLAR", "Problema de Sellar (MDF, SLSQP)",
      "min x² + z2 + y1 + e^(−y2) com y1 = z1² + z2 + x − 0,2 y2, y2 = √y1 + z1 + z2 (MDA acoplado), "
      "y1 ≥ 3,16 e y2 ≤ 24 como requisitos do registo; `acdt mdo` estratégia slsqp.", "verificacao",
      [Reference("f", 3.18339395, "", SELLAR, tol_abs=2e-4, tol_source="tolerância do otimizador (tol 1e-9, FD "
                 "1e-6) no teste existente"),
       Reference("z1", 1.97763888, "", SELLAR, tol_abs=5e-3, tol_source="idem"),
       Reference("z2", 0.0, "", SELLAR, tol_abs=5e-3, tol_source="idem"),
       Reference("x", 0.0, "", SELLAR, tol_abs=5e-3, tol_source="idem")],
      requires=("py:openmdao",), tests=("tests/test_mdo_system.py::test_sellar_slsqp_published_optimum",))
def _sellar() -> Mapping[str, float | None]:
    from acdt.core.sysmdo import parse_spec, run_mdo
    from acdt.core.sysmdo.toy import FunctionModel, sellar

    reqs = [{"id": "SEL-G1", "metric": "y1", "comparison": "min", "threshold": 3.16},
            {"id": "SEL-G2", "metric": "y2", "comparison": "max", "threshold": 24.0}]
    spec = parse_spec({"design_variables": [
        {"path": "x", "lower": 0, "upper": 10, "x0": 1, "source": "Sellar et al. 1996"},
        {"path": "z1", "lower": -10, "upper": 10, "x0": 5, "source": "Sellar et al. 1996"},
        {"path": "z2", "lower": 0, "upper": 10, "x0": 2, "source": "Sellar et al. 1996"}],
        "objectives": [{"metric": "obj", "sense": "min"}], "strategy": "slsqp",
        "options": {"maxiter": 100, "tol": 1e-9, "fd_step": 1e-6}, "constraints": {"policy": "limiar"}})
    r = run_mdo(spec, FunctionModel(sellar, {}, reqs, "Sellar"), log=lambda s: None)
    if r["best"].get("obj") is None:
        return {"f": None, "z1": None, "z2": None, "x": None}
    b = r["evaluations"][r["best"]["obj"]]
    return {"f": b["objectives"]["obj"], "z1": b["x"]["z1"], "z2": b["x"]["z2"], "x": b["x"]["x"]}


@_mdo("MDO-ZDT1", "Frente de Pareto ZDT1 (NSGA-II)",
      "ZDT1 com n = 5 variáveis em [0, 1]; `acdt mdo` estratégia nsga2 (população 40, 60 gerações, semente 3). "
      "Hipervolume da frente obtida ao ponto (1,1; 1,1) e mediana da distância vertical à frente verdadeira.",
      "verificacao",
      [Reference("hipervolume", 0.87667, "", ZDT, tol_abs=0.02667, tol_source="aceita ≥ 0,85 (≈ 97 % do ótimo) com "
                 "o orçamento de 2400 avaliações — banda do teste existente", kind="min"),
       Reference("mediana_gap", 0.0, "", ZDT, tol_abs=0.02, tol_source="banda do teste existente", kind="max")],
      requires=("py:openmdao",), tests=("tests/test_mdo_system.py::test_zdt1_nsga2_front",))
def _zdt1() -> Mapping[str, float | None]:
    from acdt.core.sysmdo import hypervolume_2d, parse_spec, run_mdo
    from acdt.core.sysmdo.toy import FunctionModel, zdt1

    n = 5
    spec = parse_spec({"design_variables": [{"path": f"x{i}", "lower": 0, "upper": 1, "x0": 0.5, "source": "ZDT1"}
                                            for i in range(1, n + 1)],
                       "objectives": ["f1", "f2"], "strategy": "nsga2",
                       "options": {"pop_size": 40, "max_gen": 60, "seed": 3}})
    r = run_mdo(spec, FunctionModel(zdt1, {"n": n}, [], "ZDT1"), log=lambda s: None)
    ev = {e["id"]: e for e in r["evaluations"]}
    F = np.array([[ev[i]["objectives"]["f1"], ev[i]["objectives"]["f2"]] for i in r["pareto"]])
    if F.size == 0:
        return {"hipervolume": None, "mediana_gap": None}
    gap = F[:, 1] - (1.0 - np.sqrt(F[:, 0]))
    return {"hipervolume": float(hypervolume_2d(F, (1.1, 1.1))), "mediana_gap": float(np.median(gap))}


# ------------------------------------------------------------------------------------------------ estruturas
TIMO_MM = "Timoshenko & Gere, Mechanics of Materials, 4.ª ed., PWS 1997 — consola com carga na ponta, δ = PL³/(3EI)"
TIMO_ES = ("Timoshenko & Gere, Theory of Elastic Stability, 2.ª ed., McGraw-Hill 1961, §9.2 — placa simplesmente "
           "apoiada em compressão uniaxial, N_cr = kπ²D/b², k = 4 para a/b = 1")
SP8007 = ("NASA SP-8007, Buckling of Thin-Walled Circular Cylinders (1965, rev. 1968): γ = 1 − 0,901(1 − e^(−φ)), "
          "φ = √(R/t)/16; R/t = 100 → φ = 0,625, γ = 1 − 0,901·(1 − e^(−0,625)) = 0,5813")
_st = builder("estruturas")
_E, _NU = 70e9, 0.3


def _plate(L: float, b: float, nx: int, ny: int, t: float) -> tuple[Any, dict[tuple[int, int], int]]:
    from acdt.core.fem.laminate import isotropic
    from acdt.core.fem.model import FEModel

    idx: dict[tuple[int, int], int] = {}
    nodes: list[tuple[float, float, float]] = []
    for i, x in enumerate(np.linspace(0, L, nx + 1)):
        for j, y in enumerate(np.linspace(0, b, ny + 1)):
            idx[i, j] = len(nodes)
            nodes.append((float(x), float(y), 0.0))
    m = FEModel(np.array(nodes))
    s = m.add_section(isotropic(_E, _NU, t, 2700.0))
    m.shells = [(idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1], s, None)
                for i in range(nx) for j in range(ny)]
    return m, idx


_PL = {"L": 1.0, "b": 0.1, "t": 0.01, "P": 100.0}
_DELTA_PLATE = _PL["P"] * _PL["L"] ** 3 / (3 * _E * _PL["b"] * _PL["t"] ** 3 / 12)


@_st("STR-FEM-CANTILEVER", "Consola em cascas: flecha de ponta",
     "Placa 1 × 0,1 × 0,01 m, E = 70 GPa, ν = 0,3, encastrada, P = 100 N na ponta (20 × 2 elementos de casca do "
     "`acdt.core.fem`); flecha de flexão comparada com a teoria de vigas de Euler–Bernoulli.", "verificacao",
     [Reference("w_tip", _DELTA_PLATE, "m", TIMO_MM, tol_rel=0.02, tol_source="malha 20 × 2: ±2 % (teste existente; "
                "efeito de Poisson na placa larga desprezável)")],
     tests=("tests/test_fem_core.py::test_cantilever_plate_bending_and_membrane",))
def _fem_cant() -> Mapping[str, float | None]:
    m, idx = _plate(_PL["L"], _PL["b"], 20, 2, _PL["t"])
    for j in range(3):
        m.fixed[idx[0, j]] = range(6)
        m.loads[idx[20, j]] = [0, 0, _PL["P"] / 3, 0, 0, 0]
    return {"w_tip": float(m.solve_static()["u"][6 * idx[20, 1] + 2])}


_D = _E * 0.01 ** 3 / 12 / (1 - _NU ** 2)


@_st("STR-FEM-PLATE-BUCKLING", "Encurvadura de placa quadrada simplesmente apoiada",
     "Placa 0,5 × 0,5 × 0,01 m, E = 70 GPa, ν = 0,3, apoiada nos 4 bordos, compressão uniaxial; 1.º valor próprio "
     "do problema de encurvadura linear do `acdt.core.fem` (12 × 12 cascas).", "verificacao",
     [Reference("N_cr", 4 * math.pi ** 2 * _D / 0.5 ** 2, "N/m", TIMO_ES, tol_rel=0.02,
                tol_source="malha 12 × 12: ±2 % (teste existente)")],
     tests=("tests/test_fem_core.py::test_ss_plate_buckling_k4",))
def _fem_buck() -> Mapping[str, float | None]:
    a, t, n, Nx = 0.5, 0.01, 12, 1000.0
    m, idx = _plate(a, a, n, n, t)
    for (i, j), k in idx.items():
        m.fixed[k] = ([2] if i in (0, n) or j in (0, n) else []) + [5]
    m.fixed[idx[0, 0]] = [0, 1, 2, 5]
    m.fixed[idx[0, n]] = [0, 2, 5]
    for j in range(n + 1):
        wgt = (0.5 if j in (0, n) else 1) * a / n
        m.loads[idx[n, j]] = [-Nx * wgt, 0, 0, 0, 0, 0]
        m.loads[idx[0, j]] = [Nx * wgt, 0, 0, 0, 0, 0]
    bk = m.buckling(m.solve_static(), 3)
    return {"N_cr": float(bk["lambda"][0] * Nx)}


@_st("STR-BEAM-CANTILEVER", "Viga em consola (integração de M/EI): flecha e rotação de torção",
     "L = 2 m, P = 1 kN na ponta, EI = 10⁶ N·m², GJ = 5·10⁵ N·m², T = 200 N·m; `cantilever_response` "
     "(integração numérica do momento) contra a solução fechada.", "verificacao",
     [Reference("w_tip", 1000.0 * 2.0 ** 3 / (3 * 1.0e6), "m", TIMO_MM, tol_rel=0.005,
                tol_source="401 pontos de integração: ±0,5 % (teste existente)"),
      Reference("theta_tip", 200.0 * 2.0 / 5.0e5, "rad", "Timoshenko & Gere 1997 — torção uniforme, θ = TL/(GJ)",
                tol_rel=0.005, tol_source="idem")],
     tests=("tests/test_structures_l1.py::test_thin_tube_and_cantilever_closed_form",))
def _beam() -> Mapping[str, float | None]:
    from acdt.core.structures.beam import cantilever_response

    L, P, EI, GJ, T = 2.0, 1000.0, 1.0e6, 5.0e5, 200.0
    y = np.linspace(0.0, L, 401)
    r = cantilever_response(y, P * (L - y), np.full_like(y, T), EI, GJ)
    return {"w_tip": float(r["deflection_m"][-1]), "theta_tip": float(r["twist_rad"][-1])}


@_st("STR-SP8007-KNOCKDOWN", "Fator de redução de encurvadura de cilindros (NASA SP-8007)",
     "Fator empírico de projeto γ para cilindros finos em compressão axial, R/t = 100.", "verificacao",
     [Reference("gamma", 0.5813, "", SP8007, tol_abs=1e-4, tol_source="arredondamento a 4 casas do valor da "
                "fórmula publicada")],
     tests=("tests/test_structures_l1.py::test_sp8007_knockdown_and_clamp",))
def _sp8007() -> Mapping[str, float | None]:
    from acdt.core.structures.beam import cylinder_axial_knockdown

    return {"gamma": float(cylinder_axial_knockdown(100.0))}


# ------------------------------------------------------------------------------------------------ EM (RCS)
KNOTT = ("Knott, Shaeffer & Tuley, Radar Cross Section, 2.ª ed., Artech House 1993, Tab. 6.1 (formas canónicas em "
         "ótica física); Balanis, Advanced Engineering Electromagnetics, 2.ª ed., Wiley 2012, §11.3")
_em = builder("em")


_PO_CACHE: list[dict[str, Any]] = []


def _po_case(i: int) -> Mapping[str, float | None]:
    from acdt.core.em import validate

    if not _PO_CACHE:
        _PO_CACHE.extend(validate.cases())
    c = _PO_CACHE[i]
    if c.get("po_dbsm") is None:
        return {"max_abs_delta_db": c["max_abs_delta_db"]}
    return {"sigma_dbsm": c["po_dbsm"]}


def _register_po() -> None:
    """Os casos de ``acdt.core.em.validate`` (valor exato e tolerância já declarados lá) como casos V&V."""
    try:
        from acdt.core.em import validate
        cs = validate.cases()
    except Exception as e:  # noqa: BLE001 — sem numpy/EM: regista um caso que fica nao_avaliado
        msg = f"{type(e).__name__}: {e}"

        @_em("EM-PO-CANONICAL", "Casos canónicos de RCS em ótica física", "Indisponível neste ambiente.",
             "verificacao", [Reference("sigma_dbsm", 0.0, "dBsm", KNOTT, tol_abs=1.0)])
        def _na() -> Mapping[str, float | None]:
            raise NotAssessed(msg)
        return
    for i, c in enumerate(cs):
        word = "".join(ch for ch in c["case"].split()[0].upper() if ch.isalnum())
        cid = f"EM-PO-{i + 1:02d}-{word}"
        if c.get("po_dbsm") is None:
            ref = Reference("max_abs_delta_db", 0.0, "dB", KNOTT, tol_abs=float(c["tol_db"]),
                            tol_source="banda de aceitação de acdt.core.em.validate", kind="max")
        else:
            ref = Reference("sigma_dbsm", float(c["exact_dbsm"]), "dBsm", KNOTT, tol_abs=float(c["tol_db"]),
                            tol_source="banda de aceitação de acdt.core.em.validate (malha/discretização)")

        def ev(i: int = i) -> Mapping[str, float | None]:
            return _po_case(i)
        ev.__qualname__ = f"_po_case[{i}]"
        _em(cid, c["case"], f"RCS por ótica física (`acdt.core.em.po`) a 10 GHz contra a forma fechada: "
                            f"{c['case']}.", "verificacao", [ref],
            tests=("tests/test_phase6_rcs.py::test_canonical_cases_within_tolerance",))(ev)


_register_po()
