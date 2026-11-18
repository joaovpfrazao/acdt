"""Process models per part (Phase 7): labour hours, tooling, buy-to-fly, cycle time and feasibility checks.

Methods (all cited in :mod:`.refdata`):

* **FOPV** — first-order process velocity model (Gutowski et al. 1994), hyperbolic form
  ``t = sqrt((x/V0)^2 + 2 tau x / V0)`` with the generic-wing parameters of Bao & Samareh (2000) / Bao (2002):
  aluminium parts *milled* and composite parts *lay-up / RTM*, by part kind (skin, spar, rib) and the
  assembly model on the joined perimeter. Used for: ``cnc_machining`` (metal FOPV, native), all composite
  moulding routes (composite FOPV, native) and ``sheet_metal_riveted`` (metal FOPV used as a proxy — flagged).
* **ACCEM** woven-fabric lay-up per ply ``t[h] = 0.000851 A[in^2]^0.6295`` (Northrop 1976 via Hagnell &
  Akermo 2016) — reported as a cross-check for laminated parts when the ply count is known.
* **rate-based** models where the time is set by a machine rate that only a datasheet can give
  (filament winding deposition rate, FDM/SLS build rate, cure cycle) — required inputs, never defaulted.

Every process distinguishes itself through cited data *or* through inputs (material price, tooling quote,
machine rate, cure cycle). Where no public differentiating data exists (e.g. wet lay-up vs infusion vs prepreg
touch labour) the shared composite FOPV is used and the output says so; supply quotes or shop data to refine.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from . import refdata as R

IN2 = 0.0254**2
IN = 0.0254

METALS = ("metal",)
COMPOSITES = ("composite", "composite_equivalent")
POLYMERS = ("polymer",)

# part kind -> FOPV part model (Bao & Samareh only publish skin / spar / rib; others mapped and flagged)
FOPV_KIND = {"skin": "skin", "shell": "skin", "fairing": "skin", "spar": "spar", "longeron": "spar",
             "stringer": "spar", "rib": "rib", "frame": "rib", "bulkhead": "rib", "fitting": "rib"}

PROCESSES = {
    "cnc_machining": {"materials": METALS, "fopv": "metal", "b2f": "cnc_machining", "tooling": True,
                      "desc": "CNC machining from plate/bar (FOPV aluminium-milled parameters)"},
    "sheet_metal_riveted": {"materials": METALS, "fopv": "metal", "b2f": "sheet_metal_riveted", "tooling": True,
                            "proxy": True, "desc": "sheet metal (routed blanks, formed) + riveted assembly"},
    "wet_layup": {"materials": COMPOSITES, "fopv": "composite", "b2f": "composite", "tooling": True,
                  "cure": "room/oven", "desc": "hand wet lay-up, vacuum bag optional"},
    "vacuum_infusion": {"materials": COMPOSITES, "fopv": "composite", "b2f": "composite", "tooling": True,
                        "cure": "room/oven", "desc": "dry fabric + resin infusion (VARTM)"},
    "prepreg_ooa": {"materials": COMPOSITES, "fopv": "composite", "b2f": "composite", "tooling": True,
                    "cure": "oven", "desc": "prepreg, out-of-autoclave oven cure"},
    "prepreg_autoclave": {"materials": COMPOSITES, "fopv": "composite", "b2f": "composite", "tooling": True,
                          "cure": "autoclave", "desc": "prepreg, autoclave cure"},
    "filament_winding": {"materials": COMPOSITES, "fopv": None, "b2f": "composite", "tooling": True,
                         "desc": "filament winding on a mandrel (axisymmetric / convex parts)"},
    "fdm": {"materials": POLYMERS, "fopv": None, "b2f": None, "tooling": False,
            "desc": "fused deposition modelling (polymer)"},
    "sls": {"materials": POLYMERS, "fopv": None, "b2f": None, "tooling": False,
            "desc": "selective laser sintering (polymer powder)"},
}


@dataclass
class Part:
    """One manufactured part (or a set of identical parts, ``count``) of the airframe."""
    name: str
    kind: str                    # skin | shell | spar | rib | frame | longeron | stringer | fitting | fairing ...
    mass_kg: float               # flown mass of one part
    area_m2: float               # wetted (moulded/machined) area of one part — FOPV extensive variable
    perimeter_m: float = 0.0     # joined edge length (assembly FOPV, rivet count)
    max_dim_m: float = 0.0       # largest dimension (envelope checks)
    thickness_m: float = 0.0     # nominal gauge / laminate thickness
    count: int = 1               # identical parts per aircraft
    group: str = ""              # wing | htail | vtail | fuselage ...
    double_curvature: bool = False
    axisymmetric: bool = False   # surface of revolution / convex closed section (filament winding)
    n_plies: int | None = None
    material: str | None = None  # material key (library or external) chosen for this part
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def fopv_minutes(x: float, V0: float, tau: float) -> float:
    """Hyperbolic FOPV time [min] for extensive variable x (in^2 or in), V0 [x-unit/min], tau [min]."""
    return math.sqrt((x / V0) ** 2 + 2.0 * tau * x / V0)


def accem_layup_hours(area_m2: float, n_plies: int) -> float:
    """ACCEM woven-fabric lay-up time [h] for n plies of one area (per-ply equation summed)."""
    a, b = R.ACCEM_WOVEN_LAYUP
    return n_plies * a * (area_m2 / IN2) ** b


def material_class(mat: dict) -> str:
    k = mat.get("kind", "metal")
    return "composite" if k in COMPOSITES else k


def _num(d: dict, key: str, default=None):
    v = d.get(key, default)
    return None if v is None else float(v)


def evaluate(part: Part, process: str, material: dict, inp: dict | None = None) -> dict:
    """Evaluate one process for one part.

    ``material``: ``{key, kind (metal|composite_equivalent|polymer), rho, usd_per_kg, t_min?, ...}``
    (``usd_per_kg`` already escalated to the study year; see :func:`plan.price_material`).
    ``inp`` (all optional, per process): ``labour_rate_usd_h`` (study-year, default: refdata FOPV rate x CPI),
    ``V0``/``tau`` overrides, ``b2f``, ``tooling_cost`` (USD, per part design), ``cure_h`` (cycle time),
    ``envelope_m`` (machine/autoclave/oven/bed max dimension), ``deposition_kg_h`` (filament winding),
    ``build_cm3_h`` (FDM/SLS), ``machine_rate_usd_h``, ``rivet_D_m``, ``rivet_pitch_D``, ``rivet_rows``,
    ``fastener_usd``, ``min_gauge_m``.

    Returns hours per part (first-unit basis, see :mod:`.plan` for learning), material cost, tooling and the
    feasibility verdict ``feasible`` (True / False) with ``reasons`` and ``missing`` inputs."""
    P = PROCESSES[process]
    inp = dict(inp or {})
    mc = material_class(material)
    out = {"part": part.name, "process": process, "material": material.get("key"), "feasible": True,
           "reasons": [], "warnings": [], "missing": [], "method": [], "sources": []}

    def no(msg):
        out["feasible"] = False
        out["reasons"].append(msg)

    if mc not in [material_class({"kind": k}) for k in P["materials"]]:
        no(f"{process} does not process {mc} material ({material.get('key')})")
    # ------------------------------------------------------------------ feasibility (design-constraint checks)
    env = _num(inp, "envelope_m")
    if env is not None and part.max_dim_m > env:
        no(f"part {part.max_dim_m:.2f} m exceeds the {process} envelope {env:.2f} m")
    elif env is None and process in ("prepreg_autoclave", "fdm", "sls", "cnc_machining", "filament_winding"):
        out["warnings"].append("machine/autoclave envelope not given: size not checked (envelope_m)")
    tmin = _num(inp, "min_gauge_m", material.get("t_min"))
    if tmin and part.thickness_m and part.thickness_m < tmin:
        no(f"gauge {part.thickness_m*1e3:.2f} mm below the minimum {tmin*1e3:.2f} mm for {material.get('key')}")
    if process == "sheet_metal_riveted":
        if part.double_curvature:
            out["warnings"].append("double curvature: needs stretch/hydro forming tooling (supply tooling_cost)")
        if part.kind in ("fitting",):
            no("fittings are not sheet-metal parts (machined or forged)")
    if process == "filament_winding" and not part.axisymmetric:
        no("filament winding needs an axisymmetric/convex closed part on a removable mandrel")
    if mc == "composite" and process != "filament_winding":
        out["warnings"].append(
            "composite rules (MIL-HDBK-17F via Abbott): ply drop-offs >= 20:1, <= 2 plies per drop; no bucked "
            "rivets in laminate; fastener edge distance >= 3.0D")
        out["sources"].append("abbott_mil17")
    # ------------------------------------------------------------------ labour time
    rate = _num(inp, "labour_rate_usd_h")
    if rate is None:
        rate = R.FOPV_RATE_USD_H[0] * R.cpi_factor(int(inp.get("year", 2025)), R.FOPV_RATE_USD_H[1])
        out["warnings"].append(f"labour rate default: {R.FOPV_RATE_USD_H[0]} USD/h (2000, Bao & Samareh) x CPI "
                               f"-> {rate:.0f} USD/h; supply the shop rate (labour_rate_usd_h)")
    hours = None
    if P["fopv"]:
        fk = FOPV_KIND.get(part.kind)
        if fk is None:
            no(f"no FOPV model for part kind {part.kind}")
        else:
            V0, tau = R.FOPV[(P["fopv"], fk)]
            V0, tau = _num(inp, "V0", V0), _num(inp, "tau", tau)
            x_in2 = part.area_m2 / IN2
            hours = fopv_minutes(x_in2, V0, tau) / 60.0
            if x_in2 < 2 * tau * V0:
                out["warnings"].append(
                    f"FOPV time-constant regime (area {x_in2:.0f} in2 < 2 tau V0 = {2 * tau * V0:.0f} in2): the "
                    f"time is set by tau (generic transport-wing parts) and is likely high for small parts — "
                    f"calibrate (labour_calibration / V0, tau from shop data)")
            out["method"].append(f"FOPV {P['fopv']} '{fk}' (V0={V0:g} in2/min, tau={tau:g} min) on "
                                 f"{part.area_m2:.3f} m2")
            out["sources"] += ["gutowski1994", R.FOPV_SOURCE]
            if fk != part.kind:
                out["warnings"].append(f"part kind '{part.kind}' timed with the FOPV '{fk}' parameters (nearest "
                                       f"published part type)")
            if P.get("proxy"):
                out["warnings"].append("sheet metal timed with the aluminium-milled FOPV parameters (only "
                                       "published metal set) — supply shop V0/tau for formed sheet")
            if mc == "composite":
                out["warnings"].append("touch labour from the generic composite FOPV set (lay-up/RTM); no public "
                                       "data separates wet lay-up / infusion / prepreg labour — differentiate with "
                                       "V0/tau, material price, tooling and cure inputs")
                if part.n_plies:
                    out["accem_layup_h"] = accem_layup_hours(part.area_m2, part.n_plies)
                    out["sources"].append("accem_hagnell2016")
    elif process == "filament_winding":
        dep = _num(inp, "deposition_kg_h")
        if dep is None:
            out["missing"].append("deposition_kg_h (winding machine datasheet)")
        else:
            hours = part.mass_kg * _num(inp, "b2f", R.BUY_TO_FLY["composite"]["default"]) / dep
            out["method"].append(f"winding time = mass x B2F / {dep:g} kg/h")
    else:  # AM
        bld = _num(inp, "build_cm3_h")
        if bld is None:
            out["missing"].append("build_cm3_h (printer datasheet / slicer estimate)")
        else:
            vol = part.mass_kg / material["rho"] * 1e6
            hours = vol / bld
            out["method"].append(f"build time = {vol:.0f} cm3 / {bld:g} cm3/h (machine time)")
    # assembly (joined perimeter), rivets
    asm_h = 0.0
    fasteners = 0
    if part.perimeter_m > 0 and process not in ("fdm", "sls"):
        V0, tau = R.FOPV[("composite" if mc == "composite" else "metal", "assembly")]
        asm_h = fopv_minutes(part.perimeter_m / IN, V0, tau) / 60.0
        out["method"].append(f"assembly FOPV on {part.perimeter_m:.2f} m of joined perimeter")
    if process == "sheet_metal_riveted" and part.perimeter_m > 0:
        D = _num(inp, "rivet_D_m", R.RIVET_RULES["D_over_t"] * part.thickness_m if part.thickness_m else None)
        if not D:
            out["missing"].append("rivet_D_m")
        else:
            pD = _num(inp, "rivet_pitch_D", sum(R.RIVET_RULES["pitch_D"]) / 2)
            if pD < R.RIVET_RULES["pitch_min_D"]:
                no(f"rivet pitch {pD}D below the AC 43.13-1B minimum {R.RIVET_RULES['pitch_min_D']}D")
            rows = int(inp.get("rivet_rows", 1))
            fasteners = int(math.ceil(part.perimeter_m / (pD * D))) * rows
            out["method"].append(f"{fasteners} rivets (D={D*1e3:.1f} mm, pitch {pD:g}D, {rows} row(s))")
            out["sources"].append("faa_h_8083_31")
    elif mc == "composite" and part.perimeter_m > 0:
        out["warnings"].append("composite joints: bonded or fastened (no bucked rivets) — fastener count not modelled")
    fast_usd = _num(inp, "fastener_usd")
    if fast_usd is None:
        fast_usd = R.FASTENER_USD[0] * R.cpi_factor(int(inp.get("year", 2025)), R.FASTENER_USD[1])
    # ------------------------------------------------------------------ material, B2F
    b2f = _num(inp, "b2f")
    if b2f is None and P["b2f"]:
        bd = R.BUY_TO_FLY[P["b2f"]]
        b2f = bd["default"]
        out["sources"].append(bd["source"])
    if b2f is None:
        b2f = 1.0
        out["warnings"].append("buy-to-fly for AM not in the reference DB: 1.0 used (lower bound) — supply b2f "
                               "(support/powder refresh losses)")
    price = inp.get("usd_per_kg", material.get("usd_per_kg"))  # per-process stock form (plate vs sheet)
    if price is None:
        out["missing"].append(f"usd_per_kg for {material.get('key')} (research a dated quote / distributor price)")
    mat_cost = None if price is None else part.mass_kg * b2f * price
    # ------------------------------------------------------------------ machine time, cure, tooling
    mrate = _num(inp, "machine_rate_usd_h", 0.0)
    machine_cost = (hours or 0.0) * mrate if process in ("fdm", "sls", "filament_winding", "cnc_machining") else 0.0
    cure = _num(inp, "cure_h")
    if P.get("cure") and cure is None:
        out["warnings"].append("cure cycle time not given (cure_h, from the resin/prepreg datasheet)")
    tooling = _num(inp, "tooling_cost")
    out.update({
        "touch_hours": hours, "assembly_hours": asm_h,
        "labour_hours": None if hours is None else (hours if process not in ("fdm", "sls") else 0.0) + asm_h,
        "machine_hours": hours if process in ("fdm", "sls", "filament_winding") else None,
        "cycle_time_h": None if hours is None else hours + asm_h + (cure or 0.0),
        "labour_rate_usd_h": rate, "b2f": b2f, "bought_mass_kg": part.mass_kg * b2f, "scrap_kg": part.mass_kg * (b2f - 1),
        "material_cost": mat_cost, "fasteners": fasteners, "fastener_cost": fasteners * fast_usd,
        "machine_cost": machine_cost, "tooling_cost": tooling, "needs_tooling": P["tooling"],
    })
    if hours is None and not out["missing"] and out["feasible"]:
        out["missing"].append("process time")
    out["sources"] = sorted(set(out["sources"]))
    return out
