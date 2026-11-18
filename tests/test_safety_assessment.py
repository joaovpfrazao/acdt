import pytest

from acdt.domains.aircraft import safety_assessment as SA


def _fc(a, i):
    return next(r for r in a["failure_conditions"] if r["id"] == i)


def test_ga_baseline_ac23_class_I():
    a = SA.assess("ga_piston", {}, "ac23_1309_class_I", 1.0)
    att = _fc(a, "FC-A1")
    # (λ_AI + λ_vac) · λ_TC  (NASA GARS rates, T = 1 h)
    assert att["P_per_fh"] == pytest.approx((4.0e-4 + 2.5e-4) * 4.76e-4, rel=2e-3)
    assert att["status"] == "cumpre" and not att["single_point_catastrophic"]
    assert _fc(a, "FC-A3")["status"] == "não cumpre"                     # single altimeter vs 1e-5
    assert _fc(a, "FC-A3")["required"]["mtbf_required_h"] == pytest.approx(1e5, rel=1e-3)
    assert _fc(a, "FC-A5")["status"] == "em aberto"                      # compass: no published rate
    b = SA.assess("ga_piston", {"standby_altimeter": True}, "ac23_1309_class_I", 1.0)
    assert _fc(b, "FC-A3")["status"] == "cumpre"


def test_uas_single_point_and_redundancy():
    a = SA.assess("uas", {}, "stanag4671", 10.0, 150)
    u1 = _fc(a, "FC-U1")
    assert u1["single_point_catastrophic"] and "srv_elev1" in u1["single_point_failures"]
    b = SA.assess("uas", {"servo": "dual", "fcc": "dual", "backup_battery": True}, "stanag4671", 10.0, 150)
    assert not _fc(b, "FC-U1")["single_point_catastrophic"]
    assert _fc(b, "FC-U1")["P_per_fh"] < u1["P_per_fh"] / 100


def test_trade_selects_lightest_feasible_4703():
    unit = {"servo_kg": 0.1, "fcc_kg": 0.1, "battery_kg": 1.0, "n_servo_channels": 4}
    t = SA.redundancy_trade("uas", "stanag4703", 10.0, 136.4, unit, growth=2.0)
    s = t["selected"]
    assert s["meets"] and s["options"]["servo"] == "dual" and s["options"]["backup_battery"]
    assert all(r["dm_kg"] >= s["dm_kg"] for r in t["rows"] if r["meets"])
    assert s["dW0_kg"] == pytest.approx(2.0 * s["dm_kg"])
    assert not t["baseline"]["meets"]


def test_fmea_rows_flag_single_points():
    a = SA.assess("uas", {}, "stanag4671", 10.0, 150)
    rows = SA.fmea_from(a)
    r = next(x for x in rows if x["id"] == "srv_elev1")
    assert r["ponto único de falha"] == "sim" and "FC-U1" in r["efeito no sistema (condição de falha)"]


def test_severity_override_and_missing_rate():
    a = SA.assess("uas", {}, "stanag4671", 10.0, 150, severity_overrides={"FC-U2": "major"})
    assert _fc(a, "FC-U2")["target_per_fh"] == 1e-4 and "PRESSUPOSTO" in _fc(a, "FC-U2")["note"]
    with pytest.raises(KeyError):
        SA.assess("uas", {}, "stanag4671", 10.0, 150, overrides=None) and SA.rate("no_such")


def test_toolkit_safety_assessment_and_cli():
    import subprocess
    import sys

    from acdt.ai import toolkit as T
    r = T.safety_assessment("uas", "stanag4703", 10.0, 136.4, trade=True,
                            unit={"servo_kg": 0.18, "battery_kg": 1.5}, baseline={"backup_battery": True},
                            sora={"span_m": 5.4, "v_max_m_s": 48.5, "aec": 5})
    assert r["selected"] == {"servo": "dual", "fcc": "dual", "backup_battery": True}
    assert r["sora"]["SAIL"] == "IV" and r["sora"]["iGRC"] == 5
    assert "certify" in T.TOOLS
    out = subprocess.run([sys.executable, "-m", "acdt.cli", "safety", "ga_piston", "--scheme", "ac23_1309_class_I",
                          "--options", "standby_altimeter=true"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and "FC-A3" in out.stdout
