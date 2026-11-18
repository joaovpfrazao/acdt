"""Standards-compliance checklist generator.

Filters the curated knowledge base (data/standards.yaml) by the run's
regulatory category, MTOW, vehicle type (UAS or crewed) and features (e.g.
lithium battery) and renders a Markdown checklist. It records *which*
standards are likely applicable and what they cover; it does not assess
compliance (that requires the standard texts and the authority).
"""
from __future__ import annotations

from .database import load_standards


def applicable_standards(category: str | None, mtow_kg: float, uas: bool, features: set[str]) -> list[dict]:
    out = []
    for s in load_standards():
        a = s.get("applies", {})
        if "uas" in a and a["uas"] != uas:
            continue
        cats = a.get("categories", "any")
        if cats != "any" and category not in cats:
            continue
        lo, hi = a.get("mtow_kg", [0, 1e9])
        if not (lo <= mtow_kg <= hi):
            continue
        if not set(a.get("needs", [])) <= features:
            continue
        out.append(s)
    return out


def checklist_markdown(category: str | None, mtow_kg: float, uas: bool, features: set[str]) -> str:
    stds = applicable_standards(category, mtow_kg, uas, features)
    lines = [f"### Checklist de normas (categoria: `{category}`, MTOW {mtow_kg:.1f} kg, "
             f"{'UAS' if uas else 'tripulado'}, features: {', '.join(sorted(features)) or '-'})", "",
             "> Orientação de primeira análise. A base de certificação é acordada com a autoridade; "
             "confirmar sempre a edição em vigor de cada documento.", ""]
    for s in stds:
        lines.append(f"- [ ] **{s['id']}** — {s['title']} ({s['issuer']}). <{s['url']}>")
        for t in s.get("topics", []):
            lines.append(f"  - [ ] {t}")
    return "\n".join(lines) + "\n"
