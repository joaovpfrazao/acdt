# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Wing-plus-fuselage mesh guard. The nominal 12 million cell case stays refused."""
from pathlib import Path

import pytest

from acdt.domains.aircraft.hifi.c172_wf_rans import (
    CAUCHY_EPS,
    ITER_CAP,
    KB_PER_CELL,
    MEASURED_RATE_S,
    N_THREADS,
    WORKSET_FACTOR,
    cauchy_met,
    cell_caps,
    drop_tails,
    half_model_geo,
    mesh_guard,
    parse_history,
    rans_cfg,
)

# The stored wing-plus-fuselage count. It is not rerun.
_NOMINAL_CELLS = 12072848
_AVAILABLE_GB = 17.55


def test_time_binds_before_ram_on_this_machine_class():
    caps = cell_caps(_AVAILABLE_GB)
    assert caps["binding"] == "measured_rate_time"
    expected = 45.0 * 60.0 * N_THREADS / (ITER_CAP * MEASURED_RATE_S)
    assert caps["cell_cap"] == pytest.approx(expected)
    assert caps["by_workset_ram"] > caps["cell_cap"]
    assert caps["limit_GB"] == pytest.approx(0.7 * _AVAILABLE_GB)
    assert caps["workset_factor"] == WORKSET_FACTOR


def test_nominal_millions_of_cells_are_refused():
    guard = mesh_guard(_NOMINAL_CELLS, _AVAILABLE_GB)
    assert guard["run_here"] is False
    assert any("memória" in reason for reason in guard["reasons"])
    assert any("tempo" in reason for reason in guard["reasons"])
    ram = _NOMINAL_CELLS * KB_PER_CELL * 1e-6 * WORKSET_FACTOR
    assert guard["ram_workset_GB"] == pytest.approx(ram)


def test_a_mesh_inside_both_guards_may_run():
    guard = mesh_guard(100_000, _AVAILABLE_GB)
    assert guard["run_here"] is True
    assert guard["reasons"] == []
    assert guard["ram_workset_GB"] < 0.7 * _AVAILABLE_GB
    assert guard["time_min_measured_rate"] < 45.0


def test_a_bad_input_is_not_a_zero_cell_pass():
    caps = cell_caps(0.0)
    assert caps["run_here"] is False
    assert caps["cell_cap"] is None
    guard = mesh_guard(float("nan"), _AVAILABLE_GB)
    assert guard["run_here"] is False
    assert guard["ram_formula_GB"] is None


def test_tails_are_removed_and_the_geo_has_no_prism_stack():
    spec = drop_tails({"wing": {"semispan": 1.0}, "htail": {"semispan": 2.0}, "vtail": {"semispan": 0.4},
                       "fuselage": {"length": 7.0}})
    assert "htail" not in spec
    assert "vtail" not in spec
    assert spec["wing"]["semispan"] == 1.0
    geo = half_model_geo("wing.step", "fuselage.step", 1.38, 5.5, 0.17)
    assert "wing.step" in geo
    assert "fuselage.step" in geo
    assert 'Physical Surface("aircraft")' in geo
    assert "htail" not in geo
    assert "BoundaryLayer" not in geo
    assert "BooleanFragments" in geo


def test_the_deck_is_one_angle_with_restart_and_no_mpi():
    cfg = rans_cfg("c172_wf.su2", 0.0, 0.12, 3.0e6, 1.38, 8.0, 1.38, 0.4, iters=400, restart=False)
    assert "AOA= 0.000" in cfg
    assert "RESTART_SOL= NO" in cfg
    assert "SOLUTION_FILENAME= restart_flow.dat" in cfg
    assert "RESTART_FILENAME= restart_flow.dat" in cfg
    assert "MARKER_HEATFLUX= ( aircraft, 0.0 )" in cfg
    assert "CONV_CAUCHY_EPS=" in cfg
    assert "mpiexec" not in cfg
    assert "mpirun" not in cfg
    again = rans_cfg("c172_wf.su2", 0.0, 0.2, 3.0e6, 1.38, 8.0, 1.38, 0.4, iters=800, restart=True)
    assert "RESTART_SOL= YES" in again
    assert "ITER= 800" in again
    assert "MACH_NUMBER= 0.2000" in again
    low = rans_cfg("c172_wf.su2", 0.0, 0.05, 1.0, 1.0, 1.0, 1.0, 0.0, iters=1, restart=False)
    assert "MACH_NUMBER= 0.1500" in low


def test_a_missing_history_is_not_zero_and_cauchy_needs_the_three_forces():
    empty = parse_history(Path("does-not-exist-history.csv"))
    assert empty["rows"] == 0
    assert empty["last"] == {}
    assert cauchy_met({"series": []}) is False
    flat = [{"CL": 0.4, "CD": 0.04, "CMy": -0.02} for _ in range(400)]
    assert cauchy_met({"series": flat}) is True
    missing = [{"CL": 0.4, "CD": 0.04} for _ in range(400)]
    assert cauchy_met({"series": missing}) is False
    moving = [{"CL": 0.4 + 1e-3 * i, "CD": 0.04, "CMy": -0.02} for i in range(400)]
    assert cauchy_met({"series": moving}) is False
    assert CAUCHY_EPS == 2e-6


def test_the_module_does_not_call_mpi():
    text = Path(__file__).resolve().parents[1].joinpath(
        "src", "acdt", "domains", "aircraft", "hifi", "c172_wf_rans.py").read_text(encoding="utf-8")
    assert 'find_exe("mpiexec")' not in text
    assert 'find_exe("mpirun")' not in text
    assert "import openvsp" not in text
    assert "import gmsh" not in text
    assert "import su2" not in text
