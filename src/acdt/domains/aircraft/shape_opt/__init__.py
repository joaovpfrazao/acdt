"""P6 light N2 shape optimisation: aero/RCS DOE + packaging score (heavy CFD → Grok Build)."""
from .n2 import BOUNDS_N2, packaging_score, run_n2_study  # noqa: F401

__all__ = ["BOUNDS_N2", "packaging_score", "run_n2_study"]
