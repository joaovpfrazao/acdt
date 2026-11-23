# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Regressão: `thinwalled.solve` vectorizado (PR thinwalled-vectorizado) contra a implementação anterior congelada
em `tests/thinwalled_reference.py` — mesmas saídas (x_sc, z_sc, GJ, EI, fluxos unitários) até 1e-9 relativo."""
from __future__ import annotations

import copy

import numpy as np
import pytest

from acdt.core.thinwalled import ThinWalledSection
from acdt.domains.aircraft.wingbox.section import Contour, wing_section

from thinwalled_reference import ThinWalledSection as RefSection

KEYS = ("x_sc", "z_sc", "GJ", "EIxx", "EIzz", "EIxz", "xc", "zc")


def _ref_of(sec, cells):
    return RefSection(sec.pts.copy(), np.asarray(sec.boom_area, float).copy(), list(sec.walls),
                      copy.deepcopy(cells), sec.E_ref, sec.G_ref).solve()


def _new_of(sec, cells):
    return ThinWalledSection(sec.pts.copy(), np.asarray(sec.boom_area, float).copy(), list(sec.walls),
                             copy.deepcopy(cells), sec.E_ref, sec.G_ref).solve()


def _assert_same(a, b):
    for k in KEYS:
        va, vb = getattr(a, k), getattr(b, k)
        assert va == pytest.approx(vb, rel=1e-9, abs=1e-12 * (abs(vb) + 1.0)), k
    np.testing.assert_allclose(a.B, b.B, rtol=1e-12, atol=1e-18)
    for k in ("q_Sz", "q_Sx", "q_T"):
        qa, qb = getattr(a, k), getattr(b, k)
        np.testing.assert_allclose(qa, qb, rtol=1e-8, atol=1e-9 * np.abs(qb).max())
    assert [list(c) for c in a.cells] == [list(c) for c in b.cells]


def _cases():
    rng = np.random.default_rng(20261123)
    out = []
    for airfoil in ("NACA 0012", "NACA 2412", "NACA 23015", "NACA 4415"):
        for le in (False, True):
            for _ in range(4):
                tc = rng.uniform(0.09, 0.18)
                xf, xr = rng.uniform(0.1, 0.25), rng.uniform(0.55, 0.75)
                tu, tl = rng.uniform(0.6e-3, 3e-3, 2)
                sec = wing_section(rng.uniform(0.3, 3.0), Contour.from_airfoil(airfoil, tc), xf, xr,
                                   t_up=tu, t_lo=tl, t_wf=rng.uniform(0.8e-3, 4e-3), t_wr=rng.uniform(0.5e-3, 3e-3),
                                   tbar_up=tu * rng.uniform(1, 2), tbar_lo=tl * rng.uniform(1, 2),
                                   cap_area=rng.uniform(0, 4e-5, 4), cap_E_ratio=rng.uniform(1, 2.5),
                                   stringers_up=(0.3, 0.45), stringers_lo=(0.35,), A_str=rng.uniform(0, 3e-5),
                                   t_le=rng.uniform(0.5e-3, 1.5e-3) if le else None,
                                   n_cover=int(rng.integers(6, 16)), n_web=int(rng.integers(3, 8)))
                out.append(sec)
    return out


@pytest.mark.parametrize("k", range(32))
def test_wing_sections_match_reference(k):
    sec = _cases()[k]
    cells0 = copy.deepcopy(sec.cells)
    _assert_same(_new_of(sec, cells0), _ref_of(sec, cells0))
    flipped = [[-s for s in c[::-1]] for c in cells0]          # opposite loop orientation → flip path
    _assert_same(_new_of(sec, flipped), _ref_of(sec, flipped))


def test_open_section_and_missing_cell_fallback():
    sec = _cases()[5]                                          # D-nose: two cells
    _assert_same(_new_of(sec, []), _ref_of(sec, []))            # no cells: lstsq fallback (underdetermined)
    _assert_same(_new_of(sec, sec.cells[:1]), _ref_of(sec, sec.cells[:1]))

