"""Operational weight and balance on top of the stability-stage mass stations.

Raymer, *Aircraft Design: A Conceptual Approach*, 6th ed., 2018, Sec. 15.1, and Roskam,
*Airplane Design* Part II, 1985, Ch. 10: every loading of crew, payload and fuel is a point on the
loading diagram, and the diagram has to sit inside the forward and aft limits.

The limits used here are the conceptual ones already in the stability stage, unless the user
supplies them:

* aft — neutral point minus the target static margin (Raymer Ch. 16);
* forward — the more-aft station of two trims with the elevator at its stop,
  x̄ = x̄_np − (Cm0 + |Cmδe| δe_max) / CL (Nelson, *Flight Stability*, 1998, Ch. 2):
  clean CLmax with the wing Cm0 (Raymer Eq. 16.13), and the full-flap flare at landing
  CLmax with wing + fuselage (Multhopp) + flap Cm0. A plain or split flap uses Glauert;
  a slotted flap uses the DATCOM Sec. 6.1.2.1 center of pressure. The flare tail lift
  slope includes Torenbeek's ground-effect factor. CLmax and the neutral-point downwash
  do not.

Structure stations stay the Roskam Part V assumptions until a layout replaces them. Useful-load
defaults sit on the fixed-mass CG (``balance`` in ``stability.DEFAULT_STATIONS``, Raymer 2018
Sec. 15.1), not on a fuselage-length fraction. Wing fuel stays at 30 % MAC.
``weight_balance.loading`` replaces the lumped crew, payload, fuel and battery; ``arm_in`` is
inches aft of the firewall. A tank is one fixed station: fuel CG shift inside a tank is not
modelled. Unusable fuel is not split out.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from acdt.core.systems.mass import (LoadItem, OperationalEnvelope, cg_limit_at, operational_loadings,
                                    outside_limits, percent_mac)


@dataclass
class WeightBalanceResult:
    evaluated: bool
    envelope: OperationalEnvelope | None = None
    x_forward_m: float | None = None
    x_aft_m: float | None = None
    forward_limit: list[tuple[float, float]] | None = None
    aft_limit: list[tuple[float, float]] | None = None
    within_limits: bool | None = None
    message: str = ""
    x_mac_le: float | None = None
    mac: float | None = None
    x_mac_le_report: float | None = None
    mac_report: float | None = None
    notes: list[str] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)

    def mac_percent(self, x: float) -> float | None:
        """Percent MAC. A weighing-form LEMAC/MAC, when set, replaces the sized wing."""
        le = self.x_mac_le if self.x_mac_le_report is None else self.x_mac_le_report
        mac = self.mac if self.mac_report is None else self.mac_report
        if not mac:
            return None
        return percent_mac(x, le, mac)

    @property
    def x_min_m(self) -> float | None:
        p = self.envelope.most_forward if self.envelope else None
        return None if p is None else p.x

    @property
    def x_max_m(self) -> float | None:
        p = self.envelope.most_aft if self.envelope else None
        return None if p is None else p.x

    def summary(self) -> dict:
        env = self.envelope
        def pt(p):
            if p is None:
                return None
            return {"name": p.name, "mass_kg": p.mass, "x_m": p.x, "x_mac_percent": self.mac_percent(p.x)}

        points = []
        if env is not None:
            for p in env.points:
                points.append(pt(p) | {"kind": p.kind})
        return {
            "evaluated": self.evaluated,
            "within_limits": self.within_limits,
            "summary": self.message,
            "x_forward_m": self.x_forward_m,
            "x_aft_m": self.x_aft_m,
            "x_min_m": self.x_min_m,
            "x_max_m": self.x_max_m,
            "forward_limit": self.forward_limit,
            "aft_limit": self.aft_limit,
            "x_mac_le_m": self.x_mac_le,
            "mac_m": self.mac,
            "x_mac_le_report_m": self.x_mac_le_report,
            "mac_report_m": self.mac_report,
            "most_forward": pt(env.most_forward) if env else None,
            "most_aft": pt(env.most_aft) if env else None,
            "points": points,
            "paths": [[{"name": p.name, "mass_kg": p.mass, "x_m": p.x} for p in path]
                      for path in (env.paths if env else [])],
            "items": self.items,
            "notes": self.notes,
        }


def _forward_from_trim(res, st) -> tuple[float | None, str]:
    from .stability import ETA_H, binding_forward_station, flap_effectiveness

    o = res.spec.assumptions["stability"]
    te = flap_effectiveness(float(o.get("elevator_cf_c", 0.30)))
    cmde = -ETA_H * st.Vh * st.CLa_h * te
    return binding_forward_station(res, st.xbar_np, cmde, float(o.get("elevator_max_deg", 25.0)),
                                   st.x_mac_le, st.mac)


def _limits(res, st, opts: dict) -> tuple[list[tuple[float, float]] | None, list[tuple[float, float]] | None, list[str]]:
    notes = []
    if opts.get("forward_limit"):
        fwd = [(float(m), float(x)) for m, x in opts["forward_limit"]]
        notes.append("Limite dianteiro em função da massa, dado pelo utilizador (weight_balance.forward_limit).")
    elif opts.get("x_forward_m") is not None:
        fwd = [(0.0, float(opts["x_forward_m"]))]
        notes.append("Limite dianteiro dado pelo utilizador (weight_balance.x_forward_m).")
    else:
        x, note = _forward_from_trim(res, st)
        notes.append(note)
        fwd = None if x is None else [(0.0, x)]
    if opts.get("aft_limit"):
        aft = [(float(m), float(x)) for m, x in opts["aft_limit"]]
        notes.append("Limite traseiro em função da massa, dado pelo utilizador (weight_balance.aft_limit).")
    elif opts.get("x_aft_m") is not None:
        aft = [(0.0, float(opts["x_aft_m"]))]
        notes.append("Limite traseiro dado pelo utilizador (weight_balance.x_aft_m).")
    else:
        aft = [(0.0, st.x_mac_le + (st.xbar_np - st.target_SM) * st.mac)]
        notes.append("Limite traseiro conceptual: ponto neutro menos a margem estática alvo (Raymer Cap. 16).")
    return fwd, aft, notes


def _row_x(res, row) -> float:
    """Station in metres from the nose. ``x_m`` is absolute. ``arm_in`` is inches aft of the firewall."""
    if row.get("x_m") is not None:
        return float(row["x_m"])
    if row.get("arm_in") is None:
        raise ValueError(f"{row.get('name', 'loading')}: give x_m or arm_in")
    from .stability import INCH, _firewall_x
    x_fw = _firewall_x(res, res.config.fuselage.length)
    if x_fw is None:
        raise ValueError(f"{row.get('name', 'loading')}: arm_in needs a firewall datum "
                         "(stability.firewall_x_m, firewall_fraction or firewall_from_engine)")
    return x_fw + float(row["arm_in"]) * INCH


# Useful-load keys a loading list replaces. Structure stations stay.
_LUMPED_USEFUL = frozenset({"fuel", "payload", "crew", "battery"})


def _items_from_stations(res, opts: dict) -> list[LoadItem]:
    """Stability stations, unless ``weight_balance.loading`` replaces the useful-load lumps.

    A loading row is ``{name, mass_min_kg, mass_max_kg, kind, fuel_order, x_m | arm_in}``.
    ``arm_in`` is inches aft of the firewall. ``mass_max_kg: null`` on a fuel row uses the sized
    fuel mass. ``extra_items`` still append, so a loading list must not repeat them.
    """
    loading = list(opts.get("loading") or [])
    skip = _LUMPED_USEFUL if loading else frozenset()
    electric = res.spec.propulsion_kind == "electric"
    optional_crew = bool(opts.get("crew_optional", False))
    items: list[LoadItem] = []
    for s in res.stability.stations:
        key, mass, x = s["item"], float(s["mass_kg"]), float(s["x_m"])
        if key in skip or mass <= 0:
            continue
        if key == "fuel" and not electric:
            items.append(LoadItem("combustível", x, 0.0, mass, "fuel", 0))
        elif key == "payload":
            items.append(LoadItem("payload", x, 0.0, mass, "variable"))
        elif key == "crew":
            if optional_crew:
                items.append(LoadItem("tripulação", x, 0.0, mass, "variable"))
            else:
                items.append(LoadItem("tripulação", x, mass, mass, "fixed"))
        elif key == "battery":
            items.append(LoadItem("bateria", x, mass, mass, "fixed"))
        else:
            items.append(LoadItem(key, x, mass, mass, "fixed"))
    if loading:
        fuel_mass = next((float(s["mass_kg"]) for s in res.stability.stations if s["item"] == "fuel"), 0.0)
        for row in loading:
            kind = row.get("kind", "variable")
            name = str(row["name"])
            if row.get("mass_max_kg") is None:
                if kind != "fuel":
                    raise ValueError(f"{name}: mass_max_kg may be empty only for kind fuel")
                mass_max = fuel_mass
            else:
                mass_max = float(row["mass_max_kg"])
            if row.get("mass_min_kg") is None:
                mass_min = mass_max if kind == "fixed" else 0.0
            else:
                mass_min = float(row["mass_min_kg"])
            items.append(LoadItem(name, _row_x(res, row), mass_min, mass_max, kind,
                                  int(row.get("fuel_order", 0))))
    for extra in opts.get("extra_items") or []:
        items.append(LoadItem(str(extra["name"]), float(extra["x_m"]), float(extra.get("mass_min_kg", 0.0)),
                              float(extra["mass_max_kg"]), extra.get("kind", "variable"),
                              int(extra.get("fuel_order", 0))))
    return items


def analyse_weight_balance(res) -> WeightBalanceResult | None:
    """Loading diagram for the aircraft the stability stage just placed. None if that stage did not run."""
    st = getattr(res, "stability", None)
    if st is None or not st.stations:
        return None
    opts = res.spec.assumptions.get("weight_balance") or {}
    items = _items_from_stations(res, opts)
    if not items:
        return WeightBalanceResult(False, notes=["Sem itens de massa com estação — envelope não calculado."])
    env = operational_loadings(items, res.sizing.W0)
    fwd, aft, notes = _limits(res, st, opts)
    if opts.get("loading"):
        notes.append("Carregamento operacional em weight_balance.loading: substitui tripulação, payload, "
                     "combustível e bateria das estações. arm_in são polegadas atrás da firewall. "
                     "A estrutura mantém as estações da estabilidade. mass_max_kg vazio num item fuel "
                     "usa a massa de combustível dimensionada. "
                     "O combustível arde na estação do tanque; não há combustível inutilizável separado.")
        if opts.get("crew_optional"):
            notes.append("weight_balance.crew_optional não se aplica com loading: a tripulação é uma linha "
                         "do carregamento.")
    else:
        notes.append("Estações de CG: as da estabilidade. Estrutura: Roskam Parte V, Tabela 8.1 (PRESSUPOSTO). "
                     "Tripulação, carga e bateria, se a missão não as der, ficam no CG da massa fixa "
                     "(Raymer 2018 Sec. 15.1); combustível de asa a 30 % da CMA. "
                     "Substituir em assumptions.stability.stations, weight_balance.loading ou extra_items. "
                     "O combustível arde na estação do tanque; não há combustível inutilizável separado.")
        notes.append("A tripulação pode sair do carregamento (weight_balance.crew_optional)."
                     if opts.get("crew_optional") else
                     "A tripulação, quando existe, vai em todos os carregamentos.")
    bad = outside_limits(env.points, fwd, aft) if env.points else []
    x_fwd = cg_limit_at(fwd, res.sizing.W0) if fwd else None
    x_aft = cg_limit_at(aft, res.sizing.W0) if aft else None
    if not env.points or (fwd is None and aft is None):
        within = None
        message = "Envelope calculado sem limites dianteiro e traseiro para comparar."
    else:
        within = not bad
        lo = env.most_forward
        hi = env.most_aft
        span = (f"extremos {lo.x:.3f} m ({lo.name}, {lo.mass:.0f} kg) e "
                f"{hi.x:.3f} m ({hi.name}, {hi.mass:.0f} kg)")
        if within:
            message = f"Todos os {len(env.points)} carregamentos dentro dos limites conceptuais; {span}."
        else:
            message = (f"{len(bad)} carregamento(s) fora dos limites conceptuais; {span}. "
                       "Os limites são de projeto (margem estática e trim), não um envelope aprovado.")
    x_le_report, mac_report, report_note = _report_mac(res, opts, st)
    if report_note:
        notes.append(report_note)
    return WeightBalanceResult(
        True, env, x_fwd, x_aft, fwd, aft, within, message, st.x_mac_le, st.mac,
        x_le_report, mac_report, notes,
        [{"name": i.name, "x_m": i.x, "mass_min_kg": i.mass_min, "mass_max_kg": i.mass_max, "kind": i.kind}
         for i in items])


def _report_mac(res, opts: dict, st) -> tuple[float | None, float | None, str | None]:
    """Weighing-form LEMAC and MAC, inches aft of the firewall. Checks stay in metres."""
    arm, mac_in = opts.get("lemac_arm_in"), opts.get("mac_in")
    if arm is None or mac_in is None:
        return None, None, None
    from .stability import INCH, _firewall_x
    x_fw = _firewall_x(res, res.config.fuselage.length)
    if x_fw is None or float(mac_in) <= 0.0:
        return None, None, ("lemac_arm_in e mac_in ignorados: falta o datum da firewall ou a CMA do relatório.")
    x_le = x_fw + float(arm) * INCH
    mac = float(mac_in) * INCH
    note = (
        f"Percentagem da CMA no diagrama: (braço − {float(arm):.2f} in) / {float(mac_in):.2f} in, "
        f"datum na firewall. A CMA dimensionada é {st.mac:.3f} m, com bordo de ataque a {st.x_mac_le:.3f} m "
        "do nariz. A verificação wb:envelope continua em metros sobre essa CMA. O polígono de limites de um "
        "POH, quando existe, não é a nuvem de carregamentos.")
    return x_le, mac, note


def plot_loading_diagram(wb: WeightBalanceResult, path, title: str = ""):
    """Mass versus CG. The polygon is the loading envelope; the lines are the conceptual limits."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    env = wb.envelope
    if env is None or not env.points:
        return None
    use_mac = wb.mac_percent(0.0) is not None
    def xx(x):
        return wb.mac_percent(x) if use_mac else x

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    hull = _hull([(xx(p.x), p.mass) for p in env.points])
    if len(hull) >= 2:
        closed = hull + [hull[0]]
        ax.plot([p[0] for p in closed], [p[1] for p in closed], color="C0", lw=1.2)
        ax.fill([p[0] for p in closed], [p[1] for p in closed], color="C0", alpha=0.12)
    ax.scatter([xx(p.x) for p in env.points], [p.mass for p in env.points], s=18, color="C0", zorder=3)
    for path_pts in env.paths:
        ax.plot([xx(p.x) for p in path_pts], [p.mass for p in path_pts], color="C1", lw=1.0, alpha=0.7)
    for p in (env.most_forward, env.most_aft):
        if p is not None:
            ax.annotate(p.name, (xx(p.x), p.mass), fontsize=7, xytext=(4, 4), textcoords="offset points")
    masses = [p.mass for p in env.points]
    m0, m1 = min(masses), max(masses)
    span = max(m1 - m0, 1.0)

    def draw(limit, color, label):
        if not limit:
            return
        xs, ys = [], []
        for m in (m0 - 0.05 * span, m1 + 0.05 * span):
            x = cg_limit_at(limit, m)
            if x is not None:
                xs.append(xx(x))
                ys.append(m)
        if len(xs) >= 2:
            ax.plot(xs, ys, color=color, lw=1.3, label=label)

    draw(wb.forward_limit, "C3", "limite dianteiro")
    draw(wb.aft_limit, "C2", "limite traseiro")
    ax.set_xlabel("x_cg [% CMA]" if use_mac else "x_cg [m]")
    ax.set_ylabel("massa [kg]")
    ax.set_title(title or "Carregamento operacional")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def _hull(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]
