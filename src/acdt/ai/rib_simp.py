# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Toolkit wrapper: opt-in SIMP-informed rib-web mass in the Phase 6 structural budget."""
from __future__ import annotations

from typing import Any

from acdt.ai.toolkit import clean
from acdt.domains.aircraft.wingbox.rib_simp_mass import apply_simp_rib_mass, rib_web_mass_from_simp


def rib_simp_mass(spec: dict) -> dict[str, Any]:
    """Budget update or a single-web mass. Missing vol, ρ+source, t+source, geometry or loads → unassessed."""
    if spec.get("masses") and spec.get("ribs"):
        cfg = spec.get("rib_simp_mass") or spec
        return clean(apply_simp_rib_mass(
            spec["masses"], spec["ribs"],
            rho_kg_m3=cfg.get("rho_kg_m3") or spec.get("rho_kg_m3"),
            rho_source=cfg.get("rho_source") or spec.get("rho_source") or "",
            t_source=cfg.get("t_source", spec.get("t_source",
                             "sizing6.size_ribs (Niu 1988 §5.4 crushing/shear/buckling/min gauge)")),
            vol=cfg.get("vol", spec.get("vol")), penal=cfg.get("penal", spec.get("penal")),
            nelx=int(cfg.get("nelx", spec.get("nelx", 40))),
            iters=int(cfg.get("iters", spec.get("iters", 40))),
            rmin=float(cfg.get("rmin", spec.get("rmin", 1.8))),
            nu=float(cfg.get("nu", spec.get("nu", 0.33))),
            stations=cfg.get("stations", spec.get("stations", "all")),
            nonoptimum_factor=spec.get("nonoptimum_factor"),
        ))
    rib = spec.get("rib") or spec
    return clean(rib_web_mass_from_simp(
        w_m=rib.get("w_m"), h_m=rib.get("h_m"), p_crush_N_m=rib.get("p_crush_N_m"),
        dV_N=rib.get("dV_N"), t_m=rib.get("t_m"), rho_kg_m3=rib.get("rho_kg_m3"),
        vol=rib.get("vol"), penal=rib.get("penal", 3.0),
        rmin=float(rib.get("rmin", 1.8)), nu=float(rib.get("nu", 0.33)),
        nelx=int(rib.get("nelx", 40)), iters=int(rib.get("iters", 40)),
        rho_source=rib.get("rho_source"), t_source=rib.get("t_source"),
    ))
