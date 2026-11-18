"""Phase 4 — detailed design and high-fidelity verification (L3).

Modules: :mod:`tools` (external-tool discovery and the box-capacity guard), :mod:`geometry` (OpenVSP
.vsp3/STEP/STL + render), :mod:`cfd` (Gmsh meshes + SU2 RANS/Euler cases), :mod:`wing_bl` (pyHyp prism
mesh of the tailless wing and the 3-D GCI), :mod:`fem` (CalculiX shell
wing box: static, linear buckling, modes), :mod:`flutter` (FEM modes + doublet-lattice p-k, SOL 145 deck),
:mod:`calibration` (L3 → L1/L2 factors), :mod:`detailed` (ribs, joints, control surfaces, Roskam Class II),
:mod:`kicad` (netlist). L3 *verifies*; it does not size (docs/ARCHITECTURE.md §5)."""
