# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""`uncertainty.fixed`: sobreposições fixas do estudo de UQ (como `mdo.fixed`), sem mudar o yaml da missão."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from acdt.domains.aircraft.uq_run import apply_fixed

ROOT = Path(__file__).resolve().parents[1]


def test_apply_fixed_numbers_blocks_and_value_nodes():
    raw = {"assumptions": {"propulsion": {"battery_Wh_kg": 200}}, "requirements": {"endurance": {"min": 2.5}}}
    out = apply_fixed(raw, {"assumptions.propulsion.battery_Wh_kg": 210, "requirements.endurance": 3.0,
                            "assumptions.thermal": {"coupling": "iterar"},
                            "assumptions.aero.fidelity": "handbook"})
    assert raw["assumptions"]["propulsion"]["battery_Wh_kg"] == 200          # original intacto
    assert out["assumptions"]["propulsion"]["battery_Wh_kg"] == 210.0
    assert out["requirements"]["endurance"]["min"] == 3.0
    assert out["assumptions"]["thermal"] == {"coupling": "iterar"}
    assert out["assumptions"]["aero"]["fidelity"] == "handbook"


def test_study_spec_parses_with_fixed_nominals():
    from acdt.core.sensitivity.study import parse_spec
    from acdt.domains.aircraft.uq_run import nominal_of

    u = yaml.safe_load((ROOT / "examples/studies/uq_disciplinas/uq_disciplinas.yaml").read_text(encoding="utf-8"))
    assert u["applied"] is False
    unc = dict(u["uncertainty"])
    raw = yaml.safe_load((ROOT / "examples/uav_endurance_payload.yaml").read_text(encoding="utf-8"))
    raw = apply_fixed(raw, unc.pop("fixed"))
    spec = parse_spec(unc, lambda p: nominal_of(raw, p), [], [])
    noms = {i.path: i.nominal for i in spec.inputs}
    assert noms["assumptions.life_cycle.cost_per_fh_USD"] == pytest.approx(65.0)
    assert noms["assumptions.life_cycle.environment.grid_intensity_kgCO2e_per_kWh"] == pytest.approx(0.25)
    assert noms["assumptions.thermal.electric.eta_esc"] == pytest.approx(0.97)
