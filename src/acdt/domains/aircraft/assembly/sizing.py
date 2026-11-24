"""P1b — the generic component assembly in the sizing loop: weights, CG / loading, neutral point, gear and CD0.

Any configuration assembled from :mod:`.components` (conventional, twin boom, inverted V, canard, tailless /
flying wing, box wing...) is evaluated with the same classical methods the fixed-type pipeline uses. Nothing
here knows a configuration name: each part is mapped to a method by its *kind* (lifting surface or body), its
free-text ``role`` and its geometry (dihedral of the panel).

Methods (all published; defaults that are not from a source are listed in :data:`ASSUMPTIONS`):

* Structure weights — Raymer, *Aircraft Design: A Conceptual Approach*, 6th ed., Sec. 15.3.3 (GA),
  ``weights_detailed.raymer_ga_*``: Eq. 15.46 every wing-like surface, Eq. 15.47 horizontal tails and canards,
  Eq. 15.48 fins and winglets, Eq. 15.49 every body (fuselage, pod, boom, nacelle, radome) with its *exposed*
  wetted area. V / inverted-V panels: the area is split into horizontal and vertical shares S·cos²Γ and
  S·sin²Γ (Purser & Campbell 1945, NACA Report 823 projected areas) and each share takes its equation.
  Composite factors: Raymer Table 15.4 (``weights_detailed.COMPOSITE_FACTORS``). A ``mass_kg`` on a part wins.
* Geometry of a surface — trapezoidal panels between sections: S = Σ ½(c_i + c_i+1)·s_i, MAC = (2/S)∫c² ds and
  the MAC leading edge = (1/S)∫c·x_LE ds (Raymer Sec. 7.4 / Fig. 7.3, integrated exactly for linear panels).
* CD0 — Raymer Eq. 12.24 component build-up (``aero.drag``): Cf Eqs. 12.25–12.28, FF Eq. 12.30 for surfaces
  (x/c of max thickness 0.30 for the NACA 4-digit sections of :mod:`.components`, Abbott & von Doenhoff 1959),
  Eq. 12.31 for bodies and Eq. 12.32 for nacelles / pods / stores; exposed wetted area from the meshes
  (triangles whose centroid lies inside another part are removed).
* Neutral point — AVL 3.x (Drela & Youngren) of the whole assembly: every surface as SURFACE and every
  axis-aligned body as BODY (source + doublet line, slender-body theory; an equivalent round body of the same
  cross-section area as the AVL guide asks). Cross-check: AVL without bodies plus the Torenbeek (1982) App. E
  fuselage shift Δx̄_ac = −(1.8/CLα_w)·b_f·h_f·l_fn/(S·c̄) for each body whose nose is ahead of the wing.
* Loading — Σ m·r for parts, placed equipment (:mod:`.integration`) and listed masses; CG at the empty,
  payload, fuel and full conditions; static margin (x_np − x_cg)/c̄ at every condition.
* Landing gear — ``landing_gear`` primitives (Raymer 2018 Ch. 11; Currey 1988): tricycle on the 15° tip-back
  ray and the 8–15 % nose-load band, overturn ≤ 63° (minimum half-track), rotation clearance of *every* part
  aft of the main wheels (mesh vertices, propeller tips included) against Raymer's 10–15°, propeller ground
  clearance 7 in tricycle / 9 in tailwheel (14 CFR 23.925(a)(1), as amended before Amdt. 23-64), and the nose
  leg kept out of any propeller disc.
"""
from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .assembly import Assembly
from .components import Body, Disc, Surface

LB, FT = 0.45359237, 0.3048
IN = 0.0254
XC_MAX_T_NACA4 = 0.30            # NACA 4-digit: max thickness at 30 % chord (Abbott & von Doenhoff 1959)

ASSUMPTIONS = [
    "PRESSUPOSTO: o papel (`role`) e o diedro decidem a equação de massa — superfície com 'wing'/'asa' ou a "
    "maior sem papel → Raymer 15.46; 'canard' ou cauda com |Γ| < 20° → 15.47; 'fin'/'winglet' ou |Γ| > 70° → "
    "15.48; entre 20° e 70° (V, V invertido) a área divide-se em S·cos²Γ (15.47) e S·sin²Γ (15.48), áreas "
    "projetadas de Purser & Campbell (NACA Rep. 823). O Raymer GA não tem equação de canard nem de lança.",
    "PRESSUPOSTO: cada corpo (fuselagem, pod, lança, nacelle, radome) pesa pela Eq. 15.49 com a sua área molhada "
    "exposta; L_t = braço da cauda (c/4 da CMA da asa → c/4 da CMA da cauda); sem cauda L_t = ½ do comprimento "
    "do corpo (expoente −0,051: menos de 4 % de efeito).",
    "PRESSUPOSTO: Q (interferência) por omissão 1,0 para asa e corpos e 1,04 para caudas (valores do pipeline "
    "clássico, dentro das gamas de Raymer Sec. 12.5.5); dá-se por componente em `drag.Q`.",
    "PRESSUPOSTO: escoamento laminar por omissão 10 % nas superfícies e 0 nos corpos (como `aero.laminar`).",
    "PRESSUPOSTO: CG de cada parte no centróide do volume; o grupo motopropulsor no cubo do disco quando não há "
    "massa listada para ele; o resto do equipamento do dimensionamento no centróide do corpo principal.",
    "PRESSUPOSTO: corpos com rotação (orientation ≠ 0) ficam fora do BODY do AVL (AVL BODY é sempre ao longo "
    "de x — avl_doc.txt slender bodies) e também fora do desvio de Torenbeek App. E (escrito para fuselagem "
    "ao longo de x). A contribuição desses corpos para x_np fica unassessed — nunca um stand-in alinhado.",
    "PRESSUPOSTO: a margem estática usa por omissão x_np = AVL sem corpos + desvio de Torenbeek (App. E); o "
    "AVL com BODY é sempre reportado e escolhe-se com `options.np_source` (avl_bodies | most_forward).",
    "PRESSUPOSTO: o chão é o plano z = ground_z na atitude estática; sem `ground_z` dado, calcula-se o mais alto "
    "que cumpre a rotação, a folga da hélice e a folga do ventre (é um resultado de projeto, não um dado).",
]


# ------------------------------------------------------------------------------------------- geometry
def surface_geometry(s: Surface) -> dict:
    """Planform quantities of one surface (both halves when ``mirror``), aircraft frame."""
    secs = s.sections
    le = s.to_global([sec["le"] for sec in secs])
    ch = np.array([sec["chord"] for sec in secs], float)
    tc = np.array([sec["tc"] for sec in secs], float)
    A = I2 = Ix = Iy = Iz = Itc = 0.0
    Gs = []
    for i in range(len(secs) - 1):
        d = le[i + 1] - le[i]
        sp = math.hypot(d[1], d[2])                        # panel length ⟂ x (on its own plane)
        c0, c1 = ch[i], ch[i + 1]
        a = 0.5 * (c0 + c1) * sp
        A += a
        I2 += sp * (c0 * c0 + c0 * c1 + c1 * c1) / 3.0
        for k, acc in ((0, "x"), (1, "y"), (2, "z")):
            v = sp * (2 * c0 * le[i, k] + c0 * le[i + 1, k] + c1 * le[i, k] + 2 * c1 * le[i + 1, k]) / 6.0
            if acc == "x":
                Ix += v
            elif acc == "y":
                Iy += v
            else:
                Iz += v
        Itc += a * 0.5 * (tc[i] + tc[i + 1])
        Gs.append((math.degrees(math.atan2(abs(d[2]), abs(d[1]))), a))
    n = 2 if s.mirror else 1
    half = max(A, 1e-12)
    mac = I2 / half                                        # (2/S)∫c² dy over one half
    span_along = sum(math.hypot(*(le[i + 1] - le[i])[1:]) for i in range(len(secs) - 1))
    b = n * span_along
    S = n * A
    dtot = le[-1] - le[0]
    sp_tot = math.hypot(dtot[1], dtot[2])
    c4 = le[:, 0] + 0.25 * ch
    xt = le[:, 0] + XC_MAX_T_NACA4 * ch
    sweep_c4 = math.atan2(c4[-1] - c4[0], sp_tot) if sp_tot > 0 else 0.0
    sweep_t = math.atan2(xt[-1] - xt[0], sp_tot) if sp_tot > 0 else 0.0
    sweep_le = math.atan2(le[-1, 0] - le[0, 0], sp_tot) if sp_tot > 0 else 0.0
    gamma = sum(g * a for g, a in Gs) / half
    x_mac_le = Ix / half
    return {"S": S, "S_half": A, "b": b, "AR": b * b / S if S > 0 else 0.0, "mac": mac,
            "x_mac_le": x_mac_le, "y_mac": abs(Iy / half), "z_mac": Iz / half, "x_ac": x_mac_le + 0.25 * mac,
            "taper": float(ch[-1] / ch[0]) if ch[0] > 0 else 1.0, "c_root": float(ch[0]), "c_tip": float(ch[-1]),
            "tc_mean": Itc / half, "tc_root": float(tc[0]), "sweep_c4": sweep_c4, "sweep_maxt": sweep_t,
            "sweep_le": sweep_le, "dihedral_deg": gamma, "x_root_le": float(le[0, 0]), "mirror": s.mirror}


def classify_surface(s: Surface, geo: dict, is_largest: bool) -> str:
    """wing | htail | vtail | vee | canard — from the free-text role, then from the dihedral."""
    r = (s.role or "").lower()
    g = abs(geo["dihedral_deg"])
    if "canard" in r:
        return "canard"
    if re.search(r"winglet|fin|vertical|deriva|leme|rudder", r):
        return "vtail"
    if re.search(r"tail|cauda|empen|stabil", r):
        return "htail" if g < 20 else ("vtail" if g > 70 else "vee")
    if re.search(r"wing|asa", r) or (not r and is_largest):
        return "wing"
    return "htail" if g < 20 else ("vtail" if g > 70 else "vee")


def _parts(asm: Assembly):
    surfs = [c for c in asm.components if isinstance(c, Surface) and not c.mirrored_image]
    bodies = [c for c in asm.components if isinstance(c, Body) and not c.mirrored_image and c.role != "item"]
    discs = [c for c in asm.components if isinstance(c, Disc) and not c.mirrored_image]
    geos = {s.name: surface_geometry(s) for s in surfs}
    big = max(surfs, key=lambda s: geos[s.name]["S"]).name if surfs else None
    kinds = {s.name: classify_surface(s, geos[s.name], s.name == big) for s in surfs}
    if surfs and "wing" not in kinds.values():
        kinds[big] = "wing"
    return surfs, bodies, discs, geos, kinds


def main_wing(asm: Assembly):
    surfs, _, _, geos, kinds = _parts(asm)
    wings = [s for s in surfs if kinds[s.name] == "wing"]
    if not wings:
        raise ValueError("assembly has no lifting surface")
    w = max(wings, key=lambda s: geos[s.name]["S"])
    return w, geos[w.name]


def exposed_wetted_areas(asm: Assembly, fine: int = 2) -> dict:
    """Wetted area of every part minus the triangles whose centroid is inside another (non-disc) part."""
    others = [c for c in asm.components if not isinstance(c, Disc)]
    out = {}
    for c in asm.components:
        if isinstance(c, Disc):
            continue
        V, F = c.mesh(fine)
        a, b, cc = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
        ar = 0.5 * np.linalg.norm(np.cross(b - a, cc - a), axis=1)
        cen = (a + b + cc) / 3.0
        inside = np.zeros(len(F), bool)
        for o in others:
            if o is c:
                continue
            inside |= o.contains(cen) > 1e-6
        key = c.name[:-2] if c.mirrored_image else c.name
        out[key] = out.get(key, 0.0) + float(ar[~inside].sum())
    return out


# ------------------------------------------------------------------------------------------- weights
@dataclass
class PartMass:
    name: str
    kind: str
    mass_kg: float
    method: str
    cg: list
    group: str = "structure"


def structure_weights(asm: Assembly, W0_kg: float, Nz: float, q_Pa: float, material: str = "metal",
                      Wfw_kg: float = 0.0, swet: dict | None = None) -> list[PartMass]:
    """Raymer GA Eqs. 15.46–15.49 per part (imperial inside, kg out); ``mass_kg`` on a part overrides."""
    from ..weights_detailed import (COMPOSITE_FACTORS, raymer_ga_fuselage, raymer_ga_htail, raymer_ga_vtail,
                                    raymer_ga_wing)
    surfs, bodies, _, geos, kinds = _parts(asm)
    swet = swet or exposed_wetted_areas(asm)
    Wdg, q = W0_kg / LB, q_Pa / 47.880259
    fac = (lambda k: float(np.mean(COMPOSITE_FACTORS[k]))) if material == "composite" else (lambda k: 1.0)
    w, gw = main_wing(asm)
    tails = [s for s in surfs if kinds[s.name] in ("htail", "vtail", "vee")]
    Lt_tail = None
    if tails:
        St = sum(geos[s.name]["S"] for s in tails)
        Lt_tail = sum(geos[s.name]["S"] * (geos[s.name]["x_ac"] - gw["x_ac"]) for s in tails) / St

    def cg_of(c):
        cs = [c] + ([asm.get(c.name + "~m")] if c.mirror else [])
        if c.cg is not None:
            return list(np.mean([np.asarray(x.cg, float) for x in cs], axis=0))
        return list(np.mean([x.centroid() for x in cs], axis=0))

    out = []
    for s in surfs:
        g, k = geos[s.name], kinds[s.name]
        S_ft2 = g["S"] / FT ** 2
        if s.mass_kg is not None:
            out.append(PartMass(s.name, k, float(s.mass_kg) * (2 if s.mirror else 1), "user (mass_kg por lado)",
                                cg_of(s)))
            continue
        if k == "wing":
            m = LB * raymer_ga_wing(S_ft2, Wfw_kg / LB, g["AR"], g["sweep_c4"], q, max(g["taper"], 1e-3),
                                    g["tc_mean"], Nz, Wdg) * fac("wing")
            meth = "Raymer Eq. 15.46"
        else:
            G = math.radians(abs(g["dihedral_deg"]))
            sh, sv = {"htail": (1.0, 0.0), "canard": (1.0, 0.0), "vtail": (0.0, 1.0),
                      "vee": (math.cos(G) ** 2, math.sin(G) ** 2)}[k]
            m, parts = 0.0, []
            if sh > 0:
                m += LB * raymer_ga_htail(sh * S_ft2, g["AR"], g["sweep_c4"], q, max(g["taper"], 1e-3),
                                          g["tc_mean"], Nz, Wdg) * fac("htail")
                parts.append(f"15.47 ×{sh:.2f}S")
            if sv > 0:
                m += LB * raymer_ga_vtail(sv * S_ft2, g["AR"], g["sweep_c4"], q, max(g["taper"], 1e-3),
                                          g["tc_mean"], Nz, Wdg) * fac("vtail")
                parts.append(f"15.48 ×{sv:.2f}S")
            meth = "Raymer Eq. " + " + ".join(parts) + (" (Purser & Campbell cos²Γ/sin²Γ)" if k == "vee" else "")
        out.append(PartMass(s.name, k, m, meth + (" × Table 15.4 composite" if material == "composite" else ""),
                            cg_of(s)))
    for b in bodies:
        n = 2 if b.mirror else 1
        if b.mass_kg is not None:
            out.append(PartMass(b.name, "body", float(b.mass_kg) * n, "user (mass_kg por instância)", cg_of(b)))
            continue
        h = max(max(st["h"] for st in b.stations), 1e-6)
        Lb = max(b.length, 1e-6)
        Lt = Lt_tail if (Lt_tail and Lt_tail > 0) else 0.5 * Lb
        Sf = swet.get(b.name, b.wetted_area() * n) / n / FT ** 2
        m = n * LB * raymer_ga_fuselage(Sf, Nz, Wdg, Lt / FT, Lb / FT, h / FT, q) * fac("fuselage")
        out.append(PartMass(b.name, "body", m, "Raymer Eq. 15.49 (área molhada exposta)" +
                            (" × Table 15.4 composite" if material == "composite" else ""), cg_of(b)))
    return out


# ------------------------------------------------------------------------------------------- drag
def cd0_buildup(asm: Assembly, V: float, rho: float, mu: float, a: float, Sref: float | None = None,
                opts: dict | None = None, swet: dict | None = None, items=None, positions: dict | None = None) -> dict:
    """Zero-lift drag of the assembly: Raymer build-up plus junction / upsweep / base / protuberance terms
    (see :mod:`.drag`)."""
    from .drag import cd0_buildup as _cd0
    return _cd0(asm, V, rho, mu, a, Sref, opts, swet, items, positions)


# ------------------------------------------------------------------------------------------- AVL
def _body_profile(b: Body, n: int = 41):
    """Equivalent round body (same Lamé section area): x, z_up, z_lo in the aircraft frame."""
    t = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))
    xl = b.stations[0]["x"] + t * b.length
    A = b.section_area(xl)
    r = np.sqrt(np.maximum(A, 0.0) / math.pi)
    zc = np.interp(xl, [s["x"] for s in b.stations], [s["zc"] for s in b.stations])
    x = b.origin[0] + xl
    z = b.origin[2] + zc
    return x, z + r, z - r


def _body_is_rotated(b: Body) -> bool:
    o = b.orientation or {}
    return any(abs(float(o.get(k, 0.0))) > 1e-9 for k in ("yaw", "pitch", "roll"))


def avl_geometry(asm: Assembly, outdir: Path, mach: float = 0.0, x_ref: float = 0.0, z_ref: float = 0.0,
                 with_bodies: bool = True) -> tuple[Path, list[str], list[str]]:
    """Write assembly.avl (surfaces + axis-aligned bodies as BODY/BFIL) into ``outdir``.

    Returns ``(path, notes, rotated_omitted)``. AVL BODY is always along aircraft x (avl_doc.txt slender
    bodies); a rotated body is **omitted** and listed in ``rotated_omitted`` — never rewritten as an
    axis-aligned stand-in (unknown≠pass).
    """
    w, gw = main_wing(asm)
    txt = asm.avl_text(mach=mach, ref={"Sref": gw["S"], "Cref": gw["mac"], "Bref": gw["b"]},
                       cg=(x_ref, 0.0, z_ref))
    notes, rotated = [], []
    if with_bodies:
        _, bodies, _, _, _ = _parts(asm)
        for b in bodies:
            if _body_is_rotated(b):
                rotated.append(b.name)
                notes.append(
                    f"corpo {b.name!r} com rotação {b.orientation}: fora do BODY do AVL "
                    f"(AVL BODY só ao longo de x — avl_doc.txt); contribuição unassessed, "
                    f"não substituída por um corpo alinhado")
                continue
            x, zu, zl = _body_profile(b)
            fn = f"body_{re.sub(r'[^A-Za-z0-9_]', '_', b.name)}.dat"
            pts = [(x[i], zu[i]) for i in range(len(x) - 1, -1, -1)] + [(x[i], zl[i]) for i in range(1, len(x))]
            (outdir / fn).write_text(b.name + "\n" + "\n".join(f"{p:.6f} {q:.6f}" for p, q in pts) + "\n",
                                     encoding="utf-8")
            txt += "#" + "=" * 60 + f"\nBODY\n{b.name}\n24 1.0\n"
            if b.mirror:
                txt += "YDUPLICATE\n0.0\n"
            txt += f"TRANSLATE\n0.0 {b.origin[1]:.5f} 0.0\nBFIL\n{fn}\n"
    path = outdir / "assembly.avl"
    path.write_text(txt, encoding="utf-8")
    return path, notes, rotated


def run_assembly_avl(asm: Assembly, alpha_deg: float = 2.0, mach: float = 0.0, x_ref: float = 0.0,
                     z_ref: float = 0.0, with_bodies: bool = True, exe: str = "avl", timeout: float = 60,
                     keep_dir=None, CL: float | None = None) -> dict:
    """One AVL point of the whole assembly; returns CL, CDi, e, Cm, CLa, Cma, Xnp and the stability-axis
    derivatives (CYβ, Clβ, Cnβ, CYp, Clp, Cnp, CYr, Clr, Cnr, CLq, Cmq). With ``CL`` AVL finds α for that CL
    (``a c``) instead of running at ``alpha_deg``."""
    from ..aero.avl import _grab
    from ..aero.interfaces import ToolNotAvailable
    exe_path = shutil.which(exe)
    if exe_path is None:
        raise ToolNotAvailable("AVL binary not found on PATH")
    tmp = Path(keep_dir) if keep_dir else Path(tempfile.mkdtemp(prefix="acdt_asm_avl_"))
    tmp.mkdir(parents=True, exist_ok=True)
    geo, notes, rotated = avl_geometry(asm, tmp, mach, x_ref, z_ref, with_bodies)
    (tmp / "st.txt").unlink(missing_ok=True)
    trim = f"a c {CL:.6f}" if CL is not None else f"a a {alpha_deg:.5f}"
    cmds = ["oper", trim, f"m\nmn {mach:.4f}\n", "x", "st", "st.txt", "", "quit"]
    from acdt.core.provenance import tool_used
    tool_used("avl", exe_path)
    r = subprocess.run([exe_path, geo.name], input="\n".join(cmds) + "\n", capture_output=True, text=True,
                       timeout=timeout, cwd=tmp)
    if not (tmp / "st.txt").exists():
        raise RuntimeError(f"AVL failed on the assembly. Last output:\n{r.stdout[-1500:]}")
    st = (tmp / "st.txt").read_text(encoding="utf-8")
    out = {k: _grab(st, key) for k, key in (("alpha_deg", "Alpha"), ("CL", "CLtot"), ("CDi", "CDff"), ("e", "e"),
                                             ("Cm", "Cmtot"), ("CLa", "CLa"), ("Cma", "Cma"), ("Xnp", "Xnp"),
                                             ("Cnb", "Cnb"), ("Clb", "Clb"))}
    for k in ("CYb", "CYp", "Clp", "Cnp", "CYr", "Clr", "Cnr", "CLq", "Cmq"):
        try:
            out[k] = _grab(st, k)
        except Exception:                                    # pragma: no cover - older AVL output
            pass
    out["with_bodies"], out["notes"] = with_bodies, notes
    out["rotated_bodies_omitted"] = list(rotated)
    if with_bodies and rotated:
        out["bodies_representation"] = "unassessed"
        out["bodies_unassessed_reason"] = (
            "AVL BODY cannot represent non-axis-aligned attitude (avl_doc.txt slender bodies along x); "
            f"omitted rotated bodies {rotated} rather than a silent axis-aligned stand-in")
    else:
        out["bodies_representation"] = "axis_aligned" if with_bodies else "none"
    if not keep_dir:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def neutral_point(asm: Assembly, mach: float = 0.0, x_ref: float | None = None, run_avl: bool = True,
                  source: str = "avl_torenbeek") -> dict:
    """x_np from AVL with bodies (slender-body source+doublet lines), AVL without bodies, and AVL without bodies
    + Torenbeek 1982 App. E body shift.

    ``source`` selects the x_np used for the static margin: ``"avl_torenbeek"`` (default), ``"avl_bodies"`` or
    ``"most_forward"`` (the more forward of the two). Why the default: the AVL manual (avl_doc.txt, "slender
    bodies") warns that the body model has limited validation, and on the C172 adapter it moves x_np forward
    by 17.7 % MAC, about twice Munk's 2·Vol/(S·c) bound and four times the handbook shift (Torenbeek App. E,
    Raymer Eq. 16.25: about 4-6 % MAC), which would leave the certified C172 almost neutral at its aft limit.
    The AVL-with-bodies value is always reported, with a note when the two differ by more than 5 % MAC.

    Rotated bodies are omitted from AVL BODY **and** from the Torenbeek App. E sum (that formula is for a
    fuselage along x). Their contribution is ``bodies_avl_status='unassessed'`` — never an axis-aligned fake.
    """
    from ..stability import fuselage_ac_shift
    w, gw = main_wing(asm)
    x_ref = gw["x_ac"] if x_ref is None else x_ref
    out = {"mac": gw["mac"], "x_mac_le": gw["x_mac_le"], "S": gw["S"], "b": gw["b"], "x_ref": x_ref}
    if not run_avl or shutil.which("avl") is None:
        out["note"] = "AVL indisponível: ponto neutro não calculado"
        return out
    bare = run_assembly_avl(asm, mach=mach, x_ref=x_ref, with_bodies=False)
    full = run_assembly_avl(asm, mach=mach, x_ref=x_ref, with_bodies=True)
    _, bodies, _, _, _ = _parts(asm)
    dx = 0.0
    shifts = {}
    rotated = []
    for b in bodies:
        if _body_is_rotated(b):
            rotated.append(b.name)
            continue  # Torenbeek App. E is for fuselage along x — do not invent a shift
        l_fn = gw["x_root_le"] - (b.origin[0] + b.stations[0]["x"])
        if l_fn <= 0:
            continue
        bf = max(s["w"] for s in b.stations)
        hf = max(s["h"] for s in b.stations)
        d = fuselage_ac_shift(bf, hf, l_fn, gw["S"], gw["mac"], bare["CLa"]) * gw["mac"] * (2 if b.mirror else 1)
        shifts[b.name] = d
        dx += d
    cands = {"avl_bodies": full["Xnp"], "avl_torenbeek": bare["Xnp"] + dx}
    if source == "most_forward":
        pick = min(cands, key=cands.get)
    elif source in cands:
        pick = source
    else:
        raise ValueError(f"np source {source!r}: use avl_bodies, avl_torenbeek or most_forward")
    x_np = cands[pick]
    gap = abs(cands["avl_bodies"] - cands["avl_torenbeek"]) / gw["mac"]
    if gap > 0.05:
        out["warning"] = (f"x_np AVL com corpos e AVL sem corpos + Torenbeek diferem {gap:.1%} da MAC; o modelo de "
                          "corpos do AVL tem validação limitada (avl_doc.txt). Confirmar com VSPAERO/CFD ou ensaio.")
    out.update({"avl": full, "avl_no_bodies": bare, "x_np": x_np, "np_source": pick, "np_rule": source,
                "x_np_avl_bodies": full["Xnp"], "x_np_no_bodies": bare["Xnp"],
                "x_np_torenbeek": bare["Xnp"] + dx, "torenbeek_shifts_m": shifts,
                "xbar_np": (x_np - gw["x_mac_le"]) / gw["mac"],
                "rotated_bodies_omitted": list(rotated) or list(full.get("rotated_bodies_omitted") or []),
                "method": "AVL 3.x (Drela & Youngren) com BODY (slender body); AVL sem corpos + Torenbeek 1982 "
                          "App. E"})
    rot = out["rotated_bodies_omitted"]
    if rot:
        out["bodies_avl_status"] = "unassessed"
        out["bodies_avl_note"] = (
            f"corpos rodados {rot} omitidos do BODY AVL e do Torenbeek App. E — contribuição unassessed "
            f"(AVL/Torenbeek assumem corpo ao longo de x; sem stand-in alinhado)")
        if pick == "avl_bodies":
            # Selecting avl_bodies while bodies are incomplete must not silently pass as a full answer.
            out["x_np_status"] = "unassessed"
            out["x_np_unassessed_reason"] = out["bodies_avl_note"]
    else:
        out["bodies_avl_status"] = "assessed"
        out["x_np_status"] = "assessed"
    return out


def _rotation_vertices(asm: Assembly):
    P = []
    for c in asm.components:
        if re.search(r"gear|trem|wheel|roda", (c.role or "").lower()) or c.role == "item":
            continue
        V, _ = c.mesh(1)
        P.append(V)
    return np.concatenate(P)


def gear_layout(asm: Assembly, cg_fwd: list, cg_aft: list, opts: dict | None = None) -> dict:
    """Landing-gear layout and ground clearances from the assembly (Raymer Ch. 11; 14 CFR 23.925).

    ``type`` shortcuts: ``tricycle`` (default), ``taildragger``/``conventional``/``tailwheel``, ``ski``.
    Unknown type → unassessed (never a silent tricycle substitute). Drawn legs / retract kinematics are
    opt-in via :mod:`.gear_devices` after placement.

    Tricycle ``ground_attitude_deg`` θ_g (opt-in, default 0 = level stance, unchanged): nose-strut extension that
    parks the aeroplane nose-up (a flying wing whose zero-lift attitude is above the ground line). The main
    contacts stay at ``ground_z``; the nose contact is ``nose_strut_extension_m`` = (x_main − x_nose)·tan θ_g lower.
    Tip-back (Raymer Ch. 11: angle off the vertical from the main wheel to the CG ≥ 15°), nose load and overturn
    are measured in that static attitude; the take-off rotation clearance (10–15°) is measured from it; the
    propeller clearance (14 CFR 23.925(a)(1): level take-off *or* taxiing attitude, whichever is most critical)
    is checked in both attitudes.
    """
    from ..landing_gear import (angle_from_vertical_deg, min_half_track, overturn_angle_deg, place_tricycle,
                                static_fraction_front)
    from .gear_devices import SKI_TYPES, TAILDRAGGER_TYPES, layout_ski, layout_taildragger
    o = {"type": "tricycle", "tipback_deg": 15.0, "nose_fraction": [0.08, 0.15], "overturn_max_deg": 63.0,
         "rotation_min_deg": 10.0, "prop_clearance_m": None, "ground_z": None, "x_main": None, "x_nose": None,
         "half_track": None, "nose_leg_clearance_m": 0.0, "ground_attitude_deg": 0.0, "wheelbase": "longest", **(opts or {})}
    if o["type"] in ("none", None):
        return {"type": "none", "checks": []}
    if o["type"] in TAILDRAGGER_TYPES:
        return layout_taildragger(asm, cg_fwd, cg_aft, o)
    if o["type"] in SKI_TYPES:
        return layout_ski(asm, cg_fwd, cg_aft, o)
    if o["type"] != "tricycle":
        return {"type": o["type"], "status": "unassessed", "checks": [
            ("asm:gear_position", None,
             f"gear.type '{o['type']}' sem método citado — unassessed (não substituído por triciclo; "
             "usar tricycle | taildragger | ski | none, ou desenhar o trem à mão)")],
                "note": f"unassessed type {o['type']!r}"}
    prop_c = o["prop_clearance_m"] if o["prop_clearance_m"] is not None else 7 * IN   # 23.925(a)(1)
    P = _rotation_vertices(asm)
    discs = [c for c in asm.components if isinstance(c, Disc)]
    bodies = [c for c in asm.components if isinstance(c, Body) and c.role != "item"]
    x_nose_min = min(float(c.bbox()[0][0]) for c in bodies) if bodies else float(P[:, 0].min())
    zf, zr = float(cg_fwd[2]), float(cg_aft[2])
    xf, xr = float(cg_fwd[0]), float(cg_aft[0])
    thg = math.radians(float(o.get("ground_attitude_deg") or 0.0))
    th = math.radians(o["rotation_min_deg"]) + thg
    z_min = float(P[:, 2].min())
    disc_low = [float(d.bbox()[0][2]) for d in discs]
    disc_pts = np.concatenate([d.mesh(1)[0] for d in discs]) if (discs and thg) else None

    def gframe(x, xm, zg, h):
        """Body station → horizontal station in the static (nose-up θ_g) attitude, about the main contact."""
        return xm + (x - xm) * math.cos(thg) + h * math.sin(thg)

    def layout(zg):
        h = max(zf, zr) - zg
        if thg:   # stance: tip-back and nose band in the static attitude (ground frame), stations back to body
            hf, hr = zf - zg, zr - zg   # per-CG heights for the static-attitude stations
            if o["x_main"] is not None:
                xm = float(o["x_main"])
            else:   # angle off the vertical in the static attitude = atan(d/h) − θ_g ≥ tip-back
                xm = xr + h * math.tan(math.radians(o["tipback_deg"]) + thg)
            xfg, xrg = gframe(xf, xm, zg, hf), gframe(xr, xm, zg, hr)
            xnmin_g = xm + (x_nose_min - xm) / math.cos(thg)
            if o["x_nose"] is not None:
                xn = float(o["x_nose"])
            else:
                hg = h * math.cos(thg) + (xm - xr) * math.sin(thg)
                pl = place_tricycle(min(xfg, xrg), max(xfg, xrg), hg, 1e-6, *o["nose_fraction"], xnmin_g, None, xm,
                                    prefer=o["wheelbase"])
                xn = (xm + (pl[0] - xm) * math.cos(thg)) if pl else None
            return h, xn, xm
        if o["x_main"] is not None:
            xm = float(o["x_main"])
            xn = float(o["x_nose"]) if o["x_nose"] is not None else None
            if xn is None:
                pl = place_tricycle(xf, xr, h, o["tipback_deg"], *o["nose_fraction"], x_nose_min, None, xm,
                                    prefer=o["wheelbase"])
                xn = pl[0] if pl else None
        else:
            pl = place_tricycle(xf, xr, h, o["tipback_deg"], *o["nose_fraction"], x_nose_min, prefer=o["wheelbase"])
            xm = xr + h * math.tan(math.radians(o["tipback_deg"]))
            xn = pl[0] if pl else None
        return h, xn, xm

    def zg_required(xm):
        aft = P[P[:, 0] > xm + 1e-9]
        req = [z_min] + [z - prop_c for z in disc_low]
        if disc_pts is not None:   # 23.925(a)(1) also in the nose-up static (taxi) attitude
            req.append(float((disc_pts[:, 2] - ((disc_pts[:, 0] - xm) * math.sin(thg) + prop_c) / math.cos(thg)).min()))
        if len(aft):
            req.append(float((aft[:, 2] - (aft[:, 0] - xm) * math.tan(th)).min()))
        return min(req)

    given = o["ground_z"] is not None
    if given:
        zg = float(o["ground_z"])
        it = 0
    else:
        zg = z_min
        for it in range(1, 41):
            _, _, xm = layout(zg)
            zn = zg_required(xm)
            if abs(zn - zg) < 1e-4:
                zg = zn
                break
            zg = zn
    h, xn, xm = layout(zg)
    aft = P[P[:, 0] > xm + 1e-9]
    rot = float(np.degrees(np.arctan2(aft[:, 2] - zg, aft[:, 0] - xm)).min()) if len(aft) else 90.0
    who = None
    if len(aft):
        k = int(np.argmin(np.arctan2(aft[:, 2] - zg, aft[:, 0] - xm)))
        who = [round(float(v), 3) for v in aft[k]]
    clear_prop = min([z - zg for z in disc_low], default=math.inf)
    if disc_pts is not None:
        clear_prop = min(clear_prop, float(((disc_pts[:, 2] - zg) * math.cos(thg)
                                            - (disc_pts[:, 0] - xm) * math.sin(thg)).min()))
    belly = z_min - zg
    checks = []
    tipback = angle_from_vertical_deg(xm - xr, h) - math.degrees(thg)
    checks.append(("asm:gear_tipback", tipback + 1e-6 >= o["tipback_deg"],
                   f"tip-back {tipback:.1f}° (mín. {o['tipback_deg']:.0f}°, Raymer Ch. 11), x_main {xm:.3f} m, "
                   f"h_cg {h:.3f} m"))
    st = f" a partir da atitude estática {math.degrees(thg):.1f}°" if thg else ""
    checks.append(("asm:gear_rotation", rot - math.degrees(thg) + 1e-6 >= o["rotation_min_deg"],
                   f"rotação até tocar {rot - math.degrees(thg):.1f}°{st} (mín. {o['rotation_min_deg']:.0f}°, "
                   f"Raymer Ch. 11 10–15°); primeiro ponto a tocar {who}"))
    if discs:
        checks.append(("asm:gear_prop_clearance", clear_prop + 1e-6 >= prop_c,
                       f"folga da hélice ao solo {clear_prop:.3f} m (mín. {prop_c:.3f} m, 14 CFR 23.925(a)(1))"))
    checks.append(("asm:gear_belly", belly >= -1e-6, f"folga do ventre ao solo {belly:.3f} m"))
    res = {"type": "tricycle", "ground_z": zg, "ground_z_given": given, "iterations": it, "h_cg": h,
           "x_main": xm, "x_nose": xn, "rotation_deg": rot, "rotation_first_contact": who,
           "prop_clearance_m": clear_prop, "belly_clearance_m": belly, "tipback_deg": tipback,
           "main_leg_from_lowest_point_m": z_min - zg}
    if thg:
        res.update({"ground_attitude_deg": math.degrees(thg), "rotation_from_stance_deg": rot - math.degrees(thg),
                    "h_cg_static": h * math.cos(thg) + (xm - xr) * math.sin(thg),
                    "stance_source": "PRESSUPOSTO (opção de projeto): extensão da perna do nariz; tip-back, carga "
                                     "no nariz e capotamento na atitude estática (Raymer Ch. 11); hélice nas duas "
                                     "atitudes (14 CFR 23.925(a)(1))"})
    if xn is None:
        checks.append(("asm:gear_position", False,
                       f"sem entre-eixos na banda {o['nose_fraction'][0]:.0%}–{o['nose_fraction'][1]:.0%} com o "
                       f"nariz atrás de x = {x_nose_min:.3f} m"))
    else:
        if thg:   # horizontal stations in the static attitude
            xng = xm + (xn - xm) / math.cos(thg)
            ff = static_fraction_front(xng, xm, gframe(xf, xm, zg, zf - zg))
            fa = static_fraction_front(xng, xm, gframe(xr, xm, zg, zr - zg))
            res["nose_strut_extension_m"] = (xm - xn) * math.tan(thg)
        else:
            ff, fa = static_fraction_front(xn, xm, xf), static_fraction_front(xn, xm, xr)
        lo, hi = o["nose_fraction"]
        checks.append(("asm:gear_position", lo - 1e-3 <= min(ff, fa) and max(ff, fa) <= hi + 1e-3,
                       f"carga no nariz {fa:.1%}–{ff:.1%} (banda {lo:.0%}–{hi:.0%}, Raymer Ch. 11), "
                       f"entre-eixos {xm - xn:.3f} m"))
        if thg:
            hs = h * math.cos(thg) + (xm - xf) * math.sin(thg)
            xn_o, xf_o = xm + (xn - xm) / math.cos(thg), gframe(xf, xm, zg, zf - zg)
        else:
            hs, xn_o, xf_o = h, xn, xf
        t_req = min_half_track(xn_o, xm, xf_o, hs, o["overturn_max_deg"])
        res.update({"nose_fraction": [fa, ff], "wheelbase": xm - xn, "half_track_min": t_req})
        if o["half_track"] is not None:
            res["half_track"] = float(o["half_track"])
            ov = overturn_angle_deg(xn_o, xm, float(o["half_track"]), xf_o, hs)
            res["overturn_deg"] = ov
            checks.append(("asm:gear_overturn", ov <= o["overturn_max_deg"] + 1e-6,
                           f"capotamento {ov:.1f}° (máx. {o['overturn_max_deg']:.0f}°), meia-via {o['half_track']} m"))
        # nose leg (vertical line x = xn, y = 0, from the ground to the body) must stay out of every disc
        zs = np.linspace(zg, max(zf, zr), 60)
        line = np.stack([np.full_like(zs, xn), np.zeros_like(zs), zs], axis=1)
        hit = [d.name for d in discs if float(d.contains(line).max()) > -float(o["nose_leg_clearance_m"])]
        checks.append(("asm:gear_nose_vs_prop", not hit,
                       "perna do nariz fora dos discos" if not hit else f"perna do nariz atravessa o disco {hit}"))
    res["checks"] = checks
    return res


# ------------------------------------------------------------------------------------------- loading
def _cg(rows):
    M = sum(r[1] for r in rows)
    return M, (sum(r[1] * np.asarray(r[2], float) for r in rows) / M).tolist() if M > 0 else [math.nan] * 3


def loading(parts: list[PartMass], extra: list[dict], payload: list[dict], fuel: list[dict]) -> dict:
    """CG at empty / payload / fuel / full. Each list entry {name, mass_kg, r}."""
    base = [(p.name, p.mass_kg, p.cg) for p in parts] + [(e["name"], e["mass_kg"], e["r"]) for e in extra]
    pl = [(e["name"], e["mass_kg"], e["r"]) for e in payload]
    fu = [(e["name"], e["mass_kg"], e["r"]) for e in fuel]
    cases, by_case = {}, {}
    for nm, rows in (("vazio", base), ("carga", base + pl), ("combustível", base + fu), ("cheio", base + pl + fu)):
        M, cg = _cg(rows)
        cases[nm] = {"mass_kg": M, "cg": cg}
        by_case[nm] = rows
    xs = [c["cg"][0] for c in cases.values()]
    i_f, i_a = int(np.argmin(xs)), int(np.argmax(xs))
    names = list(cases)
    return {"cases": cases, "fwd": cases[names[i_f]]["cg"], "aft": cases[names[i_a]]["cg"],
            "fwd_case": names[i_f], "aft_case": names[i_a], "rows": by_case}


# ------------------------------------------------------------------------------------------- driver
@dataclass
class AssemblySizing:
    structure: list
    structure_mass_kg: float
    drag: dict
    np: dict
    loading: dict
    static_margin: dict
    gear: dict
    checks: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    integration: dict | None = None
    assumptions: list = field(default_factory=lambda: list(ASSUMPTIONS))

    def summary(self) -> dict:
        return {"structure": [p.__dict__ for p in self.structure], "structure_mass_kg": self.structure_mass_kg,
                "CD0": self.drag.get("CD0"), "drag": self.drag, "neutral_point": self.np,
                "loading": {k: v for k, v in self.loading.items() if k != "rows"},
                "static_margin": self.static_margin, "gear": {k: v for k, v in self.gear.items() if k != "checks"},
                "checks": [{"key": k, "ok": ok, "message": m} for k, ok, m in self.checks], "notes": self.notes,
                "integration_ok": None if self.integration is None else self.integration.get("ok"),
                "assumptions": self.assumptions}


def analyse(spec: dict, flight: dict, opts: dict | None = None) -> AssemblySizing:
    """Evaluate one assembled configuration.

    ``spec``: {assembly: {components}, items?, constraints?, masses?: [{name, mass_kg, position | component,
    group: equipment | propulsion | payload | fuel}], gear?: {...}, drag?: {Q, laminar, ...}, material?}.
    ``flight``: {W0_kg, V_m_s, altitude_m, Nz | n_limit | category, Wf_kg, payload_kg, mach?,
    other_masses?: [{name, mass_kg, group, key}] (non-structural groups of a sizing run)}."""
    from acdt.core.atmosphere import isa
    from ..weights_detailed import limit_load_factor
    from .integration import check as integration_check
    o = {"static_margin_min": 0.05, "run_avl": True, "np_source": "avl_torenbeek", **(opts or {}), **(spec.get("options") or {})}
    asm = Assembly.from_dict(spec["assembly"])
    at = isa(float(flight.get("altitude_m", 0.0)))
    V = float(flight["V_m_s"])
    W0 = float(flight["W0_kg"])
    Nz = flight.get("Nz") or 1.5 * float(flight.get("n_limit") or limit_load_factor(W0, flight.get("category",
                                                                                                    "normal")))
    q = 0.5 * at.rho * V * V
    notes = []
    swet = exposed_wetted_areas(asm)
    parts = structure_weights(asm, W0, Nz, q, spec.get("material", "metal"), swet=swet)
    w, gw = main_wing(asm)
    mach = flight.get("mach", V / at.a)
    try:
        npd = neutral_point(asm, mach=mach, run_avl=o["run_avl"], source=o["np_source"])
    except Exception as ex:                                  # pragma: no cover - AVL runtime failure
        npd = {"mac": gw["mac"], "x_mac_le": gw["x_mac_le"], "note": f"AVL falhou: {ex}"}
        notes.append(npd["note"])
    if npd.get("warning"):
        notes.append(npd["warning"])
    # masses -------------------------------------------------------------------------------------------
    fus = max((c for c in asm.components if isinstance(c, Body) and c.role != "item"),
              key=lambda c: c.volume(), default=None)
    r_default = list(fus.centroid()) if fus is not None else list(w.centroid())
    discs = [c for c in asm.components if isinstance(c, Disc)]
    r_prop = list(np.mean([d.origin for d in discs], axis=0)) if discs else r_default
    integ = None
    groups = {"equipment": [], "payload": [], "fuel": []}
    listed = set()
    if spec.get("items"):
        integ = integration_check(asm, spec["items"], spec.get("constraints"))
        for it in spec["items"]:
            nm = it["name"]
            if nm in integ["positions"] and it.get("mass_kg", 0) > 0:
                g = it.get("group") or "equipment"
                groups.setdefault(g, []).append({"name": nm, "mass_kg": float(it["mass_kg"]),
                                                 "r": integ["positions"][nm]})
                listed.add(nm)
    for m in spec.get("masses") or []:
        r = m.get("position") or (list(asm.get(m["component"]).centroid()) if m.get("component") else r_default)
        groups.setdefault(m.get("group", "equipment"), []).append({"name": m["name"], "mass_kg": float(m["mass_kg"]),
                                                                   "r": list(r)})
        listed.add(m["name"])
        if m.get("key"):
            listed.add(m["key"])
    skip = set(spec.get("replaces") or [])
    for m in flight.get("other_masses") or []:
        if m["name"] in listed or m.get("key") in listed or m.get("key") in skip:
            continue
        g = m.get("group", "equipment")
        r = r_prop if g == "propulsion" else r_default
        groups.setdefault(g, []).append({"name": m["name"], "mass_kg": float(m["mass_kg"]), "r": list(r)})
    r_load, load_note = r_default, "no centróide do corpo principal (PRESSUPOSTO)"
    if o.get("useful_load_at") == "empty_cg":
        # opt-in (tailless trim, 10 nov 2026): unpositioned payload / fuel on the CG of the fixed masses, so
        # adding them does not move the CG (Raymer 2018 Sec. 15.1, as the fixed-type 'balance' station;
        # NACA TR-796 (Donlan 1944): CG range is more critical on tailless aeroplanes). Volume packaging of
        # the lumped load there is NOT checked (unassessed) — use positioned items for that.
        rows0 = [(p.name, p.mass_kg, p.cg) for p in parts] + [
            (e["name"], e["mass_kg"], e["r"]) for g, v in groups.items() if g not in ("payload", "fuel") for e in v]
        r_load = _cg(rows0)[1]
        load_note = ("no CG das massas fixas (useful_load_at: empty_cg; Raymer 2018 Sec. 15.1) — PRESSUPOSTO; "
                     "volume/packaging nesse ponto unassessed")
    pl_listed = sum(e["mass_kg"] for e in groups["payload"])
    if flight.get("payload_kg") and pl_listed < float(flight["payload_kg"]) - 1e-6:
        rest = float(flight["payload_kg"]) - pl_listed
        groups["payload"].append({"name": "carga não posicionada", "mass_kg": rest, "r": list(r_load)})
        notes.append(f"{rest:.2f} kg de carga sem item posicionado: {load_note}")
    fu_listed = sum(e["mass_kg"] for e in groups["fuel"])
    if flight.get("Wf_kg") and fu_listed < float(flight["Wf_kg"]) - 1e-6:
        rest = float(flight["Wf_kg"]) - fu_listed
        tanks = groups["fuel"]
        if tanks:
            # The mission fuel that the drawn tanks do not yet weigh is still fuel in those tanks,
            # not a lump at the body centroid (PRESSUPOSTO).
            mt = sum(e["mass_kg"] for e in tanks)
            r_fuel = (sum(e["mass_kg"] * np.asarray(e["r"], float) for e in tanks) / mt).tolist()
            note = (f"{rest:.2f} kg de combustível além da massa dos tanques desenhados: no CG desses tanques "
                    "(PRESSUPOSTO; Raymer — o combustível vai nos tanques)")
        elif o.get("useful_load_at") == "empty_cg":
            r_fuel = list(r_load)
            note = f"{rest:.2f} kg de combustível sem tanque posicionado: {load_note}"
        else:
            r_fuel = list(w.centroid()) if not fus else r_default
            note = (f"{rest:.2f} kg de combustível sem tanque posicionado (PRESSUPOSTO: centróide do corpo "
                    "principal)")
        groups["fuel"].append({"name": "combustível não posicionado", "mass_kg": rest, "r": r_fuel})
        notes.append(note)
    drag = cd0_buildup(asm, V, at.rho, at.mu, at.a, opts=spec.get("drag"), items=spec.get("items"),
                       positions=integ["positions"] if integ is not None else None)
    extra = [e for g, v in groups.items() if g not in ("payload", "fuel") for e in v]
    ld = loading(parts, extra, groups["payload"], groups["fuel"])
    # static margin -------------------------------------------------------------------------------------
    sm = {}
    checks = []
    if "x_np" in npd:
        for nm, c in ld["cases"].items():
            sm[nm] = (npd["x_np"] - c["cg"][0]) / gw["mac"]
        smin = min(sm.values())
        sm_msg = (f"margem estática mínima {smin:.1%} ({min(sm, key=sm.get)}) contra {o['static_margin_min']:.0%};"
                  f" x_np {npd['x_np']:.3f} m ({npd['np_source']}, regra {npd['np_rule']}); AVL com corpos "
                  f"{npd['x_np_avl_bodies']:.3f} m, sem corpos {npd['x_np_no_bodies']:.3f} m, sem corpos + "
                  f"Torenbeek {npd['x_np_torenbeek']:.3f} m")
        if npd.get("x_np_status") == "unassessed":
            checks.append(("asm:static_margin", None,
                           f"unassessed: {npd.get('x_np_unassessed_reason') or npd.get('bodies_avl_note')}; "
                           + sm_msg))
        else:
            checks.append(("asm:static_margin", smin + 1e-9 >= o["static_margin_min"], sm_msg))
        if npd.get("bodies_avl_status") == "unassessed":
            checks.append(("asm:avl_bodies", None, npd.get("bodies_avl_note") or
                           "corpos rodados omitidos do BODY AVL / Torenbeek — unassessed"))
        elif npd.get("rotated_bodies_omitted"):
            checks.append(("asm:avl_bodies", None,
                           f"corpos rodados {npd['rotated_bodies_omitted']} omitidos — unassessed"))
    gear = gear_layout(asm, ld["fwd"], ld["aft"], spec.get("gear"))
    from .gear_devices import apply_gear_devices
    gopts = spec.get("gear") or {}
    if (gopts.get("draw_legs") or gopts.get("retract") is not None
            or gopts.get("check_retract") or gopts.get("tip_skids")):
        gear["W_N"] = float(W0) * 9.80665
        gear["mass_kg"] = float(W0)
        spec_after, devices = apply_gear_devices(spec, gear)
        gear["devices"] = devices
        if devices.get("drawn_legs"):
            # Rebuild assembly with drawn legs so subsequent CAD/export of this sizing sees them.
            asm = Assembly.from_dict(spec_after["assembly"])
            gear["assembly_with_legs"] = spec_after["assembly"]
        # retract / tip_skids may have appended checks onto gear["checks"].
        # Mass is reported on gear['tip_skids'] / asm:gear_tip_skids and is not folded into
        # loading() here: that would shift the CG after SM was already computed (desync with
        # the balance loop). 0.16 kg on this airframe is ~0.1 % of W0 — next size can inventory it.
    _assess_gear_followup(asm, gear, float(W0) * 9.80665, spec, groups)
    checks += gear.get("checks", [])
    if integ is not None:
        checks.append(("asm:integration", integ["ok"], f"{integ['n_violations']} violações de integração em "
                                                       f"{integ['n_constraints']} restrições"))
    sm_struct = sum(p.mass_kg for p in parts)
    m_full = float(ld["cases"]["cheio"]["mass_kg"])
    if abs(m_full / W0 - 1.0) > 0.05:
        notes.append(f"massa montada (cheio) {m_full:.1f} kg contra W0 {W0:.1f} kg ({m_full / W0 - 1:+.1%}): as massas "
                     "por peça não fecham com o W0 dado; o CG e a margem são os da montagem")
    return AssemblySizing(parts, sm_struct, drag, npd, ld, sm, gear, checks, notes, integ)


# ------------------------------------------------------------------------------------------- adapter

def _assess_gear_followup(asm, gear: dict, W_N: float, spec: dict, groups: dict | None = None) -> None:
    """Drag scaling, 23.485 leg structure and Sadraey 9.5.3.2 max-track (after gear_layout)."""
    if not gear or gear.get("type") == "none" or gear.get("x_main") is None:
        return
    gopts = spec.get("gear") or {}
    if not (gopts.get("assess_structure") or gopts.get("scale_drag") or gopts.get("drag_ref_main_m") is not None):
        return
    from .gear_devices import (
        conservative_wing_EI_at_root, max_track_sadraey_9532, scale_fixed_gear_drag_area,
        size_gear_side_load_structure)
    # lengths used in Raymer 15.50/15.51 (mission weights.components, copied onto the spec when present)
    length_opts = {}
    for src in (spec.get("weights") or {}, (spec.get("flight") or {}).get("weights") or {},
                gopts, spec):
        if isinstance(src, dict):
            if src.get("main_gear_length_m") is not None:
                length_opts["main_gear_length_m"] = src["main_gear_length_m"]
            if src.get("nose_gear_length_m") is not None:
                length_opts["nose_gear_length_m"] = src["nose_gear_length_m"]
    # also look under groups / components-style items
    comps = ((spec.get("assumptions") or {}).get("weights") or {}).get("components") or {}
    if comps.get("main_gear_length_m") is not None:
        length_opts["main_gear_length_m"] = comps["main_gear_length_m"]
    if comps.get("nose_gear_length_m") is not None:
        length_opts["nose_gear_length_m"] = comps["nose_gear_length_m"]
    area = None
    extra = (spec.get("drag") or {}).get("extra_drag_areas_m2") or {}
    if "fixed_gear" in extra:
        area = extra["fixed_gear"]
    # mission aero often owns the lumped area; the assembly loop copies it onto drag
    if area is None:
        for key in ("extra_drag_areas_m2",):
            blk = spec.get(key) or (spec.get("aero") or {}).get(key) or {}
            if isinstance(blk, dict) and "fixed_gear" in blk:
                area = blk["fixed_gear"]
                break
    if area is not None:
        ref_m = gopts.get("drag_ref_main_m")
        ref_n = gopts.get("drag_ref_nose_m")
        kw = {"length_opts": length_opts or None}
        if ref_m is not None:
            kw["ref_main_m"] = float(ref_m)
        if ref_n is not None:
            kw["ref_nose_m"] = float(ref_n)
        sc = scale_fixed_gear_drag_area(float(area), gear, **kw)
        gear["drag_scaled"] = sc
        if sc.get("status") == "assessed":
            gear.setdefault("checks", []).append(
                ("asm:gear_drag_area", True,
                 f"área equivalente do trem {sc['area_given_m2']:.4f} m² × {sc['factor']:.3f} "
                 f"= {sc['area_scaled_m2']:.4f} m² (L {sc['L_main_m']:.2f}/{sc['L_nose_m']:.2f} m vs "
                 f"ref {sc['L_ref_m']:.2f} m Σ; {sc['source']}; "
                 + ("aplicada ao polar — aero:gear_drag)" if gopts.get("apply_scaled_drag")
                    else "não aplicada ao polar: gear.apply_scaled_drag ausente)")))
        else:
            gear.setdefault("checks", []).append(
                ("asm:gear_drag_area", None, f"área do trem unassessed: {sc.get('issue')}"))
    # opt-in (24 nov 2026): legs designed above the 23.485 minimum (factor on both side loads); the 6-DOF touchdown
    # check then compares with the same design limit (gear['side_load_factor'] → flightsim). Absent → 1 (23.485).
    k_side = float(gopts.get("side_load_factor") or 1.0)
    side = size_gear_side_load_structure(
        gear, W_N, diameter_m=gopts.get("leg_diameter_m"), length_opts=length_opts or None, side_factor=k_side)
    gear["side_load_structure"] = side
    if k_side != 1.0:
        gear["side_load_factor"] = k_side
    if side.get("status") == "assessed":
        gear.setdefault("checks", []).append(
            ("asm:gear_side_load_structure", bool(side.get("ok")),
             f"pernas às cargas 23.485{f' × {k_side:g}' if k_side != 1.0 else ''}: RF flexão {side['RF_bending']:.2f}, "
             f"corte {side['RF_shear']:.2f}, "
             f"encurvadura {side['RF_buckling']:.1f}, σ {side['sigma_MPa']:.0f} MPa, "
             f"massa 2× principais {side['mass_two_mains_kg']:.2f} kg ({side['source']})"))
    else:
        gear.setdefault("checks", []).append(
            ("asm:gear_side_load_structure", None, f"estrutura lateral unassessed: {side.get('issue')}"))
    ei = conservative_wing_EI_at_root(asm)
    if ei:
        gear["wing_EI_conservative"] = ei
    tr = max_track_sadraey_9532(gear, W_N, None if not ei else ei["EI_Nm2"],
                                delta_allow_m=gopts.get("delta_allow_m"))
    if ei:
        tr["EI_note"] = ei["note"]
    gear["max_track_sadraey_9532"] = tr
    if tr.get("status") == "assessed":
        msg = (f"Sadraey 9.5.3.2: T {tr['track_m']:.3f} m, δ a meio-vão {tr['delta_m']*1e3:.2f} mm, "
               f"ΔΓ {tr['delta_dihedral_deg']:.3f}° (EI conservador {tr['EI_Nm2']:.0f} N·m²")
        if ei:
            msg += f"; {ei['note']}"
        msg += f"). {tr.get('note') or tr['source']}"
        gear.setdefault("checks", []).append(("asm:gear_max_track_9532", tr.get("ok"), msg))
    else:
        gear.setdefault("checks", []).append(
            ("asm:gear_max_track_9532", None,
             f"Sadraey 9.5.3.2 unassessed: {tr.get('issue')} ({tr.get('source') or ''})".strip()))


def assembly_from_design(res) -> dict:
    """Legacy fixed type (Configuration: wing + fuselage + htail + vtail) → generic assembly spec, so a fixed-type
    design runs through the same component path. Wing apex from the stability stage (or 35 % L, PRESSUPOSTO)."""
    cfg = res.config
    w, f, ht, vt = cfg.wing, cfg.fuselage, cfg.htail, cfg.vtail
    st = getattr(res, "stability", None)
    x_apex = float(st.x_wing_apex) if st is not None and getattr(st, "x_wing_apex", None) is not None \
        else 0.35 * f.length
    x_ac_w = x_apex + w.y_mac * math.tan(w.sweep_at(0.0)) + 0.25 * w.mac

    def panel(tw, name, role, x_ac, z, dihedral, mirror):
        x_le_root = x_ac - 0.25 * tw.mac - tw.y_mac * math.tan(tw.sweep_at(0.0))
        span = tw.span / 2 if mirror else tw.span
        return {"type": "surface", "name": name, "role": role, "origin": [x_le_root, 0.0, z], "mirror": mirror,
                "panel": {"root_chord": tw.c_root, "tip_chord": tw.c_tip, "span": span,
                          "sweep_le_deg": math.degrees(tw.sweep_at(0.0)), "dihedral_deg": dihedral,
                          "tc_root": tw.tc_root if hasattr(tw, "tc_root") else w.tc_mean,
                          "tc_tip": tw.tc_tip if hasattr(tw, "tc_tip") else w.tc_mean}}
    htw, vtw = ht.as_wing(), vt.as_wing()
    vt_mirror_span = vtw.span / 2          # TrapezoidalWing span of the fin "as wing": half is the fin height
    comps = [
        {"type": "body", "name": "fuselage", "role": "fuselage",
         "pod": {"length": f.length, "width": f.max_diameter, "nose_frac": 0.2, "tail_frac": 0.45,
                 "tail_scale": 0.1}},
        panel(w, "wing", "wing", x_ac_w, 0.0, math.degrees(w.dihedral), True),
        panel(htw, "htail", "horizontal tail", x_ac_w + ht.arm, 0.0, 0.0, True),
    ]
    v = panel(vtw, "vtail", "fin", x_ac_w + vt.arm, 0.0, 90.0, False)
    v["panel"]["span"] = vt_mirror_span
    comps.append(v)
    # non-structural masses at the stability-stage stations (the legacy W&B positions), structure recomputed
    masses = []
    for s_ in (getattr(st, "stations", None) or []):
        key = s_["item"]
        if key in ("wing", "htail", "vtail", "fuselage") or float(s_["mass_kg"]) <= 0:
            continue
        grp = {"payload": "payload", "fuel": "fuel", "crew": "payload"}.get(key, "equipment")
        masses.append({"name": key, "key": key, "group": grp, "mass_kg": float(s_["mass_kg"]),
                       "position": [float(s_["x_m"]), 0.0, 0.0]})
    return {"assembly": {"components": comps}, "masses": masses, "gear": {"type": "none"},
            "_note": "adaptador do tipo fixo: fuselagem pod 20 % nariz / 45 % cone (PRESSUPOSTO de forma); "
                     "massas não estruturais nas estações da estabilidade, z = 0 (PRESSUPOSTO); trem fora "
                     "(o tipo fixo já tem gear:*)"}


# ------------------------------------------------------------------------------------------- pipeline hook
def flight_from_design(res) -> dict:
    """Flight condition and non-structural masses of a sizing run (``acdt size``) for :func:`analyse`."""
    wb = getattr(res, "weights", None)
    other, replaces = [], []
    if wb is not None:
        for it in wb.items:
            if it.group == "structure" and "gear" not in it.key:
                replaces.append(it.key)          # recomputed per part from the assembly
            else:
                other.append({"name": it.name, "key": it.key, "group": it.group, "mass_kg": float(it.mass)})
    payload = float(res.spec.requirements.value("payload_mass", 0.0) or 0.0) if hasattr(
        res.spec, "requirements") else 0.0
    return {"W0_kg": float(res.sizing.W0), "V_m_s": float(res.cruise_speed),
            "altitude_m": float(res.cruise_altitude), "Nz": float(wb.Nz) if wb is not None else None,
            "Wf_kg": float(getattr(res.sizing, "Wf", 0.0) or 0.0), "payload_kg": payload,
            "other_masses": other, "replaces": replaces}


def assembly_stage(res, spec: dict) -> tuple[AssemblySizing, dict]:
    """Run :func:`analyse` on a sized design and compare with the fixed-type path (S, structure mass, CD0).

    The assembly is evaluated as drawn (it is NOT rescaled to the sized S); ``asm:wing_area`` flags a drawing
    that departs from the sized wing by more than ``options.area_tolerance`` (PRESSUPOSTO: 5 %)."""
    flight = flight_from_design(res)
    spec = dict(spec)
    spec["replaces"] = list(spec.get("replaces") or []) + flight.pop("replaces")
    out = analyse(spec, flight)
    tol = float((spec.get("options") or {}).get("area_tolerance", 0.05))
    asm = Assembly.from_dict(spec["assembly"])
    S_asm = main_wing(asm)[1]["S"]
    cmp = {"S_assembly_m2": S_asm, "S_sized_m2": float(res.S),
           "structure_assembly_kg": out.structure_mass_kg,
           "structure_sized_kg": sum(float(it.mass) for it in res.weights.items
                                     if it.group == "structure" and "gear" not in it.key)
           if getattr(res, "weights", None) is not None else None,
           "CD0_assembly": out.drag["CD0"], "CD0_sized": float(getattr(res.polar, "CD0", float("nan")))}
    dS = abs(S_asm / float(res.S) - 1.0) if res.S else float("inf")
    out.checks.insert(0, ("asm:wing_area", dS <= tol, f"asa da montagem {S_asm:.3f} m² contra {float(res.S):.3f} m² "
                                                     f"dimensionados ({dS:.1%}, tolerância {tol:.0%}, PRESSUPOSTO)"))
    return out, cmp
