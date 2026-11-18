"""Functional hazard assessment (FHA) support: severity classes, probability targets and DAL per scheme.

Schemes (all values from the cited documents; probabilities are average per flight hour):

* ``ac23_1309_class_I`` … ``_IV`` — FAA AC 23.1309-1E (2011) Figure 2 (Minor/Major/Hazardous/Catastrophic) and
  the software/complex-hardware DAL (primary/secondary) of the same figure. Class I: SRE ≤ 6 000 lb; II: MRE/STE/
  MTE ≤ 6 000 lb; III: > 6 000 lb; IV: commuter. EASA accepts the same values through AMC to CS 23.2510 (ASTM
  F3230 safety assessment, referenced by F3264).
* ``amc25_1309`` — EASA AMC 25.1309: Minor ≤ 1e-3 (probable), Major ≤ 1e-5 (remote), Hazardous ≤ 1e-7
  (extremely remote), Catastrophic ≤ 1e-9 (extremely improbable); DAL per ARP4754A (A/B/C/D).
* ``stanag4671`` — STANAG 4671 Ed. 1, AMC.1309 (definitions in Annex A): Catastrophic extremely improbable
  < 1e-6, Hazardous extremely remote ≤ 1e-5, Major remote ≤ 1e-4, Minor probable ≤ 1e-3; if the state of the
  art does not allow it, the combination of all catastrophic conditions ≤ 1e-5 (AMC.1309 (5)(c)).
* ``stanag4703`` — STANAG 4703 / AEP-83 Annex G: cumulative catastrophic probability P_CUM-CAT = 1e-4 for MTOW
  < 15 kg and 0.0015 / MTOW[kg] for 15–150 kg; individual conditions per the Hazard Reference System agreed with
  the authority (not fixed here).
"""
from __future__ import annotations

SEVERITIES = ("no_effect", "minor", "major", "hazardous", "catastrophic")
SEVERITY_PT = {"no_effect": "sem efeito", "minor": "menor", "major": "maior", "hazardous": "perigosa",
               "catastrophic": "catastrófica"}

_AC23 = {  # AC 23.1309-1E Figure 2: (target per flight hour, DAL primary/secondary)
    "I":   {"minor": (1e-3, "P=D"), "major": (1e-4, "P=C, S=D"), "hazardous": (1e-5, "P=C, S=D"),
            "catastrophic": (1e-6, "P=C, S=C")},
    "II":  {"minor": (1e-3, "P=D"), "major": (1e-5, "P=C, S=D"), "hazardous": (1e-6, "P=C, S=C"),
            "catastrophic": (1e-7, "P=C, S=C")},
    "III": {"minor": (1e-3, "P=D"), "major": (1e-5, "P=C, S=D"), "hazardous": (1e-7, "P=C, S=C"),
            "catastrophic": (1e-8, "P=B, S=C")},
    "IV":  {"minor": (1e-3, "P=D"), "major": (1e-5, "P=C, S=D"), "hazardous": (1e-7, "P=B, S=C"),
            "catastrophic": (1e-9, "P=A, S=B")},
}

SCHEMES: dict[str, dict] = {
    **{f"ac23_1309_class_{c}": {"targets": {k: v[0] for k, v in t.items()}, "dal": {k: v[1] for k, v in t.items()},
                                "ref": "FAA AC 23.1309-1E (2011) Fig. 2",
                                "url": "https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_23_1309-1E.pdf"}
       for c, t in _AC23.items()},
    "amc25_1309": {"targets": {"minor": 1e-3, "major": 1e-5, "hazardous": 1e-7, "catastrophic": 1e-9},
                   "dal": {"minor": "D", "major": "C", "hazardous": "B", "catastrophic": "A"},
                   "ref": "EASA CS-25 AMC 25.1309; DAL per SAE ARP4754A",
                   "url": "https://www.easa.europa.eu/en/document-library/certification-specifications/group/cs-25-large-aeroplanes"},
    "stanag4671": {"targets": {"minor": 1e-3, "major": 1e-4, "hazardous": 1e-5, "catastrophic": 1e-6},
                   "dal": {}, "combined_catastrophic_fallback": 1e-5,
                   "ref": "STANAG 4671 Ed. 1 USAR.1309 / AMC.1309 (Annex A definitions)",
                   "url": "https://nso.nato.int"},
    "stanag4703": {"targets": {}, "dal": {},
                   "ref": "STANAG 4703 (AEP-83) UL.30 + Annex G (cumulative catastrophic)",
                   "url": "https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/391827/20140916-STANAG-4703_AEP-83_A__1_.pdf"},
}


def stanag4703_cumulative_catastrophic(mtow_kg: float) -> float:
    """STANAG 4703 Annex G: P_CUM-CAT per flight hour."""
    return 1e-4 if mtow_kg < 15.0 else 0.0015 / mtow_kg


def ac23_class(mtow_kg: float, n_engines: int = 1, turbine: bool = False, commuter: bool = False) -> str:
    """AC 23.1309-1E §15 airplane class (typical): I SRE ≤ 6 000 lb; II MRE/STE/MTE ≤ 6 000 lb; III > 6 000 lb;
    IV commuter."""
    if commuter:
        return "IV"
    if mtow_kg > 6000 * 0.45359237:
        return "III"
    return "II" if (n_engines > 1 or turbine) else "I"


def target(scheme: str, severity: str, mtow_kg: float | None = None) -> float | None:
    s = SCHEMES[scheme]
    if scheme == "stanag4703" and severity == "catastrophic" and mtow_kg:
        return stanag4703_cumulative_catastrophic(mtow_kg)
    return s["targets"].get(severity)


def dal(scheme: str, severity: str) -> str:
    return SCHEMES[scheme].get("dal", {}).get(severity, "")


def single_failure_rule(severity: str) -> bool:
    """Catastrophic failure conditions must not result from a single failure (CS 23.2510 / AMC, AC 23.1309-1E,
    SC-RPAS.1309, STANAG 4703 UL.30)."""
    return severity == "catastrophic"
