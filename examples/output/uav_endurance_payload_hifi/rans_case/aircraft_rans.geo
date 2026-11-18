// acdt Phase 4 — full aircraft half model, RANS-SA (Gmsh 4.x). First cell 1.55e-05 m (y+ 1).
SetFactory("OpenCASCADE");
Geometry.OCCTargetUnit = "M";
v() = ShapeFromFile("uav_endurance_payload.step");
// keep y >= 0, build fluid = box − aircraft, symmetry at y = 0 (see wing_half_mesh in cfd3d.py)
Mesh.MeshSizeMin = 0.00078;
Mesh.MeshSizeMax = 6.24;
Mesh.Algorithm3D = 10;
// prism layer: Field[1] = BoundaryLayer (Gmsh ≥ 4.11 supports 3-D BL via Extrude Boundary Layer) —
// 30 layers, first 1.55e-05 m, ratio 1.2
