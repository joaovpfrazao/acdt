"""Small linear finite-element core (domain-agnostic) for thin-walled structures in the optimisation loop.

Elements (standard formulations, references in each docstring):

* 4-node flat shell, 6 DOF/node: QM6 incompatible-mode membrane (Taylor, Beresford & Wilson 1976) + MITC4
  Reissner–Mindlin bending/transverse shear (Bathe & Dvorkin 1985) + small drilling stiffness;
  isotropic, orthotropic and symmetric laminate / sandwich (equivalent single layer, FSDT: Reddy 2004).
* 2-node 3-D Euler–Bernoulli beam with rigid offsets (Przemieniecki 1968, Ch. 5) — stringers, spar caps.
* 2-node bar (truss) — mass arms.

Analyses: linear static, linear buckling (K + λ K_G) φ = 0 (Cook, Malkus, Plesha & Witt 2002, Ch. 18), normal
modes K φ = ω² M φ (lumped mass). Sparse assembly (SciPy), ARPACK shift-invert eigen-solutions.

Why not an external library: scikit-fem (BSD) has no shell elements; TACS (Apache-2.0) needs MPI/conda builds and
is not on PyPI; CalculiX (GPL) stays the L3 verifier (Phase 4). This core is verified against closed-form
solutions and against the Phase 4 CalculiX S8R model (tests/test_fem_core.py, docs/tutorial-fase5.md)."""
from .laminate import ShellSection, isotropic, laminate, orthotropic  # noqa: F401
from .model import FEModel  # noqa: F401
