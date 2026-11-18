// acdt Phase 4 — half-wing Euler mesh (written by acdt, meshed by the gmsh executable)
SetFactory("OpenCASCADE");
Geometry.OCCTargetUnit = "M";
imp() = ShapeFromFile("../../cessna172_check_hifi/geometry/cessna172_check_wing.step");
all() = Surface{:};
// y >= 0 faces; a face whose bounding box repeats an accepted one (the root cap is exported once per
// half-wing by OpenVSP) is dropped, otherwise the sewn shell self-intersects and the boolean fails
right() = {}; left() = {}; rb() = {};
For i In {0 : #all() - 1}
  bs() = BoundingBox Surface{all(i)};
  dup = 0;
  For j In {0 : #right() - 1}
    d = 0;
    For k In {0 : 5}
      d = d + Fabs(bs(k) - rb(6 * j + k));
    EndFor
    If (d < 1e-6)
      dup = 1;
    EndIf
  EndFor
  If (bs(1) > -1e-5 && dup == 0)
    right() += all(i);
    rb() += bs();
  Else
    left() += all(i);
  EndIf
EndFor
If (#left() > 0)
  Recursive Delete{ Surface{left()}; }
EndIf
sl = newsl;
Surface Loop(sl) = {right()} Using Sewing;
wing = newv;
Volume(wing) = {sl};
R = 27.605204928703397;
semispan = 4.999850935151839;
bw() = BoundingBox Volume{wing};
xmin = bw(0); zmin = bw(2); xmax = bw(3); zmax = bw(5);
box = newv;
Box(box) = {xmin - R, 0.0, zmin - R, (xmax - xmin) + 2 * R, semispan + R, (zmax - zmin) + 2 * R};
fluid() = BooleanDifference{ Volume{box}; Delete; }{ Volume{wing}; Delete; };
vol = fluid(0);
faces() = Boundary{ Volume{vol}; };
wall() = {}; sym() = {}; far() = {};
For i In {0 : #faces() - 1}
  t = Fabs(faces(i));
  b() = BoundingBox Surface{t};
  If (Fabs(b(1)) < 1e-6 && Fabs(b(4)) < 1e-6)
    sym() += t;
  Else
    If (b(0) < xmin - 0.5 * R || b(3) > xmax + 0.5 * R || b(2) < zmin - 0.5 * R || b(5) > zmax + 0.5 * R || b(4) > semispan + 0.5 * R)
      far() += t;
    Else
      wall() += t;
    EndIf
  EndIf
EndFor
Printf("ACDT_MARKERS %g %g %g", #wall(), #sym(), #far());
Field[1] = Distance;
Field[1].SurfacesList = {wall()};
Field[1].Sampling = 60;
Field[2] = Threshold;
Field[2].InField = 1;
Field[2].SizeMin = 0.03450650616087925;
Field[2].SizeMax = R / 4;
Field[2].DistMin = 0.027605204928703397;
Field[2].DistMax = R;
Field[3] = Box;
Field[3].VIn = 0.0690130123217585;
Field[3].VOut = R;
Field[3].XMin = xmin - 0.41407807393055096;
Field[3].XMax = xmax + 2.7605204928703397;
Field[3].YMin = 0;
Field[3].YMax = 5.999821122182206;
Field[3].ZMin = zmin - 0.6901301232175849;
Field[3].ZMax = zmax + 0.6901301232175849;
Field[3].Thickness = 2.7605204928703397;
Field[4] = Min;
Field[4].FieldsList = {2, 3};
Background Field = 4;
Mesh.MeshSizeExtendFromBoundary = 0;
Mesh.MeshSizeFromPoints = 0;
Mesh.MeshSizeFromCurvature = 0;
Mesh.Algorithm = 6;
Mesh.MeshSizeMin = 0.008626626540219812;
Mesh.Algorithm3D = 1; // Delaunay
Physical Surface("wing") = {wall()};
Physical Surface("symmetry") = {sym()};
Physical Surface("farfield") = {far()};
Physical Volume("fluid") = {vol};
