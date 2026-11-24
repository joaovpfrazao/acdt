# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Render 3-D (PNG, matplotlib fora do ecrã) do avião com a estrutura paramétrica tal como a tabela de membros e a
geometria do layout a descrevem (:func:`.structure_layout.analyse_layout`).

Desenha: revestimento exterior semitransparente (fuselagem, booms, superfícies), longarinas e nervuras dos caixões
(asa, estabilizador, deriva), cavernas (fortes destacadas), anteparas, reforçadores e longarinas da fuselagem, piso
(vigas e painel), soleiras das aberturas, ferragens (olhais/cavilhas) e berço do motor. Cores por tipo de membro
(``color_by="kind"``) ou pelo fator de reserva RF_min do membro (``color_by="RF"``; cinzento = desconhecido).
Uso: ``render_layout(res.structure_layout, "aviao.png")`` ou
``python -m acdt.domains.aircraft.structure_render exemplo.yaml saida.png [--rf]``.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

from acdt.core.structures import frames as fr

KIND_COLORS: dict[str, str] = {
    "revestimento": "#9aa5b1", "caverna": "#4e79a7", "caverna_pesada": "#d62728", "antepara": "#f28e2b",
    "reforcador": "#59a14f", "longarina": "#1b5e20", "alma_longarina": "#1f3a93", "nervura": "#17becf",
    "piso": "#8c564b", "viga_piso": "#5d3a1a", "soleira": "#e377c2", "ferragem": "#111111",
    "berco_motor": "#7f7f7f", "boom": "#9467bd", "escora": "#bcbd22",
}
LABELS: dict[str, str] = {
    "caverna": "cavernas", "caverna_pesada": "cavernas fortes", "antepara": "anteparas", "reforcador": "reforçadores",
    "longarina": "longarinas (fuselagem)", "alma_longarina": "longarinas (caixões)", "nervura": "nervuras",
    "piso": "piso", "viga_piso": "vigas de piso", "soleira": "soleiras de aberturas", "ferragem": "ferragens",
    "berco_motor": "berço do motor", "boom": "cavernas dos booms", "revestimento": "revestimento",
    "escora": "escoras da asa",
}


def _rf_color(rf: float | None, cmap: Any) -> Any:
    if rf is None or not math.isfinite(rf):
        return "#b0b0b0"
    return cmap(min(max((rf - 1.0) / 2.0, 0.0), 1.0))     # RF 1 → vermelho, ≥ 3 → verde


def _section_xyz(R: float, w: float | None, h: float | None, n_exp: float, k: int = 48) -> tuple[np.ndarray, np.ndarray]:
    sp = fr.section_points(R, k, w, h, n_exp)
    y, z = np.append(sp["y"], sp["y"][0]), np.append(sp["z"], sp["z"][0])
    return y, z


def _surface_lines(sf: dict[str, Any]) -> dict[str, Any]:
    """Planta da superfície: bordos, longarinas e nervuras em coordenadas globais (um lado ou os dois). Com
    ``root_c4_m``/``span_vec_m`` (layout com colocação real) segue diedro, flecha, inclinação e incidência; sem
    eles, o plano z0 antigo."""
    cr, ct = sf["c_root_m"], sf["c_tip_m"]
    fs, rs = sf["front_spar_xc"], sf["rear_spar_xc"]
    pitch = max(float(sf.get("rib_pitch_m") or 0.6 * (cr + ct) / 2), 1e-3)
    sides = (1.0, -1.0) if sf.get("mirror", True) else (1.0,)
    out: dict[str, list[Any]] = {"outline": [], "spars": [], "ribs": []}
    if sf.get("span_vec_m") is not None:
        r0 = np.asarray(sf["root_c4_m"], float)
        sv = np.asarray(sf["span_vec_m"], float)
        s = float(np.hypot(sv[1], sv[2])) or 1e-9
        inc = math.radians(float(sf.get("incidence_deg") or 0.0))
    else:
        s, sw = sf["semispan_m"], sf.get("sweep_c4_rad", 0.0)
        r0 = np.array([sf["x_c4_root_m"], sf["y0_m"], sf["z0_m"]], float)
        sv = (np.array([s * math.tan(sw), 0.0, s]) if sf.get("axis", "y") == "z"
              else np.array([s * math.tan(sw), s, 0.0]))
        inc = 0.0
    eta_ribs = np.unique(np.append(np.arange(0.0, s, pitch), s)) / s

    def P(eta: float, xc: float, side: float) -> tuple[float, float, float]:
        v = sv * np.array([1.0, side, 1.0])
        n = np.cross([1.0, 0.0, 0.0], [0.0, v[1], v[2]])
        n = n / (np.linalg.norm(n) or 1.0)
        if n[2] < 0 or (abs(n[2]) < 1e-9 and n[1] < 0):
            n = -n
        cdir = math.cos(inc) * np.array([1.0, 0.0, 0.0]) - math.sin(inc) * n   # incidência: bordo de fuga desce
        c = cr + (ct - cr) * eta
        p = r0 + eta * v + (xc - 0.25) * c * cdir
        return float(p[0]), float(p[1]), float(p[2])

    for sd in sides:
        out["outline"].append([P(0, 0, sd), P(1, 0, sd), P(1, 1, sd), P(0, 1, sd)])
        out["spars"] += [[P(0, fs, sd), P(1, fs, sd)], [P(0, rs, sd), P(1, rs, sd)]]
        out["ribs"] += [[P(e, fs, sd), P(e, rs, sd)] for e in eta_ribs]
    return out


def render_layout(layout: dict[str, Any], path: str | Path, color_by: str = "kind", title: str = "",
                  elev: float = 24.0, azim: float = -128.0, dpi: int = 170) -> Path:
    """Desenha o layout (``res.structure_layout``) e grava o PNG. Devolve o caminho."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    if not layout.get("evaluated") or not layout.get("geometry"):
        raise ValueError("layout sem geometria (correr com structure_layout.enabled e a versão com 'geometry')")
    geo = layout["geometry"]
    mem = {m["id"]: m for m in layout["members"]}
    by_rf = color_by.upper() == "RF"
    cmap = plt.get_cmap("RdYlGn")

    def col(kind: str, mid: str | None = None) -> Any:
        if by_rf:
            m = mem.get(mid or "")
            return _rf_color(None if m is None else m.get("RF_min"), cmap)
        return KIND_COLORS.get(kind, "#333333")

    used: set[str] = set()
    fig = plt.figure(figsize=(13, 9))
    ax = fig.add_subplot(111, projection="3d")
    pts: list[np.ndarray] = []

    def line(p: Any, kind: str, mid: str | None = None, lw: float = 1.0, alpha: float = 1.0) -> None:
        a = np.asarray(p, float)
        ax.plot(a[:, 0], a[:, 1], a[:, 2], color=col(kind, mid), lw=lw, alpha=alpha)
        pts.append(a)
        used.add(kind)

    # ---- corpos: fuselagem e booms
    for body in geo.get("bodies", []):
        xs, Rs = np.asarray(body["x_m"], float), np.asarray(body["R_m"], float)
        y0, z0 = body.get("y0_m", 0.0), body.get("z0_m", 0.0)
        w_, h_, n_ = body.get("w_m"), body.get("h_m"), float(body.get("n_exp") or 2.0)
        Rmax = float(Rs.max()) if Rs.size else 1.0

        def sc(R: float) -> tuple[float | None, float | None]:
            return (w_ * R / Rmax, h_ * R / Rmax) if (w_ and h_) else (None, None)
        X, Y, Z = [], [], []
        for x, R in zip(xs, Rs):
            ws_, hs_ = sc(R)
            yy, zz = _section_xyz(max(R, 1e-4), ws_, hs_, n_, 40)
            X.append(np.full_like(yy, x))
            Y.append(y0 + yy)
            Z.append(z0 + zz)
        ax.plot_surface(np.array(X), np.array(Y), np.array(Z), color="#9aa5b1", alpha=0.07, linewidth=0, shade=False)
        # reforçadores / longarinas
        nst = int(body.get("n_stringers") or 0)
        if nst:
            ring = [fr.section_points(max(R, 1e-4), nst, sc(R)[0], sc(R)[1], n_) for R in Rs]
            for k in range(nst):
                line([[x, y0 + r["y"][k], z0 + r["z"][k]] for x, r in zip(xs, ring)], "reforcador",
                     f"{body['comp']}.reforcadores", lw=0.5, alpha=0.8)
        for tl in body.get("longeron_theta_deg") or []:
            t = math.radians(float(tl))
            line([[x, y0 + R * math.sin(t), z0 + R * math.cos(t)] for x, R in zip(xs, Rs)], "longarina",
                 f"{body['comp']}.longarinas", lw=2.0)
        # cavernas
        for f in body.get("frames", []):
            yy, zz = _section_xyz(max(f["R_m"], 1e-4), f.get("w_m"), f.get("h_m"), float(f.get("n_exp") or 2.0))
            kind = "caverna_pesada" if f.get("heavy") else ("boom" if body["comp"] != "fuselagem" else "caverna")
            mid = f"{body['comp']}.caverna@{f['x_m']:.3f}"
            line(np.c_[np.full_like(yy, f["x_m"]), y0 + yy, z0 + zz], kind, mid,
                 lw=2.6 if f.get("heavy") else 0.9)
        # anteparas
        for bk in body.get("bulkheads", []):
            yy, zz = _section_xyz(max(bk["R_m"], 1e-4), bk.get("w_m"), bk.get("h_m"), n_)
            poly = Poly3DCollection([list(zip(np.full_like(yy, bk["x_m"]), y0 + yy, z0 + zz))], alpha=0.35,
                                    facecolor=col("antepara", bk.get("member")), edgecolor=col("antepara", bk.get("member")))
            ax.add_collection3d(poly)
            used.add("antepara")
        # piso
        fl = body.get("floor")
        if fl:
            for b in fl["beams"]:
                hw = 0.5 * b["span_m"]
                line([[b["x_m"], y0 - hw, z0 + b["z_m"]], [b["x_m"], y0 + hw, z0 + b["z_m"]]], "viga_piso",
                     f"{body['comp']}.piso.viga@{b['x_m']:.3f}", lw=2.0)
            xb = [b["x_m"] for b in fl["beams"]]
            hw = [0.5 * b["span_m"] for b in fl["beams"]]
            zf = fl["z_m"]
            quad = [(x, y0 - h, z0 + zf) for x, h in zip(xb, hw)] + [(x, y0 + h, z0 + zf) for x, h in zip(xb[::-1], hw[::-1])]
            ax.add_collection3d(Poly3DCollection([quad], alpha=0.25, facecolor=col("piso", f"{body['comp']}.piso.painel")))
            used.add("piso")
        # aberturas: soleiras nos bordos do arco
        for cu in body.get("cutouts", []):
            for side, dth in (("a", -0.5), ("b", 0.5)):
                t = math.radians(cu["theta_deg"] + dth * cu["width_deg"])
                xx = np.array([cu["x0_m"], cu["x1_m"]])
                R = np.interp(xx, xs, Rs)
                line(np.c_[xx, y0 + R * math.sin(t), z0 + R * math.cos(t)], "soleira",
                     f"{body['comp']}.abertura.{cu['id']}.soleira_{side}", lw=3.0)
    # ---- superfícies
    for sf in geo.get("surfaces", []):
        L = _surface_lines(sf)
        for q in L["outline"]:
            ax.add_collection3d(Poly3DCollection([q], alpha=0.08, facecolor="#9aa5b1", edgecolor="#6b7680", lw=0.4))
            pts.append(np.asarray(q))
        for sp in L["spars"]:
            line(sp, "alma_longarina", f"{sf.get('id', sf['comp'])}.caps", lw=2.2)
        for rb in L["ribs"]:
            line(rb, "nervura", f"{sf.get('id', sf['comp'])}.ribs", lw=0.9)
    for es in geo.get("struts", []):
        line([es["p0_m"], es["p1_m"]], "escora", es["id"], lw=3.0)
    # ---- ferragens e berço
    for m in layout["members"]:
        if m["kind"] == "ferragem" and m.get("mass_kg") is not None:
            ax.scatter([m["x_m"]], [m["y_m"]], [m["z_m"]], color=col("ferragem", m["id"]), marker="^", s=28)
            used.add("ferragem")
    em = (layout.get("fittings") or {}).get("engine_mount") or {}
    g = em.get("geometry") or {}
    if g.get("bars"):
        for a_, b_ in g["bars"]:          # nomes "apoioN" (motor) / "paredeN" (parede de fogo), N a partir de 1
            i, j = int(str(a_).removeprefix("apoio")) - 1, int(str(b_).removeprefix("parede")) - 1
            line([g["nodes_engine"][i], g["nodes_firewall"][j]], "berco_motor", "berco_motor", lw=2.0)
    # ---- eixos iguais, legenda
    allp = np.vstack(pts)
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    ctr, rng = 0.5 * (lo + hi), float((hi - lo).max())
    ax.set_xlim(ctr[0] - rng / 2, ctr[0] + rng / 2)
    ax.set_ylim(ctr[1] - rng / 2, ctr[1] + rng / 2)
    ax.set_zlim(ctr[2] - rng / 4, ctr[2] + rng / 4)
    ax.set_box_aspect((1, 1, 0.5))
    ax.view_init(elev=elev, azim=azim)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_zlabel("z [m]")
    if by_rf:
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=matplotlib.colors.Normalize(1.0, 3.0))
        fig.colorbar(sm, ax=ax, shrink=0.55, pad=0.02, label="RF_min do membro (cinzento = desconhecido)")
    else:
        order = [k for k in KIND_COLORS if k in used]
        ax.legend([Line2D([0], [0], color=KIND_COLORS[k], lw=3) for k in order], [LABELS.get(k, k) for k in order],
                  loc="upper left", fontsize=8, framealpha=0.85)
    b = layout.get("budget", {})
    ax.set_title(title or f"Estrutura paramétrica — {b.get('mass_kg', 0.0):.1f} kg; veredicto {layout.get('verdict')}",
                 fontsize=11)
    import textwrap
    ax.text2D(0.0, -0.02, textwrap.fill("Desenho do que a tabela de membros e a geometria do layout descrevem — " +
                                        str(geo.get("note", "")), 150), transform=ax.transAxes, fontsize=7,
              color="#555555", va="top")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out


def main(argv: list[str] | None = None) -> None:
    import yaml

    from acdt.core.pipeline import run_pipeline
    from acdt.domains.aircraft.mission import MissionSpec
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) < 2:
        raise SystemExit("uso: python -m acdt.domains.aircraft.structure_render exemplo.yaml saida.png [--rf]")
    p = Path(a[0])
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    sl = d.setdefault("assumptions", {}).setdefault("structure_layout", {})
    sl["enabled"] = True
    lay = run_pipeline("aircraft", MissionSpec.from_dict(d, p))["result"].structure_layout
    print(render_layout(lay, a[1], color_by="RF" if "--rf" in a else "kind"))


if __name__ == "__main__":
    main()
