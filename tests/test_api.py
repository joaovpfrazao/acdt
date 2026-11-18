# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""API pública versionada (acdt.api; docs/API.md): estabilidade das assinaturas, descontinuação e contratos."""
from __future__ import annotations

import math
import re
import warnings
from pathlib import Path

import pytest

import acdt
from acdt import api
from acdt.api import stability as S

ROOT = Path(__file__).resolve().parents[1]
UAV = ROOT / "examples" / "uav_gasoline_150kg.yaml"


# ------------------------------------------------------------------------------------------- estabilidade
def test_public_surface_matches_snapshot_or_version_bumped():
    """Falha quando uma assinatura pública muda sem subir API_VERSION (regenerar: python -m acdt.api.stability
    --write depois de subir a versão segundo docs/API.md §2)."""
    probs = S.check(S.load_snapshot(), S.surface(), api.API_VERSION)
    assert not probs, "\n".join(probs)
    snap = S.load_snapshot()
    if snap["api_version"] == api.API_VERSION:
        assert snap["surface"] == S.surface(), "superfície mudou: subir API_VERSION e regenerar api_surface.json"


def test_check_rules():
    old = {"api_version": "1.2.0", "surface": {"f": "def(x)", "g": "def()"}}
    assert S.check(old, {"f": "def(x)", "g": "def()"}, "1.2.0") == []
    assert S.check(old, {"f": "def(x)", "g": "def()"}, "1.2.1") == []
    # acréscimo → MENOR
    assert S.check(old, {"f": "def(x)", "g": "def()", "h": "def()"}, "1.2.1")
    assert S.check(old, {"f": "def(x)", "g": "def()", "h": "def()"}, "1.3.0") == []
    # alteração ou remoção → MAIOR
    assert S.check(old, {"f": "def(x, y)", "g": "def()"}, "1.3.0")
    assert S.check(old, {"f": "def(x)"}, "1.9.0")
    assert S.check(old, {"f": "def(x, y)"}, "2.0.0") == []
    assert S.check(old, {"f": "def(x)", "g": "def()"}, "1.1.0")  # versão a descer


def test_all_is_complete_and_documented():
    for n in api.__all__:
        assert hasattr(api, n), n
        obj = getattr(api, n)
        if callable(obj) and not isinstance(obj, type):
            doc = obj.__doc__ or ""
            assert len(doc.strip()) > 20, f"{n} sem docstring"
    public = {n for n, o in vars(api).items() if not n.startswith("_") and callable(o)
              and getattr(o, "__module__", "").startswith("acdt.api") and not isinstance(o, type)}
    assert public - set(api.__all__) == set(), "funções públicas fora de __all__"


def test_versions_semver_and_consistent():
    assert re.fullmatch(r"\d+\.\d+\.\d+", api.API_VERSION)
    assert re.fullmatch(r"\d+\.\d+\.\d+", acdt.__version__)
    txt = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{acdt.__version__}"' in txt
    v = api.version_info()
    assert v["acdt"] == acdt.__version__ and v["api"] == api.API_VERSION


# ------------------------------------------------------------------------------------------- descontinuação
def test_deprecated_helper_warns_and_registers():
    @api.deprecated("1.0.0", removed_in="2.0.0", alternative="acdt.api.size", name="_velho")
    def velho(x: int) -> int:
        """Antigo."""
        return x + 1

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert velho(1) == 2
    assert any(issubclass(x.category, api.ACDTDeprecationWarning) and "acdt.api.size" in str(x.message) for x in w)
    assert api.DEPRECATED.pop("_velho")["removed_in"] == "2.0.0"
    assert velho.__doc__ == "Antigo."
    with pytest.raises(ValueError):
        api.deprecated("1.0.0", removed_in="1.5.0")  # só sai numa MAIOR
    with pytest.raises(ValueError):
        api.deprecated("1.0.0", removed_in="2.1.0")


def test_no_deprecated_name_past_its_removal():
    major = int(api.API_VERSION.split(".")[0])
    for n, info in api.DEPRECATED.items():
        assert int(str(info["removed_in"]).split(".")[0]) > major, f"{n} devia ter saído na {info['removed_in']}"


# ------------------------------------------------------------------------------------------- contratos
def test_load_mission_level_and_errors(tmp_path):
    spec = api.load_mission(UAV, level="L0")
    assert spec.assumptions["aero"]["fidelity"] == "handbook"
    assert api.load_mission(UAV).assumptions["aero"]["fidelity"] == "lowfi"
    with pytest.raises(ValueError):
        api.load_mission(UAV, level="L9")
    with pytest.raises(FileNotFoundError):
        api.load_mission(tmp_path / "nao_existe.yaml")


def test_size_L0_summary_and_files(tmp_path):
    r = api.size(UAV, tmp_path / "out", level="L0", no_systems=True)
    assert r["feasible"] in (True, False) and r["W0_kg"] and r["W0_kg"] > 0
    assert math.isfinite(r["S_m2"]) and r["converged"] is True
    assert r["verification"] is not None and r["verification"]["requisitos"] >= 1
    assert (tmp_path / "out" / "result.json").is_file()
    m = api.verify(UAV, tmp_path / "out")
    assert m["coverage"]["por_estado"] == r["verification"]["por_estado"]
    db = api.db_load(tmp_path / "out")
    assert api.db_validate(db) == []
    assert api.db_diff(db, db)["identical"] is True
    # dict em vez de ficheiro dá o mesmo W0
    import yaml
    d = yaml.safe_load(UAV.read_text(encoding="utf-8"))
    r2 = api.size(d, level="L0", no_systems=True)
    assert r2["W0_kg"] == pytest.approx(r["W0_kg"], rel=1e-12) and r2["output"] is None


def test_generic_uq_and_mdo_studies():
    m = api.function_model(lambda p: {"y": p["a"] + 0.1 * p["b"]}, {"a": 1.0, "b": 0.0},
                           [{"id": "R1", "metric": "y", "comparison": "max", "threshold": 1.5}])
    r = api.uq_study({"n": 200, "seed": 1, "inputs": [
        {"path": "a", "dist": "normal", "std": 0.5, "source": "teste"},
        {"path": "b", "dist": "uniform", "low": -1, "high": 1, "source": "teste"}]}, m)
    assert r["schema"] == "acdt.uq/1"
    assert 0.6 < r["propagation"]["requirements"]["R1"]["p_passa"] < 1.0
    fm = api.function_model(lambda p: {"f1": p["x"] ** 2, "f2": (p["x"] - 2) ** 2})
    mo = api.mdo_study({"design_variables": [{"path": "x", "lower": 0, "upper": 2, "x0": 1, "source": "t"}],
                        "objectives": ["f1", "f2"], "strategy": "doe", "options": {"n": 9, "seed": 0}}, fm)
    assert len(mo["pareto"]) >= 2


def test_vv_cases_listing():
    cs = api.vv_cases()
    assert cs and {"id", "discipline", "kind", "cost", "title"} <= set(cs[0])
    with pytest.raises(KeyError):
        api.vv(cases=["caso_que_nao_existe"])
