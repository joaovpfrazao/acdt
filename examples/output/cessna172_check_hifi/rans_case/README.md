# Caso RANS-SA da aeronave completa (meia aeronave) — máquina mais forte

* Re_mac: 4938738.058685804
* first_cell_m: 7.470485118065404e-06
* surface_spacing_m: 0.01399010730768489
* n_surface_tri: 291005
* prism_layers: 42
* cells_estimate: 13968267
* ram_GB: 25.142882380292697
* wall_h_8cores_3alpha: 46.56089329683832
* wall_h_64cores_3alpha: 5.82011166210479

```
cd /workspace/aircraft-design-tools/examples/output/cessna172_check_hifi/rans_case
gmsh aircraft_rans.geo -3 -format su2 -o aircraft_half.su2
mpirun -n <N> SU2_CFD aircraft_rans.cfg   # AOA in the cfg; repeat for α = 0, 2, 4 (+ stall sweep)
```

O .geo indica a construção (como `cfd3d.wing_half_mesh`); a camada de prismas 3-D tem de ser verificada (qualidade, y+) antes de correr.
