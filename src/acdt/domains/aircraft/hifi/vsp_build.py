"""OpenVSP build script (run with the OpenVSP Python, ``python vsp_build.py spec.json``).

Builds the parametric acdt configuration in OpenVSP (McDonald & Gloudemans, "Open Vehicle Sketch Pad: An Open
Source Parametric Geometry and Analysis Tool for Conceptual Aircraft Design", AIAA 2022-0004): trapezoidal wing
(NACA 4/5-digit sections, dihedral, quarter-chord sweep, incidence), horizontal and vertical tails, and a POD
fuselage (length + fineness ratio). Writes .vsp3, STEP, STL and the CompGeom wetted areas (JSON).
Kept free of acdt imports: it runs in a separate interpreter (OpenVSP ships its own CPython build)."""
import json
import sys

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
    vsp.SetParmVal(g, "Sweep", "XSec_1", s["sweep_c4_deg"])
    vsp.SetParmVal(g, "Sweep_Location", "XSec_1", 0.25)
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
    vsp.Update()
    return g


def main(spec_path):
    sp = json.load(open(spec_path))
    vsp.VSPRenew()
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
    _surface("Wing", sp["wing"])
    _surface("Htail", sp["htail"])
    _surface("Vtail", sp["vtail"], vertical=True)
    vsp.Update()
    out = sp["out_stem"]
    vsp.WriteVSPFile(out + ".vsp3")
    # model is in metres; OpenVSP's STEP/IGES default length unit is ft (LEN_FT) — declare metres
    vid = vsp.GetVehicleID()
    for grp in ("STEPSettings", "IGESSettings"):
        pid = vsp.FindParm(vid, "LenUnit", grp)
        if pid:
            vsp.SetParmVal(pid, float(vsp.LEN_M))
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
    json.dump({"components": [{"name": n, "wet_area": a, "theo_area": t, "volume": v}
                              for n, a, t, v in zip(names, wet, theo, vol)],
               "version": vsp.GetVSPVersion()}, open(out + "_compgeom.json", "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
