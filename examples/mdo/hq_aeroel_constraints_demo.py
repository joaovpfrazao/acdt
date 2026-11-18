# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Runnable numbers: hq/aeroel constraint-active vs filter-only vs unassessed.

Does not invent aircraft data — synthetic CheckResult / margin payloads only.
Run: PYTHONPATH=src python examples/mdo/hq_aeroel_constraints_demo.py
"""
from types import SimpleNamespace

from acdt.domains.aircraft.mdo import _hifi


def res(checks, margins=None):
    ae = SimpleNamespace(margins=margins) if margins else None
    return SimpleNamespace(
        sizing=SimpleNamespace(W0=120.0, energy_J=None, Wf=15.0, converged=True),
        spec=SimpleNamespace(requirements={}, assumptions={"mdo": {}}),
        config=None, checks=checks, systems=SimpleNamespace(pinned_ok=True),
        aeroelastic=ae, cost=None,
    )


def chk(key, ok):
    return SimpleNamespace(key=key, ok=ok, message="")


def main():
    margins = {"flutter": {"V_eas": 90.0, "V_required": 120.0, "margin": 90 / 120 - 1, "ok": False}}
    checks = [chk("hq:dutch_roll", False), chk("aeroel:flutter", False), chk("perf:climb", True)]
    r = res(checks, margins)
    rows = []
    for flag in (False, True):
        f, v, failed, st = _hifi(r, "W0", None, flag)
        phi = f / abs(f) + 10 * v
        rows.append((flag, f, v, phi, sorted(failed), st.get("unassessed"), st.get("violated")))
    print("filter_only (hq_aeroel_constraints=false):")
    print(f"  f={rows[0][1]}  violation={rows[0][2]}  phi={rows[0][3]:.4f}  failed={rows[0][4]}")
    print("constraint_active (hq_aeroel_constraints=true):")
    print(f"  f={rows[1][1]}  violation={rows[1][2]:.4f}  phi={rows[1][3]:.4f}  failed={rows[1][4]}")
    print(f"  violated={rows[1][6]}  (Δphi = {rows[1][3] - rows[0][3]:.4f})")
    # unassessed case
    ru = res([chk("hq:spiral", None)])
    _, v_u, _, st_u = _hifi(ru, "W0", None, True)
    print("unassessed (hq:spiral ok=None, constraints on):")
    print(f"  violation={v_u}  unassessed={st_u['unassessed']}  (never treated as pass)")


if __name__ == "__main__":
    main()
