"""Substituto barato do modelo: superfície de resposta quadrática por mínimos quadrados, validada por PRESS.

Quando cada avaliação do pipeline custa minutos, o estudo corre o modelo verdadeiro num desenho LHS de treino
(N_treino pontos, entradas aleatórias pelas suas distribuições e intervalos varridos uniformemente) e ajusta, por
saída, um polinómio de 2.º grau nas entradas normalizadas (Myers, Montgomery & Anderson-Cook, Response Surface
Methodology, 4.ª ed., Wiley 2016, Cap. 2–3). Validação por validação cruzada «deixar um de fora» exata a partir da
matriz chapéu: e_(i) = e_i / (1 − h_ii), PRESS = Σ e_(i)², Q² = 1 − PRESS/SS_tot (Allen, Technometrics 16 (1974)
125–127). Uma saída só usa o substituto se Q² ≥ ``q2_min`` (declarado; omissão 0,95 PRESSUPOSTO); senão fica com
as amostras do modelo verdadeiro (o desenho de treino é um LHS válido) e a sensibilidade dessa saída não é avaliada.

Termos: quadrático completo (1 + k + k(k+1)/2) se N_treino ≥ 1,5·termos, senão quadrático sem interações
(1 + 2k). A fração de pontos de Monte Carlo fora da caixa de treino (extrapolação) fica registada.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from .distributions import Array

REF = ("Myers, Montgomery & Anderson-Cook, Response Surface Methodology, 4.ª ed., Wiley 2016; Allen, Technometrics "
       "16 (1974) 125–127 (PRESS)")
DEFAULT_Q2_MIN = 0.95


def _basis(z: Array, full: bool) -> Array:
    n, k = z.shape
    cols = [np.ones(n)] + [z[:, i] for i in range(k)] + [z[:, i] ** 2 for i in range(k)]
    if full:
        cols += [z[:, i] * z[:, j] for i in range(k) for j in range(i + 1, k)]
    return np.column_stack(cols)


def n_terms(k: int, full: bool) -> int:
    return 1 + 2 * k + (k * (k - 1) // 2 if full else 0)


@dataclass
class QuadraticRS:
    names: list[str]
    center: Array
    scale: Array
    full: bool
    coef: Array = field(default_factory=lambda: np.zeros(0))
    q2: float = math.nan
    r2: float = math.nan
    rmse_loo: float = math.nan
    n_train: int = 0

    def predict(self, x: Array) -> Array:
        z = (x - self.center) / self.scale
        return np.asarray(_basis(z, self.full) @ self.coef, dtype=float)

    def to_dict(self) -> dict[str, Any]:
        return {"terms": "quadrático completo" if self.full else "quadrático sem interações",
                "n_terms": int(self.coef.size), "n_train": self.n_train, "Q2": self.q2, "R2": self.r2,
                "rmse_loo": self.rmse_loo}


def fit(x: Array, y: Array, names: Sequence[str], full: bool | None = None) -> QuadraticRS | None:
    """Ajusta e valida (PRESS). None se houver menos pontos do que termos + 2."""
    ok = np.isfinite(y)
    x, y = x[ok], y[ok]
    n, k = x.shape
    if full is None:
        full = n >= 1.5 * n_terms(k, True)
    p = n_terms(k, full)
    if n < p + 2:
        return None
    c = x.mean(axis=0)
    s = x.std(axis=0)
    s[s <= 0] = 1.0
    xb = _basis((x - c) / s, full)
    coef, *_ = np.linalg.lstsq(xb, y, rcond=None)
    yhat = xb @ coef
    e = y - yhat
    pinv = np.linalg.pinv(xb.T @ xb)
    h = np.einsum("ij,jk,ik->i", xb, pinv, xb)
    loo = e / np.clip(1 - h, 1e-9, None)
    sst = float(np.sum((y - y.mean()) ** 2))
    press = float(np.sum(loo ** 2))
    rs = QuadraticRS(list(names), c, s, bool(full), coef, n_train=int(n))
    if sst <= 0:
        rs.q2 = rs.r2 = math.nan
    else:
        rs.q2 = 1 - press / sst
        rs.r2 = 1 - float(np.sum(e ** 2)) / sst
    rs.rmse_loo = math.sqrt(press / n)
    return rs


def outside_box(x: Array, lo: Array, hi: Array) -> float:
    if x.size == 0:
        return 0.0
    return float(np.mean(np.any((x < lo) | (x > hi), axis=1)))


def outside_box_per_input(x: Array, lo: Array, hi: Array, names: Sequence[str]) -> dict[str, dict[str, float]]:
    """Por entrada: fração fora de [lo, hi] e excursão máxima em unidades da largura da caixa."""
    out: dict[str, dict[str, float]] = {}
    for j, nm in enumerate(names):
        c = x[:, j]
        w = float(hi[j] - lo[j])
        exc = np.maximum(lo[j] - c, c - hi[j])
        out[str(nm)] = {"lo": float(lo[j]), "hi": float(hi[j]),
                        "fracao": float(np.mean((c < lo[j]) | (c > hi[j]))),
                        "excursao_max": float(max(0.0, float(exc.max())) / w) if w > 0 else 0.0}
    return out


@dataclass
class Surrogates:
    names: list[str]
    models: dict[str, QuadraticRS]
    rejected: dict[str, str]
    lo: Array
    hi: Array
    q2_min: float

    def predict(self, points: Sequence[Mapping[str, float]], fixed: Mapping[str, float] | None = None
                ) -> dict[str, Array]:
        x = np.asarray([[float({**(fixed or {}), **p}[nm]) for nm in self.names] for p in points], dtype=float)
        return {m: rs.predict(x) for m, rs in self.models.items()}

    def report(self) -> dict[str, Any]:
        return {"reference": REF, "q2_min": self.q2_min,
                "accepted": {m: r.to_dict() for m, r in self.models.items()}, "rejected": dict(self.rejected)}


def build(x: Array, results: Sequence[Mapping[str, float] | None], names: Sequence[str], q2_min: float,
          metrics: Sequence[str] | None = None) -> Surrogates:
    ms = list(metrics) if metrics else sorted({m for r in results if r for m in r})
    models: dict[str, QuadraticRS] = {}
    rej: dict[str, str] = {}
    for m in ms:
        y = np.asarray([float(r[m]) if r and m in r and math.isfinite(float(r[m])) else math.nan for r in results])
        if np.sum(np.isfinite(y)) < 4:
            rej[m] = "menos de 4 amostras de treino com valor"
            continue
        if float(np.nanstd(y)) <= 1e-12 * max(1.0, abs(float(np.nanmean(y)))):
            rej[m] = "constante no desenho de treino (sem variância a modelar)"
            continue
        rs = fit(x, y, names)
        if rs is None:
            rej[m] = "pontos de treino insuficientes para os termos do polinómio"
            continue
        if not (math.isfinite(rs.q2) and rs.q2 >= q2_min):
            rej[m] = f"Q² = {rs.q2:.3f} < {q2_min:g} (validação cruzada PRESS)"
            continue
        models[m] = rs
    return Surrogates(list(names), models, rej, x.min(axis=0), x.max(axis=0), q2_min)
