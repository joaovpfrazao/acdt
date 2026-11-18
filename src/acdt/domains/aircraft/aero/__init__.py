"""Low-fidelity aerodynamics: classical handbook first-cut (lift.py, drag.py) and
wrappers to established open-source tools (interfaces.py: NeuralFoil/XFOIL, AVL, OpenVSP)."""
from .lift import *  # noqa: F401,F403
from .drag import *  # noqa: F401,F403
