"""Phase 6 calibration shell FEM of the sized box (A1) — in-house solver (:mod:`acdt.core.fem`, Q4 QM6/MITC4 shells,
2-node beams).

Unlike the Phase 4/5 model (flat covers at ±h/2, no D-cell) the mesh follows the real section used by the beam
model: covers on the airfoil contour (:class:`wingbox.section.Contour`, depth factor 0.95), the D-nose cell of
minimum-gauge LE skin closed by the front web, spar caps and stringers as beams on the cover line (the same
idealisation as the Megson section), ribs at the actual rib stations (box rib + nose rib), root clamped at the
fuselage side y0. LE sweep included. Metal: isotropic skins (t_s), webs (t_w); composite: sandwich covers
(face / core / face) and webs, UD caps.

**Calibration** (two unit load cases on the design's ultimate net running load p(y)): case F with p on the
front-spar line, case R with p on the rear-spar line (each split between the upper and lower corner). For each rib
bay (between two consecutive ribs, where the sections are kept in shape):
  * section rotation from a least-squares plane fitted to the spanwise displacements of the box nodes
    (plane sections, Bernoulli): φ_x; bending EI_bay = ∫_bay M dy / Δφ (M from the applied loads);
  * twist θ = (w_front − w_rear)/d from the corner nodes; with D(y) = Σ_outboard F d (the torque of the load moved
    by one box width): GJ_bay = ∫_bay D dy / (Δθ_F − Δθ_R) and the shear-centre position s = Δθ_F/(Δθ_F − Δθ_R),
    x_sc = x_f + s d (Bredt–Batho / unit-load reasoning, e.g. Megson 2017 §17–18);
  * cover force at mid-bay: ∫ N_yy over the box cover + stringer and cap axial forces, k_σ = F_cover / (M/h)
    (h = sizing depth) and the cover peak/mean stress ratio (shear lag, reported).
Factors = FEM / Megson-section values, stored on η = (y − y0)/(s − y0) (:class:`sizing6.Calibration`).

**Check** (:func:`fem_check6`): design ultimate loads — lift at the local c/4 and the q c² c_m0 couple, inertia
relief at the shear centre (the beam model's torque reference) — resolved statically onto the two spar lines;
FEM tip deflection / twist vs the calibrated beam."""
from __future__ import annotations

import math
import time

import numpy as np

from acdt.core.fem import FEModel, isotropic
from acdt.core.fem.laminate import sandwich

from .section import Contour


def _cos_space(n):
    return 0.5 * (1 - np.cos(np.linspace(0, math.pi, n + 1)))


class ShellBox:
    """Contour-following box + D-nose shell model of one semispan."""

    def __init__(self, wing, box, mat, x, y0, camber=None, n_le=8, n_h=4, nc_per_bay=2, ds=None, n_cov=None):
        from .. import structures as S
        self.wing, self.box, self.mat, self.x, self.y0 = wing, box, mat, x, y0
        det = box.details
        s = wing.span / 2
        y_rib = np.array(det["ribs"]["y"])
        c0 = S.chord_at(wing, np.array([y0]))[0]
        ds = ds or c0 / 8
        ys = [y_rib[0]]
        for a, b in zip(y_rib[:-1], y_rib[1:]):
            n = max(2, math.ceil((b - a) / ds))
            ys += list(np.linspace(a, b, n + 1)[1:])
        self.y = np.array(ys)
        self.rib_j = [int(np.argmin(np.abs(self.y - yr))) for yr in y_rib]
        n_str = int(det.get("n_str", 0)) if not mat["composite"] else 0
        self.n_str = n_str
        n_c = n_cov or ((n_str + 1) * nc_per_bay if n_str > 0 else 6)
        self.n_c, self.n_h, self.n_le = n_c, n_h, n_le
        self.c = S.chord_at(wing, self.y)
        self.tc = wing.tc_root + (wing.tc_tip - wing.tc_root) * self.y / s
        self.xle = self.y * math.tan(wing.sweep_at(0.0))
        fs, rs = x["xf"], x["xr"]
        self.fs, self.rs = fs, rs
        intp = lambda a: np.interp(self.y, box.y, np.asarray(a, float))
        self.ts_u, self.ts_l = intp(det["skin_upper"]), intp(det["skin_lower"])
        self.tw = intp(box.web_t)
        self.Acap = intp(det["cap_each"])
        self.h_siz = intp(box.h_box)
        if n_str:
            self.Astr = intp(det["A_str"])
        if mat["composite"]:
            self.tcore = intp(det["core_t"])
            self.tcw = intp(det["web_core_t"])
        self.camber = camber
        self._build()

    def _contour(self, j):
        if self.camber is not None:
            return Contour(self.camber[0], self.camber[1], float(self.tc[j]))
        return Contour.from_airfoil(getattr(self.wing, "airfoil", "NACA 0012"), float(self.tc[j]))

    def _build(self):
        m = self.mat
        E, nu, rho = m["E"], m["nu"], m["rho"]
        G = m["G"]
        nodes = []
        ny = len(self.y)
        nc, nh, nl = self.n_c, self.n_h, self.n_le
        xb = np.linspace(self.fs, self.rs, nc + 1)
        xn = self.fs * _cos_space(nl)                 # 0 … fs (LE → front spar)
        # per station ring: upper box (nc+1), rear web interior (nh−1), lower box reversed (nc+1),
        # front web interior (nh−1) → box ring; nose: upper LE nodes xn[1:nl] … , LE, lower
        self.idx = {}
        for j in range(ny):
            ct = self._contour(j)
            c, xl = self.c[j], self.xle[j]
            zu, zl = ct.z(xb)
            zun, zln = ct.z(xn)
            d = {}
            base = len(nodes)
            d["up"] = list(range(base, base + nc + 1))
            nodes += [(xl + xx * c, self.y[j], z * c) for xx, z in zip(xb, zu)]
            d["lo"] = list(range(len(nodes), len(nodes) + nc + 1))
            nodes += [(xl + xx * c, self.y[j], z * c) for xx, z in zip(xb, zl)]
            for key, k in (("wf", 0), ("wr", nc)):
                zz = np.linspace(zl[k], zu[k], nh + 1)[1:-1]
                ids = list(range(len(nodes), len(nodes) + nh - 1))
                nodes += [(xl + xb[k] * c, self.y[j], z * c) for z in zz]
                d[key] = [d["lo"][k]] + ids + [d["up"][k]]
            # nose: upper chain xn[nl-1]..xn[1], LE xn[0], lower chain xn[1]..xn[nl-1]
            nu_ids = list(range(len(nodes), len(nodes) + nl - 1))
            nodes += [(xl + xn[i] * c, self.y[j], zun[i] * c) for i in range(1, nl)]
            le = len(nodes)
            nodes.append((xl, self.y[j], 0.5 * (zun[0] + zln[0]) * c))
            nl_ids = list(range(len(nodes), len(nodes) + nl - 1))
            nodes += [(xl + xn[i] * c, self.y[j], zln[i] * c) for i in range(1, nl)]
            # nose chain from front-spar upper corner round the LE to the lower corner
            d["nose"] = [d["up"][0]] + nu_ids[::-1] + [le] + nl_ids + [d["lo"][0]]
            d["nose_up"] = nu_ids       # xn[1..nl-1]
            d["nose_lo"] = nl_ids
            self.idx[j] = d
        fm = FEModel(np.zeros((0, 3)))
        sec = {}

        def S_iso(t):
            k = ("iso", round(float(t), 8))
            if k not in sec:
                sec[k] = fm.add_section(isotropic(E, nu, float(t), rho))
            return sec[k]

        def S_sand(tf, tc):
            k = ("sw", round(float(tf), 8), round(float(tc), 8))
            if k not in sec:
                core = m["core"]
                sec[k] = fm.add_section(sandwich(E, nu, float(tf), core["E"], core["G"], float(tc), rho, core["rho"])
                                        if tc > 0 else isotropic(E, nu, 2 * float(tf), rho))
            return sec[k]

        comp = m["composite"]
        self.groups = {"up": [], "lo": [], "web": [], "nose": [], "rib": []}
        for j in range(ny - 1):
            a, b = self.idx[j], self.idx[j + 1]
            jm = j  # bay properties from the inboard station (step-wise)
            if comp:
                su, sl = S_sand(self.ts_u[jm] / 2, self.tcore[jm]), S_sand(self.ts_l[jm] / 2, self.tcore[jm])
                sw = S_sand(self.tw[jm] / 2, self.tcw[jm])
            else:
                su, sl, sw = S_iso(self.ts_u[jm]), S_iso(self.ts_l[jm]), S_iso(self.tw[jm])
            sn = S_iso(m["t_min_skin"])
            for key, sid in (("up", su), ("lo", sl), ("wf", sw), ("wr", sw), ("nose", sn)):
                ca, cb = a[key], b[key]
                grp = {"up": "up", "lo": "lo", "wf": "web", "wr": "web", "nose": "nose"}[key]
                for i in range(len(ca) - 1):
                    self.groups[grp].append(len(fm.shells))
                    fm.shells.append((ca[i], ca[i + 1], cb[i + 1], cb[i], sid, (0, 1, 0)))
        # ribs: box rib (grid between upper and lower chains) + nose rib (pairs xn[1..nl-1])
        nodes_l = nodes
        t_rib = np.interp(self.y[self.rib_j], self.box.details["ribs"]["y"], np.array(self.box.details["ribs"]["t_mm"]) * 1e-3)
        for r, j in enumerate(self.rib_j):
            d = self.idx[j]
            sid = S_iso(max(t_rib[r], m["t_min_web"]))
            sidn = S_iso(m["t_min_web"])

            def panel(top, bot, sid):
                cols = []
                for tp, bt in zip(top, bot):
                    if tp in d["wf"] and bt in d["wf"]:
                        cols.append(d["wf"])
                        continue
                    if tp in d["wr"] and bt in d["wr"]:
                        cols.append(d["wr"])
                        continue
                    pt, pb = np.array(nodes_l[tp]), np.array(nodes_l[bt])
                    col = [bt]
                    for f in np.linspace(0, 1, self.n_h + 1)[1:-1]:
                        col.append(len(nodes_l))
                        nodes_l.append(tuple(pb + f * (pt - pb)))
                    col.append(tp)
                    cols.append(col)
                for i in range(len(cols) - 1):
                    for k in range(self.n_h):
                        self.groups["rib"].append(len(fm.shells))
                        fm.shells.append((cols[i][k], cols[i + 1][k], cols[i + 1][k + 1], cols[i][k + 1], sid, None))
            panel(d["up"], d["lo"], sid)
            panel(d["nose_up"] + [d["up"][0]], d["nose_lo"] + [d["lo"][0]], sidn)
        # caps (4 corners) and stringers as beams on the cover line
        capm = m.get("cap", m) if comp else m
        self.bgroups = {"cap_up": [], "cap_lo": [], "str_up": [], "str_lo": []}
        stride = self.n_c // (self.n_str + 1) if self.n_str else 0
        for j in range(ny - 1):
            a, b = self.idx[j], self.idx[j + 1]
            A = max(self.Acap[j], 1e-9)
            pid = fm.add_beam_prop(E=capm["E"], G=capm.get("G", G), A=A, Iy=A**2 / 12, Iz=A**2 / 12, J=A**2 / 6,
                                   rho=capm["rho"])
            for key, k in (("up", 0), ("up", self.n_c), ("lo", 0), ("lo", self.n_c)):
                self.bgroups["cap_" + key].append(len(fm.beams))
                fm.beams.append((a[key][k], b[key][k], pid, None, None, (0, 0, 1)))
            if self.n_str:
                As = max(self.Astr[j], 1e-9)
                ps = fm.add_beam_prop(E=E, G=G, A=As, Iy=As**2 / 12, Iz=As**2 / 12, J=As**2 / 6, rho=rho)
                for key in ("up", "lo"):
                    for i in range(1, self.n_str + 1):
                        self.bgroups["str_" + key].append(len(fm.beams))
                        fm.beams.append((a[key][i * stride], b[key][i * stride], ps, None, None, (0, 0, 1)))
        fm.nodes = np.array(nodes_l, float)
        for n in range(len(fm.nodes)):
            if abs(fm.nodes[n, 1] - self.y[0]) < 1e-9:
                fm.fixed[n] = range(6)
        self.fm = fm
        self.xf_abs = self.xle + self.fs * self.c
        self.xr_abs = self.xle + self.rs * self.c
        self.d = self.xr_abs - self.xf_abs

    # -------------------------------------------------------------- loads / post
    def trib(self):
        t = np.zeros(len(self.y))
        dy = np.diff(self.y)
        t[:-1] += dy / 2
        t[1:] += dy / 2
        return t

    def load_vector(self, Ff, Fr):
        F = np.zeros(self.fm.ndof)
        for j in range(len(self.y)):
            d = self.idx[j]
            for n, f in ((d["up"][0], Ff[j]), (d["lo"][0], Ff[j]), (d["up"][-1], Fr[j]), (d["lo"][-1], Fr[j])):
                F[6 * n + 2] += f / 2
        return F

    def kinematics(self, u):
        U = u.reshape(-1, 6)
        nY = len(self.y)
        th, phi, w = np.zeros(nY), np.zeros(nY), np.zeros(nY)
        X = self.fm.nodes
        for j in range(nY):
            d = self.idx[j]
            wf = 0.5 * (U[d["up"][0], 2] + U[d["lo"][0], 2])
            wr = 0.5 * (U[d["up"][-1], 2] + U[d["lo"][-1], 2])
            th[j] = (wf - wr) / self.d[j]
            w[j] = 0.5 * (wf + wr)
            ids = d["up"] + d["lo"]
            A = np.c_[np.ones(len(ids)), X[ids, 2], X[ids, 0]]
            coef = np.linalg.lstsq(A, U[ids, 1], rcond=None)[0]
            phi[j] = coef[1]           # v = −φ z → dw/dy slope = −… (sign handled by the M sign)
        return {"theta": th, "phi": phi, "w": w}

    def moment(self, Fz):
        """M(y) = Σ_outboard F (y_k − y) from nodal station forces Fz (station totals)."""
        return np.array([np.sum(Fz[k:] * (self.y[k:] - yy)) for k, yy in enumerate(self.y)])

    def cover_force(self, st, j_mid_y):
        """Upper-cover spanwise force at y (elements of the bay containing y) and its peak/mean stress."""
        fm = self.fm
        R, N = st["R"], st["N"]
        up = np.asarray(self.groups["up"])
        yc = fm.nodes[np.array([fm.shells[e][0] for e in up]), 1]
        jj = np.searchsorted(self.y, j_mid_y) - 1
        sel = up[np.abs(yc - self.y[jj]) < 1e-9]
        a, b = R[sel, 0, 1], R[sel, 1, 1]
        nyy = a * a * N[sel, 0] + b * b * N[sel, 1] + 2 * a * b * N[sel, 2]
        # element chordwise width
        wid = np.array([np.linalg.norm(fm.nodes[fm.shells[e][1]] - fm.nodes[fm.shells[e][0]]) for e in sel])
        Fs = float(np.sum(nyy * wid))
        Pb = 0.0
        for g in ("cap_up", "str_up"):
            for bi in self.bgroups[g]:
                if abs(fm.nodes[fm.beams[bi][0], 1] - self.y[jj]) < 1e-9:
                    Pb += st["P"][bi]
        t = np.array([fm.sections[fm.shells[e][4]].t for e in sel])
        sig = nyy / t
        return Fs + Pb, float(np.min(sig) / np.mean(sig)) if np.mean(sig) != 0 else 1.0


def calibrate(wing, box, mat, x, y0, camber, sec_raw, beam, n_ult=1.5, **mesh_kw):
    """Run the F / R calibration cases on the design (box sized, raw Megson section ``sec_raw``) → Calibration +
    diagnostics."""
    from .sizing6 import Calibration
    t0 = time.time()
    sb = ShellBox(wing, box, mat, x, y0, camber, **mesh_kw)
    fm = sb.fm
    p = n_ult * np.maximum(np.interp(sb.y, beam.y, -np.gradient(beam.shear, beam.y)), 0.0)
    Fz = p * sb.trib()
    st = fm.solve_static(sb.load_vector(Fz, 0 * Fz))
    lu, free = st["lu"], st["free"]
    FR = sb.load_vector(0 * Fz, Fz)
    uR = np.zeros(fm.ndof)
    uR[free] = lu.solve(FR[free])
    kF, kR = sb.kinematics(st["u"]), sb.kinematics(uR)
    stR = fm.recover(uR, st["_sh"], st["_bd"])
    M = sb.moment(Fz)
    D = np.array([np.sum(Fz[k:] * sb.d[k:]) for k in range(len(sb.y))])
    rj = sb.rib_j
    s = wing.span / 2
    eta, kEI, kGJ, dxs, ksig, peak, rows, IMs, GAs = [], [], [], [], [], [], [], [], []
    for a, b in zip(rj[:-1], rj[1:]):
        ya, yb = sb.y[a], sb.y[b]
        seg = slice(a, b + 1)
        IM = np.trapezoid(M[seg], sb.y[seg])
        ID = np.trapezoid(D[seg], sb.y[seg])
        dphi = 0.5 * ((kF["phi"][b] - kF["phi"][a]) + (kR["phi"][b] - kR["phi"][a]))
        dthF, dthR = kF["theta"][b] - kF["theta"][a], kR["theta"][b] - kR["theta"][a]
        EI = abs(IM / dphi) if dphi else math.nan
        # transverse-shear flexibility (thin webs): γ = w' − (bending slope), slope = −φ (v = −z w')
        wF = 0.5 * (kF["w"] + kR["w"])
        ph = 0.5 * (kF["phi"] + kR["phi"])
        gam = (wF[b] - wF[a]) / (yb - ya) - 0.5 * (-ph[a] - ph[b])
        Vm = np.trapezoid(np.array([np.sum(Fz[k:]) for k in range(a, b + 1)]), sb.y[seg]) / (yb - ya)
        GA = Vm / gam if gam > 0 else math.inf
        GJ = ID / (dthF - dthR) if dthF != dthR else math.nan
        sfr = dthF / (dthF - dthR)
        ym = 0.5 * (ya + yb)
        cm = np.interp(ym, sb.y, sb.c)
        x_sc_c = sb.fs + sfr * (sb.rs - sb.fs)
        # cover force: mean of the two cases (same bending) at mid-bay
        Fc1, pk1 = sb.cover_force(st, ym)
        Fc2, pk2 = sb.cover_force(stR, ym)
        Mm = np.interp(ym, sb.y, M)
        hm = np.interp(ym, sb.y, sb.h_siz)
        kc = abs(0.5 * (Fc1 + Fc2)) / (Mm / hm) if Mm > 0 else math.nan
        EIr = np.interp(ym, box.y, sec_raw["EI_raw"])
        GJr = np.interp(ym, box.y, sec_raw["GJ_raw"])
        xr_ = np.interp(ym, box.y, sec_raw["x_sc_c_raw"])
        e = (ym - y0) / (s - y0)
        IMs.append(IM / (yb - ya))
        eta.append(e)
        kEI.append(EI / EIr)
        kGJ.append(GJ / GJr)
        dxs.append(x_sc_c - xr_)
        ksig.append(kc)
        peak.append(0.5 * (pk1 + pk2))
        GAs.append(GA)
        rows.append({"y_mid": ym, "GA_fem": GA, "EI_fem": EI, "EI_sec": EIr, "GJ_fem": GJ, "GJ_sec": GJr, "x_sc_c_fem": x_sc_c,
                     "x_sc_c_sec": xr_, "k_sigma": kc, "peak_over_mean": 0.5 * (pk1 + pk2)})
    eta = np.array(eta)
    lowload = np.array(IMs) < 0.05 * max(IMs)
    # robust: bays with < 5 % of the root-bay moment (tip) give ill-conditioned ratios → filled from inboard
    def clean(v, lo, hi, default):
        v = np.array(v, float)
        bad = ~np.isfinite(v) | (v < lo) | (v > hi) | lowload
        if bad.all():
            return np.full_like(v, default)
        v[bad] = np.interp(eta[bad], eta[~bad], v[~bad])
        return v
    for r_, lw in zip(rows, lowload):
        r_["low_load_filled"] = bool(lw)
    cal = Calibration(eta, clean(kEI, 0.2, 5, 1), clean(kGJ, 0.2, 5, 1), clean(dxs, -0.3, 0.3, 0),
                      clean(ksig, 0.3, 3, 1), source="shell6 F/R")
    ga = np.array(GAs, float)
    okg = np.isfinite(ga) & (ga > 0) & ~lowload
    cal.GA = np.interp(eta, eta[okg], ga[okg]) if okg.any() else np.full_like(eta, np.inf)
    diag = {"nodes": int(len(fm.nodes)), "shells": len(fm.shells), "beams": len(fm.beams), "t_s": time.time() - t0,
            "bays": rows, "tip_w_F": float(kF["w"][-1]), "tip_theta_F_deg": math.degrees(kF["theta"][-1]),
            "tip_theta_R_deg": math.degrees(kR["theta"][-1]), "struct_mass_semispan_kg": fm.structural_mass()}
    return cal, diag, sb


def fem_check6(wing, box, mat, x, y0, camber, lift, cm0, q, beam, sec, n_ult=1.5, **mesh_kw):
    """Design ultimate load case on the shell model vs the calibrated beam (tip w, tip twist)."""
    from .. import structures as S
    t0 = time.time()
    sb = ShellBox(wing, box, mat, x, y0, camber, **mesh_kw)
    yy = sb.y
    tr = sb.trib()
    c = sb.c
    L = n_ult * np.interp(yy, beam.y, lift) * tr
    net = n_ult * np.interp(yy, beam.y, -np.gradient(beam.shear, beam.y)) * tr
    I = L - net                                           # inertia relief (positive down)
    Mp = n_ult * q * c**2 * np.interp(yy, beam.y, cm0) * tr
    xa = sb.xle + 0.25 * c
    xsc = sb.xle + np.interp(yy, box.y, sec["x_sc_c"]) * c
    d = sb.d

    def split(F, xp):
        return F * (sb.xr_abs - xp) / d, F * (xp - sb.xf_abs) / d
    Lf, Lr = split(L, xa)
    If, Ir = split(I, xsc)
    Ff = Lf - If + Mp / d
    Fr = Lr - Ir - Mp / d
    st = sb.fm.solve_static(sb.load_vector(Ff, Fr))
    k = sb.kinematics(st["u"])
    # beam (calibrated section), clamped at y0
    y = np.linspace(y0, wing.span / 2, 300)
    M = n_ult * np.interp(y, beam.y, beam.moment)
    T = n_ult * np.interp(y, beam.y, beam.torque)
    EI, GJ = np.interp(y, box.y, sec["EI"]), np.interp(y, box.y, sec["GJ"])
    kk = M / EI
    slope = np.r_[0, np.cumsum(0.5 * (kk[1:] + kk[:-1]) * np.diff(y))]
    wb = np.r_[0, np.cumsum(0.5 * (slope[1:] + slope[:-1]) * np.diff(y))]
    GA = sec.get("GA")
    if GA is not None:
        Vb = n_ult * np.interp(y, beam.y, beam.shear)
        g = Vb / np.interp(y, box.y, GA)
        wb = wb + np.r_[0, np.cumsum(0.5 * (g[1:] + g[:-1]) * np.diff(y))]
    tw_pure = np.r_[0, np.cumsum(0.5 * (T[1:] / GJ[1:] + T[:-1] / GJ[:-1]) * np.diff(y))]
    # Swept-axis kinematics: at constant y the front/rear points belong to different stations of the
    # (swept) shear-centre line, so bending adds a streamwise pseudo-twist −w'·dx_sc/dy (washout for aft
    # sweep; swept-wing bending–torsion kinematics as in Bisplinghoff, Ashley & Halfman, Aeroelasticity, 1955).
    xsc_y = np.interp(y, yy, xsc)
    wslope = np.gradient(wb, y)
    tw = tw_pure - wslope * np.gradient(xsc_y, y)
    Fc, pk = sb.cover_force(st, 0.5 * (yy[sb.rib_j[0]] + yy[sb.rib_j[1]]))
    ym = 0.5 * (yy[sb.rib_j[0]] + yy[sb.rib_j[1]])
    Mm = n_ult * np.interp(ym, beam.y, beam.moment)
    return {"tip_w_fem_m": float(k["w"][-1]), "tip_w_beam_m": float(wb[-1]),
            "tip_twist_fem_deg": math.degrees(k["theta"][-1]), "tip_twist_beam_deg": math.degrees(tw[-1]),
            "tip_twist_beam_pure_torsion_deg": math.degrees(tw_pure[-1]),
            "root_bay_cover_force_fem_N": abs(Fc), "root_bay_cover_force_beam_N":
                float(Mm / np.interp(ym, box.y, box.h_box) * np.interp(ym, box.y, _ks(box))),
            "root_bay_peak_over_mean": pk,
            "V0_N": float(np.sum(Ff + Fr)), "V0_beam_N": float(n_ult * np.interp(y0, beam.y, beam.shear)),
            "T0_fem_Nm": float(np.sum(Ff * (xsc - sb.xf_abs) - Fr * (sb.xr_abs - xsc))),
            "T0_beam_Nm": float(n_ult * np.interp(y0, beam.y, beam.torque)),
            "nodes": int(len(sb.fm.nodes)), "t_s": time.time() - t0,
            "y": yy.tolist(), "w_fem": k["w"].tolist(), "theta_fem_deg": np.degrees(k["theta"]).tolist(),
            "y_beam": y.tolist(), "w_beam": wb.tolist(), "theta_beam_deg": np.degrees(tw).tolist()}


def _ks(box):
    ks = box.details.get("k_sigma")
    return np.ones_like(box.y) if ks is None else np.asarray(ks, float)
