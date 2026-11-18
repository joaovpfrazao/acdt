"""Electronics & systems first-cut selection (Phase 1E).

Modules: database (example component DB), electric_propulsion (motor/propeller/ESC),
battery (cell chemistry, S/P configuration, C-rate), servos (hinge moments),
avionics (autopilot selection, power budget), harness (wire sizing, netlist,
WireViz/Graphviz export), compliance (standards checklist), mass (mass & CG),
integrate (design point -> systems, with mass/energy closure back to sizing).
"""
from .database import ComponentDB, load_default_db  # noqa: F401
from . import electrical, payload_trade  # noqa: F401  # P4

