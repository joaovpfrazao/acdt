"""``acdt uq`` para o domínio aircraft: o modelo é o pipeline L0/L1 (dimensionamento → estabilidade →
aeroelasticidade → desempenho → matriz de verificação), corrido por amostra sobre uma cópia da missão YAML com os
caminhos incertos substituídos. Sem relatório nem ficheiros por amostra. docs/INCERTEZA.md.

* fidelidade: a declarada na missão (por omissão) ou ``handbook`` (mais barata; muda o modelo e fica registado);
* ``skip_stages``: etapas a não correr (p. ex. ``[aeroelasticity]``); os requisitos que delas dependem ficam
  ``nao_avaliado`` nas amostras E na corrida nominal deste estudo (o mesmo modelo nos dois);
* ``workers``: processos em paralelo (cada amostra é independente; AVL/XFOIL usam pastas temporárias próprias).
"""
from __future__ import annotations

import copy
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from acdt.core.sensitivity import distributions as D
from acdt.core.sensitivity.study import Sample, UQSpec, parse_spec, run_study

STAGES = ("sizing+systems", "stability", "aeroelasticity", "performance", "verification")


def _get(d: Mapping[str, Any], path: str) -> Any:
    cur: Any = d
    for p in path.split("."):
        if isinstance(cur, Mapping) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def nominal_of(raw: Mapping[str, Any], path: str) -> float | None:
    """Valor nominal de um caminho: o da missão; para ``assumptions.*`` ausentes, o valor por omissão do domínio."""
    v = _get(raw, path)
    if v is None and path.startswith("assumptions."):
        from .mission import DEFAULT_ASSUMPTIONS

        v = _get({"assumptions": DEFAULT_ASSUMPTIONS}, path)
    if isinstance(v, Mapping):  # requisito {min|max|target: x} ou fator {value: x}
        for k in ("target", "min", "max", "value"):
            if k in v:
                v = v[k]
                break
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def set_path(d: dict[str, Any], path: str, value: float) -> None:
    from acdt.core.sensitivity.oat import _set_path

    parts = path.split(".")
    node = _get(d, ".".join(parts[:-1])) if len(parts) > 1 else d
    leaf = parts[-1]
    if isinstance(node, dict) and isinstance(node.get(leaf), dict) and "value" in node[leaf] \
            and not any(k in node[leaf] for k in ("min", "max", "target")):
        node[leaf]["value"] = value  # fator de calibração {value, group, …}
        return
    _set_path(d, path, value)


def _metrics(res: Any, rows: Sequence[Mapping[str, Any]], result_paths: Mapping[str, str]) -> dict[str, float]:
    from acdt.core.sensitivity.oat import extract_metrics

    m = dict(extract_metrics(res))
    for r in rows:
        v = r.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)):
            m[f"req:{r['id']}"] = float(v)
    if result_paths:
        from acdt.core.verification import json_path

        from .report import to_dict
        dd = to_dict(res)
        for name, pth in result_paths.items():
            try:
                v = json_path(dd, pth)
            except Exception:  # noqa: BLE001 — caminho ausente nesta amostra: sem valor (≠ 0)
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)):
                m[name] = float(v)
    return m


def evaluate_point(raw: Mapping[str, Any], source: str | None, point: Mapping[str, float],
                   opts: Mapping[str, Any]) -> Sample:
    """Uma amostra: missão modificada → pipeline → métricas + estado de cada requisito."""
    return run_point(raw, source, point, opts)[0]


def run_point(raw: Mapping[str, Any], source: str | None, point: Mapping[str, float],
              opts: Mapping[str, Any]) -> tuple[Sample, dict[str, Any] | None]:
    """Como :func:`evaluate_point`, mais a matriz de verificação completa desta corrida."""
    import warnings

    from acdt.core.pipeline import DesignState, get_domain

    from .mission import MissionSpec

    dd = copy.deepcopy(dict(raw))
    if opts.get("fidelity") == "handbook":
        dd.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = "handbook"
    for pth, val in point.items():
        set_path(dd, pth, float(val))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            spec = MissionSpec.from_dict(dd, Path(source) if source else None)
            dom = get_domain("aircraft")
            st = DesignState("aircraft", {"spec": spec, "options": {"no_systems": bool(opts.get("no_systems", True))}})
            skip = set(opts.get("skip_stages") or ())
            for stage in dom.stages:
                if stage.name in skip or stage.name == "report" or st.stopped:
                    continue
                stage.run(st)
            res: Any = st.data.get("result")
            if res is None or res.sizing is None or not res.sizing.converged:
                return Sample(False, message="dimensionamento não convergiu"), None
            mat: dict[str, Any] = st.data.get("verification") or {}
            rows = mat.get("rows") or []
            reqs = {str(r["id"]): {"status": r["status"], "value": r.get("value"), "threshold": r.get("threshold"),
                                   "tolerance": r.get("tolerance")} for r in rows}  # limiar desta corrida (MDO)
            return Sample(True, _metrics(res, rows, opts.get("result_paths") or {}), reqs), (dict(mat) or None)
    except Exception as ex:  # noqa: BLE001 — falha da amostra: contada, nunca vale zero
        return Sample(False, message=f"{type(ex).__name__}: {str(ex)[:200]}"), None


def _star(args: tuple[Mapping[str, Any], str | None, Mapping[str, float], Mapping[str, Any]]) -> Sample:
    return evaluate_point(*args)


class AircraftModel:
    def __init__(self, raw: Mapping[str, Any], source: str | None, opts: Mapping[str, Any]):
        self.raw, self.source, self.opts = raw, source, dict(opts)
        self.n_calls = 0

    def nominal(self, path: str) -> float | None:
        return nominal_of(self.raw, path)

    def run(self, points: Sequence[Mapping[str, float]]) -> list[Sample]:
        self.n_calls += len(points)
        w = int(self.opts.get("workers") or 1)
        args = [(self.raw, self.source, p, self.opts) for p in points]
        if w <= 1 or len(points) <= 1:
            return [_star(a) for a in args]
        with ProcessPoolExecutor(max_workers=w) as ex:
            return list(ex.map(_star, args, chunksize=max(1, len(args) // (4 * w))))

    def requirement_defs(self) -> list[Any]:
        from .mission import MissionSpec
        from .verification_run import traced_requirements

        try:
            return list(traced_requirements(MissionSpec.from_dict(copy.deepcopy(dict(self.raw)),
                                                                  Path(self.source) if self.source else None)))
        except Exception:  # noqa: BLE001
            return []

    def describe(self) -> dict[str, Any]:
        fid = self.opts.get("fidelity") or "como declarada"
        skip = list(self.opts.get("skip_stages") or [])
        return {"domain": "aircraft", "mission": self.source, "fidelity": fid, "skip_stages": skip,
                "workers": int(self.opts.get("workers") or 1),
                "result_metrics": dict(self.opts.get("result_paths") or {}),  # nome → caminho (acdt db add-uq)
                "text": f"pipeline aircraft L0/L1 (`{Path(self.source).name if self.source else '?'}`), fidelidade "
                        f"{fid}" + (f", sem {', '.join(skip)}" if skip else "") + "; um pipeline por amostra"}


def calibration_inputs(raw: Mapping[str, Any], cal: Mapping[str, Any], base: Path) -> tuple[
        list[D.UncertainInput], list[dict[str, Any]]]:
    """Fatores de calibração de alta fidelidade como entradas incertas (``uncertainty.calibration``).

    ``cal``: ``{file: calibration.json | h1_wing_gci.json, factors: [nomes]?}``. Só entram os fatores que a corrida
    determinística **aplica** (``assumptions.calibration.apply`` + filtro ``factor_acceptable``; registos H1 com
    ``decision: nao_aplicar`` nunca). Incerteza = GCI da malha fina (Celik et al., ASME JFE 130 (2008) 078001;
    Roache 1998 — banda de ~95 % com Fs = 1,25) ou U_osc (Stern et al. 2001) quando oscilatório, aplicada como
    uniforme ±GCI·|valor| (PRESSUPOSTO: só o erro de discretização da alta fidelidade; o modelo L1 é determinístico).
    Sem GCI → não propagado e listado (incerteza desconhecida ≠ zero).
    """
    import json

    from .hifi.calibration import APPLICABLE, STRUCTURES_APPLIED, _group_of, factor_acceptable

    ins: list[D.UncertainInput] = []
    exc: list[dict[str, Any]] = []
    f = cal.get("file")
    if not f:
        return ins, [{"name": "calibration", "reason": "uncertainty.calibration sem 'file'"}]
    fp = (base / str(f)) if not Path(str(f)).is_absolute() else Path(str(f))
    try:
        d = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        return ins, [{"name": str(f), "reason": f"não foi possível ler: {ex}"}]
    want = set(cal.get("factors") or [])
    acal = ((raw.get("assumptions") or {}).get("calibration") or {})
    applied = set(acal.get("apply") or [])
    facs: dict[str, dict[str, Any]] = {}
    gci_by_q: dict[str, Any] = d.get("gci") or {}
    if isinstance(d.get("factors"), dict):
        facs = {k: dict(v) for k, v in d["factors"].items()}
    elif isinstance(d.get("factors"), list):  # registo H1 (wing_bl.factor_record)
        for rec in d["factors"]:
            facs[str(rec.get("name"))] = dict(rec)
    for name, fac in facs.items():
        if want and name not in want:
            continue
        path = f"assumptions.calibration.factors.{name}"
        group = str(fac.get("group") or _group_of(name))
        if fac.get("decision") == "nao_aplicar":
            exc.append({"name": name, "path": path, "reason": f"H1: nao_aplicar ({fac.get('invalid_reason', '')})"})
            continue
        ok, why = factor_acceptable(name, fac)
        if not ok:
            exc.append({"name": name, "path": path, "reason": f"fator não aplicável: {why}"})
            continue
        if group not in applied or group not in APPLICABLE or (group == "structures" and name not in STRUCTURES_APPLIED):
            exc.append({"name": name, "path": path, "reason": f"grupo '{group}' não está em "
                                                              "assumptions.calibration.apply (não muda o modelo)"})
            continue
        if fac.get("fidelity") == "ensaio" or isinstance(fac.get("calibration"), Mapping):
            # fator de ensaio (acdt calib, acdt.calib/1): distribuição calibrada N(valor, σ do ajuste)
            sdv = fac.get("sd")
            if sdv is None or not math.isfinite(float(sdv)) or float(sdv) <= 0:
                exc.append({"name": name, "path": path, "reason": "ensaio: σ do ajuste desconhecido, não propagado"})
                continue
            crec = fac.get("calibration") or {}
            ins.append(D.UncertainInput(path=path, dist="normal", params={"mean": float(fac["value"]), "std": float(sdv)},
                                        source=f"{fp.name}: calibração contra ensaio ({crec.get('method', '?')}, "
                                               f"registo {crec.get('record', '?')})" +
                                               (" — DADOS SINTÉTICOS" if fac.get("synthetic") else ""),
                                        pressuposto=bool(fac.get("synthetic")), nominal=float(fac["value"]),
                                        name=name, origin="calibracao",
                                        notes="σ do ajuste (covariância dos parâmetros); válido só na gama de validade"))
            continue
        g = fac.get("gci_fine")
        how = "GCI fina (Celik et al. 2008)"
        q = name[2:] if name.startswith("k_") else name
        if g is None and isinstance(gci_by_q.get(q), Mapping):
            gq = gci_by_q[q]
            g = gq.get("gci_fine")
            if g is None and gq.get("oscillatory") and gq.get("u_osc") is not None:
                g, how = gq["u_osc"], "U_osc oscilatório (Stern et al. 2001)"
        if g is None or not math.isfinite(float(g)):
            exc.append({"name": name, "path": path, "reason": "sem GCI: incerteza desconhecida, não propagado"})
            continue
        v = float(fac["value"])
        hw = abs(float(g) * v)
        if hw <= 0:
            exc.append({"name": name, "path": path, "reason": "GCI nulo: sem incerteza de discretização medida"})
            continue
        ins.append(D.UncertainInput(path=path, dist="uniform", params={"low": v - hw, "high": v + hw},
                                    source=f"{fp.name}: {how} = {100 * float(g):.2f} %", pressuposto=True,
                                    nominal=v, name=name, origin="calibracao",
                                    notes="PRESSUPOSTO: uniforme ±GCI·|valor|; só discretização da alta fidelidade"))
    return ins, exc


def load_uq(mission: str | Path, uq_file: str | Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    p = Path(mission)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if uq_file:
        u = yaml.safe_load(Path(uq_file).read_text(encoding="utf-8")) or {}
        u = u.get("uncertainty", u)
    else:
        u = raw.get("uncertainty")
    if not u:
        raise D.UncertaintySpecError(f"{p}: sem secção 'uncertainty' (ou passe --spec ficheiro.yaml)")
    return raw, dict(u)


def run_uq(mission: str | Path, outdir: str | Path | None = None, *, uq_file: str | Path | None = None,
           overrides: Mapping[str, Any] | None = None, plots: bool = True) -> dict[str, Any]:
    """Missão + ``uncertainty`` → estudo completo (nominal + propagação + P(passa) + Sobol/Morris)."""
    raw, u = load_uq(mission, uq_file)
    ov = dict(overrides or {})
    sens = dict(u.pop("sensitivity", None) or {})
    for kind in ("sobol", "morris"):
        if kind in sens and kind not in u:
            u[kind] = sens[kind]
        if kind in ov:
            if ov[kind] is None:
                u.pop(kind, None)
            else:
                cur = u.get(kind)
                u[kind] = {**(cur if isinstance(cur, Mapping) else {}), **ov[kind]}
    u.update({k: v for k, v in ov.items() if v is not None and k not in ("model", "sobol", "morris")})
    mopts = dict(u.get("model") or {})
    mopts.update({k: v for k, v in ((overrides or {}).get("model") or {}).items() if v is not None})
    if mopts.get("workers") in (None, 0, "auto"):
        mopts["workers"] = max(1, min(8, (os.cpu_count() or 2) - 1))
    mopts["result_paths"] = dict(u.get("result_metrics") or {})
    bad = set(mopts.get("skip_stages") or []) - set(STAGES)
    if bad:
        raise D.UncertaintySpecError(f"skip_stages desconhecidas: {sorted(bad)} (etapas: {STAGES})")
    base = (Path(uq_file) if uq_file else Path(mission)).resolve().parent  # caminhos relativos ao YAML de uq
    extra: list[D.UncertainInput] = []
    exc: list[dict[str, Any]] = []
    if u.get("calibration"):
        extra, exc = calibration_inputs(raw, u["calibration"], base)
    spec: UQSpec = parse_spec(u, lambda path: nominal_of(raw, path), extra, exc)
    model = AircraftModel(raw, str(Path(mission)), mopts)
    nom, nominal_matrix = run_point(raw, str(Path(mission)), {}, mopts)  # mesmo modelo, processo principal
    return run_study(spec, model, outdir=outdir, nominal_matrix=nominal_matrix, nominal_sample=nom, plots=plots)

