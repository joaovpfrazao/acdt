"""MCP registration of the P1 tools (:mod:`acdt.ai.assembly`): generic component geometry + integration checker.
``build_server`` calls :func:`register`."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import Field

from . import assembly as A

ASM = Annotated[dict, Field(description=(
    "{components: [...]} in the aircraft frame (x aft, y starboard, z up, m). Each component: type body | "
    "surface | disc, name, role (free text), origin [x,y,z], orientation {yaw,pitch,roll} deg, mirror (y=0 "
    "image), mass_kg, cg, transparent_to ['rf'|'optical'...], opacity. body: stations [{x,w,h,zc,yc,n}] "
    "(Lamé section, n=2 ellipse) or pod {length,width,height,nose_frac,tail_frac,tail_scale,n}. surface: "
    "sections [{le:[x,y,z],chord,twist_deg,tc}] or panel {root_chord,tip_chord,span,sweep_le_deg,dihedral_deg,"
    "tc_root,tc_tip,twist_tip_deg}. disc (prop): diameter, thickness. No configuration enum: assemble any "
    "layout (twin boom, canard, flying wing, box/joined wing, V/inverted V/H tails, pusher/tractor...)."))]


def register(srv, ann, call) -> None:
    tool = srv.tool

    @tool(name="assembly_geometry", annotations=ann(False, "Generic component geometry (any configuration)"))
    async def assembly_geometry(assembly: ASM, write_files: bool = True, name: str = "assembly") -> dict[str, Any]:
        """Build an aircraft from generic parts and return volumes, wetted / planform areas, centroids and
        bounding boxes; writes assembly.stl (for `rcs` STL mode / CAD viewers) and assembly.avl (surfaces)."""
        return await call(A.assembly_geometry, assembly, write_files, name)

    @tool(name="integration_check", annotations=ann(False, "Packaging + field-of-view + mass/CG check"))
    async def integration_check(
            assembly: ASM,
            items: Annotated[list, Field(description=(
                "equipment [{name, mass_kg, size_m [lx,ly,lz], position [x,y,z] (omit → placed by deterministic "
                "grid search in host), host, prefer {x|y|z: value|'min'|'max'}, power_w {avg, peak}, heat_w, "
                "cg_offset, aperture_offset, obstructs (external turret blocks other FOVs), fov [{name, band, "
                "az_deg [a,b], el_deg [a,b] | axis [x,y,z] + half_angle_deg, step_deg, max_blocked_frac, "
                "range_m, ignore}]}]. az from nose to starboard, el up."))],
            constraints: Annotated[Optional[list], Field(description=(
                "[{type: within {item, body} | range {item, axis, min, max} | min_separation {a, b, distance_m} | "
                "max_distance {a, b, distance_m} | keep_out {name, zone: {box [[lo],[hi]] | sphere {center, "
                "radius} | component, clearance_m}, items '*'|[...]} | sky_view {item, el_min_deg, band} | "
                "cg_range {axis, min, max} | max_packing_fraction {body, max}}]"))] = None,
            base: Annotated[Optional[dict], Field(description="{mass_kg, cg [x,y,z]} rest of the aircraft")] = None,
            place_unpositioned: bool = True, name: str = "integration") -> dict[str, Any]:
        """Check integration requirements as constraints (never fixed slots): fit inside host volumes,
        no overlaps, separations, keep-out zones (prop arc...), FOV / sky-view obstruction by the aircraft itself
        (ray casting, Möller–Trumbore), CG window, packing fraction; returns per-constraint margins, violations,
        placements, mass / CG / inertia, power and heat totals, PRESSUPOSTOS. Low fidelity (N1)."""
        return await call(A.integration_check, assembly, items, constraints, base, place_unpositioned, name)

    @tool(name="assembly_sizing", annotations=ann(False, "Assembly as an aircraft: masses, CD0, AVL, gear, CG"))
    async def assembly_sizing(
            spec: Annotated[dict, Field(description=(
                "{assembly (as in assembly_geometry), items/constraints (as in integration_check; item 'group' "
                "payload|fuel|equipment|propulsion), masses [{name, mass_kg, group, position [x,y,z] | component}], "
                "gear {type tricycle|none, tipback_deg, nose_fraction [lo,hi], rotation_min_deg, prop_clearance_m, "
                "ground_z, x_main, x_nose, half_track}, drag {Q {part: Q}, laminar {part: frac}}, material "
                "metal|composite, options {static_margin_min, np_source avl_torenbeek|avl_bodies|most_forward, "
                "checks_from assembly|fixed_type (hq:*/gear:* in acdt size), hq_case cheio|vazio|carga|combustível}}"))],
            flight: Annotated[dict, Field(description=(
                "{W0_kg, V_m_s, altitude_m, Nz | n_limit | category, Wf_kg, payload_kg}"))],
            options: Optional[dict] = None, name: str = "assembly_sizing") -> dict[str, Any]:
        """Evaluate ANY drawn configuration as an aircraft (P1b): Raymer GA per-part weights by role (V-tail
        split by Purser & Campbell), wetted-area CD0 buildup (Raymer Eq. 12.24), neutral point from AVL with
        BODY plus the Torenbeek App. E body shift, loading cases and static margin, tricycle gear placed from
        the geometry (tip-back, rotation clearance over the mesh, 14 CFR 23.925 prop clearance, overturn), and
        the integration check. Returns asm:* checks, notes and PRESSUPOSTOS. Low fidelity (N1)."""
        return await call(A.assembly_sizing, spec, flight, options, name)
