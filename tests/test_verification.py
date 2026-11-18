"""Requisitos rastreáveis e matriz de verificação (acdt.core.verification). Testes independentes da máquina:
estrutura, lógica dos estados e ligação à proveniência — sem números do dimensionamento."""
import csv
import io
import json
from pathlib import Path

import pytest

from acdt.core import verification as V
from acdt.core.requirements import parse_requirement
from acdt.domains.aircraft import verification_evaluators  # noqa: F401  (regista os avaliadores)
from acdt.domains.aircraft.mission import MissionSpec
from acdt.domains.aircraft.verification_run import traced_requirements

EX = Path(__file__).parents[1] / "examples"


def R(id="R1", comp="max", thr=100.0, tol=0.0, ev="resultado:x", fid="N0", parents=(), goal=None):
    return V.TracedRequirement(id=id, text=id, quantity="q", comparison=comp, threshold=thr, tolerance=tol,
                               evaluator=ev, fidelity=fid, parents=tuple(parents), goal=goal)


def status(req, ev):
    return V.classify(req, ev)[0]


@pytest.mark.parametrize("comp,value,tol,expected", [
    ("max", 90.0, 0.0, "passa"), ("max", 110.0, 0.0, "falha"), ("max", 100.0, 0.0, "passa"),
    ("max", 101.0, 0.02, "no_limite"), ("max", 99.0, 0.02, "no_limite"), ("max", 97.0, 0.02, "passa"),
    ("max", 103.0, 0.02, "falha"), ("min", 110.0, 0.0, "passa"), ("min", 90.0, 0.0, "falha"),
    ("min", 99.5, 0.01, "no_limite"), ("target", 100.0, 0.0, "passa"), ("target", 101.0, 0.0, "falha"),
    ("target", 101.0, 0.02, "passa"),
])
def test_numeric_statuses(comp, value, tol, expected):
    assert status(R(comp=comp, tol=tol), V.Evidence(value)) == expected


def test_margin_sign_and_resolution_band():
    st, m, _ = V.classify(R(comp="max"), V.Evidence(80.0))
    assert st == "passa" and m == pytest.approx(0.2)
    st, m, msg = V.classify(R(comp="min"), V.Evidence(99.95, resolution=1e-3, resolution_source="x"))
    assert st == "no_limite" and m < 0 and "resolução" in msg


def test_never_pass_without_evaluator_or_data():
    r = R()
    assert status(r, V.Evidence(ran=False)) == "nao_avaliado"
    assert status(r, V.Evidence(None)) == "desconhecido"
    assert status(r, V.Evidence(float("nan"))) == "desconhecido"
    assert status(r, V.Evidence("texto")) == "desconhecido"
    b = R(comp="bool", thr=None)
    assert status(b, V.Evidence(None, ok=None)) == "desconhecido"
    assert status(b, V.Evidence(None, ok=True)) == "passa"
    assert status(b, V.Evidence(None, ok=False)) == "falha"
    assert status(R(comp="objetivo", thr=None), V.Evidence(5.0)) == "nao_avaliado"
    # avaliador só com veredicto num requisito numérico
    assert status(r, V.Evidence(None, ok=False)) == "falha"


def test_evaluate_missing_unregistered_broken_and_fidelity():
    def boom(req, ctx, arg):
        raise RuntimeError("x")
    V.register_evaluator(V.Evaluator("teste:boom", boom, "falha de propósito"), overwrite=True)
    reqs = [R("A", ev=None), R("B", ev="nao:existe"), R("C", ev="teste:boom"), R("D", ev="resultado:x", fid="N2"),
            R("E", ev="resultado:y.z"), R("F", ev="resultado:x")]
    rows = {r.id: r for r in V.evaluate(reqs, V.VerificationContext(result={"x": 50.0}, evidence_file="r.json"))}
    assert rows["A"].status == "nao_avaliado" and rows["B"].status == "nao_avaliado"
    assert rows["C"].status == "desconhecido" and "RuntimeError" in rows["C"].message
    assert rows["D"].status == "nao_avaliado" and "fidelidade" in rows["D"].message   # passaria, mas N0 < N2
    assert rows["E"].status == "nao_avaliado"
    assert rows["F"].status == "passa" and rows["F"].evidence == "r.json#x" and rows["F"].value == 50.0
    assert rows["A"].evidence == ""


def test_tree_aggregation_and_issues():
    reqs = [R("P", ev=None, comp="bool", thr=None), R("C1", parents=["P"]), R("C2", parents=["P"], ev=None),
            R("G", parents=["C1"])]
    rows = {r.id: r for r in V.evaluate(reqs, V.VerificationContext(result={"x": 1.0}))}
    assert rows["P"].aggregated_from_children and rows["P"].status == "nao_avaliado"   # C2 sem avaliador
    assert set(rows["P"].children) == {"C1", "C2"} and rows["C1"].children_worst == "passa"
    assert V.check_tree(reqs) == []
    assert any("ciclo" in x for x in V.check_tree([R("A", parents=["B"]), R("B", parents=["C"]),
                                                   R("C", parents=["A"])]))
    issues = " ".join(V.check_tree([R("A"), R("A"), R("X", parents=["nada"])]))
    assert "ID repetido: A" in issues and "pai desconhecido 'nada'" in issues


def test_aggregation_all_pass_and_one_fail():
    reqs = [R("P", ev=None, comp="bool", thr=None), R("C1", parents=["P"]), R("C2", parents=["P"])]
    rows = {r.id: r for r in V.evaluate(reqs, V.VerificationContext(result={"x": 1.0}))}
    assert rows["P"].status == "passa"
    rows = {r.id: r for r in V.evaluate(reqs, V.VerificationContext(result={"x": 1000.0}))}
    assert rows["P"].status == "falha"


def test_coverage_lists_gaps():
    reqs = [R("A", ev=None), R("B", ev="nao:existe"), R("C", ev="resultado:x")]
    rows = V.evaluate(reqs, V.VerificationContext(result={"x": 1.0}))
    cov = V.coverage(reqs, rows, ["resultado:x", "check:hq:roll"])
    assert cov["requisitos_sem_avaliador"] == ["A"] and cov["avaliadores_nao_registados"] == ["nao:existe"]
    assert cov["avaliadores_sem_requisito"] == ["check:hq:roll"]
    assert sum(cov["por_estado"].values()) == 3 and cov["por_estado"]["passa"] == 1


def test_invalid_requirements_rejected():
    with pytest.raises(V.VerificationError):
        R(comp="max", thr=None)
    with pytest.raises(V.VerificationError):
        V.TracedRequirement(id="X", text="", quantity="q", comparison="bool", method="palpite")
    with pytest.raises(V.VerificationError):
        V.from_dict({"id": "X", "comparison": "bool", "campo_errado": 1})
    with pytest.raises(V.VerificationError):
        V.si_convert(1.0, "g")        # massa ou adimensional: ambígua
    assert V.si_convert(1.0, "km") == (1000.0, "m")
    d = V.from_dict({"id": "X", "comparison": "max", "threshold": 1, "unit": "km", "method": "simulation"})
    assert d.threshold == 1000.0 and d.unit == "m" and d.method == "simulacao" and d.display == "≤ 1 km"


def test_trace_keys_do_not_change_the_requirement():
    a = parse_requirement("takeoff_ground_roll", {"max": 300, "unit": "m"})
    b = parse_requirement("takeoff_ground_roll", {"max": 300, "unit": "m", "id": "MIS-TO-01", "parent": "OPS",
                                                  "method": "analise", "fidelity": "N1", "tolerance": 0.02})
    assert (a.key, a.sense, a.value, a.unit) == (b.key, b.sense, b.value, b.unit)
    assert b.trace["id"] == "MIS-TO-01" and a.trace == {}
    c = parse_requirement("propulsion_type", {"target": "piston_prop", "id": "CFG"})
    assert c.value == "piston_prop" and c.trace == {"id": "CFG"}


@pytest.mark.parametrize("name", ["cessna172_check.yaml", "heavy/uav150_flying_wing_tailless.yaml"])
def test_example_missions_are_traceable(name):
    spec = MissionSpec.from_yaml(EX / name)
    reqs = traced_requirements(spec)
    ids = [r.id for r in reqs]
    assert len(ids) == len(set(ids)) and all(not i.startswith("REQ-") for i in ids)   # todos com ID explícito
    assert V.check_tree(reqs) == []
    assert all(r.method in V.METHODS and r.fidelity in V.FIDELITIES for r in reqs)
    # cada requisito da missão é rastreável a um avaliador registado, ou declarado sem avaliador (cobertura)
    for r in reqs:
        assert r.evaluator is None or V.resolve_evaluator(r.evaluator) is not None, r.id
    by = {r.id: r for r in reqs}
    if "tailless" in name:
        assert by["MIS-TO-01"].evaluator == "perf:takeoff_ground_roll" and by["MIS-TO-01"].parents == ("MIS-OPS-01",)
        assert by["REG-23233-01"].source_kind == "regulamento" and by["SORA-01"].evaluator is None


def _fake_result():
    return {"checks": [{"key": "hq:roll", "ok": True, "message": "ok"}, {"key": "hq:spiral", "ok": None,
                                                                         "message": "unassessed"},
                       {"key": "perf:range", "ok": True, "message": ""}],
            "performance": {"requirements": [{"requisito": "range", "grandeza": "d", "obtido": 1233.0,
                                              "requerido": 1185.0, "unidade": "km", "ok": True}]},
            "design_point": {"W_S_N_m2": 500.0}, "aero": {"CLmax_landing": 1.5},
            "weights": {"payload_kg": 30.0}}


def test_aircraft_evaluators_on_synthetic_result():
    ctx = V.VerificationContext(result=_fake_result(), evidence_file="result.json", domain="aircraft")
    reqs = [V.TracedRequirement("A", "", "range", "min", 1185e3, evaluator="perf:range"),
            V.TracedRequirement("B", "", "x", "bool", evaluator="check:hq:roll"),
            V.TracedRequirement("C", "", "x", "bool", evaluator="check:hq:spiral"),
            V.TracedRequirement("D", "", "x", "bool", evaluator="check:aeroel:flutter"),
            V.TracedRequirement("E", "", "stall_speed", "max", 30.0, evaluator="sizing:stall_speed"),
            V.TracedRequirement("F", "", "endurance", "min", 3600.0, evaluator="perf:endurance"),
            V.TracedRequirement("G", "", "payload_mass", "target", 30.0, evaluator="entrada:payload_mass",
                                method="inspecao")]
    rows = {r.id: r for r in V.evaluate(reqs, ctx)}
    assert rows["A"].status == "passa" and rows["A"].value == pytest.approx(1233e3) and rows["A"].unit == "m"
    assert rows["A"].value_display.endswith("km") and rows["A"].evidence == "result.json#performance.requirements[0]"
    assert rows["B"].status == "passa" and rows["C"].status == "desconhecido" and rows["D"].status == "nao_avaliado"
    vs = (2 * 500.0 / (1.225 * 1.5)) ** 0.5            # Raymer Eq. 5.6, f_ater = 1 (sem missão), nível do mar
    assert rows["E"].value == pytest.approx(vs, rel=1e-3) and rows["E"].status == "passa"
    assert "PRESSUPOSTO" in rows["E"].message
    assert rows["F"].status == "nao_avaliado" and rows["G"].status == "passa"
    orphan = V.available_evidence(ctx)
    assert "check:hq:roll" in orphan and "perf:range" in orphan and "check:perf:range" not in orphan


def test_matrix_files_and_provenance_link(tmp_path):
    from acdt.core import provenance as P
    (tmp_path / "result.json").write_text(json.dumps(_fake_result()), encoding="utf-8")
    rec = P.collect(probe_versions=False)
    rec2 = {**rec, "created": {"utc": "outro"}, "outputs": [{"path": "x"}], "notes": ["n"]}
    assert V.provenance_fingerprint(rec) == V.provenance_fingerprint(rec2)      # datas/manifesto não contam
    rec3 = {**rec, "seeds": {"s": 1}}
    assert V.provenance_fingerprint(rec) != V.provenance_fingerprint(rec3)
    (tmp_path / "provenance.json").write_text(json.dumps(rec), encoding="utf-8")
    ctx = V.context_from_output(tmp_path, domain="aircraft")
    assert ctx.provenance_fingerprint == V.provenance_fingerprint(rec) and ctx.provenance_sha256
    reqs = [V.TracedRequirement("A", "alcance", "range", "min", 1185e3, evaluator="perf:range"),
            V.TracedRequirement("B", "sem avaliador", "x", "bool")]
    m = V.verify(reqs, ctx, tmp_path)
    for f in V.MATRIX_FILES:
        assert (tmp_path / f).is_file()
    j = json.loads((tmp_path / "verification_matrix.json").read_text(encoding="utf-8"))
    assert j["schema"] == V.SCHEMA and j["coverage"]["por_estado"] == m["coverage"]["por_estado"]
    assert j["rows"][0]["evidence_sha256"] == P.sha256_file(tmp_path / "result.json")
    assert j["rows"][0]["provenance_fingerprint"] == ctx.provenance_fingerprint
    rows = list(csv.DictReader(io.StringIO((tmp_path / "verification_matrix.csv").read_text(encoding="utf-8"))))
    assert [r["id"] for r in rows] == ["A", "B"] and rows[1]["status"] == "nao_avaliado"
    md = (tmp_path / "verification_matrix.md").read_text(encoding="utf-8")
    assert "| A |" in md and "nao_avaliado" in md and "Cobertura" in md


def test_file_evaluator(tmp_path):
    (tmp_path / "sim").mkdir()
    (tmp_path / "sim" / "s.json").write_text(json.dumps({"to": {"roll_m": 320.0}}), encoding="utf-8")
    ctx = V.VerificationContext(result={}, output_dir=str(tmp_path))
    reqs = [R("A", thr=300.0, ev="ficheiro:sim/s.json#to.roll_m"), R("B", ev="ficheiro:nao/ha.json#x")]
    rows = {r.id: r for r in V.evaluate(reqs, ctx)}
    assert rows["A"].status == "falha" and rows["A"].evidence == "sim/s.json#to.roll_m" and rows["A"].evidence_sha256
    assert rows["B"].status == "nao_avaliado"


def test_cli_verify_missing_output(tmp_path, capsys):
    from acdt.cli import main
    assert main(["verify", str(EX / "cessna172_check.yaml"), str(tmp_path)]) == 2
