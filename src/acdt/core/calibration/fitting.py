# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Ajuste de parâmetros/fatores de modelo a dados medidos (domínio-agnóstico).

O modelo é uma expressão aritmética segura (sem ``eval``) dos **canais** do conjunto de dados, dos **parâmetros** a
calibrar e de **constantes** declaradas, p. ex. ``CD0 + CL**2 / (pi * AR * e)`` ou ``k_clmax * CLmax_modelo`` (a
previsão do modelo do acdt nas mesmas condições entra como canal, com a sua proveniência).

Métodos:

* ``wls`` — mínimos quadrados não lineares ponderados (Levenberg–Marquardt / região de confiança, SciPy
  ``least_squares``). Pesos = 1/σ² com σ a incerteza-padrão da saída medida e, quando as entradas também têm
  incerteza declarada, a **variância efetiva** σ² = σ_y² + Σ (∂η/∂x_j · σ_xj)² (Orear, Am. J. Phys. 50 (1982)
  912–916). Covariância dos parâmetros = (JᵀWJ)⁻¹ (Bard, *Nonlinear Parameter Estimation*, Academic Press 1974,
  Cap. 7; Seber & Wild, *Nonlinear Regression*, Wiley 1989, §2.1). Sem incerteza de instrumento declarada, σ é
  estimado pelos resíduos (s² = SSR/(n−p)) e a covariância é s²(JᵀJ)⁻¹. Com σ declarado e χ²/ν > 1 a
  covariância é multiplicada por χ²/ν (razão de Birge, Phys. Rev. 40 (1932) 207; Bevington & Robinson, *Data
  Reduction and Error Analysis*, 3.ª ed. 2003, §8.2) — o instrumento sozinho não explica a dispersão. Intervalo
  de 95 % pela t de Student com ν = n − p graus de liberdade (GUM G.3). ν < 1 ou JᵀWJ singular → incerteza
  **desconhecida** (nunca zero).
* ``koh`` — calibração bayesiana à Kennedy & O'Hagan, J. R. Statist. Soc. B 63 (2001) 425–464, versão leve:
  y = η(x, θ) + δ(x) + ε, discrepância δ ~ PG(0, σ_δ² exp(−|x−x'|²/2ℓ²)) nas entradas normalizadas a [0, 1],
  ε ~ N(0, σ²) (σ do instrumento ou hiperparâmetro). Máximo a posteriori conjunto de θ e dos hiperparâmetros e
  covariância de θ pela aproximação de Laplace (Gauss–Newton: (JᵀC⁻¹J + Σ_prior⁻¹)⁻¹) com os hiperparâmetros
  fixos no MAP — a abordagem «modular» de Bayarri et al., Technometrics 49 (2007) 138–154 e Liu, Bayarri &
  Berger, Bayesian Analysis 4 (2009) 119–150. **Exige** prior normal informativo para cada parâmetro: θ e δ não
  são identificáveis sem ele (Brynjarsdóttir & O'Hagan, Inverse Problems 30 (2014) 114007). Não é MCMC: a
  posterior é aproximada por uma normal.
"""
from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from .ingest import Dataset, IngestError

Array = npt.NDArray[np.float64]

METHODS = ("wls", "koh")
REF_WLS = ("Bard, Nonlinear Parameter Estimation, Academic Press 1974, Cap. 7; Seber & Wild, Nonlinear Regression, "
           "Wiley 1989; Orear, Am. J. Phys. 50 (1982) 912 (variância efetiva); Birge, Phys. Rev. 40 (1932) 207")
REF_KOH = ("Kennedy & O'Hagan, J. R. Statist. Soc. B 63 (2001) 425–464; Bayarri et al., Technometrics 49 (2007) "
           "138–154; Brynjarsdóttir & O'Hagan, Inverse Problems 30 (2014) 114007")

_BIN: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide, ast.Pow: np.power}
_FN: dict[str, Callable[..., Any]] = {
    "sqrt": np.sqrt, "log": np.log, "exp": np.exp, "abs": np.abs, "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "radians": np.radians, "degrees": np.degrees, "min": np.minimum, "max": np.maximum, "tanh": np.tanh}
_CONST = {"pi": math.pi}


class CalibrationError(ValueError):
    pass


# ------------------------------------------------------------------------------------------ expressões vetoriais
def compile_model(src: str) -> ast.Expression:
    try:
        tree = ast.parse(str(src), mode="eval")
    except SyntaxError as e:
        raise CalibrationError(f"expressão do modelo inválida '{src}': {e.msg}") from e
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Call,
                                 ast.USub, ast.UAdd, *tuple(_BIN))):
            raise CalibrationError(f"expressão '{src}': elemento não permitido {type(node).__name__}")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in _FN):
            raise CalibrationError(f"expressão '{src}': só as funções {sorted(_FN)}")
        if isinstance(node, ast.Constant) and (isinstance(node.value, bool) or
                                               not isinstance(node.value, (int, float))):
            raise CalibrationError(f"expressão '{src}': só constantes numéricas")
    return tree


def model_names(src: str) -> set[str]:
    tree = compile_model(src)
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - calls


def eval_model(tree: ast.Expression, env: Mapping[str, Any]) -> Array:
    def ev(n: ast.AST) -> Any:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return float(n.value)  # type: ignore[arg-type]
        if isinstance(n, ast.Name):
            if n.id in env:
                return env[n.id]
            if n.id in _CONST:
                return _CONST[n.id]
            raise CalibrationError(f"nome '{n.id}' sem valor (nem canal, nem parâmetro, nem constante)")
        if isinstance(n, ast.UnaryOp):
            x = ev(n.operand)
            return -x if isinstance(n.op, ast.USub) else x
        if isinstance(n, ast.BinOp):
            return _BIN[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            return _FN[n.func.id](*[ev(a) for a in n.args])
        raise CalibrationError(f"elemento {type(n).__name__}")  # pragma: no cover — validado em compile_model

    with np.errstate(all="ignore"):
        return np.asarray(ev(tree), dtype=float)


# ---------------------------------------------------------------------------------------------- especificação
@dataclass
class Parameter:
    name: str
    initial: float
    lower: float = -math.inf
    upper: float = math.inf
    nominal: float | None = None  # valor atual do modelo (antes da calibração), se conhecido
    unit: str = "1"
    prior_mean: float | None = None
    prior_sd: float | None = None
    prior_source: str = ""
    target: str | None = None  # caminho de parâmetro (assumptions.…) a substituir
    factor: str | None = None  # nome de um fator de calibração existente do domínio (k_clmax, k_EI, …)
    group: str | None = None
    what: str = ""

    @classmethod
    def from_dict(cls, name: str, d: Mapping[str, Any]) -> "Parameter":
        b = d.get("bounds") or [-math.inf, math.inf]
        pr = d.get("prior") or {}
        init = d.get("initial", d.get("nominal", pr.get("mean")))
        if init is None:
            raise CalibrationError(f"parâmetro '{name}': falta 'initial' (ou 'nominal'/'prior.mean')")
        if pr and (pr.get("mean") is None or pr.get("sd") is None or not pr.get("source")):
            raise CalibrationError(f"parâmetro '{name}': prior precisa de mean, sd e source")
        return cls(name=name, initial=float(init), lower=float(b[0]), upper=float(b[1]),
                   nominal=None if d.get("nominal") is None else float(d["nominal"]), unit=str(d.get("unit", "1")),
                   prior_mean=None if not pr else float(pr["mean"]), prior_sd=None if not pr else float(pr["sd"]),
                   prior_source=str(pr.get("source", "")), target=d.get("target"), factor=d.get("factor"),
                   group=d.get("group"), what=str(d.get("what", "")))


@dataclass
class ModelSpec:
    expr: str
    output: str
    parameters: list[Parameter]
    units: dict[str, str] = field(default_factory=dict)  # canal → unidade em que entra na expressão
    constants: dict[str, float] = field(default_factory=dict)
    method: str = "wls"
    birge: bool = True
    discrepancy_inputs: list[str] | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ModelSpec":
        m = d.get("model") or {}
        if not m.get("expr") or not m.get("output"):
            raise CalibrationError("model precisa de 'expr' e 'output'")
        ps = [Parameter.from_dict(k, v or {}) for k, v in (d.get("parameters") or {}).items()]
        if not ps:
            raise CalibrationError("sem parâmetros a calibrar")
        meth = str(d.get("method", "wls"))
        if meth not in METHODS:
            raise CalibrationError(f"método '{meth}' não é um de {METHODS}")
        consts = {}
        for k, v in (m.get("constants") or {}).items():
            if isinstance(v, Mapping):
                if not v.get("source"):
                    raise CalibrationError(f"constante '{k}': falta 'source'")
                v = v["value"]
            consts[str(k)] = float(v)
        disc = (d.get("discrepancy") or {}).get("inputs")
        return cls(expr=str(m["expr"]), output=str(m["output"]), parameters=ps,
                   units={str(k): str(v) for k, v in (m.get("units") or {}).items()}, constants=consts,
                   method=meth, birge=bool(d.get("birge_scaling", True)),
                   discrepancy_inputs=None if disc is None else [str(x) for x in disc])

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.parameters]

    def inputs(self) -> list[str]:
        used = model_names(self.expr)
        return sorted(used - set(self.names) - set(self.constants) - set(_CONST))


@dataclass
class FitResult:
    method: str
    names: list[str]
    theta: Array
    cov: Array | None
    dof: int
    n: int
    n_dropped: int
    sigma_source: str  # instrumento | residuos | hiperparametro
    chi2: float | None
    chi2_red: float | None
    birge_factor: float | None
    rmse: float
    residuals: Array  # y − η (unidade da saída)
    eta: Array
    y: Array
    sigma: Array | None
    x: dict[str, Array]
    at_bound: list[str]
    identifiable: bool
    notes: list[str] = field(default_factory=list)
    discrepancy: dict[str, Any] | None = None
    mask: Array | None = None  # linhas do conjunto usadas no ajuste

    def sd(self) -> Array | None:
        if self.cov is None:
            return None
        d = np.diag(self.cov)
        return np.sqrt(np.where(d >= 0, d, np.nan))

    def ci95(self) -> Array | None:
        s = self.sd()
        if s is None or self.dof < 1:
            return None
        from scipy.stats import t
        k = float(t.ppf(0.975, self.dof)) if self.method == "wls" else 1.959963984540054
        return np.stack([self.theta - k * s, self.theta + k * s], axis=1)

    def corr(self) -> Array | None:
        s = self.sd()
        if self.cov is None or s is None or not np.all(s > 0):
            return None
        return np.asarray(self.cov / np.outer(s, s), dtype=float)


def _data(spec: ModelSpec, ds: Dataset) -> tuple[dict[str, Array], Array, Array | None, dict[str, Array | None], Array]:
    ins = spec.inputs()
    out = ds.channel(spec.output)

    def unit_of(name: str, ch: Any) -> str:
        if name in spec.units:
            return spec.units[name]
        if ch.unit is None:
            raise CalibrationError(f"canal '{name}' com unidade não declarada; declare-a nos metadados ou em "
                                   f"model.units (não se presume adimensional)")
        return str(ch.unit)

    try:
        x = {k: ds.channel(k).to(unit_of(k, ds.channel(k))) for k in ins}
        sx = {k: ds.channel(k).sd_to(unit_of(k, ds.channel(k))) for k in ins}
        uy = unit_of(spec.output, out)
        y, sy = out.to(uy), out.sd_to(uy)
    except IngestError as e:
        raise CalibrationError(str(e)) from e
    ok = np.isfinite(y)
    for v in x.values():
        ok &= np.isfinite(v)
    return ({k: v[ok] for k, v in x.items()}, y[ok], None if sy is None else sy[ok],
            {k: (None if v is None else v[ok]) for k, v in sx.items()}, ok)


def _jac(f: Callable[[Array], Array], th: Array, lo: Array, hi: Array) -> Array:
    """Jacobiano por diferenças centrais (passo relativo √ε^(1/3)), unilateral junto aos limites."""
    cols = []
    for j in range(th.size):
        h = 6e-6 * max(1.0, abs(th[j]))
        a, b = th.copy(), th.copy()
        a[j] = min(th[j] + h, hi[j])
        b[j] = max(th[j] - h, lo[j])
        cols.append((f(a) - f(b)) / (a[j] - b[j]))
    return np.stack(cols, axis=1)


def fit(spec: ModelSpec, ds: Dataset) -> FitResult:
    x, y, sy, sx, mask = _data(spec, ds)
    nd = int(mask.size - mask.sum())
    n, p = y.size, len(spec.parameters)
    if n == 0:
        raise CalibrationError("sem pontos válidos (todos em falta)")
    tree = compile_model(spec.expr)
    lo = np.array([q.lower for q in spec.parameters])
    hi = np.array([q.upper for q in spec.parameters])
    th0 = np.clip(np.array([q.initial for q in spec.parameters]), lo, hi)

    def eta(th: Array, xx: Mapping[str, Array] | None = None) -> Array:
        env: dict[str, Any] = dict(spec.constants)
        env.update(xx if xx is not None else x)
        env.update({q.name: th[i] for i, q in enumerate(spec.parameters)})
        e = eval_model(tree, env)
        return np.broadcast_to(e, y.shape).astype(float)

    if spec.method == "koh":
        r = _fit_koh(spec, x, y, sy, sx, nd, eta, th0, lo, hi)
    else:
        r = _fit_wls(spec, x, y, sy, sx, nd, eta, th0, lo, hi)
    r.mask = mask
    return r


def _sigma_eff(eta: Callable[..., Array], th: Array, x: Mapping[str, Array], sy: Array | None,
               sx: Mapping[str, Array | None]) -> Array | None:
    if sy is None:
        return None
    var = sy ** 2
    for k, s in sx.items():
        if s is None or not np.any(s > 0):
            continue
        h = 1e-6 * np.maximum(1.0, np.abs(x[k]))
        xp, xm = dict(x), dict(x)
        xp[k], xm[k] = x[k] + h, x[k] - h
        d = (eta(th, xp) - eta(th, xm)) / (2 * h)
        var = var + (d * s) ** 2
    return np.sqrt(var)


def _fit_wls(spec: ModelSpec, x: dict[str, Array], y: Array, sy: Array | None, sx: dict[str, Array | None], nd: int,
             eta: Callable[..., Array], th0: Array, lo: Array, hi: Array) -> FitResult:
    from scipy.optimize import least_squares

    n, p = y.size, th0.size
    notes: list[str] = []
    if sy is not None and np.any(sy <= 0):
        notes.append("incerteza de instrumento nula em algum ponto: tratada como desconhecida (σ pelos resíduos)")
        sy = None
    sig = _sigma_eff(eta, th0, x, sy, sx)
    th = th0
    for _ in range(3):  # variância efetiva recalculada no ótimo (Orear 1982)
        w = np.ones_like(y) if sig is None else 1.0 / sig
        r = least_squares(lambda t: (y - eta(t)) * w, th, bounds=(lo, hi), method="trf", x_scale="jac",
                          xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=2000)
        th = np.asarray(r.x, dtype=float)
        new = _sigma_eff(eta, th, x, sy, sx)
        if new is None or sig is None or np.allclose(new, sig, rtol=1e-6):
            sig = new
            break
        sig = new
    if sig is not None and any(v is not None and np.any(v > 0) for v in sx.values()):
        notes.append("variância efetiva com a incerteza das entradas (Orear 1982)")
    w = np.ones_like(y) if sig is None else 1.0 / sig
    res = y - eta(th)
    J = _jac(lambda t: eta(t) * w, th, lo, hi)
    dof = n - p
    at_b = [q.name for i, q in enumerate(spec.parameters)
            if (math.isfinite(lo[i]) and abs(th[i] - lo[i]) <= 1e-9 * max(1, abs(lo[i]))) or
            (math.isfinite(hi[i]) and abs(th[i] - hi[i]) <= 1e-9 * max(1, abs(hi[i])))]
    JTJ = J.T @ J
    ident = bool(np.linalg.matrix_rank(JTJ, tol=1e-10 * max(1.0, float(np.abs(JTJ).max()))) == p)
    cov = chi2 = chi2r = birge = None
    src = "instrumento" if sig is not None else "residuos"
    if not ident:
        notes.append("JᵀWJ singular: parâmetros não identificáveis com estes dados (incerteza desconhecida)")
    elif dof < 1:
        notes.append(f"ν = n − p = {dof} < 1: incerteza dos parâmetros desconhecida (não zero)")
    else:
        inv = np.linalg.inv(JTJ)
        if sig is not None:
            chi2 = float(np.sum((res * w) ** 2))
            chi2r = chi2 / dof
            if spec.birge and chi2r > 1.0:
                birge = chi2r
                inv = inv * chi2r
                notes.append(f"covariância × χ²/ν = {chi2r:.3g} (razão de Birge): o instrumento não explica a dispersão")
            cov = inv
        else:
            s2 = float(np.sum(res ** 2)) / dof
            cov = inv * s2
            notes.append("sem incerteza de instrumento declarada: σ estimado pelos resíduos (s² = SSR/ν)")
    if at_b:
        notes.append(f"parâmetro(s) no limite {at_b}: a covariância linearizada não vale lá")
    return FitResult("wls", spec.names, th, cov, dof, n, nd, src, chi2, chi2r, birge,
                     float(np.sqrt(np.mean(res ** 2))), res, eta(th), y, sig, x, at_b, ident, notes)


def _fit_koh(spec: ModelSpec, x: dict[str, Array], y: Array, sy: Array | None, sx: dict[str, Array | None],
             nd: int, eta: Callable[..., Array], th0: Array, lo: Array, hi: Array) -> FitResult:
    from scipy.optimize import minimize

    missing = [q.name for q in spec.parameters if q.prior_mean is None or not q.prior_sd]
    if missing:
        raise CalibrationError(f"koh: prior normal informativo obrigatório para {missing} (θ e δ não são "
                               f"identificáveis sem ele — Brynjarsdóttir & O'Hagan 2014)")
    n, p = y.size, th0.size
    pm = np.array([float(q.prior_mean) for q in spec.parameters])  # type: ignore[arg-type]
    ps = np.array([float(q.prior_sd) for q in spec.parameters])  # type: ignore[arg-type]
    dins = spec.discrepancy_inputs or sorted(x)
    bad = set(dins) - set(x)
    if bad:
        raise CalibrationError(f"koh: discrepancy.inputs {sorted(bad)} não são entradas do modelo {sorted(x)}")
    if not dins:
        raise CalibrationError("koh: o modelo não tem entradas para a discrepância δ(x)")
    Z = np.stack([x[k] for k in dins], axis=1)
    span = np.ptp(Z, axis=0)
    Z = (Z - Z.min(axis=0)) / np.where(span > 0, span, 1.0)
    D2 = np.sum((Z[:, None, :] - Z[None, :, :]) ** 2, axis=2)
    sig = _sigma_eff(eta, th0, x, sy, sx)
    ys = float(np.std(y)) or 1.0
    noise_hyper = sig is None

    def unpack(z: Array) -> tuple[Array, float, float, Array]:
        th = z[:p]
        sd_d, ell = math.exp(z[p]), math.exp(z[p + 1])
        se = sig if not noise_hyper else np.full(n, math.exp(z[p + 2]))
        return th, sd_d, ell, se  # type: ignore[return-value]

    def C_of(sd_d: float, ell: float, se: Array) -> Array:
        return np.asarray(sd_d ** 2 * np.exp(-0.5 * D2 / ell ** 2) + np.diag(se ** 2) + 1e-12 * ys ** 2 * np.eye(n))

    def nlp(z: Array) -> float:
        th, sd_d, ell, se = unpack(z)
        r = y - eta(th)
        if not np.all(np.isfinite(r)):
            return 1e30
        try:
            L = np.linalg.cholesky(C_of(sd_d, ell, se))
        except np.linalg.LinAlgError:
            return 1e30
        a = np.linalg.solve(L, r)
        return float(0.5 * a @ a + np.sum(np.log(np.diag(L))) + 0.5 * np.sum(((th - pm) / ps) ** 2))

    z0 = [*np.clip(pm, lo, hi), math.log(0.1 * ys), math.log(0.3)] + ([math.log(0.1 * ys)] if noise_hyper else [])
    bnds = list(zip(lo, hi)) + [(math.log(1e-8 * ys), math.log(10 * ys)), (math.log(0.05), math.log(5.0))]
    if noise_hyper:
        bnds.append((math.log(1e-8 * ys), math.log(10 * ys)))
    best = None
    for start_ell in (math.log(0.3), math.log(1.0)):
        zz = np.array(z0, dtype=float)
        zz[p + 1] = start_ell
        r = minimize(nlp, zz, method="L-BFGS-B", bounds=[(None if not math.isfinite(a) else a,
                                                         None if not math.isfinite(b) else b) for a, b in bnds])
        if best is None or r.fun < best.fun:
            best = r
    assert best is not None
    th, sd_d, ell, se = unpack(np.asarray(best.x, dtype=float))
    C = C_of(sd_d, ell, se)
    Ci = np.linalg.inv(C)
    J = _jac(lambda t: eta(t), th, lo, hi)
    H = J.T @ Ci @ J + np.diag(1.0 / ps ** 2)
    cov = np.linalg.inv(H)
    res = y - eta(th)
    K = sd_d ** 2 * np.exp(-0.5 * D2 / ell ** 2)
    dmean = K @ Ci @ res
    notes = ["MAP + Laplace (hiperparâmetros fixos no MAP; abordagem modular, Bayarri et al. 2007); não é MCMC",
             "θ e δ só se separam pelo prior: a posterior de θ depende dos priors declarados"]
    prior_shift = np.abs(th - pm) / ps
    at_b = [q.name for i, q in enumerate(spec.parameters)
            if (math.isfinite(lo[i]) and abs(th[i] - lo[i]) < 1e-9 * max(1, abs(lo[i]))) or
            (math.isfinite(hi[i]) and abs(th[i] - hi[i]) < 1e-9 * max(1, abs(hi[i])))]
    disc = {"kernel": "exponencial quadrática (entradas normalizadas a [0, 1])", "inputs": dins,
            "sd": sd_d, "length_scale_norm": ell, "noise_sd": float(se.mean()),
            "noise_source": "hiperparametro" if noise_hyper else "instrumento",
            "mean_at_data_rms": float(np.sqrt(np.mean(dmean ** 2))),
            "residual_after_discrepancy_rms": float(np.sqrt(np.mean((res - dmean) ** 2))),
            "posterior_prior_ratio_sd": [float(v) for v in np.sqrt(np.diag(cov)) / ps],
            "prior_shift_sigma": [float(v) for v in prior_shift]}
    return FitResult("koh", spec.names, th, cov, n - p, n, nd, "hiperparametro" if noise_hyper else "instrumento",
                     None, None, None, float(np.sqrt(np.mean(res ** 2))), res, eta(th), y, None if noise_hyper else se,
                     x, at_b, True, notes, disc)


def predict(spec: ModelSpec, theta: Sequence[float], x: Mapping[str, Sequence[float] | float]) -> Array:
    env: dict[str, Any] = dict(spec.constants)
    env.update({k: np.asarray(v, dtype=float) for k, v in x.items()})
    env.update({q.name: float(theta[i]) for i, q in enumerate(spec.parameters)})
    return eval_model(compile_model(spec.expr), env)
