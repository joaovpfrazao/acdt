# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Contrato da CLI (docs/API.md §4): --version, --help em todos os comandos, --json e códigos de saída."""
from __future__ import annotations

import json

import pytest

import acdt
from acdt import api
from acdt import cli


def _subparsers(p):
    import argparse
    for a in p._actions:
        if isinstance(a, argparse._SubParsersAction):
            return a.choices
    return {}


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert acdt.__version__ in out and api.API_VERSION in out


def test_every_command_has_help_and_common_flags(capsys):
    subs = _subparsers(cli.build_parser())
    assert len(subs) >= 30
    for name, sp in subs.items():
        with pytest.raises(SystemExit) as e:
            cli.main([name, "--help"])
        assert e.value.code == 0, name
        txt = capsys.readouterr().out
        assert f"acdt {name}" in txt and "--json" in txt and "--debug" in txt, name
    top = cli.build_parser().format_help()
    for code in cli.EXIT_CODES:
        assert f"{code} " in top


def test_every_command_has_a_one_line_help():
    p = cli.build_parser()
    import argparse
    act = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))
    helps = {c.dest: c.help for c in act._choices_actions}
    missing = [n for n in act.choices if not helps.get(n)]
    assert not missing, f"comandos sem help: {missing}"


def test_json_envelope_and_text_to_stderr(tmp_path, capsys):
    code = cli.main(["vv", "--case", "ATM-ISA-SL", "-o", str(tmp_path / "vv"), "--json"])
    cap = capsys.readouterr()
    env = json.loads(cap.out)
    assert code == 0 and env["schema"] == "acdt.cli/1" and env["exit_code"] == 0
    assert env["command"] == "vv" and env["api"] == api.API_VERSION
    assert env["result"]["counts"]["passa"] == 1
    assert any(f.endswith("vv_report.json") for f in env["files"])
    assert "acdt vv:" in cap.err  # texto humano não suja o JSON


def test_usage_error_is_2(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["size"])  # falta o argumento obrigatório
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e:
        cli.main(["comando-que-nao-existe"])
    assert e.value.code == 2


def test_internal_error_is_4_with_json(monkeypatch, capsys):
    def boom(a):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(cli, "_cmd_vv", boom)
    code = cli.main(["vv", "--list", "--json"])
    cap = capsys.readouterr()
    assert code == 4 and json.loads(cap.out)["exit_code"] == 4
    assert "falha simulada" in cap.err and "--debug" in cap.err
    code = cli.main(["vv", "--list", "--debug"])
    assert code == 4 and "Traceback" in capsys.readouterr().err


def test_exit_codes_documented():
    from pathlib import Path
    doc = (Path(__file__).resolve().parents[1] / "docs" / "API.md").read_text(encoding="utf-8")
    for code in cli.EXIT_CODES:
        assert f"| {code} |" in doc
