# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Falha transitória do AVL no modelo de faixas low-fi: repetida antes de cair para Schrenk, e uma mudança de fonte
entre iterações do ciclo W0 nunca fica silenciosa (causa do teste instável de reutilização de run_id, 18 nov 2026)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from acdt.domains.aircraft.aero import lowfi as lf


def test_avl_pair_retries_with_longer_timeout(monkeypatch):
    calls = []

    def fake(config, alpha_deg=None, mach=0.0, timeout=60):
        calls.append((alpha_deg, timeout))
        if len(calls) == 1:
            raise subprocess.TimeoutExpired("avl", timeout)
        return ("r", alpha_deg)

    monkeypatch.setattr(lf, "run_avl_case", fake)
    r1, r2 = lf._avl_pair(object(), 0.1)
    assert (r1, r2) == (("r", 2.0), ("r", 6.0))
    assert calls == [(2.0, lf.AVL_TIMEOUTS_S[0]), (2.0, lf.AVL_TIMEOUTS_S[1]), (6.0, lf.AVL_TIMEOUTS_S[1])]


def test_avl_pair_raises_after_all_attempts(monkeypatch):
    def boom(config, alpha_deg=None, mach=0.0, timeout=60):
        raise RuntimeError("AVL failed (no ST output)")

    monkeypatch.setattr(lf, "run_avl_case", boom)
    with pytest.raises(RuntimeError):
        lf._avl_pair(object(), 0.1)


@pytest.mark.slow
@pytest.mark.requires_avl
@pytest.mark.requires_xfoil
def test_intermediate_avl_failure_is_reported(monkeypatch, tmp_path):
    """Reproduz a falha observada: a 3.ª avaliação do modelo de faixas (5.ª corrida AVL) cai para Schrenk.
    O W0 convergido muda (~1e-5 relativo) e o resultado tem de o dizer."""
    from acdt.core.pipeline import run_pipeline

    real = lf._avl_pair
    n = {"k": 0}

    def flaky(config, mach):
        n["k"] += 1
        if n["k"] == 3:
            raise subprocess.TimeoutExpired("avl", lf.AVL_TIMEOUTS_S[-1])
        return real(config, mach)

    monkeypatch.setattr(lf, "_avl_pair", flaky)
    ex = Path(__file__).resolve().parents[1] / "examples" / "uav_gasoline_150kg.yaml"
    res = run_pipeline("aircraft", ex, output=tmp_path, no_systems=True)["result"]
    msgs = [i.message for i in res.issues if i.severity == "warning"]
    assert any("mudou de fonte entre iterações" in m and "Schrenk" in m for m in msgs)
