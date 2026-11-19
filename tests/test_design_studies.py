# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Blocos MDO, V&V e L3 no estado de projeto (docs/DADOS.md). Não corre solvers."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from acdt.cli import main
from acdt.core import design_db as D
from acdt.core.design_studies import (
    attach_hifi_path,
    attach_hifi_step,
    attach_mdo,
    attach_mdo_file,
    attach_vv,
    attach_vv_file,
)
from acdt.core.review.bundle import Bundle
from acdt.core.review.evaluate import Ctx, primary_disciplines
from acdt.core.review.profile import NON_PRIMARY, profile_for

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "data" / "review_small"


def _db() -> dict:
    return D.new("estudo", "analitico", {"input": {"asa": "inalterada"}, "source": None})


def test_mdo_copies_chosen_and_omits_missing_objective():
    db = _db()
    D.set_results(db, "aerodinamica", "L1", {"CD0": D.quantity(0.02, None)}, method="L1", source="teste")
    study = {"schema": "acdt.mdo/1", "strategy": "doe", "n_evaluations": 2, "n_failed": 0, "n_feasible": 1,
             "pareto": [1], "chosen": 1, "evaluations": [
                 {"id": 1, "feasible": True, "objectives": {"f1": 0.4, "CD0": None},
                  "x": {"span_m": 1.5, "nota": "texto"}}]}
    rep = attach_mdo(db, study, evidence="mdo.json", evidence_sha256="abc")
    assert rep["veredicto"] == "validado" and rep["calibracao"] == "nao_aplicar"
    qs = db["results"]["mdo"]["L2"]["quantities"]
    assert qs["n_evaluations"]["value"] == 2 and qs["n_pareto"]["value"] == 1
    assert qs["objetivo.f1"]["value"] == 0.4 and qs["objetivo.f1"]["unit"] is None
    assert "objetivo.CD0" not in qs
    assert qs["n_failed"]["value"] == 0  # zero declarado no registo, não um objetivo em falta
    assert qs["x.span_m"]["unit"] == "m" and qs["x.span_m"]["value"] == 1.5
    assert "x.nota" not in qs
    assert qs["escolhido.feasible"]["value"] is True and qs["escolhido.feasible"]["unit"] is None
    assert db["definition"]["input"] == {"asa": "inalterada"}
    assert db["definition"]["derived"]["mdo"]["variables"] == {"span_m": 1.5}
    assert db["definition"]["derived"]["mdo"]["chosen"] == 1
    assert db["results"]["aerodinamica"]["L1"]["quantities"]["CD0"]["value"] == 0.02
    assert "mdo.json" in db["results"]["mdo"]["L2"]["evidence"]
    assert D.validate(db) == []


def test_mdo_without_chosen_does_not_invent_an_optimum():
    db = _db()
    rep = attach_mdo(db, {"schema": "acdt.mdo/1", "n_evaluations": 3, "pareto": [0], "chosen": None,
                          "evaluations": [{"id": 0, "objectives": {"f1": 1.0}, "x": {"span_m": 2.0}}]},
                     evidence=None, evidence_sha256=None)
    qs = db["results"]["mdo"]["L2"]["quantities"]
    assert rep["veredicto"] == "validado"
    assert "chosen" in rep["omitidas"]
    assert not any(k.startswith("objetivo.") or k.startswith("x.") for k in qs)
    assert qs["n_evaluations"]["value"] == 3
    assert db["definition"]["derived"]["mdo"]["variables"] == {}
    assert "pareto" not in qs


def test_mdo_pareto_absent_is_not_zero():
    db = _db()
    attach_mdo(db, {"schema": "acdt.mdo/1", "n_evaluations": 1, "chosen": None, "evaluations": []},
               evidence=None, evidence_sha256=None)
    qs = db["results"]["mdo"]["L2"]["quantities"]
    assert "n_pareto" not in qs
    with pytest.raises(D.DesignDBError):
        attach_mdo(db, {"schema": "acdt.uq/1"}, evidence=None, evidence_sha256=None)


def test_vv_skips_unevaluated_and_keeps_stored_relative_error():
    db = _db()
    report = {"schema": "acdt.vv/1", "registry_version": "2026.11.17",
              "counts": {"passa": 1, "nao_avaliado": 1},
              "cases": [{"id": "ATM.ISA", "status": "passa", "results": [
                  {"quantity": "T", "status": "passa", "delta": 0.0, "delta_rel": 0.0, "unit": "K"},
                  {"quantity": "mu", "status": "nao_avaliado", "delta": None, "delta_rel": None, "unit": "Pa·s"},
                  {"quantity": "x", "status": "desconhecido", "delta": 0.0, "delta_rel": 0.0},
                  {"quantity": "razão", "status": "passa", "delta": 1.0, "delta_rel": None, "unit": "1"},
              ]}]}
    rep = attach_vv(db, report, evidence="vv_report.json", evidence_sha256="def")
    qs = db["results"]["vv"]["L0"]["quantities"]
    assert rep["veredicto"] == "validado"
    assert qs["caso.ATM_ISA.T.delta"]["value"] == 0.0 and qs["caso.ATM_ISA.T.delta"]["unit"] == "K"
    assert qs["caso.ATM_ISA.T.delta_rel"]["unit"] == "1"
    assert qs["caso.ATM_ISA.status"]["value"] == "passa"
    assert not any("mu" in k or k.endswith(".x.delta") or ".x.delta_rel" in k for k in qs)
    assert "caso.ATM_ISA.mu" in rep["omitidas"] and "caso.ATM_ISA.x" in rep["omitidas"]
    assert qs["caso.ATM_ISA.razão.delta"]["value"] == 1.0
    assert "caso.ATM_ISA.razão.delta_rel" not in qs
    assert db["results"]["vv"]["L0"]["references"] == ["2026.11.17"]
    assert D.validate(db) == []


def test_hifi_copies_only_finite_scalars_and_merges_steps(tmp_path: Path):
    db = _db()
    fem = tmp_path / "fem.json"
    fem.write_text(json.dumps({"tip_w_fem_m": 0.012, "tip_twist_fem_deg": 1.5, "ok": True,
                               "margin": {"V_required": 40.0, "g003": math.inf},
                               "cover_bay": {"bay": 12.0}, "CL": [0.1, 0.2]}), encoding="utf-8")
    r1 = attach_hifi_path(db, fem, step="fem")
    assert r1[0]["veredicto"] == "validado" and r1[0]["disciplina"] == "estruturas"
    qs = db["results"]["estruturas"]["L3"]["quantities"]
    assert qs["fem.tip_w_fem_m"]["unit"] == "m" and qs["fem.tip_w_fem_m"]["value"] == 0.012
    assert qs["fem.tip_twist_fem_deg"]["unit"] == "deg"
    assert qs["fem.margin.V_required"]["value"] == 40.0 and qs["fem.margin.V_required"]["unit"] is None
    assert "fem.margin.g003" not in qs and "fem.ok" not in qs and "fem.CL" not in qs
    assert qs["fem.cover_bay.bay"]["unit"] is None and qs["fem.cover_bay.bay"]["value"] == 12.0
    nl = tmp_path / "nl.json"
    nl.write_text(json.dumps({"tip_w_fem_m": 0.02}), encoding="utf-8")
    r2 = attach_hifi_path(db, nl, step="nlgeom")
    assert r2[0]["disciplina"] == "estruturas"
    qs = db["results"]["estruturas"]["L3"]["quantities"]
    assert qs["fem.tip_w_fem_m"]["value"] == 0.012 and qs["nlgeom.tip_w_fem_m"]["value"] == 0.02
    assert db["results"]["estruturas"]["L3"]["sections"]["fem"].startswith("acdt hifi passo")
    assert any("fem.json" in n for n in db["results"]["estruturas"]["L3"]["notes"])
    assert D.validate(db) == []


def test_hifi_skipped_unknown_and_rans_estimate_write_nothing():
    db = _db()
    assert attach_hifi_step(db, "flutter", {"skipped": "sem binário", "VD_eas": 80.0},
                            evidence=None, evidence_sha256=None)["veredicto"] == "nao_avaliado"
    assert attach_hifi_step(db, "calibration", {"factor": 1.1}, evidence=None, evidence_sha256=None)["motivo"]
    assert "sem disciplina" in attach_hifi_step(
        db, "calibration", {"factor": 1.1}, evidence=None, evidence_sha256=None)["motivo"]
    est = attach_hifi_step(db, "rans_case", {"cells_estimate": 1.0e6, "ram_GB": 4.0},
                           evidence=None, evidence_sha256=None)
    assert est["veredicto"] == "nao_avaliado" and "CL" in est["motivo"]
    ponto = attach_hifi_step(db, "rans_case", {"CL": 0.4, "CD": 0.03, "ok": True},
                             evidence="ponto.json", evidence_sha256=None)
    assert ponto["veredicto"] == "validado" and ponto["disciplina"] == "aerodinamica"
    ala = attach_hifi_step(db, "wing_euler", {"CL": [0.1, 0.2], "CLa_euler": 4.8, "ok": True},
                           evidence=None, evidence_sha256=None)
    assert ala["veredicto"] == "validado"
    aero = db["results"]["aerodinamica"]["L3"]["quantities"]
    assert "rans_case.CL" in aero and "wing_euler.CLa_euler" in aero
    assert aero["wing_euler.CLa_euler"]["unit"] is None
    assert "wing_euler.CL" not in aero and "rans_case.ok" not in aero
    assert "estruturas" not in db["results"] and "aeroelasticidade" not in db["results"]
    assert db["results"].keys() == {"aerodinamica"}


def test_hifi_directory_skips_missing_and_empty_dir_errors(tmp_path: Path):
    db = _db()
    (tmp_path / "fem").mkdir()
    (tmp_path / "fem" / "fem_results.json").write_text(json.dumps({"tip_w_fem_m": 0.01}), encoding="utf-8")
    reps = attach_hifi_path(db, tmp_path)
    assert [r["passo"] for r in reps] == ["fem"]
    assert db["results"]["estruturas"]["L3"]["quantities"]["fem.tip_w_fem_m"]["value"] == 0.01
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    with pytest.raises(D.DesignDBError):
        attach_hifi_path(db, vazio)
    with pytest.raises(D.DesignDBError):
        attach_hifi_path(db, tmp_path / "fem" / "fem_results.json")


def test_mdo_and_vv_are_not_primary_disciplines(tmp_path: Path):
    assert "mdo" in NON_PRIMARY and "vv" in NON_PRIMARY
    db = _db()
    attach_mdo(db, {"schema": "acdt.mdo/1", "n_evaluations": 1, "pareto": [], "chosen": None, "evaluations": []},
               evidence=None, evidence_sha256=None)
    attach_vv(db, {"schema": "acdt.vv/1", "counts": {"passa": 1}, "cases": []}, evidence=None, evidence_sha256=None)
    attach_hifi_step(db, "fem", {"tip_w_fem_m": 0.01}, evidence=None, evidence_sha256=None)
    b = Bundle(base=tmp_path, design_path=tmp_path / "design.json", design=db, design_sha256="x")
    ctx = Ctx(bundle=b, profile=profile_for("sem_perfil_de_teste"), gate="PDR")
    prim = primary_disciplines(ctx)
    assert prim == ["estruturas"]


def test_cli_add_mdo_and_vv_from_fixtures(tmp_path: Path):
    db = D.new("review_small", "analitico")
    dst = tmp_path / "design.json"
    D.save(db, dst)
    assert main(["db", "add-mdo", str(dst), str(FIX / "mdo")]) == 0
    assert main(["db", "add-vv", str(dst), str(FIX / "vv" / "vv_report.json")]) == 0
    loaded = D.load(dst)
    assert D.validate(loaded) == []
    mdo = loaded["results"]["mdo"]["L2"]["quantities"]
    assert mdo["n_evaluations"]["value"] == 9 and mdo["n_pareto"]["value"] == 9
    assert mdo["escolhido.feasible"]["value"] is True
    assert "objetivo.f1" in mdo and "objetivo.f2" in mdo
    assert loaded["definition"]["derived"]["mdo"]["chosen"] == 4
    vv = loaded["results"]["vv"]["L0"]["quantities"]
    assert vv["caso.ATM-ISA-SL.status"]["value"] == "passa"
    assert vv["caso.ATM-ISA-SL.T.delta"]["value"] == 0.0
    assert loaded["results"]["vv"]["L0"]["references"] == ["2026.11.17"]
    hifi = tmp_path / "hifi.json"
    hifi.write_text(json.dumps({"skipped": "sintético"}), encoding="utf-8")
    assert main(["db", "add-hifi", str(dst), str(hifi), "--step", "flutter"]) == 0
    assert "aeroelasticidade" not in D.load(dst)["results"]


def test_fixture_files_round_trip_hashes(tmp_path: Path):
    db = _db()
    rep = attach_mdo_file(db, FIX / "mdo" / "mdo.json")
    assert rep["veredicto"] == "validado"
    vrep = attach_vv_file(db, FIX / "vv")
    assert vrep["veredicto"] == "validado"
    assert db["results"]["mdo"]["L2"]["evidence_sha256"]
    assert db["results"]["vv"]["L0"]["evidence_sha256"]
    D.save(db, tmp_path / "design.json")
    assert D.validate(D.load(tmp_path / "design.json")) == []
