"""OpenVSP build script (run with the OpenVSP Python, ``python vsp_build.py spec.json``).

Builds the parametric acdt configuration in OpenVSP (McDonald & Gloudemans, "Open Vehicle Sketch Pad: An Open
Source Parametric Geometry and Analysis Tool for Conceptual Aircraft Design", AIAA 2022-0004): trapezoidal wing
(NACA 4/5-digit sections, dihedral, sweep, incidence, optional section twist), horizontal and vertical tails,
and a POD fuselage (length + fineness ratio). Tails and the fuselage are omitted when the spec has no key for
them, so a flying wing is only the wing. Writes .vsp3, STEP, STL, the CompGeom wetted areas and a read-back of
the parameters OpenVSP stored. An optional ``vspaero`` object runs one vortex-lattice point.
Kept free of acdt imports: it runs in a separate interpreter (OpenVSP ships its own CPython build)."""
import json
import math
import os
import subprocess
import sys
import time
import traceback

import openvsp as vsp


def _airfoil(gid, i, digits, tc):
    xs = vsp.GetXSecSurf(gid, 0)
    if len(digits) == 5:
        vsp.ChangeXSecShape(xs, i, vsp.XS_FIVE_DIGIT)
        x = vsp.GetXSec(xs, i)
        vsp.SetParmVal(vsp.GetXSecParm(x, "IdealCl"), 0.15 * int(digits[0]))
        vsp.SetParmVal(vsp.GetXSecParm(x, "CamberLoc"), 0.05 * int(digits[1]))  # NACA LPQXX: x_c = P/20
    else:
        vsp.ChangeXSecShape(xs, i, vsp.XS_FOUR_SERIES)
        x = vsp.GetXSec(xs, i)
        d = digits if len(digits) == 4 else "0012"
        vsp.SetParmVal(vsp.GetXSecParm(x, "Camber"), int(d[0]) / 100)
        vsp.SetParmVal(vsp.GetXSecParm(x, "CamberLoc"), max(int(d[1]) / 10, 0.1))
    vsp.SetParmVal(vsp.GetXSecParm(x, "ThickChord"), tc)


def _surface(name, s, vertical=False):
    g = vsp.AddGeom("WING")
    vsp.SetGeomName(g, name)
    vsp.SetDriverGroup(g, 1, vsp.SPAN_WSECT_DRIVER, vsp.ROOTC_WSECT_DRIVER, vsp.TIPC_WSECT_DRIVER)
    vsp.SetParmVal(g, "Span", "XSec_1", s["semispan"])
    vsp.SetParmVal(g, "Root_Chord", "XSec_1", s["c_root"])
    vsp.SetParmVal(g, "Tip_Chord", "XSec_1", s["c_tip"])
    sweep = s["sweep_deg"] if "sweep_deg" in s else s["sweep_c4_deg"]
    vsp.SetParmVal(g, "Sweep", "XSec_1", sweep)
    # 0.25 keeps the historical quarter-chord sweep. A spec that names sweep_location (0 = leading edge) wins.
    vsp.SetParmVal(g, "Sweep_Location", "XSec_1", s.get("sweep_location", 0.25))
    vsp.SetParmVal(g, "Dihedral", "XSec_1", s.get("dihedral_deg", 0.0))
    vsp.SetParmVal(g, "X_Rel_Location", "XForm", s["x"])
    vsp.SetParmVal(g, "Z_Rel_Location", "XForm", s.get("z", 0.0))
    vsp.SetParmVal(g, "Y_Rel_Rotation", "XForm", s.get("incidence_deg", 0.0))
    if vertical:
        vsp.SetParmVal(g, "X_Rel_Rotation", "XForm", 90.0)
        vsp.SetParmVal(g, "Sym_Planar_Flag", "Sym", 0.0)
    vsp.SetParmVal(g, "Tess_W", "Shape", s.get("tess_w", 33))
    vsp.SetParmVal(g, "SectTess_U", "XSec_1", s.get("tess_u", 16))
    vsp.Update()
    for i in (0, 1):
        _airfoil(g, i, s["airfoil"], s["tc"][i])
    tw = s.get("twist_deg")
    if tw is not None:
        xs = vsp.GetXSecSurf(g, 0)
        # Twist_Location is the pivot as a fraction of chord. OpenVSP's own default is 0.25.
        # The flying-wing loft rotates about the leading edge, so that spec sets 0.
        loc = s.get("twist_location")
        for i, ang in enumerate(tw):
            x = vsp.GetXSec(xs, i)
            vsp.SetParmVal(vsp.GetXSecParm(x, "Twist"), float(ang))
            if loc is not None:
                vsp.SetParmVal(vsp.GetXSecParm(x, "Twist_Location"), float(loc))
    vsp.Update()
    return g


def _xyz(gid, u, w):
    p = vsp.CompPnt01(gid, 0, u, w)
    return (p.x(), p.y(), p.z())


def _dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _incidence_deg(le, te, le_root, le_tip):
    """Signed chord rotation from +x about the outboard span, degrees. Positive is nose up.

    Same construction as the loft check: atan2(chord · (k × ex), chord · ex), with the span's x
    component removed. This is the AVL Ainc, not the x-z projection."""
    span = [le_tip[i] - le_root[i] for i in range(3)]
    span[0] = 0.0
    n = math.sqrt(sum(c * c for c in span))
    if n < 1e-14:
        return None
    k = [c / n for c in span]
    chord = [te[i] - le[i] for i in range(3)]
    kcross = (0.0, k[2], -k[1])
    return math.degrees(math.atan2(sum(chord[i] * kcross[i] for i in range(3)), chord[0]))


def _section_measure(gid):
    """Leading edge at w = 0.5 and trailing edge at w = 0, root (u = 0) and tip (u = 1).

    On this OpenVSP the wing surface is a loop: w = 0.5 is the leading edge and w = 0 meets w = 1
    at the trailing edge. The geometric t/c is the largest distance between those two sides divided
    by the chord. It is a check of the ThickChord parameter, not a substitute for it."""
    ends = {}
    for uname, u in (("root", 0.0), ("tip", 1.0)):
        le, te, te_other = _xyz(gid, u, 0.5), _xyz(gid, u, 0.0), _xyz(gid, u, 1.0)
        chord = _dist(le, te)
        best = 0.0
        if chord > 1e-9:
            for i in range(1, 40):
                w = i / 80.0
                best = max(best, _dist(_xyz(gid, u, w), _xyz(gid, u, 1.0 - w)) / chord)
        ends[uname] = {"le_m": list(le), "te_m": list(te), "te_other_m": list(te_other),
                       "te_closure_m": _dist(te, te_other), "chord_m": chord,
                       "tc_geometric": best}
    root, tip = ends["root"]["le_m"], ends["tip"]["le_m"]
    for uname, u in (("root", 0.0), ("tip", 1.0)):
        ends[uname]["nose_up_deg"] = _incidence_deg(ends[uname]["le_m"], ends[uname]["te_m"], root, tip)
        ends[uname]["te_minus_le_z_m"] = ends[uname]["te_m"][2] - ends[uname]["le_m"][2]
    return ends


def _parm(gid, name, group):
    pid = vsp.FindParm(gid, name, group)
    if not pid:
        return None
    return vsp.GetParmVal(pid)


def _xsec_parm(xsec, name):
    pid = vsp.GetXSecParm(xsec, name)
    if not pid:
        return None
    return vsp.GetParmVal(pid)


def _readback(gid):
    xs = vsp.GetXSecSurf(gid, 0)
    n = vsp.GetNumXSec(xs)
    secs = []
    for i in range(n):
        x = vsp.GetXSec(xs, i)
        secs.append({
            "ThickChord": _xsec_parm(x, "ThickChord"),
            "Twist": _xsec_parm(x, "Twist"),
            "Twist_Location": _xsec_parm(x, "Twist_Location"),
            "Camber": _xsec_parm(x, "Camber"),
            "CamberLoc": _xsec_parm(x, "CamberLoc"),
        })
    row = {
        "name": vsp.GetGeomName(gid),
        "Y_Rel_Rotation_deg": _parm(gid, "Y_Rel_Rotation", "XForm"),
        "Z_Rel_Location_m": _parm(gid, "Z_Rel_Location", "XForm"),
        "X_Rel_Location_m": _parm(gid, "X_Rel_Location", "XForm"),
        "Span_m": _parm(gid, "Span", "XSec_1"),
        "ProjectedSpan_m": _parm(gid, "ProjectedSpan", "XSec_1"),
        "TotalProjectedSpan_m": _parm(gid, "TotalProjectedSpan", "WingGeom"),
        "Dihedral_deg": _parm(gid, "Dihedral", "XSec_1"),
        "Sweep_deg": _parm(gid, "Sweep", "XSec_1"),
        "Sweep_Location": _parm(gid, "Sweep_Location", "XSec_1"),
        "xsec": secs,
    }
    try:
        row["sections"] = _section_measure(gid)
    except Exception:
        row["sections_error"] = traceback.format_exc()
    return row


def _input(analysis, name, kind):
    fn = vsp.GetDoubleAnalysisInput if kind == "d" else vsp.GetIntAnalysisInput
    return list(fn(analysis, name))


def _text_tail(path, limit=30000):
    if not os.path.isfile(path):
        return None
    data = open(path, errors="replace").read()
    return data if len(data) <= limit else data[-limit:]


def _thin_surface(analysis):
    """Put every surface on the thin set. A thick panel mesh on this build loads and then dies
    while attaching the trailing wake (``Could not find global edge for trailing wake``)."""
    vsp.SetIntAnalysisInput(analysis, "GeomSet", (int(vsp.SET_NONE),), 0)
    vsp.SetIntAnalysisInput(analysis, "ThinGeomSet", (int(vsp.SET_ALL),), 0)


def _vspaero(cfg, wing_id, stem):
    """One VSPAERO vortex-lattice point. Reference lengths come from the spec, not from the wing area.

    The analysis manager writes the case and stops before the solver. Launching the solver from that
    manager on this build does not return (the viewer binary is absent). The solver is therefore a
    separate process, the ``vspaero`` executable that sits next to the OpenVSP Python module.
    Both the geometry step and the sweep are thin surfaces: that is the lattice AVL solves."""
    analysis_geom = "VSPAEROComputeGeometry"
    analysis = "VSPAEROSweep"
    vsp.SetVSPAERORefWingID(wing_id)
    vsp.SetAnalysisInputDefaults(analysis_geom)
    _thin_surface(analysis_geom)
    t0 = time.time()
    vsp.ExecAnalysis(analysis_geom)
    vsp.SetAnalysisInputDefaults(analysis)
    alpha = float(cfg["alpha_deg"])
    mach = float(cfg["mach"])
    ncpu = int(cfg.get("ncpu", 4))
    vsp.SetIntAnalysisInput(analysis, "RefFlag", (0,), 0)
    vsp.SetIntAnalysisInput(analysis, "AlphaNpts", (1,), 0)
    vsp.SetIntAnalysisInput(analysis, "WakeNumIter", (int(cfg.get("wake_iter", 5)),), 0)
    vsp.SetIntAnalysisInput(analysis, "NCPU", (ncpu,), 0)
    vsp.SetIntAnalysisInput(analysis, "StallModel", (0,), 0)
    vsp.SetIntAnalysisInput(analysis, "StopBeforeRun", (1,), 0)
    _thin_surface(analysis)
    vsp.SetDoubleAnalysisInput(analysis, "AlphaStart", (alpha,), 0)
    vsp.SetDoubleAnalysisInput(analysis, "AlphaEnd", (alpha,), 0)
    vsp.SetDoubleAnalysisInput(analysis, "MachStart", (mach,), 0)
    vsp.SetDoubleAnalysisInput(analysis, "MachEnd", (mach,), 0)
    vsp.SetDoubleAnalysisInput(analysis, "Sref", (float(cfg["sref"]),), 0)
    vsp.SetDoubleAnalysisInput(analysis, "bref", (float(cfg["bref"]),), 0)
    vsp.SetDoubleAnalysisInput(analysis, "cref", (float(cfg["cref"]),), 0)
    vsp.SetDoubleAnalysisInput(analysis, "Xcg", (float(cfg["xcg"]),), 0)
    vsp.SetDoubleAnalysisInput(analysis, "Ycg", (float(cfg.get("ycg", 0.0)),), 0)
    vsp.SetDoubleAnalysisInput(analysis, "Zcg", (float(cfg.get("zcg", 0.0)),), 0)
    if cfg.get("re_cref") is not None:
        vsp.SetDoubleAnalysisInput(analysis, "ReCref", (float(cfg["re_cref"]),), 0)
    inputs = {}
    for name, kind in (("RefFlag", "i"), ("AlphaNpts", "i"), ("AlphaStart", "d"), ("AlphaEnd", "d"),
                       ("MachStart", "d"), ("WakeNumIter", "i"), ("NCPU", "i"), ("StallModel", "i"),
                       ("StopBeforeRun", "i"), ("GeomSet", "i"), ("ThinGeomSet", "i"),
                       ("Sref", "d"), ("bref", "d"), ("cref", "d"),
                       ("Xcg", "d"), ("ReCref", "d")):
        try:
            inputs[name] = _input(analysis, name, kind)
        except Exception as exc:
            inputs[name] = "ERR " + type(exc).__name__
    vsp.ExecAnalysis(analysis)
    exe = os.path.join(os.path.dirname(os.path.abspath(vsp.__file__)), "vspaero")
    t1 = time.time()
    proc = subprocess.run([exe, "-omp", str(ncpu), stem], cwd=os.getcwd(),
                          capture_output=True, text=True, timeout=1200)
    wall = time.time() - t1
    return {"inputs": inputs, "surface": "thin", "solver": os.path.basename(exe),
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-4000:], "stderr_tail": proc.stderr[-4000:],
            "history": _text_tail(stem + ".history"), "polar": _text_tail(stem + ".polar"),
            "geometry_wall_s": t1 - t0, "sweep_wall_s": wall,
            "ref_wing": vsp.GetVSPAERORefWingID()}


def main(spec_path):
    sp = json.load(open(spec_path))
    vsp.VSPRenew()
    if "fuselage" in sp:
        f = sp["fuselage"]
        fu = vsp.AddGeom("POD")
        vsp.SetGeomName(fu, "Fuselage")
        vsp.SetParmVal(fu, "Length", "Design", f["length"])
        # OpenVSP POD: max radius = Length / FineRatio (measured on the exported STL), so FineRatio = 2 L / D
        vsp.SetParmVal(fu, "FineRatio", "Design", 2 * f["length"] / f["diameter"])
        vsp.SetParmVal(fu, "Z_Rel_Location", "XForm", f.get("z", 0.0))
        vsp.SetParmVal(fu, "X_Rel_Location", "XForm", f.get("x", 0.0))
        vsp.SetParmVal(fu, "Tess_U", "Shape", 25)
        vsp.SetParmVal(fu, "Tess_W", "Shape", 33)
    wing = _surface("Wing", sp["wing"])
    if "htail" in sp:
        _surface("Htail", sp["htail"])
    if "vtail" in sp:
        _surface("Vtail", sp["vtail"], vertical=True)
    vsp.Update()
    out = sp["out_stem"]
    vsp.WriteVSPFile(out + ".vsp3")
    # model is in metres; OpenVSP's STEP/IGES default length unit is ft (LEN_FT) — declare metres
    vid = vsp.GetVehicleID()
    len_unit = {}
    for grp in ("STEPSettings", "IGESSettings"):
        pid = vsp.FindParm(vid, "LenUnit", grp)
        if pid:
            vsp.SetParmVal(pid, float(vsp.LEN_M))
            len_unit[grp] = vsp.GetParmVal(pid)
    vsp.ExportFile(out + ".step", vsp.SET_ALL, vsp.EXPORT_STEP)
    vsp.ExportFile(out + ".stl", vsp.SET_ALL, vsp.EXPORT_STL)
    # wing-only STEP for the CFD wing case
    vsp.SetSetFlag(vsp.FindGeomsWithName("Wing")[0], 3, True)
    vsp.ExportFile(out + "_wing.step", 3, vsp.EXPORT_STEP)
    vsp.ComputeCompGeom(vsp.SET_ALL, False, 0)
    rid = vsp.FindLatestResultsID("Comp_Geom")
    names = vsp.GetStringResults(rid, "Comp_Name")
    wet = vsp.GetDoubleResults(rid, "Wet_Area")
    theo = vsp.GetDoubleResults(rid, "Theo_Area")
    vol = vsp.GetDoubleResults(rid, "Wet_Vol")
    readback = []
    for gid in vsp.FindGeoms():
        readback.append(_readback(gid))
    payload = {"components": [{"name": n, "wet_area": a, "theo_area": t, "volume": v}
                              for n, a, t, v in zip(names, wet, theo, vol)],
               "version": vsp.GetVSPVersion(),
               "len_unit": len_unit,
               "len_unit_metre": float(vsp.LEN_M),
               "readback": readback}
    with open(out + "_compgeom.json", "w") as fh:
        json.dump(payload, fh, indent=1)
    if "vspaero" in sp:
        try:
            payload["vspaero"] = _vspaero(sp["vspaero"], wing, out)
        except Exception:
            payload["vspaero_error"] = traceback.format_exc()
        with open(out + "_compgeom.json", "w") as fh:
            json.dump(payload, fh, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
