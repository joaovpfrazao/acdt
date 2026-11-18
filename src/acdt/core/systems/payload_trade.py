"""Payload catalog trade (P4): mass, power, volume, FOV cone — agent researches live datasheets.

The built-in catalog is EXAMPLE DATA. Prefer user/agent rows with ``source`` and ``retrieved``.
Comparison uses :func:`acdt.core.concept.tradeoff.compare` (Pareto); this module never picks.
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from acdt.core.concept.tradeoff import compare

REF = "Deb 2001 (Pareto); FOV as datasheet cone — packaging check is separate (assembly integration)"


def load_payload_catalog(path: str | Path | None = None, extra: list[dict] | None = None) -> list[dict]:
    if path is None:
        with resources.as_file(resources.files("acdt.core") / "data" / "payloads.yaml") as p:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
    else:
        d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rows = list(d.get("payloads") or [])
    if extra:
        rows = list(extra) + rows
    for r in rows:
        if not r.get("source"):
            r["source"] = "UNSPECIFIED"
        if str(r.get("source", "")).upper() == "EXAMPLE" or r.get("source") == "EXAMPLE":
            r.setdefault("notes", "")
            if "EXEMPLO" not in str(r.get("notes", "")):
                r["notes"] = (str(r.get("notes", "")) + " EXAMPLE DATA").strip()
    return rows


def load_electrical_catalog(path: str | Path | None = None) -> dict:
    if path is None:
        with resources.as_file(resources.files("acdt.core") / "data" / "payloads.yaml") as p:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
    else:
        d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return {"generators": d.get("generators") or [], "batteries_avionics": d.get("batteries_avionics") or [],
            "payloads": d.get("payloads") or []}


def trade(payloads: list[dict], objectives: dict | None = None, constraints: dict | None = None,
          kinds: list[str] | None = None) -> dict[str, Any]:
    """Pareto trade on catalog rows. Default objectives: min mass, min power_avg, max fov_cross."""
    obj = objectives or {"mass_kg": "min", "power_w_avg": "min", "fov_cross_deg": "max"}
    rows = payloads
    if kinds:
        rows = [p for p in rows if p.get("kind") in kinds]
    alts = []
    for p in rows:
        metrics = {k: p.get(k) for k in obj}
        metrics["volume_l"] = p.get("volume_l")
        metrics["power_w_peak"] = p.get("power_w_peak")
        alts.append({"id": p["id"], "metrics": metrics, "payload": p})
    cmp = compare(alts, obj, constraints)
    # attach payload details
    by_id = {p["id"]: p for p in rows}
    for r in cmp["rows"]:
        r["payload"] = by_id.get(r["id"])
    cmp["reference"] = REF
    cmp["note_catalog"] = "catálogo de exemplo salvo como EXAMPLE; preferir linhas com source+retrieved"
    return cmp
