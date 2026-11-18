"""EASA SORA 2.5 (AMC1 Article 11, Reg. (EU) 2019/947 — ED Decision 2025/018/R, Issue 1 Amdt 3): ground risk
(iGRC Table 1, mitigations Table 5), air risk (AEC → initial ARC, Figure 6), SAIL (Table 3), TMPR (Table 6) and
OSO robustness (Table 14).

Tables transcribed from the EASA AMC/GM text (https://www.easa.europa.eu/en/document-library/acceptable-means-of-
compliance-and-guidance-materials/amc-gm-regulation-eu-2019947); check against the issue in force before use.
Step #8 containment (Tables 8–13 + Annex E § E.4) is available **opt-in** when adjacent-area
inputs are supplied (:mod:`acdt.core.certification.containment`). Missing density, assemblies,
SAIL, or cited compliance evidence → unassessed (never a silent pass or a default 'low').
Strategic air-risk mitigations (Annex C) remain an open item unless the operator supplies a residual ARC.
The operator, not the designer, owns the SORA; acdt gives the design-side view.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SOURCE = ("EASA AMC1 Article 11 Reg. (EU) 2019/947 (SORA 2.5), ED Decision 2025/018/R — "
          "https://www.easa.europa.eu/en/document-library/acceptable-means-of-compliance-and-guidance-materials/"
          "amc-gm-regulation-eu-2019947")

# Table 1 — columns: (max characteristic dimension m, max speed m/s)
COLUMNS = [(1.0, 25.0), (3.0, 35.0), (8.0, 75.0), (20.0, 120.0), (40.0, 200.0)]
POP_ROWS = ["controlled", "<5", "<50", "<500", "<5000", "<50000", ">50000"]
IGRC = {"controlled": [1, 1, 2, 3, 3], "<5": [2, 3, 4, 5, 6], "<50": [3, 4, 5, 6, 7], "<500": [4, 5, 6, 7, 8],
        "<5000": [5, 6, 7, 8, 9], "<50000": [6, 7, 8, 9, 10], ">50000": [7, 8, None, None, None]}
# Table 5 — reduction by robustness (None = n/a)
MITIGATIONS = {"M1A": {"low": -1, "medium": -2}, "M1B": {"medium": -1, "high": -2},
               "M1C": {"low": -1}, "M2": {"medium": -1, "high": -2}}
MITIGATION_PT = {"M1A": "M1(A) abrigo (sheltering)", "M1B": "M1(B) restrições operacionais",
                 "M1C": "M1(C) observação do solo", "M2": "M2 redução dos efeitos do impacto (p.ex. paraquedas)"}
# Figure 6 — aggregated encounter categories (120 m ≈ 400 ft AGL in SORA 2.5)
AEC = {1: ("d", "ambiente de aeródromo em espaço classe B, C ou D"),
       2: ("d", "> 120 m AGL em zona Mode-S/TMZ"),
       3: ("d", "> 120 m AGL em espaço controlado"),
       4: ("c", "> 120 m AGL, não controlado, sobre zona urbana"),
       5: ("c", "> 120 m AGL, não controlado, sobre zona rural"),
       6: ("c", "ambiente de aeródromo em espaço classe E, F ou G"),
       7: ("c", "< 120 m AGL em zona Mode-S/TMZ"),
       8: ("c", "< 120 m AGL em espaço controlado"),
       9: ("c", "< 120 m AGL, não controlado, sobre zona urbana"),
       10: ("b", "< 120 m AGL, não controlado, sobre zona rural"),
       11: ("b", "acima de FL600"),
       12: ("a", "espaço atípico/segregado")}
TMPR = {"a": "nenhum", "b": "baixo", "c": "médio", "d": "alto"}
# Table 3 — rows final GRC ≤2,3,4,5,6,7
SAIL = {2: {"a": "I", "b": "II", "c": "IV", "d": "VI"}, 3: {"a": "II", "b": "II", "c": "IV", "d": "VI"},
        4: {"a": "III", "b": "III", "c": "IV", "d": "VI"}, 5: {"a": "IV", "b": "IV", "c": "IV", "d": "VI"},
        6: {"a": "V", "b": "V", "c": "V", "d": "VI"}, 7: {"a": "VI", "b": "VI", "c": "VI", "d": "VI"}}
SAILS = ["I", "II", "III", "IV", "V", "VI"]
# Table 14 — robustness per SAIL I..VI; designer = evidence expected from the UAS designer (Table 14 'Designer')
OSO = {
    "OSO#01": ("operador competente e/ou com provas dadas", "NR L M H H H", False),
    "OSO#02": ("UAS projetado e produzido por entidade competente", "NR NR L M H H", True),
    "OSO#03": ("manutenção do UAS", "L L M M H H", False),
    "OSO#04": ("componentes essenciais projetados segundo uma norma de aeronavegabilidade (ADS)", "NR NR NR M H H", True),
    "OSO#05": ("UAS projetado considerando segurança e fiabilidade de sistemas", "NR NR L M H H", True),
    "OSO#06": ("características da ligação C3 adequadas à operação", "NR L L M H H", True),
    "OSO#07": ("verificação de conformidade da configuração do UAS", "L L M M H H", False),
    "OSO#08": ("procedimentos operacionais definidos, validados e cumpridos", "L M H H H H", True),
    "OSO#09": ("tripulação remota treinada e atualizada", "L L M M H H", False),
    "OSO#13": ("serviços externos adequados à operação", "L L M H H H", False),
    "OSO#16": ("coordenação multi-tripulação", "L L M M H H", False),
    "OSO#17": ("tripulação remota apta para operar", "L L M M H H", False),
    "OSO#18": ("proteção automática do envelope de voo contra erro humano", "NR NR L M H H", True),
    "OSO#19": ("recuperação segura de erro humano", "NR NR L M M H", True),
    "OSO#20": ("avaliação de fatores humanos; HMI adequada", "NR L L M M H", True),
    "OSO#23": ("condições ambientais para operação segura definidas e mensuráveis", "L L M M H H", True),
    "OSO#24": ("UAS projetado e qualificado para condições ambientais adversas", "NR NR M H H H", True),
}
ROB_PT = {"NR": "não requerido", "L": "baixa", "M": "média", "H": "alta"}
# Light-UAS (EASA Special Condition, Medium Risk) — design verification route by SAIL (see basis.LIGHT_UAS_NOTES)
DESIGN_ROUTE = {"I": "declaração do operador (sem verificação de projeto pela EASA)",
                "II": "declaração do operador (sem verificação de projeto pela EASA)",
                "III": "declaração de conformidade do projetista com a SC Light-UAS (verificar)",
                "IV": "Design Verification Report (DVR) da EASA — SC Light-UAS Medium Risk / MoC Light-UAS.2510-01",
                "V": "certificado de tipo (TC) ou equivalente — verificar com a EASA",
                "VI": "certificado de tipo (TC) ou equivalente — verificar com a EASA"}


@dataclass
class SoraInput:
    span_m: float
    v_max_m_s: float
    population: str = "<50"            # POP_ROWS key (highest density in the iGRC footprint) — operator input
    aec: int = 10
    mitigations: dict = field(default_factory=dict)   # {"M1A": "low", "M2": "medium", ...}
    mtow_kg: float | None = None
    vlos: bool = False
    containment: dict | None = None  # opt-in Step #8 (adjacent density, assemblies, evidence)


def column(span_m: float, v_max: float) -> int:
    """Table 1 column: the more demanding of dimension and speed (exceeding either → next column)."""
    for i, (d, v) in enumerate(COLUMNS):
        if span_m <= d and v_max <= v:
            return i
    raise ValueError(f"dimensão {span_m:.1f} m / velocidade {v_max:.0f} m/s fora da Tabela 1 (> 40 m ou > 200 m/s): "
                     "usar o Anexo F")


def igrc(span_m: float, v_max: float, population: str) -> int | None:
    if population not in IGRC:
        raise ValueError(f"population '{population}' unknown ({', '.join(POP_ROWS)})")
    return IGRC[population][column(span_m, v_max)]


def final_grc(i_grc: int, col: int, mitigations: dict) -> tuple[int, list[str]]:
    """Apply Table 5 in numerical order; final GRC not below the controlled-ground-area value of the column.
    M1(A) medium cannot be combined with M1(B) (Annex B)."""
    notes = []
    m = {k: (v or "").lower() for k, v in (mitigations or {}).items() if v and str(v).lower() not in ("none", "no")}
    if m.get("M1A") == "medium" and "M1B" in m:
        raise ValueError("M1(A) robustez média não pode ser combinada com M1(B) (SORA Anexo B)")
    g = i_grc
    for k in ("M1A", "M1B", "M1C", "M2"):
        if k in m:
            red = MITIGATIONS[k].get(m[k])
            if red is None:
                raise ValueError(f"{k} robustez '{m[k]}' n/a na Tabela 5")
            g += red
            notes.append(f"{MITIGATION_PT[k]} ({m[k]}): {red:+d}")
    floor = IGRC["controlled"][col]
    if g < floor:
        notes.append(f"GRC final limitado ao valor de área controlada da coluna ({floor})")
        g = floor
    return g, notes


def sail(grc: int, arc: str) -> str | None:
    """None → GRC > 7: operation in the 'certified' category."""
    if grc > 7:
        return None
    return SAIL[max(grc, 2)][arc]


def oso_table(s: str) -> list[dict]:
    i = SAILS.index(s)
    return [{"oso": k, "título": t, "robustez": ROB_PT[r.split()[i]], "nível": r.split()[i], "projetista": d}
            for k, (t, r, d) in OSO.items()]


def assess(inp: SoraInput) -> dict:
    col = column(inp.span_m, inp.v_max_m_s)
    ig = igrc(inp.span_m, inp.v_max_m_s, inp.population)
    from .containment import assess_containment
    out = {"source": SOURCE, "column": f"{COLUMNS[col][0]:g} m / {COLUMNS[col][1]:g} m/s", "iGRC": ig,
           "inputs": {"span_m": inp.span_m, "v_max_m_s": inp.v_max_m_s, "population": inp.population,
                      "aec": inp.aec, "mitigations": inp.mitigations, "vlos": inp.vlos,
                      "containment": inp.containment},
           "open": ["Mitigações estratégicas de risco aéreo (Anexo C) não aplicadas — ARC residual = ARC inicial"]}
    # Step #8: only assessed when the operator/agent supplies adjacent-area inputs
    # (otherwise unassessed, never a silent pass — kept as an open item for BC).
    if ig is None:
        out.update(grc=None, sail=None, category="fora do âmbito SORA (> 50 000 hab/km² com UA ≥ 8 m / 75 m/s)")
        out["containment"] = assess_containment(
            span_m=inp.span_m, v_max_m_s=inp.v_max_m_s, sail=None,
            mtow_kg=inp.mtow_kg, containment=inp.containment, span_col=col)
        _containment_open(out)
        return out
    g, notes = final_grc(ig, col, inp.mitigations)
    arc, arc_desc = AEC[inp.aec]
    s = sail(g, arc)
    out.update(final_GRC=g, mitigation_notes=notes, iARC=arc, AEC=f"AEC {inp.aec}: {arc_desc}", residual_ARC=arc,
               TMPR="VLOS/observadores aceites como mitigação tática" if inp.vlos else TMPR[arc], SAIL=s)
    if s is None:
        out["category"] = "certificada (GRC final > 7)"
        out["containment"] = assess_containment(
            span_m=inp.span_m, v_max_m_s=inp.v_max_m_s, sail=None,
            mtow_kg=inp.mtow_kg, containment=inp.containment, span_col=col)
        _containment_open(out)
        return out
    out["category"] = "específica"
    out["design_route"] = DESIGN_ROUTE[s]
    out["OSOs"] = oso_table(s)
    out["containment"] = assess_containment(
        span_m=inp.span_m, v_max_m_s=inp.v_max_m_s, sail=s,
        mtow_kg=inp.mtow_kg, containment=inp.containment, span_col=col)
    _containment_open(out)
    return out



def _containment_open(out: dict) -> None:
    """Keep Step #8 on the open list unless the requirement itself was assessed."""
    c = out.get("containment") or {}
    if c.get("requirement_status") in ("ok", "out_of_scope"):
        return
    out.setdefault("open", [])
    if not any("contenção" in x for x in out["open"]):
        out["open"].insert(0, "Passo #8 contenção (Tabelas 8–13) — por avaliar pelo operador (área adjacente, ajuntamentos); unassessed≠pass")


def to_markdown(a: dict) -> str:
    L = ["## SORA 2.5 (vista do projetista)", "", f"Fonte: {a['source']}", "",
         f"- coluna da Tabela 1: {a['column']} (envergadura {a['inputs']['span_m']:.2f} m, "
         f"v_max {a['inputs']['v_max_m_s']:.1f} m/s)",
         f"- densidade populacional (PRESSUPOSTO do operador): {a['inputs']['population']} hab/km² → iGRC {a['iGRC']}"]
    if a.get("final_GRC") is not None:
        L += [f"- mitigações: {'; '.join(a['mitigation_notes']) or 'nenhuma'} → GRC final {a['final_GRC']}",
              f"- {a['AEC']} → ARC-{a['iARC']} (residual {a['residual_ARC']}), TMPR {a['TMPR']}",
              f"- **SAIL {a['SAIL'] or '—'}** — categoria {a['category']}"]
    else:
        L.append(f"- categoria: {a['category']}")
    if a.get("design_route"):
        L += [f"- via de verificação do projeto: {a['design_route']}", "", "| OSO | objetivo | robustez | projetista |",
              "|---|---|---|---|"]
        L += [f"| {o['oso']} | {o['título']} | {o['robustez']} | {'sim' if o['projetista'] else ''} |" for o in a["OSOs"]]
    c = a.get("containment")
    if c:
        L += ["", "### Passo #8 — contenção", "",
              f"- estado: requisito {c.get('requirement_status')}, conformidade {c.get('compliance_status')} "
              f"(status {c.get('status')})",
              f"- robustez exigida: {c.get('required_robustness') or '—'} "
              f"({c.get('table') or 'tabela n/d'})"]
        if c.get("adjacent_radius_km") is not None:
            L.append(f"- raio da área adjacente: {c['adjacent_radius_km']:.2f} km")
        if c.get("p_exit_target_per_fh") is not None:
            L.append(f"- alvo quantitativo Anexo E § E.4 Critério #1: P(sair do volume) < {c['p_exit_target_per_fh']:.0e}/FH")
        for n in c.get("notes") or []:
            L.append(f"- {n}")
        if c.get("unassessed_terms"):
            L.append("- termos unassessed: " + "; ".join(c["unassessed_terms"]))
    L += ["", "Em aberto:"] + [f"- {t}" for t in a["open"]]
    return "\n".join(L) + "\n"
