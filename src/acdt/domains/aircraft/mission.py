"""Mission specification: open requirement set + documented assumptions.

YAML layout::

    name: ...
    aircraft_class: ga_single_engine      # Raymer Table 3.1 / 6.3 class (statistics)
    requirements: {<key>: {min|max|target|objective: v, unit: u, <qualifiers>}}
    assumptions: {weights: {...}, aero: {...}, propulsion: {...}, geometry: {...}, constraints: {...}}
    systems: {...}                         # optional, acdt.core.systems stage

Every assumption has a default; the report lists all values actually used so
that each number is traceable (assumption vs. requirement vs. method output).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from acdt.core.requirements import RequirementSet

from . import requirement_types  # noqa: F401  (registers aircraft requirement types)

DEFAULT_ASSUMPTIONS: dict = {
    # method: "components" (statistical We/W0 only as the initial value, then component build-up,
    # weights_detailed) or "statistical" (Phase-1 behaviour). initial_class: statistical class for the
    # initial value (default: aircraft_class). components: options of weights_detailed.component_weights.
    "weights": {"method": "components", "initial_class": None, "fixed_fraction": None, "A": None, "C": None,
                "tech_factor": 1.0, "Kvs": 1.0, "fixed_mass_kg": 0.0, "components": {}},
    "aero": {
        "AR": 8.0, "taper": 0.5, "sweep_c4_deg": 0.0, "tc_root": 0.12, "tc_tip": 0.12, "xc_max_t": 0.30,
        "airfoil": "NACA 23015", "clmax_airfoil": 1.5, "flap": {"kind": "plain", "flapped_area_ratio": 0.6},
        "oswald": None, "cfe": 0.0055, "swet_sref": 4.0,
        "laminar": {"wing": 0.10, "htail": 0.10, "vtail": 0.10, "fuselage": 0.0},
        "roughness": "smooth_paint", "Q": {}, "lp_fraction": 0.05, "extra_drag_areas_m2": {},
        "CL_ground": 0.5, "dCD0_takeoff": 0.01, "mu_roll": 0.04,
        # Phase 2: "handbook" (Raymer Eq. 12.24 + Oswald) or "lowfi" (XFOIL/NeuralFoil section polars +
        # AVL span loading, aero/lowfi.py); airfoil_solver: xfoil | neuralfoil
        "fidelity": "handbook", "airfoil_solver": "xfoil",
    },
    "propulsion": {"eta_cruise": 0.80, "eta_climb": 0.75, "eta_takeoff": 0.55, "bsfc_lb_hp_h": None,
                   "tsfc_1_h": 0.5, "battery_Wh_kg": 200.0, "eta_total": 0.70, "dod": 0.80,
                   "energy_reserve": 0.20, "systems_power_W": 0.0, "n_engines": 1,
                   # fixed-pitch propeller map (propeller.py): {type: fixed_pitch, rpm_rated, diameter_m | tip_mach,
                   # pitch_m | auto, chord_075_over_D | static_rpm | auto, blades, airfoil}; None = constant etas
                   "propeller": None},
    "geometry": {"fuselage_length_m": None, "fuselage_diameter_m": None, "fuselage_fineness": 7.0,
                 "fuselage_class": None, "fuselage_profile": None, "tail_class": None, "c_ht": None, "c_vt": None,
                 "tail_arm_fraction": 0.60, "ar_h": 4.0, "ar_v": 1.5,
                 # dihedral_deg: explicit wing dihedral [deg] for AVL Clβ / spiral (Etkin & Reid /
                 # Nelson). None → PRESSUPOSTO 3° on TrapezoidalWing (backward compatible); set null
                 # deliberately to leave spiral unassessed. configuration: conventional (default) |
                 # V | inverted_V | twin_boom — named shortcuts that assemble generic components
                 # (assembly/shortcuts.py); never overwrite a supplied assumptions.assembly drawing.
                 "dihedral_deg": None, "configuration": "conventional",
                 "tail_dihedral_deg": None, "boom_span_fraction": 0.35, "pod_length_fraction": 0.55,
                 "boom_width_m": None, "taper_v": 0.5},
    "constraints": {"cruise_weight_fraction": 1.0, "landing_weight_fraction": 1.0, "approach_distance_ft": 600.0,
                    "margin": 0.0, "ws_initial_psf": 17.0, "ws_min": 50.0, "ws_max": 3000.0, "default_cruise_altitude_m": 0.0,
                    # criterion "fixed_ws": W/S [N/m²] (and optional P/W or T/W floor) given, e.g. by acdt optimize
                    "ws_fixed": None, "value_fixed": None},
    "mda": {"max_iter": 30, "tol": 1e-5, "tol_lowfi": 2e-4},
    # Phase 2 — structures.py: V-n (CS-23 / STANAG 4671), Schrenk loads, box-beam wing
    "structures": {"regulation": "auto", "load_factor_from_vn": True, "material": "auto",
                   "nonoptimum_factor": 1.25, "VH_eas_m_s": None,
                   # VD declarado [m/s EAS] (p. ex. VNE/0,9 de um TCDS, CS 22.1505); CD,min para o VD mínimo de
                   # CS 22.335(f); alívio extra na asa (lastro de água nos tanques da asa) e massa máxima das partes
                   # não sustentadoras (TCDS de planadores) — caso de flexão adicional
                   "VD_eas_m_s": None, "CD_min": None, "wing_relief_extra_kg": 0.0, "non_lifting_max_kg": None,
                   "elastic_axis": "section", "le_cell": True,
                   # L1 beam (structures_l1.py). Both default off: the size loop stays the rigid Raymer/Megson
                   # path. flex (or aero.elastic) feeds cruise twist back into K. mass_in_loop replaces the
                   # fuselage and tail group weights with the beam masses inside the MDA.
                   "flex": False, "mass_in_loop": False,
                   # Phase 5/6: freeze t/c, camber and geometric twist at the baseline (drawn washout)
                   "wingbox": {"hold_section": False}},
    # Phase 2 — stability.py (CG stations are ASSUMPTIONS until a layout exists)
    "stability": {"target_static_margin": 0.10, "wing_apex_x_fraction": None, "stations": {},
                  # inertias: components (sum) | roskam (Part V Eqs. 3.7–3.9, R̄ of roskam_reference or
                  # radii_of_gyration {Rx, Ry, Rz} on the operating empty mass + useful load by components)
                  "inertia_method": "components", "roskam_reference": None, "radii_of_gyration": None,
                  "elevator_max_deg": 25.0, "use_avl": True,
                  # Phase 3: dynamic modes + MIL-F-8785C level check (Class I; flight-phase category for cruise)
                  "dynamics": True, "hq_category": "B", "hq_required_level": 1},
    # Phase 2 — performance.py (segment mission, payload-range, field lengths, ceilings)
    "performance": {"fuel_capacity_kg": None, "max_payload_kg": None, "mu_brake": 0.4,
                    # approach angle [deg]: 3° = max. gradient 5.2 % of 14 CFR/CS 23.75(a)(1); steeper only if
                    # demonstrated, limited and indicated (23.75(a)(2))
                    "approach_angle_deg": 3.0},
    # Phase 3 — aeroelasticity.py (strip model on the wing box; OpenAeroStruct static coupling if installed)
    "aeroelasticity": {"enabled": True, "a_w": 6.283185307179586, "x_cg_chord": None, "margin_factor": 1.2,
                       "static_aerostructural": True},
    # Phase 3 — mdo.py (OpenMDAO). objective: None → from the requirement registry
    "mdo": {"objective": None, "solver": "nlbgs", "trust_region_iterations": 8, "trust_region_radius": 0.3, "design_vars": ["ws", "AR"], "AR_bounds": [5.0, 16.0],
            "ws_bounds_factor": [0.6, 1.4], "pw_bounds_factor": [0.6, 1.6], "maxiter": 60, "tol": 1e-6,
            # Opt-in: hq:*/aeroel:* as real MDO inequalities in φ / OpenMDAO (default = filter-after only)
            "hq_aeroel_constraints": False, "hq_aeroel_keys": None},
    "cost": {},
    # Phase 4 — hifi/calibration.py: factors L3 → L1/L2 (file = calibration.json of `acdt hifi`, and/or inline
    # factors); apply: groups to apply ("aero", "flutter", "structures" → k_EI and k_GJ only); empty → reported only
    "calibration": {"file": None, "apply": [], "factors": {}},
    # Operational loading diagram (weight_balance.py). Limits default to the stability-stage
    # aft (static margin) and forward (elevator at CLmax) CG. extra_items: [{name, x_m, mass_max_kg,
    # mass_min_kg, kind, fuel_order}]. loading, when set, replaces lumped crew/payload/fuel/battery:
    # [{name, mass_min_kg, mass_max_kg, kind, fuel_order, x_m | arm_in}]. arm_in is inches aft of the
    # firewall. mass_max_kg null on kind fuel uses the sized fuel mass.
    # forward_limit / aft_limit: [[mass_kg, x_m], ...] piecewise.
    "weight_balance": {"crew_optional": False, "extra_items": [], "x_forward_m": None, "x_aft_m": None,
                       "forward_limit": None, "aft_limit": None, "lemac_arm_in": None, "mac_in": None},
    # Landing-gear layout and 14 CFR 23.473 landing load (landing_gear.py). Lengths and the gear
    # load factor stay in weights.components, because the weight equations already use them.
    "landing_gear": {"h_cg_m": None, "tipback_deg": 15.0, "overturn_max_deg": 63.0,
                     "nose_fraction_min": 0.08, "nose_fraction_max": 0.15, "wing_lift_fraction": 2.0 / 3.0,
                     "absorber": "oleo", "eta": None, "stroke_m": None, "tire_stroke_m": 0.0,
                     "max_stroke_m": None, "rotation_min_deg": 10.0, "x_nose_m": None, "x_main_m": None,
                     "x_tail_m": None, "track_m": None, "x_nose_min_m": 0.0, "x_main_max_m": None},
    # Opt-in catapult launch / belly landing, first order (launch_recovery.py). None → not run. Example:
    # {catapult: {accel_g: 10, rail_angle_deg: 10, stroke_max_m: 6, airframe_nx_limit_g: 12, payload_nx_limit_g: 15},
    #  belly_landing: {mu_slide: 0.5, n_limit: 4.0}}. Missing limits → the check is unassessed, never a pass.
    "launch_recovery": None,
    # Disciplina ruído L0 (noise.py; docs/RUIDO.md). Precisa de propulsion.propeller (mapa BEMT). other_sources:
    # {status: desprezaveis | incluidas, justification} declara as fontes não modeladas; sem isso o nível é um
    # limite inferior. engine_noise: {octave_dB: {f: dB}, distance_m, source}. certification: {part36_G: {...}}.
    "noise": {"enabled": True, "T_C": 15.0, "rh_pct": 70.0, "p_kpa": 101.325, "harmonics": 10,
              "effective_radius_fraction": 0.8, "broadband": True, "blade_thickness_ratio": None,
              "flyover_altitude_m": None, "flyover_speed_m_s": None, "sideline_m": 0.0, "ground_dB": 0.0,
              "ambient_third_octave_dB": None, "detection_margin_dB": 0.0, "other_sources": None,
              "engine_noise": None, "certification": None},
    # Disciplina térmica L0/L1 (thermal.py; docs/TERMICA.md). bays: compartimentos [{id, skin_area_m2, flow_length_m,
    # height_m, eps_ext, alpha_solar, eps_int, sources, components: [{id, source|heat_W, conductance_W_K|case_area_m2,
    # T_max_C, T_min_C, limit_source}], ram_air, fan, capacity_J_K}]; sem bays → fuselagem π·D·L. coupling:
    # relatorio (uma passagem, efeito relatado) | iterar (ponto fixo com o dimensionamento).
    "thermal": {"enabled": True, "coupling": "relatorio", "max_iter": 6, "tol": 0.01,
                "hot_atmosphere": "mil310_hot_1pct", "cold_atmosphere": "mil310_cold_1pct", "solar_W_m2": None,
                "ground": True, "ground_time_s": None, "conditions": None, "bays": None, "sources": {},
                "radiated_fraction": 0.0,
                "electric": {"eta_esc": None, "eta_motor": None, "eta_battery": None, "cell_R_internal_ohm": None,
                             "source": None},
                "engine": {"fuel": None, "lhv_MJ_kg": None, "cooling_fraction": None, "heat_rejection_W": None,
                           "air_temperature_rise_K": None, "ram_recovery": None, "duct_loss_q": None,
                           "mass_flow_ratio": None, "source": None},
                "components": [], "transient": None},
    # Disciplina gelo L0/L1 (icing.py; docs/GELO.md). surfaces: [{id, chord_m + t_c | le_radius_m | d_m, lifting,
    # critical, protection: none|anti_ice_thermal|deice_electrothermal|boots, protected_area_m2 |
    # protected_chord_fraction, surface_temperature_C, duty_cycle, power_density_W_m2, parting_strip_area_m2,
    # electric, mass_kg}]; sem surfaces → asa + estabilizadores sem proteção. temperature: envelope | isa.
    "icing": {"enabled": True, "coupling": "relatorio", "max_iter": 6, "tol": 0.01,
              "envelopes": ["continuous", "intermittent"], "mvd_um": None, "conditions": None, "surfaces": None,
              "temperature": "envelope", "isa_dT_K": 0.0, "fiki": None, "max_altitude_m": None,
              "power_schedule": "exposicao"},
    # Disciplina fiabilidade L0 (reliability.py; docs/FIABILIDADE.md). Sem components → não avaliada (desconhecida).
    # components: [{id, supplier | rate_key | lambda_per_h | mtbf_h (+ source), n, duty, critical, mttr_h,
    # mmh_per_action, replacement_cost, spares}], rbd, preventive, logistics, utilization, fleet, spares,
    # operating_cost (bloco de manufacturing.costing; manutenção preenchida pela fiabilidade).
    # Estrutura paramétrica (structure_layout.py; docs/ESTRUTURA_PARAMETRICA.md). Opt-in. Ver DEFAULTS no módulo
    # (fuselage: cavernas/anteparas/reforçadores/cargas; booms; export do modelo de vigas).
    "structure_layout": {"enabled": False, "coupling": "relatorio"},
    "reliability": {"enabled": True, "components": None, "rbd": None, "mission_duration_h": None,
                    "accept_assumptions": False, "preventive": None, "logistics": None, "utilization": None,
                    "fleet": None, "spares": None, "operating_cost": None, "labour_rate_per_h": None},
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("Q", "extra_drag_areas_m2"):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class MissionSpec:
    name: str
    requirements: RequirementSet
    aircraft_class: str = "ga_single_engine"
    description: str = ""
    assumptions: dict = field(default_factory=lambda: copy.deepcopy(DEFAULT_ASSUMPTIONS))
    systems: dict | None = None
    source: Path | None = None
    # requisitos derivados/regulamentares e opções da matriz de verificação (acdt.core.verification; docs/REQUISITOS.md)
    verification: dict | None = None

    @classmethod
    def from_dict(cls, d: dict, source: Path | None = None) -> "MissionSpec":
        # Automatic close: top-level / assumptions.onboard → native hotel/extraction + incremental mass
        # inside acdt size (MissionSpec / run_pipeline). No separate onboard_size call required for
        # mass/fuel/energy coupling. Missing BSFC/η/model → raise unassessed (never free energy).
        # Absent onboard → unchanged. Full CG/FOV/closure screens remain on `acdt onboard size`.
        # Unidades escritas ("3.2 m", {value: 10, unit: ft}) → unidade que a chave declara (acdt.core.quantities;
        # docs/DADOS.md). Números simples ficam iguais: os YAML sem unidades funcionam como antes.
        if isinstance(d, dict):
            from acdt.core.quantities import normalise_tree
            d = dict(d)
            for sec in ("assumptions", "systems", "onboard"):
                if isinstance(d.get(sec), (dict, list)):
                    d[sec] = normalise_tree(d[sec], sec)
        d_in = d
        if isinstance(d, dict) and (d.get("onboard") or (d.get("assumptions") or {}).get("onboard")):
            from .onboard_bridge import apply_onboard_to_size_dict
            d_in, bridge = apply_onboard_to_size_dict(d)
            if bridge.get("status") == "unassessed" and not bridge.get("applied"):
                raise ValueError(f"onboard hotel unassessed: {bridge.get('reason')}")
        else:
            d_in = d
        return cls(name=d_in.get("name", "unnamed"), description=d_in.get("description", ""),
                   aircraft_class=d_in.get("aircraft_class", "ga_single_engine"),
                   requirements=RequirementSet.from_dict(d_in.get("requirements", {}), domain="aircraft"),
                   assumptions=_merge(DEFAULT_ASSUMPTIONS, d_in.get("assumptions", {})),
                   systems=d_in.get("systems"), source=source, verification=d_in.get("verification"))

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MissionSpec":
        p = Path(path)
        return cls.from_dict(yaml.safe_load(p.read_text(encoding="utf-8")), p)

    @property
    def propulsion_kind(self) -> str:
        return self.requirements.value("propulsion_type", "piston_prop")
