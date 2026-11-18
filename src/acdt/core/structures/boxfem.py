"""BoxFEM — the in-house shell finite-element model (QM6 + MITC4).

The implementation stays in :mod:`acdt.core.fem`. This module is the short name used by the L1
structural stack. Importing it does not move or wrap the elements: ``BoxFEM`` is ``FEModel``.
"""
from acdt.core.fem.laminate import ShellSection, isotropic, laminate, orthotropic, sandwich
from acdt.core.fem.model import FEModel

BoxFEM = FEModel

__all__ = ["BoxFEM", "FEModel", "ShellSection", "isotropic", "laminate", "orthotropic", "sandwich"]
