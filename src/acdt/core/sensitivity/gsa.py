"""Sensibilidade global sobre entradas incertas declaradas (várias saídas de uma só amostra).

* **Sobol'** — matrizes A, B e A_B^(i) (Saltelli 2002) no cubo unitário, transformadas pela função quantil de cada
  entrada; estimadores de Saltelli et al., Comput. Phys. Commun. 181 (2010) 259–270, Tabela 2: efeito de 1.ª ordem
  V_i = (1/N) Σ f(B)(f(A_B^i) − f(A)) (o recomendado no artigo) e efeito total de Jansen (1999)
  V_Ti = (1/2N) Σ (f(A) − f(A_B^i))², com V = variância de [f(A); f(B)]. Custo N(k+2).
  As saídas são **centradas** (f − f̂0, f̂0 = média de [f(A); f(B)]) antes dos estimadores: o estimador de V_i não é
  invariante a uma constante em amostra finita — somar c acrescenta c·mean(f(A_B^i) − f(A)), de média nula mas com
  desvio-padrão ≈ c·√(2·V_Ti/N). Com |média|/σ ≫ 1 (p. ex. W0 ≈ 150 kg, σ ≈ 7 kg) o ruído em S1 é da ordem de
  (c/σ)·√(2·ST/N) e dá ΣS1 > 1, S1 > ST e S1 < 0. Subtrair f̂0 é a correção de Sobol', Math. Comput. Simul. 55
  (2001) 271–280 (subtração de uma constante próxima de f0 para reduzir o erro). Jansen e V não mudam.
  Verificação de consistência: S1 ≤ ST e ΣS1 ≤ 1 (com tolerância ``SOBOL_CONSISTENCY_TOL`` ou o IC bootstrap);
  violações ficam em ``avisos`` (amostra insuficiente), nunca corrigidas em silêncio.
  Hipótese do método: entradas **independentes** — as correlações declaradas são ignoradas aqui (e avisado).
* **Morris** — efeitos elementares em r trajetórias numa grelha de p níveis, Δ = p/(2(p−1)) (Morris,
  Technometrics 33 (1991) 161–174); μ* = média de |EE| (Campolongo, Cariboni & Saltelli, Environ. Model. Softw.
  22 (2007) 1509–1518) e σ. Custo r(k+1). Rastreio: ordena, não quantifica variância.

Amostras falhadas (avaliador devolve None/NaN) retiram a linha dessa saída e ficam contadas; nunca entram como 0.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from .distributions import Array, UncertainInput

REF_SOBOL = ("Saltelli, Comput. Phys. Commun. 145 (2002) 280–297 (desenho A, B, A_B); Saltelli et al., Comput. "
             "Phys. Commun. 181 (2010) 259–270, Tab. 2; Jansen, Comput. Phys. Commun. 117 (1999) 35–43")
REF_MORRIS = ("Morris, Technometrics 33 (1991) 161–174; Campolongo, Cariboni & Saltelli, Environ. Model. Softw. 22 "
              "(2007) 1509–1518 (μ*)")
SOBOL_CONSISTENCY_TOL = 0.05  # PRESSUPOSTO: folga absoluta em S1 ≤ ST e ΣS1 ≤ 1 sem IC bootstrap
SOBOL_NEGLIGIBLE = 0.01  # PRESSUPOSTO: violações com |excesso| < 0,01 são irrelevantes (não avisadas)
MORRIS_UNBOUNDED_Q = (0.01, 0.99)  # PRESSUPOSTO: grelha de Morris em quantis 1–99 % nas marginais ilimitadas
Evaluate = Callable[[list[dict[str, float]]], list[Mapping[str, float] | None]]


def _phys(inputs: Sequence[UncertainInput], u: Array, *, morris: bool = False) -> Array:
    x = np.empty_like(u)
    for j, inp in enumerate(inputs):
        col = u[:, j]
        if morris and inp.bounds() is None:
            lo, hi = MORRIS_UNBOUNDED_Q
            col = lo + col * (hi - lo)
        x[:, j] = inp.ppf(col)
    return x


def _rows(inputs: Sequence[UncertainInput], x: Array) -> list[dict[str, float]]:
    return [{inp.path: float(x[i, j]) for j, inp in enumerate(inputs)} for i in range(x.shape[0])]


def _metric_matrix(results: Sequence[Mapping[str, float] | None], metrics: Sequence[str]) -> Array:
    y = np.full((len(results), len(metrics)), np.nan)
    for i, r in enumerate(results):
        if not r:
            continue
        for j, m in enumerate(metrics):
            v = r.get(m)
            if v is not None and isinstance(v, (int, float)) and math.isfinite(float(v)):
                y[i, j] = float(v)
    return y


def sobol_design(inputs: Sequence[UncertainInput], n: int, seed: int) -> dict[str, Any]:
    if n < 2:
        raise ValueError("Sobol: N ≥ 2")
    k = len(inputs)
    rng = np.random.default_rng(seed)
    ua, ub = rng.random((n, k)), rng.random((n, k))
    a, b = _phys(inputs, ua), _phys(inputs, ub)
    ab = []
    for i in range(k):
        m = a.copy()
        m[:, i] = b[:, i]
        ab.append(m)
    pts = _rows(inputs, a) + _rows(inputs, b)
    for m in ab:
        pts += _rows(inputs, m)
    return {"n": n, "k": k, "points": pts, "n_evaluations": n * (k + 2), "seed": seed}


def sobol_from_y(y_a: Array, y_b: Array, y_ab: Sequence[Array], names: Sequence[str], *,
                 bootstrap: int = 0, seed: int = 0, conf: float = 0.95) -> dict[str, Any]:
    """Índices S1/ST (Saltelli 2010 + Jansen 1999) para uma saída escalar; linhas com NaN retiradas."""
    ok = np.isfinite(y_a) & np.isfinite(y_b)
    for c in y_ab:
        ok &= np.isfinite(c)
    n_used = int(ok.sum())
    if n_used < 4:
        return {"status": "nao_avaliado", "reason": f"só {n_used} linhas completas (A, B e todos os A_B)",
                "n_used": n_used, "indices": []}
    ya, yb = y_a[ok], y_b[ok]
    yab = [c[ok] for c in y_ab]

    def est(ia: Array, ib: Array, iab: Sequence[Array]) -> tuple[float, list[tuple[float, float]]]:
        f0 = float(np.mean(np.concatenate([ia, ib])))  # centragem (Sobol' 2001)
        ia, ib, iab = ia - f0, ib - f0, [c - f0 for c in iab]
        v = float(np.var(np.concatenate([ia, ib]), ddof=1))
        res = []
        for c in iab:
            if v <= 1e-300:
                res.append((math.nan, math.nan))
                continue
            s1 = float(np.mean(ib * (c - ia))) / v
            st = 0.5 * float(np.mean((ia - c) ** 2)) / v
            res.append((s1, st))
        return v, res

    v, base = est(ya, yb, yab)
    rel = v / max(float(np.mean(np.concatenate([ya, yb])) ** 2), 1e-300)
    sum_boot: list[float] = []
    if v <= 1e-300 or rel < 1e-20:
        return {"status": "nao_avaliado", "reason": "variância da saída nula — índices indefinidos (≠ 0)",
                "n_used": n_used, "variance": v, "indices": []}
    cis: list[dict[str, list[float] | None]] = [{"S1_ic": None, "ST_ic": None} for _ in names]
    if bootstrap > 0:
        rng = np.random.default_rng(seed + 7919)
        acc: list[list[tuple[float, float]]] = [[] for _ in names]
        for _ in range(bootstrap):
            ix = rng.integers(0, n_used, n_used)
            _, r = est(ya[ix], yb[ix], [c[ix] for c in yab])
            if all(math.isfinite(t[0]) for t in r):
                sum_boot.append(float(sum(t[0] for t in r)))
            for i, t in enumerate(r):
                if math.isfinite(t[0]):
                    acc[i].append(t)
        a = 100 * (1 - conf) / 2
        for i, lst in enumerate(acc):
            if len(lst) > 10:
                arr = np.asarray(lst)
                cis[i] = {"S1_ic": [float(np.percentile(arr[:, 0], a)), float(np.percentile(arr[:, 0], 100 - a))],
                          "ST_ic": [float(np.percentile(arr[:, 1], a)), float(np.percentile(arr[:, 1], 100 - a))]}
    idx: list[dict[str, Any]] = [{"variable": nm, "S1": base[i][0], "ST": base[i][1], **cis[i]}
                                 for i, nm in enumerate(names)]
    idx.sort(key=lambda r: -float(r["ST"]))
    s1sum = float(sum(float(r["S1"]) for r in idx))
    a2 = 100 * (1 - conf) / 2
    sum_ic = ([float(np.percentile(sum_boot, a2)), float(np.percentile(sum_boot, 100 - a2))]
              if len(sum_boot) > 10 else None)
    avisos: list[str] = []
    for row in idx:
        s1, st_ = float(row["S1"]), float(row["ST"])
        lo_s1 = row["S1_ic"][0] if row.get("S1_ic") else s1 - SOBOL_CONSISTENCY_TOL
        hi_st = row["ST_ic"][1] if row.get("ST_ic") else st_
        if lo_s1 > hi_st + SOBOL_NEGLIGIBLE:
            avisos.append(f"{row['variable']}: S1 = {s1:.3f} > ST = {st_:.3f} fora do IC/tolerância — aumente N")
        if (row["S1_ic"][1] if row.get("S1_ic") else s1 + SOBOL_CONSISTENCY_TOL) < -SOBOL_NEGLIGIBLE:
            avisos.append(f"{row['variable']}: S1 = {s1:.3f} < 0 fora do IC/tolerância — aumente N")
    if (sum_ic[0] if sum_ic else s1sum - SOBOL_CONSISTENCY_TOL) > 1.0 + SOBOL_NEGLIGIBLE:
        avisos.append(f"ΣS1 = {s1sum:.3f} > 1 fora do IC/tolerância — aumente N")
    return {"status": "ok", "n_used": n_used, "variance": v, "indices": idx, "sum_S1": s1sum,
            "sum_S1_ic": sum_ic, "consistente": not avisos, "avisos": avisos,
            "interacoes": max(0.0, 1.0 - s1sum),
            "nota": "ST − S1 grande = interações; ΣS1 < 1 = parte da variância vem de interações"}


def sobol(inputs: Sequence[UncertainInput], evaluate: Evaluate, metrics: Sequence[str] | None, *, n: int,
          seed: int = 0, bootstrap: int = 0, conf: float = 0.95) -> dict[str, Any]:
    """Sobol' para todas as saídas pedidas com um só desenho de Saltelli."""
    d = sobol_design(inputs, n, seed)
    res = evaluate(d["points"])
    if metrics is None:
        metrics = sorted({m for r in res if r for m in r})
    y = _metric_matrix(res, metrics)
    k = len(inputs)
    names = [i.path for i in inputs]
    n_failed = int(sum(1 for r in res if not r))
    out: dict[str, Any] = {"method": "Sobol' (S1 de Saltelli 2010, ST de Jansen 1999)", "n": n, "k": k,
                           "n_evaluations": d["n_evaluations"], "n_failed": n_failed, "seed": seed,
                           "reference": REF_SOBOL, "metrics": {}}
    for j, m in enumerate(metrics):
        col = y[:, j]
        ya, yb = col[:n], col[n:2 * n]
        yab = [col[(2 + i) * n:(3 + i) * n] for i in range(k)]
        out["metrics"][m] = sobol_from_y(ya, yb, yab, names, bootstrap=bootstrap, seed=seed, conf=conf)
    return out


def morris_design(k: int, r: int, levels: int, seed: int) -> tuple[Array, list[list[tuple[int, int, float]]]]:
    """r trajetórias de k+1 pontos no cubo unitário; devolve os pontos e, por trajetória, (fator, linha, ±Δ)."""
    if levels < 2 or levels % 2:
        raise ValueError("Morris: número de níveis p tem de ser par ≥ 2 (Morris 1991)")
    rng = np.random.default_rng(seed)
    delta = levels / (2.0 * (levels - 1))
    grid = np.arange(levels) / (levels - 1)
    pts = []
    steps: list[list[tuple[int, int, float]]] = []
    for t in range(r):
        x = rng.choice(grid, size=k)
        traj = [x.copy()]
        st = []
        for f in rng.permutation(k):
            up = x[f] + delta <= 1 + 1e-12
            down = x[f] - delta >= -1e-12
            sgn = 1.0 if (up and (not down or rng.random() < 0.5)) else -1.0
            x = x.copy()
            x[f] = x[f] + sgn * delta
            traj.append(x.copy())
            st.append((int(f), t * (k + 1) + len(traj) - 1, sgn * delta))
        pts += traj
        steps.append(st)
    return np.asarray(pts), steps


def morris(inputs: Sequence[UncertainInput], evaluate: Evaluate, metrics: Sequence[str] | None, *,
           r: int = 10, levels: int = 4, seed: int = 0) -> dict[str, Any]:
    k = len(inputs)
    u, steps = morris_design(k, r, levels, seed)
    x = _phys(inputs, u, morris=True)
    res = evaluate(_rows(inputs, x))
    if metrics is None:
        metrics = sorted({m for q in res if q for m in q})
    y = _metric_matrix(res, metrics)
    names = [i.path for i in inputs]
    out: dict[str, Any] = {"method": "Morris (efeitos elementares, μ* de Campolongo 2007)", "r": r,
                           "levels": levels, "delta": levels / (2.0 * (levels - 1)), "k": k,
                           "n_evaluations": int(u.shape[0]), "n_failed": int(sum(1 for q in res if not q)),
                           "seed": seed, "reference": REF_MORRIS,
                           "unbounded_quantiles": list(MORRIS_UNBOUNDED_Q),
                           "nota": "EE no cubo unitário (por unidade de quantil); grelha em quantis 1–99 % nas "
                                   "marginais ilimitadas (PRESSUPOSTO)", "metrics": {}}
    for j, m in enumerate(metrics):
        ee: list[list[float]] = [[] for _ in range(k)]
        for traj in steps:
            for f, row, d in traj:
                y1, y0 = y[row, j], y[row - 1, j]
                if math.isfinite(y1) and math.isfinite(y0):
                    ee[f].append((y1 - y0) / d)
        rows: list[dict[str, Any]] = []
        for f in range(k):
            e = np.asarray(ee[f])
            if e.size == 0:
                rows.append({"variable": names[f], "status": "nao_avaliado", "n_ee": 0, "mu": None,
                             "mu_star": None, "sigma": None})
                continue
            rows.append({"variable": names[f], "status": "ok", "n_ee": int(e.size), "mu": float(e.mean()),
                         "mu_star": float(np.abs(e).mean()),
                         "sigma": float(e.std(ddof=1)) if e.size > 1 else None})
        mx = max((float(q["mu_star"]) for q in rows if q["mu_star"] is not None), default=0.0)
        for q in rows:
            q["mu_star_norm"] = (float(q["mu_star"]) / mx) if (q["mu_star"] is not None and mx > 0) else None
        rows.sort(key=lambda q: -(q["mu_star"] if q["mu_star"] is not None else -1.0))
        out["metrics"][m] = {"status": "ok" if any(q["status"] == "ok" for q in rows) else "nao_avaliado",
                             "effects": rows}
    return out
