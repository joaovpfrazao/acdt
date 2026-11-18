"""Component weight build-up (Raymer 6th ed. Ch. 15), statistical registry and the sizing weight loop."""
import math
from pathlib import Path

import pytest

from acdt.core.systems.harness import DENSITY_CU, Connector, Harness, Wire, awg_area_m2
from acdt.domains.aircraft.mission import MissionSpec
from acdt.domains.aircraft.sizing import run
from acdt.domains.aircraft.weights import (EMPTY_FRACTION_ALIASES, FIXED_EMPTY_FRACTION, NICOLAI_EMPTY_WEIGHT,
                                           RAYMER_EMPTY_WEIGHT, EmptyWeightModel,
                                           statistical_bracket, statistical_fraction, statistical_source)
from acdt.domains.aircraft.weights_detailed import (limit_load_factor, raymer_ga_installed_engine,
                                                    raymer_ga_wing)

EX = Path(__file__).parents[1] / "examples"
LB = 0.45359237


def test_raymer_wing_eq_15_46_hand_check():
    # Raymer Eq. 15.46 evaluated by hand (Sw 134 ft², Wfw 1060 lb, A 8, Λ 0, λ 0.4, t/c 0.16,
    # q from ρ = 0.0018685 slug/ft³ and V = 337.562 ft/s, Nz 5.25, Wdg 5354 lb) -> ≈ 344 lb
    q = 0.5 * 0.0018685 * 337.562 ** 2
    ref = (0.036 * 134 ** 0.758 * 1060 ** 0.0035 * 8 ** 0.6 * q ** 0.006 * 0.4 ** 0.04 * 16 ** -0.3
           * (5.25 * 5354) ** 0.49)
    assert raymer_ga_wing(134, 1060, 8, 0.0, q, 0.4, 0.16, 5.25, 5354) == pytest.approx(ref, rel=1e-9)
    assert ref == pytest.approx(344, abs=1.0)


def test_raymer_installed_engine():
    assert raymer_ga_installed_engine(268.0) == pytest.approx(2.575 * 268.0 ** 0.922, rel=1e-9)


def test_limit_load_factor_cs23():
    assert limit_load_factor(1157) == pytest.approx(3.8)         # 2.1 + 24000/(W+10000) capped at 3.8
    assert limit_load_factor(12000 * LB) == pytest.approx(2.1 + 24000 / 22000)
    assert limit_load_factor(1000, "utility") == 4.4 and limit_load_factor(1000, "aerobatic") == 6.0


def test_statistical_registry():
    W0 = 150.0
    # Former fixed-fraction class names are aliases of published Raymer Table 3.1 regressions (no unpublished value).
    A, C = RAYMER_EMPTY_WEIGHT["uav_tactical_recce_ucav"]
    assert statistical_fraction("uav_gasoline", W0) == pytest.approx(A * (W0 / LB) ** C)
    assert "Raymer" in statistical_source("uav_gasoline") and "alias" in statistical_source("uav_gasoline")
    assert statistical_fraction("uav_small_electric", 25.0) == pytest.approx(statistical_fraction("uav_small", 25.0))
    assert set(EMPTY_FRACTION_ALIASES.values()) <= set(RAYMER_EMPTY_WEIGHT)
    assert FIXED_EMPTY_FRACTION == {}                                       # acdt ships no unpublished fraction
    a, b = NICOLAI_EMPTY_WEIGHT["nicolai_uav_prop_endurance_lt12h"][:2]
    W_lb = W0 / LB
    assert statistical_fraction("nicolai_uav_prop_endurance_lt12h", W0) == pytest.approx(a * W_lb ** b / W_lb)
    rows = statistical_bracket(W0, ["uav_gasoline", "uav_small", "nicolai_light_ga"])
    assert {r["class"] for r in rows} == {"uav_gasoline", "uav_small", "nicolai_light_ga"}
    assert all(0 < r["We/W0"] < 1.2 for r in rows)
    assert EmptyWeightModel(empty_mass_kg=60.0).fraction(150.0) == pytest.approx(0.4)


def test_harness_mass():
    h = Harness("t")
    h.add_connector(Connector("A", ["1"]))
    h.add_connector(Connector("B", ["1"]))
    h.connect(Wire("w", ("A", "1"), ("B", "1"), "PWR", current_A=20, length_m=1.0, v_supply=12.0))
    h.size_wires()
    cu = awg_area_m2(h.wires[0].awg) * 1.0 * DENSITY_CU
    assert h.conductor_mass() == pytest.approx(cu)
    assert h.mass(1.3, 0.01) == pytest.approx(1.3 * cu + 0.02)


@pytest.fixture(scope="module")
def uav():
    from acdt.domains.aircraft.systems_integration import run_with_systems
    return run_with_systems(MissionSpec.from_yaml(EX / "uav_endurance_payload.yaml"))[0]


@pytest.mark.slow
def test_uav_weight_loop(uav):
    # Phase 3: takeoff+climb energy now from the segment model -> baseline (AR 14 by hand) breaks the 4.2 m span
    # limit only; reported honestly, `acdt optimize` resolves it (test_phase3)
    assert uav.converged and uav.weights is not None
    failed = {c.key for c in uav.checks if c.ok is False and not c.key.startswith(("perf:", "hq:", "aeroel:", "wb:", "gear:"))}
    # NeuralFoil (extra wingbox) can lift W0 over the 25 kg limit. Both outcomes are accepted,
    # as in tests/test_examples_cli.py::test_cli_uav.
    assert "wing_span" in failed and failed <= {"wing_span", "mtow"}
    bd = uav.weights
    keys = {i.key for i in bd.items}
    assert {"wing", "fuselage", "htail", "vtail", "harness", "growth"} <= keys
    assert not any(i.key.endswith("gear") for i in bd.items)               # landing_gear: none
    assert uav.sizing.We == pytest.approx(bd.empty, rel=0.02)
    assert 0.3 < uav.sizing.empty_fraction < 0.8
    # Initial value: Raymer Table 3.1 'uav_small' (≈0.8 here). With the battery in Wf it does not close
    # (We/W0 + Wf/W0 > 0.98), so the component loop restarts from 0.30 and says so (info issue).
    restarted = any("reiniciada com We/W0 = 0.30" in i.message for i in uav.issues)
    first = uav.history[0]["We/W0 usado"]
    assert (restarted and first == pytest.approx(0.30)) or \
        first == pytest.approx(statistical_fraction("uav_small", uav.history[0]["W0"]), rel=1e-6)
    assert any(i.method.startswith("minimum gauge") for i in bd.items)


def test_gasoline_uav_initial_class():
    r = run(MissionSpec.from_yaml(EX / "uav_gasoline_150kg.yaml"))
    assert r.converged and r.feasible
    assert 100 <= r.sizing.W0 <= 1000
    assert 0.4 < r.sizing.empty_fraction < 0.8                              # component build-up, not the class
    assert any(row["class"] == "uav_tactical_recce_ucav" for row in r.weight_cross_check)


def test_gasoline_uav_150kg_stays_feasible():
    """Regression: payload at 50 % L put the forward CG at −26 % MAC (δe −52° at CLmax,
    scissor control NaN) and the full pipeline reported the 150 kg UAV infeasible.
    Payload now sits on the fixed-mass CG, and trim and the scissor read that same range.

    Tail volume is the scissor result for this MDA (Torenbeek 1982 Ch. 9; Raymer Ch. 16),
    c_ht = 0.55, above the Raymer Table 6.4 homebuilt start of 0.50. The measured
    intersection is 0.543; 0.55 is that value rounded up to the hundredth. The 0.5 %
    S_h/S tolerance in ``tail_sizing_scissor`` is unchanged.

    ``gear:position`` and ``gear:tipback`` stay false. The installed engine remains at
    8 % L (Roskam Part V Table 8.1, tractor) while the example text describes a pusher.
    On the 15° tip-back ray the 8–15 % nose-load band (Raymer Ch. 11) asks for a nose
    ahead of the datum. Shortening the 0.35 m leg or widening 8–15 % is not a fix.
    """
    from acdt.core.pipeline import run_pipeline

    res = run_pipeline("aircraft", EX / "uav_gasoline_150kg.yaml", output=None)["result"]
    assert res.converged and res.feasible
    assert res.sizing.crew == 0.0
    assert res.spec.assumptions["geometry"]["c_ht"] == pytest.approx(0.55)
    st = res.stability
    assert all(t["ok"] for t in st.trim.values())
    lo, hi = st.cg_range_mac
    assert hi - lo < 0.25
    assert lo > -0.05
    sc = res.dynamics["scissor"]
    assert sc["cg_range"] == (lo, hi)
    assert st.trim["CLmax limpo (CG dianteiro)"]["xbar_cg"] == pytest.approx(lo)
    assert math.isfinite(sc["Sh_S_control"]) and math.isfinite(sc["Sh_S_required"])
    assert sc["ok"] is True
    assert sc["binding"] == "estabilidade"
    assert sc["Sh_S_control"] < sc["Sh_S_current"]
    assert sc["Sh_S_current"] + 1e-9 >= sc["Sh_S_required"] * (1 - 5e-3)
    checks = {c.key: c for c in res.checks}
    assert checks["hq:scissor"].ok is True, checks["hq:scissor"].message
    assert checks["wb:envelope"].ok is True, checks["wb:envelope"].message
    wb = res.weight_balance
    assert wb.x_min_m >= wb.x_forward_m - 1e-6
    assert wb.x_max_m <= wb.x_aft_m + 1e-6
    assert checks["gear:position"].ok is False
    assert checks["gear:tipback"].ok is False
    assert res.landing_gear.x_nose_m is None
    empty = next(c for c in st.cases if c.name == "vazio")
    payload = next(s for s in st.stations if s["item"] == "payload")
    assert payload["x_m"] == pytest.approx(empty.x_cg, abs=1e-6)
    assert not any(s["item"] == "crew" for s in st.stations)


def test_statistical_method_still_available():
    import yaml
    d = yaml.safe_load((EX / "uav_endurance_payload.yaml").read_text())
    d["assumptions"]["weights"] = {"method": "statistical", "fixed_fraction": 0.55}
    r = run(MissionSpec.from_dict(d))
    assert r.weights is None and r.sizing.empty_fraction == pytest.approx(0.55)
    assert math.isfinite(r.sizing.W0)


def test_aeroelasticity_stubs_name_methods():
    from acdt.domains.aircraft import aeroelasticity as ae
    # Phase 4 implemented FEM+DLM flutter and the margin check; the AeroSandbox backend remains a stub
    m = ae.flutter_margin_check(130.0, 125.0, 100.0)
    assert m["ok"] and abs(m["margin_g003"] - (130 / 120 - 1)) < 1e-12
    assert not ae.flutter_margin_check(110.0, 105.0, 100.0)["ok"]
    with pytest.raises(NotImplementedError, match="AeroSandbox"):
        ae.static_aerostructural(None, backend="aerosandbox")
