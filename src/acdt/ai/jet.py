# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""JSON/YAML-facing subsonic jet transport L0 wrappers."""
import json
from pathlib import Path
from acdt.domains.aircraft.jet import wave_drag, turbofan_point, flight_envelope, analyse_jet, check_reference


def load_spec(spec):
    if isinstance(spec, dict):
        return spec
    path = Path(spec)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml
        out = yaml.safe_load(text)
    else:
        out = json.loads(text)
    if not isinstance(out, dict):
        raise ValueError("jet input must be a mapping")
    return out


def jet_wave_drag(mach: float, cl: float = 0.5, thickness_ratio: float = 0.12,
                  sweep_deg: float = 25.0, technology_factor: float = 0.95) -> dict:
    return wave_drag(mach, cl, thickness_ratio, sweep_deg, technology_factor)


def jet_turbofan(mach: float, altitude_m: float, thrust_sl_N: float = 120000.0,
                 installation_factor: float = 0.97, throttle_ratio: float = 1.05,
                 tsfc_multiplier: float = 1.0, throttle: float = 1.0, map=None) -> dict:
    """Max-rating Mattingly/Ihme by default; opt-in map via engine_point (no cycle code)."""
    from acdt.domains.aircraft.jet.engine_map import engine_point
    return engine_point(mach, altitude_m, thrust_sl_N, installation_factor=installation_factor,
                        throttle_ratio=throttle_ratio, tsfc_multiplier=tsfc_multiplier,
                        throttle=throttle, map=map)


def jet_loads(mass_kg: float, wing_area_m2: float, vc_eas_m_s: float,
              cl_max: float = 1.5, cl_min: float = -1.0, vd_ratio: float = 1.25) -> dict:
    return flight_envelope(mass_kg, wing_area_m2, vc_eas_m_s, cl_max, cl_min, vd_ratio)


def jet_analyse(spec) -> dict:
    return analyse_jet(load_spec(spec))


def jet_check(reference) -> dict:
    return check_reference(load_spec(reference))


def jet_size(spec, record: bool = True) -> dict:
    """Coupled fixed-geometry jet mass closure; writes a provenance run by default.

    No acdt size/GA fallback. One user-supplied jet_transport candidate; explicit
    mass bracket and payload/crew. Pure deterministic domain API: size_jet(dict).
    """
    return _jet_run(spec, record, "jet_size")


def jet_performance(spec, record: bool = True) -> dict:
    """Close jet mass then screen explicit ground/climb/OEI points; NOT certification.

    Requires the optional performance block; returns the jet_size envelope with
    additive performance/schema_version=1.0 and combined_requested_checks_passed.
    """
    inputs = load_spec(spec)
    if "performance" not in inputs:
        raise ValueError("jet performance requires an explicit performance block")
    return _jet_run(inputs, record, "jet_performance")


def _jet_run(spec, record, tool):
    from acdt.domains.aircraft.jet.sizing import size_jet
    from . import registry
    inputs = load_spec(spec)
    run = registry.new_run(tool, str(inputs.get("configuration_id", "jet")), {"spec": inputs}) if record else None
    try:
        out = size_jet(inputs)
        if run:
            result_path = run.path/"result.json"
            out["run_id"] = run.id
            out["files"] = {"result": str(result_path), "run": str(run.path/"run.json")}
            result_path.write_text(json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
            run.record["assumptions"] = out["assumptions"]
            summary = {k: out[k] for k in ("converged", "feasible", "mtow_kg", "issues")}
            if "combined_requested_checks_passed" in out:
                summary["combined_requested_checks_passed"] = out["combined_requested_checks_passed"]
            passed = out.get("combined_requested_checks_passed", out["feasible"])
            run.finish(outputs=summary, files=out["files"], status="done" if passed else
                       ("infeasible" if out["converged"] else "not_converged"))
        return out
    except Exception as exc:
        if run:
            run.finish(status="error", error=str(exc))
        raise


def jet_weights(spec, record: bool = True) -> dict:
    """Transport component accounting at a supplied mass, or explicit statistical baseline.

    spec: mass_kg, wing_area_m2, aspect_ratio, weights. Not an OEW fit, full
    transport build-up, architecture selector or GA equation fallback.
    """
    from acdt.core.energy_storage import mapping, number
    from acdt.domains.aircraft.jet.weights import validate_weights, transport_weights
    from acdt.domains.aircraft.weights import statistical_fraction, statistical_source
    from . import registry
    inputs = load_spec(spec)
    run = registry.new_run("jet_weights", "transport-components", {"spec": inputs}) if record else None
    try:
        mapping(inputs, {"mass_kg", "wing_area_m2", "aspect_ratio", "weights"}, "jet weights spec")
        if set(inputs) != {"mass_kg", "wing_area_m2", "aspect_ratio", "weights"}: raise ValueError("mass_kg, wing_area_m2, aspect_ratio, weights required")
        for key in ("mass_kg", "wing_area_m2", "aspect_ratio"): number(key, inputs[key], positive=True, maximum=1e6)
        validate_weights(inputs["weights"])
        if inputs["weights"]["mode"] == "components":
            out = transport_weights(inputs["mass_kg"], inputs["wing_area_m2"], inputs["aspect_ratio"], inputs["weights"])
        else:
            m = inputs["mass_kg"]
            empty = m*statistical_fraction("jet_transport",m)
            valid = 0 < empty < m
            out = {"level":"L0", "mode":"statistical", "design_mass_kg":m,
                   "empty_mass_kg":empty, "operating_empty_mass_kg":None,
                   "checks":[{"name":"empty_below_design_mass","passed":valid,"margin_kg":m-empty}],
                   "issues":[] if valid else ["invalid_statistical_empty_fraction"], "method":statistical_source("jet_transport"),
                   "validity":"global historical jet_transport statistic, not component or OEW prediction",
                   "assumptions":[{"path":"weights.mode","value":"statistical","source":"explicit baseline"}]}
        if run:
            out["run_id"] = run.id
            path = run.path/"result.json"
            out["files"] = {"result":str(path),"run":str(run.path/"run.json")}
            path.write_text(json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
            run.record["assumptions"] = out["assumptions"]
            run.finish(outputs={"empty_mass_kg":out["empty_mass_kg"],"issues":out["issues"]},files=out["files"],status="done" if not out["issues"] else
                       ("incomplete" if out.get("coverage",{}).get("complete") is False else "infeasible"))
        return out
    except Exception as exc:
        if run: run.finish(status="error",error=str(exc))
        raise
