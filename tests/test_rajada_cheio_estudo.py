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


def _load_opcao_a_module():
    import importlib.util
    p = ROOT / "examples/studies/rajada_cheio/estudo_opcao_a.py"
    spec = importlib.util.spec_from_file_location("estudo_opcao_a", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_opcao_a_fixed_overrides_only_in_memory():
    mod = _load_opcao_a_module()
    st = yaml.safe_load((ROOT / "examples/studies/rajada_cheio/opcao_a.yaml").read_text(encoding="utf-8"))
    assert st["applied"] is False
    ex = yaml.safe_load((ROOT / st["example"]).read_text(encoding="utf-8"))
    opt = mod.apply_fixed(ex, st["fixed"])
    split = [i for i in opt["assumptions"]["weights"]["components"]["items"] if "split aileron" in i["name"]]
    assert len(split) == 1 and "DA 30-HT" in split[0]["name"] and split[0]["mass_kg"] == 8.80
    fw = opt["assumptions"]["assembly"]["options"]["flying_wing"]
    assert fw["actuators"]["split_rate_required_deg_s"] == 100
    # o dicionário do exemplo não é tocado
    fw0 = ex["assumptions"]["assembly"]["options"]["flying_wing"]
    assert "split_rate_required_deg_s" not in fw0["actuators"]
    sp0 = [i for i in ex["assumptions"]["weights"]["components"]["items"] if "split aileron" in i["name"]]
    assert len(sp0) == 1 and "HT" not in sp0[0]["name"] and sp0[0]["mass_kg"] == 5.04


def test_opcao_a_output_consistent():
    out = json.loads((ROOT / "examples/output/rajada_cheio/opcao_a.json").read_text(encoding="utf-8"))
    assert out["applied"] is False
    b, a = out["base"], out["opcao_a"]
    assert b["converged"] and a["converged"] and a["W0_kg"] > b["W0_kg"]
    assert a["servo_split"]["name"] == "Volz DA 30-HT" and a["servo_split"]["n_per_surface"] == 2
    assert a["rate_max_effective_deg_s"] >= a["split_rate_required_design_deg_s"] == 100
    assert b["split_rate_required_design_deg_s"] is None
    assert a["actuator_mass"]["within_budget"] is True
    assert a["P_elec_per_leaf_W"] is None                    # desconhecida ≠ 0
    for c in a["gust_6dof"]["cases"].values():
        assert c["veredicto"] in ("passa", "falha", "desconhecido")
    # falhas novas listadas a partir das verificações que mudaram para False
    assert set(out["new_failures"]) == {k for k, v in out["checks_changed"].items() if v["opcao_a"] is False}
