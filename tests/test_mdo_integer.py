"""Integer catalog assignment stays outside SLSQP (Geoffrion, J. Optim. Theory Appl. 10, 1972)."""
from types import SimpleNamespace

from acdt.domains.aircraft.mdo import _hifi, discrete_improves
from acdt.domains.aircraft.systems_integration import apply_catalog_pin, clear_catalog_pin


def test_discrete_step_needs_a_real_merit_drop_and_no_new_failure():
    assert discrete_improves(1.0, 0.9, {"perf:a"}, {"perf:a"})
    assert not discrete_improves(1.0, 0.9, {"perf:a"}, {"perf:a", "perf:b"})
    assert not discrete_improves(1.0, 1.1, set(), set())
    assert not discrete_improves(1.0, 1.0 - 1e-6, set(), set())  # same cutoff as a zero predicted reduction


def test_overloaded_pin_is_a_violation_and_a_feasible_pin_is_not():
    def res(ok):
        return SimpleNamespace(
            sizing=SimpleNamespace(W0=10.0, energy_J=None, Wf=1.0, converged=True),
            spec=SimpleNamespace(requirements={}), checks=[], systems=SimpleNamespace(pinned_ok=ok))
    f, v, failed, st = _hifi(res(False), "W0", None, False)
    assert f == 10.0 and v == 1.0 and failed == set() and st["enabled"] is False
    _, v_ok, _, st_ok = _hifi(res(True), "W0", None, False)
    assert v_ok == 0.0


def test_catalog_master_reruns_the_pipeline_only_when_the_choice_changes(monkeypatch):
    from acdt.domains.aircraft import mdo
    from acdt.domains.aircraft import systems_integration as si

    def choice(mid):
        return SimpleNamespace(
            motor=SimpleNamespace(motor={"id": mid, "mass": 0.5 if mid == "heavy" else 0.2},
                                  esc={"id": "esc"}, feasible=True, esc_feasible=True),
            battery=SimpleNamespace(cell={"id": "cell"}, current_ok=True), pinned_ok=True)

    def fake_select(res, sysspec=None, db=None):
        mid = (res.spec.systems.get("motor") or {}).get("id") or "light"
        return choice(mid)

    seen = []

    def fake_run(domain, spec, **kw):
        seen.append((spec.systems.get("motor") or {}).get("id"))
        sy = fake_select(SimpleNamespace(spec=spec))
        res = SimpleNamespace(
            sizing=SimpleNamespace(W0=9.0, energy_J=None, Wf=1.0, converged=True),
            spec=SimpleNamespace(requirements={}), checks=[], systems=sy, config=SimpleNamespace())
        return {"result": res, "systems": sy}

    monkeypatch.setattr(si, "select_systems", fake_select)
    monkeypatch.setattr("acdt.core.pipeline.run_pipeline", fake_run)
    spec = SimpleNamespace(propulsion_kind="electric",
                           systems={"motor": {"id": "heavy", "power_margin": 1.2}, "esc_id": "esc", "cell_id": "cell"})
    res = SimpleNamespace(spec=spec, systems=choice("heavy"))
    changed = mdo._catalog_master(res, spec, objective="W0", W0_cap=None, hqa=False, phi_k=1.0, failed_k=set(),
                                  ids_now=si.catalog_ids(choice("heavy")), cell_fixed=False, ref=10.0, mu=10.0)
    # The pipeline must see the pin removed; the accepted spec is pinned to the new motor.
    assert seen == [None]
    assert changed["accepted"] is True and changed["to"]["motor_id"] == "light"
    assert changed["spec"].systems["motor"]["id"] == "light"

    seen.clear()
    spec_light = SimpleNamespace(propulsion_kind="electric",
                                 systems={"motor": {"id": "light"}, "esc_id": "esc", "cell_id": "cell"})
    res_light = SimpleNamespace(spec=spec_light, systems=choice("light"))
    held = mdo._catalog_master(res_light, spec_light, objective="W0", W0_cap=None, hqa=False, phi_k=1.0,
                               failed_k=set(), ids_now=si.catalog_ids(choice("light")), cell_fixed=False,
                               ref=10.0, mu=10.0)
    assert held["same"] is True and seen == []


def test_catalog_pin_roundtrip_keeps_a_user_cell():
    spec = SimpleNamespace(systems={"motor": {"power_margin": 1.2}, "close_loop": True, "cell_id": "user"})
    apply_catalog_pin(spec, {"motor_id": "heavy", "esc_id": "esc_b", "cell_id": "user"})
    assert spec.systems["motor"] == {"power_margin": 1.2, "id": "heavy"}
    assert spec.systems["esc_id"] == "esc_b" and spec.systems["cell_id"] == "user"
    clear_catalog_pin(spec, keep_cell=True)
    assert "id" not in spec.systems["motor"] and "esc_id" not in spec.systems
    assert spec.systems["cell_id"] == "user" and spec.systems["close_loop"] is True
