"""Methods catalogue, reference data and docs exposed to the AI agent (MCP resources).

The methods catalogue is *generated from the module docstrings* (where acdt cites its sources), so it never
drifts from the code and adds no citation that the code does not make. The workflow map links each design stage
to the toolkit tool and to the modules that implement it."""
from __future__ import annotations

import ast
import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]           # src/acdt
REPO = PKG.parents[1]
_YEAR = re.compile(r"\b(1[89]\d\d|20[0-3]\d)\b")

# stage → toolkit tool(s), fidelity level, implementing modules (no citations here: they come from docstrings)
WORKFLOW = [
    {"stage": "requirements", "tools": ["requirements_schema", "validate_requirements"], "level": "-",
     "modules": ["acdt.core.requirements", "acdt.domains.aircraft.requirement_types", "acdt.domains.aircraft.mission"]},
    {"stage": "conceptual sizing + design point (L0 handbook)", "tools": ["size(level='L0')"], "level": "L0",
     "modules": ["acdt.domains.aircraft.sizing", "acdt.domains.aircraft.constraints", "acdt.domains.aircraft.weights",
                 "acdt.domains.aircraft.weights_detailed", "acdt.domains.aircraft.aero.drag",
                 "acdt.domains.aircraft.aero.lift", "acdt.domains.aircraft.propulsion"]},
    {"stage": "low-fidelity aero (L1: XFOIL/AVL) + structures/stability/performance/aeroelasticity",
     "tools": ["size(level='L1')"], "level": "L1",
     "modules": ["acdt.domains.aircraft.aero.lowfi", "acdt.domains.aircraft.structures",
                 "acdt.core.structures.beam", "acdt.core.structures.loads",
                 "acdt.domains.aircraft.structures_l1", "acdt.domains.aircraft.cad_export",
                 "acdt.domains.aircraft.stability", "acdt.domains.aircraft.weight_balance",
                 "acdt.domains.aircraft.landing_gear", "acdt.domains.aircraft.performance",
                 "acdt.domains.aircraft.aeroelasticity"]},
    {"stage": "components / systems / harness", "tools": ["systems", "validate_component",
              "electrical_catalog", "electrical_analyse", "payload_catalog", "payload_trade",
              "cost_per_flight_hour", "operational_cost"], "level": "L1",
     "modules": ["acdt.domains.aircraft.systems_integration", "acdt.core.systems.electric_propulsion",
                 "acdt.core.systems.battery", "acdt.core.systems.servos", "acdt.core.systems.avionics",
                 "acdt.core.systems.harness", "acdt.core.systems.compliance",
                 "acdt.core.systems.electrical", "acdt.core.systems.payload_trade"]},
    {"stage":"shared incremental onboard payload/electrical coupling (prop/jet/VTOL); hybrid accounting only",
     "tools":["onboard_size"],"level":"L0", "modules":["acdt.core.onboard","acdt.domains.aircraft.onboard"]},
    {"stage":"N0 envelope to N1 mission/ground service/fleet feedback (explicit candidates; no global optimum; schema 1.1 derived endurance, prop/jet capability closure, operational reserve once)",
     "tools":["mission_fleet_study"],"level":"N0/N1-L0",
     "modules":["acdt.domains.aircraft.mission_fleet","acdt.domains.aircraft.mission_endurance","acdt.core.concept.fleet_feedback","acdt.core.concept.ground_queue","acdt.domains.aircraft.mission_fleet_mixed","acdt.domains.aircraft.hybrid_dispatch","acdt.domains.aircraft.mission_phases"]},
    {"stage": "decision log (P5)", "tools": ["decisions_open", "decisions_add", "decisions_check",
              "decisions_list", "decisions_report"], "level": "N0–N3",
     "modules": ["acdt.core.decisions.log"]},
    {"stage": "sensitivity (P7)", "tools": ["sensitivity_from_samples", "sensitivity_pipeline"],
     "level": "N0–N2", "modules": ["acdt.core.sensitivity.oat"]},
    {"stage": "shape N2 light (P6)", "tools": ["shape_bounds", "shape_n2_study", "shape_packaging_score"],
     "level": "N2", "modules": ["acdt.domains.aircraft.shape_opt.n2", "acdt.domains.aircraft.rcs"]},
    {"stage": "VTOL / eVTOL L0 (hover, transition, architecture compare)",
     "tools": ["vtol_hover", "vtol_size", "vtol_compare"], "level": "L0",
     "modules": ["acdt.domains.aircraft.vtol.momentum", "acdt.domains.aircraft.vtol.size", "acdt.domains.aircraft.vtol.closure"]},
    {"stage": "subsonic jet transport L0 (wave drag, turbofan, loads, mass closure, takeoff/climb/OEI screening)",
     "tools": ["jet_wave_drag", "jet_turbofan", "jet_loads", "jet_analyse", "jet_check", "jet_size", "jet_performance", "jet_weights"], "level": "L0",
     "modules": ["acdt.domains.aircraft.jet.wave_drag", "acdt.domains.aircraft.jet.turbofan",
                 "acdt.domains.aircraft.jet.loads_cs25", "acdt.domains.aircraft.jet.analyse",
                 "acdt.domains.aircraft.jet.sizing", "acdt.domains.aircraft.jet.performance", "acdt.domains.aircraft.jet.weights"]},
    {"stage": "common fuel/battery storage L0 (capacity and allocated volume; demand adapters)",
     "tools": ["storage_check"], "level": "L0",
     "modules": ["acdt.core.energy_storage", "acdt.domains.aircraft.storage"]},
    {"stage": "preliminary / MDO", "tools": ["optimize"], "level": "L1/L2",
     "modules": ["acdt.domains.aircraft.mdo", "acdt.core.mdo"]},
    {"stage": "wing box (sections, stringers/ribs, FEM)", "tools": ["wingbox"], "level": "L2",
     "modules": ["acdt.domains.aircraft.wingbox.study", "acdt.domains.aircraft.wingbox.study6",
                 "acdt.domains.aircraft.wingbox.section", "acdt.domains.aircraft.wingbox.sizing6",
                 "acdt.core.materials", "acdt.core.sections", "acdt.core.thinwalled"]},
    {"stage": "RCS (if relevant)", "tools": ["rcs"], "level": "L1 (physical optics)",
     "modules": ["acdt.core.em.po", "acdt.core.em.validate", "acdt.domains.aircraft.rcs.study"]},
    {"stage": "detailed sizing", "tools": ["hifi(steps=['detailed'])"], "level": "L2",
     "modules": ["acdt.domains.aircraft.detailed_sizing", "acdt.domains.aircraft.weights_detailed"]},
    {"stage": "high fidelity + calibration (L3)", "tools": ["hifi_estimate", "hifi", "apply_calibration"],
     "level": "L3", "modules": ["acdt.domains.aircraft.hifi.run", "acdt.domains.aircraft.hifi.cfd",
                                "acdt.domains.aircraft.hifi.cfd3d", "acdt.domains.aircraft.hifi.fem",
                                "acdt.domains.aircraft.hifi.flutter", "acdt.domains.aircraft.hifi.calibration"]},
    {"stage": "cost (unit production cost — modified Eastlake, Gudmundsson 2014 Sec. 2.3; if requested)", "tools": ["size", "cost_estimate"], "level": "L0",
     "modules": ["acdt.domains.aircraft.cost", "acdt.domains.aircraft.manufacturing.costing"]},
    {"stage": "manufacturing + cost (per-part processes, bottom-up vs Eastlake/DAPCA IV, W0–cost Pareto)",
     "tools": ["manufacturing_plan", "process_options", "compare_materials", "cost_estimate"], "level": "L0/L1",
     "modules": ["acdt.domains.aircraft.manufacturing.refdata", "acdt.domains.aircraft.manufacturing.processes",
                 "acdt.domains.aircraft.manufacturing.parts", "acdt.domains.aircraft.manufacturing.plan",
                 "acdt.domains.aircraft.manufacturing.selection", "acdt.domains.aircraft.manufacturing.study",
                 "acdt.domains.aircraft.manufacturing.pareto"]},
    {"stage": "N1 morphological architecture (Zwicky + set-based)", "tools": ["morph_matrix", "morph_generate", "morph_evaluate", "morph_prune"], "level": "N1",
     "modules": ["acdt.domains.aircraft.morphology.matrix", "acdt.domains.aircraft.morphology.generate",
                 "acdt.domains.aircraft.morphology.evaluate", "acdt.domains.aircraft.morphology.prune"]},
    {"stage": "mission simulation (point-mass N0/N1, 6-DOF N2)", "tools": ["simulate_mission"],
     "level": "N0–N2",
     "modules": ["acdt.domains.aircraft.flightsim.pointmass", "acdt.domains.aircraft.flightsim.mission",
                 "acdt.domains.aircraft.flightsim.sensors", "acdt.domains.aircraft.flightsim.failures",
                 "acdt.domains.aircraft.performance", "acdt.core.concept.search"]},
]


def _modules():
    for p in sorted(PKG.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(PKG.parent).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        yield ".".join(parts), p


def methods() -> dict:
    """{workflow, modules: [{module, summary, references (docstring lines with a year), docstring}]}."""
    mods = []
    for name, p in _modules():
        try:
            doc = ast.get_docstring(ast.parse(p.read_text(encoding="utf-8"))) or ""
        except SyntaxError:  # pragma: no cover
            continue
        if not doc or name.startswith("acdt.ai") or name == "acdt.cli":
            continue
        summary = doc.split("\n\n")[0].replace("\n", " ").strip()
        refs = [ln.strip(" *-") for ln in re.split(r"(?<=[.;])\s+|\n", doc) if _YEAR.search(ln)]
        mods.append({"module": name, "summary": summary[:400], "references": refs[:12], "docstring": doc[:3000]})
    return {"note": "Generated from the acdt module docstrings (the code's own citations). Methods are classical, "
                    "cited handbook/textbook methods; validity limits are stated in each module docstring.",
            "workflow": WORKFLOW, "modules": mods}


def materials() -> dict:
    from acdt.core import materials as M
    lib = M.library()
    return {"note": "Small cited reference library (typical / S-basis values). For design data research the "
                    "current MMPDS / CMH-17 / manufacturer datasheet and pass it through validate_material.",
            "materials": {k: {"name": m.name, "kind": m.kind, "E_Pa": m.E, "G_Pa": m.G, "nu": m.nu, "rho_kg_m3": m.rho,
                              "Ftu_Pa": m.Ftu, "Fty_Pa": m.Fty, "Fcy_Pa": m.Fcy, "Fsu_Pa": m.Fsu, "t_min_m": m.t_min,
                              "source": m.source, "notes": m.notes} for k, m in lib.items()}}


def components() -> dict:
    from acdt.core.systems.database import load_default_db
    db = load_default_db()
    return {"note": "EXAMPLE DATA — generic classes and approximate manufacturer data (see components.yaml "
                    "header). Research current datasheets and pass them through validate_component.",
            **{k: getattr(db, k) for k in ("motors", "escs", "cells", "servos", "autopilots")}}


def standards() -> list:
    from acdt.core.systems.database import load_standards
    return load_standards()


def docs() -> dict[str, Path]:
    d = {p.stem: p for p in sorted((REPO / "docs").glob("*.md"))}
    for n in ("README", "AGENTS", "THIRD_PARTY", "CAPABILITIES"):
        if (REPO / f"{n}.md").exists():
            d[n] = REPO / f"{n}.md"
    return d


def doc(name: str) -> str:
    dd = docs()
    if name not in dd:
        raise KeyError(f"doc {name!r} not found ({', '.join(dd)})")
    return dd[name].read_text(encoding="utf-8")


def examples() -> list[dict]:
    import yaml
    out = []
    for p in sorted((REPO / "examples").glob("*.yaml")):
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        out.append({"example": p.stem, "path": str(p), "name": d.get("name"), "aircraft_class": d.get("aircraft_class"),
                    "description": (d.get("description") or "").strip(), "requirements": d.get("requirements")})
    return out
