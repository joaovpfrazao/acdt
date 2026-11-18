"""Failure modes and effects analysis (FMEA) table — ARP4761 Appendix G style, quantitative (λ per mode).

Mode apportionment: each component failure mode carries a fraction α of the component λ (λ_mode = α λ). Public
mode-distribution data (e.g. FMD-2016) are proprietary, so the default is a single "loss of function" mode with
α = 1 (conservative for the failure condition it feeds); any other split must be given by the user and is labelled
PRESSUPOSTO.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field

from .fha import SEVERITY_PT


@dataclass
class FailureMode:
    mode: str
    fraction: float = 1.0
    local_effect: str = ""
    system_effect: str = ""          # failure condition id it contributes to
    severity: str = "minor"
    detection: str = "evidente"      # "evidente" (crew/GCS alerted) or "latente"
    mitigation: str = ""


@dataclass
class Component:
    id: str
    name: str
    rate_key: str
    lambda_per_h: float
    source: str
    kind: str
    quantity: int = 1
    modes: list[FailureMode] = field(default_factory=list)


def fmea_rows(components: list[Component], single_points: set[str] | None = None) -> list[dict]:
    sp = single_points or set()
    rows = []
    for c in components:
        modes = c.modes or [FailureMode("perda de função")]
        for m in modes:
            lam = c.lambda_per_h * m.fraction
            rows.append({
                "componente": c.name, "id": c.id, "qtd": c.quantity, "modo de falha": m.mode,
                "α (fração)": m.fraction, "λ_modo [1/h]": lam, "MTBF_modo [h]": (1.0 / lam) if lam > 0 else None,
                "efeito local": m.local_effect, "efeito no sistema (condição de falha)": m.system_effect,
                "severidade": SEVERITY_PT.get(m.severity, m.severity), "deteção": m.detection,
                "ponto único de falha": "sim" if c.id in sp else "não", "mitigação": m.mitigation,
                "fonte λ": c.source, "tipo de dado": c.kind,
            })
    return rows


def write_csv(rows: list[dict], path) -> str:
    if not rows:
        return str(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return str(path)


def to_markdown(rows: list[dict], cols: list[str] | None = None) -> str:
    if not rows:
        return "(sem linhas)\n"
    cols = cols or ["componente", "modo de falha", "λ_modo [1/h]", "efeito no sistema (condição de falha)",
                    "severidade", "deteção", "ponto único de falha", "tipo de dado"]

    def fmt(v):
        if isinstance(v, float):
            return f"{v:.3g}"
        return "" if v is None else str(v).replace("|", "/")
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(fmt(r.get(c)) for c in cols) + " |" for r in rows]
    return "\n".join(out) + "\n"
