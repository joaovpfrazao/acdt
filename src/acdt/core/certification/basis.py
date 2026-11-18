"""Certification basis selection from the requirements, the sized design and an optional ``certification:`` block.

Rules (sources in the catalogue ``core/data/cert_catalogue.yaml``):

* crewed aeroplanes: CS-23 Amdt 6 normal category when ≤ 19 passenger seats and MTOW ≤ 8 618 kg (19 000 lb)
  (CS/14 CFR 23.2005(a)); otherwise CS-25. Certification level by the maximum passenger seating (23.2005(b)):
  Level 1 = 0–1, Level 2 = 2–6, Level 3 = 7–9, Level 4 = 10–19. Performance level (23.2005(c)): low speed when
  VNO and VMO ≤ 250 KCAS and MMO ≤ 0.6.
* UAV: STANAG 4671 for fixed-wing UAV with MTOW 150–20 000 kg (USAR.1(a)); STANAG 4703 below 150 kg; EASA
  "specific" category adds the SORA (AMC1 Article 11 of Reg. (EU) 2019/947); "certified" category / SORA GRC > 7
  or SAIL VI → type certification (notes on SC Light-UAS).
* ``certification.basis`` overrides the automatic choice (e.g. STANAG 4671 below 150 kg "where considered
  applicable by the Certifying Authority", USAR.1(a)).
"""
from __future__ import annotations

from dataclasses import dataclass, field

LB = 0.45359237
KT = 0.514444

LIGHT_UAS_NOTES = [
    "EASA SC Light-UAS (Medium Risk): verificação de projeto para operações SAIL III–IV na categoria específica "
    "(SAIL III por declaração; SAIL IV com Design Verification Report da EASA) — "
    "https://www.easa.europa.eu/en/special-condition-sc-light-uas-medium-risk",
    "Meios de conformidade EASA (p.ex. MoC Light-UAS.2510-01 para SAIL IV) — "
    "https://www.easa.europa.eu/en/document-library/product-certification-consultations/final-means-compliance-uas-2510-01-sail-iv",
    "SAIL V–VI ou GRC final > 7: certificação de tipo da UAS (categoria certificada / alto risco) — verificar a base "
    "aplicável com a EASA; o STANAG 4671 é usado aqui como referência técnica.",
    "'CS-LUAS' (JARUS) é uma recomendação, não um código EASA adotado; usar apenas como orientação.",
]


@dataclass
class CertContext:
    uav: bool
    mtow_kg: float
    passengers: int = 0
    level: int | None = None
    perf_level: str = "low"          # "low" | "high"
    occupants: bool = True
    seaplane: bool = False
    icing: bool = False
    pressurized: bool = False
    multiengine: bool = False
    retractable: bool = False
    ifr: bool = False
    propulsion: str = "piston_prop"
    fuel: bool = True
    category: str | None = None
    ac23_class: str | None = None
    notes: list[str] = field(default_factory=list)

    def env(self) -> dict:
        return {k: getattr(self, k) for k in ("uav", "mtow_kg", "passengers", "level", "perf_level", "occupants",
                                              "seaplane", "icing", "pressurized", "multiengine", "retractable",
                                              "ifr", "propulsion", "fuel")}


def _req(result: dict, key: str):
    for r in result.get("requirements", []) or []:
        if r.get("key") == key:
            return r.get("value_si")
    return None


def build_context(result: dict, cert: dict | None = None) -> CertContext:
    cert = cert or {}
    w = result.get("weights", {})
    mtow = float(w.get("W0_kg") or 0.0)
    crew = float(w.get("crew_kg") or 0.0)
    prop = str(_req(result, "propulsion_type") or "piston_prop")
    cat = _req(result, "regulatory_category")
    uav = bool(cert.get("uav", crew <= 0.0))
    notes = []
    pax = cert.get("max_passenger_seats")
    if pax is None:
        if uav:
            pax = 0
        else:
            pm = float(_req(result, "crew_mass") or 77.0)
            pax = int(round(float(w.get("payload_kg") or 0.0) / pm))
            notes.append(f"lugares de passageiros estimados = carga útil / massa por pessoa = {pax} "
                         "(PRESSUPOSTO — defina certification.max_passenger_seats)")
    level = None if uav else (1 if pax <= 1 else 2 if pax <= 6 else 3 if pax <= 9 else 4)
    vn = (result.get("structures") or {}).get("vn") or {}
    vc = vn.get("VC_EAS_m_s")
    vno_kt = cert.get("VNO_KCAS") or (vc / KT if vc else None)
    if vno_kt is not None and cert.get("VNO_KCAS") is None:
        notes.append(f"VNO ≈ VC de projeto = {vno_kt:.0f} kt EAS≈CAS (PRESSUPOSTO para o nível de desempenho)")
    perf = "high" if (vno_kt and vno_kt > 250.0) or float(cert.get("MMO", 0) or 0) > 0.6 else "low"
    n_eng = int(cert.get("n_engines", 1))
    ctx = CertContext(uav=uav, mtow_kg=mtow, passengers=int(pax), level=level, perf_level=perf,
                      occupants=not uav, seaplane=bool(cert.get("seaplane", False)), icing=bool(cert.get("icing", False)),
                      pressurized=bool(cert.get("pressurized", False)), multiengine=n_eng > 1,
                      retractable=bool(cert.get("retractable_gear", False)), ifr=bool(cert.get("ifr", not uav)),
                      propulsion=prop, fuel=not prop.startswith("electric"), category=cat, notes=notes)
    if not uav:
        from ..safety.fha import ac23_class
        ctx.ac23_class = cert.get("ac23_class") or ac23_class(mtow, n_eng, turbine="turbo" in prop or "jet" in prop)
    return ctx


def select_basis(result: dict, cert: dict | None = None) -> dict:
    """→ {bases: [...], sora: bool, context: CertContext, rationale: [...], notes: [...]}"""
    cert = cert or {}
    ctx = build_context(result, cert)
    why: list[str] = []
    sora = False
    if cert.get("basis"):
        bases = list(cert["basis"]) if isinstance(cert["basis"], (list, tuple)) else [cert["basis"]]
        why.append(f"base imposta pelo utilizador: {', '.join(bases)}")
    elif not ctx.uav:
        if ctx.passengers <= 19 and ctx.mtow_kg <= 19000 * LB:
            bases = ["cs23"]
            why.append(f"tripulado, {ctx.passengers} lugares de passageiros e MTOW {ctx.mtow_kg:.0f} kg ≤ 8 618 kg "
                       f"→ CS-23 categoria normal, Nível {ctx.level}, {'baixa' if ctx.perf_level == 'low' else 'alta'} "
                       "velocidade (CS 23.2005)")
        else:
            bases = ["cs25"]
            why.append("tripulado acima dos limites da categoria normal → CS-25")
    else:
        bases = ["stanag4671" if ctx.mtow_kg >= 150.0 else "stanag4703"]
        why.append(f"UAV com MTOW {ctx.mtow_kg:.1f} kg → "
                   + ("STANAG 4671 (USAR.1: 150–20 000 kg)" if ctx.mtow_kg >= 150 else "STANAG 4703 (< 150 kg)"))
    so = cert.get("sora", None)
    if ctx.uav and (so is True or isinstance(so, dict)
                    or (so is None and ctx.category in ("easa_specific", None, "easa_certified"))):
        sora = True
        why.append("UAS na categoria específica EASA → avaliação SORA (AMC1 Art. 11, Reg. (EU) 2019/947)")
    if ctx.category in ("cs_vla", "cs_lsa"):
        why.append(f"categoria {ctx.category}: CS-VLA/CS-LSA não catalogados — usado o CS-23 como referência")
    notes = list(ctx.notes)
    if ctx.uav:
        notes += LIGHT_UAS_NOTES
    return {"bases": bases, "sora": sora, "context": ctx, "rationale": why, "notes": notes}
