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
from acdt.core.review.criteria import CRITERIA, GATES, STANDARD
from acdt.core.review.evaluate import verdict

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
    assert set(GATES) == {"SRR", "PDR", "CDR"} and STANDARD["id"] == "NPR 7123.1D"
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
