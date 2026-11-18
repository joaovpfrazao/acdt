"""Phase 4 (L3): unit checks of the closed-form pieces and an offline orchestration test (no solver runs).

Solver-backed steps (OpenVSP, SU2, CalculiX) are exercised by ``acdt hifi`` (see docs/tutorial-fase4.md); here
the tests only need numpy, and pyNastran / kinparse when installed."""
import json
import math
import os
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from acdt.domains.aircraft.hifi import calibration, tools
from acdt.domains.aircraft.hifi.cfd import _last_history, first_cell, gci, naca_coords
from acdt.domains.aircraft.hifi.flutter import flutter_margin_check
from acdt.domains.aircraft import detailed_sizing as ds
from acdt.domains.aircraft import weights_detailed as wd


def test_su2_history_header_with_padded_quotes(tmp_path):
    # SU2 8.5 on Windows writes spaces inside the header quotes and can stop before 200 rows
    text = (
        '"Time_Iter","Outer_Iter",    "rms[Rho]"    ,       "CD"       ,       "CL"       ,       "CMz"      \n'
        "0,0,-2.0,0.020,0.10,-0.05\n"
        "1,1,-6.0,0.012,0.50,-0.06\n"
    )
    path = tmp_path / "history.csv"
    path.write_text(text)
    d = _last_history(path)
    assert d["CL"] == pytest.approx(0.50)
    assert d["CD"] == pytest.approx(0.012)
    assert d["CMz"] == pytest.approx(-0.06)
    assert d["rms[Rho]"] == pytest.approx(-6.0)
    assert d["CL_unsteady"] == pytest.approx(0.2)


def test_windows_available_memory_matches_the_os():
    gb = tools.mem_available_gb()
    assert 0.5 < gb < 4096
    if os.name != "nt":
        return
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(stat)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    assert gb == pytest.approx(stat.ullAvailPhys / 1024**3, rel=0.05)


def test_time_limit_can_be_raised_without_dropping_the_memory_guard():
    # 100 min is over the default 45 min cap and under a 7 h authorization. A huge estimate still refuses.
    short = tools.budget(0.01, 100.0, max_time_min=45.0)
    assert short.run_here is False and "45" in short.reason
    long = tools.budget(0.01, 100.0, max_time_min=420.0)
    assert long.run_here is True
    huge = tools.budget(1.0e6, 1.0, max_time_min=420.0)
    assert huge.run_here is False and "memória" in huge.reason


def test_gci_recovers_order_and_extrapolated_value():
    # f = f_ext + C h^p with p = 2, r = sqrt(2) (Celik et al. 2008 procedure must return p and f_ext exactly)
    f_ext, C, p = 0.010, 0.3, 2.0
    h = [1.0, math.sqrt(2), 2.0]
    f = [f_ext + C * x**p * 1e-3 for x in h]
    g = gci(*f, *h)
    assert g["p"] == pytest.approx(2.0, rel=1e-6)
    assert g["f_ext"] == pytest.approx(f_ext, rel=1e-9)
    assert not g["oscillatory"]
    # GCI_fine = Fs |e21| / (r^p - 1), Fs = 1.25
    e21 = abs((f[0] - f[1]) / f[0])
    assert g["gci_fine"] == pytest.approx(1.25 * e21 / (2.0 - 1.0), rel=1e-6)


def test_naca_coords_thickness_and_closure():
    xy = naca_coords("NACA 2412", 161)
    assert xy[:, 0].min() == pytest.approx(0.0, abs=1e-3) and xy[:, 0].max() == pytest.approx(1.0, abs=1e-3)
    x = np.linspace(0.05, 0.95, 50)
    up = xy[: len(xy) // 2 + 1]
    lo = xy[len(xy) // 2:]
    yu = np.interp(x, up[::-1, 0], up[::-1, 1]) if up[0, 0] > up[-1, 0] else np.interp(x, up[:, 0], up[:, 1])
    yl = np.interp(x, lo[:, 0], lo[:, 1]) if lo[0, 0] < lo[-1, 0] else np.interp(x, lo[::-1, 0], lo[::-1, 1])
    assert (yu - yl).max() == pytest.approx(0.12, abs=0.005)


def test_first_cell_yplus_scaling():
    # flat-plate estimate: Δy ∝ y+, decreasing with Re
    assert first_cell(1e6, 1.0, 2.0) == pytest.approx(2 * first_cell(1e6, 1.0, 1.0), rel=1e-9)
    assert first_cell(5e6) < first_cell(1e6)


def test_flutter_margin_check():
    assert flutter_margin_check(130.0, 125.0, 100.0)["ok"]
    m = flutter_margin_check(110.0, 105.0, 100.0)
    assert not m["ok"] and m["V_required"] == pytest.approx(120.0)
    assert flutter_margin_check(math.inf, math.inf, 100.0)["ok"]


def test_calibration_load_opt_in_and_groups(tmp_path):
    cal = {"factors": {"k_clmax": {"group": "aero", "value": 1.07, "hifi": 1.8, "lowfi": 1.7, "what": "x"},
                       "k_flutter": {"group": "flutter", "value": 1.4, "hifi": 160, "lowfi": 113, "what": "y"},
                       "k_EI": {"group": "structures", "value": 1.1, "hifi": 0.25, "lowfi": 0.27, "what": "z"}}}
    f = calibration.write(cal, tmp_path / "c.json")
    assert calibration.load({"calibration": {"file": str(f), "apply": []}}) == {}
    a = calibration.load({"calibration": {"file": str(f), "apply": ["aero"]}})
    assert a == {"k_clmax": 1.07}
    b = calibration.load({"calibration": {"file": str(f), "apply": ["aero", "flutter", "structures"]}})
    assert set(b) == {"k_clmax", "k_flutter", "k_EI"}   # structures applies k_EI and k_GJ only
    c = calibration.load({"calibration": {"apply": ["aero"], "factors": {"k_cd_profile": 1.3}}})
    assert c == {"k_cd_profile": 1.3}
    md = "\n".join(calibration.table_md(cal, b))
    assert "`k_EI`" in md and md.count("| sim |") == 3


def test_calibration_rejects_negative_and_absurd_ratios(tmp_path):
    # The Windows PaStiX static solve produced these factors. They must not be applied.
    fem = {"tip_w_fem_m": -8.8e-7, "tip_w_beam_m": 0.11, "tip_twist_fem_deg": 0.16,
           "tip_twist_beam_deg": -0.20,
           "cover_bay": {"bay": 0, "y": 0.2, "cap_fem_MPa": -3.95, "skin_fem_MPa": 1.0, "cap_allow_MPa": 500.0},
           "buckling_factors_ultimate": [9.65]}
    cal = calibration.build("uav_endurance_payload", fem=fem)
    assert cal["factors"]["k_EI"]["valid"] is False
    assert cal["factors"]["k_EI"]["value"] < 0
    assert cal["factors"]["k_GJ"]["valid"] is False          # negative twist ratio
    assert cal["factors"]["k_sigma_cap"]["value"] == pytest.approx(3.95 / 500)
    assert cal["factors"]["k_sigma_cap"]["valid"] is False   # ~0.008, below the band
    assert cal["factors"]["lambda_buckling"]["valid"] is False
    cal["factors"]["k_flutter"] = {"group": "flutter", "value": -1.2, "hifi": 1, "lowfi": 1, "what": "x",
                                   "valid": False}
    cal["factors"]["k_cd_profile"] = {"group": "aero", "value": 100.0, "hifi": 1, "lowfi": 0.01, "what": "x"}
    f = calibration.write(cal, tmp_path / "calibration.json")
    got = calibration.load({"calibration": {"file": str(f), "apply": ["aero", "flutter", "structures"]}})
    assert got == {}


def test_section_axis_torque_transfers_to_the_midbox():
    """Lift ahead of the section shear centre and behind c/4: the mid-box arm is the one the rectangle carries."""
    from acdt.domains.aircraft.hifi.fem import meshed_box_gj, torque_about_meshed_box
    from acdt.domains.aircraft.structures import _cum_from_tip

    y = np.linspace(0.0, 2.0, 9)
    lift = np.full_like(y, 1000.0)
    chord = np.ones_like(y)
    xsc = np.full_like(y, 0.30)
    # T_section(0) = 1000 * (0.30 − 0.25) * 1 * 2 = 100 N·m
    T = _cum_from_tip(y, lift * (xsc - 0.25) * chord)
    res = SimpleNamespace(
        config=SimpleNamespace(wing=SimpleNamespace(
            box=SimpleNamespace(front_spar_xc=0.20, rear_spar_xc=0.65))),
        structures=SimpleNamespace(
            load=SimpleNamespace(y=y, lift=lift, chord=chord),
            beam=SimpleNamespace(torque=T),
            box=SimpleNamespace(y=y, GJ=np.array([10.0, 8.0]), details={"x_sc_c": xsc, "GJ_phase3": np.array([4.0, 3.0])}),
        ),
    )
    # x_mid = 0.425; T_mid(0) = 1000 * (0.425 − 0.25) * 2 = 350 N·m
    assert float(torque_about_meshed_box(res, 0.0)) == pytest.approx(350.0)
    assert float(torque_about_meshed_box(res, 2.0)) == pytest.approx(0.0, abs=1e-9)
    assert meshed_box_gj(res.structures.box)[0] == pytest.approx(4.0)
    res.structures.box.details = {}
    assert float(torque_about_meshed_box(res, 0.0)) == pytest.approx(100.0)
    assert meshed_box_gj(res.structures.box)[0] == pytest.approx(10.0)


def _constant_rectangle(L, w, h, t, n_span, n_chord, n_height, E, nu, rho):
    """Prismatic S8R tube, same node order as ``fem.build_box_mesh`` (no ribs, no stringers)."""
    from acdt.domains.aircraft.hifi.fem import BoxMesh

    ny, nx, nz = 2 * n_span + 1, 2 * n_chord + 1, 2 * n_height + 1
    ys = np.linspace(0.0, L, ny)
    xs = np.linspace(0.0, w, nx)
    zs = np.linspace(-h / 2, h / 2, nz)
    key, coords = {}, []

    def node(p):
        k = (round(p[0], 7), round(p[1], 7), round(p[2], 7))
        if k not in key:
            key[k] = len(coords)
            coords.append(p)
        return key[k]

    up = np.array([[node((x, y, h / 2)) for x in xs] for y in ys])
    lo = np.array([[node((x, y, -h / 2)) for x in xs] for y in ys])
    wf = np.array([[node((0.0, y, z)) for z in zs] for y in ys])
    wr = np.array([[node((w, y, z)) for z in zs] for y in ys])

    def quads(G, flip=False):
        out = []
        for a in range(0, G.shape[0] - 1, 2):
            for b in range(0, G.shape[1] - 1, 2):
                n1, n2, n3, n4 = int(G[a, b]), int(G[a, b + 2]), int(G[a + 2, b + 2]), int(G[a + 2, b])
                m5, m6, m7, m8 = int(G[a, b + 1]), int(G[a + 1, b + 2]), int(G[a + 2, b + 1]), int(G[a + 1, b])
                e = [n1, n2, n3, n4, m5, m6, m7, m8]
                if flip:
                    e = [n1, n4, n3, n2, m8, m7, m6, m5]
                out.append(e)
        return out

    shells = {"UP": quads(up), "LO": quads(lo, flip=True), "WF": quads(wf, flip=True), "WR": quads(wr)}
    sprops = {k: {"t": t} for k in shells}
    root = sorted(set(up[0].tolist() + lo[0].tolist() + wf[0].tolist() + wr[0].tolist()))
    spar = {"f_up": up[:, 0].tolist(), "f_lo": lo[:, 0].tolist(), "r_up": up[:, -1].tolist(), "r_lo": lo[:, -1].tolist()}
    meta = {"material": {"name": "al", "E": E, "nu": nu, "rho": rho}, "composite": False}
    return BoxMesh(np.array(coords), shells, {}, sprops, {}, root, spar, ys, np.zeros(ny), np.full(ny, w),
                   np.full(ny, h), [0, ny - 1], meta)


def test_rectangular_box_torsion_matches_bredt(tmp_path):
    """Closed rectangular tube versus Bredt–Batho (Megson Eq. 18.4): θ' = T / (G J), J = 4 A² / ∮ ds/t.

    The tip load is the analytical shear flow q = T / (2 A), tangential. A spar couple on this tube with no
    diaphragm distorts the profile (plate bending of the covers) and is not the Bredt rate; the wing box has
    ribs, so that path is a different check. Same S8R deck writer. Nose-up is front uz − rear uz, as on the wing.
    The rate is taken mid-span, clear of the clamped root and of the tip load."""
    from acdt.domains.aircraft.hifi.fem import parse_dat_blocks, write_deck
    from acdt.domains.aircraft.hifi.tools import find_exe, run

    if find_exe("ccx") is None:
        pytest.skip("CalculiX ccx not on ACDT_HIFI_BIN or PATH")
    L, w, h, t, T = 2.0, 0.4, 0.1, 0.002, 1000.0
    E, nu = 70e9, 0.3
    mesh = _constant_rectangle(L, w, h, t, n_span=8, n_chord=2, n_height=2, E=E, nu=nu, rho=2700.0)
    X = mesh.nodes
    tip = [i for i, p in enumerate(X) if abs(p[1] - L) < 1e-9]
    top = sorted([i for i in tip if abs(X[i, 2] - h / 2) < 1e-9], key=lambda i: X[i, 0])
    bot = sorted([i for i in tip if abs(X[i, 2] + h / 2) < 1e-9], key=lambda i: -X[i, 0])
    rear = sorted([i for i in tip if abs(X[i, 0] - w) < 1e-9 and abs(abs(X[i, 2]) - h / 2) > 1e-9],
                  key=lambda i: -X[i, 2])
    front = sorted([i for i in tip if abs(X[i, 0]) < 1e-9 and abs(abs(X[i, 2]) - h / 2) > 1e-9],
                   key=lambda i: X[i, 2])
    per = top + rear + bot + front
    q = T / (2 * w * h)
    fx = {i: 0.0 for i in per}
    fz = {i: 0.0 for i in per}
    for a, b in zip(per, per[1:] + per[:1]):
        f = q * (X[b] - X[a])
        fx[a] += 0.5 * f[0]
        fz[a] += 0.5 * f[2]
        fx[b] += 0.5 * f[0]
        fz[b] += 0.5 * f[2]
    write_deck(mesh, tmp_path / "box_static.inp", "static", {i: 0.0 for i in per})
    cloads = "".join(f"{i + 1}, 1, {fx[i]:.6e}\n{i + 1}, 3, {fz[i]:.6e}\n" for i in per)
    inp = (tmp_path / "box_static.inp").read_text()
    inp = inp[:inp.index("*CLOAD\n")] + "*CLOAD\n" + cloads + inp[inp.index("*NODE PRINT"):]
    (tmp_path / "box_static.inp").write_text(inp)
    rc = run([find_exe("ccx"), "box_static"], tmp_path, "box_static.log", timeout=120)
    assert rc == 0, (tmp_path / "box_static.log").read_text(errors="replace")[-500:]
    U = {}
    for head, rows in parse_dat_blocks(tmp_path / "box_static.dat"):
        if head.startswith("displacements"):
            for row in rows:
                U[int(row[0]) - 1] = row[1:4]

    def theta(j):
        fu, ru = mesh.spar_lines["f_up"][j], mesh.spar_lines["r_up"][j]
        return math.atan2(U[fu][2] - U[ru][2], mesh.x_r[j] - mesh.x_f[j])

    j1, j2 = 6, 12
    rate = (theta(j2) - theta(j1)) / (mesh.y[j2] - mesh.y[j1])
    G = E / (2 * (1 + nu))
    J = 4 * (w * h) ** 2 / (2 * w / t + 2 * h / t)
    assert rate > 0.0
    assert rate == pytest.approx(T / (G * J), rel=0.03)


def test_nlgeom_step_is_not_a_riks_card(tmp_path):
    """CalculiX 2.23 geometric nonlinearity is *STEP, NLGEOM. Riks is not written."""
    from acdt.domains.aircraft.hifi.fem import _tip_deflection, write_deck
    from acdt.domains.aircraft.hifi.tools import find_exe, run

    L, w, h, t = 2.0, 0.4, 0.1, 0.002
    mesh = _constant_rectangle(L, w, h, t, n_span=4, n_chord=2, n_height=2, E=70e9, nu=0.3, rho=2700.0)
    jt = len(mesh.y) - 1
    loads = {mesh.spar_lines["f_up"][jt]: -20.0, mesh.spar_lines["r_up"][jt]: -20.0}
    write_deck(mesh, tmp_path / "box_nlgeom.inp", "nlgeom", loads)
    text = (tmp_path / "box_nlgeom.inp").read_text(encoding="utf-8")
    assert "*STEP, NLGEOM\n" in text
    assert "*STATIC, SOLVER=SPOOLES\n0.2, 1.\n" in text
    assert "RIKS" not in text.upper()
    with pytest.raises(ValueError):
        write_deck(mesh, tmp_path / "nope.inp", "riks", loads)
    if find_exe("ccx") is None:
        pytest.skip("CalculiX ccx not on ACDT_HIFI_BIN or PATH")
    rc = run([find_exe("ccx"), "box_nlgeom"], tmp_path, "box_nlgeom.log", timeout=180)
    assert rc == 0, (tmp_path / "box_nlgeom.log").read_text(errors="replace")[-500:]
    tip = _tip_deflection(mesh, tmp_path / "box_nlgeom.dat")
    assert tip is not None and math.isfinite(tip[0]) and tip[0] < 0.0


def test_shift_echo_is_scaled_back_to_the_ultimate_load():
    """A cluster about σ = 1 is not the lowest factor. Scaling the load must recover it."""
    from acdt.domains.aircraft.hifi.fem import reliable_buckling_factors

    def solve(scale):
        true = 0.05 * scale
        if true < 0.5:
            return 0, [0.933, 0.950, 0.999, 1.020]
        return 0, [true, true * 1.57, true * 2.82, true * 4.07]

    out = reliable_buckling_factors(solve)
    assert out["scale"] > 1.0
    assert out["factors"][0] == pytest.approx(0.05, rel=1e-6)
    assert out["raw"][0] >= 0.5


def _square_plate_deck(scale: float, nx: int = 16) -> str:
    """Simply-supported square plate, S4, compression N = (Ncr / 0.05) / scale.

    Ncr = 4 π² D / a², k = 4 (Timoshenko and Gere, *Theory of Elastic Stability*).
    At scale 1 the true factor is 0.05, below the CalculiX shift.
    """
    a, t, E, nu = 0.5, 0.01, 70e9, 0.3
    D = E * t**3 / 12 / (1 - nu**2)
    ncr = 4 * math.pi**2 * D / a**2
    load = (ncr / 0.05) / scale
    n = nx

    def nid(i, j):
        return j * (n + 1) + i + 1

    lines = [
        "** Windows CalculiX 2.23, SPOOLES. Square plate a=0.5 m, t=0.01 m, S4.",
        "** Timoshenko and Gere, k=4: Ncr = 4 pi^2 D / a^2. Reference N = (Ncr/0.05)/scale.",
        f"** scale = {scale:.8g}. Factors in the .dat are on this reference load, not yet divided by scale.",
        "*NODE",
    ]
    for j in range(n + 1):
        for i in range(n + 1):
            lines.append(f"{nid(i, j)}, {a * i / n:.6f}, {a * j / n:.6f}, 0.")
    lines.append("*ELEMENT, TYPE=S4, ELSET=P")
    e = 1
    for j in range(n):
        for i in range(n):
            lines.append(f"{e}, {nid(i, j)}, {nid(i + 1, j)}, {nid(i + 1, j + 1)}, {nid(i, j + 1)}")
            e += 1
    lines += ["*MATERIAL, NAME=M", "*ELASTIC", f"{E:.6e}, {nu}", "*SHELL SECTION, ELSET=P, MATERIAL=M", f"{t}", "*BOUNDARY"]
    edge = [nid(i, 0) for i in range(n + 1)] + [nid(i, n) for i in range(n + 1)]
    edge += [nid(0, j) for j in range(1, n)] + [nid(n, j) for j in range(1, n)]
    for k in sorted(set(edge)):
        lines.append(f"{k}, 3, 3")
    lines.append(f"{nid(0, 0)}, 1, 2")
    lines.append(f"{nid(0, n)}, 1, 1")
    lines += ["*STEP", "*BUCKLE, SOLVER=SPOOLES", "4, 1e-3", "*CLOAD"]
    for j in range(n + 1):
        w = 0.5 if j in (0, n) else 1.0
        f = load * (a / n) * w
        lines.append(f"{nid(0, j)}, 1, {f:.6e}")
        lines.append(f"{nid(n, j)}, 1, {-f:.6e}")
    lines += ["*NODE FILE", "U", "*END STEP", ""]
    return "\n".join(lines)


def test_square_plate_buckling_matches_timoshenko_k4(tmp_path):
    """The Windows *BUCKLE cluster at λ ≈ 1 is the shift. The scaled factor is k = 4.

    The unscaled deck (true factor 0.05) and the deck that leaves the shift are stored under
    tests/data/ccx_buckle_win so the same .inp can be run on Linux. A previous *STATIC step is
    not written: the User's Manual drops it, and on an Euler column it did not change λ.
    """
    from acdt.domains.aircraft.hifi.fem import parse_buckling_factors, reliable_buckling_factors
    from acdt.domains.aircraft.hifi.tools import find_exe, run

    ccx = find_exe("ccx")
    if ccx is None:
        pytest.skip("CalculiX ccx not on ACDT_HIFI_BIN or PATH")
    # Production *BUCKLE sets OMP_NUM_THREADS=1. SPOOLES with several threads can return a factor
    # that is neither the shift cluster nor Timoshenko's k=4 (seen: 0.030 against 0.050).
    one = {"OMP_NUM_THREADS": "1"}
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "plate.inp").write_text(_square_plate_deck(1.0))
    rc = run([ccx, "plate"], raw_dir, "plate.log", timeout=120, env=one)
    assert rc == 0, (raw_dir / "plate.log").read_text(errors="replace")[-400:]
    raw = parse_buckling_factors(raw_dir / "plate.dat")
    assert len(raw) == 4
    assert min(raw) > 0.8 and max(raw) < 1.25

    def solve(scale, _ccx=ccx):
        d = tmp_path / f"s{scale:.6g}"
        d.mkdir(exist_ok=True)
        (d / "plate.inp").write_text(_square_plate_deck(scale))
        rc_s = run([_ccx, "plate"], d, "plate.log", timeout=120, env=one)
        fac = parse_buckling_factors(d / "plate.dat") if (d / "plate.dat").exists() else []
        solve.last = d
        return rc_s, fac

    solve.last = raw_dir
    out = reliable_buckling_factors(solve)
    assert out["rc"] == 0
    assert out["scale"] > 1.0
    assert out["factors"][0] == pytest.approx(0.05, rel=0.02)
    # The Windows decks in tests/data/ccx_buckle_win are a snapshot of this run (shift echo, then the
    # scaled load). They are not rewritten here, so a Linux run of the test does not replace them.


def test_calculix_static_tip_within_half_of_the_beam(tmp_path):
    """PaStiX on Windows collapsed the tip to ~1e-6 m. SPOOLES must stay within ±50 % of the beam, λ > 0.

    Tip twist uses the same sign and, within 25 %, the Phase 3 Bredt beam (mid-box torque / GJ_phase3).
    The old comparison (section shear centre, multi-cell GJ) gave k_GJ 0.22 on this UAV and a sign change
    on the C172."""
    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.hifi import fem
    from acdt.domains.aircraft.hifi.tools import find_exe

    if find_exe("ccx") is None:
        pytest.skip("CalculiX ccx not on ACDT_HIFI_BIN or PATH")
    res = run_pipeline("aircraft", "examples/uav_endurance_payload.yaml")["result"]
    out = fem.run_box_fem(res, tmp_path, steps=("static", "buckle"))
    beam, tip = out["tip_w_beam_m"], out["tip_w_fem_m"]
    assert beam > 0.0
    assert abs(tip - beam) / beam <= 0.50
    assert min(out["buckling_factors_ultimate"]) > 0.0
    assert out["loads"]["T0_fem_Nm"] == pytest.approx(out["loads"]["T0_phase3_Nm"], rel=0.02)
    assert out["tip_twist_beam_deg"] == pytest.approx(out["tip_twist_fem_deg"], rel=0.25)


def test_calibration_build_traces_sources():
    sec = {"k_clmax": 1.07, "clmax_rans": 1.82, "clmax_xfoil": 1.70, "k_cd_profile": 1.45, "cd05_rans": 0.0118,
           "cd05_xfoil": 0.0082, "d_cm0": -0.0056, "cm0_rans": -0.0565, "cm0_xfoil": -0.0509}
    fl = {"strip_V_F": 113.0, "margin": {"V_F_g003": 162.0}}
    c = calibration.build("t", sec, None, fl, sources={"cfd2d": "a"})
    assert c["factors"]["k_flutter"]["value"] == pytest.approx(162 / 113)
    assert c["factors"]["k_clmax"]["hifi"] == 1.82 and c["sources"]["cfd2d"] == "a"


def test_k_flutter_is_not_zero_when_the_strip_speed_does_not_cross():
    """Dividing a finite DLM speed by an infinite strip speed is 0 in IEEE arithmetic. That 0 is not a ratio."""
    fl = {"strip_V_F": math.inf, "margin": {"V_F_g003": 284.5870142213441}}
    c = calibration.build("uav150_flying_wing_tailless", None, None, fl)
    f = c["factors"]["k_flutter"]
    assert f["value"] is None and f["valid"] is False and f["lowfi"] is None
    assert f["hifi"] == pytest.approx(284.5870142213441)
    assert "not finite" in f["invalid_reason"]
    assert "k_flutter" not in calibration.load({"calibration": {"factors": {"k_flutter": f}, "apply": ["flutter"]}})
    line = calibration.table_md(c)[-1]
    assert "`k_flutter`" in line and "inválido" in line and "0.000" not in line


def test_k_cd_profile_from_turbulent_rans_is_reported_not_applied(tmp_path):
    """Fully turbulent RANS-SA over XFOIL (transition) is not the same cd. Keep the ratio; do not apply it."""
    sec = {"k_clmax": 1.06, "clmax_rans": 1.815, "clmax_xfoil": 1.713, "k_cd_profile": 1.426,
           "cd05_rans": 0.01190, "cd05_xfoil": 0.008344, "d_cm0": -0.007, "cm0_rans": -0.057,
           "cm0_xfoil": -0.050}
    gci_cd = {"cd": {"gci_fine": 0.08898430897866533, "f_ext": 0.010018291073403528, "iterative_ok": True}}
    cal = calibration.build("cessna172_check", sec, gci=gci_cd)
    f = cal["factors"]["k_cd_profile"]
    assert f["value"] == pytest.approx(1.426)
    assert f["gci_fine"] == 0.08898430897866533
    assert f["cd_extrapolated"] == 0.010018291073403528
    assert f["valid"] is False
    assert f["invalid_reason"] == calibration.K_CD_PROFILE_NOT_APPLIED
    assert "transition" in f["invalid_reason"]
    assert cal["factors"]["k_clmax"]["valid"] is True
    assert cal["factors"]["d_cm0"]["valid"] is True
    path = calibration.write(cal, tmp_path / "calibration.json")
    applied = calibration.load({"calibration": {"file": str(path), "apply": ["aero"]}})
    assert set(applied) == {"k_clmax", "d_cm0"}
    assert applied["k_clmax"] == pytest.approx(1.06)
    md = "\n".join(calibration.table_md(cal, applied))
    assert "`k_cd_profile`" in md
    row = next(line for line in md.splitlines() if "`k_cd_profile`" in line)
    assert row.endswith("| inválido |")


def test_stored_k_cd_profile_stays_reported_and_not_applied():
    root = Path(__file__).resolve().parents[1] / "examples" / "output"
    expected = {
        "cessna172_check_hifi_win": 1.4259881768874867,
        "cessna172_check_hifi": 1.445606406508509,
        "uav_endurance_payload_hifi": 1.4031083304196825,
    }
    for name, value in expected.items():
        cal = json.loads((root / name / "calibration.json").read_text(encoding="utf-8"))
        f = cal["factors"]["k_cd_profile"]
        assert f["value"] == value
        assert f["hifi"] > 0 and f["lowfi"] > 0
        assert f["valid"] is False
        assert f["invalid_reason"] == calibration.K_CD_PROFILE_NOT_APPLIED
        applied = calibration.load({"calibration": {"factors": cal["factors"], "apply": ["aero"]}})
        assert "k_cd_profile" not in applied
        assert "k_clmax" in applied
        md = (root / name / "report_fase4.md").read_text(encoding="utf-8")
        row = next(line for line in md.splitlines() if line.startswith("| `k_cd_profile`"))
        assert row.endswith("| inválido |")
        assert "k_cd_profile` é reportado e não é aplicado" in md


def test_euler_drag_stays_wind_axis_and_must_be_near_induced():
    """Negative C172 Euler CD is SU2's wind-axis pressure integral. Do not flip the sign.

    The same formula on the SU2 inviscid ONERA M6 tutorial (582752 tetras, M = 0.8395,
    α = 3.06°, SU2 8.5.0, residual −12 in 129 s) returns that run's CL 0.284858 and
    CD +0.011967. AoA 3.06° is a positive freestream w component (SU2: x aft, z up).
    A usable subsonic Euler CD is ≥ 0 and within 50 % of CL²/(π e AR).

    The C172 wing was exported with the apex at x = 0 and incidence 0 (NACA 2412).
    The STEP bounding box matches that spec (x 0–1.621 m, y ±5.04 m, chord plane z = 0.529 m).
    CL at 0° is 0.207 against the AVL wing 0.172: 0.42° of CLα. The slopes agree.
    """
    from acdt.domains.aircraft.hifi import cfd3d

    cl4, cd4 = cfd3d.wind_axis_coefficients(-0.071933347, 0.530257492, 4.0)
    assert cl4 == pytest.approx(0.533983628, abs=1e-6)
    assert cd4 == pytest.approx(-0.03476922816, abs=1e-6)
    cl0, cd0 = cfd3d.wind_axis_coefficients(-0.04900253094, 0.2067361289, 0.0)
    assert cl0 == pytest.approx(0.2067361289, abs=1e-9)
    assert cd0 == pytest.approx(-0.04900253094, abs=1e-9)
    # ONERA M6, last history row: CFx, CFz -> CL, CD. CD is positive.
    cl_m, cd_m = cfd3d.wind_axis_coefficients(-0.003255760445, 0.2850904703, 3.06)
    assert cl_m == pytest.approx(0.284857781, abs=1e-8)
    assert cd_m == pytest.approx(0.01196749272, abs=1e-8)
    assert cd_m > 0.0
    spec = json.loads((Path(__file__).resolve().parents[1] / "examples" / "output"
                       / "cessna172_check_hifi" / "geometry" / "cessna172_check_vsp_spec.json"
                       ).read_text(encoding="utf-8"))
    assert spec["wing"]["x"] == 0.0 and spec["wing"]["incidence_deg"] == 0.0
    assert spec["wing"]["airfoil"] == "2412"

    AR, e = 7.5, 0.80
    cl = 0.50
    cdi = cfd3d.induced_drag_coefficient(cl, AR, e)
    assert cdi == pytest.approx(cl ** 2 / (math.pi * e * AR))
    assert cfd3d.euler_drag_check(cl, cdi, AR, e)["ok"]
    assert cfd3d.euler_drag_check(cl, 1.1 * cdi, AR, e)["ok"]
    assert cfd3d.euler_drag_check(cl, 3.0 * cdi, AR, e)["ok"] is False
    assert cfd3d.euler_drag_check(cl, -0.01, AR, e)["ok"] is False

    stored = json.loads((Path(__file__).resolve().parents[1] / "examples" / "output"
                         / "cessna172_check_hifi_win" / "wing_euler" / "wing_euler.json").read_text(encoding="utf-8"))
    assert stored["CD"] == [-0.04900253094, -0.03476922816]
    assert stored["CL"][0] == pytest.approx(0.2067361289)
    shift = math.degrees(stored["dCL_at_alpha0"] / stored["CLa_euler"])
    assert shift == pytest.approx(0.42, abs=0.02)
    assert stored["k_CLa"] == pytest.approx(1.010, abs=0.005)
    for cl_s, cd_s in zip(stored["CL"], stored["CD"]):
        assert cfd3d.euler_drag_check(cl_s, cd_s, AR, e)["ok"] is False
    md = (Path(__file__).resolve().parents[1] / "examples" / "output" / "cessna172_check_hifi_win"
          / "report_fase4.md").read_text(encoding="utf-8")
    assert "Não se aplica como calibração" in md
    assert "S_ref = S/2" in md


def test_grid_convergence_default_stays_three_meshes():
    import inspect

    from acdt.domains.aircraft.hifi.cfd import grid_convergence

    refine = inspect.signature(grid_convergence).parameters["refine"].default
    coarse, mid, fine = (float(x) for x in refine)
    assert mid == pytest.approx(1.0)
    assert coarse == pytest.approx(1.0 / math.sqrt(2))
    assert fine == pytest.approx(math.sqrt(2))
    # The follow-up mesh (refine 2) is one more √2 in h, about twice the cells. Not the default.
    assert 2.0 / fine == pytest.approx(math.sqrt(2))
    assert (2.0 / fine) ** 2 == pytest.approx(2.0)


def test_rib_crushing_closed_form():
    # w = M² h t_e s E / (2 EI²): doubling M quadruples w; column-buckling t ∝ w^(1/3)
    M, h, te, s, E = 1.0e4, 0.15, 2e-3, 0.5, 72.4e9
    EI = E * 2 * (0.15 * 2e-3) * (h / 2) ** 2
    w1 = ds.rib_crushing_load(M, h, te, s, EI, E)
    assert ds.rib_crushing_load(2 * M, h, te, s, EI, E) == pytest.approx(4 * w1)
    I = EI / E
    assert w1 == pytest.approx((M * h / 2 / I * te) * (M / EI) * s)   # N κ s
    t = ds.rib_web_thickness(1e5, 0.2, E, 0.33, 269e6, 0.0)
    assert 1e5 / t <= math.pi**2 * E * t**2 / (12 * (1 - 0.33**2) * 0.2**2) * (1 + 1e-9)


def test_root_joint_bolts_and_bearing():
    sr = SimpleNamespace(beam=SimpleNamespace(moment=np.array([2.0e4])), box=SimpleNamespace(h_box=np.array([0.18])))
    j = ds.root_joint(sr, "al2024_t3")
    P = 1.5 * 2.0e4 / 0.18 * 1.15
    assert j["P_cap_with_fitting_factor_N"] == pytest.approx(P)
    jj = j["joint"]
    assert jj["n_bolts_per_cap"] * jj["P_bolt_double_shear_N"] >= P and jj["MS_shear"] >= 0
    # AN4 single shear at Fsu 75 ksi ≈ 3680 lbf (AN-bolt tables)
    assert ds.FSU_STEEL * math.pi * (0.25 * ds.IN) ** 2 / 4 / 4.448222 == pytest.approx(3682, rel=0.01)


def test_roskam_usaf_wing_c172_order_of_magnitude():
    # C172-like: W_TO 2450 lb, n_ult 5.7, A 7.5, S 174 ft², λ 0.69, t/c 0.12, V_H 124 kt → actual wing ≈ 230 lb
    w = wd.roskam_usaf_wing(2450, 5.7, 7.5, 0.0, 174, 0.69, 0.12, 124)
    assert 150 < w < 320
    wc = wd.roskam_cessna_wing(2450, 5.7, 7.5, 174)
    assert wc > 0


def test_kicad_netlist_roundtrip(tmp_path):
    from acdt.core.systems.harness import Connector, Harness, Wire, kicad_netlist

    h = Harness("t")
    h.add_connector(Connector("J1", ["VBAT", "GND"], "XT30"))
    h.add_connector(Connector("ESC", ["V+", "GND"]))
    h.connect(Wire("W1", ("J1", "VBAT"), ("ESC", "V+"), "VBAT"))
    h.connect(Wire("W2", ("J1", "GND"), ("ESC", "GND"), "GND"))
    s = kicad_netlist(h, "t")
    assert s.count("(") == s.count(")") and '(export (version "E")' in s
    kinparse = pytest.importorskip("kinparse")
    p = tmp_path / "t.net"
    p.write_text(s)
    n = kinparse.parse_netlist(str(p))
    assert {c.ref for c in n.parts} == {"J1", "ESC"}
    assert {x.name: sorted((q.ref, q.num) for q in x.pins) for x in n.nets}["/VBAT"] == [("ESC", "1"), ("J1", "1")]


@pytest.mark.slow
@pytest.mark.parametrize("name", ["uav_endurance_payload"])
def test_hifi_report_from_stored_results(tmp_path, ex, name):
    """Regenerate report_fase4.md + calibration.json from the stored L3 JSONs (no solver is run)."""
    from acdt.domains.aircraft.hifi.run import run_hifi

    src = ex / "output" / f"{name}_hifi"
    if not (src / "flutter" / "flutter_results.json").exists():
        pytest.skip("stored Phase 4 results not present")
    for sub in ("cfd2d/section_verification.json", "fem/fem_results.json", "flutter/flutter_results.json"):
        (tmp_path / sub).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src / sub, tmp_path / sub)
    R = run_hifi(ex / f"{name}.yaml", tmp_path, steps=("detailed", "calibration"), log=lambda *_: None)
    cal = json.loads((tmp_path / "calibration.json").read_text())
    assert {"k_clmax", "k_cd_profile", "k_flutter", "k_EI"} <= set(cal["factors"])
    md = (tmp_path / "report_fase4.md").read_text()
    assert "Fatores de calibração" in md and "`k_flutter`" in md and "Roskam" in md
    assert R["steps"]["geometry"]["skipped"].startswith("passo não pedido")


@pytest.mark.slow
def test_nastran_sol145_deck_reads_back(tmp_path, ex):
    pytest.importorskip("pyNastran")
    from pyNastran.bdf.bdf import read_bdf

    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.hifi import fem, nastran

    res = run_pipeline("aircraft", str(ex / "uav_endurance_payload.yaml"))["result"]
    mesh = fem.build_box_mesh(res, 0.06)
    extra, masses, _ = fem.section_masses(res, mesh)
    VD = res.structures.vn.VD
    d = nastran.write_sol145(res, mesh, masses, extra, tmp_path, VD / 340.29, np.linspace(0.2 * VD, 2 * VD, 5))
    assert not Path(d["bdf"]).is_absolute()
    b = read_bdf(tmp_path.parent / d["bdf"], xref=True, debug=None)
    assert b.sol == 145 and len(b.caeros) >= 1 and len(b.flutters) == 1 and len(b.nodes) == len(mesh.nodes) + len(extra) == d["grids"]


def test_case_paths_stay_relative_and_tool_installs_are_basenames():
    root = Path(__file__).resolve().parents[1]
    case = root / "examples" / "output" / "cessna172_check_hifi_win"
    assert tools.case_relative(case / "fem", case) == "fem"
    sibling = case.parent / "cessna172_check_hifi" / "geometry" / "cessna172_check.step"
    assert tools.case_relative(sibling, case) == "../cessna172_check_hifi/geometry/cessna172_check.step"
    assert tools.case_relative(r"C:\acdt-tools\calculix\calculix_2.23_4win\ccx.EXE", case) == "ccx.EXE"
    assert tools.case_relative("examples/cessna172_check.yaml", case) == "examples/cessna172_check.yaml"
    resolved = tools.resolve_case_path("../cessna172_check_hifi/geometry/cessna172_check.step", case)
    assert resolved == sibling.resolve()
    # committed Windows cases must not grow another machine path
    bad = []
    for p in (root / "examples" / "output").glob("*_hifi_win/**/*"):
        if p.suffix.lower() not in {".json", ".md"}:
            continue
        text = p.read_text(encoding="utf-8")
        if re.search(r"[A-Za-z]:[\\/]", text) or "acdt-tools" in text:
            bad.append(str(p.relative_to(root)))
    assert bad == []


def test_gci_oscillatory_uses_range_uncertainty():
    from acdt.domains.aircraft.hifi.cfd import gci

    g = gci(0.4942, 0.4998, 0.4942, 1.0, 1.3, 1.7)
    assert g["oscillatory"] and g["gci_fine"] is None and g["f_ext"] is None
    assert g["u_osc"] == pytest.approx(0.5 * 0.0056 / 0.4942)


# ------------------------------------------------------------------ Gmsh as a separate process (no GPL import)
def test_gmsh_library_never_imported():
    import ast
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src"
    for f in src.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            names = [a.name for a in node.names] if isinstance(node, (ast.Import, ast.ImportFrom)) else []
            mod = getattr(node, "module", None) or ""
            assert "gmsh" not in names and not mod.startswith("gmsh"), f"{f} imports gmsh"


_GMSH = __import__("acdt.domains.aircraft.hifi.tools", fromlist=["find_exe"]).find_exe("gmsh")


@pytest.mark.skipif(_GMSH is None, reason="gmsh executable not on PATH / ACDT_HIFI_BIN")
def test_airfoil_mesh_via_gmsh_executable(tmp_path):
    from acdt.domains.aircraft.hifi import cfd
    m = cfd.airfoil_mesh("2412", tmp_path / "af.su2", 2.5e6, n_surf=81)
    assert (tmp_path / "af.geo").exists() and m["cells"] > 1000
    txt = (tmp_path / "af.su2").read_text()
    assert "MARKER_TAG= airfoil" in txt and "MARKER_TAG= farfield" in txt


@pytest.mark.skipif(_GMSH is None, reason="gmsh executable not on PATH / ACDT_HIFI_BIN")
def test_wing_half_mesh_via_gmsh_executable(tmp_path, ex):
    from acdt.domains.aircraft.hifi import cfd3d
    step = ex / "output" / "cessna172_check_hifi" / "geometry" / "cessna172_check_wing.step"
    m = cfd3d.wing_half_mesh(step, tmp_path / "w.su2", 1.49, 5.04, h_wing=0.3)
    assert m["cells"] > 1000
    assert m["markers"]["wing"] >= 1 and m["markers"]["symmetry"] == 1 and m["markers"]["farfield"] >= 1
    # Gmsh is launched with the .geo directory as cwd, so the STEP path stays relative. A drive
    # letter only appears when the STEP and the .geo are on different volumes (os.path.relpath).
    geo_txt = (tmp_path / "w.geo").read_text(encoding="utf-8")
    cited = re.search(r'ShapeFromFile\("([^"]+)"\)', geo_txt)
    assert cited and not re.match(r"^[A-Za-z]:", cited.group(1))
    assert "C:/Users" not in geo_txt and "C:\\" not in geo_txt


def test_stored_wing_half_geo_step_path_is_relative():
    """The checked-in Euler .geo must not embed a home directory.

    ``tools.run_gmsh`` starts Gmsh in the .geo directory, so ShapeFromFile is relative to that
    file: two levels up from ``wing_euler`` into the sibling Linux geometry folder.
    """
    geo = (Path(__file__).resolve().parents[1] / "examples" / "output"
           / "cessna172_check_hifi_win" / "wing_euler" / "wing_half.geo")
    text = geo.read_text(encoding="utf-8")
    assert "C:/Users" not in text and "C:\\" not in text
    rel = "../../cessna172_check_hifi/geometry/cessna172_check_wing.step"
    assert f'ShapeFromFile("{rel}")' in text
    assert (geo.parent / rel).is_file()
