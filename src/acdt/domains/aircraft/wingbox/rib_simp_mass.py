# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Feed SIMP-informed rib-web mass back into the Phase 6 structural budget (opt-in).

The 2-D SIMP solver itself is :func:`rib_simp` (Bendsøe 1989; Bendsøe & Sigmund 2003;
density filter: Bruns & Tortorelli 2001; OC update: Sigmund 2001 / Andreassen et al. 2011).
This module does not invent a second topology method, a rib thickness, or a material
density. Thickness comes from :func:`sizing6.size_ribs` (Niu §5.4 crushing, shear,
buckling, min gauge). Material density must be supplied with its source (e.g. the
existing MMPDS Al 2024-T3 card). The volume fraction ``vol`` is a required design
input (Sigmund 2001), not a mass the solver is allowed to invent.

Mass of the box web (between spars) of one rib:

    m_web = mean(ρ_SIMP) · w · h · t · ρ_material

The nose/tail remainder of the rib is outside the SIMP domain and stays the
size_ribs 50 % lightening PRESSUPOSTO (Abbott & von Doenhoff section area minus
the box rectangle). Both semispans are counted, as in ``size_box6``.

Opt-in and backward compatible: without a ``rib_simp_mass`` request the budget is
unchanged. Missing geometry, load case (p_crush, ΔV), thickness, material density
+ source, or volume fraction → the SIMP term is unassessed; sized (size_ribs)
masses are retained and never presented as a SIMP close-out. A root-only run is
not silently extrapolated to the other stations (unassessed ≠ pass).
"""
from __future__ import annotations

import math
from typing import Any

from .rib_simp import rib_simp

SOURCE = ("Bendsøe 1989; Bendsøe & Sigmund, Topology Optimization, 2003; "
          "Bruns & Tortorelli 2001; Sigmund 2001; Andreassen et al. 2011; "
          "Niu, Airframe Structural Design, 1988 §5.4 (rib sizing, not SIMP)")


def _num(name, v, lo=None, hi=None):
    if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
        return None, f"{name} missing or not numeric"
    x = float(v)
    if not math.isfinite(x):
        return None, f"{name} not finite"
    if lo is not None and x < lo:
        return None, f"{name}={x} below {lo}"
    if hi is not None and x > hi:
        return None, f"{name}={x} above {hi}"
    return x, None


def hole_mass_factor(D_h) -> float:
    """Net-area factor used by size_ribs: 1 − π D_h/8 for a circular lightening hole, else 1."""
    if not D_h:
        return 1.0
    return 1.0 - math.pi * float(D_h) / 8.0


def rib_web_mass_from_simp(*, w_m: float, h_m: float, p_crush_N_m: float, dV_N: float,
                           t_m: float, rho_kg_m3: float, vol: float, penal: float = 3.0,
                           rmin: float = 1.8, nu: float = 0.33, nelx: int = 40, iters: int = 40,
                           tol: float = 0.01, rho_source: str | None = None,
                           t_source: str | None = None) -> dict[str, Any]:
    """SIMP-informed mass of one rib web. Unassessed if a required input or source is missing."""
    notes, un = [SOURCE], []
    for name, val, lo, hi in (
        ("w_m", w_m, 1e-6, 50.0), ("h_m", h_m, 1e-6, 20.0),
        ("p_crush_N_m", p_crush_N_m, 0.0, 1e9), ("dV_N", dV_N, 0.0, 1e9),
        ("t_m", t_m, 1e-6, 0.2), ("rho_kg_m3", rho_kg_m3, 1.0, 3e4),
        ("vol", vol, 1e-3, 1.0), ("penal", penal, 1.0, 10.0),
    ):
        _, err = _num(name, val, lo=lo, hi=hi)
        if err:
            un.append(err)
    if not (isinstance(rho_source, str) and rho_source.strip()):
        un.append("rho_source (material density source required — density not invented)")
    if not (isinstance(t_source, str) and t_source.strip()):
        un.append("t_source (rib thickness source required — typically size_ribs / Niu §5.4)")
    if un:
        return {"status": "unassessed", "mass_web_kg": None, "vol_achieved": None,
                "unassessed_terms": un, "notes": notes + [
                    "SIMP pedido mas inputs em falta — a massa size_ribs não é um resultado SIMP"
                ], "source": SOURCE}
    solid = float(w_m) * float(h_m) * float(t_m) * float(rho_kg_m3)
    try:
        rs = rib_simp(float(w_m), float(h_m), float(p_crush_N_m), float(dV_N),
                      nelx=int(nelx), vol=float(vol), penal=float(penal), rmin=float(rmin),
                      nu=float(nu), iters=int(iters), tol=float(tol))
    except Exception as exc:  # noqa: BLE001 — solver failure is unassessed, not a silent mass
        return {"status": "unassessed", "mass_web_kg": None, "vol_achieved": None,
                "unassessed_terms": [f"SIMP solve failed: {exc}"], "notes": notes, "source": SOURCE,
                "solid_web_kg": solid}
    vol_a = float(rs["vol"])
    return {
        "status": "ok", "mass_web_kg": vol_a * solid, "vol_target": float(vol),
        "vol_achieved": vol_a, "solid_web_kg": solid, "compliance": rs["compliance"],
        "iters": rs["iters"], "nelx": rs["nelx"], "nely": rs["nely"],
        "unassessed_terms": [], "notes": notes, "source": SOURCE,
        "rho_source": rho_source.strip(), "t_source": t_source.strip(),
        "penal": float(penal),
    }


def _stations(cfg: dict, n: int) -> tuple[list[int] | None, list[str]]:
    raw = cfg.get("stations", "all")
    if raw in (None, "all", "*"):
        return list(range(n)), []
    if raw in ("root", 0, "0"):
        return [0], ["stations=root: outras estações não são extrapoladas (SIMP orçamento unassessed se não for all)"]
    if isinstance(raw, (list, tuple)) and raw:
        idx = []
        un = []
        for i in raw:
            try:
                k = int(i)
            except (TypeError, ValueError):
                un.append(f"station {i} not an index")
                continue
            if 0 <= k < n:
                idx.append(k)
            else:
                un.append(f"station {k} out of range 0..{n-1}")
        return (idx or None), un
    return None, [f"stations must be 'all', 'root', or a list of indices (got {raw!r})"]


def apply_simp_rib_mass(masses: dict, ribs: dict, *, rho_kg_m3: float, rho_source: str,
                        t_source: str = "sizing6.size_ribs (Niu 1988 §5.4 crushing/shear/buckling/min gauge)",
                        vol: float | None = None, penal: float | None = None,
                        nelx: int = 40, iters: int = 40, rmin: float = 1.8, nu: float = 0.33,
                        stations="all", nonoptimum_factor: float | None = None,
                        n_semispans: int = 2) -> dict[str, Any]:
    """Replace ``masses['ribs']`` with SIMP-informed web mass + unchanged LE/TE remainder.

    ``ribs`` is the Phase 6 ``details['ribs']`` dict (y, w_m, h_m, t_mm or t_m, dV_N,
    p_crush_N_m, and either rest_kg / box_part_kg or D_h + enough data to rebuild them).
    Both semispans are counted (``n_semispans=2``), matching ``size_box6``.
    """
    out: dict[str, Any] = {"status": "unassessed", "source": SOURCE, "unassessed_terms": [],
                           "notes": [], "masses_sized": dict(masses or {}), "masses_simp": None,
                           "ribs_sized_kg": None, "ribs_simp_kg": None, "delta_kg": None,
                           "per_rib": []}
    if not masses or "ribs" not in masses:
        out["unassessed_terms"].append("masses['ribs'] (sized budget) missing")
        return out
    out["ribs_sized_kg"] = float(masses["ribs"])
    if vol is None:
        out["unassessed_terms"].append("vol (volume fraction is a required SIMP input, not invented)")
    if penal is None:
        out["unassessed_terms"].append("penal (SIMP penalty; typical p=3 per Bendsøe/Sigmund — must be stated)")
    n = len(ribs.get("w_m") or ribs.get("h_m") or [])
    if n == 0:
        out["unassessed_terms"].append("ribs geometry (w_m, h_m) missing")
        return out if out["unassessed_terms"] else out
    idx, st_notes = _stations({"stations": stations}, n)
    out["notes"].extend(st_notes)
    if idx is None:
        out["unassessed_terms"].extend(st_notes or ["stations unassessed"])
        return out
    if sorted(idx) != list(range(n)):
        out["unassessed_terms"].append(
            f"SIMP only at stations {idx} of 0..{n-1} — no silent extrapolation to the other ribs"
        )
        return out
    if out["unassessed_terms"]:
        out["notes"].append("orçamento size_ribs retido; unassessed≠pass")
        return out

    t_list = ribs.get("t_m") or ([1e-3 * x for x in ribs["t_mm"]] if ribs.get("t_mm") is not None else None)
    if t_list is None or len(t_list) != n:
        out["unassessed_terms"].append("rib thickness t_m or t_mm missing")
        return out
    rest = ribs.get("rest_kg")
    box_part = ribs.get("box_part_kg")
    if rest is None or len(rest) != n:
        # rebuild box_part from D_h if possible; rest then from the sized total
        Dh = ribs.get("D_h") or [0] * n
        box_part = []
        for i in range(n):
            t = float(t_list[i])
            fac = hole_mass_factor(Dh[i] if i < len(Dh) else 0)
            box_part.append(fac * float(ribs["w_m"][i]) * float(ribs["h_m"][i]) * t * float(rho_kg_m3))
        sized_half = float(masses["ribs"]) / n_semispans
        rest_total = sized_half - float(sum(box_part))
        if rest_total < -1e-9:
            out["unassessed_terms"].append("cannot infer LE/TE remainder (rest_kg) from sized ribs and box_part")
            return out
        # distribute remainder in proportion to box_part (documentation: not a SIMP result)
        sbp = float(sum(box_part)) or 1.0
        rest = [rest_total * (b / sbp) for b in box_part]
        out["notes"].append(
            "resto nariz/cauda inferido do orçamento size_ribs (50 % aligeirado, PRESSUPOSTO) — fora do domínio SIMP"
        )
    per, un = [], []
    m_web = 0.0
    m_rest = 0.0
    for i in idx:
        one = rib_web_mass_from_simp(
            w_m=float(ribs["w_m"][i]), h_m=float(ribs["h_m"][i]),
            p_crush_N_m=float(ribs["p_crush_N_m"][i]), dV_N=float(ribs["dV_N"][i]),
            t_m=float(t_list[i]), rho_kg_m3=float(rho_kg_m3), vol=float(vol), penal=float(penal),
            rmin=float(rmin), nu=float(nu), nelx=int(nelx), iters=int(iters),
            rho_source=rho_source, t_source=t_source,
        )
        one["station"] = i
        one["y_m"] = (ribs.get("y") or [None] * n)[i]
        one["rest_kg"] = float(rest[i])
        per.append(one)
        if one["status"] != "ok":
            un.extend(f"rib[{i}]: {t}" for t in one.get("unassessed_terms") or ["unassessed"])
        else:
            m_web += float(one["mass_web_kg"])
            m_rest += float(rest[i])
    out["per_rib"] = per
    if un:
        out["unassessed_terms"] = un
        out["notes"].append("pelo menos uma nervura unassessed — orçamento size_ribs retido (nunca zero silencioso)")
        return out
    ribs_simp = n_semispans * (m_web + m_rest)
    new = dict(masses)
    nonopt = float(nonoptimum_factor if nonoptimum_factor is not None else
                   (1.0 + float(masses.get("nonoptimum", 0.0)) / float(masses["ideal"])
                    if masses.get("ideal") else 1.25))
    ideal = float(masses["ideal"]) - float(masses["ribs"]) + ribs_simp
    new["ribs"] = float(ribs_simp)
    new["ideal"] = float(ideal)
    new["nonoptimum"] = float((nonopt - 1.0) * ideal)
    new["total"] = float(nonopt * ideal)
    out.update({
        "status": "ok", "masses_simp": new, "ribs_simp_kg": float(ribs_simp),
        "delta_kg": float(ribs_simp - masses["ribs"]),
        "web_simp_kg_semispan": float(m_web), "rest_kg_semispan": float(m_rest),
        "n_ribs_semispan": n, "n_semispans": n_semispans, "nonoptimum_factor": nonopt,
        "notes": out["notes"] + [
            f"alma SIMP (fração alcançada × t × w × h × ρ); resto nariz/cauda = size_ribs PRESSUPOSTO; "
            f"×{n_semispans} semi-asas"
        ],
    })
    return out


def apply_to_box(box, cfg: dict, *, material: dict | None = None) -> dict[str, Any]:
    """Apply :func:`apply_simp_rib_mass` to a Phase 6 ``WingBoxResult`` (mutates masses if status=ok)."""
    cfg = dict(cfg or {})
    mat = material or {}
    rho = cfg.get("rho_kg_m3", mat.get("rho"))
    rho_source = cfg.get("rho_source") or mat.get("note") or mat.get("source")
    report = apply_simp_rib_mass(
        box.masses, (box.details or {}).get("ribs") or {},
        rho_kg_m3=rho if rho is not None else 0.0,  # validation happens inside
        rho_source=rho_source if isinstance(rho_source, str) else "",
        t_source=cfg.get("t_source", "sizing6.size_ribs (Niu 1988 §5.4 crushing/shear/buckling/min gauge)"),
        vol=cfg.get("vol"), penal=cfg.get("penal"),
        nelx=int(cfg.get("nelx", 40)), iters=int(cfg.get("iters", 40)),
        rmin=float(cfg.get("rmin", 1.8)), nu=float(cfg.get("nu", mat.get("nu", 0.33))),
        stations=cfg.get("stations", "all"),
        nonoptimum_factor=getattr(box, "nonoptimum_factor", None),
    )
    if report["status"] == "ok":
        box.masses.update(report["masses_simp"])
        box.details = dict(box.details or {})
        box.details["rib_simp_mass"] = {k: report[k] for k in
                                        ("status", "ribs_sized_kg", "ribs_simp_kg", "delta_kg", "source") if k in report}
        box.notes = list(box.notes or []) + [
            f"nervuras SIMP no orçamento: {report['ribs_sized_kg']:.3f} → {report['ribs_simp_kg']:.3f} kg "
            f"(Δ {report['delta_kg']:+.3f} kg); unassessed≠pass"
        ]
    else:
        box.details = dict(box.details or {})
        box.details["rib_simp_mass"] = {"status": "unassessed",
                                        "unassessed_terms": report.get("unassessed_terms")}
        box.notes = list(box.notes or []) + [
            "SIMP no orçamento unassessed — massas size_ribs retidas (nunca pass silencioso)"
        ]
    return report
