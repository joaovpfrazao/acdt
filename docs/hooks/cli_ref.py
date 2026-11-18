# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Hook do MkDocs: substitui ``<!-- acdt-cli-help -->`` pela ajuda de todos os comandos do ``acdt``."""
from __future__ import annotations

import argparse
from typing import Any

MARK = "<!-- acdt-cli-help -->"


def _help_md() -> str:
    from acdt import cli

    p = cli.build_parser()
    p.formatter_class = argparse.RawDescriptionHelpFormatter
    out = ["## acdt", "", "```text", p.format_help().rstrip(), "```", ""]
    act = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))
    helps = {c.dest: c.help for c in act._choices_actions}
    out += ["## Comandos", "", "| comando | descrição |", "|---|---|"]
    out += [f"| [`{n}`](#acdt-{n}) | {(helps.get(n) or '').replace('|', '/')} |" for n in act.choices]
    out.append("")
    for n, sp in act.choices.items():
        out += [f"### acdt {n}", "", "```text", sp.format_help().rstrip(), "```", ""]
    return "\n".join(out)


def on_page_markdown(markdown: str, page: Any, config: Any, files: Any) -> str:
    if MARK in markdown:
        return markdown.replace(MARK, _help_md())
    return markdown
