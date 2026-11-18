"""3-D preview of the wing internal structure (matplotlib, off-screen PNG): semi-transparent skin, spar webs and
caps on the airfoil contour, ribs at the rib pitch, cover stringers (metal) and two section cuts (contour, box,
D-nose cell, stringers, shear centre). Geometry only — a visual check of the parametric layout."""
from __future__ import annotations

import math

import numpy as np

from .section import Contour, naca4


def _stringer_x(xf, xr, chord, pitch):
    if not (pitch and pitch == pitch and pitch > 0):
        return np.array([])
    n = max(int((xr - xf) * chord / pitch) - 1, 0)
    return np.linspace(xf, xr, n + 2)[1:-1]


def render_wing_structure(wing, x: dict, box, path, title: str = "", p_camber: float = 0.4, x_sc=None,
                          z_scale: float = 1.5, le_cell: bool = True):
    """``x``: xf, xr, tc_root, tc_tip, camber, rib_pitch (as in :mod:`wingbox.optimize`); ``box``: sized
    :class:`structures.WingBoxResult` (stringer pitch, thicknesses); ``x_sc``: shear centre x/c per box.y."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    s = wing.span / 2
    cr, ct = wing.c_root, wing.c_tip
    chord = lambda y: cr + (ct - cr) * y / s
    tc = lambda y: x["tc_root"] + (x["tc_tip"] - x["tc_root"]) * y / s
    xle = lambda y: 0.25 * cr - 0.25 * chord(y) + y * math.tan(wing.sweep_c4)
    xf, xr, m = x["xf"], x["xr"], x["camber"]
    det = box.details
    composite = float(np.nanmax(det.get("core_t", np.zeros(1)))) > 0 or "E_cap" in str(box.material)
    ys = np.linspace(0, s, 25)
    fig = plt.figure(figsize=(16, 8))
    ax = fig.add_axes([-0.06, -0.08, 0.76, 1.16], projection="3d")
    xa = np.linspace(0, 1, 41)

    def surf(y, xc, upper=True):
        ct_ = Contour(m, p_camber, tc(y), 1.0)
        zu, zl = ct_.z(xc)
        return xle(y) + xc * chord(y), (zu if upper else zl) * chord(y) * z_scale

    # skins
    for up in (True, False):
        polys = []
        for j in range(len(ys) - 1):
            for i in range(len(xa) - 1):
                q = []
                for (yy, a) in ((ys[j], xa[i]), (ys[j], xa[i + 1]), (ys[j + 1], xa[i + 1]), (ys[j + 1], xa[i])):
                    X, Z = surf(yy, np.array([a]), up)
                    q.append((X[0], yy, Z[0]))
                polys.append(q)
        ax.add_collection3d(Poly3DCollection(polys, facecolor="#9ecae1", edgecolor="none", alpha=0.16))
    # spar webs + caps
    for xs, col in ((xf, "#d62728"), (xr, "#ff7f0e")):
        polys = []
        for j in range(len(ys) - 1):
            Xa, Zua = surf(ys[j], np.array([xs]), True)
            _, Zla = surf(ys[j], np.array([xs]), False)
            Xb, Zub = surf(ys[j + 1], np.array([xs]), True)
            _, Zlb = surf(ys[j + 1], np.array([xs]), False)
            polys.append([(Xa[0], ys[j], Zla[0]), (Xa[0], ys[j], Zua[0]), (Xb[0], ys[j + 1], Zub[0]),
                          (Xb[0], ys[j + 1], Zlb[0])])
        ax.add_collection3d(Poly3DCollection(polys, facecolor=col, edgecolor="none", alpha=0.55))
        for up in (True, False):
            pts = np.array([[surf(y, np.array([xs]), up)[0][0], y, surf(y, np.array([xs]), up)[1][0]] for y in ys])
            ax.plot(pts[:, 0], pts[:, 1], pts[:, 2], color="k", lw=2.2 if composite else 1.4)
    # ribs
    L = x["rib_pitch"]
    y_rib = np.r_[np.arange(0, s, L), s]
    xb = np.linspace(xf, xr, 15)
    for yr in y_rib:
        Xu, Zu = surf(yr, xb, True)
        Xl, Zl = surf(yr, xb, False)
        poly = [(a, yr, b) for a, b in zip(Xu, Zu)] + [(a, yr, b) for a, b in zip(Xl[::-1], Zl[::-1])]
        ax.add_collection3d(Poly3DCollection([poly], facecolor="#2ca02c", edgecolor="#1b5e20", alpha=0.45, lw=0.5))
    # stringers (metal): count from the local pitch, drawn per bay
    if not composite:
        pitch = np.asarray(det.get("stringer_pitch", []), float)
        for k in range(len(y_rib) - 1):
            ym = 0.5 * (y_rib[k] + y_rib[k + 1])
            pk = float(np.interp(ym, box.y, np.nan_to_num(pitch, nan=0.0))) if pitch.size else 0.0
            tb = float(np.interp(ym, box.y, det["cover_tbar_upper"]))
            if tb <= float(np.interp(ym, box.y, det["skin_upper"])) * 1.01:
                continue
            for a in _stringer_x(xf, xr, chord(ym), pk):
                for up in (True, False):
                    yy = np.array([y_rib[k], y_rib[k + 1]])
                    P = [surf(v, np.array([a]), up) for v in yy]
                    ax.plot([P[0][0][0], P[1][0][0]], yy, [P[0][1][0], P[1][1][0]], color="#6a3d9a", lw=0.7)
    # LE contour lines for the D-nose
    for yy in (0.0, s):
        xs_ = np.linspace(0, 1, 60)
        Xu, Zu = surf(yy, xs_, True)
        Xl, Zl = surf(yy, xs_, False)
        ax.plot(np.r_[Xu, Xl[::-1]], np.full(120, yy), np.r_[Zu, Zl[::-1]], color="#08519c", lw=0.8)
    ax.set_xlim(-0.1 * cr, 1.1 * cr)
    ax.set_ylim(0, s)
    ax.set_zlim(-0.6 * cr, 0.6 * cr)
    ax.set_box_aspect((1.2 * cr, s, 1.2 * cr), zoom=1.1)
    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
        pane.set_alpha(0.0)
    ax.view_init(elev=24, azim=-52)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_zlabel(f"z [m] (×{z_scale:g})")
    ax.set_title(title or "Estrutura interna", fontsize=11)

    # section cuts
    for k, yy in enumerate((0.0, 0.5 * s)):
        a2 = fig.add_axes([0.68, 0.60 - 0.42 * k, 0.31, 0.28])
        c = chord(yy)
        xu, zu, xl, zl = naca4(m, p_camber, tc(yy), 121)
        a2.fill(np.r_[xu, xl[::-1]] * c, np.r_[zu, zl[::-1]] * c, color="#deebf7", ec="#08519c", lw=1)
        con = Contour(m, p_camber, tc(yy), 0.95)
        xb2 = np.linspace(xf, xr, 50)
        zub, zlb = con.z(xb2)
        a2.plot(np.r_[xb2, xb2[::-1], xb2[:1]] * c, np.r_[zub, zlb[::-1], zub[:1]] * c, "k-", lw=1.6, label="caixão")
        for xs, col in ((xf, "#d62728"), (xr, "#ff7f0e")):
            zz = con.z(np.array([xs]))
            a2.plot([xs * c] * 2, [zz[1][0] * c, zz[0][0] * c], color=col, lw=3)
        if le_cell:
            xn = np.linspace(0, xf, 40)
            zun, zln = con.z(xn)
            a2.plot(np.r_[xn, xn[::-1]] * c, np.r_[zun, zln[::-1]] * c, color="#08519c", ls="--", lw=1,
                    label="célula D (bordo de ataque)")
        if not composite:
            pk = float(np.interp(yy, box.y, np.nan_to_num(np.asarray(det.get("stringer_pitch", [0.0]), float))))
            xsx = _stringer_x(xf, xr, c, pk)
            if len(xsx):
                zs = con.z(xsx)
                a2.plot(xsx * c, zs[0] * c, "s", color="#6a3d9a", ms=3, label="reforçadores")
                a2.plot(xsx * c, zs[1] * c, "s", color="#6a3d9a", ms=3)
        if x_sc is not None:
            xs_c = float(np.interp(yy, box.y, x_sc))
            a2.plot(xs_c * c, float(np.mean(con.z(np.array([xs_c])))) * c, "r+", ms=12, mew=2, label="centro de corte")
        a2.set_aspect("equal")
        a2.set_title(f"secção y = {yy:.2f} m  (c = {c:.2f} m, t/c = {tc(yy):.3f}, longarinas {xf:.2f}/{xr:.2f} c)",
                     fontsize=8)
        a2.tick_params(labelsize=7)
        a2.grid(alpha=0.3)
        if k == 0:
            a2.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.25), ncol=2)
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
