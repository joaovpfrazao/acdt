"""Camada de incerteza + sensibilidade (docs/INCERTEZA.md): distribuições, propagação, Sobol/Morris, P(passa)."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pytest

from acdt.core import verification as V
from acdt.core.sensitivity import distributions as D
from acdt.core.sensitivity import gsa, stats
from acdt.core.sensitivity import surrogate as SG
from acdt.core.sensitivity.sobol import ISHIGAMI_ANALYTIC, ishigami
from acdt.core.sensitivity.study import Sample, parse_spec, run_study

ROOT = Path(__file__).resolve().parents[1]


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# ------------------------------------------------------------------ declaração
def test_source_required_and_pressuposto_label():
    with pytest.raises(D.UncertaintySpecError, match="source"):
        D.parse_input({"path": "a.b", "dist": "uniform", "low": 0, "high": 1})
    i = D.parse_input({"path": "a.b", "dist": "uniform", "low": 0, "high": 1, "pressuposto": "sem dados"})
    assert i.pressuposto and i.source.startswith("PRESSUPOSTO")
    j = D.parse_input({"path": "a.b", "dist": "normal", "cv": 0.1, "source": "Raymer 2018"}, nominal=2.0)
    assert j.params["mean"] == 2.0 and j.params["std"] == pytest.approx(0.2) and not j.pressuposto


def test_bad_specs():
    for bad in ({"path": "x", "dist": "beta", "source": "s"},
                {"path": "x", "dist": "uniform", "low": 1, "high": 1, "source": "s"},
                {"path": "x", "dist": "normal", "source": "s"},  # sem nominal nem mean
                {"path": "x", "dist": "triangular", "low": 0, "high": 1, "mode": 2, "source": "s"}):
        with pytest.raises(D.UncertaintySpecError):
            D.parse_input(bad)


def test_marginals_moments():
    ln = D.parse_input({"path": "a", "dist": "lognormal", "cv": 0.2, "source": "s"}, nominal=10.0)
    tri = D.parse_input({"path": "b", "dist": "triangular", "low": 0, "high": 3, "mode": 0, "source": "s"})
    nor = D.parse_input({"path": "c", "dist": "normal", "mean": 5, "std": 2, "source": "s"})
    d = D.sample([ln, tri, nor], 20000, method="lhs", seed=1)
    x = d.values
    assert x[:, 0].mean() == pytest.approx(10.0, rel=0.01)  # média lognormal = nominal (Ang & Tang)
    assert x[:, 0].std() / x[:, 0].mean() == pytest.approx(0.2, rel=0.03)
    assert x[:, 1].mean() == pytest.approx(1.0, rel=0.01)  # (a+b+c)/3
    assert x[:, 2].std() == pytest.approx(2.0, rel=0.02)


def test_lhs_stratified():
    u = D.unit_sample(50, 3, "lhs", np.random.default_rng(0))
    for j in range(3):
        assert sorted(np.floor(u[:, j] * 50).astype(int)) == list(range(50))


def test_iman_conover_rank_correlation():
    a = D.parse_input({"path": "a", "dist": "normal", "mean": 1, "std": 0.1, "source": "s"})
    b = D.parse_input({"path": "b", "dist": "uniform", "low": 0, "high": 1, "source": "s"})
    c = D.parse_correlations([{"a": "a", "b": "b", "rho": 0.7, "source": "s"}], [a, b])
    d = D.sample([a, b], 2000, seed=0, correlation=c)
    ra = np.argsort(np.argsort(d.values[:, 0]))
    rb = np.argsort(np.argsort(d.values[:, 1]))
    assert np.corrcoef(ra, rb)[0, 1] == pytest.approx(0.7, abs=0.05)
    # marginais intactas: a estratificação LHS da uniforme mantém-se
    assert sorted(np.floor(d.values[:, 1] * 2000).astype(int)) == list(range(2000))
    with pytest.raises(D.UncertaintySpecError):
        D.parse_correlations([{"a": "a", "b": "b", "rho": 0.7}], [a, b])  # sem origem


# ------------------------------------------------------------------ estatísticas
def test_wilson_and_percentile_ci():
    lo, hi = stats.wilson(0, 10)  # Agresti & Coull 1998: 0/10 → [0, 0.278]
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-3)
    lo, hi = stats.wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3) and hi == pytest.approx(0.7634, abs=1e-3)
    x = np.random.default_rng(0).normal(10, 1, 2000)
    sm = stats.summarize(list(x))
    lo, hi = sm["p95_ic"]
    assert lo < 10 + 1.6449 < hi
    assert sm["converged"] and sm["running_mean"][-1]["n"] == 2000
    assert stats.summarize([1.0])["status"] == "nao_avaliado"


def test_probabilistic_status_rules():
    q = stats.probabilistic_status({"passa": 100}, 100, target=0.9, conf=0.95)
    assert q["estado_probabilistico"] == "prob_passa"
    q = stats.probabilistic_status({"passa": 50, "falha": 50}, 100, target=0.9, conf=0.95)
    assert q["estado_probabilistico"] == "prob_falha"
    q = stats.probabilistic_status({"passa": 9, "falha": 1}, 10, target=0.9, conf=0.95)
    assert q["estado_probabilistico"] == "inconclusivo"
    q = stats.probabilistic_status({"nao_avaliado": 10}, 10, target=0.9, conf=0.95)
    assert q["estado_probabilistico"] == "nao_avaliado" and q["p_passa"] is None
    q = stats.probabilistic_status({"desconhecido": 10}, 10, target=0.9, conf=0.95)
    assert q["estado_probabilistico"] == "desconhecido"
    # amostras falhadas e no_limite não contam como passa (não avaliado ≠ passa)
    q = stats.probabilistic_status({"passa": 90, "falhou": 5, "no_limite": 5}, 100, target=0.5, conf=0.95)
    assert q["p_passa"] == pytest.approx(0.90) and q["p_no_limite"] == pytest.approx(0.05)


# ------------------------------------------------------------------ sensibilidade global
def _ish_inputs() -> list[D.UncertainInput]:
    return [D.parse_input({"path": f"x{i}", "dist": "uniform", "low": -math.pi, "high": math.pi,
                           "source": "Ishigami & Homma 1990"}) for i in (1, 2, 3)]


def _ish(points: Sequence[Mapping[str, float]]) -> list[Mapping[str, float] | None]:
    return [{"Y": ishigami(p["x1"], p["x2"], p["x3"])} for p in points]


def test_sobol_ishigami_analytic():
    """Valores analíticos de Ishigami (a=7, b=0,1; Saltelli et al. 2008 Primer / Homma & Saltelli 1996)."""
    r = gsa.sobol(_ish_inputs(), _ish, ["Y"], n=8192, seed=11)
    by = {x["variable"]: x for x in r["metrics"]["Y"]["indices"]}
    for v in ("x1", "x2", "x3"):
        assert by[v]["S1"] == pytest.approx(ISHIGAMI_ANALYTIC["S1"][v], abs=0.04)
        assert by[v]["ST"] == pytest.approx(ISHIGAMI_ANALYTIC["ST"][v], abs=0.04)
    assert r["n_evaluations"] == 8192 * 5


def test_sobol_linear_nonuniform_inputs():
    """Y = 2a + b com a~N(0,1), b~N(0,2): S_a = 4/(4+4) = 0,5 exato; sem interações → S1 = ST."""
    a = D.parse_input({"path": "a", "dist": "normal", "mean": 0, "std": 1, "source": "s"})
    b = D.parse_input({"path": "b", "dist": "normal", "mean": 0, "std": 2, "source": "s"})
    r = gsa.sobol([a, b], lambda pts: [{"Y": 2 * p["a"] + p["b"]} for p in pts], ["Y"], n=4096, seed=2)
    by = {x["variable"]: x for x in r["metrics"]["Y"]["indices"]}
    assert by["a"]["S1"] == pytest.approx(0.5, abs=0.05) and by["a"]["ST"] == pytest.approx(0.5, abs=0.05)


def test_sobol_constant_output_unassessed():
    r = gsa.sobol(_ish_inputs(), lambda pts: [{"Y": 1.0} for _ in pts], ["Y"], n=16, seed=0)
    assert r["metrics"]["Y"]["status"] == "nao_avaliado"


def test_morris_linear_exact():
    """Para Y = Σ c_i x_i com x_i ~ U(0, 1), cada EE = c_i exatamente: μ* = |c_i|, σ = 0 (Morris 1991)."""
    c = {"a": 3.0, "b": -1.0, "c": 0.0}
    ins = [D.parse_input({"path": k, "dist": "uniform", "low": 0, "high": 1, "source": "s"}) for k in c]
    r = gsa.morris(ins, lambda pts: [{"Y": sum(c[k] * p[k] for k in c)} for p in pts], ["Y"], r=6, levels=4,
                   seed=3)
    eff = {e["variable"]: e for e in r["metrics"]["Y"]["effects"]}
    for k, v in c.items():
        assert eff[k]["mu_star"] == pytest.approx(abs(v), abs=1e-9)
        assert eff[k]["sigma"] == pytest.approx(0.0, abs=1e-9)
    assert [e["variable"] for e in r["metrics"]["Y"]["effects"]][0] == "a"
    assert r["n_evaluations"] == 6 * 4


def test_morris_ishigami_ranking():
    """Rastreio: x3 só atua por interação com x1 → σ/μ* alto; o ranking põe x1 e x2 à frente de x3 em μ."""
    r = gsa.morris(_ish_inputs(), _ish, ["Y"], r=60, levels=4, seed=5)
    eff = {e["variable"]: e for e in r["metrics"]["Y"]["effects"]}
    assert abs(eff["x3"]["mu"]) < eff["x3"]["mu_star"]
    assert eff["x3"]["sigma"] > 0


# ------------------------------------------------------------------ estudo com modelo de brinquedo
class Toy:
    """y = a + b; requisito R1: y ≤ 1,5; R2: bool sem avaliador → nao_avaliado."""

    def __init__(self) -> None:
        self.calls = 0

    def nominal(self, path: str) -> float | None:
        return {"a": 1.0, "b": 0.0}.get(path)

    def run(self, points: Sequence[Mapping[str, float]]) -> list[Sample]:
        out = []
        for p in points:
            self.calls += 1
            y = p["a"] + p.get("b", 0.0) + p.get("c", 0.0)
            if not math.isfinite(y):
                out.append(Sample(False, message="x"))
                continue
            out.append(Sample(True, {"y": y, "req:R1": y},
                              {"R1": {"status": "passa" if y <= 1.5 else "falha", "value": y},
                               "R2": {"status": "nao_avaliado", "value": None}}))
        return out

    def describe(self) -> dict[str, Any]:
        return {"text": "brinquedo"}

    def requirement_defs(self) -> list[V.TracedRequirement]:
        return [V.TracedRequirement(id="R1", text="y ≤ 1,5", quantity="y", comparison="max", threshold=1.5)]


def _matrix() -> dict[str, Any]:
    reqs = [V.TracedRequirement(id="R1", text="y", quantity="y", comparison="max", threshold=1.5,
                                evaluator="resultado:y"),
            V.TracedRequirement(id="R2", text="z", quantity="z", comparison="bool")]
    return V.build_matrix(reqs, V.VerificationContext(result={"y": 1.0}))


def test_study_pass_probability_analytic(tmp_path):
    """a ~ N(1, 0,5): P(y ≤ 1,5) = Φ(1) = 0,841 — dentro do IC de Wilson; estado determinístico intacto."""
    u = {"n": 400, "seed": 3, "target_probability": 0.8, "target_source": "teste",
         "inputs": [{"path": "a", "dist": "normal", "std": 0.5, "source": "teste"}]}
    toy = Toy()
    spec = parse_spec(u, toy.nominal)
    m0 = _matrix()
    r = run_study(spec, toy, outdir=tmp_path, nominal_matrix=m0, plots=False)
    q = r["propagation"]["requirements"]["R1"]
    lo, hi = q["p_passa_ic"]
    assert lo <= _norm_cdf(1.0) <= hi
    assert r["propagation"]["requirements"]["R2"]["estado_probabilistico"] == "nao_avaliado"
    rows = {x["id"]: x for x in r["verification_matrix"]["rows"]}
    assert rows["R1"]["status"] == "passa"  # determinístico não muda
    assert rows["R1"]["estado_probabilistico"] in ("prob_passa", "inconclusivo")
    assert {x["id"]: x["status"] for x in m0["rows"]} == {k: v["status"] for k, v in rows.items()}
    sm = r["propagation"]["summaries"]["y"]
    assert sm["p50"] == pytest.approx(1.0, abs=0.08) and sm["p95"] == pytest.approx(1 + 1.6449 * 0.5, abs=0.12)
    files = {p.name for p in tmp_path.iterdir()}
    assert {"uq.json", "uq.md", "verification_matrix.json", "verification_matrix.md",
            "verification_matrix.csv"} <= files
    assert "estado_probabilistico" in (tmp_path / "verification_matrix.csv").read_text(encoding="utf-8")
    md = (tmp_path / "uq.md").read_text(encoding="utf-8")
    assert "P(passa)" in md and "R1" in md
    js = json.loads((tmp_path / "uq.json").read_text(encoding="utf-8"))
    assert js["schema"] == "acdt.uq/1" and js["settings"]["seed"] == 3


def test_study_interval_envelope():
    """Intervalo b ∈ [0, 0,5] sem distribuição → ciclo exterior em 2 extremos; P(passa) em [mín, máx]."""
    u = {"n": 200, "seed": 1, "inputs": [
        {"path": "a", "dist": "normal", "std": 0.5, "source": "teste"},
        {"path": "b", "dist": "interval", "low": 0.0, "high": 0.5, "pressuposto": "só o intervalo é conhecido"}]}
    toy = Toy()
    spec = parse_spec(u, toy.nominal)
    assert any("probabilidade-alvo" in p for p in spec.pressupostos)  # alvo por omissão marcado
    r = run_study(spec, toy, plots=False)
    assert len(r["propagation"]["runs"]) == 2 and toy.calls == 400
    q = r["propagation"]["requirements"]["R1"]
    assert q["intervalo"] and q["p_passa"][0] < q["p_passa"][1]
    assert q["p_passa"][0] == pytest.approx(0.5, abs=0.1) and q["p_passa"][1] == pytest.approx(0.84, abs=0.08)
    sm = r["propagation"]["summaries"]["y"]
    assert sm["p50"][1] - sm["p50"][0] == pytest.approx(0.5, abs=0.05)


def test_study_surrogate_quadratic(tmp_path):
    """Substituto: y linear → Q² ≈ 1, aceite; P(passa) e Sobol pelo substituto; poucas corridas do modelo."""
    u = {"n": 2000, "seed": 4, "target_probability": 0.8, "target_source": "teste",
         "inputs": [{"path": "a", "dist": "normal", "std": 0.5, "source": "teste"},
                    {"path": "c", "dist": "uniform", "low": -0.1, "high": 0.1, "source": "teste"}],
         "surrogate": {"n_train": 20, "q2_min": 0.99}, "sobol": {"n": 8192}}
    toy = Toy()
    spec = parse_spec(u, toy.nominal)
    r = run_study(spec, toy, outdir=tmp_path, nominal_matrix=_matrix(), plots=False)
    assert toy.calls == 20  # o resto corre no substituto
    assert r["surrogate"]["accepted"]["y"]["Q2"] > 0.999
    q = r["propagation"]["requirements"]["R1"]
    assert q["fonte"] == "substituto"
    assert q["p_passa"] == pytest.approx(0.83, abs=0.04)
    assert r["propagation"]["requirements"]["R2"]["fonte"].startswith("modelo")
    by = {x["variable"]: x for x in r["sobol"]["metrics"]["y"]["indices"]}
    # Var(a) = 0,25, Var(c) = 0,2²/12 → S_a = 0,25/(0,25+0,00333) = 0,987
    assert by["a"]["ST"] == pytest.approx(0.987, abs=0.03)


def test_surrogate_rejects_poor_fit():
    rng = np.random.default_rng(0)
    x = rng.random((30, 2))
    y = np.sign(np.sin(40 * x[:, 0]))  # descontínuo: um quadrático não o representa
    s = SG.build(x, [{"y": float(v)} for v in y], ["a", "b"], 0.95)
    assert "y" in s.rejected and "y" not in s.models


def test_attach_probabilistic_parent_aggregation():
    reqs = [V.TracedRequirement(id="P", text="pai", quantity="", comparison="bool"),
            V.TracedRequirement(id="C1", text="f", quantity="y", comparison="max", threshold=1.0,
                                evaluator="resultado:y", parents=("P",))]
    m = V.build_matrix(reqs, V.VerificationContext(result={"y": 0.5}))
    out = V.attach_probabilistic(m, {"C1": {"p_passa": 0.7, "p_passa_ic": [0.6, 0.8],
                                            "estado_probabilistico": "prob_falha"}})
    rows = {r["id"]: r for r in out["rows"]}
    assert rows["P"]["estado_probabilistico"] == "prob_falha"
    assert rows["C1"]["status"] == "passa"
    assert "Estado prob." in V.to_markdown(out) and "Estado prob." not in V.to_markdown(m)
    assert "estado_probabilistico" not in V.to_csv(m)


# ------------------------------------------------------------------ domínio aircraft
def test_calibration_factors_as_uncertain_inputs(tmp_path):
    from acdt.domains.aircraft.uq_run import calibration_inputs

    cal = {"factors": {
        "k_clmax": {"group": "aero", "value": 1.10, "gci_fine": 0.04},
        "k_EI": {"group": "structures", "value": 1.2},  # sem GCI → não propagado
        "k_flutter": {"group": "flutter", "value": 1.3, "gci_fine": 0.02},  # grupo não aplicado
        "k_cd_profile": {"group": "aero", "value": 1.4, "valid": False, "invalid_reason": "outra grandeza"}}}
    f = tmp_path / "calibration.json"
    f.write_text(json.dumps(cal), encoding="utf-8")
    raw = {"assumptions": {"calibration": {"apply": ["aero", "structures"]}}}
    ins, exc = calibration_inputs(raw, {"file": "calibration.json"}, tmp_path)
    assert [i.path for i in ins] == ["assumptions.calibration.factors.k_clmax"]
    lo, hi = ins[0].bounds() or (0.0, 0.0)
    assert lo == pytest.approx(1.10 * 0.96) and hi == pytest.approx(1.10 * 1.04)
    assert ins[0].pressuposto and "GCI" in ins[0].source
    why = {e["name"]: e["reason"] for e in exc}
    assert "sem GCI" in why["k_EI"] and "apply" in why["k_flutter"] and "não aplicável" in why["k_cd_profile"]


def test_h1_record_nao_aplicar_never_propagated():
    from acdt.domains.aircraft.uq_run import calibration_inputs

    h1 = ROOT / "examples" / "output" / "uav150_flying_wing_tailless_hifi_win" / "h1_wing_gci.json"
    if not h1.is_file():
        pytest.skip("registo H1 do exemplo ausente")
    raw = {"assumptions": {"calibration": {"apply": ["aero"]}}}
    ins, exc = calibration_inputs(raw, {"file": str(h1)}, ROOT)
    assert ins == [] and exc and all("nao_aplicar" in e["reason"] for e in exc)


def test_set_path_and_nominal():
    from acdt.domains.aircraft.uq_run import nominal_of, set_path

    raw: dict[str, Any] = {"requirements": {"endurance": {"min": 10, "unit": "h"}},
                           "assumptions": {"calibration": {"factors": {"k_clmax": {"value": 1.1, "group": "aero"}}}}}
    assert nominal_of(raw, "requirements.endurance") == 10
    assert nominal_of(raw, "assumptions.aero.mu_roll") == 0.04  # valor por omissão do domínio
    assert nominal_of(raw, "assumptions.nada.x") is None
    set_path(raw, "assumptions.calibration.factors.k_clmax", 1.2)
    assert raw["assumptions"]["calibration"]["factors"]["k_clmax"] == {"value": 1.2, "group": "aero"}
    set_path(raw, "requirements.endurance", 12.0)
    assert raw["requirements"]["endurance"]["min"] == 12.0


def test_aircraft_uq_small(tmp_path):
    """Estrutura do estudo no pipeline real (handbook, N pequeno): nominal, percentis, P(passa), Morris, ficheiros."""
    import yaml

    from acdt.domains.aircraft.uq_run import run_uq

    spec = {"uncertainty": {"n": 4, "seed": 2, "model": {"workers": 1, "fidelity": "handbook",
                                                         "skip_stages": ["aeroelasticity"]},
                            "inputs": [{"path": "assumptions.weights.components.growth_allowance",
                                        "dist": "uniform", "low": 0.0, "high": 0.1, "pressuposto": "teste"}],
                            "metrics": ["W0_kg", "req:REQ-mtow"], "morris": {"r": 1}}}
    f = tmp_path / "uq.yaml"
    f.write_text(yaml.safe_dump(spec), encoding="utf-8")
    r = run_uq(ROOT / "examples" / "uav_endurance_payload.yaml", tmp_path / "out", uq_file=f, plots=False)
    assert r["nominal"]["ok"] and r["settings"]["seed"] == 2
    sm = r["propagation"]["summaries"]["W0_kg"]
    assert sm["status"] == "ok" and sm["min"] < sm["max"]  # a margem de crescimento muda o W0
    assert r["morris"]["metrics"]["W0_kg"]["effects"][0]["mu_star"] > 0
    q = r["propagation"]["requirements"]["REQ-mtow"]
    assert q["estado_probabilistico"] in stats.PROB_STATUSES
    vm = json.loads((tmp_path / "out" / "verification_matrix.json").read_text(encoding="utf-8"))
    assert all("estado_probabilistico" in row for row in vm["rows"])


def test_cli_uq_without_section_exits_2(tmp_path):
    from acdt.cli import main

    assert main(["uq", str(ROOT / "examples" / "uav_endurance_payload.yaml"), "-o", str(tmp_path)]) == 2


# ------------------------------------------------------------------ correções do estudo de exemplo (eng-uq-fixes)
def test_training_contains_interval_extremes_no_spurious_extrapolation():
    """Bug: o LHS de treino deixava o intervalo a até 1/n dos extremos e a propagação avalia-o só nos extremos →
    100 % «fora da caixa». O treino inclui agora os extremos; a fração por entrada fica reportada."""
    u = {"n": 400, "seed": 3, "target_probability": 0.5, "target_source": "teste",
         "inputs": [{"path": "a", "dist": "uniform", "low": 0.5, "high": 1.5, "source": "teste"},
                    {"path": "b", "dist": "interval", "low": 0.0, "high": 0.5, "pressuposto": "só intervalo"}],
         "surrogate": {"n_train": 24, "q2_min": 0.99}}
    toy = Toy()
    r = run_study(parse_spec(u, toy.nominal), toy, plots=False)
    tr_b = [p["inputs"]["b"] for p in r["training_samples"]]
    assert min(tr_b) == 0.0 and max(tr_b) == 0.5
    per = r["surrogate"]["extrapolacao_por_entrada"]
    assert per["b"]["fracao"] == 0.0
    # uniforme limitada: o LHS de treino com 24 pontos deixa ≈ 2/25 fora (nunca 100 %)
    assert 0.0 < per["a"]["fracao"] < 0.15 and per["a"]["excursao_max"] < 0.1
    assert r["surrogate"]["fracao_extrapolada"] == pytest.approx(per["a"]["fracao"])


def test_probabilistic_no_limite_state_and_intervals():
    q = stats.probabilistic_status({"no_limite": 4000}, 4000, target=0.9, conf=0.95)
    assert q["estado_probabilistico"] == "prob_no_limite"
    assert q["p_passa"] == 0.0 and q["p_no_limite"] == 1.0 and q["p_falha"] == 0.0
    assert q["p_no_limite_ic"][0] > 0.99 and q["p_falha_ic"][1] < 0.01
    q = stats.probabilistic_status({"no_limite": 50, "falha": 50}, 100, target=0.9, conf=0.95)
    assert q["estado_probabilistico"] == "prob_falha"
    assert "prob_no_limite" in stats.PROB_STATUSES


def test_envelope_keeps_no_limite_falha_and_ci():
    """Com intervalos (ciclo exterior) P(no_limite), P(falha) e o IC já não se perdem no envelope."""
    u = {"n": 300, "seed": 1, "target_probability": 0.5, "target_source": "teste", "inputs": [
        {"path": "a", "dist": "normal", "std": 0.5, "source": "teste"},
        {"path": "b", "dist": "interval", "low": 0.0, "high": 0.5, "pressuposto": "só o intervalo é conhecido"}]}
    toy = Toy()
    r = run_study(parse_spec(u, toy.nominal), toy, plots=False)
    q = r["propagation"]["requirements"]["R1"]
    assert q["intervalo"] and isinstance(q["p_falha"], list) and isinstance(q["p_no_limite"], list)
    assert q["p_passa_ic"][0] <= q["p_passa"][0] <= q["p_passa"][1] <= q["p_passa_ic"][1]
    assert q["p_falha"][0] == pytest.approx(1 - q["p_passa"][1], abs=1e-12)
    vm = V.attach_probabilistic(_matrix(), r["propagation"]["requirements"])
    row = {x["id"]: x for x in vm["rows"]}["R1"]
    assert row["p_falha"] is not None and "p_no_limite" in V.to_csv(vm)


def test_sobol_large_mean_offset_centering():
    """Bug: sem centragem, o S1 de Saltelli 2010 tem ruído ≈ (|média|/σ)·√(2ST/N): W0 ≈ 150 kg com σ ≈ 7 dava
    ΣS1 = 1,01 e S1 > ST. Ishigami + 10⁴ tem de dar os valores analíticos (Sobol' 2001: subtrair f0)."""
    def f(points: Sequence[Mapping[str, float]]) -> list[Mapping[str, float] | None]:
        return [{"Y": 1e4 + ishigami(p["x1"], p["x2"], p["x3"])} for p in points]

    r = gsa.sobol(_ish_inputs(), f, ["Y"], n=4096, seed=5, bootstrap=100)
    res = r["metrics"]["Y"]
    by = {x["variable"]: x for x in res["indices"]}
    for v in ("x1", "x2", "x3"):
        assert by[v]["S1"] == pytest.approx(ISHIGAMI_ANALYTIC["S1"][v], abs=0.05)
        assert by[v]["ST"] == pytest.approx(ISHIGAMI_ANALYTIC["ST"][v], abs=0.05)
    assert res["consistente"] and not res["avisos"]
    assert res["sum_S1_ic"][0] <= 1.0


def test_sobol_consistency_warning():
    """Amostra que viola S1 ≤ ST (f(A_B) = f(A) + 0,3·f(B): ST ≈ 0,045, S1 ≈ 0,3) → aviso, nunca corrigido em silêncio."""
    rng = np.random.default_rng(0)
    ya, yb = rng.normal(size=200), rng.normal(size=200)
    res = gsa.sobol_from_y(ya, yb, [ya + 0.3 * yb], ["x"])
    assert res["status"] == "ok" and res["indices"][0]["S1"] > res["indices"][0]["ST"] + 0.1
    assert not res["consistente"] and "S1" in res["avisos"][0]


def test_sobol_negligible_negative_not_warned():
    """Entrada sem efeito: S1 ≈ −1e-6 com IC todo negativo mas desprezável → sem aviso (folga 0,01)."""
    rng = np.random.default_rng(1)
    ya, yb = rng.normal(size=400), rng.normal(size=400)
    res = gsa.sobol_from_y(ya, yb, [ya - 1e-6 * yb], ["x"], bootstrap=50)
    assert res["consistente"], res["avisos"]
