# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Registo de calibração ``acdt.calib/1``: fatores ± incerteza, resíduos, gama de validade e decisão.

A decisão ``aplicar``/``nao_aplicar`` é tomada **só** contra critérios de aceitação declarados no estudo
(:data:`CRITERIA`). Sem critérios declarados → ``nao_aplicar``. Regras fixas (não configuráveis): incerteza do
parâmetro conhecida (ν ≥ 1, JᵀWJ não singular), parâmetro fora dos limites de procura, dados não sintéticos
(salvo ``allow_synthetic: true`` declarado, que fica no registo). Um critério que não se consegue avaliar fica
``desconhecido`` e conta como não cumprido (desconhecido ≠ passa).

A aplicação a um ponto de projeto (:func:`applicable_at`) exige, além de ``aplicar``, que **todas** as entradas
da gama de validade (mínimo/máximo dos dados usados) sejam dadas e estejam dentro dela: nunca se aplica fora da
gama nem com a condição em falta.

Exportações: :func:`factors_file` (formato ``calibration.json`` de ``assumptions.calibration.file``, com
``decision``, ``sd`` e ``validity``), :func:`overlay` (substituição de caminhos ``assumptions.…``),
:func:`uq_inputs` (entradas normais + correlações de postos para ``acdt uq``) e :func:`to_design_db`
(bloco ``results.calibracao.<nível>`` com ``fidelity: ensaio``).
"""
from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from . import fitting as F
from .ingest import Dataset

SCHEMA = "acdt.calib/1"
DECISIONS = ("aplicar", "nao_aplicar")
CRITERIA = ("min_points", "max_rel_sd", "max_chi2_red", "max_rmse", "band", "require_instrument_uncertainty",
            "max_prior_shift_sigma", "allow_synthetic")
LEVELS = ("L0", "L1", "L2", "L3")


def _f(x: Any) -> float | None:
    if x is None:
        return None
    v = float(x)
    return v if math.isfinite(v) else None


def _crit(name: str, status: str, detail: str, applies_to: str = "*") -> dict[str, Any]:
    return {"criterion": name, "status": status, "detail": detail, "applies_to": applies_to}


def decide(spec: F.ModelSpec, res: F.FitResult, acceptance: Mapping[str, Any], synthetic: bool
           ) -> tuple[dict[str, str], dict[str, list[str]], list[dict[str, Any]]]:
    """Decisão por parâmetro. Devolve (decisão, razões, critérios avaliados)."""
    acc = dict(acceptance or {})
    unknown = set(acc) - set(CRITERIA)
    if unknown:
        raise F.CalibrationError(f"critérios de aceitação desconhecidos {sorted(unknown)} (use {CRITERIA})")
    sd = res.sd()
    crits: list[dict[str, Any]] = []
    reasons: dict[str, list[str]] = {q: [] for q in res.names}

    def per_param(v: Any, name: str) -> Any:
        return v.get(name) if isinstance(v, Mapping) else v

    if not [k for k in acc if k != "allow_synthetic"]:
        for q in res.names:
            reasons[q].append("sem critérios de aceitação declarados")
    if synthetic:
        if acc.get("allow_synthetic"):
            crits.append(_crit("allow_synthetic", "passa", "dados SINTÉTICOS aceites por declaração explícita "
                                                           "(só demonstração; nunca um projeto real)"))
        else:
            crits.append(_crit("dados_reais", "falha", "dados sintéticos: não se aplicam a um projeto"))
            for q in res.names:
                reasons[q].append("dados sintéticos")
    if "min_points" in acc:
        ok = res.n >= int(acc["min_points"])
        crits.append(_crit("min_points", "passa" if ok else "falha", f"n = {res.n} (mín. {acc['min_points']})"))
        if not ok:
            for q in res.names:
                reasons[q].append(f"n = {res.n} < {acc['min_points']}")
    if acc.get("require_instrument_uncertainty"):
        ok = res.sigma_source == "instrumento"
        crits.append(_crit("require_instrument_uncertainty", "passa" if ok else "falha",
                           f"σ: {res.sigma_source}"))
        if not ok:
            for q in res.names:
                reasons[q].append("sem incerteza de instrumento declarada")
    if "max_chi2_red" in acc:
        if res.chi2_red is None:
            st, det = "desconhecido", "χ²/ν não calculável (sem σ de instrumento ou ν < 1)"
        else:
            st = "passa" if res.chi2_red <= float(acc["max_chi2_red"]) else "falha"
            det = f"χ²/ν = {res.chi2_red:.3g} (máx. {acc['max_chi2_red']})"
        crits.append(_crit("max_chi2_red", st, det))
        if st != "passa":
            for q in res.names:
                reasons[q].append(f"max_chi2_red: {det}")
    if "max_rmse" in acc:
        ok = res.rmse <= float(acc["max_rmse"])
        crits.append(_crit("max_rmse", "passa" if ok else "falha", f"RMSE = {res.rmse:.4g} (máx. {acc['max_rmse']}, "
                                                                     f"unidade da saída)"))
        if not ok:
            for q in res.names:
                reasons[q].append(f"RMSE {res.rmse:.4g} > {acc['max_rmse']}")
    for i, q in enumerate(res.names):
        if "max_rel_sd" in acc and per_param(acc["max_rel_sd"], q) is not None:
            lim = float(per_param(acc["max_rel_sd"], q))
            if sd is None or not math.isfinite(sd[i]) or res.theta[i] == 0:
                st, det = "desconhecido", "incerteza do parâmetro desconhecida"
            else:
                rel = float(sd[i] / abs(res.theta[i]))
                st, det = ("passa" if rel <= lim else "falha"), f"σ/|θ| = {rel:.3g} (máx. {lim})"
            crits.append(_crit("max_rel_sd", st, det, q))
            if st != "passa":
                reasons[q].append(f"max_rel_sd: {det}")
        if "band" in acc and per_param(acc["band"], q) is not None:
            lo, hi = (float(v) for v in per_param(acc["band"], q))
            ok = lo <= float(res.theta[i]) <= hi
            crits.append(_crit("band", "passa" if ok else "falha", f"{res.theta[i]:.5g} em [{lo:g}, {hi:g}]", q))
            if not ok:
                reasons[q].append(f"{res.theta[i]:.5g} fora da banda [{lo:g}, {hi:g}]")
        if "max_prior_shift_sigma" in acc and res.discrepancy is not None:
            lim = float(acc["max_prior_shift_sigma"])
            sh = res.discrepancy["prior_shift_sigma"][i]
            ok = sh <= lim
            crits.append(_crit("max_prior_shift_sigma", "passa" if ok else "falha", f"|θ−μ₀|/σ₀ = {sh:.3g}", q))
            if not ok:
                reasons[q].append(f"desvio ao prior {sh:.3g}σ > {lim}")
        # regras fixas
        if sd is None or not math.isfinite(sd[i]):
            reasons[q].append("incerteza do parâmetro desconhecida")
        if q in res.at_bound:
            reasons[q].append("no limite de procura")
    dec = {q: ("aplicar" if not reasons[q] else "nao_aplicar") for q in res.names}
    return dec, reasons, crits


def build_record(study: Mapping[str, Any], spec: F.ModelSpec, ds: Dataset, res: F.FitResult,
                 base: Path | None = None) -> dict[str, Any]:
    acc = dict(study.get("acceptance") or {})
    dec, why, crits = decide(spec, res, acc, ds.synthetic)
    sd, ci, corr = res.sd(), res.ci95(), res.corr()
    params: dict[str, Any] = {}
    for i, q in enumerate(spec.parameters):
        params[q.name] = {
            "value": float(res.theta[i]), "unit": q.unit,
            "sd": None if sd is None else _f(sd[i]), "ci95": None if ci is None else [_f(ci[i, 0]), _f(ci[i, 1])],
            "nominal": q.nominal, "initial": q.initial, "bounds": [_f(q.lower), _f(q.upper)],
            "shift_sigma": (None if (q.nominal is None or sd is None or not sd[i]) else
                            _f((res.theta[i] - q.nominal) / sd[i])),
            "prior": None if q.prior_mean is None else {"mean": q.prior_mean, "sd": q.prior_sd,
                                                        "source": q.prior_source},
            "target": q.target, "factor": q.factor, "group": q.group, "what": q.what,
            "decision": dec[q.name], "reasons": why[q.name]}
    validity = {k: [float(np.min(v)), float(np.max(v))] for k, v in res.x.items()}
    vunits = {k: spec.units.get(k) or ds.channel(k).unit for k in res.x}
    rows = []
    for j in range(res.n):
        r: dict[str, Any] = {k: float(v[j]) for k, v in res.x.items()}
        r.update({"y": float(res.y[j]), "eta": float(res.eta[j]), "residual": float(res.residuals[j])})
        if res.sigma is not None:
            r["sigma"] = float(res.sigma[j])
            r["residual_norm"] = float(res.residuals[j] / res.sigma[j]) if res.sigma[j] > 0 else None
        rows.append(r)
    overall = "aplicar" if all(v == "aplicar" for v in dec.values()) else (
        "parcial" if any(v == "aplicar" for v in dec.values()) else "nao_aplicar")
    lvl = str(study.get("level", "L1"))
    if lvl not in LEVELS:
        raise F.CalibrationError(f"level '{lvl}' não é um de {LEVELS} (nível do modelo calibrado)")
    return {
        "schema": SCHEMA, "name": str(study.get("name") or ds.name), "discipline": str(study.get("discipline", "")),
        "level": lvl, "fidelity": "ensaio",
        "method": {"name": res.method, "reference": F.REF_KOH if res.method == "koh" else F.REF_WLS,
                   "expr": spec.expr, "output": spec.output, "units": dict(spec.units), "constants": spec.constants,
                   "sigma_source": res.sigma_source, "notes": res.notes},
        "data": ds.to_dict(), "synthetic": ds.synthetic,
        "fit": {"n": res.n, "n_dropped": res.n_dropped, "dof": res.dof, "chi2": res.chi2, "chi2_red": res.chi2_red,
                "birge_factor": res.birge_factor, "rmse": res.rmse, "identifiable": res.identifiable,
                "at_bound": res.at_bound, "output_unit": spec.units.get(spec.output) or ds.channel(spec.output).unit},
        "parameters": params,
        "covariance": None if res.cov is None else res.cov.tolist(),
        "correlation": None if corr is None else corr.tolist(),
        "discrepancy": res.discrepancy,
        "validity": {"ranges": validity, "units": vunits, "conditions": ds.meta.get("conditions") or {},
                     "rule": "aplica-se só com todas as entradas dadas e dentro de [mín, máx] dos dados usados"},
        "acceptance": acc, "criteria": crits, "decision": overall,
        "residuals": rows,
    }


# ------------------------------------------------------------------------------------------- aplicação
def _split_value(v: Any, unit: str | None, where: str) -> float:
    from acdt.core.quantities import _split, convert

    mag, u = _split(v, where)
    if u is None or unit is None or u == unit:
        return mag
    return convert(mag, u, unit, where)


def applicable_at(rec: Mapping[str, Any], param: str, at: Mapping[str, Any] | None) -> tuple[bool, list[str]]:
    """O parâmetro pode ser aplicado no ponto ``at`` (``{entrada: valor | "texto com unidade"}``)?"""
    p = rec["parameters"][param]
    why: list[str] = []
    if p["decision"] != "aplicar":
        why.append("decisão nao_aplicar: " + "; ".join(p["reasons"]))
    rng = (rec.get("validity") or {}).get("ranges") or {}
    units = (rec.get("validity") or {}).get("units") or {}
    at = dict(at or {})
    for k, (lo, hi) in rng.items():
        if k not in at:
            why.append(f"condição '{k}' do ponto de aplicação não dada (desconhecida ≠ dentro da gama)")
            continue
        v = _split_value(at[k], units.get(k), k)
        tol = 1e-9 * max(1.0, abs(lo), abs(hi))
        if not (lo - tol <= v <= hi + tol):
            why.append(f"{k} = {v:.6g} fora da gama de validade [{lo:.6g}, {hi:.6g}] {units.get(k) or ''}".rstrip())
    return (not why), why


def factors_file(rec: Mapping[str, Any], at: Mapping[str, Any] | None, group_of: Any = None,
                 source_path: str | None = None) -> dict[str, Any]:
    """Fatores (parâmetros com ``factor``) no formato de ``assumptions.calibration.file``. Fatores não aplicáveis
    no ponto ficam com ``valid: false`` e ``decision: nao_aplicar`` (o carregador recusa-os)."""
    out: dict[str, Any] = {"design": rec["name"], "factors": {}, "sources": {"calibracao": source_path or rec["name"],
                                                                            "schema": SCHEMA},
                           "note": "fatores de ensaio (acdt calib); só aplicados com o grupo em "
                                   "assumptions.calibration.apply e decision aplicar no ponto dado"}
    for name, p in rec["parameters"].items():
        fname = p.get("factor")
        if not fname:
            continue
        ok, why = applicable_at(rec, name, at)
        grp = p.get("group") or (group_of(fname) if group_of else None)
        out["factors"][fname] = {
            "group": grp, "value": p["value"], "sd": p["sd"], "ci95": p["ci95"], "valid": ok,
            "decision": "aplicar" if ok else "nao_aplicar", "invalid_reason": "; ".join(why) if why else None,
            "validity": rec["validity"]["ranges"], "validity_units": rec["validity"]["units"],
            "fidelity": "ensaio", "synthetic": rec["synthetic"], "what": p.get("what") or name,
            "calibration": {"record": source_path or rec["name"], "parameter": name, "method": rec["method"]["name"]}}
    return out


def overlay(rec: Mapping[str, Any], at: Mapping[str, Any] | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Substituições de caminhos (``target``) para os parâmetros aplicáveis no ponto; e a lista dos recusados."""
    tree: dict[str, Any] = {}
    refused: list[dict[str, Any]] = []
    for name, p in rec["parameters"].items():
        tgt = p.get("target")
        if not tgt:
            continue
        ok, why = applicable_at(rec, name, at)
        if not ok:
            refused.append({"parameter": name, "target": tgt, "reasons": why})
            continue
        node = tree
        parts = str(tgt).split(".")
        for k in parts[:-1]:
            node = node.setdefault(k, {})
        node[parts[-1]] = p["value"]
    return tree, refused


def spearman_from_pearson(rho: float) -> float:
    """Correlação de postos de uma normal bivariada: ρ_S = (6/π)·asin(ρ/2) (Pearson 1907; Kruskal, JASA 53
    (1958) 814–861)."""
    return 6.0 / math.pi * math.asin(rho / 2.0)


def uq_inputs(rec: Mapping[str, Any], source_path: str | None = None, only_applied: bool = True
              ) -> dict[str, Any]:
    """Fragmento ``uncertainty`` para ``acdt uq``: N(valor, sd) por parâmetro com ``target`` ou ``factor``
    (caminho ``assumptions.calibration.factors.<fator>``) e correlações de postos pela covariância."""
    names = list(rec["parameters"])
    inputs, idx = [], []
    src = f"acdt.calib/1 {source_path or rec['name']} ({rec['method']['name']}, n = {rec['fit']['n']})"
    excluded = []
    for i, n in enumerate(names):
        p = rec["parameters"][n]
        path = p.get("target") or (f"assumptions.calibration.factors.{p['factor']}" if p.get("factor") else None)
        if not path:
            continue
        if p["sd"] is None:
            excluded.append({"parameter": n, "reason": "incerteza desconhecida: não propagada"})
            continue
        if only_applied and p["decision"] != "aplicar":
            excluded.append({"parameter": n, "reason": "nao_aplicar: o modelo determinístico não o usa"})
            continue
        d: dict[str, Any] = {"path": path, "dist": "normal", "mean": p["value"], "std": p["sd"], "source": src}
        lo, hi = p["bounds"]
        if lo is not None:
            d["low"] = lo
        if hi is not None:
            d["high"] = hi
        inputs.append(d)
        idx.append(i)
    cors = []
    C = rec.get("correlation")
    if C is not None:
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                r = float(C[idx[a]][idx[b]])
                if abs(r) > 1e-3:
                    cors.append({"a": inputs[a]["path"], "b": inputs[b]["path"], "rho": round(spearman_from_pearson(r), 6),
                                 "source": f"{src}: correlação da covariância do ajuste (ρ = {r:.4f} → postos)"})
    return {"inputs": inputs, "correlations": cors, "excluded": excluded}


def to_design_db(db: dict[str, Any], rec: Mapping[str, Any], evidence: str | None = None,
                 evidence_sha256: str | None = None) -> dict[str, Any]:
    """Junta o registo ao estado de projeto: bloco ``results.calibracao.<nível>`` (``fidelity: ensaio``), uma
    grandeza ``<registo>.<parâmetro>`` com a incerteza (desvio-padrão) e ``<registo>.decisao.<parâmetro>``."""
    from acdt.core import design_db as DDB

    lvl = rec["level"]
    old = ((db.get("results") or {}).get("calibracao") or {}).get(lvl) or {}
    qs: dict[str, Any] = dict(old.get("quantities") or {})
    pre = rec["name"]
    for k in [k for k in qs if k.startswith(pre + ".")]:
        del qs[k]
    src = f"acdt calib ({rec['method']['name']}, dados {rec['data']['name']}"
    src += ", SINTÉTICOS)" if rec["synthetic"] else ")"
    for n, p in rec["parameters"].items():
        unc = None
        if p["sd"] is not None:
            unc = {"kind": "desvio_padrao", "sd": float(p["sd"]), "source": src, "n": int(rec["fit"]["n"])}
        qs[f"{pre}.{n}"] = DDB.quantity(p["value"], p.get("unit") or "1", uncertainty=unc, source=src)
        qs[f"{pre}.decisao.{n}"] = DDB.quantity(p["decision"], None)
    qs[f"{pre}.n"] = DDB.quantity(rec["fit"]["n"], "1")
    qs[f"{pre}.rmse"] = DDB.quantity(rec["fit"]["rmse"], rec["fit"].get("output_unit"))
    if rec["fit"].get("chi2_red") is not None:
        qs[f"{pre}.chi2_red"] = DDB.quantity(rec["fit"]["chi2_red"], "1")
    refs = sorted(set(list(old.get("references") or []) + [rec["method"]["reference"]]))
    notes = [n for n in (old.get("notes") or []) if not str(n).startswith(pre + ":")]
    notes.append(f"{pre}: decisão {rec['decision']}; validade {json.dumps(rec['validity']['ranges'])}")
    return DDB.set_results(db, "calibracao", lvl, qs, method="calibração contra ensaio (acdt.calib/1)",
                           references=refs, source="ensaio", evidence=evidence, evidence_sha256=evidence_sha256,
                           notes=notes, fidelity="ensaio")


# ------------------------------------------------------------------------------------------------ relatórios
def residuals_csv(rec: Mapping[str, Any]) -> str:
    rows = rec.get("residuals") or []
    if not rows:
        return ""
    cols = list(rows[0])
    s = io.StringIO()
    w = csv.DictWriter(s, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return s.getvalue()


def _g(x: Any, fmt: str = ".5g") -> str:
    if x is None:
        return "desconhecido"
    if isinstance(x, (int, float)):
        return format(x, fmt)
    return str(x)


def to_markdown(rec: Mapping[str, Any]) -> str:
    L = [f"# Calibração `{rec['name']}` ({rec['discipline'] or '—'}, {rec['level']}, fidelidade {rec['fidelity']})",
         ""]
    if rec["synthetic"]:
        L += ["> **DADOS SINTÉTICOS** — demonstração do método; não é um ensaio real.", ""]
    d = rec["data"]
    meta = d.get("meta") or {}
    L += [f"Dados: `{d['name']}` ({d['format']}, {d['n_rows']} linhas), origem: {meta.get('source')}; data: "
          f"{meta.get('date') or 'desconhecida'}; tipo {meta.get('kind')}.",
          f"Ficheiro: `{(d.get('file') or {}).get('path', '—')}` sha256 `{str((d.get('file') or {}).get('sha256', '—'))[:16]}…`",
          "", f"Modelo: `{rec['method']['output']} = {rec['method']['expr']}`; método **{rec['method']['name']}** "
              f"({rec['method']['reference']}). σ: {rec['method']['sigma_source']}.", ""]
    f = rec["fit"]
    L += [f"n = {f['n']} (descartados {f['n_dropped']}), ν = {f['dof']}, RMSE = {_g(f['rmse'])} "
          f"{f.get('output_unit') or ''}, χ²/ν = {_g(f['chi2_red'], '.3g')}.", "",
          "| Parâmetro | Valor | σ | IC 95 % | Nominal | Desvio (σ) | Decisão | Razões |",
          "|---|---|---|---|---|---|---|---|"]
    for n, p in rec["parameters"].items():
        ci = "desconhecido" if not p["ci95"] else f"[{_g(p['ci95'][0])}, {_g(p['ci95'][1])}]"
        L.append(f"| {n} | {_g(p['value'])} | {_g(p['sd'], '.3g')} | {ci} | {_g(p['nominal'])} | "
                 f"{_g(p['shift_sigma'], '.2f')} | **{p['decision']}** | {'; '.join(p['reasons']) or '—'} |")
    L += ["", "Critérios de aceitação:", ""]
    L += [f"- {c['criterion']} ({c['applies_to']}): **{c['status']}** — {c['detail']}" for c in rec["criteria"]] or [
        "- nenhum declarado → nao_aplicar"]
    L += ["", "Gama de validade (dados usados):", ""]
    for k, (lo, hi) in rec["validity"]["ranges"].items():
        L.append(f"- {k}: [{lo:.6g}, {hi:.6g}] {rec['validity']['units'].get(k) or ''}")
    if rec.get("discrepancy"):
        dd = rec["discrepancy"]
        L += ["", f"Discrepância δ(x): σ_δ = {_g(dd['sd'], '.3g')}, ℓ = {_g(dd['length_scale_norm'], '.3g')} "
                  f"(normalizado), RMS de δ nos dados = {_g(dd['mean_at_data_rms'], '.3g')}."]
    if rec["method"]["notes"]:
        L += ["", "Notas:", ""] + [f"- {n}" for n in rec["method"]["notes"]]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------- estudo YAML
def load_study(path: str | Path) -> tuple[dict[str, Any], Path]:
    import yaml

    p = Path(path)
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return dict(d.get("calibration", d)), p.resolve().parent


def dataset_for(study: Mapping[str, Any], base: Path) -> Dataset:
    from . import ingest

    dd = study.get("data") or {}
    if not dd.get("file"):
        raise F.CalibrationError("data.file em falta")
    fp = Path(str(dd["file"]))
    fp = fp if fp.is_absolute() else base / fp
    meta = dd.get("meta")
    if isinstance(meta, str) and not Path(meta).is_absolute():
        meta = str(base / meta)
    ds = ingest.load(fp, meta, topics=dd.get("topics"))
    if dd.get("where"):
        ds = ds.where(**{str(k): float(v) for k, v in dd["where"].items()})
        if ds.n == 0:
            raise F.CalibrationError(f"data.where {dd['where']} não deixa nenhuma linha")
    return ds


def run_study(path: str | Path, outdir: str | Path | None = None) -> dict[str, Any]:
    """Lê o estudo, ingere os dados, ajusta, decide e (com ``outdir``) escreve ``calibration_record.json``,
    ``calibration.md`` e ``residuals.csv`` com o registo de proveniência."""
    from acdt.core import provenance as P

    study, base = load_study(path)
    ds = dataset_for(study, base)
    spec = F.ModelSpec.from_dict(study)
    res = F.fit(spec, ds)
    rec = build_record(study, spec, ds, res, base)
    rec["study"] = P.hash_input(path)
    if outdir is not None:
        o = Path(outdir)
        o.mkdir(parents=True, exist_ok=True)
        (o / "calibration_record.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        (o / "calibration.md").write_text(to_markdown(rec), encoding="utf-8")
        (o / "residuals.csv").write_text(residuals_csv(rec), encoding="utf-8")
        P.note_output(o, inputs=[path] + ([ds.file["path"]] if ds.file else []), entry_point="acdt calib fit")
    return rec


def load_record(path: str | Path) -> dict[str, Any]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if d.get("schema") != SCHEMA:
        raise F.CalibrationError(f"{path}: não é um registo {SCHEMA}")
    return dict(d)


def parse_at(items: Sequence[str]) -> dict[str, Any]:
    """``["Re=3e5", "V=30 m/s"]`` → ``{"Re": "3e5", "V": "30 m/s"}``."""
    out: dict[str, Any] = {}
    for s in items or []:
        if "=" not in s:
            raise F.CalibrationError(f"--at '{s}': esperado nome=valor")
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out
