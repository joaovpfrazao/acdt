"""Gerador de modelo JSBSim (XML) a partir do :class:`FlightModel` — sem importar o JSBSim.

O ficheiro segue o formato JSBSim (Berndt & De Marco, *JSBSim Reference Manual*, aircraft configuration file):
``metrics``, ``mass_balance``, ``ground_reactions`` (BOGEY mola-amortecedor), ``external_reactions`` (tração com o
mesmo modelo de :class:`Propulsion`, sem motor JSBSim), ``system`` (manete e tração), ``flight_control``
(δe, δa, δr, flap em rad/deg, convenções do ACDT) e ``aerodynamics`` com tabelas α × flap reamostradas do modelo
tabelado (incluindo a mistura de perda) e derivadas de taxa/comando.

Equivalências: forças e momentos referidos ao AERORP = x_ref + dx_fus·c̄ (reproduz C_m,cg = C_m,ref + C_N k);
momentos de rolamento/guinada convertidos de eixos de estabilidade para eixos do corpo (cos α, sin α).
O arrasto induzido inclui os incrementos C_Lδe δe e C_Lq q̂ (como no 6-DOF próprio) e o momento de guinada da força
lateral transferida do AERORP é cancelado (o C_n fica referido a x_ref, como no 6-DOF próprio) — 11 nov 2026.
Diferenças conhecidas face ao 6-DOF próprio: massa constante (sem queima de combustível); unidades inglesas
internas."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .aeromodel import FlightModel

FT = 3.280839895
IN = 39.37007874
LBF = 0.2248089431
SLUG = 0.0685217659
SLUGFT2 = 0.7375621493  # kg m² → slug ft²
LBS = 2.2046226218
N_PER_M_TO_LBS_PER_FT = LBF / FT


def _table2(fm: FlightModel, fn, alphas_deg, name="") -> str:
    a = fm.aero
    flaps = a.flap_deg
    rows = []
    head = "            " + " ".join(f"{f:10.3f}" for f in flaps)
    for ad in alphas_deg:
        vals = [fn(math.radians(ad), f) for f in flaps]
        rows.append(f"      {math.radians(ad):9.5f} " + " ".join(f"{v:10.6f}" for v in vals))
    if len(flaps) == 1:
        body = "\n".join(f"      {math.radians(ad):9.5f} {fn(math.radians(ad), flaps[0]):10.6f}" for ad in alphas_deg)
        return (f"<table>\n      <independentVar lookup=\"row\">aero/alpha-rad</independentVar>\n"
                f"      <tableData>\n{body}\n      </tableData>\n     </table>")
    return (f"<table>\n      <independentVar lookup=\"row\">aero/alpha-rad</independentVar>\n"
            f"      <independentVar lookup=\"column\">fcs/flap-pos-deg</independentVar>\n      <tableData>\n{head}\n"
            + "\n".join(rows) + "\n      </tableData>\n     </table>")


def _prop(p):
    return f"<property>{p}</property>"


def _fn(name, desc, *factors) -> str:
    return (f"   <function name=\"{name}\">\n    <description>{desc}</description>\n    <product>\n     "
            + "\n     ".join(factors) + "\n    </product>\n   </function>")


def _drag_names(drag_fns: list[str]) -> list[str]:
    import re
    return [m.group(1) for f in drag_fns for m in [re.search(r'function name="([^"]+)"', f)] if m]


def write_jsbsim_aircraft(fm: FlightModel, root: str | Path, name: str = "acdt") -> Path:
    """Write ``<root>/aircraft/<name>/<name>.xml`` (and empty engine/systems dirs). Returns the XML path."""
    a, mp, pr = fm.aero, fm.mass, fm.prop
    root = Path(root)
    d = root / "aircraft" / name
    d.mkdir(parents=True, exist_ok=True)
    (root / "engine").mkdir(exist_ok=True)
    (root / "systems").mkdir(exist_ok=True)
    alphas = list(np.arange(-30.0, 40.01, 1.0))
    x_cg_in = mp.x_cg * IN
    x_ac_in = (a.x_ref + a.dx_fus * a.c) * IN

    sig = lambda al, fl: a.sigma(al, fl)  # noqa: E731
    oms = lambda al, fl: 1.0 - a.sigma(al, fl)  # noqa: E731

    def basic(key):
        return lambda al, fl: a.coefficients(al, 0, 0, 0, 0, 0, 0, 0, 0, fl, a.x_ref + a.dx_fus * a.c)[key]

    tab = lambda key: (lambda al, fl: a._interp(key, al, fl))  # noqa: E731
    Cm_ref = lambda al, fl: a._interp("Cm", al, fl)  # noqa: E731
    # ---------------- aerodynamics
    q, S, b, c = _prop("aero/qbar-psf"), _prop("metrics/Sw-sqft"), _prop("metrics/bw-ft"), _prop("metrics/cbarw-ft")
    T = lambda f, n: _table2(fm, f, alphas, n)  # noqa: E731
    ph, qh, rh, adh = _prop("aero/ps-hat"), _prop("aero/q-hat"), _prop("aero/rs-hat"), _prop("aero/alphadot-hat")
    de, da, dr = _prop("fcs/elevator-pos-rad"), _prop("fcs/aileron-pos-rad"), _prop("fcs/rudder-pos-rad")
    beta = _prop("aero/beta-rad")
    pre = f"""  <function name="aero/ps-hat">
   <description>stability-axis roll rate p b/2V</description>
   <product>{_prop("aero/bi2vel")}<sum>
    <product>{_prop("velocities/p-aero-rad_sec")}<cos>{_prop("aero/alpha-rad")}</cos></product>
    <product>{_prop("velocities/r-aero-rad_sec")}<sin>{_prop("aero/alpha-rad")}</sin></product></sum></product>
  </function>
  <function name="aero/rs-hat">
   <description>stability-axis yaw rate r b/2V</description>
   <product>{_prop("aero/bi2vel")}<difference>
    <product>{_prop("velocities/r-aero-rad_sec")}<cos>{_prop("aero/alpha-rad")}</cos></product>
    <product>{_prop("velocities/p-aero-rad_sec")}<sin>{_prop("aero/alpha-rad")}</sin></product></difference></product>
  </function>
  <function name="aero/q-hat">
   <product>{_prop("aero/ci2vel")}{_prop("velocities/q-aero-rad_sec")}</product>
  </function>
  <function name="aero/alphadot-hat">
   <product>{_prop("aero/ci2vel")}{_prop("aero/alphadot-rad_sec")}{_prop("acdt/alphadot-enable")}</product>
  </function>
"""

    def coef(name, terms):
        return (f"  <function name=\"aero/coefficient/{name}\">\n   <sum>\n" +
                "\n".join(f"    <product>{t}</product>" for t in terms) + "\n   </sum>\n  </function>")

    Cls = coef("Cl_s", [T(tab("Clb"), "Clb") + beta, T(tab("Clp"), "Clp") + ph, T(tab("Clr"), "Clr") + rh,
                        T(tab("Clda"), "Clda") + da, T(tab("Cldr"), "Cldr") + dr])
    Cns = coef("Cn_s", [T(tab("Cnb"), "Cnb") + beta, T(tab("Cnp"), "Cnp") + ph, T(tab("Cnr"), "Cnr") + rh,
                        T(tab("Cnda"), "Cnda") + da, T(tab("Cndr"), "Cndr") + dr])
    al = _prop("aero/alpha-rad")
    lift = [_fn("aero/force/L_basic", "C_L(α, flap) incl. stall blend", q, S, T(basic("CL"), "CL_basic")),
            _fn("aero/force/L_q", "(1-σ) C_Lq q̂", q, S, T(oms, "one_minus_sigma"), T(tab("CLq"), "CLq"), qh),
            _fn("aero/force/L_adot", "(1-σ) C_Lα̇ α̇̂", q, S, T(oms, "one_minus_sigma"), f"<value>{a.CLad}</value>", adh),
            _fn("aero/force/L_de", "(1-σ) C_Lδe δe", q, S, T(oms, "one_minus_sigma"), T(tab("CLde"), "CLde"), de)]
    drag = [_fn("aero/force/D_basic", "C_D(α, flap): C_D0 + ΔC_D0,flap + K C_L² blended", q, S, T(basic("CD"), "CD_basic"))]
    # induced drag of the δe / q̂ lift increments, as in the in-house 6-DOF (C_D = C_D0 + K C_L,lin², C_L,lin with
    # C_Lδe δe + C_Lq q̂): (1-σ) K [2 C_L0 X + X²], X = C_Lδe δe + C_Lq q̂ (14 nov 2026: was omitted — trim throttle
    # differed by up to ~11 % on a tailless design with large trim δe)
    Kv = f"<value>{a.K:.8f}</value>"
    for nm, ds, fac in (("D_de_CL0", "2 K C_L0 C_Lδe δe", [f"<value>{2 * a.K:.8f}</value>", T(tab("CL"), "CL_lin0"), T(tab("CLde"), "CLde"), de]),
                        ("D_de2", "K (C_Lδe δe)²", [Kv, T(tab("CLde"), "CLde"), de, T(tab("CLde"), "CLde"), de]),
                        ("D_q_CL0", "2 K C_L0 C_Lq q̂", [f"<value>{2 * a.K:.8f}</value>", T(tab("CL"), "CL_lin0"), T(tab("CLq"), "CLq"), qh]),
                        ("D_q2", "K (C_Lq q̂)²", [Kv, T(tab("CLq"), "CLq"), qh, T(tab("CLq"), "CLq"), qh]),
                        ("D_de_q", "2 K C_Lδe δe C_Lq q̂", [f"<value>{2 * a.K:.8f}</value>", T(tab("CLde"), "CLde"), de, T(tab("CLq"), "CLq"), qh])):
        drag.append(_fn(f"aero/force/{nm}", f"(1-σ) {ds}", q, S, T(oms, "one_minus_sigma"), *fac))
    if getattr(a, "yaw_drag_per_Cn", 0.0):  # tailless drag rudder: rudder channel = ΔC_n, ΔC_D = k |ΔC_n|
        drag.append(f"""   <function name="aero/force/D_drag_rudder">
    <description>split-aileron drag rudder: k |C_ndr δr| (assembly.tailless, McCormick 1995 Eq. 3.45)</description>
    <product>{q}{S}<value>{a.yaw_drag_per_Cn:.6f}</value><abs><product>{T(tab("Cndr"), "Cndr")}{dr}</product></abs></product>
   </function>""")
    side = [_fn("aero/force/Y_beta", "C_Yβ β", q, S, T(tab("CYb"), "CYb"), beta),
            _fn("aero/force/Y_p", "C_Yp p̂", q, S, T(tab("CYp"), "CYp"), ph),
            _fn("aero/force/Y_r", "C_Yr r̂", q, S, T(tab("CYr"), "CYr"), rh),
            _fn("aero/force/Y_da", "C_Yδa δa", q, S, T(tab("CYda"), "CYda"), da),
            _fn("aero/force/Y_dr", "C_Yδr δr", q, S, T(tab("CYdr"), "CYdr"), dr)]
    roll = [f"""   <function name="aero/moment/Roll">
    <description>body-axis: Cl_s cos α − Cn_s sin α</description>
    <product>{q}{S}{b}<difference>
     <product>{_prop("aero/coefficient/Cl_s")}<cos>{al}</cos></product>
     <product>{_prop("aero/coefficient/Cn_s")}<sin>{al}</sin></product></difference></product>
   </function>"""]
    yaw = [f"""   <function name="aero/moment/Yaw">
    <description>body-axis: Cl_s sin α + Cn_s cos α</description>
    <product>{q}{S}{b}<sum>
     <product>{_prop("aero/coefficient/Cl_s")}<sin>{al}</sin></product>
     <product>{_prop("aero/coefficient/Cn_s")}<cos>{al}</cos></product></sum></product>
   </function>"""]
    # JSBSim transfers every aero force from the AERORP (x_ref + dx_fus c̄, chosen to reproduce C_m) to the CG; the
    # in-house 6-DOF transfers the side force from x_ref only (dx_fus is a pitch-only fuselage correction, the body's
    # yaw effect is already in C_nβ). Cancel the extra (dx_fus c̄)·Y yaw moment so both models carry the same C_n.
    if a.dx_fus:
        ysum = "".join(_prop(f"aero/force/Y_{k}") for k in ("beta", "p", "r", "da", "dr"))
        dsum = "".join(_prop(n) for n in _drag_names(drag))
        bb = _prop("aero/beta-rad")
        # body side force of the wind-axis aero forces: Y cosβ − D sinβ (JSBSim manual, wind → body rotation)
        yaw.append(f"""   <function name="aero/moment/Yaw_aerorp_side_force_correction">
    <description>cancel the side-force transfer from the AERORP offset dx_fus c̄ (yaw stays about x_ref)</description>
    <product><value>{a.dx_fus * a.c * FT:.8f}</value><difference>
     <product><sum>{ysum}</sum><cos>{bb}</cos></product>
     <product><sum>{dsum}</sum><sin>{bb}</sin></product></difference></product>
   </function>""")
    pitch = [_fn("aero/moment/Pitch_basic", "C_m(α, flap) about the AERORP", q, S, c, T(Cm_ref, "Cm0")),
             _fn("aero/moment/Pitch_q", "C_mq q̂", q, S, c, T(tab("Cmq"), "Cmq"), qh),
             _fn("aero/moment/Pitch_adot", "C_mα̇ α̇̂", q, S, c, f"<value>{a.Cmad}</value>", adh),
             _fn("aero/moment/Pitch_de", "C_mδe δe", q, S, c, T(tab("Cmde"), "Cmde"), de)]

    def axis(n, fns):
        return f"  <axis name=\"{n}\">\n" + "\n".join(fns) + "\n  </axis>"
    aero_xml = ("<aerodynamics>\n" + pre + Cls + "\n" + Cns + "\n" + axis("LIFT", lift) + "\n" + axis("DRAG", drag) + "\n"
                + axis("SIDE", side) + "\n" + axis("ROLL", roll) + "\n" + axis("PITCH", pitch) + "\n" + axis("YAW", yaw)
                + "\n </aerodynamics>")
    # ---------------- ground
    from .sixdof import GroundModel
    gm = GroundModel.from_model(fm)
    contacts = []
    for nm, rb, k, cd, steer, mu in gm.contacts:
        x_in = (mp.x_cg - rb[0]) * IN
        typ = "STRUCTURE" if nm == "tail_strike" or nm.startswith("skid") else "BOGEY"
        brake = "NONE" if (steer or typ == "STRUCTURE") else ("LEFT" if nm.endswith("L") else "RIGHT")
        contacts.append(f"""  <contact type="{typ}" name="{nm}">
   <location unit="IN"><x>{x_in:.3f}</x><y>{rb[1] * IN:.3f}</y><z>{-rb[2] * IN:.3f}</z></location>
   <static_friction>0.8</static_friction><dynamic_friction>0.5</dynamic_friction>
   <rolling_friction>{mu if mu is not None else gm.mu_roll}</rolling_friction>
   <spring_coeff unit="LBS/FT">{k * N_PER_M_TO_LBS_PER_FT:.2f}</spring_coeff>
   <damping_coeff unit="LBS/FT/SEC">{cd * N_PER_M_TO_LBS_PER_FT:.2f}</damping_coeff>
   <max_steer unit="DEG">{gm.steer_max_deg if steer else 0.0}</max_steer>
   <brake_group>{brake}</brake_group>
   <retractable>0</retractable>
  </contact>""")
    # ---------------- thrust (same model as Propulsion)
    from ..propulsion import is_propeller
    rho_r = f"<quotient>{_prop('atmosphere/rho-slugs_ft3')}<value>0.0023769</value></quotient>"
    if pr.kind == "piston_prop":
        lapse = f"<difference>{rho_r}<quotient><difference><value>1</value>{rho_r}</difference><value>7.55</value></quotient></difference>"
    elif pr.kind == "electric":
        lapse = "<value>1</value>"
    else:
        lapse = rho_r
    thr = _prop("fcs/throttle-pos-norm")
    prop_obj = pr.propeller() if hasattr(pr, "propeller") else None
    if prop_obj is not None:
        # fixed-pitch map (propeller.py) tabulated at SL: T(V, throttle) [lbf]; altitude through the same lapse
        # factor (PRESSUPOSTO: the rpm-matched point at altitude approximated by T_SL(V, δ)·lapse(σ))
        Vmax = prop_obj.J[-1] * prop_obj.rpm_rated / 60 * prop_obj.D
        Vs_ = np.linspace(0.0, Vmax, 15)
        ths = np.linspace(0.0, 1.0, 6)
        rows = "\n".join(f"      {v * FT:9.2f} " + " ".join(f"{prop_obj.operating_point(float(v), 0.0, float(t))['T'] * LBF:9.3f}"
                                                         for t in ths) for v in Vs_)
        Tn = (f"<table><independentVar lookup=\"row\">velocities/vt-fps</independentVar>"
              f"<independentVar lookup=\"column\">fcs/throttle-pos-norm</independentVar><tableData>\n"
              f"               " + " ".join(f"{t:9.2f}" for t in ths) + f"\n{rows}\n     </tableData></table>")
        thr = ""
    elif is_propeller(pr.kind):
        Tn = (f"<min><value>{pr.eta_takeoff * pr.P_sl / pr.V_low * LBF:.4f}</value><quotient><value>"
              f"{pr.eta_cruise * pr.P_sl * LBF * FT:.4f}</value><max>{_prop('velocities/vt-fps')}<value>0.01</value>"
              f"</max></quotient></min>")
    else:
        Tn = f"<value>{pr.T_sl * LBF:.4f}</value>"
    lim = a.limits
    def ch(nm, cmd, out, mx, extra=""):
        return f"""  <channel name="{nm}">
   <summer name="fcs/{nm}-sum"><input>{cmd}</input>{extra}<clipto><min>-1</min><max>1</max></clipto></summer>
   <aerosurface_scale name="fcs/{nm}-scale"><input>fcs/{nm}-sum</input>
    <range><min>{-math.radians(mx):.6f}</min><max>{math.radians(mx):.6f}</max></range>
    <output>{out}</output></aerosurface_scale>
  </channel>"""
    fcs = f"""<flight_control name="ACDT FCS">
  <property value="0">fcs/throttle-cmd-acdt</property>
  <property value="0">fcs/flap-cmd-deg</property>
  <property value="1">acdt/alphadot-enable</property>
{ch("pitch", "fcs/elevator-cmd-norm", "fcs/elevator-pos-rad", lim.get("elevator", 25), "<input>fcs/pitch-trim-cmd-norm</input>")}
{ch("roll", "fcs/aileron-cmd-norm", "fcs/aileron-pos-rad", lim.get("aileron", 25))}
{ch("yaw", "fcs/rudder-cmd-norm", "fcs/rudder-pos-rad", lim.get("rudder", 30))}
  <channel name="flaps-throttle">
   <pure_gain name="fcs/flap-pos"><input>fcs/flap-cmd-deg</input><gain>1</gain><output>fcs/flap-pos-deg</output></pure_gain>
   <pure_gain name="fcs/throttle-pos"><input>fcs/throttle-cmd-acdt</input><gain>1</gain>
    <clipto><min>0</min><max>1</max></clipto><output>fcs/throttle-pos-norm</output></pure_gain>
   <fcs_function name="fcs/thrust-lbs">
    <function><product>{thr}{lapse}{Tn}</product></function>
    <output>external_reactions/thrust/magnitude</output>
   </fcs_function>
  </channel>
 </flight_control>"""
    g = mp.gear
    xml = f"""<?xml version="1.0"?>
<!-- Gerado pelo ACDT (acdt.domains.aircraft.flightsim.jsbsim_export). Modelo de baixa fidelidade: AVL + polar + manual.
     Formato JSBSim (LGPL-2.1, executado como processo separado). -->
<fdm_config name="{name}" version="2.0" release="ALPHA">
 <fileheader><author>ACDT</author><description>{name}: modelo gerado do projecto conceptual</description></fileheader>
 <metrics>
  <wingarea unit="FT2">{a.S * FT**2:.4f}</wingarea>
  <wingspan unit="FT">{a.b * FT:.4f}</wingspan>
  <chord unit="FT">{a.c * FT:.4f}</chord>
  <location name="AERORP" unit="IN"><x>{x_ac_in:.3f}</x><y>0</y><z>0</z></location>
  <location name="EYEPOINT" unit="IN"><x>{x_cg_in:.3f}</x><y>0</y><z>20</z></location>
  <location name="VRP" unit="IN"><x>{x_cg_in:.3f}</x><y>0</y><z>0</z></location>
 </metrics>
 <mass_balance>
  <ixx unit="SLUG*FT2">{mp.Ixx * SLUGFT2:.4f}</ixx>
  <iyy unit="SLUG*FT2">{mp.Iyy * SLUGFT2:.4f}</iyy>
  <izz unit="SLUG*FT2">{mp.Izz * SLUGFT2:.4f}</izz>
  <ixz unit="SLUG*FT2">{mp.Ixz * SLUGFT2:.4f}</ixz>
  <emptywt unit="LBS">{mp.m * LBS:.4f}</emptywt>
  <location name="CG" unit="IN"><x>{x_cg_in:.3f}</x><y>0</y><z>0</z></location>
 </mass_balance>
 <ground_reactions>
{chr(10).join(contacts)}
 </ground_reactions>
 <external_reactions>
  <force name="thrust" frame="BODY" unit="LBS">
   <location unit="IN"><x>{x_cg_in:.3f}</x><y>0</y><z>{-pr.z_thrust * IN:.3f}</z></location>
   <direction><x>1</x><y>0</y><z>0</z></direction>
  </force>
 </external_reactions>
 {fcs}
 {aero_xml}
</fdm_config>
"""
    p = d / f"{name}.xml"
    p.write_text(xml)
    return p
