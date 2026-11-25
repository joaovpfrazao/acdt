"""Structural material library (Phase 6) — **isotropic** properties for the low-fidelity loop.

User decision (Phase 6): at the conceptual/preliminary (low-fidelity) stage every structural member is modelled as
an isotropic material. Composite construction is represented by an *equivalent isotropic* material whose E, G, ν
are the in-plane engineering constants of a laminate from Classical Lamination Theory (Jones, *Mechanics of
Composite Materials*, 2nd ed. 1999, Ch. 4; same CLT as :mod:`acdt.core.fem.laminate`), and whose allowables come
from design strain cut-offs (knock-downs for environment and impact damage). The orthotropic / laminate path of
:mod:`acdt.core.fem.laminate` is kept for the future high-fidelity stage but is not the default.

Sources (values are *typical/S-basis handbook values — verify against the current MMPDS / CMH-17 release before
any certification use*):

* Metals — MIL-HDBK-5J (2003, public domain; superseded by MMPDS): 2024-T3 sheet (Table 3.2.3.0(b)),
  7075-T6 sheet (Table 3.7.6.0(b)), AISI 4130 normalized sheet ≤ 0.188 in (Table 2.3.1.0(c1)), Ti-6Al-4V
  annealed sheet (Table 5.4.1.0(b)).
* Unidirectional lamina constants — Daniel & Ishai, *Engineering Mechanics of Composite Materials*, 2nd ed. 2006,
  Table A.4 (AS4/3501-6 carbon/epoxy, E-glass/epoxy).
* Design strain cut-offs for composites (BVID + hot/wet) — ``ASSUMPTION``: the 3000–4000 με band commonly used in
  preliminary design (CMH-17-3G Vol. 3 Ch. 12 "damage resistance, durability and damage tolerance"; Niu,
  *Composite Airframe Structures*, 1992, Ch. 4). Values here: ε_c = 3500 με, ε_t = 4000 με, γ = 7000 με,
  each with an extra environmental factor k_env = 0.8 (hot/wet).
* Core / wood (reference only) — PVC foam: DIAB Divinycell H80 datasheet (ρ 80 kg/m³, E_c 95 MPa, G 27 MPa,
  τ 1.15 MPa); balsa: USDA *Wood Handbook* FPL-GTR-190 (2010), Table 5-3b (SG 0.16, MOE 3.4 GPa, compression ∥
  14.9 MPa).

All quantities SI (Pa, kg/m³)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

import numpy as np

KSI = 6.894757e6
LB_IN3 = 27679.9


@dataclass
class Material:
    key: str
    name: str
    E: float            # Young's modulus (tension ≈ compression, isotropic)
    G: float
    nu: float
    rho: float
    Ftu: float          # ultimate tensile allowable
    Fty: float          # tensile yield (metals) / = Ftu for composites (linear to failure)
    Fcy: float          # compressive yield / compressive allowable (composites)
    Fsu: float          # ultimate shear allowable
    source: str
    kind: str = "metal"               # metal | composite_equivalent | core | wood
    t_min: float = 0.5e-3             # minimum gauge (manufacturing) — ASSUMPTION per material
    laminate: dict | None = None      # CLT definition for composite equivalents
    notes: list = field(default_factory=list)

    def as_structures_dict(self) -> dict:
        """Form used by :mod:`acdt.domains.aircraft.structures` (Phase 3 sizing): sigma_cap = Fcy, tau = Fsu."""
        return {"name": self.name, "rho": self.rho, "E": self.E, "nu": self.nu, "G": self.G, "sigma_cap": self.Fcy,
                "tau": self.Fsu, "sigma_tu": self.Ftu, "t_min_skin": self.t_min, "t_min_web": self.t_min,
                "cap_min_area": 5e-6, "note": self.source, "kind": self.kind}

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------------------------------------ CLT equivalents
LAMINA = {
    # Daniel & Ishai (2006) Table A.4 — typical values (verify vs CMH-17 Vol. 2)
    "AS4/3501-6": {"E1": 147e9, "E2": 10.3e9, "G12": 7.0e9, "nu12": 0.27, "rho": 1600.0, "t_ply": 0.13e-3},
    "E-glass/epoxy": {"E1": 41e9, "E2": 10.4e9, "G12": 4.3e9, "nu12": 0.28, "rho": 1970.0, "t_ply": 0.13e-3},
}
QUASI_ISO = (0.0, 45.0, -45.0, 90.0)            # [0/±45/90]s
SPAR_CAP = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 45.0, -45.0, 90.0)   # 70/20/10 — ASSUMPTION (UD-rich cap laminate)
STRAIN_CUTOFF = {"eps_c": 3500e-6, "eps_t": 4000e-6, "gamma": 7000e-6, "k_env": 0.8}   # ASSUMPTION (see docstring)


def clt_engineering_constants(lamina: dict, angles_deg) -> dict:
    """In-plane engineering constants of a symmetric, balanced laminate (Jones 1999 Eq. 4.92):
    E_x = 1/(h a11), E_y = 1/(h a22), G_xy = 1/(h a66), ν_xy = −a12/a11 with a = A⁻¹."""
    from .fem.laminate import plane_stress_Q, _Tbar

    Q = plane_stress_Q(lamina["E1"], lamina["E2"], lamina["nu12"], lamina["G12"])
    t = lamina["t_ply"]
    A = np.zeros((3, 3))
    for ang in list(angles_deg) + list(angles_deg)[::-1]:     # symmetric stack
        T = _Tbar(math.radians(ang))
        A += T.T @ Q @ T * t
    h = 2 * len(angles_deg) * t
    a = np.linalg.inv(A)
    return {"Ex": 1 / (h * a[0, 0]), "Ey": 1 / (h * a[1, 1]), "Gxy": 1 / (h * a[2, 2]), "nu_xy": -a[0, 1] / a[0, 0],
            "h_per_sublaminate": h}


def composite_equivalent(key: str, lamina_name: str, angles=QUASI_ISO, cut=STRAIN_CUTOFF, t_min=0.25e-3,
                         label: str = "") -> Material:
    """Equivalent isotropic material of a laminate: E = E_x, G = G_xy, ν = ν_xy (CLT); allowables from the design
    strain cut-offs × k_env (σ = E ε, τ = G γ)."""
    lam = LAMINA[lamina_name]
    c = clt_engineering_constants(lam, angles)
    k = cut["k_env"]
    E, G = c["Ex"], c["Gxy"]
    return Material(key, f"{lamina_name} {label or 'laminate'} — equivalent isotropic (CLT)", E, G, c["nu_xy"],
                    lam["rho"], k * cut["eps_t"] * E, k * cut["eps_t"] * E, k * cut["eps_c"] * E, k * cut["gamma"] * G,
                    "CLT (Jones 1999) on Daniel & Ishai (2006) Table A.4 lamina; strain cut-offs ASSUMPTION "
                    "(CMH-17-3G Vol. 3 Ch. 12 / Niu 1992)", "composite_equivalent", t_min,
                    {"lamina": lamina_name, "angles_half_stack": list(angles), "lamina_props": lam, "cutoffs": dict(cut),
                     "E_y": c["Ey"]},
                    ["isotropic equivalent: valid for in-plane membrane behaviour of balanced laminates; bending "
                     "stiffness D and anisotropic coupling are NOT represented (high-fidelity stage)"])


UD = (0.0,)                                     # roving / tecido unidirecional puro
PM45 = (45.0, -45.0)                            # tecido ±45 (revestimentos de corte de planadores)
# Banzos de longarina em rovings de vidro de planador: tensão de cálculo ÚLTIMA 300 MPa do banzo do Schempp-Hirth
# Janus (Patching & Wood, "Fatigue testing of a GFRP glider", Technical Soaring / XXII OSTIV Congress, Uvalde 1991:
# "ultimate design stress of 300 MPa", 950 με/g nos rovings do banzo superior até 9 g último).
GLIDER_GFRP_CAP_ULT_PA = 300e6


def glider_gfrp_cap() -> Material:
    """Banzo de rovings de vidro UD (E1 de Daniel & Ishai Tab. A.4) com a tensão de cálculo última do Janus
    (:data:`GLIDER_GFRP_CAP_ULT_PA`, Patching & Wood 1991) como admissível de compressão e tração."""
    lam = LAMINA["E-glass/epoxy"]
    E = lam["E1"]
    s = GLIDER_GFRP_CAP_ULT_PA
    return Material("gfrp_ud_cap", "E-glass/epoxy UD rovings — glider spar cap", E, lam["G12"], lam["nu12"],
                    lam["rho"], s, s, s, 0.8 * STRAIN_CUTOFF["gamma"] * lam["G12"],
                    "E1 Daniel & Ishai (2006) Tab. A.4; σ de cálculo último 300 MPa — Patching & Wood (1991), "
                    "banzo GFRP do Janus (OSTIV XXII); τ por corte de deformação (PRESSUPOSTO)",
                    "composite_equivalent", 0.25e-3, {"lamina": "E-glass/epoxy", "angles_half_stack": [0.0]},
                    ["admissível de banzo de planador (ensaio de fadiga/estático publicado), não do CMH-17"])


def _metals() -> dict:
    return {
        "al2024_t3": Material("al2024_t3", "Al 2024-T3 sheet", 72.4e9, 27.6e9, 0.33, 2780.0, 434e6, 269e6, 269e6,
                              262e6, "MIL-HDBK-5J Table 3.2.3.0(b) — typical/S-basis (as Phase 3 MATERIALS)",
                              t_min=0.41e-3),
        "al7075_t6": Material("al7075_t6", "Al 7075-T6 sheet", 10.3e3 * KSI, 3.9e3 * KSI, 0.33, 0.101 * LB_IN3,
                              78 * KSI, 68 * KSI, 68 * KSI, 45 * KSI,
                              "MIL-HDBK-5J Table 3.7.6.0(b) sheet — verify (A/B/S basis per thickness)", t_min=0.41e-3),
        "steel_4130": Material("steel_4130", "AISI 4130 normalized sheet (≤ 0.188 in)", 29.0e3 * KSI, 11.0e3 * KSI,
                               0.32, 0.283 * LB_IN3, 95 * KSI, 75 * KSI, 75 * KSI, 57 * KSI,
                               "MIL-HDBK-5J Table 2.3.1.0(c1), S-basis", t_min=0.5e-3),
        "ti6al4v": Material("ti6al4v", "Ti-6Al-4V annealed sheet", 16.0e3 * KSI, 6.2e3 * KSI, 0.31, 0.160 * LB_IN3,
                            134 * KSI, 126 * KSI, 130 * KSI, 79 * KSI,
                            "MIL-HDBK-5J Table 5.4.1.0(b), annealed sheet — verify", t_min=0.4e-3),
    }


def _others() -> dict:
    return {
        "pvc_foam_h80": Material("pvc_foam_h80", "PVC foam core (Divinycell H80 class)", 95e6, 27e6, 0.3, 80.0,
                                 2.2e6, 2.2e6, 1.4e6, 1.15e6, "DIAB Divinycell H datasheet (typical) — reference only",
                                 "core", 2e-3),
        "balsa": Material("balsa", "Balsa (along grain)", 3.4e9, 0.15e9, 0.3, 160.0, 14.9e6, 14.9e6, 14.9e6, 2.0e6,
                          "USDA Wood Handbook FPL-GTR-190 Table 5-3b (E, compression ∥); G and τ ASSUMPTION "
                          "(G/E ≈ 0.05 typical of wood) — reference only", "wood", 1e-3),
    }


def library() -> dict[str, Material]:
    lib = _metals()
    lib["cfrp_qi"] = composite_equivalent("cfrp_qi", "AS4/3501-6", QUASI_ISO, label="[0/±45/90]s quasi-isotropic")
    lib["cfrp_cap"] = composite_equivalent("cfrp_cap", "AS4/3501-6", SPAR_CAP, label="70/20/10 spar-cap laminate")
    lib["gfrp_qi"] = composite_equivalent("gfrp_qi", "E-glass/epoxy", QUASI_ISO, label="[0/±45/90]s quasi-isotropic")
    lib["gfrp_pm45"] = composite_equivalent("gfrp_pm45", "E-glass/epoxy", PM45, label="±45 fabric (shear skins)")
    lib["cfrp_pm45"] = composite_equivalent("cfrp_pm45", "AS4/3501-6", PM45, label="±45 fabric (shear skins)")
    lib["gfrp_ud_cap"] = glider_gfrp_cap()
    lib.update(_others())
    return lib


def get(key: str) -> Material:
    lib = library()
    if key not in lib:
        raise KeyError(f"material {key!r} not in the library ({', '.join(lib)})")
    return lib[key]


def composite_box_material(skin="cfrp_qi", cap="cfrp_cap", core="pvc_foam_h80") -> dict:
    """Phase 3-style CFRP box dict made only of equivalent isotropic materials (skins/webs ``skin``, caps ``cap``,
    sandwich core ``core``) — the Phase 6 replacement of the legacy ``structures.MATERIALS['cfrp']``."""
    s, c, k = get(skin), get(cap), get(core)
    d = s.as_structures_dict()
    d.update({"name": f"{s.name} + caps {c.name}", "E_cap": c.E, "sigma_cap": c.Fcy, "sigma_tu": s.Ftu,
              "core": {"name": k.name, "rho": k.rho, "E": k.E, "G": k.G, "t_min": k.t_min, "tau": k.Fsu},
              "note": "Phase 6 equivalent-isotropic composite box (CLT) — " + s.source})
    return d
