"""Material comparison by Ashby performance indices (Phase 7).

Minimum-mass scaling for a fixed geometry envelope and a given governing requirement (Ashby, M.F. *Materials
Selection in Mechanical Design*, 4th ed., Butterworth-Heinemann 2011, Ch. 5 and App. B):

==================  ===================  ======================================
requirement          index (maximise)      mass ratio  m2/m1
==================  ===================  ======================================
tie, stiffness       E/rho                 (rho2/rho1) (E1/E2)
tie, strength        sigma/rho             (rho2/rho1) (s1/s2)
beam, stiffness      E^(1/2)/rho           (rho2/rho1) (E1/E2)^(1/2)
beam, strength       sigma^(2/3)/rho       (rho2/rho1) (s1/s2)^(2/3)
panel, stiffness     E^(1/3)/rho           (rho2/rho1) (E1/E2)^(1/3)   (also panel buckling)
panel, strength      sigma^(1/2)/rho       (rho2/rho1) (s1/s2)^(1/2)
==================  ===================  ======================================

The strength used is ``Ftu`` (or ``sigma``) of the material dict; composites are the equivalent-isotropic
laminates of :mod:`acdt.core.materials`. Cost per part = scaled mass x buy-to-fly x price.
"""
from __future__ import annotations

from dataclasses import replace

from .processes import Part

EXPONENTS = {  # (stiffness exponent, strength exponent) on the property ratio
    "tie_stiffness": ("E", 1.0), "tie_strength": ("Ftu", 1.0),
    "beam_stiffness": ("E", 0.5), "beam_strength": ("Ftu", 2 / 3),
    "panel_stiffness": ("E", 1 / 3), "panel_strength": ("Ftu", 0.5),
}
# governing requirement by part kind (ASSUMPTION, documented: skins and shells buckling/stiffness-critical panels,
# spars/longerons bending beams, ribs/frames shear-web panels, fittings strength)
AUTO = {"skin": "panel_stiffness", "shell": "panel_stiffness", "fairing": "panel_stiffness",
        "spar": "beam_stiffness", "longeron": "beam_stiffness", "stringer": "beam_stiffness",
        "rib": "panel_stiffness", "frame": "panel_stiffness", "bulkhead": "panel_stiffness",
        "fitting": "tie_strength"}


def mass_ratio(m_from: dict, m_to: dict, requirement: str) -> float:
    prop, n = EXPONENTS[requirement]
    return (m_to["rho"] / m_from["rho"]) * (m_from[prop] / m_to[prop]) ** n


def scale_part(part: Part, m_from: dict, m_to: dict, scaling: str = "auto") -> Part:
    req = AUTO.get(part.kind, "panel_stiffness") if scaling == "auto" else scaling
    r = mass_ratio(m_from, m_to, req)
    t = part.thickness_m * r * m_from["rho"] / m_to["rho"] if part.thickness_m else 0.0
    return replace(part, mass_kg=part.mass_kg * r, thickness_m=t, material=m_to.get("key"),
                   notes=part.notes + [f"mass scaled {r:.3f} from {m_from.get('key')} ({req}, Ashby)"])


def compare(materials: dict, requirement: str = "panel_stiffness", reference: str | None = None,
            b2f: dict | None = None) -> dict:
    """Rank materials for one requirement: relative mass vs ``reference`` and relative bought-material cost
    (mass x B2F x usd_per_kg) when prices are given. ``b2f``: {material key: buy-to-fly}."""
    keys = list(materials)
    ref = reference or keys[0]
    rows = []
    for k in keys:
        m = materials[k]
        r = mass_ratio(materials[ref], m, requirement)
        price = m.get("usd_per_kg")
        bf = (b2f or {}).get(k, 1.0)
        rows.append({"material": k, "relative_mass": r, "usd_per_kg": price, "b2f": bf,
                     "relative_material_cost": None if price is None else r * bf * price})
    c_ref = next(r for r in rows if r["material"] == ref)["relative_material_cost"]
    for r in rows:
        if r["relative_material_cost"] is not None:
            r["relative_material_cost"] = r["relative_material_cost"] / c_ref if c_ref else None
    rows.sort(key=lambda r: r["relative_mass"])
    return {"requirement": requirement, "reference": ref, "ranking": rows,
            "method": "Ashby (2011) performance indices, equal geometry envelope"}
