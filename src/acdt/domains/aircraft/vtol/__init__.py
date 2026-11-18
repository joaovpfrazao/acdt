# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""VTOL / eVTOL L0: momentum-theory hover, transition energy and architecture comparison."""
from .momentum import (blade_loading, climb_power, hover_power, ideal_hover_power,  # noqa: F401
                       induced_velocity_forward, induced_velocity_hover)
from .size import ARCHITECTURES, CITATIONS, compare_architectures, hover_point, size_vtol  # noqa: F401
from .bemt import assess_rotor_bemt, attach_to_hover  # noqa: F401

__all__ = ["ARCHITECTURES", "CITATIONS", "blade_loading", "climb_power", "compare_architectures",
           "hover_point", "hover_power", "ideal_hover_power", "induced_velocity_forward",
           "induced_velocity_hover", "size_vtol", "assess_rotor_bemt", "attach_to_hover"]
