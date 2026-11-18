"""Proveniência (acdt.core.provenance): estrutura do registo, hash canónico, âmbito de corrida, comparação.
Os testes não dependem da máquina: verificam a estrutura e usam binários falsos criados no tmp_path."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from acdt.core import provenance as P


def _fake_bin(tmp_path: Path, name: str, payload: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(payload)
    return p


def test_canonical_hash_ignores_key_order_and_yaml_formatting(tmp_path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("name: x\nmass: 150.0\nlist: [1, 2]\n", encoding="utf-8")
    b.write_text("# comentário\nlist:\n  - 1\n  - 2\nmass: 150.0\nname:   x\n", encoding="utf-8")
    ha, hb = P.hash_input(a), P.hash_input(b)
    assert ha["kind"] == hb["kind"] == "yaml-canonical"
    assert ha["sha256"] == hb["sha256"]
    assert ha["sha256_bytes"] != hb["sha256_bytes"]
    b.write_text("name: x\nmass: 150.1\nlist: [1, 2]\n", encoding="utf-8")
    assert P.hash_input(b)["sha256"] != ha["sha256"]
    assert P.canonical_hash({"b": 1, "a": [1.0, "é"]}) == P.canonical_hash({"a": [1.0, "é"], "b": 1})


def test_non_yaml_input_and_invalid_json_fall_back_to_bytes(tmp_path):
    f = tmp_path / "x.avl"
    f.write_text("SURFACE\n", encoding="utf-8")
    assert P.hash_input(f)["kind"] == "bytes"
    j = tmp_path / "bad.json"
    j.write_text("{not json", encoding="utf-8")
    r = P.hash_input(j)
    assert r["kind"] == "bytes" and "note" in r


def test_tool_identity_hashes_binary_and_distinguishes_builds(tmp_path):
    lin = P.tool_identity("avl", _fake_bin(tmp_path, "avl_linux", b"ELF..."), probe=False)
    win = P.tool_identity("avl", _fake_bin(tmp_path, "avl.exe", b"MZ..."), probe=False)
    assert lin["found"] and lin["sha256"] and lin["sha256"] != win["sha256"]
    assert lin["version"] is None and "SHA-256" in lin["version_note"]
    assert P.tool_identity("su2", None)["found"] is False
    assert P.tool_identity("su2", tmp_path / "nao_existe")["found"] is False


def test_collect_structure_is_complete(tmp_path):
    inp = tmp_path / "m.yaml"
    inp.write_text("a: 1\n", encoding="utf-8")
    rec = P.collect(entry_point="teste", argv=["x"], inputs=[inp], seeds={"seed": 3},
                    tools={"avl": _fake_bin(tmp_path, "avl", b"x")}, probe_versions=False)
    assert rec["schema"] == P.SCHEMA
    for k in ("created", "entry_point", "acdt", "python", "packages", "platform", "tools", "inputs", "seeds"):
        assert k in rec
    assert rec["created"]["utc"].endswith("+00:00")
    assert set(rec["acdt"]["git"]) >= {"commit", "dirty", "branch"}
    assert rec["acdt"]["version"]
    assert "numpy" in rec["packages"]
    assert rec["platform"]["system"]
    assert rec["tools"]["avl"]["sha256"]
    assert rec["inputs"][0]["kind"] == "yaml-canonical"
    assert rec["seeds"] == {"seed": 3}
    json.dumps(rec)  # serializável


def test_timestamps_utc_and_lisbon():
    import datetime as dt

    t = P.timestamps(dt.datetime(2026, 7, 1, 12, 0, tzinfo=dt.timezone.utc))
    assert t["utc"] == "2026-07-01T12:00:00+00:00"
    if t["europe_lisbon"] is not None:  # sem tzdata (Windows) fica None, não inventado
        assert t["europe_lisbon"] == "2026-07-01T13:00:00+01:00"


def test_run_scope_writes_dir_and_file_sidecars(tmp_path, monkeypatch):
    monkeypatch.setenv("ACDT_PROVENANCE", "1")
    inp = tmp_path / "m.yaml"
    inp.write_text("a: 1\n", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    fo = tmp_path / "res.json"
    with P.run_scope("acdt teste", argv=["teste"], inputs=[inp], seeds={"seed": 7}):
        P.tool_used("avl", _fake_bin(tmp_path, "avl", b"bin"))
        (out / "result.json").write_text('{"W0": 1}', encoding="utf-8")
        (out / "sub").mkdir()
        (out / "sub" / "x.txt").write_text("x", encoding="utf-8")
        fo.write_text("{}", encoding="utf-8")
        P.note_output(out)
        P.note_output(fo)
        P.note_output(tmp_path / "nunca_escrito")
        assert not (out / "provenance.json").exists()  # só no fim da corrida
    d = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
    assert d["entry_point"]["command"] == "acdt teste" and d["seeds"] == {"seed": 7}
    assert "avl" in d["tools"] and d["inputs"][0]["path"].endswith("m.yaml")
    paths = {e["path"]: e for e in d["outputs"]}
    assert set(paths) == {"result.json", "sub/x.txt"}
    assert paths["result.json"]["written_this_run"] and len(paths["result.json"]["sha256"]) == 64
    assert (tmp_path / "res.provenance.json").exists()
    assert P.load(fo)["schema"] == P.SCHEMA
    assert P.load(out)["schema"] == P.SCHEMA
    assert (out / "result.json").read_text(encoding="utf-8") == '{"W0": 1}'  # resultado intacto


def test_note_output_outside_scope_writes_immediately_and_can_be_disabled(tmp_path, monkeypatch):
    out = tmp_path / "o"
    out.mkdir()
    (out / "a.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("ACDT_PROVENANCE", "0")
    assert P.note_output(out) is None and not (out / "provenance.json").exists()
    monkeypatch.setenv("ACDT_PROVENANCE", "1")
    p = P.note_output(out, entry_point="lib")
    assert p == out / "provenance.json" and json.loads(p.read_text(encoding="utf-8"))["entry_point"]["command"] == "lib"


def test_load_reads_run_json_and_rejects_unknown(tmp_path):
    rec = P.collect(entry_point="mcp x", probe_versions=False)
    (tmp_path / "run.json").write_text(json.dumps({"run_id": "r", "provenance": rec}), encoding="utf-8")
    assert P.load(tmp_path)["entry_point"]["command"] == "mcp x"
    with pytest.raises(FileNotFoundError):
        P.load(tmp_path / "nada.json")


def _base() -> dict:
    return {"schema": P.SCHEMA, "acdt": {"version": "0.1.0", "git": {"commit": "abc", "dirty": False}},
            "python": {"version": "3.13.0"}, "packages": {"numpy": "2.1"},
            "platform": {"system": "Linux", "machine": "x86_64", "release": "6"},
            "tools": {"avl": {"path": "/a/avl", "sha256": "1" * 64, "version": None}},
            "inputs": [{"path": "/x/m.yaml", "sha256": "f" * 64}], "seeds": {"seed": 0},
            "entry_point": {"command": "acdt size", "argv": ["size", "m.yaml"]}}


def test_compare_identical_and_info_only():
    a, b = _base(), _base()
    b["tools"]["avl"]["path"] = "/outro/avl"
    r = P.compare(a, b)
    assert r["identicos"] and [d["peso"] for d in r["diferencas"]] == ["info"]
    assert "Mesma proveniência" in P.explain(r)


def test_compare_explains_windows_vs_linux_avl_dirty_and_inputs():
    a, b = _base(), _base()
    b["platform"]["system"] = "Windows"
    b["platform"]["machine"] = "AMD64"
    b["tools"]["avl"]["sha256"] = "2" * 64
    b["acdt"]["git"]["dirty"] = True
    b["inputs"][0]["sha256"] = "e" * 64
    b["seeds"] = {"seed": 1}
    r = P.compare(a, b)
    assert not r["identicos"]
    campos = {d["campo"] for d in r["diferencas"]}
    assert {"platform.system", "tools.avl.sha256", "acdt.git.dirty", "inputs.m.yaml", "seeds"} <= campos
    txt = P.explain(r)
    assert "binário de avl diferente" in txt and "não commitadas" in txt and "[aviso]" in txt


def test_compare_tool_only_in_one_run():
    a, b = _base(), _base()
    b["tools"] = {}
    r = P.compare(a, b)
    assert any(d["campo"] == "tools.avl" and d["peso"] == "alto" for d in r["diferencas"])


def test_hifi_tools_run_records_solver_behind_mpirun(tmp_path, monkeypatch):
    from acdt.domains.aircraft.hifi import tools

    monkeypatch.setenv("ACDT_PROVENANCE", "1")
    fake_su2 = _fake_bin(tmp_path, "SU2_CFD", b"su2")
    with P.run_scope("teste") as sc:
        tools._record_tools(["/usr/bin/mpirun", "-n", "4", str(fake_su2), "case.cfg"])
        tools._record_tools([sys.executable, "/x/vsp_build.py", "spec.json"])
    assert {"mpirun", "SU2_CFD"} <= set(sc.tools)
    assert "python (vsp_build.py)" in sc.tools


def test_cli_size_writes_provenance_and_diff(tmp_path, monkeypatch, capsys):
    """A CLI escreve provenance.json na pasta de saída; ``provenance diff`` contra si própria dá 0."""
    from acdt.cli import main

    monkeypatch.setenv("ACDT_PROVENANCE", "1")
    mission = Path(__file__).resolve().parents[1] / "examples" / "uav_overconstrained.yaml"
    out = tmp_path / "o"
    main(["size", str(mission), "-o", str(out), "--no-systems"])
    rec = P.load(out)
    assert rec["entry_point"]["command"] == "acdt size"
    assert any(i["path"].endswith("uav_overconstrained.yaml") for i in rec["inputs"])
    capsys.readouterr()
    assert main(["provenance", "diff", str(out), str(out)]) == 0
    assert "Mesma proveniência" in capsys.readouterr().out
    assert main(["provenance", "show", str(out)]) == 0


def test_compare_dirty_trees():
    a, b = _base(), _base()
    for r in (a, b):
        r["acdt"]["git"].update(dirty=True, dirty_diff_sha256="d" * 64)
    r = P.compare(a, b)
    assert r["identicos"] and not r["reprodutivel"] and len(r["avisos_reprodutibilidade"]) == 2
    b["acdt"]["git"]["dirty_diff_sha256"] = "c" * 64
    assert not P.compare(a, b)["identicos"]
    b["acdt"]["git"]["dirty"] = False
    assert any(d["campo"] == "acdt.git.dirty" for d in P.compare(a, b)["diferencas"])
