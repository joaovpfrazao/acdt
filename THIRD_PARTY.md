# Third-party software

acdt is licensed under the Apache License 2.0 (see `LICENSE` and `NOTICE`). The repository **contains no third-party source code**. This file lists the
external projects acdt depends on, wraps or uses as a reference. Licences and maintenance status
were checked against the projects' official repositories (GitHub API `license` / `pushed_at`,
or the official project pages) in **October 2026**. Re-check them before any redistribution.

## Runtime dependencies (installed via pip, imported)

| package | licence | source | use |
|---|---|---|---|
| NumPy | BSD-3-Clause | https://github.com/numpy/numpy | numerics |
| Matplotlib | Matplotlib licence (PSF-based, BSD-compatible) | https://github.com/matplotlib/matplotlib | plots |
| PyYAML | MIT | https://github.com/yaml/pyyaml | mission / database files |
| pytest (dev) | MIT | https://github.com/pytest-dev/pytest | tests |

## Optional, imported (permissive / weak copyleft, installed by the user via extras)

| project | origin | licence | status (2026-10) | acdt integration |
|---|---|---|---|---|
| AeroSandbox | Peter Sharpe (MIT) — https://github.com/peterdsharpe/AeroSandbox | MIT | active (tested 4.2.10) | `[aero]`: VLM / AeroBuildup cross-check (`aero/interfaces.py`) |
| NeuralFoil | Peter Sharpe (MIT) — https://github.com/peterdsharpe/NeuralFoil | MIT | active (tested 0.3.3) | `[aero]`, `[wingbox]`: airfoil polars; Phase 2 fallback when XFOIL is not installed; Phase 5 `wingbox/aero.py` polars of continuous NACA 4-digit sections (t/c, camber as design variables) |
| OpenMDAO | NASA Glenn — https://github.com/OpenMDAO/OpenMDAO | Apache-2.0 | active (tested 3.45.1) | `[mdo]`: Phase 3 MDA/MDO |
| dymos | NASA — https://github.com/OpenMDAO/dymos | Apache-2.0 | active | Phase 3 trajectory (planned) |
| OpenAeroStruct | U. Michigan MDO Lab / NASA — https://github.com/mdolab/OpenAeroStruct | Apache-2.0 | low activity (last push 2025-10; tested 2.12.0) | `[mdo]`: Phase 3 static aero-structural coupling (VLM + wing-box), `aeroelasticity.static_aerostructural` |
| pyOptSparse | U. Michigan MDO Lab — https://github.com/mdolab/pyoptsparse | LGPL-3.0 | active | optional optimisers, dynamically imported only |
| pyNastran | https://github.com/SteveDoyle2/pyNastran | BSD-3-Clause | active (tested 1.3.4) | `[structures]`, `[hifi]`: Phase 4 SOL 103 / SOL 145 decks (`hifi/nastran.py`), written and read back with xref |
| PanelAero | DLR Institute of Aeroelasticity — https://github.com/DLR-AE/PanelAero | BSD-3-Clause | active (tested 2025.8) | `[hifi]`: Doublet-Lattice AIC for the Phase 4 p-k flutter (`hifi/flutter.py`) |
| SciPy | https://github.com/scipy/scipy | BSD-3-Clause | active (tested 1.18.1) | `[hifi]`, `[wingbox]`: root finding (`aeroelasticity.py`); Phase 5 sparse matrices, `splu`, `eigsh` (ARPACK, BSD) and SLSQP (`wingbox/optimize.py`) |
| pypardiso | A. Haas — https://github.com/haasad/PyPardiso | BSD-3-Clause | active (tested 0.4.7) | `[fastfem]`, optional: sparse direct solver for the Phase 5 shell FEM (`core/fem/solvers.py`); falls back to SciPy `splu` when absent |
| Intel oneMKL (PyPI `mkl`, pulled in by pypardiso) | Intel — https://pypi.org/project/mkl/ | Intel Simplified Software Licence (proprietary, free redistribution) | active (tested 2026.2.0) | PARDISO back-end of pypardiso; never required, never shipped by acdt |
| kinparse | D. Vandenbout — https://github.com/devbisme/kinparse | MIT | low activity (tested 1.2.4) | `[hifi]`, tests only: parses the exported KiCad netlist back (round-trip check) |
| Loads Kernel | DLR Institute of Aeroelasticity — https://github.com/DLR-AE/LoadsKernel | BSD-3-Clause | active (last push 2026-10) | not used: Phase 4 uses PanelAero (same group) directly for the DLM |
| MCP Python SDK (`mcp`) | Model Context Protocol project — https://github.com/modelcontextprotocol/python-sdk | MIT | active (tested 2.3.0; v1 `FastMCP` API also supported) | `[ai]`: `acdt mcp` server (`acdt/ai/mcp_server.py`), stdio and streamable HTTP. Pulls in pydantic (MIT), anyio (MIT), starlette (BSD-3-Clause), uvicorn (BSD-3-Clause), sse-starlette (BSD-3-Clause) |

### Phase 5 shell FEM: why in-house

`core/fem` (flat Q4 shell = QM6 membrane + MITC4 plate + small artificial drilling stiffness, offset Euler–Bernoulli beams,
linear buckling and modal) is written in acdt from textbook formulations (Bathe & Dvorkin 1985; Taylor, Beresford & Wilson
1976 QM6; Cook et al., *Concepts and Applications of FEA*). Open alternatives were checked
(2026-10): TACS (MDO Lab, Apache-2.0) has no usable PyPI wheel (the PyPI name is a placeholder; it needs an
MPI/C++ build), scikit-fem (BSD) has no shell elements, and CalculiX/NASTRAN are external executables already
used in Phase 4 for verification, too slow for an optimisation loop. Nothing was copied from them.

### Phase 6 RCS: why in-house

`core/em/po.py` implements Physical Optics from the textbook formulation (Knott, Shaeffer & Tuley; Balanis) and
Gordon's closed-form facet integral (IEEE TAP 1975). Checked (2026-10) as references, **no code copied**:

| project | origin | licence | status | use |
|---|---|---|---|---|
| POFACETS | D. Jenn, Naval Postgraduate School (MATLAB) | US-government work, distributed without a licence file (treated as public domain; verify before redistribution) | archival | reference for the same PO facet formulation; results not imported |
| PyPOFacets | Python port of POFACETS (GEMS/UFF) — https://github.com/gems-uff/pypofacets | MIT | active (last push 2026-04) | reference only; not imported |
| openEMS | T. Liebig et al. — https://github.com/thliebig/openEMS | GPL-3.0 | active (last push 2026-10) | **future** full-wave (FDTD) verification of RCS at high fidelity; would be called as an external executable only |

OpenMDAO (Apache-2.0, above) drives the Phase 6 aero/RCS DOE; SciPy (BSD-3-Clause, above) provides
`scipy.stats.qmc` (Latin hypercube) and COBYLA/SLSQP. The Phase 6 wing-box sizing, rib sizing and beam ↔ shell
calibration are in-house (textbook methods cited in the code).

## Planned / optional high fidelity (N2/N3, NOT installed, NOT imported; separate processes only)

Aerostructural RANS-adjoint chain from the MDO Lab family, chosen on 3 Nov 2026 as an N2/N3 option next to SU2
(same OpenMDAO framework acdt already uses). Nothing below is a dependency yet: acdt will only write input files
(geometry, mesh scripts, run scripts) and read JSON/CGNS results back. ADflow is LGPL, so it runs **only in its own
process** (Docker image with MPI, launched by a run script); it is never imported by the acdt process. Licences
checked on the official repositories (LICENSE / GitHub API) on **2026-11-03**.

| project | origin | licence | status (2026-11) | planned use |
|---|---|---|---|---|
| ADflow | MDO Lab, U. Michigan — https://github.com/mdolab/adflow | LGPL-2.1 | active (last push 2026-10) | N2/N3: RANS (SA) with discrete adjoint, overset structured meshes; external process (Docker/MPI) |
| TACS | SMDO group (Kennedy, Georgia Tech) / MDO Lab — https://github.com/smdogroup/tacs | Apache-2.0 | active (last push 2026-11) | N2/N3: thin-walled composite FE with adjoints and buckling; coupled to ADflow through MPhys |
| MPhys | NASA / OpenMDAO — https://github.com/OpenMDAO/mphys | Apache-2.0 | active (last push 2026-10) | multiphysics coupling (ADflow + TACS + mesh warping) on OpenMDAO, inside the external process |
| pyGeo | MDO Lab — https://github.com/mdolab/pygeo | Apache-2.0 | active (last push 2026-10) | FFD / surface geometry from the assembly OML (IGES/STEP surfaces) |
| pyHyp | MDO Lab — https://github.com/mdolab/pyhyp | Apache-2.0 | active (last push 2026-09) | hyperbolic extrusion of the structured surface mesh into the volume mesh |
| IDWarp | MDO Lab — https://github.com/mdolab/idwarp | Apache-2.0 | active (last push 2026-10) | volume mesh warping during shape optimisation |
| cgnsUtilities | MDO Lab — https://github.com/mdolab/cgnsutilities | Apache-2.0 | active (last push 2026-04) | CGNS mesh manipulation (overset assembly) |
| baseClasses | MDO Lab — https://github.com/mdolab/baseclasses | Apache-2.0 | active (last push 2026-06) | AeroProblem / StructProblem definitions used by ADflow and TACS |

The runs belong to Grok Build on João's PC (see `docs/HANDOFF.md` §4b), never to the cloud box.

## External executables (NOT imported, NOT redistributed; file / CLI interface only)

These are copyleft or non-OSI licences. acdt only writes their input files and/or calls the
user-installed executable, so they never become part of an acdt distribution.

| project | origin | licence | status | interface |
|---|---|---|---|---|
| AVL 3.40 | M. Drela & H. Youngren, MIT — https://web.mit.edu/drela/Public/web/avl/ | GPL | stable (MIT page) | Phase 2: `aero/avl.py` writes the `.avl` geometry and runs `avl` as a subprocess (batch stdin), parses ST/FS output. User-installed (built from source with gfortran) |
| XFOIL 6.99 | M. Drela, MIT — https://web.mit.edu/drela/Public/web/xfoil/ | GPL | stable (MIT page) | Phase 2: `aero/airfoil.py` runs `xfoil` as a subprocess (batch stdin) and reads the polar file. Built from source: the Debian `xfoil` package crashed with SIGFPE in viscous batch mode in our test. NeuralFoil (MIT, imported) is the fallback |
| OpenVSP | NASA — https://github.com/OpenVSP/OpenVSP | NOSA 1.3 | active | Phase 4: `hifi/vsp_build.py` runs in the user's OpenVSP Python (`$ACDT_VSP_PYTHON`, separate process) to build the .vsp3 / STL / render; acdt only passes a JSON description |
| NASTRAN-95 | NASA — https://github.com/nasa/NASTRAN-95 | NASA Open Source Agreement 1.3 | archival (no support) | Phase 4 optional solver for pyNastran-written decks |
| Gmsh | C. Geuzaine & J.-F. Remacle — https://gitlab.onelab.info/gmsh/gmsh | GPL-2.0-or-later | active (tested 4.15.2, `gmsh` via `$ACDT_HIFI_BIN`) | Phase 4: `hifi/cfd.py`, `cfd3d.py` write `.geo` scripts and run the `gmsh` executable as a separate process (`hifi/tools.run_gmsh`: `gmsh <case>.geo -2/-3 -format su2 -o <mesh>.su2`); acdt reads the `.su2` mesh back. Since 2026-10 the Gmsh Python library is no longer imported anywhere in acdt |
| SU2 | Stanford / SU2 Foundation — https://github.com/su2code/SU2 | LGPL-2.1 | active (tested 8.5.0, `SU2_CFD` via `$ACDT_HIFI_BIN`) | Phase 4: `hifi/cfd.py`, `cfd3d.py` write `.cfg`/`.su2` and run `SU2_CFD` (optionally under `mpirun`) |
| OpenFOAM | OpenFOAM Foundation — https://github.com/OpenFOAM/OpenFOAM-dev | GPL-3.0 | active | Phase 4 case files |
| CalculiX | G. Dhondt — https://github.com/Dhondtguido/CalculiX , http://www.calculix.de | GPL-2.0 | active (tested ccx 2.23) | Phase 4: `hifi/fem.py` writes `.inp` and runs `ccx` (static, buckling, frequency); reads `.dat`/`.frd` |
| WireViz | https://github.com/wireviz/WireViz | GPL-3.0 | active | acdt writes `harness.wireviz.yml`; run `wireviz` yourself |
| KiCad | https://gitlab.com/kicad/code/kicad | GPL-3.0 | active | Phase 4: `harness.kicad_netlist` writes a KiCad s-expression netlist (format "E", `harness.net`) for Pcbnew import; file format only, no KiCad code |
| JSBSim | J. S. Berndt and the JSBSim team — https://github.com/JSBSim-Team/jsbsim | LGPL-2.1 | active (tested 1.3.3, PyPI `jsbsim`) | Phase 8: `flightsim/jsbsim_export.py` writes a JSBSim aircraft XML from acdt's own flight model (acdt-generated data, no JSBSim content); `flightsim/jsbsim_runner.py` runs a driver script in a **separate Python process** (`$ACDT_JSBSIM_PYTHON`, default the current interpreter) and exchanges JSON. The `jsbsim` module is never imported in the acdt process. Used as an independent cross-check of the in-house 6-DOF (trim and doublet time histories) |
| CadQuery | CadQuery developers — https://github.com/CadQuery/cadquery | Apache-2.0 | optional extra `acdt[cad]` (tested 2.8.0) | `cad_build.py` and `assembly/step_build.py` only (separate processes). Write the structure STEP and the faceted component-assembly STEP. Not imported by the acdt process |
| cadquery-ocp / Open CASCADE | Open Cascade — https://dev.opencascade.org/ (wheel `cadquery-ocp`) | LGPL-2.1 | pulled in by CadQuery, separate process only | kernel behind `cad_build.py` / `assembly/step_build.py`. The acdt process never imports it |

## Reference only (results compared, code never imported)

| project | origin | licence | status | why not imported |
|---|---|---|---|---|
| FAST-OAD | ONERA / ISAE-SUPAERO / Airbus — https://github.com/fast-aircraft-design/FAST-OAD | GPL-3.0 | active (v1.10.0, 2026-06) | GPL; used as an independent cross-check |
| RCAIDE | Stanford ADL / LEADS — https://github.com/leadsgroup/RCAIDE_LEADS | AGPL-3.0 | active | AGPL; cross-check only |
| SUAVE | Stanford ADL — https://github.com/suavecode/SUAVE | LGPL-2.1 | **superseded** (last push 2024-02) | superseded by RCAIDE; not imported. Its public Raymer GA weight implementation was read only to confirm the interpretation of Eqs. 15.47–15.48 (tail aspect ratio); no code copied |

## Phase 8 methods and references (control surfaces and 6-DOF simulator)

No new code dependency (JSBSim is listed above as an external executable). The 6-DOF integrator, autopilot,
Dryden filters and control-surface sizing are in-house, written from the publications below (cited in the code):

* Sadraey, *Aircraft Design: A Systems Engineering Approach* (Wiley 2012), Ch. 12 (control surfaces);
* Stevens, Lewis & Johnson, *Aircraft Control and Simulation*, 3rd ed. (Wiley 2016) (equations of motion);
* Beard & McLain, *Small Unmanned Aircraft: Theory and Practice* (Princeton 2012), Ch. 4 (Dryden, Table 4.1),
  Ch. 6 (successive loop closure), Ch. 10 (path following); its Aerosonde stall-blend sharpness M = 50;
* MIL-F-8785C (handling qualities, roll time-to-bank), CS 25.341 (1−cos gust shape), 14 CFR 23.233 and 23.455.
* Validation data (retrieved 2026-10-28): Cessna 172S POH / Information Manual, Rev. 5 (2004), "Performance –
  Specifications"; JSBSim `aircraft/c172p/c172p.xml` (LGPL-2.1, "educational and entertainment purposes
  only" per its header) used **only** as a reference for inertias — not copied or redistributed; Sadraey
  (2012) Ch. 12 control-surface tables (Cessna 182) as historical comparison.

## Data

The component entries named `*_class` in `src/acdt/core/data/components.yaml` are **illustrative
values** for a component class. The few entries named after a real product (autopilots) carry
approximate public figures, each with its `url`/`source`. Neither kind copies a datasheet. Verify
the values against the current datasheet before any design decision. The standards list in
`standards.yaml` names each document with its issuer. It does not reproduce the documents' text.

Regulations used by the Phase 2 V-n diagram (`structures.py`): EASA CS-23 / 14 CFR Part 23 (legacy
§23.333–23.341 load-factor and gust clauses) and NATO STANAG 4671 (USAR.333–USAR.341). Only the
formulae are implemented, each with its clause number in the code. The clause texts are not
reproduced. Check them against the amendment that applies before use.

## Phase 7 methods and data (manufacturing and cost)

No new code dependency. The methods are implemented from the publications below, each cited in the code
(`manufacturing/refdata.py`). Only the parameters needed are reproduced, each with its source.

* Process time (FOPV):
  * Gutowski et al. (1994), *Compos. Manuf.* 5(4), for the hyperbolic process-time model;
  * Bao & Samareh (2000) and Bao (2002), NASA grant NAG-1-2195, Table 4.1 V0/τ (NTRS 20020065232, https://ntrs.nasa.gov/citations/20020065232; o relatório inclui o AIAA-2000-4839 em anexo).
* ACCEM lay-up hours: Hagnell & Åkermo (2016), *Adv. Manuf. Polym. Compos. Sci.*
* Buy-to-fly:
  * Airbus (2018) newsroom;
  * Alma CAM / DAHER-Socata case study;
  * Gonzalo et al. (2023, Scipedia).
* Rivet rules: FAA-H-8083-31 and AC 43.13-1B. Composite rules: Abbott (2019), after MIL-HDBK-17F.
* Cost estimating relationships:
  * DAPCA IV: Raymer (2018) Ch. 18;
  * modified Eastlake: Gudmundsson (2014) Ch. 2.
* Learning curves: Wright (1936), Crawford (1944), NASA JSC learning-curve calculator.
* Material indices: Ashby, *Materials Selection in Mechanical Design*.
* Uncertainty bands per cost level: AACE International RP 18R-97, Table 1 (expected accuracy ranges, cited,
  not reproduced beyond the class limits).
* Escalation: U.S. BLS CPI-U (CUUR0000SA0) annual averages; the 2026 value is the September 2026 monthly index.
* Validation and example inputs (retrieved 2026-10-28; prices are retail, dated and cited in the example YAMLs):
  * GAMA 2024 Year-End Shipment Report;
  * fliegermagazin (2025-05-05) C172 list price;
  * Aircraft Spruce catalogue prices (2024-T3 sheet and plate, carbon fabric, Aeropoxy resin);
  * laminate properties from Suranaree J. Sci. Technol. (article 12583).


## Phase 9 methods and references (fixed-pitch propeller, inertias, camber flaps)

* Propeller blade-element momentum theory (in-house implementation):
  * McCormick, *Aerodynamics, Aeronautics and Flight Mechanics*, 2nd ed. (1995), Ch. 6;
  * Glauert (1935) and the Prandtl tip-loss factor;
  * Ning, "A simple solution method for the blade element momentum equations with guaranteed
    convergence", *Wind Energy* 17 (2014) — one-equation residual in the inflow angle;
  * Viterna & Corrigan (1982), NASA CP-2230 — post-stall extrapolation of the section polar;
  * Adkins & Liebeck, *J. Propulsion & Power* 10(5) (1994) — design cl at max cl/cd (auto chord).
* Section polar (Clark Y, a PRESSUPOSTO for the McCauley 1C235/LFA7570): NeuralFoil (MIT, already imported).
* Cessna 172 propeller and climb data (validation only): Cessna 172S Information Manual (static rpm,
  730 ft/min sea-level ROC, ground roll), McCauley model designation for the diameter/pitch.
* Radii of gyration: Roskam, *Airplane Design Part V* (1985), Eqs. 3.7–3.9 and Appendix B, Table B2
  (non-dimensional radii of gyration of single-engine propeller airplanes, values cited, not reproduced beyond
  the six rows used).
* JSBSim c172p `mass_balance` (LGPL data file, reference only, never redistributed): empty-aircraft
  inertias used for comparison.

### Phase 9 — camber (cruise) flaps as a design option

Methods only (no code copied); all implemented in `aero/camber_flap.py` and `design_options.py`:

* F. Thomas, *Fundamentals of Sailplane Design*, College Park Press, 1999 — Ch. 3 (airfoils, laminar bucket) and
  Ch. 5 (camber flaps, flap schedule δ(CL), flaps used as landing flaps).
* D. Althaus & F. X. Wortmann, *Stuttgarter Profilkatalog I*, Vieweg, 1981 — FX flapped laminar sections (the
  envelope-polar concept; FX 67-K-150 coordinates from the UIUC database were tried, see the tutorial).
* L. M. M. Boermans & G. Waibel, "Aerodynamic and structural design of the Standard Class sailplane ASW-24",
  ICAS-88-2.7.2, 1988; L. M. M. Boermans, "Research on sailplane aerodynamics at Delft University of
  Technology", *Technical Soaring* 30(1/2), 2006 — flapped sections and schedules.
* D. P. Raymer, *Aircraft Design: A Conceptual Approach*, 6th ed., Eq. 12.21 and Table 12.2 — ΔCLmax of the
  flapped area (plain flap, landing deflection).
* S. Gudmundsson, *General Aviation Aircraft Design*, 2014, Sec. 2.2.2 — Eastlake F_CF (complex flaps 1.03).
* M. Drela, XFOIL 6.99 (GPL, separate process) — GDES/FLAP plain-flap geometry and polars.
* AeroSandbox (MIT, P. Sharpe) `Airfoil.add_control_surface` — deflected geometry for NeuralFoil (MIT).
* Selig/Donovan SD7062 coordinates — UIUC Airfoil Coordinates Database (M. Selig), via AeroSandbox.

## Phase 10 methods, regulations and data (certification compliance and safety assessment)

No third-party code is used: FTA (MOCUS, exact probability), FHA targets, compliance matrix and SORA are
in-house implementations. The regulatory texts are **not** reproduced — `cert_catalogue.yaml` holds acdt
paraphrases plus a link to the official source; the authority's text in force prevails.

| Item | Owner / source | Licence / status | Used for |
|---|---|---|---|
| CS-23 Amdt 6 / 14 CFR Part 23 Amdt 23-64 | EASA — https://www.easa.europa.eu/en/document-library/certification-specifications/group/cs-23-normal-utility-aerobatic-and-commuter-aeroplanes ; eCFR — https://www.ecfr.gov/current/title-14/chapter-I/subchapter-C/part-23 | public regulation (paraphrased) | basis selection (23.2005 levels), compliance-matrix rows |
| CS-25 / 14 CFR Part 25, AMC 25.1309 | EASA — https://www.easa.europa.eu/en/document-library/certification-specifications/group/cs-25-large-aeroplanes ; https://www.ecfr.gov/current/title-14/chapter-I/subchapter-C/part-25 | public (paraphrased) | basis rows, FHA targets `amc25_1309` |
| FAA AC 23.1309-1E (Fig. 2, classes I–IV) | FAA — https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_23_1309-1E.pdf | public | FHA probability targets per class |
| STANAG 4671 Ed. 1 (USAR, incl. USAR.1309 / AMC) | NATO NSO — https://nso.nato.int ; index https://everyspec.com/NATO/NATO-STANAG/STANAG_4671_ED-1_40024/ | NATO publication (paraphrased) | basis rows, FHA targets and the "sum of catastrophic ≤ 1e-5" alternative |
| STANAG 4703 / AEP-83 (light UAS < 150 kg, Annex G) | UK MOD — https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/391827/20140916-STANAG-4703_AEP-83_A__1_.pdf | public | basis rows, cumulative catastrophic target 0.0015/MTOW |
| SORA 2.5 — AMC/GM to Reg. (EU) 2019/947 (Tables 1, 3, 5, 14; Annex C AEC) | EASA — https://www.easa.europa.eu/en/document-library/acceptable-means-of-compliance-and-guidance-materials/amc-gm-regulation-eu-2019947 | public (tables transcribed, check the issue in force) | `core/certification/sora.py` iGRC, mitigations, SAIL, OSO robustness |
| EASA Special Condition Light-UAS (Medium Risk) / MoC Light-UAS.2510-01 | EASA | public (referenced only) | design route by SAIL (DVR) |
| SAE ARP4761 / ARP4754A | SAE International | copyrighted standard — process only (FHA → FTA → FMEA), no text reproduced | assessment structure |
| NASA/CR-2001-210647, General Aviation Aircraft Reliability Study (Table A1) | NASA — https://ntrs.nasa.gov/citations/20010069394 | public (US Gov.) | GA instrument/electrical MTBF (`failure_rates.yaml`, kind `published`) |
| ATSB AR-2013-107, Engine failures and malfunctions in light aeroplanes | ATSB — https://www.atsb.gov.au/publications/research-and-analysis-report/2022/aviation/engine-failures-and-malfunctions-light | public | piston engine failure rate |
| Volz DA-26 datasheet (servo life claim) | Volz Servos — https://www.volz-servos.com/fileadmin/user_upload/Downloads/Standard/DA-26_Datasheet_uni.pdf | vendor data (`vendor_claim`) | UAS servo rate proxy |
| United Instruments 5934 altimeter (13 oz) / Mid-Continent MD302 SAM (1.6 lb, install manual 9017782) | unitedinst.com ; mcico.com | vendor data | C172 example unit masses of the standby-instrument options |
| SCRAM (fault-tree tool) | https://github.com/rakhimov/scram | GPL-3.0 | **reviewed, not used** (GPL cannot be imported in-process) |
| `cutsets` (PyPI) | https://pypi.org/project/cutsets/ | MIT | reviewed, not used (MOCUS only; own implementation preferred) |
| openpyxl | https://foss.heptapod.net/openpyxl/openpyxl | MIT | optional `[cert]` extra: coloured XLSX compliance matrix (CSV/MD without it) |

## Methods — concept trade (`core/concept/`, own implementations)

| method | source | licence | use |
|---|---|---|---|
| Haversine great-circle distance | R. W. Sinnott, "Virtues of the Haversine", Sky & Telescope 68(2):159, 1984 | published formula | `geo.great_circle_km` |
| Spherical polygon area | R. G. Chamberlain & W. H. Duquette, "Some algorithms for polygons on a sphere", JPL Publ. 07-03, 2007 | public (NASA/JPL) | `geo.polygon_area_km2` |
| Search theory (random search, definite range) | B. O. Koopman, *Search and Screening* (OEG Rep. 56, 1946; Pergamon 1980); A. R. Washburn, *Search and Detection*, 4th ed., INFORMS 2002 | published | `search.pod`, `ops.sweep` |
| Continuous-coverage cyclic schedule | T. Ha, AFIT-OR-MS-ENS-10-03 (DTIC ADA517241), 2010 | public (US Gov.) | `ops.cycle` |
| Inherent / operational availability | B. S. Blanchard & W. J. Fabrycky, *Systems Engineering and Analysis*, 5th ed., 2011; MIL-HDBK-338B | published / public | `ops.availability` |
| k-out-of-n reliability | P. O'Connor & A. Kleyner, *Practical Reliability Engineering*, 5th ed., 2012; MIL-HDBK-338B | published / public | `reliability.k_of_n` |
| 4/3-earth radar horizon | M. I. Skolnik, *Introduction to Radar Systems*, 3rd ed., 2001, Sec. 8.2 | published | `search.horizon_km` |
| Johnson criteria | J. Johnson, "Analysis of image forming systems", Image Intensifier Symposium, 1958 | published | `search.johnson_range` |
| Pareto dominance; normalised weighted sum | K. Deb, *Multi-Objective Optimization using Evolutionary Algorithms*, 2001; R. T. Marler & J. S. Arora, SMO 26:369–395, 2004 | published | `tradeoff.compare` |

## Methods — structural beam L1 (`core/structures/`, `domains/aircraft/structures_l1.py`)

No new library. The shell FEM is the in-house BoxFEM (`core/fem`, QM6+MITC4). The formulas below are public methods, not copied text.

| method | source | licence | use |
|---|---|---|---|
| Cylinder buckling knockdown γ | NASA SP-8007, *Buckling of Thin-Walled Circular Cylinders*, 1968: φ = √(R/t)/16, γ = 1 − 0.901(1 − e^{−φ}) | public (US Gov.) | `cylinder_axial_knockdown`; fuselage shell thickness. On CFRP the same γ is a stated knockdown, not a laminate test |
| Classical cylinder stress 0.605 E t/R | Timoshenko & Gere, *Theory of Elastic Stability* (ν = 0.3) | published | axial and bending thickness of the fuselage tube |
| Cantilever beam; thin tube A, I, J | Megson, *Aircraft Structures for Engineering Students* | published | `cantilever_response`, `thin_circular_tube` |
| Glauert lifting line with elastic twist | Anderson, *Fundamentals of Aerodynamics*, §5.3; section slope 0.95·2π from Raymer §12.4.1 | published | `wing_elastic` (no NeuralFoil on this path) |

| NACA 4-digit symmetric thickness | Abbott & von Doenhoff, *Theory of Wing Sections*, 1959, Eq. 6.2 (closed TE, a4 = −0.1036) | published | `assembly.components.naca_yt`: lifting-surface meshes and packaging clearance |
| Ray/triangle intersection | Möller & Trumbore, "Fast, minimum storage ray-triangle intersection", *J. Graphics Tools* 2(1), 1997 | published | `assembly.integration.cast`: FOV / sky-view obstruction |
| Fibonacci lattice on the sphere | González, "Measurement of areas on a sphere using Fibonacci and latitude–longitude lattices", *Math. Geosci.* 42, 2010 | published | FOV cone sampling |
| Component interference factors Q per junction | D. P. Raymer, *Aircraft Design: A Conceptual Approach*, 6th ed., Sec. 12.5.5 (nacelle/store 1.5 / 1.3 / 1.0 by distance in diameters; low wing 1.1–1.4; V-tail 1.03, conventional 1.04–1.05, H-tail 1.08); background Hoerner, *Fluid-Dynamic Drag*, 1965, Ch. VIII | published | `assembly.drag.junction_Q` |
| Aft-fuselage upsweep drag (D/q) = 3.83 u^2.5 A_max | Raymer 6th ed., Eq. 12.36 | published | `assembly.drag.upsweep_Dq` |
| Subsonic base drag (D/q) = [0.139 + 0.419 (M − 0.161)²] A_base | Raymer 6th ed., Eq. 12.37 | published | `assembly.drag.base_Dq` |
| Leakage & protuberance 5–10 % (propeller aircraft) | Raymer 6th ed., Sec. 12.5.10 | published | `assembly.drag.cd0_buildup` (nominal 5 %, pessimistic 10 %) |
| Sphere C_D 0.47, circular cylinder in cross-flow C_D 1.2 (subcritical) | S. F. Hoerner, *Fluid-Dynamic Drag*, 1965, Ch. III | published | `assembly.drag.protuberance_Dq` |
| Geometric similarity of the drawn assembly to the sized wing area (k = √(S/S₀)) | conceptual-design convention (PRESSUPOSTO, no single source) | — | `assembly.loop.scale_spec` |

## VTOL / eVTOL L0 methods and references (`acdt vtol`, November 2026)

Own implementation of textbook equations; **no third-party code or data copied or imported**.

* Momentum theory, figure of merit, axial climb, Glauert inflow, blade loading: Johnson, *Helicopter Theory*
  (Princeton 1980); Leishman, *Principles of Helicopter Aerodynamics*, 2nd ed. (Cambridge 2006).
* Battery energy/reserve/DoD convention: Hepperle 2012 (NATO STO-MP-AVT-209), as in `acdt size`.
* NDARC (W. Johnson, NASA/TP-2015-218751) — NASA software distributed under its own NASA release terms; used
  **only as a method reference** for eVTOL sizing, not installed, wrapped or redistributed.
* Opt-in VTOL mass closure (`vtol/closure.py`, 9 Nov 2026): own implementation of published regression
  equations from the NDARC Theory Manual (Johnson, NASA/TP-2015-218751, April 2015): Ch. 27-2 AFDD00 blade and
  hub-hinge weight (with f_tilt = 1.17940) and the rotor-support form W_supt = f_supt W_MTO; Ch. 22-4 NASA15 motor
  weight W = 0.5382 f_design Q^0.8129 (f_design 1.0 / 2.5606) and high-torque fit 0.3928 Q^0.8587; Ch. 22-1
  controller 10–30 % (to 70 %) range quoted as context only. Coefficients transcribed from the public NASA report
  (equations, not software); no NDARC code or data files used. Bisection: Burden & Faires 2011 §2.1.

## Métodos de jatos subsónicos L0 (6 nov 2026)

Implementação própria de equações publicadas, sem código copiado nem novas dependências:
Korn/Mason, *Configuration Aerodynamics* (2006), cap. 7,
https://archive.aoe.vt.edu/mason/Mason_f/ConfigAeroTransonics.pdf ;
Gur, Mason e Schetz (2010), *Full-Configuration Drag Estimation*,
*Journal of Aircraft* 47(4), 1356–1367, https://doi.org/10.2514/1.47557 ;
Mattingly, Heiser e Pratt (2002), *Aircraft Engine Design*, cap. 2;
Ihme (2025), ME257, eq. 2.77, https://ihmegroup.github.io/assets/pdf/ME257.pdf ;
Raymer (2018), tabelas 3.1/3.2 e caps. 12–14 (reutilização de `weights.py`).
14 CFR 25.335/.337: https://www.law.cornell.edu/cfr/text/14/25.335 e
https://www.law.cornell.edu/cfr/text/14/25.337 (paráfrases, não prova de conformidade).
Números públicos A320 e proveniência por campo: `examples/jet/a320_ref.json`
(consulta 2026-11-06; Airbus airport planning julho 2026 e resumo técnico Frawley/GCC Ports).
Não se redistribuem PDFs. pyCycle/OpenMDAO adiado para L2, não instalado nesta fatia.

Fecho de massa de jato (6 nov 2026): equação de massa e Breguet diferencial de
Raymer (2018), cap. 3, acoplados aos métodos L0 acima. Integração numérica própria
por Runge–Kutta clássico de ordem 4, duplicação de passos/Richardson e bissecção;
Hairer, Nørsett e Wanner (1993), *Solving Ordinary Differential Equations I*,
2.ª ed., cap. II. Sem código de terceiros copiado nem novas dependências.

## Triagem de performance de jatos L0 (7 nov 2026)

Implementação própria dos equilíbrios clássicos de força de corrida/subida,
sem código externo copiado nem dependências novas. ERAU, *Introduction to
Aerospace Flight Vehicles*, “Takeoff & Landing Performance”, eqs. 1–8 da análise
https://eaglepubs.erau.edu/introductiontoaerospaceflightvehicles/chapter/takeoff-landing-performance/
e “Climbing, Ceiling & Gliding”, eqs. 3–4 do equilíbrio estacionário
https://eaglepubs.erau.edu/introductiontoaerospaceflightvehicles/chapter/climbing-ceiling-gliding/ ;
Raymer §17.8, transcrição pública de corrida (eqs. 17.102–104):
https://computationaldesignlab.github.io/aircraft-design/performance/takeoff.html .
Valores de referência de 14 CFR 25.121(a)–(d) e limites do âmbito consultados em
https://www.law.cornell.edu/cfr/text/14/25.121 ,
https://www.law.cornell.edu/cfr/text/14/25.111 ,
https://www.law.cornell.edu/cfr/text/14/25.113 e
https://www.law.cornell.edu/cfr/text/14/25.115 .
Consulta 2026-11-07. Tabelas para comparação numérica, não demonstração regulamentar.
Arrasto/rating/velocidades do exemplo são PRESSUPOSTOS, não dados publicados de aeronave.


## Common energy-storage layer L0 (2026-11-07)

Own mass/density/volume and energy/mass/volume bookkeeping implementation; no third-party
code copied and no new dependency. Unit factors verified against NIST SP 811 (2008),
Appendix B.8: litre = 1e-3 m³; watt-hour = 3600 J:
https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b8 .
Hepperle, M. (2012), *Electric Flight — Potential and Limitations*, NATO STO-MP-AVT-209,
Sec. 3.2, energy-chain/battery-system context, PDF opened and read:
https://elib.dlr.de/78726/1/MP-AVT-209-09.pdf . Consulted 2026-11-07.
Reserve and DoD in the new storage layer are explicit user bookkeeping conventions,
NOT claimed to be regulatory rules or equations from that paper (its numerical
studies explicitly exclude operational reserves). No new published aircraft, tank
or pack reference data claimed; example properties are marked PRESSUPOSTO.
Existing jet/VTOL/mission consumption equations and citations are reused unchanged.


## Transport partial component weights (2026-11-07)

Own implementation of three classical Raymer cargo/transport equations: wing,
horizontal tail and vertical tail. *Aircraft Design: A Conceptual Approach*,
5th ed. (2012), Sec. 15.3.2; algebra/imperial units verified against the public functions
`mass_wing`, `mass_hstab`, `mass_vstab` in AeroSandbox documentation (4.2.6):
https://aerosandbox.readthedocs.io/en/master/_modules/aerosandbox/library/weights/raymer_cargo_transport_weights.html .
Independent wing/root t/c, quarter-chord sweep and horizontal-tail definitions:
*Chapter 15 Weight and Balance*, slides 46 and 54, dated 2022-11-23,
https://www.adac.aero/_files/ugd/c40aeb_ceb381b4d854417fa39876cbc1db0bf4.pdf .
Raymer's author provenance/limits (historical aluminium aircraft, not automatic
composite/unconventional applicability):
https://aircraftdesign.com/weights-methods-sources-for-aircraft-design-a-conceptual-approach/ .
All consulted 2026-11-07. No third-party code copied, package installed/imported,
or source PDF redistributed. Source links are mathematical-method references only.
Wing uses ROOT t/c explicitly (lecture definition), not a minimum-airfoil heuristic.
Fuselage/gear correlations deferred: definitions/units in the consulted sources
were not sufficiently unambiguous for this implementation. Remaining group masses
must be supplied or explicitly excluded with provenance; no arbitrary residual,
GA substitution or OEW fitting. Example new masses/geometry/load/radii are
PRESSUPOSTO, not published aircraft data. Hand-check tests verify the published
equations and SI conversion, not prediction accuracy against an actual transport.

Edition/year verified in the AIAA bibliographic entry (Google Books), consulted 2026-11-07:
https://books.google.com/books?id=9jBsLgEACAAJ .


## Shared onboard coupling (2026-11-07)

Own all-rights-reserved implementation; no copied third-party code/new dependency.
Reuses existing `systems.avionics.PowerBudget` duty-average/simultaneous-peak bookkeeping
(MIL-E-7016F and Moir & Seabridge, Aircraft Systems, 3rd ed., Ch. 5, as cited in that module),
and native Raymer 2018 Ch. 3 Breguet / Hepperle 2012 battery methods cited above.
The extra prop term is the analytic linear-ODE solution of `dm/dt=-a*m-b` with **supplied**
constant accessory flow b; jet uses its existing distance integrator plus b. BSFC/generator
eta and incremental jet fuel/thrust penalties are user inputs, **not** new published engine
correlations or inferred coefficients. The examples label every new value PRESSUPOSTO.

Unit identities `Wh=J/3600`, `kWh=3.6e6 J` and `kg/kWh * W / 3.6e6 = kg/s` use NIST SP811
Appendix B.8, https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b8
(opened and verified 2026-11-07). No regulatory requirement or compliance claim added.

## Methods — N0/N1 mission–fleet feedback (7 November 2026)

Own orchestration reuses Ha (2010) cyclic coverage, Blanchard & Fabrycky / MIL-HDBK-338B
availability, O'Connor & Kleyner reliability and Deb (2001) Pareto implementations listed
above; no copied source or new dependency. The new bridge retains flown handoff overlap
in the full flight+ground cycle: number of replacement intervals (station minus overlap)
must cover that cycle (direct timeline identity, explicit PRESSUPOSTO schedule, not a new
empirical coefficient). Native pointmass/jet/VTOL consumption and onboard accounting retain
their existing method citations and phase limitations.

Charging uses energy conservation `time[h]=terminal_Wh/(eta*allocated_average_input_W)`;
`grid_Wh=terminal_Wh/eta`. Pack C-rating checks use `P[W]=C[1/h]*E_nominal[Wh]`, the same
explicit pack-level convention as native VTOL; not a cell-to-pack assumption or thermal
verification. SI/Wh identities: NIST SP811 (2008), Appendix B.8,
https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b8
(previously verified for the common storage/onboard layer). All new example operational,
charging and rating values are PRESSUPOSTO supplied assumptions, not aircraft reference data.

## Methods — derived endurance and capability closure (9 November 2026)

Own all-rights-reserved code, no new dependency. Derived maximum station time: bracketing by
doubling plus bisection, R. L. Burden & J. D. Faires, *Numerical Analysis*, 9th ed.,
Brooks/Cole, 2011, Sec. 2.1 (The Bisection Method); largest verified feasible value kept.
Sizing↔capability closure is an upward fixed-point correction on the design station time
with explicit residual history, not a new physical model. Forward models reused unchanged:
existing pointmass (Anderson/Raymer), jet differential Breguet (`fixed_design_burn` repeats
the `size_jet` terms at fixed MTOW; regression test reproduces trip burn), VTOL segments
(Hepperle 2012). Held prop allowances are the native ones already cited (Raymer 2018 Table 3.2
fractions; `performance.takeoff_climb_energy`). Operational reserve values in examples are
PRESSUPOSTO, not regulatory reserves.

## Methods — shared ground resources (schema 1.2, 9 November 2026)

Own all-rights-reserved code, no new dependency. Deterministic next-event time-advance
discrete-event simulation: A. M. Law, *Simulation Modeling and Analysis*, 5th ed., McGraw-Hill,
2015, Ch. 1–2. Utilisation/stability of multi-server queues: L. Kleinrock, *Queueing Systems,
Volume 1: Theory*, Wiley, 1975. Little's law L = λW (fleet lower bound): J. D. C. Little,
"A Proof for the Queuing Formula: L = λW", *Operations Research* 9(3):383–387, 1961. No queueing
library or data imported; resource counts, powers and durations in examples are PRESSUPOSTO.
Mixed fleets: exhaustive bounded enumeration plus Pareto dominance (K. Deb, *Multi-Objective
Optimization using Evolutionary Algorithms*, Wiley, 2001, Ch. 2), existing `tradeoff.compare`.

## Methods — L0 hybrid dispatch and common phases (schema 1.2, 9 November 2026)

Own all-rights-reserved code. Rule-based (heuristic) supervisory control: L. Guzzella &
A. Sciarretta, *Vehicle Propulsion Systems*, 3rd ed., Springer, 2013, Ch. 8 "Supervisory Control
Algorithms", pp. 243–276. Hybrid-electric architecture vocabulary / degree of hybridisation:
C. Pornet & A. T. Isikveren, "Conceptual design of hybrid-electric transport aircraft", *Progress in
Aerospace Sciences* 79:114–135, 2015, doi:10.1016/j.paerosci.2015.09.002. Level power: Raymer 2018
§17.2; climb/descent power from rate of climb: J. D. Anderson, *Aircraft Performance and Design*,
McGraw-Hill, 1999, §5.10. Phase coverage reuses the already cited Raymer 2018 Table 3.2 fractions.
All component values (BSFC, efficiencies, SOC limits, powers) in examples are PRESSUPOSTO.

## Extended Raymer transport components + pressurization (9 November 2026)

Own all-rights-reserved scalar implementation. Additional cargo/transport equations from
Raymer, *Aircraft Design: A Conceptual Approach*, 5th ed., Sec. 15.3.2, transcribed against:

* ADAC *Chapter 15 Weight and Balance* (2022-11-23) slides 56–57 (fuselage fineness L/D =
  structural length/depth; main-gear landing weight Wl): 
  https://www.adac.aero/_files/ugd/c40aeb_ceb381b4d854417fa39876cbc1db0bf4.pdf
* SUAVE Raymer fuselage / landing_gear (2nd ed.; Vstall in knots):
  https://raw.githubusercontent.com/suavecode/SUAVE/master/trunk/SUAVE/Methods/Weights/Correlations/Raymer/fuselage.py
* AeroSandbox `raymer_cargo_transport_weights` (nacelles, systems, APU, fuel, AC, …) and
  GA `W_press = 11.9 (Vp_ft³·ΔP_psi)^0.271` lb (Sec. 15.3.3) for the optional shell increment.

No AeroSandbox/SUAVE code imported. Engines_dry remains supplied (no Sec.15.3.2 thrust→mass).
Bleed/electrical extraction is user-supplied auxiliary only; never an invented pack map.
Example inputs are PRESSUPOSTO, not published aircraft data.

## L0 jet field takeoff screening (9 November 2026)

Own all-rights-reserved code. Accelerate-stop / accelerate-go / balanced-field
construction: Krenkel & Salzman, *Journal of Aircraft* 5(5):429, 1968; Roskam,
*Airplane Design* Part I; Torenbeek, *Synthesis of Subsonic Airplane Design*
(screening BFL). Ground/climb force balances reuse the ERAU public textbook
relations already cited for `jet.performance`. 14 CFR 25.109 / 25.113 are
numerical screening references only — compliance always unassessed. Example
μ_brake, delays and drag increments are PRESSUPOSTO, not AFM data.



## Onboard thermal / CG / spatial / FOV closure (2026-11-09)

Own all-rights-reserved L0 screens in `core/onboard_closure.py`; no new dependency.
Thermal rejection uses the open-system cooling-air identity `Q = ṁ·cp·ΔT`
(Incropera & DeWitt, *Fundamentals of Heat and Mass Transfer*; screening only, not an
ECS pack map). Conversion heat reuses the same delivery/generator efficiencies already
cited for MIL-E-7016F / Moir & Seabridge PowerBudget accounting. CG is Σm·r (Meriam &
Kraige / Raymer mass properties, same as `assembly.integration`). Spatial fit uses AABB
containment/overlap. FOV sampling reuses the az/el grid and optional Fibonacci cone
(González 2010) already cited in `assembly.integration`; blockers are ray–AABB slab /
ray–sphere tests (no mesh). Examples label every new value PRESSUPOSTO.


## Lightweight engine / motor maps (2026-11-09)

Own all-rights-reserved interpolation in `jet/engine_map.py` and `core/motor_map.py`.
No pyCycle, NPSS, GasTurb, T-MATS, OpenMDAO cycle, or CFD dependency.

* Default thrust/TSFC: Mattingly, Heiser & Pratt (2002) Ch. 2 high-bypass lapse and
  Ihme (2025) Eq. 2.77, as already cited for `turbofan_point`.
* Corrected-parameter recovery F=(F/δ)·δ, SFC=(SFC/√θ)·√θ: Walsh & Fletcher,
  *Gas Turbine Performance* (corrected-parameter map forms); δ,θ from ISA static or
  isentropic freestream totals when `totals: true`.
* Table interpolation: multilinear on a supplied regular grid (Press et al.,
  *Numerical Recipes* — classical multilinear interp). Out-of-domain queries are
  unassessed unless the user opts into flagged extrapolation.
* Electric motor η(P[,rpm]) tables: energy identity P_elec=P_shaft/η; efficiencies are
  user inputs. Examples label every new numeric value PRESSUPOSTO.


## Common jet/VTOL mission judge (2026-11-09)

Own orchestration in `flightsim/common_mission.py`. Reuses Anderson 1999 Ch. 3/5 and
Raymer 2018 Ch. 17 pointmass already cited for `simulate_pointmass_mission`, plus
Mattingly/Ihme / Walsh & Fletcher engine maps for jet thrust/TSFC, and existing VTOL
L0 segment powers (Leishman momentum / size_vtol citations). No new dependency; no
pyCycle, NPSS, CFD or JSBSim deck generation.

### Configuration shortcuts (V / inverted_V / twin_boom) and dihedral → spiral (9 Nov 2026)

Own orchestration in `assembly/shortcuts.py`. V-panel area from Purser & Campbell, NACA
Rep. 823 projections (S·cos²Γ / S·sin²Γ) already cited for assembly sizing, with Raymer 2018
Eqs. 6.28–6.29 volume targets. Spiral / lateral modes reuse Nelson 1998 Ch. 5 and Etkin & Reid
1996 Ch. 6 via existing AVL Clβ (geometric dihedral on the wing). No new dependency.
