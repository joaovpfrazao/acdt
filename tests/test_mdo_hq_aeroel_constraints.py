# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""hq:*/aeroel:* as real MDO constraints (opt-in), not only post-optimization filters."""
from types import SimpleNamespace

import pytest

from acdt.domains.aircraft.mdo import _hifi, hq_aeroel_constraint_status


def _res(checks, *, margins=None, W0=100.0, converged=True, pinned_ok=True):
    ae = None
    if margins is not None:
        ae = SimpleNamespace(margins=margins)
    return SimpleNamespace(
        sizing=SimpleNamespace(W0=W0, energy_J=None, Wf=10.0, converged=converged),
        spec=SimpleNamespace(requirements={}, assumptions={"mdo": {}}),
        config=None,
        checks=checks,
        systems=SimpleNamespace(pinned_ok=pinned_ok),
        aeroelastic=ae,
        cost=None,
    )


def _chk(key, ok, msg=""):
    return SimpleNamespace(key=key, ok=ok, message=msg)


def test_default_filter_after_ignores_hq_aeroel_in_violation_and_failed():
    r = _res([_chk("hq:dutch_roll", False), _chk("aeroel:flutter", False), _chk("perf:climb", False)],
             margins={"flutter": {"V_eas": 50.0, "V_required": 100.0, "margin": -0.5, "ok": False}})
    f, v, failed, st = _hifi(r, "W0", None, False)
    assert f == 100.0
    assert v == 0.0  # hq/aeroel ignored when flag off
    assert failed == {"perf:climb"}  # hq/aeroel skipped from failed set
    assert st["enabled"] is False and st["violation"] == 0.0


def test_opt_in_hq_fail_raises_violation_vs_filter_only():
    checks = [_chk("hq:dutch_roll", False), _chk("hq:CAP", True)]
    r = _res(checks)
    _, v_off, failed_off, st_off = _hifi(r, "W0", None, False)
    _, v_on, failed_on, st_on = _hifi(r, "W0", None, True)
    assert v_off == 0.0 and "hq:dutch_roll" not in failed_off
    assert v_on == pytest.approx(1.0)  # discrete fail → unit violation
    assert "hq:dutch_roll" in failed_on
    assert "hq:dutch_roll" in st_on["violated"]
    assert "hq:CAP" in st_on["active"] and "hq:CAP" not in st_on["violated"]
    assert st_on["unassessed"] == []


def test_opt_in_aeroel_smooth_margin_in_violation():
    margins = {
        "flutter": {"V_eas": 80.0, "V_required": 100.0, "margin": -0.2, "ok": False},
        "divergence": {"V_eas": 200.0, "V_required": 100.0, "margin": 1.0, "ok": True},
    }
    r = _res([_chk("aeroel:flutter", False), _chk("aeroel:divergence", True)], margins=margins)
    _, v_off, _, _ = _hifi(r, "W0", None, False)
    _, v_on, failed, st = _hifi(r, "W0", None, True)
    assert v_off == 0.0
    # g_flutter = 1 - 80/100 = 0.2; divergence satisfied (g < 0) → 0
    assert v_on == pytest.approx(0.2)
    assert "aeroel:flutter" in failed and "aeroel:flutter" in st["violated"]
    assert st["values"]["aeroel:flutter"] == pytest.approx(0.2)


def test_unassessed_is_not_a_satisfied_constraint():
    r = _res([_chk("hq:spiral", None, "espiral unassessed: declare dihedral")])
    _, v_off, failed_off, _ = _hifi(r, "W0", None, False)
    _, v_on, failed_on, st = _hifi(r, "W0", None, True)
    assert v_off == 0.0 and failed_off == set()
    assert v_on == pytest.approx(1.0)  # unit violation
    assert failed_on == set()  # ok is None → not in failed
    assert "hq:spiral" in st["unassessed"]
    assert st["values"]["hq:spiral"] is None


def test_key_allowlist_limits_active_set():
    r = _res([_chk("hq:dutch_roll", False), _chk("hq:CAP", False), _chk("aeroel:flutter", False)],
             margins={"flutter": {"V_eas": 50.0, "V_required": 100.0, "margin": -0.5, "ok": False}})
    st = hq_aeroel_constraint_status(r, enabled=True, keys={"hq:dutch_roll", "aeroel:flutter"})
    assert set(st["active"]) == {"hq:dutch_roll", "aeroel:flutter"}
    assert "hq:CAP" not in st["active"]
    _, v, failed, st2 = _hifi(r, "W0", None, True, {"hq:dutch_roll"})
    assert "hq:dutch_roll" in st2["violated"] and "hq:dutch_roll" in failed
    assert v == pytest.approx(1.0)  # only dutch_roll in allowlist for violation path
    assert "aeroel:flutter" not in st2["active"] and "aeroel:flutter" not in failed
    assert "hq:CAP" not in failed


def test_status_helper_disabled_is_noop():
    r = _res([_chk("hq:dutch_roll", False)])
    st = hq_aeroel_constraint_status(r, enabled=False)
    assert st == {"enabled": False, "active": [], "violated": [], "unassessed": [],
                  "values": {}, "violation": 0.0}
