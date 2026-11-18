# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""OpenVSP spec of the flying wing. The interpreter is not required for this test."""
import os

import pytest

from acdt.domains.aircraft.aero.interfaces import ToolNotAvailable
from acdt.domains.aircraft.hifi.geometry import export_vsp, flying_wing_vsp_spec
from acdt.domains.aircraft.hifi.wing_bl import scaled_wing


def test_flying_wing_spec_uses_leading_edge_twist_and_declared_thickness():
    surf, _scale = scaled_wing()
    spec = flying_wing_vsp_spec(surf)
    assert "fuselage" not in spec and "htail" not in spec and "vtail" not in spec
    wing = spec["wing"]
    assert wing["twist_deg"] == pytest.approx([0.0, -10.0])
    assert wing["twist_location"] == 0.0
    assert wing["tc"] == pytest.approx([0.15, 0.12])
    assert wing["sweep_location"] == 0.0
    assert wing["sweep_deg"] == pytest.approx(28.0, abs=1e-6)
    assert wing["dihedral_deg"] == pytest.approx(2.0, abs=1e-6)
    # Symmetric code: camber stays zero. ThickChord carries 0.15 and 0.12.
    assert wing["airfoil"] == "0012"
    assert surf.naca4_mean_line is False


def test_export_needs_the_openvsp_interpreter(tmp_path, monkeypatch):
    monkeypatch.delenv("ACDT_VSP_PYTHON", raising=False)
    assert os.environ.get("ACDT_VSP_PYTHON") is None
    with pytest.raises(ToolNotAvailable):
        export_vsp({"wing": {}}, tmp_path, "wing")
