"""MDO de sistema (``acdt mdo``; docs/MDO.md): casos analíticos com ótimo/frente publicados."""
from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("openmdao")

from acdt.core.sysmdo import hypervolume_2d, knee_point, nondominated_sort, parse_spec, run_mdo  # noqa: E402
from acdt.core.sysmdo import expr as E  # noqa: E402
from acdt.core.sysmdo.spec import MDOSpecError  # noqa: E402
from acdt.core.sysmdo.toy import FunctionModel, sellar, zdt1  # noqa: E402

QUIET = (lambda s: None)

SELLAR_REQS = [{"id": "SEL-G1", "metric": "y1", "comparison": "min", "threshold": 3.16},
               {"id": "SEL-G2", "metric": "y2", "comparison": "max", "threshold": 24.0}]


def _sellar_spec(**kw):
    d = {"design_variables": [{"path": "x", "lower": 0, "upper": 10, "x0": 1, "source": "Sellar et al. 1996"},
                              {"path": "z1", "lower": -10, "upper": 10, "x0": 5, "source": "Sellar et al. 1996"},
                              {"path": "z2", "lower": 0, "upper": 10, "x0": 2, "source": "Sellar et al. 1996"}],
         "objectives": [{"metric": "obj", "sense": "min"}], "strategy": "slsqp",
         "options": {"maxiter": 100, "tol": 1e-9, "fd_step": 1e-6}, "constraints": {"policy": "limiar"}}
    d.update(kw)
    return parse_spec(d)


def test_sellar_slsqp_published_optimum():
    """OpenMDAO docs (Sellar MDF): f* = 3.18339395, z* = (1.97763888, 0), x* = 0, y1 = 3.16, y2 = 3.75527777.
    As restrições g1/g2 vêm do registo de requisitos (SEL-G1 y1 ≥ 3.16, SEL-G2 y2 ≤ 24)."""
    model = FunctionModel(sellar, {}, SELLAR_REQS, "Sellar")
    r = run_mdo(_sellar_spec(), model, log=QUIET)
    best = r["evaluations"][r["best"]["obj"]]
    assert best["feasible"]
    assert best["objectives"]["obj"] == pytest.approx(3.18339395, abs=2e-4)
    assert best["x"]["z1"] == pytest.approx(1.97763888, abs=5e-3)
    assert best["x"]["z2"] == pytest.approx(0.0, abs=5e-3)
    assert best["x"]["x"] == pytest.approx(0.0, abs=5e-3)
    assert best["metrics"]["y1"] == pytest.approx(3.16, abs=1e-3)
    assert best["requirements"]["SEL-G1"]["status"] in ("passa", "no_limite")
    names = [c["name"] for c in r["constraints"]]
    assert names == ["req:SEL-G1", "req:SEL-G2"]
    # cada avaliação tem o estado de cada requisito
    assert all(set(e["requirements"]) == {"SEL-G1", "SEL-G2"} for e in r["evaluations"] if e["ok"])


def test_policy_passa_pushes_beyond_tolerance_band():
    reqs = [dict(SELLAR_REQS[0], tolerance=0.01), SELLAR_REQS[1]]
    model = FunctionModel(sellar, {}, reqs)
    r = run_mdo(_sellar_spec(constraints={"policy": "passa"}), model, log=QUIET)
    best = r["evaluations"][r["best"]["obj"]]
    assert best["metrics"]["y1"] >= 3.16 * 1.01 - 1e-6
    assert best["requirements"]["SEL-G1"]["status"] == "passa"


def test_zdt1_nsga2_front():
    n = 5
    spec = parse_spec({"design_variables": [{"path": f"x{i}", "lower": 0, "upper": 1, "x0": 0.5, "source": "ZDT1"}
                                            for i in range(1, n + 1)],
                       "objectives": ["f1", "f2"], "strategy": "nsga2",
                       "options": {"pop_size": 40, "max_gen": 60, "seed": 3}})
    model = FunctionModel(zdt1, {"n": n}, [], "ZDT1")
    r = run_mdo(spec, model, log=QUIET)
    ev = {e["id"]: e for e in r["evaluations"]}
    F = np.array([[ev[i]["objectives"]["f1"], ev[i]["objectives"]["f2"]] for i in r["pareto"]])
    assert len(F) >= 20
    hv = hypervolume_2d(F, (1.1, 1.1))
    assert hv > 0.85  # frente verdadeira: 0.1 + 2/3 + 0.11 = 0.8767
    gap = F[:, 1] - (1.0 - np.sqrt(F[:, 0]))
    assert np.median(gap) < 0.02
    k = ev[r["knee"]["id"]]["objectives"]
    assert 0.1 < k["f1"] < 0.5  # joelho da curva 1 − √f₁ (Das 1999) no interior


def test_epsilon_constraint_convex_front():
    """min f1 = x²+y², f2 = (x−2)²+y²: frente y = 0, x ∈ [0, 2], f2 = (2 − √f1)² (Haimes et al. 1971)."""
    def fn(p):
        x, y = float(p["x"]), float(p["y"])
        return {"f1": x * x + y * y, "f2": (x - 2) ** 2 + y * y}
    spec = parse_spec({"design_variables": [{"path": "x", "lower": -1, "upper": 3, "x0": 1.0, "source": "t"},
                                            {"path": "y", "lower": -1, "upper": 1, "x0": 0.5, "source": "t"}],
                       "objectives": [{"metric": "f1", "ref": 1.0}, {"metric": "f2", "ref": 1.0}],
                       "strategy": "epsilon",
                       "options": {"n_points": 4, "maxiter": 60, "tol": 1e-9, "fd_step": 1e-6}})
    r = run_mdo(spec, FunctionModel(fn, {}), log=QUIET)
    ev = {e["id"]: e for e in r["evaluations"]}
    runs = r["loops"][0]["iterations"][0]["inner"]["runs"]
    pts = [ev[x["best"]]["objectives"] for x in runs if x.get("best") is not None]
    assert len(pts) >= 5
    for p in pts:
        assert p["f2"] == pytest.approx((2 - math.sqrt(max(p["f1"], 0))) ** 2, abs=2e-3)


def test_doe_and_outer_discrete_with_unknown_never_feasible():
    def fn(p):
        out = {"m": (float(p["a"]) - 1) ** 2 + float(p["k"])}
        if float(p["a"]) > 2.5:
            out["v"] = float("nan")  # valor desconhecido nesta região
        else:
            out["v"] = float(p["a"])
        return out
    spec = parse_spec({"design_variables": [{"path": "a", "lower": 0, "upper": 3, "source": "t"},
                                            {"path": "k", "type": "discrete", "values": [0.0, 5.0], "source": "t"}],
                       "objectives": ["m"], "strategy": "doe", "options": {"n": 12, "seed": 1},
                       "constraints": {"policy": "limiar"}})
    reqs = [{"id": "R-V", "metric": "v", "comparison": "max", "threshold": 2.0}]
    r = run_mdo(spec, FunctionModel(fn, {"a": 1.0, "k": 0.0}, reqs), log=QUIET)
    assert len(r["loops"]) == 2
    for e in r["evaluations"]:
        if e["x"]["a"] > 2.5:
            assert not e["feasible"] and e["requirements"]["R-V"]["status"] == "desconhecido"
    b = r["evaluations"][r["best"]["m"]]
    assert b["combo"]["k"] == 0.0 and b["feasible"]


def test_closure_fixed_point_fleet_toy():
    """Frota ↔ projeto: n aviões cobrem T = 24 h; requisito por avião endurance ≥ T/n; capacidade até 16 h.
    Partida n = 1 (inviável) → segue o de menor violação (16 h) → n = ceil(24/16) = 2 → converge."""
    def fn(p):
        s = float(p["s"])
        return {"endurance_h": s, "W0": 10 + s * s}
    spec = parse_spec({"design_variables": [{"path": "s", "lower": 1, "upper": 16, "x0": 4, "source": "t"}],
                       "objectives": ["W0"], "strategy": "slsqp", "constants": {"T": 24.0},
                       "constants_source": "teste",
                       "options": {"maxiter": 50, "fd_step": 1e-6},
                       "derived": {"fleet_mass": "ceil(T / endurance_h) * W0"},
                       "closure": {"name": "n", "x0": 1, "update": "ceil(T / endurance_h - 1e-6)",
                                   "apply": {"end_req": "T / n"}, "source": "teste"}})
    reqs = [{"id": "END", "metric": "endurance_h", "comparison": "min", "threshold_param": "end_req"}]
    r = run_mdo(spec, FunctionModel(fn, {"end_req": 24.0}, reqs), log=QUIET)
    lp = r["loops"][0]
    assert [it["closure_value"] for it in lp["iterations"]] == [1, 2]
    assert lp["closure_status"] == "convergiu"
    best = r["evaluations"][r["chosen"]]
    assert best["x"]["s"] == pytest.approx(12.0, abs=1e-3)
    assert best["metrics"]["fleet_mass"] == pytest.approx(2 * (10 + 144), rel=1e-3)


def test_robust_mean_k_sigma_on_surrogate():
    """y = (a − 1)² + u, u ~ U(−0,5; 0,5)·a → σ cresce com a; robust = média + 2σ desloca o ótimo para a < 1."""
    def fn(p):
        a, u = float(p["a"]), float(p["u"])
        return {"y": (a - 1) ** 2 + u * a}
    spec = parse_spec({"design_variables": [{"path": "a", "lower": 0.1, "upper": 2, "x0": 1.5, "source": "t"}],
                       "objectives": ["robust:y"], "strategy": "slsqp", "options": {"fd_step": 1e-4},
                       "robust": {"k": 2, "n": 400, "n_train": 30, "seed": 2, "metrics": ["y"],
                                  "inputs": [{"path": "u", "dist": "uniform", "low": -0.5, "high": 0.5,
                                              "source": "teste"}]}})
    r = run_mdo(spec, FunctionModel(fn, {"a": 1.0, "u": 0.0}), log=QUIET)
    b = r["evaluations"][r["best"]["robust:y"]]
    # média = (a−1)², σ = a/√12 → min (a−1)² + 2a/√12 → a* = 1 − 1/√12 ≈ 0.7113
    assert b["x"]["a"] == pytest.approx(1 - 1 / math.sqrt(12), abs=0.03)


def test_pareto_tools():
    F = np.array([[1, 5], [2, 3], [3, 4], [4, 1], [5, 5]], dtype=float)
    fr = nondominated_sort(F)
    assert sorted(fr[0]) == [0, 1, 3]
    i, _ = knee_point(F[[0, 1, 3]])
    assert i == 1
    fr2 = nondominated_sort(F, [0, 0, 1.0, 2.0, 0])
    assert 3 not in fr2[0]


def test_expr_and_spec_errors():
    assert E.evaluate("ceil(a / b) * 2", {"a": 5, "b": 2}) == 6
    assert E.evaluate("a + c", {"a": 1}) is None  # desconhecido ≠ zero
    with pytest.raises(E.ExprError):
        E.compile_expr("__import__('os')")
    with pytest.raises(MDOSpecError):
        parse_spec({"design_variables": [{"path": "x", "lower": 0, "upper": 1}], "objectives": ["a", "b"],
                    "strategy": "slsqp"})
    s = parse_spec({"design_variables": [{"path": "x", "lower": 0, "upper": 1}], "objectives": ["a"]})
    assert any("PRESSUPOSTO" in p for p in s.pressupostos)


@pytest.mark.slow
def test_real_pipeline_tiny_doe(tmp_path):
    """Pipeline aircraft real (handbook, sem aeroelasticidade), 3 avaliações: estado da matriz em cada uma,
    restrições geradas do registo, saídas escritas e matriz do projeto escolhido."""
    import json
    from pathlib import Path

    import yaml

    from acdt.domains.aircraft.mdo_system import run_mdo_mission

    root = Path(__file__).resolve().parents[1]
    mission = root / "examples" / "uav_150kg_stanag4671.yaml"
    spec = {"mdo": {"design_variables": [{"path": "assumptions.aero.AR", "lower": 7, "upper": 11,
                                          "source": "teste"}],
                    "objectives": ["W0_kg"], "strategy": "doe", "options": {"method": "full_factorial", "levels": 3},
                    "constraints": {"policy": "limiar"},
                    "model": {"fidelity": "handbook", "skip_stages": ["aeroelasticity"], "workers": 1}}}
    sp = tmp_path / "mdo.yaml"
    sp.write_text(yaml.safe_dump(spec), encoding="utf-8")
    r = run_mdo_mission(mission, tmp_path / "out", mdo_file=sp, plots=False, log=QUIET)
    assert r["n_evaluations"] == 3
    names = {c["name"] for c in r["constraints"]}
    assert "req:REQ-takeoff_ground_roll" in names and "req:REQ-endurance" in names
    assert "REQ-regulatory_category" in {f["id"] for f in r["filters"]}  # não numérico → filtro, não restrição
    for e in r["evaluations"]:
        assert e["ok"]
        assert e["requirements"]["REQ-propulsion_type"]["status"] == "nao_avaliado"  # nunca passa por omissão
    ws = sorted(e["metrics"]["W0_kg"] for e in r["evaluations"])
    assert ws[0] < ws[-1]  # AR muda o projeto
    out = tmp_path / "out"
    for f in ("mdo.json", "mdo.md", "evaluations.csv", "verification_matrix.json"):
        assert (out / f).exists(), f
    js = json.loads((out / "mdo.json").read_text(encoding="utf-8"))
    assert js["schema"] == "acdt.mdo/1" and js["chosen"] is not None


def test_fixed_overrides_and_no_effect_warning():
    def fn(p):
        return {"m": float(p["c"])}  # 'a' não é usada pelo modelo
    spec = parse_spec({"design_variables": [{"path": "a", "lower": 0, "upper": 1, "source": "t"}],
                       "objectives": ["m"], "strategy": "doe", "options": {"n": 4}, "fixed": {"c": 3.0}})
    r = run_mdo(spec, FunctionModel(fn, {"c": 1.0}), log=QUIET)
    assert r["evaluations"][0]["metrics"]["m"] == 3.0
    assert r["warnings"] and "não muda" in r["warnings"][0]


def test_requirement_as_design_variable_uses_point_threshold():
    """Um requisito que é variável de projeto: a margem usa o limiar DESSA avaliação, não o nominal."""
    def fn(p):
        return {"v": float(p["thr"]) + 0.5, "m": float(p["thr"])}
    reqs = [{"id": "R", "metric": "v", "comparison": "min", "threshold_param": "thr"}]

    class PerPoint(FunctionModel):
        def run(self, points):
            out = []
            for p in points:
                mm = FunctionModel(self.fn, {**self.params, **p}, self.reqs)
                out += FunctionModel.run(mm, [p])
            return out

        def with_overrides(self, overrides):
            return PerPoint(self.fn, {**self.params, **overrides}, self.reqs)

    spec = parse_spec({"design_variables": [{"path": "thr", "lower": 1, "upper": 5, "source": "t"}],
                       "objectives": [{"metric": "m", "sense": "max"}], "strategy": "doe", "options": {"n": 5}})
    r = run_mdo(spec, PerPoint(fn, {"thr": 1.0}, reqs), log=QUIET)
    assert all(e["feasible"] for e in r["evaluations"])
    assert all(e["constraints"]["req:R"] == pytest.approx(0.5 / e["x"]["thr"]) for e in r["evaluations"])


def test_requirement_outside_model_scope_is_reported_not_passed():
    """Requisito numérico que o modelo nunca avalia (nao_avaliado): não é restrição, fica nao_avaliado em cada
    projeto e aparece nos avisos; um requisito desconhecido continua a tornar o projeto inviável."""
    from acdt.core.sensitivity.study import Sample

    class M(FunctionModel):
        def run(self, points):
            out = FunctionModel.run(self, points)
            for s in out:
                s.requirements["SIM"] = {"status": "nao_avaliado", "value": None}
            return out

        def requirement_defs(self):
            from acdt.core.verification import TracedRequirement
            return FunctionModel.requirement_defs(self) + [TracedRequirement(
                id="SIM", text="6-DOF", quantity="x", comparison="max", threshold=300.0)]

        def with_overrides(self, o):
            return M(self.fn, {**self.params, **o}, self.reqs)

    spec = parse_spec({"design_variables": [{"path": "a", "lower": 0, "upper": 1, "source": "t"}],
                       "objectives": ["m"], "strategy": "doe", "options": {"n": 3}})
    r = run_mdo(spec, M(lambda p: {"m": float(p["a"])}, {}), log=QUIET)
    assert all(e["feasible"] for e in r["evaluations"])
    assert all(e["requirements"]["SIM"]["status"] == "nao_avaliado" for e in r["evaluations"])
    assert any("SIM" in w for w in r["warnings"])
    assert Sample  # usado no tipo
