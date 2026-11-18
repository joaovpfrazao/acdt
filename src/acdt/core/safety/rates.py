"""Failure-rate database access (``core/data/failure_rates.yaml``) with provenance."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_PATH = Path(__file__).resolve().parents[1] / "data" / "failure_rates.yaml"


@lru_cache(maxsize=1)
def database() -> dict[str, dict]:
    d = yaml.safe_load(_PATH.read_text(encoding="utf-8"))
    return {k: dict(v) for k, v in d["components"].items()}


def rate(key: str, override: dict | None = None) -> dict:
    """Entry for ``key`` (λ, MTBF, kind, source, url); ``override`` = {key: λ or {lambda_per_h, source}} from the
    user (marked kind='user')."""
    if override and key in override:
        o = override[key]
        if isinstance(o, (int, float)):
            o = {"lambda_per_h": float(o)}
        lam = float(o["lambda_per_h"])
        kind = o.get("kind") or "user"
        return {"lambda_per_h": lam, "mtbf_h": 1.0 / lam if lam > 0 else None, "kind": kind,
                "source": o.get("source", "valor do utilizador (PRESSUPOSTO)"), "url": o.get("url", ""),
                "retrieved": o.get("retrieved", "")}
    db = database()
    if key not in db:
        raise KeyError(f"failure rate '{key}' not in failure_rates.yaml (add it with a source or pass an override)")
    return db[key]


def supplier_rate(key: str, raw) -> dict:
    """Build a supplier-provided rate. Requires λ or MTBF and a source with a date (``retrieved``).

    Missing source/date → ``status=unassessed`` and no λ to apply (never a silent number
    presented as a supplier fact). Does not invent vendor reliability data.
    """
    if raw is None:
        return {"key": key, "status": "unassessed", "unassessed_terms": ["supplier entry missing"],
                "kind": "supplier", "lambda_per_h": None, "source": None, "retrieved": None}
    if isinstance(raw, (int, float)):
        return {"key": key, "status": "unassessed", "lambda_per_h": None, "kind": "supplier",
                "unassessed_terms": ["source and retrieved/date missing — numeric rate not applied"],
                "note": "uma taxa numérica sem fonte e data não fecha o termo (unassessed≠zero/pass)"}
    if not isinstance(raw, dict):
        return {"key": key, "status": "unassessed", "lambda_per_h": None, "kind": "supplier",
                "unassessed_terms": [f"supplier rate for {key} must be a dict with lambda_per_h|mtbf_h, source, retrieved"]}
    src = (raw.get("source") or "").strip()
    retrieved = (raw.get("retrieved") or raw.get("date") or raw.get("year") or "")
    retrieved = str(retrieved).strip()
    missing = []
    if not src:
        missing.append("source")
    if not retrieved:
        missing.append("retrieved/date")
    lam = raw.get("lambda_per_h")
    mtbf = raw.get("mtbf_h")
    if lam is None and mtbf:
        lam = 1.0 / float(mtbf) if float(mtbf) else None
    if lam is None:
        missing.append("lambda_per_h or mtbf_h")
    if missing:
        return {"key": key, "status": "unassessed", "lambda_per_h": None, "kind": "supplier",
                "source": src or None, "retrieved": retrieved or None,
                "unassessed_terms": missing,
                "note": "taxa de fornecedor incompleta — não aplicada (unassessed≠pass)"}
    lam = float(lam)
    return {"key": key, "status": "ok", "lambda_per_h": lam,
            "mtbf_h": (1.0 / lam) if lam > 0 else None,
            "kind": "supplier", "source": src, "retrieved": retrieved,
            "url": raw.get("url", ""),
            "note": raw.get("note", "")}


def merge_supplier_rates(overrides: dict | None, supplier_rates: dict | None) -> tuple[dict, list[dict]]:
    """Merge sourced supplier rates into the override map used by :func:`rate`.

    Unsourced supplier entries are **not** merged (they would understate uncertainty).
    Legacy ``overrides`` (user numbers, possibly without a date) are left unchanged.
    """
    merged = dict(overrides or {})
    report: list[dict] = []
    for key, raw in (supplier_rates or {}).items():
        entry = supplier_rate(key, raw)
        report.append(entry)
        if entry["status"] == "ok":
            merged[key] = {
                "lambda_per_h": entry["lambda_per_h"],
                "source": f"{entry['source']} (retrieved {entry['retrieved']})",
                "url": entry.get("url", ""),
                "kind": "supplier",
            }
    return merged, report
