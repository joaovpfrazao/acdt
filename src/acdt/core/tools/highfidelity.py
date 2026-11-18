"""Fase 4 — verificação de alta fidelidade (entry points).

The implementations are domain-specific (they need the parametric geometry and the low-fidelity result);
for aircraft they live in :mod:`acdt.domains.aircraft.hifi` (OpenVSP geometry, Gmsh, SU2, CalculiX, DLM
flutter, Nastran deck, calibration). These wrappers dispatch there; OpenFOAM remains a stub."""
from acdt.core._stub import not_implemented


def su2_rans_case(design, work):
    """SU2 RANS-SA section verification (Gmsh hybrid mesh) of CD0/CLmax/Cm — aircraft: hifi.cfd.verify_section."""
    from acdt.domains.aircraft.hifi.cfd import verify_section
    return verify_section(design, work)


def openfoam_case(geometry, condition):
    """OpenFOAM simpleFoam case as an independent CFD cross-check."""
    not_implemented("OpenFOAM case", "OpenFOAM (Weller et al. 1998)", "Phase 4 (SU2 used instead)")


def calculix_wingbox(design, work, **kw):
    """CalculiX S8R/B32 shell FE model of the wing box (stress, buckling, modes) — aircraft: hifi.fem.run_box_fem."""
    from acdt.domains.aircraft.hifi.fem import run_box_fem
    return run_box_fem(design, work, **kw)
