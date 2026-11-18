# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Rede térmica de um compartimento (baía): nó do compartimento (ar + equipamento, temperatura única) e nó da pele.

Balanços (regime permanente; Incropera et al. 6.ª ed., Cap. 1 e 3, conservação de energia num volume de controlo):

* pele: q_int + α_s·G_s·A_sol = h_ext·A·(T_s − T_aw) + ε_ext·σ·A·(T_s⁴ − T_∞⁴)
* compartimento: Q_gerado = q_int + ṁ·c_p·(T_b − T_entrada)
* q_int = (T_b − T_s)/R_int, R_int = 1/((h_int + h_rad,int)·A) + 1/(U_parede·A); h_rad,int = εσ(T_b²+T_s²)(T_b+T_s)
  (radiação linearizada entre o equipamento e a parede; Incropera Eq. 1.9).

h_ext: placa plana (Eqs. 7.30/7.38) em voo, convecção natural (Eq. 9.26) parado; h_int: convecção natural
(Eq. 9.26) com a altura do compartimento. T_aw: temperatura de parede adiabática; T_entrada do ar de ventilação =
temperatura total T_∞ + V²/2c_p (PRESSUPOSTO: conduta adiabática, mistura perfeita no compartimento, ar sai a T_b).

Transitório (capacidade concentrada; Incropera §5.3, balanço Eq. 5.15 sem fluxo imposto): C·dT_b/dt = Q(t) −
q_int − ṁc_p(T_b − T_entrada), com a pele quase estacionária (PRESSUPOSTO: capacidade da pele ≪ C).

**Intervalos.** Cada parâmetro desconhecido (emissividades, absortividade solar, área de radiação interna, regime
da camada limite exterior) é resolvido nos dois extremos físicos: o conjunto «quente» dá o limite superior da
temperatura, o «frio» o inferior. Q_gerado desconhecido (máximo ``None``) → limite superior desconhecido.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from .air import CP_AIR, SIGMA_SB, Ambient, ram_temperature
from .convection import adiabatic_wall_T, flat_plate_forced, film_props, vertical_plate_natural


@dataclass
class Bound:
    """Parâmetro com intervalo [lo, hi] e a sua origem. ``lo == hi`` → valor declarado."""

    lo: float
    hi: float
    source: str

    @classmethod
    def of(cls, v: Any, lo_default: float, hi_default: float, what: str) -> "Bound":
        if v is None:
            return cls(lo_default, hi_default, f"{what} desconhecido: gama física [{lo_default:g}, {hi_default:g}]")
        if isinstance(v, (list, tuple)) and len(v) == 2:
            return cls(float(v[0]), float(v[1]), f"{what}: intervalo declarado")
        return cls(float(v), float(v), f"{what}: declarado")


@dataclass
class Bay:
    """Compartimento genérico (fuselagem, nacele, casulo de carga, baía de baterias…)."""

    id: str
    skin_area_m2: float
    flow_length_m: float
    height_m: float
    eps_ext: Bound
    alpha_solar: Bound
    sun_area_m2: float
    eps_int: Bound
    wall_U_W_m2K: float | None = None  # condutância da parede/isolamento; None = pele fina (resistência desprezável)
    capacity_J_K: float | None = None
    vent_m_dot_kg_s: float = 0.0  # ar de ventilação (ram ou ventilador) que atravessa o compartimento
    notes: list[str] = field(default_factory=list)


@dataclass
class Condition:
    """Condição de operação: atmosfera, velocidade, irradiância solar."""

    name: str
    ambient: Ambient
    V_m_s: float
    solar_W_m2: float = 0.0


@dataclass
class BaySolution:
    T_bay_K: float
    T_skin_K: float
    q_skin_W: float
    q_vent_W: float
    h_ext: float
    h_int: float
    T_aw_K: float
    T_in_K: float
    correlations: list[str]
    warnings: list[str]


Corner = tuple[float, float, float, bool]
"""Vértice dos parâmetros incertos: (ε_ext, α_s, ε_int, camada limite turbulenta desde o bordo)."""


def _corner(bay: Bay, hot: "bool | Corner") -> Corner:
    if isinstance(hot, tuple):
        return hot
    if hot:
        return (bay.eps_ext.lo, bay.alpha_solar.hi, bay.eps_int.lo, False)
    return (bay.eps_ext.hi, bay.alpha_solar.lo, bay.eps_int.hi, True)


def corners(bay: Bay, forced: bool = True) -> list[Corner]:
    """Todos os vértices distintos da caixa de parâmetros incertos (ε_ext, α_s, ε_int e, com escoamento,
    transição laminar/mista vs turbulenta desde o bordo).

    PRESSUPOSTO: a temperatura é monótona em cada parâmetro (o sentido pode mudar — p. ex. ε_int aquece o
    compartimento quando a pele está ao sol); os extremos estão então nos vértices."""
    out: list[Corner] = []
    for ee in sorted({bay.eps_ext.lo, bay.eps_ext.hi}):
        for al in sorted({bay.alpha_solar.lo, bay.alpha_solar.hi}):
            for ei in sorted({bay.eps_int.lo, bay.eps_int.hi}):
                for tr in ((False, True) if forced else (False,)):
                    out.append((ee, al, ei, tr))
    return out


def _h_ext(cond: Condition, bay: Bay, T_s: float, hot: "bool | Corner") -> tuple[float, str, list[str], bool]:
    a = cond.ambient
    tripped = _corner(bay, hot)[3]
    if cond.V_m_s > 0.5:
        c = flat_plate_forced(cond.V_m_s, bay.flow_length_m, T_s, a.T_K, a.p_Pa, tripped=tripped)
        turb = tripped or (c.Re or 0.0) > 5e5
        return c.h, c.correlation, c.warnings, turb
    c = vertical_plate_natural(bay.height_m, T_s if abs(T_s - a.T_K) > 1e-3 else a.T_K + 1e-3, a.T_K, a.p_Pa)
    return c.h, c.correlation + " (parado)", c.warnings, False


def _state(bay: Bay, cond: Condition, T_b: float, hot: "bool | Corner") -> dict[str, Any]:
    """Pele em equilíbrio para T_b imposto: devolve T_s, q_int, q_vent, h e correlações."""
    a = cond.ambient
    eps_e, alp, eps_i, _tr = _corner(bay, hot)
    A = bay.skin_area_m2
    T_in = ram_temperature(a.T_K, cond.V_m_s)
    Pr = film_props(a.T_K, a.T_K, a.p_Pa).Pr
    info: dict[str, Any] = {"h_i": 0.0, "corr_i": "convecção natural interna (ΔT≈0)", "w_i": []}

    def q_int(T_s: float) -> float:
        dT = T_b - T_s
        if abs(dT) < 1e-6:
            return 0.0
        c = vertical_plate_natural(bay.height_m, T_b, T_s, a.p_Pa)
        h_r = eps_i * SIGMA_SB * (T_b ** 2 + T_s ** 2) * (T_b + T_s)
        R = 1.0 / ((c.h + h_r) * A)
        if bay.wall_U_W_m2K:
            R += 1.0 / (bay.wall_U_W_m2K * A)
        info.update(h_i=c.h, corr_i=c.correlation, w_i=c.warnings)
        return dT / R

    def res(T_s: float) -> float:
        h_e, corr, w, turb = _h_ext(cond, bay, T_s, hot)
        T_aw = adiabatic_wall_T(a.T_K, cond.V_m_s, Pr, turb)
        info.update(h_e=h_e, corr_e=corr, w_e=w, T_aw=T_aw)
        return q_int(T_s) + alp * cond.solar_W_m2 * bay.sun_area_m2 - h_e * A * (T_s - T_aw) \
            - eps_e * SIGMA_SB * A * (T_s ** 4 - a.T_K ** 4)

    lo, hi = min(T_b, a.T_K) - 80.0, max(T_b, a.T_K) + 600.0
    T_s = float(brentq(res, max(lo, 20.0), hi, xtol=1e-6))
    res(T_s)  # deixa info coerente com a solução
    qi = q_int(T_s)
    return {"T_s": T_s, "q_int": qi, "q_vent": bay.vent_m_dot_kg_s * CP_AIR * (T_b - T_in), "T_in": T_in, **info}


def losses(bay: Bay, cond: Condition, T_b: float, hot: "bool | Corner") -> float:
    """Calor que sai do compartimento à temperatura T_b (pele quase estacionária) [W]."""
    st = _state(bay, cond, T_b, hot)
    return float(st["q_int"] + st["q_vent"])


def solve_bay_steady(bay: Bay, cond: Condition, Q_W: float, *, hot: "bool | Corner") -> BaySolution:
    """Temperaturas de regime permanente do compartimento e da pele para a potência ``Q_W``.

    ``hot=True``: ε_ext mínimo, α_s máximo, ε_int mínimo, camada limite laminar/mista; ``hot=False``: o oposto;
    ou um vértice explícito (``Corner``). Para limites rigorosos use :func:`solve_bay_bounds`."""
    a = cond.ambient
    T_in = ram_temperature(a.T_K, cond.V_m_s)

    def f(T_b: float) -> float:
        return Q_W - losses(bay, cond, T_b, hot)

    lo = min(a.T_K, T_in) - 60.0
    hi = max(a.T_K, T_in) + 60.0
    while f(hi) > 0 and hi < 3000.0:
        hi += 200.0
    while f(lo) < 0 and lo > 40.0:
        lo = max(lo - 40.0, 30.0)
    T_b = float(brentq(f, lo, hi, xtol=1e-5))
    st = _state(bay, cond, T_b, hot)
    return BaySolution(T_b, float(st["T_s"]), float(st["q_int"]), float(st["q_vent"]), float(st["h_e"]),
                       float(st["h_i"]), float(st["T_aw"]), float(st["T_in"]),
                       [str(st["corr_e"]), str(st["corr_i"])], list(st["w_e"]) + list(st["w_i"]))


def solve_bay_bounds(bay: Bay, cond: Condition, Q_lo: float, Q_hi: float | None
                     ) -> tuple[BaySolution, BaySolution | None]:
    """Minorante (com ``Q_lo``) e majorante (com ``Q_hi``; ``None`` = desconhecido) da temperatura do
    compartimento: mínimo/máximo sobre todos os vértices de :func:`corners`."""
    cs = corners(bay, cond.V_m_s > 0.5)
    lo = min((solve_bay_steady(bay, cond, Q_lo, hot=c) for c in cs), key=lambda s: s.T_bay_K)
    hi = None if Q_hi is None else max((solve_bay_steady(bay, cond, Q_hi, hot=c) for c in cs),
                                       key=lambda s: s.T_bay_K)
    return lo, hi


@dataclass
class Phase:
    """Fase do perfil para o transitório: condição, duração e potência gerada (função do tempo na fase)."""

    condition: Condition
    duration_s: float
    Q_W: float | Callable[[float], float]
    vent_m_dot_kg_s: float | None = None


def solve_bay_transient(bay: Bay, phases: Sequence[Phase], T0_K: float, *, hot: "bool | Corner", n_out: int = 40
                        ) -> dict[str, Any]:
    """Integra C·dT_b/dt ao longo das fases (RK45, scipy). Precisa de ``bay.capacity_J_K``."""
    if not bay.capacity_J_K or bay.capacity_J_K <= 0:
        raise ValueError(f"compartimento '{bay.id}' sem capacidade térmica (capacity_J_K): transitório desconhecido")
    C = float(bay.capacity_J_K)
    t_all: list[float] = []
    T_all: list[float] = []
    names: list[str] = []
    T = float(T0_K)
    t0 = 0.0
    for ph in phases:
        if ph.duration_s <= 0:
            continue
        b = Bay(**{**bay.__dict__, "vent_m_dot_kg_s": bay.vent_m_dot_kg_s if ph.vent_m_dot_kg_s is None
                   else ph.vent_m_dot_kg_s})
        Qf = ph.Q_W

        def rhs(t: float, y: Any, b: Bay = b, ph: Phase = ph, Qf: Any = Qf) -> list[float]:
            Tb = float(y[0])
            q = float(Qf(t)) if callable(Qf) else float(Qf)
            ss = losses(b, ph.condition, Tb, hot)
            return [(q - ss) / C]

        sol = solve_ivp(rhs, (0.0, ph.duration_s), [T], method="RK45", max_step=max(ph.duration_s / 50.0, 1.0),
                        t_eval=[ph.duration_s * i / n_out for i in range(n_out + 1)], rtol=1e-6, atol=1e-6)
        if not sol.success:
            raise RuntimeError(f"transitório falhou na fase {ph.condition.name}: {sol.message}")
        t_all += [t0 + float(x) for x in sol.t]
        T_all += [float(x) for x in sol.y[0]]
        names += [ph.condition.name] * len(sol.t)
        T = float(sol.y[0][-1])
        t0 += ph.duration_s
    i = max(range(len(T_all)), key=lambda k: T_all[k]) if T_all else 0
    j = min(range(len(T_all)), key=lambda k: T_all[k]) if T_all else 0
    return {"t_s": t_all, "T_K": T_all, "phase": names, "T_max_K": T_all[i] if T_all else None,
            "t_max_s": t_all[i] if T_all else None, "phase_at_max": names[i] if T_all else None,
            "T_min_K": T_all[j] if T_all else None, "T_end_K": T, "tau_note": "capacidade concentrada"}


def component_temperature(T_bay_K: float, Q_W: float, conductance_W_K: float | None) -> float | None:
    """T_componente = T_b + Q/G (G = condutância componente→ar do compartimento). Sem G: desconhecido (≥ T_b)."""
    if Q_W <= 0:
        return T_bay_K
    if conductance_W_K is None or conductance_W_K <= 0 or not math.isfinite(conductance_W_K):
        return None
    return T_bay_K + Q_W / conductance_W_K
