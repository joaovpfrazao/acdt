"""Phase 4 geometry: OpenVSP model (.vsp3), STEP (CAD/meshing) and STL (render) from the parametric
configuration, plus a CompGeom wetted-area check against the L0 wetted areas (Raymer Eq. 7.12 /
Torenbeek App. F) that feed the CD0 build-up.

Positions follow the AVL model of Phase 2 (x aft from the wing root leading edge, z up): the tail
leading edges from the tail arms (Raymer Eqs. 6.28–6.29), the fuselage nose at −x_wing_apex (stability
stage). The fuselage is an OpenVSP POD (length and fineness ratio) — a conceptual body of revolution, not
a lofted fuselage (stated). Wing vertical position: ``geometry.wing_position`` high | mid | low."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from ..aero.avl import wing_x_ac
from ..aero.interfaces import ToolNotAvailable, _naca_digits
from . import tools

VSP_REF = ("McDonald & Gloudemans, Open Vehicle Sketch Pad, AIAA 2022-0004 (NASA Open Source Agreement 1.3)")
BUILD_SCRIPT = Path(__file__).with_name("vsp_build.py")


def vsp_spec(res, out_stem: str | Path, tess: int = 33) -> dict:
    cfg = res.config
    w, ht, vt = cfg.wing, cfg.htail.as_wing(), cfg.vtail.as_wing()
    x_ac = wing_x_ac(w)
    x_ht = x_ac + cfg.htail.arm - (0.25 * ht.mac + ht.y_mac * math.tan(ht.sweep_at(0.0)))
    x_vt = x_ac + cfg.vtail.arm - 0.25 * vt.mac
    vh = cfg.vtail.S / ((vt.c_root + vt.c_tip) / 2)
    x_apex = getattr(res.stability, "x_wing_apex", None) or 0.3 * cfg.fuselage.length
    D = cfg.fuselage.max_diameter
    gs = res.spec.assumptions.get("geometry", {}) or {}
    pos = str(gs.get("wing_position", "mid")).lower()
    # high/low: root chord plane at the fuselage crown/keel, sunk by a quarter of the root thickness so the
    # root is embedded and CompGeom trims a watertight junction (ASSUMPTION, no fairing). Override with
    # geometry.wing_z_fraction (z / D, + up).
    t_root = w.tc_root * w.c_root
    zw = {"high": D / 2 - 0.25 * t_root, "low": -(D / 2 - 0.25 * t_root)}.get(pos, 0.0)
    if gs.get("wing_z_fraction") is not None:
        zw = float(gs["wing_z_fraction"]) * D
    inc = float(res.spec.assumptions.get("geometry", {}).get("wing_incidence_deg", 0.0) or 0.0)
    af = _naca_digits(w.airfoil) or "0012"
    return {
        "out_stem": str(out_stem),
        "fuselage": {"length": cfg.fuselage.length, "diameter": D, "x": -x_apex},
        "wing": {"semispan": w.span / 2, "c_root": w.c_root, "c_tip": w.c_tip,
                 "sweep_c4_deg": math.degrees(w.sweep_c4), "dihedral_deg": math.degrees(w.dihedral),
                 "x": 0.0, "z": zw, "incidence_deg": inc, "airfoil": af, "tc": [w.tc_root, w.tc_tip],
                 "tess_w": tess, "tess_u": 24},
        "htail": {"semispan": ht.span / 2, "c_root": ht.c_root, "c_tip": ht.c_tip,
                  "sweep_c4_deg": math.degrees(ht.sweep_c4), "x": x_ht, "z": 0.0, "airfoil": "0012",
                  "tc": [ht.tc_root, ht.tc_tip], "tess_w": tess, "tess_u": 10},
        "vtail": {"semispan": vh, "c_root": vt.c_root, "c_tip": vt.c_tip,
                  "sweep_c4_deg": math.degrees(vt.sweep_c4), "x": x_vt, "z": 0.0, "airfoil": "0010",
                  "tc": [vt.tc_root, vt.tc_tip], "tess_w": tess, "tess_u": 8},
    }


def flying_wing_vsp_spec(surf, name: str = "wing") -> dict:
    """OpenVSP spec of one lofted trapezoidal wing. No fuselage and no tails.

    Section twist is the loft twist, nose up positive, and the pivot is the leading edge
    (``twist_location`` 0). OpenVSP's own default pivot is the quarter chord; leaving that
    default would move the leading edge. Sweep is the leading-edge sweep of the straight
    panel. Thickness is the declared t/c on each section. The airfoil code is symmetric:
    the camber line of a NACA 4-digit name is not written, which is the same choice as
    :func:`acdt.domains.aircraft.hifi.wing_bl.avl_text`.
    """
    root, tip = surf.sections[0], surf.sections[-1]
    le0 = surf.to_global([root["le"]])[0]
    le1 = surf.to_global([tip["le"]])[0]
    dx = float(le1[0] - le0[0])
    dy = float(le1[1] - le0[1])
    dz = float(le1[2] - le0[2])
    panel = math.hypot(dy, dz)
    if panel <= 0.0 or dy <= 0.0:
        raise ValueError("a asa não tem envergadura positiva")
    return {
        "out_stem": name,
        "wing": {
            "semispan": panel,
            "c_root": float(root["chord"]),
            "c_tip": float(tip["chord"]),
            "sweep_deg": math.degrees(math.atan2(dx, panel)),
            "sweep_location": 0.0,
            "dihedral_deg": math.degrees(math.atan2(dz, dy)),
            "x": float(le0[0]),
            "z": float(le0[2]),
            "incidence_deg": 0.0,
            "airfoil": "0012",
            "tc": [float(root["tc"]), float(tip["tc"])],
            "twist_deg": [float(root["twist_deg"]), float(tip["twist_deg"])],
            "twist_location": 0.0,
            "tess_w": 41,
            "tess_u": 16,
        },
    }


def export_vsp(spec: dict, out: str | Path, name: str = "aircraft", timeout: float = 600) -> dict:
    """Run ``vsp_build.py`` in the OpenVSP interpreter. The acdt process does not import ``openvsp``.

    Raises ToolNotAvailable without ``$ACDT_VSP_PYTHON``. ``out_stem`` in the spec is replaced by
    ``name`` because the build's working directory is ``out``."""
    py = tools.vsp_python()
    if py is None:
        raise ToolNotAvailable("OpenVSP Python API ($ACDT_VSP_PYTHON) não encontrado; ver docs/tutorial-fase4.md §0")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    spec = dict(spec)
    spec["out_stem"] = name
    spec_path = out / f"{name}_vsp_spec.json"
    spec_path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    rc = tools.run([py, str(BUILD_SCRIPT), str(spec_path)], out, f"{name}_vsp.log", timeout=timeout)
    cg_path = out / f"{name}_compgeom.json"
    if rc != 0 or not cg_path.exists():
        raise RuntimeError(f"OpenVSP falhou (ver {cg_path.with_name(name + '_vsp.log')})")
    cg = json.loads(cg_path.read_text(encoding="utf-8"))
    case = out.resolve().parent

    def stored(suffix: str) -> str:
        return tools.case_relative(out / f"{name}{suffix}", case)

    return {"vsp3": stored(".vsp3"), "step": stored(".step"), "step_wing": stored("_wing.step"),
            "stl": stored(".stl"), "spec": spec, "compgeom": cg, "vsp_version": cg.get("version")}


def build_vsp(res, out: str | Path, name: str = "aircraft") -> dict:
    """Run the OpenVSP build (separate interpreter). Returns paths, CompGeom areas and the wetted-area
    comparison against L0. Raises ToolNotAvailable without ``$ACDT_VSP_PYTHON``."""
    info = export_vsp(vsp_spec(res, name), out, name)
    cg = info["compgeom"]
    l0 = res.config.wetted_areas()
    key = {"Fuselage": "fuselage", "Wing": "wing", "Htail": "htail", "Vtail": "vtail"}
    comp = []
    for c in cg["components"]:
        k = key.get(c["name"])
        if k:
            comp.append({"component": k, "Swet_vsp_m2": c["wet_area"], "Swet_L0_m2": l0[k],
                         "ratio": c["wet_area"] / l0[k] if l0[k] else math.nan})
    tot_v = sum(c["Swet_vsp_m2"] for c in comp)
    tot_0 = sum(c["Swet_L0_m2"] for c in comp)
    return {"vsp3": info["vsp3"], "step": info["step"], "step_wing": info["step_wing"],
            "stl": info["stl"], "spec": info["spec"], "vsp_version": cg.get("version"), "wetted": comp,
            "Swet_total_vsp": tot_v, "Swet_total_L0": tot_0, "Swet_ratio": tot_v / tot_0, "ref": VSP_REF,
            "readback": cg.get("readback"),
            "note": "CompGeom exclui as interseções (asa–fuselagem, cauda–fuselagem); L0: Raymer Eq. 7.12 com "
                    "área exposta e Torenbeek App. F para a fuselagem"}


def read_stl(path) -> np.ndarray:
    """Triangles (n, 3, 3) from an ASCII or binary STL."""
    data = Path(path).read_bytes()
    if data[:5] == b"solid" and b"facet" in data[:400]:
        v = [list(map(float, ln.split()[1:4])) for ln in data.decode(errors="ignore").splitlines()
             if ln.strip().startswith("vertex")]
        return np.array(v).reshape(-1, 3, 3)
    n = int.from_bytes(data[80:84], "little")
    rec = np.frombuffer(data[84:84 + 50 * n], dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    return rec["v"].astype(float)


def render_png(stl_path, png_path, title: str = "") -> str:
    """Shaded 3D render (isometric + top + front) of the STL with matplotlib (Lambert shading)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    tri = read_stl(stl_path)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-30
    lo, hi = tri.reshape(-1, 3).min(0), tri.reshape(-1, 3).max(0)
    ctr, R = (lo + hi) / 2, (hi - lo).max() / 2
    fig = plt.figure(figsize=(12, 10))
    views = [("isométrica", 25, -135), ("isométrica (trás)", 20, -45), ("planta", 90, -90), ("frente", 0, -180)]
    for i, (lab, el, az) in enumerate(views):
        ax = fig.add_subplot(2, 2, i + 1, projection="3d")
        e = np.radians(el)
        a = np.radians(az)
        view = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        light = view + np.array([0.3, 0.2, 0.6])
        light /= np.linalg.norm(light)
        shade = 0.25 + 0.75 * np.abs(nrm @ light)
        col = np.c_[0.55 * shade, 0.62 * shade, 0.75 * shade, np.ones_like(shade)]
        ax.add_collection3d(Poly3DCollection(tri, facecolors=col, edgecolors="none"))
        for k, lim in enumerate((ax.set_xlim, ax.set_ylim, ax.set_zlim)):
            lim(ctr[k] - R, ctr[k] + R)
        ax.set_box_aspect((1, 1, 1), zoom=1.45)
        ax.view_init(el, az)
        ax.set_axis_off()
        ax.set_title(lab)
    fig.suptitle(title or "OpenVSP")
    fig.tight_layout()
    fig.savefig(png_path, dpi=130)
    plt.close(fig)
    return str(png_path)
