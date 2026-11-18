# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Partial transport component build-up with explicit coverage, never a GA fallback.

Raymer (2012), Aircraft Design: A Conceptual Approach, cargo/transport weights,
5th ed. Sec. 15.3.2. Equations/imperial units verified against public
transcriptions opened 2026-11-07 / 2026-11-09:

* AeroSandbox raymer_cargo_transport_weights (wing/HT/VT already in use):
  https://aerosandbox.readthedocs.io/en/master/_modules/aerosandbox/library/weights/raymer_cargo_transport_weights.html
* ADAC Chapter 15 Weight and Balance (2022-11-23) slides 46/54/56–57
  (fuselage L/D = structural length/depth, not aerodynamic L/D; main gear Wl):
  https://www.adac.aero/_files/ugd/c40aeb_ceb381b4d854417fa39876cbc1db0bf4.pdf
* SUAVE Raymer fuselage / landing_gear (2nd ed. transcription; Vstall in knots):
  https://raw.githubusercontent.com/suavecode/SUAVE/master/trunk/SUAVE/Methods/Weights/Correlations/Raymer/fuselage.py
  https://raw.githubusercontent.com/suavecode/SUAVE/master/trunk/SUAVE/Methods/Weights/Correlations/Raymer/landing_gear.py

PRESSUPOSTO resolution of prior ambiguity: AeroSandbox's cargo fuselage argument
named ``L_over_D`` is the fuselage fineness L/D (SUAVE/ADAC), NOT cruise L/D.
Landing-gear speed exponent uses knots (SUAVE/Raymer), not ft/s OCR from ADAC.
Landing design weight Wl is an EXPLICIT input (ADAC/SUAVE), never silently TOGW.

Optional cabin pressure increment W_press = 11.9 (Vp_ft³ · ΔP_psi)^0.271 lb
(Raymer Sec. 15.3.3 GA fuselage add-on, AeroSandbox GA transcription) may be
added on top of the transport fuselage regression when both cabin volume and
ΔP are supplied. The transport fuselage correlation already embeds historical
pressurised metal transports; W_press is an explicit extra shell increment, not
a substitute for non-cylindrical BWB sizing.

Own scalar implementation; no AeroSandbox/SUAVE code imported. No fitted residual,
composite factor, engine-thrust-to-mass regression, tank or GA weight substitution.
Historical conventional METAL transport only. Engines_dry stay supplied (no
thrust→dry-mass correlation in Sec. 15.3.2). Unknown mass ≠ zero.
"""
from __future__ import annotations
from copy import deepcopy
import math
import json
from acdt.core.energy_storage import mapping, number
from acdt.domains.aircraft.weights_detailed import LB, FT

SOURCE_URL = "https://aerosandbox.readthedocs.io/en/master/_modules/aerosandbox/library/weights/raymer_cargo_transport_weights.html"
ADAC_URL = "https://www.adac.aero/_files/ugd/c40aeb_ceb381b4d854417fa39876cbc1db0bf4.pdf"
SUAVE_FUSE_URL = "https://raw.githubusercontent.com/suavecode/SUAVE/master/trunk/SUAVE/Methods/Weights/Correlations/Raymer/fuselage.py"
INCH = 0.0254
PSI = 6894.757293168  # Pa
FT3 = FT**3
GALLON = 0.003785411784  # m³

COVERAGE = {
    "wing_structure": "airframe", "horizontal_tail_structure": "airframe", "vertical_tail_structure": "airframe",
    "fuselage_structure": "airframe", "landing_gear": "airframe", "nacelles_pylons": "airframe",
    "engines_dry": "propulsion", "propulsion_accessories": "propulsion", "apu_installed": "propulsion",
    "flight_controls": "equipment", "hydraulics": "equipment", "electrical_avionics": "equipment",
    "environmental_antiice": "equipment", "furnishings_interiors": "equipment", "fuel_system_dry": "equipment",
    "operating_items_noncrew_nonfuel": "equipment", "other_empty_items": "equipment",
}

# method → exactly one coverage group
METHODS = {
    "raymer_transport_wing": "wing_structure",
    "raymer_transport_htail": "horizontal_tail_structure",
    "raymer_transport_vtail": "vertical_tail_structure",
    "raymer_transport_fuselage": "fuselage_structure",
    "raymer_transport_landing_gear": "landing_gear",
    "raymer_transport_nacelles": "nacelles_pylons",
    "raymer_transport_propulsion_accessories": "propulsion_accessories",
    "raymer_transport_apu": "apu_installed",
    "raymer_transport_flight_controls": "flight_controls",
    "raymer_transport_hydraulics": "hydraulics",
    "raymer_transport_electrical_avionics": "electrical_avionics",
    "raymer_transport_environmental": "environmental_antiice",
    "raymer_transport_furnishings": "furnishings_interiors",
    "raymer_transport_fuel_system": "fuel_system_dry",
}

KDOOR = {"none": 1.0, "one_side": 1.06, "two_side": 1.12, "aft_clamshell": 1.12, "two_side_and_aft_clamshell": 1.25}

INPUTS = {
    "raymer_transport_wing": {"root_thickness_ratio", "taper_ratio", "sweep_quarter_chord_deg", "control_area_m2"},
    "raymer_transport_htail": {"area_m2", "aspect_ratio", "sweep_quarter_chord_deg", "tail_arm_m", "pitch_radius_m",
                                "fuselage_width_m", "elevator_area_m2", "all_moving"},
    "raymer_transport_vtail": {"area_m2", "aspect_ratio", "sweep_quarter_chord_deg", "tail_arm_m", "yaw_radius_m",
                                "root_thickness_ratio", "tail_height_ratio"},
    "raymer_transport_fuselage": {"length_m", "wetted_area_m2", "depth_m", "wing_span_m", "wing_taper_ratio",
                                   "wing_sweep_quarter_chord_deg", "cargo_door", "fuselage_mounted_main_gear",
                                   "pressurized_volume_m3", "delta_p_Pa"},
    "raymer_transport_landing_gear": {"landing_mass_kg", "landing_load_factor", "main_length_m", "nose_length_m",
                                      "main_wheels", "nose_wheels", "main_shock_struts", "landing_stall_speed_kt",
                                      "main_kneeling", "nose_kneeling"},
    "raymer_transport_nacelles": {"length_m", "width_m", "height_m", "mass_per_engine_kg", "n_engines",
                                   "pylon_mounted", "thrust_reversers"},
    "raymer_transport_propulsion_accessories": {"n_engines", "cockpit_to_engine_length_m", "mass_per_engine_kg"},
    "raymer_transport_apu": {"uninstalled_mass_kg"},
    "raymer_transport_flight_controls": {"n_control_functions", "control_surface_area_m2", "Iyy_kg_m2",
                                          "mechanical_controls_fraction"},
    "raymer_transport_hydraulics": {"n_control_functions", "fuselage_length_m", "wing_span_m"},
    "raymer_transport_electrical_avionics": {"electrical_power_W", "routing_distance_m", "n_engines",
                                              "uninstalled_avionics_mass_kg"},
    "raymer_transport_environmental": {"n_crew", "n_pax", "pressurized_volume_m3", "uninstalled_avionics_mass_kg"},
    "raymer_transport_furnishings": {"n_crew", "cargo_mass_kg", "fuselage_wetted_area_m2"},
    "raymer_transport_fuel_system": {"fuel_volume_m3", "n_tanks", "integral_tank_fraction"},
}

# optional keys may be omitted from fuselage (pressurization pair is all-or-nothing)
FUSE_OPTIONAL = {"pressurized_volume_m3", "delta_p_Pa"}
FUSE_REQUIRED = INPUTS["raymer_transport_fuselage"] - FUSE_OPTIONAL


def validate_weights(settings):
    """Validate syntax; missing/unknown component masses remain missing coverage, not zero."""
    mapping(settings, {"mode", "conventional_metal_transport", "configuration_description", "ultimate_n",
                       "items", "additional_required_groups"}, "jet weights")
    mode = settings.get("mode")
    if mode == "statistical":
        if set(settings) != {"mode"}: raise ValueError("statistical mode accepts only mode; no ignored component inputs")
        return
    if mode != "components": raise ValueError("weights.mode must be statistical or components")
    if not isinstance(settings.get("conventional_metal_transport"), bool):
        raise ValueError("declare conventional_metal_transport applicability explicitly")
    if not isinstance(settings.get("configuration_description"), str) or not settings["configuration_description"].strip():
        raise ValueError("configuration_description required; no automatic architecture selection")
    extra = settings.get("additional_required_groups", [])
    if not isinstance(extra, list) or any(not isinstance(x, str) or not x.strip() for x in extra) or len(set(extra)) != len(extra) or set(extra) & set(COVERAGE):
        raise ValueError("additional_required_groups must be unique new nonempty accounting keys")
    excluded = {"crew", "crew_kg", "payload", "payload_kg", "fuel", "mission_fuel",
                "fuel_mass_kg", "trip_burn_kg", "reserve_fuel", "reserve_fuel_kg", "unusable_fuel"}
    if any(x.lower() in excluded for x in extra):
        raise ValueError("crew/payload/all fuel are outside the empty inventory, not additional groups")
    required = set(COVERAGE) | set(extra)
    items = settings.get("items", [])
    if not isinstance(items, list) or len(items) > 200: raise ValueError("weights.items must be a list of <=200 items")
    seen, names = set(), set()
    for item in items:
        mapping(item, {"name", "covers", "method", "inputs", "source", "mass_kg", "reason"}, "weight item")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip() or name in names: raise ValueError("weight item names must be unique and nonempty")
        names.add(name)
        covers = item.get("covers")
        if not isinstance(covers, list) or not covers or any(not isinstance(c, str) for c in covers) or len(set(covers)) != len(covers) or set(covers) - required:
            raise ValueError("covers must list unique declared accounting groups (not crew, payload or mission fuel)")
        if seen & set(covers): raise ValueError("duplicate component coverage: " + str(sorted(seen & set(covers))))
        seen.update(covers)
        method = item.get("method")
        if not isinstance(item.get("source"), str) or not item["source"].strip(): raise ValueError("every item needs input/mass provenance or PRESSUPOSTO source")
        if method == "supplied":
            if set(item) - {"name", "covers", "method", "source", "mass_kg"}: raise ValueError("supplied item accepts only total mass, not a second equation/allowance")
            if item.get("mass_kg") is not None: number("mass_kg", item["mass_kg"], maximum=1e6)
        elif method == "not_applicable":
            if set(item) - {"name", "covers", "method", "source", "reason"}: raise ValueError("not_applicable must not hide another mass")
            if not isinstance(item.get("reason"), str) or not item["reason"].strip(): raise ValueError("explicit reason required for not_applicable")
        elif method in METHODS:
            if covers != [METHODS[method]]: raise ValueError("a regression covers exactly its own structural group")
            if set(item) - {"name", "covers", "method", "source", "inputs"}: raise ValueError("choose regression OR supplied override, never both")
            _validate_inputs(method, item.get("inputs"))
        else: raise ValueError("unsupported component method (no GA fallback); engines_dry/operating/other stay supplied")
    if any(i["method"] in METHODS for i in items):
        number("ultimate_n", settings.get("ultimate_n"), positive=True, maximum=20)
    elif "ultimate_n" in settings:
        number("ultimate_n", settings["ultimate_n"], positive=True, maximum=20)
    if "ultimate_n" in settings and settings["ultimate_n"] < 1:
        raise ValueError("ultimate_n must support at least 1g")


def _validate_inputs(method, p):
    allowed = INPUTS[method]
    if method == "raymer_transport_fuselage":
        if not isinstance(p, dict): raise ValueError("regression inputs required")
        if FUSE_REQUIRED - set(p): raise ValueError("fuselage missing " + str(sorted(FUSE_REQUIRED - set(p))))
        if set(p) - allowed: raise ValueError("unexpected fuselage inputs")
        has_v, has_dp = "pressurized_volume_m3" in p, "delta_p_Pa" in p
        if has_v ^ has_dp: raise ValueError("pressurized_volume_m3 and delta_p_Pa must be supplied together or omitted")
    else:
        mapping(p, allowed, "regression inputs")
        if set(p) != allowed: raise ValueError("all regression inputs must be explicit for " + method)
    for key, val in p.items():
        if key in {"all_moving", "fuselage_mounted_main_gear", "pylon_mounted", "thrust_reversers", "main_kneeling", "nose_kneeling"}:
            if not isinstance(val, bool): raise ValueError(key + " must be bool")
        elif key == "cargo_door":
            if val not in KDOOR: raise ValueError("cargo_door must be one of " + str(sorted(KDOOR)))
        elif key in {"n_engines", "main_wheels", "nose_wheels", "main_shock_struts", "n_tanks", "n_control_functions", "n_crew", "n_pax"}:
            if isinstance(val, bool) or not isinstance(val, int) or val < (0 if key in {"n_pax"} else 1) or val > 400:
                raise ValueError(key + " must be a positive int in range")
        elif key in {"sweep_quarter_chord_deg", "wing_sweep_quarter_chord_deg"}:
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or not -45 <= val <= 60:
                raise ValueError("quarter-chord sweep outside implemented numerical domain [-45,60] deg")
        elif key == "mechanical_controls_fraction":
            number(key, val, maximum=1)
        elif key == "integral_tank_fraction":
            number(key, val, maximum=1)
        elif key == "delta_p_Pa":
            number(key, val, maximum=1e6)  # 0 allowed (unpressurised add-on)
        else:
            number(key, val, positive=key not in {"fuselage_width_m", "elevator_area_m2", "tail_height_ratio"}, maximum=1e9)
    for key in ("root_thickness_ratio", "taper_ratio", "wing_taper_ratio"):
        if key in p and not .01 <= p[key] <= 1: raise ValueError(key + " outside numerical domain [.01,1]")
    if "tail_height_ratio" in p and p["tail_height_ratio"] > 1: raise ValueError("tail_height_ratio must be 0..1")
    if "elevator_area_m2" in p and p["elevator_area_m2"] > p["area_m2"]: raise ValueError("elevator area exceeds tail area")
    if "aspect_ratio" in p and not .1 <= p["aspect_ratio"] <= 30: raise ValueError("tail aspect ratio outside numerical domain")
    if "landing_stall_speed_kt" in p and not 40 <= p["landing_stall_speed_kt"] <= 200:
        raise ValueError("landing_stall_speed_kt outside numerical domain [40,200] kt")
    if "landing_load_factor" in p and not 2 <= p["landing_load_factor"] <= 6:
        raise ValueError("landing_load_factor (Ngear) outside numerical domain [2,6]")
    if "main_shock_struts" in p and p["main_wheels"] < p["main_shock_struts"]:
        raise ValueError("main_wheels must be >= main_shock_struts")


def _regress(method, p, w_lb, nz):
    """Return component mass [kg] from explicit imperial Raymer transport equations."""
    if method == "raymer_transport_wing":
        c = math.cos(math.radians(p["sweep_quarter_chord_deg"]))
        if p["control_area_m2"] > p.get("_wing_area_m2", 1e9): raise ValueError("wing control area exceeds planform")
        lb = (.0051 * (w_lb * nz) ** .557 * (p["_wing_area_m2"] / FT ** 2) ** .649 * p["_aspect_ratio"] ** .5
              * p["root_thickness_ratio"] ** -.4 * (1 + p["taper_ratio"]) ** .1 / c * (p["control_area_m2"] / FT ** 2) ** .1)
    elif method == "raymer_transport_htail":
        c = math.cos(math.radians(p["sweep_quarter_chord_deg"]))
        span = math.sqrt(p["area_m2"] * p["aspect_ratio"])
        lb = (.0379 * (1.143 if p["all_moving"] else 1) * (1 + p["fuselage_width_m"] / span) ** -.25
              * w_lb ** .639 * nz ** .10 * (p["area_m2"] / FT ** 2) ** .75 / (p["tail_arm_m"] / FT)
              * (p["pitch_radius_m"] / FT) ** .704 / c * p["aspect_ratio"] ** .166 * (1 + p["elevator_area_m2"] / p["area_m2"]) ** .1)
    elif method == "raymer_transport_vtail":
        c = math.cos(math.radians(p["sweep_quarter_chord_deg"]))
        lb = (.0026 * (1 + p["tail_height_ratio"]) ** .225 * w_lb ** .556 * nz ** .536 * (p["tail_arm_m"] / FT) ** -.5
              * (p["area_m2"] / FT ** 2) ** .5 * (p["yaw_radius_m"] / FT) ** .875 / c * p["aspect_ratio"] ** .35
              * p["root_thickness_ratio"] ** -.5)
    elif method == "raymer_transport_fuselage":
        # L/D = structural fineness (ADAC/SUAVE). Kdoor from ADAC table.
        Kdoor = KDOOR[p["cargo_door"]]
        Klg = 1.12 if p["fuselage_mounted_main_gear"] else 1.0
        L_ft = p["length_m"] / FT
        Sf = p["wetted_area_m2"] / FT ** 2
        D_ft = p["depth_m"] / FT
        Bw = p["wing_span_m"] / FT
        lam = p["wing_taper_ratio"]
        Kws = 0.75 * ((1 + 2 * lam) / (1 + lam)) * (Bw / L_ft) * math.tan(math.radians(p["wing_sweep_quarter_chord_deg"]))
        lb = (0.3280 * Kdoor * Klg * (w_lb * nz) ** 0.5 * L_ft ** 0.25 * Sf ** 0.302
              * (1 + Kws) ** 0.04 * (L_ft / D_ft) ** 0.10)
        if "pressurized_volume_m3" in p:
            # Raymer Sec.15.3.3 GA add-on, cited for explicit ΔP shell increment.
            vp_ft3 = p["pressurized_volume_m3"] / FT3
            dp_psi = p["delta_p_Pa"] / PSI
            lb += 11.9 * (vp_ft3 * dp_psi) ** 0.271
    elif method == "raymer_transport_landing_gear":
        Wl = p["landing_mass_kg"] / LB
        Nl = p["landing_load_factor"] * 1.5
        Kmp = 1.126 if p["main_kneeling"] else 1.0
        Knp = 1.15 if p["nose_kneeling"] else 1.0
        Lm = p["main_length_m"] / INCH
        Ln = p["nose_length_m"] / INCH
        main = (0.0106 * Kmp * Wl ** 0.888 * Nl ** 0.25 * Lm ** 0.4 * p["main_wheels"] ** 0.321
                * p["main_shock_struts"] ** -0.5 * p["landing_stall_speed_kt"] ** 0.1)
        nose = (0.032 * Knp * Wl ** 0.646 * Nl ** 0.2 * Ln ** 0.5 * p["nose_wheels"] ** 0.45)
        lb = main + nose
    elif method == "raymer_transport_nacelles":
        Kng = 1.017 if p["pylon_mounted"] else 1.0
        Ktr = 1.18 if p["thrust_reversers"] else 1.0
        Wen = p["mass_per_engine_kg"] / LB
        # Raymer content mass with TR factor; no propeller path (transport jet).
        Wen_c = max(2.331 * Wen ** 0.901 * Ktr, Wen)
        Swet = (p["length_m"] * p["height_m"] * 2 + p["width_m"] * p["height_m"] * 2) / FT ** 2
        lb = (0.6724 * Kng * (p["length_m"] / FT) ** 0.10 * (p["width_m"] / FT) ** 0.294 * nz ** 0.119
              * Wen_c ** 0.611 * p["n_engines"] ** 0.984 * Swet ** 0.224)
    elif method == "raymer_transport_propulsion_accessories":
        Lec = p["cockpit_to_engine_length_m"] / FT
        controls = 5 * p["n_engines"] + 0.80 * Lec * p["n_engines"]
        starter = 49.19 * (p["mass_per_engine_kg"] / LB * p["n_engines"] / 1000) ** 0.541
        lb = controls + starter
    elif method == "raymer_transport_apu":
        lb = 2.2 * (p["uninstalled_mass_kg"] / LB)
    elif method == "raymer_transport_flight_controls":
        Scs = p["control_surface_area_m2"] / FT ** 2
        # Iyy: kg·m² → lbm·ft²
        Iyy = p["Iyy_kg_m2"] / LB / FT ** 2
        lb = (145.9 * p["n_control_functions"] ** 0.554 * (1 + p["mechanical_controls_fraction"]) ** -1
              * Scs ** 0.20 * (Iyy * 1e-6) ** 0.07)
    elif method == "raymer_transport_hydraulics":
        lb = 0.2673 * p["n_control_functions"] * ((p["fuselage_length_m"] + p["wing_span_m"]) / FT) ** 0.937
    elif method == "raymer_transport_electrical_avionics":
        electrical = (7.291 * (p["electrical_power_W"] / 1e3) ** 0.782
                      * (p["routing_distance_m"] / FT) ** 0.346 * p["n_engines"] ** 0.10)
        avionics = 1.73 * (p["uninstalled_avionics_mass_kg"] / LB) ** 0.983
        lb = electrical + avionics
    elif method == "raymer_transport_environmental":
        ac = (62.36 * (p["n_crew"] + p["n_pax"]) ** 0.25
              * (p["pressurized_volume_m3"] / FT3 / 1e3) ** 0.604
              * (p["uninstalled_avionics_mass_kg"] / LB) ** 0.10)
        anti = 0.002 * w_lb
        lb = ac + anti
    elif method == "raymer_transport_furnishings":
        lb = (0.0577 * p["n_crew"] ** 0.1 * (p["cargo_mass_kg"] / LB) ** 0.393
              * (p["fuselage_wetted_area_m2"] / FT ** 2) ** 0.75)
    elif method == "raymer_transport_fuel_system":
        fi = p["integral_tank_fraction"]
        lb = (2.405 * (p["fuel_volume_m3"] / GALLON) ** 0.606 * (1 + fi) ** -1 * (1 + (1 - fi))
              * p["n_tanks"] ** 0.5)
    else:
        raise ValueError("internal: unknown method")
    if not math.isfinite(lb) or lb <= 0: raise ValueError("weight regression arithmetic outside finite domain")
    return lb * LB


def transport_weights(mass_kg, wing_area_m2, aspect_ratio, settings):
    """Explicit zero-mission-fuel empty inventory, excluding crew/payload and NOT certified OEW."""
    validate_weights(settings)
    if settings["mode"] != "components": raise ValueError("transport_weights requires components mode")
    for key, val in (("mass_kg", mass_kg), ("wing_area_m2", wing_area_m2), ("aspect_ratio", aspect_ratio)):
        number(key, val, positive=True, maximum=1e6)
    w = mass_kg / LB
    required = set(COVERAGE) | set(settings.get("additional_required_groups", []))
    rows, claimed, assessed = [], set(), set()
    modeled, supplied = 0., 0.
    groups = {"airframe": 0., "propulsion": 0., "equipment": 0., "user_defined": 0., "mixed": 0.}
    unresolved_categories = set()
    press_note = None
    for item in settings.get("items", []):
        method, covers = item["method"], item["covers"]
        claimed.update(covers)
        categories = {COVERAGE.get(c, "user_defined") for c in covers}
        category = next(iter(categories)) if len(categories) == 1 else "mixed"
        m, source = None, item["source"]
        applicable = method not in METHODS or settings["conventional_metal_transport"]
        detail = None
        if method == "supplied": m = item.get("mass_kg")
        elif method == "not_applicable": m = 0.
        elif applicable:
            p = dict(item["inputs"])
            if method == "raymer_transport_wing":
                p["_wing_area_m2"] = wing_area_m2
                p["_aspect_ratio"] = aspect_ratio
                if p["control_area_m2"] > wing_area_m2: raise ValueError("wing control area exceeds planform")
            try:
                m = _regress(method, p, w, settings["ultimate_n"])
            except (OverflowError, ZeroDivisionError, ValueError) as exc:
                raise ValueError("weight regression arithmetic outside finite domain") from exc
            number("component mass", m, positive=True, maximum=1e9)
            source = "Raymer cargo/transport Sec.15.3.2 (public ADAC/SUAVE/AeroSandbox transcription); inputs: " + source
            if method == "raymer_transport_fuselage" and "pressurized_volume_m3" in p:
                vp_ft3 = p["pressurized_volume_m3"] / FT3
                dp_psi = p["delta_p_Pa"] / PSI
                w_press_lb = 11.9 * (vp_ft3 * dp_psi) ** 0.271
                detail = {"pressure_shell_increment_kg": w_press_lb * LB,
                          "pressurized_volume_m3": p["pressurized_volume_m3"], "delta_p_Pa": p["delta_p_Pa"],
                          "formula": "W_press=11.9 (Vp_ft3·ΔP_psi)^0.271 lb (Raymer Sec.15.3.3 GA add-on)",
                          "note": "added on top of transport fuselage regression; correlation already embeds historical pressurised metal transports"}
                press_note = detail
                source = "Raymer Sec.15.3.2 fuselage + Sec.15.3.3 W_press; inputs: " + item["source"]
            if method == "raymer_transport_landing_gear":
                detail = {"landing_mass_kg": p["landing_mass_kg"], "landing_load_factor": p["landing_load_factor"],
                          "ultimate_landing_load_factor": p["landing_load_factor"] * 1.5,
                          "landing_stall_speed_kt": p["landing_stall_speed_kt"],
                          "speed_unit_note": "Vstall exponent uses knots (SUAVE/Raymer), not ft/s"}
            if method == "raymer_transport_electrical_avionics":
                detail = {"accounting_note": "Raymer instruments remain outside this group unless supplied separately; electrical+avionics only"}
        if m is not None:
            assessed.update(covers); groups[category] += m
            if method in METHODS: modeled += m
            else: supplied += m
            if category == "mixed": unresolved_categories.update(categories)
        else: unresolved_categories.update(categories | {category})
        rows.append({"name": item["name"], "covers": list(covers), "method": method, "mass_kg": m, "group": category,
                     "status": "assessed" if m is not None else ("out_of_domain" if not applicable else "unassessed"),
                     "source": source, "inputs": deepcopy(item.get("inputs")), "reason": item.get("reason"),
                     "detail": detail,
                     "method_source_url": SOURCE_URL if method in METHODS else None,
                     "method_retrieved": "2026-11-09" if method in METHODS else None})
    missing = sorted(required - assessed)
    for key in required - claimed: unresolved_categories.add(COVERAGE.get(key, "user_defined"))
    complete = not missing
    total = modeled + supplied
    out = {"schema_version": "1.0", "level": "L0", "mode": "components", "design_mass_kg": mass_kg,
           "empty_mass_kg": total if complete else None, "known_subtotal_kg": total, "operating_empty_mass_kg": None,
           "mass_basis": "declared zero-mission-fuel empty inventory; crew and payload outside; no certified OEW",
           "coverage": {"complete": complete, "required": sorted(required), "assessed": sorted(assessed), "missing": missing,
                        "known_mass_modeled_kg": modeled, "known_mass_supplied_kg": supplied,
                        "modeled_fraction_of_known_mass": modeled / total if total else None,
                        "note": "coverage is declared accounting, not independently verified completeness or predictive accuracy"},
           "items": rows, "group_totals_kg": {k: None if k in unresolved_categories else v for k, v in groups.items()},
           "known_group_subtotals_kg": groups,
           "pressurization": press_note,
           "uncertainty": "uncalibrated historical regressions and user masses; no verified numerical accuracy bound",
           "dry_airframe_mass_kg": groups["airframe"] if "airframe" not in unresolved_categories else None,
           "checks": [{"name": "empty_component_coverage", "passed": complete},
                      {"name": "positive_empty_inventory", "passed": total > 0 if complete else None},
                      {"name": "empty_below_design_mass", "passed": total < mass_kg if complete else None,
                       "margin_kg": mass_kg - total if complete else None}],
           "issues": (["missing_or_out_of_domain:" + x for x in missing]
                      + (["nonpositive_empty_inventory"] if complete and total <= 0 else [])
                      + (["empty_not_below_design_mass"] if complete and total >= mass_kg else [])),
           "assumptions": [{"path": "weights", "value": deepcopy(settings), "source": "explicit inputs / PRESSUPOSTO unless substantiated"}],
           "method": "Declared component inventory; optional Raymer transport regressions (actual methods per item), no residual fit",
           "validity": "Historical conventional metal transport only for regressions; fuselage L/D is structural fineness (ADAC/SUAVE); "
                       "no automatic composite corrections, BWB pressure-shell, engine-location trade, full MDA or certified OEW.",
           "accounting": "All supplied group masses are totals, not per engine. Fuel-system dry tanks/pumps are included once; "
                         "mission fuel, unusable fuel, crew and payload are excluded. Storage inventory is not added again. "
                         "engines_dry has no Sec.15.3.2 thrust correlation (remains supplied). No assembly/CG feedback.",
           "citations": {"aerosandbox": SOURCE_URL, "adac_ch15": ADAC_URL, "suave_fuselage": SUAVE_FUSE_URL,
                         "retrieved": "2026-11-09"}}
    try: json.dumps(out, allow_nan=False)
    except ValueError as exc: raise ValueError("weight arithmetic outside finite domain") from exc
    return out
