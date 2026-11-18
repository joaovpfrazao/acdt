// acdt Phase 4 — full aircraft half model, RANS-SA (Gmsh 4.x). First cell 7.47e-06 m (y+ 1).
SetFactory("OpenCASCADE");
Geometry.OCCTargetUnit = "M";
v() = ShapeFromFile("cessna172_check.step");
// keep y >= 0, build fluid = box − aircraft, symmetry at y = 0 (see wing_half_mesh in cfd3d.py)
Mesh.MeshSizeMin = 0.003498;
Mesh.MeshSizeMax = 27.98;
Mesh.Algorithm3D = 10;
// prism layer: Field[1] = BoundaryLayer (Gmsh ≥ 4.11 supports 3-D BL via Extrude Boundary Layer) —
// 42 layers, first 7.47e-06 m, ratio 1.2
