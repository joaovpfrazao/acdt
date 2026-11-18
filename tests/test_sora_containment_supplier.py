"""SORA 2.5 Step #8 containment + supplier failure-rate path (opt-in, unassessed≠pass)."""
from __future__ import annotations

from pathlib import Path

import pytest

from acdt.core.certification import sora
from acdt.core.certification.containment import adjacent_radius_km, assess_containment, required_robustness
from acdt.core.safety.rates import merge_supplier_rates, supplier_rate
from acdt.domains.aircraft import safety_assessment as SA

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples/certification"


def test_adjacent_radius_clamped_to_5_and_35_km():
    # 48.5 m/s × 180 s = 8.73 km
    assert adjacent_radius_km(48.5) == pytest.approx(8.73)
    assert adjacent_radius_km(10.0) == 5.0          # 1.8 km → floor 5
    assert adjacent_radius_km(250.0) == 35.0        # 45 km → cap 35


def test_table11_sail_iv_density_and_assemblies():
    # 8 m column, SAIL IV (matches existing UAV iGRC 5 / ARC-b or -c examples)
    low = required_robustness("IV", 11, density_per_km2=20, assembly="<40k")
    assert low["required_robustness"] == "low"
    mid = required_robustness("IV", 11, density_per_km2=10_000, assembly="40k-400k")
    assert mid["required_robustness"] == "medium"
    oos = required_robustness("IV", 11, density_per_km2=80_000, assembly=">400k")
    assert oos["required_robustness"] == "out_of_scope"


def test_assess_without_containment_keeps_legacy_open_item():
    a = sora.assess(sora.SoraInput(5.37, 48.5, "<50", 10, {}))
    assert a["SAIL"] == "IV" and a["residual_ARC"] == "b"
    assert a["containment"]["status"] == "unassessed"
    assert a["containment"]["requirement_status"] == "unassessed"
    assert any("contenção" in x for x in a["open"])


def test_assess_containment_complete_example():
    raw = __import__("json").loads((EX / "sora_containment_assessed.json").read_text(encoding="utf-8"))
    a = sora.assess(sora.SoraInput(
        raw["span_m"], raw["v_max_m_s"], raw["population"], raw["aec"], raw.get("mitigations") or {},
        raw.get("mtow_kg"), raw.get("vlos", False), raw.get("containment"),
    ))
    c = a["containment"]
    assert a["SAIL"] == "IV"
    assert c["table_no"] == 11
    assert c["adjacent_radius_km"] == pytest.approx(8.73)
    assert c["required_robustness"] == "low"
    assert c["p_exit_target_per_fh"] == 1e-3          # Annex E low/medium
    assert c["requirement_status"] == "ok"
    assert c["compliance_status"] == "ok"
    assert c["status"] == "ok"
    assert not any("Passo #8" in x for x in a["open"])


def test_assess_containment_missing_adjacent_data_unassessed():
    raw = __import__("json").loads((EX / "sora_containment_unassessed.json").read_text(encoding="utf-8"))
    a = sora.assess(sora.SoraInput(
        raw["span_m"], raw["v_max_m_s"], raw["population"], raw["aec"], {},
        raw.get("mtow_kg"), False, raw.get("containment"),
    ))
    c = a["containment"]
    assert c["status"] == "unassessed"
    assert c["requirement_status"] == "unassessed"
    assert c["compliance_status"] == "unassessed"
    assert "adjacent_population_density_per_km2" in c["unassessed_terms"]
    assert "outdoor_assembly" in c["unassessed_terms"]
    assert any("contenção" in x for x in a["open"])


def test_mtom_below_250g_is_low_containment():
    c = assess_containment(span_m=0.4, v_max_m_s=20.0, sail="II", mtow_kg=0.2,
                           containment={"requested": True}, span_col=0)
    # empty dict would mean "not requested"; any key requests the step. Use a flag-like dict.
    c = assess_containment(span_m=0.4, v_max_m_s=20.0, sail="II", mtow_kg=0.2,
                           containment={"note": "step requested"}, span_col=0)
    assert c["required_robustness"] == "low"
    assert c["status"] == "ok"
    assert "250 g" in c["operational_limitations"] or "250 g" in " ".join(c["notes"])


def test_unsourced_p_exit_not_applied():
    c = assess_containment(
        span_m=5.37, v_max_m_s=48.5, sail="IV", mtow_kg=136.0, span_col=2,
        containment={
            "adjacent_population_density_per_km2": 20,
            "outdoor_assembly": "<40k",
            "p_exit_operational_volume_per_fh": 1e-9,  # would "pass" if silently applied
        },
    )
    assert c["requirement_status"] == "ok"
    assert c["required_robustness"] == "low"
    assert c["p_exit_operational_volume_per_fh"] is None
    assert c["compliance_status"] == "unassessed"
    assert c["status"] == "unassessed"


def test_supplier_rate_requires_source_and_date():
    bare = supplier_rate("uav_c2_link", 2e-4)
    assert bare["status"] == "unassessed" and bare["lambda_per_h"] is None
    ok = supplier_rate("uav_c2_link", {
        "lambda_per_h": 2e-4,
        "source": "EXAMPLE / PRESSUPOSTO ilustrativo",
        "retrieved": "2026-11-10",
    })
    assert ok["status"] == "ok" and ok["lambda_per_h"] == pytest.approx(2e-4)
    merged, report = merge_supplier_rates(None, {"uav_c2_link": 2e-4})
    assert "uav_c2_link" not in merged
    assert report[0]["status"] == "unassessed"


def test_c2_closes_only_with_sourced_supplier_rate():
    # default: FC-U4 stays open
    a = SA.assess("uas", {}, "stanag4671", 10.0, 150)
    fc = next(f for f in a["failure_conditions"] if f["id"] == "FC-U4")
    assert fc["status"] == "em aberto" and fc["P_per_fh"] is None

    # unsourced supplier attempt: still open
    b = SA.assess("uas", {}, "stanag4671", 10.0, 150, supplier_rates={"uav_c2_link": 2e-4})
    fc2 = next(f for f in b["failure_conditions"] if f["id"] == "FC-U4")
    assert fc2["status"] == "em aberto" and fc2["P_per_fh"] is None
    assert "incompleta" in fc2["note"] or "incompleta" in (fc2.get("note") or "") or "aberto" in fc2["note"]

    # sourced EXAMPLE rate: assessed, P = lambda (single event)
    src = __import__("json").loads((EX / "supplier_rates_illustrative.json").read_text(encoding="utf-8"))
    c = SA.assess("uas", {}, "stanag4671", 10.0, 150, supplier_rates=src["supplier_rates"])
    fc3 = next(f for f in c["failure_conditions"] if f["id"] == "FC-U4")
    assert fc3["P_per_fh"] is not None
    assert fc3["P_per_fh"] == pytest.approx(2.0e-4, rel=2e-3)  # 1-exp(-λT)/T for T=10 h
    assert c["components"]["c2"]["lambda_per_h"] == pytest.approx(2.0e-4)
    assert fc3["status"] != "em aberto"
    eng = c["components"]["engine"]
    assert eng["kind"] == "supplier"
    assert eng["lambda_per_h"] == pytest.approx(5.0e-4)
    fcc = next(v for k, v in c["components"].items() if v["rate_key"] == "uav_flight_computer")
    assert fcc["kind"] == "supplier"
    assert fcc["lambda_per_h"] == pytest.approx(1.0 / 20000)


def test_3m_column_needs_explicit_sheltering():
    # 3 m / 35 m/s → Tables 9 vs 10; missing sheltering makes table selection unassessed
    c = assess_containment(
        span_m=3.0, v_max_m_s=35.0, sail="IV", mtow_kg=25.0, span_col=1,
        containment={"adjacent_population_density_per_km2": 20, "outdoor_assembly": "<40k"},
    )
    assert c["requirement_status"] == "unassessed"
    assert any("sheltering" in t for t in c["unassessed_terms"])
    with_s = assess_containment(
        span_m=3.0, v_max_m_s=35.0, sail="IV", mtow_kg=25.0, span_col=1,
        containment={"adjacent_population_density_per_km2": 20, "outdoor_assembly": "<40k",
                     "sheltering": False},
    )
    assert with_s["table_no"] == 10
    assert with_s["requirement_status"] == "ok"
