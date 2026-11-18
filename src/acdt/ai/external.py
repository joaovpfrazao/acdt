"""Externally researched data (materials, components) with **mandatory provenance**.

The repository only keeps a small, cited reference database (:mod:`acdt.core.materials`,
``core/data/components.yaml``). Current product data (a motor, a battery cell, an alloy temper from MMPDS) is
researched by the AI agent on the web and passed to the tools through this module, which

1. requires provenance: ``source_url`` (http/https), ``retrieved`` (ISO date, not in the future), ``source_type``
   (``manufacturer_datasheet`` | ``handbook`` | ``standard`` | ``peer_reviewed`` | ``distributor`` | ``other``);
   optional ``datasheet`` (URL / document id + revision), ``manufacturer``, ``part_number``, ``basis``
   (A/B/S/typical for metals), ``notes``;
2. converts every quantity to the units the analysis uses (``{value, unit}``, ``"72 GPa"`` or a bare number —
   a bare number is taken in the field's base unit and flagged);
3. checks broad **plausibility ranges** (sanity bounds, not design allowables — an ``acdt`` ASSUMPTION documented
   in :data:`MATERIAL_FIELDS` / :data:`COMPONENT_FIELDS`) and physical consistency (Fty ≤ Ftu, G ≈ E/2(1+ν) for
   isotropic metals, cell specific energy, motor specific power);
4. returns the entry in the form the analysis consumes plus a provenance record that the run registry stores.

Nothing here fetches the web: the agent does the research and cites it; this module refuses data without a
source and flags implausible numbers instead of silently using them."""
from __future__ import annotations

import datetime as _dt
import re
from typing import Any

from acdt.core import units

SOURCE_TYPES = ("manufacturer_datasheet", "handbook", "standard", "peer_reviewed", "distributor", "other")
CREDIBLE = ("manufacturer_datasheet", "handbook", "standard", "peer_reviewed")

# field: (dimension, base unit used by acdt, {kind: (lo, hi)} plausibility in base unit, required)
_ANY = "*"
MATERIAL_FIELDS: dict[str, tuple] = {
    "E": ("stress", "Pa", {"metal": (40e9, 250e9), "composite_equivalent": (10e9, 250e9), "core": (1e6, 2e9),
                           "wood": (0.5e9, 25e9)}, True),
    "G": ("stress", "Pa", {"metal": (15e9, 100e9), "composite_equivalent": (2e9, 80e9), "core": (0.3e6, 1e9),
                           "wood": (0.02e9, 2e9)}, False),
    "nu": ("dimensionless", "-", {_ANY: (0.0, 0.5)}, False),
    "rho": ("density", "kg/m3", {"metal": (1500, 9000), "composite_equivalent": (1100, 2300), "core": (20, 400),
                                 "wood": (80, 1100)}, True),
    "Ftu": ("stress", "Pa", {"metal": (50e6, 2000e6), "composite_equivalent": (50e6, 3000e6), "core": (0.1e6, 50e6),
                             "wood": (5e6, 300e6)}, True),
    "Fty": ("stress", "Pa", {"metal": (30e6, 1900e6), _ANY: (0.1e6, 3000e6)}, False),
    "Fcy": ("stress", "Pa", {"metal": (30e6, 1900e6), _ANY: (0.1e6, 3000e6)}, False),
    "Fsu": ("stress", "Pa", {"metal": (30e6, 1300e6), _ANY: (0.1e6, 1000e6)}, False),
    "t_min": ("length", "m", {_ANY: (0.05e-3, 20e-3)}, False),
}
MATERIAL_KINDS = ("metal", "composite_equivalent", "core", "wood")

COMPONENT_FIELDS: dict[str, dict[str, tuple]] = {
    "motors": {"kv": ("rotational_constant", "rpm/V", (5, 5000), True),
               "p_max": ("power", "W", (1, 500e3), True), "v_max": ("voltage", "V", (3, 1000), True),
               "i_max": ("current", "A", (0.1, 1000), True), "mass": ("mass", "kg", (0.001, 300), True),
               "eta_max": ("dimensionless", "-", (0.5, 0.98), False)},
    "escs": {"i_cont": ("current", "A", (1, 1000), True), "v_max": ("voltage", "V", (3, 1000), True),
             "mass": ("mass", "kg", (0.001, 50), True)},
    "cells": {"v_nom": ("voltage", "V", (1.0, 5.0), True), "v_max": ("voltage", "V", (1.0, 5.0), True),
              "capacity_ah": ("electric_charge", "Ah", (0.05, 500), True), "i_cont": ("current", "A", (0.05, 2000), True),
              "mass": ("mass", "kg", (0.001, 20), True)},
    "servos": {"torque": ("torque", "N*m", (0.01, 200), True), "v_max": ("voltage", "V", (3, 60), True),
               "mass": ("mass", "kg", (0.001, 5), True), "i_stall": ("current", "A", (0.05, 50), False)},
    "autopilots": {"mass": ("mass", "kg", (0.001, 5), True), "power_w": ("power", "W", (0.1, 100), False)},
}
_NUM_UNIT = re.compile(r"^\s*([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)\s*(.*?)\s*$")


class ExternalDataError(ValueError):
    pass


def _issue(sev, field, msg):
    return {"severity": sev, "field": field, "message": msg}


def check_provenance(p: dict | None) -> tuple[dict, list[dict]]:
    p = dict(p or {})
    iss = []
    url = str(p.get("source_url") or "")
    if not re.match(r"^https?://\S+$", url):
        iss.append(_issue("error", "source_url", "source_url (http/https) is mandatory for external data"))
    d = p.get("retrieved")
    try:
        day = _dt.date.fromisoformat(str(d)[:10])
        if day > _dt.date.today():
            iss.append(_issue("error", "retrieved", f"retrieved date {day} is in the future"))
        elif (_dt.date.today() - day).days > 5 * 365:
            iss.append(_issue("warning", "retrieved", f"data retrieved {day}: older than 5 years — check for a "
                                                      f"newer datasheet / handbook release"))
        p["retrieved"] = day.isoformat()
    except (TypeError, ValueError):
        iss.append(_issue("error", "retrieved", "retrieved (ISO date YYYY-MM-DD) is mandatory"))
    st = p.get("source_type", "other")
    if st not in SOURCE_TYPES:
        iss.append(_issue("error", "source_type", f"source_type must be one of {SOURCE_TYPES}"))
    elif st not in CREDIBLE:
        iss.append(_issue("warning", "source_type", f"source_type '{st}': prefer a manufacturer datasheet, "
                                                    f"MMPDS/CMH-17 handbook, standard or peer-reviewed source"))
    p["source_type"] = st
    return p, iss


def _quantity(field: str, v: Any, dim: str, base: str) -> tuple[float | None, list[dict], dict]:
    """→ (value in base unit, issues, {raw, unit})."""
    unit, raw = None, v
    if isinstance(v, dict):
        raw, unit = v.get("value"), v.get("unit")
    elif isinstance(v, str):
        m = _NUM_UNIT.match(v)
        if not m:
            return None, [_issue("error", field, f"cannot parse quantity {v!r}")], {"raw": v}
        raw, unit = float(m.group(1)), (m.group(2) or None)
    try:
        raw = float(raw)
    except (TypeError, ValueError):
        return None, [_issue("error", field, f"{field}: not a number ({raw!r})")], {"raw": raw}
    iss = []
    if unit is None:
        unit = base
        if dim != "dimensionless":
            iss.append(_issue("warning", field, f"{field}: no unit given — taken as {base}"))
    try:
        val = units.from_si(units.to_si(raw, unit, dim), base, dim)
    except units.UnitError as e:
        return None, [_issue("error", field, f"{field}: {e}")], {"raw": raw, "unit": unit}
    return val, iss, {"raw": raw, "unit": unit}


def _range(field, val, lo, hi, base, iss):
    if not (lo <= val <= hi):
        iss.append(_issue("error", field, f"{field} = {val:.4g} {base} outside the plausibility range "
                                          f"[{lo:.4g}, {hi:.4g}] {base} — check the unit and the source"))


def validate_material(entry: dict) -> dict:
    """Validate a structural material researched externally.

    ``entry``: ``{key, name, kind (metal|composite_equivalent|core|wood), E, G?, nu?, rho, Ftu, Fty?, Fcy?, Fsu?,
    t_min?, provenance: {source_url, retrieved, source_type, datasheet?, basis?, ...}}``. Composite entries are
    *equivalent isotropic* (in-plane CLT constants and strain-cut-off allowables), as in
    :func:`acdt.core.materials.composite_equivalent`.

    Returns ``{ok, issues, material (SI), structures (form consumed by the wing-box sizing), provenance}``."""
    kind = entry.get("kind", "metal")
    iss: list[dict] = []
    if kind not in MATERIAL_KINDS:
        iss.append(_issue("error", "kind", f"kind must be one of {MATERIAL_KINDS}"))
        kind = "metal"
    prov, pi = check_provenance(entry.get("provenance"))
    iss += pi
    m: dict[str, Any] = {"key": str(entry.get("key") or re.sub(r"\W+", "_", str(entry.get("name", "ext"))).lower()),
                         "name": str(entry.get("name") or entry.get("key") or "external material"), "kind": kind}
    raw = {}
    for f, (dim, base, ranges, req) in MATERIAL_FIELDS.items():
        if entry.get(f) is None:
            if req:
                iss.append(_issue("error", f, f"{f} is required"))
            continue
        val, qi, r = _quantity(f, entry[f], dim, base)
        iss += qi
        raw[f] = r
        if val is None:
            continue
        lo, hi = ranges.get(kind, ranges.get(_ANY, (float("-inf"), float("inf"))))
        _range(f, val, lo, hi, base, iss)
        m[f] = val
    E, nu, G = m.get("E"), m.get("nu"), m.get("G")
    if E and G is None and nu is not None:
        m["G"] = E / (2 * (1 + nu))
        iss.append(_issue("info", "G", "G not given — isotropic G = E / 2(1+ν) used"))
    if E and nu is None:
        m["nu"] = 0.33 if kind == "metal" else 0.3
        iss.append(_issue("warning", "nu", f"ν not given — {m['nu']} ASSUMED"))
    if kind == "metal" and E and m.get("G") and m.get("nu") is not None and G is not None:
        Gi = E / (2 * (1 + m["nu"]))
        if abs(G / Gi - 1) > 0.15:
            iss.append(_issue("warning", "G", f"G = {G / 1e9:.1f} GPa differs > 15 % from E/2(1+ν) = {Gi / 1e9:.1f} GPa"))
    ftu = m.get("Ftu")
    if "Fty" not in m and ftu:
        m["Fty"] = ftu
        iss.append(_issue("warning" if kind == "metal" else "info", "Fty",
                          "Fty not given — Ftu used (valid for linear-to-failure materials; for metals give the yield)"))
    if "Fcy" not in m and m.get("Fty"):
        m["Fcy"] = m["Fty"]
        iss.append(_issue("warning", "Fcy", "Fcy not given — Fcy = Fty ASSUMED (give the compressive allowable; it "
                                            "sizes the compression cover)"))
    if m.get("Fty") and ftu and m["Fty"] > ftu * 1.001:
        iss.append(_issue("error", "Fty", "Fty > Ftu"))
    if "Fsu" not in m and ftu:
        m["Fsu"] = 0.6 * ftu
        iss.append(_issue("warning", "Fsu", "Fsu not given — 0.6 Ftu ASSUMED (ratio of the aluminium sheets in "
                                            "acdt.core.materials: 2024-T3 0.60, 7075-T6 0.58, MIL-HDBK-5J; verify)"))
    if kind == "metal" and not (entry.get("provenance") or {}).get("basis"):
        iss.append(_issue("warning", "basis", "metal allowables without basis (A/B/S/typical) — state it "
                                              "(MMPDS)"))
    ok = not any(i["severity"] == "error" for i in iss)
    out = {"ok": ok, "issues": iss, "material": m, "raw": raw, "provenance": prov, "structures": None}
    if ok:
        from acdt.core.materials import Material
        mat = Material(m["key"], m["name"], m["E"], m["G"], m["nu"], m["rho"], m["Ftu"], m["Fty"], m["Fcy"], m["Fsu"],
                       f"EXTERNAL: {prov.get('source_url')} (retrieved {prov.get('retrieved')}"
                       + (f", {prov['datasheet']}" if prov.get("datasheet") else "") + ")",
                       kind, m.get("t_min", 0.5e-3))
        out["structures"] = mat.as_structures_dict()
        if "t_min" not in m:
            iss.append(_issue("warning", "t_min", "t_min (minimum gauge) not given — 0.5 mm ASSUMED"))
    return out


def validate_component(category: str, entry: dict) -> dict:
    """Validate one component (``category`` ∈ motors, escs, cells, servos, autopilots) in the
    ``components.yaml`` schema, with provenance. Returns ``{ok, issues, component, provenance}``; ``component`` can
    be passed in ``systems.components.<category>`` (user components are tried before the example DB)."""
    if category not in COMPONENT_FIELDS:
        raise ExternalDataError(f"category must be one of {list(COMPONENT_FIELDS)}")
    iss: list[dict] = []
    prov, pi = check_provenance(entry.get("provenance"))
    iss += pi
    c = {k: v for k, v in entry.items() if k not in COMPONENT_FIELDS[category] and k != "provenance"}
    if not c.get("id"):
        iss.append(_issue("error", "id", "id is required"))
    for f, (dim, base, (lo, hi), req) in COMPONENT_FIELDS[category].items():
        if entry.get(f) is None:
            if req:
                iss.append(_issue("error", f, f"{f} is required"))
            continue
        val, qi, _ = _quantity(f, entry[f], dim, base)
        iss += qi
        if val is not None:
            _range(f, val, lo, hi, base, iss)
            c[f] = val
    if category == "cells" and all(k in c for k in ("v_nom", "capacity_ah", "mass")):
        se = c["v_nom"] * c["capacity_ah"] / c["mass"]
        c["specific_energy_Wh_kg"] = se
        if not 50 <= se <= 500:
            iss.append(_issue("error", "mass", f"cell specific energy {se:.0f} Wh/kg outside [50, 500] — check"))
        elif se > 350:
            iss.append(_issue("warning", "mass", f"cell specific energy {se:.0f} Wh/kg is exceptional — confirm "
                                                 f"with the datasheet"))
        if c.get("v_max", 0) < c["v_nom"]:
            iss.append(_issue("error", "v_max", "v_max < v_nom"))
    if category == "motors" and all(k in c for k in ("p_max", "mass")):
        sp = c["p_max"] / c["mass"] / 1e3
        if not 0.1 <= sp <= 15:
            iss.append(_issue("warning", "p_max", f"motor specific power {sp:.2f} kW/kg outside [0.1, 15] — check"))
    c["source"] = f"EXTERNAL: {prov.get('source_url')} (retrieved {prov.get('retrieved')})"
    c["url"] = prov.get("source_url")
    return {"ok": not any(i["severity"] == "error" for i in iss), "issues": iss, "component": c,
            "provenance": prov}
