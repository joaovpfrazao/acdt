import math

import pytest

from acdt.core.safety import BasicEvent, FaultTree, Gate, ac23_class, rate, stanag4703_cumulative_catastrophic, target
from acdt.core.safety.fmea import Component, FailureMode, fmea_rows, to_markdown


def _tree():
    ft = FaultTree("TOP", name="t")
    for e, lam in (("A", 1e-3), ("B", 2e-3), ("C", 1e-4)):
        ft.add_event(BasicEvent(e, rate_per_h=lam))
    ft.add_gate(Gate("G1", "AND", ["A", "B"]))
    ft.add_gate(Gate("TOP", "OR", ["G1", "C"]))
    return ft


def test_q_exponential():
    assert BasicEvent("x", rate_per_h=1e-3).q(10) == pytest.approx(1 - math.exp(-1e-2))
    assert BasicEvent("x", rate_per_h=1e-3, exposure_h=100, latent=True).q(1) == pytest.approx(1 - math.exp(-0.1))


def test_mcs_and_exact():
    ft = _tree()
    mcs = ft.minimal_cut_sets()
    assert set(mcs) == {frozenset({"C"}), frozenset({"A", "B"})}
    qa, qb, qc = (1 - math.exp(-l * 2) for l in (1e-3, 2e-3, 1e-4))
    exact = 1 - (1 - qa * qb) * (1 - qc)
    assert ft.top_probability(2) == pytest.approx(exact, rel=1e-12)
    assert ft.rare_event(2) >= ft.top_probability(2)
    assert ft.summary(2)["single_point_failures"] == ["C"]


def test_repeated_event_exact_and_absorption():
    # TOP = (A or B) and (A or C) = A or (B and C)
    ft = FaultTree("TOP")
    for e in "ABC":
        ft.add_event(BasicEvent(e, prob=0.1))
    ft.add_gate(Gate("G1", "OR", ["A", "B"]))
    ft.add_gate(Gate("G2", "OR", ["A", "C"]))
    ft.add_gate(Gate("TOP", "AND", ["G1", "G2"]))
    assert set(ft.minimal_cut_sets()) == {frozenset("A"), frozenset("BC")}
    assert ft.top_probability() == pytest.approx(0.1 + 0.9 * 0.01)


def test_k_of_n():
    ft = FaultTree("TOP")
    for e in "ABC":
        ft.add_event(BasicEvent(e, prob=0.1))
    ft.add_gate(Gate("TOP", "KOFN", list("ABC"), k=2))
    assert len(ft.minimal_cut_sets()) == 3
    assert ft.top_probability() == pytest.approx(3 * 0.01 * 0.9 + 0.001)


def test_importance_and_plot(tmp_path):
    ft = _tree()
    imp = ft.importance(1.0)
    assert imp["C"] > imp["A"]
    p = ft.plot(tmp_path / "ft.png", t_flight=1.0)
    assert (tmp_path / "ft.png").stat().st_size > 1000 and p


def test_targets():
    assert target("ac23_1309_class_I", "catastrophic") == 1e-6
    assert target("ac23_1309_class_II", "hazardous") == 1e-6
    assert target("amc25_1309", "catastrophic") == 1e-9
    assert target("stanag4671", "major") == 1e-4
    assert stanag4703_cumulative_catastrophic(100) == pytest.approx(1.5e-5)
    assert stanag4703_cumulative_catastrophic(10) == 1e-4
    assert ac23_class(1157) == "I" and ac23_class(1157, n_engines=2) == "II" and ac23_class(3000) == "III"


def test_rates_have_sources():
    for k in ("altimeter", "uav_servo", "piston_engine_lycoming"):
        r = rate(k)
        assert r["lambda_per_h"] > 0 and r["source"]
    assert rate("altimeter")["lambda_per_h"] == pytest.approx(1 / 5500, rel=0.01)
    u = rate("uav_servo", {"uav_servo": 1e-5})
    assert u["kind"] == "user" and u["mtbf_h"] == pytest.approx(1e5)
    with pytest.raises(KeyError):
        rate("gnss")


def test_fmea_rows():
    c = Component("srv", "servo", "uav_servo", 5e-4, "x", "vendor_claim",
                  modes=[FailureMode("encravamento", 0.5, system_effect="FC1", severity="catastrophic")])
    rows = fmea_rows([c], {"srv"})
    assert rows[0]["λ_modo [1/h]"] == pytest.approx(2.5e-4) and rows[0]["ponto único de falha"] == "sim"
    assert "servo" in to_markdown(rows)
