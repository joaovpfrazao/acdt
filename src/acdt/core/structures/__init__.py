"""L1 structures namespace: **BoxFEM** and **BeamAero**.

* **BoxFEM** is the in-house shell model already in :mod:`acdt.core.fem` (QM6 membrane + MITC4 plate).
  It stays there so existing imports keep working; :mod:`acdt.core.structures.boxfem` re-exports it.
* **BeamAero** is the calibrated beam plus the aeroelastic coupling. The beam integration, the
  thin-tube section and the load formulas live here. The aircraft assembly (wing box already sized
  in :mod:`acdt.domains.aircraft.structures`, fuselage, empennage, lifting-line feedback) lives in
  :mod:`acdt.domains.aircraft.structures_l1`, because it needs the aircraft geometry and must not
  be imported from ``core``.

Nothing in this package imports ``acdt.domains``.
"""
from acdt.core.structures.beam import (cantilever_response, cylinder_axial_knockdown, thin_circular_tube,
                                      tube_thickness)
from acdt.core.structures.boxfem import FEModel as BoxFEM
from acdt.core.structures.loads import (angular_tail_increment, checked_maneuver_alpha, equilibrium_tail_load,
                                       surface_limit_lift)

__all__ = ["BoxFEM", "cantilever_response", "cylinder_axial_knockdown", "thin_circular_tube", "tube_thickness",
           "angular_tail_increment", "checked_maneuver_alpha", "equilibrium_tail_load", "surface_limit_lift"]
