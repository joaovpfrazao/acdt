"""Sparse direct factorisation used by the FE core.

Intel oneMKL PARDISO through ``pypardiso`` (BSD-3 wrapper; MKL under the Intel Simplified Software Licence) when
installed — an order of magnitude faster than SuperLU's COLAMD ordering on shell meshes — else SciPy SuperLU."""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

try:  # optional
    import pypardiso as _pp
except Exception:  # pragma: no cover
    _pp = None


class Factor:
    def __init__(self, A, symmetric: bool = True):
        self.n = A.shape[0]
        if _pp is not None:
            self.A = sp.csr_matrix(A)
            self._s = _pp.PyPardisoSolver(mtype=11)
            self._s.factorize(self.A)
            self.backend = "pardiso"
        else:
            self._lu = spla.splu(sp.csc_matrix(A))
            self.backend = "superlu"

    def solve(self, b):
        b = np.asarray(b, float)
        if self.backend == "pardiso":
            return self._s.solve(self.A, b)
        return self._lu.solve(b)

    def free(self):
        if self.backend == "pardiso":
            self._s.free_memory(everything=True)

    def op(self):
        return spla.LinearOperator((self.n, self.n), matvec=self.solve, dtype=float)


def backend() -> str:
    return "pardiso" if _pp is not None else "superlu"
