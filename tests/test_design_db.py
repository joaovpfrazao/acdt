# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Estado de projeto único acdt.design/1 e unidades na fronteira (docs/DADOS.md)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from acdt.core import design_db as D
from acdt.core import quantities as Q
from acdt.core.requirements import RequirementError, parse_requirement
import acdt.domains.aircraft  # noqa: F401,E402  (regista os tipos de requisito)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


# ------------------------------------------------------------------------------------------ unidades
def test_to_unit_conversions_exact():
    assert Q.to_unit("150 kg", "kg") == 150.0
    assert Q.to_unit("100 lb", "kg") == pytest.approx(45.359237, rel=1e-12)   # lb exata (NIST SP 811)
    assert Q.to_unit({"value": 10, "unit": "ft"}, "m") == pytest.approx(3.048, rel=1e-12)
    assert Q.to_unit(3.2, "m") == 3.2                                          # número simples: já na unidade
    assert Q.to_unit("90 deg", "rad") == pytest.approx(math.pi / 2)
    assert Q.to_unit("15 degC", "K") == pytest.approx(288.15)                  # afim (pint)


def test_dimension_error_is_clear():
    with pytest.raises(Q.QuantityError) as e:
        Q.to_unit("3 kg", "m", "assumptions.geometry.fuselage_length_m")
    msg = str(e.value)
    assert "fuselage_length_m" in msg and "[mass]" in msg and "[length]" in msg
    with pytest.raises(Q.QuantityError):
        Q.to_unit("3 parsecs_nao_existe", "m")
    with pytest.raises(Q.QuantityError):
        Q.parse_quantity("kg 3")
    assert isinstance(Q.QuantityError("x"), ValueError)


def test_unit_from_key_suffix():
    assert Q.unit_from_key("W0_kg") == "kg"
    assert Q.unit_from_key("W_S_N_m2") == "N/m**2"
    assert Q.unit_from_key("cruise_speed_m_s") == "m/s"
    assert Q.unit_from_key("CL_alpha_per_rad") == "1/rad"
    assert Q.unit_from_key("engine_kW_per_kg") == "kW/(kg)"
    assert Q.unit_from_key("arm_in") == "inch"
    assert Q.unit_from_key("CD0") is None              # não declarada, nunca «adimensional» por omissão
    assert Q.unit_from_key("accel_g") is None          # fator de carga ≠ grama
    r = Q.ureg()
    for s, u in Q.SUFFIX_UNITS.items():                # todas as unidades da tabela são pint válidas
        if u not in Q._OPAQUE:
            r.Quantity(1.0, u)


def test_normalise_tree_converts_by_key_and_keeps_numbers():
    src = {"geometry": {"fuselage_length_m": "10 ft", "c_ht": 0.55, "stations_m": ["1 ft", 2.0]},
           "airfoil": "NACA 4415", "weight_balance": {"arm_in": {"value": 1, "unit": "m"}}}
    out = Q.normalise_tree(src, "assumptions")
    assert out["geometry"]["fuselage_length_m"] == pytest.approx(3.048)
    assert out["geometry"]["stations_m"] == [pytest.approx(0.3048), 2.0]
    assert out["geometry"]["c_ht"] == 0.55 and out["airfoil"] == "NACA 4415"
    assert out["weight_balance"]["arm_in"] == pytest.approx(1 / 0.0254)
    assert src["geometry"]["fuselage_length_m"] == "10 ft"           # não altera a entrada
    assert Q.normalise_tree({"AR": "16 m"}) == {"AR": "16 m"}   # chave sem unidade declarada: texto, não se adivinha
    free = {"retrieved": "2026-11-06", "notes": "2 tempos", "ref": "3 pins", "id": "123"}   # texto livre: igual
    assert Q.normalise_tree(free) == free
    with pytest.raises(Q.QuantityError, match=r"\[time\]"):
        Q.normalise_tree({"geometry": {"fuselage_length_m": "3 s"}})


def test_examples_unchanged_by_normalisation():
    """Compatibilidade: nenhum exemplo existente (sem unidades em texto) muda."""
    import yaml
    n = 0
    for f in sorted(EX.rglob("*.yaml")):
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(d, dict):
            continue
        for sec in ("assumptions", "systems", "onboard"):
            if isinstance(d.get(sec), (dict, list)):
                assert Q.normalise_tree(d[sec], sec) == d[sec], f
                n += 1
    assert n > 10


def test_requirement_with_unit_text():
    a = parse_requirement("payload_mass", "30 kg")
    b = parse_requirement("payload_mass", {"target": 30, "unit": "kg"})
    assert a.value == b.value == 30.0 and a.unit == "kg" and a.raw == 30.0
    e = parse_requirement("endurance", {"min": "10 h"})
    assert e.value == 36000.0 and e.sense == "min" and e.unit == "h"
    v = parse_requirement("cruise_speed", {"target": "27 kt"})
    assert v.value == pytest.approx(27 * 1852 / 3600)
    k = parse_requirement("cruise_speed", {"target": "100 kilometer/hour"})   # fora da tabela: pint
    assert k.value == pytest.approx(100 / 3.6)
    assert parse_requirement("endurance", {"min": 10, "unit": "h"}).value == 36000.0   # forma antiga igual
    assert parse_requirement("payload_mass", 30).value == 30.0                         # número simples = SI
    with pytest.raises(RequirementError, match=r"\[length\]|não válida"):
        parse_requirement("payload_mass", "30 m")


def test_mission_spec_units_in_assumptions(tmp_path):
    from acdt.domains.aircraft.mission import MissionSpec
    import yaml
    d = yaml.safe_load((EX / "ga_range_speed.yaml").read_text(encoding="utf-8"))
    d.setdefault("assumptions", {}).setdefault("geometry", {})["fuselage_length_m"] = "26.25 ft"
    s = MissionSpec.from_dict(d)
    assert s.assumptions["geometry"]["fuselage_length_m"] == pytest.approx(8.001)
    d["assumptions"]["geometry"]["fuselage_length_m"] = "8 kg"
    with pytest.raises(Q.QuantityError, match="fuselage_length_m"):
        MissionSpec.from_dict(d)


def test_verification_threshold_with_unit():
    from acdt.core.verification import VerificationError, from_dict
    r = from_dict({"id": "X-1", "quantity": "q", "comparison": "max", "threshold": "300 m"})
    assert r.threshold == 300.0 and r.unit == "m"
    r2 = from_dict({"id": "X-2", "quantity": "q", "comparison": "min", "threshold": "1 km", "goal": "2 km"})
    assert r2.threshold == 1000.0 and r2.goal == 2000.0
    with pytest.raises(VerificationError):
        from_dict({"id": "X-3", "quantity": "q", "comparison": "max", "threshold": "3 m", "unit": "ft"})


# ------------------------------------------------------------------------------------- base de dados
def _db() -> dict:
    db = D.new("teste", "aircraft", {"requirements": {
        "payload_mass.target": {"value": 30.0, "unit": "kg", "sense": "target", "raw": 30, "raw_unit": "kg"}}})
    D.set_results(db, "massas", "L0", D.quantities_from_tree({"W0_kg": 150.0, "CD0": 0.03, "ok": True,
                                                             "nan_kg": float("nan"), "S_m2": None}, ""),
                  method="Raymer", references=["Raymer 6.ª ed."], source="teste",
                  provenance={"fingerprint": "abc"})
    D.set_results(db, "aerodinamica", "L1", D.quantities_from_tree({"aero": {"CL_alpha_per_rad": 5.0,
                                                                            "cruise_speed_m_s": 27.0}}),
                  method="AVL", source="teste")
    return db


def test_roundtrip_and_schema(tmp_path):
    db = _db()
    p = D.save(db, tmp_path / "design.json")
    back = D.load(tmp_path)                          # aceita a pasta
    assert back["revision"] == 1 and back["schema"] == D.SCHEMA
    q = back["results"]["massas"]["L0"]["quantities"]
    assert q["W0_kg"] == {"value": 150.0, "unit": "kg"}
    assert q["CD0"]["unit"] is None                  # não declarada
    assert q["nan_kg"]["value"] is None and "não finito" in q["nan_kg"]["note"]   # desconhecido, não zero
    assert q["S_m2"]["value"] is None
    assert D.validate(back) == []
    assert D.diff(db, back)["identical"]
    txt = p.read_text(encoding="utf-8")
    assert "NaN" not in txt
    D.save(back, p)
    assert D.load(p)["revision"] == 2


def test_schema_rejects_bad_states(tmp_path):
    db = _db()
    with pytest.raises(D.DesignDBError):
        D.set_results(db, "massas", "L7", {})
    bad = json.loads(D.dumps(db))
    bad["results"]["massas"]["L0"]["quantities"]["W0_kg"] = {"value": 1.0}          # sem unit
    assert any("unit" in e for e in D.validate(bad))
    bad2 = json.loads(D.dumps(db))
    bad2["results"]["massas"]["L9"] = bad2["results"]["massas"].pop("L0")
    assert D.validate(bad2)
    (tmp_path / "x.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(D.DesignDBError):
        D.load(tmp_path / "x.json")
    assert D.validate({"schema": "acdt.design/0"})


def test_query_and_get_value():
    db = _db()
    assert list(D.query(db, "results.massas.L0.W0_kg")) == ["results.massas.L0.W0_kg"]
    assert list(D.query(db, "W0_kg")) == ["results.massas.L0.W0_kg"]
    assert set(D.query(db, "results.*.L1.*")) == {"results.aerodinamica.L1.aero.CL_alpha_per_rad",
                                                   "results.aerodinamica.L1.aero.cruise_speed_m_s"}
    hit = D.query(db, "W0_kg")["results.massas.L0.W0_kg"]
    assert hit["level"] == "L0" and hit["method"] == "Raymer" and hit["provenance_fingerprint"] == "abc"
    assert D.get_value(db, "results.massas.L0.W0_kg", "lb") == pytest.approx(150 / 0.45359237)
    assert D.get_value(db, "results.aerodinamica.L1.aero.cruise_speed_m_s", "knot") == pytest.approx(27 * 3600 / 1852)
    with pytest.raises(D.DesignDBError, match="não declarada"):
        D.get_value(db, "results.massas.L0.CD0", "1")
    assert "definition.requirements.payload_mass.target" in D.flatten(db)


def test_diff_values_units_and_structure():
    a = _db()
    b = D.copy_db(a)
    qb = b["results"]["massas"]["L0"]["quantities"]
    qb["W0_kg"] = {"value": 160.0, "unit": "kg"}
    qb["CD0"] = {"value": 0.03, "unit": None}
    b["results"]["aerodinamica"]["L1"]["quantities"]["aero.cruise_speed_m_s"] = \
        {"value": 27 * 3600 / 1852, "unit": "knot"}                                  # mesmo valor noutra unidade
    del qb["ok"]
    qb["novo_m"] = {"value": 1.0, "unit": "m"}
    d = D.diff(a, b)
    paths = {c["path"]: c for c in d["changed"]}
    assert set(paths) == {"results.massas.L0.W0_kg"}
    assert paths["results.massas.L0.W0_kg"]["delta"] == pytest.approx(10.0)
    assert paths["results.massas.L0.W0_kg"]["rel"] == pytest.approx(10 / 150)
    assert d["added"] == ["results.massas.L0.novo_m"] and d["removed"] == ["results.massas.L0.ok"]
    assert not d["identical"]
    b["results"]["aerodinamica"]["L1"]["quantities"]["aero.cruise_speed_m_s"] = {"value": 27.0, "unit": "kg"}
    d2 = D.diff(a, b, include="results.aerodinamica.*")
    assert d2["changed"][0]["kind"] == "unidade_incompativel"
    assert "W0_kg" in D.explain_diff(d) and "+ results.massas.L0.novo_m" in D.explain_diff(d)


def test_uncertainty_and_export(tmp_path):
    db = _db()
    D.set_uncertainty(db, "results.massas.L0.W0_kg", {"kind": "percentis", "p5": 140.0, "p50": 150.0,
                                                       "p95": 162.0, "n": 256, "source": "acdt uq (teste)"})
    with pytest.raises(D.DesignDBError):
        D.set_uncertainty(db, "results.massas.L0.W0_kg", {"kind": "palpite", "source": "x"})
    with pytest.raises(D.DesignDBError):
        D.set_uncertainty(db, "results.massas.L0.nao_existe", {"kind": "intervalo", "lo": 0, "hi": 1, "source": "x"})
    D.save(db, tmp_path / "d.json")
    back = D.load(tmp_path / "d.json")
    assert back["results"]["massas"]["L0"]["quantities"]["W0_kg"]["uncertainty"]["p95"] == 162.0
    csv_txt = D.to_csv(back)
    assert csv_txt.splitlines()[0].startswith("path,value,unit,discipline,level")
    assert "results.massas.L0.W0_kg,150.0,kg,massas,L0,Raymer" in csv_txt
    md = D.to_markdown(back, "results.massas.*")
    assert "não declarada" in md and "W0_kg" in md
    assert "massas" in D.summary(back)


def test_verification_section():
    db = _db()
    m = {"schema": "acdt.verification/1", "provenance": {"fingerprint": "f"}, "coverage": {"n": 2},
         "rows": [{"id": "R1", "status": "passa", "value": 1.0, "unit": "m", "threshold": 2.0},
                  {"id": "R2", "status": "nao_avaliado", "value": None}]}
    D.set_verification(db, m)
    assert db["verification"]["counts"] == {"passa": 1, "nao_avaliado": 1}
    assert D.validate(json.loads(D.dumps(db))) == []
    assert D.flatten(db)["verification.R2"]["value"] == "nao_avaliado"


# ------------------------------------------------------------------------------------- integração aircraft
def test_results_into_db_from_result_dict():
    from acdt.domains.aircraft.design_db_run import build
    from acdt.domains.aircraft.mission import MissionSpec
    spec = MissionSpec.from_yaml(EX / "ga_range_speed.yaml")
    result = {"acdt_version": "x", "name": "n", "feasible": True, "requirements": [],
              "weights": {"W0_kg": 1000.0, "We_W0": 0.6}, "aero": {"CD0": 0.03},
              "secao_nova": {"x_m": 1.0}, "mda_history": [1, 2]}
    db = build(spec, result, None)
    assert db["results"]["dimensionamento"]["L0"]["quantities"]["weights.W0_kg"]["unit"] == "kg"
    assert db["results"]["aerodinamica"]["L0"]["quantities"]["aero.CD0"]["unit"] is None
    assert "secao_nova" in db["results"]["outros"]["L0"]["notes"][0]          # nada se perde, fica assinalado
    assert "mda_history" not in json.dumps(db["results"])
    req = db["definition"]["requirements"]
    assert any(k.startswith("cruise_speed.") for k in req)
    assert db["definition"]["source"]["sha256"]
    assert D.validate(json.loads(D.dumps(db))) == []


@pytest.mark.slow
def test_pipeline_writes_design_json_and_cli(tmp_path, capsys):
    from acdt.cli import main
    from acdt.core.pipeline import run_pipeline
    out = tmp_path / "ga"
    st = run_pipeline("aircraft", EX / "ga_range_speed.yaml", output=out)
    db = D.load(out)
    assert db["revision"] == 1 and st["design"]["revision"] == 1
    w0 = D.get_value(db, "results.dimensionamento.L0.weights.W0_kg")
    assert w0 == pytest.approx(st["result"].sizing.W0)
    assert db["verification"] and sum(db["verification"]["counts"].values()) == len(db["verification"]["rows"])
    # bloco de outra fonte (p. ex. L3) mantém-se; os do próprio `acdt size` são substituídos
    D.set_results(db, "aerodinamica", "L3", {"CL": D.quantity(0.5, "1")}, method="RANS", source="hifi (teste)")
    D.save(db, out / "design.json")
    run_pipeline("aircraft", EX / "ga_range_speed.yaml", output=out)
    db2 = D.load(out)
    assert db2["revision"] == 3 and "L3" in db2["results"]["aerodinamica"]
    assert D.diff(db, db2, include="results.dimensionamento.*")["identical"]
    assert main(["db", "show", str(out)]) == 0
    assert main(["db", "get", str(out), "W0_kg", "--unit", "lb"]) == 0
    assert " lb " in capsys.readouterr().out
    assert main(["db", "validate", str(out)]) == 0
    assert main(["db", "export", str(out), "--format", "csv", "-o", str(tmp_path / "x.csv")]) == 0
    assert (tmp_path / "x.csv").read_text(encoding="utf-8").startswith("path,")
    assert main(["db", "diff", str(out / "design.json"), str(out / "design.json")]) == 0
    assert main(["db", "build", str(EX / "ga_range_speed.yaml"), str(out), "-o", str(tmp_path / "b.json")]) == 0
    assert D.load(tmp_path / "b.json")["revision"] == 4


def test_attach_uq_scalar_and_epistemic(tmp_path):
    db = _db()
    D.set_results(db, "dimensionamento", "L0", D.quantities_from_tree({"weights": {"W0_kg": 150.0, "We_kg": 90.0}}),
                  method="Raymer", source="teste")
    uq = {"schema": "acdt.uq/1", "settings": {"n": 4000},
          "propagation": {"summaries": {
              "W0_kg": {"status": "ok", "converged": True, "mean": 151.0, "std": 7.0, "p5": 140.0, "p50": 150.5,
                        "p95": 163.0},
              "We_kg": {"status": "ok", "intervalo": True, "converged": True, "mean": [90.0, 94.0],
                        "std": [5.0, 5.2], "p5": [82.0, 85.0], "p50": [89.0, 93.0], "p95": [99.0, 104.0]},
              "CD0": {"status": "sem_amostras"}}}}
    rep = D.attach_uq(db, uq, {"W0_kg": "weights.W0_kg", "We_kg": "weights.We_kg", "CD0": "aero.CD0",
                              "S_m2": "geometry.wing.S_m2"}, source="teste")
    assert rep["ligadas"] == ["results.dimensionamento.L0.weights.W0_kg", "results.dimensionamento.L0.weights.We_kg"]
    assert set(rep["sem_resumo"]) == {"CD0", "S_m2"}
    q = db["results"]["dimensionamento"]["L0"]["quantities"]
    assert q["weights.W0_kg"]["uncertainty"]["p95"] == 163.0 and q["weights.W0_kg"]["uncertainty"]["n"] == 4000
    u = q["weights.We_kg"]["uncertainty"]
    assert u["p5"] == 82.0 and u["p95"] == 104.0 and u["p50"] is None and u["epistemico"]   # envelope, sem P50 único
    D.save(db, tmp_path / "d.json")
    assert D.validate(D.load(tmp_path / "d.json")) == []
    with pytest.raises(D.DesignDBError):
        D.attach_uq(db, {"schema": "acdt.mdo/1"}, {})


def test_uq_into_db_reads_file_and_model_metrics(tmp_path):
    from acdt.domains.aircraft.design_db_run import uq_into_db
    db = _db()
    D.set_results(db, "dimensionamento", "L0", D.quantities_from_tree({"weights": {"W0_kg": 150.0}}),
                  method="Raymer", source="teste")
    D.set_results(db, "trem", "L0", D.quantities_from_tree({"landing_gear": {"track_m": 1.2}}), method="x",
                  source="teste")
    uq = {"schema": "acdt.uq/1", "settings": {"n": 10}, "model": {"result_metrics": {"bitola": "landing_gear.track_m"}},
          "propagation": {"summaries": {"W0_kg": {"status": "ok", "p5": 1.0, "p50": 2.0, "p95": 3.0},
                                        "bitola": {"status": "ok", "p5": 1.1, "p50": 1.2, "p95": 1.3}}}}
    (tmp_path / "uq.json").write_text(json.dumps(uq), encoding="utf-8")
    rep = uq_into_db(db, tmp_path)
    assert "results.trem.L0.landing_gear.track_m" in rep["ligadas"]
    assert "results.dimensionamento.L0.weights.W0_kg" in rep["ligadas"]
    assert "sha256" in db["results"]["trem"]["L0"]["quantities"]["landing_gear.track_m"]["uncertainty"]["source"]
