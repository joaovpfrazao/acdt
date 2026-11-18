"""Biblioteca de V&V (``acdt vv``; docs/VV.md): registo, regras de estado, relatório versionado, casos baratos."""
from __future__ import annotations

import json
import math

import pytest

from acdt.core import vv


def test_registry_cases_have_citation_tolerance_and_known_kinds():
    cs = vv.cases()
    assert len(cs) >= 20
    ids = [c.id for c in cs]
    assert len(ids) == len(set(ids))
    for c in cs:
        assert c.kind in vv.KINDS and c.cost in vv.COSTS and c.problem and c.title
        for r in c.references:
            assert r.citation.strip() and (r.tol_abs > 0 or r.tol_rel > 0)
            assert r.tol_source.strip(), (c.id, r.quantity)
    assert {"atmosfera", "sensibilidade", "mdo", "estruturas", "em", "aerodinamica", "cargas",
            "dimensionamento"} <= {c.discipline for c in cs}
    assert any(c.kind == "validacao" for c in cs)


def test_compare_rules():
    r = vv.Reference("x", 10.0, "m", "fonte", tol_rel=0.1)
    assert vv.compare(r, 10.9)["status"] == "passa"
    assert vv.compare(r, 11.1)["status"] == "falha"
    assert vv.compare(r, None)["status"] == "desconhecido"
    assert vv.compare(r, math.nan)["status"] == "desconhecido"  # desconhecido ≠ zero
    lo = vv.Reference("hv", 1.0, "", "fonte", tol_abs=0.1, kind="min")
    assert vv.compare(lo, 0.95)["status"] == "passa" and vv.compare(lo, 0.85)["status"] == "falha"
    hi = vv.Reference("g", 0.0, "", "fonte", tol_abs=0.02, kind="max")
    assert vv.compare(hi, 0.01)["status"] == "passa" and vv.compare(hi, 0.03)["status"] == "falha"


def test_register_rejects_missing_citation_or_tolerance():
    with pytest.raises(ValueError):
        vv.register(vv.Case("X-1", "d", "t", "p", "verificacao", (vv.Reference("a", 1, "", "", tol_abs=1),),
                            lambda: {}, "f"))
    with pytest.raises(ValueError):
        vv.register(vv.Case("X-2", "d", "t", "p", "verificacao", (vv.Reference("a", 1, "", "c"),), lambda: {}, "f"))
    with pytest.raises(ValueError):
        vv.register(vv.Case("X-3", "d", "t", "p", "teste", (vv.Reference("a", 1, "", "c", tol_abs=1),),
                            lambda: {}, "f"))


def test_missing_tool_and_errors_never_pass():
    ref = (vv.Reference("a", 1.0, "", "c", tol_abs=0.1),)
    c1 = vv.Case("T-TOOL", "d", "t", "p", "verificacao", ref, lambda: {"a": 1.0}, "f",
                 requires=("ferramenta-que-nao-existe-xyz",))
    r1 = vv.run_case(c1)
    assert r1["status"] == "nao_avaliado" and "em falta" in r1["message"]

    def boom() -> dict[str, float]:
        raise RuntimeError("partiu")
    r2 = vv.run_case(vv.Case("T-ERR", "d", "t", "p", "verificacao", ref, boom, "f"))
    assert r2["status"] == "desconhecido" and "partiu" in r2["message"]

    def na() -> dict[str, float]:
        raise vv.NotAssessed("sem dados")
    assert vv.run_case(vv.Case("T-NA", "d", "t", "p", "verificacao", ref, na, "f"))["status"] == "nao_avaliado"
    r4 = vv.run_case(vv.Case("T-NONE", "d", "t", "p", "verificacao", ref, lambda: {}, "f"))
    assert r4["status"] == "desconhecido"


@pytest.mark.parametrize("cid", [c.id for c in vv.cases() if c.cost == "barato"])
def test_cheap_case_passes(cid):
    r = vv.run_case({c.id: c for c in vv.cases()}[cid])
    if r["status"] == "nao_avaliado":
        pytest.skip(r["message"])
    assert r["status"] == "passa", r


def test_report_versioned_with_provenance(tmp_path):
    rep = vv.run(ids=["ATM-ISA-SL", "STR-SP8007-KNOCKDOWN"])
    assert rep["schema"] == vv.SCHEMA and rep["registry_version"] == vv.REGISTRY_VERSION
    assert len(rep["registry_fingerprint"]) == 64
    assert rep["counts"]["passa"] == 2 and rep["provenance"]["schema"] == "acdt.provenance/1"
    files = vv.write(rep, tmp_path)
    d = json.loads(files[0].read_text(encoding="utf-8"))
    assert {c["id"] for c in d["cases"]} == {"ATM-ISA-SL", "STR-SP8007-KNOCKDOWN"}
    md = files[1].read_text(encoding="utf-8")
    assert "ISO 2533" in md and "SP-8007" in md and vv.REGISTRY_VERSION in md


def test_cost_filter_marks_expensive_cases_not_assessed():
    rep = vv.run(disciplines=["dimensionamento"], max_cost="barato")
    row = {c["id"]: c for c in rep["cases"]}["SIZ-C172S"]
    assert row["status"] == "nao_avaliado" and "--cost medio" in row["message"]
    with pytest.raises(KeyError):
        vv.select(ids=["NAO-EXISTE"])


def test_fingerprint_changes_with_definitions():
    cs = vv.cases()
    f0 = vv.registry_fingerprint(cs)
    assert f0 == vv.registry_fingerprint(list(reversed(cs)))
    assert f0 != vv.registry_fingerprint(cs[1:])


def test_cli_vv(tmp_path):
    from acdt.cli import main

    assert main(["vv", "--case", "ATM-ISA-11KM", "-o", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "vv_report.json").is_file() and (tmp_path / "o" / "vv_report.md").is_file()
    assert main(["vv", "--case", "NAO-EXISTE", "-o", str(tmp_path / "x")]) == 2
    assert main(["vv", "--list"]) == 0


@pytest.mark.slow
def test_c172_validation_case():
    r = vv.run_case({c.id: c for c in vv.cases()}["SIZ-C172S"])
    assert r["status"] == "passa", r
