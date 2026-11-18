"""Entradas incertas declaradas (camada de incerteza, docs/INCERTEZA.md).

Cada entrada incerta liga um **caminho** de parâmetro (``assumptions.aero.cfe``, ``requirements.payload_mass``,
``assumptions.calibration.factors.k_clmax`` …) a uma distribuição e a uma **origem** obrigatória. Sem origem, a
entrada tem de vir marcada como ``pressuposto`` com a justificação escrita; nunca há entradas sem rasto.

Distribuições (marginais, transformação pela função quantil, Devroye 1986 Cap. 2):

* ``normal`` — ``mean`` (omissão: o valor nominal do caminho) e ``std`` ou ``cv``; ``low``/``high`` truncam por
  corte (clip) e ficam registados;
* ``lognormal`` — X = exp(μ + σZ); ``median`` ou ``mean`` (omissão: nominal = média) e ``cv`` ou ``sigma_ln``;
  σ² = ln(1 + cv²), μ = ln(média) − σ²/2 (Ang & Tang 2007, Sec. 3.2.3);
* ``uniform`` — ``low``/``high`` ou ``rel`` (± fração do nominal);
* ``triangular`` — ``low``/``high``/``mode`` (``mode`` por omissão = nominal), ou ``rel``;
* ``interval`` — só ``low``/``high`` (ou ``rel``), **sem** distribuição: incerteza epistémica. Na propagação entra
  num ciclo exterior (caixa de probabilidade, Ferson et al. 2003 SAND2002-4015; Oberkampf & Roy 2010 Cap. 13):
  os resultados saem como [mínimo, máximo] sobre os extremos do intervalo. Na sensibilidade global (Sobol/Morris)
  o intervalo é varrido uniformemente — é rastreio da influência, não uma probabilidade.

Correlações (opcionais): coeficientes de correlação de **postos** (Spearman) impostos pelo método de Iman & Conover,
Commun. Statist. Simul. Comput. 11 (1982) 311–334 — preserva exatamente as marginais e a estratificação do LHS.
Amostragem: Monte Carlo i.i.d. ou hipercubo latino (McKay, Beckman & Conover 1979). Semente sempre explícita.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from .monte_carlo import _lhs_unit, _norm_ppf

Array = npt.NDArray[np.float64]

DISTRIBUTIONS = ("normal", "lognormal", "uniform", "triangular", "interval")
_ALIASES = {"gauss": "normal", "gaussian": "normal", "lognorm": "lognormal", "log-normal": "lognormal",
            "u": "uniform", "triang": "triangular", "tri": "triangular", "intervalo": "interval"}
REF = ("McKay, Beckman & Conover, Technometrics 21 (1979) 239–245 (LHS); Iman & Conover, Commun. Statist. "
       "Simul. Comput. 11 (1982) 311–334 (correlação de postos); Ang & Tang, Probability Concepts in Engineering, "
       "2.ª ed., Wiley 2007 (lognormal); Ferson et al., SAND2002-4015 (2003) e Oberkampf & Roy, Verification and "
       "Validation in Scientific Computing, CUP 2010, Cap. 13 (intervalos / caixas de probabilidade)")
U_CLIP = 1e-12  # quantis 0 e 1 das distribuições ilimitadas


class UncertaintySpecError(ValueError):
    pass


@dataclass(frozen=True)
class UncertainInput:
    """Uma entrada incerta já resolvida (parâmetros numéricos explícitos)."""

    path: str
    dist: str
    params: Mapping[str, float]
    source: str
    pressuposto: bool = False
    nominal: float | None = None
    unit: str = ""
    name: str = ""
    notes: str = ""
    origin: str = "utilizador"  # utilizador | calibracao

    @property
    def label(self) -> str:
        return self.name or self.path

    @property
    def epistemic(self) -> bool:
        return self.dist == "interval"

    def bounds(self) -> tuple[float, float] | None:
        """Suporte finito (uniform/triangular/interval ou normal truncada); None se ilimitado."""
        p = self.params
        if "low" in p and "high" in p:
            return float(p["low"]), float(p["high"])
        return None

    def ppf(self, u: Array) -> Array:
        """Função quantil (u ∈ (0,1) → valor físico)."""
        p = self.params
        u = np.asarray(u, dtype=float)
        if self.dist in ("uniform", "interval"):
            return np.asarray(p["low"] + u * (p["high"] - p["low"]), dtype=float)
        if self.dist == "triangular":
            lo, hi, mo = p["low"], p["high"], p["mode"]
            fc = (mo - lo) / (hi - lo)
            out = np.empty_like(u)
            left = u < fc
            out[left] = lo + np.sqrt(u[left] * (hi - lo) * (mo - lo))
            out[~left] = hi - np.sqrt((1 - u[~left]) * (hi - lo) * (hi - mo))
            return out
        z = np.asarray(_norm_ppf(np.clip(u, U_CLIP, 1 - U_CLIP)), dtype=float)
        if self.dist == "normal":
            x = p["mean"] + p["std"] * z
            if "low" in p:
                x = np.maximum(x, p["low"])
            if "high" in p:
                x = np.minimum(x, p["high"])
            return np.asarray(x, dtype=float)
        if self.dist == "lognormal":
            return np.asarray(np.exp(p["mu_ln"] + p["sigma_ln"] * z), dtype=float)
        raise UncertaintySpecError(f"{self.path}: distribuição '{self.dist}' desconhecida")

    def mean(self) -> float:
        p = self.params
        if self.dist in ("uniform", "interval"):
            return 0.5 * (p["low"] + p["high"])
        if self.dist == "triangular":
            return (p["low"] + p["high"] + p["mode"]) / 3.0
        if self.dist == "normal":
            return float(p["mean"])
        return math.exp(p["mu_ln"] + 0.5 * p["sigma_ln"] ** 2)

    def describe(self) -> str:
        p = self.params
        if self.dist == "normal":
            s = f"N(μ={p['mean']:.6g}, σ={p['std']:.4g})"
            if "low" in p or "high" in p:
                s += f" cortada a [{p.get('low', -math.inf):.6g}, {p.get('high', math.inf):.6g}]"
            return s
        if self.dist == "lognormal":
            return f"LN(mediana={math.exp(p['mu_ln']):.6g}, σ_ln={p['sigma_ln']:.4g})"
        if self.dist == "triangular":
            return f"Tri({p['low']:.6g}, {p['mode']:.6g}, {p['high']:.6g})"
        if self.dist == "uniform":
            return f"U({p['low']:.6g}, {p['high']:.6g})"
        return f"intervalo [{p['low']:.6g}, {p['high']:.6g}] (sem distribuição)"

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "name": self.label, "dist": self.dist, "params": dict(self.params),
                "describe": self.describe(), "source": self.source, "pressuposto": self.pressuposto,
                "nominal": self.nominal, "unit": self.unit, "notes": self.notes, "origin": self.origin}


def _f(d: Mapping[str, Any], k: str, path: str) -> float:
    try:
        v = float(d[k])
    except (TypeError, ValueError) as ex:
        raise UncertaintySpecError(f"{path}: '{k}' tem de ser numérico") from ex
    if not math.isfinite(v):
        raise UncertaintySpecError(f"{path}: '{k}' não é finito")
    return v


def parse_input(d: Mapping[str, Any], nominal: float | None = None) -> UncertainInput:
    """Valida e resolve uma entrada declarada em YAML. ``nominal`` = valor do caminho na missão (se existir)."""
    path = str(d.get("path") or d.get("param") or d.get("name") or "").strip()
    if not path:
        raise UncertaintySpecError("entrada incerta sem 'path'")
    dist = str(d.get("dist") or d.get("distribution") or "").lower().strip()
    dist = _ALIASES.get(dist, dist)
    if dist not in DISTRIBUTIONS:
        raise UncertaintySpecError(f"{path}: 'dist' tem de ser um de {DISTRIBUTIONS} (recebido '{dist}')")
    src = str(d.get("source") or "").strip()
    pres_raw = d.get("pressuposto")
    pres = bool(pres_raw)
    if not src and not (isinstance(pres_raw, str) and pres_raw.strip()):
        raise UncertaintySpecError(
            f"{path}: falta 'source' (referência ou dados) — ou declare 'pressuposto: \"<justificação>\"'")
    if not src:
        src = f"PRESSUPOSTO: {str(pres_raw).strip()}"
    elif isinstance(pres_raw, str) and pres_raw.strip():
        src = f"{src}; PRESSUPOSTO: {pres_raw.strip()}"
    nom = nominal
    if "nominal" in d:
        nom = _f(d, "nominal", path)
    params: dict[str, float] = {}

    def need_nominal(what: str) -> float:
        if nom is None:
            raise UncertaintySpecError(f"{path}: '{what}' relativo precisa de valor nominal (o caminho não existe "
                                       f"na missão; declare 'nominal')")
        return float(nom)

    if dist in ("uniform", "interval", "triangular"):
        if "rel" in d:
            r = _f(d, "rel", path)
            n0 = need_nominal("rel")
            params["low"], params["high"] = n0 - abs(r * n0), n0 + abs(r * n0)
        else:
            if "low" not in d or "high" not in d:
                raise UncertaintySpecError(f"{path}: {dist} precisa de 'low' e 'high' (ou 'rel')")
            params["low"], params["high"] = _f(d, "low", path), _f(d, "high", path)
        if not params["high"] > params["low"]:
            raise UncertaintySpecError(f"{path}: intervalo degenerado [{params['low']}, {params['high']}]")
        if dist == "triangular":
            mo = _f(d, "mode", path) if "mode" in d else need_nominal("mode")
            if not params["low"] <= mo <= params["high"]:
                raise UncertaintySpecError(f"{path}: moda {mo} fora de [{params['low']}, {params['high']}]")
            params["mode"] = mo
    elif dist == "normal":
        mu = _f(d, "mean", path) if "mean" in d else need_nominal("mean")
        if "std" in d:
            sd = _f(d, "std", path)
        elif "cv" in d:
            sd = abs(_f(d, "cv", path) * mu)
        else:
            raise UncertaintySpecError(f"{path}: normal precisa de 'std' ou 'cv'")
        if not sd > 0:
            raise UncertaintySpecError(f"{path}: desvio-padrão tem de ser > 0")
        params["mean"], params["std"] = mu, sd
        for k in ("low", "high"):
            if k in d:
                params[k] = _f(d, k, path)
    else:  # lognormal
        if "sigma_ln" in d:
            s = _f(d, "sigma_ln", path)
        elif "cv" in d:
            s = math.sqrt(math.log1p(_f(d, "cv", path) ** 2))
        else:
            raise UncertaintySpecError(f"{path}: lognormal precisa de 'cv' ou 'sigma_ln'")
        if not s > 0:
            raise UncertaintySpecError(f"{path}: σ_ln tem de ser > 0")
        if "median" in d:
            med = _f(d, "median", path)
            if med <= 0:
                raise UncertaintySpecError(f"{path}: mediana tem de ser > 0")
            mu_ln = math.log(med)
        else:
            m = _f(d, "mean", path) if "mean" in d else need_nominal("mean")
            if m <= 0:
                raise UncertaintySpecError(f"{path}: lognormal precisa de média > 0")
            mu_ln = math.log(m) - 0.5 * s * s
        params["mu_ln"], params["sigma_ln"] = mu_ln, s
    return UncertainInput(path=path, dist=dist, params=params, source=src, pressuposto=pres or src.startswith(
        "PRESSUPOSTO"), nominal=nom, unit=str(d.get("unit") or ""), name=str(d.get("name") or ""),
        notes=str(d.get("notes") or ""), origin=str(d.get("origin") or "utilizador"))


@dataclass
class Correlation:
    names: list[str]
    matrix: Array
    source: str = ""


def parse_correlations(entries: Sequence[Any], inputs: Sequence[UncertainInput]) -> Correlation | None:
    """``[{a, b, rho, source}]`` ou ``[a, b, rho]`` → matriz de correlação de postos (só entradas aleatórias)."""
    if not entries:
        return None
    alea = [i for i in inputs if not i.epistemic]
    idx = {}
    for j, i in enumerate(alea):
        idx[i.path] = j
        idx[i.label] = j
    k = len(alea)
    c = np.eye(k)
    srcs = []
    for e in entries:
        if isinstance(e, Mapping):
            a, b, rho, s = e.get("a"), e.get("b"), e.get("rho"), str(e.get("source") or e.get("pressuposto") or "")
        else:
            a, b, rho = e[0], e[1], e[2]
            s = str(e[3]) if len(e) > 3 else ""
        if a not in idx or b not in idx:
            raise UncertaintySpecError(f"correlação {a}–{b}: entrada aleatória desconhecida (intervalos não "
                                       f"se correlacionam)")
        r = float(rho)  # type: ignore[arg-type]
        if not -1.0 < r < 1.0:
            raise UncertaintySpecError(f"correlação {a}–{b}: |ρ| tem de ser < 1")
        if not s.strip():
            raise UncertaintySpecError(f"correlação {a}–{b}: falta 'source' (ou 'pressuposto')")
        ia, ib = idx[str(a)], idx[str(b)]
        c[ia, ib] = c[ib, ia] = r
        srcs.append(f"{a}–{b}: {s}")
    try:
        np.linalg.cholesky(c)
    except np.linalg.LinAlgError as ex:
        raise UncertaintySpecError("matriz de correlação não é definida positiva") from ex
    return Correlation(names=[i.path for i in alea], matrix=c, source="; ".join(srcs))


def iman_conover(u: Array, target: Array, rng: np.random.Generator) -> Array:
    """Reordena as colunas de ``u`` para a correlação de postos ``target`` (Iman & Conover 1982).

    Scores de van der Waerden Φ⁻¹(i/(n+1)), permutados ao acaso por coluna; S = scores·(Q⁻¹)ᵀ·Pᵀ com
    P = chol(target) e Q = chol(corr(scores)); cada coluna de ``u`` toma a ordem de postos da coluna de S.
    """
    n, k = u.shape
    if k < 2:
        return u
    base = np.asarray(_norm_ppf(np.arange(1, n + 1) / (n + 1.0)), dtype=float)
    scores = np.column_stack([rng.permutation(base) for _ in range(k)])
    e = np.corrcoef(scores, rowvar=False)
    q = np.linalg.cholesky(e)
    p = np.linalg.cholesky(target)
    s = scores @ np.linalg.inv(q).T @ p.T
    out = np.empty_like(u)
    for j in range(k):
        ranks = np.argsort(np.argsort(s[:, j]))
        out[:, j] = np.sort(u[:, j])[ranks]
    return out


def unit_sample(n: int, k: int, method: str, rng: np.random.Generator) -> Array:
    m = (method or "lhs").lower()
    if m in ("lhs", "latin", "latin_hypercube"):
        return np.asarray(_lhs_unit(n, k, rng), dtype=float)
    if m in ("mc", "montecarlo", "monte_carlo", "iid"):
        return np.asarray(rng.random((n, k)), dtype=float)
    raise UncertaintySpecError(f"método de amostragem '{method}' desconhecido (lhs | mc)")


@dataclass
class Design:
    """Amostra das entradas aleatórias (n × k) e combinações dos intervalos (ciclo exterior)."""

    names: list[str]
    values: Array
    method: str
    seed: int
    epistemic_names: list[str] = field(default_factory=list)
    epistemic_points: list[dict[str, float]] = field(default_factory=list)

    def rows(self) -> list[dict[str, float]]:
        return [{self.names[j]: float(self.values[i, j]) for j in range(len(self.names))}
                for i in range(self.values.shape[0])]


def sample(inputs: Sequence[UncertainInput], n: int, *, method: str = "lhs", seed: int = 0,
           correlation: Correlation | None = None) -> Design:
    """Amostra das entradas aleatórias; os intervalos vão para o ciclo exterior (todas as combinações dos extremos)."""
    if n < 2:
        raise UncertaintySpecError("N tem de ser ≥ 2")
    alea = [i for i in inputs if not i.epistemic]
    epi = [i for i in inputs if i.epistemic]
    rng = np.random.default_rng(seed)
    k = len(alea)
    vals = np.empty((n, k))
    if k:
        u = unit_sample(n, k, method, rng)
        if correlation is not None:
            if n <= k + 1:
                raise UncertaintySpecError(f"correlações (Iman & Conover) precisam de N > k + 1 = {k + 1}")
            try:
                u = iman_conover(u, correlation.matrix, rng)
            except np.linalg.LinAlgError as ex:
                raise UncertaintySpecError(f"Iman & Conover falhou com N = {n}: {ex}") from ex
        for j, inp in enumerate(alea):
            vals[:, j] = inp.ppf(u[:, j])
    pts: list[dict[str, float]] = []
    if epi:
        if len(epi) > 6:
            raise UncertaintySpecError("mais de 6 intervalos: 2^k extremos é demasiado caro; reduza ou dê "
                                       "distribuições")
        for mask in range(2 ** len(epi)):
            pts.append({e.path: (e.params["high"] if (mask >> b) & 1 else e.params["low"])
                        for b, e in enumerate(epi)})
    return Design(names=[i.path for i in alea], values=vals, method="lhs" if method.lower().startswith("l")
                  else "mc", seed=seed, epistemic_names=[e.path for e in epi], epistemic_points=pts)
