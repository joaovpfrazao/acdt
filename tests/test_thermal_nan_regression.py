# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Regressão: NaN no brentq de ``solve_bay_steady`` (2/28 corridas do estudo uq_disciplinas).

Causa isolada: com bateria ~194–206 Wh/kg e η_total ~0,59–0,60 o ciclo ``iterar`` térmica ↔ dimensionamento entra
em espiral de massa, o dimensionamento não converge e o ``DesignResult`` traz V_cruzeiro e P_SL = NaN; a térmica
recebia Q e V NaN. Não há solução de regime: fica ``nao_avaliado`` com o motivo (desconhecido ≠ zero)."""
from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from acdt.core.thermal.air import ambient
from acdt.core.thermal.network import Bay, Bound, Condition, solve_bay_steady
from acdt.domains.aircraft.thermal import sizing_unusable

ROOT = Path(__file__).resolve().parents[1]

# amostra de treino 1 com ok:false em examples/output/uq_disciplinas/uq.json
FAILING = {
    "assumptions.propulsion.battery_Wh_kg": 206.49235625993063,
    "assumptions.propulsion.eta_total": 0.5993341794651943,
    "assumptions.thermal.electric.eta_esc": 0.9689757200139838,
    "assumptions.life_cycle.cost_per_fh_USD": 68.33789133701055,
    "assumptions.life_cycle.fh_per_aircraft_per_year": 400.1517315564029,
    "assumptions.life_cycle.environment.grid_intensity_kgCO2e_per_kWh": 0.1117322179691137,
    "assumptions.life_cycle.discount_rate": 0.05634810983931782,
}


def _bay() -> Bay:
    return Bay(id="avionica", skin_area_m2=1.0, flow_length_m=1.6, height_m=0.2, eps_ext=Bound(0.85, 0.85, "t"),
               alpha_solar=Bound(0.3, 0.3, "t"), sun_area_m2=0.3, eps_int=Bound(0.1, 0.9, "t"),
               capacity_J_K=9000.0)


@pytest.mark.parametrize("Q,V", [(float("nan"), 20.0), (50.0, float("nan"))])
def test_solve_bay_steady_rejects_non_finite_inputs_clearly(Q, V):
    cond = Condition("subida_quente", ambient("mil310_hot_1pct", 0.0), V, 1120.0)
    with pytest.raises(ValueError, match="não finita"):
        solve_bay_steady(_bay(), cond, Q, hot=True)


def test_solve_bay_steady_still_solves_finite_hot_case():
    cond = Condition("subida_quente", ambient("mil310_hot_1pct", 0.0), 20.0, 1120.0)
    s = solve_bay_steady(_bay(), cond, 50.0, hot=True)
    assert math.isfinite(s.T_bay_K) and s.T_bay_K > cond.ambient.T_K - 60.0


def test_sizing_unusable_flags_non_converged_or_nan():
    ok = SimpleNamespace(sizing=SimpleNamespace(converged=True, W0=27.0), cruise_speed=22.0, power_sl=900.0)
    assert sizing_unusable(ok) is None
    assert "não convergiu" in sizing_unusable(SimpleNamespace(sizing=SimpleNamespace(converged=False, W0=30.0),
                                                              cruise_speed=22.0, power_sl=900.0))
    assert "cruise_speed" in sizing_unusable(SimpleNamespace(sizing=SimpleNamespace(converged=True, W0=30.0),
                                                             cruise_speed=float("nan"), power_sl=900.0))


def test_uq_failing_sample_gives_nao_avaliado_not_nan():
    from acdt.core.pipeline import DesignState, get_domain
    from acdt.domains.aircraft.mission import MissionSpec
    from acdt.domains.aircraft.uq_run import apply_fixed, set_path

    ex = ROOT / "examples/uav_endurance_payload.yaml"
    raw = yaml.safe_load(ex.read_text(encoding="utf-8"))
    u = yaml.safe_load((ROOT / "examples/studies/uq_disciplinas/uq_disciplinas.yaml").read_text(encoding="utf-8"))
    raw = apply_fixed(raw, u["uncertainty"]["fixed"])
    for k, v in FAILING.items():
        set_path(raw, k, v)
    st = DesignState("aircraft", {"spec": MissionSpec.from_dict(raw, ex), "options": {"no_systems": True}})
    for stage in get_domain("aircraft").stages:
        stage.run(st)                                   # antes: ValueError "function value ... is NaN"
    r = st.data["result"]
    assert r.sizing.converged is False
    assert r.thermal["evaluated"] is False and "não convergiu" in r.thermal["reason"]
    assert r.icing["evaluated"] is False and "não convergiu" in r.icing["reason"]
