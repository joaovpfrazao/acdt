# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Estudo de decisão da rajada do «cheio»: não aplicado e coerente com o registo (sem voltar a correr o 6-DOF)."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_study_is_not_applied_and_output_is_consistent():
    st = yaml.safe_load((ROOT / "examples/studies/rajada_cheio/rajada_cheio.yaml").read_text(encoding="utf-8"))
    assert st["applied"] is False and st["case"] == "cheio"
    out = json.loads((ROOT / "examples/output/rajada_cheio/rajada_cheio.json").read_text(encoding="utf-8"))
    assert out["applied"] is False
    assert out["baseline"]["gust"]["veredicto"] == "falha"
    assert out["baseline"]["gust"]["rate_required_deg_s"] > out["baseline"]["rate_deg_s"]
    assert [float(k) for k in out["a_servo"]] == [float(x) for x in st["options"]["a_servo_rates_deg_s"]]
    for fam in ("a", "b", "c"):
        chk = out["all_cases_check"][fam]
        assert chk["all_pass"] is True and chk["rate_margin_min"] >= 1.0
    # ganhos com Nível 2 não contam como passa (desconhecido/insuficiente ≠ passa)
    for row in out["c_gains"].values():
        if not row["level1_kept"]:
            assert row["veredicto"] == "falha"


def test_example_yaml_untouched_by_study():
    ex = yaml.safe_load((ROOT / "examples/heavy/uav150_flying_wing_tailless.yaml").read_text(encoding="utf-8"))
    fw = ex["assumptions"]["assembly"]["options"]["flying_wing"]
    assert fw["split_aileron"]["bias_deg"] == 2
