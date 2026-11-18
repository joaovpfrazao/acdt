# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Gera o exemplo pequeno do teste dos relatórios de revisão (tests/test_review.py).

Modelo ANALÍTICO de teste (não é um projeto real): y = a + 0,1·b, m_kg = 10·a, sigma_max_Pa fixo. Os registos são
produzidos pelas próprias ferramentas do acdt (matriz de verificação, UQ, MDO, V&V, calibração do exemplo
sintético de examples/calibration) e depois NORMALIZADOS para serem reprodutíveis entre máquinas: instantes fixos,
caminhos relativos, proveniência reduzida (sem versões de pacotes/plataforma) e sem as amostras do Monte Carlo.

    python tests/data/review_small/gerar.py      # reescreve a pasta e o relatório de referência (golden)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIX = "2026-11-18T00:00:00+00:00"


def _dump(p: Path, d: object) -> None:
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _model(p: dict) -> dict:
    return {"y": p["a"] + 0.1 * p["b"], "m_kg": 10.0 * p["a"]}


def generate() -> None:
    from acdt import api
    from acdt.core import design_db as D
    from acdt.core import verification as V
    from acdt.core.provenance import git_info, sha256_file

    for sub in ("uq", "mdo", "vv", "calib"):
        shutil.rmtree(HERE / sub, ignore_errors=True)
    for f in ("result.json", "provenance.json", "verification_matrix.json", "verification_matrix.md",
              "verification_matrix.csv", "design.json"):
        (HERE / f).unlink(missing_ok=True)

    nominal = _model({"a": 1.0, "b": 0.0})
    result = {"feasible": True, "sizing": nominal, "struct": {"sigma_max_Pa": 1.2e8},
              "issues": [{"severity": "warning", "message": "aviso de teste (modelo analítico)"}]}
    _dump(HERE / "result.json", result)
    git = git_info()
    _dump(HERE / "provenance.json", {
        "schema": "acdt.provenance/1", "created": {"utc": FIX, "europe_lisbon": FIX},
        "entry_point": {"command": "tests/data/review_small/gerar.py", "argv": [], "cwd": "."},
        "acdt": {"version": "fixture", "git": {"commit": git.get("commit"), "dirty": False, "branch": "fixture",
                                               "dirty_diff_sha256": None}},
        "python": {}, "packages": {}, "platform": {}, "tools": {}, "inputs": [], "seeds": {},
        "notes": ["registo NORMALIZADO para o teste (sem versões de pacotes nem plataforma)"],
        "outputs": [{"path": "result.json", "sha256": sha256_file(HERE / "result.json"), "written_this_run": True}]})

    reqs = [V.from_dict(d) for d in (
        {"id": "R1", "text": "y máximo", "source": "teste", "quantity": "y", "comparison": "max", "threshold": 1.5,
         "evaluator": "resultado:sizing.y"},
        {"id": "R2", "text": "massa máxima", "source": "teste", "quantity": "m", "comparison": "max",
         "threshold": "10 kg", "tolerance": 0.5, "evaluator": "resultado:sizing.m_kg"},
        {"id": "R3", "text": "tensão máxima", "source": "teste", "quantity": "sigma", "comparison": "max",
         "threshold": "100 MPa", "evaluator": "resultado:struct.sigma_max_Pa"},
        {"id": "R4", "text": "requisito sem avaliador", "source": "teste", "quantity": "z", "comparison": "bool"},
    )]
    ctx = V.context_from_output(HERE, domain="analitico")
    matrix = V.verify(reqs, ctx, HERE)
    for f in ("verification_matrix.md", "verification_matrix.csv"):
        (HERE / f).unlink(missing_ok=True)

    db = D.new("exemplo analítico de teste", "analitico",
               {"source": {"path": "exemplo_analitico.yaml", "sha256": None},
                "input": {"name": "exemplo analítico de teste",
                          "notas": "PRESSUPOSTO: modelo analítico só para testar o relatório"},
                "requirements": {}})
    esha = sha256_file(HERE / "result.json")
    qs = D.quantities_from_tree(result["sizing"], "sizing")
    qs["feasible"] = D.quantity(True, None)
    D.set_results(db, "dimensionamento", "L0", qs, method="função analítica de teste", source="gerar.py",
                  evidence="result.json", evidence_sha256=esha)
    D.set_results(db, "estruturas", "L1", D.quantities_from_tree(result["struct"], "struct"),
                  method="valor fixo de teste", source="gerar.py", evidence="result.json", evidence_sha256=esha)
    D.set_verification(db, matrix, "verification_matrix.json")
    db["created_utc"] = db["updated_utc"] = FIX
    db["history"] = [{"utc": FIX, "what": "gerar.py"}]
    for lv in db["results"].values():
        for blk in lv.values():
            blk["updated_utc"] = FIX
    assert not D.validate(db), D.validate(db)
    _dump(HERE / "design.json", db)

    m = api.function_model(_model, {"a": 1.0, "b": 0.0},
                           [{"id": "R1", "metric": "y", "comparison": "max", "threshold": 1.5}])
    api.uq_study({"n": 200, "seed": 1, "inputs": [
        {"path": "a", "dist": "normal", "std": 0.1, "source": "teste"},
        {"path": "b", "dist": "uniform", "low": -1, "high": 1, "source": "teste"}]}, m, HERE / "uq")
    u = json.loads((HERE / "uq" / "uq.json").read_text(encoding="utf-8"))
    for run in (u.get("propagation") or {}).get("runs") or []:
        run.pop("samples", None)
    for s in ((u.get("propagation") or {}).get("summaries") or {}).values():
        s.pop("running_mean", None)
    _dump(HERE / "uq" / "uq.json", u)

    fm = api.function_model(lambda p: {"f1": p["x"] ** 2, "f2": (p["x"] - 2) ** 2})
    api.mdo_study({"design_variables": [{"path": "x", "lower": 0, "upper": 2, "x0": 1, "source": "teste"}],
                   "objectives": ["f1", "f2"], "strategy": "doe", "options": {"n": 9, "seed": 0}}, fm, HERE / "mdo")

    api.vv(cases=["ATM-ISA-SL"], output=HERE / "vv")
    v = json.loads((HERE / "vv" / "vv_report.json").read_text(encoding="utf-8"))
    v["provenance"] = {"schema": "acdt.provenance/1", "nota": "normalizado para o teste"}
    for c in v["cases"]:
        c["seconds"] = 0.0
    _dump(HERE / "vv" / "vv_report.json", v)

    api.calibrate(ROOT / "examples" / "calibration" / "polar_tunel_sintetico.yaml", HERE / "calib")
    shutil.copyfile(ROOT / "examples" / "calibration" / "polar_tunel_sintetico.csv",
                    HERE / "calib" / "polar_tunel_sintetico.csv")
    c = json.loads((HERE / "calib" / "calibration_record.json").read_text(encoding="utf-8"))
    c["data"]["file"]["path"] = "polar_tunel_sintetico.csv"
    c["study"]["path"] = "examples/calibration/polar_tunel_sintetico.yaml"
    _dump(HERE / "calib" / "calibration_record.json", c)
    for f in ("provenance.json", "residuals.csv"):
        (HERE / "calib" / f).unlink(missing_ok=True)
    for sub in ("uq", "mdo", "vv", "calib"):
        for f in (HERE / sub).glob("*.md"):
            f.unlink()
        (HERE / sub / "provenance.json").unlink(missing_ok=True)

    from acdt.core import review as R
    r = R.report(HERE, "PDR", now=FIX)
    (HERE / "relatorio_pdr.golden.md").write_text(R.to_markdown(r), encoding="utf-8")


if __name__ == "__main__":
    generate()
