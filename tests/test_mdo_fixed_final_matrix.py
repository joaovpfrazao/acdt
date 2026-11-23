# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""`acdt mdo`: a matriz de verificação final do projeto escolhido usa as sobreposições `mdo.fixed` do estudo."""
from __future__ import annotations

from pathlib import Path

import yaml

import acdt.domains.aircraft.mdo_system as M
from acdt.core.sysmdo.evaluate import Record

ROOT = Path(__file__).resolve().parents[1]


def test_final_matrix_applies_fixed(monkeypatch, tmp_path):
    mission = tmp_path / "m.yaml"
    raw = yaml.safe_load((ROOT / "examples/uav_endurance_payload.yaml").read_text(encoding="utf-8"))
    raw["mdo"] = {"fixed": {"assumptions.thermal": {"coupling": "iterar"}, "assumptions.aero.fidelity": "handbook"},
                  "design_variables": [{"path": "assumptions.aero.AR", "lower": 8, "upper": 12, "x0": 10}],
                  "objectives": [{"metric": "W0_kg"}], "strategy": "doe"}
    mission.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    seen = {}

    def fake_run_point(r, source, pt, opts):  # noqa: ANN001, ANN202
        seen["raw"], seen["pt"] = r, pt
        return None, {"rows": []}

    def fake_run_mdo(spec, model, *, outdir, plots, log, final_matrix):  # noqa: ANN001, ANN202
        rec = Record(id=0, combo={}, x={"assumptions.aero.AR": 9.0}, ok=True, metrics={}, requirements={},
                     objectives={}, constraints={}, violation=0.0, feasible=True)
        return {"verification_matrix": final_matrix(rec)}

    monkeypatch.setattr(M, "run_point", fake_run_point)
    monkeypatch.setattr(M, "run_mdo", fake_run_mdo)
    M.run_mdo_mission(mission, tmp_path / "out", plots=False, log=lambda *a: None)
    assert seen["raw"]["assumptions"]["thermal"] == {"coupling": "iterar"}
    assert seen["raw"]["assumptions"]["aero"]["fidelity"] == "handbook"
    assert seen["pt"] == {"assumptions.aero.AR": 9.0}
