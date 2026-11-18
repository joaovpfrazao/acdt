# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Liga o pipeline aircraft (``acdt size``) e a matriz de verificação ao estado de projeto ``acdt.design/1``
(:mod:`acdt.core.design_db`; docs/DADOS.md).

Cada secção de topo do ``result.json`` vai para uma disciplina e um nível. O nível é o que CAPABILITIES.md
declara para o método que a produz; quando a secção declara uma faixa (p. ex. «L0–L1»), fica o nível de baixo
(PRESSUPOSTO: conservador — nunca se declara mais fidelidade do que a garantida), exceto quando a própria corrida
diz qual correu (``aero.fidelity: lowfi`` → L1).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from acdt.core import design_db as D

# secção de result.json → (disciplina, nível, método, referência CAPABILITIES)
SECTION_MAP: dict[str, tuple[str, str, str, str]] = {
    "feasible": ("dimensionamento", "L0", "Raymer/Roskam/Gudmundsson + MDA", "CAPABILITIES §2"),
    "weights": ("dimensionamento", "L0", "Raymer/Roskam/Gudmundsson + MDA", "CAPABILITIES §2"),
    "design_point": ("dimensionamento", "L0", "diagrama de restrições (Raymer Cap. 5; Gudmundsson Cap. 3)",
                     "CAPABILITIES §2"),
    "weight_initial_source": ("dimensionamento", "L0", "Raymer/Roskam/Gudmundsson + MDA", "CAPABILITIES §2"),
    "weight_cross_check": ("massas", "L0", "pesos por componentes (Raymer Cap. 15, Roskam V)", "CAPABILITIES §3"),
    "weight_breakdown": ("massas", "L0", "pesos por componentes (Raymer Cap. 15, Roskam V)", "CAPABILITIES §3"),
    "onboard_bridge": ("dimensionamento", "L0", "fecho onboard (hotel/extração)", "CAPABILITIES §2"),
    "geometry": ("geometria", "L0", "geometria paramétrica do dimensionamento", "CAPABILITIES §2"),
    "aero": ("aerodinamica", "L0", "manual (Raymer Cap. 12, DATCOM)", "CAPABILITIES §4"),
    "aero_lowfi": ("aerodinamica", "L1", "XFOIL/NeuralFoil + AVL (Drela)", "CAPABILITIES §4"),
    "avl_cruise_trim": ("estabilidade", "L1", "AVL (VLM, Drela)", "CAPABILITIES §4/§6"),
    "stability": ("estabilidade", "L1", "Raymer Cap. 16, Etkin & Reid, Nelson + AVL", "CAPABILITIES §6"),
    "dynamics": ("estabilidade", "L1", "modos e qualidades de voo (Etkin & Reid, Nelson, MIL-F-8785C)",
                 "CAPABILITIES §6"),
    "structures": ("estruturas", "L0", "viga/caixão (Megson, Bruhn; NASA SP-8007)", "CAPABILITIES §7"),
    "structures_avl_loading": ("estruturas", "L1", "caixão com carga AVL (Megson, Bruhn)", "CAPABILITIES §7"),
    "wing_box_comparison_kg": ("estruturas", "L0", "caixão resistência vs encurvadura (Megson, Bruhn)",
                               "CAPABILITIES §7"),
    "aeroelasticity": ("aeroelasticidade", "L2", "divergência, reversão, flutter binário, AEER-45 (Wright & Cooper,"
                       " Bisplinghoff) + OpenAeroStruct", "CAPABILITIES §8"),
    "weight_balance": ("massas", "L0", "peso e centragem operacional", "CAPABILITIES §20"),
    "landing_gear": ("trem", "L0", "trem (Raymer Cap. 11; 14 CFR 23.473)", "CAPABILITIES §20"),
    "performance": ("desempenho", "L0", "missão por segmentos (Raymer Cap. 17, Anderson)", "CAPABILITIES §2"),
    "verified_segment_mission": ("desempenho", "L0", "missão por segmentos (Raymer Cap. 17)", "CAPABILITIES §2"),
    "cost": ("custo", "L0", "DAPCA IV / Eastlake (Raymer Cap. 18)", "CAPABILITIES §14"),
    "noise": ("ruido", "L0", "ruído de hélice: Gutin 1936 + Schlegel-King-Mull 1966, ISO 9613-1, IEC 61672-1, "
              "ISO 226", "CAPABILITIES §32r"),
    "systems": ("sistemas", "L0", "seleção de sistemas (hélice, motor, bateria, servos)", "CAPABILITIES §12"),
}
# metadados, listas de mensagens e históricos: ficam no result.json (referenciado pelo SHA-256)
SKIP = {"acdt_version", "name", "requirements", "issues", "checks", "mda_history"}
SOURCE = "acdt size (aircraft)"


def _req_quantities(spec: Any) -> dict[str, dict[str, Any]]:
    from acdt.core import units

    out: dict[str, dict[str, Any]] = {}
    for r in spec.requirements:
        dim = r.type.dimension
        si_unit: str | None
        if dim == "category" or r.sense == "objective":
            si_unit = None
        else:
            from acdt.core.quantities import DIMENSION_SI
            si_unit = DIMENSION_SI.get(dim, units.default_unit(dim)) or "1"
        q: dict[str, Any] = {"value": r.value, "unit": si_unit, "sense": r.sense,
                             "raw": r.raw if isinstance(r.raw, (int, float, str, bool)) or r.raw is None else str(r.raw),
                             "raw_unit": r.unit or None, "source": str(r.trace.get("source", "missao")),
                             "id": r.trace.get("id")}
        name = f"{r.key}.{r.sense}"
        out[name] = q
    return out


def _input_definition(spec: Any) -> dict[str, Any]:
    src = getattr(spec, "source", None)
    d: dict[str, Any] = {"source": None, "input": None, "requirements": _req_quantities(spec)}
    if src and Path(src).is_file():
        import yaml
        from acdt.core.provenance import sha256_file
        d["source"] = {"path": str(src), "sha256": sha256_file(src)}
        try:
            d["input"] = json.loads(json.dumps(yaml.safe_load(Path(src).read_text(encoding="utf-8")), default=str))
        except Exception:  # noqa: BLE001 — a entrada fica referenciada pelo SHA-256
            d["input"] = None
    return d


def results_into_db(db: dict[str, Any], result: Mapping[str, Any], *, spec: Any = None,
                    evidence: str | None = None, evidence_sha256: str | None = None,
                    provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Escreve as secções de um ``result.json`` (``report.to_dict``) nos blocos disciplina × nível."""
    lowfi = False
    if spec is not None:
        lowfi = str(((getattr(spec, "assumptions", {}) or {}).get("aero") or {}).get("fidelity", "")) == "lowfi"
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for key, val in result.items():
        if key in SKIP:
            continue
        disc, lvl, meth, ref = SECTION_MAP.get(key, ("outros", "L0", "(secção não classificada)", ""))
        if key == "aero" and lowfi:
            lvl, meth = "L1", "XFOIL/NeuralFoil + AVL (Drela); aero.fidelity: lowfi"
        g = groups.setdefault((disc, lvl), {"methods": [], "refs": [], "q": {}, "notes": [], "sections": {}})
        g["sections"][key] = meth
        if meth not in g["methods"]:
            g["methods"].append(meth)
        if ref and ref not in g["refs"]:
            g["refs"].append(ref)
        if key not in SECTION_MAP:
            g["notes"].append(f"secção '{key}' sem disciplina declarada em design_db_run.SECTION_MAP")
        if isinstance(val, dict):
            g["q"].update(D.quantities_from_tree(val, key))
        elif D._is_scalar(val):
            g["q"].update(D.quantities_from_tree({key: val}))
    prov = dict(provenance or {})
    for (disc, lvl), g in sorted(groups.items()):
        D.set_results(db, disc, lvl, g["q"], method="; ".join(g["methods"]), references=g["refs"], source=SOURCE,
                      evidence=evidence, evidence_sha256=evidence_sha256, provenance=prov,
                      notes=g["notes"], sections=g["sections"])
    return db


def build(spec: Any, result: Mapping[str, Any], matrix: Mapping[str, Any] | None = None, *,
          evidence: str | None = None, evidence_sha256: str | None = None,
          provenance: Mapping[str, Any] | None = None, base: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Estado de projeto a partir da missão, do result.json e da matriz. ``base``: estado anterior (mantém os
    blocos de outras disciplinas/níveis, p. ex. L3 de verificação, e continua a revisão)."""
    db = D.copy_db(base) if base else D.new(getattr(spec, "name", "unnamed"), "aircraft")
    # os blocos que esta mesma fonte escreveu antes são substituídos (nada obsoleto fica com ar de atual);
    # os de outras fontes (p. ex. L3 de verificação, incerteza) ficam
    for disc in list(db.get("results", {})):
        for lvl in list(db["results"][disc]):
            if db["results"][disc][lvl].get("source") == SOURCE:
                del db["results"][disc][lvl]
        if not db["results"][disc]:
            del db["results"][disc]
    db["name"] = getattr(spec, "name", db.get("name"))
    db["definition"] = _input_definition(spec)
    results_into_db(db, result, spec=spec, evidence=evidence, evidence_sha256=evidence_sha256, provenance=provenance)
    if matrix is not None:
        D.set_verification(db, matrix, evidence="verification_matrix.json")
    return db


def write_state(st: Any) -> dict[str, Any] | None:
    """Etapa do pipeline: monta ``st['design']`` e, com pasta de saída, escreve ``design.json``.

    Um ``design.json`` já existente na pasta é a base (revisão seguinte; blocos de outros níveis mantidos)."""
    spec, res = st["spec"], st.get("result")
    if res is None:
        return None
    out = st["options"].get("output")
    m = st.get("verification") or None
    prov: dict[str, Any] = {}
    if m:
        prov = {"fingerprint": (m.get("provenance") or {}).get("fingerprint")}
    if out and (Path(out) / "result.json").is_file():
        from acdt.core.provenance import sha256_file
        rf = Path(out) / "result.json"
        result = json.loads(rf.read_text(encoding="utf-8"))
        ev, sha = "result.json", sha256_file(rf)
    else:
        from .report import to_dict
        result = json.loads(json.dumps(to_dict(res), default=str))
        ev, sha = None, None
    base = None
    if out and (Path(out) / D.DEFAULT_FILE).is_file():
        try:
            base = D.load(Path(out) / D.DEFAULT_FILE)
        except (ValueError, OSError):
            base = None  # estado anterior inválido: recomeça (a revisão anterior perde-se, fica no git/disco)
    db = build(spec, result, m, evidence=ev, evidence_sha256=sha, provenance=prov, base=base)
    st["design"] = db
    if out:
        D.save(db, Path(out) / D.DEFAULT_FILE)
    else:
        db["revision"] = int(db.get("revision", 0)) + 1
    return db


def build_from_output(mission: str | Path, outdir: str | Path) -> dict[str, Any]:
    """``acdt db build``: missão + pasta já corrida (result.json, verification_matrix.json) → estado."""
    from acdt.core.provenance import sha256_file

    from .mission import MissionSpec
    spec = MissionSpec.from_yaml(mission)
    d = Path(outdir)
    rf = d / "result.json"
    if not rf.is_file():
        raise FileNotFoundError(f"{rf} não existe (corra acdt size … -o {d})")
    result = json.loads(rf.read_text(encoding="utf-8"))
    mf = d / "verification_matrix.json"
    m = json.loads(mf.read_text(encoding="utf-8")) if mf.is_file() else None
    prov = {"fingerprint": (m.get("provenance") or {}).get("fingerprint")} if m else {}
    pf = d / "provenance.json"
    if pf.is_file():
        try:
            from acdt.core.verification import provenance_fingerprint
            prov = {"fingerprint": provenance_fingerprint(json.loads(pf.read_text(encoding="utf-8"))),
                    "file": "provenance.json", "sha256": sha256_file(pf)}
        except (OSError, ValueError):
            pass
    base = D.load(d / D.DEFAULT_FILE) if (d / D.DEFAULT_FILE).is_file() else None
    return build(spec, result, m, evidence="result.json", evidence_sha256=sha256_file(rf), provenance=prov, base=base)


# métrica de acdt.core.sensitivity.oat.extract_metrics → nome da grandeza no estado (mesma origem em report.to_dict)
UQ_METRIC_MAP: dict[str, str] = {
    "W0_kg": "weights.W0_kg",                    # sizing.W0
    "We_kg": "weights.We_kg",                    # sizing.We
    "Wf_kg": "weights.Wfuel_or_battery_kg",      # sizing.Wf
    "E_Wh": "weights.battery_energy_Wh",         # sizing.energy_J / 3600
    "CD0": "aero.CD0",                           # polar.CD0
    "K": "aero.K",                               # polar.K
    "V_cruise_mps": "aero.cruise_speed_m_s",     # res.cruise_speed
    "ws_Pa": "design_point.W_S_N_m2",            # design_point.ws
}


def uq_into_db(db: dict[str, Any], uq_file: str | Path, extra_map: Mapping[str, str] | None = None
               ) -> dict[str, list[str]]:
    """``acdt db add-uq``: percentis de um ``uq.json`` nas grandezas do estado. As métricas declaradas em
    ``uncertainty.result_metrics`` (nome → caminho do result.json, guardado em ``model.result_metrics``) ligam-se
    pelo próprio caminho; ``extra_map`` (``--map nome=caminho``) junta ou corrige ligações."""
    from acdt.core.provenance import sha256_file

    f = Path(uq_file)
    if f.is_dir():
        f = f / "uq.json"
    uq = json.loads(f.read_text(encoding="utf-8"))
    mapping = dict(UQ_METRIC_MAP)
    mapping.update({k: str(v) for k, v in ((uq.get("model") or {}).get("result_metrics") or {}).items()})
    mapping.update(dict(extra_map or {}))
    return D.attach_uq(db, uq, mapping, source=f"acdt uq ({f.name}, sha256 {sha256_file(f)[:12]})")
