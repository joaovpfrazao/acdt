# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Second-bounce PO on the twist-corrected flying-wing loft. Not a full-wave run."""
import pytest

from acdt.core.em import po
from acdt.domains.aircraft.assembly.assembly import Assembly
from acdt.domains.aircraft.hifi.wing_bl import scaled_wing


def _mesh():
    surf, _scale = scaled_wing()
    return surf, Assembly([surf]).to_rcs_mesh(fine=1, exclude_roles=("propeller",))


def test_tip_trailing_edge_is_above_the_leading_edge():
    surf, _mesh_ = _mesh()
    le, chord, _t, length, _tc = surf._frames()[-1]
    te = le + length * chord
    assert surf.sections[-1]["twist_deg"] == -10.0
    assert te[2] > le[2]


def test_second_bounce_raises_the_nose_return_and_is_not_full_wave():
    _surf, mesh = _mesh()
    kw = dict(nose=(-1, 0, 0), occlusion=True, n_sub_max=12)
    one = po.monostatic(mesh, 10e9, 0.0, 0.0, "VV", bounces=1, **kw)
    two = po.monostatic(mesh, 10e9, 0.0, 0.0, "VV", bounces=2, **kw)
    hh = po.monostatic(mesh, 10e9, 0.0, 0.0, "HH", bounces=1, **kw)
    assert float(two) > float(one)
    assert float(hh) == pytest.approx(float(one), rel=1e-9, abs=1e-12)
