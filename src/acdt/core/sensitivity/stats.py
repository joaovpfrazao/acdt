"""Estatísticas da propagação: média, desvio, percentis com intervalo de confiança, convergência, P(passa).

* Erro-padrão da média s/√N (estimador clássico; para LHS é conservador — Stein, Technometrics 29 (1987) 143–151
  mostra que a variância do LHS não excede a do MC para N grande).
* Intervalo de confiança dos percentis por estatísticas de ordem, sem hipótese de distribuição (Conover,
  Practical Nonparametric Statistics, 3.ª ed., Wiley 1999, Sec. 3.2; aproximação normal à binomial).
* Média corrida em potências de 2 (histórico) e critério de convergência SE/|média| ≤ tolerância declarada.
* P(passa) com intervalo de Wilson (Wilson, JASA 22 (1927) 209–212; Agresti & Coull, Am. Stat. 52 (1998) 119–126).
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

REF = ("Conover 1999 Sec. 3.2 (IC de quantis por estatísticas de ordem); Stein 1987 (variância do LHS); "
       "Wilson 1927 e Agresti & Coull 1998 (IC de proporção)")
PERCENTILES = (5.0, 50.0, 95.0)


def z_of(conf: float) -> float:
    """Quantil normal bilateral para o nível de confiança ``conf`` (Φ⁻¹((1+conf)/2))."""
    from .monte_carlo import _norm_ppf

    return float(_norm_ppf(np.asarray([0.5 * (1.0 + conf)]))[0])


def pkey(p: float) -> str:
    return f"p{int(p) if float(p).is_integer() else p}"


def percentile_ci(sorted_x: np.ndarray, p: float, conf: float) -> tuple[float, float] | None:
    """IC distribution-free do quantil p/100 (Conover 1999): postos n·q ∓ z·√(n q (1−q))."""
    n = sorted_x.size
    q = p / 100.0
    z = z_of(conf)
    half = z * math.sqrt(n * q * (1 - q))
    lo = int(math.floor(n * q - half))
    hi = int(math.ceil(n * q + half)) + 1  # postos 1-based → índice
    if lo < 1 or hi > n:
        return None  # N pequeno de mais para este percentil a este nível
    return float(sorted_x[lo - 1]), float(sorted_x[hi - 1])


def summarize(values: Sequence[float], *, percentiles: Sequence[float] = PERCENTILES, conf: float = 0.95,
              rel_tol: float = 0.01) -> dict[str, Any]:
    x = np.asarray([v for v in values if v is not None and math.isfinite(float(v))], dtype=float)
    n = int(x.size)
    if n < 2:
        return {"status": "nao_avaliado", "n": n,
                "reason": "menos de 2 amostras válidas — incerteza indefinida (não é zero)"}
    mean = float(np.mean(x))
    sd = float(np.std(x, ddof=1))
    se = sd / math.sqrt(n)
    xs = np.sort(x)
    out: dict[str, Any] = {"status": "ok", "n": n, "mean": mean, "std": sd, "se_mean": se,
                           "cv": (sd / abs(mean)) if mean != 0 else None,
                           "min": float(xs[0]), "max": float(xs[-1])}
    for p in percentiles:
        out[pkey(p)] = float(np.percentile(x, p))
        ci = percentile_ci(xs, p, conf)
        out[pkey(p) + "_ic"] = list(ci) if ci else None
    # média corrida em N = 2, 4, 8, … (ordem da amostra) — ver se estabiliza
    hist = []
    m = 2
    while m < n:
        hist.append({"n": m, "mean": float(np.mean(x[:m])), "se": float(np.std(x[:m], ddof=1) / math.sqrt(m))})
        m *= 2
    hist.append({"n": n, "mean": mean, "se": se})
    out["running_mean"] = hist
    rel = se / abs(mean) if mean != 0 else (0.0 if se == 0 else math.inf)
    out["se_rel"] = rel
    out["converged"] = bool(rel <= rel_tol)
    out["convergence"] = (f"SE/|média| = {rel:.3g} {'≤' if rel <= rel_tol else '>'} {rel_tol:g} "
                          f"(tolerância declarada)")
    return out


def wilson(k: int, n: int, conf: float = 0.95) -> tuple[float, float] | None:
    if n <= 0:
        return None
    z = z_of(conf)
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


PROB_STATUSES = ("prob_passa", "prob_no_limite", "prob_falha", "inconclusivo", "nao_avaliado", "desconhecido")


def probabilistic_status(counts: dict[str, int], n_total: int, *, target: float, conf: float) -> dict[str, Any]:
    """Estado probabilístico de um requisito a partir dos estados determinísticos por amostra.

    P(passa) conservadora = n_passa / N_total: amostras falhadas, ``no_limite``, ``desconhecido`` e
    ``nao_avaliado`` não contam como passa (não avaliado ≠ passa). P(no_limite) e P(falha) também sobre N_total,
    cada uma com o seu IC de Wilson ao nível ``conf``. Estados:

    * ``prob_passa`` — limite inferior de P(passa) ≥ alvo;
    * ``prob_no_limite`` — P(passa) não chega ao alvo (limite superior < alvo) **mas** o limite inferior de
      P(passa ∪ no_limite) ≥ alvo: cumpre dentro da tolerância declarada do requisito, sem margem. É o análogo
      probabilístico do ``no_limite`` determinístico (decisão do engenheiro), não uma falha;
    * ``prob_falha`` — limite superior de P(passa) < alvo e não é ``prob_no_limite``;
    * ``inconclusivo`` — o IC de P(passa) contém o alvo (mais amostras);
    * ``nao_avaliado`` — nenhuma amostra avaliada; ``desconhecido`` — todas as avaliadas sem valor.
    """
    np_ = counts.get("passa", 0)
    nl = counts.get("no_limite", 0)
    nf = counts.get("falha", 0)
    assessed = np_ + nl + nf
    out: dict[str, Any] = {"n": n_total, "counts": dict(counts), "p_passa": None, "p_passa_ic": None,
                           "p_falha": None, "p_falha_ic": None, "p_no_limite": None, "p_no_limite_ic": None,
                           "p_passa_avaliadas": None, "alvo": target, "confianca": conf}
    if n_total <= 0 or (assessed == 0 and counts.get("desconhecido", 0) == 0):
        out["estado_probabilistico"] = "nao_avaliado"
        out["nota"] = "nenhuma amostra avaliada"
        return out
    if assessed == 0:
        out["estado_probabilistico"] = "desconhecido"
        out["nota"] = "avaliador correu sem valor em todas as amostras"
        return out
    p = np_ / n_total
    ci = wilson(np_, n_total, conf)
    ci_nl = wilson(nl, n_total, conf)
    ci_f = wilson(nf, n_total, conf)
    ci_ok = wilson(np_ + nl, n_total, conf)
    assert ci is not None and ci_nl is not None and ci_f is not None and ci_ok is not None
    out.update(p_passa=p, p_passa_ic=list(ci), p_falha=nf / n_total, p_falha_ic=list(ci_f),
               p_no_limite=nl / n_total, p_no_limite_ic=list(ci_nl), p_passa_avaliadas=np_ / assessed,
               p_passa_ou_no_limite=(np_ + nl) / n_total, p_passa_ou_no_limite_ic=list(ci_ok))
    if ci[0] >= target:
        st = "prob_passa"
    elif ci[1] < target and ci_ok[0] >= target:
        st = "prob_no_limite"
    elif ci[1] < target:
        st = "prob_falha"
    else:
        st = "inconclusivo"
    out["estado_probabilistico"] = st
    nn = n_total - assessed
    out["nota"] = (f"P(passa)={p:.3f} IC{int(round(100 * conf))}% [{ci[0]:.3f}, {ci[1]:.3f}] vs alvo {target:g}"
                   + (f"; P(no_limite)={nl / n_total:.3f} (cumpre só dentro da tolerância declarada)"
                      if st == "prob_no_limite" else "")
                   + (f"; {nn} amostras sem veredicto contam como não-passa" if nn else ""))
    return out
