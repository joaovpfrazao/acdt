import pytest

import acdt.domains.aircraft  # noqa: F401  (registers the aircraft requirement types)

from acdt.core.requirements import (REGISTRY, RequirementError, RequirementSet, RequirementType, handlers,
                               parse_requirement, register_handler, register_requirement)


def test_parse_forms():
    r = parse_requirement("endurance", {"min": 2, "unit": "h"})
    assert r.sense == "min" and r.value == 7200
    r = parse_requirement("cruise_speed", {"target": 100, "unit": "kt", "altitude": {"value": 5000, "unit": "ft"}})
    assert r.params["altitude"] == pytest.approx(1524.0)
    assert parse_requirement("payload_mass", 3).value == 3
    assert parse_requirement("unit_cost", {"objective": "minimize"}).sense == "objective"
    assert parse_requirement("propulsion_type", "electric").value == "electric"


def test_unknown_key_suggests():
    with pytest.raises(RequirementError, match="endurance"):
        parse_requirement("endurence", 2)


def test_bad_sense_and_choice():
    with pytest.raises(RequirementError):
        parse_requirement("stall_speed", {"min": 20})  # stall accepts max/target only
    with pytest.raises(RequirementError):
        parse_requirement("propulsion_type", "warp_drive")


def test_any_subset_and_free_keys():
    rs = RequirementSet.from_dict({"payload_mass": 2, "range": {"min": 100, "unit": "km"}})
    assert rs.get("endurance") is None
    assert [r.key for r in rs.by_stage("sizing")] == ["payload_mass", "range"]
    assert not [i for i in rs.validate() if i.severity == "error"]


def test_validation_detects_conflicts():
    rs = RequirementSet.from_dict({"payload_mass": 5, "mtow": {"max": 4}, "stall_speed": {"max": 30},
                                   "cruise_speed": {"target": 31}, "max_speed": {"min": 25}})
    msgs = " ".join(i.message for i in rs.validate() if i.severity == "error")
    assert "payload" in msgs and "max_speed" in msgs
    rs2 = RequirementSet.from_dict({"payload_mass": 1, "mtow": [{"target": 30}, {"max": 25}]})
    assert any(i.severity == "error" for i in rs2.validate())
    rs3 = RequirementSet.from_dict({"range": {"min": 10, "unit": "km"}})
    assert any("payload" in i.message for i in rs3.validate() if i.severity == "error")


def test_plugin_requirement_without_core_change():
    key = "test_pluggable_max_roll"
    register_requirement(RequirementType(key, "dimensionless", "test plugin", ("check",), ("max",)))

    @register_handler("check", key)
    def _chk(r, res):  # pragma: no cover - only registration tested here
        return None

    assert key in REGISTRY and key in handlers("check")
    rs = RequirementSet.from_dict({"payload_mass": 1, key: {"max": 3}})
    assert rs.get(key).value == 3
    del REGISTRY[key]


def test_types_are_domain_scoped():
    from acdt.core.requirements import types_for
    assert "endurance" in types_for("aircraft")
    assert "endurance" not in types_for("marine")


def test_toy_domain_plugs_into_pipeline(tmp_path):
    """A new domain registers types, validators and stages without touching the core."""
    from acdt.core.pipeline import Domain, Stage, register_domain, run_pipeline
    from acdt.core.requirements import Issue, register_validator

    register_requirement(RequirementType("test_toy_displacement", "mass", "toy", ("sizing",), ("target",),
                                         domains=("toy",)))

    @register_validator("toy")
    def _v(rs):
        return [Issue("warning", "toy validator ran")]

    def size(st):
        rs = RequirementSet.from_dict({"test_toy_displacement": 1000}, domain="toy")
        st["issues"] = rs.validate()
        st["result"] = rs.value("test_toy_displacement") * 2

    register_domain(Domain("toy", "toy", lambda p: {"path": p}, [Stage("size", size)]))
    st = run_pipeline("toy", "x.yaml")
    assert st["result"] == 2000 and st.log == ["size"]
    assert any("toy validator" in i.message for i in st["issues"])
    del REGISTRY["test_toy_displacement"]
