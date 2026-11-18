"""SORA 2.5 Step #8 — containment requirements (Tables 8–13) and Annex E integrity targets.

Source: EASA AMC1 Article 11 Reg. (EU) 2019/947 (SORA 2.5), ED Decision 2025/018/R,
§ S.4.8 and Annex E § E.4. Tables transcribed from the AMC; check the issue in force
before operational use. The operator, not the designer, owns the SORA.

Opt-in: without adjacent-area / assembly inputs the requirement is unassessed
(never a silent 'low' or a pass). Compliance with Annex E is unassessed unless a
cited qualitative claim or a sourced quantitative P(OV exit) is supplied.
Sheltering credit for UA > 3 m requires Annex F Edition 2.5 — not automated here.
"""
from __future__ import annotations

SOURCE = ("EASA AMC1 Article 11 Reg. (EU) 2019/947 (SORA 2.5) § S.4.8 Tables 8–13 "
          "and Annex E § E.4, ED Decision 2025/018/R — "
          "https://www.easa.europa.eu/en/document-library/acceptable-means-of-compliance-and-guidance-materials/"
          "amc-gm-regulation-eu-2019947")

# Annex E § E.4 Criterion #1 quantitative targets (untethered UA)
# Low and medium share 1e-3 /FH; high is 1e-4 /FH.
P_EXIT_OV = {"low": 1e-3, "medium": 1e-3, "high": 1e-4}

# Robustness order: more demanding first
_RANK = {"out_of_scope": 3, "high": 2, "medium": 1, "low": 0}

# Assembly size bands used as column keys (people)
ASM_BANDS = (">400k", "40k-400k", "<40k")


def _row(sail: str, mapping: dict) -> str:
    """Map a SAIL letter to the table row key in ``mapping``."""
    s = (sail or "").upper().replace("SAIL", "").strip()
    if s in ("I", "II") and "I-II" in mapping:
        return mapping["I-II"]
    if s == "III" and "III" in mapping:
        return mapping["III"]
    if s == "IV" and "IV" in mapping:
        return mapping["IV"]
    if s in ("V", "VI") and "V-VI" in mapping:
        return mapping["V-VI"]
    if s == "V" and "V" in mapping:
        return mapping["V"]
    if s == "VI" and "VI" in mapping:
        return mapping["VI"]
    if s in ("IV", "V", "VI") and "IV-VI" in mapping:
        return mapping["IV-VI"]
    raise ValueError(f"SAIL '{sail}' not in containment table row keys {sorted(mapping)}")


# Each column: (density_max_per_km2 or None=no upper limit, assembly band or None, sail→robustness)
# Tables 8–13 as transcribed from AMC1 Article 11 § S.4.8.3.

def _cols(*rows):
    return list(rows)


TABLES = {
    # Table 8 — UA up to 1 m (< 25 m/s), sheltering assumed applicable
    8: {
        "title": "Table 8 — UA up to 1 m with shelter assumption",
        "span_m": 1.0, "v_max_m_s": 25.0, "shelter": True,
        "columns": [
            (None, ">400k", {"I-II": "high", "III": "medium", "IV-VI": "low"}),
            (None, "40k-400k", {"I-II": "medium", "III": "low", "IV-VI": "low"}),
            (50_000, "<40k", {"I-II": "low", "III": "low", "IV-VI": "low"}),
        ],
    },
    # Table 9 — UA up to 3 m (< 35 m/s), shelter assumed applicable
    9: {
        "title": "Table 9 — UA up to 3 m with shelter assumption",
        "span_m": 3.0, "v_max_m_s": 35.0, "shelter": True,
        "columns": [
            (None, ">400k", {"I-II": "out_of_scope", "III": "out_of_scope", "IV": "medium", "V-VI": "low"}),
            (None, "40k-400k", {"I-II": "high", "III": "medium", "IV": "low", "V-VI": "low"}),
            (50_000, "<40k", {"I-II": "medium", "III": "low", "IV": "low", "V-VI": "low"}),
            (5_000, None, {"I-II": "low", "III": "low", "IV": "low", "V-VI": "low"}),
        ],
    },
    # Table 10 — UA up to 3 m (< 35 m/s), shelter not applicable
    10: {
        "title": "Table 10 — UA up to 3 m without shelter assumption",
        "span_m": 3.0, "v_max_m_s": 35.0, "shelter": False,
        "columns": [
            (None, ">400k", {"I-II": "out_of_scope", "III": "out_of_scope", "IV": "medium", "V-VI": "low"}),
            (50_000, "40k-400k", {"I-II": "high", "III": "medium", "IV": "low", "V-VI": "low"}),
            (5_000, "<40k", {"I-II": "medium", "III": "low", "IV": "low", "V-VI": "low"}),
            (500, None, {"I-II": "low", "III": "low", "IV": "low", "V-VI": "low"}),
        ],
    },
    # Table 11 — UA up to 8 m (< 75 m/s), sheltering not applicable
    11: {
        "title": "Table 11 — UA up to 8 m",
        "span_m": 8.0, "v_max_m_s": 75.0, "shelter": False,
        "columns": [
            (None, ">400k", {"I-II": "out_of_scope", "III": "out_of_scope", "IV": "out_of_scope", "V": "medium", "VI": "low"}),
            (50_000, "40k-400k", {"I-II": "out_of_scope", "III": "out_of_scope", "IV": "medium", "V": "low", "VI": "low"}),
            (5_000, "<40k", {"I-II": "high", "III": "medium", "IV": "low", "V": "low", "VI": "low"}),
            (500, None, {"I-II": "medium", "III": "low", "IV": "low", "V": "low", "VI": "low"}),
            (50, None, {"I-II": "low", "III": "low", "IV": "low", "V": "low", "VI": "low"}),
        ],
    },
    # Table 12 — UA up to 20 m (< 120 m/s)
    12: {
        "title": "Table 12 — UA up to 20 m",
        "span_m": 20.0, "v_max_m_s": 120.0, "shelter": False,
        "columns": [
            (None, ">400k", {"I-II": "out_of_scope", "III": "out_of_scope", "IV": "out_of_scope", "V": "out_of_scope", "VI": "medium"}),
            (50_000, "40k-400k", {"I-II": "out_of_scope", "III": "out_of_scope", "IV": "out_of_scope", "V": "medium", "VI": "low"}),
            (5_000, "<40k", {"I-II": "out_of_scope", "III": "out_of_scope", "IV": "medium", "V": "low", "VI": "low"}),
            (500, None, {"I-II": "high", "III": "medium", "IV": "low", "V": "low", "VI": "low"}),
            (50, None, {"I-II": "medium", "III": "low", "IV": "low", "V": "low", "VI": "low"}),
        ],
    },
    # Table 13 — UA up to 40 m (< 200 m/s)
    13: {
        "title": "Table 13 — UA up to 40 m",
        "span_m": 40.0, "v_max_m_s": 200.0, "shelter": False,
        "columns": [
            (None, ">400k", {"I-II": "out_of_scope", "III": "out_of_scope", "IV": "out_of_scope", "V": "out_of_scope", "VI": "out_of_scope"}),
            (50_000, "40k-400k", {"I-II": "out_of_scope", "III": "out_of_scope", "IV": "out_of_scope", "V": "out_of_scope", "VI": "medium"}),
            (5_000, "<40k", {"I-II": "out_of_scope", "III": "out_of_scope", "IV": "out_of_scope", "V": "medium", "VI": "low"}),
            (500, None, {"I-II": "out_of_scope", "III": "out_of_scope", "IV": "medium", "V": "low", "VI": "low"}),
            (50, None, {"I-II": "high", "III": "medium", "IV": "low", "V": "low", "VI": "low"}),
        ],
    },
}


def adjacent_radius_km(v_max_m_s: float) -> float:
    """Lateral outer limit of the adjacent ground area from the operational volume (S.4.8.3(b)(i)).

    Distance flown in 3 minutes at maximum speed, floored at 5 km and capped at 35 km.
    """
    if v_max_m_s is None or v_max_m_s <= 0:
        raise ValueError("v_max_m_s must be > 0 to size the adjacent ground area")
    d_km = float(v_max_m_s) * 180.0 / 1000.0
    return min(35.0, max(5.0, d_km))


def assembly_band(value) -> str:
    """Map a count or a band label to '>400k' | '40k-400k' | '<40k'."""
    if value is None or value == "":
        raise ValueError("outdoor assembly of people is missing")
    if isinstance(value, str):
        v = value.strip().lower().replace(" ", "")
        aliases = {
            ">400k": ">400k", "gt400k": ">400k", "over400k": ">400k", ">400000": ">400k",
            "40k-400k": "40k-400k", "40kto400k": "40k-400k", "40000-400000": "40k-400k",
            "<40k": "<40k", "lt40k": "<40k", "under40k": "<40k", "<40000": "<40k",
            "none": "<40k", "no": "<40k", "0": "<40k",
        }
        if v in aliases:
            return aliases[v]
        try:
            return assembly_band(float(v.replace("k", "e3").replace(",", "")))
        except ValueError as e:
            raise ValueError(f"unknown outdoor-assembly band '{value}' ({', '.join(ASM_BANDS)})") from e
    n = float(value)
    if n > 400_000:
        return ">400k"
    if n >= 40_000:
        return "40k-400k"
    if n >= 0:
        return "<40k"
    raise ValueError("outdoor assembly size cannot be negative")


def _select_table(span_col: int, sheltering: bool | None) -> tuple[int | None, list[str]]:
    """Return (table_number, notes). span_col is the Table 1 column index 0..4."""
    notes: list[str] = []
    if span_col == 0:
        return 8, notes
    if span_col == 1:
        if sheltering is None:
            return None, ["sheltering no adjacent area não indicado — Tabela 9 (com abrigo) vs 10 (sem) (S.4.8.4)"]
        return (9 if sheltering else 10), notes
    if span_col == 2:
        if sheltering:
            notes.append("abrigo em UA > 3 m não é creditado aqui (Anexo F Edition 2.5, não automatizado)")
        return 11, notes
    if span_col == 3:
        if sheltering:
            notes.append("abrigo em UA > 3 m não é creditado aqui (Anexo F Edition 2.5, não automatizado)")
        return 12, notes
    if span_col == 4:
        if sheltering:
            notes.append("abrigo em UA > 3 m não é creditado aqui (Anexo F Edition 2.5, não automatizado)")
        return 13, notes
    raise ValueError(f"Table 1 column {span_col} fora do âmbito das Tabelas 8–13")


def _robustness_from_column(sail: str, mapping: dict) -> str:
    return _row(sail, mapping)


def _column_for_density(columns: list, density_per_km2: float) -> int | None:
    """Tightest (smallest dens_max) column that still allows this average density.

    'No upper limit' (dens_max is None) always allows the value. A density above
    every finite cap still matches the unlimited column if one exists.
    """
    if density_per_km2 < 0:
        raise ValueError("adjacent population density cannot be negative")
    finite = [(i, d) for i, (d, _a, _m) in enumerate(columns) if d is not None and density_per_km2 < d]
    if finite:
        return min(finite, key=lambda x: x[1])[0]
    unlimited = [i for i, (d, _a, _m) in enumerate(columns) if d is None]
    return unlimited[0] if unlimited else None


def _column_for_assembly(columns: list, band: str) -> int | None:
    """Column whose assembly heading matches ``band``.

    A trailing column with assembly=None is only used for the tightest
    (smallest-assembly) band, consistent with the AMC layout (last columns
    tighten density after '<40k' has already been listed).
    """
    for i, (_d, a, _m) in enumerate(columns):
        if a == band:
            return i
    if band == "<40k":
        none_cols = [i for i, (_d, a, _m) in enumerate(columns) if a is None]
        if none_cols:
            return none_cols[-1]
    return None


def required_robustness(sail: str, table_no: int, *, density_per_km2: float,
                        assembly) -> dict:
    """Required containment robustness: most stringent of density vs assemblies (S.4.8.3(d))."""
    tbl = TABLES[table_no]
    cols = tbl["columns"]
    band = assembly_band(assembly)
    i_d = _column_for_density(cols, density_per_km2)
    i_a = _column_for_assembly(cols, band)
    if i_d is None:
        raise ValueError(f"densidade {density_per_km2} /km² fora das colunas de {tbl['title']}")
    if i_a is None:
        raise ValueError(f"ajuntamento '{band}' fora das colunas de {tbl['title']}")
    r_d = _robustness_from_column(sail, cols[i_d][2])
    r_a = _robustness_from_column(sail, cols[i_a][2])
    # most stringent
    winner = "density" if _RANK[r_d] >= _RANK[r_a] else "assembly"
    required = r_d if winner == "density" else r_a
    return {
        "required_robustness": required,
        "from_density": r_d, "from_assembly": r_a, "driver": winner,
        "density_column": i_d, "assembly_column": i_a, "assembly_band": band,
        "table": tbl["title"], "table_no": table_no,
    }


def assess_containment(*, span_m: float, v_max_m_s: float, sail: str | None,
                       mtow_kg: float | None = None, containment: dict | None = None,
                       span_col: int | None = None) -> dict:
    """Opt-in Step #8 assessment. Missing adjacent inputs → unassessed (never pass).

    ``containment`` keys (all optional until the step is requested):
      adjacent_population_density_per_km2, outdoor_assembly (band or count),
      sheltering (bool, required to choose Table 9 vs 10 at 3 m),
      claimed_robustness (low|medium|high), p_exit_operational_volume_per_fh,
      sources (dict with dates), evidence (str).
    """
    notes: list[str] = []
    unassessed: list[str] = []
    c = dict(containment or {})
    requested = bool(c)
    out = {
        "step": "#8",
        "source": SOURCE,
        "requested": requested,
        "requirement_status": "unassessed",
        "compliance_status": "unassessed",
        "status": "unassessed",
        "required_robustness": None,
        "claimed_robustness": (c.get("claimed_robustness") or None),
        "notes": notes,
        "unassessed_terms": unassessed,
        "p_exit_target_per_fh": None,
        "adjacent_radius_km": None,
    }
    if not requested:
        unassessed.append("containment inputs (passo #8 não pedido)")
        notes.append("Passo #8 contenção não pedido — requisito e conformidade unassessed (nunca pass silencioso)")
        return out

    if mtow_kg is not None and mtow_kg < 0.25:
        out.update(
            requirement_status="ok", compliance_status="ok", status="ok",
            required_robustness="low",
            adjacent_radius_km=None,
            operational_limitations="nenhuma exigida (MTOM < 250 g, S.4.8.3(a))",
            p_exit_target_per_fh=P_EXIT_OV["low"],
        )
        notes.append("MTOM < 250 g → contenção baixa, sem limites operacionais na área adjacente (S.4.8.3(a))")
        return out

    try:
        out["adjacent_radius_km"] = adjacent_radius_km(v_max_m_s)
        notes.append(
            f"raio da área adjacente = {out['adjacent_radius_km']:.2f} km "
            f"(3 min × {v_max_m_s:.1f} m/s, piso 5 km / tecto 35 km, S.4.8.3(b)(i))"
        )
    except ValueError as e:
        unassessed.append(str(e))

    if not sail:
        unassessed.append("SAIL (passo #7) em falta — não há linha nas Tabelas 8–13")
        out["unassessed_terms"] = unassessed
        return out

    from .sora import column as table1_column
    col = span_col if span_col is not None else table1_column(span_m, v_max_m_s)
    sheltering = c.get("sheltering")
    if "sheltering" in c and not isinstance(sheltering, bool) and sheltering is not None:
        s = str(sheltering).strip().lower()
        sheltering = s in ("true", "yes", "1", "sim") if s in ("true", "yes", "1", "sim", "false", "no", "0", "nao", "não") else None
        if sheltering is None:
            unassessed.append("sheltering deve ser true|false")

    tno, tnotes = _select_table(col, sheltering)
    notes.extend(tnotes)
    if tno is None:
        unassessed.append(tnotes[0] if tnotes else "tabela de contenção não selecionável")
        out["unassessed_terms"] = unassessed
        return out

    dens = c.get("adjacent_population_density_per_km2")
    asm = c.get("outdoor_assembly")
    if dens is None:
        unassessed.append("adjacent_population_density_per_km2")
    if asm is None or asm == "":
        unassessed.append("outdoor_assembly")
    if unassessed:
        notes.append("densidade média da área adjacente e ajuntamentos a 1 km são ambos exigidos (S.4.8.3(c)–(d)); "
                     "em falta → requisito unassessed (nunca low/pass silencioso)")
        out["unassessed_terms"] = unassessed
        out["table"] = TABLES[tno]["title"]
        return out

    try:
        look = required_robustness(sail, tno, density_per_km2=float(dens), assembly=asm)
    except ValueError as e:
        unassessed.append(str(e))
        out["unassessed_terms"] = unassessed
        return out

    req = look["required_robustness"]
    out.update(look)
    out["requirement_status"] = "out_of_scope" if req == "out_of_scope" else "ok"
    out["p_exit_target_per_fh"] = None if req == "out_of_scope" else P_EXIT_OV[req]
    out["operational_limitations"] = {
        "adjacent_average_population_density_per_km2": float(dens),
        "outdoor_assemblies_within_1km": look["assembly_band"],
        "adjacent_radius_km": out["adjacent_radius_km"],
    }

    if req == "out_of_scope":
        out["compliance_status"] = "out_of_scope"
        out["status"] = "out_of_scope"
        notes.append("resultado 'out of scope' nas Tabelas 8–13 — operação fora da categoria específica "
                     "(ajustar local ou aumentar o SAIL, S.4.8.4(a)(iv)); não é um pass")
        out["unassessed_terms"] = unassessed
        return out

    # Compliance: claimed robustness and/or sourced quantitative P(OV exit). Missing → unassessed, never pass.
    claimed = (c.get("claimed_robustness") or "").strip().lower() or None
    if claimed and claimed not in P_EXIT_OV:
        unassessed.append(f"claimed_robustness '{claimed}' não é low|medium|high")
        claimed = None
    out["claimed_robustness"] = claimed

    p_exit = c.get("p_exit_operational_volume_per_fh")
    sources = dict(c.get("sources") or {})
    p_src = sources.get("p_exit_operational_volume_per_fh") or sources.get("p_exit")
    if p_exit is not None and not p_src:
        unassessed.append("p_exit_operational_volume_per_fh sem source/data (não usar como taxa de fornecedor)")
        p_exit = None  # do not apply unsourced probability
    out["p_exit_operational_volume_per_fh"] = float(p_exit) if p_exit is not None else None

    evidence = (c.get("evidence") or "").strip()
    ev_src = sources.get("claimed_robustness") or sources.get("evidence") or evidence
    if claimed and not ev_src:
        unassessed.append("claimed_robustness sem source/evidência citada")
        claimed_ok = False
    elif claimed:
        claimed_ok = _RANK[claimed] >= _RANK[req]
    else:
        claimed_ok = False

    quant_ok = None
    if out["p_exit_operational_volume_per_fh"] is not None:
        tgt = P_EXIT_OV[req]
        quant_ok = out["p_exit_operational_volume_per_fh"] < tgt or abs(out["p_exit_operational_volume_per_fh"] - tgt) < 1e-15
        notes.append(
            f"P(sair do volume operacional)={out['p_exit_operational_volume_per_fh']:.3g}/FH "
            f"vs alvo Anexo E § E.4 Critério #1 ({req}) {tgt:.0e}/FH"
        )

    if quant_ok is False or (claimed and not claimed_ok and ev_src):
        out["compliance_status"] = "fail"
        out["status"] = "fail"
        if claimed and not claimed_ok:
            notes.append(f"robustez reivindicada '{claimed}' abaixo da exigida '{req}'")
    elif quant_ok is True or (claimed_ok and ev_src):
        out["compliance_status"] = "ok"
        out["status"] = "ok"
        notes.append(f"conformidade com contenção '{req}' (Anexo E § E.4) com evidência citada")
    else:
        out["compliance_status"] = "unassessed"
        out["status"] = "unassessed"
        unassessed.append("evidência de conformidade (claimed_robustness+source ou p_exit com source)")
        notes.append("requisito das Tabelas 8–13 determinado, mas a conformidade Anexo E está unassessed "
                     "(nunca pass sem evidência citada)")

    # High claimed robustness / required high: mention DVR note from AMC (do not auto-pass)
    if req == "high" or (claimed == "high"):
        notes.append("contenção de robustez alta: o AMC prevê DVR EASA para a função de contenção "
                     "(S.2.5(d)) — não verificado automaticamente")

    out["unassessed_terms"] = unassessed
    out["notes"] = notes
    return out
