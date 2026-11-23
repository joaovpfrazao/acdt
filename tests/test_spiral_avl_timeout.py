# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Teste instável `test_spiral_unassessed_without_explicit_dihedral` (23 nov 2026): causa reproduzida por injeção de
falha. Um tempo-limite transitório do AVL no estágio de estabilidade deixava ``avl = None``, os modos laterais por
avaliar e a linha ``hq:spiral`` desaparecia. Agora a corrida repete com tempo-limite maior e, sem modos laterais, a
linha fica presente como desconhecida (desconhecido ≠ passa, nunca omitida)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from acdt.domains.aircraft.mission import MissionSpec
from acdt.domains.aircraft.phase2 import _avl_stability_case

UAV = Path(__file__).resolve().parents[1] / "examples" / "uav_gasoline_150kg.yaml"


def test_stability_avl_retries_once_with_longer_timeout():
    calls: list[float] = []

    def fake(config, *, trim_elevator, timeout, **kw):  # noqa: ANN001, ANN202
        calls.append(timeout)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired("avl", timeout)
        return "ok"

    assert _avl_stability_case(fake, object(), CL=0.5) == "ok"
    assert calls == [60.0, 180.0]

    def always(config, *, trim_elevator, timeout, **kw):  # noqa: ANN001, ANN202
        raise subprocess.TimeoutExpired("avl", timeout)

    with pytest.raises(subprocess.TimeoutExpired):
        _avl_stability_case(always, object(), CL=0.5)


@pytest.mark.requires_avl
def test_spiral_row_survives_stability_avl_timeout(tmp_path, monkeypatch):
    import acdt.domains.aircraft.aero.avl as A
    from acdt.core.pipeline import run_pipeline

    orig = A.run_avl_case

    def timeout_on_stability(*a, **k):  # noqa: ANN002, ANN003, ANN202
        if k.get("trim_elevator"):
            raise subprocess.TimeoutExpired("avl", k.get("timeout", 60))
        return orig(*a, **k)

    monkeypatch.setattr(A, "run_avl_case", timeout_on_stability)
    spec = MissionSpec.from_yaml(UAV)
    spec.assumptions["geometry"]["dihedral_deg"] = None
    res = run_pipeline("aircraft", spec, output=tmp_path / "s")["result"]
    spiral = [c for c in res.checks if c.key == "hq:spiral"]
    assert len(spiral) == 1 and spiral[0].ok is None
    assert "unassessed" in spiral[0].message.lower() and "dihedral" in spiral[0].message.lower()
    assert res.avl is None
