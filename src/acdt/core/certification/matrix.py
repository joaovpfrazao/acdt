"""Compliance matrix: applicable paragraphs × means of compliance × acdt evidence × automatic status.

Status rule (conceptual-design level, not a substitute for the authority's acceptance):

* ``non-compliant`` — an acdt analysis evaluated a numeric criterion and it fails;
* ``needs-test``   — the analysis passes (or reports the determined value) but the means of compliance includes
  test (flight / ground / structural / GVT), so final compliance needs the test;
* ``compliant``    — the analysis passes (or the required determination is made) and the means of compliance is
  analysis/inspection/similarity only;
* ``open``         — no acdt evidence yet (or only qualitative), the paragraph remains to be addressed.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

import yaml

from .basis import select_basis
from .evidence import EVIDENCE

_CAT = Path(__file__).resolve().parents[1] / "data" / "cert_catalogue.yaml"
STATUSES = ("compliant", "needs-test", "non-compliant", "open")
STATUS_PT = {"compliant": "conforme", "needs-test": "requer ensaio", "non-compliant": "não conforme",
             "open": "em aberto"}


@lru_cache(maxsize=1)
def catalogue() -> dict:
    return yaml.safe_load(_CAT.read_text(encoding="utf-8"))["bases"]


def _applies(item: dict, env: dict) -> bool:
    w = item.get("when")
    if not w:
        return True
    return bool(eval(str(w), {"__builtins__": {}}, dict(env)))  # catalogue is package data (trusted)


def status_of(moc: list[str], evs: list[dict]) -> str:
    if not evs:
        return "open"
    if any(e["ok"] is False for e in evs):
        return "non-compliant"
    if "test" in moc:
        return "needs-test"
    return "compliant"   # analysis/inspection-only MoC, evidence present (criterion met or determination made)


def build_matrix(result: dict, cert: dict | None = None, extra: dict | None = None) -> dict:
    """``result``: result.json dictionary (or :func:`evidence.extract_evidence`); ``cert``: certification block;
    ``extra``: {"safety": safety summary, "electrical": evidence} injected as evidence sources."""
    sel = select_basis(result, cert)
    ctx = sel["context"]
    env = ctx.env()
    r = dict(result)
    r["_extra"] = extra or {}
    rows = []
    cat = catalogue()
    for b in sel["bases"]:
        base = cat[b]
        for it in base["items"]:
            if not _applies(it, env):
                continue
            evs, tools, vals = [], [], []
            for k in it.get("ev") or []:
                e = EVIDENCE[k](r, ctx, it.get("param") or {})
                if e is not None:
                    evs.append(e)
                    tools.append(e["tool"])
                    vals.append(e["value"])
            st = status_of(it["moc"], evs)
            rows.append({"base": b, "parágrafo": it["id"], "título": it["t"], "paráfrase (acdt, não oficial)": it["p"],
                         "meios de conformidade": "/".join(it["moc"]), "MoC de referência": it.get("mocref", ""),
                         "evidência acdt": " | ".join(vals), "ferramenta": " | ".join(dict.fromkeys(tools)),
                         "estado": st, "estado (PT)": STATUS_PT[st], "fonte oficial": base["url"]})
    counts = {s: sum(1 for x in rows if x["estado"] == s) for s in STATUSES}
    return {"bases": sel["bases"], "sora": sel["sora"], "rationale": sel["rationale"], "notes": sel["notes"],
            "context": env | {"ac23_class": ctx.ac23_class, "category": ctx.category},
            "rows": rows, "counts": counts}


def write_csv(m: dict, path) -> str:
    rows = m["rows"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["base"])
        w.writeheader()
        w.writerows(rows)
    return str(path)


def write_xlsx(m: dict, path) -> str | None:
    """XLSX with one sheet per basis + summary, status cells coloured. Needs ``openpyxl`` (extra ``cert``)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:
        return None
    fill = {"compliant": "C6EFCE", "needs-test": "FFEB9C", "non-compliant": "FFC7CE", "open": "D9D9D9"}
    wb = Workbook()
    ws = wb.active
    ws.title = "resumo"
    ws.append(["bases", ", ".join(m["bases"])])
    for k, v in m["counts"].items():
        ws.append([STATUS_PT[k], v])
    for t in m["rationale"] + m["notes"]:
        ws.append([t])
    for b in m["bases"]:
        sh = wb.create_sheet(b[:30])
        rows = [r for r in m["rows"] if r["base"] == b]
        if not rows:
            continue
        cols = list(rows[0])
        sh.append(cols)
        for c in sh[1]:
            c.font = Font(bold=True)
        for r in rows:
            sh.append([r[c] for c in cols])
            sh.cell(sh.max_row, cols.index("estado") + 1).fill = PatternFill("solid", fgColor=fill[r["estado"]])
        for i, wdt in enumerate([10, 11, 34, 60, 20, 18, 70, 30, 13, 13, 40], start=1):
            sh.column_dimensions[sh.cell(1, i).column_letter].width = wdt
        for row in sh.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(path)
    return str(path)


def to_markdown(m: dict) -> str:
    L = ["# Matriz de conformidade (acdt)", "",
         "> Paráfrases do acdt, não o texto oficial — consultar sempre a fonte oficial ligada. Estado automático a "
         "nível de projeto conceptual; a aceitação cabe à autoridade.", "",
         "**Base(s):** " + ", ".join(m["bases"]) + ("  ·  **SORA:** sim" if m["sora"] else ""), ""]
    L += [f"- {t}" for t in m["rationale"]]
    L += ["", "| estado | nº |", "|---|---|"] + [f"| {STATUS_PT[k]} | {v} |" for k, v in m["counts"].items()]
    if m["notes"]:
        L += ["", "**Notas:**"] + [f"- {t}" for t in m["notes"]]
    for b in m["bases"]:
        L += ["", f"## {catalogue()[b]['name']}", f"Fonte oficial: {catalogue()[b]['url']}", "",
              "| parágrafo | título | MoC | evidência acdt | estado |", "|---|---|---|---|---|"]
        for r in m["rows"]:
            if r["base"] != b:
                continue
            ev = r["evidência acdt"].replace("|", "/") or "—"
            L.append(f"| {r['parágrafo']} | {r['título']} | {r['meios de conformidade']} | {ev} | {r['estado (PT)']} |")
    return "\n".join(L) + "\n"


def plot_summary(m: dict, path, title: str = "") -> str:
    """Stacked bar per basis (counts by status) + per-paragraph status strip."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    col = {"compliant": "#4caf50", "needs-test": "#ffb300", "non-compliant": "#e53935", "open": "#9e9e9e"}
    rows = m["rows"]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 5.6), gridspec_kw={"height_ratios": [1, 1.4]})
    bases = m["bases"]
    left = [0] * len(bases)
    for s in STATUSES:
        v = [sum(1 for r in rows if r["base"] == b and r["estado"] == s) for b in bases]
        a1.barh(bases, v, left=left, color=col[s], label=f"{STATUS_PT[s]} ({sum(v)})")
        left = [l + x for l, x in zip(left, v)]
    a1.legend(ncol=4, fontsize=8, loc="lower right")
    a1.set_xlabel("nº de parágrafos aplicáveis")
    a1.set_title(title or "Matriz de conformidade — resumo", fontsize=10)
    for i, r in enumerate(rows):
        a2.add_patch(plt.Rectangle((i, 0), 0.9, 1, color=col[r["estado"]]))
        a2.text(i + 0.45, -0.05, r["parágrafo"], rotation=90, ha="center", va="top", fontsize=5.5)
    a2.set_xlim(0, max(len(rows), 1))
    a2.set_ylim(-1.6, 1.05)
    a2.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return str(path)
