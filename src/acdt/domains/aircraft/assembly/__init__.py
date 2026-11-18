"""Generic component-based aircraft geometry, integration requirements and packaging / FOV checker (P1).

See :mod:`.components` (Body, Surface, Disc), :mod:`.assembly` (Assembly + RCS/STL/AVL adapters) and
:mod:`.integration` (Item, constraints, :func:`check`)."""
from .assembly import Assembly, component_from_dict
from .components import Body, Disc, Surface
from .integration import Item, check, check_fov, mass_properties, place

__all__ = ["Assembly", "Body", "Disc", "Surface", "Item", "check", "check_fov", "component_from_dict",
           "mass_properties", "place"]
