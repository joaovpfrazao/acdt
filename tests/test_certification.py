import json
from pathlib import Path

import pytest

from acdt.core.certification import build_matrix, catalogue, select_basis, to_markdown, write_csv, write_xlsx
from acdt.core.certification.evidence import _n_required
from acdt.core.certification.matrix import status_of


def _result(W0=1137.8, crew=77.0, payload=185.0, cat="cs_23", gamma=5.45, n=3.8, vc=69.9):
    return {
        "weights": {"W0_kg": W0, "We_kg": 0.6 * W0, "crew_kg": crew, "payload_kg": payload},
        "requirements": [{"key": "regulatory_category", "value_si": cat},
                         {"key": "propulsion_type", "value_si": "piston_prop"}],
        "checks": [{"key": "static_margin", "ok": True, "message": "SM 10 %"},
                   {"key": "trim", "ok": True, "message": "trim ok"},
                   {"key": "aeroel:flutter", "ok": False, "message": "flutter < 1.2 VD"}],
        "structures": {"vn": {"VS1_EAS_m_s": 29.4, "VA_EAS_m_s": 57, "VC_EAS_m_s": vc, "VD_EAS_m_s": 97.8,
                              "n_manoeuvre_pos": n, "n_manoeuvre_neg": -0.4 * n, "n_limit_pos": n,
                              "n_limit_neg": -1.5, "n_ultimate": 1.5 * n, "n_gust_VC": [3.9, -1.9]}},
        "performance": {"takeoff": {"gamma_climb_deg": gamma, "ground_roll": 270, "total_50ft": 450}},
        "aero": {"CLmax_clean": 1.5, "LD_max": 11.8},
    }


def test_catalogue_has_sources_and_paraphrases():
    cat = catalogue()
    assert {"cs23", "cs25", "stanag4671", "stanag4703"} <= set(cat)
    for b in cat.values():
        assert b["url"].startswith("https://")
        for it in b["items"]:
            assert it["id"] and it["t"] and it["p"] and it["moc"]


def test_basis_c172_level2_low_speed():
    s = select_basis(_result(), {"max_passenger_seats": 3})
    assert s["bases"] == ["cs23"] and s["context"].level == 2 and s["context"].perf_level == "low"
    assert s["context"].ac23_class == "I" and not s["sora"]


def test_basis_uav_by_mass_and_override():
    assert select_basis(_result(W0=136, crew=0, payload=30, cat="easa_specific"))["bases"] == ["stanag4703"]
    s = select_basis(_result(W0=160, crew=0, payload=30, cat="easa_specific"))
    assert s["bases"] == ["stanag4671"] and s["sora"]
    assert select_basis(_result(W0=136, crew=0, cat="easa_specific"), {"basis": "stanag4671"})["bases"] == ["stanag4671"]


def test_load_factor_formulas():
    assert _n_required("usar337", 150) == pytest.approx(3.8)
    assert _n_required("usar337", 3000) == pytest.approx(2.1 + 10900 / 7536)
    assert _n_required("astm_f3116", 1157) == pytest.approx(3.8)  # 2.1+24000/12551 = 4.01 → 3.8


def test_status_rule():
    assert status_of(["analysis"], []) == "open"
    assert status_of(["analysis", "test"], [{"ok": True}]) == "needs-test"
    assert status_of(["analysis"], [{"ok": True}, {"ok": None}]) == "compliant"
    assert status_of(["analysis", "test"], [{"ok": False}]) == "non-compliant"


def test_matrix_statuses_and_exports(tmp_path):
    m = build_matrix(_result(gamma=3.0), {"max_passenger_seats": 3})
    st = {r["parágrafo"]: r["estado"] for r in m["rows"]}
    assert st["23.2120"] == "non-compliant"          # 5.2 % < 8.3 %
    assert st["23.2245"] == "non-compliant"          # flutter check failed
    assert st["23.2230"] == "compliant"
    assert st["23.2150"] == "open"
    assert "23.2310" not in st                        # seaplane only
    assert sum(m["counts"].values()) == len(m["rows"])
    write_csv(m, tmp_path / "m.csv")
    assert "23.2120" in (tmp_path / "m.csv").read_text(encoding="utf-8")
    assert "Matriz de conformidade" in to_markdown(m)
    x = write_xlsx(m, tmp_path / "m.xlsx")
    if x:
        assert Path(x).stat().st_size > 3000


def test_safety_evidence_feeds_1309():
    sa = {"scheme": "ac23_1309_class_I", "failure_conditions": [
        {"id": "FC1", "ok": True}, {"id": "FC2", "ok": False}, {"id": "FC3", "ok": None}]}
    m = build_matrix(_result(), {"max_passenger_seats": 3}, extra={"safety": sa})
    r = next(r for r in m["rows"] if r["parágrafo"] == "23.2510")
    assert r["estado"] == "non-compliant" and "FC2" in r["evidência acdt"]


def test_sora_tables():
    from acdt.core.certification import sora
    assert sora.column(5.37, 48.5) == 2 and sora.igrc(5.37, 48.5, "<50") == 5
    assert sora.column(2.0, 40.0) == 2                       # speed drives the column
    assert sora.final_grc(5, 2, {"M2": "medium"})[0] == 4
    assert sora.final_grc(4, 2, {"M1A": "medium", "M2": "high"})[0] == 2   # floor = controlled value of column
    with pytest.raises(ValueError):
        sora.final_grc(5, 2, {"M1A": "medium", "M1B": "medium"})
    assert sora.sail(5, "b") == "IV" and sora.sail(2, "a") == "I" and sora.sail(8, "a") is None
    a = sora.assess(sora.SoraInput(5.37, 48.5, "<50", 10, {}))
    assert a["SAIL"] == "IV" and a["residual_ARC"] == "b"
    o4 = next(o for o in a["OSOs"] if o["oso"] == "OSO#04")
    assert o4["nível"] == "M" and o4["projetista"]
    assert sora.assess(sora.SoraInput(10, 80, ">50000"))["category"].startswith("fora")
