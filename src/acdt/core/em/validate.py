"""Canonical PO validation cases against closed forms (Knott, Shaeffer & Tuley 1993, Table 6.1; Balanis 2012 §11.3).
Tolerances are the acceptance bands used by the tests."""
from __future__ import annotations

import math

import numpy as np

from . import po


def cases(freq=10e9) -> list[dict]:
    lam = po.C0 / freq
    k = 2 * math.pi / lam
    out = []
    # 1 flat plate a×b, principal plane, θ = 0…20°: 4π(ab)²/λ² cos²θ sinc²(ka sinθ)
    a, b = 0.3, 0.2
    m = po.plate(a, b)
    th = np.radians(np.linspace(0, 20, 21))
    r = np.c_[np.sin(th), np.zeros_like(th), np.cos(th)]
    e = np.tile([0, 1.0, 0], (len(th), 1))
    s = po.rcs(m, freq, -r, r, e, e)
    ref = 4 * math.pi * (a * b) ** 2 / lam ** 2 * np.cos(th) ** 2 * np.sinc(k * a * np.sin(th) / math.pi) ** 2
    main = ref > ref[0] * 1e-2                                       # main lobe and first side lobes (> −20 dB)
    out.append({"case": "plate 0.3×0.2 m, normal incidence", "po_dbsm": float(po.dbsm(s[0])),
                "exact_dbsm": float(po.dbsm(ref[0])), "tol_db": 0.01})
    out.append({"case": "plate, θ ≤ 20° (lobes > −20 dB)", "po_dbsm": None, "exact_dbsm": None,
                "max_abs_delta_db": float(np.max(np.abs(po.dbsm(s[main]) - po.dbsm(ref[main])))), "tol_db": 0.01})
    # 2 bistatic plate, specular direction for θi = 30°: same peak 4πA²cos²θ/λ²
    ti = math.radians(30)
    kin = np.array([[math.sin(ti), 0, -math.cos(ti)]])
    sdir = np.array([[math.sin(ti), 0, math.cos(ti)]])
    eh = np.array([[0, 1.0, 0]])
    sb = po.rcs(m, freq, kin, sdir, eh, eh)[0]
    out.append({"case": "plate bistatic specular θi = 30°", "po_dbsm": float(po.dbsm(sb)),
                "exact_dbsm": float(po.dbsm(4 * math.pi * (a * b) ** 2 / lam ** 2 * math.cos(ti) ** 2)), "tol_db": 0.01})
    # 3 sphere radius 0.5 m, 2–4 GHz band average: πa² (PO high-frequency limit)
    R = 0.5
    sp = po.icosphere(R, 5)
    fs = np.linspace(2e9, 4e9, 21)
    vals = np.array([po.monostatic(sp, f, 0.0, 0.0, "VV", nose=(1, 0, 0))[()] for f in fs])
    out.append({"case": "sphere a = 0.5 m (20 480 facets), 2–4 GHz mean", "po_dbsm": float(po.dbsm(vals.mean())),
                "exact_dbsm": float(po.dbsm(math.pi * R ** 2)), "tol_db": 0.5,
                "spread_db": [float(po.dbsm(vals.min())), float(po.dbsm(vals.max()))]})
    # 4 circular cylinder broadside 2πaL²/λ
    Rc, L = 0.1, 1.0
    cy = po.cylinder(Rc, L, n_theta=720)
    sc = po.monostatic(cy, freq, 0.0, 0.0, "VV", nose=(1, 0, 0))
    out.append({"case": "cylinder a = 0.1 m, L = 1 m, broadside", "po_dbsm": float(po.dbsm(sc)),
                "exact_dbsm": float(po.dbsm(2 * math.pi * Rc * L ** 2 / lam)), "tol_db": 0.3})
    # 5 90° dihedral, symmetric incidence, 2-bounce SBR: 8πa²b²/λ²; off-bisector ±15°: 16π(ab)²/λ² sin²(45°−15°)
    a2 = b2 = 0.3
    d = po.dihedral(a2, b2, 90)
    for ang, ref_v in ((0.0, 8 * math.pi * a2 ** 2 * b2 ** 2 / lam ** 2),
                       (15.0, 16 * math.pi * (a2 * b2) ** 2 / lam ** 2 * math.sin(math.radians(30)) ** 2)):
        for pol in ("VV", "HH"):
            sd = po.monostatic(d, freq, 0.0, ang, pol, nose=(1, 0, 0), bounces=2)
            out.append({"case": f"dihedral 90°, 0.3×0.3 m, {ang:.0f}° off bisector, {pol}, 2 bounces",
                        "po_dbsm": float(po.dbsm(sd)), "exact_dbsm": float(po.dbsm(ref_v)), "tol_db": 1.0})
    for c in out:
        if c.get("po_dbsm") is not None:
            c["delta_db"] = c["po_dbsm"] - c["exact_dbsm"]
            c["ok"] = abs(c["delta_db"]) <= c["tol_db"]
        else:
            c["ok"] = c["max_abs_delta_db"] <= c["tol_db"]
    return out
