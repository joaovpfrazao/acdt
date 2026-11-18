"""AI-native layer: external data provenance, compute guard, run registry, toolkit, MCP server (in-process)."""
from __future__ import annotations

import json

import pytest

from acdt.ai import external, guard, registry
from acdt.ai import toolkit as T

PROV = {"source_url": "https://example.org/datasheet.pdf", "retrieved": "2026-10-01", "source_type": "handbook",
        "basis": "S"}


@pytest.fixture(autouse=True)
def runs_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ACDT_RUNS_DIR", str(tmp_path / "runs"))
    return tmp_path / "runs"


def test_external_material_units_ranges_provenance():
    m = {"key": "al6061_t6", "name": "Al 6061-T6", "kind": "metal", "E": "10.0 Msi", "nu": 0.33,
         "rho": {"value": 0.098, "unit": "lb/in3"}, "Ftu": "42 ksi", "Fty": "35 ksi", "Fsu": "27 ksi",
         "provenance": PROV}
    v = external.validate_material(m)
    assert v["ok"], v["issues"]
    assert v["material"]["E"] == pytest.approx(68.95e9, rel=1e-3)
    assert v["material"]["rho"] == pytest.approx(2712.6, rel=1e-3)
    assert v["structures"]["sigma_cap"] == pytest.approx(35 * 6.894757e6, rel=1e-6)   # Fcy = Fty (flagged)
    assert any(i["field"] == "Fcy" for i in v["issues"])
    assert "EXTERNAL: https://example.org" in v["structures"]["note"]
    bad = external.validate_material({**m, "E": "68.9 MPa"})             # unit slip → outside range
    assert not bad["ok"] and any(i["field"] == "E" and i["severity"] == "error" for i in bad["issues"])
    nosrc = external.validate_material({k: v for k, v in m.items() if k != "provenance"})
    assert not nosrc["ok"] and {"source_url", "retrieved"} <= {i["field"] for i in nosrc["issues"]}
    fut = external.validate_material({**m, "provenance": {**PROV, "retrieved": "2999-01-01"}})
    assert not fut["ok"]


def test_external_component_checks():
    cell = {"id": "test_21700", "chemistry": "li_ion", "v_nom": 3.6, "v_max": 4.2, "capacity_ah": "5000 mAh",
            "i_cont": "10 A", "mass": "70 g", "provenance": {**PROV, "source_type": "manufacturer_datasheet"}}
    v = external.validate_component("cells", cell)
    assert v["ok"], v["issues"]
    assert v["component"]["capacity_ah"] == pytest.approx(5.0)
    assert v["component"]["specific_energy_Wh_kg"] == pytest.approx(3.6 * 5 / 0.07)
    heavy = external.validate_component("cells", {**cell, "mass": "7 g"})     # 2571 Wh/kg → implausible
    assert not heavy["ok"]
    with pytest.raises(external.ExternalDataError):
        external.validate_component("wings", cell)


def test_compute_guard(monkeypatch, tmp_path):
    e = guard.estimate(["fem", "cfd2d", "gci"])
    assert e["verdict"] == "needs_user_approval" and e["needs_approval"] == ["cfd2d", "gci"]
    assert guard.estimate(["fem", "cfd2d"], user_approved=True)["verdict"] == "ok"
    (tmp_path / "cfd2d").mkdir()
    (tmp_path / "cfd2d" / "section_verification.json").write_text("{}")
    assert guard.estimate(["cfd2d"], tmp_path)["steps"][0]["decision"] == "cached"
    monkeypatch.setenv("ACDT_MCP_HEAVY", "never")
    assert guard.estimate(["cfd2d"], user_approved=True)["verdict"] == "refused"
    r = T.start("hifi", 0, example="uav_endurance_payload", steps=["cfd2d"], user_approved=False)
    assert r["status"] == "refused" and r["run_id"] is None


def test_validate_requirements_lenient_and_recorded():
    v = T.validate_requirements({"name": "t", "aircraft_class": "uav_small",
                                 "requirements": {"propulsion_type": "electric", "payload_mass": "4 kg",
                                                  "endurance": {"min": "150 min"}, "stall_speed": {"max": "25 kt"}}})
    assert v["ok"] and v["run_id"]
    vals = {r["key"]: r["value_si"] for r in v["requirements"]}
    assert vals["endurance"] == pytest.approx(9000.0) and vals["stall_speed"] == pytest.approx(25 * 1852 / 3600)
    assert v["assumptions"]["n_defaults"] > 50
    bad = T.validate_requirements({"requirements": {"endurence": {"min": 2, "unit": "h"}}})
    assert not bad["ok"] and "endurance" in bad["errors"][0]
    inc = T.validate_requirements({"requirements": {"mtow": [{"min": 30, "unit": "kg"}, {"max": 20, "unit": "kg"}]}},
                                  record=False)
    assert not inc["ok"] and any(i["severity"] == "error" for i in inc["issues"])


@pytest.mark.slow
def test_size_registry_provenance_compare_report():
    r = T.size(example="uav_endurance_payload", level="L0", no_systems=True)
    assert r["status"] == "done", r
    rec = registry.load(r["run_id"]).record
    assert rec["git"].get("commit") and rec["versions"]["acdt"]
    assert rec["files"]["spec"].endswith(".yaml") and rec["files"]["report.md"]
    srcs = {a["path"]: a["source"] for a in rec["assumptions"]}
    assert srcs["aero.AR"].startswith("user") and srcs["mda.tol"].startswith("assumed")
    assert srcs["aero.fidelity"].startswith("user")              # level L0 → handbook, recorded as an override
    w0 = r["summary"]["weights"]["W0_kg"]
    assert 5 < w0 < 50
    mat = {"key": "al6061_t6", "name": "Al 6061-T6", "kind": "metal", "E": "68.9 GPa", "nu": 0.33, "rho": "2700 kg/m3",
           "Ftu": "290 MPa", "Fty": "240 MPa", "Fcy": "240 MPa", "Fsu": "186 MPa", "t_min": "0.5 mm", "provenance": PROV}
    r2 = T.size(run_id=r["run_id"], level="L0", no_systems=True, materials={"structure": mat})
    assert r2["status"] == "done", r2
    rec2 = registry.load(r2["run_id"]).record
    assert rec2["parent_run"] == r["run_id"]
    assert rec2["external_data"][0]["provenance"]["source_url"] == PROV["source_url"]
    assert {a["path"]: a["source"] for a in rec2["assumptions"]}["structures.material"].startswith("external")
    c = T.compare_runs([r["run_id"], r2["run_id"]])
    assert any(d["path"] == "structures.material" for d in c["assumption_differences"])
    rep = T.report([r["run_id"], r2["run_id"]], "dossier teste")
    md = open(rep["files"]["dossier_md"], encoding="utf-8").read()
    assert "Dado externo material" in md and r2["run_id"] in md
    assert len(T.list_runs()["runs"]) == 3


def test_calibration_apply_records(tmp_path):
    cal = {"design": "x", "factors": {"k_cd_profile": {"group": "aero", "value": 1.07, "hifi": 1, "lowfi": 1,
                                                       "what": "test"}}}
    f = tmp_path / "calibration.json"
    f.write_text(json.dumps(cal))
    r = T.apply_calibration(example="uav_endurance_payload", calibration_file=str(f), apply=["aero"])
    assert r["calibration"]["applied_factors"] == {"k_cd_profile": 1.07}
    with pytest.raises(T.ToolError):
        T.apply_calibration(example="uav_endurance_payload", calibration_file=str(f), apply=["wings"])


def test_methods_catalogue_and_examples():
    from acdt.ai import catalogue
    m = catalogue.methods()
    mods = {x["module"]: x for x in m["modules"]}
    assert "acdt.domains.aircraft.cost" in mods and any("Gudmundsson" in r for r in mods["acdt.domains.aircraft.cost"]["references"])
    assert {w["stage"].split()[0] for w in m["workflow"]} >= {"requirements", "preliminary", "wing", "RCS"}
    assert any(e["example"] == "uav_endurance_payload" for e in catalogue.examples())


mcp = pytest.importorskip("mcp")


def _client(srv):
    from mcp import Client
    return Client(srv)


def _sc(r):
    return getattr(r, "structured_content", None) or getattr(r, "structuredContent", None)


def test_mcp_server_inprocess():
    import anyio
    from acdt.ai.mcp_server import build_server
    srv = build_server()

    async def go():
        async with _client(srv) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert {"size", "optimize", "wingbox", "rcs", "hifi", "hifi_estimate", "validate_requirements",
                    "job_status", "compare_runs", "generate_report", "apply_calibration", "validate_material"} <= names
            res = {str(r.uri) for r in (await c.list_resources()).resources}
            assert {"acdt://methods", "acdt://materials", "acdt://components", "acdt://agents-guide",
                    "acdt://capabilities"} <= res
            assert {p.name for p in (await c.list_prompts()).prompts} >= {"design_from_requirements"}
            p = await c.get_prompt("design_from_requirements", {"description": "UAV 25 kg, 3 h"})
            assert "validate_requirements" in p.messages[0].content.text
            m = await c.read_resource("acdt://methods")
            assert "workflow" in json.loads(m.contents[0].text)
            r = await c.call_tool("hifi", {"example": "uav_endurance_payload", "steps": ["cfd2d"]})
            assert _sc(r)["status"] == "needs_user_approval"
            r = await c.call_tool("size", {"example": "does_not_exist"})
            assert r.is_error if hasattr(r, "is_error") else r.isError
            r = await c.call_tool("rcs", {"mode": "validate", "freq_ghz": 10.0, "wait_s": 120})
            assert _sc(r)["ok"] is True
            r = await c.call_tool("size", {"example": "uav_endurance_payload", "level": "L0", "no_systems": True,
                                           "wait_s": 0})
            sc = _sc(r)
            if sc.get("status") != "done":
                assert sc["job_id"]
                r = await c.call_tool("job_status", {"job_id": sc["job_id"], "wait_s": 300})
                sc = _sc(r)
                assert sc["status"] == "done", sc
                sc = sc["result"]
            assert sc["summary"]["weights"]["W0_kg"] > 0
            g = await c.call_tool("get_run", {"run_id": sc["run_id"], "include": ["git", "versions"]})
            assert _sc(g)["git"]["commit"]
    anyio.run(go)


def test_mcp_stdio_subprocess(tmp_path):
    """`acdt mcp` over stdio, as Cursor / Claude / Grok Build launch it."""
    import os
    import sys
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def go():
        env = {**os.environ, "ACDT_RUNS_DIR": str(tmp_path / "runs")}
        p = StdioServerParameters(command=sys.executable, args=["-m", "acdt.cli", "mcp"], env=env)
        async with stdio_client(p) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                assert len((await s.list_tools()).tools) >= 20
                x = await s.call_tool("list_examples", {})
                assert "uav_endurance_payload" in x.content[0].text
    anyio.run(go)


def test_mcp_phase7_tools():
    import anyio
    from acdt.ai.mcp_server import build_server
    srv = build_server()
    prov = {"source_url": "https://www.aircraftspruce.com/catalog/mepages/alumsheet_2024t3.php",
            "retrieved": "2026-10-28", "source_type": "distributor"}
    mats = {"al": {"base": "al2024_t3", "price": {"usd_per_kg": 28.8, "year": 2026, "provenance": prov}},
            "cf": {"base": "cfrp_qi", "price": {"usd_per_kg": 93.3, "year": 2026, "provenance": prov}}}

    async def go():
        async with _client(srv) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert {"manufacturing_plan", "cost_estimate", "process_options", "compare_materials"} <= names
            r = _sc(await c.call_tool("cost_estimate", {"We_kg": 754, "V_H_kt": 124, "N": 820, "power_bhp": 180}))
            assert 2e5 < r["eastlake"]["unit_cost"] < 4e5 and r["dapca4"]["unit_cost"] > r["eastlake"]["unit_cost"]
            assert r["confidence"]["confidence"] == "medium" and r["confidence"]["band"]["aace_class"] == 5
            r = _sc(await c.call_tool("cost_estimate", {"We_kg": 90, "V_H_kt": 100, "N": 50, "unmanned": True,
                                                        "configuration": ["tailless flying wing"]}))
            assert r["confidence"]["outside_database"] and r["confidence"]["band"]["high_pct"] == 100
            part = {"name": "skin", "kind": "skin", "mass_kg": 3, "area_m2": 1.5, "perimeter_m": 5,
                    "max_dim_m": 2.5, "thickness_m": 0.8e-3, "material": "al"}
            r = _sc(await c.call_tool("process_options", {"part": part, "materials": mats, "N": 100,
                                                          "process_inputs": {"*": {"tooling_cost": 5000}}}))
            assert r["selected"]["process"] == "sheet_metal_riveted"
            fw = [o for o in r["options"] if o["process"] == "filament_winding"][0]
            assert fw["feasible"] is False
            r = _sc(await c.call_tool("compare_materials", {"materials": mats, "reference": "al"}))
            assert r["ranking"][0]["material"] == "cf"
    anyio.run(go)


@pytest.mark.slow
def test_toolkit_manufacturing_plan():
    import yaml
    from acdt.ai import toolkit as T
    from acdt.ai.catalogue import REPO
    cfg = yaml.safe_load((REPO / "examples/manufacturing/cessna172_manufacturing.yaml").read_text())
    r = T.manufacturing_plan(example="cessna172_check", manufacturing=cfg["manufacturing"], level="L0")
    assert r["status"] == "done", r
    s = r["summary"]
    assert s["selection"]["wing skin"][0] == "sheet_metal_riveted" and not s["unresolved_parts"]
    assert 0.3 < s["validation"]["ratio_eastlake"] < 1.0
    assert r["files"]["cost_breakdown"].endswith(".png")
    assert s["fidelity"]["recommended"] == "L0" and set(s["fidelity"]["levels"]) == {"L0", "L1"}
    assert r["files"]["cost_calibration"].endswith("cost_calibration.json")


@pytest.mark.slow
@pytest.mark.requires_avl
def test_toolkit_simulation_tools():
    """Phase 8 tools: control-surface sizing and a short airborne 6-DOF mission (sized layout)."""
    import anyio
    from acdt.ai import toolkit as T
    from acdt.ai.mcp_server import build_server

    async def names():
        async with _client(build_server()) as c:
            return {t.name for t in (await c.list_tools()).tools}
    assert {"size_control_surfaces", "simulate_mission"} <= anyio.run(names)
    ms = {"mission": {"name": "curta", "dt": 0.02, "initial": {"altitude_m": 600, "speed_m_s": 50},
                      "segments": [{"type": "cruise", "time_min": 0.5}, {"type": "turn", "heading_change_deg": 90,
                                                                         "load_factor": 1.3}]}}
    r = T.simulate_mission(example="cessna172_check", mission=ms)
    assert r["status"] == "done", r
    s = r["summary"]
    assert not s["aborted"] and [g["type"] for g in s["segments"]] == ["cruise", "turn"]
    assert 0.85 < s["segments"][0]["k_energy"] < 1.15
    assert 1.1 < s["segments"][1]["nz_max"] < 1.8
    assert 0.1 <= s["controls_layout"]["layout_sized"]["aileron_span_fraction"] <= 0.6
    assert r["files"]["time_history"].endswith(".png")
    with pytest.raises(T.ToolError):
        T.simulate_mission(example="cessna172_check", mission=ms, mission_example="c172_check")


def test_capabilities_doc_matches_code():
    """CAPABILITIES.md exists, is served as a doc, and every CLI command / MCP tool it names exists."""
    import re
    from acdt.ai import catalogue
    txt = catalogue.doc("CAPABILITIES")
    assert "Roadmap" in txt and "Sugestões de capacidades" in txt
    cli = (catalogue.REPO / "src/acdt/cli.py").read_text(encoding="utf-8")
    for cmd in set(re.findall(r"`acdt ([a-z0-9-]+)", txt)):
        assert f'add_parser("{cmd}"' in cli, cmd
    ai_dir = catalogue.REPO / "src/acdt/ai"
    srv = "".join(p.read_text(encoding="utf-8") for p in [ai_dir / "mcp_server.py", *sorted(ai_dir.glob("*_mcp.py"))])
    for uri in set(re.findall(r"`(acdt://[a-z-]+)", txt)):
        assert f'"{uri}' in srv, uri
    for line in txt.splitlines():
        if line.startswith("* **CLI / MCP**") and "/" in line:
            mcp = line.split(" / ", 1)[1]
            for name in re.findall(r"`([a-z_]+)(?:[(`])", mcp):
                assert f'@tool(name="{name}"' in srv, name
