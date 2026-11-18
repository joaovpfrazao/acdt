"""P4: electrical architecture / power budget and payload catalog trade."""
from __future__ import annotations

from pathlib import Path

from acdt.ai import systems_p4 as S
from acdt.core.systems.electrical import ElectricalArchitecture, Load, analyse, flight_hour_cost
from acdt.core.systems.payload_trade import load_payload_catalog, trade

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "systems" / "electrical_uav_isr.json"


def test_payload_catalog_marks_example():
    rows = load_payload_catalog()
    assert len(rows) >= 4
    assert all(r.get("source") for r in rows)
    assert any("EXAMPLE" in str(r.get("notes", "")) or r.get("source") == "EXAMPLE" for r in rows)


def test_payload_trade_pareto_radar():
    out = trade(load_payload_catalog(), kinds=["radar"])
    assert out["pareto"]
    assert all(r["payload"]["kind"] == "radar" for r in out["rows"] if r["comparable"])


def test_electrical_analyse_example_arch():
    import json
    arch = json.loads(EX.read_text(encoding="utf-8"))
    out = S.electrical_analyse(arch)
    assert out["P_avg_W"] > 0
    assert out["P_peak_W"] >= out["P_avg_W"]
    assert "MIL-E-7016F" in out["reference"]
    assert "mass_kg" in out
    # PMA 400 W continuous with mid EO+AIS+avionics should be tight or fail margin — still returns ok flag
    assert isinstance(out["ok"], bool)


def test_electrical_fails_without_sources():
    arch = ElectricalArchitecture(id="bare", loads=[Load("x", 50.0)])
    out = analyse(arch)
    assert out["ok"] is False
    assert any("fontes" in r for r in out["reasons"])


def test_electrical_generation_covers_load():
    arch = ElectricalArchitecture(
        id="ok",
        generation=[{"id": "g", "power_w_cont": 200, "power_w_peak": 250, "mass_kg": 1.0}],
        batteries=[{"id": "b", "energy_wh": 100, "continuous_w": 100, "mass_kg": 0.5}],
        loads=[Load("avionics", 40.0, duty=1.0, peak_w=60.0, bus="avionics")],
        endurance_h=1.0,
    )
    out = analyse(arch)
    assert out["ok"] is True


def test_flight_hour_cost():
    c = flight_hour_cost(2.0, 1.5, maintenance_per_h=10.0)
    assert c["total_per_h"] == 2.0 * 1.5 + 10.0


def test_cli_electrical(tmp_path):
    import subprocess, sys
    out = tmp_path / "e.json"
    r = subprocess.run(
        [sys.executable, "-m", "acdt.cli", "systems-p4", "electrical",
         "--architecture", str(EX), "-o", str(out)],
        cwd=ROOT, capture_output=True, text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert out.exists()
