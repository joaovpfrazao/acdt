"""AI toolkit for P1 (docs/DESIGN_WORKFLOW.md): generic component geometry and the integration checker.

The agent assembles ANY configuration from generic parts (body / surface / disc) and states the integration
requirements derived from the mission (volumes, mass, power, heat, FOV cones, keep-out zones, placement
constraints); these functions only evaluate. Each call is a registered run (inputs, outputs, files)."""
from __future__ import annotations

import json

from acdt.domains.aircraft.assembly import Assembly, check

from . import registry
from .toolkit import ToolError, clean


def _asm(assembly) -> Assembly:
    try:
        return Assembly.from_dict(assembly)
    except (ValueError, TypeError, KeyError) as e:
        raise ToolError(f"assembly: {e}") from e


def _files(run, asm: Assembly) -> dict:
    files = {"assembly_stl": asm.write_stl(run.path / "assembly.stl")}
    try:
        (run.path / "assembly.avl").write_text(asm.avl_text(), encoding="utf-8")
        files["avl"] = run.path / "assembly.avl"
    except ValueError:
        pass
    return files


def assembly_geometry(assembly: dict, write_files: bool = True, name: str = "assembly") -> dict:
    """Build an assembly from generic components; return per-component volume, wetted area, planform area,
    centroid and bounding box, plus STL (RCS `acdt rcs` STL mode / CAD viewers) and AVL (surfaces only)."""
    asm = _asm(assembly)
    out = clean(asm.summary())
    if write_files:
        run = registry.new_run("assembly_geometry", name, {"assembly": assembly})
        files = _files(run, asm)
        run.finish(out, files)
        out = {"run_id": run.id, **out, "files": {k: str(v) for k, v in files.items()}}
    return out


def integration_check(assembly: dict, items: list, constraints: list | None = None, base: dict | None = None,
                      place_unpositioned: bool = True, name: str = "integration") -> dict:
    """Packaging + field-of-view + mass-properties check (see :func:`acdt.domains.aircraft.assembly.check`)."""
    asm = _asm(assembly)
    try:
        res = clean(check(asm, items, constraints, base, place_unpositioned))
    except (ValueError, TypeError, KeyError) as e:
        raise ToolError(f"integration_check: {e}") from e
    run = registry.new_run("integration_check", name, {"assembly": assembly, "items": items,
                                                        "constraints": constraints, "base": base})
    run.record["assumptions"] = [{"text": a, "kind": "assumed_default"} for a in res["assumptions"]]
    files = _files(run, asm)
    (run.path / "integration.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    files["result"] = run.path / "integration.json"
    run.finish({k: res[k] for k in ("ok", "n_constraints", "n_violations", "positions", "power_w", "heat_w")}
               | {"mass_kg": res["mass_properties"].get("mass_kg"), "cg": res["mass_properties"].get("cg")}, files)
    return {"run_id": run.id, **res, "files": {k: str(v) for k, v in files.items()}}


def assembly_sizing(spec: dict, flight: dict, options: dict | None = None, name: str = "assembly_sizing") -> dict:
    """P1b: evaluate a drawn assembly as an aircraft (see :func:`acdt.domains.aircraft.assembly.sizing.analyse`):
    per-part Raymer masses, wetted-area CD0 buildup, AVL with bodies + Torenbeek neutral point, loading cases and
    static margin, tricycle gear from the geometry, integration check. Each call is a registered run."""
    from acdt.domains.aircraft.assembly.sizing import analyse
    if "assembly" not in spec:
        raise ToolError("assembly_sizing: spec needs 'assembly'")
    try:
        out = analyse(spec, flight, options)
    except (ValueError, TypeError, KeyError) as e:
        raise ToolError(f"assembly_sizing: {e}") from e
    res = clean(out.summary())
    run = registry.new_run("assembly_sizing", name, {"spec": spec, "flight": flight, "options": options})
    run.record["assumptions"] = [{"text": a, "kind": "assumed_default"} for a in out.assumptions]
    asm = _asm(spec["assembly"])
    files = _files(run, asm)
    (run.path / "assembly_sizing.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    files["result"] = run.path / "assembly_sizing.json"
    run.finish({"structure_mass_kg": res.get("structure_mass_kg"), "CD0": res.get("CD0"),
                "static_margin": res.get("static_margin"), "checks": res.get("checks")}, files)
    return {"run_id": run.id, **res, "files": {k: str(v) for k, v in files.items()}}
