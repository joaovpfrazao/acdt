# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Relatórios de revisão de projeto (acdt report; docs/RELATORIOS.md): estrutura, lógica do veredito (incluindo
dados em falta), dispensas/adaptações, rastreabilidade, figuras, CLI/API e o relatório de referência (golden) do
exemplo analítico pequeno em tests/data/review_small (gerado por gerar.py)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from acdt import api, cli
from acdt.core import review as R
from acdt.core.review.criteria import CRITERIA, DEFAULT_REQUIRED_LEVEL, GATES, STANDARD
from acdt.core.review.evaluate import verdict
from acdt.core.review.figures import draw_plan, histogram_plan, pareto_plan

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "data" / "review_small"
FIX = "2026-11-18T00:00:00+00:00"


@pytest.fixture()
def proj(tmp_path):
    d = tmp_path / "proj"
    shutil.copytree(FIXTURE, d, ignore=shutil.ignore_patterns("gerar.py", "*.golden.md", "__pycache__"))
    return d


def _crit(r, cid):
    return next(c for c in r["criteria"] if c["id"] == cid)


# ------------------------------------------------------------------------------------------------ golden
def test_golden_markdown_of_small_example():
    r = R.report(FIXTURE, "PDR", now=FIX)
    got = R.to_markdown(r)
    want = (FIXTURE / "relatorio_pdr.golden.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert got == want, "relatório mudou: rever e regenerar com python tests/data/review_small/gerar.py"


# --------------------------------------------------------------------------------------------- estrutura
def test_criteria_declared_and_cited():
    assert set(GATES) == {"SRR", "PDR", "CDR", "MDR", "TRR", "PRR"} and STANDARD["id"] == "NPR 7123.1D"
    for g, cs in CRITERIA.items():
        ids = [c.id for c in cs]
        assert len(ids) == len(set(ids)), g
        assert any(c.check for c in cs) and any(c.check is None for c in cs), g
        for c in cs:
            assert c.gate == g and c.phase in ("entrada", "sucesso") and len(c.quote) > 20
            assert c.check is None or c.check in R.build.__globals__["evaluate_criteria"].__globals__["CHECKS"]
            assert GATES[g]["table"] in c.ref


def test_report_structure_and_json(proj, tmp_path):
    r = R.report(proj, "pdr", tmp_path / "out", now=FIX)
    assert r["schema"] == "acdt.review/1" and r["gate"] == "PDR"
    for k in ("verdict", "criteria", "requirements", "design", "fidelity", "open_items", "uq", "mdo", "vv",
              "calibration", "traceability", "figures", "standard"):
        assert k in r, k
    assert r["standard"]["table"].startswith("Tabela G-6")
    names = sorted(Path(f).name for f in r["files"])
    assert names == ["relatorio_pdr.html", "relatorio_pdr.json", "relatorio_pdr.md"]
    j = json.loads((tmp_path / "out" / "relatorio_pdr.json").read_text(encoding="utf-8"))
    assert j["verdict"] == r["verdict"]
    html = (tmp_path / "out" / "relatorio_pdr.html").read_text(encoding="utf-8")
    assert "<table>" in html and "NÃO PRONTO" in html
    # nao_avaliado nunca conta como passa; a fração avaliada exclui-o
    rq = r["requirements"]
    assert rq["counts"]["nao_avaliado"] == 1 and rq["fracao_avaliada"] == pytest.approx(0.75)
    assert {i["id"] for i in r["open_items"] if i["categoria"] == "requisito"} == {"R2", "R3", "R4"}
    assert r["uq"]["studies"][0]["requirements"][0]["estado"] == "prob_passa"
    assert r["mdo"]["studies"][0]["chosen"]["id"] == 4


# ------------------------------------------------------------------------------------------------ veredito
def _rows(*sts, auto=True):
    return [{"id": f"C{i}", "automatico": auto, "status": s} for i, s in enumerate(sts)]


def test_verdict_logic():
    assert verdict(_rows("cumpre", "cumpre"))["status"] == "pronto"
    assert verdict(_rows("cumpre", "insuficiente"))["status"] == "insuficiente"
    v = verdict(_rows("insuficiente", "nao_cumpre", "cumpre"))
    assert v["status"] == "nao_pronto" and v["motivos"] == ["C1"]
    assert verdict(_rows("revisao_humana", auto=False))["status"] == "insuficiente"  # nada automático
    assert verdict(_rows("cumpre", "dispensado"))["status"] == "pronto"
    assert verdict(_rows("cumpre") + _rows("revisao_humana", auto=False))["counts"]["revisao_humana"] == 1


def test_missing_data_is_insuficiente_never_pass(proj):
    for sub in ("uq", "mdo", "vv", "calib"):
        shutil.rmtree(proj / sub)
    for f in ("verification_matrix.json", "provenance.json"):
        (proj / f).unlink()
    db = json.loads((proj / "design.json").read_text(encoding="utf-8"))
    db["verification"] = None
    (proj / "design.json").write_text(json.dumps(db), encoding="utf-8")
    r = R.report(proj, "PDR", criteria={"required_level": {"PDR": "L0"}}, now=FIX)
    st = {c["id"]: c["status"] for c in r["criteria"]}
    for cid in ("PDR-E01", "PDR-E02", "PDR-S03", "PDR-S04", "PDR-S05", "PDR-S07", "PDR-S08", "PDR-E09"):
        assert st[cid] == "insuficiente", cid
    assert st["PDR-S06"] == "cumpre"
    assert r["verdict"]["status"] == "insuficiente"
    assert not r["requirements"]["present"]
    md = R.to_markdown(r)
    assert "conformidade desconhecida" in md and "Sem estudo de incerteza" in md


def test_unevaluated_requirement_blocks_pass(proj):
    m = json.loads((proj / "verification_matrix.json").read_text(encoding="utf-8"))
    for row in m["rows"]:
        row["status"] = "passa" if row["id"] != "R4" else "desconhecido"
    (proj / "verification_matrix.json").write_text(json.dumps(m), encoding="utf-8")
    r = R.report(proj, "PDR", now=FIX)
    c = _crit(r, "PDR-E01")
    assert c["status"] == "insuficiente" and "R4" in c["detail"]


def test_srr_ready_and_cdr_not(proj):
    srr = R.report(proj, "SRR", now=FIX)
    assert {c["id"]: c["status"] for c in srr["criteria"]}["SRR-S04"] == "cumpre"  # feasible = True
    cdr = R.report(proj, "CDR", now=FIX)
    assert cdr["verdict"]["status"] == "nao_pronto"
    assert _crit(cdr, "CDR-S06")["status"] == "insuficiente"  # só calibração sintética: não é ensaio
    assert _crit(cdr, "CDR-E07")["status"] == "nao_cumpre"    # disciplinas abaixo de L2


def test_calibration_real_vs_synthetic(proj):
    p = proj / "calib" / "calibration_record.json"
    c = json.loads(p.read_text(encoding="utf-8"))
    c["synthetic"] = False
    p.write_text(json.dumps(c), encoding="utf-8")
    assert _crit(R.report(proj, "CDR", now=FIX), "CDR-S06")["status"] == "cumpre"
    c["decision"] = "nao_aplicar"
    p.write_text(json.dumps(c), encoding="utf-8")
    assert _crit(R.report(proj, "CDR", now=FIX), "CDR-S06")["status"] == "nao_cumpre"


def test_waivers_and_tailoring_need_justification(proj):
    r = R.report(proj, "PDR", criteria={"waivers": [{"id": "R3", "justificacao": "dispensa de teste"}],
                                        "tailoring": [{"criterio": "PDR-S08", "justificacao": "sem trade"}]}, now=FIX)
    e01 = _crit(r, "PDR-E01")
    assert e01["status"] == "insuficiente" and "dispensa" in e01["detail"]  # R4 continua por avaliar
    assert _crit(r, "PDR-S08")["status"] == "dispensado"
    with pytest.raises(R.ReviewInputError):
        R.report(proj, "PDR", criteria={"waivers": [{"id": "R3"}]})
    with pytest.raises(R.ReviewInputError):
        R.report(proj, "PDR", criteria={"tailoring": [{"criterio": "XYZ", "justificacao": "x"}]})
    bad = proj / "crit.yaml"
    bad.write_text("campo_errado: 1\n", encoding="utf-8")
    with pytest.raises(R.ReviewInputError):
        R.report(proj, "PDR", criteria=bad)


def test_traceability_detects_changed_evidence(proj):
    r0 = R.report(proj, "PDR", now=FIX)
    assert _crit(r0, "PDR-E09")["status"] == "cumpre"
    rj = proj / "result.json"
    rj.write_text(rj.read_text(encoding="utf-8").replace("120000000.0", "130000000.0"), encoding="utf-8")
    r = R.report(proj, "PDR", now=FIX)
    t = next(x for x in r["traceability"] if x["path"] == "result.json")
    assert t["status"] == "difere"
    assert _crit(r, "PDR-E09")["status"] == "nao_cumpre"
    assert any(i["categoria"] == "rastreabilidade" for i in r["open_items"])


def test_dirty_git_breaks_baseline(proj):
    p = proj / "provenance.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["acdt"]["git"]["dirty"] = True
    p.write_text(json.dumps(d), encoding="utf-8")
    assert _crit(R.report(proj, "PDR", now=FIX), "PDR-E09")["status"] == "nao_cumpre"


def test_figures_embedded(proj, tmp_path):
    png = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
    (proj / "diagrama.png").write_bytes(png)
    r = R.report(proj, "SRR", tmp_path / "o", now=FIX)
    assert r["figures"][0]["path"] == "diagrama.png"
    assert (tmp_path / "o" / "figuras" / "diagrama.png").read_bytes() == png
    assert "data:image/png;base64," in (tmp_path / "o" / "relatorio_srr.html").read_text(encoding="utf-8")
    assert "](figuras/diagrama.png)" in (tmp_path / "o" / "relatorio_srr.md").read_text(encoding="utf-8")
    names = {Path(f).name for f in r["files"]}
    assert names == {"relatorio_srr.html", "relatorio_srr.json", "relatorio_srr.md"}


def test_pareto_from_stored_points_and_histogram_without_samples(proj, tmp_path):
    r = R.report(proj, "PDR", tmp_path / "out", now=FIX)
    plans = {p["kind"]: p for p in r["figure_plans"]["plans"]}
    pareto, hist = plans["pareto"], plans["histograma_uq"]
    assert pareto["veredicto"] == "validado" and pareto["calibracao"] == "nao_aplicar"
    assert pareto["n"] == 9 and pareto["n_front"] == 9 and pareto["file"] == "mdo/mdo.json"
    assert {p["id"] for p in pareto["points"]} == set(pareto["front"])
    png = tmp_path / "out" / "figuras" / pareto["out_name"]
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert hist["veredicto"] == "nao_avaliado" and "amostras" in hist["reason"]
    assert not (tmp_path / "out" / "figuras" / hist["out_name"]).exists()
    md = (tmp_path / "out" / "relatorio_pdr.md").read_text(encoding="utf-8")
    assert "Nenhuma figura já produzida nas pastas do projeto." in md
    assert "não avaliado" in md and "veredicto validado" in md
    assert pareto["out_name"] not in {Path(f).name for f in r["files"]}


def test_incomplete_records_are_not_drawn(tmp_path):
    bad = {"objectives": [{"metric": "f1", "sense": "min"}, {"metric": "f2", "sense": "min"}],
           "evaluations": [{"id": 0, "objectives": {"f1": 1.0, "f2": float("nan")}},
                           {"id": 1, "objectives": {"f1": True, "f2": 1.0}}],
           "pareto": [0]}
    plan = pareto_plan(bad, "mdo/mdo.json", "abc")
    assert plan["veredicto"] == "nao_avaliado" and plan["points"] == []
    missing = pareto_plan({"objectives": [{"metric": "f1", "sense": "min"}, {"metric": "f2", "sense": "min"}],
                           "evaluations": [{"id": 0, "objectives": {"f1": 1.0, "f2": 2.0}}],
                           "pareto": [0, 9]}, "a/mdo.json", None)
    assert missing["veredicto"] == "nao_avaliado" and "9" in missing["reason"]
    dest = tmp_path / "no.png"
    draw_plan(plan, dest)
    assert not dest.exists()
    assert pareto_plan(bad, "mdo/mdo.json", None)["out_name"] != pareto_plan(bad, "outro/mdo.json", None)["out_name"]
    none = histogram_plan({"n": 200}, "uq/uq.json", None)
    assert none["veredicto"] == "nao_avaliado" and none["values"] == []
    partial = histogram_plan({"samples": [{"ok": True, "metrics": {"y": 1.0}},
                                          {"ok": False, "metrics": {"y": 0.0}}]}, "uq/uq.json", None)
    assert partial["veredicto"] == "nao_avaliado"
    short = histogram_plan({"samples": [{"ok": True, "metrics": {"y": 1.0}},
                                        {"ok": True, "metrics": {"y": 2.0}}], "n_ok": 3}, "uq/uq.json", None)
    assert short["veredicto"] == "nao_avaliado" and "n_ok" in short["reason"]
    good = histogram_plan({"samples": [{"ok": True, "metrics": {"y": 1.0}},
                                       {"ok": True, "metrics": {"y": 2.5}}], "n_ok": 2}, "uq/uq.json", None)
    assert good["veredicto"] == "validado" and good["calibracao"] == "nao_aplicar" and good["values"] == [1.0, 2.5]
    draw_plan(good, tmp_path / "h.png")
    assert (tmp_path / "h.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_mdr_trr_prr_transcribed(proj):
    assert DEFAULT_REQUIRED_LEVEL["MDR"] == DEFAULT_REQUIRED_LEVEL["TRR"] == DEFAULT_REQUIRED_LEVEL["PRR"] == "L0"
    for gate, banned in (("MDR", "fidelidade_disciplinas"), ("TRR", "fidelidade_disciplinas"),
                         ("PRR", "fidelidade_disciplinas")):
        r = R.report(proj, gate, now=FIX)
        assert r["gate"] == gate and r["fidelity"]["required_level"] == "L0"
        checks = [c["check"] for c in r["criteria"]]
        assert banned not in checks
        assert any(c is None for c in checks) and any(c for c in checks)
        assert "Tabela G-" in r["standard"]["table"]
    assert "typically greater than three" in GATES["PRR"]["purpose"]
    assert "single-project programs" in GATES["MDR"]["purpose"]
    prr_tbd = next(c.quote for c in CRITERIA["PRR"] if c.id == "PRR-S06")
    trr_tbd = next(c.quote for c in CRITERIA["TRR"] if c.id == "TRR-S06")
    assert prr_tbd.startswith("TBD and TBR items are clearly identified, with")
    assert trr_tbd.startswith("TBD and TBR items are clearly identified with")


def test_bad_inputs(tmp_path, proj):
    with pytest.raises(R.ReviewInputError):
        R.report(tmp_path / "nada", "PDR")
    with pytest.raises(ValueError):
        R.report(proj, "XDR")
    with pytest.raises(R.ReviewInputError):
        R.report(proj, "PDR", uq=[proj / "mdo" / "mdo.json"])  # esquema errado dado explicitamente


def test_pdf_optional(proj, tmp_path):
    from acdt.core.review.render import pdf_available
    if pdf_available():
        r = R.report(proj, "SRR", tmp_path / "p", pdf=True, now=FIX)
        assert any(f.endswith(".pdf") for f in r["files"])
    else:
        with pytest.raises(RuntimeError):
            R.report(proj, "SRR", tmp_path / "p", pdf=True, now=FIX)


# -------------------------------------------------------------------------------------------- CLI e API
def test_cli_json_and_exit_codes(proj, tmp_path, capsys):
    code = cli.main(["report", str(proj), "--level", "pdr", "-o", str(tmp_path / "rel"), "--json"])
    env = json.loads(capsys.readouterr().out)
    assert code == 1 and env["command"] == "report" and env["exit_code"] == 1
    assert env["result"]["verdict"]["status"] == "nao_pronto" and env["result"]["standard"] == "NPR 7123.1D"
    assert any(f.endswith("relatorio_pdr.md") for f in env["files"])
    assert cli.main(["report", str(proj), "--level", "PDR", "-o", str(proj)]) == 2  # sobreporia a proveniência
    assert cli.main(["report", str(tmp_path / "nada"), "--level", "SRR", "-o", str(tmp_path / "x")]) == 2
    code = cli.main(["report", str(proj), "--level", "PDR", "-o", str(tmp_path / "r2"), "--no-discover",
                     "--criteria", str(_write(tmp_path / "c.yaml", "required_level: {PDR: L0}\n"))])
    assert code == 1  # R3 em falha decide, mesmo sem registos


def _write(p: Path, txt: str) -> Path:
    p.write_text(txt, encoding="utf-8")
    return p


def test_api_report_and_errors(proj):
    assert "report" in api.__all__ and "ReviewInputError" in api.errors()
    r = api.report(proj, "SRR")
    assert r["verdict"]["status"] in R.VERDICTS and "files" not in r


def test_aircraft_profile_registered():
    from acdt.core.review.profile import profile_for
    p = profile_for("aircraft")
    assert "aerodinamica" in p.primary_disciplines and "weights.W0_kg" in p.headline
    assert profile_for("dominio_inexistente").primary_disciplines == ()
