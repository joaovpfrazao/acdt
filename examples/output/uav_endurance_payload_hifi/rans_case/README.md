# Caso RANS-SA da aeronave completa (meia aeronave) — máquina mais forte

* Re_mac: 448147.0866022125
* first_cell_m: 1.5467691823447735e-05
* surface_spacing_m: 0.0031199301129453544
* n_surface_tri: 442454
* prism_layers: 30
* cells_estimate: 15928368
* ram_GB: 28.671064065490626
* wall_h_8cores_3alpha: 53.094563084241905
* wall_h_64cores_3alpha: 6.636820385530238

```
cd /workspace/aircraft-design-tools/examples/output/uav_endurance_payload_hifi/rans_case
gmsh aircraft_rans.geo -3 -format su2 -o aircraft_half.su2
mpirun -n <N> SU2_CFD aircraft_rans.cfg   # AOA in the cfg; repeat for α = 0, 2, 4 (+ stall sweep)
```

O .geo indica a construção (como `cfd3d.wing_half_mesh`); a camada de prismas 3-D tem de ser verificada (qualidade, y+) antes de correr.
