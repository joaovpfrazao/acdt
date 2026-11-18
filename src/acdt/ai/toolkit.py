"""acdt toolkit for AI agents — plain-Python tool functions with JSON-serialisable inputs and outputs.

The MCP server (:mod:`acdt.ai.mcp_server`) only registers these functions; they are also usable directly
(scripts, notebooks, tests). Conventions:

* **Source of a design** (every analysis tool): exactly one of ``spec`` (mission dict, same schema as the
  example YAMLs), ``spec_path`` (YAML file), ``run_id`` (a previous run — its materialised spec is reused and the
  new run is linked to it) or ``example`` (name of an ``examples/*.yaml``).
* Every computing call creates a **run** in the registry (:mod:`acdt.ai.registry`) and returns ``run_id``,
  a structured summary, ``files`` (reports, plots, JSON) and the ``issues``/limitations found. Numbers come only
  from the analyses; nothing is invented — a missing tool or a failed step is reported as such.
* Long analyses go through :func:`start` (async job: returns the result if it finishes within ``wait_s``,
  otherwise a ``job_id`` to poll with :func:`job_status`).
"""
from __future__ import annotations

import contextlib
import copy
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from . import catalogue, external, guard, registry
from .jobs import MANAGER

try:  # analyses plot from worker threads
    import matplotlib
    matplotlib.use("Agg")
except ImportError:  # pragma: no cover
    pass

LEVELS = {"L0": "handbook", "L1": "lowfi"}
LONG_TOOLS = ("size", "systems", "optimize", "wingbox", "rcs", "hifi", "manufacturing_plan")


class ToolError(ValueError):
    """Bad input to a tool (reported to the agent as an error with the reason)."""


# --------------------------------------------------------------------------------------------- helpers
def clean(o: Any) -> Any:
    """JSON-safe copy: NaN/inf → None, numpy → python, Path → str, tuples → lists, objects → dicts."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [clean(v) for v in o]
    if isinstance(o, bool) or o is None or isinstance(o, str):
        return o
    if isinstance(o, int):
        return o
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, Path):
        return str(o)
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return clean(o.item())
        if isinstance(o, np.ndarray):
            return clean(o.tolist())
    except ImportError:  # pragma: no cover
        pass
    if hasattr(o, "__dict__"):
        return clean({k: v for k, v in vars(o).items() if not k.startswith("_")})
    return str(o)


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and v and k not in ("Q", "extra_drag_areas_m2", "stations", "components", "material"):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def _slug(s: str) -> str:
    return registry._slug(s)


def _resolve(spec=None, spec_path=None, run_id=None, example=None) -> tuple[dict, dict]:
    """→ (mission dict, origin {kind, ref, parent_run})."""
    given = [k for k, v in (("spec", spec), ("spec_path", spec_path), ("run_id", run_id), ("example", example))
             if v not in (None, "", {})]
    if len(given) != 1:
        raise ToolError("give exactly one design source: spec (dict), spec_path, run_id or example "
                        f"(got {given or 'none'})")
    if spec is not None and given == ["spec"]:
        if not isinstance(spec, dict):
            raise ToolError("spec must be a mission dict (keys: name, aircraft_class, requirements, assumptions, "
                            "systems)")
        return copy.deepcopy(spec), {"kind": "spec", "ref": None, "parent_run": None}
    if spec_path:
        p = Path(spec_path)
        if not p.exists():
            raise ToolError(f"spec_path {spec_path} not found")
        d = _absolutise(yaml.safe_load(p.read_text(encoding="utf-8")) or {}, p.parent)
        d.setdefault("assumption_sources", {}).setdefault("*", f"spec file {p.name} (see its comments)")
        return d, {"kind": "spec_path", "ref": str(p.resolve()), "parent_run": None}
    if example:
        p = catalogue.REPO / "examples" / f"{Path(example).stem}.yaml"
        if not p.exists():
            raise ToolError(f"example {example!r} not found ({', '.join(e['example'] for e in catalogue.examples())})")
        d = _absolutise(yaml.safe_load(p.read_text(encoding="utf-8")) or {}, p.parent)
        d.setdefault("assumption_sources", {}).setdefault("*", f"examples/{p.name} (see the comments in that file)")
        return d, {"kind": "example", "ref": p.stem, "parent_run": None}
    r = registry.load(run_id)
    sp = r.record.get("files", {}).get("spec")
    if not sp or not Path(sp).exists():
        raise ToolError(f"run {run_id} has no materialised spec")
    return yaml.safe_load(Path(sp).read_text(encoding="utf-8")) or {}, \
        {"kind": "run", "ref": run_id, "parent_run": run_id}


def _absolutise(d: dict, base: Path) -> dict:
    """Relative calibration file paths are relative to the YAML that names them."""
    c = ((d.get("assumptions") or {}).get("calibration") or {})
    f = c.get("file")
    if f and not Path(f).is_absolute() and (base / f).exists():
        c["file"] = str((base / f).resolve())
    return d


def _materialise(run: registry.Run, d: dict) -> Path:
    stem = _slug(d.get("name", "design"))
    p = run.path / f"{stem}.yaml"
    p.write_text(yaml.safe_dump(clean(d), sort_keys=False, allow_unicode=True), encoding="utf-8")
    run.record.setdefault("files", {})["spec"] = str(p)
    return p


def _assumption_entries(d: dict) -> list[dict]:
    """Every assumption value with its source: ``user`` (given in the spec, optionally cited through
    ``assumption_sources: {"aero.AR": "Raymer Table 4.1"}``), ``external`` (validated external data) or
    ``assumed (acdt default — DEFAULT_ASSUMPTIONS in acdt/domains/aircraft/mission.py)``."""
    from acdt.domains.aircraft.mission import DEFAULT_ASSUMPTIONS, _merge
    user = _flatten(d.get("assumptions") or {})
    cites = d.get("assumption_sources") or {}
    merged = _flatten(_merge(DEFAULT_ASSUMPTIONS, d.get("assumptions") or {}))
    ext = {e["path"]: e for e in d.get("_external", [])}
    out = []
    for k, v in merged.items():
        if k in ext:
            src = f"external: {ext[k]['provenance'].get('source_url')} (retrieved {ext[k]['provenance'].get('retrieved')})"
        elif k in user:
            c = _cite(cites, k)
            src = "user" + (f" — {c}" if c else " (no citation given)")
        else:
            src = "assumed (acdt default — DEFAULT_ASSUMPTIONS, acdt/domains/aircraft/mission.py)"
        out.append({"path": k, "value": clean(v), "source": src})
    if not d.get("aircraft_class"):
        out.append({"path": "aircraft_class", "value": "ga_single_engine", "source": "assumed (acdt default)"})
    return out


def _cite(cites: dict, k: str) -> str | None:
    """Citation of an assumption path: exact key, else the longest dotted prefix, else ``"*"``."""
    parts = k.split(".")
    for n in range(len(parts), 0, -1):
        c = cites.get(".".join(parts[:n]))
        if c:
            return c
    return cites.get("*")


def _note_source(d: dict, path: str, text: str) -> None:
    d.setdefault("assumption_sources", {})[path] = text


def _aircraft_classes() -> list[str]:
    from acdt.domains.aircraft import weights as W
    return sorted(set(W.RAYMER_EMPTY_WEIGHT) | set(W.NICOLAI_EMPTY_WEIGHT) | set(W.FIXED_EMPTY_FRACTION)
                  | set(W.EMPTY_FRACTION_ALIASES))


def _new_run(tool: str, d: dict, origin: dict, inputs: dict) -> registry.Run:
    run = registry.new_run(tool, d.get("name", "design"), clean({"origin": origin, **inputs}), origin.get("parent_run"))
    _materialise(run, {k: v for k, v in d.items() if k != "_external"})
    run.record["assumptions"] = _assumption_entries(d)
    run.record["external_data"] = clean(d.get("_external", []))
    run.record["calibration"] = _calibration_record(d)
    run.save()
    return run


def _calibration_record(d: dict) -> dict | None:
    c = ((d.get("assumptions") or {}).get("calibration") or {})
    if not (c.get("file") or c.get("factors")):
        return None
    rec = {"file": c.get("file"), "apply": c.get("apply") or [], "factors_inline": c.get("factors") or {}}
    try:
        from acdt.domains.aircraft.hifi import calibration as cal_mod
        rec["applied_factors"] = cal_mod.load(d.get("assumptions"))
    except (OSError, KeyError, ValueError) as ex:
        rec["error"] = f"{type(ex).__name__}: {ex}"
    return rec


def _files_in(folder: Path) -> dict:
    return {p.name: str(p) for p in sorted(Path(folder).glob("*")) if p.is_file()}


@contextlib.contextmanager
def _quiet():
    """Analyses print progress: keep stdout clean (stdio MCP transport) by sending it to stderr."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


def _log(job):
    return (lambda m: job.log.append(str(m))) if job is not None else (lambda m: print(m, file=sys.stderr))


# --------------------------------------------------------------------------------------------- requirements
def requirements_schema(domain: str = "aircraft") -> dict:
    """Requirement types (key, dimension, default unit, accepted units, senses, qualifiers, choices, implemented,
    foreseen method) + the spec layout and the aircraft classes."""
    from acdt.core import units
    from acdt.core.pipeline import get_domain
    from acdt.core.requirements import types_for
    get_domain(domain)
    types = []
    for k, rt in types_for(domain).items():
        dim = rt.dimension
        types.append({"key": k, "dimension": dim, "description": rt.description,
                      "default_unit": (units.default_unit(dim) if dim != "category" else None),
                      "units": (units.units_for(dim) if dim != "category" else []), "senses": list(rt.senses),
                      "qualifiers": list(rt.params), "choices": list(rt.choices), "implemented": rt.implemented,
                      "reference": rt.reference, "stages": list(rt.stages)})
    return {"domain": domain, "requirement_types": types, "aircraft_classes": _aircraft_classes(),
            "spec_layout": {"name": "str", "description": "str", "aircraft_class": "one of aircraft_classes",
                            "requirements": "{key: {min|max|target|objective: value, unit: u, <qualifier>: ...}} "
                                            "or a bare number (target, default unit) or a category string; "
                                            "strings such as '2.5 h' are accepted by validate_requirements",
                            "assumptions": "overrides of DEFAULT_ASSUMPTIONS (weights, aero, propulsion, geometry, "
                                           "constraints, mda, structures, stability, performance, aeroelasticity, "
                                           "mdo, cost, calibration)",
                            "assumption_sources": "{'aero.AR': 'citation'} — the source of each assumption you set",
                            "systems": "optional electric-UAV systems block (see example uav_endurance_payload)"},
            "default_assumptions": _default_assumptions()}


def _default_assumptions() -> dict:
    from acdt.domains.aircraft.mission import DEFAULT_ASSUMPTIONS
    return clean(DEFAULT_ASSUMPTIONS)


def _norm_req(key: str, v):
    """Lenient forms → the canonical parser forms: '2.5 h', {'min': '2.5 h'}, {'min': 2.5, 'unit': 'h'}."""
    from acdt.core.requirements import SENSES
    def split(s):
        m = external._NUM_UNIT.match(s)
        return (float(m.group(1)), m.group(2) or None) if m else (None, None)
    if isinstance(v, str):
        num, unit = split(v)
        if num is not None:
            return {"target": num, **({"unit": unit} if unit else {})}
        return v
    if isinstance(v, dict):
        v = dict(v)
        for s in SENSES:
            if isinstance(v.get(s), str) and s != "objective":
                num, unit = split(v[s])
                if num is not None:
                    v[s] = num
                    if unit and "unit" not in v:
                        v["unit"] = unit
        return v
    if isinstance(v, list):
        return [_norm_req(key, x) for x in v]
    return v


def validate_requirements(spec: dict, record: bool = True) -> dict:
    """Validate + normalise a mission request (lenient units), list SI values, static issues, which values are
    assumed (defaults) and what is still missing. With ``record`` a ``requirements`` run is created whose
    ``run_id`` can be passed to ``size`` etc."""
    from acdt.core.requirements import RequirementError, RequirementSet, types_for
    from acdt.core import units
    import acdt.domains.aircraft  # noqa: F401  (registers types)
    if not isinstance(spec, dict):
        raise ToolError("spec must be a dict")
    d = copy.deepcopy(spec)
    reqs = {k: _norm_req(k, v) for k, v in (d.get("requirements") or {}).items()}
    d["requirements"] = reqs
    errors, table = [], []
    try:
        rs = RequirementSet.from_dict(reqs, domain="aircraft")
    except RequirementError as e:
        return {"ok": False, "errors": [str(e)], "issues": [{"severity": "error", "message": str(e), "keys": []}],
                "normalised_spec": clean(d), "run_id": None,
                "hint": "fix the requirement (see requirements_schema for keys, units and senses)"}
    issues = [{"severity": i.severity, "message": i.message, "keys": list(i.keys)} for i in rs.validate()]
    tps = types_for("aircraft")
    for r in rs:
        rt = tps[r.key]
        table.append({"key": r.key, "sense": r.sense, "value_si": clean(r.value) if not isinstance(r.value, str) else r.value,
                      "si_unit": units.default_unit(rt.dimension) if rt.dimension != "category" else None,
                      "given": r.raw, "unit": r.unit or None, "qualifiers_si": r.params, "implemented": rt.implemented})
    cls = d.get("aircraft_class")
    if cls and cls not in _aircraft_classes():
        errors.append(f"aircraft_class {cls!r} unknown (one of {_aircraft_classes()})")
    hints = []
    keys = {r.key for r in rs}
    if not cls:
        hints.append("aircraft_class not given → 'ga_single_engine' ASSUMED (statistical We/W0 class)")
    if "propulsion_type" not in keys:
        hints.append("propulsion_type not given → 'piston_prop' ASSUMED")
    if not keys & {"range", "endurance"}:
        hints.append("no range/endurance requirement: the fuel/battery fraction is driven only by the defaults")
    if "payload_mass" not in keys:
        hints.append("no payload_mass requirement")
    issues += [{"severity": "error", "message": e, "keys": []} for e in errors]
    ok = not any(i["severity"] == "error" for i in issues)
    out = {"ok": ok, "requirements": table, "issues": issues, "hints": hints, "normalised_spec": clean(d)}
    ents = _assumption_entries(d)
    out["assumptions"] = {"n_total": len(ents), "user": [e for e in ents if e["source"].startswith("user")],
                          "n_defaults": sum(e["source"].startswith("assumed") for e in ents),
                          "note": "defaults are the acdt DEFAULT_ASSUMPTIONS (cited in mission.py and the modules); "
                                  "set and cite your own in assumptions/assumption_sources"}
    if record and ok:
        run = _new_run("requirements", d, {"kind": "spec", "ref": None, "parent_run": None}, {})
        run.finish(clean({"ok": ok, "requirements": table, "issues": issues, "hints": hints}))
        out["run_id"], out["spec_path"] = run.id, run.record["files"]["spec"]
    else:
        out["run_id"] = None
    return out


# --------------------------------------------------------------------------------------------- inputs w/ data
def _apply_external(d: dict, materials: dict | None, components: dict | None) -> list[dict]:
    """Inject validated external data into the spec; returns the issues; records provenance in d['_external']."""
    iss = []
    ext = d.setdefault("_external", [])
    for role, m in (materials or {}).items():
        if role not in ("structure", "wing_box"):
            raise ToolError("materials: supported role is 'structure' (wing box / structural sizing)")
        a = d.setdefault("assumptions", {}).setdefault("structures", {})
        if isinstance(m, str):
            from acdt.core import materials as M
            from acdt.domains.aircraft.structures import MATERIALS
            if m in MATERIALS or m == "auto":
                a["material"] = m
            else:
                try:
                    a["material"] = M.get(m).as_structures_dict()
                except KeyError as e:
                    raise ToolError(str(e)) from e
            continue
        v = external.validate_material(m)
        iss += [{**i, "item": f"material:{role}"} for i in v["issues"]]
        if not v["ok"]:
            raise ToolError(f"external material rejected: {[i['message'] for i in v['issues'] if i['severity'] == 'error']}")
        a["material"] = v["structures"]
        ext.append({"path": "structures.material", "kind": "material", "name": v["material"]["name"],
                    "provenance": v["provenance"], "issues": v["issues"]})
    for cat, items in (components or {}).items():
        if d.get("systems") is None:
            raise ToolError("components given but the spec has no 'systems' block (electric-UAV systems)")
        lst = d["systems"].setdefault("components", {}).setdefault(cat, [])
        for it in items:
            v = external.validate_component(cat, it)
            iss += [{**i, "item": f"{cat}:{it.get('id')}"} for i in v["issues"]]
            if not v["ok"]:
                raise ToolError(f"external component {it.get('id')} rejected: "
                                f"{[i['message'] for i in v['issues'] if i['severity'] == 'error']}")
            lst.insert(0, v["component"])
            ext.append({"path": f"systems.components.{cat}", "kind": "component", "name": it.get("id"),
                        "provenance": v["provenance"], "issues": v["issues"]})
    return iss


# --------------------------------------------------------------------------------------------- size
def _size_summary(res, d: dict) -> dict:
    dp = d.get("design_point", {})
    s = {"name": d.get("name"), "feasible": d.get("feasible"), "weights": d.get("weights"),
         "design_point": dp, "geometry": {"wing": (d.get("geometry") or {}).get("wing"),
                                          "fuselage": (d.get("geometry") or {}).get("fuselage")},
         "aero": d.get("aero"),
         "failed_checks": [c for c in d.get("checks", []) if c.get("ok") is False],
         "checks": d.get("checks"), "issues": d.get("issues")}
    if d.get("aero_lowfi"):
        lf = d["aero_lowfi"]
        s["aero_lowfi"] = {k: lf.get(k) for k in ("CD0", "e_eff", "clmax_airfoil", "airfoil_source", "span_source")}
    st = d.get("structures")
    if st:
        s["structures"] = {k: st.get(k) for k in ("wing_box_mass_kg", "wing_mass_raymer_kg", "box_over_raymer",
                                                  "box_method")}
        s["structures"]["n_limit"] = (st.get("vn") or {}).get("n_limit_pos")
    stb = d.get("stability")
    if stb:
        s["stability"] = {k: stb.get(k) for k in ("SM_fwd", "SM_aft", "xbar_np", "xbar_np_avl")}
    if d.get("weight_balance"):
        wb = d["weight_balance"]
        s["weight_balance"] = {k: wb.get(k) for k in ("within_limits", "x_min_m", "x_max_m", "summary")}
    if d.get("landing_gear"):
        g = d["landing_gear"]
        s["landing_gear"] = {k: g.get(k) for k in ("kind", "geometry_ok", "stroke_m", "descent_m_s",
                                                   "geometry_summary", "load_summary")}
    pf = d.get("performance")
    if pf:
        s["performance"] = {"range_km": pf.get("range_km"), "endurance_h": pf.get("endurance_h"),
                            "requirements": pf.get("requirements")}
    ae = d.get("aeroelasticity")
    if ae:
        s["aeroelasticity_margins"] = ae.get("margins")
    if d.get("cost"):
        s["cost"] = d["cost"]
    if d.get("systems"):
        sy = d["systems"]
        s["systems"] = {"motor": (sy.get("motor") or {}).get("id") if isinstance(sy.get("motor"), dict) else sy.get("motor"),
                        "esc": (sy.get("esc") or {}).get("id") if isinstance(sy.get("esc"), dict) else sy.get("esc"),
                        "battery": sy.get("battery"), "autopilot": (sy.get("autopilot") or {}).get("id")
                        if isinstance(sy.get("autopilot"), dict) else sy.get("autopilot"),
                        "servos": sy.get("servos"), "power_avg_W": sy.get("power_avg_W"), "messages": sy.get("messages")}
    s["verified_segment_mission"] = d.get("verified_segment_mission")
    if d.get("onboard_bridge"):
        s["onboard_bridge"] = d["onboard_bridge"]
    return clean(s)


def size(job=None, *, spec=None, spec_path=None, run_id=None, example=None, level: str | None = "L1",
         no_systems: bool = False, materials: dict | None = None, components: dict | None = None,
         assumptions: dict | None = None) -> dict:
    """Conceptual (L0, handbook) or low-fidelity (L1, XFOIL/AVL) sizing + design point + Phase 2/3 disciplines
    (structures, stability, aeroelasticity, performance) + report. ``assumptions`` are merged over the spec's;
    ``materials`` / ``components`` are external data with provenance (validated, recorded)."""
    from acdt.core.pipeline import InfeasibleError, run_pipeline
    from acdt.core.requirements import RequirementError
    from acdt.domains.aircraft.mission import _merge
    from acdt.domains.aircraft.report import to_dict
    d, origin = _resolve(spec, spec_path, run_id, example)
    if assumptions:
        d["assumptions"] = _merge(d.get("assumptions") or {}, assumptions)
    if level:
        if level not in LEVELS:
            raise ToolError(f"level must be one of {list(LEVELS)}")
        d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = LEVELS[level]
        _note_source(d, "aero.fidelity", f"tool argument level={level}")
    ext_issues = _apply_external(d, materials, components)
    warn = []
    if (level == "L1" or (d.get("assumptions", {}).get("aero", {}).get("fidelity") == "lowfi")):
        for e in ("xfoil", "avl"):
            if not (shutil.which(e)):
                warn.append(f"{e} not found on PATH — the low-fi stage falls back/fails for that part (see "
                            f"aero_lowfi.*_source)")
    run = _new_run("size", d, origin, {"level": level, "no_systems": no_systems})
    if job is not None:
        job.run_id = run.id
    out = run.path / "size"
    try:
        with _quiet():
            st = run_pipeline("aircraft", run.record["files"]["spec"], output=out, no_systems=no_systems)
    except (InfeasibleError, RequirementError) as e:
        run.finish({"feasible": False, "error": str(e)}, status="infeasible", error=str(e))
        return {"run_id": run.id, "status": "infeasible", "error": str(e),
                "hint": "the analysis stopped: an input is missing or the requirements cannot be met together — "
                        "read the message, supply the missing assumption (cited) or relax a requirement"}
    res = st["result"]
    dd = to_dict(res)
    summ = _size_summary(res, dd)
    summ["warnings"] = warn + [f"{i['item']}: {i['message']}" for i in ext_issues if i["severity"] != "info"]
    files = _files_in(out)
    run.finish(summ, files)
    return {"run_id": run.id, "status": "done", "level": level, "summary": summ,
            "report": files.get("report.md"), "result_json": files.get("result.json"), "files": files}


def systems(job=None, *, spec=None, spec_path=None, run_id=None, example=None, components: dict | None = None,
            level: str | None = None) -> dict:
    """Systems selection (propeller, motor, ESC, battery, servos, autopilot, power budget) closed with the sizing,
    plus wiring harness (WireViz, Graphviz, netlist CSV, KiCad netlist) and compliance checklist."""
    d, _ = _resolve(spec, spec_path, run_id, example)
    if not d.get("systems"):
        raise ToolError("the spec has no 'systems' block — add one (see example 'uav_endurance_payload': "
                        "bus_cells_series, cell_chemistry, propeller, motor, servos, autopilot, loads, harness)")
    r = size(job, spec=d, level=level, components=components)
    if r.get("status") != "done":
        return r
    reg = registry.load(r["run_id"])
    reg.record["tool"] = "systems"
    reg.save()
    f = r["files"]
    return {"run_id": r["run_id"], "status": "done", "systems": r["summary"].get("systems"),
            "feasible": r["summary"]["feasible"], "weights": r["summary"]["weights"],
            "harness_files": {k: f[k] for k in ("harness.wireviz.yml", "harness.dot", "netlist.csv", "harness.net")
                              if k in f},
            "compliance_checklist": f.get("compliance_checklist.md"), "report": r["report"]}


# --------------------------------------------------------------------------------------------- MDO
def optimize(job=None, *, spec=None, spec_path=None, run_id=None, example=None, objective: str | None = None,
             solver: str | None = None, max_iter: int | None = None, level: str | None = None,
             consistency_order: int | None = None, assumptions: dict | None = None) -> dict:
    """Preliminary MDO (OpenMDAO, trust-region model management on the full pipeline); writes baseline/ and
    optimum/ reports + mdo_report.md. ``level`` sets the fidelity of the 'truth' pipeline (L1 = XFOIL/AVL, the
    default of the spec; L0 = handbook, much faster, for exploration). ``consistency_order`` 0 skips the
    finite-difference gradient of the full pipeline (fewer pipeline runs, weaker model correction)."""
    from acdt.core.mdo import openmdao_available
    if not openmdao_available():
        raise ToolError("OpenMDAO not installed: pip install 'acdt[mdo]'")
    from acdt.domains.aircraft.mdo import optimize_pipeline
    from acdt.domains.aircraft.mission import _merge
    d, origin = _resolve(spec, spec_path, run_id, example)
    if assumptions:
        d["assumptions"] = _merge(d.get("assumptions") or {}, assumptions)
    if level:
        if level not in LEVELS:
            raise ToolError(f"level must be one of {list(LEVELS)}")
        d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = LEVELS[level]
        _note_source(d, "aero.fidelity", f"tool argument level={level}")
    if consistency_order is not None:
        if consistency_order not in (0, 1):
            raise ToolError("consistency_order must be 0 or 1")
        d.setdefault("assumptions", {}).setdefault("mdo", {})["consistency_order"] = consistency_order
        _note_source(d, "mdo.consistency_order", "tool argument consistency_order")
    run = _new_run("optimize", d, origin, {"objective": objective, "solver": solver, "max_iter": max_iter,
                                           "level": level, "consistency_order": consistency_order})
    if job is not None:
        job.run_id = run.id
    out = run.path / "mdo"
    try:
        with _quiet():
            r = optimize_pipeline(run.record["files"]["spec"], out, objective, solver, max_iter, verbose=False)
    except RuntimeError as e:
        run.finish({"error": str(e)}, status="failed", error=str(e))
        return {"run_id": run.id, "status": "failed", "error": str(e),
                "hint": "the baseline must converge first: run size on the same spec and read its issues"}
    o = r["opt"]
    pb, po = o["pipeline"]["baseline"], o["pipeline"]["optimum"]
    summ = clean({"objective": o.get("objective"), "solver": o.get("solver"), "improved": o.get("improved"),
                  "trust_region_iterations": len(o.get("trust_region", [])),
                  "trust_region": [{k: h.get(k) for k in ("iter", "delta", "predicted", "actual", "rho", "accepted",
                                                          "new_failures", "status", "status_note")}
                                   for h in o.get("trust_region", [])],
                  "W0_cap_kg": o.get("W0_cap"), "x_baseline": o.get("x_baseline"), "x_optimum": o.get("x_optimum"),
                  "baseline": pb, "optimum": po})
    files = {"mdo_report": str(r["report"]), "mdo_json": str(out / "mdo.json"),
             "baseline_report": str(out / "baseline" / "report.md")}
    if (out / "optimum" / "report.md").exists():
        files["optimum_report"] = str(out / "optimum" / "report.md")
    run.finish(summ, files)
    return {"run_id": run.id, "status": "done", "summary": summ, "files": files}


# --------------------------------------------------------------------------------------------- wing box
def wingbox(job=None, *, spec=None, spec_path=None, run_id=None, example=None, phase: int = 5,
            objective: str | None = None, material: str | None = None, maxiter: int | None = None,
            fem: bool = True, materials: dict | None = None) -> dict:
    """Wing-box study. ``phase=5``: spar positions / t/c / thickness optimisation with t/c sweep + shell FEM
    check; ``phase=6``: stringers, ribs, skin panels with isotropic-equivalent materials (``material`` kind
    'metal'|'composite' or library key)."""
    from acdt.core.pipeline import run_pipeline
    d, origin = _resolve(spec, spec_path, run_id, example)
    _apply_external(d, materials, None)
    run = _new_run("wingbox", d, origin, {"phase": phase, "objective": objective, "material": material,
                                          "maxiter": maxiter, "fem": fem})
    if job is not None:
        job.run_id = run.id
    lg = _log(job)
    stem = Path(run.record["files"]["spec"]).stem
    with _quiet():
        res = run_pipeline("aircraft", run.record["files"]["spec"])["result"]
        obj = objective or ("endurance" if res.sizing.energy_J else "range")
        if phase == 5:
            from acdt.domains.aircraft.wingbox.study import run_study
            s = run_study(res, run.path / "wingbox", obj, stem, maxiter=maxiter or 40, fem=fem, log=lg)
        elif phase == 6:
            from acdt.domains.aircraft.wingbox.study6 import run_study6
            p5 = None
            if run_id:
                prev = registry.load(run_id).path / "wingbox" / f"{stem}_wingbox.json"
                p5 = str(prev) if prev.exists() else None
            s = run_study6(res, run.path / "wingbox", obj, stem, material=material, maxiter=maxiter or 30, fem=fem,
                           phase5_json=p5, log=lg)
        else:
            raise ToolError("phase must be 5 or 6")
    b, o = s["baseline"], s["optimum"]
    summ = clean({"objective": obj, "phase": phase,
                  "box_mass_kg": {"baseline": b.get("box_mass_kg"), "optimum": o.get("box_mass_kg")},
                  "L_D": {"baseline": (b.get("cruise") or {}).get("L_D"), "optimum": (o.get("cruise") or {}).get("L_D")},
                  "x_optimum": o.get("x"), "phase6": o.get("phase6"), "n_str": s.get("n_str"),
                  "fem_optimum": s.get("fem_optimum"), "fem_error": s.get("fem_error"), "wall_s": s.get("wall_s")})
    files = {**{k: v for k, v in s.get("paths", {}).items()}, **_files_in(run.path / "wingbox")}
    run.finish(summ, files)
    return {"run_id": run.id, "status": "done", "summary": summ, "files": files}


# --------------------------------------------------------------------------------------------- RCS
def rcs(job=None, *, spec=None, spec_path=None, run_id=None, example=None, mode: str = "study",
        freq_ghz: float = 10.0, samples: int = 80, refine: list[float] | None = None, seed: int = 0,
        stl_path: str | None = None) -> dict:
    """Radar cross-section (physical optics, faceted). ``mode``: 'validate' (PO vs analytic canonical cases),
    'study' (aero/RCS shaping trade on a sized design; reuses the result.json of a ``size`` run_id when given) or
    'stl' (polar of a triangulated STL)."""
    from acdt.core.em import validate as em_val
    from acdt.core.em.po import LIMITATIONS
    from acdt.domains.aircraft.rcs import study
    f = freq_ghz * 1e9
    if mode == "validate":
        with _quiet():
            cases = em_val.cases(f)
        return clean({"status": "done", "ok": all(c["ok"] for c in cases), "cases": cases, "limitations": LIMITATIONS})
    if mode == "stl":
        if not stl_path or not Path(stl_path).exists():
            raise ToolError("mode 'stl' needs an existing stl_path")
        run = registry.new_run("rcs", Path(stl_path).stem, {"mode": mode, "stl_path": stl_path, "freq_ghz": freq_ghz})
        with _quiet():
            r = study.stl_polar(stl_path, run.path / f"{Path(stl_path).stem}_rcs_polar.png", f)
        summ = clean({"frontal": r.get("frontal"), "n_facets": r.get("n_facets"), "limitations": LIMITATIONS})
        run.finish(summ, {"polar": r.get("png")})
        return {"run_id": run.id, "status": "done", "summary": summ, "files": {"polar": r.get("png")}}
    if mode != "study":
        raise ToolError("mode must be validate | study | stl")
    result_json = None
    if run_id:
        rr = registry.load(run_id)
        cand = rr.record.get("files", {}).get("result.json")
        if cand and Path(cand).exists():
            result_json = cand
    if result_json is None:
        r0 = size(job, spec=spec, spec_path=spec_path, run_id=run_id, example=example)
        if r0.get("status") != "done":
            return r0
        result_json, run_id = r0["result_json"], r0["run_id"]
    d, origin = _resolve(None, None, run_id, None)
    run = _new_run("rcs", d, origin, {"mode": mode, "freq_ghz": freq_ghz, "samples": samples, "refine": refine,
                                      "seed": seed})
    if job is not None:
        job.run_id = run.id
    with _quiet():
        r = study.run_study(result_json, run.path / "rcs", f, samples, tuple(refine or ()), seed, log=_log(job))
    picks = {k: {"shape": v.get("shape"), "perf_ratio": (v.get("aero") or {}).get("perf_ratio"),
                 "L_D": (v.get("aero") or {}).get("LD"), "rcs_frontal_mean_dbsm": ((v.get("rcs") or {}).get("all") or {})
                 .get("mean_dbsm")} for k, v in (r.get("picks") or {}).items()}
    summ = clean({"freq_GHz": freq_ghz, "n_doe": r.get("n_doe"), "n_feasible": r.get("n_feasible"), "picks": picks,
                  "baseline_rcs_frontal_mean_dbsm": (((r.get("baseline") or {}).get("rcs") or {}).get("all") or {})
                  .get("mean_dbsm"), "limitations": LIMITATIONS, "wall_s": r.get("wall_s")})
    files = {**r.get("files", {}), "rcs_study_json": str(run.path / "rcs" / "rcs_study.json")}
    run.finish(summ, files)
    return {"run_id": run.id, "status": "done", "summary": summ, "files": files}


# --------------------------------------------------------------------------------------------- high fidelity
def hifi_estimate(steps: list[str] | None = None, continue_run: str | None = None, force: bool = False) -> dict:
    """Cost/permission estimate of the hifi steps (no compute)."""
    from acdt.domains.aircraft.hifi.run import STEPS
    out = (registry.load(continue_run).path / "hifi") if continue_run else None
    e = guard.estimate(list(steps or STEPS), out, force, user_approved=False)
    try:
        from acdt.domains.aircraft.hifi.tools import mem_available_gb, cores
        e["machine"] = {"cpu_cores": cores(), "mem_available_gb": round(mem_available_gb(), 1)}
    except Exception:  # pragma: no cover
        pass
    return e


def hifi(job=None, *, spec=None, spec_path=None, run_id=None, example=None, steps: list[str] | None = None,
         user_approved: bool = False, approval_note: str | None = None, continue_run: str | None = None,
         force: bool = False) -> dict:
    """High-fidelity chain (OpenVSP geometry, SU2 2-D/3-D, CalculiX FEM, flutter, Nastran decks, detailed sizing,
    calibration factors) under the compute guard. Heavy steps need ``user_approved=True`` (explicit consent of
    the user for *this* run on *this* machine; put their words in ``approval_note``). ``continue_run``: reuse the
    folder of a previous hifi run (steps already computed are not recomputed)."""
    from acdt.domains.aircraft.hifi.run import STEPS, run_hifi
    steps = list(steps or STEPS)
    prev = registry.load(continue_run) if continue_run else None
    if prev is not None and not any((spec, spec_path, run_id, example)):
        d, origin = _resolve(None, None, continue_run, None)
    else:
        d, origin = _resolve(spec, spec_path, run_id, example)
    out_prev = prev.path / "hifi" if prev else None
    g = guard.estimate(steps, out_prev, force, user_approved)
    if g["verdict"] != "ok":
        return {"status": g["verdict"], "guard": g, "run_id": None,
                "hint": "nothing was run. Ask the user for explicit approval of the heavy steps (they use this "
                        "machine's CPU/RAM), or call with only the light steps"}
    run = _new_run("hifi", d, origin, {"steps": steps, "user_approved": user_approved,
                                       "approval_note": approval_note, "continue_run": continue_run, "force": force})
    if job is not None:
        job.run_id = run.id
    out = run.path / "hifi"
    if out_prev and out_prev.exists():
        shutil.copytree(out_prev, out, dirs_exist_ok=True)
    with _quiet():
        R = run_hifi(run.record["files"]["spec"], out, tuple(steps), force, log=_log(job))
    st = {}
    for k, v in R["steps"].items():
        if v is None:
            st[k] = {"status": "not run"}
        elif "skipped" in v:
            st[k] = {"status": "skipped", "reason": str(v["skipped"]).splitlines()[0]}
        else:
            st[k] = {"status": "ok", "json": str(out / guard.STEP_COST[k]["json"])}
    cal = R.get("calibration") or {}
    summ = clean({"steps": st, "guard": g, "calibration_factors": {k: {"value": f.get("value"), "group": f.get("group"),
                                                                        "what": f.get("what")}
                                                                    for k, f in (cal.get("factors") or {}).items()}})
    files = {"report_fase4": R.get("report"), "calibration_json": str(out / "calibration.json")
             if (out / "calibration.json").exists() else None}
    run.finish(summ, files)
    return {"run_id": run.id, "status": "done", "summary": summ, "files": {k: v for k, v in files.items() if v}}


# --------------------------------------------------------------------------------------------- calibration
def get_calibration(run_id: str | None = None, path: str | None = None) -> dict:
    """Calibration factors (L3 → L1/L2) of a hifi run or a calibration.json."""
    if run_id:
        p = registry.load(run_id).path / "hifi" / "calibration.json"
    elif path:
        p = Path(path)
    else:
        raise ToolError("give run_id (of a hifi run) or path (calibration.json)")
    if not p.exists():
        raise ToolError(f"no calibration.json at {p}")
    return {"path": str(p), "calibration": clean(json.loads(p.read_text(encoding="utf-8")))}


def apply_calibration(*, spec=None, spec_path=None, run_id=None, example=None, calibration_run: str | None = None,
                      calibration_file: str | None = None, apply: list[str] | None = None,
                      factors: dict | None = None) -> dict:
    """Set ``assumptions.calibration`` (file and/or inline factors, groups to apply: 'aero', 'flutter') on a design
    and record it as a new ``calibrated`` spec run (no compute) — pass its run_id to ``size``/``optimize``."""
    from acdt.domains.aircraft.hifi.calibration import APPLICABLE
    d, origin = _resolve(spec, spec_path, run_id, example)
    f = None
    if calibration_run:
        f = str(registry.load(calibration_run).path / "hifi" / "calibration.json")
    elif calibration_file:
        f = str(Path(calibration_file).resolve())
    if f and not Path(f).exists():
        raise ToolError(f"calibration file {f} not found")
    bad = set(apply or []) - set(APPLICABLE)
    if bad:
        raise ToolError(f"apply groups must be in {APPLICABLE} (got {sorted(bad)})")
    c = d.setdefault("assumptions", {}).setdefault("calibration", {})
    if f:
        c["file"] = f
    c["apply"] = list(apply or [])
    if factors:
        c["factors"] = factors
    run = _new_run("calibration", d, origin, {"calibration_run": calibration_run, "calibration_file": f,
                                              "apply": apply, "factors": factors})
    run.finish({"calibration": run.record["calibration"]})
    return {"run_id": run.id, "status": "done", "calibration": run.record["calibration"],
            "next": "call size/optimize with run_id=" + run.id}


# --------------------------------------------------------------------------------------------- registry tools
def list_examples() -> dict:
    return {"examples": clean(catalogue.examples())}


def get_run(run_id: str, include: list[str] | None = None) -> dict:
    """The run record (inputs, assumptions, versions, git, outputs, files, calibration, external data).
    ``include`` limits the keys (e.g. ['outputs', 'files'])."""
    r = registry.load(run_id).record
    if include:
        r = {k: r.get(k) for k in ["run_id", "tool", "status", *include]}
    return clean(r)


def list_runs(tool: str | None = None, limit: int = 50) -> dict:
    return {"runs_root": str(registry.runs_root()), "runs": registry.list_runs(tool, limit)}


def _num_leaves(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_num_leaves(v, f"{prefix}{k}."))
    elif isinstance(d, bool):
        out[prefix[:-1]] = d
    elif isinstance(d, (int, float)):
        out[prefix[:-1]] = d
    return out


def compare_runs(run_ids: list[str], metrics: list[str] | None = None) -> dict:
    """Side-by-side numeric outputs of several runs (keys common to all; ``metrics`` = dotted keys or prefixes to
    keep) with the relative change vs the first run."""
    if len(run_ids) < 2:
        raise ToolError("give at least two run ids")
    recs = [registry.load(r).record for r in run_ids]
    leaves = [_num_leaves(r.get("outputs") or {}) for r in recs]
    keys = set(leaves[0]).intersection(*leaves[1:])
    if metrics:
        keys = {k for k in keys if any(k == m or k.startswith(m + ".") for m in metrics)}
    rows = []
    for k in sorted(keys):
        vals = [lv[k] for lv in leaves]
        row = {"metric": k, "values": vals}
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals) and vals[0]:
            row["rel_change_vs_first"] = [v / vals[0] - 1 for v in vals]
        if len(set(map(str, vals))) > 1:
            rows.append(row)
    return clean({"runs": [{k: r.get(k) for k in ("run_id", "tool", "name", "created")} for r in recs],
                  "differences": rows, "n_common_metrics": len(keys),
                  "assumption_differences": _assumption_diff(recs)})


def _assumption_diff(recs):
    maps = [{a["path"]: a["value"] for a in r.get("assumptions", [])} for r in recs]
    keys = set().union(*maps)
    return [{"path": k, "values": [m.get(k) for m in maps]} for k in sorted(keys)
            if len({json.dumps(m.get(k), sort_keys=True, default=str) for m in maps}) > 1]


# --------------------------------------------------------------------------------------------- report
def report(run_ids: list[str], title: str = "acdt design dossier", notes: str | None = None) -> dict:
    """Design dossier (markdown + JSON) over several runs: what was done, key results, assumptions and their
    sources, external data provenance, calibration, validity limits/issues, links to the full reports."""
    recs = [registry.load(r).record for r in run_ids]
    run = registry.new_run("report", title, {"run_ids": run_ids, "notes": notes})
    L = [f"# {title}", "", f"Gerado: {registry.now_iso()} · acdt {registry.versions()['acdt']} · git "
         f"{(registry.git_info().get('commit') or 'n/a')[:10]}", ""]
    if notes:
        L += [notes, ""]
    L += ["## Corridas", "", "| run | ferramenta | estado | criado |", "|---|---|---|---|"]
    L += [f"| `{r['run_id']}` | {r['tool']} | {r['status']} | {r['created']} |" for r in recs]
    for r in recs:
        o = r.get("outputs") or {}
        L += ["", f"## {r['tool']} — {r.get('name')} (`{r['run_id']}`)", ""]
        if r["tool"] in ("size", "systems"):
            w, dp = o.get("weights") or {}, o.get("design_point") or {}
            wing = (o.get("geometry") or {}).get("wing") or {}
            L += [f"- Viável: **{o.get('feasible')}**; W0 = {_f(w.get('W0_kg'))} kg, We/W0 = {_f(w.get('We_W0'))}, "
                  f"bateria = {_f(w.get('battery_energy_Wh'))} Wh",
                  f"- W/S = {_f(dp.get('W_S_kg_m2'))} kg/m², {dp.get('metric')} = {_f(dp.get('value'))}; ativas: "
                  f"{', '.join(dp.get('active_constraints') or [])}",
                  f"- Asa: S = {_f(wing.get('S_m2'))} m², b = {_f(wing.get('span_m'))} m, AR = {_f(wing.get('AR'))}"]
            for c in o.get("failed_checks") or []:
                L.append(f"- FALHA {c['key']}: {c['message']}")
        elif r["tool"] == "optimize":
            L.append(f"- Objetivo {o.get('objective')} ({o.get('solver')}); melhoria aceite: {o.get('improved')}")
            for k in ("W0 [kg]", "AR", "W/S [N/m²]", "b [m]", "energia bateria [Wh]", "autonomia (segmentos) [h]",
                      "alcance (segmentos) [km]", "falhas"):
                if k in (o.get("baseline") or {}):
                    L.append(f"- {k}: {_f(o['baseline'][k])} → {_f((o.get('optimum') or {}).get(k))}")
        else:
            for k, v in o.items():
                if isinstance(v, (int, float, str, bool)) or v is None:
                    L.append(f"- {k}: {_f(v)}")
                elif isinstance(v, dict) and len(json.dumps(v, default=str)) < 300:
                    L.append(f"- {k}: `{json.dumps(v, default=str, ensure_ascii=False)}`")
        user = [a for a in r.get("assumptions", []) if not a["source"].startswith("assumed")]
        if user:
            L += ["", "Pressupostos fornecidos (fonte):", ""]
            L += [f"- `{a['path']}` = `{json.dumps(a['value'], default=str, ensure_ascii=False)[:80]}` — {a['source']}"
                  for a in user[:40]]
        nd = sum(a["source"].startswith("assumed") for a in r.get("assumptions", []))
        if nd:
            L.append(f"- {nd} valores por omissão do acdt (DEFAULT_ASSUMPTIONS; ver `run.json`).")
        for e in r.get("external_data") or []:
            p = e.get("provenance") or {}
            L.append(f"- Dado externo {e['kind']} **{e.get('name')}** → `{e['path']}`: {p.get('source_url')} "
                     f"({p.get('source_type')}, obtido {p.get('retrieved')})")
        if r.get("calibration"):
            L.append(f"- Calibração: `{json.dumps(r['calibration'], default=str, ensure_ascii=False)[:300]}`")
        for k, v in (r.get("files") or {}).items():
            if k.endswith((".md",)) or k in ("mdo_report", "report_fase4", "baseline_report", "optimum_report"):
                L.append(f"- Relatório: [{k}]({v})")
        iss = [i for i in (o.get("issues") or []) if isinstance(i, dict) and i.get("severity") in ("warning", "error")]
        if iss:
            L += ["", "Limitações / avisos:", ""] + [f"- [{i['severity']}] {i['message']}" for i in iss[:15]]
        if o.get("limitations"):
            L.append(f"- Limitações do método: {o['limitations']}")
    L += ["", "---", "Métodos clássicos citados nos módulos (ver recurso `acdt://methods`). Valores por omissão e "
          "pressupostos estão marcados; nenhum valor foi inventado pelo agente — os dados externos têm fonte e data."]
    md = run.path / "dossier.md"
    md.write_text("\n".join(L) + "\n", encoding="utf-8")
    (run.path / "dossier.json").write_text(json.dumps(clean(recs), indent=1, ensure_ascii=False), encoding="utf-8")
    run.finish({"n_runs": len(recs)}, {"dossier_md": md, "dossier_json": run.path / "dossier.json"})
    return {"run_id": run.id, "status": "done", "files": {"dossier_md": str(md), "dossier_json": str(run.path / "dossier.json")}}


def _f(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    return "n/a" if v is None else str(v)


# --------------------------------------------------------------------------------------------- manufacturing / cost
def _mfg_materials(materials: dict) -> dict:
    """{key: library key | material dict (kind, rho, E, Ftu, price{usd_per_kg, year, provenance}, base?)}."""
    from acdt.domains.aircraft.manufacturing.study import resolve_materials
    out = {}
    for k, v in (materials or {}).items():
        out[k] = {"base": v} if isinstance(v, str) else v
    try:
        return resolve_materials(out)
    except (KeyError, ValueError) as e:
        raise ToolError(f"materials: {e}") from e


def manufacturing_plan(job=None, *, spec=None, spec_path=None, run_id=None, example=None,
                       manufacturing: dict | None = None, pareto: dict | None = None, level: str | None = "L0") -> dict:
    """Size the design, decompose it into parts, choose a process + material per part at quantity N (process
    models: FOPV/ACCEM hours, buy-to-fly, rivets, tooling, learning) and cost it bottom-up and top-down (modified
    Eastlake, DAPCA IV), with optional validation against a public price and a W0–cost Pareto sweep.
    ``manufacturing``: the ``assumptions.manufacturing`` block (see docs/tutorial-fase7-fabrico-custo.md);
    material prices are INPUTS with provenance (research them: distributor/manufacturer page + retrieved date)."""
    from acdt.domains.aircraft.manufacturing.study import run_files
    d, origin = _resolve(spec, spec_path, run_id, example)
    mcfg = manufacturing or (d.get("assumptions") or {}).get("manufacturing")
    if not mcfg:
        raise ToolError("manufacturing config missing: pass manufacturing={year, N, materials, groups: {default}, "
                        "...} or put it in assumptions.manufacturing")
    if level:
        if level not in LEVELS:
            raise ToolError(f"level must be one of {list(LEVELS)}")
        d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = LEVELS[level]
        _note_source(d, "aero.fidelity", f"tool argument level={level}")
    d.setdefault("assumptions", {})["manufacturing"] = mcfg
    run = _new_run("manufacturing_plan", d, origin, {"level": level, "pareto": bool(pareto)})
    if job is not None:
        job.run_id = run.id
    out = run.path / "manufacturing"
    try:
        with _quiet():
            r = run_files({"mission": run.record["files"]["spec"], "manufacturing": mcfg, "pareto": pareto}, out,
                          pareto=bool(pareto), log=_log(job))
    except (KeyError, ValueError) as e:
        run.finish({"error": str(e)}, status="failed", error=str(e))
        return {"run_id": run.id, "status": "failed", "error": str(e)}
    st = r["study"]
    pl = st["plan"]
    warn = sorted({w for row in pl["parts"] if row["selected"] for w in row["selected"]["warnings"]})
    prov = {k: m.get("price_issues") for k, m in pl["materials"].items() if m.get("price_issues")}
    summ = clean({"N": st["N"], "year": st["year"], "selection": pl["selection"], "unresolved_parts":
                  pl["unresolved_parts"], "structure_totals": pl["totals"], "learning_factor": pl["learning_factor"],
                  "mass_change": pl.get("mass_change"), "bottom_up": st["bottom_up"],
                  "eastlake": {k: st["topdown"]["eastlake"].get(k) for k in ("unit_cost", "hours")},
                  "dapca4": {k: st["topdown"]["dapca4"].get(k) for k in ("unit_cost", "hours")},
                  "calibration": st["calibration"], "validation": st.get("validation"),
                  "fidelity": {"recommended": st["fidelity"]["recommended"],
                               "why": st["fidelity"]["recommended_why"],
                               "levels": {k: {"unit_cost": v["unit_cost"], "confidence": v["confidence"],
                                              "aace_class": v["band"]["aace_class"], "low": v["band"]["low"],
                                              "high": v["band"]["high"]}
                                          for k, v in st["fidelity"]["levels"].items()},
                               "L0_outside_database": st["fidelity"]["levels"]["L0"]["reasons"],
                               "calibration_factors": {k: f.get("value") for k, f in
                                                       st["fidelity"]["calibration_out"]["factors"].items()
                                                       if f.get("value") is not None},
                               "applied_calibration": st["fidelity"]["applied_calibration"]},
                  "operating": st.get("operating"), "warnings": warn, "price_provenance_issues": prov,
                  "pareto": None if "pareto" not in r else [{k: q[k] for k in ("option", "ws", "AR", "W0", "unit_cost")}
                                                             for q in r["pareto"]["pareto"]]})
    files = {k: v for k, v in r["files"].items() if v}
    run.finish(summ, files)
    return {"run_id": run.id, "status": "done", "summary": summ, "report": files.get("md"), "files": files}


def cost_estimate(*, We_kg: float, V_H_kt: float, N: int, year: int = 2025, method: str = "both",
                  power_bhp: float | None = None, n_engines: int = 1, engine_cost: dict | None = None,
                  avionics_cost: dict | None = None, propeller_cost: dict | None = None, f_comp: float = 0.0,
                  airframe_fraction_of_empty: float = 0.65, n_flight_test: int = 2, eastlake: dict | None = None,
                  dapca: dict | None = None, learning: dict | None = None, operating: dict | None = None,
                  configuration: list[str] | None = None, unmanned: bool = False,
                  propulsion: str | None = None) -> dict:
    """Top-down unit production cost (modified Eastlake — Gudmundsson 2014; DAPCA IV — Raymer) in USD of
    ``year`` (CPI-U). Purchased items as {usd, year, source_url}; a piston engine without a quote uses the Eastlake
    CER on ``power_bhp``. ``learning``: {slope, theory, n_from, n_to} → learning-curve factors.
    ``operating``: costing.OperatingInputs fields (optional eastlake/dapca CER for unit_price) → DOC; status ok|partial|unassessed (missing activated terms never a silent zero).
    Fidelity L0: the result carries ``confidence`` (CER database applicability: ``configuration`` features,
    ``unmanned``, ``propulsion``) and the AACE 18R-97 Class 5 band — refine with manufacturing_plan (L1/L2)."""
    from acdt.domains.aircraft.cost import EastlakeInputs, eastlake_unit_cost, piston_engine_cost
    from acdt.domains.aircraft.manufacturing import refdata as R
    from acdt.domains.aircraft.manufacturing.costing import (DapcaInputs, dapca4,
                                                            learning_factor, learning_unit)
    if method not in ("eastlake", "dapca4", "both"):
        raise ToolError("method: eastlake | dapca4 | both")
    try:
        cpi = R.cpi_factor(int(year), 2012)
    except KeyError as e:
        raise ToolError(f"no CPI-U for {e}: years {sorted(R.CPI_U)}") from e

    def esc(it, what):
        if it is None:
            return None
        if "usd" not in it:
            raise ToolError(f"{what}: give {{usd, year, source_url}}")
        y = int(it.get("year", year))
        return float(it["usd"]) * (R.cpi_factor(int(year), y) if y != int(year) else 1.0)
    notes = []
    eng = esc(engine_cost, "engine_cost")
    if eng is None:
        if power_bhp:
            eng = piston_engine_cost(power_bhp, n_engines, cpi)
            notes.append("engine: Eastlake piston CER (Gudmundsson 2014 eq. 2.12) — give a quote if available")
        else:
            eng = 0.0
            notes.append("engine cost NOT included (give engine_cost or power_bhp for a piston engine)")
    avi = esc(avionics_cost, "avionics_cost")
    if avi is None:
        avi = 15000.0 * cpi
        notes.append("avionics: Gudmundsson default 15000 USD-2012 × CPI (ASSUMPTION — give a quote)")
    prop = esc(propeller_cost, "propeller_cost") or 0.0
    out = {"year": year, "cpi_2012": cpi, "N": N, "notes": notes}
    if method in ("eastlake", "both"):
        ei = EastlakeInputs(W_airframe_kg=airframe_fraction_of_empty * We_kg, V_H_kt=V_H_kt, N=N, cpi=cpi,
                            engine_cost=eng, avionics_cost=avi, propeller_cost=prop, f_comp=f_comp,
                            **{"Q_m": N / 60.0, **(eastlake or {})})
        out["eastlake"] = eastlake_unit_cost(ei).as_dict()
    if method in ("dapca4", "both"):
        out["dapca4"] = dapca4(DapcaInputs(We_kg=We_kg, V_kt=V_H_kt, Q=N, FTA=n_flight_test, cpi=cpi,
                                           n_engines=1, engine_cost=eng, avionics_cost=avi + prop,
                                           **(dapca or {})))
    if learning:
        lc = {"slope": R.LEARNING_DEFAULT["slope"], "theory": "crawford", **learning}
        out["learning"] = {"slope": lc["slope"], "theory": lc["theory"],
                           "average_factor_N": learning_factor(N, lc["slope"], lc["theory"]),
                           "unit_factor_N": learning_unit(1.0, N, lc["slope"]), "source": R.ref("crawford1944")}
    if operating:
        try:
            from acdt.domains.aircraft.manufacturing.costing import operational_cost_from_dict
            out["operating"] = operational_cost_from_dict(operating)
        except (TypeError, ValueError) as e:
            raise ToolError(f"operating: {e}") from e
    from acdt.domains.aircraft.manufacturing import fidelity as FID
    reasons = []
    if configuration:
        reasons.append("unconventional configuration (" + ", ".join(configuration) + "): outside the Eastlake (GA) "
                       "and DAPCA IV (military/transport) databases")
    if unmanned:
        reasons.append("unmanned: both CER databases are crewed aircraft")
    if propulsion and propulsion not in ("piston_prop", "turboprop", "jet", "turbofan", "turbojet"):
        reasons.append(f"propulsion '{propulsion}' not represented in the CER databases")
    vals = [out[k]["unit_cost"] for k in ("eastlake", "dapca4") if k in out]
    central = out["eastlake"]["unit_cost"] if "eastlake" in out else vals[0]
    out["confidence"] = {"level": "L0", "confidence": "low" if reasons else "medium", "outside_database": bool(reasons),
                         "reasons": reasons, "band": FID.band(central, 5, 1.0 if reasons else 0.0),
                         "model_spread": max(vals) / min(vals) if len(vals) == 2 else None,
                         "next": "L1: manufacturing_plan (part/process bottom-up); L2: manufacturing_plan with "
                                 "detailed={parts, bom, quotes} — each calibrates the level below"}
    return clean(out)


def process_options(*, part: dict, materials: dict, N: int = 100, year: int = 2025,
                    processes: list[str] | None = None, process_inputs: dict | None = None,
                    learning: dict | None = None, tooling_pool: float | None = None) -> dict:
    """Feasibility, hours, buy-to-fly, cycle time, tooling and unit cost of one part for every candidate
    material × process at quantity N (process selection). ``part``: {name, kind, mass_kg, area_m2, perimeter_m,
    max_dim_m, thickness_m, count, double_curvature, axisymmetric, n_plies, material}. ``materials``: {key: library
    key or dict with kind, rho, E, Ftu, price{usd_per_kg, year, provenance}}."""
    from acdt.domains.aircraft.manufacturing import PROCESSES, Part, plan
    mats = _mfg_materials(materials)
    try:
        p = Part(**part)
    except TypeError as e:
        raise ToolError(f"part: {e} (fields: {list(Part.__dataclass_fields__)})") from e
    if p.material is None:
        p.material = next(iter(mats))
    bad = [x for x in (processes or []) if x not in PROCESSES]
    if bad:
        raise ToolError(f"unknown processes {bad}; available {list(PROCESSES)}")
    ch = {"*": {"materials": list(mats), **({"processes": processes} if processes else {})}}
    r = plan([p], mats, N, choices=ch, process_inputs=process_inputs, year=year, learning=learning,
             tooling_pool=tooling_pool)
    row = r["parts"][0]
    keep = ("process", "material", "feasible", "reasons", "warnings", "missing", "labour_hours", "labour_rate_usd_h",
            "labour_cost", "cycle_time_h", "cure_h", "bought_mass_kg", "mass_kg", "b2f", "material_cost",
            "fasteners", "fastener_cost", "machine_cost", "tooling_cost", "tooling_per_unit", "unit_cost")
    opts = sorted(([{k: o.get(k) for k in keep} for o in row["options"]]),
                  key=lambda o: (not o["feasible"], o["unit_cost"] is None, o["unit_cost"] or 0))
    sel = row["selected"]
    return clean({"part": row["part"], "N": N, "year": year, "learning_factor": r["learning_factor"],
                  "selected": None if sel is None else {"process": sel["process"], "material": sel["material"],
                                                        "unit_cost": sel["unit_cost"]},
                  "options": opts, "materials": r["materials"], "notes": r["notes"],
                  "processes_available": {k: v["desc"] for k, v in PROCESSES.items()}})


def compare_materials(*, materials: dict, requirement: str = "panel_stiffness", reference: str | None = None,
                      year: int = 2025, b2f: dict | None = None) -> dict:
    """Rank candidate materials for a part by Ashby performance index (equal geometry envelope): relative mass
    and relative bought-material cost (mass × buy-to-fly × price escalated to ``year``). Requirements:
    tie/beam/panel × stiffness/strength. ``materials``: {key: library key or dict with price + provenance}."""
    from acdt.domains.aircraft.manufacturing.plan import price_material
    from acdt.domains.aircraft.manufacturing.selection import EXPONENTS, compare
    if requirement not in EXPONENTS:
        raise ToolError(f"requirement must be one of {list(EXPONENTS)}")
    mats = {k: price_material(m, year) for k, m in _mfg_materials(materials).items()}
    if reference and reference not in mats:
        raise ToolError(f"reference {reference!r} not in materials")
    r = compare(mats, requirement, reference, b2f)
    r["price_issues"] = {k: m.get("price_issues") for k, m in mats.items() if m.get("price_issues")}
    r["no_price"] = [k for k, m in mats.items() if m.get("usd_per_kg") is None]
    return clean(r)


# --------------------------------------------------------------------------------------------- phase 8: flight
def _sized_res(job, tool: str, d: dict, origin: dict, inputs: dict, level: str = "L1"):
    """New run + full pipeline (AVL needs the L1 level); returns (run, res) or (run, error dict)."""
    from acdt.core.pipeline import InfeasibleError, run_pipeline
    from acdt.core.requirements import RequirementError
    if level not in LEVELS:
        raise ToolError(f"level must be one of {list(LEVELS)}")
    d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = LEVELS[level]
    _note_source(d, "aero.fidelity", f"tool argument level={level}")
    if not shutil.which("avl"):
        raise ToolError("AVL not found on PATH — control sizing and the flight model need AVL 3.40")
    run = _new_run(tool, d, origin, inputs)
    if job is not None:
        job.run_id = run.id
    try:
        with _quiet():
            st = run_pipeline("aircraft", run.record["files"]["spec"], output=run.path / "size")
    except (InfeasibleError, RequirementError) as e:
        run.finish({"feasible": False, "error": str(e)}, status="infeasible", error=str(e))
        return run, {"run_id": run.id, "status": "infeasible", "error": str(e)}
    return run, st["result"]


def size_control_surfaces(job=None, *, spec=None, spec_path=None, run_id=None, example=None,
                          options: dict | None = None, level: str = "L1") -> dict:
    """Size aileron (roll performance: CS-23.157 / MIL-F-8785C time-to-bank), elevator (take-off rotation, trim
    over the CG range and flap settings), rudder (crosswind, OEI) and flaps (CLmax), plus hinge moments/servo
    torques, with AVL. ``options`` override ``assumptions.stability.controls`` (design choices: deflection
    limits, candidate ranges, crosswind, flap settings…)."""
    from acdt.domains.aircraft.flightsim.study import controls_study
    d, origin = _resolve(spec, spec_path, run_id, example)
    run, res = _sized_res(job, "size_control_surfaces", d, origin, {"options": options, "level": level}, level)
    if isinstance(res, dict):
        return res
    with _quiet():
        s = controls_study(res, run.path / "controls", options)
    files = s.pop("files")
    s.pop("plots", None)
    summ = clean({"layout_current": s["layout_current"], "layout_sized": s["layout_sized"],
                  "aileron": {k: s["aileron"].get(k) for k in ("requirements", "current", "sized", "sized_span_fraction",
                                                               "ok_current", "note")},
                  "elevator": {k: v for k, v in s["elevator"].items() if not isinstance(v, list) or len(v) < 40},
                  "rudder": s["rudder"], "flap": s["flap"], "hinge_moments": s["hinge_moments"], "notes": s["notes"]})
    run.finish(summ, files)
    return {"run_id": run.id, "status": "done", "summary": summ, "files": files}


def _sim_mission(mission, mission_path, mission_example):
    given = [k for k, v in (("mission", mission), ("mission_path", mission_path),
                            ("mission_example", mission_example)) if v]
    if len(given) != 1:
        raise ToolError("give exactly one of mission (dict), mission_path or mission_example "
                        "(see examples/simulation/*.yaml)")
    if mission:
        return mission
    p = Path(mission_path) if mission_path else catalogue.REPO / "examples" / "simulation" / \
        f"{Path(mission_example).stem}.yaml"
    if not p.exists():
        raise ToolError(f"simulation mission {p} not found")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _has_aircraft(ms) -> bool:
    if not isinstance(ms, dict):
        return False
    if isinstance(ms.get("aircraft"), dict):
        return True
    inner = ms.get("mission")
    return isinstance(inner, dict) and isinstance(inner.get("aircraft"), dict)


def _n0_assumptions(ms: dict) -> list[dict]:
    """Provenance of an N0 run: only the aircraft block. Sizing defaults are recorded as not used."""
    ac = ms.get("aircraft") if isinstance(ms.get("aircraft"), dict) else (ms.get("mission") or {}).get("aircraft") or {}
    src = ac.get("source") or "não citada"
    rows = []

    def walk(prefix, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(f"{prefix}.{k}", v)
        elif isinstance(obj, list):
            rows.append({"path": prefix, "value": clean(obj), "source": f"user — {src}"})
        else:
            rows.append({"path": prefix, "value": clean(obj), "source": f"user — {src}"})

    walk("aircraft", ac)
    rows.append({"path": "sizing_defaults", "value": "não usados",
                 "source": "massa pontual N0: os DEFAULT_ASSUMPTIONS de dimensionamento não entram no voo"})
    return rows


def _finish_pointmass(run, r: dict) -> dict:
    files = r.pop("files", {}) or {}
    summ = clean({"name": r.get("name"), "fidelity": "pointmass", "aborted": r.get("aborted"),
                  "aircraft_source": r.get("aircraft_source"), "total_time_min": r["total_time_min"],
                  "total_dist_km": r["total_dist_km"], "unit": r["unit"],
                  "total_used": r.get("total_used_" + r["unit"]), "segments": r["segments"],
                  "metrics": r.get("metrics"), "sensor": r.get("sensor"), "failures": r.get("failures"),
                  "method": r.get("method"), "validity": r.get("validity"), "notes": r.get("notes"),
                  "limitations": [r.get("validity")]})
    run.finish(summ, files)
    return {"run_id": run.id, "status": "done", "summary": summ, "files": files}


def simulate_mission(job=None, *, spec=None, spec_path=None, run_id=None, example=None, mission: dict | None = None,
                     mission_path: str | None = None, mission_example: str | None = None, layout: str = "sized",
                     jsbsim_check: bool = False, options: dict | None = None, level: str = "L1",
                     fidelity: str = "6dof", aircraft: dict | None = None) -> dict:
    """Mission simulation. ``fidelity='6dof'`` (default) is the sized-design runner: AVL tables → in-house
    6-DOF (Stevens & Lewis), autopilot (Beard & McLain), Dryden and gusts, k_energy, handling qualities.
    ``fidelity='pointmass'`` is the quasi-steady 3-DOF judge (Anderson 1999 Ch. 5, Raymer 2018 Ch. 17) for N0
    (aircraft block, no sizing) and N1 (sizing result, no AVL flight model). Same YAML. Sensor footprint and
    deterministic failure hooks are on both; only the point-mass runner flies the failure response."""
    from acdt.domains.aircraft.flightsim.pointmass import simulate_pointmass_mission
    from acdt.domains.aircraft.flightsim.study import simulation_study
    if fidelity not in ("pointmass", "6dof"):
        raise ToolError("fidelity is 'pointmass' or '6dof'")
    ms = _sim_mission(mission, mission_path, mission_example)
    if aircraft is not None:
        ms = copy.deepcopy(ms)
        if isinstance(ms.get("mission"), dict):
            ms["mission"]["aircraft"] = aircraft
        else:
            ms["aircraft"] = aircraft
    has_design = any(v not in (None, "", {}) for v in (spec, spec_path, run_id, example))
    if fidelity == "pointmass" and not has_design:
        if not _has_aircraft(ms):
            raise ToolError("point-mass without a design source needs an aircraft block in the mission "
                            "(or pass spec, spec_path, run_id or example)")
        name = (ms.get("mission") or ms).get("name", "n0") if isinstance(ms, dict) else "n0"
        d = {"name": name, "description": "N0 point-mass", "assumptions": {},
             "assumption_sources": {"*": "bloco aircraft da missão; DEFAULT_ASSUMPTIONS de dimensionamento não usados"}}
        run = _new_run("simulate_mission", d, {"kind": "n0_aircraft", "ref": None, "parent_run": None},
                       {"mission": ms, "fidelity": "pointmass"})
        if job is not None:
            job.run_id = run.id
        run.record["assumptions"] = _n0_assumptions(ms)
        run.save()
        try:
            with _quiet():
                r = simulate_pointmass_mission(ms, run.path / "simulation")
        except ValueError as e:
            run.finish({"error": str(e)}, status="failed", error=str(e))
            return {"run_id": run.id, "status": "failed", "error": str(e)}
        return _finish_pointmass(run, r)
    d, origin = _resolve(spec, spec_path, run_id, example)
    run, res = _sized_res(job, "simulate_mission", d, origin,
                          {"mission": ms, "layout": layout, "jsbsim_check": jsbsim_check, "options": options,
                           "fidelity": fidelity}, level)
    if isinstance(res, dict):
        return res
    if fidelity == "pointmass":
        try:
            with _quiet():
                r = simulate_pointmass_mission(ms, run.path / "simulation", res=res)
        except ValueError as e:
            run.finish({"error": str(e)}, status="failed", error=str(e))
            return {"run_id": run.id, "status": "failed", "error": str(e)}
        return _finish_pointmass(run, r)
    try:
        with _quiet():
            r = simulation_study(res, ms, run.path / "simulation", layout=layout, jsbsim_check=jsbsim_check,
                                 opts=options, log=_log(job))
    except (ValueError, KeyError) as e:
        run.finish({"error": str(e)}, status="failed", error=str(e))
        return {"run_id": run.id, "status": "failed", "error": str(e)}
    if r.get("name") == "tailless_lateral_test":  # tailless split-aileron: lateral test only, no mission
        files = r.pop("files", {})
        summ = clean(r)
        run.finish(summ, files)
        return {"run_id": run.id, "status": "done", "summary": summ, "files": files}
    files = r.pop("files")
    keep = ("t_min", "dist_km", "used_kg", "used_Wh", "extrapolated_min", "V_target_m_s", "Va_mean_m_s", "nz_max",
            "nz_min", "alpha_max_deg", "stall_time_s", "de_sat_pct", "da_sat_pct", "dr_sat_pct", "throttle_sat_pct",
            "k_energy", "quasi_steady_kg", "quasi_steady_Wh", "notes")
    segs = [{"segment": s_["segment"], "type": s_["type"], **{k: s_.get(k) for k in keep if k in s_},
             "metrics": {k: v for k, v in s_.items() if k not in keep and k not in ("segment", "type")}}
            for s_ in r["segments"]]
    summ = clean({"name": r.get("name"), "aborted": r.get("aborted"), "total_time_min": r["total_time_min"],
                  "total_dist_km": r["total_dist_km"], "unit": r["unit"],
                  "total_used": r.get("total_used_" + r["unit"]), "segments": segs,
                  "k_energy_airborne": r.get("quasi_steady", {}).get("k_energy_airborne"),
                  "handling_qualities": r.get("handling_qualities"), "controls_layout": r.get("controls"),
                  "jsbsim": r.get("jsbsim"), "notes": r.get("notes"),
                  "limitations": ["baixa fidelidade: tabelas AVL (potencial, sem fuselagem), perda por mistura "
                                  "sigmoide, sem efeito de solo/sopro da hélice; Dryden light/moderate (Beard & "
                                  "McLain Tab. 4.1); segmentos longos extrapolados em regime estacionário"]})
    run.finish(summ, files)
    return {"run_id": run.id, "status": "done", "summary": summ, "files": files}


def flap_options(job=None, *, spec=None, spec_path=None, run_id=None, example=None, options: list | None = None,
                 objective: str | None = None, min_gain: float | None = None, per_option: dict | None = None,
                 sweep: dict | None = None) -> dict:
    """Phase 9: size the same mission with each trailing-edge option (none / plain / camber / flaperon, plus a
    plain flap of the same flapped area for fairness) and select one; camber/flaperon only if they improve the
    objective by at least ``min_gain`` (default 1 %) over the best simple option. ``sweep`` = {key, values_si}
    for a requirement sweep (Pareto plot)."""
    from acdt.domains.aircraft.design_options import flap_options_report, flap_options_sweep
    from acdt.domains.aircraft.mission import MissionSpec
    d, origin = _resolve(spec, spec_path, run_id, example)
    fo = d.setdefault("assumptions", {}).setdefault("design_options", {}).setdefault("flaps", {})
    for k, v in (("options", options), ("objective", objective), ("min_gain", min_gain), ("per_option", per_option)):
        if v is not None:
            fo[k] = v
            _note_source(d, f"design_options.flaps.{k}", "tool argument")
    run = _new_run("flap_options", d, origin, {"options": options, "objective": objective, "min_gain": min_gain,
                                                "sweep": sweep})
    if job is not None:
        job.run_id = run.id
    out = run.path / "flap_options"
    with _quiet():
        sp = MissionSpec.from_yaml(run.record["files"]["spec"])
        s = flap_options_report(sp, out)
        if sweep:
            pts = flap_options_sweep(sp, sweep["key"], sweep["values_si"], out / f"pareto_{sweep['key']}.png")
            s["sweep"] = pts
            s["files"][f"pareto_{sweep['key']}"] = str(out / f"pareto_{sweep['key']}.png")
    files = s.pop("files")
    summ = clean({**s, "limitations": [
        "camber flap: polares 2D XFOIL/NeuralFoil por deflexão; carga em envergadura do avião limpo; "
        "arrasto de compensação HT (Nelson/Etkin) e gap opt-in (sealed ou dCD com fonte; unassessed≠zero); "
        "massas/custos de atuadores só se dados pelo utilizador"]})
    run.finish(summ, files)
    return {"run_id": run.id, "status": "done", "summary": summ, "files": files}


def certify(job=None, *, spec=None, spec_path=None, run_id=None, example=None, certification: dict | None = None) -> dict:
    """Phase 10: certification basis (CS-23/CS-25/STANAG 4671/4703 + SORA), compliance matrix (CSV/XLSX/MD) with
    automatic status from the design results, low-fi ARP4761 safety assessment (FHA/FTA/FMEA, required MTBF) and a
    redundancy trade whose mass deltas are fed back into W0 (options selected only when needed)."""
    from acdt.domains.aircraft.certify import certify as _certify
    d, origin = _resolve(spec, spec_path, run_id, example)
    if certification:
        d["certification"] = {**(d.get("certification") or {}), **certification}
        _note_source(d, "certification", "tool argument")
    run = _new_run("certify", d, origin, {"certification": certification})
    if job is not None:
        job.run_id = run.id
    out = run.path / "certification"
    with _quiet():
        s = _certify(run.record["files"]["spec"], out, log=lambda m: None)
    files = {p.stem if p.suffix != ".png" else p.name: str(p) for p in sorted(out.glob("*")) if p.is_file()}
    summ = clean({**s, "limitations": [
        "paráfrases do acdt, não o texto oficial; estado automático a nível conceptual — a aceitação é da autoridade",
        "FTA com taxas constantes (exponencial), sem falhas de modo comum, bloqueio/hardover de servos nem software",
        "taxas 'assumption'/'vendor_claim' são PRESSUPOSTOS — ver MTBF requerido e substituir por dados do fornecedor",
        "SORA passo #8 contenção: opt-in com certification.sora.containment; em falta → unassessed≠pass",
        "mitigações estratégicas de risco aéreo (Anexo C) não automatizadas",
        "taxas de fornecedor (C2, FCC, motor UAV): certification.safety.supplier_rates exige source+retrieved"]})
    run.finish(summ, files)
    return {"run_id": run.id, "status": "done", "summary": summ, "files": files}


def safety_assessment(template: str = "uas", scheme: str = "stanag4671", t_flight_h: float = 1.0,
                      mtow_kg: float = 150.0, options: dict | None = None, trade: bool = False,
                      unit: dict | None = None, baseline: dict | None = None, rate_overrides: dict | None = None,
                      severity_overrides: dict | None = None, sora: dict | None = None,
                      supplier_rates: dict | None = None) -> dict:
    """Quick FHA/FTA (no sizing) of a template architecture (uas | ga_piston) against a scheme
    (ac23_1309_class_I..IV | amc25_1309 | stanag4671 | stanag4703); optional redundancy trade and SORA
    ({span_m, v_max_m_s, population, aec, mitigations, vlos, containment?}).
    supplier_rates: {key: {lambda_per_h|mtbf_h, source, retrieved}} — unsourced entries stay unassessed."""
    from acdt.core.certification import sora as S
    from acdt.domains.aircraft import safety_assessment as SA
    try:
        if trade:
            t = SA.redundancy_trade(template, scheme, t_flight_h, mtow_kg, unit or {}, None, rate_overrides,
                                    baseline=baseline, severity_overrides=severity_overrides,
                                    supplier_rates=supplier_rates)
            a = t["selected"]["assessment"]
            out = {"assessment": a, "selected": t["selected"]["options"], "reason": t["reason"],
                   "rows": [{k: r[k] for k in ("options", "meets", "n_fail", "worst_ratio", "dm_kg", "dcost",
                                               "missing_inputs")} for r in t["rows"]]}
        else:
            a = SA.assess(template, options or {}, scheme, t_flight_h, mtow_kg, rate_overrides,
                          severity_overrides=severity_overrides, supplier_rates=supplier_rates)
            out = {"assessment": a, "meets": SA.meets(a)}
        if sora:
            so = S.assess(S.SoraInput(float(sora["span_m"]), float(sora["v_max_m_s"]), sora.get("population", "<50"),
                                      int(sora.get("aec", 10)), sora.get("mitigations") or {}, mtow_kg,
                                      bool(sora.get("vlos", False)), sora.get("containment")))
            out["sora"] = so
    except (KeyError, ValueError) as e:
        raise ToolError(str(e)) from e
    return clean(out)


# --------------------------------------------------------------------------------------------- jobs
TOOLS = {"size": size, "systems": systems, "optimize": optimize, "wingbox": wingbox, "rcs": rcs, "hifi": hifi,
         "manufacturing_plan": manufacturing_plan, "size_control_surfaces": size_control_surfaces,
         "simulate_mission": simulate_mission, "flap_options": flap_options, "certify": certify}


def start(tool: str, wait_s: float = 50.0, **kwargs) -> dict:
    """Run a long tool as a job; return its result if it finishes within ``wait_s`` s, else the job id."""
    if tool not in TOOLS:
        raise ToolError(f"unknown long tool {tool!r}")
    if tool == "hifi":   # guard before queueing — never queue a refused run
        prev = registry.load(kwargs["continue_run"]).path / "hifi" if kwargs.get("continue_run") else None
        from acdt.domains.aircraft.hifi.run import STEPS
        g = guard.estimate(list(kwargs.get("steps") or STEPS), prev, kwargs.get("force", False),
                           kwargs.get("user_approved", False))
        if g["verdict"] != "ok":
            return {"status": g["verdict"], "guard": g, "run_id": None, "job_id": None,
                    "hint": "nothing was run — ask the user for explicit approval of the heavy steps"}
    src = {k: kwargs.get(k) for k in ("spec", "spec_path", "run_id", "example")}
    n0_pointmass = (tool == "simulate_mission" and kwargs.get("fidelity") == "pointmass"
                    and not any(v not in (None, "", {}) for v in src.values()))
    if n0_pointmass and not kwargs.get("aircraft") and not _has_aircraft(kwargs.get("mission") or {}):
        if kwargs.get("mission") is not None or not (kwargs.get("mission_path") or kwargs.get("mission_example")):
            raise ToolError("point-mass without a design source needs an aircraft block in the mission "
                            "(or pass spec, spec_path, run_id or example)")
    if tool != "hifi" or not kwargs.get("continue_run"):
        if not (tool == "rcs" and kwargs.get("mode") in ("validate", "stl")) and not n0_pointmass:
            _resolve(**src)          # bad source → immediate error, never a queued failure
    fn = TOOLS[tool]
    j = MANAGER.submit(tool, lambda job, **kw: fn(job, **kw), {k: v for k, v in kwargs.items() if v is not None})
    j = MANAGER.wait(j.id, wait_s)
    if j.status == "done":
        return {**clean(j.result), "job_id": j.id}
    if j.status == "failed":
        return {"status": "failed", "job_id": j.id, "error": j.error, "run_id": j.run_id, "log_tail": list(j.log)[-5:]}
    return {"status": j.status, "job_id": j.id, "run_id": j.run_id,
            "hint": f"still running after {wait_s:.0f} s — poll job_status(job_id='{j.id}')"}


def job_status(job_id: str, wait_s: float = 0.0) -> dict:
    j = MANAGER.wait(job_id, wait_s) if wait_s else MANAGER.get(job_id)
    info = j.info(with_result=True)
    return clean(info)


def list_jobs() -> dict:
    return {"jobs": clean(MANAGER.list())}
